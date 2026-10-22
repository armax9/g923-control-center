// SPDX-License-Identifier: GPL-3.0-only
// Diagnostic process-local interposer. Does not alter report descriptors.
// Admits only the real G923 TRUEFORCE collection past Wine's IOHID gate.
// All G923 SetReport calls are denied; this is NOT a haptic transport.
#include <IOKit/hid/IOHIDLib.h>
#include <IOKit/hid/IOHIDKeys.h>
#include <stdio.h>
#include <unistd.h>
__attribute__((constructor)) static void loaded(void){fprintf(stderr,"G923_ADMISSION: loaded pid=%d; writes blocked\n",getpid());}
static long number(IOHIDDeviceRef d,CFStringRef key){long n=0;CFTypeRef v=IOHIDDeviceGetProperty(d,key);if(v&&CFGetTypeID(v)==CFNumberGetTypeID())CFNumberGetValue(v,kCFNumberLongType,&n);return n;}
static int wheel(IOHIDDeviceRef d){long pid=number(d,CFSTR(kIOHIDProductIDKey));return number(d,CFSTR(kIOHIDVendorIDKey))==0x046d&&(pid==0xc266||pid==0xc267);}
static CFTypeRef admission(IOHIDDeviceRef d,CFStringRef key){
 if((CFEqual(key,CFSTR(kIOHIDPrimaryUsagePageKey))||CFEqual(key,CFSTR(kIOHIDPrimaryUsageKey)))&&wheel(d)&&number(d,CFSTR(kIOHIDPrimaryUsagePageKey))==0xfffd&&number(d,CFSTR(kIOHIDPrimaryUsageKey))==0xfd01){
  static CFNumberRef page,usage;if(!page){int p=1,u=4;page=CFNumberCreate(NULL,kCFNumberIntType,&p);usage=CFNumberCreate(NULL,kCFNumberIntType,&u);}
  fprintf(stderr,"G923_ADMISSION: vendor collection admitted; descriptor unchanged; writes blocked\n");
  return CFEqual(key,CFSTR(kIOHIDPrimaryUsagePageKey))?page:usage;
 }
 return IOHIDDeviceGetProperty(d,key);
}
static IOReturn deny_report(IOHIDDeviceRef d,IOHIDReportType type,CFIndex id,const uint8_t* data,CFIndex length){
 if(wheel(d)){fprintf(stderr,"G923_ADMISSION: BLOCKED SetReport type=%d id=%ld bytes=%ld\n",type,(long)id,(long)length);return kIOReturnNotPermitted;}
 return IOHIDDeviceSetReport(d,type,id,data,length);
}
#define INTERPOSE(replacement,original) \
 __attribute__((used)) static struct {const void* replacement;const void* original;} interpose_##original \
 __attribute__((section("__DATA,__interpose")))={(const void*)&replacement,(const void*)&original}
INTERPOSE(admission,IOHIDDeviceGetProperty);
INTERPOSE(deny_report,IOHIDDeviceSetReport);
