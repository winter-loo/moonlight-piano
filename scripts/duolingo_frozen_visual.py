"""Record a frozen performance's live score motion on the input clock.

This observer never schedules keys.  It keeps decoded-frame arrival times,
unwrapped measure-line positions, and visible key onset times for one run.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import threading
import time

from PIL import Image

from duolingo_live_clock import KeyHighlightLatency
from duolingo_measure_tracker import (
    MeasureLineTracker,
    detect_measure_barline_candidates,
)


def _screen_reader():
    path = Path(__file__).with_name("duolingo-read-screen-notes.py")
    spec = importlib.util.spec_from_file_location("duolingo_frozen_screen_reader", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FrozenVisualObserver:
    def __init__(
        self, *, adb: str, serial: str,
        key_points: dict[str, tuple[int, int]], output_dir: Path,
    ) -> None:
        self._reader = _screen_reader()
        self._pump = self._reader.H264FramePump(
            adb, serial, encoder_fps=30, output_fps=15, warmup_frames=10,
            archive_path=output_dir / "visual-recording.h264",
        )
        self._key_points = key_points
        self._output_path = output_dir / "visual-samples.json"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._samples: list[dict[str, object]] = []
        self._edges: list[dict[str, object]] = []
        self._error: str | None = None
        self._latency: KeyHighlightLatency | None = None

    def start(self) -> None:
        self._pump.start(timeout=10.0)
        opening, sequence, received_ns = self._pump.wait_for_timed_frame(
            after_sequence=-1, timeout=2.0,
        )
        context = self._reader.build_analysis_context(opening)
        if context.staff_lines is None:
            raise RuntimeError("visual observer could not find staff lines")
        self._staff = tuple(context.staff_lines)
        self._judgment_x = int(context.judgment_line_x)
        self._tracker = MeasureLineTracker()
        self._latency = KeyHighlightLatency(opening, self._key_points)
        self._record(opening, sequence, received_ns)
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _record(self, image: Image.Image, sequence: int, received_ns: int) -> None:
        candidates = detect_measure_barline_candidates(
            image, self._staff, self._judgment_x,
        )
        update = self._tracker.update(received_ns, candidates)
        self._latency.observe(image, received_ns)
        self._samples.append({
            "sequence": sequence,
            "received_ns": received_ns,
            "phase_px": update.phase_px,
            "spacing_px": update.spacing_px,
            "speed_px_s": update.fitted_speed_px_s,
            "state": update.state,
            "r_squared": update.fit_r_squared,
        })

    def _read(self) -> None:
        sequence = int(self._samples[-1]["sequence"])
        while not self._stop.is_set():
            try:
                image, sequence, received_ns = self._pump.wait_for_timed_frame(
                    after_sequence=sequence, timeout=1.0,
                )
                self._record(image, sequence, received_ns)
            except TimeoutError:
                continue
            except Exception as exc:
                self._error = repr(exc)
                break

    def mark(self, kind: str, pitch: str, sent_ns: int) -> None:
        self._edges.append({"kind": kind, "pitch": pitch, "sent_ns": sent_ns})
        if self._latency is not None:
            if kind == "DOWN":
                self._latency.mark_press(pitch, sent_ns)
            else:
                self._latency.mark_release(pitch, sent_ns)

    def latest_sample(self) -> dict[str, object]:
        """Return the latest decoded-frame measurement for the scheduler."""
        return dict(self._samples[-1])

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._pump.stop()
        self._output_path.write_text(json.dumps({
            "judgment_x": self._judgment_x,
            "staff_lines": self._staff,
            "samples": self._samples,
            "edges": self._edges,
            "key_onsets": self._latency.readings if self._latency else [],
            "key_releases": self._latency.release_readings if self._latency else [],
            "error": self._error,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def phase_correction_ms(
    current: dict[str, object], *, current_origin_ns: int,
    current_beat_ns: int, reference: list[dict[str, object]],
    reference_origin_ns: int, reference_beat_ns: int,
    now_ns: int, max_correction_ms: float = 450.0,
) -> float | None:
    """Positive correction delays notes when this run's score trails a reference."""
    if (
        current.get("state") != "steady"
        or current.get("phase_px") is None
        or float(current.get("r_squared") or 0) < 0.95
        or now_ns - int(current["received_ns"]) > 300_000_000
    ):
        return None
    beat = (int(current["received_ns"]) - current_origin_ns) / current_beat_ns
    valid = [sample for sample in reference if (
        sample.get("state") == "steady"
        and sample.get("phase_px") is not None
        and sample.get("speed_px_s") is not None
        and float(sample.get("r_squared") or 0) >= 0.95
    )]
    if not valid:
        return None
    nearest = min(
        valid,
        key=lambda sample: abs(
            (int(sample["received_ns"]) - reference_origin_ns)
            / reference_beat_ns - beat
        ),
    )
    reference_beat = (
        int(nearest["received_ns"]) - reference_origin_ns
    ) / reference_beat_ns
    if abs(reference_beat - beat) > 0.2:
        return None
    speed = float(nearest["speed_px_s"])
    if not -400.0 <= speed <= -150.0:
        return None
    reference_phase = float(nearest["phase_px"]) + (
        beat - reference_beat
    ) * reference_beat_ns / 1_000_000_000 * speed
    offset_ms = (
        float(current["phase_px"]) - reference_phase
    ) / -speed * 1000.0
    return max(-max_correction_ms, min(max_correction_ms, offset_ms))
