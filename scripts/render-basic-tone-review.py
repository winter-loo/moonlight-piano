#!/usr/bin/env python3
"""Offline listening evidence; uses the analysis-only NumPy/SciPy environment.

Optionally pass a basic_render executable built against the baseline core.
Both revisions receive identical events. A/B matching applies one scalar gain
per segment, with no filtering, limiting, denoising or resampling.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
RATE = 48000
SECONDS = 16.5
PROBES = [33, 45, 60, 69, 84]


def write_events(path, events):
    events.sort(key=lambda event: event[0])
    path.write_text("".join(",".join(map(str, event)) + "\n" for event in events))


def rms(samples):
    return float(np.sqrt(np.mean(samples * samples)))


def samples(path):
    rate, pcm = wavfile.read(path)
    if rate != RATE or pcm.dtype != np.int16 or pcm.ndim != 2 or pcm.shape[1] != 2:
        raise ValueError(f"Unexpected render format: {path}")
    return pcm.astype(np.float64) / 32768.0


def spectral_peak(signal, fundamental):
    window = np.hanning(len(signal))
    size = 1 << 19
    spectrum = np.abs(np.fft.rfft(signal * window, n=size))
    frequencies = np.fft.rfftfreq(size, 1 / RATE)
    valid = (frequencies > fundamental * .8) & (frequencies < max(260, fundamental * 1.8))
    return float(frequencies[valid][np.argmax(spectrum[valid])])


def render(renderer, events, output, seconds):
    subprocess.run([str(renderer), str(events), str(output), str(seconds), str(RATE)], check=True, cwd=ROOT)
    return samples(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "work/basic-tone-review")
    parser.add_argument("--baseline-renderer", type=Path)
    parser.add_argument("--baseline-revision")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cargo", "build", "--release", "-p", "moonlight-dsp", "--example", "basic_render"], cwd=ROOT, check=True)
    renderers = {"candidate": ROOT / "target/release/examples/basic_render"}
    if args.baseline_renderer:
        renderers = {"baseline": args.baseline_renderer.resolve(), **renderers}

    events = []

    def note(time, duration, pitch, velocity):
        events.extend([(round(time * RATE), "on", pitch, velocity),
                       (round((time + duration) * RATE), "off", pitch, .5)])

    note(.15, .6, 45, .65)
    note(1.5, .6, 60, .65)
    for pitch in [60, 64, 67]:
        note(2.85, .9, pitch, .65)
    # Read the song's canonical source rather than maintaining another score.
    song = runpy.run_path(str(ROOT / "scripts/generate-bicycle-grand-staff.py"))
    for index, measure in enumerate([4, 5, 6, 7, 8, 9]):
        for hand, key, volume in [("rh", "RIGHT_HAND_MEASURES", .44), ("lh", "LEFT_HAND_MODE_1", .38)]:
            for event in song[key][measure - 1]["events"]:
                if event["type"] != "note":
                    continue
                pitch = event["pitch"]
                midi = (int(pitch[-1]) + 1) * 12 + {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[pitch[0]]
                note(4.5 + (index * 3 + event["beat"]) * .6,
                     event["durationBeats"] * .6 * (.96 if hand == "lh" else 1),
                     midi, volume * 1.6 * (.92 if hand == "lh" else 1))
    listening_events = output / "listen.events.csv"
    write_events(listening_events, events)
    report = {
        "sample_rate": RATE, "segment_seconds": SECONDS,
        "candidate_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "candidate_dsp_sha256": hashlib.sha256((ROOT / "crates/moonlight-dsp/src/basic.rs").read_bytes()).hexdigest(),
        "baseline_revision": args.baseline_revision,
        "events_sha256": hashlib.sha256(listening_events.read_bytes()).hexdigest(),
        "renders": {},
        "acceptance": "Artifact regression evidence only; subjective piano tone acceptance remains pending.",
    }
    listens = {}
    for label, renderer in renderers.items():
        listens[label] = render(renderer, listening_events, output / f"{label}.wav", SECONDS)
        measurements = {"renderer_sha256": hashlib.sha256(renderer.read_bytes()).hexdigest(),
                        "listen_peak": float(np.max(np.abs(listens[label]))),
                        "listen_rms": rms(listens[label]), "probes": {}}
        for pitch in PROBES:
            csv = output / f"note-{pitch}.csv"
            write_events(csv, [(0, "on", pitch, .8), (RATE, "off", pitch, .5)])
            audio = render(renderer, csv, output / f"{label}-{pitch}.wav", 2).mean(axis=1)
            fundamental = 440 * 2 ** ((pitch - 69) / 12)
            measurements["probes"][pitch] = {
                "held_peak_hz": spectral_peak(audio[int(.25 * RATE):int(.85 * RATE)], fundamental),
                "released_peak_hz": spectral_peak(audio[int(1.005 * RATE):int(1.125 * RATE)], fundamental),
                "first_second_rms": rms(audio[:RATE]),
            }
        individual = []
        for name, pitches in [("c", [60]), ("e", [64]), ("chord", [60, 64])]:
            csv = output / f"{name}.csv"
            write_events(csv, [(0, "on", pitch, .8) for pitch in pitches])
            individual.append(render(renderer, csv, output / f"{label}-{name}.wav", 1))
        measurements["chord_superposition_error_ratio"] = rms(individual[2] - individual[0] - individual[1]) / rms(individual[2])
        report["renders"][label] = measurements
    if "baseline" in listens:
        crest = max(float(np.max(np.abs(audio))) / rms(audio) for audio in listens.values())
        target = min(.1, .95 / crest)
        parts = []
        for label, audio in listens.items():
            gain = target / rms(audio)
            parts.append(audio * gain)
            report["renders"][label]["comparison_gain_db"] = float(20 * np.log10(gain))
        combined = np.concatenate([parts[0], np.zeros((int(1.5 * RATE), 2)), parts[1]])
        if not np.all(np.isfinite(combined)) or np.max(np.abs(combined)) >= 1:
            raise ValueError("Comparison would clip")
        wavfile.write(output / "basic-piano-tone-ab.wav", RATE, np.rint(combined * 32767).astype(np.int16))
        report["comparison"] = {"baseline_seconds": [0, 16.5], "candidate_seconds": [18, 34.5],
                                "matching": "one constant RMS-matching gain per segment; not LUFS normalization"}
    (output / "tone-review.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
