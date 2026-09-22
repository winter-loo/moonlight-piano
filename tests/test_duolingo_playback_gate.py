"""Scheduling tests for the frozen-plan playback gate.

Everything here runs without a phone: the ADB input bridge is replaced by a
recording double, and the plans are played on a deliberately absurd BPM so a
whole song finishes in milliseconds.
"""

import argparse
import importlib.util
import json
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).parents[1]
OUTPUT_DIR = REPO_ROOT / "outputs/duolingo-stage4-section14-musette/ultimate"
CORRECTED_PLAN_PATH = OUTPUT_DIR / "musette-corrected-frozen-plan.json"
SUPERSEDED_PLAN_PATH = OUTPUT_DIR / "musette-frozen-plan.json"


def _load_player():
    """Import the hyphenated player script as a module."""
    path = REPO_ROOT / "scripts/duolingo-timed-player.py"
    spec = importlib.util.spec_from_file_location("duolingo_timed_player", path)
    module = importlib.util.module_from_spec(spec)
    # Registering first keeps ``dataclasses`` able to resolve annotations.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


player = _load_player()

MS = 1_000_000

# ``/outputs`` is gitignored, so a fresh clone has the scripts but not the
# captured plans.  The gate logic above still runs; only the replays skip.
HAVE_PLANS = CORRECTED_PLAN_PATH.exists() and SUPERSEDED_PLAN_PATH.exists()
requires_plans = unittest.skipUnless(
    HAVE_PLANS, "captured frozen plans are not present in this checkout"
)


class PlaybackGateTest(unittest.TestCase):
    def test_admits_events_inside_the_boundary(self):
        gate = player.PlaybackGate(last_valid_event_index=68, stop_after_beat=71)
        self.assertTrue(gate.admits(0, 0.0))
        self.assertTrue(gate.admits(68, 70.0))
        self.assertTrue(gate.is_open)

    def test_event_index_past_the_audit_closes_the_gate(self):
        gate = player.PlaybackGate(last_valid_event_index=68, stop_after_beat=None)
        self.assertFalse(gate.admits(69, 71.0))
        self.assertFalse(gate.is_open)
        self.assertTrue(gate.closed_planned)
        self.assertIn("last_valid_event_index", gate.closed_reason)

    def test_stop_beat_is_exclusive_for_onsets(self):
        gate = player.PlaybackGate(last_valid_event_index=None, stop_after_beat=71)
        self.assertTrue(gate.admits(68, 70.5))
        self.assertFalse(gate.admits(69, 71.0))
        self.assertTrue(gate.closed_planned)
        self.assertIn("stop_after_beat", gate.closed_reason)

    def test_an_unbounded_gate_admits_everything(self):
        gate = player.PlaybackGate()
        self.assertTrue(gate.admits(10_000, 9_999.0))
        self.assertTrue(gate.is_open)

    def test_close_is_idempotent_and_keeps_the_first_reason(self):
        gate = player.PlaybackGate()
        self.assertTrue(gate.close("screen shows 要停顿"))
        self.assertFalse(gate.close("frozen plan exhausted", planned=True))
        self.assertEqual("screen shows 要停顿", gate.closed_reason)
        self.assertFalse(gate.closed_planned)

    def test_a_closed_gate_admits_nothing_and_keeps_its_reason(self):
        gate = player.PlaybackGate(last_valid_event_index=68)
        gate.close("screen shows 要停顿")
        self.assertFalse(gate.admits(0, 0.0))
        self.assertEqual("screen shows 要停顿", gate.closed_reason)

    def test_wait_until_runs_to_the_deadline(self):
        gate = player.PlaybackGate()
        deadline = time.monotonic_ns() + 20 * MS
        self.assertTrue(gate.wait_until(deadline))
        self.assertGreaterEqual(time.monotonic_ns(), deadline)

    def test_close_from_another_thread_cuts_a_long_sleep_short(self):
        """The whole point of the gate: a pending rest must be interruptible."""
        gate = player.PlaybackGate()
        threading.Timer(0.05, gate.close, args=("screen shows the results page",)).start()
        started_ns = time.monotonic_ns()
        # Without cancellation this would block for a full 30 seconds.
        self.assertFalse(gate.wait_until(started_ns + 30_000 * MS))
        self.assertLess(time.monotonic_ns() - started_ns, 5_000 * MS)


class WaitForActionTest(unittest.TestCase):
    def test_returns_false_immediately_when_already_closed(self):
        gate = player.PlaybackGate()
        gate.close("aborted")
        started_ns = time.monotonic_ns()
        self.assertFalse(
            player.wait_for_action(gate, started_ns + 30_000 * MS, 250 * MS)
        )
        self.assertLess(time.monotonic_ns() - started_ns, 1_000 * MS)

    def test_long_waits_are_sliced_so_the_gate_is_re_read(self):
        gate = player.PlaybackGate()
        slices = []
        real_wait_until = gate.wait_until

        def recording_wait_until(deadline_ns):
            slices.append(deadline_ns - time.monotonic_ns())
            return real_wait_until(deadline_ns)

        with mock.patch.object(gate, "wait_until", recording_wait_until):
            threading.Timer(0.12, gate.close, args=("screen verdict",)).start()
            self.assertFalse(
                player.wait_for_action(gate, time.monotonic_ns() + 5_000 * MS, 20 * MS)
            )
        self.assertGreater(len(slices), 1)
        # No single commitment ever exceeds the release window.
        self.assertLessEqual(max(slices), 21 * MS)

    def test_short_waits_go_straight_to_the_deadline(self):
        gate = player.PlaybackGate()
        deadline = time.monotonic_ns() + 5 * MS
        self.assertTrue(player.wait_for_action(gate, deadline, 250 * MS))
        self.assertGreaterEqual(time.monotonic_ns(), deadline)


class PlanGateClosureTest(unittest.TestCase):
    def setUp(self):
        self.now = time.monotonic_ns()
        self.ringing = player.HeldNote(
            event_index=68,
            pitch="Bb4",
            release_beat=71.0,
            scheduled_release_ns=self.now + 500 * MS,
        )
        self.overdue = player.HeldNote(
            event_index=67,
            pitch="C5",
            release_beat=70.0,
            scheduled_release_ns=self.now - 10 * MS,
        )

    def test_a_planned_stop_lets_the_last_note_ring_in_full(self):
        [(note, release_ns)] = player.plan_gate_closure(
            True, (self.ringing,), self.now
        )
        self.assertEqual("Bb4", note.pitch)
        self.assertEqual(self.ringing.scheduled_release_ns, release_ns)

    def test_an_abort_lifts_every_key_now(self):
        [(_, release_ns)] = player.plan_gate_closure(
            False, (self.ringing,), self.now
        )
        self.assertEqual(self.now, release_ns)

    def test_a_release_is_never_pushed_past_its_schedule(self):
        for planned in (True, False):
            [(_, release_ns)] = player.plan_gate_closure(
                planned, (self.overdue,), self.now
            )
            self.assertEqual(self.overdue.scheduled_release_ns, release_ns)

    def test_releases_come_back_in_release_order(self):
        released = player.plan_gate_closure(
            True, (self.ringing, self.overdue), self.now
        )
        self.assertEqual([67, 68], [note.event_index for note, _ in released])


class RecordingInputShell:
    """Stands in for the on-device input bridge; ACKs everything instantly."""

    def __init__(self, *args, **kwargs):
        self.sent: list[tuple[str, str, int]] = []
        self._acks: dict[int, int] = {}
        self._held: list[str] = []

    def send(self, kind, pitch, sequence):
        self.sent.append((kind, pitch, sequence))
        now_ns = time.monotonic_ns()
        self._acks[sequence] = now_ns
        if kind == "DOWN":
            self._held.append(pitch)
        elif pitch in self._held:
            self._held.remove(pitch)
        return now_ns, 0

    def wait_for(self, sequences, timeout):
        return all(sequence in self._acks for sequence in sequences)

    def ack_ns(self, sequence):
        return self._acks.get(sequence)

    @property
    def pitches(self):
        return tuple(self._held)

    def close(self):
        return ""

    def warmup(self, **kwargs):
        return 0.0

    # -- assertions helpers -------------------------------------------------
    @property
    def downs(self):
        return [(pitch, seq) for kind, pitch, seq in self.sent if kind == "DOWN"]

    @property
    def ups(self):
        return [(pitch, seq) for kind, pitch, seq in self.sent if kind == "UP"]


@requires_plans
class FrozenPlanGateIntegrationTest(unittest.TestCase):
    """Drive ``run_frozen_plan`` end to end with no device attached."""

    def _play(self, plan_path, tmp_dir, **overrides):
        args = argparse.Namespace(
            adb="adb",
            serial="test-serial",
            frozen_plan=Path(plan_path),
            keyboard_profile="musette-ultimate-f4",
            # 60000 BPM keeps a beat at 1 ms so the whole song runs in one blink.
            bpm=60_000.0,
            input_advance_ms=0.0,
            score_start_delay_ms=0.0,
            pre_roll=0.0,
            result_wait=0.0,
            release_window_ms=250.0,
            last_valid_event_index=None,
            stop_after_beat=None,
            output_dir=Path(tmp_dir),
        )
        for key, value in overrides.items():
            setattr(args, key, value)

        shell = RecordingInputShell()
        screencap = mock.Mock(stdout=b"\x89PNG\r\n\x1a\n")
        with mock.patch.object(player, "PersistentInputShell", return_value=shell), \
             mock.patch.object(player.shutil, "which", return_value="/usr/bin/adb"), \
             mock.patch.object(player.subprocess, "run", return_value=screencap):
            result = player.run_frozen_plan(args)
        return shell, result

    def test_corrected_plan_plays_every_audited_event(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            shell, result = self._play(CORRECTED_PLAN_PATH, tmp_dir)
        plan = json.loads(CORRECTED_PLAN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(list(range(69)), result["events_sent"])
        self.assertEqual(69, len(shell.downs))
        self.assertEqual(69, len(shell.ups))
        self.assertEqual("Bb4", shell.downs[-1][0])
        self.assertTrue(result["playback_gate_close_was_planned"])
        self.assertEqual(
            [event["pitch"] for event in plan["events"]],
            [pitch for pitch, _ in shell.downs],
        )

    def test_no_key_is_left_down_at_the_end(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            shell, _ = self._play(CORRECTED_PLAN_PATH, tmp_dir)
        self.assertEqual((), shell.pitches)

    def test_the_boundary_suppresses_the_ten_tail_events(self):
        """The regression this gate exists for: replay the 79-event plan."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            shell, result = self._play(
                SUPERSEDED_PLAN_PATH,
                tmp_dir,
                last_valid_event_index=68,
                stop_after_beat=71.0,
            )
        self.assertEqual(list(range(69)), result["events_sent"])
        self.assertEqual(69, len(shell.downs))
        self.assertEqual("Bb4", shell.downs[-1][0])
        # The beat-71 C5 that the app answered with 要停顿 is never sent.
        self.assertNotIn(69, result["events_sent"])
        self.assertEqual((), shell.pitches)

    def test_the_last_valid_note_still_gets_its_full_duration(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            shell, result = self._play(
                SUPERSEDED_PLAN_PATH,
                tmp_dir,
                last_valid_event_index=68,
                stop_after_beat=71.0,
            )
        actions = result["actions"]
        down = next(a for a in actions if a["event"] == 68 and a["kind"] == "DOWN")
        up = next(a for a in actions if a["event"] == 68 and a["kind"] == "UP")
        self.assertEqual(70, down["beat"])
        self.assertEqual(71, up["beat"])
        # One beat is 1 ms at the test BPM, and the release is honoured in full.
        self.assertGreaterEqual(up["sent_ns"] - down["sent_ns"], 900_000)

    def test_a_screen_verdict_mid_note_lifts_the_key_at_once(self):
        """A live stop outranks the plan, and must not strand a held key."""
        import tempfile

        # One long note gives the screen watcher somewhere to interrupt.
        plan = {
            "keyboard_profile": "musette-ultimate-f4",
            "events": [
                {"start_beat": 0, "pitch": "D5", "duration_beats": 1},
                {"start_beat": 1, "pitch": "C5", "duration_beats": 8},
            ],
        }
        gates = []
        real_gate_cls = player.PlaybackGate

        def capture_gate(*args, **kwargs):
            gate = real_gate_cls(*args, **kwargs)
            gates.append(gate)
            # Stand in for the frame pump noticing the results page.
            threading.Timer(0.25, gate.close, args=("screen shows 要停顿",)).start()
            return gate

        with tempfile.TemporaryDirectory() as tmp_dir:
            plan_path = Path(tmp_dir) / "long-note-plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with mock.patch.object(player, "PlaybackGate", capture_gate):
                # 300 BPM puts a beat at 200 ms, so the C5's scheduled release is
                # 1.6 s away -- a wide enough margin that a loaded machine cannot
                # blur an immediate abort into an on-schedule release.
                shell, result = self._play(plan_path, tmp_dir, bpm=300.0)

        self.assertFalse(result["playback_gate_close_was_planned"])
        self.assertEqual("screen shows 要停顿", result["playback_gate_closed_reason"])
        self.assertEqual((), shell.pitches)
        # The C5 went down and was lifted well before its beat-9 release.
        c5_down = next(a for a in result["actions"] if a["pitch"] == "C5" and a["kind"] == "DOWN")
        c5_up = next(a for a in result["actions"] if a["pitch"] == "C5" and a["kind"] == "UP")
        self.assertLess(c5_up["sent_ns"] - c5_down["sent_ns"], 1200 * MS)

    def test_an_unplayable_boundary_is_rejected_before_any_input(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError):
                self._play(
                    CORRECTED_PLAN_PATH, tmp_dir, last_valid_event_index=500
                )


if __name__ == "__main__":
    unittest.main()
