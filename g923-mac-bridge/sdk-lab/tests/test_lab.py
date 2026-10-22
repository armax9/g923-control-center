# SPDX-License-Identifier: GPL-3.0-only
import json,pathlib,sys,tempfile,unittest,hashlib
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
import lab
class LabIsolationTests(unittest.TestCase):
 def test_foreign_and_unmarked_bottle_rejected(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(lab,'STATE',pathlib.Path(tmp)):
   (lab.STATE/'bottles').mkdir()
   with self.assertRaises(RuntimeError):lab.owned_lab()
   (lab.STATE/'bottles').rmdir()
   self.assertEqual(lab.owned_lab(),lab.STATE/'bottles')
   (lab.STATE/'owner.json').write_text(json.dumps({'purpose':'other project'}))
   with self.assertRaises(RuntimeError):lab.owned_lab()
 def test_timeout_returns_distinct_code(self):
  r=lab.run([sys.executable,'-c','import time;time.sleep(20)'],timeout=.1)
  self.assertEqual(r['returncode'],124)
 def test_arguments_do_not_use_shell(self):
  payload='space; $(touch should-not-exist)'
  r=lab.run([sys.executable,'-c','import sys;print(sys.argv[1])',payload])
  self.assertEqual(r['returncode'],0);self.assertEqual(r['stdout'].strip(),payload)
 def test_missing_sdk_rejected_without_wine(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(lab,'STATE',pathlib.Path(tmp)),patch.object(lab,'ensure_bottle',return_value=(pathlib.Path(tmp)/'bottle',{})),patch.object(lab,'wine') as wine:
   (lab.STATE/'stage.json').write_text(json.dumps({'chosen':{}}))
   with self.assertRaises(RuntimeError):lab.check_staged(pathlib.Path('/unused'),True)
   wine.assert_not_called()
 def test_changed_staged_bytes_rejected(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(lab,'STATE',pathlib.Path(tmp)),patch.object(lab,'wine') as wine:
   bottle=lab.STATE/'bottle';(bottle/'drive_c').mkdir(parents=True);(bottle/'drive_c/tf.dll').write_bytes(b'changed')
   (lab.STATE/'stage.json').write_text(json.dumps({'chosen':{'trueforce':{'windows_path':'C:\\tf.dll','sha256':'bad'}}}))
   with patch.object(lab,'ensure_bottle',return_value=(bottle,{})),self.assertRaises(RuntimeError):lab.check_staged(pathlib.Path('/unused'),True)
   wine.assert_not_called()
 def test_untrusted_staged_file_not_loaded_and_report_saved(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(lab,'STATE',pathlib.Path(tmp)),patch.object(lab,'wine',return_value={'returncode':4,'stdout':'unsigned','stderr':''}) as wine:
   bottle=lab.STATE/'bottle';(bottle/'drive_c').mkdir(parents=True);data=b'unsigned test data';(bottle/'drive_c/tf.dll').write_bytes(data)
   (lab.STATE/'stage.json').write_text(json.dumps({'chosen':{'trueforce':{'windows_path':'C:\\tf.dll','sha256':hashlib.sha256(data).hexdigest()}}}))
   with patch.object(lab,'ensure_bottle',return_value=(bottle,{})),self.assertRaises(RuntimeError):lab.check_staged(pathlib.Path('/unused'),True)
   self.assertEqual(wine.call_count,1);self.assertIn('--verify',wine.call_args[0][2]);self.assertTrue((lab.STATE/'signature-real-sdk.json').exists())
if __name__=='__main__':unittest.main()
