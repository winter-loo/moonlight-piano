import json
import unittest
from collections import Counter
from pathlib import Path


PLAN_PATH = (
    Path(__file__).parents[1]
    / "tests/fixtures/duolingo-frozen-plans/tonight-frozen-plan.json"
)


class TonightFrozenPlanTest(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        self.events = self.plan["events"]

    def test_every_bar_holds_at_most_four_beats(self):
        """A 4/4 bar cannot sound more than four beats; rests make up the rest."""
        sounded = Counter()
        for event in self.events:
            sounded[int(event["start_beat"] // 4)] += event["duration_beats"]
        for bar, total in sorted(sounded.items()):
            self.assertLessEqual(total, 4.0, f"bar {bar+1} holds {total} beats")

    def test_no_note_sounds_across_a_barline(self):
        for event in self.events:
            bar_end = (int(event["start_beat"] // 4) + 1) * 4
            self.assertLessEqual(
                event["start_beat"] + event["duration_beats"], bar_end + 1e-9,
                f"{event} crosses a barline without a tie",
            )

    def test_notes_never_overlap(self):
        for a, b in zip(self.events, self.events[1:]):
            self.assertLessEqual(
                a["start_beat"] + a["duration_beats"], b["start_beat"] + 1e-9
            )
            self.assertLess(a["start_beat"], b["start_beat"])

    def test_archived_counts(self):
        self.assertEqual(83, len(self.events))
        self.assertEqual(20, self.plan["measure_count"])
        self.assertEqual(
            {"F4": 33, "Bb4": 17, "A4": 14, "C5": 9, "G4": 7, "D4": 2, "D5": 1},
            dict(Counter(e["pitch"] for e in self.events)),
        )
        self.assertEqual({1.0: 24, 0.5: 59}, dict(Counter(e["duration_beats"] for e in self.events)))
        self.assertEqual(53.5, sum(e["duration_beats"] for e in self.events))

    def test_stop_boundary_matches_the_last_valid_event(self):
        index = self.plan["last_valid_event_index"]
        last = self.events[index]
        self.assertEqual(len(self.events) - 1, index)
        self.assertEqual("F4", last["pitch"])
        self.assertEqual("F4", self.plan["last_valid_pitch"])
        self.assertEqual(76, last["start_beat"])
        self.assertEqual(77, self.plan["stop_after_beat"])
        self.assertLess(last["start_beat"], self.plan["stop_after_beat"])

    def test_every_pitch_exists_in_the_measured_keyboard_profile(self):
        import importlib.util
        import sys

        path = Path(__file__).parents[1] / "scripts/duolingo-timed-player.py"
        spec = importlib.util.spec_from_file_location("duolingo_timed_player_tonight", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        profile = module.KEYBOARD_PROFILES[self.plan["keyboard_profile"]]
        for event in self.events:
            self.assertIn(event["pitch"], profile)


if __name__ == "__main__":
    unittest.main()
