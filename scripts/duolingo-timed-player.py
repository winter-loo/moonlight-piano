#!/usr/bin/env python3
"""Play the recorded Duolingo score with an absolute, duration-aware clock.

The score is read from section 21.3 of the product document.  Only the first
visible chunk is scheduled initially.  Later chunks are appended three beats
before their start, while a separate ADB process continuously captures PNG
frames.  Piano input never waits for frame capture or UI target recognition.
"""

from __future__ import annotations

import argparse
import dataclasses
import heapq
import io
import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import BinaryIO

import numpy as np
from PIL import Image
from scipy import ndimage


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCORE_DOC = REPO_ROOT / "docs/product/月光琴房-产品文档-v0.1.md"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs/duolingo-stage4-section7/timed-run"
REMOTE_INPUT_BRIDGE = "/data/local/tmp/codex-input-bridge.jar"

KEYBOARD_PROFILES = {
    "greensleeves-c4": {
        "C4": (178, 600),
        "C#4": (246, 475),
        "D4": (312, 600),
        "D#4": (379, 475),
        "E4": (445, 600),
        "F4": (594, 600),
        "F#4": (660, 475),
        "G4": (727, 600),
        "G#4": (794, 475),
        "A4": (860, 600),
        "A#4": (927, 475),
        "B4": (993, 600),
        "C5": (1127, 600),
        "C#5": (1209, 475),
        "D5": (1260, 600),
        "D#5": (1342, 475),
        "E5": (1393, 600),
    },
    # Stage 4, section 12 opens a wider keyboard at F4.  Spell the two
    # signature accidentals as flats so score events retain musical intent.
    "saints-f4": {
        "F4": (173, 600),
        "G4": (294, 600),
        "A4": (415, 600),
        "Bb4": (476, 475),
        "B4": (536, 600),
        "C5": (653, 600),
        "D5": (774, 600),
        "Eb5": (855, 475),
        "E5": (895, 600),
        "F5": (1053, 600),
        "G5": (1174, 600),
        "A5": (1295, 600),
        "Bb5": (1355, 475),
        "B5": (1416, 600),
    },
    # Stage 4, section 14's continuous Musette challenge uses the same
    # nominal F4-B5 range but shifts the middle white-key hit regions. These
    # centers are measured from this challenge's own key boundaries.
    "musette-ultimate-f4": {
        "F4": (173, 600),
        "G4": (294, 600),
        "A4": (415, 600),
        "Bb4": (476, 475),
        "B4": (536, 600),
        "C5": (673, 600),
        "D5": (794, 600),
        "Eb5": (855, 475),
        "E5": (915, 600),
        "F5": (1052, 600),
        "G5": (1173, 600),
        "A5": (1294, 600),
        "Bb5": (1355, 475),
        "B5": (1415, 600),
    },
}

# The wide F-to-B keyboard is used by lessons whose displayed key signature
# contains B-flat and E-flat. Staff-position recovery produces diatonic letter
# names first; spell those affected degrees before dispatching device input.
KEY_SIGNATURE_SPELLINGS = {
    "saints-f4": {
        "B4": "Bb4",
        "E5": "Eb5",
        "B5": "Bb5",
    },
    "musette-ultimate-f4": {
        "B4": "Bb4",
        "E5": "Eb5",
        "B5": "Bb5",
    },
}

DURATION_BEATS = {
    "e": 0.5,
    "q": 1.0,
    "q.": 1.5,
    "h": 2.0,
}

# Chunk boundaries match the groups previously transcribed from the scrolling
# score.  A new chunk is loaded one measure (three beats) before it is needed.
CHUNK_MEASURES = ((1, 10), (11, 19), (20, 26), (27, 34))
LOOKAHEAD_BEATS = 3.0


@dataclasses.dataclass(frozen=True)
class ScoreEvent:
    measure: int
    pitch: str | None
    start_beat: float
    duration_beats: float


@dataclasses.dataclass(order=True, frozen=True)
class InputAction:
    beat: float
    order: int
    sequence: int
    kind: str = dataclasses.field(compare=False)
    pitch: str = dataclasses.field(compare=False)
    measure: int = dataclasses.field(compare=False)


@dataclasses.dataclass(order=True, frozen=True)
class AbsoluteInputAction:
    deadline_ns: int
    order: int
    sequence: int
    kind: str = dataclasses.field(compare=False)
    pitch: str = dataclasses.field(compare=False)
    beat_slot: int = dataclasses.field(compare=False)


@dataclasses.dataclass(frozen=True)
class Chunk:
    index: int
    first_measure: int
    last_measure: int
    events: tuple[ScoreEvent, ...]

    @property
    def first_beat(self) -> float:
        return (self.first_measure - 1) * 3.0

    @property
    def load_beat(self) -> float:
        return max(0.0, self.first_beat - LOOKAHEAD_BEATS)


@dataclasses.dataclass(frozen=True)
class DetectedNote:
    x_min: int
    x_max: int
    pitch_options: tuple[str, ...]
    duration_beats: float | None
    area: int
    dotted: bool


@dataclasses.dataclass(frozen=True)
class VisibleEvent:
    pitch: str
    onset_beats: float
    duration_beats: float
    glyph_index: int


def _staff_c4_y(image: np.ndarray) -> float:
    """Locate C4's ledger-line y from the five rendered staff lines."""

    candidate_rows: list[int] = []
    for y in range(100, 380):
        row = image[y, 100:1500]
        neutral = (
            (np.max(row, axis=1) - np.min(row, axis=1) < 8)
            & (np.mean(row, axis=1) > 175)
            & (np.mean(row, axis=1) < 235)
        )
        if int(neutral.sum()) > 700:
            candidate_rows.append(y)

    bands: list[list[int]] = []
    for y in candidate_rows:
        if not bands or y > bands[-1][-1] + 1:
            bands.append([y])
        else:
            bands[-1].append(y)
    centers = [sum(band) / len(band) for band in bands]
    for start in range(len(centers) - 4):
        group = centers[start : start + 5]
        gaps = [b - a for a, b in zip(group, group[1:])]
        if all(34.0 <= gap <= 42.0 for gap in gaps):
            staff_step = sum(gaps) / len(gaps) / 2
            # The bottom treble-staff line is E4; C4 is two diatonic steps below.
            return group[-1] + 2 * staff_step
    raise ValueError("could not locate five evenly spaced staff lines")


def _judgment_line_x(image: np.ndarray) -> int:
    """Return the left edge of Duolingo's translucent judgment overlay."""

    best_x = 0
    best_score = 0
    for x in range(300, 520):
        column = image[80:400, x]
        neutral = (
            (np.max(column, axis=1) - np.min(column, axis=1) < 6)
            & (np.mean(column, axis=1) > 225)
            & (np.mean(column, axis=1) < 252)
        )
        score = int(neutral.sum())
        if score > best_score:
            best_x = x
            best_score = score
    if best_score < 100:
        raise ValueError("could not locate the judgment overlay")
    return best_x


def _pitch_at_staff_y(y: float, c4_y: float) -> str | None:
    pitch_index = round((c4_y - y) / 19.0)
    pitches = (
        "C4",
        "D4",
        "E4",
        "F4",
        "G4",
        "A4",
        "B4",
        "C5",
        "D5",
        "E5",
        "F5",
        "G5",
        "A5",
        "B5",
        "C6",
    )
    if 0 <= pitch_index < len(pitches):
        return pitches[pitch_index]
    return None


def analyze_staff_png(png: bytes) -> tuple[DetectedNote, ...]:
    """Recover dark, not-yet-played notes from one 1612x720 score frame."""

    image = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
    if image.shape[1::-1] != (1612, 720):
        raise ValueError(f"unexpected screenshot size: {image.shape[1]}x{image.shape[0]}")

    c4_y = _staff_c4_y(image)
    judgment_x = _judgment_line_x(image)
    current_x_limit = judgment_x + 55
    x0, x1, y0, y1 = 320, 1500, 120, 380
    roi = image[y0:y1, x0:x1]
    # Future glyphs use a neutral dark gray.  Played/current glyphs become
    # saturated colors and intentionally fall out of this mask.
    # Newer Duolingo lessons draw pending glyph stems around RGB 150 rather
    # than the older sub-125 gray. The staff remains much lighter, while
    # saturated played/current notes still fall outside this neutral mask.
    mask = np.max(roi, axis=2) < 160
    seen = np.zeros(mask.shape, dtype=bool)
    height, width = mask.shape
    components: list[dict[str, object]] = []

    for seed_y, seed_x in zip(*np.nonzero(mask)):
        if seen[seed_y, seed_x]:
            continue
        stack = [(int(seed_y), int(seed_x))]
        seen[seed_y, seed_x] = True
        points: list[tuple[int, int]] = []
        while stack:
            y, x = stack.pop()
            points.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if (
                        0 <= ny < height
                        and 0 <= nx < width
                        and mask[ny, nx]
                        and not seen[ny, nx]
                    ):
                        seen[ny, nx] = True
                        stack.append((ny, nx))

        if len(points) < 100:
            continue
        ys = np.fromiter((point[0] for point in points), dtype=int)
        xs = np.fromiter((point[1] for point in points), dtype=int)
        components.append(
            {
                "area": len(points),
                "x_min": int(xs.min()) + x0,
                "x_max": int(xs.max()) + x0,
                "y_min": int(ys.min()) + y0,
                "y_max": int(ys.max()) + y0,
                "ys": ys + y0,
            }
        )

    main = [
        component
        for component in components
        if int(component["area"]) >= 1500
        or (
            int(component["x_min"]) <= current_x_limit
            and int(component["area"]) >= 900
        )
    ]
    dots = [
        component
        for component in components
        if 120 <= int(component["area"]) <= 350
        and int(component["x_max"]) - int(component["x_min"]) <= 24
    ]

    detected: list[DetectedNote] = []
    represented_components: set[int] = set()

    # Filled noteheads are broad ellipses; stems and beams are comparatively
    # thin. Opening with an elliptical kernel separates every head even when
    # multiple eighth notes belong to one connected beam component.
    kernel_y, kernel_x = np.mgrid[-5:6, -8:9]
    head_kernel = (kernel_x / 8.5) ** 2 + (kernel_y / 5.5) ** 2 <= 1
    opened = ndimage.binary_opening(mask, structure=head_kernel)
    head_labels, _ = ndimage.label(opened)
    for slices in ndimage.find_objects(head_labels):
        if slices is None:
            continue
        y_slice, x_slice = slices
        head_area = int(opened[slices].sum())
        head_width = x_slice.stop - x_slice.start
        head_height = y_slice.stop - y_slice.start
        if not (
            1300 <= head_area <= 2100
            and 35 <= head_width <= 60
            and 30 <= head_height <= 60
        ):
            continue

        head_pixels_y, head_pixels_x = np.nonzero(opened[slices])
        head_x = float(head_pixels_x.mean() + x_slice.start + x0)
        head_y = float(head_pixels_y.mean() + y_slice.start + y0)
        head_x_min = x_slice.start + x0
        head_x_max = x_slice.stop - 1 + x0
        # During a scroll transition the previously played head can remain
        # dark for one frame just left of the judgment line. It is historical
        # feedback, not the next event to schedule.
        if head_x_min < judgment_x - 8:
            continue
        parents = [
            component
            for component in components
            if int(component["x_min"]) <= head_x <= int(component["x_max"])
            and int(component["y_min"]) <= head_y <= int(component["y_max"])
        ]
        if not parents:
            continue
        parent = min(parents, key=lambda item: int(item["area"]))
        represented_components.add(id(parent))
        pitch = _pitch_at_staff_y(head_y, c4_y)
        if pitch is None:
            continue

        dotted = any(
            head_x_min < int(dot["x_min"]) <= head_x_max + 24
            for dot in dots
        )
        if dotted:
            duration_beats: float | None = 1.5
        elif int(parent["area"]) >= 3400:
            # A beam remains visible even when its first head is underneath
            # the judgment overlay, so its eighth-note duration is reliable.
            duration_beats = 0.5
        elif head_x_min <= current_x_limit:
            duration_beats = None
        else:
            duration_beats = 1.0
        detected.append(
            DetectedNote(
                x_min=head_x_min,
                x_max=head_x_max,
                pitch_options=(pitch,),
                duration_beats=duration_beats,
                area=int(parent["area"]),
                dotted=dotted,
            )
        )

    # Hollow half notes do not survive the filled-head opening. Preserve the
    # component-level fallback for any glyph not represented above.
    for component in sorted(main, key=lambda item: int(item["x_min"])):
        if id(component) in represented_components:
            continue
        area = int(component["area"])
        x_min = int(component["x_min"])
        x_max = int(component["x_max"])
        y_max = int(component["y_max"])
        ys = np.asarray(component["ys"])
        row_values, row_counts = np.unique(ys, return_counts=True)
        filled_head_y = float(row_values[int(np.argmax(row_counts))])
        # A hollow head can have either an upward or downward stem, so its
        # vertical center cannot be inferred from one end of the component.
        # Rows crossing the oval are much wider than stem-only rows; the
        # midpoint of that wide band is the stable pitch location.
        wide_head_rows = row_values[row_counts >= 15]
        hollow_head_y = (
            float((wide_head_rows.min() + wide_head_rows.max()) / 2)
            if len(wide_head_rows)
            else filled_head_y
        )

        pitch_options = []
        for candidate_y in (
            (filled_head_y,) if x_min <= current_x_limit else (
                hollow_head_y if area < 2700 else filled_head_y,
            )
        ):
            pitch = _pitch_at_staff_y(candidate_y, c4_y)
            if pitch is not None and pitch not in pitch_options:
                pitch_options.append(pitch)
        if not pitch_options:
            continue

        dotted = any(
            x_min < int(dot["x_min"]) <= x_max + 24
            for dot in dots
        )
        if dotted:
            duration_beats: float | None = 1.5
        elif area >= 3400:
            duration_beats = 0.5
        elif x_min <= current_x_limit:
            # The judgment line/color overlay clips the current glyph, so its
            # fill state is not reliable.  Score matching resolves the duration.
            duration_beats = None
        elif area < 2700:
            duration_beats = 2.0
        else:
            duration_beats = 1.0

        detected.append(
            DetectedNote(
                x_min=x_min,
                x_max=x_max,
                pitch_options=tuple(pitch_options),
                duration_beats=duration_beats,
                area=area,
                dotted=dotted,
            )
        )
    return tuple(sorted(detected, key=lambda note: note.x_min))


def frame_shows_exit_x(png: bytes) -> bool:
    """Distinguish a complete static prompt from the active performance UI.

    The left control alone is not a sufficient state signal: during phrase
    transitions Duolingo can briefly draw an X-shaped intermediate frame.  A
    real launch prompt also has the centered ``Play <pitch> to start`` text,
    while performance feedback is confined to the left of the staff.
    """

    image = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
    dark = np.max(image, axis=2) < 190
    diagonal_hits = 0
    samples = 0
    for y in range(38, 92):
        progress = (y - 38) / (91 - 38)
        for x in (round(108 + 42 * progress), round(150 - 42 * progress)):
            samples += 1
            if dark[y - 3 : y + 4, x - 3 : x + 4].any():
                diagonal_hits += 1
    center_hits = int(dark[38:92, 122:136].sum())
    prompt_text_hits = int(dark[20:115, 560:1050].sum())
    return (
        diagonal_hits >= samples * 0.8
        and center_hits >= 100
        and prompt_text_hits >= 1000
    )


def locate_score_window(
    detected: tuple[DetectedNote, ...],
    score_notes: tuple[ScoreEvent, ...],
    *,
    search_first: int,
    search_last: int,
    hint: int,
) -> tuple[int, int] | None:
    """Return (score note index, matched glyph count) for a visible window."""

    if not detected:
        return None
    candidates: list[tuple[int, int, int]] = []
    for start in range(search_first, min(search_last, len(score_notes) - 1) + 1):
        matched = 0
        for offset, glyph in enumerate(detected):
            score_index = start + offset
            if score_index >= len(score_notes):
                break
            event = score_notes[score_index]
            if event.pitch not in glyph.pitch_options:
                break
            if (
                glyph.duration_beats is not None
                and abs(event.duration_beats - glyph.duration_beats) > 1e-9
            ):
                break
            matched += 1
        if matched:
            candidates.append((matched, -abs(start - hint), start))
    if not candidates:
        return None
    matched, _, start = max(candidates)
    return start, matched


def locate_prompt_window(
    detected: tuple[DetectedNote, ...],
    score_notes: tuple[ScoreEvent, ...],
    *,
    prompt_pitch: str,
    search_first: int,
    search_last: int,
    hint: int,
) -> tuple[int, int] | None:
    """Locate a static prompt while forcing its accessibility-reported pitch."""

    candidates: list[tuple[int, int, int]] = []
    for start in range(search_first, min(search_last, len(score_notes) - 1) + 1):
        if score_notes[start].pitch != prompt_pitch:
            continue
        matched = 0
        for offset, glyph in enumerate(detected):
            score_index = start + offset
            if score_index >= len(score_notes):
                break
            event = score_notes[score_index]
            if event.pitch not in glyph.pitch_options:
                break
            if (
                glyph.duration_beats is not None
                and abs(event.duration_beats - glyph.duration_beats) > 1e-9
            ):
                break
            matched += 1
        if matched:
            candidates.append((matched, -abs(start - hint), start))
    if not candidates:
        return None
    matched, _, start = max(candidates)
    return start, matched


def read_prompt_pitch(adb: str, serial: str) -> str | None:
    """Read the one static launch letter exposed by Duolingo's native view tree."""

    try:
        result = subprocess.run(
            [
                adb,
                "-s",
                serial,
                "shell",
                "uiautomator dump /sdcard/codex-window.xml >/dev/null 2>&1; "
                "cat /sdcard/codex-window.xml",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=6,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    match = re.search(r'在琴键上弹 ([A-G]) 开始', result.stdout)
    return None if match is None else f"{match.group(1)}4"


def parse_score_document(path: Path) -> tuple[ScoreEvent, ...]:
    row_re = re.compile(r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|$")
    token_re = re.compile(r"^(R|[A-G]4)\((e|q\.|q|h)\)$")
    rows: dict[int, list[str]] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        row = row_re.match(line)
        if not row:
            continue
        measure = int(row.group(1))
        if 1 <= measure <= 34:
            rows[measure] = [token.strip() for token in row.group(2).split(",")]

    if sorted(rows) != list(range(1, 35)):
        missing = sorted(set(range(1, 35)) - rows.keys())
        raise ValueError(f"score table is incomplete; missing measures: {missing}")

    events: list[ScoreEvent] = []
    for measure in range(1, 35):
        beat = (measure - 1) * 3.0
        measure_duration = 0.0
        for token in rows[measure]:
            match = token_re.match(token)
            if not match:
                raise ValueError(f"unsupported score token in measure {measure}: {token!r}")
            raw_pitch, raw_duration = match.groups()
            duration = DURATION_BEATS[raw_duration]
            events.append(
                ScoreEvent(
                    measure=measure,
                    pitch=None if raw_pitch == "R" else raw_pitch,
                    start_beat=beat + measure_duration,
                    duration_beats=duration,
                )
            )
            measure_duration += duration
        if abs(measure_duration - 3.0) > 1e-9:
            raise ValueError(
                f"measure {measure} contains {measure_duration:g} beats instead of 3"
            )

    notes = sum(event.pitch is not None for event in events)
    rests = sum(event.pitch is None for event in events)
    if (notes, rests) != (75, 10):
        raise ValueError(f"unexpected score totals: {notes} notes, {rests} rests")
    return tuple(events)


def make_chunks(events: tuple[ScoreEvent, ...]) -> tuple[Chunk, ...]:
    chunks = []
    for index, (first, last) in enumerate(CHUNK_MEASURES):
        chunk_events = tuple(
            event for event in events if first <= event.measure <= last
        )
        chunks.append(Chunk(index, first, last, chunk_events))
    return tuple(chunks)


class FramePump:
    """Continuously retain the newest complete PNG from one ADB stream."""

    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
    IEND_PREFIX = b"\x00\x00\x00\x00IEND"

    def __init__(self, adb: str, serial: str) -> None:
        self._adb = adb
        self._serial = serial
        self._process: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest: bytes | None = None
        self._latest_ns = 0
        self._frames = 0
        self._error: str | None = None

    def start(self) -> None:
        # One long-lived exec-out connection is materially cheaper than starting
        # a new adb process for every frame.  PNG boundaries are recovered from
        # the standard IEND chunk.
        self._process = subprocess.Popen(
            [
                self._adb,
                "-s",
                self._serial,
                "exec-out",
                "sh",
                "-c",
                "while true; do screencap -p; sleep 0.05; done",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        stream: BinaryIO = self._process.stdout
        buffer = bytearray()
        try:
            while True:
                block = stream.read(64 * 1024)
                if not block:
                    break
                buffer.extend(block)
                while True:
                    start = buffer.find(self.PNG_SIGNATURE)
                    if start < 0:
                        if len(buffer) > len(self.PNG_SIGNATURE):
                            del buffer[: -len(self.PNG_SIGNATURE)]
                        break
                    end_marker = buffer.find(self.IEND_PREFIX, start)
                    if end_marker < 0:
                        if start:
                            del buffer[:start]
                        break
                    end = end_marker + 12  # length + IEND + CRC
                    png = bytes(buffer[start:end])
                    del buffer[:end]
                    with self._lock:
                        self._latest = png
                        self._latest_ns = time.monotonic_ns()
                        self._frames += 1
        except Exception as exc:  # pragma: no cover - diagnostic path on device
            self._error = repr(exc)

    def wait_for_first_frame(self, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if self._latest is not None:
                    return
            time.sleep(0.02)
        raise TimeoutError("continuous ADB frame stream produced no PNG")

    def checkpoint(self, path: Path) -> dict[str, float | int | str | None]:
        with self._lock:
            png = self._latest
            captured_ns = self._latest_ns
            frames = self._frames
            error = self._error
        if png is None:
            raise RuntimeError("cannot checkpoint before the first frame")
        path.write_bytes(png)
        now_ns = time.monotonic_ns()
        return {
            "path": str(path),
            "frame": frames,
            "age_ms": (now_ns - captured_ns) / 1_000_000,
            "stream_error": error,
        }

    def latest(self) -> tuple[bytes, int, float]:
        with self._lock:
            png = self._latest
            captured_ns = self._latest_ns
            frames = self._frames
        if png is None:
            raise RuntimeError("frame stream has not produced a PNG yet")
        return png, frames, (time.monotonic_ns() - captured_ns) / 1_000_000

    def stop(self) -> dict[str, float | int | str | None]:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2.0)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        with self._lock:
            return {"frames": self._frames, "stream_error": self._error}


class PersistentInputShell:
    def __init__(
        self,
        adb: str,
        serial: str,
        *,
        key_points: dict[str, tuple[int, int]],
    ) -> None:
        self._condition = threading.Condition()
        self._ack_ns: dict[int, int] = {}
        self._sent = 0
        self._key_points = key_points
        self._process = subprocess.Popen(
            [
                adb,
                "-s",
                serial,
                "shell",
                "-t",
                f"CLASSPATH={REMOTE_INPUT_BRIDGE} "
                "app_process /system/bin CodexInputBridge",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_acks, daemon=True)
        self._reader.start()

    def _read_acks(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            match = re.search(r"__ACK__(\d+)", line)
            if match is None:
                continue
            sequence = int(match.group(1))
            with self._condition:
                self._ack_ns[sequence] = time.monotonic_ns()
                self._condition.notify_all()

    def send(
        self,
        kind: str,
        pitch: str,
        sequence: int,
        *,
        x_offset: int = 0,
    ) -> tuple[int, int]:
        if self._process.poll() is not None:
            raise RuntimeError(f"persistent adb shell exited with {self._process.returncode}")
        assert self._process.stdin is not None
        sent_ns = time.monotonic_ns()
        x, y = self._key_points[pitch]
        self._process.stdin.write(
            f"{kind} {x + x_offset} {y} {sequence}\n"
        )
        self._process.stdin.flush()
        with self._condition:
            self._sent += 1
            pending = self._sent - len(self._ack_ns)
        return sent_ns, pending

    @property
    def pitches(self) -> tuple[str, ...]:
        return tuple(self._key_points)

    def wait_for(self, sequences: set[int], timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            while not sequences.issubset(self._ack_ns):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def ack_ns(self, sequence: int) -> int | None:
        with self._condition:
            return self._ack_ns.get(sequence)

    def close(self) -> str:
        if self._process.stdin is not None:
            try:
                self._process.stdin.write("exit\n")
                self._process.stdin.flush()
            except (BrokenPipeError, ValueError):
                pass
            try:
                self._process.stdin.close()
            except BrokenPipeError:
                pass
        try:
            self._process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            self._process.wait(timeout=2.0)
        self._reader.join(timeout=2.0)
        assert self._process.stderr is not None
        return self._process.stderr.read()


class LiveActionScheduler:
    """Send absolute-time input actions while vision keeps reading frames."""

    def __init__(
        self,
        input_shell: PersistentInputShell,
        action_log: list[dict[str, object]],
    ) -> None:
        self._input_shell = input_shell
        self._action_log = action_log
        self._condition = threading.Condition()
        self._heap: list[AbsoluteInputAction] = []
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._closing = False
        self._active = False
        self._next_sequence = 0
        self._sent_sequences: set[int] = set()
        self._error: str | None = None

    def start(self) -> None:
        self._thread.start()

    def schedule_note(
        self,
        *,
        pitch: str,
        beat_slot: int,
        onset_ns: int,
        duration_beats: float,
        beat_ns: int,
    ) -> tuple[int, int]:
        with self._condition:
            down_sequence = self._next_sequence
            up_sequence = self._next_sequence + 1
            self._next_sequence += 2
            heapq.heappush(
                self._heap,
                AbsoluteInputAction(
                    onset_ns,
                    1,
                    down_sequence,
                    "DOWN",
                    pitch,
                    beat_slot,
                ),
            )
            heapq.heappush(
                self._heap,
                AbsoluteInputAction(
                    onset_ns + round(duration_beats * beat_ns),
                    0,
                    up_sequence,
                    "UP",
                    pitch,
                    beat_slot,
                ),
            )
            self._condition.notify_all()
        return down_sequence, up_sequence

    def schedule_action(
        self,
        *,
        kind: str,
        pitch: str,
        deadline_ns: int,
        beat_slot: int,
        order: int,
    ) -> int:
        """Queue one independently timed key edge for a visual controller."""

        with self._condition:
            sequence = self._next_sequence
            self._next_sequence += 1
            heapq.heappush(
                self._heap,
                AbsoluteInputAction(
                    deadline_ns,
                    order,
                    sequence,
                    kind,
                    pitch,
                    beat_slot,
                ),
            )
            self._condition.notify_all()
        return sequence

    def _run(self) -> None:
        try:
            while True:
                with self._condition:
                    while not self._heap and not self._closing:
                        self._condition.wait()
                    if not self._heap and self._closing:
                        return
                    action = self._heap[0]
                    remaining_ns = action.deadline_ns - time.monotonic_ns()
                    if remaining_ns > 0:
                        self._condition.wait(remaining_ns / 1_000_000_000)
                        continue
                    heapq.heappop(self._heap)
                    self._active = True

                sent_ns, pending = self._input_shell.send(
                    action.kind, action.pitch, action.sequence
                )
                self._action_log.append(
                    {
                        "sequence": action.sequence,
                        "beat_slot": action.beat_slot,
                        "beat": action.beat_slot / 2,
                        "kind": action.kind,
                        "pitch": action.pitch,
                        "scheduled_ns": action.deadline_ns,
                        "sent_ns": sent_ns,
                        "send_drift_ms": (
                            sent_ns - action.deadline_ns
                        )
                        / 1_000_000,
                        "device_queue_depth_after_send": pending,
                    }
                )
                with self._condition:
                    self._sent_sequences.add(action.sequence)
                    self._active = False
                    self._condition.notify_all()
        except Exception as exc:  # pragma: no cover - live device failure path
            with self._condition:
                self._error = repr(exc)
                self._active = False
                self._closing = True
                self._heap.clear()
                self._condition.notify_all()

    def wait_until_idle(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._heap or self._active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def stop(self, *, cancel_pending: bool) -> None:
        with self._condition:
            if cancel_pending:
                self._heap.clear()
            self._closing = True
            self._condition.notify_all()
        self._thread.join(timeout=3.0)

    @property
    def next_sequence(self) -> int:
        with self._condition:
            return self._next_sequence

    @property
    def sent_sequences(self) -> set[int]:
        with self._condition:
            return set(self._sent_sequences)

    @property
    def error(self) -> str | None:
        with self._condition:
            return self._error


def add_chunk_actions(
    heap: list[InputAction], chunk: Chunk, next_sequence: int
) -> int:
    for event in chunk.events:
        if event.pitch is None:
            continue
        # At the same beat, releases sort before presses.  This preserves a
        # monophonic key-up/key-down boundary without changing score time.
        heapq.heappush(
            heap,
            InputAction(
                event.start_beat,
                1,
                next_sequence,
                "DOWN",
                event.pitch,
                event.measure,
            ),
        )
        next_sequence += 1
        heapq.heappush(
            heap,
            InputAction(
                event.start_beat + event.duration_beats,
                0,
                next_sequence,
                "UP",
                event.pitch,
                event.measure,
            ),
        )
        next_sequence += 1
    return next_sequence


def wait_until_ns(deadline_ns: int) -> None:
    # Sleeping most of the interval avoids spinning for a full minute; the last
    # 2 ms are kept local so scheduler wake-up error does not accumulate.
    while True:
        remaining_ns = deadline_ns - time.monotonic_ns()
        if remaining_ns <= 0:
            return
        if remaining_ns > 2_000_000:
            time.sleep((remaining_ns - 1_000_000) / 1_000_000_000)


def run(args: argparse.Namespace) -> dict[str, object]:
    adb = shutil.which(args.adb)
    if adb is None:
        raise FileNotFoundError(f"adb executable not found: {args.adb}")

    events = parse_score_document(args.score_doc)
    chunks = make_chunks(events)
    beat_ns = round(60_000_000_000 / args.bpm)
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    log: dict[str, object] = {
        "serial": args.serial,
        "bpm": args.bpm,
        "quarter_ms": beat_ns / 1_000_000,
        "score": {
            "measures": 34,
            "notes": sum(event.pitch is not None for event in events),
            "rests": sum(event.pitch is None for event in events),
            "beats": 102,
        },
        "chunks": [],
        "actions": [],
    }

    frames = FramePump(adb, args.serial)
    input_shell = PersistentInputShell(
        adb,
        args.serial,
        key_points=KEYBOARD_PROFILES[args.keyboard_profile],
    )
    action_heap: list[InputAction] = []
    next_sequence = add_chunk_actions(action_heap, chunks[0], 0)
    next_chunk_index = 1

    frames.start()
    stream_summary: dict[str, float | int | str | None] = {}
    try:
        frames.wait_for_first_frame()
        initial = frames.checkpoint(output_dir / "chunk-01-initial.png")
        initial.update({"chunk": 1, "measures": [1, 10], "load_beat": 0.0})
        log["chunks"].append(initial)  # type: ignore[union-attr]

        start_ns = time.monotonic_ns() + round(args.pre_roll * 1_000_000_000)
        log["start_monotonic_ns"] = start_ns

        while action_heap or next_chunk_index < len(chunks):
            next_action_ns = (
                start_ns + round(action_heap[0].beat * beat_ns)
                if action_heap
                else 2**63 - 1
            )
            next_chunk = chunks[next_chunk_index] if next_chunk_index < len(chunks) else None
            next_load_ns = (
                start_ns + round(next_chunk.load_beat * beat_ns)
                if next_chunk is not None
                else 2**63 - 1
            )

            if next_load_ns <= next_action_ns:
                wait_until_ns(next_load_ns)
                assert next_chunk is not None
                checkpoint = frames.checkpoint(
                    output_dir / f"chunk-{next_chunk.index + 1:02d}-lookahead.png"
                )
                checkpoint.update(
                    {
                        "chunk": next_chunk.index + 1,
                        "measures": [next_chunk.first_measure, next_chunk.last_measure],
                        "load_beat": next_chunk.load_beat,
                        "load_drift_ms": (time.monotonic_ns() - next_load_ns) / 1_000_000,
                    }
                )
                log["chunks"].append(checkpoint)  # type: ignore[union-attr]
                next_sequence = add_chunk_actions(
                    action_heap, next_chunk, next_sequence
                )
                next_chunk_index += 1
                continue

            action = heapq.heappop(action_heap)
            deadline_ns = start_ns + round(action.beat * beat_ns)
            wait_until_ns(deadline_ns)
            sent_ns, pending = input_shell.send(
                action.kind, action.pitch, action.sequence
            )
            log["actions"].append(  # type: ignore[union-attr]
                {
                    "sequence": action.sequence,
                    "beat": action.beat,
                    "measure": action.measure,
                    "kind": action.kind,
                    "pitch": action.pitch,
                    "scheduled_ns": deadline_ns,
                    "sent_ns": sent_ns,
                    "send_drift_ms": (sent_ns - deadline_ns) / 1_000_000,
                    "device_queue_depth_after_send": pending,
                }
            )
    finally:
        score_sequences = {
            int(action["sequence"])
            for action in log["actions"]  # type: ignore[union-attr]
        }
        log["all_score_actions_acked"] = input_shell.wait_for(
            score_sequences, timeout=5.0
        )
        for action in log["actions"]:  # type: ignore[union-attr]
            ack_ns = input_shell.ack_ns(int(action["sequence"]))
            action["device_ack_ns"] = ack_ns
            action["device_ack_drift_ms"] = (
                None
                if ack_ns is None
                else (ack_ns - int(action["scheduled_ns"])) / 1_000_000
            )

        # If the run is interrupted between DOWN and UP, release every possible
        # white key before closing the session.
        release_sequences: set[int] = set()
        for index, pitch in enumerate(input_shell.pitches):
            release_sequence = next_sequence + index
            try:
                input_shell.send("UP", pitch, release_sequence)
                release_sequences.add(release_sequence)
            except Exception:
                break
        input_shell.wait_for(release_sequences, timeout=2.0)
        log["input_shell_stderr"] = input_shell.close()
        stream_summary = frames.stop()
        log["frame_stream"] = stream_summary

    drifts = [
        abs(float(action["send_drift_ms"]))
        for action in log["actions"]  # type: ignore[union-attr]
    ]
    drifts.sort()
    if drifts:
        p95_index = min(len(drifts) - 1, int(len(drifts) * 0.95))
        log["absolute_send_drift_ms"] = {
            "median": drifts[len(drifts) // 2],
            "p95": drifts[p95_index],
            "max": drifts[-1],
        }

    ack_drifts = sorted(
        abs(float(action["device_ack_drift_ms"]))
        for action in log["actions"]  # type: ignore[union-attr]
        if action["device_ack_drift_ms"] is not None
    )
    if ack_drifts:
        p95_index = min(len(ack_drifts) - 1, int(len(ack_drifts) * 0.95))
        log["absolute_device_ack_drift_ms"] = {
            "median": ack_drifts[len(ack_drifts) // 2],
            "p95": ack_drifts[p95_index],
            "max": ack_drifts[-1],
        }

    log_path = output_dir / "timing-log.json"
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"log_path": str(log_path), **log}


def run_known_tail(args: argparse.Namespace) -> dict[str, object]:
    """Play one confirmed score position through the end on one beat clock."""

    adb = shutil.which(args.adb)
    if adb is None:
        raise FileNotFoundError(f"adb executable not found: {args.adb}")
    events = parse_score_document(args.score_doc)
    score_notes = tuple(event for event in events if event.pitch is not None)
    if not 0 <= args.score_start_index < len(score_notes):
        raise ValueError(
            f"score start index must be in [0, {len(score_notes) - 1}]"
        )
    first_note = score_notes[args.score_start_index]
    tail_end = len(score_notes)
    if args.known_note_count > 0:
        tail_end = min(
            len(score_notes),
            args.score_start_index + args.known_note_count,
        )
    tail = score_notes[args.score_start_index : tail_end]
    beat_ns = round(60_000_000_000 / args.bpm)
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    log: dict[str, object] = {
        "mode": "known-score-tail-absolute-clock",
        "serial": args.serial,
        "bpm": args.bpm,
        "quarter_ms": beat_ns / 1_000_000,
        "score_start_index": args.score_start_index,
        "score_start_beat": first_note.start_beat,
        "tail_note_count": len(tail),
        "after_first_gap_beats": args.after_first_gap_beats,
        "release_advance_ms": args.release_advance_ms,
        "same_pitch_extra_gap_ms": args.same_pitch_extra_gap_ms,
        "extra_gap_after_index": args.extra_gap_after_index,
        "extra_gap_beats": args.extra_gap_beats,
        "prompt_key_x_offset": args.prompt_key_x_offset,
        "stop_at_next_prompt": args.stop_at_next_prompt,
        "actions": [],
    }
    action_list: list[InputAction] = []
    sequence = 0

    def scheduled_relative_beat(tail_index: int) -> float:
        absolute_index = args.score_start_index + tail_index
        relative_beat = tail[tail_index].start_beat - first_note.start_beat
        if tail_index > 0:
            relative_beat += args.after_first_gap_beats
        if (
            args.score_start_index <= args.extra_gap_after_index < absolute_index
        ):
            relative_beat += args.extra_gap_beats
        return relative_beat

    for note_index, note in enumerate(tail):
        assert note.pitch is not None
        relative_beat = scheduled_relative_beat(note_index)
        action_list.append(
            InputAction(
                relative_beat,
                1,
                sequence,
                "DOWN",
                note.pitch,
                note.measure,
            )
        )
        sequence += 1
        release_beat = relative_beat + note.duration_beats
        if note_index + 1 < len(tail):
            next_relative_beat = scheduled_relative_beat(note_index + 1)
            if (
                abs(next_relative_beat - release_beat) < 1e-9
            ):
                release_advance_ms = args.release_advance_ms
                if tail[note_index + 1].pitch == note.pitch:
                    release_advance_ms += args.same_pitch_extra_gap_ms
                release_advance_beats = release_advance_ms * args.bpm / 60_000
                release_beat -= release_advance_beats
        action_list.append(
            InputAction(
                release_beat,
                0,
                sequence,
                "UP",
                note.pitch,
                note.measure,
            )
        )
        sequence += 1
    action_list.sort(key=lambda action: (action.beat, action.order, action.sequence))

    frames = FramePump(adb, args.serial)
    input_shell = PersistentInputShell(
        adb,
        args.serial,
        key_points=KEYBOARD_PROFILES[args.keyboard_profile],
    )
    prompt_monitor_stop = threading.Event()
    frame_archive_stop = threading.Event()
    prompt_state_lock = threading.Lock()
    prompt_state: dict[str, object] = {
        "frame": 0,
        "showing_exit": True,
        "seen_active": False,
        "error": None,
    }

    def monitor_prompt_state() -> None:
        last_frame = -1
        while not prompt_monitor_stop.wait(0.01):
            try:
                latest_png, frame_number, _ = frames.latest()
                if frame_number == last_frame:
                    continue
                last_frame = frame_number
                showing_exit = frame_shows_exit_x(latest_png)
                with prompt_state_lock:
                    prompt_state["frame"] = frame_number
                    prompt_state["showing_exit"] = showing_exit
                    if not showing_exit:
                        prompt_state["seen_active"] = True
            except Exception as exc:
                with prompt_state_lock:
                    prompt_state["error"] = repr(exc)
                return

    prompt_monitor: threading.Thread | None = None
    frame_archive_thread: threading.Thread | None = None
    archived_frames: list[dict[str, object]] = []

    def archive_latest_frames() -> None:
        archive_dir = output_dir / "frames"
        archive_dir.mkdir(parents=True, exist_ok=True)
        last_frame = -1
        while not frame_archive_stop.wait(0.005):
            try:
                latest_png, frame_number, age_ms = frames.latest()
                if frame_number <= last_frame:
                    continue
                captured_ns = time.monotonic_ns() - round(age_ms * 1_000_000)
                frame_path = archive_dir / f"frame-{frame_number:04d}.png"
                frame_path.write_bytes(latest_png)
                archived_frames.append(
                    {
                        "frame": frame_number,
                        "captured_ns": captured_ns,
                        "path": str(frame_path),
                    }
                )
                last_frame = frame_number
            except Exception as exc:
                archived_frames.append({"error": repr(exc)})
                return

    frames.start()
    try:
        frames.wait_for_first_frame()
        if args.archive_frames:
            frame_archive_thread = threading.Thread(
                target=archive_latest_frames,
                name="duolingo-frame-archive",
                daemon=True,
            )
            frame_archive_thread.start()
        if args.stop_at_next_prompt:
            prompt_monitor = threading.Thread(
                target=monitor_prompt_state,
                name="duolingo-prompt-monitor",
                daemon=True,
            )
            prompt_monitor.start()
        log["initial_checkpoint"] = frames.checkpoint(
            output_dir / "tail-initial.png"
        )
        start_ns = time.monotonic_ns() + round(args.pre_roll * 1_000_000_000)
        log["start_monotonic_ns"] = start_ns
        stopped_at_next_prompt = False
        for action in action_list:
            deadline_ns = start_ns + round(action.beat * beat_ns)
            wait_until_ns(deadline_ns)
            if args.stop_at_next_prompt:
                with prompt_state_lock:
                    showing_exit = bool(prompt_state["showing_exit"])
                    seen_active = bool(prompt_state["seen_active"])
                if showing_exit and seen_active and action.kind == "DOWN":
                    stopped_at_next_prompt = True
                    break
            prompt_x_offset = (
                args.prompt_key_x_offset if action.sequence in (0, 1) else 0
            )
            sent_ns, pending = input_shell.send(
                action.kind,
                action.pitch,
                action.sequence,
                x_offset=prompt_x_offset,
            )
            log["actions"].append(  # type: ignore[union-attr]
                {
                    "sequence": action.sequence,
                    "relative_beat": action.beat,
                    "measure": action.measure,
                    "kind": action.kind,
                    "pitch": action.pitch,
                    "x_offset": prompt_x_offset,
                    "scheduled_ns": deadline_ns,
                    "sent_ns": sent_ns,
                    "send_drift_ms": (sent_ns - deadline_ns) / 1_000_000,
                    "device_queue_depth_after_send": pending,
                }
            )
        with prompt_state_lock:
            log["prompt_monitor"] = dict(prompt_state)
            seen_active_performance = bool(prompt_state["seen_active"])
        log["seen_active_performance"] = seen_active_performance
        log["stopped_at_next_prompt"] = stopped_at_next_prompt
        score_sequences = {
            int(action["sequence"])
            for action in log["actions"]  # type: ignore[union-attr]
        }
        log["all_score_actions_acked"] = input_shell.wait_for(
            score_sequences, timeout=5.0
        )
        time.sleep(args.result_wait)
        log["result_checkpoint"] = frames.checkpoint(
            output_dir / "tail-result.png"
        )
    finally:
        prompt_monitor_stop.set()
        frame_archive_stop.set()
        if prompt_monitor is not None:
            prompt_monitor.join(timeout=1.0)
        if frame_archive_thread is not None:
            frame_archive_thread.join(timeout=1.0)
        if args.archive_frames:
            log["archived_frames"] = archived_frames
        for action in log["actions"]:  # type: ignore[union-attr]
            ack_ns = input_shell.ack_ns(int(action["sequence"]))
            action["device_ack_ns"] = ack_ns
            action["device_ack_drift_ms"] = (
                None
                if ack_ns is None
                else (ack_ns - int(action["scheduled_ns"])) / 1_000_000
            )
        release_sequences: set[int] = set()
        for index, pitch in enumerate(input_shell.pitches):
            release_sequence = sequence + index
            try:
                input_shell.send("UP", pitch, release_sequence)
                release_sequences.add(release_sequence)
            except Exception:
                break
        input_shell.wait_for(release_sequences, timeout=2.0)
        log["input_shell_stderr"] = input_shell.close()
        log["frame_stream"] = frames.stop()

        drifts = sorted(
            abs(float(action["send_drift_ms"]))
            for action in log["actions"]  # type: ignore[union-attr]
        )
        if drifts:
            p95_index = min(len(drifts) - 1, int(len(drifts) * 0.95))
            log["absolute_send_drift_ms"] = {
                "median": drifts[len(drifts) // 2],
                "p95": drifts[p95_index],
                "max": drifts[-1],
            }
        log_path = output_dir / "timing-log.json"
        log_path.write_text(
            json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {"log_path": str(log_path), **log}


def run_segmented(args: argparse.Namespace) -> dict[str, object]:
    """Play visible score windows and re-anchor time between windows."""

    adb = shutil.which(args.adb)
    if adb is None:
        raise FileNotFoundError(f"adb executable not found: {args.adb}")
    events = parse_score_document(args.score_doc)
    score_notes = tuple(event for event in events if event.pitch is not None)
    beat_ns = round(60_000_000_000 / args.bpm)
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    log: dict[str, object] = {
        "mode": "visible-score-segments",
        "serial": args.serial,
        "bpm": args.bpm,
        "quarter_ms": beat_ns / 1_000_000,
        "score": {"measures": 34, "notes": 75, "rests": 10, "beats": 102},
        "segments": [],
        "actions": [],
    }
    frames = FramePump(adb, args.serial)
    input_shell = PersistentInputShell(
        adb,
        args.serial,
        key_points=KEYBOARD_PROFILES[args.keyboard_profile],
    )
    sequence = 0
    segment_number = 0
    search_floor = max(0, args.score_start_index - 2)
    expected_hint = args.score_start_index
    minimum_frame = 0

    def glyph_json(glyph: DetectedNote) -> dict[str, object]:
        return {
            "x": [glyph.x_min, glyph.x_max],
            "pitch_options": list(glyph.pitch_options),
            "duration_beats": glyph.duration_beats,
            "area": glyph.area,
            "dotted": glyph.dotted,
        }

    frames.start()
    try:
        frames.wait_for_first_frame()
        while expected_hint < len(score_notes):
            wait_started_ns = time.monotonic_ns()
            selected: tuple[bytes, int, float, tuple[DetectedNote, ...], int, int] | None = None
            deadline = time.monotonic() + args.segment_timeout
            last_checked_frame = -1

            while time.monotonic() < deadline:
                png, frame_number, age_ms = frames.latest()
                if frame_number <= max(minimum_frame, last_checked_frame):
                    time.sleep(0.02)
                    continue
                last_checked_frame = frame_number
                try:
                    detected = analyze_staff_png(png)
                except ValueError:
                    # Score scrolls and round transitions can briefly erase or
                    # distort one of the five staff lines. A newer stream frame
                    # is the correct recovery; no input should be scheduled.
                    continue
                if not detected or detected[0].x_min > 430:
                    continue

                # A segment can fail after its first accepted note, so retain a
                # small overlap behind the expected next index.  The hint and
                # visible duration pattern select the closest real position.
                if args.global_reanchor:
                    search_first = 0
                    search_last = len(score_notes) - 1
                else:
                    search_first = max(0, search_floor)
                    search_last = min(
                        len(score_notes) - 1,
                        max(expected_hint + 8, search_first + 8),
                    )
                located = locate_score_window(
                    detected,
                    score_notes,
                    search_first=search_first,
                    search_last=search_last,
                    hint=expected_hint,
                )
                if located is None:
                    continue
                start_index, matched = located
                required_match = min(3, len(score_notes) - start_index)
                initial_single_note = (
                    segment_number == 0 and start_index == 0 and matched == 1
                )
                if (
                    not initial_single_note
                    and matched < required_match
                    and start_index + matched < len(score_notes)
                ):
                    continue
                selected = (
                    png,
                    frame_number,
                    age_ms,
                    detected,
                    start_index,
                    matched,
                )
                break

            if selected is None:
                raise TimeoutError(
                    f"could not localize the next visible segment near note {expected_hint}"
                )

            png, frame_number, age_ms, detected, start_index, matched = selected
            playable = min(args.segment_notes, matched)
            segment_notes = score_notes[start_index : start_index + playable]
            checkpoint = output_dir / f"segment-{segment_number + 1:02d}.png"
            checkpoint.write_bytes(png)
            segment_record: dict[str, object] = {
                "segment": segment_number + 1,
                "frame": frame_number,
                "frame_age_ms": age_ms,
                "checkpoint": str(checkpoint),
                "wait_for_visible_ms": (
                    time.monotonic_ns() - wait_started_ns
                )
                / 1_000_000,
                "localized_note_index": start_index,
                "matched_visible_notes": matched,
                "played_note_count": playable,
                "detected": [glyph_json(glyph) for glyph in detected],
                "played": [
                    {
                        "score_note_index": start_index + offset,
                        "measure": note.measure,
                        "pitch": note.pitch,
                        "duration_beats": note.duration_beats,
                    }
                    for offset, note in enumerate(segment_notes)
                ],
            }
            log["segments"].append(segment_record)  # type: ignore[union-attr]

            start_ns = time.monotonic_ns() + round(args.pre_roll * 1_000_000_000)
            cursor_beats = 0.0
            local_actions: list[InputAction] = []
            for offset, note in enumerate(segment_notes):
                assert note.pitch is not None
                local_actions.append(
                    InputAction(
                        cursor_beats,
                        1,
                        sequence,
                        "DOWN",
                        note.pitch,
                        note.measure,
                    )
                )
                sequence += 1
                cursor_beats += note.duration_beats
                local_actions.append(
                    InputAction(
                        cursor_beats,
                        0,
                        sequence,
                        "UP",
                        note.pitch,
                        note.measure,
                    )
                )
                sequence += 1

            # Release-before-press ordering at equal beats preserves legato
            # boundaries without extending the previous note.
            local_actions.sort(key=lambda action: (action.beat, action.order, action.sequence))
            segment_sequences: set[int] = set()
            for action in local_actions:
                deadline_ns = start_ns + round(action.beat * beat_ns)
                wait_until_ns(deadline_ns)
                sent_ns, pending = input_shell.send(
                    action.kind, action.pitch, action.sequence
                )
                segment_sequences.add(action.sequence)
                log["actions"].append(  # type: ignore[union-attr]
                    {
                        "sequence": action.sequence,
                        "segment": segment_number + 1,
                        "local_beat": action.beat,
                        "measure": action.measure,
                        "kind": action.kind,
                        "pitch": action.pitch,
                        "scheduled_ns": deadline_ns,
                        "sent_ns": sent_ns,
                        "send_drift_ms": (sent_ns - deadline_ns) / 1_000_000,
                        "device_queue_depth_after_send": pending,
                    }
                )
            segment_record["all_actions_acked"] = input_shell.wait_for(
                segment_sequences, timeout=3.0
            )
            for action in log["actions"]:  # type: ignore[union-attr]
                if action.get("segment") != segment_number + 1:
                    continue
                ack_ns = input_shell.ack_ns(int(action["sequence"]))
                action["device_ack_ns"] = ack_ns
                action["device_ack_drift_ms"] = (
                    None
                    if ack_ns is None
                    else (ack_ns - int(action["scheduled_ns"])) / 1_000_000
                )

            # Do not assume every scheduled key was accepted.  The next score
            # position is established from the next visible frame, with this
            # endpoint used only as a localization hint.
            expected_hint = start_index + playable
            search_floor = start_index
            _, minimum_frame, _ = frames.latest()
            segment_number += 1
            if segment_number > 30:
                raise RuntimeError("segment controller made no bounded progress")

        log["completed_score_notes"] = expected_hint
    finally:
        release_sequences: set[int] = set()
        for index, pitch in enumerate(input_shell.pitches):
            release_sequence = sequence + index
            try:
                input_shell.send("UP", pitch, release_sequence)
                release_sequences.add(release_sequence)
            except Exception:
                break
        input_shell.wait_for(release_sequences, timeout=2.0)
        log["input_shell_stderr"] = input_shell.close()
        log["frame_stream"] = frames.stop()
        log_path = output_dir / "timing-log.json"
        log_path.write_text(
            json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {"log_path": str(log_path), **log}


def resolve_visible_window(
    detected: tuple[DetectedNote, ...],
    *,
    approaching: tuple[str, float] | None,
    initial_duration: float,
    pixels_per_beat: float,
    maximum_notes: int,
) -> tuple[VisibleEvent, ...]:
    """Convert one visual score window into device-independent note events."""

    if not detected:
        return ()
    first_x = detected[0].x_min
    resolved: list[VisibleEvent] = []
    previous_end = 0.0
    for index, glyph in enumerate(detected[:maximum_notes]):
        if index == 0 and approaching is not None:
            cached_pitch, cached_duration = approaching
            if cached_pitch in glyph.pitch_options:
                pitch = cached_pitch
                duration = cached_duration
            else:
                pitch = glyph.pitch_options[-1]
                duration = glyph.duration_beats
        else:
            # Under the vertical judgment overlay, the actual head is the lower
            # of the two geometry candidates.  Future glyphs have one candidate.
            pitch = glyph.pitch_options[-1]
            duration = glyph.duration_beats

        if duration is None:
            if index != 0:
                break
            duration = initial_duration

        geometric_onset = max(0.0, (glyph.x_min - first_x) / pixels_per_beat)
        onset = max(geometric_onset, previous_end)
        resolved.append(
            VisibleEvent(
                pitch=pitch,
                onset_beats=onset,
                duration_beats=duration,
                glyph_index=index,
            )
        )
        previous_end = onset + duration
    return tuple(resolved)


def run_generic_visible(args: argparse.Namespace) -> dict[str, object]:
    """Play an unknown monophonic score using only the live visible staff."""

    adb = shutil.which(args.adb)
    if adb is None:
        raise FileNotFoundError(f"adb executable not found: {args.adb}")
    beat_ns = round(60_000_000_000 / args.bpm)
    beat_ms = beat_ns / 1_000_000
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    log: dict[str, object] = {
        "mode": "generic-visible-score",
        "serial": args.serial,
        "bpm": args.bpm,
        "quarter_ms": beat_ms,
        "pixels_per_beat": args.pixels_per_beat,
        "segments": [],
        "actions": [],
    }
    frames = FramePump(adb, args.serial)
    input_shell = PersistentInputShell(
        adb,
        args.serial,
        key_points=KEYBOARD_PROFILES[args.keyboard_profile],
    )
    sequence = 0
    segment_number = 0
    minimum_frame = 0
    completed = False
    carried_approaching: tuple[str, float] | None = None
    prompt_consumed = False
    last_scheduled_signature: tuple[object, ...] | None = None
    duplicate_frames_skipped = 0

    def glyph_json(glyph: DetectedNote) -> dict[str, object]:
        return {
            "x": [glyph.x_min, glyph.x_max],
            "pitch_options": list(glyph.pitch_options),
            "duration_beats": glyph.duration_beats,
            "area": glyph.area,
            "dotted": glyph.dotted,
        }

    frames.start()
    try:
        frames.wait_for_first_frame()
        while not completed:
            wait_started_ns = time.monotonic_ns()
            selected: tuple[
                bytes,
                int,
                float,
                tuple[DetectedNote, ...],
                tuple[VisibleEvent, ...],
            ] | None = None
            selected_signature: tuple[object, ...] | None = None
            approaching = carried_approaching
            deadline = time.monotonic() + args.segment_timeout
            last_checked_frame = -1

            while time.monotonic() < deadline:
                png, frame_number, age_ms = frames.latest()
                if frame_number <= max(minimum_frame, last_checked_frame):
                    time.sleep(0.01)
                    continue
                last_checked_frame = frame_number

                size = Image.open(io.BytesIO(png)).size
                if size != (1612, 720):
                    if segment_number:
                        completion = output_dir / "completion-screen.png"
                        completion.write_bytes(png)
                        log["completion_checkpoint"] = str(completion)
                        log["completion_frame_size"] = list(size)
                        completed = True
                        break
                    continue

                detected = analyze_staff_png(png)
                if not detected:
                    continue
                showing_prompt = frame_shows_exit_x(png)
                if prompt_consumed:
                    if showing_prompt:
                        continue
                    prompt_consumed = False
                first = detected[0]
                if first.x_min > 430:
                    if (
                        len(first.pitch_options) == 1
                        and first.duration_beats is not None
                    ):
                        approaching = (
                            first.pitch_options[0],
                            first.duration_beats,
                        )
                    continue

                visible = resolve_visible_window(
                    detected,
                    approaching=approaching,
                    initial_duration=args.initial_duration,
                    pixels_per_beat=args.pixels_per_beat,
                    maximum_notes=args.segment_notes,
                )
                spellings = KEY_SIGNATURE_SPELLINGS.get(
                    args.keyboard_profile, {}
                )
                visible = tuple(
                    dataclasses.replace(
                        event,
                        pitch=spellings.get(event.pitch, event.pitch),
                    )
                    for event in visible
                )
                if not visible:
                    continue

                # A failed key does not advance Duolingo's score.  In that
                # state the live stream keeps yielding fresh PNG frames, but
                # scheduling the unchanged window again would turn one error
                # into a rapid cascade.  Combine the quantized staff geometry
                # with the course progress strip so an intentionally repeated
                # musical phrase at a later position remains distinguishable.
                frame_array = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
                progress_strip = frame_array[:25, :, :]
                progress_green_pixels = int(
                    (
                        (progress_strip[:, :, 0] < 130)
                        & (progress_strip[:, :, 1] > 150)
                        & (progress_strip[:, :, 2] < 100)
                    ).sum()
                )
                candidate_signature: tuple[object, ...] = (
                    progress_green_pixels // 40,
                    tuple(
                        (
                            glyph.x_min // 8,
                            glyph.x_max // 8,
                            glyph.pitch_options,
                            glyph.duration_beats,
                        )
                        for glyph in detected
                    ),
                )
                if candidate_signature == last_scheduled_signature:
                    duplicate_frames_skipped += 1
                    continue
                selected = (png, frame_number, age_ms, detected, visible)
                selected_signature = candidate_signature
                break

            if completed:
                break
            if selected is None:
                png, frame_number, _ = frames.latest()
                timeout_path = output_dir / f"timeout-after-segment-{segment_number:02d}.png"
                timeout_path.write_bytes(png)
                raise TimeoutError(
                    f"no playable note reached the judgment line after segment "
                    f"{segment_number}; frame {frame_number} saved to {timeout_path}"
                )

            png, frame_number, age_ms, detected, visible = selected
            assert selected_signature is not None
            last_scheduled_signature = selected_signature
            if frame_shows_exit_x(png):
                prompt_consumed = True
            checkpoint = output_dir / f"segment-{segment_number + 1:02d}.png"
            checkpoint.write_bytes(png)

            # Re-detect the judgment line for every lesson layout. Frame age is
            # subtracted because the score keeps moving after capture.
            selected_image = np.asarray(
                Image.open(io.BytesIO(png)).convert("RGB")
            )
            judgment_x = _judgment_line_x(selected_image)
            lead_beats = max(
                0.0,
                (detected[0].x_min - judgment_x) / args.pixels_per_beat
                - age_ms / beat_ms,
            )
            segment_record: dict[str, object] = {
                "segment": segment_number + 1,
                "frame": frame_number,
                "frame_age_ms": age_ms,
                "wait_for_visible_ms": (
                    time.monotonic_ns() - wait_started_ns
                )
                / 1_000_000,
                "lead_beats": lead_beats,
                "judgment_x": judgment_x,
                "checkpoint": str(checkpoint),
                "approaching_cache": (
                    None
                    if approaching is None
                    else {"pitch": approaching[0], "duration_beats": approaching[1]}
                ),
                "detected": [glyph_json(glyph) for glyph in detected],
                "played": [dataclasses.asdict(event) for event in visible],
            }
            log["segments"].append(segment_record)  # type: ignore[union-attr]

            # The first visible glyph not scheduled in this segment is already
            # fully readable.  Retain it across the action loop so it remains
            # known if it reaches the overlay before the next analyzed frame.
            carried_approaching = None
            next_glyph_index = len(visible)
            if next_glyph_index < len(detected):
                next_glyph = detected[next_glyph_index]
                if (
                    len(next_glyph.pitch_options) == 1
                    and next_glyph.duration_beats is not None
                ):
                    carried_approaching = (
                        next_glyph.pitch_options[0],
                        next_glyph.duration_beats,
                    )
            segment_record["carried_approaching"] = (
                None
                if carried_approaching is None
                else {
                    "pitch": carried_approaching[0],
                    "duration_beats": carried_approaching[1],
                }
            )

            start_ns = time.monotonic_ns()
            local_actions: list[InputAction] = []
            for event in visible:
                local_actions.append(
                    InputAction(
                        lead_beats + event.onset_beats,
                        1,
                        sequence,
                        "DOWN",
                        event.pitch,
                        segment_number + 1,
                    )
                )
                sequence += 1
                local_actions.append(
                    InputAction(
                        lead_beats + event.onset_beats + event.duration_beats,
                        0,
                        sequence,
                        "UP",
                        event.pitch,
                        segment_number + 1,
                    )
                )
                sequence += 1

            local_actions.sort(
                key=lambda action: (action.beat, action.order, action.sequence)
            )
            segment_sequences: set[int] = set()
            for action in local_actions:
                deadline_ns = start_ns + round(action.beat * beat_ns)
                wait_until_ns(deadline_ns)
                sent_ns, pending = input_shell.send(
                    action.kind, action.pitch, action.sequence
                )
                segment_sequences.add(action.sequence)
                log["actions"].append(  # type: ignore[union-attr]
                    {
                        "sequence": action.sequence,
                        "segment": segment_number + 1,
                        "local_beat": action.beat,
                        "kind": action.kind,
                        "pitch": action.pitch,
                        "scheduled_ns": deadline_ns,
                        "sent_ns": sent_ns,
                        "send_drift_ms": (sent_ns - deadline_ns) / 1_000_000,
                        "device_queue_depth_after_send": pending,
                    }
                )
            segment_record["all_actions_acked"] = input_shell.wait_for(
                segment_sequences, timeout=3.0
            )
            for action in log["actions"]:  # type: ignore[union-attr]
                if action.get("segment") != segment_number + 1:
                    continue
                ack_ns = input_shell.ack_ns(int(action["sequence"]))
                action["device_ack_ns"] = ack_ns
                action["device_ack_drift_ms"] = (
                    None
                    if ack_ns is None
                    else (ack_ns - int(action["scheduled_ns"])) / 1_000_000
                )

            _, minimum_frame, _ = frames.latest()
            segment_number += 1
            if segment_number > args.maximum_segments:
                raise RuntimeError("generic controller exceeded its segment guard")

        log["completed"] = completed
        log["played_segments"] = segment_number
        log["duplicate_frames_skipped"] = duplicate_frames_skipped
    finally:
        release_sequences: set[int] = set()
        for index, pitch in enumerate(input_shell.pitches):
            release_sequence = sequence + index
            try:
                input_shell.send("UP", pitch, release_sequence)
                release_sequences.add(release_sequence)
            except Exception:
                break
        input_shell.wait_for(release_sequences, timeout=2.0)
        log["input_shell_stderr"] = input_shell.close()
        log["frame_stream"] = frames.stop()
        log_path = output_dir / "timing-log.json"
        log_path.write_text(
            json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {"log_path": str(log_path), **log}


def run_streaming_visible(args: argparse.Namespace) -> dict[str, object]:
    """Continuously discover future notes and schedule them on one beat clock."""

    adb = shutil.which(args.adb)
    if adb is None:
        raise FileNotFoundError(f"adb executable not found: {args.adb}")
    beat_ns = round(60_000_000_000 / args.bpm)
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    actions: list[dict[str, object]] = []
    log: dict[str, object] = {
        "mode": "streaming-visible-score",
        "serial": args.serial,
        "bpm": args.bpm,
        "quarter_ms": beat_ns / 1_000_000,
        "pixels_per_beat": args.pixels_per_beat,
        "observations": [],
        "scheduled_notes": [],
        "slot_conflicts": [],
        "actions": actions,
    }
    frames = FramePump(adb, args.serial)
    input_shell = PersistentInputShell(
        adb,
        args.serial,
        key_points=KEYBOARD_PROFILES[args.keyboard_profile],
    )
    scheduler = LiveActionScheduler(input_shell, actions)
    scheduled_slots: dict[tuple[int, int], tuple[str, float]] = {}
    completed = False
    origin_ns = 0
    round_number = 1
    last_checked_frame = -1
    last_launch_frame = -1
    observation_number = 0
    spellings = KEY_SIGNATURE_SPELLINGS.get(args.keyboard_profile, {})
    seen_active_since_launch = False

    def launch_duration(detected: tuple[DetectedNote, ...]) -> float:
        first = detected[0]
        if first.duration_beats is not None:
            return first.duration_beats
        if len(detected) > 1:
            onset_gap = (
                detected[1].x_min - first.x_min
            ) / args.pixels_per_beat
            candidates = (0.5, 1.0, 1.5, 2.0)
            return min(candidates, key=lambda value: abs(value - onset_gap))
        return args.initial_duration

    frames.start()
    scheduler.start()
    try:
        frames.wait_for_first_frame()

        # The launch glyph is static and partially covered.  It supplies pitch;
        # the duration fallback is retained as an explicit observable parameter.
        start_deadline = time.monotonic() + args.segment_timeout
        while time.monotonic() < start_deadline:
            png, frame_number, age_ms = frames.latest()
            if frame_number == last_checked_frame:
                time.sleep(0.01)
                continue
            last_checked_frame = frame_number
            if Image.open(io.BytesIO(png)).size != (1612, 720):
                continue
            try:
                detected = analyze_staff_png(png)
            except ValueError:
                continue
            if not detected or detected[0].x_min > 430:
                continue
            first = detected[0]
            first_pitch = spellings.get(
                first.pitch_options[-1], first.pitch_options[-1]
            )
            origin_ns = time.monotonic_ns() + 100_000_000
            scheduler.schedule_note(
                pitch=first_pitch,
                beat_slot=0,
                onset_ns=origin_ns,
                duration_beats=args.initial_duration,
                beat_ns=beat_ns,
            )
            scheduled_slots[(round_number, 0)] = (
                first_pitch,
                args.initial_duration,
            )
            initial_path = output_dir / "observation-001-launch.png"
            initial_path.write_bytes(png)
            log["initial"] = {
                "frame": frame_number,
                "frame_age_ms": age_ms,
                "checkpoint": str(initial_path),
                "pitch": first_pitch,
                "duration_beats": args.initial_duration,
                "detected": dataclasses.asdict(first),
            }
            observation_number = 1
            last_launch_frame = frame_number
            break
        if not origin_ns:
            raise TimeoutError("could not identify the static launch note")

        performance_deadline = time.monotonic() + args.performance_timeout
        while time.monotonic() < performance_deadline:
            if scheduler.error is not None:
                raise RuntimeError(f"input scheduler failed: {scheduler.error}")
            png, frame_number, age_ms = frames.latest()
            if frame_number == last_checked_frame:
                time.sleep(0.01)
                continue
            last_checked_frame = frame_number
            size = Image.open(io.BytesIO(png)).size
            if size != (1612, 720):
                completion_path = output_dir / "completion-screen.png"
                completion_path.write_bytes(png)
                log["completion_checkpoint"] = str(completion_path)
                log["completion_frame_size"] = list(size)
                completed = True
                break

            analyzed_ns = time.monotonic_ns()
            capture_ns = analyzed_ns - round(age_ms * 1_000_000)
            try:
                frame_image = np.asarray(
                    Image.open(io.BytesIO(png)).convert("RGB")
                )
                judgment_x = _judgment_line_x(frame_image)
                detected = analyze_staff_png(png)
            except ValueError:
                continue
            showing_prompt = frame_shows_exit_x(png)
            if not showing_prompt:
                seen_active_since_launch = True

            # A lesson contains multiple short performances.  Once the prior
            # action queue is empty, a new static glyph at the judgment line is
            # the next round's explicit launch prompt, not a continuation beat.
            if (
                detected
                and detected[0].x_min <= judgment_x + 3
                and frame_number != last_launch_frame
                and showing_prompt
                and seen_active_since_launch
                and scheduler.wait_until_idle(0.0)
            ):
                round_number += 1
                first = detected[0]
                first_pitch = spellings.get(
                    first.pitch_options[-1], first.pitch_options[-1]
                )
                first_duration = launch_duration(detected)
                origin_ns = time.monotonic_ns() + 100_000_000
                scheduler.schedule_note(
                    pitch=first_pitch,
                    beat_slot=0,
                    onset_ns=origin_ns,
                    duration_beats=first_duration,
                    beat_ns=beat_ns,
                )
                scheduled_slots[(round_number, 0)] = (
                    first_pitch,
                    first_duration,
                )
                last_launch_frame = frame_number
                seen_active_since_launch = False
                observation_number += 1
                checkpoint = (
                    output_dir
                    / f"observation-{observation_number:03d}-round-{round_number}-launch.png"
                )
                checkpoint.write_bytes(png)
                log["observations"].append(  # type: ignore[union-attr]
                    {
                        "observation": observation_number,
                        "round": round_number,
                        "kind": "launch",
                        "frame": frame_number,
                        "frame_age_ms": age_ms,
                        "checkpoint": str(checkpoint),
                        "pitch": first_pitch,
                        "duration_beats": first_duration,
                    }
                )
                continue

            new_notes: list[dict[str, object]] = []
            for glyph in detected:
                # Only schedule intact future glyphs.  The initial current note
                # was handled above; later notes are learned several beats early.
                if (
                    glyph.x_min <= judgment_x + 3
                    or glyph.x_min > args.scheduling_x_max
                    or glyph.duration_beats is None
                    or len(glyph.pitch_options) != 1
                ):
                    continue
                pitch = spellings.get(
                    glyph.pitch_options[0], glyph.pitch_options[0]
                )
                observed_beat = (
                    (capture_ns - origin_ns) / beat_ns
                    + (glyph.x_min - judgment_x) / args.pixels_per_beat
                )
                raw_beat = observed_beat - args.input_phase_beats
                duplicate = next(
                    (
                        key
                        for key, value in scheduled_slots.items()
                        if key[0] == round_number
                        and value == (pitch, glyph.duration_beats)
                        and abs(key[1] / 2 - raw_beat) < 0.4
                    ),
                    None,
                )
                if duplicate is not None:
                    continue
                beat_slot = round(raw_beat * 2)
                if beat_slot <= 0:
                    continue
                slot_key = (round_number, beat_slot)
                existing = scheduled_slots.get(slot_key)
                if existing is not None:
                    if existing != (pitch, glyph.duration_beats):
                        log["slot_conflicts"].append(  # type: ignore[union-attr]
                            {
                                "round": round_number,
                                "beat_slot": beat_slot,
                                "beat": beat_slot / 2,
                                "existing": list(existing),
                                "observed": [pitch, glyph.duration_beats],
                                "observed_beat": observed_beat,
                                "raw_beat": raw_beat,
                                "frame": frame_number,
                            }
                        )
                    continue

                onset_ns = origin_ns + round(beat_slot * beat_ns / 2)
                if onset_ns - analyzed_ns < 150_000_000:
                    log.setdefault("late_observations", []).append(  # type: ignore[union-attr]
                        {
                            "beat_slot": beat_slot,
                            "pitch": pitch,
                            "lead_ms": (onset_ns - analyzed_ns) / 1_000_000,
                            "frame": frame_number,
                        }
                    )
                    continue
                scheduler.schedule_note(
                    pitch=pitch,
                    beat_slot=beat_slot,
                    onset_ns=onset_ns,
                    duration_beats=glyph.duration_beats,
                    beat_ns=beat_ns,
                )
                scheduled_slots[slot_key] = (pitch, glyph.duration_beats)
                note_record = {
                    "round": round_number,
                    "beat_slot": beat_slot,
                    "beat": beat_slot / 2,
                    "pitch": pitch,
                    "duration_beats": glyph.duration_beats,
                    "observed_beat": observed_beat,
                    "raw_beat": raw_beat,
                    "x_min": glyph.x_min,
                    "judgment_x": judgment_x,
                    "frame": frame_number,
                    "lead_ms": (onset_ns - analyzed_ns) / 1_000_000,
                }
                log["scheduled_notes"].append(note_record)  # type: ignore[union-attr]
                new_notes.append(note_record)

            if new_notes:
                observation_number += 1
                checkpoint = output_dir / f"observation-{observation_number:03d}.png"
                checkpoint.write_bytes(png)
                log["observations"].append(  # type: ignore[union-attr]
                    {
                        "observation": observation_number,
                        "frame": frame_number,
                        "frame_age_ms": age_ms,
                        "checkpoint": str(checkpoint),
                        "new_notes": new_notes,
                    }
                )
        else:
            timeout_path = output_dir / "performance-timeout.png"
            png, _, _ = frames.latest()
            timeout_path.write_bytes(png)
            raise TimeoutError(f"performance did not finish; saved {timeout_path}")

        log["completed"] = completed
        log["rounds"] = round_number
        log["scheduled_note_count"] = len(scheduled_slots)
    finally:
        scheduler.stop(cancel_pending=not completed)
        score_sequences = scheduler.sent_sequences
        log["all_score_actions_acked"] = input_shell.wait_for(
            score_sequences, timeout=5.0
        )
        for action in actions:
            ack_ns = input_shell.ack_ns(int(action["sequence"]))
            action["device_ack_ns"] = ack_ns
            action["device_ack_drift_ms"] = (
                None
                if ack_ns is None
                else (ack_ns - int(action["scheduled_ns"])) / 1_000_000
            )

        release_sequences: set[int] = set()
        next_sequence = scheduler.next_sequence
        for index, pitch in enumerate(input_shell.pitches):
            release_sequence = next_sequence + index
            try:
                input_shell.send("UP", pitch, release_sequence)
                release_sequences.add(release_sequence)
            except Exception:
                break
        input_shell.wait_for(release_sequences, timeout=2.0)
        log["input_shell_stderr"] = input_shell.close()
        log["frame_stream"] = frames.stop()

        drifts = sorted(abs(float(action["send_drift_ms"])) for action in actions)
        if drifts:
            p95_index = min(len(drifts) - 1, int(len(drifts) * 0.95))
            log["absolute_send_drift_ms"] = {
                "median": drifts[len(drifts) // 2],
                "p95": drifts[p95_index],
                "max": drifts[-1],
            }
        log_path = output_dir / "timing-log.json"
        log_path.write_text(
            json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {"log_path": str(log_path), **log}


def run_visual_follow(args: argparse.Namespace) -> dict[str, object]:
    """Follow the judgment line directly, re-anchoring at every lesson prompt."""

    adb = shutil.which(args.adb)
    if adb is None:
        raise FileNotFoundError(f"adb executable not found: {args.adb}")
    events = parse_score_document(args.score_doc)
    score_notes = tuple(event for event in events if event.pitch is not None)
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    actions: list[dict[str, object]] = []
    log: dict[str, object] = {
        "mode": "visual-judgment-line-follow",
        "serial": args.serial,
        "pixels_per_beat": args.pixels_per_beat,
        "visual_pipeline_ms": args.visual_pipeline_ms,
        "visual_schedule_x": args.visual_schedule_x,
        "visual_default_quarter_ms": args.visual_default_quarter_ms,
        "rounds": [],
        "actions": actions,
    }
    frames = FramePump(adb, args.serial)
    input_shell = PersistentInputShell(
        adb,
        args.serial,
        key_points=KEYBOARD_PROFILES[args.keyboard_profile],
    )
    scheduler = LiveActionScheduler(input_shell, actions)
    scheduler.start()
    frames.start()
    hint = args.score_start_index
    round_number = 0
    last_frame = -1
    completion_since: float | None = None
    archived_frames: list[dict[str, object]] = []
    archived_frame_numbers: set[tuple[int, int]] = set()

    def archive_visual_frame(
        round_index: int,
        frame_number: int,
        png: bytes,
        age_ms: float,
    ) -> None:
        if not args.archive_frames:
            return
        frame_key = (round_index, frame_number)
        if frame_key in archived_frame_numbers:
            return
        archived_frame_numbers.add(frame_key)
        frame_dir = output_dir / "frames" / f"round-{round_index:02d}"
        frame_dir.mkdir(parents=True, exist_ok=True)
        frame_path = frame_dir / f"frame-{frame_number:04d}.png"
        frame_path.write_bytes(png)
        archived_frames.append(
            {
                "round": round_index,
                "frame": frame_number,
                "received_ns": time.monotonic_ns(),
                "age_ms": age_ms,
                "path": str(frame_path),
            }
        )

    def has_rest_after(note_index: int) -> bool:
        if note_index + 1 >= len(score_notes):
            return True
        note = score_notes[note_index]
        following = score_notes[note_index + 1]
        return following.start_beat > note.start_beat + note.duration_beats + 1e-9

    def release_advance_ns(note_index: int) -> int:
        if note_index + 1 >= len(score_notes):
            return 0
        note = score_notes[note_index]
        following = score_notes[note_index + 1]
        contiguous = abs(
            following.start_beat - note.start_beat - note.duration_beats
        ) < 1e-9
        if contiguous:
            return round(args.release_advance_ms * 1_000_000)
        return 0

    def queue_note(
        note_index: int,
        onset_ns: int,
        quarter_seconds: float,
        record: dict[str, object],
    ) -> None:
        note = score_notes[note_index]
        assert note.pitch is not None
        beat_slot = note_index * 2
        down_sequence = scheduler.schedule_action(
            kind="DOWN",
            pitch=note.pitch,
            deadline_ns=onset_ns,
            beat_slot=beat_slot,
            order=1,
        )
        duration_ns = round(note.duration_beats * quarter_seconds * 1_000_000_000)
        up_ns = onset_ns + duration_ns - release_advance_ns(note_index)
        up_sequence = scheduler.schedule_action(
            kind="UP",
            pitch=note.pitch,
            deadline_ns=up_ns,
            beat_slot=beat_slot,
            order=0,
        )
        record.update(
            {
                "score_index": note_index,
                "pitch": note.pitch,
                "duration_beats": note.duration_beats,
                "quarter_ms": quarter_seconds * 1000,
                "onset_ns": onset_ns,
                "release_ns": up_ns,
                "down_sequence": down_sequence,
                "up_sequence": up_sequence,
                "rest_after": has_rest_after(note_index),
            }
        )

    try:
        frames.wait_for_first_frame()
        performance_deadline = time.monotonic() + args.performance_timeout
        while time.monotonic() < performance_deadline:
            png, frame_number, age_ms = frames.latest()
            if frame_number == last_frame:
                time.sleep(0.01)
                continue
            last_frame = frame_number
            if Image.open(io.BytesIO(png)).size != (1612, 720):
                completion_path = output_dir / "completion-screen.png"
                completion_path.write_bytes(png)
                log["completion_checkpoint"] = str(completion_path)
                break

            detected = analyze_staff_png(png)
            showing_prompt = frame_shows_exit_x(png)
            if not showing_prompt or not detected:
                if not detected:
                    completion_since = completion_since or time.monotonic()
                    if time.monotonic() - completion_since >= args.result_wait:
                        completion_path = output_dir / "completion-screen.png"
                        completion_path.write_bytes(png)
                        log["completion_checkpoint"] = str(completion_path)
                        break
                else:
                    completion_since = None
                continue

            completion_since = None
            frames.stop()
            prompt_pitch = read_prompt_pitch(adb, args.serial)
            frames = FramePump(adb, args.serial)
            frames.start()
            frames.wait_for_first_frame()
            last_frame = -1
            if prompt_pitch is None:
                time.sleep(0.02)
                continue
            located = locate_prompt_window(
                detected,
                score_notes,
                prompt_pitch=prompt_pitch,
                search_first=max(0, hint - 10),
                search_last=min(len(score_notes) - 1, hint + 24),
                hint=hint,
            )
            if located is None:
                time.sleep(0.02)
                continue
            start_index, matched = located
            first = score_notes[start_index]
            assert first.pitch is not None
            round_number += 1
            prompt_path = output_dir / f"round-{round_number:02d}-prompt.png"
            prompt_path.write_bytes(png)
            round_record: dict[str, object] = {
                "round": round_number,
                "start_index": start_index,
                "matched_prompt_glyphs": matched,
                "prompt_pitch": first.pitch,
                "accessibility_prompt_pitch": prompt_pitch,
                "prompt_checkpoint": str(prompt_path),
                "notes": [],
                "velocity_samples": [],
            }
            log["rounds"].append(round_record)  # type: ignore[union-attr]

            launch_ns = time.monotonic_ns() + round(args.pre_roll * 1_000_000_000)
            launch_record: dict[str, object] = {"source": "prompt"}
            queue_note(
                start_index,
                launch_ns,
                args.visual_default_quarter_ms / 1000,
                launch_record,
            )
            round_record["notes"].append(launch_record)  # type: ignore[union-attr]
            expected = start_index + 1
            highest_scheduled = start_index
            seen_active = False
            previous_positions: dict[int, tuple[int, int]] = {}
            default_quarter_seconds = args.visual_default_quarter_ms / 1000
            velocity_px_s = args.pixels_per_beat / default_quarter_seconds
            phase_anchor_index = start_index
            phase_anchor_ns = launch_ns
            round_deadline = time.monotonic() + args.segment_timeout
            round_last_frame = frame_number

            while time.monotonic() < round_deadline:
                if scheduler.error is not None:
                    raise RuntimeError(f"input scheduler failed: {scheduler.error}")
                current_png, current_frame, current_age_ms = frames.latest()
                if current_frame == round_last_frame:
                    time.sleep(0.008)
                    continue
                round_last_frame = current_frame
                now_ns = time.monotonic_ns()
                archive_visual_frame(
                    round_number,
                    current_frame,
                    current_png,
                    current_age_ms,
                )
                if Image.open(io.BytesIO(current_png)).size != (1612, 720):
                    completion_path = output_dir / "completion-screen.png"
                    completion_path.write_bytes(current_png)
                    log["completion_checkpoint"] = str(completion_path)
                    round_record["highest_scheduled_index"] = highest_scheduled
                    completion_since = time.monotonic()
                    break
                current_prompt = frame_shows_exit_x(current_png)
                if not current_prompt:
                    seen_active = True
                elif seen_active:
                    round_record["next_prompt_frame"] = current_frame
                    round_record["highest_scheduled_index"] = highest_scheduled
                    hint = max(hint, highest_scheduled + 1)
                    break

                current_detected = analyze_staff_png(current_png)
                if not current_detected:
                    continue
                current_located = locate_score_window(
                    current_detected,
                    score_notes,
                    search_first=max(start_index, expected - 3),
                    search_last=min(len(score_notes) - 1, expected + 18),
                    hint=expected,
                )
                if current_located is None:
                    continue
                visible_start, visible_matched = current_located
                capture_ns = now_ns - round(current_age_ms * 1_000_000)
                positions = {
                    visible_start + offset: glyph.x_min
                    for offset, glyph in enumerate(current_detected[:visible_matched])
                }
                speed_samples = []
                for score_index, x_min in positions.items():
                    previous = previous_positions.get(score_index)
                    if previous is None:
                        continue
                    previous_ns, previous_x = previous
                    elapsed = (capture_ns - previous_ns) / 1_000_000_000
                    if elapsed <= 0:
                        continue
                    speed = (previous_x - x_min) / elapsed
                    if 60 <= speed <= 600:
                        speed_samples.append(speed)
                previous_positions = {
                    score_index: (capture_ns, x_min)
                    for score_index, x_min in positions.items()
                }
                if speed_samples:
                    sample = float(np.median(np.asarray(speed_samples)))
                    velocity_px_s = velocity_px_s * 0.8 + sample * 0.2
                    round_record["velocity_samples"].append(  # type: ignore[union-attr]
                        {
                            "frame": current_frame,
                            "sample_px_s": sample,
                            "filtered_px_s": velocity_px_s,
                        }
                    )

                quarter_seconds = min(
                    1.2,
                    max(0.35, args.pixels_per_beat / velocity_px_s),
                )
                while expected < len(score_notes):
                    x_min = positions.get(expected)
                    if x_min is None or x_min > args.visual_schedule_x:
                        break
                    lead_seconds = (
                        (x_min - 360) / velocity_px_s
                        - args.visual_pipeline_ms / 1000
                    )
                    if lead_seconds > args.visual_max_lead:
                        break
                    visual_onset_ns = round(
                        now_ns + max(0.025, lead_seconds) * 1_000_000_000
                    )
                    previous_index = expected - 1
                    if has_rest_after(previous_index):
                        # A rest (the long opening silence in this score) also
                        # contains Duolingo's launch animation.  Re-anchor once
                        # on the first moving note after it.
                        onset_ns = visual_onset_ns
                        phase_anchor_index = expected
                        phase_anchor_ns = onset_ns
                    else:
                        anchor_gap_beats = (
                            score_notes[expected].start_beat
                            - score_notes[phase_anchor_index].start_beat
                        )
                        clock_onset_ns = phase_anchor_ns + round(
                            anchor_gap_beats
                            * default_quarter_seconds
                            * 1_000_000_000
                        )
                        correction_ns = round(
                            args.visual_phase_correction_ms * 1_000_000
                        )
                        onset_ns = clock_onset_ns + max(
                            -correction_ns,
                            min(correction_ns, visual_onset_ns - clock_onset_ns),
                        )
                    note_record = {
                        "source": "visual",
                        "frame": current_frame,
                        "frame_age_ms": current_age_ms,
                        "x_min": x_min,
                        "velocity_px_s": velocity_px_s,
                        "lead_ms": max(25.0, lead_seconds * 1000),
                    }
                    queue_note(
                        expected,
                        onset_ns,
                        default_quarter_seconds,
                        note_record,
                    )
                    round_record["notes"].append(note_record)  # type: ignore[union-attr]
                    highest_scheduled = expected
                    expected += 1
            else:
                raise TimeoutError(
                    f"visual round {round_number} did not return to a prompt"
                )
            if completion_since is not None:
                break
        else:
            raise TimeoutError("visual performance did not reach a result screen")
    finally:
        scheduler.stop(cancel_pending=True)
        release_sequences: set[int] = set()
        next_sequence = scheduler.next_sequence
        for index, pitch in enumerate(input_shell.pitches):
            sequence = next_sequence + index
            try:
                input_shell.send("UP", pitch, sequence)
                release_sequences.add(sequence)
            except Exception:
                break
        input_shell.wait_for(release_sequences, timeout=2.0)
        score_sequences = scheduler.sent_sequences
        log["all_score_actions_acked"] = input_shell.wait_for(
            score_sequences, timeout=4.0
        )
        for action in actions:
            ack_ns = input_shell.ack_ns(int(action["sequence"]))
            action["device_ack_ns"] = ack_ns
        log["input_shell_stderr"] = input_shell.close()
        log["frame_stream"] = frames.stop()
        if args.archive_frames:
            log["archived_frames"] = archived_frames
        log_path = output_dir / "timing-log.json"
        log_path.write_text(
            json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {"log_path": str(log_path), **log}


def run_frozen_plan(args: argparse.Namespace) -> dict[str, object]:
    """Play an offline-verified plan on one device-ACK-anchored clock."""

    adb = shutil.which(args.adb)
    if adb is None:
        raise FileNotFoundError(f"adb executable not found: {args.adb}")
    assert args.frozen_plan is not None
    raw_events = json.loads(
        args.frozen_plan.read_text(encoding="utf-8")
    ).get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise ValueError("frozen plan contains no events")

    key_points = KEYBOARD_PROFILES[args.keyboard_profile]
    events: list[tuple[float, str, float]] = []
    for index, raw in enumerate(raw_events):
        event = (
            float(raw["start_beat"]),
            str(raw["pitch"]),
            float(raw["duration_beats"]),
        )
        if event[1] not in key_points or event[2] <= 0:
            raise ValueError(f"invalid frozen event at index {index}: {raw!r}")
        if events and event[0] < events[-1][0]:
            raise ValueError("frozen events are not ordered")
        events.append(event)
    if events[0][0] != 0:
        raise ValueError("frozen plan must begin at beat zero")

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    beat_ns = round(60_000_000_000 / args.bpm)
    advance_ns = round(args.input_advance_ms * 1_000_000)
    score_start_delay_ns = round(args.score_start_delay_ms * 1_000_000)
    input_shell = PersistentInputShell(adb, args.serial, key_points=key_points)
    log: dict[str, object] = {
        "mode": "frozen-event-plan-device-ack-clock",
        "serial": args.serial,
        "plan": str(args.frozen_plan),
        "keyboard_profile": args.keyboard_profile,
        "bpm": args.bpm,
        "quarter_ms": beat_ns / 1_000_000,
        "input_advance_ms": args.input_advance_ms,
        "score_start_delay_ms": args.score_start_delay_ms,
        "event_count": len(events),
        "actions": [],
    }
    sequence = 0
    score_sequences: set[int] = set()

    try:
        launch_deadline_ns = time.monotonic_ns() + round(
            args.pre_roll * 1_000_000_000
        )
        wait_until_ns(launch_deadline_ns)
        sent_ns, pending = input_shell.send("DOWN", events[0][1], sequence)
        score_sequences.add(sequence)
        input_shell.wait_for({sequence}, timeout=2.0)
        origin_ack_ns = input_shell.ack_ns(sequence)
        if origin_ack_ns is None:
            raise TimeoutError("launch note was not acknowledged by the device")
        log["origin_device_ack_ns"] = origin_ack_ns
        log["actions"].append(  # type: ignore[union-attr]
            {
                "sequence": sequence,
                "event": 0,
                "kind": "DOWN",
                "pitch": events[0][1],
                "beat": 0.0,
                "scheduled_ns": launch_deadline_ns,
                "sent_ns": sent_ns,
                "device_ack_ns": origin_ack_ns,
                "device_queue_depth_after_send": pending,
            }
        )
        sequence += 1

        queue: list[tuple[int, int, int, str, str, float]] = []
        for event_index, (start_beat, pitch, duration_beats) in enumerate(events):
            phase_delay_ns = score_start_delay_ns if event_index else 0
            if event_index:
                deadline = (
                    origin_ack_ns
                    + phase_delay_ns
                    + round(start_beat * beat_ns)
                    - advance_ns
                )
                queue.append((deadline, 1, event_index, "DOWN", pitch, start_beat))
            release_beat = start_beat + duration_beats
            deadline = (
                origin_ack_ns
                + phase_delay_ns
                + round(release_beat * beat_ns)
                - advance_ns
            )
            queue.append((deadline, 0, event_index, "UP", pitch, release_beat))
        queue.sort(key=lambda item: (item[0], item[1], item[2]))

        for deadline_ns, _, event_index, kind, pitch, beat in queue:
            wait_until_ns(deadline_ns)
            sent_ns, pending = input_shell.send(kind, pitch, sequence)
            score_sequences.add(sequence)
            log["actions"].append(  # type: ignore[union-attr]
                {
                    "sequence": sequence,
                    "event": event_index,
                    "kind": kind,
                    "pitch": pitch,
                    "beat": beat,
                    "scheduled_ns": deadline_ns,
                    "sent_ns": sent_ns,
                    "send_drift_ms": (sent_ns - deadline_ns) / 1_000_000,
                    "target_device_ack_ns": deadline_ns + advance_ns,
                    "device_queue_depth_after_send": pending,
                }
            )
            sequence += 1
        log["all_score_actions_acked"] = input_shell.wait_for(
            score_sequences, timeout=5.0
        )
        time.sleep(args.result_wait)
        result_path = output_dir / "result.png"
        capture = subprocess.run(
            [adb, "-s", args.serial, "exec-out", "screencap", "-p"],
            check=True,
            stdout=subprocess.PIPE,
        )
        result_path.write_bytes(capture.stdout)
        log["result_checkpoint"] = str(result_path)
    finally:
        for action in log["actions"]:  # type: ignore[union-attr]
            ack_ns = input_shell.ack_ns(int(action["sequence"]))
            action["device_ack_ns"] = ack_ns
            target_ack_ns = action.get("target_device_ack_ns")
            action["device_ack_drift_ms"] = (
                None
                if ack_ns is None or target_ack_ns is None
                else (ack_ns - int(target_ack_ns)) / 1_000_000
            )
        release_sequences: set[int] = set()
        for index, pitch in enumerate(input_shell.pitches):
            release_sequence = sequence + index
            try:
                input_shell.send("UP", pitch, release_sequence)
                release_sequences.add(release_sequence)
            except Exception:
                break
        input_shell.wait_for(release_sequences, timeout=2.0)
        log["input_shell_stderr"] = input_shell.close()
        log_path = output_dir / "timing-log.json"
        log_path.write_text(
            json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {"log_path": str(log_path), **log}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, help="ADB device serial")
    parser.add_argument("--bpm", type=float, default=100.0)
    parser.add_argument("--pre-roll", type=float, default=0.35)
    parser.add_argument("--adb", default="adb")
    parser.add_argument(
        "--keyboard-profile",
        choices=tuple(KEYBOARD_PROFILES),
        default="greensleeves-c4",
        help="map score pitches to the keyboard layout shown by this lesson",
    )
    parser.add_argument("--score-doc", type=Path, default=DEFAULT_SCORE_DOC)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--segmented",
        action="store_true",
        help="re-read and re-anchor each visible score segment",
    )
    parser.add_argument(
        "--generic-visible",
        action="store_true",
        help="play an unknown score directly from each visible staff window",
    )
    parser.add_argument(
        "--streaming-visible",
        action="store_true",
        help="continuously schedule unknown future notes on one absolute clock",
    )
    parser.add_argument(
        "--visual-follow",
        action="store_true",
        help="follow note motion to the judgment line and re-anchor every round",
    )
    parser.add_argument(
        "--frozen-plan",
        type=Path,
        help="play an offline-verified JSON event plan on one absolute clock",
    )
    parser.add_argument(
        "--known-tail",
        action="store_true",
        help="play from --score-start-index to the score end on one clock",
    )
    parser.add_argument(
        "--known-note-count",
        type=int,
        default=0,
        help="limit --known-tail to this many notes; zero plays to score end",
    )
    parser.add_argument(
        "--stop-at-next-prompt",
        action="store_true",
        help="stop --known-tail when an active round returns to the exit-X prompt",
    )
    parser.add_argument(
        "--after-first-gap-beats",
        type=float,
        default=0.0,
        help="insert extra silent beats after the first --known-tail note",
    )
    parser.add_argument(
        "--release-advance-ms",
        type=float,
        default=0.0,
        help="release contiguous notes early so the next device DOWN lands on beat",
    )
    parser.add_argument(
        "--same-pitch-extra-gap-ms",
        type=float,
        default=0.0,
        help="add articulation time before a contiguous repeat of the same key",
    )
    parser.add_argument(
        "--extra-gap-after-index",
        type=int,
        default=-1,
        help="insert a score-clock gap after this absolute note index",
    )
    parser.add_argument(
        "--extra-gap-beats",
        type=float,
        default=0.0,
        help="number of silent beats inserted after --extra-gap-after-index",
    )
    parser.add_argument(
        "--prompt-key-x-offset",
        type=int,
        default=0,
        help="horizontal offset for the first note while Duolingo shows its prompt layout",
    )
    parser.add_argument(
        "--archive-frames",
        action="store_true",
        help="save every low-latency PNG with its monotonic capture timestamp",
    )
    parser.add_argument("--segment-notes", type=int, default=5)
    parser.add_argument("--segment-timeout", type=float, default=15.0)
    parser.add_argument("--score-start-index", type=int, default=0)
    parser.add_argument(
        "--global-reanchor",
        action="store_true",
        help="allow lesson rounds to re-anchor anywhere in the known score",
    )
    parser.add_argument("--initial-duration", type=float, default=1.0)
    parser.add_argument("--pixels-per-beat", type=float, default=144.0)
    parser.add_argument("--maximum-segments", type=int, default=60)
    parser.add_argument("--performance-timeout", type=float, default=180.0)
    parser.add_argument("--result-wait", type=float, default=3.0)
    parser.add_argument(
        "--scheduling-x-max",
        type=int,
        default=1150,
        help="ignore right-edge entrance animation until a glyph reaches this x",
    )
    parser.add_argument(
        "--input-phase-beats",
        type=float,
        default=0.2,
        help="subtract stable device-input latency before beat-grid quantization",
    )
    parser.add_argument(
        "--input-advance-ms",
        type=float,
        default=20.5,
        help="send frozen-plan actions early by the measured device ACK latency",
    )
    parser.add_argument(
        "--score-start-delay-ms",
        type=float,
        default=0.0,
        help="delay frozen-plan events after the launch note while the score starts scrolling",
    )
    parser.add_argument("--visual-pipeline-ms", type=float, default=240.0)
    parser.add_argument("--visual-schedule-x", type=int, default=620)
    parser.add_argument("--visual-max-lead", type=float, default=1.5)
    parser.add_argument("--visual-default-quarter-ms", type=float, default=600.0)
    parser.add_argument(
        "--visual-phase-correction-ms",
        type=float,
        default=30.0,
        help="bound each non-cumulative visual phase correction around the score clock",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    if arguments.frozen_plan is not None:
        result = run_frozen_plan(arguments)
    elif arguments.known_tail:
        result = run_known_tail(arguments)
    elif arguments.visual_follow:
        result = run_visual_follow(arguments)
    elif arguments.streaming_visible:
        result = run_streaming_visible(arguments)
    elif arguments.generic_visible:
        result = run_generic_visible(arguments)
    elif arguments.segmented:
        result = run_segmented(arguments)
    else:
        result = run(arguments)
    print(json.dumps(result, ensure_ascii=False, indent=2))
