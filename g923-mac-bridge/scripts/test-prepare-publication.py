#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Source publication boundaries and reproducibility; no apps or hardware."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location('publication', Path(__file__).with_name('prepare-publication.py'))
publication = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def fixture(self, directory):
        root, mescon = directory / 'project', directory / 'mescon-telemetry'
        for source, names in ((root, publication.REQUIRED_MAIN), (mescon, publication.REQUIRED_MESCON)):
            for name in names:
                file = source / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('{}\n' if file.suffix == '.json' else 'Public source fixture\n')
        for name, content in {
                '.gitignore': '/build/\n*.log\n',
                'src/main.cpp': 'int main() { return 0; }\n',
                'scripts/build.sh': '#!/bin/sh\nexit 0\n',
                'scripts/build-release-components.py': '# source builder\n',
                'scripts/test-release-components.py': '# source builder tests\n',
                'docs/publication/RELEASE.md': '[SDK](../LOGITECH_SDK_SETUP.md)\n',
                'docs/publication/POST_RU.md': '\u0427\u0430\u0441\u0442\u043d\u043e\u0432\u0438\u043a \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438\n',
                'docs/LOGITECH_SDK_SETUP.md': 'SDK import instructions\n',
                'docs/WINE_TRANSPORT_SOURCE.md': 'Wine transport source instructions\n',
                'assets/control-center/AppIcon.png': 'fixture asset\n',
                'sdk-lab/tools/native_setup.py': '# portable helper\n',
                'sdk-lab/tests/test_native_setup.py': '# offline test\n',
                'vendor/crossover-ffb/scripts/build-bridge': '#!/bin/sh\nexit 0\n',
                'vendor/crossover-ffb/Sources/WheelCore/Input.swift': '// Swift source\n',
                'LICENSES/runtime.txt': 'Runtime attribution\n',
                'patches/wine.patch': 'Public Wine patch\n'}.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        (root / 'scripts/build.sh').chmod(0o755)
        return root, mescon

    def test_whitelist_preserves_build_sources_not_private_or_generated_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root, mescon = self.fixture(directory)
            private = ('build/private.dll', 'work/source.py', '.git/config', 'private/token.txt',
                       'docs/HARDWARE_2026-10-20.json', 'docs/STATUS.md', 'AGENTS.md',
                       'scripts/diagnostics/recovery.py', 'sdk-lab/tools/ets2_capture_session.py',
                       'sdk-lab/tests/test_capture_restore.py', 'docs/publication/POST_RU.md',
                       'sdk-lab/private/original-sdk.dll',
                       'vendor/crossover-ffb/.build/module.swift', 'src/main.cpp.bak')
            for name in private:
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    path.write_bytes(b'never export this')
            (mescon / 'build').mkdir(); (mescon / 'build/mescon-synth').write_bytes(b'never export')
            result = publication.export(root, mescon, directory / 'release')
            stage = Path(result['stage'])
            manifest = json.loads((stage / publication.MANIFEST_NAME).read_text())
            for name in private:
                self.assertNotIn('g923-mac-bridge/' + name, manifest['files'])
                self.assertFalse((stage / 'g923-mac-bridge' / name).exists())
            for name in ('scripts/build-release-components.py', 'scripts/test-release-components.py',
                         'vendor/crossover-ffb/scripts/build-bridge', 'LICENSES/runtime.txt'):
                self.assertIn('g923-mac-bridge/' + name, manifest['files'])
            self.assertTrue((stage / 'mescon-telemetry/src/control.rs').is_file())
            self.assertFalse((stage / 'mescon-telemetry/build').exists())
            self.assertEqual(manifest['components']['mescon-telemetry']['license'], 'GPL-2.0-only')
            self.assertTrue(manifest['components']['mescon-telemetry']['separate_process'])
            self.assertNotIn(str(root), json.dumps(manifest))
            self.assertIn('.gitignore', manifest['files'])
            self.assertIn('README.md', manifest['files'])
            self.assertIn('LICENSE', manifest['files'])
            self.assertIn('NOTICE.md', manifest['files'])
            self.assertEqual((stage / 'LICENSE').read_bytes(), (root / 'LICENSE').read_bytes())
            self.assertEqual((stage / 'g923-mac-bridge/vendor/crossover-ffb/LICENSE').read_bytes(),
                             (root / 'vendor/crossover-ffb/LICENSE').read_bytes())
            notice = (stage / 'NOTICE.md').read_text()
            self.assertIn('GPL-3.0-only', notice)
            self.assertIn('GPL-2.0-only', notice)
            self.assertIn('separate process', notice)
            self.assertIn('g923-mac-bridge/vendor/crossover-ffb/LICENSE', notice)
            self.assertEqual((stage / 'g923-mac-bridge/.gitignore').read_text(), '/build/\n*.log\n')
            self.assertIn('**/build/', (stage / '.gitignore').read_text())
            self.assertTrue((root / 'private/token.txt').exists())
            self.assertRegex((root / 'docs/publication/POST_RU.md').read_text(), '[\u0400-\u04ff]')
            public_docs = [stage / 'README.md', stage / 'NOTICE.md',
                           stage / 'g923-mac-bridge/README.md']
            public_docs += list((stage / 'g923-mac-bridge/docs').rglob('*.md'))
            for document in public_docs:
                self.assertNotRegex(document.read_text(), '[\u0400-\u04ff]')
            with zipfile.ZipFile(directory / 'release' / result['archive']) as archive:
                self.assertFalse(any('POST_RU' in name for name in archive.namelist()))

    def test_archive_and_manifest_are_reproducible_despite_source_mtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root, mescon = self.fixture(directory)
            first = publication.export(root, mescon, directory / 'first')
            os.utime(root / 'src/main.cpp', (1234567890, 1234567890))
            second = publication.export(root, mescon, directory / 'second')
            self.assertEqual(first['sha256'], second['sha256'])
            self.assertEqual((directory / 'first' / first['archive']).read_bytes(),
                             (directory / 'second' / second['archive']).read_bytes())
            with zipfile.ZipFile(directory / 'first' / first['archive']) as archive:
                for info in archive.infolist():
                    self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertTrue(info.filename.startswith(publication.BUNDLE_NAME + '/'))
                mode = archive.getinfo(publication.BUNDLE_NAME + '/g923-mac-bridge/scripts/build.sh').external_attr >> 16
                self.assertEqual(mode & 0o777, 0o755)
            stage = Path(first['stage'])
            manifest = json.loads((stage / publication.MANIFEST_NAME).read_text())
            for name, metadata in manifest['files'].items():
                self.assertEqual(metadata['sha256'], hashlib.sha256((stage / name).read_bytes()).hexdigest())

    def test_personal_paths_fail_without_exporting_or_printing_sensitive_bytes(self):
        for marker in (b'/Users/' + b'armax/secret', b'/Volumes/' + b'armax/SteamLibrary'):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary); root, mescon = self.fixture(directory)
                (root / 'src/main.cpp').write_bytes(marker)
                with self.assertRaisesRegex(ValueError, 'personal machine path') as caught:
                    publication.export(root, mescon, directory / 'release')
                self.assertNotIn(marker.decode(), str(caught.exception))
                self.assertFalse((directory / 'release').exists())

    def test_secret_patterns_fail_without_echoing_token(self):
        tokens = (b'ghp_' + b'A' * 36, b'AKIA' + b'Z' * 16,
                  b'-----BEGIN ' + b'OPENSSH PRIVATE KEY-----',
                  b'-----BEGIN ' + b'ENCRYPTED PRIVATE KEY-----', b'sk-proj-' + b'B' * 40)
        for token in tokens:
            with self.subTest(token_type=token[:4]), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary); root, mescon = self.fixture(directory)
                (root / 'src/main.cpp').write_bytes(token)
                with self.assertRaisesRegex(ValueError, 'audit failed') as caught:
                    publication.export(root, mescon, directory / 'release')
                self.assertNotIn(token.decode(), str(caught.exception))

    def test_renamed_executable_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); root, mescon = self.fixture(directory)
            (root / 'src/main.cpp').write_bytes(b'MZ' + b'compiled SDK')
            with self.assertRaisesRegex(ValueError, 'compiled executable'):
                publication.export(root, mescon, directory / 'release')

    def test_symlink_file_and_directory_are_rejected(self):
        for link_directory in (False, True):
            with self.subTest(directory=link_directory), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary); root, mescon = self.fixture(directory)
                outside = directory / 'outside'
                if link_directory:
                    outside.mkdir(); (root / 'src/link').symlink_to(outside, target_is_directory=True)
                else:
                    outside.write_text('private'); (root / 'src/link.cpp').symlink_to(outside)
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    publication.export(root, mescon, directory / 'release')

    def test_missing_license_or_sibling_source_is_rejected(self):
        for component, name in (('root', 'vendor/crossover-ffb/LICENSE'), ('mescon', 'COPYING')):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary); root, mescon = self.fixture(directory)
                (locals()[component] / name).unlink()
                with self.assertRaisesRegex(ValueError, 'Required source/attribution'):
                    publication.export(root, mescon, directory / 'release')

    def test_missing_local_document_link_aborts_before_promoting(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); root, mescon = self.fixture(directory)
            (root / 'README.md').write_text('[Missing](docs/historical-private-report.md)\n')
            with self.assertRaisesRegex(ValueError, 'documentation has missing'):
                publication.export(root, mescon, directory / 'release')
            self.assertFalse((directory / 'release' / publication.BUNDLE_NAME).exists())
            self.assertFalse(list((directory / 'release').glob('*.zip')))

    def test_relative_document_links_cannot_escape_the_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); root, mescon = self.fixture(directory)
            (root / 'README.md').write_text('[Outside](../../../outside.md)\n')
            with self.assertRaisesRegex(ValueError, 'unsafe links'):
                publication.export(root, mescon, directory / 'release')

    def test_export_never_replaces_a_stage_turned_into_a_git_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);root,mescon=self.fixture(directory)
            result=publication.export(root,mescon,directory/'release');stage=Path(result['stage'])
            metadata=stage/'.git';metadata.mkdir();(metadata/'HEAD').write_text('ref: refs/heads/main\n')
            before=(stage/'README.md').read_bytes()
            (root/'README.md').write_text('Changed upstream source\n')
            with self.assertRaisesRegex(ValueError,'not owned'):publication.export(root,mescon,directory/'release')
            self.assertEqual((metadata/'HEAD').read_text(),'ref: refs/heads/main\n')
            self.assertEqual((stage/'README.md').read_bytes(),before)

    def test_landing_readme_rebases_relative_links_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); root, mescon = self.fixture(directory)
            source = ('# G923\n[SDK](docs/LOGITECH_SDK_SETUP.md#steps)\n'
                      '[License](LICENSE "Project license")\n'
                      '[External](https://example.org/docs#anchor)\n'
                      '[Anchor](#g923)\n![Icon](<assets/control-center/AppIcon.png>)\n')
            (root / 'README.md').write_text(source)
            result = publication.export(root, mescon, directory / 'release')
            stage = Path(result['stage'])
            generated = (stage / 'README.md').read_text()
            self.assertIn('[SDK](g923-mac-bridge/docs/LOGITECH_SDK_SETUP.md#steps)', generated)
            self.assertIn('[License](g923-mac-bridge/LICENSE "Project license")', generated)
            self.assertIn('[External](https://example.org/docs#anchor)', generated)
            self.assertIn('[Anchor](#g923)', generated)
            self.assertIn('![Icon](<g923-mac-bridge/assets/control-center/AppIcon.png>)', generated)
            self.assertEqual((root / 'README.md').read_text(), source)
            self.assertEqual((stage / 'g923-mac-bridge/README.md').read_text(), source)

    def test_existing_unrelated_folder_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); root, mescon = self.fixture(directory)
            target = directory / 'release' / publication.BUNDLE_NAME; target.mkdir(parents=True)
            (target / 'keep.txt').write_text('unrelated')
            with self.assertRaisesRegex(ValueError, 'not owned'):
                publication.export(root, mescon, directory / 'release')
            self.assertEqual((target / 'keep.txt').read_text(), 'unrelated')

    def test_owned_previous_export_can_be_refreshed(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); root, mescon = self.fixture(directory)
            first = publication.export(root, mescon, directory / 'release')
            (root / 'src/main.cpp').write_text('int main() { return 1; }\n')
            second = publication.export(root, mescon, directory / 'release')
            self.assertNotEqual(first['sha256'], second['sha256'])
            self.assertIn('return 1', (Path(second['stage']) / 'g923-mac-bridge/src/main.cpp').read_text())

    def test_output_cannot_replace_source_or_write_inside_its_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); root, mescon = self.fixture(directory)
            for output in (root, root / 'src/release', directory):
                with self.subTest(output=output), self.assertRaisesRegex(ValueError, 'Output'):
                    publication.export(root, mescon, output)
            self.assertTrue((root / 'src/main.cpp').is_file())

    def test_checksum_output_replaces_a_symlink_without_following_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); root, mescon = self.fixture(directory)
            outside = directory / 'outside.txt'; outside.write_text('unchanged')
            output = directory / 'release'; output.mkdir()
            checksum = output / 'G923ControlCenter-0.6.2-source.zip.sha256'
            checksum.symlink_to(outside)
            publication.export(root, mescon, output)
            self.assertEqual(outside.read_text(), 'unchanged')
            self.assertFalse(checksum.is_symlink())


if __name__ == '__main__':
    unittest.main()
