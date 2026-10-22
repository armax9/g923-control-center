# SPDX-License-Identifier: GPL-3.0-only
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
import game_settings


class GameSettingsTests(unittest.TestCase):
    def document(self, value):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'settings.json'
        path.write_text(json.dumps(value))
        return path

    def test_missing_file_preserves_accepted_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            games = game_settings.load_settings(Path(directory) / 'missing')
        self.assertEqual(games['227300'], {'ffbStrength':100, 'trueForceEnabled':True, 'engineVibration':10})
        self.assertEqual(games['690790'], {})

    def test_partial_settings_preserve_independent_defaults(self):
        path = self.document({'version':1, 'games':{'227300':{'engineVibration':0}, '99999':{}}})
        self.assertEqual(game_settings.for_game(227300, path), {'ffbStrength':100,'trueForceEnabled':True,'engineVibration':0})
        self.assertEqual(game_settings.for_game(99999, path), {})

    def test_saved_engine_level_is_preserved_when_default_changes(self):
        path = self.document({'version':1, 'games':{'227300':{'engineVibration':40}}})
        self.assertEqual(game_settings.for_game(227300,path)['engineVibration'],40)

    def test_each_bad_existing_file_fails_instead_of_reverting_to_full_force(self):
        documents = [
            {}, {'version':True,'games':{}}, {'version':2,'games':{}},
            {'version':1,'games':[]}, {'version':1,'games':{},'unexpected':True},
            {'version':1,'games':{'227300':[]}},
            *[{'version':1,'games':{'227300':{'ffbStrength':value}}} for value in (-1,101,True,'40',None,float('nan'),float('inf'))],
            *[{'version':1,'games':{'227300':{'engineVibration':value}}} for value in (-1,101,False,'40',None,float('nan'),float('inf'))],
            *[{'version':1,'games':{'227300':{'trueForceEnabled':value}}} for value in (0,1,None,'true')],
            {'version':1,'games':{'227300':{'unknownGain':1}}},
            {'version':1,'games':{'690790':{'ffbStrength':40}}},
            {'version':1,'games':{'99999':{'trueForceEnabled':True}}},
            {'version':1,'games':{'0227300':{}}},
        ]
        for document in documents:
            with self.subTest(document=document):
                with self.assertRaises(ValueError):game_settings.load_settings(self.document(document))

    def test_truncation_and_duplicate_keys_fail(self):
        path = self.document({'version':1,'games':{}})
        for raw in ('{', '{"version":1,"games":{},"games":{}}', '{"version":1,"games":{"227300":{"ffbStrength":0,"ffbStrength":100}}}'):
            path.write_text(raw)
            with self.assertRaises(ValueError):game_settings.load_settings(path)

    def test_boundaries_roundtrip(self):
        for strength, enabled, vibration in [(0,False,100),(100,True,0),(37.5,True,45.5)]:
            values = {'ffbStrength':strength,'trueForceEnabled':enabled,'engineVibration':vibration}
            path = self.document({'version':1,'games':{'227300':values,'690790':{}}})
            self.assertEqual(game_settings.for_game(227300,path),values)
            self.assertEqual(game_settings.for_game(690790,path),{})
