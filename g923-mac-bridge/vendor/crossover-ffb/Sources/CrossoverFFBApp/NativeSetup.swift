import AppKit
import SwiftUI
import WheelCore

struct NativeSetupState: Decodable {
    struct SDK: Decodable { let installed: Bool; let path: String; let version: String; let detail: String }
    struct Transport: Decodable { let installed: Bool; let available: Bool; let state: String; let detail: String }
    struct Bottle: Decodable { let configured: Bool; let detail: String }
    let sdk: SDK
    let transport: Transport
    let bottle: Bottle
}

extension AppModel {
    func refreshNativeSetup(_ game: GameEntry) {
        guard let root = projectRoot, let python = PythonRuntime.locate() else { return }
        var arguments = ["native-status", "--json", "--exe", game.executable.path, "--prefix", game.prefix.url.path]
        if let runner = game.runner { arguments += ["--runner", runner.path] }
        else if let choices = discoveredRunners[game.prefix.url.resolvingSymlinksInPath().path], choices.count == 1 {
            arguments += ["--runner", choices[0].1.path]
        }
        let command = arguments
        DispatchQueue.global(qos: .utility).async { [weak self] in
            do {
                let result = try Self.helperJSON(python: python, root: root, arguments: command)
                let data = try JSONSerialization.data(withJSONObject: result)
                let state = try JSONDecoder().decode(NativeSetupState.self, from: data)
                DispatchQueue.main.async { MainActor.assumeIsolated { self?.nativeSetup[game.id] = state } }
            } catch {
                DispatchQueue.main.async { MainActor.assumeIsolated {
                    self?.notice = Notice(title: "Setup status unavailable", message: error.localizedDescription)
                } }
            }
        }
    }
    func importNativeSDK(_ game: GameEntry) {
        guard let root = projectRoot, !maintenanceSession.running else { return }
        let panel = NSOpenPanel()
        panel.title = "Import Logitech TRUEFORCE SDK"
        panel.message = "Choose trueforce_sdk_x64.dll copied from Windows G HUB. The app stores and installs it for you."
        panel.canChooseFiles = true; panel.canChooseDirectories = false
        panel.allowedContentTypes = [.init(filenameExtension: "dll") ?? .data]
        guard panel.runModal() == .OK, let file = panel.url else { return }
        busyGame = game.id
        maintenanceSession.start(title: "Import Logitech SDK", arguments: [root.appendingPathComponent("sdk-lab/tools/bootstrap.py").path,
            "sdk-import", "--sdk-dll", file.path], directory: root)
    }
    func installNativeTransport(_ game: GameEntry) {
        guard let root = projectRoot, !maintenanceSession.running, let runner = setupRunner(game) else { return }
        busyGame = game.id
        maintenanceSession.start(title: "Install TRUEFORCE transport", arguments: [root.appendingPathComponent("sdk-lab/tools/bootstrap.py").path,
            "transport-install", "--runner", runner.path], directory: root)
    }
    var transportSourceFolder: URL? {
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("WineTransportSource", isDirectory: true)
        if let bundled, FileManager.default.fileExists(atPath: bundled.path) { return bundled }
        if let root = projectRoot, FileManager.default.fileExists(atPath: root.appendingPathComponent("docs/WINE_TRANSPORT_SOURCE.md").path) { return root }
        return nil
    }

}

struct NativeSetupCard: View {
    @EnvironmentObject var model: AppModel
    @ObservedObject private var session = AppModel.shared.projectSession
    let game: GameEntry
    @State private var guide = false
    @State private var transportGuide = false
    private var setup: NativeSetupState? { model.nativeSetup[game.id] }
    private var busy: Bool { model.maintenanceSession.running }
    var body: some View {
        Card(title: "Native TRUEFORCE setup") {
            Row(symbol: "shippingbox", title: "1. Logitech SDK", subtitle: setup?.sdk.installed == true ? "Original TRUEFORCE \(setup!.sdk.version) x64" : "Get the Windows DLL from Logitech G HUB") {
                if setup?.sdk.installed == true { Label("Installed", systemImage: "checkmark.circle.fill").foregroundStyle(.green) }
                Button("Import SDK…") { model.importNativeSDK(game) }.disabled(busy)
            }
            HStack {
                Link("Get Logitech G HUB", destination: URL(string: "https://www.logitechg.com/en-us/software/ghub")!)
                Button("SDK instructions") { guide = true }
                Spacer()
            }.font(.callout).padding(.vertical, 10)
            Row(symbol: "cpu", title: "2. CrossOver transport", subtitle: setup?.transport.detail ?? "Checking the selected CrossOver build…") {
                if setup?.transport.installed == true { Label("Installed", systemImage: "checkmark.circle.fill").foregroundStyle(.green) }
                else {
                    Button("Install transport") { model.installNativeTransport(game) }
                        .disabled(busy || (setup?.transport.available == false && setup?.transport.state != "select_runner"))
                }
            }
            Row(symbol: "gamecontroller", title: "3. Game integration", subtitle: setup?.bottle.detail ?? "Install the SDK and enable transport for this bottle", divider: false) {
                if model.installationReady(game) { Label("Installed", systemImage: "checkmark.circle.fill").foregroundStyle(.green) }
                else {
                    Button("Install game integration") { model.patchPrepared(game) }.buttonStyle(.borderedProminent)
                        .disabled(busy || session.activeAppID != nil || setup?.sdk.installed != true || setup?.transport.installed != true)
                }
            }
            HStack {
                Button("Refresh status") { model.refreshPreparedInstallation(); model.refreshNativeSetup(game) }
                Button("Wine source & build guide") { transportGuide = true }
                Spacer()
                if busy { ProgressView().controlSize(.small); Text(model.maintenanceSession.title).foregroundStyle(.secondary) }
            }.font(.callout).padding(.vertical, 12)
            Text("After setup, open Steam normally and launch the game yourself.").font(.caption).foregroundStyle(.secondary).padding(.bottom, 10)
        }
        .onAppear { model.refreshNativeSetup(game) }
        .onChange(of: busy) { value in if !value { model.refreshNativeSetup(game) } }
        .sheet(isPresented: $guide) { NativeSDKGuide() }
        .sheet(isPresented: $transportGuide) { NativeTransportGuide(folder: model.transportSourceFolder) }
    }
}

struct NativeSDKGuide: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Get the Logitech TRUEFORCE SDK").font(.title2.bold())
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("1. In Windows or Parallels, download and install the Windows version of Logitech G HUB.")
                    Link("Open the official Logitech G HUB download page", destination: URL(string: "https://www.logitechg.com/en-us/software/ghub")!)
                    Text("2. In Windows File Explorer, open this folder and copy trueforce_sdk_x64.dll:")
                    Text(#"C:\Program Files\Logi\Trueforce\1_3_12"#).font(.system(.body, design: .monospaced)).textSelection(.enabled)
                    Text("3. Copy the DLL to a Mac folder through Parallels sharing. The wheel can stay connected to the Mac.")
                    Text("4. Click Import SDK… on the game's setup page and select that DLL. You do not need to copy anything into the bottle manually.")
                    Text("The app stores the SDK here:").font(.headline)
                    Text("~/Library/Application Support/G923 Control Center/SDK/1_3_12/").font(.system(.callout, design: .monospaced)).textSelection(.enabled)
                    Text("5. Click Install transport, then Install game integration. Close Steam and games before the final integration step.")
                    Text("This release accepts the verified TRUEFORCE 1.3.12 x64 DLL. If your G HUB installation has another version, keep your existing DLL or backup; the app will report unsupported versions. The macOS G HUB installer and the separate Steering Wheel SDK do not provide this DLL.").font(.callout).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack { Spacer(); Button("Done") { dismiss() }.keyboardShortcut(.defaultAction) }
        }.padding(24).frame(width: 650, height: 620)
    }
}


struct NativeTransportGuide: View {
    @Environment(\.dismiss) private var dismiss
    let folder: URL?
    @State private var showDetails = false
    @State private var openError: String?
    private var fullGuide: String {
        guard let folder else { return "The bundled source guide could not be found. Reinstall the complete application package." }
        for name in ["README.md", "docs/WINE_TRANSPORT_SOURCE.md"] {
            if let text = try? String(contentsOf: folder.appendingPathComponent(name), encoding: .utf8) { return text }
        }
        return "The bundled source guide could not be read. Reinstall the complete application package."
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Wine source & build guide").font(.title2.bold())
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Native TRUEFORCE uses the original Logitech SDK and a patched Wine HID transport. The complete Wine source, patches, licenses and build script are included with this app.")
                    Text("Included source").font(.headline)
                    Text("Open the source folder and extract g923-wine-11.17-source.tar.xz. It contains the pinned upstream source archive, both G923 patches and the build instructions. Logitech SDK and commercial CrossOver files are provided by your own installation.")
                    Text("Build the transport").font(.headline)
                    Text("Install Xcode Command Line Tools, Bison and llvm-mingw. From the extracted source package, run the command below to inspect the build plan. Add --build to compile the module pair.")
                    Text(verbatim: """
                    python3 scripts/build-wine-transport.py \\
                      --source-archive upstream/wine-11.17.tar.gz \\
                      --output /path/to/new-build \\
                      --mingw-bin /path/to/llvm-mingw/bin
                    """)
                        .font(.system(.callout, design: .monospaced)).textSelection(.enabled)
                    Text("Future Wine versions").font(.headline)
                    Text("Port and review the patches for each new Wine/CrossOver build, compile both modules together and validate them before adding a new installer catalog entry. The included accepted pair is for CrossOver Preview 27.0.0.41069 / Wine 11.17.")
                    DisclosureGroup("Complete technical guide", isExpanded: $showDetails) {
                        Text(fullGuide).font(.system(.callout, design: .monospaced)).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 8)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack {
                Button("Open source folder") {
                    guard let folder, NSWorkspace.shared.open(folder) else {
                        openError = "The source folder could not be opened. Reinstall the complete application package."; return
                    }
                }
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
        }.padding(24).frame(width: 720, height: 620)
        .alert("Could not open source folder", isPresented: Binding(get: { openError != nil }, set: { if !$0 { openError = nil } })) {
            Button("OK") { openError = nil }
        } message: { Text(openError ?? "") }
    }
}
