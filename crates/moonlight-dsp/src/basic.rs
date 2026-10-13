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
    ChannelLengthMismatch,
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
    key_down: bool,
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
            key_down: false,
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
    sustain: bool,
    body: [Mode; 2],
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
        let mut body = [Mode::default(); 2];
        for (mode, frequency) in body.iter_mut().zip([110.0, 220.0]) {
            let coefficients = modal_coefficients(frequency, 0.55, sample_rate_hz as f64)
                .map_err(|_| BasicError::InvalidModel)?;
            *mode = Mode {
                feedback_1: coefficients.feedback_1,
                feedback_2: coefficients.feedback_2,
                amplitude: 0.000001,
                ..Mode::default()
            };
        }
        Ok(Self {
            keys,
            voices: [Voice::default(); MAX_VOICES],
            next_age: 0,
            sustain: false,
            body,
            release: 10.0_f64.powf(-3.0 / (0.25 * sample_rate_hz as f64)),
        })
    }

    pub fn process_block(
        &mut self,
        start: u64,
        events: &[PianoEvent],
        output: &mut [f32],
    ) -> Result<(), BasicError> {
        self.process_channels(start, events, output, None)
    }

    pub fn process_stereo_block(
        &mut self,
        start: u64,
        events: &[PianoEvent],
        left: &mut [f32],
        right: &mut [f32],
    ) -> Result<(), BasicError> {
        if left.len() != right.len() {
            return Err(BasicError::ChannelLengthMismatch);
        }
        self.process_channels(start, events, left, Some(right))
    }

    fn process_channels(
        &mut self,
        start: u64,
        events: &[PianoEvent],
        output: &mut [f32],
        mut right: Option<&mut [f32]>,
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
            if let PianoEventKind::Sustain { position } = event.kind {
                if !position.is_finite() || !(0.0..=1.0).contains(&position) {
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
            let mut left_sum = 0.0;
            let mut right_sum = 0.0;
            for voice in &mut self.voices {
                if !voice.active {
                    continue;
                }
                let mut energy = 0.0;
                let mut voice_sum = 0.0;
                for mode in voice.modes.iter_mut().take(voice.count) {
                    let next = mode.feedback_1 * mode.current + mode.feedback_2 * mode.previous;
                    mode.previous = mode.current;
                    mode.current = if voice.held {
                        next
                    } else {
                        next * self.release
                    };
                    voice_sum += mode.current;
                    energy += mode.current.abs() + mode.previous.abs();
                }
                if !voice.held && energy < 0.00001 {
                    voice.active = false;
                }
                let pan = f64::from(voice.note - FIRST_NOTE) / (KEYS - 1) as f64;
                left_sum += voice_sum * (1.0 - 0.35 * pan);
                right_sum += voice_sum * (0.65 + 0.35 * pan);
            }
            // Small, persistent shared modal response, fed by every key. This is
            // a simplified body coloration, not a bidirectional soundboard model.
            let body_input = (left_sum + right_sum) * 0.5;
            for mode in &mut self.body {
                let next = mode.feedback_1 * mode.current
                    + mode.feedback_2 * mode.previous
                    + mode.amplitude * body_input;
                mode.previous = mode.current;
                mode.current = next;
            }
            left_sum += 0.08 * self.body[0].current + 0.03 * self.body[1].current;
            right_sum += 0.03 * self.body[0].current + 0.08 * self.body[1].current;
            // A bounded, continuous master response prevents a 32-key chord from clipping.
            let left_rendered = (0.12 * left_sum / (1.0 + 0.2 * left_sum.abs())) as f32;
            let right_rendered = (0.12 * right_sum / (1.0 + 0.2 * right_sum.abs())) as f32;
            if !left_rendered.is_finite() || !right_rendered.is_finite() {
                self.reset();
                output.fill(0.0);
                if let Some(channel) = right.as_deref_mut() {
                    channel.fill(0.0);
                }
                return Err(BasicError::NonFiniteOutput);
            }
            *sample = if right.is_some() {
                left_rendered
            } else {
                (left_rendered + right_rendered) * 0.5
            };
            if let Some(channel) = right.as_deref_mut() {
                channel[offset] = right_rendered;
            }
        }
        Ok(())
    }

    pub fn active_voices(&self) -> usize {
        self.voices.iter().filter(|voice| voice.active).count()
    }

    pub fn reset(&mut self) {
        self.voices = [Voice::default(); MAX_VOICES];
        self.sustain = false;
        for mode in &mut self.body {
            mode.current = 0.0;
            mode.previous = 0.0;
        }
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
                    voice.key_down = false;
                    voice.held = self.sustain;
                }
            }
            PianoEventKind::Sustain { position } => {
                self.sustain = position >= 0.5;
                for voice in &mut self.voices {
                    if voice.active {
                        voice.held = voice.key_down || self.sustain;
                    }
                }
            }
            PianoEventKind::NoteOn { note, velocity } => {
                if velocity == 0.0 {
                    if let Some(voice) = self
                        .voices
                        .iter_mut()
                        .find(|voice| voice.active && voice.note == note)
                    {
                        voice.key_down = false;
                        voice.held = self.sustain;
                    }
                    return;
                }
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
                        key_down: true,
                        age: self.next_age,
                        count: self.keys[(note - FIRST_NOTE) as usize].count,
                        modes: self.keys[(note - FIRST_NOTE) as usize].modes,
                    };
                }
                self.next_age = self.next_age.wrapping_add(1);
                voice.age = self.next_age;
                voice.held = true;
                voice.key_down = true;
                let velocity = velocity as f64;
                let mut spectral = velocity.powf(0.75);
                let tilt = velocity.powf(0.12);
                for mode in voice.modes.iter_mut().take(voice.count) {
                    // High partials gain proportionally more energy at greater velocity.
                    mode.current += mode.amplitude * spectral;
                    spectral *= tilt;
                }
            }
        }
    }
}
