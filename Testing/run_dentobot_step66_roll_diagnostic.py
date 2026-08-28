"""Read-only reachability diagnostic for exact-case drilling axial roll.

Restores the operator x4 package, reconstructs the transient simulation stack,
plans Goal 1, and probes full Entry-to-Target Cartesian reachability from the
planned Entry state. It does not preview commands or expose execution.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import slicer


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
for path in (ROOT / "DENTOWorkflow/Resources/Python", ROOT / "DENTOWorkflow"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import DENTOROS2Bridge as bridge  # noqa: E402


PACKAGE = Path(
    "/workspace/data/Slicer_Saved/SampleStudy1/"
    "dentobot-case-step6x4.dentocase"
)
ROLLS_DEG = (0.0, 45.0, -45.0, 90.0, -90.0, 135.0, -135.0, 180.0)


def process_events(seconds: float = 0.25) -> None:
    deadline = time.monotonic() + float(seconds)
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        ros_logic = slicer.util.getModuleLogic("ROS2")
        if ros_logic is not None:
            ros_logic.Spin()
        time.sleep(0.01)


def require(result, stage: str):
    if not result.success:
        raise RuntimeError(f"{stage}: {result.message}")
    return result


def run() -> dict[str, object]:
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget._applyDENTOBOTGuiMode("legacy", persist=False)
    widget._openCaseBundle(PACKAGE)
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    parameter_node = widget._parameterNode
    logic = widget.logic
    facade = widget._robotWorkflowFacade
    require(facade.loadRobot(), "load local robot")
    connection = facade.connect(open_motion_module=False)
    if not connection.success:
        if (
            connection.code != "task_home_scene_invalid_runtime_connected"
            or not facade.capabilities().connected
        ):
            raise RuntimeError(f"connect: {connection.message}")
        require(facade.saveTaskHome(), "save remediated Task Home")
        require(facade.applyTaskHome(), "validate remediated Task Home")
        require(facade.confirmTask(), "confirm remediated task")
    snapshot = logic.confirmedTaskRecord(parameter_node)
    guard_ok, guard_message = facade._prepare_phase_guard(parameter_node, snapshot)
    if not guard_ok:
        raise RuntimeError(f"configure phase guard: {guard_message}")
    pre_entry, entry = logic.step6ApproachPoints(parameter_node)
    pre_entry_pose = bridge.tool_pose_matrices_world_mm(pre_entry, entry, 2)[0]
    ok, message, _goal = bridge.set_moveit_tcp_goal_matrix(pre_entry_pose)
    if not ok:
        raise RuntimeError(f"set pre-entry goal: {message}")
    ok, message, _positions = bridge.solve_moveit_tcp_goal()
    if not ok:
        raise RuntimeError(f"solve pre-entry IK: {message}")
    strict = bridge.plan_moveit_joint_goal()
    if not strict.success:
        raise RuntimeError(f"plan strict approach: {strict.message}")
    terminal = bridge.plan_moveit_cartesian_path(
        entry_ras_mm=pre_entry,
        target_ras_mm=entry,
        sample_count=max(3, int(parameter_node.robotMotionPlanSampleCount) // 2),
        base_transform=parameter_node.robotBaseTransform,
        avoid_collisions=False,
        minimum_fraction=0.99,
        start_joint_positions_si=strict.waypoint_joint_vectors_si[-1],
    )
    if not terminal.success or not terminal.waypoint_joint_vectors_si:
        raise RuntimeError(f"plan terminal contact: {terminal.message}")
    entry_state = terminal.waypoint_joint_vectors_si[-1]
    attempts = []
    for roll_deg in ROLLS_DEG:
        result = bridge.plan_moveit_cartesian_path(
            entry_ras_mm=snapshot.entry_ras_mm,
            target_ras_mm=snapshot.target_ras_mm,
            sample_count=int(parameter_node.robotMotionPlanSampleCount),
            base_transform=parameter_node.robotBaseTransform,
            avoid_collisions=False,
            minimum_fraction=0.99,
            start_joint_positions_si=entry_state,
            axial_roll_start_deg=0.0,
            axial_roll_end_deg=roll_deg,
        )
        attempts.append(
            {
                "rollDeg": roll_deg,
                "success": result.success,
                "fraction": result.fraction,
                "waypointCount": len(result.waypoint_joint_vectors_si),
                "message": result.message,
            }
        )
        if result.success:
            break
    return {
        "package": PACKAGE.name,
        "attempts": attempts,
        "fullPathFound": any(item["success"] for item in attempts),
        "hardwareExecutionEnabled": False,
    }


try:
    report = run()
    print("DENTOBOT_STEP66_ROLL_DIAGNOSTIC_COMPLETE", flush=True)
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    bridge.disconnect_dentobot_motion_control([])
    bridge.shutdown_slicer_adapter()
    slicer.mrmlScene.Clear(0)
    slicer.app.processEvents()
    # This is an evidence probe, not an acceptance test.  Completing every
    # configured roll attempt is success even when the current base placement
    # proves unreachable; fullPathFound carries that engineering result.
    slicer.util.exit(0)
except Exception as exc:
    print(f"DENTOBOT_STEP66_ROLL_DIAGNOSTIC_FAILED: {exc}", flush=True)
    try:
        bridge.disconnect_dentobot_motion_control([])
        bridge.shutdown_slicer_adapter()
    except Exception:
        pass
    slicer.util.exit(1)
