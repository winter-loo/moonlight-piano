"""Unit tests for the H.264 capture helper's live-assist scheduling."""

import importlib.util
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def load_capture_module():
    path = REPO_ROOT / "scripts/duolingo-capture-h264-sample.py"
    spec = importlib.util.spec_from_file_location("duolingo_capture_h264_sample", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


capture_module = load_capture_module()


class FakeScheduler:
    def __init__(self):
        self.calls = []

    def schedule(self, **kwargs):
        self.calls.append(kwargs)


class AssistSchedulingTest(unittest.TestCase):
    def test_schedules_future_note_once_with_predicted_crossing_deadline(self):
        scheduler = FakeScheduler()
        scheduled = []
        note = {
            "pitch": "A3",
            "x": 630.0,
            "hold_beats": 0.8,
        }

        first = capture_module.schedule_visible_notes(
            notes=[note],
            captured_ns=10_000_000_000,
            judgment_line_x=350.0,
            speed_px_s=280.0,
            beat_ms=500.0,
            key_points={"A3": (415, 600)},
            scheduled=scheduled,
            scheduler=scheduler,
        )
        duplicate = capture_module.schedule_visible_notes(
            notes=[note],
            captured_ns=10_020_000_000,
            judgment_line_x=350.0,
            speed_px_s=280.0,
            beat_ms=500.0,
            key_points={"A3": (415, 600)},
            scheduled=scheduled,
            scheduler=scheduler,
        )

        self.assertEqual(1, first)
        self.assertEqual(0, duplicate)
        self.assertEqual(11_000_000_000, scheduler.calls[0]["deadline_ns"])
        self.assertEqual(400, scheduler.calls[0]["hold_ms"])

    def test_ignores_notes_too_close_or_without_a_key_mapping(self):
        scheduler = FakeScheduler()
        added = capture_module.schedule_visible_notes(
            notes=[
                {"pitch": "A3", "x": 360.0, "hold_beats": 0.8},
                {"pitch": "C6", "x": 700.0, "hold_beats": 1.0},
            ],
            captured_ns=10_000_000_000,
            judgment_line_x=350.0,
            speed_px_s=280.0,
            beat_ms=500.0,
            key_points={"A3": (415, 600)},
            scheduled=[],
            scheduler=scheduler,
        )

        self.assertEqual(0, added)
        self.assertEqual([], scheduler.calls)


if __name__ == "__main__":
    unittest.main()
