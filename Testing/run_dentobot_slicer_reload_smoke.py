"""Headless Slicer smoke test for the developer module-reload button."""

from __future__ import annotations

import json
import sys

import qt
import slicer


MODULE_NAME = "DENTOWorkflow"
SENTINEL_NAME = "DENTOBOT Reload Scene Sentinel"


def fail(message: str) -> None:
    print(json.dumps({"module_reload_success": False, "error": message}))
    slicer.util.exit(1)


def verify_reload(old_widget_id: int, old_helper_id: int) -> None:
    try:
        new_widget = slicer.util.getModuleWidget(MODULE_NAME)
        button = new_widget.ui.reloadDENTOWorkflowButton
        sentinel = slicer.util.getFirstNodeByName(SENTINEL_NAME)
        new_helper_id = id(sys.modules["DENTOROS2Bridge"])
        report = {
            "button_visible": bool(button.visible),
            "helper_module_reloaded": new_helper_id != old_helper_id,
            "module_reload_success": id(new_widget) != old_widget_id,
            "scene_preserved": sentinel is not None,
            "workspace_explorer_visible": bool(
                new_widget.ui.step6WorkspaceGroupBox
                and new_widget.ui.generateRobotWorkspaceButton
            ),
        }
        if sentinel is not None:
            slicer.mrmlScene.RemoveNode(sentinel)
        if not all(report.values()):
            fail(f"reload contract failed: {report}")
            return
        print(json.dumps(report, indent=2, sort_keys=True))
        slicer.util.exit(0)
    except Exception as exc:
        fail(str(exc))


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
    old_helper_id = id(sys.modules["DENTOROS2Bridge"])
    old_widget_id = id(old_widget)
    button.click()
    qt.QTimer.singleShot(
        3000,
        lambda: verify_reload(old_widget_id, old_helper_id),
    )


qt.QTimer.singleShot(0, run)
