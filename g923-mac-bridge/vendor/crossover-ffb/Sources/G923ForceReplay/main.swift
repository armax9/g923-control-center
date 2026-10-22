// SPDX-License-Identifier: GPL-3.0-only
// Offline stdin/stdout evaluator. No HID, Wine, SDK, mapping or motor startup.
import Foundation
import WheelCore
let args = Array(CommandLine.arguments.dropFirst())
guard args.count == 2, args[0] == "--motor-sign", let sign = Double(args[1]), sign == -1 || sign == 1 else {
    fputs("Usage: G923ForceReplay --motor-sign -1|1 < frames.jsonl\n", stderr); exit(2)
}
let engine = EffectEngine()
while let line = readLine() {
    do {
        guard let row = try JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any],
              let encoded = row["force_base64"] as? String, let frame = Data(base64Encoded: encoded) else { throw SharedBridge.Failure.invalidForceFrame }
        let state = try SharedBridge.decodeRecordedForceFrame(Array(frame))
        let position = (row["position"] as? Double) ?? 0
        let velocity = (row["velocity"] as? Double) ?? 0
        let now = ((row["unix_ms"] as? Double) ?? 0) / 1000
        let output: Double
        if state.acquired && !state.paused && !state.actuatorsOff {
            output = engine.force(state, wheel: .init(position: position, velocity: velocity), now: now)
        } else { engine.reset(); output = 0 }
        let result: [String: Any] = ["sequence": row["sequence"] ?? 0, "unix_ms": row["unix_ms"] ?? 0,
            "requested_force": output, "classic_byte": LogitechWheelCommand.constant(output * sign)[2],
            "playing": state.effects.filter(\.playing).count,
            "condition_kinematics_approximate": state.effects.contains { $0.playing && $0.kind.isCondition },
            "hardware": false]
        let bytes = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
        FileHandle.standardOutput.write(bytes); FileHandle.standardOutput.write(Data([10]))
    } catch { fputs("Invalid recorded force frame: \(error)\n", stderr); exit(3) }
}
