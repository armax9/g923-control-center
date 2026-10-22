// SPDX-License-Identifier: GPL-3.0-only
import Foundation
/// Atomic-file IPC. G9KF, version 1, Unix milliseconds, normalized signed force.
public enum SDKForceFrame {
    public static func encode(level: Double, milliseconds: UInt64) -> Data {
        var data = Data("G9KF".utf8)
        func append<T: FixedWidthInteger>(_ word: T) {
            var value = word.littleEndian
            withUnsafeBytes(of: &value) { data.append(contentsOf: $0) }
        }
        append(UInt32(1)); append(milliseconds)
        append((level.isFinite ? max(-1, min(1, level)) : 0).bitPattern)
        return data
    }
}
