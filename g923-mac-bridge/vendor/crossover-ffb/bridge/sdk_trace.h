/* SPDX-License-Identifier: MIT
 * Opt-in observation of SDK exports resolved by the main executable. The
 * original signed SDK file and returned results are never modified. */
typedef struct {
    U64 calls, errors, samples, nonzero, peakMilli, lastValue;
    U32 last;
} SdkMetric;
enum { SDK_OPEN_A, SDK_OPEN_W, SDK_CLOSE, SDK_MODE, SDK_AVAILABLE, SDK_KF,
       SDK_TF8, SDK_TF16, SDK_TF32, SDK_TFFLOAT, SDK_TFDOUBLE,
       SDK_CLEAR_KF, SDK_CLEAR_TF, SDK_DLL_OPEN, SDK_DLL_CLOSE, SDK_OPERATOR_STOP, SDK_SUPPORTED, SDK_SUPPORTED_A, SDK_SUPPORTED_W, SDK_WHEEL_SUPPORTED_A, SDK_WHEEL_SUPPORTED_W, SDK_GET_MODE, SDK_RATE, SDK_THREAD, SDK_TF_GAIN, SDK_KF_GAIN, SDK_MAX_PEAK, SDK_MAX_CONT, SDK_DAMP_MAX, SDK_DAMP, SDK_BOUNDS, SDK_VERSION, SDK_COUNT };
static const char *sdkNames[SDK_COUNT] = {
    "logiWheelOpenByDirectInputA", "logiWheelOpenByDirectInputW", "logiWheelClose",
    "logiWheelSetForceMode", "logiTrueForceAvailable", "logiTrueForceSetTorqueKF",
    "logiTrueForceSetTorqueTFint8", "logiTrueForceSetTorqueTFint16", "logiTrueForceSetTorqueTFint32",
    "logiTrueForceSetTorqueTFfloat", "logiTrueForceSetTorqueTFdouble",
    "logiTrueForceClearKF", "logiTrueForceClearTF", "dllOpen", "dllClose", "operator_stop",
    "logiTrueForceSupported", "logiTrueForceSupportedByDirectInputA", "logiTrueForceSupportedByDirectInputW",
    "logiWheelSupportedByDirectInputA", "logiWheelSupportedByDirectInputW", "logiWheelGetForceMode",
    "logiTrueForceGetHapticRate", "logiTrueForceGetHapticThreadStatus", "logiTrueForceGetGainTF",
    "logiTrueForceGetGainKF", "logiTrueForceGetMaxPeakTorqueKF", "logiTrueForceGetMaxContinuousTorqueKF",
    "logiTrueForceGetDampingMax", "logiTrueForceGetDamping", "logiTrueForceGetTorqueTFRateBounds", "logiWheelGetVersion"
};
static SdkMetric sdkMetrics[SDK_COUNT];
static PTR sdkOriginal[SDK_COUNT];
static PTR sdkObservedModule;
static int sdk_equal(const char *a,const char *b) {
    for(U32 i=0;i<128;i++){if(a[i]!=b[i])return 0;if(!a[i])return 1;}return 0;
}
static U64 sdk_peak(double value) {
    if(value<0)value=-value;
    if(value!=value || value>1e12)return 0; /* no invalid FP-to-integer conversion */
    return value>0&&value<.001?1:(U64)(value*1000.);
}
static U32 sdk_decimal(char *out,U32 at,U64 value) {
    char digits[24];U32 count=0;do{digits[count++]='0'+value%10;value/=10;}while(value);
    while(count)out[at++]=digits[--count];return at;
}
#ifdef CFB_TEST
extern void test_sdk_record(U32,const SdkMetric *);
static void sdk_record(U32 index){test_sdk_record(index,&sdkMetrics[index]);}
#else
IMPORT PTR GetModuleHandleW(const U16 *);
IMPORT U32 GetEnvironmentVariableW(const U16 *,U16 *,U32);
IMPORT int VirtualProtect(PTR,U64,U32,U32 *);
static void sdk_record(U32 index) {
    U16 path[1024];U32 length=GetModuleFileNameW(module,path,1024);
    if(!length||length>=900)return;
    while(length&&path[length-1]!='\\'&&path[length-1]!='/')length--;
    if(!length)return;
    const char *leaf="g923-sdk-trace.jsonl";
    for(U32 i=0;;i++){path[length+i]=leaf[i];if(!leaf[i])break;}
    PTR file=CreateFileW(path,4|0x80,3,0,4,0x80,0);
    if(file==(PTR)(~(U64)0))return;
    long long size=0;
    if(!GetFileSizeEx(file,&size)||size>64*1024*1024){CloseHandle(file);return;}
    SdkMetric *m=&sdkMetrics[index];char line[512];U32 n=0,written=0;
    n=text(line,n,"{\"event\":\"sdk_call_summary\",\"name\":\"");n=text(line,n,sdkNames[index]);
    n=text(line,n,"\",\"pid\":");n=sdk_decimal(line,n,GetCurrentProcessId());
    n=text(line,n,",\"tick_ms\":");n=sdk_decimal(line,n,GetTickCount64());
    n=text(line,n,",\"calls\":");n=sdk_decimal(line,n,__atomic_load_n(&m->calls,__ATOMIC_RELAXED));
    n=text(line,n,",\"errors\":");n=sdk_decimal(line,n,__atomic_load_n(&m->errors,__ATOMIC_RELAXED));
    n=text(line,n,",\"samples_total\":");n=sdk_decimal(line,n,__atomic_load_n(&m->samples,__ATOMIC_RELAXED));
    n=text(line,n,",\"nonzero_batches\":");n=sdk_decimal(line,n,__atomic_load_n(&m->nonzero,__ATOMIC_RELAXED));
    n=text(line,n,",\"peak_raw_milli\":");n=sdk_decimal(line,n,__atomic_load_n(&m->peakMilli,__ATOMIC_RELAXED));
    n=text(line,n,",\"last_raw_milli\":");n=sdk_decimal(line,n,__atomic_load_n(&m->lastValue,__ATOMIC_RELAXED));
    n=text(line,n,",\"status_hex\":\"");n=hex(line,n,__atomic_load_n(&m->last,__ATOMIC_RELAXED),8);
    n=text(line,n,"\"}\n");WriteFile(file,line,n,&written,0);CloseHandle(file);
}
#endif
static void sdk_note(U32 index,HR status,U64 samples,U64 peak,int forceLog) {
    SdkMetric *m=&sdkMetrics[index];
    U64 count=__atomic_add_fetch(&m->calls,1,__ATOMIC_RELAXED);
    if(status)__atomic_add_fetch(&m->errors,1,__ATOMIC_RELAXED);
    U32 previous=__atomic_exchange_n(&m->last,(U32)status,__ATOMIC_RELAXED);
    __atomic_store_n(&m->lastValue,peak,__ATOMIC_RELAXED);
    __atomic_add_fetch(&m->samples,samples,__ATOMIC_RELAXED);
    if(peak)__atomic_add_fetch(&m->nonzero,1,__ATOMIC_RELAXED);
    U64 old=__atomic_load_n(&m->peakMilli,__ATOMIC_RELAXED);
    while(old<peak&&!__atomic_compare_exchange_n(&m->peakMilli,&old,peak,0,__ATOMIC_RELAXED,__ATOMIC_RELAXED)){}
    /* First calls, powers of two, every 256 calls and every error. */
    if(forceLog||(status&&(U32)status!=previous)||count<=3||!(count&(count-1))||!(count&255))sdk_record(index);
}
static void sdk_flush(void){for(U32 i=0;i<SDK_COUNT;i++)if(sdkMetrics[i].calls)sdk_record(i);}
static PTR sdk_fn(U32 index){return __atomic_load_n(&sdkOriginal[index],__ATOMIC_ACQUIRE);}
#ifdef CFB_TEST
static int sdk_stopped(U64 handle){(void)handle;return 0;}
#else
IMPORT U32 GetFileAttributesW(const U16 *);
static U16 sdkStopPath[1024];
static U32 sdkStopLatched;
static int sdk_stopped(U64 handle) {
    if(__atomic_load_n(&sdkStopLatched,__ATOMIC_ACQUIRE))return 1;
    if(!sdkStopPath[0]||GetFileAttributesW(sdkStopPath)==0xffffffff)return 0;
    U32 expected=0;
    if(__atomic_compare_exchange_n(&sdkStopLatched,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){
        PTR library=__atomic_load_n(&sdkObservedModule,__ATOMIC_ACQUIRE);
        HR (*clearKF)(U64)=(void *)GetProcAddress(library,"logiTrueForceClearKF");
        HR (*clearTF)(U64)=(void *)GetProcAddress(library,"logiTrueForceClearTF");
        HR (*mode)(U64,unsigned char)=(void *)GetProcAddress(library,"logiWheelSetForceMode");
        HR a=clearKF?clearKF(handle):UNSUPPORTED,b=clearTF?clearTF(handle):UNSUPPORTED,c=mode?mode(handle,0):UNSUPPORTED;
        sdk_note(SDK_CLEAR_KF,a,0,0,1);sdk_note(SDK_CLEAR_TF,b,0,0,1);sdk_note(SDK_MODE,c,0,0,1);
        sdk_note(SDK_OPERATOR_STOP,a?a:b?b:c,0,0,1);
    }
    return 1;
}
#endif
static HR sdk_open_a(PTR device,U64 *handle){HR r=((HR(*)(PTR,U64*))sdk_fn(SDK_OPEN_A))(device,handle);sdk_note(SDK_OPEN_A,r,0,0,1);return r;}
static HR sdk_open_w(PTR device,U64 *handle){HR r=((HR(*)(PTR,U64*))sdk_fn(SDK_OPEN_W))(device,handle);sdk_note(SDK_OPEN_W,r,0,0,1);return r;}
static HR sdk_close(U64 h){HR r=((HR(*)(U64))sdk_fn(SDK_CLOSE))(h);sdk_note(SDK_CLOSE,r,0,0,1);sdk_flush();return r;}
static HR sdk_mode(U64 h,unsigned char mode){if(mode==1&&sdk_stopped(h)){sdk_note(SDK_MODE,(HR)0x80004004,0,mode,1);return (HR)0x80004004;}HR r=((HR(*)(U64,unsigned char))sdk_fn(SDK_MODE))(h,mode);sdk_note(SDK_MODE,r,0,mode,1);return r;}
static HR sdk_available(unsigned char *value){HR r=((HR(*)(unsigned char*))sdk_fn(SDK_AVAILABLE))(value);sdk_note(SDK_AVAILABLE,r,0,r==0&&value?*value:0,1);return r;}
static HR sdk_kf(U64 h,double value){if(sdk_stopped(h)&&value!=0){sdk_note(SDK_KF,(HR)0x80004004,0,0,1);return (HR)0x80004004;}HR r=((HR(*)(U64,double))sdk_fn(SDK_KF))(h,value);sdk_note(SDK_KF,r,0,r==0?sdk_peak(value):0,0);return r;}
#define SDK_TF_WRAPPER(name,index,type) \
static HR name(U64 h,const type *values,U64 count,double rate,double scale,int selector){ \
 if(sdk_stopped(h)&&scale!=0){sdk_note(index,(HR)0x80004004,0,0,1);return (HR)0x80004004;} \
 HR r=((HR(*)(U64,const type*,U64,double,double,int))sdk_fn(index))(h,values,count,rate,scale,selector); \
 U64 peak=0;if(r==0&&values)for(U64 i=0;i<count&&i<64;i++){U64 p=sdk_peak((double)values[i]);if(p>peak)peak=p;} \
 sdk_note(index,r,r==0?count:0,peak,0);return r; }
SDK_TF_WRAPPER(sdk_tf8,SDK_TF8,signed char)
SDK_TF_WRAPPER(sdk_tf16,SDK_TF16,short)
SDK_TF_WRAPPER(sdk_tf32,SDK_TF32,int)
SDK_TF_WRAPPER(sdk_tffloat,SDK_TFFLOAT,float)
SDK_TF_WRAPPER(sdk_tfdouble,SDK_TFDOUBLE,double)
static HR sdk_clear_kf(U64 h){HR r=((HR(*)(U64))sdk_fn(SDK_CLEAR_KF))(h);sdk_note(SDK_CLEAR_KF,r,0,0,1);return r;}
static HR sdk_clear_tf(U64 h){HR r=((HR(*)(U64))sdk_fn(SDK_CLEAR_TF))(h);sdk_note(SDK_CLEAR_TF,r,0,0,1);return r;}
static void sdk_dll_open(void){((void(*)(void))sdk_fn(SDK_DLL_OPEN))();sdk_note(SDK_DLL_OPEN,0,0,0,1);}
static void sdk_dll_close(void){((void(*)(void))sdk_fn(SDK_DLL_CLOSE))();sdk_note(SDK_DLL_CLOSE,0,0,0,1);sdk_flush();}
/* Read-only capabilities: pass the original output pointer through unchanged.
 * Boolean observations read only the first byte; status is never synthesized. */
#define SDK_BOOL_GET(name,index) \
static HR name(U64 h,unsigned char *out){HR r=((HR(*)(U64,unsigned char*))sdk_fn(index))(h,out);sdk_note(index,r,0,r==0&&out?*out:0,1);return r;}
SDK_BOOL_GET(sdk_supported,SDK_SUPPORTED)
SDK_BOOL_GET(sdk_supported_a,SDK_SUPPORTED_A)
SDK_BOOL_GET(sdk_supported_w,SDK_SUPPORTED_W)
SDK_BOOL_GET(sdk_wheel_supported_a,SDK_WHEEL_SUPPORTED_A)
SDK_BOOL_GET(sdk_wheel_supported_w,SDK_WHEEL_SUPPORTED_W)
SDK_BOOL_GET(sdk_get_mode,SDK_GET_MODE)
#define SDK_DOUBLE_GET(name,index) \
static HR name(U64 h,double *out){HR r=((HR(*)(U64,double*))sdk_fn(index))(h,out);sdk_note(index,r,0,r==0&&out?sdk_peak(*out):0,1);return r;}
SDK_DOUBLE_GET(sdk_rate,SDK_RATE)
SDK_DOUBLE_GET(sdk_tf_gain,SDK_TF_GAIN)
SDK_DOUBLE_GET(sdk_kf_gain,SDK_KF_GAIN)
SDK_DOUBLE_GET(sdk_max_peak,SDK_MAX_PEAK)
SDK_DOUBLE_GET(sdk_max_cont,SDK_MAX_CONT)
/* Opaque status-only outputs until their exact structure/size is validated. */
#define SDK_OPAQUE_GET(name,index) \
static HR name(U64 h,PTR out){HR r=((HR(*)(U64,PTR))sdk_fn(index))(h,out);sdk_note(index,r,0,0,1);return r;}
SDK_OPAQUE_GET(sdk_damp_max,SDK_DAMP_MAX)
SDK_OPAQUE_GET(sdk_damp,SDK_DAMP)
static HR sdk_thread(U64 h,U32 *out){HR r=((HR(*)(U64,U32*))sdk_fn(SDK_THREAD))(h,out);sdk_note(SDK_THREAD,r,0,0,1);return r;}
static HR sdk_bounds(U64 h,double *lo,double *hi){HR r=((HR(*)(U64,double*,double*))sdk_fn(SDK_BOUNDS))(h,lo,hi);sdk_note(SDK_BOUNDS,r,0,r==0&&hi?sdk_peak(*hi):0,1);return r;}
static HR sdk_version(U32 *major,U32 *minor,U32 *patch){HR r=((HR(*)(U32*,U32*,U32*))sdk_fn(SDK_VERSION))(major,minor,patch);sdk_note(SDK_VERSION,r,0,r==0&&major&&minor&&patch?((U64)*major<<32)|((U64)*minor<<16)|*patch:0,1);return r;}
static PTR sdkWrappers[SDK_COUNT]={sdk_open_a,sdk_open_w,sdk_close,sdk_mode,sdk_available,sdk_kf,
 sdk_tf8,sdk_tf16,sdk_tf32,sdk_tffloat,sdk_tfdouble,sdk_clear_kf,sdk_clear_tf,sdk_dll_open,sdk_dll_close,0,sdk_supported,sdk_supported_a,sdk_supported_w,sdk_wheel_supported_a,sdk_wheel_supported_w,sdk_get_mode,sdk_rate,sdk_thread,sdk_tf_gain,sdk_kf_gain,sdk_max_peak,sdk_max_cont,sdk_damp_max,sdk_damp,sdk_bounds,sdk_version};
static PTR sdk_wrap(PTR library,const char *name,PTR original) {
    if(!original||(U64)name<65536)return original;
    for(U32 i=0;i<SDK_COUNT;i++)if(sdk_equal(name,sdkNames[i])){
        PTR expected=0;
        if(!__atomic_compare_exchange_n(&sdkObservedModule,&expected,library,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)&&expected!=library)return original;
        expected=0;
        if(!__atomic_compare_exchange_n(&sdkOriginal[i],&expected,original,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)&&expected!=original)return original;
        return sdkWrappers[i];
    }
    return original;
}
#ifndef CFB_TEST
typedef PTR (*SdkGetProc)(PTR,const char *);
static SdkGetProc sdkGetProc;
static PTR sdk_get_proc(PTR library,const char *name) {
    PTR original=sdkGetProc(library,name);
    if(!original||(U64)name<65536)return original;
    U16 path[1024];U32 n=GetModuleFileNameW(library,path,1024);
    if(!n||n>=1024)return original;
    U32 start=n;while(start&&path[start-1]!='\\'&&path[start-1]!='/')start--;
    const char leaf[]="trueforce_sdk_x64.dll";U32 i=0;
    if(n-start!=sizeof(leaf)-1)return original;
    for(;leaf[i];i++){U16 c=path[start+i];if(c>='A'&&c<='Z')c+='a'-'A';if(c!=(U16)leaf[i])return original;}
    if(start+i!=n)return original;
    if(name[0]=='l'&&name[1]=='o'&&name[2]=='g'&&name[3]=='i'){
        char label[160];U32 at=text(label,0,"SDK_RESOLVED_");
        U32 k=0;while(name[k]&&k<120){char c=name[k++];if((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_')label[at++]=c;else break;}
        label[at]=0;event(label,1,0);
    }
    return sdk_wrap(library,name,original);
}
static int sdk_range(U32 rva,U32 bytes,U32 size){return rva<size&&bytes<=size-rva;}
static void install_sdk_trace(void) {
    U16 enable[4];const U16 variable[]={'G','9','2','3','_','S','D','K','_','T','R','A','C','E',0};
    if(GetEnvironmentVariableW(variable,enable,4)!=1||enable[0]!='1')return;
    const U16 stopVariable[]={'G','9','2','3','_','S','D','K','_','S','T','O','P','_','F','I','L','E',0};
    U32 stopLength=GetEnvironmentVariableW(stopVariable,sdkStopPath,1024);
    if(stopLength>=1024)sdkStopPath[0]=0;
    unsigned char *base=GetModuleHandleW(0);if(!base||base[0]!='M'||base[1]!='Z')return;
    U32 nt=le32(base+60);if(nt>1024*1024||le32(base+nt)!=0x4550)return;
    unsigned char *opt=base+nt+24;if(opt[0]!=0x0b||opt[1]!=2)return;
    U32 size=le32(opt+56),imports=le32(opt+120),importSize=le32(opt+124);
    if(!sdk_range(imports,importSize,size))return;
    U32 patched=0;
    for(U32 pos=0;pos+20<=importSize;pos+=20){
        U32 oft=le32(base+imports+pos),iat=le32(base+imports+pos+16);
        if(!oft&&!iat)break;if(!oft||iat%8)continue;
        for(U32 j=0;j<65536;j++){
            U64 offset=(U64)j*8;
            if(offset>size||!sdk_range(oft, (U32)offset+8,size)||!sdk_range(iat,(U32)offset+8,size))break;
            U64 hint=le64(base+oft+offset);if(!hint)break;
            if(hint>>63||hint>0xffffffff||!sdk_range((U32)hint,17,size))continue;
            if(!sdk_equal((const char *)(base+hint+2),"GetProcAddress"))continue;
            PTR *slot=(PTR *)(base+iat+offset);U32 old,unused;
            sdkGetProc=(SdkGetProc)*slot;
            if(VirtualProtect(slot,8,4,&old)){
                __atomic_store_n(slot,(PTR)sdk_get_proc,__ATOMIC_RELEASE);
                VirtualProtect(slot,8,old,&unused);patched++;
            }
        }
    }
    event("SDK_TRACE_IAT_PATCHED",patched,0);
}
#endif
