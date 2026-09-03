#!/usr/bin/env python3
"""
Generate Complete 34-Measure Grand Staff (大谱表: 高音右手 + 低音左手)
for "Bicycle Built for Two" (Daisy Bell — 朱朱版本).
Using Meloo Rounded SMuFL Font.

Accompaniment Modes:
- Mode 1 (Active/Primary): 初学单音根音伴奏 (Beginner Single-Note Bass)
- Mode 2 (Documented/Upgrade): 1892 经典圆舞曲“澎-恰-恰”和弦 (1892 Classical Waltz Boom-Chic-Chic)
- Mode 3 (Documented/Upgrade): 抒情分解和弦伴奏 (Lyrical Arpeggiated Waltz)

Outputs:
1. moonlight/docs/practiced-songs/bicycle-built-for-two-grand-staff.html
2. moonlight/docs/practiced-songs/bicycle-built-for-two-grand-staff.svg
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

# Right Hand (Treble Clef) 34 Measures
RIGHT_HAND_MEASURES = [
    {"measure": 1, "events": [{"type": "note", "pitch": "F4", "durationType": "half", "beat": 0.0, "durationBeats": 2.0, "lyric": "F4", "solfege": "Fa"}, {"type": "rest", "durationType": "quarter", "beat": 2.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"}]},
    {"measure": 2, "events": [{"type": "rest", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"}, {"type": "rest", "durationType": "quarter", "beat": 1.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"}, {"type": "rest", "durationType": "quarter", "beat": 2.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"}]},
    {"measure": 3, "events": [{"type": "rest", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"}, {"type": "rest", "durationType": "quarter", "beat": 1.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"}, {"type": "rest", "durationType": "quarter", "beat": 2.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"}]},
    {"measure": 4, "events": [{"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "Dai-", "solfege": "Re"}, {"type": "note", "pitch": "F4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "sy,", "solfege": "Fa"}]},
    {"measure": 5, "events": [{"type": "note", "pitch": "G4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "Dai-", "solfege": "Sol"}, {"type": "note", "pitch": "A4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "sy,", "solfege": "La"}, {"type": "note", "pitch": "B4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "give", "solfege": "Ti"}]},
    {"measure": 6, "events": [{"type": "note", "pitch": "A4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "me", "solfege": "La"}, {"type": "note", "pitch": "G4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "your", "solfege": "Sol"}]},
    {"measure": 7, "events": [{"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "an-", "solfege": "Mi"}, {"type": "note", "pitch": "C4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "swer", "solfege": "Do"}, {"type": "note", "pitch": "D4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "do!", "solfege": "Re"}]},
    {"measure": 8, "events": [{"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "I'm", "solfege": "Mi"}, {"type": "note", "pitch": "F4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "half", "solfege": "Fa"}]},
    {"measure": 9, "events": [{"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "cra-", "solfege": "Re"}, {"type": "note", "pitch": "D4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "zy,", "solfege": "Re"}, {"type": "note", "pitch": "C4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "all", "solfege": "Do"}]},
    {"measure": 10, "events": [{"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "for", "solfege": "Re"}, {"type": "note", "pitch": "E4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "the", "solfege": "Mi"}]},
    {"measure": 11, "events": [{"type": "note", "pitch": "F4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "love", "solfege": "Fa"}, {"type": "note", "pitch": "E4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "of", "solfege": "Mi"}]},
    {"measure": 12, "events": [{"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "you!", "solfege": "Re"}, {"type": "note", "pitch": "F4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "It", "solfege": "Fa"}]},
    {"measure": 13, "events": [{"type": "note", "pitch": "G4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "won't", "solfege": "Sol"}, {"type": "note", "pitch": "A4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "be", "solfege": "La"}, {"type": "note", "pitch": "B4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "a", "solfege": "Ti"}]},
    {"measure": 14, "events": [{"type": "note", "pitch": "A4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "sty-", "solfege": "La"}, {"type": "note", "pitch": "G4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "lish", "solfege": "Sol"}]},
    {"measure": 15, "events": [{"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "mar-", "solfege": "Mi"}, {"type": "note", "pitch": "C4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "riage,", "solfege": "Do"}, {"type": "note", "pitch": "D4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "I", "solfege": "Re"}]},
    {"measure": 16, "events": [{"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "can't", "solfege": "Mi"}, {"type": "note", "pitch": "F4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "af-", "solfege": "Fa"}, {"type": "note", "pitch": "E4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "ford", "solfege": "Mi"}]},
    {"measure": 17, "events": [{"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "a", "solfege": "Re"}, {"type": "note", "pitch": "E4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "car-", "solfege": "Mi"}, {"type": "note", "pitch": "D4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "riage,", "solfege": "Re"}]},
    {"measure": 18, "events": [{"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "but", "solfege": "Mi"}, {"type": "note", "pitch": "D4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "you'll", "solfege": "Re"}]},
    {"measure": 19, "events": [{"type": "rest", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"}, {"type": "rest", "durationType": "quarter", "beat": 1.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"}, {"type": "rest", "durationType": "quarter", "beat": 2.0, "durationBeats": 1.0, "lyric": "", "solfege": "休"}]},
    {"measure": 20, "events": [{"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "look", "solfege": "Re"}, {"type": "note", "pitch": "F4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "sweet", "solfege": "Fa"}]},
    {"measure": 21, "events": [{"type": "note", "pitch": "G4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "up-", "solfege": "Sol"}, {"type": "note", "pitch": "A4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "on", "solfege": "La"}, {"type": "note", "pitch": "B4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "the", "solfege": "Ti"}]},
    {"measure": 22, "events": [{"type": "note", "pitch": "A4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "seat", "solfege": "La"}, {"type": "note", "pitch": "G4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "of", "solfege": "Sol"}]},
    {"measure": 23, "events": [{"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "a", "solfege": "Mi"}, {"type": "note", "pitch": "C4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "bi-", "solfege": "Do"}, {"type": "note", "pitch": "D4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "cy-", "solfege": "Re"}]},
    {"measure": 24, "events": [{"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "cle", "solfege": "Mi"}, {"type": "note", "pitch": "F4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "built", "solfege": "Fa"}]},
    {"measure": 25, "events": [{"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "for", "solfege": "Re"}, {"type": "note", "pitch": "D4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "two,", "solfege": "Re"}, {"type": "note", "pitch": "C4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "yes", "solfege": "Do"}]},
    {"measure": 26, "events": [{"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "built", "solfege": "Re"}, {"type": "note", "pitch": "E4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "for", "solfege": "Mi"}]},
    {"measure": 27, "events": [{"type": "note", "pitch": "F4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "two,", "solfege": "Fa"}, {"type": "note", "pitch": "E4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "a", "solfege": "Mi"}]},
    {"measure": 28, "events": [{"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "bi-", "solfege": "Re"}, {"type": "note", "pitch": "F4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "cy-", "solfege": "Fa"}]},
    {"measure": 29, "events": [{"type": "note", "pitch": "G4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "cle", "solfege": "Sol"}, {"type": "note", "pitch": "A4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "built", "solfege": "La"}, {"type": "note", "pitch": "B4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "for", "solfege": "Ti"}]},
    {"measure": 30, "events": [{"type": "note", "pitch": "A4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "two,", "solfege": "La"}, {"type": "note", "pitch": "G4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "sweet", "solfege": "Sol"}]},
    {"measure": 31, "events": [{"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "bi-", "solfege": "Mi"}, {"type": "note", "pitch": "C4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "cy-", "solfege": "Do"}, {"type": "note", "pitch": "D4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "cle", "solfege": "Re"}]},
    {"measure": 32, "events": [{"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "built", "solfege": "Mi"}, {"type": "note", "pitch": "F4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "for", "solfege": "Fa"}, {"type": "note", "pitch": "E4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "two,", "solfege": "Mi"}]},
    {"measure": 33, "events": [{"type": "note", "pitch": "D4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "for", "solfege": "Re"}, {"type": "note", "pitch": "E4", "durationType": "dotted-quarter", "beat": 1.0, "durationBeats": 1.5, "lyric": "you", "solfege": "Mi"}, {"type": "note", "pitch": "D4", "durationType": "eighth", "beat": 2.5, "durationBeats": 0.5, "lyric": "and", "solfege": "Re"}]},
    {"measure": 34, "events": [{"type": "note", "pitch": "E4", "durationType": "quarter", "beat": 0.0, "durationBeats": 1.0, "lyric": "me,", "solfege": "Mi"}, {"type": "note", "pitch": "D4", "durationType": "half", "beat": 1.0, "durationBeats": 2.0, "lyric": "do!", "solfege": "Re"}]},
]

# Left Hand (Bass Clef) Mode 1: 初学单音根音伴奏 (Sustained 3-beat Dotted-Half Notes)
LEFT_HAND_MODE_1 = [
    {"measure": 1, "events": [{"type": "note", "pitch": "F2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "F", "solfege": "Fa"}]},
    {"measure": 2, "events": [{"type": "rest", "durationType": "whole", "beat": 0.0, "durationBeats": 3.0, "chord": "Rest", "solfege": "休"}]},
    {"measure": 3, "events": [{"type": "rest", "durationType": "whole", "beat": 0.0, "durationBeats": 3.0, "chord": "Rest", "solfege": "休"}]},
    {"measure": 4, "events": [{"type": "note", "pitch": "D3", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "Dm", "solfege": "Re"}]},
    {"measure": 5, "events": [{"type": "note", "pitch": "G2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "G7", "solfege": "Sol"}]},
    {"measure": 6, "events": [{"type": "note", "pitch": "C3", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "C", "solfege": "Do"}]},
    {"measure": 7, "events": [{"type": "note", "pitch": "A2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "Am", "solfege": "La"}]},
    {"measure": 8, "events": [{"type": "note", "pitch": "F2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "F", "solfege": "Fa"}]},
    {"measure": 9, "events": [{"type": "note", "pitch": "G2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "G7", "solfege": "Sol"}]},
    {"measure": 10, "events": [{"type": "note", "pitch": "C3", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "C", "solfege": "Do"}]},
    {"measure": 11, "events": [{"type": "note", "pitch": "F2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "F", "solfege": "Fa"}]},
    {"measure": 12, "events": [{"type": "note", "pitch": "G2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "G7", "solfege": "Sol"}]},
    {"measure": 13, "events": [{"type": "note", "pitch": "C3", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "C", "solfege": "Do"}]},
    {"measure": 14, "events": [{"type": "note", "pitch": "F2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "F", "solfege": "Fa"}]},
    {"measure": 15, "events": [{"type": "note", "pitch": "C3", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "C", "solfege": "Do"}]},
    {"measure": 16, "events": [{"type": "note", "pitch": "F2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "F", "solfege": "Fa"}]},
    {"measure": 17, "events": [{"type": "note", "pitch": "G2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "G7", "solfege": "Sol"}]},
    {"measure": 18, "events": [{"type": "note", "pitch": "C3", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "C", "solfege": "Do"}]},
    {"measure": 19, "events": [{"type": "rest", "durationType": "whole", "beat": 0.0, "durationBeats": 3.0, "chord": "Rest", "solfege": "休"}]},
    {"measure": 20, "events": [{"type": "note", "pitch": "D3", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "Dm", "solfege": "Re"}]},
    {"measure": 21, "events": [{"type": "note", "pitch": "G2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "G7", "solfege": "Sol"}]},
    {"measure": 22, "events": [{"type": "note", "pitch": "C3", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "C", "solfege": "Do"}]},
    {"measure": 23, "events": [{"type": "note", "pitch": "A2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "Am", "solfege": "La"}]},
    {"measure": 24, "events": [{"type": "note", "pitch": "F2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "F", "solfege": "Fa"}]},
    {"measure": 25, "events": [{"type": "note", "pitch": "G2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "G7", "solfege": "Sol"}]},
    {"measure": 26, "events": [{"type": "note", "pitch": "C3", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "C", "solfege": "Do"}]},
    {"measure": 27, "events": [{"type": "note", "pitch": "F2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "F", "solfege": "Fa"}]},
    {"measure": 28, "events": [{"type": "note", "pitch": "G2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "G7", "solfege": "Sol"}]},
    {"measure": 29, "events": [{"type": "note", "pitch": "C3", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "C", "solfege": "Do"}]},
    {"measure": 30, "events": [{"type": "note", "pitch": "F2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "F", "solfege": "Fa"}]},
    {"measure": 31, "events": [{"type": "note", "pitch": "C3", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "C", "solfege": "Do"}]},
    {"measure": 32, "events": [{"type": "note", "pitch": "F2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "F", "solfege": "Fa"}]},
    {"measure": 33, "events": [{"type": "note", "pitch": "G2", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "G7", "solfege": "Sol"}]},
    {"measure": 34, "events": [{"type": "note", "pitch": "C3", "durationType": "dotted-half", "beat": 0.0, "durationBeats": 3.0, "chord": "C", "solfege": "Do"}]},
]

# Mode 2 & Mode 3 Design Blueprints (Preserved for future upgrade)
LEFT_HAND_MODE_2_BLUEPRINT = """
Mode 2: 1892 经典圆舞曲“澎-恰-恰” (Boom-Chic-Chic)
- Beat 1: 低音单音根音 (如 C3 / G2 / F2，四分音符)
- Beat 2: 中音区双音/三音和弦 (如 [E3,G3] 或 [F3,A3] 或 [F3,G3,B3]，四分音符跳音)
- Beat 3: 中音区双音/三音和弦 (同 Beat 2，四分音符跳音)
"""

LEFT_HAND_MODE_3_BLUEPRINT = """
Mode 3: 抒情分解和弦 (Arpeggiated Waltz)
- Beat 1: 低音根音 (如 C3，四分音符)
- Beat 2: 和弦五音 (如 G3，四分音符)
- Beat 3: 和弦三音 (如 E4，四分音符)
"""

# Pitch to Bass Staff Y (Base: Line 5 A3 = 0, Staff Line 4 F3 = 25, Line 1 G2 = 100)
BASS_PITCH_Y = {
    "A3": 0.0,    # Line 5
    "G3": 12.5,   # Space 4
    "F3": 25.0,   # Line 4 (F-Clef Line)
    "E3": 37.5,   # Space 3
    "D3": 50.0,   # Line 3
    "C3": 62.5,   # Space 2
    "B2": 75.0,   # Line 2
    "A2": 87.5,   # Space 1
    "G2": 100.0,  # Line 1
    "F2": 112.5,  # Space below Line 1
    "E2": 125.0,  # Ledger Line 1 below Line 1
}

TREBLE_PITCH_Y = {
    "B4": 50.0,
    "A4": 62.5,
    "G4": 75.0,
    "F4": 87.5,
    "E4": 100.0,
    "D4": 112.5,
    "C4": 125.0,
}

PITCH_FREQ = {
    "F2": 87.31,
    "G2": 98.00,
    "A2": 110.00,
    "B2": 123.47,
    "C3": 130.81,
    "D3": 146.83,
    "E3": 164.81,
    "F3": 174.61,
    "G3": 196.00,
    "A3": 220.00,
    "B3": 246.94,
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


def generate_grand_staff_svg() -> str:
    svg_width = 1200
    system_height = 410
    top_header_height = 145
    total_systems = len(SYSTEM_MEASURES_MAP)
    svg_height = top_header_height + total_systems * system_height + 40

    treble_offset_y = 0.0
    bass_offset_y = 210.0 # 110px generous space for RH badges, lyrics, middle C ledger

    svg_parts = []
    svg_parts.append(f'''<svg viewBox="0 0 {svg_width} {svg_height}" width="100%" height="{svg_height}" xmlns="http://www.w3.org/2000/svg" class="meloo-grand-score-svg">
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
      .system-bracket {{ stroke: #64748b; stroke-width: 4.0; fill: none; }}
      .system-brace-bar {{ stroke: #64748b; stroke-width: 2.5; }}
      .ledger-line {{ stroke: #94a3b8; stroke-width: 2.2; }}
      .measure-num {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 12px; font-weight: bold; fill: #38bdf8; text-anchor: start; }}
      .lyric-text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 12px; font-weight: 500; fill: #cbd5e1; text-anchor: middle; }}
      .pitch-badge-treble {{ font-family: monospace; font-size: 10px; font-weight: bold; fill: #38bdf8; text-anchor: middle; }}
      .pitch-badge-bass {{ font-family: monospace; font-size: 10px; font-weight: bold; fill: #a78bfa; text-anchor: middle; }}
      .hand-label {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 11px; font-weight: bold; fill: #64748b; }}
      .event-group {{ cursor: pointer; transition: transform 0.1s; }}
      .event-group:hover .smufl-char {{ fill: #38bdf8; }}
      .event-group.active .smufl-char {{ fill: #f59e0b !important; filter: drop-shadow(0 0 6px rgba(245, 158, 11, 0.8)); }}
      .event-group.active .pitch-badge-treble, .event-group.active .pitch-badge-bass {{ fill: #f59e0b; font-weight: 900; }}
    </style>
  </defs>

  <rect width="{svg_width}" height="{svg_height}" class="score-bg" />

  <!-- Grand Staff Score Header -->
  <g transform="translate(600, 45)">
    <text y="0" class="score-title">Daisy Bell (Bicycle Built for Two) — 双手大谱表 (Grand Staff)</text>
    <text y="28" class="score-sub">3/4 拍 | C大调 (100 BPM) | 右手旋律 (高音谱表) + 左手初学单音根音伴奏 (低音谱表)</text>
    <text y="48" class="score-sub">Meloo Rounded SMuFL 国际标准音乐字体库驱动 | 34 小节双手全谱</text>
  </g>
''')

    for sys_idx, (m_start, m_end) in enumerate(SYSTEM_MEASURES_MAP):
        sys_y = top_header_height + sys_idx * system_height
        sys_right_m = RIGHT_HAND_MEASURES[m_start - 1 : m_end]
        sys_left_m = LEFT_HAND_MODE_1[m_start - 1 : m_end]
        is_first_sys = (sys_idx == 0)
        is_last_sys = (sys_idx == len(SYSTEM_MEASURES_MAP) - 1)

        left_x = 45
        right_x = 1160

        clef_x = left_x + 15
        if is_first_sys:
            measures_start_x = left_x + 135
        else:
            measures_start_x = left_x + 85

        avail_width = right_x - measures_start_x
        num_m = len(sys_right_m)
        m_width = avail_width / num_m if not is_last_sys else avail_width / 4.0
        last_m_right_x = measures_start_x + num_m * m_width if is_last_sys else right_x

        svg_parts.append(f'  <!-- Grand System {sys_idx + 1} (Measures {m_start}–{m_end}) -->')
        svg_parts.append(f'  <g id="grand-system-{sys_idx + 1}" transform="translate(0, {sys_y})">')

        # 1. Grand Staff Left Bracket (spans from Treble Line 5 y=0 to Bass Line 1 y=250)
        svg_parts.append(f'    <line x1="{left_x}" y1="{treble_offset_y}" x2="{left_x}" y2="{bass_offset_y + 100}" class="system-brace-bar" />')
        svg_parts.append(f'    <line x1="{left_x - 6}" y1="{treble_offset_y}" x2="{left_x - 6}" y2="{bass_offset_y + 100}" class="system-bracket" />')

        # Hand Labels
        svg_parts.append(f'    <text x="{left_x - 32}" y="{treble_offset_y + 55}" class="hand-label">RH</text>')
        svg_parts.append(f'    <text x="{left_x - 32}" y="{bass_offset_y + 55}" class="hand-label">LH</text>')

        # 2. Treble Staff Lines (y = 0, 25, 50, 75, 100)
        for line_y in [0, 25, 50, 75, 100]:
            svg_parts.append(f'    <line x1="{left_x}" y1="{treble_offset_y + line_y}" x2="{last_m_right_x}" y2="{treble_offset_y + line_y}" class="staff-line" />')

        # 3. Bass Staff Lines (y = 150, 175, 200, 225, 250)
        for line_y in [0, 25, 50, 75, 100]:
            svg_parts.append(f'    <line x1="{left_x}" y1="{bass_offset_y + line_y}" x2="{last_m_right_x}" y2="{bass_offset_y + line_y}" class="staff-line" />')

        # 4. Clefs
        # Treble Clef (G4 baseline on line 2 y=75)
        svg_parts.append(f'    <text x="{clef_x}" y="{treble_offset_y + 75}" class="smufl-char">&#xE050;</text>')
        # Bass Clef (F3 baseline on line 4 y=25, which is bass_offset_y + 25)
        svg_parts.append(f'    <text x="{clef_x}" y="{bass_offset_y + 25}" class="smufl-char">&#xE062;</text>')

        # 5. Time Signatures in System 1 (3/4)
        if is_first_sys:
            # Treble 3/4
            svg_parts.append(f'    <text x="{left_x + 85}" y="{treble_offset_y + 25}" class="smufl-char">&#xE083;</text>')
            svg_parts.append(f'    <text x="{left_x + 85}" y="{treble_offset_y + 75}" class="smufl-char">&#xE084;</text>')
            # Bass 3/4
            svg_parts.append(f'    <text x="{left_x + 85}" y="{bass_offset_y + 25}" class="smufl-char">&#xE083;</text>')
            svg_parts.append(f'    <text x="{left_x + 85}" y="{bass_offset_y + 75}" class="smufl-char">&#xE084;</text>')

        # 6. Render Measures
        for i in range(num_m):
            m_num = sys_right_m[i]["measure"]
            m_left = measures_start_x + i * m_width
            m_right = m_left + m_width

            # Measure number
            svg_parts.append(f'    <text x="{m_left + 4}" y="{treble_offset_y - 16}" class="measure-num">{m_num}</text>')

            pad_left = 18.0
            pad_right = 16.0
            usable_w = m_width - pad_left - pad_right

            # --- Right Hand Events ---
            for ev in sys_right_m[i]["events"]:
                beat = ev["beat"]
                ev_type = ev["type"]
                dur_type = ev["durationType"]
                ev_x = m_left + pad_left + (beat / 3.0) * usable_w
                ev_id = f"rh-{m_num}-{beat}"

                svg_parts.append(f'    <g id="{ev_id}" class="event-group" data-hand="rh" data-measure="{m_num}" onclick="playSingleNote(\'{ev.get("pitch", "")}\', {ev.get("durationBeats", 1.0)})">')

                if ev_type == "note":
                    pitch = ev["pitch"]
                    note_y = treble_offset_y + TREBLE_PITCH_Y[pitch]

                    if pitch == "C4":
                        svg_parts.append(f'      <line x1="{ev_x - 8}" y1="{treble_offset_y + 125}" x2="{ev_x + 38}" y2="{treble_offset_y + 125}" class="ledger-line" />')

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
                        svg_parts.append(f'      <text x="{ev_x + 36.0}" y="{dot_y}" class="smufl-char">&#xE1E7;</text>')

                    badge_label = f"{pitch}"
                    svg_parts.append(f'      <text x="{ev_x + 16}" y="{treble_offset_y + 146}" class="pitch-badge-treble">{badge_label}</text>')
                    if ev.get("lyric"):
                        svg_parts.append(f'      <text x="{ev_x + 16}" y="{treble_offset_y + 174}" class="lyric-text">{ev["lyric"]}</text>')

                elif ev_type == "rest":
                    svg_parts.append(f'      <text x="{ev_x}" y="{treble_offset_y + 50}" class="smufl-char">&#xE4E5;</text>')

                svg_parts.append('    </g>')

            # --- Left Hand Events (Mode 1: Dotted Half Note Root) ---
            for ev_lh in sys_left_m[i]["events"]:
                ev_type_lh = ev_lh["type"]
                beat_lh = ev_lh["beat"]
                ev_x_lh = m_left + pad_left + (beat_lh / 3.0) * usable_w
                ev_id_lh = f"lh-{m_num}-{beat_lh}"

                svg_parts.append(f'    <g id="{ev_id_lh}" class="event-group" data-hand="lh" data-measure="{m_num}" onclick="playSingleNote(\'{ev_lh.get("pitch", "")}\', {ev_lh.get("durationBeats", 3.0)})">')

                if ev_type_lh == "note":
                    pitch_lh = ev_lh["pitch"]
                    note_y_lh = bass_offset_y + BASS_PITCH_Y[pitch_lh]

                    # Mode 1 uses Dotted Half Note (noteHalfUp \uE1D3 + augmentationDot \uE1E7)
                    glyph_lh = "&#xE1D3;"
                    svg_parts.append(f'      <text x="{ev_x_lh}" y="{note_y_lh}" class="smufl-char">{glyph_lh}</text>')

                    # Dot sits in space
                    dot_y_lh = note_y_lh - 12.5 if pitch_lh in ["G2", "B2", "D3", "F3", "A3"] else note_y_lh
                    svg_parts.append(f'      <text x="{ev_x_lh + 36.0}" y="{dot_y_lh}" class="smufl-char">&#xE1E7;</text>')

                    chord_label = f"{ev_lh.get('chord', '')} ({pitch_lh})"
                    svg_parts.append(f'      <text x="{ev_x_lh + 22}" y="{bass_offset_y + 140}" class="pitch-badge-bass">{chord_label}</text>')

                elif ev_type_lh == "rest":
                    # Whole Measure Rest (hangs from Line 4 y=25 in Bass staff)
                    svg_parts.append(f'      <text x="{ev_x_lh + 20}" y="{bass_offset_y + 25}" class="smufl-char">&#xE4E3;</text>')
                    svg_parts.append(f'      <text x="{ev_x_lh + 32}" y="{bass_offset_y + 140}" class="pitch-badge-bass" style="fill:#64748b;">休止</text>')

                svg_parts.append('    </g>')

            # Connecting Grand Barlines (through both Treble & Bass)
            if i == num_m - 1 and is_last_sys:
                # Double barline for Grand Staff
                svg_parts.append(f'    <line x1="{last_m_right_x - 8}" y1="{treble_offset_y}" x2="{last_m_right_x - 8}" y2="{treble_offset_y + 100}" class="bar-line" />')
                svg_parts.append(f'    <line x1="{last_m_right_x - 8}" y1="{bass_offset_y}" x2="{last_m_right_x - 8}" y2="{bass_offset_y + 100}" class="bar-line" />')
                svg_parts.append(f'    <line x1="{last_m_right_x}" y1="{treble_offset_y}" x2="{last_m_right_x}" y2="{treble_offset_y + 100}" class="final-bar-thick" />')
                svg_parts.append(f'    <line x1="{last_m_right_x}" y1="{bass_offset_y}" x2="{last_m_right_x}" y2="{bass_offset_y + 100}" class="final-bar-thick" />')
            else:
                # Single barline through both staves
                svg_parts.append(f'    <line x1="{m_right}" y1="{treble_offset_y}" x2="{m_right}" y2="{treble_offset_y + 100}" class="bar-line" />')
                svg_parts.append(f'    <line x1="{m_right}" y1="{bass_offset_y}" x2="{m_right}" y2="{bass_offset_y + 100}" class="bar-line" />')

        svg_parts.append('  </g>\n')

    svg_parts.append('</svg>')
    return '\n'.join(svg_parts)


def generate_grand_staff_html() -> str:
    svg_content = generate_grand_staff_svg()
    rh_json = json.dumps(RIGHT_HAND_MEASURES, ensure_ascii=False)
    lh_json = json.dumps(LEFT_HAND_MODE_1, ensure_ascii=False)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Bicycle Built for Two (双手大谱表) — Meloo Rounded SMuFL</title>
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
      --purple: #a78bfa;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --score-bg: #0b1120;
    }}

    body.theme-light {{
      --bg-main: #f1f5f9;
      --card-bg: #ffffff;
      --card-border: #cbd5e1;
      --accent: #0284c7;
      --accent-glow: rgba(2, 132, 199, 0.3);
      --purple: #7c3aed;
      --text-main: #0f172a;
      --text-muted: #64748b;
      --score-bg: #ffffff;
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

    .badge-purple {{
      background: #5b21b6;
      color: #ede9fe;
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

    .track-selector {{
      display: flex;
      align-items: center;
      background: rgba(0,0,0,0.2);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 3px;
      gap: 4px;
    }}

    .track-btn {{
      background: transparent;
      color: var(--text-muted);
      padding: 6px 12px;
      font-size: 12px;
      border-radius: 6px;
      cursor: pointer;
    }}

    .track-btn.active {{
      background: var(--accent);
      color: #0b1120;
      font-weight: bold;
    }}

    .slider-group {{
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 13px;
      color: var(--text-muted);
    }}

    .slider-group input[type="range"] {{
      width: 120px;
      accent-color: var(--accent);
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

    body.theme-light .score-bg {{ fill: #ffffff !important; }}
    body.theme-light .smufl-char {{ fill: #0f172a !important; }}
    body.theme-light .staff-line {{ stroke: #94a3b8 !important; }}
    body.theme-light .bar-line {{ stroke: #475569 !important; }}
    body.theme-light .final-bar-thick {{ stroke: #0f172a !important; }}
    body.theme-light .ledger-line {{ stroke: #64748b !important; }}
    body.theme-light .lyric-text {{ fill: #334155 !important; }}
    body.theme-light .score-title {{ fill: #0369a1 !important; }}
    body.theme-light .score-sub {{ fill: #64748b !important; }}
    body.theme-light .system-bracket, body.theme-light .system-brace-bar {{ stroke: #475569 !important; }}

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

    .mode-note-card {{
      margin-top: 20px;
      padding: 18px 24px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
    }}
    .mode-note-card h3 {{
      margin: 0 0 10px 0;
      color: var(--purple);
      font-size: 15px;
    }}
    .mode-note-card p {{
      margin: 0 0 8px 0;
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.6;
    }}
    .mode-note-card code {{
      background: rgba(0,0,0,0.3);
      padding: 2px 6px;
      border-radius: 4px;
      color: var(--accent);
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="header-left">
        <h1>
          🎼 Bicycle Built for Two (双手大谱表)
          <span class="badge-tag">模式 1：初学单音伴奏</span>
          <span class="badge-tag badge-purple">Grand Staff</span>
        </h1>
        <p>高音谱表（右手旋律 C4–B4） + 低音谱表（左手单音和弦根音 F2–D3） | 3/4 拍 | 100 BPM | 34 小节双手合奏</p>
      </div>
      <div class="btn-group">
        <button class="btn-secondary" onclick="toggleTheme()">🌓 明/暗主题</button>
        <button class="btn-secondary" onclick="window.print()">🖨️ 打印大谱表</button>
        <button class="btn-secondary" onclick="downloadSVG()">📥 下载 SVG</button>
      </div>
    </header>

    <div class="controls-panel">
      <div class="btn-group">
        <button id="btn-play" onclick="togglePlay()">▶ 播放双手合奏 (Play)</button>
        <button class="btn-secondary" onclick="stopPlayback()">⏹ 停止</button>
        <button class="btn-secondary" onclick="resetToStart()">⏮ 复位</button>
      </div>

      <div class="track-selector">
        <span style="font-size:12px; color:var(--text-muted); margin: 0 6px;">音轨:</span>
        <button class="track-btn active" id="track-both" onclick="setTrack('both')">双手合奏 (Both)</button>
        <button class="track-btn" id="track-rh" onclick="setTrack('rh')">仅右手 (RH)</button>
        <button class="track-btn" id="track-lh" onclick="setTrack('lh')">仅左手 (LH)</button>
      </div>

      <div class="slider-group">
        <span>速度:</span>
        <input type="range" id="tempo-slider" min="40" max="180" value="100" oninput="updateTempo(this.value)">
        <span id="tempo-text" style="color:var(--accent); font-weight:bold; font-family:monospace;">100 BPM</span>
      </div>
    </div>

    <!-- Grand Staff Viewer -->
    <div class="score-wrapper">
      {svg_content}
    </div>

    <!-- Status Bar -->
    <div class="status-bar">
      <div>当前小节: <strong id="cur-measure" style="color:var(--accent);">1</strong> / 34 | 双手状态: <strong id="cur-hands" style="color:var(--purple);">准备就绪</strong></div>
      <div style="font-family:monospace; color:var(--text-muted);">Meloo Rounded SMuFL 大谱表 | 支持点击任意音符单音/和弦试听</div>
    </div>

    <!-- Upgrade Modes Documentation Box -->
    <div class="mode-note-card">
      <h3>🚀 进阶模式备忘录 (Accompaniment Upgrade Roadmap)</h3>
      <p><strong>当前运行模式：模式 1（初学单音根音）</strong> — 左手每小节弹奏一个稳定的附点二分音符低音根音（如 <code>C3(h.)</code>、<code>G2(h.)</code>、<code>F2(h.)</code>、<code>Dm(D3)</code>、<code>Am(A2)</code>），手型稳定，适合单八度右手旋律的初学者建立和声感。</p>
      <p><strong>进阶模式 2（1892 经典圆舞曲“澎-恰-恰”）</strong> — 第 1 拍弹奏单音低音根音，第 2、3 拍弹奏中音区双音/三音跳音和弦（如 <code>C3</code> + <code>[E3,G3]</code> + <code>[E3,G3]</code>），还原 19 世纪音乐厅纯正圆舞曲舞步律动。</p>
      <p><strong>进阶模式 3（抒情流水分解和弦）</strong> — 第 1 拍低音根音、第 2 拍五音、第 3 拍三音（如 <code>C3 -> G3 -> E4</code>），形成流畅优美的琶音背景。</p>
    </div>
  </div>

  <script>
    const RIGHT_HAND = {rh_json};
    const LEFT_HAND = {lh_json};
    const PITCH_FREQ = {json.dumps(PITCH_FREQ)};

    let audioCtx = null;
    let isPlaying = false;
    let currentBPM = 100;
    let currentMeasureIdx = 0;
    let playbackTimeoutId = null;
    let activeTrack = 'both'; // 'both' | 'rh' | 'lh'

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

    // Multi-Harmonic Warm Piano Synthesizer (Polyphonic)
    function playTone(pitch, durationSec, volume = 0.35, hand = 'rh') {{
      const freq = PITCH_FREQ[pitch];
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
      masterGain.gain.linearRampToValueAtTime(volume, now + attack);
      masterGain.gain.exponentialRampToValueAtTime(sustainLevel * volume, now + attack + decay);
      masterGain.gain.setValueAtTime(sustainLevel * volume, now + durationSec);
      masterGain.gain.exponentialRampToValueAtTime(0.0001, now + durationSec + release);

      // Fundamental
      const osc1 = ctx.createOscillator();
      osc1.type = hand === 'lh' ? 'triangle' : 'triangle';
      osc1.frequency.setValueAtTime(freq, now);
      osc1.connect(masterGain);
      osc1.start(now);
      osc1.stop(now + durationSec + release);

      // 2nd Harmonic
      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      gain2.gain.value = hand === 'lh' ? 0.20 : 0.30;
      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(freq * 2, now);
      osc2.connect(gain2);
      gain2.connect(masterGain);
      osc2.start(now);
      osc2.stop(now + durationSec + release);
    }}

    function playSingleNote(pitch, durBeats) {{
      if (!pitch) return;
      const beatSec = 60.0 / currentBPM;
      playTone(pitch, durBeats * beatSec, 0.4);
    }}

    function highlightMeasure(measureNum) {{
      document.querySelectorAll('.event-group.active').forEach(el => el.classList.remove('active'));

      if (measureNum !== null) {{
        document.querySelectorAll(`[data-measure="${{measureNum}}"]`).forEach(el => {{
          el.classList.add('active');
        }});
        document.getElementById('cur-measure').textContent = measureNum;
        const firstEl = document.querySelector(`[data-measure="${{measureNum}}"]`);
        if (firstEl) {{
          const bbox = firstEl.getBoundingClientRect();
          if (bbox.top < 60 || bbox.bottom > window.innerHeight - 60) {{
            firstEl.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
          }}
        }}
      }}
    }}

    function stepMeasurePlayback() {{
      if (!isPlaying) return;

      if (currentMeasureIdx >= RIGHT_HAND.length) {{
        stopPlayback();
        return;
      }}

      const mRH = RIGHT_HAND[currentMeasureIdx];
      const mLH = LEFT_HAND[currentMeasureIdx];
      const measureNum = mRH.measure;
      const beatSec = 60.0 / currentBPM;
      const measureSec = 3.0 * beatSec;

      highlightMeasure(measureNum);

      // Play Right Hand
      if (activeTrack === 'both' || activeTrack === 'rh') {{
        mRH.events.forEach(ev => {{
          if (ev.type === 'note') {{
            setTimeout(() => {{
              if (isPlaying) playTone(ev.pitch, ev.durationBeats * beatSec, 0.38, 'rh');
            }}, ev.beat * beatSec * 1000);
          }}
        }});
      }}

      // Play Left Hand (Mode 1: Dotted Half Note)
      if (activeTrack === 'both' || activeTrack === 'lh') {{
        mLH.events.forEach(ev => {{
          if (ev.type === 'note') {{
            setTimeout(() => {{
              if (isPlaying) playTone(ev.pitch, ev.durationBeats * beatSec * 0.95, 0.32, 'lh');
            }}, ev.beat * beatSec * 1000);
          }}
        }});
      }}

      currentMeasureIdx++;
      playbackTimeoutId = setTimeout(stepMeasurePlayback, measureSec * 1000);
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
        stepMeasurePlayback();
      }}
    }}

    function stopPlayback() {{
      isPlaying = false;
      if (playbackTimeoutId) {{
        clearTimeout(playbackTimeoutId);
        playbackTimeoutId = null;
      }}
      const btn = document.getElementById('btn-play');
      btn.textContent = '▶ 播放双手合奏 (Play)';
      btn.style.background = 'var(--accent)';
      highlightMeasure(null);
    }}

    function resetToStart() {{
      stopPlayback();
      currentMeasureIdx = 0;
      highlightMeasure(1);
    }}

    function setTrack(track) {{
      activeTrack = track;
      document.querySelectorAll('.track-btn').forEach(btn => btn.classList.remove('active'));
      document.getElementById('track-' + track).classList.add('active');
    }}

    function updateTempo(val) {{
      currentBPM = Number(val);
      document.getElementById('tempo-text').textContent = val + ' BPM';
    }}

    function toggleTheme() {{
      document.body.classList.toggle('theme-light');
    }}

    function downloadSVG() {{
      const svgEl = document.querySelector('.meloo-grand-score-svg');
      if (!svgEl) return;
      const svgData = new XMLSerializer().serializeToString(svgEl);
      const blob = new Blob([svgData], {{ type: 'image/svg+xml;charset=utf-8' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'bicycle-built-for-two-grand-staff.svg';
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
    print("Generating Grand Staff (大谱表) for Bicycle Built for Two...")
    svg_content = generate_grand_staff_svg()
    html_content = generate_grand_staff_html()

    svg_path = MOONLIGHT_DOCS / "bicycle-built-for-two-grand-staff.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    print(f"[OK] Saved Grand Staff SVG to {svg_path}")

    html_path = MOONLIGHT_DOCS / "bicycle-built-for-two-grand-staff.html"
    html_path.write_text(html_content, encoding="utf-8")
    print(f"[OK] Saved Grand Staff HTML to {html_path}")


if __name__ == "__main__":
    main()
