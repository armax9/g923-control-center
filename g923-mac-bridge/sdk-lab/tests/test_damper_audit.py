import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from analyze_damper import audit, expected_output
from classic_lab import diagnostic_strength
import argparse


class DamperAuditTests(unittest.TestCase):
    def snapshot(self, velocity, output):
        return dict(event='force_snapshot', active=True, paused=False,
                    actuators_off=False, velocity=velocity, output=output,
                    uptime_ms=100, gain=10000,
                    effects=[dict(kind=9, playing=True, gain=10000,
                                  params=[0, 10000, 10000, 4000, 4000, 0])])

    def test_diagnostic_strength_rejects_invalid_values(self):
        for value in ["nan", "inf", "-0.1", "0.51"]:
            with self.assertRaises(argparse.ArgumentTypeError):
                diagnostic_strength(value)
        self.assertEqual(diagnostic_strength("0.5"), .5)

    def test_rest_and_both_directions(self):
        for speed, expected in [(0, 0), (0.4, -0.05), (-0.4, 0.05), (2, -0.1)]:
            self.assertAlmostEqual(expected_output(self.snapshot(speed, expected), .25), expected)

    def test_detect_wrong_command_polarity(self):
        events = [dict(event='classic_bridge_start', strength=.25, motor_sign=-1),
                  self.snapshot(.4, -.05),
                  dict(event='classic_hid_output', payload=[17, 0, 122], uptime_ms=101)]
        report = audit(events)
        self.assertEqual(report['same_tick_command_mismatches'], 1)
        events[-1]['payload'][2] = 134
        self.assertEqual(audit(events)['same_tick_command_mismatches'], 0)

    def test_never_match_stale_snapshot(self):
        events = [dict(event='classic_bridge_start', strength=.25, motor_sign=-1),
                  self.snapshot(.4, -.05),
                  dict(event='classic_hid_output', payload=[17, 0, 122], uptime_ms=150)]
        self.assertEqual(audit(events)['same_tick_command_matches'], 0)


if __name__ == '__main__':
    unittest.main()
