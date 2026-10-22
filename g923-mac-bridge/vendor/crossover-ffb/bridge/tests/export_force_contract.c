/* Cross-language oracle fixtures. Fake Win32 only; never opens HID or Wine. */
#define main bridge_original_test_main
#include "test_bridge.c"
#undef main
static int ringMode;
static void frame(const char *name, double expected) {
    if(ringMode)return;
    printf("{\"case\":\"%s\",\"expected_force\":%.9f,\"words\":[",name,expected);
    for (U32 i=0;i<(64+96*32)/4;i++) printf("%s%u",i?",":"",get32(SHM_FF+i*4));
    puts("]}");
}
int main(int argc,char **argv) {
    ringMode=argc==2 && !strcmp(argv[1],"--ring");
    if(ringMode){traceEnabled=1;put32(0,SHM_MAGIC);*(U32 *)(traceBuffer+0)=TRACE_MAGIC;*(U32 *)(traceBuffer+4)=1;*(U32 *)(traceBuffer+8)=TRACE_SLOTS;*(U32 *)(traceBuffer+12)=TRACE_STRIDE;}
    Factory *factory=0;Device *d=0;Effect *e=0;
    input(1,32768,65535,65535,65535,0,8);
    assert(DirectInput8Create(0,0x800,&iidW,(void **)&factory,0)==OK);
    assert(factory->v->CreateDevice(factory,&virtualGuid,(void **)&d,0)==OK);
    DataFormat f=joystick2();assert(d->v->SetDataFormat(d,&f)==OK);assert(d->v->Acquire(d)==OK);
    U32 axis=0;I32 direction=1,magnitude=5000;
    EffectParams p={sizeof(p),0x10|2,0xffffffffu,0,10000,0xffffffffu,0,1,&axis,&direction,0,4,&magnitude,0};
    assert(d->v->CreateEffect(d,&constantGuid,&p,&e,0)==OK);assert(e->v->Start(e,1,0)==OK);frame("constant",-.5);
    magnitude=-9000;assert(e->v->SetParameters(e,&p,0x100|0x80000000u)==OK);frame("pending_not_applied",-.5);
    assert(e->v->Download(e)==OK);frame("download_committed",.9);
    assert(e->v->Unload(e)==OK);frame("unloaded",0);
    assert(e->v->Start(e,1,0x80000000u)==(HR)0x80040203u);frame("start_without_download_rejected",0);
    e->v->Release(e);
    I32 ramp[2]={0,10000};p.duration=1000000;p.startDelay=200000;p.params=ramp;p.paramBytes=8;
    assert(d->v->CreateEffect(d,&effectGuids[1],&p,&e,0)==OK);assert(e->v->Start(e,1,0)==OK);
    nowTicks+=100;assert(d->v->Poll(d)==OK);frame("start_delay",0);
    nowTicks+=200;assert(d->v->Poll(d)==OK);frame("ramp_late_observer",-.1);
    assert(d->v->SendForceFeedbackCommand(d,4)==OK);nowTicks+=5000;assert(d->v->Poll(d)==OK);frame("paused",0);
    assert(d->v->SendForceFeedbackCommand(d,8)==OK);frame("resumed_same_phase",-.1);
    nowTicks+=400;assert(d->v->Poll(d)==OK);frame("ramp_half",-.5);
    p.duration=400000;assert(e->v->SetParameters(e,&p,1)==OK);frame("duration_shrunk_finished",0);
    if(ringMode){
        e->v->Release(e);e=0;p.duration=0xffffffffu;p.startDelay=0;p.params=&magnitude;p.paramBytes=4;
        assert(d->v->CreateEffect(d,&constantGuid,&p,&e,0)==OK);assert(e->v->Start(e,1,0)==OK);
        for(U32 i=0;i<200;i++){nowTicks++;magnitude=i%2?2500:-2500;assert(e->v->SetParameters(e,&p,0x100)==OK);}
        fwrite(traceBuffer,1,TRACE_BYTES,stdout);
    }
    e->v->Release(e);d->v->Release(d);factory->v->Release(factory);assert(allocations==0);
    return 0;
}
