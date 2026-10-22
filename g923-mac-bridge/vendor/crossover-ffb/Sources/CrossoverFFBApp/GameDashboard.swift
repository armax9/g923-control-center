import AppKit
import SwiftUI
import WheelCore

extension AppModel {
    func installationReady(_ game: GameEntry) -> Bool { installationLabel(game) == "Installed" }
    func installationLabel(_ game: GameEntry) -> String {
        if [690790, 227300].contains(game.steamAppID ?? 0) {
            switch entryInstallation[game.id] {
            case "installed": return "Installed"
            case "patch": return "Install required"
            case "attention": return "Needs attention"
            default: return "Checking…"
            }
        }
        return FileManager.default.fileExists(atPath: game.executable.path) ? "Integration pending" : "Game unavailable"
    }
}

struct GameThumbnail: View {
    @EnvironmentObject var model: AppModel
    let game: GameEntry
    var body: some View {
        if let id = game.steamAppID, let image = model.artwork[id] {
            Image(nsImage: image).resizable().scaledToFill()
        } else {
            ZStack {
                LinearGradient(colors: GamePalette.colors(for: game.name), startPoint: .topLeading, endPoint: .bottomTrailing)
                Image(systemName: "flag.checkered").foregroundStyle(.white)
            }
        }
    }
}

struct DashboardPage: View {
    @EnvironmentObject var model: AppModel
    @ObservedObject private var session = AppModel.shared.projectSession
    var body: some View {
        Page(title: "Games", subtitle: "The bridge connects automatically.") {
            HStack {
                Label(model.wheelDetected ? "G923 PlayStation detected" : "Connect your G923 PlayStation", systemImage: "steeringwheel")
                Spacer()
                Text(session.bridgeArmed ? "Bridge on" : "Bridge off").foregroundStyle(session.bridgeArmed ? Color.cyan : Color.secondary)
            }.padding(20).background(Color.cyan.opacity(0.08), in: RoundedRectangle(cornerRadius: 18))
            HStack {
                Text("Your games").font(.title2.bold())
                Spacer()
                Button { model.rescan(); model.refreshPreparedInstallation() } label: { Image(systemName: "arrow.clockwise") }.disabled(model.scanning).help("Refresh games and installation status")
                Button { model.addGame() } label: { Label("Add Game", systemImage: "plus") }
            }
            if model.pendingCustomExe != nil { GameAdditionView() }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 235, maximum: 340), spacing: 18)], spacing: 18) {
                ForEach(model.games) { game in
                    Button { model.selectGame(game) } label: {
                        VStack(alignment: .leading, spacing: 0) {
                            GameThumbnail(game: game).frame(height: 145).clipped()
                            VStack(alignment: .leading, spacing: 8) {
                                Text(game.name).font(.headline).lineLimit(1)
                                HStack {
                                    Circle().fill(model.installationReady(game) ? Color.green : Color.secondary).frame(width: 6, height: 6)
                                    Text(model.installationLabel(game)).font(.caption).foregroundStyle(.secondary)
                                    Spacer()
                                    Image(systemName: "arrow.up.right").foregroundStyle(.secondary)
                                }
                            }.padding(16)
                        }.background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 18)).clipShape(RoundedRectangle(cornerRadius: 18))
                    }.buttonStyle(.plain)
                }
            }
            if model.games.isEmpty { Text(model.scanning ? "Looking for supported games…" : "Add a game to get started.").foregroundStyle(.secondary) }
            Text("Select a game for its settings, installation and compatibility details.").font(.callout).foregroundStyle(.secondary)
        }
    }
}

struct GameDetailPage: View {
    @EnvironmentObject var model: AppModel
    @ObservedObject private var session = AppModel.shared.projectSession
    let game: GameEntry
    private var id: Int { game.steamAppID ?? 0 }
    private var accepted: Bool { [690790, 227300].contains(id) }
    private var installed: Bool { model.installationReady(game) }
    private var isCurrent: Bool {
        guard session.activeAppID == id && session.running else { return false }
        if let path = session.activeGameExe,
           URL(fileURLWithPath: path).resolvingSymlinksInPath().path != game.executable.resolvingSymlinksInPath().path { return false }
        if let path = session.activeBottle,
           URL(fileURLWithPath: path).resolvingSymlinksInPath().path != game.prefix.url.resolvingSymlinksInPath().path { return false }
        return true
    }
    private var connection: String {
        guard isCurrent else { return session.running ? "Waiting for this game" : "Bridge off" }
        if session.inputConnected { return "Input / FFB connected" }
        return session.backendReady ? "Input bridge ready" : "Connecting…"
    }
    private var transportState: String { isCurrent ? session.nativeTransport ?? "unknown" : model.entryNativeTransport[game.id] ?? "unknown" }
    private var transportLabel: String {
        switch transportState {
        case "ready": return "Loaded"
        case "restart_required": return "Restart Steam"
        case "setup_required": return "Setup required"
        case "waiting": return "Waiting for Steam"
        default: return "Not verified"
        }
    }
    var body: some View {
        Page(title: game.name, subtitle: game.prefix.label) {
            HStack(spacing: 18) {
                GameThumbnail(game: game).frame(width: 84, height: 104).clipped().clipShape(RoundedRectangle(cornerRadius: 12))
                VStack(alignment: .leading, spacing: 8) {
                    Text(accepted ? "G923 PlayStation" : "Compatibility profile").font(.title2.bold())
                    Text(installed ? "Components installed. Connection is shown below." : "Install components to continue.")
                        .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }.padding(20).frame(maxWidth: .infinity, alignment: .leading).background(Color.accentColor.opacity(0.09), in: RoundedRectangle(cornerRadius: 20))
            Card(title: "Status") {
                statusRow("Installation", model.installationLabel(game), ready: installed)
                statusRow("Connection", connection, ready: isCurrent && session.inputConnected)
                if id == 690790 { statusRow("TRUEFORCE transport", transportLabel, ready: transportState == "ready") }
                if id == 227300 {
                    statusRow("Engine telemetry", isCurrent && session.telemetryLive ? "Receiving" : "Idle", ready: isCurrent && session.telemetryLive)
                }
            }
            if id == 227300 { ets2Settings }
            else if id == 690790 { nativeSettings }
            else {
                Card(title: "Game settings") {
                    Text("Experimental integration. Automatic connection is not enabled for this game.").foregroundStyle(.secondary).padding(.vertical, 12)
                }
            }
            if id == 690790 { NativeSetupCard(game: game) }
            else { installation }
            compatibility

        }
    }
    private var ets2Settings: some View {
        VStack(spacing: 18) {
            Card(title: "Force feedback", footer: "100% is the game’s original strength.") {
                Row(symbol: "steeringwheel", title: "FFB strength", subtitle: "Resistance, centering and impacts", divider: false) {
                    PercentSlider(value: model.preferenceBinding(id, \.ffbStrength))
                        .disabled(isCurrent)
                }
            }
            Card(title: "Engine vibration", footer: "Changes apply immediately, including during a drive.") {
                Row(symbol: "waveform", color: .orange, title: "Enable engine vibration", subtitle: nil) {
                    Toggle("Enable engine vibration", isOn: model.preferenceBinding(id, \.trueForceEnabled)).labelsHidden().toggleStyle(.switch)
                }
                Row(title: "Engine intensity", subtitle: "0% turns vibration off", divider: false) {
                    PercentSlider(value: model.preferenceBinding(id, \.engineVibration))
                        .disabled(!model.gamePreference(id).trueForceEnabled)
                }
            }
            if isCurrent { Text("FFB strength can be changed after closing the game.").font(.caption).foregroundStyle(.secondary) }
        }.disabled(model.gamePreferencesError != nil)
    }
    private var nativeSettings: some View {
        Card(title: "Force feedback & TRUEFORCE") {
            Row(symbol: "steeringwheel", title: "FFB strength", subtitle: "Adjust in the game's Vibration & Feedback menu") { Text("Game controlled").foregroundStyle(.secondary) }
            Row(symbol: "waveform", color: .blue, title: "Native TRUEFORCE", subtitle: "Enable TRUEFORCE and adjust Logitech Engine, Surface and Tyre Slip in the game.", divider: false) { Text("Game controlled").foregroundStyle(.secondary) }
        }
    }
    private var installation: some View {
        Card(title: "Installation") {
            Row(symbol: "shippingbox", title: "Required components", subtitle: game.prefix.label) {
                if accepted {
                    if installed { Label("Installed", systemImage: "checkmark.circle.fill").foregroundStyle(.green) }
                    else if model.entryInstallation[game.id] != nil {
                        Button("Install components") { model.patchPrepared(game) }.buttonStyle(.borderedProminent).disabled(session.activeAppID != nil || model.maintenanceSession.running)
                    } else { Text("Needs attention").foregroundStyle(.orange) }
                } else { Text("Integration pending").foregroundStyle(.secondary) }
            }
            if accepted {
                Text(id == 227300 ? "Input / FFB bridge · SCS telemetry. DLAA preserved." : "Logitech SDK · CrossOver transport · game integration.")
                    .font(.caption).foregroundStyle(.secondary).padding(.vertical, 10)
                if !installed, let detail = model.entryInstallationDetails[game.id], !detail.isEmpty { Text(detail).font(.caption).foregroundStyle(.orange).textSelection(.enabled).padding(.bottom, 8) }
            }
            HStack {
                Button("Refresh status") { model.refreshPreparedInstallation() }
                Spacer()
            }.padding(.vertical, 10)
        }
    }
    private var integrationDescription: String {
        if accepted { return id == 690790 ? "Native game TRUEFORCE and FFB." : "Game FFB with optional engine vibration emulation." }
        switch GameSupport.forGame(game) {
        case .nativeSDK:
            return NativeTrueForceGame.matching(game)?.sdkInstallerAvailable == true ? "SDK integration available in source. Not tested." : "The game supports native TRUEFORCE. Bridge integration is pending."
        case .mesconSCS: return "SCS telemetry adapter available in source. Not tested."
        case .telemetryCandidate: return "Telemetry adapter available in source. Not tested."
        case .classic: return "DirectInput integration available. Not tested."
        }
    }
    private var compatibility: some View {
        Card(title: "Support & compatibility") {
            HStack(spacing: 6) {
                Tag(text: id == 690790 ? "LOGITECH SDK" : id == 227300 ? "EMULATED" : GameSupport.forGame(game) == .nativeSDK ? "SDK CANDIDATE" : "CLASSIC FFB", color: id == 690790 ? .blue : .orange, solid: true)
                if id == 227300 { Tag(text: "MESCON", color: .purple, solid: true) }
                Tag(text: accepted ? "TESTED · G923 PLAYSTATION" : "UNTESTED", color: accepted ? .green : .secondary, solid: false)
            }.padding(.vertical, 12)
            Text(integrationDescription)
                .font(.caption).foregroundStyle(.secondary).padding(.bottom, 12)
        }
    }
    private func statusRow(_ title: String, _ value: String, ready: Bool) -> some View {
        Row(title: title, divider: title != "Engine telemetry") {
            HStack(spacing: 6) { Circle().fill(ready ? Color.green : Color.secondary.opacity(0.5)).frame(width: 6, height: 6); Text(value).foregroundStyle(ready ? Color.green : Color.secondary) }
        }
    }
}

struct ApplicationSettingsPage: View {
    @EnvironmentObject var model: AppModel
    @ObservedObject private var session = AppModel.shared.projectSession
    var body: some View {
        Page(title: "Settings", subtitle: "Game-specific settings are saved with each game.") {
            Card(title: "Application", footer: "The bridge starts automatically with this app.") {
                Row(symbol: "menubar.rectangle", title: "Show in menu bar", divider: false) { Toggle("Show in menu bar", isOn: $model.showInMenuBar).labelsHidden().toggleStyle(.switch) }
            }
            if let error = model.gamePreferencesError { Text(error).foregroundStyle(.orange).textSelection(.enabled) }
            Card(title: "Diagnostics") {
                Row(symbol: "doc.text", title: "Session and logs", divider: false) { Button("Open") { model.openDiagnostics() } }
            }
            Text("G923 Control Center · 0.6.2").font(.caption).foregroundStyle(.secondary)
        }
    }
}
