#!/usr/bin/env python3
"""Objective full-score reader for Duolingo Music screen.

Locates the 5 staff lines, detects all noteheads at and to the right of the
judgment line, measures their precise geometric centers, determines pitch,
key-signature accidentals, note durations (including augmentation dots), and outputs
a structured ledger with pitch, physical key mapping, and relative timing (hold & delta).
"""

from __future__ import annotations

import argparse
import uuid
from dataclasses import dataclass, field
from datetime import datetime
import io
import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, TextIO

import numpy as np
from PIL import Image, ImageDraw
import scipy.ndimage
import scipy.signal

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from duolingo_keyboard_detect import (  # noqa: E402
    KeyboardLayout,
    KeyboardNotDetectedError,
    detect_keyboard,
)
from duolingo_pitch import apply_key_signature  # noqa: E402


# Key targets are no longer hard-coded.  Every lesson re-anchors the pitches on
# the same physical grid, so a table measured on one lesson silently taps the
# wrong key on the next; see duolingo_keyboard_detect.detect_keyboard.

DEFAULT_HUMAN_READABLE_OUTPUT = Path("duolingo-screen-notes.txt")


class ScoreNotVisibleError(RuntimeError):
    """Raised when the current frame is not a Duolingo staff screen."""


@dataclass(frozen=True)
class ScreenAnalysisContext:
    """Frame-wide data shared by note and rest recognition."""

    image: Image.Image
    arr: np.ndarray
    luminance: np.ndarray
    staff_lines: tuple[int, int, int, int, int]
    judgment_line_x: int
    # Detection costs ~40ms, and capture loops build a context for every frame
    # while only the note recognizer ever needs a key target, so resolve it on
    # first use instead of per frame.
    _keyboard_cache: list = field(default_factory=list, repr=False, compare=False)

    @property
    def keyboard(self) -> KeyboardLayout | None:
        if not self._keyboard_cache:
            self._keyboard_cache.append(detect_frame_keyboard(self.arr))
        return self._keyboard_cache[0]


def build_analysis_context(img: Image.Image) -> ScreenAnalysisContext:
    """Compute invariant frame geometry once for all recognizers."""
    image = img.convert("RGB")
    arr = np.asarray(image)
    return ScreenAnalysisContext(
        image=image,
        arr=arr,
        luminance=arr.mean(axis=2),
        staff_lines=find_staff_lines(arr),
        judgment_line_x=locate_judgment_line(arr),
    )


def detect_frame_keyboard(arr: np.ndarray) -> KeyboardLayout | None:
    """Read this frame's keyboard, tolerating frames that do not show one."""
    try:
        return detect_keyboard(arr)
    except KeyboardNotDetectedError:
        return None


def ensure_analysis_context(
    source: Image.Image | ScreenAnalysisContext,
) -> ScreenAnalysisContext:
    if isinstance(source, ScreenAnalysisContext):
        return source
    return build_analysis_context(source)


def resolve_adb_serial(serial: str | None = None, adb: str = "adb") -> str | None:
    """Resolve the preferred OPPO serial while excluding the projector."""
    if not serial:
        out = subprocess.run(
            [adb, "devices"], stdout=subprocess.PIPE, text=True, check=True
        ).stdout
        devices = [line.split()[0] for line in out.strip().splitlines()[1:] if "\tdevice" in line]
        if len(devices) == 1:
            serial = devices[0]
        elif len(devices) > 1:
            # Prefer OPPO port or tls connect if available
            oppo_devs = [d for d in devices if d != "192.168.10.100:5555"]
            serial = oppo_devs[0] if oppo_devs else devices[0]
    return serial


def require_adb_device(serial: str, adb: str = "adb") -> None:
    """Fail clearly unless the exact requested ADB device is online."""
    result = subprocess.run(
        [adb, "devices"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    device_states = {}
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2:
            device_states[fields[0]] = fields[1]

    state = device_states.get(serial)
    if state != "device":
        state_description = state if state is not None else "missing"
        raise RuntimeError(
            f"ADB device {serial!r} is not connected "
            f"(state: {state_description}); reconnect that device before "
            "starting the screen reader"
        )


def capture_adb_screenshot(serial: str | None = None) -> Image.Image:
    serial = resolve_adb_serial(serial)

    cmd = ["adb"]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(["exec-out", "screencap", "-p"])
    raw = subprocess.run(cmd, stdout=subprocess.PIPE, check=True).stdout
    return Image.open(io.BytesIO(raw)).convert("RGB")


class H264FramePump:
    """Continuously decode the OPPO hardware H.264 stream and retain one frame."""

    def __init__(
        self,
        adb: str,
        serial: str,
        *,
        ffmpeg: str = "ffmpeg",
        width: int = 1612,
        height: int = 720,
        bitrate: int = 12_000_000,
        encoder_fps: int = 60,
        output_fps: int = 60,
        warmup_frames: int = 60,
        archive_path: Path | None = None,
    ) -> None:
        self._adb = adb
        self._serial = serial
        self._ffmpeg = ffmpeg
        self._width = width
        self._height = height
        self._bitrate = bitrate
        self._encoder_fps = encoder_fps
        self._output_fps = output_fps
        self._warmup_frames = warmup_frames
        self._archive_path = archive_path
        self._remote_pts_path = (
            f"/data/local/tmp/codex-screen-encoder-{uuid.uuid4().hex}.pts"
            if archive_path is not None else "/dev/null"
        )
        self._archive_stream = None
        self._archive_thread: threading.Thread | None = None
        self._frame_size = width * height * 3
        self._encoder: subprocess.Popen[bytes] | None = None
        self._decoder: subprocess.Popen[bytes] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_threads: list[threading.Thread] = []
        self._condition = threading.Condition()
        self._latest: bytes | None = None
        self._sequence = 0
        self._latest_arrival_ns = 0
        self._stable_intervals = 0
        self._error: str | None = None
        self._stopping = False
        self._stderr_tail: list[str] = []

    @property
    def sequence(self) -> int:
        with self._condition:
            return self._sequence

    def start(self, timeout: float = 4.0) -> None:
        require_adb_device(self._serial, self._adb)
        remote = (
            "CLASSPATH=/data/local/tmp/codex-screen-encoder.jar "
            "app_process /system/bin CodexScreenEncoder "
            f"{self._width} {self._height} {self._bitrate} "
            f"{self._encoder_fps} 86400 0 {self._remote_pts_path}"
        )
        self._encoder = subprocess.Popen(
            [self._adb, "-s", self._serial, "exec-out", "sh", "-c", remote],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert self._encoder.stdout is not None
        if self._archive_path is not None:
            self._archive_stream = self._archive_path.open("wb")
        self._decoder = subprocess.Popen(
            [
                self._ffmpeg,
                "-v",
                "error",
                "-flags",
                "low_delay",
                "-f",
                "h264",
                "-i",
                "pipe:0",
                "-vf",
                f"fps={self._output_fps}",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ],
            stdin=subprocess.PIPE if self._archive_path is not None else self._encoder.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if self._archive_path is not None:
            self._archive_thread = threading.Thread(target=self._archive_h264, daemon=True)
            self._archive_thread.start()
        else:
            self._encoder.stdout.close()
        for name, process in (("encoder", self._encoder), ("decoder", self._decoder)):
            assert process.stderr is not None
            thread = threading.Thread(
                target=self._drain_stderr,
                args=(name, process.stderr),
                daemon=True,
            )
            thread.start()
            self._stderr_threads.append(thread)
        self._reader_thread = threading.Thread(target=self._read_frames, daemon=True)
        self._reader_thread.start()
        self._wait_until_ready(timeout)

    def _archive_h264(self) -> None:
        """Copy the one encoded stream to disk and to the live decoder."""
        assert self._encoder is not None and self._encoder.stdout is not None
        assert self._decoder is not None and self._decoder.stdin is not None
        assert self._archive_stream is not None
        try:
            while block := self._encoder.stdout.read1(64 * 1024):
                self._archive_stream.write(block)
                self._decoder.stdin.write(block)
        except (BrokenPipeError, OSError) as exc:
            if not self._stopping:
                with self._condition:
                    self._error = f"H.264 archive pipe failed: {exc}"
                    self._condition.notify_all()
        finally:
            self._archive_stream.close()
            try:
                self._decoder.stdin.close()
            except OSError:
                pass

    def _wait_until_ready(self, timeout: float) -> None:
        """Wait until startup backlog is drained and output is real-time."""
        started = time.monotonic()
        deadline = started + timeout
        with self._condition:
            while (
                self._sequence < self._warmup_frames
                or self._stable_intervals < 3
            ):
                if self._error is not None:
                    raise RuntimeError(self._error)
                now = time.monotonic()
                # ffmpeg may deliver fresh frames in short bursts, making the
                # interval counter stay at zero despite a live 10-fps stream.
                if (self._sequence >= self._warmup_frames
                        and now - started >= max(2.0, self._warmup_frames / self._output_fps)
                        and self._latest_arrival_ns
                        and time.monotonic_ns() - self._latest_arrival_ns < 250_000_000):
                    return
                remaining = deadline - now
                if remaining <= 0:
                    raise TimeoutError("H.264 stream did not reach real-time cadence")
                self._condition.wait(remaining)

    def _drain_stderr(self, name: str, stream) -> None:
        for raw_line in iter(stream.readline, b""):
            line = raw_line.decode("utf-8", "replace").strip()
            if not line:
                continue
            with self._condition:
                self._stderr_tail.append(f"{name}: {line}")
                self._stderr_tail = self._stderr_tail[-20:]

    def _read_frames(self) -> None:
        assert self._decoder is not None and self._decoder.stdout is not None
        try:
            while True:
                frame = bytearray()
                while len(frame) < self._frame_size:
                    block = self._decoder.stdout.read(self._frame_size - len(frame))
                    if not block:
                        raise EOFError("H.264 decoder stream ended")
                    frame.extend(block)
                arrival_ns = time.monotonic_ns()
                with self._condition:
                    if self._latest_arrival_ns:
                        interval_ns = arrival_ns - self._latest_arrival_ns
                        # Decimated output can arrive in short batches even
                        # after the source backlog is drained. Do not demand
                        # a full fraction of its nominal 15-fps period here;
                        # the original 60-fps cadence remains a useful floor
                        # for distinguishing a decoder flush from live frames.
                        minimum_live_interval_ns = int(
                            0.45 * 1_000_000_000 / max(self._output_fps, 60)
                        )
                        self._stable_intervals = (
                            self._stable_intervals + 1
                            if interval_ns >= minimum_live_interval_ns
                            else 0
                        )
                    self._latest_arrival_ns = arrival_ns
                    self._latest = bytes(frame)
                    self._sequence += 1
                    self._condition.notify_all()
        except Exception as exc:
            with self._condition:
                if not self._stopping:
                    details = "; ".join(self._stderr_tail[-3:])
                    self._error = f"{exc}{': ' + details if details else ''}"
                self._condition.notify_all()

    def wait_for_frame(
        self,
        *,
        after_sequence: int,
        timeout: float,
    ) -> Image.Image:
        image, _, _ = self.wait_for_timed_frame(
            after_sequence=after_sequence, timeout=timeout,
        )
        return image

    def wait_for_timed_frame(
        self,
        *,
        after_sequence: int,
        timeout: float,
    ) -> tuple[Image.Image, int, int]:
        """Return one frame with its decoder-arrival time, not processing time."""
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._latest is None or self._sequence <= after_sequence:
                if self._error is not None:
                    raise RuntimeError(self._error)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("H.264 stream produced no fresh frame")
                self._condition.wait(remaining)
            frame = self._latest
            sequence = self._sequence
            arrival_ns = self._latest_arrival_ns
        assert frame is not None
        return Image.frombytes("RGB", (self._width, self._height), frame), sequence, arrival_ns

    def stop(self) -> None:
        with self._condition:
            self._stopping = True
            self._condition.notify_all()
        # With archiving enabled, drain the encoder pipe into both sinks before
        # closing the decoder; otherwise its broken pipe truncates the archive.
        if self._encoder is not None and self._encoder.poll() is None:
            self._encoder.terminate()
        if self._encoder is not None:
            try:
                self._encoder.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._encoder.kill()
                self._encoder.wait()
        if self._archive_thread is not None:
            self._archive_thread.join(timeout=2.0)
        for process in (self._decoder,):
            if process is not None and process.poll() is None:
                process.terminate()
        for process in (self._decoder,):
            if process is None:
                continue
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)
        for thread in self._stderr_threads:
            thread.join(timeout=1.0)
        for process in (self._decoder, self._encoder):
            if process is None:
                continue
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
        if self._archive_path is not None:
            result = subprocess.run(
                [self._adb, "-s", self._serial, "exec-out", "cat", self._remote_pts_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            if result.returncode != 0 or not result.stdout:
                raise RuntimeError("could not retrieve H.264 frame PTS from device")
            self._archive_path.with_suffix(".pts").write_bytes(result.stdout)


def find_staff_lines(arr: np.ndarray) -> tuple[int, int, int, int, int]:
    """Detect the y-coordinates of the 5 treble staff lines."""
    h, w, _ = arr.shape
    col_profile = arr[100:350, w // 3 : 2 * w // 3, :].mean(axis=(1, 2))
    peaks, _ = scipy.signal.find_peaks(255 - col_profile, height=15, distance=20)
    lines = sorted([int(100 + p) for p in peaks])
    if len(lines) == 5:
        return tuple(lines)

    for x_col in range(150, w - 150, 50):
        c = arr[100:350, x_col - 10 : x_col + 10, :].mean(axis=(1, 2))
        pks, _ = scipy.signal.find_peaks(255 - c, height=12, distance=20)
        if len(pks) == 5:
            return tuple(sorted([int(100 + p) for p in pks]))

def locate_judgment_line(arr: np.ndarray) -> int:
    """Locate the x-coordinate of the vertical judgment line.

    The mascot changes color between characters, so detect the tall translucent
    neutral-gray band itself.  It is the only 18px-wide feature that remains
    continuously light gray through most of the score height.
    """
    x0, x1 = 150, min(arr.shape[1], 650)
    band = arr[105:365, x0:x1]
    neutral_gray = (
        (band.max(axis=2) - band.min(axis=2) < 4)
        & (band.mean(axis=2) >= 225)
        & (band.mean(axis=2) <= 252)
    )
    continuity = neutral_gray.sum(axis=0)
    # A notehead or stem can cross the translucent line and split its per-pixel
    # continuity into several narrow islands. Integrate across the line's
    # physical width before choosing a location instead of requiring five
    # adjacent columns to pass one threshold.
    line_width = 18
    window_strength = np.convolve(
        continuity, np.ones(line_width, dtype=np.float64), mode="valid",
    )
    strongest = int(np.argmax(window_strength))
    if window_strength[strongest] >= line_width * 80:
        return x0 + strongest + line_width // 2

    # Last-resort fallback for unfamiliar themes.
    sub = arr[350:480, 200:500]
    col_darkness = 255 - sub.mean(axis=(0, 2))
    return 200 + int(np.argmax(col_darkness))


def suppress_close_candidates(
    candidate_xs: list[int],
    strengths: np.ndarray,
    minimum_distance: int = 55,
) -> list[int]:
    """Keep the strongest candidate when a notehead and its flag overlap.

    Duolingo's standalone eighth-note flag is roughly 45--50 pixels to the
    right of its notehead.  Both shapes can correlate with the circular
    template, but the real filled notehead has a substantially stronger
    response.  Suppressing in strength order preserves the notehead without
    imposing a global confidence threshold that could discard hollow notes.
    """
    strongest_first = sorted(candidate_xs, key=lambda x: float(strengths[x]), reverse=True)
    kept: list[int] = []
    for candidate_x in strongest_first:
        if all(abs(candidate_x - kept_x) >= minimum_distance for kept_x in kept):
            kept.append(candidate_x)
    return sorted(kept)


def refine_hollow_notehead_center(
    arr: np.ndarray,
    candidate_x: int,
    rough_center_y: float,
    positions: dict[str, tuple[float, str]],
) -> tuple[float, float] | None:
    """Locate a hollow notehead by its dark ellipse and bright inner cavity.

    A half-note stem and the staff line crossing its head can pull a generic
    dark-pixel centroid upward.  Evaluate the expected staff-step positions
    with an elliptical ring instead, while rejecting candidates whose inner
    cavity is too dark to be hollow.
    """
    h, w, _ = arr.shape
    radius_x, radius_y = 24, 18
    grid_y, grid_x = np.ogrid[-radius_y : radius_y + 1, -radius_x : radius_x + 1]
    ellipse_distance = (grid_x / 21.0) ** 2 + (grid_y / 14.0) ** 2
    ring_mask = (ellipse_distance <= 1.0) & (ellipse_distance >= 0.45)
    core_mask = ellipse_distance <= 0.35
    # Only these pixels can be visited by the candidate-center search below.
    # Building a full-frame mask once per hollow candidate dominates the live
    # reader on dense scores, even though each patch is only 49x37 pixels.
    rough_y = int(round(rough_center_y))
    top = max(0, rough_y - 31 - radius_y)
    bottom = min(h, rough_y + 31 + radius_y + 1)
    left = max(0, candidate_x - 14 - radius_x)
    right = min(w, candidate_x + 14 + radius_x + 1)
    dark = (arr[top:bottom, left:right] < 130).all(axis=2)

    best: tuple[float, float, float] | None = None
    for expected_y, _description in positions.values():
        if abs(float(expected_y) - rough_center_y) > 30:
            continue
        center_y = int(round(expected_y))
        if center_y - radius_y < 0 or center_y + radius_y >= h:
            continue

        for center_x in range(candidate_x - 14, candidate_x + 15):
            if center_x - radius_x < 0 or center_x + radius_x >= w:
                continue
            patch = dark[
                center_y - radius_y - top : center_y + radius_y + 1 - top,
                center_x - radius_x - left : center_x + radius_x + 1 - left,
            ]
            ring_darkness = float(patch[ring_mask].mean())
            core_darkness = float(patch[core_mask].mean())
            if ring_darkness < 0.35 or core_darkness > 0.40:
                continue

            score = ring_darkness - 0.45 * core_darkness
            if best is None or score > best[0]:
                best = (score, float(center_x), float(expected_y))

    if best is None or best[0] < 0.25:
        return None
    return best[1], best[2]


def find_augmentation_dot(
    arr: np.ndarray,
    center_x: float,
    center_y: float,
    next_note_x: float | None = None,
) -> tuple[float, float] | None:
    """Return the center of a small filled augmentation dot to a note's right.

    In the OPPO Duolingo renderer, the dot is a nearly circular 16px blob whose
    center is about 39px to the right of the notehead. Limit the search before
    the next notehead and reject narrow stem fragments or large note shapes.
    """
    h, w, _ = arr.shape
    cx, cy = int(round(center_x)), int(round(center_y))
    # The generic notehead centroid can be pulled about 8px toward an up-stem,
    # so start early enough to retain the dot's complete circular silhouette.
    left = max(0, cx + 20)
    right = min(w, cx + 50)
    if next_note_x is not None:
        right = min(right, int(round(next_note_x)) - 23)
    top = max(0, cy - 20)
    bottom = min(h, cy + 21)
    if right - left < 7 or bottom - top < 7:
        return None

    dark = (arr[top:bottom, left:right] < 150).all(axis=2)
    labels, count = scipy.ndimage.label(dark)
    best: tuple[int, float, float] | None = None
    for label_id in range(1, count + 1):
        ys, xs = np.where(labels == label_id)
        area = len(xs)
        if area == 0:
            continue
        width = int(xs.max() - xs.min() + 1)
        height = int(ys.max() - ys.min() + 1)
        fill_ratio = area / float(width * height)
        dot_x = left + float(xs.mean())
        dot_y = top + float(ys.mean())
        aspect_ratio = width / float(height)

        if not (12 <= width <= 20 and 12 <= height <= 20):
            continue
        if not (0.65 <= aspect_ratio <= 1.45 and fill_ratio >= 0.50):
            continue
        if not (24 <= dot_x - center_x <= 48 and abs(dot_y - center_y) <= 15):
            continue
        if best is None or area > best[0]:
            best = (area, dot_x, dot_y)

    return None if best is None else (best[1], best[2])


def detect_flat_key_signature_count(arr: np.ndarray) -> int:
    """Count neutral-gray flats between the clef and judgment line.

    Theme glyphs are substantially darker than their local background but are
    not necessarily black. Flat glyphs form roughly 30x64px components; the
    height constraint excludes nearby 3/4 time-signature digits.
    """
    # In some lessons the second flat reaches y≈117; cropping at y=125
    # shortens its component below the height threshold and silently turns
    # every E-flat note into E-natural.
    # Scan through the whole signature slot.  Cropping at x=350 loses the
    # rightmost flat; time-signature digits remain excluded by glyph height.
    region = arr[90:345, 195:430]
    luminance = region.mean(axis=2)
    neutral = region.max(axis=2) - region.min(axis=2) < 12
    local_background = float(np.median(luminance))
    glyph_threshold = min(205.0, local_background - 25.0)
    labels, count = scipy.ndimage.label(neutral & (luminance < glyph_threshold))

    flat_count = 0
    for label_id in range(1, count + 1):
        ys, xs = np.where(labels == label_id)
        if len(xs) < 300:
            continue
        width = int(xs.max() - xs.min() + 1)
        height = int(ys.max() - ys.min() + 1)
        if 15 <= width <= 45 and 58 <= height <= 105:
            flat_count += 1

    return flat_count


def detect_flat_key_signature(arr: np.ndarray) -> bool:
    """Backward-compatible boolean key-signature query."""
    return detect_flat_key_signature_count(arr) > 0


def detect_sharp_key_signature_count(arr: np.ndarray) -> int:
    """Count sharp glyphs between the clef and time signature.

    A sharp is a wider, denser component than the flat glyphs in this score
    theme. Keep the crop before the time signature so its digits cannot count.
    """
    # The right edge must also admit four or more sharps.  Time-signature
    # digits are shorter than the sharp components in the captured theme.
    region = arr[90:345, 195:430]
    luminance = region.mean(axis=2)
    neutral = region.max(axis=2) - region.min(axis=2) < 12
    local_background = float(np.median(luminance))
    glyph_threshold = min(205.0, local_background - 25.0)
    labels, count = scipy.ndimage.label(neutral & (luminance < glyph_threshold))

    sharp_count = 0
    for label_id in range(1, count + 1):
        ys, xs = np.where(labels == label_id)
        if len(xs) < 900:
            continue
        width = int(xs.max() - xs.min() + 1)
        height = int(ys.max() - ys.min() + 1)
        if 37 <= width <= 55 and 55 <= height <= 90:
            sharp_count += 1
    return sharp_count


def detect_key_signature_counts(arr: np.ndarray) -> tuple[int, int]:
    """Return (flats, sharps), resolving the sharp/flat shape overlap."""
    flats = detect_flat_key_signature_count(arr)
    sharps = detect_sharp_key_signature_count(arr)
    return (0, sharps) if sharps else (flats, 0)


def notehead_component_label(
    labels: np.ndarray,
    center_x: float,
    center_y: float,
) -> int:
    """Return the connected dark-glyph component containing a notehead."""
    h, w = labels.shape
    cx, cy = int(round(center_x)), int(round(center_y))
    x0, x1 = max(0, cx - 24), min(w, cx + 25)
    y0, y1 = max(0, cy - 18), min(h, cy + 19)
    patch = labels[y0:y1, x0:x1]
    component_ids, counts = np.unique(patch[patch > 0], return_counts=True)
    if len(component_ids) == 0:
        return 0
    return int(component_ids[int(np.argmax(counts))])


def detect_note_stem(
    labels: np.ndarray,
    component_label: int,
    center_x: float,
    center_y: float,
) -> dict | None:
    """Detect a note's stem above-right or below-left of its notehead.

    Only pixels belonging to the notehead's connected glyph are considered,
    so nearby notes, accidentals, and staff decorations cannot donate a stem.
    """
    if component_label == 0:
        return None

    h, w = labels.shape
    cx, cy = int(round(center_x)), int(round(center_y))
    candidates: list[dict] = []
    searches = (
        ("up", max(0, cy - 170), max(0, cy - 12), max(0, cx + 3), min(w, cx + 30)),
        ("down", min(h, cy + 12), min(h, cy + 170), max(0, cx - 30), max(0, cx - 3)),
    )
    for direction, y0, y1, x0, x1 in searches:
        if y1 <= y0 or x1 <= x0:
            continue
        component = labels[y0:y1, x0:x1] == component_label
        column_counts = component.sum(axis=0)
        if len(column_counts) == 0 or int(column_counts.max()) < 25:
            continue
        best_column = int(np.argmax(column_counts))
        strong = np.where(column_counts >= max(25, int(column_counts.max() * 0.65)))[0]
        stem_columns = strong[np.abs(strong - best_column) <= 8]
        if len(stem_columns) == 0:
            stem_columns = np.array([best_column])
        stem_pixels = component[:, stem_columns]
        stem_rows = np.where(stem_pixels.any(axis=1))[0]
        if len(stem_rows) == 0:
            continue
        tip_y = y0 + int(stem_rows.min() if direction == "up" else stem_rows.max())
        candidates.append({
            "direction": direction,
            "x": x0 + best_column,
            "left": x0 + int(stem_columns.min()),
            "right": x0 + int(stem_columns.max()),
            "tip_y": tip_y,
            "strength": int(column_counts.max()),
        })

    return max(candidates, key=lambda candidate: candidate["strength"], default=None)


def detect_judgment_occluded_stem(
    arr: np.ndarray,
    center_x: float,
    center_y: float,
    judgment_line_x: int,
    luminance: np.ndarray | None = None,
) -> dict | None:
    """Recover a stem whose dark pixels are recolored by the judgment line.

    The translucent neutral-gray line raises the stem above the normal dark
    glyph threshold, but the covered stem remains much darker than the line's
    untouched background. This fallback is only active for overlapping notes.
    """
    h, w, _ = arr.shape
    cx, cy = int(round(center_x)), int(round(center_y))
    if abs(cx - judgment_line_x) > 36:
        return None

    if luminance is None:
        luminance = arr.mean(axis=2)
    candidates: list[dict] = []
    searches = (
        ("up", max(0, cy - 170), max(0, cy - 12), max(0, cx + 3), min(w, cx + 30)),
        ("down", min(h, cy + 12), min(h, cy + 170), max(0, cx - 30), max(0, cx - 3)),
    )
    for direction, y0, y1, x0, x1 in searches:
        if y1 <= y0 or x1 <= x0:
            continue
        covered_glyph = luminance[y0:y1, x0:x1] < 205
        column_counts = covered_glyph.sum(axis=0)
        if len(column_counts) == 0 or int(column_counts.max()) < 25:
            continue
        best_column = int(np.argmax(column_counts))
        stem_rows = np.where(covered_glyph[:, best_column])[0]
        tip_y = y0 + int(stem_rows.min() if direction == "up" else stem_rows.max())
        candidates.append({
            "direction": direction,
            "x": x0 + best_column,
            "left": x0 + best_column,
            "right": x0 + best_column,
            "tip_y": tip_y,
            "strength": int(column_counts.max()),
        })

    return max(candidates, key=lambda candidate: candidate["strength"], default=None)


def detect_stem_flag(
    arr: np.ndarray,
    is_staff: np.ndarray,
    stem: dict | None,
) -> bool:
    """Detect a standalone eighth-note flag for either stem direction."""
    if stem is None:
        return False
    h, w, _ = arr.shape
    tip_y = int(stem["tip_y"])
    if stem["direction"] == "up":
        y0, y1 = max(0, tip_y), min(h, tip_y + 52)
    else:
        y0, y1 = max(0, tip_y - 52), min(h, tip_y + 1)
    x0 = max(0, int(stem["right"]) + 2)
    x1 = min(w, int(stem["right"]) + 32)
    flag_pixels = (
        (arr[y0:y1, x0:x1] < 120).all(axis=2)
        & (~is_staff[y0:y1, None])
    )
    return bool(flag_pixels.sum() > 150)


def is_keyboard_key_top(arr: np.ndarray, center_x: float, center_y: float) -> bool:
    """Return whether a circular candidate is the rounded top of a piano key.

    Low staff positions can overlap the on-screen keyboard.  A genuine
    notehead ends within a few pixels below its center, while a black key has
    a broad, nearly solid body extending dozens of pixels downward.  Test that
    continuation instead of excluding the A3/G3 pitch band altogether.
    """
    h, w, _ = arr.shape
    cx, cy = int(round(center_x)), int(round(center_y))
    below = (arr[
        min(h, cy + 14) : min(h, cy + 74),
        max(0, cx - 16) : min(w, cx + 17),
    ] < 130).all(axis=2)
    if below.size == 0 or below.shape[0] < 40:
        return False

    row_density = below.mean(axis=1)
    gap_rows = row_density[:32] < 0.10
    longest_gap = 0
    current_gap = 0
    for is_gap in gap_rows:
        current_gap = current_gap + 1 if is_gap else 0
        longest_gap = max(longest_gap, current_gap)

    dark_density = float(below.mean())
    long_dark_columns = int((below.sum(axis=0) > 35).sum())
    return longest_gap < 6 and dark_density > 0.45 and long_dark_columns >= 8


def find_staff_right_edge(arr: np.ndarray, staff_ys: list[int]) -> int:
    """Find where the shared horizontal staff lines end on the right."""
    sampled_rows = arr[np.asarray(staff_ys), :, :]
    line_presence = (sampled_rows < 245).all(axis=2).sum(axis=0) >= 3
    present_xs = np.where(line_presence)[0]
    return int(present_xs.max()) if len(present_xs) else arr.shape[1] - 1


def analyze_screen_rests(
    img: Image.Image | ScreenAnalysisContext,
    min_x: int | None = None,
    max_x: int = 1520,
) -> list[dict]:
    """Detect Duolingo rest glyphs at and to the right of the judgment line."""
    context = ensure_analysis_context(img)
    arr = context.arr
    line_5_y, line_4_y, line_3_y, _line_2_y, line_1_y = context.staff_lines
    if min_x is None:
        min_x = max(0, context.judgment_line_x - 10)

    # Duolingo draws rests darker than the staff.  Label the complete screen
    # so low noteheads and keyboard keys retain their full component geometry
    # instead of being truncated into rest-sized fragments by a crop.
    dark = (arr < 190).all(axis=2)
    labels, _count = scipy.ndimage.label(dark)
    components = scipy.ndimage.find_objects(labels)
    score_top = line_5_y - 12
    score_bottom = line_1_y + 32
    rests: list[dict] = []

    for label_id, slices in enumerate(components, 1):
        if slices is None:
            continue
        y_slice, x_slice = slices
        x0, x1 = x_slice.start, x_slice.stop
        y0, y1 = y_slice.start, y_slice.stop
        width, height = x1 - x0, y1 - y0
        center_x = (x0 + x1 - 1) / 2.0
        center_y = (y0 + y1 - 1) / 2.0
        if center_x < min_x or center_x >= max_x:
            continue
        if y1 < score_top or y0 > score_bottom:
            continue

        area = int((labels[slices] == label_id).sum())
        duration_type: str | None = None
        duration_beats: float | None = None
        position = ""

        if 20 <= width <= 45 and 75 <= height <= 110 and 500 <= area <= 1800:
            duration_type = "Quarter Rest (四分休止符)"
            duration_beats = 1.0
            position = "Quarter-rest glyph"
        elif 24 <= width <= 50 and 45 <= height <= 75 and 300 <= area <= 1300:
            duration_type = "Eighth Rest (八分休止符)"
            duration_beats = 0.5
            position = "Eighth-rest glyph"
        elif 20 <= width <= 42 and 10 <= height <= 26 and 200 <= area <= 750:
            half_distance = abs(y1 - line_3_y)
            whole_distance = abs(y0 - line_4_y)
            if half_distance <= 10 and half_distance <= whole_distance:
                duration_type = "Half Rest (二分休止符)"
                duration_beats = 2.0
                position = "Block resting on middle line"
            elif whole_distance <= 10:
                duration_type = "Whole Rest (全休止符)"
                duration_beats = 4.0
                position = "Block hanging from line 4"

        if duration_type is None or duration_beats is None:
            continue

        rests.append({
            "event_type": "rest",
            "x": round(center_x, 1),
            "y": round(center_y, 1),
            "bbox": [x0, y0, x1, y1],
            "pitch": None,
            "position": position,
            "pixel_error": 0.0,
            "edge_clipped": False,
            "duration_type": duration_type,
            "duration_beats": duration_beats,
            "hold_beats": 0.0,
            "delta_beats": duration_beats,
            "key_target": None,
            "key_label": "休",
            "key_unmapped": False,
        })

    return sorted(rests, key=lambda rest: rest["x"])


def analyze_screen_notes(
    img: Image.Image | ScreenAnalysisContext,
    min_x: int | None = None,
    max_x: int = 1520,
    has_flat_key_sig: bool = False,
    annotated_output_path: Path | None = None,
    key_signature: tuple[int, int] | None = None,
) -> list[dict]:
    context = ensure_analysis_context(img)
    arr = context.arr
    h, w, _ = arr.shape

    # Detect judgment line if min_x is not explicitly provided
    judgment_line_x = context.judgment_line_x
    if min_x is None:
        # Start right at the judgment line (with a slight margin to capture notehead on/at the line)
        min_x = max(0, judgment_line_x - 10)

    flat_count, sharp_count = (
        key_signature if key_signature is not None
        else detect_key_signature_counts(arr)
    )
    if has_flat_key_sig:
        flat_count = max(flat_count, 1)
    def signed_pitch(natural_pitch: str) -> str:
        return apply_key_signature(natural_pitch, (flat_count, sharp_count))

    # 1. Staff lines: line 5 (top) to line 1 (bottom)
    line_5_y, line_4_y, line_3_y, line_2_y, line_1_y = context.staff_lines
    step_y = (line_1_y - line_5_y) / 4.0
    staff_ys = [line_5_y, line_4_y, line_3_y, line_2_y, line_1_y]
    staff_right_x = find_staff_right_edge(arr, staff_ys)

    positions = {
        signed_pitch("A5"): (line_5_y - step_y, "Ledger line 1 above"),
        signed_pitch("G5"): (line_5_y - step_y / 2.0, "Space above Line 5"),
        signed_pitch("F5"): (line_5_y, "Line 5"),
        signed_pitch("E5"): ((line_5_y + line_4_y) / 2.0, "Space 4"),
        signed_pitch("D5"): (line_4_y, "Line 4"),
        signed_pitch("C5"): ((line_4_y + line_3_y) / 2.0, "Space 3"),
        signed_pitch("B4"): (line_3_y, "Line 3"),
        signed_pitch("A4"): ((line_3_y + line_2_y) / 2.0, "Space 2"),
        signed_pitch("G4"): (line_2_y, "Line 2"),
        signed_pitch("F4"): ((line_2_y + line_1_y) / 2.0, "Space 1"),
        signed_pitch("E4"): (line_1_y, "Line 1"),
        signed_pitch("D4"): (line_1_y + step_y / 2.0, "Space below Line 1"),
        signed_pitch("C4"): (line_1_y + step_y, "Ledger line 1 below"),
        signed_pitch("B3"): (line_1_y + 1.5 * step_y, "Space below Ledger 1"),
        signed_pitch("A3"): (line_1_y + 2.0 * step_y, "Ledger line 2 below"),
    }

    # 2. Find noteheads using 2D circular shape correlation to prevent stems/beams from throwing off X/Y
    search_top = int(min(row for row, _ in positions.values()) - 25)
    search_bottom = int(line_1_y + 2.5 * step_y + 35)

    dark = (arr[search_top:search_bottom, :] < 130).all(axis=2).astype(float)
    r = 14
    y_grid, x_grid = np.ogrid[-r:r+1, -r:r+1]
    disk = (x_grid**2 + y_grid**2 <= r**2).astype(float)
    ring = ((x_grid**2 + y_grid**2 <= r**2) & (x_grid**2 + y_grid**2 >= (r-5)**2)).astype(float)

    # The circular templates are center-symmetric, so FFT convolution is
    # numerically equivalent to correlation and substantially faster here.
    corr_disk = scipy.signal.fftconvolve(dark, disk, mode="same") / disk.sum()
    corr_ring = scipy.signal.fftconvolve(dark, ring, mode="same") / ring.sum()
    score = np.maximum(corr_disk, corr_ring / 0.6)

    # Restrict the peak profile to narrow bands around playable staff steps.
    # Searching every Y lets stems, beams, and the keyboard win the column max.
    pitch_rows = sorted({
        row
        for expected_y, _description in positions.values()
        for row in range(
            max(0, int(round(expected_y)) - 8 - search_top),
            min(score.shape[0], int(round(expected_y)) + 9 - search_top),
        )
    })
    pitch_score = score[pitch_rows, :].max(axis=0)
    pitch_argmax = score[pitch_rows, :].argmax(axis=0)
    col_best_y = np.asarray(pitch_rows)[pitch_argmax] + search_top

    peaks_x, _ = scipy.signal.find_peaks(
        pitch_score[min_x:max_x], height=0.75, distance=45
    )
    raw_candidate_xs = [min_x + int(px) for px in peaks_x]
    lower_rows = sorted({
        row
        for name, (expected_y, _description) in positions.items()
        if name != signed_pitch("A5")
        for row in range(
            max(0, int(round(expected_y)) - 8 - search_top),
            min(score.shape[0], int(round(expected_y)) + 9 - search_top),
        )
    })
    lower_profile = score[lower_rows, :].max(axis=0)
    lower_peaks, _ = scipy.signal.find_peaks(
        lower_profile[min_x:max_x], height=0.75, distance=45
    )
    raw_candidate_xs.extend(min_x + int(px) for px in lower_peaks)
    candidate_xs = suppress_close_candidates(raw_candidate_xs, pitch_score)

    # 3. For each notehead X, extract true circular blob center
    notes = []
    vis = context.image.copy() if annotated_output_path else None
    draw = ImageDraw.Draw(vis) if vis else None

    if draw:
        # Draw judgment line in distinct purple
        draw.line([(judgment_line_x, 0), (judgment_line_x, h)], fill=(180, 50, 220), width=2)
        draw.text((judgment_line_x + 4, 150), "判定线", fill=(180, 50, 220))
        for ly in [line_5_y, line_4_y, line_3_y, line_2_y, line_1_y]:
            draw.line([(0, ly), (w, ly)], fill=(0, 200, 255), width=1)
        draw.line([(0, int(line_1_y + step_y)), (w, int(line_1_y + step_y))], fill=(100, 220, 255), width=1)
        draw.line([(0, int(line_1_y + 2 * step_y)), (w, int(line_1_y + 2 * step_y))], fill=(100, 220, 255), width=1)

    is_staff = np.zeros(h, dtype=bool)
    for sy in staff_ys:
        is_staff[max(0, sy - 3) : min(h, sy + 4)] = True

    for fx in candidate_xs:
        fy = col_best_y[fx]
        sub = arr[max(0, fy - 20) : min(h, fy + 25), max(0, fx - 22) : min(w, fx + 23)]
        sub_dark = (sub < 130).all(axis=2)
        row_spans = sub_dark.sum(axis=1)
        # A touching down-stem flag widens the narrow edge rows below a filled
        # head. Prefer its broad body so that the curl cannot shift the pitch;
        # hollow or clipped heads retain the original narrow-row fallback.
        c_rows = np.where(row_spans >= (30 if pitch_score[fx] >= 1.4 else 16))[0]
        if len(c_rows) == 0:
            c_rows = np.where(row_spans >= 16)[0]
        if len(c_rows) == 0:
            c_rows = np.where(row_spans >= 10)[0]
        if len(c_rows) == 0:
            continue
        cy = (fy - 20) + (c_rows.min() + c_rows.max()) / 2.0

        mid_r = int((c_rows.min() + c_rows.max()) / 2.0)
        col_spans = sub_dark[max(0, mid_r - 6) : min(sub_dark.shape[0], mid_r + 7), :].sum(axis=0)
        c_cols = np.where(col_spans > 0)[0]
        cx = (fx - 22) + (c_cols.min() + c_cols.max()) / 2.0 if len(c_cols) > 0 else float(fx)

        # Hollow noteheads need a shape-aware center.  Their tall stem and a
        # crossing staff line otherwise bias the dark-pixel centroid upward.
        hollow_center = (
            refine_hollow_notehead_center(arr, fx, cy, positions)
            if pitch_score[fx] < 1.4
            else None
        )
        if hollow_center is not None:
            cx, cy = hollow_center

        # Find closest pitch
        diffs = {name: abs(cy - exp_y) for name, (exp_y, desc) in positions.items()}
        closest_pitch = min(diffs, key=diffs.get)
        pixel_error = diffs[closest_pitch]
        pos_desc = positions[closest_pitch][1]

        # The keyboard only overlaps positions well below the staff.  Applying
        # its broad-downward-body heuristic to higher notes incorrectly removes
        # valid down-stem eighth notes whose flag touches the notehead.
        keyboard_overlap_y = line_1_y + 1.25 * step_y
        if cy >= keyboard_overlap_y and is_keyboard_key_top(arr, cx, cy):
            continue

        notes.append({
            "event_type": "note",
            "x": round(float(cx), 1),
            "y": round(float(cy), 1),
            "pitch": closest_pitch,
            "position": pos_desc,
            "pixel_error": round(float(pixel_error), 2),
            "edge_clipped": bool(cx + 18 >= staff_right_x),
        })

    # Bind each notehead to its complete dark glyph. Beamed notes share a
    # connected component regardless of whether their stems point up or down,
    # and regardless of the beam's angle.
    glyph_labels, _component_count = scipy.ndimage.label((arr < 120).all(axis=2))
    component_labels = [
        notehead_component_label(glyph_labels, note["x"], note["y"])
        for note in notes
    ]
    # A flagged eighth note is one connected glyph.  Its curled flag can
    # resemble a second, much higher notehead just to the right of the real
    # one.  Adjacent beamed notes may also share a component, but their heads
    # stay on the same staff row or are spaced farther apart.
    flag_echo_indices = {
        index
        for index, candidate in enumerate(notes)
        if component_labels[index] != 0
        and any(
            index != peer_index
            and component_labels[index] == component_labels[peer_index]
            and 20 <= candidate["x"] - peer["x"] <= 60
            and candidate["y"] <= peer["y"] - 40
            for peer_index, peer in enumerate(notes)
        )
    }
    if flag_echo_indices:
        notes = [note for index, note in enumerate(notes) if index not in flag_echo_indices]
        component_labels = [
            label for index, label in enumerate(component_labels)
            if index not in flag_echo_indices
        ]
    stems = [
        detect_note_stem(glyph_labels, component_label, note["x"], note["y"])
        for note, component_label in zip(notes, component_labels)
    ]
    stems = [
        stem
        if stem is not None
        else detect_judgment_occluded_stem(
            arr,
            note["x"],
            note["y"],
            judgment_line_x,
            luminance=context.luminance,
        )
        for note, stem in zip(notes, stems)
    ]
    beam_components = {
        component_labels[index]
        for index in range(len(notes) - 1)
        if component_labels[index] != 0
        and component_labels[index] == component_labels[index + 1]
        and stems[index] is not None
        and stems[index + 1] is not None
    }

    # 4. Determine base durations, then apply any augmentation dot.
    for i, note in enumerate(notes):
        cx, cy = int(round(note["x"])), int(round(note["y"]))
        stem = stems[i]
        has_beam = component_labels[i] in beam_components
        has_flag = False
        # Sample the upper and lower inside of notehead: hollow notehead (half or whole note)
        # has bright hole inside, but ledger line or staff line may pass directly through the horizontal center
        top_inner = arr[max(0, cy - 9) : max(0, cy - 3), max(0, cx - 6) : min(w, cx + 3)]
        btm_inner = arr[min(h, cy + 4) : min(h, cy + 10), max(0, cx - 6) : min(w, cx + 3)]
        top_bright = (top_inner > 180).all(axis=2).mean()
        btm_bright = (btm_inner > 180).all(axis=2).mean()
        center_roi = arr[max(0, cy - 4) : min(h, cy + 5), max(0, cx - 4) : min(w, cx + 5)]
        center_bright = (center_roi.mean() > 180) and ((center_roi < 100).all(axis=2).sum() == 0)

        is_hollow = center_bright or (top_bright > 0.15 and btm_bright > 0.10)

        if note["edge_clipped"]:
            note["duration_type"] = "Unknown (右侧裁切，时值未知)"
            note["duration_beats"] = None
            note["hold_beats"] = None
            note["delta_beats"] = None
        elif is_hollow:
            if stem is not None:
                note["duration_type"] = "Half Note (二分音符)"
                note["duration_beats"] = 2.0
                note["hold_beats"] = 1.8
                note["delta_beats"] = 2.0
            else:
                note["duration_type"] = "Whole Note (全音符)"
                note["duration_beats"] = 4.0
                note["hold_beats"] = 3.8
                note["delta_beats"] = 4.0
        else:
            has_flag = detect_stem_flag(arr, is_staff, stem) if not has_beam else False
            is_eighth = has_flag or has_beam
            if is_eighth:
                note["duration_type"] = "Eighth Note (八分音符)"
                note["duration_beats"] = 0.5
                note["hold_beats"] = 0.4
                note["delta_beats"] = 0.5
            else:
                note["duration_type"] = "Quarter Note (四分音符)"
                note["duration_beats"] = 1.0
                note["hold_beats"] = 0.8
                note["delta_beats"] = 1.0

        note["stem_direction"] = stem["direction"] if stem is not None else None
        note["has_beam"] = bool(has_beam)
        note["has_flag"] = bool(has_flag)

        next_note_x = notes[i + 1]["x"] if i + 1 < len(notes) else None
        dot_center = (
            find_augmentation_dot(arr, note["x"], note["y"], next_note_x)
            if note["duration_beats"] is not None
            else None
        )
        note["is_dotted"] = dot_center is not None
        if dot_center is not None:
            base_duration = note["duration_beats"]
            release_gap = base_duration - note["hold_beats"]
            note["duration_beats"] = base_duration * 1.5
            note["delta_beats"] = note["duration_beats"]
            note["hold_beats"] = note["duration_beats"] - release_gap
            english, chinese = note["duration_type"].rsplit(" (", 1)
            note["duration_type"] = f"Dotted {english} (附点{chinese}"

        keyboard = context.keyboard
        note["key_target"] = keyboard.target(note["pitch"]) if keyboard else None
        note["key_label"] = (
            keyboard.label(note["pitch"]) if keyboard else note["pitch"]
        )
        # Duolingo only prints a label on the keys this song uses, so a pitch
        # with no key is a signal that recognition drifted -- surface it rather
        # than tapping the nearest plausible coordinate.
        note["key_unmapped"] = note["key_target"] is None

        if draw:
            cx, cy = note["x"], note["y"]
            p = note["pitch"]
            draw.ellipse((cx - 15, cy - 15, cx + 15, cy + 15), outline=(255, 0, 0), width=2)
            draw.line([(cx - 20, cy), (cx + 20, cy)], fill=(255, 0, 0), width=2)
            draw.text((cx - 12, cy - 35), p, fill=(255, 0, 0))
            if dot_center is not None:
                dot_x, dot_y = dot_center
                draw.ellipse(
                    (dot_x - 10, dot_y - 10, dot_x + 10, dot_y + 10),
                    outline=(255, 140, 0),
                    width=2,
                )

    if annotated_output_path and vis:
        vis.save(annotated_output_path)

    return notes


def annotate_rests(path: Path, rests: list[dict]) -> None:
    """Add orange rest boxes to an annotation image created for notes."""
    vis = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(vis)
    for rest in rests:
        x0, y0, x1, y1 = rest["bbox"]
        draw.rectangle((x0 - 3, y0 - 3, x1 + 3, y1 + 3), outline=(255, 140, 0), width=3)
        short_label = rest["duration_type"].split(" ", 1)[0] + " Rest"
        draw.text((x0, max(0, y0 - 18)), short_label, fill=(255, 100, 0))
    vis.save(path)


def chinese_duration_name(duration_type: str) -> str:
    if "(" in duration_type and duration_type.endswith(")"):
        return duration_type.rsplit("(", 1)[1][:-1]
    return duration_type


def format_human_readable_list(events: list[dict] | tuple[dict, ...]) -> str:
    """Render recognition events as a numbered, human-readable list."""
    lines: list[str] = []
    note_count = 0
    rest_count = 0
    unknown_count = 0
    known_beats = 0.0

    for index, event in enumerate(events, 1):
        duration = event["duration_beats"]
        if duration is None:
            unknown_count += 1
        else:
            known_beats += float(duration)

        if event["event_type"] == "rest":
            rest_count += 1
            name = chinese_duration_name(event["duration_type"])
            duration_label = "时值未知" if duration is None else f"{duration:g} 拍"
            lines.append(f"{index}. {name} — {duration_label}")
            continue

        note_count += 1
        pitch = (event["pitch"] or "?").replace("b", "♭").replace("#", "♯")
        if duration is None:
            lines.append(f"{index}. {pitch} — 时值未知")
            continue
        name = chinese_duration_name(event["duration_type"])
        lines.append(f"{index}. {pitch} — {name} — {duration:g} 拍")

    unknown_summary = f"，{unknown_count} 个时值未知" if unknown_count else ""
    lines.extend(
        [
            "",
            f"已知合计：{known_beats:g} 拍",
            f"事件统计：{note_count} 个音符，{rest_count} 个休止符{unknown_summary}",
        ]
    )
    return "\n".join(lines)


class AsyncHumanReadableWriter:
    """Format and append human output away from the response path."""

    def __init__(self, error_stream: TextIO | None = None) -> None:
        self._error_stream = error_stream or sys.stderr
        self._queue: queue.SimpleQueue[
            tuple[Path, tuple[dict, ...]] | None
        ] = queue.SimpleQueue()
        self._thread: threading.Thread | None = None

    def submit(self, path: Path, events: list[dict]) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        self._queue.put((path, tuple(events)))

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                return
            path, events = job
            try:
                rendered = format_human_readable_list(events)
                path.parent.mkdir(parents=True, exist_ok=True)
                separator = "\n\n" if path.exists() and path.stat().st_size else ""
                timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
                record = (
                    f"{separator}记录时间：{timestamp}\n\n"
                    f"{rendered}\n"
                )
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(record)
            except Exception as exc:
                print(
                    f"human-readable output failed for {path}: {exc}",
                    file=self._error_stream,
                    flush=True,
                )

    def close(self) -> None:
        if self._thread is None:
            return
        self._queue.put(None)
        self._thread.join()
        self._thread = None


def print_markdown_table(events: list[dict], elapsed_ms: float) -> None:
    print(f"\n### 屏幕识别乐谱事件与相对时间结果 (耗时: {elapsed_ms:.1f} ms)")
    print("| 序号 | 类型 | 坐标 (X, Y) | 几何位置 | 音名 | 对应琴键坐标 | 键位标注 | 时值类型 | 按住拍数 (hold) | 相对间隔 (delta) |")
    print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for idx, event in enumerate(events, 1):
        if event["key_target"]:
            coord_str = f"({event['key_target'][0]}, {event['key_target'][1]})"
        elif event.get("key_unmapped"):
            coord_str = "**⚠ 未标注键**"
        else:
            coord_str = "—"
        pitch = event["pitch"] or "休止"
        event_label = "音符" if event["event_type"] == "note" else "休止符"
        hold = f"{event['hold_beats']} 拍" if event["hold_beats"] is not None else "未知"
        delta = f"{event['delta_beats']} 拍" if event["delta_beats"] is not None else "未知"
        print(
            f"| {idx} | {event_label} | ({event['x']}, {event['y']}) | {event['position']} | "
            f"**{pitch}** | {coord_str} | `{event['key_label']}` | {event['duration_type']} | "
            f"{hold} | **{delta}** |"
        )


def analyze_image(
    img: Image.Image,
    *,
    out_annotated: Path | None = None,
    started_at: float | None = None,
    key_signature: tuple[int, int] | None = None,
) -> dict:
    """Analyze one already-loaded frame."""
    if started_at is None:
        started_at = time.perf_counter()
    context = build_analysis_context(img)
    if context.staff_lines is None:
        raise ScoreNotVisibleError("five-line staff is not visible")
    detected_key_signature = detect_key_signature_counts(context.arr)
    notes = analyze_screen_notes(
        context,
        annotated_output_path=out_annotated,
        key_signature=key_signature or detected_key_signature,
    )
    rests = analyze_screen_rests(context)
    events = sorted([*notes, *rests], key=lambda event: event["x"])
    if out_annotated is not None:
        annotate_rests(out_annotated, rests)

    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    return {
        "elapsed_ms": elapsed_ms,
        "key_signature": {
            "flats": detected_key_signature[0],
            "sharps": detected_key_signature[1],
        },
        "notes": notes,
        "rests": rests,
        "events": events,
    }


def analyze_request(
    *,
    image_path: Path | None = None,
    serial: str | None = None,
    out_annotated: Path | None = None,
    started_at: float | None = None,
) -> dict:
    """Capture or load one frame and return its complete recognition result."""
    if started_at is None:
        started_at = time.perf_counter()
    if image_path is not None:
        with Image.open(image_path) as source:
            img = source.convert("RGB")
    else:
        img = capture_adb_screenshot(serial)
    return analyze_image(
        img,
        out_annotated=out_annotated,
        started_at=started_at,
    )


def write_json_line(stream: TextIO, payload: dict) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    stream.write("\n")
    stream.flush()


def semantic_event_signature(events: list[dict]) -> tuple[tuple[object, ...], ...]:
    """Return score meaning while deliberately ignoring scrolling geometry."""
    return tuple(
        (
            event["event_type"],
            event["pitch"],
            event["duration_type"],
            event["duration_beats"],
        )
        for event in events
    )


def watch_result_signature(result: dict) -> tuple[object, ...]:
    """Distinguish a visible empty staff from a screen with no score."""
    return (
        result.get("screen_state", "score"),
        semantic_event_signature(result["events"]),
    )


def watch_screen_changes(
    output_stream: TextIO,
    *,
    default_serial: str | None = None,
    frame_source: str = "auto",
    stable_frames: int = 2,
    poll_interval: float = 0.05,
    frame_pump_factory: Callable[[str, str], H264FramePump] | None = None,
    human_readable_out: Path | None = None,
    human_writer: AsyncHumanReadableWriter | None = None,
    max_updates: int | None = None,
) -> None:
    """Continuously emit a JSON result only when stable score meaning changes."""
    if frame_source not in {"auto", "h264", "png"}:
        raise ValueError(f"unsupported frame source: {frame_source}")
    if stable_frames < 1:
        raise ValueError("stable_frames must be at least 1")
    if poll_interval < 0:
        raise ValueError("poll_interval cannot be negative")

    writer = human_writer or AsyncHumanReadableWriter()
    resolved_serial = resolve_adb_serial(default_serial)
    if resolved_serial is None:
        raise RuntimeError("no OPPO ADB device is connected")

    pump: H264FramePump | None = None
    active_source = "png"
    fallback_reason: str | None = None
    if frame_source != "png":
        try:
            factory = frame_pump_factory or H264FramePump
            pump = factory("adb", resolved_serial)
            pump.start()
            active_source = "h264"
        except Exception as exc:
            if pump is not None:
                pump.stop()
                pump = None
            if frame_source == "h264":
                raise RuntimeError(f"failed to start H.264 frame source: {exc}") from exc
            fallback_reason = str(exc)

    ready = {
        "ready": True,
        "protocol": "duolingo-screen-reader/v1",
        "mode": "watch",
        "frame_source": active_source,
        "stable_frames": stable_frames,
    }
    if fallback_reason is not None:
        ready["fallback_reason"] = fallback_reason
    write_json_line(output_stream, ready)

    candidate_signature: tuple[object, ...] | None = None
    candidate_count = 0
    emitted_signature: tuple[object, ...] | None = None
    update_index = 0
    last_sequence = pump.sequence if pump is not None else 0

    try:
        while max_updates is None or update_index < max_updates:
            started_at = time.perf_counter()
            response_fallback: str | None = None
            if pump is not None:
                try:
                    image = pump.wait_for_frame(
                        after_sequence=last_sequence,
                        timeout=1.0,
                    )
                    last_sequence = pump.sequence
                except Exception as exc:
                    if frame_source == "h264":
                        raise
                    response_fallback = str(exc)
                    pump.stop()
                    pump = None
                    active_source = "png"
                    image = capture_adb_screenshot(resolved_serial)
            else:
                image = capture_adb_screenshot(resolved_serial)

            try:
                result = analyze_image(image, started_at=started_at)
            except ScoreNotVisibleError:
                result = {
                    "elapsed_ms": (time.perf_counter() - started_at) * 1000.0,
                    "screen_state": "no_score",
                    "notes": [],
                    "rests": [],
                    "events": [],
                }
            signature = watch_result_signature(result)
            if signature == candidate_signature:
                candidate_count += 1
            else:
                candidate_signature = signature
                candidate_count = 1

            if candidate_count >= stable_frames and signature != emitted_signature:
                update_index += 1
                response = {
                    "ok": True,
                    "update_index": update_index,
                    "frame_source": active_source,
                    "screen_state": result.get("screen_state", "score"),
                    **result,
                }
                if response_fallback is not None:
                    response["fallback_reason"] = response_fallback
                write_json_line(output_stream, response)
                emitted_signature = signature
                if (
                    human_readable_out is not None
                    and response["screen_state"] == "score"
                ):
                    writer.submit(human_readable_out, result["events"])

            if poll_interval:
                time.sleep(poll_interval)
    finally:
        if pump is not None:
            pump.stop()
        writer.close()


def serve_requests(
    input_stream: TextIO,
    output_stream: TextIO,
    default_serial: str | None = None,
    frame_source: str = "auto",
    frame_pump_factory: Callable[[str, str], H264FramePump] | None = None,
    default_human_readable_out: Path | None = None,
    human_writer: AsyncHumanReadableWriter | None = None,
) -> None:
    """Process newline-delimited JSON requests without reloading Python.

    Each request may contain ``image``, ``serial``, and ``out_annotated``.
    Omitting ``image`` captures the current ADB screen. A malformed request
    returns an error object and does not terminate the persistent process.
    """
    if frame_source not in {"auto", "h264", "png"}:
        raise ValueError(f"unsupported frame source: {frame_source}")

    writer = human_writer or AsyncHumanReadableWriter()
    pump: H264FramePump | None = None
    active_source = "png"
    fallback_reason: str | None = None
    resolved_serial = (
        resolve_adb_serial(default_serial)
        if frame_source != "png"
        else default_serial
    )
    if frame_source != "png" and resolved_serial is not None:
        try:
            factory = frame_pump_factory or H264FramePump
            pump = factory("adb", resolved_serial)
            pump.start()
            active_source = "h264"
        except Exception as exc:
            if pump is not None:
                pump.stop()
                pump = None
            if frame_source == "h264":
                raise RuntimeError(f"failed to start H.264 frame source: {exc}") from exc
            fallback_reason = str(exc)

    ready = {
        "ready": True,
        "protocol": "duolingo-screen-reader/v1",
        "frame_source": active_source,
    }
    if fallback_reason is not None:
        ready["fallback_reason"] = fallback_reason
    write_json_line(output_stream, ready)

    try:
        for line in input_stream:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise TypeError("request must be a JSON object")
                if request.get("command") == "quit":
                    write_json_line(output_stream, {"ok": True, "stopped": True})
                    return

                request_started = time.perf_counter()
                image_value = request.get("image")
                annotated_value = request.get("out_annotated")
                human_value = request.get("human_readable_out")
                annotated_path = (
                    Path(annotated_value) if annotated_value is not None else None
                )
                human_path = (
                    Path(human_value)
                    if human_value is not None
                    else default_human_readable_out
                )
                request_serial = request.get("serial") or resolved_serial
                response_source = "image" if image_value is not None else "png"
                response_fallback: str | None = None

                if image_value is not None:
                    result = analyze_request(
                        image_path=Path(image_value),
                        out_annotated=annotated_path,
                        started_at=request_started,
                    )
                elif pump is not None and request_serial == resolved_serial:
                    sequence = pump.sequence
                    try:
                        img = pump.wait_for_frame(
                            after_sequence=sequence,
                            timeout=1.0,
                        )
                        result = analyze_image(
                            img,
                            out_annotated=annotated_path,
                            started_at=request_started,
                        )
                        response_source = "h264"
                    except Exception as exc:
                        response_fallback = str(exc)
                        pump.stop()
                        pump = None
                        active_source = "png"
                        result = analyze_request(
                            serial=request_serial,
                            out_annotated=annotated_path,
                            started_at=request_started,
                        )
                else:
                    result = analyze_request(
                        serial=request_serial,
                        out_annotated=annotated_path,
                        started_at=request_started,
                    )

                response = {"ok": True, "frame_source": response_source, **result}
                if response_fallback is not None:
                    response["fallback_reason"] = response_fallback
                write_json_line(output_stream, response)
                if human_path is not None:
                    writer.submit(human_path, result["events"])
            except Exception as exc:
                write_json_line(
                    output_stream,
                    {
                        "ok": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
    finally:
        if pump is not None:
            pump.stop()
        writer.close()


def main():
    parser = argparse.ArgumentParser(
        description="Objective Duolingo Score Reader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Persistent mode reads one JSON object per line:
  python3 scripts/duolingo-read-screen-notes.py --serve --serial DEVICE
  {}
  {"image":"screen.png","human_readable_out":"notes.txt"}
  {"command":"quit"}
""",
    )
    parser.add_argument("--image", type=Path, help="Input PNG image path (if omitted, capture from adb)")
    parser.add_argument("--serial", type=str, default=None, help="ADB device serial")
    parser.add_argument("--out-annotated", type=Path, help="Path to save annotated visual image")
    parser.add_argument(
        "--human-readable-out",
        type=Path,
        default=DEFAULT_HUMAN_READABLE_OUTPUT,
        help=(
            "Asynchronously write a numbered human-readable list "
            "(default: duolingo-screen-notes.txt)"
        ),
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of markdown table")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--serve",
        action="store_true",
        help="Read newline-delimited JSON requests from stdin and keep dependencies loaded",
    )
    mode_group.add_argument(
        "--watch",
        action="store_true",
        help="Continuously emit JSON only when the recognized score changes",
    )
    parser.add_argument(
        "--stable-frames",
        type=int,
        default=2,
        help="Matching recognitions required before a watch update (default: 2)",
    )
    parser.add_argument(
        "--watch-interval-ms",
        type=float,
        default=50.0,
        help="Delay between watch analyses in milliseconds (default: 50)",
    )
    parser.add_argument(
        "--frame-source",
        choices=("auto", "h264", "png"),
        default="auto",
        help="Persistent-mode frame source (default: auto)",
    )
    args = parser.parse_args()

    if args.watch:
        if args.image is not None or args.out_annotated is not None:
            parser.error("--image and --out-annotated cannot be used with --watch")
        try:
            watch_screen_changes(
                sys.stdout,
                default_serial=args.serial,
                frame_source=args.frame_source,
                stable_frames=args.stable_frames,
                poll_interval=args.watch_interval_ms / 1000.0,
                human_readable_out=args.human_readable_out,
            )
        except KeyboardInterrupt:
            pass
        return

    if args.serve:
        if args.image is not None or args.out_annotated is not None:
            parser.error("--image and --out-annotated belong in each --serve request")
        serve_requests(
            sys.stdin,
            sys.stdout,
            default_serial=args.serial,
            frame_source=args.frame_source,
            default_human_readable_out=args.human_readable_out,
        )
        return

    result = analyze_request(
        image_path=args.image,
        serial=args.serial,
        out_annotated=args.out_annotated,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_markdown_table(result["events"], result["elapsed_ms"])
    sys.stdout.flush()

    if args.human_readable_out is not None:
        writer = AsyncHumanReadableWriter()
        writer.submit(args.human_readable_out, result["events"])
        writer.close()


if __name__ == "__main__":
    main()
