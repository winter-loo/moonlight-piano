"""Detect and track scrolling Duolingo Music measure barlines."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class BarlineCandidate:
    x: float
    coverage: float
    width: int


@dataclass(frozen=True)
class TrackedBarline:
    line_id: int
    x: float
    coverage: float


@dataclass(frozen=True)
class MeasureTrackUpdate:
    timestamp_ns: int
    state: str
    spacing_px: float | None
    phase_px: float | None
    instantaneous_speed_px_s: float | None
    fitted_speed_px_s: float | None
    fit_r_squared: float | None
    candidates: tuple[BarlineCandidate, ...]
    barlines: tuple[TrackedBarline, ...]
    missing_frames: int


@dataclass(frozen=True)
class TempoEstimate:
    beats_per_measure: float
    spacing_px: float
    speed_sample_count: int
    crossing_count: int
    crossing_period_count: int
    crossing_segment_count: int
    speed_px_s: float
    measure_seconds_from_speed: float
    measure_seconds_from_crossings: float | None
    bpm_from_speed: float
    bpm_from_crossings: float | None
    bpm: float
    period_disagreement_ms: float | None
    crossing_period_range_ms: float | None
    maximum_crossing_error_ms: float | None
    bpm_range: float
    confidence: str


def detect_measure_barline_candidates(
    image: Image.Image,
    staff_lines: Sequence[int],
    judgment_line_x: int,
    *,
    minimum_coverage: float = 0.60,
) -> tuple[BarlineCandidate, ...]:
    """Find staff-colored barlines, allowing noteheads to cover part of them."""
    if len(staff_lines) != 5:
        raise ValueError("exactly five staff lines are required")

    array = np.asarray(image.convert("RGB"))
    staff_top = int(min(staff_lines))
    staff_bottom = int(max(staff_lines))
    y_values = np.arange(staff_top, staff_bottom + 1)
    usable_rows = np.ones(y_values.shape, dtype=bool)
    for staff_y in staff_lines:
        usable_rows &= np.abs(y_values - int(staff_y)) > 4

    width = image.width
    minimum_x = round(width * 0.08)
    maximum_x = round(width * 0.92)
    staff_color = np.median(
        array[np.asarray(staff_lines), minimum_x : maximum_x + 1, :],
        axis=(0, 1),
    )
    staff_strip = array[y_values[usable_rows], :, :]
    staff_ink = np.max(
        np.abs(staff_strip.astype(np.int16) - staff_color), axis=2,
    ) <= 22
    coverage = staff_ink.mean(axis=0)

    eligible = coverage >= minimum_coverage
    eligible[:minimum_x] = False
    eligible[maximum_x + 1 :] = False
    # A judgment line continues outside the staff. A barline ends at its edges.
    for outside in (
        array[max(0, staff_top - 12) : max(0, staff_top - 4)],
        array[min(image.height, staff_bottom + 5) : min(image.height, staff_bottom + 13)],
    ):
        if len(outside):
            continuation = np.max(
                np.abs(outside.astype(np.int16) - staff_color), axis=2,
            ) <= 22
            eligible &= continuation.mean(axis=0) < 0.5

    candidates: list[BarlineCandidate] = []
    start: int | None = None
    for x in range(width + 1):
        active = x < width and bool(eligible[x])
        if active and start is None:
            start = x
        elif not active and start is not None:
            stop = x
            group = coverage[start:stop]
            strongest_offset = int(np.argmax(group))
            candidates.append(
                BarlineCandidate(
                    x=float(start),
                    coverage=float(group[strongest_offset]),
                    width=stop - start,
                )
            )
            start = None
    return tuple(candidates)


def infer_measure_spacing(
    candidates: Sequence[BarlineCandidate],
    *,
    minimum_spacing: float = 250.0,
    maximum_spacing: float = 800.0,
    tolerance: float = 8.0,
) -> float | None:
    """Infer the repeated barline spacing from candidate pair differences."""
    differences = sorted(
        right.x - left.x
        for index, left in enumerate(candidates)
        for right in candidates[index + 1 :]
        if minimum_spacing <= right.x - left.x <= maximum_spacing
    )
    if not differences:
        return None

    best_cluster: list[float] = []
    for difference in differences:
        cluster = [
            value for value in differences if abs(value - difference) <= tolerance
        ]
        if len(cluster) > len(best_cluster):
            best_cluster = cluster
    return float(np.median(best_cluster))


def select_regular_barlines(
    candidates: Sequence[BarlineCandidate],
    spacing_px: float,
    *,
    tolerance: float = 8.0,
) -> tuple[BarlineCandidate, ...]:
    """Keep the strongest candidate chain repeating at one measure spacing."""
    if spacing_px <= 0:
        raise ValueError("spacing_px must be positive")
    if not candidates:
        return ()

    best: tuple[BarlineCandidate, ...] = ()
    best_strength = -1.0
    for anchor in candidates:
        members = []
        for candidate in candidates:
            periods = round((candidate.x - anchor.x) / spacing_px)
            expected_x = anchor.x + periods * spacing_px
            if abs(candidate.x - expected_x) <= tolerance:
                members.append(candidate)
        ordered = tuple(sorted(members, key=lambda item: item.x))
        strength = sum(item.coverage for item in ordered)
        if len(ordered) > len(best) or (
            len(ordered) == len(best) and strength > best_strength
        ):
            best = ordered
            best_strength = strength
    return best


class MeasureLineTracker:
    """Track the unwrapped phase and speed of regularly spaced barlines."""

    def __init__(
        self,
        *,
        spacing_px: float | None = None,
        history_size: int = 24,
        spacing_tolerance_px: float = 8.0,
        steady_r_squared: float = 0.98,
        moving_speed_threshold_px_s: float = 30.0,
        initial_phase_px: float | None = None,
    ) -> None:
        self.spacing_px = spacing_px
        self._spacing_tolerance_px = spacing_tolerance_px
        self._steady_r_squared = steady_r_squared
        self._moving_speed_threshold_px_s = moving_speed_threshold_px_s
        self._history: deque[tuple[int, float]] = deque(maxlen=history_size)
        self._phase_px: float | None = initial_phase_px
        self._timestamp_ns: int | None = None
        self._last_input_timestamp_ns: int | None = None
        self._fitted_speed_px_s: float | None = None
        self._missing_frames = 0
        self._discontinuity_frames = 0

    def update(
        self,
        timestamp_ns: int,
        candidates: Sequence[BarlineCandidate],
    ) -> MeasureTrackUpdate:
        if (
            self._last_input_timestamp_ns is not None
            and timestamp_ns <= self._last_input_timestamp_ns
        ):
            raise ValueError("timestamps must be strictly increasing")
        self._last_input_timestamp_ns = timestamp_ns

        if self.spacing_px is None:
            self.spacing_px = infer_measure_spacing(
                candidates,
                tolerance=self._spacing_tolerance_px,
            )
        selected = (
            select_regular_barlines(
                candidates,
                self.spacing_px,
                tolerance=self._spacing_tolerance_px,
            )
            if self.spacing_px is not None
            else ()
        )

        if not selected or self.spacing_px is None:
            self._missing_frames += 1
            return MeasureTrackUpdate(
                timestamp_ns=timestamp_ns,
                state="missing",
                spacing_px=self.spacing_px,
                phase_px=self._phase_px,
                instantaneous_speed_px_s=None,
                fitted_speed_px_s=self._fitted_speed_px_s,
                fit_r_squared=None,
                candidates=tuple(candidates),
                barlines=(),
                missing_frames=self._missing_frames,
            )

        reference_phase = self._phase_px
        if (
            reference_phase is not None
            and self._timestamp_ns is not None
            and self._fitted_speed_px_s is not None
        ):
            elapsed_s = (timestamp_ns - self._timestamp_ns) / 1_000_000_000
            reference_phase += self._fitted_speed_px_s * elapsed_s

        if reference_phase is None:
            phase_px = min(candidate.x for candidate in selected)
        else:
            mapped_phases = [
                candidate.x
                + round((reference_phase - candidate.x) / self.spacing_px)
                * self.spacing_px
                for candidate in selected
            ]
            phase_px = float(np.median(mapped_phases))

        if (
            reference_phase is not None
            and self._phase_px is not None
            and self._fitted_speed_px_s is not None
            and self._fitted_speed_px_s < -self._moving_speed_threshold_px_s
            and len(self._history) >= 4
            and abs(phase_px - reference_phase) > self.spacing_px / 8
            and not (reference_phase < phase_px < self._phase_px)
        ):
            # A single spurious vertical stroke can win the barline-chain
            # selection. Do not let it relabel every following measure. A
            # slower-than-predicted frame that still moved left, however, is
            # not a reset: accept it and refit the speed after the frame gap.
            self._discontinuity_frames += 1
            self._missing_frames += 1
            return MeasureTrackUpdate(
                timestamp_ns=timestamp_ns,
                state=("resetting" if self._discontinuity_frames >= 3 else "missing"),
                spacing_px=self.spacing_px,
                phase_px=self._phase_px,
                instantaneous_speed_px_s=None,
                fitted_speed_px_s=self._fitted_speed_px_s,
                fit_r_squared=None,
                candidates=tuple(candidates),
                barlines=(),
                missing_frames=self._missing_frames,
            )
        if self._phase_px is not None and self._timestamp_ns is not None:
            if phase_px - self._phase_px > self.spacing_px / 100:
                # A decoder/line-detection wobble can make one frame appear
                # to move right. Require a sustained reversal before calling
                # it a score reset, just as with a large phase jump above.
                self._discontinuity_frames += 1
                self._missing_frames += 1
                return MeasureTrackUpdate(
                    timestamp_ns=timestamp_ns,
                    state=("resetting" if self._discontinuity_frames >= 3 else "missing"),
                    spacing_px=self.spacing_px,
                    phase_px=self._phase_px,
                    instantaneous_speed_px_s=None,
                    fitted_speed_px_s=self._fitted_speed_px_s,
                    fit_r_squared=None,
                    candidates=tuple(candidates),
                    barlines=(),
                    missing_frames=self._missing_frames,
                )
        self._discontinuity_frames = 0

        instantaneous_speed: float | None = None
        if self._phase_px is not None and self._timestamp_ns is not None:
            elapsed_s = (timestamp_ns - self._timestamp_ns) / 1_000_000_000
            instantaneous_speed = (phase_px - self._phase_px) / elapsed_s

        self._phase_px = phase_px
        self._timestamp_ns = timestamp_ns
        self._missing_frames = 0
        self._history.append((timestamp_ns, phase_px))
        fitted_speed, r_squared = self._fit_history()
        self._fitted_speed_px_s = fitted_speed

        if instantaneous_speed is not None and instantaneous_speed > 60.0:
            state = "resetting"
        elif (
            fitted_speed is not None
            and abs(fitted_speed) < self._moving_speed_threshold_px_s
        ):
            state = "waiting"
        elif (
            fitted_speed is not None
            and fitted_speed < -self._moving_speed_threshold_px_s
            and r_squared is not None
            and r_squared >= self._steady_r_squared
        ):
            state = "steady"
        else:
            state = "accelerating"

        tracked = tuple(
            TrackedBarline(
                line_id=round((candidate.x - phase_px) / self.spacing_px),
                x=candidate.x,
                coverage=candidate.coverage,
            )
            for candidate in selected
        )
        return MeasureTrackUpdate(
            timestamp_ns=timestamp_ns,
            state=state,
            spacing_px=self.spacing_px,
            phase_px=phase_px,
            instantaneous_speed_px_s=instantaneous_speed,
            fitted_speed_px_s=fitted_speed,
            fit_r_squared=r_squared,
            candidates=tuple(candidates),
            barlines=tracked,
            missing_frames=0,
        )

    def _fit_history(self) -> tuple[float | None, float | None]:
        if len(self._history) < 3:
            return None, None
        timestamps = np.array([item[0] for item in self._history], dtype=np.float64)
        positions = np.array([item[1] for item in self._history], dtype=np.float64)
        seconds = (timestamps - timestamps[0]) / 1_000_000_000
        slope, intercept = np.polyfit(seconds, positions, 1)
        predicted = slope * seconds + intercept
        residual_sum = float(np.sum((positions - predicted) ** 2))
        total_sum = float(np.sum((positions - positions.mean()) ** 2))
        r_squared = 1.0 if total_sum == 0 else 1.0 - residual_sum / total_sum
        return float(slope), r_squared


class MeasureTempoEstimator:
    """Combine barline velocity and judgment-line crossings into a tempo."""

    def __init__(self, *, beats_per_measure: float) -> None:
        if beats_per_measure <= 0:
            raise ValueError("beats_per_measure must be positive")
        self._beats_per_measure = beats_per_measure
        self._steady_speeds: list[float] = []
        self._previous_phase: tuple[int, float] | None = None
        self._crossings: list[tuple[int, int, int]] = []
        self._segment_id = 0
        self._segment_active = False
        self._spacing_px: float | None = None

    @property
    def crossing_times_ns(self) -> dict[int, int]:
        return {line_id: timestamp_ns for _, line_id, timestamp_ns in self._crossings}

    @property
    def crossing_records(self) -> tuple[tuple[int, int, int], ...]:
        """Return ``(segment_id, line_id, timestamp_ns)`` records."""
        return tuple(self._crossings)

    def observe(
        self,
        update: MeasureTrackUpdate,
        *,
        judgment_line_x: float,
    ) -> None:
        if update.spacing_px is not None:
            self._spacing_px = update.spacing_px

        moving = (
            update.state in {"accelerating", "steady"}
            and update.fitted_speed_px_s is not None
            and update.fitted_speed_px_s < 0
        )
        if not moving:
            if self._segment_active and update.state in {
                "waiting",
                "resetting",
            }:
                self._segment_id += 1
                self._segment_active = False
                self._previous_phase = None
            return

        self._segment_active = True
        if (
            update.state == "steady"
            and update.fitted_speed_px_s is not None
            and update.fitted_speed_px_s < 0
        ):
            self._steady_speeds.append(update.fitted_speed_px_s)
        if update.phase_px is None or self._spacing_px is None:
            return

        if self._previous_phase is not None:
            previous_ns, previous_phase = self._previous_phase
            current_phase = update.phase_px
            if current_phase < previous_phase:
                first_id = int(
                    np.floor((judgment_line_x - previous_phase) / self._spacing_px)
                ) + 1
                last_id = int(
                    np.floor((judgment_line_x - current_phase) / self._spacing_px)
                )
                for line_id in range(first_id, last_id + 1):
                    previous_distance = (
                        previous_phase + line_id * self._spacing_px - judgment_line_x
                    )
                    current_distance = (
                        current_phase + line_id * self._spacing_px - judgment_line_x
                    )
                    distance_span = previous_distance - current_distance
                    fraction = previous_distance / distance_span
                    crossing_ns = previous_ns + round(
                        fraction * (update.timestamp_ns - previous_ns)
                    )
                    self._crossings.append(
                        (self._segment_id, line_id, crossing_ns)
                    )
        self._previous_phase = (update.timestamp_ns, update.phase_px)

    def estimate(self) -> TempoEstimate | None:
        if self._spacing_px is None or not self._steady_speeds:
            return None

        speeds = np.asarray(self._steady_speeds, dtype=np.float64)
        speed_px_s = float(np.median(speeds))
        speed_period = self._spacing_px / abs(speed_px_s)
        segments: dict[int, list[tuple[int, int]]] = {}
        for segment_id, line_id, timestamp_ns in self._crossings:
            segments.setdefault(segment_id, []).append((line_id, timestamp_ns))
        contiguous_segments: list[list[tuple[int, int]]] = []
        for records in segments.values():
            ordered = sorted(records)
            current: list[tuple[int, int]] = []
            for record in ordered:
                if current and record[0] != current[-1][0] + 1:
                    contiguous_segments.append(current)
                    current = []
                current.append(record)
            if current:
                contiguous_segments.append(current)
        best_segment = max(contiguous_segments, key=len, default=[])

        crossing_periods = [
            (right_ns - left_ns) / 1_000_000_000
            for (_, left_ns), (_, right_ns) in zip(
                best_segment, best_segment[1:]
            )
        ]
        crossing_period = None
        maximum_crossing_error_ms = None
        rolling_bpms: list[float] = []
        if len(best_segment) >= 2:
            line_ids = np.asarray(
                [record[0] for record in best_segment], dtype=np.float64
            )
            crossing_seconds = np.asarray(
                [
                    (record[1] - best_segment[0][1]) / 1_000_000_000
                    for record in best_segment
                ],
                dtype=np.float64,
            )
            crossing_period, intercept = np.polyfit(
                line_ids, crossing_seconds, 1
            )
            crossing_period = float(crossing_period)
            predicted = crossing_period * line_ids + intercept
            maximum_crossing_error_ms = float(
                np.max(np.abs(crossing_seconds - predicted)) * 1000.0
            )
            window_size = min(5, len(best_segment))
            for start in range(len(best_segment) - window_size + 1):
                window_ids = line_ids[start : start + window_size]
                window_times = crossing_seconds[start : start + window_size]
                window_period, _ = np.polyfit(window_ids, window_times, 1)
                rolling_bpms.append(
                    self._beats_per_measure * 60.0 / float(window_period)
                )
        crossing_period_range_ms = (
            (max(crossing_periods) - min(crossing_periods)) * 1000.0
            if len(crossing_periods) >= 2
            else None
        )
        bpm_from_speed = self._beats_per_measure * 60.0 / speed_period
        bpm_from_crossings = (
            self._beats_per_measure * 60.0 / crossing_period
            if crossing_period is not None
            else None
        )
        disagreement_ms = (
            abs(speed_period - crossing_period) * 1000.0
            if crossing_period is not None
            else None
        )
        if rolling_bpms:
            bpm_range = max(rolling_bpms) - min(rolling_bpms)
        else:
            speed_bpms = (
                self._beats_per_measure
                * 60.0
                * np.abs(speeds)
                / self._spacing_px
            )
            bpm_range = float(np.max(speed_bpms) - np.min(speed_bpms))

        if (
            len(self._steady_speeds) >= 5
            and len(crossing_periods) >= 5
            and disagreement_ms is not None
            and disagreement_ms < 30.0
            and maximum_crossing_error_ms is not None
            and maximum_crossing_error_ms < 30.0
            and bpm_range < 1.0
        ):
            confidence = "high"
        elif len(self._steady_speeds) >= 3 and (
            disagreement_ms is None or disagreement_ms < 75.0
        ):
            confidence = "medium"
        else:
            confidence = "low"

        bpm = (
            float(np.median([bpm_from_speed, bpm_from_crossings]))
            if bpm_from_crossings is not None
            else bpm_from_speed
        )
        return TempoEstimate(
            beats_per_measure=self._beats_per_measure,
            spacing_px=self._spacing_px,
            speed_sample_count=len(self._steady_speeds),
            crossing_count=len(best_segment),
            crossing_period_count=len(crossing_periods),
            crossing_segment_count=len(contiguous_segments),
            speed_px_s=speed_px_s,
            measure_seconds_from_speed=speed_period,
            measure_seconds_from_crossings=crossing_period,
            bpm_from_speed=bpm_from_speed,
            bpm_from_crossings=bpm_from_crossings,
            bpm=bpm,
            period_disagreement_ms=disagreement_ms,
            crossing_period_range_ms=crossing_period_range_ms,
            maximum_crossing_error_ms=maximum_crossing_error_ms,
            bpm_range=bpm_range,
            confidence=confidence,
        )
