//! Validated initialization and the common realtime render boundary.
use std::error::Error;
use std::fmt::{Display, Formatter};

use moonlight_model::{ModelError, ModelPack};

mod basic;
mod realtime;
pub use basic::{BasicError, BasicPianoEngine, FIRST_NOTE, LAST_NOTE, MAX_VOICES};
pub use realtime::{
    BlockReport, HammerDiagnostics, HammerParameters, PianoEvent, PianoEventKind, HAMMER_SUBSTEPS,
    MAX_BLOCK_FRAMES, MAX_EVENTS_PER_BLOCK,
};
use realtime::{ModeState, RealtimeState, RenderError, MODE_CAPACITY};

#[derive(Debug)]
pub enum ProcessError {
    InvalidModel(ModelError),
    InvalidHammerParameters,
    EmptyOutput,
    BlockTooLarge,
    TooManyEvents,
    EventOutsideBlock { frame: u64, start: u64, end: u64 },
    EventsOutOfOrder,
    UnsupportedNote(u8),
    InvalidVelocity,
    UnsupportedControl,
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
            RenderError::UnsupportedControl => Self::UnsupportedControl,
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
        Self::new_with_hammer(pack, sample_rate_hz, seed, HammerParameters::default())
    }

    /// Compile bounded physical parameters outside the realtime callback. The
    /// seed is retained in the host API; this deterministic contact model does
    /// not add random gain variation to a prescribed mechanical strike.
    pub fn new_with_hammer(
        pack: &ModelPack,
        sample_rate_hz: u32,
        _seed: u64,
        hammer: HammerParameters,
    ) -> Result<Self, ProcessError> {
        pack.validate(sample_rate_hz)
            .map_err(ProcessError::InvalidModel)?;
        if !(8_000..=384_000).contains(&sample_rate_hz) {
            return Err(ProcessError::InvalidModel(ModelError::InvalidMode {
                index: 0,
                reason: "sample rate outside supported range",
            }));
        }
        validate_hammer(hammer)?;
        if pack.mode_count > MODE_CAPACITY {
            return Err(ProcessError::InvalidModel(ModelError::InvalidModeCount));
        }
        let step_seconds = 1.0 / (sample_rate_hz as f64 * HAMMER_SUBSTEPS as f64);
        let mut compliance = 0.5 * step_seconds * step_seconds / hammer.mass_kg;
        let mut modes = [ModeState::default(); MODE_CAPACITY];
        for (index, (mode, spec)) in modes
            .iter_mut()
            .zip(pack.modes.iter())
            .take(pack.mode_count)
            .enumerate()
        {
            // Inverse bilinear pole mapping gives midpoint integration exactly
            // the pack's damped frequency/T60. The energy uses this equivalent
            // stiffness, not an unwarped frequency inserted after the solve.
            let radius = 10.0_f64.powf(-3.0 * step_seconds / spec.t60_seconds);
            let phase = 2.0 * std::f64::consts::PI * spec.frequency_hz * step_seconds;
            let denominator = 1.0 + 2.0 * radius * phase.cos() + radius * radius;
            let sigma = 2.0 * (1.0 - radius * radius) / (step_seconds * denominator);
            let omega = 4.0 * radius * phase.sin() / (step_seconds * denominator);
            let frequency_squared = sigma * sigma + omega * omega;
            let inverse_midpoint = 1.0
                / (1.0
                    + step_seconds * sigma
                    + 0.25 * step_seconds * step_seconds * frequency_squared);
            // Mode amplitudes retain their output/radiation-weight role. Strike
            // shapes and masses are independent provisional physical choices.
            let strike_weight =
                (std::f64::consts::PI * (index + 1) as f64 * hammer.strike_position_ratio).sin();
            let force_scale =
                step_seconds * strike_weight * inverse_midpoint / (2.0 * hammer.modal_mass_kg);
            compliance += step_seconds * strike_weight * force_scale;
            *mode = ModeState {
                mass: hammer.modal_mass_kg,
                stiffness: hammer.modal_mass_kg * frequency_squared,
                damping: 2.0 * sigma * hammer.modal_mass_kg,
                strike_weight,
                output_weight: spec.amplitude,
                velocity_scale: inverse_midpoint,
                position_scale: -0.5 * step_seconds * frequency_squared * inverse_midpoint,
                force_scale,
                position: 0.0,
                velocity: 0.0,
                midpoint_velocity: 0.0,
            };
        }
        Ok(Self {
            realtime: RealtimeState {
                note: pack.note,
                output_gain: pack.output_gain,
                mode_count: pack.mode_count,
                modes,
                key_down: false,
                hammer_parameters: hammer,
                velocity_log_ratio: (hammer.loudest_velocity_mps
                    / hammer.softest_midi_velocity_mps)
                    .ln(),
                step_seconds,
                compliance,
                hammer_position: 0.0,
                hammer_velocity: 0.0,
                hammer_active: false,
                contacted: false,
                flight_seconds: 0.0,
                diagnostics: HammerDiagnostics::default(),
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

    pub fn hammer_diagnostics(&self) -> HammerDiagnostics {
        self.realtime.diagnostics
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

fn validate_hammer(parameters: HammerParameters) -> Result<(), ProcessError> {
    let bounded =
        |value: f64, lower: f64, upper: f64| value.is_finite() && (lower..=upper).contains(&value);
    if !bounded(parameters.mass_kg, 0.001, 0.03)
        || !bounded(parameters.stiffness_newtons_per_cubic_meter, 1.0e8, 1.0e14)
        || !bounded(
            parameters.damping_newton_seconds_per_cubic_meter,
            0.0,
            1.0e9,
        )
        || !bounded(parameters.modal_mass_kg, 0.001, 0.2)
        || !bounded(parameters.strike_position_ratio, 0.05, 0.45)
        || !bounded(parameters.softest_midi_velocity_mps, 0.05, 0.5)
        || !bounded(parameters.loudest_velocity_mps, 0.05, 8.0)
        || parameters.loudest_velocity_mps <= parameters.softest_midi_velocity_mps
    {
        return Err(ProcessError::InvalidHammerParameters);
    }
    Ok(())
}
