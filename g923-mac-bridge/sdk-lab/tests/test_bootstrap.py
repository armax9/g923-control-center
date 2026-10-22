"""Portable setup uses fake files only; no Wine process, game or HID is started."""
import json
import shutil
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import bootstrap
import native_setup
import transport_setup
from portable_paths import digest, payload, runtime_directory, wine_command
from profile_store import load_registry


class PortableSetup(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.bottle=self.root/'Custom Bottles/Truck & Rally'
        self.game=self.root/'External Disk/Steam Library/common/ETS2/bin/win_x64/eurotrucks2.exe'
        self.game.parent.mkdir(parents=True);self.game.write_bytes(b'game')
        self.bottle.mkdir(parents=True);(self.bottle/'cxbottle.conf').write_text('[Bottle]\nVersion=27\n')
        (self.bottle/'user.reg').write_text('WINE REGISTRY Version 2\n\n[Existing] 1\n"test"="keep"\n')
        self.runner=self.root/'Renamed CrossOver Preview.app';self.runner.mkdir()
        self.inventory={'runners':[{'id':'runner','path':str(self.runner),'wine':str(self.runner/'Contents/SharedSupport/CrossOver/bin/wine')}],
            'bottles':[{'id':'bottle','path':str(self.bottle),'runner_ids':['runner']}], 'games':[]}
        self.registry=self.root/'App Support/Profiles/registry.json'
        self.assets=self.root/'assets';self.assets.mkdir()
        names=('g923_bridge.dll','winmm.dll','g923_scs_telemetry.dll','G923TelemetryLab','mescon-synth')
        self.sources={n:self.assets/n for n in names}
        for n,p in self.sources.items():p.write_bytes(b'fake:'+n.encode())
        self.sources['g923_bridge.dll'].write_bytes(b'prefix'+b'CFBUID=0'.ljust(24,b'\0')+b'suffix')

    def install(self):
        with patch.object(bootstrap,'payload',side_effect=lambda n:self.sources[n]),patch.object(bootstrap,'stopped'):
            return bootstrap.install(227300,self.game,self.bottle,self.runner,self.registry,self.inventory)

    def test_custom_paths_install_without_original_dinput_and_preserve_unrelated_registry(self):
        result=self.install();self.assertTrue(result['profiles'][0]['installed'])
        self.assertFalse((self.game.parent/'dinput8.dll').exists())
        text=(self.bottle/'user.reg').read_text()
        self.assertIn('"test"="keep"',text);self.assertIn('"winmm"="native,builtin"',text)
        profile=load_registry(self.registry)['profiles'][0]
        self.assertEqual(profile['source_bottle'],str(self.bottle))
        manifest=json.loads((Path(profile['session_dir'])/'manifest.json').read_text())
        self.assertIsNone(manifest['preserved_dlaa_sha'])
        self.assertEqual(manifest['runner_path'],str(self.runner))
        self.assertFalse(manifest['native_tf_direction_measured'])
        self.assertIn('hardware accepted',manifest['tf_motor_sign_source'])

    def test_existing_library_kept_byte_for_byte_and_second_install_is_idempotent(self):
        mod=self.game.parent/'dinput8.dll';mod.write_bytes(b'existing library')
        self.install();self.install()
        self.assertEqual(mod.read_bytes(),b'existing library')
        self.assertEqual(len(load_registry(self.registry)['profiles']),1)

    def test_foreign_winmm_never_overwritten_or_partial_files_left(self):
        foreign=self.game.parent/'winmm.dll';foreign.write_bytes(b'other mod')
        before=(self.bottle/'user.reg').read_bytes()
        with self.assertRaisesRegex(ValueError,'Existing file preserved'):self.install()
        self.assertEqual(foreign.read_bytes(),b'other mod')
        self.assertEqual((self.bottle/'user.reg').read_bytes(),before)
        self.assertFalse((self.game.parent/'g923_bridge.dll').exists())
        self.assertFalse(self.registry.exists())

    def test_registry_failure_rolls_back_files_without_touching_existing_library(self):
        mod=self.game.parent/'dinput8.dll';mod.write_bytes(b'keep')
        before=(self.bottle/'user.reg').read_bytes()
        with patch.object(bootstrap,'register',side_effect=OSError('disk write failed')):
            with self.assertRaisesRegex(OSError,'disk write failed'):self.install()
        self.assertEqual(mod.read_bytes(),b'keep')
        self.assertEqual((self.bottle/'user.reg').read_bytes(),before)
        self.assertFalse((self.game.parent/'g923_bridge.dll').exists())
        self.assertFalse((self.game.parent/'winmm.dll').exists())

    def test_incompatible_runner_refused_before_mutation(self):
        self.inventory['bottles'][0]['runner_ids']=[]
        with self.assertRaisesRegex(ValueError,'does not match'):self.install()
        self.assertFalse(self.registry.exists())

    def test_unknown_game_is_not_reported_installed(self):
        with self.assertRaisesRegex(ValueError,'not available'):
            bootstrap.select_installation(123,self.game,self.bottle,self.runner,self.inventory)

    def test_native_missing_dependencies_are_explicit_and_no_external_writes(self):
        native=self.game.with_name('dirtrally2.exe');native.write_bytes(b'game')
        with patch.object(bootstrap,'stopped'),patch('sdk_setup.default_store',return_value=self.root/'empty-sdk'):
            with self.assertRaisesRegex(ValueError,'original Logitech.*SDK'):
                bootstrap.install(690790,native,self.bottle,self.runner,self.registry,self.inventory)
        self.assertFalse((native.parent/'dinput8.dll').exists())
        self.assertFalse(self.registry.exists())

    def test_changed_library_blocks_repair_and_preserves_new_file(self):
        mod=self.game.parent/'dinput8.dll';mod.write_bytes(b'first version');self.install()
        mod.write_bytes(b'new version')
        with self.assertRaisesRegex(ValueError,'dinput8 changed'):self.install()
        self.assertEqual(mod.read_bytes(),b'new version')

    def test_registry_does_not_duplicate_existing_override(self):
        text='WINE REGISTRY Version 2\n\n[Software\\\\Wine\\\\AppDefaults\\\\eurotrucks2.exe\\\\DllOverrides] 1\n"winmm"="native,builtin"\n"other"="keep"\n'
        after,previous=bootstrap.registry_value(text,r'Software\\Wine\\AppDefaults\\eurotrucks2.exe\\DllOverrides','winmm','native,builtin')
        self.assertEqual(after,text);self.assertEqual(previous,'"native,builtin"')

    def test_missing_loader_override_cannot_report_installed(self):
        self.install()
        (self.bottle/'user.reg').write_text('WINE REGISTRY Version 2\n')
        result=bootstrap.status(self.registry)
        self.assertFalse(result['profiles'][0]['installed'])
        self.assertIn('override',result['profiles'][0]['detail'])

    def test_repair_refuses_running_prefix_before_creating_missing_dll(self):
        self.install();missing=self.game.parent/'winmm.dll';missing.unlink()
        with patch.object(bootstrap,'stopped',side_effect=ValueError('Close Steam')):
            with self.assertRaisesRegex(ValueError,'Close Steam'):
                bootstrap.install(227300,self.game,self.bottle,self.runner,self.registry,self.inventory)
        self.assertFalse(missing.exists())

    def native_fixture(self):
        (self.bottle/'cxbottle.conf').write_text('[Bottle]\n"Version"="27"\n"Timestamp"="123"\n')
        native=self.game.with_name('dirtrally2.exe');native.write_bytes(b'game')
        (native.parent/'steam_api64.dll').write_bytes(b'game provided steam api')
        builtin=self.bottle/'drive_c/windows/system32/dinput8.dll';builtin.parent.mkdir(parents=True);builtin.write_bytes(b'original wine builtin')
        (self.bottle/'system.reg').write_text('WINE REGISTRY Version 2\n\n[System\\\\CurrentControlSet\\\\Services\\\\winebus]\n"Start"=dword:00000003\n')
        transport=self.root/'Reviewed Transport';runtime=transport/'runtime';(runtime/'etc').mkdir(parents=True)
        (runtime/'etc/CrossOver.conf').write_text('[CrossOver]\n"ProductVersion"="27"\n"BuildTimestamp"="123"\n')
        (runtime/'bin').mkdir();(runtime/'bin/wine').write_bytes(b'private wine')
        hashes={}
        for name in ('x86_64-unix/winebus.so','x86_64-windows/winebus.sys','x86_64-windows/dinput8.dll'):
            path=runtime/'lib/wine'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(name.encode())
            if 'winebus' in name:hashes[name]=digest(path)
        (transport/'manifest.json').write_text(json.dumps({'purpose':'g923-isolated-crossover-hid-transport','prepared_module_hashes':hashes}))
        sdk=self.root/'original SDK.dll';sdk.write_bytes(b'lawfully supplied test sdk')
        self.sources['sdk-dinput8.dll']=self.sources['g923_bridge.dll']
        self.sources['g923-input']=self.root/'g923-input';self.sources['g923-input'].write_bytes(b'input publisher')
        self.inventory['runners'][0].update(version='27',timestamp='123')
        return native,transport,sdk

    def install_native(self,native,transport,sdk):
        with patch.object(bootstrap,'payload',side_effect=lambda n:self.sources[n]),patch.object(bootstrap,'stopped'),patch.object(bootstrap,'SDK_SHA',digest(sdk or self.root/'original SDK.dll')),patch('native_transport.require_stopped'),patch('native_connection.subprocess.check_output',return_value=''):
            return bootstrap.install(690790,native,self.bottle,self.runner,self.registry,self.inventory,transport,sdk)

    def test_native_setup_in_custom_bottle_records_transport_and_per_game_override(self):
        native,transport,sdk=self.native_fixture()
        result=self.install_native(native,transport,sdk)
        self.assertTrue(result['profiles'][0]['installed'])
        self.assertIn('[Software\\\\Wine\\\\AppDefaults\\\\dirtrally2.exe\\\\DllOverrides]',(self.bottle/'user.reg').read_text())
        self.assertIn('"dinput8"="native,builtin"',(self.bottle/'user.reg').read_text())
        session=Path(load_registry(self.registry)['profiles'][0]['session_dir'])
        self.assertEqual((session/'runtime/bin/wine').read_bytes(),b'private wine')
        self.assertEqual((session/'backup-2').read_bytes(),b'original wine builtin')

    def test_correct_sdk_already_in_bottle_is_reused_and_never_owned(self):
        native,transport,sdk=self.native_fixture()
        target=self.bottle/'drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll'
        target.parent.mkdir(parents=True);target.write_bytes(sdk.read_bytes())
        before=target.stat().st_mtime_ns
        result=self.install_native(native,transport,target)
        self.assertTrue(result['profiles'][0]['installed'])
        session=Path(load_registry(self.registry)['profiles'][0]['session_dir'])
        manifest=json.loads((session/'manifest.json').read_text())
        self.assertTrue(manifest['sdk_preexisting'])
        self.assertEqual(manifest['preserved_sdk_sha'],digest(target))
        transaction=json.loads((session/'transaction.json').read_text())
        self.assertNotIn(str(target),transaction['files'])
        self.assertEqual(target.stat().st_mtime_ns,before)

    def test_rollback_never_removes_existing_sdk(self):
        native,transport,sdk=self.native_fixture()
        target=self.bottle/'drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll'
        target.parent.mkdir(parents=True);target.write_bytes(sdk.read_bytes())
        before=target.stat().st_mtime_ns
        with patch.object(bootstrap,'register',side_effect=OSError('registry failure')):
            with self.assertRaisesRegex(OSError,'registry failure'):
                self.install_native(native,transport,target)
        self.assertEqual(target.read_bytes(),sdk.read_bytes())
        self.assertEqual(target.stat().st_mtime_ns,before)
        self.assertFalse((native.parent/'dinput8.dll').exists())

    def test_different_existing_sdk_is_preserved_before_game_changes(self):
        native,transport,sdk=self.native_fixture()
        target=self.bottle/'drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll'
        target.parent.mkdir(parents=True);target.write_bytes(b'newer or foreign SDK')
        before=(self.bottle/'user.reg').read_bytes()
        with self.assertRaisesRegex(ValueError,'existing bottle SDK differs'):
            self.install_native(native,transport,sdk)
        self.assertEqual(target.read_bytes(),b'newer or foreign SDK')
        self.assertEqual((self.bottle/'user.reg').read_bytes(),before)
        self.assertFalse((native.parent/'dinput8.dll').exists())

    def test_fresh_install_uses_managed_transport_and_imported_sdk_without_manual_paths(self):
        native,prepared,sdk=self.native_fixture()
        # A real tiny fixture runtime is processed by the transport installer;
        # only SDK static validation is mocked because these are not PE DLLs.
        runtime=self.runner/'Contents/SharedSupport/CrossOver'
        shutil.copytree(prepared/'runtime',runtime)
        payloads=self.root/'bundle/winebus';payloads.mkdir(parents=True)
        originals={};modules={}
        for name in transport_setup.MODULES:
            source=prepared/'runtime/lib/wine'/name
            destination=payloads/'fixture'/Path(name).name
            destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
            modules[name]={'path':str(destination.relative_to(payloads)),'sha256':digest(destination)}
            stock=runtime/'lib/wine'/name;stock.write_bytes(('stock '+name).encode());originals[name]=digest(stock)
        catalog={'version':1,'builds':[{'id':'fixture','product_version':'27','build_timestamp':'123','wine_version':'fixture',
                                      'original_module_hashes':originals,'modules':modules}]}
        (payloads/'catalog.json').write_text(json.dumps(catalog))
        store=self.root/'managed Transports'
        managed=transport_setup.install(self.runner,store=store,payload_root=payloads)
        with patch.object(transport_setup,'default_store',return_value=store),patch.object(transport_setup,'_catalog',return_value=(payloads,catalog['builds'])),patch.object(native_setup.sdk_setup,'status',return_value={'installed':True,'path':str(sdk),'version':'1.3.12','detail':'Imported'}):
            result=self.install_native(native,None,None)
        self.assertTrue(result['profiles'][0]['installed'])
        session=Path(load_registry(self.registry)['profiles'][0]['session_dir'])
        manifest=json.loads((session/'manifest.json').read_text())
        self.assertEqual(manifest['runtime_hashes'],managed['module_hashes'])
        self.assertEqual((session/'runtime/bin/wine').read_bytes(),b'private wine')

    def test_atomic_registry_write_error_keeps_original(self):
        path=self.bottle/'user.reg';before=path.read_bytes()
        with patch.object(bootstrap.os,'replace',side_effect=OSError('replacement denied')):
            with self.assertRaises(OSError):bootstrap.replace_bytes(path,before,b'after')
        self.assertEqual(path.read_bytes(),before)


class BundledComponents(unittest.TestCase):
    def test_moved_bundle_and_hash_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'Moved.app/Contents/Resources/BridgeTools';p=root/'payloads';p.mkdir(parents=True)
            (p/'g923-input').write_bytes(b'own executable')
            (p/'manifest.json').write_text(json.dumps({'version':1,'files':{'g923-input':{'path':'g923-input','sha256':digest(p/'g923-input')}}}))
            self.assertEqual(payload('g923-input',root=root),p/'g923-input')
            (p/'g923-input').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'differs'):payload('g923-input',root=root)

    def test_runtime_supports_app_or_binary_and_real_bottle_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Path(tmp)/'Whatever.app';runtime=app/'Contents/SharedSupport/CrossOver'
            wine=runtime/'bin/wine';wine.parent.mkdir(parents=True);wine.write_bytes(b'wine')
            bottle=Path(tmp)/'Bottles/Not Steam'
            self.assertEqual(runtime_directory(Path(tmp),{'runner_path':str(app)}),runtime)
            self.assertEqual(wine_command(Path(tmp),{'runner_path':str(wine),'source_bottle':str(bottle)}),[str(wine),'--bottle','Not Steam'])


if __name__=='__main__':unittest.main()
