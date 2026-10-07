"""Exercise the smoke runner without Slicer, including action replacement."""

from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("disabled_cycle", [None, 0, 2])
def test_production_menu_action_is_reacquired(monkeypatch, capsys, disabled_cycle):
    callbacks, exits, widgets, helpers, internals, triggered = [], [], [], [], [], []
    sentinel = object()
    scene = SimpleNamespace(
        AddNewNodeByClass=lambda *args: sentinel,
        RemoveNode=lambda node: removed.append(node),
    )
    removed = []

    def replace_widget():
        cycle = len(widgets)
        action = SimpleNamespace(visible=True, enabled=True)

        def trigger():
            # A stale QAction must never be used after its widget is replaced.
            assert widgets[-1]._workflowReloadMenuAction is action
            assert action.enabled
            triggered.append(cycle)
            replace_widget()

        action.trigger = trigger
        widget = SimpleNamespace(
            _workflowReloadMenuAction=action,
            _syncWorkflowMoreMenu=lambda: setattr(
                action, "enabled", cycle != disabled_cycle
            ),
            ui=SimpleNamespace(
                reloadDENTOWorkflowButton=SimpleNamespace(visible=False),
                step6WorkspaceGroupBox=object(),
                generateRobotWorkspaceButton=object(),
            ),
        )
        widgets.append(widget)
        helpers.append(SimpleNamespace())
        internals.append(SimpleNamespace())
        monkeypatch.setitem(sys.modules, "DENTOROS2Bridge", helpers[-1])
        monkeypatch.setitem(sys.modules, "dentobot_workflow.widget_robot", internals[-1])

    replace_widget()
    monkeypatch.setitem(sys.modules, "qt", SimpleNamespace(
        QTimer=SimpleNamespace(singleShot=lambda delay, callback: callbacks.append(callback))
    ))
    monkeypatch.setitem(sys.modules, "slicer", SimpleNamespace(
        util=SimpleNamespace(
            selectModule=lambda name: None,
            getModuleWidget=lambda name: widgets[-1],
            getFirstNodeByName=lambda name: sentinel,
            exit=exits.append,
        ),
        app=SimpleNamespace(processEvents=lambda: None),
        mrmlScene=scene,
    ))
    state = runpy.run_path(str(Path(__file__).with_name("run_dentobot_slicer_reload_smoke.py")))
    while callbacks and not exits:
        callbacks.pop(0)()
    output = capsys.readouterr().out
    if disabled_cycle is None:
        assert exits == [0]
        assert triggered == list(range(5))
        assert len(state["reports"]) == 5
        assert all(report["scene_preserved"] for report in state["reports"])
        assert removed == [sentinel]
        assert "DENTOBOT_FIVE_RELOAD_CYCLES_PASS" in output
    else:
        assert exits == [1]
        assert len(triggered) == disabled_cycle
        assert "missing, hidden or disabled" in output
        assert "DENTOBOT_FIVE_RELOAD_CYCLES_PASS" not in output
