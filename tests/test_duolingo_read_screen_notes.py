"""Regression tests for the Duolingo screen-note reader."""

import importlib.util
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image, ImageDraw


REPO_ROOT = Path(__file__).parents[1]
FIXTURE_DIR = REPO_ROOT / "tests/fixtures/duolingo-screen-reader"


def _load_reader():
    path = REPO_ROOT / "scripts/duolingo-read-screen-notes.py"
    spec = importlib.util.spec_from_file_location("duolingo_read_screen_notes", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


reader = _load_reader()


class CandidateSuppressionTest(unittest.TestCase):
    def test_prefers_noteheads_over_nearby_weaker_flag_candidates(self):
        strengths = np.zeros(1600)
        strengths[[1151, 1198, 1436, 1483]] = [1.67, 0.79, 1.67, 0.79]

        kept = reader.suppress_close_candidates(
            [1151, 1198, 1436, 1483], strengths, minimum_distance=55
        )

        self.assertEqual([1151, 1436], kept)


class HollowNoteCenterTest(unittest.TestCase):
    def test_uses_hollow_ellipse_instead_of_stem_weight_for_pitch(self):
        image = Image.new("RGB", (500, 420), "white")
        draw = ImageDraw.Draw(image)
        staff_ys = (144, 182, 220, 258, 296)
        for y in staff_ys:
            draw.line((80, y, 470, y), fill=(210, 210, 210), width=5)

        # E4 half note: its tall stem deliberately biases a raw dark-pixel
        # centroid upward toward F4, matching the real OPPO regression frame.
        draw.ellipse((348, 281, 390, 311), outline=(70, 70, 70), width=8)
        draw.line((386, 195, 386, 296), fill=(70, 70, 70), width=10)

        positions = {
            "F4": (277.0, "Space 1"),
            "E4": (296.0, "Line 1"),
            "D4": (315.0, "Space below Line 1"),
        }
        center = reader.refine_hollow_notehead_center(
            np.array(image), candidate_x=378, rough_center_y=283.0, positions=positions
        )

        self.assertIsNotNone(center)
        center_x, center_y = center
        self.assertAlmostEqual(369.0, center_x, delta=4.0)
        self.assertEqual(296.0, center_y)


class AugmentationDotTest(unittest.TestCase):
    def test_finds_round_dot_but_rejects_stem_and_next_notehead(self):
        image = Image.new("RGB", (320, 180), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((78, 86, 120, 114), fill=(70, 70, 70))
        draw.line((116, 35, 116, 100), fill=(70, 70, 70), width=6)
        draw.ellipse((134, 92, 149, 107), fill=(70, 70, 70))
        draw.ellipse((177, 86, 219, 114), fill=(70, 70, 70))

        dot = reader.find_augmentation_dot(
            np.array(image), center_x=99, center_y=100, next_note_x=198
        )

        self.assertIsNotNone(dot)
        self.assertAlmostEqual(141.5, dot[0], delta=1.0)
        self.assertAlmostEqual(99.5, dot[1], delta=1.0)


class KeyboardOverlapRegressionTest(unittest.TestCase):
    def test_keyboard_key_tops_are_not_reported_as_a3_notes(self):
        image = Image.new("RGB", (1612, 720), "white")
        draw = ImageDraw.Draw(image)
        for y in (144, 182, 220, 258, 296):
            draw.line((96, y, 1490, y), fill=(210, 210, 210), width=5)

        # A real, partially visible C4 entering at the right edge.  Keeping
        # this makes the regression prove that edge notes survive filtering.
        draw.line((1458, 334, 1512, 334), fill=(70, 70, 70), width=6)
        draw.ellipse((1468, 319, 1510, 349), fill=(70, 70, 70))

        # Rounded black-key tops overlap the A3 search band at y=372.  Before
        # the fix, five of these corners were emitted as quarter-note A3s.
        for left in (611, 744, 877, 1159, 1292):
            draw.rounded_rectangle(
                (left, 376, left + 100, 496), radius=16, fill=(70, 70, 70)
            )

        notes = reader.analyze_screen_notes(image, min_x=400)

        self.assertEqual(["C4"], [note["pitch"] for note in notes])
        self.assertTrue(notes[0]["edge_clipped"])
        self.assertIsNone(notes[0]["duration_beats"])


class RestDetectionTest(unittest.TestCase):
    def test_detects_quarter_half_and_eighth_rests_in_score_order(self):
        image = Image.new("RGB", (1612, 720), "white")
        draw = ImageDraw.Draw(image)
        staff_ys = (144, 182, 220, 258, 296)
        for y in staff_ys:
            draw.line((96, y, 1490, y), fill=(210, 210, 210), width=5)

        # Simplified silhouettes with the measured Duolingo glyph bounds.
        draw.line(
            ((556, 181), (568, 203), (551, 226), (566, 249), (556, 273)),
            fill=(165, 165, 165),
            width=12,
            joint="curve",
        )
        draw.rectangle((688, 200, 717, 217), fill=(165, 165, 165))
        draw.ellipse((1408, 186, 1431, 209), fill=(165, 165, 165))
        draw.line((1428, 200, 1418, 245), fill=(165, 165, 165), width=10)

        rests = reader.analyze_screen_rests(image, min_x=400)

        self.assertEqual(
            ["Quarter Rest (四分休止符)", "Half Rest (二分休止符)", "Eighth Rest (八分休止符)"],
            [rest["duration_type"] for rest in rests],
        )
        self.assertEqual([1.0, 2.0, 0.5], [rest["duration_beats"] for rest in rests])


class BidirectionalStemAndBeamTest(unittest.TestCase):
    def test_detects_connected_beams_without_direction_or_angle_assumptions(self):
        image = Image.open(
            FIXTURE_DIR / "bidirectional-stems-and-steep-beams.png"
        ).convert("RGB")

        notes = reader.analyze_screen_notes(image)

        self.assertEqual(
            ["up"] * 9 + ["down", "down", "down"],
            [note["stem_direction"] for note in notes],
        )
        self.assertEqual(
            [True, True, True, True, False, True, True, True, True, True, True, False],
            [note["has_beam"] for note in notes],
        )


class OccludedStemAndKeySignatureTest(unittest.TestCase):
    def test_two_flats_and_judgment_line_occluded_downstem(self):
        image = Image.open(
            FIXTURE_DIR / "two-flats-occluded-downstem.png"
        ).convert("RGB")

        notes = reader.analyze_screen_notes(image)

        self.assertEqual("Eb5", notes[0]["pitch"])
        self.assertEqual("down", notes[0]["stem_direction"])
        self.assertEqual("Bb4", notes[-1]["pitch"])


class SharedAnalysisContextTest(unittest.TestCase):
    def test_reuses_frame_geometry_for_notes_and_rests(self):
        image = Image.open(
            FIXTURE_DIR / "single-flat-mixed-rhythm-and-edge-note.png"
        ).convert("RGB")

        with (
            mock.patch.object(
                reader, "find_staff_lines", wraps=reader.find_staff_lines
            ) as find_staff_lines,
            mock.patch.object(
                reader, "locate_judgment_line", wraps=reader.locate_judgment_line
            ) as locate_judgment_line,
        ):
            context = reader.build_analysis_context(image)
            reader.analyze_screen_notes(context)
            reader.analyze_screen_rests(context)

        self.assertEqual(1, find_staff_lines.call_count)
        self.assertEqual(1, locate_judgment_line.call_count)


class RealScreenRegressionTest(unittest.TestCase):
    def test_manually_verified_screen_events(self):
        manifest = json.loads((FIXTURE_DIR / "expected.json").read_text())
        for case in manifest["cases"]:
            with self.subTest(image=case["image"]):
                image_path = FIXTURE_DIR / case["image"]
                self.assertEqual(case["sha256"], hashlib.sha256(image_path.read_bytes()).hexdigest())
                image = Image.open(image_path).convert("RGB")
                located_line = reader.locate_judgment_line(np.array(image))
                self.assertAlmostEqual(case["judgment_line_x"], located_line, delta=2)

                notes = reader.analyze_screen_notes(image)
                rests = reader.analyze_screen_rests(image)
                events = sorted([*notes, *rests], key=lambda event: event["x"])
                actual = [
                    [event["event_type"], event["pitch"], event["duration_beats"]]
                    for event in events
                ]

                self.assertEqual(case["events"], actual)

                if "known_duration_beats" in case:
                    known_duration = sum(
                        event["duration_beats"] or 0.0 for event in events
                    )
                    self.assertEqual(case["known_duration_beats"], known_duration)

                if "note_features" in case:
                    note_features = [
                        [
                            note["pitch"],
                            note["stem_direction"],
                            note["has_beam"],
                            note["has_flag"],
                            note["is_dotted"],
                            note["edge_clipped"],
                        ]
                        for note in notes
                    ]
                    self.assertEqual(case["note_features"], note_features)


if __name__ == "__main__":
    unittest.main()
