#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the real SDK-session executable against a no-HID test double."""
import argparse
import json
import mmap
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
    parser.add_argument('--wine-build', type=Path, required=True)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--replay',type=Path)
    parser.add_argument('--kf-live', action='store_true')
    parser.add_argument('--kf-only', action='store_true')
    args = parser.parse_args()
    replay=[]
    if args.replay:
        for line in args.replay.read_text().splitlines():
            try:r=json.loads(line)
            except ValueError:continue
            if r.get('event')=='force_snapshot' and r.get('active') and r.get('output'):replay.append(r['output'])
        if not replay:raise RuntimeError('No recorded forces')
    replay_index=0
    prefix = args.prefix.resolve()
    if json.loads((prefix / 'g923-owned-prefix.json').read_text()).get('purpose') != 'g923-isolated-wine-hid-experiment':
        parser.error('Expected owned test prefix')
    output = args.output_dir.resolve()
    output.mkdir(exist_ok=False, parents=True)
    results = []
    cases = [('', 0), ('kinetic', 22), ('sample', 19), ('clear', 23), ('arm',0), ('arm-stop',18), ('operator-stop',[19,22])]
    if args.kf_only: cases=[('',0),('kinetic',22),('clear',23),('arm',0),('arm-stop',18)]
    if args.kf_live: cases=[('',0),('kinetic',22),('clear',23),('stale',24),('nan',24)]
    for fault, expected in cases:
        directory = output / (fault or 'success')
        directory.mkdir()
        for name in ['sdk-session.exe', 'fixture-sdk-combined.dll']:
            shutil.copy2(ROOT / 'build/sdk-lab' / name, directory / name)
        # Deliberate software-only alias: exercise the observer's SDK basename filter.
        shutil.copy2(directory/'fixture-sdk-combined.dll',directory/'trueforce_sdk_x64.dll')
        uid = secrets.randbelow(1000000000) + 1000000000
        shared = Path('/tmp') / f'crossover-ffb-{uid}'
        shared.mkdir(mode=0o700)
        mapping = shared / 'ffb-v2.bin'
        raw = bytearray((ROOT / 'build/crossover-base/dinput8.dll').read_bytes())
        if raw.count(b'CFBUID=0\0') != 1:
            raise RuntimeError('Invalid project DLL marker')
        index = raw.index(b'CFBUID=0\0')
        raw[index:index+24] = ('CFBUID=' + str(uid)).encode().ljust(24, b'\0')
        (directory / 'dinput8.dll').write_bytes(raw)
        child = None
        try:
            with mapping.open('x+b') as backing:
                backing.truncate(8192)
                with mmap.mmap(backing.fileno(), 8192) as memory:
                    struct.pack_into('<III', memory, 0, 0x32424643, 2, 8192)
                    env = os.environ.copy()
                    env.update(WINEPREFIX=str(prefix), WINEDEBUG='-all',
                               WINEDLLOVERRIDES='dinput8=n,b;mscoree,mshtml=',
                               G923_COMBINED_FIXTURE_FAIL='' if fault.startswith('arm') else fault, G923_SDK_TRACE='1', G923_SDK_STOP_FILE='')
                    win = lambda p: 'Z:' + str(p).replace('/', '\\')
                    env['G923_SDK_STOP_FILE']=win(directory/'operator-stop-request')
                    command = [str(args.wine_build.resolve() / 'wine'), str(directory / 'sdk-session.exe'),
                               '--kf-live' if args.kf_live else '--kf-only' if args.kf_only else '--tf-combined', win(directory / 'trueforce_sdk_x64.dll'),
                               '--initialize-sdk-1_3_12', '--user-ready', '--stop-file',
                               win(directory / 'stop-request')]
                    if args.kf_live:command+=['--force-file',win(directory/'force.bin')]
                    if fault=='operator-stop':env['G923_COMBINED_FIXTURE_FAIL']=''
                    if fault.startswith('arm'):command+=['--arm-file',win(directory/'arm-request')]
                    waiting_at=None;transition=False
                    with (directory / 'events.jsonl').open('w') as log, (directory / 'errors.txt').open('w') as err:
                        child = subprocess.Popen(command, env=env, cwd=directory, stdout=log, stderr=err)
                        deadline, sequence = time.monotonic() + 30, 0
                        live_started=None
                        while child.poll() is None:
                            if args.kf_live:
                                stamp=int(time.time()*1000)-(1000 if fault=='stale' else 0)
                                level=float('nan') if fault=='nan' else replay[replay_index % len(replay)] if replay else .25
                                replay_index+=1
                                temp=directory/'force.tmp';temp.write_bytes(struct.pack('<4sIQd',b'G9KF',1,stamp,level));temp.replace(directory/'force.bin')
                                text=(directory/'events.jsonl').read_text(errors='replace')
                                if '"event":"sdk_live_ready"' in text:
                                    if live_started is None:live_started=time.monotonic()
                                    if fault in ['', 'clear'] and time.monotonic()-live_started>.3:(directory/'stop-request').touch()

                            if fault.startswith('arm') and not transition:
                                text=(directory/'events.jsonl').read_text(errors='replace')
                                if '"event":"combined_waiting_for_arm"' in text:
                                    if waiting_at is None:waiting_at=time.monotonic()
                                    if '"event":"enable_tf_zero"' in text or '"event":"pulse_finished"' in text:raise RuntimeError('Output before arm')
                                    if time.monotonic()-waiting_at>=.2:
                                        (directory/('stop-request' if fault=='arm-stop' else 'arm-request')).touch();transition=True
                            if fault=='operator-stop' and not transition:
                                text=(directory/'events.jsonl').read_text(errors='replace')
                                if '"event":"combined_limits"' in text:
                                    (directory/'operator-stop-request').touch();transition=True
                            if time.monotonic() > deadline:
                                raise RuntimeError('Fixture watchdog')
                            sequence += 2
                            struct.pack_into('<I', memory, 64, sequence - 1)
                            struct.pack_into('<IQ6I', memory, 68, 1, int(time.time()*1000),
                                             32768, 65535, 65535, 65535, 0, 8)
                            struct.pack_into('<I', memory, 64, sequence)
                            time.sleep(.005)
            events = [json.loads(line) for line in (directory / 'events.jsonl').read_text().splitlines()]
            if child.returncode not in (expected if isinstance(expected,list) else [expected]):
                raise RuntimeError(f'{fault}: exit {child.returncode}, expected {expected}')
            if fault=='arm-stop':
                if any(e.get('event')=='enable_tf_zero' for e in events):raise RuntimeError('Arming cancellation entered TF mode')
                if not any(e.get('event')=='sdk_closed' and e.get('pulse_send_calls')==0 for e in events):raise RuntimeError('Cancellation sent samples')
            for name in (['sdk_wheel_close'] if fault=='arm-stop' else ['kinetic_zero', 'clear_tf', 'restore_mode', 'sdk_wheel_close']):
                if not any(e.get('event') == name and e.get('status_hex') == '00000000' for e in events):
                    raise RuntimeError(f'{fault}: cleanup missing {name}')
            if fault!='arm-stop' and not any(e.get('event') == 'force_mode_restored' and e.get('value') == 0 for e in events):
                raise RuntimeError('Mode not restored')
            trace=[json.loads(line) for line in (directory/'g923-sdk-trace.jsonl').read_text().splitlines()]
            if not any(e.get('name')=='dllClose' and e.get('calls')==1 for e in trace):raise RuntimeError('SDK observer lifecycle missing')
            if fault=='operator-stop' and not any(e.get('name')=='operator_stop' and e.get('calls')==1 and e.get('status_hex')=='00000000' for e in trace):raise RuntimeError('Operator stop not confirmed')
            if args.kf_only or args.kf_live:
                if any(e.get('name')=='logiTrueForceSetTorqueTFint16' for e in trace):raise RuntimeError('KF-only called TF samples')
                if args.kf_only and fault!='arm-stop' and not any(e.get('event')=='kf_only_finished' and e.get('tf_sample_calls')==0 for e in events):raise RuntimeError('KF-only completion missing')
            if not args.kf_only and not args.kf_live and fault in ['', 'arm']:
                tf=[e for e in trace if e.get('name')=='logiTrueForceSetTorqueTFint16']
                if not tf or tf[-1]['calls']!=117 or tf[-1]['samples_total']!=480 or tf[-1]['nonzero_batches']==0:raise RuntimeError('SDK observer sample counters wrong')
            if args.kf_live and fault=='':
                live=[e for e in events if e.get('event')=='sdk_live_force' and e.get('fresh')]
                if not live or not any(abs(e.get('target',0))>0 for e in live):raise RuntimeError('Live force did not reach SDK sink')
            results.append(dict(fault=fault or 'none', expected_exit=expected,
                                actual_exit=child.returncode, cleanup_verified=True, observer_verified=True, hardware=False))
        finally:
            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            mapping.unlink(missing_ok=True)
            shared.rmdir()
    (output / 'result.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
