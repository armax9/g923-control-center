#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Opt-in trace for an executable in an owned diagnostic Wine prefix."""
import argparse,datetime,json,os,subprocess
from pathlib import Path
from trace_summary import summarize

def main():
 p=argparse.ArgumentParser();p.add_argument('--wine-build',type=Path,required=True);p.add_argument('--prefix',type=Path,required=True);p.add_argument('--exe',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--user-ready',action='store_true');p.add_argument('args',nargs=argparse.REMAINDER);a=p.parse_args()
 if not a.user_ready:raise SystemExit('Launching a game can activate forces; user readiness is required')
 prefix=a.prefix.resolve();marker=json.loads((prefix/'g923-owned-prefix.json').read_text())
 if marker.get('purpose')!='g923-isolated-wine-hid-experiment':raise SystemExit('Use only the owned experiment prefix')
 exe=a.exe.resolve(strict=True);exe.relative_to(prefix/'drive_c')
 a.output_dir.mkdir(parents=True,exist_ok=False)
 env=os.environ.copy();env.update(WINEPREFIX=str(prefix),WINEDEBUG='-all,+hid,+dinput,+loaddll',WINEDLLOVERRIDES='mscoree,mshtml=')
 meta={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'executable':str(exe),'prefix':str(prefix),'trace_channels':['hid','dinput','loaddll'],'sdk_calls_intercepted':False,'physical_playback_confirmed':False,'capture_end':'exit game normally; no user-response deadline'}
 (a.output_dir/'session.json').write_text(json.dumps(meta,indent=2)+'\n')
 with (a.output_dir/'stdout.txt').open('w') as out,(a.output_dir/'wine-trace.txt').open('w') as err:
  # Stream to disk, rather than retaining potentially huge HID traces in RAM.
  child=subprocess.Popen([str(a.wine_build.resolve()/'wine'),str(exe),*a.args],cwd=exe.parent,env=env,stdout=out,stderr=err)
  try:rc=child.wait()
  except KeyboardInterrupt:
   child.terminate();rc=child.wait();meta['interrupted']=True;meta['physical_stop_confirmed']=False
 meta.update(returncode=rc,ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 (a.output_dir/'session.json').write_text(json.dumps(meta,indent=2)+'\n')
 with (a.output_dir/'wine-trace.txt').open(errors='replace') as f:summary=summarize(f)
 (a.output_dir/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print('Saved session metadata, game stdout, Wine trace and evidence summary in',a.output_dir)
 return rc
if __name__=='__main__':raise SystemExit(main())
