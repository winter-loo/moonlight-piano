#!/usr/bin/env python3
"""Persist and enforce a hard three-attempt budget for one Duolingo challenge."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


MAX_ATTEMPTS = 3


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_state(path: Path) -> dict[str, object]:
    if not path.exists():
        raise SystemExit(f"state does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(path: Path, state: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def init(path: Path, challenge: str) -> None:
    if path.exists():
        state = read_state(path)
        if state.get("challenge") != challenge:
            raise SystemExit("existing state belongs to a different challenge")
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return
    state: dict[str, object] = {
        "challenge": challenge,
        "max_attempts": MAX_ATTEMPTS,
        "attempts_started": 0,
        "active_attempt": None,
        "history": [],
        "created_at": now(),
    }
    write_state(path, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))


def start(path: Path, label: str) -> None:
    state = read_state(path)
    if state.get("active_attempt") is not None:
        raise SystemExit("an attempt is already active")
    count = int(state["attempts_started"])
    if count >= int(state["max_attempts"]):
        print("attempt budget exhausted: refusing attempt 4", file=sys.stderr)
        raise SystemExit(3)
    attempt = {"number": count + 1, "label": label, "started_at": now()}
    history = list(state["history"])
    history.append(attempt)
    state["history"] = history
    state["attempts_started"] = count + 1
    state["active_attempt"] = count + 1
    write_state(path, state)
    print(json.dumps(attempt, ensure_ascii=False, indent=2))


def finish(path: Path, result: str) -> None:
    state = read_state(path)
    active = state.get("active_attempt")
    if active is None:
        raise SystemExit("no active attempt to finish")
    history = list(state["history"])
    record = dict(history[-1])
    if record.get("number") != active:
        raise SystemExit("state history is inconsistent")
    record.update({"finished_at": now(), "result": result})
    history[-1] = record
    state["history"] = history
    state["active_attempt"] = None
    write_state(path, state)
    print(json.dumps(record, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--challenge", required=True)
    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("--label", required=True)
    finish_parser = subparsers.add_parser("finish")
    finish_parser.add_argument("--result", required=True)
    subparsers.add_parser("status")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "init":
        init(args.state, args.challenge)
    elif args.command == "start":
        start(args.state, args.label)
    elif args.command == "finish":
        finish(args.state, args.result)
    else:
        print(json.dumps(read_state(args.state), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
