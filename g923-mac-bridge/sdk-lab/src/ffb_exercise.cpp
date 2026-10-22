// SPDX-License-Identifier: GPL-3.0-only
// Runs only with the adjacent project virtual DLL, never with builtin DInput.
#define DIRECTINPUT_VERSION 0x0800
#include <windows.h>
#include <dinput.h>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <cmath>
static IDirectInput8A* di;static IDirectInputDevice8A* wheel;static unsigned count;
static BOOL CALLBACK found(const DIDEVICEINSTANCEA* d,void*){if(d->guidProduct.Data1!=0xc266046d)return DIENUM_CONTINUE;++count;if(!wheel)di->CreateDevice(d->guidInstance,&wheel,nullptr);return DIENUM_CONTINUE;}
static bool ok(const char* event,HRESULT hr){std::printf("{\"event\":\"%s\",\"hr\":\"%08lx\",\"tick_ms\":%llu}\n",event,(unsigned long)hr,(unsigned long long)GetTickCount64());return SUCCEEDED(hr);}
int wmain(int argc,wchar_t**argv){
 setvbuf(stdout,nullptr,_IONBF,0);
 const wchar_t* mode=argc>1?argv[1]:L"";
 bool spring=!std::wcscmp(mode,L"--spring-software-only")||!std::wcscmp(mode,L"--spring-exercise");
 bool damper=!std::wcscmp(mode,L"--damper-software-only")||!std::wcscmp(mode,L"--damper-exercise");
 bool friction=!std::wcscmp(mode,L"--friction-software-only")||!std::wcscmp(mode,L"--friction-exercise");
 bool resistance=damper||friction;
 bool software=argc==2&&(!std::wcscmp(mode,L"--software-only")||!std::wcscmp(mode,L"--spring-software-only")||!std::wcscmp(mode,L"--damper-software-only")||!std::wcscmp(mode,L"--friction-software-only"));
 bool comparison=argc==7&&!std::wcscmp(argv[5],L"--enable-file")&&resistance;
 bool physical=(argc==5||comparison)&&(!std::wcscmp(mode,L"--exercise")||!std::wcscmp(mode,L"--spring-exercise")||!std::wcscmp(mode,L"--damper-exercise")||!std::wcscmp(mode,L"--friction-exercise"))&&!std::wcscmp(argv[2],L"--user-ready")&&!std::wcscmp(argv[3],L"--stop-file");
 if(!software&&!physical)return 2;
 if(physical && GetFileAttributesW(argv[4])!=INVALID_FILE_ATTRIBUTES)return 3;
 if(comparison && GetFileAttributesW(argv[6])!=INVALID_FILE_ATTRIBUTES)return 3;
 wchar_t exe[MAX_PATH]{},dll[MAX_PATH]{};GetModuleFileNameW(nullptr,exe,MAX_PATH);auto sep=std::wcsrchr(exe,L'\\');if(!sep)return 3;sep[1]=0;
 auto module=GetModuleHandleW(L"dinput8.dll");GetModuleFileNameW(module,dll,MAX_PATH);
 auto tail=std::wcsrchr(dll,L'\\');if(!tail)return 3;tail[1]=0;
 if(_wcsicmp(exe,dll)){std::puts("{\"event\":\"refuse_nonadjacent_dinput\"}");return 4;}
 if(!ok("create_dinput",DirectInput8Create(GetModuleHandle(nullptr),DIRECTINPUT_VERSION,IID_IDirectInput8A,(void**)&di,nullptr)))return 5;
 IDirectInputEffect* effect=nullptr;int rc=0;
 do{
  if(!ok("enumerate",di->EnumDevices(DI8DEVCLASS_GAMECTRL,found,nullptr,DIEDFL_ATTACHEDONLY))||count!=1||!wheel){rc=6;break;}
  DIDEVCAPS caps{};caps.dwSize=sizeof(caps);if(!ok("capabilities",wheel->GetCapabilities(&caps))||!(caps.dwFlags&DIDC_FORCEFEEDBACK)){rc=7;break;}
  if(!ok("format",wheel->SetDataFormat(&c_dfDIJoystick2))||!ok("cooperative",wheel->SetCooperativeLevel(GetDesktopWindow(),DISCL_BACKGROUND|DISCL_EXCLUSIVE))||!ok("acquire",wheel->Acquire())){rc=8;break;}
  DICONDITION condition{0,10000,10000,4000,4000,0};
  DIPERIODIC periodic{8000,0,0,200000};DWORD axis=DIJOFS_X;LONG direction=10000;
  DIENVELOPE envelope{sizeof(DIENVELOPE),0,50000,0,50000};
  DIEFFECT p{};p.dwSize=sizeof(p);p.dwFlags=DIEFF_CARTESIAN|DIEFF_OBJECTOFFSETS;p.dwDuration=400000;p.dwGain=10000;p.dwTriggerButton=DIEB_NOTRIGGER;p.cAxes=1;p.rgdwAxes=&axis;p.rglDirection=&direction;p.lpEnvelope=&envelope;p.cbTypeSpecificParams=sizeof(periodic);p.lpvTypeSpecificParams=&periodic;
  if(spring||resistance){p.dwDuration=spring?1000000:(physical?INFINITE:400000);p.lpEnvelope=nullptr;p.cbTypeSpecificParams=sizeof(condition);p.lpvTypeSpecificParams=&condition;}
  const GUID& effectGuid=spring?GUID_Spring:damper?GUID_Damper:friction?GUID_Friction:GUID_Sine;
  if(!ok("create_effect",wheel->CreateEffect(effectGuid,&p,&effect,nullptr))||!effect){rc=9;break;}
  bool enabled=!comparison;
  if(enabled&&!ok("start_effect",effect->Start(1,0))){rc=10;break;}
  if(comparison)std::puts("{\"event\":\"comparison_phase\",\"enabled\":false}");
  std::printf("{\"event\":\"exercise_active\",\"effect\":\"%s\",\"until_stop\":%s}\n",spring?"spring":damper?"damper":friction?"friction":"sine",physical&&resistance?"true":"false");
  auto begin=GetTickCount64();
  while((resistance&&physical)||GetTickCount64()-begin<(spring?1050:450)){
   if(spring){
    auto elapsed=GetTickCount64()-begin;
    condition.lOffset=elapsed<1000?LONG(std::lround(4000.*std::sin(2.*3.14159265358979323846*double(elapsed)/1000.))):0;
    if(!ok("update_spring",effect->SetParameters(&p,DIEP_TYPESPECIFICPARAMS))){rc=15;break;}
   }
   DIJOYSTATE2 state{};
   if(!ok("poll",wheel->Poll())||!ok("read_input",wheel->GetDeviceState(sizeof(state),&state))){rc=11;break;}
   if(physical){bool stop=GetFileAttributesW(argv[4])!=INVALID_FILE_ATTRIBUTES;for(auto b:state.rgbButtons)stop|=(b&0x80)!=0;if(stop){std::puts("{\"event\":\"stop_requested\"}");break;}}
   if(comparison){
    bool requested=GetFileAttributesW(argv[6])!=INVALID_FILE_ATTRIBUTES;
    if(requested!=enabled){
     if(!ok(requested?"comparison_start":"comparison_stop",requested?effect->Start(1,0):effect->Stop())){rc=16;break;}
     enabled=requested;std::printf("{\"event\":\"comparison_phase\",\"enabled\":%s}\n",enabled?"true":"false");
    }
   }
   Sleep(10);
  }
 }while(false);
 if(effect){if(!ok("stop_effect",effect->Stop()))rc=13;effect->Release();}
 if(wheel){if(!ok("reset_effects",wheel->SendForceFeedbackCommand(DISFFC_RESET)))rc=14;wheel->Unacquire();wheel->Release();}di->Release();
 std::printf("{\"event\":\"exercise_finished\",\"exit_code\":%d,\"software_only\":%s}\n",rc,software?"true":"false");return rc;
}
