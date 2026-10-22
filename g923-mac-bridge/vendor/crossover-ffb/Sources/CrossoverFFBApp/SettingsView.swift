import AppKit
import SwiftUI
import WheelCore

enum Radius {
    static let card: CGFloat = 22
}

struct SettingsView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        NavigationSplitView {
            Sidebar()
                .navigationSplitViewColumnWidth(min: 220, ideal: 236, max: 280)
        } detail: {
            VStack(spacing: 0) {
                Group {
                switch model.settingsTab {
                case .games:
                    if let game = model.games.first(where: { $0.id == model.selectedGameID }) { GameDetailPage(game: game) }
                    else { DashboardPage() }
                case .general: ApplicationSettingsPage()
                }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        }
        .frame(minWidth: 780, minHeight: 540)
        .background(ProjectSessionPresenter(session: model.projectSession))
        .background(ProjectSessionPresenter(session: model.maintenanceSession))
        .alert(item: $model.notice) { notice in
            Alert(title: Text(notice.title), message: Text(notice.message), dismissButton: .default(Text("OK")))
        }
    }
}

// MARK: sidebar

private struct Sidebar: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                IconTile(symbol: "steeringwheel", color: .cyan, size: 34)
                VStack(alignment: .leading, spacing: 2) {
                    Text("G923").font(.title3.bold())
                    Text("CONTROL CENTER").font(.system(size: 9, weight: .bold, design: .rounded)).tracking(1.4).foregroundStyle(.secondary)
                }
            }.padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 18)
            SidebarControls(session: model.projectSession).padding(.horizontal, 12)
            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    navButton("Overview", symbol: "square.grid.2x2", selected: model.settingsTab == .games && model.selectedGameID == nil) {
                        model.selectedGameID = nil; model.settingsTab = .games
                    }
                    Text("GAMES").font(.system(size: 10, weight: .bold)).tracking(1.2).foregroundStyle(.secondary).padding(.top, 18).padding(.leading, 10)
                    ForEach(model.games) { game in
                        Button { model.selectGame(game) } label: {
                            HStack(spacing: 10) {
                                GameThumbnail(game: game).frame(width: 34, height: 40).clipShape(RoundedRectangle(cornerRadius: 6))
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(game.name).font(.system(size: 12, weight: .semibold)).lineLimit(2)
                                    Text(model.installationLabel(game)).font(.system(size: 10)).foregroundStyle(model.installationReady(game) ? Color.green : Color.secondary)
                                }
                                Spacer(minLength: 0)
                                if model.projectSession.activeAppID == game.steamAppID && model.projectSession.backendReady {
                                    Circle().fill(Color.cyan).frame(width: 6, height: 6)
                                }
                            }.padding(9).contentShape(Rectangle())
                                .background(RoundedRectangle(cornerRadius: 10).fill(model.settingsTab == .games && model.selectedGameID == game.id ? Color.accentColor.opacity(0.22) : Color.clear))
                        }.buttonStyle(.plain)
                    }
                }.padding(12)
            }
            Divider().padding(.horizontal, 16)
            navButton("Settings", symbol: "gearshape", selected: model.settingsTab != .games) { model.settingsTab = .general }
                .padding(12)
        }
        .background(Color(nsColor: .controlBackgroundColor).opacity(0.35))
    }
    private func navButton(_ title: String, symbol: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: symbol).font(.system(size: 13, weight: .semibold)).frame(maxWidth: .infinity, alignment: .leading).padding(11)
                .background(RoundedRectangle(cornerRadius: 10).fill(selected ? Color.accentColor.opacity(0.22) : Color.clear))
        }.buttonStyle(.plain)
    }

}

/// Wheel access and bridge arming are separate: enabling access alone never sends forces.
private struct SidebarControls: View {
    @EnvironmentObject var model: AppModel
    @ObservedObject var session: ProjectSession
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 8) {
                Image(systemName: "steeringwheel").frame(width: 18)
                    .foregroundStyle(model.wheelAccessEnabled && model.wheelDetected ? Color.green : Color.secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Steering wheel").font(.subheadline.weight(.semibold))
                    Text(!model.wheelAccessEnabled ? "Disabled" : model.wheelDetected ? "Detected" : "Not detected")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                Toggle("Wheel access", isOn: Binding(get: { model.wheelAccessEnabled }, set: { model.setWheelAccess($0) }))
                    .labelsHidden().toggleStyle(.switch).controlSize(.small)
                    .help("Allow the bridge to use this wheel.")
            }
            Divider()
            HStack(spacing: 8) {
                Image(systemName: "cable.connector").frame(width: 18)
                    .foregroundStyle(session.bridgeArmed && !session.stopping ? Color.green : Color.secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Bridge").font(.subheadline.weight(.semibold))
                    Text(session.stopping ? "Stopping…" : session.bridgeArmed ? "On" : "Off")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                Toggle("Bridge", isOn: Binding(get: { session.bridgeArmed }, set: { _ in model.toggleRunning() }))
                    .labelsHidden().toggleStyle(.switch).controlSize(.small)
                    .disabled(!model.wheelAccessEnabled || session.stopping || (session.running && !session.isBridgeSession))
            }
            if session.running {
                Text(session.status).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(.quaternary.opacity(0.6)))
        .onReceive(session.$running) { running in if !running { model.refreshPreparedInstallation() } }
    }
}

/// Coloured rounded-square symbol tile, as in System Settings.
struct IconTile: View {
    let symbol: String, color: Color
    var size: CGFloat = 28
    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.5, weight: .semibold))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(RoundedRectangle(cornerRadius: size * 0.3, style: .continuous).fill(color.gradient))
    }
}

// MARK: page building blocks

struct Page<Accessory: View, Content: View>: View {
    let title: String, subtitle: String
    @ViewBuilder var accessory: Accessory
    @ViewBuilder var content: Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack(alignment: .bottom, spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(title).font(.largeTitle.weight(.bold))
                        Text(subtitle).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 12)
                    accessory
                }
                content
            }
            .padding(.horizontal, 28)
            .padding(.top, 20)
            .padding(.bottom, 28)
            .frame(maxWidth: 900, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
    }
}

extension Page where Accessory == EmptyView {
    init(title: String, subtitle: String, @ViewBuilder content: () -> Content) {
        self.init(title: title, subtitle: subtitle, accessory: { EmptyView() }, content: content)
    }
}

/// Rounded section card with an optional heading and footer.
struct Card<Content: View>: View {
    var title: String? = nil
    var footer: String? = nil
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let title { Text(title).font(.headline).padding(.leading, 6) }
            VStack(alignment: .leading, spacing: 0) { content }
                .padding(.horizontal, 16)
                .padding(.vertical, 6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: Radius.card, style: .continuous).fill(.quaternary.opacity(0.45)))
                .overlay(RoundedRectangle(cornerRadius: Radius.card, style: .continuous).strokeBorder(Color.primary.opacity(0.06)).allowsHitTesting(false))
            if let footer { Text(footer).font(.caption).foregroundStyle(.secondary).padding(.horizontal, 6).fixedSize(horizontal: false, vertical: true) }
        }
    }
}

/// One row in a card: icon tile, title and subtitle, trailing control.
struct Row<Trailing: View>: View {
    var symbol: String? = nil
    var color: Color = .accentColor
    let title: String
    var subtitle: String? = nil
    var divider = true
    @ViewBuilder var trailing: Trailing

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                if let symbol { IconTile(symbol: symbol, color: color) }
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                    if let subtitle { Text(subtitle).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true) }
                }
                Spacer(minLength: 12)
                trailing
            }
            .padding(.vertical, 10)
            if divider { Divider().padding(.leading, symbol == nil ? 0 : 40) }
        }
    }
}

struct PercentSlider: View {
    @Binding var value: Double
    var body: some View {
        HStack(spacing: 10) {
            Slider(value: Binding(get: { value }, set: { value = $0.rounded() }), in: 0...100).frame(width: 220)
            Text("\(Int(value.rounded()))%").monospacedDigit().foregroundStyle(.secondary).frame(width: 40, alignment: .trailing)
        }
    }
}

// MARK: Game installation

struct GameAdditionView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        if let exe = model.pendingCustomExe { PrefixPicker(exe: exe) }
    }
}

enum GamePalette {
    static func colors(for name: String) -> [Color] {
        let hue = Double(name.unicodeScalars.reduce(UInt32(7)) { ($0 &* 31) &+ $1.value } % 360) / 360
        return [Color(hue: hue, saturation: 0.55, brightness: 0.55),
                Color(hue: (hue + 0.08).truncatingRemainder(dividingBy: 1), saturation: 0.7, brightness: 0.3)]
    }
}

struct Tag: View {
    let text: String, color: Color
    var solid = false
    var body: some View {
        Text(text).font(.caption2.weight(.semibold)).fixedSize().padding(.horizontal, 8).padding(.vertical, 3)
            .background(solid ? color.opacity(0.9) : color.opacity(0.15), in: Capsule())
            .foregroundStyle(solid ? .white : color)
    }
}

struct PrefixPicker: View {
    @EnvironmentObject var model: AppModel
    let exe: URL
    @State private var selection = 0
    var body: some View {
        Card(title: "Add \(exe.lastPathComponent)", footer: "Choose the game’s CrossOver bottle or Wine prefix.") {
            if !model.prefixChoices.isEmpty {
                Row(symbol: "shippingbox.fill", color: .brown, title: "Game environment", divider: false) {
                    Picker("Prefix", selection: $selection) {
                        ForEach(Array(model.prefixChoices.enumerated()), id: \.offset) { i, p in Text(p.label).tag(i) }
                    }
                    .labelsHidden().frame(maxWidth: 320)
                }
            }
            HStack {
                Spacer()
                Button("Cancel") { model.pendingCustomExe = nil }.buttonStyle(.bordered)
                Button("Choose Folder…") { if let p = model.choosePrefixFolder() { model.add(exe: exe, prefix: p) } }.buttonStyle(.bordered)
                if !model.prefixChoices.isEmpty {
                    Button("Add Game") { model.add(exe: exe, prefix: model.prefixChoices[selection]) }.buttonStyle(.borderedProminent)
                }
            }
            .padding(.vertical, 10)
        }
    }
}

private struct ProjectSessionPresenter: View {
    @ObservedObject var session: ProjectSession
    var body: some View {
        Color.clear.frame(width: 0, height: 0)
            .sheet(isPresented: $session.presented) { ProjectSessionView(session: session) }
    }
}

