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


def _fake_snapshots(module, monkeypatch, *snapshots):
    iterator = iter(snapshots)
    last = [snapshots[-1]]

    def snapshot():
        last[0] = next(iterator, last[0])
        return dict(last[0])

    monkeypatch.setattr(module, "_process_snapshot", snapshot)
    monkeypatch.setattr(module, "_host_context", lambda: {"host_swap_free_mib": 512})


def _snapshot(main_ticks, process_ticks, major_faults=0, swap_mib=100.0):
    return {
        "main_state": "S",
        "main_ticks": main_ticks,
        "process_ticks": process_ticks,
        "major_faults": major_faults,
        "rss_mib": 2000.0,
        "swap_mib": swap_mib,
        "threads": 90,
    }


def test_stall_records_cpu_fraction_paging_and_host_context(tmp_path, monkeypatch):
    module, timers = load_watchdog(monkeypatch)
    ticks = module._CLOCK_TICKS
    # baseline at construction, then the snapshot taken when the stall is reported
    _fake_snapshots(
        module, monkeypatch,
        _snapshot(0, 0), _snapshot(int(0.3 * ticks), int(1.0 * ticks), major_faults=40),
        _snapshot(int(0.3 * ticks), int(1.0 * ticks), major_faults=40),
    )
    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    watchdog = module.UiStallWatchdog(tmp_path)
    clock[0] = 6.0
    timers[0].callback()
    line = next(l for l in Path(watchdog.log.name).read_text().splitlines() if "UI_STALL_RECOVERED" in l)
    assert "gap_seconds=6.000 phase=Idle" in line
    assert "main_cpu_seconds=0.30 main_cpu_fraction=0.05 blocked_hint=waiting" in line
    assert "major_faults_delta=40" in line
    assert "swap_mib=100.0" in line and "host_swap_free_mib=512" in line
    watchdog.close()


def test_cpu_bound_gap_is_hinted_as_cpu_bound(tmp_path, monkeypatch):
    module, timers = load_watchdog(monkeypatch)
    ticks = module._CLOCK_TICKS
    _fake_snapshots(module, monkeypatch, _snapshot(0, 0), _snapshot(int(5.5 * ticks), int(6 * ticks)))
    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    watchdog = module.UiStallWatchdog(tmp_path)
    clock[0] = 6.0
    timers[0].callback()
    assert "blocked_hint=cpu_bound" in Path(watchdog.log.name).read_text()
    watchdog.close()


def test_action_end_reports_stalls_and_timed_waits(tmp_path, monkeypatch):
    module, timers = load_watchdog(monkeypatch)
    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(module, "_process_snapshot", lambda: None)
    monkeypatch.setattr(module, "_host_context", lambda: {})
    watchdog = module.UiStallWatchdog(tmp_path)
    monkeypatch.setattr(module, "_watchdog", watchdog)
    token = watchdog.begin_action("Guarded approach")
    clock[0] = 6.2
    timers[0].callback()
    with module.ui_wait("task_command_result", "approach") as scope:
        clock[0] = 8.0
        scope.outcome = "timeout"
    with module.ui_wait("task_command_result", "approach"):
        clock[0] = 8.2
    assert watchdog.end_action(token, "success")
    log = Path(watchdog.log.name).read_text()
    wait_lines = [l for l in log.splitlines() if " UI_WAIT " in l]
    assert len(wait_lines) == 1  # the 0.2 s ok wait stays below the logging floor
    assert 'kind=task_command_result label="approach" duration_seconds=1.800 outcome=timeout' in wait_lines[0]
    end = next(l for l in log.splitlines() if " ACTION_END " in l)
    assert "max_gap_seconds=6.200 stalls=1 stalled_seconds=6.200" in end
    assert "waits=2 wait_seconds=2.000 wait_max_seconds=1.800 wait_timeouts=1" in end
    watchdog.close()
    assert "SESSION_END stalls=1 stalled_seconds=6.200 max_gap_seconds=6.200 waits=2" in (
        Path(watchdog.log.name).read_text()
    )


def test_ui_wait_is_inert_without_an_installed_watchdog(monkeypatch):
    module, _ = load_watchdog(monkeypatch)
    monkeypatch.setattr(module, "_watchdog", None)
    with module.ui_wait("task_command_result", "x") as scope:
        scope.outcome = "timeout"
    with pytest.raises(ValueError):
        with module.ui_wait("task_command_result", "x"):
            raise ValueError("propagates")


def test_active_stall_is_reported_while_it_is_still_running(tmp_path, monkeypatch):
    import time as real_time

    module, timers = load_watchdog(monkeypatch)
    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(module, "_process_snapshot", lambda: None)
    monkeypatch.setattr(module, "_host_context", lambda: {})
    watchdog = module.UiStallWatchdog(tmp_path, active_stall_reports=True, active_check_seconds=0.01)
    watchdog.note_phase("Guarded approach")

    def wait_for(text):
        deadline = real_time.time() + 3
        while real_time.time() < deadline:
            if text in Path(watchdog.log.name).read_text():
                return
            real_time.sleep(0.01)
        raise AssertionError(f"{text!r} not logged:\n{Path(watchdog.log.name).read_text()}")

    clock[0] = 7.0
    wait_for("UI_STALL_ACTIVE gap_so_far_seconds=7.0 phase=Guarded approach")
    clock[0] = 40.0
    wait_for("UI_STALL_ONGOING gap_so_far_seconds=40.0")
    log = Path(watchdog.log.name).read_text()
    assert log.count("UI_STALL_ACTIVE") == 1
    timers[0].callback()
    assert "UI_STALL_RECOVERED gap_seconds=40.000" in Path(watchdog.log.name).read_text()
    watchdog.close()
    assert not watchdog._active_thread.is_alive()
    watchdog.close()


def test_run_id_and_graphics_environment_are_recorded(tmp_path, monkeypatch):
    module, _ = load_watchdog(monkeypatch)
    monkeypatch.delenv("DENTOBOT_RUN_ID", raising=False)
    monkeypatch.setenv("DENTOBOT_HEADED_EVIDENCE_DIR", "/data/dentobot-runs/s6-live-01-r16/evidence")
    monkeypatch.setenv("LIBGL_ALWAYS_SOFTWARE", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "/not/a/safe/value")
    metadata = module._session_metadata()
    assert metadata["run_id"] == "s6-live-01-r16"
    assert metadata["graphics_environment"]["LIBGL_ALWAYS_SOFTWARE"] == "1"
    assert metadata["graphics_environment"]["QT_QPA_PLATFORM"] is None
    monkeypatch.setenv("DENTOBOT_RUN_ID", "explicit-run.1")
    assert module._session_metadata()["run_id"] == "explicit-run.1"
    monkeypatch.setenv("DENTOBOT_RUN_ID", "bad/value")
    assert module._session_metadata()["run_id"] == "s6-live-01-r16"


@pytest.mark.skipif(not Path("/proc/self/task").exists(), reason="Linux /proc only")
def test_process_snapshot_reads_the_live_process(monkeypatch):
    module, _ = load_watchdog(monkeypatch)
    snapshot = module._process_snapshot()
    assert snapshot["main_state"] in set("RSDTtZXIPW")
    assert snapshot["rss_mib"] > 0 and snapshot["threads"] >= 1
    assert snapshot["major_faults"] >= 0
