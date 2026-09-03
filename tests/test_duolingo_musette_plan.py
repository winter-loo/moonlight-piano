import json
import unittest
from pathlib import Path


PLAN_PATH = (
    Path(__file__).parents[1]
    / "outputs/duolingo-stage4-section14-musette/ultimate/musette-frozen-plan.json"
)

# Independent 4/4 transcription used as the timing oracle.  ``None`` denotes
# a rest, so every measure documents all four beats rather than only the notes
# that happen to be sent to Android.
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
    (("A4", 0.5), ("Bb4", 0.5), ("C5", 1), ("Bb4", 1), ("C5", 1)),
    ((None, 3), ("C5", 1)),
    (("F5", 1), ("Bb4", 2), ("A4", 0.5), ("Bb4", 0.5)),
    (("C5", 1), ("A4", 0.5), ("Bb4", 0.5), ("C5", 1), (None, 1)),
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
    def test_all_4_4_measures_match_the_frozen_plan(self):
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(21, len(MEASURES))
        self.assertEqual(79, len(plan["events"]))
        self.assertEqual(transcribed_events(), plan["events"])


if __name__ == "__main__":
    unittest.main()
