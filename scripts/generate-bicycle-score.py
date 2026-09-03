#!/usr/bin/env python3
"""
Generate Complete 34-Measure Sheet Music Score for "Bicycle Built for Two" (朱朱版本)
Using Meloo Rounded SMuFL Font.
Outputs:
1. moonlight/docs/practiced-songs/bicycle-built-for-two-score.html
2. moonlight/docs/practiced-songs/bicycle-built-for-two-score.svg
"""

import base64
import json
from pathlib import Path

def find_font_dir() -> Path:
    candidates = [
        Path("/Users/ldd/proj/lab-piano/meloo-font"),
        Path("/Users/ldd/proj/meloo-rounded"),
        Path(__file__).resolve().parents[1].parent / "meloo-font",
        Path(__file__).resolve().parents[1].parent / "meloo-rounded",
    ]
    for c in candidates:
        if (c / "MelooRounded-Regular.woff2").exists() or (c / "dist" / "fonts" / "MelooRounded-Regular.woff2").exists():
            return c
    raise FileNotFoundError("Could not find meloo-font / meloo-rounded directory")

FONT_DIR = find_font_dir()
MOONLIGHT_DOCS = Path(__file__).resolve().parents[1] / "docs" / "practiced-songs"

# Read WOFF2 font from meloo-font and encode as base64
woff2_path = FONT_DIR / "MelooRounded-Regular.woff2"
if not woff2_path.exists():
    woff2_path = FONT_DIR / "dist" / "fonts" / "MelooRounded-Regular.woff2"

with open(woff2_path, "rb") as f:
    woff2_b64 = base64.b64encode(f.read()).decode("ascii")

# Complete Measure Data for "Bicycle Built for Two" (34 measures, 3/4 time)
SONG_MEASURES = [
    # Measure 1: F4(h), R(q)
    {
        "measure": 1,
        "events": [
            {"type": "note", "pitch": "F4", "durationType": "half", "beat": 0.0, "durationBeats": 2.0, "lyric": "F4", "solfege": "Fa"},
            {"type": "rest", "durationType": "quarter", "beat": 2.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"},
        ]
    },
    # Measure 2: R(q), R(q), R(q)
    {
        "measure": 2,
        "events": [
            {"type": "rest", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"},
            {"type": "rest", "durationType": "quarter", "beat": 1.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"},
            {"type": "rest", "durationType": "quarter", "beat": 2.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"},
        ]
    },
    # Measure 3: R(q), R(q), R(q)
    {
        "measure": 3,
        "events": [
            {"type": "rest", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"},
            {"type": "rest", "durationType": "quarter", "beat": 1.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"},
            {"type": "rest", "durationType": "quarter", "beat": 2.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"},
        ]
    },
    # Measure 4: D4(q), F4(h)
    {
        "measure": 4,
        "events": [
            {"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "Dai-", "solfege": "Re"},
            {"type": "note", "pitch": "F4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "sy,", "solfege": "Fa"},
        ]
    },
    # Measure 5: G4(q), A4(q.), B4(e)
    {
        "measure": 5,
        "events": [
            {"type": "note", "pitch": "G4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "Dai-", "solfege": "Sol"},
            {"type": "note", "pitch": "A4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "sy,", "solfege": "La"},
            {"type": "note", "pitch": "B4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "give", "solfege": "Ti"},
        ]
    },
    # Measure 6: A4(q), G4(h)
    {
        "measure": 6,
        "events": [
            {"type": "note", "pitch": "A4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "me", "solfege": "La"},
            {"type": "note", "pitch": "G4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "your", "solfege": "Sol"},
        ]
    },
    # Measure 7: E4(q), C4(q.), D4(e)
    {
        "measure": 7,
        "events": [
            {"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "an-", "solfege": "Mi"},
            {"type": "note", "pitch": "C4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "swer", "solfege": "Do"},
            {"type": "note", "pitch": "D4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "do!", "solfege": "Re"},
        ]
    },
    # Measure 8: E4(q), F4(h)
    {
        "measure": 8,
        "events": [
            {"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "I'm", "solfege": "Mi"},
            {"type": "note", "pitch": "F4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "half", "solfege": "Fa"},
        ]
    },
    # Measure 9: D4(q), D4(q.), C4(e)
    {
        "measure": 9,
        "events": [
            {"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "cra-", "solfege": "Re"},
            {"type": "note", "pitch": "D4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "zy,", "solfege": "Re"},
            {"type": "note", "pitch": "C4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "all", "solfege": "Do"},
        ]
    },
    # Measure 10: D4(q), E4(h)
    {
        "measure": 10,
        "events": [
            {"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "for", "solfege": "Re"},
            {"type": "note", "pitch": "E4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "the", "solfege": "Mi"},
        ]
    },
    # Measure 11: F4(q), E4(h)
    {
        "measure": 11,
        "events": [
            {"type": "note", "pitch": "F4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "love", "solfege": "Fa"},
            {"type": "note", "pitch": "E4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "of", "solfege": "Mi"},
        ]
    },
    # Measure 12: D4(q), F4(h)
    {
        "measure": 12,
        "events": [
            {"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "you!", "solfege": "Re"},
            {"type": "note", "pitch": "F4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "It", "solfege": "Fa"},
        ]
    },
    # Measure 13: G4(q), A4(q.), B4(e)
    {
        "measure": 13,
        "events": [
            {"type": "note", "pitch": "G4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "won't", "solfege": "Sol"},
            {"type": "note", "pitch": "A4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "be", "solfege": "La"},
            {"type": "note", "pitch": "B4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "a", "solfege": "Ti"},
        ]
    },
    # Measure 14: A4(q), G4(h)
    {
        "measure": 14,
        "events": [
            {"type": "note", "pitch": "A4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "sty-", "solfege": "La"},
            {"type": "note", "pitch": "G4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "lish", "solfege": "Sol"},
        ]
    },
    # Measure 15: E4(q), C4(q.), D4(e)
    {
        "measure": 15,
        "events": [
            {"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "mar-", "solfege": "Mi"},
            {"type": "note", "pitch": "C4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "riage,", "solfege": "Do"},
            {"type": "note", "pitch": "D4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "I", "solfege": "Re"},
        ]
    },
    # Measure 16: E4(q), F4(q.), E4(e)
    {
        "measure": 16,
        "events": [
            {"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "can't", "solfege": "Mi"},
            {"type": "note", "pitch": "F4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "af-", "solfege": "Fa"},
            {"type": "note", "pitch": "E4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "ford", "solfege": "Mi"},
        ]
    },
    # Measure 17: D4(q), E4(q.), D4(e)
    {
        "measure": 17,
        "events": [
            {"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "a", "solfege": "Re"},
            {"type": "note", "pitch": "E4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "car-", "solfege": "Mi"},
            {"type": "note", "pitch": "D4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "riage,", "solfege": "Re"},
        ]
    },
    # Measure 18: E4(q), D4(h)
    {
        "measure": 18,
        "events": [
            {"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "but", "solfege": "Mi"},
            {"type": "note", "pitch": "D4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "you'll", "solfege": "Re"},
        ]
    },
    # Measure 19: R(q), R(q), R(q)
    {
        "measure": 19,
        "events": [
            {"type": "rest", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"},
            {"type": "rest", "durationType": "quarter", "beat": 1.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"},
            {"type": "rest", "durationType": "quarter", "beat": 2.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"},
        ]
    },
    # Measure 20: D4(q), F4(h)
    {
        "measure": 20,
        "events": [
            {"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "look", "solfege": "Re"},
            {"type": "note", "pitch": "F4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "sweet", "solfege": "Fa"},
        ]
    },
    # Measure 21: G4(q), A4(q.), B4(e)
    {
        "measure": 21,
        "events": [
            {"type": "note", "pitch": "G4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "up-", "solfege": "Sol"},
            {"type": "note", "pitch": "A4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "on", "solfege": "La"},
            {"type": "note", "pitch": "B4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "the", "solfege": "Ti"},
        ]
    },
    # Measure 22: A4(q), G4(h)
    {
        "measure": 22,
        "events": [
            {"type": "note", "pitch": "A4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "seat", "solfege": "La"},
            {"type": "note", "pitch": "G4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "of", "solfege": "Sol"},
        ]
    },
    # Measure 23: E4(q), C4(q.), D4(e)
    {
        "measure": 23,
        "events": [
            {"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "a", "solfege": "Mi"},
            {"type": "note", "pitch": "C4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "bi-", "solfege": "Do"},
            {"type": "note", "pitch": "D4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "cy-", "solfege": "Re"},
        ]
    },
    # Measure 24: E4(q), F4(h)
    {
        "measure": 24,
        "events": [
            {"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "cle", "solfege": "Mi"},
            {"type": "note", "pitch": "F4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "built", "solfege": "Fa"},
        ]
    },
    # Measure 25: D4(q), D4(q.), C4(e)
    {
        "measure": 25,
        "events": [
            {"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "for", "solfege": "Re"},
            {"type": "note", "pitch": "D4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "two,", "solfege": "Re"},
            {"type": "note", "pitch": "C4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "yes", "solfege": "Do"},
        ]
    },
    # Measure 26: D4(q), E4(h)
    {
        "measure": 26,
        "events": [
            {"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "built", "solfege": "Re"},
            {"type": "note", "pitch": "E4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "for", "solfege": "Mi"},
        ]
    },
    # Measure 27: F4(q), E4(h)
    {
        "measure": 27,
        "events": [
            {"type": "note", "pitch": "F4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "two,", "solfege": "Fa"},
            {"type": "note", "pitch": "E4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "a", "solfege": "Mi"},
        ]
    },
    # Measure 28: D4(q), F4(h)
    {
        "measure": 28,
        "events": [
            {"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "bi-", "solfege": "Re"},
            {"type": "note", "pitch": "F4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "cy-", "solfege": "Fa"},
        ]
    },
    # Measure 29: G4(q), A4(q.), B4(e)
    {
        "measure": 29,
        "events": [
            {"type": "note", "pitch": "G4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "cle", "solfege": "Sol"},
            {"type": "note", "pitch": "A4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "built", "solfege": "La"},
            {"type": "note", "pitch": "B4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "for", "solfege": "Ti"},
        ]
    },
    # Measure 30: A4(q), G4(h)
    {
        "measure": 30,
        "events": [
            {"type": "note", "pitch": "A4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "two,", "solfege": "La"},
            {"type": "note", "pitch": "G4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "sweet", "solfege": "Sol"},
        ]
    },
    # Measure 31: E4(q), C4(q.), D4(e)
    {
        "measure": 31,
        "events": [
            {"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "bi-", "solfege": "Mi"},
            {"type": "note", "pitch": "C4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "cy-", "solfege": "Do"},
            {"type": "note", "pitch": "D4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "cle", "solfege": "Re"},
        ]
    },
    # Measure 32: E4(q), F4(q.), E4(e)
    {
        "measure": 32,
        "events": [
            {"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "built", "solfege": "Mi"},
            {"type": "note", "pitch": "F4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "for", "solfege": "Fa"},
            {"type": "note", "pitch": "E4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "two,", "solfege": "Mi"},
        ]
    },
    # Measure 33: D4(q), E4(q.), D4(e)
    {
        "measure": 33,
        "events": [
            {"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "for", "solfege": "Re"},
            {"type": "note", "pitch": "E4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "you", "solfege": "Mi"},
            {"type": "note", "pitch": "D4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "and", "solfege": "Re"},
        ]
    },
    # Measure 34: E4(q), D4(h)
    {
        "measure": 34,
        "events": [
            {"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "me,", "solfege": "Mi"},
            {"type": "note", "pitch": "D4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "do!", "solfege": "Re"},
        ]
    },
]

# Assign global event indices
global_event_id = 0
for m in SONG_MEASURES:
    for ev in m["events"]:
        ev["id"] = global_event_id
        global_event_id += 1

PITCH_Y_OFFSET = {
    "B4": 50.0,  # Line 3
    "A4": 62.5,  # Space 2
    "G4": 75.0,  # Line 2
    "F4": 87.5,  # Space 1
    "E4": 100.0, # Line 1
    "D4": 112.5, # Space below Line 1
    "C4": 125.0, # Middle C
}

PITCH_FREQ = {
    "C4": 261.63,
    "D4": 293.66,
    "E4": 329.63,
    "F4": 349.23,
    "G4": 392.00,
    "A4": 440.00,
    "B4": 493.88,
}

SYSTEM_MEASURES_MAP = [
    (1, 4),   # Sys 1
    (5, 8),   # Sys 2
    (9, 12),  # Sys 3
    (13, 16), # Sys 4
    (17, 20), # Sys 5
    (21, 24), # Sys 6
    (25, 28), # Sys 7
    (29, 32), # Sys 8
    (33, 34), # Sys 9
]


def generate_svg_score() -> str:
    svg_width = 1200
    system_height = 240
    top_header_height = 140
    total_systems = len(SYSTEM_MEASURES_MAP)
    svg_height = top_header_height + total_systems * system_height + 40

    svg_parts = []
    svg_parts.append(f'''<svg viewBox="0 0 {svg_width} {svg_height}" width="100%" height="{svg_height}" xmlns="http://www.w3.org/2000/svg" class="meloo-score-svg">
  <defs>
    <style>
      @font-face {{
        font-family: 'MelooRounded';
        src: url('data:font/woff2;base64,{woff2_b64}') format('woff2');
        font-weight: normal;
        font-style: normal;
      }}
      .score-bg {{ fill: #0b1120; }}
      .score-title {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 26px; font-weight: bold; fill: #38bdf8; text-anchor: middle; }}
      .score-sub {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 13px; fill: #94a3b8; text-anchor: middle; }}
      .smufl-char {{ font-family: 'MelooRounded'; font-size: 100px; fill: #f8fafc; text-anchor: start; dominant-baseline: alphabetic; }}
      .staff-line {{ stroke: #475569; stroke-width: 2.2; }}
      .bar-line {{ stroke: #94a3b8; stroke-width: 2.2; }}
      .final-bar-thick {{ stroke: #f8fafc; stroke-width: 6.0; }}
      .system-bracket {{ stroke: #64748b; stroke-width: 3.5; fill: none; }}
      .ledger-line {{ stroke: #94a3b8; stroke-width: 2.2; }}
      .measure-num {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 12px; font-weight: bold; fill: #38bdf8; text-anchor: start; }}
      .lyric-text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 13px; font-weight: 500; fill: #cbd5e1; text-anchor: middle; }}
      .pitch-badge {{ font-family: monospace; font-size: 10px; font-weight: bold; fill: #38bdf8; text-anchor: middle; }}
      .event-group {{ cursor: pointer; transition: transform 0.1s; }}
      .event-group:hover .smufl-char {{ fill: #38bdf8; }}
      .event-group.active .smufl-char {{ fill: #f59e0b !important; filter: drop-shadow(0 0 6px rgba(245, 158, 11, 0.8)); }}
      .event-group.active .pitch-badge {{ fill: #f59e0b; font-weight: 900; }}
    </style>
  </defs>

  <rect width="{svg_width}" height="{svg_height}" class="score-bg" />

  <!-- Score Header -->
  <g transform="translate(600, 45)">
    <text y="0" class="score-title">Daisy Bell (Bicycle Built for Two) — 朱朱版本</text>
    <text y="28" class="score-sub">3/4 拍 | C大调 (中速 100 BPM) | Meloo Rounded 纯粹圆润 SMuFL 矢量五线谱</text>
    <text y="48" class="score-sub">高音谱号 G4 | 音域 C4–B4 | 34 小节 75 音符 10 四分休止符</text>
  </g>
''')

    for sys_idx, (m_start, m_end) in enumerate(SYSTEM_MEASURES_MAP):
        sys_y = top_header_height + sys_idx * system_height
        sys_measures = SONG_MEASURES[m_start - 1 : m_end]
        is_first_sys = (sys_idx == 0)
        is_last_sys = (sys_idx == len(SYSTEM_MEASURES_MAP) - 1)

        left_x = 40
        right_x = 1160

        clef_x = left_x + 15
        if is_first_sys:
            measures_start_x = left_x + 135
        else:
            measures_start_x = left_x + 85

        avail_width = right_x - measures_start_x
        num_m = len(sys_measures)
        m_width = avail_width / num_m if not is_last_sys else avail_width / 4.0
        last_m_right_x = measures_start_x + num_m * m_width if is_last_sys else right_x

        svg_parts.append(f'  <!-- System {sys_idx + 1} (Measures {m_start}–{m_end}) -->')
        svg_parts.append(f'  <g id="system-{sys_idx + 1}" transform="translate(0, {sys_y})">')
        svg_parts.append(f'    <line x1="{left_x}" y1="0" x2="{left_x}" y2="100" class="system-bracket" />')

        for line_idx, line_y in enumerate([0, 25, 50, 75, 100]):
            svg_parts.append(f'    <line x1="{left_x}" y1="{line_y}" x2="{last_m_right_x}" y2="{line_y}" class="staff-line" />')

        svg_parts.append(f'    <text x="{clef_x}" y="75" class="smufl-char">&#xE050;</text>')

        if is_first_sys:
            svg_parts.append(f'    <text x="{left_x + 85}" y="25" class="smufl-char">&#xE083;</text>')
            svg_parts.append(f'    <text x="{left_x + 85}" y="75" class="smufl-char">&#xE084;</text>')

        for i, m_data in enumerate(sys_measures):
            m_num = m_data["measure"]
            m_left = measures_start_x + i * m_width
            m_right = m_left + m_width

            svg_parts.append(f'    <text x="{m_left + 4}" y="-16" class="measure-num">{m_num}</text>')

            pad_left = 18.0
            pad_right = 16.0
            usable_w = m_width - pad_left - pad_right

            for ev in m_data["events"]:
                ev_id = ev["id"]
                beat = ev["beat"]
                ev_type = ev["type"]
                dur_type = ev["durationType"]
                ev_x = m_left + pad_left + (beat / 3.0) * usable_w

                lyric = ev.get("lyric", "")
                solfege = ev.get("solfege", "")

                svg_parts.append(f'    <g id="event-{ev_id}" class="event-group" data-event-id="{ev_id}" data-measure="{m_num}" data-type="{ev_type}" onclick="playSingleEvent({ev_id})">')

                if ev_type == "note":
                    pitch = ev["pitch"]
                    note_y = PITCH_Y_OFFSET[pitch]

                    if pitch == "C4":
                        svg_parts.append(f'      <line x1="{ev_x - 8}" y1="125" x2="{ev_x + 38}" y2="125" class="ledger-line" />')

                    if dur_type in ["quarter", "dotted-quarter"]:
                        glyph_code = "&#xE1D6;" if pitch == "B4" else "&#xE1D5;"
                    elif dur_type == "half":
                        glyph_code = "&#xE1D4;" if pitch == "B4" else "&#xE1D3;"
                    elif dur_type == "eighth":
                        glyph_code = "&#xE1D8;" if pitch == "B4" else "&#xE1D7;"
                    else:
                        glyph_code = "&#xE1D5;"

                    svg_parts.append(f'      <text x="{ev_x}" y="{note_y}" class="smufl-char">{glyph_code}</text>')

                    if dur_type == "dotted-quarter":
                        dot_y = note_y - 12.5 if pitch in ["C4", "E4", "G4", "B4"] else note_y
                        dot_x = ev_x + 36.0
                        svg_parts.append(f'      <text x="{dot_x}" y="{dot_y}" class="smufl-char">&#xE1E7;</text>')

                    badge_label = f"{pitch}·{solfege}"
                    svg_parts.append(f'      <text x="{ev_x + 16}" y="150" class="pitch-badge">{badge_label}</text>')
                    if lyric:
                        svg_parts.append(f'      <text x="{ev_x + 16}" y="178" class="lyric-text">{lyric}</text>')

                elif ev_type == "rest":
                    svg_parts.append(f'      <text x="{ev_x}" y="50" class="smufl-char">&#xE4E5;</text>')
                    svg_parts.append(f'      <text x="{ev_x + 12}" y="150" class="pitch-badge" style="fill:#64748b;">休</text>')

                svg_parts.append('    </g>')

            if i == num_m - 1 and is_last_sys:
                svg_parts.append(f'    <line x1="{last_m_right_x - 8}" y1="0" x2="{last_m_right_x - 8}" y2="100" class="bar-line" />')
                svg_parts.append(f'    <line x1="{last_m_right_x}" y1="0" x2="{last_m_right_x}" y2="100" class="final-bar-thick" />')
            else:
                svg_parts.append(f'    <line x1="{m_right}" y1="0" x2="{m_right}" y2="100" class="bar-line" />')

        svg_parts.append('  </g>\n')

    svg_parts.append('</svg>')
    return '\n'.join(svg_parts)


def generate_interactive_html() -> str:
    svg_content = generate_svg_score()
    song_json = json.dumps(SONG_MEASURES, ensure_ascii=False)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Bicycle Built for Two (朱朱版本) — Meloo Rounded SMuFL 五线谱</title>
  <style>
    @font-face {{
      font-family: 'MelooRounded';
      src: url('data:font/woff2;base64,{woff2_b64}') format('woff2');
      font-weight: normal;
      font-style: normal;
    }}
    :root {{
      --bg-main: #0b1120;
      --card-bg: #1e293b;
      --card-border: #334155;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.4);
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --score-bg: #0b1120;
      --score-note: #f8fafc;
      --score-line: #475569;
      --score-bar: #94a3b8;
    }}

    body.theme-light {{
      --bg-main: #f1f5f9;
      --card-bg: #ffffff;
      --card-border: #cbd5e1;
      --accent: #0284c7;
      --accent-glow: rgba(2, 132, 199, 0.3);
      --text-main: #0f172a;
      --text-muted: #64748b;
      --score-bg: #ffffff;
      --score-note: #0f172a;
      --score-line: #94a3b8;
      --score-bar: #475569;
    }}

    body {{
      margin: 0;
      padding: 24px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: var(--bg-main);
      color: var(--text-main);
      transition: background 0.25s, color 0.25s;
    }}

    .container {{
      max-width: 1280px;
      margin: 0 auto;
    }}

    header {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 20px;
      gap: 16px;
    }}

    .header-left h1 {{
      font-size: 24px;
      margin: 0 0 6px 0;
      color: var(--accent);
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .header-left p {{
      margin: 0;
      font-size: 13px;
      color: var(--text-muted);
    }}

    .badge-tag {{
      font-size: 11px;
      background: #0369a1;
      color: #e0f2fe;
      padding: 3px 8px;
      border-radius: 6px;
      font-weight: 600;
    }}

    .controls-panel {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 20px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }}

    .btn-group {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    button {{
      background: var(--accent);
      color: #0b1120;
      border: none;
      border-radius: 8px;
      padding: 9px 18px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }}

    button:hover {{
      opacity: 0.92;
      transform: translateY(-1px);
      box-shadow: 0 3px 8px var(--accent-glow);
    }}

    button.btn-secondary {{
      background: transparent;
      border: 1px solid var(--card-border);
      color: var(--text-main);
    }}

    button.btn-secondary:hover {{
      background: var(--card-border);
    }}

    .slider-group {{
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 13px;
      color: var(--text-muted);
    }}

    .slider-group input[type="range"] {{
      width: 130px;
      accent-color: var(--accent);
    }}

    .tempo-val {{
      font-weight: bold;
      color: var(--accent);
      font-family: monospace;
      font-size: 14px;
      min-width: 60px;
    }}

    .toggles-group {{
      display: flex;
      align-items: center;
      gap: 16px;
      font-size: 13px;
      color: var(--text-muted);
    }}

    .toggle-item {{
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      user-select: none;
    }}

    .score-wrapper {{
      background: var(--score-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 24px 16px;
      overflow-x: auto;
      box-shadow: 0 4px 20px rgba(0,0,0,0.15);
      transition: background 0.25s, border-color 0.25s;
    }}

    .score-wrapper svg {{
      display: block;
      margin: 0 auto;
    }}

    body.theme-light .score-bg {{ fill: #ffffff !important; }}
    body.theme-light .smufl-char {{ fill: #0f172a !important; }}
    body.theme-light .staff-line {{ stroke: #94a3b8 !important; }}
    body.theme-light .bar-line {{ stroke: #475569 !important; }}
    body.theme-light .final-bar-thick {{ stroke: #0f172a !important; }}
    body.theme-light .ledger-line {{ stroke: #64748b !important; }}
    body.theme-light .lyric-text {{ fill: #334155 !important; }}
    body.theme-light .score-title {{ fill: #0369a1 !important; }}
    body.theme-light .score-sub {{ fill: #64748b !important; }}

    .status-bar {{
      margin-top: 20px;
      padding: 12px 18px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      font-size: 13px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    .status-info {{
      color: var(--text-muted);
    }}

    .status-info strong {{
      color: var(--accent);
    }}

    @media print {{
      body {{
        background: #ffffff !important;
        color: #000000 !important;
        padding: 0 !important;
      }}
      header, .controls-panel, .status-bar {{
        display: none !important;
      }}
      .score-wrapper {{
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        background: #ffffff !important;
      }}
      .score-bg {{ fill: #ffffff !important; }}
      .smufl-char {{ fill: #000000 !important; }}
      .staff-line {{ stroke: #000000 !important; stroke-width: 1.5 !important; }}
      .bar-line {{ stroke: #000000 !important; stroke-width: 1.5 !important; }}
      .final-bar-thick {{ stroke: #000000 !important; }}
      .ledger-line {{ stroke: #000000 !important; }}
      .score-title {{ fill: #000000 !important; }}
      .score-sub {{ fill: #333333 !important; }}
      .lyric-text {{ fill: #000000 !important; }}
      .pitch-badge {{ fill: #444444 !important; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="header-left">
        <h1>
          🎼 Bicycle Built for Two (Daisy Bell)
          <span class="badge-tag">朱朱全曲完美重现</span>
          <span class="badge-tag" style="background:#059669;">Meloo Rounded SMuFL</span>
        </h1>
        <p>Duolingo Music 第 4 阶段第 7 部分星形练习 | 高音谱号 | 3/4 拍 | C 大调 | 34 小节 75 音符 10 休止符</p>
      </div>
      <div class="btn-group">
        <button class="btn-secondary" onclick="toggleTheme()">🌓 切换明/暗主题</button>
        <button class="btn-secondary" onclick="window.print()">🖨️ 打印五线谱</button>
        <button class="btn-secondary" onclick="downloadSVG()">📥 下载 SVG 矢量谱</button>
      </div>
    </header>

    <div class="controls-panel">
      <div class="btn-group">
        <button id="btn-play" onclick="togglePlay()">▶ 播放整曲 (Play)</button>
        <button class="btn-secondary" onclick="stopPlayback()">⏹ 停止 (Stop)</button>
        <button class="btn-secondary" onclick="resetToStart()">⏮ 重置到第一小节</button>
      </div>

      <div class="slider-group">
        <span>速度 (Tempo):</span>
        <input type="range" id="tempo-slider" min="40" max="180" value="100" oninput="updateTempo(this.value)">
        <span class="tempo-val" id="tempo-text">100 BPM</span>
      </div>

      <div class="toggles-group">
        <label class="toggle-item">
          <input type="checkbox" id="toggle-pitch" checked onchange="togglePitchLabels(this.checked)">
          显示音名/唱名 (Pitch)
        </label>
        <label class="toggle-item">
          <input type="checkbox" id="toggle-lyrics" checked onchange="toggleLyrics(this.checked)">
          显示歌词 (Lyrics)
        </label>
        <label class="toggle-item">
          <input type="checkbox" id="toggle-loop" onchange="toggleLoop(this.checked)">
          循环播放 (Loop)
        </label>
      </div>
    </div>

    <div class="score-wrapper" id="score-container">
      {svg_content}
    </div>

    <div class="status-bar">
      <div class="status-info">
        当前小节: <strong id="cur-measure">1</strong> / 34 | 当前音符: <strong id="cur-note">F4 (Fa)</strong> | 当前时值: <strong id="cur-dur">二分音符 (2 拍)</strong>
      </div>
      <div class="status-info" style="font-family: monospace;">
        音域: C4–B4 | 字体: MelooRounded-Regular (SMuFL v0.254) | 提示: 点击谱上任意音符可即时试听
      </div>
    </div>
  </div>

  <script>
    const SONG_DATA = {song_json};
    const PITCH_FREQ = {json.dumps(PITCH_FREQ)};

    let audioCtx = null;
    let isPlaying = false;
    let currentBPM = 100;
    let isLooping = false;
    let playbackTimeoutId = null;
    let currentEventIndex = 0;

    const allEvents = [];
    SONG_DATA.forEach(m => {{
      m.events.forEach(ev => {{
        allEvents.push(ev);
      }});
    }});

    function getAudioContext() {{
      if (!audioCtx) {{
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        audioCtx = new AudioContextClass();
      }}
      if (audioCtx.state === 'suspended') {{
        audioCtx.resume();
      }}
      return audioCtx;
    }}

    function playTone(freq, durationSec) {{
      if (!freq) return;
      const ctx = getAudioContext();
      const now = ctx.currentTime;

      const masterGain = ctx.createGain();
      masterGain.connect(ctx.destination);

      const attack = 0.008;
      const decay = 0.25;
      const sustainLevel = 0.35;
      const release = Math.min(0.3, durationSec * 0.4);

      masterGain.gain.setValueAtTime(0.0001, now);
      masterGain.gain.linearRampToValueAtTime(0.4, now + attack);
      masterGain.gain.exponentialRampToValueAtTime(sustainLevel * 0.4, now + attack + decay);
      masterGain.gain.setValueAtTime(sustainLevel * 0.4, now + durationSec);
      masterGain.gain.exponentialRampToValueAtTime(0.0001, now + durationSec + release);

      const osc1 = ctx.createOscillator();
      osc1.type = 'triangle';
      osc1.frequency.setValueAtTime(freq, now);
      osc1.connect(masterGain);
      osc1.start(now);
      osc1.stop(now + durationSec + release);

      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      gain2.gain.value = 0.3;
      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(freq * 2, now);
      osc2.connect(gain2);
      gain2.connect(masterGain);
      osc2.start(now);
      osc2.stop(now + durationSec + release);

      const osc3 = ctx.createOscillator();
      const gain3 = ctx.createGain();
      gain3.gain.value = 0.12;
      osc3.type = 'sine';
      osc3.frequency.setValueAtTime(freq * 3, now);
      osc3.connect(gain3);
      gain3.connect(masterGain);
      osc3.start(now);
      osc3.stop(now + durationSec + release);
    }}

    function highlightEvent(eventId) {{
      document.querySelectorAll('.event-group.active').forEach(el => el.classList.remove('active'));

      if (eventId !== null && eventId !== undefined) {{
        const el = document.getElementById('event-' + eventId);
        if (el) {{
          el.classList.add('active');
          const bbox = el.getBoundingClientRect();
          if (bbox.top < 50 || bbox.bottom > window.innerHeight - 50) {{
            el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
          }}
        }}

        const ev = allEvents.find(e => e.id === eventId);
        if (ev) {{
          document.getElementById('cur-measure').textContent = ev.measure;
          if (ev.type === 'note') {{
            document.getElementById('cur-note').textContent = `${{ev.pitch}} (${{ev.solfege || ''}})`;
            const durNames = {{ 'quarter': '四分音符 (1 拍)', 'half': '二分音符 (2 拍)', 'dotted-quarter': '附点四分音符 (1.5 拍)', 'eighth': '八分音符 (0.5 拍)' }};
            document.getElementById('cur-dur').textContent = durNames[ev.durationType] || ev.durationType;
          }} else {{
            document.getElementById('cur-note').textContent = '四分休止符';
            document.getElementById('cur-dur').textContent = '休止 1 拍';
          }}
        }}
      }}
    }}

    function playSingleEvent(eventId) {{
      const ev = allEvents.find(e => e.id === eventId);
      if (!ev) return;
      highlightEvent(eventId);
      if (ev.type === 'note') {{
        const beatSec = 60.0 / currentBPM;
        const durSec = ev.durationBeats * beatSec;
        const freq = PITCH_FREQ[ev.pitch];
        playTone(freq, durSec);
      }}
    }}

    function stepPlayback() {{
      if (!isPlaying) return;

      if (currentEventIndex >= allEvents.length) {{
        if (isLooping) {{
          currentEventIndex = 0;
        }} else {{
          stopPlayback();
          return;
        }}
      }}

      const ev = allEvents[currentEventIndex];
      const beatSec = 60.0 / currentBPM;
      const durSec = ev.durationBeats * beatSec;

      highlightEvent(ev.id);

      if (ev.type === 'note') {{
        const freq = PITCH_FREQ[ev.pitch];
        playTone(freq, durSec * 0.95);
      }}

      currentEventIndex++;
      playbackTimeoutId = setTimeout(stepPlayback, durSec * 1000);
    }}

    function togglePlay() {{
      const btn = document.getElementById('btn-play');
      if (isPlaying) {{
        stopPlayback();
      }} else {{
        isPlaying = true;
        btn.textContent = '⏸ 暂停 (Pause)';
        btn.style.background = '#f59e0b';
        getAudioContext();
        stepPlayback();
      }}
    }}

    function stopPlayback() {{
      isPlaying = false;
      if (playbackTimeoutId) {{
        clearTimeout(playbackTimeoutId);
        playbackTimeoutId = null;
      }}
      const btn = document.getElementById('btn-play');
      btn.textContent = '▶ 播放整曲 (Play)';
      btn.style.background = 'var(--accent)';
      highlightEvent(null);
    }}

    function resetToStart() {{
      stopPlayback();
      currentEventIndex = 0;
      highlightEvent(0);
      const firstEv = allEvents[0];
      if (firstEv) {{
        const el = document.getElementById('event-0');
        if (el) el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
      }}
    }}

    function updateTempo(val) {{
      currentBPM = Number(val);
      document.getElementById('tempo-text').textContent = val + ' BPM';
    }}

    function togglePitchLabels(show) {{
      document.querySelectorAll('.pitch-badge').forEach(el => {{
        el.style.display = show ? '' : 'none';
      }});
    }}

    function toggleLyrics(show) {{
      document.querySelectorAll('.lyric-text').forEach(el => {{
        el.style.display = show ? '' : 'none';
      }});
    }}

    function toggleLoop(val) {{
      isLooping = val;
    }}

    function toggleTheme() {{
      document.body.classList.toggle('theme-light');
    }}

    function downloadSVG() {{
      const svgEl = document.querySelector('.meloo-score-svg');
      if (!svgEl) return;
      const svgData = new XMLSerializer().serializeToString(svgEl);
      const blob = new Blob([svgData], {{ type: 'image/svg+xml;charset=utf-8' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'bicycle-built-for-two-score-meloo-rounded.svg';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }}
  </script>
</body>
</html>
'''
    return html


def main():
    print("Generating Bicycle Built for Two score in moonlight/docs/practiced-songs...")
    svg_content = generate_svg_score()
    html_content = generate_interactive_html()

    svg_path = MOONLIGHT_DOCS / "bicycle-built-for-two-score.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    print(f"[OK] Saved SVG to {svg_path}")

    html_path = MOONLIGHT_DOCS / "bicycle-built-for-two-score.html"
    html_path.write_text(html_content, encoding="utf-8")
    print(f"[OK] Saved HTML to {html_path}")


if __name__ == "__main__":
    main()
