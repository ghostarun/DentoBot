"""Exact saved-case acceptance test for guarded Step 6.5/6.6 simulation.

This test restores the operator's x4 case, reconstructs only transient ROS 2
state, and exercises planning plus guarded preview.  It never exposes or calls
hardware execution.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import traceback
from pathlib import Path

import slicer
import vtk


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
MODULE = ROOT / "DENTOWorkflow"
for path in (HELPERS, MODULE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import DENTOROS2Bridge as bridge  # noqa: E402


PACKAGE = Path(
    "/workspace/data/Slicer_Saved/SampleStudy1/"
    "dentobot-case-step6x4.dentocase"
)
EXPECTED_TASK = "39201d8f79a4a9ebee2290dfe7f2f37415123187b8b654aee038dba27584c27c"
PREVIEW_TIMEOUT_SEC = float(os.environ.get("DENTOBOT_PREVIEW_TIMEOUT_SEC", "240"))


def process_events(seconds: float = 0.25) -> None:
    deadline = time.monotonic() + float(seconds)
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        ros_logic = slicer.util.getModuleLogic("ROS2")
        if ros_logic is not None:
            ros_logic.Spin()
        time.sleep(0.01)


def wait_until(predicate, timeout_sec: float):
    deadline = time.monotonic() + float(timeout_sec)
    while time.monotonic() < deadline:
        process_events(0.05)
        result = predicate()
        if result:
            return result
    return None


def require_success(result, stage: str):
    if not result.success:
        raise RuntimeError(f"{stage}: {result.message}")
    return result


def run() -> dict[str, object]:
    if not PACKAGE.is_file():
        raise RuntimeError(f"exact operator package is missing: {PACKAGE}")
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    if widget is None:
        raise RuntimeError("DENTOWorkflow widget is unavailable")
    widget._applyDENTOBOTGuiMode("legacy", persist=False)
    widget._openCaseBundle(PACKAGE)
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    parameter_node = widget._parameterNode
    logic = widget.logic
    facade = widget._robotWorkflowFacade
    if parameter_node is None or logic is None or facade is None:
        raise RuntimeError("restored Step 6 workflow services are unavailable")
    if slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"):
        raise RuntimeError("the package serialized a transient ROS robot")
    package_issues = logic.step6PlanningPackageFreshnessIssues(parameter_node)
    jaw_issues = logic.step6CaseJawOpeningFreshnessIssues(parameter_node)
    home_issues = logic.taskHomeFreshnessIssues(parameter_node)
    task_issues = logic.confirmedTaskFreshnessIssues(parameter_node)
    # A saved task snapshot may intentionally become stale after a robot-profile
    # migration (for example the J2/J5 URDF update).  Geometry/jaw/home
    # corruption is still a hard restore failure, but the immutable snapshot
    # is expected to be explicitly reconfirmed after the live runtime is
    # reconstructed below.
    if package_issues or jaw_issues or home_issues:
        raise RuntimeError(
            "restored x4 prerequisites are stale: "
            + " | ".join(
                " ".join(group)
                for group in (package_issues, jaw_issues, home_issues)
                if group
            )
        )
    restored_snapshot = logic.confirmedTaskRecord(parameter_node)
    restored_task_before_runtime = (
        restored_snapshot.snapshot_fingerprint if restored_snapshot is not None else ""
    )
    if not parameter_node.robotBaseMountLocked:
        raise RuntimeError("restored x4 robot base is not provisionally locked")

    require_success(facade.loadRobot(), "load local robot")
    selected_before_connect = slicer.util.selectedModule()
    connection = facade.connect(open_motion_module=False)
    task_home_remediated = False
    if not connection.success:
        if (
            connection.code != "task_home_scene_invalid_runtime_connected"
            or not facade.capabilities().connected
        ):
            raise RuntimeError(f"connect ROS/MoveIt: {connection.message}")
        # The x4 package intentionally remains immutable on disk.  Exercise the
        # same explicit operator recovery offered by 6.2: the rejected home has
        # already restored the current guard-accepted joint vector in the UI.
        require_success(facade.saveTaskHome(), "save remediated Task Home")
        require_success(facade.applyTaskHome(), "validate remediated Task Home")
        require_success(facade.confirmTask(), "confirm remediated task")
        task_home_remediated = True
    connected = connection
    # Rebuild the live evidence invalidated by the saved package's legacy
    # robot-profile migration.  This follows the normal 6.2→6.4 operator
    # sequence; it is intentionally not an automatic connect/restore action.
    if not facade.taskHomeRuntimeValidated(parameter_node):
        require_success(facade.saveTaskHome(), "save migrated Task Home")
        require_success(facade.applyTaskHome(), "apply migrated Task Home")
    if not facade.workspaceRuntimeValidated(parameter_node):
        require_success(facade.generateWorkspaceCloud(), "regenerate workspace")
        require_success(facade.reviewAssistedLimits(), "review regenerated limits")
    # Reconfirm an old snapshot only after all transient ROS/MoveIt evidence is
    # live.  This is the same explicit operator action required by 6.4 after a
    # robot-resource or policy revision; it must never be auto-connect state.
    if task_issues or logic.confirmedTaskRecord(parameter_node) is None:
        require_success(facade.confirmTask(), "reconfirm restored task")
    snapshot = logic.confirmedTaskRecord(parameter_node)
    if slicer.util.selectedModule() != selected_before_connect:
        raise RuntimeError("routine Step 6 Connect left DENTOWorkflow")

    approach = require_success(facade.planApproachPhase(), "plan Goal 1")
    approach_plan = approach.payload
    planned_path_nodes = [
        node
        for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
        if node.GetAttribute("DENTOBOT.Step6PhasePlanPath") == "true"
    ]
    if not 1 <= len(planned_path_nodes) <= 3:
        raise RuntimeError(
            "Goal 1 did not create the expected bounded set of stage paths."
        )
    for planned_path_node in planned_path_nodes:
        planned_path_polydata = planned_path_node.GetPolyData()
        if (
            planned_path_polydata is None
            or planned_path_polydata.GetNumberOfPoints() < 2
            or planned_path_polydata.GetNumberOfLines() < 1
        ):
            raise RuntimeError(
                "A Goal 1 stage path is empty or has no rendered path cells."
            )
    for waypoint in approach_plan.waypoint_joint_vectors_si:
        if abs(float(waypoint[bridge.ROS2_JOINT_SI_ORDER[-1]])) > 1.0e-9:
            raise RuntimeError("Goal 1 moved the externally driven spindle joint")
    if not approach_plan.tool_orientation_fingerprint:
        raise RuntimeError("Goal 1 did not commit a Stage-1 drilling frame")
    if len(approach_plan.tool_axis_ras) != 3 or not math.isclose(
        sum(float(value) ** 2 for value in approach_plan.tool_axis_ras),
        1.0,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        raise RuntimeError("Goal 1 committed an invalid drilling-axis vector")
    if approach_plan.cartesian_fraction < 0.99:
        raise RuntimeError(
            f"Goal 1 terminal fraction is {approach_plan.cartesian_fraction}"
        )
    if approach_plan.coordinate_frame != bridge.ROS2_FIXED_FRAME:
        raise RuntimeError(
            f"Goal 1 used unexpected frame {approach_plan.coordinate_frame}"
        )
    if (
        approach_plan.start_position_error_mm is not None
        and approach_plan.start_position_error_mm
        > bridge.CARTESIAN_START_POSITION_TOLERANCE_MM
    ) or (
        approach_plan.start_orientation_error_deg is not None
        and approach_plan.start_orientation_error_deg
        > bridge.CARTESIAN_START_ORIENTATION_TOLERANCE_DEG
    ):
        raise RuntimeError(
            "Goal 1 start continuity is outside tolerance: "
            f"{approach_plan.start_position_error_mm} mm, "
            f"{approach_plan.start_orientation_error_deg} deg"
        )
    approach_finished = []
    approach_progress = []
    require_success(
        facade.previewPhase(
            "approach",
            interval_ms=50,
            on_progress=lambda index, total: approach_progress.append(
                (int(index), int(total))
            ),
            on_finished=approach_finished.append,
        ),
        "start Goal 1 preview",
    )
    if wait_until(lambda: approach_finished, PREVIEW_TIMEOUT_SEC) is None:
        last_status = bridge._last_task_status
        raise RuntimeError(
            "Goal 1 guarded preview timed out at "
            f"{approach_progress[-1] if approach_progress else (0, len(approach_plan.waypoint_joint_vectors_si))}; "
            f"previewActive={facade.previewActive}, sequence={facade._phase_sequence}, "
            f"lastGuardStatus={last_status}"
        )
    approach_outcome = require_success(approach_finished[-1], "preview Goal 1")
    if facade.completedPhase != "approach":
        raise RuntimeError("Goal 1 did not establish the accepted Entry state")

    # The approach is an independently reviewable milestone.  Keep a focused
    # acceptance mode so a known/intentional Goal 2 reachability failure cannot
    # hide a valid Goal 1 preview during development.
    if os.environ.get("DENTOBOT_GOAL1_ONLY", "") == "1":
        accepted = bridge.last_accepted_joint_positions_si()
        if any(name not in accepted for name in bridge.ROS2_JOINT_SI_ORDER):
            raise RuntimeError("Goal 1 preview did not leave an accepted state")
        return {
            "package": PACKAGE.name,
            # Older step-6 packages may not contain an immutable task record;
            # the empty value is intentional until the live runtime has been
            # reconstructed and the task is explicitly reconfirmed below.
            "restored_task_fingerprint": restored_task_before_runtime,
            "planned_task_fingerprint": (
                snapshot.snapshot_fingerprint if snapshot is not None else ""
            ),
            "task_home_remediated": task_home_remediated,
            "goal1_strict_points": approach_plan.strict_waypoint_count,
            "goal1_axis_points": approach_plan.axis_waypoint_count,
            "goal1_terminal_points": approach_plan.contact_waypoint_count,
            "goal1_cartesian_fraction": approach_plan.cartesian_fraction,
            "goal1_start_position_error_mm": approach_plan.start_position_error_mm,
            "goal1_start_orientation_error_deg": approach_plan.start_orientation_error_deg,
            "goal1_exploratory_tool_contact_suppressed": bool(
                approach_outcome.details.get("exploratoryToolContactSuppressed", False)
            ),
            "goal1_suppressed_tool_contact_samples": int(
                approach_outcome.details.get("suppressedToolContactSampleCount", 0)
            ),
            "goal1_preview_complete": True,
            "goal1_result_code": approach.code,
            "full_task_status": str(
                approach.details.get("fullTaskStatus") or "Provisional"
            ),
            "full_task_blocked_stage": str(
                approach.details.get("blockedStage") or ""
            ),
            "full_task_blocker": str(
                approach.details.get("firstInvalidCause")
                or approach.details.get("terminalPlanningError")
                or approach.details.get("drillingPreflightError")
                or ""
            ),
            "terminal_planning_fraction": approach.details.get(
                "terminalPlanningFraction"
            ),
            "stage_path_count": len(planned_path_nodes),
            "spindle_locked_rad": float(
                accepted[bridge.ROS2_JOINT_SI_ORDER[-1]]
            ),
            "tool_orientation_fingerprint": (
                approach_plan.tool_orientation_fingerprint
            ),
            "tool_axis_ras": tuple(approach_plan.tool_axis_ras),
            "goal2_deferred": True,
            "hardware_execution_enabled": False,
        }

    drilling = require_success(facade.planDrillingPhase(), "plan Goal 2")
    drilling_plan = drilling.payload
    if (
        drilling_plan.tool_orientation_fingerprint
        != approach_plan.tool_orientation_fingerprint
        or tuple(drilling_plan.tool_axis_ras) != tuple(approach_plan.tool_axis_ras)
    ):
        raise RuntimeError(
            "Goal 2 did not inherit the exact Stage-1 drilling-frame commitment"
        )
    if drilling_plan.cartesian_fraction < 0.99:
        raise RuntimeError(
            f"Goal 2 Cartesian fraction is {drilling_plan.cartesian_fraction}"
        )
    if (
        drilling_plan.start_position_error_mm is None
        or drilling_plan.start_position_error_mm
        > bridge.CARTESIAN_START_POSITION_TOLERANCE_MM
        or drilling_plan.start_orientation_error_deg is None
        or drilling_plan.start_orientation_error_deg
        > bridge.CARTESIAN_START_ORIENTATION_TOLERANCE_DEG
    ):
        raise RuntimeError(
            "Goal 2 did not begin at the accepted Entry state: "
            f"{drilling_plan.start_position_error_mm} mm, "
            f"{drilling_plan.start_orientation_error_deg} deg"
        )
    drilling_finished = []
    drilling_progress = []
    require_success(
        facade.previewPhase(
            "drilling",
            interval_ms=50,
            on_progress=lambda index, total: drilling_progress.append(
                (int(index), int(total))
            ),
            on_finished=drilling_finished.append,
        ),
        "start Goal 2 preview",
    )
    if wait_until(lambda: drilling_finished, PREVIEW_TIMEOUT_SEC) is None:
        last_status = bridge._last_task_status
        raise RuntimeError(
            "Goal 2 guarded preview timed out at "
            f"{drilling_progress[-1] if drilling_progress else (0, len(drilling_plan.waypoint_joint_vectors_si))}; "
            f"previewActive={facade.previewActive}, sequence={facade._phase_sequence}, "
            f"lastGuardStatus={last_status}"
        )
    drilling_outcome = require_success(drilling_finished[-1], "preview Goal 2")
    if facade.completedPhase != "drilling":
        raise RuntimeError("Goal 2 did not complete under the phase guard")

    accepted = bridge.last_accepted_joint_positions_si()
    if any(name not in accepted for name in bridge.ROS2_JOINT_SI_ORDER):
        raise RuntimeError("final accepted six-joint state is unavailable")
    robot = connected.payload
    actual_target_base_mm = vtk.vtkMatrix4x4()
    if robot.ComputeKDLFK(
        bridge.joint_si_vector(accepted),
        actual_target_base_mm,
        bridge.ROS2_TOOL_TCP_LINK,
    ) is None:
        raise RuntimeError("final provisional TCP FK failed")
    expected_target_base_m = bridge.world_ras_mm_to_base_m(
        snapshot.target_ras_mm,
        parameter_node.robotBaseTransform,
    )
    final_position_error_mm = math.sqrt(
        sum(
            (
                actual_target_base_mm.GetElement(axis, 3)
                - expected_target_base_m[axis] * 1000.0
            )
            ** 2
            for axis in range(3)
        )
    )
    if final_position_error_mm > bridge.CARTESIAN_START_POSITION_TOLERANCE_MM:
        raise RuntimeError(
            f"final TCP missed Target by {final_position_error_mm:.6f} mm"
        )
    return {
        "package": PACKAGE.name,
        "restored_task_fingerprint": restored_task_before_runtime,
        "planned_task_fingerprint": snapshot.snapshot_fingerprint,
        "task_home_remediated": task_home_remediated,
        "planning_frame": drilling_plan.coordinate_frame,
        "goal1_strict_points": approach_plan.strict_waypoint_count,
        "goal1_terminal_points": approach_plan.contact_waypoint_count,
        "goal1_cartesian_fraction": approach_plan.cartesian_fraction,
        "goal1_start_position_error_mm": approach_plan.start_position_error_mm,
        "goal1_start_orientation_error_deg": approach_plan.start_orientation_error_deg,
        "goal2_points": drilling_plan.contact_waypoint_count,
        "goal2_cartesian_fraction": drilling_plan.cartesian_fraction,
        "goal2_start_position_error_mm": drilling_plan.start_position_error_mm,
        "goal2_start_orientation_error_deg": drilling_plan.start_orientation_error_deg,
        "goal2_axial_roll_deg": drilling_plan.axial_roll_deg,
        "goal1_exploratory_tool_contact_suppressed": bool(
            approach_outcome.details.get("exploratoryToolContactSuppressed", False)
        ),
        "goal1_suppressed_tool_contact_samples": int(
            approach_outcome.details.get("suppressedToolContactSampleCount", 0)
        ),
        "goal2_exploratory_tool_contact_suppressed": bool(
            drilling_outcome.details.get("exploratoryToolContactSuppressed", False)
        ),
        "goal2_suppressed_tool_contact_samples": int(
            drilling_outcome.details.get("suppressedToolContactSampleCount", 0)
        ),
        "final_target_position_error_mm": final_position_error_mm,
        "guarded_preview_complete": True,
        "hardware_execution_enabled": False,
    }


try:
    report = run()
    print("DENTOBOT_STEP65_EXACT_CASE_PASS", flush=True)
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    bridge.disconnect_dentobot_motion_control([])
    bridge.shutdown_slicer_adapter()
    slicer.mrmlScene.Clear(0)
    slicer.app.processEvents()
    slicer.util.exit(0)
except Exception as exc:
    print(f"DENTOBOT_STEP65_EXACT_CASE_FAILED: {exc}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
    try:
        bridge.disconnect_dentobot_motion_control([])
        bridge.shutdown_slicer_adapter()
    except Exception:
        pass
    slicer.util.exit(1)
