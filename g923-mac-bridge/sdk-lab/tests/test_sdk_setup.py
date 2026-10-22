# SPDX-License-Identifier: GPL-3.0-only
"""SDK setup fixtures contain synthetic PE bytes, never proprietary DLL code."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import sdk_setup


def synthetic_sdk(machine=0x8664, bits=64, exports=True):
    data = bytearray(1024)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 128)
    data[128:132] = b'PE\0\0'
    struct.pack_into('<HH', data, 132, machine, 1)
    struct.pack_into('<H', data, 148, 240)
    optional = 152
    struct.pack_into('<H', data, optional, 0x20b if bits == 64 else 0x10b)
    struct.pack_into('<I', data, optional+60, 512)
    count, base = (108, 112) if bits == 64 else (92, 96)
    struct.pack_into('<I', data, optional+count, 16)
    if exports:
        struct.pack_into('<II', data, optional+base, 0x1000, 0x100)
        struct.pack_into('<IIIII', data, 512+20, 2, 2, 0x1040, 0x1050, 0x1060)
        struct.pack_into('<II', data, 512+0x40, 0x1180, 0x1190)
        struct.pack_into('<II', data, 512+0x50, 0x1070, 0x10a0)
        struct.pack_into('<HH', data, 512+0x60, 0, 1)
        for offset, name in ((0x70, b'logiTrueForceAvailable\0'), (0xa0, b'logiTrueForceSupported\0')):
            data[512+offset:512+offset+len(name)] = name
    section = optional+240
    data[section:section+8] = b'.text\0\0\0'
    struct.pack_into('<IIII', data, section+8, 512, 0x1000, 512, 512)
    return bytes(data)


class SDKSetup(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root/'Windows shared/SDK/trueforce_sdk_x64.dll'
        self.source.parent.mkdir(parents=True)
        self.data = synthetic_sdk()
        self.source.write_bytes(self.data)
        self.store = self.root/'Mac App Support/SDK'
        self.target = sdk_setup.managed_path(self.store)
        self.hash_patch = patch.object(sdk_setup, 'SDK_SHA', hashlib.sha256(self.data).hexdigest())
        self.hash_patch.start()
        self.addCleanup(self.hash_patch.stop)

    def test_status_is_read_only_and_missing_is_not_ready(self):
        result = sdk_setup.status(self.store)
        self.assertFalse(result['installed'])
        self.assertEqual(result['path'], str(self.target))
        self.assertFalse(self.store.exists())

    def test_import_verified_snapshot_and_repeat_is_idempotent(self):
        result = sdk_setup.import_sdk(self.source, self.store)
        self.assertTrue(result['installed'])
        self.assertEqual(result['version'], '1.3.12')
        self.assertEqual(self.target.read_bytes(), self.data)
        before = self.target.stat().st_mtime_ns
        sdk_setup.import_sdk(self.source, self.store)
        self.assertEqual(before, self.target.stat().st_mtime_ns)
        self.assertEqual(self.target.stat().st_mode & 0o777, stat.S_IRUSR|stat.S_IWUSR)
        self.assertEqual(list(self.target.parent.glob('.sdk-import-*')), [])

    def test_unknown_sdk_hash_refused_before_creating_store(self):
        self.source.write_bytes(self.data+b'changed')
        with self.assertRaisesRegex(ValueError, 'has not been validated'):
            sdk_setup.import_sdk(self.source, self.store)
        self.assertFalse(self.store.exists())

    def test_wrong_architecture_or_missing_exports_are_not_sdk(self):
        for data in (synthetic_sdk(0x14c, 32), synthetic_sdk(exports=False), b'bad DLL'):
            with self.subTest(data=data[:2]):
                self.source.write_bytes(data)
                with self.assertRaises(ValueError):
                    sdk_setup.import_sdk(self.source, self.store)
        self.assertFalse(self.store.exists())

    def test_hash_match_still_requires_valid_pe_and_trueforce_exports(self):
        for data in (b'bad DLL', synthetic_sdk(exports=False)):
            self.source.write_bytes(data)
            with patch.object(sdk_setup, 'SDK_SHA', hashlib.sha256(data).hexdigest()):
                with self.assertRaises(ValueError):
                    sdk_setup.import_sdk(self.source, self.store)

    def test_changed_destination_is_preserved_and_reported_not_ready(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b'important foreign DLL')
        self.assertFalse(sdk_setup.status(self.store)['installed'])
        with self.assertRaisesRegex(ValueError, 'was preserved'):
            sdk_setup.import_sdk(self.source, self.store)
        self.assertEqual(self.target.read_bytes(), b'important foreign DLL')

    def test_destination_symlink_is_preserved(self):
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(self.source)
        self.assertFalse(sdk_setup.status(self.store)['installed'])
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            sdk_setup.import_sdk(self.source, self.store)
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_sdk_directory_symlink_does_not_redirect_import(self):
        outside = self.root/'unrelated'; outside.mkdir()
        self.store.mkdir(parents=True)
        self.target.parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            sdk_setup.import_sdk(self.source, self.store)
        self.assertEqual(list(outside.iterdir()), [])

    def test_atomic_import_preserves_file_written_by_another_process(self):
        def concurrent_writer(source, target):
            Path(target).write_bytes(b'concurrent foreign DLL')
            raise FileExistsError('already exists')
        with patch.object(sdk_setup.os, 'link', side_effect=concurrent_writer):
            with self.assertRaisesRegex(ValueError, 'appeared'):
                sdk_setup.import_sdk(self.source, self.store)
        self.assertEqual(self.target.read_bytes(), b'concurrent foreign DLL')
        self.assertEqual(list(self.target.parent.glob('.sdk-import-*')), [])

    def test_discovery_handles_windows_and_shared_layouts_without_import(self):
        for index, relative in enumerate(('Program Files/Logi/Trueforce/1_3_12', 'Logi/Trueforce/1_3_12', 'Trueforce/1_3_12', '.')):
            root = self.root/str(index)
            dll = root/relative/sdk_setup.SDK_FILENAME
            dll.parent.mkdir(parents=True)
            dll.write_bytes(self.data)
            result = sdk_setup.candidates([root, dll, root])
            self.assertEqual(len(result), 1)
            self.assertTrue(result[0]['supported'])
            self.assertEqual(result[0]['path'], str(dll.resolve()))
        self.assertFalse(self.store.exists())

    def test_discovery_shows_unvalidated_versions_without_claiming_they_work(self):
        dll = self.root/'Windows/Program Files/Logi/Trueforce/2_0_0'/sdk_setup.SDK_FILENAME
        dll.parent.mkdir(parents=True)
        dll.write_bytes(self.data+b'new version')
        result = sdk_setup.candidates([self.root/'Windows'])
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]['supported'])
        self.assertIsNone(result[0]['version'])
        self.assertIn('has not been validated', result[0]['detail'])

    def test_cli_emits_structured_status_and_errors(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = sdk_setup.main(['status', '--store', str(self.store), '--json'])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(out.getvalue())['installed'])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = sdk_setup.main(['import', '--store', str(self.store), '--json'])
        self.assertEqual(code, 2)
        self.assertIn('error', json.loads(out.getvalue()))


if __name__ == '__main__':
    unittest.main()
