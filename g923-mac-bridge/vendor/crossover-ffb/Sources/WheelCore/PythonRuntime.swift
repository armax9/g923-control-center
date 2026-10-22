import Foundation

/// Resolves a local Python installation at launch; bundles never store a builder's path.
public enum PythonRuntime {
    public static let minimumVersion = (3, 10)
    public static func candidates(environment: [String: String] = ProcessInfo.processInfo.environment) -> [URL] {
        var paths: [String] = []
        if let selected = environment["G923_PYTHON"], selected.hasPrefix("/") { paths.append(selected) }
        paths += ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
        paths += (environment["PATH"] ?? "").split(separator: ":").filter { $0.hasPrefix("/") }.map { String($0) + "/python3" }
        var seen = Set<String>()
        return paths.map { URL(fileURLWithPath: $0).resolvingSymlinksInPath() }.filter { seen.insert($0.path).inserted }
    }
    public static func locate() -> URL? {
        for url in candidates() where FileManager.default.isExecutableFile(atPath: url.path) {
            let child = Process(), output = Pipe()
            child.executableURL = url
            child.arguments = ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"]
            child.standardOutput = output; child.standardError = FileHandle.nullDevice
            child.standardInput = FileHandle.nullDevice
            do { try child.run(); child.waitUntilExit(); if child.terminationStatus == 0 { return url } } catch { continue }
        }
        return nil
    }
}
