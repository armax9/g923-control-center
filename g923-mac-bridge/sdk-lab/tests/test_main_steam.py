import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from main_steam import patch_registry,unpatch_registry,BUS,CLSID,section
class RegistryTest(unittest.TestCase):
 def test_roundtrip_preserves_other_settings(self):
  source='WINE REGISTRY Version 2\n\n['+BUS+'] 123\n"Start"=dword:00000003\n\n[Other]\n"Game"="keep"\n\n'
  changed=patch_registry(source)
  self.assertIn('046D:C266',changed);self.assertIsNotNone(section(changed,CLSID)[0])
  self.assertEqual(unpatch_registry(changed).rstrip(),source.rstrip())
 def test_existing_registration_rejected(self):
  with self.assertRaises(ValueError):patch_registry('['+BUS+']\n\n['+CLSID+']\n@="other"\n')
 def test_existing_allowlist_rejected(self):
  with self.assertRaises(ValueError):patch_registry('['+BUS+']\n"EnableHidraw"="other"\n')
 def test_changed_registration_not_removed(self):
  text=patch_registry('['+BUS+']\n')
  with self.assertRaises(ValueError):unpatch_registry(text.replace('trueforce_sdk_x64.dll','other.dll'))
