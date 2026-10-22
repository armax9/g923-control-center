// SPDX-License-Identifier: GPL-3.0-only
// Real HID -> private virtual DInput input only. No Output/Feature reports.
#include "hid_support.hpp"
#include <algorithm>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
struct Input {uint32_t steer=32768,gas=65535,brake=65535,clutch=65535,buttons=0,hat=8;};
static volatile sig_atomic_t stopping=0;
static Input current;
static void stop(int){stopping=1;}
static void update(IOHIDValueRef v){
 auto e=IOHIDValueGetElement(v);auto page=IOHIDElementGetUsagePage(e),usage=IOHIDElementGetUsage(e);auto raw=IOHIDValueGetIntegerValue(v);auto lo=IOHIDElementGetLogicalMin(e),hi=IOHIDElementGetLogicalMax(e);
 auto norm=hi>lo?(uint32_t)std::clamp((double(raw)-lo)*65535./double(hi-lo),0.,65535.):0;
 if(page==1){if(usage==0x30)current.steer=norm;else if(usage==0x32)current.gas=norm;else if(usage==0x35)current.brake=norm;else if(usage==0x31)current.clutch=norm;else if(usage==0x39)current.hat=raw>=0&&raw<8?uint32_t(raw):8;}
 if(page==9&&usage>=1&&usage<=25){auto mask=uint32_t(1)<<(usage-1);if(raw)current.buttons|=mask;else current.buttons&=~mask;}
}
static void callback(void*,IOReturn result,void*,IOHIDValueRef value){if(result==kIOReturnSuccess)update(value);}
int main(int argc,char**argv){
 if(argc!=5||std::strcmp(argv[1],"--map")||std::strcmp(argv[3],"--seconds")){std::cerr<<"Usage: g923-input --map NEW_PRIVATE_MAPPING --seconds 0..120 (0: until stopped)\n";return 2;}
 int seconds=0;try{size_t end=0;seconds=std::stoi(argv[4],&end);if(end!=std::strlen(argv[4]))return 2;}catch(...){return 2;}if(seconds<0||seconds>120)return 2;
 Hids h;IOHIDDeviceRef wheel=nullptr;
 for(auto d:h.devices)if(g923(d)&&prop(d,CFSTR(kIOHIDPrimaryUsagePageKey))==1&&prop(d,CFSTR(kIOHIDPrimaryUsageKey))==4){if(wheel){std::cerr<<"Multiple wheel collections; refuse ambiguity\n";return 3;}wheel=d;}
 if(!wheel||IOHIDDeviceOpen(wheel,0)!=kIOReturnSuccess){std::cerr<<"No readable G923 joystick\n";return 3;}
 int fd=open(argv[2],O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(fd<0){perror("private mapping create");IOHIDDeviceClose(wheel,0);return 1;}
 if(ftruncate(fd,8192)){close(fd);return 1;}auto memory=mmap(nullptr,8192,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);close(fd);if(memory==MAP_FAILED){IOHIDDeviceClose(wheel,0);return 1;}
 auto b=(uint8_t*)memory;std::memset(b,0,8192);auto put32=[&](size_t o,uint32_t v){__atomic_store_n((uint32_t*)(b+o),v,__ATOMIC_RELEASE);};
 put32(0,0x32424643);put32(4,2);put32(8,8192);uint32_t seq=0;
 auto publish=[&](bool connected){put32(64,++seq);put32(68,connected?1:0);auto now=std::chrono::system_clock::now().time_since_epoch();uint64_t ms=std::chrono::duration_cast<std::chrono::milliseconds>(now).count();__atomic_store_n((uint64_t*)(b+72),ms,__ATOMIC_RELEASE);put32(80,current.steer);put32(84,current.gas);put32(88,current.brake);put32(92,current.clutch);put32(96,current.buttons);put32(100,current.hat);put32(64,++seq);};
 auto elements=IOHIDDeviceCopyMatchingElements(wheel,nullptr,0);if(elements){for(CFIndex i=0;i<CFArrayGetCount(elements);++i){auto e=(IOHIDElementRef)CFArrayGetValueAtIndex(elements,i);if(IOHIDElementGetType(e)>kIOHIDElementTypeInput_ScanCodes)continue;IOHIDValueRef v=nullptr;if(IOHIDDeviceGetValue(wheel,e,&v)==kIOReturnSuccess&&v)update(v);}CFRelease(elements);}
 std::signal(SIGINT,stop);std::signal(SIGTERM,stop);IOHIDDeviceRegisterInputValueCallback(wheel,callback,nullptr);IOHIDDeviceScheduleWithRunLoop(wheel,CFRunLoopGetCurrent(),kCFRunLoopDefaultMode);
 std::cout<<"REAL G923 INPUT ONLY; no motor reports. ACTIVE\n"<<std::flush;
 auto end=std::chrono::steady_clock::now()+std::chrono::seconds(seconds);int tick=0;
 while(!stopping&&(seconds==0||std::chrono::steady_clock::now()<end)){CFRunLoopRunInMode(kCFRunLoopDefaultMode,.02,false);publish(true);if(++tick%25==0)std::cout<<"steer="<<current.steer<<" gas="<<current.gas<<" brake="<<current.brake<<" clutch="<<current.clutch<<" buttons="<<current.buttons<<std::endl;}
 publish(false);IOHIDDeviceUnscheduleFromRunLoop(wheel,CFRunLoopGetCurrent(),kCFRunLoopDefaultMode);IOHIDDeviceClose(wheel,0);munmap(memory,8192);return 0;
}
