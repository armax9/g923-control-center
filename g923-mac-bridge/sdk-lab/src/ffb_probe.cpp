// SPDX-License-Identifier: GPL-3.0-only
#define DIRECTINPUT_VERSION 0x0800
#include <windows.h>
#include <dinput.h>
#include <cstdio>
#include <cstring>
static IDirectInput8A* di;
static IDirectInputDevice8A* wheel;
static int targets;
static unsigned effects;
static BOOL CALLBACK found(const DIDEVICEINSTANCEA* d,void*){
 if(d->guidProduct.Data1!=0xc266046d && d->guidProduct.Data1!=0xc267046d)return DIENUM_CONTINUE;
 ++targets;if(!wheel){auto hr=di->CreateDevice(d->guidInstance,&wheel,nullptr);std::printf("{\"event\":\"device_create\",\"hr\":\"%08lx\"}\n",(unsigned long)hr);}return DIENUM_CONTINUE;
}
static BOOL CALLBACK object(const DIDEVICEOBJECTINSTANCEA* o,void*){
 if(o->dwFlags&DIDOI_FFACTUATOR)std::printf("{\"event\":\"actuator_metadata\",\"offset\":%lu,\"flags\":%lu,\"max_force_newtons\":%lu,\"force_resolution\":%lu}\n",(unsigned long)o->dwOfs,(unsigned long)o->dwFlags,(unsigned long)o->dwFFMaxForce,(unsigned long)o->dwFFForceResolution);
 return DIENUM_CONTINUE;
}
static BOOL CALLBACK effect(const DIEFFECTINFOA* e,void*){++effects;std::printf("{\"event\":\"effect_supported\",\"guid_data1\":%lu,\"type\":%lu}\n",(unsigned long)e->guid.Data1,(unsigned long)e->dwEffType);return DIENUM_CONTINUE;}
int main(int argc,char**argv){
 setvbuf(stdout,nullptr,_IONBF,0);
 bool external=argc==3&&!std::strcmp(argv[1],"--factory");
 if(argc!=1 && !(argc==2&&!std::strcmp(argv[1],"--inventory"))&&!external)return 2;
 std::puts("{\"event\":\"ffb_inventory_begin\",\"effect_commands_sent\":false}");
 using Factory=HRESULT(WINAPI*)(HINSTANCE,DWORD,REFIID,void**,IUnknown*);
 Factory factory=DirectInput8Create;HMODULE module=nullptr;
 if(external){module=LoadLibraryA(argv[2]);if(!module)return 8;factory=(Factory)GetProcAddress(module,"DirectInput8Create");if(!factory)return 9;}
 auto hr=factory(GetModuleHandle(nullptr),DIRECTINPUT_VERSION,IID_IDirectInput8A,(void**)&di,nullptr);
 if(FAILED(hr))return 3;
 hr=di->EnumDevices(DI8DEVCLASS_GAMECTRL,found,nullptr,DIEDFL_ATTACHEDONLY);
 int rc=0;
 if(FAILED(hr)||targets!=1||!wheel)rc=4;
 else{
  DIDEVCAPS caps{};caps.dwSize=sizeof(caps);hr=wheel->GetCapabilities(&caps);
  std::printf("{\"event\":\"capabilities\",\"hr\":\"%08lx\",\"flags\":%lu,\"force_feedback\":%s,\"ff_sample_period_us\":%lu,\"ff_min_resolution\":%lu}\n",(unsigned long)hr,(unsigned long)caps.dwFlags,(caps.dwFlags&DIDC_FORCEFEEDBACK)?"true":"false",(unsigned long)caps.dwFFSamplePeriod,(unsigned long)caps.dwFFMinTimeResolution);
  if(FAILED(hr))rc=5;
  hr=wheel->SetDataFormat(&c_dfDIJoystick2);
  DIDEVICEOBJECTINSTANCEA steering{};steering.dwSize=sizeof(steering);
  auto info=wheel->GetObjectInfo(&steering,DIJOFS_X,DIPH_BYOFFSET);
  std::printf("{\"event\":\"steering_metadata\",\"hr\":\"%08lx\",\"offset\":%lu,\"flags\":%lu,\"max_force_newtons\":%lu,\"force_resolution\":%lu}\n",(unsigned long)info,(unsigned long)steering.dwOfs,(unsigned long)steering.dwFlags,(unsigned long)steering.dwFFMaxForce,(unsigned long)steering.dwFFForceResolution);
  hr=wheel->EnumObjects(object,nullptr,DIDFT_ALL);
  std::printf("{\"event\":\"enum_actuators\",\"hr\":\"%08lx\"}\n",(unsigned long)hr);
  if(FAILED(hr))rc=7;
  hr=wheel->EnumEffects(effect,nullptr,DIEFT_ALL);
  std::printf("{\"event\":\"enum_effects\",\"hr\":\"%08lx\",\"effect_count\":%u}\n",(unsigned long)hr,effects);
  if(FAILED(hr))rc=6;
 }
 if(wheel)wheel->Release();di->Release();if(module)FreeLibrary(module);return rc;
}
