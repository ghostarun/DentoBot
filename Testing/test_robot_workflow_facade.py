"""Contract tests for the shared Legacy/New-GUI Step 6 façade."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOROS2Bridge import ROS2_JOINT_SI_ORDER  # noqa: E402
from DENTORobotWorkflowFacade import (  # noqa: E402
    DENTORobotWorkflowFacade,
    _compact_guarded_waypoints,
    _concatenate_waypoint_times,
)


class FakeBase:
    def __init__(self):
        self.node_id = "base"
        self.active = False
        self.matrix = None

    def GetID(self):
        return self.node_id

    def SetAndObserveTransformNodeID(self, node_id):
        assert node_id is None

    def SetMatrixTransformToParent(self, matrix):
        self.matrix = matrix


class FakeParameterNode:
    def __init__(self):
        self.step6PlanningContextImported = True
        self.robotBaseTransform = FakeBase()
        self.robotBaseMountLocked = False
        self.robotJoint1Deg = 0.0
        self.robotJoint2Mm = 0.0
        self.robotJoint3Deg = 0.0
        self.robotJoint4Mm = 0.0
        self.robotJoint5Deg = 0.0
        self.robotJoint6Deg = 0.0
        self.end_modify_callback = None

    def StartModify(self):
        return 11

    def EndModify(self, token):
        assert token == 11
        if self.end_modify_callback is not None:
            self.end_modify_callback()


class FakeBridge:
    ROS2_PLANNING_GROUP = "dentobot_arm"
    ROS2_TOOL_TCP_LINK = "dentobot_drill_tip_provisional"
    ROS2_TASK_GUARD_INITIAL_SEQUENCE = 1
    ROS2_GUARD_MAX_REVOLUTE_STEP_RAD = 0.017453292519943295
    ROS2_GUARD_MAX_PRISMATIC_STEP_M = 0.0005
    ROS2_GUARD_PREVIEW_MAX_INTERPOLATION_SAMPLES = 4

    def __init__(self):
        self.reject = False
        self.applied = []

    @staticmethod
    def simulation_stack_status():
        return SimpleNamespace(
            state=SimpleNamespace(value="ready"),
            description_ready=True,
            planning_ready=True,
            joint_state_publisher_count=1,
            reason="",
        )

    def apply_joint_positions_si_to_motion_control(self, positions):
        self.applied.append(dict(positions))
        return (False, "collision") if self.reject else (True, "accepted")

    @staticmethod
    def last_accepted_joint_positions_si():
        return {name: 0.0 for name in ROS2_JOINT_SI_ORDER}

    @staticmethod
    def joint_command_status():
        return None

    @staticmethod
    def wait_for_collision_guard_world(minimum_object_count):
        return True, f"acknowledged {minimum_object_count}"


class FakeLogic:
    def __init__(self, parameter_node):
        self.parameter_node = parameter_node
        self.updated = []
        self.synced = 0

    @staticmethod
    def draftPhantomModelNodes():
        return []

    @staticmethod
    def robotModelNodes():
        return ["local-model"]

    @staticmethod
    def robotLinkTransformNodes():
        return ["link-transform"]

    @staticmethod
    def positionRobotBaseNearResearchPhantom(base, models):
        raise AssertionError("case mode must not reposition for a phantom")

    @staticmethod
    def ensureRobotBaseTransform(base):
        return base

    @staticmethod
    def isRos2MotionControlActive(base):
        return bool(base and base.active)

    @staticmethod
    def getTaskJointLimits(parameter_node):
        del parameter_node
        pair = lambda lo, hi: SimpleNamespace(minimum=lo, maximum=hi)
        return SimpleNamespace(
            joint_1=pair(-30.0, 30.0),
            joint_2=pair(0.0, 80.0),
            joint_3=pair(-90.0, 90.0),
            joint_4=pair(0.0, 75.0),
            joint_5=pair(-90.0, 90.0),
            joint_6=pair(-360.0, 360.0),
        )

    def updateRobotJointPoses(self, positions):
        self.updated.append(dict(positions))

    def setRobotBaseMountLocked(self, parameter_node, locked):
        parameter_node.robotBaseMountLocked = bool(locked)

    def syncStep6MoveItPlanningScene(self, parameter_node):
        del parameter_node
        self.synced += 1
        return 4


def make_facade():
    parameter_node = FakeParameterNode()
    logic = FakeLogic(parameter_node)
    bridge = FakeBridge()
    facade = DENTORobotWorkflowFacade(
        logic,
        lambda: parameter_node,
        bridge=bridge,
    )
    return facade, parameter_node, logic, bridge


def test_capabilities_expose_fixed_moveit_contract_without_saved_ui_state():
    facade, parameter_node, _logic, _bridge = make_facade()
    parameter_node.robotBaseTransform.active = True
    capabilities = facade.capabilities()
    assert capabilities.simulation_only
    assert capabilities.connected
    assert capabilities.single_joint_state_source
    assert capabilities.move_group_available
    assert capabilities.planning_group == "dentobot_arm"
    assert capabilities.tcp_link == "dentobot_drill_tip_provisional"


def test_current_state_uses_operator_units_and_ros_si_values():
    facade, parameter_node, _logic, _bridge = make_facade()
    parameter_node.robotJoint1Deg = 90.0
    parameter_node.robotJoint2Mm = 25.0
    state = facade.currentRobotState()
    assert state.scene_kind == "case"
    assert state.joint_display_values[:2] == (90.0, 25.0)
    assert state.joint_display_units[:2] == ("deg", "mm")
    assert abs(state.joint_positions_si[ROS2_JOINT_SI_ORDER[0]] - 1.5707963268) < 1e-9
    assert state.joint_positions_si[ROS2_JOINT_SI_ORDER[1]] == 0.025


def test_local_joint_request_updates_fk_through_logic():
    facade, parameter_node, logic, _bridge = make_facade()
    result = facade.requestJointValue(1, 12.5)
    assert result.success
    assert parameter_node.robotJoint1Deg == 12.5
    assert len(logic.updated) == 1


def test_ros_rejection_restores_last_accepted_operator_values():
    facade, parameter_node, _logic, bridge = make_facade()
    parameter_node.robotBaseTransform.active = True
    parameter_node.robotJoint1Deg = 5.0
    bridge.reject = True
    result = facade.requestJointValue(1, 20.0)
    assert not result.success
    assert result.code == "joint_rejected"
    assert parameter_node.robotJoint1Deg == 0.0


def test_programmatic_display_sync_does_not_publish_or_clear_guard_session():
    facade, parameter_node, _logic, bridge = make_facade()
    parameter_node.robotBaseTransform.active = True
    facade._phase_sequence = 7
    callback_results = []
    parameter_node.end_modify_callback = lambda: callback_results.append(
        facade.requestCurrentJointState()
    )

    facade._write_display_values(
        parameter_node,
        (10.0, 20.0, 30.0, 40.0, 50.0, 60.0),
    )

    assert callback_results[-1].success
    assert callback_results[-1].code == "display_sync_ignored"
    assert facade._phase_sequence == 7
    assert bridge.applied == []
    assert not facade.displaySyncActive


def test_lock_base_synchronizes_moveit_scene_when_ros_is_active():
    facade, parameter_node, logic, _bridge = make_facade()
    parameter_node.robotBaseTransform.active = True
    result = facade.lockBase()
    assert result.success
    assert parameter_node.robotBaseMountLocked
    assert logic.synced == 1
    capabilities = facade.capabilities()
    assert capabilities.planning_scene_synchronized
    assert capabilities.planning_scene_object_count == 4


def test_joint_limit_rejection_does_not_mutate_parameter_node():
    facade, parameter_node, logic, _bridge = make_facade()
    result = facade.requestJointValue(1, 45.0)
    assert not result.success
    assert result.code == "joint_limit"
    assert parameter_node.robotJoint1Deg == 0.0
    assert logic.updated == []


def test_independent_moveit_stage_times_are_joined_monotonically():
    joined = _concatenate_waypoint_times((0.0, 0.5, 1.0), (0.0, 0.2, 0.4))
    assert joined[:3] == (0.0, 0.5, 1.0)
    assert joined[3] > joined[2]
    assert all(joined[index] >= joined[index - 1] for index in range(1, len(joined)))


def test_guarded_waypoint_compaction_preserves_endpoints_bends_and_span():
    names = tuple(ROS2_JOINT_SI_ORDER)

    def point(j1, j2=0.0):
        values = (j1, j2, 0.0, 0.0, 0.0, 0.0)
        return dict(zip(names, values))

    straight = tuple(point(index * 0.001) for index in range(21))
    compact, times = _compact_guarded_waypoints(
        straight,
        tuple(float(index) for index in range(len(straight))),
        maximum_revolute_span_rad=0.01,
        maximum_prismatic_span_m=0.002,
    )
    assert compact[0] == straight[0]
    assert compact[-1] == straight[-1]
    assert len(compact) == 3
    assert times == (0.0, 10.0, 20.0)
    assert all(
        abs(compact[index][names[0]] - compact[index - 1][names[0]]) <= 0.01
        for index in range(1, len(compact))
    )

    bent = (point(0.0), point(0.005, 0.0005), point(0.01, 0.0))
    compact_bend, _ = _compact_guarded_waypoints(
        bent,
        (0.0, 1.0, 2.0),
        maximum_revolute_span_rad=0.02,
        maximum_prismatic_span_m=0.002,
    )
    assert compact_bend == bent


def test_goal2_reuses_goal1_guard_session_and_accepted_entry_state():
    source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py"
    ).read_text(encoding="utf-8")
    drilling = source.split("def planDrillingPhase", 1)[1].split(
        "def previewPhase", 1
    )[0]
    assert "_prepare_phase_guard" not in drilling
    assert "_phase_guard_task_fingerprint" in drilling
    assert "last_accepted_joint_positions_si" in drilling
    assert "_preflight_drilling_plan" in drilling
    assert "_plan_full_drilling_line" in drilling
    assert "start_positions" in drilling


def test_phase_guard_separates_burr_proximity_from_contact_permission():
    facade_source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py"
    ).read_text(encoding="utf-8")
    prepare = facade_source.split("def _prepare_phase_guard", 1)[1].split(
        "def _guarded_preview_checkpoints", 1
    )[0]
    assert "step6BurrProximityCollisionObjectIds" in prepare
    assert "target_object_id not in burr_proximity_object_ids" in prepare
    assert "clearance_exempt_object_ids=burr_proximity_object_ids" in prepare

    logic_source = (
        ROOT / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_robot.py"
    ).read_text(encoding="utf-8")
    proximity = logic_source.split(
        "def step6BurrProximityCollisionObjectIds", 1
    )[1].split("def importStep6PlanningContext", 1)[0]
    assert '":target:" in sourceId' in proximity
    assert '":anatomy:" in sourceId' in proximity
    assert "isGuidance or isCaseAnatomy" in proximity


def test_phase_preview_keeps_one_monotonic_sequence_across_both_goals():
    source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py"
    ).read_text(encoding="utf-8")
    preview = source.split("def previewPhase", 1)[1].split(
        "def _apply_positions_si", 1
    )[0]
    assert "self._phase_sequence = 0" not in preview
    assert "sequence=self._phase_sequence" in preview
    assert "self._phase_sequence += 1" in preview
    assert "phase_session_consumed" in preview


def test_terminal_and_drilling_keep_dense_cartesian_samples_uncompacted():
    source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py"
    ).read_text(encoding="utf-8")
    approach = source.split("def planApproachPhase", 1)[1].split(
        "def planDrillingPhase", 1
    )[0]
    drilling = source.split("def planDrillingPhase", 1)[1].split(
        "def previewPhase", 1
    )[0]
    assert "terminal_waypoints = terminal_source" in approach
    assert "waypoints = source_waypoints" in drilling


def test_drilling_searches_only_bounded_cylindrical_burr_axial_roll():
    source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py"
    ).read_text(encoding="utf-8")
    drilling = source.split("def _plan_full_drilling_line", 1)[1].split(
        "def planApproachPhase", 1
    )[0]
    assert "axial_roll_candidates_deg" in drilling
    assert "axial_roll_start_deg=0.0" in drilling
    assert "axial_roll_end_deg=axial_roll_deg" in drilling
    assert "Reposition the robot base" in drilling
    assert "partial path" in drilling
