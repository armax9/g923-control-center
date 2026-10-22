#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compatibility entry point for the audited public source exporter."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/prepare-publication.py'), run_name='__main__')
