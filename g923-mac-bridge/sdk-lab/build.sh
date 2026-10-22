#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p build/sdk-lab
export ZIG_GLOBAL_CACHE_DIR="${ZIG_GLOBAL_CACHE_DIR:-$PWD/build/zig-cache}"
export ZIG_LOCAL_CACHE_DIR="${ZIG_LOCAL_CACHE_DIR:-$PWD/build/zig-local}"
if [ -n "${ZIG:-}" ]; then
 "$ZIG" c++ -target x86_64-windows-gnu -std=c++17 -O2 -municode sdk-lab/src/sdk_probe.cpp -o build/sdk-lab/sdk-probe.exe -lsetupapi -lhid -lwintrust -lcrypt32 -ladvapi32
 "$ZIG" c++ -target x86_64-windows-gnu -std=c++17 -O2 -municode sdk-lab/src/sdk_session.cpp -o build/sdk-lab/sdk-session.exe -ldinput8 -ldxguid
 "$ZIG" c++ -target x86_64-windows-gnu -std=c++17 -O2 -municode sdk-lab/src/steam_ready.cpp -o build/sdk-lab/steam-ready.exe
 "$ZIG" c++ -target x86_64-windows-gnu -std=c++17 -O2 -municode sdk-lab/src/sdk_route_probe.cpp -o build/sdk-lab/sdk-route-probe.exe -ldinput8 -ldxguid -ladvapi32
 "$ZIG" c++ -target x86_64-windows-gnu -std=c++17 -O2 sdk-lab/src/ffb_probe.cpp -o build/sdk-lab/ffb-probe.exe -ldinput8 -ldxguid
 "$ZIG" c++ -target x86_64-windows-gnu -std=c++17 -O2 -municode sdk-lab/src/ffb_exercise.cpp -o build/sdk-lab/ffb-exercise.exe -ldinput8 -ldxguid
 "$ZIG" c++ -target x86_64-windows-gnu -std=c++17 -O2 -shared sdk-lab/src/fixture_combined.cpp -o build/sdk-lab/fixture-sdk-combined.dll
 "$ZIG" cc -target x86_64-windows-gnu -O2 -shared sdk-lab/src/fixture.c -o build/sdk-lab/fixture-not-logitech.dll
 "$ZIG" cc -target x86_64-windows-gnu -O2 -shared -DG923_LIFECYCLE_FIXTURE sdk-lab/src/fixture.c -o build/sdk-lab/fixture-sdk-lifecycle.dll
else
 "${CXX_WIN:-x86_64-w64-mingw32-g++}" -std=c++17 -O2 -static-libgcc -static-libstdc++ -municode sdk-lab/src/sdk_probe.cpp -o build/sdk-lab/sdk-probe.exe -lsetupapi -lhid -lwintrust -lcrypt32 -ladvapi32
 "${CXX_WIN:-x86_64-w64-mingw32-g++}" -std=c++17 -O2 -static-libgcc -static-libstdc++ -municode sdk-lab/src/sdk_session.cpp -o build/sdk-lab/sdk-session.exe -ldinput8 -ldxguid
 "${CXX_WIN:-x86_64-w64-mingw32-g++}" -std=c++17 -O2 -static-libgcc -static-libstdc++ -municode sdk-lab/src/steam_ready.cpp -o build/sdk-lab/steam-ready.exe
 "${CXX_WIN:-x86_64-w64-mingw32-g++}" -std=c++17 -O2 -static-libgcc -static-libstdc++ -municode sdk-lab/src/sdk_route_probe.cpp -o build/sdk-lab/sdk-route-probe.exe -ldinput8 -ldxguid -ladvapi32
 "${CXX_WIN:-x86_64-w64-mingw32-g++}" -std=c++17 -O2 -static-libgcc -static-libstdc++ sdk-lab/src/ffb_probe.cpp -o build/sdk-lab/ffb-probe.exe -ldinput8 -ldxguid
 "${CXX_WIN:-x86_64-w64-mingw32-g++}" -std=c++17 -O2 -static-libgcc -static-libstdc++ -municode sdk-lab/src/ffb_exercise.cpp -o build/sdk-lab/ffb-exercise.exe -ldinput8 -ldxguid
 "${CXX_WIN:-x86_64-w64-mingw32-g++}" -std=c++17 -O2 -shared -static-libgcc -static-libstdc++ sdk-lab/src/fixture_combined.cpp -o build/sdk-lab/fixture-sdk-combined.dll
 "${CC_WIN:-x86_64-w64-mingw32-gcc}" -O2 -shared sdk-lab/src/fixture.c -o build/sdk-lab/fixture-not-logitech.dll
 "${CC_WIN:-x86_64-w64-mingw32-gcc}" -O2 -shared -DG923_LIFECYCLE_FIXTURE sdk-lab/src/fixture.c -o build/sdk-lab/fixture-sdk-lifecycle.dll
fi
python3 -m unittest discover -s sdk-lab/tests -v
