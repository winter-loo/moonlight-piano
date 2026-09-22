"""Tests for Duolingo measure-barline detection and tracking."""

import importlib.util
import json
from pathlib import Path
import sys
import unittest

from PIL import Image


REPO_ROOT = Path(__file__).parents[1]
FIXTURE_ROOT = (
    REPO_ROOT
    / "tests/fixtures/duolingo-realtime-measure/2026-09-20-h264-scroll-01"
)
TEMPO_FIXTURE_ROOT = (
    REPO_ROOT
    / "tests/fixtures/duolingo-realtime-measure/2026-09-20-flowers-ultimate-h264-03"
)


def load_tracker():
    path = REPO_ROOT / "scripts/duolingo_measure_tracker.py"
    spec = importlib.util.spec_from_file_location("duolingo_measure_tracker", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tracker_module = load_tracker()


def require_fixture(root: Path) -> None:
    # The captured frames live outside git; skip rather than fail on a clean checkout.
    if not (root / "frames.jsonl").exists():
        raise unittest.SkipTest(f"capture fixture not present: {root.name}")


def load_rows():
    require_fixture(FIXTURE_ROOT)
    return [
        json.loads(line)
        for line in (FIXTURE_ROOT / "frames.jsonl").read_text().splitlines()
    ]


class MeasureBarlineDetectionTest(unittest.TestCase):
    def test_detects_periodic_barlines_without_note_stems_or_judgment_line(self):
        row = load_rows()[0]
        image = Image.open(FIXTURE_ROOT / row["image"]).convert("RGB")

        candidates = tracker_module.detect_measure_barline_candidates(
            image,
            row["staff_lines"],
            row["judgment_line_x"],
        )
        spacing = tracker_module.infer_measure_spacing(candidates)
        selected = tracker_module.select_regular_barlines(candidates, spacing)

        self.assertEqual(576.0, spacing)
        self.assertEqual([322.0, 898.0, 1474.0], [item.x for item in selected])
        self.assertTrue(all(abs(item.x - row["judgment_line_x"]) > 18 for item in candidates))
        self.assertNotIn(233.0, [item.x for item in candidates])


class MeasureLineTrackerTest(unittest.TestCase):
    def test_tracks_real_fixture_and_recovers_stable_scroll_speed(self):
        rows = load_rows()
        tracker = tracker_module.MeasureLineTracker()
        updates = []
        for row in rows[:34]:
            image = Image.open(FIXTURE_ROOT / row["image"]).convert("RGB")
            candidates = tracker_module.detect_measure_barline_candidates(
                image,
                row["staff_lines"],
                row["judgment_line_x"],
            )
            updates.append(tracker.update(row["monotonic_ns"], candidates))

        self.assertEqual(576.0, tracker.spacing_px)
        steady = [update for update in updates if update.state == "steady"]
        self.assertTrue(steady)
        speeds = [
            update.fitted_speed_px_s
            for update in steady
            if update.fitted_speed_px_s is not None
        ]
        self.assertTrue(any(-290.0 < speed < -265.0 for speed in speeds))
        self.assertTrue(any((update.fit_r_squared or 0) > 0.99 for update in steady))

        ids_by_frame = {
            rows[index]["frame_index"]: {line.line_id for line in update.barlines}
            for index, update in enumerate(updates)
        }
        self.assertIn(1, ids_by_frame[0])
        self.assertIn(1, ids_by_frame[10])
        self.assertEqual({2, 3}, ids_by_frame[25])
        self.assertEqual("resetting", updates[32].state)

    def test_missing_frame_preserves_phase_and_line_identity(self):
        candidate = tracker_module.BarlineCandidate
        tracker = tracker_module.MeasureLineTracker(spacing_px=576.0)
        first = tracker.update(
            1_000_000_000,
            [candidate(600.0, 1.0, 4), candidate(1176.0, 1.0, 4)],
        )
        missing = tracker.update(1_100_000_000, [])
        recovered = tracker.update(
            1_200_000_000,
            [candidate(544.0, 1.0, 4), candidate(1120.0, 1.0, 4)],
        )

        self.assertEqual("missing", missing.state)
        self.assertEqual(first.phase_px, missing.phase_px)
        self.assertEqual([0, 1], [line.line_id for line in recovered.barlines])
        self.assertAlmostEqual(-280.0, recovered.instantaneous_speed_px_s)


class MeasureTempoEstimatorTest(unittest.TestCase):
    def test_cross_validates_speed_and_six_judgment_line_crossings(self):
        candidate = tracker_module.BarlineCandidate
        tracker = tracker_module.MeasureLineTracker(
            spacing_px=576.0,
            history_size=12,
        )
        tempo = tracker_module.MeasureTempoEstimator(beats_per_measure=4.0)
        start_ns = 10_000_000_000
        speed_px_s = -288.0
        judgment_x = 350.0

        for frame in range(121):
            elapsed_s = frame / 10.0
            timestamp_ns = start_ns + round(elapsed_s * 1_000_000_000)
            positions = []
            for logical_id in range(-3, 12):
                x = 500.0 + logical_id * 576.0 + speed_px_s * elapsed_s
                if 120.0 <= x <= 1490.0:
                    positions.append(candidate(x, 1.0, 4))
            update = tracker.update(timestamp_ns, positions)
            tempo.observe(update, judgment_line_x=judgment_x)

        estimate = tempo.estimate()
        self.assertIsNotNone(estimate)
        self.assertGreaterEqual(estimate.crossing_period_count, 5)
        self.assertAlmostEqual(2.0, estimate.measure_seconds_from_speed, places=6)
        self.assertAlmostEqual(2.0, estimate.measure_seconds_from_crossings, places=6)
        self.assertAlmostEqual(120.0, estimate.bpm, places=6)
        self.assertLess(estimate.period_disagreement_ms, 0.001)
        self.assertLess(estimate.crossing_period_range_ms, 0.001)
        self.assertLess(estimate.maximum_crossing_error_ms, 0.001)
        self.assertLess(estimate.bpm_range, 0.001)
        self.assertEqual("high", estimate.confidence)

    def test_startup_speed_convergence_does_not_pollute_crossing_bpm_range(self):
        tempo = tracker_module.MeasureTempoEstimator(beats_per_measure=4.0)
        update = tracker_module.MeasureTrackUpdate
        line = tracker_module.TrackedBarline
        crossing_period_ns = 2_000_000_000

        # The fitted velocity is deliberately still converging, while the
        # independently observed barline crossings remain exactly periodic.
        for index in range(7):
            crossing_ns = 20_000_000_000 + index * crossing_period_ns
            phase_before = 350.0 - index * 576.0 + 28.8
            phase_after = 350.0 - index * 576.0 - 28.8
            tempo.observe(
                update(
                    timestamp_ns=crossing_ns - 100_000_000,
                    state="steady",
                    spacing_px=576.0,
                    phase_px=phase_before,
                    instantaneous_speed_px_s=None,
                    fitted_speed_px_s=-260.0 - index * 4.0,
                    fit_r_squared=0.999,
                    candidates=(),
                    barlines=(line(index, 378.8, 1.0),),
                    missing_frames=0,
                ),
                judgment_line_x=350.0,
            )
            tempo.observe(
                update(
                    timestamp_ns=crossing_ns + 100_000_000,
                    state="steady",
                    spacing_px=576.0,
                    phase_px=phase_after,
                    instantaneous_speed_px_s=None,
                    fitted_speed_px_s=-288.0,
                    fit_r_squared=0.999,
                    candidates=(),
                    barlines=(line(index, 321.2, 1.0),),
                    missing_frames=0,
                ),
                judgment_line_x=350.0,
            )

        estimate = tempo.estimate()
        self.assertIsNotNone(estimate)
        self.assertEqual(6, estimate.crossing_period_count)
        self.assertAlmostEqual(0.0, estimate.crossing_period_range_ms)
        self.assertAlmostEqual(0.0, estimate.maximum_crossing_error_ms)
        self.assertAlmostEqual(0.0, estimate.bpm_range)
        self.assertEqual("high", estimate.confidence)

    def test_does_not_bridge_period_across_a_waiting_screen(self):
        candidate = tracker_module.BarlineCandidate
        tracker = tracker_module.MeasureLineTracker(spacing_px=576.0)
        tempo = tracker_module.MeasureTempoEstimator(beats_per_measure=4.0)

        frames = [
            (0.0, [500.0, 1076.0]),
            (0.5, [356.0, 932.0]),
            (1.0, [212.0, 788.0]),
            (3.0, [212.0, 788.0]),
            (5.0, [500.0, 1076.0]),
            (5.5, [356.0, 932.0]),
            (6.0, [212.0, 788.0]),
        ]
        for seconds, positions in frames:
            update = tracker.update(
                30_000_000_000 + round(seconds * 1e9),
                [candidate(x, 1.0, 4) for x in positions],
            )
            tempo.observe(update, judgment_line_x=350.0)

        records = tempo.crossing_records
        self.assertTrue(records)
        self.assertGreaterEqual(len({record[0] for record in records}), 1)
        estimate = tempo.estimate()
        if estimate is not None:
            self.assertTrue(
                estimate.measure_seconds_from_crossings is None
                or estimate.measure_seconds_from_crossings < 3.0
            )

    def test_real_flowers_fixture_meets_five_measure_acceptance(self):
        require_fixture(TEMPO_FIXTURE_ROOT)
        rows = [
            json.loads(line)
            for line in (TEMPO_FIXTURE_ROOT / "frames.jsonl").read_text().splitlines()
        ]
        tracker = tracker_module.MeasureLineTracker()
        tempo = tracker_module.MeasureTempoEstimator(beats_per_measure=4.0)

        for row in rows:
            image = Image.open(TEMPO_FIXTURE_ROOT / row["image"]).convert("RGB")
            candidates = tracker_module.detect_measure_barline_candidates(
                image,
                row["staff_lines"],
                row["judgment_line_x"],
            )
            update = tracker.update(row["monotonic_ns"], candidates)
            tempo.observe(update, judgment_line_x=row["judgment_line_x"])

        estimate = tempo.estimate()
        self.assertIsNotNone(estimate)
        self.assertGreaterEqual(estimate.crossing_period_count, 5)
        self.assertLess(estimate.maximum_crossing_error_ms, 30.0)
        self.assertLess(estimate.bpm_range, 1.0)
        self.assertLess(estimate.period_disagreement_ms, 30.0)
        self.assertEqual("high", estimate.confidence)


if __name__ == "__main__":
    unittest.main()
