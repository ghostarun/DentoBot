"""Load the retained operator Step 6 package twice without mutating lineage."""

from __future__ import annotations

import math
import os
from pathlib import Path
import sys
import time

import slicer


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOCaseBundle import validate_case_bundle  # noqa: E402
from DENTOROS2Bridge import shutdown_slicer_adapter  # noqa: E402


PACKAGE = Path(
    "/workspace/data/Slicer_Saved/SampleStudy1/dentobot-case-step6.dentocase"
)


def process_events(seconds: float = 0.5) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def assert_points_close(expected, actual, path: str) -> None:
    if len(expected) != len(actual):
        raise RuntimeError(f"{path} point count changed")
    for point_index, (expected_point, actual_point) in enumerate(
        zip(expected, actual)
    ):
        for axis, (expected_value, actual_value) in enumerate(
            zip(expected_point, actual_point)
        ):
            if not math.isclose(
                float(expected_value),
                float(actual_value),
                rel_tol=0.0,
                abs_tol=1e-6,
            ):
                raise RuntimeError(
                    f"{path}[{point_index}][{axis}] changed: "
                    f"{expected_value} != {actual_value}"
                )


def run() -> None:
    if not PACKAGE.is_file():
        raise RuntimeError(f"operator package is missing: {PACKAGE}")
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget._applyDENTOBOTGuiMode("legacy", persist=False)
    process_events(0.25)
    inspection = validate_case_bundle(PACKAGE)
    expected_imported = bool(
        inspection.workflow["step6"]["planningContextImportedAtSave"]
    )
    expected_plane = next(
        record
        for record in inspection.workflow["nodes"]
        if record["field"] == "targetDockingReferencePlane"
    )
    expected_trajectory = next(
        record
        for record in inspection.workflow["nodes"]
        if record["field"] == "trajectoryLine"
    )
    expected_insertion = next(
        record
        for record in inspection.workflow["nodes"]
        if record["field"] == "templateInsertionDirection"
    )
    expected_shell = next(
        record
        for record in inspection.workflow["nodes"]
        if record["field"] == "patientContactShellModel"
    )
    expected_final = next(
        record
        for record in inspection.workflow["nodes"]
        if record["field"] == "finalPrintableTemplateModel"
    )

    for attempt in range(2):
        widget._openCaseBundle(PACKAGE)
        process_events(1.0)
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        if widget._caseBundleRestoreDepth != 0:
            raise RuntimeError("restore barrier remained active")
        if slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"):
            raise RuntimeError("package restored a live ROS robot")
        parameter_node = widget._parameterNode
        package_issues = widget.logic.step6PlanningPackageFreshnessIssues(
            parameter_node
        )
        if bool(parameter_node.step6PlanningContextImported) != expected_imported:
            raise RuntimeError(
                "restore changed the package's saved Step 6 import state: "
                f"expected {expected_imported}, got "
                f"{bool(parameter_node.step6PlanningContextImported)}"
            )
        if package_issues:
            raise RuntimeError(
                "restored Steps 0–5 package is unexpectedly stale: "
                + " ".join(package_issues)
            )
        if expected_imported:
            jaw_issues = widget.logic.step6CaseJawOpeningFreshnessIssues(
                parameter_node
            )
            if not jaw_issues or not any(
                "four Step 6 case jaw landmarks" in issue for issue in jaw_issues
            ):
                raise RuntimeError(
                    "restore did not expose the expected Step 6.0A landmark gate"
                )
            if parameter_node.robotBaseMountLocked:
                raise RuntimeError(
                    "restore retained an unsafe locked pre-opening base"
                )
            if parameter_node.step6BasePlacementStatus != "Stale":
                raise RuntimeError(
                    "restored pre-opening base was not retained as Stale"
                )
            base = parameter_node.robotBaseTransform
            if base.GetAttribute("DENTOBOT.RobotBaseMountLocked") != "false":
                raise RuntimeError(
                    "base MRML lock evidence disagrees with typed state"
                )
            widget._updateStep6CaseJawOpeningControls()
            widget._updateStep6PlanningUi()
            if widget._step6SceneKind() != "case":
                raise RuntimeError(
                    "restored package is not the active Step 6 case scene"
                )
            if not widget.ui.step6CaseJawOpeningGroupBox.enabled:
                raise RuntimeError(
                    "Step 6.0A remained disabled after package restore"
                )
            if not widget.ui.createStep6CaseJawLandmarksButton.enabled:
                raise RuntimeError(
                    "first Step 6.0A landmark action remained disabled"
                )
            if not widget.ui.importStep6PlanningContextButton.enabled:
                raise RuntimeError(
                    "Step 6 package/import recovery action remained disabled"
                )
            if widget.ui.step6MountLockGroupBox.enabled:
                raise RuntimeError(
                    "Step 6.1 became active before Step 6.0A completion"
                )
            if (
                "Complete 6.0A"
                not in widget.ui.step6PlanningContextStatusLabel.text
            ):
                raise RuntimeError(
                    "Step 6 status does not direct the operator to 6.0A"
                )
        plane = widget._parameterNode.targetDockingReferencePlane
        assembly = widget._parameterNode.targetDockingAssemblyModel
        if (
            plane.GetAttribute("DENTOBOT.OrientationState")
            != expected_plane["attributes"]["DENTOBOT.OrientationState"]
        ):
            raise RuntimeError("restore changed the Step 4C plane orientation")
        if assembly.GetAttribute("DENTOBOT.GeometryState") != "Current":
            raise RuntimeError(
                "restore falsely marked Step 4C stale: "
                f"{assembly.GetAttribute('DENTOBOT.StaleReason')}"
            )
        trajectory = widget._parameterNode.trajectoryLine
        actual_points = []
        for index in range(trajectory.GetNumberOfDefinedControlPoints()):
            point = [0.0, 0.0, 0.0]
            trajectory.GetNthControlPointPositionWorld(index, point)
            actual_points.append(point)
        assert_points_close(
            expected_trajectory["controlPointsWorldRasMm"],
            actual_points,
            f"attempt{attempt}.trajectory",
        )
        insertion = widget._parameterNode.templateInsertionDirection
        insertion_points = []
        for index in range(insertion.GetNumberOfDefinedControlPoints()):
            point = [0.0, 0.0, 0.0]
            insertion.GetNthControlPointPositionWorld(index, point)
            insertion_points.append(point)
        assert_points_close(
            expected_insertion["controlPointsWorldRasMm"],
            insertion_points,
            f"attempt{attempt}.insertionDirection",
        )
        direction_summary = widget.logic.getTemplateInsertionDirectionSummary(
            insertion
        )
        shell = widget._parameterNode.patientContactShellModel
        shell_summary = widget.logic.getPatientContactShellSummary(shell)
        process_events(0.25)
        if (
            direction_summary["geometryJson"]
            != shell_summary["insertionGeometryJson"]
        ):
            raise RuntimeError("loaded insertion geometry differs from shell provenance")
        if (
            shell.GetAttribute("DENTOBOT.GeometryState")
            != expected_shell["attributes"]["DENTOBOT.GeometryState"]
        ):
            raise RuntimeError(
                "restore falsely marked the patient shell stale: "
                f"{shell.GetAttribute('DENTOBOT.StaleReason')}"
            )
        final_template = widget._parameterNode.finalPrintableTemplateModel
        if (
            final_template.GetAttribute("DENTOBOT.GeometryState")
            != expected_final["attributes"]["DENTOBOT.GeometryState"]
        ):
            raise RuntimeError(
                "restore falsely marked the final template stale: "
                f"{final_template.GetAttribute('DENTOBOT.StaleReason')}"
            )
        verification = widget.logic.verifyFinalPrintableTemplate(final_template)
        if any(check["result"] == "FAIL" for check in verification["checks"]):
            raise RuntimeError("final geometry verification contains a failure")

        stage_combo = widget.ui.workflowStageComboBox
        if not stage_combo.enabled:
            raise RuntimeError("restored-case workflow stage picker is disabled")
        for stage_index in range(len(widget._workflowStageEntries())):
            stage_item = stage_combo.model().item(stage_index)
            if stage_item is not None and not stage_item.isEnabled():
                raise RuntimeError(
                    f"restored-case workflow stage {stage_index} is disabled"
                )
            widget._setWorkflowStage(stage_index, ensureVisible=False)
            process_events(0.05)
            if int(stage_combo.currentIndex) != stage_index:
                raise RuntimeError(
                    f"could not resume restored case at workflow stage {stage_index}"
                )
            active_section = widget._workflowStageEntries()[stage_index][1]
            if active_section.isHidden() or active_section.collapsed:
                raise RuntimeError(
                    f"workflow stage {stage_index} did not become the active card"
                )
            if slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"):
                raise RuntimeError(
                    "stage navigation restored or created a live ROS robot"
                )

        widget._applyDENTOBOTGuiMode("shell", persist=False)
        process_events(0.25)
        shell = widget._applicationShell
        if not shell or not shell.active:
            raise RuntimeError(
                "restored case could not enter the six-workspace application shell"
            )
        if len(shell._workspace_buttons) != 6:
            raise RuntimeError(
                "restored case does not expose exactly six application workspaces"
            )
        for workspace_index, workspace_button in enumerate(
            shell._workspace_buttons
        ):
            if not workspace_button.enabled:
                raise RuntimeError(
                    f"restored-case workspace {workspace_index} is disabled"
                )
            workspace_button.click()
            process_events(0.05)
            if int(shell._current_workspace_index) != workspace_index:
                raise RuntimeError(
                    f"could not resume restored case in workspace {workspace_index}"
                )
            if slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"):
                raise RuntimeError(
                    "workspace navigation restored or created a live ROS robot"
                )
        widget._applyDENTOBOTGuiMode("legacy", persist=False)
        process_events(0.25)

    print("DENTOBOT_EXISTING_CASE_RESTORE_PASS", flush=True)
    shutdown_slicer_adapter()
    slicer.util.exit(0)


try:
    run()
except Exception as exc:
    message = " ".join(str(exc).split())[:500]
    os.write(
        2,
        (
            "DENTOBOT_EXISTING_CASE_RESTORE_FAILED: "
            f"{type(exc).__name__}: {message}\n"
        ).encode("utf-8", errors="replace"),
    )
    process_events(0.25)
    shutdown_slicer_adapter()
    slicer.util.exit(1)
