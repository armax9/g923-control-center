// SPDX-License-Identifier: GPL-3.0-only
// Adapted from teosemi/CrossFFB, commit 5ea4eac1e41fc743191e9e007c59abe2ea4f28d6.
// Copyright (c) 2026 Matteo Seminara and Maurizio Seminara.
// Original MIT permission/disclaimer: vendor/CrossFFB-reference/LICENSE.
import Foundation
/// Explicit classic-only candidate. Caller supplies already evaluated/signed force.
/// Does not copy CrossFFB's simplified effect semantics or replace input bindings.
public enum CrossFFBClassicProfile {
    public static let initializationDelayMicroseconds: UInt32 = 100_000
    public static func initialization(range: Int, length: Int = 16) -> [[UInt8]] {
        [LogitechWheelCommand.stopAll(length: length),
         LogitechWheelCommand.autocenterOff(length: length),
         LogitechWheelCommand.range(range, length: length),
         pad([0x0d, 0x01, 0, 0, 0, 0, 0], length)]
    }
    public static func forceByte(_ normalized: Double) -> UInt8 {
        let value = normalized.isFinite ? max(-1, min(1, normalized)) : 0
        return UInt8(max(0, min(255, 128 + Int(value * 127))))
    }
    public static func constant(_ normalized: Double, length: Int = 16) -> [UInt8] {
        pad([0x11, 0, forceByte(normalized), 0x80, 0x80, 0x80, 0], length)
    }
    private static func pad(_ bytes: [UInt8], _ length: Int) -> [UInt8] {
        bytes + Array(repeating: 0, count: max(0, length - bytes.count))
    }
}
