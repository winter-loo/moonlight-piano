"""The live clock must survive long scores without a song-specific BPM."""

import sys
from pathlib import Path
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from duolingo_live_clock import (
    KeyHighlightLatency, TempoReading, VisualBeatClock, VisualClockLost,
)


class VisualBeatClockTest(unittest.TestCase):
    def test_measure_motion_recovers_tempo_across_meters(self):
        for beats_per_measure, beat_ms, px_per_beat in (
            (3, 802.0, 144.0),
            (4, 661.0, 120.0),
        ):
            with self.subTest(meter=beats_per_measure, beat_ms=beat_ms):
                clock = VisualBeatClock(
                    anchor_ns=10_000_000_000,
                    anchor_beat=0.0,
                    beat_ms=beat_ms * 1.03,
                    px_per_beat=px_per_beat,
                    beats_per_measure=beats_per_measure,
                )
                reading = None
                for frame in range(90):
                    elapsed_ms = frame * beat_ms / 10
                    # Frame-arrival jitter changes the regression residual but
                    # must not make the long-window slope song-specific.
                    jitter_px = (frame % 5 - 2) * 0.7
                    phase = 900 - px_per_beat * elapsed_ms / beat_ms + jitter_px
                    reading = clock.observe(
                        10_000_000_000 + round(elapsed_ms * 1_000_000), phase
                    ) or reading
                self.assertIsNotNone(reading)
                self.assertLess(abs(reading.beat_ms - beat_ms), beat_ms * 0.005)
                self.assertGreater(reading.span_beats, beats_per_measure)

    def test_new_period_preserves_current_playhead_position(self):
        clock = VisualBeatClock(
            anchor_ns=1_000_000_000,
            anchor_beat=0.0,
            beat_ms=820.0,
            px_per_beat=144.0,
            beats_per_measure=3,
        )
        now_ns = 1_000_000_000 + round(4.5 * 820 * 1_000_000)
        before = clock.due_ns(4.5)
        clock.adopt(TempoReading(800.0, 4.0, 1.0), now_ns=now_ns)
        self.assertEqual(before, clock.due_ns(4.5))
        self.assertEqual(now_ns + 800_000_000, clock.due_ns(5.5))

    def test_reset_and_lost_barline_alias_stop_the_clock(self):
        for bad_phase in (500.0, -400.0):
            with self.subTest(bad_phase=bad_phase):
                clock = VisualBeatClock(
                    anchor_ns=0,
                    anchor_beat=0.0,
                    beat_ms=800.0,
                    px_per_beat=144.0,
                    beats_per_measure=3,
                )
                for index in range(20):
                    clock.observe(index * 100_000_000, 400 - index * 18)
                with self.assertRaises(VisualClockLost):
                    clock.observe(2_000_000_000, bad_phase)

    def test_visual_deadline_tracks_crossing_and_measured_input_lag(self):
        reference_ns = 1_000_000_000
        clock = VisualBeatClock(
            anchor_ns=reference_ns, anchor_beat=0,
            beat_ms=500, px_per_beat=100, beats_per_measure=3,
        )
        for frame in range(20):
            elapsed_s = frame / 4
            clock.observe(
                reference_ns + round(elapsed_s * 1e9),
                900 - 200 * elapsed_s,
            )
        # Beat 5's engraved position crosses x=400 when the unwrapped
        # barline phase reaches 400 - (5 + .25) * 100 = -125.
        crossing_ns = reference_ns + 5_125_000_000
        self.assertAlmostEqual(
            clock.visual_due_ns(
                5, judgment_x=400, engraving_delta=.25,
                input_to_visual_ms=200,
            ), crossing_ns - 200_000_000, delta=1_000,
        )
        self.assertAlmostEqual(
            clock.visual_due_ns(
                5, judgment_x=400, engraving_delta=.25,
                input_to_visual_ms=200, lead_ms=100,
            ), crossing_ns - 300_000_000, delta=1_000,
        )

    def test_startup_deadline_uses_recent_phase_and_this_notes_position(self):
        """A slow startup fit must not shift a nearby note by its full history."""
        clock = VisualBeatClock(
            anchor_ns=0, anchor_beat=0, beat_ms=680,
            px_per_beat=144, beats_per_measure=4,
        )
        for seconds, phase in (
            (0, 900), (1, 750), (2, 600), (3, 450),
            (4, 300), (5, 128), (5.1, 107),
        ):
            clock.observe(round(seconds * 1e9), phase)
        # The current phase is 107 px; this note crosses when it reaches 50.
        # Use the measured opening beat (144 px / 680 ms), not the biased
        # long-head regression, for this short remaining distance.
        crossing_ns = 5_100_000_000 + round(57 / (144 / .680) * 1e9)
        self.assertAlmostEqual(
            clock.visual_due_ns(
                4, judgment_x=400, engraving_delta=.25,
                relative_x_px=350, input_to_visual_ms=200,
            ), crossing_ns - 200_000_000, delta=10_000_000,
        )

    def test_launch_key_highlight_measures_this_runs_visual_lag(self):
        white = Image.new("RGB", (100, 100), "white")
        shaded = Image.new("RGB", (100, 100), "gray")
        latency = KeyHighlightLatency(white, {"C4": (50, 50)})
        latency.observe(white, 100_000_000)
        latency.mark_press("C4", 200_000_000)
        latency.observe(white, 220_000_000)
        self.assertIsNone(latency.latency_ms)
        latency.observe(shaded, 260_000_000)
        self.assertEqual(40, latency.latency_ms)

    def test_recent_key_highlights_update_the_live_delay(self):
        white = Image.new("RGB", (100, 100), "white")
        shaded = Image.new("RGB", (100, 100), "gray")
        latency = KeyHighlightLatency(white, {"C4": (50, 50)})
        for sent_ms, observed_ms in ((100, 180), (400, 520), (700, 860)):
            latency.observe(white, (sent_ms - 10) * 1_000_000)
            latency.mark_press("C4", sent_ms * 1_000_000)
            latency.observe(white, (sent_ms + 20) * 1_000_000)
            latency.observe(shaded, observed_ms * 1_000_000)
        self.assertEqual([50, 70, 90], [r["latency_ms"] for r in latency.readings])
        self.assertEqual(70, latency.latency_ms)

    def test_pre_press_frame_does_not_underestimate_first_lit_frame(self):
        white = Image.new("RGB", (100, 100), "white")
        shaded = Image.new("RGB", (100, 100), "gray")
        latency = KeyHighlightLatency(white, {"C4": (50, 50)})
        latency.observe(white, 100_000_000)
        latency.mark_press("C4", 200_000_000)
        latency.observe(shaded, 400_000_000)
        self.assertEqual(200, latency.latency_ms)

    def test_recent_delay_adapts_without_following_implausible_frames(self):
        white = Image.new("RGB", (100, 100), "white")
        shaded = Image.new("RGB", (100, 100), "gray")
        latency = KeyHighlightLatency(white, {"C4": (50, 50)})
        for index, delay_ms in enumerate((210, 215, 225, 340, 345, 35, 700)):
            sent_ms = index * 1000 + 100
            latency.observe(white, (sent_ms - 50) * 1_000_000)
            latency.mark_press("C4", sent_ms * 1_000_000)
            latency.observe(shaded, (sent_ms + delay_ms) * 1_000_000)
        self.assertEqual(340, latency.latency_ms)
        self.assertEqual([False, False],
                         [reading["accepted"] for reading in latency.readings[-2:]])

    def test_two_low_highlight_samples_do_not_shift_a_stable_playback_clock(self):
        """The captured 927-point run became late after 219/198 ms samples."""
        white = Image.new("RGB", (100, 100), "white")
        shaded = Image.new("RGB", (100, 100), "gray")
        latency = KeyHighlightLatency(white, {"C4": (50, 50)})
        for index, delay_ms in enumerate((323, 335, 339, 326, 334, 219, 198)):
            sent_ms = index * 1000 + 100
            latency.observe(white, (sent_ms - 50) * 1_000_000)
            latency.mark_press("C4", sent_ms * 1_000_000)
            latency.observe(shaded, (sent_ms + delay_ms) * 1_000_000)
        self.assertEqual([False, False],
                         [reading["accepted"] for reading in latency.readings[-2:]])
        self.assertEqual(334, latency.latency_ms)

    def test_two_false_low_onsets_do_not_poison_startup_latency(self):
        white = Image.new("RGB", (100, 100), "white")
        shaded = Image.new("RGB", (100, 100), "gray")
        latency = KeyHighlightLatency(white, {"G4": (50, 50)})
        for index, delay_ms in enumerate((208, 24, 32, 359, 345)):
            sent_ms = 1000 + index * 1000
            latency.observe(white, (sent_ms - 50) * 1_000_000)
            latency.mark_press("G4", sent_ms * 1_000_000)
            latency.observe(shaded, (sent_ms + delay_ms) * 1_000_000)
        self.assertEqual(
            [True, False, False, True, True],
            [reading["accepted"] for reading in latency.readings],
        )
        self.assertGreater(latency.scheduling_latency_ms, 300)

    def test_two_high_onsets_confirm_across_rejected_low_samples(self):
        white = Image.new("RGB", (100, 100), "white")
        shaded = Image.new("RGB", (100, 100), "gray")
        latency = KeyHighlightLatency(white, {"G4": (50, 50)})
        for index, delay_ms in enumerate((222, 160, 77, 361, 44, 99, 374)):
            sent_ms = 1000 + index * 1000
            latency.observe(white, (sent_ms - 50) * 1_000_000)
            latency.mark_press("G4", sent_ms * 1_000_000)
            latency.observe(shaded, (sent_ms + delay_ms) * 1_000_000)
        self.assertEqual(
            [True, False, False, True, False, False, True],
            [reading["accepted"] for reading in latency.readings],
        )
        self.assertGreater(latency.scheduling_latency_ms, 300)

    def test_scheduling_delay_follows_a_rise_without_chasing_a_large_outlier(self):
        white = Image.new("RGB", (100, 100), "white")
        shaded = Image.new("RGB", (100, 100), "gray")
        latency = KeyHighlightLatency(white, {"C4": (50, 50)})
        # The 991-point run used the median of 213, 178, 269 ms for F4,
        # leaving that onset about 55 ms late despite the newest observation.
        for index, delay_ms in enumerate((213, 178, 269, 410)):
            sent_ms = index * 1000 + 100
            latency.observe(white, (sent_ms - 50) * 1_000_000)
            latency.mark_press("C4", sent_ms * 1_000_000)
            latency.observe(shaded, (sent_ms + delay_ms) * 1_000_000)
            if index == 2:
                self.assertEqual(213, latency.latency_ms)
                self.assertEqual(268, latency.scheduling_latency_ms)
        self.assertFalse(latency.readings[-1]["accepted"])
        self.assertEqual(213, latency.latency_ms)
        self.assertEqual(268, latency.scheduling_latency_ms)

    def test_isolated_high_c_key_readings_do_not_move_other_notes(self):
        """The 942-point run mixed ~400 ms observations with 602/623 ms C5 spikes."""
        white = Image.new("RGB", (100, 100), "white")
        shaded = Image.new("RGB", (100, 100), "gray")
        latency = KeyHighlightLatency(white, {"C5": (50, 50)})
        for index, delay_ms in enumerate((380, 400, 410, 602, 405, 623, 415)):
            sent_ms = index * 1000 + 100
            latency.observe(white, (sent_ms - 50) * 1_000_000)
            latency.mark_press("C5", sent_ms * 1_000_000)
            latency.observe(shaded, (sent_ms + delay_ms) * 1_000_000)
        self.assertEqual([False, False], [
            latency.readings[index]["accepted"] for index in (3, 5)
        ])
        self.assertEqual(410, latency.latency_ms)
        self.assertEqual(415, latency.scheduling_latency_ms)

    def test_startup_release_calibrates_first_scrolling_note(self):
        white = Image.new("RGB", (100, 100), "white")
        shaded = Image.new("RGB", (100, 100), "gray")
        latency = KeyHighlightLatency(white, {"F4": (50, 50)})
        latency.mark_press("F4", 100_000_000)
        latency.observe(shaded, 320_000_000)
        self.assertEqual(220, latency.scheduling_latency_ms)
        latency.mark_release("F4", 1_000_000_000)
        latency.observe(shaded, 1_100_000_000)
        latency.observe(white, 1_500_000_000)
        self.assertEqual(300, latency.release_latency_ms)
        self.assertEqual(300, latency.scheduling_latency_ms)

    def test_release_delay_bounds_two_false_high_press_readings(self):
        white = Image.new("RGB", (100, 100), "white")
        latency = KeyHighlightLatency(white, {"G5": (50, 50)})
        latency._readings = [
            {"latency_ms": delay, "accepted": True}
            for delay in (350, 360, 370, 510, 520)
        ]
        latency._release_readings = [
            {"latency_ms": delay} for delay in (350, 360, 355)
        ]
        self.assertEqual(435, latency.scheduling_latency_ms)

    def test_fast_release_feedback_cannot_make_later_presses_late(self):
        """Part 112 measured ~350 ms press lag but ~60 ms releases."""
        white = Image.new("RGB", (100, 100), "white")
        latency = KeyHighlightLatency(white, {"Ab4": (50, 50)})
        latency._readings = [
            {"latency_ms": delay, "accepted": True}
            for delay in (345, 352, 360)
        ]
        latency._release_readings = [
            {"latency_ms": delay} for delay in (64, 69, 62)
        ]
        self.assertEqual(360, latency.scheduling_latency_ms)


if __name__ == "__main__":
    unittest.main()
