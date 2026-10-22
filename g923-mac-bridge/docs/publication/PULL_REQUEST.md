# Add native TRUEFORCE and ETS2 engine vibration for G923 on macOS

This extends crossover-ffb with native Logitech TRUEFORCE in DiRT Rally 2.0 and telemetry-based engine vibration alongside ordinary game FFB in Euro Truck Simulator 2. Both paths were confirmed in gameplay on G923 PlayStation / PC, M3 Max, macOS 27.0.1 and CrossOver Preview 27.0.0.41069 with the patched Wine 11.17 transport and original Logitech SDK 1.3.12 x64.

The SwiftUI app starts its bridge quietly, detects the game automatically and keeps per-game settings and installation status on each game's page. ETS2 preserves DLAA `dinput8.dll`; engine intensity defaults to 10% and changes live without restarting FFB. Native setup provides SDK import instructions, transport installation, game integration and an in-app Wine source/build guide. A completed installation has one green status indicator.

The source includes Windows bridges, Wine patches and corresponding-source packaging, the separate GPL-2.0-only mescon synthesizer, telemetry adapters and offline tests. Other game integrations retain untested/pending labels. New Wine/CrossOver builds require their own validated transport. Logitech SDK and commercial CrossOver binaries remain user supplied. Clean installation on a second Mac is pending; the recorded hardware results cover the two existing game installations.

See the README, support matrix and build guide for setup and validation scope.

Validation: clean source export, all nine components and signed app packaging; 216 Python tests (two skips), 81 Swift tests, seven CTest targets and the compiled live-gain stream test passed.
