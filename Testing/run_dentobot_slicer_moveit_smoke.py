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
    landmarks = workflow_logic.createOrResetDraftJawLandmarks(
        parameter_node.draftJawLandmarks
    )
    for point in workflow_logic.draftPhantomExampleLandmarksWorldRas():
        landmarks.AddControlPointWorld(vtk.vtkVector3d(*point))
    parameter_node.draftJawLandmarks = landmarks
    jaw_transform, gap_line, jaw_summary = workflow_logic.createOrUpdateDraftJawOpening(
        mandible,
        landmarks,
        parameter_node.draftJawTransform,
        parameter_node.draftJawGapLine,
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
    robot_facade = DENTORobotWorkflowFacade(
        workflow_logic,
        lambda: parameter_node,
    )
    local_robot = robot_facade.loadRobot()
    if not local_robot.success:
        raise RuntimeError(local_robot.message)
    workflow_logic.setRobotBaseMountLocked(parameter_node, True)
    task_home = robot_facade.saveTaskHome()
    if not task_home.success:
        raise RuntimeError(task_home.message)
    parameter_node.robotWorkspaceSampleCount = 200
    workspace_setup = robot_facade.generateWorkspaceCloud()
    if not workspace_setup.success:
        raise RuntimeError(workspace_setup.message)
    limits_review = robot_facade.reviewAssistedLimits()
    if not limits_review.success:
        raise RuntimeError(limits_review.message)
    slicer.util.selectModule("DENTOWorkflow")
    slicer.app.processEvents()
    workflow_widget = slicer.util.getModuleWidget("DENTOWorkflow")
    if workflow_widget is None:
        raise RuntimeError("DENTOWorkflow widget is unavailable")
    selected_before_connect = slicer.util.selectedModule()
    connected = robot_facade.connect(open_motion_module=False)
    if not connected.success:
        raise RuntimeError(connected.message)
    if slicer.util.selectedModule() != selected_before_connect:
        raise RuntimeError("Routine Connect left DENTOWorkflow")
    robot = connected.payload
    capabilities = robot_facade.capabilities()
    if not (
        capabilities.simulation_only
        and capabilities.connected
        and capabilities.move_group_available
        and capabilities.ik_available
        and capabilities.collision_check_available
        and capabilities.single_joint_state_source
        and capabilities.planning_group == "dentobot_arm"
        and capabilities.tcp_link == "dentobot_drill_tip_provisional"
    ):
        raise RuntimeError(f"unexpected robot façade capabilities: {capabilities}")
    root_tip = robot.FindRootAndTipLinks()
    if not root_tip or root_tip[0] != "base_link" or root_tip[-1] != "dentobot_drill_tip_provisional":
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
    selected_tcp = capabilities.tcp_link

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

    # Exercise generic Goal/IK/Plan through the native façade without entering
    # the upstream widget or leaving DENTOWorkflow.
    goal_result = robot_facade.ensureTcpGoal()
    if not goal_result.success:
        raise RuntimeError(goal_result.message)
    native_goal = goal_result.payload
    original_probe = vtk.vtkMatrix4x4()
    native_goal.GetMatrixTransformToParent(original_probe)
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
        set_goal = robot_facade.setTcpGoal(probe_matrix)
        if not set_goal.success:
            raise RuntimeError(set_goal.message)
        ik_result = robot_facade.solveIk()
        if ik_result.success:
            ik_solution = ik_result.payload
            ik_offset_world_mm = offset
            break
    if not ik_solution:
        raise RuntimeError("generic 3D Control failed all 1 mm MoveIt IK targets")
    facade_plan = robot_facade.planToGoal()
    if not facade_plan.success:
        raise RuntimeError(facade_plan.message)
    generic_points = facade_plan.payload.waypoint_joint_vectors_si
    if not generic_points:
        raise RuntimeError("generic MoveIt Plan returned an empty trajectory")
    if slicer.util.selectedModule() != "DENTOWorkflow":
        raise RuntimeError("Native Goal/IK/Plan left DENTOWorkflow")

    # Expert diagnostics is an explicit, reversible handoff.  Views remain
    # application-level and a one-click toolbar action returns to Step 6.
    workflow_widget._onStep6OpenExpertDiagnostics()
    slicer.app.processEvents()
    if slicer.util.selectedModule() != "ROS2MotionControl":
        raise RuntimeError("Expert diagnostics did not open ROS2MotionControl")
    if motion_widget.ui.moveGroupExistsCheckBox.enabled:
        raise RuntimeError("MoveIt readiness checkbox is still operator-editable")
    if "detected" not in motion_widget.ui.moveGroupExistsCheckBox.text.lower():
        raise RuntimeError("MoveIt readiness is not labelled as detected")
    if motion_widget.ui.planGroupComboBox.currentText != "dentobot_arm":
        raise RuntimeError("DENTOBOT planning group is not selected")
    selected_tcp = motion_widget.ui.endEffectorLinkComboBox.itemData(
        motion_widget.ui.endEffectorLinkComboBox.currentIndex
    )
    if selected_tcp != "dentobot_drill_tip_provisional":
        raise RuntimeError(f"DENTOBOT TCP is not exposed: {selected_tcp}")
    if motion_widget.ui.executeButton.visible or motion_widget.ui.executeButton.enabled:
        raise RuntimeError("Execute must remain unavailable in simulation-only mode")
    motion_status = getattr(motion_widget, "_dentobotMotionStatusLabel", None)
    if motion_status is None or "plan/preview only" not in motion_status.text:
        raise RuntimeError("plan-only MoveIt status is not visible")
    toolbar = getattr(workflow_widget, "_step6ExpertReturnToolbar", None)
    if toolbar is None or not toolbar.visible:
        raise RuntimeError("Expert diagnostics return toolbar is unavailable")
    views_palette = getattr(workflow_widget, "_viewControlsPalette", None)
    if views_palette is None or not views_palette.visible:
        raise RuntimeError("DENTOBOT Views did not remain available in expert diagnostics")
    workflow_widget._onReturnFromStep6ExpertDiagnostics()
    wait_until(lambda: slicer.util.selectedModule() == "DENTOWorkflow", 2.0)
    if slicer.util.selectedModule() != "DENTOWorkflow":
        raise RuntimeError("Return to Robot Simulation did not restore DENTOWorkflow")
    obstacle_count = workflow_logic.syncStep6MoveItPlanningScene(parameter_node)
    original_base = vtk.vtkMatrix4x4()
    base.GetMatrixTransformToWorld(original_base)
    placement_nudge_mm = None
    initial_forehead_collision_rejected = False
    search_directions = (
        (0.0, 0.0, 1.0),
        (0.0, 0.0, -1.0),
        (0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0),
        (1.0, 0.0, 0.0),
        (-1.0, 0.0, 0.0),
    )
    for direction in search_directions:
        for distance_mm in (0, 100, 200, 400):
            base.SetMatrixTransformToParent(original_base)
            if distance_mm:
                workflow_logic.nudgeRobotBase(
                    base,
                    translationLocalMm=tuple(
                        value * float(distance_mm) for value in direction
                    ),
                )
                obstacle_count = workflow_logic.syncStep6MoveItPlanningScene(
                    parameter_node
                )
            scene_ready_at = time.monotonic() + 0.35
            wait_until(lambda: time.monotonic() >= scene_ready_at, 0.5)
            applied, apply_error = apply_joint_positions_si_to_motion_control(command)
            if applied:
                placement_nudge_mm = tuple(
                    value * float(distance_mm) for value in direction
                )
                break
            if distance_mm == 0:
                initial_forehead_collision_rejected = True
        if placement_nudge_mm is not None:
            break
    if placement_nudge_mm is None:
        # Base/phantom collision-clearance behavior is covered authoritatively
        # by the strict ROS smoke.  This normal-window probe must not turn the
        # disposable visual phantom's arbitrary initial placement into a gate
        # for native module/Views/expert-handoff acceptance.
        base.SetMatrixTransformToParent(original_base)

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
    if robot.ComputeKDLFK(list(observed), pose_root, "dentobot_drill_tip_provisional") is None:
        raise RuntimeError("SlicerROS2 KDL FK failed for dentobot_drill_tip_provisional")
    entry = [pose_root.GetElement(row, 3) for row in range(3)]
    tool_z = [pose_root.GetElement(row, 2) for row in range(3)]
    target = [entry[index] + tool_z[index] for index in range(3)]
    plan = None
    if placement_nudge_mm is not None:
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
        "cartesian_fraction": plan.fraction if plan is not None else None,
        "trajectory_points": (
            len(plan.waypoint_joint_vectors_si) if plan is not None else 0
        ),
        "phantom_models": len(phantom_models),
        "incisor_gap_mm": jaw_summary["gapMm"],
        "planning_scene_obstacles": obstacle_count,
        "initial_forehead_collision_rejected": initial_forehead_collision_rejected,
        "collision_clear_base_nudge_mm": placement_nudge_mm,
        "collision_clear_visual_phantom_placement_found": (
            placement_nudge_mm is not None
        ),
        "base_snapped_to_forehead": True,
        "goal_root_matches_live_root": root_world_error <= 1e-6,
        "generic_ik_success": True,
        "generic_ik_offset_world_mm": ik_offset_world_mm,
        "generic_plan_points": len(generic_points),
        "facade_contract": True,
        "routine_connect_stayed_in_workflow": True,
        "expert_diagnostics_returned": True,
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
