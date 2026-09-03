"""Focused, read-only PreEntry axial-roll reachability diagnostic.

This probe restores the exact x4 case, reconstructs the transient simulation
stack, and asks the five-joint MoveIt group for the exact PreEntry XYZ with the
Entry-to-Target tool axis held fixed.  The only varied quantity is the tool
frame roll about that axis (30 degree samples from 0 through 330 degrees).
Collision-aware IK is attempted first for every roll.  If every roll fails,
the same requests are repeated with collision checking disabled solely to
separate kinematic infeasibility from collision-scene infeasibility.  No
joint command, preview, plan, guard session, or production state is changed.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import slicer
import vtk


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
for path in (ROOT / "DENTOWorkflow/Resources/Python", ROOT / "DENTOWorkflow"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import DENTOROS2Bridge as bridge  # noqa: E402


PACKAGE = Path(
    "/workspace/data/Slicer_Saved/SampleStudy1/"
    "dentobot-case-step6x4.dentocase"
)
ROLLS_DEG = tuple(float(value) for value in range(0, 360, 30))
IK_TIMEOUT_SEC = 0.2
FK_TIMEOUT_SEC = 2.0


def process_events(seconds: float = 0.25) -> None:
    deadline = time.monotonic() + float(seconds)
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        ros_logic = slicer.util.getModuleLogic("ROS2")
        if ros_logic is not None:
            ros_logic.Spin()
        time.sleep(0.01)


def _matrix_copy(matrix):
    result = vtk.vtkMatrix4x4()
    result.DeepCopy(matrix)
    return result


def _vector(matrix, column: int) -> tuple[float, float, float]:
    values = tuple(float(matrix.GetElement(row, column)) for row in range(3))
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 1.0e-12:
        raise ValueError("pose rotation column is degenerate")
    return tuple(value / norm for value in values)


def _dot(first, second) -> float:
    return sum(float(a) * float(b) for a, b in zip(first, second))


def _cross(first, second) -> tuple[float, float, float]:
    return (
        float(first[1]) * float(second[2]) - float(first[2]) * float(second[1]),
        float(first[2]) * float(second[0]) - float(first[0]) * float(second[2]),
        float(first[0]) * float(second[1]) - float(first[1]) * float(second[0]),
    )


def _norm(vector) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in vector))


def _normalize(vector) -> tuple[float, float, float]:
    length = _norm(vector)
    if length <= 1.0e-12:
        raise ValueError("zero-length vector")
    return tuple(float(value) / length for value in vector)


def _pose_components(actual, expected) -> dict[str, float]:
    actual_rows = bridge._matrix4_rows(actual)
    expected_rows = bridge._matrix4_rows(expected)
    position_error = math.sqrt(
        sum(
            (float(actual_rows[row][3]) - float(expected_rows[row][3])) ** 2
            for row in range(3)
        )
    )
    actual_axis = _normalize(tuple(actual_rows[row][2] for row in range(3)))
    expected_axis = _normalize(tuple(expected_rows[row][2] for row in range(3)))
    axis_cosine = max(-1.0, min(1.0, _dot(actual_axis, expected_axis)))
    axis_error = math.degrees(math.acos(axis_cosine))

    # The axial component is reported separately from the tool-axis direction
    # component.  Project the actual X column into the requested axis plane so
    # a small axis-direction residual does not masquerade as a roll solution.
    expected_x = _normalize(tuple(expected_rows[row][0] for row in range(3)))
    actual_x = _normalize(tuple(actual_rows[row][0] for row in range(3)))
    projected_x = tuple(
        actual_x[index] - axis_cosine * expected_axis[index] for index in range(3)
    )
    if _norm(projected_x) <= 1.0e-12:
        axial_roll_error = None
    else:
        projected_x = _normalize(projected_x)
        sine = _dot(expected_axis, _cross(expected_x, projected_x))
        cosine = max(-1.0, min(1.0, _dot(expected_x, projected_x)))
        axial_roll_error = math.degrees(math.atan2(sine, cosine))

    _, full_orientation_error = bridge._pose_residual_mm_degrees(actual, expected)
    result: dict[str, float] = {
        "position_residual_mm": float(position_error),
        "drilling_axis_angular_residual_deg": float(axis_error),
        "full_orientation_residual_deg": float(full_orientation_error),
    }
    if axial_roll_error is not None:
        result["axial_roll_residual_deg"] = float(axial_roll_error)
    return result


def _collision_pairs(robot_node, positions: dict[str, float]) -> list[list[str]]:
    values = bridge.joint_si_vector(positions)
    encoded = robot_node.GetMoveItCollidingBodyPairs(
        bridge.ROS2_PLANNING_GROUP,
        values,
    )
    result: list[list[str]] = []
    for value in encoded:
        text = str(value)
        if "\t" in text:
            result.append([str(part) for part in text.split("\t", 1)])
        else:
            result.append([text])
    return result


def _joint_limit_margins(robot_node, positions: dict[str, float]):
    try:
        names = [str(value) for value in robot_node.GetJoints()]
        lower = [float(value) for value in robot_node.GetJointLowerPositionLimits()]
        upper = [float(value) for value in robot_node.GetJointUpperPositionLimits()]
    except Exception as exc:
        return {"error": str(exc), "minimum_margin": None, "per_joint": {}}
    by_name = {
        name: (lower[index], upper[index])
        for index, name in enumerate(names)
        if index < len(lower) and index < len(upper)
    }
    per_joint = {}
    finite_margins = []
    for name in bridge.ROS2_JOINT_SI_ORDER:
        bounds = by_name.get(name)
        value = float(positions[name])
        if bounds is None:
            per_joint[name] = {"value": value, "lower": None, "upper": None, "margin": None}
            continue
        minimum, maximum = bounds
        margin = min(value - minimum, maximum - value)
        if math.isfinite(margin):
            finite_margins.append(float(margin))
        per_joint[name] = {
            "value": value,
            "lower": minimum if math.isfinite(minimum) else None,
            "upper": maximum if math.isfinite(maximum) else None,
            "margin": float(margin) if math.isfinite(margin) else None,
        }
    return {
        "minimum_margin": min(finite_margins) if finite_margins else None,
        "per_joint": per_joint,
    }


def _authoritative_fk(motion_node, positions: dict[str, float]):
    values = bridge.joint_si_vector(positions)
    matrix = motion_node.ComputeMoveItForwardKinematics(
        bridge.ROS2_PLANNING_GROUP,
        list(bridge.ROS2_JOINT_SI_ORDER),
        values,
        bridge.ROS2_TOOL_TCP_LINK,
        FK_TIMEOUT_SEC,
    )
    message = str(motion_node.GetLastForwardKinematicsMessage() or "")
    if not message.startswith("MoveIt FK returned"):
        return None, message or "MoveIt FK returned no authoritative pose."
    return _matrix_copy(matrix), message


def _ik_attempt(
    robot_node,
    motion_node,
    expected_pose_base,
    expected_pose_world,
    home_positions,
    *,
    roll_deg: float,
    avoid_collisions: bool,
) -> dict[str, object]:
    result: dict[str, object] = {
        "roll_deg": float(roll_deg),
        "avoid_collisions": bool(avoid_collisions),
        "ik_success": False,
        "joint_positions_si": None,
        "ik_message": "",
        "collision_status": "not_evaluated",
        "collision_pairs": [],
        "joint_limit_margins": None,
        "position_residual_mm": None,
        "drilling_axis_angular_residual_deg": None,
        "full_orientation_residual_deg": None,
        "axial_roll_residual_deg": None,
    }
    try:
        solution = robot_node.ComputeMoveItIK(
            expected_pose_base,
            bridge.ROS2_TOOL_TCP_LINK,
            bridge.joint_si_vector(home_positions),
            IK_TIMEOUT_SEC,
            bool(avoid_collisions),
        )
        values = [float(value) for value in solution]
    except Exception as exc:
        result["ik_message"] = f"MoveIt IK request failed: {exc}"
        return result
    if len(values) != len(bridge.ROS2_JOINT_SI_ORDER):
        result["ik_message"] = (
            "MoveIt IK returned "
            f"{len(values)} values; expected {len(bridge.ROS2_JOINT_SI_ORDER)}."
        )
        return result
    positions = bridge.canonicalize_planning_joint_positions(
        dict(zip(bridge.ROS2_JOINT_SI_ORDER, values))
    )
    result["ik_success"] = True
    result["joint_positions_si"] = positions
    result["ik_message"] = "MoveIt returned a five-joint IK solution."
    try:
        pairs = _collision_pairs(robot_node, positions)
        result["collision_pairs"] = pairs
        result["collision_status"] = "clear" if not pairs else "colliding"
    except Exception as exc:
        result["collision_status"] = "unavailable"
        result["collision_pairs"] = [[str(exc)]]
    result["joint_limit_margins"] = _joint_limit_margins(robot_node, positions)
    try:
        actual_pose, fk_message = _authoritative_fk(motion_node, positions)
        if actual_pose is None:
            result["ik_message"] += f" FK unavailable: {fk_message}"
        else:
            result.update(_pose_components(actual_pose, expected_pose_base))
            result["fk_message"] = fk_message
    except Exception as exc:
        result["ik_message"] += f" FK query failed: {exc}"
    # Keep the exact requested world XYZ/axis visible in the record without
    # using it as a second acceptance frame.
    result["requested_preentry_ras_mm"] = [
        float(expected_pose_world.GetElement(axis, 3)) for axis in range(3)
    ]
    result["requested_drilling_axis_ras"] = [
        float(expected_pose_world.GetElement(axis, 2)) for axis in range(3)
    ]
    return result


def _require_success(result, stage: str):
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
    package_issues = logic.step6PlanningPackageFreshnessIssues(parameter_node)
    jaw_issues = logic.step6CaseJawOpeningFreshnessIssues(parameter_node)
    home_issues = logic.taskHomeFreshnessIssues(parameter_node)
    migration_home_issues = tuple(
        issue for issue in home_issues if "different robot resources" in str(issue).lower()
    )
    blocking_home_issues = tuple(
        issue for issue in home_issues if issue not in migration_home_issues
    )
    task_issues = logic.confirmedTaskFreshnessIssues(parameter_node)
    if package_issues or jaw_issues or blocking_home_issues:
        raise RuntimeError(
            "restored x4 prerequisites are stale: "
            + " | ".join(
                " ".join(group)
                for group in (package_issues, jaw_issues, blocking_home_issues)
                if group
            )
        )
    if not parameter_node.robotBaseMountLocked:
        raise RuntimeError("restored x4 robot base is not provisionally locked")

    _require_success(facade.loadRobot(), "load local robot")
    connection = facade.connect(open_motion_module=False)
    if not connection.success:
        if (
            connection.code != "task_home_scene_invalid_runtime_connected"
            or not facade.capabilities().connected
        ):
            raise RuntimeError(f"connect ROS/MoveIt: {connection.message}")
        _require_success(facade.saveTaskHome(), "save remediated Task Home")
        _require_success(facade.applyTaskHome(), "validate remediated Task Home")
        _require_success(facade.confirmTask(), "confirm remediated task")
    if not facade.taskHomeRuntimeValidated(parameter_node):
        _require_success(facade.saveTaskHome(), "save migrated Task Home")
        _require_success(facade.applyTaskHome(), "apply migrated Task Home")
    if not facade.workspaceRuntimeValidated(parameter_node):
        _require_success(facade.generateWorkspaceCloud(), "regenerate workspace")
        _require_success(facade.reviewAssistedLimits(), "review regenerated limits")
    if task_issues or logic.confirmedTaskRecord(parameter_node) is None:
        _require_success(facade.confirmTask(), "reconfirm restored task")

    snapshot = logic.confirmedTaskRecord(parameter_node)
    if snapshot is None:
        raise RuntimeError("x4 confirmed task snapshot is unavailable")
    robot_node = bridge.find_ros2_robot_by_name(bridge.ROS2_ROBOT_NAME)
    motion_logic = bridge.get_motion_control_logic()
    if robot_node is None or motion_logic is None:
        raise RuntimeError("connected MoveIt robot or motion logic is unavailable")
    motion_parameter = motion_logic.getParameterNode()
    motion_node = slicer.mrmlScene.GetNodeByID(motion_parameter.motionControlNodeID)
    if motion_node is None:
        raise RuntimeError("MoveIt motion-control node is unavailable")

    pre_entry, entry = logic.step6ApproachPoints(parameter_node)
    target = tuple(float(value) for value in snapshot.target_ras_mm)
    entry = tuple(float(value) for value in entry)
    pre_entry = tuple(float(value) for value in pre_entry)
    axis = _normalize(tuple(target[index] - entry[index] for index in range(3)))

    # Start with the Entry->Target frame so the requested drill axis does not
    # inherit any numerical direction change from the short PreEntry segment.
    axis_pose = bridge.tool_pose_matrices_world_mm(
        entry,
        target,
        2,
        axial_roll_start_deg=0.0,
        axial_roll_end_deg=0.0,
    )[0]
    base_transform = parameter_node.robotBaseTransform
    if base_transform is None:
        raise RuntimeError("locked robot base transform is unavailable")
    home_record = logic.taskHomeRecord(parameter_node)
    if home_record is None:
        raise RuntimeError("Task Home record is unavailable")
    home_positions = dict(
        zip(home_record.joint_names, home_record.joint_positions_si)
    )
    collision_aware_attempts = []
    for roll_deg in ROLLS_DEG:
        world_pose = _matrix_copy(axis_pose)
        for index, value in enumerate(pre_entry):
            world_pose.SetElement(index, 3, float(value))
        # Rebuild the roll at the requested angle while preserving the exact
        # Entry->Target +Z axis and exact PreEntry XYZ.
        world_pose = bridge.tool_pose_matrices_world_mm(
            entry,
            target,
            2,
            axial_roll_start_deg=roll_deg,
            axial_roll_end_deg=roll_deg,
        )[0]
        for index, value in enumerate(pre_entry):
            world_pose.SetElement(index, 3, float(value))
        expected_base = bridge._pose_matrices_world_to_base_mm(
            [world_pose], base_transform
        )[0]
        collision_aware_attempts.append(
            _ik_attempt(
                robot_node,
                motion_node,
                expected_base,
                world_pose,
                home_positions,
                roll_deg=roll_deg,
                avoid_collisions=True,
            )
        )

    collision_aware_success = [
        attempt for attempt in collision_aware_attempts if attempt["ik_success"]
    ]
    collision_free_attempts = []
    if not collision_aware_success:
        for roll_deg in ROLLS_DEG:
            world_pose = bridge.tool_pose_matrices_world_mm(
                entry,
                target,
                2,
                axial_roll_start_deg=roll_deg,
                axial_roll_end_deg=roll_deg,
            )[0]
            for index, value in enumerate(pre_entry):
                world_pose.SetElement(index, 3, float(value))
            expected_base = bridge._pose_matrices_world_to_base_mm(
                [world_pose], base_transform
            )[0]
            collision_free_attempts.append(
                _ik_attempt(
                    robot_node,
                    motion_node,
                    expected_base,
                    world_pose,
                    home_positions,
                    roll_deg=roll_deg,
                    avoid_collisions=False,
                )
            )

    return {
        "package": PACKAGE.name,
        "planning_group": bridge.ROS2_PLANNING_GROUP,
        "planning_joints": list(bridge.ROS2_JOINT_SI_ORDER),
        "tcp_link": bridge.ROS2_TOOL_TCP_LINK,
        "spindle_involved": False,
        "preentry_ras_mm": list(pre_entry),
        "entry_ras_mm": list(entry),
        "target_ras_mm": list(target),
        "entry_to_target_axis_ras": list(axis),
        "roll_sweep_deg": list(ROLLS_DEG),
        "collision_aware_attempts": collision_aware_attempts,
        "collision_aware_success_count": len(collision_aware_success),
        "collision_free_attempts": collision_free_attempts,
        "collision_free_success_count": sum(
            1 for attempt in collision_free_attempts if attempt["ik_success"]
        ),
        "interpretation": (
            "at_least_one_collision_aware_roll_reachable"
            if collision_aware_success
            else "no_collision_aware_roll_reachable"
        ),
        "hardware_execution_enabled": False,
    }


try:
    report = run()
    print("DENTOBOT_STEP6_PREENTRY_ROLL_DIAGNOSTIC_COMPLETE", flush=True)
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    bridge.disconnect_dentobot_motion_control([])
    bridge.shutdown_slicer_adapter()
    slicer.mrmlScene.Clear(0)
    slicer.app.processEvents()
    slicer.util.exit(0)
except Exception as exc:
    print(f"DENTOBOT_STEP6_PREENTRY_ROLL_DIAGNOSTIC_FAILED: {exc}", flush=True)
    try:
        bridge.disconnect_dentobot_motion_control([])
        bridge.shutdown_slicer_adapter()
    except Exception:
        pass
    slicer.util.exit(1)
