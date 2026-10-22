#!/usr/bin/env python3
"""Exercise the real mescon executable over loopback, with no wheel process."""
import math,socket,struct,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
binary=root/'build/control-center/G923 Control Center.app/Contents/Resources/mescon-synth'
for source,port in [('relay',20780),('pcars',5606)]:
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as audio, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
  audio.bind(('127.0.0.1',20781));audio.settimeout(2)
  process=subprocess.Popen([str(binary),'--source',source,'--effects','all'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  try:
   def read():
    packet=audio.recv(4096)
    assert packet[:6] in (b'G9AU\x01\x00',b'G9AU\x01\x01')
    count=struct.unpack_from('<H',packet,6)[0];samples=struct.unpack_from('<'+'f'*count,packet,12)
    assert all(math.isfinite(s) and abs(s)<=1 for s in samples)
    return packet[5],samples
   live,samples=read();assert live==0 and not any(samples)
   if source=='relay':
    packet=bytearray(40);packet[:4]=b'LTFR';packet[4]=2;packet[6:10]=b'ets2';struct.pack_into('<fffh',packet,14,1500,2500,.5,2)
   else:
    packet=bytearray(559);packet[11]=2;packet[30]=128;struct.pack_into('<fHH',packet,36,12,4500,8000)
   sender.sendto(packet,('127.0.0.1',port));deadline=time.monotonic()+.4;heard=False
   while time.monotonic()<deadline:
    live,samples=read();heard|=bool(live and any(abs(s)>1e-6 for s in samples))
   assert heard,source+' never generated live audio'
   deadline=time.monotonic()+1
   while time.monotonic()<deadline:live,samples=read()
   assert live==0 and not any(samples),'Telemetry timeout must silence every effect'
   assert process.poll() is None
   print(source+': valid bounded audio; stale telemetry silenced; no HID process')
  finally:
   process.terminate();process.wait(timeout=5)
