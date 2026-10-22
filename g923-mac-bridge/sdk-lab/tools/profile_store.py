# SPDX-License-Identifier: GPL-3.0-only
"""Portable installation registry. Imports and reads never change installations.

Profiles describe actual installations, not a guessed bottle called Steam. SDK
profiles keep their reviewed private runtime inside their session directory.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

PROFILE_VERSION = 1
SUPPORTED = {690790: ('DiRT Rally 2.0', 'G923 Installation'),
             227300: ('Euro Truck Simulator 2', 'G923 ETS2')}


def default_profiles_dir():
    return Path.home() / 'Library/Application Support/G923 Control Center/Profiles'


def default_registry_path():
    return default_profiles_dir() / 'registry.json'


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate profile registry key: ' + key)
        result[key] = value
    return result


def _absolute(value, field, nullable=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value or '\0' in value or not Path(value).is_absolute():
        raise ValueError('Profile ' + field + ' must be an absolute path')
    return value


def validate(document):
    if not isinstance(document, dict) or set(document) != {'version', 'profiles'}:
        raise ValueError('Profile registry must contain version and profiles')
    if type(document['version']) is not int or document['version'] != PROFILE_VERSION:
        raise ValueError('Unsupported profile registry version')
    if not isinstance(document['profiles'], list):
        raise ValueError('Profile registry profiles must be a list')
    ids, sessions = set(), set()
    fields = {'id', 'appid', 'name', 'game_exe', 'source_bottle', 'runner_path', 'session_dir'}
    for profile in document['profiles']:
        if not isinstance(profile, dict) or set(profile) != fields:
            raise ValueError('Profile fields are incomplete or unknown')
        if type(profile['appid']) is not int or profile['appid'] <= 0:
            raise ValueError('Profile appid must be a positive integer')
        if not isinstance(profile['id'], str) or not profile['id'] or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in profile['id']):
            raise ValueError('Profile id must be a safe identifier')
        if not isinstance(profile['name'], str) or not profile['name']:
            raise ValueError('Profile name is required')
        for key in ('game_exe', 'source_bottle', 'session_dir'):
            _absolute(profile[key], key)
        _absolute(profile['runner_path'], 'runner_path', nullable=True)
        if profile['id'] in ids or profile['session_dir'] in sessions:
            raise ValueError('Duplicate profile identity or session directory')
        ids.add(profile['id']); sessions.add(profile['session_dir'])
    return document


def load_registry(path=None):
    path = Path(path) if path is not None else default_registry_path()
    try:
        document = json.loads(path.read_text(), object_pairs_hook=_object)
    except FileNotFoundError:
        return {'version': PROFILE_VERSION, 'profiles': []}
    except (ValueError, UnicodeError) as error:
        raise ValueError('Invalid profile registry: ' + str(error)) from error
    return validate(document)


def save_registry(document, path=None):
    """Explicit atomic write. A failed validation leaves the previous file intact."""
    validate(document)
    path = Path(path) if path is not None else default_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.registry-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(document, stream, indent=2); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return document


def select_profile(appid, registry=None, profile_id=None, path=None):
    profiles = (load_registry(path) if registry is None else validate(registry))['profiles']
    matches = [p for p in profiles if p['appid'] == appid and (profile_id is None or p['id'] == profile_id)]
    if len(matches) != 1:
        raise ValueError(('No prepared profile for ' if not matches else 'Ambiguous prepared profiles for ') + str(appid))
    return matches[0]


def legacy_session(appid, project_root):
    return Path(project_root).parent / SUPPORTED[appid][1]


def manifest_path(session):
    return Path(session) / 'manifest.json'


def profile_from_manifest(session, appid, source_bottle=None, runner_path=None, profile_id=None):
    """Build a record from real manifest paths; callers supply missing old metadata."""
    session = Path(session).resolve()
    manifest = json.loads(manifest_path(session).read_text())
    bottle = manifest.get('source_bottle') or source_bottle
    if bottle is None:
        raise ValueError('Source bottle is missing from legacy profile ' + str(session))
    bottle = Path(bottle).resolve()
    private_runner = session / 'runtime/bin/wine'
    runner = manifest.get('runner_path') or runner_path
    if appid == 690790 and private_runner.is_file():
        runner = private_runner
    identity = hashlib.sha256((str(bottle) + '\0' + manifest['game_exe']).encode()).hexdigest()[:12]
    profile = {'id': profile_id or str(appid) + '-' + identity, 'appid': appid,
               'name': SUPPORTED.get(appid, (str(appid),))[0],
               'game_exe': str(Path(manifest['game_exe']).resolve()),
               'source_bottle': str(bottle), 'runner_path': str(Path(runner).resolve()) if runner else None,
               'session_dir': str(session)}
    validate({'version': PROFILE_VERSION, 'profiles': [profile]})
    return profile


def _portable_runtime(source, destination):
    """Preserve reviewed runtime bytes while removing source-checkout symlinks."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    shutil.copytree(source, destination, symlinks=True)
    for link in list(destination.rglob('*')):
        if not link.is_symlink():
            continue
        target = link.resolve(strict=True)
        try:
            target.relative_to(destination)
            continue
        except ValueError:
            pass
        local = None
        try:
            local = destination / target.relative_to(source)
        except ValueError:
            # Reviewed runtime links may point into its parent CrossOver app.
            # Reuse an identical copied library rather than retain the app path.
            marker = '/Contents/SharedSupport/CrossOver/'
            if marker in str(target):
                candidate = destination / str(target).split(marker, 1)[1]
                if candidate.is_file() and target.is_file() and hashlib.sha256(candidate.read_bytes()).digest() == hashlib.sha256(target.read_bytes()).digest():
                    local = candidate
        link.unlink()
        if local is not None and local.exists():
            link.symlink_to(os.path.relpath(local, link.parent), target_is_directory=local.is_dir())
        elif target.is_dir():
            shutil.copytree(target, link, symlinks=False)
        else:
            shutil.copy2(target, link)


def migrate_legacy(project_root, registry_path=None, source_bottle=None, runner_path=None):
    """Explicit bootstrap migration of owned sessions; never modifies bottle/game files.

    Old sources stay available for rollback. Only components needed by the bridge
    are copied; runtime bytes are preserved rather than replaced by stock Wine.
    """
    registry_path = Path(registry_path) if registry_path else default_registry_path()
    document = load_registry(registry_path)
    legacy = [(appid, legacy_session(appid, project_root)) for appid in SUPPORTED]
    # Old ETS2 manifests did not record a bottle. A unique accepted SDK session is
    # evidence of its associated bottle; never infer a bottle from its display name.
    sdk_manifest = legacy_session(690790, project_root) / 'manifest.json'
    if source_bottle is None and sdk_manifest.is_file():
        source_bottle = json.loads(sdk_manifest.read_text()).get('source_bottle')
    for appid, source in legacy:
        if not manifest_path(source).is_file():
            continue
        record = profile_from_manifest(source, appid, source_bottle, runner_path)
        if any(p['id'] == record['id'] for p in document['profiles']):
            continue
        destination = registry_path.parent / record['id']
        if destination.exists():
            raise ValueError('Unregistered profile directory preserved: ' + str(destination))
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix='.migrate-', dir=registry_path.parent))
        try:
            manifest = json.loads(manifest_path(source).read_text())
            names = {'manifest.json'}
            if appid == 690790:
                names.update({'runtime', 'private', 'sdk-dinput8.dll', 'accepted-dinput8.dll',
                              'system-dinput8-before.dll', 'system-before-install.reg', 'INSTALLATION.json'})
            else:
                names.update(manifest.get('backend_hashes', {}))
                names.update({'g923_bridge.dll', 'winmm.dll', 'logi_tf_scs.dll', 'mescon-synth',
                              'G923TelemetryLab', 'DLAA-dinput8-backup.dll', 'winmm-before-manual.dll'})
            for name in names:
                relative = Path(name)
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Unsafe component path in legacy manifest')
                old, new = source / name, staging / name
                if not old.exists():
                    continue
                new.parent.mkdir(parents=True, exist_ok=True)
                if name == 'runtime':
                    _portable_runtime(old, new)
                elif old.is_dir():
                    shutil.copytree(old, new, symlinks=True)
                else:
                    shutil.copy2(old, new)
            if appid == 690790:
                from portable_paths import payload
                shutil.copy2(payload('g923-input', source), staging / 'g923-input')
                manifest.setdefault('backend_hashes',{})['g923-input']=hashlib.sha256((staging/'g923-input').read_bytes()).hexdigest()
            manifest.update(source_bottle=record['source_bottle'], runner_path=record['runner_path'])
            # A private SDK runner is copied with its session, so rebase its pointer.
            if appid == 690790 and (staging / 'runtime/bin/wine').is_file():
                manifest['runner_path'] = str(destination / 'runtime/bin/wine')
            manifest['installation_directory'] = str(destination)
            (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            staging.rename(destination)
            record = profile_from_manifest(destination, appid, source_bottle, runner_path)
            document['profiles'].append(record)
            save_registry(document, registry_path)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return document


def register(profile, registry_path=None):
    """Explicitly add/update one prepared profile without touching its game."""
    validate({'version': PROFILE_VERSION, 'profiles': [profile]})
    document = load_registry(registry_path)
    previous = next((p for p in document['profiles'] if p['id'] == profile['id']), None)
    if previous and (previous['appid'] != profile['appid'] or previous['game_exe'] != profile['game_exe']):
        raise ValueError('Profile identity already belongs to a different game')
    document['profiles'] = [p for p in document['profiles'] if p['id'] != profile['id']] + [profile]
    return save_registry(document, registry_path)
