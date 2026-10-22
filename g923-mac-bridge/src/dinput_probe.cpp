// SPDX-License-Identifier: GPL-3.0-only
#define DIRECTINPUT_VERSION 0x0800
#include <windows.h>
#include <dinput.h>
#include <cstdio>
#include <cstring>
static IDirectInput8A* input=nullptr;
static int wheels=0,working=0;
static const char* stopPath=nullptr;
static BOOL CALLBACK object(const DIDEVICEOBJECTINSTANCEA* o,void*){std::printf(" object offset=%lu type=%08lx flags=%08lx name=%s\n",(unsigned long)o->dwOfs,(unsigned long)o->dwType,(unsigned long)o->dwFlags,o->tszName);return DIENUM_CONTINUE;}
static BOOL CALLBACK device(const DIDEVICEINSTANCEA* i,void*){
 std::printf("device name=%s product=%08lx type=%08lx\n",i->tszInstanceName,(unsigned long)i->guidProduct.Data1,(unsigned long)i->dwDevType);
 if((i->guidProduct.Data1&65535)!=0x046d)return DIENUM_CONTINUE;
 auto pid=i->guidProduct.Data1>>16;if(pid!=0xc266&&pid!=0xc267&&pid!=0xc24f&&pid!=0xc294)return DIENUM_CONTINUE;
 ++wheels;IDirectInputDevice8A* d=nullptr;auto r=input->CreateDevice(i->guidInstance,&d,nullptr);std::printf(" CreateDevice=%08lx\n",(unsigned long)r);if(FAILED(r))return DIENUM_CONTINUE;
 DIDEVCAPS caps{};caps.dwSize=sizeof(caps);r=d->GetCapabilities(&caps);std::printf(" caps=%08lx axes=%lu buttons=%lu flags=%08lx\n",(unsigned long)r,(unsigned long)caps.dwAxes,(unsigned long)caps.dwButtons,(unsigned long)caps.dwFlags);
 d->EnumObjects(object,nullptr,DIDFT_ALL);
 r=d->SetDataFormat(&c_dfDIJoystick2);std::printf(" SetDataFormat=%08lx\n",(unsigned long)r);
 r=d->SetCooperativeLevel(GetDesktopWindow(),DISCL_NONEXCLUSIVE|DISCL_BACKGROUND);std::printf(" CooperativeLevel=%08lx\n",(unsigned long)r);
 r=d->Acquire();std::printf(" Acquire=%08lx\n",(unsigned long)r);
 bool ok=false;for(int n=0;stopPath || n<100;++n){if(stopPath && GetFileAttributesA(stopPath)!=INVALID_FILE_ATTRIBUTES)break;auto poll=d->Poll();DIJOYSTATE2 state{};r=d->GetDeviceState(sizeof(state),&state);if(SUCCEEDED(r)){ok=true;DWORD buttons=0;for(int bit=0;bit<25;++bit)if(state.rgbButtons[bit]&0x80)buttons|=1u<<bit;std::printf(" state x=%ld y=%ld z=%ld rx=%ld ry=%ld rz=%ld slider0=%ld slider1=%ld pov=%lu buttons=%08lx\n",state.lX,state.lY,state.lZ,state.lRx,state.lRy,state.lRz,state.rglSlider[0],state.rglSlider[1],(unsigned long)state.rgdwPOV[0],(unsigned long)buttons);}else{std::printf(" Poll=%08lx GetDeviceState=%08lx\n",(unsigned long)poll,(unsigned long)r);d->Acquire();}Sleep(100);}
 if(ok)++working;d->Unacquire();d->Release();return DIENUM_CONTINUE;
}
int main(int argc,char**argv){setvbuf(stdout,nullptr,_IONBF,0);if(argc==3 && !std::strcmp(argv[1],"--until-stop"))stopPath=argv[2];else if(argc!=1)return 2;auto r=DirectInput8Create(GetModuleHandle(nullptr),DIRECTINPUT_VERSION,IID_IDirectInput8A,(void**)&input,nullptr);std::printf("DirectInput8Create=%08lx\n",(unsigned long)r);if(FAILED(r))return 1;r=input->EnumDevices(DI8DEVCLASS_GAMECTRL,device,nullptr,DIEDFL_ATTACHEDONLY);std::printf("EnumDevices=%08lx wheels=%d readable=%d (readable does not prove moving axes)\n",(unsigned long)r,wheels,working);input->Release();return FAILED(r)?1:working?0:3;}
