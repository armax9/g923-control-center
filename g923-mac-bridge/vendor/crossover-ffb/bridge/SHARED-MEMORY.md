# Shared memory v2

File `/tmp/crossover-ffb-<uid>/ffb-v2.bin` (8192 bytes, 0600, never truncated or replaced),
created by the app and opened by the DLL as `Z:\tmp\crossover-ffb-<uid>\ffb-v2.bin` with
`CreateFileMapping`/`MapViewOfFile`; Wine maps it `MAP_SHARED`. Little-endian. Each block starts
with a seqlock counter: odd while the writer is updating, readers retry until it is even and
unchanged. Source of truth: `bridge/shm.h` and `Sources/WheelCore/SharedBridge.swift`.

| Offset | Writer | Field |
|---|---|---|
| 0 | app | magic `CFB2`, u32 version 2, u32 size 8192 (an old 4096-byte file is grown, the DLL then skips telemetry) |
| 64 | app | input seqlock |
| 68 / 72 | app | connected u32 / heartbeat Unix ms u64 (stale > 500 ms = input lost) |
| 80…92 | app | steering, accelerator, brake, clutch (u32 0…65535, pedals as reported by HID) |
| 96 / 100 | app | buttons 1…25 bitmask / hat 0…7 clockwise from north, 8 = centred |
| 256 | DLL | force seqlock |
| 260 / 264 | DLL | Windows PID / heartbeat Unix ms u64 (every Poll/GetDeviceState) |
| 272 / 276 / 280 | DLL | acquired / device gain 0…10000 / flags: 1 paused, 2 actuators off, 4 autocenter |
| 320 + 96·n | DLL | 32 effect records |
| 4096 | DLL | telemetry seqlock |
| 4100 / 4104 / 4112 | DLL | source (1 = AC/ACC `Local\acpmf_physics`, 2 = AC EVO `Local\acevo_pmf_physics`) / length (800) / copied at Unix ms u64 |
| 4120 | DLL | car max rpm u32 from the static page (`Local\acpmf_static` / `Local\acevo_pmf_static`, offset 412), 0 if unknown; drives the rev lights |
| 4128… | DLL | raw page, copied on every Poll/GetDeviceState whose page packetId changed |

Effect record (u32/i32 words): 0 kind (1 constant, 2 ramp, 3 square, 4 sine, 5 triangle,
6 saw up, 7 saw down, 8 spring, 9 damper, 10 inertia, 11 friction; 0 empty), 1 playing,
2 start counter (changes on every Start), 3 duration µs (0xffffffff infinite), 4 start delay µs,
5 gain, 6 coordinate flags (0x10 cartesian, 0x20 polar, 0x40 spherical), 7 axis count,
8 index of the steering axis, 9–10 direction, 11 has envelope, 12–15 attack level/time,
fade level/time, 16–21 type-specific parameters (constant: magnitude; ramp: start, end;
periodic: magnitude, offset, phase, period; condition for the steering axis: offset,
+coefficient, −coefficient, +saturation, −saturation, dead band), 22 iterations.

Telemetry is read by `GameTelemetry.acPhysics` (word indices of `SPageFilePhysics`: 0 packetId,
1 gas, 5 rpm (int), 7 speed km/h, 46–49 suspension travel, 195 engine running, 196–199 kerb,
slip, g (AC EVO: road) and ABS vibration levels) and drives the simulated TrueForce synthesizer.

The DLL builds the Wine path from the digits after `CFBUID=` in its data section. The app's
installer (`BridgeInstaller`) writes the Mac user's uid there when it copies the DLL into a game,
so one build serves every user.

## TIM1 playback-clock extension (candidate, 21 October 2026)

The v2 record sizes and input GUIDs remain unchanged. Force-header offset32 (absolute288)
contains `0x314d4954` (`TIM1`). Effect word23 contains **device playback elapsed milliseconds
plus1**, including start delay. Zero means the old DLL did not provide a playback timestamp.
The reader requires both TIM1 and nonzero word23: an old DLL clears the record but can leave
reserved header bytes behind after rollback. Native code must then use its legacy clock.
Elapsed milliseconds saturate at `UInt32.max-1` (about49.7days of uninterrupted playback);
this is a session diagnostic protocol, not an unbounded kernel-driver clock.

The DLL owns the playback origin. PAUSE freezes its clock; CONTINUE resumes it without a new
Start. ACTUATORSOFF mutes output while time continues. Downloaded parameters are separate
from GetParameters' requested parameters. A dynamic duration update retains the original
playback origin and cannot revive an already expired effect. Poll/GetDeviceState republishes
the timestamp and effect records together under the seqlock, avoiding a fresh heartbeat
paired with an old playback age. Native extrapolation between publications is capped500ms,
within the existing independent game/input freshness checks. Older native readers ignore
the extension; both new components are needed for authoritative phase reconstruction.

## Optional full-state capture ring

`/tmp/crossover-ffb-<uid>/trace-v1.bin` is separate from the8192-byte control mapping. A private
collector creates it before launching the game; the candidate DLL only opens an existing
mapping, once, and never creates a trace file. No collector file means capture is disabled.
Ring writes use memory only; this does not remove the pre-existing bounded observer log.
One Windows producer PID may own a capture. Start a new collector/game process for another
capture. The collector uses acquire barriers on Apple Silicon and verifies slot generations.

Header64bytes: magic `G9TR` u32, version1 u32, slots128 u32, stride4096 u32,
latest completed sequence u64 at16, owner Windows PID u32 at24.
Each4096-byte slot: seqlock `sequence*2` u64 at0 (odd while writing), sequence u64 at8,
Unixms u64 at16, producer monotonic tickms u64 at24, force bytes3136 u32 at32,
input bytes48 or0 u32 at36, operation u32 at40, flags u32 at44, effect slot u32 at48,
HRESULT bits u32 at52. At64 is the complete force header plus32effect records;
at3200 is a coherent copy of the published input block (ignore it when input bytes=0).
Remaining bytes are zero. Operations:0 general state publication,1SetParameters,2Start,
3Stop,4Download,5Unload. Getter calls are not a complete API-call trace; NODOWNLOAD publishes
its result/flags and the **previously downloaded** playback image, not pending motor output.

A slow consumer can lose overwritten slots. The reader counts these explicitly and preserves
sequence IDs. Capture goes to `frames.bin.gz`; `summary.json` reports loss, truncation,
completion/error and PID. The default uncompressed recording limit is2GiB; hitting it does
not alter motor output or stop the user's driving. SCS LTFR telemetry is separately recorded
with local receive timestamps; RPM does not supply an actual engine-enabled boolean.
