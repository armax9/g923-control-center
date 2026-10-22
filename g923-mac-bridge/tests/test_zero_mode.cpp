// SPDX-License-Identifier: GPL-3.0-only
#include "../sdk-lab/src/zero_mode.hpp"
#include <cstdlib>
#include <cstring>
#include <cstddef>
#include "../sdk-lab/src/guarded_out.hpp"
#include <vector>
static unsigned char mode;static int get_error,set_error,clear_error;static std::vector<int> calls;
static int get(uint64_t h,unsigned char* p){if(h!=0x123456789abcdef0ULL)std::abort();calls.push_back(10);*p=mode;return get_error;}
static int set(uint64_t,unsigned char v){calls.push_back(20+v);mode=v;return v==1?set_error:0;}
static int clear(uint64_t){calls.push_back(30);return clear_error;}
static void reset(){mode=0;get_error=set_error=clear_error=0;calls.clear();}
static void check(bool x){if(!x)std::abort();}
int main(){
 static_assert(offsetof(GuardedOut<uint8_t>,after)==offsetof(GuardedOut<uint8_t>,value)+1);
 GuardedOut<uint32_t> proper;uint32_t v=1;std::memcpy(&proper.value,&v,4);check(proper.intact()&&proper.value==1);
 GuardedOut<uint8_t> wrong;auto bytes=reinterpret_cast<unsigned char*>(&wrong);std::memcpy(bytes+offsetof(GuardedOut<uint8_t>,value),&v,4);check(!wrong.intact());

 reset();{ZeroMode g{0x123456789abcdef0ULL,get,set,clear};check(g.enable()==0);g.cleanup();g.cleanup();check(mode==0);check(calls==std::vector<int>({10,21,10,30,20}));}
 reset();get_error=9;{ZeroMode g{0x123456789abcdef0ULL,get,set,clear};check(g.enable()==9);}check(calls==std::vector<int>({10}));
 reset();set_error=8;{ZeroMode g{0x123456789abcdef0ULL,get,set,clear};check(g.enable()==8);}check(mode==0);check(calls==std::vector<int>({10,21,30,20}));
 reset();clear_error=7;{ZeroMode g{0x123456789abcdef0ULL,get,set,clear};check(g.enable()==0);g.cleanup();check(g.clear_status==7);check(g.restore_status==0);}check(mode==0);
 reset();mode=1;{ZeroMode g{0x123456789abcdef0ULL,get,set,clear};check(g.enable()!=0);}check(calls==std::vector<int>({10}));check(mode==1);
}
