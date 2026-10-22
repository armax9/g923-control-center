# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from sdk_direction import infer_sign
class SDKDirectionTests(unittest.TestCase):
    def test_positive_and_negative_sensor_motion(self):
        self.assertEqual(infer_sign(32000,32500),(1,500))
        self.assertEqual(infer_sign(32000,31500),(-1,-500))
    def test_noise_and_invalid_motion_not_accepted(self):
        for end in [32001,32000,float('nan'),float('inf'),40000]:
            with self.assertRaises(ValueError):infer_sign(32000,end)
    def test_measured_sign_converts_restore_force(self):
        for physical_positive in [-1,1]:
            sign,_=infer_sign(32000,32000+physical_positive*500)
            for position in [-.25,.25]:
                desired=-position
                sdk=desired*sign
                self.assertLess(position*sdk*physical_positive,0)
