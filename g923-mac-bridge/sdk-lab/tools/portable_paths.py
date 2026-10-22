# SPDX-License-Identifier: GPL-3.0-only
"""Resolve installed assets and selected runtimes without machine-specific paths."""
import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with Path(path).open('rb') as stream:
        result = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
        return result.hexdigest()


def payload(name, session=None, root=None):
    """Prefer recorded session bytes; verify bundled payload hashes before use."""
    if Path(name).name != name:
        raise ValueError('Invalid component name')
    if session:
        candidate = Path(session) / name
        if candidate.is_file():
            return candidate
    root = Path(root) if root else ROOT
    directories = [root / 'payloads', root / 'Resources/payloads']
    override = os.environ.get('G923_PAYLOADS')
    if override:
        directories.insert(0, Path(override))
    for directory in directories:
        index = directory / 'manifest.json'
        if not index.is_file():
            continue
        data = json.loads(index.read_text())
        entry = data.get('files', {}).get(name)
        if not entry:
            continue
        relative = Path(entry.get('path', name))
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid bundled component path')
        candidate = directory / relative
        if not candidate.is_file() or digest(candidate) != entry['sha256']:
            raise ValueError('Bundled component differs: ' + name)
        return candidate
    # Developer builds may use their own local output, never a different checkout.
    developer = {
        'g923-input': 'build/g923-input',
        'g923_bridge.dll': 'build/ets2-force-unknown/g923_bridge.dll',
        'winmm.dll': 'build/winmm-chain/winmm.dll',
        'dinput8.dll': 'build/crossover-base/dinput8.dll',
        'G923ClassicLab': 'build/ets2-swift/debug/G923ClassicLab',
    }.get(name)
    if developer and (root / developer).is_file():
        return root / developer
    raise FileNotFoundError('Missing component: ' + name + '. Install a complete application build.')


def runtime_directory(session, manifest):
    if manifest.get('runtime_dir'):
        runtime=Path(manifest['runtime_dir']).expanduser()
        if not (runtime/'bin/wine').is_file():
            raise FileNotFoundError('The selected Wine runtime is unavailable.')
        return runtime
    local = Path(session) / 'runtime'
    if local.is_dir():
        if not (local/'bin/wine').is_file():
            raise FileNotFoundError('The prepared Wine runtime is incomplete.')
        return local
    runner = manifest.get('runner_path')
    if runner:
        selected = Path(runner)
        runtime = selected.parent.parent if selected.is_file() and selected.parent.name == 'bin' else selected / 'Contents/SharedSupport/CrossOver'
        if (runtime/'bin/wine').is_file():
            return runtime
    raise FileNotFoundError('The selected CrossOver runtime is unavailable. Select its current location.')


def wine_command(session, manifest):
    bottle = Path(manifest['source_bottle']) if manifest.get('source_bottle') else None
    name = bottle.name if bottle else manifest.get('bottle')
    if not name:
        raise ValueError('No bottle selected')
    return [str(runtime_directory(session, manifest) / 'bin/wine'), '--bottle', name]


def bottle_environment(manifest):
    env = os.environ.copy()
    bottle = manifest.get('source_bottle')
    if bottle:
        prefix = Path(bottle).expanduser().resolve()
        env['CX_BOTTLE_PATH'] = str(prefix.parent)
        env['WINEPREFIX'] = str(prefix)
    elif manifest.get('bottle_root'):
        env['CX_BOTTLE_PATH'] = manifest['bottle_root']
    return env


def steam_executable(manifest):
    explicit = manifest.get('steam_exe')
    if explicit and Path(explicit).is_file():
        return Path(explicit)
    bottle = manifest.get('source_bottle')
    if bottle:
        from discovery import discover
        inventory = discover(bottle_roots=[Path(bottle).parent], app_roots=[], applications=[], spotlight=False)
        for item in inventory['bottles']:
            if Path(item['path']).resolve() == Path(bottle).resolve():
                from discovery import case_path
                found = [p for root in item.get('steam_roots', []) if (p:=case_path(Path(root)/'Steam.exe')) is not None and p.is_file()]
                if len(found) == 1:
                    return found[0]
                if len(found) > 1:
                    raise ValueError('Multiple Steam installations found in the selected bottle. Select one during setup.')
    raise FileNotFoundError('Steam was not found in the selected bottle. Refresh the installation locations.')
