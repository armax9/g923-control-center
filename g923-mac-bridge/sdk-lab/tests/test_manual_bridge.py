"""Manual sessions must never launch Steam or a game as a side effect."""
import contextlib,io,struct,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import ets2,installed_play,sdk_game
class ManualBridge(unittest.TestCase):
 def test_ets2_manual_only_starts_two_backends_and_cleans_them(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);mapping=root/'ffb.bin';header=bytearray(104)
   struct.pack_into('<I',header,68,1);struct.pack_into('<Q',header,72,int(time.time()*1000));mapping.write_bytes(header)
   children=[]
   def spawn(args,**kwargs):
    self.assertFalse(any(str(x).lower().endswith('.exe') for x in args))
    if str(args[0]).endswith('G923TelemetryLab'):
     self.assertEqual(args[args.index('--strength')+1],'1')
     self.assertEqual(args[args.index('--max-force')+1],'1')
    child=MagicMock();child.poll.return_value=None;children.append(child)
    if len(children)==2:(root/'stop').touch()
    return child
   with patch.object(ets2,'INSTALL',root),patch.object(ets2.subprocess,'Popen',side_effect=spawn),patch.object(ets2.subprocess,'run',side_effect=AssertionError('No Steam probes in manual mode')),contextlib.redirect_stdout(io.StringIO()) as output:
    ets2.run({'native_tf_direction_measured':True,'mapping':str(mapping),'tf_motor_sign':1},launch_game=False)
   self.assertEqual(len(children),2)
   for child in children:child.terminate.assert_called_once()
   self.assertIn('BRIDGE_LISTENING:',output.getvalue())
 def test_manual_dirt_does_not_enter_steam_or_game_launcher(self):
  with patch.object(sys,'argv',['installed_play.py','--installation','/tmp/session','--manual','--user-ready']),patch.object(installed_play,'load',return_value={}),patch.object(installed_play,'check'),patch.object(installed_play,'start') as start,patch.object(installed_play,'game_running',side_effect=AssertionError('Manual path must bypass launcher')),patch.object(installed_play.subprocess,'Popen',side_effect=AssertionError('No Steam/game spawn')):
   installed_play.main()
   start.assert_called_once_with(Path('/tmp/session').resolve(),{},launch_game=False)
 def test_sdk_manual_starts_input_only_and_skips_readiness_and_game(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);mapping=root/'input.bin';child=MagicMock();child.poll.side_effect=[None,0,0]
   real_open=sdk_game.os.open
   def open_private_lock(path,*args,**kwargs):
    return real_open(root/'private-test.lock' if str(path).startswith('/tmp/g923-mac-bridge-') else path,*args,**kwargs)
   def spawn(args,**kwargs):
    self.assertTrue(str(args[0]).endswith('g923-input'))
    header=bytearray(8192);struct.pack_into('<I',header,68,1);mapping.write_bytes(header)
    return child
   manifest={'main_steam_experiment':True,'game_exe':str(root/'game.exe'),'mapping':str(mapping)}
   with patch.object(sdk_game.os,'open',side_effect=open_private_lock),patch.object(sdk_game,'check'),patch.object(sdk_game,'environment',return_value={}),patch.object(sdk_game,'stop'),patch.object(sdk_game.subprocess,'Popen',side_effect=spawn) as popen,patch.object(sdk_game.subprocess,'run',side_effect=AssertionError('No Steam probe/game in manual mode')),contextlib.redirect_stdout(io.StringIO()) as output:
    with self.assertRaisesRegex(RuntimeError,'Input publisher exited'):
     sdk_game.start(root,manifest,launch_game=False)
   self.assertEqual(popen.call_count,1)
   self.assertIn('BRIDGE_LISTENING:',output.getvalue())
if __name__=='__main__':unittest.main()

class ClassicIsolation(unittest.TestCase):
 def test_per_game_gain_does_not_scale_engine_or_change_accepted_motor_sign(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);mapping=root/'ffb.bin';header=bytearray(104)
   struct.pack_into('<I',header,68,1);struct.pack_into('<Q',header,72,int(time.time()*1000));mapping.write_bytes(header)
   commands=[]
   def spawn(args,**kwargs):
    commands.append(args);child=MagicMock();child.poll.return_value=None
    if len(commands)==2:(root/'stop').touch()
    return child
   with patch.object(ets2,'INSTALL',root),patch.object(ets2.subprocess,'Popen',side_effect=spawn),contextlib.redirect_stdout(io.StringIO()):
    ets2.run({'native_tf_direction_measured':True,'mapping':str(mapping),'tf_motor_sign':1},launch_game=False,ffb_strength=65,engine_vibration=80)
   synth,native=commands
   self.assertEqual(synth[synth.index('--intensity')+1],'0.8')
   self.assertEqual(native[native.index('--strength')+1],'0.65')
   self.assertEqual(native[native.index('--max-force')+1],'1')
   self.assertEqual(native[native.index('--motor-sign')+1],'-1')
   self.assertEqual(native[native.index('--tf-motor-sign')+1],'1')

 def test_zero_vibration_starts_classic_only_and_does_not_require_tf_calibration(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);mapping=root/'ffb.bin';header=bytearray(104)
   struct.pack_into('<I',header,68,1);struct.pack_into('<Q',header,72,int(time.time()*1000));mapping.write_bytes(header)
   def spawn(args,**kwargs):
    self.assertNotIn('--mescon-audio',args);self.assertNotIn('--tf-motor-sign',args)
    self.assertEqual(args[args.index('--strength')+1],'0')
    (root/'stop').touch();child=MagicMock();child.poll.return_value=None;return child
   with patch.object(ets2,'INSTALL',root),patch.object(ets2.subprocess,'Popen',side_effect=spawn) as popen,contextlib.redirect_stdout(io.StringIO()):
    ets2.run({'mapping':str(mapping)},launch_game=False,engine_vibration=0,ffb_strength=0)
   self.assertEqual(popen.call_count,1)

 def test_invalid_effect_values_fail_before_backend_start(self):
  with patch.object(ets2.subprocess,'Popen') as popen:
   for kwargs in ({'ffb_strength':101},{'ffb_strength':float('nan')},{'engine_vibration':float('inf')},{'engine_vibration':False}):
    with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):ets2.run({},launch_game=False,**kwargs)
   popen.assert_not_called()

 def test_classic_comparison_uses_only_native_no_audio_or_game(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);mapping=root/'ffb.bin';header=bytearray(104)
   struct.pack_into('<I',header,68,1);struct.pack_into('<Q',header,72,int(time.time()*1000));mapping.write_bytes(header)
   def spawn(args,**kwargs):
    self.assertTrue(str(args[0]).endswith('G923TelemetryLab'))
    self.assertNotIn('--mescon-audio',args)
    (root/'stop').touch();child=MagicMock();child.poll.return_value=None;return child
   with patch.object(ets2,'INSTALL',root),patch.object(ets2.subprocess,'Popen',side_effect=spawn) as popen,patch.object(ets2.subprocess,'run',side_effect=AssertionError('No game launch')),contextlib.redirect_stdout(io.StringIO()):
    ets2.run({'native_tf_direction_measured':True,'mapping':str(mapping),'tf_motor_sign':1},launch_game=False,classic_only=True)
   self.assertEqual(popen.call_count,1)
