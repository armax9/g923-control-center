#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Private Steam/game experiment preparation. Does not launch Steam or a game."""
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_vdf(text):
    # Valve text KeyValues, including escaped quotes/backslashes and // comments.
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[{}]|//[^\n]*', text)
    tokens = [t for t in tokens if not t.startswith('//')]
    def string(token):
        if not token.startswith('"'):
            raise ValueError('Expected quoted VDF key/value')
        return re.sub(r'\\([\\"])', r'\1', token[1:-1])
    def block(index, nested=False):
        result = {}
        while index < len(tokens):
            if tokens[index] == '}':
                if not nested:
                    raise ValueError('Unexpected VDF close')
                return result, index + 1
            key = string(tokens[index]); index += 1
            if key in result or index >= len(tokens):
                raise ValueError('Duplicate or missing VDF value')
            if tokens[index] == '{':
                result[key], index = block(index + 1, True)
            else:
                result[key] = string(tokens[index]); index += 1
        if nested:
            raise ValueError('Unclosed VDF block')
        return result, index
    return block(0)[0]


def write_vdf(data, indent=''):
    quote = lambda value: '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'
    lines = []
    for key, value in data.items():
        if isinstance(value, dict):
            lines += [indent + quote(key), indent + '{', write_vdf(value, indent + '\t'), indent + '}']
        else:
            lines += [indent + quote(key) + '\t\t' + quote(value)]
    return '\n'.join(lines) + '\n'


def windows(path):
    return 'Z:' + str(path.resolve()).replace('/', '\\')


def prepare(session, source_bottle, game_exe, transport, sdk):
    session, source_bottle, game_exe, transport, sdk = (
        path.resolve() for path in [session, source_bottle, game_exe, transport, sdk])
    if session.exists() or source_bottle.name != 'Steam' or not (source_bottle/'cxbottle.conf').is_file():
        raise ValueError('Need fresh output and existing Steam bottle')
    if json.loads((transport/'manifest.json').read_text()).get('purpose') != 'g923-isolated-crossover-hid-transport':
        raise ValueError('Not a prepared transport')
    if sha(sdk) != '2468bdafe64c09ff42ef26f09e49f2096321bb687467323aafb3f0672fb83315':
        raise ValueError('Unreviewed original SDK')
    library = source_bottle/'drive_c/Program Files (x86)/Steam/steamapps/libraryfolders.vdf'
    vdf = parse_vdf(library.read_text())
    folders = vdf.get('libraryfolders', vdf.get('LibraryFolders', {}))
    candidates = [entry for entry in folders.values() if isinstance(entry, dict) and '690790' in entry.get('apps', {})]
    if len(candidates) != 1:
        raise ValueError('Cannot uniquely identify installed game library')
    source_manifest = game_exe.parent.parent.parent/'appmanifest_690790.acf'
    app = parse_vdf(source_manifest.read_text())['AppState']
    install = app['installdir']
    if Path(install).name != install or '\\' in install:
        raise ValueError('Unsafe game install directory')
    session.mkdir(parents=True)
    (session/'runtime').symlink_to(transport/'runtime', target_is_directory=True)
    bottle = session/'G923TFGame'
    subprocess.run(['cp', '-cR', str(source_bottle), str(bottle)], check=True)
    system_dinput=bottle/'drive_c/windows/system32/dinput8.dll'
    if system_dinput.is_symlink():raise ValueError('Unexpected cloned system DInput symlink')
    shutil.copy2(system_dinput,session/'cloned-system-dinput8-before.dll')
    shutil.copy2(transport/'runtime/lib/wine/x86_64-windows/dinput8.dll',system_dinput)
    registry=bottle/'system.reg';text=registry.read_text()
    header='[System\\\\CurrentControlSet\\\\Services\\\\winebus]'
    pos=text.find(header)
    if pos<0:raise ValueError('Missing winebus service registry section')
    end=text.find('\n[',pos+1)
    if end<0:end=len(text)
    block=text[pos:end]
    if '"EnableHidraw"=' in block and '046D:C266' not in block:raise ValueError('Unreviewed existing HID allowlist')
    if '"EnableHidraw"=' not in block:
        line_end=text.index('\n',pos)+1
        text=text[:line_end]+'"EnableHidraw"=str(7):"046D:C266\\0"\n'+text[line_end:]
        registry.write_text(text)
    (bottle/'g923-owned-prefix.json').write_text(json.dumps(dict(
        purpose='g923-isolated-crossover-hid-transport', project=str(ROOT), source_bottle=str(source_bottle)), indent=2)+'\n')
    # Replace only the cloned Documents symlink so test settings cannot write to
    # the user's accepted settings directory. Copy current DR2 settings verbatim.
    documents = bottle/'drive_c/users/crossover/Documents'
    source_documents = source_bottle/'drive_c/users/crossover/Documents'
    if not documents.is_symlink():
        raise ValueError('Expected cloned Documents symlink; refusing unexpected layout')
    documents.unlink(); documents.mkdir()
    settings = source_documents/'My Games/DiRT Rally 2.0'
    if settings.is_dir():
        (documents/'My Games').mkdir()
        subprocess.run(['cp', '-cR', str(settings), str(documents/'My Games/DiRT Rally 2.0')], check=True)
    private_library = session/'SteamLibrary'
    (private_library/'steamapps/common').mkdir(parents=True)
    shutil.copy2(source_manifest, private_library/'steamapps/appmanifest_690790.acf')
    candidates[0]['path'] = windows(private_library)
    candidates[0]['apps'] = {'690790': candidates[0]['apps']['690790']}
    (bottle/'drive_c/Program Files (x86)/Steam/steamapps/libraryfolders.vdf').write_text(write_vdf(vdf))
    game = session/'game'; game.mkdir()
    excluded = {'dinput8.dll', 'steam_appid.txt', 'crossover-ffb-observe.log', 'g923-sdk-trace.jsonl', game_exe.name.lower()}
    for path in game_exe.parent.iterdir():
        if path.name.lower() in excluded or path.name.lower().endswith(('.log', '.dmp')):
            continue
        (game/path.name).symlink_to(path, target_is_directory=path.is_dir())
    shutil.copy2(game_exe, game/game_exe.name)
    (game/'steam_appid.txt').write_text('690790\n')
    (private_library/'steamapps/common'/install).symlink_to(game, target_is_directory=True)
    uid = secrets.randbelow(1000000000) + 1000000000
    directory = Path('/tmp')/f'crossover-ffb-{uid}'; directory.mkdir(mode=0o700)
    dll = bytearray((ROOT/'build/crossover-base/dinput8.dll').read_bytes())
    if dll.count(b'CFBUID=0\0') != 1:
        raise ValueError('Unknown project DLL')
    index = dll.index(b'CFBUID=0\0')
    dll[index:index+24] = ('CFBUID='+str(uid)).encode().ljust(24,b'\0')
    (game/'dinput8.dll').write_bytes(dll)
    target_sdk = bottle/'drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll'
    target_sdk.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(sdk, target_sdk)
    settings_hashes = {str(path.relative_to(settings)): sha(path) for path in settings.rglob('*') if path.is_file() and not path.name.startswith('.')}
    manifest = dict(purpose='g923-isolated-crossover-hid-transport', game_experiment=True,
                    source_bottle=str(source_bottle), source_game=str(game_exe), bottle='G923TFGame',
                    game_exe=str(game/game_exe.name), game_sha=sha(game_exe), game_dll_sha=sha(game/'dinput8.dll'),
                    steam_api_sha=sha(game/'steam_api64.dll'), mapping=str(directory/'ffb-v2.bin'),
                    source_game_dll_sha=sha(game_exe.parent/'dinput8.dll'), settings_hashes=settings_hashes,
                    sdk_sha=sha(target_sdk), private_system_dinput_sha=sha(system_dinput), hidraw_allowlist='046D:C266', runtime_hashes={name: sha(transport/'runtime/lib/wine'/name) for name in
                        ['x86_64-unix/winebus.so','x86_64-windows/winebus.sys']},
                    launch_arguments=['-novr'], input_only_publisher=True, sdk_is_only_force_sender=True,
                    game_launched=False, original_game_modified=False, source_bottle_modified=False)
    (session/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
