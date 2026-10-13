//! Bounded, analytic full-keyboard instrument. Parameters are generated at
//! initialization; the audio callback only advances fixed-size modal state.
use moonlight_physics::{modal_coefficients, rigid_string_frequency};

use crate::{PianoEvent, PianoEventKind, MAX_BLOCK_FRAMES, MAX_EVENTS_PER_BLOCK};

pub const FIRST_NOTE: u8 = 21;
pub const LAST_NOTE: u8 = 108;
pub const MAX_VOICES: usize = 32;
const KEYS: usize = (LAST_NOTE - FIRST_NOTE + 1) as usize;
const MODES: usize = 12;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BasicError {
    InvalidSampleRate,
    InvalidModel,
    EmptyOutput,
    BlockTooLarge,
    TooManyEvents,
    EventOutsideBlock,
    EventsOutOfOrder,
    UnsupportedNote,
    InvalidVelocity,
    NonFiniteOutput,
}

#[derive(Clone, Copy, Default)]
struct Mode {
    feedback_1: f64,
    feedback_2: f64,
    amplitude: f64,
    current: f64,
    previous: f64,
}

#[derive(Clone, Copy)]
struct Key {
    count: usize,
    modes: [Mode; MODES],
}

impl Default for Key {
    fn default() -> Self {
        Self {
            count: 0,
            modes: [Mode::default(); MODES],
        }
    }
}

#[derive(Clone, Copy)]
struct Voice {
    note: u8,
    active: bool,
    held: bool,
    age: u64,
    count: usize,
    modes: [Mode; MODES],
}

impl Default for Voice {
    fn default() -> Self {
        Self {
            note: 0,
            active: false,
            held: false,
            age: 0,
            count: 0,
            modes: [Mode::default(); MODES],
        }
    }
}

pub struct BasicPianoEngine {
    keys: [Key; KEYS],
    voices: [Voice; MAX_VOICES],
    next_age: u64,
    // One-pole release damping, compiled for this sample rate.
    release: f64,
}

impl BasicPianoEngine {
    pub fn new(sample_rate_hz: u32) -> Result<Self, BasicError> {
        if !(44_100..=192_000).contains(&sample_rate_hz) {
            return Err(BasicError::InvalidSampleRate);
        }
        let mut keys = [Key::default(); KEYS];
        let guarded_nyquist = sample_rate_hz as f64 * 0.49;
        for (index, key) in keys.iter_mut().enumerate() {
            let note = FIRST_NOTE as usize + index;
            let fundamental = 440.0 * 2.0_f64.powf((note as f64 - 69.0) / 12.0);
            // Explicit analytic priors, not measured or fitted piano data.
            let stiffness = 0.00006 + (index as f64 / (KEYS - 1) as f64).powi(2) * 0.0003;
            let decay = 8.0 - 5.0 * index as f64 / (KEYS - 1) as f64;
            for partial in 1..=MODES {
                let frequency = rigid_string_frequency(fundamental, partial as u32, stiffness)
                    .map_err(|_| BasicError::InvalidModel)?;
                if frequency >= guarded_nyquist {
                    break;
                }
                let coefficients = modal_coefficients(
                    frequency,
                    decay / (1.0 + partial as f64 * 0.08),
                    sample_rate_hz as f64,
                )
                .map_err(|_| BasicError::InvalidModel)?;
                key.modes[key.count] = Mode {
                    feedback_1: coefficients.feedback_1,
                    feedback_2: coefficients.feedback_2,
                    amplitude: 1.0 / (partial as f64).powf(1.4),
                    ..Mode::default()
                };
                key.count += 1;
            }
            if key.count == 0 {
                return Err(BasicError::InvalidModel);
            }
        }
        Ok(Self {
            keys,
            voices: [Voice::default(); MAX_VOICES],
            next_age: 0,
            release: 10.0_f64.powf(-3.0 / (0.25 * sample_rate_hz as f64)),
        })
    }

    pub fn process_block(
        &mut self,
        start: u64,
        events: &[PianoEvent],
        output: &mut [f32],
    ) -> Result<(), BasicError> {
        if output.is_empty() {
            return Err(BasicError::EmptyOutput);
        }
        if output.len() > MAX_BLOCK_FRAMES {
            return Err(BasicError::BlockTooLarge);
        }
        if events.len() > MAX_EVENTS_PER_BLOCK {
            output.fill(0.0);
            return Err(BasicError::TooManyEvents);
        }
        let Some(end) = start.checked_add(output.len() as u64) else {
            output.fill(0.0);
            return Err(BasicError::EventOutsideBlock);
        };
        let mut previous = None;
        for event in events {
            if event.frame < start || event.frame >= end {
                output.fill(0.0);
                return Err(BasicError::EventOutsideBlock);
            }
            if previous.is_some_and(|frame| event.frame < frame) {
                output.fill(0.0);
                return Err(BasicError::EventsOutOfOrder);
            }
            previous = Some(event.frame);
            if let PianoEventKind::NoteOn { note, velocity }
            | PianoEventKind::NoteOff {
                note,
                release_velocity: velocity,
            } = event.kind
            {
                if !(FIRST_NOTE..=LAST_NOTE).contains(&note) {
                    output.fill(0.0);
                    return Err(BasicError::UnsupportedNote);
                }
                if !velocity.is_finite() || !(0.0..=1.0).contains(&velocity) {
                    output.fill(0.0);
                    return Err(BasicError::InvalidVelocity);
                }
            }
        }
        let mut next_event = 0;
        for (offset, sample) in output.iter_mut().enumerate() {
            let frame = start + offset as u64;
            while next_event < events.len() && events[next_event].frame == frame {
                self.apply(events[next_event].kind);
                next_event += 1;
            }
            let mut sum = 0.0;
            for voice in &mut self.voices {
                if !voice.active {
                    continue;
                }
                let mut energy = 0.0;
                for mode in voice.modes.iter_mut().take(voice.count) {
                    let next = mode.feedback_1 * mode.current + mode.feedback_2 * mode.previous;
                    mode.previous = mode.current;
                    mode.current = if voice.held {
                        next
                    } else {
                        next * self.release
                    };
                    sum += mode.current;
                    energy += mode.current.abs() + mode.previous.abs();
                }
                if !voice.held && energy < 0.00001 {
                    voice.active = false;
                }
            }
            // A bounded, continuous master response prevents a 32-key chord from clipping.
            let rendered = (0.12 * sum / (1.0 + 0.2 * sum.abs())) as f32;
            if !rendered.is_finite() {
                self.reset();
                output.fill(0.0);
                return Err(BasicError::NonFiniteOutput);
            }
            *sample = rendered;
        }
        Ok(())
    }

    pub fn active_voices(&self) -> usize {
        self.voices.iter().filter(|voice| voice.active).count()
    }

    pub fn reset(&mut self) {
        self.voices = [Voice::default(); MAX_VOICES];
    }

    fn apply(&mut self, event: PianoEventKind) {
        match event {
            PianoEventKind::Reset => self.reset(),
            PianoEventKind::NoteOff { note, .. } => {
                if let Some(voice) = self
                    .voices
                    .iter_mut()
                    .find(|voice| voice.active && voice.note == note)
                {
                    voice.held = false;
                }
            }
            PianoEventKind::NoteOn { note, velocity } => {
                let index = self
                    .voices
                    .iter()
                    .position(|voice| voice.active && voice.note == note)
                    .or_else(|| self.voices.iter().position(|voice| !voice.active))
                    .unwrap_or_else(|| {
                        // Release tails go first; otherwise steal the oldest key.
                        self.voices
                            .iter()
                            .enumerate()
                            .min_by_key(|(_, voice)| (voice.held as u8, voice.age))
                            .map(|(index, _)| index)
                            .unwrap_or(0)
                    });
                let voice = &mut self.voices[index];
                if !voice.active || voice.note != note {
                    *voice = Voice {
                        note,
                        active: true,
                        held: true,
                        age: self.next_age,
                        count: self.keys[(note - FIRST_NOTE) as usize].count,
                        modes: self.keys[(note - FIRST_NOTE) as usize].modes,
                    };
                }
                self.next_age = self.next_age.wrapping_add(1);
                voice.age = self.next_age;
                voice.held = true;
                for (partial, mode) in voice.modes.iter_mut().take(voice.count).enumerate() {
                    // High partials gain proportionally more energy at greater velocity.
                    mode.current +=
                        mode.amplitude * (velocity as f64).powf(0.75 + partial as f64 * 0.12);
                }
            }
        }
    }
}
