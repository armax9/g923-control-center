#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Temporary per-game virtual DLL + classic motor bridge, with hash-checked rollback."""
import argparse,hashlib,json,os,pathlib,random,shutil,signal,struct,subprocess,time
from classic_log_summary import summarize
ROOT=pathlib.Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(out,state):(out/'classic-session.json').write_text(json.dumps(state,indent=2)+'\n')
def install(out,state):
 target=pathlib.Path(state['target']);src=out/'dinput8.dll'
 if sha(src)!=state['installed_sha']:raise RuntimeError('Staged DLL changed')
 expected=state['previous_sha']
 if target.is_symlink() or (sha(target) if target.exists() else None)!=expected:raise RuntimeError('Game DLL changed since preparation')
 if expected:
  shutil.copy2(target,out/'original-dinput8.dll')
  if sha(out/'original-dinput8.dll')!=expected:raise RuntimeError('Backup hash mismatch')
 state['installation_attempted']=True;save(out,state)
 # Exclusive create of temporary file; atomic replacement only after complete copy.
 temp=target.with_name('.g923-classic-'+str(state['uid'])+'.tmp')
 created=False
 try:
  with temp.open('xb') as f:
   created=True;f.write(src.read_bytes());f.flush();os.fsync(f.fileno())
  if sha(temp)!=state['installed_sha']:raise RuntimeError('Staged bytes changed while copying')
  os.replace(temp,target)
 finally:
  if created:temp.unlink(missing_ok=True)
 state['installed']=True;save(out,state)
def rollback(out,state):
 if not state.get('installation_attempted'):return
 target=pathlib.Path(state['target'])
 if target.is_symlink():raise RuntimeError('Refuse rollback through symlink')
 current=sha(target) if target.exists() else None
 if current==state['previous_sha']:
  state['rollback_complete']=True;save(out,state);return
 if current is not None and current!=state['installed_sha']:raise RuntimeError('Game DLL changed externally; refusing rollback overwrite')
 if state['previous_sha']:
  backup=out/'original-dinput8.dll'
  if sha(backup)!=state['previous_sha']:raise RuntimeError('Original backup changed')
  shutil.copy2(backup,target)
 else:target.unlink(missing_ok=True)
 state['rollback_complete']=True;save(out,state)
def prepare(out,exe):
 exe=exe.resolve(strict=True);out.mkdir(parents=True,exist_ok=False)
 matches=[p for p in exe.parent.iterdir() if p.name.lower()=='dinput8.dll']
 if len(matches)>1:raise RuntimeError('Ambiguous game DLL names')
 target=matches[0] if matches else exe.parent/'dinput8.dll'
 if target.is_symlink():raise RuntimeError('Refuse game DLL symlink')
 for _ in range(100):
  uid=random.randrange(1000000000,2000000000);directory=pathlib.Path('/tmp')/f'crossover-ffb-{uid}'
  try:directory.mkdir(mode=0o700);break
  except FileExistsError:continue
 else:raise RuntimeError('No private mapping path')
 raw=bytearray((ROOT/'build/crossover-base/dinput8.dll').read_bytes());marker=b'CFBUID=0\0'
 if raw.count(marker)!=1:raise RuntimeError('Unreviewed DLL')
 i=raw.index(marker);raw[i:i+24]=('CFBUID='+str(uid)).encode().ljust(24,b'\0');(out/'dinput8.dll').write_bytes(raw)
 state={'purpose':'g923-temporary-classic-game-test','project':str(ROOT),'uid':uid,'mapping':str(directory/'ffb-v2.bin'),'exe':str(exe),'target':str(target),'previous_sha':sha(target) if target.exists() else None,'installed_sha':sha(out/'dinput8.dll'),'installed':False,'hardware_started':False,'trueforce_enabled':False,'strength':0.25}
 save(out,state);print(json.dumps(state,indent=2))
def validate_motor_profile(profile):
 if profile.get('purpose')!='g923-classic-physical-motor-sign' or not profile.get('valid') or profile.get('sign') not in [-1,1] or abs(profile.get('delta',0))<150 or not profile.get('cleanup',{}).get('final_force_command_is_successful_stop'):
  raise RuntimeError('A successful physical motor sign calibration is required')
 if (profile['delta']>0)!=(profile['sign']>0):raise RuntimeError('Inconsistent measured sign')
 return profile['sign']
def run(out,state,app,bottle,stop,motor_profile):
 profile=json.loads(motor_profile.read_text());motor_sign=validate_motor_profile(profile)
 state['motor_profile']=str(motor_profile.resolve());state['measured_motor_sign']=motor_sign

 if stop.exists():raise RuntimeError('Stop request already exists')
 native=None;recorder=None;native_log=None
 try:
  install(out,state)
  native_log=(out/'native.jsonl').open('w');state['hardware_started']=True;save(out,state)
  native=subprocess.Popen([str(ROOT/'build/crossover-base/swift/debug/G923ClassicLab'),'--map',state['mapping'],'--user-ready','--motor-sign',str(int(motor_sign))],stdout=native_log,stderr=subprocess.STDOUT)
  mapping=pathlib.Path(state['mapping']);deadline=time.monotonic()+15
  while time.monotonic()<deadline:
   if stop.exists() or native.poll() is not None:raise RuntimeError('Native startup stopped')
   if mapping.exists() and mapping.stat().st_size==8192:
    with mapping.open('rb') as f:buf=f.read(104)
    if struct.unpack_from('<I',buf,68)[0]==1:break
   time.sleep(.05)
  else:raise RuntimeError('Native wheel not ready')
  for line in (out/'native.jsonl').read_text(errors='replace').splitlines():
   if line.startswith('{'):
    v=json.loads(line)
    if v.get('event')=='classic_hid_output' and v['status']!=0:raise RuntimeError('Initialization HID write failed')
  log=pathlib.Path(state['exe']).parent/'crossover-ffb-observe.log';start=log.stat().st_size if log.exists() else 0
  recorder=subprocess.Popen(['python3',str(ROOT/'sdk-lab/tools/record_crossover_game.py'),'--crossover-app',str(app),'--bottle',bottle,'--exe',state['exe'],'--output-dir',str(out/'game'),'--user-ready'])
  print('GAME CLASSIC BRIDGE ACTIVE: no interaction deadline; exit game normally.',flush=True)
  while recorder.poll() is None:
   if stop.exists() or native.poll() is not None:
    recorder.send_signal(signal.SIGINT);break
   time.sleep(.1)
  state['recorder_exit']=recorder.wait(timeout=10)
  if log.exists():
   with log.open('rb') as f:f.seek(min(start,log.stat().st_size));(out/'game-bridge.log').write_bytes(f.read(4*1024*1024+1024))
 finally:
  if native and native.poll() is None:
   native.terminate()
   try:native.wait(timeout=5)
   except subprocess.TimeoutExpired:native.kill();native.wait();state['native_shutdown_timeout']=True
  if native_log:
   native_log.close()
   with (out/'native.jsonl').open(errors='replace') as f:summary=summarize(f)
   (out/'native-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('Native summary:',json.dumps(summary))
  rollback(out,state)
  mapping=pathlib.Path(state['mapping']);mapping.unlink(missing_ok=True);mapping.parent.rmdir()
  save(out,state);print('Per-game DLL rollback complete:',state.get('rollback_complete',False))
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','install','run','rollback']);p.add_argument('--output-dir',type=pathlib.Path,required=True);p.add_argument('--exe',type=pathlib.Path);p.add_argument('--crossover-app',type=pathlib.Path);p.add_argument('--bottle');p.add_argument('--motor-profile',type=pathlib.Path);p.add_argument('--user-ready',action='store_true');p.add_argument('--stop-file',type=pathlib.Path);a=p.parse_args();out=a.output_dir.resolve()
 if a.action=='prepare':
  if not a.exe:p.error('--exe required')
  prepare(out,a.exe);return
 state=json.loads((out/'classic-session.json').read_text())
 if state.get('purpose')!='g923-temporary-classic-game-test' or state.get('project')!=str(ROOT):raise RuntimeError('Not a project-owned session')
 if a.action=='rollback':rollback(out,state);return
 if a.action=='install':
  if not a.motor_profile:p.error('install requires --motor-profile')
  profile=json.loads(a.motor_profile.read_text());state['measured_motor_sign']=validate_motor_profile(profile);state['motor_profile']=str(a.motor_profile.resolve());install(out,state);return
 if not a.user_ready or not a.stop_file or not a.crossover_app or not a.bottle or not a.motor_profile:p.error('run requires readiness, stop-file, CrossOver app and bottle')
 if state.get('installation_attempted'):raise RuntimeError('Use a fresh session for each run')
 run(out,state,a.crossover_app,a.bottle,a.stop_file,a.motor_profile)
if __name__=='__main__':main()
