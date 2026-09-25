"""Low-overhead UI stall evidence for normal Slicer sessions."""

import faulthandler
import atexit
import logging
import os
from pathlib import Path
import time

import qt


_watchdog = None


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
        self.phase = "Slicer UI"
        self._write("SESSION_START")
        faulthandler.enable(file=self.log, all_threads=True)
        self.timer = qt.QTimer()
        self.timer.setInterval(int(interval_seconds * 1000))
        self.timer.timeout.connect(self.tick)
        self.arm()
        self.timer.start()
        atexit.register(self.close)

    def _write(self, event, **fields):
        details = " ".join(f"{key}={value}" for key, value in fields.items())
        self.log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {event} {details}\n")

    def arm(self):
        faulthandler.cancel_dump_traceback_later()
        faulthandler.dump_traceback_later(self.stall_seconds, file=self.log)

    def tick(self):
        now = time.monotonic()
        gap = now - self.last_tick
        self.maximum_gap = max(self.maximum_gap, gap)
        self.heartbeat_count += 1
        if gap >= self.stall_seconds:
            self._write("UI_STALL_RECOVERED", gap_seconds=f"{gap:.3f}", phase=self.phase)
        elif gap >= 2:
            self._write("UI_LATENCY", gap_seconds=f"{gap:.3f}", phase=self.phase)
        if now - self.last_summary >= 60:
            self._write("UI_SUMMARY", heartbeats=self.heartbeat_count,
                        max_gap_seconds=f"{self.maximum_gap:.3f}", phase=self.phase)
            self.last_summary = now
            self.maximum_gap = 0.0
            self.heartbeat_count = 0
        self.last_tick = now
        self.arm()

    def note_phase(self, phase, done=None, total=None):
        now = time.monotonic()
        if phase != self.phase or now - self.last_phase_log >= 10:
            self.phase = phase
            self.last_phase_log = now
            self._write("WORKFLOW_PHASE", phase=phase, completed=done, total=total)

    def close(self):
        if not self.log.closed:
            self.timer.stop()
            faulthandler.cancel_dump_traceback_later()
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


def note_ui_phase(phase, done=None, total=None):
    if _watchdog is not None:
        _watchdog.note_phase(phase, done, total)
