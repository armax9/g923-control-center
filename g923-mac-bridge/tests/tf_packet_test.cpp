// SPDX-License-Identifier: GPL-3.0-only
#include "tf_packet.hpp"
#include <iostream>
#include <limits>
#define CHECK(x) do {if(!(x)){std::cerr<<"FAIL line "<<__LINE__<<": "<<#x<<'\n';return 1;}}while(0)
int main(){tf::Encoder e;auto p=e.encode({0,.5,-.5,0});CHECK(p.size()==64);CHECK(p[0]==1&&p[4]==1&&p[5]==69);CHECK(p[6]==0&&p[7]==128&&p[8]==0&&p[9]==128);CHECK(p[10]==4&&p[11]==13);for(int i=0;i<13;++i)CHECK(p[12+4*i]==p[14+4*i]&&p[13+4*i]==p[15+4*i]);CHECK(tf::sample(0)==32768);CHECK(tf::sample(4)==65535);CHECK(tf::sample(-4)==1);CHECK(tf::sample(std::numeric_limits<double>::quiet_NaN())==32768);e.seq=255;CHECK(e.stop()[5]==255);CHECK(e.stop()[5]==0);auto q=e.encode({0,0,0,0});CHECK(q[12+4*6]==p[12+4*10]);uint8_t b[264]{};float rate=1000;std::memcpy(b+148,&rate,4);CHECK(tf::rpm(b,264)==10000);bool rejected=false;try{tf::rpm(b,100);}catch(...){rejected=true;}CHECK(rejected);std::cout<<"TF packet, history, clamp, sequence and telemetry checks passed\n";}
