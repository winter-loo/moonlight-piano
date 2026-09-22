#!/usr/bin/env python3
"""Play the notes currently on screen, timed from the score's own geometry.

The first note doubles as the start trigger, so every later note is scheduled
against that press on one absolute clock: note spacing comes from the score's
pixels-per-beat, and the tempo from the measured scroll speed.  Frames are
recorded throughout so the per-note verdict can be read back afterwards.
"""

from __future__ import annotations

import argparse
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


def load_script(alias: str, filename: str):
    spec = importlib.util.spec_from_file_location(alias, REPO_ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def build_beat_grid(events: list[dict]) -> list[dict]:
    """Lay the recognised events on the beat grid their durations imply."""
    grid, beat = [], 0.0
    for event in events:
        delta = event.get("delta_beats")
        grid.append({**event, "beat": beat})
        if delta is None:
            # A right-clipped tail note still starts on the grid; it simply has
            # no measurable length, so nothing after it can be placed.
            break
        beat += float(delta)
    return grid


def fit_px_per_beat(grid: list[dict]) -> tuple[float, float] | None:
    """Least-squares px-per-beat from noteheads; needs at least three of them."""
    usable = [g for g in grid if g["event_type"] == "note" and g.get("delta_beats") is not None]
    if len(usable) < 3:
        return None
    beats = np.array([g["beat"] for g in usable], dtype=float)
    xs = np.array([g["x"] for g in usable], dtype=float)
    slope, intercept = np.polyfit(beats, xs, 1)
    residual = float(np.max(np.abs(xs - (slope * beats + intercept))))
    return float(slope), residual


def capture_worker(pump, out_dir, records, stop, start_ns):
    last_sequence = -1
    while not stop.is_set():
        try:
            image = pump.wait_for_frame(after_sequence=last_sequence, timeout=1.0)
        except Exception:
            continue
        received_ns = time.monotonic_ns()
        last_sequence = pump.sequence
        index = len(records)
        name = f"frame-{index:04d}.png"
        image.save(out_dir / name, format="PNG")
        records.append({
            "index": index,
            "image": f"frames/{name}",
            "relative_ms": (received_ns - start_ns) / 1_000_000,
        })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scroll-px-s", type=float, default=179.27)
    parser.add_argument(
        "--beat-ms",
        type=float,
        help="use this measured beat length instead of fitting one from noteheads",
    )
    parser.add_argument(
        "--startup-ms",
        type=float,
        default=85.0,
        help="device-side delay between the start touch and the score scrolling",
    )
    parser.add_argument("--release-ms", type=float, default=60.0)
    parser.add_argument("--tail-ms", type=float, default=2500.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    reader = load_script("dl_reader_play", "duolingo-read-screen-notes.py")
    timed = load_script("dl_timed_play", "duolingo-timed-player.py")

    frame = kbdetect.capture_device_frame(args.serial, args.adb)
    layout = kbdetect.detect_keyboard(frame)
    from PIL import Image
    result = reader.analyze_image(Image.fromarray(frame))
    grid = build_beat_grid(result["events"])
    notes = [g for g in grid if g["event_type"] == "note"]
    if not notes:
        raise SystemExit("no notes on screen")

    fit = fit_px_per_beat(grid)
    if args.beat_ms is not None:
        beat_ms = args.beat_ms
        px_per_beat = beat_ms * args.scroll_px_s / 1000.0
        residual = fit[1] if fit else float("nan")
        tempo_source = "explicit --beat-ms"
    elif fit is not None:
        px_per_beat, residual = fit
        beat_ms = px_per_beat / args.scroll_px_s * 1000.0
        tempo_source = "notehead fit"
    else:
        raise SystemExit(
            "this screen has fewer than three notes, so px-per-beat cannot be "
            "fitted; pass --beat-ms with a measured value"
        )

    plan = []
    for note in notes:
        target = layout.target(note["pitch"])
        if target is None:
            raise SystemExit(f"{note['pitch']} has no key on this keyboard")
        hold = float(note["duration_beats"] or 0.5) * beat_ms - args.release_ms
        plan.append({
            "pitch": note["pitch"],
            "beat": note["beat"],
            "x": note["x"],
            "duration_beats": note["duration_beats"],
            "key_target": list(target),
            "offset_ms": args.startup_ms + note["beat"] * beat_ms,
            "hold_ms": max(hold, 80.0),
        })

    header = {
        "px_per_beat": round(px_per_beat, 2),
        "fit_residual_px": round(residual, 2),
        "tempo_source": tempo_source,
        "beat_ms": round(beat_ms, 2),
        "bpm": round(60000.0 / beat_ms, 2),
        "startup_ms": args.startup_ms,
        "notes": len(plan),
        "span_beats": plan[-1]["beat"],
    }
    print(json.dumps(header, ensure_ascii=False, indent=2), file=sys.stderr)
    for step in plan:
        print(
            f"  beat {step['beat']:5.2f}  {step['pitch']:4s} "
            f"{str(step['key_target']):12s} hold {step['hold_ms']:6.1f}ms "
            f"@ +{step['offset_ms']:7.1f}ms",
            file=sys.stderr,
        )
    if args.dry_run:
        print(json.dumps({"dry_run": True, **header, "plan": plan}, ensure_ascii=False))
        return

    out_dir: Path = args.output
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=False)

    pump = reader.H264FramePump(args.adb, args.serial)
    shell = timed.PersistentInputShell(args.adb, args.serial, key_points=layout.keys)
    records: list[dict] = []
    stop = threading.Event()
    log = []
    try:
        pump.start()
        warmup_ms = shell.warmup()
        start_ns = time.monotonic_ns()
        cam = threading.Thread(
            target=capture_worker, args=(pump, frames_dir, records, stop, start_ns), daemon=True
        )
        cam.start()

        actions = []
        for index, step in enumerate(plan):
            actions.append((start_ns + int(step["offset_ms"] * 1e6), "DOWN", index, step))
            actions.append(
                (start_ns + int((step["offset_ms"] + step["hold_ms"]) * 1e6), "UP", index, step)
            )
        actions.sort(key=lambda a: (a[0], 0 if a[1] == "UP" else 1))

        sequence = 2000
        for deadline_ns, kind, index, step in actions:
            while (remaining := deadline_ns - time.monotonic_ns()) > 0:
                time.sleep(min(remaining / 1e9, 0.005))
            sequence += 1
            sent_ns, _ = shell.send(kind, step["pitch"], sequence)
            log.append({
                "note_index": index,
                "kind": kind,
                "pitch": step["pitch"],
                "sequence": sequence,
                "deadline_ms": (deadline_ns - start_ns) / 1e6,
                "sent_ms": (sent_ns - start_ns) / 1e6,
                "error_ms": (sent_ns - deadline_ns) / 1e6,
            })
        shell.wait_for({entry["sequence"] for entry in log}, timeout=3.0)
        for entry in log:
            ack = shell._ack_ns.get(entry["sequence"])
            entry["ack_ms"] = (ack - start_ns) / 1e6 if ack else None

        tail_deadline = time.monotonic_ns() + int(args.tail_ms * 1e6)
        while time.monotonic_ns() < tail_deadline:
            time.sleep(0.05)
    finally:
        stop.set()
        time.sleep(0.3)
        try:
            pump.stop()
        except Exception:
            pass

    errors = [entry["error_ms"] for entry in log]
    summary = {
        "protocol": "duolingo-play-screen-notes/v1",
        **header,
        "warmup_ms": round(warmup_ms, 2),
        "frames": len(records),
        "dispatch_error_ms": {
            "max_abs": round(max(abs(e) for e in errors), 3),
            "mean": round(float(np.mean(errors)), 3),
        },
        "acks_received": sum(1 for entry in log if entry["ack_ms"] is not None),
        "actions": len(log),
    }
    (out_dir / "plan.json").write_text(
        json.dumps({**header, "plan": plan}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "input-log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "frames.json").write_text(
        json.dumps(records, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
