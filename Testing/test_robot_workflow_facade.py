"""Contract tests for the shared Legacy/New-GUI Step 6 façade."""

from __future__ import annotations

import json
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


class FakePoseMatrix:
    def __init__(self, rotation):
        self.rotation = rotation

    def GetElement(self, row, column):
        return self.rotation[row][column]


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
    assert "cannot independently" in drilling
    assert "start_positions" in drilling


def test_phase_guard_separates_burr_proximity_from_contact_permission():
    facade_source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py"
    ).read_text(encoding="utf-8")
    configure = facade_source.split("def _configure_phase_guard", 1)[1].split(
        "def _prepare_phase_guard", 1
    )[0]
    assert "step6BurrProximityCollisionObjectIds" in configure
    assert "target_object_id not in burr_proximity_object_ids" in configure
    assert "clearance_exempt_object_ids=burr_proximity_object_ids" in configure

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


def test_drilling_uses_one_spindle_locked_cartesian_orientation():
    source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py"
    ).read_text(encoding="utf-8")
    drilling = source.split("def _plan_full_drilling_line", 1)[1].split(
        "def planApproachPhase", 1
    )[0]
    assert "axial_roll_candidates_deg" not in drilling
    assert "fixed_roll_deg = float(start_axial_roll_deg)" in drilling
    assert "axial_roll_start_deg=fixed_roll_deg" in drilling
    assert "axial_roll_end_deg=fixed_roll_deg" in drilling
    assert "del start_axial_roll_deg" not in drilling
    assert "spindle locked at 0 rad" in drilling
    assert "partial joint path" in drilling


def test_stage1_selects_one_fixed_frame_after_full_chain_preflight():
    source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py"
    ).read_text(encoding="utf-8")
    approach = source.split("def planApproachPhase", 1)[1].split(
        "def planDrillingPhase", 1
    )[0]
    assert "_goal1_candidate_chain_preflight" in approach
    assert 'selected_candidate["orientationCommitment"]' in approach
    assert 'route["chain"]["score"]' in approach
    assert "tool_orientation_fingerprint" in approach
    assert "selected_roll_deg" in approach


def test_stage1_uses_every_bounded_home_connected_seed_with_j6_locked():
    class SeedBridge(FakeBridge):
        def __init__(self):
            super().__init__()
            self.goal = None
            self.audited = []

        @staticmethod
        def tool_pose_matrices_world_mm(*_args, **_kwargs):
            return (
                FakePoseMatrix(
                    (
                        (1.0, 0.0, 0.0),
                        (0.0, 1.0, 0.0),
                        (0.0, 0.0, 1.0),
                    )
                ),
            )

        def set_moveit_tcp_goal_matrix(self, pose):
            self.goal = pose
            return True, "goal", pose

        @staticmethod
        def solve_moveit_tcp_goal(*, seed_joint_positions_si=None):
            return True, "ik", dict(seed_joint_positions_si)

        def check_moveit_static_joint_state(self, positions):
            self.audited.append(dict(positions))
            return True, "valid", True

        @staticmethod
        def spindle_locked_tcp_roll_deg(*_args, **_kwargs):
            return True, "roll", 0.0

    parameter_node = FakeParameterNode()
    evidence = []
    for sample_index in range(8):
        positions = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
        positions[ROS2_JOINT_SI_ORDER[0]] = 0.1 * (sample_index + 1)
        positions[ROS2_JOINT_SI_ORDER[-1]] = 1.0
        evidence.append(
            {
                "sample_index": sample_index,
                "joint_names": list(ROS2_JOINT_SI_ORDER),
                "joint_positions_si": [
                    positions[name] for name in ROS2_JOINT_SI_ORDER
                ],
                "home_connectivity": {"status": "HomeConnected"},
            }
        )
    parameter_node.step6AssistedLimitProposalJson = json.dumps(
        {"accepted_sample_evidence": evidence}
    )
    bridge = SeedBridge()
    facade = DENTORobotWorkflowFacade(
        FakeLogic(parameter_node),
        lambda: parameter_node,
        bridge=bridge,
    )
    home = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}

    candidates, failures = facade._goal1_pre_entry_ik_candidates(
        parameter_node,
        (0.0, 0.0, -2.0),
        (0.0, 0.0, 0.0),
        home,
    )

    assert failures == []
    assert len(candidates) == 9
    assert {candidate["seedSampleIndex"] for candidate in candidates} == {
        None,
        *range(8),
    }
    assert len(bridge.audited) == 9
    assert all(
        positions[ROS2_JOINT_SI_ORDER[-1]] == 0.0
        for positions in bridge.audited
    )


def test_stage1_orientation_commitment_fingerprints_axis_and_complete_rotation():
    pose = FakePoseMatrix(
        (
            (0.0, -1.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
        )
    )
    first = DENTORobotWorkflowFacade._tool_orientation_commitment(
        pose,
        pre_entry_ras_mm=(0.0, 0.0, -5.0),
        entry_ras_mm=(0.0, 0.0, 0.0),
        axial_roll_deg=90.0,
    )
    second = DENTORobotWorkflowFacade._tool_orientation_commitment(
        pose,
        pre_entry_ras_mm=(0.0, 0.0, -5.0),
        entry_ras_mm=(0.0, 0.0, 0.0),
        axial_roll_deg=90.0,
    )
    assert first["toolAxisRas"] == (0.0, 0.0, 1.0)
    assert first["rotationRas"] == pose.rotation
    assert first["fingerprint"] == second["fingerprint"]


def test_post_preentry_motion_cost_ignores_external_spindle_rotation():
    first = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    spindle_only = dict(first)
    spindle_only[ROS2_JOINT_SI_ORDER[-1]] = 2.0
    arm_move = dict(spindle_only)
    arm_move[ROS2_JOINT_SI_ORDER[0]] = 0.5
    assert DENTORobotWorkflowFacade._arm_path_motion_cost(
        SimpleNamespace(waypoint_joint_vectors_si=(first, spindle_only))
    ) == 0.0
    assert DENTORobotWorkflowFacade._arm_path_motion_cost(
        SimpleNamespace(waypoint_joint_vectors_si=(first, arm_move))
    ) > 0.0


def test_full_chain_uses_non_mutating_phase_guard_preflight():
    source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py"
    ).read_text(encoding="utf-8")
    approach = source.split("def planApproachPhase", 1)[1].split(
        "def planDrillingPhase", 1
    )[0]
    assert "validate_task_phase_waypoints" in approach
    assert '"terminal_contact"' in approach
    assert '"drilling"' in approach
    assert '"Complete" if drilling_preflight is not None else "Blocked"' in approach


def test_later_cartesian_failure_keeps_its_first_invalid_evidence():
    partial = SimpleNamespace(
        waypoint_joint_vectors_si=({"joint": 0.0},) * 4,
        first_invalid_requested_index=5,
        first_invalid_ras_mm=(1.0, 2.0, 3.0),
        first_invalid_joint_positions_si=None,
        first_invalid_collision_pairs=(),
        last_valid_joint_positions_si={"joint": 0.0},
        failure_classification="kinematic_joint_or_singularity_failure",
        completed_distance_mm=9.0,
        requested_path_length_mm=10.0,
    )
    fields = DENTORobotWorkflowFacade._goal1_chain_diagnostic_fields(
        {
            "status": "BlockedStage3Cartesian",
            "terminalPlan": SimpleNamespace(waypoint_joint_vectors_si=({},) * 2),
            "drillingPlan": partial,
            "firstInvalidIndex": -1,
            "reason": "partial",
            "guardMessage": "",
        },
        3,
    )
    assert fields["full_chain_first_invalid_stage_index"] == 5
    assert fields["full_chain_first_invalid_index"] == 10
    assert fields["failure_classification"] == "kinematic_joint_or_singularity_failure"
    assert fields["first_invalid_ras_mm"] == (1.0, 2.0, 3.0)


def test_stage2_uses_one_fixed_axis_path_and_phase_guard_contact_policy():
    source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py"
    ).read_text(encoding="utf-8")
    preflight = source.split("def _goal1_candidate_chain_preflight", 1)[1].split(
        "def _goal1_pre_entry_ik_candidates", 1
    )[0]
    assert "target_ras_mm=entry" in preflight
    assert "avoid_collisions=False" in preflight
    assert '"terminal_contact"' in preflight
    assert "_configure_phase_guard" in preflight
    assert "contact_start" not in preflight


def test_goal1_diagnostics_are_arm_routes_not_spindle_roll_rows():
    source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py"
    ).read_text(encoding="utf-8")
    assert "GOAL1_AXIAL_ROLL_CANDIDATES_DEG" not in source
    assert '"route_type"' in source
    assert '"clearance-detour"' in source
    assert '"seeded"' in source
    assert '"geometrically_distinct"' in source


def test_collision_guard_rejects_spindle_motion_and_supports_validate_only():
    source = (ROOT / "dentobot_moveit_config/src/collision_guard.cpp").read_text(
        encoding="utf-8"
    )
    assert "SPINDLE_LOCKED_VALUE_RAD" in source
    assert "validate_only" in source
    assert "preflight_positions_" in source
