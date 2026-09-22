#!/usr/bin/env python3
"""Rehearse a whole Duolingo song, then perform it from the frozen ledger.

Two passes, because tempo cannot be measured from a still screen:

  rehearse  Start the song, track the scrolling barlines to measure the beat
            in pixels and milliseconds, and re-read the score as it goes by,
            stitching every reading onto one global pixel axis.  Output is a
            ledger of the whole song plus the measured tempo.
  perform   Replay that ledger from the first note on one absolute clock.

Nothing here reads a stored tempo: `spacing_px / beats_per_measure` comes from
the barlines and the scroll speed from their motion.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import importlib.util
import json
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
from duolingo_measure_tracker import (  # noqa: E402
    MeasureLineTracker,
    detect_measure_barline_candidates,
)
from duolingo_beat_grid import BeatGridError, build_beat_grid  # noqa: E402
from duolingo_measure_tracker import infer_measure_spacing  # noqa: E402

REPO_ROOT = _SCRIPTS_DIR.parent
BEATS_PER_MEASURE = 4.0


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


@dataclass
class LedgerNote:
    beat: float
    pitch: str
    duration_beats: float | None
    sightings: int = 1


@dataclass
class Ledger:
    """Notes keyed by their beat on the barline-anchored grid."""

    tolerance_beats: float = 0.25
    notes: list[LedgerNote] = field(default_factory=list)

    def add(self, beat: float, pitch: str, duration_beats: float | None) -> bool:
        for note in self.notes:
            if note.pitch == pitch and abs(note.beat - beat) <= self.tolerance_beats:
                note.sightings += 1
                if note.duration_beats is None:
                    note.duration_beats = duration_beats
                return False
        self.notes.append(LedgerNote(beat, pitch, duration_beats))
        return True

    def ordered(self) -> list[LedgerNote]:
        return sorted(self.notes, key=lambda n: n.beat)

    def confirmed(self, min_sightings: int) -> list[LedgerNote]:
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
        return sorted(best.values(), key=lambda n: n.beat)


class ScrollTracker:
    """Wrap the barline tracker into displacement, speed, and beat length."""

    def __init__(self, staff_lines, judgment_line_x):
        self._staff = list(staff_lines)
        self._judgment_x = int(judgment_line_x)
        self._tracker = MeasureLineTracker()
        self._origin_phase: float | None = None
        self.samples: list[ScrollSample] = []
        self._lock = threading.Lock()

    def observe(self, image: Image.Image, t_ms: float) -> ScrollSample:
        candidates = detect_measure_barline_candidates(image, self._staff, self._judgment_x)
        try:
            update = self._tracker.update(int(t_ms * 1e6), candidates)
        except ValueError:
            return ScrollSample(t_ms, None, None, None, None)
        sample = ScrollSample(
            t_ms, update.phase_px, update.fitted_speed_px_s,
            update.spacing_px, update.fit_r_squared,
        )
        with self._lock:
            if self._origin_phase is None and update.phase_px is not None:
                self._origin_phase = update.phase_px
            self.samples.append(sample)
        return sample

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

    Beats-per-measure and pixels-per-beat are properties of the piece, so they
    are learned once and kept; the engraving offset is cheap to re-derive and
    is re-checked on every reading.
    """

    def __init__(self) -> None:
        self.beats_per_measure: int | None = None
        self.px_per_beat: float | None = None
        self.delta: float | None = None
        self.spacing_px: float | None = None

    def update(self, events, phase_px: float, spacing_px: float | None):
        if spacing_px is None:
            return None
        try:
            grid = build_beat_grid(events, phase_px, spacing_px)
        except BeatGridError:
            return None
        if self.beats_per_measure is None:
            log("grid", "locked",
                beats_per_measure=grid.beats_per_measure,
                px_per_beat=round(grid.px_per_beat, 2),
                delta=round(grid.delta, 3))
        self.beats_per_measure = grid.beats_per_measure
        self.px_per_beat = grid.px_per_beat
        self.delta = grid.delta
        self.spacing_px = grid.spacing_px
        return grid

    @property
    def ready(self) -> bool:
        return self.px_per_beat is not None and self.delta is not None

    def beat_of(self, x: float, phase_px: float, quantum: float = 0.5) -> float:
        raw = (x - phase_px) / self.px_per_beat - self.delta
        return round(raw / quantum) * quantum


def capture_and_track(pump, tracker, recog_q, stop, start_ns, interval_s, frames_dir,
                      records, save_every=1):
    last_sequence = -1
    last_push = -1e9
    frame_index = 0
    while not stop.is_set():
        try:
            image = pump.wait_for_frame(after_sequence=last_sequence, timeout=1.0)
        except Exception:
            continue
        t_ms = (time.monotonic_ns() - start_ns) / 1e6
        last_sequence = pump.sequence
        sample = tracker.observe(image, t_ms)
        if t_ms - last_push >= interval_s * 1000.0 and sample.phase_px is not None:
            last_push = t_ms
            if recog_q.qsize() < 2:
                # the phase must come from this very frame, or the note would be
                # placed against a score position it was never seen at
                recog_q.put((image.copy(), t_ms, sample.phase_px))
        if frames_dir is not None and frame_index % save_every == 0:
            name = f"frame-{len(records):04d}.png"
            image.save(frames_dir / name, format="PNG")
            records.append({"index": len(records), "image": f"frames/{name}", "t_ms": t_ms})
        frame_index += 1


def recognition_worker(reader, keeper, recog_q, ledger, stop, stats):
    while not stop.is_set():
        try:
            image, t_ms, phase_px = recog_q.get(timeout=0.3)
        except queue.Empty:
            continue
        from duolingo_measure_tracker import detect_measure_barline_candidates
        try:
            ctx = reader.build_analysis_context(image)
            if ctx.staff_lines is None:
                continue
            notes = reader.analyze_screen_notes(ctx)
            rests = reader.analyze_screen_rests(ctx)
        except Exception:
            continue
        result = {"events": sorted([*notes, *rests], key=lambda e: e["x"])}
        spacing = infer_measure_spacing(
            detect_measure_barline_candidates(image, list(ctx.staff_lines), ctx.judgment_line_x)
        )
        keeper.update(result["events"], phase_px, spacing)
        stats["reads"] += 1
        if not keeper.ready:
            continue
        added = 0
        for event in result["events"]:
            if event["event_type"] != "note" or event.get("edge_clipped"):
                continue
            beat = keeper.beat_of(event["x"], phase_px)
            if ledger.add(beat, event["pitch"], event.get("duration_beats")):
                added += 1
        stats["added"] += added
        if added:
            log("scan", "new notes", at_ms=round(t_ms), added=added, total=len(ledger.notes))


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

    frame = kbdetect.capture_device_frame(args.serial, args.adb)
    layout = kbdetect.detect_keyboard(frame)
    image0 = Image.fromarray(frame)
    ctx = reader.build_analysis_context(image0)
    if ctx.staff_lines is None:
        raise SystemExit("no staff on screen")
    result = reader.analyze_image(image0)
    seed = [e for e in result["events"] if e["event_type"] == "note" and not e.get("edge_clipped")]
    if not seed:
        raise SystemExit("no playable notes on screen")
    start_note = min(seed, key=lambda e: e["x"])
    if layout.target(start_note["pitch"]) is None:
        raise SystemExit(
            f"start note {start_note['pitch']} has no key on this keyboard; "
            f"available: {', '.join(sorted(layout.keys))}"
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

    tracker = ScrollTracker(ctx.staff_lines, ctx.judgment_line_x)
    keeper = GridKeeper()
    ledger = Ledger()
    # Build the grid before the first key goes out.  Waiting for the first live
    # reading leaves the note half a beat after the start trigger due before
    # anything can be scheduled, which is only ~400ms away.
    seed_spacing = infer_measure_spacing(seed_candidates)
    if keeper.update(result["events"], seed_phase, seed_spacing) is not None:
        for event in result["events"]:
            if event["event_type"] != "note" or event.get("edge_clipped"):
                continue
            beat = keeper.beat_of(event["x"], seed_phase)
            ledger.add(beat, event["pitch"], event.get("duration_beats"))
        log("grid", "primed from the opening frame", seeded=len(ledger.notes))
    else:
        log("grid", "opening frame has too few barlines; waiting for a live reading")
    pump = reader.H264FramePump(args.adb, args.serial)
    shell = timed.PersistentInputShell(args.adb, args.serial, key_points=layout.keys)
    recog_q: queue.Queue = queue.Queue()
    stop = threading.Event()
    stats = {"reads": 0, "added": 0}
    played: list[dict] = []
    beat_ms = args.beat_ms

    try:
        pump.start()
        warmup_ms = shell.warmup()
        start_ns = time.monotonic_ns()
        threads = [
            threading.Thread(target=capture_and_track, daemon=True, args=(
                pump, tracker, recog_q, stop, start_ns, args.scan_interval, frames_dir,
                records, args.save_every)),
            threading.Thread(target=recognition_worker, daemon=True, args=(
                reader, keeper, recog_q, ledger, stop, stats)),
        ]
        for thread in threads:
            thread.start()

        # The first note doubles as the start trigger, so it is played on sight;
        # everything after it is timed against this one press.
        press_ns = start_ns + int(args.startup_ms * 1e6)
        while (remaining := press_ns - time.monotonic_ns()) > 0:
            time.sleep(min(remaining / 1e9, 0.004))
        sequence = 3000
        sent_ns, _ = shell.send("DOWN", start_note["pitch"], sequence)
        start_hold = max((start_note.get("duration_beats") or 1.0) * beat_ms - args.release_ms, 80.0)
        threading.Timer(start_hold / 1000.0,
                        lambda: shell.send("UP", start_note["pitch"], 3500)).start()
        log("play", "start note sent", pitch=start_note["pitch"], x=start_note["x"])

        start_beat = None
        beat_limit = None
        anchor_ns = sent_ns
        anchor_beat = None
        tempo_locked = False
        played_beats: set[float] = set()
        deadline_ns = start_ns + int(args.duration * 1e9)

        while time.monotonic_ns() < deadline_ns and not stop.is_set():
            if start_beat is None:
                if not keeper.ready:
                    time.sleep(0.02)
                    continue
                start_beat = keeper.beat_of(start_note["x"], seed_phase)
                anchor_beat = start_beat
                played_beats.add(start_beat)
                log("grid", "anchored on the start note",
                    start_beat=start_beat, beats_per_measure=keeper.beats_per_measure)
            pending = [
                n for n in ledger.confirmed(args.min_sightings)
                if n.beat not in played_beats
            ]
            if not pending:
                time.sleep(0.01)
                continue
            note = pending[0]
            if note.beat <= start_beat:
                played_beats.add(note.beat)
                continue
            if not tempo_locked and args.refine_tempo:
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
            if args.play_to_end:
                limit = None
            else:
                limit = stop_beat_for(ledger, start_beat, keeper.beats_per_measure)
            if limit is not None and limit != beat_limit:
                beat_limit = limit
                log("gate", "stop point resolved from the score",
                    first_played_measure_ends_at=beat_limit)
            safety = start_beat + args.max_measures * keeper.beats_per_measure
            if not args.play_to_end and beat_limit is not None and note.beat >= beat_limit:
                log("gate", "reached the end of the first playable measure",
                    next_beat=note.beat, limit=beat_limit)
                break
            if not args.play_to_end and note.beat >= safety:
                log("gate", "safety cap reached before any playable measure appeared",
                    cap_measures=args.max_measures, next_beat=note.beat)
                break
            due_ns = anchor_ns + int((note.beat - anchor_beat) * beat_ms * 1e6)
            if due_ns < time.monotonic_ns() - int(args.skip_late_ms * 1e6):
                played_beats.add(note.beat)
                log("skip", "discovered too late", beat=note.beat, pitch=note.pitch)
                continue
            while (remaining := due_ns - time.monotonic_ns()) > 0:
                time.sleep(min(remaining / 1e9, 0.004))
            sequence += 1
            key_ns, _ = shell.send("DOWN", note.pitch, sequence)
            hold_ms = max((note.duration_beats or 0.5) * beat_ms - args.release_ms, 80.0)
            played_beats.add(note.beat)
            played.append({
                "pitch": note.pitch, "beat": note.beat,
                "due_ms": round((due_ns - start_ns) / 1e6, 2),
                "sent_ms": round((key_ns - start_ns) / 1e6, 2),
                "hold_ms": round(hold_ms, 1),
            })
            threading.Timer(
                hold_ms / 1000.0,
                lambda pitch=note.pitch, seq=sequence + 500: shell.send("UP", pitch, seq),
            ).start()

        log("gate", "playing finished; recording tail", tail_s=args.tail)
        tail_deadline = time.monotonic_ns() + int(args.tail * 1e9)
        while time.monotonic_ns() < tail_deadline:
            time.sleep(0.05)
    finally:
        stop.set()
        time.sleep(0.4)
        try:
            pump.stop()
        except Exception:
            pass

    notes = ledger.ordered()
    ledger_out = [{
        "beat": n.beat, "pitch": n.pitch,
        "duration_beats": n.duration_beats, "sightings": n.sightings,
    } for n in notes]
    summary = {
        "protocol": "duolingo-rehearse-song/v2",
        "serial": args.serial,
        "warmup_ms": round(warmup_ms, 2),
        "beat_ms": beat_ms,
        "tempo_refined": tempo_locked,
        "grid": {
            "beats_per_measure": keeper.beats_per_measure,
            "px_per_beat": keeper.px_per_beat,
            "delta": round(keeper.delta, 4) if keeper.delta is not None else None,
            "spacing_px": keeper.spacing_px,
        },
        "start_note": {"pitch": start_note["pitch"], "x": start_note["x"], "beat": start_beat},
        "beat_limit": beat_limit,
        "scan": stats,
        "ledger_notes": len(ledger_out),
        "played": len(played),
        "frames": len(records),
    }
    (out_dir / "ledger.json").write_text(json.dumps({
        "summary": summary, "notes": ledger_out}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "played.json").write_text(
        json.dumps(played, ensure_ascii=False, indent=2), encoding="utf-8")
    if records:
        (out_dir / "frames.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("rehearse",))
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--scan-interval", type=float, default=0.4)
    parser.add_argument("--startup-ms", type=float, default=85.0)
    parser.add_argument("--release-ms", type=float, default=60.0)
    parser.add_argument("--skip-late-ms", type=float, default=120.0)
    parser.add_argument("--save-frames", action="store_true")
    parser.add_argument(
        "--min-sightings", type=int, default=2,
        help="how many readings must agree before a note is played",
    )
    parser.add_argument("--play-to-end", action="store_true",
                        help="ignore the measure stop rule and play the whole song")
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
        "--beat-ms", type=float, required=True,
        help="measured milliseconds per beat",
    )
    args = parser.parse_args()
    summary = rehearse(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
