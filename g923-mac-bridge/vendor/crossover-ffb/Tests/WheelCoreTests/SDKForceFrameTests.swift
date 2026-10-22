import XCTest
@testable import WheelCore
final class SDKForceFrameTests: XCTestCase {
    func testWireContractAndSanitizing() {
        let data = Array(SDKForceFrame.encode(level: 0.25, milliseconds: 1234))
        XCTAssertEqual(data.count,24)
        XCTAssertEqual(Array(data.prefix(8)),[71,57,75,70,1,0,0,0])
        XCTAssertEqual(Array(data[8..<16]),[210,4,0,0,0,0,0,0])
        XCTAssertEqual(Array(data[16..<24]),[0,0,0,0,0,0,208,63])
        XCTAssertEqual(Array(SDKForceFrame.encode(level: .nan,milliseconds:0).suffix(8)),Array(repeating:0,count:8))
    }
}
