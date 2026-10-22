// SPDX-License-Identifier: GPL-2.0-only
// Simulated SCS host: validates the real Windows plugin without a game/HID.
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cassert>
struct Value{uint32_t type,pad;alignas(8) unsigned char storage[40];};
struct Named{const char*name;uint32_t index,pad;Value value;};
using Event=void(*)(uint32_t,const void*,void*);
using Channel=void(*)(const char*,uint32_t,const Value*,void*);
static Event events[6];static Channel channels[5];static const char*names[5];static int n;
static int eventReg(uint32_t e,Event cb,void*){if(e>=6)return -1;events[e]=cb;return 0;}
static int channelReg(const char*name,uint32_t,uint32_t,uint32_t,Channel cb,void*){if(n>=5)return -1;names[n]=name;channels[n++]=cb;return 0;}
static void logLine(int,const char*s){std::puts(s);}
struct Init {const char*game_name;const char*game_id;uint32_t version,pad;decltype(&logLine) log;decltype(&eventReg) event;void*unregEvent;decltype(&channelReg) channel;void*unregChannel;};
static_assert(sizeof(Init)==64&&sizeof(Value)==48&&sizeof(Named)==64);
int wmain(int argc,wchar_t**argv){if(argc!=2)return 2;auto dll=LoadLibraryW(argv[1]);if(!dll)return 3;auto init=(int(*)(uint32_t,const Init*))GetProcAddress(dll,"scs_telemetry_init");auto stop=(void(*)())GetProcAddress(dll,"scs_telemetry_shutdown");if(!init||!stop)return 4;Init p{"fixture","eut2",0,0,logLine,eventReg,nullptr,channelReg,nullptr};if(init(0x10001,&p)!=0||n!=5)return 5;
 Named attrs[2]{};attrs[0].name="rpm.limit";attrs[0].value.type=5;float limit=2500.;memcpy(attrs[0].value.storage,&limit,4);struct Config{const char*id;Named*attrs;}config{"truck",attrs};events[5](5,&config,nullptr);
 for(int i=0;i<n;i++){Value value{};value.type=strstr(names[i],"gear")?2:5;float f=strstr(names[i],"rpm")?1200.f:strstr(names[i],"throttle")?.5f:0.f;memcpy(value.storage,&f,4);channels[i](names[i],0,&value,nullptr);}
 events[4](4,nullptr,nullptr);for(int i=0;i<4;i++){events[2](2,nullptr,nullptr);Sleep(40);}events[3](3,nullptr,nullptr);stop();FreeLibrary(dll);std::puts("fixture_callbacks_ok");return 0;}
