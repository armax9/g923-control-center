#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only bottle registry and virtual DInput path probe; no native backend."""
import argparse
import mmap
import json
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wine', type=Path, required=True)
    parser.add_argument('--bottle', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--bottle-root', type=Path)
    parser.add_argument('--main-session', type=Path, help='Applied reversible Steam experiment; open-only probes')
    parser.add_argument('--sdk-open-only', '--sdk-dll', type=Path, help='Initialize pinned SDK and open session, no force mode or samples; owned transport bottle only')
    parser.add_argument('--sdk-mode',choices=['open','combined','kf-only','kf-live'],default='open')
    parser.add_argument('--user-ready',action='store_true')
    parser.add_argument('--stop-file',type=Path)
    parser.add_argument('--arm-file',type=Path)
    parser.add_argument('--force-file',type=Path)
    args = parser.parse_args()
    if args.sdk_mode=='kf-live' and (not args.force_file or not args.force_file.is_file() or not args.user_ready or args.arm_file):parser.error('Live KF requires fresh force-file and explicit readiness')
    if args.sdk_mode in ['combined','kf-only','kf-live']:
        if not args.sdk_open_only or not args.stop_file or args.stop_file.exists():
            parser.error('Combined mode requires pinned SDK and fresh stop-file')
        if args.arm_file:
            if args.arm_file.exists():parser.error('Arm-file must not exist')
        elif not args.user_ready:parser.error('Immediate combined pulse requires explicit user readiness')
    sdk_windows = None
    if args.sdk_open_only:
        if not args.bottle_root or Path(args.bottle).name != args.bottle:
            parser.error('SDK session requires a private bottle root and simple bottle name')
        prefix=(args.bottle_root/args.bottle).resolve()
        if args.main_session:
            from sdk_game import load, check
            main_manifest=load(args.main_session.resolve())
            if args.sdk_mode!='open' or not main_manifest.get('main_steam_experiment') or prefix!=Path(main_manifest['source_bottle']).resolve():
                parser.error('Main Steam diagnostic permits only open-only in the installed experiment')
            check(args.main_session.resolve(),main_manifest)
        else:
            marker=json.loads((prefix/'g923-owned-prefix.json').read_text())
            if marker.get('purpose')!='g923-isolated-crossover-hid-transport':
                parser.error('Not an owned transport bottle')
        sdk=args.sdk_open_only.resolve()
        if hashlib.sha256(sdk.read_bytes()).hexdigest()!='2468bdafe64c09ff42ef26f09e49f2096321bb687467323aafb3f0672fb83315':
            parser.error('Unreviewed SDK bytes')
        sdk_windows='C:'+chr(92)+str(sdk.relative_to(prefix/'drive_c')).replace('/',chr(92))
    output = args.output_dir.resolve()
    output.mkdir(exist_ok=False, parents=True)
    uid = secrets.randbelow(1000000000) + 1000000000
    directory = Path('/tmp') / f'crossover-ffb-{uid}'
    directory.mkdir(mode=0o700)
    mapping = directory / 'ffb-v2.bin'
    child = None
    try:
        raw = bytearray((ROOT / 'build/crossover-base/dinput8.dll').read_bytes())
        marker = b'CFBUID=0\0'
        if raw.count(marker) != 1:
            raise RuntimeError('Unexpected project DLL marker')
        index = raw.index(marker)
        raw[index:index + 24] = ('CFBUID=' + str(uid)).encode().ljust(24, b'\0')
        (output / 'dinput8.dll').write_bytes(raw)
        executable='sdk-session.exe' if sdk_windows else 'sdk-route-probe.exe'
        shutil.copy2(ROOT / 'build/sdk-lab' / executable, output / executable)
        with mapping.open('x+b') as backing:
            os.chmod(mapping, 0o600)
            backing.truncate(8192)
            with mmap.mmap(backing.fileno(), 8192) as memory:
                struct.pack_into('<III', memory, 0, 0x32424643, 2, 8192)
                env = os.environ.copy()
                env.update(WINEDLLOVERRIDES='dinput8=n,b;mscoree,mshtml=', WINEDEBUG='-all')
                if args.bottle_root:env['CX_BOTTLE_PATH']=str(args.bottle_root.resolve())
                tail=['--open-only',sdk_windows,'--initialize-sdk-1_3_12'] if sdk_windows else ['--virtual-only']
                if args.sdk_mode in ['combined','kf-only','kf-live']:
                    win=lambda p:'Z:'+str(p.resolve()).replace('/',chr(92))
                    tail=['--kf-live' if args.sdk_mode=='kf-live' else '--kf-only' if args.sdk_mode=='kf-only' else '--tf-combined',sdk_windows,'--initialize-sdk-1_3_12','--user-ready','--stop-file',win(args.stop_file)]
                    if args.sdk_mode=='kf-live':tail+=['--force-file',win(args.force_file)]
                    if args.arm_file:tail+=['--arm-file',win(args.arm_file)]
                with (output / 'probe.jsonl').open('w') as log, (output / 'errors.txt').open('w') as err:
                    child = subprocess.Popen([str(args.wine.resolve()), '--bottle', args.bottle,
                                              '--no-gui','--debugmsg',('-all,+dinput,+hid,+loaddll' if sdk_windows else '-all'),'--dll','dinput8=n,b;mscoree,mshtml=',str(output / executable), *tail],
                                             env=env, cwd=output, stdout=log, stderr=err)
                    deadline, sequence = time.monotonic() + (60 if sdk_windows else 30), 0
                    waiting=False;armed=False
                    while child.poll() is None:
                        if args.sdk_mode=='kf-live' and deadline is not None and '"event":"sdk_live_ready"' in (output/'probe.jsonl').read_text(errors='replace'):
                            deadline=None
                            print('SDK KF READY: live force sink; no TF samples.',flush=True)
                        if args.arm_file:
                            events_text=(output/'probe.jsonl').read_text(errors='replace')
                            if not waiting and '"event":"combined_waiting_for_arm"' in events_text:
                                waiting=True;deadline=None
                                print('SDK READY: mode=0; waiting for explicit arm-file, no sample calls yet.',flush=True)
                            if waiting and not armed and args.arm_file.exists():
                                armed=True;deadline=time.monotonic()+20
                        if deadline is not None and time.monotonic() > deadline:
                            raise RuntimeError('Read-only route probe timeout')
                        sequence += 2
                        struct.pack_into('<I', memory, 64, sequence - 1)
                        struct.pack_into('<IQ6I', memory, 68, 1, int(time.time() * 1000),
                                         32768, 65535, 65535, 65535, 0, 8)
                        struct.pack_into('<I', memory, 64, sequence)
                        time.sleep(.005)
                    if child.returncode:
                        raise RuntimeError(f'Route probe exited {child.returncode}')
        print((output / 'probe.jsonl').read_text(), end='')
    finally:
        if child and child.poll() is None:
            if args.sdk_mode in ['combined','kf-only','kf-live'] and args.stop_file:
                args.stop_file.touch()
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:pass
            if child.poll() is None:child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        mapping.unlink(missing_ok=True)
        directory.rmdir()


if __name__ == '__main__':
    main()
