import AppKit
import SwiftUI

struct MenuView: View {
    @EnvironmentObject var model: AppModel
    @ObservedObject private var session = AppModel.shared.projectSession
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 12) {
                IconTile(symbol: "steeringwheel", color: .cyan, size: 42)
                VStack(alignment: .leading, spacing: 3) {
                    Text("G923 Control Center").font(.headline)
                    Text(model.wheelDetected ? "Wheel detected" : "Wheel not detected").font(.caption).foregroundStyle(.secondary)
                }
            }
            Divider()
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Automatic bridge").font(.subheadline.bold())
                    Text(session.stopping ? "Stopping…" : session.bridgeArmed ? "On" : "Off").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Toggle("Bridge", isOn: Binding(get: { session.bridgeArmed }, set: { _ in model.toggleRunning() }))
                    .labelsHidden().toggleStyle(.switch)
                    .disabled(!model.wheelAccessEnabled || session.stopping || (session.running && !session.isBridgeSession))
            }
            if session.bridgeArmed { Text(session.status).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true) }
            Button("Open Control Center") { model.showSettings(.games) }.buttonStyle(.borderedProminent).frame(maxWidth: .infinity)
            HStack {
                Text("G923 PlayStation").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Quit") { session.cancel(); NSApp.terminate(nil) }.buttonStyle(.plain).foregroundStyle(.secondary)
            }
        }.padding(20).frame(width: 330)
    }
}
