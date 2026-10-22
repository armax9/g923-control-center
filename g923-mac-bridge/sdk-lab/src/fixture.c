// SPDX-License-Identifier: GPL-3.0-only
// TEST DOUBLE ONLY: not Logitech software, no HID/SDK functionality.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
__declspec(dllexport) int g923_fixture_probe(void){return 923;}
__declspec(dllexport) int logiTrueForceSetStreamTF(void){return -1;}
__declspec(dllexport) int logiTrueForceSetTorqueKF(void){return -1;}
__declspec(dllexport) int logiWheelOpenByDirectInputA(void){return -1;}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID unused){(void)instance;(void)unused;if(reason==DLL_PROCESS_ATTACH){wchar_t path[32768];DWORD n=GetEnvironmentVariableW(L"G923_FIXTURE_SENTINEL",path,32768);if(n>0&&n<32768){HANDLE f=CreateFileW(path,GENERIC_WRITE,0,0,CREATE_ALWAYS,0,0);if(f!=INVALID_HANDLE_VALUE){DWORD wrote;const char s[]="FIXTURE_ONLY_DLLMAIN_EXECUTED\n";WriteFile(f,s,sizeof(s)-1,&wrote,0);CloseHandle(f);}}}return TRUE;}

#ifdef G923_LIFECYCLE_FIXTURE
static int sdk_opened=0;
__declspec(dllexport) void dllOpen(void){sdk_opened=1;}
__declspec(dllexport) void dllClose(void){sdk_opened=0;}
__declspec(dllexport) int logiTrueForceAvailable(unsigned char* out){if(!out)return (int)0x80000001;if(!sdk_opened)return (int)0x8000000c;*out=0;return 0;}
#endif
