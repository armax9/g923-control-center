# SPDX-License-Identifier: GPL-3.0-only
"""Portable discovery/registry fixtures use no installed bottle or hardware."""
import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
import profile_store as store


class ProfileStoreTests(unittest.TestCase):
    def fixture(self, root, appid=227300):
        game = root / 'External Drive/Truck Library/steamapps/common/ETS2/bin/win_x64/eurotrucks2.exe'
        game.parent.mkdir(parents=True); game.write_bytes(b'exe')
        bottle = root / 'Custom Bottles/Truck Games'; bottle.mkdir(parents=True)
        (bottle / 'cxbottle.conf').write_text('fixture')
        session = root / 'Profiles/trucks'; session.mkdir(parents=True)
        (session / 'manifest.json').write_text(json.dumps({'game_exe': str(game), 'source_bottle': str(bottle)}))
        return {'id': 'trucks-one', 'appid': appid, 'name': 'Euro Truck Simulator 2',
                'game_exe': str(game), 'source_bottle': str(bottle),
                'runner_path': None, 'session_dir': str(session)}

    def test_missing_registry_and_import_are_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'not-created'
            with patch.object(store, 'default_profiles_dir', return_value=directory):
                self.assertEqual(store.load_registry(), {'version': 1, 'profiles': []})
                self.assertFalse(directory.exists())

    def test_register_round_trip_and_atomic_invalid_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); profile = self.fixture(root); registry = root / 'App Support/Profiles/registry.json'
            store.register(profile, registry)
            self.assertEqual(store.select_profile(227300, path=registry), profile)
            before = registry.read_bytes()
            broken = dict(profile, session_dir='../unsafe')
            with self.assertRaises(ValueError): store.register(broken, registry)
            self.assertEqual(registry.read_bytes(), before)
            self.assertEqual(registry.stat().st_mode & 0o777, 0o600)

    def test_bottle_names_and_steam_locations_are_not_assumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); profile = self.fixture(root)
            generated = store.profile_from_manifest(Path(profile['session_dir']), 227300)
            self.assertEqual(generated['source_bottle'], str(Path(profile['source_bottle']).resolve()))
            self.assertEqual(generated['game_exe'], str(Path(profile['game_exe']).resolve()))
            self.assertIsNone(generated['runner_path'])

    def test_duplicate_installations_are_ambiguous_not_first_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = self.fixture(Path(tmp)); second = dict(profile, id='trucks-two', session_dir=str(Path(tmp) / 'other'))
            document = {'version': 1, 'profiles': [profile, second]}
            with self.assertRaisesRegex(ValueError, 'Ambiguous'):store.select_profile(227300, document)
            self.assertEqual(store.select_profile(227300, document, 'trucks-two'), second)

    def test_registry_rejects_malformed_duplicate_and_unsafe_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); profile = self.fixture(root); path = root / 'registry.json'
            for raw in ['{"version":1,"version":1,"profiles":[]}', '{broken', '{"version":true,"profiles":[]}']:
                path.write_text(raw)
                with self.subTest(raw=raw), self.assertRaises(ValueError): store.load_registry(path)
            for field, value in [('id', '../game'), ('appid', True), ('source_bottle', 'relative'), ('session_dir', None)]:
                bad = dict(profile); bad[field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):store.validate({'version': 1, 'profiles': [bad]})
            with self.assertRaisesRegex(ValueError, 'Duplicate'):store.validate({'version': 1, 'profiles': [profile, profile]})

    def test_explicit_migration_preserves_bytes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / 'outputs/project'; project.mkdir(parents=True)
            fixture = self.fixture(root)
            source = root / 'outputs/G923 ETS2'; source.mkdir()
            manifest = {'game_exe': fixture['game_exe'], 'source_bottle': fixture['source_bottle'],
                        'mapping': '/tmp/crossover-ffb-1234567890/ffb-v2.bin',
                        'backend_hashes': {'G923TelemetryLab': 'unchanged-acceptance-hash'},
                        'installed_files': {'g923_bridge.dll': 'accepted-game-hash'}}
            (source / 'manifest.json').write_text(json.dumps(manifest))
            (source / 'G923TelemetryLab').write_bytes(b'accepted-native-backend')
            (source / 'g923_bridge.dll').write_bytes(b'accepted-windows-bridge')
            (source / 'run-old').mkdir(); (source / 'run-old/log').write_bytes(b'private old logs')
            registry = root / 'Application Support/G923 Control Center/Profiles/registry.json'
            game_before = Path(fixture['game_exe']).read_bytes()
            document = store.migrate_legacy(project, registry)
            self.assertEqual(len(document['profiles']), 1)
            session = Path(document['profiles'][0]['session_dir'])
            self.assertEqual(session.parent, registry.parent.resolve())
            self.assertEqual((session / 'G923TelemetryLab').read_bytes(), b'accepted-native-backend')
            self.assertFalse((session / 'run-old').exists())
            copied = json.loads((session / 'manifest.json').read_text())
            self.assertEqual(copied['mapping'], manifest['mapping'])
            self.assertEqual(copied['backend_hashes'], manifest['backend_hashes'])
            self.assertEqual(copied['installed_files'], manifest['installed_files'])
            self.assertEqual(Path(fixture['game_exe']).read_bytes(), game_before)
            self.assertEqual(store.migrate_legacy(project, registry), document)
            self.assertEqual(json.loads((source / 'manifest.json').read_text()), manifest)

    def test_new_sdk_profile_keeps_its_reviewed_private_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); profile = self.fixture(root, 690790); session = Path(profile['session_dir'])
            runner = session / 'runtime/bin/wine'; runner.parent.mkdir(parents=True); runner.write_bytes(b'reviewed-runtime')
            generated = store.profile_from_manifest(session, 690790, runner_path='/Applications/Other.app/wine')
            self.assertEqual(generated['runner_path'], str(runner.resolve()))

    def test_runtime_copy_materializes_external_and_rebases_internal_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'old/runtime'; source.mkdir(parents=True)
            external = root / 'original app/library'; external.parent.mkdir(); external.write_bytes(b'original native library')
            (source / 'external').symlink_to(external)
            own = source / 'library'; own.write_bytes(b'owned native library')
            (source / 'internal').symlink_to(own)
            destination = root / 'new/runtime'
            store._portable_runtime(source, destination)
            self.assertFalse((destination / 'external').is_symlink())
            self.assertFalse((destination / 'internal').readlink().is_absolute())
            external.unlink(); own.unlink()
            self.assertEqual((destination / 'external').read_bytes(), b'original native library')
            self.assertEqual((destination / 'internal').read_bytes(), b'owned native library')
