#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Summarize Wine traces, preserving the difference between requests and playback."""
import argparse,collections,json,re
from pathlib import Path

def summarize(lines):
 counts=collections.Counter();commands=collections.Counter();pending={};g923=set();sdk_modules=set()
 for line in lines:
  m=re.search(r'([0-9a-f]+):trace:hid:hid_internal_dispatch write output report id',line)
  if m:counts['hid_output_requests']+=1;pending[m[1]]=bytearray();continue
  m=re.search(r'([0-9a-f]+):trace:hid:hid_internal_dispatch ([0-9a-f]{8})  ((?:[0-9a-f]{2} ?)+)',line)
  if m and m[1] in pending:
   b=pending[m[1]];off=int(m[2],16)
   if len(b)!=off:del pending[m[1]];counts['incomplete_or_out_of_order_dumps']+=1;continue
   b.extend(bytes.fromhex(m[3]))
   if len(b)==64:
    counts['complete_64byte_output_reports']+=1
    if b[0]==1:commands[str(b[4])]+=1
    del pending[m[1]]
  if ':trace:hid:deliver_next_report ' in line and 'input report length' in line:counts['hid_input_deliveries']+=1
  if ':trace:dinput:' in line:
   for key in ['CreateEffect','SetParameters','Start','Stop','SendForceFeedbackCommand']:
    # Match function name, not an incidental mention in payload.
    m=re.search(r':trace:dinput:([^\s:]+)',line)
    if m and m[1].lower().endswith(key.lower()) and (key not in ['Start','Stop','SetParameters'] or 'effect' in m[1].lower()):counts['dinput_'+key+'_requests']+=1
  if 'trueforce_sdk' in line.lower() and ':loaddll:' in line:sdk_modules.add('trueforce_sdk module mentioned by Wine loader')
  if 'vid_046d' in line.lower() and any(x in line.lower() for x in ['pid_c266','pid_c267']):g923.add('G923 path mentioned')
 counts['unfinished_dumps_at_end']=len(pending)
 return {'observations':dict(counts),'report_id_1_byte_4_histogram':dict(commands),'loader_observations':sorted(sdk_modules),'device_observations':sorted(g923),'interpretation':{'dinput_events':'requests, not confirmed device actuation','hid_reports':'Wine output requests; may include other devices and cannot alone prove hardware delivery or vibration','command_histogram':'raw byte classification only; not an SDK protocol decoder','sdk_calls':'not intercepted by this tracer; module load does not prove native TRUEFORCE use','physical_playback':'requires separate user observation or independent measurement'}}

def main():
 p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 with a.trace.open(errors='replace') as f:r=summarize(f)
 a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
