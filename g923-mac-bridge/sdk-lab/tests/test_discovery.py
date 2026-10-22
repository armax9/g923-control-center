# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
import discovery


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / 'Different User'
        self.apps = self.root / 'Installed Apps'
        self.home.mkdir(); self.apps.mkdir()

    def write(self, path, text=''):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def app(self, filename, *, name='CrossOver', version='26.0.1.12345', stamp='20260101T000000Z', custom=None):
        app = self.apps / filename
        self.write(app / 'Contents/Info.plist')
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier':'com.codeweavers.CrossOver',
            'CFBundleName':name, 'CFBundleShortVersionString':'20260101'}))
        runtime = app / 'Contents/SharedSupport/CrossOver'
        wine = self.write(runtime / 'bin/wine', '#!/bin/sh\nexit 1\n')
        wine.chmod(0o755)
        self.write(runtime / 'etc/CrossOver.conf', '\n'.join([
            '[CrossOver]', '"ProductVersion" = "' + version + '"',
            '"BuildTimestamp" = "' + stamp + '"',
            '"BuildTag" = "' + ('cxpreview' if 'Preview' in name else 'cxrelease') + '"',
            *(['"BottlePath" = "' + str(custom) + '"'] if custom else [])]))
        return app

    def bottle(self, name='My Steam', *, root=None, version='26.0.1.12345', stamp='20260101T000000Z'):
        root = root or self.home / 'Library/Application Support/CrossOver/Bottles'
        bottle = root / name
        self.write(bottle / 'user.reg', 'WINE REGISTRY Version 2\n')
        self.write(bottle / 'cxbottle.conf', '[Bottle]\n"Version" = "' + version + '"\n"Timestamp" = "' + stamp + '"\n')
        (bottle / 'drive_c').mkdir()
        (bottle / 'dosdevices').mkdir()
        (bottle / 'dosdevices/c:').symlink_to(bottle / 'drive_c')
        return bottle

    def steam(self, bottle, relative='Program Files (x86)/Steam'):
        steam = bottle / 'drive_c' / relative
        self.write(steam / 'steamapps/libraryfolders.vdf', '"libraryfolders" {}\n')
        return steam

    def game(self, library, appid=227300, folder='Euro Truck Simulator 2', name=None):
        manifest = ('"AppState" { "appid" "' + str(appid) + '" "name" "' + (name or folder) +
                    '" "installdir" "' + folder + '" }\n')
        self.write(library / ('steamapps/appmanifest_' + str(appid) + '.acf'), manifest)
        base = library / 'steamapps/common' / folder
        exe = discovery.KNOWN_EXECUTABLES.get(appid, ['Game.exe'])[0]
        self.write(base / exe)
        return base / exe

    def discover(self, **kwargs):
        return discovery.discover(home=self.home, app_roots=[self.apps], spotlight=False, environ={}, **kwargs)

    def test_empty_inventory_does_not_launch_anything(self):
        with mock.patch.object(discovery.subprocess, 'run', side_effect=AssertionError('No process expected')):
            self.assertEqual(self.discover(), dict(version=1,runners=[],bottles=[],games=[],issues=[]))

    def test_app_identity_uses_metadata_not_filename_and_both_channels(self):
        stable = self.app('A Renamed Wrapper.app')
        preview = self.app('CrossOver.app', name='CrossOver Preview', version='27.0.0.45678')
        bottle = self.bottle()
        result = self.discover()
        self.assertEqual({x['channel'] for x in result['runners']}, {'stable','preview'})
        r = next(r for r in result['runners'] if r['channel'] == 'stable')
        self.assertEqual(r['path'],str(stable))
        self.assertEqual(r['version'],'26.0.1.12345')
        self.assertEqual(result['bottles'][0]['runner_ids'],[r['id']])
        self.assertEqual(result['bottles'][0]['path'],str(bottle))
        self.assertNotIn('20260101',[r['version'] for r in result['runners']])

    def test_preview_bottle_uses_runtime_build_not_filename(self):
        self.app('CrossOver.app')
        preview = self.app('Also Renamed.app', name='CrossOver Preview', version='27.0.0.45678', stamp='20261006T113703Z')
        self.bottle(version='27.0.0.45678',stamp='20261006T113703Z')
        result = self.discover()
        r = next(r for r in result['runners'] if r['path'] == str(preview))
        self.assertEqual(result['bottles'][0]['runner_ids'],[r['id']])

    def test_missing_runtime_and_foreign_bundle_are_not_runners(self):
        one = self.app('One.app'); (one / 'Contents/SharedSupport/CrossOver/bin/wine').unlink()
        two = self.app('Two.app'); (two / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'other.App','CFBundleName':'CrossOver'}))
        three = self.app('Three.app'); (three / 'Contents/SharedSupport/CrossOver/bin/wine').chmod(0o644)
        self.assertEqual(self.discover()['runners'],[])

    def test_ambiguous_same_build_is_never_chosen_by_order(self):
        self.app('First.app'); self.app('Second.app')
        self.bottle()
        result = self.discover()
        self.assertEqual(result['bottles'][0]['runner_match'],'ambiguous')
        self.assertEqual(len(result['bottles'][0]['runner_ids']),2)
        self.assertEqual(result['issues'][0]['scope'],'bottle')

    def test_version_mismatch_exposes_bottle_but_cannot_launch(self):
        self.app('Old.app'); self.bottle(version='27.0.0.45678')
        result = self.discover()
        self.assertEqual(result['bottles'][0]['runner_ids'],[])
        self.assertEqual(result['bottles'][0]['runner_match'],'version-mismatch')

    def test_custom_bottlepath_configuration_and_nested_collections(self):
        custom = self.root / 'External Drive/My Bottle Collection'
        self.app('CrossOver.app', custom=custom)
        target = self.bottle(name='Nested/My Renamed Bottle',root=custom)
        self.bottle(name='NotDiscovered',root=self.root / 'Random')
        result = self.discover()
        self.assertEqual([b['path'] for b in result['bottles']],[str(target)])

    def test_user_configuration_overrides_runtime_with_home_expansion(self):
        self.app('CrossOver.app',custom=self.root / 'Factory')
        target = self.bottle(root=self.home / 'Custom Bottles')
        self.write(self.home / 'Library/Application Support/CrossOver/CrossOver.conf',
                   ';"BottlePath" = "/never"\n[CrossOver]\n"BottlePath" = "${HOME}/Custom Bottles"\n')
        self.assertEqual(self.discover()['bottles'][0]['path'],str(target))

    def test_environment_colon_paths_and_explicit_bottle_exports(self):
        self.app('CrossOver.app')
        one = self.bottle(root=self.root / 'DiskA')
        two = self.bottle(root=self.root / 'DiskB')
        third = self.bottle(root=self.root / 'Export')
        result = discovery.discover(home=self.home,app_roots=[self.apps],spotlight=False,
                                    environ={'CX_BOTTLE_PATH':str(one.parent)+':'+str(two.parent)},bottle_roots=[third])
        self.assertEqual({b['path'] for b in result['bottles']},{str(one),str(two),str(third)})

    def test_preference_custom_path(self):
        self.app('CrossOver.app')
        bottle = self.bottle(root=self.root / 'PrefsLocation')
        path = self.home / 'Library/Preferences/com.codeweavers.CrossOver.plist'
        path.parent.mkdir(parents=True)
        path.write_bytes(plistlib.dumps({'BottleDirectory':str(bottle.parent),'BottleSidebarExpanded':True}))
        self.assertEqual(self.discover()['bottles'][0]['path'],str(bottle))

    def test_steam_registry_custom_path_case_and_external_dos_drive_new_vdf(self):
        self.app('CrossOver.app'); bottle = self.bottle()
        steam = self.steam(bottle,'Games/Not The Default Steam')
        with (bottle/'user.reg').open('a') as f:
            f.write('[Software\\\\Valve\\\\Steam]\n"SteamPath"="c:\\\\games\\\\not the default steam"\n')
        external = self.root / 'External Games'; external.mkdir()
        (bottle / 'dosdevices/d:').symlink_to(external)
        library = external / 'Library With Spaces'
        exe = self.game(library)
        self.write(steam/'steamapps/libraryfolders.vdf','"LibraryFolders" { "0" { "path" "C:\\\\Games\\\\Not The Default Steam" } "1" { "path" "D:\\\\Library With Spaces" "apps" {"227300" "1"} } }')
        result = self.discover()
        self.assertEqual(result['bottles'][0]['steam_roots'],[str(steam)])
        self.assertEqual(len(result['games']),1)
        game = result['games'][0]
        self.assertEqual(game['exe'],str(exe)); self.assertEqual(game['appid'],227300)
        self.assertEqual(game['bottle_id'],result['bottles'][0]['id'])
        self.assertEqual(game['runner_ids'],result['bottles'][0]['runner_ids'])

    def test_old_vdf_z_drive_symlink_dedup_and_case_executable(self):
        self.app('CrossOver.app'); bottle = self.bottle(); steam = self.steam(bottle)
        lib = self.root / 'Actual Library'
        exe = self.game(lib,690790,'DiRT Rally 2.0')
        exe.rename(exe.with_name('DIRTRALLY2.EXE'))
        alias = self.root / 'Library Alias'; alias.symlink_to(lib)
        self.write(steam/'steamapps/libraryfolders.vdf','"LibraryFolders" {"1" "Z:'+str(alias)+'" "2" "Z:'+str(lib)+'"}')
        result = self.discover()
        self.assertEqual(len(result['games']),1)
        self.assertEqual(result['games'][0]['exe'],str(exe.with_name('DIRTRALLY2.EXE')))

    def test_native_steam_and_shared_game_keep_prefix_identity(self):
        self.app('CrossOver.app')
        lib = self.home / 'Library/Application Support/Steam'
        self.game(lib)
        for name in ('Bottle One','Bottle Two'):
            steam = self.steam(self.bottle(name))
            self.write(steam/'steamapps/libraryfolders.vdf','"libraryfolders" {"0" {"path" "'+str(lib)+'"}}')
        result = self.discover()
        self.assertEqual(len(result['games']),3)
        self.assertEqual(len({g['id'] for g in result['games']}),3)
        native = next(g for g in result['games'] if g['bottle_id'] is None)
        self.assertEqual(native['runner_ids'],[])

    def test_missing_library_and_uninstalled_manifest_are_skipped(self):
        self.app('CrossOver.app'); steam = self.steam(self.bottle())
        self.write(steam/'steamapps/libraryfolders.vdf','"libraryfolders" {"1" {"path" "D:\\\\Missing"}}')
        self.write(steam/'steamapps/appmanifest_227300.acf','"AppState" {"appid" "227300" "installdir" "Not Installed"}')
        self.assertEqual(self.discover()['games'],[])

    def test_unsafe_install_directory_or_mismatched_id_reported(self):
        self.app('CrossOver.app'); steam = self.steam(self.bottle())
        for fields in ('"appid" "227300" "installdir" "../Escape"','"appid" "690790" "installdir" "Game"'):
            self.write(steam/'steamapps/appmanifest_227300.acf','"AppState" {'+fields+'}')
            result = self.discover()
            self.assertEqual(result['games'],[])
            self.assertEqual(result['issues'][0]['scope'],'steam')

    def test_corrupt_manifest_or_vdf_does_not_hide_other_installed_games(self):
        self.app('CrossOver.app'); steam = self.steam(self.bottle())
        self.game(steam,690790,'DiRT Rally 2.0')
        self.write(steam/'steamapps/appmanifest_227300.acf','broken {')
        self.write(steam/'steamapps/libraryfolders.vdf','unclosed {')
        result = self.discover()
        self.assertEqual([g['appid'] for g in result['games']],[690790])
        self.assertEqual(len(result['issues']),2)

    def test_invalid_app_plist_and_preferences_do_not_crash_scan(self):
        app = self.app('Broken.app')
        self.write(app/'Contents/Info.plist','<plist>broken &xml</plist>')
        self.app('Valid.app'); self.bottle()
        self.write(self.home/'Library/Preferences/com.codeweavers.CrossOver.plist','not a plist')
        result = self.discover()
        self.assertEqual(len(result['runners']),1)
        self.assertEqual(len(result['bottles']),1)
        self.assertEqual(len(result['issues']),1)

    def test_inventory_is_read_only_and_deterministic(self):
        self.app('CrossOver.app'); steam = self.steam(self.bottle()); self.game(steam)
        before = {str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        first = self.discover(); second = self.discover()
        after = {str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after); self.assertEqual(first,second)
        json.dumps(first)

    def test_vdf_escaping_comments_unquoted_and_invalid(self):
        self.assertEqual(discovery.parse_vdf('//comment\nroot { path "D:\\\\A \\"Quote\\"" value 2 }'),
                         {'root':{'path':'D:\\A "Quote"','value':'2'}})
        for text in ('"root" {', '}','"a" "b" "a" "c"','"root" "unterminated'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):discovery.parse_vdf(text)

    def test_case_collision_is_not_silently_selected(self):
        directory = self.root / 'Collision'; directory.mkdir()
        self.write(directory/'Foo'); self.write(directory/'FOO')
        if len(list(directory.iterdir())) < 2:
            self.skipTest('Host volume is case insensitive')
        with self.assertRaises(ValueError):discovery.case_path(directory/'foo')

    def test_spotlight_optional_is_read_only_and_handles_missing_command(self):
        app = self.app('Renamed.app')
        result = mock.Mock(returncode=0,stdout=str(app)+'\n')
        with mock.patch.object(discovery.subprocess,'run',return_value=result) as run:
            found = discovery.discover(home=self.home,app_roots=[],spotlight=True,environ={})
        self.assertEqual(len(found['runners']),1)
        self.assertEqual(run.call_args.args[0][0],'/usr/bin/mdfind')
        with mock.patch.object(discovery.subprocess,'run',side_effect=FileNotFoundError):
            self.assertEqual(discovery.discover(home=self.home,app_roots=[],spotlight=True,environ={})['runners'],[])


if __name__ == '__main__':
    unittest.main()
