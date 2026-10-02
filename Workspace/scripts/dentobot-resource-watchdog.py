#!/usr/bin/env python3
"""Sample one Slicer/ROS container session without touching its processes."""

import argparse
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import uuid


CGROUP = Path("/sys/fs/cgroup")
PROC = Path("/proc")
HZ = os.sysconf("SC_CLK_TCK")
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
DISK_SECTOR_BYTES = 512
SESSION_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
HEX_RE = re.compile(r"[0-9a-f]{7,64}")
CHECKOUT_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")
SLICER_VERSION_RE = re.compile(r"5\.\d{1,2}")
RUN_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")
# Directory names that hold many runs' logs and therefore do not identify one run.
SHARED_LOG_DIRECTORIES = {"ui-watchdog", "dentobot-runs", "tmp"}
# Host alert thresholds, chosen from the 24 Sep - 2 Oct 2026 native Ubuntu
# evidence: pressure that high occurred in about 1% of Slicer samples and
# coincided with a 2.5x higher chance of a UI stall.
ALERT_HOST_MEM_AVAILABLE_KIB = 2 * 1024 * 1024
ALERT_HOST_SWAP_USED_FRACTION = 0.75
ALERT_MEMORY_PRESSURE_FULL_AVG10 = 5.0
ALERT_IO_PRESSURE_FULL_AVG10 = 20.0
ALERT_CPU_PRESSURE_SOME_AVG10 = 80.0
ALERT_SWAP_BYTES_PER_SECOND = 20 * 1024 * 1024
ALERT_SLICER_RSS_MIB = 5 * 1024
ALERT_SLICER_RSS_GROWTH_MIB = 1024
ALERT_SLICER_RSS_GROWTH_WINDOW_SECONDS = 120
ALERT_LOAD_PER_CPU = 2.0
METADATA_KEYS = (
    "session_id",
    "environment",
    "source_checkout",
    "source_revision",
    "source_dirty",
    "source_dirty_fingerprint",
    "slicer_version",
    "image_id",
    "native_module_identity",
)
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


def parse_vmstat(text):
    counters = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in {"pswpin", "pswpout", "pgmajfault"}:
            value = number(parts[1])
            if value is not None and value >= 0:
                counters[parts[0]] = value
    return counters


def parse_diskstats(text):
    devices = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 14 or not re.fullmatch(r"[A-Za-z0-9_.-]+", parts[2]):
            continue
        values = [number(parts[index]) for index in (5, 9, 12, 13)]
        if any(value is None or value < 0 for value in values):
            continue
        devices[parts[2]] = dict(zip(
            ("read_sectors", "write_sectors", "io_time_ms", "weighted_io_time_ms"),
            values,
        ))
    return devices


def parse_cgroup_io_stat(text):
    if not text:
        return None
    devices = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts or not re.fullmatch(r"\d+:\d+", parts[0]):
            continue
        counters = {}
        for item in parts[1:]:
            key, separator, value = item.partition("=")
            parsed = number(value) if separator else None
            if re.fullmatch(r"[a-z_]+", key) and parsed is not None and parsed >= 0:
                counters[key] = parsed
        if counters:
            devices[parts[0]] = counters
    return devices or None


def counter_delta(current, previous):
    if current is None or previous is None or current < previous:
        return None
    return current - previous


def counter_rate(delta, elapsed):
    if delta is None or elapsed <= 0:
        return None
    return round(delta / elapsed, 3)


def resource_counters(previous, elapsed):
    vmstat = parse_vmstat(read(PROC / "vmstat"))
    diskstats = parse_diskstats(read(PROC / "diskstats"))
    old_vmstat = previous.get("vmstat", {})
    old_diskstats = previous.get("diskstats", {})

    swap_in = counter_delta(vmstat.get("pswpin"), old_vmstat.get("pswpin"))
    swap_out = counter_delta(vmstat.get("pswpout"), old_vmstat.get("pswpout"))
    major_faults = counter_delta(vmstat.get("pgmajfault"), old_vmstat.get("pgmajfault"))
    devices = {}
    for name, counters in diskstats.items():
        old = old_diskstats.get(name, {})
        read_sectors = counter_delta(counters.get("read_sectors"), old.get("read_sectors"))
        write_sectors = counter_delta(counters.get("write_sectors"), old.get("write_sectors"))
        io_time = counter_delta(counters.get("io_time_ms"), old.get("io_time_ms"))
        weighted_io_time = counter_delta(
            counters.get("weighted_io_time_ms"), old.get("weighted_io_time_ms")
        )
        devices[name] = {
            "read_bytes_per_second": counter_rate(
                read_sectors * DISK_SECTOR_BYTES if read_sectors is not None else None,
                elapsed,
            ),
            "write_bytes_per_second": counter_rate(
                write_sectors * DISK_SECTOR_BYTES if write_sectors is not None else None,
                elapsed,
            ),
            "io_time_ms_delta": io_time,
            "io_time_ms_per_second": counter_rate(io_time, elapsed),
            "weighted_io_time_ms_delta": weighted_io_time,
            "weighted_io_time_ms_per_second": counter_rate(weighted_io_time, elapsed),
        }

    return {
        "host_paging": {
            "page_size_bytes": PAGE_SIZE,
            "swap_in_pages_delta": swap_in,
            "swap_in_bytes_per_second": counter_rate(
                swap_in * PAGE_SIZE if swap_in is not None else None, elapsed
            ),
            "swap_out_pages_delta": swap_out,
            "swap_out_bytes_per_second": counter_rate(
                swap_out * PAGE_SIZE if swap_out is not None else None, elapsed
            ),
            "major_faults_delta": major_faults,
            "major_faults_per_second": counter_rate(major_faults, elapsed),
        },
        "host_disk_io": {"sector_size_bytes": DISK_SECTOR_BYTES, "devices": devices},
        "cgroup_io_stat": parse_cgroup_io_stat(read(CGROUP / "io.stat")),
    }, {"vmstat": vmstat, "diskstats": diskstats}


def valid_session_id(value):
    return value if isinstance(value, str) and SESSION_ID_RE.fullmatch(value) else None


def safe_checkout(value):
    if not isinstance(value, str) or value in {".", ".."} or "\\" in value or Path(value).name != value:
        return None
    return value if CHECKOUT_RE.fullmatch(value) else None


def sanitized_metadata(value, session_id=None, source_checkout=None, slicer_version=None):
    try:
        raw = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    sid = valid_session_id(session_id) or valid_session_id(raw.get("session_id"))
    metadata = {key: None for key in METADATA_KEYS}
    metadata["session_id"] = sid
    metadata["environment"] = (
        "native-ubuntu" if raw.get("environment") == "native-ubuntu" else None
    )
    metadata["source_checkout"] = safe_checkout(raw.get("source_checkout")) or safe_checkout(source_checkout)
    revision = raw.get("source_revision")
    metadata["source_revision"] = revision if isinstance(revision, str) and HEX_RE.fullmatch(revision) else None
    dirty = raw.get("source_dirty")
    metadata["source_dirty"] = dirty if type(dirty) is bool else None
    fingerprint = raw.get("source_dirty_fingerprint")
    metadata["source_dirty_fingerprint"] = (
        fingerprint if isinstance(fingerprint, str) and re.fullmatch(r"[0-9a-f]{64}", fingerprint) else None
    )
    version = raw.get("slicer_version") or slicer_version
    metadata["slicer_version"] = (
        version if isinstance(version, str) and SLICER_VERSION_RE.fullmatch(version) else None
    )
    return metadata["session_id"], metadata


def environment_label():
    if os.environ.get("WSL_INTEROP"):
        return None
    kernel = read(PROC / "sys/kernel/osrelease").lower()
    if "microsoft" in kernel or "wsl" in kernel:
        return None
    for line in read("/etc/os-release").splitlines():
        if line.startswith("ID="):
            return "native-ubuntu" if line[3:].strip().strip('"\'').lower() == "ubuntu" else None
    return None


def git_output(source_root, *args):
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), *args],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def prepare_metadata(source_root, slicer_version=""):
    root = Path(source_root)
    revision = git_output(root, "rev-parse", "--short=12", "HEAD")
    if not isinstance(revision, str) or not HEX_RE.fullmatch(revision):
        revision = None
    status = git_output(root, "status", "--porcelain=v1", "--untracked-files=all")
    metadata = {
        "session_id": str(uuid.uuid4()),
        "environment": environment_label(),
        "source_checkout": safe_checkout(root.name),
        "source_revision": revision,
        "source_dirty": bool(status) if status is not None else None,
        "source_dirty_fingerprint": None,
        "slicer_version": slicer_version,
        "image_id": None,
        "native_module_identity": None,
    }
    sid, metadata = sanitized_metadata(metadata)
    return sid or str(uuid.uuid4()), metadata


def prepare_fallback_metadata(source_root):
    existing = os.environ.get("DENTOBOT_WATCHDOG_METADATA", "")
    sid, metadata = sanitized_metadata(
        existing,
        session_id=os.environ.get("DENTOBOT_WATCHDOG_SESSION_ID"),
        source_checkout=Path(source_root).name,
    )
    if sid is None:
        sid = str(uuid.uuid4())
    metadata["session_id"] = sid
    return sid, metadata


def print_metadata_pair(session_id, metadata):
    print(f"{session_id}\t{json.dumps(metadata, separators=(',', ':'))}")


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
    swap_kib = number(status.get("VmSwap", "").split(" ", 1)[0])
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
        "vm_swap_mib": round(swap_kib / 1024, 1) if swap_kib is not None else None,
        "major_faults": number(parts[7]),
        "fds": fds,
        "cpu_percent": round(100 * max(0, ticks - previous.get(pid, ticks)) / (HZ * elapsed), 1),
        "ticks": ticks,
    }


def pressure_average(text, kind, window="avg10"):
    match = re.search(rf"^{kind} .*?\b{window}=([0-9.]+)", text or "", re.MULTILINE)
    return float(match.group(1)) if match else None


def host_alerts(mem_available_kib, swap_total_kib, swap_free_kib, pressure, load_average, cpu_count):
    """Host-wide conditions that coincided with Slicer stalls; cgroup rules stay in snapshot()."""
    alerts = []
    if mem_available_kib is not None and mem_available_kib < ALERT_HOST_MEM_AVAILABLE_KIB:
        alerts.append("host_mem_available_below_2_gib")
    if swap_total_kib and swap_free_kib is not None and (
        1 - swap_free_kib / swap_total_kib >= ALERT_HOST_SWAP_USED_FRACTION
    ):
        alerts.append("host_swap_used_above_75_percent")
    memory_full = pressure_average(pressure.get("memory"), "full")
    if memory_full is not None and memory_full >= ALERT_MEMORY_PRESSURE_FULL_AVG10:
        alerts.append("host_memory_pressure_full_above_5_percent")
    io_full = pressure_average(pressure.get("io"), "full")
    if io_full is not None and io_full >= ALERT_IO_PRESSURE_FULL_AVG10:
        alerts.append("host_io_pressure_full_above_20_percent")
    cpu_some = pressure_average(pressure.get("cpu"), "some")
    if cpu_some is not None and cpu_some >= ALERT_CPU_PRESSURE_SOME_AVG10:
        alerts.append("host_cpu_pressure_some_above_80_percent")
    if load_average and load_average[0] >= ALERT_LOAD_PER_CPU * max(cpu_count, 1):
        alerts.append("host_load_above_2x_cpu_count")
    return alerts


def slicer_summary(slicer_processes):
    """The Slicer main process (largest RSS) condensed so trends need no top_processes scan."""
    if not slicer_processes:
        return None
    main = max(slicer_processes, key=lambda item: item["rss_mib"] or 0)
    return {
        "pid": main["pid"],
        "state": main["state"],
        "rss_mib": main["rss_mib"],
        "vm_swap_mib": main["vm_swap_mib"],
        "threads": main["threads"],
        "fds": main["fds"],
        "cpu_percent": main["cpu_percent"],
        "major_faults": main["major_faults"],
    }


def counter_alerts(data, counters, interval):
    """Alerts that need the counter deltas or the sampler's own timing."""
    alerts = []
    paging = counters["host_paging"]
    swap_rates = [paging.get("swap_in_bytes_per_second"), paging.get("swap_out_bytes_per_second")]
    if sum(rate for rate in swap_rates if rate is not None) >= ALERT_SWAP_BYTES_PER_SECOND:
        alerts.append("host_swapping_above_20_mib_per_second")
    if data["zombie_count"]:
        alerts.append("zombie_processes_present")
    if data["sample_gap_seconds"] > 2 * interval:
        alerts.append("sample_gap_over_twice_interval")
    return alerts


def rss_growth_alert(history, now, data):
    """Alert when the Slicer main process grew by more than 1 GiB inside two minutes."""
    slicer = data.get("slicer")
    if not slicer or slicer["rss_mib"] is None:
        history.clear()
        return []
    history.append((now, slicer["rss_mib"]))
    while history and now - history[0][0] > ALERT_SLICER_RSS_GROWTH_WINDOW_SECONDS:
        history.popleft()
    alerts = []
    if slicer["rss_mib"] >= ALERT_SLICER_RSS_MIB:
        alerts.append("slicer_rss_above_5_gib")
    if slicer["rss_mib"] - history[0][1] >= ALERT_SLICER_RSS_GROWTH_MIB:
        alerts.append("slicer_rss_growth_over_1_gib_in_2_min")
    return alerts


def derive_run_id(output_path, explicit=None):
    """Name the run so this log joins the UI watchdog's SESSION_METADATA run_id."""
    for candidate in (explicit, os.environ.get("DENTOBOT_RUN_ID")):
        if isinstance(candidate, str) and RUN_ID_RE.fullmatch(candidate):
            return candidate
    parent = Path(output_path).resolve().parent.name
    if RUN_ID_RE.fullmatch(parent) and parent not in SHARED_LOG_DIRECTORIES:
        return parent
    return None


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
    host_pressure = {kind: read(PROC / "pressure" / kind) for kind in ("cpu", "memory", "io")}
    mem_total_kib = number(mem.get("MemTotal", "").split(" ", 1)[0])
    swap_total_kib = number(mem.get("SwapTotal", "").split(" ", 1)[0])
    mem_available_kib = number(mem.get("MemAvailable", "").split(" ", 1)[0])
    swap_free_kib = number(mem.get("SwapFree", "").split(" ", 1)[0])
    load_average = tuple(round(value, 2) for value in os.getloadavg())
    slicer_processes = [item for item in processes if item["name"] in {"Slicer", "SlicerApp-real"}]
    alerts = host_alerts(
        mem_available_kib, swap_total_kib, swap_free_kib, host_pressure, load_average,
        os.cpu_count() or 1,
    )
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
        "slicer_present": bool(slicer_processes),
        "slicer": slicer_summary(slicer_processes),
        "host_mem_total_kib": mem_total_kib,
        "host_mem_available_kib": mem_available_kib,
        "host_swap_total_kib": swap_total_kib,
        "host_swap_free_kib": swap_free_kib,
        "host_load_average": load_average,
        "host_pressure": host_pressure,
        "cgroup": cgroup,
        "log_disk_free_gib": free_gib,
    }, next_ticks


def parent_alive(pid):
    """A zombie parent has already exited; its unreaped /proc entry must not keep the sampler running."""
    stat = read(PROC / str(pid) / "stat")
    tail = stat.rpartition(") ")[2].split()
    return bool(tail) and tail[0] != "Z"


def on_signal(_signum, _frame):
    global stop
    stop = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--metadata-once", action="store_true")
    parser.add_argument("--metadata-fallback", action="store_true")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--slicer-version", default="")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    if args.metadata_once or args.metadata_fallback:
        if args.source_root is None:
            parser.error("metadata mode requires --source-root")
        if args.metadata_once and args.metadata_fallback:
            parser.error("choose one metadata mode")
        pair = prepare_metadata(args.source_root, args.slicer_version) if args.metadata_once else prepare_fallback_metadata(args.source_root)
        print_metadata_pair(*pair)
        return
    if args.parent_pid is None or args.output_path is None:
        parser.error("--parent-pid and --output-path are required for sampling")
    if not 1 <= args.interval <= 60:
        parser.error("interval must be between 1 and 60 seconds")
    path = args.output_path
    path.parent.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    previous = {}
    previous_counters = {}
    previous_time = time.monotonic()
    saw_slicer = False
    session_id, metadata = sanitized_metadata(
        os.environ.get("DENTOBOT_WATCHDOG_METADATA", ""),
        session_id=os.environ.get("DENTOBOT_WATCHDOG_SESSION_ID"),
    )
    metadata_source = "launcher"
    if session_id is None:
        # Harnesses that start the sampler directly (no launcher/handoff) pass no
        # metadata; derive it from this checkout so the log is never anonymous.
        session_id, metadata = prepare_metadata(Path(__file__).resolve().parents[2])
        metadata_source = "sampler_derived"
    run_id = derive_run_id(path, args.run_id)
    rss_history = deque()
    with path.open("a", encoding="utf-8", buffering=1) as log:
        log.write(json.dumps({"event": "MONITOR_START", "utc": datetime.now(timezone.utc).isoformat(),
                              "parent_pid": args.parent_pid, "interval_seconds": args.interval,
                              "session_id": session_id, "run_id": run_id,
                              "metadata_source": metadata_source, "metadata": metadata}) + "\n")
        while not stop and parent_alive(args.parent_pid):
            now = time.monotonic()
            try:
                collection_started = time.monotonic()
                elapsed = max(now - previous_time, 0.001)
                data, previous = snapshot(previous, elapsed, path.parent)
                counters, previous_counters = resource_counters(previous_counters, elapsed)
                data.update(counters)
                data["alerts"] += counter_alerts(data, counters, args.interval)
                data["alerts"] += rss_growth_alert(rss_history, now, data)
                data["actual_collection_duration_seconds"] = round(
                    max(time.monotonic() - collection_started, 0.0), 3
                )
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
