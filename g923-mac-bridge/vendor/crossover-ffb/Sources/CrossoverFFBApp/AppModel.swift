import AppKit
import IOKit.hid
import SwiftUI
import WheelCore

/// Everything the menu and the settings window show, kept in sync with the bridge thread and
/// UserDefaults.
@MainActor
final class AppModel: ObservableObject {
    static let shared = AppModel()
    /// What the menu bar icon shows; changes only when the icon itself changes.
    final class IconState: ObservableObject {
        @Published var running = false
        @Published var gameActive = false
    }
    let icon = IconState()
    static var current: AppModel? { shared }
    let projectSession = ProjectSession()
    let maintenanceSession = ProjectSession()
    private var maintenanceWasRunning = false
    @Published var wheelAccessEnabled = true
    func setWheelAccess(_ enabled: Bool) {
        wheelAccessEnabled = enabled
        if !enabled {
            projectSession.cancel()
            passiveConnected = false
            wheelDetected = false
        } else { nextPassiveScan = .distantPast; startAutomaticBridge() }
    }

    @Published var entryInstallation: [String: String] = [:]
    @Published var entryInstallationDetails: [String: String] = [:]
    @Published var entryNativeTransport: [String: String] = [:]
    @Published var nativeSetup: [String: NativeSetupState] = [:]
    var discoveredRunners: [String: [(String, URL)]] = [:]
    var ets2EngineVibration: Double { UserDefaults.standard.object(forKey: "ets2EngineVibration") as? Double ?? 10 }
    private let defaults = UserDefaults.standard
    private var timer: Timer?
    private var passiveConnected = false
    private var nextPassiveScan = Date.distantPast

    private var settingsWindow: NSWindow?

    @Published var wheelDetected = false
    /// Shared with the scene's @AppStorage("showInMenuBar"), which also changes when the icon is
    /// ⌘-dragged out of the menu bar; Settings is then the way back in.
    @Published var showInMenuBar: Bool {
        didSet {
            guard showInMenuBar != oldValue else { return }
            if defaults.bool(forKey: "showInMenuBar") != showInMenuBar { defaults.set(showInMenuBar, forKey: "showInMenuBar") }
            if !showInMenuBar { DispatchQueue.main.async { MainActor.assumeIsolated { self.showSettings(.general) } } }
        }
    }
    @Published var settingsTab = SettingsTab.games
    @Published var selectedGameID: String?
    @Published var gamePreferences: [String: GamePreference] = [:]
    @Published var gamePreferencesError: String?
    var gamePreferencesNeedSaving = true

    // Games
    @Published var games: [GameEntry] = []
    @Published var scanning = false
    @Published var busyGame: String?
    @Published var notice: Notice?
    @Published var pendingCustomExe: URL?
    @Published var prefixChoices: [WinePrefix] = []
    @Published var artwork: [Int: NSImage] = [:]
    private var artworkRequested = Set<Int>()

    struct Notice: Identifiable { let id = UUID(); var title: String; var message: String }
    enum SettingsTab: Hashable { case games, general }

    init() {
        defaults.register(defaults: ["showInMenuBar": true])
        showInMenuBar = defaults.bool(forKey: "showInMenuBar")
        loadGamePreferences()
        timer = Timer(timeInterval: 1, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                if self.wheelAccessEnabled && Date() >= self.nextPassiveScan {
                    self.nextPassiveScan = Date().addingTimeInterval(1)
                    let manager = IOHIDManagerCreate(kCFAllocatorDefault, 0)
                    IOHIDManagerSetDeviceMatching(manager, [kIOHIDVendorIDKey: 0x046d, kIOHIDProductIDKey: 0xc266] as CFDictionary)
                    self.passiveConnected = !(IOHIDManagerCopyDevices(manager) as? Set<IOHIDDevice> ?? []).isEmpty
                    self.wheelDetected = self.passiveConnected
                }
                let armed = self.projectSession.bridgeArmed
                if armed != self.icon.running { self.icon.running = armed }
                if self.projectSession.inputConnected != self.icon.gameActive { self.icon.gameActive = self.projectSession.inputConnected }
                if self.maintenanceWasRunning && !self.maintenanceSession.running {
                    self.busyGame = nil
                    self.refreshPreparedInstallation()
                    if self.maintenanceSession.status.hasPrefix("Failed") || self.maintenanceSession.status == "Launch failed" {
                        self.notice = Notice(title: "Installation failed", message: "See Diagnostics in Settings for details.")
                    }
                }
                self.maintenanceWasRunning = self.maintenanceSession.running
            }
        }
        RunLoop.main.add(timer!, forMode: .common)
        let snapshot = CommandLine.arguments.contains("--snapshot")
        // Snapshot rendering never arms a hardware session.
        if snapshot { return }
        rescan()
        refreshPreparedInstallation()
        NotificationCenter.default.addObserver(forName: UserDefaults.didChangeNotification, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                let value = self.defaults.bool(forKey: "showInMenuBar")
                if value != self.showInMenuBar { self.showInMenuBar = value }
            }
        }
        NotificationCenter.default.addObserver(forName: NSApplication.willTerminateNotification, object: nil, queue: .main) { [weak self] _ in MainActor.assumeIsolated { self?.projectSession.cancel(); self?.maintenanceSession.cancel() } }

    }

    // MARK: automatic bridge

    func toggleRunning() {
        if projectSession.bridgeArmed { projectSession.cancel() }
        else { startAutomaticBridge() }
    }
    func startAutomaticBridge() {
        guard !projectSession.running, !projectSession.stopping, wheelAccessEnabled,
              !CommandLine.arguments.contains("--snapshot") else { return }
        guard let root = projectRoot else {
            notice = Notice(title: "Bridge unavailable", message: "The installed bridge tools could not be found.")
            return
        }
        guard PythonRuntime.locate() != nil else {
            notice = Notice(title: "Python required", message: "Install Python 3.10 or newer, then reopen G923 Control Center.")
            return
        }
        guard saveGamePreferences() else { return }
        projectSession.start(title: "Wheel bridge", arguments: [root.appendingPathComponent("sdk-lab/tools/auto_bridge.py").path, "start", "--user-ready", "--registry", profileRegistryURL.path, "--settings-file", gamePreferencesURL.path], directory: root)
    }
    var profileRegistryURL: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("G923 Control Center/Profiles/registry.json")
    }
    func refreshPreparedInstallation() {
        guard let root = projectRoot, let python = PythonRuntime.locate() else {
            entryInstallation = Dictionary(uniqueKeysWithValues: games.map { ($0.id, "attention") })
            entryInstallationDetails = Dictionary(uniqueKeysWithValues: games.map { ($0.id, "Python 3.10 or newer and bundled bridge tools are required.") })
            return
        }
        let currentGames = games
        for game in currentGames where game.steamAppID == 690790 { refreshNativeSetup(game) }
        DispatchQueue.global(qos: .utility).async { [weak self] in
            do {
                let rows = try Self.helperJSON(python: python, root: root, arguments: ["status", "--json"])
                let profiles = rows["profiles"] as? [[String: Any]] ?? []
                var states: [String: String] = [:], details: [String: String] = [:], transports: [String: String] = [:]
                for game in currentGames where [690790, 227300].contains(game.steamAppID ?? 0) {
                    let profile = profiles.first {
                        ($0["game_exe"] as? String).map { URL(fileURLWithPath: $0).standardizedFileURL == game.executable.standardizedFileURL } == true &&
                        ($0["source_bottle"] as? String).map { URL(fileURLWithPath: $0).resolvingSymlinksInPath().path == game.prefix.url.resolvingSymlinksInPath().path } == true
                    }
                    states[game.id] = profile.map { $0["installed"] as? Bool == true ? "installed" : "attention" } ?? "patch"
                    details[game.id] = profile?["detail"] as? String ?? ""
                    transports[game.id] = profile?["nativeTransport"] as? String
                }
                DispatchQueue.main.async { MainActor.assumeIsolated {
                    self?.entryInstallation = states; self?.entryInstallationDetails = details; self?.entryNativeTransport = transports
                } }
            } catch {
                let message = "Installation could not be verified: " + error.localizedDescription
                DispatchQueue.main.async { MainActor.assumeIsolated {
                    self?.entryInstallation = Dictionary(uniqueKeysWithValues: currentGames.map { ($0.id, "attention") })
                    self?.entryInstallationDetails = Dictionary(uniqueKeysWithValues: currentGames.map { ($0.id, message) })
                } }
            }
        }
    }
    nonisolated static func helperJSON(python: URL, root: URL, arguments: [String]) throws -> [String: Any] {
        let process = Process(), output = Pipe()
        process.executableURL = python
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        process.environment = environment
        process.arguments = [root.appendingPathComponent("sdk-lab/tools/bootstrap.py").path] + arguments
        process.standardOutput = output; process.standardError = FileHandle.nullDevice
        process.standardInput = FileHandle.nullDevice
        try process.run()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            let record = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let error = record?["error"] as? String ?? record?["detail"] as? String ?? "Bridge setup could not be inspected (exit \(process.terminationStatus)). Open Diagnostics for details."
            throw NSError(domain: "G923", code: Int(process.terminationStatus), userInfo: [NSLocalizedDescriptionKey: error])
        }
        return (try JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
    }
    func openDiagnostics() {
        if maintenanceSession.hasLog && (maintenanceSession.status.hasPrefix("Failed") || maintenanceSession.status == "Launch failed") {
            maintenanceSession.presented = true
        } else { projectSession.presented = true }
    }
    func setupRunner(_ game: GameEntry) -> URL? {
        let choices = discoveredRunners[game.prefix.url.resolvingSymlinksInPath().path] ?? []
        let runner: URL
        if let selected = game.runner { runner = selected }
        else if choices.count == 1 { runner = choices[0].1 }
        else if choices.count > 1 {
            let alert = NSAlert()
            alert.messageText = "Choose CrossOver for this bottle"
            alert.informativeText = "More than one compatible installation was found. Choose the application you use for this game."
            let picker = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 360, height: 28))
            for choice in choices { picker.addItem(withTitle: choice.0 + " · " + choice.1.path) }
            alert.accessoryView = picker; alert.addButton(withTitle: "Continue"); alert.addButton(withTitle: "Cancel")
            guard alert.runModal() == .alertFirstButtonReturn else { return nil }
            runner = choices[picker.indexOfSelectedItem].1
        } else {
            let panel = NSOpenPanel()
            panel.title = "Choose CrossOver"
            panel.message = "Choose the CrossOver or CrossOver Preview application used for this bottle."
            panel.canChooseDirectories = false; panel.canChooseFiles = true
            panel.allowedContentTypes = [.applicationBundle]
            guard panel.runModal() == .OK, let selected = panel.url else { return nil }
            runner = selected
        }
        return runner
    }
    func patchPrepared(_ game: GameEntry) {
        guard let root = projectRoot, projectSession.activeAppID == nil, !maintenanceSession.running,
              let runner = setupRunner(game) else { return }
        let arguments = [root.appendingPathComponent("sdk-lab/tools/bootstrap.py").path,
            "install", "--appid", String(game.steamAppID ?? 0), "--exe", game.executable.path,
            "--prefix", game.prefix.url.path, "--runner", runner.path]
        busyGame = game.id
        maintenanceSession.start(title: "Install " + game.name, arguments: arguments, directory: root)
    }

    // MARK: settings window

    func showSettings(_ tab: SettingsTab? = nil) {
        // Menu-bar agents need an explicit icon when promoted to a Dock application.
        if let url = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"),
           let image = NSImage(contentsOf: url) { NSApp.applicationIconImage = image }
        NSApp.setActivationPolicy(.regular)
        if let tab { settingsTab = tab }
        if settingsWindow == nil {
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1120, height: 780),
                                  styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
            window.title = "G923 Control Center"
            // Sidebar runs the full height under a transparent title bar, as in System Settings.
            window.titleVisibility = .hidden
            window.titlebarAppearsTransparent = true
            window.toolbarStyle = .unified
            window.isReleasedWhenClosed = false
            window.contentViewController = NSHostingController(rootView: SettingsView().environmentObject(self))
            window.setContentSize(NSSize(width: 1120, height: 780))
            window.minSize = NSSize(width: 940, height: 620)
            window.center()
            window.setFrameAutosaveName("SettingsWindow2")
            NotificationCenter.default.addObserver(forName: NSWindow.willCloseNotification, object: window, queue: .main) { _ in
                MainActor.assumeIsolated { _ = NSApp.setActivationPolicy(.accessory) }
            }
            settingsWindow = window
        }
        NSApp.activate(ignoringOtherApps: true)
        settingsWindow?.makeKeyAndOrderFront(nil)
    }

    // MARK: games

    private var customGames: [GameEntry] {
        get { (defaults.data(forKey: "customGames")).flatMap { try? JSONDecoder().decode([GameEntry].self, from: $0) } ?? [] }
        set { defaults.set(try? JSONEncoder().encode(newValue), forKey: "customGames") }
    }
    private var hiddenGames: Set<String> {
        get { Set(defaults.stringArray(forKey: "hiddenGames") ?? []) }
        set { defaults.set(Array(newValue), forKey: "hiddenGames") }
    }

    nonisolated static func discoveredGames(root: URL?, python: URL?) -> ([GameEntry], [String: [(String, URL)]]) {
        guard let root, let python,
              let inventory = try? helperJSON(python: python, root: root, arguments: ["discover", "--json"]),
              let records = inventory["games"] as? [[String: Any]] else { return (GameLibrary().discover(), [:]) }
        let bottles = inventory["bottles"] as? [[String: Any]] ?? []
        let runners = inventory["runners"] as? [[String: Any]] ?? []
        func runnerChoices(_ ids: [String]) -> [(String, URL)] {
            runners.compactMap { row in
                guard let id = row["id"] as? String, ids.contains(id), let path = row["path"] as? String else { return nil }
                return (row["name"] as? String ?? "CrossOver", URL(fileURLWithPath: path))
            }
        }
        var byPrefix: [String: [(String, URL)]] = [:]
        for bottle in bottles {
            if let path = bottle["path"] as? String {
                byPrefix[URL(fileURLWithPath: path).resolvingSymlinksInPath().path] = runnerChoices(bottle["runner_ids"] as? [String] ?? [])
            }
        }
        let entries = records.compactMap { record -> GameEntry? in
            guard let executable = record["exe"] as? String, let name = record["name"] as? String,
                  let bottleID = record["bottle_id"] as? String,
                  let bottle = bottles.first(where: { $0["id"] as? String == bottleID }),
                  let prefix = bottle["path"] as? String else { return nil }
            let choices = runnerChoices(record["runner_ids"] as? [String] ?? [])
            let id = record["appid"] as? Int
            let known = id.flatMap { KnownGame.byAppID($0) }
            return GameEntry(name: known?.name ?? name, executable: URL(fileURLWithPath: executable),
                prefix: WinePrefix(url: URL(fileURLWithPath: prefix), label: (choices.count == 1 ? choices[0].0 : "CrossOver") + " · " + (bottle["name"] as? String ?? "Bottle")),
                source: record["source"] as? String ?? "CrossOver", known: known != nil,
                telemetry: known?.telemetry ?? false, steamAppID: id, runner: choices.count == 1 ? choices[0].1 : nil)
        }
        return (entries, byPrefix)
    }

    /// Synchronous scan, for --snapshot.
    func scanNow() {
        games = customGames + Self.discoveredGames(root: projectRoot, python: PythonRuntime.locate()).0.filter { $0.known && !hiddenGames.contains($0.id) && !customGames.contains($0) }
        for id in Set(games.compactMap(\.steamAppID)) { artwork[id] = GameArtwork.cover(appID: id) }
    }

    /// Fetches cover art for games that do not have it yet (in the background).
    func loadArtwork() {
        let wanted = Set(games.compactMap(\.steamAppID)).subtracting(artworkRequested)
        artworkRequested.formUnion(wanted)
        for id in wanted {
            DispatchQueue.global(qos: .utility).async {
                let image = GameArtwork.cover(appID: id)
                DispatchQueue.main.async { MainActor.assumeIsolated { if let image { self.artwork[id] = image } else { self.artworkRequested.remove(id) } } }
            }
        }
    }

    func rescan() {
        guard !scanning else { return }
        scanning = true
        games = customGames
        let custom = customGames, hidden = hiddenGames
        let root = projectRoot, python = PythonRuntime.locate()
        DispatchQueue.global(qos: .userInitiated).async {
            let (discovered, runnerChoices) = Self.discoveredGames(root: root, python: python)
            let found = discovered.filter { $0.known && !hidden.contains($0.id) }
            let base = custom
            let all = base + found.filter { f in !base.contains { $0.id == f.id } }
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    self.games = all
                    self.discoveredRunners = runnerChoices
                    self.scanning = false
                    self.loadArtwork()
                    self.refreshPreparedInstallation()
                }
            }
        }
    }

    var projectRoot: URL? {
        if let resources = Bundle.main.resourceURL {
            let root = resources.appendingPathComponent("BridgeTools")
            if FileManager.default.fileExists(atPath: root.appendingPathComponent("sdk-lab/tools/bootstrap.py").path) { return root }
        }
        // Source checkout fallback for developers; installed apps use their bundled tools.
        var directory = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath().deletingLastPathComponent()
        for _ in 0..<9 {
            if FileManager.default.fileExists(atPath: directory.appendingPathComponent("sdk-lab/tools/bootstrap.py").path) { return directory }
            directory.deleteLastPathComponent()
        }
        return nil
    }
    /// Lets the user add any 64-bit Windows game: pick its exe, the prefix is worked out when possible.
    func addGame(replacing original: GameEntry? = nil) {
        let panel = NSOpenPanel()
        panel.title = original == nil ? "Choose the game's .exe" : "Choose the .exe that actually runs \(original!.name)"
        panel.message = "Pick the Windows program of the game (for Unreal Engine games, the …-Win64-Shipping.exe inside Binaries/Win64)."
        panel.allowedContentTypes = [.init(filenameExtension: "exe")!]
        panel.allowsOtherFileTypes = false
        panel.canChooseDirectories = false
        if let original { panel.directoryURL = original.executable.deletingLastPathComponent() }
        NSApp.activate(ignoringOtherApps: true)
        guard panel.runModal() == .OK, let exe = panel.url else { return }
        guard PE.isWin64(exe) else {
            notice = Notice(title: "Not a 64-bit Windows game", message: "\(exe.lastPathComponent) is not a 64-bit Windows executable. Only 64-bit DirectInput games are supported.")
            return
        }
        if let original {
            add(exe: exe, prefix: original.prefix, name: original.name, source: original.source, hiding: original)
        } else if let prefix = GameLibrary().prefix(for: exe, among: games) {
            add(exe: exe, prefix: prefix)
        } else {
            prefixChoices = GameLibrary().prefixes()
            pendingCustomExe = exe // the Games tab shows a prefix picker
        }
    }

    func choosePrefixFolder() -> WinePrefix? {
        let panel = NSOpenPanel()
        panel.title = "Choose the Wine prefix or CrossOver bottle"
        panel.message = "The folder that contains user.reg and drive_c."
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        guard panel.runModal() == .OK, let url = panel.url else { return nil }
        let prefix = WinePrefix(url: url, label: url.lastPathComponent)
        guard prefix.exists else {
            notice = Notice(title: "Not a Wine prefix", message: "\(url.path) has no user.reg. Choose the bottle / prefix folder itself.")
            return nil
        }
        return prefix
    }

    func add(exe: URL, prefix: WinePrefix, name: String? = nil, source: String? = nil, hiding original: GameEntry? = nil) {
        let known = KnownGame.matching(executable: exe)
        let entry = GameEntry(name: name ?? known?.name ?? exe.deletingPathExtension().lastPathComponent, executable: exe, prefix: prefix,
                              source: source ?? prefix.label, known: known != nil, telemetry: known?.telemetry ?? false, custom: true,
                              steamAppID: original?.steamAppID ?? known?.steamAppID)
        customGames = customGames.filter { $0.id != entry.id && $0.id != original?.id } + [entry]
        if let original, !original.custom { hiddenGames.insert(original.id) }
        pendingCustomExe = nil
        rescan()
    }

    func remove(_ game: GameEntry) {
        if game.custom { customGames = customGames.filter { $0.id != game.id } } else { hiddenGames.insert(game.id) }
        rescan()
    }
}
