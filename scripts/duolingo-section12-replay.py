#!/usr/bin/env python3
"""Replay the pass-one score ledger for Duolingo music section 4.12.

The ledger stores musical facts (pitch, onset beat, duration beats).  This
script converts them to absolute DOWN/UP deadlines on one monotonic clock and
records both host send times and device acknowledgements for later audit.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
import threading
import time
from pathlib import Path


INPUT_BRIDGE = "/data/local/tmp/codex-input-bridge.jar"

KEYS = {
    "F4": (173, 600),
    "G4": (294, 600),
    "A4": (415, 600),
    "Bb4": (476, 475),
    "C5": (653, 600),
    "D5": (774, 600),
    "Eb5": (855, 475),
    "F5": (1053, 600),
}


@dataclasses.dataclass(frozen=True)
class Note:
    pitch: str
    onset: float
    duration: float


def notes(*rows: tuple[str, float, float]) -> tuple[Note, ...]:
    return tuple(Note(*row) for row in rows)


# E is always flattened by the two-flat key signature unless an explicit
# natural sign is present.  This ledger is reconstructed from the aligned
# pass-two H.264 stream.  Each entry stops at the next on-screen start prompt;
# notes visible beyond that prompt belong to the following phrase.
PHRASES = {
    1: notes(
        ("C5", 0, 1),
        ("Bb4", 6.5, 0.5), ("D5", 7, 0.5), ("Eb5", 7.5, 0.5),
        ("F5", 8, 1),
        ("Bb4", 10.5, 0.5), ("D5", 11, 0.5), ("Eb5", 11.5, 0.5),
        ("F5", 12, 1),
        ("D5", 13, 1), ("Bb4", 14, 1), ("D5", 15, 1),
        ("C5", 16, 2),
    ),
    2: notes(
        ("F5", 0, 1), ("D5", 1, 1), ("Bb4", 2, 1),
        # The visible C5 half note is the next phrase's start prompt.
        ("D5", 3, 1),
    ),
    3: notes(
        ("C5", 0, 2),
        ("D5", 2.5, 0.5), ("D5", 3, 0.5), ("C5", 3.5, 0.5),
        ("Bb4", 4, 1),
        ("Bb4", 5.5, 0.5), ("D5", 6, 0.5),
    ),
    4: notes(
        # This checkpoint starts on the third F in an overlapping F-F-F-Eb
        # group; it is not the start of an independent phrase.
        ("F5", 0, 0.5), ("Eb5", 0.5, 0.5),
        ("D5", 3, 0.5), ("Eb5", 3.5, 0.5),
        ("F5", 4, 1), ("D5", 5, 1), ("Bb4", 6, 1), ("D5", 7, 1),
        ("C5", 8, 2),
    ),
    5: notes(
        ("Bb4", 0, 2),
        ("Bb4", 2.5, 0.5), ("D5", 3, 0.5), ("Eb5", 3.5, 0.5),
        ("F5", 4, 1),
        ("Bb4", 6.5, 0.5), ("D5", 7, 0.5), ("Eb5", 7.5, 0.5),
        ("F5", 8, 1),
        ("D5", 9, 1), ("Bb4", 10, 1), ("D5", 11, 1),
        ("C5", 12, 2),
    ),
    6: notes(
        ("F5", 0, 2),
        ("Bb4", 2.5, 0.5), ("D5", 3, 0.5), ("Eb5", 3.5, 0.5),
        ("F5", 4, 1), ("D5", 5, 1), ("Bb4", 6, 1), ("D5", 7, 1),
        ("C5", 8, 2),
    ),
    7: notes(
        ("Bb4", 0, 0.5), ("A4", 0.5, 1),
        ("Bb4", 2, 0.5), ("C5", 2.5, 0.5),
        ("F5", 3.5, 0.5), ("F5", 4, 0.5),
        ("F5", 4.5, 0.5), ("Eb5", 5, 0.5),
        ("D5", 7.5, 0.5), ("Eb5", 8, 0.5),
        ("F5", 8.5, 1), ("D5", 9.5, 1), ("Bb4", 10.5, 1),
        ("C5", 11.5, 1), ("Bb4", 12.5, 2),
    ),
    8: notes(
        ("F5", 0, 1), ("D5", 1, 1), ("Bb4", 2, 1),
        ("D5", 3, 1), ("C5", 4, 2),
    ),
}


# One continuous reconstruction of the complete arrangement.  The on-screen
# recovery prompts are overlapping checkpoints inside this timeline, not
# independent phrases to concatenate in numerical order.
FULL_SCORE = notes(
    ("C5", 0, 1),

    ("Bb4", 6.5, 0.5), ("D5", 7, 0.5), ("Eb5", 7.5, 0.5),
    ("F5", 8, 1),
    ("Bb4", 10.5, 0.5), ("D5", 11, 0.5), ("Eb5", 11.5, 0.5),
    ("F5", 12, 1),
    ("Bb4", 14.5, 0.5), ("D5", 15, 0.5), ("Eb5", 15.5, 0.5),
    ("F5", 16, 1),
    ("D5", 17, 1), ("Bb4", 18, 1),
    ("D5", 19, 1), ("C5", 20, 2),

    ("D5", 22.5, 0.5), ("D5", 23, 0.5), ("C5", 23.5, 0.5),
    ("Bb4", 24, 1),
    ("Bb4", 25.5, 0.5), ("D5", 26, 0.5),
    ("F5", 27, 0.5), ("F5", 27.5, 0.5),
    ("F5", 28, 0.5), ("Eb5", 28.5, 0.5),
    ("D5", 31, 0.5), ("Eb5", 31.5, 0.5),
    ("F5", 32, 1), ("D5", 33, 1), ("Bb4", 34, 1),
    # D5 is a quarter note ending exactly where the Bb4 half-note checkpoint
    # begins.  The following phrase is anchored to that Bb4, so its first
    # eighth-note group starts at beat 38.5.
    ("D5", 35, 1), ("Bb4", 36, 2),

    ("Bb4", 38.5, 0.5), ("D5", 39, 0.5), ("Eb5", 39.5, 0.5),
    ("F5", 40, 1),
    ("Bb4", 42.5, 0.5), ("D5", 43, 0.5), ("Eb5", 43.5, 0.5),
    ("F5", 44, 1),
    # Pass 9 exposed a third pickup motif here.  The gray "D" timing bubble
    # appeared when the old ledger pressed D5 at beat 45, while the playhead
    # was visibly crossing a rest and the next Bb-D-Eb-F group was still to
    # its right.  This mirrors the three pickup motifs in the first half.
    ("Bb4", 46.5, 0.5), ("D5", 47, 0.5), ("Eb5", 47.5, 0.5),
    ("F5", 48, 1),
    ("D5", 49, 1), ("Bb4", 50, 1), ("D5", 51, 1),
    ("C5", 52, 2),

    # The pass-10 stream shows that the 16-beat middle section repeats here;
    # the previously scheduled F5 at beat 54 landed on its leading rest.  This
    # is the accepted beat-22.5 block transposed in time by exactly 32 beats.
    ("D5", 54.5, 0.5), ("D5", 55, 0.5), ("C5", 55.5, 0.5),
    ("Bb4", 56, 1),
    ("Bb4", 57.5, 0.5), ("D5", 58, 0.5),
    ("F5", 59, 0.5), ("F5", 59.5, 0.5),
    ("F5", 60, 0.5), ("Eb5", 60.5, 0.5),
    ("D5", 63, 0.5), ("Eb5", 63.5, 0.5),
    ("F5", 64, 1), ("D5", 65, 1), ("Bb4", 66, 1),
    ("D5", 67, 1), ("Bb4", 68, 2),

    ("F5", 70, 1), ("D5", 71, 1), ("Bb4", 72, 1),
    ("D5", 73, 1), ("C5", 74, 2),
)


def phrase_notes(number: int) -> tuple[Note, ...]:
    return PHRASES[number]


class DeviceInput:
    def __init__(self, adb: str, serial: str) -> None:
        self._acks: dict[int, int] = {}
        self._condition = threading.Condition()
        self._process = subprocess.Popen(
            [
                adb,
                "-s",
                serial,
                "shell",
                "-t",
                f"CLASSPATH={INPUT_BRIDGE} app_process /system/bin CodexInputBridge",
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
            if match:
                with self._condition:
                    self._acks[int(match.group(1))] = time.monotonic_ns()
                    self._condition.notify_all()

    def send(self, kind: str, pitch: str, sequence: int) -> int:
        assert self._process.stdin is not None
        x, y = KEYS[pitch]
        sent_ns = time.monotonic_ns()
        self._process.stdin.write(f"{kind} {x} {y} {sequence}\n")
        self._process.stdin.flush()
        return sent_ns

    def wait_for_ack(self, sequence: int, timeout: float = 2.0) -> int:
        deadline = time.monotonic() + timeout
        with self._condition:
            while sequence not in self._acks:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"device did not acknowledge action {sequence}")
                self._condition.wait(remaining)
            return self._acks[sequence]

    def close(self) -> dict[int, int]:
        assert self._process.stdin is not None
        self._process.stdin.write("exit\n")
        self._process.stdin.flush()
        self._process.stdin.close()
        self._process.wait(timeout=3)
        self._reader.join(timeout=1)
        return dict(self._acks)


def play(args: argparse.Namespace) -> dict[str, object]:
    score = FULL_SCORE if args.full else phrase_notes(args.phrase)
    selection: int | str = "full" if args.full else args.phrase
    seconds_per_beat = 60.0 / args.bpm
    input_device = DeviceInput(args.adb, args.serial)
    if not score:
        raise ValueError(f"selection {selection} has no notes")

    # The first injection also starts Duolingo's musical clock.  Its shell-to-
    # device latency varies by more than 100 ms, so wait for the ACK and use it
    # as the shared origin for the first release and every later note.
    first_note = score[0]
    first_deadline_ns = time.monotonic_ns() + int(args.pre_roll_ms * 1_000_000)
    while True:
        remaining_ns = first_deadline_ns - time.monotonic_ns()
        if remaining_ns <= 0:
            break
        time.sleep(min(remaining_ns / 1_000_000_000, 0.003))
    first_sent_ns = input_device.send("DOWN", first_note.pitch, 0)
    musical_anchor_ns = input_device.wait_for_ack(0)
    records: list[dict[str, object]] = [
        {
            "sequence": 0,
            "kind": "DOWN",
            "pitch": first_note.pitch,
            "deadline_ns": first_deadline_ns,
            "sent_ns": first_sent_ns,
            "send_lateness_ms": (first_sent_ns - first_deadline_ns) / 1_000_000,
        }
    ]

    actions: list[tuple[int, int, str, str, float]] = []
    sequence = 1
    phase_seconds = args.after_prompt_phase_ms / 1000.0
    release_advance = args.release_advance_ms / 1000.0
    actions.append(
        (
            sequence,
            0,
            "UP",
            first_note.pitch,
            first_note.duration * seconds_per_beat - release_advance,
        )
    )
    sequence += 1

    for note in score[1:]:
        down_seconds = note.onset * seconds_per_beat + phase_seconds
        release_advance = args.release_advance_ms / 1000.0
        up_seconds = (
            (note.onset + note.duration) * seconds_per_beat
            + phase_seconds
            - release_advance
        )
        actions.append((sequence, 1, "DOWN", note.pitch, down_seconds))
        sequence += 1
        actions.append((sequence, 0, "UP", note.pitch, up_seconds))
        sequence += 1

    actions.sort(key=lambda row: (row[4], row[1]))  # UP precedes DOWN on ties.
    for action_sequence, _, kind, pitch, offset_seconds in actions:
        deadline_ns = musical_anchor_ns + int(offset_seconds * 1_000_000_000)
        while True:
            remaining_ns = deadline_ns - time.monotonic_ns()
            if remaining_ns <= 0:
                break
            time.sleep(min(remaining_ns / 1_000_000_000, 0.003))
        sent_ns = input_device.send(kind, pitch, action_sequence)
        records.append(
            {
                "sequence": action_sequence,
                "kind": kind,
                "pitch": pitch,
                "deadline_ns": deadline_ns,
                "sent_ns": sent_ns,
                "send_lateness_ms": (sent_ns - deadline_ns) / 1_000_000,
            }
        )

    acks = input_device.close()
    for record in records:
        ack_ns = acks.get(int(record["sequence"]))
        record["ack_ns"] = ack_ns
        record["ack_latency_ms"] = (
            None if ack_ns is None else (ack_ns - int(record["sent_ns"])) / 1_000_000
        )

    result = {
        "selection": selection,
        "bpm": args.bpm,
        "after_prompt_phase_ms": args.after_prompt_phase_ms,
        "release_advance_ms": args.release_advance_ms,
        "first_deadline_ns": first_deadline_ns,
        "musical_anchor_ns": musical_anchor_ns,
        "score": [dataclasses.asdict(note) for note in score],
        "actions": records,
    }
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--phrase", type=int, choices=range(1, 9))
    selection.add_argument(
        "--full",
        action="store_true",
        help="play the reconstructed continuous arrangement",
    )
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--bpm", type=float, default=80.0)
    parser.add_argument(
        "--after-prompt-phase-ms",
        type=float,
        default=0.0,
        help="optional phase applied after the first device ACK (default: 0)",
    )
    parser.add_argument("--release-advance-ms", type=float, default=20.0)
    parser.add_argument("--pre-roll-ms", type=float, default=250.0)
    return parser.parse_args()


if __name__ == "__main__":
    options = parse_args()
    print(json.dumps(play(options), ensure_ascii=False, indent=2))
