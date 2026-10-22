#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""One-click launcher for the accepted main-Steam installation, never run on install."""
import argparse,json,subprocess,time
from pathlib import Path
from sdk_game import load,check,command,environment,start
from game_sandbox import ROOT,windows
from portable_paths import steam_executable

def readiness(text):
    records=[]
    for line in text.splitlines():
        try:records.append(json.loads(line))
        except ValueError:pass
    return next((x for x in reversed(records) if x.get('event')=='steam_readiness'),{})

def game_running(executable="dirtrally2.exe"):
    result=subprocess.run(['/bin/ps','-axo','comm='],capture_output=True,text=True,check=True)
    return any(line.strip().lower().endswith(executable.lower()) for line in result.stdout.splitlines())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation',type=Path,required=True)
    parser.add_argument('--user-ready',action='store_true')
    parser.add_argument('--manual',action='store_true',help='Start input bridge only; never launch Steam or the game')
    args=parser.parse_args()
    if not args.user_ready:parser.error('Launch requires explicit user action')
    session=args.installation.resolve();manifest=load(session);check(session,manifest)
    if args.manual:
        try:start(session,manifest,launch_game=False)
        except KeyboardInterrupt:print('Bridge stopped.',flush=True)
        return
    if game_running(Path(manifest['game_exe']).name):raise SystemExit('DiRT Rally 2.0 is already running. Exit it first.')
    env=environment(session);game=Path(manifest['game_exe']);started=False
    logdir=session/'startup';logdir.mkdir(exist_ok=True)
    print(manifest.get('game_name','DiRT Rally 2.0')+' + G923 TRUEFORCE. The wheel must be securely mounted.\n'
          'Launching without VR; game settings are preserved.\n'
          'Waiting for Steam to become ready; sign in if needed.\n'
          'Cancel waiting with the stop button in G923 Control Center. There is no sign-in timeout.',flush=True)
    try:
        while True:
            try:
                probe=subprocess.run(command(session)+['--no-gui','--debugmsg','-all',str(ROOT/'build/sdk-lab/steam-ready.exe'),windows(game.parent/'steam_api64.dll')],env=env,cwd=game.parent,capture_output=True,text=True,timeout=40)
                state=readiness(probe.stdout)
                (logdir/'steam-readiness.txt').write_text(probe.stdout+'\n'+probe.stderr)
            except subprocess.TimeoutExpired:
                state={}
            if state.get('initialized') is True:break
            if not started and state.get('client_running') is not True:
                # Launch exactly the existing main bottle; never a second Steam install.
                with (logdir/'steam.txt').open('a') as log:
                    subprocess.Popen(command(session)+['--debugmsg','-all',str(steam_executable(manifest))],env={k:v for k,v in env.items() if k not in ('SteamAppId','SteamGameId')},stdout=log,stderr=log)
                started=True
            time.sleep(3)
        print('Steam is ready. Launching without VR. Status and stop controls are in G923 Control Center.',flush=True)
        start(session,manifest)
    except KeyboardInterrupt:
        print('Launch cancelled.',flush=True)

if __name__=='__main__':main()
