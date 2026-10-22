// SPDX-License-Identifier: GPL-3.0-only
/// Classic Logitech slot 0 lifecycle. Wire facts from new-lg4ff/dd-lg4ff:
/// opcode 1 installs/plays a slot, opcode 0xC changes an installed slot.
/// Independent implementation; no GPL-2 source is incorporated.
public struct ClassicForceStream {
    private var installed = false
    public init() {}
    public mutating func reset() { installed = false }
    public mutating func packet(_ level: Double, length: Int = 7) -> [UInt8] {
        let safe = level.isFinite ? max(-1, min(1, level)) : 0
        let force = UInt8(max(0, min(255, (128 + safe * 127).rounded())))
        let opcode: UInt8 = installed ? 0x1c : 0x11
        installed = true
        return [opcode, 0, force, 0, 0, 0, 0] + Array(repeating: 0, count: max(0, length - 7))
    }
}
