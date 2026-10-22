# SPDX-License-Identifier: GPL-3.0-only
"""Transport installation fixtures never execute Wine or access a wheel."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]/'tools'))
import transport_setup as setup


def sha(value):
    return hashlib.sha256(value).hexdigest()


class TransportSetupTests(unittest.TestCase):
    def fixture(self, root):
        app = root/'Apps with spaces/任意 CrossOver Preview.app'
        runtime = app/'Contents/SharedSupport/CrossOver'
        files = {'bin/wine': b'never execute this fixture',
                 'etc/CrossOver.conf': b'[CrossOver]\n"ProductVersion" = "27.fixture"\n"BuildTimestamp" = "reviewed-build"\n',
                 'lib/wine/x86_64-unix/winebus.so': b'original unix module',
                 'lib/wine/x86_64-windows/winebus.sys': b'original windows module',
                 'lib/libunchanged.dylib': b'original user runtime library'}
        for relative, data in files.items():
            target = runtime/relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        (runtime/'bin/wine').chmod(0o755)
        (runtime/'lib/absolute-internal-link').symlink_to(runtime/'lib/libunchanged.dylib')
        payloads = root/'Resources/payloads/winebus'; payloads.mkdir(parents=True)
        modules = {}
        for name in sorted(setup.MODULES):
            data = ('prepared ' + name).encode()
            path = payloads/'fixture'/Path(name).name
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            modules[name] = dict(path=str(path.relative_to(payloads)), sha256=sha(data))
        build = dict(id='fixture-1', product_version='27.fixture', build_timestamp='reviewed-build', wine_version='11.fixture',
                     original_module_hashes={name: sha(files['lib/wine/'+name]) for name in setup.MODULES}, modules=modules)
        catalog = dict(version=1, builds=[build])
        (payloads/'catalog.json').write_text(json.dumps(catalog))
        store = root/'Application Support/G923 Control Center/Transports'
        return app, runtime, payloads, store, catalog

    def options(self, store, payloads):
        return dict(store=store, payload_root=payloads)

    def test_status_is_read_only_and_install_clones_exact_matching_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, runtime, payloads, store, catalog = self.fixture(Path(tmp))
            original = {str(p.relative_to(runtime)): p.read_bytes() for p in runtime.rglob('*') if p.is_file()}
            options = self.options(store, payloads)
            before = setup.status(app, **options)
            self.assertEqual(before['state'], 'available')
            self.assertFalse(store.exists())
            with patch('subprocess.run', side_effect=AssertionError('no processes may launch')):
                result = setup.install(app, **options)
            self.assertTrue(result['installed'])
            self.assertEqual(result['state'], 'installed')
            self.assertEqual(setup.lookup(app, **options), Path(result['transport_dir']))
            copied = Path(result['runtime_dir'])
            manifest = json.loads((Path(result['transport_dir'])/'manifest.json').read_text())
            self.assertEqual(manifest['purpose'], setup.PURPOSE)
            self.assertEqual(manifest['original_hashes'], catalog['builds'][0]['original_module_hashes'])
            self.assertEqual(manifest['runtime_hashes'], manifest['prepared_module_hashes'])
            self.assertFalse(manifest['game_launched'])
            for relative, item in catalog['builds'][0]['modules'].items():
                self.assertEqual(setup.digest(copied/'lib/wine'/relative), item['sha256'])
            for name, data in original.items():
                self.assertEqual((runtime/name).read_bytes(), data)
            self.assertEqual((copied/'lib/libunchanged.dylib').read_bytes(), b'original user runtime library')
            link = copied/'lib/absolute-internal-link'
            self.assertTrue(link.is_symlink())
            self.assertFalse(Path(link.readlink()).is_absolute())
            self.assertEqual(link.resolve(), copied/'lib/libunchanged.dylib')
            record = (Path(result['transport_dir'])/'manifest.json').read_bytes()
            self.assertEqual(setup.install(app, **options)['transport_dir'], result['transport_dir'])
            self.assertEqual((Path(result['transport_dir'])/'manifest.json').read_bytes(), record)
            self.assertFalse(any(p.name.startswith('.') for p in store.iterdir()))

    def test_unknown_version_or_timestamp_cannot_install(self):
        for old, new in [('27.fixture', 'new.update'), ('reviewed-build', 'different-build')]:
            with self.subTest(field=old), tempfile.TemporaryDirectory() as tmp:
                app, runtime, payloads, store, _ = self.fixture(Path(tmp))
                config = runtime/'etc/CrossOver.conf'; config.write_text(config.read_text().replace(old, new))
                result = setup.status(app, **self.options(store,payloads))
                self.assertEqual(result['state'], 'unsupported')
                self.assertIn('No compatible transport build', result['detail'])
                with self.assertRaisesRegex(ValueError, 'No compatible transport build'):
                    setup.install(app, **self.options(store,payloads))
                self.assertFalse(store.exists())

    def test_changed_stock_module_or_changed_payload_is_preserved(self):
        for which in ('stock', 'payload'):
            with self.subTest(which=which), tempfile.TemporaryDirectory() as tmp:
                app, runtime, payloads, store, catalog = self.fixture(Path(tmp))
                target = runtime/'lib/wine/x86_64-unix/winebus.so' if which=='stock' else payloads/catalog['builds'][0]['modules']['x86_64-unix/winebus.so']['path']
                target.write_bytes(b'changed bytes')
                result = setup.status(app, **self.options(store,payloads))
                self.assertEqual(result['state'], 'invalid')
                with self.assertRaises(ValueError):
                    setup.install(app, **self.options(store,payloads))
                self.assertEqual(target.read_bytes(), b'changed bytes')
                self.assertFalse(store.exists())

    def test_incomplete_payload_pair_or_traversal_is_rejected(self):
        for mutation in ('pair', 'path', 'duplicate', 'hash'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                app, runtime, payloads, store, catalog = self.fixture(Path(tmp))
                build = catalog['builds'][0]
                if mutation=='pair':
                    del build['modules']['x86_64-unix/winebus.so']
                elif mutation=='path':
                    build['modules']['x86_64-unix/winebus.so']['path']='../outside.so'
                elif mutation=='duplicate':
                    catalog['builds'].append(dict(build))
                else:
                    build['original_module_hashes']['x86_64-unix/winebus.so']='not a hash'
                (payloads/'catalog.json').write_text(json.dumps(catalog))
                with self.assertRaises(ValueError):
                    setup.install(app, **self.options(store,payloads))
                self.assertFalse(store.exists())

    def test_external_payload_symlink_cannot_substitute_a_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, runtime, payloads, store, catalog = self.fixture(Path(tmp))
            target = payloads/catalog['builds'][0]['modules']['x86_64-unix/winebus.so']['path']
            external = Path(tmp)/'external.so'; target.rename(external); target.symlink_to(external)
            with self.assertRaisesRegex(ValueError, 'differs from its catalog'):
                setup.install(app, **self.options(store,payloads))
            self.assertFalse(store.exists())

    def test_failed_copy_does_not_leave_install_or_modify_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, runtime, payloads, store, _ = self.fixture(Path(tmp))
            def fail(source, destination):
                destination.mkdir()
                (destination/'partial').write_bytes(b'incomplete')
                raise OSError('copy interrupted')
            with patch.object(setup, '_portable_runtime', side_effect=fail):
                with self.assertRaisesRegex(OSError, 'copy interrupted'):
                    setup.install(app, **self.options(store,payloads))
            self.assertEqual(list(store.iterdir()), [])
            self.assertEqual((runtime/'lib/wine/x86_64-unix/winebus.so').read_bytes(), b'original unix module')

    def test_source_change_during_copy_is_rejected_before_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, runtime, payloads, store, _ = self.fixture(Path(tmp))
            clone = setup._portable_runtime
            def changed(source, destination):
                clone(source,destination)
                (source/'lib/wine/x86_64-windows/winebus.sys').write_bytes(b'updater changed original')
            with patch.object(setup, '_portable_runtime', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'differ from the compatible stock build'):
                    setup.install(app, **self.options(store,payloads))
            self.assertEqual(list(store.iterdir()), [])

    def test_existing_invalid_directory_or_symlink_is_preserved(self):
        for link in (False, True):
            with self.subTest(link=link), tempfile.TemporaryDirectory() as tmp:
                app, runtime, payloads, store, _ = self.fixture(Path(tmp))
                fingerprint = setup.status(app, **self.options(store,payloads))['fingerprint']
                store.mkdir(parents=True)
                target = store/fingerprint
                if link:
                    target.symlink_to(runtime, target_is_directory=True)
                else:
                    target.mkdir(); (target/'unowned').write_bytes(b'preserve')
                with self.assertRaises(ValueError):
                    setup.install(app, **self.options(store,payloads))
                self.assertTrue(target.exists())
                if not link:
                    self.assertEqual((target/'unowned').read_bytes(),b'preserve')

    def test_runtime_nested_store_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,runtime,payloads,store,_=self.fixture(Path(tmp))
            with self.assertRaisesRegex(ValueError,'must be separate'):
                setup.install(app,store=runtime/'Transports',payload_root=payloads)
            self.assertFalse((runtime/'Transports').exists())

    def test_import_verifies_existing_profile_and_does_not_copy_or_edit_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,runtime,payloads,store,_=self.fixture(Path(tmp))
            first = setup.install(app, **self.options(store,payloads))
            session = Path(first['transport_dir'])
            before = (session/'manifest.json').read_bytes()
            other = Path(tmp)/'Other user data/Transports'
            imported = setup.import_existing(session,store=other,payload_root=payloads)
            self.assertEqual(imported['transport_dir'],str(session))
            self.assertEqual((session/'manifest.json').read_bytes(),before)
            self.assertEqual(setup.lookup(app,store=other,payload_root=payloads),session)
            with patch.object(setup,'_portable_runtime',side_effect=AssertionError('must reuse verified runtime')):
                result=setup.install(app,store=other,payload_root=payloads)
            self.assertEqual(result['transport_dir'],str(session))
            self.assertEqual(len(json.loads((other/'registry.json').read_text())['imports']),1)
            setup.import_existing(session,store=other,payload_root=payloads)
            self.assertEqual(len(json.loads((other/'registry.json').read_text())['imports']),1)

    def test_corrupted_prepared_pair_is_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,runtime,payloads,store,_=self.fixture(Path(tmp))
            installed=setup.install(app,**self.options(store,payloads))
            (Path(installed['runtime_dir'])/'lib/wine/x86_64-unix/winebus.so').write_bytes(b'wrong transport')
            self.assertFalse(setup.status(app,**self.options(store,payloads))['installed'])
            self.assertIsNone(setup.lookup(app,**self.options(store,payloads)))
            with self.assertRaisesRegex(ValueError,'transport changed'):
                setup.import_existing(installed['transport_dir'],store=Path(tmp)/'other',payload_root=payloads)

    def test_runtime_loader_and_discovery_runner_are_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,runtime,payloads,store,_=self.fixture(Path(tmp))
            options=self.options(store,payloads)
            self.assertTrue(setup.status(runtime,**options)['available'])
            self.assertTrue(setup.status(runtime/'bin/wine',**options)['available'])
            self.assertTrue(setup.status({'path':str(app),'wine':'unused'},**options)['available'])

    def test_unspecified_runner_leaves_explicit_selection_reachable(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,runtime,payloads,store,_=self.fixture(Path(tmp))
            state=setup.status(store=store,payload_root=payloads)
            self.assertEqual(state['state'],'select_runner')
            self.assertTrue(state['available'])
            self.assertFalse(state['installed'])
            self.assertFalse(store.exists())

    def test_builtin_accepted_metadata_is_valid_without_payloads(self):
        self.assertEqual(setup._validate_catalog({'version':1,'builds':[setup.ACCEPTED_BUILD]}),[setup.ACCEPTED_BUILD])

    def test_prepared_profile_can_be_checked_when_payload_is_not_bundled(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,runtime,payloads,store,catalog=self.fixture(Path(tmp))
            installed=setup.install(app,**self.options(store,payloads))
            absent=Path(tmp)/'no bundled modules'
            with patch.object(setup,'ACCEPTED_BUILD',catalog['builds'][0]):
                self.assertTrue(setup.status(session=installed['transport_dir'],payload_root=absent)['installed'])
                unavailable=setup.status(app,store=Path(tmp)/'fresh user',payload_root=absent)
                self.assertFalse(unavailable['available'])
                self.assertIn('payload is missing',unavailable['detail'])

    def test_malformed_prepared_metadata_returns_status_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,runtime,payloads,store,catalog=self.fixture(Path(tmp))
            installed=setup.install(app,**self.options(store,payloads))
            session=Path(installed['transport_dir'])
            for value in ([], {'purpose':setup.PURPOSE,'runtime_dir':123}, {'purpose':setup.PURPOSE,'runtime_dir':'relative/runtime'}):
                with self.subTest(value=value):
                    (session/'manifest.json').write_text(json.dumps(value))
                    result=setup.status(session=session,payload_root=payloads)
                    self.assertEqual(result['state'],'invalid')
                    self.assertFalse(result['installed'])


if __name__=='__main__':
    unittest.main()
