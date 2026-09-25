#!/usr/bin/env python3
"""Sample one Slicer/ROS container session without touching its processes."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import time


CGROUP = Path("/sys/fs/cgroup")
PROC = Path("/proc")
HZ = os.sysconf("SC_CLK_TCK")
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
stop = False


def read(path):
    try:
        return Path(path).read_text().strip()
    except (OSError, UnicodeError):
        return ""


def fields(path):
    result = {}
    for line in read(path).splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            result[parts[0].rstrip(":")] = parts[1]
    return result


def number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def process(pid, previous, elapsed):
    path = PROC / str(pid)
    stat = read(path / "stat")
    if ") " not in stat:
        return None
    name, tail = stat.split(") ", 1)
    parts = tail.split()
    if len(parts) < 22:
        return None
    ticks = int(parts[11]) + int(parts[12])
    status = fields(path / "status")
    rss_kib = number(status.get("VmRSS", "").split(" ", 1)[0])
    try:
        fds = len(os.listdir(path / "fd"))
    except OSError:
        fds = None
    return {
        "pid": pid,
        "name": name.rsplit("(", 1)[-1],
        "state": parts[0],
        "ppid": number(parts[1]),
        "rss_mib": round(rss_kib / 1024, 1) if rss_kib is not None else None,
        "threads": number(status.get("Threads")),
        "fds": fds,
        "cpu_percent": round(100 * max(0, ticks - previous.get(pid, ticks)) / (HZ * elapsed), 1),
        "ticks": ticks,
    }


def snapshot(previous, elapsed, output_root):
    processes = []
    for entry in PROC.iterdir():
        if entry.name.isdecimal():
            try:
                item = process(int(entry.name), previous, elapsed)
            except (OSError, ValueError, IndexError):
                item = None
            if item:
                processes.append(item)
    next_ticks = {item["pid"]: item.pop("ticks") for item in processes}
    mem = fields(PROC / "meminfo")
    disk = os.statvfs(output_root)
    cgroup = {
        key: read(CGROUP / key)
        for key in ("memory.current", "memory.max", "memory.events", "memory.pressure",
                    "cpu.max", "cpu.stat", "cpu.pressure", "pids.current", "pids.max", "io.pressure")
    }
    alerts = []
    memory_max = number(cgroup["memory.max"])
    memory_used = number(cgroup["memory.current"])
    if memory_max and memory_used is not None and memory_used / memory_max >= 0.9:
        alerts.append("cgroup_memory_above_90_percent")
    pids_max = number(cgroup["pids.max"])
    pids_used = number(cgroup["pids.current"])
    if pids_max and pids_used is not None and pids_used / pids_max >= 0.9:
        alerts.append("cgroup_pids_above_90_percent")
    free_gib = round(disk.f_bavail * disk.f_frsize / (1024 ** 3), 2)
    if free_gib < 2:
        alerts.append("run_log_disk_below_2_gib")
    return {
        "sample_gap_seconds": round(elapsed, 3),
        "alerts": alerts,
        "process_count": len(processes),
        "zombie_count": sum(item["state"] == "Z" for item in processes),
        "top_processes": sorted(processes, key=lambda item: item["rss_mib"] or 0, reverse=True)[:12],
        "slicer_present": any(item["name"] in {"Slicer", "SlicerApp-real"} for item in processes),
        "host_mem_available_kib": number(mem.get("MemAvailable", "").split(" ", 1)[0]),
        "host_swap_free_kib": number(mem.get("SwapFree", "").split(" ", 1)[0]),
        "host_load_average": tuple(round(value, 2) for value in os.getloadavg()),
        "host_pressure": {kind: read(PROC / "pressure" / kind) for kind in ("cpu", "memory", "io")},
        "cgroup": cgroup,
        "log_disk_free_gib": free_gib,
    }, next_ticks


def on_signal(_signum, _frame):
    global stop
    stop = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--output-path", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=5)
    args = parser.parse_args()
    if not 1 <= args.interval <= 60:
        parser.error("interval must be between 1 and 60 seconds")
    path = args.output_path
    path.parent.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    previous = {}
    previous_time = time.monotonic()
    saw_slicer = False
    with path.open("a", encoding="utf-8", buffering=1) as log:
        log.write(json.dumps({"event": "MONITOR_START", "utc": datetime.now(timezone.utc).isoformat(),
                              "parent_pid": args.parent_pid, "interval_seconds": args.interval}) + "\n")
        while not stop and (PROC / str(args.parent_pid)).exists():
            now = time.monotonic()
            try:
                data, previous = snapshot(previous, max(now - previous_time, 0.001), path.parent)
                event = "RESOURCE_SAMPLE"
                if saw_slicer and not data["slicer_present"]:
                    event = "SLICER_EXIT_OBSERVED"
                saw_slicer |= data["slicer_present"]
                log.write(json.dumps({"event": event, "utc": datetime.now(timezone.utc).isoformat(), **data},
                                     separators=(",", ":")) + "\n")
            except OSError as exc:
                log.write(json.dumps({"event": "MONITOR_ERROR", "error": str(exc)}) + "\n")
            previous_time = now
            time.sleep(args.interval)
        log.write(json.dumps({"event": "MONITOR_STOP", "utc": datetime.now(timezone.utc).isoformat(),
                              "reason": "signal" if stop else "parent_exited"}) + "\n")


if __name__ == "__main__":
    main()
