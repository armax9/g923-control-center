import Foundation

/// Native game capability, not CrossOver compatibility or bridge installation acceptance.
/// PC-only: Logitech's TRUEFORCE (*) marker, not the dual-clutch marker or console lists.
/// New titles use verified Steam IDs; unknown executable paths are deliberately left empty.
public struct NativeTrueForceGame: Sendable {
    public let steamAppID: Int
    public let name: String
    public let aliases: [String]
    public let executables: [String]
    public let source: String
    public var sdkInstallerAvailable: Bool { [690790, 805550, 3058630].contains(steamAppID) }
    public var acceptedOnThisMac: Bool { steamAppID == 690790 }
    public static let verifiedOn = "2026-10-20"
    public static let logitechSource = "https://www.logitechg.com/en-us/products/driving/g923-trueforce-sim-racing-wheel.html"
    public static let evoSource = "https://assettocorsa.gg/wp-content/uploads/acevo_wheel-setup-guide.pdf"
    public static let catalog: [Self] = [
        .init(steamAppID: 805550, name: "Assetto Corsa Competizione", aliases: [], executables: ["AC2/Binaries/Win64/AC2-Win64-Shipping.exe"], source: logitechSource),
        .init(steamAppID: 3058630, name: "Assetto Corsa EVO", aliases: [], executables: ["AssettoCorsaEVO.exe"], source: evoSource),
        .init(steamAppID: 1066890, name: "Automobilista 2", aliases: [], executables: ["AMS2AVX.exe", "AMS2.exe"], source: logitechSource),
        .init(steamAppID: 284160, name: "BeamNG.drive", aliases: ["BeamNG Drive"], executables: ["Bin64/BeamNG.drive.x64.exe"], source: logitechSource),
        .init(steamAppID: 690790, name: "DiRT Rally 2.0", aliases: [], executables: ["dirtrally2.exe"], source: logitechSource),
        .init(steamAppID: 1849250, name: "EA Sports WRC", aliases: [], executables: ["WRC/Binaries/Win64/WRC.exe"], source: logitechSource),
        .init(steamAppID: 1692250, name: "F1 22", aliases: [], executables: ["F1_22.exe"], source: logitechSource),
        .init(steamAppID: 2108330, name: "F1 23", aliases: [], executables: ["F1_23.exe"], source: logitechSource),
        .init(steamAppID: 2488620, name: "F1 24", aliases: [], executables: ["F1_24.exe"], source: logitechSource),
        .init(steamAppID: 3059520, name: "F1 25", aliases: [], executables: ["F1_25.exe"], source: logitechSource),
        .init(steamAppID: 2440510, name: "Forza Motorsport (2023)", aliases: ["Forza Motorsport"], executables: [], source: logitechSource),
        .init(steamAppID: 703860, name: "GRID (2019)", aliases: ["GRID"], executables: [], source: logitechSource),
        .init(steamAppID: 266410, name: "iRacing", aliases: [], executables: ["iRacingSim64DX11.exe"], source: logitechSource),
        .init(steamAppID: 1209360, name: "Monster Truck Championship", aliases: [], executables: [], source: logitechSource),
        .init(steamAppID: 958400, name: "Project CARS 3", aliases: [], executables: [], source: logitechSource),
        .init(steamAppID: 1465360, name: "SnowRunner", aliases: [], executables: [], source: logitechSource),
        .init(steamAppID: 1249970, name: "Test Drive Unlimited Solar Crown", aliases: [], executables: [], source: logitechSource),
        .init(steamAppID: 1462810, name: "WRC 10", aliases: ["WRC 10 FIA World Rally Championship"], executables: [], source: logitechSource),
        .init(steamAppID: 1953520, name: "WRC Generations", aliases: ["WRC Generations – The FIA WRC Official Game"], executables: [], source: logitechSource),
    ]
    private static func normalize(_ name: String) -> String {
        name.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: Locale(identifier: "en_US_POSIX"))
            .components(separatedBy: CharacterSet.alphanumerics.inverted).filter { !$0.isEmpty }.joined()
    }
    public static func matching(_ game: GameEntry) -> Self? {
        // An explicit app ID wins over an ambiguous title such as GRID or WRC.
        if let id = game.steamAppID { return catalog.first { $0.steamAppID == id } }
        let path = game.executable.path.lowercased()
        if let match = catalog.first(where: { $0.executables.contains { path.hasSuffix("/" + $0.lowercased()) } }) { return match }
        let name = normalize(game.name)
        return catalog.first { ([ $0.name ] + $0.aliases).contains { normalize($0) == name } }
    }
}
