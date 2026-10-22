// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <array>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
struct TfTestPlan {
 static constexpr int rate=1000,active=200,tail=64,peak=64;
 std::array<int16_t,active+tail> samples{};
 explicit TfTestPlan(bool pulse,int amplitude=peak){if(amplitude<0||amplitude>32767)throw std::invalid_argument("amplitude out of int16 range");if(!pulse)return;for(int i=0;i<active;++i){double fade=std::min(1.,std::min(i/25.,(active-1-i)/25.));samples[i]=int16_t(std::lround(amplitude*fade*std::sin(2.*3.14159265358979323846*80*i/rate)));}}
};
