#!/usr/bin/env python3
"""Read Duolingo Music while playing it on one scrolling beat timeline.

``rehearse`` stops after the first playable measure following the launch.
``continuous`` keeps reading new measures and sending their confirmed notes
until the score stops, the screen is lost, or an optional run-time cap expires.
The initial tempo is a measured input. Continuous play aligns each later note
to the live barline motion and this run's observed key-highlight latency.
"""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass, field, replace
import importlib.util
import json
import math
from pathlib import Path
import queue
import sys
import threading
import time

import numpy as np
from PIL import Image

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import duolingo_keyboard_detect as kbdetect  # noqa: E402
from duolingo_pitch import apply_key_signature  # noqa: E402
from duolingo_live_clock import (  # noqa: E402
    KeyHighlightLatency, VisualBeatClock, VisualClockLost,
)
from duolingo_live_keys import LiveKeys  # noqa: E402
from duolingo_measure_tracker import (  # noqa: E402
    MeasureLineTracker,
    detect_measure_barline_candidates,
)
from duolingo_beat_grid import (  # noqa: E402
    BeatGridError, build_beat_grid, estimate_px_per_beat,
)
from duolingo_measure_tracker import infer_measure_spacing  # noqa: E402

REPO_ROOT = _SCRIPTS_DIR.parent
def load_script(alias: str, filename: str):
    spec = importlib.util.spec_from_file_location(alias, REPO_ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def log(stage: str, message: str, **fields) -> None:
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    print(f"[{stage}] {message} {extra}".rstrip(), file=sys.stderr, flush=True)


@dataclass
class ScrollSample:
    t_ms: float
    phase_px: float | None
    speed_px_s: float | None
    spacing_px: float | None
    r_squared: float | None
    state: str


@dataclass
class LedgerNote:
    beat: float
    pitch: str
    duration_beats: float | None
    hold_beats: float | None
    sightings: int = 1
    articulation_votes: dict[tuple[float | None, float | None], int] = field(
        default_factory=dict,
    )
    relative_x_samples: list[float] = field(default_factory=list)

    @property
    def relative_x_px(self) -> float | None:
        """Median notehead position relative to its measure-line phase."""
        if not self.relative_x_samples:
            return None
        return float(np.median(self.relative_x_samples))


@dataclass
class Ledger:
    """Notes keyed by their beat on the barline-anchored grid."""

    tolerance_beats: float = 0.25
    notes: list[LedgerNote] = field(default_factory=list)

    def add(
        self, beat: float, pitch: str,
        duration_beats: float | None, hold_beats: float | None,
        *, relative_x_px: float | None = None,
    ) -> bool:
        for note in self.notes:
            if note.pitch == pitch and abs(note.beat - beat) <= self.tolerance_beats:
                note.sightings += 1
                if relative_x_px is not None:
                    note.relative_x_samples.append(relative_x_px)
                articulation = (duration_beats, hold_beats)
                note.articulation_votes[articulation] = (
                    note.articulation_votes.get(articulation, 0) + 1
                )
                best = max(
                    note.articulation_votes,
                    key=note.articulation_votes.__getitem__,
                )
                note.duration_beats, note.hold_beats = best
                return False
        self.notes.append(LedgerNote(
            beat, pitch, duration_beats, hold_beats,
            articulation_votes={(duration_beats, hold_beats): 1},
            relative_x_samples=(
                [relative_x_px] if relative_x_px is not None else []
            ),
        ))
        return True

    def ordered(self) -> list[LedgerNote]:
        return sorted(self.notes, key=lambda n: n.beat)

    def confirmed(
        self, min_sightings: int, px_per_beat: float | None = None,
    ) -> list[LedgerNote]:
        """Notes the readings agree on.

        A single frame whose grid offset landed on the wrong alias contributes
        a whole phantom line half a beat off, and a misread pitch contributes a
        rival note on an occupied beat.  Both show up once or twice against a
        real note's dozens, so the ledger's own tally separates them: require
        corroboration, and where two pitches claim one beat keep the one the
        readings favour.
        """
        best: dict[float, LedgerNote] = {}
        for note in self.notes:
            if note.sightings < min_sightings:
                continue
            current = best.get(note.beat)
            if current is None or note.sightings > current.sightings:
                best[note.beat] = note
        strongest_first = sorted(
            best.values(), key=lambda n: (-n.sightings, n.beat),
        )
        accepted: list[LedgerNote] = []
        for note in strongest_first:
            if any(
                note.pitch == earlier.pitch
                and note.duration_beats is not None
                and earlier.duration_beats is not None
                and min(
                    note.beat + note.duration_beats,
                    earlier.beat + earlier.duration_beats,
                ) - max(note.beat, earlier.beat) > self.tolerance_beats
                and not (
                    px_per_beat is not None
                    and note.relative_x_px is not None
                    and earlier.relative_x_px is not None
                    and abs(note.relative_x_px - earlier.relative_x_px)
                    >= px_per_beat / 2
                )
                for earlier in accepted
            ):
                # Two renderings of one sustained note may land half a beat
                # apart. The better-supported interval owns that key; real
                # repeated eighths merely touch at their boundaries.
                continue
            accepted.append(note)
        return sorted(accepted, key=lambda n: n.beat)


def opening_start_confirmed(ledger: Ledger, pitch: str) -> bool:
    """The still prompt has exactly two independent reads before scrolling."""
    return any(note.pitch == pitch and note.sightings >= 2 for note in ledger.notes)


def has_start_prompt_icon(image: Image.Image, opening_image: Image.Image) -> bool:
    """Distinguish the prompt's X from the moving score's pause bars."""
    if image.size != opening_image.size:
        return False
    box = (100, 40, 155, 90)
    current = np.asarray(image.crop(box).convert("RGB"), dtype=np.int16)
    reference = np.asarray(opening_image.crop(box).convert("RGB"), dtype=np.int16)
    return float(np.abs(current - reference).mean()) < 8.0


def stable_prompt_candidate(
    candidate: tuple[float, float, int] | None,
    beat: float, x: float, now_ns: int,
) -> tuple[bool, tuple[float, float, int]]:
    """Require a prompt note to remain at the line while the score settles."""
    if candidate is None or candidate[0] != beat or abs(candidate[1] - x) > 8:
        return False, (beat, x, now_ns)
    return now_ns - candidate[2] >= 400_000_000, candidate


def prompt_transition_grace_ns(beat_ms: float, beats_per_measure: int) -> int:
    """Give a stopped score two measures to reveal a stable prompt."""
    return round(beat_ms * beats_per_measure * 2_000_000)


def key_signature_pitch(pitch: str, sharps: set[str]) -> str:
    """Apply a visually verified key signature to an unaltered note name."""
    if len(pitch) >= 2 and pitch[0] in sharps and pitch[1].isdigit():
        return f"{pitch[0]}#{pitch[1:]}"
    return pitch


def signed_pitch_from_signature(
    pitch: str, key_signature: tuple[int, int],
) -> str:
    """Apply the locked score signature to a natural quick-read pitch."""
    return apply_key_signature(pitch, key_signature)


def quick_pitch_near_x(
    image: Image.Image, staff_lines: tuple[int, int, int, int, int],
    expected_x: float,
) -> tuple[str, float] | None:
    """Read a filled notehead in a small crop just before its key is sent.

    This deliberately checks pitch only. The full reader remains responsible
    for beat, duration, accidentals, and repeated sightings.
    """
    w, h = image.size
    if expected_x < 30 or expected_x >= w - 30:
        return None
    top, line4, line3, line2, bottom = staff_lines
    step = (bottom - top) / 8.0
    names = ["A5", "G5", "F5", "E5", "D5", "C5", "B4",
             "A4", "G4", "F4", "E4", "D4", "C4", "B3", "A3"]
    centers_y = [top + (i - 2) * step for i in range(len(names))]
    radius = max(8, round(step * 0.63))
    x0 = max(0, round(expected_x) - radius - 10)
    y0 = max(0, round(min(centers_y)) - radius - 4)
    x1 = min(w, round(expected_x) + radius + 11)
    y1 = min(h, round(max(centers_y)) + radius + 5)
    arr = np.asarray(image.crop((x0, y0, x1, y1)).convert("RGB"))
    yy, xx = np.ogrid[-radius:radius + 1, -radius:radius + 1]
    disk = xx * xx + yy * yy <= radius * radius
    dark = np.all(arr < 130, axis=2)
    scores: list[tuple[float, str]] = []
    for name, y in zip(names, centers_y):
        best = 0.0
        for dy in (-3, 0, 3):
            cy = round(y + dy) - y0
            if cy - radius < 0 or cy + radius >= dark.shape[0]:
                continue
            for dx in (-8, -4, 0, 4, 8):
                cx = round(expected_x + dx) - x0
                window = dark[cy - radius:cy + radius + 1,
                              cx - radius:cx + radius + 1]
                best = max(best, float(window[disk].mean()))
        scores.append((best, name))
    scores.sort(reverse=True)
    if len(scores) < 2 or scores[0][0] < 0.70 or scores[0][0] - scores[1][0] < 0.02:
        return None
    return scores[0][1], scores[0][0]


def match_visible_prompt(
    events: list[dict], notes: list[LedgerNote], *, judgment_x: float,
    screen_width: int, sharps: set[str], min_beat: float, max_beat: float,
) -> tuple[LedgerNote, dict] | None:
    """Identify a stopped prompt by the notes following it, not one key alone."""
    ranked: list[tuple[int, LedgerNote, dict]] = []
    for note in notes:
        if not (min_beat <= note.beat <= max_beat) or note.relative_x_px is None:
            continue
        for visible in events:
            if (abs(visible["x"] - judgment_x) > 45
                    or key_signature_pitch(visible["pitch"], sharps)
                    != key_signature_pitch(note.pitch, sharps)):
                continue
            matches = 0
            for following in notes:
                # A four-beat prefix can repeat verbatim several times in one
                # song.  Compare everything visible over roughly two
                # measures; the screen bounds below discard offscreen notes.
                if (not note.beat <= following.beat <= note.beat + 8.0
                        or following.relative_x_px is None):
                    continue
                predicted_x = (visible["x"] + following.relative_x_px
                               - note.relative_x_px)
                if not judgment_x - 45 <= predicted_x <= screen_width + 15:
                    continue
                if any(
                    abs(event["x"] - predicted_x) <= 25
                    and key_signature_pitch(event["pitch"], sharps)
                    == key_signature_pitch(following.pitch, sharps)
                    for event in events
                ):
                    matches += 1
            ranked.append((matches, note, visible))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < 3:
        return None
    if len(ranked) > 1 and ranked[0][0] <= ranked[1][0]:
        return None
    return ranked[0][1], ranked[0][2]


def hold_ms_for(
    duration_beats: float | None, hold_beats: float | None,
    beat_ms: float, release_ms: float | None,
    long_release_ms: float | None = None,
) -> float:
    """Prefer the reader's articulation; a release override is explicit."""
    if release_ms is not None:
        if duration_beats is None:
            raise ValueError("note duration is unknown")
        return max(duration_beats * beat_ms - release_ms, 80.0)
    if long_release_ms is not None and duration_beats is not None and duration_beats >= 1.5:
        return max(duration_beats * beat_ms - long_release_ms, 80.0)
    if hold_beats is None:
        raise ValueError("note hold time is unknown")
    return max(hold_beats * beat_ms, 80.0)


def cap_repeated_eighth_hold(
    hold_ms: float, pitch: str, beat: float,
    next_pitch: str | None, next_beat: float | None, beat_ms: float,
) -> float:
    """Leave a release gap when a repeated eighth may be rescheduled early."""
    if (next_pitch == pitch and next_beat is not None
            and 0 < next_beat - beat <= 0.6):
        return min(hold_ms, max(80.0, beat_ms * 0.20))
    return hold_ms


def bounded_retrigger_due_ns(
    due_ns: int, *, pitch: str, beat: float, previous: dict | None,
    previous_sent_ns: int | None, beat_ms: float,
) -> int:
    """Keep a recalibrated clock from squeezing or stretching a same-key repeat."""
    if (previous is None or previous_sent_ns is None
            or previous["pitch"] != pitch or beat <= previous["beat"]):
        return due_ns
    beat_gap_ms = (beat - previous["beat"]) * beat_ms
    hold_ms = float(previous["hold_ms"])
    gap_ms = max(hold_ms + 25.0, beat_gap_ms * 0.65)
    earliest_ns = previous_sent_ns + round(gap_ms * 1_000_000)
    if beat - previous["beat"] <= 1.0 and not previous.get("prompt_restart"):
        latest_ns = previous_sent_ns + round(
            (beat_gap_ms + 25.0) * 1_000_000
        )
        return min(max(due_ns, earliest_ns), max(latest_ns, earliest_ns))
    return max(due_ns, earliest_ns)


def fixed_phrase_due_ns(
    beat: float, phrases: list[tuple[float, float, float]],
    sent_ns_by_beat: dict[float, int],
) -> int | None:
    """Use one played note as the clock for a short, measured phrase."""
    for first, last, period_ms in phrases:
        if first < beat <= last and first in sent_ns_by_beat:
            return sent_ns_by_beat[first] + round((beat - first) * period_ms * 1e6)
    return None


def rewind_played_beats(
    played_beats: set[float], sent_ns_by_beat: dict[float, int], beat: float,
) -> None:
    """Requeue inputs sent after a stopped score's actual prompt beat."""
    played_beats.difference_update({old for old in played_beats if old >= beat})
    for old in tuple(sent_ns_by_beat):
        if old >= beat:
            del sent_ns_by_beat[old]


def prompt_search_floor(last_played_beat: float, beats_per_measure: int) -> float:
    """Allow a checkpoint prompt to roll back across up to four measures."""
    return last_played_beat - 4 * beats_per_measure


def prompt_search_ceiling(
    last_played_beat: float, first_remaining_beat: float,
    beats_per_measure: int,
) -> float:
    """Allow an unplayed prompt later in the next two measures."""
    return max(first_remaining_beat + 2.0,
               last_played_beat + 2 * beats_per_measure)


def tempo_refinement_ready(
    *, measured_beat_ms: float, current_beat_ms: float,
    span_beats: float, residual_px: float,
    px_per_beat: float, beats_per_measure: int,
    first_update: bool, steady_speed_px_s: float | None = None,
    fit_r_squared: float | None = None,
) -> bool:
    """Trust an early large correction only when two motion fits agree."""
    large_correction = not (
        0.75 * current_beat_ms <= measured_beat_ms <= 1.25 * current_beat_ms
    )
    if large_correction:
        if not first_update:
            return (span_beats >= 2 * beats_per_measure
                    and residual_px <= px_per_beat / 8)
        if (span_beats < 1.5 * beats_per_measure
                or residual_px > px_per_beat / 16
                or steady_speed_px_s is None or steady_speed_px_s >= 0
                or fit_r_squared is None or fit_r_squared < 0.99):
            return False
        recent_beat_ms = px_per_beat * 1000 / -steady_speed_px_s
        return abs(recent_beat_ms / measured_beat_ms - 1) <= 0.08
    if span_beats < 2 * beats_per_measure or residual_px > px_per_beat / 8:
        return False
    if (first_update and span_beats < 3 * beats_per_measure
            and abs(measured_beat_ms / current_beat_ms - 1) > 0.03):
        return False
    return True


def should_commit_due(*, due_ns: int, now_ns: int, beat_ms: float,
                      lead_beats: float = 0.05) -> bool:
    """Freeze near onset before a late highlight sample can move a due key."""
    return due_ns - now_ns <= beat_ms * lead_beats * 1_000_000


class ScrollTracker:
    """Wrap the barline tracker into displacement, speed, and beat length."""

    def __init__(self, staff_lines, judgment_line_x,
                 *, initial_phase_px=None, spacing_px=None):
        self._staff = list(staff_lines)
        self._judgment_x = int(judgment_line_x)
        self._tracker = MeasureLineTracker(
            spacing_px=spacing_px, initial_phase_px=initial_phase_px,
        )
        self._origin_phase: float | None = None
        self.samples: list[ScrollSample] = []
        self._lock = threading.Lock()
        self._fault_reason: str | None = None
        self._resetting_reads = 0
        self._resetting_since_ms: float | None = None
        self._raw_barline_x: float | None = None
        self._last_raw_motion_ms: float | None = None
        self._latest_image: Image.Image | None = None
        self._latest_state = "missing"

    def lock_spacing(self, spacing_px: float) -> None:
        """Use the confirmed opening grid before unwrapping live barlines."""
        if self.samples:
            raise RuntimeError("cannot change measure spacing after scrolling starts")
        self._tracker.spacing_px = spacing_px

    def observe(self, image: Image.Image, t_ms: float) -> ScrollSample:
        candidates = detect_measure_barline_candidates(image, self._staff, self._judgment_x)
        try:
            update = self._tracker.update(int(t_ms * 1e6), candidates)
        except ValueError:
            return ScrollSample(t_ms, None, None, None, None, "missing")
        sample = ScrollSample(
            t_ms, update.phase_px, update.fitted_speed_px_s,
            update.spacing_px, update.fit_r_squared, update.state,
        )
        with self._lock:
            self._latest_image = image
            self._latest_state = update.state
            if candidates and update.spacing_px:
                raw_x = min(candidate.x for candidate in candidates)
                if self._raw_barline_x is not None:
                    displacement = raw_x - self._raw_barline_x
                    displacement -= round(displacement / update.spacing_px) * update.spacing_px
                    if -update.spacing_px / 2 < displacement < -3:
                        self._last_raw_motion_ms = t_ms
                self._raw_barline_x = raw_x
            if update.state == "resetting":
                self._resetting_reads += 1
                if self._resetting_since_ms is None:
                    self._resetting_since_ms = t_ms
                # A rejected barline chain can look like a reset for several
                # decoded frames. Wait about half a measure's beat before
                # treating the discontinuity as a real screen reset.
                measure_ms = (
                    1000 * update.spacing_px / abs(update.fitted_speed_px_s)
                    if update.spacing_px and update.fitted_speed_px_s
                    else 2500.0
                )
                reset_grace_ms = max(200.0, min(500.0, measure_ms * 0.12))
                if (self._resetting_reads >= 2
                        and t_ms - self._resetting_since_ms >= reset_grace_ms
                        and not self._raw_motion_recent_unlocked(t_ms)
                        and self._fault_reason is None):
                    self._fault_reason = "score moved right or reset"
            elif update.state != "missing":
                self._resetting_reads = 0
                self._resetting_since_ms = None
            if self._origin_phase is None and update.phase_px is not None:
                self._origin_phase = update.phase_px
            self.samples.append(sample)
        return sample

    @property
    def fault_reason(self) -> str | None:
        with self._lock:
            return self._fault_reason

    def _raw_motion_recent_unlocked(self, t_ms: float) -> bool:
        return (self._last_raw_motion_ms is not None
                and t_ms - self._last_raw_motion_ms <= 600.0)

    def raw_motion_recent(self, t_ms: float) -> bool:
        with self._lock:
            return self._raw_motion_recent_unlocked(t_ms)

    def latest_frame(self) -> tuple[Image.Image | None, str]:
        with self._lock:
            return (self._latest_image.copy() if self._latest_image is not None else None,
                    self._latest_state)

    def latest_frame_with_phase(
        self,
    ) -> tuple[Image.Image | None, ScrollSample | None]:
        """Return the image and barline phase from the same decoded frame."""
        with self._lock:
            return (
                self._latest_image.copy() if self._latest_image is not None else None,
                self.samples[-1] if self.samples else None,
            )

    def reanchor(self, phase_px: float, spacing_px: float) -> None:
        with self._lock:
            self._tracker = MeasureLineTracker(
                spacing_px=spacing_px, initial_phase_px=phase_px,
            )
            self._fault_reason = None
            self._resetting_reads = 0
            self._resetting_since_ms = None
            self._raw_barline_x = None
            self._last_raw_motion_ms = None
            self.samples.clear()

    def stalled(self, *, window_ms: float = 500.0, still_px: float = 5.0) -> bool:
        """True once the score has scrolled and then stopped.

        The ultimate challenge never pauses mid-song: a still score after
        motion means the app reset to its "press X to start" prompt or reached
        the end, and any key sent from the old timeline lands on a stopped
        screen.
        """
        with self._lock:
            samples = [
                (s.t_ms, s.phase_px) for s in self.samples
                if s.phase_px is not None
                and s.state in {"steady", "accelerating", "waiting"}
            ]
        if len(samples) < 3:
            return False
        phases = [p for _, p in samples]
        if max(phases) - min(phases) < 50.0:
            return False          # never started moving: still on the start prompt
        latest = samples[-1][0]
        recent = [p for t, p in samples if t >= latest - window_ms]
        span = samples[-1][0] - min(t for t, _ in samples if t >= latest - window_ms)
        if len(recent) < 3 or span < window_ms * 0.6:
            return False
        return max(recent) - min(recent) < still_px

    @property
    def origin_phase(self) -> float | None:
        with self._lock:
            return self._origin_phase

    def refined_beat_ms(self, px_per_beat: float, *, skip_ms: float = 5000.0,
                        min_span_ms: float = 8000.0, min_samples: int = 60):
        """Fit the whole scroll at once instead of trusting a sliding window.

        The app scrolls uniformly, so one good constant lasts the whole song;
        what corrupts short windows is the capture pipeline, which delivers the
        first seconds of frames late and makes the score look slower than it is.
        Dropping that head and fitting a long span removes the bias, and a
        constant transport delay cannot tilt a slope.
        """
        with self._lock:
            samples = [(s.t_ms, s.phase_px) for s in self.samples if s.phase_px is not None]
        if len(samples) < min_samples:
            return None
        times = np.array([s[0] for s in samples])
        phases = np.array([s[1] for s in samples])
        moving = np.where(np.abs(np.diff(phases)) > 1.0)[0]
        if len(moving) < 2:
            return None
        first_motion = times[moving[0] + 1]
        keep = (times >= first_motion + skip_ms) & (times <= times[moving[-1] + 1])
        if keep.sum() < min_samples or times[keep][-1] - times[keep][0] < min_span_ms:
            return None
        tt, pp = times[keep], phases[keep]
        slope, intercept = np.polyfit(tt, pp, 1)
        residual = pp - (slope * tt + intercept)
        good = np.abs(residual) < max(3.0 * residual.std(), 3.0)
        slope, intercept = np.polyfit(tt[good], pp[good], 1)
        speed = abs(slope) * 1000.0
        if speed <= 1.0:
            return None
        return {
            "speed_px_s": speed,
            "beat_ms": px_per_beat / speed * 1000.0,
            "span_ms": float(tt[-1] - tt[0]),
            "samples": int(good.sum()),
            "residual_px": float(np.abs(pp[good] - (slope * tt[good] + intercept)).std()),
        }


class GridKeeper:
    """Hold the song-wide grid constants once they are known.

    Beats-per-measure, pixels-per-beat, and the engraving offset are properties
    of the piece. Later readings check that the grid still fits, but must not
    move the established beat timeline with a single noisy engraving offset.
    """

    def __init__(self) -> None:
        self._grid = None
        self.rejected_grids = 0

    def update(self, events, phase_px: float, spacing_px: float | None):
        if spacing_px is None:
            # The final viewport can contain only one barline. Its notes still
            # have a phase from the scroll tracker and the song grid is fixed.
            return self._grid
        try:
            grid = build_beat_grid(events, phase_px, spacing_px)
        except BeatGridError:
            return None
        previous = self._grid
        if previous is not None and (
            grid.beats_per_measure != previous.beats_per_measure
            or abs(grid.spacing_px - previous.spacing_px) > previous.px_per_beat / 8
            or abs(grid.delta - previous.delta) >= grid.quantum / 2
        ):
            # A single misread frame must not change the meaning of every
            # previously recorded beat in the song-wide ledger.
            self.rejected_grids += 1
            return None
        if previous is None:
            log("grid", "locked",
                beats_per_measure=grid.beats_per_measure,
                px_per_beat=round(grid.px_per_beat, 2),
                delta=round(grid.delta, 3))
            self._grid = grid
        return self._grid

    @property
    def beats_per_measure(self) -> int | None:
        return self._grid.beats_per_measure if self._grid is not None else None

    @property
    def px_per_beat(self) -> float | None:
        return self._grid.px_per_beat if self._grid is not None else None

    @property
    def delta(self) -> float | None:
        return self._grid.delta if self._grid is not None else None

    @property
    def spacing_px(self) -> float | None:
        return self._grid.spacing_px if self._grid is not None else None

    @property
    def ready(self) -> bool:
        return self._grid is not None

    def beat_of(self, x: float, phase_px: float) -> float:
        grid = self._grid
        if grid is None:
            raise BeatGridError("beat grid is not locked")
        return grid.snapped_beat_of(x, phase_px)


def infer_opening_measure_spacing(events, barlines, judgment_line_x: float) -> float | None:
    """Use a complete opening measure if the viewport contains one barline.

    The pre-scroll prompt puts its first event at the judgment line.  This is
    the only point where a single barline can safely delimit a full measure;
    later scrolling frames must use repeated barlines instead.
    """
    spacing = infer_measure_spacing(barlines)
    if spacing is not None or len(barlines) != 1:
        return spacing
    phase = barlines[0].x
    before = [e for e in events if e["x"] < phase]
    if len(before) < 3 or any(e.get("edge_clipped") or not e.get("delta_beats") for e in before):
        return None
    before.sort(key=lambda e: e["x"])
    px_per_beat = estimate_px_per_beat(events)
    if px_per_beat is None or px_per_beat <= 0:
        return None
    beats = sum(float(e["delta_beats"]) for e in before)
    if not (2 <= beats <= 12 and beats.is_integer()):
        return None
    if abs(before[0]["x"] - judgment_line_x) > px_per_beat / 2:
        return None
    if any(
        abs((right["x"] - left["x"]) - left["delta_beats"] * px_per_beat)
        > px_per_beat * .18
        for left, right in zip(before, before[1:])
    ):
        return None
    if abs(phase - (before[-1]["x"] + before[-1]["delta_beats"] * px_per_beat)) > px_per_beat / 2:
        return None
    spacing = beats * px_per_beat
    if abs(before[0]["x"] - (phase - spacing)) > px_per_beat / 2:
        return None
    return spacing


def capture_and_track(pump, tracker, latency, recog_q, phase_q, stop, start_ns,
                      interval_s, save_q, save_stats, scan_stats, save_every=1):
    last_sequence = -1
    last_push = -1e9
    frame_index = 0
    while not stop.is_set():
        try:
            image, last_sequence, received_ns = pump.wait_for_timed_frame(
                after_sequence=last_sequence, timeout=1.0,
            )
        except Exception:
            continue
        t_ms = (received_ns - start_ns) / 1e6
        latency.observe(image, received_ns)
        sample = tracker.observe(image, t_ms)
        if not phase_q.full():
            phase_q.put_nowait(sample)
        if (recog_q is not None
                and t_ms - last_push >= interval_s * 1000.0
                and sample.phase_px is not None
                and sample.state not in {"missing", "resetting"}):
            last_push = t_ms
            # The phase must come from this exact frame. If the recognizer is
            # busy, replace the waiting image with the newest one rather than
            # let several seconds of obsolete score accumulate.
            try:
                recog_q.put_nowait((image.copy(), t_ms, sample.phase_px))
            except queue.Full:
                try:
                    recog_q.get_nowait()
                except queue.Empty:
                    pass
                scan_stats["replaced_pending"] += 1
                recog_q.put_nowait((image.copy(), t_ms, sample.phase_px))
        if save_q is not None and frame_index % save_every == 0:
            try:
                save_q.put_nowait((image, t_ms))
            except queue.Full:
                save_stats["dropped"] += 1
        frame_index += 1


def frame_writer(stop, frames_dir, save_q, records):
    """Keep PNG encoding off the timing-critical capture loop."""
    while not stop.is_set() or not save_q.empty():
        try:
            image, t_ms = save_q.get(timeout=0.1)
        except queue.Empty:
            continue
        name = f"frame-{len(records):04d}.png"
        image.save(frames_dir / name, format="PNG")
        records.append({"index": len(records), "image": f"frames/{name}", "t_ms": t_ms})


_process_reader = None


def recognize_frame_in_process(image, key_signature=None):
    """Keep expensive staff analysis off the capture and key-scheduling GIL."""
    global _process_reader
    if _process_reader is None:
        _process_reader = load_script("dl_reader_live_process", "duolingo-read-screen-notes.py")
    if image is None:
        return None  # prewarm imports before the first key starts the clock
    ctx = _process_reader.build_analysis_context(image)
    if ctx.staff_lines is None:
        return None
    notes = _process_reader.analyze_screen_notes(
        ctx, key_signature=key_signature,
    )
    rests = _process_reader.analyze_screen_rests(ctx)
    events = sorted([*notes, *rests], key=lambda e: e["x"])
    spacing = infer_measure_spacing(
        detect_measure_barline_candidates(
            image, list(ctx.staff_lines), ctx.judgment_line_x,
        ),
    )
    return events, spacing


def recognition_worker(
    executor, keeper, recog_q, ledger, stop, stats, start_ns, key_signature,
):
    in_flight = {}
    while not stop.is_set():
        # Do not make the next independent sighting wait for the preceding
        # full-frame analysis. A late-song note may only be visible for a few
        # beats while the recognizer is under load.
        while len(in_flight) < 2 and not stop.is_set():
            try:
                image, t_ms, phase_px = recog_q.get(
                    timeout=0.02 if not in_flight else 0,
                )
            except queue.Empty:
                break
            try:
                future = executor.submit(
                    recognize_frame_in_process, image, key_signature,
                )
            except Exception as exc:
                log("scan", "recognition process failed", error=repr(exc))
                continue
            in_flight[future] = (t_ms, phase_px)
        if not in_flight:
            continue
        done, _ = wait(tuple(in_flight), timeout=0.02,
                       return_when=FIRST_COMPLETED)
        for future in sorted(done, key=lambda item: in_flight[item][0]):
            t_ms, phase_px = in_flight.pop(future)
            try:
                recognized = future.result()
            except Exception as exc:
                log("scan", "recognition process failed", error=repr(exc))
                continue
            if recognized is None:
                continue
            events, spacing = recognized
            grid = keeper.update(events, phase_px, spacing)
            stats["reads"] += 1
            finished_ms = (time.monotonic_ns() - start_ns) / 1e6
            stats["reader_lag_ms"].append(round(finished_ms - t_ms, 1))
            if grid is None or not keeper.ready:
                continue
            added = 0
            for event in events:
                if event["event_type"] != "note" or event.get("edge_clipped"):
                    continue
                beat = keeper.beat_of(event["x"], phase_px)
                if ledger.add(
                    beat, event["pitch"], event.get("duration_beats"),
                    event.get("hold_beats"),
                    relative_x_px=event["x"] - phase_px,
                ):
                    added += 1
            stats["added"] += added
            if added:
                log("scan", "new notes", at_ms=round(t_ms),
                    finished_ms=round(finished_ms),
                    added=added, total=len(ledger.notes))


def stop_beat_for(ledger, start_beat: float, beats_per_measure: int) -> float | None:
    """Where to stop: the end of the first measure after the start that has notes.

    A rest-heavy opening can push the first playable measure arbitrarily far
    out, so the limit is read from the score instead of being fixed in advance;
    until such a measure is seen the answer is simply "not yet known".
    """
    start_measure = int(np.floor(start_beat / beats_per_measure))
    later = {
        int(np.floor(note.beat / beats_per_measure))
        for note in ledger.ordered()
        if note.beat > start_beat
    }
    later = {m for m in later if m > start_measure}
    if not later:
        return None
    return (min(later) + 1) * float(beats_per_measure)


def rehearse(args) -> dict:
    reader = load_script("dl_reader_reh", "duolingo-read-screen-notes.py")
    timed = load_script("dl_timed_reh", "duolingo-timed-player.py")
    explicit_note_pitch_beats = set(args.note_pitch)

    frame = kbdetect.capture_device_frame(args.serial, args.adb)
    keyboard_frame = frame
    if args.keyboard_image is not None:
        keyboard_frame = np.asarray(Image.open(args.keyboard_image).convert("RGB"))
        if keyboard_frame.shape != frame.shape:
            raise SystemExit("--keyboard-image dimensions differ from the live screen")
    layout = kbdetect.detect_keyboard(keyboard_frame)
    image0 = Image.fromarray(frame)
    ctx = reader.build_analysis_context(image0)
    if ctx.staff_lines is None:
        raise SystemExit("no staff on screen")
    result = reader.analyze_image(image0)
    key_signature = (
        result["key_signature"]["flats"],
        result["key_signature"]["sharps"],
    )
    seed = [e for e in result["events"] if e["event_type"] == "note" and not e.get("edge_clipped")]
    if not seed:
        raise SystemExit("no playable notes on screen")
    start_note = min(seed, key=lambda e: e["x"])
    if args.opening_note_beats is not None:
        start_note["duration_beats"] = args.opening_note_beats
        start_note["hold_beats"] = max(args.opening_note_beats - 0.2, 0.4)
        start_note["delta_beats"] = args.opening_note_beats
    if start_note.get("duration_beats") is None:
        raise SystemExit("start note has no measurable duration")
    start_play_pitch = args.note_pitch.get(
        -4.0, key_signature_pitch(start_note["pitch"], args.key_sharps),
    )
    start_point = layout.target(start_play_pitch)
    if start_point is None:
        raise SystemExit(
            f"start note {start_play_pitch} has no key on this keyboard; "
            f"available: {', '.join(sorted(layout.keys))}"
        )
    for event in seed:
        pitch = key_signature_pitch(event["pitch"], args.key_sharps)
        if layout.target(pitch) is None:
            raise SystemExit(
                f"opening score note {pitch} has no key on this keyboard; "
                "verify the key signature and score before playing"
            )
    # Pair the note with the phase of this same frame: reading x here and the
    # phase from a later frame would silently fold the capture start-up delay
    # into the anchor.
    from duolingo_measure_tracker import detect_measure_barline_candidates as _barlines
    seed_candidates = _barlines(image0, list(ctx.staff_lines), ctx.judgment_line_x)
    seed_phase = min((c.x for c in seed_candidates), default=None)
    if seed_phase is None:
        raise SystemExit("no barline on the opening frame to anchor the grid")

    out_dir: Path = args.output
    out_dir.mkdir(parents=True, exist_ok=False)
    frames_dir = None
    records: list[dict] = []
    if args.save_frames:
        frames_dir = out_dir / "frames"
        frames_dir.mkdir()

    seed_spacing = infer_opening_measure_spacing(
        result["events"], seed_candidates, ctx.judgment_line_x,
    )
    tracker = ScrollTracker(
        ctx.staff_lines, ctx.judgment_line_x,
        initial_phase_px=seed_phase, spacing_px=seed_spacing,
    )
    latency = KeyHighlightLatency(image0, layout.keys)
    keeper = GridKeeper()
    ledger = Ledger()
    screen_last_beat: float | None = None
    # Build the grid before the first key goes out.  Waiting for the first live
    # reading leaves the note half a beat after the start trigger due before
    # anything can be scheduled, which is only ~400ms away.
    opening_grid_primed = keeper.update(
        result["events"], seed_phase, seed_spacing,
    ) is not None
    if opening_grid_primed:
        if args.stop_at_initial_screen_end:
            last_visible = max(seed, key=lambda event: event["x"])
            screen_last_beat = keeper.beat_of(last_visible["x"], seed_phase)
        for event in result["events"]:
            if event["event_type"] != "note" or event.get("edge_clipped"):
                continue
            beat = keeper.beat_of(event["x"], seed_phase)
            ledger.add(
                beat, event["pitch"], event.get("duration_beats"),
                event.get("hold_beats"),
                relative_x_px=event["x"] - seed_phase,
            )
        log("grid", "primed from the opening frame", seeded=len(ledger.notes))
    else:
        log("grid", "opening frame has no reliable grid; waiting for a live reading")
    if args.stop_at_initial_screen_end and screen_last_beat is None:
        raise SystemExit("initial screen has no reliable beat grid")
    # Full-size RGB delivery can backlog the decoder under concurrent score
    # recognition. The capture cadence is a transport setting, not a musical
    # timing assumption, and can be tuned for the current device's throughput.
    pump = reader.H264FramePump(
        args.adb, args.serial, encoder_fps=args.capture_fps,
        output_fps=args.capture_fps, warmup_frames=20,
        archive_path=out_dir / "recording.h264" if args.record_h264 else None,
    )
    shell = timed.PersistentInputShell(args.adb, args.serial, key_points=layout.keys)
    def record_key_edge(kind: str, pitch: str, sent_ns: int) -> None:
        if kind == "DOWN":
            latency.mark_press(pitch, sent_ns)
        else:
            latency.mark_release(pitch, sent_ns)

    keys = LiveKeys(shell, on_edge=record_key_edge)
    recog_q: queue.Queue | None = None if args.seed_only else queue.Queue(maxsize=1)
    phase_q: queue.Queue = queue.Queue(maxsize=512)
    save_q: queue.Queue | None = queue.Queue(maxsize=16) if frames_dir else None
    save_stats = {"dropped": 0}
    stop = threading.Event()
    stats = {"reads": 0, "added": 0, "replaced_pending": 0,
             "reader_lag_ms": []}
    played: list[dict] = []
    beat_ms = args.beat_ms
    tempo_updates: list[dict] = []
    continuous = args.mode == "continuous"
    threads: list[threading.Thread] = []
    recognizer = None if args.seed_only else ProcessPoolExecutor(max_workers=2)

    try:
        if recognizer is not None:
            warmups = [
                recognizer.submit(recognize_frame_in_process, None)
                for _ in range(2)
            ]
            for warmup in warmups:
                warmup.result(timeout=30)
        pump.start(timeout=10.0)
        warmup_ms = shell.warmup()
        # Re-read the still opening screen from an independent H.264 frame
        # before touching a key. Nearby notes may be due sooner than one live
        # recognition pass can complete after the scroll starts.
        preflight_image, _, _ = pump.wait_for_timed_frame(
            after_sequence=-1, timeout=1.0,
        )
        preflight_ctx = reader.build_analysis_context(preflight_image)
        if preflight_ctx.staff_lines is None:
            raise RuntimeError("staff disappeared during the opening preflight")
        preflight_result = reader.analyze_image(preflight_image)
        preflight_signature = (
            preflight_result["key_signature"]["flats"],
            preflight_result["key_signature"]["sharps"],
        )
        if preflight_signature != key_signature:
            raise RuntimeError(
                "opening key signature changed between independent frames: "
                f"{key_signature} then {preflight_signature}"
            )
        preflight_events = preflight_result["events"]
        preflight_barlines = _barlines(
            preflight_image, list(preflight_ctx.staff_lines),
            preflight_ctx.judgment_line_x,
        )
        preflight_phase = min((c.x for c in preflight_barlines), default=None)
        if preflight_phase is None:
            raise RuntimeError("opening preflight has no measure line")
        preflight_notes = [
            event for event in preflight_events
            if event["event_type"] == "note" and not event.get("edge_clipped")
        ]
        for event in seed:
            if not any(
                abs((other["x"] - preflight_phase)
                    - (event["x"] - seed_phase)) <= 18
                and other["pitch"] == event["pitch"]
                for other in preflight_notes
            ):
                raise RuntimeError(
                    "opening note pitch disagrees between independent frames: "
                    f"x={event['x']} pitch={event['pitch']}"
                )
        for event in preflight_events:
            if event["event_type"] != "note" or event.get("edge_clipped"):
                continue
            pitch = key_signature_pitch(event["pitch"], args.key_sharps)
            if layout.target(pitch) is None:
                raise RuntimeError(
                    f"preflight score note {pitch} has no keyboard key"
                )
        if args.opening_note_beats is not None:
            first_note = min(
                (event for event in preflight_events
                 if event["event_type"] == "note" and not event.get("edge_clipped")),
                key=lambda event: event["x"],
            )
            first_note["duration_beats"] = args.opening_note_beats
            first_note["hold_beats"] = max(args.opening_note_beats - 0.2, 0.4)
            first_note["delta_beats"] = args.opening_note_beats
        preflight_grid = (
            keeper.update(
                preflight_events, preflight_phase,
                infer_opening_measure_spacing(
                    preflight_events, preflight_barlines,
                    preflight_ctx.judgment_line_x,
                ),
            ) if preflight_phase is not None else None
        )
        if preflight_grid is None:
            raise RuntimeError("opening score did not pass a second grid reading")
        tracker.lock_spacing(keeper.spacing_px)
        if not opening_grid_primed:
            # The first still frame can lack enough visible barlines to build
            # a grid. Once the independent preflight locks it, map that first
            # frame through its own barline phase so its notes still count as
            # the first reading of the stationary opening score.
            if abs(seed_phase - preflight_phase) > keeper.px_per_beat / 8:
                raise RuntimeError("opening score moved during the preflight")
            for event in result["events"]:
                if event["event_type"] != "note" or event.get("edge_clipped"):
                    continue
                ledger.add(
                    keeper.beat_of(event["x"], seed_phase),
                    event["pitch"], event.get("duration_beats"),
                    event.get("hold_beats"),
                    relative_x_px=event["x"] - seed_phase,
                )
        for event in preflight_events:
            if event["event_type"] != "note" or event.get("edge_clipped"):
                continue
            ledger.add(
                keeper.beat_of(event["x"], preflight_phase),
                event["pitch"], event.get("duration_beats"),
                event.get("hold_beats"),
                relative_x_px=event["x"] - preflight_phase,
            )
        if not opening_start_confirmed(ledger, start_note["pitch"]):
            raise RuntimeError("start note was not confirmed by the preflight")
        log("scan", "opening frame independently confirmed",
            confirmed=len(ledger.confirmed(2)))
        seed_beats: set[float] | None = None
        if args.seed_from_run is not None:
            source = args.seed_from_run
            source_notes = json.loads((source / "ledger.json").read_text(encoding="utf-8"))["notes"]
            source_played = json.loads((source / "played.json").read_text(encoding="utf-8"))
            seed_beats = {note["beat"] for note in source_played}
            if not source_played or source_played[0]["beat"] <= -4:
                raise ValueError("seed run has no usable played notes")
            for played_note in source_played:
                matches = [note for note in source_notes
                           if abs(note["beat"] - played_note["beat"]) <= 0.1
                           and note["pitch"] == played_note.get(
                               "read_pitch", played_note["pitch"])]
                if not matches:
                    raise ValueError(f"seed run lacks score note {played_note!r}")
                source_note = max(matches, key=lambda note: note["sightings"])
                # A seed must replay the key that was actually sent, even when
                # a previous run overrode the score reader's pitch.  A new
                # explicit --note-pitch remains the caller's correction.
                args.note_pitch.setdefault(source_note["beat"], played_note["pitch"])
                ledger.notes.append(LedgerNote(
                    beat=source_note["beat"], pitch=source_note["pitch"],
                    duration_beats=source_note["duration_beats"],
                    hold_beats=source_note["hold_beats"], sightings=100,
                    articulation_votes={(
                        source_note["duration_beats"],
                        source_note["hold_beats"],
                    ): 100},
                    relative_x_samples=[source_note["relative_x_px"]],
                ))
            log("scan", "preloaded confirmed played notes",
                source=str(source), count=len(source_played))
        for beat, pitch, duration, relative_x in args.seed_note:
            ledger.notes.append(LedgerNote(
                beat=beat, pitch=pitch, duration_beats=duration,
                hold_beats=max(duration - 0.2, 0.4), sightings=100,
                articulation_votes={(duration, max(duration - 0.2, 0.4)): 100},
                relative_x_samples=[relative_x],
            ))
            if seed_beats is not None:
                seed_beats.add(beat)
        if args.seed_note:
            log("scan", "preloaded visually verified score notes",
                count=len(args.seed_note))
        start_ns = time.monotonic_ns()
        threads = [threading.Thread(target=capture_and_track, daemon=True, args=(
            pump, tracker, latency, recog_q, phase_q, stop, start_ns,
            args.scan_interval, save_q, save_stats, stats,
            args.save_every))]
        if recognizer is not None:
            threads.append(threading.Thread(target=recognition_worker, daemon=True,
                args=(recognizer, keeper, recog_q, ledger, stop, stats,
                      start_ns, key_signature)))
        if save_q is not None:
            threads.append(threading.Thread(
                target=frame_writer, daemon=True, name="frame-writer",
                args=(stop, frames_dir, save_q, records),
            ))
        for thread in threads:
            thread.start()

        # The first note doubles as the start trigger, so it is played on sight;
        # everything after it is timed against this one press.
        press_ns = start_ns + int(args.startup_ms * 1e6)
        while (remaining := press_ns - time.monotonic_ns()) > 0:
            time.sleep(min(remaining / 1e9, 0.004))
        start_hold = hold_ms_for(
            start_note.get("duration_beats"), start_note.get("hold_beats"),
            beat_ms, args.release_ms, args.long_release_ms,
        )
        sent_ns = keys.press(
            pitch=start_play_pitch, beat=0.0,
            deadline_ns=press_ns, hold_ms=start_hold,
        )
        log("play", "start note sent", pitch=start_play_pitch,
            read_pitch=start_note["pitch"], x=start_note["x"])

        start_beat = None
        beat_limit = None
        anchor_ns = sent_ns
        anchor_beat = None
        clock = None
        last_refined_ns = None
        last_good_phase_ns = None
        saw_motion = False
        stop_reason = "duration elapsed"
        tempo_locked = False
        visual_ready = False
        played_beats: set[float] = set()
        sent_ns_by_beat: dict[float, int] = {}
        committed_due: dict[float, tuple[int, float | None]] = {}
        late_pitch_seen_ms: dict[float, float] = {}
        late_pitch_cache: dict[float, tuple[float, str, float]] = {}
        prompt_wait_started_ns: int | None = None
        last_prompt_probe_ns = 0
        last_prompt_press_ns = 0
        prompt_attempts: dict[float, int] = {}
        prompt_candidate: tuple[float, float, int] | None = None

        def restart_from_visible_prompt(now_ns: int) -> bool:
            nonlocal visual_ready, last_good_phase_ns, last_refined_ns
            nonlocal last_prompt_press_ns, prompt_candidate
            if clock is None or not played_beats:
                return False
            if now_ns - last_prompt_press_ns < max(750_000_000, round(beat_ms * 800_000)):
                return False
            prompt_image, _ = tracker.latest_frame()
            if (prompt_image is None
                    or not has_start_prompt_icon(prompt_image, image0)):
                return False
            remaining = [n for n in ledger.confirmed(
                args.min_sightings, keeper.px_per_beat,
            ) if n.beat not in played_beats
                and (seed_beats is None or n.beat in seed_beats)]
            if not remaining:
                return False
            prompt_ctx = reader.build_analysis_context(prompt_image)
            if prompt_ctx.staff_lines is None:
                return False
            visible_notes = reader.analyze_screen_notes(
                prompt_ctx, key_signature=key_signature,
            )
            matched = match_visible_prompt(
                visible_notes, ledger.confirmed(
                    args.min_sightings, keeper.px_per_beat,
                ), judgment_x=prompt_ctx.judgment_line_x,
                screen_width=prompt_image.width, sharps=args.key_sharps,
                min_beat=prompt_search_floor(
                    max(played_beats), keeper.beats_per_measure,
                ),
                max_beat=prompt_search_ceiling(
                    max(played_beats), remaining[0].beat,
                    keeper.beats_per_measure,
                ),
            )
            if matched is None:
                prompt_candidate = None
                return False
            note, visible = matched
            # The prompt banner can precede the end of the old scroll.  A
            # passing note is not a restart cue even if tracking says stalled.
            stable, prompt_candidate = stable_prompt_candidate(
                prompt_candidate, note.beat, visible["x"], now_ns,
            )
            if not stable:
                return False
            if prompt_attempts.get(note.beat, 0) >= 2:
                return False
            pitch = args.note_pitch.get(
                note.beat, key_signature_pitch(note.pitch, args.key_sharps),
            )
            hold_ms = args.note_hold_ms.get(note.beat, hold_ms_for(
                note.duration_beats, note.hold_beats, clock.beat_ms,
                args.release_ms, args.long_release_ms,
            ))
            sent = keys.press(pitch=pitch, beat=note.beat,
                              deadline_ns=now_ns, hold_ms=hold_ms)
            tracker.reanchor(visible["x"] - note.relative_x_px, keeper.spacing_px)
            # A prompt press starts a new scroll animation.  Until measure-line
            # motion is calibrated again, the next beat uses this fallback
            # anchor; account for the observed delay before scrolling starts.
            prompt_anchor_ns = sent + round(args.prompt_start_delay_ms * 1_000_000)
            clock.restart_at(note.beat, prompt_anchor_ns)
            rewind_played_beats(played_beats, sent_ns_by_beat, note.beat)
            played_beats.add(note.beat)
            sent_ns_by_beat[note.beat] = sent
            prompt_attempts[note.beat] = prompt_attempts.get(note.beat, 0) + 1
            last_prompt_press_ns = sent
            prompt_candidate = None
            committed_due.clear()
            while not phase_q.empty():
                phase_q.get_nowait()
            visual_ready = False
            last_good_phase_ns = sent
            last_refined_ns = None
            played.append({
                "pitch": pitch, "read_pitch": note.pitch, "beat": note.beat,
                "sent_ms": round((sent - start_ns) / 1e6, 2),
                "hold_ms": round(hold_ms, 1), "prompt_restart": True,
            })
            log("play", "restarted from a visible prompt",
                beat=note.beat, pitch=pitch,
                scroll_start_delay_ms=args.prompt_start_delay_ms)
            return True
        deadline_ns = (
            start_ns + int(args.duration * 1e9)
            if args.duration is not None else None
        )

        while (deadline_ns is None or time.monotonic_ns() < deadline_ns) and not stop.is_set():
            now_ns = time.monotonic_ns()
            keys.release_due(now_ns)
            fault = tracker.fault_reason
            stalled = tracker.stalled()
            if fault is not None or stalled:
                if now_ns - last_prompt_probe_ns >= 250_000_000:
                    last_prompt_probe_ns = now_ns
                    if restart_from_visible_prompt(now_ns):
                        prompt_wait_started_ns = None
                        continue
                if prompt_wait_started_ns is None:
                    prompt_wait_started_ns = now_ns
                if now_ns - prompt_wait_started_ns < prompt_transition_grace_ns(
                    beat_ms, keeper.beats_per_measure,
                ):
                    time.sleep(0.02)
                    continue
                stop_reason = fault or "score stopped scrolling (reset or end of song)"
                log("gate", stop_reason, played=len(played))
                break
            prompt_wait_started_ns = None
            if start_beat is None:
                if not keeper.ready:
                    time.sleep(0.02)
                    continue
                start_beat = keeper.beat_of(start_note["x"], seed_phase)
                anchor_beat = start_beat
                played_beats.add(start_beat)
                if continuous:
                    clock = VisualBeatClock(
                        anchor_ns=sent_ns, anchor_beat=start_beat,
                        beat_ms=beat_ms, px_per_beat=keeper.px_per_beat,
                        beats_per_measure=keeper.beats_per_measure,
                    )
                log("grid", "anchored on the start note",
                    start_beat=start_beat, beats_per_measure=keeper.beats_per_measure)
            while not phase_q.empty():
                sample = phase_q.get_nowait()
                sample_ns = start_ns + round(sample.t_ms * 1_000_000)
                if sample_ns <= sent_ns or not continuous:
                    continue
                if sample.state == "resetting":
                    if tracker.fault_reason is not None and not args.seed_only:
                        stop_reason = tracker.fault_reason
                        break
                    continue
                if sample.state in {"steady", "accelerating"} and sample.phase_px is not None:
                    saw_motion = True
                    last_good_phase_ns = sample_ns
                    try:
                        reading = clock.observe(sample_ns, sample.phase_px)
                    except VisualClockLost as exc:
                        stop_reason = str(exc)
                        break
                    if (reading is not None
                            and reading.residual_px <= keeper.px_per_beat / 8):
                        visual_ready = True
                    if (reading is not None
                            and tempo_refinement_ready(
                                measured_beat_ms=reading.beat_ms,
                                current_beat_ms=clock.beat_ms,
                                span_beats=reading.span_beats,
                                residual_px=reading.residual_px,
                                px_per_beat=keeper.px_per_beat,
                                beats_per_measure=keeper.beats_per_measure,
                                first_update=last_refined_ns is None,
                                steady_speed_px_s=(
                                    sample.speed_px_s if sample.state == "steady"
                                    else None
                                ),
                                fit_r_squared=sample.r_squared,
                            )
                            and (last_refined_ns is None or sample_ns - last_refined_ns
                                 >= clock.beat_ms * keeper.beats_per_measure * 1_000_000)):
                        large_first_correction = (
                            last_refined_ns is None
                            and not 0.75 * clock.beat_ms <= reading.beat_ms
                            <= 1.25 * clock.beat_ms
                        )
                        if (not large_first_correction
                                and not 0.75 * clock.beat_ms <= reading.beat_ms
                                <= 1.25 * clock.beat_ms):
                            stop_reason = "visual tempo disagrees with the playback clock"
                            break
                        if large_first_correction:
                            # The long-window fit still includes launch
                            # acceleration.  Its agreement with the tracker's
                            # recent steady speed lets us use that fresher
                            # speed for the first playable measure.
                            reading = replace(
                                reading,
                                beat_ms=keeper.px_per_beat * 1000
                                / -sample.speed_px_s,
                            )
                        previous_ms = clock.beat_ms
                        clock.adopt(reading, now_ns=sample_ns)
                        beat_ms = clock.beat_ms
                        last_refined_ns = sample_ns
                        tempo_updates.append({
                            "at_ms": round(sample.t_ms, 1),
                            "previous_beat_ms": round(previous_ms, 3),
                            "measured_beat_ms": round(beat_ms, 3),
                            "span_beats": round(reading.span_beats, 2),
                            "residual_px": round(reading.residual_px, 2),
                        })
                        log("tempo", "updated from live barlines", **tempo_updates[-1])
            if stop_reason != "duration elapsed":
                break
            if (continuous and saw_motion and last_good_phase_ns is not None
                    and now_ns - last_good_phase_ns > clock.beat_ms * 2_000_000):
                prompt_image, _ = tracker.latest_frame()
                if (now_ns - last_good_phase_ns < prompt_transition_grace_ns(
                        clock.beat_ms, keeper.beats_per_measure)):
                    if (prompt_image is not None
                            and has_start_prompt_icon(prompt_image, image0)
                            and now_ns - last_prompt_probe_ns >= 250_000_000):
                        last_prompt_probe_ns = now_ns
                        if restart_from_visible_prompt(now_ns):
                            continue
                    time.sleep(0.02)
                    continue
                stop_reason = "score disappeared or frame tracking stalled"
                log("gate", stop_reason)
                break
            if (continuous and not saw_motion and now_ns - sent_ns
                    > clock.beat_ms * keeper.beats_per_measure * 1_000_000):
                stop_reason = "score did not begin scrolling"
                log("gate", stop_reason)
                break
            pending = [
                n for n in ledger.confirmed(
                    args.min_sightings, keeper.px_per_beat,
                )
                if n.beat not in played_beats
                and (not args.seed_only or seed_beats is None or n.beat in seed_beats)
            ]
            if not pending:
                time.sleep(0.01)
                continue
            note = pending[0]
            if continuous and last_good_phase_ns is not None:
                _, frame_state = tracker.latest_frame()
                phase_age_ns = time.monotonic_ns() - last_good_phase_ns
                if (frame_state in {"missing", "resetting"}
                        and phase_age_ns > 250_000_000):
                    # During a score transition the old barline phase can
                    # predict an onset hundreds of milliseconds too early.
                    # Wait for fresh motion before committing a new key.
                    if (time.monotonic_ns() - last_prompt_probe_ns
                            >= 250_000_000):
                        last_prompt_probe_ns = time.monotonic_ns()
                        if restart_from_visible_prompt(last_prompt_probe_ns):
                            continue
                    time.sleep(0.01)
                    continue
            if (args.seed_only and played_beats
                    and note.beat - max(played_beats) >= 1.5):
                _, state = tracker.latest_frame()
                if state in {"missing", "resetting"}:
                    time.sleep(0.01)
                    continue
            if note.beat <= start_beat:
                played_beats.add(note.beat)
                continue
            if not continuous and not tempo_locked and args.refine_tempo:
                fit = tracker.refined_beat_ms(keeper.px_per_beat)
                if fit is not None:
                    now_ns = time.monotonic_ns()
                    # Re-anchor on the current position so the correction never
                    # makes the schedule jump backwards or forwards.
                    anchor_beat = anchor_beat + (now_ns - anchor_ns) / 1e6 / beat_ms
                    anchor_ns = now_ns
                    log("tempo", "refined from the full scroll fit",
                        was=round(beat_ms, 2), now=round(fit["beat_ms"], 2),
                        speed=round(fit["speed_px_s"], 2),
                        span_s=round(fit["span_ms"] / 1000, 1),
                        resid_px=round(fit["residual_px"], 2))
                    beat_ms = fit["beat_ms"]
                    tempo_locked = True
            if args.play_to_end or continuous or args.stop_at_initial_screen_end:
                limit = None
            else:
                limit = stop_beat_for(ledger, start_beat, keeper.beats_per_measure)
            if limit is not None and limit != beat_limit:
                beat_limit = limit
                log("gate", "stop point resolved from the score",
                    first_played_measure_ends_at=beat_limit)
            safety = start_beat + args.max_measures * keeper.beats_per_measure
            if not (args.play_to_end or continuous) and beat_limit is not None and note.beat >= beat_limit:
                stop_reason = "end of the first playable measure"
                log("gate", "reached the end of the first playable measure",
                    next_beat=note.beat, limit=beat_limit)
                break
            if not (args.play_to_end or continuous) and note.beat >= safety:
                stop_reason = "safety cap"
                log("gate", "safety cap reached before any playable measure appeared",
                    cap_measures=args.max_measures, next_beat=note.beat)
                break
            lag_ms_used: float | None = None
            fixed_lead_ms = args.note_visual_lead_ms.get(note.beat)
            if fixed_lead_ms is None:
                for first_beat, lead in args.visual_lead_from_beat:
                    if note.beat >= first_beat:
                        fixed_lead_ms = lead
            if (continuous and visual_ready and (
                    latency.scheduling_latency_ms is not None
                    or fixed_lead_ms is not None)):
                lag_ms_used = (
                    0.0 if fixed_lead_ms is not None
                    else latency.scheduling_latency_ms
                )
                due_ns = clock.visual_due_ns(
                    note.beat, judgment_x=ctx.judgment_line_x,
                    engraving_delta=keeper.delta,
                    relative_x_px=note.relative_x_px,
                    input_to_visual_ms=lag_ms_used,
                    lead_ms=(
                        fixed_lead_ms if fixed_lead_ms is not None
                        else args.visual_lead_ms
                    ),
                )
            elif continuous and args.timing_offset_ms is None:
                # An early note cannot be guessed from an uncalibrated visual
                # clock. A caller may supply a measured fallback for such a
                # song; otherwise stop before sending a likely wrong key.
                provisional_ns = clock.due_ns(note.beat)
                if provisional_ns - time.monotonic_ns() < beat_ms * 500_000:
                    stop_reason = "visual timing was not calibrated before the next note"
                    log("gate", stop_reason, beat=note.beat)
                    break
                time.sleep(0.01)
                continue
            elif continuous:
                due_ns = clock.due_ns(
                    note.beat, offset_ms=args.timing_offset_ms,
                )
            else:
                due_ns = anchor_ns + int(
                    ((note.beat - anchor_beat) * beat_ms + args.timing_offset_ms) * 1e6
                )
            phrase_due_ns = fixed_phrase_due_ns(
                note.beat, args.fixed_phrases, sent_ns_by_beat,
            ) if continuous else None
            if phrase_due_ns is not None:
                due_ns = phrase_due_ns
                lag_ms_used = None
            due_ns += int(args.note_delay_ms.get(note.beat, 0.0) * 1e6)
            if continuous and played:
                previous_played = played[-1]
                previous_sent_ns = sent_ns_by_beat.get(previous_played["beat"])
                due_ns = bounded_retrigger_due_ns(
                    due_ns, pitch=args.note_pitch.get(
                        note.beat, key_signature_pitch(note.pitch, args.key_sharps),
                    ), beat=note.beat, previous=previous_played,
                    previous_sent_ns=previous_sent_ns, beat_ms=beat_ms,
                )
            if continuous:
                if note.beat in committed_due:
                    due_ns, lag_ms_used = committed_due[note.beat]
                elif should_commit_due(
                    due_ns=due_ns, now_ns=time.monotonic_ns(), beat_ms=beat_ms,
                    lead_beats=args.commit_lead_beats,
                ):
                    # Freeze only near onset. A decoder gap can temporarily
                    # skew phase by ~100 ms, then correct within half a beat.
                    committed_due[note.beat] = (due_ns, lag_ms_used)
            if due_ns < time.monotonic_ns() - int(args.skip_late_ms * 1e6):
                if (played_beats and time.monotonic_ns() - due_ns
                        < beat_ms * keeper.beats_per_measure * 2_000_000):
                    probe_ns = time.monotonic_ns()
                    if probe_ns - last_prompt_probe_ns >= 250_000_000:
                        last_prompt_probe_ns = probe_ns
                        if restart_from_visible_prompt(probe_ns):
                            continue
                    time.sleep(0.02)
                    continue
                if continuous:
                    stop_reason = f"confirmed {note.pitch} at beat {note.beat:g} too late"
                    log("gate", stop_reason)
                    break
                played_beats.add(note.beat)
                log("skip", "discovered too late", beat=note.beat, pitch=note.pitch)
                continue
            remaining = due_ns - time.monotonic_ns()
            if (args.late_pitch_check and continuous
                    and note.beat not in explicit_note_pitch_beats
                    and note.relative_x_px is not None
                    and -40_000_000 <= remaining <= 150_000_000):
                recent_image, recent_sample = tracker.latest_frame_with_phase()
                if (recent_image is not None and recent_sample is not None
                        and recent_sample.phase_px is not None
                        and recent_sample.state in {"steady", "accelerating"}
                        and recent_sample.t_ms > late_pitch_seen_ms.get(note.beat, -1)
                        and (time.monotonic_ns() - start_ns) / 1e6
                        - recent_sample.t_ms < 160):
                    late_pitch_seen_ms[note.beat] = recent_sample.t_ms
                    note_x = note.relative_x_px + recent_sample.phase_px
                    if ctx.judgment_line_x - 70 <= note_x <= ctx.judgment_line_x + 180:
                        observed = quick_pitch_near_x(
                            recent_image, ctx.staff_lines, note_x,
                        )
                        if observed is not None:
                            late_pitch_cache[note.beat] = (
                                recent_sample.t_ms,
                                key_signature_pitch(
                                    signed_pitch_from_signature(
                                        observed[0], key_signature,
                                    ), args.key_sharps,
                                ),
                                observed[1],
                            )
            if remaining > 0:
                time.sleep(min(remaining / 1e9, 0.01))
                continue
            phase_gap_ns = (
                time.monotonic_ns() - last_good_phase_ns
                if last_good_phase_ns is not None else 0
            )
            locked_seed_gap = (
                args.seed_only and note.beat in committed_due
                and phase_gap_ns <= beat_ms * 2_500_000
            )
            if (continuous and last_good_phase_ns is not None
                    and phase_gap_ns > beat_ms * 1_000_000
                    and not locked_seed_gap
                    and (phase_gap_ns > beat_ms * 2_500_000
                         or not tracker.raw_motion_recent(
                             (time.monotonic_ns() - start_ns) / 1_000_000))):
                # A short decoder gap need not invalidate a rolling clock;
                # the separately checked onset deadline still gates late keys.
                stop_reason = "visual timing is stale at the next note"
                log("gate", stop_reason, beat=note.beat)
                break
            play_pitch = args.note_pitch.get(
                note.beat, key_signature_pitch(note.pitch, args.key_sharps),
            )
            late_pitch: str | None = None
            cached_pitch = late_pitch_cache.get(note.beat)
            if (cached_pitch is not None
                    and (time.monotonic_ns() - start_ns) / 1e6
                    - cached_pitch[0] < 220):
                late_pitch = cached_pitch[1]
                if late_pitch != play_pitch:
                    log("scan", "late pitch correction",
                        beat=note.beat, was=play_pitch,
                        now=late_pitch, score=round(cached_pitch[2], 2))
                    play_pitch = late_pitch
            if layout.target(play_pitch) is None:
                stop_reason = f"{play_pitch} has no key on the current keyboard"
                log("gate", stop_reason)
                break
            if note.duration_beats is None or (
                note.hold_beats is None and args.release_ms is None
            ):
                stop_reason = f"{note.pitch} at beat {note.beat:g} has unknown hold time"
                log("gate", stop_reason)
                break
            hold_ms = hold_ms_for(
                note.duration_beats, note.hold_beats, beat_ms,
                args.release_ms, args.long_release_ms,
            )
            if len(pending) > 1:
                following = pending[1]
                following_pitch = args.note_pitch.get(
                    following.beat,
                    key_signature_pitch(following.pitch, args.key_sharps),
                )
                hold_ms = cap_repeated_eighth_hold(
                    hold_ms, play_pitch, note.beat,
                    following_pitch, following.beat, beat_ms,
                )
            hold_ms = args.note_hold_ms.get(note.beat, hold_ms)
            key_ns = keys.press(
                pitch=play_pitch, beat=note.beat,
                deadline_ns=due_ns, hold_ms=hold_ms,
            )
            played_beats.add(note.beat)
            sent_ns_by_beat[note.beat] = key_ns
            played.append({
                "pitch": play_pitch, "read_pitch": note.pitch, "beat": note.beat,
                "late_pitch": late_pitch,
                "due_ms": round((due_ns - start_ns) / 1e6, 2),
                "sent_ms": round((key_ns - start_ns) / 1e6, 2),
                "hold_ms": round(hold_ms, 1),
                "engraving_delta_used": round(keeper.delta, 4),
                "input_to_visual_ms": (
                    round(lag_ms_used, 2) if lag_ms_used is not None else None
                ),
                "fixed_phrase": phrase_due_ns is not None,
            })
            if (args.stop_at_initial_screen_end and screen_last_beat is not None
                    and note.beat >= screen_last_beat - 0.1):
                stop_reason = "end of the initial screen"
                log("gate", stop_reason, last_beat=screen_last_beat,
                    last_pitch=play_pitch)
                break

        if stop_reason in {"end of the first playable measure", "end of the initial screen"}:
            keys.finish()
        else:
            keys.abort()
        log("gate", "playing finished; recording tail", tail_s=args.tail)
        tail_deadline = time.monotonic_ns() + int(args.tail * 1e9)
        while time.monotonic_ns() < tail_deadline:
            time.sleep(0.05)
    finally:
        try:
            keys.abort()
        except Exception as exc:
            log("input", "could not release held keys during cleanup", error=repr(exc))
        stop.set()
        try:
            pump.stop()
        except Exception:
            pass
        for thread in threads:
            thread.join(timeout=10 if thread.name == "frame-writer" else 1.5)
        if recognizer is not None:
            recognizer.shutdown(wait=True, cancel_futures=True)
        # Keep the device actions and the visible tail even if an unexpected
        # exception prevents the final summary from being assembled.
        (out_dir / "played.json").write_text(
            json.dumps(played, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        keys.record_ack_latencies()
        (out_dir / "input-log.json").write_text(
            json.dumps(keys.actions, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        if records:
            (out_dir / "frames.json").write_text(
                json.dumps(records, ensure_ascii=False), encoding="utf-8",
            )
        (out_dir / "phase.json").write_text(
            json.dumps([sample.__dict__ for sample in tracker.samples],
                       ensure_ascii=False), encoding="utf-8",
        )
        shell.close()

    notes = ledger.ordered()
    ledger_out = [{
        "beat": n.beat, "pitch": n.pitch,
        "duration_beats": n.duration_beats,
        "hold_beats": n.hold_beats, "sightings": n.sightings,
        "relative_x_px": n.relative_x_px,
    } for n in notes]
    summary = {
        "protocol": "duolingo-rehearse-song/v2",
        "serial": args.serial,
        "warmup_ms": round(warmup_ms, 2),
        "beat_ms": beat_ms,
        "tempo_refined": tempo_locked or bool(tempo_updates),
        "tempo_updates": tempo_updates,
        "stop_reason": stop_reason,
        "timing_offset_ms": args.timing_offset_ms,
        "visual_lead_ms": args.visual_lead_ms,
        "note_delay_ms": args.note_delay_ms,
        "fixed_phrases": args.fixed_phrases,
        "note_hold_ms": args.note_hold_ms,
        "note_visual_lead_ms": args.note_visual_lead_ms,
        "visual_lead_from_beat": args.visual_lead_from_beat,
        "key_highlight_latency_ms": latency.latency_ms,
        "key_highlight_samples": latency.readings,
        "key_release_latency_ms": latency.release_latency_ms,
        "key_release_samples": latency.release_readings,
        "visual_clock_calibrated": visual_ready,
        "grid": {
            "beats_per_measure": keeper.beats_per_measure,
            "px_per_beat": keeper.px_per_beat,
            "delta": round(keeper.delta, 4) if keeper.delta is not None else None,
            "spacing_px": keeper.spacing_px,
            "rejected_grids": keeper.rejected_grids,
        },
        "start_note": {"pitch": start_play_pitch, "read_pitch": start_note["pitch"],
                       "x": start_note["x"], "beat": start_beat},
        "beat_limit": beat_limit,
        "screen_last_beat": screen_last_beat,
        "scan": stats,
        "ledger_notes": len(ledger_out),
        "played": len(played),
        "frames": len(records),
        "phase_samples": len(tracker.samples),
        "dropped_saved_frames": save_stats["dropped"],
        "recording_h264": "recording.h264" if args.record_h264 else None,
        "recording_pts": "recording.pts" if args.record_h264 else None,
    }
    (out_dir / "ledger.json").write_text(json.dumps({
        "summary": summary, "notes": ledger_out}, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("rehearse", "continuous"))
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--duration", type=float,
                        help="optional maximum run time; continuous play normally ends from the screen")
    parser.add_argument("--scan-interval", type=float, default=0.4)
    parser.add_argument("--opening-note-beats", type=float,
                        help="correct a visually verified opening note duration")
    parser.add_argument("--commit-lead-beats", type=float, default=0.05,
                        help="freeze each predicted onset this many beats ahead")
    parser.add_argument("--seed-from-run", type=Path,
                        help="preload confirmed notes from a prior run's played and ledger JSON")
    parser.add_argument("--seed-note", action="append", default=[],
                        metavar="BEAT:PITCH:DURATION:RELX",
                        help="preload a visually verified score note and its barline-relative x")
    parser.add_argument("--key-sharps", default="", metavar="LETTERS",
                        help="visually verified sharp key signature, e.g. F,C,G")
    parser.add_argument("--keyboard-image", type=Path,
                        help="clear keyboard frame saved from this same challenge")
    parser.add_argument("--capture-fps", type=int, default=10,
                        help="H.264 capture cadence; raise only if reading keeps up")
    parser.add_argument("--startup-ms", type=float, default=85.0)
    parser.add_argument("--prompt-start-delay-ms", type=float, default=300.0,
                        help="fallback delay from an in-song prompt press until score scrolling resumes")
    parser.add_argument("--release-ms", type=float,
                        help="explicitly override the score reader's hold_beats")
    parser.add_argument("--long-release-ms", type=float,
                        help="release notes of at least 1.5 beats this many ms early")
    parser.add_argument("--skip-late-ms", type=float, default=120.0)
    parser.add_argument("--save-frames", action="store_true")
    parser.add_argument("--record-h264", action="store_true",
                        help="archive the live H.264 stream and device frame PTS")
    parser.add_argument("--seed-only", action="store_true",
                        help="play only beats from --seed-from-run while still tracking live video")
    parser.add_argument(
        "--min-sightings", type=int, default=2,
        help="how many readings must agree before a note is played",
    )
    parser.add_argument("--play-to-end", action="store_true",
                        help="ignore the measure stop rule and play the whole song")
    parser.add_argument("--stop-at-initial-screen-end", action="store_true",
                        help="in rehearse mode, stop after the rightmost complete note visible at launch")
    parser.add_argument("--refine-tempo", action="store_true",
                        help="re-measure the beat from a long scroll fit once enough has scrolled")
    parser.add_argument("--save-every", type=int, default=6,
                        help="write only every Nth frame; PNG encoding per frame starves the capture loop")
    parser.add_argument(
        "--max-measures", type=int, default=12,
        help="safety cap only; the real stop point comes from the score itself",
    )
    parser.add_argument("--tail", type=float, default=4.0)
    parser.add_argument(
        "--timing-offset-ms", type=float,
        help="measured onset offset for rehearsal or as a continuous-mode "
             "fallback before the visual clock is calibrated",
    )
    parser.add_argument(
        "--visual-lead-ms", type=float, default=0.0,
        help="explicit lead measured from this run's visual timing feedback",
    )
    parser.add_argument(
        "--note-delay-ms", action="append", default=[], metavar="BEAT:MS",
        help="delay one video-confirmed note by MS at its barline-anchored beat",
    )
    parser.add_argument(
        "--fixed-phrase", action="append", default=[], metavar="FIRST:LAST:MS",
        help="from FIRST through LAST, use MS per beat after FIRST is sent",
    )
    parser.add_argument(
        "--note-pitch", action="append", default=[], metavar="BEAT:PITCH",
        help="use a visually verified pitch at one barline-anchored beat",
    )
    parser.add_argument(
        "--late-pitch-check", action="store_true",
        help="recheck a pending notehead in the latest frame before pressing",
    )
    parser.add_argument(
        "--note-hold-ms", action="append", default=[], metavar="BEAT:MS",
        help="hold one video-confirmed note for MS before its key release",
    )
    parser.add_argument(
        "--note-visual-lead-ms", action="append", default=[], metavar="BEAT:MS",
        help="send a note MS before its predicted visual judgment-line crossing",
    )
    parser.add_argument(
        "--visual-lead-from-beat", action="append", default=[], metavar="BEAT:MS",
        help="use a fixed visual lead from this beat until the next switch",
    )
    parser.add_argument(
        "--beat-ms", type=float, required=True,
        help="measured milliseconds per beat",
    )
    args = parser.parse_args()
    if args.seed_only and args.seed_from_run is None:
        parser.error("--seed-only requires --seed-from-run")
    if not math.isfinite(args.prompt_start_delay_ms) or not 0 <= args.prompt_start_delay_ms <= 1500:
        parser.error("--prompt-start-delay-ms must be within [0, 1500]")
    key_sharps = [letter.strip().upper() for letter in args.key_sharps.split(",")
                  if letter.strip()]
    if len(key_sharps) != len(set(key_sharps)) or any(
        letter not in "ABCDEFG" or len(letter) != 1 for letter in key_sharps
    ):
        parser.error("--key-sharps must contain distinct note letters")
    args.key_sharps = set(key_sharps)
    if not math.isfinite(args.commit_lead_beats) or not 0 < args.commit_lead_beats <= 1:
        parser.error("--commit-lead-beats must be within (0, 1]")
    if args.opening_note_beats is not None and (
        not math.isfinite(args.opening_note_beats) or args.opening_note_beats <= 0
    ):
        parser.error("--opening-note-beats must be positive and finite")
    note_delays = {}
    for adjustment in args.note_delay_ms:
        try:
            beat_text, delay_text = adjustment.split(":", 1)
            beat, delay = float(beat_text), float(delay_text)
        except ValueError:
            parser.error("--note-delay-ms must be BEAT:MS")
        if not math.isfinite(beat) or not math.isfinite(delay):
            parser.error("--note-delay-ms requires finite numbers")
        note_delays[beat] = delay
    args.note_delay_ms = note_delays
    fixed_phrases = []
    for item in args.fixed_phrase:
        try:
            first, last, period_ms = map(float, item.split(":"))
        except ValueError:
            parser.error("--fixed-phrase must be FIRST:LAST:MS")
        if (not all(map(math.isfinite, (first, last, period_ms)))
                or first >= last or period_ms <= 0):
            parser.error("--fixed-phrase requires FIRST < LAST and positive MS")
        fixed_phrases.append((first, last, period_ms))
    if any(left[1] >= right[0] for left, right in zip(
            sorted(fixed_phrases), sorted(fixed_phrases)[1:])):
        parser.error("--fixed-phrase ranges must not overlap")
    args.fixed_phrases = sorted(fixed_phrases)
    note_pitches = {}
    for adjustment in args.note_pitch:
        try:
            beat_text, pitch = adjustment.split(":", 1)
            beat = float(beat_text)
        except ValueError:
            parser.error("--note-pitch must be BEAT:PITCH")
        if not math.isfinite(beat) or not pitch:
            parser.error("--note-pitch requires a finite beat and nonempty pitch")
        note_pitches[beat] = pitch
    args.note_pitch = note_pitches
    seed_notes = []
    for item in args.seed_note:
        try:
            beat_text, pitch, duration_text, relative_x_text = item.split(":", 3)
            beat, duration, relative_x = (
                float(beat_text), float(duration_text), float(relative_x_text)
            )
        except ValueError:
            parser.error("--seed-note must be BEAT:PITCH:DURATION:RELX")
        if (not pitch or not all(map(math.isfinite, (beat, duration, relative_x)))
                or duration <= 0):
            parser.error("--seed-note requires a pitch and finite beat, duration and x")
        seed_notes.append((beat, pitch, duration, relative_x))
    args.seed_note = seed_notes
    note_holds = {}
    for adjustment in args.note_hold_ms:
        try:
            beat_text, hold_text = adjustment.split(":", 1)
            beat, hold = float(beat_text), float(hold_text)
        except ValueError:
            parser.error("--note-hold-ms must be BEAT:MS")
        if not math.isfinite(beat) or not math.isfinite(hold) or hold <= 0:
            parser.error("--note-hold-ms requires a finite beat and positive hold")
        note_holds[beat] = hold
    args.note_hold_ms = note_holds
    visual_leads = {}
    for adjustment in args.note_visual_lead_ms:
        try:
            beat_text, lead_text = adjustment.split(":", 1)
            beat, lead = float(beat_text), float(lead_text)
        except ValueError:
            parser.error("--note-visual-lead-ms must be BEAT:MS")
        if not math.isfinite(beat) or not math.isfinite(lead) or lead < 0:
            parser.error("--note-visual-lead-ms requires a finite beat and nonnegative lead")
        visual_leads[beat] = lead
    args.note_visual_lead_ms = visual_leads
    lead_switches = {}
    for adjustment in args.visual_lead_from_beat:
        try:
            beat_text, lead_text = adjustment.split(":", 1)
            beat, lead = float(beat_text), float(lead_text)
        except ValueError:
            parser.error("--visual-lead-from-beat must be BEAT:MS")
        if not math.isfinite(beat) or not math.isfinite(lead) or lead < 0:
            parser.error("--visual-lead-from-beat requires a finite beat and nonnegative lead")
        lead_switches[beat] = lead
    args.visual_lead_from_beat = sorted(lead_switches.items())
    if args.capture_fps <= 0:
        parser.error("--capture-fps must be positive")
    if args.mode == "rehearse" and args.timing_offset_ms is None:
        parser.error("rehearse requires --timing-offset-ms")
    if args.stop_at_initial_screen_end and (args.mode != "rehearse" or args.play_to_end):
        parser.error("--stop-at-initial-screen-end requires rehearse without --play-to-end")
    summary = rehearse(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
