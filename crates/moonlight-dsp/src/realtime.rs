//! Allocation-free render closure. Also compiled independently without std by CI.
//! Host-owned event/output slices are borrowed, never queued or retained.
#![forbid(unsafe_code)]

pub const MODE_CAPACITY: usize = 16;
pub const MAX_BLOCK_FRAMES: usize = 16_384;
pub const MAX_EVENTS_PER_BLOCK: usize = 256;

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

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum RenderError {
    EmptyOutput,
    BlockTooLarge,
    TooManyEvents,
    EventOutsideBlock { frame: u64, start: u64, end: u64 },
    EventsOutOfOrder,
    UnsupportedNote(u8),
    InvalidVelocity,
    NonFiniteOutput,
}

#[derive(Debug, Clone, Copy, Default)]
pub struct ModeState {
    pub feedback_1: f64,
    pub feedback_2: f64,
    pub amplitude: f64,
    pub current: f64,
    pub previous: f64,
}

pub struct RealtimeState {
    pub note: u8,
    pub output_gain: f64,
    pub mode_count: usize,
    pub modes: [ModeState; MODE_CAPACITY],
    pub key_down: bool,
    pub pending_impulse: f64,
    pub rng_state: u64,
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
            let impulse = self.pending_impulse;
            self.pending_impulse = 0.0;
            let mut sum = 0.0;
            for mode in self.modes.iter_mut().take(self.mode_count) {
                let next = mode.feedback_1 * mode.current
                    + mode.feedback_2 * mode.previous
                    + impulse * mode.amplitude;
                mode.previous = mode.current;
                mode.current = next;
                sum += next;
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
            mode.current = 0.0;
            mode.previous = 0.0;
        }
        self.key_down = false;
        self.pending_impulse = 0.0;
    }

    pub fn active_modes(&self) -> usize {
        self.modes
            .iter()
            .take(self.mode_count)
            .filter(|mode| mode.current != 0.0 || mode.previous != 0.0)
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
        };
        if note != self.note {
            return Err(RenderError::UnsupportedNote(note));
        }
        if !velocity.is_finite() || !(0.0..=1.0).contains(&velocity) {
            return Err(RenderError::InvalidVelocity);
        }
        Ok(())
    }

    fn apply_event(&mut self, event: PianoEvent) {
        match event.kind {
            PianoEventKind::NoteOn { velocity, .. } => {
                self.key_down = true;
                let mut value = self.rng_state;
                value ^= value << 13;
                value ^= value >> 7;
                value ^= value << 17;
                self.rng_state = value;
                let variation = 0.995 + (value as f64 / u64::MAX as f64) * 0.01;
                self.pending_impulse += velocity as f64 * variation;
            }
            PianoEventKind::NoteOff { .. } => self.key_down = false,
            PianoEventKind::Reset => self.reset(),
        }
    }
}
