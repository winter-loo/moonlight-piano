//! Host-side measurements; clocks, allocation and serialization stay outside DSP.
use std::env;
use std::fs;
use std::hint::black_box;
use std::path::PathBuf;
use std::process::Command;
use std::time::Instant;

use moonlight_dsp::{PianoEngine, PianoEvent, PianoEventKind};
use moonlight_model::parse_model_pack;

const MODEL: &str = include_str!("../../../fixtures/physical-c4/minimal-c4.mlpiano");
const WARMUP: usize = 256;

fn quote(value: &str) -> String {
    let mut output = String::from("\"");
    for ch in value.chars() {
        match ch {
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            ch if ch.is_control() => output.push_str(&format!("\\u{:04x}", ch as u32)),
            ch => output.push(ch),
        }
    }
    output.push('"');
    output
}

fn percentile(sorted: &[f64], quantile: f64) -> f64 {
    let rank = (quantile * sorted.len() as f64).ceil() as usize;
    sorted[rank.clamp(1, sorted.len()) - 1]
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut mode = String::from("smoke");
    let mut blocks = 2048_usize;
    let mut device = String::from("unidentified-host");
    let mut output_path = None;
    let mut seen = std::collections::HashSet::new();
    let mut args = env::args().skip(1);
    while let Some(key) = args.next() {
        if !seen.insert(key.clone()) {
            return Err(format!("duplicate option {key}").into());
        }
        let value = args.next().ok_or("each option requires a value")?;
        match key.as_str() {
            "--mode" => mode = value,
            "--blocks" => blocks = value.parse()?,
            "--device-id" => device = value,
            "--output" => output_path = Some(PathBuf::from(value)),
            _ => return Err(format!("unknown option {key}").into()),
        }
    }
    if !matches!(mode.as_str(), "smoke" | "dedicated") || !(16..=1_000_000).contains(&blocks) {
        return Err("mode must be smoke/dedicated; blocks must be 16..1000000".into());
    }
    if mode == "dedicated" && (blocks < 100_000 || device == "unidentified-host") {
        return Err("dedicated runs require >=100000 blocks and a --device-id".into());
    }
    let cpu = fs::read_to_string("/proc/cpuinfo")
        .ok()
        .and_then(|text| {
            text.lines()
                .find(|line| line.starts_with("model name"))
                .map(str::to_owned)
        })
        .unwrap_or_else(|| env::var("PROCESSOR_IDENTIFIER").unwrap_or_else(|_| device.clone()));
    let compiler = Command::new("rustc").arg("-Vv").output()?;
    if !compiler.status.success() {
        return Err("rustc metadata unavailable".into());
    }
    let compiler = String::from_utf8(compiler.stdout)?;
    let binary_bytes = fs::metadata(env::current_exe()?)?.len();
    let mut cases = Vec::new();
    for sample_rate in [44_100_u32, 48_000] {
        for block_size in [64_usize, 128, 256, 512] {
            let pack = parse_model_pack(MODEL, sample_rate)?;
            let mut engine = PianoEngine::new(&pack, sample_rate, 17)?;
            let mut samples = vec![0.0_f32; block_size];
            let mut ratios = vec![0.0_f64; blocks];
            let mut max_modes = 0;
            let mut checksum = 0_u64;
            for block in 0..WARMUP + blocks {
                let start = (block * block_size) as u64;
                // Bounded repeated attack/tail scene; keep real state active.
                let events = [
                    PianoEvent {
                        frame: start,
                        kind: PianoEventKind::Reset,
                    },
                    PianoEvent {
                        frame: start,
                        kind: PianoEventKind::NoteOn {
                            note: 60,
                            velocity: 0.4,
                        },
                    },
                ];
                let events = if block % 32 == 0 { &events[..] } else { &[] };
                let clock = Instant::now();
                let result =
                    engine.process_block(start, black_box(events), black_box(&mut samples));
                let elapsed = clock.elapsed().as_secs_f64();
                result?;
                // Ensure output remains observable without timing serialization.
                checksum = checksum.wrapping_add(black_box(samples[0]).to_bits() as u64);
                if block >= WARMUP {
                    ratios[block - WARMUP] = elapsed * sample_rate as f64 / block_size as f64;
                    max_modes = max_modes.max(engine.state_counts().active_modes);
                }
            }
            if ratios
                .iter()
                .any(|ratio| !ratio.is_finite() || *ratio < 0.0)
            {
                return Err("invalid clock observation".into());
            }
            ratios.sort_by(f64::total_cmp);
            let state = engine.state_counts();
            cases.push(format!(
                concat!(
                    "{{\"sampleRateHz\":{},\"blockFrames\":{},\"observations\":{},",
                    "\"p50\":{:.9},\"p99\":{:.9},\"p9999\":{:.9},\"max\":{:.9},",
                    "\"deadlineMisses\":{},\"activeModesPeak\":{},\"configuredModes\":{},",
                    "\"activeStrings\":{},\"stateBytes\":{},\"outputBytes\":{},",
                    "\"measurementBufferBytes\":{},\"checksum\":{}}}"
                ),
                sample_rate,
                block_size,
                blocks,
                percentile(&ratios, 0.5),
                percentile(&ratios, 0.99),
                percentile(&ratios, 0.9999),
                ratios[ratios.len() - 1],
                ratios.iter().filter(|ratio| **ratio >= 1.0).count(),
                max_modes,
                state.configured_modes,
                state.active_strings,
                state.state_bytes,
                samples.len() * std::mem::size_of::<f32>(),
                ratios.len() * std::mem::size_of::<f64>(),
                checksum,
            ));
        }
    }
    let report = format!(
        concat!(
            "{{\n\"schemaVersion\":1,\"mode\":{},\"deviceId\":{},",
            "\"cpu\":{},\"architecture\":{},\"os\":{},\"compiler\":{},",
            "\"kernel\":\"scalar-f64\",\"scene\":\"c4-restrike-tail-v1\",",
            "\"sourceRevision\":{},\"warmupBlocks\":{},\"binaryBytes\":{},",
            "\"modelBytes\":{},\"modelFingerprint\":{},\"tailResolutionSufficient\":{},",
            "\"timingIncludesClockOverhead\":true,\"thermalCertification\":false,",
            "\"cases\":[{}]\n}}\n"
        ),
        quote(&mode),
        quote(&device),
        quote(&cpu),
        quote(env::consts::ARCH),
        quote(env::consts::OS),
        quote(compiler.trim()),
        quote(&env::var("MOONLIGHT_SOURCE_REVISION").unwrap_or_else(|_| "unknown".into())),
        WARMUP,
        binary_bytes,
        MODEL.len(),
        quote(&format!("{:016x}", fingerprint(MODEL.as_bytes()))),
        blocks >= 100_000,
        cases.join(",\n"),
    );
    if let Some(path) = output_path {
        if let Some(parent) = path
            .parent()
            .filter(|parent| !parent.as_os_str().is_empty())
        {
            fs::create_dir_all(parent)?;
        }
        fs::write(path, &report)?;
    }
    print!("{report}");
    Ok(())
}

fn fingerprint(bytes: &[u8]) -> u64 {
    bytes.iter().fold(0xcbf29ce484222325_u64, |hash, byte| {
        (hash ^ *byte as u64).wrapping_mul(0x100000001b3)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nearest_rank_percentiles_use_real_observations() {
        let sorted = [0.1, 0.2, 0.3, 0.4];
        assert_eq!(percentile(&sorted, 0.5), 0.2);
        assert_eq!(percentile(&sorted, 0.99), 0.4);
        assert_eq!(percentile(&sorted, 0.9999), 0.4);
    }

    #[test]
    fn metadata_is_json_escaped() {
        assert_eq!(quote("a\n\"b"), "\"a\\u000a\\\"b\"");
    }
}
