//! Development-only 32-key load measurement; not a dedicated-device baseline.
use std::hint::black_box;
use std::time::Instant;

use moonlight_dsp::{BasicPianoEngine, PianoEvent, PianoEventKind, MAX_VOICES};

fn percentile(sorted: &[f64], fraction: f64) -> f64 {
    sorted[((sorted.len() as f64 * fraction).ceil() as usize).clamp(1, sorted.len()) - 1]
}

fn main() {
    let blocks = std::env::args()
        .nth(1)
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(2048);
    assert!((16..=100_000).contains(&blocks));
    for rate in [44_100_u32, 48_000] {
        for frames in [64_usize, 128, 256, 512] {
            let mut engine = BasicPianoEngine::new(rate).unwrap();
            let mut output = vec![0.0_f32; frames];
            let mut ratios = Vec::with_capacity(blocks);
            let mut checksum = 0.0_f64;
            for block in 0..blocks + 256 {
                let start = (block * frames) as u64;
                let events: Vec<_> = if block % 128 == 0 {
                    (0..MAX_VOICES)
                        .map(|index| PianoEvent {
                            frame: start,
                            kind: PianoEventKind::NoteOn {
                                note: 36 + index as u8,
                                velocity: 0.8,
                            },
                        })
                        .collect()
                } else {
                    Vec::new()
                };
                let before = Instant::now();
                engine.process_block(start, &events, &mut output).unwrap();
                let elapsed = before.elapsed().as_secs_f64();
                black_box(&output);
                checksum += output[frames / 2] as f64;
                if block >= 256 {
                    ratios.push(elapsed * rate as f64 / frames as f64);
                }
            }
            ratios.sort_by(f64::total_cmp);
            let misses = ratios.iter().filter(|ratio| **ratio >= 1.0).count();
            println!("rate={rate} frames={frames} voices={} blocks={blocks} p50={:.4} p99={:.4} p99.99={:.4} max={:.4} misses={misses} checksum={checksum:.3}",
                engine.active_voices(), percentile(&ratios, 0.5), percentile(&ratios, 0.99), percentile(&ratios, 0.9999), ratios[blocks - 1]);
        }
    }
}
