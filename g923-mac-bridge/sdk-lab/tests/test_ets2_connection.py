import sys,json,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from ets2_connection import ConnectionMonitor
class ConnectionTests(unittest.TestCase):
 def test_telemetry_alone_is_not_game_bridge_connection(self):
  m=ConnectionMonitor();m.feed(json.dumps({'event':'telemetry','live':True,'packets':1996}))
  m.feed(json.dumps({'event':'force_snapshot','pid':0,'active':False,'effects':[]}))
  self.assertIn('input_ffb=waiting; telemetry=live',m.message())
  self.assertIsNone(m.message())
 def test_fresh_active_process_and_stale_disconnect(self):
  m=ConnectionMonitor();m.feed(json.dumps({'event':'force_snapshot','pid':123,'active':True,'age_ms':3,'effects':[{}]}))
  self.assertIn('input_ffb=connected',m.message())
  m.feed(json.dumps({'event':'force_snapshot','pid':123,'active':True,'age_ms':800,'effects':[]}))
  self.assertIn('input_ffb=waiting',m.message())
 def test_partial_log_is_ignored(self):
  m=ConnectionMonitor();m.feed('{partial');self.assertIn('input_ffb=waiting',m.message())
