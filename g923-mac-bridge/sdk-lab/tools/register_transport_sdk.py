#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Register pinned SDK only in the private transport experiment, never Steam."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
KEY = r'HKLM\SOFTWARE\Classes\CLSID\{e8dfb59f-141f-40e4-8dd4-5526ead25a4c}'
DLL = r'C:\Program Files\Logi\Trueforce\1_3_12\trueforce_sdk_x64.dll'
SDK_HASH = '2468bdafe64c09ff42ef26f09e49f2096321bb687467323aafb3f0672fb83315'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--bottle',default='G923TFTransport')
    parser.add_argument('--apply', action='store_true', help='Default only prints the plan')
    args = parser.parse_args()
    experiment = args.experiment.resolve()
    purpose = 'g923-isolated-crossover-hid-transport'
    if json.loads((experiment / 'manifest.json').read_text()).get('purpose') != purpose:
        parser.error('Invalid experiment manifest')
    if Path(args.bottle).name!=args.bottle or args.bottle=='Steam':parser.error('Private bottle name required')
    prefix = experiment / args.bottle
    if prefix.is_symlink() or json.loads((prefix / 'g923-owned-prefix.json').read_text()).get('purpose') != purpose:
        parser.error('Not a private transport bottle')
    sdk = prefix / 'drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll'
    if hashlib.sha256(sdk.read_bytes()).hexdigest() != SDK_HASH:
        parser.error('Unreviewed SDK bytes')
    plan = dict(key=KEY, value=DLL, original_sdk_sha256=SDK_HASH,
                private_bottle=str(prefix), applied=False, game_launched=False)
    if args.apply:
        logdir = experiment / ('sdk-registration' if args.bottle=='G923TFTransport' else 'sdk-registration-'+args.bottle)
        logdir.mkdir(exist_ok=False)
        env = os.environ.copy()
        env['CX_BOTTLE_PATH'] = str(experiment)
        command = [str(experiment / 'runtime/bin/wine'), '--bottle', args.bottle,
                   '--no-gui', '--debugmsg', '-all']

        def run(name, tail):
            result = subprocess.run(command + tail, env=env, capture_output=True,
                                    text=True, timeout=40)
            (logdir / (name + '.json')).write_text(json.dumps(dict(
                returncode=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2) + '\n')
            return result

        signature = run('signature', [str(ROOT / 'build/sdk-lab/sdk-probe.exe'), '--verify', DLL])
        if signature.returncode or not any(json.loads(line).get('trusted_here')
                for line in signature.stdout.splitlines() if line.startswith('{')):
            raise RuntimeError('Original signature not trusted; no registry change')
        inventory = run('before', [str(ROOT / 'build/sdk-lab/sdk-probe.exe')])
        entries = [json.loads(line) for line in inventory.stdout.splitlines() if line.startswith('{')]
        matching = [e for e in entries if e.get('event') == 'registry' and
                    e.get('key') == KEY.replace('HKLM\\', '')]
        if inventory.returncode or len(matching) != 1 or matching[0]['status'] != 2:
            raise RuntimeError('Expected absent registration; refusing overwrite')
        result = run('apply', ['reg.exe', 'add', KEY, '/ve', '/t', 'REG_SZ', '/d', DLL, '/f'])
        if result.returncode:
            raise RuntimeError('Registry installation failed; inspect apply.json')
        after = run('after', [str(ROOT / 'build/sdk-lab/sdk-probe.exe')])
        entries = [json.loads(line) for line in after.stdout.splitlines() if line.startswith('{')]
        if after.returncode or not any(e.get('event') == 'registry' and
                e.get('key') == KEY.replace('HKLM\\', '') and e.get('status') == 0 and
                e.get('value') == DLL for e in entries):
            raise RuntimeError('Registration verification failed')
        plan['applied'] = True
        plan['rollback'] = 'Disposable private bottle; original registration was absent. No Steam or installed runtime edits.'
        (logdir / 'manifest.json').write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps(plan, indent=2))


if __name__ == '__main__':
    main()
