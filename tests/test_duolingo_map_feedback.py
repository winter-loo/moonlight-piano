"""Timebase regression for archived Duolingo judgment feedback."""

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "duolingo_map_feedback", ROOT / "scripts/duolingo-map-feedback.py"
)
mapper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mapper
spec.loader.exec_module(mapper)


class FeedbackTimebaseTest(unittest.TestCase):
    def test_consecutive_late_banners_are_separate_events(self):
        observations = [
            {"grade": "迟了", "t_ms": t}
            for t in (1000.0, 1220.0, 1430.0, 1570.0, 1790.0)
        ]
        groups = mapper.feedback_groups(observations)
        self.assertEqual([1000.0, 1570.0],
                         [group["first_ms"] for group in groups])

    def test_fits_barline_offset_before_attributing_a_late_note(self):
        spacing = 576.0
        offset = 1800.0
        phase = [
            {"t_ms": float(t), "phase_px": 1038.0 - 0.2 * t,
             "spacing_px": spacing, "speed_px_s": 200.0,
             "state": "steady"}
            for t in range(0, 20001, 100)
        ]
        observations = [
            (float(t), (1038.0 - 0.2 * (t - offset)) % spacing)
            for t in range(4000, 17000, 500)
        ]
        fitted, error, ambiguous = mapper.fit_video_offset(
            observations, phase
        )
        self.assertAlmostEqual(offset, fitted, delta=10)
        self.assertLess(error, 1)
        self.assertTrue(ambiguous)  # One whole-measure alias also fits.

        feedback = [{"grade": "迟了", "t_ms": 5373.0}]
        played = [
            {"beat": 0.0, "pitch": "Db4", "sent_ms": 3164.0},
            {"beat": 2.0, "pitch": "Eb4", "sent_ms": 4516.0},
        ]
        mapped = mapper.map_feedback(
            feedback, played, video_offset_ms=fitted,
            timebase_ambiguous=ambiguous,
        )
        self.assertEqual(0.0, mapped[0]["beat"])
        self.assertEqual("Db4", mapped[0]["pitch"])
        self.assertTrue(mapped[0]["ambiguous"])


if __name__ == "__main__":
    unittest.main()
