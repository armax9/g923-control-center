// SPDX-License-Identifier: GPL-2.0-only
// Extracted from upstream relay.rs, pinned in UPSTREAM.json.
pub const ID:&str="relay";
pub const DEFAULT_PORT:u16=20780;
pub const PACKET_LEN_FULL:usize=40;
pub const MAGIC:[u8;4]=*b"LTFR";
pub const VERSION:u8=2;
pub const FLAG_AIRBORNE:u8=1;
pub const GAME_ID_LEN:usize=8;
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RelayTelemetry {
    /// Which title produced this sample, one of [`GAME_IDS`]. Decides which
    /// `game.<id>.*` settings gate it.
    pub game_id: &'static str,
    /// Engine speed in revolutions per minute.
    pub rpm: f32,
    /// Engine redline in revolutions per minute.
    pub max_rpm: f32,
    /// Throttle position, 0.0 to 1.0.
    pub throttle: f32,
    /// Selected gear: -1 reverse, 0 neutral, 1..=N forward.
    pub gear: i16,
    /// Car speed in metres per second, 0.0 when the source has none.
    pub speed: f32,
    /// Brake pedal, 0.0 to 1.0, 0.0 when the source has none.
    pub brake: f32,
    /// All four wheels off the ground, when the source can tell. Senders
    /// that cannot leave this false, which is what a listener assumes of
    /// any sender predating the flag.
    pub airborne: bool,
}

pub fn encode(t: &RelayTelemetry) -> [u8; PACKET_LEN_FULL] {
    let mut buf = [0u8; PACKET_LEN_FULL];
    buf[0..4].copy_from_slice(&MAGIC);
    buf[4] = VERSION;
    buf[5] = if t.airborne { FLAG_AIRBORNE } else { 0 };
    // NUL-padded, never NUL-terminated-and-truncated: an id longer than the
    // field would silently become a different id, so ids are kept short and
    // the excess is dropped rather than encoded wrong.
    let id = t.game_id.as_bytes();
    let n = id.len().min(GAME_ID_LEN);
    buf[6..6 + n].copy_from_slice(&id[..n]);
    buf[14..18].copy_from_slice(&t.rpm.to_le_bytes());
    buf[18..22].copy_from_slice(&t.max_rpm.to_le_bytes());
    buf[22..26].copy_from_slice(&t.throttle.to_le_bytes());
    buf[26..28].copy_from_slice(&t.gear.to_le_bytes());
    // 28..32: first_led, which no relay source knows; 0.0 is "unknown".
    buf[32..36].copy_from_slice(&t.speed.to_le_bytes());
    buf[36..40].copy_from_slice(&t.brake.to_le_bytes());
    buf
}
pub const GAME_IDS:&[&str]=&["ets2","ats","iracing","raceroom","assetto","acc","ac-evo","lmu","rf2",ID];
