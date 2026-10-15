"""Send live piano key edges in order from one playback thread."""

from __future__ import annotations

import heapq
import time
from typing import Callable


class LiveKeys:
    """Track every DOWN until its UP, including during an emergency stop."""

    def __init__(
        self, input_shell, *, first_sequence: int = 3000,
        on_edge: Callable[[str, str, int], None] | None = None,
    ) -> None:
        self._shell = input_shell
        self._on_edge = on_edge
        self._sequence = first_sequence
        self._releases: list[tuple[int, int, str]] = []
        self._held: dict[str, int] = {}
        self.actions: list[dict] = []

    def _send(self, kind: str, pitch: str, beat: float, deadline_ns: int) -> int:
        self._sequence += 1
        sent_ns, pending = self._shell.send(kind, pitch, self._sequence)
        self.actions.append({
            "sequence": self._sequence,
            "kind": kind,
            "pitch": pitch,
            "beat": beat,
            "deadline_ns": deadline_ns,
            "sent_ns": sent_ns,
            "drift_ms": (sent_ns - deadline_ns) / 1_000_000,
            "device_queue_depth": pending,
        })
        if self._on_edge is not None:
            self._on_edge(kind, pitch, sent_ns)
        return sent_ns

    def release_due(self, now_ns: int) -> None:
        while self._releases and self._releases[0][0] <= now_ns:
            release_ns, _, pitch = heapq.heappop(self._releases)
            if self._held.get(pitch) != release_ns:
                continue
            self._send("UP", pitch, 0.0, release_ns)
            del self._held[pitch]

    def press(
        self, *, pitch: str, beat: float, deadline_ns: int, hold_ms: float
    ) -> int:
        self.release_due(time.monotonic_ns())
        if pitch in self._held:
            previous_release_ns = self._held.pop(pitch)
            released_ns = self._send("UP", pitch, beat, previous_release_ns)
            self.actions[-1]["early_retrigger_ms"] = max(
                0.0, (previous_release_ns - released_ns) / 1_000_000,
            )
        sent_ns = self._send("DOWN", pitch, beat, deadline_ns)
        release_ns = sent_ns + round(hold_ms * 1_000_000)
        self._held[pitch] = release_ns
        heapq.heappush(self._releases, (release_ns, self._sequence, pitch))
        return sent_ns

    @property
    def next_release_ns(self) -> int | None:
        return self._releases[0][0] if self._releases else None

    @property
    def held_pitches(self) -> tuple[str, ...]:
        return tuple(self._held)

    def record_ack_latencies(self) -> None:
        """Attach observed bridge round trips without changing playback timing."""
        for action in self.actions:
            ack_ns = self._shell.ack_ns(action["sequence"])
            action["ack_latency_ms"] = (
                round((ack_ns - action["sent_ns"]) / 1_000_000, 3)
                if ack_ns is not None else None
            )

    def finish(self) -> None:
        """Complete valid note durations after the final onset."""
        while self._releases:
            now_ns = time.monotonic_ns()
            self.release_due(now_ns)
            if self._releases:
                time.sleep(min((self._releases[0][0] - now_ns) / 1e9, 0.01))

    def abort(self) -> None:
        """Release held keys immediately and discard their planned UPs."""
        self._releases.clear()
        for pitch in tuple(self._held):
            self._send("UP", pitch, 0.0, time.monotonic_ns())
            del self._held[pitch]
