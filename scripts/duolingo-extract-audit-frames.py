#!/usr/bin/env python3
"""Extract sparse, timestamped PNGs from a saved Duolingo H.264 run.

This runs after playback, so PNG encoding cannot delay live note scheduling.
The raw stream can contain codec-config packets; device PTS is therefore an
approximate audit clock, not a replacement for the live input log.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--every", type=int, default=12,
                        help="keep one out of every N decoded video frames")
    args = parser.parse_args()
    if args.every < 1:
        parser.error("--every must be positive")

    recording = args.run / "recording.h264"
    pts_file = args.run / "recording.pts"
    manifest = args.run / "frames.json"
    frames_dir = args.run / "frames"
    if manifest.exists() or frames_dir.exists():
        parser.error("audit frames already exist; refusing to overwrite them")
    if not recording.is_file() or not pts_file.is_file():
        parser.error("run must contain recording.h264 and recording.pts")

    device_us = []
    for line in pts_file.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "__PTS__":
            device_us.append(int(parts[2]))
    if not device_us:
        parser.error("recording.pts has no device timestamps")

    frames_dir.mkdir()
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(recording),
        "-vf", f"select=not(mod(n\\,{args.every}))", "-vsync", "vfr",
        str(frames_dir / "frame-%05d.png"),
    ], check=True)
    images = sorted(frames_dir.glob("frame-*.png"))
    if not images:
        raise RuntimeError("ffmpeg did not decode any frames")
    records = []
    for index, path in enumerate(images):
        source_index = min(index * args.every, len(device_us) - 1)
        records.append({
            "index": source_index,
            "image": f"frames/{path.name}",
            "t_ms": (device_us[source_index] - device_us[0]) / 1000,
        })
    manifest.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    print(f"{len(records)} audit frames -> {manifest}")


if __name__ == "__main__":
    main()
