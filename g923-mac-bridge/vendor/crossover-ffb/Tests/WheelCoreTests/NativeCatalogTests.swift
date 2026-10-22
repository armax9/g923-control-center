import XCTest
@testable import WheelCore
final class NativeCatalogTests: XCTestCase {
    func game(_ id: Int? = nil, _ name: String = "Unknown", _ exe: String = "/games/unknown.exe") -> GameEntry {
        GameEntry(name: name, executable: URL(fileURLWithPath: exe), prefix: WinePrefix(url: URL(fileURLWithPath: "/tmp/prefix"), label: "fixture"), source: "fixture", known: false, telemetry: false, steamAppID: id)
    }
    func testNativeCatalogAndLibraryIDsAreUniqueAndComplete() {
        let ids = NativeTrueForceGame.catalog.map(\.steamAppID)
        XCTAssertEqual(ids.count, 19)
        XCTAssertEqual(Set(ids).count, ids.count)
        for entry in NativeTrueForceGame.catalog {
            XCTAssertNotNil(KnownGame.byAppID(entry.steamAppID))
            XCTAssertEqual(GameSupport.forGame(game(entry.steamAppID)), .nativeSDK)
            XCTAssertTrue(entry.source.hasPrefix("https://"))
        }
    }
    func testExecutableAndExactNameFallback() {
        XCTAssertEqual(NativeTrueForceGame.matching(game(nil, "Custom", "/Games/DiRT/DIRTRALLY2.EXE"))?.steamAppID, 690790)
        XCTAssertEqual(NativeTrueForceGame.matching(game(nil, "snowrunner"))?.steamAppID, 1465360)
        XCTAssertEqual(NativeTrueForceGame.matching(game(nil, "GRID"))?.steamAppID, 703860)
        XCTAssertNil(NativeTrueForceGame.matching(game(nil, "GRID 2")))
        XCTAssertNil(NativeTrueForceGame.matching(game(nil, "Project CARS 2")))
        XCTAssertNil(NativeTrueForceGame.matching(game(227300, "GRID")))
    }
    func testNoNativeLabelFromWheelOrConsoleOnlySupport() {
        for id in [227300,270880,244210,378860,211500,365960,2399420] {
            XCTAssertNotEqual(GameSupport.forGame(game(id)), .nativeSDK)
        }
        XCTAssertEqual(GameSupport.forGame(game(227300)), .mesconSCS)
        XCTAssertEqual(GameSupport.forGame(game(378860)), .telemetryCandidate)
        XCTAssertNil(NativeTrueForceGame.matching(game(nil, "Gran Turismo 7")))
    }
    func testMesconCatalogIsDistinctFromNativeAndKeepsAdapterRequirements() {
        XCTAssertEqual(MesconTelemetryGame.catalog.count, 7)
        for entry in MesconTelemetryGame.catalog {
            XCTAssertNotEqual(GameSupport.forGame(game(entry.steamAppID)), .nativeSDK)
            XCTAssertNotNil(KnownGame.byAppID(entry.steamAppID))
            XCTAssertFalse(entry.requirements.isEmpty)
            XCTAssertTrue(GameSupport.forGame(game(entry.steamAppID)).title.contains("emulated"))
        }
        XCTAssertEqual(MesconTelemetryGame.matching(game(nil, "Custom", "/Games/acs.exe"))?.steamAppID, 244210)
        XCTAssertEqual(GameSupport.forGame(game(1066890)), .nativeSDK)
        XCTAssertEqual(GameSupport.forGame(game(999999)), .classic)
    }
    func testNativeCapabilityDoesNotClaimInstallerOrAcceptance() {
        XCTAssertEqual(NativeTrueForceGame.catalog.filter(\.acceptedOnThisMac).map(\.steamAppID), [690790])
        XCTAssertFalse(NativeTrueForceGame.matching(game(1465360))!.sdkInstallerAvailable)
        XCTAssertTrue(NativeTrueForceGame.matching(game(805550))!.sdkInstallerAvailable)
    }
}
