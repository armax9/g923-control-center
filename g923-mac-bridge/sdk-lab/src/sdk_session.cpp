// SPDX-License-Identifier: GPL-3.0-only
// Exact x64 SDK 1.3.12 ABI, checked against supplied unmodified DLL.
// Explicit pulse mode is bounded; open-only never sends samples. SDK 1.3.12 x64 only.
#define DIRECTINPUT_VERSION 0x0800
#include <windows.h>
#include <dinput.h>
#include <cstdio>
#include <cstdint>
#include <cwchar>
#include <cstring>
#include <initializer_list>
#include <cstdarg>
#include "zero_mode.hpp"
#include "tf_test_plan.hpp"
#include "combined_test_plan.hpp"
#include "guarded_out.hpp"
#include "sdk_force_frame.hpp"
// Per-process elapsed time; never equate a successful API call with physical playback.
static void eventf(const char* fmt,...){
 static const ULONGLONG origin=GetTickCount64();char text[2048];
 va_list args;va_start(args,fmt);int n=std::vsnprintf(text,sizeof(text),fmt,args);va_end(args);
 if(n<0||n>=int(sizeof(text))){std::fputs("event formatting failed\n",stderr);return;}
 while(n>0&&(text[n-1]=='\n'||text[n-1]=='\r'))text[--n]=0;
 if(n>1&&text[0]=='{'&&text[n-1]=='}'){
  text[n-1]=0;std::printf("%s,\"t_ms\":%llu,\"pid\":%lu}\n",text,(unsigned long long)(GetTickCount64()-origin),(unsigned long)GetCurrentProcessId());
 }else std::printf("%s\n",text);
}
static void eventline(const char* s){eventf("%s",s);}
static volatile LONG interrupted=0;
static BOOL WINAPI stop_handler(DWORD){InterlockedExchange(&interrupted,1);return TRUE;}
static bool stop_requested(const wchar_t* file,IDirectInputDevice8A* d){
 if(InterlockedCompareExchange(&interrupted,0,0)||GetFileAttributesW(file)!=INVALID_FILE_ATTRIBUTES)return true;
 DIJOYSTATE2 state{};if(FAILED(d->Poll())||FAILED(d->GetDeviceState(sizeof(state),&state)))return true;
 for(auto b:state.rgbButtons)if(b&0x80)return true;return false;
}
static GUID selected{};static unsigned count=0;
static BOOL CALLBACK select(const DIDEVICEINSTANCEA* i,void*){
 if(i->guidProduct.Data1==0xc266046d||i->guidProduct.Data1==0xc267046d){selected=i->guidInstance;++count;}
 return DIENUM_CONTINUE;
}
static void status(const char* event,int code){eventf("{\"event\":\"%s\",\"status_hex\":\"%08lx\"}\n",event,(unsigned long)(DWORD)code);}
static int run_kf_only(HMODULE lib,uint64_t handle,IDirectInputDevice8A* device,const wchar_t* stopFile){
 auto set=(KineticCleanup::Set)GetProcAddress(lib,"logiTrueForceSetTorqueKF");
 auto clear=(KineticCleanup::Clear)GetProcAddress(lib,"logiTrueForceClearKF");
 using Get=int(*)(uint64_t,double*);
 auto peak=(Get)GetProcAddress(lib,"logiTrueForceGetMaxPeakTorqueKF");
 auto continuous=(Get)GetProcAddress(lib,"logiTrueForceGetMaxContinuousTorqueKF");
 if(!set||!clear||!peak||!continuous)return 21;
 GuardedOut<double> p,c;int a=peak(handle,&p.value),b=continuous(handle,&c.value);
 status("kf_peak_query",a);status("kf_continuous_query",b);
 if(a||b||!p.intact()||!c.intact()||!std::isfinite(p.value)||!std::isfinite(c.value)||p.value<=0||p.value>100||c.value<=0||c.value>p.value)return 21;
 double limit=std::min(p.value*.25,c.value);
 eventf("{\"event\":\"kf_only_limits\",\"sdk_peak\":%.17g,\"sdk_continuous\":%.17g,\"test_limit\":%.17g,\"active_ms\":800,\"tf_sample_calls\":0}\n",p.value,c.value,limit);
 KineticCleanup cleanup{handle,set,clear};int result=0;unsigned calls=0;
 SetConsoleCtrlHandler(stop_handler,TRUE);auto start=GetTickCount64();
 for(unsigned i=0;i<200;i++){
  if(stop_requested(stopFile,device)||GetTickCount64()-start>1200){result=18;break;}
  unsigned phase=(i*4)%400;
  double fade=std::min(1.,std::min(phase/40.,(399-phase)/40.));
  double target=limit*fade*(i<100?1.:-1.);
  int q=cleanup.send(target);++calls;
  if(q){status("kinetic_send_failed",q);result=22;break;}
  auto deadline=start+(i+1)*4;auto now=GetTickCount64();if(deadline>now)Sleep(DWORD(deadline-now));
 }
 cleanup.cleanup();status("kinetic_zero",cleanup.zero_status);status("clear_kf",cleanup.clear_status);
 if(cleanup.zero_status||cleanup.clear_status)result=23;
 SetConsoleCtrlHandler(stop_handler,FALSE);
 eventf("{\"event\":\"kf_only_finished\",\"kinetic_calls\":%u,\"tf_sample_calls\":0,\"elapsed_ms\":%llu}\n",calls,(unsigned long long)(GetTickCount64()-start));
 return result;
}
static uint64_t unix_ms(){FILETIME ft;GetSystemTimeAsFileTime(&ft);ULARGE_INTEGER t;t.LowPart=ft.dwLowDateTime;t.HighPart=ft.dwHighDateTime;return (t.QuadPart-116444736000000000ULL)/10000;}
static int run_kf_live(HMODULE lib,uint64_t handle,const wchar_t* stopFile,const wchar_t* forceFile){
 auto set=(KineticCleanup::Set)GetProcAddress(lib,"logiTrueForceSetTorqueKF");
 auto clear=(KineticCleanup::Clear)GetProcAddress(lib,"logiTrueForceClearKF");
 using Get=int(*)(uint64_t,double*);
 auto peak=(Get)GetProcAddress(lib,"logiTrueForceGetMaxPeakTorqueKF");
 auto continuous=(Get)GetProcAddress(lib,"logiTrueForceGetMaxContinuousTorqueKF");
 auto control=(int(*)(uint64_t,uint32_t*))GetProcAddress(lib,"logiWheelSdkHasControl");
 if(!set||!clear||!peak||!continuous||!control)return 21;
 GuardedOut<double> p,c;int a=peak(handle,&p.value),b=continuous(handle,&c.value);
 if(a||b||!p.intact()||!c.intact()||!std::isfinite(p.value)||!std::isfinite(c.value)||p.value<=0||p.value>100||c.value<=0||c.value>p.value)return 21;
 KineticCleanup cleanup{handle,set,clear};int result=0;unsigned calls=0;auto fresh=GetTickCount64(),lastLog=fresh,lastControl=fresh;
 eventf("{\"event\":\"sdk_live_ready\",\"peak\":%.17g,\"continuous\":%.17g,\"tf_sample_calls\":0}\n",p.value,c.value);
 SetConsoleCtrlHandler(stop_handler,TRUE);
 while(!InterlockedCompareExchange(&interrupted,0,0)&&GetFileAttributesW(stopFile)==INVALID_FILE_ATTRIBUTES){
  unsigned char bytes[25]{};DWORD n=0;double level=0;
  HANDLE f=CreateFileW(forceFile,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
  bool valid=false;if(f!=INVALID_HANDLE_VALUE){if(ReadFile(f,bytes,sizeof(bytes),&n,nullptr))valid=decode_kf_frame(bytes,n,unix_ms(),level);CloseHandle(f);}
  auto now=GetTickCount64();if(valid)fresh=now;
  double target=valid?sdk_kf_target(level,p.value,c.value):0;
  int q=cleanup.send(target);++calls;if(q){status("kinetic_send_failed",q);result=22;break;}
  if(now-lastControl>=250){GuardedOut<uint32_t> owned;int q=control(handle,&owned.value);lastControl=now;if(q||!owned.intact()||!owned.value){result=25;break;}}
  if(now-lastLog>=100){eventf("{\"event\":\"sdk_live_force\",\"fresh\":%s,\"normalized\":%.17g,\"target\":%.17g,\"calls\":%u}\n",valid?"true":"false",level,target,calls);lastLog=now;}
  if(now-fresh>1000){eventline("{\"event\":\"sdk_force_watchdog\"}");result=24;break;}
  Sleep(4);
 }
 cleanup.cleanup();status("kinetic_zero",cleanup.zero_status);status("clear_kf",cleanup.clear_status);if(cleanup.zero_status||cleanup.clear_status)result=23;
 SetConsoleCtrlHandler(stop_handler,FALSE);return result;
}
int wmain(int argc,wchar_t**argv){
 setvbuf(stdout,nullptr,_IONBF,0);
 if(argc==2&&!std::wcscmp(argv[1],L"--dry-run")){eventline("{\"hardware_used\":false,\"active_ms\":200,\"zero_tail_ms\":64,\"tone_hz\":80,\"rate\":1000,\"sample_peak\":64,\"scale\":0.1}");return 0;}
 bool kfLive=argc==9&&!std::wcscmp(argv[1],L"--kf-live")&&!std::wcscmp(argv[3],L"--initialize-sdk-1_3_12")&&!std::wcscmp(argv[4],L"--user-ready")&&!std::wcscmp(argv[5],L"--stop-file")&&!std::wcscmp(argv[7],L"--force-file");
 bool kfOnly=(argc==7||argc==9)&&!std::wcscmp(argv[1],L"--kf-only")&&!std::wcscmp(argv[3],L"--initialize-sdk-1_3_12")&&!std::wcscmp(argv[4],L"--user-ready")&&!std::wcscmp(argv[5],L"--stop-file")&&(argc==7||!std::wcscmp(argv[7],L"--arm-file"));
 bool armedCombined=argc==9&&!std::wcscmp(argv[1],L"--tf-combined")&&!std::wcscmp(argv[7],L"--arm-file");
 if(kfOnly&&argc==9)armedCombined=true;
 bool combined=(argc==7||armedCombined)&&!std::wcscmp(argv[1],L"--tf-combined");
 bool maximum=combined||(argc==7&&!std::wcscmp(argv[1],L"--tf-pulse-max"));
 int samplePeak=maximum?32767:64;
 bool detect=argc==7&&!std::wcscmp(argv[1],L"--tf-pulse-detect");
 double pulseScale=(detect||maximum)?1.:0.1;
 bool pulse=(argc==7||armedCombined)&&(!std::wcscmp(argv[1],L"--tf-pulse")||detect||maximum)&&!std::wcscmp(argv[5],L"--stop-file")&&!std::wcscmp(argv[4],L"--user-ready");
 bool buffer=argc==5&&!std::wcscmp(argv[1],L"--tf-zero-buffer");
 bool zero=(argc==5||pulse)&&(!std::wcscmp(argv[1],L"--enable-tf-zero")||buffer||pulse)&&!std::wcscmp(argv[4],L"--user-ready");
 if(kfOnly||kfLive)zero=true;
 if((argc!=4&&!zero)||(!zero&&std::wcscmp(argv[1],L"--open-only"))||std::wcscmp(argv[3],L"--initialize-sdk-1_3_12")){std::fputs("Usage: sdk-session.exe --open-only ABS_DLL --initialize-sdk-1_3_12\nOpen-only makes no sample calls; tf-zero-buffer explicitly sends zero samples.\n",stderr);return 2;}
 IDirectInput8A* di=nullptr;
 HRESULT pre=DirectInput8Create(GetModuleHandleW(nullptr),DIRECTINPUT_VERSION,IID_IDirectInput8A,(void**)&di,nullptr);status("pre_sdk_dinput_create",pre);if(FAILED(pre))return 5;
 auto lib=LoadLibraryExW(argv[2],nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
 if(!lib){status("load_failed",GetLastError());di->Release();return 3;}
 auto init=(void(*)())GetProcAddress(lib,"dllOpen");auto finish=(void(*)())GetProcAddress(lib,"dllClose");
 auto open=(int(*)(IDirectInputDevice8A*,uint64_t*))GetProcAddress(lib,"logiWheelOpenByDirectInputA");
 auto close=(int(*)(uint64_t))GetProcAddress(lib,"logiWheelClose");
 auto control=(int(*)(uint64_t,uint32_t*))GetProcAddress(lib,"logiWheelSdkHasControl");
 if(!init||!finish||!open||!close||!control){FreeLibrary(lib);di->Release();return 4;}
 IDirectInputDevice8A* device=nullptr;uint64_t handle=0;unsigned nonzeroCalls=0;bool opened=false,initialized=false;int result=5;

 do {
  HRESULT hr=pre;status("dinput_create",hr);
  hr=di->EnumDevices(DI8DEVCLASS_GAMECTRL,select,nullptr,DIEDFL_ATTACHEDONLY);status("dinput_enumerate",hr);eventf("{\"event\":\"target_count\",\"count\":%u}\n",count);if(FAILED(hr)||count!=1)break;
  hr=di->CreateDevice(selected,&device,nullptr);status("device_create",hr);if(FAILED(hr))break;
  DIPROPDWORD vp{};vp.diph.dwSize=sizeof(vp);vp.diph.dwHeaderSize=sizeof(vp.diph);vp.diph.dwHow=DIPH_DEVICE;hr=device->GetProperty(DIPROP_VIDPID,&vp.diph);status("vidpid_query",hr);eventf("{\"event\":\"device_vidpid\",\"value\":\"%08lx\"}\n",(unsigned long)vp.dwData);
  hr=device->SetDataFormat(&c_dfDIJoystick2);status("format",hr);if(FAILED(hr))break;
  hr=device->SetCooperativeLevel(GetDesktopWindow(),DISCL_NONEXCLUSIVE|DISCL_BACKGROUND);status("cooperative",hr);if(FAILED(hr))break;
  hr=device->Acquire();status("acquire",hr);if(FAILED(hr))break;
  init();initialized=true;eventf("{\"event\":\"sdk_initialized\",\"pulse_requested\":%s}\n",pulse?"true":"false");
  int r=open(device,&handle);status("sdk_wheel_open",r);eventf("{\"event\":\"session_handle\",\"nonzero\":%s,\"upper32_nonzero\":%s}\n",handle?"true":"false",handle>>32?"true":"false");
  opened=r==0&&handle!=0;if(!opened)break;
  GuardedOut<uint32_t> flag;r=control(handle,&flag.value);if(!flag.intact()){status("control_output_overrun",-1);result=15;break;}uint32_t value=flag.value;status("sdk_has_control",r);eventf("{\"event\":\"control_value\",\"value\":%s}\n",r==0&&value?"true":"false");result=r==0&&value?0:6;if(result)break;
  auto getmode=(ZeroMode::Get)GetProcAddress(lib,"logiWheelGetForceMode");auto setmode=(ZeroMode::Set)GetProcAddress(lib,"logiWheelSetForceMode");auto clear=(ZeroMode::Clear)GetProcAddress(lib,"logiTrueForceClearTF");
  if(!getmode||!setmode||!clear){result=9;break;}
  unsigned char original=255;int m=getmode(handle,&original);status("get_force_mode",m);eventf("{\"event\":\"force_mode\",\"value\":%u}\n",original);
  if(m!=0||original!=0){result=14;break;}
  for(const char* name:{"logiWheelGetOperatingRangeDegrees","logiTrueForceGetGainKF"}){
   auto get=(int(*)(uint64_t,double*))GetProcAddress(lib,name);
   if(get){GuardedOut<double> value;int q=get(handle,&value.value);status(name,q);
    if(!value.intact()){result=15;break;}
    if(!q&&std::isfinite(value.value))eventf("{\"event\":\"sdk_readonly_parameter\",\"name\":\"%s\",\"value\":%.17g}\n",name,value.value);
   }
  }
  if(result==15)break;
  ZeroMode guard{handle,getmode,setmode,clear};
  bool capsReady=true;double gain=0,low=0,high=0;
  if((pulse||kfOnly||kfLive)&&stop_requested(argv[6],device)){result=16;break;}
  if(armedCombined){
   eventline("{\"event\":\"combined_waiting_for_arm\",\"force_mode\":0}");
   while(GetFileAttributesW(argv[8])==INVALID_FILE_ATTRIBUTES){
    if(stop_requested(argv[6],device)){result=18;break;}Sleep(10);
   }
   if(result==18)break;
   eventline("{\"event\":\"combined_arm_received\"}");
  }
  if(zero){int z=guard.enable();status("enable_tf_zero",z);if(z){result=10;guard.cleanup();status("clear_tf",guard.clear_status);status("restore_mode",guard.restore_status);break;}}
  if(kfOnly||kfLive){
   result=kfLive?run_kf_live(lib,handle,argv[6],argv[8]):run_kf_only(lib,handle,device,argv[6]);
   guard.cleanup();status("clear_tf",guard.clear_status);status("restore_mode",guard.restore_status);
   unsigned char after=255;int q=getmode(handle,&after);status("mode_after_cleanup",q);
   eventf("{\"event\":\"force_mode_restored\",\"value\":%u}\n",after);
   if(guard.clear_status||guard.restore_status||q||after!=original)result=11;
   break;
  }
  for(const char* name:{"logiTrueForceGetGainTF","logiTrueForceGetHapticRate"}){
   auto get=(int(*)(uint64_t,double*))GetProcAddress(lib,name);double number=0;
   if(get){int code=get(handle,&number);status(name,code);if(code||!std::isfinite(number))capsReady=false;if(!std::strcmp(name,"logiTrueForceGetGainTF"))gain=number;eventf("{\"event\":\"getter_value\",\"name\":\"%s\",\"value\":%.17g}\n",name,number);}
  }
  auto bounds=(int(*)(uint64_t,double*,double*))GetProcAddress(lib,"logiTrueForceGetTorqueTFRateBounds");
  if(bounds){double lo=0,hi=0;int code=bounds(handle,&lo,&hi);low=lo;high=hi;if(code)capsReady=false;status("rate_bounds",code);eventf("{\"event\":\"rate_bounds_value\",\"low\":%.17g,\"high\":%.17g}\n",lo,hi);}

  if(pulse){
   auto send=(int(*)(uint64_t,const int16_t*,uint64_t,double,double,int))GetProcAddress(lib,"logiTrueForceSetTorqueTFint16");
   if(!send||!capsReady||gain<0||gain>1||!std::isfinite(low)||!std::isfinite(high)||low>1000||high<1000){status("pulse_precondition_failed",-1);result=17;}
   else{
    auto setKF=(KineticCleanup::Set)GetProcAddress(lib,"logiTrueForceSetTorqueKF");
    auto clearKF=(KineticCleanup::Clear)GetProcAddress(lib,"logiTrueForceClearKF");
    auto maxKF=(int(*)(uint64_t,double*))GetProcAddress(lib,"logiTrueForceGetMaxPeakTorqueKF");
    double maximumKF=0;bool kfReady=!combined;
    if(combined&&setKF&&clearKF&&maxKF){
     GuardedOut<double> value;int q=maxKF(handle,&value.value);status("max_peak_kf",q);
     kfReady=q==0&&value.intact()&&std::isfinite(value.value)&&value.value>0&&value.value<=100;
     maximumKF=value.value;
     if(kfReady)eventf("{\"event\":\"combined_limits\",\"sdk_peak_kf\":%.17g,\"fraction\":0.10,\"active_ms\":400,\"tf_active_ms\":200}\n",maximumKF);
    }
    KineticCleanup kinetic{handle,setKF,clearKF};
    SetConsoleCtrlHandler(stop_handler,TRUE);TfTestPlan plan(true,samplePeak);CombinedTestPlan mixed;
    const int16_t* samples=combined?mixed.samples.data():plan.samples.data();
    size_t count=combined?mixed.samples.size():plan.samples.size();
    auto start=GetTickCount64();unsigned kineticCalls=0;
    if(!kfReady){status("combined_precondition_failed",-1);result=21;}
    else for(size_t off=0;off<count;off+=4){
     if(stop_requested(argv[6],device)||GetTickCount64()-start>(combined?750:500)){status("pulse_aborted",-1);result=18;break;}
     if(combined){int q=kinetic.send(mixed.kinetic[off]*maximumKF);++kineticCalls;if(q){status("kinetic_send_failed",q);result=22;break;}}
     int q=send(handle,samples+off,4,1000.,pulseScale,0);++nonzeroCalls;if(q){status("pulse_send_failed",q);result=19;break;}
     auto target=start+off+4;auto now=GetTickCount64();if(target>now)Sleep(DWORD(target-now));
    }
    int16_t zeros[16]{};int q=send(handle,zeros,16,1000.,0.,0);status("final_zero_buffer",q);if(q)result=20;
    if(combined){kinetic.cleanup();status("kinetic_zero",kinetic.zero_status);status("clear_kf",kinetic.clear_status);if(kinetic.zero_status||kinetic.clear_status)result=23;}
    eventf("{\"event\":\"pulse_finished\",\"send_calls\":%u,\"kinetic_calls\":%u,\"combined\":%s,\"elapsed_ms\":%llu,\"sample_peak\":%d,\"scale\":%g}\n",nonzeroCalls,kineticCalls,combined?"true":"false",(unsigned long long)(GetTickCount64()-start),samplePeak,pulseScale);
    SetConsoleCtrlHandler(stop_handler,FALSE);
   }
  }
  if(buffer){auto send=(int(*)(uint64_t,const int16_t*,uint64_t,double,double,int))GetProcAddress(lib,"logiTrueForceSetTorqueTFint16");
   if(!send){result=12;}else{TfTestPlan plan(false);int q=send(handle,plan.samples.data(),plan.samples.size(),TfTestPlan::rate,0.,0);status("sdk_zero_buffer",q);eventline("{\"event\":\"buffer_submitted\",\"samples\":264,\"rate\":1000,\"all_samples_zero\":true,\"scale\":0}");if(q)result=13;}
  }
  if(zero){guard.cleanup();status("clear_tf",guard.clear_status);status("restore_mode",guard.restore_status);unsigned char after=255;int q=getmode(handle,&after);status("mode_after_cleanup",q);eventf("{\"event\":\"force_mode_restored\",\"value\":%u}\n",after);if(guard.clear_status||guard.restore_status||q||after!=original)result=11;}
 }while(false);
 if(opened){int r=close(handle);status("sdk_wheel_close",r);if(r!=0)result=7;}
 if(device){device->Unacquire();device->Release();}if(di)di->Release();if(initialized)finish();eventf("{\"event\":\"sdk_closed\",\"pulse_send_calls\":%u}\n",nonzeroCalls);FreeLibrary(lib);return result;
}
