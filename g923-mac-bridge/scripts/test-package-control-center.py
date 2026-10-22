#!/usr/bin/env python3
"""Check the release bundle contents without starting apps or touching bottles."""
import importlib.util
import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('packager', Path(__file__).with_name('package-control-center.py'))
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


def archive_bytes(files, mode='w:xz', extra=None):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode=mode) as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        if extra is not None:
            archive.addfile(extra)
    return output.getvalue()


def source_bundle_fixture(root, prepared, modules, upstream_extra=None):
    source = {'bundle': 'sources/g923-wine-11.17-source.tar.xz', 'commit': '1' * 40,
              'tag': 'wine-11.17', 'patch': 'winebus-11.17-g923-trueforce.patch',
              'notice_patch': 'winebus-11.17-g923-change-notices.patch',
              'build_script': 'scripts/build-wine-transport.py'}
    licences = {name: ('public upstream ' + name).encode() for name in ('COPYING.LIB', 'LICENSE', 'AUTHORS')}
    original = archive_bytes({'wine-wine-11.17/' + name: data for name, data in licences.items()},
                             mode='w:gz', extra=upstream_extra)
    source['archive_sha256'] = hashlib.sha256(original).hexdigest()
    source['patch_sha256'] = packager.digest(root / 'patches' / source['patch'])
    build = {'id': 'fixture', 'modules': modules, 'source': source}
    catalog = {'version': 1, 'builds': [build]}
    files = dict(licences)
    for name in ('docs/WINE_TRANSPORT_SOURCE.md', 'patches/README.md', 'patches/' + source['patch'],
                 'patches/' + source['notice_patch'], source['build_script']):
        files[name] = (root / name).read_bytes()
    files['patches/transport-catalog.json'] = json.dumps(catalog).encode()
    files['upstream/wine-11.17.tar.gz'] = original
    manifest = {'version': 1, 'license': 'LGPL-2.1-or-later', 'source_commit': source['commit'],
                'patches': [source['patch'], source['notice_patch']],
                'upstream_archive': 'upstream/wine-11.17.tar.gz',
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files['SOURCE_MANIFEST.json'] = json.dumps(manifest).encode()
    path = prepared / source['bundle']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(archive_bytes({'g923-wine-transport-source/' + name: data for name, data in files.items()}))
    for name, data in licences.items():
        (path.parent / name).write_bytes(data)
    return catalog


def rewrite_source_bundle(path, change, extra=None):
    with tarfile.open(path) as archive:
        files = {member.name: archive.extractfile(member).read() for member in archive if member.isfile()}
    change(files)
    path.write_bytes(archive_bytes(files, extra=extra))


class PackageTests(unittest.TestCase):
    def test_public_bundle_rejects_private_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder)
            (app / 'tool').write_bytes(b'compiled debug data /Users/' + b'example/private/build')
            with self.assertRaisesRegex(ValueError, 'Personal build path'):
                packager.audit_public_app(app)

    def test_public_bundle_rejects_external_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder)
            (app / 'source').symlink_to('/private/tmp')
            with self.assertRaisesRegex(ValueError, 'symlink escapes'):
                packager.audit_public_app(app)

    def test_public_bundle_accepts_internal_source_link(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder)
            (app / 'source.tar.xz').write_bytes(b'complete public source')
            (app / 'source-link').symlink_to('source.tar.xz')
            packager.audit_public_app(app)

    def fixture(self, directory):
        root = directory / 'source'
        binary = directory / 'compiled'
        files = [root / p for p in ('assets/control-center/AppIcon.icns', 'LICENSE',
                 'vendor/crossover-ffb/LICENSE', 'sdk-lab/tools/bootstrap.py', 'sdk-lab/tools/discovery.py',
                 'build/g923-input', 'build/ets2-force-unknown/g923_bridge.dll', 'build/winmm-chain/winmm.dll',
                 'build/crossover-base/dinput8.dll')]
        files += [directory / 'mescon-telemetry' / p for p in ('COPYING', 'UPSTREAM.json', 'build/logi_tf_scs.dll',
                  'build/live-engine-candidate/mescon-synth')]
        files += [root / p for p in ('patches/README.md', 'patches/winebus-11.17-g923-trueforce.patch',
                  'patches/winebus-11.17-g923-change-notices.patch', 'scripts/build-wine-transport.py',
                  'docs/WINE_TRANSPORT_SOURCE.md')]
        files += [binary / p for p in ('CrossoverFFBApp', 'G923ClassicLab')]
        files += [root/'sdk-lab/tools'/(name+'.py') for name in packager.RUNTIME_HELPERS]
        for file in files:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(('fixture ' + file.name).encode())
        # These are private migration data, never release resources.
        (directory / 'G923 Installation/private').mkdir(parents=True)
        (directory / 'G923 Installation/private/trueforce_sdk_x64.dll').write_bytes(b'private SDK')
        native = directory / 'G923 Installation'
        (native / 'sdk-dinput8.dll').write_bytes(b'own native game bridge')
        (native / 'manifest.json').write_text(json.dumps({'game_dll_sha':packager.digest(native / 'sdk-dinput8.dll')}))
        components = root / 'build/public-components'
        components.mkdir(parents=True)
        source_manifest = {'version':1,'files':{}}
        for name in packager.REQUIRED_COMPONENTS:
            path=components/name; path.write_bytes(('rebuilt '+name).encode())
            source_manifest['files'][name]={'path':name,'sha256':packager.digest(path)}
        (components/'manifest.json').write_text(json.dumps(source_manifest))
        live = directory / 'mescon-telemetry/build/live-engine-candidate/mescon-synth'
        synth_hash = patch.object(packager, 'LIVE_MESCON_SHA256', packager.digest(live))
        synth_hash.start(); self.addCleanup(synth_hash.stop)
        prepared = root / 'build/wine-transport-source'
        modules = {}
        for kind in ('x86_64-unix/winebus.so', 'x86_64-windows/winebus.sys'):
            name = 'candidate/' + Path(kind).name
            path = prepared / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('public reviewed module ' + kind).encode())
            modules[kind] = {'path': name, 'sha256': packager.digest(path)}
        catalog = source_bundle_fixture(root, prepared, modules)
        for path in (prepared / 'catalog.json', root / 'patches/transport-catalog.json'):
            path.write_text(json.dumps(catalog))
        (prepared / 'private-SDK.dll').write_bytes(b'never release')
        return root, binary

    def testBundleContainsOnlyPortableMetadataAndPublicPayloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            root, binary = self.fixture(directory)
            with patch.object(packager.subprocess, 'run'), patch.object(packager.subprocess, 'check_output', return_value=str(binary)):
                app = packager.package(root, directory / 'release')
            resources = app / 'Contents/Resources'
            for name in ('project-root.txt', 'python-path.txt', 'prepared-profiles.json'):
                self.assertFalse((resources / name).exists())
            self.assertFalse(list(resources.rglob('trueforce_sdk_x64.dll')))
            self.assertTrue((resources / 'BridgeTools/sdk-lab/tools/bootstrap.py').is_file())
            for name in ('sdk_setup', 'pe_inventory', 'native_setup', 'transport_setup'):
                self.assertTrue((resources / 'BridgeTools/sdk-lab/tools' / (name + '.py')).is_file())
            payloads = resources / 'BridgeTools/payloads'
            manifest = json.loads((payloads / 'manifest.json').read_text())
            for name, item in manifest['files'].items():
                self.assertEqual(item['path'], name)
                self.assertEqual(item['sha256'], packager.digest(payloads / name))
            self.assertNotIn(str(root), json.dumps(manifest))
            self.assertFalse(list(resources.rglob('private-SDK.dll')))
            transport = payloads / 'winebus'
            catalog = json.loads((transport / 'catalog.json').read_text())
            for build in catalog['builds']:
                for module in build['modules'].values():
                    self.assertEqual(module['sha256'], packager.digest(transport / module['path']))
                self.assertEqual(build['source']['bundle_sha256'], packager.digest(transport / build['source']['bundle']))
            browsable = resources / 'WineTransportSource'
            self.assertTrue((browsable / 'scripts/build-wine-transport.py').is_file())
            self.assertTrue((browsable / 'patches/winebus-11.17-g923-trueforce.patch').is_file())
            self.assertTrue((browsable / 'COPYING.LIB').is_file())
            source_archive = browsable / 'g923-wine-11.17-source.tar.xz'
            self.assertTrue(source_archive.is_symlink())
            self.assertTrue(source_archive.resolve().is_relative_to(resources.resolve()))
            self.assertEqual(source_archive.read_bytes(), (transport / 'sources' / source_archive.name).read_bytes())
            with (app / 'Contents/Info.plist').open('rb') as handle:
                info = packager.plistlib.load(handle)
            self.assertEqual(info['CFBundleShortVersionString'], '0.6.2')
            self.assertEqual(info['CFBundleVersion'], '9')

    def testAcceptedTelemetryDoesNotReplaceLiveSynth(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); root, binary = self.fixture(directory)
            accepted = directory / 'G923 ETS2'; accepted.mkdir()
            (accepted / 'mescon-synth').write_bytes(b'old accepted synthesizer')
            (accepted / 'G923TelemetryLab').write_bytes(b'accepted native telemetry backend')
            (accepted / 'manifest.json').write_text(json.dumps({'backend_hashes': {
                name: packager.digest(accepted / name) for name in ('mescon-synth', 'G923TelemetryLab')}}))
            with patch.object(packager.subprocess, 'run'), patch.object(packager.subprocess, 'check_output', return_value=str(binary)):
                app = packager.package(root, directory / 'release', accepted_local=True)
            payloads = app / 'Contents/Resources/BridgeTools/payloads'
            self.assertEqual((payloads / 'G923TelemetryLab').read_bytes(), (accepted / 'G923TelemetryLab').read_bytes())
            live = directory / 'mescon-telemetry/build/live-engine-candidate/mescon-synth'
            self.assertEqual((payloads / 'mescon-synth').read_bytes(), live.read_bytes())

    def testMissingLiveSynthDoesNotFallBackToOldSynth(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); root, binary = self.fixture(directory)
            (directory / 'mescon-telemetry/build/live-engine-candidate/mescon-synth').unlink()
            (directory / 'mescon-telemetry/build/mescon-synth').write_bytes(b'old fallback')
            with patch.object(packager.subprocess, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'live engine-vibration'):
                    packager.package(root, directory / 'release', accepted_local=True)
            run.assert_not_called()

    def testSourceBuildDoesNotNeedLocalAcceptedFoldersOrCandidateHash(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);root,binary=self.fixture(directory)
            packager.shutil.rmtree(directory/'G923 Installation')
            packager.shutil.rmtree(directory/'mescon-telemetry/build/live-engine-candidate')
            with patch.object(packager.subprocess,'run'),patch.object(packager.subprocess,'check_output',return_value=str(binary)):
                app=packager.package(root,directory/'release')
            self.assertEqual((app/'Contents/Resources/BridgeTools/payloads/sdk-dinput8.dll').read_bytes(),b'rebuilt sdk-dinput8.dll')
            self.assertFalse((app/'Contents/Resources/WineTransportSource/LOCAL_BUILD_PROVENANCE.txt').exists())

    def testSourcePayloadMissingTamperedOrEscapingIsRejectedBeforeBuild(self):
        for case in ('missing','tampered','escape','incomplete'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                directory=Path(tmp);root,_=self.fixture(directory);components=root/'build/public-components'
                path=components/'manifest.json';record=json.loads(path.read_text())
                if case=='missing':path.unlink()
                elif case=='tampered':(components/'mescon-synth').write_bytes(b'changed')
                elif case=='escape':
                    record['files']['mescon-synth']['path']='../private-SDK.dll';path.write_text(json.dumps(record))
                else:
                    del record['files']['sdk-dinput8.dll'];path.write_text(json.dumps(record))
                with patch.object(packager.subprocess,'run') as run:
                    with self.assertRaises((ValueError,RuntimeError)):packager.package(root,directory/'release')
                run.assert_not_called()

    def testTamperedTransportIsRejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); root, binary = self.fixture(directory)
            (root / 'build/wine-transport-source/candidate/winebus.so').write_bytes(b'changed')
            with patch.object(packager.subprocess, 'run'), patch.object(packager.subprocess, 'check_output', return_value=str(binary)):
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    packager.package(root, directory / 'release')

    def testTransportPathCannotEscapePayload(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); root, binary = self.fixture(directory)
            path = root / 'build/wine-transport-source/catalog.json'
            catalog = json.loads(path.read_text())
            catalog['builds'][0]['modules']['x86_64-unix/winebus.so']['path'] = '../private-SDK.dll'
            for item in (path, root / 'patches/transport-catalog.json'):
                item.write_text(json.dumps(catalog))
            with patch.object(packager.subprocess, 'run'), patch.object(packager.subprocess, 'check_output', return_value=str(binary)):
                with self.assertRaisesRegex(ValueError, 'escapes'):
                    packager.package(root, directory / 'release')

    def testSourceManifestCommitUpstreamAndPatchMustMatchReviewedCatalog(self):
        for field in ('commit', 'archive_sha256', 'patch_sha256'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root, _ = self.fixture(Path(tmp))
                prepared = root / 'build/wine-transport-source'
                build = json.loads((prepared / 'catalog.json').read_text())['builds'][0]
                build['source'][field] = '2' * (40 if field == 'commit' else 64)
                with self.assertRaisesRegex(ValueError, 'reviewed commit|pinned upstream'):
                    packager.verify_wine_source_bundle(prepared / build['source']['bundle'], build)

    def testSourceMemberTamperingIsDetected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = self.fixture(Path(tmp))
            prepared = root / 'build/wine-transport-source'
            build = json.loads((prepared / 'catalog.json').read_text())['builds'][0]
            path = prepared / build['source']['bundle']
            rewrite_source_bundle(path, lambda files: files.update({'g923-wine-transport-source/patches/' + build['source']['patch']: b'changed patch'}))
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                packager.verify_wine_source_bundle(path, build)

    def testSourceArchiveRejectsTraversalSymlinksAndUnlistedFiles(self):
        for kind in ('traversal', 'symlink', 'unlisted', 'duplicate'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root, _ = self.fixture(Path(tmp))
                prepared = root / 'build/wine-transport-source'
                build = json.loads((prepared / 'catalog.json').read_text())['builds'][0]
                path = prepared / build['source']['bundle']
                if kind == 'traversal':
                    extra = tarfile.TarInfo('g923-wine-transport-source/../../outside')
                elif kind == 'duplicate':
                    extra = tarfile.TarInfo('g923-wine-transport-source/COPYING.LIB/')
                else:
                    extra = tarfile.TarInfo('g923-wine-transport-source/unlisted.dll')
                    if kind == 'symlink':
                        extra.type, extra.linkname = tarfile.SYMTYPE, '/private/file'
                rewrite_source_bundle(path, lambda files: None, extra=extra)
                with self.assertRaisesRegex(ValueError, 'escapes|linked|unlisted|Duplicate'):
                    packager.verify_wine_source_bundle(path, build)

    def testUpstreamArchiveRejectsLinksEvenWithMatchingManifestHashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = self.fixture(Path(tmp))
            prepared = root / 'build/wine-transport-source'
            old = json.loads((prepared / 'catalog.json').read_text())
            link = tarfile.TarInfo('wine-wine-11.17/linked-source')
            link.type, link.linkname = tarfile.SYMTYPE, '/private/file'
            catalog = source_bundle_fixture(root, prepared, old['builds'][0]['modules'], upstream_extra=link)
            build = catalog['builds'][0]
            with self.assertRaisesRegex(ValueError, 'linked'):
                packager.verify_wine_source_bundle(prepared / build['source']['bundle'], build)

    def testPackagedWineLicenceMustMatchCorrespondingSource(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, binary = self.fixture(Path(tmp))
            (root / 'build/wine-transport-source/sources/COPYING.LIB').write_bytes(b'changed licence')
            with patch.object(packager.subprocess, 'run'), patch.object(packager.subprocess, 'check_output', return_value=str(binary)):
                with self.assertRaisesRegex(ValueError, 'licence differs'):
                    packager.package(root, Path(tmp) / 'release')

    def testMissingCorrespondingSourceCannotBeBundled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = self.fixture(Path(tmp))
            prepared = root / 'build/wine-transport-source'
            build = json.loads((prepared / 'catalog.json').read_text())['builds'][0]
            path = prepared / build['source']['bundle']
            rewrite_source_bundle(path, lambda files: files.pop('g923-wine-transport-source/scripts/build-wine-transport.py'))
            with self.assertRaisesRegex(ValueError, 'missing or unlisted'):
                packager.verify_wine_source_bundle(path, build)

    def testInstallPreservesPortableSourceArchiveLink(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); root, binary = self.fixture(directory)
            installed = directory / 'Applications/G923 Control Center.app'
            with patch.object(packager.subprocess, 'run'), patch.object(packager.subprocess, 'check_output', return_value=str(binary)):
                packager.package(root, directory / 'release', installed)
            link = installed / 'Contents/Resources/WineTransportSource/g923-wine-11.17-source.tar.xz'
            self.assertTrue(link.is_symlink())
            self.assertTrue(link.is_file())
            self.assertTrue(link.resolve().is_relative_to(installed.resolve()))

    def testInstallNeedsExplicitDestinationAndRejectsOtherApplication(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            root, binary = self.fixture(directory)
            installed = directory / 'Existing.app'
            (installed / 'Contents').mkdir(parents=True)
            with (installed / 'Contents/Info.plist').open('wb') as handle:
                packager.plistlib.dump({'CFBundleIdentifier': 'another.app'}, handle)
            with patch.object(packager.subprocess, 'run'), patch.object(packager.subprocess, 'check_output', return_value=str(binary)):
                with self.assertRaisesRegex(ValueError, 'another application'):
                    packager.package(root, directory / 'release', installed)
            self.assertTrue((installed / 'Contents/Info.plist').is_file())


if __name__ == '__main__':
    unittest.main()
