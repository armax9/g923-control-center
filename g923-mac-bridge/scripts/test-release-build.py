#!/usr/bin/env python3
"""Offline checks for portable release inputs, export preservation and payload manifests."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


release = module('release_builder', 'scripts/build-release-components.py')
winmm = module('winmm_builder', 'sdk-lab/winmm-chain/build.py')
force = module('force_builder', 'scripts/build-ets2-force-bridge.py')


def winmm_fixture(path):
    data = bytearray(2048)
    def u16(offset, value): struct.pack_into('<H', data, offset, value)
    def u32(offset, value): struct.pack_into('<I', data, offset, value)
    data[:2] = b'MZ'
    u32(60, 128)
    data[128:132] = b'PE\0\0'
    u16(132, 0x8664)
    u16(134, 1)
    u16(148, 240)
    u16(152, 0x20b)
    u32(264, 0x1000)
    section = 392
    u32(section + 8, 1536)
    u32(section + 12, 0x1000)
    u32(section + 16, 1536)
    u32(section + 20, 512)
    for offset, value in [(16, 1), (20, 2), (24, 1), (28, 0x1040), (32, 0x1048), (36, 0x1050)]:
        u32(512 + offset, value)
    u32(576, 0x1100)
    u32(580, 0x1110)
    u32(584, 0x1060)
    u16(592, 0)
    data[608:620] = b'timeGetTime\0'
    path.write_bytes(data)


class ReleaseBuildTests(unittest.TestCase):
    def test_tool_versions_support_zig_subcommand_and_standard_flags(self):
        with patch.object(release.subprocess, 'check_output', return_value='0.13.0\n') as call:
            self.assertEqual(release.tool_version('zig','/tools/zig'),'0.13.0')
            call.assert_called_once_with(['/tools/zig','version'],text=True)
        with patch.object(release.subprocess, 'check_output', return_value='rustc 1.99.1\n') as call:
            self.assertEqual(release.tool_version('rustc','/tools/rustc'),'rustc 1.99.1')
            call.assert_called_once_with(['/tools/rustc','--version'],text=True)

    def test_winmm_exports_preserve_names_and_ordinal_only_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'winmm.dll'
            winmm_fixture(path)
            self.assertEqual(winmm.exports_from(path), [
                {'name': 'timeGetTime', 'ordinal': 1}, {'name': None, 'ordinal': 2}])
            with patch.object(winmm.subprocess, 'run'):
                winmm.build(path, Path(temporary) / 'out', '/explicit/zig')
            definition = (Path(temporary) / 'out/exports.def').read_text()
            self.assertIn('timeGetTime=wp_0 @1', definition)
            self.assertIn('wp_1 @2 NONAME', definition)

    def test_invalid_winmm_is_rejected_before_output_or_compilation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'other.dll').write_bytes(b'MZ not a PE')
            with patch.object(winmm.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    winmm.build(root / 'other.dll', root / 'out', '/zig')
            self.assertFalse((root / 'out').exists())
            run.assert_not_called()

    def test_wine_export_source_is_explicit_no_application_auto_selection(self):
        args = argparse.Namespace(mescon_source=ROOT.parent / 'mescon-telemetry', wine_winmm=None)
        with self.assertRaisesRegex(ValueError, 'explicitly select'):
            release.plan(args)

    def test_manifest_contains_complete_portable_checksums(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / 'out'
            output.mkdir()
            sources = {}
            for name in release.PAYLOAD_NAMES:
                path = root / ('source-' + name)
                path.write_bytes(('compiled ' + name).encode())
                sources[name] = path
            manifest = release.write_payloads(output, sources)
            self.assertEqual(set(manifest['files']), release.PAYLOAD_NAMES)
            self.assertNotIn(str(root), json.dumps(manifest))
            for name, entry in manifest['files'].items():
                self.assertEqual(entry['path'], name)
                self.assertEqual(entry['sha256'], release.digest(output / name))

    def test_missing_payload_cannot_create_an_incomplete_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                release.write_payloads(output, {})
            self.assertFalse((output / 'manifest.json').exists())

    def test_existing_build_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = {'output': temporary, 'mescon_source': str(ROOT.parent / 'mescon-telemetry')}
            with patch.object(release.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    release.build(argparse.Namespace(), report)
            run.assert_not_called()

    def test_bridge_defaults_do_not_embed_a_developer_uid(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            def compiler(command, **kwargs):
                if '-shared' in command:
                    Path(command[command.index('-o') + 1]).write_bytes(b'MZ' + b'CFBUID=0'.ljust(24, b'\0') + b'end')
            with patch.object(force.subprocess, 'run', side_effect=compiler):
                payload = force.build(output, '/explicit/zig', unknown_force_metadata=True, tests=False)
            self.assertIn(b'CFBUID=0\0', payload.read_bytes())
            record = json.loads((output / 'candidate.json').read_text())
            self.assertEqual(record['max_force_newtons'], 0)
            self.assertFalse(record['physical_acceptance'])


if __name__ == '__main__':
    unittest.main()
