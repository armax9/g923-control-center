import Foundation
@main struct SessionTest {
    @MainActor static func main() throws {
        let root = URL(fileURLWithPath: "/tmp/g923-session-fixture-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        func wait(_ predicate: () -> Bool) {
            let deadline = Date().addingTimeInterval(8)
            while !predicate() && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.05)) }
            precondition(predicate(), "Process did not reach expected state")
        }
        let session = ProjectSession(interpreter: URL(fileURLWithPath: "/usr/bin/python3"), logDirectory: root)
        session.start(title: "fixture", arguments: ["-c", "import time\nprint('ready',flush=True)\ntry: time.sleep(60)\nexcept KeyboardInterrupt: print('cleanup',flush=True)"], directory: root)
        wait { session.output.contains("ready") }
        precondition(!session.presented, "Starting a session must not open diagnostics")
        session.start(title: "duplicate", arguments: ["-c", "raise Exception('duplicate')"], directory: root)
        precondition(session.title == "fixture")
        session.start(title: "helper", arguments: ["-c", "print('helper-ready',flush=True)"], directory: root, alongside: true)
        wait { session.output.contains("helper-ready") }
        session.cancel()
        wait { !session.running }
        precondition(session.output.contains("cleanup"))
        precondition(session.status == "Completed")
        precondition(!session.stopping, "A stopped bridge must be restartable")
        let state = "AUTO_STATE: {\"activeAppid\":227300,\"backendReady\":true,\"inputFfb\":\"connected\",\"telemetry\":\"live\"}"
        session.start(title: "state fixture", arguments: ["-c", "import time\nprint('" + state + "',flush=True)\ntry: time.sleep(60)\nexcept KeyboardInterrupt: pass"], directory: root)
        wait { session.inputConnected }
        precondition(session.activeAppID == 227300 && session.backendReady && session.telemetryLive)
        precondition(!session.bridgeArmed, "An arbitrary diagnostic must not arm the bridge toggle")
        session.cancel()
        wait { !session.running }
        precondition(session.activeAppID == nil && !session.backendReady && !session.inputConnected && !session.telemetryLive)
        let nativeState = "AUTO_STATE: {\"activeAppid\":690790,\"backendReady\":true,\"inputFfb\":\"unknown\",\"nativeTransport\":\"restart_required\"}"
        session.start(title: "native state fixture", arguments: ["-c", "import time\nprint('" + nativeState + "',flush=True)\ntry: time.sleep(60)\nexcept KeyboardInterrupt: pass"], directory: root)
        wait { session.nativeTransport == "restart_required" }
        precondition(session.backendReady && !session.inputConnected, "An input publisher cannot establish TRUEFORCE readiness")
        precondition(!session.presented, "Transport status must not open diagnostics")
        session.cancel()
        wait { !session.running }
        precondition(session.nativeTransport == nil)
        session.start(title: "failure", arguments: ["-c", "raise RuntimeError('fixture-error')"], directory: root)
        wait { !session.running }
        precondition(session.output.contains("fixture-error"))
        precondition(session.status.contains("Failed"))
        print("PASS: live Unicode logs, duplicate guard, cancellation/cleanup, error reporting. No HID/game.")
    }
}
