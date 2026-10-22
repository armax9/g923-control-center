// SPDX-License-Identifier: MIT
#define DIRECTINPUT_VERSION 0x0800
#include <windows.h>
#include <mmsystem.h>
#include <dinput.h>
#include <cstdio>
static BOOL CALLBACK enumerate(const DIDEVICEINSTANCEW*,void*ctx){++*(int*)ctx;return DIENUM_STOP;}
int wmain(int argc,wchar_t**argv){if(argc!=2)return 2;
 auto before=timeGetTime();timeBeginPeriod(1);Sleep(10);timeEndPeriod(1);auto after=timeGetTime();if(after-before<5||after-before>30000)return 3;
 auto m=LoadLibraryW(argv[1]);if(!m)return 4;auto create=(HRESULT(WINAPI*)(HINSTANCE,DWORD,const IID&,void**,IUnknown*))GetProcAddress(m,"DirectInput8Create");if(!create)return 5;
 IDirectInput8W*di=nullptr;HRESULT h=create(GetModuleHandleW(nullptr),0x800,IID_IDirectInput8W,(void**)&di,nullptr);if(FAILED(h)||!di)return 6;
 if(create(GetModuleHandleW(nullptr),0x800,IID_IDirectInput8W,nullptr,nullptr)!=E_POINTER)return 10;
 bool bridged=GetModuleHandleW(L"g923_bridge.dll")!=nullptr;int count=0;if(bridged){h=di->EnumDevices(DI8DEVCLASS_GAMECTRL,enumerate,&count,0);if(FAILED(h)||count!=1)return 7;}di->Release();
 auto calls=(ULONG(*)())GetProcAddress(m,"FixtureOriginalCalls");auto releases=(ULONG(*)())GetProcAddress(m,"FixtureOriginalReleases");if(!calls||!releases)return 8;
 printf("{\"winmm_timing_ok\":true,\"virtual_bridge\":%s,\"controllers\":%d,\"original_calls\":%lu,\"original_releases\":%lu,\"hardware_used\":false}\n",bridged?"true":"false",count,calls(),releases());return calls()==2&&releases()==1?0:9;}
