// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "tf_test_plan.hpp"

// Synthetic SDK test only, not game FFB. KF values are fractions of the
// SDK-reported peak; apply no guessed physical-unit conversion.
struct CombinedTestPlan {
 static constexpr int rate=1000, active=400, tail=64, count=active+tail;
 static constexpr double kineticFraction=0.10;
 std::array<int16_t,count> samples{};
 std::array<double,count> kinetic{};
 CombinedTestPlan() {
  TfTestPlan tf(true,32767);
  std::copy(tf.samples.begin(),tf.samples.end(),samples.begin());
  for(int i=0;i<active;i++) {
   double fade=std::max(0.,std::min(1.,std::min(i/50.,(active-1-i)/50.)));
   kinetic[i]=kineticFraction*fade*std::sin(2.*3.14159265358979323846*5.*i/rate);
  }
 }
};

struct KineticCleanup {
 using Set=int(*)(uint64_t,double);
 using Clear=int(*)(uint64_t);
 uint64_t handle;Set set;Clear clear;
 bool attempted=false,cleaned=false;
 int zero_status=0,clear_status=0;
 int send(double value) { attempted=true;return set(handle,value); }
 void cleanup() {
  if(cleaned)return;cleaned=true;
  if(attempted){zero_status=set(handle,0.);clear_status=clear(handle);}
 }
 ~KineticCleanup(){cleanup();}
};
