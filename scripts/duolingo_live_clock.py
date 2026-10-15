"""Estimate a song's beat period from its scrolling measure lines.

The first key press supplies the playback epoch.  Screen motion supplies the
period, so a long performance need not keep the opening tempo estimate forever.
All distances are measured from the current score; no song tempo or time
signature lives in this module.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import threading

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class TempoReading:
    beat_ms: float
    span_beats: float
    residual_px: float
    reference_ns: int | None = None
    phase_at_reference_px: float | None = None
    speed_px_s: float | None = None


class VisualClockLost(RuntimeError):
    """The measure-line phase no longer describes one continuous scroll."""


class VisualBeatClock:
    """Keep one beat timeline while refining its period from live scroll.

    ``anchor_ns`` is the actual launch-key send time.  Changing the measured
    period preserves the current beat position, so a new fit cannot jump a
    note that is already close to its deadline.
    """

    def __init__(
        self,
        *,
        anchor_ns: int,
        anchor_beat: float,
        beat_ms: float,
        px_per_beat: float,
        beats_per_measure: int,
    ) -> None:
        if beat_ms <= 0 or px_per_beat <= 0 or beats_per_measure <= 0:
            raise ValueError("beat time and score geometry must be positive")
        self.anchor_ns = anchor_ns
        self.anchor_beat = anchor_beat
        self.beat_ms = beat_ms
        self.px_per_beat = px_per_beat
        self.beats_per_measure = beats_per_measure
        self._samples: deque[tuple[int, float]] = deque()
        self._last_reading: TempoReading | None = None

    @property
    def last_reading(self) -> TempoReading | None:
        return self._last_reading

    def due_ns(self, beat: float, *, offset_ms: float = 0.0) -> int:
        return self.anchor_ns + round(
            ((beat - self.anchor_beat) * self.beat_ms + offset_ms) * 1_000_000
        )

    def adopt(self, reading: TempoReading, *, now_ns: int) -> None:
        """Use a new period without moving the beat under the playhead."""
        current_beat = self.anchor_beat + (
            now_ns - self.anchor_ns
        ) / (self.beat_ms * 1_000_000)
        self.anchor_beat = current_beat
        self.anchor_ns = now_ns
        self.beat_ms = reading.beat_ms

    def restart_at(self, beat: float, now_ns: int) -> None:
        """Begin a new scrolling phrase at a visually confirmed prompt note."""
        self.anchor_beat = beat
        self.anchor_ns = now_ns
        self._samples.clear()
        self._last_reading = None

    def visual_due_ns(
        self, beat: float, *, judgment_x: float, engraving_delta: float,
        input_to_visual_ms: float, lead_ms: float = 0.0,
        relative_x_px: float | None = None,
    ) -> int:
        """Predict a note's crossing, compensating the measured visual lag.

        Project from the newest observed barline, not the startup regression's
        old intercept. Early frame-arrival jitter can skew that long
        extrapolation even when the nearby barline is accurately located.
        """
        reading = self._last_reading
        if reading is None or not self._samples:
            raise ValueError("visual beat clock is not calibrated")
        target_phase = judgment_x - (
            relative_x_px if relative_x_px is not None
            else (beat + engraving_delta) * self.px_per_beat
        )
        latest_ns, latest_phase = self._samples[-1]
        seconds = (latest_phase - target_phase) * self.beat_ms / (
            self.px_per_beat * 1000
        )
        return (latest_ns + round(seconds * 1_000_000_000)
                - round((input_to_visual_ms + lead_ms) * 1_000_000))

    def observe(self, timestamp_ns: int, phase_px: float) -> TempoReading | None:
        """Fit motion over recent measures and reject a lost barline identity."""
        if self._samples:
            previous_ns, previous_phase = self._samples[-1]
            elapsed_s = (timestamp_ns - previous_ns) / 1_000_000_000
            if elapsed_s <= 0:
                raise ValueError("frame timestamps must increase")
            movement_px = previous_phase - phase_px
            # A scrolling score moves left.  Small frame-to-frame detection
            # noise is fine; a rightward jump is a reset or lost line identity.
            if movement_px < -self.px_per_beat / 10:
                raise VisualClockLost("measure-line phase moved right")
            if self._last_reading is not None:
                expected_px = elapsed_s * self.px_per_beat * 1000 / self._last_reading.beat_ms
                if movement_px > expected_px * 3 + self.px_per_beat / 4:
                    raise VisualClockLost("measure-line phase jumped left")
        self._samples.append((timestamp_ns, phase_px))

        # Four measures are long enough to suppress frame-arrival jitter, while
        # the window length scales with the score's own meter and geometry.
        window_px = self.px_per_beat * self.beats_per_measure * 4
        while (
            len(self._samples) > 3
            and self._samples[0][1] - phase_px > window_px
        ):
            self._samples.popleft()
        if len(self._samples) < 3:
            return None
        span_px = self._samples[0][1] - phase_px
        if span_px < self.px_per_beat:
            return None

        times = np.asarray([s[0] for s in self._samples], dtype=np.float64)
        phases = np.asarray([s[1] for s in self._samples], dtype=np.float64)
        seconds = (times - times[0]) / 1_000_000_000
        slope, intercept = np.polyfit(seconds, phases, 1)
        residuals = phases - (slope * seconds + intercept)
        median_residual = float(np.median(np.abs(residuals)))
        keep = np.abs(residuals) <= max(self.px_per_beat / 8, median_residual * 3)
        if keep.sum() >= 3 and keep.sum() < len(times):
            slope, intercept = np.polyfit(seconds[keep], phases[keep], 1)
            residuals = phases[keep] - (slope * seconds[keep] + intercept)
        if slope >= 0:
            return None
        reading = TempoReading(
            beat_ms=float(-self.px_per_beat / slope * 1000),
            span_beats=span_px / self.px_per_beat,
            residual_px=float(np.median(np.abs(residuals))),
            reference_ns=int(times[0]),
            phase_at_reference_px=float(intercept),
            speed_px_s=float(slope),
        )
        self._last_reading = reading
        return reading


class KeyHighlightLatency:
    """Re-measure input plus video delay from each visible key press."""

    def __init__(
        self, opening: Image.Image, points: dict[str, tuple[int, int]],
    ) -> None:
        half_w = max(1, round(opening.width * 0.025))
        half_h = max(1, round(opening.height * 0.06))
        self._boxes = {
            pitch: (
                max(0, x - half_w), max(0, y - half_h),
                min(opening.width, x + half_w), min(opening.height, y + half_h),
            ) for pitch, (x, y) in points.items()
        }
        self._baseline = {
            pitch: self._luminance(opening, pitch) for pitch in points
        }
        self._latest_values = self._baseline.copy()
        self._pending: dict[str, tuple[int, int | None]] = {}
        self._readings: list[dict] = []
        self._high_candidate: dict | None = None
        self._release_pending: dict[str, tuple[int, int | None]] = {}
        self._release_readings: list[dict] = []
        self._lock = threading.Lock()

    def _luminance(self, image: Image.Image, pitch: str) -> float:
        return float(np.asarray(image.crop(self._boxes[pitch]).convert("RGB")).mean())

    def mark_press(self, pitch: str, sent_ns: int) -> None:
        with self._lock:
            self._release_pending.pop(pitch, None)
            if pitch not in self._boxes:
                return
            if abs(self._latest_values[pitch] - self._baseline[pitch]) > 1.5:
                return  # still lit from an earlier press; onset is ambiguous
            # A frame from before the press cannot bound the highlight onset.
            # Decoder gaps would otherwise put their midpoint near the press
            # and report an implausibly short input/video delay.
            self._pending[pitch] = (sent_ns, None)

    def mark_release(self, pitch: str, sent_ns: int) -> None:
        with self._lock:
            if pitch not in self._boxes:
                return
            if abs(self._latest_values[pitch] - self._baseline[pitch]) <= 1.5:
                return  # no observed lit state to time the return from
            self._release_pending[pitch] = (sent_ns, None)

    def observe(self, image: Image.Image, received_ns: int) -> None:
        values = {
            pitch: self._luminance(image, pitch) for pitch in self._boxes
        }
        with self._lock:
            for pitch, (sent_ns, previous_ns) in tuple(self._pending.items()):
                if received_ns <= sent_ns:
                    continue
                value = values[pitch]
                if abs(value - self._baseline[pitch]) > 1.5:
                    onset_ns = (
                        (previous_ns + received_ns) // 2
                        if previous_ns is not None else received_ns
                    )
                    latency_ms = (onset_ns - sent_ns) / 1_000_000
                    if 0 <= latency_ms <= 2000:
                        recent = [
                            reading["latency_ms"] for reading in self._readings
                            if reading["accepted"]
                        ][-5:]
                        # Repeated notes can leave a key visually lit just as
                        # the next press is sent.  A 20 ms apparent onset must
                        # not poison startup calibration after one credible
                        # opening-key sample.
                        baseline = (
                            float(np.median(recent)) if len(recent) >= 3
                            else max(recent[-1], float(np.median(recent)))
                            if recent else None
                        )
                        high_jump = (
                            baseline is not None and latency_ms > baseline * 1.4
                        )
                        previous = self._high_candidate
                        confirmed_high_jump = (
                            high_jump and previous is not None
                            and abs(previous["latency_ms"] - latency_ms) <= 50
                        )
                        if confirmed_high_jump:
                            previous["accepted"] = True
                        accepted = (
                            baseline is None
                            or baseline * 0.75 <= latency_ms <= baseline * 1.4
                            or confirmed_high_jump
                        )
                        self._readings.append({
                            "pitch": pitch, "sent_ns": sent_ns,
                            "onset_ns": onset_ns, "latency_ms": latency_ms,
                            "accepted": accepted,
                        })
                        if high_jump and not accepted:
                            self._high_candidate = self._readings[-1]
                        elif accepted:
                            self._high_candidate = None
                    del self._pending[pitch]
                elif received_ns - sent_ns > 2_000_000_000:
                    del self._pending[pitch]
                else:
                    self._pending[pitch] = (sent_ns, received_ns)
            for pitch, (sent_ns, previous_ns) in tuple(self._release_pending.items()):
                if received_ns <= sent_ns:
                    continue
                if abs(values[pitch] - self._baseline[pitch]) <= 1.5:
                    onset_ns = (
                        (previous_ns + received_ns) // 2
                        if previous_ns is not None else received_ns
                    )
                    delay_ms = (onset_ns - sent_ns) / 1_000_000
                    if 0 <= delay_ms <= 2000:
                        self._release_readings.append({
                            "pitch": pitch, "sent_ns": sent_ns,
                            "onset_ns": onset_ns, "latency_ms": delay_ms,
                        })
                    del self._release_pending[pitch]
                elif received_ns - sent_ns > 2_000_000_000:
                    del self._release_pending[pitch]
                else:
                    self._release_pending[pitch] = (sent_ns, received_ns)
            self._latest_values = values

    @property
    def latency_ms(self) -> float | None:
        with self._lock:
            recent = [
                reading["latency_ms"] for reading in self._readings
                if reading["accepted"]
            ][-3:]
            if not recent:
                return None
            return float(np.median(recent))

    @property
    def scheduling_latency_ms(self) -> float | None:
        """Follow visual delay while checking it against key releases."""
        with self._lock:
            accepted = [
                reading["latency_ms"] for reading in self._readings
                if reading["accepted"]
            ]
            recent = accepted[-3:]
            if not recent:
                return None
            median = float(np.median(recent))
            stable_press = float(np.median(accepted[-5:]))
            if len(recent) < 3:
                if self._release_readings:
                    release = float(np.median([
                        reading["latency_ms"]
                        for reading in self._release_readings[-3:]
                    ]))
                    if release >= stable_press * 0.75:
                        return min(max(median, release), median + 80.0)
                return median
            estimate = min(max(median, recent[-1]), median + 55.0)
            if len(self._release_readings) >= 3:
                release = float(np.median([
                    reading["latency_ms"]
                    for reading in self._release_readings[-5:]
                ]))
                # Press and release share the ADB/video path. A missed or
                # occluded key highlight can look like a persistent rise even
                # while release transitions still show steady transport delay.
                if release >= stable_press * 0.75:
                    estimate = min(estimate, release + 80.0)
            return estimate

    @property
    def release_latency_ms(self) -> float | None:
        with self._lock:
            if not self._release_readings:
                return None
            return float(np.median([
                reading["latency_ms"] for reading in self._release_readings[-3:]
            ]))

    @property
    def release_readings(self) -> list[dict]:
        with self._lock:
            return self._release_readings.copy()

    @property
    def readings(self) -> list[dict]:
        with self._lock:
            return self._readings.copy()
