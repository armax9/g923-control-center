#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only force/telemetry collector. Never opens HID, SDK, Steam or a game."""
import argparse,ctypes,gzip,json,math,mmap,os,signal,socket,stat,struct,time
from pathlib import Path
MAGIC=0x52543947
SLOTS=128
STRIDE=4096
HEADER=64
SIZE=HEADER+SLOTS*STRIDE
FORCE_BYTES=3136
INPUT_BYTES=48
# An acquire fence is required around copies on Apple Silicon.
_barrier=ctypes.CDLL('/usr/lib/libSystem.B.dylib').OSMemoryBarrier
_barrier.argtypes=[]
_barrier.restype=None

def drain(memory,after):
    if struct.unpack_from('<4I',memory)!= (MAGIC,1,SLOTS,STRIDE):raise ValueError('Invalid force trace mapping')
    latest=struct.unpack_from('<Q',memory,16)[0];_barrier()
    if latest<after:raise ValueError('Trace producer reset during capture')
    first=max(after+1,latest-SLOTS+1);lost=max(0,first-after-1);rows=[]
    for sequence in range(first,latest+1):
        offset=HEADER+(sequence-1)%SLOTS*STRIDE
        before=struct.unpack_from('<Q',memory,offset)[0];_barrier()
        if before!=sequence*2:lost+=1;continue
        row=bytes(memory[offset:offset+STRIDE]);_barrier()
        if struct.unpack_from('<Q',memory,offset)[0]!=before or struct.unpack_from('<Q',row,8)[0]!=sequence:
            lost+=1;continue
        if struct.unpack_from('<I',row,32)[0]!=FORCE_BYTES:raise ValueError('Trace record layout changed')
        rows.append(row)
    return rows,latest,lost

def telemetry(packet):
    if len(packet)<28 or packet[:4]!=b'LTFR' or packet[4]!=2:return None
    rpm,maximum,throttle=struct.unpack_from('<3f',packet,14)
    speed,brake=struct.unpack_from('<2f',packet,32) if len(packet)>=40 else (None,None)
    values=[rpm,maximum,throttle]+([speed,brake] if speed is not None else [])
    if not all(math.isfinite(v) for v in values):return None
    return dict(game=packet[6:14].rstrip(b'\0').decode('ascii',errors='replace'),rpm=rpm,max_rpm=maximum,throttle=throttle,
                gear=struct.unpack_from('<h',packet,26)[0],speed_mps=speed,brake=brake,
                engine_running_measured=False) # RPM is not the engine-enabled boolean channel.

def create_ring(path):
    parent=path.parent
    parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    info=parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
        raise ValueError('Trace directory must be owned and mode0700')
    fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        os.ftruncate(fd,SIZE);memory=mmap.mmap(fd,SIZE)
        struct.pack_into('<4I',memory,0,MAGIC,1,SLOTS,STRIDE)
        return memory,os.fstat(fd).st_ino
    finally:os.close(fd)

def collect(path,output,stop,telemetry_port=None,forward_port=None,max_bytes=2*1024*1024*1024):
    if forward_port and (not telemetry_port or forward_port==telemetry_port):raise ValueError('Telemetry forwarding requires distinct loopback ports')
    output.mkdir(parents=True,exist_ok=False)
    memory=None;inode=None;udp=None;latest=records=lost=written=packets=0;truncated=False;running=True;completed=False;error=None;owner=0;connected=False;forces_seen=False
    def finish(*_):
        nonlocal running
        running=False
    previous={s:signal.signal(s,finish) for s in (signal.SIGINT,signal.SIGTERM)}
    started=time.time_ns()//1_000_000
    try:
        if telemetry_port:
            udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',telemetry_port));udp.setblocking(False)
        memory,inode=create_ring(path)
        (output/'ready').write_text('Force trace ready; no motor access.\n')
        with (output/'frames.bin.gz').open('xb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1) as frames,(output/'telemetry.jsonl').open('x') as tele:
            print('TRACE_READY: full published force state; no HID output.',flush=True)
            while running and not stop.exists():
                rows,latest,gaps=drain(memory,latest);lost+=gaps
                if latest and not connected:
                    connected=True;print('TRACE_CONNECTED: game DLL is publishing full force state.',flush=True)
                for row in rows:
                    if not forces_seen and struct.unpack_from('<I',row,64+16)[0] and any(struct.unpack_from('<I',row,64+64+n*96+4)[0] for n in range(32)):
                        forces_seen=True;print('TRACE_FORCES_ACTIVE: acquired device with playing game effects.',flush=True)
                    if written+len(row)<=max_bytes:frames.write(row);written+=len(row);records+=1
                    else:truncated=True
                if udp:
                    for _ in range(256):
                        try:packet,_=udp.recvfrom(65535)
                        except BlockingIOError:break
                        if forward_port:udp.sendto(packet,('127.0.0.1',forward_port))
                        item=telemetry(packet)
                        if item is not None:
                            item['received_unix_ms']=time.time_ns()//1_000_000
                            tele.write(json.dumps(item,separators=(',',':'))+'\n');packets+=1
                time.sleep(.002)
        completed=True
        return dict(records=records,lost_records=lost,last_sequence=latest,uncompressed_bytes=written,recording_truncated=truncated,telemetry_packets=packets)
    except BaseException as exc:
        error=str(exc);raise
    finally:
        if memory:owner=struct.unpack_from('<I',memory,24)[0]
        summary=dict(records=records,lost_records=lost,last_sequence=latest,uncompressed_bytes=written,recording_truncated=truncated,telemetry_packets=packets,started_unix_ms=started,ended_unix_ms=time.time_ns()//1_000_000,hardware_output=False,completed=completed,error=error,producer_windows_pid=owner,ring_slots=SLOTS,stride=STRIDE,force_bytes=FORCE_BYTES,input_bytes=INPUT_BYTES)
        (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        if udp:udp.close()
        if memory:memory.close()
        if inode is not None and path.exists() and path.lstat().st_ino==inode:path.unlink()
        for s,handler in previous.items():signal.signal(s,handler)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mapping',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--stop-file',type=Path,required=True);p.add_argument('--telemetry-port',type=int);p.add_argument('--forward-port',type=int);a=p.parse_args()
    for port in [a.telemetry_port,a.forward_port]:
        if port is not None and not 1<=port<=65535:p.error('Invalid loopback port')
    collect(a.mapping,a.output_dir,a.stop_file,a.telemetry_port,a.forward_port)
if __name__=='__main__':main()
