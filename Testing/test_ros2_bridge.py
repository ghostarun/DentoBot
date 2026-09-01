"""Pure tests for the thin, externally owned DENTOBOT ROS adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOROS2Bridge import (  # noqa: E402
    CARTESIAN_START_ORIENTATION_TOLERANCE_DEG,
    CARTESIAN_START_POSITION_TOLERANCE_MM,
    ROS2_JOINT_COMMAND_STATUS_SCHEMA,
    ROS2_JOINT_SI_ORDER,
    ROS2_PLANNING_GROUP,
    ROS2_SIMULATION_STATUS_SCHEMA,
    ROS2_TASK_GUARD_INITIAL_SEQUENCE,
    ROS2_TASK_JOINT_STATUS_SCHEMA,
    ROS2_TOOL_TCP_LINK,
    RuntimeState,
    _pose_residual_mm_degrees,
    _rigid_pose_world_to_reference_rows,
    _trajectory_motion_summary,
    align_ros2_goal_to_base_transform,
    align_ros2_robot_to_base_transform,
    joint_si_vector,
    parse_joint_command_status,
    parse_simulation_status,
    parse_task_joint_status,
)


def status_payload(**overrides) -> str:
    data = {
        "schema": ROS2_SIMULATION_STATUS_SCHEMA,
        "mode": "simulation_only",
        "description_ready": True,
        "planning_ready": True,
        "joint_state_publisher_count": 1,
        "ready": True,
        "reason": "",
    }
    data.update(overrides)
    return json.dumps(data)


def test_ready_status_requires_simulation_mode_and_one_joint_source():
    ready = parse_simulation_status(status_payload())
    assert ready.state == RuntimeState.READY
    assert ready.ready
    duplicate = parse_simulation_status(
        status_payload(joint_state_publisher_count=2, ready=False)
    )
    assert duplicate.state != RuntimeState.READY
    hardware = parse_simulation_status(status_payload(mode="hardware"))
    assert hardware.state == RuntimeState.ERROR


def test_status_schema_mismatch_is_explicit_error():
    status = parse_simulation_status(status_payload(schema="future.schema"))
    assert status.state == RuntimeState.ERROR
    assert "schema" in status.reason.lower()


def test_joint_vector_has_one_explicit_urdf_order():
    positions = {name: float(index) for index, name in enumerate(ROS2_JOINT_SI_ORDER)}
    assert joint_si_vector(positions) == [0.0, 1.0, 2.0, 3.0, 4.0, 0.0]


def test_joint_guard_status_parses_accepted_state_and_clearances():
    payload = json.dumps(
        {
            "schema": ROS2_JOINT_COMMAND_STATUS_SCHEMA,
            "mode": "simulation_only",
            "accepted": False,
            "reason": "Self-clearance is 3.00 mm",
            "requested_positions": [0.1, 0.02, 0.2, 0.02, 0.1, 0.0],
            "accepted_positions": [0.0] * 6,
            "checked_samples": 20,
            "minimum_clearance_m": 0.005,
            "minimum_self_distance_m": 0.003,
            "minimum_world_distance_m": None,
            "first_body": "link-3",
            "second_body": "link-5",
            "world_object_count": 0,
        }
    )
    status = parse_joint_command_status(payload)
    assert status.accepted is False
    assert status.minimum_self_distance_m == 0.003
    assert status.accepted_positions == (0.0,) * 6
    assert (status.first_body, status.second_body) == ("link-3", "link-5")


def test_joint_guard_status_rejects_wrong_mode_and_vector_length():
    base = {
        "schema": ROS2_JOINT_COMMAND_STATUS_SCHEMA,
        "mode": "simulation_only",
        "accepted": True,
        "reason": "accepted",
        "requested_positions": [0.0] * 6,
        "accepted_positions": [0.0] * 6,
    }
    wrong_mode = dict(base, mode="hardware")
    try:
        parse_joint_command_status(json.dumps(wrong_mode))
    except ValueError as exc:
        assert "simulation_only" in str(exc)
    else:
        raise AssertionError("hardware status was accepted")
    malformed = dict(base, requested_positions=[0.0] * 5)
    try:
        parse_joint_command_status(json.dumps(malformed))
    except ValueError as exc:
        assert "six" in str(exc)
    else:
        raise AssertionError("five-joint status was accepted")


def test_task_guard_status_requires_and_preserves_transient_session_identity():
    payload = {
        "schema": ROS2_TASK_JOINT_STATUS_SCHEMA,
        "mode": "simulation_only",
        "accepted": True,
        "reason": "accepted",
        "task_fingerprint": "immutable-task",
        "guard_session_id": "transient-session",
        "phase": "approach",
        "sequence": 1,
        "requested_positions": [0.0] * 6,
        "accepted_positions": [0.0] * 6,
        "exploratory_tool_contact_suppressed": True,
        "suppressed_tool_contact_sample_count": 3,
    }
    status = parse_task_joint_status(json.dumps(payload))
    assert status.guard_session_id == "transient-session"
    assert status.exploratory_tool_contact_suppressed
    assert status.suppressed_tool_contact_sample_count == 3
    payload["guard_session_id"] = ""
    try:
        parse_task_joint_status(json.dumps(payload))
    except ValueError as exc:
        assert "guard session" in str(exc)
    else:
        raise AssertionError("task status without a guard session was accepted")


def test_moveit_frame_contract_constants():
    assert ROS2_PLANNING_GROUP == "dentobot_arm"
    assert ROS2_TOOL_TCP_LINK == "dentobot_drill_tip_provisional"
    assert ROS2_TASK_GUARD_INITIAL_SEQUENCE == 1
    assert CARTESIAN_START_POSITION_TOLERANCE_MM == 0.25
    assert CARTESIAN_START_ORIENTATION_TOLERANCE_DEG == 0.5


def test_joint_goal_planning_waits_for_a_stable_scene_and_retries_boundedly():
    source = (HELPERS / "DENTOROS2Bridge.py").read_text(encoding="utf-8")
    planner = source.split("def plan_moveit_joint_goal", 1)[1].split(
        "def sync_moveit_obstacle_polydata", 1
    )[0]
    assert "RefreshMoveItPlanningScene" in planner
    assert "ROS2_MOVEIT_PLANNING_SCENE_SETTLE_SEC" in planner
    assert "ROS2_MOVEIT_JOINT_PLAN_ATTEMPTS" in planner
    assert "for attempt in range" in planner


def test_exploratory_cartesian_planning_uses_bounded_finer_ik_steps():
    source = (HELPERS / "DENTOROS2Bridge.py").read_text(encoding="utf-8")
    planner = source.split("def plan_moveit_cartesian_path", 1)[1].split(
        "def _dentobot_native_motion_context", 1
    )[0]
    assert "ROS2_CARTESIAN_EEF_STEP_ATTEMPTS_M" in planner
    assert "if avoid_collisions" in planner
    assert "for eef_step_m in eef_steps" in planner
    assert "candidate_fraction >= fraction" in planner
    assert "avoid_collisions" in planner.split("break", 1)[0]
    assert "axial_roll_start_deg" in planner
    assert "axial_roll_end_deg" in planner


def test_step65_world_pose_is_explicitly_converted_to_locked_base_frame():
    """Regression for the 0.9% x4-case Cartesian planning failure."""

    base_to_world = (
        (0.0201084, 0.999776, -0.00656425, -88.4572),
        (0.950417, -0.0211527, -0.310257, 42.0928),
        (-0.310326, 0.0, -0.95063, 137.66),
        (0.0, 0.0, 0.0, 1.0),
    )
    pre_entry_world = (
        (1.0, 0.0, 0.0, -74.433660),
        (0.0, 1.0, 0.0, -66.834729),
        (0.0, 0.0, 1.0, 47.057526),
        (0.0, 0.0, 0.0, 1.0),
    )
    pre_entry_base = _rigid_pose_world_to_reference_rows(
        pre_entry_world,
        base_to_world,
    )
    assert tuple(round(pre_entry_base[row][3], 6) for row in range(3)) == (
        -75.128281,
        16.324510,
        119.832904,
    )
    wrong_frame_position_error, _angle_error = _pose_residual_mm_degrees(
        pre_entry_world,
        pre_entry_base,
    )
    assert abs(wrong_frame_position_error - 110.5088) < 0.001
    assert _pose_residual_mm_degrees(pre_entry_base, pre_entry_base) == (0.0, 0.0)


def test_cartesian_frame_conversion_rejects_scale_or_reflection():
    identity = (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    scaled = (
        (2.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    try:
        _rigid_pose_world_to_reference_rows(identity, scaled)
    except ValueError as exc:
        assert "unit length" in str(exc) or "scale" in str(exc)
    else:
        raise AssertionError("a scaled robot-base pose was accepted")


def test_cartesian_planner_converts_raw_matrices_once_and_checks_continuity():
    source = (HELPERS / "DENTOROS2Bridge.py").read_text(encoding="utf-8")
    planner = source.split("def plan_moveit_cartesian_path", 1)[1].split(
        "def _dentobot_native_motion_context", 1
    )[0]
    assert "_pose_matrices_world_to_base_mm" in planner
    assert "_cartesian_start_continuity" in planner
    assert "relativeToNode=None" in planner
    assert "Refusing an unintended Cartesian bridge" in planner


def test_phased_waypoints_do_not_republish_and_reset_guard_configuration():
    source = (HELPERS / "DENTOROS2Bridge.py").read_text(encoding="utf-8")
    apply_phase = source.split("def apply_task_phase_joint_positions", 1)[1].split(
        "def _wait_for_joint_command_result", 1
    )[0]
    assert "config_publisher.Publish" not in apply_phase
    assert "active_fingerprint" in apply_phase


def test_task_guard_configuration_requires_a_strict_sequence_zero_handshake():
    source = (HELPERS / "DENTOROS2Bridge.py").read_text(encoding="utf-8")
    configure = source.split("def configure_task_phase_guard", 1)[1].split(
        "def apply_task_phase_joint_positions", 1
    )[0]
    assert '"sequence": 0' in configure
    assert '"phase": "approach"' in configure
    assert '"guard_session_id": uuid4().hex' in configure
    assert '"clearance_exempt_object_ids"' in configure
    assert "status.accepted" in configure
    assert "ROS2_TASK_GUARD_SCENE_SYNC_TIMEOUT_SEC" in configure
    assert "configured task-proximity collision object is missing" in configure
    assert "complete planning-scene object set" in configure
    assert "did not acknowledge" in configure


class _FakeTransform:
    def __init__(self, node_id):
        self.node_id = node_id
        self.parent_id = None

    def GetID(self):
        return self.node_id

    def SetAndObserveTransformNodeID(self, node_id):
        self.parent_id = node_id


class _FakeRobot:
    def __init__(self, live_root=None, goal_root=None):
        self.references = {
            "lookup": [live_root] if live_root is not None else [],
            "goal_transform": [goal_root] if goal_root is not None else [],
        }

    def GetNthNodeReference(self, role, index):
        values = self.references.get(role, [])
        return values[index] if index < len(values) else None


def test_live_and_goal_robot_roots_share_the_step6_base_transform():
    base = _FakeTransform("Step6Base")
    live_root = _FakeTransform("LiveRoot")
    goal_root = _FakeTransform("GoalRoot")
    robot = _FakeRobot(live_root, goal_root)
    assert align_ros2_robot_to_base_transform(robot, base)
    assert align_ros2_goal_to_base_transform(robot, base)
    assert live_root.parent_id == base.GetID()
    assert goal_root.parent_id == base.GetID()


def test_goal_alignment_fails_closed_when_goal_hierarchy_is_missing():
    assert not align_ros2_goal_to_base_transform(
        _FakeRobot(_FakeTransform("LiveRoot"), None),
        _FakeTransform("Step6Base"),
    )


class _FakePoint:
    def __init__(self, positions):
        self.positions = positions

    def GetPositions(self):
        return self.positions


class _FakeJointTrajectory:
    def __init__(self, points):
        self.points = points

    def GetPoints(self):
        return self.points


class _FakeTrajectory:
    def __init__(self, points):
        self.joint_trajectory = _FakeJointTrajectory(points)

    def GetJointTrajectory(self):
        return self.joint_trajectory


def test_motion_summary_distinguishes_real_motion_from_identical_goal():
    still = _FakeTrajectory([_FakePoint([0.0] * 6), _FakePoint([0.0] * 6)])
    ok, message = _trajectory_motion_summary(still)
    assert not ok
    assert "identical" in message
    moving = _FakeTrajectory([_FakePoint([0.0] * 6), _FakePoint([0.1] * 6)])
    ok, message = _trajectory_motion_summary(moving)
    assert ok
    assert "2 point" in message


def test_slicer_adapter_contains_no_process_or_ros_cli_orchestration():
    source = (HELPERS / "DENTOROS2Bridge.py").read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert "subprocess." not in source
    assert "ros2 node list" not in source
    assert "Popen(" not in source


def test_step6_joint_controls_publish_when_ros_robot_is_active():
    workflow = (
        ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot_scene.py"
    ).read_text(encoding="utf-8")
    handler = workflow.split("def onRobotJointValueChanged", 1)[1].split(
        "def onRobotBaseTransformSelectionChanged", 1
    )[0]
    assert "_robotWorkflowFacade.requestCurrentJointState()" in handler
    assert "_robotWorkflowFacade.displaySyncActive" in handler
    facade = (
        ROOT
        / "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py"
    ).read_text(encoding="utf-8")
    request = facade.split("def requestCurrentJointState", 1)[1].split(
        "def setBasePose", 1
    )[0]
    assert "apply_joint_positions_si_to_motion_control" in request
    assert "last_accepted_joint_positions_si" in request


def test_robot_facade_exposes_moveit_goal_without_hardware_execute_path():
    bridge = (HELPERS / "DENTOROS2Bridge.py").read_text(encoding="utf-8")
    facade = (HELPERS / "DENTORobotWorkflowFacade.py").read_text(encoding="utf-8")
    assert "def ensure_moveit_tcp_goal_control" in bridge
    assert "def solve_moveit_tcp_goal" in bridge
    assert "def plan_moveit_joint_goal" in bridge
    assert "def solveIk" in facade
    assert "def planToGoal" in facade
    assert "def execute" not in facade
