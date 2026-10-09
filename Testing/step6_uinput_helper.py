#!/usr/bin/env python3
"""Host-side owner of the uinput pointer for the Step 6 harness (S6-ADVISOR-GUI-01).

Runs on the host that owns the desktop, outside the DentoBot container, because the container
has no /dev/uinput device. The in-container harness (DENTOBOT_HEADED_INPUT=uinput with
DENTOBOT_UINPUT_RELAY_DIR set) writes requests into a relay directory in the run root:

  requests/<name>.json    {"op": "abs_move", "x", "y"}  or  {"op": "button", "button": 1, "pressed"}
  responses/<name>.json   {"name", "ok", "error", "utc"}

The helper executes only those two operations, with absolute values in 0..UINPUT_ABS_MAX. It never
chooses a position: the harness computes the absolute values from the X root and verifies each move
with XQueryPointer. Files written: owner.json (this PID and its start ticks), ready.json once the
device is enumerated (or failed.json if it could not be created), and stopped.json on exit.

The helper exits when shutdown.request appears in the relay, after an idle timeout, or on SIGTERM or
SIGINT. Every exit destroys the kernel device. A relay directory that already has owner.json,
ready.json or failed.json is refused: one helper per run, never reused.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import step6_user_input as ui  # noqa: E402

DEFAULT_IDLE_TIMEOUT_SEC = 7200.0
SHUTDOWN_REQUEST = "shutdown.request"
POLL_SEC = 0.005
RELAY_MARKERS = ("owner.json", "ready.json", "failed.json")


def _start_ticks(pid: int) -> int:
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    return int(stat[stat.rfind(")") + 2:].split()[19])


def _coordinate(value) -> int:
    if type(value) is not int or not 0 <= value <= ui.UINPUT_ABS_MAX:
        raise ValueError(f"absolute value {value!r} is outside 0..{ui.UINPUT_ABS_MAX}")
    return value


def execute(device, request: dict, name: str) -> dict:
    """Run one request on ``device``. A refusal is answered and the device is not touched."""
    try:
        op = request.get("op")
        if op == "abs_move":
            device.abs_move(_coordinate(request.get("x")), _coordinate(request.get("y")))
        elif op == "button":
            if type(request.get("button")) is not int or request["button"] != 1:
                raise ValueError("a button request must be button 1")
            if type(request.get("pressed")) is not bool:
                raise ValueError("a button request needs a boolean pressed")
            device.button(request["pressed"])
        else:
            raise ValueError(f"unknown op {op!r}")
    except Exception as exc:  # answered to the harness, which fails loudly
        return {"name": name, "ok": False, "error": f"{type(exc).__name__}: {exc}", "utc": ui.utc_now()}
    return {"name": name, "ok": True, "error": None, "utc": ui.utc_now()}


def _read_request(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}  # a malformed request is answered as an unknown op
    return payload if isinstance(payload, dict) else {}


def _pending(requests_dir: Path, responses_dir: Path) -> list[str]:
    return sorted(path.name for path in requests_dir.glob("*.json")
                  if not (responses_dir / path.name).exists())


def serve(root, device, *, idle_timeout_sec: float = DEFAULT_IDLE_TIMEOUT_SEC,
          settle_sec: float = ui.UINPUT_SETTLE_SEC, poll_sec: float = POLL_SEC,
          sleep=time.sleep, now=time.monotonic, interrupted=lambda: False) -> dict:
    """Create ``device``, serve requests from ``root`` until a shutdown reason, then destroy it."""
    root = Path(root)
    requests_dir, responses_dir = root / "requests", root / "responses"
    requests_dir.mkdir(parents=True, exist_ok=True)
    responses_dir.mkdir(parents=True, exist_ok=True)
    try:
        device.create()
    except ui.UserInputError as exc:
        ui.write_atomic_json(root / "failed.json", {"error": str(exc), "utc": ui.utc_now()})
        raise
    reason, served = "error", 0
    try:
        sleep(settle_sec)
        pid = os.getpid()
        ui.write_atomic_json(root / "owner.json", {"pid": pid, "start_ticks": _start_ticks(pid),
                                                   "utc": ui.utc_now()})
        ui.write_atomic_json(root / "ready.json", {"ready": True, "abs_max": ui.UINPUT_ABS_MAX,
                                                   "device": ui.UINPUT_DEVICE_NAME, "pid": pid,
                                                   "utc": ui.utc_now()})
        last_activity = now()
        reason = None
        while reason is None:
            if interrupted():
                reason = "signal"
            elif (root / SHUTDOWN_REQUEST).exists():
                reason = SHUTDOWN_REQUEST
            else:
                pending = _pending(requests_dir, responses_dir)
                if pending:
                    name = pending[0]
                    response = execute(device, _read_request(requests_dir / name), name)
                    ui.write_atomic_json(responses_dir / name, response)
                    served += 1
                    last_activity = now()
                elif now() - last_activity >= idle_timeout_sec:
                    reason = "idle timeout"
                else:
                    sleep(poll_sec)
    finally:
        close_error = None
        try:
            device.close()
        except ui.UserInputError as exc:  # recorded in stopped.json; the device is closed as far as possible
            close_error = str(exc)
        ui.write_atomic_json(root / "stopped.json", {"reason": reason or "error",
                                                     "requests_served": served,
                                                     "close_error": close_error,
                                                     "utc": ui.utc_now()})
    return {"reason": reason, "requests_served": served, "close_error": close_error}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Own the uinput pointer for a Step 6 run's relay directory.")
    parser.add_argument("--relay-dir", required=True, help="run-root relay directory (created if missing)")
    parser.add_argument("--idle-timeout-sec", type=float, default=DEFAULT_IDLE_TIMEOUT_SEC)
    args = parser.parse_args(argv)
    root = Path(args.relay_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    used = [name for name in RELAY_MARKERS if (root / name).exists()]
    if used:
        print(f"refusing: the relay directory was already used ({', '.join(used)})", file=sys.stderr)
        return 2
    interrupted = {"set": False}

    def _on_signal(signum, _frame):
        interrupted["set"] = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    try:
        summary = serve(root, ui.UinputDevice(), idle_timeout_sec=args.idle_timeout_sec,
                        interrupted=lambda: interrupted["set"])
    except ui.UserInputError as exc:
        print(f"uinput helper failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
