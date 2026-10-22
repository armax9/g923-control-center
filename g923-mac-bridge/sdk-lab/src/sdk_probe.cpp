// SPDX-License-Identifier: GPL-3.0-only
// Inventory only by default. Explicit availability mode calls SDK lifecycle; never torque APIs.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <setupapi.h>
#include <hidsdi.h>
#include <hidpi.h>
#include <wintrust.h>
#include <softpub.h>
#include <cstdio>
#include <cwchar>
#include <string>
#include <vector>
static std::string utf8(const wchar_t* s){if(!s)return "";int n=WideCharToMultiByte(CP_UTF8,0,s,-1,nullptr,0,nullptr,nullptr);if(n<=1)return "";std::string b(n,0);WideCharToMultiByte(CP_UTF8,0,s,-1,b.data(),n,nullptr,nullptr);b.resize(n-1);return b;}
static std::string quoted(const std::string& s){std::string r="\"";for(unsigned char c:s){if(c=='"'||c=='\\'){r+='\\';r+=char(c);}else if(c<32){char t[7];std::snprintf(t,sizeof(t),"\\u%04x",c);r+=t;}else r+=char(c);}return r+'"';}
static void error(const char* event,DWORD code){std::printf("{\"event\":\"%s\",\"error\":%lu}\n",event,(unsigned long)code);}
static int registry(){
 const wchar_t* paths[]={L"SOFTWARE\\Classes\\CLSID\\{e8dfb59f-141f-40e4-8dd4-5526ead25a4c}",L"SOFTWARE\\Classes\\CLSID\\{e8dfb59f-141f-40e4-8dd4-5526ead25a4c}\\InprocServer32",L"SOFTWARE\\Classes\\CLSID\\{63bd165d-1584-4e75-ab56-08330350545f}\\ServerBinary"};
 for(auto key:paths){HKEY h;auto rc=RegOpenKeyExW(HKEY_LOCAL_MACHINE,key,0,KEY_READ|KEY_WOW64_64KEY,&h);wchar_t value[32768]{};DWORD n=sizeof(value),type=0;if(rc==ERROR_SUCCESS){rc=RegQueryValueExW(h,nullptr,nullptr,&type,(BYTE*)value,&n);RegCloseKey(h);}value[32767]=0;std::printf("{\"event\":\"registry\",\"key\":%s,\"status\":%ld,\"type\":%lu,\"value\":%s}\n",quoted(utf8(key)).c_str(),(long)rc,(unsigned long)type,quoted(rc==0?utf8(value):"").c_str());}return 0;
}
static int inventory(){GUID hid;HidD_GetHidGuid(&hid);auto set=SetupDiGetClassDevsW(&hid,nullptr,nullptr,DIGCF_PRESENT|DIGCF_DEVICEINTERFACE);if(set==INVALID_HANDLE_VALUE){error("hid_setup",GetLastError());return 1;}int found=0,unreadable=0;DWORD final=0;
 for(DWORD i=0;;++i){SP_DEVICE_INTERFACE_DATA item{};item.cbSize=sizeof(item);if(!SetupDiEnumDeviceInterfaces(set,nullptr,&hid,i,&item)){final=GetLastError();break;}
 DWORD needed=0;SetupDiGetDeviceInterfaceDetailW(set,&item,nullptr,0,&needed,nullptr);if(needed<sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W)||needed>1024*1024){++unreadable;continue;}
 std::vector<BYTE>b(needed);auto detail=(SP_DEVICE_INTERFACE_DETAIL_DATA_W*)b.data();detail->cbSize=sizeof(*detail);if(!SetupDiGetDeviceInterfaceDetailW(set,&item,detail,needed,nullptr,nullptr)){++unreadable;continue;}
 // Zero desired access; descriptor/attribute queries only, never GENERIC_WRITE.
 HANDLE h=CreateFileW(detail->DevicePath,0,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,0,nullptr);if(h==INVALID_HANDLE_VALUE){++unreadable;continue;}
 HIDD_ATTRIBUTES a{};a.Size=sizeof(a);if(HidD_GetAttributes(h,&a)&&a.VendorID==0x046d&&(a.ProductID==0xc266||a.ProductID==0xc267)){
 ++found;HIDP_CAPS caps{};PHIDP_PREPARSED_DATA data=nullptr;LONG result=0;if(HidD_GetPreparsedData(h,&data)){result=HidP_GetCaps(data,&caps);HidD_FreePreparsedData(data);}
 std::printf("{\"event\":\"g923_hid\",\"vid\":%u,\"pid\":%u,\"usage_page\":%u,\"usage\":%u,\"input_bytes\":%u,\"output_bytes\":%u,\"feature_bytes\":%u,\"caps_status\":%ld,\"path\":%s}\n",a.VendorID,a.ProductID,caps.UsagePage,caps.Usage,caps.InputReportByteLength,caps.OutputReportByteLength,caps.FeatureReportByteLength,(long)result,quoted(utf8(detail->DevicePath)).c_str());}
 CloseHandle(h);}
 SetupDiDestroyDeviceInfoList(set);std::printf("{\"event\":\"hid_summary\",\"g923_interfaces\":%d,\"unreadable_interfaces\":%d,\"enumeration_error\":%lu,\"absence_conclusive\":false,\"motor_output_sent\":false}\n",found,unreadable,(unsigned long)final);return final==ERROR_NO_MORE_ITEMS?0:1;}
static int verify(const wchar_t* file){WINTRUST_FILE_INFO fi{};fi.cbStruct=sizeof(fi);fi.pcwszFilePath=file;WINTRUST_DATA d{};d.cbStruct=sizeof(d);d.dwUIChoice=WTD_UI_NONE;d.fdwRevocationChecks=WTD_REVOKE_NONE;d.dwUnionChoice=WTD_CHOICE_FILE;d.pFile=&fi;d.dwStateAction=WTD_STATEACTION_VERIFY;d.dwProvFlags=WTD_CACHE_ONLY_URL_RETRIEVAL;GUID action=WINTRUST_ACTION_GENERIC_VERIFY_V2;LONG r=WinVerifyTrust(nullptr,&action,&d);std::printf("{\"event\":\"signature\",\"path\":%s,\"status_hex\":\"%08lx\",\"trusted_here\":%s,\"publisher_verified_by_probe\":false,\"revocation_checked\":false}\n",quoted(utf8(file)).c_str(),(unsigned long)(DWORD)r,r==0?"true":"false");d.dwStateAction=WTD_STATEACTION_CLOSE;WinVerifyTrust(nullptr,&action,&d);return r==0?0:4;}
static int load(const wchar_t* file){
 // This explicit mode runs DllMain. It is NOT an SDK/device functional test.
 SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOOPENFILEERRORBOX);
 HMODULE h=LoadLibraryExW(file,nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);if(!h){error("load_failed",GetLastError());return 5;}
 const char* names[]={"logiWheelOpenByDirectInputA","logiWheelOpenByDirectInputW","logiTrueForceAvailable","logiTrueForceSetStreamTF","logiTrueForceSetTorqueKF","DllRegisterServer","g923_fixture_probe"};
 for(auto name:names)std::printf("{\"event\":\"export_lookup\",\"name\":%s,\"present\":%s,\"called\":false}\n",quoted(name).c_str(),GetProcAddress(h,name)?"true":"false");
 FreeLibrary(h);std::puts("{\"event\":\"load_finished\",\"dllmain_executed\":true,\"sdk_functions_called\":false,\"hardware_success_proven\":false}");return 0;
}
// ABI pinned by static inspection of the original 1.3.12 x64 DLL:
// dllOpen/dllClose take no parameters and have no meaningful return value;
// Available returns a 32-bit status and writes one byte through its pointer.
static int availability_1312(const wchar_t* file,int samples=8){
 SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOOPENFILEERRORBOX);
 HMODULE h=LoadLibraryExW(file,nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
 if(!h){error("load_failed",GetLastError());return 5;}
 auto open=(void(*)())GetProcAddress(h,"dllOpen");auto close=(void(*)())GetProcAddress(h,"dllClose");auto available=(int(*)(unsigned char*))GetProcAddress(h,"logiTrueForceAvailable");
 if(!open||!close||!available){error("sdk_lifecycle_exports_missing",ERROR_PROC_NOT_FOUND);FreeLibrary(h);return 6;}
 std::puts("{\"event\":\"sdk_initializing\",\"abi\":\"1.3.12-x64\",\"torque_api_calls\":0}");std::fflush(stdout);
 open();std::puts("{\"event\":\"sdk_initialized\"}");std::fflush(stdout);
 bool any=false;int last=0;
 for(int i=0;i<samples;++i){unsigned char value=0;last=available(&value);any=any||(last==0&&value!=0);
 std::printf("{\"event\":\"sdk_availability\",\"status_hex\":\"%08lx\",\"available\":%s,\"sample\":%d}\n",(unsigned long)(DWORD)last,last==0&&value?"true":"false",i);std::fflush(stdout);Sleep(250);}
 close();std::puts("{\"event\":\"sdk_closed\",\"torque_api_calls\":0}");std::fflush(stdout);FreeLibrary(h);return any?0:last?8:7;
}
int wmain(int argc,wchar_t**argv){
 std::puts("{\"event\":\"probe\",\"version\":1,\"pointer_bits\":64}");
 if(argc==1){registry();return inventory();}
 if(argc==4&&std::wstring(argv[1])==L"--availability"&&std::wstring(argv[3])==L"--initialize-sdk-1_3_12")return availability_1312(argv[2]);
 if(argc==6&&std::wstring(argv[1])==L"--availability"&&std::wstring(argv[3])==L"--initialize-sdk-1_3_12"&&std::wstring(argv[4])==L"--observe-seconds"){
  wchar_t* end=nullptr;long seconds=std::wcstol(argv[5],&end,10);if(!end||*end||seconds<1||seconds>120)return 2;
  return availability_1312(argv[2],int(seconds)*4);
 }
 if(argc==3&&std::wstring(argv[1])==L"--verify")return verify(argv[2]);
 if(argc==4&&std::wstring(argv[1])==L"--load"&&std::wstring(argv[3])==L"--execute-dllmain")return load(argv[2]);
 std::fprintf(stderr,"Usage: sdk-probe.exe [--verify ABS_DLL | --load ABS_DLL --execute-dllmain]\nDefault: registry + HID enumeration; no output reports. Load may initialize SDK/hardware.\n");return 2;
}
