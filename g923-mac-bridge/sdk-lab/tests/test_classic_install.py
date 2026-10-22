# SPDX-License-Identifier: GPL-3.0-only
import importlib.util,pathlib,sys,tempfile,unittest
TOOL=pathlib.Path(__file__).resolve().parents[1]/'tools';sys.path.insert(0,str(TOOL))
import classic_game as m
class InstallTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=pathlib.Path(self.tmp.name);self.out=self.base/'out';self.out.mkdir();self.target=self.base/'game.dll';(self.out/'dinput8.dll').write_bytes(b'project')
 def state(self,original):
  if original:self.target.write_bytes(original)
  return {'target':str(self.target),'installed_sha':m.sha(self.out/'dinput8.dll'),'previous_sha':m.sha(self.target) if original else None,'uid':123}
 def test_game_requires_measured_motor_sign(self):
  with self.assertRaises(RuntimeError):m.validate_motor_profile({})
  good={'purpose':'g923-classic-physical-motor-sign','valid':True,'sign':-1,'delta':-200,'cleanup':{'final_force_command_is_successful_stop':True}}
  self.assertEqual(m.validate_motor_profile(good),-1)
  good['sign']=1
  with self.assertRaises(RuntimeError):m.validate_motor_profile(good)
 def test_restore_original_bytes(self):
  s=self.state(b'original');m.install(self.out,s);self.assertEqual(self.target.read_bytes(),b'project');m.rollback(self.out,s);self.assertEqual(self.target.read_bytes(),b'original')
 def test_remove_only_our_new_dll(self):
  s=self.state(None);m.install(self.out,s);m.rollback(self.out,s);self.assertFalse(self.target.exists())
 def test_intervening_change_preserved(self):
  s=self.state(b'original');m.install(self.out,s);self.target.write_bytes(b'user edit')
  with self.assertRaises(RuntimeError):m.rollback(self.out,s)
  self.assertEqual(self.target.read_bytes(),b'user edit')
 def test_changed_before_install_refused(self):
  s=self.state(None);self.target.write_bytes(b'user added')
  with self.assertRaises(RuntimeError):m.install(self.out,s)
  self.assertEqual(self.target.read_bytes(),b'user added')
if __name__=='__main__':unittest.main()
