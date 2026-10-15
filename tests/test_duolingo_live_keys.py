"""Live input ordering and cleanup across note and abort boundaries."""

import sys
from pathlib import Path
import time
import unittest


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from duolingo_live_keys import LiveKeys


class RecordingShell:
    def __init__(self):
        self.sent = []
        self.acks = {}

    def send(self, kind, pitch, sequence):
        self.sent.append((kind, pitch, sequence))
        return time.monotonic_ns(), 0

    def ack_ns(self, sequence):
        return self.acks.get(sequence)


class LiveKeysTest(unittest.TestCase):
    def test_late_down_preserves_the_requested_hold_duration(self):
        deadline_ns = time.monotonic_ns() + 1_000_000_000
        sent_ns = deadline_ns + 24_000_000

        class LateShell:
            def send(self, kind, pitch, sequence):
                if kind != "DOWN":
                    raise AssertionError(f"unexpected edge: {kind}")
                return sent_ns, 0

        shell = LateShell()
        keys = LiveKeys(shell)
        self.assertEqual(
            sent_ns,
            keys.press(pitch="F4", beat=16.5, deadline_ns=deadline_ns, hold_ms=273),
        )
        self.assertEqual(sent_ns + 273_000_000, keys.next_release_ns)

    def test_repeated_pitch_releases_before_next_down(self):
        shell = RecordingShell()
        keys = LiveKeys(shell)
        first_ns = time.monotonic_ns()
        keys.press(pitch="C4", beat=0.0, deadline_ns=first_ns, hold_ms=100)
        keys.press(pitch="C4", beat=0.5, deadline_ns=first_ns, hold_ms=20)
        keys.finish()
        self.assertEqual(
            ["DOWN", "UP", "DOWN", "UP"],
            [kind for kind, _, _ in shell.sent],
        )
        self.assertGreater(keys.actions[1]["early_retrigger_ms"], 0)
        self.assertEqual((), keys.held_pitches)

    def test_abort_lifts_every_key_and_cancels_future_releases(self):
        shell = RecordingShell()
        keys = LiveKeys(shell)
        due_ns = time.monotonic_ns()
        keys.press(pitch="C4", beat=0, deadline_ns=due_ns, hold_ms=1000)
        keys.press(pitch="E4", beat=0, deadline_ns=due_ns, hold_ms=1000)
        keys.abort()
        keys.release_due(due_ns + 2_000_000_000)
        self.assertEqual(2, sum(kind == "UP" for kind, _, _ in shell.sent))
        self.assertEqual((), keys.held_pitches)
        self.assertIsNone(keys.next_release_ns)

    def test_edge_callback_receives_actual_down_and_up_send_times(self):
        shell = RecordingShell()
        edges = []
        keys = LiveKeys(shell, on_edge=lambda kind, pitch, sent_ns: edges.append(
            (kind, pitch, sent_ns)
        ))
        now_ns = time.monotonic_ns()
        keys.press(pitch="F4", beat=0, deadline_ns=now_ns, hold_ms=1)
        keys.release_due(now_ns + 2_000_000)
        self.assertEqual(["DOWN", "UP"], [edge[0] for edge in edges])
        self.assertEqual(["F4", "F4"], [edge[1] for edge in edges])
        self.assertEqual([action["sent_ns"] for action in keys.actions],
                         [edge[2] for edge in edges])

    def test_ack_latencies_keep_missing_ack_visible(self):
        shell = RecordingShell()
        keys = LiveKeys(shell)
        now_ns = time.monotonic_ns()
        keys.press(pitch="C4", beat=0, deadline_ns=now_ns, hold_ms=10)
        sent = keys.actions[0]
        shell.acks[sent["sequence"]] = sent["sent_ns"] + 12_345_000
        keys.record_ack_latencies()
        self.assertEqual(12.345, sent["ack_latency_ms"])
        keys.abort()
        keys.record_ack_latencies()
        self.assertIsNone(keys.actions[1]["ack_latency_ms"])


if __name__ == "__main__":
    unittest.main()
