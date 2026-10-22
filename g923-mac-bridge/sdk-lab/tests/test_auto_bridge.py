# SPDX-License-Identifier: GPL-3.0-only
import contextlib, importlib.util, io, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1]/'tools'))
spec = importlib.util.spec_from_file_location('auto_bridge', Path(__file__).parents[1]/'tools/auto_bridge.py')
auto = importlib.util.module_from_spec(spec); spec.loader.exec_module(auto)

class AutoBridgeTests(unittest.TestCase):
    def setUp(self):
        self.registry_directory=tempfile.TemporaryDirectory();self.addCleanup(self.registry_directory.cleanup)
        registry=Path(self.registry_directory.name)/'registry.json'
        for target,value in [('load_registry',{'version':1,'profiles':[]}),('default_registry_path',registry)]:
            guard=patch.object(auto,target,return_value=value);guard.start();self.addCleanup(guard.stop)
    def test_engine_vibration_only_reaches_ets2(self):
        for level in (0, 40, 100):
            args = auto.child_command(227300, engine_vibration=level)
            self.assertEqual(args[-2:], ["--engine-vibration", str(level)])
            self.assertNotIn("--engine-vibration", auto.child_command(690790, engine_vibration=level))

    def test_independent_effect_settings_only_reach_ets2(self):
        values = {'ffbStrength': 65, 'trueForceEnabled': False, 'engineVibration': 80}
        command = auto.child_command(227300, settings=values)
        self.assertEqual(command[command.index('--ffb-strength')+1], '65')
        self.assertEqual(command[command.index('--engine-vibration')+1], '80')
        self.assertIn('--classic-only', command)
        self.assertNotIn('--engine-emulation', command)
        dirt = auto.child_command(690790, settings=values)
        self.assertNotIn('--ffb-strength', dirt)
        self.assertNotIn('--classic-only', dirt)
        self.assertIn('--manual', dirt)

    def test_live_engine_preferences_keep_combined_transport_without_force_restart(self):
        values={'ffbStrength':65,'trueForceEnabled':False,'engineVibration':40}
        command=auto.child_command(227300,settings=values,settings_file='/tmp/settings.json')
        self.assertEqual(command[command.index('--settings-file')+1],'/tmp/settings.json')
        self.assertIn('--engine-emulation',command)
        self.assertNotIn('--classic-only',command)
        self.assertNotIn('--settings-file',auto.child_command(690790,settings_file='/tmp/settings.json'))

    def test_connection_status_does_not_claim_force_from_spawn_or_ready(self):
        state = {'backendReady':False,'inputFfb':'unknown','telemetry':'unknown'}
        auto.connection_line('Starting backend', state)
        self.assertEqual(state, {'backendReady':False,'inputFfb':'unknown','telemetry':'unknown'})
        auto.connection_line('BRIDGE_LISTENING: Ready for the game', state)
        self.assertTrue(state['backendReady'])
        self.assertEqual(state['inputFfb'], 'unknown')
        auto.connection_line('ETS2_STATUS: input_ffb=waiting; telemetry=live; effects=0', state)
        self.assertEqual(state['inputFfb'], 'waiting')
        self.assertEqual(state['telemetry'], 'live')
        auto.connection_line('ETS2_STATUS: input_ffb=connected; telemetry=live; effects=1', state)
        self.assertEqual(state['inputFfb'], 'connected')

    def test_invalid_settings_start_no_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'settings.json';path.write_text('{broken')
            with patch.object(auto.subprocess,'Popen') as spawn:
                with self.assertRaises(ValueError):auto.run(settings_file=path)
                spawn.assert_not_called()

    def test_exact_executable_detection(self):
        self.assertEqual(auto.detect('/games/dirtrally2.exe\n/games/eurotrucks2.exe\n'), [690790,227300])
        self.assertEqual(auto.detect('/games/notdirtrally2.exe\nSteam.exe'), [])
    def test_crossover_windows_process_paths(self):
        self.assertEqual(auto.detect(r'A:\SteamLibrary\steamapps\common\Euro Truck Simulator 2\bin\win_x64\eurotrucks2.exe'), [227300])
        self.assertEqual(auto.detect(r'A:\games\DIRTRALLY2.EXE'), [690790])
        self.assertEqual(auto.detect(r'A:\games\not_eurotrucks2.exe'), [])
    def test_missing_patch_preserves_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'trusted'; source.write_bytes(b'owned')
            target=Path(tmp)/'game/plugin.dll'
            entries=[(target,auto.digest(source),source)]
            with patch.object(auto,'components',return_value=entries):
                self.assertEqual(auto.installation(227300),'patch')
                self.assertFalse(target.exists())
                auto.installation(227300,patch=True)
                self.assertEqual(target.read_bytes(),b'owned')
                self.assertEqual(auto.installation(227300),'installed')
                target.write_bytes(b'foreign')
                with self.assertRaises(ValueError):auto.installation(227300,patch=True)
                self.assertEqual(target.read_bytes(),b'foreign')
    def test_preflight_prevents_partial_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'trusted'; source.write_bytes(b'owned')
            target=Path(tmp)/'missing'; conflict=Path(tmp)/'foreign'; conflict.write_bytes(b'mod')
            with patch.object(auto,'components',return_value=[(target,auto.digest(source),source),(conflict,auto.digest(source),source)]):
                with self.assertRaises(ValueError):auto.installation(227300,patch=True)
                self.assertFalse(target.exists())
    def test_single_owner_switch_and_cleanup(self):
        events=[]
        class Child:
            def __init__(self,command,**kwargs):self.command=command;events.append(('start',command));self.stopped=False;self.stdout=[]
            def poll(self):return 0 if self.stopped else None
            def send_signal(self,_):self.stopped=True;events.append(('stop',self.command))
            def wait(self):events.append(('wait',self.command))
        snapshots=iter(['dirtrally2.exe','eurotrucks2.exe','eurotrucks2.exe\ndirtrally2.exe',''])
        def processes(*a,**kw):
            try:return next(snapshots)
            except StopIteration:raise KeyboardInterrupt
        with patch.object(auto.subprocess,'check_output',side_effect=processes),patch.object(auto.subprocess,'Popen',side_effect=Child),patch.object(auto,'installation',return_value='installed'),patch.object(auto,'child_command',side_effect=lambda id, **kwargs:[id]),patch.object(auto.time,'sleep'):
            with self.assertRaises(KeyboardInterrupt):auto.run()
        self.assertEqual(events,[('start',[690790]),('stop',[690790]),('wait',[690790]),('start',[227300]),('stop',[227300]),('wait',[227300])])

    def test_settings_file_is_resolved_for_each_detected_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings=Path(tmp)/'settings.json'
            settings.write_text(json.dumps({'version':1,'games':{'227300':{'ffbStrength':72,'trueForceEnabled':False,'engineVibration':91}}}))
            class Child:
                stdout=[]
                def poll(self):return None
                def send_signal(self,_):pass
                def wait(self):pass
            snapshots=iter(['eurotrucks2.exe'])
            def processes(*a,**kw):
                try:return next(snapshots)
                except StopIteration:raise KeyboardInterrupt
            with patch.object(auto.subprocess,'check_output',side_effect=processes),patch.object(auto.subprocess,'Popen',return_value=Child()) as spawn,patch.object(auto,'installation',return_value='installed'),patch.object(auto.time,'sleep'),contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(KeyboardInterrupt):auto.run(settings_file=settings)
            args=spawn.call_args.args[0]
            self.assertEqual(args[args.index('--ffb-strength')+1], '72')
            self.assertIn('--engine-emulation',args)
            self.assertEqual(args[args.index('--settings-file')+1],str(settings))
            states=[json.loads(x.split(': ',1)[1]) for x in output.getvalue().splitlines() if x.startswith('AUTO_STATE:')]
            self.assertEqual(states[-1]['appid'],227300)
            self.assertEqual(states[-1]['phase'],'connecting')
            self.assertFalse(states[-1]['backendReady'])
