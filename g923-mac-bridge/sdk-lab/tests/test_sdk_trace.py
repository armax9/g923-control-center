import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from sdk_trace_summary import summarize


class SdkTraceTests(unittest.TestCase):
    def row(self, calls, pid=1):
        return json.dumps(dict(event='sdk_call_summary', pid=pid,
                               name='logiTrueForceSetTorqueTFint16', calls=calls,
                               samples_total=calls*4, nonzero_batches=calls))

    def test_snapshots_are_not_added(self):
        report=summarize([self.row(1),self.row(256),self.row(256)])
        self.assertEqual(report['tf_call_count'],256)
        self.assertEqual(report['tf_accepted_samples'],1024)
        self.assertFalse(report['physical_playback_confirmed'])

    def test_pids_are_separate(self):
        self.assertEqual(summarize([self.row(3,1),self.row(4,2)])['tf_call_count'],7)

    def test_bad_or_other_events_not_evidence(self):
        report=summarize(['bad',json.dumps(dict(event='sdk_export_resolved',calls=99))])
        self.assertEqual(report['tf_call_count'],0)
        self.assertEqual(report['invalid_lines'],1)


if __name__=='__main__':
    unittest.main()
