# SPDX-License-Identifier: GPL-3.0-only
"""Live engine gain: pure preferences tests and optional loopback-only synth test."""
import contextlib
import io
import json
import math
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import ets2


class EngineControlTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.root=Path(folder.name);self.settings=self.root/'game-settings.json';self.control=self.root/'control.json'

    def preferences(self,level=10,enabled=True,strength=100):
        self.settings.write_text(json.dumps({'version':1,'games':{'227300':{'ffbStrength':strength,'trueForceEnabled':enabled,'engineVibration':level}}}))

    def level(self):
        return json.loads(self.control.read_text())['intensity']

    def test_changes_only_engine_gain_and_preserves_independent_ffb(self):
        self.preferences()
        control=ets2.EngineGainControl(self.settings,self.control,10)
        self.assertEqual(self.level(),0.1)
        self.preferences(40,strength=73)
        with contextlib.redirect_stdout(io.StringIO()):control.update()
        self.assertEqual(self.level(),0.4)
        self.preferences(40,enabled=False,strength=73)
        with contextlib.redirect_stdout(io.StringIO()):control.update()
        self.assertEqual(self.level(),0)
        self.preferences(10,enabled=True,strength=73)
        with contextlib.redirect_stdout(io.StringIO()):control.update()
        self.assertEqual(self.level(),0.1)
        self.assertEqual(json.loads(self.settings.read_text())['games']['227300']['ffbStrength'],73)

    def test_invalid_or_missing_live_file_keeps_last_valid_gain(self):
        control=ets2.EngineGainControl(self.settings,self.control,10)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            for bad in ('{','{"version":1,"games":{"227300":{"engineVibration":200}}}',
                        '{"version":1,"games":{"227300":{"trueForceEnabled":"true"}}}'):
                self.settings.write_text(bad);control.update();self.assertEqual(self.level(),0.1)
            self.settings.unlink();control.update();control.update()
        self.assertEqual(output.getvalue().count('unavailable'),1)
        self.preferences(40)
        with contextlib.redirect_stdout(io.StringIO()):control.update()
        self.assertEqual(self.level(),0.4)

    def test_live_session_updates_one_synth_without_restarting_native_owner(self):
        self.preferences()
        mapping=self.root/'ffb.bin';header=bytearray(104)
        struct.pack_into('<I',header,68,1);struct.pack_into('<Q',header,72,int(time.time()*1000));mapping.write_bytes(header)
        commands=[]
        def spawn(args,**kwargs):
            commands.append(args);child=MagicMock();child.poll.return_value=None;return child
        sleeps=0
        def tick(_):
            nonlocal sleeps
            sleeps+=1
            if sleeps==1:self.preferences(40)
            elif sleeps==2:self.preferences(40,enabled=False)
            else:(self.root/'stop').touch()
        with patch.object(ets2,'INSTALL',self.root),patch.object(ets2.subprocess,'Popen',side_effect=spawn),patch.object(ets2.time,'sleep',side_effect=tick),contextlib.redirect_stdout(io.StringIO()) as output:
            ets2.run({'native_tf_direction_measured':True,'mapping':str(mapping),'tf_motor_sign':1},
                     launch_game=False,settings_file=self.settings,engine_vibration=10,ffb_strength=73)
        self.assertEqual(len(commands),2)
        synth,native=commands
        self.assertIn('--control-file',synth)
        self.assertEqual(native[native.index('--strength')+1],'0.73')
        self.assertEqual(native[native.index('--motor-sign')+1],'-1')
        self.assertEqual(native[native.index('--tf-motor-sign')+1],'1')
        self.assertIn('"percent": 40.0',output.getvalue())
        self.assertIn('"percent": 0',output.getvalue())
        control=Path(synth[synth.index('--control-file')+1]);self.assertEqual(json.loads(control.read_text())['intensity'],0)

    def test_initial_zero_live_gain_keeps_combined_path_for_later_slider_changes(self):
        self.preferences(0)
        mapping=self.root/'ffb.bin';header=bytearray(104)
        struct.pack_into('<I',header,68,1);struct.pack_into('<Q',header,72,int(time.time()*1000));mapping.write_bytes(header)
        commands=[]
        def spawn(args,**kwargs):
            commands.append(args);child=MagicMock();child.poll.return_value=None
            if len(commands)==2:(self.root/'stop').touch()
            return child
        with patch.object(ets2,'INSTALL',self.root),patch.object(ets2.subprocess,'Popen',side_effect=spawn),contextlib.redirect_stdout(io.StringIO()):
            ets2.run({'native_tf_direction_measured':True,'mapping':str(mapping),'tf_motor_sign':1},
                     launch_game=False,settings_file=self.settings,engine_vibration=0)
        self.assertEqual(len(commands),2)
        self.assertIn('--mescon-audio',commands[1])
        self.assertEqual(commands[0][commands[0].index('--intensity')+1],'0.0')


@unittest.skipUnless(os.environ.get('MESCON_SYNTH_TEST_BINARY'),'Set MESCON_SYNTH_TEST_BINARY to run the loopback-only compiled synth test')
class LiveSynthUDP(unittest.TestCase):
    def test_ten_to_forty_and_mute_changes_audio_in_same_process_without_gaps(self):
        # Unique ephemeral ports: this fixture never connects to the motor
        # backend's production UDP address and cannot send HID output.
        with tempfile.TemporaryDirectory() as folder, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as output, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as reserve, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
            output.bind(('127.0.0.1',0));output.setblocking(False)
            reserve.bind(('127.0.0.1',0));listen=reserve.getsockname()[1];reserve.close()
            control=Path(folder)/'engine-control.json'
            def set_gain(gain):
                temporary=control.with_suffix('.tmp');temporary.write_text(json.dumps({'version':1,'intensity':gain},separators=(',',':')));temporary.replace(control)
            set_gain(0.1)
            process=subprocess.Popen([os.environ['MESCON_SYNTH_TEST_BINARY'],'--intensity','0.1','--control-file',str(control),
                '--listen-port',str(listen),'--output-port',str(output.getsockname()[1])],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            self.addCleanup(lambda: process.poll() is None and process.kill())
            packet=bytearray(40);packet[:4]=b'LTFR';packet[4]=2;packet[6:10]=b'ets2'
            struct.pack_into('<fff',packet,14,900.0,2500.0,0.5)
            all_sequences=[];all_times=[]
            def capture(seconds,discard=0.12):
                start=time.monotonic();values=[]
                while time.monotonic()-start<seconds:
                    sender.sendto(packet,('127.0.0.1',listen))
                    readable,_,_=select.select([output],[],[],0.005)
                    if not readable:continue
                    while True:
                        try:data=output.recv(4096)
                        except BlockingIOError:break
                        self.assertEqual(data[:4],b'G9AU')
                        if data[5] and time.monotonic()-start>discard:
                            values.extend(struct.unpack('<'+'f'*struct.unpack_from('<H',data,6)[0],data[12:]))
                        all_sequences.append(struct.unpack_from('<I',data,8)[0]);all_times.append(time.monotonic())
                    self.assertIsNone(process.poll(),'Synth process exited during a live gain change')
                self.assertTrue(values,'No live audio samples received')
                return math.sqrt(sum(v*v for v in values)/len(values))
            try:
                low=capture(0.45);set_gain(0.4);high=capture(0.45)
                self.assertGreater(high,low*3.5);self.assertLess(high,low*4.5)
                control.write_text('{broken');kept=capture(0.30)
                self.assertGreater(kept,high*0.9);self.assertLess(kept,high*1.1)
                set_gain(0.0);silent=capture(0.35)
                self.assertEqual(silent,0.0)
                set_gain(0.1);restored=capture(0.35)
                self.assertGreater(restored,low*0.9);self.assertLess(restored,low*1.1)
                self.assertTrue(all((b-a)&0xffffffff==1 for a,b in zip(all_sequences,all_sequences[1:])), 'Packet sequence reset or skipped')
                self.assertLess(max(b-a for a,b in zip(all_times,all_times[1:])),0.1,'Audio stream stalled')
            finally:
                process.terminate();process.communicate(timeout=5)


if __name__=='__main__':unittest.main()
