"""Headless Slicer smoke test for the developer module-reload button."""

from __future__ import annotations

import json
import sys

import qt
import slicer


MODULE_NAME = "DENTOWorkflow"
SENTINEL_NAME = "DENTOBOT Reload Scene Sentinel"
RELOAD_CYCLES = 5
reports = []


def fail(message: str) -> None:
    print(json.dumps({"module_reload_success": False, "error": message}))
    slicer.util.exit(1)


def verify_reload(
    cycle: int,
    old_widget_id: int,
    old_helper_id: int,
    old_internal_id: int,
) -> None:
    try:
        new_widget = slicer.util.getModuleWidget(MODULE_NAME)
        button = new_widget.ui.reloadDENTOWorkflowButton
        sentinel = slicer.util.getFirstNodeByName(SENTINEL_NAME)
        new_helper_id = id(sys.modules["DENTOROS2Bridge"])
        new_internal_id = id(sys.modules["dentobot_workflow.widget_robot"])
        report = {
            "button_visible": bool(button.visible),
            "helper_module_reloaded": new_helper_id != old_helper_id,
            "internal_module_reloaded": new_internal_id != old_internal_id,
            "module_reload_success": id(new_widget) != old_widget_id,
            "scene_preserved": sentinel is not None,
            "workspace_explorer_visible": bool(
                new_widget.ui.step6WorkspaceGroupBox
                and new_widget.ui.generateRobotWorkspaceButton
            ),
        }
        if not all(report.values()):
            fail(f"reload contract failed: {report}")
            return
        report["cycle"] = cycle
        reports.append(report)
        if cycle < RELOAD_CYCLES:
            qt.QTimer.singleShot(250, lambda: reload_once(cycle + 1))
            return
        if sentinel is not None:
            slicer.mrmlScene.RemoveNode(sentinel)
        print(
            json.dumps(
                {
                    "module_reload_success": True,
                    "cycles": RELOAD_CYCLES,
                    "reports": reports,
                },
                indent=2,
                sort_keys=True,
            )
        )
        print("DENTOBOT_FIVE_RELOAD_CYCLES_PASS")
        slicer.util.exit(0)
    except Exception as exc:
        fail(str(exc))


def reload_once(cycle: int) -> None:
    old_widget = slicer.util.getModuleWidget(MODULE_NAME)
    button = old_widget.ui.reloadDENTOWorkflowButton
    old_helper_id = id(sys.modules["DENTOROS2Bridge"])
    old_internal_id = id(sys.modules["dentobot_workflow.widget_robot"])
    old_widget_id = id(old_widget)
    button.click()
    qt.QTimer.singleShot(
        3000,
        lambda: verify_reload(
            cycle,
            old_widget_id,
            old_helper_id,
            old_internal_id,
        ),
    )


def run() -> None:
    slicer.util.selectModule(MODULE_NAME)
    slicer.app.processEvents()
    old_widget = slicer.util.getModuleWidget(MODULE_NAME)
    button = old_widget.ui.reloadDENTOWorkflowButton
    if button is None or not button.visible:
        fail("developer reload button is missing or hidden")
        return
    sentinel = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLScriptedModuleNode",
        SENTINEL_NAME,
    )
    if sentinel is None:
        fail("could not create reload scene sentinel")
        return
    reload_once(1)


qt.QTimer.singleShot(0, run)
