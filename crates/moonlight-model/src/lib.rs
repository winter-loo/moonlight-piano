//! Validated, sample-free instrument model data shared by every host.

use std::error::Error;
use std::fmt::{Display, Formatter};

use moonlight_physics::modal_coefficients;

pub const MODEL_MAGIC: &str = "MOONLIGHT_MODEL_V1";
pub const MODEL_SCHEMA_VERSION: u32 = 1;
pub const MAX_MODES: usize = 16;
pub const NYQUIST_GUARD_RATIO: f64 = 0.98;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ModeSpec {
    pub frequency_hz: f64,
    pub t60_seconds: f64,
    pub amplitude: f64,
}

impl Default for ModeSpec {
    fn default() -> Self {
        Self {
            frequency_hz: 0.0,
            t60_seconds: 0.0,
            amplitude: 0.0,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct ModelPack {
    pub schema_version: u32,
    pub instrument_id: String,
    pub note: u8,
    pub output_gain: f64,
    pub mode_count: usize,
    pub modes: [ModeSpec; MAX_MODES],
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ModelError {
    MissingMagic,
    DuplicateField(String),
    MissingField(&'static str),
    UnknownField(String),
    InvalidInteger(String),
    InvalidFloat(String),
    InvalidSchemaVersion(u32),
    InvalidInstrumentId,
    InvalidNote,
    InvalidOutputGain,
    InvalidModeCount,
    InvalidMode { index: usize, reason: &'static str },
}

impl Display for ModelError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{self:?}")
    }
}

impl Error for ModelError {}

impl ModelPack {
    pub fn validate(&self, sample_rate_hz: u32) -> Result<(), ModelError> {
        if self.schema_version != MODEL_SCHEMA_VERSION {
            return Err(ModelError::InvalidSchemaVersion(self.schema_version));
        }
        if self.instrument_id.is_empty()
            || !self
                .instrument_id
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
        {
            return Err(ModelError::InvalidInstrumentId);
        }
        if self.note > 127 {
            return Err(ModelError::InvalidNote);
        }
        if !self.output_gain.is_finite() || !(0.0 < self.output_gain && self.output_gain <= 1.0) {
            return Err(ModelError::InvalidOutputGain);
        }
        if self.mode_count == 0 || self.mode_count > MAX_MODES {
            return Err(ModelError::InvalidModeCount);
        }
        if sample_rate_hz < 8_000 {
            return Err(ModelError::InvalidMode {
                index: 0,
                reason: "sample rate below supported range",
            });
        }

        let guarded_nyquist = sample_rate_hz as f64 * 0.5 * NYQUIST_GUARD_RATIO;
        let mut has_energy = false;
        for (index, mode) in self.modes[..self.mode_count].iter().enumerate() {
            if !mode.frequency_hz.is_finite()
                || !mode.t60_seconds.is_finite()
                || !mode.amplitude.is_finite()
            {
                return Err(ModelError::InvalidMode {
                    index,
                    reason: "non-finite value",
                });
            }
            if mode.frequency_hz <= 0.0 || mode.frequency_hz >= guarded_nyquist {
                return Err(ModelError::InvalidMode {
                    index,
                    reason: "frequency outside guarded realtime bandwidth",
                });
            }
            if mode.t60_seconds <= 0.0 || mode.t60_seconds > 120.0 {
                return Err(ModelError::InvalidMode {
                    index,
                    reason: "invalid decay",
                });
            }
            if mode.amplitude < 0.0 || mode.amplitude > 4.0 {
                return Err(ModelError::InvalidMode {
                    index,
                    reason: "invalid amplitude",
                });
            }
            has_energy |= mode.amplitude > 0.0;
            let coefficients = modal_coefficients(
                mode.frequency_hz,
                mode.t60_seconds,
                sample_rate_hz as f64,
            )
            .map_err(|_| ModelError::InvalidMode {
                index,
                reason: "unstable or invalid pole",
            })?;
            if !(0.0..1.0).contains(&coefficients.pole_radius) {
                return Err(ModelError::InvalidMode {
                    index,
                    reason: "unstable pole",
                });
            }
        }
        if !has_energy {
            return Err(ModelError::InvalidMode {
                index: 0,
                reason: "all modes have zero amplitude",
            });
        }
        Ok(())
    }
}

pub fn parse_model_pack(input: &str, sample_rate_hz: u32) -> Result<ModelPack, ModelError> {
    let mut lines = input.lines().enumerate().filter_map(|(index, raw)| {
        let line = raw.trim();
        (!line.is_empty() && !line.starts_with('#')).then_some((index + 1, line))
    });
    let Some((_line_number, magic)) = lines.next() else {
        return Err(ModelError::MissingMagic);
    };
    if magic != MODEL_MAGIC {
        return Err(ModelError::MissingMagic);
    }

    let mut schema_version = None;
    let mut instrument_id = None;
    let mut note = None;
    let mut output_gain = None;
    let mut modes = [ModeSpec::default(); MAX_MODES];
    let mut mode_count = 0;

    for (line_number, line) in lines {
        let Some((key, value)) = line.split_once('=') else {
            return Err(ModelError::UnknownField(format!("line {line_number}: {line}")));
        };
        let key = key.trim();
        let value = value.trim();
        match key {
            "schema_version" => set_once(
                &mut schema_version,
                value
                    .parse::<u32>()
                    .map_err(|_| ModelError::InvalidInteger(value.to_owned()))?,
                key,
            )?,
            "instrument_id" => set_once(&mut instrument_id, value.to_owned(), key)?,
            "note" => set_once(
                &mut note,
                value
                    .parse::<u8>()
                    .map_err(|_| ModelError::InvalidInteger(value.to_owned()))?,
                key,
            )?,
            "output_gain" => set_once(&mut output_gain, parse_f64(value)?, key)?,
            "mode" => {
                if mode_count == MAX_MODES {
                    return Err(ModelError::InvalidModeCount);
                }
                let values: Vec<&str> = value.split(',').map(str::trim).collect();
                if values.len() != 3 {
                    return Err(ModelError::InvalidMode {
                        index: mode_count,
                        reason: "mode needs frequency,t60,amplitude",
                    });
                }
                modes[mode_count] = ModeSpec {
                    frequency_hz: parse_f64(values[0])?,
                    t60_seconds: parse_f64(values[1])?,
                    amplitude: parse_f64(values[2])?,
                };
                mode_count += 1;
            }
            _ => return Err(ModelError::UnknownField(key.to_owned())),
        }
    }

    let pack = ModelPack {
        schema_version: schema_version.ok_or(ModelError::MissingField("schema_version"))?,
        instrument_id: instrument_id.ok_or(ModelError::MissingField("instrument_id"))?,
        note: note.ok_or(ModelError::MissingField("note"))?,
        output_gain: output_gain.ok_or(ModelError::MissingField("output_gain"))?,
        mode_count,
        modes,
    };
    pack.validate(sample_rate_hz)?;
    Ok(pack)
}

fn parse_f64(value: &str) -> Result<f64, ModelError> {
    value
        .parse::<f64>()
        .map_err(|_| ModelError::InvalidFloat(value.to_owned()))
}

fn set_once<T>(slot: &mut Option<T>, value: T, key: &str) -> Result<(), ModelError> {
    if slot.replace(value).is_some() {
        return Err(ModelError::DuplicateField(key.to_owned()));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const VALID: &str = r#"MOONLIGHT_MODEL_V1
schema_version=1
instrument_id=moonlight-minimal-c4
note=60
output_gain=0.12
mode=261.625565,6.5,1.0
mode=523.334500,5.2,0.42
"#;

    #[test]
    fn parses_and_validates_a_sample_free_pack() {
        let pack = parse_model_pack(VALID, 48_000).unwrap();
        assert_eq!(pack.note, 60);
        assert_eq!(pack.mode_count, 2);
    }

    #[test]
    fn rejects_non_finite_model_values() {
        let input = VALID.replace("261.625565", "NaN");
        assert!(matches!(
            parse_model_pack(&input, 48_000),
            Err(ModelError::InvalidMode {
                reason: "non-finite value",
                ..
            })
        ));
    }

    #[test]
    fn rejects_a_silent_output_gain() {
        let input = VALID.replace("output_gain=0.12", "output_gain=0");
        assert!(matches!(
            parse_model_pack(&input, 48_000),
            Err(ModelError::InvalidOutputGain)
        ));
    }

    #[test]
    fn rejects_unstable_decay() {
        let input = VALID.replace("6.5", "-1");
        assert!(matches!(
            parse_model_pack(&input, 48_000),
            Err(ModelError::InvalidMode {
                reason: "invalid decay",
                ..
            })
        ));
    }

    #[test]
    fn rejects_modes_above_the_guarded_nyquist_limit() {
        let input = VALID.replace("523.334500", "23999");
        assert!(matches!(
            parse_model_pack(&input, 48_000),
            Err(ModelError::InvalidMode {
                reason: "frequency outside guarded realtime bandwidth",
                ..
            })
        ));
    }

    #[test]
    fn rejects_malformed_and_unknown_fields() {
        assert!(matches!(
            parse_model_pack("not-a-pack", 48_000),
            Err(ModelError::MissingMagic)
        ));
        let input = format!("{VALID}sample=/tmp/C4.wav\n");
        assert!(matches!(
            parse_model_pack(&input, 48_000),
            Err(ModelError::UnknownField(field)) if field == "sample"
        ));
    }
}
