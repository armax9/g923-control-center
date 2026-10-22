#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare a private CrossOver transport experiment. Never modifies source runtime/bottle.

The Wine module pair must come from the same patched Wine build. Successful PE
import checks are a preflight, not a claim of ABI or gaming compatibility.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from pe_inventory import inspect

ROOT = Path(__file__).resolve().parents[2]
PURPOSE = 'g923-isolated-crossover-hid-transport'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight(runtime, bottle, build, owner):
    expected = {'purpose': 'g923-sdk-lab', 'project': str(ROOT)}
    if json.loads(owner.read_text()) != expected:
        raise ValueError('Source must be a project-owned SDK lab')
    if bottle.parent.resolve() != (owner.parent / 'bottles').resolve():
        raise ValueError('Source bottle is outside the owned lab')
    if bottle.name != 'G923SDKLab' or not (bottle / 'cxbottle.conf').is_file():
        raise ValueError('Expected the SDK lab bottle, never Steam')
    if not (runtime / 'bin/wine').is_file():
        raise ValueError('Invalid runtime')
    pe = build / 'dlls/winebus.sys/x86_64-windows/winebus.sys'
    unix = build / 'dlls/winebus.sys/winebus.so'
    report = inspect(pe)
    if not report['x64'] or not unix.is_file():
        raise ValueError('Need a complete x64 Wine module pair')
    imports = {}
    for library in report['imports']:
        target = runtime / 'lib/wine/x86_64-windows' / library['dll'].lower()
        exports = {entry['name'] for entry in inspect(target)['exports']}
        missing = [name for name in library['symbols'] if name not in exports]
        if missing:
            raise ValueError(f'Missing imports from {library["dll"]}: {missing}')
        imports[library['dll']] = len(library['symbols'])
    return pe, unix, imports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--source-bottle', type=Path, required=True)
    parser.add_argument('--owner', type=Path, required=True)
    parser.add_argument('--wine-build', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true', help='Default is a no-copy plan')
    args = parser.parse_args()
    runtime, bottle, build = (p.resolve() for p in
                              [args.runtime, args.source_bottle, args.wine_build])
    pe, unix, imports = preflight(runtime, bottle, build, args.owner.resolve())
    output = args.output_dir.resolve()
    if output.exists():
        parser.error('Output must not exist')
    if any(output == src or src in output.parents or output in src.parents
           for src in [runtime, bottle, build]):
        parser.error('Output must be separate from source trees')
    modules = {'x86_64-unix/winebus.so': unix, 'x86_64-windows/winebus.sys': pe}
    original = {name: sha(runtime / 'lib/wine' / name) for name in modules}
    manifest = dict(purpose=PURPOSE, source_runtime=str(runtime), source_bottle=str(bottle),
                    wine_build=str(build), original_hashes=original,
                    source_module_hashes={name: sha(path) for name, path in modules.items()},
                    pe_import_counts=imports, prepared=args.prepare, game_launched=False,
                    steam_bottle_modified=False, installed_runtime_modified=False,
                    compatibility_note='Preflight only; inventory and SDK tests required')
    if args.prepare:
        output.mkdir(parents=True)
        # clonefile copies on APFS: independent files, never hard links to originals.
        subprocess.run(['cp', '-cR', str(runtime), str(output / 'runtime')], check=True)
        subprocess.run(['cp', '-cR', str(bottle), str(output / 'G923TFTransport')], check=True)
        for name, source in modules.items():
            shutil.copy2(source, output / 'runtime/lib/wine' / name)
        subprocess.run(['codesign', '--force', '--sign', '-',
                        str(output / 'runtime/lib/wine/x86_64-unix/winebus.so')], check=True)
        manifest['prepared_module_hashes'] = {
            name: sha(output / 'runtime/lib/wine' / name) for name in modules}
        (output / 'G923TFTransport/g923-owned-prefix.json').write_text(
            json.dumps({'purpose': PURPOSE}, indent=2) + '\n')
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        if any(sha(runtime / 'lib/wine' / name) != value for name, value in original.items()):
            raise RuntimeError('Source runtime changed during experiment preparation')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
