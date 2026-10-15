import json
import unittest
from collections import Counter
from pathlib import Path


FIXTURE_DIR = (
    Path(__file__).parents[1]
    / "tests/fixtures/duolingo-frozen-plans"
)
CORRECTED_PLAN_PATH = FIXTURE_DIR / "musette-corrected-frozen-plan.json"
SUPERSEDED_PLAN_PATH = FIXTURE_DIR / "musette-frozen-plan.json"

# Independent 4/4 transcription used as the timing oracle, transcribed from
# docs/practiced-songs/014-musette-in-c-major.md.  ``None`` denotes a rest, so
# every measure documents all four beats rather than only the notes that
# happen to be sent to Android.
#
# The piece is 18 measures.  Measure 18 closes on a quarter rest after the
# B♭4 on beat 70: frame-by-frame review showed the app raised "要停顿" on the
# C5 that the original capture placed at beat 71, so that note and everything
# after it were tail garbage rather than score.
MEASURES = (
    (("D5", 1), (None, 3)),
    ((None, 4),),
    (("F5", 1), (None, 1), ("Eb5", 0.5), ("D5", 0.5), ("C5", 1)),
    (("F5", 1), (None, 1), ("Eb5", 0.5), ("D5", 0.5), ("C5", 1)),
    (("D5", 0.5), ("Eb5", 0.5), ("F5", 1), ("Eb5", 1), ("D5", 1)),
    (("C5", 1), ("F5", 1), ("D5", 1), ("Bb4", 1)),
    (("F5", 1), (None, 1), ("Eb5", 0.5), ("D5", 0.5), ("C5", 1)),
    (("F5", 1), (None, 1), ("Eb5", 0.5), ("D5", 0.5), ("C5", 1)),
    (("D5", 0.5), ("Eb5", 0.5), ("F5", 1), ("Eb5", 1), ("D5", 1)),
    (("C5", 1), ("F5", 1), ("Bb4", 2)),
    (("A4", 0.5), ("Bb4", 0.5), ("C5", 1), ("A4", 0.5), ("Bb4", 0.5), ("C5", 1)),
    (("F5", 1), ("C5", 1), ("C5", 2)),
    (("F5", 1), ("C5", 1), ("F5", 1), ("C5", 1)),
    (("Bb4", 0.5), ("A4", 0.5), ("G4", 1), ("G4", 1), ("C5", 1)),
    (("A4", 0.5), ("Bb4", 0.5), ("C5", 1), ("A4", 0.5), ("Bb4", 0.5), ("C5", 1)),
    (("F5", 1), ("C5", 1), ("C5", 2)),
    (("F5", 1), ("C5", 1), ("F5", 1), ("C5", 1)),
    (("A4", 0.5), ("Bb4", 0.5), ("C5", 1), ("Bb4", 1), (None, 1)),
)

# The ten tail events that the original capture appended past the real ending.
SUPERSEDED_TAIL = (
    {"start_beat": 71, "pitch": "C5", "duration_beats": 1},
    {"start_beat": 75, "pitch": "C5", "duration_beats": 1},
    {"start_beat": 76, "pitch": "F5", "duration_beats": 1},
    {"start_beat": 77, "pitch": "Bb4", "duration_beats": 2},
    {"start_beat": 79, "pitch": "A4", "duration_beats": 0.5},
    {"start_beat": 79.5, "pitch": "Bb4", "duration_beats": 0.5},
    {"start_beat": 80, "pitch": "C5", "duration_beats": 1},
    {"start_beat": 81, "pitch": "A4", "duration_beats": 0.5},
    {"start_beat": 81.5, "pitch": "Bb4", "duration_beats": 0.5},
    {"start_beat": 82, "pitch": "C5", "duration_beats": 1},
)


def transcribed_events():
    events = []
    beat = 0.0
    for measure_number, measure in enumerate(MEASURES, start=1):
        measure_duration = sum(duration for _, duration in measure)
        if measure_duration != 4:
            raise AssertionError(
                f"measure {measure_number} has {measure_duration:g} beats"
            )
        for pitch, duration in measure:
            if pitch is not None:
                events.append(
                    {
                        "start_beat": beat,
                        "pitch": pitch,
                        "duration_beats": duration,
                    }
                )
            beat += duration
    return events


class MusetteFrozenPlanTest(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(CORRECTED_PLAN_PATH.read_text(encoding="utf-8"))

    def test_all_4_4_measures_match_the_corrected_plan(self):
        self.assertEqual(18, len(MEASURES))
        self.assertEqual(69, len(self.plan["events"]))
        self.assertEqual(transcribed_events(), self.plan["events"])

    def test_archived_note_and_duration_statistics(self):
        """Pin the counts published in the song archive."""
        events = transcribed_events()
        durations = Counter(event["duration_beats"] for event in events)
        self.assertEqual({0.5: 24, 1: 42, 2: 3}, dict(durations))
        self.assertEqual(
            {"G4": 2, "A4": 6, "Bb4": 9, "C5": 20, "D5": 10, "Eb5": 8, "F5": 14},
            dict(Counter(event["pitch"] for event in events)),
        )
        sounded = sum(event["duration_beats"] for event in events)
        self.assertEqual(60, sounded)
        self.assertEqual(72, 4 * len(MEASURES))
        self.assertEqual(12, 4 * len(MEASURES) - sounded)

    def test_stop_boundary_matches_the_last_valid_event(self):
        index = self.plan["last_valid_event_index"]
        last = self.plan["events"][index]
        self.assertEqual(68, index)
        self.assertEqual(len(self.plan["events"]) - 1, index)
        self.assertEqual("Bb4", last["pitch"])
        self.assertEqual("Bb4", self.plan["last_valid_pitch"])
        self.assertEqual(70, last["start_beat"])
        self.assertEqual(71, last["start_beat"] + last["duration_beats"])
        self.assertEqual(71, self.plan["last_valid_release_beat"])
        # ``stop_after_beat`` bounds note onsets, so the beat-70 down-stroke is
        # admitted while its beat-71 release is still honoured in full.
        self.assertEqual(71, self.plan["stop_after_beat"])
        self.assertLess(last["start_beat"], self.plan["stop_after_beat"])

    def test_superseded_plan_exercises_tail_garbage_regression(self):
        """The fixture preserves the ten extra notes the gate must suppress."""
        superseded = json.loads(SUPERSEDED_PLAN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(79, len(superseded["events"]))
        boundary = self.plan["last_valid_event_index"] + 1
        self.assertEqual(self.plan["events"], superseded["events"][:boundary])
        self.assertEqual(list(SUPERSEDED_TAIL), superseded["events"][boundary:])
        self.assertEqual(
            len(SUPERSEDED_TAIL), self.plan["superseded_tail_event_count"]
        )
        self.assertEqual(SUPERSEDED_PLAN_PATH.name, self.plan["superseded_plan"])


if __name__ == "__main__":
    unittest.main()
