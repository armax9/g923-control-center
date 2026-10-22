# SPDX-License-Identifier: GPL-3.0-only
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
import auto_bridge as auto
import ets2
from profile_store import save_registry


class PortableBackendTests(unittest.TestCase):
    def profile(self, root, name='one'):
        return {'id': 'trucks-' + name, 'appid': 227300, 'name': 'Euro Truck Simulator 2',
                'game_exe': str(root / name / 'Games/Truck 2/bin/win_x64/eurotrucks2.exe'),
                'source_bottle': str(root / name / 'My Windows Games'), 'runner_path': None,
                'session_dir': str(root / name / 'Profiles/Truck 2')}

    def test_profile_paths_reach_only_the_corresponding_backend(self):
        profile = self.profile(Path('/fixture'))
        command = auto.child_command(227300, profile=profile)
        self.assertEqual(command[command.index('--installation') + 1], profile['session_dir'])
        self.assertIn('--manual', command)
        profile['appid'] = 690790
        command = auto.child_command(690790, profile=profile)
        self.assertEqual(command[command.index('--installation') + 1], profile['session_dir'])
        self.assertNotIn('G923 Installation', command)

    def test_duplicate_exe_basename_is_ambiguous_but_concrete_path_selects(self):
        one, two = self.profile(Path('/fixture'), 'one'), self.profile(Path('/fixture'), 'two')
        document = {'version': 1, 'profiles': [one, two]}
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):auto.running_profiles('eurotrucks2.exe', document)
        self.assertEqual(auto.running_profiles(one['game_exe'], document), [one])
        windows_z = 'Z:' + two['game_exe'].replace('/', '\\')
        self.assertEqual(auto.running_profiles(windows_z, document), [two])

    def test_explicit_empty_registry_does_not_spawn_legacy_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / 'registry.json'; save_registry({'version': 1, 'profiles': []}, registry)
            snapshots = iter(['eurotrucks2.exe'])
            def processes(*args, **kwargs):
                try:return next(snapshots)
                except StopIteration:raise KeyboardInterrupt
            with patch.object(auto.subprocess, 'check_output', side_effect=processes), patch.object(auto.subprocess, 'Popen') as spawn, patch.object(auto.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(KeyboardInterrupt):auto.run(registry=registry)
            spawn.assert_not_called()

    def test_ets2_state_uses_manifest_game_location_and_optional_mod(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); session = root / 'App Support/Profiles/ets2'; session.mkdir(parents=True)
            game = root / 'Any external library/Truck Game/bin/win_x64/eurotrucks2.exe'; game.parent.mkdir(parents=True); game.write_bytes(b'exe')
            native = session / 'G923TelemetryLab'; native.write_bytes(b'backend')
            bridge = game.parent / 'g923_bridge.dll'; bridge.write_bytes(b'bridge')
            manifest = {'game_exe': str(game), 'preserved_dlaa_sha': None,
                        'backend_hashes': {'G923TelemetryLab': ets2.sha(native)},
                        'installed_files': {'g923_bridge.dll': ets2.sha(bridge)}}
            (session / 'manifest.json').write_text(json.dumps(manifest))
            with patch.object(ets2, 'INSTALL', session), patch.object(ets2, 'GAME', None):
                self.assertEqual(ets2.state(), manifest)
                self.assertEqual(ets2.GAME, game.parent)
                (game.parent / 'dinput8.dll').write_bytes(b'new mod')
                with self.assertRaisesRegex(ValueError, 'changed'):ets2.state()
                # Never rename or overwrite an independently installed mod.
                self.assertEqual((game.parent / 'dinput8.dll').read_bytes(), b'new mod')

    def test_optional_dlaa_absence_and_component_hashes_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); profile = self.profile(root)
            session = Path(profile['session_dir']); session.mkdir(parents=True)
            game = Path(profile['game_exe']); game.parent.mkdir(parents=True); game.write_bytes(b'exe')
            (session / 'manifest.json').write_text(json.dumps({'game_exe': str(game), 'source_bottle': profile['source_bottle'], 'preserved_dlaa_sha': None, 'backend_hashes': {}, 'installed_files': {}}))
            self.assertEqual(auto.components(227300, profile), [])
            (game.parent / 'dinput8.dll').write_bytes(b'foreign')
            with self.assertRaisesRegex(ValueError, 'changed'):auto.components(227300, profile)

    def test_runtime_environment_uses_actual_crossover_runner_and_bottle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); bottle = root / 'custom root/Heavy Trucks'; bottle.mkdir(parents=True); (bottle / 'cxbottle.conf').write_text('fixture')
            runner = root / 'Applications/CrossOver Preview.app/Contents/SharedSupport/CrossOver/bin/wine'; runner.parent.mkdir(parents=True); runner.write_bytes(b'runner')
            manifest = {'source_bottle': str(bottle), 'runner_path': str(runner)}
            args = ets2.runtime_command(manifest); environment = ets2.env(manifest)
            self.assertEqual(args[0], str(runner))
            self.assertEqual(args[args.index('--bottle') + 1], 'Heavy Trucks')
            self.assertEqual(environment['CX_BOTTLE_PATH'], str(bottle.parent.resolve()))
            self.assertEqual(environment['WINEPREFIX'], str(bottle.resolve()))
            self.assertNotIn('G923 Installation', ' '.join(args))

    def test_only_accepted_playstation_protocol_direction_skips_user_measurement(self):
        accepted = {'device_model': '046d:c266', 'tf_motor_sign': 1,
                    'tf_motor_sign_source': 'G923 PlayStation protocol profile, hardware accepted 2026-10-22'}
        self.assertTrue(ets2.accepted_tf_direction(accepted))
        self.assertTrue(ets2.accepted_tf_direction({'native_tf_direction_measured': True}))
        self.assertFalse(ets2.accepted_tf_direction({}))
        for key, value in [('device_model', '046d:c26e'), ('tf_motor_sign', -1), ('tf_motor_sign_source', 'guessed')]:
            self.assertFalse(ets2.accepted_tf_direction(dict(accepted, **{key: value})))
