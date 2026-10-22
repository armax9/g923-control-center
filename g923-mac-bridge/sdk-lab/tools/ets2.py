#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""ETS2 input, Force Feedback and telemetry-driven engine vibration."""
import argparse,datetime,hashlib,json,os,secrets,shutil,subprocess,time,struct,tempfile
from pathlib import Path
from game_sandbox import ROOT,windows
from installed_play import readiness
from game_settings import for_game, percentage
TOP=ROOT.parent.parent
# Legacy CLI default remains available until explicit bootstrap migration.
INSTALL=ROOT.parent/'G923 ETS2'
GAME=None
SOURCE_BOTTLE=None
RUNNER_PATH=None
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def game_directory(m):
 path=Path(m['game_exe'])
 if not path.is_absolute() or path.name.lower()!='eurotrucks2.exe':raise ValueError('Expected an absolute ETS2 executable path')
 return path.parent

def preserved_hash(game):
 path=game/'dinput8.dll'
 if path.is_symlink():raise ValueError('Inspect the existing dinput8 symlink before installation')
 return sha(path) if path.is_file() else None

def verify_preserved(m,game):
 if 'preserved_dlaa_sha' not in m:raise ValueError('Missing original dinput8 preservation record')
 if preserved_hash(game)!=m['preserved_dlaa_sha']:raise ValueError('Original dinput8 DLL changed; stopped for inspection')

def component_path(root,name):
 relative=Path(name)
 if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe component path: '+name)
 return root/relative

def state():
 global GAME
 m=json.loads((INSTALL/'manifest.json').read_text());GAME=game_directory(m)
 verify_preserved(m,GAME)
 for name,value in m.get('backend_hashes',{}).items():
  if sha(component_path(INSTALL,name))!=value:raise ValueError('Backend changed: '+name)
 for name,value in m['installed_files'].items():
  if sha(component_path(GAME,name))!=value:raise ValueError('Installed component changed: '+name)
 return m

def prepare():
 if INSTALL.exists():raise ValueError('ETS2 installation already staged')
 if GAME is None or not (GAME/'eurotrucks2.exe').is_file():raise ValueError('Provide --game-exe for the installed ETS2 executable')
 original_hash=preserved_hash(GAME)
 INSTALL.mkdir(parents=True);uid=secrets.randbelow(1000000000)+1000000000;mapping=f'/tmp/crossover-ffb-{uid}/ffb-v2.bin'
 raw=bytearray((ROOT/'build/crossover-base/dinput8.dll').read_bytes());marker=b'CFBUID=0\0';assert raw.count(marker)==1;i=raw.index(marker);raw[i:i+24]=('CFBUID='+str(uid)).encode().ljust(24,b'\0');(INSTALL/'g923_bridge.dll').write_bytes(raw)
 for src,name in [(ROOT/'build/winmm-chain/winmm.dll','winmm.dll'),(TOP/'outputs/mescon-telemetry/build/logi_tf_scs.dll','logi_tf_scs.dll'),(ROOT/'build/ets2-swift/debug/G923ClassicLab','G923TelemetryLab'),(TOP/'outputs/mescon-telemetry/build/mescon-synth','mescon-synth')]:shutil.copy2(src,INSTALL/name)
 if original_hash is not None:shutil.copy2(GAME/'dinput8.dll',INSTALL/'DLAA-dinput8-backup.dll')
 m={'mode':'mescon_telemetry_emulation','app_id':'227300','game_exe':str(GAME/'eurotrucks2.exe'),'preserved_dlaa_sha':original_hash,'source_bottle':str(SOURCE_BOTTLE) if SOURCE_BOTTLE else None,'runner_path':str(RUNNER_PATH) if RUNNER_PATH else None,'mapping':mapping,'installed_files':{},'game_settings_changed':False,'hardware_accepted':False,'native_tf_direction_measured':False,'synth':'Original mescon EngineSynth, GPL-2.0-only, separate UDP process','installed':False}
 (INSTALL/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print('ETS2 components prepared')

def install():
 processes=subprocess.run(['/bin/ps','-axo','comm='],capture_output=True,text=True,check=True).stdout
 if any(line.strip().lower().endswith('eurotrucks2.exe') for line in processes.splitlines()):raise ValueError('Close ETS2 first')
 global GAME
 m=json.loads((INSTALL/'manifest.json').read_text());GAME=game_directory(m);verify_preserved(m,GAME)
 targets={'winmm.dll':'winmm.dll','g923_bridge.dll':'g923_bridge.dll','logi_tf_scs.dll':'plugins/logi_tf_scs.dll'}
 for name in targets.values():
  if (GAME/name).exists():raise ValueError('Existing target: '+name)
 for source,target in targets.items():
  path=GAME/target;path.parent.mkdir(exist_ok=True);shutil.copy2(INSTALL/source,path);m['installed_files'][target]=sha(path);(INSTALL/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
 verify_preserved(m,GAME)
 m['installed']=True;(INSTALL/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print('Installed ETS2 bridge and SCS telemetry plugin')

def env(m=None):
 from portable_paths import bottle_environment
 m=m if m is not None else json.loads((INSTALL/'manifest.json').read_text())
 e=bottle_environment(m);e.update(SteamAppId='227300',SteamGameId='227300',G923_DINPUT_IAT='1',G923_SDK_TRACE='0');return e

def runtime_command(m=None):
 from portable_paths import wine_command
 m=m if m is not None else json.loads((INSTALL/'manifest.json').read_text())
 return wine_command(INSTALL,m)+['--no-gui','--debugmsg','-all']

def accepted_tf_direction(m):
 return bool(m.get('native_tf_direction_measured')) or (
  m.get('device_model')=='046d:c266' and m.get('tf_motor_sign')==1 and
  m.get('tf_motor_sign_source')=='G923 PlayStation protocol profile, hardware accepted 2026-10-22')

def calibrate(m):
 logdir=INSTALL/('direction-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'));logdir.mkdir()
 with (logdir/'native.jsonl').open('w') as log:
  p=subprocess.Popen([str(INSTALL/'G923TelemetryLab'),'--map',m['mapping'],'--user-ready','--mescon-audio','20781','--calibrate'],stdout=log,stderr=subprocess.STDOUT)
  try:p.wait(timeout=20)
  except (KeyboardInterrupt,subprocess.TimeoutExpired):
   p.terminate()
   try:p.wait(timeout=5)
   except subprocess.TimeoutExpired:p.kill();p.wait();raise RuntimeError('Motor stop not confirmed; disconnect wheel power if force persists')
   raise
 rows=[]
 for line in (logdir/'native.jsonl').read_text().splitlines():
  try:rows.append(json.loads(line))
  except ValueError:pass
 valid=next((x for x in rows if x.get('event')=='motor_direction_result' and x.get('valid') and x.get('via_trueforce')),None)
 cleaned=any(x.get('event')=='tf_cleanup' and x.get('zero_success') and x.get('stop_success') for x in rows)
 if p.returncode or not valid or not cleaned:raise ValueError('Direction/cleanup not verified; inspect '+str(logdir))
 m.update(native_tf_direction_measured=True,tf_motor_sign=valid['sign'],direction_log=str(logdir));(INSTALL/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print('Measured TF sign:',valid['sign'],'cleanup successful')

class EngineGainControl:
 """Translate validated UI preferences into one private synth control record.

 Only engine audio gain changes. This object never restarts or reconfigures the
 native FFB owner, and invalid/deleted preferences keep the last valid gain.
 """
 def __init__(self, settings_file, control_file, initial):
  self.settings_file=Path(settings_file);self.control_file=Path(control_file)
  self.gain=percentage(initial,'Engine vibration')/100;self.last_error=None
  self._write(self.gain)
 def _write(self,gain):
  record=json.dumps({'version':1,'intensity':gain},separators=(',',':'))+'\n'
  fd,temporary=tempfile.mkstemp(prefix='.engine-control-',dir=self.control_file.parent)
  try:
   with os.fdopen(fd,'w') as stream:stream.write(record);stream.flush();os.fsync(stream.fileno())
   os.replace(temporary,self.control_file)
  finally:Path(temporary).unlink(missing_ok=True)
 def update(self):
  try:
   if not self.settings_file.is_file():raise ValueError('Game settings are unavailable; keeping the last engine level')
   settings=for_game(227300,self.settings_file)
   gain=settings['engineVibration']/100 if settings['trueForceEnabled'] else 0
   if gain!=self.gain:
    self._write(gain);self.gain=gain
    print(json.dumps({'event':'engine_intensity','percent':round(gain*100,4),'live_update':True}),flush=True)
   self.last_error=None
  except (OSError,ValueError) as error:
   message=str(error)
   if message!=self.last_error:
    print(json.dumps({'event':'engine_control_warning','detail':message,'keeping_percent':round(self.gain*100,4)}),flush=True)
   self.last_error=message

def run(m, launch_game=True, classic_only=False, crossffb=False, engine_vibration=10, ffb_strength=100, settings_file=None):
 percentage(engine_vibration, 'Engine vibration');percentage(ffb_strength, 'FFB strength')
 live_settings=settings_file is not None and not classic_only
 if live_settings:
  settings=for_game(227300,settings_file)
  engine_vibration=settings['engineVibration'] if settings['trueForceEnabled'] else 0
 classic_only = classic_only or (engine_vibration == 0 and not live_settings)
 if crossffb and (not classic_only or launch_game):raise ValueError("CrossFFB candidate requires manual, classic-only mode")
 if not classic_only and not accepted_tf_direction(m):raise ValueError('Run the short TF motor direction check first.')
 # Standalone manual FFB never needs the SDK installation or a Wine process.
 if launch_game:
  command=runtime_command(m);e=env(m)

  print('Waiting for Steam. Sign in if needed; there is no sign-in timeout.',flush=True)
  started=False
  while True:
   try:
    check=subprocess.run(command+[str(ROOT/'build/sdk-lab/steam-ready.exe'),windows(GAME/'steam_api64.dll')],env=e,cwd=GAME,capture_output=True,text=True,timeout=40)
    ready=readiness(check.stdout)
   except subprocess.TimeoutExpired:ready={}
   if ready.get('initialized'):break
   if not started and ready.get('client_running') is not True:
    bottle=Path(m['source_bottle'])
    with (INSTALL/'steam-startup.log').open('a') as log:
     steam_exe=m.get('steam_exe')
     if not steam_exe or not Path(steam_exe).is_file():raise ValueError('Open Steam yourself; the prepared profile has no detected Steam executable')
     subprocess.Popen(command+[str(steam_exe)],env={k:v for k,v in e.items() if k not in ('SteamAppId','SteamGameId')},stdout=log,stderr=log)
    started=True
   time.sleep(3)

 logdir=INSTALL/('run-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'));logdir.mkdir();stop=INSTALL/'stop';stop.unlink(missing_ok=True);children=[];files=[]
 try:
  def launch(name,args,**kwargs):
   log=(logdir/(name+'.log')).open('w');files.append(log);p=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,**kwargs);children.append(p);return p
  control=EngineGainControl(settings_file,logdir/'engine-control.json',engine_vibration) if live_settings else None
  synth_args=[str(INSTALL/'mescon-synth'),'--intensity',str(engine_vibration / 100),'--cylinders','6']
  if control:synth_args+=['--control-file',str(control.control_file)]
  synth=None if classic_only else launch('synth',synth_args)
  image=INSTALL/('G923CrossFFBLab' if crossffb else 'G923TelemetryLab')
  if crossffb:
   candidate=json.loads((INSTALL/'crossffb-candidate.json').read_text())
   if sha(image)!=candidate['sha256']:raise ValueError('CrossFFB candidate changed')
  args=[str(image),'--map',m['mapping'],'--user-ready','--motor-sign','-1','--all-effects','--strength',format(ffb_strength / 100, 'g'),'--max-force','1']
  if crossffb:args+=['--crossffb-classic']
  if not classic_only:args+=['--tf-motor-sign',str(int(m['tf_motor_sign'])),'--mescon-audio','20781']
  native=launch('native',args)
  deadline=time.monotonic()+15
  while True:
   if native.poll() is not None or (synth is not None and synth.poll() is not None):raise ValueError('Backend failed; inspect log')
   mapping=Path(m['mapping'])
   if mapping.is_file():
    with mapping.open('rb') as f:header=f.read(104)
    if len(header)>=80 and struct.unpack_from('<I',header,68)[0]==1 and abs(time.time()*1000-struct.unpack_from('<Q',header,72)[0])<500:break
   if time.monotonic()>deadline:raise ValueError('Fresh connected input bridge not ready')
   time.sleep(.1)
  if launch_game:launch('game',command+['--dll','winmm=n,b;dinput8=n,b',str(GAME/'eurotrucks2.exe'),'-rdevice','dx11'],env=e,cwd=GAME)
  if not launch_game:print('BRIDGE_LISTENING: Start ETS2 yourself from Steam. Waiting for the game bridge; VR mode is your choice.',flush=True)
  print('ETS2 transport: '+('classic FFB only (engine emulation disabled)' if classic_only else 'combined FFB + mescon engine emulation'),flush=True)
  print('ETS2: telemetry emulation is not native game TRUEFORCE.\nGame force gain '+str(ffb_strength)+'%; full device range; no experimental force ceiling. Engine emulation '+('disabled' if classic_only else 'enabled at '+str(engine_vibration)+'%')+'. Game settings are unchanged.\nStop: use the stop button in G923 Control Center. Logs: '+str(logdir),flush=True)
  from ets2_connection import ConnectionMonitor
  monitor=ConnectionMonitor();positions={};next_status=0
  while not stop.exists():
   if control:control.update()
   if time.monotonic()>=next_status:
    next_status=time.monotonic()+1
    for name in ['native','synth']:
     path=logdir/(name+'.log')
     if not path.exists():continue
     with path.open(errors='replace') as source:
      source.seek(positions.get(name,0))
      for line in source:monitor.feed(line)
      positions[name]=source.tell()
    message=monitor.message()
    if message:print(message,flush=True)
   if (synth is not None and synth.poll() is not None) or native.poll() is not None:raise RuntimeError('A backend exited')
   time.sleep(.1)
 finally:
  # Motor owner stops first and sends neutral samples + stop. Never kill Steam/game.
  for child in reversed(children[:2]):
   if child.poll() is None:
    child.terminate()
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:child.kill();child.wait()
  for f in files:f.close()

def main():
 global INSTALL,GAME,SOURCE_BOTTLE,RUNNER_PATH
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','install','uninstall','check','calibrate','start','stop']);p.add_argument('--user-ready',action='store_true');p.add_argument('--manual',action='store_true');p.add_argument('--engine-vibration',type=float);p.add_argument('--ffb-strength',type=float);p.add_argument('--settings-file',type=Path);p.add_argument('--installation',type=Path);p.add_argument('--registry',type=Path);p.add_argument('--profile-id');p.add_argument('--game-exe',type=Path);p.add_argument('--source-bottle',type=Path);p.add_argument('--runner-path',type=Path);mode=p.add_mutually_exclusive_group();mode.add_argument('--classic-only',action='store_true');mode.add_argument('--engine-emulation',action='store_true');p.add_argument('--crossffb-classic',action='store_true');a=p.parse_args()
 if a.installation is not None:INSTALL=a.installation.resolve();GAME=None
 elif a.action!='prepare':
  from profile_store import load_registry,select_profile
  registry=load_registry(a.registry)
  from profile_store import default_registry_path
  if registry['profiles'] or a.registry is not None or default_registry_path().exists():
   profile=select_profile(227300,registry,profile_id=a.profile_id);INSTALL=Path(profile['session_dir']);GAME=None
 if a.game_exe is not None:GAME=a.game_exe.resolve().parent
 SOURCE_BOTTLE=a.source_bottle.resolve() if a.source_bottle else None
 RUNNER_PATH=a.runner_path.resolve() if a.runner_path else None
 if a.action=='prepare':return prepare()
 if a.action=='install':return install()
 if a.action=='uninstall':
  processes=subprocess.check_output(['/bin/ps','-axo','comm='],text=True)
  if any(x.strip().lower().endswith('eurotrucks2.exe') for x in processes.splitlines()):raise ValueError('Close ETS2 before removing the bridge')
  m=json.loads((INSTALL/'manifest.json').read_text());GAME=game_directory(m);verify_preserved(m,GAME)
  for name,value in m['installed_files'].items():
   path=component_path(GAME,name)
   if path.exists() and sha(path)!=value:raise ValueError('File modified externally: '+name)
  if m.get('manual_chain'):
   from ets2_manual import restore
   restore(m)
  for name in m['installed_files']:component_path(GAME,name).unlink(missing_ok=True)
  m['installed']=False;(INSTALL/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print('ETS2 bridge components removed');return
 if a.action=='stop':(INSTALL/'stop').touch();print('ETS2 bridge stop requested');return
 m=state()
 if a.action=='check':print('ETS2 installation verified');return
 if not a.user_ready:p.error('Explicit user readiness required for motor/game')
 if a.action=='calibrate':return calibrate(m)
 settings=for_game(227300,a.settings_file)
 vibration=settings['engineVibration'] if a.engine_vibration is None else percentage(a.engine_vibration,'Engine vibration')
 strength=settings['ffbStrength'] if a.ffb_strength is None else percentage(a.ffb_strength,'FFB strength')
 classic_only=a.classic_only or (not a.engine_emulation and not settings['trueForceEnabled'])
 try:return run(m,launch_game=not a.manual,classic_only=classic_only,crossffb=a.crossffb_classic,engine_vibration=vibration,ffb_strength=strength,settings_file=a.settings_file)
 except KeyboardInterrupt:print('Stopped')
if __name__=='__main__':main()
