# SPDX-License-Identifier: GPL-3.0-only
"""Bind one stopped bottle to its reviewed native TRUEFORCE runtime.

CrossOver's own launcher reads CX_ROOT from the bottle environment before it
selects WINELOADER, WINESERVER and WINEDLLPATH. Merely keeping the patched
winebus in a profile does not make an ordinary Steam launch use that transport.
This module changes only that bottle configuration and an owned local symlink.
Planning and checking are read-only. No function starts Wine, a game or HID.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from portable_paths import runtime_directory, digest

ROOT_VALUE = '${WINEPREFIX}/g923-native-runtime'
ENVIRONMENT = {'CX_ROOT': ROOT_VALUE, 'G923_SDK_TRACE': '1',
               'G923_SDK_STOP_FILE': 'Z:${WINEPREFIX}/g923-sdk-stop'}
LINK_NAME = 'g923-native-runtime'
JOURNAL_NAME = 'native-transport.json'
BACKUP_NAME = 'native-transport-before.conf'
MODULES = {'x86_64-unix/winebus.so', 'x86_64-windows/winebus.sys'}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _section(text, name):
    sections = list(re.finditer(r'^\[' + re.escape(name) + r'\][^\n]*\n.*?(?=^\[|\Z)', text, re.M | re.S))
    if len(sections) > 1:
        raise ValueError('Duplicate CrossOver configuration section: ' + name)
    return sections[0] if sections else None


def _value(text, section, name):
    block = _section(text, section)
    if not block:
        return None
    matches = list(re.finditer(r'^\s*"' + re.escape(name) + r'"\s*=\s*"((?:\\.|[^"\\])*)"\s*$', block.group(), re.M))
    if len(matches) > 1:
        raise ValueError('Duplicate CrossOver setting: ' + name)
    return re.sub(r'\\([\\"])', r'\1', matches[0][1]) if matches else None


def _with_root(text):
    newline = '\r\n' if '\r\n' in text else '\n'
    entries = []
    for name, value in ENVIRONMENT.items():
        previous = _value(text, 'EnvironmentVariables', name)
        if previous is not None and previous != value:
            raise ValueError('A different bottle environment setting was preserved: ' + name)
        if previous is None:
            entries.append('"' + name + '" = "' + value + '"' + newline)
    entry = ''.join(entries)
    block = _section(text, 'EnvironmentVariables')
    if block:
        position = block.start() + block.group().index('\n') + 1
        return text[:position] + entry + text[position:]
    return text.rstrip('\r\n') + newline + newline + '[EnvironmentVariables]' + newline + entry


def _read_journal(session):
    path = session / JOURNAL_NAME
    if path.is_symlink():
        raise ValueError('The native transport journal must be a regular file.')
    if not path.exists():
        return None
    document = json.loads(path.read_text())
    if document.get('version') != 1 or document.get('kind') != 'g923-bottle-native-transport':
        raise ValueError('Unrecognized native transport ownership journal.')
    if document.get('backup') != BACKUP_NAME or document.get('state') not in ('prepared', 'applied', 'restored') or document.get('environment') != ENVIRONMENT:
        raise ValueError('Invalid native transport ownership journal.')
    if not isinstance(document.get('previous_environment'), dict) or set(document['previous_environment']) != set(ENVIRONMENT):
        raise ValueError('Incomplete native transport ownership journal.')
    return document


def plan(session, manifest):
    """Validate runtime, bottle build and ownership; return the exact config edit."""
    session = Path(session).resolve()
    bottle = Path(manifest['source_bottle']).expanduser().resolve()
    runtime = runtime_directory(session, manifest).resolve()
    config = bottle / 'cxbottle.conf'
    if config.is_symlink() or not config.is_file():
        raise ValueError('The bottle configuration must be a regular file.')
    before = config.read_bytes()
    text = before.decode('utf-8')
    runtime_text = (runtime / 'etc/CrossOver.conf').read_text()
    version = _value(runtime_text, 'CrossOver', 'ProductVersion')
    timestamp = _value(runtime_text, 'CrossOver', 'BuildTimestamp')
    if not version or not timestamp or version != _value(text, 'Bottle', 'Version') or timestamp != _value(text, 'Bottle', 'Timestamp'):
        raise ValueError('The reviewed native runtime does not match this bottle build. Select a matching prepared transport.')
    hashes = manifest.get('runtime_hashes', {})
    if set(hashes) != MODULES:
        raise ValueError('The reviewed native transport module pair is missing.')
    for relative, value in hashes.items():
        if digest(runtime / 'lib/wine' / relative) != value:
            raise ValueError('The reviewed native transport changed: ' + relative)
    link = bottle / LINK_NAME
    journal = _read_journal(session)
    if journal and (journal.get('bottle') != str(bottle) or journal.get('runtime') != str(runtime) or journal.get('link') != str(link)):
        raise ValueError('The native transport journal belongs to another installation.')
    if link.exists() or link.is_symlink():
        if not link.is_symlink() or link.resolve() != runtime:
            raise ValueError('An existing bottle runtime link was preserved.')
        if not journal:
            raise ValueError('An unowned bottle runtime link was preserved.')
    if not journal and _value(text, 'EnvironmentVariables', 'CX_ROOT') is not None:
        raise ValueError('An unowned bottle runtime override was preserved.')
    after = _with_root(text).encode('utf-8')
    return {'version': 1, 'bottle': str(bottle), 'runtime': str(runtime),
            'config': str(config), 'link': str(link), 'root_value': ROOT_VALUE,
            'before': text, 'after': after.decode('utf-8'),
            'before_sha256': _sha(before), 'after_sha256': _sha(after),
            'change_required': before != after or not link.is_symlink(),
            'product_version': version, 'build_timestamp': timestamp,
            'module_hashes': hashes,
            'environment': ENVIRONMENT,
            'previous_environment': {name: _value(text, 'EnvironmentVariables', name) for name in ENVIRONMENT}}


def check_config(session, manifest):
    """Read-only installation state; this does not establish a live SDK connection."""
    try:
        item = plan(session, manifest)
        journal = _read_journal(Path(session))
        configured = not item['change_required'] and journal is not None and journal['state'] == 'applied'
        return {'configured': configured, 'runtime': item['runtime'],
                'detail': 'Native transport configured for this bottle.' if configured else 'Native transport must be enabled for ordinary CrossOver launches.'}
    except (ValueError, OSError, UnicodeError) as error:
        return {'configured': False, 'detail': str(error)}


def _atomic(path, data, expected=None):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('A symlink was preserved: ' + str(path))
    if expected is not None and path.read_bytes() != expected:
        raise ValueError('The bottle configuration changed during setup.')
    fd, temporary = tempfile.mkstemp(prefix='.g923-transport-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        if path.exists():
            Path(temporary).chmod(path.stat().st_mode & 0o777)
        if expected is not None and path.read_bytes() != expected:
            raise ValueError('The bottle configuration changed during setup.')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _save(path, data):
    _atomic(path, (json.dumps(data, indent=2) + '\n').encode())


def require_stopped():
    names = subprocess.check_output(['/bin/ps', '-axo', 'comm='], text=True)
    for line in names.splitlines():
        name = line.strip().replace('\\','/').rsplit('/',1)[-1].casefold()
        if name in ('wine', 'wine64', 'wine64-preloader', 'wine-preloader', 'steam.exe', 'dirtrally2.exe', 'eurotrucks2.exe') or name.startswith('wineserver'):
            raise ValueError('Close Steam, games and CrossOver before enabling the native transport. Nothing was closed automatically.')


def configure(session, manifest):
    """Explicit, reversible installation. Call only with Steam and games stopped."""
    require_stopped()
    session = Path(session).resolve()
    item = plan(session, manifest)
    if not item['change_required']:
        journal = _read_journal(session)
        if journal and journal['state'] == 'prepared':
            journal['state'] = 'applied'
            _save(session / JOURNAL_NAME, journal)
        return check_config(session, manifest)
    config, link = Path(item['config']), Path(item['link'])
    before, after = item['before'].encode(), item['after'].encode()
    journal = _read_journal(session)
    if journal:
        # An interrupted transaction may be retried only with its original bytes.
        if item['before_sha256'] not in (journal.get('before_sha256'), journal.get('after_sha256')):
            raise ValueError('The bottle changed after native transport setup; inspect it before retrying.')
    else:
        backup = session / BACKUP_NAME
        if backup.exists() or backup.is_symlink():
            raise ValueError('An unowned native transport backup was preserved.')
        with backup.open('xb') as stream:
            stream.write(before)
        journal = {'version': 1, 'kind': 'g923-bottle-native-transport',
                   'bottle': item['bottle'], 'runtime': item['runtime'], 'link': str(link),
                   'before_sha256': item['before_sha256'], 'after_sha256': item['after_sha256'],
                   'backup': BACKUP_NAME, 'environment': dict(ENVIRONMENT),
                   'previous_environment': item['previous_environment'], 'state': 'prepared'}
        _save(session / JOURNAL_NAME, journal)
    created = False
    try:
        if not link.is_symlink():
            link.symlink_to(item['runtime'], target_is_directory=True)
            created = True
        if before != after:
            _atomic(config, after, expected=before)
        journal['state'] = 'applied'
        _save(session / JOURNAL_NAME, journal)
    except Exception:
        if config.read_bytes() == after and before != after:
            _atomic(config, before, expected=after)
        if created and link.is_symlink() and link.resolve() == Path(item['runtime']):
            link.unlink()
        raise
    return check_config(session, manifest)


def restore(session, manifest):
    """Remove only the owned CX_ROOT entry; preserve subsequent unrelated edits."""
    require_stopped()
    session = Path(session).resolve()
    item = plan(session, manifest)
    journal = _read_journal(session)
    if not journal or journal.get('state') != 'applied':
        raise ValueError('No applied native transport transaction was found.')
    backup = session / journal['backup']
    if backup.is_symlink() or digest(backup) != journal['before_sha256']:
        raise ValueError('The native transport backup changed.')
    before = Path(item['config']).read_bytes()
    text = before.decode('utf-8')
    block = _section(text, 'EnvironmentVariables')
    if not block or _value(text, 'EnvironmentVariables', 'CX_ROOT') != ROOT_VALUE:
        raise ValueError('The owned runtime override changed; no rollback was performed.')
    if _sha(before) == journal['after_sha256']:
        after = backup.read_bytes()
    else:
        changed = block.group()
        for name, value in ENVIRONMENT.items():
            if _value(text, 'EnvironmentVariables', name) != value:
                raise ValueError('The owned environment entry changed: ' + name)
            if journal['previous_environment'].get(name) is None:
                changed = re.sub(r'^[^\S\n]*"' + re.escape(name) + r'"\s*=\s*"' + re.escape(value) + r'"[^\S\n]*\n', '', changed, count=1, flags=re.M)
        after = (text[:block.start()] + changed + text[block.end():]).encode()
    _atomic(Path(item['config']), after, expected=before)
    link = Path(item['link'])
    if link.is_symlink() and link.resolve() == Path(item['runtime']):
        link.unlink()
    journal['state'] = 'restored'
    _save(session / JOURNAL_NAME, journal)
    return {'configured': False, 'detail': 'The bottle native transport override was removed.'}


def environment_preflight(wrapper, bottle):
    """Run only CrossOver's Perl launcher and print six selected environment values.

    --ux-app runs a macOS executable directly. --no-update and --no-lock prevent
    bottle setup/lock writes. This never invokes a Wine loader or wineserver.
    """
    names = ['CX_ROOT', 'WINEPREFIX', 'WINELOADER', 'WINESERVER', 'WINEDLLPATH', 'CX_INITIALIZED']
    env = {key: value for key, value in os.environ.items() if not key.startswith(('CX_', 'WINE'))}
    result = {}
    # macOS printenv accepts a single name, unlike several GNU versions.
    for name in names:
        probe = subprocess.run([str(wrapper), '--bottle', str(Path(bottle).resolve()),
                                '--no-gui', '--no-update', '--no-lock', '--ux-app',
                                '/usr/bin/printenv', name], env=env, text=True,
                               capture_output=True, timeout=15)
        if probe.returncode or len(probe.stdout.splitlines()) != 1:
            raise ValueError('The CrossOver launcher environment could not be verified: ' + name)
        result[name] = probe.stdout.rstrip('\n')
    return result
