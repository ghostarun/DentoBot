"""The session watchdog attributes recovered UI gaps without scheduled traceback dumping."""

import importlib.util
import json
from pathlib import Path
import sys
import types
import uuid

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "DENTOWorkflow/Resources/Python/dentobot_workflow/ui_stall_watchdog.py"


def load_watchdog(monkeypatch):
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
    return module, timers


def test_stall_recovery_is_logged_without_faulthandler_and_close_is_idempotent(
    tmp_path, monkeypatch
):
    module, timers = load_watchdog(monkeypatch)
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


def test_nested_and_out_of_order_actions_restore_the_live_phase(tmp_path, monkeypatch):
    module, _ = load_watchdog(monkeypatch)
    monkeypatch.setattr(module.time, "monotonic", lambda: 0.0)
    watchdog = module.UiStallWatchdog(tmp_path)
    outer = watchdog.begin_action("Outer")
    watchdog.note_phase("Outer phase", token=outer)
    middle = watchdog.begin_action("Middle")
    leaf = watchdog.begin_action("Leaf")
    watchdog.note_phase("Leaf phase", token=leaf)

    assert watchdog.end_action(middle)
    assert watchdog.phase == "Leaf phase"
    assert watchdog.end_action(leaf)
    assert watchdog.phase == "Outer phase"
    assert watchdog.end_action(outer)
    assert watchdog.phase == "Idle"
    assert not watchdog.end_action(outer)
    assert not watchdog.note_phase("stale", token=outer)

    log = Path(watchdog.log.name).read_text()
    assert log.count("ACTION_START") == 3
    assert log.count("ACTION_END") == 3
    assert "WORKFLOW_PHASE phase=Outer phase" in log
    assert 'title="Middle"' in log
    watchdog.close()


def test_closing_action_captures_unreported_blocking_gap_before_idle(tmp_path, monkeypatch):
    module, timers = load_watchdog(monkeypatch)
    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    watchdog = module.UiStallWatchdog(tmp_path)
    token = watchdog.begin_action("Blocking operation")
    clock[0] = 6.2
    assert watchdog.end_action(token)
    assert watchdog.phase == "Idle"
    timers[0].callback()
    log = Path(watchdog.log.name).read_text()
    assert "UI_STALL_RECOVERED gap_seconds=6.200 phase=Blocking operation token=" + token in log
    assert log.count("UI_STALL_RECOVERED") == 1
    assert "ACTION_END token=" + token in log
    watchdog.close()


def test_session_metadata_is_single_line_whitelisted_and_validated(tmp_path, monkeypatch):
    module, _ = load_watchdog(monkeypatch)
    session_id = str(uuid.uuid4())
    checkout = SOURCE.resolve().parents[4].name
    metadata = {
        "session_id": str(uuid.uuid4()),
        "environment": "native-ubuntu",
        "source_checkout": checkout,
        "source_revision": "a" * 40,
        "source_dirty": True,
        "source_dirty_fingerprint": "b" * 64,
        "slicer_version": "99.99.99",
        "image_id": "sha256:" + "c" * 64,
        "native_module_identity": "DENTORobotSimulation:1.0",
        "patient_name": "Sensitive Person",
        "output_path": "/home/sensitive/private",
    }
    monkeypatch.setenv("DENTOBOT_WATCHDOG_SESSION_ID", session_id)
    monkeypatch.setenv("DENTOBOT_WATCHDOG_METADATA", json.dumps(metadata))
    monkeypatch.setitem(
        sys.modules, "slicer", types.SimpleNamespace(app=types.SimpleNamespace(applicationVersion="5.10.0"))
    )
    watchdog = module.UiStallWatchdog(tmp_path)
    lines = Path(watchdog.log.name).read_text().splitlines()
    metadata_lines = [line for line in lines if " SESSION_METADATA " in line]
    assert len(metadata_lines) == 1
    payload = json.loads(metadata_lines[0].split(" metadata=", 1)[1])
    assert payload["session_id"] == session_id
    assert payload["environment"] == "native-ubuntu"
    assert payload["source_checkout"] == checkout
    assert payload["actual_checkout"] == checkout
    assert payload["launcher_checkout_match"] == "match"
    assert payload["source_revision"] == "a" * 40
    assert payload["source_revision_provenance"] == "launcher_reported"
    assert payload["source_dirty"] is True
    assert payload["slicer_version"] == "5.10.0"
    assert payload["image_id"] == "sha256:" + "c" * 64
    assert len(payload["source_file_sha256"]) == 64
    assert "Sensitive Person" not in metadata_lines[0]
    assert "/home/sensitive/private" not in metadata_lines[0]
    assert "patient_name" not in metadata_lines[0]
    watchdog.close()


@pytest.mark.parametrize("raw_metadata", ("{bad json", "[]"))
def test_malformed_or_non_dictionary_metadata_stays_unknown(tmp_path, monkeypatch, raw_metadata):
    module, _ = load_watchdog(monkeypatch)
    monkeypatch.setenv("DENTOBOT_WATCHDOG_SESSION_ID", "patient-name")
    monkeypatch.setenv("DENTOBOT_WATCHDOG_METADATA", raw_metadata)
    monkeypatch.delitem(sys.modules, "slicer", raising=False)
    watchdog = module.UiStallWatchdog(tmp_path)
    line = next(
        item for item in Path(watchdog.log.name).read_text().splitlines()
        if " SESSION_METADATA " in item
    )
    payload = json.loads(line.split(" metadata=", 1)[1])
    assert payload["session_id"] != "patient-name"
    assert len(payload["session_id"]) == 36
    assert payload["source_checkout"] is None
    assert payload["source_revision"] is None
    assert payload["source_dirty"] is None
    assert payload["slicer_version"] is None
    assert payload["launcher_checkout_match"] == "unknown"
    assert "bad json" not in line
    watchdog.close()
