# Copyright and license notices

Project integration sources, scripts and documentation: Copyright (c) 2026 G923 Mac Bridge contributors; GPL-3.0-only, see [LICENSE](LICENSE). This project is not affiliated with Logitech or CodeWeavers.

## crossover-ffb

`vendor/crossover-ffb/` derives from [0xbiel/crossover-ffb](https://github.com/0xbiel/crossover-ffb), commit `65a9685f85908e01dc3c8ca91f84dc49a1329c0f`, Copyright (c) 2026 crossover-ffb contributors, MIT. The complete grant and disclaimer remain in `vendor/crossover-ffb/LICENSE`. Local app, bridge and packaging changes are identified in the project source. No GPL-2.0-only synthesis code is linked into the application.

## mescon components

The separate `mescon-telemetry` source tree derives from [mescon/logitech-trueforce-linux-driver](https://github.com/mescon/logitech-trueforce-linux-driver), commit `972274bdce293419c058eb10b796feb232bfd9ef`. It is GPL-2.0-only, with its `COPYING` and `UPSTREAM.json`. The engine synthesizer is a separate executable; its game plugin and relay remain separate components. Communication with the main bridge uses loopback UDP.

`vendor/trueforce/tf_init_data.h` is the unmodified initialization table from that commit, `userspace/libtrueforce/src/tf_init_data.h`, under LGPL-2.1-or-later. Its original capture notice and the license in `vendor/trueforce/COPYING` are retained. The launcher adjusts the range packet in memory to 900 degrees. Linux kernel driver and FreeTheWheel GPL-2.0-only sources are not linked into the main bridge.

## Wine transport

The G923 Wine transport modifies Wine `wine-11.17`, commit `36b6a2cf679fb395f668a917b76537190e212d9c`, under LGPL-2.1-or-later. Patches, modification notices, the pinned source relationship and complete corresponding-source packaging are described in [the Wine guide](docs/WINE_TRANSPORT_SOURCE.md). Any distributed patched Wine module pair must accompany its complete corresponding source and Wine license notices.

Original Logitech SDK DLLs and commercial CrossOver runtime files are not redistributed. The app imports the user's SDK and prepares a private runtime from the user's CrossOver installation.

## Wheelio

`vendor/wheelio/` derives from [ivonunes/wheelio](https://github.com/ivonunes/wheelio), commit `b869065082c2918189c300edd8c2e5154baf82a6`, by ivonunes and contributors, GPL version 3. The complete license is in `vendor/wheelio/LICENSE.txt`; upstream source notices remain. The included engine/proxy sources are unmodified. Upstream app and VR streamer are omitted; their original build instructions may describe components outside this distribution. Optional OpenXR headers retain their own notices and are not used by this project's Windows bridge build.

## CrossFFB reference

`vendor/CrossFFB-reference/` contains unmodified reference sources from [teosemi/CrossFFB](https://github.com/teosemi/CrossFFB), commit `5ea4eac1e41fc743191e9e007c59abe2ea4f28d6`, Copyright (c) 2026 Matteo Seminara and Maurizio Seminara, MIT. Its license and `SOURCE.json` preserve permission, disclaimer and source hashes. The project's `CrossFFBClassicProfile.swift` adapts initialization ordering, loop selection and constant-force packet quantization with that MIT permission preserved. The reference's G29 results do not establish G923 hardware acceptance here.

## Toolchains and test files

Windows builds use Zig/LLVM and MinGW components under their respective licenses. The source does not include these toolchains. Binary packaging must retain the applicable runtime notices from `LICENSES/` and the toolchain distribution.

`sdk-lab`'s `fixture-not-logitech.dll` is an original test double, not Logitech SDK code or a compatible replacement.
