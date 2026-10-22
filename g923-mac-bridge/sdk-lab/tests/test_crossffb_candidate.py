# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import ets2
class CrossFFBCandidateTests(unittest.TestCase):
    def test_candidate_rejects_sdk_style_or_game_launch_before_any_process(self):
        with self.assertRaises(ValueError):ets2.run({},launch_game=False,classic_only=False,crossffb=True)
        with self.assertRaises(ValueError):ets2.run({},launch_game=True,classic_only=True,crossffb=True)
