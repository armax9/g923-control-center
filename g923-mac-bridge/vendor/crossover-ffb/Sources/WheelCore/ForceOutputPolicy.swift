import Foundation

/// Game gain and the safety ceiling have different meanings: preserve small forces,
/// clip only peaks. Invalid input always yields zero.
public enum ForceOutputPolicy {
    public static func apply(_ requested: Double, gain: Double, limit: Double) -> Double {
        guard requested.isFinite, gain.isFinite, limit.isFinite else { return 0 }
        let ceiling = max(0, min(1, limit))
        return max(-ceiling, min(ceiling, requested * max(0, gain)))
    }
}
