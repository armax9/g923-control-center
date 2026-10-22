import AppKit
import SwiftUI
import WheelCore

/// A directly owned helper process. Output goes to disk, never to an undrained pipe.
@MainActor
final class ProjectSession: ObservableObject {
    @Published var title = "Game session"
    @Published var status = "Ready"
    @Published var output = ""
    @Published var running = false
    @Published var stopping = false
    @Published var presented = false
    @Published var isBridgeSession = false
    @Published var activeAppID: Int?
    @Published var activeGameExe: String?
    @Published var activeBottle: String?
    @Published var nativeTransport: String?
    @Published var backendReady = false
    @Published var inputConnected = false
    @Published var telemetryLive = false
    var bridgeArmed: Bool { running && isBridgeSession }
    var hasLog: Bool { logURL != nil }

    private let interpreter: URL?
    private let logDirectory: URL?
    init(interpreter: URL? = nil, logDirectory: URL? = nil) { self.interpreter = interpreter; self.logDirectory = logDirectory }
    private var projectDirectory: URL?
    private var auxiliaries: [Process] = []
    private var process: Process?
    private var logHandle: FileHandle?
    private var logURL: URL?
    private var timer: Timer?

    func start(title: String, arguments: [String], directory: URL, alongside: Bool = false) {
        projectDirectory = directory
        if running {
            guard alongside else { return }
            do {
                let child = Process()
                child.executableURL = process?.executableURL
                child.arguments = ["-u"] + arguments
                child.currentDirectoryURL = directory
                var environment = ProcessInfo.processInfo.environment
                environment["PYTHONDONTWRITEBYTECODE"] = "1"
                child.environment = environment
                child.standardInput = FileHandle.nullDevice
                child.standardOutput = logHandle
                child.standardError = logHandle
                try child.run()
                auxiliaries.append(child)
            } catch { status = "Helper failed: " + error.localizedDescription }
            return
        }
        self.title = title
        isBridgeSession = arguments.contains(where: { $0.hasSuffix("auto_bridge.py") }) && arguments.contains("start")
            || arguments.contains(where: { $0.hasSuffix("installed_play.py") })
            || arguments.contains(where: { $0.hasSuffix("ets2.py") }) && arguments.contains("start")
        activeAppID = nil; activeGameExe = nil; activeBottle = nil; nativeTransport = nil; backendReady = false; inputConnected = false; telemetryLive = false
        output = ""
        stopping = false
        status = "Preparing…"
        do {
            guard let python = interpreter ?? PythonRuntime.locate() else {
                throw NSError(domain: "G923", code: 1, userInfo: [NSLocalizedDescriptionKey: "Python 3.10 or newer is required. Install Python, then reopen the app."])
            }
            let logs = logDirectory ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("G923 Control Center/Sessions")
            try FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
            let url = logs.appendingPathComponent(UUID().uuidString + ".log")
            FileManager.default.createFile(atPath: url.path, contents: nil)
            let handle = try FileHandle(forWritingTo: url)
            let child = Process()
            child.executableURL = python
            child.arguments = ["-u"] + arguments
            child.currentDirectoryURL = directory
            child.standardInput = FileHandle.nullDevice
            child.standardOutput = handle
            child.standardError = handle
            var env = ProcessInfo.processInfo.environment
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            child.environment = env
            try child.run()
            process = child; logHandle = handle; logURL = url
            running = true
            status = "Working…"
            timer = Timer.scheduledTimer(withTimeInterval: 0.3, repeats: true) { [weak self] _ in
                MainActor.assumeIsolated { self?.refresh() }
            }
        } catch {
            status = "Launch failed"
            output = error.localizedDescription
        }
    }

    private func refresh() {
        auxiliaries.removeAll { !$0.isRunning }
        if let url = logURL, let reader = try? FileHandle(forReadingFrom: url) {
            let size = (try? reader.seekToEnd()) ?? 0
            try? reader.seek(toOffset: size > 65536 ? size - 65536 : 0)
            if let bytes = try? reader.readToEnd() { output = String(decoding: bytes, as: UTF8.self) }
            try? reader.close()
        }
        if running && !stopping {
            if let stateLine = output.components(separatedBy: "\n").last(where: { $0.hasPrefix("AUTO_STATE: ") }),
               let bytes = String(stateLine.dropFirst("AUTO_STATE: ".count)).data(using: .utf8),
               let state = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any] {
                activeAppID = state["activeAppid"] as? Int
                activeGameExe = state["activeGameExe"] as? String
                activeBottle = state["activeBottle"] as? String
                nativeTransport = state["nativeTransport"] as? String
                backendReady = activeAppID != nil && state["backendReady"] as? Bool == true
                inputConnected = activeAppID != nil && state["inputFfb"] as? String == "connected"
                telemetryLive = activeAppID != nil && state["telemetry"] as? String == "live"
            }
            if let record = output.components(separatedBy: "\n").last(where: { $0.hasPrefix("AUTO_STATUS:") || $0.hasPrefix("ETS2_STATUS:") }) {
                if record.hasPrefix("AUTO_STATUS:") {
                    status = String(record.dropFirst("AUTO_STATUS: ".count))
                } else {
                    status = record.contains("input_ffb=connected") ? "Game bridge connected" : "Waiting for game bridge"
                    status += record.contains("telemetry=live") ? " · telemetry live" : " · waiting for telemetry"
                }
            } else if output.contains("BRIDGE_LISTENING:") {
                status = "Bridge listening · start the game yourself from Steam"
            }
        }
        guard let child = process, !child.isRunning else { return }
        let code = child.terminationStatus
        status = code == 0 ? "Completed" : "Failed (\(code)) · see details below"
        running = false
        stopping = false
        activeAppID = nil; activeGameExe = nil; activeBottle = nil; nativeTransport = nil; backendReady = false; inputConnected = false; telemetryLive = false
        process = nil
        try? logHandle?.close(); logHandle = nil
        timer?.invalidate(); timer = nil
    }

    func cancel() {
        guard let child = process, child.isRunning, !stopping else { return }
        // Python handles SIGINT in its cleanup/finally blocks; never kill Steam or the game.
        stopping = true
        status = "Stopping and clearing effects…"
        child.interrupt()
    }

    func revealLog() {
        if let url = logURL { NSWorkspace.shared.activateFileViewerSelecting([url]) }
    }
}

struct ProjectSessionView: View {
    @ObservedObject var session: ProjectSession
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Diagnostics").font(.title2.bold())
            HStack {
                if session.running { ProgressView().controlSize(.small) }
                Text(session.status)
            }
            ScrollView {
                Text(session.output.isEmpty ? "No activity recorded yet." : session.output)
                    .font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(10)
            }.background(.quaternary).clipShape(RoundedRectangle(cornerRadius: 8))
            HStack {
                Button("Show log file") { session.revealLog() }
                Spacer()
                Button("Close") { session.presented = false }
            }
        }.padding(20).frame(width: 700, height: 460)
    }
}
