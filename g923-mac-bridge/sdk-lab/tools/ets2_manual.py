#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Explicit, reversible ETS2 loader installation. Never launches a game or writes HID."""
import json,os,re,shutil,subprocess
from pathlib import Path
import ets2
KEY=r'HKCU\Software\Wine\AppDefaults\eurotrucks2.exe\DllOverrides'
VALUE='native,builtin'
MARKER=b'G923 chain opt-in v1\n'

def registry(args):
 m=ets2.state()
 env=ets2.env(m);env['WINEDEBUG']='-all'
 return subprocess.run(ets2.runtime_command(m)+['--no-gui','--debugmsg','-all','reg.exe']+args,env=env,capture_output=True,text=True,timeout=30)

def current_override():
 result=registry(['query',KEY,'/v','winmm'])
 if result.returncode==1:return None
 if result.returncode:raise RuntimeError('Cannot inspect ETS2 WinMM override: '+result.stderr)
 match=re.search(r'winmm\s+REG_SZ\s+([^\r\n]+)',result.stdout,re.I)
 if not match:raise RuntimeError('Unexpected registry output: '+result.stdout)
 return match.group(1).strip()

def restore(m):
 record=m.get('manual_chain')
 if not record:return
 value=current_override()
 if value!=VALUE:raise ValueError('ETS2 WinMM override changed externally; refusing rollback')
 previous=record['previous_winmm']
 args=['delete',KEY,'/v','winmm','/f'] if previous is None else ['add',KEY,'/v','winmm','/t','REG_SZ','/d',previous,'/f']
 result=registry(args)
 if result.returncode:raise RuntimeError('Could not restore ETS2 WinMM override')

def configure():
 m=ets2.state()
 processes=subprocess.check_output(['/bin/ps','-axo','comm='],text=True)
 if any(x.strip().lower().endswith('eurotrucks2.exe') for x in processes.splitlines()):raise ValueError('Close ETS2 before updating its loader')
 marker=ets2.GAME/'g923-chain.enabled'
 if marker.exists() and marker.read_bytes()!=MARKER:raise ValueError('Foreign chain marker preserved')
 if 'manual_chain' not in m:
  previous=current_override();backup=ets2.INSTALL/'winmm-before-manual.dll'
  if backup.exists():raise ValueError('Unrecorded loader backup; inspect before continuing')
  shutil.copyfile(ets2.GAME/'winmm.dll',backup)
  m['manual_chain']={'previous_winmm':previous,'previous_loader_sha':ets2.sha(backup),'loader_backup':str(backup)}
  (ets2.INSTALL/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
 from portable_paths import payload
 source=payload('winmm.dll',ets2.INSTALL)
 for target in [ets2.INSTALL/'winmm.dll',ets2.GAME/'winmm.dll']:shutil.copyfile(source,target)
 marker.write_bytes(MARKER)
 m['installed_files'].update({'winmm.dll':ets2.sha(source),'g923-chain.enabled':ets2.sha(marker)})
 if 'winmm.dll' in m.get('backend_hashes',{}):m['backend_hashes']['winmm.dll']=ets2.sha(source)
 (ets2.INSTALL/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
 result=registry(['add',KEY,'/v','winmm','/t','REG_SZ','/d',VALUE,'/f'])
 if result.returncode or current_override()!=VALUE:raise RuntimeError('ETS2 WinMM registration failed; installation journal preserved')
 ets2.state()
 print('ETS2 manual loader installed: per-game WinMM override and file opt-in. DLAA preserved. No game or motor started.')

if __name__=='__main__':configure()
