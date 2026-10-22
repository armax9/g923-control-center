#!/usr/bin/env python3
"""Build a self-contained control center. Installing the app is an explicit option."""
import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

RUNTIME_HELPERS = ('auto_bridge', 'bootstrap', 'discovery', 'ets2', 'ets2_connection',
                   'game_settings', 'game_sandbox', 'installed_play', 'main_steam',
                   'portable_paths', 'profile_store', 'registry_overrides', 'sdk_game',
                   'native_transport', 'native_connection', 'sdk_setup', 'pe_inventory',
                   'native_setup', 'transport_setup', 'ets2_manual')

LIVE_MESCON_SHA256 = '2fe6c5481c6dbf0c4513a077812ac3db07bac34d2d8c647c33beacd496ca7bb5'
TRANSPORT_MODULES = {'x86_64-unix/winebus.so', 'x86_64-windows/winebus.sys'}
REQUIRED_COMPONENTS = {'g923-input', 'G923ClassicLab', 'G923TelemetryLab', 'g923_bridge.dll',
                       'winmm.dll', 'g923_scs_telemetry.dll', 'mescon-synth', 'dinput8.dll',
                       'sdk-dinput8.dll'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_payload_path(root, value):
    """Catalog paths must stay within the prepared release directory."""
    if not isinstance(value, str) or not value or '\0' in value:
        raise ValueError('Invalid Wine transport payload path')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Wine transport payload path escapes its directory')
    source = root / path
    if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root.resolve()):
        raise ValueError('Wine transport payload must be a regular file: ' + value)
    return source


def stream_digest(stream):
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        value.update(block)
    return value.hexdigest()


def archive_path(value, prefix):
    """Tar names are data, never paths to extract or execute."""
    if not isinstance(value, str) or not value or '\0' in value or '\\' in value:
        raise ValueError('Invalid Wine source archive path')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != prefix:
        raise ValueError('Wine source archive path escapes its root: ' + value)
    if str(path) != value.rstrip('/'):
        raise ValueError('Noncanonical Wine source archive path: ' + value)
    return path


def verify_wine_source_bundle(archive, build, project_root=None):
    """Verify complete corresponding source in place, without extraction or execution."""
    if not isinstance(build, dict) or not isinstance(build.get('source'), dict):
        raise ValueError('Wine source catalog must identify its corresponding source')
    source = build.get('source', {})
    for field, length in [('commit', 40), ('archive_sha256', 64), ('patch_sha256', 64)]:
        if not isinstance(source.get(field), str) or not re.fullmatch('[0-9a-f]{' + str(length) + '}', source[field]):
            raise ValueError('Wine source catalog is missing a pinned ' + field)
    patch, notice = source.get('patch'), source.get('notice_patch')
    if any(not isinstance(name, str) or PurePosixPath(name).name != name or not name.endswith('.patch')
           for name in (patch, notice)) or patch == notice:
        raise ValueError('Wine source catalog must identify both source patches')
    if source.get('build_script') != 'scripts/build-wine-transport.py':
        raise ValueError('Wine source catalog must identify its build script')
    if not isinstance(source.get('tag'), str) or not re.fullmatch(r'wine-[0-9.]+', source['tag']):
        raise ValueError('Wine source catalog must identify its upstream tag')
    prefix = 'g923-wine-transport-source'
    try:
        with tarfile.open(archive, 'r:*') as package:
            files, names, total = {}, set(), 0
            for member in package:
                path = archive_path(member.name, prefix)
                if str(path) in names or not (member.isfile() or member.isdir()) or member.issparse():
                    raise ValueError('Duplicate, linked or unsupported Wine source archive member: ' + member.name)
                names.add(str(path))
                total += member.size
                if member.size > 256 * 1024 * 1024 or total > 512 * 1024 * 1024 or len(names) > 1000:
                    raise ValueError('Wine source archive exceeds its source package limits')
                if member.isfile():
                    files[str(PurePosixPath(*path.parts[1:]))] = member
            manifest_name = 'SOURCE_MANIFEST.json'
            if manifest_name not in files or files[manifest_name].size > 128 * 1024:
                raise ValueError('Wine source archive is missing its source manifest')
            manifest = json.load(package.extractfile(files[manifest_name]))
            if not isinstance(manifest, dict) or manifest.get('version') != 1 or manifest.get('license') != 'LGPL-2.1-or-later':
                raise ValueError('Unsupported Wine source manifest')
            if manifest.get('source_commit') != source['commit'] or manifest.get('patches') != [patch, notice]:
                raise ValueError('Wine source manifest does not match the reviewed commit and patches')
            upstream = manifest.get('upstream_archive')
            if not isinstance(upstream, str) or not re.fullmatch(r'upstream/wine-[0-9.]+\.tar\.gz', upstream):
                raise ValueError('Wine source manifest has an invalid upstream archive path')
            required = {'AUTHORS', 'COPYING.LIB', 'LICENSE', 'docs/WINE_TRANSPORT_SOURCE.md',
                        'patches/README.md', 'patches/transport-catalog.json', 'patches/' + patch,
                        'patches/' + notice, source['build_script'], upstream}
            expected = manifest.get('files')
            if not isinstance(expected, dict) or set(expected) != required or set(files) != required | {manifest_name}:
                raise ValueError('Wine source archive has missing or unlisted source files')
            for name, checksum in expected.items():
                if not isinstance(checksum, str) or not re.fullmatch('[0-9a-f]{64}', checksum):
                    raise ValueError('Invalid Wine source manifest checksum: ' + name)
                if stream_digest(package.extractfile(files[name])) != checksum:
                    raise ValueError('Wine source archive checksum mismatch: ' + name)
            if expected[upstream] != source['archive_sha256'] or expected['patches/' + patch] != source['patch_sha256']:
                raise ValueError('Wine source archive differs from the pinned upstream source or patch')
            embedded = json.load(package.extractfile(files['patches/transport-catalog.json']))
            if not isinstance(embedded, dict) or embedded.get('version') != 1 or not isinstance(embedded.get('builds'), list) or build not in embedded['builds']:
                raise ValueError('Wine source archive catalog differs from the reviewed module pair')
            # The pinned upstream archive is complete, and carries the same licence texts.
            upstream_prefix = 'wine-' + source['tag']
            upstream_names, licence_hashes, upstream_total = set(), {}, 0
            with tarfile.open(fileobj=package.extractfile(files[upstream]), mode='r|gz') as original:
                for member in original:
                    path = archive_path(member.name, upstream_prefix)
                    if str(path) in upstream_names or not (member.isfile() or member.isdir()) or member.issparse():
                        raise ValueError('Duplicate, linked or unsupported upstream Wine source member: ' + member.name)
                    upstream_names.add(str(path))
                    upstream_total += member.size
                    if member.size > 256 * 1024 * 1024 or upstream_total > 1024 * 1024 * 1024 or len(upstream_names) > 50000:
                        raise ValueError('Upstream Wine source archive exceeds its source limits')
                    relative = str(PurePosixPath(*path.parts[1:]))
                    if member.isfile() and relative in ('AUTHORS', 'COPYING.LIB', 'LICENSE'):
                        licence_hashes[relative] = stream_digest(original.extractfile(member))
            if any(licence_hashes.get(name) != expected[name] for name in ('AUTHORS', 'COPYING.LIB', 'LICENSE')):
                raise ValueError('Wine source licence texts differ from the pinned upstream source')
            if project_root is not None:
                for name in ('patches/' + patch, 'patches/' + notice, source['build_script']):
                    if digest(Path(project_root) / name) != expected[name]:
                        raise ValueError('Packaged Wine source instructions differ from the verified source: ' + name)
            return manifest
    except (tarfile.TarError, EOFError, OSError) as error:
        raise ValueError('Wine source archive could not be verified: ' + str(error)) from error


def bundle_wine_transport(root, payloads, resources, prepared=None, local_provenance=False):
    prepared = Path(prepared) if prepared is not None else root / 'build/wine-transport-source'
    catalog = json.loads((prepared / 'catalog.json').read_text())
    reviewed = json.loads((root / 'patches/transport-catalog.json').read_text())
    if catalog != reviewed or catalog.get('version') != 1 or not catalog.get('builds'):
        raise ValueError('Prepared Wine transport catalog does not match the reviewed source catalog')
    destination = payloads / 'winebus'
    destination.mkdir()
    copied = set()
    for build in catalog['builds']:
        if set(build.get('modules', {})) != TRANSPORT_MODULES:
            raise ValueError('Both Wine transport modules are required')
        for module in build['modules'].values():
            source = relative_payload_path(prepared, module['path'])
            if digest(source) != module['sha256']:
                raise ValueError('Prepared Wine transport module checksum mismatch: ' + module['path'])
            target = destination / module['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        source_metadata = build.get('source', {})
        archive = relative_payload_path(prepared, source_metadata.get('bundle'))
        source_manifest = verify_wine_source_bundle(archive, build, project_root=root)
        for name in ('COPYING.LIB', 'LICENSE', 'AUTHORS'):
            if digest(relative_payload_path(prepared, 'sources/' + name)) != source_manifest['files'][name]:
                raise ValueError('Packaged Wine licence differs from the verified source: ' + name)
        target = destination / source_metadata['bundle']
        target.parent.mkdir(parents=True, exist_ok=True)
        if str(target) not in copied:
            shutil.copy2(archive, target)
            copied.add(str(target))
        source_metadata['bundle_sha256'] = digest(target)
    # Copy a deliberate list: temporary local logs, SDKs and runtime files can
    # never be included simply because they exist next to a prepared payload.
    (destination / 'sources').mkdir(parents=True, exist_ok=True)
    for name in ('COPYING.LIB', 'LICENSE', 'AUTHORS'):
        source = relative_payload_path(prepared, 'sources/' + name)
        shutil.copy2(source, destination / 'sources' / name)
    (destination / 'catalog.json').write_text(json.dumps(catalog, indent=2) + '\n')
    browsable = resources / 'WineTransportSource'
    for folder, name in [('patches', 'README.md'), ('patches', 'transport-catalog.json'),
                         ('patches', 'winebus-11.17-g923-trueforce.patch'),
                         ('patches', 'winebus-11.17-g923-change-notices.patch'),
                         ('scripts', 'build-wine-transport.py'), ('docs', 'WINE_TRANSPORT_SOURCE.md')]:
        target = browsable / folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / folder / name, target)
    shutil.copy2(root / 'docs/WINE_TRANSPORT_SOURCE.md', browsable / 'README.md')
    for name in ('COPYING.LIB', 'LICENSE', 'AUTHORS'):
        shutil.copy2(destination / 'sources' / name, browsable / name)
    # Finder can open the same archive without storing another 75 MB copy.
    for build in catalog['builds']:
        archive = destination / build['source']['bundle']
        link = browsable / archive.name
        if not link.exists():
            link.symlink_to(os.path.relpath(archive, browsable))
    if local_provenance:
        (browsable / 'LOCAL_BUILD_PROVENANCE.txt').write_text(
            'This local application preserves previously accepted transport binaries.\n'
            'Their debug data may contain original build-directory paths.\n'
            'Use the public source package and reviewed source-built components for publication.\n')
    return catalog


def component_sources(directory):
    """A portable source build is identified by its own manifest, not a developer's binary hash."""
    directory = Path(directory)
    manifest = directory / 'manifest.json'
    if not manifest.is_file() or manifest.is_symlink():
        raise RuntimeError('Build the source components first with scripts/build-release-components.py, or select --payloads with that build output.')
    record = json.loads(manifest.read_text())
    if record.get('version') != 1 or set(record.get('files', {})) != REQUIRED_COMPONENTS:
        raise ValueError('A complete source-built component manifest is required.')
    sources = {}
    for name, item in record['files'].items():
        path = relative_payload_path(directory, item['path'])
        if digest(path) != item.get('sha256'):
            raise ValueError('Source-built component checksum mismatch: ' + name)
        sources[name] = path
    return sources


def public_binary(path, pe_strip=None):
    magic = path.read_bytes()[:4]
    if magic[:2] == b'MZ':
        if pe_strip is None: raise ValueError('Public PE payloads require --llvm-strip.')
        subprocess.run([str(pe_strip), '--strip-debug', str(path)], check=True)
        return
    if magic != b'\xcf\xfa\xed\xfe':
        return
    subprocess.run(['/usr/bin/strip', '-S', '-x', str(path)], check=True)
    subprocess.run(['codesign', '--force', '--sign', '-', str(path)], check=True)


def audit_public_app(app):
    for path in app.rglob('*'):
        if path.is_symlink():
            if os.path.isabs(os.readlink(path)) or not path.resolve().is_relative_to(app.resolve()):
                raise ValueError('Public bundle symlink escapes the app')
            continue
        if not path.is_file(): continue
        data = path.read_bytes()
        if b'/Users/' in data or b'/Volumes/' in data:
            raise ValueError('Personal build path in public bundle: ' + str(path.relative_to(app)))
        if hashlib.sha256(data).hexdigest() == '2468bdafe64c09ff42ef26f09e49f2096321bb687467323aafb3f0672fb83315':
            raise ValueError('Original Logitech SDK must not be redistributed')


def package(root, output, install=None, component_root=None, transport_root=None, accepted_local=False, public_release=False, pe_strip=None):
    if accepted_local and component_root is not None:
        raise ValueError('Choose source-built payloads or --accepted-local, not both.')
    if public_release and accepted_local:
        raise ValueError("Public releases require source-built components.")
    sources = None if accepted_local else component_sources(component_root or root / 'build/public-components')
    live_synth = root.parent / 'mescon-telemetry/build/live-engine-candidate/mescon-synth'
    if accepted_local and (not live_synth.is_file() or digest(live_synth) != LIVE_MESCON_SHA256):
        raise RuntimeError('The reviewed local live engine-vibration synthesizer is missing or changed.')
    environment = os.environ.copy()
    cache = output / 'module-cache'
    environment.setdefault('CLANG_MODULE_CACHE_PATH', str(cache))
    environment.setdefault('SWIFT_MODULECACHE_PATH', str(cache))
    swift = ['swift', 'build', '--disable-sandbox', '--package-path', str(root / 'vendor/crossover-ffb'),
             '--scratch-path', str(output / 'swift')]
    for product in ('CrossoverFFBApp', 'G923ClassicLab'):
        subprocess.run(swift + ['--product', product], check=True, env=environment)
    binary = Path(subprocess.check_output(swift + ['--show-bin-path'], text=True, env=environment).strip())
    app = output / 'G923 Control Center.app'
    if app.exists():
        shutil.rmtree(app)
    mac = app / 'Contents/MacOS'
    resources = app / 'Contents/Resources'
    tools = resources / 'BridgeTools'
    mac.mkdir(parents=True)
    resources.mkdir(parents=True)
    shutil.copy2(binary / 'CrossoverFFBApp', mac / 'CrossoverFFBApp')
    if public_release: public_binary(mac / 'CrossoverFFBApp', pe_strip)
    shutil.copy2(root / 'assets/control-center/AppIcon.icns', resources / 'AppIcon.icns')
    # Python sources are standard-library-only. No private profiles, registries or SDK binaries.
    helpers = tools / 'sdk-lab/tools'
    helpers.mkdir(parents=True)
    for name in RUNTIME_HELPERS:
        helper = root / 'sdk-lab/tools' / (name + '.py')
        shutil.copy2(helper, helpers / helper.name)
    licenses = resources / 'Licenses'
    licenses.mkdir()
    for source, name in [(root / 'vendor/crossover-ffb/LICENSE', 'crossover-ffb.txt'),
                         (root / 'LICENSE', 'G923-bridge.txt'),
                         (root.parent / 'mescon-telemetry/COPYING', 'mescon-telemetry.txt'),
                         (root.parent / 'mescon-telemetry/LICENSES/Rust-MIT.txt', 'Rust-MIT.txt'),
                         (root / 'vendor/wheelio/LICENSE.txt', 'Wheelio.txt'),
                         (root / 'vendor/trueforce/COPYING', 'libtrueforce.txt'),
                         (root / 'vendor/CrossFFB-reference/LICENSE', 'CrossFFB.txt')]:
        if source.is_file():
            shutil.copy2(source, licenses / name)
    for source in (root / 'LICENSES').glob('*'):
        if source.is_file():
            shutil.copy2(source, licenses / source.name)
    if (root / 'NOTICE.md').is_file():
        shutil.copy2(root / 'NOTICE.md', licenses / 'NOTICE.md')
    upstream = root.parent / 'mescon-telemetry/UPSTREAM.json'
    if upstream.is_file():
        shutil.copy2(upstream, licenses / 'mescon-UPSTREAM.json')
    payloads = tools / 'payloads'
    payloads.mkdir()
    if accepted_local:
        sources = {
            'g923-input': root / 'build/g923-input',
            'G923ClassicLab': binary / 'G923ClassicLab',
            'G923TelemetryLab': binary / 'G923ClassicLab',
            'g923_bridge.dll': root / 'build/ets2-force-unknown/g923_bridge.dll',
            'winmm.dll': root / 'build/winmm-chain/winmm.dll',
            'g923_scs_telemetry.dll': root.parent / 'mescon-telemetry/build/logi_tf_scs.dll',
            'mescon-synth': live_synth,
            'dinput8.dll': root / 'build/crossover-base/dinput8.dll',
        }
        # An existing accepted installation is a source of our own release components,
        # never of SDK, Wine runtime, registry or game files. Verify before using it.
        accepted = root.parent / 'G923 ETS2'
        accepted_manifest = accepted / 'manifest.json'
        if accepted_manifest.is_file():
            accepted_record = json.loads(accepted_manifest.read_text())
            for name in ('G923TelemetryLab',):
                expected = accepted_record.get('backend_hashes', {}).get(name)
                source = accepted / name
                if expected and source.is_file() and digest(source) == expected:
                    sources[name] = source
        native = root.parent / 'G923 Installation'
        if (native / 'manifest.json').is_file():
            record = json.loads((native / 'manifest.json').read_text())
            source = native / 'sdk-dinput8.dll'
            if source.is_file() and digest(source) == record.get('game_dll_sha'):
                sources['sdk-dinput8.dll'] = source
        if set(sources) != REQUIRED_COMPONENTS:
            raise RuntimeError('The local accepted native game bridge is missing. Use a complete source build instead.')
    manifest = {'version': 1, 'files': {}}
    for name, source in sources.items():
        if not source.is_file():
            raise RuntimeError('Required release payload is missing: ' + name + '. Build the bridge components first.')
        target = payloads / name
        shutil.copy2(source, target)
        if public_release: public_binary(target, pe_strip)
        manifest['files'][name] = {'path': name, 'sha256': digest(target)}
    (payloads / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    bundle_wine_transport(root, payloads, resources, prepared=transport_root, local_provenance=accepted_local)
    shutil.copy2(payloads / 'dinput8.dll', resources / 'dinput8.dll')
    info = dict(CFBundleExecutable='CrossoverFFBApp', CFBundleIdentifier='local.g923.controlcenter',
                CFBundleName='G923 Control Center', CFBundleIconFile='AppIcon', CFBundleDevelopmentRegion='en',
                CFBundlePackageType='APPL', CFBundleShortVersionString='0.6.2', CFBundleVersion='10' if public_release else '9',
                LSMinimumSystemVersion='27.0' if public_release else '13.0', LSUIElement=True,
                NSInputMonitoringUsageDescription='Read Logitech wheel input and status.')
    with (app / 'Contents/Info.plist').open('wb') as handle:
        plistlib.dump(info, handle)
    # Generated Finder metadata is not part of a signed bundle. No quarantine or
    # system security attributes are changed.
    for attribute in ('com.apple.FinderInfo', 'com.apple.ResourceFork'):
        subprocess.run(['xattr', '-r', '-d', attribute, str(app)], capture_output=True)
    if public_release: audit_public_app(app)
    # The app's outer signature seals its manifest-verified resources.
    subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True)
    subprocess.run(['codesign', '--verify', '--strict', str(app)], check=True)
    if install is not None:
        installed = install.expanduser().absolute()
        if installed.exists():
            with (installed / 'Contents/Info.plist').open('rb') as handle:
                existing = plistlib.load(handle)
            if existing.get('CFBundleIdentifier') != info['CFBundleIdentifier']:
                raise ValueError('Destination belongs to another application')
            shutil.rmtree(installed)
        installed.parent.mkdir(parents=True, exist_ok=True)
        # Copy bytes, not file-provider metadata that can invalidate code signatures.
        shutil.copytree(app, installed, copy_function=shutil.copyfile, symlinks=True)
        for source in app.rglob('*'):
            if source.is_file() and not source.is_symlink():
                (installed / source.relative_to(app)).chmod(source.stat().st_mode & 0o777)
        subprocess.run(['codesign', '--verify', '--strict', str(installed)], check=True)
        return installed
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--install', type=Path, help='Explicit destination .app; omitting this only creates a build artifact')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--payloads', type=Path, help='Manifest-verified source build; defaults to build/public-components')
    group.add_argument('--accepted-local', action='store_true', help='Explicit recovery build using local accepted session components; not a public release')
    parser.add_argument('--wine-transport', type=Path, help='Reviewed Wine catalog, module pair and complete source package')
    parser.add_argument('--public-release', action='store_true', help='Strip debug information, sign bundled tools and audit public binary contents')
    parser.add_argument('--llvm-strip', type=Path, help='LLVM strip for public Windows payload debug data')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = (args.output or root / 'build/control-center').resolve()
    output.mkdir(parents=True, exist_ok=True)
    print(package(root, output, args.install, component_root=args.payloads, transport_root=args.wine_transport, accepted_local=args.accepted_local, public_release=args.public_release, pe_strip=args.llvm_strip))


if __name__ == '__main__':
    main()
