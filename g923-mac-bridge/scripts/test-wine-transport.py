#!/usr/bin/env python3
"""Offline source/build policy tests. No Wine execution or hardware access."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('wine_transport_build', Path(__file__).with_name('build-wine-transport.py'))
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class SourcePolicy(unittest.TestCase):
    def test_catalog_pins_pair_and_source(self):
        catalog = json.loads(build.CATALOG.read_text())
        entry = catalog['builds'][0]
        self.assertEqual(entry['source']['commit'], build.SOURCE_COMMIT)
        self.assertEqual(entry['source']['archive_sha256'], build.ARCHIVE_SHA256)
        self.assertEqual(entry['source']['patch_sha256'], build.digest(build.ROOT / 'patches' / build.PATCHES[0]))
        self.assertEqual(set(entry['modules']), {'x86_64-unix/winebus.so', 'x86_64-windows/winebus.sys'})
        self.assertEqual(set(entry['original_module_hashes']), set(entry['modules']))

    def test_wrong_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'archive.tar.gz'; p.write_bytes(b'not the source')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                build.validate_source(None, p)

    def test_other_wine_revision_is_rejected(self):
        with patch.object(build, 'run', return_value='a' * 40):
            with self.assertRaisesRegex(ValueError, 'pinned Wine'):
                build.validate_source(Path('/source'), None)

    def test_dirty_source_is_rejected(self):
        with patch.object(build, 'run', side_effect=[build.SOURCE_COMMIT, ' M dlls/winebus.sys/main.c']):
            with self.assertRaisesRegex(ValueError, 'modified tracked'):
                build.validate_source(Path('/source'), None)

    def test_plan_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'build with spaces'
            with patch.object(build, 'validate_source', return_value={'commit': build.SOURCE_COMMIT}):
                self.assertEqual(build.main(['--source', tmp, '--output', str(out)]), 0)
            self.assertFalse(out.exists())

    def test_source_bundle_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'existing.tar.xz'; target.write_bytes(b'keep')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                build.bundle_source(None, Path(tmp) / 'source.tar.gz', target)
            self.assertEqual(target.read_bytes(), b'keep')

    def test_source_archive_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'unsafe.tar'; dest = Path(tmp) / 'dest'
            with tarfile.open(archive, 'w') as tf:
                item = tarfile.TarInfo('wine-wine-11.17/../../escaped'); item.size = 1
                tf.addfile(item, io.BytesIO(b'x'))
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                build.extract_source(archive, dest)
            self.assertFalse((Path(tmp) / 'escaped').exists())

    def test_source_archive_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'link.tar'; dest = Path(tmp) / 'dest'
            with tarfile.open(archive, 'w') as tf:
                item = tarfile.TarInfo('wine-wine-11.17/link'); item.type = tarfile.SYMTYPE; item.linkname = '/tmp'
                tf.addfile(item)
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                build.extract_source(archive, dest)


if __name__ == '__main__':
    unittest.main()
