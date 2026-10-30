//! Allocation-free render closure. Also compiled independently without std by CI.
//! Host-owned event/output slices are borrowed, never queued or retained.
#![forbid(unsafe_code)]

pub const MODE_CAPACITY: usize = 16;
pub const MAX_BLOCK_FRAMES: usize = 16_384;
pub const MAX_EVENTS_PER_BLOCK: usize = 256;
pub const HAMMER_SUBSTEPS: usize = 4;
const CONTACT_ITERATIONS: usize = 32;

/// Prototype physical parameters. These are independently chosen, not measured
/// piano parameters. Exponents are fixed at p=3 and q=2 in this solver.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct HammerParameters {
    pub mass_kg: f64,
    pub stiffness_newtons_per_cubic_meter: f64,
    pub damping_newton_seconds_per_cubic_meter: f64,
    pub modal_mass_kg: f64,
    pub strike_position_ratio: f64,
    pub softest_midi_velocity_mps: f64,
    pub loudest_velocity_mps: f64,
}

impl Default for HammerParameters {
    fn default() -> Self {
        Self {
            mass_kg: 0.008,
            stiffness_newtons_per_cubic_meter: 100_000_000_000.0,
            damping_newton_seconds_per_cubic_meter: 3_000_000.0,
            modal_mass_kg: 0.02,
            strike_position_ratio: 1.0 / 7.0,
            softest_midi_velocity_mps: 0.12,
            loudest_velocity_mps: 5.0,
        }
    }
}

/// Last strike contact measurements survive separation; energy totals cover all
/// strikes since Reset. `force_newtons` is the last substep's average force while
/// contact remains closed, and exactly zero once the backcheck catches it.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct HammerDiagnostics {
    pub force_newtons: f64,
    pub peak_force_newtons: f64,
    pub compression_meters: f64,
    pub peak_compression_meters: f64,
    pub initial_velocity_mps: f64,
    pub hammer_velocity_mps: f64,
    pub contact_seconds: f64,
    pub hammer_energy_joules: f64,
    pub string_energy_joules: f64,
    pub total_energy_joules: f64,
    pub dissipated_energy_joules: f64,
    pub input_energy_joules: f64,
    pub max_energy_error_joules: f64,
    pub contact_count: u32,
    pub in_contact: bool,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum PianoEventKind {
    NoteOn { note: u8, velocity: f32 },
    NoteOff { note: u8, release_velocity: f32 },
    Sustain { position: f32 },
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

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum RenderError {
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

#[derive(Debug, Clone, Copy, Default)]
pub struct ModeState {
    pub mass: f64,
    pub stiffness: f64,
    pub damping: f64,
    pub strike_weight: f64,
    pub output_weight: f64,
    pub velocity_scale: f64,
    pub position_scale: f64,
    pub force_scale: f64,
    pub position: f64,
    pub velocity: f64,
    pub midpoint_velocity: f64,
}

pub struct RealtimeState {
    pub note: u8,
    pub output_gain: f64,
    pub mode_count: usize,
    pub modes: [ModeState; MODE_CAPACITY],
    pub key_down: bool,
    pub hammer_parameters: HammerParameters,
    pub velocity_log_ratio: f64,
    pub step_seconds: f64,
    pub compliance: f64,
    pub hammer_position: f64,
    pub hammer_velocity: f64,
    pub hammer_active: bool,
    pub contacted: bool,
    pub flight_seconds: f64,
    pub diagnostics: HammerDiagnostics,
}

impl RealtimeState {
    pub fn process_block(
        &mut self,
        start: u64,
        events: &[PianoEvent],
        output: &mut [f32],
    ) -> Result<BlockReport, RenderError> {
        // Reject untrusted host sizes before loops, indexing, or state changes.
        if output.is_empty() {
            return Err(RenderError::EmptyOutput);
        }
        if output.len() > MAX_BLOCK_FRAMES {
            return Err(RenderError::BlockTooLarge);
        }
        if events.len() > MAX_EVENTS_PER_BLOCK {
            return Err(RenderError::TooManyEvents);
        }
        let end = start
            .checked_add(output.len() as u64)
            .ok_or(RenderError::EventOutsideBlock {
                frame: u64::MAX,
                start,
                end: u64::MAX,
            })?;
        let mut previous = None;
        for event in events {
            if event.frame < start || event.frame >= end {
                return Err(RenderError::EventOutsideBlock {
                    frame: event.frame,
                    start,
                    end,
                });
            }
            if previous.is_some_and(|frame| event.frame < frame) {
                return Err(RenderError::EventsOutOfOrder);
            }
            previous = Some(event.frame);
            self.validate_event(*event)?;
        }
        let mut events = events.iter().peekable();
        let mut applied_events = 0;
        for (offset, sample) in output.iter_mut().enumerate() {
            let frame = start + offset as u64;
            while events.peek().is_some_and(|event| event.frame == frame) {
                if let Some(event) = events.next() {
                    self.apply_event(*event);
                    applied_events += 1;
                }
            }
            for _ in 0..HAMMER_SUBSTEPS {
                self.step();
            }
            let mut sum = 0.0;
            for mode in self.modes.iter().take(self.mode_count) {
                sum += mode.velocity * mode.output_weight;
            }
            let rendered = (sum * self.output_gain) as f32;
            if !rendered.is_finite() {
                self.reset();
                return Err(RenderError::NonFiniteOutput);
            }
            *sample = rendered;
        }
        Ok(BlockReport {
            start_frame: start,
            rendered_frames: output.len(),
            applied_events,
            key_down: self.key_down,
        })
    }

    pub fn reset(&mut self) {
        for mode in &mut self.modes {
            mode.position = 0.0;
            mode.velocity = 0.0;
            mode.midpoint_velocity = 0.0;
        }
        self.key_down = false;
        self.hammer_active = false;
        self.contacted = false;
        self.hammer_position = 0.0;
        self.hammer_velocity = 0.0;
        self.flight_seconds = 0.0;
        self.diagnostics = HammerDiagnostics::default();
    }

    pub fn active_modes(&self) -> usize {
        self.modes
            .iter()
            .take(self.mode_count)
            .filter(|mode| mode.position != 0.0 || mode.velocity != 0.0)
            .count()
    }

    fn validate_event(&self, event: PianoEvent) -> Result<(), RenderError> {
        let (note, velocity) = match event.kind {
            PianoEventKind::NoteOn { note, velocity } => (note, velocity),
            PianoEventKind::NoteOff {
                note,
                release_velocity,
            } => (note, release_velocity),
            PianoEventKind::Reset => return Ok(()),
            PianoEventKind::Sustain { .. } => return Err(RenderError::UnsupportedControl),
        };
        if note != self.note {
            return Err(RenderError::UnsupportedNote(note));
        }
        if !velocity.is_finite() {
            return Err(RenderError::InvalidVelocity);
        }
        Ok(())
    }

    fn apply_event(&mut self, event: PianoEvent) {
        match event.kind {
            PianoEventKind::NoteOn { velocity, .. } => {
                self.strike(f64::from(velocity).clamp(0.0, 1.0));
            }
            PianoEventKind::NoteOff { .. } => self.key_down = false,
            PianoEventKind::Reset => self.reset(),
            PianoEventKind::Sustain { .. } => {}
        }
    }

    fn string_position(&self) -> f64 {
        self.modes
            .iter()
            .take(self.mode_count)
            .map(|mode| mode.strike_weight * mode.position)
            .sum()
    }

    fn felt_energy(&self, compression: f64) -> f64 {
        let squared = compression.max(0.0) * compression.max(0.0);
        0.25 * self.hammer_parameters.stiffness_newtons_per_cubic_meter * squared * squared
    }

    fn strike(&mut self, velocity: f64) {
        // Replacing a still-flying hammer is an explicit passive backcheck, not
        // an impulse to or reset of the already moving modal string.
        let string_position = self.string_position();
        self.catch_hammer(string_position);
        let parameters = self.hammer_parameters;
        let speed = self.hammer_speed(velocity);
        self.hammer_velocity = speed;
        self.hammer_position = string_position;
        self.hammer_active = speed > 0.0;
        self.key_down = speed > 0.0;
        self.contacted = false;
        self.flight_seconds = 0.0;
        self.diagnostics.initial_velocity_mps = speed;
        self.diagnostics.peak_force_newtons = 0.0;
        self.diagnostics.peak_compression_meters = 0.0;
        self.diagnostics.contact_seconds = 0.0;
        self.diagnostics.input_energy_joules += 0.5 * parameters.mass_kg * speed * speed;
    }

    fn hammer_speed(&self, velocity: f64) -> f64 {
        let parameters = self.hammer_parameters;
        const FIRST_MIDI_VELOCITY: f64 = 1.0 / 127.0;
        if velocity < FIRST_MIDI_VELOCITY {
            // Monotone cubic Hermite: exactly silent at zero and C1 with the
            // playable range. This is not a positive-velocity floor or layer.
            let t = velocity / FIRST_MIDI_VELOCITY;
            let end_slope = parameters.softest_midi_velocity_mps * self.velocity_log_ratio / 126.0;
            let softest = parameters.softest_midi_velocity_mps;
            t * t * ((3.0 * softest - end_slope) + (end_slope - 2.0 * softest) * t)
        } else {
            let t = (velocity - FIRST_MIDI_VELOCITY) / (1.0 - FIRST_MIDI_VELOCITY);
            // exp(x) with x/16 <= ln(160)/16 < 0.318: positive sixth-order
            // Taylor polynomial followed by four squarings. Fixed work, no
            // runtime libm call, no table/layer boundaries. Relative error is
            // < 1.1e-6 throughout the validated anchor range (< 1e-7 default).
            let x = self.velocity_log_ratio * t / 16.0;
            let mut exponential = 1.0
                + x * (1.0
                    + x * (0.5
                        + x * (1.0 / 6.0 + x * (1.0 / 24.0 + x * (1.0 / 120.0 + x / 720.0)))));
            for _ in 0..4 {
                exponential *= exponential;
            }
            parameters.softest_midi_velocity_mps * exponential
        }
    }

    fn catch_hammer(&mut self, string_position: f64) {
        if self.hammer_active {
            self.diagnostics.dissipated_energy_joules +=
                0.5 * self.hammer_parameters.mass_kg * self.hammer_velocity * self.hammer_velocity
                    + self.felt_energy(self.hammer_position - string_position);
        }
        self.hammer_active = false;
        self.hammer_position = string_position;
        self.hammer_velocity = 0.0;
        self.diagnostics.force_newtons = 0.0;
        self.diagnostics.compression_meters = 0.0;
        self.diagnostics.in_contact = false;
    }

    /// Coupled implicit-midpoint mechanical step, with a discrete gradient for
    /// the one-sided quartic felt potential. The modal free motion and force
    /// compliance are affine, so only one scalar nonnegative force is solved.
    fn step(&mut self) {
        let h = self.step_seconds;
        let parameters = self.hammer_parameters;
        let string_before = self.string_position();
        let compression_before = self.hammer_position - string_before;
        let mut free_string_after = 0.0;
        for mode in self.modes.iter_mut().take(self.mode_count) {
            mode.midpoint_velocity =
                mode.velocity_scale * mode.velocity + mode.position_scale * mode.position;
            free_string_after += mode.strike_weight * (mode.position + h * mode.midpoint_velocity);
        }

        let mut force = 0.0;
        let free_compression = self.hammer_position + h * self.hammer_velocity - free_string_after;
        if self.hammer_active {
            // H(delta) is monotone. Since delta(F)=a-bF with b>0, the
            // residual F-max(0,H(a-bF)) is strictly increasing. This bracket
            // follows directly; no unbounded search or convergence loop.
            let mut low = 0.0;
            let mut high = self
                .contact_force(compression_before, free_compression)
                .max(0.0);
            for _ in 0..CONTACT_ITERATIONS {
                let middle = 0.5 * (low + high);
                let compression_after = free_compression - self.compliance * middle;
                let candidate = self
                    .contact_force(compression_before, compression_after)
                    .max(0.0);
                if middle < candidate {
                    low = middle;
                } else {
                    high = middle;
                }
            }
            force = 0.5 * (low + high);
            let midpoint_velocity = self.hammer_velocity - h * force / (2.0 * parameters.mass_kg);
            self.hammer_position += h * midpoint_velocity;
            self.hammer_velocity = 2.0 * midpoint_velocity - self.hammer_velocity;
            self.flight_seconds += h;
        }

        let mut string_after = 0.0;
        let mut string_energy = 0.0;
        for mode in self.modes.iter_mut().take(self.mode_count) {
            let midpoint = mode.midpoint_velocity + mode.force_scale * force;
            mode.position += h * midpoint;
            mode.velocity = 2.0 * midpoint - mode.velocity;
            string_after += mode.strike_weight * mode.position;
            string_energy += 0.5
                * (mode.mass * mode.velocity * mode.velocity
                    + mode.stiffness * mode.position * mode.position);
            self.diagnostics.dissipated_energy_joules += h * mode.damping * midpoint * midpoint;
        }

        if self.hammer_active {
            let compression_after = self.hammer_position - string_after;
            let elastic = self.elastic_gradient(compression_before, compression_after);
            let damping = self.damping_force(compression_before, compression_after);
            // Use the law's theoretical dissipation, not a balancing residual:
            // the finite bisection error stays visible in max_energy_error.
            let loss_force = if elastic + damping > 0.0 {
                damping
            } else {
                -elastic
            };
            self.diagnostics.dissipated_energy_joules +=
                (loss_force * (compression_after - compression_before)).max(0.0);
            self.diagnostics.force_newtons = force;
            self.diagnostics.compression_meters = compression_after.max(0.0);
            self.diagnostics.peak_force_newtons = self.diagnostics.peak_force_newtons.max(force);
            self.diagnostics.peak_compression_meters = self
                .diagnostics
                .peak_compression_meters
                .max(compression_after.max(0.0));
            if force > 0.0 {
                if !self.contacted {
                    self.diagnostics.contact_count =
                        self.diagnostics.contact_count.saturating_add(1);
                }
                self.contacted = true;
                self.diagnostics.contact_seconds += h;
            }
            self.diagnostics.in_contact = force > 0.0 && compression_after > 0.0;
            if (self.contacted && (force == 0.0 || compression_after <= 0.0))
                || self.flight_seconds >= 1.0
            {
                // One impact per event in #7. Removing the remaining hammer
                // and felt energy is explicitly accounted, never restored on
                // a subsequent contact. Detailed key-action/recollision is #15.
                self.catch_hammer(string_after);
            }
        } else {
            self.hammer_position = string_after;
        }

        self.diagnostics.hammer_velocity_mps = self.hammer_velocity;
        self.diagnostics.hammer_energy_joules =
            0.5 * parameters.mass_kg * self.hammer_velocity * self.hammer_velocity;
        self.diagnostics.string_energy_joules = string_energy;
        self.diagnostics.total_energy_joules = string_energy
            + self.diagnostics.hammer_energy_joules
            + self.felt_energy(self.diagnostics.compression_meters);
        let error = self.diagnostics.total_energy_joules
            + self.diagnostics.dissipated_energy_joules
            - self.diagnostics.input_energy_joules;
        let absolute_error = if error < 0.0 { -error } else { error };
        self.diagnostics.max_energy_error_joules =
            self.diagnostics.max_energy_error_joules.max(absolute_error);
    }

    fn contact_force(&self, before: f64, after: f64) -> f64 {
        self.elastic_gradient(before, after) + self.damping_force(before, after)
    }

    fn elastic_gradient(&self, before: f64, after: f64) -> f64 {
        let a = before.max(0.0);
        let b = after.max(0.0);
        let coefficient = 0.25 * self.hammer_parameters.stiffness_newtons_per_cubic_meter;
        if before >= 0.0 && after >= 0.0 {
            // Factored quartic divided difference, also valid when a == b.
            coefficient * (a + b) * (a * a + b * b)
        } else if a > 0.0 {
            coefficient * a * a * a * (a / (before - after))
        } else if b > 0.0 {
            coefficient * b * b * b * (b / (after - before))
        } else {
            0.0
        }
    }

    fn damping_force(&self, before: f64, after: f64) -> f64 {
        let a = before.max(0.0);
        let b = after.max(0.0);
        // Integral mean of C*delta^2 over the compression change. This is a
        // nonnegative secant times relative velocity, and is monotone in b.
        self.hammer_parameters
            .damping_newton_seconds_per_cubic_meter
            * (b - a)
            * (b * b + a * b + a * a)
            / (3.0 * self.step_seconds)
    }
}
