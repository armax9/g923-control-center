/* Offline tests for the DirectInput8 bridge core (host build, fake Win32). */
#include <assert.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CFB_TEST
#ifndef EXPECTED_HAND_FORCE_NEWTONS
#define EXPECTED_HAND_FORCE_NEWTONS 20u
#endif
#include "../observe.c"

void test_sdk_record(U32 index,const SdkMetric *metric){(void)index;(void)metric;}
unsigned char test_shm[SHM_FULL];
_Alignas(8) static unsigned char traceBuffer[TRACE_BYTES];
static int traceEnabled;
volatile unsigned char *test_trace_map(void) { return traceEnabled ? traceBuffer : 0; }
static unsigned char physics[TM_PHYSICS_BYTES];
const unsigned char *test_physics(void) { return physics; }
static unsigned char staticPage[512];
const unsigned char *test_static(void) { return staticPage; }
static U64 nowMs = 1000000, nowTicks = 5000;
static int allocations;
static int repairSnapshot, snapshotYields;
void test_snapshot_yield(void) {
    snapshotYields++;
    if (repairSnapshot) { __atomic_store_n((U32 *)(test_shm + SHM_IN), 2, __ATOMIC_RELEASE); repairSnapshot = 0; }
}
U64 test_unix_ms(void) { return nowMs; }
U32 test_pid(void) { return 4242; }
U64 test_ticks(void) { return nowTicks; }
void test_lock(U64 *p) {
    while (__atomic_exchange_n(p, 1, __ATOMIC_ACQUIRE))
        sched_yield();
}
void test_unlock(U64 *p) { __atomic_store_n(p, 0, __ATOMIC_RELEASE); }
void *test_alloc(U32 n) {
    allocations++;
    return calloc(1, n);
}
void test_free(void *p) {
    allocations--;
    free(p);
}
void test_log(const char *m, U32 v, const GUID *g) { (void)m, (void)v, (void)g; }

static void put32(U32 off, U32 v) { memcpy(test_shm + off, &v, 4); }
static void put64(U32 off, U64 v) { memcpy(test_shm + off, &v, 8); }
static U32 get32(U32 off) {
    U32 v;
    memcpy(&v, test_shm + off, 4);
    return v;
}
static void input(U32 connected, U32 steer, U32 gas, U32 brake, U32 clutch, U32 buttons, U32 hat) {
    put32(0, SHM_MAGIC);
    put32(4, SHM_VERSION);
    put32(8, SHM_SIZE);
    U32 seq = get32(SHM_IN) + 2;
    put32(SHM_IN + 4, connected);
    put64(SHM_IN + 8, nowMs);
    put32(SHM_IN + 16, steer);
    put32(SHM_IN + 20, gas);
    put32(SHM_IN + 24, brake);
    put32(SHM_IN + 28, clutch);
    put32(SHM_IN + 32, buttons);
    put32(SHM_IN + 36, hat);
    put32(SHM_IN, seq);
}
static U32 fx(U32 slot, U32 word) { return get32(SHM_FX + slot * SHM_FX_SIZE + word * 4); }

typedef struct {
    PTR *v;
} COM;
#define CALL(o, i, T, ...) (((T)((COM *)(o))->v[i])((o), ##__VA_ARGS__))
#define CALL0(o, i, T) (((T)((COM *)(o))->v[i])(o))

/* Equivalent of Windows c_dfDIJoystick2, including the repeated slider
 * offsets for the velocity/acceleration/force aliases. */
static ObjectFormat joy2[164];
static DataFormat joystick2(void) {
    U32 n = 0, base[] = {0, 176, 208, 240};
    const GUID *axes[] = {&guidX, &guidY, &guidZ, 0, 0, &guidRz};
    static const GUID rx = AXISGUID(0x14), ry = AXISGUID(0x15);
    axes[3] = &rx;
    axes[4] = &ry;
    for (U32 aspect = 0; aspect < 4; aspect++) {
        for (U32 a = 0; a < 6; a++)
            joy2[n++] = (ObjectFormat){axes[a], base[aspect] + a * 4, OPTIONAL | DIDFT_AXIS | ANYINSTANCE,
                                       aspect ? 0x100u * (aspect + 1) : 0};
        for (U32 s = 0; s < 2; s++)
            joy2[n++] = (ObjectFormat){&guidSlider, 24 + 4 * s, OPTIONAL | DIDFT_AXIS | ANYINSTANCE,
                                       aspect ? 0x100u * (aspect + 1) : 0};
        if (!aspect) {
            for (U32 p = 0; p < 4; p++)
                joy2[n++] = (ObjectFormat){&guidPov, 32 + 4 * p, OPTIONAL | DIDFT_POV | ANYINSTANCE, 0};
            for (U32 b = 0; b < 128; b++)
                joy2[n++] = (ObjectFormat){0, 48 + b, OPTIONAL | DIDFT_BUTTON | ANYINSTANCE, 0};
        }
    }
    assert(n == 164);
    return (DataFormat){sizeof(DataFormat), sizeof(ObjectFormat), 1, 272, n, joy2};
}

static unsigned physicalCount, physicalReleased, physicalQueries;
static U32 physicalPid;
static Device physicalMetadata;
static U32 metadata_release(Device *d) { (void)d;physicalReleased++;return 1; }
static HR metadata_property(Device *d,const GUID *g,Property *p) {
    (void)d;physicalQueries++;
    if((U64)g==24){((DwordProperty *)p)->value=physicalPid;return OK;}
    if((U64)g==12){HidPathProperty *out=(void *)p;out->interfaceClass=virtualGuid;nameW(out->path,"\\\\?\\hid#vid_046d&pid_c266#metadata");return OK;}
    return INVALID;
}
static const DeviceVT metadata_vtable={.Release=metadata_release,.GetProperty=metadata_property};
static HR metadata_create(Factory *f,const GUID *g,void **out,PTR outer) {
    (void)f;(void)g;(void)outer;physicalMetadata.v=&metadata_vtable;*out=&physicalMetadata;return OK;
}
static HR metadata_enum(Factory *f,U32 kind,PTR callback,PTR context,U32 flags) {
    (void)f;assert(kind==4&&flags==1);
    InstanceA info;instance_info(&info,0);
    for(unsigned i=0;i<physicalCount;i++)((int (*)(const void *,PTR))callback)(&info,context);
    return OK;
}
static void test_hid_discovery(void) {
    const FactoryVT backendVT={.CreateDevice=metadata_create,.EnumDevices=metadata_enum};
    Factory backend={.v=&backendVT};Factory virtualFactory={.real=&backend};
    for(unsigned count=0;count<3;count++){
        physicalCount=count;physicalReleased=physicalQueries=0;physicalPid=0xc266046d;
        Device *device=0;assert(create(&virtualFactory,&virtualGuid,(void **)&device,0)==OK);
        assert(device->hasHidPath==(count==1));assert(physicalReleased==count);assert(physicalQueries==2*count);
        device->v->Release(device);
    }
    physicalCount=1;physicalPid=0xc267046d;
    Device *device=0;assert(create(&virtualFactory,&virtualGuid,(void **)&device,0)==OK);
    assert(!device->hasHidPath);device->v->Release(device);
}
static HR fixture_tf(U64 handle,const short *values,U64 count,double rate,double scale,int selector) {
    assert(handle==42&&count==4&&rate==1000.&&scale==.25&&selector==7);
    assert(values[0]==-32768&&values[1]==42);return OK;
}
static HR fixture_kf(U64 h,double value){assert(h==42&&value==-.125);return 9;}
static HR fixture_supported(U64 h,unsigned char *out){assert(h==42&&out);*out=1;return 0;}
static HR fixture_rate(U64 h,double *out){assert(h==42&&out);*out=.0001;return 0;}
static HR fixture_version(U32 *a,U32 *b,U32 *c){assert(a&&b&&c);*a=1;*b=3;*c=12;return 0;}
static void test_sdk_observation(void) {
    short values[]={-32768,42,0,5};
    PTR wrapped=sdk_wrap((PTR)1,"logiTrueForceSetTorqueTFint16",fixture_tf);
    assert(wrapped!=fixture_tf);
    HR r=((HR(*)(U64,const short*,U64,double,double,int))wrapped)(42,values,4,1000.,.25,7);
    assert(r==0&&sdkMetrics[SDK_TF16].calls==1&&sdkMetrics[SDK_TF16].samples==4);
    assert(sdkMetrics[SDK_TF16].nonzero==1&&sdkMetrics[SDK_TF16].peakMilli==32768000);
    assert(sdk_wrap((PTR)2,"logiTrueForceSetTorqueTFint16",fixture_tf)==fixture_tf);
    assert(sdk_wrap((PTR)1,"unknown",fixture_tf)==fixture_tf);
    assert(sdk_wrap((PTR)1,(const char*)2,fixture_tf)==fixture_tf);
    wrapped=sdk_wrap((PTR)1,"logiTrueForceSetTorqueKF",fixture_kf);
    r=((HR(*)(U64,double))wrapped)(42,-.125);
    assert(r==9&&sdkMetrics[SDK_KF].errors==1&&sdkMetrics[SDK_KF].nonzero==0);
    assert(sdk_peak(0./0.)==0&&sdk_peak(1e20)==0&&sdk_peak(-.5)==500);
    unsigned char supported=0;
    wrapped=sdk_wrap((PTR)1,"logiTrueForceSupportedByDirectInputW",fixture_supported);
    assert(((HR(*)(U64,unsigned char*))wrapped)(42,&supported)==0&&supported==1);
    assert(sdkMetrics[SDK_SUPPORTED_W].lastValue==1&&sdkMetrics[SDK_SUPPORTED_W].errors==0);
    double rate=0;wrapped=sdk_wrap((PTR)1,"logiTrueForceGetHapticRate",fixture_rate);
    assert(((HR(*)(U64,double*))wrapped)(42,&rate)==0&&rate==.0001);
    assert(sdkMetrics[SDK_RATE].lastValue==1);
    U32 major=0,minor=0,patch=0;wrapped=sdk_wrap((PTR)1,"logiWheelGetVersion",fixture_version);
    assert(((HR(*)(U32*,U32*,U32*))wrapped)(&major,&minor,&patch)==0);
    assert(major==1&&minor==3&&patch==12);
    char text[32];U32 length=sdk_decimal(text,0,18446744073709551615ULL);text[length]=0;
    assert(!strcmp(text,"18446744073709551615"));
}
static void test_hid_property(void) {
    Device d; zero(&d,sizeof(d));
    HidPathProperty p; zero(&p,sizeof(p));
    p.header=(Property){sizeof(p),16,0,0};
    assert(property(&d,(const GUID *)12,&p.header,0)==NOTFOUND);
    nameW(d.hidPath.path,"\\\\?\\hid#vid_046d&pid_c266#real-path");
    assert(valid_hid_path(&d.hidPath));
    d.hasHidPath=1;d.hidPath.interfaceClass=virtualGuid;
    assert(property(&d,(const GUID *)12,&p.header,0)==OK);
    assert(same(&p.interfaceClass,&virtualGuid));
    assert(!memcmp(p.path,d.hidPath.path,sizeof(p.path)));
    p.header.size--;assert(property(&d,(const GUID *)12,&p.header,0)==INVALID);p.header.size++;
    p.header.how=1;assert(property(&d,(const GUID *)12,&p.header,0)==INVALID);p.header.how=0;
    p.header.object=1;assert(property(&d,(const GUID *)12,&p.header,0)==INVALID);p.header.object=0;
    assert(property(&d,(const GUID *)12,&p.header,1)==INVALID);
    nameW(p.path,"\\\\?\\hid#vid_046d&pid_c2660#wrong");assert(!valid_hid_path(&p));
    nameW(p.path,"\\\\?\\hid#vid_1234&pid_c266#wrong");assert(!valid_hid_path(&p));
    nameW(p.path,"\\\\?\\HID#VID_046D&PID_C266#actual");assert(valid_hid_path(&p));
    for(U32 i=0;i<260;i++)p.path[i]='a';assert(!valid_hid_path(&p));
}
static void test_force_units(void) {
    Device d; zero(&d,sizeof(d)); d.wide=1;
    ObjectW object;
    object_info(&d,&object,0);
    assert(object.maxForce==EXPECTED_HAND_FORCE_NEWTONS && object.resolution==256);
    for(U32 source=1;source<4;source++) {
        object_info(&d,&object,source);
        assert(object.maxForce==0 && object.resolution==0);
    }
}
/* No-HID contract regressions: actual COM wrappers and published force records. */
static void test_download_and_playback_contract(void) {
    Factory *factory = 0; Device *d = 0; Effect *e = 0;
    input(1,32768,65535,65535,65535,0,8);
    assert(DirectInput8Create(0,0x800,&iidW,(void **)&factory,0)==OK);
    assert(factory->v->CreateDevice(factory,&virtualGuid,(void **)&d,0)==OK);
    DataFormat f=joystick2(); assert(d->v->SetDataFormat(d,&f)==OK); assert(d->v->Acquire(d)==OK);
    U32 axis=0,status=0; I32 direction=1,magnitude=5000;
    EffectParams p={sizeof(p),0x10|2,0xffffffffu,0,10000,0xffffffffu,0,1,&axis,&direction,0,4,&magnitude,0};
    assert(d->v->CreateEffect(d,&constantGuid,&p,&e,0)==OK);
    assert(e->v->Start(e,1,0)==OK);
    U32 starts=e->starts;
    magnitude=-9000; direction=-1; p.gain=3000;
    assert(e->v->SetParameters(e,&p,0x144|0x80000000u)==OK);
    assert((I32)fx(0,16)==5000 && fx(0,5)==10000 && (I32)fx(0,9)==1 && fx(0,1)==1);
    I32 requested=0,requestedDirection=0; U32 requestedAxis=0;
    EffectParams q={0};q.size=sizeof(q);q.axes=1;q.axisIDs=&requestedAxis;q.directions=&requestedDirection;q.params=&requested;q.paramBytes=4;
    assert(e->v->GetParameters(e,&q,0x144)==OK);
    assert(requested==-9000 && q.gain==3000 && requestedDirection==-1);
    assert(e->v->Download(e)==OK);
    assert((I32)fx(0,16)==-9000 && fx(0,5)==3000 && (I32)fx(0,9)==-1 && fx(0,2)==starts);
    /* Pending duration must not change the already downloaded infinite effect. */
    p.duration=1000;magnitude=7000;
    assert(e->v->SetParameters(e,&p,0x101|0x80000000u)==OK);
    nowTicks+=10;
    assert(e->v->GetEffectStatus(e,&status)==OK && status==1);
    assert(e->v->Start(e,1,0x80000000u)==OK);
    assert(fx(0,3)==0xffffffffu && (I32)fx(0,16)==-9000);
    assert(e->v->Start(e,1,0)==OK && fx(0,3)==1000 && (I32)fx(0,16)==7000);
    nowTicks+=2;assert(e->v->GetEffectStatus(e,&status)==OK && status==0);
    assert(e->v->Unload(e)==OK);
    assert(e->v->Start(e,1,0x80000000u)==(HR)0x80040203u && fx(0,1)==0);
    assert(e->v->Start(e,1,0)==OK);
    /* Mutually exclusive control flags fail before mutating requested parameters. */
    magnitude=1234;
    assert(e->v->SetParameters(e,&p,0x100|0xa0000000u)==INVALID);
    assert(e->v->SetParameters(e,&p,0x100|0xc0000000u)==INVALID);
    q.paramBytes=4;assert(e->v->GetParameters(e,&q,0x100)==OK && requested==7000);
    assert(d->v->Unacquire(d)==OK);
    assert(e->v->SetParameters(e,&p,0x100)==3); /* parameters saved; automatic download skipped */
    q.paramBytes=4;assert(e->v->GetParameters(e,&q,0x100)==OK && requested==1234);
    assert(e->v->Download(e)==NOTACQUIRED);
    input(1,32768,65535,65535,65535,0,8);assert(d->v->Acquire(d)==OK);
    assert(e->v->Start(e,1,0)==OK && (I32)fx(0,16)==1234);
    e->v->Release(e);d->v->Release(d);factory->v->Release(factory);assert(allocations==0);
}
static void test_authoritative_effect_time(void) {
    Factory *factory=0;Device *d=0;Effect *e=0;
    input(1,32768,65535,65535,65535,0,8);
    assert(DirectInput8Create(0,0x800,&iidW,(void **)&factory,0)==OK);
    assert(factory->v->CreateDevice(factory,&virtualGuid,(void **)&d,0)==OK);
    DataFormat f=joystick2();assert(d->v->SetDataFormat(d,&f)==OK);assert(d->v->Acquire(d)==OK);
    U32 axis=0,status=0;I32 direction=1,magnitude=5000;
    EffectParams p={sizeof(p),0x10|2,3000000,0,10000,0xffffffffu,0,1,&axis,&direction,0,4,&magnitude,0};
    assert(d->v->CreateEffect(d,&constantGuid,&p,&e,0)==OK);assert(e->v->Start(e,1,0)==OK);
    nowTicks+=2000;p.duration=1500000;
    assert(e->v->SetParameters(e,&p,1)==OK);assert(e->v->GetEffectStatus(e,&status)==OK && status==0 && fx(0,1)==0);
    /* Increasing an already expired effect's duration must not revive it. */
    p.duration=4000000;assert(e->v->SetParameters(e,&p,1)==OK);
    assert(e->v->GetEffectStatus(e,&status)==OK && status==0);
    p.duration=3000000;assert(e->v->SetParameters(e,&p,1|0x20000000u)==OK);
    nowTicks+=1000;p.duration=4000000;assert(e->v->SetParameters(e,&p,1)==OK);
    nowTicks+=2500;assert(e->v->GetEffectStatus(e,&status)==OK && status==1);
    nowTicks+=500;assert(e->v->GetEffectStatus(e,&status)==OK && status==0);
    p.duration=1000000;assert(e->v->SetParameters(e,&p,1)==OK);assert(e->v->Start(e,2,0)==OK);
    nowTicks+=500;p.duration=2000000;assert(e->v->SetParameters(e,&p,1)==OK);
    nowTicks+=2000;assert(e->v->GetEffectStatus(e,&status)==OK && status==1);
    nowTicks+=1500;assert(e->v->GetEffectStatus(e,&status)==OK && status==0);
    p.duration=1000;assert(e->v->SetParameters(e,&p,1|0x20000000u)==OK);
    p.duration=0xffffffffu;assert(e->v->SetParameters(e,&p,1)==OK);
    nowTicks+=2000;assert(e->v->GetEffectStatus(e,&status)==OK && status==1);
    p.duration=1000;assert(e->v->SetParameters(e,&p,1)==OK);
    assert(e->v->GetEffectStatus(e,&status)==OK && status==0);
    p.duration=0;assert(e->v->SetParameters(e,&p,1|0x20000000u)==OK);
    assert(e->v->GetEffectStatus(e,&status)==OK && status==0);
    /* Pause freezes start delay, duration and exported playback age. */
    p.duration=500000;p.startDelay=200000;
    assert(e->v->SetParameters(e,&p,0x201|0x20000000u)==OK);
    U32 start=e->starts;nowTicks+=100;
    assert(e->v->GetEffectStatus(e,&status)==OK && status==0);
    assert(d->v->SendForceFeedbackCommand(d,4)==OK);assert(fx(0,23)==101);
    nowTicks+=1000;assert(d->v->Poll(d)==OK);assert(fx(0,23)==101);
    assert(d->v->SendForceFeedbackCommand(d,8)==OK);assert(e->starts==start);
    nowTicks+=100;assert(e->v->GetEffectStatus(e,&status)==OK && status==1);
    assert(d->v->Poll(d)==OK && fx(0,23)==201 && get32(SHM_FF+32)==0x314d4954u);
    nowTicks+=500;assert(e->v->GetEffectStatus(e,&status)==OK && status==0);
    e->v->Release(e);d->v->Release(d);factory->v->Release(factory);assert(allocations==0);
}

int main(void) {
    test_download_and_playback_contract();
    test_authoritative_effect_time();
    test_force_units();
    test_sdk_observation();
    test_hid_property();
    test_hid_discovery();
    input(1,32768,65535,65535,65535,0,8);
    put32(SHM_IN,1); repairSnapshot=1; Snapshot snapshot; U32 reason=0;
    assert(read_snapshot_status(&snapshot,&reason)); assert(snapshotYields==1);
    put32(SHM_IN,1); snapshotYields=0;
    assert(!read_snapshot_status(&snapshot,&reason)); assert(reason==2); assert(snapshotYields==128);
    memset(test_shm,0,sizeof(test_shm));

    COM *factory = 0, *device = 0, *constant = 0, *damper = 0;
    assert(DirectInput8Create(0, 0x800, &iidW, (void **)&factory, 0) == OK);
    assert(CALL(factory, 3, HR (*)(PTR, const GUID *, void **, PTR), &virtualGuid, (void **)&device, 0) == OK);

    DataFormat f = joystick2();
    assert(CALL(device, 11, HR (*)(PTR, const DataFormat *), &f) == OK);
    assert(CALL0(device, 7, HR (*)(PTR)) == INPUTLOST); /* app not sharing yet */

    input(1, 40000, 1000, 2000, 3000, 0x5, 8);
    assert(CALL0(device, 7, HR (*)(PTR)) == OK);
    unsigned char st[272];
    memset(st, 0xcc, sizeof(st));
    assert(CALL(device, 9, HR (*)(PTR, U32, PTR), 272, st) == OK);
    I32 *l = (I32 *)st;
    assert(l[0] == 40000 && l[1] == 1000 && l[5] == 2000 && l[6] == 3000);
    assert(l[2] == 0 && l[3] == 0 && l[4] == 0 && l[7] == 0);
    for (int p = 0; p < 4; p++)
        assert(l[8 + p] == -1); /* centered POVs: no phantom D-pad presses */
    assert(st[48] == 128 && st[49] == 0 && st[50] == 128 && st[51] == 0);
    for (int i = 176; i < 272; i++)
        assert(st[i] == 0);

    input(1, 32768, 65535, 65535, 65535, 0, 0);
    assert(CALL(device, 9, HR (*)(PTR, U32, PTR), 272, st) == OK && l[8] == 0);

    /* Constant force on X by offset, Cartesian. */
    U32 axis = 0;
    I32 dir = 1, magnitude = 5000;
    EffectParams e = {sizeof(EffectParams), 0x10 | 2, 0xffffffffu, 0, 10000, 0xffffffffu, 0, 1, &axis, &dir, 0, 4,
                      &magnitude, 0};
    assert(CALL(device, 18, HR (*)(PTR, const GUID *, const EffectParams *, void **, PTR), &constantGuid, &e,
                (void **)&constant, 0) == OK);
    assert(CALL(constant, 7, HR (*)(PTR, U32, U32), 1, 0) == OK);
    assert(get32(SHM_FF) % 2 == 0 && get32(SHM_FF + 4) == 4242 && get32(SHM_FF + 16) == 1);
    assert(fx(0, 0) == 1 && fx(0, 1) == 1 && fx(0, 2) == 1 && (I32)fx(0, 16) == 5000 && fx(0, 8) == 0);
    assert(fx(0, 6) == 0x10 && (I32)fx(0, 9) == 1);

    /* Per-frame magnitude updates must not restart the effect. */
    magnitude = -7000;
    assert(CALL(constant, 6, HR (*)(PTR, const EffectParams *, U32), &e, 0x100) == OK);
    assert((I32)fx(0, 16) == -7000 && fx(0, 2) == 1 && fx(0, 1) == 1);

    /* Damper, single condition block. */
    I32 cond[6] = {0, 4000, 3000, 10000, 10000, 100};
    EffectParams c = {sizeof(EffectParams), 0x10 | 2, 0xffffffffu, 0, 8000, 0xffffffffu, 0, 1, &axis, &dir, 0, 24,
                      cond, 0};
    assert(CALL(device, 18, HR (*)(PTR, const GUID *, const EffectParams *, void **, PTR), &damperGuid, &c,
                (void **)&damper, 0) == OK);
    assert(CALL(damper, 7, HR (*)(PTR, U32, U32), 0xffffffffu, 0) == OK);
    assert(fx(1, 0) == 9 && fx(1, 1) == 1 && fx(1, 5) == 8000 && fx(1, 17) == 4000 && fx(1, 21) == 100);
    assert(fx(1, 22) == 0xffffffffu);

    /* Actuators and pause are reported to the app. */
    assert(CALL(device, 22, HR (*)(PTR, U32), 0x4) == OK && (get32(SHM_FF + 24) & 1));
    assert(CALL(device, 22, HR (*)(PTR, U32), 0x8 | 0x10) == OK && get32(SHM_FF + 24) == 0);

    /* ACC physics page is mirrored on each new packetId. */
    staticPage[412] = 8200 & 0xff; staticPage[413] = 8200 >> 8;
    physics[0] = 7;
    memcpy(physics + 20, &(I32){6500}, 4); /* rpms */
    assert(CALL0(device, 25, HR (*)(PTR)) == OK);
    assert(get32(SHM_TM) % 2 == 0 && get32(SHM_TM + 4) == 1 && get32(SHM_TM + 8) == TM_PHYSICS_BYTES);
    assert(get32(SHM_TM + SHM_TM_DATA) == 7 && get32(SHM_TM + SHM_TM_DATA + 20) == 6500);
    assert(get32(SHM_TM + 24) == 8200); /* static maxRpm */
    U32 tseq = get32(SHM_TM);
    assert(CALL0(device, 25, HR (*)(PTR)) == OK && get32(SHM_TM) == tseq); /* unchanged packet: no copy */

    /* Stale input: lost, effects stop, buffer neutral. */
    nowMs += 600;
    memset(st, 0xcc, sizeof(st));
    assert(CALL(device, 9, HR (*)(PTR, U32, PTR), 272, st) == INPUTLOST);
    assert(l[0] == 32768 && l[8] == -1 && st[48] == 0);
    assert(fx(0, 1) == 0 && fx(1, 1) == 0 && get32(SHM_FF + 16) == 0);

    nowMs += 10;
    input(1, 32768, 65535, 65535, 65535, 0, 8);
    assert(CALL0(device, 7, HR (*)(PTR)) == OK);
    assert(CALL(constant, 7, HR (*)(PTR, U32, U32), 1, 0) == OK && fx(0, 2) == 2 && fx(0, 1) == 1);
    assert(CALL0(device, 8, HR (*)(PTR)) == OK && fx(0, 1) == 0);

    /* Standard 80-byte DIJOYSTATE. */
    DataFormat f1 = {sizeof(DataFormat), sizeof(ObjectFormat), 1, 80, 44, joy2};
    for (U32 i = 0; i < 44; i++)
        assert(joy2[i].offset < 80);
    assert(CALL(device, 11, HR (*)(PTR, const DataFormat *), &f1) == OK);

    assert(CALL0(constant, 2, U32 (*)(PTR)) == 0);
    assert(CALL0(damper, 2, U32 (*)(PTR)) == 0);
    assert(fx(0, 0) == 0 && fx(1, 0) == 0);
    assert(CALL0(device, 2, U32 (*)(PTR)) == 0);
    assert(CALL0(factory, 2, U32 (*)(PTR)) == 0);
    assert(allocations == 0 && DllCanUnloadNow() == 0);
    puts("PASS bridge core: joystick2 format, shared-memory input, effect mirroring, lifetimes");
    return 0;
}
