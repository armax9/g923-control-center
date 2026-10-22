# Building and publishing the Wine transport

The native TRUEFORCE path is:

`game → original Logitech TRUEFORCE SDK → patched Wine winebus → macOS IOHID → G923`

Publish the Wine patches and build instructions with the application source. They are reusable for future ports. A new Wine or CrossOver version still needs a reviewed port and an independently validated module pair; the installer must not silently apply the 11.17 pair to it.

## Accepted source and binary provenance

| Item | Value |
|---|---|
| Upstream tag | `wine-11.17` |
| Upstream commit | `36b6a2cf679fb395f668a917b76537190e212d9c` |
| Source archive SHA-256 | `8dde1acf3b7b702d911127edae5bad3a4683f6dd8c87e725e0379cb842fb1e0e` |
| Functional patch SHA-256 | `ae5e9f041502d57eb373cbdb6f9e38c983c9e4651e6908c2ff04df5bb99a1630` |
| Unix module SHA-256, ad hoc signed | `b8d60dce48b6fb768eb50e41950ffbfa99d29fb63e2d03dd764c338438f1453c` |
| PE module SHA-256 | `ecaf49c5ccea05ddad1d626f414ea9f761eb48bdf51e21c1f74512f7cd7146d8` |

The recovered upstream archive was checked against all **12,455** original files: only `bus_iohid.c` and `main.c` differed. Applying the functional patch to the pristine files reproduces both modified files byte for byte. The recovered PE build exactly matches the accepted PE module. Ad hoc signing the recovered Unix build exactly reproduces the accepted Unix module hash. This establishes the source/build relationship; it does not promise byte-identical builds on another toolchain or path. Debug data, timestamps, compiler versions and signing may change hashes.

The accepted build used Apple clang 21.0.0 targeting x86_64 macOS, Xcode's macOS 27 SDK, and [llvm-mingw 20260505 UCRT macOS universal](https://github.com/mstorsjo/llvm-mingw/releases/tag/20260505). LLVM-mingw archive SHA-256: `050379de888f0c843787819dadf183df3693330a5724643919e9121f16355295`. CrossOver supplies the rest of the user's runtime; it is not part of the source package.

## Download the pinned source

Download [Wine 11.17 source](https://github.com/wine-mirror/wine/archive/refs/tags/wine-11.17.tar.gz). The build script verifies its checksum and refuses another archive. A clean Git checkout of the pinned commit is also accepted through `--source`.

Install Xcode Command Line Tools, a modern Bison, and llvm-mingw. Keep their normal installation paths or supply paths as arguments. The script discovers neither bottles nor games and never starts Wine, Steam or a motor.

From the project root, first inspect the build plan:

```sh
python3 scripts/build-wine-transport.py \
  --source-archive /path/to/wine-11.17.tar.gz \
  --output /path/to/new-build \
  --mingw-bin /path/to/llvm-mingw/bin
```

Then add `--build` to compile both modules. Optional arguments are `--compiler`, `--cxx`, `--sdk`, `--bison` and `--jobs`. Input source remains unchanged. The script creates its own source/build directories, checks each patch before applying it, builds `dlls/winebus.sys/all`, ad hoc signs the Unix module and writes `build-manifest.json`. A fresh output directory is required. No security setting or installed runtime is modified.

The resulting pair is in `new-build/modules/x86_64-unix/winebus.so` and `new-build/modules/x86_64-windows/winebus.sys`. Keep these modules together. Newly built hashes are candidates; add them to the installer catalog only after compatibility and hardware acceptance.

## Complete source package

```sh
python3 scripts/build-wine-transport.py \
  --source-archive /path/to/wine-11.17.tar.gz \
  --source-bundle /path/to/g923-wine-11.17-source.tar.xz
```

This command does not compile. It packages the complete unchanged upstream source archive, both patches, this guide, the build script, copyright/license files and a file-hash manifest. Extract the package, use its root as the project root, and pass `upstream/wine-11.17.tar.gz` to the same build command. No network request is required after obtaining the toolchain.

Ship the source package alongside the transport modules and include Wine's `COPYING.LIB` in the app's source/licenses folder. For a downloadable release, provide source and binary assets from the same release. The package contains no Logitech SDK, commercial CrossOver files, bottles, game files, logs or user settings. Wine identifies its license as [LGPL-2.1-or-later](https://raw.githubusercontent.com/wine-mirror/wine/wine-11.17/LICENSE); the [complete license](https://raw.githubusercontent.com/wine-mirror/wine/wine-11.17/COPYING.LIB) governs redistribution.

## Porting a future Wine release

1. Pin the new upstream revision and the intended CrossOver product/build. Compare winebus's descriptor layout, Unix call ABI, HID handling and container identity with 11.17.
2. Reapply the three narrow G923 behaviors, preserving any upstream improvements. Review failing hunks instead of forcing them.
3. Build both PE and Unix modules from that source configuration. Record original runtime module hashes and replacement hashes as a new catalog entry.
4. Run software fixtures and loader checks without motor output. Then check SDK enumeration/open/close with a connected G923.
5. Obtain explicit user readiness for force tests. Verify native game TRUEFORCE, ordinary FFB, input/pedals/shifter, stop/quit and rollback. Keep the previous accepted entry available.

Only the G923 PlayStation / PC and the cataloged CrossOver Preview build have hardware acceptance in this project. Finding another installed CrossOver build does not make its transport compatible.

## Public binary packaging

The app download uses stripped copies of the accepted modules. Runtime section contents match the accepted pair; removal of debug data and ad-hoc signing change the file hashes:

- Unix: `7b30ba344bbebcf4966bd6d6e5e98ccd8305d5b65f152f64943701904475e1c9`
- PE: `c120a9aa5841056a5fe2ccab003ec46e6d9494dfeedd42fbb510ea6493523bb0`

`scripts/prepare-public-transport.py` verifies the original hashes and runtime sections, produces the public pair and corresponding source, and can update the catalog after review. This packaging transformation has software verification; no additional physical wheel acceptance is claimed.
