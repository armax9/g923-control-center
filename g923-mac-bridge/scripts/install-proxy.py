#!/usr/bin/env python3
"""Explicit, reversible per-game installation. Does not alter registry or security."""
import argparse, pathlib, shutil, hashlib, json
p=argparse.ArgumentParser();p.add_argument('action',choices=['install','uninstall']);p.add_argument('game_directory',type=pathlib.Path);a=p.parse_args()
d=a.game_directory.resolve();src=pathlib.Path(__file__).resolve().parents[1]/'build/windows/dinput8.dll';dst=d/'dinput8.dll';manifest=d/'.g923-proxy-install.json';backup=d/'dinput8.dll.g923-backup'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
if not d.is_dir():p.error('game directory does not exist')
if a.action=='install':
 if not src.is_file():p.error('build Windows DLL first')
 if manifest.exists() or backup.exists():p.error('installation/backup already exists; uninstall first')
 previous=dst.exists()
 if previous:shutil.copy2(dst,backup)
 try:
  shutil.copy2(src,dst);manifest.write_text(json.dumps({'sha256':sha(dst),'previous':previous},indent=2)+'\n')
 except Exception:
  if previous:shutil.copy2(backup,dst);backup.unlink()
  elif dst.exists():dst.unlink()
  raise
 print('Installed. Set bottle dinput8 override to native,builtin in CrossOver winecfg. Undo with uninstall.')
else:
 if not manifest.exists():p.error('no installation manifest')
 m=json.loads(manifest.read_text())
 if dst.exists() and sha(dst)!=m['sha256']:p.error('DLL changed since installation; refusing to overwrite')
 if m['previous']:
  if not backup.exists():p.error('backup missing')
  shutil.copy2(backup,dst);backup.unlink()
 elif dst.exists():dst.unlink()
 manifest.unlink();print('Removed. Restore prior bottle override manually if changed.')
