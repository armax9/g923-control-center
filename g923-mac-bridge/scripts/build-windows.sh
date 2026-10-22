#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p build/windows
export ZIG_GLOBAL_CACHE_DIR="${ZIG_GLOBAL_CACHE_DIR:-$PWD/build/zig-cache}"
export ZIG_LOCAL_CACHE_DIR="${ZIG_LOCAL_CACHE_DIR:-$PWD/build/zig-local}"
if [ -n "${ZIG:-}" ]; then
  "$ZIG" c++ -target x86_64-windows-gnu -std=c++17 -O2 -shared -o build/windows/dinput8.dll \
   -Ivendor/wheelio/include -Ivendor/wheelio/bridge/include -Ivendor/wheelio/bridge/windows/include \
   vendor/wheelio/bridge/windows/dinput8_proxy.cpp vendor/wheelio/bridge/windows/bridge_client.cpp \
   vendor/wheelio/bridge/common/ffb_mapping.cpp vendor/wheelio/bridge/common/dinput_effects.cpp -ldxguid -lws2_32
  "$ZIG" c++ -target x86_64-windows-gnu -std=c++17 -O2 src/dinput_probe.cpp -o build/windows/dinput-probe.exe -ldinput8 -ldxguid
else
  CXX_WIN=${CXX_WIN:-x86_64-w64-mingw32-g++}
  "$CXX_WIN" -std=c++17 -O2 -shared -static-libgcc -static-libstdc++ -o build/windows/dinput8.dll \
   -Ivendor/wheelio/include -Ivendor/wheelio/bridge/include -Ivendor/wheelio/bridge/windows/include \
   vendor/wheelio/bridge/windows/dinput8_proxy.cpp vendor/wheelio/bridge/windows/bridge_client.cpp \
   vendor/wheelio/bridge/common/ffb_mapping.cpp vendor/wheelio/bridge/common/dinput_effects.cpp -ldxguid -lws2_32
  "$CXX_WIN" -std=c++17 -O2 -static-libgcc -static-libstdc++ src/dinput_probe.cpp -o build/windows/dinput-probe.exe -ldinput8 -ldxguid
fi
