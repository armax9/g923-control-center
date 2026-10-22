#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Explicit user-started native-SDK game experiment, separate from accepted FFB."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import stat
import shutil
import struct
import subprocess
import time

from game_sandbox import ROOT, prepare, sha, windows
from portable_paths import (bottle_environment, payload, runtime_directory,
                            steam_executable, wine_command)


def load(session):
    manifest = json.loads((session/'manifest.json').read_text())
    if manifest.get('main_steam_experiment') and manifest.get('source_bottle'):
        if not manifest.get('applied'): raise ValueError('SDK experiment is not installed')
        if not (Path(manifest['source_bottle'])/'cxbottle.conf').is_file():
            raise ValueError('The selected bottle is unavailable. Refresh its location in Settings.')
        return manifest
    if not manifest.get('game_experiment') or manifest.get('bottle') != 'G923TFGame':
        raise ValueError('Not a private SDK game session')
    prefix = session/'G923TFGame'
    if prefix.is_symlink() or json.loads((prefix/'g923-owned-prefix.json').read_text()).get('project') != str(ROOT):
        raise ValueError('Invalid private prefix')
    return manifest


def command(session):
    manifest = load(session)
    return wine_command(session, manifest)


def environment(session):
    manifest = load(session)
    env = bottle_environment(manifest)
    env.update(SteamAppId=str(manifest.get('steam_app_id',690790)), SteamGameId=str(manifest.get('steam_app_id',690790)),
               G923_SDK_TRACE='1', G923_SDK_STOP_FILE=windows(stop_paths(session,manifest)[0]))
    return env


def stop_paths(session,manifest):
    paths=[Path(session)/'sdk-stop']
    if manifest.get('main_steam_experiment') and manifest.get('source_bottle'):
        paths.insert(0,Path(manifest['source_bottle'])/'g923-sdk-stop')
    return paths


def clear_stop_requests(session,manifest):
    for path in stop_paths(session,manifest):
        if path.exists() or path.is_symlink():
            info=path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1:
                raise ValueError('Unsafe SDK stop file preserved: '+str(path))
            path.unlink()


def check(session, manifest):
    from registry_overrides import verify
    verify(manifest)
    game = Path(manifest['game_exe'])
    expected = [(game, manifest['game_sha']), (game.parent/'dinput8.dll', manifest['game_dll_sha']),
                (game.parent/'steam_api64.dll', manifest['steam_api_sha'])]
    expected += [(runtime_directory(session, manifest)/'lib/wine'/name, value) for name,value in manifest['runtime_hashes'].items()]
    expected += [(session/name,value) for name,value in manifest.get('backend_hashes',{}).items()]
    for path, value in expected:
        if sha(path) != value:
            raise ValueError('Experiment file changed: '+str(path))
    prefix = Path(manifest['source_bottle']) if manifest.get('main_steam_experiment') else session/'G923TFGame'
    if sha(prefix/'drive_c/windows/system32/dinput8.dll')!=manifest['private_system_dinput_sha']:raise ValueError('Private builtin DInput changed')
    sdk = Path(manifest['sdk_target']) if manifest.get('sdk_target') else prefix/'drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll'
    if sha(sdk) != manifest['sdk_sha']:
        raise ValueError('Original SDK changed')
    for relative, value in ({} if manifest.get('main_steam_experiment') else manifest['settings_hashes']).items():
        copied = prefix/'drive_c/users/crossover/Documents/My Games/DiRT Rally 2.0'/relative
        # The game may legitimately change its private copy after the first run.
        if not (session/'game-started').exists() and sha(copied) != value:
            raise ValueError('Initial settings copy differs')
    print('Verified: DLL, original SDK and patched transport. Game settings are unchanged.', flush=True)


def stop(session):
    for path in stop_paths(session,load(session)):
        if path.is_symlink():raise ValueError('Unsafe SDK stop file preserved')
        path.touch(mode=0o600)
    (session/'host-stop').touch()
    # Let observed force calls clear KF/TF and mode before closing the private
    # game/Steam processes. Never kill another prefix or the normal bridge.
    time.sleep(.4)
    env = environment(session)
    if load(session).get('main_steam_experiment'):
        print('SDK cleanup requested for the next game call. Exit the game normally; Steam is not closed automatically.', flush=True)
        return 0
    env['WINEPREFIX'] = str(session/'G923TFGame')
    result = subprocess.run([str(session/'runtime/bin/wineserver-x86'), '-k'], env=env,
                            capture_output=True, text=True, timeout=15)
    print('Stop requested. Only the isolated test bottle was closed, including its game and Steam.', flush=True)
    return result.returncode


def prepare_input_mapping(mapping):
    """Recreate only the owned private input file, including after /tmp cleanup.

    The publisher exclusively creates its file but does not create directories.
    Never follow a substituted directory/file or remove another user's file.
    """
    mapping = Path(mapping)
    if not mapping.is_absolute():
        raise ValueError('Input mapping must use an absolute path')
    parent = mapping.parent
    try:
        parent.mkdir(mode=0o700)
    except FileExistsError:
        pass
    directory = parent.lstat()
    if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid()
            or stat.S_IMODE(directory.st_mode) != 0o700):
        raise ValueError('Input mapping directory must be owned and mode 0700')
    try:
        info = mapping.lstat()
    except FileNotFoundError:
        return mapping
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size != 8192
            or info.st_nlink != 1):
        raise ValueError('Unsafe stale input mapping')
    mapping.unlink()
    return mapping


def start(session, manifest, launch_game=True):
    check(session, manifest)
    registration = session/'sdk-registration-G923TFGame/manifest.json'
    if not manifest.get('main_steam_experiment') and (not registration.is_file() or not json.loads(registration.read_text()).get('applied')):
        raise ValueError('Private SDK is not registered')
    lock_path = '/tmp/g923-mac-bridge-'+str(os.getuid())+'.lock'
    descriptor = os.open(lock_path, os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC, 0o600)
    info = os.fstat(descriptor)
    if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
        os.close(descriptor)
        raise ValueError('Unsafe motor ownership lock')
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(descriptor)
        raise ValueError('Stop the classic FFB bridge first: two force senders cannot run simultaneously.')
    publisher = launcher = None
    try:
        game = Path(manifest['game_exe'])
        clear_stop_requests(session,manifest)
        for name in ['host-stop']:
            (session/name).unlink(missing_ok=True)
        logs = session/('run-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
        logs.mkdir()
        env = environment(session)
        if launch_game:
            with (logs/'steam-ready.jsonl').open('w') as log, (logs/'steam-ready-errors.txt').open('w') as err:
                ready = subprocess.run(command(session)+['--no-gui','--debugmsg','-all',
                            str(ROOT/'build/sdk-lab/steam-ready.exe'), windows(game.parent/'steam_api64.dll')],
                            env=env, cwd=game.parent, stdout=log, stderr=err, timeout=45)
            if ready.returncode:
                raise ValueError('Steam API is not ready. The game was not launched. Restore the Steam client first.')
        for name in ['crossover-ffb-observe.log','g923-sdk-trace.jsonl']:
            path = game.parent/name
            if path.is_file():
                if launch_game:shutil.move(str(path),str(logs/('previous-'+name)))
                else:shutil.copy2(path,logs/('startup-snapshot-'+name))
        mapping = prepare_input_mapping(Path(manifest['mapping']))
        with (logs/'input.txt').open('w') as input_log, (logs/'game-stdout.txt').open('w') as output, (logs/'wine.log').open('w') as error:
            publisher = subprocess.Popen([str(payload('g923-input', session)),'--map',str(mapping),'--seconds','0'], stdout=input_log, stderr=subprocess.STDOUT)
            deadline=time.monotonic()+15
            while True:
                if publisher.poll() is not None:
                    raise ValueError('Input publisher exited; see input.txt')
                if mapping.exists() and mapping.stat().st_size==8192:
                    with mapping.open('rb') as source:header=source.read(104)
                    if struct.unpack_from('<I',header,68)[0]==1:break
                if time.monotonic()>deadline:
                    raise ValueError('Wheel input startup timed out')
                time.sleep(.05)
            if launch_game:
                (session/'game-started').touch()
                (logs/'launch.json').write_text(json.dumps(dict(arguments=['-novr'], game_exe=str(game),
                     sdk_is_only_force_sender=True, game_executable_modified=False, app_local_bridge_installed=True, physical_playback_confirmed=False),indent=2)+'\n')
                launcher = subprocess.Popen(command(session)+['--debugmsg','-all,+loaddll','--dll','dinput8=n,b',
                                             str(game),'-novr'], env=env, cwd=game.parent, stdout=output, stderr=error)
                print('Game launched without VR. Input uses the bridge; forces use the original SDK.\n'
                      'The bridge stops automatically after you exit the game.\n'
                      'Manual stop: use the stop button in G923 Control Center.\nLogs: '+str(logs), flush=True)
            else:
                print('BRIDGE_LISTENING: Input publisher ready. Native TRUEFORCE connection has not been verified. Steam and game remain under your control.',flush=True)
            # Steam may hand off the game. Observe the actual game process,
            # never treat the short-lived wrapper's exit as game exit.
            seen_game=False;next_process_check=0
            while not (session/'host-stop').exists():
                if publisher.poll() is not None:
                    raise RuntimeError('Input publisher exited during SDK test')
                if manifest.get('installed_permanently') and time.monotonic()>=next_process_check:
                    next_process_check=time.monotonic()+1
                    try:
                        processes=subprocess.run(['/bin/ps','-axo','comm='],capture_output=True,text=True,timeout=3,check=True)
                        live=any(line.strip().lower().endswith(game.name.lower()) for line in processes.stdout.splitlines())
                        if live:seen_game=True
                        elif seen_game:
                            print('Game exited. Stopping the bridge; Steam remains open.',flush=True)
                            break
                    except (OSError,subprocess.SubprocessError):
                        pass # Keep the publisher until explicit Stop if process inspection is unavailable.
                time.sleep(.1)
    finally:
        if publisher:
            try:stop(session)
            except Exception as error:print('Stop needs attention: '+str(error),flush=True)
        if publisher and publisher.poll() is None:
            publisher.terminate()
            try:publisher.wait(timeout=5)
            except subprocess.TimeoutExpired:publisher.kill();publisher.wait()
        if launcher and launcher.poll() is None:
            launcher.terminate()
        if 'logs' in locals():
            for name in ['crossover-ffb-observe.log','g923-sdk-trace.jsonl']:
                path=game.parent/name
                if path.is_file():
                    try:shutil.copy2(path,logs/name)
                    except OSError:pass
        os.close(descriptor)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','check','steam','start','stop'])
    parser.add_argument('--session',type=Path,required=True)
    parser.add_argument('--source-bottle',type=Path)
    parser.add_argument('--game-exe',type=Path)
    parser.add_argument('--transport',type=Path)
    parser.add_argument('--sdk-dll',type=Path)
    parser.add_argument('--user-ready',action='store_true')
    args=parser.parse_args();session=args.session.resolve()
    if args.action=='prepare':
        if not all([args.source_bottle,args.game_exe,args.transport,args.sdk_dll]):
            parser.error('prepare requires source bottle, game exe, transport and SDK DLL')
        print(json.dumps(prepare(session,args.source_bottle,args.game_exe,args.transport,args.sdk_dll),indent=2))
        return
    manifest=load(session)
    if args.action=='check':return check(session,manifest)
    if args.action=='stop':return stop(session)
    if not args.user_ready:parser.error('Steam/game launch requires explicit user action/readiness')
    if args.action=='steam':
        # Intentionally only Steam. No app launch URL and no game argument.
        prefix=Path(manifest['source_bottle']) if manifest.get('main_steam_experiment') else session/'G923TFGame'
        steam=steam_executable(manifest)
        env=environment(session)
        env.pop('SteamAppId',None);env.pop('SteamGameId',None)
        env['G923_DINPUT_IAT']='1'
        overrides=env.get('WINEDLLOVERRIDES','')
        env['WINEDLLOVERRIDES']=overrides+(';' if overrides else '')+'winmm=n,b;dinput8=n,b'
        logdir=session/'startup';logdir.mkdir(exist_ok=True)
        with (logdir/'manual-steam.log').open('a') as log:
            subprocess.Popen(command(session)+[str(steam)],env=env,stdout=log,stderr=log)
        print('Steam open requested. No game was launched. If Steam was already open through a different runtime, exit Steam and use Open Steam again.',flush=True)
        return 0
    start(session,manifest)


if __name__=='__main__':
    main()
