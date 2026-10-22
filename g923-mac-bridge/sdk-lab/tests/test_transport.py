import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import prepare_crossover_transport as transport


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.runtime, self.build = root / 'runtime', root / 'build'
        self.owner = root / 'lab/owner.json'
        self.bottle = root / 'lab/bottles/G923SDKLab'
        self.owner.parent.mkdir()
        self.owner.write_text(json.dumps({'purpose': 'g923-sdk-lab', 'project': str(transport.ROOT)}))
        for path in [self.runtime / 'bin/wine', self.bottle / 'cxbottle.conf',
                     self.build / 'dlls/winebus.sys/winebus.so']:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    def run_preflight(self):
        return transport.preflight(self.runtime, self.bottle, self.build, self.owner)

    def test_refuse_unowned_lab(self):
        self.owner.write_text('{}')
        with self.assertRaises(ValueError):
            self.run_preflight()

    def test_refuse_steam(self):
        self.bottle = self.bottle.with_name('Steam')
        with self.assertRaises(ValueError):
            self.run_preflight()

    @patch.object(transport, 'inspect')
    def test_missing_host_exports(self, inspect):
        inspect.side_effect = [{'x64': True, 'imports': [dict(dll='ntdll.dll', symbols=['Missing'])]},
                               {'exports': []}]
        with self.assertRaises(ValueError):
            self.run_preflight()

    @patch.object(transport, 'inspect')
    def test_import_preflight_without_copying(self, inspect):
        inspect.side_effect = [{'x64': True, 'imports': [dict(dll='ntdll.dll', symbols=['Known'])]},
                               {'exports': [dict(name='Known')]}]
        _, _, imports = self.run_preflight()
        self.assertEqual(imports, {'ntdll.dll': 1})
        self.assertFalse((self.runtime / 'lib').exists())


if __name__ == '__main__':
    unittest.main()
