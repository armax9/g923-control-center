import XCTest
@testable import WheelCore
final class ForceOutputPolicyTests: XCTestCase {
    func testCeilingDoesNotAttenuateSmallGameForces() {
        XCTAssertEqual(ForceOutputPolicy.apply(0.06, gain: 1, limit: 0.25), 0.06)
        XCTAssertEqual(ForceOutputPolicy.apply(-0.15, gain: 1, limit: 0.25), -0.15)
        XCTAssertEqual(ForceOutputPolicy.apply(0.25, gain: 1, limit: 0.25), 0.25)
    }
    func testClipsBothDirectionsAndHandlesInvalidInput() {
        XCTAssertEqual(ForceOutputPolicy.apply(1, gain: 1, limit: 0.25), 0.25)
        XCTAssertEqual(ForceOutputPolicy.apply(-1, gain: 1, limit: 0.25), -0.25)
        XCTAssertEqual(ForceOutputPolicy.apply(.nan, gain: 1, limit: 0.25), 0)
        XCTAssertEqual(ForceOutputPolicy.apply(1, gain: .infinity, limit: 0.25), 0)
    }
    func testGainRemainsIndependentOfLimit() {
        XCTAssertEqual(ForceOutputPolicy.apply(0.25, gain: 0.25, limit: 1), 0.0625)
        XCTAssertEqual(ForceOutputPolicy.apply(0.25, gain: 1, limit: 0.25), 0.25)
        XCTAssertEqual(ForceOutputPolicy.apply(0, gain: 1, limit: 0.25), 0)
    }
}
