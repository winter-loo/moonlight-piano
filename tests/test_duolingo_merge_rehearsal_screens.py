"""Regression checks for overlapping stopped-screen score assembly."""

import importlib.util
import json
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/duolingo-merge-rehearsal-screens.py"
SPEC = importlib.util.spec_from_file_location("merge_rehearsal", SCRIPT)
MERGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MERGE)


def fake_run(name, notes, sent_beats):
    by_beat = defaultdict(list)
    for beat, pitch in notes:
        by_beat[float(beat)].append({"beat": float(beat), "pitch": pitch,
                                     "duration_beats": 1, "hold_beats": 0.8})
    return {"path": Path(name), "ledger": by_beat,
            "events": [by_beat[float(beat)][0] for beat in sent_beats]}


class MergeRehearsalScreensTest(unittest.TestCase):
    def test_replay_queue_excludes_separately_sent_opening_prompt(self):
        score = [{"beat": -4, "pitch": "A4"},
                 {"beat": 0, "pitch": "A4"},
                 {"beat": 1, "pitch": "F#4"}]
        self.assertEqual(MERGE.replay_queue(score), score[1:])
        self.assertEqual(len(score), 3)
        three_four = [{"beat": -3, "pitch": "E5"},
                      {"beat": -2, "pitch": "F#5"},
                      {"beat": 0, "pitch": "A5"}]
        self.assertEqual(MERGE.replay_queue(three_four), three_four[1:])

    def test_final_screen_adds_confirmed_unplayed_tail(self):
        run = fake_run("last", [(0, "F#4"), (0.5, "G#4"),
                                (1, "A4"), (2, "C#4"), (4, "B3")],
                       [0, 0.5, 1])
        run["ledger"][2.0][0]["sightings"] = 3
        run["ledger"][4.0][0]["sightings"] = 1
        notes, _ = MERGE.merge([run], 40)
        self.assertEqual([(note["beat"], note["pitch"]) for note in notes],
                         [(40, "F#4"), (40.5, "G#4"),
                          (41, "A4"), (42, "C#4")])

    def test_overlap_prefers_more_confirmed_duration_and_includes_gap(self):
        first = fake_run("first", [(0, "C#5"), (2, "E5"),
                                   (3, "F#5"), (4, "G#5")], [0, 2])
        second = fake_run("second", [(0, "E5"), (1, "F#5"),
                                     (2, "G#5")], [0, 1, 2])
        first["ledger"][3.0][0]["sightings"] = 8
        first["ledger"][4.0][0]["sightings"] = 8
        second["ledger"][1.0][0]["sightings"] = 3
        second["ledger"][1.0][0]["duration_beats"] = 2
        notes, _ = MERGE.merge([first, second], 0)
        self.assertEqual([(note["beat"], note["pitch"]) for note in notes],
                         [(0, "C#5"), (2, "E5"),
                          (3, "F#5"), (4, "G#5")])
        self.assertEqual(notes[2]["duration_beats"], 1)

    def test_repeated_phrase_requires_verified_advance(self):
        phrase = [(0, "A4"), (1, "B4"), (2, "C#5"), (3, "D5")]
        previous = fake_run("previous", phrase +
                            [(beat + 4, pitch) for beat, pitch in phrase] +
                            [(beat + 12, pitch) for beat, pitch in phrase],
                            [0, 1, 2, 3])
        following = fake_run("following", phrase, [0, 1, 2, 3])
        with self.assertRaisesRegex(ValueError, "ambiguous overlap"):
            MERGE.merge([previous, following], 0)
        notes, alignments = MERGE.merge([previous, following], 0,
                                         advances={1: 4})
        self.assertEqual(alignments[0]["advance_beats"], 4)
        self.assertEqual([note["beat"] for note in notes], [0, 1, 2, 3, 4, 5, 6, 7])

    def test_prefix_accepts_list_and_keeps_only_earlier_beats(self):
        previous = fake_run("previous", [(0, "A4"), (4, "B4"),
                                          (5, "C#5"), (6, "D5")], [0])
        following = fake_run("following", [(0, "B4"), (1, "C#5"),
                                            (2, "D5")], [0, 1, 2])
        with tempfile.TemporaryDirectory() as temp:
            prefix = Path(temp) / "prefix.json"
            prefix.write_text(json.dumps([
                {"beat": -1, "pitch": "G#4", "duration_beats": 1,
                 "hold_beats": 0.8},
                {"beat": 0, "pitch": "A4", "duration_beats": 1,
                 "hold_beats": 0.8},
            ]))
            notes, _ = MERGE.merge([previous, following], 0, prefix)
        self.assertEqual([note["beat"] for note in notes], [-1, 0, 4, 5, 6])


if __name__ == "__main__":
    unittest.main()
