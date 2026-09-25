"""The session watchdog records a stalled event loop and rearms once it recovers."""

import importlib.util
from pathlib import Path
import sys
import types


SOURCE = Path(__file__).resolve().parents[1] / "DENTOWorkflow/Resources/Python/dentobot_workflow/ui_stall_watchdog.py"


def test_stall_recovery_is_logged_and_timer_rearmed(tmp_path, monkeypatch):
    class Timer:
        def __init__(self):
            self.timeout = types.SimpleNamespace(connect=lambda callback: None)

        def setInterval(self, value):
            assert value == 1000

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setitem(sys.modules, "qt", types.SimpleNamespace(QTimer=Timer))
    spec = importlib.util.spec_from_file_location("testable_ui_stall_watchdog", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    clock = iter((0.0, 0.1, 6.2))
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    armed = []
    monkeypatch.setattr(module.faulthandler, "cancel_dump_traceback_later", lambda: armed.append("cancel"))
    monkeypatch.setattr(module.faulthandler, "dump_traceback_later", lambda *args, **kwargs: armed.append("arm"))
    monkeypatch.setattr(module.faulthandler, "enable", lambda **kwargs: None)
    watchdog = module.UiStallWatchdog(tmp_path)
    watchdog.note_phase("Step 6.3: MoveIt")
    watchdog.tick()
    log = Path(watchdog.log.name).read_text()
    assert "WORKFLOW_PHASE phase=Step 6.3: MoveIt" in log
    assert "UI_STALL_RECOVERED gap_seconds=6.200 phase=Step 6.3: MoveIt" in log
    assert armed == ["cancel", "arm", "cancel", "arm"]
    watchdog.close()
