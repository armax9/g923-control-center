// SPDX-License-Identifier: GPL-3.0-only
#include "hid_support.hpp"
#include "ownership.hpp"
#include "tf_packet.hpp"
#include "../vendor/trueforce/tf_init_data.h"
#include <chrono>
#include <memory>
#include <thread>
#include <fstream>
#include <iostream>
#include <csignal>
#include <sys/socket.h>
#include <netinet/in.h>
#include <fcntl.h>
#include <unistd.h>
static volatile sig_atomic_t stopping=0;
static void stopSignal(int){stopping=1;}
int main(int argc,char**argv){
 bool hardware=false,udp=false;std::string out="tf-tone.bin";double seconds=3;
 try{
 for(int i=1;i<argc;++i){std::string a=argv[i];if(a=="--hardware")hardware=true;else if(a=="--udp")udp=true;else if(a=="--out"&&i+1<argc)out=argv[++i];else if(a=="--seconds"&&i+1<argc)seconds=std::stod(argv[++i]);else throw std::runtime_error("Usage: g923-tf [--hardware] [--udp] [--seconds 1..30] [--out trace.bin]");}
 if(!std::isfinite(seconds)||seconds<1||seconds>30)throw std::runtime_error("seconds must be 1..30");
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}
 std::signal(SIGINT,stopSignal);std::signal(SIGTERM,stopSignal);
 std::ofstream file(out,std::ios::binary|std::ios::trunc);if(!file){std::cerr<<"Cannot create trace\n";return 1;}
 int sock=-1;if(udp){sock=socket(AF_INET,SOCK_DGRAM,0);sockaddr_in a{};a.sin_family=AF_INET;a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);a.sin_port=htons(20777);if(sock<0||bind(sock,(sockaddr*)&a,sizeof(a))){perror("UDP bind");return 1;}fcntl(sock,F_SETFL,O_NONBLOCK);}
 // Do not even open HID manager for dry runs.
 std::unique_ptr<Ownership> owner;
 if(hardware){try{owner=std::make_unique<Ownership>();}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}
 int test=socket(AF_INET,SOCK_STREAM,0);sockaddr_in addr{};addr.sin_family=AF_INET;addr.sin_addr.s_addr=htonl(INADDR_LOOPBACK);addr.sin_port=htons(18423);bool busy=test>=0&&connect(test,(sockaddr*)&addr,sizeof(addr))==0;if(test>=0)close(test);if(busy){std::cerr<<"Classic bridge listening: stop it before TF test\n";return 1;}}
 std::unique_ptr<Hids> h;IOHIDDeviceRef device=nullptr;tf::Encoder encoder;bool failed=false;
 if(hardware){h=std::make_unique<Hids>();for(auto d:h->devices)if(g923(d)&&prop(d,CFSTR(kIOHIDPrimaryUsagePageKey))==0xfffd){if(device){std::cerr<<"Ambiguous TF interface: unplug second wheel\n";return 1;}device=d;}
 if(!device){std::cerr<<"G923 PS vendor page 0xFFFD unavailable; no reports sent\n";return 3;}
 auto r=IOHIDDeviceOpen(device,0);if(r){std::cerr<<"Device open failed: "<<r<<'\n';return 1;}}
 auto send=[&](const tf::Packet& p){file.write((const char*)p.data(),p.size());if(!file)failed=true;if(device){auto r=IOHIDDeviceSetReport(device,kIOHIDReportTypeOutput,1,p.data(),p.size());if(r){std::cerr<<"SetReport failed 0x"<<std::hex<<r<<'\n';failed=true;}}};
 std::cout<<(hardware?"HARDWARE EXPERIMENT":"DRY RUN")<<": synthesized haptics, not game-native TRUEFORCE. 2% amplitude, cur neutral; no concurrent FFB.\n";
 for(int pass=0;pass<2&&!failed&&!stopping;++pass)for(int i=0;i<TF_INIT_PACKET_COUNT&&!failed&&!stopping;++i){tf::Packet p;std::copy_n(tf_init_packets[i],64,p.begin());p[5]=i+1;if(p[4]==0x0e){float range=900;std::memcpy(p.data()+6,&range,4);}send(p);if(hardware)std::this_thread::sleep_for(std::chrono::milliseconds(2));}
 auto begin=std::chrono::steady_clock::now(),last=begin-std::chrono::seconds(1);double phase=0,engine=0;long late=0,valid=0,invalid=0;
 for(int tick=0;tick<int(seconds*1000)&&!stopping&&!failed;++tick){
  if(udp){uint8_t b[2048];ssize_t n;int drained=0;while(drained++<128&&(n=recv(sock,b,sizeof(b),0))>0){try{engine=tf::rpm(b,n);last=std::chrono::steady_clock::now();++valid;}catch(...){++invalid;}}}
  bool live=!udp||(engine>0&&std::chrono::steady_clock::now()-last<std::chrono::milliseconds(500));
  double frequency=udp?std::clamp(engine/60.*2.,15.,200.):40.+80.*tick/(seconds*1000);
  std::array<double,4> audio{};for(auto&v:audio){phase+=2*3.141592653589793*frequency/4000.;v=live?std::sin(phase)*.02:0;}
  send(encoder.encode(audio));
  if(hardware||udp){auto deadline=begin+std::chrono::milliseconds(tick+1);if(std::chrono::steady_clock::now()>deadline+std::chrono::milliseconds(2))++late;std::this_thread::sleep_until(deadline);}
 }
 send(encoder.encode({0,0,0,0}));send(encoder.stop());
 if(device)IOHIDDeviceClose(device,0);if(sock>=0)close(sock);
 std::cout<<"late_ticks="<<late<<" telemetry_valid="<<valid<<" invalid="<<invalid<<" trace="<<out<<'\n';return failed?1:0;
}
