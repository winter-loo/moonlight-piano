//! Deterministic listening/regression fixture renderer for the analytic piano.
//! CSV: frame,on|off|sustain|reset,note,value (frames at the chosen sample rate).
use std::error::Error;
use std::fs::File;
use std::io::Write;

use moonlight_dsp::{BasicPianoEngine, PianoEvent, PianoEventKind};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 5 {
        return Err("usage: basic_render EVENTS.csv OUTPUT.wav SECONDS SAMPLE_RATE".into());
    }
    let rate: u32 = args[4].parse()?;
    let seconds: f64 = args[3].parse()?;
    if !seconds.is_finite() || seconds <= 0.0 || seconds > 600.0 {
        return Err("duration must be finite, positive and at most 600 seconds".into());
    }
    let mut events = Vec::new();
    for line in std::fs::read_to_string(&args[1])?.lines() {
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let fields: Vec<_> = line.split(',').collect();
        if fields.len() != 4 {
            return Err(format!("invalid event: {line}").into());
        }
        let note = fields[2].parse()?;
        let value = fields[3].parse()?;
        let kind = match fields[1] {
            "on" => PianoEventKind::NoteOn {
                note,
                velocity: value,
            },
            "off" => PianoEventKind::NoteOff {
                note,
                release_velocity: value,
            },
            "sustain" => PianoEventKind::Sustain { position: value },
            "reset" => PianoEventKind::Reset,
            _ => return Err(format!("unknown event: {line}").into()),
        };
        events.push(PianoEvent {
            frame: fields[0].parse()?,
            kind,
        });
    }
    if events.windows(2).any(|pair| pair[0].frame > pair[1].frame) {
        return Err("events must be ordered by frame".into());
    }
    let frames = (seconds * rate as f64).round() as usize;
    if events
        .last()
        .is_some_and(|event| event.frame >= frames as u64)
    {
        return Err("event lies beyond output duration".into());
    }
    let mut engine = BasicPianoEngine::new(rate).map_err(|error| format!("{error:?}"))?;
    let mut left = [0.0; 256];
    let mut right = [0.0; 256];
    let mut pcm = Vec::with_capacity(frames * 4);
    let mut peak = 0.0_f32;
    let mut energy = 0.0_f64;
    for start in (0..frames).step_by(256) {
        let count = (frames - start).min(256);
        let first = events.partition_point(|event| event.frame < start as u64);
        let last = events.partition_point(|event| event.frame < (start + count) as u64);
        engine
            .process_stereo_block(
                start as u64,
                &events[first..last],
                &mut left[..count],
                &mut right[..count],
            )
            .map_err(|error| format!("{error:?}"))?;
        for (l, r) in left[..count].iter().zip(&right[..count]) {
            for sample in [*l, *r] {
                peak = peak.max(sample.abs());
                energy += f64::from(sample).powi(2);
                pcm.extend_from_slice(
                    &((sample.clamp(-1.0, 1.0) * 32767.0).round() as i16).to_le_bytes(),
                );
            }
        }
    }
    let size = pcm.len() as u32;
    let mut file = File::create(&args[2])?;
    file.write_all(b"RIFF")?;
    file.write_all(&(36 + size).to_le_bytes())?;
    file.write_all(b"WAVEfmt ")?;
    file.write_all(&16_u32.to_le_bytes())?;
    file.write_all(&1_u16.to_le_bytes())?;
    file.write_all(&2_u16.to_le_bytes())?;
    file.write_all(&rate.to_le_bytes())?;
    file.write_all(&(rate * 4).to_le_bytes())?;
    file.write_all(&4_u16.to_le_bytes())?;
    file.write_all(&16_u16.to_le_bytes())?;
    file.write_all(b"data")?;
    file.write_all(&size.to_le_bytes())?;
    file.write_all(&pcm)?;
    println!(
        "frames={frames} rate={rate} peak={peak:.6} rms={:.6}",
        (energy / (frames * 2) as f64).sqrt()
    );
    Ok(())
}
