#!/usr/bin/env python3
"""Measure the uncalibrated C4 hammer candidate and export listening comparisons.

The Rust example renders the production core. Analysis uses only synthetic PCM;
no reference recording or sealed holdout is read. The A/B uses identical C4
events, sums the accepted basic engine to mono, and applies one constant scalar
gain to each complete segment. It is RMS matching, not perceptual loudness/LUFS.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[1]
LISTEN_SECONDS = 16
LISTEN_VELOCITIES = [8, 24, 40, 56, 72, 88, 104, 127]
ACCEPTED_BASIC_SHA256 = "1d520b0ed200361c6f30d0dee19fca8bbf8df4d462e17c13838221d172e89fc7"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rms(signal):
    return float(np.sqrt(np.mean(signal * signal)))


def read_pcm(path, expected_frames):
    signal = np.fromfile(path, dtype="<f4").astype(np.float64)
    if len(signal) != expected_frames or not np.all(np.isfinite(signal)):
        raise ValueError(f"Invalid float PCM: {path}")
    return signal


def features(signal, rate, partials):
    level = rms(signal)
    if level == 0:
        raise ValueError("Velocity sweep produced a silent note")
    # Fixed acoustic window for every velocity; no onset-dependent selection.
    held = signal[round(.02 * rate):round(.4 * rate)]
    spectrum = np.abs(np.fft.rfft(held * np.hanning(len(held)), n=65536))
    frequencies = np.fft.rfftfreq(65536, 1 / rate)
    power = spectrum * spectrum
    centroid = float(np.dot(frequencies, spectrum) / np.sum(spectrum))
    energies = [float(np.sum(power[np.abs(frequencies - frequency) <= 8]))
                for frequency in partials if frequency < rate / 2]
    total_partial = sum(energies)
    normalized = [energy / total_partial for energy in energies]
    attack = signal[:round(.05 * rate)]
    window = max(1, round(.001 * rate))
    squared = np.r_[np.zeros(window), np.cumsum(attack * attack)]
    envelope = np.sqrt((squared[window:] - squared[:-window]) / window)
    peak = float(np.max(envelope))
    t10 = int(np.flatnonzero(envelope >= peak * .1)[0]) / rate
    t90 = int(np.flatnonzero(envelope >= peak * .9)[0]) / rate
    return {
        "peak": float(np.max(np.abs(signal))),
        "rms": level,
        "rms_dbfs": float(20 * np.log10(level)),
        "attack_10_90_ms": 1000 * (t90 - t10),
        "attack_10_ms": 1000 * t10,
        "attack_90_ms": 1000 * t90,
        "spectral_centroid_hz": centroid,
        "partial_energy_fractions": normalized,
        "first_partial_energy_fraction": normalized[0],
        "late_to_early_rms_ratio": rms(signal[round(.3 * rate):]) / rms(signal[round(.03 * rate):round(.13 * rate)]),
    }


def write_pcm16(path, rate, signal):
    if not np.all(np.isfinite(signal)) or np.max(np.abs(signal)) >= 1:
        raise ValueError(f"Refusing clipped/nonfinite listening export: {path}")
    wavfile.write(path, rate, np.rint(signal * 32767).astype(np.int16))


def listen_exports(output, rate):
    audio = {name: read_pcm(output / f"{name}-listen.f32le", LISTEN_SECONDS * rate)
             for name in ["basic", "hammer"]}
    result = {}
    for name, signal in audio.items():
        peak = float(np.max(np.abs(signal)))
        # Keep raw output independently inspectable even if a candidate overloads.
        wavfile.write(output / f"{name}-raw-float.wav", rate, signal.astype(np.float32))
        result[name] = {"raw_peak": peak, "raw_rms": rms(signal),
                        "raw_sha256": sha256(output / f"{name}-listen.f32le")}

    # A common gain preserves the actual dynamic relationship between engines.
    common_gain = min(1.0, .9 / max(result[name]["raw_peak"] for name in result))
    raw = np.concatenate([audio["basic"] * common_gain, np.zeros(rate), audio["hammer"] * common_gain])
    write_pcm16(output / "c4-hammer-raw-comparison.wav", rate, raw)

    crest = max(result[name]["raw_peak"] / result[name]["raw_rms"] for name in result)
    target = min(.08, .9 / crest)
    parts = []
    for name, signal in audio.items():
        gain = target / result[name]["raw_rms"]
        result[name]["matched_gain_db"] = float(20 * np.log10(gain))
        parts.append(signal * gain)
    matched = np.concatenate([parts[0], np.zeros(rate), parts[1]])
    write_pcm16(output / "c4-hammer-rms-matched-ab.wav", rate, matched)
    # Candidate by itself retains its velocity dynamics; this is one gain total.
    write_pcm16(output / "c4-hammer-candidate.wav", rate, parts[1])
    return {
        "basic_seconds": [0, 16], "hammer_seconds": [17, 33],
        "velocities": LISTEN_VELOCITIES,
        "strike_seconds_within_each_segment": [round(.15 + 1.5 * i, 2) for i in range(8)],
        "repeated_velocity": .6, "repeated_strike_seconds": [13, 13 + 1 / 3, 13 + 2 / 3],
        "raw_comparison_common_gain": common_gain,
        "matching": "one constant RMS gain per entire 16-second segment; preserves within-segment dynamics; no EQ/denoising/limiter/resampling",
        "channel_policy": "C4 candidate mono; accepted BasicPianoEngine stereo averaged to mono for comparison",
        "renders": result,
    }


def analyze_rate(output, rate, partials):
    rows = list(csv.DictReader((output / "hammer-diagnostics.csv").open()))
    if len(rows) != 127:
        raise ValueError("Expected 127 velocity diagnostics")
    metrics = []
    for midi, row in enumerate(rows, 1):
        if int(row["midi_velocity"]) != midi:
            raise ValueError("Unordered velocity diagnostics")
        path = output / f"velocity-{midi:03}.f32le"
        signal = read_pcm(path, rate // 2)
        metrics.append({"midi_velocity": midi, "pcm_sha256": sha256(path),
                        **features(signal, rate, partials),
                        "hammer": {key: float(value) for key, value in row.items() if key != "midi_velocity"}})
    low = read_pcm(output / "velocity-024.f32le", rate // 2)
    high = read_pcm(output / "velocity-104.f32le", rate // 2)
    gain = float(np.dot(low, high) / np.dot(low, low))
    residual = rms(high - gain * low) / rms(high)
    levels = np.array([item["rms_dbfs"] for item in metrics])
    centroids = np.array([item["spectral_centroid_hz"] for item in metrics])
    shapes = np.array([item["partial_energy_fractions"] for item in metrics])
    summary = {
        "rms_strictly_increases": bool(np.all(np.diff(levels) > 0)),
        "rms_dynamic_range_db": float(levels[-1] - levels[0]),
        "largest_adjacent_rms_change_db": float(np.max(np.abs(np.diff(levels)))),
        "minimum_adjacent_rms_change_db": float(np.min(np.diff(levels))),
        "centroid_soft_hz": float(centroids[0]),
        "centroid_loud_hz": float(centroids[-1]),
        "largest_adjacent_centroid_change_hz": float(np.max(np.abs(np.diff(centroids)))),
        "largest_adjacent_centroid_change_fraction": float(np.max(np.abs(np.diff(centroids)) / centroids[:-1])),
        "largest_adjacent_partial_distribution_l1_change": float(np.max(np.sum(np.abs(np.diff(shapes, axis=0)), axis=1))),
        "weak_strong_best_scalar_gain": gain,
        "weak_strong_scalar_fit_relative_rms_residual": residual,
        "maximum_pcm_peak": max(item["peak"] for item in metrics),
        "maximum_absolute_energy_ledger_residual_joules": max(item["hammer"]["max_energy_error_joules"] for item in metrics),
        "weak_strong_velocities": [24, 104],
    }
    # Gate only properties claimed by this milestone. Real-piano likeness and
    # professional acceptance cannot be inferred from these synthetic metrics.
    checks = {
        "all_pcm_finite_and_nonzero": True,
        "rms_strictly_increases": summary["rms_strictly_increases"],
        # Candidate uses the stricter numeric velocity-continuity targets from
        # the product spec; these still do not establish real-piano calibration.
        "adjacent_midi_level_step_at_most_0_5db": summary["largest_adjacent_rms_change_db"] <= .5,
        "adjacent_midi_centroid_change_at_most_3percent": summary["largest_adjacent_centroid_change_fraction"] <= .03,
        "weak_strong_are_not_one_scaled_waveform": residual > .01,
        "loud_spectrum_is_brighter_than_soft": bool(centroids[-1] > centroids[0]),
        "ordinary_single_c4_does_not_clip": summary["maximum_pcm_peak"] < 1,
        "contact_force_is_positive": all(item["hammer"]["peak_force_newtons"] > 0 for item in metrics),
    }
    return {"sample_rate_hz": rate, "frames_per_velocity": rate // 2,
            "summary": summary, "checks": checks, "velocities": metrics,
            "listening": listen_exports(output, rate)}


def convergence(output, rate, partials, renderer, skip_render):
    high_rate = rate * 4
    reference_path = output / f"reference-{high_rate}.f32le"
    if not skip_render:
        subprocess.run([str(renderer), "--reference", str(reference_path), str(high_rate)], cwd=ROOT, check=True)
    high = read_pcm(reference_path, high_rate // 2)
    native = read_pcm(output / "velocity-127.f32le", rate // 2)
    # Rust emits the end-of-sample state. Prepend the exact rest state at t=0,
    # lowpass then decimate, and drop that t=0 sample to align physical times.
    reference = resample_poly(np.r_[0.0, high], 1, 4, window=("kaiser", 8.6))[1:len(native) + 1]
    if len(reference) != len(native):
        raise ValueError("Reference resampling changed the expected time span")
    compared = slice(0, round(.4 * rate))  # avoid end-padding effects
    direct = native[compared]
    target = reference[compared]
    gain = float(np.dot(direct, target) / np.dot(target, target))
    direct_features = features(native, rate, partials)
    reference_features = features(reference, rate, partials)
    high_diagnostics = json.loads(reference_path.with_suffix(".json").read_text())
    raw_diagnostics = list(csv.DictReader((output / "hammer-diagnostics.csv").open()))[-1]
    return {
        "native_sample_rate_hz": rate,
        "reference_sample_rate_hz": high_rate,
        "reference_pcm_sha256": sha256(reference_path),
        "event": "one C4 velocity-1 strike at t=0, held for 0.5 seconds",
        "resampling": "scipy.signal.resample_poly, down=4, Kaiser beta=8.6; exact rest sample prepended for end-of-sample time alignment",
        "comparison_window_seconds": [0, .4],
        "relative_rms_waveform_error": rms(direct - target) / rms(target),
        "relative_rms_attack_error_first_20ms": rms((native - reference)[:round(.02 * rate)]) / rms(reference[:round(.02 * rate)]),
        "relative_rms_held_error_20_to_400ms": rms((native - reference)[round(.02 * rate):round(.4 * rate)]) / rms(reference[round(.02 * rate):round(.4 * rate)]),
        "best_reference_scalar_gain": gain,
        "scalar_adjusted_relative_rms_error": rms(direct - gain * target) / rms(direct),
        "native_centroid_hz": direct_features["spectral_centroid_hz"],
        "reference_centroid_hz": reference_features["spectral_centroid_hz"],
        "native_contact_ms": 1000 * float(raw_diagnostics["contact_seconds"]),
        "reference_contact_ms": 1000 * high_diagnostics["contact_seconds"],
        "limitation": "Combined integration/output-sampling convergence probe at one strong C4 strike; not an alias-free certificate, psychoacoustic audibility bound or full-parameter convergence proof. Both runs use the same numerical model and configured substeps.",
    }


def markdown(report):
    lines = ["# C4 nonlinear hammer: reproducible evidence", "",
             "Status: uncalibrated synthetic candidate. This report does not establish piano realism or listening acceptance.", "",
             "RMS is signal level, not perceptual loudness. Spectral centroid uses magnitude-weighted FFT bins over 20–400 ms; partial fractions integrate power within ±8 Hz of each configured mode. Attack is the first 10–90% rise of a 1 ms causal RMS envelope relative to its maximum within the first 50 ms. These definitions are fixed across velocities.", "",
             "| Rate | Max adjacent RMS (≤0.5 dB) | Max adjacent centroid (≤3%) | Checks | RMS range | Soft centroid | Loud centroid | Weak/strong scalar-fit residual | Peak |",
             "| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |"]
    for item in report["sample_rates"]:
        s = item["summary"]
        passed = all(item["checks"].values())
        status = "PASS" if passed else "FAIL"
        lines.append(f"| {item['sample_rate_hz']} Hz | {s['largest_adjacent_rms_change_db']:.6f} dB | {100 * s['largest_adjacent_centroid_change_fraction']:.6f}% | {status} ({sum(item['checks'].values())}/{len(item['checks'])}) | {s['rms_dynamic_range_db']:.2f} dB | {s['centroid_soft_hz']:.2f} Hz | {s['centroid_loud_hz']:.2f} Hz | {s['weak_strong_scalar_fit_relative_rms_residual']:.6f} | {s['maximum_pcm_peak']:.6f} |")
    lines.extend(["", "## Higher-rate reference", "", "A strong isolated C4 strike is also rendered at four times each output rate. A Kaiser-window lowpass is applied before downsampling, with end-of-sample timestamps aligned. Relative waveform/attack error, centroid and contact time are recorded separately from native/WASM conformance. This is combined numerical and output-sampling convergence evidence, not proof of alias-free output.", ""])
    for item in report["sample_rates"]:
        c = item["higher_rate_reference"]
        lines.append(f"- {item['sample_rate_hz']} Hz versus {c['reference_sample_rate_hz']} Hz reference: relative RMS waveform error {c['relative_rms_waveform_error']:.6f}; contact {c['native_contact_ms']:.6f} vs {c['reference_contact_ms']:.6f} ms.")
    lines.extend(["", "## Listening", "", "Each rate folder contains `c4-hammer-rms-matched-ab.wav`: 0–16 s accepted basic engine, 17–33 s C4 hammer candidate. Both play MIDI velocities 8, 24, 40, 56, 72, 88, 104, 127 held until the next reset, then three release/repeat probes. One constant gain per segment preserves its dynamic range. `c4-hammer-raw-comparison.wav` uses a common gain, and float WAV/raw f32 files preserve the engine output.", "", "The hard reset between single-note probes may abruptly cut still-sounding tails. It is an intentional test separator, not the completed key-release behavior. Judge contact/attack and held tone separately from that boundary; continuous, click-free damper release remains issue #8.", "", "This comparison differs in the underlying C4 string/voice topology as well as excitation. It is a development A/B against the existing MVP, not an isolated causal test of the hammer or a replacement for real-piano calibration. The single-C4 path has no completed half-pedal, bridge/soundboard or full-keyboard model. The final repeat probe also exposes the currently different release behavior.", "", "## Reproduction", "", "```sh", report["reproduce"], "```", "", "## Exact candidate identity", "", f"Git base revision at analysis: `{report['source_revision']}`."])
    if report["source_has_uncommitted_changes"]:
        lines.extend(["", "Working tree: **dirty (uncommitted changes)**. The base commit alone does not identify the measured candidate. The source and renderer SHA-256 values below and in `hammer-review.json` identify the actual implementation that produced the verified PCM."])
    else:
        lines.extend(["", "Working tree: clean. Source and renderer SHA-256 values still identify the exact measured implementation."])
    lines.extend(["", "| Candidate component | SHA-256 |", "| --- | --- |"])
    for component in ["crates/moonlight-dsp/src/lib.rs", "crates/moonlight-dsp/src/realtime.rs"]:
        lines.append(f"| `{component}` | `{report['source_sha256'][component]}` |")
    lines.extend([f"| Native renderer executable | `{report['renderer_sha256']}` |", "", "All source/model/analysis hashes, exact diagnostics, every velocity's PCM hash, render manifests, and machine-readable checks are recorded in `hammer-review.json` and the per-rate `render-manifest.json` files. Re-analysis verifies the raw render identity before producing this report.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "work/c4-hammer-review")
    parser.add_argument("--rate", type=int, choices=[44100, 48000], action="append")
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()
    rates = args.rate or [44100, 48000]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    renderer = ROOT / "target/release/examples/hammer_sweep"
    if not args.skip_render:
        subprocess.run(["cargo", "build", "--release", "-p", "moonlight-dsp", "--example", "hammer_sweep"], cwd=ROOT, check=True)
    model_path = ROOT / "fixtures/physical-c4/minimal-c4.mlpiano"
    partials = [float(line.split("=", 1)[1].split(",")[0]) for line in model_path.read_text().splitlines() if line.startswith("mode=")]
    source_paths = [ROOT / "crates/moonlight-dsp/src/realtime.rs", ROOT / "crates/moonlight-dsp/src/lib.rs",
                    ROOT / "crates/moonlight-dsp/src/basic.rs", model_path,
                    ROOT / "crates/moonlight-model/src/lib.rs", ROOT / "crates/moonlight-physics/src/lib.rs",
                    ROOT / "crates/moonlight-dsp/examples/hammer_sweep.rs", Path(__file__)]
    hammer_source = ROOT / "crates/moonlight-dsp/src/hammer.rs"
    if hammer_source.exists():
        source_paths.append(hammer_source)
    report = {
        "schema_version": 1,
        "status": "uncalibrated C4 hammer candidate; subjective listening acceptance pending",
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_has_uncommitted_changes": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in source_paths},
        "renderer_sha256": sha256(renderer),
        "seed_hex": "85a308d3243f6a88",
        "tools": {"python": sys.version.split()[0], "numpy": np.__version__, "scipy": scipy.__version__,
                  "rustc": subprocess.check_output(["rustc", "--version"], cwd=ROOT, text=True).strip()},
        "baseline": {"implementation": "current BasicPianoEngine; mono average of its stereo output",
                     "pr46_accepted_source_sha256": ACCEPTED_BASIC_SHA256,
                     "matches_pr46_accepted_source": sha256(ROOT / "crates/moonlight-dsp/src/basic.rs") == ACCEPTED_BASIC_SHA256},
        "partial_frequencies_hz": partials,
        "reproduce": "python3 scripts/render-hammer-review.py" + "".join(f" --rate {rate}" for rate in rates),
        "reference_data": "none; generated from the production Rust C4 model without reading outer holdout",
        "sample_rates": [],
    }
    render_sources = {key: value for key, value in report["source_sha256"].items()
                      if key != "scripts/render-hammer-review.py"}
    render_identity = {"source_sha256": render_sources, "renderer_sha256": report["renderer_sha256"]}

    def check_render_identity():
        current_sources = {key: sha256(ROOT / key) for key in render_sources}
        if current_sources != render_sources or sha256(renderer) != report["renderer_sha256"]:
            raise ValueError("Render source or executable changed while collecting evidence; rerun from a stable revision")

    for rate in rates:
        destination = output / str(rate)
        manifest_path = destination / "render-manifest.json"
        if args.skip_render:
            if not manifest_path.exists() or json.loads(manifest_path.read_text()) != render_identity:
                raise ValueError(f"Raw render identity does not match current sources/executable: {manifest_path}; rerender")
        if not args.skip_render:
            subprocess.run([str(renderer), str(destination), str(rate)], cwd=ROOT, check=True)
        analyzed = analyze_rate(destination, rate, partials)
        analyzed["higher_rate_reference"] = convergence(destination, rate, partials, renderer, args.skip_render)
        check_render_identity()
        if not args.skip_render:
            manifest_path.write_text(json.dumps(render_identity, indent=2) + "\n")
        report["sample_rates"].append(analyzed)
    report["all_checks_passed"] = all(all(item["checks"].values()) for item in report["sample_rates"])
    (output / "hammer-review.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "hammer-review.md").write_text(markdown(report))
    print(json.dumps({"output": str(output), "all_checks_passed": report["all_checks_passed"],
                      "summary": [{"sample_rate_hz": item["sample_rate_hz"], **item["summary"], "checks": item["checks"]} for item in report["sample_rates"]]}, indent=2))
    if not report["all_checks_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
