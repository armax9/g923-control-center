import Foundation

/// Capability is independent of installation and hardware acceptance.
public enum GameSupport: String, Sendable {
    case nativeSDK, mesconSCS, telemetryCandidate, classic
    public static func forGame(_ game: GameEntry) -> Self {
        if NativeTrueForceGame.matching(game) != nil { return .nativeSDK }
        if let mescon = MesconTelemetryGame.matching(game) {
            return [227300, 270880].contains(mescon.steamAppID) ? .mesconSCS : .telemetryCandidate
        }
        return .classic
    }

    public var title: String {
        switch self {
        case .nativeSDK: return "Native TRUEFORCE · SDK"
        case .mesconSCS: return "TRUEFORCE · mescon telemetry (emulated)"
        case .telemetryCandidate: return "TRUEFORCE · mescon telemetry (emulated)"
        case .classic: return "DirectInput FFB · experimental"
        }
    }
    public var detail: String {
        switch self {
        case .nativeSDK: return "Original Logitech SDK. DiRT Rally 2.0 accepted on this Mac; other games require an individual SDK installation and test."
        case .mesconSCS: return "Engine effects synthesized from SCS telemetry by the port of the mescon Linux project. Emulated effects, not native game TRUEFORCE. Experimental."
        case .telemetryCandidate: return "Effects synthesized from game telemetry by the port of the mescon Linux project. Emulated effects, not native game TRUEFORCE. Experimental; gameplay untested."
        case .classic: return "Wheel input and classic FFB bridge. Telemetry effects require a game adapter."
        }
    }
}
