#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""User-armed game detection. Never launches Steam or a game."""
import argparse, hashlib, json, queue, signal, subprocess, sys, threading, time
from pathlib import Path
from game_settings import load_settings, percentage, ETS2_DEFAULTS
from profile_store import load_registry, default_registry_path, select_profile, legacy_session
ROOT = Path(__file__).resolve().parents[2]
PROFILES = {690790: ('DiRT Rally 2.0', 'dirtrally2.exe', 'G923 Installation'),
            227300: ('Euro Truck Simulator 2', 'eurotrucks2.exe', 'G923 ETS2')}

def detect(text):
    names = {line.strip().replace('\\', '/').rsplit('/', 1)[-1].lower() for line in text.splitlines()}
    return [appid for appid, (_, exe, _) in PROFILES.items() if exe in names]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def prepared_profile(appid, registry=None, profile_id=None):
    document = load_registry(registry)
    if document['profiles'] or registry is not None or default_registry_path().exists():
        return select_profile(appid, document, profile_id=profile_id)
    return None


def components(appid, profile=None):
    profile = prepared_profile(appid) if profile is None else profile
    session = Path(profile['session_dir']) if profile else legacy_session(appid, ROOT)
    m = json.loads((session / 'manifest.json').read_text())
    game = Path(m['game_exe'])
    if profile and game.resolve() != Path(profile['game_exe']).resolve():
        raise ValueError('Registry game path differs from the prepared manifest')
    if profile and Path(m['source_bottle']).resolve() != Path(profile['source_bottle']).resolve():
        raise ValueError('Registry bottle path differs from the prepared manifest')
    from registry_overrides import verify
    verify(m)
    if appid == 227300:
        original = game.parent / 'dinput8.dll'
        original_hash = digest(original) if original.is_file() else None
        if 'preserved_dlaa_sha' not in m or original_hash != m['preserved_dlaa_sha']:
            raise ValueError('Original dinput8 changed; inspection required')
        from ets2 import component_path
        entries = [(component_path(game.parent, name), expected,
                    session / ('logi_tf_scs.dll' if name == 'plugins/logi_tf_scs.dll' else name))
                   for name, expected in m['installed_files'].items()]
        entries += [(component_path(session, name), expected, None) for name, expected in m['backend_hashes'].items()]
    else:
        prefix = Path(m['source_bottle'])
        sdk = Path(m.get('sdk_target') or prefix / 'drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll')
        entries = [(game, m['game_sha'], None),
                   (game.parent / 'dinput8.dll', m['game_dll_sha'], session / 'sdk-dinput8.dll'),
                   (game.parent / 'steam_api64.dll', m['steam_api_sha'], None),
                   (prefix / 'drive_c/windows/system32/dinput8.dll', m['private_system_dinput_sha'], None),
                   (sdk, m['sdk_sha'], session / 'private/trueforce_sdk_x64.dll')]
        from portable_paths import runtime_directory
        runtime = runtime_directory(session, m)
        entries += [(runtime / 'lib/wine' / name, value, None) for name, value in m['runtime_hashes'].items()]
        entries += [(session / name, value, None) for name,value in m.get('backend_hashes',{}).items()]
    return entries

def installation(appid, patch=False, profile=None):
    entries = components(appid) if profile is None else components(appid, profile=profile)
    missing = []
    for target, expected, source in entries:
        if target.exists():
            if digest(target) != expected:
                raise ValueError('Changed file preserved: ' + str(target))
        else:
            if source is None or not source.is_file() or digest(source) != expected:
                raise ValueError('Trusted component unavailable: ' + str(target))
            missing.append((target, source))
    if patch:
        # Preflight all files before writing; exclusive creation never replaces mods.
        for target, source in missing:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as out:
                out.write(source.read_bytes())
    return 'installed' if patch or not missing else 'patch'

def states(registry=None):
    result = {}
    for appid in PROFILES:
        try:
            profile = prepared_profile(appid, registry)
            result[str(appid)] = {'state': installation(appid, profile=profile), 'profileId': profile['id'] if profile else None}
        except Exception as error: result[str(appid)] = {'state': 'attention', 'detail': str(error)}
    return result

def child_command(appid, engine_vibration=None, settings=None, profile=None, settings_file=None):
    if appid == 227300:
        values = dict(ETS2_DEFAULTS)
        values.update(settings or {})
        if engine_vibration is not None: values['engineVibration'] = percentage(engine_vibration, 'Engine vibration')
        args = [sys.executable, '-u', str(ROOT / 'sdk-lab/tools/ets2.py'), 'start', '--manual', '--user-ready',
                '--ffb-strength', str(values['ffbStrength'])]
        if profile:args += ['--installation', profile['session_dir']]
        if settings_file is not None:
            # Keep the accepted combined transport open; engine gain can become
            # zero/live again without resetting its independent game FFB stream.
            args += ['--settings-file', str(settings_file), '--engine-emulation']
        else:
            args += ['--engine-emulation' if values['trueForceEnabled'] else '--classic-only']
        return args + ['--engine-vibration', str(values['engineVibration'])]
    return [sys.executable, '-u', str(ROOT / 'sdk-lab/tools/installed_play.py'), '--installation',
            profile['session_dir'] if profile else str(legacy_session(appid, ROOT)), '--manual', '--user-ready']

def stop_child(child):
    if child and child.poll() is None:
        child.send_signal(signal.SIGINT)
        # Let the motor owner's finally block finish before any replacement starts.
        child.wait()

def forward_output(child, output):
    """Keep backend diagnostics visible without blocking game detection or stop."""
    for line in child.stdout:
        output.put(line.rstrip('\n'))


def connection_line(line, state):
    if line.startswith('BRIDGE_LISTENING:'):
        state['backendReady'] = True
    if line.startswith('ETS2_STATUS:'):
        for entry in line.split(':', 1)[1].split(';'):
            key, _, value = entry.strip().partition('=')
            if key == 'input_ffb' and value in ('connected', 'waiting'): state['inputFfb'] = value
            if key == 'telemetry' and value in ('live', 'waiting'): state['telemetry'] = value


def native_status(profile):
    from native_connection import live_status
    session=Path(profile['session_dir'])
    return live_status(session,json.loads((session/'manifest.json').read_text()))


def running_profiles(text, document):
    """Match concrete paths first; ambiguous exe names never select a bottle."""
    lines = [line.strip().replace('\\', '/') for line in text.splitlines() if line.strip()]
    found = []
    for appid in detect(text):
        candidates = [p for p in document['profiles'] if p['appid'] == appid]
        exact = []
        for profile in candidates:
            wanted = profile['game_exe'].lower()
            if any(line.lower() == wanted or (line[:2].lower() == 'z:' and line[2:].lower() == wanted) for line in lines):
                exact.append(profile)
        matches = exact or candidates
        if len(matches) > 1:
            raise ValueError('Ambiguous running game: ' + PROFILES[appid][0] + '. More than one prepared installation matches.')
        if matches:found.append(matches[0])
    return found


def run(engine_vibration=None, settings_file=None, registry=None):
    child = None
    active = None
    failed = None
    previous = None
    previous_state = None
    output = queue.Queue()
    connection = {'backendReady': False, 'inputFfb': 'unknown', 'telemetry': 'unknown'}
    transport={'state':'unknown','detail':''};next_transport=0
    try:
        # Reject malformed settings before starting any process with HID access.
        load_settings(settings_file)
        document = load_registry(registry)
        use_registry = registry is not None or bool(document['profiles']) or default_registry_path().exists()
        active_profile = None
        armed_native=set()
        while True:
            # Setup can register a game while the quiet worker is waiting.
            # Keep a live motor owner on its current snapshot until it exits.
            if child is None:
                document = load_registry(registry)
                use_registry = registry is not None or bool(document['profiles']) or default_registry_path().exists()
            text = subprocess.check_output(['/bin/ps', '-axo', 'comm='], text=True)
            profiles = running_profiles(text, document) if use_registry else []
            found = [p['appid'] for p in profiles] if use_registry else detect(text)
            selected = found[0] if len(found) == 1 else None
            profile = profiles[0] if len(profiles) == 1 else None
            if child is None and not found:
                for entry in document['profiles']:
                    if entry['appid']==690790 and entry['id'] not in armed_native:
                        from sdk_game import clear_stop_requests
                        session=Path(entry['session_dir'])
                        clear_stop_requests(session,json.loads((session/'manifest.json').read_text()))
                        armed_native.add(entry['id'])
            if not found: failed = None
            if selected != active or profile != active_profile:
                if active_profile:armed_native.discard(active_profile['id'])
                stop_child(child); child = None; active = None; active_profile = None
                output = queue.Queue()
                connection = {'backendReady': False, 'inputFfb': 'unknown', 'telemetry': 'unknown'}
                transport={'state':'unknown','detail':''};next_transport=0
                if selected != failed: failed = None
            if selected is not None and selected != failed and child is None:
                installed = installation(selected, profile=profile) if profile else installation(selected)
                if installed != 'installed':
                    raise ValueError('Patch required for ' + PROFILES[selected][0])
                print('AUTO_STATUS: Connecting · ' + PROFILES[selected][0], flush=True)
                values = load_settings(settings_file).get(str(selected), {})
                options = {'engine_vibration': engine_vibration, 'settings': values, 'settings_file': settings_file}
                if profile:options['profile'] = profile
                child = subprocess.Popen(child_command(selected, **options),
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                active = selected; active_profile = profile
                threading.Thread(target=forward_output, args=(child, output), daemon=True).start()
            while True:
                try: line = output.get_nowait()
                except queue.Empty: break
                print(line, flush=True)
                connection_line(line, connection)
            if child is not None and child.poll() is not None:
                failed = active; child = None; active = None
                connection = {'backendReady': False, 'inputFfb': 'unknown', 'telemetry': 'unknown'}
            if active==690790 and active_profile and time.monotonic()>=next_transport:
                next_transport=time.monotonic()+5
                transport=native_status(active_profile)
            status = ('Bridge error · stop and restart after checking logs' if failed is not None else
                      'Close one supported game to connect' if len(found) > 1 else
                      ('Bridge ready · ' if connection['backendReady'] else 'Connecting · ') + PROFILES[active][0] if active else
                      'Ready · launch a supported game yourself')
            if active==690790 and connection['backendReady']:
                status=('Input bridge ready · TRUEFORCE transport loaded' if transport['state']=='ready' else
                        'Input bridge ready · '+transport['detail'] if transport['detail'] else
                        'Input bridge ready · TRUEFORCE not verified')
            if status != previous: print('AUTO_STATUS: ' + status, flush=True); previous = status
            state = {'appid': selected, 'activeAppid': active, 'profileId': active_profile['id'] if active_profile else None,
                     'activeGameExe': active_profile['game_exe'] if active_profile else None,
                     'activeBottle': active_profile['source_bottle'] if active_profile else None,
                     'nativeTransport': transport['state'] if active==690790 else None,
                     'phase': 'error' if failed is not None else ('ready' if connection['backendReady'] else 'connecting') if active else 'waiting',
                     **connection, 'detail': status}
            if state != previous_state:
                print('AUTO_STATE: ' + json.dumps(state), flush=True)
                previous_state = dict(state)
            time.sleep(.5)
    except (ValueError, OSError) as error:
        print('AUTO_STATE: ' + json.dumps({'appid': active, 'activeAppid': None, 'phase': 'error',
              'backendReady': False, 'inputFfb': 'unknown', 'telemetry': 'unknown', 'detail': str(error)}), flush=True)
        raise
    finally: stop_child(child)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'patch', 'start'])
    parser.add_argument('--appid', type=int, choices=PROFILES)
    parser.add_argument('--engine-vibration', type=float, help='Compatibility override for the ETS2 profile')
    parser.add_argument('--registry', type=Path, help='Prepared installation registry')
    parser.add_argument('--profile-id', help='Select a specific installation for patching')
    parser.add_argument('--settings-file', type=Path, help='Version 1 per-game settings JSON')
    parser.add_argument('--user-ready', action='store_true')
    args = parser.parse_args()
    if args.engine_vibration is not None:
        try: percentage(args.engine_vibration, 'Engine vibration')
        except ValueError as error: parser.error(str(error))
    if args.action == 'status': print(json.dumps(states(args.registry))); return
    if args.action == 'patch':
        if args.appid is None: parser.error('appid required')
        if detect(subprocess.check_output(['/bin/ps', '-axo', 'comm='], text=True)):
            parser.error('Close supported games before patching')
        profile = prepared_profile(args.appid, args.registry, args.profile_id)
        print(installation(args.appid, patch=True, profile=profile)); return
    if not args.user_ready: parser.error('Explicit user readiness required')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try: run(engine_vibration=args.engine_vibration, settings_file=args.settings_file, registry=args.registry)
    except KeyboardInterrupt: print('Automatic bridge stopped.', flush=True)
if __name__ == '__main__': main()
