# Build and setup

The source release contains two sibling projects:

```text
G923ControlCenter/
  g923-mac-bridge/
  mescon-telemetry/
```

Keep this layout or pass `--mescon-source` when building. Run the commands below from `g923-mac-bridge`.

## Dependencies

- Apple Silicon macOS, Xcode/Command Line Tools and a compatible Swift toolchain.
- CMake 3.21 or newer and Python 3.10 or newer.
- Zig; version 0.13 was used for the accepted Windows bridges.
- Rust with `aarch64-apple-darwin` and `x86_64-pc-windows-gnullvm` standard libraries.
- llvm-mingw providing `x86_64-w64-mingw32-gcc`.
- User-installed CrossOver or CrossOver Preview. Native TRUEFORCE also needs the original Logitech SDK and a compatible patched Wine transport.

## Build the bridge components

Select the x64 `winmm.dll` from the CrossOver installation you intend to use. The builder reads its export table to generate the chain loader; it does not copy the commercial runtime into the release.

Inspect the plan first:

```sh
python3 scripts/build-release-components.py \
  --wine-winmm '/path/to/CrossOver.app/Contents/SharedSupport/CrossOver/lib/wine/x86_64-windows/winmm.dll' \
  --zig /path/to/zig \
  --rustc /path/to/rustc \
  --mingw /path/to/x86_64-w64-mingw32-gcc \
  --plan
```

Run the same command without `--plan` to build. Tools can also be found on `PATH` or set through `ZIG`, `G923_RUSTC` and `G923_MINGW`. The default output, `build/public-components`, must not already exist; use a fresh `--output` for a rebuild.

The builder runs offline C/Rust tests and produces nine components with `manifest.json` and `build-report.json`. This includes the input publisher, classic/combined backend, Windows bridges, SCS telemetry plugin and separate synthesizer. It does not install components or start Wine, games or HID output.

Additional software checks:

```sh
./scripts/build.sh
ZIG=/path/to/zig ./sdk-lab/build.sh
python3 scripts/test-offline.py
swift test --package-path vendor/crossover-ffb --disable-sandbox
python3 -m unittest discover -s sdk-lab/tests -v
python3 scripts/test-release-build.py
python3 scripts/test-package-control-center.py
python3 scripts/test-prepare-publication.py
```

The SDK lab build creates the PE test fixtures before running the Python suite. Local socket tests need localhost access. Full Xcode is needed for XCTest and sanitizer tests on this setup; select it with DEVELOPER_DIR if Command Line Tools are active. Software checks do not establish physical wheel behavior.

## Wine transport and app package

The tested transport targets **CrossOver Preview 27.0.0.41069 / Wine 11.17**. Follow the [Wine source guide](../WINE_TRANSPORT_SOURCE.md) to obtain the pinned upstream source, apply the patches and build both modules together. A rebuilt pair needs reviewed hashes and a matching compatibility catalog entry before packaging.

A reviewed Wine payload directory contains `catalog.json`, the matching Unix/PE module pair, the complete corresponding-source archive and Wine license files. The packager checks this against `patches/transport-catalog.json`.

```sh
python3 scripts/package-control-center.py \
  --payloads build/public-components \
  --wine-transport /path/to/reviewed-wine-payload \
  --output /path/to/app-build
```

This creates an app artifact without installation. Add `--install '/path/to/G923 Control Center.app'` only to install explicitly. `--accepted-local` is a private recovery option for an existing development installation, not a source-release build.

The current publication is source-only. Accepted local Wine binaries retain debug build paths; public binary assets need path removal, new hash review and validation. The source package contains no original Logitech SDK or commercial CrossOver runtime.

## Set up DiRT Rally 2.0

1. Open the app and select the discovered DiRT installation.
2. In **Native TRUEFORCE setup**, open **Get Logitech G HUB** or **SDK instructions**. Install Windows G HUB in Windows/Parallels and copy `C:\Program Files\Logi\Trueforce\1_3_12\trueforce_sdk_x64.dll` to a Mac folder. Use **Import SDK…**. This release accepts the verified original 1.3.12 x64 DLL; see the [SDK guide](../LOGITECH_SDK_SETUP.md).
3. Use **Install transport**. The app checks the selected CrossOver build and prepares a private runtime. An unsupported build needs a compatible transport port first.
4. Exit Steam and games. Use **Install game integration**, then **Refresh status**. The app records the installed files and bottle configuration in Application Support.
5. Open Steam normally and launch DiRT yourself. Wine must restart after a transport change.
6. In the game, select/calibrate G923 and enable the separate **Logitech TRUEFORCE** controls near the bottom of **Vibration & Feedback**. The generic Engine and Tyre Slip entries may remain grey.

**Wine source & build guide** opens inside the app. Its **Open source folder** button exposes the source archive and build tools.

## Set up ETS2

1. Select the discovered ETS2 installation and use **Install components** with the game closed.
2. Setup installs the separate bridge and SCS telemetry files, preserving an existing DLAA `dinput8.dll`.
3. Check the installation and bridge status. Open Steam and the game yourself, then select G923 and assign/calibrate its pedals.
4. Adjust **Engine intensity** on the game's app page while driving. New settings start at 10%; zero mutes the engine signal. Engine enable/intensity changes retain the synth process and ordinary FFB transport.
5. Change **FFB strength** with the game closed. Its default is 100% of the game's original strength.

The bridge starts automatically with the app. The app does not launch Steam or games, choose VR mode, or open logs on activation. Hardware acceptance covers the setup in the [support matrix](SUPPORT.md); clean installation on a second Mac is pending.

## Prepare the source archive

```sh
python3 scripts/prepare-publication.py
```

This creates `build/publication/G923ControlCenter` and a versioned source ZIP with a SHA-256 file. It includes both source projects, public guides, patches and licenses, and excludes private sessions, installed runtimes and generated binaries. It does not upload anything. See [publication checks](PUBLICATION_TECHNICAL_PREP.md).
