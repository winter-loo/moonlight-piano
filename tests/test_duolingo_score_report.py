"""A score report must not invent notes or lose rests."""

import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/duolingo-score-report.py"
SPEC = importlib.util.spec_from_file_location("duolingo_score_report_test", SCRIPT)
report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = report
SPEC.loader.exec_module(report)


class ScoreReportTest(unittest.TestCase):
    def test_joins_sent_keys_and_inserts_measured_rests(self):
        sent = [{"beat": 0, "pitch": "Bb3", "read_pitch": "Bb3"},
                {"beat": 2.5, "pitch": "C#4", "read_pitch": "C#4"}]
        ledger = [{"beat": 0, "pitch": "Bb3", "duration_beats": 1},
                  {"beat": 2.5, "pitch": "C#4", "duration_beats": .5}]
        events = report.score_events(sent, ledger)
        self.assertEqual([(0.0, "Bb3", 1.0), (2.5, "C#4", .5)], events)
        self.assertEqual((1, 0.0, 3.0, [
            ("Bb3", 0.0, 1.0), ("R", 1.0, 1.5), ("C#4", 2.5, .5),
        ]), report.measure_rows(events, 4)[0])
        self.assertLess(report.midi_number("Bb3"), report.midi_number("C4"))

    def test_rejects_unsupported_sent_note_instead_of_guessing_duration(self):
        with self.assertRaisesRegex(ValueError, "no unique ledger duration"):
            report.score_events([{"beat": 1, "pitch": "Db4"}], [])

    def test_matching_seed_and_live_readings_may_both_appear_in_ledger(self):
        sent = [{"beat": -1, "pitch": "Eb4"}]
        same_note = {"beat": -1, "pitch": "Eb4", "duration_beats": 1}
        self.assertEqual([(-1.0, "Eb4", 1.0)],
                         report.score_events(sent, [same_note, same_note]))
        with self.assertRaisesRegex(ValueError, "no unique ledger duration"):
            report.score_events(sent, [same_note, {**same_note, "duration_beats": 2}])

    def test_current_screen_duration_overrides_preloaded_seed(self):
        sent = [{"beat": 0, "pitch": "Bb4"}]
        live = {"beat": 0, "pitch": "Bb4", "duration_beats": 1.5, "sightings": 2}
        seed = {"beat": 0, "pitch": "Bb4", "duration_beats": 1, "sightings": 100}
        self.assertEqual([(0.0, "Bb4", 1.5)], report.score_events(sent, [live, seed]))


if __name__ == "__main__":
    unittest.main()
