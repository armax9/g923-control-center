# SPDX-License-Identifier: GPL-3.0-only
"""Prepare a reviewed Wine transport from the user's matching CrossOver build.

Checks are read-only. Installation copies the user's runtime to private app data
and replaces only the reviewed open-source Wine module pair in that copy. It
never changes CrossOver, bottles, games or security settings and never runs Wine.
Bottle activation is a separate reversible native_transport transaction.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from native_transport import _value
from portable_paths import ROOT, digest, runtime_directory
from profile_store import _portable_runtime

PURPOSE = 'g923-isolated-crossover-hid-transport'
MODULES = {'x86_64-unix/winebus.so', 'x86_64-windows/winebus.sys'}
# This metadata also permits read-only verification of previously accepted
# profiles when no redistributable payload has been installed yet.
ACCEPTED_BUILD = {
    'id': 'cx-preview-27.0.0.41069-wine-11.17',
    'product_version': '27.0.0.41069',
    'build_timestamp': '20261006T113703Z',
    'wine_version': '11.17',
    'original_module_hashes': {
        'x86_64-unix/winebus.so': '2826a5f9f3ebab4d011b63bb5afe24025b9e9fb294f82557645eb2bc16ebb21e',
        'x86_64-windows/winebus.sys': '09594bcc90bd55935f5f07a887efaee362ac800b3ba15ca7eb2809eb142ec1ce'},
    'modules': {
        'x86_64-unix/winebus.so': {
            'path': 'cx-preview-27.0.0.41069-wine-11.17/winebus.so',
            'sha256': 'b8d60dce48b6fb768eb50e41950ffbfa99d29fb63e2d03dd764c338438f1453c'},
        'x86_64-windows/winebus.sys': {
            'path': 'cx-preview-27.0.0.41069-wine-11.17/winebus.sys',
            'sha256': 'ecaf49c5ccea05ddad1d626f414ea9f761eb48bdf51e21c1f74512f7cd7146d8'}}}


def default_store():
    return Path.home() / 'Library/Application Support/G923 Control Center/Transports'


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate transport metadata key: ' + key)
        result[key] = value
    return result


def _read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Transport metadata must be a regular file: ' + str(path))
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Transport metadata is too large.')
    return json.loads(path.read_text(), object_pairs_hook=_object)


def _safe_path(value):
    if not isinstance(value, str) or not value or '\0' in value:
        raise ValueError('Invalid transport payload path.')
    result = Path(value)
    if result.is_absolute() or '..' in result.parts:
        raise ValueError('Invalid transport payload path.')
    return result


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Invalid transport SHA-256 fingerprint.')
    return value


def _validate_catalog(document):
    if not isinstance(document, dict) or document.get('version') != 1 or not isinstance(document.get('builds'), list):
        raise ValueError('Unsupported transport catalog.')
    identities, versions = set(), set()
    for build in document['builds']:
        if not isinstance(build, dict) or not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', str(build.get('id', ''))):
            raise ValueError('Invalid transport build identity.')
        for name in ('product_version', 'build_timestamp', 'wine_version'):
            if not isinstance(build.get(name), str) or not build[name] or '\0' in build[name]:
                raise ValueError('Incomplete transport build metadata.')
        version = (build['product_version'], build['build_timestamp'])
        if build['id'] in identities or version in versions:
            raise ValueError('Duplicate transport build.')
        identities.add(build['id']); versions.add(version)
        if not isinstance(build.get('original_module_hashes'), dict) or set(build['original_module_hashes']) != MODULES:
            raise ValueError('A complete original Wine module pair is required.')
        if not isinstance(build.get('modules'), dict) or set(build['modules']) != MODULES:
            raise ValueError('A complete prepared Wine module pair is required.')
        for value in build['original_module_hashes'].values():
            _hash(value)
        for module in build['modules'].values():
            if not isinstance(module, dict):
                raise ValueError('Invalid transport payload metadata.')
            _safe_path(module.get('path')); _hash(module.get('sha256'))
    return document['builds']


def _catalog(payload_root=None):
    roots = [Path(payload_root)] if payload_root is not None else [ROOT/'payloads/winebus', ROOT/'Resources/payloads/winebus']
    if payload_root is None and os.environ.get('G923_PAYLOADS'):
        roots.insert(0, Path(os.environ['G923_PAYLOADS'])/'winebus')
    for root in roots:
        if (root/'catalog.json').exists() or (root/'catalog.json').is_symlink():
            return root.resolve(), _validate_catalog(_read_json(root/'catalog.json'))
    # No payload is considered available from this fallback.
    return None, [ACCEPTED_BUILD]


def _config(runtime):
    text = (runtime/'etc/CrossOver.conf').read_text()
    values = (_value(text, 'CrossOver', 'ProductVersion'), _value(text, 'CrossOver', 'BuildTimestamp'))
    if not all(values):
        raise ValueError('CrossOver runtime build metadata is missing.')
    return dict(product_version=values[0], build_timestamp=values[1])


def _runtime(runner):
    if isinstance(runner, dict):
        runner = runner.get('path') or runner.get('wine')
    if not runner:
        raise ValueError('Select the CrossOver installation used by this bottle.')
    path = Path(runner).expanduser().resolve()
    if path.is_dir() and (path/'Contents/SharedSupport/CrossOver/bin/wine').is_file():
        return path, path/'Contents/SharedSupport/CrossOver'
    if path.is_dir() and (path/'bin/wine').is_file():
        return path, path
    if path.is_file() and path.parent.name == 'bin' and path.name in ('wine', 'wine64'):
        return path, path.parent.parent
    raise ValueError('The selected CrossOver runtime is unavailable.')


def _build(runtime, builds, prepared=False):
    config = _config(runtime)
    matches = [b for b in builds if all(b[k] == config[k] for k in config)]
    if not matches:
        raise ValueError('No compatible transport build for CrossOver ' + config['product_version'] + ' (' + config['build_timestamp'] + ').')
    build = matches[0]
    hashes = {name: digest(runtime/'lib/wine'/name) for name in MODULES}
    expected = {name: item['sha256'] for name, item in build['modules'].items()} if prepared else build['original_module_hashes']
    if hashes != expected:
        raise ValueError(('The prepared Wine transport changed.' if prepared else 'The CrossOver Wine modules differ from the compatible stock build. Nothing was changed.'))
    fingerprint = hashlib.sha256(json.dumps(dict(config, original_module_hashes=build['original_module_hashes']), sort_keys=True).encode()).hexdigest()
    return build, fingerprint


def _prepared(session, builds):
    session = Path(session).expanduser().resolve()
    manifest = _read_json(session/'manifest.json')
    if not isinstance(manifest, dict) or manifest.get('purpose') != PURPOSE:
        raise ValueError('This is not a prepared G923 Wine transport.')
    for field in ('runtime_dir', 'runner_path'):
        if manifest.get(field) is not None and (not isinstance(manifest[field], str) or '\0' in manifest[field] or not Path(manifest[field]).expanduser().is_absolute()):
            raise ValueError('Invalid prepared transport runtime path.')
    runtime = runtime_directory(session, manifest).resolve()
    build, fingerprint = _build(runtime, builds, prepared=True)
    hashes = manifest.get('prepared_module_hashes') or manifest.get('runtime_hashes')
    expected = {name: item['sha256'] for name, item in build['modules'].items()}
    if hashes != expected:
        raise ValueError('The prepared transport manifest differs from the reviewed module pair.')
    return {'state': 'installed', 'installed': True, 'available': True,
            'detail': 'Compatible Wine transport prepared. Bottle activation is checked separately.',
            'transport_dir': str(session), 'runtime_dir': str(runtime), 'build': build['id'],
            'product_version': build['product_version'], 'build_timestamp': build['build_timestamp'],
            'fingerprint': fingerprint, 'module_hashes': hashes}


def _registry(store):
    path = store/'registry.json'
    if not path.exists() and not path.is_symlink():
        return {'version': 1, 'imports': []}
    value = _read_json(path)
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('imports'), list):
        raise ValueError('Invalid transport registry.')
    for entry in value['imports']:
        if not isinstance(entry, dict) or set(entry) != {'session_dir', 'build'} or not isinstance(entry['session_dir'], str) or not Path(entry['session_dir']).is_absolute() or not isinstance(entry['build'], str):
            raise ValueError('Invalid transport registry entry.')
    return value


def _payloads(root, build):
    if root is None:
        raise FileNotFoundError('The compatible transport payload is missing. Install a complete G923 application build.')
    paths = {}
    for name, item in build['modules'].items():
        path = root/_safe_path(item['path'])
        # Symlinks outside the catalog root must not substitute another payload.
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file() or digest(path) != item['sha256']:
            raise ValueError('The bundled Wine transport differs from its catalog: ' + name)
        paths[name] = path
    return paths


def status(runner=None, session=None, store=None, payload_root=None):
    """Read-only preparation status, never a claim that a game loaded this runtime."""
    try:
        root, builds = _catalog(payload_root)
        if session is not None:
            return _prepared(session, builds)
        if runner is None:
            return {'state': 'select_runner', 'installed': False, 'available': True,
                    'detail': 'Choose the CrossOver application used by this bottle to check or install its transport.'}
        path, runtime = _runtime(runner)
        build, fingerprint = _build(runtime, builds)
        store = Path(store).expanduser().resolve() if store is not None else default_store()
        managed = store/fingerprint
        if managed.exists() or managed.is_symlink():
            if managed.is_symlink():
                raise ValueError('An unowned transport directory link was preserved.')
            result = _prepared(managed, builds)
            if result['fingerprint'] != fingerprint:
                raise ValueError('The installed transport belongs to a different CrossOver build.')
            return dict(result, runner=str(path))
        for item in _registry(store)['imports']:
            if item['build'] != build['id']:
                continue
            imported = _prepared(item['session_dir'], builds)
            if imported['fingerprint'] == fingerprint:
                return dict(imported, runner=str(path))
        _payloads(root, build)
        return {'state': 'available', 'installed': False, 'available': True,
                'detail': 'A compatible Wine transport is available to install.', 'runner': str(path),
                'build': build['id'], 'product_version': build['product_version'],
                'build_timestamp': build['build_timestamp'], 'fingerprint': fingerprint}
    except (ValueError, OSError, UnicodeError) as error:
        detail = str(error)
        return {'state': 'unsupported' if detail.startswith('No compatible transport build') else 'invalid',
                'installed': False, 'available': False, 'detail': detail}


def lookup(runner, store=None, payload_root=None):
    """Return a verified prepared directory for the selected runner, or None."""
    result = status(runner=runner, store=store, payload_root=payload_root)
    return Path(result['transport_dir']) if result['installed'] else None


def _write_json(path, value):
    if path.is_symlink():
        raise ValueError('A transport metadata symlink was preserved.')
    fd, temporary = tempfile.mkstemp(prefix='.metadata-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def import_existing(session, store=None, payload_root=None):
    """Explicitly register a verified accepted profile without changing its bytes."""
    _, builds = _catalog(payload_root)
    result = _prepared(session, builds)
    store = Path(store).expanduser().resolve() if store is not None else default_store()
    registry = _registry(store)
    entry = {'session_dir': result['transport_dir'], 'build': result['build']}
    if entry not in registry['imports']:
        registry['imports'].append(entry)
        store.mkdir(parents=True, exist_ok=True)
        _write_json(store/'registry.json', registry)
    return result


def install(runner, store=None, payload_root=None):
    """Atomically prepare a private runtime; caller enables the selected bottle."""
    root, builds = _catalog(payload_root)
    path, runtime = _runtime(runner)
    build, fingerprint = _build(runtime, builds)
    store = Path(store).expanduser().resolve() if store is not None else default_store()
    # Do not recursively clone a runtime into itself or overwrite an ancestor.
    if store == runtime or store.is_relative_to(runtime) or runtime.is_relative_to(store):
        raise ValueError('The transport store must be separate from the CrossOver runtime.')
    current = status(runner, store=store, payload_root=payload_root)
    if current['installed']:
        return current
    if current['state'] != 'available':
        raise ValueError(current['detail'])
    destination = store/fingerprint
    if destination.exists() or destination.is_symlink():
        raise ValueError(current['detail'])
    paths = _payloads(root, build)
    store.mkdir(parents=True, exist_ok=True)
    lock = store/('.install-' + fingerprint + '.lock')
    try:
        lock_stream = lock.open('x')
    except FileExistsError as error:
        raise ValueError('This Wine transport is already being installed.') from error
    temporary = None
    try:
        lock_stream.close()
        temporary = Path(tempfile.mkdtemp(prefix='.prepare-', dir=store))
        _portable_runtime(runtime, temporary/'runtime')
        _build(runtime, builds)  # The source pair must remain unchanged throughout.
        copied, copied_fingerprint = _build(temporary/'runtime', builds)
        if copied_fingerprint != fingerprint or copied['id'] != build['id']:
            raise ValueError('The copied runtime differs from the selected CrossOver build.')
        for name, source in paths.items():
            if digest(source) != build['modules'][name]['sha256']:
                raise ValueError('The bundled Wine transport changed during installation.')
            target = temporary/'runtime/lib/wine'/name
            if target.is_symlink():
                target.unlink()
            shutil.copy2(source, target)
        hashes = {name: digest(temporary/'runtime/lib/wine'/name) for name in MODULES}
        manifest = {'version': 1, 'purpose': PURPOSE, 'prepared': True,
                    'build_id': build['id'], 'source_runtime': str(runtime), 'runner_path': str(path),
                    'source_fingerprint': fingerprint, 'source_product': _config(runtime),
                    'original_hashes': dict(build['original_module_hashes']),
                    'original_module_hashes': dict(build['original_module_hashes']),
                    'runtime_hashes': hashes, 'prepared_module_hashes': hashes,
                    'game_launched': False, 'installed_runtime_modified': False,
                    'bottle_modified': False}
        _write_json(temporary/'manifest.json', manifest)
        _prepared(temporary, builds)
        _build(runtime, builds)
        if destination.exists() or destination.is_symlink():
            raise ValueError('An existing transport directory was preserved.')
        temporary.rename(destination)
        temporary = None
        return dict(_prepared(destination, builds), runner=str(path))
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary)
        lock.unlink(missing_ok=True)


def list_transports(store=None, payload_root=None):
    root, builds = _catalog(payload_root)
    store = Path(store).expanduser().resolve() if store is not None else default_store()
    sessions = {item['session_dir'] for item in _registry(store)['imports']}
    if store.is_dir():
        sessions.update(str(path) for path in store.iterdir() if path.is_dir() and not path.name.startswith('.'))
    return {'version': 1, 'builds': [{'id': b['id'], 'product_version': b['product_version'],
                                    'build_timestamp': b['build_timestamp'], 'wine_version': b['wine_version']}
                                   for b in builds],
            'transports': [dict(status(session=session, payload_root=payload_root), session_dir=session)
                           for session in sorted(sessions)]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['list', 'status', 'install', 'import'])
    parser.add_argument('--runner', type=Path); parser.add_argument('--session', type=Path)
    parser.add_argument('--store', type=Path); parser.add_argument('--payload-root', type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    options = dict(store=args.store, payload_root=args.payload_root)
    try:
        if args.action == 'list':
            result = list_transports(**options)
        elif args.action == 'status':
            result = status(args.runner, session=args.session, **options)
        elif args.action == 'import':
            if not args.session:
                parser.error('--session is required')
            result = import_existing(args.session, **options)
        else:
            if not args.runner:
                parser.error('--runner is required')
            result = install(args.runner, **options)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError) as error:
        print(json.dumps({'state': 'invalid', 'installed': False, 'available': False, 'detail': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
