#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure SDK force polarity against real macOS wheel input. No game launch."""
import argparse,datetime,fcntl,json,math,os,signal,statistics,struct,subprocess,sys,time
from pathlib import Path
import ets2

def infer_sign(before, after):
    delta=after-before
    if not math.isfinite(delta) or abs(delta)<80:raise ValueError('Insufficient wheel movement; direction not measured')
    if abs(delta)>6000:raise ValueError('Excessive movement; direction not accepted')
    return (1 if delta>0 else -1),delta

def write_force(path,level):
    tmp=path.with_suffix('.tmp');tmp.write_bytes(struct.pack('<4sIQd',b'G9KF',1,int(time.time()*1000),level));tmp.replace(path)

def sensor(path):
    for _ in range(5):
        raw=path.read_bytes()
        seq,connected,stamp,steer,gas,brake,clutch,buttons=struct.unpack_from('<IIQ5I',raw,64)
        with path.open('rb') as f:
            f.seek(64);after=struct.unpack('<I',f.read(4))[0]
        if not seq&1 and seq==after and connected and abs(time.time()*1000-stamp)<=250:
            return steer,buttons
        time.sleep(.001)
    raise ValueError('Stale or unstable physical input')

def run():
    from auto_bridge import detect
    if detect(subprocess.check_output(['/bin/ps','-axo','comm='],text=True)):raise ValueError('Close supported games before direction calibration')
    lock=os.open('/tmp/g923-mac-bridge-'+str(os.getuid())+'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    if os.fstat(lock).st_uid!=os.getuid():raise ValueError('Invalid motor ownership file')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    output=ets2.INSTALL/('sdk-direction-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));output.mkdir()
    input_file=output/'input.bin';force=output/'force.bin';stop=output/'stop';transport=ets2.TOP/'work/crossover-tf-11.17'
    children=[];logs=[];samples=[];result=None
    def launch(name,args):
        log=(output/(name+'.log')).open('w');logs.append(log)
        p=subprocess.Popen([str(x) for x in args],stdout=log,stderr=subprocess.STDOUT);children.append(p);return p
    try:
        native=launch('input',[ets2.ROOT/'build/g923-input','--map',input_file,'--seconds','0'])
        deadline=time.monotonic()+15
        while not input_file.exists():
            if native.poll() is not None or time.monotonic()>deadline:raise ValueError('Physical input unavailable')
            time.sleep(.02)
        write_force(force,0)
        worker=launch('sdk',[sys.executable,'-u',ets2.ROOT/'sdk-lab/tools/run_sdk_route.py','--wine',transport/'runtime/bin/wine','--bottle','G923TFTransport','--bottle-root',transport,'--sdk-open-only',transport/'G923TFTransport/drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll','--sdk-mode','kf-live','--user-ready','--stop-file',stop,'--force-file',force,'--output-dir',output/'worker'])
        deadline=time.monotonic()+60;stable=[];pulse_start=None;end=None;baseline=None
        print('SDK direction test: waiting for stationary physical input, then one positive 15% / 200 ms pulse. No game or vibration.',flush=True)
        while True:
            now=time.monotonic();desired=0.0
            if native.poll() is not None or worker.poll() is not None:raise ValueError('A test process exited')
            steer,buttons=sensor(input_file)
            if buttons:raise ValueError('Stopped by wheel button')
            path=output/'worker/probe.jsonl';ready=path.exists() and '"event":"sdk_live_ready"' in path.read_text(errors='replace')
            if pulse_start is None:
                if time.monotonic()>deadline:raise ValueError('SDK/stationary input not ready')
                if ready:
                    stable.append((now,steer));stable=[x for x in stable if now-x[0]<=.6]
                    if len(stable)>=45 and stable[-1][0]-stable[0][0]>=.45 and max(x[1] for x in stable)-min(x[1] for x in stable)<40:
                        baseline=statistics.median(x[1] for x in stable)
                        if not 8000<baseline<57535:raise ValueError('Wheel too near a steering stop')
                        pulse_start=now;end=now+.4
                        print('SDK direction pulse active.',flush=True)
            else:
                elapsed=now-pulse_start
                if abs(steer-baseline)>4000:raise ValueError('Travel limit; test stopped')
                if elapsed<.2:
                    ramp=max(0,min(1,elapsed/.02,(.2-elapsed)/.02));desired=.15*ramp
                samples.append({'time':elapsed,'steer':steer})
                if now>=end:
                    tail=[x['steer'] for x in samples if .3<=x['time']<=.4]
                    sign,delta=infer_sign(baseline,statistics.median(tail))
                    result={'measured':True,'sign':sign,'raw_delta':delta,'before':baseline,'sdk_positive_fraction':.15,'pulse_ms':200,'samples':samples};break
            write_force(force,desired)
            time.sleep(.005)
    finally:
        write_force(force,0);stop.touch()
        for p in reversed(children):
            if p is children[0] and p.poll() is None:p.send_signal(signal.SIGINT)
            if p.poll() is None:
                try:p.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    p.terminate()
                    try:p.wait(timeout=5)
                    except subprocess.TimeoutExpired:p.kill();p.wait()
        for log in logs:log.close()
        os.close(lock)
    events=[json.loads(x) for x in (output/'worker/probe.jsonl').read_text().splitlines()]
    clean=all(any(r.get('event')==name and r.get('status_hex')=='00000000' for r in events) for name in ['kinetic_zero','clear_kf','clear_tf','restore_mode','sdk_wheel_close'])
    if not clean or not result:raise ValueError('Direction cleanup not verified')
    result['cleanup_verified']=True;(output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    m=json.loads((ets2.INSTALL/'sdk-candidate.json').read_text());m['sdk_direction']=dict(result, samples=None);m['sdk_direction']['log']=str(output);m.pop('gameplay_blocked',None)
    (ets2.INSTALL/'sdk-candidate.json').write_text(json.dumps(m,indent=2)+'\n');print('SDK direction measured: '+str(result['sign'])+'; raw movement '+str(result['raw_delta'])+'; cleanup verified.',flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--user-ready',action='store_true');a=p.parse_args()
    if not a.user_ready:p.error('Explicit user readiness required')
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    run()
