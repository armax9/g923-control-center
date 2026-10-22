# SPDX-License-Identifier: GPL-3.0-only
"""Private mapping lifecycle fixtures. No SDK, Wine, HID or motor access."""
import contextlib
import io
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
import sdk_game


class SDKMappingTests(unittest.TestCase):
    def test_missing_temporary_directory_is_recreated_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            mapping = Path(tmp) / 'crossover-ffb-1234567890/ffb-v2.bin'
            self.assertEqual(sdk_game.prepare_input_mapping(mapping), mapping)
            self.assertEqual(mapping.parent.stat().st_mode & 0o777, 0o700)
            self.assertFalse(mapping.exists())  # The publisher must create it exclusively.

    def test_owned_stale_mapping_is_removed_for_exclusive_publisher(self):
        with tempfile.TemporaryDirectory() as tmp:
            mapping = Path(tmp) / 'ffb-v2.bin'
            mapping.write_bytes(bytes(8192)); mapping.chmod(0o600)
            sdk_game.prepare_input_mapping(mapping)
            self.assertFalse(mapping.exists())

    def test_symlink_directory_and_file_are_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); real = root / 'real'; real.mkdir(mode=0o700)
            linked = root / 'linked'; linked.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'directory'):
                sdk_game.prepare_input_mapping(linked / 'ffb-v2.bin')
            self.assertTrue(linked.is_symlink())
            for target in (root / 'missing', real / 'original'):
                if target.name == 'original':
                    target.write_bytes(bytes(8192)); target.chmod(0o600)
                mapping = real / 'ffb-v2.bin'; mapping.symlink_to(target)
                with self.assertRaisesRegex(ValueError, 'Unsafe stale'):
                    sdk_game.prepare_input_mapping(mapping)
                self.assertTrue(mapping.is_symlink())
                if target.exists(): self.assertEqual(target.stat().st_size, 8192)
                mapping.unlink()

    def test_shared_or_foreign_directory_is_not_chmodded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); root.chmod(0o755)
            with self.assertRaisesRegex(ValueError, 'directory'):
                sdk_game.prepare_input_mapping(root / 'ffb-v2.bin')
            self.assertEqual(root.stat().st_mode & 0o777, 0o755)
            root.chmod(0o700)
            with patch.object(sdk_game.os, 'getuid', return_value=os.getuid() + 1):
                with self.assertRaisesRegex(ValueError, 'directory'):
                    sdk_game.prepare_input_mapping(root / 'ffb-v2.bin')

    def test_malformed_public_hardlinked_and_foreign_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); mapping = root / 'ffb-v2.bin'
            for size, mode in ((8191, 0o600), (8193, 0o600), (8192, 0o644)):
                with self.subTest(size=size, mode=mode):
                    mapping.write_bytes(bytes(size)); mapping.chmod(mode)
                    with self.assertRaisesRegex(ValueError, 'Unsafe stale'):
                        sdk_game.prepare_input_mapping(mapping)
                    self.assertEqual(mapping.stat().st_size, size)
                    mapping.unlink()
            mapping.write_bytes(bytes(8192)); mapping.chmod(0o600)
            original = root / 'other-link'; os.link(mapping, original)
            with self.assertRaisesRegex(ValueError, 'Unsafe stale'):
                sdk_game.prepare_input_mapping(mapping)
            self.assertTrue(mapping.is_file()); original.unlink()
            uid = os.getuid()
            with patch.object(sdk_game.os, 'getuid', side_effect=[uid, uid + 1]):
                with self.assertRaisesRegex(ValueError, 'Unsafe stale'):
                    sdk_game.prepare_input_mapping(mapping)
            self.assertTrue(mapping.is_file())

    def test_relative_mapping_is_rejected_before_directory_creation(self):
        with self.assertRaisesRegex(ValueError, 'absolute'):
            sdk_game.prepare_input_mapping(Path('crossover-ffb-fixture/ffb-v2.bin'))

    def test_manual_start_prepares_missing_directory_before_publisher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); mapping = root / 'clean-tmp/ffb-v2.bin'
            child = MagicMock(); child.poll.side_effect = [None, 0, 0]
            real_open = os.open

            def open_lock(path, *args, **kwargs):
                if str(path).startswith('/tmp/g923-mac-bridge-'):
                    path = root / 'test-owner.lock'
                return real_open(path, *args, **kwargs)

            def spawn(arguments, **kwargs):
                self.assertEqual(arguments[0], '/fixture/g923-input')
                self.assertTrue(mapping.parent.is_dir())
                self.assertEqual(mapping.parent.stat().st_mode & 0o777, 0o700)
                self.assertFalse(mapping.exists())
                header = bytearray(8192); struct.pack_into('<I', header, 68, 1)
                mapping.write_bytes(header); mapping.chmod(0o600)
                return child

            manifest = {'main_steam_experiment': True, 'game_exe': str(root / 'game.exe'),
                        'mapping': str(mapping)}
            with patch.object(sdk_game.os, 'open', side_effect=open_lock), \
                    patch.object(sdk_game, 'check'), patch.object(sdk_game, 'stop'), \
                    patch.object(sdk_game, 'environment', return_value={}), \
                    patch.object(sdk_game, 'payload', return_value=Path('/fixture/g923-input')), \
                    patch.object(sdk_game.subprocess, 'Popen', side_effect=spawn) as publisher, \
                    patch.object(sdk_game.subprocess, 'run', side_effect=AssertionError('No Wine, SDK or game launch')), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaisesRegex(RuntimeError, 'Input publisher exited'):
                    sdk_game.start(root, manifest, launch_game=False)
            self.assertEqual(publisher.call_count, 1)
            self.assertIn('Native TRUEFORCE connection has not been verified', output.getvalue())


if __name__ == '__main__':
    unittest.main()
