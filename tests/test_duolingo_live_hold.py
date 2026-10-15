"""Score-derived articulation must keep adjacent notes from overlapping."""

import importlib.util
from concurrent.futures import Future
from pathlib import Path
import queue
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

SCRIPT = Path(__file__).parents[1] / "scripts" / "duolingo-rehearse-song.py"
SPEC = importlib.util.spec_from_file_location("duolingo_live_hold_test", SCRIPT)
player = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = player
SPEC.loader.exec_module(player)


class LiveHoldTest(unittest.TestCase):
    def test_recalibration_cannot_collapse_a_same_key_half_beat(self):
        # Part 115 sent these two Bb4 presses only 34 ms apart after the
        # highlight estimate changed between them.
        first_ns = 4_891_000_000
        due_ns = player.bounded_retrigger_due_ns(
            4_925_000_000, pitch="Bb4", beat=5.0,
            previous={"pitch": "Bb4", "beat": 4.5, "hold_ms": 100.0},
            previous_sent_ns=first_ns, beat_ms=500.0,
        )
        self.assertGreaterEqual(due_ns - first_ns, 162_500_000)
        self.assertEqual(
            4_925_000_000,
            player.bounded_retrigger_due_ns(
                4_925_000_000, pitch="G4", beat=5.0,
                previous={"pitch": "Bb4", "beat": 4.5, "hold_ms": 100.0},
                previous_sent_ns=first_ns, beat_ms=500.0,
            ),
        )

    def test_visual_correction_cannot_stretch_a_same_key_beat(self):
        # Part 115 sent G4 at beats 36 and 37 about 697 ms apart, despite a
        # stable 500 ms beat, and the second note was marked late.
        first_ns = 20_265_000_000
        due_ns = player.bounded_retrigger_due_ns(
            20_962_000_000, pitch="G4", beat=37.0,
            previous={"pitch": "G4", "beat": 36.0, "hold_ms": 398.0},
            previous_sent_ns=first_ns, beat_ms=500.0,
        )
        self.assertEqual(first_ns + 525_000_000, due_ns)

    def test_quick_pitch_uses_locked_flats_and_sharps(self):
        self.assertEqual("Db5", player.signed_pitch_from_signature("D5", (4, 0)))
        self.assertEqual("C#5", player.signed_pitch_from_signature("C5", (0, 2)))
        self.assertEqual("Bb4", player.signed_pitch_from_signature("Bb4", (4, 0)))

    def test_preflight_spacing_keeps_barline_phase_continuous_across_measures(self):
        from duolingo_measure_tracker import BarlineCandidate

        tracker = player.ScrollTracker(
            [144, 182, 220, 258, 296], 498,
            initial_phase_px=1048, spacing_px=519,
        )
        tracker.lock_spacing(564)
        for frame in range(40):
            positions = (1048 - 20 * frame + 564 * line for line in range(3))
            candidates = [
                BarlineCandidate(x, 1.0, 2)
                for x in positions if 120 < x < 1480
            ]
            update = tracker._tracker.update(frame * 100_000_000 + 1, candidates)
            self.assertEqual(564, update.spacing_px)
            self.assertAlmostEqual(1048 - 20 * frame, update.phase_px)

    def test_opening_start_needs_two_reads_even_with_stricter_moving_note_gate(self):
        ledger = player.Ledger()
        ledger.add(-4, "G4", 1.0, 0.8)
        self.assertFalse(player.opening_start_confirmed(ledger, "G4"))
        ledger.add(-4, "G4", 1.0, 0.8)
        self.assertTrue(player.opening_start_confirmed(ledger, "G4"))

    def test_half_beat_note_can_use_the_previous_notes_late_latency_sample(self):
        # Lift Off: E4's visual onset arrived about 40 ms before the next G4
        # press. Freezing G4 about 70 ms early kept a stale 296 ms estimate,
        # despite E4's new 165 ms sample arriving before G4 was sent.
        due_ns = 1_000_000_000
        self.assertFalse(player.should_commit_due(
            due_ns=due_ns, now_ns=due_ns - 50_000_000, beat_ms=466,
        ))
        self.assertTrue(player.should_commit_due(
            due_ns=due_ns, now_ns=due_ns - 15_000_000, beat_ms=466,
        ))

    def test_live_deadline_is_not_frozen_during_a_short_capture_backlog(self):
        # In the 988-point run, an A4 deadline was frozen 282 ms ahead while
        # phase tracking was still catching up. A later frame moved it 75 ms.
        self.assertFalse(player.should_commit_due(
            due_ns=9_621_000_000, now_ns=9_339_000_000, beat_ms=695,
        ))
        self.assertTrue(player.should_commit_due(
            due_ns=9_546_000_000, now_ns=9_515_000_000, beat_ms=695,
        ))

    def test_short_window_rejects_the_captured_startup_tempo_spike(self):
        self.assertFalse(player.tempo_refinement_ready(
            measured_beat_ms=717.525, current_beat_ms=680.7,
            span_beats=8.01, residual_px=17.96,
            px_per_beat=144, beats_per_measure=4,
            first_update=True,
        ))
        self.assertTrue(player.tempo_refinement_ready(
            measured_beat_ms=678.29, current_beat_ms=680.7,
            span_beats=8.01, residual_px=12.34,
            px_per_beat=144, beats_per_measure=4,
            first_update=True,
        ))
        self.assertTrue(player.tempo_refinement_ready(
            measured_beat_ms=690.225, current_beat_ms=680.7,
            span_beats=12.12, residual_px=9.26,
            px_per_beat=144, beats_per_measure=4,
            first_update=True,
        ))

    def test_fast_song_bootstraps_from_agreeing_steady_motion(self):
        # Part 124 began with a 600 ms guess. By 3.0 s the barline's
        # long-window fit (381 ms) and recent steady fit (367 ms) agreed,
        # before the first scored note. The old 25% guard stopped the song.
        self.assertTrue(player.tempo_refinement_ready(
            measured_beat_ms=381, current_beat_ms=600,
            span_beats=6.8, residual_px=6.3,
            px_per_beat=144, beats_per_measure=4,
            first_update=True, steady_speed_px_s=-392,
            fit_r_squared=0.994,
        ))
        for speed, r_squared, residual in (
            (-392, 0.97, 6.3), (-250, 0.994, 6.3),
            (-392, 0.994, 18.0),
        ):
            self.assertFalse(player.tempo_refinement_ready(
                measured_beat_ms=381, current_beat_ms=600,
                span_beats=6.8, residual_px=residual,
                px_per_beat=144, beats_per_measure=4,
                first_update=True, steady_speed_px_s=speed,
                fit_r_squared=r_squared,
            ))
        # A new 40% disagreement after tempo lock remains a stop condition.
        self.assertTrue(player.tempo_refinement_ready(
            measured_beat_ms=381, current_beat_ms=600,
            span_beats=12, residual_px=6.3,
            px_per_beat=144, beats_per_measure=4,
            first_update=False,
        ))

    def test_ledger_keeps_this_notes_position_relative_to_its_barline(self):
        ledger = player.Ledger()
        ledger.add(4, "F4", 1.5, 1.3, relative_x_px=626)
        ledger.add(4, "F4", 1.5, 1.3, relative_x_px=620)
        ledger.add(4, "F4", 1.5, 1.3, relative_x_px=623)
        self.assertEqual(623, ledger.confirmed(2)[0].relative_x_px)

    def test_continuous_defaults_keep_the_live_reader_below_its_measured_load_limit(self):
        argv = ["duolingo-rehearse-song.py", "continuous", "--serial", "test-device",
                "--output", "unused", "--beat-ms", "858"]
        with patch.object(sys, "argv", argv), patch.object(player, "rehearse", return_value={}) as run:
            player.main()
        args = run.call_args.args[0]
        self.assertEqual((10, .4, 6),
                         (args.capture_fps, args.scan_interval, args.save_every))

    def test_opening_grid_uses_complete_first_measure_when_only_one_barline_is_visible(self):
        events = [
            {"event_type": "note", "x": 431.5, "pitch": "F4", "delta_beats": 1.0},
            {"event_type": "rest", "x": 558.0, "delta_beats": 1.0},
            {"event_type": "rest", "x": 702.5, "delta_beats": 2.0},
            {"event_type": "rest", "x": 990.5, "delta_beats": 2.0},
            {"event_type": "rest", "x": 1278.0, "delta_beats": 1.0},
            {"event_type": "rest", "x": 1426.0, "delta_beats": .5},
            {"event_type": "note", "x": 1476.0, "edge_clipped": True},
        ]
        barlines = [SimpleNamespace(x=954.0)]
        spacing = player.infer_opening_measure_spacing(events, barlines, 407)
        self.assertAlmostEqual(576, spacing)
        grid = player.GridKeeper().update(events, 954, spacing)
        self.assertEqual(4, grid.beats_per_measure)
        self.assertEqual(-4, grid.snapped_beat_of(431.5, 954))

    def test_opening_grid_rejects_a_partial_first_measure(self):
        events = [
            {"event_type": "note", "x": 600, "delta_beats": 1.0},
            {"event_type": "rest", "x": 744, "delta_beats": 1.0},
        ]
        self.assertIsNone(player.infer_opening_measure_spacing(
            events, [SimpleNamespace(x=954.0)], 407,
        ))

    def test_tail_note_gets_two_reads_without_waiting_for_first_result(self):
        """A visible tail note must be corroborated before its onset deadline."""
        stop = threading.Event()
        frames = queue.Queue(maxsize=1)
        ledger = player.Ledger()
        stats = {"reads": 0, "added": 0, "reader_lag_ms": []}

        class Keeper:
            ready = True

            def update(self, events, phase_px, spacing):
                return object()

            def beat_of(self, x, phase_px):
                return 67.5

        class PendingExecutor:
            def __init__(self):
                self.futures = []

            def submit(self, function, image, key_signature):
                future = Future()
                self.futures.append(future)
                return future

        executor = PendingExecutor()
        frames.put((object(), 1000, 100))
        worker = threading.Thread(target=player.recognition_worker, args=(
            executor, Keeper(), frames, ledger, stop, stats, time.monotonic_ns(),
            (0, 0),
        ))
        worker.start()
        try:
            limit = time.monotonic() + 0.5
            while len(executor.futures) < 1 and time.monotonic() < limit:
                time.sleep(0.005)
            self.assertEqual(1, len(executor.futures))
            frames.put((object(), 1300, 90))
            limit = time.monotonic() + 0.25
            while len(executor.futures) < 2 and time.monotonic() < limit:
                time.sleep(0.005)
            self.assertEqual(2, len(executor.futures),
                             "second tail frame waited for the first full scan")
            events = [{"event_type": "note", "x": 789, "pitch": "A3",
                       "duration_beats": .5, "hold_beats": .4,
                       "edge_clipped": False}]
            for future in executor.futures:
                future.set_result((events, 576))
            limit = time.monotonic() + 0.5
            while not ledger.confirmed(2) and time.monotonic() < limit:
                time.sleep(0.005)
            self.assertEqual([67.5], [note.beat for note in ledger.confirmed(2)])
        finally:
            for future in executor.futures:
                if not future.done():
                    future.set_result(([], 576))
            stop.set()
            worker.join(timeout=1)

    def test_transport_gap_is_not_a_still_score_or_one_frame_reset(self):
        tracker = player.ScrollTracker([144, 185, 220, 261, 294], 351)
        tracker.samples = [
            player.ScrollSample(0, 500, -250, 576, 1, "steady"),
            player.ScrollSample(300, 425, -250, 576, 1, "steady"),
            player.ScrollSample(600, 350, -250, 576, 1, "steady"),
            player.ScrollSample(900, 350, -250, 576, None, "missing"),
            player.ScrollSample(1200, 350, -250, 576, None, "missing"),
            player.ScrollSample(1300, 350, -250, 576, None, "missing"),
        ]
        self.assertFalse(tracker.stalled())

        readings = iter(("resetting", "steady", "resetting", "resetting", "resetting"))
        tracker._tracker.update = lambda *_: SimpleNamespace(
            phase_px=250, fitted_speed_px_s=-250, spacing_px=576,
            fit_r_squared=1, state=next(readings),
        )
        with patch.object(player, "detect_measure_barline_candidates", return_value=[]):
            for t in (1400, 1500, 1600):
                tracker.observe(Image.new("RGB", (10, 10)), t)
                self.assertIsNone(tracker.fault_reason)
            tracker.observe(Image.new("RGB", (10, 10)), 1700)
            self.assertIsNone(tracker.fault_reason)
            tracker.observe(Image.new("RGB", (10, 10)), 2000)
        self.assertEqual("score moved right or reset", tracker.fault_reason)

    def test_brief_resetting_frames_that_resume_leftward_are_not_a_reset(self):
        tracker = player.ScrollTracker([144, 185, 220, 261, 294], 351)
        readings = iter((
            (4067, -173, "steady"),
            (4099, -173, "missing"),
            (4135, -173, "missing"),
            (4189, -173, "resetting"),
            (4223, -173, "resetting"),
            (4226, -173, "resetting"),
            (4283, -173, "resetting"),
            (4311, -180, "accelerating"),
        ))
        def next_reading(*_):
            _, x, state = next(readings)
            return SimpleNamespace(
                phase_px=x, fitted_speed_px_s=-170, spacing_px=519,
                fit_r_squared=1, state=state,
            )

        tracker._tracker.update = next_reading
        with patch.object(player, "detect_measure_barline_candidates", return_value=[]):
            for t in (4067, 4099, 4135, 4189, 4223, 4226, 4283, 4311):
                tracker.observe(Image.new("RGB", (10, 10)), t)
                self.assertIsNone(tracker.fault_reason)

    def test_raw_barlines_keep_reset_gate_open_only_while_moving_left(self):
        tracker = player.ScrollTracker([182, 223, 261, 299, 334], 499)
        tracker._tracker.update = lambda *_: SimpleNamespace(
            phase_px=0, fitted_speed_px_s=-155, spacing_px=288,
            fit_r_squared=1, state="resetting",
        )
        xs = iter((700, 650, 600, 550, 500, 500, 500))
        with patch.object(player, "detect_measure_barline_candidates",
                          side_effect=lambda *_: [SimpleNamespace(x=next(xs))]):
            for t in (0, 300, 600, 900, 1200, 1500):
                tracker.observe(Image.new("RGB", (10, 10)), t)
                self.assertIsNone(tracker.fault_reason)
            tracker.observe(Image.new("RGB", (10, 10)), 1900)
        self.assertEqual("score moved right or reset", tracker.fault_reason)

    def test_grid_does_not_move_after_one_noisy_offset_reading(self):
        from duolingo_beat_grid import BeatGrid
        first = BeatGrid(432, 3, 144, .25)
        noisy = BeatGrid(432, 3, 144, .4875)
        keeper = player.GridKeeper()
        with patch.object(player, "build_beat_grid", side_effect=[first, noisy]):
            self.assertIs(first, keeper.update([], 0, 432))
            self.assertIs(first, keeper.update([], 0, 432))
        self.assertEqual(.25, keeper.delta)
        self.assertEqual(5, keeper.beat_of(756, 0))

    def test_locked_grid_survives_single_barline_at_song_tail(self):
        from duolingo_beat_grid import BeatGrid
        grid = BeatGrid(578, 4, 144.5, .3325)
        keeper = player.GridKeeper()
        with patch.object(player, "build_beat_grid", return_value=grid) as build:
            self.assertIs(grid, keeper.update([], 0, 578))
            self.assertIs(grid, keeper.update([], -7744, None))
            build.assert_called_once()
        self.assertEqual(58, keeper.beat_of(679, -7744))

    def test_reader_hold_beats_win_over_notated_duration(self):
        self.assertEqual(640, player.hold_ms_for(1, .8, 800, None))
        self.assertEqual(320, player.hold_ms_for(.5, .4, 800, None))
        self.assertEqual(1440, player.hold_ms_for(2, 1.8, 800, None))
        self.assertEqual(740, player.hold_ms_for(1, .8, 800, 60))

    def test_long_note_release_experiment_does_not_change_short_notes(self):
        self.assertEqual(640, player.hold_ms_for(1, .8, 800, None, 50))
        self.assertEqual(1550, player.hold_ms_for(2, 1.8, 800, None, 50))
        self.assertEqual(740, player.hold_ms_for(1, .8, 800, 60, 50))

    def test_ledger_keeps_articulation_across_corroborating_reads(self):
        ledger = player.Ledger()
        ledger.add(2, "C4", 1, .8)
        ledger.add(2, "C4", 1, .8)
        self.assertEqual(.8, ledger.confirmed(2)[0].hold_beats)

    def test_ledger_rejects_shifted_duplicate_of_long_note(self):
        ledger = player.Ledger()
        for _ in range(10):
            ledger.add(57, "F4", 2, 1.8)
        for _ in range(2):
            ledger.add(57.5, "F4", 2, 1.8)
        self.assertEqual([57], [note.beat for note in ledger.confirmed(2)])

    def test_ledger_keeps_distinct_repeated_notes_despite_overlap(self):
        ledger = player.Ledger()
        for _ in range(6):
            ledger.add(79, "F#4", 1, .8, relative_x_px=11424)
            ledger.add(79.5, "F#4", .5, .4, relative_x_px=11560)
        self.assertEqual(
            [79, 79.5],
            [note.beat for note in ledger.confirmed(4, px_per_beat=144.5)],
        )

    def test_ledger_keeps_adjacent_repeated_short_notes(self):
        ledger = player.Ledger()
        for _ in range(2):
            ledger.add(11, "C4", .5, .4)
            ledger.add(11.5, "C4", .5, .4)
        self.assertEqual([11, 11.5],
                         [note.beat for note in ledger.confirmed(2)])

    def test_later_articulation_readings_correct_first_frame(self):
        ledger = player.Ledger()
        ledger.add(41, "C4", 1, .8)
        ledger.add(41, "C4", .5, .4)
        ledger.add(41, "C4", .5, .4)
        ledger.add(41.5, "C4", .5, .4)
        ledger.add(41.5, "C4", .5, .4)
        notes = ledger.confirmed(2)
        self.assertEqual([41, 41.5], [note.beat for note in notes])
        self.assertEqual([.5, .5], [note.duration_beats for note in notes])

    def test_capture_replaces_a_pending_old_score_frame(self):
        stop = threading.Event()
        image = Image.new("RGB", (10, 10), "white")

        class Pump:
            sequence = 0

            def wait_for_timed_frame(self, **_):
                self.sequence += 1
                if self.sequence == 3:
                    stop.set()
                return image, self.sequence, self.sequence * 1_000_000

        class Tracker:
            def observe(self, _, t_ms):
                return player.ScrollSample(t_ms, 1000 - t_ms, None,
                                           432, None, "steady")

        class Latency:
            def observe(self, *_):
                pass

        recognition = queue.Queue(maxsize=1)
        stats = {"replaced_pending": 0}
        player.capture_and_track(
            Pump(), Tracker(), Latency(), recognition, queue.Queue(), stop,
            0, 0, None, {}, stats,
        )
        _, t_ms, _ = recognition.get_nowait()
        self.assertEqual(3, t_ms)
        self.assertEqual(2, stats["replaced_pending"])


if __name__ == "__main__":
    unittest.main()
