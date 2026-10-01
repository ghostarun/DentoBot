"""Headless real-Qt check for the Step 6.1 -> 6.2 -> 6.3 UI sequence."""

from __future__ import annotations

import json

import qt
import slicer


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def process_events() -> None:
    for _ in range(8):
        slicer.app.processEvents()


def authority_snapshot(parameter_node) -> tuple[object, ...]:
    return tuple(
        getattr(parameter_node, name)
        for name in (
            "robotBaseMountLocked",
            "step6BasePlacementStatus",
            "step6TaskHomeJson",
            "step6ConfirmedTaskJson",
            "step6MotionDiagnosticJson",
        )
    )


def run() -> None:
    try:
        slicer.util.selectModule("DENTOWorkflow")
        process_events()
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        require(widget is not None, "DENTOWorkflow widget was not created")
        widget._setWorkflowStage(10, ensureVisible=False)
        process_events()
        panel = widget._robotSimulationPanel
        require(panel is not None, "robot simulation panel was not created")
        before = authority_snapshot(widget._parameterNode)

        widget._configureRobotSimulationShellSubstep(1)
        process_events()
        require(panel.visualizationGroup.visible, "6.1 setup is hidden")
        require(panel.step61TabWidget.count == 2, "6.1 Placement/Scene views changed")
        require(hasattr(panel, "baseInteractionStatusLabel"), "6.1 drag status is missing")

        widget._configureRobotSimulationShellSubstep(2)
        process_events()
        require(panel.homeGroup.visible, "6.2 Home is hidden")
        require(len(panel.taskHomeJointControls) == 5, "6.2 does not show J1-J5")

        widget._configureRobotSimulationShellSubstep(3)
        process_events()
        require(panel.workbenchGroup.visible, "6.3 workbench is hidden")
        require(not panel.homeGroup.visible, "full 6.2 Home editor leaked into 6.3")
        require(panel.step63TabWidget.count == 3, "6.3 does not expose three primary views")
        require(
            tuple(panel.step63TabWidget.tabText(i) for i in range(3))
            == ("Manual", "Workspace", "Plan"),
            "6.3 primary view order changed",
        )
        require(panel.step63ManualTabWidget.count == 2, "Manual Joints/TCP views changed")
        draft_before = tuple(panel.manualJogJointPositionsSi().items())

        panel.step63TabWidget.currentIndex = 2
        panel.step63EditBaseButton.click()
        process_events()
        require(panel._activeSubstep == 1, "Edit Base did not navigate to 6.1")
        require(panel.returnFromBaseButton.visible, "6.1 return context is missing")
        panel.returnFromBaseButton.click()
        process_events()
        require(panel._activeSubstep == 3, "Base return did not restore 6.3")
        require(panel.step63TabWidget.currentIndex == 2, "Plan return view was not preserved")

        panel.step63TabWidget.currentIndex = 0
        panel.step63ReviewHomeButton.click()
        process_events()
        require(panel._activeSubstep == 2, "Review Home did not navigate to 6.2")
        require(panel.returnFromHomeButton.visible, "6.2 return context is missing")
        panel.returnFromHomeButton.click()
        process_events()
        require(panel._activeSubstep == 3, "Home return did not restore 6.3")
        require(panel.step63TabWidget.currentIndex == 0, "Manual return view was not preserved")

        panel.showManualRecordsDialog()
        panel.showPlanningToolsDialog()
        panel.showAnatomyReviewDialog()
        process_events()
        require(panel._manualRecordsDialog.visible, "Records tool did not open")
        require(panel._planningToolsDialog.visible, "Planner Comparison tool did not open")
        require(panel._anatomyReviewDialog.visible, "Anatomy Review tool did not open")
        widget._configureRobotSimulationShellSubstep(2)
        process_events()
        require(not panel._manualRecordsDialog.visible, "Records tool remained active outside 6.3")
        require(not panel._planningToolsDialog.visible, "Planner tool remained active outside 6.3")
        require(not panel._anatomyReviewDialog.visible, "Anatomy tool remained active outside 6.3")

        widget._configureRobotSimulationShellSubstep(3)
        process_events()
        require(
            tuple(panel.manualJogJointPositionsSi().items()) == draft_before,
            "6.1/6.2/6.3 navigation changed the joint draft",
        )
        require(
            authority_snapshot(widget._parameterNode) == before,
            "view navigation changed Base/Home/task/plan authority",
        )
        print(
            json.dumps(
                {
                    "dentobot_step63_ui_headless": True,
                    "sequence": ["6.1", "6.2", "6.3", "6.1", "6.3", "6.2", "6.3"],
                    "primary_views": ["Manual", "Workspace", "Plan"],
                    "joint_draft_preserved": True,
                    "authority_unchanged": True,
                    "tools_close_outside_6_3": True,
                },
                sort_keys=True,
            )
        )
        print("DENTOBOT_STEP63_UI_HEADLESS_PASS", flush=True)
        slicer.util.exit(0)
    except Exception as exc:
        print(json.dumps({"dentobot_step63_ui_headless": False, "error": str(exc)}))
        slicer.util.exit(1)


qt.QTimer.singleShot(0, run)
