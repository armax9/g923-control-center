#!/usr/bin/env python3
import pathlib,subprocess,tempfile,struct,socket,time,json
root=pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
 path=pathlib.Path(tmp)/'tone.bin'
 subprocess.run([str(root/'build/g923-tf'),'--out',str(path),'--seconds','1'],check=True)
 b=path.read_bytes();assert len(b)==(136+1000+2)*64
 packets=[b[i:i+64] for i in range(0,len(b),64)]
 assert packets[0][5]==1 and packets[68][5]==1
 for pkt in packets:
  assert pkt[0]==1
  if pkt[4]==14:assert struct.unpack_from('<f',pkt,6)[0]==900
 for i,p in enumerate(packets[136:-1]):
  assert p[4]==1 and p[5]==(69+i)%256
  assert p[6:10]==b'\x00\x80\x00\x80'
 assert packets[-1][4]==4
 # Live loopback integration and stale-data path; no HID opened.
 path=pathlib.Path(tmp)/'udp.bin'
 proc=subprocess.Popen([str(root/'build/g923-tf'),'--udp','--seconds','2','--out',str(path)])
 time.sleep(.15);s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);data=bytearray(264);struct.pack_into('<f',data,148,600)
 for _ in range(10):s.sendto(data,('127.0.0.1',20777));time.sleep(.02)
 s.close();assert proc.wait(timeout=5)==0
 b=path.read_bytes();tail=[b[i:i+64] for i in range(136*64,len(b)-128,64)]
 assert any(p[12:]!=b'\x00\x80\x00\x80'*13 for p in tail)
 assert tail[-1][12:]==b'\x00\x80\x00\x80'*13, 'telemetry timeout must silence window'
 # Installer rollback with a pre-existing unrelated proxy.
 game=pathlib.Path(tmp)/'game';game.mkdir();dll=game/'dinput8.dll';dll.write_bytes(b'original')
 script=root/'scripts/install-proxy.py'
 if (root/'build/windows/dinput8.dll').exists():
  subprocess.run(['python3',str(script),'install',str(game)],check=True)
  subprocess.run(['python3',str(script),'uninstall',str(game)],check=True)
  assert dll.read_bytes()==b'original'
print('Offline tone, init, sequence, UDP timeout and installer rollback: PASS')
