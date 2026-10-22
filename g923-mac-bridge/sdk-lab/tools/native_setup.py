# SPDX-License-Identifier: GPL-3.0-only
"""Application setup workflow for the original SDK and native Wine transport."""
import json
from pathlib import Path

from profile_store import load_registry
from portable_paths import digest
import sdk_setup
import transport_setup


def profile_for(exe=None,prefix=None,registry=None):
    profiles=[p for p in load_registry(registry)['profiles'] if p['appid']==690790]
    if exe is not None:profiles=[p for p in profiles if Path(p['game_exe']).resolve()==Path(exe).resolve()]
    if prefix is not None:profiles=[p for p in profiles if Path(p['source_bottle']).resolve()==Path(prefix).resolve()]
    if len(profiles)>1:raise ValueError('Choose a specific game installation.')
    return profiles[0] if profiles else None


def sdk_for_bottle(prefix=None):
    managed=sdk_setup.status()
    if managed['installed'] or prefix is None:return managed
    source=Path(prefix)/'drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll'
    if source.is_file() and digest(source)==sdk_setup.SDK_SHA:
        return dict(managed,installed=True,path=str(source),source='bottle',detail='Original SDK 1.3.12 is installed in this bottle.')
    return managed


def status(exe=None,prefix=None,runner=None,registry=None):
    profile=profile_for(exe,prefix,registry)
    session=Path(profile['session_dir']) if profile else None
    transport=transport_setup.status(runner=runner,session=session)
    bottle={'configured':False,'detail':'Install the game integration to enable this bottle.'}
    if session:
        from native_transport import check_config
        bottle=check_config(session,json.loads((session/'manifest.json').read_text()))
    return {'sdk':sdk_for_bottle(prefix),'transport':transport,'bottle':bottle,
            'download_url':sdk_setup.GHUB_URL,'profile_id':profile['id'] if profile else None}


def dependencies(prefix,runner):
    sdk=sdk_for_bottle(prefix)
    if not sdk['installed']:
        raise ValueError('Import the original Logitech TRUEFORCE SDK first. Open SDK instructions in the game setup page.')
    transport=transport_setup.status(runner=runner)
    if not transport['installed']:
        raise ValueError('Install the matching CrossOver transport first using Install transport.')
    return Path(transport['transport_dir']),Path(sdk['path'])
