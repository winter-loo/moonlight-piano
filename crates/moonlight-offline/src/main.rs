use std::env;
use std::path::PathBuf;
use std::process::ExitCode;

use moonlight_offline::{render_to_files, RenderConfig};

fn main() -> ExitCode {
    match parse_args(env::args().skip(1).collect()).and_then(|config| {
        let metrics = render_to_files(&config)?;
        println!(
            "rendered {} frames at {} Hz; peak={:.6}, rms={:.6}, pcm-fnv1a64={:016x}",
            metrics.frames, metrics.sample_rate_hz, metrics.peak, metrics.rms, metrics.pcm_fnv1a64
        );
        Ok(())
    }) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("moonlight-render: {error}");
            ExitCode::FAILURE
        }
    }
}

fn parse_args(arguments: Vec<String>) -> Result<RenderConfig, moonlight_offline::OfflineError> {
    let mut sample_rate_hz = 48_000_u32;
    let mut block_size = 128_usize;
    let mut duration_seconds = 6.0_f64;
    let mut seed = 0x4d4f4f4e_u64;
    let mut model_path = None;
    let mut events_path = None;
    let mut output_dir = None;
    let mut index = 0;
    while index < arguments.len() {
        let key = &arguments[index];
        index += 1;
        let value = arguments.get(index).ok_or_else(|| {
            moonlight_offline::OfflineError::InvalidArgument(format!("missing value for {key}"))
        })?;
        index += 1;
        match key.as_str() {
            "--sample-rate" => {
                sample_rate_hz = value.parse().map_err(|_| {
                    moonlight_offline::OfflineError::InvalidArgument(
                        "invalid --sample-rate".to_owned(),
                    )
                })?
            }
            "--block-size" => {
                block_size = value.parse().map_err(|_| {
                    moonlight_offline::OfflineError::InvalidArgument(
                        "invalid --block-size".to_owned(),
                    )
                })?
            }
            "--duration" => {
                duration_seconds = value.parse().map_err(|_| {
                    moonlight_offline::OfflineError::InvalidArgument(
                        "invalid --duration".to_owned(),
                    )
                })?
            }
            "--seed" => {
                seed = value.parse().map_err(|_| {
                    moonlight_offline::OfflineError::InvalidArgument("invalid --seed".to_owned())
                })?
            }
            "--model" => model_path = Some(PathBuf::from(value)),
            "--events" => events_path = Some(PathBuf::from(value)),
            "--output-dir" => output_dir = Some(PathBuf::from(value)),
            _ => {
                return Err(moonlight_offline::OfflineError::InvalidArgument(format!(
                    "unknown argument: {key}"
                )))
            }
        }
    }
    Ok(RenderConfig {
        sample_rate_hz,
        block_size,
        duration_seconds,
        seed,
        model_path: model_path.ok_or_else(|| {
            moonlight_offline::OfflineError::InvalidArgument("--model is required".to_owned())
        })?,
        events_path: events_path.ok_or_else(|| {
            moonlight_offline::OfflineError::InvalidArgument("--events is required".to_owned())
        })?,
        output_dir: output_dir.ok_or_else(|| {
            moonlight_offline::OfflineError::InvalidArgument("--output-dir is required".to_owned())
        })?,
    })
}
