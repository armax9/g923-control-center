#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Explicit bounded physical sign measurement, never run by software tests."""
import argparse,json,pathlib,subprocess,time
from classic_log_summary import summarize
ROOT=pathlib.Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--output-dir',type=pathlib.Path,required=True);p.add_argument('--user-ready',action='store_true');p.add_argument('--stop-file',type=pathlib.Path,required=True);a=p.parse_args()
 if not a.user_ready or a.stop_file.exists():raise SystemExit('Fresh readiness and no pending stop request required')
 out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False);mapping=out/'ffb-v2.bin';child=None;timedout=False
 with (out/'native.jsonl').open('w') as log:
  child=subprocess.Popen([str(ROOT/'build/crossover-base/swift/debug/G923ClassicLab'),'--map',str(mapping),'--user-ready','--calibrate'],stdout=log,stderr=subprocess.STDOUT)
  try:
   deadline=time.monotonic()+10
   while child.poll() is None:
    if a.stop_file.exists() or time.monotonic()>deadline:
     timedout=True;child.terminate();break
    time.sleep(.01)
   try:rc=child.wait(timeout=5)
   except subprocess.TimeoutExpired:child.kill();rc=child.wait();timedout=True
  finally:
   if child.poll() is None:child.terminate();child.wait(timeout=5)
 lines=(out/'native.jsonl').read_text(errors='replace').splitlines();events=[]
 for l in lines:
  try:events.append(json.loads(l))
  except ValueError:pass
 summary=summarize(lines);(out/'native-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 result=next((e for e in events if e.get('event')=='motor_direction_result'),{})
 measured=next((e for e in events if e.get('event')=='motor_direction_measurement'),{})
 valid=rc==0 and not timedout and result.get('valid') and summary['hid_output_errors']==0 and summary['final_force_command_is_successful_stop'] and abs(measured.get('delta',0))>=150
 profile={'purpose':'g923-classic-physical-motor-sign','valid':bool(valid),'sign':result.get('sign'),'delta':measured.get('delta'),'command':0.12,'duration_ms':200,'process_exit':rc,'watchdog_or_stop':timedout,'cleanup':summary,'physical_dynamics_not_game_validated':True}
 (out/'motor-profile.json').write_text(json.dumps(profile,indent=2)+'\n');print(json.dumps(profile,indent=2));return 0 if valid else 1
if __name__=='__main__':raise SystemExit(main())
