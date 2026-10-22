#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Real Wine COM test with SYNTHETIC INPUT and private shared-memory UID.
No app, HID writer, effect creation, or SDK DLL involved.
"""
import json,mmap,os,pathlib,random,re,shutil,struct,threading,time
from lab import ROOT,STATE,ensure_bottle,wine,write_json
CX=pathlib.Path(os.environ.get('CROSSOVER_APP','/Applications/CrossOver.app'))/'Contents/SharedSupport/CrossOver'
def main():
 _,env=ensure_bottle(CX);folder=STATE/'virtual-input-fixture';folder.mkdir(exist_ok=True)
 src=ROOT/'build/crossover-base/dinput8.dll';raw=bytearray(src.read_bytes());marker=b'CFBUID=0\0'
 if raw.count(marker)!=1:raise RuntimeError('Unexpected UID slot; refusing binary patch')
 off=raw.index(marker)
 for _ in range(100):
  uid=random.randrange(1000000000,2000000000);directory=pathlib.Path('/tmp')/f'crossover-ffb-{uid}'
  try:directory.mkdir(mode=0o700);break
  except FileExistsError:continue
 else:raise RuntimeError('Cannot reserve isolated input mapping')
 raw[off:off+24]=('CFBUID='+str(uid)).encode().ljust(24,b'\0')
 (folder/'dinput8.dll').write_bytes(raw);shutil.copy2(ROOT/'build/windows/dinput-probe.exe',folder/'dinput-probe.exe')
 path=directory/'ffb-v2.bin';fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600);os.ftruncate(fd,8192);view=mmap.mmap(fd,8192);os.close(fd)
 stop=threading.Event();errors=[]
 def feed():
  seq=0
  try:
   while not stop.is_set():
    seq+=2;struct.pack_into('<III',view,0,0x32424643,2,8192)
    struct.pack_into('<I',view,64,seq-1)
    struct.pack_into('<I',view,68,1);struct.pack_into('<Q',view,72,int(time.time()*1000))
    steering=10000 if seq%40<20 else 50000
    struct.pack_into('<IIIIII',view,80,steering,12000,23000,34000,5,8)
    struct.pack_into('<I',view,64,seq);stop.wait(.02)
  except Exception as e:errors.append(str(e))
 thread=threading.Thread(target=feed);thread.start()
 try:
  live=wine(CX,env,['--dll','dinput8=n,b',folder/'dinput-probe.exe'])
 finally:
  stop.set();thread.join()
 try:
  if errors:raise RuntimeError(errors)
  assert live['returncode']==0,live['stdout']+live['stderr']
  rows=re.findall(r'state x=(-?\d+) y=(-?\d+) z=(-?\d+) rx=(-?\d+) ry=(-?\d+) rz=(-?\d+) slider0=(-?\d+)',live['stdout'])
  assert len({r[0] for r in rows})>=2,'Expected changing synthetic steering values'
  assert any(r[1]=='12000' and r[5]=='23000' and r[6]=='34000' for r in rows),'Pedal layout mismatch'
  time.sleep(.65)
  stale=wine(CX,env,['--dll','dinput8=n,b',folder/'dinput-probe.exe'])
  assert stale['returncode']==3,'Stale synthetic input should not advertise an attached G923'
  report={'pass':True,'synthetic_input_only':True,'sdk_or_hardware_tested':False,'effects_created':False,'distinct_steering_values':sorted({int(r[0]) for r in rows}),'pedals_verified':[12000,23000,34000],'live':live,'stale':stale}
  write_json(STATE/'virtual-input-runtime.json',report);print(json.dumps({k:v for k,v in report.items() if k not in ['live','stale']},indent=2))
 finally:
  view.close();path.unlink();directory.rmdir()
if __name__=='__main__':main()
