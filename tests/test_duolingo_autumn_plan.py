import json
import unittest
from collections import Counter
from pathlib import Path


PLAN_PATH = (
    Path(__file__).parents[1]
    / "tests/fixtures/duolingo-frozen-plans/autumn-frozen-plan.json"
)

# Independent 4/4 transcription used as the timing oracle, taken from
# docs/practiced-songs/001-autumn.md.  ``None`` denotes a rest so every measure
# documents all four beats, not just the notes sent to Android.
#
# Bar 1's A4 is the launch note: the challenge prints "在琴键上弹 A 开始" and
# only starts scrolling once it is played, so bars 1-2 are almost all rest.
MEASURES = (
    (("A4", 1), (None, 3)),
    ((None, 4),),
    (("A4", .5), ("A4", .5), ("A4", .5), ("Bb4", .5), ("A4", 1), ("A4", .5), ("Bb4", .5)),
    (("A4", .5), ("A4", .5), ("A4", .5), ("Bb4", .5), ("A4", 1), ("A4", .5), ("Bb4", .5)),
    (("A4", 1), ("Bb4", .5), ("A4", .5), ("G4", 2)),
    (("A4", .5), ("A4", .5), ("A4", .5), ("Bb4", .5), ("A4", 1), ("A4", .5), ("Bb4", .5)),
    (("A4", .5), ("A4", .5), ("A4", .5), ("Bb4", .5), ("A4", 1), ("A4", .5), ("Bb4", .5)),
    (("A4", 1), ("Bb4", .5), ("A4", .5), ("G4", 2)),
    (("A4", .5), ("A4", .5), ("A4", .5), ("C5", .5), ("D5", 2)),
    (("G4", .5), ("G4", .5), ("G4", .5), ("Bb4", .5), ("C5", 2)),
    (("A4", .5), ("A4", .5), ("A4", .5), ("Bb4", .5),
     ("A4", .5), ("A4", .5), ("A4", .5), ("Bb4", .5)),
    (("A4", .5), ("A4", .5), ("A4", .5), ("Bb4", .5), ("A4", 1), ("Bb4", .5), ("G4", .5)),
    (("F4", 2), (None, 2)),
)

def transcribed_events():
    events = []
    beat = 0.0
    for number, measure in enumerate(MEASURES, start=1):
        if sum(d for _, d in measure) != 4:
            raise AssertionError(f"measure {number} does not hold four beats")
        for pitch, duration in measure:
            if pitch is not None:
                events.append(
                    {"start_beat": beat, "pitch": pitch, "duration_beats": duration}
                )
            beat += duration
    return events


class AutumnFrozenPlanTest(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    def test_all_4_4_measures_match_the_frozen_plan(self):
        self.assertEqual(13, len(MEASURES))
        self.assertEqual(63, len(self.plan["events"]))
        self.assertEqual(transcribed_events(), self.plan["events"])

    def test_archived_note_and_duration_statistics(self):
        events = transcribed_events()
        self.assertEqual(
            {"A4": 38, "Bb4": 15, "G4": 6, "C5": 2, "D5": 1, "F4": 1},
            dict(Counter(e["pitch"] for e in events)),
        )
        self.assertEqual({0.5: 50, 1: 8, 2: 5}, dict(Counter(e["duration_beats"] for e in events)))
        sounded = sum(e["duration_beats"] for e in events)
        self.assertEqual(43, sounded)
        self.assertEqual(52, 4 * len(MEASURES))
        self.assertEqual(9, 4 * len(MEASURES) - sounded)

    def test_stop_boundary_matches_the_last_valid_event(self):
        index = self.plan["last_valid_event_index"]
        last = self.plan["events"][index]
        self.assertEqual(62, index)
        self.assertEqual(len(self.plan["events"]) - 1, index)
        self.assertEqual("F4", last["pitch"])
        self.assertEqual("F4", self.plan["last_valid_pitch"])
        self.assertEqual(48, last["start_beat"])
        self.assertEqual(50, last["start_beat"] + last["duration_beats"])
        self.assertEqual(50, self.plan["stop_after_beat"])
        # stop_after_beat bounds onsets, so the beat-48 down-stroke is admitted
        # while its beat-50 release is still honoured in full.
        self.assertLess(last["start_beat"], self.plan["stop_after_beat"])

    def test_every_pitch_exists_in_the_measured_keyboard_profile(self):
        import importlib.util
        import sys

        path = Path(__file__).parents[1] / "scripts/duolingo-timed-player.py"
        spec = importlib.util.spec_from_file_location("duolingo_timed_player_autumn", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        profile = module.KEYBOARD_PROFILES[self.plan["keyboard_profile"]]
        for event in self.plan["events"]:
            self.assertIn(event["pitch"], profile)


if __name__ == "__main__":
    unittest.main()
