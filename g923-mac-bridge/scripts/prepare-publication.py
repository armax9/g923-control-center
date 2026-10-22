#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Export a reviewed source-only tree and reproducible ZIP; never install or launch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_NAME = 'G923ControlCenter'
MANIFEST_NAME = 'PUBLIC_SOURCE_MANIFEST.json'
MANIFEST_KIND = 'g923-public-source-only'
MAIN_FILES = ('.gitignore', 'CMakeLists.txt', 'LICENSE', 'NOTICE.md', 'README.md')
MAIN_TREES = ('src', 'tests', 'fixtures', 'patches', 'LICENSES', 'scripts',
              'sdk-lab/src', 'sdk-lab/tests', 'sdk-lab/tools', 'sdk-lab/winmm-chain',
              'vendor/wheelio', 'vendor/trueforce', 'vendor/crossover-ffb',
              'vendor/CrossFFB-reference', 'assets/control-center', 'docs/publication')
MAIN_EXTRA = ('sdk-lab/build.sh', 'sdk-lab/Collect-readonly.command',
              'docs/LOGITECH_SDK_SETUP.md', 'docs/WINE_TRANSPORT_SOURCE.md',
              'docs/SDK_RUNTIME_PROVENANCE.json', 'docs/upstream-lock.json',
              'docs/NATIVE_TRUEFORCE_CATALOG.json')
MESCON_FILES = ('COPYING', 'README.md', 'UPSTREAM.json', 'build.py')
MESCON_TREES = ('src', 'LICENSES')
SKIP_PARTS = frozenset(('.git', '.github', '.build', '.swiftpm', '__pycache__',
                        '.cache', 'cache', 'build', 'dist', 'work', 'private',
                        'logs', 'captures', 'diagnostics', 'node_modules', 'payloads'))
EXCLUDED_FILES = frozenset(('sdk-lab/tools/ets2_capture_session.py',
                            'sdk-lab/tests/test_capture_restore.py',
                            'docs/publication/POST_RU.md'))
SOURCE_SUFFIXES = frozenset(('.py', '.sh', '.command', '.swift', '.c', '.h', '.cpp',
                             '.hpp', '.rs', '.def', '.cmake', '.md', '.txt', '.json',
                             '.jsonl', '.patch', '.icns', '.png'))
SOURCE_NAMES = frozenset(('LICENSE', 'LICENSE.txt', 'COPYING', 'COPYING.LIB',
                          'AUTHORS', 'VERSION', 'CMakeLists.txt'))
REQUIRED_MAIN = ('LICENSE', 'NOTICE.md', 'README.md', 'CMakeLists.txt',
                 'vendor/wheelio/LICENSE.txt', 'vendor/trueforce/COPYING',
                 'vendor/crossover-ffb/LICENSE', 'vendor/crossover-ffb/Package.swift',
                 'vendor/CrossFFB-reference/LICENSE',
                 'vendor/CrossFFB-reference/SOURCE.json', 'docs/upstream-lock.json')
REQUIRED_MESCON = ('COPYING', 'UPSTREAM.json', 'README.md', 'build.py', 'src/main.rs',
                   'src/synth.rs', 'src/control.rs')
# Concatenation keeps these scanner fixtures from matching their own source.
PRIVATE_PATHS = (('/Users/' + 'armax').encode(), ('/Volumes/' + 'armax').encode())
SECRET_PATTERNS = (
    ('private key', re.compile(rb'-----BEGIN (?:(?:RSA|EC|OPENSSH|DSA|ENCRYPTED) )?PRIVATE KEY-----')),
    ('GitHub token', re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b')),
    ('AWS access key', re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')),
    ('Slack token', re.compile(rb'\bxox[baprs]-[A-Za-z0-9-]{20,}\b')),
    ('API secret', re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b')),
)
TOP_LEVEL_GITIGNORE = '''# Generated outputs and local user data
**/build/
**/.build/
**/dist/
**/.cache/
**/__pycache__/
**/work/
**/private/
**/captures/
**/logs/
*.py[cod]
*.log
*.bin
.DS_Store
'''
TOP_LEVEL_NOTICE = '''# Copyright and license notices

G923 Control Center integration sources, scripts and documentation are
Copyright (c) 2026 G923 Mac Bridge contributors and licensed under
GPL-3.0-only; see [LICENSE](LICENSE). Component licenses remain attached to
their source trees and are described in [the detailed notices](g923-mac-bridge/NOTICE.md).

This fork derives from [0xbiel/crossover-ffb](https://github.com/0xbiel/crossover-ffb),
commit `65a9685f85908e01dc3c8ca91f84dc49a1329c0f`. Its MIT copyright grant
and disclaimer are preserved in
[vendor/crossover-ffb/LICENSE](g923-mac-bridge/vendor/crossover-ffb/LICENSE).

- [g923-mac-bridge](g923-mac-bridge/README.md): GPL-3.0-only integration,
  with MIT, GPLv3 and LGPL component notices retained in its vendor trees.
- [mescon-telemetry](mescon-telemetry/README.md): GPL-2.0-only engine
  synthesis, run as a separate process and not linked into the GPLv3 app;
  see [COPYING](mescon-telemetry/COPYING) and [UPSTREAM.json](mescon-telemetry/UPSTREAM.json).
- [Wine transport](g923-mac-bridge/docs/WINE_TRANSPORT_SOURCE.md):
  LGPL-2.1-or-later patches, build tools and corresponding-source packaging.

The Logitech SDK and commercial CrossOver runtime are user-supplied and
are not redistributed here. This project is not affiliated with Logitech
or CodeWeavers.
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_source(root, relative):
    """No symlink in an exported path may redirect a read outside its source."""
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Source symlink is not publishable: ' + relative)
    return path


def accepted_source(relative):
    parts = Path(relative).parts
    if any(part in SKIP_PARTS or part.startswith('.') for part in parts):
        return False
    if relative in EXCLUDED_FILES:
        return False
    path = Path(relative)
    return (path.suffix.lower() in SOURCE_SUFFIXES or path.name in SOURCE_NAMES or
            relative.startswith('vendor/crossover-ffb/scripts/'))


def select_files(root, files, trees):
    selected = set()
    for relative in files:
        path = safe_source(root, relative)
        if path.is_file():
            selected.add(relative)
    for tree in trees:
        directory = safe_source(root, tree)
        if not directory.exists():
            continue
        # Pruning happens before inspection: caches and build outputs never enter
        # the candidate inventory, even if they contain a source-like extension.
        for current, directories, filenames in os.walk(directory, followlinks=False):
            directories[:] = sorted(name for name in directories
                                    if name not in SKIP_PARTS and not name.startswith('.'))
            for name in directories:
                path = Path(current) / name
                if path.is_symlink():
                    raise ValueError('Source symlink is not publishable: ' + str(path.relative_to(root)))
            for name in sorted(filenames):
                relative = str((Path(current) / name).relative_to(root))
                if accepted_source(relative):
                    path = safe_source(root, relative)
                    if not path.is_file():
                        raise ValueError('Source must be a regular file: ' + relative)
                    selected.add(relative)
    return sorted(selected)


def privacy_issues(relative, data):
    issues = []
    if any(marker.lower() in data.lower() for marker in PRIVATE_PATHS):
        issues.append(relative + ': personal machine path')
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(data):
            issues.append(relative + ': possible ' + label)
    # Source extensions alone do not make an executable or shared library safe.
    if data.startswith((b'MZ', b'\x7fELF', b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
                        b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe')):
        issues.append(relative + ': compiled executable/library content')
    return issues


def inventory(root, mescon):
    for directory, required in ((root, REQUIRED_MAIN), (mescon, REQUIRED_MESCON)):
        for relative in required:
            if not safe_source(directory, relative).is_file():
                raise ValueError('Required source/attribution file missing: ' + relative)
    records = []
    issues = []
    for component, directory, files, trees in (
            ('g923-mac-bridge', root, MAIN_FILES + MAIN_EXTRA, MAIN_TREES),
            ('mescon-telemetry', mescon, MESCON_FILES, MESCON_TREES)):
        for relative in select_files(directory, files, trees):
            path = safe_source(directory, relative)
            data = path.read_bytes()
            public_name = component + '/' + relative
            issues.extend(privacy_issues(public_name, data))
            mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
            records.append((public_name, data, mode))
    if issues:
        # Print filenames/reasons only; never print the suspected secret itself.
        raise ValueError('Publication privacy/content audit failed:\n' + '\n'.join(issues))
    return sorted(records)


def check_document_links(staged):
    main = staged / 'g923-mac-bridge'
    docs = [staged / 'README.md', staged / 'NOTICE.md', main / 'README.md']
    docs += sorted((main / 'docs').rglob('*.md'))
    problems = []
    for document in docs:
        for value in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', document.read_text()):
            target = value.split(' "', 1)[0].strip('<>')
            if not target or target.startswith('#') or re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', target):
                continue
            target = target.split('#', 1)[0].split('?', 1)[0]
            resolved = (document.parent / target).resolve()
            if not resolved.is_relative_to(staged.resolve()) or not resolved.exists():
                problems.append(str(document.relative_to(staged)) + ': ' + target)
    if problems:
        raise ValueError('Publication documentation has missing/unsafe links:\n' + '\n'.join(problems))


def landing_readme(source):
    """Use the maintained feature text with links relative to the repository root."""
    def rebase(match):
        opening, target, closing = match.groups()
        angle = target.startswith('<') and target.endswith('>')
        value = target[1:-1] if angle else target
        if (value.startswith(('#', '/', '//')) or
                re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', value)):
            return match.group(0)
        value = 'g923-mac-bridge/' + value
        return opening + ('<' + value + '>' if angle else value) + closing
    return re.sub(r'(!?\[[^\]]*\]\()(<[^>]+>|[^)\s]+)([^)]*\))', rebase, source)


def make_manifest(records, version):
    return {'kind': MANIFEST_KIND, 'version': version, 'artifact': 'source-only',
            'components': {
                'g923-mac-bridge': {'license': 'GPL-3.0-only', 'notices': 'g923-mac-bridge/NOTICE.md'},
                'mescon-telemetry': {'license': 'GPL-2.0-only', 'separate_process': True,
                                     'notices': 'mescon-telemetry/UPSTREAM.json'}},
            'proprietary_dependencies_included': False,
            'files': {name: {'sha256': digest(data), 'bytes': len(data), 'mode': format(mode, '04o')}
                      for name, data, mode in records}}


def owned_stage(path):
    if path.is_symlink() or not path.is_dir() or (path / '.git').exists() or (path / '.git').is_symlink():
        return False
    marker = path / MANIFEST_NAME
    if marker.is_symlink():
        return False
    try:
        return json.loads(marker.read_text()).get('kind') == MANIFEST_KIND
    except (OSError, ValueError):
        return False


def export(root, mescon, output, version='0.6.2'):
    root, mescon, output = (Path(p).resolve() for p in (root, mescon, output))
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,39}', version):
        raise ValueError('Version must be a simple release identifier')
    for source in (root, mescon):
        if source == output or source.is_relative_to(output):
            raise ValueError('Output must not replace or contain a source tree')
        if output.is_relative_to(source) and output.relative_to(source).parts[0] != 'build':
            raise ValueError('Output inside a source tree must be under build/')
    records = inventory(root, mescon)
    readme = next(data for name, data, _ in records if name == 'g923-mac-bridge/README.md')
    license_text = next(data for name, data, _ in records if name == 'g923-mac-bridge/LICENSE')
    records += [('README.md', landing_readme(readme.decode()).encode(), 0o644),
                ('.gitignore', TOP_LEVEL_GITIGNORE.encode(), 0o644),
                ('LICENSE', license_text, 0o644),
                ('NOTICE.md', TOP_LEVEL_NOTICE.encode(), 0o644)]
    records.sort()
    manifest = make_manifest(records, version)
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
    records.append((MANIFEST_NAME, manifest_bytes, 0o644))
    records.sort()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / BUNDLE_NAME
    if destination.exists() and not owned_stage(destination):
        raise ValueError('Existing export folder is not owned by this source exporter')
    archive_name = BUNDLE_NAME + '-' + version + '-source.zip'
    with tempfile.TemporaryDirectory(prefix='.publication-', dir=output) as temporary:
        temporary = Path(temporary)
        staged = temporary / BUNDLE_NAME
        staged.mkdir()
        for name, data, mode in records:
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(mode)
            os.utime(target, (0, 0))
        check_document_links(staged)
        archive = temporary / archive_name
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
            for name, data, mode in records:
                item = zipfile.ZipInfo(BUNDLE_NAME + '/' + name, date_time=(1980, 1, 1, 0, 0, 0))
                item.create_system = 3
                item.external_attr = (stat.S_IFREG | mode) << 16
                item.compress_type = zipfile.ZIP_DEFLATED
                zipped.writestr(item, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        with zipfile.ZipFile(archive) as zipped:
            if zipped.testzip() is not None:
                raise ValueError('Source archive failed its integrity check')
        archive_sha = digest(archive.read_bytes())
        checksum = temporary / (archive_name + '.sha256')
        checksum.write_text(archive_sha + '  ' + archive_name + '\n')
        # Replace only a prior exporter-owned copy; source and unrelated outputs
        # are never removed. The temporary copy passes audits before promotion.
        if destination.exists():
            shutil.rmtree(destination)
        staged.replace(destination)
        archive.replace(output / archive_name)
        checksum.replace(output / checksum.name)
    return {'kind': MANIFEST_KIND, 'version': version, 'files': len(records) - 1,
            'archive': archive_name, 'sha256': archive_sha, 'bytes': (output / archive_name).stat().st_size,
            'stage': str(destination), 'privacy_audit': 'passed', 'document_links': 'passed'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Main integration source root')
    parser.add_argument('--mescon-root', type=Path, help='Separate GPL-2.0-only telemetry source root')
    parser.add_argument('--output-dir', type=Path, help='Only the source stage/archive are written here')
    parser.add_argument('--version', default='0.6.2')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        result = export(root, args.mescon_root or root.parent / 'mescon-telemetry',
                        args.output_dir or root / 'build/publication', args.version)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
