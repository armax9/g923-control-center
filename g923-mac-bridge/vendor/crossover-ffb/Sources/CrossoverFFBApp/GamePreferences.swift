import AppKit
import WheelCore

import SwiftUI

/// Only settings implemented by each accepted transport are written to its profile.
struct GamePreference: Codable, Equatable {
    var ffbStrength: Double = 100
    var trueForceEnabled = true
    var engineVibration: Double = 10
    init(ffbStrength: Double = 100, trueForceEnabled: Bool = true, engineVibration: Double = 10) {
        self.ffbStrength = ffbStrength; self.trueForceEnabled = trueForceEnabled; self.engineVibration = engineVibration
    }
    enum CodingKeys: String, CodingKey { case ffbStrength, trueForceEnabled, engineVibration }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ffbStrength = try c.decodeIfPresent(Double.self, forKey: .ffbStrength) ?? 100
        trueForceEnabled = try c.decodeIfPresent(Bool.self, forKey: .trueForceEnabled) ?? true
        engineVibration = try c.decodeIfPresent(Double.self, forKey: .engineVibration) ?? 10
    }
}
private struct GamePreferenceFile: Codable {
    var version = 1
    var games: [String: GamePreference]
}

extension AppModel {
    var gamePreferencesURL: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("G923 Control Center/game-settings.json")
    }
    func loadGamePreferences() {
        let url = gamePreferencesURL
        guard FileManager.default.fileExists(atPath: url.path) else {
            gamePreferences["227300"] = GamePreference(engineVibration: ets2EngineVibration)
            return
        }
        do {
            // Preserve the file if it contains an unsupported version or invalid values.
            let data = try Data(contentsOf: url)
            guard let raw = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  Set(raw.keys) == Set(["version", "games"]),
                  let games = raw["games"] as? [String: [String: Any]] else { throw CocoaError(.fileReadCorruptFile) }
            for (id, fields) in games {
                guard let appID = Int(id), appID > 0, String(appID) == id else { throw CocoaError(.fileReadCorruptFile) }
                let allowed: Set<String> = id == "227300" ? ["ffbStrength", "trueForceEnabled", "engineVibration"] : []
                guard Set(fields.keys).isSubset(of: allowed) else { throw CocoaError(.fileReadCorruptFile) }
            }
            let file = try JSONDecoder().decode(GamePreferenceFile.self, from: data)
            guard file.version == 1 else { throw CocoaError(.fileReadCorruptFile) }
            for (id, settings) in file.games where id == "227300" {
                guard settings.ffbStrength.isFinite, (0...100).contains(settings.ffbStrength),
                      settings.engineVibration.isFinite, (0...100).contains(settings.engineVibration) else {
                    throw CocoaError(.fileReadCorruptFile)
                }
            }
            gamePreferences = file.games
            gamePreferencesNeedSaving = false
        } catch {
            gamePreferencesError = "Game settings could not be read. Your file was preserved: " + error.localizedDescription
        }
    }
    @discardableResult func saveGamePreferences() -> Bool {
        guard gamePreferencesError == nil else {
            notice = Notice(title: "Game settings need attention", message: gamePreferencesError!)
            return false
        }
        guard gamePreferencesNeedSaving else { return true }
        do {
            let settings = gamePreferences["227300"] ?? GamePreference()
            let data = try JSONSerialization.data(withJSONObject: ["version": 1, "games": [
                "227300": ["ffbStrength": settings.ffbStrength, "trueForceEnabled": settings.trueForceEnabled,
                           "engineVibration": settings.engineVibration], "690790": [:] as [String: Any]
            ]], options: [.prettyPrinted, .sortedKeys])
            try FileManager.default.createDirectory(at: gamePreferencesURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            try data.write(to: gamePreferencesURL, options: .atomic)
            gamePreferencesNeedSaving = false
            return true
        } catch {
            notice = Notice(title: "Could not save game settings", message: error.localizedDescription)
            return false
        }
    }
    func gamePreference(_ id: Int) -> GamePreference { gamePreferences[String(id)] ?? GamePreference() }
    func preferenceBinding<T>(_ id: Int, _ key: WritableKeyPath<GamePreference, T>) -> Binding<T> {
        Binding(get: { self.gamePreference(id)[keyPath: key] }, set: { value in
            var next = self.gamePreference(id)
            next[keyPath: key] = value
            self.gamePreferences[String(id)] = next
            self.gamePreferencesNeedSaving = true
            self.saveGamePreferences()
        })
    }
    func selectGame(_ game: WheelCore.GameEntry) {
        selectedGameID = game.id
        settingsTab = .games
    }
}
