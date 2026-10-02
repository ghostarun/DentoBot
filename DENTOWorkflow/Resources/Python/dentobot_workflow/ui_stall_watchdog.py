"""Qt logs UI stalls with cause hints; use external GDB for hard hangs and native stacks.

Beyond the 1 s Qt heartbeat this module records, without tracebacks or any Qt/MRML
access from a second thread: what the main thread was doing during a gap (CPU
fraction, paging, swap, host pressure), stalls still in progress, per-action
stall/wait totals, and timed synchronous waits (ROS round trips) via ``ui_wait``.
"""

import atexit
import contextlib
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
import threading
import time
import uuid

import qt


_watchdog = None
_CLOCK_TICKS = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
_ACTIVE_REPORT_REPEAT_SECONDS = 30
_WAIT_LOG_SECONDS = 1.0
_WAIT_LOG_LINE_LIMIT = 500
_GRAPHICS_ENVIRONMENT = (
    "LIBGL_ALWAYS_SOFTWARE", "GALLIUM_DRIVER", "MESA_LOADER_DRIVER_OVERRIDE",
    "QT_QPA_PLATFORM", "__GLX_VENDOR_LIBRARY_NAME",
)
_PROCESS_SESSION_ID = str(uuid.uuid4())
_UNKNOWN_METADATA = {
    "environment": None,
    "source_checkout": None,
    "source_revision": None,
    "source_dirty": None,
    "source_dirty_fingerprint": None,
    "slicer_version": None,
    "image_id": None,
    "native_module_identity": None,
}


def _safe_string(value, pattern, max_length):
    if not isinstance(value, str) or len(value) > max_length:
        return None
    if not re.fullmatch(pattern, value) or "/" in value or "\\" in value:
        return None
    return value


def _safe_session_id(value):
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError):
        return None


def _single_line(value):
    return str(value).replace("\r", r"\r").replace("\n", r"\n")


def _read_text(path):
    try:
        return Path(path).read_text()
    except (OSError, UnicodeError):
        return ""


def _stat_tail(text):
    """Fields after the command name in /proc/<pid>/stat, or None."""
    _, separator, tail = text.rpartition(") ")
    parts = tail.split()
    return parts if separator and len(parts) >= 22 else None


def _kib(status, key):
    match = re.search(rf"^{key}:\s+(\d+)\s+kB", status, re.MULTILINE)
    return int(match.group(1)) if match else None


def _process_snapshot():
    """Cheap Linux view of this process and its main thread; None without /proc."""
    try:
        pid = os.getpid()
        main = _stat_tail(_read_text(f"/proc/self/task/{pid}/stat"))
        process = _stat_tail(_read_text("/proc/self/stat"))
        if main is None or process is None:
            return None
        status = _read_text("/proc/self/status")
        rss_kib = _kib(status, "VmRSS")
        swap_kib = _kib(status, "VmSwap")
        threads = re.search(r"^Threads:\s+(\d+)", status, re.MULTILINE)
        return {
            "main_state": main[0],
            "main_ticks": int(main[11]) + int(main[12]),
            "process_ticks": int(process[11]) + int(process[12]),
            "major_faults": int(process[7]),
            "rss_mib": round(rss_kib / 1024, 1) if rss_kib is not None else None,
            "swap_mib": round(swap_kib / 1024, 1) if swap_kib is not None else None,
            "threads": int(threads.group(1)) if threads else None,
        }
    except (OSError, ValueError, IndexError):
        return None


def _host_context():
    """Host memory and pressure at the moment a stall is reported."""
    meminfo = _read_text("/proc/meminfo")
    result = {}
    available = _kib(meminfo, "MemAvailable")
    swap_free = _kib(meminfo, "SwapFree")
    if available is not None:
        result["host_mem_available_mib"] = round(available / 1024)
    if swap_free is not None:
        result["host_swap_free_mib"] = round(swap_free / 1024)
    for kind, label in (("memory", "host_psi_mem_full_avg10"), ("io", "host_psi_io_full_avg10")):
        match = re.search(r"^full .*?avg10=([0-9.]+)", _read_text(f"/proc/pressure/{kind}"), re.MULTILINE)
        if match:
            result[label] = match.group(1)
    return result


def _run_id():
    explicit = os.environ.get("DENTOBOT_RUN_ID")
    if _safe_string(explicit, r"[A-Za-z0-9._-]{1,128}", 128):
        return explicit
    evidence = os.environ.get("DENTOBOT_HEADED_EVIDENCE_DIR")
    if evidence and Path(evidence).name == "evidence":
        return _safe_string(Path(evidence).parent.name, r"[A-Za-z0-9._-]{1,128}", 128)
    return None


def _graphics_environment():
    return {
        name: _safe_string(os.environ.get(name), r"[A-Za-z0-9_.:,+-]{1,64}", 64)
        for name in _GRAPHICS_ENVIRONMENT
        if os.environ.get(name) is not None
    }


def _slicer_version():
    try:
        module = sys.modules.get("slicer")
        app = getattr(module, "app", None)
        version = getattr(app, "applicationVersion", None)
        return _safe_string(version, r"[0-9]+(?:\.[0-9A-Za-z]+){1,5}", 32)
    except (AttributeError, RuntimeError, TypeError):
        return None


def _session_metadata():
    try:
        raw = os.environ.get("DENTOBOT_WATCHDOG_METADATA", "")
        metadata = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}

    session_id = _safe_session_id(os.environ.get("DENTOBOT_WATCHDOG_SESSION_ID"))
    if session_id is None:
        session_id = _safe_session_id(metadata.get("session_id"))
    if session_id is None:
        session_id = _PROCESS_SESSION_ID

    result = {"session_id": session_id, **_UNKNOWN_METADATA}
    environment = _safe_string(
        metadata.get("environment"), r"[A-Za-z0-9_.:+-]{1,64}", 64
    )
    result["environment"] = environment if environment in {
        "native-ubuntu", "ubuntu", "ubuntu-container", "docker", "container", "wsl", "wsl2"
    } else None
    launcher_checkout = _safe_string(
        metadata.get("source_checkout"), r"[A-Za-z0-9._-]{1,96}", 96
    )
    if launcher_checkout in {".", ".."}:
        launcher_checkout = None
    result["source_revision"] = _safe_string(
        metadata.get("source_revision"), r"[0-9a-fA-F]{7,64}", 64
    )
    dirty = metadata.get("source_dirty")
    result["source_dirty"] = dirty if isinstance(dirty, bool) else None
    result["source_dirty_fingerprint"] = _safe_string(
        metadata.get("source_dirty_fingerprint"), r"[0-9a-fA-F]{64}", 64
    )
    result["slicer_version"] = _slicer_version()
    result["image_id"] = _safe_string(
        metadata.get("image_id"), r"(?:sha256:)?[0-9a-fA-F]{64}", 71
    )
    result["native_module_identity"] = _safe_string(
        metadata.get("native_module_identity"), r"DENTORobotSimulation(?::[A-Za-z0-9_.+-]{1,96})?", 128
    )

    try:
        actual_checkout = Path(__file__).resolve().parents[4].name
    except (OSError, IndexError, RuntimeError):
        actual_checkout = None
    actual_checkout = _safe_string(actual_checkout, r"[A-Za-z0-9._-]{1,96}", 96)
    try:
        source_file_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except OSError:
        source_file_sha256 = None
    result["actual_checkout"] = actual_checkout
    result["source_file_sha256"] = source_file_sha256
    result["source_checkout"] = (
        launcher_checkout if actual_checkout and launcher_checkout == actual_checkout else None
    )
    result["launcher_checkout_match"] = (
        "unknown" if not actual_checkout or not launcher_checkout else
        "match" if actual_checkout == result["source_checkout"] else "mismatch"
    )
    result["source_revision_provenance"] = (
        "launcher_reported" if result["source_revision"] else None
    )
    result["run_id"] = _run_id()
    result["graphics_environment"] = _graphics_environment()
    result["cpu_count"] = os.cpu_count()
    return result


class UiStallWatchdog:
    def __init__(self, directory=None, interval_seconds=1, stall_seconds=5, active_stall_reports=False,
                 active_check_seconds=1.0):
        root = Path(directory or os.environ.get("DENTOBOT_UI_WATCHDOG_DIR") or
                    Path(os.environ.get("DENTOBOT_RUN_ARTIFACT_ROOT", "/workspace/data/dentobot-runs")) /
                    "ui-watchdog")
        root.mkdir(parents=True, exist_ok=True)
        self.log = (root / f"slicer-ui-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.log").open(
            "a", encoding="utf-8", buffering=1
        )
        self.stall_seconds = stall_seconds
        self.last_tick = time.monotonic()
        self.last_summary = self.last_tick
        self.maximum_gap = 0.0
        self.heartbeat_count = 0
        self.last_phase_log = 0.0
        self.phase = "Idle"
        self.actions = []
        self.closed = False
        self.total_stalls = 0
        self.total_stalled_seconds = 0.0
        self.session_max_gap = 0.0
        self.total_waits = 0
        self.total_wait_seconds = 0.0
        self.wait_log_lines = 0
        self.peak_rss_mib = 0.0
        self.peak_swap_mib = 0.0
        self._baseline = _process_snapshot()
        self._write_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._active_thread = None
        self._active_check_seconds = active_check_seconds
        self._write("SESSION_START")
        self._write("SESSION_METADATA", metadata=json.dumps(
            _session_metadata(), sort_keys=True, separators=(",", ":")
        ))
        self.timer = qt.QTimer()
        self.timer.setInterval(int(interval_seconds * 1000))
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        if active_stall_reports:
            self._active_thread = threading.Thread(
                target=self._watch_active_stalls, name="DentobotUiStallWatch", daemon=True
            )
            self._active_thread.start()
        atexit.register(self.close)

    def _write(self, event, **fields):
        details = " ".join(f"{key}={_single_line(value)}" for key, value in fields.items())
        with self._write_lock:
            if not self.log.closed:
                self.log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {event} {details}\n")

    def _gap_context(self, gap):
        """What the main thread was doing during a gap; hints, not proof of cause."""
        context = {}
        snapshot = _process_snapshot()
        baseline = self._baseline
        if snapshot is not None and baseline is not None and gap > 0:
            main_cpu = max(0, snapshot["main_ticks"] - baseline["main_ticks"]) / _CLOCK_TICKS
            fraction = min(main_cpu / gap, 1.0)
            context["main_cpu_seconds"] = f"{main_cpu:.2f}"
            context["main_cpu_fraction"] = f"{fraction:.2f}"
            context["blocked_hint"] = (
                "cpu_bound" if fraction >= 0.7 else "waiting" if fraction < 0.2 else "mixed"
            )
            context["main_state"] = snapshot["main_state"]
            process_cpu = max(0, snapshot["process_ticks"] - baseline["process_ticks"]) / _CLOCK_TICKS
            context["process_cpu_seconds"] = f"{process_cpu:.2f}"
            context["major_faults_delta"] = max(0, snapshot["major_faults"] - baseline["major_faults"])
            for key in ("rss_mib", "swap_mib", "threads"):
                if snapshot[key] is not None:
                    context[key] = snapshot[key]
        context.update(_host_context())
        return context

    def _watch_active_stalls(self):
        """Report a stall while it is still running; no traceback, no Qt/MRML access.

        A native call that holds the GIL also silences this thread; hard hangs
        still need the external GDB capture.
        """
        reported_tick = None
        next_report = 0.0
        while not self._stop_event.wait(self._active_check_seconds):
            try:
                tick = self.last_tick
                gap = time.monotonic() - tick
                if gap < self.stall_seconds:
                    reported_tick = None
                    continue
                if reported_tick != tick:
                    event = "UI_STALL_ACTIVE"
                    reported_tick = tick
                    next_report = gap + _ACTIVE_REPORT_REPEAT_SECONDS
                elif gap >= next_report:
                    event = "UI_STALL_ONGOING"
                    next_report = gap + _ACTIVE_REPORT_REPEAT_SECONDS
                else:
                    continue
                fields = {"gap_so_far_seconds": f"{gap:.1f}", "phase": self.phase}
                if self.actions:
                    fields["token"] = self.actions[-1]["token"]
                fields.update(self._gap_context(gap))
                self._write(event, **fields)
            except Exception:  # a monitor must never raise into the application
                continue

    def _record_gap(self, now, *, count_heartbeat):
        gap = now - self.last_tick
        self.maximum_gap = max(self.maximum_gap, gap)
        self.session_max_gap = max(self.session_max_gap, gap)
        if count_heartbeat:
            self.heartbeat_count += 1
        fields = {"gap_seconds": f"{gap:.3f}", "phase": self.phase}
        if self.actions:
            fields["token"] = self.actions[-1]["token"]
        if gap >= 2:
            fields.update(self._gap_context(gap))
            stalled = gap >= self.stall_seconds
            if stalled:
                self.total_stalls += 1
                self.total_stalled_seconds += gap
            for action in self.actions:
                action["max_gap"] = max(action["max_gap"], gap)
                if stalled:
                    action["stalls"] += 1
                    action["stalled_seconds"] += gap
            self._write("UI_STALL_RECOVERED" if stalled else "UI_LATENCY", **fields)
        if now - self.last_summary >= 60:
            summary = {
                "heartbeats": self.heartbeat_count,
                "max_gap_seconds": f"{self.maximum_gap:.3f}",
                "phase": self.phase,
            }
            if self.actions:
                summary["token"] = self.actions[-1]["token"]
            snapshot = _process_snapshot()
            if snapshot is not None:
                for key in ("rss_mib", "swap_mib", "threads"):
                    if snapshot[key] is not None:
                        summary[key] = snapshot[key]
                self.peak_rss_mib = max(self.peak_rss_mib, snapshot["rss_mib"] or 0.0)
                self.peak_swap_mib = max(self.peak_swap_mib, snapshot["swap_mib"] or 0.0)
                try:
                    summary["fds"] = len(os.listdir("/proc/self/fd"))
                except OSError:
                    pass
            self._write("UI_SUMMARY", **summary)
            self.last_summary = now
            self.maximum_gap = 0.0
            self.heartbeat_count = 0
        self.last_tick = now
        self._baseline = _process_snapshot()
        return gap

    def tick(self):
        if not self.closed:
            self._record_gap(time.monotonic(), count_heartbeat=True)

    def begin_action(self, title):
        if self.closed:
            return None
        now = time.monotonic()
        token = str(uuid.uuid4())
        title = str(title)
        previous_phase = self.phase
        self.actions.append({
            "token": token,
            "title": title,
            "started": now,
            "phase": title,
            "last_phase_log": now,
            "max_gap": 0.0,
            "stalls": 0,
            "stalled_seconds": 0.0,
            "waits": 0,
            "wait_seconds": 0.0,
            "wait_max": 0.0,
            "wait_timeouts": 0,
        })
        self.phase = title
        try:
            self._write("ACTION_START", token=token, title=json.dumps(title, ensure_ascii=True))
        except Exception:
            self.actions.pop()
            self.phase = previous_phase
            raise
        return token

    def note_phase(self, phase, done=None, total=None, token=None):
        if self.closed:
            return False
        action = next((item for item in self.actions if item["token"] == token), None) if token else (
            self.actions[-1] if self.actions else None
        )
        if token and action is None:
            return False
        now = time.monotonic()
        old_phase = action["phase"] if action else self.phase
        phase = str(phase)
        if action:
            action["phase"] = phase
            if action is not self.actions[-1]:
                return True
            self.phase = phase
            last_logged = action["last_phase_log"]
        else:
            self.phase = phase
            last_logged = self.last_phase_log
        if phase != old_phase or now - last_logged >= 10:
            if action:
                action["last_phase_log"] = now
                fields = {"phase": phase, "token": action["token"]}
            else:
                self.last_phase_log = now
                fields = {"phase": phase}
            if done is not None:
                fields["completed"] = done
            if total is not None:
                fields["total"] = total
            self._write("WORKFLOW_PHASE", **fields)
        return True

    def note_wait(self, kind, label, duration, outcome="ok"):
        """Account a synchronous wait on the UI thread (for example a ROS round trip)."""
        if self.closed:
            return
        duration = max(0.0, float(duration))
        self.total_waits += 1
        self.total_wait_seconds += duration
        for action in self.actions:
            action["waits"] += 1
            action["wait_seconds"] += duration
            action["wait_max"] = max(action["wait_max"], duration)
            action["wait_timeouts"] += outcome == "timeout"
        if (duration >= _WAIT_LOG_SECONDS or outcome != "ok") and self.wait_log_lines < _WAIT_LOG_LINE_LIMIT:
            self.wait_log_lines += 1
            fields = {
                "kind": kind,
                "label": json.dumps(str(label), ensure_ascii=True),
                "duration_seconds": f"{duration:.3f}",
                "outcome": outcome,
                "phase": self.phase,
            }
            if self.actions:
                fields["token"] = self.actions[-1]["token"]
            self._write("UI_WAIT", **fields)

    def end_action(self, token, outcome="closed"):
        if self.closed or not token:
            return False
        index = next((i for i, item in enumerate(self.actions) if item["token"] == token), None)
        if index is None:
            return False
        now = time.monotonic()
        if now - self.last_tick >= 2:
            self._record_gap(now, count_heartbeat=False)
        action = self.actions.pop(index)
        if not isinstance(outcome, str) or outcome not in {
            "closed", "success", "error", "cancelled"
        }:
            outcome = "unknown"
        active = self.actions[-1] if self.actions else None
        self.phase = active["phase"] if active else "Idle"
        self._write(
            "ACTION_END",
            token=action["token"],
            title=json.dumps(action["title"], ensure_ascii=True),
            duration_seconds=f"{max(0.0, now - action['started']):.3f}",
            outcome=outcome,
            max_gap_seconds=f"{action['max_gap']:.3f}",
            stalls=action["stalls"],
            stalled_seconds=f"{action['stalled_seconds']:.3f}",
            waits=action["waits"],
            wait_seconds=f"{action['wait_seconds']:.3f}",
            wait_max_seconds=f"{action['wait_max']:.3f}",
            wait_timeouts=action["wait_timeouts"],
        )
        fields = {"phase": self.phase, "token": active["token"] if active else "none"}
        self._write("WORKFLOW_PHASE", **fields)
        return True

    def close(self):
        if not self.log.closed:
            self.closed = True
            self._stop_event.set()
            self.timer.stop()
            thread = self._active_thread
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=2)
            self._write(
                "SESSION_END",
                stalls=self.total_stalls,
                stalled_seconds=f"{self.total_stalled_seconds:.3f}",
                max_gap_seconds=f"{self.session_max_gap:.3f}",
                waits=self.total_waits,
                wait_seconds=f"{self.total_wait_seconds:.3f}",
                peak_rss_mib=self.peak_rss_mib,
                peak_swap_mib=self.peak_swap_mib,
            )
            with self._write_lock:
                self.log.close()


def install_ui_stall_watchdog():
    global _watchdog
    if os.environ.get("DENTOBOT_UI_WATCHDOG_DISABLE") == "1":
        return None
    if _watchdog is None:
        try:
            _watchdog = UiStallWatchdog(
                active_stall_reports=os.environ.get("DENTOBOT_UI_WATCHDOG_ACTIVE") != "0"
            )
            logging.info("DENTOBOT UI stall log: %s", _watchdog.log.name)
        except (OSError, RuntimeError) as exc:
            logging.warning("DENTOBOT UI stall watchdog unavailable: %s", exc)
    return _watchdog


def begin_ui_action(title):
    return _watchdog.begin_action(title) if _watchdog is not None else None


def end_ui_action(token, outcome="closed"):
    if _watchdog is not None and token is not None:
        _watchdog.end_action(token, outcome)


def note_ui_phase(phase, done=None, total=None, token=None):
    if _watchdog is not None:
        _watchdog.note_phase(phase, done, total, token)


class _WaitScope:
    outcome = "ok"


@contextlib.contextmanager
def ui_wait(kind, label=""):
    """Time a synchronous UI-thread wait; set ``scope.outcome = "timeout"`` when it expires."""
    watchdog = _watchdog
    scope = _WaitScope()
    started = time.monotonic() if watchdog is not None else 0.0
    try:
        yield scope
    except BaseException:
        scope.outcome = "error"
        raise
    finally:
        if watchdog is not None:
            watchdog.note_wait(kind, label, time.monotonic() - started, scope.outcome)
