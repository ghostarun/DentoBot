"""Qt logs recovered UI stalls; use external GDB for hard hangs and native stacks."""

import atexit
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
import uuid

import qt


_watchdog = None
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
    return result


class UiStallWatchdog:
    def __init__(self, directory=None, interval_seconds=1, stall_seconds=5):
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
        self._write("SESSION_START")
        self._write("SESSION_METADATA", metadata=json.dumps(
            _session_metadata(), sort_keys=True, separators=(",", ":")
        ))
        self.timer = qt.QTimer()
        self.timer.setInterval(int(interval_seconds * 1000))
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        atexit.register(self.close)

    def _write(self, event, **fields):
        details = " ".join(f"{key}={_single_line(value)}" for key, value in fields.items())
        self.log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {event} {details}\n")

    def _record_gap(self, now, *, count_heartbeat):
        gap = now - self.last_tick
        self.maximum_gap = max(self.maximum_gap, gap)
        if count_heartbeat:
            self.heartbeat_count += 1
        fields = {"gap_seconds": f"{gap:.3f}", "phase": self.phase}
        if self.actions:
            fields["token"] = self.actions[-1]["token"]
        if gap >= self.stall_seconds:
            self._write("UI_STALL_RECOVERED", **fields)
        elif gap >= 2:
            self._write("UI_LATENCY", **fields)
        if now - self.last_summary >= 60:
            summary = {
                "heartbeats": self.heartbeat_count,
                "max_gap_seconds": f"{self.maximum_gap:.3f}",
                "phase": self.phase,
            }
            if self.actions:
                summary["token"] = self.actions[-1]["token"]
            self._write("UI_SUMMARY", **summary)
            self.last_summary = now
            self.maximum_gap = 0.0
            self.heartbeat_count = 0
        self.last_tick = now
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
        )
        fields = {"phase": self.phase, "token": active["token"] if active else "none"}
        self._write("WORKFLOW_PHASE", **fields)
        return True

    def close(self):
        if not self.log.closed:
            self.closed = True
            self.timer.stop()
            self._write("SESSION_END")
            self.log.close()


def install_ui_stall_watchdog():
    global _watchdog
    if os.environ.get("DENTOBOT_UI_WATCHDOG_DISABLE") == "1":
        return None
    if _watchdog is None:
        try:
            _watchdog = UiStallWatchdog()
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
