/* SPDX-License-Identifier: MIT
 * Optional per-game loader. Keeps the existing dinput8 graphics mod in the
 * call chain; all WinMM calls are tail-forwarded with their original ABI.
 */
typedef unsigned int U32;typedef unsigned long long U64;typedef unsigned short U16;typedef void* PTR;typedef int HR;
#define IMPORT __declspec(dllimport)
IMPORT PTR GetModuleHandleW(const U16*);IMPORT U32 GetModuleFileNameW(PTR,U16*,U32);IMPORT U32 GetSystemDirectoryW(U16*,U32);IMPORT PTR LoadLibraryW(const U16*);IMPORT PTR GetProcAddress(PTR,const char*);IMPORT int VirtualProtect(PTR,U64,U32,U32*);IMPORT U32 GetEnvironmentVariableW(const U16*,U16*,U32);
extern const char* winmm_names[];
static PTR module,realWinmm;static PTR(*originalGetProc)(PTR,const char*);
static HR(*originalCreate)(PTR,U32,PTR,PTR*,PTR);static HR(*bridgeCreate)(PTR,U32,PTR,PTR*,PTR);
static int equal(const char*a,const char*b){for(U32 i=0;i<256;i++){if(a[i]!=b[i])return 0;if(!a[i])return 1;}return 0;}
static U32 le32(const unsigned char*p){return p[0]|((U32)p[1]<<8)|((U32)p[2]<<16)|((U32)p[3]<<24);}
static PTR proc(PTR lib,const char*name){return originalGetProc?originalGetProc(lib,name):GetProcAddress(lib,name);}
static U64 missing(void){return 0;}
PTR winmm_resolve(U32 i){
 if(!realWinmm){U16 path[1024];U32 n=GetSystemDirectoryW(path,980);const char*leaf="\\winmm.dll";if(!n||n>=980)return missing;for(U32 k=0;;k++){path[n+k]=leaf[k];if(!leaf[k])break;}realWinmm=LoadLibraryW(path);}
 PTR fn=realWinmm?proc(realWinmm,winmm_names[i]):0;return fn?fn:(PTR)missing;
}
static void release(PTR object){if(object){PTR*v=*(PTR**)object;((U32(*)(PTR))v[2])(object);}}
static HR chained_create(PTR instance,U32 version,PTR iid,PTR*out,PTR outer){
 if(!out)return originalCreate(instance,version,iid,out,outer);
 PTR base=0,virtualDevice=0;HR result=originalCreate(instance,version,iid,&base,outer);
 if(result<0||!base){if(out)*out=base;return result;}
 if(!out||outer){if(out)*out=base;return result;}
 HR bridge=bridgeCreate(instance,version,iid,&virtualDevice,outer);
 if(bridge<0||!virtualDevice){*out=base;return result;}
 release(base);*out=virtualDevice;return bridge;
}
static PTR intercepted_proc(PTR lib,const char*name){
 PTR actual=originalGetProc(lib,name);
 if(!actual||(U64)name<65536||!equal(name,"DirectInput8Create"))return actual;
 U16 path[1024];U32 n=GetModuleFileNameW(lib,path,1024),begin=n;if(!n||n>=1024)return actual;
 while(begin&&path[begin-1]!='\\'&&path[begin-1]!='/')begin--;
 const char*leaf="dinput8.dll";U32 k=0;for(;leaf[k];k++){U16 c=path[begin+k];if(c>='A'&&c<='Z')c+=32;if(c!=(U16)leaf[k])return actual;}if(begin+k!=n)return actual;
 if(originalCreate&&originalCreate!=(PTR)actual)return actual;
 if(!bridgeCreate){
  n=GetModuleFileNameW(module,path,1024);if(!n||n>=980)return actual;while(n&&path[n-1]!='\\'&&path[n-1]!='/')n--;
  const char*b="g923_bridge.dll";for(k=0;;k++){path[n+k]=b[k];if(!b[k])break;}
  PTR helper=LoadLibraryW(path);if(!helper)return actual;bridgeCreate=(void*)originalGetProc(helper,"DirectInput8Create");
 }
 if(!bridgeCreate)return actual;originalCreate=(void*)actual;return chained_create;
}
static int file_opt_in(void){
 U16 path[1024];U32 n=GetModuleFileNameW(module,path,1024);if(!n||n>=980)return 0;
 while(n&&path[n-1]!='\\'&&path[n-1]!='/')n--;
 const char*leaf="g923-chain.enabled";for(U32 k=0;;k++){path[n+k]=leaf[k];if(!leaf[k])break;}
 const U16 kernel[]={'k','e','r','n','e','l','3','2','.','d','l','l',0};
 U32(*attributes)(const U16*)=(void*)GetProcAddress(GetModuleHandleW(kernel),"GetFileAttributesW");
 if(!attributes)return 0;U32 value=attributes(path);return value!=0xffffffff&&!(value&0x10);
}
static void hook(void){
 const U16 variable[]={'G','9','2','3','_','D','I','N','P','U','T','_','I','A','T',0};U16 flag[4];if((GetEnvironmentVariableW(variable,flag,4)!=1||flag[0]!='1')&&!file_opt_in())return;
 unsigned char*base=GetModuleHandleW(0);if(!base||base[0]!='M'||base[1]!='Z')return;U32 nt=le32(base+60);if(nt>1048576||le32(base+nt)!=0x4550)return;
 unsigned char*opt=base+nt+24;if(opt[0]!=0x0b||opt[1]!=2)return;U32 size=le32(opt+56),imports=le32(opt+120),bytes=le32(opt+124);
 if(imports>=size||bytes>size-imports)return;
 for(U32 p=0;p+20<=bytes;p+=20){U32 oft=le32(base+imports+p),iat=le32(base+imports+p+16);if(!oft||!iat)continue;
  for(U32 j=0;j<16384;j++){if(oft>=size||iat>=size||size-oft<8||size-iat<8||j>(size-oft-8)/8||j>(size-iat-8)/8)break;U64 rva=*(U64*)(base+oft+j*8);if(!rva)break;if(rva>>63)continue;if(rva>=size||size-rva<18)continue;
   if(!equal((char*)(base+rva+2),"GetProcAddress"))continue;PTR*slot=(PTR*)(base+iat+j*8);U32 protection;originalGetProc=(void*)*slot;
   if(VirtualProtect(slot,8,4,&protection)){*slot=intercepted_proc;U32 unused;VirtualProtect(slot,8,protection,&unused);}return;
  }
 }
}
__declspec(dllexport) int DllMain(PTR h,U32 reason,PTR reserved){(void)reserved;if(reason==1){module=h;hook();}return 1;}
