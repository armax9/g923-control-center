#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Opt-in ETS2 SDK KF candidate. No Steam/game launch and no mescon."""
import argparse,datetime,json,signal,subprocess,sys,time
from pathlib import Path
import ets2

def run():
    m=ets2.state()
    candidate=json.loads((ets2.INSTALL/'sdk-candidate.json').read_text())
    if candidate.get('gameplay_blocked'):raise ValueError(candidate['gameplay_blocked'])
    direction=candidate.get('sdk_direction',{})
    if not direction.get('measured') or not direction.get('cleanup_verified') or direction.get('sign') not in [-1,1]:raise ValueError('Measure SDK direction first')
    for name, expected in candidate['hashes'].items():
        path=Path(name)
        if ets2.sha(path)!=expected:raise ValueError('SDK candidate changed: '+name)
    root=ets2.ROOT; top=ets2.TOP
    transport=top/'work/crossover-tf-11.17'
    output=ets2.INSTALL/('sdk-run-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir();force=output/'force.bin';stop=output/'sdk-stop'
    children=[];files=[]
    def launch(name,args):
        log=(output/(name+'.log')).open('w');files.append(log)
        p=subprocess.Popen([str(x) for x in args],stdout=log,stderr=subprocess.STDOUT);children.append(p);return p
    try:
        native=launch('native',[ets2.INSTALL/'G923SDKInputLab','--map',m['mapping'],'--user-ready','--motor-sign','-1','--all-effects','--strength','1','--max-force','1','--sdk-force-file',force,'--sdk-force-sign',str(direction['sign'])])
        deadline=time.monotonic()+15
        while not force.exists():
            if native.poll() is not None:raise RuntimeError('Input/effect evaluator failed')
            if time.monotonic()>deadline:raise RuntimeError('Input startup timeout')
            time.sleep(.05)
        worker=launch('sdk',[sys.executable,'-u',root/'sdk-lab/tools/run_sdk_route.py','--wine',transport/'runtime/bin/wine','--bottle','G923TFTransport','--bottle-root',transport,'--sdk-open-only',transport/'G923TFTransport/drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll','--sdk-mode','kf-live','--user-ready','--stop-file',stop,'--force-file',force,'--output-dir',output/'worker'])
        ready=False
        while True:
            if native.poll() is not None or worker.poll() is not None:raise RuntimeError('SDK candidate stopped; inspect '+str(output))
            log=output/'worker/probe.jsonl'
            if not ready and log.exists() and '"event":"sdk_live_ready"' in log.read_text(errors='replace'):
                ready=True;print('BRIDGE_LISTENING: ETS2 SDK FFB ready. Launch ETS2 yourself. Engine emulation is disabled. Logs: '+str(output),flush=True)
            time.sleep(.2)
    finally:
        stop.touch()  # SDK first; input evaluator maintains freshness until cleanup.
        for p in reversed(children):
            if p is children[0] and p.poll() is None:p.send_signal(signal.SIGINT)
            if p.poll() is None:
                try:p.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    p.terminate()
                    try:p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        p.kill();p.wait()
                        print('SDK cleanup watchdog: inspect logs; physical stop is not confirmed.',flush=True)
        for f in files:f.close()
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--user-ready',action='store_true');a=p.parse_args()
    if not a.user_ready:p.error('Explicit readiness required')
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    try:run()
    except KeyboardInterrupt:print('SDK bridge stopped.',flush=True)
