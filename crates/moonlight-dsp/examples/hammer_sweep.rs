//! Reproducible, offline-only C4 hammer evidence. No PCM is used by the engine.
//!
//! `hammer_sweep OUTPUT_DIR RATE` writes all 127 MIDI velocities from silence,
//! identical C4 listening gestures for the accepted basic engine and candidate,
//! and scalar hammer diagnostics. Raw output is little-endian f32, before any
//! export normalization. `--parity OUTPUT.f32le RATE BLOCK` emits a short event
//! fixture for comparing the native core with the actual production WASM.

use std::error::Error;
use std::fs::{self, File};
use std::io::Write;
use std::path::Path;

use moonlight_dsp::{BasicPianoEngine, PianoEngine, PianoEvent, PianoEventKind};
use moonlight_model::parse_model_pack;

const MODEL: &str = include_str!("../../../fixtures/physical-c4/minimal-c4.mlpiano");
const SEED: u64 = 0x85a3_08d3_243f_6a88;
const VELOCITIES: [u8; 8] = [8, 24, 40, 56, 72, 88, 104, 127];

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() == 4 && args[1] == "--reference" {
        let rate: u32 = args[3].parse()?;
        if ![44_100, 48_000, 176_400, 192_000].contains(&rate) {
            return Err("reference rate must be 44100, 48000, 176400 or 192000".into());
        }
        let path = Path::new(&args[2]);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let pack = parse_model_pack(MODEL, rate)?;
        let mut engine = PianoEngine::new(&pack, rate, SEED)?;
        let mut samples = vec![0.0; rate as usize / 2];
        process_hammer(&mut engine, &[on(0, 1.0)], &mut samples, 128)?;
        write_f32(path, &samples)?;
        let d = engine.hammer_diagnostics();
        fs::write(path.with_extension("json"), format!(
            "{{\"sample_rate_hz\":{rate},\"velocity\":1,\"contact_seconds\":{:.12},\"peak_force_newtons\":{:.12},\"max_energy_error_joules\":{:.17e}}}\n",
            d.contact_seconds, d.peak_force_newtons, d.max_energy_error_joules))?;
        return Ok(());
    }
    if args.len() == 5 && args[1] == "--parity" {
        let rate = valid_rate(&args[3])?;
        let block: usize = args[4].parse()?;
        if block == 0 || block > moonlight_dsp::MAX_BLOCK_FRAMES {
            return Err("invalid parity block size".into());
        }
        let path = Path::new(&args[2]);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let events = parity_events(rate);
        let samples = render_parity(
            rate,
            block,
            &events,
            &path.with_extension("diagnostics.csv"),
        )?;
        write_f32(path, &samples)?;
        write_events(&path.with_extension("events.csv"), &events)?;
        return Ok(());
    }
    if args.len() != 3 {
        return Err(
            "usage: hammer_sweep OUTPUT_DIR RATE | --parity OUTPUT.f32le RATE BLOCK | --reference OUTPUT.f32le RATE".into(),
        );
    }
    let output = Path::new(&args[1]);
    let rate = valid_rate(&args[2])?;
    fs::create_dir_all(output)?;
    let pack = parse_model_pack(MODEL, rate)?;
    let mut diagnostics = File::create(output.join("hammer-diagnostics.csv"))?;
    writeln!(diagnostics, "midi_velocity,velocity,initial_velocity_mps,peak_force_newtons,peak_compression_meters,contact_seconds,contact_count,input_energy_joules,total_energy_joules,dissipated_energy_joules,max_energy_error_joules")?;

    // A fresh physical state makes adjacent velocities directly comparable.
    let sweep_frames = rate as usize / 2;
    for midi in 1..=127_u8 {
        let velocity = f32::from(midi) / 127.0;
        let mut engine = PianoEngine::new(&pack, rate, SEED)?;
        let mut samples = vec![0.0; sweep_frames];
        let events = [on(0, velocity)];
        process_hammer(&mut engine, &events, &mut samples, 128)?;
        write_f32(&output.join(format!("velocity-{midi:03}.f32le")), &samples)?;
        let d = engine.hammer_diagnostics();
        writeln!(
            diagnostics,
            "{midi},{velocity:.9},{:.12},{:.12},{:.12},{:.12},{},{:.15},{:.15},{:.15},{:.15}",
            d.initial_velocity_mps,
            d.peak_force_newtons,
            d.peak_compression_meters,
            d.contact_seconds,
            d.contact_count,
            d.input_energy_joules,
            d.total_energy_joules,
            d.dissipated_energy_joules,
            d.max_energy_error_joules
        )?;
    }

    let events = listening_events(rate);
    let frames = 16 * rate as usize;
    let candidate = render_hammer(rate, 128, frames, &events)?;
    let baseline = render_basic_mono(rate, frames, &events)?;
    write_f32(&output.join("hammer-listen.f32le"), &candidate)?;
    write_f32(&output.join("basic-listen.f32le"), &baseline)?;
    write_events(&output.join("listen.events.csv"), &events)?;
    println!("rendered 127 velocities and two identical 16-second C4 sequences at {rate} Hz");
    Ok(())
}

fn valid_rate(input: &str) -> Result<u32, Box<dyn Error>> {
    let rate: u32 = input.parse()?;
    if ![44_100, 48_000].contains(&rate) {
        return Err("evidence sample rate must be 44100 or 48000".into());
    }
    Ok(rate)
}

fn on(frame: u64, velocity: f32) -> PianoEvent {
    PianoEvent {
        frame,
        kind: PianoEventKind::NoteOn { note: 60, velocity },
    }
}

fn off(frame: u64) -> PianoEvent {
    PianoEvent {
        frame,
        kind: PianoEventKind::NoteOff {
            note: 60,
            release_velocity: 0.5,
        },
    }
}

fn reset(frame: u64) -> PianoEvent {
    PianoEvent {
        frame,
        kind: PianoEventKind::Reset,
    }
}

fn parity_events(rate: u32) -> Vec<PianoEvent> {
    vec![
        on(17, 0.12),
        off(31),
        on(83, 0.4),
        on(u64::from(rate) / 20 + 7, 1.0),
        off(u64::from(rate) / 10 + 3),
        reset(u64::from(rate) / 6 + 1),
        on(u64::from(rate) / 5 + 9, 0.75),
        off(u64::from(rate) / 3 + 11),
        reset(u64::from(rate) * 9 / 20),
    ]
}

fn listening_events(rate: u32) -> Vec<PianoEvent> {
    let mut events = Vec::new();
    for (index, velocity) in VELOCITIES.into_iter().enumerate() {
        let start = ((0.15 + 1.5 * index as f64) * f64::from(rate)).round() as u64;
        events.push(reset(start - 1));
        events.push(on(start, f32::from(velocity) / 127.0));
        // Hold until the next explicit reset. Basic and C4 currently have
        // different release implementations; do not let that obscure dynamics.
    }
    // Separately labeled release/repeat probe: these paths are not yet matched
    // physically (C4 continuous damper/key action belongs to the next issues).
    let start = u64::from(rate) * 13;
    events.push(reset(start - 1));
    for index in 0..3 {
        let frame = start + index * u64::from(rate) / 3;
        events.push(on(frame, 0.6));
        events.push(off(frame + u64::from(rate) / 5));
    }
    events
}

fn render_hammer(
    rate: u32,
    block: usize,
    frames: usize,
    events: &[PianoEvent],
) -> Result<Vec<f32>, Box<dyn Error>> {
    let pack = parse_model_pack(MODEL, rate)?;
    let mut engine = PianoEngine::new(&pack, rate, SEED)?;
    let mut samples = vec![0.0; frames];
    process_hammer(&mut engine, events, &mut samples, block)?;
    Ok(samples)
}

fn render_parity(
    rate: u32,
    block: usize,
    events: &[PianoEvent],
    diagnostics_path: &Path,
) -> Result<Vec<f32>, Box<dyn Error>> {
    let pack = parse_model_pack(MODEL, rate)?;
    let mut engine = PianoEngine::new(&pack, rate, SEED)?;
    let mut samples = vec![0.0; rate as usize / 2];
    let mut diagnostics = File::create(diagnostics_path)?;
    for start in (0..samples.len()).step_by(block) {
        let end = (start + block).min(samples.len());
        let first = events.partition_point(|event| event.frame < start as u64);
        let last = events.partition_point(|event| event.frame < end as u64);
        engine.process_block(start as u64, &events[first..last], &mut samples[start..end])?;
        let d = engine.hammer_diagnostics();
        let values = [
            d.force_newtons,
            d.peak_force_newtons,
            d.compression_meters,
            d.peak_compression_meters,
            d.initial_velocity_mps,
            d.hammer_velocity_mps,
            d.contact_seconds,
            d.hammer_energy_joules,
            d.string_energy_joules,
            d.total_energy_joules,
            d.dissipated_energy_joules,
            d.input_energy_joules,
            d.max_energy_error_joules,
            d.contact_count as f64,
            if d.in_contact { 1.0 } else { 0.0 },
        ];
        write!(diagnostics, "{end}")?;
        for value in values {
            write!(diagnostics, ",{value:.17e}")?;
        }
        writeln!(diagnostics)?;
    }
    Ok(samples)
}

fn process_hammer(
    engine: &mut PianoEngine,
    events: &[PianoEvent],
    samples: &mut [f32],
    block: usize,
) -> Result<(), Box<dyn Error>> {
    for start in (0..samples.len()).step_by(block) {
        let end = (start + block).min(samples.len());
        let first = events.partition_point(|event| event.frame < start as u64);
        let last = events.partition_point(|event| event.frame < end as u64);
        engine.process_block(start as u64, &events[first..last], &mut samples[start..end])?;
    }
    Ok(())
}

fn render_basic_mono(
    rate: u32,
    frames: usize,
    events: &[PianoEvent],
) -> Result<Vec<f32>, Box<dyn Error>> {
    let mut engine = BasicPianoEngine::new(rate).map_err(|error| format!("{error:?}"))?;
    let mut samples = Vec::with_capacity(frames);
    let mut left = [0.0; 128];
    let mut right = [0.0; 128];
    for start in (0..frames).step_by(128) {
        let count = (frames - start).min(128);
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
        samples.extend(
            left[..count]
                .iter()
                .zip(&right[..count])
                .map(|(l, r)| 0.5 * (l + r)),
        );
    }
    Ok(samples)
}

fn write_f32(path: &Path, samples: &[f32]) -> Result<(), Box<dyn Error>> {
    let mut file = File::create(path)?;
    for sample in samples {
        if !sample.is_finite() {
            return Err("nonfinite PCM in evidence render".into());
        }
        file.write_all(&sample.to_le_bytes())?;
    }
    Ok(())
}

fn write_events(path: &Path, events: &[PianoEvent]) -> Result<(), Box<dyn Error>> {
    let mut file = File::create(path)?;
    writeln!(file, "# frame,kind,note,value; kind 1=on, 2=off, 3=reset")?;
    for event in events {
        let (kind, note, value) = match event.kind {
            PianoEventKind::NoteOn { note, velocity } => (1, note, velocity),
            PianoEventKind::NoteOff {
                note,
                release_velocity,
            } => (2, note, release_velocity),
            PianoEventKind::Reset => (3, 60, 0.0),
            PianoEventKind::Sustain { .. } => return Err("unexpected sustain in C4 fixture".into()),
        };
        writeln!(file, "{},{kind},{note},{value:.9}", event.frame)?;
    }
    Ok(())
}
