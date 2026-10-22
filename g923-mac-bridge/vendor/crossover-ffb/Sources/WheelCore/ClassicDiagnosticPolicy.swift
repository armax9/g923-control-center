// SPDX-License-Identifier: GPL-3.0-only
// Conservative diagnostic phase: isolate game-supplied directional effects.
import Foundation
public enum ClassicDiagnosticPolicy {
 public static func directionalOnly(_ state: BridgeForceState) -> BridgeForceState {
  var copy=state;copy.effects=state.effects.filter { !$0.kind.isCondition };return copy
 }
}
