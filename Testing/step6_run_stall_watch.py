#!/usr/bin/env python3
"""Host-side stall watcher for one headed Step 6 run (operator 2026-10-03).

    python3 Testing/step6_run_stall_watch.py <run_dir> [--idle-sec 600] [--poll-sec 20]

When ``<run>/campaign.log`` has not grown for ``--idle-sec``, it asks this run's
Slicer for one all-thread Python stack dump by sending SIGUSR1 (handled by
``faulthandler.register`` in the generated wrapper). It replaces the periodic
``dump_traceback_later`` watchdog that crashed r16 with SIGSEGV.

Safety: it signals only the PID in ``<run>/slicer.pid`` and only after the
container's ``/proc/<pid>/cmdline`` shows ``SlicerApp-real`` launched with this
run's ``faulthandler-wrapper.py``. It never kills or stops anything. At most
``MAX_DUMPS`` dumps; it re-arms only after the log grows again. Every event is
recorded in ``<run>/stall-watch.json``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

CONTAINER = "dentobot-slicerros2"
MAX_DUMPS = 3


def _docker(args, *, runner=subprocess.run):
    return runner(["docker", "exec", CONTAINER, *args], capture_output=True, text=True, check=False)


def owned_slicer_pid(run_dir: Path, *, runner=subprocess.run) -> tuple[int | None, str]:
    """PID of this run's Slicer, or (None, reason) when ownership is not proven."""
    pid_file = run_dir / "slicer.pid"
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return None, "slicer.pid missing or invalid"
    out = _docker(["cat", f"/proc/{pid}/cmdline"], runner=runner)
    cmdline = (out.stdout or "").replace("\0", " ")
    if out.returncode != 0 or not cmdline:
        return None, f"pid {pid} not running in {CONTAINER}"
    if "SlicerApp-real" not in cmdline:
        return None, f"pid {pid} is not SlicerApp-real"
    if f"{run_dir.name}/faulthandler-wrapper.py" not in cmdline:
        return None, f"pid {pid} was not launched by run {run_dir.name}"
    return pid, "owned"


def watch(run_dir: Path, *, idle_sec=600.0, poll_sec=20.0, runner=subprocess.run,
          clock=time.time, sleep=time.sleep) -> dict:
    log = run_dir / "campaign.log"
    record_path = run_dir / "stall-watch.json"
    record = {"run": run_dir.name, "idle_sec": idle_sec, "events": []}
    armed = True
    last_size = -1

    def save():
        record_path.write_text(json.dumps(record, indent=2) + "\n")

    save()
    while not (run_dir / "transaction-status.json").is_file():
        try:
            stat = log.stat()
        except OSError:
            sleep(poll_sec)
            continue
        if stat.st_size != last_size:
            if not armed and last_size >= 0:
                record["events"].append({"at": clock(), "event": "progress_resumed"})
                save()
            armed = True
            last_size = stat.st_size
        idle = clock() - stat.st_mtime
        dumps = sum(1 for event in record["events"] if event["event"] == "sigusr1_sent")
        if armed and idle > idle_sec and dumps < MAX_DUMPS:
            faulthandler_log = run_dir / "faulthandler.log"
            before = faulthandler_log.stat().st_size if faulthandler_log.is_file() else 0
            pid, reason = owned_slicer_pid(run_dir, runner=runner)
            event = {"at": clock(), "idle_sec": round(idle, 1), "pid": pid, "ownership": reason}
            if pid is None:
                event["event"] = "not_signalled"
            else:
                result = _docker(["kill", "-USR1", str(pid)], runner=runner)
                event["event"] = "sigusr1_sent" if result.returncode == 0 else "signal_failed"
                sleep(5)
                event["faulthandler_log_bytes_added"] = (
                    (faulthandler_log.stat().st_size if faulthandler_log.is_file() else 0) - before
                )
            record["events"].append(event)
            save()
            armed = False
        sleep(poll_sec)
    record["ended"] = clock()
    save()
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--idle-sec", type=float, default=600.0)
    parser.add_argument("--poll-sec", type=float, default=20.0)
    args = parser.parse_args(argv)
    record = watch(args.run_dir, idle_sec=args.idle_sec, poll_sec=args.poll_sec)
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
