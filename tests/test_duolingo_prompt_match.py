"""A stopped score must be reanchored to the right repeated-note beat."""

import importlib.util
from pathlib import Path
import sys
import unittest
from PIL import Image, ImageDraw


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/duolingo-rehearse-song.py"
SPEC = importlib.util.spec_from_file_location("duolingo_rehearse_prompt_test", SCRIPT)
song = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = song
SPEC.loader.exec_module(song)


class PromptMatchTest(unittest.TestCase):
    def test_stopped_score_waits_for_prompt_to_appear(self):
        # Part 124 displayed its checkpoint after motion stopped. The old
        # two-beat timeout exited before the stable prompt was visible.
        self.assertEqual(2_800_000_000,
                         song.prompt_transition_grace_ns(350, 4))
        self.assertLess(700_000_000,
                        song.prompt_transition_grace_ns(350, 4))

    def test_prompt_note_must_stop_moving_before_restart(self):
        stable, candidate = song.stable_prompt_candidate(None, 53.0, 490, 1_000_000_000)
        self.assertFalse(stable)
        stable, candidate = song.stable_prompt_candidate(candidate, 53.0, 470, 1_300_000_000)
        self.assertFalse(stable)
        stable, candidate = song.stable_prompt_candidate(candidate, 52.0, 490, 1_500_000_000)
        self.assertFalse(stable)
        stable, candidate = song.stable_prompt_candidate(candidate, 52.0, 492, 1_800_000_000)
        self.assertFalse(stable)
        stable, _ = song.stable_prompt_candidate(candidate, 52.0, 492, 1_910_000_000)
        self.assertTrue(stable)

    def test_prompt_icon_excludes_a_moving_score(self):
        opening = Image.new("RGB", (200, 120), "white")
        ImageDraw.Draw(opening).line((107, 45, 147, 85), fill="gray", width=5)
        ImageDraw.Draw(opening).line((147, 45, 107, 85), fill="gray", width=5)
        paused = opening.copy()
        moving = Image.new("RGB", (200, 120), "white")
        ImageDraw.Draw(moving).line((115, 45, 115, 85), fill="gray", width=5)
        ImageDraw.Draw(moving).line((140, 45, 140, 85), fill="gray", width=5)
        self.assertTrue(song.has_start_prompt_icon(paused, opening))
        self.assertFalse(song.has_start_prompt_icon(moving, opening))

    def test_prompt_search_covers_checkpoint_rollback(self):
        self.assertEqual(12.0, song.prompt_search_floor(24.0, 3))
        self.assertEqual(21.0, song.prompt_search_floor(37.0, 4))
        self.assertEqual(23.5, song.prompt_search_ceiling(15.5, 16.0, 4))
        self.assertEqual(20.0, song.prompt_search_ceiling(13.0, 18.0, 3))

    def test_four_repeated_c_sharps_need_the_later_b_and_e(self):
        notes = [
            song.LedgerNote(beat, pitch, 1.0, None, 100,
                            relative_x_samples=[relative_x])
            for beat, pitch, relative_x in (
                (10.0, "C#5", 1485.0), (11.0, "C#5", 1627.0),
                (11.5, "C#5", 1697.5), (12.0, "C#5", 1773.0),
                (13.0, "C#5", 1918.0), (14.0, "C#5", 2060.5),
                (15.0, "C#5", 2200.5), (15.5, "B4", 2267.0),
                (16.0, "E5", 2348.25),
            )
        ]
        visible = [
            {"x": x, "pitch": pitch} for x, pitch in (
                (524.0, "C#5"), (659.0, "C#5"),
                (808.0, "C#5"), (942.0, "C#5"),
                (1011.0, "B4"), (1092.0, "E5"),
            )
        ]
        result = song.match_visible_prompt(
            visible, notes, judgment_x=499, screen_width=1612,
            sharps={"F", "C", "G"}, min_beat=9, max_beat=17,
        )
        self.assertIsNotNone(result)
        self.assertEqual(12.0, result[0].beat)

    def test_following_notes_disambiguate_a_repeated_c_sharp_prompt(self):
        notes = [
            song.LedgerNote(beat, pitch, duration, None, 100,
                            relative_x_samples=[relative_x])
            for beat, pitch, duration, relative_x in (
                (13.0, "C#5", 1.0, 1918.0),
                (14.0, "C#5", 1.0, 2060.5),
                (15.0, "C#5", 0.5, 2204.5),
                (15.5, "B4", 0.5, 2275.0),
                (16.0, "E5", 1.0, 2350.0),
            )
        ]
        visible = [
            {"x": 524.0, "pitch": "C#5"},
            {"x": 660.0, "pitch": "C#5"},
            {"x": 729.0, "pitch": "B4"},
            {"x": 805.0, "pitch": "E5"},
        ]
        result = song.match_visible_prompt(
            visible, notes, judgment_x=499, screen_width=1612,
            sharps={"F", "C", "G"}, min_beat=13, max_beat=17.5,
        )
        self.assertIsNotNone(result)
        self.assertEqual(14.0, result[0].beat)
        self.assertIsNone(song.match_visible_prompt(
            visible[:1], notes, judgment_x=499, screen_width=1612,
            sharps={"F", "C", "G"}, min_beat=13, max_beat=17.5,
        ))

    def test_part124_checkpoint_uses_the_visible_second_measure(self):
        # The stopped screen after beat 91 repeats an A4 phrase from beat 76.
        # Only beat 84 also has the A4 after the later G4 in this view.
        entries = (
            (76, "A4", 10988), (76.5, "A4", 11057),
            (77, "A4", 11132), (78, "A4", 11275),
            (79, "A4", 11418), (79.5, "A4", 11486),
            (80.5, "A4", 11629), (81.5, "A4", 11774),
            (82, "A4", 11851), (82.5, "G4", 11918),
            (84, "A4", 12137), (84.5, "A4", 12209),
            (85, "A4", 12288), (86, "A4", 12427),
            (87, "A4", 12570), (87.5, "A4", 12636),
            (88.5, "A4", 12783), (89.5, "A4", 12927),
            (90, "A4", 13004), (90.5, "G4", 13073),
            (91, "A4", 13149),
        )
        notes = [
            song.LedgerNote(beat, pitch, 1, None, 100,
                            relative_x_samples=[x])
            for beat, pitch, x in entries
        ]
        visible = [
            {"x": x, "pitch": "G4" if x == 1305 else "A4"}
            for x in (374, 434, 511, 650, 794, 868, 1011, 1151,
                      1227, 1305, 1379)
        ]
        result = song.match_visible_prompt(
            visible, notes, judgment_x=351, screen_width=1612,
            sharps=set(), min_beat=75, max_beat=99,
        )
        self.assertIsNotNone(result)
        self.assertEqual(84, result[0].beat)

    def test_measured_phrase_uses_its_first_sent_note(self):
        phrases = [(6.0, 13.0, 924.0)]
        self.assertIsNone(song.fixed_phrase_due_ns(9.0, phrases, {}))
        sent = {6.0: 10_000_000_000}
        self.assertEqual(12_772_000_000,
                         song.fixed_phrase_due_ns(9.0, phrases, sent))
        self.assertEqual(11_386_000_000,
                         song.fixed_phrase_due_ns(7.5, phrases, sent))
        self.assertIsNone(song.fixed_phrase_due_ns(14.0, phrases, sent))

    def test_prompt_rewind_requeues_sent_notes_after_the_visible_beat(self):
        played = {-2.0, 6.0, 7.0, 12.0, 13.0, 14.0}
        sent = {6.0: 1, 7.0: 2, 12.0: 3, 13.0: 4, 14.0: 5}
        song.rewind_played_beats(played, sent, 12.0)
        self.assertEqual({-2.0, 6.0, 7.0}, played)
        self.assertEqual({6.0: 1, 7.0: 2}, sent)


if __name__ == "__main__":
    unittest.main()
