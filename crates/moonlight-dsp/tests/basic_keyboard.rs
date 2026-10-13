use moonlight_dsp::{BasicError, BasicPianoEngine, PianoEvent, PianoEventKind, MAX_VOICES};

fn on(frame: u64, note: u8) -> PianoEvent {
    PianoEvent {
        frame,
        kind: PianoEventKind::NoteOn {
            note,
            velocity: 0.8,
        },
    }
}

fn off(frame: u64, note: u8) -> PianoEvent {
    PianoEvent {
        frame,
        kind: PianoEventKind::NoteOff {
            note,
            release_velocity: 0.5,
        },
    }
}

#[test]
fn every_piano_key_sounds_at_both_web_sample_rates() {
    for rate in [44_100, 48_000] {
        let mut engine = BasicPianoEngine::new(rate).unwrap();
        let mut output = [0.0; 128];
        for note in 21..=108 {
            engine.reset();
            engine
                .process_block(0, &[on(17, note)], &mut output)
                .unwrap();
            assert!(output[..17].iter().all(|sample| *sample == 0.0));
            assert!(
                output[17..].iter().any(|sample| *sample != 0.0),
                "MIDI {note}"
            );
            assert!(
                output.iter().all(|sample| sample.is_finite()),
                "MIDI {note}"
            );
        }
        assert_eq!(
            engine.process_block(0, &[on(0, 20)], &mut output),
            Err(BasicError::UnsupportedNote)
        );
        assert_eq!(
            engine.process_block(0, &[on(0, 109)], &mut output),
            Err(BasicError::UnsupportedNote)
        );
    }
}

#[test]
fn chords_are_bounded_and_note_off_retains_a_damped_tail() {
    let mut engine = BasicPianoEngine::new(48_000).unwrap();
    let events: Vec<_> = (21..=108).map(|note| on(0, note)).collect();
    let mut output = [0.0; 128];
    engine.process_block(0, &events, &mut output).unwrap();
    assert_eq!(engine.active_voices(), MAX_VOICES);
    assert!(output
        .iter()
        .all(|sample| sample.is_finite() && sample.abs() <= 1.0));
    engine
        .process_block(128, &[off(128, 108)], &mut output)
        .unwrap();
    assert!(output.iter().any(|sample| *sample != 0.0));
    engine
        .process_block(
            256,
            &[PianoEvent {
                frame: 256,
                kind: PianoEventKind::Reset,
            }],
            &mut output,
        )
        .unwrap();
    assert_eq!(engine.active_voices(), 0);
    assert!(output.iter().all(|sample| *sample == 0.0));
}

#[test]
fn mixed_key_event_offsets_are_block_partition_invariant() {
    let events = [
        on(17, 21),
        on(47, 60),
        on(100, 108),
        off(233, 60),
        on(317, 64),
    ];
    let mut whole = [0.0; 512];
    BasicPianoEngine::new(48_000)
        .unwrap()
        .process_block(0, &events, &mut whole)
        .unwrap();
    for size in [64, 128, 256] {
        let mut engine = BasicPianoEngine::new(48_000).unwrap();
        let mut split = [0.0; 512];
        for (block, output) in split.chunks_mut(size).enumerate() {
            let start = (block * size) as u64;
            let first = events.partition_point(|event| event.frame < start);
            let last = events.partition_point(|event| event.frame < start + output.len() as u64);
            engine
                .process_block(start, &events[first..last], output)
                .unwrap();
        }
        assert_eq!(whole, split);
    }
}

#[test]
fn low_middle_and_high_keys_have_their_expected_fundamentals() {
    for note in [21_u8, 60, 108] {
        let mut engine = BasicPianoEngine::new(48_000).unwrap();
        let mut output = vec![0.0_f32; 48_000];
        for (block, chunk) in output.chunks_mut(256).enumerate() {
            let start = (block * 256) as u64;
            let events = if block == 0 { Some(on(0, note)) } else { None };
            engine
                .process_block(
                    start,
                    events.as_ref().map(std::slice::from_ref).unwrap_or(&[]),
                    chunk,
                )
                .unwrap();
        }
        let fundamental = 440.0 * 2.0_f64.powf((note as f64 - 69.0) / 12.0);
        let strength = |frequency: f64| {
            let mut real = 0.0;
            let mut imaginary = 0.0;
            for (index, sample) in output.iter().enumerate() {
                let window = (std::f64::consts::PI * index as f64 / output.len() as f64)
                    .sin()
                    .powi(2);
                let phase = 2.0 * std::f64::consts::PI * frequency * index as f64 / 48_000.0;
                real += *sample as f64 * window * phase.cos();
                imaginary += *sample as f64 * window * phase.sin();
            }
            real.hypot(imaginary)
        };
        let target = strength(fundamental);
        assert!(
            target > strength(fundamental * 2.0_f64.powf(-1.0 / 12.0)) * 2.0,
            "MIDI {note}: low neighbor"
        );
        assert!(
            target > strength(fundamental * 2.0_f64.powf(1.0 / 12.0)) * 2.0,
            "MIDI {note}: high neighbor"
        );
    }
}
