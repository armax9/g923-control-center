#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
set -eu
cd "$(dirname "$0")/.."
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export SDKROOT="$(xcrun --show-sdk-path)"
export CLANG_MODULE_CACHE_PATH="$PWD/build/crossover-module-cache"
export SWIFT_MODULECACHE_PATH="$PWD/build/crossover-swift-module-cache"
mkdir -p build/crossover-base
clang_bin="$(xcrun --find clang)"
"$clang_bin" -isysroot "$SDKROOT" -std=c11 -g -Wall -Wextra -Wno-unused-function -Wno-missing-field-initializers -fsanitize=address,undefined \
 vendor/crossover-ffb/bridge/tests/test_bridge.c -o build/crossover-base/test-bridge
build/crossover-base/test-bridge
"$(xcrun --find swift)" test --package-path vendor/crossover-ffb --build-system native \
 --cache-path "$PWD/build/crossover-swiftpm-cache" --scratch-path "$PWD/build/crossover-base/swift" --disable-sandbox
"$(xcrun --find swift)" build --package-path vendor/crossover-ffb \
 --cache-path "$PWD/build/crossover-swiftpm-cache" --scratch-path "$PWD/build/crossover-base/swift" --disable-sandbox --product G923ClassicLab
build/crossover-base/swift/debug/G923ClassicLab --dry-run
if [ -n "${ZIG:-}" ]; then
 export ZIG_GLOBAL_CACHE_DIR="${ZIG_GLOBAL_CACHE_DIR:-$PWD/build/zig-cache}"
 export ZIG_LOCAL_CACHE_DIR="${ZIG_LOCAL_CACHE_DIR:-$PWD/build/zig-local}"
 "$ZIG" cc -target x86_64-windows-msvc -std=c11 -O2 -ffreestanding -fno-builtin -fno-stack-protector -c \
  vendor/crossover-ffb/bridge/observe.c -o build/crossover-base/observe.obj
 "$ZIG" dlltool -m i386:x86-64 -d vendor/crossover-ffb/bridge/kernel32.def -l build/crossover-base/kernel32.lib
 "$ZIG" cc -target x86_64-windows-msvc -nostdlib -shared build/crossover-base/observe.obj build/crossover-base/kernel32.lib \
  vendor/crossover-ffb/bridge/exports.def -Wl,--entry,DllMain -o build/crossover-base/dinput8.dll
 python3 - <<'PY'
import sys
sys.path.insert(0,'sdk-lab/tools')
from pe_inventory import inspect
p=inspect('build/crossover-base/dinput8.dll')
assert p['x64']
assert {d['dll'].lower() for d in p['imports']}=={'kernel32.dll'}
assert {'DirectInput8Create','DllCanUnloadNow','DllGetClassObject','DllRegisterServer','DllUnregisterServer'} <= {e['name'] for e in p['exports']}
print('PASS: optional virtual DInput bridge is x64, KERNEL32-only imports and required exports')
PY
else
 echo 'Swift app/CLI built. For DLL: set ZIG or use upstream scripts/build-bridge with LLVM/lld.'
fi
if [ -f build/crossover-base/dinput8.dll ]; then
 python3 - <<'PY'
from pathlib import Path
import plistlib,shutil
base=Path('build/crossover-base');app=base/'G923 Experimental FFB.app'
mac=app/'Contents/MacOS';res=app/'Contents/Resources'
mac.mkdir(parents=True,exist_ok=True);res.mkdir(parents=True,exist_ok=True)
for name in ['CrossoverFFBApp','crossover-ffb']:shutil.copy2(base/'swift/debug'/name,mac/name)
shutil.copy2(base/'dinput8.dll',res/'dinput8.dll')
shutil.copy2('vendor/crossover-ffb/LICENSE',res/'LICENSE-crossover-ffb.txt')
info={'CFBundleExecutable':'CrossoverFFBApp','CFBundleIdentifier':'local.g923.prototype.crossover','CFBundleName':'G923 Experimental FFB','CFBundlePackageType':'APPL','CFBundleShortVersionString':Path('vendor/crossover-ffb/VERSION').read_text().strip(),'CFBundleVersion':'1','LSMinimumSystemVersion':'13.0','LSUIElement':True,'NSInputMonitoringUsageDescription':'Read racing wheel input for the experimental bridge. Motor output only with user present.'}
with (app/'Contents/Info.plist').open('wb') as f:plistlib.dump(info,f)
print('Experimental SYNTHETIC FFB app packaged; not launched, not native Logitech SDK.')
PY
 # Remove only Finder/resource-fork metadata from our generated bundle; preserve quarantine/security attributes.
 xattr -r -d com.apple.FinderInfo "build/crossover-base/G923 Experimental FFB.app" 2>/dev/null || true
 xattr -r -d com.apple.ResourceFork "build/crossover-base/G923 Experimental FFB.app" 2>/dev/null || true
 codesign --force --sign - "build/crossover-base/G923 Experimental FFB.app"
 codesign --verify --strict "build/crossover-base/G923 Experimental FFB.app"
fi
