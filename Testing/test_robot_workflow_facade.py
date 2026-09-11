"""Contract tests for the shared Legacy/New-GUI Step 6 façade."""

from __future__ import annotations

import json
import ast
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))


def test_route_selection_allows_direct_winner_after_detours():
    source = HELPERS / "DENTORobotWorkflowFacade.py"
    tree = ast.parse(source.read_text())
    block = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                 and isinstance(node.test, ast.Name)
                 and node.test.id == "clearance_candidate_routes")
    code = compile(ast.Module(body=block.body, type_ignores=[]), str(source), "exec")
    direct = {"strictPlan": "direct", "candidate": "direct",
              "chain": {"score": (0,), "axisPlan": "axis"}, "diagnosticIndex": 0}
    detour = {"strictPlan": "detour", "candidate": "detour",
              "chain": {"score": (1,), "axisPlan": "axis"}, "diagnosticIndex": 1,
              "clearance": {"sampleIndex": 3}}
    state = {"planned_candidate_routes": [direct], "clearance_candidate_routes": [detour]}
    exec(code, state)
    assert state["strict_plan"] == "direct"
    assert state["selected_clearance"] is None
    detour["chain"]["score"] = (-1,)
    exec(code, state)
    assert state["strict_plan"] == "detour"
    assert state["selected_clearance"] == {"sampleIndex": 3}


def test_guide_allowlist_uses_acknowledged_semantic_collision_audit():
    source = (HELPERS / "dentobot_workflow" / "logic_robot.py").read_text()
    method = source[source.index("    def step6GuidanceCollisionObjectIds"):]
    method = method[:method.index("\n    def ", 5)]
    assert "collisionSceneAuditRecord(parameterNode)" in method
    assert 'audit.status != "Acknowledged"' in method
    assert 'record.get("publish_status") == "PublishReturnedSuccess"' in method
    assert '"FinalPrintableTemplate", "verified-final-template"' in method
    assert "getNodesByClass" not in method

from DENTOROS2Bridge import ROS2_JOINT_SI_ORDER  # noqa: E402
from DENTOStep6State import SPINDLE_JOINT_NAME  # noqa: E402
from DENTORobotWorkflowFacade import (  # noqa: E402
    DENTORobotWorkflowFacade,
    PROVISIONAL_EFFECTIVE_TOOL_PROTRUSION_MM,
    PROVISIONAL_GUIDE_SHELL_TRAVERSAL_ALLOWANCE_MM,
    PROVISIONAL_MAXIMUM_COMBINED_INSERTION_MM,
    RobotActionResult,
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
        self.values = [
            [
                float(rotation[row][column]) if row < 3 and column < 3 else
                1.0 if row == column else 0.0
                for column in range(4)
            ]
            for row in range(4)
        ]

    def GetElement(self, row, column):
        return self.values[row][column]

    def SetElement(self, row, column, value):
        self.values[row][column] = float(value)


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
    ROS2_TOOL_TCP_LINK = "dentobot_drill_tcp"
    ROS2_TASK_GUARD_INITIAL_SEQUENCE = 1
    ROS2_GUARD_MAX_REVOLUTE_STEP_RAD = 0.017453292519943295
    ROS2_GUARD_MAX_PRISMATIC_STEP_M = 0.0005
    ROS2_GUARD_PREVIEW_MAX_INTERPOLATION_SAMPLES = 4
    ROS2_MONITORED_PRISMATIC_TOLERANCE_M = 0.0002
    ROS2_MONITORED_REVOLUTE_TOLERANCE_RAD = 0.002

    def __init__(self):
        self.reject = False
        self.applied = []
        self.accepted = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
        self.phase_calls = []
        self.task_status = None

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

    def last_accepted_joint_positions_si(self):
        return dict(self.accepted)

    def apply_task_phase_joint_positions(
        self, positions, *, task_fingerprint, phase, sequence
    ):
        self.accepted = dict(positions)
        self.phase_calls.append((str(phase), int(sequence), dict(positions)))
        self.task_status = SimpleNamespace(
            guide_clearance_warning=(phase == "retraction"),
            guide_clearance_warning_sample_count=1,
            minimum_guide_clearance_warning_m=0.0008,
            guide_clearance_warning_robot_link="pneumatic_spindle-Copy",
            guide_clearance_warning_object_id="guide",
            reason="accepted with warning",
        )
        return True, "accepted"

    def last_task_joint_status(self):
        return self.task_status

    def wait_for_monitored_joint_positions_si(self, expected, timeout_sec=1.5):
        del timeout_sec
        self.accepted = dict(expected)
        return True, "matched", dict(expected), 0.0

    @staticmethod
    def joint_command_status():
        return None

    @staticmethod
    def wait_for_collision_guard_world(minimum_object_count):
        return True, f"acknowledged {minimum_object_count}"


def test_provisional_tool_insertion_limit_preserves_requested_depth():
    maximum = (
        PROVISIONAL_MAXIMUM_COMBINED_INSERTION_MM
        - PROVISIONAL_GUIDE_SHELL_TRAVERSAL_ALLOWANCE_MM
    )
    passing = DENTORobotWorkflowFacade._tool_insertion_evidence(
        (0.0, 0.0, 0.0), (0.0, 0.0, maximum)
    )
    blocked = DENTORobotWorkflowFacade._tool_insertion_evidence(
        (0.0, 0.0, 0.0), (0.0, 0.0, maximum + 0.001)
    )
    assert passing["status"] == "Pass"
    assert abs(passing["remainingInsertionMarginMm"]) <= 1.0e-12
    assert blocked["status"] == "Blocked"
    assert blocked["code"] == "TRAJECTORY_COMBINED_INSERTION_LIMIT_EXCEEDED"
    assert abs(blocked["requestedDrillingDepthMm"] - (maximum + 0.001)) <= 1.0e-12
    assert passing["requestedCombinedInsertionMm"] == 6.5
    assert passing["remainingVisibleProtrusionMm"] == 0.5


def test_guarded_return_reverses_accepted_contact_history_before_home_check():
    facade, _parameter_node, logic, bridge = make_facade()
    home = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    entry = dict(home, **{ROS2_JOINT_SI_ORDER[0]: 0.1})
    target = dict(home, **{ROS2_JOINT_SI_ORDER[0]: 0.2})
    bridge.accepted = dict(target)
    logic.confirmedTaskFreshnessIssues = lambda _node: ()
    logic.confirmedTaskRecord = lambda _node: SimpleNamespace(
        snapshot_fingerprint="task"
    )
    facade.applyTaskHome = lambda: RobotActionResult(
        True, "task_home_applied", "matched", details={"runtimeValidated": True}
    )
    facade._robot_away_from_home = True
    facade._completed_phase = "drilling"
    facade._phase_sequence = 12
    facade._motion_history_task_fingerprint = "task"
    facade._accepted_motion_history = [
        {"positions": home, "phase": "home"},
        {"positions": entry, "phase": "terminal_contact"},
        {"positions": target, "phase": "drilling"},
    ]

    result = facade.returnToTaskHome()

    assert result.success and result.details["axialRetractionCompleted"]
    assert [call[:2] for call in bridge.phase_calls] == [
        ("retraction", 12),
        ("retraction", 13),
    ]
    assert result.details["acceptedReverseWaypointCount"] == 2
    assert result.details["guideClearanceWarningCount"] == 2


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
    assert capabilities.tcp_link == "dentobot_drill_tcp"


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


def test_target_switch_preserves_task_home_and_return_home_state():
    facade, _parameter_node, _logic, _bridge = make_facade()
    facade._runtime_validated_task_home_key = "home-key"
    facade._runtime_task_home_evidence = {"status": "Validated"}
    facade._robot_away_from_home = True
    facade._planning_scene_synchronized = True
    facade._runtime_validated_workspace_key = "old-target"

    facade.invalidateTargetRuntimeState()

    assert facade._runtime_validated_task_home_key == "home-key"
    assert facade._runtime_task_home_evidence == {"status": "Validated"}
    assert facade.returnHomeRequired
    assert not facade.capabilities().planning_scene_synchronized
    assert facade._runtime_validated_workspace_key == ""


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
    assert "simulation_guide_clearance_object_ids=guidance_object_ids" in configure
    assert "_template_collision_excluded_object_ids" not in configure

    logic_source = (
        ROOT / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_robot.py"
    ).read_text(encoding="utf-8")
    proximity = logic_source.split(
        "def step6BurrProximityCollisionObjectIds", 1
    )[1].split("def importStep6PlanningContext", 1)[0]
    assert "target_object_id = self.step6TargetCollisionObjectId(parameterNode)" in proximity
    assert "return (target_object_id,) if target_object_id else ()" in proximity
    assert "isGuidance or isCaseAnatomy" not in proximity


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


def test_drilling_uses_one_external_spindle_independent_cartesian_orientation():
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
    assert "non-spinning TCP" in drilling
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


def test_stage1_uses_every_bounded_home_connected_seed_without_j6():
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
        def solve_moveit_tcp_position_axis_goal(*, seed_joint_positions_si=None):
            return True, "ik", dict(seed_joint_positions_si), {
                "position_residual_mm": 0.0,
                "drilling_axis_residual_deg": 0.0,
            }

        @staticmethod
        def compute_tcp_pose_world_ras_mm(_positions, *, base_transform):
            assert base_transform is not None
            return True, "fk", (
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, -2.0),
                (0.0, 0.0, 0.0, 1.0),
            )

        def check_moveit_static_joint_state(self, positions):
            self.audited.append(dict(positions))
            return True, "valid", True

    parameter_node = FakeParameterNode()
    evidence = []
    for sample_index in range(8):
        positions = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
        positions[ROS2_JOINT_SI_ORDER[0]] = 0.1 * (sample_index + 1)
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
        (0.0, 0.0, 10.0),
        home,
    )

    assert failures == []
    assert len(candidates) == 9
    assert {candidate["seedSampleIndex"] for candidate in candidates} == {
        None,
        *range(8),
    }
    assert len(bridge.audited) == 9
    assert all(set(positions) == set(ROS2_JOINT_SI_ORDER) for positions in bridge.audited)
    assert all(
        candidate["positionAxisIkDiagnostic"][
            "authoritative_position_residual_mm"
        ]
        == 0.0
        and candidate["positionAxisIkDiagnostic"][
            "authoritative_drilling_axis_residual_deg"
        ]
        == 0.0
        for candidate in candidates
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
        entry_ras_mm=(0.0, 0.0, 0.0),
        target_ras_mm=(0.0, 0.0, 5.0),
        axial_roll_deg=90.0,
    )
    second = DENTORobotWorkflowFacade._tool_orientation_commitment(
        pose,
        entry_ras_mm=(0.0, 0.0, 0.0),
        target_ras_mm=(0.0, 0.0, 5.0),
        axial_roll_deg=90.0,
    )
    assert first["toolAxisRas"] == (0.0, 0.0, 1.0)
    assert first["rotationRas"] == pose.rotation
    assert first["fingerprint"] == second["fingerprint"]


def test_post_preentry_motion_cost_ignores_external_spindle_rotation():
    first = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    spindle_only = dict(first)
    spindle_only[SPINDLE_JOINT_NAME] = 2.0
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


def test_collision_guard_uses_group_joint_count_and_supports_validate_only():
    source = (ROOT / "dentobot_moveit_config/src/collision_guard.cpp").read_text(
        encoding="utf-8"
    )
    assert "SPINDLE_LOCKED_VALUE_RAD" not in source
    assert "validate_only" in source
    assert "preflight_positions_" in source
