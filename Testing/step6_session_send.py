#!/usr/bin/env python3
"""Queue one command into a live headed Step 6 session and wait for its result.

    python3 Testing/step6_session_send.py <run_dir> <command> [--timeout SEC]

<command> is a file path or a name from Testing/step6_session_commands
(checkpoint_fast, reload, diagnose, cycles, stop). Exit status: 0 ok, 1 command
error, 2 timeout, 3 session not serving or heartbeat lost.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

COMMANDS = Path(__file__).resolve().with_name("step6_session_commands")
HEARTBEAT_LOST_SEC = 120.0


def _resolve(command: str) -> Path:
    path = Path(command)
    if path.is_file():
        return path
    named = COMMANDS / f"{command}.py"
    if named.is_file():
        return named
    raise SystemExit(f"unknown command: {command}")


def send(run_dir: Path, command: str, timeout_sec: float, *, poll=1.0, clock=time.monotonic,
         sleep=time.sleep) -> tuple[int, dict]:
    session = run_dir / "session"
    if not (session / "ready.json").is_file():
        return 3, {"error": "session is not serving (no ready.json)"}
    source = _resolve(command)
    used = [p.name for folder in ("inbox", "running", "done") for p in (session / folder).glob("*.py")]
    number = 1 + max((int(name[:3]) for name in used if name[:3].isdigit()), default=0)
    name = f"{number:03d}-{source.stem}"
    staging = session / f".{name}.py.tmp"
    shutil.copyfile(source, staging)
    staging.rename(session / "inbox" / f"{name}.py")  # atomic: never read half-written
    result_path = session / "outbox" / f"{name}.json"
    started = clock()
    while clock() - started < timeout_sec:
        if result_path.is_file():
            record = json.loads(result_path.read_text())
            return (0 if record.get("status") == "ok" else 1), record
        if (run_dir / "transaction-status.json").is_file():
            return 3, {"error": "the run has ended", "command": name}
        beat = session / "heartbeat"
        queued = (session / "inbox" / f"{name}.py").is_file()
        if queued and beat.is_file() and time.time() - beat.stat().st_mtime > HEARTBEAT_LOST_SEC:
            return 3, {"error": "heartbeat lost before the command started", "command": name}
        sleep(poll)
    return 2, {"error": "timeout", "command": name}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("command")
    parser.add_argument("--timeout", type=float, default=3600.0)
    args = parser.parse_args(argv)
    code, record = send(args.run_dir, args.command, args.timeout)
    print(json.dumps(record, indent=2)[:20000])
    return code


if __name__ == "__main__":
    sys.exit(main())
