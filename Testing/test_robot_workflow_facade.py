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
from DENTORobotWorkflowFacade import DENTORobotWorkflowFacade  # noqa: E402


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

    def StartModify(self):
        return 11

    def EndModify(self, token):
        assert token == 11


class FakeBridge:
    ROS2_PLANNING_GROUP = "dentobot_arm"
    ROS2_TOOL_TCP_LINK = "dentobot_drill_tip_provisional"

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
