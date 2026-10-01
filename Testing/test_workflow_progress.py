"""Truthful WorkflowProgress lifecycle checks with fake Qt and Slicer APIs."""

import importlib.util
from pathlib import Path
import sys
import types

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "DENTOWorkflow/Resources/Python/dentobot_workflow/workflow_progress.py"


def load_progress(monkeypatch, *, fail_at=None):
    calls = []
    dialogs = []
    package = types.ModuleType("dentobot_workflow")
    package.__path__ = [str(SOURCE.parent)]
    watchdog = types.ModuleType("dentobot_workflow.ui_stall_watchdog")

    def begin(title):
        token = f"action-{len([call for call in calls if call[0] == 'begin']) + 1}"
        calls.append(("begin", title, token))
        return token

    watchdog.begin_ui_action = begin
    watchdog.end_ui_action = lambda token, outcome="closed": calls.append(
        ("end", token, outcome)
    )
    watchdog.note_ui_phase = lambda phase, done=None, total=None, token=None: calls.append(
        ("phase", phase, done, total, token)
    )

    class ProgressDialog:
        def __init__(self, title, cancel_text, minimum, maximum, parent):
            assert (title, cancel_text, minimum, maximum) == ("Progress", "Cancel", 0, 0)
            assert parent == "main-window"
            self.wasCanceled = False
            self.close_calls = 0
            self.labels = []
            dialogs.append(self)

        def setWindowModality(self, value):
            assert value == "window-modal"

        def setMinimumDuration(self, value):
            assert value == 0

        def show(self):
            if fail_at == "show":
                raise RuntimeError("show failed")

        def setCancelButton(self, button):
            assert button is None

        def setLabelText(self, value):
            if fail_at == "label":
                raise RuntimeError("label failed")
            self.labels.append(value)

        def cancel(self):
            self.wasCanceled = True

        def close(self):
            self.close_calls += 1

    qt_module = types.SimpleNamespace(
        QProgressDialog=ProgressDialog,
        Qt=types.SimpleNamespace(WindowModal="window-modal"),
    )
    slicer_module = types.SimpleNamespace(
        util=types.SimpleNamespace(mainWindow=lambda: "main-window"),
        app=types.SimpleNamespace(processEvents=lambda: calls.append(("events",))),
    )
    monkeypatch.setitem(sys.modules, "dentobot_workflow", package)
    monkeypatch.setitem(sys.modules, "dentobot_workflow.ui_stall_watchdog", watchdog)
    monkeypatch.setitem(sys.modules, "qt", qt_module)
    monkeypatch.setitem(sys.modules, "slicer", slicer_module)
    spec = importlib.util.spec_from_file_location("dentobot_workflow.workflow_progress", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module, calls, dialogs


def test_progress_updates_keep_token_and_close_is_idempotent(monkeypatch):
    module, calls, dialogs = load_progress(monkeypatch)
    progress = module.WorkflowProgress("Progress")
    token = progress.action_token
    progress.update("Import", 2, 4)
    progress.close()
    progress.close()
    progress.update("stale")

    assert len(dialogs) == 1
    assert dialogs[0].labels == ["Progress: Starting · 0s elapsed", "Progress: Import (2/4) · 0s elapsed"]
    assert dialogs[0].close_calls == 1
    assert ("phase", "Progress: Import", 2, 4, token) in calls
    assert [call for call in calls if call[0] == "end"] == [("end", token, "closed")]
    assert calls.count(("events",)) == 2


def test_known_cancel_closes_action_as_cancelled(monkeypatch):
    module, calls, dialogs = load_progress(monkeypatch)
    progress = module.WorkflowProgress("Progress")
    token = progress.action_token
    dialogs[0].cancel()
    with pytest.raises(module.WorkflowCancelled):
        progress.update("next checkpoint")
    progress.close()

    assert dialogs[0].close_calls == 1
    assert [call for call in calls if call[0] == "end"] == [("end", token, "cancelled")]


@pytest.mark.parametrize("fail_at", ("show", "label"))
def test_constructor_failure_ends_started_action(monkeypatch, fail_at):
    module, calls, dialogs = load_progress(monkeypatch, fail_at=fail_at)
    with pytest.raises(RuntimeError, match="failed"):
        module.WorkflowProgress("Progress")

    token = next(call[2] for call in calls if call[0] == "begin")
    assert dialogs[0].close_calls == 1
    assert [call for call in calls if call[0] == "end"] == [("end", token, "error")]
