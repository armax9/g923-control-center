// SPDX-License-Identifier: GPL-3.0-only
// Steamworks client readiness only; never starts a game or a wheel SDK.
#include <windows.h>
#include <cstdio>
int wmain(int argc,wchar_t** argv){
 if(argc!=2)return 2;
 auto dll=LoadLibraryExW(argv[1],nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
 if(!dll)return 4;
 auto running=(bool(*)())GetProcAddress(dll,"SteamAPI_IsSteamRunning");
 auto init=(bool(*)())GetProcAddress(dll,"SteamAPI_Init");
 auto shutdown=(void(*)())GetProcAddress(dll,"SteamAPI_Shutdown");
 if(!running||!init||!shutdown){FreeLibrary(dll);return 5;}
 bool live=running(),ready=live&&init();if(ready)shutdown();
 std::printf("{\"event\":\"steam_readiness\",\"client_running\":%s,\"initialized\":%s,\"game_launched\":false}\n",live?"true":"false",ready?"true":"false");
 FreeLibrary(dll);return ready?0:3;
}
