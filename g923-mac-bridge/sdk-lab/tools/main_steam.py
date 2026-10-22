#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reversible SDK experiment in the user's existing, stopped Steam bottle."""
import argparse, hashlib, json, os, re, shutil, subprocess
from pathlib import Path
from game_sandbox import ROOT, sha

CLSID = r'Software\\Classes\\CLSID\\{e8dfb59f-141f-40e4-8dd4-5526ead25a4c}'
BUS = r'System\\CurrentControlSet\\Services\\winebus'
SDK_HASH = '2468bdafe64c09ff42ef26f09e49f2096321bb687467323aafb3f0672fb83315'

def stopped():
    result = subprocess.run(['ps','-axo','comm='],capture_output=True,text=True,check=True)
    names = [Path(line.strip()).name.lower() for line in result.stdout.splitlines()]
    if any(n in ('wine','wine64','wine64-preloader','wine-preloader','steam.exe','dirtrally2.exe') or n.startswith('wineserver') or n.startswith('g923classic') for n in names):
        raise ValueError('Закрой Steam, игру и FFB-мост перед установкой/откатом. Процессы автоматически не завершаются.')

def section(text, key):
    pattern = re.compile(r'^\['+re.escape(key)+r'\][^\n]*\n.*?(?=^\[|\Z)', re.M|re.S)
    match=pattern.search(text)
    return match, match.group() if match else None

def patch_registry(text):
    match, block = section(text, BUS)
    if match is None or '"EnableHidraw"=' in block: raise ValueError('Expected existing winebus without HID override')
    added='"EnableHidraw"=str(7):"046D:C266\\0"\n'
    pos=match.start()+block.index('\n')+1
    text=text[:pos]+added+text[pos:]
    if section(text,CLSID)[0]: raise ValueError('SDK registration already exists; refusing overwrite')
    sdkblock='['+CLSID+']\n@="'+r'C:\\Program Files\\Logi\\Trueforce\\1_3_12\\trueforce_sdk_x64.dll'+'"\n\n'
    return text.rstrip()+'\n\n'+sdkblock

def unpatch_registry(text):
    match,block=section(text,CLSID)
    expected=r'C:\\Program Files\\Logi\\Trueforce\\1_3_12\\trueforce_sdk_x64.dll'
    if match is None or expected not in block: raise ValueError('SDK registration changed; manual review required')
    text=text[:match.start()]+text[match.end():]
    match,block=section(text,BUS)
    line='"EnableHidraw"=str(7):"046D:C266\\0"\n'
    if match is None or line not in block: raise ValueError('HID override changed; manual review required')
    return text[:match.start()]+block.replace(line,'',1)+text[match.end():]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','apply','restore']);p.add_argument('--session',type=Path,required=True);a=p.parse_args();s=a.session.resolve()
    if a.action=='prepare':
        if s.exists():raise ValueError('Session already exists')
        work=ROOT.parent.parent/'work'; old=json.loads((work/'crossover-tf-game/manifest.json').read_text())
        bottle=Path(old['source_bottle']); game=Path(old['source_game']); runtime=work/'crossover-tf-isolated/runtime'
        sdk=work/'sdk-private/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll'
        candidate=work/'crossover-tf-game/game/dinput8.dll'
        if sha(sdk)!=SDK_HASH or sha(candidate)!=old['game_dll_sha']:raise ValueError('Staged bytes changed')
        reg=(bottle/'system.reg').read_text();patch_registry(reg)
        if sha(game.parent/'dinput8.dll')!=old['source_game_dll_sha']:raise ValueError('Accepted FFB DLL changed')
        s.mkdir();(s/'runtime').symlink_to(runtime,target_is_directory=True)
        shutil.copy2(candidate,s/'sdk-dinput8.dll');shutil.copy2(game.parent/'dinput8.dll',s/'accepted-dinput8.dll')
        system=bottle/'drive_c/windows/system32/dinput8.dll';shutil.copy2(system,s/'system-dinput8-before.dll')
        target_sdk=bottle/'drive_c/Program Files/Logi/Trueforce/1_3_12/trueforce_sdk_x64.dll'
        if target_sdk.exists():raise ValueError('SDK destination exists')
        m=dict(old,main_steam_experiment=True,bottle='Steam',game_exe=str(game),bottle_root=str(bottle.parent),source_bottle=str(bottle),sdk_source=str(sdk),sdk_target=str(target_sdk),system_before_sha=sha(system),accepted_dll_sha=sha(game.parent/'dinput8.dll'),applied=False)
        (s/'manifest.json').write_text(json.dumps(m,indent=2)+'\n'); print('Подготовлено без изменения Steam/игры: '+str(s));return
    m=json.loads((s/'manifest.json').read_text());stopped()
    if not m.get('main_steam_experiment') or m['bottle']!='Steam':raise ValueError('Invalid manifest')
    bottle=Path(m['source_bottle']); game=Path(m['game_exe']).parent/'dinput8.dll'; system=bottle/'drive_c/windows/system32/dinput8.dll';reg=bottle/'system.reg';sdk=Path(m['sdk_target'])
    if a.action=='apply':
        if m['applied']:raise ValueError('Already applied')
        if sha(game)!=m['accepted_dll_sha'] or sha(system)!=m['system_before_sha'] or sdk.exists():raise ValueError('Installation inputs changed')
        before=reg.read_text();after=patch_registry(before)
        (s/'system-before-install.reg').write_text(before)
        # Mark the transaction before any external write so partial failures remain recoverable.
        m['installation_started']=True;(s/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
        sdk.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(Path(m['sdk_source']),sdk)
        shutil.copy2(s/'runtime/lib/wine/x86_64-windows/dinput8.dll',system)
        reg.write_text(after);shutil.copy2(s/'sdk-dinput8.dll',game)
        m['applied']=True
        print('SDK установлен в обычную Steam. Игра и мотор не запускались.')
    else:
        if sha(game) not in (m['game_dll_sha'],m['accepted_dll_sha']):raise ValueError('Game DLL changed; refusing overwrite')
        if sha(system) not in (m['private_system_dinput_sha'],m['system_before_sha']):raise ValueError('System DLL changed; refusing overwrite')
        before=reg.read_text()
        if section(before,CLSID)[0]:reg.write_text(unpatch_registry(before))
        shutil.copy2(s/'accepted-dinput8.dll',game);shutil.copy2(s/'system-dinput8-before.dll',system)
        if sdk.exists():
            if sha(sdk)!=SDK_HASH:raise ValueError('SDK bytes changed; refusing removal')
            sdk.unlink()
        m['applied']=False;print('Рабочий обычный FFB восстановлен. Настройки игры не менялись.')
    (s/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')

if __name__=='__main__':main()
