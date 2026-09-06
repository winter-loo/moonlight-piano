//! Deterministic block renderer shared by offline, WebAssembly, FFI, and native hosts.

use std::error::Error;
use std::fmt::{Display, Formatter};

use moonlight_model::{ModelError, ModelPack, MAX_MODES};
use moonlight_physics::modal_coefficients;

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum PianoEventKind {
    NoteOn { note: u8, velocity: f32 },
    NoteOff { note: u8, release_velocity: f32 },
    Reset,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PianoEvent {
    pub frame: u64,
    pub kind: PianoEventKind,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BlockReport {
    pub start_frame: u64,
    pub rendered_frames: usize,
    pub applied_events: usize,
    pub key_down: bool,
}

#[derive(Debug)]
pub enum ProcessError {
    InvalidModel(ModelError),
    EmptyOutput,
    EventOutsideBlock { frame: u64, start: u64, end: u64 },
    EventsOutOfOrder,
    UnsupportedNote(u8),
    InvalidVelocity,
    NonFiniteOutput,
}

impl Display for ProcessError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{self:?}")
    }
}

impl Error for ProcessError {}

#[derive(Debug, Clone, Copy, Default)]
struct ModeState {
    feedback_1: f64,
    feedback_2: f64,
    amplitude: f64,
    current: f64,
    previous: f64,
}

impl ModeState {
    fn tick(&mut self, impulse: f64) -> f64 {
        let next = self.feedback_1 * self.current + self.feedback_2 * self.previous + impulse;
        self.previous = self.current;
        self.current = next;
        next
    }

    fn reset(&mut self) {
        self.current = 0.0;
        self.previous = 0.0;
    }
}

pub struct PianoEngine {
    note: u8,
    output_gain: f64,
    mode_count: usize,
    modes: [ModeState; MAX_MODES],
    key_down: bool,
    pending_impulse: f64,
    rng_state: u64,
}

impl PianoEngine {
    pub fn new(pack: &ModelPack, sample_rate_hz: u32, seed: u64) -> Result<Self, ProcessError> {
        pack.validate(sample_rate_hz).map_err(ProcessError::InvalidModel)?;
        let mut modes = [ModeState::default(); MAX_MODES];
        for (index, spec) in pack.modes[..pack.mode_count].iter().enumerate() {
            let coefficients = modal_coefficients(
                spec.frequency_hz,
                spec.t60_seconds,
                sample_rate_hz as f64,
            )
            .map_err(|_| ProcessError::InvalidModel(ModelError::InvalidMode {
                index,
                reason: "could not derive stable coefficients",
            }))?;
            modes[index] = ModeState {
                feedback_1: coefficients.feedback_1,
                feedback_2: coefficients.feedback_2,
                amplitude: spec.amplitude,
                current: 0.0,
                previous: 0.0,
            };
        }
        Ok(Self {
            note: pack.note,
            output_gain: pack.output_gain,
            mode_count: pack.mode_count,
            modes,
            key_down: false,
            pending_impulse: 0.0,
            rng_state: seed.max(1),
        })
    }

    pub fn process_block(
        &mut self,
        block_start_frame: u64,
        events: &[PianoEvent],
        output: &mut [f32],
    ) -> Result<BlockReport, ProcessError> {
        if output.is_empty() {
            return Err(ProcessError::EmptyOutput);
        }
        let block_end_frame = block_start_frame
            .checked_add(output.len() as u64)
            .ok_or(ProcessError::EventOutsideBlock {
                frame: u64::MAX,
                start: block_start_frame,
                end: u64::MAX,
            })?;
        let mut previous_frame = None;
        for event in events {
            if event.frame < block_start_frame || event.frame >= block_end_frame {
                return Err(ProcessError::EventOutsideBlock {
                    frame: event.frame,
                    start: block_start_frame,
                    end: block_end_frame,
                });
            }
            if previous_frame.is_some_and(|previous| event.frame < previous) {
                return Err(ProcessError::EventsOutOfOrder);
            }
            previous_frame = Some(event.frame);
            self.validate_event(*event)?;
        }

        let mut event_index = 0;
        for (offset, sample) in output.iter_mut().enumerate() {
            let frame = block_start_frame + offset as u64;
            while event_index < events.len() && events[event_index].frame == frame {
                self.apply_event(events[event_index]);
                event_index += 1;
            }
            let impulse = self.pending_impulse;
            self.pending_impulse = 0.0;
            let mut sum = 0.0;
            for mode in &mut self.modes[..self.mode_count] {
                sum += mode.tick(impulse * mode.amplitude);
            }
            let rendered = sum * self.output_gain;
            if !rendered.is_finite() {
                return Err(ProcessError::NonFiniteOutput);
            }
            *sample = rendered as f32;
        }

        Ok(BlockReport {
            start_frame: block_start_frame,
            rendered_frames: output.len(),
            applied_events: events.len(),
            key_down: self.key_down,
        })
    }

    pub fn reset(&mut self) {
        for mode in &mut self.modes[..self.mode_count] {
            mode.reset();
        }
        self.key_down = false;
        self.pending_impulse = 0.0;
    }

    pub fn key_down(&self) -> bool {
        self.key_down
    }

    fn validate_event(&self, event: PianoEvent) -> Result<(), ProcessError> {
        match event.kind {
            PianoEventKind::NoteOn { note, velocity } => {
                if note != self.note {
                    return Err(ProcessError::UnsupportedNote(note));
                }
                if !velocity.is_finite() || !(0.0..=1.0).contains(&velocity) {
                    return Err(ProcessError::InvalidVelocity);
                }
            }
            PianoEventKind::NoteOff {
                note,
                release_velocity,
            } => {
                if note != self.note {
                    return Err(ProcessError::UnsupportedNote(note));
                }
                if !release_velocity.is_finite()
                    || !(0.0..=1.0).contains(&release_velocity)
                {
                    return Err(ProcessError::InvalidVelocity);
                }
            }
            PianoEventKind::Reset => {}
        }
        Ok(())
    }

    fn apply_event(&mut self, event: PianoEvent) {
        match event.kind {
            PianoEventKind::NoteOn { velocity, .. } => {
                self.key_down = true;
                let micro_variation = 0.995 + self.next_unit_f64() * 0.01;
                self.pending_impulse += velocity as f64 * micro_variation;
            }
            PianoEventKind::NoteOff { .. } => {
                // Ticket #4 deliberately leaves damper contact to ticket #8. The
                // passive string state continues to decay after the key is released.
                self.key_down = false;
            }
            PianoEventKind::Reset => self.reset(),
        }
    }

    fn next_unit_f64(&mut self) -> f64 {
        let mut value = self.rng_state;
        value ^= value << 13;
        value ^= value >> 7;
        value ^= value << 17;
        self.rng_state = value;
        (value as f64) / (u64::MAX as f64)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use moonlight_model::parse_model_pack;

    const MODEL: &str = r#"MOONLIGHT_MODEL_V1
schema_version=1
instrument_id=test-c4
note=60
output_gain=0.1
mode=261.625565,6.5,1.0
mode=523.334500,5.2,0.42
"#;

    fn engine(seed: u64) -> PianoEngine {
        let pack = parse_model_pack(MODEL, 48_000).unwrap();
        PianoEngine::new(&pack, 48_000, seed).unwrap()
    }

    #[test]
    fn identical_history_and_seed_are_reproducible() {
        let event = PianoEvent {
            frame: 0,
            kind: PianoEventKind::NoteOn {
                note: 60,
                velocity: 0.8,
            },
        };
        let mut left = engine(42);
        let mut right = engine(42);
        let mut left_output = [0.0; 256];
        let mut right_output = [0.0; 256];
        left.process_block(0, &[event], &mut left_output).unwrap();
        right
            .process_block(0, &[event], &mut right_output)
            .unwrap();
        assert_eq!(left_output, right_output);
        assert!(left_output.iter().any(|sample| *sample != 0.0));
    }

    #[test]
    fn state_persists_across_blocks() {
        let event = PianoEvent {
            frame: 0,
            kind: PianoEventKind::NoteOn {
                note: 60,
                velocity: 0.8,
            },
        };
        let mut engine = engine(7);
        let mut first = [0.0; 128];
        let mut second = [0.0; 128];
        engine.process_block(0, &[event], &mut first).unwrap();
        engine.process_block(128, &[], &mut second).unwrap();
        assert!(second.iter().any(|sample| *sample != 0.0));
    }

    #[test]
    fn rejects_events_outside_the_current_block() {
        let mut engine = engine(1);
        let mut output = [0.0; 128];
        let event = PianoEvent {
            frame: 128,
            kind: PianoEventKind::NoteOn {
                note: 60,
                velocity: 0.8,
            },
        };
        assert!(matches!(
            engine.process_block(0, &[event], &mut output),
            Err(ProcessError::EventOutsideBlock { .. })
        ));
    }

    #[test]
    fn rejects_non_finite_velocity() {
        let mut engine = engine(1);
        let mut output = [0.0; 128];
        let event = PianoEvent {
            frame: 0,
            kind: PianoEventKind::NoteOn {
                note: 60,
                velocity: f32::NAN,
            },
        };
        assert!(matches!(
            engine.process_block(0, &[event], &mut output),
            Err(ProcessError::InvalidVelocity)
        ));
    }
}
