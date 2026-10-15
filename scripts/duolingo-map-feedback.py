#!/usr/bin/env python3
"""Map visible judgment feedback to played notes using display latency."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

from duolingo_measure_tracker import detect_measure_barline_candidates


BAD_GRADES = {"迟了", "早了", "太早", "失误", "哎呀"}


def feedback_groups(feedback: list[dict]) -> list[dict]:
    groups: list[dict] = []
    for frame in feedback:
        grade = frame.get("grade")
        if grade not in BAD_GRADES:
            continue
        if (groups and groups[-1]["grade"] == grade
                and frame["t_ms"] - groups[-1]["last_ms"] < 700
                and frame["t_ms"] - groups[-1]["first_ms"] < 550):
            groups[-1]["last_ms"] = frame["t_ms"]
        else:
            groups.append({"grade": grade, "first_ms": frame["t_ms"],
                           "last_ms": frame["t_ms"]})
    return groups


def fit_video_offset(observations: list[tuple[float, float]],
                     phase: list[dict]) -> tuple[float, float, bool]:
    """Fit the two clocks from shared barline phases, preserving aliases."""
    steady = [p for p in phase if p.get("phase_px") is not None
              and p["state"] == "steady"]
    if len(steady) < 10:
        raise ValueError("not enough steady barline phases for video alignment")
    spacing = float(np.median([p["spacing_px"] for p in steady
                               if p.get("spacing_px")]))
    speeds = [abs(float(p["speed_px_s"])) for p in steady
              if p.get("speed_px_s")]
    measure_period_ms = (1000.0 * spacing / float(np.median(speeds))
                         if speeds else 2500.0)
    phase_t = np.asarray([p["t_ms"] for p in steady], dtype=float)
    phase_x = np.asarray([p["phase_px"] for p in steady], dtype=float)
    if len(observations) < 8:
        raise ValueError("not enough visible barlines for video alignment")
    video_t = np.asarray([item[0] for item in observations])
    video_x = np.asarray([item[1] for item in observations])
    scores = []
    for offset in np.arange(0.0, 6000.1, 10.0):
        host_t = video_t - offset
        valid = (host_t >= phase_t[0]) & (host_t <= phase_t[-1])
        if valid.sum() < 8:
            continue
        predicted = np.interp(host_t[valid], phase_t, phase_x)
        residual = np.abs((video_x[valid] - predicted + spacing / 2)
                          % spacing - spacing / 2)
        scores.append((float(np.median(residual)), float(offset)))
    if not scores:
        raise ValueError("no overlapping video and phase clock interval")
    minimum_error = min(error for error, _offset in scores)
    # An earlier whole-measure alias is compatible with the score appearing
    # shortly after capture starts.  Keep the alias warning for auditability.
    plausible = [(error, offset) for error, offset in scores
                 if error <= minimum_error + 2.0]
    earliest = min(offset for _error, offset in plausible)
    error_px, best_offset = min(
        (error, offset) for error, offset in plausible
        if offset <= earliest + 100.0
    )
    aliases = [offset for error, offset in scores
               if abs(offset - best_offset) > 0.6 * measure_period_ms
               and error <= error_px + 2.0]
    return best_offset, error_px, bool(aliases)


def estimate_video_offset(run: Path) -> tuple[float, float, bool]:
    """Align archived device PTS to host time through visible barlines."""
    frames = json.loads((run / "frames.json").read_text())
    phase = json.loads((run / "phase.json").read_text())
    usable = [f for f in frames if 3000 <= f["t_ms"] <= 24000]
    chosen = usable[::max(1, len(usable) // 28)][:28]
    observations = []
    for frame in chosen:
        image = Image.open(run / frame["image"]).convert("RGB")
        candidates = detect_measure_barline_candidates(
            image, (144, 182, 220, 258, 296), 490,
        )
        strong = [candidate.x for candidate in candidates
                  if candidate.coverage >= 0.7]
        if strong:
            observations.append((float(frame["t_ms"]), strong[0]))
    if len(observations) < 8:
        raise ValueError("not enough visible barlines for video alignment")
    return fit_video_offset(observations, phase)


def map_feedback(feedback: list[dict], played: list[dict],
                 expected_lag_ms: float = 460.0,
                 video_offset_ms: float = 0.0,
                 timebase_ambiguous: bool = False) -> list[dict]:
    mapped = []
    for group in feedback_groups(feedback):
        candidates = []
        for note in played:
            lag = group["first_ms"] - video_offset_ms - note["sent_ms"]
            if 150 <= lag <= 950:
                candidates.append((abs(lag - expected_lag_ms), note, lag))
        candidates.sort(key=lambda item: item[0])
        result = dict(group)
        result["video_offset_ms"] = video_offset_ms
        result["aligned_first_ms"] = round(group["first_ms"] - video_offset_ms, 1)
        result["timebase_ambiguous"] = timebase_ambiguous
        if candidates:
            best = candidates[0]
            result.update(beat=best[1]["beat"], pitch=best[1]["pitch"],
                          lag_ms=round(best[2], 1),
                          ambiguous=(timebase_ambiguous or
                                     (len(candidates) > 1 and
                                      candidates[1][0] - best[0] < 100)))
        else:
            result.update(beat=None, pitch=None, lag_ms=None, ambiguous=True)
        mapped.append(result)
    return mapped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--video-offset-ms", type=float,
                        help="explicit device-video to host-clock offset")
    args = parser.parse_args()
    feedback = json.loads((args.run / "feedback.json").read_text())
    played = json.loads((args.run / "played.json").read_text())
    if args.video_offset_ms is None:
        offset, residual, ambiguous = estimate_video_offset(args.run)
        print(f"[timebase] video_offset_ms={offset:.0f} "
              f"barline_residual_px={residual:.1f} ambiguous={ambiguous}",
              file=sys.stderr)
    else:
        offset, ambiguous = args.video_offset_ms, False
    print(json.dumps(map_feedback(feedback, played,
                                  video_offset_ms=offset,
                                  timebase_ambiguous=ambiguous),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
