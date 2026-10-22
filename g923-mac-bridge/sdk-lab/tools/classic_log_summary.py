#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
import argparse,json
from pathlib import Path

def summarize(lines):
 writes=[];snapshots=[];invalid=0
 for line in lines:
  try:v=json.loads(line)
  except ValueError:invalid+=1;continue
  if v.get('event')=='classic_hid_output':writes.append(v)
  if v.get('event')=='force_snapshot':snapshots.append(v)
 forces=[v for v in writes if v.get('payload') and v['payload'][0] in [0x11,0xf3]]
 return {'hid_output_count':len(writes),'hid_output_errors':sum(v['status']!=0 for v in writes),'nonzero_constant_requests':sum(v.get('payload',[0])[0]==0x11 and len(v['payload'])>=3 and v['payload'][2]!=128 for v in writes),'live_effect_snapshot_seen':any(any(e.get('playing') for e in s.get('effects',[])) for s in snapshots),'nonzero_computed_output_seen':any(abs(s.get('output',0))>0 for s in snapshots),'final_force_command_is_successful_stop':bool(forces and forces[-1]['payload'][0]==0xf3 and forces[-1]['status']==0),'non_json_lines':invalid,'physical_playback_confirmed':False,'limitation':'IOKit success confirms API return only; physical effect requires user confirmation. Shutdown timeout is separate.'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('log',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 with a.log.open(errors='replace') as f:r=summarize(f)
 a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
