use moonlight_dsp::{HammerParameters, PianoEngine, PianoEvent, PianoEventKind};
use moonlight_model::parse_model_pack;

const MODEL: &str = include_str!("../../../fixtures/physical-c4/minimal-c4.mlpiano");

fn engine(rate: u32, hammer: HammerParameters) -> PianoEngine {
    PianoEngine::new_with_hammer(&parse_model_pack(MODEL, rate).unwrap(), rate, 17, hammer).unwrap()
}

fn note(frame: u64, velocity: f32) -> PianoEvent {
    PianoEvent {
        frame,
        kind: PianoEventKind::NoteOn { note: 60, velocity },
    }
}

fn render(rate: u32, velocity: f32, seconds: f64) -> (Vec<f32>, PianoEngine) {
    let mut engine = engine(rate, HammerParameters::default());
    let mut samples = vec![0.0; (f64::from(rate) * seconds) as usize];
    for (block, output) in samples.chunks_mut(128).enumerate() {
        let start = (block * 128) as u64;
        let events = [note(start, velocity)];
        engine
            .process_block(start, if block == 0 { &events } else { &[] }, output)
            .unwrap();
    }
    (samples, engine)
}

fn rms(samples: &[f32]) -> f64 {
    (samples
        .iter()
        .map(|&sample| f64::from(sample).powi(2))
        .sum::<f64>()
        / samples.len() as f64)
        .sqrt()
}

#[test]
fn contact_is_compressive_and_passive_through_separation_at_all_rates() {
    for rate in [8_000, 44_100, 48_000, 96_000, 384_000] {
        for velocity in [1.0 / 127.0, 0.25, 1.0] {
            for damping in [0.0, 3_000_000.0] {
                let mut core = engine(
                    rate,
                    HammerParameters {
                        damping_newton_seconds_per_cubic_meter: damping,
                        ..HammerParameters::default()
                    },
                );
                let mut previous_energy = f64::INFINITY;
                let mut saw_contact = false;
                for frame in 0..u64::from(rate / 10) {
                    let event = [note(frame, velocity)];
                    let mut output = [0.0];
                    core.process_block(frame, if frame == 0 { &event } else { &[] }, &mut output)
                        .unwrap();
                    assert!(output[0].is_finite());
                    let diagnostics = core.hammer_diagnostics();
                    assert!(diagnostics.force_newtons.is_finite());
                    assert!(diagnostics.force_newtons >= 0.0);
                    if diagnostics.in_contact {
                        saw_contact = true;
                        assert!(diagnostics.compression_meters > 0.0);
                    } else {
                        assert_eq!(diagnostics.force_newtons, 0.0);
                    }
                    let allowance = 2.0e-9 * diagnostics.input_energy_joules.max(1.0e-6);
                    assert!(
                        diagnostics.total_energy_joules <= previous_energy + allowance,
                        "energy grew: rate={rate}, velocity={velocity}, damping={damping}, {diagnostics:?}"
                    );
                    assert!(
                        diagnostics.max_energy_error_joules < allowance,
                        "unbalanced energy at {rate} Hz: {diagnostics:?}"
                    );
                    previous_energy = diagnostics.total_energy_joules;
                }
                let diagnostics = core.hammer_diagnostics();
                assert!(saw_contact);
                assert_eq!(diagnostics.contact_count, 1);
                assert!(diagnostics.peak_force_newtons > 0.0);
                assert!(diagnostics.peak_compression_meters > 0.0);
                assert!(diagnostics.contact_seconds > 0.0);
                assert_eq!(diagnostics.force_newtons, 0.0);
                assert_eq!(diagnostics.hammer_energy_joules, 0.0);
                assert!(!diagnostics.in_contact);
            }
        }
    }
}

#[test]
fn velocity_changes_spectrum_instead_of_scaling_a_fixed_waveform() {
    let (soft, soft_core) = render(48_000, 0.1, 0.4);
    let (loud, loud_core) = render(48_000, 1.0, 0.4);
    let dot = soft
        .iter()
        .zip(&loud)
        .map(|(&a, &b)| f64::from(a) * f64::from(b))
        .sum::<f64>();
    let soft_energy = soft.iter().map(|&x| f64::from(x).powi(2)).sum::<f64>();
    let gain = dot / soft_energy;
    let residual = soft
        .iter()
        .zip(&loud)
        .map(|(&a, &b)| (f64::from(b) - gain * f64::from(a)).powi(2))
        .sum::<f64>();
    let loud_energy = loud.iter().map(|&x| f64::from(x).powi(2)).sum::<f64>();
    assert!(residual / loud_energy > 0.01);
    assert!(rms(&loud) > rms(&soft));
    let soft_contact = soft_core.hammer_diagnostics();
    let loud_contact = loud_core.hammer_diagnostics();
    assert!(loud_contact.peak_force_newtons > soft_contact.peak_force_newtons);
    assert!(loud_contact.contact_seconds < soft_contact.contact_seconds);

    // Compare upper-partial energy relative to the fundamental after contact.
    let partial_energy = |samples: &[f32], frequency: f64| {
        let mut real = 0.0;
        let mut imaginary = 0.0;
        for (frame, &sample) in samples.iter().enumerate().skip(960) {
            let phase = 2.0 * std::f64::consts::PI * frequency * frame as f64 / 48_000.0;
            real += f64::from(sample) * phase.cos();
            imaginary += f64::from(sample) * phase.sin();
        }
        real * real + imaginary * imaginary
    };
    let brightness = |samples: &[f32]| {
        [1048.399060, 1311.680210, 1575.649780, 2106.171140]
            .iter()
            .map(|&frequency| partial_energy(samples, frequency))
            .sum::<f64>()
            / partial_energy(samples, 261.636030)
    };
    assert!(brightness(&loud) > brightness(&soft));
}

#[test]
fn adjacent_velocities_are_continuous_and_the_full_midi_range_is_monotone() {
    let mut previous = 0.0;
    for midi_velocity in 1..=127 {
        let (samples, _) = render(48_000, midi_velocity as f32 / 127.0, 0.12);
        let level = rms(&samples);
        assert!(
            level > previous,
            "loudness reversal at velocity {midi_velocity}"
        );
        if previous > 0.0 {
            assert!(
                20.0 * (level / previous).log10() <= 0.5,
                "adjacent velocity jump exceeds spec at velocity {midi_velocity}"
            );
        }
        previous = level;
    }
    let (a, _) = render(48_000, 0.5, 0.2);
    let (b, _) = render(48_000, 0.5001, 0.2);
    let difference: Vec<_> = a.iter().zip(&b).map(|(a, b)| a - b).collect();
    assert!(rms(&difference) / rms(&a) < 0.01);
}

#[test]
fn sub_midi_velocity_bridge_has_no_floor_or_derivative_step() {
    let speed = |velocity| {
        let mut core = engine(48_000, HammerParameters::default());
        core.process_block(0, &[note(0, velocity)], &mut [0.0])
            .unwrap();
        core.hammer_diagnostics().initial_velocity_mps
    };
    let mut previous = 0.0;
    for step in 1..=128 {
        let velocity = step as f32 / (127.0 * 128.0);
        let current = speed(velocity);
        assert!(current > previous && current <= 0.120_001);
        previous = current;
    }
    assert_eq!(speed(0.0), 0.0);
    assert!(speed(1.0e-6) < 1.0e-6);
    let split = 1.0 / 127.0;
    let epsilon = 1.0e-6;
    let center = speed(split);
    let left_slope = (center - speed(split - epsilon)) / f64::from(epsilon);
    let right_slope = (speed(split + epsilon) - center) / f64::from(epsilon);
    assert!((left_slope - right_slope).abs() < 0.02);
}

#[test]
fn bounded_exponential_mapping_matches_reference_across_parameter_limits() {
    for (softest, loudest) in [(0.05, 8.0), (0.12, 5.0), (0.5, 0.51)] {
        let parameters = HammerParameters {
            softest_midi_velocity_mps: softest,
            loudest_velocity_mps: loudest,
            ..HammerParameters::default()
        };
        for step in 1..=127 {
            let velocity = step as f32 / 127.0;
            let mut core = engine(48_000, parameters);
            core.process_block(0, &[note(0, velocity)], &mut [0.0])
                .unwrap();
            let observed = core.hammer_diagnostics().initial_velocity_mps;
            let t = (f64::from(velocity) - 1.0 / 127.0) / (126.0 / 127.0);
            let reference = softest * ((loudest / softest).ln() * t).exp();
            assert!(
                (observed / reference - 1.0).abs() < 1.1e-6,
                "anchor range {softest}..{loudest}, velocity {step}"
            );
            assert!(observed <= loudest * (1.0 + 1e-14));
        }
    }
}

#[test]
fn finite_velocities_clamp_but_nonfinite_events_preserve_state() {
    assert_eq!(render(48_000, -10.0, 0.02).0, render(48_000, 0.0, 0.02).0);
    assert_eq!(render(48_000, 10.0, 0.02).0, render(48_000, 1.0, 0.02).0);
    assert!(render(48_000, 0.0, 0.02)
        .0
        .iter()
        .all(|&sample| sample == 0.0));
    for bad in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
        let mut altered = engine(48_000, HammerParameters::default());
        let mut untouched = engine(48_000, HammerParameters::default());
        let mut prefix = [0.0; 128];
        for core in [&mut altered, &mut untouched] {
            core.process_block(0, &[note(0, 0.8)], &mut prefix).unwrap();
        }
        let before = altered.hammer_diagnostics();
        let mut rejected = [1.0; 128];
        assert!(altered
            .process_block(128, &[note(128, bad)], &mut rejected)
            .is_err());
        assert!(rejected.iter().all(|&sample| sample == 0.0));
        assert_eq!(altered.hammer_diagnostics(), before);
        let mut a = [0.0; 128];
        let mut b = [0.0; 128];
        altered.process_block(128, &[], &mut a).unwrap();
        untouched.process_block(128, &[], &mut b).unwrap();
        assert_eq!(a, b);
    }
}

#[test]
fn repeated_strikes_keep_string_history_and_account_for_replaced_hammer() {
    let mut repeated = engine(48_000, HammerParameters::default());
    let mut a = [0.0; 4096];
    repeated
        .process_block(0, &[note(0, 0.8)], &mut a[..32])
        .unwrap();
    let energy_before = repeated.hammer_diagnostics().string_energy_joules;
    assert!(energy_before > 0.0);
    repeated
        .process_block(32, &[note(32, 0.8)], &mut a)
        .unwrap();
    let d = repeated.hammer_diagnostics();
    assert!(d.max_energy_error_joules < 1.0e-9);
    assert!(d.dissipated_energy_joules > 0.0);
    let mut fresh = engine(48_000, HammerParameters::default());
    let mut b = [0.0; 4096];
    fresh.process_block(32, &[note(32, 0.8)], &mut b).unwrap();
    assert_ne!(a, b);
    let repeat_render = || {
        let mut core = engine(48_000, HammerParameters::default());
        let mut samples = [0.0; 4096];
        core.process_block(
            0,
            &[note(0, 0.8), note(32, 0.8), note(370, 0.8)],
            &mut samples,
        )
        .unwrap();
        samples
    };
    assert_eq!(repeat_render(), repeat_render());
}

#[test]
fn invalid_parameters_fail_before_audio_and_valid_extremes_stay_bounded() {
    let pack = parse_model_pack(MODEL, 48_000).unwrap();
    for parameters in [
        HammerParameters {
            mass_kg: 0.0,
            ..HammerParameters::default()
        },
        HammerParameters {
            mass_kg: f64::NAN,
            ..HammerParameters::default()
        },
        HammerParameters {
            stiffness_newtons_per_cubic_meter: f64::INFINITY,
            ..HammerParameters::default()
        },
        HammerParameters {
            damping_newton_seconds_per_cubic_meter: -1.0,
            ..HammerParameters::default()
        },
        HammerParameters {
            modal_mass_kg: -0.01,
            ..HammerParameters::default()
        },
        HammerParameters {
            strike_position_ratio: 0.0,
            ..HammerParameters::default()
        },
        HammerParameters {
            loudest_velocity_mps: 16.0,
            ..HammerParameters::default()
        },
    ] {
        assert!(PianoEngine::new_with_hammer(&pack, 48_000, 17, parameters).is_err());
    }
    for mass in [0.001, 0.03] {
        for stiffness in [1.0e8, 1.0e14] {
            for damping in [0.0, 1.0e9] {
                let mut core = engine(
                    8_000,
                    HammerParameters {
                        mass_kg: mass,
                        stiffness_newtons_per_cubic_meter: stiffness,
                        damping_newton_seconds_per_cubic_meter: damping,
                        modal_mass_kg: 0.001,
                        strike_position_ratio: 0.05,
                        softest_midi_velocity_mps: 0.12,
                        loudest_velocity_mps: 8.0,
                    },
                );
                let mut samples = [0.0; 1600];
                core.process_block(0, &[note(0, 1.0), note(3, 1.0)], &mut samples)
                    .unwrap();
                assert!(samples.iter().all(|sample| sample.is_finite()));
                let diagnostics = core.hammer_diagnostics();
                assert!(
                    diagnostics.max_energy_error_joules < 2.0e-7,
                    "{diagnostics:?}"
                );
                assert!(
                    diagnostics.total_energy_joules <= diagnostics.input_energy_joules + 2.0e-7
                );
            }
        }
    }
}
