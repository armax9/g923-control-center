# Game and hardware support

## Tested integrations

| Game | Mode | Physical gameplay result |
| --- | --- | --- |
| DiRT Rally 2.0 | Native Logitech TRUEFORCE SDK | TRUEFORCE, ordinary FFB, steering, three pedals and H-pattern shifter |
| Euro Truck Simulator 2 | Ordinary game FFB + emulated engine vibration | Steering resistance/return, impacts, engine vibration and input |

Both have automatic runtime profiles and were tested in gameplay on **G923 PlayStation / PC, M3 Max, macOS 27.0.1, CrossOver Preview 27.0.0.41069 and the patched Wine 11.17 transport**. Native TRUEFORCE uses the original **SDK 1.3.12 x64**.

Other wheels, CrossOver 26, other macOS versions and clean installation on a second Mac have no project hardware acceptance. Live engine adjustment has software and localhost-stream verification.

## Additional adapters in source

| Game | Adapter | Status |
| --- | --- | --- |
| American Truck Simulator | SCS telemetry plugin | Gameplay untested |
| Assetto Corsa | Windows shared-memory relay | Implemented; gameplay untested |
| Project CARS 2 | PCARS2-format UDP | Implemented; gameplay untested |
| rFactor 2 | Shared-memory plugin + Windows relay | Game plugin required; gameplay untested |
| Le Mans Ultimate | Shared-memory plugin + Windows relay | Game plugin required; gameplay untested |
| RaceRoom Racing Experience | Windows shared-memory relay | Implemented; gameplay untested |

These adapters provide emulation inputs, not native SDK support or a completed automatic app profile for every title. The separate mescon source tree includes further UDP parsers; see its `UPSTREAM.json`.

## Native TRUEFORCE catalog

[NATIVE_TRUEFORCE_CATALOG.json](../NATIVE_TRUEFORCE_CATALOG.json) records game capability and its references. DiRT is the tested native SDK integration. ACC and AC EVO have experimental SDK profile tooling; other recognized titles need integration work. A catalog match is not a completed installation or a CrossOver compatibility result.

## App status

- **Installed:** required integration files match the installation record. A completed installation shows one green indicator; warning details appear only when attention is needed.
- **On / Ready:** automatic game detection is running.
- **Connected:** the backend observed active game bridge data.
- **Untested:** source or an adapter exists without physical gameplay acceptance.
- **Integration pending:** recognition exists, but automatic integration is not ready.

DiRT's SDK, transport and bottle installation have separate checks. Force and native TRUEFORCE intensity remain game-controlled. ETS2 has independent app controls for FFB strength and engine vibration. Engine enable/intensity changes apply during a drive, starting at 10% for new settings; change FFB strength with the game closed.
