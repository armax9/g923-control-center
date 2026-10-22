#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Strip a reviewed Wine pair and verify unchanged runtime sections; no Wine or HID runs."""
from pathlib import Path
import argparse,hashlib,json,shutil,struct,subprocess,tarfile
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--prepared',type=Path,required=True,help='Reviewed original transport payload directory')
p.add_argument('--llvm-strip',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--update-catalog',action='store_true',help='Record transformed hashes in this source checkout')
a=p.parse_args()
root=Path(__file__).resolve().parents[1];out=a.output.resolve();strip=a.llvm_strip.resolve()
if out.exists():p.error('Output already exists; choose a fresh directory')
out.mkdir(parents=True)
def sections(p):
 d=p.read_bytes();result={}
 if d[:2]==b'MZ':
  pe=struct.unpack_from('<I',d,60)[0];n=struct.unpack_from('<H',d,pe+6)[0];opt=struct.unpack_from('<H',d,pe+20)[0];pos=pe+24+opt
  for i in range(n):
   at=pos+i*40;name=d[at:at+8].split(b'\0')[0].decode();size,offset=struct.unpack_from('<II',d,at+16)
   if name in ('.text','.rdata','.data','.pdata','.xdata','.reloc'):result[name]=hashlib.sha256(d[offset:offset+size]).hexdigest()
 else:
  assert d[:4]==b'\xcf\xfa\xed\xfe';n=struct.unpack_from('<I',d,16)[0];at=32
  for i in range(n):
   cmd,size=struct.unpack_from('<II',d,at)
   if cmd==0x19:
    count=struct.unpack_from('<I',d,at+64)[0]
    for j in range(count):
     s=at+72+j*80;name=d[s:s+16].split(b'\0')[0].decode();seg=d[s+16:s+32].split(b'\0')[0].decode();length=struct.unpack_from('<Q',d,s+40)[0];offset=struct.unpack_from('<I',d,s+48)[0]
     if seg not in ('__DWARF','__LINKEDIT') and offset:result[seg+'/'+name]=hashlib.sha256(d[offset:offset+length]).hexdigest()
   at+=size
 return result
catalog=json.loads((a.prepared/'catalog.json').read_text());build=catalog['builds'][0];checks={}
for module in build['modules'].values():
 src=a.prepared/module['path'];assert hashlib.sha256(src.read_bytes()).hexdigest()==module['sha256'];dst=out/module['path'];dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 subprocess.run([str(strip),'--strip-debug',str(dst)] if dst.suffix=='.sys' else ['/usr/bin/strip','-S','-x',str(dst)],check=True)
 assert sections(src)==sections(dst),(src,sections(src),sections(dst))
 if dst.suffix=='.so':subprocess.run(['codesign','--force','--sign','-',str(dst)],check=True)
 assert b'/Users/' not in dst.read_bytes()
 module['sha256']=hashlib.sha256(dst.read_bytes()).hexdigest();checks[dst.name]={'runtime_sections_unchanged':True,'sha256':module['sha256']}
build['distribution']={'transform':'Debug information stripped; Mach-O ad-hoc signed. Runtime section contents verified unchanged.','hardware_test':'Original unstripped pair accepted; no new physical test.'}
if a.update_catalog:(root/'patches/transport-catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
if json.loads((root/'patches/transport-catalog.json').read_text())!=catalog:raise ValueError('Review transformed hashes and pass --update-catalog before corresponding-source packaging')
(out/'catalog.json').write_text(json.dumps(catalog,indent=2)+'\n');(out/'STRIP_VERIFICATION.json').write_text(json.dumps(checks,indent=2)+'\n')
(out/'sources').mkdir(exist_ok=True)
for name in ['AUTHORS','LICENSE','COPYING.LIB']:shutil.copy2(a.prepared/'sources'/name,out/'sources'/name)
with tarfile.open(a.prepared/'sources/g923-wine-11.17-source.tar.xz') as tf:
 with tf.extractfile('g923-wine-transport-source/upstream/wine-11.17.tar.gz') as src,(out/'upstream.tar.gz').open('wb') as dst:shutil.copyfileobj(src,dst)
subprocess.run(['python3',str(root/'scripts/build-wine-transport.py'),'--source-archive',str(out/'upstream.tar.gz'),'--source-bundle',str(out/'sources/g923-wine-11.17-source.tar.xz')],check=True)
print(json.dumps(checks,indent=2))
