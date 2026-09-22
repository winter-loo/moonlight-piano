"""Place recognized score events on a beat grid anchored to the barlines.

A notehead is drawn a fixed distance to the right of the beat it sounds on, so
anchoring the grid to the first notehead bakes that padding into every later
beat number.  Barlines carry no such padding and, unlike a single first note,
they recur, so any reading error is re-anchored one measure later instead of
accumulating.

With `p` the tracked (unwrapped) barline phase of a frame, barlines sit at
`p + k * spacing` for integer k, hence

    beat = (x - p) / px_per_beat - delta

is independent of which frame the note was seen in: the scroll displacement
cancels out entirely, so the grid cannot drift.

`delta` cannot be recovered from note positions alone -- the note lattice is
periodic, so delta and delta+quantum fit equally well.  It is resolved from
structure instead: a measure's events must tile it exactly, starting at the
barline.  Beats per measure is likewise derived, never assumed: time
signatures other than 4/4 are common.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_QUANTUM = 0.5


@dataclass(frozen=True)
class BeatGrid:
    spacing_px: float
    beats_per_measure: int
    px_per_beat: float
    delta: float
    quantum: float = DEFAULT_QUANTUM
    closed_measures: int = 0
    checked_measures: int = 0
    duration_estimate_px_per_beat: float | None = None
    fit_residual_beats: float = 0.0

    def beat_of(self, x: float, phase_px: float) -> float:
        return (x - phase_px) / self.px_per_beat - self.delta

    def snapped_beat_of(self, x: float, phase_px: float) -> float:
        raw = self.beat_of(x, phase_px)
        return round(raw / self.quantum) * self.quantum


class BeatGridError(RuntimeError):
    """Raised when the frame does not support a trustworthy grid."""


def estimate_px_per_beat(events) -> float | None:
    """Rough px-per-beat from each event's own notated length.

    Only accurate to a few percent, which is all that is needed: it exists to
    pick the integer beats-per-measure, after which the precise value comes
    back from the barline spacing.
    """
    usable = [e for e in events if not e.get("edge_clipped") and e.get("delta_beats")]
    samples = [
        (right["x"] - left["x"]) / float(left["delta_beats"])
        for left, right in zip(usable, usable[1:])
        if right["x"] > left["x"]
    ]
    if not samples:
        return None
    return float(np.median(samples))


def derive_beats_per_measure(spacing_px: float, px_per_beat_estimate: float) -> int:
    if spacing_px <= 0 or px_per_beat_estimate <= 0:
        raise BeatGridError("spacing and px-per-beat must be positive")
    ratio = spacing_px / px_per_beat_estimate
    beats = int(round(ratio))
    if beats < 2 or beats > 12:
        raise BeatGridError(f"implausible beats per measure: {ratio:.2f}")
    if abs(ratio - beats) / beats > 0.12:
        raise BeatGridError(
            f"beats per measure is ambiguous: {ratio:.2f} is not close to {beats}"
        )
    return beats


def _measure_closure_score(events, phase_px, px_per_beat, delta, beats_per_measure, quantum):
    """Count measures whose events tile them exactly, starting at the barline.

    Translating the whole reading by one quantum keeps every measure tiling --
    the quarter note simply moves along with the eighths -- so closure alone
    cannot pick the offset.  What does is physical: a notehead has to be drawn
    inside the measure it belongs to, which fails once `delta` pushes the last
    note of a measure past the next barline.
    """
    placed = []
    for event in events:
        if event.get("edge_clipped") or not event.get("delta_beats"):
            continue
        raw = (event["x"] - phase_px) / px_per_beat - delta
        snapped = round(raw / quantum) * quantum
        if int(np.floor(raw / beats_per_measure)) != int(
            np.floor(snapped / beats_per_measure)
        ):
            return -1, 0        # this note would be drawn past its own barline
        placed.append((snapped, float(event["delta_beats"])))
    if not placed:
        return 0, 0
    by_measure: dict[int, list] = {}
    for beat, duration in placed:
        by_measure.setdefault(int(np.floor(beat / beats_per_measure)), []).append(
            (beat, duration)
        )
    lo, hi = min(by_measure), max(by_measure)
    closed = checked = 0
    for index in range(lo + 1, hi):          # interior measures only: edges are cut off
        items = sorted(by_measure.get(index, []))
        if not items:
            continue
        checked += 1
        start = items[0][0] - index * beats_per_measure
        total = sum(d for _, d in items)
        contiguous = all(
            abs((items[i][0] + items[i][1]) - items[i + 1][0]) < quantum / 2
            for i in range(len(items) - 1)
        )
        if abs(start) < quantum / 2 and abs(total - beats_per_measure) < quantum / 2 and contiguous:
            closed += 1
    return closed, checked


def resolve_delta(events, phase_px, px_per_beat, beats_per_measure, quantum=DEFAULT_QUANTUM):
    """Pick the grid offset, which residual fitting alone cannot do.

    The note lattice repeats every `quantum`, so `delta` and `delta + quantum`
    fit the positions identically; measure closure does not separate them
    either, because translating the reading moves the longer notes along with
    the short ones and still tiles.  What separates them is physical: `delta`
    is the engraving gap between a barline and a note sounding on the downbeat,
    so it is non-negative, and the last note of a measure must still be drawn
    before the next barline.
    """
    usable = [
        e for e in events
        if not e.get("edge_clipped") and e.get("delta_beats")
    ]
    if not usable:
        raise BeatGridError("no usable events to place")
    raws = np.array([(e["x"] - phase_px) / px_per_beat for e in usable])

    probe = np.arange(0.0, quantum, quantum / 200.0)
    residuals = [
        float(np.abs(((raws - d) / quantum) - np.round((raws - d) / quantum)).mean())
        for d in probe
    ]
    base = float(probe[int(np.argmin(residuals))])
    fit_residual = float(min(residuals)) * quantum

    accepted = None
    aliases = max(1, int(round(beats_per_measure / quantum)))
    for step in range(aliases):
        candidate = base + step * quantum
        snapped = np.round((raws - candidate) / quantum) * quantum
        offsets = snapped - np.floor(snapped / beats_per_measure) * beats_per_measure
        if float(offsets.max()) + candidate >= beats_per_measure:
            continue        # the last note of a measure would cross its barline
        accepted = candidate
        break               # candidates ascend, and the engraving gap is small
    if accepted is None:
        raise BeatGridError("every grid offset would draw a note past its barline")

    closed, checked = _measure_closure_score(
        events, phase_px, px_per_beat, accepted, beats_per_measure, quantum
    )
    return accepted, max(closed, 0), checked, fit_residual


def build_beat_grid(events, phase_px, spacing_px, *, quantum=DEFAULT_QUANTUM) -> BeatGrid:
    estimate = estimate_px_per_beat(events)
    if estimate is None:
        raise BeatGridError("not enough notated events to estimate px-per-beat")
    beats_per_measure = derive_beats_per_measure(spacing_px, estimate)
    px_per_beat = spacing_px / beats_per_measure
    delta, closed, checked, fit_residual = resolve_delta(
        events, phase_px, px_per_beat, beats_per_measure, quantum
    )
    return BeatGrid(
        spacing_px=float(spacing_px),
        beats_per_measure=beats_per_measure,
        px_per_beat=float(px_per_beat),
        delta=float(delta),
        quantum=quantum,
        closed_measures=closed,
        checked_measures=checked,
        duration_estimate_px_per_beat=estimate,
        fit_residual_beats=fit_residual,
    )
