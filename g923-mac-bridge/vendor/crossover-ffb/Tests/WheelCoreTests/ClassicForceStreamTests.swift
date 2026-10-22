import XCTest
@testable import WheelCore
final class ClassicForceStreamTests: XCTestCase {
    func testInstallThenUpdateWithoutRecreating() {
        var stream = ClassicForceStream()
        XCTAssertEqual(stream.packet(0.25), [0x11,0,160,0,0,0,0])
        XCTAssertEqual(stream.packet(-0.25), [0x1c,0,96,0,0,0,0])
        XCTAssertEqual(stream.packet(0), [0x1c,0,128,0,0,0,0])
        stream.reset()
        XCTAssertEqual(stream.packet(0)[0], 0x11)
    }
    func testFiniteClampedPaddedOutput() {
        var stream = ClassicForceStream()
        XCTAssertEqual(stream.packet(.nan, length: 16), [0x11,0,128,0,0,0,0,0,0,0,0,0,0,0,0,0])
        XCTAssertEqual(stream.packet(10)[2],255)
        XCTAssertEqual(stream.packet(-10)[2],1)
    }
}
