import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import native_setup

class NativeSetupWorkflow(unittest.TestCase):
    def test_existing_bottle_sdk_is_detected_without_import_or_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);file=root/'drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll'
            file.parent.mkdir(parents=True);file.write_bytes(b'original fixture')
            before=file.stat().st_mtime_ns
            with patch.object(native_setup.sdk_setup,'status',return_value={'installed':False,'path':'/managed/sdk','version':'1.3.12','detail':'Missing'}),patch.object(native_setup.sdk_setup,'SDK_SHA',hashlib.sha256(file.read_bytes()).hexdigest()):
                state=native_setup.sdk_for_bottle(root)
            self.assertTrue(state['installed']);self.assertEqual(state['source'],'bottle')
            self.assertEqual(file.stat().st_mtime_ns,before)

    def test_imported_sdk_and_transport_supply_install_paths_automatically(self):
        with patch.object(native_setup,'sdk_for_bottle',return_value={'installed':True,'path':'/managed/sdk.dll'}),patch.object(native_setup.transport_setup,'status',return_value={'installed':True,'transport_dir':'/managed/transport'}):
            self.assertEqual(native_setup.dependencies('/bottle','/CrossOver.app'),(Path('/managed/transport'),Path('/managed/sdk.dll')))

    def test_each_missing_requirement_has_a_concrete_ui_action(self):
        with patch.object(native_setup,'sdk_for_bottle',return_value={'installed':False}):
            with self.assertRaisesRegex(ValueError,'Import.*SDK'):native_setup.dependencies('/bottle','/CrossOver.app')
        with patch.object(native_setup,'sdk_for_bottle',return_value={'installed':True,'path':'/sdk.dll'}),patch.object(native_setup.transport_setup,'status',return_value={'installed':False}):
            with self.assertRaisesRegex(ValueError,'Install transport'):native_setup.dependencies('/bottle','/CrossOver.app')

    def test_new_game_status_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry=Path(tmp)/'Profiles/registry.json'
            with patch.object(native_setup,'sdk_for_bottle',return_value={'installed':False}),patch.object(native_setup.transport_setup,'status',return_value={'installed':False,'available':True}):
                state=native_setup.status('/game.exe','/bottle','/CrossOver.app',registry)
            self.assertFalse(state['bottle']['configured']);self.assertIsNone(state['profile_id'])
            self.assertFalse(registry.parent.exists())

    def test_unknown_or_ambiguous_runner_keeps_selection_action_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry=Path(tmp)/'Profiles/registry.json'
            with patch.object(native_setup,'sdk_for_bottle',return_value={'installed':False}):
                state=native_setup.status('/game.exe','/bottle',None,registry)
            self.assertEqual(state['transport']['state'],'select_runner')
            self.assertTrue(state['transport']['available'])
            self.assertFalse(state['transport']['installed'])
            self.assertFalse(registry.parent.exists())

if __name__=='__main__':unittest.main()
