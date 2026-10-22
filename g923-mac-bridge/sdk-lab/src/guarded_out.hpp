// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <algorithm>
#include <cstdint>
#include <iterator>
template<class T> struct GuardedOut {
 uint64_t before=0x36a725d4108bf9c3ULL;T value{};unsigned char after[16];
 GuardedOut(){std::fill(std::begin(after),std::end(after),0xa5);}
 bool intact()const{return before==0x36a725d4108bf9c3ULL&&std::all_of(std::begin(after),std::end(after),[](auto c){return c==0xa5;});}
};
