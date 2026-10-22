#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Opt-in logging for a user-selected existing CrossOver bottle. No DLL installation."""
import argparse,datetime,json,os,subprocess
from pathlib import Path
from trace_summary import summarize

def main():
 p=argparse.ArgumentParser();p.add_argument('--crossover-app',type=Path,required=True);p.add_argument('--bottle',required=True);p.add_argument('--exe',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--user-ready',action='store_true');p.add_argument('--via-steam',action='store_true');p.add_argument('--app-id',type=int,default=690790);a=p.parse_args()
 if not a.user_ready:raise SystemExit('Game may activate wheel forces; wait for user readiness')
 bottle=Path.home()/'Library/Application Support/CrossOver/Bottles'/a.bottle
 if not bottle.is_dir() or Path(a.bottle).name!=a.bottle:raise SystemExit('Existing named bottle required')
 exe=a.exe.resolve(strict=True);wine=(a.crossover_app/'Contents/SharedSupport/CrossOver/bin/wine').resolve(strict=True)
 a.output_dir.mkdir(parents=True,exist_ok=False)
 env=os.environ.copy();env.update(WINEDEBUG='-all,+hid,+dinput,+loaddll',CX_DEBUGMSG='-all,+hid,+dinput,+loaddll',SteamAppId=str(a.app_id),SteamGameId=str(a.app_id))
 steam=bottle/'drive_c/Program Files (x86)/Steam/steam.exe'
 if a.via_steam and not steam.is_file():raise SystemExit('Steam executable missing')
 launch=[str(steam),'-applaunch',str(a.app_id)] if a.via_steam else [str(exe)]
 metadata={'via_steam':a.via_steam,'app_id':a.app_id if a.via_steam else None,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runtime':str(a.crossover_app),'bottle':a.bottle,'exe':str(exe),'settings_or_dlls_installed':False,'sdk_calls_intercepted':False,'physical_playback_confirmed':False,'note':'Direct launch may be redirected by Steam. Validate game module presence in trace; no trace does not mean no effects.'}
 save=lambda:(a.output_dir/'session.json').write_text(json.dumps(metadata,indent=2)+'\n')
 save()
 with (a.output_dir/'stdout.txt').open('w') as out,(a.output_dir/'wine-trace.txt').open('w') as err:
  child=subprocess.Popen([str(wine),'--bottle',a.bottle,'--debugmsg','-all,+hid,+dinput,+loaddll','--wait-children',*launch],cwd=exe.parent,env=env,stdout=out,stderr=err)
  try:rc=child.wait()
  except KeyboardInterrupt:
   child.terminate();rc=child.wait();metadata.update(interrupted=True,physical_stop_confirmed=False)
 metadata.update(returncode=rc,ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save()
 with (a.output_dir/'wine-trace.txt').open(errors='replace') as f:report=summarize(f)
 (a.output_dir/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
 print('Recorded',a.output_dir);return rc
if __name__=='__main__':raise SystemExit(main())
