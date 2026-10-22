#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Per-game experimental SDK/relay installation, reusing the accepted runtime."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
from game_sandbox import ROOT,sha,windows
from sdk_game import check as sdk_check
TOP=ROOT.parent.parent
BASE=TOP/'outputs/G923 Installation'
NATIVE={805550,3058630}
RELAYS={244210:'assetto',805550:'acc',3058630:'ac-evo',365960:'rf2',2399420:'lmu',211500:'raceroom',266410:'iracing'}

def session_for(exe,prefix):
    key=hashlib.sha256((str(exe)+'\0'+str(prefix)).encode()).hexdigest()[:24]
    return ROOT/'build/game-profiles'/key

def stopped(exe):
    output=subprocess.check_output(['/bin/ps','-axo','comm='],text=True)
    if any(x.strip().lower().endswith(exe.name.lower()) for x in output.splitlines()):
        raise ValueError('Close this game before changing installed files')

def install_sdk(exe,prefix,appid):
    if appid not in NATIVE:raise ValueError('No native SDK profile for this game')
    base=json.loads((BASE/'manifest.json').read_text());sdk_check(BASE,base)
    if prefix.resolve()!=Path(base['source_bottle']).resolve():raise ValueError('This SDK profile currently requires the prepared Steam bottle. Other bottles need transport deployment first.')
    session=session_for(exe,prefix)
    if (session/'manifest.json').exists():raise ValueError('Profile already exists; check or remove it first')
    target=exe.parent/'dinput8.dll'
    # Preserve mods and overlays: no generic rename or replacement of third-party DLLs.
    if target.exists():raise ValueError('Existing dinput8.dll preserved. This game needs its own verified chain profile.')
    source=Path(base['game_exe']).parent/'dinput8.dll'
    if sha(source)!=base['game_dll_sha']:raise ValueError('Accepted payload changed')
    api=exe.parent/'steam_api64.dll'
    if not api.is_file():raise ValueError('steam_api64.dll not found beside executable')
    session.mkdir(parents=True)
    (session/'runtime').symlink_to(BASE/'runtime',target_is_directory=True)
    manifest=dict(base,game_exe=str(exe),source_game=str(exe),game_sha=sha(exe),steam_api_sha=sha(api),steam_app_id=appid,game_name=exe.stem,profile_experimental=True,installed_permanently=True,owned_files={str(target):sha(source)},installation_started=True,applied=False)
    (session/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    try:
        with target.open('xb') as out:out.write(source.read_bytes())
        manifest['applied']=True
        (session/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    except Exception:
        # A partial transaction stays inspectable; never remove unknown bytes.
        raise
    print('Experimental original-SDK profile installed. Driving test pending. Game settings unchanged.')

def remove_sdk(exe,prefix):
    stopped(exe);session=session_for(exe,prefix)
    manifest=json.loads((session/'manifest.json').read_text())
    if not manifest.get('profile_experimental'):raise ValueError('Not an owned experimental profile')
    for name,value in manifest['owned_files'].items():
        target=Path(name)
        if target.exists() and sha(target)!=value:raise ValueError('Installed file changed; refusing removal: '+name)
    for name in manifest['owned_files']:Path(name).unlink(missing_ok=True)
    manifest['applied']=False;(session/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Per-game SDK bridge removed. Shared accepted SDK/runtime preserved.')

def relay_action(action,exe,prefix,appid):
    game=RELAYS.get(appid)
    if not game:raise ValueError('No shared-memory relay adapter for this game')
    source=TOP/'outputs/mescon-telemetry/build/logi-tf-relay.exe'
    session=session_for(exe,prefix);record=session/'relay-install.json';target=exe.parent/'g923-telemetry-relay.exe'
    if action=='install-relay':
        stopped(exe)
        if target.exists():raise ValueError('Existing relay file preserved')
        session.mkdir(parents=True,exist_ok=True)
        record.write_text(json.dumps(dict(path=str(target),sha=sha(source),game=game))+'\n')
        with target.open('xb') as out:out.write(source.read_bytes())
        print('Relay installed. Start it in the same bottle as the game. rF2/LMU also require their shared-memory plugin.');return
    m=json.loads(record.read_text())
    if Path(m['path'])!=target or sha(target)!=m['sha']:raise ValueError('Relay changed or moved')
    if action=='remove-relay':
        stopped(exe);target.unlink();record.unlink();print('Relay removed');return
    if action=='run-relay':
        env=os.environ.copy();env['CX_BOTTLE_PATH']=str(prefix.parent)
        print('Telemetry relay running; Ctrl-C stops only this relay.',flush=True)
        process=subprocess.Popen([str(BASE/'runtime/bin/wine'),'--bottle',prefix.name,'--no-gui',windows(target),'--game',game],env=env,cwd=exe.parent)
        try:return process.wait()
        except KeyboardInterrupt:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        return
    print('Relay hash verified; game hardware acceptance pending')

def scs_action(action,exe,prefix,appid):
    if appid!=270880:raise ValueError('ETS2 uses its dedicated DLAA-preserving installer')
    stopped(exe)
    source=TOP/'outputs/mescon-telemetry/build/logi_tf_scs.dll'
    target=exe.parent/'plugins/logi_tf_scs.dll'
    session=session_for(exe,prefix);record=session/'scs-install.json'
    if action=='install-scs':
        if target.exists():raise ValueError('Existing SCS plugin preserved')
        session.mkdir(parents=True,exist_ok=True);target.parent.mkdir(exist_ok=True)
        record.write_text(json.dumps(dict(path=str(target),sha=sha(source)))+'\n')
        with target.open('xb') as out:out.write(source.read_bytes())
        print('SCS plugin installed. Use relay adapter 20780 and the input/FFB bridge; ATS driving test pending.');return
    m=json.loads(record.read_text())
    if Path(m['path'])!=target or sha(target)!=m['sha']:raise ValueError('SCS plugin changed')
    if action=='remove-scs':target.unlink();record.unlink();print('SCS plugin removed')
    else:print('SCS plugin verified')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['install','check','remove','play','install-relay','check-relay','remove-relay','run-relay','install-scs','check-scs','remove-scs']);p.add_argument('--exe',type=Path,required=True);p.add_argument('--prefix',type=Path,required=True);p.add_argument('--appid',type=int,required=True);a=p.parse_args()
    exe=a.exe.resolve();prefix=a.prefix.resolve()
    if not exe.is_file() or not (prefix/'user.reg').is_file():raise ValueError('Game or bottle missing')
    if a.action.endswith('scs'):return scs_action(a.action,exe,prefix,a.appid)
    if a.action.endswith('relay'):return relay_action(a.action,exe,prefix,a.appid)
    if a.action=='install':stopped(exe);return install_sdk(exe,prefix,a.appid)
    if a.action=='remove':return remove_sdk(exe,prefix)
    session=session_for(exe,prefix)
    if a.action=='check':
        manifest=json.loads((session/'manifest.json').read_text());sdk_check(session,manifest);return
    if a.action=='play':
        return subprocess.call([shutil.which('python3'),str(ROOT/'sdk-lab/tools/installed_play.py'),'--installation',str(session),'--user-ready'])
if __name__=='__main__':main()
