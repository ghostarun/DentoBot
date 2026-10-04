"""Pure tests for the thin, externally owned DENTOBOT ROS adapter."""

from __future__ import annotations

import json
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOROS2Bridge import (  # noqa: E402
    CARTESIAN_START_ORIENTATION_TOLERANCE_DEG,
    CARTESIAN_START_POSITION_TOLERANCE_MM,
    ROS2_JOINT_COMMAND_STATUS_SCHEMA,
    ROS2_JOINT_SI_ORDER,
    ROS2_MANUAL_JOINT_COMMAND_SCHEMA,
    ROS2_MANUAL_JOINT_COMMAND_TOPIC,
    ROS2_MANUAL_JOINT_POLICY_ID,
    ROS2_MANUAL_JOINT_STATUS_SCHEMA,
    ROS2_MANUAL_JOINT_STATUS_TOPIC,
    ROS2_PLANNING_GROUP,
    ROS2_SIMULATION_STATUS_SCHEMA,
    ROS2_TASK_GUARD_INITIAL_SEQUENCE,
    ROS2_TASK_JOINT_STATUS_SCHEMA,
    ROS2_TOOL_TCP_LINK,
    RuntimeState,
    acknowledge_moveit_collision_scene,
    _pose_residual_mm_degrees,
    _nudged_tcp_goal_matrix,
    _compute_live_tcp_kinematic_ik,
    _install_kinematic_tcp_drag_observer,
    _rigid_pose_world_to_reference_rows,
    _trajectory_motion_summary,
    align_ros2_goal_to_base_transform,
    align_ros2_robot_to_base_transform,
    configure_task_phase_guard,
    accept_manual_joint_state_reconciliation,
    apply_manual_joint_positions_si,
    joint_si_vector,
    parse_joint_command_status,
    parse_manual_joint_status,
    parse_simulation_status,
    parse_task_joint_status,
    position_axis_joint_limit_blockers,
    query_manual_joint_state_si,
    set_moveit_tcp_goal_drag_enabled,
)
import DENTOROS2Bridge as bridge_module  # noqa: E402


def test_reverse_cartesian_travel_preserves_forward_drill_axis():
    import numpy as np
    poses = bridge_module.tool_pose_matrices_world_mm(
        (0., 0., 0.), (0., 0., -12.), 3,
        fixed_rotation_ras=np.eye(3), reverse_travel=True,
    )
    assert [p.GetElement(2, 3) for p in poses] == [0., -6., -12.]
    for pose in poses:
        assert [pose.GetElement(i, 2) for i in range(3)] == [0., 0., 1.]
    generated = bridge_module.tool_pose_matrices_world_mm(
        (0., 0., 0.), (0., 0., -12.), 3, reverse_travel=True,
    )
    assert [generated[-1].GetElement(i, 2) for i in range(3)] == [0., 0., 1.]


def test_reverse_cartesian_travel_does_not_admit_sideways_or_wrong_axis():
    import numpy as np
    with pytest.raises(ValueError, match="does not match"):
        bridge_module.tool_pose_matrices_world_mm(
            (0., 0., 0.), (0., 0., -12.), 3, fixed_rotation_ras=np.eye(3),
        )
    with pytest.raises(ValueError, match="does not match"):
        bridge_module.tool_pose_matrices_world_mm(
            (0., 0., 0.), (12., 0., 0.), 3,
            fixed_rotation_ras=np.eye(3), reverse_travel=True,
        )
    with pytest.raises(ValueError, match="does not match"):
        bridge_module.tool_pose_matrices_world_mm(
            (0., 0., 0.), (0., 0., 12.), 3,
            fixed_rotation_ras=np.eye(3), reverse_travel=True,
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


def test_tcp_goal_nudge_applies_ras_translation_and_local_rotation():
    identity = (
        (1.0, 0.0, 0.0, 10.0),
        (0.0, 1.0, 0.0, 20.0),
        (0.0, 0.0, 1.0, 30.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    translated = _nudged_tcp_goal_matrix(
        identity, (2.0, -3.0, 4.0), (0.0, 0.0, 0.0)
    )
    assert tuple(row[3] for row in translated[:3]) == (12.0, 17.0, 34.0)
    assert tuple(row[:3] for row in translated[:3]) == tuple(
        row[:3] for row in identity[:3]
    )

    rotated = _nudged_tcp_goal_matrix(
        identity, (0.0, 0.0, 0.0), (0.0, 0.0, 90.0)
    )
    assert rotated[0][:3] == pytest.approx((0.0, -1.0, 0.0), abs=1e-12)
    assert rotated[1][:3] == pytest.approx((1.0, 0.0, 0.0), abs=1e-12)
    assert rotated[2][:3] == pytest.approx((0.0, 0.0, 1.0), abs=1e-12)
    assert tuple(row[3] for row in rotated[:3]) == (10.0, 20.0, 30.0)

    current_rotated = _nudged_tcp_goal_matrix(
        identity, (0.0, 0.0, 0.0), (0.0, 0.0, 90.0)
    )
    parent_translated = _nudged_tcp_goal_matrix(
        current_rotated, (1.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    )
    assert tuple(row[3] for row in parent_translated[:3]) == (11.0, 20.0, 30.0)
    assert tuple(row[:3] for row in parent_translated[:3]) == tuple(
        row[:3] for row in current_rotated[:3]
    )
    local_roll = _nudged_tcp_goal_matrix(
        current_rotated, (0.0, 0.0, 0.0), (90.0, 0.0, 0.0)
    )
    for actual, expected in zip(
        (row[:3] for row in local_roll[:3]),
        ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        strict=True,
    ):
        assert actual == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize(
    "matrix, translation, rotation",
    [
        (((1.0, 0.0),), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        (
            ((1.0, 0.0, 0.0, float("nan")),) * 4,
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
        ),
        (
            ((1.0, 0.0, 0.0, 0.0),) * 4,
            (1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
        ),
    ],
)
def test_tcp_goal_nudge_rejects_invalid_matrix_and_mixed_delta(
    matrix, translation, rotation
):
    with pytest.raises(ValueError):
        _nudged_tcp_goal_matrix(matrix, translation, rotation)


@pytest.mark.parametrize(
    "translation, rotation",
    [
        ((1.0, 2.0), (0.0, 0.0, 0.0)),
        ((float("inf"), 0.0, 0.0), (0.0, 0.0, 0.0)),
        ((0.0, 0.0, 0.0), (0.0, float("nan"), 0.0)),
    ],
)
def test_tcp_goal_nudge_rejects_malformed_or_nonfinite_delta(translation, rotation):
    with pytest.raises(ValueError):
        _nudged_tcp_goal_matrix(
            ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0),
             (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0)),
            translation,
            rotation,
        )


def test_tcp_drag_toggle_routes_only_to_native_enter_or_exit(monkeypatch):
    calls = []
    monkeypatch.setattr(
        bridge_module,
        "ensure_moveit_tcp_goal_control",
        lambda: (calls.append("enable") or True, "enabled", object()),
    )
    monkeypatch.setattr(
        bridge_module,
        "exit_moveit_tcp_goal_control",
        lambda: (calls.append("disable") or True, "disabled", None),
    )
    assert not set_moveit_tcp_goal_drag_enabled("on")[0]
    assert set_moveit_tcp_goal_drag_enabled(True)[0]
    assert set_moveit_tcp_goal_drag_enabled(False)[0]
    assert calls == ["enable", "disable"]


def test_enable_and_disable_use_native_control_mode_entry_and_exit(monkeypatch):
    goal = object()
    enter_calls = []
    monkeypatch.setattr(
        bridge_module,
        "_dentobot_native_motion_context",
        lambda **kwargs: (
            enter_calls.append(kwargs) or object(),
            object(),
            goal,
            "",
        ),
    )
    enabled, _message, enabled_goal = bridge_module.ensure_moveit_tcp_goal_control()
    assert enabled and enabled_goal is goal
    assert enter_calls == [{"initialize_goal": True}]

    class NativeMotionLogic:
        def __init__(self):
            self.exited = []

        def ExitControlMode(self, transform):
            self.exited.append(transform)

    native_logic = NativeMotionLogic()
    monkeypatch.setattr(bridge_module, "get_motion_control_logic", lambda: native_logic)
    monkeypatch.setattr(bridge_module, "_native_goal_transform", goal)
    monkeypatch.setattr(bridge_module, "_native_tcp_drag_enabled", True)
    disabled, _message, disabled_goal = bridge_module.exit_moveit_tcp_goal_control()
    assert disabled and disabled_goal is None
    assert native_logic.exited == [goal]
    assert bridge_module._native_goal_transform is None
    assert bridge_module._native_tcp_drag_enabled is False


def test_tcp_goal_nudge_is_blocked_when_explicit_drag_mode_is_off(monkeypatch):
    monkeypatch.setattr(bridge_module, "_native_tcp_drag_enabled", False)
    monkeypatch.setattr(
        bridge_module,
        "_dentobot_native_motion_context",
        lambda **_kwargs: pytest.fail("a disabled nudge must not enter native control"),
    )
    ok, message, goal_node, pose = bridge_module.nudge_moveit_tcp_goal(
        (1.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    )
    assert not ok and "Enable TCP Drag" in message
    assert goal_node is None and pose is None


def test_matrix_goal_setter_does_not_activate_native_viewport_drag():
    source = inspect.getsource(bridge_module.set_moveit_tcp_goal_matrix)
    assert "_ensure_native_tcp_goal_transform()" in source
    assert "ensure_moveit_tcp_goal_control()" not in source


class _FakePoseMatrix:
    def __init__(self):
        self.values = [[float(row == column) for column in range(4)] for row in range(4)]


class _FakeGoalTransform:
    def __init__(self, *, fail_add=False):
        self.name = "ProbeSphere_Transform"
        self.observer = None
        self.removed = []
        self.fail_add = fail_add

    def GetName(self):
        return self.name

    def AddObserver(self, event_id, callback):
        if self.fail_add:
            raise RuntimeError("observer rejected")
        self.observer = (event_id, callback)
        return 41

    def RemoveObserver(self, tag):
        self.removed.append(tag)
        self.observer = None


class _FakeLiveRobot:
    def __init__(self):
        self.position_axis_ik_calls = []
        self.full_pose_ik_calls = []
        self.solution = [0.1, 0.02, 0.2, 0.03, 0.4]
        self.on_ik = None

    def ComputeMoveItPositionAxisIK(self, pose, link, seed, timeout, avoid_collisions):
        self.position_axis_ik_calls.append(
            (pose, link, seed, timeout, avoid_collisions)
        )
        if self.on_ik:
            self.on_ik()
        return self.solution

    def ComputeMoveItIK(self, *args, **kwargs):
        self.full_pose_ik_calls.append((args, kwargs))
        raise AssertionError("TCP review must leave axial tool roll unconstrained")

    def GetLastMoveItPositionAxisIKMessage(self):
        return "position-axis candidate available"

    def GetLastMoveItPositionAxisIKPositionResidualMm(self):
        return 0.2

    def GetLastMoveItPositionAxisIKAxisResidualDeg(self):
        return 0.3

    def FindRootAndTipLinks(self):
        return "BaseLink", ROS2_TOOL_TCP_LINK


class _FakeLiveMotionLogic:
    def __init__(self):
        self.obsNode = None
        self.obsTag = None
        self.callback = None
        self.viewObserverTags = []
        self.last_ik_solution = []
        self.updated_goal_positions = []
        self.color_results = []
        self.removed_old = []

    def removeObserver(self):
        if self.obsNode is not None and self.obsTag is not None:
            self.obsNode.RemoveObserver(self.obsTag)
            self.removed_old.append(self.obsTag)
        for observed, tag in self.viewObserverTags:
            observed.RemoveObserver(tag)
        self.viewObserverTags = []
        self.obsNode = None
        self.obsTag = None
        self.callback = None
        self.isInteracting = False

    def setIKSourceTransforms(self, source_name, target_name):
        assert source_name == "ProbeSphere_Transform"
        assert target_name == "GoalRoot"

    def findRobotTransforms(self, root_link, *, goal):
        assert root_link == "BaseLink"
        assert goal is True
        return SimpleNamespace(GetName=lambda: "GoalRoot")

    def computeIKWithMoveIt(self, **_kwargs):
        raise AssertionError("Solve IK must not enter the native collision callback")

    def ConvertTipTargetToIKTarget(self, pose, tip_link):
        assert tip_link == ROS2_TOOL_TCP_LINK
        return "ik-link", ("converted-pose", pose)

    def updategoalTransformsFromJointsKDL(self, robot, values):
        self.updated_goal_positions.append((robot, tuple(values)))

    def _updateRobotColorForIKResult(self, robot, success, base_color):
        self.color_results.append((robot, bool(success), tuple(base_color)))

    def ExitControlMode(self, _goal_node):
        self.removeObserver()


def _install_fake_slicer_vtk(monkeypatch):
    slicer_module = SimpleNamespace(
        vtkMRMLTransformNode=SimpleNamespace(TransformModifiedEvent=77),
        vtkMRMLTransformNodeAPI=SimpleNamespace(),
    )
    slicer_module.vtkMRMLTransformNode.GetMatrixTransformBetweenNodes = (
        lambda _source, _target, matrix: True
    )
    monkeypatch.setitem(sys.modules, "slicer", slicer_module)
    monkeypatch.setitem(sys.modules, "vtk", SimpleNamespace(vtkMatrix4x4=_FakePoseMatrix))


def test_live_tcp_ik_uses_exact_j1_j5_moveit_kinematics_without_collisions(monkeypatch):
    _install_fake_slicer_vtk(monkeypatch)
    logic = _FakeLiveMotionLogic()
    robot = _FakeLiveRobot()
    logic.last_ik_solution = [0.0] * len(ROS2_JOINT_SI_ORDER)

    success, message, positions = _compute_live_tcp_kinematic_ik(
        logic, robot, _FakeGoalTransform(), SimpleNamespace(name="GoalRoot")
    )

    assert success and "position-axis review" in message
    assert "axial tool roll is unconstrained" in message
    assert "position residual 0.200 mm" in message
    assert "drill-axis residual 0.300 deg" in message
    assert tuple(positions) == ROS2_JOINT_SI_ORDER
    assert tuple(positions.values()) == tuple(robot.solution)
    assert robot.position_axis_ik_calls[0][1:] == (
        "ik-link",
        [0.0] * len(ROS2_JOINT_SI_ORDER),
        0.05,
        False,
    )
    assert logic.last_ik_solution == robot.solution
    assert robot.full_pose_ik_calls == []
    assert logic.updated_goal_positions == [(robot, tuple(robot.solution))]


@pytest.mark.parametrize(
    "cached_seed",
    [
        [0.0] * 6,
        [0.0, 0.0, float("nan"), 0.0, 0.0],
    ],
)
def test_live_tcp_ik_discards_invalid_cached_seed(monkeypatch, cached_seed):
    _install_fake_slicer_vtk(monkeypatch)
    logic = _FakeLiveMotionLogic()
    logic.last_ik_solution = list(cached_seed)
    robot = _FakeLiveRobot()

    success, _message, _positions = _compute_live_tcp_kinematic_ik(
        logic, robot, _FakeGoalTransform(), SimpleNamespace(name="GoalRoot")
    )

    assert success
    assert robot.position_axis_ik_calls[0][2] == []


@pytest.mark.parametrize(
    "solution",
    [
        [0.1, 0.02, 0.2, 0.03],
        [0.1, 0.02, float("nan"), 0.03, 0.4],
    ],
)
def test_live_tcp_position_axis_ik_rejects_nonfive_or_nonfinite_solution(
    monkeypatch, solution
):
    _install_fake_slicer_vtk(monkeypatch)
    logic = _FakeLiveMotionLogic()
    previous_seed = [0.03] * len(ROS2_JOINT_SI_ORDER)
    logic.last_ik_solution = list(previous_seed)
    robot = _FakeLiveRobot()
    robot.solution = solution

    success, message, positions = _compute_live_tcp_kinematic_ik(
        logic, robot, _FakeGoalTransform(), SimpleNamespace(name="GoalRoot")
    )

    assert not success
    assert positions == {}
    assert "position-axis" in message
    assert logic.last_ik_solution == previous_seed
    assert logic.updated_goal_positions == []
    assert robot.full_pose_ik_calls == []


def test_live_tcp_drag_observer_is_reentrant_safe_and_native_exit_cleans_it(monkeypatch):
    _install_fake_slicer_vtk(monkeypatch)
    goal = _FakeGoalTransform()
    goal_root = SimpleNamespace(name="GoalRoot", GetName=lambda: "GoalRoot")
    logic = _FakeLiveMotionLogic()
    old_node = _FakeGoalTransform()
    logic.obsNode, logic.obsTag, logic.callback = old_node, 9, object()
    robot = _FakeLiveRobot()

    ok, message = _install_kinematic_tcp_drag_observer(
        logic, robot, goal, goal_root
    )
    assert ok, message
    assert logic.removed_old == [9]
    assert logic.obsNode is goal and logic.obsTag == 41
    assert logic.callback is not None and goal.observer[0] == 77
    robot.on_ik = lambda: goal.observer[1](goal, 77)
    goal.observer[1](goal, 77)
    assert len(robot.position_axis_ik_calls) == 1
    assert robot.full_pose_ik_calls == []
    assert logic.color_results == [(robot, True, (0.25, 0.75, 0.95))]

    logic.ExitControlMode(goal)
    assert goal.removed == [41]
    assert logic.obsNode is None and logic.obsTag is None and logic.callback is None


def test_failed_live_tcp_observer_install_clears_native_observer_fields(monkeypatch):
    _install_fake_slicer_vtk(monkeypatch)
    goal = _FakeGoalTransform(fail_add=True)
    logic = _FakeLiveMotionLogic()
    logic.obsNode, logic.obsTag, logic.callback = goal, 8, object()
    robot = _FakeLiveRobot()

    ok, message = _install_kinematic_tcp_drag_observer(
        logic,
        robot,
        goal,
        SimpleNamespace(name="GoalRoot", GetName=lambda: "GoalRoot"),
    )
    assert not ok and "Could not install" in message
    assert logic.obsNode is None and logic.obsTag is None and logic.callback is None


def test_drag_activation_failure_uses_native_exit_and_stays_disabled(monkeypatch):
    _install_fake_slicer_vtk(monkeypatch)
    monkeypatch.setattr(
        bridge_module,
        "find_ros2_robot_by_name",
        lambda _name: SimpleNamespace(FindRootAndTipLinks=lambda: ("base", "tip")),
    )
    goal = _FakeGoalTransform()
    goal_root = SimpleNamespace(name="GoalRoot")

    class Logic(_FakeLiveMotionLogic):
        def __init__(self):
            super().__init__()
            self.exit_calls = []

        def EnterControlMode(self, *_args, **_kwargs):
            return {"fromTransform": goal, "toTransform": goal_root}

        def ExitControlMode(self, transform):
            self.exit_calls.append(transform)
            self.removeObserver()

    logic = Logic()
    monkeypatch.setattr(bridge_module, "get_motion_control_logic", lambda: logic)
    monkeypatch.setattr(bridge_module, "_mark_node_and_storage_transient", lambda _node: None)
    monkeypatch.setattr(bridge_module, "mark_slicer_ros2_runtime_nodes_transient", lambda: 0)
    monkeypatch.setattr(
        bridge_module,
        "_install_kinematic_tcp_drag_observer",
        lambda *_args, **_kwargs: (False, "observer install failed"),
    )
    monkeypatch.setattr(bridge_module, "_native_goal_transform", None)
    monkeypatch.setattr(bridge_module, "_native_tcp_drag_enabled", False)

    _logic, _robot, failed_goal, error = bridge_module._dentobot_native_motion_context(
        initialize_goal=True
    )

    assert failed_goal is None and "observer install failed" in error
    assert logic.exit_calls == [goal]
    assert bridge_module._native_goal_transform is None
    assert bridge_module._native_tcp_drag_enabled is False


def _tcp_solve_fixture(monkeypatch, static_result):
    _install_fake_slicer_vtk(monkeypatch)
    logic = _FakeLiveMotionLogic()
    robot = _FakeLiveRobot()
    goal = _FakeGoalTransform()
    monkeypatch.setattr(
        bridge_module,
        "_dentobot_native_motion_context",
        lambda **_kwargs: (logic, robot, goal, ""),
    )
    queried = []

    def check_static(positions):
        queried.append(dict(positions))
        return static_result

    monkeypatch.setattr(
        bridge_module,
        "check_moveit_static_joint_state",
        check_static,
    )
    return logic, robot, goal, queried


def test_explicit_tcp_solve_requires_authoritative_static_validity(monkeypatch):
    logic, robot, _goal, queried = _tcp_solve_fixture(
        monkeypatch, (True, "state is clear", True)
    )

    ok, message, positions = bridge_module.solve_moveit_tcp_goal()

    assert ok and "authoritative MoveIt static validity" in message
    assert "axial tool roll is unconstrained" in message
    assert tuple(positions) == ROS2_JOINT_SI_ORDER
    assert queried == [positions]
    assert robot.position_axis_ik_calls[0][1:] == (
        "ik-link",
        [],
        0.05,
        False,
    )
    assert robot.full_pose_ik_calls == []
    assert logic.last_ik_solution == robot.solution
    assert logic.updated_goal_positions == [(robot, tuple(robot.solution))]
    assert logic.color_results == [(robot, True, (0.25, 0.75, 0.95))]


def test_explicit_tcp_solve_rejects_authoritatively_invalid_candidate(monkeypatch):
    logic, robot, _goal, queried = _tcp_solve_fixture(
        monkeypatch, (False, "self collision", True)
    )

    ok, message, positions = bridge_module.solve_moveit_tcp_goal()

    assert not ok and "rejected by MoveIt static validity" in message
    assert "self collision" in message
    assert positions == {}
    assert queried and tuple(queried[0]) == ROS2_JOINT_SI_ORDER
    assert logic.last_ik_solution == robot.solution
    assert logic.updated_goal_positions == [(robot, tuple(robot.solution))]
    assert logic.color_results == [(robot, False, (0.25, 0.75, 0.95))]


def test_explicit_tcp_solve_rejects_nonauthoritative_validity(monkeypatch):
    logic, robot, _goal, queried = _tcp_solve_fixture(
        monkeypatch, (True, "service unavailable", False)
    )

    ok, message, positions = bridge_module.solve_moveit_tcp_goal()

    assert not ok and "unresolved" in message
    assert "service unavailable" in message
    assert positions == {}
    assert queried and tuple(queried[0]) == ROS2_JOINT_SI_ORDER
    assert logic.last_ik_solution == robot.solution
    assert logic.updated_goal_positions == [(robot, tuple(robot.solution))]
    assert logic.color_results == [(robot, False, (0.25, 0.75, 0.95))]
    assert robot.full_pose_ik_calls == []


def test_failed_live_tcp_ik_is_visible_without_staging_or_advancing_state(monkeypatch):
    _install_fake_slicer_vtk(monkeypatch)
    goal = _FakeGoalTransform()
    logic = _FakeLiveMotionLogic()
    logic.last_ik_solution = [0.03] * len(ROS2_JOINT_SI_ORDER)
    robot = _FakeLiveRobot()
    robot.solution = []
    ok, message = _install_kinematic_tcp_drag_observer(
        logic,
        robot,
        goal,
        SimpleNamespace(name="GoalRoot", GetName=lambda: "GoalRoot"),
    )
    assert ok, message

    goal.observer[1](goal, 77)

    assert logic._dentobotLiveTcpIkMessage.startswith(
        "Live TCP position-axis review found no exact J1–J5 candidate"
    )
    assert logic.color_results == [(robot, False, (0.25, 0.75, 0.95))]
    assert logic.last_ik_solution == [0.03] * len(ROS2_JOINT_SI_ORDER)
    assert logic.updated_goal_positions == []


def manual_joint_status_payload(**overrides) -> str:
    data = {
        "schema": ROS2_MANUAL_JOINT_STATUS_SCHEMA,
        "mode": "simulation_only",
        "operation": "jog",
        "request_id": "request-a",
        "session_id": "session-a",
        "policy_id": ROS2_MANUAL_JOINT_POLICY_ID,
        "command_valid": True,
        "query_only": False,
        "accepted": True,
        "reason": "clear",
        "requested_positions": [0.1, 0.02, 0.2, 0.02, 0.1],
        "accepted_positions": [0.1, 0.02, 0.2, 0.02, 0.1],
        "checked_samples": 3,
        "minimum_clearance_m": 0.001,
        "minimum_self_distance_m": 0.002,
        "minimum_world_distance_m": 0.003,
        "first_body": "",
        "second_body": "",
        "world_object_count": 0,
        "world_objects": [],
    }
    data.update(overrides)
    return json.dumps(data)


def test_task_guard_rejects_non_target_allowance_before_ros():
    ok, reason = configure_task_phase_guard(
        task_fingerprint="test", target_object_id="selected-tooth",
        clearance_exempt_object_ids=["selected-tooth", "adjacent-tooth"],
        base_transform=None,
        entry_ras_mm=(0, 0, 0), target_ras_mm=(0, 0, 10),
        corridor_radius_mm=0.75, approach_standoff_mm=5,
    )
    assert not ok
    assert "Only the selected target" in reason


def test_current_task_guard_identity_reads_only_active_configuration(monkeypatch):
    monkeypatch.setattr(
        bridge_module,
        "_last_task_config_json",
        json.dumps(
            {
                "task_fingerprint": "task-a",
                "guard_session_id": "session-a",
                "collision_scene_policy_fingerprint": "policy-a",
            }
        ),
    )

    identity = bridge_module.current_task_guard_identity()

    assert dict(identity) == {
        "task_fingerprint": "task-a",
        "guard_session_id": "session-a",
        "collision_scene_policy_fingerprint": "policy-a",
    }
    monkeypatch.setattr(bridge_module, "_last_task_config_json", "")
    assert bridge_module.current_task_guard_identity() is None


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
    assert joint_si_vector(positions) == [0.0, 1.0, 2.0, 3.0, 4.0]


def test_position_axis_limit_diagnostic_reports_only_commandable_bounds():
    values = [0.1, 0.0, 0.2, 0.075, -0.3]
    lower = [-1.0, 0.0, -1.0, 0.0, -6.0]
    upper = [1.0, 0.08, 1.0, 0.075, 6.0]
    blockers = position_axis_joint_limit_blockers(values, lower, upper)
    assert [(item["joint"], item["bound"]) for item in blockers] == [
        ("link-2_Slider-2", "lower"),
        ("link-4_Slider-4", "upper"),
    ]
    assert all("pneumatic_spindle" not in str(item) for item in blockers)


def _ack_collision_scene(monkeypatch, *, expected_bounds_mm, observed_bounds_m,
                         expected_pose=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
                         observed_pose=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)):
    observed = {
        "id": "world-object",
        "shape_count": 1,
        "pose_base_link_m_xyzw": observed_pose,
        "bounds_base_link_m": observed_bounds_m,
    }
    status = SimpleNamespace(
        world_object_evidence_present=True,
        world_object_count=1,
        world_objects=(observed,),
        collision_scene_policy_fingerprint="",
    )
    monkeypatch.setattr(
        bridge_module, "apply_joint_positions_si_to_motion_control", lambda _positions: None
    )
    monkeypatch.setattr(bridge_module, "joint_command_status", lambda **_kwargs: status)
    clock_values = iter((0.0, 0.0, 1.0))
    monkeypatch.setattr(bridge_module.time, "monotonic", lambda: next(clock_values))
    monkeypatch.setattr(bridge_module.time, "sleep", lambda _seconds: None)
    return acknowledge_moveit_collision_scene(
        expected_objects=(
            {
                "outgoing_collision_object_id": "world-object",
                "outgoing_pose_base_link_m_xyzw": expected_pose,
                "outgoing_bounds_base_link_mm": expected_bounds_mm,
            },
        ),
        current_joint_positions_si={},
        timeout_sec=0.1,
    )


def test_collision_scene_acknowledgement_accepts_matching_bounds(monkeypatch):
    result = _ack_collision_scene(
        monkeypatch,
        expected_bounds_mm=(-10.0, -5.0, 20.0, 30.0, -50.0, -40.0),
        observed_bounds_m=(-0.010, -0.005, 0.020, 0.030, -0.050, -0.040),
    )
    assert result["status"] == "Acknowledged"
    assert result["acknowledged_object_ids"] == ["world-object"]


def test_collision_scene_acknowledgement_keeps_one_micrometre_tolerance(monkeypatch):
    result = _ack_collision_scene(
        monkeypatch,
        expected_bounds_mm=(-10.0, -5.0, 20.0, 30.0, -50.0, -40.0),
        observed_bounds_m=(
            -0.0100009,
            -0.005,
            0.020,
            0.030,
            -0.050,
            -0.040,
        ),
    )
    assert result["status"] == "Acknowledged"


def test_collision_scene_acknowledgement_reports_bound_mismatch_in_units(monkeypatch):
    result = _ack_collision_scene(
        monkeypatch,
        expected_bounds_mm=(-10.0, -5.0, 20.0, 30.0, -50.0, -40.0),
        observed_bounds_m=(-0.0112, -0.005, 0.020, 0.030, -0.050, -0.040),
    )
    mismatch = " ".join(result["mismatches"])
    assert result["status"] == "Mismatch"
    assert "runtime bounds differ for world-object" in mismatch
    assert "base_link bounds=(-10.0, -5.0, 20.0, 30.0, -50.0, -40.0) mm" in mismatch
    assert "base_link bounds=(-0.0112, -0.005, 0.02, 0.03, -0.05, -0.04) m" in mismatch
    assert "max_abs_delta=1.200000 mm" in mismatch


@pytest.mark.parametrize(
    "bad_bounds",
    [
        None,
        (0.0,) * 5,
        (0.0,) * 7,
        (0.0, 0.0, 0.0, float("nan"), 0.0, 0.0),
        (0.0, 0.0, 0.0, float("inf"), 0.0, 0.0),
        (0.0, 0.0, 0.0, "malformed", 0.0, 0.0),
        (1.0, 0.0, 0.0, 1.0, 0.0, 1.0),
        (0.0, 1.0, 1.0, 0.0, 0.0, 1.0),
        (0.0, 1.0, 0.0, 1.0, 1.0, 0.0),
    ],
)
@pytest.mark.parametrize("side", ("expected", "observed"))
def test_collision_scene_acknowledgement_rejects_invalid_bounds(
    monkeypatch, bad_bounds, side
):
    result = _ack_collision_scene(
        monkeypatch,
        expected_bounds_mm=(
            bad_bounds
            if side == "expected"
            else (-10.0, -5.0, 20.0, 30.0, -50.0, -40.0)
        ),
        observed_bounds_m=(
            bad_bounds
            if side == "observed"
            else (-0.010, -0.005, 0.020, 0.030, -0.050, -0.040)
        ),
    )
    assert result["status"] == "Mismatch"
    assert any(
        "invalid comparable base-link bounds" in mismatch
        for mismatch in result["mismatches"]
    )


@pytest.mark.parametrize(
    "side,bad_pose",
    (
        ("expected", (float("nan"), 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)),
        ("observed", (0.0, 0.0, 0.0, float("inf"), 0.0, 0.0, 1.0)),
    ),
)
def test_collision_scene_acknowledgement_rejects_nonfinite_poses(
    monkeypatch, side, bad_pose
):
    result = _ack_collision_scene(
        monkeypatch,
        expected_bounds_mm=(-10.0, -5.0, 20.0, 30.0, -50.0, -40.0),
        observed_bounds_m=(-0.010, -0.005, 0.020, 0.030, -0.050, -0.040),
        expected_pose=(
            bad_pose if side == "expected" else (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        ),
        observed_pose=(
            bad_pose if side == "observed" else (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        ),
    )
    assert result["status"] == "Mismatch"
    assert any(
        "invalid comparable base-link pose" in mismatch
        for mismatch in result["mismatches"]
    )


def test_joint_guard_status_parses_accepted_state_and_clearances():
    payload = json.dumps(
        {
            "schema": ROS2_JOINT_COMMAND_STATUS_SCHEMA,
            "mode": "simulation_only",
            "accepted": False,
            "reason": "Self-clearance is 3.00 mm",
            "requested_positions": [0.1, 0.02, 0.2, 0.02, 0.1],
            "accepted_positions": [0.0] * 5,
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
    assert status.accepted_positions == (0.0,) * 5
    assert (status.first_body, status.second_body) == ("link-3", "link-5")


def test_joint_guard_status_rejects_wrong_mode_and_vector_length():
    base = {
        "schema": ROS2_JOINT_COMMAND_STATUS_SCHEMA,
        "mode": "simulation_only",
        "accepted": True,
        "reason": "accepted",
        "requested_positions": [0.0] * 5,
        "accepted_positions": [0.0] * 5,
    }
    wrong_mode = dict(base, mode="hardware")
    try:
        parse_joint_command_status(json.dumps(wrong_mode))
    except ValueError as exc:
        assert "simulation_only" in str(exc)
    else:
        raise AssertionError("hardware status was accepted")
    malformed = dict(base, requested_positions=[0.0] * 6)
    try:
        parse_joint_command_status(json.dumps(malformed))
    except ValueError as exc:
        assert "five" in str(exc)
    else:
        raise AssertionError("five-joint status was accepted")


def test_manual_joint_status_requires_exact_simulation_request_policy_and_vectors():
    status = parse_manual_joint_status(manual_joint_status_payload())
    assert status.request_id == "request-a"
    assert status.session_id == "session-a"
    assert status.policy_id == ROS2_MANUAL_JOINT_POLICY_ID
    assert status.command_valid is True
    assert status.accepted_positions == status.requested_positions

    for change in (
        {"schema": ROS2_JOINT_COMMAND_STATUS_SCHEMA},
        {"mode": "hardware"},
        {"request_id": ""},
        {"session_id": ""},
        {"policy_id": "phase_guard_fingerprint"},
        {"operation": "state_query"},
        {"query_only": True},
        {"command_valid": 1},
        {"requested_positions": [True, 0.02, 0.2, 0.02, 0.1]},
        {"accepted_positions": [0.1, 0.02, float("inf"), 0.02, 0.1]},
        {"world_object_count": True},
        {"world_object_count": 1},
    ):
        with pytest.raises(ValueError):
            parse_manual_joint_status(manual_joint_status_payload(**change))


def _manual_bridge_probe(monkeypatch, replies):
    class Subscriber:
        def __init__(self, node):
            self.node = node
            self.payload = ""
            self.messages = 0
            self.observer = None

        def SaveWithSceneOff(self):
            pass

        def AddObserver(self, _event, callback):
            self.observer = callback
            return 1

        def RemoveObserver(self, _observer):
            self.observer = None

        def GetNumberOfMessages(self):
            return self.messages

        def GetLastMessage(self):
            return self.payload

        def deliver(self, payload):
            self.payload = payload
            self.messages += 1
            if self.observer:
                self.observer(self)

        def GetID(self):
            return "manual-status"

    class Publisher:
        def __init__(self, node):
            self.node = node
            self.messages = []

        def SaveWithSceneOff(self):
            pass

        def Publish(self, payload):
            self.messages.append(payload)
            for reply in replies:
                self.node.subscriber.deliver(reply)

        def GetID(self):
            return "manual-command"

    class RosNode:
        def __init__(self):
            self.subscriber = None
            self.publisher = None
            self.removed = []

        def CreateAndAddSubscriberNode(self, _type, topic):
            assert topic == ROS2_MANUAL_JOINT_STATUS_TOPIC
            self.subscriber = Subscriber(self)
            return self.subscriber

        def CreateAndAddPublisherNode(self, _type, topic):
            assert topic == ROS2_MANUAL_JOINT_COMMAND_TOPIC
            self.publisher = Publisher(self)
            return self.publisher

        def RemoveAndDeleteSubscriberNode(self, topic):
            self.removed.append(("subscriber", topic))

        def RemoveAndDeletePublisherNode(self, topic):
            self.removed.append(("publisher", topic))

        def GetNumberOfNodeReferences(self, _role):
            return 0

    class Timer:
        active = True

        def isActive(self):
            return self.active

        def stop(self):
            self.active = False

        def start(self):
            self.active = True

    node = RosNode()
    timer = Timer()
    monkeypatch.setattr(bridge_module, "ensure_default_ros2_node_in_scene", lambda: node)
    monkeypatch.setattr(bridge_module, "get_ros2_logic", lambda: SimpleNamespace(Spin=lambda: None))
    monkeypatch.setattr(bridge_module, "find_ros2_robot_by_name", lambda _name: object())
    monkeypatch.setattr(bridge_module, "_slicer_joint_command_timer", timer)
    monkeypatch.setattr(bridge_module, "_native_joint_positions", [0.0] * 5)
    monkeypatch.setattr(bridge_module, "_last_manual_joint_status", None)
    monkeypatch.setattr(bridge_module, "_last_manual_joint_status_at", 0.0)
    monkeypatch.setattr(bridge_module, "_last_joint_status", None)
    monkeypatch.setattr(bridge_module, "_last_joint_status_at", 0.0)
    monkeypatch.setattr(bridge_module, "_last_task_status", None)
    monkeypatch.setattr(bridge_module, "_last_task_status_at", 0.0)
    monkeypatch.setattr(bridge_module, "_restore_motion_control_positions", lambda _values: None)
    monkeypatch.setattr(bridge_module, "joint_command_status", lambda: None)
    monkeypatch.setattr(
        bridge_module,
        "_publish_slicer_joint_command",
        lambda: pytest.fail("manual jog must not publish the compatibility heartbeat"),
    )
    return node, timer


def test_manual_jog_ignores_delayed_same_vector_wrong_session_and_policy_replies(monkeypatch):
    requested = (0.1, 0.02, 0.2, 0.02, 0.1)
    replies = [
        manual_joint_status_payload(request_id="previous-request"),
        manual_joint_status_payload(session_id="previous-session"),
        manual_joint_status_payload(policy_id="task_phase_policy_fingerprint"),
        manual_joint_status_payload(),
    ]
    node, timer = _manual_bridge_probe(monkeypatch, replies)
    request = dict(zip(ROS2_JOINT_SI_ORDER, requested))

    applied, message, status = apply_manual_joint_positions_si(
        request, "request-a", "session-a", timeout_sec=0.02
    )

    assert applied is True
    assert message == "clear"
    assert status.request_id == "request-a"
    assert status.session_id == "session-a"
    command, = node.publisher.messages
    assert json.loads(command) == {
        "schema": ROS2_MANUAL_JOINT_COMMAND_SCHEMA,
        "mode": "simulation_only",
        "operation": "jog",
        "request_id": "request-a",
        "session_id": "session-a",
        "policy_id": ROS2_MANUAL_JOINT_POLICY_ID,
        "joint_positions": list(requested),
    }
    assert len(node.publisher.messages) == 1
    assert node.removed == [
        ("publisher", ROS2_MANUAL_JOINT_COMMAND_TOPIC),
        ("subscriber", ROS2_MANUAL_JOINT_STATUS_TOPIC),
    ]
    assert timer.active
    assert bridge_module.last_accepted_joint_positions_si() == request


def test_manual_jog_timeout_ignores_same_vector_delayed_status_without_cache_rollback(monkeypatch):
    requested = (0.1, 0.02, 0.2, 0.02, 0.1)
    node, timer = _manual_bridge_probe(
        monkeypatch,
        [
            manual_joint_status_payload(request_id="previous-request"),
            manual_joint_status_payload(session_id="previous-session"),
            manual_joint_status_payload(policy_id="wrong-policy"),
        ],
    )
    request = dict(zip(ROS2_JOINT_SI_ORDER, requested))

    applied, message, status = apply_manual_joint_positions_si(
        request, "request-a", "session-a", timeout_sec=0.02
    )

    assert applied is None
    assert "timeout" in message
    assert status is None
    assert len(node.publisher.messages) == 1
    assert bridge_module.last_accepted_joint_positions_si() == {
        name: 0.0 for name in ROS2_JOINT_SI_ORDER
    }
    assert not timer.active


def test_manual_jog_conclusive_rejection_resumes_compatibility_stream(monkeypatch):
    requested = (0.1, 0.02, 0.2, 0.02, 0.1)
    node, timer = _manual_bridge_probe(
        monkeypatch,
        [
            manual_joint_status_payload(
                accepted=False,
                accepted_positions=[0.0] * len(ROS2_JOINT_SI_ORDER),
                reason="self collision",
            )
        ],
    )

    applied, message, status = apply_manual_joint_positions_si(
        dict(zip(ROS2_JOINT_SI_ORDER, requested)),
        "request-a",
        "session-a",
        timeout_sec=0.02,
    )

    assert applied is False
    assert message == "self collision"
    assert status.accepted is False
    assert timer.active
    assert bridge_module.last_accepted_joint_positions_si() == {
        name: 0.0 for name in ROS2_JOINT_SI_ORDER
    }
    assert len(node.publisher.messages) == 1


def test_manual_jog_inconsistent_accepted_vector_does_not_advance_cache_or_display(monkeypatch):
    requested = (0.1, 0.02, 0.2, 0.02, 0.1)
    unexpected_accepted = (0.15, 0.02, 0.2, 0.02, 0.1)
    node, timer = _manual_bridge_probe(
        monkeypatch,
        [
            manual_joint_status_payload(
                accepted_positions=list(unexpected_accepted),
            )
        ],
    )
    request = dict(zip(ROS2_JOINT_SI_ORDER, requested))
    restored_positions = []
    monkeypatch.setattr(
        bridge_module,
        "_restore_motion_control_positions",
        lambda values: restored_positions.append(tuple(values)),
    )

    applied, message, status = apply_manual_joint_positions_si(
        request, "request-a", "session-a", timeout_sec=0.02
    )

    assert applied is None
    assert "did not confirm" in message
    assert status.accepted is True
    assert bridge_module.last_accepted_joint_positions_si() == {
        name: 0.0 for name in ROS2_JOINT_SI_ORDER
    }
    assert bridge_module._native_joint_positions == [0.0] * 5
    assert bridge_module._last_manual_joint_status is None
    assert restored_positions == []
    assert not timer.active
    assert len(node.publisher.messages) == 1


def test_manual_state_query_correlates_echo_without_mutating_until_commit(monkeypatch):
    echoed = (0.1, 0.02, 0.2, 0.02, 0.1)
    accepted = (0.12, 0.02, 0.2, 0.02, 0.1)
    replies = [
        manual_joint_status_payload(
            operation="state_query", query_only=True, request_id="stale-request"
        ),
        manual_joint_status_payload(
            operation="state_query", query_only=True, requested_positions=[0] * 5
        ),
        manual_joint_status_payload(
            operation="state_query",
            query_only=True,
            accepted=False,
            reason="native state currently collides",
            accepted_positions=list(accepted),
        ),
    ]
    node, timer = _manual_bridge_probe(monkeypatch, replies)
    restore_calls = []
    monkeypatch.setattr(
        bridge_module,
        "_restore_motion_control_positions",
        lambda values: restore_calls.append(tuple(values)),
    )

    status, message = query_manual_joint_state_si(
        dict(zip(ROS2_JOINT_SI_ORDER, echoed)), "request-a", "session-a"
    )

    assert status is not None
    assert status.operation == "state_query" and status.query_only is True
    assert status.accepted is False  # static collision result, not query failure
    assert status.accepted_positions == accepted
    assert "collides" in message
    assert json.loads(node.publisher.messages[0])["operation"] == "state_query"
    assert json.loads(node.publisher.messages[0])["joint_positions"] == list(echoed)
    assert len(node.publisher.messages) == 1
    assert not timer.active
    assert restore_calls == []
    assert bridge_module._native_joint_positions == [0.0] * 5
    assert bridge_module._last_manual_joint_status is None

    ok, commit_message = accept_manual_joint_state_reconciliation(
        status,
        dict(zip(ROS2_JOINT_SI_ORDER, echoed)),
        "request-a",
        "session-a",
    )

    assert ok, commit_message
    assert timer.active
    assert restore_calls == [accepted]
    assert bridge_module._native_joint_positions == list(accepted)
    assert bridge_module.last_accepted_joint_positions_si() == dict(
        zip(ROS2_JOINT_SI_ORDER, accepted)
    )


def test_manual_state_query_timeout_stays_paused_and_does_not_change_cache(monkeypatch):
    node, timer = _manual_bridge_probe(
        monkeypatch,
        [manual_joint_status_payload(operation="jog", query_only=False)],
    )
    initial = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    status, message = query_manual_joint_state_si(
        initial, "request-a", "session-a", timeout_sec=0.02
    )

    assert status is None and "timeout" in message
    assert len(node.publisher.messages) == 1
    assert not timer.active
    assert bridge_module._native_joint_positions == [0.0] * 5
    assert bridge_module._last_manual_joint_status is None


def test_manual_jog_transient_interface_failure_resumes_preexisting_stream(monkeypatch):
    node, timer = _manual_bridge_probe(monkeypatch, [])
    monkeypatch.setattr(node, "CreateAndAddPublisherNode", lambda *_args: None)

    applied, message, status = apply_manual_joint_positions_si(
        dict(zip(ROS2_JOINT_SI_ORDER, (0.1, 0.02, 0.2, 0.02, 0.1))),
        "request-a",
        "session-a",
        timeout_sec=0.02,
    )

    assert applied is None
    assert "interface is unavailable" in message
    assert status is None
    assert node.publisher is None
    assert node.removed == [("subscriber", ROS2_MANUAL_JOINT_STATUS_TOPIC)]
    assert timer.active


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
        "requested_positions": [0.0] * 5,
        "accepted_positions": [0.0] * 5,
        "exploratory_tool_contact_suppressed": True,
        "suppressed_tool_contact_sample_count": 3,
        "guide_clearance_warning": True,
        "guide_clearance_warning_sample_count": 2,
        "minimum_guide_clearance_warning_m": 0.000898675,
        "guide_clearance_warning_robot_link": "pneumatic_spindle-Copy",
        "guide_clearance_warning_object_id": "[Step 5C] guide",
    }
    status = parse_task_joint_status(json.dumps(payload))
    assert status.guard_session_id == "transient-session"
    assert status.exploratory_tool_contact_suppressed
    assert status.suppressed_tool_contact_sample_count == 3
    assert status.guide_clearance_warning
    assert status.guide_clearance_warning_sample_count == 2
    assert status.minimum_guide_clearance_warning_m == 0.000898675
    assert status.guide_clearance_warning_robot_link == "pneumatic_spindle-Copy"
    payload["guard_session_id"] = ""
    try:
        parse_task_joint_status(json.dumps(payload))
    except ValueError as exc:
        assert "guard session" in str(exc)
    else:
        raise AssertionError("task status without a guard session was accepted")


def test_task_guard_status_preserves_validate_only_transition_kind_and_policy_echo():
    payload = {
        "schema": ROS2_TASK_JOINT_STATUS_SCHEMA,
        "mode": "simulation_only",
        "accepted": False,
        "reason": "first interpolated sample left corridor",
        "task_fingerprint": "immutable-task",
        "guard_session_id": "transient-session",
        "request_id": "transition-1",
        "validation_kind": "transition",
        "phase": "drilling",
        "sequence": 4,
        "validate_only": True,
        "collision_scene_policy_fingerprint": "guard-policy-v1",
        "requested_positions": [0.0] * 5,
        "accepted_positions": [0.0] * 5,
        "starting_positions": [0.0] * 5,
        "evaluated_positions": [0.1] * 5,
        "evaluated_sample_index": 1,
        "interpolation_fraction": 0.25,
        "first_rejection_interpolation_fraction": 0.25,
        "total_sample_count": 4,
        "checked_samples": 1,
    }
    status = parse_task_joint_status(json.dumps(payload))
    assert status.validate_only is True
    assert status.collision_scene_policy_fingerprint == "guard-policy-v1"
    assert status.request_id == "transition-1"
    assert status.validation_kind == "transition"
    assert status.evaluated_positions == (0.1,) * 5
    assert status.evaluated_sample_index == 1
    assert status.interpolation_fraction == 0.25
    assert status.total_sample_count == 4
    malformed = dict(payload, validate_only="true")
    try:
        parse_task_joint_status(json.dumps(malformed))
    except ValueError as exc:
        assert "validate_only" in str(exc)
    else:
        raise AssertionError("non-boolean validate_only was accepted")


def test_task_guard_status_preserves_bounded_housing_contact_warning_and_rejects_bad_types():
    payload = {
        "schema": ROS2_TASK_JOINT_STATUS_SCHEMA,
        "mode": "simulation_only",
        "accepted": True,
        "reason": "Accepted with warning: configured 0.5 mm contact limit.",
        "task_fingerprint": "contact-task",
        "guard_session_id": "contact-session",
        "phase": "drilling",
        "sequence": 3,
        "requested_positions": [0.0] * 5,
        "accepted_positions": [0.0] * 5,
        "guide_clearance_warning": True,
        "guide_clearance_warning_sample_count": 2,
        "minimum_guide_clearance_warning_m": 0.0004,
        "guide_clearance_warning_robot_link": "pneumatic_spindle-Copy",
        "guide_clearance_warning_object_id": "configured-guide",
        "guide_warning_kind": "contact",
        "guide_clearance_warning_contact_penetration_m": 0.0004,
        "guide_clearance_warning_contact_sample_count": 2,
        "guide_clearance_warning_contact_position_base_m": [0.1, 0.2, 0.3],
    }
    status = parse_task_joint_status(json.dumps(payload))
    assert status.guide_warning_kind == "contact"
    assert status.guide_clearance_warning_contact_penetration_m == 0.0004
    assert status.guide_clearance_warning_contact_sample_count == 2
    assert status.guide_clearance_warning_contact_position_base_m == (0.1, 0.2, 0.3)
    for key, value in (
        ("guide_warning_kind", True),
        ("guide_clearance_warning_contact_penetration_m", "0.4mm"),
        ("guide_clearance_warning_contact_sample_count", 1.5),
        ("guide_clearance_warning_contact_position_base_m", [0.1, 0.2]),
    ):
        malformed = dict(payload, **{key: value})
        try:
            parse_task_joint_status(json.dumps(malformed))
        except ValueError:
            pass
        else:
            raise AssertionError(f"malformed {key} was accepted")


def test_full_chain_validation_retains_bounded_guide_warning_records(monkeypatch):
    request_ids = []

    def accept(
        _positions,
        *,
        task_fingerprint,
        phase,
        sequence,
        validate_only,
        request_id="",
    ):
        request_ids.append(request_id)
        bridge_module._last_task_status = SimpleNamespace(
            guide_clearance_warning=True,
            guide_clearance_warning_sample_count=1,
            minimum_guide_clearance_warning_m=0.0008,
            guide_clearance_warning_robot_link="pneumatic_spindle-Copy",
            guide_clearance_warning_object_id="guide",
            reason="accepted with warning",
        )
        return True, "accepted"

    monkeypatch.setattr(bridge_module, "apply_task_phase_joint_positions", accept)
    ok, message, invalid = bridge_module.validate_task_phase_waypoints(
        ({name: 0.0 for name in ROS2_JOINT_SI_ORDER},),
        ("drilling",),
        task_fingerprint="task",
        request_id_prefix="stage-check",
    )
    warnings = bridge_module.last_task_phase_validation_warnings()
    assert ok and invalid == -1 and "warning" in message
    assert warnings[0]["minimum_guide_clearance_warning_m"] == 0.0008
    assert warnings[0]["guide_clearance_warning_robot_link"] == "pneumatic_spindle-Copy"
    assert request_ids == ["stage-check:0"]


def test_moveit_frame_contract_constants():
    assert ROS2_PLANNING_GROUP == "dentobot_arm"
    assert ROS2_TOOL_TCP_LINK == "dentobot_drill_tcp"
    assert ROS2_TASK_GUARD_INITIAL_SEQUENCE == 1
    assert CARTESIAN_START_POSITION_TOLERANCE_MM == 0.25
    assert CARTESIAN_START_ORIENTATION_TOLERANCE_DEG == 0.5


def test_position_axis_ik_diagnostics_map_and_support_older_nodes(monkeypatch):
    def node(extra=()):
        getters = {
            "ComputeMoveItPositionAxisIK": lambda *_args, **_kwargs: None,
            "GetLastMoveItPositionAxisIKMessage": lambda: "IK diagnostic",
            "GetLastMoveItPositionAxisIKPositionResidualMm": lambda: 0.2,
            "GetLastMoveItPositionAxisIKAxisResidualDeg": lambda: 0.3,
            "GetLastMoveItPositionAxisIKBestJointValues": lambda: [0.1] * 5,
            "GetMoveItCollidingBodyPairs": lambda *_args: (),
        }
        getters.update(dict(extra))
        return SimpleNamespace(**getters)

    robot_node = node(
        (
            ("GetLastMoveItPositionAxisIKTerminationReason", lambda: "converged"),
            ("GetLastMoveItPositionAxisIKIterationCount", lambda: 7),
            ("GetLastMoveItPositionAxisIKCollisionCheckStatus", lambda: "not_requested"),
            ("GetLastMoveItPositionAxisIKConditionRatio", lambda: 0.25),
        )
    )
    logic = SimpleNamespace(computeIKWithMoveIt=lambda **_kwargs: [0.1] * 5)
    monkeypatch.setattr(
        bridge_module,
        "_dentobot_native_motion_context",
        lambda **_kwargs: (logic, robot_node, None, None),
    )
    ok, _message, _positions, diagnostic = bridge_module.solve_moveit_tcp_position_axis_goal(
        avoid_collisions=False
    )
    assert ok
    assert diagnostic["termination_reason"] == "converged"
    assert diagnostic["iteration_count"] == 7
    assert diagnostic["collision_check_status"] == "not_requested"
    assert diagnostic["task_jacobian_condition_ratio"] == 0.25
    assert diagnostic["collision_pairs"] == ()

    robot_node.GetLastMoveItPositionAxisIKConditionRatio = lambda: -1.0
    _ok, _message, _positions, diagnostic = bridge_module.solve_moveit_tcp_position_axis_goal(
        avoid_collisions=False
    )
    assert diagnostic["task_jacobian_condition_ratio"] is None

    old_logic = SimpleNamespace(computeIKWithMoveIt=lambda **_kwargs: [])
    old_node = node()
    monkeypatch.setattr(
        bridge_module,
        "_dentobot_native_motion_context",
        lambda **_kwargs: (old_logic, old_node, None, None),
    )
    ok, _message, _positions, diagnostic = bridge_module.solve_moveit_tcp_position_axis_goal()
    assert not ok
    assert diagnostic["termination_reason"] == "unknown"
    assert diagnostic["iteration_count"] is None
    assert diagnostic["collision_check_status"] == "unknown"
    assert diagnostic["task_jacobian_condition_ratio"] is None
    assert diagnostic["collision_pairs"] == ()


def test_position_axis_ik_residuals_are_strict_json_safe_without_faking_success(
    monkeypatch,
):
    residual = {"value": 0.0}
    robot_node = SimpleNamespace(
        ComputeMoveItPositionAxisIK=lambda *_args, **_kwargs: None,
        GetLastMoveItPositionAxisIKMessage=lambda: "native solver rejected target",
        GetLastMoveItPositionAxisIKPositionResidualMm=lambda: residual["value"],
        GetLastMoveItPositionAxisIKAxisResidualDeg=lambda: residual["value"],
        GetLastMoveItPositionAxisIKBestJointValues=lambda: [0.1] * 5,
        GetMoveItCollidingBodyPairs=lambda *_args: (),
    )
    logic = SimpleNamespace(computeIKWithMoveIt=lambda **_kwargs: [])
    monkeypatch.setattr(
        bridge_module,
        "_dentobot_native_motion_context",
        lambda **_kwargs: (logic, robot_node, None, None),
    )

    for value in (float("nan"), float("inf"), float("-inf"), -0.1):
        residual["value"] = value
        ok, message, positions, diagnostic = (
            bridge_module.solve_moveit_tcp_position_axis_goal()
        )
        assert not ok
        assert message == "native solver rejected target"
        assert positions == {}
        assert diagnostic["position_residual_mm"] is None
        assert diagnostic["drilling_axis_residual_deg"] is None
        json.dumps(diagnostic, allow_nan=False)


def test_diagnostic_display_cleanup_restores_only_owned_evidence_and_goal(
    monkeypatch,
):
    class Display:
        def __init__(self, color, visibility):
            self.color = tuple(color)
            self.visibility = bool(visibility)
            self.opacity = 1.0

        def GetColor(self):
            return self.color

        def SetColor(self, *color):
            self.color = tuple(color)

        def GetVisibility(self):
            return int(self.visibility)

        def SetVisibility(self, visible):
            self.visibility = bool(visible)

        def SetOpacity(self, opacity):
            self.opacity = float(opacity)

    class Node:
        def __init__(self, name, color=(0.2, 0.3, 0.4), visibility=True):
            self.name = name
            self.attributes = {}
            self.display = Display(color, visibility)

        def GetAttribute(self, name):
            return self.attributes.get(name)

        def SetAttribute(self, name, value):
            if value is None:
                self.attributes.pop(name, None)
            else:
                self.attributes[name] = str(value)

        def GetDisplayNode(self):
            return self.display

    collision = Node("collision", color=(0.1, 0.2, 0.3), visibility=False)
    collision.SetAttribute("DENTOBOT.CollisionAuditCopy", "true")
    collision.SetAttribute("DENTOBOT.OutgoingCollisionObjectId", "world-object")
    unrelated_collision = Node("unrelated", color=(0.3, 0.4, 0.5), visibility=True)
    unrelated_collision.SetAttribute("DENTOBOT.CollisionAuditCopy", "true")
    unrelated_collision.SetAttribute("DENTOBOT.OutgoingCollisionObjectId", "other-object")
    goal_model = Node("goal", visibility=False)
    boundary = Node("boundary")
    boundary.SetAttribute("DENTOBOT.MotionDiagnosticBoundary", "true")
    ordinary_markup = Node("ordinary-markup")
    nodes = {
        "vtkMRMLModelNode": [collision, unrelated_collision, goal_model],
        "vtkMRMLMarkupsFiducialNode": [boundary, ordinary_markup],
    }
    removed = []

    class Scene:
        def RemoveNode(self, node):
            removed.append(node)
            for group in nodes.values():
                if node in group:
                    group.remove(node)

    class Robot:
        def GetNumberOfNodeReferences(self, role):
            return 1 if role == "goal_model" else 0

        def GetNthNodeReference(self, role, index):
            return goal_model if role == "goal_model" and index == 0 else None

    slicer_stub = SimpleNamespace(
        util=SimpleNamespace(getNodesByClass=lambda node_class: list(nodes[node_class])),
        mrmlScene=Scene(),
    )
    monkeypatch.setitem(sys.modules, "slicer", slicer_stub)
    monkeypatch.setitem(sys.modules, "vtk", SimpleNamespace())
    robot = Robot()
    monkeypatch.setattr(
        bridge_module,
        "find_ros2_robot_by_name",
        lambda _name: robot,
    )
    transform_updates = []
    monkeypatch.setattr(
        bridge_module,
        "get_motion_control_logic",
        lambda: SimpleNamespace(
            updategoalTransformsFromJointsKDL=lambda _robot, values: transform_updates.append(
                tuple(values)
            )
        ),
    )
    monkeypatch.setattr(bridge_module, "_native_tcp_drag_enabled", False)
    positions = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}

    shown, _message = bridge_module.show_goal_robot_joint_positions(
        positions, diagnostic=True
    )
    evidence_ok, _message = bridge_module.show_motion_diagnostic_evidence(
        first_invalid_ras_mm=None,
        collision_pairs=(("world-object", "jaw"),),
    )

    assert shown and evidence_ok
    assert goal_model.display.visibility is True
    assert goal_model.GetAttribute("DENTOBOT.MotionDiagnosticGoal") == "true"
    assert collision.display.color == (1.0, 0.15, 0.10)
    assert collision.display.visibility is True
    assert collision.GetAttribute(
        bridge_module.ROS2_MOTION_DIAGNOSTIC_HIGHLIGHT_ATTRIBUTE
    ) == "true"
    assert unrelated_collision.display.color == (0.3, 0.4, 0.5)
    assert unrelated_collision.display.visibility is True

    cleared, _message = bridge_module.clear_motion_diagnostic_display()

    assert cleared
    assert removed == [boundary]
    assert ordinary_markup in nodes["vtkMRMLMarkupsFiducialNode"]
    assert collision.display.color == (0.1, 0.2, 0.3)
    assert collision.display.visibility is False
    assert collision.GetAttribute(
        bridge_module.ROS2_MOTION_DIAGNOSTIC_HIGHLIGHT_ATTRIBUTE
    ) is None
    assert goal_model.display.visibility is False
    assert goal_model.GetAttribute("DENTOBOT.MotionDiagnosticGoal") is None

    monkeypatch.setattr(bridge_module, "_native_tcp_drag_enabled", True)
    goal_model.SetAttribute("DENTOBOT.MotionDiagnosticGoal", "true")
    goal_model.display.SetVisibility(True)
    cleared, _message = bridge_module.clear_motion_diagnostic_display()
    assert cleared
    assert goal_model.display.visibility is True
    assert goal_model.GetAttribute("DENTOBOT.MotionDiagnosticGoal") == "true"
    blocked, message = bridge_module.show_goal_robot_joint_positions(
        positions, diagnostic=True
    )
    assert not blocked and "Disable TCP Drag" in message
    assert len(transform_updates) == 1


def test_joint_goal_planning_waits_for_a_stable_scene_and_retries_boundedly():
    source = (HELPERS / "DENTOROS2Bridge.py").read_text(encoding="utf-8")
    planner = source.split("def plan_moveit_joint_goal", 1)[1].split(
        "def sync_moveit_obstacle_polydata", 1
    )[0]
    assert "RefreshMoveItPlanningScene" in planner
    assert "ROS2_MOVEIT_PLANNING_SCENE_SETTLE_SEC" in planner
    assert "ROS2_MOVEIT_JOINT_PLAN_ATTEMPTS" in planner
    assert "for attempt in range" in planner
    assert 'planner_id: str = ""' in planner
    assert "requested_planner_id" in planner
    assert 'GetLastJointPlannerId' in planner
    assert "effective_planner_id=effective_planner_id" in planner
    assert "requested_planner_id != effective_planner_id" in planner


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
    static_refresh = apply_phase.split(
        'if validation_kind == "static_state":', 1
    )[1].split("status_before", 1)[0]
    assert apply_phase.count("config_publisher.Publish") == 1
    assert "config_publisher.Publish(_last_task_config_json)" in static_refresh
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
    assert '"simulation_guide_clearance_object_ids"' in configure
    assert "guide_clearance_exempt_robot_links" not in configure
    assert "guide_clearance_exempt_object_ids" not in configure
    assert "status.accepted" in configure
    assert "ROS2_TASK_GUARD_SCENE_SYNC_TIMEOUT_SEC" in configure
    assert "configured task-proximity collision object is missing" in configure
    assert "complete planning-scene object set" in configure
    assert "did not acknowledge" in configure


def test_task_guard_guide_clearance_field_is_optional_at_bridge_boundary():
    parameter = inspect.signature(configure_task_phase_guard).parameters[
        "simulation_guide_clearance_object_ids"
    ]
    assert parameter.default == ()
    source = (HELPERS / "DENTOROS2Bridge.py").read_text(encoding="utf-8")
    assert '"simulation_guide_clearance_object_ids"' in source


def test_preflight_start_is_canonical_read_only_and_rejects_malformed_mapping(monkeypatch):
    parameter = inspect.signature(configure_task_phase_guard).parameters[
        "preflight_start_positions_si"
    ]
    assert parameter.default is None
    source = (HELPERS / "DENTOROS2Bridge.py").read_text(encoding="utf-8")
    configure = source.split("def configure_task_phase_guard", 1)[1].split(
        "def apply_task_phase_joint_positions", 1
    )[0]
    assert "preflight_start_positions_si: Optional[Mapping[str, float]] = None" in configure
    assert "preflight_positions = joint_si_vector(preflight_start_positions_si)" in configure
    assert 'payload["preflight_start_positions"] = preflight_positions' in configure
    read_only = configure.split(
        "if static_only or preflight_positions is not None:", 1
    )[1].split("# Configuration and command use separate ROS topics", 1)[0]
    assert "config_publisher.Publish(_last_task_config_json)" in read_only
    assert "command_publisher.Publish" not in read_only
    assert '"sequence": 0' not in read_only

    publisher_calls = []
    monkeypatch.setattr(
        bridge_module,
        "_ensure_task_publishers",
        lambda: publisher_calls.append(True) or (None, None),
    )
    ok, reason = configure_task_phase_guard(
        task_fingerprint="test",
        target_object_id="selected-tooth",
        clearance_exempt_object_ids=["selected-tooth"],
        base_transform=None,
        entry_ras_mm=(0, 0, 0),
        target_ras_mm=(0, 0, 10),
        corridor_radius_mm=0.75,
        approach_standoff_mm=5,
        preflight_start_positions_si={ROS2_JOINT_SI_ORDER[0]: 0.0},
    )
    assert not ok
    assert "Invalid preflight start joint vector" in reason
    assert publisher_calls == []

    class Publisher:
        def __init__(self):
            self.messages = []

        def Publish(self, message):
            self.messages.append(message)

    config_publisher = Publisher()
    command_publisher = Publisher()
    native_before = [0.1] * len(ROS2_JOINT_SI_ORDER)
    monkeypatch.setattr(bridge_module, "_native_joint_positions", native_before)
    monkeypatch.setattr(bridge_module, "_last_task_config_json", "")
    monkeypatch.setattr(
        bridge_module,
        "_ensure_task_publishers",
        lambda: (config_publisher, command_publisher),
    )
    monkeypatch.setattr(
        bridge_module, "_ensure_task_status_subscriber", lambda: object()
    )
    monkeypatch.setattr(
        bridge_module, "world_ras_mm_to_base_m", lambda point, _base: list(point)
    )
    monkeypatch.setattr(bridge_module.time, "sleep", lambda _seconds: None)
    canonical = dict(
        zip(ROS2_JOINT_SI_ORDER, (1.0, 2.0, 3.0, 4.0, 5.0))
    )
    ok, reason = configure_task_phase_guard(
        task_fingerprint="task",
        target_object_id="selected-tooth",
        clearance_exempt_object_ids=["selected-tooth"],
        base_transform=None,
        entry_ras_mm=(0, 0, 0),
        target_ras_mm=(0, 0, 10),
        corridor_radius_mm=0.75,
        approach_standoff_mm=5,
        preflight_start_positions_si={**canonical, "unexpected_joint": 99.0},
    )
    assert not ok
    assert "exactly the canonical J1–J5 joints" in reason
    assert config_publisher.messages == []
    assert command_publisher.messages == []
    ok, reason = configure_task_phase_guard(
        task_fingerprint="task",
        target_object_id="selected-tooth",
        clearance_exempt_object_ids=["selected-tooth"],
        base_transform=None,
        entry_ras_mm=(0, 0, 0),
        target_ras_mm=(0, 0, 10),
        corridor_radius_mm=0.75,
        approach_standoff_mm=5,
        preflight_start_positions_si=canonical,
    )
    assert ok, reason
    assert len(config_publisher.messages) == 3
    assert command_publisher.messages == []
    assert json.loads(config_publisher.messages[-1])["preflight_start_positions"] == [
        1.0, 2.0, 3.0, 4.0, 5.0
    ]
    assert bridge_module._native_joint_positions == native_before


def test_facade_phase_guard_passes_the_active_policy_fingerprint():
    facade_source = (
        ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "DENTORobotWorkflowFacade.py"
    ).read_text(encoding="utf-8")
    configure = facade_source.split(
        "    def _configure_phase_guard", 1
    )[1].split("    def _prepare_phase_guard", 1)[0]
    assert (
        "collision_scene_policy_fingerprint=self._strict_guard_policy_fingerprint()"
        in configure
    )
    assert "static_only=bool(static_only)" in configure
    assert "preflight_start_positions_si: Optional[Mapping[str, float]] = None" in configure
    assert "preflight_start_positions_si=preflight_start_positions_si" in configure
    assert "preflight_start_positions_si is not None" in configure
    logic_source = (
        ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "logic_robot.py"
    ).read_text(encoding="utf-8")
    guidance = logic_source.split("def step6GuidanceCollisionObjectIds", 1)[1].split(
        "def step6BurrProximityCollisionObjectIds", 1
    )[0]
    assert "allow_deferred_static_ack: bool = False" in guidance
    assert 'audit.status == "RuntimeAcknowledgementDeferred"' in guidance
    assert '== "Deferred"' in guidance


def test_motion_bridge_can_initialize_a_static_guard_without_a_raw_joint_stream():
    bridge_source = (HELPERS / "DENTOROS2Bridge.py").read_text(encoding="utf-8")
    connect = bridge_source.split("def connect_dentobot_motion_control", 1)[1].split(
        "def prepare_dentobot_motion_diagnostics", 1
    )[0]
    assert "start_joint_command_stream: bool = True" in connect
    assert "if start_joint_command_stream:" in connect
    assert "start_slicer_joint_command_stream()" in connect
    configure = bridge_source.split("def configure_task_phase_guard", 1)[1].split(
        "def apply_task_phase_joint_positions", 1
    )[0]
    static_configuration = configure.split(
        "if static_only or preflight_positions is not None:", 1
    )[1].split(
        "# Configuration and command use separate ROS topics", 1
    )[0]
    assert "config_publisher.Publish(_last_task_config_json)" in static_configuration
    assert "command_publisher.Publish" not in static_configuration
    task_status_callback = bridge_source.split("def _on_task_status_modified", 1)[1].split(
        "def _ensure_task_status_subscriber", 1
    )[0]
    assert "not _last_task_status.validate_only" in task_status_callback
    assert "_restore_motion_control_positions" in task_status_callback


def test_validate_only_task_rejection_never_restores_display_state(monkeypatch):
    class Caller:
        def GetLastMessage(self):
            return "status"

    restored = []
    monkeypatch.setattr(
        bridge_module,
        "_restore_motion_control_positions",
        lambda values: restored.append(tuple(values)),
    )
    monkeypatch.setattr(
        bridge_module,
        "parse_task_joint_status",
        lambda _payload: SimpleNamespace(
            accepted=False,
            validate_only=True,
            accepted_positions=(1.0,) * len(ROS2_JOINT_SI_ORDER),
        ),
    )
    bridge_module._on_task_status_modified(Caller())
    assert restored == []
    monkeypatch.setattr(
        bridge_module,
        "parse_task_joint_status",
        lambda _payload: SimpleNamespace(
            accepted=False,
            validate_only=False,
            accepted_positions=(2.0,) * len(ROS2_JOINT_SI_ORDER),
        ),
    )
    bridge_module._on_task_status_modified(Caller())
    assert restored == [(2.0,) * len(ROS2_JOINT_SI_ORDER)]


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
    assert "def solve_moveit_tcp_position_axis_goal" in bridge
    assert "def plan_moveit_joint_goal" in bridge
    assert "def solveIk" in facade
    assert "def planToGoal" in facade
    assert "def execute" not in facade


def _joint_goal_result_with_fake(monkeypatch, *, mode="success", track_release=True):
    events = []
    names = list(ROS2_JOINT_SI_ORDER)
    vectors = ([0.0] * len(names), [0.1] + [0.0] * (len(names) - 1))
    if mode == "malformed":
        vectors = ([0.0] * (len(names) - 1), [0.1] + [0.0] * (len(names) - 2))

    points = []
    for index, positions in enumerate(vectors):
        def get_positions(index=index, positions=positions):
            events.append(("positions", index))
            if mode == "exception":
                raise RuntimeError("joint point read failed")
            return positions

        points.append(
            SimpleNamespace(
                GetPositions=get_positions,
                GetTimeFromStart=lambda index=index: float(index),
            )
        )
    joint_trajectory = SimpleNamespace(
        GetJointNames=lambda: names,
        GetPoints=lambda: points,
    )
    trajectory = SimpleNamespace(GetJointTrajectory=lambda: joint_trajectory)
    if track_release:
        trajectory.UnRegister = lambda value: events.append(("unregister", value))

    authority_calls = {"plan": 0, "preview": 0, "execute": 0}

    class MotionNode:
        def PlanMoveItTrajectory(self, *_args):
            authority_calls["plan"] += 1
            return trajectory

        def PreviewMoveItTrajectory(self, *_args):
            authority_calls["preview"] += 1

        def ExecuteMoveItTrajectory(self, *_args):
            authority_calls["execute"] += 1

        def GetLastJointPlanMessage(self):
            return ""

        def GetLastJointPlannerId(self):
            return ""

    motion_node = MotionNode()
    parameter_node = SimpleNamespace(motionControlNodeID="motion")
    logic = SimpleNamespace(
        last_ik_solution=[0.0] * len(names),
        getParameterNode=lambda: parameter_node,
    )
    monkeypatch.setattr(
        bridge_module,
        "_dentobot_native_motion_context",
        lambda **_kwargs: (logic, object(), None, None),
    )
    monkeypatch.setattr(bridge_module, "monitored_joint_positions_si", lambda: {})
    monkeypatch.setitem(
        sys.modules,
        "slicer",
        SimpleNamespace(mrmlScene=SimpleNamespace(GetNodeByID=lambda _node_id: motion_node)),
    )
    result = bridge_module.plan_moveit_joint_goal(
        refresh_planning_scene=False,
        planning_attempts=1,
    )
    return result, events, authority_calls


@pytest.mark.parametrize(
    ("mode", "success", "message"),
    [
        ("success", True, "Plan ready"),
        ("malformed", False, "malformed joint point"),
        ("exception", False, "joint point read failed"),
    ],
)
def test_joint_goal_planning_releases_trajectory_once_after_conversion(
    monkeypatch, mode, success, message
):
    result, events, authority_calls = _joint_goal_result_with_fake(
        monkeypatch, mode=mode
    )

    assert result.success is success
    assert message in result.message
    assert events.count(("unregister", None)) == 1
    assert events[-1] == ("unregister", None)
    assert any(event[0] == "positions" for event in events)
    assert authority_calls == {"plan": 1, "preview": 0, "execute": 0}


def _static_fk_result_with_fake(monkeypatch, *, values, fail_at=None, track_release=True):
    events = []

    def get_element(row, column):
        events.append(("element", row, column))
        if row == fail_at:
            raise RuntimeError("matrix element read failed")
        return values[row] if column == 3 else float(row == column)

    matrix = SimpleNamespace(GetElement=get_element)
    if track_release:
        matrix.UnRegister = lambda value: events.append(("unregister", value))

    class MotionNode:
        def ComputeMoveItForwardKinematics(self, *_args):
            return matrix

        def GetLastForwardKinematicsMessage(self):
            return "MoveIt FK returned an authoritative pose."

        def PreviewMoveItTrajectory(self, *_args):
            pytest.fail("static FK must not start preview")

        def ExecuteMoveItTrajectory(self, *_args):
            pytest.fail("static FK must not execute a trajectory")

    motion_node = MotionNode()
    parameter_node = SimpleNamespace(motionControlNodeID="motion")
    logic = SimpleNamespace(getParameterNode=lambda: parameter_node)
    monkeypatch.setattr(
        bridge_module,
        "_dentobot_native_motion_context",
        lambda **_kwargs: (logic, None, None, None),
    )
    monkeypatch.setitem(
        sys.modules,
        "slicer",
        SimpleNamespace(mrmlScene=SimpleNamespace(GetNodeByID=lambda _node_id: motion_node)),
    )
    positions = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    result = bridge_module.compute_moveit_static_tcp_pose_base_mm(positions)
    return result, events


@pytest.mark.parametrize(
    ("values", "fail_at", "success", "rows_read"),
    [
        ((1.0, 2.0, 3.0), None, True, (0, 1, 2)),
        ((1.0, 2.0, 3.0), 1, False, (0, 1)),
        ((1.0, float("nan"), 3.0), None, False, (0, 1, 2)),
    ],
)
def test_static_fk_releases_matrix_after_copy_on_success_and_failure(
    monkeypatch, values, fail_at, success, rows_read
):
    result, events = _static_fk_result_with_fake(
        monkeypatch,
        values=values,
        fail_at=fail_at,
    )

    assert result[0] is success
    assert events.count(("unregister", None)) == 1
    assert events[-1] == ("unregister", None)
    assert tuple(event[1] for event in events if event[0] == "element") == rows_read
    if success:
        assert result[2] == (1.0, 2.0, 3.0)
    else:
        assert result[2] is None


def test_vtk_result_fakes_without_unregister_remain_supported(monkeypatch):
    result, events, _authority_calls = _joint_goal_result_with_fake(
        monkeypatch,
        track_release=False,
    )
    assert result.success
    assert not any(event[0] == "unregister" for event in events)

    result, events = _static_fk_result_with_fake(
        monkeypatch,
        values=(1.0, 2.0, 3.0),
        track_release=False,
    )
    assert result[0]
    assert not any(event[0] == "unregister" for event in events)


def test_accepted_state_follows_last_acceptance_change_not_last_republish(monkeypatch):
    """r14/r15: a republished ordinary status (same accepted vector) must not
    override a newer phase-guard acceptance."""
    home = (0.0087, 0.03044, 3.14159, 0.032, 0.0)
    entry = (-0.0299, 0.01096, 3.1457, 0.01465, 0.3194)
    monkeypatch.setattr(bridge_module, "joint_command_status", lambda *a, **k: None)
    monkeypatch.setattr(bridge_module, "_native_joint_positions", [])
    monkeypatch.setattr(bridge_module, "_last_manual_joint_status", None)
    monkeypatch.setattr(bridge_module, "_acceptance_changed_at", {"ordinary": 0.0, "task": 0.0, "manual": 0.0})
    ordinary = SimpleNamespace(accepted_positions=home)
    bridge_module._note_acceptance("ordinary", None, ordinary, 1.0)
    monkeypatch.setattr(bridge_module, "_last_joint_status", ordinary)
    task = SimpleNamespace(accepted_positions=entry)
    bridge_module._note_acceptance("task", None, task, 2.0)
    monkeypatch.setattr(bridge_module, "_last_task_status", task)
    # The ordinary stream republishes Home many times later.
    for now in (3.0, 4.0, 5.0):
        bridge_module._note_acceptance("ordinary", ordinary, SimpleNamespace(accepted_positions=home), now)
    accepted = bridge_module.last_accepted_joint_positions_si()
    assert tuple(accepted[name] for name in ROS2_JOINT_SI_ORDER) == pytest.approx(entry)
    # A validate-only task status with an unchanged accepted vector is not a new acceptance,
    # while a real ordinary change after it wins.
    bridge_module._note_acceptance("task", task, SimpleNamespace(accepted_positions=entry), 6.0)
    assert bridge_module._acceptance_changed_at["task"] == 2.0
    moved = (0.0, 0.02, 3.1, 0.03, 0.1)
    bridge_module._note_acceptance("ordinary", ordinary, SimpleNamespace(accepted_positions=moved), 7.0)
    monkeypatch.setattr(bridge_module, "_last_joint_status", SimpleNamespace(accepted_positions=moved))
    accepted = bridge_module.last_accepted_joint_positions_si()
    assert tuple(accepted[name] for name in ROS2_JOINT_SI_ORDER) == pytest.approx(moved)


def test_task_command_wait_spins_ros_every_poll_but_throttles_ui_events(monkeypatch):
    """Operator 2026-10-03 option B: Qt events at most every 100 ms during guard waits."""
    clock = {"t": 100.0}
    monkeypatch.setattr(bridge_module.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(bridge_module.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + 0.01))
    spins = []
    events = []
    target = SimpleNamespace(task_fingerprint="t", guard_session_id="g", phase="drilling",
                             sequence=7, request_id="", validation_kind="")

    class Ros:
        def Spin(self):
            spins.append(clock["t"])
            if len(spins) == 40:  # status arrives after ~0.4 s
                monkeypatch.setattr(bridge_module, "_last_task_status", target)
                monkeypatch.setattr(bridge_module, "_last_task_status_at", clock["t"])

    monkeypatch.setattr(bridge_module, "get_ros2_logic", lambda: Ros())
    fake_slicer = SimpleNamespace(app=SimpleNamespace(processEvents=lambda: events.append(clock["t"])))
    monkeypatch.setitem(sys.modules, "slicer", fake_slicer)
    monkeypatch.setattr(bridge_module, "_last_task_status", None)
    bridge_module.task_command_wait_stats(reset=True)
    status = bridge_module._wait_for_task_command_result(
        task_fingerprint="t", guard_session_id="g", phase="drilling", sequence=7,
        after_monotonic=99.0, timeout_sec=6.0,
    )
    assert status is target
    assert len(spins) == 40 and 4 <= len(events) <= 5
    stats = bridge_module.task_command_wait_stats()
    assert stats["calls"] == 1 and stats["event_passes"] == len(events) and stats["timeouts"] == 0


def test_task_command_wait_is_timed_by_the_ui_watchdog_and_survives_its_absence(monkeypatch):
    import contextlib
    import sys
    import types

    import DENTOROS2Bridge as bridge

    calls = []

    @contextlib.contextmanager
    def fake_ui_wait(kind, label):
        scope = types.SimpleNamespace(outcome="ok")
        yield scope
        calls.append((kind, label, scope.outcome))

    package = types.ModuleType("dentobot_workflow")
    package.__path__ = []
    module = types.ModuleType("dentobot_workflow.ui_stall_watchdog")
    module.ui_wait = fake_ui_wait
    monkeypatch.setitem(sys.modules, "dentobot_workflow", package)
    monkeypatch.setitem(sys.modules, "dentobot_workflow.ui_stall_watchdog", module)
    monkeypatch.setattr(bridge, "_wait_for_task_command_result_untimed", lambda **kw: None)
    assert bridge._wait_for_task_command_result(phase="approach") is None
    monkeypatch.setattr(bridge, "_wait_for_task_command_result_untimed", lambda **kw: "status")
    assert bridge._wait_for_task_command_result(phase="retract") == "status"
    assert calls == [
        ("task_command_result", "approach", "timeout"),
        ("task_command_result", "retract", "ok"),
    ]

    monkeypatch.setitem(sys.modules, "dentobot_workflow.ui_stall_watchdog", None)  # import fails
    assert bridge._wait_for_task_command_result(phase="approach") == "status"


def test_handshake_retry_after_late_reply_uses_a_fresh_guard_session(monkeypatch):
    """r19 016: re-sending sequence 0 of the same session after a late reply
    was rejected by the guard as stale; the retry must start a fresh session."""

    class Publisher:
        def __init__(self):
            self.messages = []

        def Publish(self, message):
            self.messages.append(message)

    config_publisher, command_publisher = Publisher(), Publisher()
    monkeypatch.setattr(bridge_module, "_native_joint_positions", [0.1] * len(ROS2_JOINT_SI_ORDER))
    monkeypatch.setattr(bridge_module, "_last_task_config_json", "")
    monkeypatch.setattr(bridge_module, "_ensure_task_publishers", lambda: (config_publisher, command_publisher))
    monkeypatch.setattr(bridge_module, "_ensure_task_status_subscriber", lambda: object())
    monkeypatch.setattr(bridge_module, "world_ras_mm_to_base_m", lambda point, _base: list(point))
    monkeypatch.setattr(bridge_module.time, "sleep", lambda _seconds: None)
    waits = []

    def fake_wait(**kwargs):
        waits.append(kwargs["guard_session_id"])
        if len(waits) == 1:
            return None  # the first reply is late
        return SimpleNamespace(accepted=True, accepted_positions=[0.2] * 5, reason="ok")

    monkeypatch.setattr(bridge_module, "_wait_for_task_command_result", fake_wait)
    ok, reason = configure_task_phase_guard(
        task_fingerprint="task", target_object_id="selected-tooth",
        clearance_exempt_object_ids=["selected-tooth"], base_transform=None,
        entry_ras_mm=(0, 0, 0), target_ras_mm=(0, 0, 10),
        corridor_radius_mm=0.75, approach_standoff_mm=5,
    )
    assert ok, reason
    handshakes = [json.loads(message) for message in command_publisher.messages]
    configs = [json.loads(message) for message in config_publisher.messages]
    assert [h["sequence"] for h in handshakes] == [0, 0]
    assert handshakes[0]["guard_session_id"] != handshakes[1]["guard_session_id"]
    assert waits == [h["guard_session_id"] for h in handshakes]
    assert configs[-1]["guard_session_id"] == handshakes[1]["guard_session_id"]
    assert json.loads(bridge_module._last_task_config_json)["guard_session_id"] == handshakes[1]["guard_session_id"]


def test_task_publishers_sweep_runtime_nodes_only_when_acquired(monkeypatch):
    """Per-command full-scene sweeps cost ~6 ms each (r19 profile, 16.9 s/plan)."""

    class Publisher:
        def SetAttribute(self, *_args):
            pass

        def SaveWithSceneOff(self):
            pass

    class RosNode:
        def GetPublisherNodeByTopic(self, _topic):
            return None

        def CreateAndAddPublisherNode(self, _kind, _topic):
            return Publisher()

    sweeps = []
    monkeypatch.setattr(bridge_module, "ensure_default_ros2_node_in_scene", lambda: RosNode())
    monkeypatch.setattr(bridge_module, "mark_slicer_ros2_runtime_nodes_transient", lambda: sweeps.append(1) or 0)
    monkeypatch.setattr(bridge_module, "_task_config_publisher", None)
    monkeypatch.setattr(bridge_module, "_task_command_publisher", None)
    first = bridge_module._ensure_task_publishers()
    second = bridge_module._ensure_task_publishers()
    assert first == second and all(first)
    assert sweeps == [1]
    source = (HELPERS / "dentobot_workflow" / "widget_case_backend.py").read_text(encoding="utf-8")
    assert "mark_slicer_ros2_runtime_nodes_transient()" in source.split("def _saveSceneSnapshotToMrb", 1)[1]
