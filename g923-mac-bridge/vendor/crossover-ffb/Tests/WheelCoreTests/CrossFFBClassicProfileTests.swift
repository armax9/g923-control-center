import XCTest
@testable import WheelCore
final class CrossFFBClassicProfileTests: XCTestCase {
    func testPinnedReferenceVectors() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let file = root.appendingPathComponent("fixtures/crossffb-constant-vectors.txt")
        let text = try String(contentsOf: file, encoding: .utf8)
        let lines = text.split(separator: "\n")
        XCTAssertEqual(lines.count, 201)
        for line in lines {
            let words = line.split(separator:" ").map { Int($0)! }
            XCTAssertEqual(CrossFFBClassicProfile.constant(Double(words[0])/10000,length:7), words.dropFirst().map { UInt8($0) })
        }
    }
    func testRecordedETS2ReferenceVectors() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let text = try String(contentsOf: root.appendingPathComponent("fixtures/crossffb-recorded-vectors.txt"), encoding: .utf8)
        XCTAssertGreaterThan(text.split(separator:"\n").count,201)
        for line in text.split(separator:"\n") {
            let words=line.split(separator:" ").map { Int($0)! }
            XCTAssertEqual(CrossFFBClassicProfile.constant(Double(words[0])/10000,length:7), words.dropFirst().map { UInt8($0) })
        }
    }
    func testInitializationAndNoMagnitudeBoost() {
        let commands=CrossFFBClassicProfile.initialization(range:900)
        XCTAssertEqual(commands.map { $0[0] },[0xf3,0xf5,0xf8,0x0d])
        XCTAssertTrue(commands.allSatisfy { $0.count==16 })
        XCTAssertEqual(Array(commands.last!.prefix(7)),[0x0d,1,0,0,0,0,0])
        XCTAssertEqual(CrossFFBClassicProfile.forceByte(0),128)
        XCTAssertEqual(CrossFFBClassicProfile.forceByte(.nan),128)
        XCTAssertEqual(CrossFFBClassicProfile.forceByte(0.25),159)
    }
}
