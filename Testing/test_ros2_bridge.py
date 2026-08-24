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
    ROS2_JOINT_COMMAND_STATUS_SCHEMA,
    ROS2_JOINT_SI_ORDER,
    ROS2_PLANNING_GROUP,
    ROS2_SIMULATION_STATUS_SCHEMA,
    ROS2_TOOL_TCP_LINK,
    RuntimeState,
    _trajectory_motion_summary,
    align_ros2_goal_to_base_transform,
    align_ros2_robot_to_base_transform,
    joint_si_vector,
    parse_joint_command_status,
    parse_simulation_status,
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
    assert joint_si_vector(positions) == list(map(float, range(6)))


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


def test_moveit_frame_contract_constants():
    assert ROS2_PLANNING_GROUP == "dentobot_arm"
    assert ROS2_TOOL_TCP_LINK == "dentobot_tool_tcp"


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
    workflow = (ROOT / "DENTOWorkflow/DENTOWorkflow.py").read_text(encoding="utf-8")
    handler = workflow.split("def onRobotJointValueChanged", 1)[1].split(
        "def onRobotBaseTransformSelectionChanged", 1
    )[0]
    assert "isRos2MotionControlActive" in handler
    assert "apply_joint_positions_si_to_motion_control" in handler
    assert "last_accepted_joint_positions_si" in handler
