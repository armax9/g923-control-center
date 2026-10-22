// SPDX-License-Identifier: GPL-3.0-only
// Test double only. No Steam dependency, no game launch, no network.
#include <windows.h>
#define API extern "C" __declspec(dllexport)
API bool SteamAPI_IsSteamRunning(){wchar_t value[4]{};return GetEnvironmentVariableW(L"G923_STEAM_FIXTURE_READY",value,4)==1&&value[0]=='1';}
API bool SteamAPI_Init(){return SteamAPI_IsSteamRunning();}
API void SteamAPI_Shutdown(){}
