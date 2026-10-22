#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build the ETS2 DirectInput DLL from source; never install or run hardware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def executable(value, default):
    selected = str(value or default)
    located = shutil.which(selected)
    if not located:
        raise ValueError('Build tool not found: ' + selected)
    return str(Path(located).absolute())


def build(output, zig, *, unknown_force_metadata=False, uid=0, tests=True):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    defines = ['-DG923_NOMINAL_HAND_FORCE_NEWTONS=0', '-DEXPECTED_HAND_FORCE_NEWTONS=0'] if unknown_force_metadata else []
    environment = os.environ.copy()
    environment.setdefault('ZIG_GLOBAL_CACHE_DIR', str(output / 'zig-cache'))
    environment.setdefault('ZIG_LOCAL_CACHE_DIR', str(output / 'zig-local'))
    if tests:
        clang = subprocess.check_output(['xcrun', '--find', 'clang'], text=True).strip()
        sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
        for source, name in [('test_bridge.c', 'test-bridge'), ('export_force_contract.c', 'export-force-contract')]:
            command = [clang, '-isysroot', sdk, '-std=c11', '-g', '-Wno-unused-function', '-fsanitize=address,undefined',
                       *defines, str(ROOT / 'vendor/crossover-ffb/bridge/tests' / source), '-o', str(output / name)]
            subprocess.run(command, env=environment, check=True)
        subprocess.run([str(output / 'test-bridge')], check=True)
        frames = subprocess.check_output([str(output / 'export-force-contract')])
        if frames != (ROOT / 'vendor/crossover-ffb/bridge/tests/force_contract_frames.jsonl').read_bytes():
            raise ValueError('C/Swift force contract fixture drift; inspect actual records before updating the fixture')
    subprocess.run([zig, 'dlltool', '-m', 'i386:x86-64', '-d', str(ROOT / 'vendor/crossover-ffb/bridge/kernel32.def'),
                    '-l', str(output / 'kernel32.lib')], env=environment, check=True)
    subprocess.run([zig, 'cc', '-target', 'x86_64-windows-msvc', '-std=c11', '-O2', '-ffreestanding',
                    '-fno-builtin', '-fno-stack-protector', *defines, '-c',
                    str(ROOT / 'vendor/crossover-ffb/bridge/observe.c'), '-o', str(output / 'observe.obj')],
                   env=environment, check=True)
    payload = output / 'g923_bridge.dll'
    subprocess.run([zig, 'cc', '-target', 'x86_64-windows-msvc', '-nostdlib', '-shared', str(output / 'observe.obj'),
                    str(output / 'kernel32.lib'), str(ROOT / 'vendor/crossover-ffb/bridge/exports.def'),
                    '-Wl,--entry,DllMain', '-o', str(payload)], env=environment, check=True)
    data = bytearray(payload.read_bytes())
    marker = b'CFBUID=0\0'
    if data.count(marker) != 1:
        raise ValueError('Unexpected bridge identity marker')
    position = data.index(marker)
    data[position:position + 24] = ('CFBUID=' + str(uid)).encode().ljust(24, b'\0')
    payload.write_bytes(data)
    (output / 'candidate.json').write_text(json.dumps({
        'sha256': hashlib.sha256(data).hexdigest(), 'max_force_newtons': 0 if unknown_force_metadata else 20,
        'force_metadata_measured': False, 'installed': False, 'input_guid_unchanged': True,
        'physical_acceptance': False}, indent=2) + '\n')
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unknown-force-metadata', action='store_true', help='Advertise unknown maximum force (0 N), the accepted ETS2 contract.')
    parser.add_argument('--output', type=Path, help='Build directory; no installed files are modified.')
    parser.add_argument('--zig', default=os.environ.get('ZIG'), help='Zig executable; defaults to ZIG or zig on PATH.')
    parser.add_argument('--uid', type=int, default=0, help='Mapping UID; installers fill in the destination user UID.')
    parser.add_argument('--skip-tests', action='store_true', help='Build only; use after running the offline force contract tests separately.')
    args = parser.parse_args()
    if not 0 <= args.uid <= 0xffffffff:
        parser.error('--uid must fit an unsigned 32-bit integer')
    output = args.output or ROOT / ('build/ets2-force-unknown' if args.unknown_force_metadata else 'build/ets2-force-units')
    print(build(output, executable(args.zig, 'zig'), unknown_force_metadata=args.unknown_force_metadata,
                uid=args.uid, tests=not args.skip_tests))


if __name__ == '__main__':
    main()
