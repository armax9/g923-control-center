// SPDX-License-Identifier: GPL-3.0-only
// Read-only SDK routing checks. No SDK initialization, Acquire, or force calls.
#define DIRECTINPUT_VERSION 0x0800
#include <windows.h>
#include <dinput.h>
#include <cstdio>
#include <cwchar>
static IDirectInput8A* di;
static IDirectInputDevice8A* wheel;
static BOOL CALLBACK found(const DIDEVICEINSTANCEA* item,void*) {
 if(item->guidProduct.Data1==0xc266046d&&!wheel)di->CreateDevice(item->guidInstance,&wheel,nullptr);
 return DIENUM_CONTINUE;
}
int wmain(int argc,wchar_t** argv) {
 if(argc!=2)return 2;
 bool physical=!std::wcscmp(argv[1],L"--physical-read-only");
 if(!physical&&std::wcscmp(argv[1],L"--virtual-only"))return 2;
 wchar_t exe[MAX_PATH]{},dll[MAX_PATH]{};
 GetModuleFileNameW(nullptr,exe,MAX_PATH);GetModuleFileNameW(GetModuleHandleW(L"dinput8.dll"),dll,MAX_PATH);
 auto a=std::wcsrchr(exe,L'\\'),b=std::wcsrchr(dll,L'\\');
 if(!a||!b)return 3;a[1]=b[1]=0;
 if(!physical&&_wcsicmp(exe,dll))return 4;
 HKEY key{};LONG registry=RegOpenKeyExW(HKEY_LOCAL_MACHINE,L"SOFTWARE\\Classes\\CLSID\\{e8dfb59f-141f-40e4-8dd4-5526ead25a4c}",0,KEY_READ|KEY_WOW64_64KEY,&key);
 DWORD type=0,bytes=0;LONG value=registry;
 if(!registry){value=RegQueryValueExW(key,nullptr,nullptr,&type,nullptr,&bytes);RegCloseKey(key);}
 std::printf("{\"event\":\"sdk_registration\",\"open_status\":%ld,\"value_status\":%ld,\"type\":%lu,\"bytes\":%lu}\n",registry,value,type,bytes);
 auto hr=DirectInput8Create(GetModuleHandleW(nullptr),DIRECTINPUT_VERSION,IID_IDirectInput8A,(void**)&di,nullptr);
 if(FAILED(hr))return 5;
 hr=di->EnumDevices(DI8DEVCLASS_GAMECTRL,found,nullptr,DIEDFL_ATTACHEDONLY);
 if(FAILED(hr)||!wheel){di->Release();return 6;}
 DIPROPDWORD vp{};vp.diph={sizeof(vp),sizeof(vp.diph),0,DIPH_DEVICE};
 hr=wheel->GetProperty(DIPROP_VIDPID,&vp.diph);
 std::printf("{\"event\":\"vidpid\",\"hr\":\"%08lx\",\"value\":\"%08lx\"}\n",(unsigned long)hr,vp.dwData);
 DIPROPGUIDANDPATH path{};path.diph={sizeof(path),sizeof(path.diph),0,DIPH_DEVICE};
 hr=wheel->GetProperty(DIPROP_GUIDANDPATH,&path.diph);
 std::printf("{\"event\":\"guid_and_path\",\"hr\":\"%08lx\",\"path_nonempty\":%s}\n",(unsigned long)hr,path.wszPath[0]?"true":"false");
 if(SUCCEEDED(hr)){
  char text[2048]{};WideCharToMultiByte(CP_UTF8,0,path.wszPath,-1,text,sizeof(text),nullptr,nullptr);
  std::fputs("{\"event\":\"physical_path\",\"value\":\"",stdout);
  for(auto c:text){if(!c)break;if(c=='\\'||c=='"')std::putchar('\\');if((unsigned char)c>=32)std::putchar(c);}
  std::puts("\"}");
 }
 wheel->Release();di->Release();
 std::puts("{\"event\":\"route_probe_finished\",\"sdk_loaded\":false,\"sdk_initialized\":false,\"force_calls\":0}");
 return 0;
}
