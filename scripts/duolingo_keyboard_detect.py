"""Detect the on-screen piano keyboard layout directly from a Duolingo frame.

Every lesson re-uses the same physical key grid but re-anchors the pitches, so a
hard-coded table is only ever correct for the lesson it was measured on. This
module reads the layout off the screen instead:

1. Black keys are found as dark blobs and clustered into the piano's natural
   groups of three and two. A group of three always straddles F-G-A-B and a
   group of two always straddles C-D-E, so the letters follow from geometry
   alone -- no text recognition is involved.
2. Duolingo prints a letter plus an optional octave arrow on each key the song
   actually uses. The arrow glyph is a fixed 32x28 and is told apart from a
   letter by size; its direction comes from whether the wide end of the head
   sits at the top or the bottom. Unmarked means octave 4, up means 5, down
   means 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import subprocess

import numpy as np
from PIL import Image
import scipy.ndimage

SHARP_OF = {"C": "Db", "D": "Eb", "F": "Gb", "G": "Ab", "A": "Bb"}
ARROW_SUFFIX = {"up": "↑", "down": "↓", None: ""}
GROUP_LETTERS = {3: ("F", "G", "A", "B"), 2: ("C", "D", "E")}
HOME_OCTAVE = 4


class KeyboardNotDetectedError(RuntimeError):
    """Raised when the frame does not show a usable keyboard."""


@dataclass
class WhiteKey:
    letter: str
    x: int
    group: int = 0
    octave: int | None = None
    labeled: bool = False
    arrow: str | None = None      # "up" | "down" | None


@dataclass
class KeyboardLayout:
    keys: dict[str, tuple[int, int]]
    labels: dict[str, str]
    white_y: int
    black_y: int
    white_keys: list[WhiteKey] = field(default_factory=list)
    group_sizes: tuple[int, ...] = ()
    unlabeled: tuple[str, ...] = ()

    def target(self, pitch: str) -> tuple[int, int] | None:
        return self.keys.get(pitch)

    def label(self, pitch: str) -> str:
        return self.labels.get(pitch, pitch)

    def require(self, pitch: str) -> tuple[int, int]:
        """Return the key target, refusing to guess one the app never labeled."""
        target = self.keys.get(pitch)
        if target is None:
            raise KeyError(
                f"{pitch} has no key on this lesson's keyboard "
                f"(labeled keys: {', '.join(sorted(self.keys))})"
            )
        return target


def _black_key_blobs(lum: np.ndarray) -> list[tuple[float, float, int, int]]:
    h = lum.shape[0]
    y0, y1 = int(h * 0.55), int(h * 0.78)
    labels, _ = scipy.ndimage.label(lum[y0:y1] < 110)
    blobs = []
    for sl in scipy.ndimage.find_objects(labels):
        ys, xs = sl
        bw, bh = xs.stop - xs.start, ys.stop - ys.start
        # A key is a wide, squat rounded rect; the screen's side chrome is not.
        if 60 <= bw <= 130 and 55 <= bh <= 140:
            blobs.append(((xs.start + xs.stop) / 2, y0 + (ys.start + ys.stop) / 2, bw, bh))
    blobs.sort()
    return blobs


def _cluster_groups(blacks) -> list[list]:
    if len(blacks) < 2:
        raise KeyboardNotDetectedError(f"need >=2 black keys, found {len(blacks)}")
    gaps = [blacks[i + 1][0] - blacks[i][0] for i in range(len(blacks) - 1)]
    inner = float(np.median(gaps))
    groups, cur = [], [blacks[0]]
    for i, gap in enumerate(gaps):
        if gap > inner * 1.6:
            groups.append(cur)
            cur = [blacks[i + 1]]
        else:
            cur.append(blacks[i + 1])
    groups.append(cur)
    for g in groups:
        if len(g) not in GROUP_LETTERS:
            raise KeyboardNotDetectedError(
                f"black-key group of {len(g)} is not a piano pattern "
                f"(sizes: {[len(x) for x in groups]})"
            )
    for a, b in zip(groups, groups[1:]):
        if len(a) == len(b):
            raise KeyboardNotDetectedError(
                f"black-key groups must alternate 3/2, got {[len(x) for x in groups]}"
            )
    return groups


def _white_keys_from_groups(groups) -> tuple[list[WhiteKey], float]:
    """A group's blacks sit between its whites, so whites are blacks +/- half a step."""
    spacings = [
        g[i + 1][0] - g[i][0] for g in groups for i in range(len(g) - 1)
    ]
    step = float(np.median(spacings))
    half = step / 2.0
    whites: list[WhiteKey] = []
    for index, group in enumerate(groups):
        letters = GROUP_LETTERS[len(group)]
        xs = [group[0][0] - half] + [b[0] + half for b in group]
        for letter, x in zip(letters, xs):
            whites.append(WhiteKey(letter=letter, x=int(round(x)), group=index))
    return whites, step


def _read_octave_labels(lum: np.ndarray, whites: list[WhiteKey], step: float) -> None:
    h = lum.shape[0]
    y0, y1 = int(h * 0.82), int(h * 0.95)
    labels, _ = scipy.ndimage.label(lum[y0:y1] < 200)
    glyphs = []
    for sl in scipy.ndimage.find_objects(labels):
        ys, xs = sl
        bw, bh = xs.stop - xs.start, ys.stop - ys.start
        if bw < 6 or bh < 10 or bw > 90:
            continue
        glyphs.append({
            "cx": (xs.start + xs.stop) / 2,
            "w": bw, "h": bh,
            "mask": (lum[y0:y1] < 200)[ys, xs],
        })
    for key in whites:
        near = [g for g in glyphs if abs(g["cx"] - key.x) < step * 0.52]
        if not near:
            continue
        key.labeled = True
        for g in near:
            # The arrow is markedly wider than any letter glyph.
            if not (26 <= g["w"] <= 42 and 22 <= g["h"] <= 36):
                continue
            m = g["mask"]
            top = m[: m.shape[0] // 2].sum(axis=1).max()
            bot = m[m.shape[0] // 2 :].sum(axis=1).max()
            key.arrow = "up" if top > bot else "down"
        key.octave = HOME_OCTAVE + (1 if key.arrow == "up" else -1 if key.arrow == "down" else 0)


def _share_octave_within_groups(whites: list[WhiteKey]) -> None:
    """Give every key in a black-key group the octave its labelled siblings show.

    Groups are exactly C-D-E and F-G-A-B, and octaves start at C, so the white
    keys inside one group always share an octave.  Duolingo hides a key's label
    while the key is highlighted, and without this a momentary highlight would
    drop that key from the map entirely.
    """
    by_group: dict[int, list[WhiteKey]] = {}
    for key in whites:
        by_group.setdefault(key.group, []).append(key)
    for members in by_group.values():
        octaves = {k.octave for k in members if k.octave is not None}
        if len(octaves) != 1:
            continue
        octave = octaves.pop()
        arrow = next((k.arrow for k in members if k.octave is not None), None)
        for key in members:
            if key.octave is None:
                key.octave = octave
                key.arrow = arrow
                key.labeled = True


def _fill_unlabeled(whites: list[WhiteKey], policy: str) -> list[str]:
    """Assign octaves to keys Duolingo left unlabeled. See `detect_keyboard`."""
    unresolved: list[str] = []
    if policy == "unmapped":
        return [f"{k.letter}?@{k.x}" for k in whites if k.octave is None]
    order = "CDEFGAB"
    anchor = next((i for i, k in enumerate(whites) if k.octave is not None), None)
    if anchor is None:
        raise KeyboardNotDetectedError("no labeled key to anchor the octave")
    for i in range(anchor - 1, -1, -1):
        nxt = whites[i + 1]
        whites[i].octave = nxt.octave - (1 if order.index(whites[i].letter) > order.index(nxt.letter) else 0)
    for i in range(anchor + 1, len(whites)):
        prv = whites[i - 1]
        whites[i].octave = prv.octave + (1 if order.index(whites[i].letter) < order.index(prv.letter) else 0)
    return unresolved


def detect_keyboard(
    rgb: np.ndarray,
    *,
    unlabeled_policy: str = "unmapped",
) -> KeyboardLayout:
    """Read the keyboard layout from one RGB frame.

    `unlabeled_policy` controls keys the app printed no label on:
      "extrapolate" - continue the letter sequence so every key gets a pitch.
      "unmapped"    - leave them out, so asking for one raises instead of
                      tapping a plausible-looking wrong key.
    """
    if unlabeled_policy not in ("unmapped", "extrapolate"):
        raise ValueError(f"unknown unlabeled_policy: {unlabeled_policy!r}")
    lum = rgb.astype(np.int16).mean(axis=2)
    blacks = _black_key_blobs(lum)
    groups = _cluster_groups(blacks)
    whites, step = _white_keys_from_groups(groups)
    _read_octave_labels(lum, whites, step)
    _share_octave_within_groups(whites)
    unresolved = _fill_unlabeled(whites, unlabeled_policy)

    black_cy = float(np.median([b[1] for b in blacks]))
    black_h = float(np.median([b[3] for b in blacks]))
    white_y = int(round(black_cy + black_h / 2 + 85))
    black_y = int(round(black_cy))

    keys: dict[str, tuple[int, int]] = {}
    labels: dict[str, str] = {}
    for key in whites:
        if key.octave is None:
            continue
        pitch = f"{key.letter}{key.octave}"
        keys[pitch] = (key.x, white_y)
        labels[pitch] = f"{key.letter}{ARROW_SUFFIX[key.arrow]}"
    for group in groups:
        for black in group:
            left = max(
                (w for w in whites if w.x < black[0]), key=lambda w: w.x, default=None
            )
            if left is None or left.octave is None or left.letter not in SHARP_OF:
                continue
            pitch = f"{SHARP_OF[left.letter]}{left.octave}"
            target = (int(round(black[0])), black_y)
            keys[pitch] = target
            labels[pitch] = f"{SHARP_OF[left.letter]}{ARROW_SUFFIX[left.arrow]}"
            # The same black key may be written as a sharp by the score.
            sharp_pitch = f"{left.letter}#{left.octave}"
            keys[sharp_pitch] = target
            labels[sharp_pitch] = f"{left.letter}#{ARROW_SUFFIX[left.arrow]}"

    return KeyboardLayout(
        keys=keys,
        labels=labels,
        white_y=white_y,
        black_y=black_y,
        white_keys=whites,
        group_sizes=tuple(len(g) for g in groups),
        unlabeled=tuple(unresolved),
    )


def capture_device_frame(serial: str | None, adb: str = "adb") -> np.ndarray:
    """Grab one RGB frame from the device for layout detection."""
    cmd = [adb]
    if serial:
        cmd += ["-s", serial]
    cmd += ["exec-out", "screencap", "-p"]
    raw = subprocess.run(cmd, stdout=subprocess.PIPE, check=True).stdout
    with Image.open(io.BytesIO(raw)) as frame:
        return np.asarray(frame.convert("RGB"))


def resolve_key_points(
    *,
    serial: str | None,
    adb: str = "adb",
    profile: str | None = None,
    profiles: dict[str, dict[str, tuple[int, int]]] | None = None,
) -> dict[str, tuple[int, int]]:
    """Return this lesson's pitch->key map, reading it off the device by default.

    A stored `profile` is honoured only when the caller names one explicitly;
    it exists as an escape hatch for frames where detection cannot run, not as
    a default, because a table measured on one lesson taps the wrong key on the
    next.
    """
    if profile:
        if not profiles or profile not in profiles:
            raise KeyError(f"unknown keyboard profile: {profile!r}")
        return dict(profiles[profile])
    return dict(detect_keyboard(capture_device_frame(serial, adb)).keys)
