#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Import a user-provided Logitech DLL without loading or redistributing it.

This store is independent of bottles. Bottle installation is a separate explicit
setup action, so reading status cannot change a working game's SDK or runtime.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from pe_inventory import PE, PEError

GHUB_URL = 'https://www.logitechg.com/en-us/software/ghub'
SDK_VERSION = '1.3.12'
SDK_DIRECTORY = '1_3_12'
SDK_FILENAME = 'trueforce_sdk_x64.dll'
SDK_SHA = '2468bdafe64c09ff42ef26f09e49f2096321bb687467323aafb3f0672fb83315'
WINDOWS_SOURCE = r'C:\Program Files\Logi\Trueforce\1_3_12\trueforce_sdk_x64.dll'
MAX_BYTES = 16 * 1024 * 1024


def default_store():
    return Path.home() / 'Library/Application Support/G923 Control Center/SDK'


def managed_path(store=None):
    root = Path(store).expanduser() if store is not None else default_store()
    return root.absolute() / SDK_DIRECTORY / SDK_FILENAME


def _read_checked(source):
    source = Path(source).expanduser()
    if not source.is_file():
        raise ValueError('Choose the original Windows ' + SDK_FILENAME + ' file.')
    with source.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('The selected DLL exceeds the SDK import size limit.')
    try:
        pe = PE(data)
        if pe.machine != 0x8664 or pe.bits != 64:
            raise ValueError('Choose the x64 TRUEFORCE SDK. The x86 DLL is not supported.')
        names = {entry['name'] for entry in pe.exports()}
        if not {'logiTrueForceAvailable', 'logiTrueForceSupported'} <= names:
            raise ValueError('The selected DLL is not a supported Logitech TRUEFORCE SDK.')
    except PEError as error:
        raise ValueError('The selected file is not a valid Windows SDK DLL: ' + str(error)) from error
    if hashlib.sha256(data).hexdigest() != SDK_SHA:
        raise ValueError('This SDK version has not been validated. This release supports the original Logitech TRUEFORCE 1.3.12 x64 DLL; the selected file was not imported.')
    return data


def status(store=None):
    """Read-only, static status of the managed SDK; never invokes Wine or DLLs."""
    target = managed_path(store)
    result = dict(installed=False, path=str(target), version=SDK_VERSION,
                  detail='Import the original Logitech TRUEFORCE 1.3.12 x64 SDK from Windows G HUB.')
    if target.is_symlink():
        result['detail'] = 'The SDK destination is a symbolic link. It was preserved; choose a regular managed SDK location.'
    elif target.exists():
        try:
            _read_checked(target)
            result.update(installed=True, detail='Original Logitech TRUEFORCE 1.3.12 x64 SDK imported. Install native TRUEFORCE support for the selected bottle next.')
        except (OSError, ValueError) as error:
            result['detail'] = 'The existing SDK file was preserved. ' + str(error)
    return result


def import_sdk(source, store=None):
    """Explicit atomic import; existing nonmatching files are never replaced.

    The final link is exclusive: a concurrent import or external writer cannot
    be overwritten between validation and publication of the verified snapshot.
    """
    data = _read_checked(source)
    target = managed_path(store)
    if target.is_symlink():
        raise ValueError('Existing SDK destination is a symbolic link and was preserved.')
    if target.exists():
        if status(store)['installed']:
            return status(store)
        raise ValueError('Existing SDK destination differs from the supported SDK and was preserved.')
    root = target.parent.parent
    if root.is_symlink() or target.parent.is_symlink():
        raise ValueError('The managed SDK directory must not be a symbolic link.')
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.sdk-import-', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # mkstemp creates private user-readable files; do not make SDKs public.
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        try:
            os.link(temporary, target)
        except FileExistsError:
            if not status(store)['installed']:
                raise ValueError('Another file appeared at the SDK destination and was preserved.')
    finally:
        Path(temporary).unlink(missing_ok=True)
    return status(store)


def default_search_roots():
    """Only likely shared folders/Windows volumes; no VM-image mounting/crawl."""
    home = Path.home()
    roots = [home / 'Downloads', home / 'Desktop', Path('/Program Files')]
    volumes = Path('/Volumes')
    if volumes.is_dir():
        try:
            roots.extend(path for path in sorted(volumes.iterdir())[:128]
                         if path.is_dir() and ('windows' in path.name.lower()
                                              or path.name.startswith('[C]')))
        except OSError:
            pass
    return roots


def candidates(roots=None):
    """Find DLLs at bounded G HUB layouts, reporting unsupported versions too.

    A root may be a selected DLL, shared folder, Windows C: volume, Program
    Files, Logi or Trueforce directory. Discovery never imports candidates.
    """
    found = {}
    for value in default_search_roots() if roots is None else roots:
        root = Path(value).expanduser()
        if root.is_file():
            paths = [root] if root.name.casefold() == SDK_FILENAME.casefold() else []
        else:
            bases = [root, root/'Program Files', root/'Program Files (x86)']
            paths = []
            for base in bases:
                for relative in ('Logi/Trueforce', 'Trueforce', '.'):
                    folder = base/relative
                    paths.extend([folder/SDK_FILENAME, folder/SDK_DIRECTORY/SDK_FILENAME])
                    try:
                        if folder.is_dir():
                            # G HUB keeps versioned sibling folders, one level.
                            paths.extend(path/SDK_FILENAME for path in sorted(folder.iterdir())[:128]
                                         if path.is_dir())
                    except OSError:
                        pass
        for path in paths:
            try:
                if not path.is_file():
                    continue
                key = str(path.resolve())
                if key in found:
                    continue
                item = dict(path=key, version=None, supported=False, detail='')
                try:
                    _read_checked(path)
                    item.update(version=SDK_VERSION, supported=True,
                                detail='Validated Logitech TRUEFORCE 1.3.12 x64 SDK.')
                except (OSError, ValueError) as error:
                    item['detail'] = str(error)
                found[key] = item
            except OSError:
                continue
    return [found[key] for key in sorted(found)]


def main(argv=None):
    parser = argparse.ArgumentParser(description='Logitech TRUEFORCE SDK setup. No DLL code is executed.')
    parser.add_argument('action', choices=('status', 'import', 'discover'))
    parser.add_argument('--source', type=Path)
    parser.add_argument('--store', type=Path)
    parser.add_argument('--root', type=Path, action='append')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.action == 'import':
            if args.source is None:
                raise ValueError('Choose the Windows SDK DLL to import.')
            result = import_sdk(args.source, args.store)
        elif args.action == 'discover':
            result = {'candidates': candidates(args.root), 'download_url': GHUB_URL}
        else:
            result = status(args.store)
        print(json.dumps(result, indent=2))
    except (OSError, ValueError) as error:
        if args.json:
            print(json.dumps({'error': str(error)}))
        else:
            parser.exit(2, str(error) + '\n')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
