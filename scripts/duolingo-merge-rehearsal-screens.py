#!/usr/bin/env python3
"""Join overlapping stopped-screen Duolingo runs into one checked score seed.

Each run's local beat zero belongs to its own stopped prompt.  A failed note
may rewind the next prompt by a measure, so offsets must come from shared
score events rather than the number of notes the previous run sent.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def read_run(path: Path) -> dict:
    ledger = json.loads((path / "ledger.json").read_text())
    played = json.loads((path / "played.json").read_text())
    summary = ledger["summary"]
    by_beat = defaultdict(list)
    for note in ledger["notes"]:
        by_beat[float(note["beat"])].append(note)
    starter = summary["start_note"]
    sent = [starter] + [note for note in played if not note.get("prompt_restart")]
    events = []
    seen = set()
    for note in sent:
        beat, pitch = float(note["beat"]), note["pitch"]
        if (beat, pitch) in seen:
            continue
        seen.add((beat, pitch))
        score = next((candidate for candidate in by_beat[beat]
                      if candidate["pitch"] == pitch), None)
        if score is None:
            raise ValueError(f"{path}: sent {pitch} at {beat} is missing from ledger")
        events.append(score)
    events.sort(key=lambda note: note["beat"])
    return {"path": path, "summary": summary, "ledger": by_beat, "events": events}


def alignment_candidates(previous: dict, following: dict) -> list[tuple[float, float, int]]:
    """Return (score, local-beat shift, matches) for plausible overlaps."""
    first = following["events"][0]
    candidates = set()
    for beat, notes in previous["ledger"].items():
        if any(note["pitch"] == first["pitch"] for note in notes):
            shift = beat - float(first["beat"])
            if 0 < shift <= 16:
                candidates.add(shift)
    ranked = []
    for shift in candidates:
        score = 0.0
        matches = 0
        for note in following["events"]:
            if float(note["beat"]) - float(first["beat"]) >= 8:
                break
            old = previous["ledger"].get(float(note["beat"]) + shift, [])
            if not old:
                continue
            same = next((item for item in old if item["pitch"] == note["pitch"]), None)
            if same is None:
                score -= 1.5
            else:
                matches += 1
                score += 1.0
                if abs(float(same["duration_beats"])
                       - float(note["duration_beats"])) < 0.01:
                    score += 0.25
        ranked.append((score, shift, matches))
    return sorted(ranked, reverse=True)


def merge(runs: list[dict], first_global_beat: float,
          prefix: Path | None = None,
          advances: dict[int, float] | None = None) -> tuple[list[dict], list[dict]]:
    offsets = [first_global_beat - float(runs[0]["events"][0]["beat"])]
    alignments = []
    for pair_index, (previous, following) in enumerate(zip(runs, runs[1:]), 1):
        ranked = alignment_candidates(previous, following)
        specified = (advances or {}).get(pair_index)
        if specified is not None:
            selected = next((row for row in ranked if row[1] == specified), None)
            if selected is None or selected[2] < 3:
                raise ValueError(f"pair {pair_index}: specified advance {specified} "
                                 f"does not have three matching notes: {ranked[:3]}")
        else:
            selected = ranked[0] if ranked else None
        if selected is None or selected[2] < 3:
            raise ValueError(f"{previous['path']} -> {following['path']}: "
                             f"fewer than three matching overlap notes: {ranked[:3]}")
        if specified is None and len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 2:
            raise ValueError(f"{previous['path']} -> {following['path']}: "
                             f"ambiguous overlap: {ranked[:3]}")
        score, shift, matches = selected
        offsets.append(offsets[-1] + shift)
        alignments.append({"from": str(previous["path"]),
                           "to": str(following["path"]),
                           "advance_beats": shift, "matches": matches,
                           "score": score})

    candidates = defaultdict(list)
    if prefix is not None:
        old = json.loads(prefix.read_text())
        prefix_notes = old["notes"] if isinstance(old, dict) else old
        for note in prefix_notes:
            if float(note["beat"]) < first_global_beat:
                candidates[float(note["beat"])].append({
                    **note, "source": str(prefix),
                    "sightings": int(note.get("sightings", 100)),
                })
    for index, (run, offset) in enumerate(zip(runs, offsets)):
        sent = {(float(note["beat"]), note["pitch"]) for note in run["events"]}
        for local_beat, score_notes in run["ledger"].items():
            for note in score_notes:
                sightings = int(note.get("sightings", 0))
                if sightings < 2 and (local_beat, note["pitch"]) not in sent:
                    continue
                global_beat = local_beat + offset
                candidates[global_beat].append({
                    "beat": global_beat, "pitch": note["pitch"],
                    "duration_beats": note["duration_beats"],
                    "hold_beats": note["hold_beats"],
                    "sightings": sightings,
                    "source": str(run["path"]),
                })
    sources = []
    for beat, alternatives in sorted(candidates.items()):
        ranked = sorted(alternatives, key=lambda note: note["sightings"], reverse=True)
        winner = ranked[0]
        if (len(ranked) > 1
                and ranked[1]["sightings"] == winner["sightings"]
                and (ranked[1]["pitch"], ranked[1]["duration_beats"])
                != (winner["pitch"], winner["duration_beats"])):
            raise ValueError(f"ambiguous score at beat {beat}: {ranked[:2]}")
        sources.append(winner)
    sources.sort(key=lambda note: note["beat"])
    beats = [note["beat"] for note in sources]
    if len(beats) != len(set(beats)):
        raise ValueError("merged score contains two pitches at one beat; inspect score")
    return sources, alignments


def replay_queue(score: list[dict]) -> list[dict]:
    """Leave the opening prompt to the player's separate start-note path."""
    if score and float(score[0]["beat"]) < 0:
        return score[1:]
    return score


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path, help="ordered stopped-screen runs")
    parser.add_argument("--first-global-beat", type=float, required=True,
                        help="absolute beat of the first run's prompt note")
    parser.add_argument("--prefix-ledger", type=Path,
                        help="verified notes before the first run's prompt")
    parser.add_argument("--advance-beats", action="append", default=[], metavar="PAIR:BEATS",
                        help="visually verified advance for one ambiguous adjacent pair (1-based)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    advances = {}
    for item in args.advance_beats:
        pair, beats = item.split(":", 1)
        advances[int(pair)] = float(beats)
    runs = [read_run(path) for path in args.runs]
    notes, alignments = merge(runs, args.first_global_beat,
                              args.prefix_ledger, advances)
    px_per_beat = float(runs[0]["summary"]["grid"]["px_per_beat"])
    origin = 45.0
    seed = [{"beat": note["beat"], "pitch": note["pitch"],
             "duration_beats": note["duration_beats"],
             "hold_beats": note["hold_beats"], "sightings": 100,
             "relative_x_px": origin + note["beat"] * px_per_beat}
            for note in notes]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "ledger.json").write_text(json.dumps({"notes": seed}, indent=2))
    (args.output / "played.json").write_text(json.dumps(replay_queue(seed), indent=2))
    (args.output / "sources.json").write_text(json.dumps(notes, indent=2))
    (args.output / "alignments.json").write_text(json.dumps(alignments, indent=2))
    print(json.dumps({"notes": len(seed), "alignments": alignments}, indent=2))


if __name__ == "__main__":
    main()
