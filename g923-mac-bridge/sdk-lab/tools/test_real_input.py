#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""User-assisted physical input only: no effects, SDK or output reports."""
import json,os,pathlib,random,re,shutil,subprocess,time
from lab import ROOT,STATE,ensure_bottle,wine,write_json,run,BOTTLE,winpath
CX=pathlib.Path(os.environ.get('CROSSOVER_APP','/Applications/CrossOver.app'))/'Contents/SharedSupport/CrossOver'
def main():
 _,env=ensure_bottle(CX);folder=STATE/'real-input-probe';folder.mkdir(exist_ok=True)
 raw=bytearray((ROOT/'build/crossover-base/dinput8.dll').read_bytes());marker=b'CFBUID=0\0';assert raw.count(marker)==1
 for _ in range(100):
  uid=random.randrange(1000000000,2000000000);directory=pathlib.Path('/tmp')/f'crossover-ffb-{uid}'
  try:directory.mkdir(mode=0o700);break
  except FileExistsError:continue
 else:raise RuntimeError('Cannot reserve isolated mapping')
 off=raw.index(marker);raw[off:off+24]=('CFBUID='+str(uid)).encode().ljust(24,b'\0');(folder/'dinput8.dll').write_bytes(raw)
 shutil.copy2(ROOT/'build/windows/dinput-probe.exe',folder/'dinput-probe.exe')
 stop_file=STATE/'real-input-stop';stop_file.unlink(missing_ok=True)
 native_log=STATE/'real-input-native.txt';mapping=directory/'ffb-v2.bin';results=[]
 with native_log.open('w') as log:
  native=subprocess.Popen([ROOT/'build/g923-input','--map',mapping,'--seconds','0'],stdout=log,stderr=subprocess.STDOUT)
  try:
   for _ in range(100):
    if mapping.exists():break
    if native.poll() is not None:raise RuntimeError('Native input publisher failed; see '+str(native_log))
    time.sleep(.05)
   else:raise RuntimeError('Publisher not ready')
   print('REAL INPUT CAPTURE ACTIVE: wheel + pedals + buttons, no motor commands.',flush=True)
   stop_windows=winpath(stop_file)
   results.append(run([CX/'bin/wine','--bottle',BOTTLE,'--no-gui','--dll','dinput8=n,b',folder/'dinput-probe.exe','--until-stop',stop_windows],env,None))
   write_json(STATE/'real-input-progress.json',{'results':results})
  finally:
   if native.poll() is None:native.terminate()
   native.wait(timeout=5)
   if mapping.exists():mapping.unlink()
   directory.rmdir()
 text='\n'.join(r['stdout'] for r in results);ranges={}
 for k in ['x','y','rz','slider0']:
  data=[int(x) for x in re.findall(r'(?:^| )'+k+r'=(-?\d+)',text)]
  ranges[k]=[min(data),max(data)] if data else None
 buttons={int(x,16) for x in re.findall(r'buttons=([0-9a-fA-F]+)',text)}
 report={'physical_input_test':True,'via_virtual_dinput':True,'native_builtin_input_fixed':False,'sdk_or_ffb_test':False,'motor_output_sent_by_publisher':False,'ranges':ranges,'button_masks':sorted(buttons),'results':results}
 write_json(STATE/'real-input-runtime.json',report);print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
if __name__=='__main__':main()
