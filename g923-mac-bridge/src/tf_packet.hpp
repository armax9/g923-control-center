// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <array>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <stdexcept>
namespace tf {
using Packet=std::array<uint8_t,64>;
inline uint16_t sample(double x){if(!std::isfinite(x))x=0;return static_cast<uint16_t>(std::lround(32768+std::clamp(x,-1.,1.)*32767));}
inline void put(Packet& p,int i,uint16_t n){p[i]=n&255;p[i+1]=n>>8;}
struct Encoder {
 uint8_t seq=69;
 std::array<uint16_t,13> window;
 Encoder(){window.fill(0x8000);}
 Packet encode(const std::array<double,4>& input,double torque=0){
  std::move(window.begin()+4,window.end(),window.begin());
  for(int i=0;i<4;++i)window[9+i]=sample(input[i]);
  Packet p{};p[0]=1;p[4]=1;p[5]=seq++;put(p,6,sample(torque));put(p,8,sample(torque));p[10]=4;p[11]=13;
  for(int i=0;i<13;++i){put(p,12+4*i,window[i]);put(p,14+4*i,window[i]);}return p;
 }
 Packet stop(){Packet p{};p[0]=1;p[4]=4;p[5]=seq++;return p;}
};
// Codemasters extradata=3 float array. RPM at float 37 is RPM / 10.
inline double rpm(const uint8_t* bytes,size_t n){
 if(n!=264)throw std::runtime_error("short/misaligned Codemasters packet");
 float v;std::memcpy(&v,bytes+148,4);
 if(!std::isfinite(v)||v<0||v>4000)throw std::runtime_error("invalid engine rate");
 return v*10.;
}
}
