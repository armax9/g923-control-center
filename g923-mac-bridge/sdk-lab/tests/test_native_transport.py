# SPDX-License-Identifier: GPL-3.0-only
"""Native runtime configuration fixtures never run Wine or send HID reports."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
import native_transport as transport


class NativeTransportTests(unittest.TestCase):
    def fixture(self, root, newline='\n', extra=''):
        root = root.resolve()
        bottle = root / 'Bottles with spaces/Truck and Rally'; bottle.mkdir(parents=True)
        session = root / 'Profiles/Rally'; session.mkdir(parents=True)
        runtime = session / 'runtime'
        for relative, data in [('bin/wine', b'not executed'),
                               ('etc/CrossOver.conf', b'[CrossOver]\n"ProductVersion" = "27.0.fixture"\n"BuildTimestamp" = "20261006T113703Z"\n'),
                               ('lib/wine/x86_64-unix/winebus.so', b'accepted unix transport'),
                               ('lib/wine/x86_64-windows/winebus.sys', b'accepted windows transport')]:
            path = runtime / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        text = ('[Bottle]\n"WineArch" = "win64"\n"Preview" = "1"\n'
                '"Version" = "27.0.fixture"\n"Timestamp" = "20261006T113703Z"\n'
                '[EnvironmentVariables]\n"OTHER_SETTING" = "keep me"\n' + extra)
        (bottle / 'cxbottle.conf').write_bytes(text.replace('\n', newline).encode())
        manifest = {'source_bottle': str(bottle), 'runtime_hashes': {
            relative: hashlib.sha256((runtime / 'lib/wine' / relative).read_bytes()).hexdigest()
            for relative in transport.MODULES}}
        return session, bottle, runtime, manifest

    def configure(self, session, manifest):
        with patch.object(transport, 'require_stopped'):
            return transport.configure(session, manifest)

    def restore(self, session, manifest):
        with patch.object(transport, 'require_stopped'):
            return transport.restore(session, manifest)

    def test_plan_and_check_are_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp))
            before = (bottle / 'cxbottle.conf').read_bytes()
            item = transport.plan(session, manifest)
            self.assertEqual(item['runtime'], str(runtime))
            self.assertTrue(item['change_required'])
            self.assertIn('"CX_ROOT" = "${WINEPREFIX}/g923-native-runtime"', item['after'])
            self.assertIn('"G923_SDK_TRACE" = "1"', item['after'])
            self.assertFalse(transport.check_config(session, manifest)['configured'])
            self.assertEqual((bottle / 'cxbottle.conf').read_bytes(), before)
            self.assertFalse((session / transport.JOURNAL_NAME).exists())
            self.assertFalse((bottle / transport.LINK_NAME).exists())

    def test_configuration_is_owned_atomic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp))
            before = (bottle / 'cxbottle.conf').read_bytes()
            self.assertTrue(self.configure(session, manifest)['configured'])
            self.assertEqual((session / transport.BACKUP_NAME).read_bytes(), before)
            self.assertEqual((bottle / transport.LINK_NAME).resolve(), runtime)
            journal = (session / transport.JOURNAL_NAME).read_bytes()
            self.assertEqual(json.loads(journal)['environment'], transport.ENVIRONMENT)
            self.assertTrue(self.configure(session, manifest)['configured'])
            self.assertEqual((session / transport.JOURNAL_NAME).read_bytes(), journal)
            self.assertEqual((session / transport.BACKUP_NAME).read_bytes(), before)

    def test_matching_bottle_version_and_timestamp_are_required(self):
        for field, value in [('Version', 'wrong'), ('Timestamp', 'wrong')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                session, bottle, runtime, manifest = self.fixture(Path(tmp))
                path = bottle / 'cxbottle.conf'
                path.write_text(path.read_text().replace('"' + field + '" = "', '"' + field + '" = "' + value))
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    self.configure(session, manifest)
                self.assertFalse((session / transport.BACKUP_NAME).exists())

    def test_runtime_module_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp))
            (runtime / 'lib/wine/x86_64-unix/winebus.so').write_bytes(b'stock transport')
            with self.assertRaisesRegex(ValueError, 'transport changed'):
                self.configure(session, manifest)
            self.assertFalse((session / transport.JOURNAL_NAME).exists())

    def test_other_runtime_and_unowned_link_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp), extra='"CX_ROOT" = "/another/runtime"\n')
            before = (bottle / 'cxbottle.conf').read_bytes()
            with self.assertRaisesRegex(ValueError, 'unowned bottle runtime override'):
                self.configure(session, manifest)
            self.assertEqual((bottle / 'cxbottle.conf').read_bytes(), before)
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp))
            (bottle / transport.LINK_NAME).symlink_to(runtime, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'unowned bottle runtime link'):
                self.configure(session, manifest)
            self.assertTrue((bottle / transport.LINK_NAME).is_symlink())

    def test_config_symlink_and_duplicate_entries_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp))
            path = bottle / 'cxbottle.conf'; other = bottle / 'real.conf'; path.rename(other); path.symlink_to(other)
            with self.assertRaisesRegex(ValueError, 'regular file'):
                self.configure(session, manifest)
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp), extra='"G923_SDK_TRACE"="1"\n"G923_SDK_TRACE"="1"\n')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                self.configure(session, manifest)
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp), extra='[EnvironmentVariables]\n"OTHER"="value"\n')
            with self.assertRaisesRegex(ValueError, 'Duplicate CrossOver configuration section'):
                self.configure(session, manifest)

    def test_restore_returns_exact_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp))
            before = (bottle / 'cxbottle.conf').read_bytes()
            self.configure(session, manifest)
            self.assertFalse(self.restore(session, manifest)['configured'])
            self.assertEqual((bottle / 'cxbottle.conf').read_bytes(), before)
            self.assertFalse((bottle / transport.LINK_NAME).exists())

    def test_restore_preserves_subsequent_user_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp))
            self.configure(session, manifest)
            path = bottle / 'cxbottle.conf'
            path.write_text(path.read_text() + '"NEW_SETTING" = "user value"\n')
            self.restore(session, manifest)
            after = path.read_text()
            self.assertIn('"NEW_SETTING" = "user value"', after)
            self.assertIn('"OTHER_SETTING" = "keep me"', after)
            self.assertNotIn('"CX_ROOT"', after)
            self.assertNotIn('"G923_SDK_TRACE"', after)

    def test_existing_trace_is_not_removed_by_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp), extra='"G923_SDK_TRACE" = "1"\n')
            self.configure(session, manifest)
            path = bottle / 'cxbottle.conf'; path.write_text(path.read_text() + '"NEW_SETTING"="keep"\n')
            self.restore(session, manifest)
            self.assertIn('"G923_SDK_TRACE" = "1"', path.read_text())

    def test_config_crlf_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp), newline='\r\n')
            self.configure(session, manifest)
            data = (bottle / 'cxbottle.conf').read_bytes()
            self.assertNotIn(b'\n', data.replace(b'\r\n', b''))

    def test_failed_journal_commit_restores_config_and_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp))
            before = (bottle / 'cxbottle.conf').read_bytes()
            save = transport._save; calls = []
            def fail_commit(path, data):
                calls.append(data['state'])
                if len(calls) == 2:
                    raise OSError('fixture journal commit failure')
                return save(path, data)
            with patch.object(transport, '_save', side_effect=fail_commit), self.assertRaisesRegex(OSError, 'fixture'):
                self.configure(session, manifest)
            self.assertEqual((bottle / 'cxbottle.conf').read_bytes(), before)
            self.assertFalse((bottle / transport.LINK_NAME).exists())
            self.assertTrue(self.configure(session, manifest)['configured'])

    def test_stale_atomic_write_does_not_overwrite_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config'; path.write_bytes(b'new user config')
            with self.assertRaisesRegex(ValueError, 'changed during'):
                transport._atomic(path, b'bridge config', expected=b'old config')
            self.assertEqual(path.read_bytes(), b'new user config')

    def test_interrupted_completed_write_requires_journal_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp))
            self.configure(session, manifest)
            path = session / transport.JOURNAL_NAME; journal = json.loads(path.read_text())
            journal['state'] = 'prepared'; path.write_text(json.dumps(journal))
            self.assertFalse(transport.check_config(session, manifest)['configured'])
            self.assertTrue(self.configure(session, manifest)['configured'])

    @unittest.skipUnless(Path('/Applications/CrossOver Preview.app/Contents/SharedSupport/CrossOver/bin/wine').is_file(), 'CrossOver Perl wrapper unavailable')
    def test_real_launcher_preflight_only_runs_unix_printenv(self):
        with tempfile.TemporaryDirectory() as tmp:
            session, bottle, runtime, manifest = self.fixture(Path(tmp))
            # Real launcher resolves these dummy executable paths but never runs them.
            for relative in ['bin/wineserver-x86', 'lib/wine/x86_64-unix/wine']:
                path = runtime / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'NEVER EXECUTE'); path.chmod(0o755)
            self.configure(session, manifest)
            before = sorted(str(p.relative_to(bottle)) for p in bottle.rglob('*'))
            wrapper = Path('/Applications/CrossOver Preview.app/Contents/SharedSupport/CrossOver/bin/wine')
            env = transport.environment_preflight(wrapper, bottle)
            self.assertEqual(Path(env['CX_ROOT']).resolve(), runtime)
            self.assertEqual(Path(env['WINELOADER']).resolve(), runtime / 'lib/wine/x86_64-unix/wine')
            self.assertEqual(Path(env['WINESERVER']).resolve(), runtime / 'bin/wineserver-x86')
            self.assertIn(str(bottle / transport.LINK_NAME), env['WINEDLLPATH'])
            self.assertEqual(sorted(str(p.relative_to(bottle)) for p in bottle.rglob('*')), before)


if __name__ == '__main__':
    unittest.main()
