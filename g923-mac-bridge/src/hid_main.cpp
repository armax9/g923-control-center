// SPDX-License-Identifier: GPL-3.0-only
#include "hid_support.hpp"
#include <IOKit/hidsystem/IOHIDLib.h>
#include <cstring>
#include <chrono>
static void value(void*,IOReturn result,void*,IOHIDValueRef v){
 auto e=IOHIDValueGetElement(v);auto lo=IOHIDElementGetLogicalMin(e),hi=IOHIDElementGetLogicalMax(e);auto raw=IOHIDValueGetIntegerValue(v);
 std::printf("value result=0x%x cookie=%u page=0x%x usage=0x%x raw=%ld min=%ld max=%ld normalized=%.6f\n",result,(unsigned)IOHIDElementGetCookie(e),IOHIDElementGetUsagePage(e),IOHIDElementGetUsage(e),(long)raw,(long)lo,(long)hi,hi>lo?double(raw-lo)/double(hi-lo):0.0);std::fflush(stdout);
}
int main(int argc,char**argv){
 bool watch=argc==2&&std::strcmp(argv[1],"--watch")==0;
 if(argc>1&&!watch){std::fprintf(stderr,"Usage: g923-hid [--watch] (watch lasts 30 seconds)\n");return 2;}
 std::printf("InputMonitoring=%d (0=granted,1=denied,2=unknown)\n",IOHIDCheckAccess(kIOHIDRequestTypeListenEvent));Hids h;int count=0;
 for(auto d:h.devices){std::printf("vid=046d pid=%04lx page=%04lx usage=%04lx location=%08lx outputMax=%ld target=%d\n",prop(d,CFSTR(kIOHIDProductIDKey)),prop(d,CFSTR(kIOHIDPrimaryUsagePageKey)),prop(d,CFSTR(kIOHIDPrimaryUsageKey)),prop(d,CFSTR(kIOHIDLocationIDKey)),prop(d,CFSTR(kIOHIDMaxOutputReportSizeKey)),g923(d));if(!g923(d))continue;++count;
 auto desc=IOHIDDeviceGetProperty(d,CFSTR(kIOHIDReportDescriptorKey));if(desc&&CFGetTypeID(desc)==CFDataGetTypeID()){auto data=(CFDataRef)desc;std::printf("descriptor=");for(CFIndex i=0;i<CFDataGetLength(data);++i)std::printf("%02x",CFDataGetBytePtr(data)[i]);std::puts("");}
 auto elements=IOHIDDeviceCopyMatchingElements(d,nullptr,0);if(elements){for(CFIndex i=0;i<CFArrayGetCount(elements);++i){auto e=(IOHIDElementRef)CFArrayGetValueAtIndex(elements,i);std::printf("element cookie=%u type=%u page=%x usage=%x reportID=%u bits=%u min=%ld max=%ld\n",(unsigned)IOHIDElementGetCookie(e),IOHIDElementGetType(e),IOHIDElementGetUsagePage(e),IOHIDElementGetUsage(e),IOHIDElementGetReportID(e),IOHIDElementGetReportSize(e),(long)IOHIDElementGetLogicalMin(e),(long)IOHIDElementGetLogicalMax(e));}CFRelease(elements);}
 if(watch){auto r=IOHIDDeviceOpen(d,0);std::printf("deviceOpen=0x%x\n",r);if(r==kIOReturnSuccess){IOHIDDeviceRegisterInputValueCallback(d,value,nullptr);IOHIDDeviceScheduleWithRunLoop(d,CFRunLoopGetCurrent(),kCFRunLoopDefaultMode);}}}
 if(!count){std::fprintf(stderr,"No G923 PS HID found. Check USB/power/mode; see docs/TESTING.md\n");return 3;}
 if(watch){auto end=std::chrono::steady_clock::now()+std::chrono::seconds(30);while(std::chrono::steady_clock::now()<end)CFRunLoopRunInMode(kCFRunLoopDefaultMode,.1,false);for(auto d:h.devices)if(g923(d)){IOHIDDeviceUnscheduleFromRunLoop(d,CFRunLoopGetCurrent(),kCFRunLoopDefaultMode);IOHIDDeviceClose(d,0);}}
 return 0;
}
