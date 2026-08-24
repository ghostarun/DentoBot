"""Visible-main-window Slicer smoke for the switchable DENTOBOT shell."""

from __future__ import annotations

import json

import qt
import slicer


def fail(message: str) -> None:
    print(json.dumps({"dentobot_application_shell": False, "error": message}))
    slicer.util.exit(1)


def run() -> None:
    try:
        settings = qt.QSettings()
        settings.setValue("DENTOBOT/ApplicationShell/GuiMode", "legacy")
        settings.setValue("DENTOBOT/ApplicationShell/ExpertMode", False)
        slicer.util.selectModule("DENTOWorkflow")
        slicer.app.processEvents()
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        if widget is None or widget._applicationShell is None:
            raise RuntimeError("DENTOBOT application shell was not initialized")

        widget._applyDENTOBOTGuiMode("shell")
        slicer.app.processEvents()
        shell = widget._applicationShell
        if not shell.active:
            raise RuntimeError("shell mode did not activate")
        nav_dock = slicer.util.mainWindow().findChild(
            "QDockWidget", "DENTOBOTNavigationDock"
        )
        task_dock = slicer.util.mainWindow().findChild(
            "QDockWidget", "DENTOBOTTaskDock"
        )
        if nav_dock is None or task_dock is None:
            raise RuntimeError("application navigation/task docks are missing")
        if len(shell._workspace_buttons) != 6:
            raise RuntimeError("shell does not expose exactly six workspaces")
        if widget.ui.workflowNavigationGroupBox.visible:
            raise RuntimeError("legacy navigator remained visible in shell mode")
        if shell._view_button is None or not shell._view_button.visible:
            raise RuntimeError("new shell does not expose the shared Views control")
        shell._view_button.click()
        slicer.app.processEvents()
        if not widget._viewControlsPalette.visible:
            raise RuntimeError("new-shell Views button did not open the view palette")
        views_screenshot_path = (
            "/workspace/data/dentobot-runs/dentobot-grouped-views-smoke.png"
        )
        if not widget._viewControlsPalette.grab().save(views_screenshot_path):
            raise RuntimeError("could not capture the grouped Views palette")
        widget._hideViewControlsPalette(preservePreference=False)

        widget._setWorkflowStage(8)
        slicer.app.processEvents()
        if not shell._workspace_buttons[4].checked:
            raise RuntimeError("legacy stage 5B did not map to Guide Design")
        if shell._substep_combo.currentIndex != 3:
            raise RuntimeError("Guide Design did not select Shell and Guide Fusion")

        widget._setWorkflowStage(10)
        slicer.app.processEvents()
        if shell._substep_combo.count != 7:
            raise RuntimeError("Robot Simulation does not expose seven gated substeps")
        if not shell._substep_combo.visible:
            raise RuntimeError("Robot Simulation substep selector is hidden")
        shell._substep_combo.setCurrentIndex(3)
        slicer.app.processEvents()
        if not widget.ui.step6WorkspaceGroupBox.visible:
            raise RuntimeError("workspace explorer was not shown in 6.3")
        if not widget._robotSimulationPanel.workspaceReviewGroup.visible:
            raise RuntimeError("assisted-limit review was not shown in 6.3")
        if widget.ui.step6TaskJointLimitsGroupBox.visible:
            raise RuntimeError("Task Home controls leaked into workspace review")
        shell._substep_combo.setCurrentIndex(4)
        slicer.app.processEvents()
        if not widget._robotSimulationPanel.runtimeGroup.visible:
            raise RuntimeError("native runtime/task confirmation was not shown in 6.4")
        if not widget._robotSimulationPanel.collisionGroup.visible:
            raise RuntimeError("Scene and Collision diagnostics were not shown in 6.4")
        if widget._robotSimulationPanel.goalGroup.visible:
            raise RuntimeError("expert Goal/IK controls leaked into the routine sequence")
        shell._substep_combo.setCurrentIndex(5)
        slicer.app.processEvents()
        if not widget._robotSimulationPanel.approachGroup.visible:
            raise RuntimeError("Goal 1 approach card was not shown in 6.5")
        shell._substep_combo.setCurrentIndex(6)
        slicer.app.processEvents()
        if not widget._robotSimulationPanel.drillingGroup.visible:
            raise RuntimeError("Goal 2 drilling-preview card was not shown in 6.6")

        shell.applyTheme("dark")
        if str(settings.value("DENTOBOT/ApplicationShell/Theme")) != "dark":
            raise RuntimeError("dark theme preference was not stored")
        if "#20262c" not in shell._task_container.styleSheet:
            raise RuntimeError("dark theme was not applied to the task panel")
        shell.applyTheme("light")
        if "#f5f7fa" not in shell._nav_container.styleSheet:
            raise RuntimeError("light theme was not applied to navigation")

        screenshot_path = "/workspace/data/dentobot-runs/dentobot-application-shell-smoke.png"
        if not slicer.util.mainWindow().grab().save(screenshot_path):
            raise RuntimeError("could not capture the application shell screenshot")

        shell.setExpertMode(True)
        shell.setExpertMode(False)
        if not shell._nav_dock.visible or not shell._task_dock.visible:
            raise RuntimeError("Focus mode hid DENTOBOT's own docks")

        widget._applyDENTOBOTGuiMode("legacy")
        slicer.app.processEvents()
        if shell.active:
            raise RuntimeError("legacy mode did not deactivate the shell")
        if not widget.ui.workflowNavigationGroupBox.visible:
            raise RuntimeError("legacy navigator was not restored")
        if not widget.ui.step6TaskJointLimitsGroupBox.visible:
            raise RuntimeError("legacy Step 6 groups were not restored")
        if widget._robotSimulationPanel.goalGroup.visible:
            raise RuntimeError("new goal card leaked into Legacy mode")

        report = {
            "dentobot_application_shell": True,
            "dual_theme": True,
            "expert_focus_toggle": True,
            "legacy_restore": True,
            "workspace_count": 6,
            "robot_substep_count": 7,
            "shared_views_control": True,
            "screenshot": screenshot_path,
            "views_screenshot": views_screenshot_path,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        print("DENTOBOT_APPLICATION_SHELL_PASS", flush=True)
        slicer.util.exit(0)
    except Exception as exc:
        fail(str(exc))


qt.QTimer.singleShot(0, run)
