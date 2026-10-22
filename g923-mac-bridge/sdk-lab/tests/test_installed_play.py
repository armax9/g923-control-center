import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from installed_play import readiness
class ReadinessTest(unittest.TestCase):
 def test_ignores_noisy_loader_output(self):
  self.assertTrue(readiness('loader noise\n{"event":"steam_readiness","initialized":true}\n')['initialized'])
 def test_running_is_not_ready(self):
  self.assertFalse(readiness('{"event":"steam_readiness","client_running":true,"initialized":false}')['initialized'])
 def test_missing_result_is_not_ready(self):self.assertEqual(readiness('bad output'),{})
