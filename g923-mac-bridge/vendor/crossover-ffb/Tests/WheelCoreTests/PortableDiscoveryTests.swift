import XCTest
@testable import WheelCore

final class PortableDiscoveryTests: XCTestCase {
    var root: URL!
    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory.appendingPathComponent("g923-portable-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }
    override func tearDownWithError() throws { try? FileManager.default.removeItem(at: root) }
    func write(_ text: String, _ path: URL) throws {
        try FileManager.default.createDirectory(at: path.deletingLastPathComponent(), withIntermediateDirectories: true)
        try text.write(to: path, atomically: true, encoding: .utf8)
    }
    func testPreviewAndStableBottlesRemainDistinct() throws {
        let home = root.appendingPathComponent("Another User")
        for product in ["CrossOver", "CrossOver Preview"] {
            let bottle = home.appendingPathComponent("Library/Application Support/\(product)/Bottles/Steam")
            try write("WINE", bottle.appendingPathComponent("user.reg"))
        }
        let prefixes = GameLibrary(home: home).prefixes()
        XCTAssertEqual(prefixes.count, 2)
        XCTAssertEqual(Set(prefixes.map(\.url)).count, 2)
    }
    func testCustomPreviewBottleDirectoryExpandsFixtureHome() throws {
        let home = root.appendingPathComponent("Home")
        let bottle = home.appendingPathComponent("External Bottles/Driving")
        try write("WINE", bottle.appendingPathComponent("user.reg"))
        let prefs = home.appendingPathComponent("Library/Preferences/com.codeweavers.CrossOver.preview.plist")
        let data = try PropertyListSerialization.data(fromPropertyList: ["BottleDir": "~/External Bottles"], format: .binary, options: 0)
        try FileManager.default.createDirectory(at: prefs.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: prefs)
        XCTAssertEqual(GameLibrary(home: home).prefixes().map { $0.url.path }, [bottle.path])
    }
    func testRegistryFindsSteamOutsideProgramFilesAndExternalLibrary() throws {
        let home = root.appendingPathComponent("Home")
        let bottle = home.appendingPathComponent("Library/Application Support/CrossOver Preview/Bottles/Driving")
        let disk = root.appendingPathComponent("Mounted Disk")
        let steam = disk.appendingPathComponent("Clients/Steam App")
        let library = disk.appendingPathComponent("Games/SteamLibrary")
        try write("WINE REGISTRY Version 2\n[Software\\\\Valve\\\\Steam]\n\"SteamPath\"=\"D:\\\\Clients\\\\Steam App\"\n", bottle.appendingPathComponent("user.reg"))
        let dos = bottle.appendingPathComponent("dosdevices")
        try FileManager.default.createDirectory(at: dos, withIntermediateDirectories: true)
        try FileManager.default.createSymbolicLink(at: dos.appendingPathComponent("d:"), withDestinationURL: disk)
        try write("\"libraryfolders\"\n{\n\"1\"\n{\n\"path\" \"D:\\\\Games\\\\SteamLibrary\"\n}\n}\n", steam.appendingPathComponent("steamapps/libraryfolders.vdf"))
        try write("\"AppState\"\n{\n\"appid\" \"227300\"\n\"installdir\" \"Euro Truck Simulator 2\"\n}\n", library.appendingPathComponent("steamapps/appmanifest_227300.acf"))
        let exe = library.appendingPathComponent("steamapps/common/Euro Truck Simulator 2/bin/win_x64/eurotrucks2.exe")
        try FileManager.default.createDirectory(at: exe.deletingLastPathComponent(), withIntermediateDirectories: true)
        try InstallerTests.pe64().write(to: exe)
        let games = GameLibrary(home: home).discover()
        XCTAssertEqual(games.count, 1)
        XCTAssertEqual(games.first?.executable, exe)
        XCTAssertEqual(games.first?.prefix.url.path, bottle.path)
    }
    func testSameExecutableInTwoPrefixesHasDistinctIdentity() {
        let exe = root.appendingPathComponent("Game.exe")
        let a = GameEntry(name: "Test", executable: exe, prefix: .init(url: root.appendingPathComponent("A"), label: "A"), source: "fixture", known: true, telemetry: false)
        var b = a; b.prefix.url = root.appendingPathComponent("B")
        XCTAssertNotEqual(a.id, b.id)
    }
    func testExistingSavedGameDecodesWithoutRunner() throws {
        let game = GameEntry(name: "Test", executable: root.appendingPathComponent("Game.exe"), prefix: .init(url: root, label: "Fixture"), source: "fixture", known: true, telemetry: false)
        let bytes = try JSONEncoder().encode(game)
        let decoded = try JSONDecoder().decode(GameEntry.self, from: bytes)
        XCTAssertNil(decoded.runner)
        XCTAssertEqual(decoded.id, game.id)
    }
    func testPythonCandidatesAreResolvedOnCurrentMachine() {
        let candidates = PythonRuntime.candidates(environment: ["G923_PYTHON": "/custom/python3", "PATH": "/another/bin:/custom:relative/bin"])
        XCTAssertEqual(candidates.first?.path, "/custom/python3")
        XCTAssertTrue(candidates.contains(URL(fileURLWithPath: "/another/bin/python3")))
        XCTAssertFalse(candidates.contains { $0.path.contains("relative/bin") })
    }
}
