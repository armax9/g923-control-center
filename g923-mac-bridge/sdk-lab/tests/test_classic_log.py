# SPDX-License-Identifier: GPL-3.0-only
import importlib.util,json,pathlib,unittest
p=pathlib.Path(__file__).resolve().parents[1]/'tools/classic_log_summary.py';spec=importlib.util.spec_from_file_location('classic_log_summary',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ClassicLogTests(unittest.TestCase):
 def report(self,packets):return m.summarize([json.dumps({'event':'classic_hid_output','payload':b,'status':s}) for b,s in packets])
 def test_stop_must_follow_nonzero(self):
  r=self.report([([243],0),([17,0,160],0)]);self.assertFalse(r['final_force_command_is_successful_stop']);self.assertEqual(r['nonzero_constant_requests'],1)
 def test_failed_stop_is_not_confirmed(self):
  self.assertFalse(self.report([([17,0,160],0),([243],-1)])['final_force_command_is_successful_stop'])
 def test_led_after_stop_is_allowed_but_no_physical_claim(self):
  r=self.report([([17,0,160],0),([243],0),([248,18,0],0)]);self.assertTrue(r['final_force_command_is_successful_stop']);self.assertFalse(r['physical_playback_confirmed'])
if __name__=='__main__':unittest.main()
