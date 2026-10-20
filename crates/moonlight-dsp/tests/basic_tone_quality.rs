use moonlight_dsp::{BasicPianoEngine, PianoEvent, PianoEventKind};

fn render(rate: u32, notes: &[u8], velocity: f32, release: bool) -> Vec<f32> {
    let mut engine = BasicPianoEngine::new(rate).unwrap();
    let mut events: Vec<_> = notes
        .iter()
        .map(|note| PianoEvent {
            frame: 0,
            kind: PianoEventKind::NoteOn {
                note: *note,
                velocity,
            },
        })
        .collect();
    if release {
        events.extend(notes.iter().map(|note| PianoEvent {
            frame: u64::from(rate),
            kind: PianoEventKind::NoteOff {
                note: *note,
                release_velocity: 0.5,
            },
        }));
    }
    let mut output = vec![0.0; rate as usize * 2];
    for (block, chunk) in output.chunks_mut(256).enumerate() {
        let start = (block * 256) as u64;
        let first = events.partition_point(|event| event.frame < start);
        let last = events.partition_point(|event| event.frame < start + chunk.len() as u64);
        engine
            .process_block(start, &events[first..last], chunk)
            .unwrap();
    }
    output
}

fn rms(samples: &[f32]) -> f64 {
    (samples.iter().map(|x| f64::from(*x).powi(2)).sum::<f64>() / samples.len() as f64).sqrt()
}

fn dominant_frequency(samples: &[f32], rate: u32, low: f64, high: f64) -> f64 {
    let mut best = (0.0, 0.0);
    for step in 0..=((high - low) * 2.0).ceil() as usize {
        let frequency = low + step as f64 * 0.5;
        let omega = core::f64::consts::TAU * frequency / f64::from(rate);
        let mut real = 0.0;
        let mut imaginary = 0.0;
        for (index, sample) in samples.iter().enumerate() {
            let window = (core::f64::consts::PI * index as f64 / samples.len() as f64)
                .sin()
                .powi(2);
            let (sine, cosine) = (omega * index as f64).sin_cos();
            real += f64::from(*sample) * window * cosine;
            imaginary += f64::from(*sample) * window * sine;
        }
        let power = real * real + imaginary * imaginary;
        if power > best.1 {
            best = (frequency, power);
        }
    }
    best.0
}

#[test]
fn releasing_a_key_does_not_turn_its_tail_into_a_different_pitch() {
    for rate in [44_100, 48_000] {
        for note in [33, 45, 60] {
            let output = render(rate, &[note], 0.8, true);
            let fundamental = 440.0 * 2.0_f64.powf((f64::from(note) - 69.0) / 12.0);
            let tail =
                &output[(f64::from(rate) * 1.005) as usize..(f64::from(rate) * 1.125) as usize];
            let frequency = dominant_frequency(
                tail,
                rate,
                fundamental * 0.8,
                (fundamental * 1.8).max(260.0),
            );
            assert!((frequency - fundamental).abs() < 2.0,
                "MIDI {note} at {rate} Hz: released fundamental {frequency:.2}, expected {fundamental:.2}");
        }
    }
}

#[test]
fn ordinary_chords_do_not_create_output_stage_intermodulation() {
    let c = render(48_000, &[60], 0.8, false);
    let e = render(48_000, &[64], 0.8, false);
    let chord = render(48_000, &[60, 64], 0.8, false);
    let difference: Vec<_> = c
        .iter()
        .zip(&e)
        .zip(&chord)
        .map(|((c, e), chord)| chord - c - e)
        .collect();
    assert!(
        rms(&difference) / rms(&chord) < 0.000001,
        "a normal two-key chord must equal the linear sum of the two keys"
    );
}

#[test]
fn excitation_does_not_gain_an_inverse_frequency_or_sample_rate_factor() {
    for rate in [44_100, 48_000] {
        let low = render(rate, &[33], 0.8, false);
        let high = render(rate, &[84], 0.8, false);
        let ratio = rms(&low[..rate as usize]) / rms(&high[..rate as usize]);
        assert!(
            (0.7..1.5).contains(&ratio),
            "register RMS ratio {ratio} at {rate}"
        );
    }
    let a = render(44_100, &[45], 0.8, false);
    let b = render(48_000, &[45], 0.8, false);
    let db = 20.0 * (rms(&a[..44_100]) / rms(&b[..48_000])).log10();
    assert!(db.abs() < 0.1, "sample-rate gain difference {db} dB");
}

#[test]
fn dense_repeated_chords_remain_finite_and_within_full_scale() {
    let mut engine = BasicPianoEngine::new(48_000).unwrap();
    let notes: Vec<_> = (36..68)
        .map(|note| PianoEvent {
            frame: 0,
            kind: PianoEventKind::NoteOn {
                note,
                velocity: 1.0,
            },
        })
        .collect();
    let mut output = [0.0; 256];
    for block in 0..512 {
        let start = block * 256;
        let events: Vec<_> = if block % 8 == 0 {
            notes
                .iter()
                .map(|event| PianoEvent {
                    frame: start,
                    kind: event.kind,
                })
                .collect()
        } else {
            Vec::new()
        };
        engine.process_block(start, &events, &mut output).unwrap();
        assert!(output
            .iter()
            .all(|sample| sample.is_finite() && sample.abs() <= 1.0));
    }
}
