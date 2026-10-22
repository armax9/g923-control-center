#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolated SDK bring-up lab. No game modification; no SDK API or motor calls."""
import argparse,datetime,hashlib,json,os,pathlib,re,shutil,subprocess,sys,signal
from pe_inventory import inspect,PEError
ROOT=pathlib.Path(__file__).resolve().parents[2]
STATE=(ROOT.parents[1]/'work/sdk-lab') if ROOT.parent.name=='outputs' and (ROOT.parents[1]/'work').is_dir() else ROOT/'work/sdk-lab'
BOTTLE='G923SDKLab'
TF_CLSID='{e8dfb59f-141f-40e4-8dd4-5526ead25a4c}'
WHEEL_CLSID='{63bd165d-1584-4e75-ab56-08330350545f}'
NAMES={'trueforce':'trueforce_sdk_x64.dll','wheel':'logi_steering_wheel_x64.dll'}
REQUIRED={'trueforce':{'logiWheelOpenByDirectInputA','logiTrueForceAvailable','logiTrueForceSetStreamTF'},'wheel':{'LogiSteeringInitialize','LogiUpdate'}}
def usable(candidate):
 names={e['name'] for e in candidate['pe']['exports']}
 return candidate['pe']['x64'] and REQUIRED[candidate['kind']]<=names
def write_json(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def winpath(path):return 'Z:'+str(pathlib.Path(path).resolve()).replace('/','\\')
def run(argv,env=None,timeout=60):
 process=subprocess.Popen([str(x) for x in argv],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,errors='replace',start_new_session=True)
 try:
  stdout,stderr=process.communicate(timeout=timeout)
  return {'returncode':process.returncode,'stdout':stdout,'stderr':stderr}
 except subprocess.TimeoutExpired:
  try:os.killpg(process.pid,signal.SIGTERM)
  except ProcessLookupError:pass
  try:stdout,stderr=process.communicate(timeout=3)
  except subprocess.TimeoutExpired:
   try:os.killpg(process.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   stdout,stderr=process.communicate()
  return {'returncode':124,'stdout':stdout,'stderr':stderr+'\nTimed out; only this probe process group terminated.'}
def events(result):
 out=[]
 for line in result['stdout'].splitlines():
  try:out.append(json.loads(line))
  except ValueError:pass
 return out
def sdk_inventory(roots):
 candidates=[];errors=[]
 for root in roots:
  if not root.exists():continue
  for name in NAMES.values():
   # A bounded, named root is required; never traverse the whole home directory.
   for f in root.rglob(name):
    if not f.is_file():continue
    try:candidates.append({'path':str(f.resolve()),'kind':next(k for k,v in NAMES.items() if v==f.name),'pe':inspect(f)})
    except (OSError,PEError) as e:errors.append({'path':str(f),'error':str(e)})
 return {'candidates':candidates,'errors':errors}
def registry_text(tf_path=None,wheel_path=None):
 def value(s):
  if '\n' in s or '\r' in s:raise ValueError('newline in registry value')
  return '"'+s.replace('\\','\\\\').replace('"','\\"')+'"'
 blocks=['Windows Registry Editor Version 5.00','']
 if tf_path:
  key='HKEY_LOCAL_MACHINE\\SOFTWARE\\Classes\\CLSID\\'+TF_CLSID
  blocks += ['['+key+']','@='+value(tf_path),'','['+key+'\\InprocServer32]','@='+value(tf_path),'"ThreadingModel"="Both"','']
 if wheel_path:blocks += ['[HKEY_LOCAL_MACHINE\\SOFTWARE\\Classes\\CLSID\\'+WHEEL_CLSID+'\\ServerBinary]','@='+value(wheel_path),'']
 return '\r\n'.join(blocks)+'\r\n'
def owned_lab():
 STATE.mkdir(parents=True,exist_ok=True);marker=STATE/'owner.json'
 expected={'purpose':'g923-sdk-lab','project':str(ROOT)}
 if marker.exists():
  if json.loads(marker.read_text())!=expected:raise RuntimeError('Lab ownership marker mismatch')
 else:
  if (STATE/'bottles').exists():raise RuntimeError('Unmarked bottles directory: refusing adoption')
  write_json(marker,expected)
 return STATE/'bottles'
def ensure_bottle(cx):
 bottles=owned_lab();bottles.mkdir(exist_ok=True);bottle=bottles/BOTTLE
 env=os.environ.copy();env['CX_BOTTLE_PATH']=str(bottles)
 if not bottle.exists():
  result=run([cx/'bin/cxbottle','--bottle',BOTTLE,'--create','--template','win10_64','--description','Private G923 SDK diagnostics; no games'],env,60)
  write_json(STATE/'bottle-create.json',result)
  if result['returncode']:raise RuntimeError('Isolated bottle creation failed; see work/sdk-lab/bottle-create.json')
 if not (bottle/'cxbottle.conf').exists():raise RuntimeError('Incomplete lab bottle: cxbottle.conf missing')
 return bottle,env
def wine(cx,env,args,debug=False):
 command=[cx/'bin/wine','--bottle',BOTTLE,'--no-gui']
 if debug:command+=['--debugmsg','+loaddll,+hid,+dinput,+ole,+setupapi']
 return run(command+args,env,45)
def default_roots():
 return [pathlib.Path('/Applications/lghub.app'),pathlib.Path.home()/'Library/Application Support/lghub',pathlib.Path.home()/'Library/Application Support/CrossOver/Bottles']
def preflight(cx,roots,game=None):
 inv=sdk_inventory(roots)
 available={x['kind'] for x in inv['candidates'] if usable(x)}
 report={'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'purpose':'native SDK preparation, not TRUEFORCE validation','sdk_inventory':inv,'sdk_missing':sorted(set(NAMES)-available),'probe_built':(ROOT/'build/sdk-lab/sdk-probe.exe').exists(),'crossOver_version':run([cx/'bin/wine','--version']) if (cx/'bin/wine').exists() else None,'hardware_tested':False,'sdk_api_invoked':False,'synthesis_is_native':False}
 if game:
  report['game_static']=inspect(game)
  real_names={e['name'] for c in inv['candidates'] if c['kind']=='trueforce' for e in c['pe']['exports']}
  refs=report['game_static']['logitech_string_candidates']
  report['game_candidate_symbols_missing_in_found_sdk']=[s for s in refs if real_names and s not in real_names]
  report['game_note']='String match only. Dynamic module paths, packed games and GetProcAddress may need runtime logs.'
 return report
def offline(cx):
 _,env=ensure_bottle(cx);exe=ROOT/'build/sdk-lab/sdk-probe.exe';dll=ROOT/'build/sdk-lab/fixture-not-logitech.dll'
 if not exe.exists() or not dll.exists():raise RuntimeError('Run sdk-lab/build.sh first')
 sentinel=STATE/'fixture-dllmain.txt'
 if sentinel.exists():sentinel.unlink()
 env['G923_FIXTURE_SENTINEL']=winpath(sentinel)
 report={'fixture_only':True,'real_logitech_sdk_tested':False,'hardware_tested':False,'cases':{}}
 cases=report['cases']
 cases['invalid_load_without_optin']=wine(cx,env,[exe,'--load',winpath(dll)])
 assert cases['invalid_load_without_optin']['returncode']==2
 assert not sentinel.exists(),'DllMain ran without explicit opt-in'
 cases['signature_unsigned_fixture']=wine(cx,env,[exe,'--verify',winpath(dll)])
 assert cases['signature_unsigned_fixture']['returncode']==4
 assert any(e.get('event')=='signature' and e.get('trusted_here') is False for e in events(cases['signature_unsigned_fixture']))
 cases['missing_dll']=wine(cx,env,[exe,'--load',winpath(STATE/'missing.dll'),'--execute-dllmain'])
 assert cases['missing_dll']['returncode']==5
 cases['fixture_load']=wine(cx,env,[exe,'--load',winpath(dll),'--execute-dllmain'])
 assert cases['fixture_load']['returncode']==0
 assert sentinel.read_text()=='FIXTURE_ONLY_DLLMAIN_EXECUTED\n'
 looked={e['name']:e['present'] for e in events(cases['fixture_load']) if e.get('event')=='export_lookup'}
 assert looked.get('g923_fixture_probe') is True and looked.get('logiTrueForceAvailable') is False
 # Default probe reads registry and HID attributes only; no registration/API/motor calls.
 original=wine(cx,env,[exe]);cases['inventory']=original
 assert original['returncode']==0
 report['pass']=True;write_json(STATE/'offline-runtime.json',report);return report

def stage(cx,roots):
 # Private stage only; do not execute SDK, regsvr32, or import registration here.
 bottle,_=ensure_bottle(cx);inventory=sdk_inventory(roots);chosen={}
 for kind,name in NAMES.items():
  valid=[c for c in inventory['candidates'] if c['kind']==kind and usable(c)]
  def version(c):return tuple(int(n) for n in re.findall(r'\d+',pathlib.Path(c['path']).parent.name))
  valid.sort(key=version)
  if not valid:continue
  c=valid[-1];source=pathlib.Path(c['path']);version_name=source.parent.name
  if not re.fullmatch(r'\d+(?:_\d+)*',version_name):raise RuntimeError('Keep original version folder, e.g. Logi/Trueforce/1_3_11')
  folder=pathlib.Path('Program Files/Logi')/('Trueforce' if kind=='trueforce' else 'wheel_sdk')/version_name
  target=bottle/'drive_c'/folder/name;target.parent.mkdir(parents=True,exist_ok=True)
  if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=c['pe']['sha256']:raise RuntimeError('Conflicting staged DLL: refusing overwrite')
  if not target.exists():shutil.copy2(source,target)
  chosen[kind]={'windows_path':'C:\\'+str(folder/name).replace('/','\\'),'sha256':c['pe']['sha256'],'version':version_name}
 reg=registry_text(chosen.get('trueforce',{}).get('windows_path'),chosen.get('wheel',{}).get('windows_path'))
 (STATE/'register-sdk.reg').write_bytes(reg.encode('utf-16'))
 report={'chosen':chosen,'missing':sorted(set(NAMES)-set(chosen)),'registration_applied':False,'sdk_loaded':False,'private_files_in_archive':False}
 write_json(STATE/'stage.json',report);return report

def check_staged(cx,execute=False):
 bottle,env=ensure_bottle(cx)
 manifest=STATE/'stage.json'
 if not manifest.exists():raise RuntimeError('Stage owned SDK files first')
 chosen=json.loads(manifest.read_text())['chosen']
 if 'trueforce' not in chosen:raise RuntimeError('Real TRUEFORCE SDK missing; fixture cannot replace it')
 report={'executed_dllmain':False,'sdk_api_invoked_by_probe':False,'files':{}}
 for kind,entry in chosen.items():
  windows=entry['windows_path'];parts=pathlib.PureWindowsPath(windows)
  if parts.drive.upper()!='C:' or '..' in parts.parts:raise RuntimeError('Invalid staged path')
  file=(bottle/'drive_c').joinpath(*parts.parts[1:]).resolve()
  if not file.is_relative_to((bottle/'drive_c').resolve()):raise RuntimeError('Staged path escapes lab')
  if hashlib.sha256(file.read_bytes()).hexdigest()!=entry['sha256']:raise RuntimeError('Staged file changed: restage/review first')
  report['files'][kind]={'signature':wine(cx,env,[ROOT/'build/sdk-lab/sdk-probe.exe','--verify',windows])}
 write_json(STATE/'signature-real-sdk.json',report)
 if execute:
  if any(c['signature']['returncode']!=0 for c in report['files'].values()):raise RuntimeError('Signature check did not pass; no DLL executed. Diagnose trust/provenance with user present.')
  # Exactly one fresh process; no registered game/bottle is changed.
  report['loader']=wine(cx,env,[ROOT/'build/sdk-lab/sdk-probe.exe','--load',chosen['trueforce']['windows_path'],'--execute-dllmain'],True)
  report['initialization_attempted']=True
  report['executed_dllmain']=True if report['loader']['returncode']==0 else None
 write_json(STATE/('loader-real-sdk.json' if execute else 'signature-real-sdk.json'),report)
 return report

def availability_staged(cx):
 bottle,env=ensure_bottle(cx)
 manifest=json.loads((STATE/'stage.json').read_text())
 entry=manifest.get('chosen',{}).get('trueforce',{})
 expected='2468bdafe64c09ff42ef26f09e49f2096321bb687467323aafb3f0672fb83315'
 if entry.get('version')!='1_3_12' or entry.get('sha256')!=expected:raise RuntimeError('Availability ABI is verified only for our exact signed SDK 1.3.12 x64; refusing another binary')
 file=bottle/'drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll'
 if hashlib.sha256(file.read_bytes()).hexdigest()!=expected:raise RuntimeError('SDK bytes changed')
 verify=wine(cx,env,[ROOT/'build/sdk-lab/sdk-probe.exe','--verify',entry['windows_path']])
 if verify['returncode']!=0:raise RuntimeError('Signature verification failed; no SDK initialization')
 result=wine(cx,env,[ROOT/'build/sdk-lab/sdk-probe.exe','--availability',entry['windows_path'],'--initialize-sdk-1_3_12'],True)
 report={'purpose':'Real SDK initialization and availability, not torque/stream playback','torque_api_calls':0,'result':result}
 write_json(STATE/'availability-real-sdk.json',report)
 return report

def collect(cx,roots,game):
 report=preflight(cx,roots,game);_,env=ensure_bottle(cx)
 report['windows_inventory']=wine(cx,env,[ROOT/'build/sdk-lab/sdk-probe.exe'],True)
 report['mac_hid']=run([ROOT/'build/g923-hid']) if (ROOT/'build/g923-hid').exists() else {'missing_binary':True}
 probe=ROOT/'build/windows/dinput-probe.exe'
 if probe.exists():report['dinput_builtin']=wine(cx,env,['--dll','dinput8=b',probe],True)
 report['next']='User presence: provide owned SDK DLLs if missing; connect powered G923; decide Input Monitoring if denied. No motor commands in collection.'
 write_json(STATE/'collection.json',report);return report

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['preflight','offline','stage','collect','verify-staged','load-staged','availability-staged']);p.add_argument('--crossover-app','--crossOver',dest='crossover_app',type=pathlib.Path,default=pathlib.Path('/Applications/CrossOver.app'));p.add_argument('--sdk-dir',action='append',type=pathlib.Path);p.add_argument('--game-exe',type=pathlib.Path);p.add_argument('--execute-dllmain',action='store_true');a=p.parse_args()
 cx=a.crossover_app/'Contents/SharedSupport/CrossOver';roots=a.sdk_dir if a.sdk_dir else default_roots()
 if not (cx/'bin/wine').is_file():p.error('CrossOver launcher missing at selected application')
 try:
  if a.action=='preflight':result=preflight(cx,roots,a.game_exe);write_json(STATE/'preflight.json',result)
  elif a.action=='offline':result=offline(cx)
  elif a.action=='stage':result=stage(cx,roots)
  elif a.action=='verify-staged':result=check_staged(cx)
  elif a.action=='availability-staged':
   if not a.execute_dllmain:raise RuntimeError('Availability initializes real SDK; user must be present. Explicit --execute-dllmain needed.')
   result=availability_staged(cx)
  elif a.action=='load-staged':
   if not a.execute_dllmain:raise RuntimeError('Load runs SDK initialization; user presence required. Explicit --execute-dllmain needed.')
   result=check_staged(cx,True)
  else:result=collect(cx,roots,a.game_exe)
  print(json.dumps(result,ensure_ascii=False,indent=2))
 except (OSError,PEError,ValueError,RuntimeError,AssertionError) as e:p.exit(1,'SDK lab: '+str(e)+'\n')
if __name__=='__main__':main()
