# SPDX-License-Identifier: GPL-3.0-only
"""Inspect recorded per-game Wine overrides without launching Wine."""
import re
from pathlib import Path


def value(text, key, name):
    section = re.search(r'^\['+re.escape(key)+r'\][^\n]*\n.*?(?=^\[|\Z)',text,re.M|re.S)
    if not section:return None
    match = re.search(r'^"'+re.escape(name)+r'"="((?:\\.|[^"\\])*)"\s*$',section.group(),re.M)
    if not match:return None
    return re.sub(r'\\([\\"])',r'\1',match[1])


def verify(manifest):
    for entry in manifest.get('registry_overrides',[]):
        path=Path(entry['path'])
        if value(path.read_text(),entry['key'],entry['name']) != entry['value']:
            raise ValueError('The game loader override needs repair: '+entry['name'])
