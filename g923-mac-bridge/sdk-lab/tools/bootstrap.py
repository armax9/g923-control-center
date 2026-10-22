#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Discover and install selected game integrations. Never starts Wine, games or HID.

All modifications are explicit install operations. Existing mods are preserved;
new files and registry changes have a transaction journal and rollback checks.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile

import discovery
from portable_paths import ROOT, digest, payload
from profile_store import (default_registry_path, load_registry, migrate_legacy,
                           profile_from_manifest, register)

SUPPORTED = {227300: ('Euro Truck Simulator 2', 'eurotrucks2.exe'),
             690790: ('DiRT Rally 2.0', 'dirtrally2.exe')}
SDK_SHA = '2468bdafe64c09ff42ef26f09e49f2096321bb687467323aafb3f0672fb83315'
MARKER = b'G923 chain opt-in v1\n'


def identity(appid, exe, bottle):
    return str(appid) + '-' + hashlib.sha256((str(bottle) + '\0' + str(exe)).encode()).hexdigest()[:12]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def replace_bytes(path, expected, replacement):
    """Registry replacement is atomic; a failed write leaves its old bytes intact."""
    if path.is_symlink() or path.read_bytes() != expected:
        raise ValueError('Installation input changed: ' + str(path))
    descriptor, name = tempfile.mkstemp(prefix='.g923-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(replacement);stream.flush();os.fsync(stream.fileno())
        temporary.chmod(path.stat().st_mode & 0o777)
        if path.read_bytes() != expected:
            raise ValueError('Installation input changed: ' + str(path))
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def select_installation(appid, exe, prefix, runner, inventory=None):
    exe, prefix, runner = (Path(p).expanduser().resolve() for p in (exe, prefix, runner))
    if appid not in SUPPORTED:
        raise ValueError('This game integration is not available for automatic installation yet.')
    if not exe.is_file() or exe.name.casefold() != SUPPORTED[appid][1]:
        raise ValueError('Select the installed ' + SUPPORTED[appid][0] + ' executable.')
    inventory = discovery.discover(applications=[runner], bottle_roots=[prefix.parent]) if inventory is None else inventory
    bottles = [b for b in inventory['bottles'] if Path(b['path']).resolve() == prefix]
    runners = [r for r in inventory['runners'] if Path(r['path']).resolve() == runner]
    if len(bottles) != 1 or len(runners) != 1:
        raise ValueError('The selected bottle or CrossOver application is unavailable. Refresh the locations.')
    bottle, runtime = bottles[0], runners[0]
    if runtime['id'] not in bottle['runner_ids']:
        raise ValueError('This CrossOver version does not match the bottle. Open it in the intended CrossOver version first.')
    # Explicitly chosen files may be outside Steam. Do not invent a Steam install.
    games = [g for g in inventory['games'] if g.get('exe') and Path(g['exe']).resolve() == exe and g.get('bottle_id') == bottle['id']]
    steam = next((str(Path(g['steam_root'])/'Steam.exe') for g in games if (Path(g['steam_root'])/'Steam.exe').is_file()), None)
    return exe, prefix, runtime, steam


def stopped():
    """Offline Wine registry writes require a stopped prefix; never kill processes."""
    text = subprocess.check_output(['/bin/ps', '-axo', 'comm='], text=True)
    names = [Path(line.strip()).name.casefold() for line in text.splitlines()]
    if any(n in ('wine', 'wine64', 'wine64-preloader', 'wine-preloader', 'steam.exe',
                 'dirtrally2.exe', 'eurotrucks2.exe') or n.startswith('wineserver') for n in names):
        raise ValueError('Close Steam, games and CrossOver before installing components. Nothing was closed automatically.')


def registry_value(text, key, name, value):
    """Add one string value, preserving every unrelated section and setting."""
    section = re.search(r'^\[' + re.escape(key) + r'\][^\n]*\n.*?(?=^\[|\Z)', text, re.M|re.S)
    encoded = value.replace('\\', '\\\\').replace('"', '\\"')
    replacement = '"' + name + '"="' + encoded + '"\n'
    previous = None
    if section:
        block = section.group()
        match = re.search(r'^"' + re.escape(name) + r'"=(.*)$', block, re.M)
        if match:
            previous = match.group(1)
            block = block[:match.start()] + replacement.rstrip('\n') + block[match.end():]
        else:
            end = block.index('\n') + 1
            block = block[:end] + replacement + block[end:]
        return text[:section.start()] + block + text[section.end():], previous
    return text.rstrip() + '\n\n[' + key + ']\n' + replacement + '\n', previous


def dll_with_mapping(source, uid):
    raw = bytearray(source.read_bytes())
    matches = list(re.finditer(rb'CFBUID=\d+\x00', raw))
    if len(matches) != 1 or matches[0].start() + 24 > len(raw):
        raise ValueError('Unexpected DirectInput bridge payload')
    start = matches[0].start()
    if any(raw[start+len(matches[0].group()):start+24]):
        raise ValueError('Invalid DirectInput mapping field')
    raw[start:start+24] = ('CFBUID=' + str(uid)).encode().ljust(24, b'\0')
    return raw


def status(registry=None, exe=None, prefix=None):
    from auto_bridge import installation
    profiles, issues = [], []
    for profile in load_registry(registry)['profiles']:
        if exe and Path(profile['game_exe']).resolve() != Path(exe).resolve():
            continue
        if prefix and Path(profile['source_bottle']).resolve() != Path(prefix).resolve():
            continue
        item = dict(profile, installed=False, detail='Not installed')
        try:
            state = installation(profile['appid'], profile=profile)
            item.update(installed=state == 'installed', detail='Installed' if state == 'installed' else 'Missing components; patch required')
            if profile['appid']==690790:
                from native_connection import live_status
                transport=live_status(Path(profile['session_dir']),json.loads((Path(profile['session_dir'])/'manifest.json').read_text()))
                item['nativeTransport']=transport['state']
                item['transportDetail']=transport['detail']
                if transport['state']=='setup_required':item.update(installed=False,detail=transport['detail'])
        except Exception as error:
            item['detail'] = str(error)
        profiles.append(item)
    return {'version': 1, 'profiles': profiles, 'issues': issues}


def stage_ets2(directory, exe, prefix, runtime, steam):
    uid = secrets.randbelow(1_000_000_000) + 1_000_000_000
    original = exe.parent/'dinput8.dll'
    if original.is_symlink():
        raise ValueError('The existing dinput8 symlink needs inspection; it was preserved.')
    (directory/'g923_bridge.dll').write_bytes(dll_with_mapping(payload('g923_bridge.dll'), uid))
    for source, target in [('winmm.dll','winmm.dll'), ('g923_scs_telemetry.dll','logi_tf_scs.dll'),
                           ('G923TelemetryLab','G923TelemetryLab'), ('mescon-synth','mescon-synth')]:
        shutil.copy2(payload(source), directory/target)
    (directory/'g923-chain.enabled').write_bytes(MARKER)
    registry = prefix/'user.reg'
    before = registry.read_bytes()
    after, previous = registry_value(before.decode('utf-8'),
        r'Software\\Wine\\AppDefaults\\eurotrucks2.exe\\DllOverrides', 'winmm', 'native,builtin')
    if previous not in (None, '"native,builtin"', '"native,builtin"\r'):
        raise ValueError('An existing WinMM override was preserved. Remove the other bridge before installation.')
    targets = {'winmm.dll':'winmm.dll', 'g923_bridge.dll':'g923_bridge.dll',
               'logi_tf_scs.dll':'plugins/logi_tf_scs.dll', 'g923-chain.enabled':'g923-chain.enabled'}
    manifest = dict(mode='mescon_telemetry_emulation', app_id='227300', game_exe=str(exe),
        source_bottle=str(prefix), bottle=prefix.name, bottle_root=str(prefix.parent), runner_path=runtime['path'],
        steam_exe=steam, mapping=f'/tmp/crossover-ffb-{uid}/ffb-v2.bin',
        installed=False, preserved_dlaa_sha=digest(original) if original.is_file() else None,
        installed_files={target:digest(directory/source) for source,target in targets.items()},
        backend_hashes={name:digest(directory/name) for name in ('G923TelemetryLab','mescon-synth')},
        game_settings_changed=False, hardware_accepted=False, device_model='046d:c266',
        native_tf_direction_measured=False, tf_motor_sign=1, motor_sign=-1,
        registry_overrides=[dict(path=str(registry),key=r'Software\\Wine\\AppDefaults\\eurotrucks2.exe\\DllOverrides',
                                 name='winmm',value='native,builtin',previous=previous)],
        tf_motor_sign_source='G923 PlayStation protocol profile, hardware accepted 2026-10-22',
        synth='Original mescon EngineSynth, GPL-2.0-only, separate UDP process')
    files = [(directory/source, exe.parent/target) for source,target in targets.items()]
    return manifest, files, [(registry, before, after.encode('utf-8'))]


def stage_native(directory, exe, prefix, runtime, steam, transport, sdk):
    if not transport or not sdk:
        raise ValueError('Native TRUEFORCE requires the original Logitech SDK and a reviewed patched Wine transport. Existing accepted installations can be imported; stock CrossOver alone is not enough.')
    transport, sdk = Path(transport).resolve(), Path(sdk).resolve()
    tm = json.loads((transport/'manifest.json').read_text())
    hashes = tm.get('prepared_module_hashes') or tm.get('runtime_hashes')
    pair = {'x86_64-unix/winebus.so','x86_64-windows/winebus.sys'}
    if tm.get('purpose') != 'g923-isolated-crossover-hid-transport' or not isinstance(hashes,dict) or set(hashes) != pair:
        raise ValueError('Select a prepared G923 Wine transport.')
    config = discovery._config_values(transport/'runtime/etc/CrossOver.conf')
    if config.get('ProductVersion') != runtime.get('version') or (runtime.get('timestamp') and config.get('BuildTimestamp') != runtime['timestamp']):
        raise ValueError('The prepared transport must use the same CrossOver build as the selected bottle.')
    for relative,value in hashes.items():
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts or digest(transport/'runtime/lib/wine'/path) != value:
            raise ValueError('The prepared transport differs from its manifest.')
    if digest(sdk) != SDK_SHA:
        raise ValueError('The original Logitech TRUEFORCE 1.3.12 x64 SDK is required.')
    builtin = prefix/'drive_c/windows/system32/dinput8.dll'
    sdk_target = prefix/'drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll'
    game_dinput = exe.parent/'dinput8.dll'
    if game_dinput.exists() or game_dinput.is_symlink():
        raise ValueError('Existing game DirectInput files were preserved. Import the existing integration instead.')
    sdk_existing = sdk_target.exists() or sdk_target.is_symlink()
    if sdk_existing and (sdk_target.is_symlink() or not sdk_target.is_file() or digest(sdk_target) != SDK_SHA):
        raise ValueError('The existing bottle SDK differs from the supported original DLL and was preserved.')
    if builtin.is_symlink():
        raise ValueError('The bottle uses a shared system DirectInput symlink; no changes were made.')
    # Materialize the private runtime so moving/removing the source cannot break it.
    shutil.copytree(transport/'runtime', directory/'runtime', symlinks=False)
    uid = secrets.randbelow(1_000_000_000) + 1_000_000_000
    (directory/'sdk-dinput8.dll').write_bytes(dll_with_mapping(payload('sdk-dinput8.dll'),uid))
    shutil.copy2(payload('g923-input'), directory/'g923-input')
    (directory/'private').mkdir()
    shutil.copy2(sdk,directory/'private/trueforce_sdk_x64.dll')
    from main_steam import patch_registry
    registry = prefix/'system.reg';before = registry.read_bytes();after = patch_registry(before.decode('utf-8')).encode('utf-8')
    userreg=prefix/'user.reg';userbefore=userreg.read_bytes()
    key=r'Software\\Wine\\AppDefaults\\dirtrally2.exe\\DllOverrides'
    userafter,previous=registry_value(userbefore.decode('utf-8'),key,'dinput8','native,builtin')
    if previous not in (None,'"native,builtin"','"native,builtin"\r'):
        raise ValueError('An existing game DirectInput override was preserved. Inspect the existing integration first.')
    shutil.copy2(builtin,directory/'system-dinput8-before.dll')
    manifest = dict(purpose='g923-isolated-crossover-hid-transport', main_steam_experiment=True,
        installation_kind='accepted-native-sdk', installed_permanently=True, applied=False,
        game_experiment=True, source_bottle=str(prefix), bottle=prefix.name, bottle_root=str(prefix.parent),
        runner_path=runtime['path'], steam_exe=steam, steam_app_id=690790, game_exe=str(exe),
        game_sha=digest(exe), game_dll_sha=digest(directory/'sdk-dinput8.dll'),
        steam_api_sha=digest(exe.parent/'steam_api64.dll'), sdk_sha=digest(sdk), sdk_target=str(sdk_target),
        sdk_preexisting=sdk_existing, preserved_sdk_sha=digest(sdk_target) if sdk_existing else None,
        private_system_dinput_sha=digest(directory/'runtime/lib/wine/x86_64-windows/dinput8.dll'),
        runtime_hashes=hashes, mapping=f'/tmp/crossover-ffb-{uid}/ffb-v2.bin',
        backend_hashes={'g923-input':digest(directory/'g923-input')},
        registry_overrides=[dict(path=str(userreg),key=key,name='dinput8',value='native,builtin',previous=previous)],
        settings_hashes={}, game_settings_changed=False, hardware_accepted=False)
    files = [(directory/'sdk-dinput8.dll',exe.parent/'dinput8.dll')]
    if not sdk_existing:
        files.append((directory/'private/trueforce_sdk_x64.dll',sdk_target))
    # Only this Wine builtin can be replaced; keep exact bytes for rollback.
    return manifest, files, [(registry,before,after),(userreg,userbefore,userafter.encode('utf-8')),
        (builtin,builtin.read_bytes(),(directory/'runtime/lib/wine/x86_64-windows/dinput8.dll').read_bytes())]


def install(appid, exe, prefix, runner, registry=None, inventory=None, transport=None, sdk=None):
    registry = Path(registry) if registry else default_registry_path()
    exe,prefix,runtime,steam = select_installation(appid,exe,prefix,runner,inventory)
    found = [p for p in load_registry(registry)['profiles'] if Path(p['game_exe']).resolve() == exe and Path(p['source_bottle']).resolve() == prefix]
    if len(found) > 1:
        raise ValueError('Multiple prepared profiles match this installation. Inspect them in Settings.')
    if found:
        from auto_bridge import installation
        if installation(appid,profile=found[0]) != 'installed':
            stopped()
            installation(appid, patch=True, profile=found[0])
        if appid==690790:
            from native_transport import configure
            session=Path(found[0]['session_dir'])
            configure(session,json.loads((session/'manifest.json').read_text()))
        return status(registry,exe,prefix)
    if appid==690790 and (transport is None or sdk is None):
        from native_setup import dependencies
        prepared,original=dependencies(prefix,runner)
        transport=transport or prepared;sdk=sdk or original
    stopped()
    key = identity(appid,exe,prefix);destination = registry.parent/key
    if destination.exists():
        raise ValueError('An unfinished installation was preserved: ' + str(destination))
    registry.parent.mkdir(parents=True,exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.prepare-',dir=registry.parent))
    created,changed = [],[]
    manifest = None;hook_applied=False
    try:
        stage = stage_ets2(temporary,exe,prefix,runtime,steam) if appid == 227300 else stage_native(temporary,exe,prefix,runtime,steam,transport,sdk)
        manifest,files,edits = stage
        if manifest.get('sdk_preexisting'):
            existing_sdk=Path(manifest['sdk_target'])
            if existing_sdk.is_symlink() or not existing_sdk.is_file() or digest(existing_sdk) != manifest['preserved_sdk_sha']:
                raise ValueError('The existing bottle SDK changed during setup and was preserved.')
        for source,target in files:
            if target.exists() or target.is_symlink():
                raise ValueError('Existing file preserved: ' + str(target))
        for path,before,after in edits:
            if path.read_bytes() != before:
                raise ValueError('Installation input changed: ' + str(path))
        write_json(temporary/'manifest.json',manifest)
        write_json(temporary/'transaction.json',{'version':1,'files':[str(t) for _,t in files],
            'edits':[{'path':str(p),'before':hashlib.sha256(b).hexdigest(),'after':hashlib.sha256(a).hexdigest()} for p,b,a in edits], 'completed':False})
        for index,(path,before,after) in enumerate(edits):
            (temporary/f'backup-{index}').write_bytes(before)
        for source,target in files:
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as output:
                created.append((target,None))
                output.write(source.read_bytes())
            created[-1]=(target,digest(source))
        for path,before,after in edits:
            replace_bytes(path,before,after);changed.append((path,before,after))
        manifest.update(installed=True,applied=True,installation_directory=str(destination))
        write_json(temporary/'manifest.json',manifest)
        transaction=json.loads((temporary/'transaction.json').read_text());transaction['completed']=True
        write_json(temporary/'transaction.json',transaction)
        temporary.rename(destination)
        if appid==690790:
            from native_transport import configure
            configure(destination,manifest);hook_applied=True
        record=profile_from_manifest(destination,appid,runner_path=runtime['path'])
        register(record,registry)
        return status(registry,exe,prefix)
    except Exception as error:
        rollback_errors=[]
        if hook_applied:
            try:
                from native_transport import restore
                restore(destination,manifest)
            except Exception as failure:rollback_errors.append(str(failure))
        for path,before,after in reversed(changed):
            try:replace_bytes(path,after,before)
            except Exception as failure:rollback_errors.append(str(failure))
        for path,value in reversed(created):
            try:
                if path.is_file() and (value is None or digest(path) == value):path.unlink()
                elif path.exists():rollback_errors.append('Changed file preserved: '+str(path))
            except Exception as failure:rollback_errors.append(str(failure))
        if destination.exists() or rollback_errors:
            saved=destination if destination.exists() else temporary
            if manifest:
                manifest.update(installed=False,applied=False)
                write_json(saved/'manifest.json',manifest)
            write_json(saved/'failure.json',{'error':str(error),'rollback_errors':rollback_errors})
            if rollback_errors:
                raise RuntimeError('Installation needs recovery; journal: '+str(saved)) from error
        raise
    finally:
        if temporary.exists() and not (temporary/'failure.json').exists():shutil.rmtree(temporary)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['discover','status','install','migrate','native-status','sdk-import','transport-install'])
    p.add_argument('--json',action='store_true');p.add_argument('--registry',type=Path)
    p.add_argument('--appid',type=int);p.add_argument('--exe',type=Path);p.add_argument('--prefix',type=Path)
    p.add_argument('--runner',type=Path);p.add_argument('--transport',type=Path);p.add_argument('--sdk-dll',type=Path)
    p.add_argument('--legacy-root',type=Path,default=ROOT)
    p.add_argument('--application',type=Path,action='append');p.add_argument('--bottle-root',type=Path,action='append')
    p.add_argument('--steam-root',type=Path,action='append');a=p.parse_args(argv)
    try:
        if a.action=='discover':result=discovery.discover(applications=a.application,bottle_roots=a.bottle_root,steam_roots=a.steam_root)
        elif a.action=='status':result=status(a.registry,a.exe,a.prefix)
        elif a.action=='native-status':
            from native_setup import status as native_status
            result=native_status(a.exe,a.prefix,a.runner,a.registry)
        elif a.action=='sdk-import':
            from sdk_setup import import_sdk
            if a.sdk_dll is None:p.error('Choose an original SDK DLL')
            result=import_sdk(a.sdk_dll)
        elif a.action=='transport-install':
            from transport_setup import install as install_transport
            if a.runner is None:p.error('Choose the CrossOver application used for this bottle')
            result=install_transport(a.runner)
        elif a.action=='migrate':
            result=migrate_legacy(a.legacy_root,a.registry)
        else:
            if any(x is None for x in (a.appid,a.exe,a.prefix,a.runner)):p.error('Install requires appid, exe, prefix and runner')
            result=install(a.appid,a.exe,a.prefix,a.runner,a.registry,transport=a.transport,sdk=a.sdk_dll)
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps({'error':str(error)}))
        return 1


if __name__=='__main__':raise SystemExit(main())
