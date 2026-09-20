#!/usr/bin/env python3
"""Objective full-score reader for Duolingo Music screen.

Locates the 5 staff lines, detects all noteheads at and to the right of the
judgment line, measures their precise geometric centers, determines pitch,
key-signature accidentals, note durations (including augmentation dots), and outputs
a structured ledger with pitch, physical key mapping, and relative timing (hold & delta).
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import scipy.ndimage
import scipy.signal


KEY_COORDINATES = {
    # Low octave (arrow down): y = 600
    "A3": (294, 600),
    "B3": (415, 600),
    # Middle octave: y = 600
    "C4": (536, 600),
    "D4": (670, 600),
    "E4": (794, 600),
    "F4": (915, 600),
    "G4": (1049, 600),
    "A4": (1173, 600),
    "B4": (1294, 600),
    "C5": (1415, 600),
    # High octave (arrow up)
    "D5": (1255, 600),
    "E5": (1388, 600),
    # Black keys: y = 475
    "Bb3": (355, 475),
    "Db4": (245, 475),
    "Eb4": (378, 475),
    "Gb4": (660, 475),
    "Ab4": (793, 475),
    "Bb4": (926, 475),
    "Db5": (1208, 475),
    "Eb5": (1341, 475),
}

KEY_DISPLAY_LABELS = {
    "A3": "A↓",
    "B3": "B↓",
    "Bb3": "Bb↓",
    "C4": "C",
    "D4": "D",
    "E4": "E",
    "F4": "F",
    "G4": "G",
    "A4": "A",
    "B4": "B",
    "C5": "C↑",
    "D5": "D↑",
    "E5": "E↑",
    "Bb4": "Bb",
}


def capture_adb_screenshot(serial: str | None = None) -> Image.Image:
    if not serial:
        # Check connected devices
        out = subprocess.run(["adb", "devices"], stdout=subprocess.PIPE, text=True, check=True).stdout
        devices = [line.split()[0] for line in out.strip().splitlines()[1:] if "\tdevice" in line]
        if len(devices) == 1:
            serial = devices[0]
        elif len(devices) > 1:
            # Prefer OPPO port or tls connect if available
            oppo_devs = [d for d in devices if d != "192.168.10.100:5555"]
            serial = oppo_devs[0] if oppo_devs else devices[0]

    cmd = ["adb"]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(["exec-out", "screencap", "-p"])
    raw = subprocess.run(cmd, stdout=subprocess.PIPE, check=True).stdout
    return Image.open(io.BytesIO(raw)).convert("RGB")


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
    threshold = max(120.0, float(continuity.max()) * 0.65)
    labels, count = scipy.ndimage.label(continuity >= threshold)
    best_columns: np.ndarray | None = None
    best_weight = -1.0
    for label_id in range(1, count + 1):
        columns = np.where(labels == label_id)[0]
        if len(columns) < 5:
            continue
        weight = float(continuity[columns].sum())
        if weight > best_weight:
            best_columns = columns
            best_weight = weight
    if best_columns is not None:
        center = np.average(best_columns, weights=continuity[best_columns])
        return x0 + int(round(float(center)))

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
    dark = (arr < 130).all(axis=2)

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
                center_y - radius_y : center_y + radius_y + 1,
                center_x - radius_x : center_x + radius_x + 1,
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
    region = arr[125:345, 195:315]
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
    img: Image.Image,
    min_x: int | None = None,
    max_x: int = 1520,
) -> list[dict]:
    """Detect Duolingo rest glyphs at and to the right of the judgment line."""
    arr = np.array(img.convert("RGB"))
    line_5_y, line_4_y, line_3_y, _line_2_y, line_1_y = find_staff_lines(arr)
    if min_x is None:
        min_x = max(0, locate_judgment_line(arr) - 10)

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
        })

    return sorted(rests, key=lambda rest: rest["x"])


def analyze_screen_notes(
    img: Image.Image,
    min_x: int | None = None,
    max_x: int = 1520,
    has_flat_key_sig: bool = False,
    annotated_output_path: Path | None = None,
) -> list[dict]:
    arr = np.array(img.convert("RGB"))
    h, w, _ = arr.shape

    # Detect judgment line if min_x is not explicitly provided
    judgment_line_x = locate_judgment_line(arr)
    if min_x is None:
        # Start right at the judgment line (with a slight margin to capture notehead on/at the line)
        min_x = max(0, judgment_line_x - 10)

    flat_count = detect_flat_key_signature_count(arr)
    if has_flat_key_sig:
        flat_count = max(flat_count, 1)
    flat_pitch_classes = set(("B", "E", "A", "D", "G", "C", "F")[:flat_count])

    def signed_pitch(natural_pitch: str) -> str:
        return (
            f"{natural_pitch[0]}b{natural_pitch[1:]}"
            if natural_pitch[0] in flat_pitch_classes
            else natural_pitch
        )

    # 1. Staff lines: line 5 (top) to line 1 (bottom)
    line_5_y, line_4_y, line_3_y, line_2_y, line_1_y = find_staff_lines(arr)
    step_y = (line_1_y - line_5_y) / 4.0
    staff_ys = [line_5_y, line_4_y, line_3_y, line_2_y, line_1_y]
    staff_right_x = find_staff_right_edge(arr, staff_ys)

    positions = {
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
    search_top = int(line_5_y - 25)
    search_bottom = int(line_1_y + 2.5 * step_y + 35)

    dark = (arr[search_top:search_bottom, :] < 130).all(axis=2).astype(float)
    r = 14
    y_grid, x_grid = np.ogrid[-r:r+1, -r:r+1]
    disk = (x_grid**2 + y_grid**2 <= r**2).astype(float)
    ring = ((x_grid**2 + y_grid**2 <= r**2) & (x_grid**2 + y_grid**2 >= (r-5)**2)).astype(float)

    corr_disk = scipy.signal.correlate2d(dark, disk, mode="same") / disk.sum()
    corr_ring = scipy.signal.correlate2d(dark, ring, mode="same") / ring.sum()
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

    peaks_x, _ = scipy.signal.find_peaks(pitch_score[min_x:max_x], height=0.75, distance=45)
    raw_candidate_xs = [min_x + int(px) for px in peaks_x]
    candidate_xs = suppress_close_candidates(raw_candidate_xs, pitch_score)

    # 3. For each notehead X, extract true circular blob center
    notes = []
    vis = img.copy().convert("RGB") if annotated_output_path else None
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
    stems = [
        detect_note_stem(glyph_labels, component_label, note["x"], note["y"])
        for note, component_label in zip(notes, component_labels)
    ]
    stems = [
        stem
        if stem is not None
        else detect_judgment_occluded_stem(
            arr, note["x"], note["y"], judgment_line_x
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

        note["key_target"] = KEY_COORDINATES.get(note["pitch"])
        note["key_label"] = KEY_DISPLAY_LABELS.get(note["pitch"], note["pitch"])

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


def print_markdown_table(events: list[dict], elapsed_ms: float) -> None:
    print(f"\n### 屏幕识别乐谱事件与相对时间结果 (耗时: {elapsed_ms:.1f} ms)")
    print("| 序号 | 类型 | 坐标 (X, Y) | 几何位置 | 音名 | 对应琴键坐标 | 键位标注 | 时值类型 | 按住拍数 (hold) | 相对间隔 (delta) |")
    print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for idx, event in enumerate(events, 1):
        coord_str = (
            f"({event['key_target'][0]}, {event['key_target'][1]})"
            if event["key_target"]
            else "—"
        )
        pitch = event["pitch"] or "休止"
        event_label = "音符" if event["event_type"] == "note" else "休止符"
        hold = f"{event['hold_beats']} 拍" if event["hold_beats"] is not None else "未知"
        delta = f"{event['delta_beats']} 拍" if event["delta_beats"] is not None else "未知"
        print(
            f"| {idx} | {event_label} | ({event['x']}, {event['y']}) | {event['position']} | "
            f"**{pitch}** | {coord_str} | `{event['key_label']}` | {event['duration_type']} | "
            f"{hold} | **{delta}** |"
        )


def main():
    parser = argparse.ArgumentParser(description="Objective Duolingo Score Reader")
    parser.add_argument("--image", type=Path, help="Input PNG image path (if omitted, capture from adb)")
    parser.add_argument("--serial", type=str, default=None, help="ADB device serial")
    parser.add_argument("--out-annotated", type=Path, help="Path to save annotated visual image")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of markdown table")
    args = parser.parse_args()

    t0 = time.perf_counter()

    if args.image:
        img = Image.open(args.image).convert("RGB")
    else:
        img = capture_adb_screenshot(args.serial)

    notes = analyze_screen_notes(
        img,
        annotated_output_path=args.out_annotated,
    )
    rests = analyze_screen_rests(img)
    events = sorted([*notes, *rests], key=lambda event: event["x"])
    if args.out_annotated:
        annotate_rests(args.out_annotated, rests)

    t1 = time.perf_counter()
    elapsed_ms = (t1 - t0) * 1000.0

    if args.json:
        print(json.dumps(
            {"elapsed_ms": elapsed_ms, "notes": notes, "rests": rests, "events": events},
            indent=2,
            ensure_ascii=False,
        ))
    else:
        print_markdown_table(events, elapsed_ms)


if __name__ == "__main__":
    main()
