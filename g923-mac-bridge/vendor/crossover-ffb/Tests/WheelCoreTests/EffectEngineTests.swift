import XCTest
@testable import WheelCore

final class EffectEngineTests: XCTestCase {
    func testActualCBridgeRecordsReachSwiftEvaluatorWithoutContractDrift() throws {
        let fixture = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bridge/tests/force_contract_frames.jsonl")
        let lines = try String(contentsOf: fixture, encoding: .utf8).split(separator: "\n")
        XCTAssertEqual(lines.count, 11)
        let engine = EffectEngine()
        for (i, line) in lines.enumerated() {
            let row = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any])
            let words = try XCTUnwrap(row["words"] as? [NSNumber])
            let bytes = words.flatMap { word in (0..<4).map { UInt8(truncatingIfNeeded: word.uint32Value >> (8 * $0)) } }
            let frame = SharedBridge.decode(bytes)
            let output: Double
            if frame.paused || frame.actuatorsOff || !frame.acquired {
                engine.reset(); output = 0 // same gate as the native hardware bridge.
            } else { output = engine.force(frame, wheel: .init(), now: 1000 + Double(i) * 30) }
            let expected = try XCTUnwrap(row["expected_force"] as? Double)
            let name = try XCTUnwrap(row["case"] as? String)
            XCTAssertEqual(output, expected, accuracy: 1e-9, name)
        }
    }

    func testAuthoritativeTimelineSurvivesLateObservationAndMixerReset() {
        let engine = EffectEngine()
        var e = BridgeEffect(slot: 0, kind: .ramp, durationMicros: 1_000_000,
                             params: [0, 10000], elapsedMilliseconds: 600)
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 100), -0.6, accuracy: 1e-9)
        engine.reset() // reconnect/resume must not restart the device's envelope.
        e.elapsedMilliseconds = 800
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 200), -0.8, accuracy: 1e-9)
        var frame = state([e]); frame.playbackAdvanceMilliseconds = 50
        XCTAssertEqual(engine.force(frame, wheel: .init(), now: 200.05), -0.85, accuracy: 1e-9)
        e.elapsedMilliseconds = 1000
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 200.1), 0)
    }

    func testAuthoritativeDelayIterationsAndZeroDuration() {
        let engine = EffectEngine()
        var e = BridgeEffect(slot: 0, kind: .ramp, durationMicros: 1_000_000,
                             startDelayMicros: 200_000, params: [0, 10000],
                             iterations: 2, elapsedMilliseconds: 100)
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 1), 0)
        e.elapsedMilliseconds = 1500 // 1.3 seconds playing -> second iteration at .3.
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 2), -0.3, accuracy: 1e-9)
        e.elapsedMilliseconds = 2200
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 3), 0)
        e.durationMicros = 0; e.startDelayMicros = 0; e.elapsedMilliseconds = 0
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 4), 0)
    }

    func testTimelineExtensionRequiresPerRecordPresenceForSafeRollback() {
        var b = [UInt8](repeating: 0, count: 64 + 96 * 32)
        func put(_ o: Int, _ v: UInt32) { for i in 0..<4 { b[o+i] = UInt8(truncatingIfNeeded: v >> (8*i)) } }
        put(64, 1); put(64+92, 701)
        XCTAssertNil(SharedBridge.decode(b).effects[0].elapsedMilliseconds)
        put(32, 0x314d4954)
        XCTAssertEqual(SharedBridge.decode(b).effects[0].elapsedMilliseconds, 700)
        // Old DLL overwrites the record but leaves reserved header bytes untouched.
        put(64+92, 0)
        XCTAssertNil(SharedBridge.decode(b).effects[0].elapsedMilliseconds)
    }

    func testEffectEqualityIncludesTimingAndEnvelopeUpdates() {
        let a = BridgeEffect(slot: 0, kind: .constant, params: [5000])
        var b = a; b.durationMicros = 1000; XCTAssertNotEqual(a, b)
        b = a; b.hasEnvelope = true; XCTAssertNotEqual(a, b)
        b = a; b.elapsedMilliseconds = 100; XCTAssertNotEqual(a, b)
    }

    private func state(_ effects: [BridgeEffect], gain: UInt32 = 10000) -> BridgeForceState {
        var s = BridgeForceState()
        s.processID = 1; s.acquired = true; s.deviceGain = gain; s.effects = effects
        return s
    }

    func testConstantForceFollowsMagnitudeDirectionAndGain() {
        let engine = EffectEngine()
        let e = BridgeEffect(slot: 0, kind: .constant, gain: 5000, params: [8000])
        // A force along +X comes from the right and pushes the wheel left (DirectInput).
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 1), -0.4, accuracy: 1e-9)
        var left = e; left.direction = (-1, 0)
        XCTAssertEqual(engine.force(state([left]), wheel: .init(), now: 1), 0.4, accuracy: 1e-9)
        XCTAssertEqual(engine.force(state([e], gain: 5000), wheel: .init(), now: 1), -0.2, accuracy: 1e-9)
        engine.reverseDirectional = true
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 1), 0.4, accuracy: 1e-9)
    }

    func testPolarEastPushesTowardNegativeX() {
        let e = BridgeEffect(slot: 0, kind: .constant, coordinates: 0x20, axisCount: 2, direction: (9000, 0), params: [10000])
        XCTAssertEqual(EffectEngine().force(state([e]), wheel: .init(), now: 0), -1, accuracy: 1e-6)
    }

    func testFiniteDurationEndsAndRestartsOnNewStart() {
        let engine = EffectEngine()
        var e = BridgeEffect(slot: 0, kind: .constant, durationMicros: 100_000, params: [10000])
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 10), -1)
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 10.05), -1)
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 10.2), 0)
        e.starts = 2
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 10.3), -1)
    }

    func testSpringAndDamperResistMotion() {
        let engine = EffectEngine()
        let spring = BridgeEffect(slot: 0, kind: .spring, params: [0, 10000, 10000, 10000, 10000, 0])
        XCTAssertEqual(engine.force(state([spring]), wheel: .init(position: 0.5), now: 0), -0.5, accuracy: 1e-9)
        XCTAssertEqual(engine.force(state([spring]), wheel: .init(position: -0.25), now: 0), 0.25, accuracy: 1e-9)
        let damper = BridgeEffect(slot: 1, kind: .damper, params: [0, 5000, 5000, 10000, 10000, 0])
        XCTAssertLessThan(engine.force(state([damper]), wheel: .init(velocity: 1), now: 0), 0)
        XCTAssertGreaterThan(engine.force(state([damper]), wheel: .init(velocity: -1), now: 0), 0)
        // Reversing game direction must not turn a damper into an accelerator.
        engine.reverseDirectional = true
        XCTAssertLessThan(engine.force(state([damper]), wheel: .init(velocity: 1), now: 0), 0)
    }

    func testSineOscillatesAroundOffset() {
        let engine = EffectEngine()
        let e = BridgeEffect(slot: 0, kind: .sine, params: [5000, 1000, 0, 100_000])
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 0), -0.1, accuracy: 1e-6)
        XCTAssertEqual(engine.force(state([e]), wheel: .init(), now: 0.025), -0.6, accuracy: 1e-6)
    }

    func testSharedMemoryRoundTrip() throws {
        let path = NSTemporaryDirectory() + "cfb-test-\(UUID().uuidString)/ffb-v2.bin"
        let bridge = try SharedBridge(path: path)
        var input = BridgeInput(); input.connected = true; input.steering = 1234; input.hat = 2
        bridge.publish(input, unixMilliseconds: 99)
        let raw = try Data(contentsOf: URL(fileURLWithPath: path))
        XCTAssertEqual(raw.count, 8192)
        XCTAssertEqual(raw[0..<4], Data("CFB2".utf8))
        XCTAssertEqual(raw[64] & 1, 0)
        XCTAssertEqual(raw[80], 0xd2); XCTAssertEqual(raw[81], 0x04)
        XCTAssertEqual(bridge.readForce()?.effects.count, 0)
        XCTAssertNil(bridge.readTelemetry())
        // The DLL's telemetry block: seq, source 1, length, unix ms, then the raw page.
        var block = [UInt8](repeating: 0, count: 32 + 800)
        func put(_ o: Int, _ v: UInt32) { for k in 0..<4 { block[o + k] = UInt8(v >> (8 * k) & 0xff) } }
        put(0, 2); put(4, 1); put(8, 800); put(16, 1234); put(24, 7800); put(32, 42)
        let file = try FileHandle(forWritingTo: URL(fileURLWithPath: path))
        try file.seek(toOffset: 4096); file.write(Data(block)); try file.close()
        let telemetry = try XCTUnwrap(bridge.readTelemetry())
        XCTAssertEqual(telemetry.source, 1); XCTAssertEqual(telemetry.unixMilliseconds, 1234); XCTAssertEqual(telemetry.maxRpm, 7800)
        XCTAssertEqual(GameTelemetry.acPhysics(telemetry.bytes)?.packet, 42)
    }

    func testDecodeEffectRecord() {
        var b = [UInt8](repeating: 0, count: 64 + 96 * 32)
        func put(_ o: Int, _ v: UInt32) { for i in 0..<4 { b[o + i] = UInt8(truncatingIfNeeded: v >> (8 * i)) } }
        put(4, 77); put(16, 1); put(20, 6000)
        let r = 64 + 96
        put(r, 1); put(r + 4, 1); put(r + 8, 3); put(r + 12, .max); put(r + 20, 10000); put(r + 64, UInt32(bitPattern: -2500)); put(r + 88, 1)
        let s = SharedBridge.decode(b)
        XCTAssertEqual(s.processID, 77)
        XCTAssertEqual(s.deviceGain, 6000)
        XCTAssertEqual(s.effects.count, 1)
        XCTAssertEqual(s.effects[0].slot, 1)
        XCTAssertEqual(s.effects[0].params[0], -2500)
        XCTAssertEqual(s.effects[0].starts, 3)
    }

    func testLogitechConstantCodes() {
        XCTAssertEqual(LogitechWheelCommand.constant(0)[2], 0x80)
        XCTAssertEqual(LogitechWheelCommand.constant(1)[2], 255)
        XCTAssertEqual(LogitechWheelCommand.constant(-1)[2], 1)
        XCTAssertEqual(LogitechWheelCommand.constant(0.5, length: 16).count, 16)
        XCTAssertEqual(LogitechWheelCommand.range(900), [0xf8, 0x81, 0x84, 0x03, 0, 0, 0])
    }
}
