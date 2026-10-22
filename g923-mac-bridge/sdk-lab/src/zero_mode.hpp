// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <cstdint>
struct ZeroMode {
 using Get=int(*)(uint64_t,unsigned char*);using Set=int(*)(uint64_t,unsigned char);using Clear=int(*)(uint64_t);
 uint64_t handle;Get get;Set set;Clear clear;unsigned char original=255;bool attempted=false,cleaned=false;
 int clear_status=0,restore_status=0;
 int enable(){int r=get(handle,&original);if(r)return r;if(original!=0)return -1;
  attempted=true;r=set(handle,1);if(r)return r;unsigned char now=255;r=get(handle,&now);return r?r:now==1?0:-2;}
 void cleanup(){if(cleaned)return;cleaned=true;if(attempted){clear_status=clear(handle);restore_status=set(handle,original);}}
 ~ZeroMode(){cleanup();}
};
