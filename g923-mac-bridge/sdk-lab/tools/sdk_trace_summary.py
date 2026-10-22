#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Summarize cumulative SDK observations without double counting snapshots."""
import argparse
import json
from pathlib import Path


def summarize(lines):
    latest = {}
    invalid = 0
    for line in lines:
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            invalid += 1
            continue
        if event.get('event') != 'sdk_call_summary':
            continue
        key = (event.get('pid'), event.get('name'))
        if key not in latest or event.get('calls', 0) >= latest[key].get('calls', 0):
            latest[key] = event
    rows = list(latest.values())
    tf = [row for row in rows if str(row.get('name', '')).startswith('logiTrueForceSetTorqueTF')]
    kf = [row for row in rows if row.get('name') == 'logiTrueForceSetTorqueKF']
    return dict(api_rows=rows, invalid_lines=invalid,
                tf_call_count=sum(row.get('calls', 0) for row in tf),
                tf_accepted_samples=sum(row.get('samples_total', 0) for row in tf),
                tf_nonzero_sampled_batches=sum(row.get('nonzero_batches', 0) for row in tf),
                kf_call_count=sum(row.get('calls', 0) for row in kf),
                operator_stop_seen=any(row.get('name') == 'operator_stop' for row in rows),
                physical_playback_confirmed=False,
                limitations='Only selected SDK exports resolved by the main executable are observed. '
                            'Nonzero checks sample at most 64 values per batch. Other APIs/modules may be unobserved. '
                            'Successful calls and raw peaks alone do not prove game provenance, physical torque or vibration.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log',type=Path)
    args=parser.parse_args()
    print(json.dumps(summarize(args.log.read_text().splitlines()),indent=2))
