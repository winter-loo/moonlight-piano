//! Offline host, event parser, WAV writer, and deterministic acoustic report.

use std::error::Error;
use std::fmt::{Display, Formatter};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::Instant;

use moonlight_dsp::{PianoEngine, PianoEvent, PianoEventKind, ProcessError};
use moonlight_model::{parse_model_pack, ModelError};

#[derive(Debug, Clone, PartialEq)]
pub struct RenderConfig {
    pub sample_rate_hz: u32,
    pub block_size: usize,
    pub duration_seconds: f64,
    pub seed: u64,
    pub model_path: PathBuf,
    pub events_path: PathBuf,
    pub output_dir: PathBuf,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RenderMetrics {
    pub sample_rate_hz: u32,
    pub frames: usize,
    pub peak: f64,
    pub rms: f64,
    pub pcm_fnv1a64: u64,
}

#[derive(Debug)]
pub enum OfflineError {
    Io(std::io::Error),
    Model(ModelError),
    Process(ProcessError),
    InvalidArgument(String),
    InvalidEvent { line: usize, reason: String },
}

impl Display for OfflineError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{self:?}")
    }
}

impl Error for OfflineError {}

impl From<std::io::Error> for OfflineError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}

impl From<ModelError> for OfflineError {
    fn from(value: ModelError) -> Self {
        Self::Model(value)
    }
}

impl From<ProcessError> for OfflineError {
    fn from(value: ProcessError) -> Self {
        Self::Process(value)
    }
}

pub fn parse_events(input: &str, total_frames: u64) -> Result<Vec<PianoEvent>, OfflineError> {
    let mut result = Vec::new();
    let mut previous_frame = None;
    for (index, raw) in input.lines().enumerate() {
        let line_number = index + 1;
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let fields: Vec<&str> = line.split(',').map(str::trim).collect();
        if fields.len() != 4 {
            return Err(OfflineError::InvalidEvent {
                line: line_number,
                reason: "expected frame,type,note,value".to_owned(),
            });
        }
        let frame = fields[0]
            .parse::<u64>()
            .map_err(|_| OfflineError::InvalidEvent {
                line: line_number,
                reason: "invalid frame".to_owned(),
            })?;
        if frame >= total_frames {
            return Err(OfflineError::InvalidEvent {
                line: line_number,
                reason: "event lies outside render duration".to_owned(),
            });
        }
        if previous_frame.is_some_and(|previous| frame < previous) {
            return Err(OfflineError::InvalidEvent {
                line: line_number,
                reason: "events must be ordered by frame".to_owned(),
            });
        }
        previous_frame = Some(frame);
        let note = fields[2]
            .parse::<u8>()
            .map_err(|_| OfflineError::InvalidEvent {
                line: line_number,
                reason: "invalid MIDI note".to_owned(),
            })?;
        let value = fields[3]
            .parse::<f32>()
            .map_err(|_| OfflineError::InvalidEvent {
                line: line_number,
                reason: "invalid event value".to_owned(),
            })?;
        let kind = match fields[1] {
            "note_on" => PianoEventKind::NoteOn {
                note,
                velocity: value,
            },
            "note_off" => PianoEventKind::NoteOff {
                note,
                release_velocity: value,
            },
            other => {
                return Err(OfflineError::InvalidEvent {
                    line: line_number,
                    reason: format!("unsupported event type: {other}"),
                })
            }
        };
        result.push(PianoEvent { frame, kind });
    }
    if result.is_empty() {
        return Err(OfflineError::InvalidEvent {
            line: 0,
            reason: "at least one event is required".to_owned(),
        });
    }
    Ok(result)
}

pub fn render_to_files(config: &RenderConfig) -> Result<RenderMetrics, OfflineError> {
    validate_config(config)?;
    let model_text = fs::read_to_string(&config.model_path)?;
    let pack = parse_model_pack(&model_text, config.sample_rate_hz)?;
    let total_frames = (config.duration_seconds * config.sample_rate_hz as f64).round() as usize;
    if total_frames == 0 {
        return Err(OfflineError::InvalidArgument(
            "duration must render at least one sample frame".to_owned(),
        ));
    }
    let event_text = fs::read_to_string(&config.events_path)?;
    let events = parse_events(&event_text, total_frames as u64)?;
    let mut engine = PianoEngine::new(&pack, config.sample_rate_hz, config.seed)?;
    let mut samples = vec![0.0_f32; total_frames];
    let started = Instant::now();

    let mut frame = 0_usize;
    let mut event_cursor = 0_usize;
    while frame < total_frames {
        let end = (frame + config.block_size).min(total_frames);
        let first_event = event_cursor;
        while event_cursor < events.len() && events[event_cursor].frame < end as u64 {
            event_cursor += 1;
        }
        engine.process_block(
            frame as u64,
            &events[first_event..event_cursor],
            &mut samples[frame..end],
        )?;
        frame = end;
    }
    let elapsed = started.elapsed();

    fs::create_dir_all(&config.output_dir)?;
    let wav_path = config.output_dir.join("c4-reference.wav");
    let quantized = write_pcm16_wav(&wav_path, config.sample_rate_hz, &samples)?;
    let metrics = calculate_metrics(config.sample_rate_hz, &samples, &quantized);
    write_report(&config.output_dir.join("c4-report.json"), config, &pack.instrument_id, &metrics)?;
    write_energy_csv(
        &config.output_dir.join("c4-energy.csv"),
        config.sample_rate_hz,
        &samples,
    )?;
    write_timing_report(
        &config.output_dir.join("c4-timing.json"),
        &metrics,
        elapsed.as_secs_f64(),
    )?;
    Ok(metrics)
}

fn validate_config(config: &RenderConfig) -> Result<(), OfflineError> {
    if !(8_000..=384_000).contains(&config.sample_rate_hz) {
        return Err(OfflineError::InvalidArgument(
            "sample rate must be between 8000 and 384000 Hz".to_owned(),
        ));
    }
    if config.block_size == 0 || config.block_size > 16_384 {
        return Err(OfflineError::InvalidArgument(
            "block size must be between 1 and 16384 frames".to_owned(),
        ));
    }
    if !config.duration_seconds.is_finite()
        || config.duration_seconds <= 0.0
        || config.duration_seconds > 120.0
    {
        return Err(OfflineError::InvalidArgument(
            "duration must be finite and in (0, 120] seconds".to_owned(),
        ));
    }
    Ok(())
}

fn write_pcm16_wav(path: &Path, sample_rate_hz: u32, samples: &[f32]) -> Result<Vec<i16>, OfflineError> {
    let quantized: Vec<i16> = samples
        .iter()
        .map(|sample| (sample.clamp(-1.0, 1.0) * i16::MAX as f32).round() as i16)
        .collect();
    let data_bytes = (quantized.len() * 2) as u32;
    let mut file = fs::File::create(path)?;
    file.write_all(b"RIFF")?;
    file.write_all(&(36 + data_bytes).to_le_bytes())?;
    file.write_all(b"WAVEfmt ")?;
    file.write_all(&16_u32.to_le_bytes())?;
    file.write_all(&1_u16.to_le_bytes())?;
    file.write_all(&1_u16.to_le_bytes())?;
    file.write_all(&sample_rate_hz.to_le_bytes())?;
    file.write_all(&(sample_rate_hz * 2).to_le_bytes())?;
    file.write_all(&2_u16.to_le_bytes())?;
    file.write_all(&16_u16.to_le_bytes())?;
    file.write_all(b"data")?;
    file.write_all(&data_bytes.to_le_bytes())?;
    for sample in &quantized {
        file.write_all(&sample.to_le_bytes())?;
    }
    Ok(quantized)
}

fn calculate_metrics(sample_rate_hz: u32, samples: &[f32], quantized: &[i16]) -> RenderMetrics {
    let peak = samples
        .iter()
        .map(|sample| sample.abs() as f64)
        .fold(0.0, f64::max);
    let mean_square = samples
        .iter()
        .map(|sample| {
            let sample = *sample as f64;
            sample * sample
        })
        .sum::<f64>()
        / samples.len() as f64;
    let mut hash = 0xcbf29ce484222325_u64;
    for sample in quantized {
        for byte in sample.to_le_bytes() {
            hash ^= byte as u64;
            hash = hash.wrapping_mul(0x100000001b3);
        }
    }
    RenderMetrics {
        sample_rate_hz,
        frames: samples.len(),
        peak,
        rms: mean_square.sqrt(),
        pcm_fnv1a64: hash,
    }
}

fn write_report(
    path: &Path,
    config: &RenderConfig,
    instrument_id: &str,
    metrics: &RenderMetrics,
) -> Result<(), OfflineError> {
    let json = format!(
        concat!(
            "{{\n",
            "  \"schemaVersion\": 1,\n",
            "  \"instrumentId\": \"{}\",\n",
            "  \"sampleRateHz\": {},\n",
            "  \"blockSize\": {},\n",
            "  \"requestedDurationSeconds\": {:.9},\n",
            "  \"renderedDurationSeconds\": {:.9},\n",
            "  \"seed\": {},\n",
            "  \"frames\": {},\n",
            "  \"peak\": {:.12},\n",
            "  \"rms\": {:.12},\n",
            "  \"pcmFnv1a64\": \"{:016x}\"\n",
            "}}\n"
        ),
        escape_json(instrument_id),
        metrics.sample_rate_hz,
        config.block_size,
        config.duration_seconds,
        rendered_audio_seconds(metrics.frames, metrics.sample_rate_hz),
        config.seed,
        metrics.frames,
        metrics.peak,
        metrics.rms,
        metrics.pcm_fnv1a64,
    );
    fs::write(path, json)?;
    Ok(())
}

fn write_energy_csv(path: &Path, sample_rate_hz: u32, samples: &[f32]) -> Result<(), OfflineError> {
    let window_frames = (sample_rate_hz as usize / 10).max(1);
    let mut output = String::from("time_seconds,rms,dbfs\n");
    for (index, window) in samples.chunks(window_frames).enumerate() {
        let mean_square = window
            .iter()
            .map(|sample| {
                let value = *sample as f64;
                value * value
            })
            .sum::<f64>()
            / window.len() as f64;
        let rms = mean_square.sqrt();
        let dbfs = if rms > 0.0 {
            20.0 * rms.log10()
        } else {
            -300.0
        };
        output.push_str(&format!(
            "{:.6},{:.12},{:.6}\n",
            index as f64 * window_frames as f64 / sample_rate_hz as f64,
            rms,
            dbfs
        ));
    }
    fs::write(path, output)?;
    Ok(())
}

fn rendered_audio_seconds(frames: usize, sample_rate_hz: u32) -> f64 {
    frames as f64 / sample_rate_hz as f64
}

fn write_timing_report(
    path: &Path,
    metrics: &RenderMetrics,
    render_seconds: f64,
) -> Result<(), OfflineError> {
    let audio_seconds = rendered_audio_seconds(metrics.frames, metrics.sample_rate_hz);
    let realtime_ratio = render_seconds / audio_seconds;
    let json = format!(
        concat!(
            "{{\n",
            "  \"schemaVersion\": 1,\n",
            "  \"renderSeconds\": {:.9},\n",
            "  \"audioSeconds\": {:.9},\n",
            "  \"realtimeRatio\": {:.9}\n",
            "}}\n"
        ),
        render_seconds, audio_seconds, realtime_ratio
    );
    fs::write(path, json)?;
    Ok(())
}

fn escape_json(value: &str) -> String {
    value.replace('\\', "\\\\").replace('"', "\\\"")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_timestamped_events() {
        let events = parse_events("0,note_on,60,0.8\n48000,note_off,60,0.5\n", 96_000)
            .unwrap();
        assert_eq!(events.len(), 2);
        assert_eq!(events[1].frame, 48_000);
    }

    #[test]
    fn rendered_audio_duration_comes_from_frames() {
        assert_eq!(rendered_audio_seconds(1, 8_000), 0.000125);
        assert_eq!(rendered_audio_seconds(288_000, 48_000), 6.0);
    }

    #[test]
    fn rejects_out_of_range_and_unordered_events() {
        assert!(parse_events("100,note_on,60,0.8\n", 100).is_err());
        assert!(parse_events(
            "10,note_on,60,0.8\n5,note_off,60,0.5\n",
            100
        )
        .is_err());
    }
}
