#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
set -eu
cd "$(dirname "$0")/.."
# Reuse the isolated toolchain already downloaded for this task, if present.
if [ -z "${ZIG:-}" ] && [ -x ../../work/zig-macos-aarch64-0.13.0/zig ]; then
 ZIG="$(cd ../../work/zig-macos-aarch64-0.13.0 && pwd)/zig";export ZIG
fi
./scripts/build.sh
./scripts/build-windows.sh
./sdk-lab/build.sh
./scripts/build-crossover-base.sh
python3 sdk-lab/tools/lab.py preflight
if [ "${1:-}" = '--runtime-tests' ]; then
 python3 sdk-lab/tools/lab.py offline
 python3 sdk-lab/tools/test_virtual_input.py
fi
printf '\nSoftware preparation complete. Next: sdk-lab/Collect-readonly.command with user present.\n'
