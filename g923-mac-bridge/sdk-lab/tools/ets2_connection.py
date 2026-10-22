# SPDX-License-Identifier: GPL-3.0-only
"""Read-only connection diagnostics; never controls the wheel."""
import json
class ConnectionMonitor:
 def __init__(self):
  self.force={};self.telemetry={};self.last=None
 def feed(self,line):
  try:item=json.loads(line)
  except ValueError:return
  if item.get('event')=='force_snapshot':self.force=item
  if item.get('event')=='telemetry':self.telemetry=item
 def message(self):
  connected=bool(self.force.get('pid') and self.force.get('active') and self.force.get('age_ms',1e9)<500)
  live=bool(self.telemetry.get('live'));effects=len(self.force.get('effects',[]))
  state=(connected,live,effects)
  if state==self.last:return None
  self.last=state
  return 'ETS2_STATUS: input_ffb='+('connected' if connected else 'waiting')+'; telemetry='+('live' if live else 'waiting')+'; effects='+str(effects)
