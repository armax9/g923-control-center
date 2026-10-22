#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay saved full-rate state through the production Swift evaluator. Offline only."""
import argparse,base64,bisect,collections,gzip,json,struct,subprocess
from pathlib import Path
STRIDE=4096
FORCE=3136

def analyze(capture,replay,output,motor_sign=-1,native_log=None):
    summary=json.loads((capture/'summary.json').read_text());tele=[]
    for line in (capture/'telemetry.jsonl').read_text().splitlines():
        row=json.loads(line);tele.append(row)
    tele.sort(key=lambda r:r['received_unix_ms']);times=[r['received_unix_ms'] for r in tele]
    actual=[]
    if native_log:
        for line in native_log.read_text(errors='replace').splitlines():
            try:r=json.loads(line)
            except ValueError:continue
            payload=r.get('payload',[])
            if r.get('event')=='classic_hid_output' and len(payload)>=3 and payload[0] in (0x11,0x1c) and r.get('unix_ms'):
                actual.append((r['unix_ms'],payload[2],r.get('status')))
    actual.sort();actual_times=[r[0] for r in actual]
    process=subprocess.Popen([str(replay),'--motor-sign',str(motor_sign)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
    count=below=invalid_input=condition=matched=unmatched=0;maximum=0.;old_tick=None;old_position=0.;mags=[]
    api_calls=collections.Counter();api_failures=collections.Counter()
    try:
        with gzip.open(capture/'frames.bin.gz','rb') as source,output.open('x') as target:
            while True:
                frame=source.read(STRIDE)
                if not frame:break
                if len(frame)!=STRIDE:raise ValueError('Truncated force frame')
                version,seq,stamp,tick=struct.unpack_from('<4Q',frame)
                force_len,input_len=struct.unpack_from('<2I',frame,32)
                if version!=seq*2 or force_len!=FORCE or input_len not in (0,48):raise ValueError('Invalid force frame')
                position=struct.unpack_from('<I',frame,64+FORCE+16)[0]/32767.5-1 if input_len else 0.
                invalid_input+=not input_len
                velocity=(position-old_position)/((tick-old_tick)/1000) if old_tick is not None and tick>old_tick else 0.
                old_position=position;old_tick=tick
                request=dict(sequence=seq,unix_ms=stamp,position=position,velocity=velocity,force_base64=base64.b64encode(frame[64:64+FORCE]).decode())
                process.stdin.write(json.dumps(request,separators=(',',':'))+'\n');process.stdin.flush()
                line=process.stdout.readline()
                if not line:raise RuntimeError('Offline evaluator exited')
                row=json.loads(line);row['position']=position
                operation,flags,slot,status=struct.unpack_from('<4I',frame,40)
                row['dinput_call']=dict(operation=operation,flags=flags,slot=slot,status_hex=f'{status:08x}')
                if operation:
                    api_calls[str(operation)]+=1
                    if status&0x80000000:api_failures[f'{operation}:{status:08x}']+=1
                i=bisect.bisect_right(times,stamp)-1
                row['telemetry']=tele[i] if i>=0 and stamp-times[i]<=500 else None
                row['native_byte_match_within_15ms']=None
                if actual:
                    left=bisect.bisect_left(actual_times,stamp);right=bisect.bisect_right(actual_times,stamp+15)
                    yes=any(code==row['classic_byte'] and status==0 for _,code,status in actual[left:right])
                    row['native_byte_match_within_15ms']=yes
                    matched+=yes;unmatched+=not yes
                row['native_match_limitation']='Coalesced/intermediate updates may have no matching HID write; byte match is not measured torque.'
                magnitude=abs(row['requested_force']);mags.append(magnitude);maximum=max(maximum,magnitude);below+=magnitude<.075;condition+=row['condition_kinematics_approximate'];count+=1
                target.write(json.dumps(row,separators=(',',':'))+'\n')
        process.stdin.close();code=process.wait(timeout=5)
        if code:raise RuntimeError(f'Evaluator exited {code}')
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=5)
        if process.stdout:process.stdout.close()
    mags.sort()
    result=dict(records=count,source_lost_records=summary['lost_records'],source_truncated=summary['recording_truncated'],max_requested=maximum,median_requested=mags[len(mags)//2] if mags else None,below_7_5_percent=below,input_snapshot_missing=invalid_input,condition_replay_approximate=condition,native_byte_matches=matched,native_byte_unmatched_or_coalesced=unmatched,api_calls=dict(api_calls),api_failures=dict(api_failures),hardware_playback_proven=False)
    output.with_suffix('.summary.json').write_text(json.dumps(result,indent=2)+'\n');return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,required=True);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--motor-sign',type=int,choices=[-1,1],default=-1);p.add_argument('--native-log',type=Path);a=p.parse_args();print(json.dumps(analyze(a.capture,a.replay,a.output,a.motor_sign,a.native_log),indent=2))
if __name__=='__main__':main()
