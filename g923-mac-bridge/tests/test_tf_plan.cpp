// SPDX-License-Identifier: GPL-3.0-only
#include "../sdk-lab/src/tf_test_plan.hpp"
#include <cstdlib>
static void check(bool b){if(!b)std::abort();}
int main(){TfTestPlan zero(false),pulse(true);long total=0;int maximum=0;
 for(auto v:zero.samples)check(v==0);
 for(auto v:pulse.samples){check(std::abs(int(v))<=TfTestPlan::peak);maximum=std::max(maximum,std::abs(int(v)));total+=v;}
 check(maximum>0);check(pulse.samples.front()==0);check(pulse.samples[TfTestPlan::active-1]==0);
 for(int i=TfTestPlan::active;i<int(pulse.samples.size());++i)check(pulse.samples[i]==0);
 TfTestPlan full(true,32767);int m=0;for(auto v:full.samples){check(std::abs(int(v))<=32767);m=std::max(m,std::abs(int(v)));}check(m>32000);check(full.samples.front()==0);check(full.samples[TfTestPlan::active-1]==0);for(int i=TfTestPlan::active;i<int(full.samples.size());++i)check(full.samples[i]==0);bool rejected=false;try{TfTestPlan bad(true,32768);}catch(const std::invalid_argument&){rejected=true;}check(rejected);
 check(std::abs(total)<100);check(pulse.samples.size()==264);
}
