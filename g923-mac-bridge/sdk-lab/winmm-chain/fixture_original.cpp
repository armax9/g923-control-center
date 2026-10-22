// SPDX-License-Identifier: MIT
#include <windows.h>
static ULONG calls,releases;
struct Object {void**vtable;};
static HRESULT WINAPI query(Object*,const IID&,void**){return E_NOINTERFACE;}
static ULONG WINAPI add(Object*){return 1;}
static ULONG WINAPI release(Object*){++releases;return 0;}
static void*vt[]={reinterpret_cast<void*>(query),reinterpret_cast<void*>(add),reinterpret_cast<void*>(release)};static Object object{vt};
extern "C" __declspec(dllexport) HRESULT WINAPI DirectInput8Create(HINSTANCE,DWORD,const IID&,void**out,IUnknown*){++calls;if(!out)return E_POINTER;*out=&object;return S_OK;}
extern "C" __declspec(dllexport) ULONG FixtureOriginalCalls(){return calls;}
extern "C" __declspec(dllexport) ULONG FixtureOriginalReleases(){return releases;}
