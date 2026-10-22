/* SPDX-License-Identifier: MIT
 * Optional bounded diagnostics. The collector creates this separate mapping
 * before game start. The DLL never creates files or writes disk per event.
 * One producer (publishLock), any number of read-only consumers, LE Win64.
 */
#define TRACE_MAGIC 0x52543947u /* G9TR */
#define TRACE_SLOTS 128u
#define TRACE_STRIDE 4096u
#define TRACE_HEADER 64u
#define TRACE_BYTES (TRACE_HEADER + TRACE_SLOTS * TRACE_STRIDE)
#define TRACE_FORCE_BYTES (SHM_FX + SHM_FX_COUNT * SHM_FX_SIZE - SHM_FF)
#define TRACE_INPUT_BYTES 48u
#ifdef CFB_TEST
extern volatile unsigned char *test_trace_map(void);
#define trace_map test_trace_map
#else
static volatile unsigned char *traceView;
static int traceTried;
/* Only a pre-existing owned-session path; absence disables capture for this
 * DLL instance. Keeping the ring optional preserves normal installs. */
static volatile unsigned char *trace_map(void) {
    if (traceTried) return traceView;
    traceTried = 1;
    const char *head = "Z:\\tmp\\crossover-ffb-", *tail = "\\trace-v1.bin";
    U16 path[128];U32 n=0;
    for(U32 i=0;head[i];i++)path[n++]=(U16)head[i];
    for(U32 i=7;i<17 && uidSlot[i]>='0' && uidSlot[i]<='9';i++)path[n++]=(U16)uidSlot[i];
    for(U32 i=0;;i++){path[n++]=(U16)tail[i];if(!tail[i])break;}
    PTR f=CreateFileW(path,0xc0000000u,7,0,3,0x80,0);
    if(f==(PTR)(~(U64)0))return 0;
    long long bytes=0;PTR section=GetFileSizeEx(f,&bytes) && bytes==TRACE_BYTES ? CreateFileMappingW(f,0,4,0,TRACE_BYTES,0):0;
    CloseHandle(f);
    if(!section)return 0;
    traceView=MapViewOfFile(section,6,0,0,TRACE_BYTES);CloseHandle(section);
    return traceView;
}
#endif
static void trace_force(volatile unsigned char *shared, U32 operation, U32 flags, U32 effectSlot, U32 result) {
    volatile unsigned char *ring=trace_map();
    if(!ring || ld32(ring)!=TRACE_MAGIC || ld32(ring+4)!=1 || ld32(ring+8)!=TRACE_SLOTS || ld32(ring+12)!=TRACE_STRIDE)return;
    U32 pid=process_id(),owner=ld32(ring+24);
    if(!owner){U32 empty=0;__atomic_compare_exchange_n((volatile U32 *)(ring+24),&empty,pid,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);owner=ld32(ring+24);}
    if(owner!=pid)return; /* Never interleave two game processes in one capture. */
    U64 seq=__atomic_load_n((volatile U64 *)(ring+16),__ATOMIC_ACQUIRE)+1;
    if(seq>0x7fffffffffffffffULL)return;
    volatile unsigned char *slot=ring+TRACE_HEADER+((seq-1)%TRACE_SLOTS)*TRACE_STRIDE;
    st64(slot,seq*2-1);__atomic_thread_fence(__ATOMIC_SEQ_CST);
    st64(slot+8,seq);st64(slot+16,le64((const unsigned char *)(shared+SHM_FF+8)));
    st64(slot+24,ticks());st32(slot+32,TRACE_FORCE_BYTES);st32(slot+36,0);
    for(U32 i=40;i<TRACE_STRIDE;i++)slot[i]=0;
    st32(slot+40,operation);st32(slot+44,flags);st32(slot+48,effectSlot);st32(slot+52,result);
    for(U32 i=0;i<TRACE_FORCE_BYTES;i++)slot[64+i]=shared[SHM_FF+i];
    /* Input has an independent native producer: retain it only if coherent. */
    for(U32 attempt=0;attempt<3;attempt++){
        U32 before=ld32(shared+SHM_IN);if(before&1)continue;
        for(U32 i=0;i<TRACE_INPUT_BYTES;i++)slot[64+TRACE_FORCE_BYTES+i]=shared[SHM_IN+i];
        __atomic_thread_fence(__ATOMIC_ACQUIRE);
        if(ld32(shared+SHM_IN)==before){st32(slot+36,TRACE_INPUT_BYTES);break;}
    }
    __atomic_thread_fence(__ATOMIC_RELEASE);st64(slot,seq*2);
    st64(ring+16,seq);
}
