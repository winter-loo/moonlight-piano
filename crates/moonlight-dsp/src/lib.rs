//! Validated initialization and the common realtime render boundary.
use std::error::Error;
use std::fmt::{Display, Formatter};

use moonlight_model::{ModelError, ModelPack};
use moonlight_physics::modal_coefficients;

mod realtime;
pub use realtime::{
    BlockReport, PianoEvent, PianoEventKind, MAX_BLOCK_FRAMES, MAX_EVENTS_PER_BLOCK,
};
use realtime::{ModeState, RealtimeState, RenderError, MODE_CAPACITY};

#[derive(Debug)]
pub enum ProcessError {
    InvalidModel(ModelError),
    EmptyOutput,
    BlockTooLarge,
    TooManyEvents,
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
impl From<RenderError> for ProcessError {
    fn from(error: RenderError) -> Self {
        match error {
            RenderError::EmptyOutput => Self::EmptyOutput,
            RenderError::BlockTooLarge => Self::BlockTooLarge,
            RenderError::TooManyEvents => Self::TooManyEvents,
            RenderError::EventOutsideBlock { frame, start, end } => {
                Self::EventOutsideBlock { frame, start, end }
            }
            RenderError::EventsOutOfOrder => Self::EventsOutOfOrder,
            RenderError::UnsupportedNote(note) => Self::UnsupportedNote(note),
            RenderError::InvalidVelocity => Self::InvalidVelocity,
            RenderError::NonFiniteOutput => Self::NonFiniteOutput,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct StateCounts {
    pub configured_modes: usize,
    pub active_modes: usize,
    pub active_strings: usize,
    pub state_bytes: usize,
}

pub struct PianoEngine {
    realtime: RealtimeState,
}

impl PianoEngine {
    /// Non-realtime: validation, model parsing, and coefficient compilation.
    pub fn new(pack: &ModelPack, sample_rate_hz: u32, seed: u64) -> Result<Self, ProcessError> {
        pack.validate(sample_rate_hz)
            .map_err(ProcessError::InvalidModel)?;
        if pack.mode_count > MODE_CAPACITY {
            return Err(ProcessError::InvalidModel(ModelError::InvalidModeCount));
        }
        let mut modes = [ModeState::default(); MODE_CAPACITY];
        for (mode, spec) in modes
            .iter_mut()
            .zip(pack.modes.iter())
            .take(pack.mode_count)
        {
            let coefficients =
                modal_coefficients(spec.frequency_hz, spec.t60_seconds, sample_rate_hz as f64)
                    .map_err(|_| ProcessError::InvalidModel(ModelError::InvalidModeCount))?;
            *mode = ModeState {
                feedback_1: coefficients.feedback_1,
                feedback_2: coefficients.feedback_2,
                amplitude: spec.amplitude,
                current: 0.0,
                previous: 0.0,
            };
        }
        Ok(Self {
            realtime: RealtimeState {
                note: pack.note,
                output_gain: pack.output_gain,
                mode_count: pack.mode_count,
                modes,
                key_down: false,
                pending_impulse: 0.0,
                rng_state: seed.max(1),
            },
        })
    }

    /// Realtime: bounded borrowed inputs; errors leave no queued work.
    /// Invalid-size buffers are untouched. Other errors silence a valid buffer.
    pub fn process_block(
        &mut self,
        block_start_frame: u64,
        events: &[PianoEvent],
        output: &mut [f32],
    ) -> Result<BlockReport, ProcessError> {
        let result = self
            .realtime
            .process_block(block_start_frame, events, output);
        if result.is_err() && output.len() <= MAX_BLOCK_FRAMES {
            output.fill(0.0);
        }
        result.map_err(ProcessError::from)
    }

    pub fn reset(&mut self) {
        self.realtime.reset();
    }

    pub fn key_down(&self) -> bool {
        self.realtime.key_down
    }

    pub fn state_counts(&self) -> StateCounts {
        let active_modes = self.realtime.active_modes();
        StateCounts {
            configured_modes: self.realtime.mode_count,
            active_modes,
            active_strings: usize::from(active_modes > 0),
            state_bytes: std::mem::size_of::<Self>(),
        }
    }
}
