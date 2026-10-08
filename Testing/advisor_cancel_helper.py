#!/usr/bin/env python3
"""Independent Cancel input for the S6-ADVISOR-GUI-01 B verification (runs OUTSIDE Slicer, on the same host).

    python3 Testing/advisor_cancel_helper.py <session_dir> --display :N [--timeout-sec 1800] [--receipt-log PATH]

Waits for ``<session_dir>/cancel-arm.json`` (written by the session command: Cancel button screen coordinates, the
target sub-step and the timeline path), then watches the flushed timeline until the target sub-step is executing
(a ``step_start`` with no later ``step_end``), waits ``offset_sec`` and injects ONE real X11 click with ``xdotool``.
It stamps ``time.monotonic_ns()`` before and after the injection (same CLOCK_MONOTONIC as the in-process stamps) and
optionally records an independent receipt (``xinput test-xi2 --root`` lines stamped on arrival). Writes
``<session_dir>/cancel-helper.json``. It never touches Slicer, ROS or any file other than its own outputs, and sends at
most one click. A Qt-timer click would only measure event delivery; this stamps when the input was actually sent.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


def last_open_step(rows: list) -> dict | None:
    """The newest ``step_start`` that has no later ``step_end`` (the sub-step currently blocking Qt)."""

    for row in reversed(rows):
        if row.get("kind") == "step_end":
            return None
        if row.get("kind") == "step_start":
            return row
    return None


def read_rows(path: Path) -> list:
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass  # a half-written last line is ignored on this poll
    return rows


def should_fire(open_step: dict | None, arm: dict) -> bool:
    return (open_step is not None and open_step.get("step") == arm["target_step"]
            and int(open_step.get("candidate") or 0) >= int(arm["min_candidate"]))


def _receipt_thread(display: str, path: Path, stop: threading.Event) -> subprocess.Popen | None:
    if not shutil.which("xinput"):
        return None
    proc = subprocess.Popen(["xinput", "test-xi2", "--root"], env=dict(os.environ, DISPLAY=display),
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    def pump():
        with path.open("w", encoding="utf-8") as out:
            for line in proc.stdout:
                out.write(f"{time.monotonic_ns()} {line}")
                out.flush()
                if stop.is_set():
                    break

    threading.Thread(target=pump, daemon=True).start()
    return proc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--display", required=True)
    parser.add_argument("--timeout-sec", type=float, default=1800.0)
    parser.add_argument("--receipt-log", type=Path)
    args = parser.parse_args(argv)
    if not shutil.which("xdotool"):
        print("xdotool is not available", file=sys.stderr)
        return 3
    arm_path = args.session_dir / "cancel-arm.json"
    deadline = time.monotonic() + args.timeout_sec
    stop = threading.Event()
    receipt = _receipt_thread(args.display, args.receipt_log, stop) if args.receipt_log else None
    result = {"display": args.display, "started_mono_ns": time.monotonic_ns(), "sent": False}
    try:
        while not arm_path.is_file():
            if time.monotonic() > deadline:
                result["error"] = "not armed within the timeout"
                return 2
            time.sleep(0.2)
        arm = json.loads(arm_path.read_text(encoding="utf-8"))
        result["arm"] = arm
        while True:
            if time.monotonic() > deadline:
                result["error"] = "target sub-step never became the executing step"
                return 2
            open_step = last_open_step(read_rows(Path(arm["timeline"])))
            if should_fire(open_step, arm):
                result["target_step_start_ns"] = open_step["mono_ns"]
                break
            time.sleep(0.1)
        time.sleep(float(arm["offset_sec"]))
        still_open = last_open_step(read_rows(Path(arm["timeline"])))
        if (not should_fire(still_open, arm) or still_open.get("mono_ns") != open_step["mono_ns"]):
            result["error"] = "the armed step finished before input; no click was sent"
            return 2
        env = dict(os.environ, DISPLAY=args.display)
        subprocess.run(["xdotool", "mousemove", str(arm["x"]), str(arm["y"])], env=env, check=True, timeout=10)
        result["t_send_before_ns"] = time.monotonic_ns()
        subprocess.run(["xdotool", "click", "1"], env=env, check=True, timeout=10)
        result["t_send_after_ns"] = time.monotonic_ns()
        result["sent"] = True
        time.sleep(1.0)
        return 0
    finally:
        stop.set()
        if receipt is not None:
            receipt.terminate()
        (args.session_dir / "cancel-helper.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
