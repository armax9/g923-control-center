#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolated virtual DInput effect test; software-only unless explicitly armed."""
import argparse,json,math,mmap,os,pathlib,random,shutil,struct,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
def diagnostic_strength(value):
 number=float(value)
 if not math.isfinite(number) or not 0 <= number <= 0.5:raise argparse.ArgumentTypeError('Diagnostic strength must be finite and between 0 and 0.5')
 return number
def main():
 p=argparse.ArgumentParser();p.add_argument('--wine-build',type=pathlib.Path,required=True);p.add_argument('--prefix',type=pathlib.Path,required=True);p.add_argument('--output-dir',type=pathlib.Path,required=True);p.add_argument('--hardware',action='store_true');p.add_argument('--enable-file',type=pathlib.Path);p.add_argument('--strength',type=diagnostic_strength,default=0.25);p.add_argument('--verify-stop-loop',action='store_true');p.add_argument('--effect',choices=['sine','spring','damper','friction'],default='sine');p.add_argument('--motor-profile',type=pathlib.Path);p.add_argument('--user-ready',action='store_true');p.add_argument('--stop-file',type=pathlib.Path);a=p.parse_args()
 if a.strength!=0.25 and a.effect=='sine':p.error('Explicit strength is supported only for condition effects')
 if a.verify_stop_loop and (a.hardware or a.effect not in ['damper','friction']):p.error('stop-loop verification is software-only and condition-only')
 if a.hardware and (not a.user_ready or not a.stop_file or a.stop_file.exists()):raise SystemExit('Hardware requires readiness and a fresh stop-file path')
 if a.enable_file and (a.effect not in ['damper','friction'] or not (a.hardware or a.verify_stop_loop) or a.enable_file.exists()):p.error('Comparison requires resistance mode, fresh enable-file, and hardware or software stop-loop')
 motor_sign=None
 if a.hardware and a.effect!='sine':
  from classic_game import validate_motor_profile
  if not a.motor_profile:p.error('spring hardware test requires measured motor profile')
  motor_sign=validate_motor_profile(json.loads(a.motor_profile.read_text()))
 prefix=a.prefix.resolve();marker=json.loads((prefix/'g923-owned-prefix.json').read_text())
 if marker.get('purpose')!='g923-isolated-wine-hid-experiment':raise SystemExit('Not an owned lab prefix')
 out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
 if a.verify_stop_loop:a.stop_file=out/'software-stop-request'
 for _ in range(100):
  uid=random.randrange(1000000000,2000000000);directory=pathlib.Path('/tmp')/f'crossover-ffb-{uid}'
  try:directory.mkdir(mode=0o700);break
  except FileExistsError:continue
 else:raise RuntimeError('Cannot reserve private mapping')
 mapping=directory/'ffb-v2.bin';raw=bytearray((ROOT/'build/crossover-base/dinput8.dll').read_bytes());mark=b'CFBUID=0\0'
 if raw.count(mark)!=1:raise RuntimeError('Unreviewed DLL marker')
 i=raw.index(mark);raw[i:i+24]=('CFBUID='+str(uid)).encode().ljust(24,b'\0');(out/'dinput8.dll').write_bytes(raw)
 shutil.copyfile(ROOT/'build/sdk-lab/ffb-exercise.exe',out/'ffb-exercise.exe')
 native=None;memory=None;fd=None;child=None;seen=[];native_log=None;shutdown_timeout=False
 try:
  if a.hardware:
   native_log=(out/'native.jsonl').open('w')
   binary=ROOT/'build/crossover-base/swift/debug/G923ClassicLab'
   extra=[]
   if a.effect!='sine':
    binary=ROOT/'build/crossover-base/G923ClassicLab-all-effects-candidate';extra=['--all-effects','--motor-sign',str(int(motor_sign)),'--strength',str(a.strength)]
   native=subprocess.Popen([str(binary),'--map',str(mapping),'--user-ready',*extra],stdout=native_log,stderr=subprocess.STDOUT)
   deadline=time.monotonic()+15
   while time.monotonic()<deadline:
    if a.stop_file.exists():raise RuntimeError("Stop requested during initialization")
    if native.poll() is not None:raise RuntimeError('Native bridge exited')
    if mapping.exists() and mapping.stat().st_size==8192:
     with mapping.open('rb') as f:buf=f.read(104)
     if struct.unpack_from('<I',buf,68)[0]==1:break
    time.sleep(.05)
   else:raise RuntimeError('Native input did not become ready')
   text=(out/'native.jsonl').read_text(errors='replace')
   for line in text.splitlines():
    if line.startswith('{'):
     v=json.loads(line)
     if v.get('event')=='classic_hid_output' and v['status']!=0:raise RuntimeError('Native initialization write failed')
  else:
   fd=os.open(mapping,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600);os.ftruncate(fd,8192);memory=mmap.mmap(fd,8192)
   struct.pack_into('<III',memory,0,0x32424643,2,8192)
  env=os.environ.copy();env.update(WINEPREFIX=str(prefix),WINEDEBUG='-all',WINEDLLOVERRIDES='dinput8=n,b;mscoree,mshtml=')
  software_flag='--'+a.effect+'-software-only' if a.effect!='sine' else '--software-only'
  hardware_flag='--'+a.effect+'-exercise' if a.effect!='sine' else '--exercise'
  args=[software_flag] if not (a.hardware or a.verify_stop_loop) else [hardware_flag,'--user-ready','--stop-file','Z:'+str(a.stop_file.resolve()).replace('/',chr(92))]
  if a.enable_file:args += ['--enable-file','Z:'+str(a.enable_file.resolve()).replace('/',chr(92))]
  with (out/'windows.jsonl').open('w') as log,(out/'wine-errors.txt').open('w') as err:
   child=subprocess.Popen([str(a.wine_build.resolve()/'wine'),str(out/'ffb-exercise.exe'),*args],env=env,cwd=out,stdout=log,stderr=err)
   continuous=a.hardware and a.effect in ['damper','friction']
   deadline=time.monotonic()+45;seq=0;active_announced=False;auto_stop_at=None;comparison_step=0
   while child.poll() is None:
    if not active_announced:
     # A log line from the Windows effect start, not just process creation.
     if '"event":"exercise_active"' in (out/'windows.jsonl').read_text(errors='replace'):
      active_announced=True
      if a.verify_stop_loop:auto_stop_at=time.monotonic()+.1
      if continuous:
       deadline=None
       print('EFFECT ACTIVE: '+a.effect+'; stop-file '+str(a.stop_file)+'; no user-response timer.',flush=True)
    if auto_stop_at is not None and time.monotonic()>=auto_stop_at:
     if a.enable_file and comparison_step<2:
      if comparison_step==0:a.enable_file.touch()
      else:a.enable_file.unlink()
      comparison_step+=1;auto_stop_at=time.monotonic()+.15
     else:a.stop_file.touch();auto_stop_at=None
    if deadline is not None and time.monotonic()>deadline:child.terminate();raise RuntimeError('Wine watchdog; physical stop not implied')
    if memory is not None:
     seq+=2;struct.pack_into('<I',memory,64,seq-1);struct.pack_into('<IQ6I',memory,68,1,int(time.time()*1000),32768,65535,65535,65535,0,8);struct.pack_into('<I',memory,64,seq)
     # Read a stable seqlock snapshot, not a partially published effect record.
     before=struct.unpack_from('<I',memory,256)[0];buf=memory[256:3392];after=struct.unpack_from('<I',memory,256)[0]
     if before==after and not before&1:
      for n in range(32):
       words=struct.unpack_from('<24I',buf,64+n*96)
       if words[0] and words[1]:seen.append({'kind':words[0],'starts':words[2],'magnitude':words[16],'period_us':words[19],'positive_coefficient':words[17],'positive_saturation':words[19],'negative_saturation':words[20]})
    time.sleep(.005)
   rc=child.wait()
  if rc:raise RuntimeError('Windows exercise failed, exit '+str(rc))
  if a.verify_stop_loop:
   events=[json.loads(l) for l in (out/'windows.jsonl').read_text().splitlines() if l.startswith('{')]
   if a.enable_file:
    phases=[v['enabled'] for v in events if v.get('event')=='comparison_phase']
    if phases != [False,True,False]:raise RuntimeError('Comparison off/on/off phases not confirmed')
   if not any(v.get('event')=='stop_requested' for v in events) or not all(any(v.get('event')==key and v.get('hr')=='00000000' for v in events) for key in ['stop_effect','reset_effects']):raise RuntimeError('Software stop/cleanup not confirmed')
  if not a.hardware:
   expected=any(v['kind']==4 and v['magnitude']==8000 and v['period_us']==200000 for v in seen) if a.effect=='sine' else any(v['kind']=={'spring':8,'damper':9,'friction':11}[a.effect] and v['positive_coefficient']==10000 and v['positive_saturation']==4000 and v['negative_saturation']==4000 for v in seen)
   if not expected:raise RuntimeError('Expected live effect not mirrored into mapping')
  report={'effect':a.effect,'configured_native_strength':a.strength,'condition_output_cap':0.4*a.strength if a.effect!='sine' else None,'software_stop_loop_verified':a.verify_stop_loop,'motor_sign':motor_sign,'hardware':a.hardware,'windows_exit':rc,'live_effect_observed_in_shared_memory':None if a.hardware else bool(seen),'sampled_effect_records':seen[:8],'physical_playback_confirmed':False,'trueforce_enabled':False,'settings_or_game_dlls_changed':False}
  (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
 finally:
  if child and child.poll() is None:
   child.terminate()
   try:child.wait(timeout=3)
   except subprocess.TimeoutExpired:child.kill();child.wait()
  if native and native.poll() is None:
   native.terminate()
   try:native.wait(timeout=5)
   except subprocess.TimeoutExpired:
    shutdown_timeout=True;native.kill();native.wait();print('Native shutdown timed out; physical stop unconfirmed')
  if native_log:
   native_log.close()
   from classic_log_summary import summarize
   with (out/'native.jsonl').open(errors='replace') as log:summary=summarize(log)
   summary['shutdown_timeout']=shutdown_timeout
   (out/'native-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
   print('Native output summary:',json.dumps(summary))
  if memory is not None:memory.close()
  if fd is not None:os.close(fd)
  mapping.unlink(missing_ok=True);directory.rmdir()
if __name__=='__main__':main()
