#!/usr/bin/env python3
"""Build auditable score facts from a completed Duolingo live run.

The sent keys supply the note sequence; the multi-frame ledger supplies note
lengths.  A mismatch is an error rather than a silently invented score event.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re


_PITCH = re.compile(r"^([A-G])([b#]?)([0-9]+)$")
_BASE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi_number(pitch: str) -> int:
    match = _PITCH.fullmatch(pitch)
    if match is None:
        raise ValueError(f"invalid played pitch: {pitch!r}")
    letter, accidental, octave = match.groups()
    return (int(octave) + 1) * 12 + _BASE[letter] + (
        -1 if accidental == "b" else 1 if accidental == "#" else 0
    )


def score_events(played: list[dict], ledger_notes: list[dict]) -> list[tuple[float, str, float]]:
    """Join each real key press to exactly one corroborated score duration."""
    events = []
    seen_beats: set[float] = set()
    for sent in played:
        beat = float(sent["beat"])
        if beat in seen_beats:
            raise ValueError(f"played beat {beat:g} twice; inspect prompt restarts")
        seen_beats.add(beat)
        read_pitch = sent.get("read_pitch", sent["pitch"])
        matches = [note for note in ledger_notes
                   if abs(float(note["beat"]) - beat) < 0.01
                   and note["pitch"] == read_pitch]
        # The player marks preloaded notes with 100 synthetic sightings.
        # Prefer any observations made on this run's opening screen; the seed
        # may have an old, incorrect articulation even when its pitch is right.
        live_matches = [note for note in matches if note.get("sightings") != 100]
        if live_matches:
            matches = live_matches
        durations = {float(note["duration_beats"]) for note in matches
                     if note["duration_beats"] is not None}
        if len(durations) != 1 or any(note["duration_beats"] is None for note in matches):
            raise ValueError(f"no unique ledger duration for beat {beat:g} {read_pitch}")
        duration = durations.pop()
        if duration <= 0:
            raise ValueError(f"nonpositive duration at beat {beat:g}")
        midi_number(sent["pitch"])
        events.append((beat, sent["pitch"], duration))
    events.sort()
    for before, after in zip(events, events[1:]):
        if before[0] + before[2] > after[0] + 0.01:
            raise ValueError(f"overlapping notes at beats {before[0]:g} and {after[0]:g}")
    return events


def measure_rows(
    events: list[tuple[float, str, float]], beats_per_measure: int,
) -> list[tuple[int, float, float, list[tuple[str, float, float]]]]:
    """Return note/rest events from beat zero through the last note's release."""
    if not events or beats_per_measure <= 0:
        raise ValueError("nonempty score and positive measure length required")
    end = max(beat + duration for beat, _, duration in events)
    rows = []
    start = 0.0
    while start < end - 0.01:
        stop = min(start + beats_per_measure, end)
        row = []
        cursor = start
        for beat, pitch, duration in events:
            if not start <= beat < stop:
                continue
            if beat > cursor + 0.01:
                row.append(("R", cursor, beat - cursor))
            row.append((pitch, beat, duration))
            cursor = max(cursor, beat + duration)
        if cursor < stop - 0.01:
            row.append(("R", cursor, stop - cursor))
        rows.append((len(rows) + 1, start, stop, row))
        start += beats_per_measure
    return rows


def format_pitch(pitch: str) -> str:
    return pitch.replace("b", "♭").replace("#", "♯")


def render_report(run: Path) -> str:
    played = json.loads((run / "played.json").read_text(encoding="utf-8"))
    ledger = json.loads((run / "ledger.json").read_text(encoding="utf-8"))
    events = score_events(played, ledger["notes"])
    if not events:
        raise ValueError("run contains no formal notes")
    beats_per_measure = int(ledger["summary"]["grid"]["beats_per_measure"])
    rows = measure_rows(events, beats_per_measure)
    low = min(events, key=lambda event: midi_number(event[1]))[1]
    high = max(events, key=lambda event: midi_number(event[1]))[1]
    pitch_counts = Counter(pitch for _, pitch, _ in events)
    durations = Counter(duration for _, _, duration in events)
    lines = [
        f"正式音 {len(events)} 个；音域 {format_pitch(low)}–{format_pitch(high)}；"
        + "时值 " + ", ".join(f"{duration:g} 拍×{count}"
                              for duration, count in sorted(durations.items())),
        "",
        "| 小节 | 谱面 beat | 音符与休止 |",
        "|---:|---:|---|",
    ]
    if events[0][0] < 0:
        pickup = [(beat, pitch, duration) for beat, pitch, duration in events if beat < 0]
        lines.append("| 弱起 | " + f"{pickup[0][0]:g}–0 | " + ", ".join(
            f"{format_pitch(pitch)}({duration:g})" for _, pitch, duration in pickup
        ) + " |")
    for number, start, stop, row in rows:
        content = ", ".join(
            f"R{duration:g}" if pitch == "R" else f"{format_pitch(pitch)}({duration:g})"
            for pitch, _, duration in row
        )
        lines.append(f"| {number} | {start:g}–{stop:g} | {content} |")
    lines.extend([
        "",
        "纯音符顺序：",
        "",
        "`" + ", ".join(format_pitch(pitch) for _, pitch, _ in events) + "`",
        "",
        "音高次数：" + ", ".join(
            f"{format_pitch(pitch)}×{count}" for pitch, count in sorted(pitch_counts.items())
        ) + "。",
        f"最后音：beat {events[-1][0]:g} {format_pitch(events[-1][1])}({events[-1][2]:g})。",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="completed run with ledger.json and played.json")
    parser.add_argument("--output", type=Path, help="write Markdown report here instead of stdout")
    args = parser.parse_args()
    report = render_report(args.run)
    if args.output is None:
        print(report, end="")
    else:
        args.output.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
