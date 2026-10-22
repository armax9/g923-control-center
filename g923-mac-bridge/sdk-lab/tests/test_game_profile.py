import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
import game_profile as gp
import sdk_game
class Profiles(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
  self.base=self.root/'accepted';self.base.mkdir();self.prefix=self.root/'Steam';self.prefix.mkdir();self.exe=self.root/'candidate/game.exe';self.exe.parent.mkdir();self.exe.write_bytes(b'game');(self.exe.parent/'steam_api64.dll').write_bytes(b'api')
  self.source=self.root/'dirt/dinput8.dll';self.source.parent.mkdir();self.source.write_bytes(b'accepted bridge')
  self.manifest={'source_bottle':str(self.prefix),'game_exe':str(self.source.parent/'dirtrally2.exe'),'game_dll_sha':gp.sha(self.source)}
  (self.base/'manifest.json').write_text(json.dumps(self.manifest))
  for name,value in [('BASE',self.base),('ROOT',self.root)]:
   patcher=patch.object(gp,name,value);patcher.start();self.addCleanup(patcher.stop)
  patcher=patch.object(gp,'sdk_check');patcher.start();self.addCleanup(patcher.stop)
 def test_install_retains_accepted_payload_and_sets_game_identity(self):
  gp.install_sdk(self.exe,self.prefix,805550)
  session=gp.session_for(self.exe,self.prefix);m=json.loads((session/'manifest.json').read_text())
  self.assertEqual(m['steam_app_id'],805550);self.assertTrue(m['applied']);self.assertEqual(self.source.read_bytes(),b'accepted bridge')
  self.assertEqual((self.exe.parent/'dinput8.dll').read_bytes(),b'accepted bridge')
 def test_foreign_dll_is_never_replaced(self):
  target=self.exe.parent/'dinput8.dll';target.write_bytes(b'overlay')
  with self.assertRaisesRegex(ValueError,'preserved'):gp.install_sdk(self.exe,self.prefix,805550)
  self.assertEqual(target.read_bytes(),b'overlay')
 def test_other_bottle_needs_transport(self):
  with self.assertRaisesRegex(ValueError,'transport'):gp.install_sdk(self.exe,self.root/'other',805550)
  self.assertFalse((self.exe.parent/'dinput8.dll').exists())
 def test_remove_refuses_changed_dll(self):
  gp.install_sdk(self.exe,self.prefix,805550);target=self.exe.parent/'dinput8.dll';target.write_bytes(b'user changed')
  with patch.object(gp,'stopped'):
   with self.assertRaisesRegex(ValueError,'changed'):gp.remove_sdk(self.exe,self.prefix)
  self.assertEqual(target.read_bytes(),b'user changed')
 def test_environment_uses_actual_game_appid(self):
  with patch.object(sdk_game,'load',return_value={'steam_app_id':805550}):
   env=sdk_game.environment(self.base)
  self.assertEqual(env['SteamAppId'],'805550');self.assertEqual(env['SteamGameId'],'805550')
 def test_scs_preserves_foreign_plugin(self):
  source=self.root/'outputs/mescon-telemetry/build/logi_tf_scs.dll';source.parent.mkdir(parents=True);source.write_bytes(b'our plugin')
  target=self.exe.parent/'plugins/logi_tf_scs.dll';target.parent.mkdir();target.write_bytes(b'foreign plugin')
  with patch.object(gp,'TOP',self.root),patch.object(gp,'stopped'):
   with self.assertRaisesRegex(ValueError,'preserved'):gp.scs_action('install-scs',self.exe,self.prefix,270880)
  self.assertEqual(target.read_bytes(),b'foreign plugin')
 def test_scs_removal_refuses_user_changes(self):
  source=self.root/'outputs/mescon-telemetry/build/logi_tf_scs.dll';source.parent.mkdir(parents=True);source.write_bytes(b'our plugin')
  with patch.object(gp,'TOP',self.root),patch.object(gp,'stopped'):
   gp.scs_action('install-scs',self.exe,self.prefix,270880)
   target=self.exe.parent/'plugins/logi_tf_scs.dll';target.write_bytes(b'updated plugin')
   with self.assertRaisesRegex(ValueError,'changed'):gp.scs_action('remove-scs',self.exe,self.prefix,270880)
  self.assertEqual(target.read_bytes(),b'updated plugin')
