// SPDX-License-Identifier: GPL-3.0-only
// TEST DOUBLE ONLY. No HID, SDK dependency, or force-producing implementation.
#include <windows.h>
#include <cstdint>
#include <cwchar>
static unsigned char mode;
static bool fault(const wchar_t* expected){wchar_t value[64]{};GetEnvironmentVariableW(L"G923_COMBINED_FIXTURE_FAIL",value,64);return !std::wcscmp(value,expected);}
#define API extern "C" __declspec(dllexport)
API void dllOpen(){mode=0;}
API void dllClose(){}
API int logiWheelOpenByDirectInputA(void*,uint64_t* out){*out=42;return 0;}
API int logiWheelClose(uint64_t){return 0;}
API int logiWheelSdkHasControl(uint64_t,uint32_t* out){*out=1;return 0;}
API int logiWheelGetForceMode(uint64_t,unsigned char* out){*out=mode;return 0;}
API int logiWheelSetForceMode(uint64_t,unsigned char value){mode=value;return 0;}
API int logiTrueForceClearTF(uint64_t){return 0;}
API int logiTrueForceClearKF(uint64_t){return fault(L"clear")?7:0;}
API int logiTrueForceGetGainTF(uint64_t,double* out){*out=1.;return 0;}
API int logiTrueForceGetHapticRate(uint64_t,double* out){*out=1000.;return 0;}
API int logiTrueForceGetTorqueTFRateBounds(uint64_t,double* lo,double* hi){*lo=10.;*hi=2000.;return 0;}
API int logiTrueForceGetMaxContinuousTorqueKF(uint64_t,double* out){*out=1.1;return 0;}
API int logiTrueForceGetMaxPeakTorqueKF(uint64_t,double* out){*out=2.2;return 0;}
API int logiTrueForceSetTorqueKF(uint64_t,double value){return value!=0&&fault(L"kinetic")?8:0;}
API int logiTrueForceSetTorqueTFint16(uint64_t,const int16_t*,uint64_t,double,double scale,int){return scale!=0&&fault(L"sample")?9:0;}
API int g923_fixture_probe(){return 923;}
