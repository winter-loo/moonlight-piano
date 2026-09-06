//! Platform-independent physical primitives for the Moonlight piano engine.

use std::f64::consts::PI;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ModalCoefficients {
    pub feedback_1: f64,
    pub feedback_2: f64,
    pub pole_radius: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PhysicsError {
    NonFinite,
    InvalidSampleRate,
    InvalidFrequency,
    InvalidDecay,
    UnstablePole,
}

pub fn rigid_string_frequency(
    fundamental_hz: f64,
    partial_index: u32,
    inharmonicity: f64,
) -> Result<f64, PhysicsError> {
    if !fundamental_hz.is_finite() || !inharmonicity.is_finite() {
        return Err(PhysicsError::NonFinite);
    }
    if fundamental_hz <= 0.0 || partial_index == 0 || inharmonicity < 0.0 {
        return Err(PhysicsError::InvalidFrequency);
    }
    let n = partial_index as f64;
    Ok(n * fundamental_hz * (1.0 + inharmonicity * n * n).sqrt())
}

/// Convert a modal frequency and amplitude T60 into a stable two-pole resonator.
///
/// `t60_seconds` is the time for amplitude to decay by 60 dB. The poles are
/// conjugates at `radius * exp(±j*omega)` and are strictly inside the unit circle.
pub fn modal_coefficients(
    frequency_hz: f64,
    t60_seconds: f64,
    sample_rate_hz: f64,
) -> Result<ModalCoefficients, PhysicsError> {
    if !frequency_hz.is_finite() || !t60_seconds.is_finite() || !sample_rate_hz.is_finite() {
        return Err(PhysicsError::NonFinite);
    }
    if sample_rate_hz <= 0.0 {
        return Err(PhysicsError::InvalidSampleRate);
    }
    if frequency_hz <= 0.0 || frequency_hz >= sample_rate_hz * 0.5 {
        return Err(PhysicsError::InvalidFrequency);
    }
    if t60_seconds <= 0.0 {
        return Err(PhysicsError::InvalidDecay);
    }

    let radius = 10.0_f64.powf(-3.0 / (t60_seconds * sample_rate_hz));
    if !radius.is_finite() || !(0.0..1.0).contains(&radius) {
        return Err(PhysicsError::UnstablePole);
    }
    let omega = 2.0 * PI * frequency_hz / sample_rate_hz;
    Ok(ModalCoefficients {
        feedback_1: 2.0 * radius * omega.cos(),
        feedback_2: -(radius * radius),
        pole_radius: radius,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rigid_string_partials_are_inharmonic() {
        let second = rigid_string_frequency(261.625_565, 2, 0.00008).unwrap();
        assert!(second > 2.0 * 261.625_565);
    }

    #[test]
    fn passive_mode_has_poles_inside_unit_circle() {
        let coefficients = modal_coefficients(261.625_565, 6.5, 48_000.0).unwrap();
        assert!(coefficients.pole_radius > 0.0);
        assert!(coefficients.pole_radius < 1.0);
    }

    #[test]
    fn invalid_decay_cannot_create_an_unstable_mode() {
        assert_eq!(
            modal_coefficients(261.625_565, -1.0, 48_000.0),
            Err(PhysicsError::InvalidDecay)
        );
    }
}
