# G923 Control Center

**Native TRUEFORCE in DiRT Rally 2.0 and emulated engine vibration in ETS2, with ordinary Force Feedback, on macOS Apple Silicon and CrossOver.**

An open-source control center for Logitech G923 PlayStation / PC, based on [crossover-ffb](https://github.com/0xbiel/crossover-ffb). Current source preview: **0.6.2**.

Download the source preview and complete Wine source from [Releases](https://github.com/armax9/g923-control-center/releases). Build instructions are below.

## What works

| Game | TRUEFORCE | Tested on G923 PlayStation |
| --- | --- | --- |
| DiRT Rally 2.0 | Native game effects through the original Logitech TRUEFORCE SDK | TRUEFORCE, ordinary FFB, steering, three pedals and H-pattern shifter |
| Euro Truck Simulator 2 | Emulated engine vibration from SCS telemetry and the mescon synthesizer | Engine vibration alongside ordinary FFB, steering resistance/return, impacts and input |

Native TRUEFORCE carries the game's Logitech SDK signal. Emulation generates engine harmonics from RPM and throttle and sends them through the wheel's high-frequency output. ETS2 steering and road forces still come from the game's ordinary FFB.

ETS2 preserves an existing DLAA `dinput8.dll`. Its steering FFB and engine intensity have separate controls. **Engine intensity defaults to 10% and can be adjusted while driving**, without restarting the bridge. Zero mutes the engine vibration.

## Tested setup

- Logitech G923 PlayStation / PC, three pedals and Logitech H-pattern shifter.
- M3 Max Mac, macOS 27.0.1.
- CrossOver Preview **27.0.0.41069**, patched Wine **11.17** transport.
- Original Logitech TRUEFORCE SDK **1.3.12 x64** from Windows G HUB.
- Windows DiRT Rally 2.0 and ETS2 through Steam in CrossOver.

Both game paths were confirmed by the user in gameplay. Other wheels, CrossOver 26 and a clean installation on a second Mac have not been tested. Live engine adjustment has software and localhost-stream verification; it is not an additional hardware test.

## Use

1. Connect the wheel to USB and its power supply. Open **G923 Control Center**.
2. The bridge starts automatically. Check its status in the sidebar, then select your game.
3. Complete the installation steps below if components are missing.
4. Open Steam and launch the game yourself. Choose VR or desktop mode in Steam as usual.
5. Select G923 in the game, assign the pedals if needed and calibrate the wheel.
6. In DiRT, scroll down in **Vibration & Feedback** to **Enable TRUEFORCE** and the separate **Logitech TRUEFORCE Engine / Surface / Tyre Slip** controls.
7. In ETS2, change **Engine intensity** on the app's game page, including during a drive. Change **FFB strength** with the game closed; 100% preserves the game's original strength.

Closing Settings keeps the menu-bar app and bridge running. Opening Settings shows its Dock icon. Logs stay in the background.

## Install native TRUEFORCE

Select DiRT and use its **Native TRUEFORCE setup** card:

1. **Import SDK…** — open **Get Logitech G HUB** and **SDK instructions**. Install Windows G HUB in Windows or Parallels, copy `C:\Program Files\Logi\Trueforce\1_3_12\trueforce_sdk_x64.dll` to the Mac, then import it. The app accepts the verified **1.3.12 x64** DLL. G HUB versions may contain a different SDK; see the [SDK guide](docs/LOGITECH_SDK_SETUP.md).
2. **Install transport** — the app checks your CrossOver build and prepares a private runtime with the matching patched Wine modules. The current catalog supports the tested Preview build above.
3. **Install game integration** — exit Steam and games first. The app places and registers the SDK in the bottle and activates its transport. Reopen Steam normally afterward.

The card shows SDK, transport and game integration status separately. **Refresh status** checks the installation. **Wine source & build guide** opens an in-app guide; **Open source folder** opens the complete Wine source package, patches, licenses and build script.

For ETS2, select the game and use **Install components** if needed. Setup preserves the DLAA loader and uses separate bridge and telemetry files.

## Other games

The source includes additional native TRUEFORCE recognition and telemetry adapters. Their game pages show **Untested** or **Integration pending**. Automatic profiles and gameplay acceptance currently cover DiRT and ETS2. See the [support matrix](docs/publication/SUPPORT.md).

## Build and source

See [Build and setup](docs/publication/BUILD_AND_SETUP.md) for dependencies and commands, and the [Wine transport guide](docs/WINE_TRANSPORT_SOURCE.md) for the pinned source and future ports.

The app discovers CrossOver/Preview, bottles and Steam libraries, including external disks. It bundles its tools and open-source payloads; Python 3.10 or newer is required on the Mac. Installation profiles live in Application Support.

The Logitech SDK and commercial CrossOver runtime are user-supplied. They are not included in public source or downloads. New Wine/CrossOver builds need a separately validated transport pair.

## Credits and licenses

- [crossover-ffb](https://github.com/0xbiel/crossover-ffb): MIT app and DirectInput bridge base.
- [mescon/logitech-trueforce-linux-driver](https://github.com/mescon/logitech-trueforce-linux-driver): engine synthesis and protocol research. Its GPL-2.0-only synthesizer runs as a separate process.
- [Wheelio](https://github.com/ivonunes/wheelio): GPLv3 FFB/proxy subtree.
- [CrossFFB](https://github.com/teosemi/CrossFFB): MIT classic FFB reference.
- [Wine](https://www.winehq.org/): LGPL transport source and patches.

Project integration code is GPL-3.0-only. Component licenses and modification notices remain attached; see [NOTICE](NOTICE.md) and [LICENSE](LICENSE).
