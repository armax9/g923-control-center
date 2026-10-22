#!/usr/bin/env python3
"""Read-only audit of isolated damper logs; never opens a wheel or emits HID."""
import argparse
import json
import math
from pathlib import Path


def expected_output(snapshot, strength):
    """Replay this bridge's normalized damper model, not a hardware calibration."""
    if not snapshot.get('active') or snapshot.get('paused') or snapshot.get('actuators_off'):
        return 0.0
    total = 0.0
    for effect in snapshot.get('effects', []):
        if not effect.get('playing'):
            continue
        if effect['kind'] != 9:
            raise ValueError('Only isolated damper logs are supported')
        offset, positive, negative, pos_sat, neg_sat, dead = effect['params']
        x = max(-10000, min(10000, snapshot['velocity'] * 5000)) - offset
        dead = max(0, dead)
        force = 0.0
        if x > dead:
            cap = min(10000, pos_sat & 0xffffffff)
            force = max(-cap, min(cap, positive * (x - dead) / 10000))
        elif x < -dead:
            cap = min(10000, neg_sat & 0xffffffff)
            force = max(-cap, min(cap, negative * (x + dead) / 10000))
        total += force * effect['gain'] / 10000
    return max(-1, min(1, -total / 10000 * snapshot['gain'] / 10000)) * strength


def audit(events):
    start = next(e for e in events if e.get('event') == 'classic_bridge_start')
    strength, sign = start['strength'], start['motor_sign']
    snapshots = [e for e in events if e.get('event') == 'force_snapshot']
    errors = [abs(expected_output(e, strength) - e['output']) for e in snapshots]
    active = [e for e in snapshots if e.get('active') and any(
        f.get('playing') for f in e.get('effects', []))]
    # A force_snapshot precedes the command in the same tick. Match only the first
    # constant command within 2 ms; never pair a stale snapshot with later motion.
    pending = None
    matched = mismatches = 0
    constants = []
    for event in events:
        if event.get('event') == 'force_snapshot':
            pending = event
        elif event.get('event') == 'classic_hid_output':
            payload = event['payload']
            if payload[:2] != [17, 0]:
                continue
            constants.append(payload[2])
            if pending and 0 <= event['uptime_ms'] - pending['uptime_ms'] <= 2:
                level = pending['output'] * sign
                code = max(0, min(255, math.floor(128 + level * 127 + 0.5)))
                matched += 1
                mismatches += code != payload[2]
            pending = None
    return {
        'snapshots': len(snapshots), 'active_snapshots': len(active),
        'max_model_error': max(errors, default=0),
        'positive_mechanical_power_snapshots': sum(
            e['output'] * e['velocity'] > 1e-9 for e in active),
        'max_abs_output': max((abs(e['output']) for e in active), default=0),
        'constant_command_code_range': [min(constants), max(constants)] if constants else None,
        'same_tick_command_matches': matched, 'same_tick_command_mismatches': mismatches,
        'physical_resistance_confirmed': False,
        'limitations': 'Snapshot sampling is about 10 Hz. Byte matches and passive model do not prove motor torque or calibration.'
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit([json.loads(line) for line in args.log.read_text().splitlines()]), indent=2))
