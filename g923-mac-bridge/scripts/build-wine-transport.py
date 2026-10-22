#!/usr/bin/env python3
"""Prepare/build the pinned G923 winebus pair. Never starts Wine or touches HID."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'patches/transport-catalog.json'
SOURCE_COMMIT = '36b6a2cf679fb395f668a917b76537190e212d9c'
ARCHIVE_SHA256 = '8dde1acf3b7b702d911127edae5bad3a4683f6dd8c87e725e0379cb842fb1e0e'
BASE_FILES = {
    'dlls/winebus.sys/bus_iohid.c': '9f9be4e847726f2ce397465f0d5ef9fcd3acdf29a26e75c2b401589ab98132d6',
    'dlls/winebus.sys/main.c': 'c308c4bd404559beb97b8176779b120ab47f63388254acbcfde1575feee6eb97',
}
PATCHES = ('winebus-11.17-g923-trueforce.patch', 'winebus-11.17-g923-change-notices.patch')
CONFIGURE = ('--host=x86_64-apple-darwin', '--enable-win64', '--enable-archs=x86_64',
             '--disable-tests', '--without-x', '--without-freetype', '--without-gnutls', '--without-vulkan')


def digest(path: Path) -> str:
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def run(args: list[str], **kwargs) -> str:
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
    if result.returncode:
        raise ValueError(f'Command failed ({result.returncode}): {shlex.join(args)}\n{result.stdout[-6000:]}')
    return result.stdout.strip()


def validate_source(source: Path | None, archive: Path | None) -> dict:
    """Only the exact upstream tree is accepted; a later version needs review."""
    if archive:
        if digest(archive) != ARCHIVE_SHA256:
            raise ValueError('Upstream source archive checksum mismatch; expected pinned Wine 11.17.')
        with tarfile.open(archive) as tf:
            for rel, expected in BASE_FILES.items():
                item = tf.extractfile('wine-wine-11.17/' + rel)
                if not item or hashlib.sha256(item.read()).hexdigest() != expected:
                    raise ValueError(f'Upstream source mismatch: {rel}')
        return {'kind': 'archive', 'commit': SOURCE_COMMIT, 'sha256': ARCHIVE_SHA256}
    assert source is not None
    if run(['git', '-C', str(source), 'rev-parse', 'HEAD']) != SOURCE_COMMIT:
        raise ValueError('Source revision is not the pinned Wine 11.17 commit.')
    if run(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no']):
        raise ValueError('Source tree has modified tracked files; provide a clean pinned checkout.')
    for rel, expected in BASE_FILES.items():
        if digest(source / rel) != expected:
            raise ValueError(f'Upstream source mismatch: {rel}')
    run(['git', 'apply', '--check', str(ROOT / 'patches' / PATCHES[0])], cwd=source)
    return {'kind': 'git', 'commit': SOURCE_COMMIT}


def extract_source(archive: Path, destination: Path) -> None:
    # Reject links and traversal before extracting. The pinned archive has only
    # regular files/directories; this also makes the parser safe for test data.
    with tarfile.open(archive) as tf:
        members = tf.getmembers()
        for item in members:
            path = PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or not (item.isfile() or item.isdir()):
                raise ValueError('Unsafe source archive member: ' + item.name)
            if not path.parts or path.parts[0] != 'wine-wine-11.17':
                raise ValueError('Unexpected source archive root.')
        for item in members:
            rel = PurePosixPath(item.name).parts[1:]
            if not rel:
                continue
            target = destination.joinpath(*rel)
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = tf.extractfile(item)
                assert stream is not None
                with target.open('wb') as output:
                    shutil.copyfileobj(stream, output)
                target.chmod(item.mode & 0o777)


def materialize(source: Path | None, archive: Path | None, destination: Path) -> None:
    if archive:
        extract_source(archive, destination)
    else:
        assert source is not None
        # A git archive excludes local/ignored files, toolchain binaries and .git.
        data = subprocess.run(['git', '-C', str(source), 'archive', SOURCE_COMMIT], check=True,
                              stdout=subprocess.PIPE).stdout
        with tempfile.NamedTemporaryFile(suffix='.tar') as f:
            f.write(data); f.flush()
            with tarfile.open(f.name) as tf:
                tf.extractall(destination, filter='data')
    for patch in PATCHES:
        run(['git', 'apply', '--check', str(ROOT / 'patches' / patch)], cwd=destination)
        run(['git', 'apply', str(ROOT / 'patches' / patch)], cwd=destination)


def bundle_source(source: Path | None, archive: Path | None, target: Path) -> dict:
    if target.exists():
        raise ValueError('Source bundle output already exists; use a new filename.')
    target.parent.mkdir(parents=True, exist_ok=True)
    if not archive:
        raise ValueError('--source-bundle requires --source-archive so the pinned archive can be included unchanged.')
    # The complete upstream source and our scripts travel together. Original SDK and any
    # commercial runtime are deliberately outside this manifest.
    with tempfile.TemporaryDirectory(prefix='g923-wine-source-') as temp:
        package = Path(temp) / 'g923-wine-transport-source'
        for folder, name in [('patches', p) for p in PATCHES] + [
            ('patches', 'transport-catalog.json'), ('patches', 'README.md'),
            ('scripts', 'build-wine-transport.py'), ('docs', 'WINE_TRANSPORT_SOURCE.md')]:
            dest = package / folder / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / folder / name, dest)
        # Include the original source archive so the same strict build command
        # can reconstruct the tree without trusting a changed git tag.
        upstream = package / 'upstream/wine-11.17.tar.gz'
        upstream.parent.mkdir()
        shutil.copyfile(archive, upstream)
        with tarfile.open(archive) as tf:
            for name in ('COPYING.LIB', 'LICENSE', 'AUTHORS'):
                stream = tf.extractfile('wine-wine-11.17/' + name)
                assert stream is not None
                (package / name).write_bytes(stream.read())
        manifest = {
            'version': 1, 'license': 'LGPL-2.1-or-later', 'source_commit': SOURCE_COMMIT,
            'modified_date': '2026-10-20', 'upstream_archive': 'upstream/wine-11.17.tar.gz',
            'patches': list(PATCHES),
            'notice': 'Modified Wine winebus modules; see patches/README.md and COPYING.LIB.',
            'files': {str(p.relative_to(package)): digest(p) for p in sorted(package.rglob('*')) if p.is_file()},
        }
        (package / 'SOURCE_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
        with tarfile.open(target, 'w:xz', preset=1) as tf:
            tf.add(package, arcname=package.name)
    return {'path': str(target), 'sha256': digest(target), 'bytes': target.stat().st_size}


def plan(args) -> dict:
    output = args.output.resolve()
    cc = str(args.compiler.resolve()) if args.compiler else '/usr/bin/clang'
    cxx = str(args.cxx.resolve()) if args.cxx else str(Path(cc).with_name('clang++'))
    env = {'CC': shlex.join([cc, '-arch', 'x86_64']), 'CXX': shlex.join([cxx, '-arch', 'x86_64'])}
    if args.sdk:
        env['SDKROOT'] = str(args.sdk.resolve())
    if args.mingw_bin:
        env['PATH_PREFIX'] = str(args.mingw_bin.resolve())
    if args.bison:
        env['BISON'] = str(args.bison.resolve())
    return {
        'action': 'build' if args.build else ('source-bundle' if args.source_bundle else 'plan'),
        'source': validate_source(args.source, args.source_archive),
        'output': str(output), 'environment': env,
        'patches': [{'path': 'patches/' + p, 'sha256': digest(ROOT / 'patches' / p)} for p in PATCHES],
        'commands': [[str(output / 'source/configure'), *CONFIGURE],
                     ['make', f'-j{args.jobs}', 'dlls/winebus.sys/all']],
        'module_pair': ['x86_64-unix/winebus.so', 'x86_64-windows/winebus.sys'],
        'runs_wine': False, 'accesses_hid': False,
        'compatibility': 'Review every new Wine/CrossOver build before adding it to the installer catalog.',
    }


def build(args, report: dict) -> None:
    if sys.platform != 'darwin':
        raise ValueError('Building this macOS Unix module requires macOS and Xcode Command Line Tools.')
    if not args.mingw_bin or not (args.mingw_bin / 'x86_64-w64-mingw32-gcc').is_file():
        raise ValueError('--mingw-bin must contain x86_64-w64-mingw32-gcc (llvm-mingw).')
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Build output already exists; use a fresh output directory.')
    output.mkdir(parents=True)
    tree = output / 'source'
    materialize(args.source, args.source_archive, tree)
    build_dir = output / 'build'; build_dir.mkdir()
    env = os.environ.copy()
    env.update({k: v for k, v in report['environment'].items() if k != 'PATH_PREFIX'})
    env['PATH'] = str(args.mingw_bin.resolve()) + os.pathsep + env.get('PATH', '')
    for name, command in zip(('configure', 'make'), report['commands']):
        with (output / (name + '.log')).open('w') as log:
            result = subprocess.run(command, cwd=build_dir, env=env, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise ValueError(f'{name} failed; see {output / (name + ".log")}')
    modules = output / 'modules'
    for rel, src in {
        'x86_64-unix/winebus.so': build_dir / 'dlls/winebus.sys/winebus.so',
        'x86_64-windows/winebus.sys': build_dir / 'dlls/winebus.sys/x86_64-windows/winebus.sys',
    }.items():
        dest = modules / rel; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dest)
        if dest.suffix == '.so':
            run(['codesign', '-s', '-', str(dest)])
    report['built_modules'] = {str(p.relative_to(modules)): digest(p) for p in modules.rglob('*') if p.is_file()}
    report['hardware_tested'] = False
    (output / 'build-manifest.json').write_text(json.dumps(report, indent=2) + '\n')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--source', type=Path, help='Clean git checkout of the pinned upstream commit.')
    inputs.add_argument('--source-archive', type=Path, help='Pinned GitHub Wine 11.17 tar.gz.')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/wine-transport')
    parser.add_argument('--compiler', type=Path, help='macOS clang executable.')
    parser.add_argument('--cxx', type=Path, help='macOS clang++ executable.')
    parser.add_argument('--sdk', type=Path, help='macOS SDK directory; defaults to the active Xcode SDK.')
    parser.add_argument('--mingw-bin', type=Path, help='llvm-mingw bin directory for the PE module.')
    parser.add_argument('--bison', type=Path, help='Modern Bison executable if not available in PATH.')
    parser.add_argument('--jobs', type=int, choices=range(1, 65), default=4)
    parser.add_argument('--build', action='store_true', help='Actually compile. Without this flag only a plan is printed.')
    parser.add_argument('--source-bundle', type=Path, help='Write complete corresponding source .tar.xz (no compilation required).')
    args = parser.parse_args(argv)
    try:
        report = plan(args)
        if args.source_bundle:
            report['source_bundle'] = bundle_source(args.source, args.source_archive, args.source_bundle.resolve())
        if args.build:
            build(args, report)
        print(json.dumps(report, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, tarfile.TarError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
