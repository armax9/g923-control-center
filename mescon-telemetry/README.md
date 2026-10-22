# mescon telemetry component for macOS/CrossOver

Separate engine synthesis and Windows telemetry components for G923 Control Center. **GPL-2.0-only**; see [COPYING](COPYING) and [UPSTREAM.json](UPSTREAM.json). This code is not linked into the main GPL-3 application or FFB bridge.

## Components

- `src/synth.rs`: original EngineSynth from mescon commit `972274bdce293419c058eb10b796feb232bfd9ef`.
- `src/scs_plugin.rs` and `abi.rs`: SCS telemetry callback plugin, adapted to a local relay module and cross-compiled for Windows x64.
- `src/main.rs`: macOS adapter, receiving LTFR v2 telemetry on loopback UDP port 20780 and sending bounded G9AU audio packets at 4 kHz through port 20781. It performs no HID output.
- `src/control.rs`: validated live intensity input and gain interpolation.
- Additional source modules and Windows relay: telemetry adapters listed in `UPSTREAM.json`; gameplay status is documented in the main project's support matrix.

## Build

Install Rust standard libraries for `aarch64-apple-darwin` and `x86_64-pc-windows-gnullvm`, plus llvm-mingw:

```sh
python3 build.py --rustc /path/to/rustc --mingw /path/to/x86_64-w64-mingw32-gcc
```

The build runs synthesis, plugin ABI, adapter and relay tests before producing `build/mescon-synth`, `build/logi_tf_scs.dll` and `build/logi-tf-relay.exe`. It does not start a game or access a wheel.

## Engine synthesis

The initial engine intensity defaults to **10%**. `--intensity 0.1 --cylinders 6` selects the starting gain and configured cylinder approximation. RPM and throttle drive the harmonics; cylinder count is not inferred from ETS2 telemetry. Ordinary steering and road forces come from the game's independent FFB stream.

`--control-file /path/to/engine-control.json` accepts live gain updates:

```json
{"version":1,"intensity":0.1}
```

Gain ranges from 0 to 1. The ETS2 worker translates validated app preferences into this record. Polling and interpolation retain the synth process and phase. Zero mutes engine vibration; a missing or invalid control record retains the last valid gain. Missing, invalid or expired telemetry produces silence; valid telemetry expires after 500 ms, and paused SCS output sends zero RPM.

This is telemetry-based emulation, not a game's native Logitech TRUEFORCE integration. The accepted ETS2 app profile uses engine synthesis; it does not enable every upstream mixer effect.

## Validation

The ETS2 integration was tested in gameplay on G923 PlayStation / PC, M3 Max, macOS 27.0.1 and CrossOver Preview 27.0.0.41069, with engine vibration and ordinary FFB together. Live intensity changes were verified by software and localhost-stream tests without resetting the synth or FFB owner. Those live-gain tests are not a separate physical-wheel acceptance. Other game adapters remain untested in gameplay here.

Sources: [mescon SCS plugin](https://github.com/mescon/logitech-trueforce-linux-driver/blob/972274bdce293419c058eb10b796feb232bfd9ef/docs/SCS_PLUGIN.md), [SCS telemetry API](https://modding.scssoft.com/wiki/Documentation/Engine/SDK/Telemetry).
