// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <IOKit/hid/IOHIDManager.h>
#include <IOKit/hid/IOHIDKeys.h>
#include <vector>
#include <cstdio>
inline long prop(IOHIDDeviceRef d,CFStringRef k){long v=0;auto p=IOHIDDeviceGetProperty(d,k);if(p&&CFGetTypeID(p)==CFNumberGetTypeID())CFNumberGetValue((CFNumberRef)p,kCFNumberLongType,&v);return v;}
struct Hids{
 IOHIDManagerRef manager=IOHIDManagerCreate(kCFAllocatorDefault,0);
 std::vector<IOHIDDeviceRef> devices;
 Hids(){IOHIDManagerSetDeviceMatching(manager,nullptr);auto result=IOHIDManagerOpen(manager,0);std::fprintf(stderr,"IOHIDManagerOpen=0x%08x\n",result);auto s=IOHIDManagerCopyDevices(manager);if(s){std::vector<const void*> a(CFSetGetCount(s));CFSetGetValues(s,a.data());for(auto v:a){auto d=(IOHIDDeviceRef)v;if(prop(d,CFSTR(kIOHIDVendorIDKey))==0x046d){CFRetain(d);devices.push_back(d);}}CFRelease(s);}}
 ~Hids(){for(auto d:devices)CFRelease(d);IOHIDManagerClose(manager,0);CFRelease(manager);}
};
inline bool g923(IOHIDDeviceRef d){auto p=prop(d,CFSTR(kIOHIDProductIDKey));return p==0xc266||p==0xc267;}
