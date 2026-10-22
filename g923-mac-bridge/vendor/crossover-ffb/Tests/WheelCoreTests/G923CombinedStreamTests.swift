import XCTest
@testable import WheelCore
final class G923CombinedStreamTests: XCTestCase {
    func word(_ bytes: [UInt8], _ offset: Int) -> Int { Int(bytes[offset]) | Int(bytes[offset+1]) << 8 }
    func testEngineSilenceKeepsGameForceInWindowAndCurrent() {
        var stream = TrueForceStreamer()
        let packet = stream.packet(torque: 0.2, samples: [0,0,0,0], g923Combined: true)
        let force = word(packet, 6)
        XCTAssertGreaterThan(force, 32768)
        XCTAssertEqual(force, word(packet, 8))
        for slot in 9...12 {
            XCTAssertEqual(word(packet,12+slot*4), force)
            XCTAssertEqual(word(packet,14+slot*4), force)
        }
        XCTAssertEqual(packet[10],4);XCTAssertEqual(packet[11],13)
    }
    func testAudioAndForceAreBothPresentAndCurrentFollowsNewest() {
        var stream = TrueForceStreamer()
        let packet = stream.packet(torque: -0.3, samples: [0.08,-0.08], g923Combined: true)
        XCTAssertLessThan(word(packet,56),32768)
        XCTAssertLessThan(word(packet,60),word(packet,56))
        XCTAssertEqual(word(packet,6),word(packet,60))
    }
    func testSaturatesWithoutWrapAndZeroStaysZero() {
        var stream = TrueForceStreamer()
        let positive=stream.packet(torque:0.8,samples:[0.7],g923Combined:true)
        XCTAssertEqual(word(positive,6),65535)
        let negative=stream.packet(torque:-0.8,samples:[-0.7],g923Combined:true)
        XCTAssertEqual(word(negative,6),1)
        let zero=stream.packet(torque:0,samples:[0],g923Combined:true)
        XCTAssertEqual(word(zero,6),32768)
    }
    func testShutdownFlushesEveryHistoricalForceSample() {
        var stream = TrueForceStreamer(sequence: 8)
        _ = stream.packet(torque:0.7,samples:[Double](repeating:0.1,count:12),g923Combined:true)
        let silent=stream.silencePacket()
        XCTAssertEqual(silent[5],10)
        XCTAssertEqual(word(silent,6),32768)
        for slot in 0..<13 {
            XCTAssertEqual(word(silent,12+4*slot),32768)
            XCTAssertEqual(word(silent,14+4*slot),32768)
        }
    }
    func testSymmetricEngineTextureKeepsGameForceBias() {
        var stream = TrueForceStreamer()
        let p=stream.packet(torque:0.25,samples:[-0.12,0.12],g923Combined:true)
        let average=(Double(word(p,56))+Double(word(p,60)))/2
        XCTAssertEqual((average-32768)/32767,0.25,accuracy:0.0001)
    }
    func testLegacySeparateCurrentIsUnchangedUnlessExplicitlySelected() {
        var stream = TrueForceStreamer()
        let p=stream.packet(torque:0.2,samples:[-0.1])
        XCTAssertGreaterThan(word(p,6),32768)
        XCTAssertLessThan(word(p,60),32768)
    }
}
