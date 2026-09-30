"""The session watchdog records a stalled event loop and rearms once it recovers."""

import importlib.util
from pathlib import Path
import sys
import types

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "DENTOWorkflow/Resources/Python/dentobot_workflow/ui_stall_watchdog.py"


def test_stall_recovery_is_logged_without_faulthandler_and_close_is_idempotent(
    tmp_path, monkeypatch
):
    timers = []

    class Timer:
        def __init__(self):
            self.start_calls = 0
            self.stop_calls = 0
            self.callback = None
            self.timeout = types.SimpleNamespace(connect=self.connect)
            timers.append(self)

        def connect(self, callback):
            self.callback = callback

        def setInterval(self, value):
            assert value == 1000

        def start(self):
            self.start_calls += 1

        def stop(self):
            self.stop_calls += 1

    def forbidden_faulthandler_call(*_args, **_kwargs):
        pytest.fail("the UI watchdog must not call faulthandler")

    fake_faulthandler = types.ModuleType("faulthandler")
    fake_faulthandler.enable = forbidden_faulthandler_call
    fake_faulthandler.cancel_dump_traceback_later = forbidden_faulthandler_call
    fake_faulthandler.dump_traceback_later = forbidden_faulthandler_call

    monkeypatch.setitem(sys.modules, "qt", types.SimpleNamespace(QTimer=Timer))
    monkeypatch.setitem(sys.modules, "faulthandler", fake_faulthandler)
    spec = importlib.util.spec_from_file_location("testable_ui_stall_watchdog", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    clock = iter((0.0, 0.1, 6.2, 60.2))
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    watchdog = module.UiStallWatchdog(tmp_path)
    watchdog.note_phase("Step 6.3: MoveIt")
    timer = timers[0]
    assert timer.callback is not None
    timer.callback()
    timer.callback()
    log = Path(watchdog.log.name).read_text()
    assert "WORKFLOW_PHASE phase=Step 6.3: MoveIt" in log
    assert "UI_STALL_RECOVERED gap_seconds=6.200 phase=Step 6.3: MoveIt" in log
    assert "UI_SUMMARY heartbeats=2 max_gap_seconds=54.000 phase=Step 6.3: MoveIt" in log
    assert timer.start_calls == 1
    watchdog.close()
    watchdog.close()
    closed_log = Path(watchdog.log.name).read_text()
    assert closed_log.count("SESSION_END") == 1
    assert timer.stop_calls == 1
    assert watchdog.log.closed
