#!/usr/bin/env python3
"""Measure how long a key press takes to reach the screen.

Device ACK only proves Android accepted the touch; it says nothing about when
the app draws the result.  This tool separates the two delays that a single
start-note measurement conflates:

    send DOWN --[input pipeline]--> key lights up --[app start-up]--> score scrolls

A press is held rather than tapped so its highlight spans several sampled
frames, and frames carry only the two cheap features needed here so the sample
rate stays as high as the decoder allows.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time

import numpy as np

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import duolingo_keyboard_detect as kbdetect  # noqa: E402

REPO_ROOT = _SCRIPTS_DIR.parent
STAFF_BAND = (140, 400)
SCROLL_X = (440, 1500)


def load_script(alias: str, filename: str):
    spec = importlib.util.spec_from_file_location(alias, REPO_ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class PressAction:
    index: int
    pitch: str
    kind: str
    sequence: int
    planned_ns: int
    sent_ns: int
    ack_ns: int | None = None


def press_worker(shell, schedule, start_ns, actions, stop):
    sequence = 1000
    for index, (offset_ms, pitch, hold_ms) in enumerate(schedule):
        deadline = start_ns + int(offset_ms * 1_000_000)
        while (remaining := deadline - time.monotonic_ns()) > 0 and not stop.is_set():
            time.sleep(min(remaining / 1_000_000_000, 0.02))
        if stop.is_set():
            return
        sequence += 1
        sent_ns, _ = shell.send("DOWN", pitch, sequence)
        actions.append(PressAction(index, pitch, "DOWN", sequence, deadline, sent_ns))
        release = sent_ns + int(hold_ms * 1_000_000)
        while (remaining := release - time.monotonic_ns()) > 0 and not stop.is_set():
            time.sleep(min(remaining / 1_000_000_000, 0.02))
        sequence += 1
        up_ns, _ = shell.send("UP", pitch, sequence)
        actions.append(PressAction(index, pitch, "UP", sequence, release, up_ns))


def key_roi(point, is_black):
    x, y = point
    half_w = 40 if is_black else 50
    return (max(0, x - half_w), x + half_w, max(0, y - 45), y + 45)


def run(args) -> dict:
    reader = load_script("dl_reader_latency", "duolingo-read-screen-notes.py")
    timed = load_script("dl_timed_latency", "duolingo-timed-player.py")

    key_points = kbdetect.resolve_key_points(serial=args.serial, adb=args.adb)
    for pitch in (args.probe_pitch, args.start_pitch):
        if pitch not in key_points:
            raise SystemExit(
                f"{pitch} is not on this lesson's keyboard; available: "
                f"{', '.join(sorted(key_points))}"
            )
    rois = {
        pitch: key_roi(key_points[pitch], "b" in pitch or "#" in pitch)
        for pitch in {args.probe_pitch, args.start_pitch}
    }

    schedule = []
    for i in range(args.probe_trials):
        schedule.append((args.first_probe_ms + i * args.probe_interval_ms, args.probe_pitch, args.hold_ms))
    start_offset = args.first_probe_ms + args.probe_trials * args.probe_interval_ms
    schedule.append((start_offset, args.start_pitch, args.hold_ms))

    pump = reader.H264FramePump(args.adb, args.serial)
    shell = timed.PersistentInputShell(args.adb, args.serial, key_points=key_points)
    actions: list[PressAction] = []
    stop = threading.Event()
    frames: list[dict] = []
    profiles: list[np.ndarray] = []

    try:
        pump.start()
        warmup_ms = shell.warmup()
        start_ns = time.monotonic_ns()
        worker = threading.Thread(
            target=press_worker, args=(shell, schedule, start_ns, actions, stop), daemon=True
        )
        worker.start()
        deadline = start_ns + int(args.duration * 1_000_000_000)
        last_sequence = -1
        while time.monotonic_ns() < deadline:
            image = pump.wait_for_frame(after_sequence=last_sequence, timeout=1.0)
            received_ns = time.monotonic_ns()
            last_sequence = pump.sequence
            arr = np.asarray(image.convert("RGB")).astype(np.int16)
            lum = arr.mean(axis=2)
            band = lum[STAFF_BAND[0]:STAFF_BAND[1], SCROLL_X[0]:SCROLL_X[1]]
            profiles.append((255.0 - band).sum(axis=0))
            frames.append({
                "index": len(frames),
                "monotonic_ns": received_ns,
                "relative_ms": (received_ns - start_ns) / 1_000_000,
                "roi": {
                    pitch: float(lum[r[2]:r[3], r[0]:r[1]].mean())
                    for pitch, r in rois.items()
                },
            })
        stop.set()
        worker.join(timeout=2.0)
        shell.wait_for({a.sequence for a in actions}, timeout=2.0)
        for action in actions:
            action.ack_ns = shell._ack_ns.get(action.sequence)
    finally:
        stop.set()
        try:
            pump.stop()
        except Exception:
            pass

    return analyze(args, frames, profiles, actions, start_ns, key_points, warmup_ms, schedule)


def motion_shift(previous, current, lo=-90, hi=25):
    best, best_shift = -1e18, 0
    for shift in range(lo, hi + 1):
        if shift < 0:
            a, b = previous[-shift:], current[: len(current) + shift]
        elif shift > 0:
            a, b = previous[: len(previous) - shift], current[shift:]
        else:
            a, b = previous, current
        value = float(np.dot(a, b) / len(a))
        if value > best:
            best, best_shift = value, shift
    return -best_shift


def analyze(args, frames, profiles, actions, start_ns, key_points, warmup_ms, schedule):
    shifts = [0.0] + [motion_shift(profiles[i - 1], profiles[i]) for i in range(1, len(profiles))]
    motion_idx = next((i for i, s in enumerate(shifts) if s > 3), None)

    downs = [a for a in actions if a.kind == "DOWN"]
    results = []
    for action in downs:
        roi_series = [(f["relative_ms"], f["roi"][action.pitch]) for f in frames]
        sent_ms = (action.sent_ns - start_ns) / 1_000_000
        before = [v for t, v in roi_series if t < sent_ms]
        if len(before) < 3:
            results.append({"pitch": action.pitch, "sent_ms": sent_ms, "error": "no baseline"})
            continue
        baseline = float(np.median(before[-15:]))
        noise = float(np.percentile([abs(v - baseline) for v in before[-15:]], 95)) or 0.0
        threshold = max(noise * 3.0, args.roi_threshold)
        after = [(t, v) for t, v in roi_series if t >= sent_ms]
        hit = next((t for t, v in after if abs(v - baseline) > threshold), None)
        prev_t = None
        for t, _ in after:
            if hit is not None and t >= hit:
                break
            prev_t = t
        results.append({
            "pitch": action.pitch,
            "sent_ms": round(sent_ms, 2),
            "ack_ms": round((action.ack_ns - start_ns) / 1_000_000, 2) if action.ack_ns else None,
            "ack_latency_ms": round((action.ack_ns - action.sent_ns) / 1_000_000, 2) if action.ack_ns else None,
            "roi_baseline": round(baseline, 2),
            "roi_threshold": round(threshold, 3),
            "highlight_ms": round(hit, 2) if hit is not None else None,
            "highlight_latency_ms": round(hit - sent_ms, 2) if hit is not None else None,
            "prev_frame_ms": round(prev_t, 2) if prev_t is not None else None,
        })

    intervals = [
        frames[i]["relative_ms"] - frames[i - 1]["relative_ms"] for i in range(1, len(frames))
    ]
    summary = {
        "protocol": "duolingo-input-latency/v1",
        "serial": args.serial,
        "warmup_ms": round(warmup_ms, 2),
        "frame_count": len(frames),
        "mean_frame_interval_ms": round(float(np.mean(intervals)), 2) if intervals else None,
        "median_frame_interval_ms": round(float(np.median(intervals)), 2) if intervals else None,
        "schedule": [{"offset_ms": o, "pitch": p, "hold_ms": h} for o, p, h in schedule],
        "key_points_used": {p: key_points[p] for p in {args.probe_pitch, args.start_pitch}},
        "presses": results,
        "scroll_motion_ms": round(frames[motion_idx]["relative_ms"], 2) if motion_idx else None,
        "scroll_prev_frame_ms": (
            round(frames[motion_idx - 1]["relative_ms"], 2) if motion_idx else None
        ),
    }
    start_press = next((r for r in results if r["pitch"] == args.start_pitch), None)
    if start_press and summary["scroll_motion_ms"] is not None:
        summary["start_note_total_ms"] = round(summary["scroll_motion_ms"] - start_press["sent_ms"], 2)
        if start_press.get("highlight_latency_ms") is not None:
            summary["app_startup_ms"] = round(
                summary["scroll_motion_ms"] - start_press["highlight_ms"], 2
            )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--duration", type=float, default=12.0)
    parser.add_argument("--probe-pitch", default="F4", help="key pressed while the score is idle")
    parser.add_argument("--start-pitch", default="A4", help="key that starts the scroll")
    parser.add_argument("--hold-ms", type=float, default=600.0)
    parser.add_argument("--probe-trials", type=int, default=3)
    parser.add_argument("--first-probe-ms", type=float, default=1200.0)
    parser.add_argument("--probe-interval-ms", type=float, default=1500.0)
    parser.add_argument("--roi-threshold", type=float, default=1.5)
    args = parser.parse_args()
    summary = run(args)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
