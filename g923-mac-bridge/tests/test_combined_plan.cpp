// SPDX-License-Identifier: GPL-3.0-only
#include "../sdk-lab/src/combined_test_plan.hpp"
#include <cstdlib>
#include <vector>
static std::vector<int> calls;
static int failSet,failClear;
static int set(uint64_t h,double v){if(h!=42)std::abort();calls.push_back(v==0?0:1);return failSet;}
static int clear(uint64_t h){if(h!=42)std::abort();calls.push_back(2);return failClear;}
static void check(bool value){if(!value)std::abort();}
int main(){
 CombinedTestPlan p;
 bool kpos=false,kneg=false,tone=false;
 for(int i=0;i<p.count;i++){
  check(std::isfinite(p.kinetic[i])&&std::abs(p.kinetic[i])<=.10);
  kpos|=p.kinetic[i]>0;kneg|=p.kinetic[i]<0;tone|=p.samples[i]!=0;
  if(i>=200)check(p.samples[i]==0);
  if(i>=p.active)check(p.kinetic[i]==0&&p.samples[i]==0);
 }
 check(kpos&&kneg&&tone);
 {KineticCleanup g{42,set,clear};}check(calls.empty());
 {KineticCleanup g{42,set,clear};check(g.send(.1)==0);g.cleanup();g.cleanup();}
 check(calls==std::vector<int>({1,0,2}));
 calls.clear();failSet=7;failClear=8;
 {KineticCleanup g{42,set,clear};check(g.send(.1)==7);g.cleanup();check(g.zero_status==7&&g.clear_status==8);}
 check(calls==std::vector<int>({1,0,2}));
}
