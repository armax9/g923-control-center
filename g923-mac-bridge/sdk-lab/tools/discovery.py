#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only CrossOver, bottle and Steam discovery. Never launches Wine or games.

Paths are physical, absolute paths. An app install is identified by its bundle
metadata and Wine runtime, not its file name. A game belongs to a bottle, so
shared libraries in two bottles remain separate choices. Ambiguous runner
matches are returned as candidates and are never resolved by list ordering.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
from urllib.parse import unquote, urlparse
from xml.parsers.expat import ExpatError

MAX_TEXT = 16 * 1024 * 1024
KNOWN_EXECUTABLES = {
    690790: ['dirtrally2.exe'],
    227300: ['bin/win_x64/eurotrucks2.exe'],
    270880: ['bin/win_x64/amtrucks.exe'],
    244210: ['acs.exe'],
    805550: ['AC2/Binaries/Win64/AC2-Win64-Shipping.exe'],
    3058630: ['AssettoCorsaEVO.exe'],
    1066890: ['AMS2AVX.exe', 'AMS2.exe'],
    266410: ['iRacingSim64DX11.exe'],
    378860: ['pCARS2AVX.exe', 'pCARS2.exe'],
    1849250: ['WRC/Binaries/Win64/WRC.exe'],
    1692250: ['F1_22.exe'], 2108330: ['F1_23.exe'],
    2488620: ['F1_24.exe'], 3059520: ['F1_25.exe'],
    365960: ['Bin64/rFactor2.exe'], 2399420: ['Le Mans Ultimate.exe'],
    211500: ['Game/x64/RRRE64.exe'], 284160: ['Bin64/BeamNG.drive.x64.exe'],
}


def identity(kind, path):
    return kind + '-' + hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()[:20]


def _text(path):
    if path.stat().st_size > MAX_TEXT:
        raise ValueError('File is too large: ' + str(path))
    return path.read_text(encoding='utf-8-sig', errors='replace')


def _unique(paths):
    seen = set()
    for path in paths:
        path = Path(path).resolve()
        if str(path) not in seen:
            seen.add(str(path))
            yield path


def _unescape(value):
    # Wine/Valve use C-like quote/backslash escapes. Do not turn a literal
    # Windows \t or \n in an otherwise unescaped path into a control character.
    return re.sub(r'\\([\\"])', r'\1', value)


def parse_vdf(text):
    """Valve KeyValues, quoted/unquoted strings, // comments and nested blocks."""
    pattern = re.compile(r'\s+|//[^\n]*|"(?:\\.|[^"\\])*"|[{}]|[^\s{}"]+')
    tokens, position = [], 0
    for match in pattern.finditer(text):
        if match.start() != position:
            raise ValueError('Invalid VDF token')
        position = match.end()
        token = match.group()
        if token.isspace() or token.startswith('//'):
            continue
        tokens.append(token)
    if position != len(text):
        raise ValueError('Invalid VDF string')

    def string(token):
        if token in ('{', '}'):
            raise ValueError('Expected VDF key or value')
        return _unescape(token[1:-1]) if token.startswith('"') else token

    def block(index, nested=False, depth=0):
        if depth > 32:
            raise ValueError('VDF nesting is too deep')
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
                result[key], index = block(index + 1, True, depth + 1)
            else:
                result[key] = string(tokens[index]); index += 1
        if nested:
            raise ValueError('Unclosed VDF block')
        return result, index
    return block(0)[0]


def _get(mapping, key, default=None):
    return next((v for k, v in mapping.items() if k.casefold() == key.casefold()), default)


def case_path(path):
    """Resolve Windows case differences on case-sensitive host filesystems.

    Two entries differing only in case are ambiguous and are not guessed.
    """
    path = Path(path)
    parts = path.parts
    current = Path(parts[0])
    for part in parts[1:]:
        exact = current / part
        try:
            entries = list(current.iterdir())
            direct = next((p for p in entries if p.name == part), None)
            if direct is not None:
                current = direct
                continue
            matches = [p for p in entries if p.name.casefold() == part.casefold()]
        except OSError:
            return None
        if len(matches) > 1:
            raise ValueError('Ambiguous case in path: ' + str(exact))
        if not matches:
            return None
        current = matches[0]
    return current.resolve() if current.exists() else None


def windows_path(value, bottle):
    """Translate DOS drive links, C:, Z:, POSIX and file:// paths without Wine."""
    if not isinstance(value, str) or '\0' in value:
        return None
    value = value.strip().strip('"')
    if value.startswith('file://'):
        parsed = urlparse(value)
        if parsed.netloc not in ('', 'localhost'):
            return None
        return case_path(Path(unquote(parsed.path)))
    if value.startswith('/'):
        return case_path(Path(value))
    match = re.match(r'^([A-Za-z]):[\\/](.*)$', value)
    if not match or bottle is None:
        return None
    drive, tail = match.groups(); drive = drive.lower()
    bottle = Path(bottle)
    mapping = case_path(bottle / 'dosdevices' / (drive + ':'))
    if mapping is None:
        mapping = case_path(bottle / 'drive_c') if drive == 'c' else (Path('/') if drive == 'z' else None)
    if mapping is None:
        return None
    return case_path(mapping.joinpath(*[p for p in re.split(r'[\\/]+', tail) if p]))


def _config_values(path):
    """Quoted CrossOver INI assignments (comments cannot supply settings)."""
    if not path.is_file():
        return {}
    out = {}
    for line in _text(path).splitlines():
        match = re.match(r'^\s*"?([^"=;#]+?)"?\s*=\s*"((?:\\.|[^"\\])*)"\s*(?:[;#].*)?$', line)
        if match:
            out[match[1].strip()] = _unescape(match[2])
    return out


def _path_list(value, home, environ):
    if isinstance(value, list):
        return [p for v in value for p in _path_list(v, home, environ)]
    if not isinstance(value, str):
        return []
    def variable(match):
        return str(home) if match[1] == 'HOME' else environ.get(match[1], match[0])
    value = re.sub(r'\$\{([A-Za-z_][A-Za-z_0-9]*)\}', variable, value)
    out = []
    for item in value.split(':'):
        item = item.strip()
        if item == '~' or item.startswith('~/'):
            item = str(home) + item[1:]
        if item.startswith('/') and '${' not in item:
            out.append(Path(item))
    return out


def _preference_roots(home, bundle_id, environ):
    roots = []
    for name in dict.fromkeys([bundle_id, 'com.codeweavers.CrossOver', 'com.codeweavers.CrossOverPreview']):
        path = home / 'Library/Preferences' / (name + '.plist')
        if not path.is_file():
            continue
        try:
            data = plistlib.loads(path.read_bytes())
        except (OSError, ValueError, plistlib.InvalidFileException, ExpatError):
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            # UI expansion/sort keys are not filesystem paths.
            if re.search(r'bottle.*(?:path|root|location|directory)|(?:path|root).*bottle', key, re.I):
                roots.extend(_path_list(value, home, environ))
    return roots


def _app_candidates(roots, applications, spotlight):
    out = list(map(Path, applications))
    # Two levels cover /Applications/Utilities or a user's application folder.
    # Never follow arbitrary directory symlinks recursively or scan whole disks.
    for root in roots:
        root = Path(root)
        if root.suffix.lower() == '.app':
            out.append(root); continue
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            if child.suffix.lower() == '.app':
                out.append(child)
            elif child.is_dir() and not child.is_symlink():
                try:
                    out.extend(p for p in child.iterdir() if p.suffix.lower() == '.app')
                except OSError:
                    pass
    if spotlight:
        try:
            result = subprocess.run(['/usr/bin/mdfind', 'kMDItemCFBundleIdentifier == "com.codeweavers.CrossOver*"'],
                                    capture_output=True, text=True, timeout=8, check=False)
            if result.returncode == 0:
                out.extend(Path(p) for p in result.stdout.splitlines() if p.endswith('.app'))
        except (OSError, subprocess.TimeoutExpired):
            pass
    return list(_unique(out))


def _runner(app, home, environ):
    info_path = app / 'Contents/Info.plist'
    if not info_path.is_file():
        return None
    info = plistlib.loads(info_path.read_bytes())
    if not isinstance(info, dict):
        return None
    bundle_id = str(info.get('CFBundleIdentifier', ''))
    name = str(info.get('CFBundleName', ''))
    if not bundle_id.casefold().startswith('com.codeweavers.crossover'):
        return None
    runtime = app / 'Contents/SharedSupport/CrossOver'
    wine = runtime / 'bin/wine'
    if not wine.is_file() or not os.access(wine, os.X_OK):
        return None
    config = _config_values(runtime / 'etc/CrossOver.conf')
    user_config = _config_values(home / 'Library/Application Support/CrossOver/CrossOver.conf')
    preview = 'preview' in (name + ' ' + bundle_id + ' ' + config.get('BuildTag', '')).lower()
    channel = 'preview' if preview else 'stable'
    roots = [home / 'Library/Application Support/CrossOver/Bottles',
             home / 'Library/Application Support/CrossOver Preview/Bottles',
             Path('/Library/Application Support/CrossOver/Bottles')]
    configured = environ.get('CX_BOTTLE_PATH') or user_config.get('BottlePath') or config.get('BottlePath')
    roots.extend(_path_list(configured, home, environ))
    roots.extend(_preference_roots(home, bundle_id, environ))
    return dict(id=identity('runner', app), name=name or 'CrossOver', path=str(app), wine=str(wine.resolve()),
                channel=channel, bundle_id=bundle_id,
                version=config.get('ProductVersion', str(info.get('CFBundleShortVersionString', ''))),
                timestamp=config.get('BuildTimestamp', ''), bottle_roots=list(map(str, _unique(roots))))


def _bottles_in(root):
    """Inspect an explicit bottle or up to three nested collection levels."""
    out, seen = [], set()
    def visit(path, depth):
        path = path.resolve()
        if str(path) in seen:
            return
        seen.add(str(path))
        if (path / 'cxbottle.conf').is_file() and (path / 'drive_c').is_dir() and (path / 'user.reg').is_file():
            out.append(path); return
        if depth == 0:
            return
        try:
            children = list(path.iterdir())
        except OSError:
            return
        for child in children:
            if child.is_dir() and not child.name.startswith('.'):
                # Following explicitly enumerated collection aliases is bounded
                # by both depth and a physical-path visited set.
                visit(child, depth - 1)
    visit(Path(root), 3)
    return out


def _runner_matches(config, candidates):
    version, stamp = config.get('Version', ''), config.get('Timestamp', '')
    exact = [r for r in candidates if version and r['version'] == version and
             (not stamp or not r['timestamp'] or r['timestamp'] == stamp)]
    if exact:
        return [r['id'] for r in exact], 'exact' if len(exact) == 1 else 'ambiguous'
    same_version = [r for r in candidates if version and r['version'] == version]
    if same_version:
        return [r['id'] for r in same_version], 'same-version' if len(same_version) == 1 else 'ambiguous'
    if not version:
        return [r['id'] for r in candidates], 'unversioned' if len(candidates) == 1 else ('ambiguous' if candidates else 'unavailable')
    # A newer/older Wine version may upgrade the prefix. Discovery cannot grant
    # permission for that migration or silently choose a channel.
    return [], 'version-mismatch' if candidates else 'unavailable'


def _steam_registry_paths(bottle):
    out = []
    for filename in ('user.reg', 'system.reg'):
        path = bottle / filename
        if not path.is_file():
            continue
        section = ''
        for line in _text(path).splitlines():
            if line.startswith('['):
                section = _unescape(line[1:].split(']', 1)[0]).casefold()
            if 'valve\\steam' not in section and not section.endswith('uninstall\\steam'):
                continue
            match = re.match(r'^"(SteamPath|InstallPath|InstallLocation|SteamExe)"="((?:\\.|[^"\\])*)"', line, re.I)
            if match:
                value = _unescape(match[2])
                if match[1].casefold() == 'steamexe':
                    value = re.sub(r'[\\/][^\\/]+$', '', value)
                out.append(value)
    return out


def _steam_roots(bottle):
    paths = _steam_registry_paths(bottle)
    paths.extend([r'C:\Program Files (x86)\Steam', r'C:\Program Files\Steam', r'C:\Steam'])
    return list(_unique(p for value in paths if (p := windows_path(value, bottle)) is not None and (case_path(p / 'steamapps') is not None)))


def steam_libraries(root, bottle=None, issue=None):
    """Return main library plus every old/new libraryfolders entry."""
    out = [Path(root)]
    for relative in ('steamapps/libraryfolders.vdf', 'config/libraryfolders.vdf'):
        file = case_path(Path(root) / relative)
        if file is None:
            continue
        try:
            data = parse_vdf(_text(file))
            folders = _get(data, 'libraryfolders', {})
            if not isinstance(folders, dict):
                raise ValueError('Invalid Steam libraryfolders object')
            for key, entry in folders.items():
                if not key.isdecimal():
                    continue
                value = _get(entry, 'path') if isinstance(entry, dict) else entry
                path = windows_path(value, bottle)
                if path is not None:
                    out.append(path)
        except (OSError, ValueError) as error:
            if issue is None:
                raise
            issue('steam', file, error)
    return list(_unique(p for p in out if case_path(p / 'steamapps') is not None))


def _manifest_record(manifest, match, library, root, bottle):
    data = _get(parse_vdf(_text(manifest)), 'AppState', {})
    appid = _get(data, 'appid', match[1]) if isinstance(data, dict) else None
    folder = _get(data, 'installdir') if isinstance(data, dict) else None
    if not isinstance(appid, str) or not appid.isdecimal() or str(int(appid)) != str(int(match[1])):
        raise ValueError('Steam app ID does not match manifest: ' + str(manifest))
    if not isinstance(folder, str) or folder in ('', '.', '..') or '/' in folder or '\\' in folder:
        raise ValueError('Unsafe Steam install directory: ' + str(manifest))
    game = case_path(manifest.parent / 'common' / folder)
    if game is None or not game.is_dir():
        return None
    appid = int(appid)
    executable = next((p for relative in KNOWN_EXECUTABLES.get(appid, []) if (p := case_path(game / relative)) is not None and p.is_file()), None)
    if executable is None and appid not in KNOWN_EXECUTABLES:
        # A single top-level executable is unambiguous. Never infer a launcher
        # by recursively looking through every installed file.
        choices = [p for p in game.iterdir() if p.suffix.casefold() == '.exe' and p.is_file()]
        if len(choices) == 1:
            executable = choices[0].resolve()
    record_id = identity('game', str(game) + '/' + (bottle['id'] if bottle else 'native'))
    display_name = _get(data, 'name', folder)
    if not isinstance(display_name, str):
        display_name = folder
    return dict(id=record_id, appid=appid, name=display_name,
                exe=str(executable) if executable else None, install_path=str(game),
                bottle_id=bottle['id'] if bottle else None,
                runner_ids=bottle['runner_ids'] if bottle else [], steam_root=str(root),
                library=str(library), source='crossover' if bottle else 'native-steam',
                known=appid in KNOWN_EXECUTABLES)


def _game_records(root, bottle, issue=None):
    out = []
    bottle_path = Path(bottle['path']) if bottle else None
    for library in steam_libraries(root, bottle_path, issue):
        steamapps = case_path(library / 'steamapps')
        for manifest in sorted(steamapps.iterdir()):
            match = re.fullmatch(r'appmanifest_(\d+)\.acf', manifest.name, re.I)
            if not match or not manifest.is_file():
                continue
            try:
                record = _manifest_record(manifest, match, library, root, bottle)
                if record is not None:
                    out.append(record)
            except (OSError, ValueError) as error:
                if issue is None:
                    raise
                issue('steam', manifest, error)
    return out


def discover(*, home=None, app_roots=None, applications=None, bottle_roots=None,
             steam_roots=None, spotlight=True, environ=None):
    """Build a JSON-serializable inventory without mutating any discovered path.

    Bottle/Steam roots supplement defaults; app_roots overrides application
    search directories. Tests use app_roots=[] and spotlight=False with an
    isolated home to avoid inspecting installed applications.
    """
    home = Path(home if home is not None else Path.home()).resolve()
    environ = dict(os.environ if environ is None else environ)
    roots = [Path('/Applications'), home / 'Applications'] if app_roots is None else list(map(Path, app_roots))
    inventory = dict(version=1, runners=[], bottles=[], games=[], issues=[])
    def issue(scope, path, error):
        inventory['issues'].append(dict(scope=scope, path=str(path), message=str(error)))
    for app in _app_candidates(roots, applications or [], spotlight):
        try:
            runner = _runner(app, home, environ)
            if runner:
                inventory['runners'].append(runner)
        except (OSError, ValueError, plistlib.InvalidFileException, ExpatError) as error:
            issue('runner', app, error)
    all_roots = list(map(Path, bottle_roots or []))
    all_roots += _path_list(environ.get('CX_BOTTLE_PATH'), home, environ)
    all_roots += [home / 'Library/Application Support/CrossOver/Bottles', home / 'Library/Application Support/CrossOver Preview/Bottles']
    for runner in inventory['runners']:
        all_roots.extend(map(Path, runner['bottle_roots']))
    seen_bottles = set()
    for root in _unique(all_roots):
        for path in _bottles_in(root):
            if str(path) in seen_bottles:
                continue
            seen_bottles.add(str(path))
            try:
                config = _config_values(path / 'cxbottle.conf')
                ids, match = _runner_matches(config, inventory['runners'])
                bottle = dict(id=identity('bottle', path), name=path.name, path=str(path),
                              runner_ids=ids, runner_match=match, version=config.get('Version', ''),
                              timestamp=config.get('Timestamp', ''), steam_roots=list(map(str, _steam_roots(path))))
                inventory['bottles'].append(bottle)
                if match in ('ambiguous', 'version-mismatch'):
                    issue('bottle', path, 'Runner selection requires review: ' + match)
            except (OSError, ValueError) as error:
                issue('bottle', path, error)
    sources = [(Path(root), bottle) for bottle in inventory['bottles'] for root in bottle['steam_roots']]
    native_roots = [home / 'Library/Application Support/Steam', home / '.steam/steam']
    native_roots.extend(map(Path, steam_roots or []))
    sources.extend((root, None) for root in _unique(native_roots) if case_path(root / 'steamapps') is not None)
    for root, bottle in sources:
        try:
            inventory['games'].extend(_game_records(root, bottle, issue))
        except (OSError, ValueError) as error:
            issue('steam', root, error)
    # A manifest may appear in both the main folder and a repeated VDF entry.
    inventory['games'] = list({(g['bottle_id'], g['appid'], g['install_path']): g for g in inventory['games']}.values())
    inventory['runners'].sort(key=lambda r: (r['channel'], r['path']))
    inventory['bottles'].sort(key=lambda b: (b['name'].casefold(), b['path']))
    inventory['games'].sort(key=lambda g: (g['name'].casefold(), g['bottle_id'] or '', g['install_path']))
    return inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Emit JSON (the default).')
    parser.add_argument('--home', type=Path)
    parser.add_argument('--app-root', type=Path, action='append')
    parser.add_argument('--application', type=Path, action='append')
    parser.add_argument('--bottle-root', type=Path, action='append')
    parser.add_argument('--steam-root', type=Path, action='append')
    parser.add_argument('--no-spotlight', action='store_true')
    args = parser.parse_args()
    print(json.dumps(discover(home=args.home, app_roots=args.app_root,
                             applications=args.application, bottle_roots=args.bottle_root,
                             steam_roots=args.steam_root, spotlight=not args.no_spotlight), indent=2) + '\n', end='')


if __name__ == '__main__':
    main()
