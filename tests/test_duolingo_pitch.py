"""Regression coverage for signature-to-key conversion."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from duolingo_pitch import apply_key_signature


class SignaturePitchTest(unittest.TestCase):
    def test_every_flat_and_sharp_follows_score_order_in_all_octaves(self):
        for count in range(8):
            for letter in "ABCDEFG":
                for octave in (3, 4, 5):
                    pitch = f"{letter}{octave}"
                    flat = "b" if letter in "BEADGCF"[:count] else ""
                    sharp = "#" if letter in "FCGDAEB"[:count] else ""
                    self.assertEqual(f"{letter}{flat}{octave}",
                                     apply_key_signature(pitch, (count, 0)))
                    self.assertEqual(f"{letter}{sharp}{octave}",
                                     apply_key_signature(pitch, (0, count)))

    def test_explicit_accidental_overrides_signature(self):
        self.assertEqual("B4", apply_key_signature("Bn4", (4, 0)))
        self.assertEqual("B#4", apply_key_signature("B#4", (4, 0)))
        self.assertEqual("Eb5", apply_key_signature("Eb5", (0, 3)))

    def test_rejects_impossible_signature(self):
        with self.assertRaises(ValueError):
            apply_key_signature("C4", (2, 1))


if __name__ == "__main__":
    unittest.main()
