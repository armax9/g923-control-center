#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build portable bridge payloads from public sources, without installation or HID access."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_NAMES = {'g923-input', 'G923ClassicLab', 'G923TelemetryLab', 'g923_bridge.dll',
                 'winmm.dll', 'g923_scs_telemetry.dll', 'mescon-synth', 'dinput8.dll', 'sdk-dinput8.dll'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_builder(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tool(value, fallback):
    found = shutil.which(str(value or fallback))
    if not found:
        raise ValueError('Build tool not found: ' + str(value or fallback))
    return str(Path(found).absolute())


def tool_version(name, executable):
    # Zig uses a subcommand, while the other supported tools use --version.
    argument = 'version' if name == 'zig' else '--version'
    return subprocess.check_output([executable, argument], text=True).splitlines()[0]


def plan(args):
    mescon = args.mescon_source.expanduser().resolve()
    for name in ('COPYING', 'UPSTREAM.json', 'src/main.rs', 'src/control.rs', 'src/scs_plugin.rs'):
        if not (mescon / name).is_file():
            raise ValueError('Incomplete mescon source tree: ' + name + '. Supply --mescon-source.')
    if not args.wine_winmm:
        raise ValueError('--wine-winmm or G923_WINE_WINMM must explicitly select the Wine export table')
    winmm = Path(args.wine_winmm).expanduser().resolve()
    load_builder('winmm_builder', ROOT / 'sdk-lab/winmm-chain/build.py').exports_from(winmm)
    return {'version': 1, 'output': str(args.output.expanduser().resolve()), 'mescon_source': str(mescon),
            'wine_winmm': str(winmm), 'tools': {
                'zig': tool(args.zig, 'zig'), 'rustc': tool(args.rustc, 'rustc'),
                'mingw': tool(args.mingw, 'x86_64-w64-mingw32-gcc'),
                'cmake': tool(None, 'cmake'), 'swift': tool(None, 'swift')},
            'payloads': sorted(PAYLOAD_NAMES), 'hardware_output': False, 'installation': False,
            'tests': not args.skip_tests}


def write_payloads(output, sources):
    if set(sources) != PAYLOAD_NAMES:
        raise ValueError('Incomplete release component set')
    manifest = {'version': 1, 'files': {}}
    for name, source in sorted(sources.items()):
        if not Path(source).is_file() or Path(source).is_symlink():
            raise ValueError('Missing built release component: ' + name)
        target = output / name
        shutil.copy2(source, target)
        manifest['files'][name] = {'path': name, 'sha256': digest(target)}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def build(args, report):
    output, mescon = Path(report['output']), Path(report['mescon_source'])
    if output.exists():
        raise ValueError('Build output already exists; choose a fresh --output directory')
    output.mkdir(parents=True)
    work = output / 'work'
    work.mkdir()
    environment = os.environ.copy()
    environment.setdefault('CLANG_MODULE_CACHE_PATH', str(work / 'clang-cache'))
    environment.setdefault('SWIFT_MODULECACHE_PATH', str(work / 'swift-cache'))
    def run(command):
        subprocess.run([str(value) for value in command], env=environment, check=True)
    tools = report['tools']
    core = work / 'core'
    # Keep assertions active in offline C++ tests while optimizing the payloads.
    run([tools['cmake'], '-S', ROOT, '-B', core, '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_CXX_FLAGS_RELEASE=-O2'])
    run([tools['cmake'], '--build', core, '-j', str(args.jobs)])
    if not args.skip_tests:
        run(['ctest', '--test-dir', core, '--output-on-failure'])
    swift = [tools['swift'], 'build', '--disable-sandbox', '--package-path', ROOT / 'vendor/crossover-ffb',
             '--scratch-path', work / 'swift']
    run(swift + ['--product', 'G923ClassicLab'])
    binary_dir = Path(subprocess.check_output([str(value) for value in swift + ['--show-bin-path']],
                                             env=environment, text=True).strip())
    bridge = load_builder('force_builder', ROOT / 'scripts/build-ets2-force-bridge.py')
    generic = bridge.build(work / 'dinput', tools['zig'], tests=False)
    ets2 = bridge.build(work / 'ets2', tools['zig'], unknown_force_metadata=True, tests=not args.skip_tests)
    winmm = load_builder('winmm_builder', ROOT / 'sdk-lab/winmm-chain/build.py').build(
        report['wine_winmm'], work / 'winmm', tools['zig'])
    rust = work / 'mescon'
    rust.mkdir()
    if not args.skip_tests:
        for source, name in [('synth.rs', 'synth-tests'), ('scs_plugin.rs', 'plugin-tests'),
                             ('main.rs', 'adapter-tests'), ('windows-relay/main.rs', 'relay-tests')]:
            run([tools['rustc'], '--edition=2021', '--test', mescon / 'src' / source, '-o', rust / name])
            run([rust / name])
    run([tools['rustc'], '--edition=2021', '-C', 'opt-level=2', mescon / 'src/main.rs', '-o', rust / 'mescon-synth'])
    run([tools['rustc'], '--edition=2021', '--crate-type', 'cdylib', '--crate-name', 'logi_tf_scs',
         '--target', 'x86_64-pc-windows-gnullvm', '-C', 'opt-level=2', '-C', 'target-feature=+crt-static',
         '-C', 'link-arg=-static', '-C', 'linker=' + tools['mingw'], mescon / 'src/scs_plugin.rs',
         '-o', rust / 'logi_tf_scs.dll'])
    manifest = write_payloads(output, {
        'g923-input': core / 'g923-input', 'G923ClassicLab': binary_dir / 'G923ClassicLab',
        'G923TelemetryLab': binary_dir / 'G923ClassicLab', 'dinput8.dll': generic, 'sdk-dinput8.dll': generic,
        'g923_bridge.dll': ets2, 'winmm.dll': winmm, 'mescon-synth': rust / 'mescon-synth',
        'g923_scs_telemetry.dll': rust / 'logi_tf_scs.dll'})
    # Only portable provenance belongs beside release payloads. No SDK/runtime or personal paths.
    source_hashes = {}
    for folder in ('src', 'vendor/crossover-ffb/bridge', 'vendor/crossover-ffb/Sources'):
        for path in sorted((ROOT / folder).rglob('*')):
            if path.is_file():
                source_hashes[str(path.relative_to(ROOT))] = digest(path)
    for path in sorted((mescon / 'src').rglob('*.rs')):
        source_hashes['mescon-telemetry/' + str(path.relative_to(mescon))] = digest(path)
    provenance = {'version': 1, 'hardware_tested': False, 'installed': False,
                  'wine_winmm_sha256': digest(report['wine_winmm']), 'sources': source_hashes,
                  'tool_versions': {name: tool_version(name, path) for name, path in tools.items()},
                  'payloads': manifest['files']}
    (output / 'build-report.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wine-winmm', type=Path, default=os.environ.get('G923_WINE_WINMM'),
                        help='Original x64 Wine winmm.dll used only to read exports; or G923_WINE_WINMM.')
    parser.add_argument('--zig', default=os.environ.get('ZIG'))
    parser.add_argument('--rustc', default=os.environ.get('G923_RUSTC'))
    parser.add_argument('--mingw', default=os.environ.get('G923_MINGW'))
    parser.add_argument('--mescon-source', type=Path, default=ROOT.parent / 'mescon-telemetry')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/public-components')
    parser.add_argument('--jobs', type=int, choices=range(1, 65), default=4)
    parser.add_argument('--skip-tests', action='store_true', help='Compile only; software tests should be run separately.')
    parser.add_argument('--plan', action='store_true', help='Validate inputs and print the build plan without creating files or compiling.')
    args = parser.parse_args()
    try:
        report = plan(args)
        if args.plan:
            print(json.dumps(report, indent=2))
        elif sys.platform != 'darwin':
            raise ValueError('Building these macOS bridge payloads requires macOS and Xcode Command Line Tools')
        else:
            print(build(args, report))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
