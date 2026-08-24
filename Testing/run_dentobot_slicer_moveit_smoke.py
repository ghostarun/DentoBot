"""Headless Slicer acceptance test for DENTOBOT ROS/MoveIt integration."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import slicer
import vtk

ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
MODULE = ROOT / "DENTOWorkflow"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))
if str(MODULE) not in sys.path:
    sys.path.insert(0, str(MODULE))

from DENTOROS2Bridge import (  # noqa: E402
    ROS2_JOINT_SI_ORDER,
    apply_joint_positions_si_to_motion_control,
    connect_dentobot_motion_control,
    disconnect_dentobot_motion_control,
    ensure_slicer_ros2_runtime,
    get_motion_control_logic,
    plan_moveit_cartesian_path,
    shutdown_slicer_adapter,
)
from DENTORobotWorkflowFacade import DENTORobotWorkflowFacade  # noqa: E402
from DENTOWorkflow import DENTOWorkflowLogic  # noqa: E402


def wait_until(predicate, timeout_sec: float):
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        ros_logic = slicer.util.getModuleLogic("ROS2")
        if ros_logic is not None:
            ros_logic.Spin()
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    return None


def run() -> dict[str, object]:
    ready = wait_until(
        lambda: ensure_slicer_ros2_runtime(require_stack=True)[0],
        15.0,
    )
    if not ready:
        raise RuntimeError(ensure_slicer_ros2_runtime(require_stack=True)[1])

    workflow_logic = DENTOWorkflowLogic()
    parameter_node = workflow_logic.getParameterNode()
    skull, mandible, phantom_models = workflow_logic.createOrUpdateDraftPhantom()
    parameter_node.draftPhantomSkullModel = skull
    parameter_node.draftPhantomMandibleModel = mandible
    landmarks = workflow_logic.createOrResetDraftJawLandmarks(None)
    for point in workflow_logic.draftPhantomExampleLandmarksWorldRas():
        landmarks.AddControlPointWorld(vtk.vtkVector3d(*point))
    parameter_node.draftJawLandmarks = landmarks
    jaw_transform, gap_line, jaw_summary = workflow_logic.createOrUpdateDraftJawOpening(
        mandible,
        landmarks,
        None,
        None,
        40.0,
    )
    parameter_node.draftJawTransform = jaw_transform
    parameter_node.draftJawGapLine = gap_line

    base = workflow_logic.ensureRobotBaseTransform(None)
    parameter_node.robotBaseTransform = base
    forehead = workflow_logic.draftPhantomNativePointToWorldRas(
        workflow_logic.draftPhantomExampleForeheadPlaneNativeRas()
    )
    mount_plane = workflow_logic.createOrResetRobotMountPlane(None, base)
    mount_plane.SetOriginWorld(tuple(forehead))
    mount_plane.SetNormalWorld((0.0, -1.0, 0.0))
    workflow_logic.snapRobotBaseToPlane(base, mount_plane)
    parameter_node.robotMountPlane = mount_plane
    robot, error = connect_dentobot_motion_control(
        base,
        hide_mrml_robot=False,
        mrml_robot_models=[],
        open_motion_module=False,
        start_stack_if_needed=False,
    )
    if robot is None:
        raise RuntimeError(error)
    robot_facade = DENTORobotWorkflowFacade(
        workflow_logic,
        lambda: parameter_node,
    )
    capabilities = robot_facade.capabilities()
    if not (
        capabilities.simulation_only
        and capabilities.connected
        and capabilities.move_group_available
        and capabilities.ik_available
        and capabilities.collision_check_available
        and capabilities.single_joint_state_source
        and capabilities.planning_group == "dentobot_arm"
        and capabilities.tcp_link == "dentobot_tool_tcp"
    ):
        raise RuntimeError(f"unexpected robot façade capabilities: {capabilities}")
    root_tip = robot.FindRootAndTipLinks()
    if not root_tip or root_tip[0] != "base_link" or root_tip[-1] != "dentobot_tool_tcp":
        raise RuntimeError(f"unexpected robot chain endpoints: {root_tip}")

    live_root = robot.GetNthNodeReference("lookup", 0)
    goal_root = robot.GetNthNodeReference("goal_transform", 0)
    if live_root is None or goal_root is None:
        raise RuntimeError("live or goal robot root transform is missing")
    if live_root.GetTransformNodeID() != base.GetID():
        raise RuntimeError("live robot root is not parented to the Step 6 base")
    if goal_root.GetTransformNodeID() != base.GetID():
        raise RuntimeError("goal robot root is not parented to the Step 6 base")
    live_world = vtk.vtkMatrix4x4()
    goal_world = vtk.vtkMatrix4x4()
    live_root.GetMatrixTransformToWorld(live_world)
    goal_root.GetMatrixTransformToWorld(goal_world)
    root_world_error = max(
        abs(live_world.GetElement(row, column) - goal_world.GetElement(row, column))
        for row in range(4)
        for column in range(4)
    )
    if root_world_error > 1e-6:
        raise RuntimeError(
            f"current and goal roots do not overlap at zero: {root_world_error}"
        )

    motion_widget = slicer.util.getModuleWidget("ROS2MotionControl")
    if motion_widget is None:
        raise RuntimeError("ROS2MotionControl widget is unavailable")
    if motion_widget.ui.moveGroupExistsCheckBox.enabled:
        raise RuntimeError("MoveIt readiness checkbox is still operator-editable")
    if "detected" not in motion_widget.ui.moveGroupExistsCheckBox.text.lower():
        raise RuntimeError("MoveIt readiness is not labelled as detected")
    if motion_widget.ui.planGroupComboBox.currentText != "dentobot_arm":
        raise RuntimeError("DENTOBOT planning group is not selected")
    selected_tcp = motion_widget.ui.endEffectorLinkComboBox.itemData(
        motion_widget.ui.endEffectorLinkComboBox.currentIndex
    )
    if selected_tcp != "dentobot_tool_tcp":
        raise RuntimeError(f"DENTOBOT TCP is not exposed: {selected_tcp}")
    if motion_widget.ui.executeButton.visible or motion_widget.ui.executeButton.enabled:
        raise RuntimeError("Execute must remain unavailable in simulation-only mode")
    motion_status = getattr(motion_widget, "_dentobotMotionStatusLabel", None)
    if motion_status is None or "plan/preview only" not in motion_status.text:
        raise RuntimeError("plan-only MoveIt status is not visible")

    command_values = [0.1, 0.02, 0.2, 0.02, 0.1, 0.0]
    command = dict(zip(ROS2_JOINT_SI_ORDER, command_values))
    applied, apply_error = apply_joint_positions_si_to_motion_control(command)
    if not applied:
        raise RuntimeError(apply_error)
    motion_logic = get_motion_control_logic()

    def commanded_joint_state():
        values = motion_logic.GetCurrentJointState(list(ROS2_JOINT_SI_ORDER))
        if not values or len(values) != len(command_values):
            return None
        if any(
            abs(actual - expected) > 1e-5
            for actual, expected in zip(values, command_values)
        ):
            return None
        return values

    observed = wait_until(
        commanded_joint_state,
        10.0,
    )
    if not observed or any(
        abs(actual - expected) > 1e-5
        for actual, expected in zip(observed, command_values)
    ):
        raise RuntimeError(f"Motion Control joint state mismatch: {observed}")

    # Use the collision-cleared manual state as the seed for generic 3D IK.
    motion_widget.onCurrentStateButton()
    motion_widget.enterControlMode()
    if motion_widget.fromtransform is None:
        raise RuntimeError("3D Control did not create the TCP probe")
    original_probe = vtk.vtkMatrix4x4()
    motion_widget.fromtransform.GetMatrixTransformToParent(original_probe)
    ik_solution = None
    ik_offset_world_mm = None
    for offset in (
        (1.0, 0.0, 0.0),
        (-1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, -1.0),
    ):
        probe_matrix = vtk.vtkMatrix4x4()
        probe_matrix.DeepCopy(original_probe)
        for axis in range(3):
            probe_matrix.SetElement(
                axis,
                3,
                probe_matrix.GetElement(axis, 3) + offset[axis],
            )
        motion_widget.fromtransform.SetMatrixTransformToParent(probe_matrix)
        ik_result = robot_facade.solveIk()
        if ik_result.success:
            ik_solution = ik_result.payload
            ik_offset_world_mm = offset
            break
    if not ik_solution:
        raise RuntimeError("generic 3D Control failed all 1 mm MoveIt IK targets")
    if "IK solution found" not in motion_status.text:
        raise RuntimeError("successful IK result was not shown in the Motion Control UI")
    facade_plan = robot_facade.planToGoal()
    if not facade_plan.success:
        raise RuntimeError(facade_plan.message)
    if motion_widget.trajectoryData is None:
        raise RuntimeError("façade MoveIt Plan returned no trajectory")
    generic_points = motion_widget.trajectoryData.GetJointTrajectory().GetPoints()
    if not generic_points:
        raise RuntimeError("generic MoveIt Plan returned an empty trajectory")
    if "Plan ready" not in motion_status.text:
        raise RuntimeError("successful plan result was not shown in the Motion Control UI")
    if motion_widget.ui.executeButton.visible or motion_widget.ui.executeButton.enabled:
        raise RuntimeError("Execute became available after generic planning")
    motion_widget.exitControlMode()
    obstacle_count = workflow_logic.syncStep6MoveItPlanningScene(parameter_node)
    original_base = vtk.vtkMatrix4x4()
    base.GetMatrixTransformToWorld(original_base)
    placement_nudge_mm = None
    initial_forehead_collision_rejected = False
    for direction in (1.0, -1.0):
        base.SetMatrixTransformToParent(original_base)
        for distance_mm in range(0, 101, 10):
            if distance_mm:
                workflow_logic.nudgeRobotBase(
                    base,
                    translationLocalMm=(0.0, 0.0, direction * 10.0),
                )
                obstacle_count = workflow_logic.syncStep6MoveItPlanningScene(
                    parameter_node
                )
            scene_ready_at = time.monotonic() + 0.35
            wait_until(lambda: time.monotonic() >= scene_ready_at, 0.5)
            applied, apply_error = apply_joint_positions_si_to_motion_control(command)
            if applied:
                placement_nudge_mm = direction * float(distance_mm)
                break
            if distance_mm == 0:
                initial_forehead_collision_rejected = True
        if placement_nudge_mm is not None:
            break
    if placement_nudge_mm is None:
        raise RuntimeError(
            "Fine base nudging did not find a collision-clear phantom placement"
        )

    parameter_node.robotWorkspaceSampleCount = 200
    workspace_model, workspace_report = workflow_logic.createOrUpdateRobotWorkspace(
        parameter_node
    )
    if workspace_report.accepted_count <= 0:
        raise RuntimeError("draft workspace explorer accepted no TCP samples")
    if workspace_model.GetTransformNodeID() != base.GetID():
        raise RuntimeError("workspace cloud is not parented to the Step 6 robot base")
    if workspace_model.GetAttribute("DENTOBOT.WorkspaceState") != "Current":
        raise RuntimeError("new workspace cloud is unexpectedly stale")
    if (
        workspace_model.GetPolyData() is None
        or workspace_model.GetPolyData().GetNumberOfPoints()
        != workspace_report.accepted_count
    ):
        raise RuntimeError("workspace model point count does not match its report")

    pose_root = vtk.vtkMatrix4x4()
    if robot.ComputeKDLFK(list(observed), pose_root, "dentobot_tool_tcp") is None:
        raise RuntimeError("SlicerROS2 KDL FK failed for dentobot_tool_tcp")
    entry = [pose_root.GetElement(row, 3) for row in range(3)]
    tool_z = [pose_root.GetElement(row, 2) for row in range(3)]
    target = [entry[index] + tool_z[index] for index in range(3)]
    plan = plan_moveit_cartesian_path(
        entry_ras_mm=entry,
        target_ras_mm=target,
        sample_count=3,
        base_transform=base,
        avoid_collisions=True,
        minimum_fraction=0.99,
    )
    if not plan.success:
        raise RuntimeError(plan.message)
    return {
        "robot_root": root_tip[0],
        "robot_tip": root_tip[-1],
        "joint_count": len(observed),
        "j2_m": observed[1],
        "j4_m": observed[3],
        "cartesian_fraction": plan.fraction,
        "trajectory_points": len(plan.waypoint_joint_vectors_si),
        "phantom_models": len(phantom_models),
        "incisor_gap_mm": jaw_summary["gapMm"],
        "planning_scene_obstacles": obstacle_count,
        "initial_forehead_collision_rejected": initial_forehead_collision_rejected,
        "collision_clear_base_nudge_mm": placement_nudge_mm,
        "base_snapped_to_forehead": True,
        "goal_root_matches_live_root": root_world_error <= 1e-6,
        "generic_ik_success": True,
        "generic_ik_offset_world_mm": ik_offset_world_mm,
        "generic_plan_points": len(generic_points),
        "facade_contract": True,
        "moveit_status_read_only": True,
        "selected_tcp": selected_tcp,
        "execution_enabled": False,
        "workspace_requested": workspace_report.requested_count,
        "workspace_accepted": workspace_report.accepted_count,
        "workspace_self_rejected": workspace_report.self_collision_rejections,
        "workspace_environment_rejected": workspace_report.environment_rejections,
        "workspace_aabb_exclusions": workspace_report.excluded_aabb_pairs,
    }


try:
    report = run()
    print(json.dumps(report, indent=2, sort_keys=True))
    disconnect_dentobot_motion_control([])
    shutdown_slicer_adapter()
    slicer.mrmlScene.Clear(0)
    slicer.app.processEvents()
    slicer.util.exit(0)
except Exception as exc:
    print(f"DENTOBOT_SLICER_MOVEIT_SMOKE_FAILED: {exc}", file=sys.stderr)
    slicer.util.exit(1)
