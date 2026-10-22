#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded PE inventory. Never loads DLLs or executes proprietary code."""
import hashlib,json,pathlib,re,struct
class PEError(ValueError):pass
class PE:
 def __init__(self,data):
  self.data=data
  if self.take(0,2)!=b'MZ':raise PEError('not an MZ image')
  nt=self.u32(0x3c)
  if self.take(nt,4)!=b'PE\0\0':raise PEError('missing PE signature')
  self.machine,self.nsections=struct.unpack('<HH',self.take(nt+4,4))
  if not 1<=self.nsections<=96:raise PEError('invalid section count')
  optsize=self.u16(nt+20);opt=nt+24;self.take(opt,optsize)
  magic=self.u16(opt)
  if magic not in (0x10b,0x20b):raise PEError('unsupported optional header')
  self.bits=64 if magic==0x20b else 32
  base=112 if self.bits==64 else 96;countoff=108 if self.bits==64 else 92
  if optsize<base:raise PEError('short optional header')
  self.header_size=self.u32(opt+60)
  self.directories=[]
  ndirs=min(self.u32(opt+countoff),16)
  if base+ndirs*8>optsize:raise PEError('truncated data directories')
  for i in range(ndirs):self.directories.append(struct.unpack('<II',self.take(opt+base+8*i,8)))
  self.sections=[]
  for i in range(self.nsections):
   s=opt+optsize+i*40
   name=self.take(s,8).split(b'\0')[0].decode('ascii','replace')
   vs,va,rs,rp=struct.unpack('<IIII',self.take(s+8,16))
   if rs:self.take(rp,rs)
   self.sections.append((va,vs,rp,rs,name))
 def take(self,off,n):
  if off<0 or n<0 or off>len(self.data)-n:raise PEError('out-of-bounds PE field')
  return self.data[off:off+n]
 def u16(self,o):return struct.unpack('<H',self.take(o,2))[0]
 def u32(self,o):return struct.unpack('<I',self.take(o,4))[0]
 def rva(self,a,n=1):
  if a<self.header_size:self.take(a,n);return a
  for va,vs,rp,rs,_ in self.sections:
   if va<=a<va+max(vs,rs):
    delta=a-va
    if delta+n>rs:raise PEError('RVA references zero-filled or truncated section')
    self.take(rp+delta,n);return rp+delta
  raise PEError('unmapped RVA')
 def string(self,a):
  off=self.rva(a);end=self.data.find(b'\0',off,min(off+4096,len(self.data)))
  if end<0:raise PEError('unterminated PE string')
  self.rva(a,end-off+1)
  return self.data[off:end].decode('ascii','replace')
 def directory(self,i):return self.directories[i] if i<len(self.directories) else (0,0)
 def exports(self):
  a,size=self.directory(0)
  if not a or not size:return []
  off=self.rva(a,40);nf=self.u32(off+20);nn=self.u32(off+24)
  if nn>65536 or nf>1000000:raise PEError('excessive exports')
  functions=self.rva(self.u32(off+28),nf*4) if nf else 0
  names=self.rva(self.u32(off+32),nn*4) if nn else 0
  ords=self.rva(self.u32(off+36),nn*2) if nn else 0
  result=[]
  for i in range(nn):
   ordinal=self.u16(ords+2*i)
   if ordinal>=nf:raise PEError('bad export ordinal')
   address=self.u32(functions+4*ordinal)
   result.append({'name':self.string(self.u32(names+4*i)),'rva':address,'forwarded_to':self.string(address) if a<=address<a+size else None})
  return result
 def imports(self):
  a,size=self.directory(1)
  if not a or not size:return []
  result=[];width=self.bits//8
  for index in range(min(size//20,4096)):
   off=self.rva(a+index*20,20);oft,stamp,chain,name,iat=struct.unpack('<IIIII',self.take(off,20))
   if not any((oft,stamp,chain,name,iat)):return result
   symbols=[]
   for j in range(65536):
    pos=self.rva((oft or iat)+j*width,width);v=int.from_bytes(self.take(pos,width),'little')
    if not v:break
    symbols.append('#'+str(v&65535) if v&(1<<(self.bits-1)) else self.string(v+2))
   else:raise PEError('unterminated import thunk')
   result.append({'dll':self.string(name),'symbols':symbols})
  raise PEError('unterminated imports')
 def report(self):
  certoff,certlen=self.directory(4)
  if certlen:self.take(certoff,certlen)
  ascii_symbols=set(m.decode('ascii') for m in re.findall(rb'(?<![A-Za-z0-9_])(?:logiTrueForce|logiWheel|Logi)[A-Za-z0-9_]{2,100}',self.data))
  return {'machine':hex(self.machine),'bits':self.bits,'x64':self.machine==0x8664 and self.bits==64,'sha256':hashlib.sha256(self.data).hexdigest(),'size':len(self.data),'exports':self.exports(),'imports':self.imports(),'certificate_table_present':bool(certlen),'certificate_note':'presence is not signature validation','logitech_string_candidates':sorted(ascii_symbols),'string_note':'heuristic references, not proof a game invokes SDK','delay_import_directory_present':bool(self.directory(13)[0])}
def inspect(path):
 path=pathlib.Path(path)
 if path.stat().st_size>1024**3:raise PEError('file exceeds 1 GiB inventory limit')
 return PE(path.read_bytes()).report()
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('file',type=pathlib.Path);a=p.parse_args()
 try:print(json.dumps(inspect(a.file),indent=2))
 except (OSError,PEError) as e:p.exit(2,str(e)+'\n')
