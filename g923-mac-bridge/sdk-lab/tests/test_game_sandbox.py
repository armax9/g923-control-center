import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from game_sandbox import parse_vdf, write_vdf


class GameSandboxTests(unittest.TestCase):
    def test_windows_paths_round_trip(self):
        value = {'libraryfolders': {'1': {'path': r'Z:\Users\test "quoted"',
                                         'apps': {'690790': '123'}}}}
        self.assertEqual(parse_vdf(write_vdf(value)), value)

    def test_comments_outside_strings(self):
        source = '// test\n"root" { "url" "https://example.test" // note\n }'
        self.assertEqual(parse_vdf(source), {'root': {'url': 'https://example.test'}})

    def test_reject_ambiguous_duplicate_key(self):
        with self.assertRaises(ValueError):
            parse_vdf('"root" { "path" "one" "path" "two" }')

    def test_reject_unclosed_block(self):
        with self.assertRaises(ValueError):
            parse_vdf('"root" { "path" "one"')


if __name__ == '__main__':
    unittest.main()
