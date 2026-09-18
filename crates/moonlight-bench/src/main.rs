use std::time::Instant;

use moonlight_dsp::{PianoEngine, PianoEvent, PianoEventKind};
use moonlight_model::parse_model_pack;

const MODEL: &str = include_str!("../../../fixtures/physical-c4/minimal-c4.mlpiano");

fn main() {
    let sample_rate = 48_000_u32;
    let block_size = 128_usize;
    let audio_seconds = 10.0_f64;
    let blocks = (audio_seconds * sample_rate as f64 / block_size as f64).ceil() as usize;
    let pack = parse_model_pack(MODEL, sample_rate).expect("fixture model must validate");
    let mut engine = PianoEngine::new(&pack, sample_rate, 1).expect("engine must initialize");
    let event = PianoEvent {
        frame: 0,
        kind: PianoEventKind::NoteOn {
            note: 60,
            velocity: 0.8,
        },
    };
    let mut output = vec![0.0_f32; block_size];
    let started = Instant::now();
    for block in 0..blocks {
        let events = if block == 0 {
            std::slice::from_ref(&event)
        } else {
            &[]
        };
        engine
            .process_block((block * block_size) as u64, events, &mut output)
            .expect("benchmark render must succeed");
    }
    let elapsed = started.elapsed().as_secs_f64();
    println!(
        "audio_seconds={audio_seconds:.3} render_seconds={elapsed:.6} realtime_ratio={:.6}",
        elapsed / audio_seconds
    );
}
