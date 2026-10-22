# G923 Control Center 0.6.2

Native TRUEFORCE in DiRT Rally 2.0 and emulated engine vibration in Euro Truck Simulator 2, alongside ordinary Force Feedback and wheel input.

## Install the app

Download **G923ControlCenter-0.6.2-macOS-arm64.zip**, unzip it and drag **G923 Control Center.app** into **Applications**. Install [Python 3.10 or newer](https://www.python.org/downloads/macos/) if needed. No source build is required.

This app download requires **Apple Silicon and macOS 27 or newer**. It is ad-hoc signed and not notarized. If macOS blocks the first launch, approve it in **System Settings → Privacy & Security → Open Anyway**. Allow Input Monitoring when requested.

CrossOver is installed separately. The included native TRUEFORCE transport supports **CrossOver Preview 27.0.0.41069 / Wine 11.17**; import the original Logitech SDK through the app.

## Tested gameplay

| Game | Result |
| --- | --- |
| DiRT Rally 2.0 | Native Logitech TRUEFORCE, ordinary FFB, steering, pedals and H-pattern shifter |
| Euro Truck Simulator 2 | Engine vibration, steering resistance/return, impacts and input |

Tested in gameplay on **G923 PlayStation / PC**, M3 Max, macOS 27.0.1 and **CrossOver Preview 27.0.0.41069 / Wine 11.17**. Native TRUEFORCE uses the original **Logitech SDK 1.3.12 x64**. Other wheels and game integrations remain untested or pending.

## Included

- Automatic bridge startup, game sidebar and independent per-game settings.
- ETS2 engine intensity starts at **10%** for new settings. Enable, mute and intensity changes apply during gameplay without restarting FFB.
- Native TRUEFORCE setup: official G HUB link, SDK instructions/import, compatible transport installation and game integration status.
- In-app **Wine source & build guide**, with **Open source folder** for the complete corresponding source and build tools.
- One green **Installed** indicator on a completed installation; warning details appear when attention is needed.
- CrossOver/Preview, bottle and Steam library discovery.
- Additional game recognition and telemetry adapters with explicit test status.

## Use

Open the app and select your game. For DiRT, follow **Import SDK… → Install transport → Install game integration**. Exit Steam before the last step, then reopen it yourself. In the game, enable the separate **Logitech TRUEFORCE** controls under **Vibration & Feedback**.

For ETS2, use **Install components** if needed. Adjust **Engine intensity** in the app while driving; 0% is silent. Change ordinary **FFB strength** with the game closed.

The app leaves Steam, game launching and VR choice to you. Logs remain in the background.

## Software verification

A clean exported source tree built all nine bridge components and the signed app package. Checks passed: 216 Python tests (two skips), 81 Swift tests, seven CTest targets, five live-engine control checks and 41 release-tool fixtures. The live test covered 10% → 40% → mute → 10% in one synth process.

## App and source

The source includes the Wine patches, build instructions and complete corresponding-source packaging. The compatible CrossOver runtime and original Logitech SDK come from the user's installation. New Wine/CrossOver builds need a newly validated transport pair.

A clean installation on a second Mac remains untested. Live engine adjustment has software and localhost-stream verification. The downloadable app passed bundle signature, payload hash and personal-path checks. Wine debug data was removed with runtime section contents verified unchanged. This packaged build has not had an additional physical wheel test.

[Setup and source build](BUILD_AND_SETUP.md) · [Support matrix](SUPPORT.md) · [License notices](../../NOTICE.md)
