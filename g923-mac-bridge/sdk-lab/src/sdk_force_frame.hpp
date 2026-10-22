// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <cstdint>
#include <cstring>
#include <cmath>
#include <algorithm>
inline bool decode_kf_frame(const unsigned char* p,size_t n,uint64_t now,double& level){
 if(n!=24||std::memcmp(p,"G9KF",4))return false;
 uint32_t version;uint64_t stamp;double value;
 std::memcpy(&version,p+4,4);std::memcpy(&stamp,p+8,8);std::memcpy(&value,p+16,8);
 if(version!=1||stamp>now||now-stamp>250||!std::isfinite(value)||std::abs(value)>1)return false;
 level=value;return true;
}
inline double sdk_kf_target(double normalized,double peak,double continuous){
 return std::max(-continuous,std::min(continuous,normalized*peak));
}
