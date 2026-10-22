import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from native_connection import assess

class NativeConnection(unittest.TestCase):
    expected={'x86_64-unix/winebus.so':'patched-unix','x86_64-windows/winebus.sys':'patched-pe'}
    def inspect(self,paths,hashes):
        return assess('/bottles/Games',self.expected,[(12,r'C:\windows\system32\winedevice.exe')],lambda _:paths,lambda p:hashes[p.name])
    def test_stock_live_modules_do_not_pass_despite_valid_files_on_disk(self):
        result=self.inspect(['/bottles/Games/drive_c/windows/system32','/CrossOver/lib/winebus.so','/CrossOver/lib/winebus.sys'],{'winebus.so':'stock-unix','winebus.sys':'stock-pe'})
        self.assertEqual(result['state'],'restart_required')
    def test_reviewed_pair_loaded_for_selected_bottle(self):
        result=self.inspect(['/bottles/Games/drive_c/windows','/private-runtime/winebus.so','/private-runtime/winebus.sys'],{'winebus.so':'patched-unix','winebus.sys':'patched-pe'})
        self.assertEqual(result['state'],'ready')
        self.assertIn('separately',result['detail'])
    def test_other_bottle_is_not_evidence(self):
        result=self.inspect(['/bottles/Other/drive_c/windows','/private-runtime/winebus.so','/private-runtime/winebus.sys'],{'winebus.so':'patched-unix','winebus.sys':'patched-pe'})
        self.assertEqual(result['state'],'waiting')
    def test_half_the_pair_is_not_ready(self):
        result=self.inspect(['/bottles/Games','/private-runtime/winebus.so'],{'winebus.so':'patched-unix'})
        self.assertEqual(result['state'],'restart_required')
    def test_no_device_process_remains_waiting(self):
        self.assertEqual(assess('/bottles/Games',self.expected,[],lambda _:[])['state'],'waiting')

if __name__=='__main__':unittest.main()
