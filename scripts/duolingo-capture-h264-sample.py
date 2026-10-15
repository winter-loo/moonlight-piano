#!/usr/bin/env python3
"""Capture timestamped OPPO H.264 frames for offline score-motion analysis."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import heapq
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import duolingo_keyboard_detect as _kbdetect
from duolingo_keyboard_profiles import KEYBOARD_PROFILES as ASSIST_KEYBOARD_PROFILES


REPO_ROOT = Path(__file__).resolve().parents[1]
READER_PATH = REPO_ROOT / "scripts/duolingo-read-screen-notes.py"

class AssistTapScheduler:
    """Send best-effort hold gestures without blocking H.264 frame capture."""

    def __init__(self, serial: str) -> None:
        self._serial = serial
        self._condition = threading.Condition()
        self._queue: list[tuple[int, int, str, tuple[int, int], int]] = []
        self._next_sequence = 0
        self._stopping = False
        self.actions: list[dict] = []
        self._processes: list[subprocess.Popen] = []
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def schedule(
        self,
        *,
        deadline_ns: int,
        pitch: str,
        key_target: tuple[int, int],
        hold_ms: int,
    ) -> None:
        with self._condition:
            self._next_sequence += 1
            heapq.heappush(
                self._queue,
                (deadline_ns, self._next_sequence, pitch, key_target, hold_ms),
            )
            self._condition.notify()

    def close(self) -> None:
        with self._condition:
            self._stopping = True
            self._condition.notify()
        self._thread.join(timeout=2.0)
        for process in self._processes:
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.terminate()

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._queue and not self._stopping:
                    self._condition.wait()
                if self._stopping:
                    return
                deadline_ns, sequence, pitch, target, hold_ms = self._queue[0]
                remaining_s = (deadline_ns - time.monotonic_ns()) / 1e9
                if remaining_s > 0:
                    self._condition.wait(timeout=remaining_s)
                    continue
                heapq.heappop(self._queue)

            x, y = target
            command = [
                "adb",
                "-s",
                self._serial,
                "shell",
                "input",
                "swipe",
                str(x),
                str(y),
                str(x),
                str(y),
                str(hold_ms),
            ]
            sent_ns = time.monotonic_ns()
            self._processes.append(
                subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
            self.actions.append(
                {
                    "sequence": sequence,
                    "pitch": pitch,
                    "key_target": list(target),
                    "hold_ms": hold_ms,
                    "deadline_monotonic_ns": deadline_ns,
                    "sent_monotonic_ns": sent_ns,
                    "send_error_ms": (sent_ns - deadline_ns) / 1_000_000,
                }
            )


class AssistAnalyzer:
    """Analyze only the newest submitted frame while capture stays on cadence."""

    def __init__(
        self,
        *,
        reader,
        scheduler: AssistTapScheduler,
        key_points: dict[str, tuple[int, int]],
        speed_px_s: float,
        bpm: float,
    ) -> None:
        self._reader = reader
        self._scheduler = scheduler
        self._key_points = key_points
        self._speed_px_s = speed_px_s
        self._beat_ms = 60_000.0 / bpm
        self._condition = threading.Condition()
        self._pending = None
        self._stopping = False
        self._scheduled: list[tuple[str, int]] = []
        self.analysis_count = 0
        self.scheduled_note_count = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, image, captured_ns: int, judgment_line_x: int) -> None:
        with self._condition:
            self._pending = (image.copy(), captured_ns, judgment_line_x)
            self._condition.notify()

    def close(self) -> None:
        with self._condition:
            self._stopping = True
            self._pending = None
            self._condition.notify()
        self._thread.join(timeout=3.0)

    def _run(self) -> None:
        while True:
            with self._condition:
                while self._pending is None and not self._stopping:
                    self._condition.wait()
                if self._stopping:
                    return
                image, captured_ns, judgment_line_x = self._pending
                self._pending = None
            try:
                result = self._reader.analyze_image(image)
            except self._reader.ScoreNotVisibleError:
                continue
            self.analysis_count += 1
            self.scheduled_note_count += schedule_visible_notes(
                notes=result["notes"],
                captured_ns=captured_ns,
                judgment_line_x=judgment_line_x,
                speed_px_s=self._speed_px_s,
                beat_ms=self._beat_ms,
                key_points=self._key_points,
                scheduled=self._scheduled,
                scheduler=self._scheduler,
            )


def schedule_visible_notes(
    *,
    notes: list[dict],
    captured_ns: int,
    judgment_line_x: float,
    speed_px_s: float,
    beat_ms: float,
    key_points: dict[str, tuple[int, int]],
    scheduled: list[tuple[str, int]],
    scheduler: AssistTapScheduler,
) -> int:
    """Schedule newly observed notes and return the number added."""
    added = 0
    cutoff_ns = captured_ns - 1_000_000_000
    scheduled[:] = [item for item in scheduled if item[1] >= cutoff_ns]
    for note in notes:
        pitch = note.get("pitch")
        target = key_points.get(pitch)
        if target is None:
            continue
        lead_s = (float(note["x"]) - judgment_line_x) / speed_px_s
        if not 0.12 <= lead_s <= 4.5:
            continue
        deadline_ns = captured_ns + round(lead_s * 1_000_000_000)
        if any(
            existing_pitch == pitch
            and abs(existing_ns - deadline_ns) <= 160_000_000
            for existing_pitch, existing_ns in scheduled
        ):
            continue
        duration_beats = float(note.get("hold_beats") or 0.35)
        hold_ms = max(120, round(duration_beats * beat_ms))
        scheduler.schedule(
            deadline_ns=deadline_ns,
            pitch=pitch,
            key_target=target,
            hold_ms=hold_ms,
        )
        scheduled.append((pitch, deadline_ns))
        added += 1
    return added


def load_reader():
    spec = importlib.util.spec_from_file_location(
        "duolingo_read_screen_notes_capture", READER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load screen reader from {READER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def capture_sample(
    *,
    serial: str,
    output_dir: Path,
    duration_seconds: float,
    sample_fps: float,
    capture_fps: int = 60,
    start_tap: tuple[int, int] | None = None,
    start_tap_count: int = 0,
    start_tap_delay_ms: float = 250.0,
    start_tap_interval_ms: float = 500.0,
    assist_profile: str | None = None,
    assist_speed_px_s: float = 280.0,
    assist_bpm: float = 116.7,
) -> dict:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if sample_fps <= 0:
        raise ValueError("sample_fps must be positive")
    if start_tap_count < 0:
        raise ValueError("start_tap_count cannot be negative")
    if start_tap_count and start_tap is None:
        raise ValueError("start_tap is required when start_tap_count is positive")

    output_dir.mkdir(parents=True, exist_ok=False)
    frames_dir = output_dir / "frames"
    frames_dir.mkdir()
    metadata_path = output_dir / "frames.jsonl"
    reader = load_reader()
    pump = reader.H264FramePump(
        "adb", serial,
        encoder_fps=capture_fps,
        output_fps=capture_fps,
        warmup_frames=max(20, capture_fps),
    )
    assist = AssistTapScheduler(serial) if assist_profile is not None else None
    assist_key_points = (
        _kbdetect.resolve_key_points(
            serial=serial,
            profile=None if assist_profile == "auto" else assist_profile,
            profiles=ASSIST_KEYBOARD_PROFILES,
        )
        if assist_profile is not None
        else {}
    )
    assist_analyzer = (
        AssistAnalyzer(
            reader=reader,
            scheduler=assist,
            key_points=assist_key_points,
            speed_px_s=assist_speed_px_s,
            bpm=assist_bpm,
        )
        if assist is not None
        else None
    )
    records: list[dict] = []
    started_wall = datetime.now(timezone.utc).isoformat()
    interval_ns = round(1_000_000_000 / sample_fps)

    try:
        pump.start()
        print(
            json.dumps(
                {
                    "ready": True,
                    "serial": serial,
                    "duration_seconds": duration_seconds,
                    "sample_fps": sample_fps,
                    "output_dir": str(output_dir),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        capture_started_ns = time.monotonic_ns()
        next_deadline_ns = capture_started_ns
        last_sequence = pump.sequence
        tap_deadlines_ns = [
            capture_started_ns
            + round(
                (start_tap_delay_ms + index * start_tap_interval_ms) * 1_000_000
            )
            for index in range(start_tap_count)
        ]
        taps_sent: list[dict] = []

        with metadata_path.open("w", encoding="utf-8") as metadata_stream:
            while True:
                now_ns = time.monotonic_ns()
                if now_ns >= capture_started_ns + round(duration_seconds * 1e9):
                    break
                remaining_ns = next_deadline_ns - now_ns
                if remaining_ns > 0:
                    time.sleep(remaining_ns / 1e9)

                now_ns = time.monotonic_ns()
                while tap_deadlines_ns and now_ns >= tap_deadlines_ns[0]:
                    planned_ns = tap_deadlines_ns.pop(0)
                    assert start_tap is not None
                    subprocess.run(
                        [
                            "adb",
                            "-s",
                            serial,
                            "shell",
                            "input",
                            "tap",
                            str(start_tap[0]),
                            str(start_tap[1]),
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                    )
                    sent_ns = time.monotonic_ns()
                    taps_sent.append(
                        {
                            "x": start_tap[0],
                            "y": start_tap[1],
                            "planned_relative_ms": (
                                planned_ns - capture_started_ns
                            )
                            / 1_000_000,
                            "sent_relative_ms": (
                                sent_ns - capture_started_ns
                            )
                            / 1_000_000,
                        }
                    )
                    now_ns = sent_ns

                source_sequence_before = last_sequence
                image = pump.wait_for_frame(
                    after_sequence=last_sequence,
                    timeout=1.0,
                )
                received_ns = time.monotonic_ns()
                last_sequence = pump.sequence
                frame_index = len(records)
                filename = f"frame-{frame_index:04d}.png"
                image.save(frames_dir / filename, format="PNG")
                context = reader.build_analysis_context(image)
                record = {
                    "frame_index": frame_index,
                    "image": f"frames/{filename}",
                    "width": image.width,
                    "height": image.height,
                    "source_sequence_before": source_sequence_before,
                    "source_sequence": last_sequence,
                    "monotonic_ns": received_ns,
                    "relative_ms": (received_ns - capture_started_ns) / 1_000_000,
                    "judgment_line_x": context.judgment_line_x,
                    "staff_lines": (
                        list(context.staff_lines)
                        if context.staff_lines is not None
                        else None
                    ),
                }
                metadata_stream.write(
                    json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
                metadata_stream.flush()
                records.append(record)
                if assist_analyzer is not None and taps_sent:
                    first_tap_ns = (
                        capture_started_ns
                        + round(taps_sent[0]["sent_relative_ms"] * 1_000_000)
                    )
                    if received_ns >= first_tap_ns + 600_000_000:
                        assist_analyzer.submit(
                            image,
                            received_ns,
                            context.judgment_line_x,
                        )
                next_deadline_ns += interval_ns
    finally:
        pump.stop()
        if assist_analyzer is not None:
            assist_analyzer.close()
        if assist is not None:
            assist.close()

    captured_wall = datetime.now(timezone.utc).isoformat()
    intervals_ms = [
        (current["monotonic_ns"] - previous["monotonic_ns"]) / 1_000_000
        for previous, current in zip(records, records[1:])
    ]
    manifest = {
        "protocol": "duolingo-h264-frame-sample/v1",
        "serial": serial,
        "started_at_utc": started_wall,
        "completed_at_utc": captured_wall,
        "requested_duration_seconds": duration_seconds,
        "requested_sample_fps": sample_fps,
        "frame_count": len(records),
        "first_monotonic_ns": records[0]["monotonic_ns"] if records else None,
        "last_monotonic_ns": records[-1]["monotonic_ns"] if records else None,
        "mean_interval_ms": (
            sum(intervals_ms) / len(intervals_ms) if intervals_ms else None
        ),
        "minimum_interval_ms": min(intervals_ms) if intervals_ms else None,
        "maximum_interval_ms": max(intervals_ms) if intervals_ms else None,
        "start_taps": taps_sent,
        "assist": (
            {
                "profile": assist_profile,
                "speed_px_s": assist_speed_px_s,
                "bpm": assist_bpm,
                "analysis_count": (
                    assist_analyzer.analysis_count
                    if assist_analyzer is not None
                    else 0
                ),
                "scheduled_note_count": (
                    assist_analyzer.scheduled_note_count
                    if assist_analyzer is not None
                    else 0
                ),
                "actions": assist.actions if assist is not None else [],
            }
            if assist_profile is not None
            else None
        ),
    }
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps({"complete": True, **manifest}, ensure_ascii=False), flush=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture timestamped frames from the OPPO H.264 screen stream"
    )
    parser.add_argument("--serial", required=True, help="Exact ADB device serial")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--sample-fps", type=float, default=10.0)
    parser.add_argument("--capture-fps", type=int, default=60,
                        help="H.264 capture cadence; use 15 if 60 fps cannot start")
    parser.add_argument(
        "--start-tap",
        metavar="X,Y",
        help="Optional key coordinate to tap after capture begins",
    )
    parser.add_argument("--start-tap-count", type=int, default=0)
    parser.add_argument("--start-tap-delay-ms", type=float, default=250.0)
    parser.add_argument("--start-tap-interval-ms", type=float, default=500.0)
    parser.add_argument(
        "--assist-profile",
        choices=("auto",) + tuple(ASSIST_KEYBOARD_PROFILES),
        help=(
            "Best-effort live note scheduling used only to extend a capture; "
            "'auto' reads the keyboard off the screen"
        ),
    )
    parser.add_argument("--assist-speed-px-s", type=float, default=280.0)
    parser.add_argument("--assist-bpm", type=float, default=116.7)
    args = parser.parse_args()
    if args.capture_fps <= 0:
        parser.error("--capture-fps must be positive")
    start_tap = None
    if args.start_tap is not None:
        try:
            x_value, y_value = args.start_tap.split(",", 1)
            start_tap = (int(x_value), int(y_value))
        except ValueError as exc:
            parser.error(f"--start-tap must be X,Y: {exc}")
    capture_sample(
        serial=args.serial,
        output_dir=args.output,
        duration_seconds=args.duration,
        sample_fps=args.sample_fps,
        capture_fps=args.capture_fps,
        start_tap=start_tap,
        start_tap_count=args.start_tap_count,
        start_tap_delay_ms=args.start_tap_delay_ms,
        start_tap_interval_ms=args.start_tap_interval_ms,
        assist_profile=args.assist_profile,
        assist_speed_px_s=args.assist_speed_px_s,
        assist_bpm=args.assist_bpm,
    )


if __name__ == "__main__":
    main()
