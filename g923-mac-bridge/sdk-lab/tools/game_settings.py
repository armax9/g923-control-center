# SPDX-License-Identifier: GPL-3.0-only
"""Validated, per-game Control Center settings. Reading never starts a backend.

Only ETS2 exposes externally controlled effects. DiRT's accepted SDK stream is
owned by the game, so its record deliberately has no fake strength/TF switches.
"""
import json
import math
from pathlib import Path

DEFAULT_PATH = Path.home() / 'Library/Application Support/G923 Control Center/game-settings.json'
ETS2 = '227300'
ETS2_DEFAULTS = {'ffbStrength': 100, 'trueForceEnabled': True, 'engineVibration': 10}


def percentage(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError(name + ' must be a finite number between 0 and 100')
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate game settings key: ' + key)
        result[key] = value
    return result


def load_settings(path=None):
    """Missing files use defaults; invalid existing files fail before HID access."""
    path = Path(path) if path is not None else DEFAULT_PATH
    try:
        raw = path.read_text()
    except FileNotFoundError:
        return {ETS2: dict(ETS2_DEFAULTS), '690790': {}}
    try:
        document = json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError) as error:
        raise ValueError('Invalid game settings: ' + str(error)) from error
    if not isinstance(document, dict) or set(document) != {'version', 'games'}:
        raise ValueError('Game settings must contain version and games')
    if type(document['version']) is not int or document['version'] != 1:
        raise ValueError('Unsupported game settings version')
    if not isinstance(document['games'], dict):
        raise ValueError('Game settings games must be an object')
    games = {ETS2: dict(ETS2_DEFAULTS), '690790': {}}
    for appid, values in document['games'].items():
        if not appid.isascii() or not appid.isdigit() or appid.startswith('0'):
            raise ValueError('Game settings require canonical Steam app IDs')
        if not isinstance(values, dict):
            raise ValueError('Game settings for ' + appid + ' must be an object')
        if appid != ETS2:
            if values:
                raise ValueError('External effect settings are not supported for game ' + appid)
            games[appid] = {}
            continue
        if set(values) - set(ETS2_DEFAULTS):
            raise ValueError('Unknown ETS2 effect settings')
        current = dict(ETS2_DEFAULTS)
        for name, value in values.items():
            if name == 'trueForceEnabled':
                if type(value) is not bool:
                    raise ValueError('trueForceEnabled must be a boolean')
            else:
                percentage(value, name)
            current[name] = value
        games[appid] = current
    return games


def for_game(appid, path=None):
    return load_settings(path).get(str(appid), {})
