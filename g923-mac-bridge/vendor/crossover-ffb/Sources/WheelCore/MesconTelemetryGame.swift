import Foundation

/// Ported telemetry adapters, not native game TRUEFORCE or physical-game acceptance.
public struct MesconTelemetryGame: Sendable {
    public let steamAppID: Int
    public let name: String
    public let adapter: String
    public let requirements: String
    public static let upstream = "https://github.com/mescon/logitech-trueforce-linux-driver"
    public static let upstreamCommit = "972274bdce293419c058eb10b796feb232bfd9ef"
    public static let catalog: [Self] = [
        .init(steamAppID: 227300, name: "Euro Truck Simulator 2", adapter: "SCS telemetry", requirements: "SCS telemetry and input/FFB bridge. Tested on G923 PlayStation."),
        .init(steamAppID: 270880, name: "American Truck Simulator", adapter: "SCS telemetry", requirements: "SCS plugin and input/FFB bridge. Gameplay untested."),
        .init(steamAppID: 244210, name: "Assetto Corsa", adapter: "Shared-memory relay", requirements: "Windows telemetry relay in the game's bottle. Gameplay untested."),
        .init(steamAppID: 378860, name: "Project CARS 2", adapter: "PCARS2 UDP", requirements: "Enable PCARS2-format UDP telemetry in the game. Gameplay untested."),
        .init(steamAppID: 365960, name: "rFactor 2", adapter: "Shared-memory relay", requirements: "Game shared-memory plugin and Windows relay required. Game plugin is not included. Gameplay untested."),
        .init(steamAppID: 2399420, name: "Le Mans Ultimate", adapter: "Shared-memory relay", requirements: "Game shared-memory plugin and Windows relay required. Game plugin is not included. Gameplay untested."),
        .init(steamAppID: 211500, name: "RaceRoom Racing Experience", adapter: "Shared-memory relay", requirements: "Windows telemetry relay in the game's bottle. Gameplay untested.")
    ]
    public static func matching(_ game: GameEntry) -> Self? {
        if let id = game.steamAppID { return catalog.first { $0.steamAppID == id } }
        if let known = KnownGame.matching(executable: game.executable), let id = known.steamAppID {
            return catalog.first { $0.steamAppID == id }
        }
        return catalog.first { $0.name.caseInsensitiveCompare(game.name) == .orderedSame }
    }
}
