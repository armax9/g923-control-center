// SPDX-License-Identifier: GPL-2.0-only
// Local control of this separate audio process; no HID or game FFB writes.
use std::{fs::File, io::Read, path::PathBuf, time::{Duration, Instant}};

/// Bounded protocol record emitted by the app's validated preferences adapter.
/// Only this canonical two-field JSON is accepted; unknown fields, duplicate
/// keys, negative/nonfinite/out-of-range gains never change the current level.
pub fn parse_record(text: &str) -> Option<f32> {
    if text.len() > 128 { return None; }
    let object = text.trim().strip_prefix('{')?.strip_suffix('}')?;
    let (version, intensity) = object.split_once(',')?;
    let (version_key, version_value) = version.split_once(':')?;
    if version_key.trim() != "\"version\"" || version_value.trim() != "1" { return None; }
    let (gain_key, value) = intensity.split_once(':')?;
    if gain_key.trim() != "\"intensity\"" { return None; }
    let value=value.trim();
    // Rust float parsing also accepts a leading + and NaN; JSON numbers do not.
    if value.starts_with('+') || value.bytes().any(|c| c.is_ascii_whitespace()) { return None; }
    let gain: f32 = value.parse().ok()?;
    if gain.is_finite() && (0.0..=1.0).contains(&gain) { Some(gain) } else { None }
}

pub struct LiveGain {
    path: Option<PathBuf>,
    checked: Option<Instant>,
    current: f32,
    target: f32,
}

impl LiveGain {
    pub fn new(path: Option<PathBuf>, initial: f32) -> Self {
        Self { path, checked: None, current: initial, target: initial }
    }
    pub fn poll(&mut self, now: Instant) -> Option<f32> {
        let path = self.path.as_ref()?;
        if self.checked.map(|last| now.saturating_duration_since(last) < Duration::from_millis(50)).unwrap_or(false) {
            return None;
        }
        self.checked = Some(now);
        let mut text = String::new();
        // Read at most one tiny record. Missing/invalid files retain the last
        // validated gain instead of falling back to a larger default.
        File::open(path).ok()?.take(129).read_to_string(&mut text).ok()?;
        let gain = parse_record(&text)?;
        if gain == self.target { return None; }
        self.target = gain;
        Some(gain)
    }
    /// At most twenty milliseconds of gain interpolation avoids a step/click while
    /// preserving engine phase and the continuous independent FFB channel.
    pub fn next(&mut self, seconds: f32) -> f32 {
        let weight = (seconds / 0.020).clamp(0.0, 1.0);
        self.current += (self.target-self.current).clamp(-weight,weight);
        if (self.current-self.target).abs() < 0.00001 { self.current=self.target; }
        self.current
    }
}

#[cfg(test)] mod tests {
    use super::*;
    #[test] fn record_requires_known_finite_normalized_gain() {
        assert_eq!(parse_record("{\"version\":1,\"intensity\":0.1}\n"),Some(0.1));
        assert_eq!(parse_record("{ \"version\": 1, \"intensity\": 0 }"),Some(0.0));
        for record in ["", "{}", "{\"version\":2,\"intensity\":1}", "{\"version\":1,\"intensity\":NaN}",
            "{\"version\":1,\"intensity\":inf}", "{\"version\":1,\"intensity\":-0.1}",
            "{\"version\":1,\"intensity\":1.1}", "{\"version\":1,\"intensity\":0.1,\"intensity\":1}",
            "{\"version\":1,\"intensity\":true}", "{\"version\":1,\"intensity\":0 .1}",
            "{\"version\":1,\"intensity\":+0.1}"] { assert_eq!(parse_record(record),None,"{record}"); }
        assert_eq!(parse_record(&" ".repeat(129)),None);
    }
    #[test] fn gain_changes_keep_state_and_converge_to_zero() {
        let mut gain=LiveGain::new(None,0.1);
        gain.target=0.4;
        assert!(gain.next(0.002)>0.1);
        for _ in 0..100 { gain.next(0.002); }
        assert_eq!(gain.current,0.4);
        gain.target=0.0;
        for _ in 0..100 { gain.next(0.002); }
        assert_eq!(gain.current,0.0);
    }
    #[test] fn missing_control_file_keeps_existing_gain() {
        let mut gain=LiveGain::new(Some(PathBuf::from("/nonexistent-g923-control-fixture")),0.1);
        assert_eq!(gain.poll(Instant::now()),None);
        assert_eq!(gain.next(0.002),0.1);
    }
}
