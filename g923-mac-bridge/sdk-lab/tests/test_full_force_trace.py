# SPDX-License-Identifier: GPL-3.0-only
import gzip,importlib.util,json,os,socket,struct,subprocess,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('full_force_trace',ROOT/'sdk-lab/tools/full_force_trace.py');trace=importlib.util.module_from_spec(spec);spec.loader.exec_module(trace)
class FullForceTraceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.binary=Path(cls.temp.name)/'export'
  env=os.environ.copy();env['DEVELOPER_DIR']='/Applications/Xcode.app/Contents/Developer'
  subprocess.run(['xcrun','clang','-std=c11','-Wno-unused-function','-fsanitize=address,undefined',str(ROOT/'vendor/crossover-ffb/Bridge/tests/export_force_contract.c'),'-o',str(cls.binary)],check=True,env=env,capture_output=True)
  cls.ring=subprocess.check_output([str(cls.binary),'--ring'])
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_real_c_producer_wrap_and_exact_drop_accounting(self):
  self.assertEqual(len(self.ring),trace.SIZE)
  rows,latest,lost=trace.drain(self.ring,0)
  self.assertGreater(latest,trace.SLOTS);self.assertEqual(len(rows),trace.SLOTS);self.assertEqual(lost,latest-trace.SLOTS)
  seqs=[struct.unpack_from('<Q',r,8)[0] for r in rows]
  self.assertEqual(seqs,list(range(latest-trace.SLOTS+1,latest+1)))
  for row in rows:
   self.assertEqual(struct.unpack_from('<I',row,36)[0],48)
   self.assertEqual(struct.unpack_from('<4I',row,40),(1,0x100,0,0)) # SetParameters, success, slot0.
   self.assertEqual(struct.unpack_from('<I',row,64+trace.FORCE_BYTES+4)[0],1) # coherent connected input
  self.assertEqual(trace.drain(self.ring,latest),([],latest,0))
 def test_torn_record_is_rejected_and_counted(self):
  ring=bytearray(self.ring);latest=struct.unpack_from('<Q',ring,16)[0];offset=trace.HEADER+(latest-1)%trace.SLOTS*trace.STRIDE
  struct.pack_into('<Q',ring,offset,latest*2-1)
  rows,after,lost=trace.drain(ring,latest-1)
  self.assertEqual((rows,after,lost),([],latest,1))
 def test_header_corruption_and_reset_rejected(self):
  ring=bytearray(self.ring);struct.pack_into('<I',ring,12,12)
  with self.assertRaises(ValueError):trace.drain(ring,0)
  latest=struct.unpack_from('<Q',self.ring,16)[0]
  with self.assertRaises(ValueError):trace.drain(self.ring,latest+1)
 def test_ring_creation_is_exclusive_and_mode_private(self):
  with tempfile.TemporaryDirectory() as temp:
   os.chmod(temp,0o700);path=Path(temp)/'trace-v1.bin';memory,inode=trace.create_ring(path)
   try:
    self.assertEqual(path.stat().st_mode&0o777,0o600);self.assertEqual(trace.drain(memory,0),([],0,0))
    with self.assertRaises(FileExistsError):trace.create_ring(path)
   finally:memory.close()
 def test_collector_process_flushes_gzip_and_relays_identical_telemetry(self):
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp);os.chmod(base,0o700);mapping=base/'trace-v1.bin';output=base/'capture';stop=base/'stop'
   receiver=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);receiver.bind(('127.0.0.1',0));receiver.settimeout(3)
   probe=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
   process=subprocess.Popen([sys.executable,str(ROOT/'sdk-lab/tools/full_force_trace.py'),'--mapping',str(mapping),'--output-dir',str(output),'--stop-file',str(stop),'--telemetry-port',str(port),'--forward-port',str(receiver.getsockname()[1])],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   try:
    deadline=time.monotonic()+5
    while not (output/'ready').exists():
     if process.poll() is not None:raise AssertionError(process.communicate()[1].decode())
     if time.monotonic()>deadline:raise AssertionError('Collector did not become ready')
     time.sleep(.01)
    with mapping.open('r+b') as f:
     import mmap
     with mmap.mmap(f.fileno(),trace.SIZE) as memory:
      memory[trace.HEADER:]=self.ring[trace.HEADER:];memory[24:32]=self.ring[24:32]
      trace._barrier();memory[16:24]=self.ring[16:24]
    packet=bytearray(40);packet[:4]=b'LTFR';packet[4]=2;packet[6:10]=b'ets2';struct.pack_into('<3f',packet,14,900,2500,.2)
    receiver.sendto(packet,('127.0.0.1',port));self.assertEqual(receiver.recvfrom(65535)[0],packet)
    stop.touch();stdout,stderr=process.communicate(timeout=5);self.assertEqual(process.returncode,0,stderr.decode())
    summary=json.loads((output/'summary.json').read_text());self.assertEqual(summary['records'],trace.SLOTS);self.assertEqual(summary['telemetry_packets'],1)
    self.assertEqual(len(gzip.decompress((output/'frames.bin.gz').read_bytes())),trace.SLOTS*trace.STRIDE)
    self.assertEqual(json.loads((output/'telemetry.jsonl').read_text())['rpm'],900);self.assertFalse(mapping.exists())
   finally:
    receiver.close()
    if process.poll() is None:process.terminate();process.communicate(timeout=5)
 def test_telemetry_is_finite_and_does_not_invent_engine_flag(self):
  p=bytearray(40);p[:4]=b'LTFR';p[4]=2;p[6:10]=b'ets2';struct.pack_into('<3f',p,14,800,2500,.5);struct.pack_into('<h',p,26,2);struct.pack_into('<2f',p,32,10,.1)
  row=trace.telemetry(p);self.assertEqual(row['rpm'],800);self.assertEqual(row['speed_mps'],10);self.assertFalse(row['engine_running_measured'])
  struct.pack_into('<f',p,14,float('nan'));self.assertIsNone(trace.telemetry(p));self.assertIsNone(trace.telemetry(b'bad'))
