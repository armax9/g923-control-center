#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Pinned original SDK, owned upstream Wine prefix; pulse is never the default."""
import argparse,hashlib,json,os,pathlib,signal,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[2]
HASH='2468bdafe64c09ff42ef26f09e49f2096321bb687467323aafb3f0672fb83315'
def execute(args,env,timeout):
 p=subprocess.Popen([str(x) for x in args],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
 try:out,err=p.communicate(timeout=timeout)
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGTERM)
  try:out,err=p.communicate(timeout=3)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);out,err=p.communicate()
  return {'returncode':124,'stdout':out,'stderr':err,'watchdog_triggered':True,'physical_stop_confirmed':False}
 return {'returncode':p.returncode,'stdout':out,'stderr':err,'watchdog_triggered':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--wine-build',type=pathlib.Path,required=True);p.add_argument('--prefix',type=pathlib.Path,required=True);p.add_argument('--sdk-dll',type=pathlib.Path,required=True);p.add_argument('--mode',choices=['plan','open','zero-mode','zero-buffer','pulse','pulse-detect','pulse-max'],default='plan');p.add_argument('--user-ready',action='store_true');p.add_argument('--stop-file',type=pathlib.Path);p.add_argument('--log',type=pathlib.Path,required=True);a=p.parse_args()
 prefix=a.prefix.resolve();dll=a.sdk_dll.resolve();build=a.wine_build.resolve()
 marker=json.loads((prefix/'g923-owned-prefix.json').read_text())
 if marker.get('purpose')!='g923-isolated-wine-hid-experiment':raise RuntimeError('Not an owned experiment prefix')
 if hashlib.sha256(dll.read_bytes()).hexdigest()!=HASH:raise RuntimeError('Unreviewed SDK bytes')
 relative=dll.relative_to(prefix/'drive_c');win_dll='C:'+chr(92)+str(relative).replace('/',chr(92))
 if a.mode in ['zero-mode','zero-buffer','pulse','pulse-detect','pulse-max'] and not a.user_ready:raise RuntimeError('User presence/readiness required')
 if a.mode in ['pulse','pulse-detect','pulse-max'] and (not a.stop_file or a.stop_file.exists()):raise RuntimeError('Supply a new stop-file path; existing stop requests are respected')
 env=os.environ.copy();env.update(WINEPREFIX=str(prefix),WINEDEBUG='-all,+hid',WINEDLLOVERRIDES='mscoree,mshtml=')
 probe=ROOT/'build/sdk-lab/sdk-probe.exe';exe=ROOT/'build/sdk-lab/sdk-session.exe';wine=build/'wine'
 if a.mode!='plan':
  v=execute([wine,probe,'--verify',win_dll],env,30)
  if v['returncode']!=0 or not any(json.loads(s).get('trusted_here') for s in v['stdout'].splitlines() if s.startswith('{')):raise RuntimeError('Signature not trusted in this runtime')
 if a.mode=='plan':args=['--dry-run']
 else:
  flag={'open':'--open-only','zero-mode':'--enable-tf-zero','zero-buffer':'--tf-zero-buffer','pulse':'--tf-pulse','pulse-detect':'--tf-pulse-detect','pulse-max':'--tf-pulse-max'}[a.mode];args=[flag,win_dll,'--initialize-sdk-1_3_12']
  if a.mode!='open':args+=['--user-ready']
  if a.mode in ['pulse','pulse-detect','pulse-max']:args+=['--stop-file','Z:'+str(a.stop_file.resolve()).replace('/',chr(92))]
 result=execute([wine,exe,*args],env,20 if a.mode in ['pulse','pulse-detect','pulse-max'] else 75)
 a.log.parent.mkdir(parents=True,exist_ok=True);a.log.write_text(json.dumps(result,indent=2)+'\n');print(result['stdout']);print('exit',result['returncode'],'watchdog',result['watchdog_triggered']);return result['returncode']
if __name__=='__main__':raise SystemExit(main())
