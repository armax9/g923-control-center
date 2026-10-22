// SPDX-License-Identifier: GPL-3.0-only
#include "bridge_server.hpp"
#include "ownership.hpp"
#include <memory>
#include <CoreFoundation/CoreFoundation.h>
#include <csignal>
#include <iostream>
static volatile sig_atomic_t stopping=0;
static void stop(int){stopping=1;}
int main(int argc,char** argv){
 if(argc!=1){std::cerr<<"Usage: g923-ffb (may initialize/calibrate wheel)\n";return 2;}
 (void)argv;
 std::signal(SIGINT,stop);std::signal(SIGTERM,stop);
 std::unique_ptr<Ownership> owner;try{owner=std::make_unique<Ownership>();}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}
 BridgeServer server;
 if(!server.start()){std::cerr<<"Cannot bind bridge port\n";return 1;}
 std::cout<<"Classic FFB bridge; TRUEFORCE disabled. Ctrl-C stops forces.\n";
 while(!stopping){CFRunLoopRunInMode(kCFRunLoopDefaultMode,1,false);auto s=server.status();
 std::cout<<"listening="<<s.listening<<" wheel="<<s.wheel_connected<<" client="<<s.client_connected<<" packets="<<s.packets_received<<" name="<<s.wheel_name<<std::endl;}
 server.stop();return 0;
}
