# SPDX-License-Identifier: GPL-3.0-only
"""SDK lifecycle and status fixtures: no real Wine, games, HID or SDK calls."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
import auto_bridge
import sdk_game


class SDKLifecycleTests(unittest.TestCase):
    def fixture(self, root):
        session = root / 'App Support/Profiles/accepted-dirt'; session.mkdir(parents=True)
        bottle = root / 'Custom Bottles/Steam Games'; bottle.mkdir(parents=True)
        manifest = {'main_steam_experiment': True, 'source_bottle': str(bottle),
                    'game_exe': str(root / 'Game Library/DiRT Rally 2.0/dirtrally2.exe')}
        (session / 'manifest.json').write_text(json.dumps(manifest))
        return session, bottle, manifest

    def test_shared_stop_location_is_stable_when_session_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); session, bottle, manifest = self.fixture(root)
            self.assertEqual(sdk_game.stop_paths(session, manifest), [bottle / 'g923-sdk-stop', session / 'sdk-stop'])
            self.assertEqual(sdk_game.stop_paths(root / 'new-session', manifest)[0], bottle / 'g923-sdk-stop')
            self.assertEqual(sdk_game.stop_paths(session, {}), [session / 'sdk-stop'])
            with patch.object(sdk_game, 'load', return_value=manifest):
                environment = sdk_game.environment(session)
            self.assertEqual(environment['G923_SDK_STOP_FILE'], sdk_game.windows(bottle / 'g923-sdk-stop'))
            self.assertEqual(environment['G923_SDK_TRACE'], '1')

    def test_rearming_clears_shared_and_legacy_stop_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, manifest = self.fixture(Path(tmp))
            keep = bottle / 'other-component.stop'; keep.write_text('preserve')
            for stop in sdk_game.stop_paths(session, manifest): stop.touch(mode=0o600)
            sdk_game.clear_stop_requests(session, manifest)
            self.assertTrue(all(not stop.exists() for stop in sdk_game.stop_paths(session, manifest)))
            self.assertEqual(keep.read_text(), 'preserve')
            sdk_game.clear_stop_requests(session, manifest)  # Already armed is harmless.

    def test_rearming_preserves_symlink_and_hardlinked_stop_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); session, bottle, manifest = self.fixture(root)
            original = root / 'original'; original.write_text('preserve')
            stop = bottle / 'g923-sdk-stop'; stop.symlink_to(original)
            with self.assertRaisesRegex(ValueError, 'Unsafe SDK stop'):
                sdk_game.clear_stop_requests(session, manifest)
            self.assertTrue(stop.is_symlink()); self.assertEqual(original.read_text(), 'preserve')
            stop.unlink(); os.link(original, stop)
            with self.assertRaisesRegex(ValueError, 'Unsafe SDK stop'):
                sdk_game.clear_stop_requests(session, manifest)
            self.assertTrue(stop.is_file()); self.assertEqual(original.read_text(), 'preserve')

    def test_stopping_main_bottle_signals_both_paths_without_running_wine(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, manifest = self.fixture(Path(tmp))
            with patch.object(sdk_game, 'load', return_value=manifest), \
                    patch.object(sdk_game.time, 'sleep'), \
                    patch.object(sdk_game.subprocess, 'run', side_effect=AssertionError('Main Steam must remain open')), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sdk_game.stop(session), 0)
            for stop in sdk_game.stop_paths(session, manifest):
                self.assertTrue(stop.is_file())
                self.assertEqual(stop.stat().st_mode & 0o777, 0o600)
            self.assertTrue((session / 'host-stop').is_file())

    def test_automatic_arm_clears_both_stops_before_game_and_input_is_not_trueforce(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); session, bottle, manifest = self.fixture(root)
            for stop in sdk_game.stop_paths(session, manifest): stop.touch(mode=0o600)
            profile = {'id': 'accepted-dirt', 'appid': 690790, 'name': 'DiRT Rally 2.0',
                       'session_dir': str(session), 'source_bottle': str(bottle),
                       'game_exe': manifest['game_exe'], 'runner_path': None}
            document = {'version': 1, 'profiles': [profile]}
            snapshots = iter(['', manifest['game_exe']])

            def processes(*args, **kwargs):
                try: return next(snapshots)
                except StopIteration: raise KeyboardInterrupt

            class Child:
                stdout = ['BRIDGE_LISTENING: Input publisher ready. Native TRUEFORCE connection has not been verified.\n']
                stopped = False
                def poll(self): return 0 if self.stopped else None
                def send_signal(self, value): self.stopped = True
                def wait(self): return 0

            def spawn(*args, **kwargs):
                self.assertTrue(all(not stop.exists() for stop in sdk_game.stop_paths(session, manifest)))
                return Child()

            class InlineThread:
                def __init__(self, target, args, **kwargs): self.target, self.args = target, args
                def start(self): self.target(*self.args)

            transport = {'state': 'missing', 'detail': 'Restart Steam to load the prepared TRUEFORCE transport'}
            with patch.object(auto_bridge, 'load_registry', return_value=document), \
                    patch.object(auto_bridge, 'installation', return_value='installed'), \
                    patch.object(auto_bridge, 'native_status', return_value=transport), \
                    patch.object(auto_bridge.subprocess, 'check_output', side_effect=processes), \
                    patch.object(auto_bridge.subprocess, 'Popen', side_effect=spawn), \
                    patch.object(auto_bridge.threading, 'Thread', InlineThread), \
                    patch.object(auto_bridge.time, 'sleep'), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(KeyboardInterrupt): auto_bridge.run(registry=root / 'registry.json')
            states = [json.loads(line.split(': ', 1)[1]) for line in output.getvalue().splitlines()
                      if line.startswith('AUTO_STATE: ')]
            connected = next(state for state in states if state.get('activeAppid') == 690790)
            self.assertTrue(connected['backendReady'])
            self.assertEqual(connected['nativeTransport'], 'missing')
            self.assertEqual(connected['inputFfb'], 'unknown')
            self.assertIn('Restart Steam', connected['detail'])
            self.assertNotIn('TRUEFORCE transport loaded', connected['detail'])


if __name__ == '__main__':
    unittest.main()
