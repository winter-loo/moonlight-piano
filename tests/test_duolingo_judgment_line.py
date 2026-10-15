"""The translucent judgment band survives a note crossing its center."""

import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np


SCRIPT = Path(__file__).parents[1] / "scripts" / "duolingo-read-screen-notes.py"
SPEC = importlib.util.spec_from_file_location("duolingo_reader_judgment_test", SCRIPT)
reader = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reader
SPEC.loader.exec_module(reader)


class JudgmentLineTest(unittest.TestCase):
    def test_crossing_note_does_not_turn_a_left_stem_into_judgment_line(self):
        image = np.full((720, 1612, 3), 255, dtype=np.uint8)
        image[105:365, 398:416] = 240
        image[200:340, 403:411] = 100  # a note breaks the band in the middle
        image[105:365, 288:292] = 230  # a distracting old note to the left
        self.assertLessEqual(abs(reader.locate_judgment_line(image) - 407), 2)


if __name__ == "__main__":
    unittest.main()
