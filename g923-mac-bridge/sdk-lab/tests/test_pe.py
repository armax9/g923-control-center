# SPDX-License-Identifier: GPL-3.0-only
import pathlib,sys,unittest,struct,tempfile
TOOLS=pathlib.Path(__file__).resolve().parents[1]/'tools';sys.path.insert(0,str(TOOLS))
from pe_inventory import PE,PEError,inspect
from lab import registry_text,winpath,sdk_inventory,usable
ROOT=pathlib.Path(__file__).resolve().parents[2]
class InventoryTests(unittest.TestCase):
 def test_built_fixture(self):
  p=ROOT/'build/sdk-lab/fixture-not-logitech.dll';r=inspect(p)
  self.assertTrue(r['x64']);self.assertFalse(r['certificate_table_present'])
  names={e['name'] for e in r['exports']};self.assertIn('g923_fixture_probe',names);self.assertNotIn('logiTrueForceAvailable',names)
  self.assertTrue(any(d['dll'].lower()=='kernel32.dll' for d in r['imports']))
 def test_built_probe(self):
  r=inspect(ROOT/'build/sdk-lab/sdk-probe.exe');imports={d['dll'].lower() for d in r['imports']}
  self.assertTrue({'setupapi.dll','hid.dll','wintrust.dll'}<=imports)
 def test_truncated_and_bad_images(self):
  data=(ROOT/'build/sdk-lab/fixture-not-logitech.dll').read_bytes()
  for n in [0,1,2,40,64,128,256,len(data)//2]:
   with self.subTest(n=n),self.assertRaises(PEError):PE(data[:n]).report()
  b=bytearray(data);struct.pack_into('<I',b,0x3c,0xfffffff0)
  with self.assertRaises(PEError):PE(b)
 def test_zero_filled_rva_and_bad_export_count(self):
  pe=PE((ROOT/'build/sdk-lab/fixture-not-logitech.dll').read_bytes())
  with self.assertRaises(PEError):pe.rva(0xffffffff)
  data=bytearray(pe.data);off=pe.rva(pe.directory(0)[0]);struct.pack_into('<I',data,off+24,0x7fffffff)
  with self.assertRaises(PEError):PE(data).exports()
 def test_signature_presence_not_trust(self):
  data=bytearray((ROOT/'build/sdk-lab/fixture-not-logitech.dll').read_bytes());pe=PE(data)
  nt=pe.u32(0x3c);cert=len(data);data.extend(b'not-a-valid-cert');struct.pack_into('<II',data,nt+24+112+4*8,cert,16)
  report=PE(data).report();self.assertTrue(report['certificate_table_present']);self.assertIn('not signature',report['certificate_note'])
 def test_reg_escaping_paths_with_spaces(self):
  path='C:\\Program Files\\Logi\\Trueforce\\1_3_11\\trueforce_sdk_x64.dll'
  text=registry_text(path,None)
  self.assertIn('C:\\\\Program Files',text);self.assertEqual(text.count('@='),2);self.assertNotIn('ServerBinary',text)
  self.assertIn('ServerBinary',registry_text(None,'C:\\wheel.dll'))
  with self.assertRaises(ValueError):registry_text('C:\\bad\nfile',None)
 def test_test_double_cannot_be_mistaken_for_sdk(self):
  r=inspect(ROOT/'build/sdk-lab/fixture-not-logitech.dll')
  self.assertFalse(usable({'kind':'trueforce','pe':r}))
 def test_missing_sdk_and_path(self):
  with tempfile.TemporaryDirectory() as tmp:self.assertEqual(sdk_inventory([pathlib.Path(tmp)])['candidates'],[])
  self.assertEqual(winpath('/tmp/test space.dll'), 'Z:'+str(pathlib.Path('/tmp/test space.dll').resolve()).replace('/', '\\'))
if __name__=='__main__':unittest.main()
