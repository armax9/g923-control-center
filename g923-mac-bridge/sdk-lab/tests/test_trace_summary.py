# SPDX-License-Identifier: GPL-3.0-only
import importlib.util,pathlib,unittest
p=pathlib.Path(__file__).resolve().parents[1]/'tools/trace_summary.py'
spec=importlib.util.spec_from_file_location('trace_summary',p);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class TraceSummaryTests(unittest.TestCase):
 def test_interleaved_reports_and_partial_dump(self):
  lines=[]
  for tid in ['00c4','00d4']:lines.append(tid+':trace:hid:hid_internal_dispatch write output report id 1 length 64:\n')
  for offset in range(0,64,16):
   for tid,command in [('00c4',1),('00d4',4)]:
    b=bytearray(16)
    if offset==0:b[0]=1;b[4]=command
    lines.append(f'{tid}:trace:hid:hid_internal_dispatch {offset:08x}  '+b.hex(' ')+'\n')
  lines+=['00c4:trace:hid:hid_internal_dispatch write output report id 1 length 64:\n','00c4:trace:dinput:hid_joystick_effect_Start: iface 0x123\n']
  r=mod.summarize(lines)
  self.assertEqual(r['observations']['complete_64byte_output_reports'],2)
  self.assertEqual(r['observations']['unfinished_dumps_at_end'],1)
  self.assertEqual(r['report_id_1_byte_4_histogram'],{'1':1,'4':1})
  self.assertEqual(r['observations']['dinput_Start_requests'],1)
  self.assertIn('not intercepted',r['interpretation']['sdk_calls'])
 def test_actual_wine_function_delimiter(self):
  r=mod.summarize(['0a30:trace:dinput:dinput_device_SendForceFeedbackCommand iface 123, command 0x1.\n'])
  self.assertEqual(r['observations']['dinput_SendForceFeedbackCommand_requests'],1)
 def test_input_thread_start_is_not_effect_start(self):
  r=mod.summarize(['0a30:trace:dinput:input_thread_start thread 123\n'])
  self.assertNotIn('dinput_Start_requests',r['observations'])
 def test_empty_is_not_success(self):
  r=mod.summarize([]);self.assertNotIn('hid_output_requests',r['observations'])
  self.assertIn('requires',r['interpretation']['physical_playback'])
if __name__=='__main__':unittest.main()
