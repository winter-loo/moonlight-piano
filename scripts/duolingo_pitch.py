"""Shared pitch spelling for the score reader and live player.

The signature applies to every octave of a letter.  An explicitly spelled
accidental takes precedence, so a later local accidental can be passed through
without being silently changed back by the key signature.
"""

from __future__ import annotations

import re

FLAT_ORDER = "BEADGCF"
SHARP_ORDER = "FCGDAEB"
_PITCH = re.compile(r"^([A-G])([b#n]?)([0-9]+)$")


def apply_key_signature(pitch: str, signature: tuple[int, int]) -> str:
    """Resolve a staff pitch to its physical key, preserving explicit signs."""
    flats, sharps = signature
    if not (0 <= flats <= 7 and 0 <= sharps <= 7) or (flats and sharps):
        raise ValueError(f"invalid key signature: {signature!r}")
    match = _PITCH.fullmatch(pitch)
    if match is None:
        raise ValueError(f"invalid score pitch: {pitch!r}")
    letter, accidental, octave = match.groups()
    if accidental:
        return f"{letter}{'' if accidental == 'n' else accidental}{octave}"
    sign = "b" if letter in FLAT_ORDER[:flats] else (
        "#" if letter in SHARP_ORDER[:sharps] else ""
    )
    return f"{letter}{sign}{octave}"
