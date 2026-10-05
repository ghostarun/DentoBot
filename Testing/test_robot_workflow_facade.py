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


def test_goal1_route_key_distinguishes_seed_and_clearance_identity():
    direct = {
        "candidate": {
            "routeType": "seeded",
            "seedSampleIndex": 4,
            "rollDeg": 0.0,
        }
    }
    detour = {
        **direct,
        "clearance": {"sampleIndex": 2},
    }
    direct_key = DENTORobotWorkflowFacade._goal1_route_key(direct)
    detour_key = DENTORobotWorkflowFacade._goal1_route_key(detour)
    assert direct_key["route_type"] == "seeded"
    assert direct_key["clearance_sample_index"] is None
    assert detour_key["route_type"] == "clearance-detour"
    assert detour_key["clearance_sample_index"] == 2
    assert direct_key != detour_key


def test_failed_alternate_route_apply_preserves_active_plan_and_saved_identity(
    monkeypatch,
):
    facade, parameter_node, _logic, _bridge = make_facade()
    parameter_node.step6MotionDiagnosticJson = "prior-diagnostic"
    prior_plan = object()
    prior_paths = {0: {"stage1": ("prior",)}}
    prior_override = {"state": "locked", "candidate_index": 0}
    facade._motion_plan = prior_plan
    facade._diagnostic_candidate_paths = prior_paths
    facade._diagnostic_plan_selection_override = prior_override
    facade._completed_phase = "approach"
    facade._phase_sequence = 7

    def select(_index, *, lock=False):
        del lock
        parameter_node.step6MotionDiagnosticJson = "attempted-diagnostic"
        facade._motion_plan = object()
        facade._diagnostic_candidate_paths = {1: {"stage1": ("attempt",)}}
        return RobotActionResult(
            True,
            "motion_diagnostic_plan_locked",
            "selected",
            details={"planSelection": {"state": "locked", "candidate_index": 1}},
        )

    monkeypatch.setattr(facade, "selectDiagnosticCandidate", select)
    monkeypatch.setattr(
        facade,
        "planApproachPhase",
        lambda: RobotActionResult(False, "approach_plan_failed", "blocked"),
    )

    result = facade.applyDiagnosticCandidate(1, lock=True)

    assert not result.success
    assert result.details["activationPreserved"]
    assert parameter_node.step6MotionDiagnosticJson == "prior-diagnostic"
    assert facade._motion_plan is prior_plan
    assert facade._diagnostic_candidate_paths is prior_paths
    assert facade._diagnostic_plan_selection_override is prior_override
    assert facade._completed_phase == "approach"
    assert facade._phase_sequence == 7


def test_guide_allowlist_uses_acknowledged_or_explicit_deferred_static_audit():
    source = (HELPERS / "dentobot_workflow" / "logic_robot.py").read_text()
    method = source[source.index("    def step6GuidanceCollisionObjectIds"):]
    method = method[:method.index("\n    def ", 5)]
    assert "collisionSceneAuditRecord(parameterNode)" in method
    assert "allow_deferred_static_ack: bool = False" in method
    assert 'audit.status == "Acknowledged"' in method
    assert 'audit.status == "RuntimeAcknowledgementDeferred"' in method
    assert '== "Deferred"' in method
    assert 'record.get("publish_status") == "PublishReturnedSuccess"' in method
    assert '"FinalPrintableTemplate", "verified-final-template"' in method
    assert "getNodesByClass" not in method

from DENTOROS2Bridge import ROS2_JOINT_SI_ORDER  # noqa: E402
from DENTOStep6Planning import TaskSpaceRoi  # noqa: E402
from DENTOStep6State import (  # noqa: E402
    build_task_home,
    build_robot_environment_snapshot,
    canonical_json,
    fingerprint,
    parse_manual_simulation_record,
    parse_task_home,
)
import DENTORobotWorkflowFacade as workflow_facade_module  # noqa: E402
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
        self.parent_id = None
        self.attributes = {}

    def GetID(self):
        return self.node_id

    def SetAndObserveTransformNodeID(self, node_id):
        self.parent_id = node_id

    def GetTransformNodeID(self):
        return self.parent_id

    def SetMatrixTransformToParent(self, matrix):
        self.matrix = matrix

    def GetAttribute(self, name):
        return self.attributes.get(name)

    def SetAttribute(self, name, value):
        if value is None:
            self.attributes.pop(name, None)
        else:
            self.attributes[name] = str(value)


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
        self.inputVolume = object()
        self.teethSegmentation = object()
        self.step6PlanningContextImported = True
        self.robotBaseTransform = FakeBase()
        self.robotBaseMountLocked = False
        self.step6BasePlacementStatus = "Unlocked"
        self.step6BasePlacementSource = "test"
        self.step6BasePlacementRevision = 0
        self.robotJoint1Deg = 0.0
        self.robotJoint2Mm = 0.0
        self.robotJoint3Deg = 0.0
        self.robotJoint4Mm = 0.0
        self.robotJoint5Deg = 0.0
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
        self.tcp_drag_enabled = False
        self.tcp_nudges = []

    def set_moveit_tcp_goal_drag_enabled(self, enabled):
        self.tcp_drag_enabled = bool(enabled)
        return True, "enabled" if enabled else "disabled", object() if enabled else None

    def ensure_moveit_tcp_goal_transform(self):
        return True, "goal transform ready", object()

    def nudge_moveit_tcp_goal(self, translation, rotation):
        self.tcp_nudges.append((translation, rotation))
        return True, "nudged", object(), ((1.0, 0.0, 0.0, 1.0),)

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
    warning = DENTORobotWorkflowFacade._tool_insertion_evidence(
        (0.0, 0.0, 0.0), (0.0, 0.0, maximum + 0.001)
    )
    assert passing["status"] == "Pass"
    assert abs(passing["remainingInsertionMarginMm"]) <= 1.0e-12
    assert warning["status"] == "Warning"
    assert warning["planningAllowed"]
    assert warning["code"] == "PROVISIONAL_INSERTION_ENVELOPE_WARNING"
    assert warning["requestedTargetPreserved"]
    assert abs(warning["requestedDrillingDepthMm"] - (maximum + 0.001)) <= 1.0e-12
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
    ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE = "DENTOBOT.RobotBasePlacementAuthority"
    ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY = "ManualSimulationBaseUnreviewed"
    ROBOT_BASE_MANUAL_REVIEWED_AUTHORITY = "ManualSimulationBaseReviewed"
    ROBOT_BASE_CIRCULAR_SNAP_AUTHORITY = "QuarantinedCircularMountPlane"

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
    def assistedTaskLimitsReviewed(parameter_node):
        try:
            return bool(
                json.loads(parameter_node.step6AssistedLimitProposalJson or "").get(
                    "reviewed"
                )
            )
        except (AttributeError, TypeError, ValueError):
            return False

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
        )

    def updateRobotJointPoses(self, positions):
        self.updated.append(dict(positions))

    def setRobotBaseMountLocked(self, parameter_node, locked):
        parameter_node.robotBaseMountLocked = bool(locked)
        parameter_node.robotBaseTransform.SetAttribute(
            self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
            self.ROBOT_BASE_MANUAL_REVIEWED_AUTHORITY
            if locked
            else self.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY,
        )

    @staticmethod
    def isRobotBaseTransformNode(base):
        return isinstance(base, FakeBase)

    @staticmethod
    def _worldMatrixFromTransform(base):
        return base.matrix or FakePoseMatrix(
            ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        )

    @staticmethod
    def _vtkFromNumpyMatrix(matrix):
        result = FakePoseMatrix(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
        result.values = [[float(value) for value in row] for row in matrix]
        return result

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


def test_tcp_ik_facade_requires_authoritative_success_and_complete_finite_j1_j5():
    facade, _parameter_node, _logic, bridge = make_facade()
    valid = {name: float(index) for index, name in enumerate(ROS2_JOINT_SI_ORDER)}
    accepted_before = dict(bridge.accepted)

    bridge.solve_moveit_tcp_goal = lambda: (True, "valid", valid)
    result = facade.solveIk()
    assert result.success is True
    assert result.code == "ik_solved"
    assert result.payload == valid
    assert result.details["collisionAwareValidated"] is True
    assert result.details["authoritativeStaticValidity"] is True

    bridge.solve_moveit_tcp_goal = lambda: (False, "static validity unknown", valid)
    result = facade.solveIk()
    assert result.success is False
    assert result.payload is None
    assert result.details["collisionAwareValidated"] is False
    assert result.details["authoritativeStaticValidity"] is False
    assert result.details["candidateJointPositionsSi"] == valid

    for invalid in (
        {name: value for name, value in valid.items() if name != ROS2_JOINT_SI_ORDER[-1]},
        {**valid, ROS2_JOINT_SI_ORDER[0]: float("nan")},
        {**valid, "unexpected_joint": 0.0},
    ):
        bridge.solve_moveit_tcp_goal = lambda invalid=invalid: (
            True,
            "bridge reported valid",
            invalid,
        )
        result = facade.solveIk()
        assert result.success is False
        assert result.payload is None
        assert result.details["authoritativeStaticValidity"] is False

    bridge.solve_moveit_tcp_goal = lambda: (_ for _ in ()).throw(
        RuntimeError("validation unavailable")
    )
    result = facade.solveIk()
    assert result.success is False
    assert result.payload is None
    assert result.details["authoritativeStaticValidity"] is False
    assert bridge.accepted == accepted_before


def test_tcp_drag_facade_is_explicit_and_nudge_is_display_only():
    facade, _parameter_node, _logic, bridge = make_facade()

    prepared = facade.ensureTcpGoal()
    assert prepared.success and prepared.code == "tcp_goal_ready"
    assert not bridge.tcp_drag_enabled

    invalid_toggle = facade.setTcpDragEnabled(1)
    assert not invalid_toggle.success
    assert not bridge.tcp_drag_enabled

    enabled = facade.setTcpDragEnabled(True)
    assert enabled.success and enabled.code == "tcp_drag_enabled"
    assert enabled.details == {"dragEnabled": True}
    assert bridge.tcp_drag_enabled

    goal = facade.nudgeTcpGoal(
        {
            "translation_ras_mm": (1.0, 0.0, 0.0),
            "rotation_local_rpy_deg": (0.0, 0.0, 0.0),
            "source": "keyboard",
        }
    )
    assert goal.success and goal.code == "tcp_goal_nudged"
    assert goal.details["acceptedRobotStateChanged"] is False
    assert goal.details["routeAuthority"] is False
    assert goal.payload["currentPoseParent"][0][3] == 1.0
    assert bridge.tcp_nudges == [((1.0, 0.0, 0.0), (0.0, 0.0, 0.0))]
    assert bridge.applied == [] and bridge.phase_calls == []

    invalid_nudge = facade.nudgeTcpGoal(
        {"translation_ras_mm": (1.0, 0.0, 0.0), "source": "keyboard"}
    )
    assert not invalid_nudge.success
    assert len(bridge.tcp_nudges) == 1

    disabled = facade.setTcpDragEnabled(False)
    assert disabled.success and disabled.code == "tcp_drag_disabled"
    assert not bridge.tcp_drag_enabled


class FakePreviewTimer:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_interrupted_guarded_preview_latches_prefix_and_blocks_repeated_return():
    facade, _parameter_node, _logic, bridge = make_facade()
    home = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    accepted = {name: 0.01 for name in ROS2_JOINT_SI_ORDER}
    facade._accepted_motion_history = [
        {"positions": home, "phase": "home"},
        {"positions": accepted, "phase": "approach"},
    ]
    facade._motion_history_task_fingerprint = "task-a"
    facade._guarded_preview_task_fingerprint = "task-a"
    facade._guarded_preview_phase = "drilling"
    facade._guarded_preview_active = True
    facade._preview_timer = FakePreviewTimer()
    facade._preview_index = 1
    bridge.accepted = dict(accepted)
    bridge.monitored_joint_positions_si = lambda: dict(accepted)

    stopped = facade.stopGuardedPreview()

    assert stopped.success and stopped.code == "preview_stopped_return_required"
    evidence = stopped.details["incompletePreview"]
    assert evidence["capturedHomePositionsSi"] == home
    assert evidence["acceptedPrefix"] == [
        {"phase": "home", "positionsSi": home},
        {"phase": "approach", "positionsSi": accepted},
    ]
    assert evidence["acceptedWaypointCount"] == 1
    assert evidence["lastAcceptedPositionsSi"] == accepted
    assert evidence["lastMonitoredPositionsSi"] == accepted
    assert evidence["firstRejected"] is None
    assert evidence["endpointVerified"] is False

    first_return = facade.returnToTaskHome()
    second_return = facade.returnToTaskHome()
    assert not first_return.success and first_return.code == "guarded_return_partial_phase"
    assert not second_return.success and second_return.code == "guarded_return_partial_phase"
    assert bridge.phase_calls == []


def test_incomplete_preview_blocks_home_and_manual_joint_motion_paths():
    facade, parameter_node, logic, bridge = make_facade()
    facade._incomplete_preview_evidence = {
        "status": "Incomplete",
        "endpointVerified": False,
        "acceptedPrefix": [],
        "firstRejected": None,
    }
    original_display = (
        parameter_node.robotJoint1Deg,
        parameter_node.robotJoint2Mm,
        parameter_node.robotJoint3Deg,
        parameter_node.robotJoint4Mm,
        parameter_node.robotJoint5Deg,
    )

    def forbidden_context_access():
        raise AssertionError("blocked motion path accessed workflow context")

    facade._require_context = forbidden_context_access
    results = (
        facade.applyTaskHome(),
        facade.saveTaskHome(),
        facade.requestJointValue(1, 15.0),
        facade.previewPlan(),
        facade.requestCurrentJointState(),
    )

    assert all(not result.success for result in results)
    assert all(result.code == "incomplete_preview_blocks_motion" for result in results)
    assert all(result.details["incompletePreview"]["status"] == "Incomplete"
               for result in results)
    assert bridge.applied == []
    assert bridge.phase_calls == []
    assert facade._preview_timer is None
    assert logic.updated == []
    assert original_display == (
        parameter_node.robotJoint1Deg,
        parameter_node.robotJoint2Mm,
        parameter_node.robotJoint3Deg,
        parameter_node.robotJoint4Mm,
        parameter_node.robotJoint5Deg,
    )


def test_incomplete_preview_blocks_base_pose_and_lock_changes():
    facade, parameter_node, logic, bridge = make_facade()
    base = parameter_node.robotBaseTransform
    facade._incomplete_preview_evidence = {
        "status": "Incomplete",
        "endpointVerified": False,
        "acceptedPrefix": [],
        "firstRejected": None,
    }

    def forbidden_context_access():
        raise AssertionError("blocked base path accessed workflow context")

    facade._require_context = forbidden_context_access
    results = (
        facade.setBasePose([[1.0, 0.0, 0.0, 1.0]]),
        facade.lockBase(),
        facade.unlockBase(),
    )

    assert all(not result.success for result in results)
    assert all(result.code == "incomplete_preview_blocks_motion" for result in results)
    assert parameter_node.robotBaseTransform is base
    assert base.matrix is None
    assert not parameter_node.robotBaseMountLocked
    assert logic.synced == 0
    assert bridge.applied == []
    assert bridge.phase_calls == []


def _manual_base_test_matrix(x_mm=0.0):
    return [
        1.0, 0.0, 0.0, float(x_mm),
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def test_detached_manual_base_stage_and_cancel_leave_accepted_state_unchanged():
    facade, parameter_node, _logic, _bridge = make_facade()
    facade._completed_phase = "approach"
    facade._phase_sequence = 4
    result = facade.stageManualBaseReview(_manual_base_test_matrix(12.5))

    assert result.success and result.code == "manual_base_review_staged"
    assert result.details["staged"]
    assert result.details["candidateMatrixWorldRasMm"] == _manual_base_test_matrix(12.5)
    assert result.details["acceptedMatrixWorldRasMm"] == _manual_base_test_matrix()
    assert parameter_node.robotBaseTransform.matrix is None
    assert not parameter_node.robotBaseMountLocked
    assert facade._completed_phase == "approach"
    assert facade._phase_sequence == 4
    assert facade._manual_simulation_events == []

    state = facade.manualBaseReview()
    assert state.success and state.details["staged"]
    assert state.details["candidateMatrixWorldRasMm"] == _manual_base_test_matrix(12.5)
    cancelled = facade.cancelManualBaseReview()
    assert cancelled.success and not cancelled.details["staged"]
    assert cancelled.details["candidateMatrixWorldRasMm"] is None
    assert parameter_node.robotBaseTransform.matrix is None
    assert not parameter_node.robotBaseMountLocked
    assert facade._completed_phase == "approach"
    assert facade._phase_sequence == 4


def test_detached_manual_base_rejects_nonrigid_or_nonfinite_matrix():
    facade, parameter_node, _logic, _bridge = make_facade()
    scaled = _manual_base_test_matrix()
    scaled[0] = 2.0
    reflected = _manual_base_test_matrix()
    reflected[0] = -1.0
    nonfinite = _manual_base_test_matrix()
    nonfinite[3] = float("nan")

    results = tuple(
        facade.stageManualBaseReview(matrix)
        for matrix in (scaled, reflected, nonfinite, _manual_base_test_matrix()[:-1])
    )

    assert all(not result.success for result in results)
    assert all(result.code == "manual_base_review_rejected" for result in results)
    assert facade.manualBaseReview().details["staged"] is False
    assert parameter_node.robotBaseTransform.matrix is None
    assert not parameter_node.robotBaseMountLocked


def test_detached_manual_base_candidate_rejects_changed_case_identity():
    facade, parameter_node, _logic, _bridge = make_facade()
    staged = facade.stageManualBaseReview(_manual_base_test_matrix(7.0))
    assert staged.success
    parameter_node.teethSegmentation = object()

    restage = facade.stageManualBaseReview(_manual_base_test_matrix(11.0))
    assert not restage.success and restage.code == "manual_base_review_stale"
    assert restage.details["candidateMatrixWorldRasMm"] == _manual_base_test_matrix(7.0)
    assert restage.details["restageRejection"]["code"] == "manual_base_review_stale"

    result = facade.acceptManualBaseReview()

    assert not result.success and result.code == "manual_base_review_stale"
    assert result.details["staged"]
    assert result.details["identityStatus"] == "case_or_base_identity_changed"
    assert result.details["candidateMatrixWorldRasMm"] == _manual_base_test_matrix(7.0)
    assert parameter_node.robotBaseTransform.matrix is None
    assert not parameter_node.robotBaseMountLocked


def test_manual_base_candidate_cannot_be_replaced_while_acceptance_is_uncertain():
    facade, parameter_node, _logic, _bridge = make_facade()
    candidate = _manual_base_test_matrix(18.0)
    assert facade.stageManualBaseReview(candidate).success
    failure_evidence = {
        "code": "manual_base_acceptance_unknown",
        "stage": "lock",
    }
    facade._manual_base_review_failure = dict(failure_evidence)
    facade._manual_base_acceptance_uncertain = "native state is unknown"

    result = facade.stageManualBaseReview(_manual_base_test_matrix(24.0))

    assert not result.success and result.code == "manual_base_acceptance_unknown"
    assert result.details["staged"]
    assert result.details["candidateMatrixWorldRasMm"] == candidate
    assert result.details["failureEvidence"] == failure_evidence
    assert facade._manual_base_review["candidateMatrixWorldRasMm"] == candidate
    assert facade._manual_base_review_failure == failure_evidence
    assert facade._manual_base_acceptance_uncertain
    assert facade._manual_simulation_base_matrix(parameter_node) == _manual_base_test_matrix()


def test_manual_base_review_identity_handles_host_stubs_and_slicer_node_methods():
    facade, _parameter_node, _logic, _bridge = make_facade()
    base = FakeBase()

    host_identity = facade._manual_base_review_identity(SimpleNamespace(), base)

    assert host_identity["inputVolume"] == "none"
    assert host_identity["teethSegmentation"] == "none"
    assert host_identity["caseNodeRevisions"] == {
        "inputVolume": None,
        "teethSegmentation": None,
    }

    class FakeSlicerNode:
        def __init__(self, node_id, mtime):
            self.node_id = node_id
            self.mtime = mtime

        def GetID(self):
            return self.node_id

        def GetScene(self):
            return None

        def GetMTime(self):
            return self.mtime

    slicer_parameter_node = SimpleNamespace(
        inputVolume=FakeSlicerNode("volume", 12),
        teethSegmentation=FakeSlicerNode("segmentation", 34),
        step6BasePlacementRevision=5,
    )
    slicer_identity = facade._manual_base_review_identity(slicer_parameter_node, base)

    assert slicer_identity["inputVolume"] == "volume"
    assert slicer_identity["teethSegmentation"] == "segmentation"
    assert slicer_identity["caseNodeRevisions"] == {
        "inputVolume": 12,
        "teethSegmentation": 34,
    }
    assert slicer_identity["placementRevision"] == 5


def test_detached_manual_base_accept_uses_existing_pose_and_lock_owners():
    facade, parameter_node, _logic, _bridge = make_facade()
    candidate = _manual_base_test_matrix(18.0)
    assert facade.stageManualBaseReview(candidate).success

    result = facade.acceptManualBaseReview()

    assert result.success and result.code == "base_locked"
    assert result.details["acceptanceStatus"] == "accepted"
    assert result.details["candidateMatrixWorldRasMm"] is None
    assert result.details["acceptedMatrixWorldRasMm"] == candidate
    assert parameter_node.robotBaseMountLocked
    assert facade._manual_simulation_base_matrix(parameter_node) == candidate
    assert facade.manualBaseReview().details["staged"] is False


def test_detached_manual_base_failed_lock_restores_base_and_latches_unknown():
    facade, parameter_node, logic, _bridge = make_facade()
    candidate = _manual_base_test_matrix(21.0)
    assert facade.stageManualBaseReview(candidate).success

    def fail_after_lock_attempt(node, locked):
        node.robotBaseMountLocked = bool(locked)
        node.robotBaseTransform.SetAttribute(
            logic.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
            logic.ROBOT_BASE_MANUAL_REVIEWED_AUTHORITY,
        )
        raise RuntimeError("simulated lock-side failure")

    logic.setRobotBaseMountLocked = fail_after_lock_attempt
    result = facade.acceptManualBaseReview()

    assert not result.success and result.code == "manual_base_acceptance_unknown"
    assert result.details["staged"]
    assert result.details["candidateMatrixWorldRasMm"] == candidate
    assert result.details["failureEvidence"]["stage"] == "lock"
    assert result.details["failureEvidence"]["rollbackStatus"] == "unknown"
    assert parameter_node.robotBaseTransform.matrix is not None
    assert facade._manual_simulation_base_matrix(parameter_node) == _manual_base_test_matrix()
    assert not parameter_node.robotBaseMountLocked
    assert parameter_node.robotBaseTransform.GetAttribute(
        logic.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE
    ) is None
    blocked = facade.acceptManualBaseReview()
    assert not blocked.success and blocked.code == "manual_base_acceptance_unknown"
    assert facade.manualBaseReview().details["failureEvidence"]["stage"] == "lock"
    cancelled = facade.cancelManualBaseReview()
    assert not cancelled.success and cancelled.code == "manual_base_acceptance_unknown"
    assert cancelled.details["staged"]
    assert cancelled.details["candidateMatrixWorldRasMm"] == candidate
    assert cancelled.details["failureEvidence"]["stage"] == "lock"


def test_manual_base_review_cannot_be_cancelled_while_acceptance_is_uncertain():
    facade, _parameter_node, _logic, _bridge = make_facade()
    candidate = _manual_base_test_matrix(18.0)
    assert facade.stageManualBaseReview(candidate).success
    facade._manual_base_acceptance_uncertain = "native state is unknown"
    facade._manual_base_review_failure = {
        "code": "manual_base_acceptance_unknown",
        "stage": "lock",
    }

    result = facade.cancelManualBaseReview()

    assert not result.success and result.code == "manual_base_acceptance_unknown"
    assert result.details["candidateMatrixWorldRasMm"] == candidate
    assert result.details["failureEvidence"] == facade._manual_base_review_failure
    assert facade._manual_base_review["candidateMatrixWorldRasMm"] == candidate


def _manual_base_reconciliation_probe(
    *, include_audit=True, acknowledgement_status="Acknowledged", acknowledged_object_ids=None
):
    facade, parameter_node, logic, _bridge = make_facade()
    candidate = _manual_base_test_matrix(21.0)
    assert facade.stageManualBaseReview(candidate).success
    failure_evidence = {
        "code": "manual_base_acceptance_unknown",
        "stage": "lock",
        "rollbackStatus": "unknown",
    }
    facade._manual_base_review_failure = dict(failure_evidence)
    facade._manual_base_acceptance_uncertain = "native scene state is unknown"
    parameter_node.robotBaseTransform.active = True

    object_ids = tuple(f"obstacle-{index}" for index in range(4))
    audit = (
        SimpleNamespace(
            status=(
                "Acknowledged"
                if acknowledgement_status == "Acknowledged"
                else "RuntimeAcknowledgementFailed"
            ),
            base_fingerprint="base-current",
            object_records=tuple(
                {"outgoing_collision_object_id": object_id}
                for object_id in object_ids
            ),
            runtime_acknowledgement={
                "status": acknowledgement_status,
                "acknowledged_object_ids": (
                    object_ids
                    if acknowledged_object_ids is None
                    else acknowledged_object_ids
                ),
            },
            audit_fingerprint="audit-current",
        )
        if include_audit
        else None
    )
    audit_state = {"synced": False, "audit": audit, "reads": []}

    def sync_scene(_parameter_node):
        logic.synced += 1
        audit_state["synced"] = True
        return len(object_ids)

    def read_audit(_parameter_node):
        audit_state["reads"].append(audit_state["synced"])
        return audit_state["audit"] if audit_state["synced"] else None

    logic.syncStep6MoveItPlanningScene = sync_scene
    logic.collisionSceneAuditRecord = read_audit
    logic.robotBaseFingerprint = lambda _node: "base-current"
    facade.taskHomeRuntimeValidated = lambda _node: False
    return facade, parameter_node, logic, candidate, failure_evidence, audit_state


def test_manual_base_reconciliation_resyncs_only_the_accepted_baseline():
    (
        facade,
        parameter_node,
        logic,
        candidate,
        failure_evidence,
        audit_state,
    ) = _manual_base_reconciliation_probe()
    facade._runtime_validated_task_home_key = "old-home"
    facade._runtime_task_home_evidence = {"old": True}
    facade._runtime_validated_workspace_key = "old-workspace"

    result = facade.reconcileManualBaseAcceptance()

    assert result.success and result.code == "manual_base_acceptance_reconciled"
    assert audit_state["reads"] == [True, True]
    assert logic.synced == 1
    assert result.details["reconciliationStatus"] == "acknowledged"
    assert result.details["obstacleCount"] == 4
    assert result.details["acknowledgedObjectIds"] == tuple(
        f"obstacle-{index}" for index in range(4)
    )
    assert result.details["candidateMatrixWorldRasMm"] == candidate
    assert result.details["acceptedMatrixWorldRasMm"] == (
        facade._manual_simulation_base_matrix(parameter_node)
    )
    assert result.details["acceptedBaselineMatrixWorldRasMm"] == result.details[
        "acceptedMatrixWorldRasMm"
    ]
    assert result.details["acceptedMatrixWorldRasMm"] != candidate
    assert result.details["failureEvidence"] == failure_evidence
    assert result.details["staged"]
    assert facade._manual_base_review["candidateMatrixWorldRasMm"] == candidate
    assert not facade._manual_base_acceptance_uncertain
    assert facade._manual_base_review_failure == failure_evidence
    assert facade._manual_simulation_base_matrix(parameter_node) == _manual_base_test_matrix()
    assert not parameter_node.robotBaseMountLocked
    assert facade._planning_scene_synchronized
    assert facade._runtime_validated_task_home_key == ""
    assert facade._runtime_task_home_evidence == {}
    assert facade._runtime_validated_workspace_key == ""


def test_manual_base_reconciliation_rejects_stale_case_identity_without_sync():
    facade, parameter_node, logic, _candidate, _failure, audit_state = (
        _manual_base_reconciliation_probe()
    )
    parameter_node.teethSegmentation = object()

    result = facade.reconcileManualBaseAcceptance()

    assert not result.success and result.code == "manual_base_review_stale"
    assert logic.synced == 0
    assert audit_state["reads"] == []
    assert facade._manual_base_acceptance_uncertain
    blocked = facade.acceptManualBaseReview()
    assert not blocked.success and blocked.code == "manual_base_acceptance_unknown"


def test_manual_base_reconciliation_requires_complete_acknowledged_native_readback():
    for options in (
        {"include_audit": False},
        {"acknowledgement_status": "NotAcknowledged"},
        {"acknowledged_object_ids": ("obstacle-0", "obstacle-1")},
    ):
        facade, _parameter_node, logic, _candidate, _failure, audit_state = (
            _manual_base_reconciliation_probe(**options)
        )

        result = facade.reconcileManualBaseAcceptance()

        assert not result.success
        assert result.code == "manual_base_reconciliation_unacknowledged"
        assert logic.synced == 1
        assert audit_state["reads"] == [True, True]
        assert facade._manual_base_acceptance_uncertain
        assert not facade._planning_scene_synchronized
        assert facade._planning_scene_object_count == 0
        blocked = facade.acceptManualBaseReview()
        assert not blocked.success and blocked.code == "manual_base_acceptance_unknown"


def test_manual_base_reconciliation_keeps_latch_if_accepted_matrix_changes_during_sync():
    facade, parameter_node, logic, candidate, _failure, _audit_state = (
        _manual_base_reconciliation_probe()
    )
    original_sync = logic.syncStep6MoveItPlanningScene

    def sync_then_change_base(node):
        count = original_sync(node)
        changed = _manual_base_test_matrix(1.0)
        node.robotBaseTransform.SetMatrixTransformToParent(
            logic._vtkFromNumpyMatrix(
                [changed[row * 4 : row * 4 + 4] for row in range(4)]
            )
        )
        return count

    logic.syncStep6MoveItPlanningScene = sync_then_change_base

    result = facade.reconcileManualBaseAcceptance()

    assert not result.success
    assert result.code == "manual_base_reconciliation_stale"
    assert facade._manual_base_acceptance_uncertain
    assert facade._manual_base_review["candidateMatrixWorldRasMm"] == candidate
    assert not facade._planning_scene_synchronized
    blocked = facade.acceptManualBaseReview()
    assert not blocked.success and blocked.code == "manual_base_acceptance_unknown"


def test_guard_rejection_latches_identity_matched_evaluated_waypoint():
    facade, _parameter_node, _logic, bridge = make_facade()
    home = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    accepted = {name: 0.01 for name in ROS2_JOINT_SI_ORDER}
    requested = {name: 0.02 for name in ROS2_JOINT_SI_ORDER}
    facade._accepted_motion_history = [
        {"positions": home, "phase": "home"},
        {"positions": accepted, "phase": "approach"},
    ]
    facade._guarded_preview_task_fingerprint = "task-b"
    facade._guarded_preview_phase = "drilling"
    request = {
        "taskFingerprint": "task-b",
        "guardSessionId": "session-b",
        "phase": "drilling",
        "sequence": 12,
        "waypointIndex": 0,
        "requestedPositionsSi": requested,
    }
    bridge.task_status = SimpleNamespace(
        task_fingerprint="task-b",
        guard_session_id="session-b",
        phase="drilling",
        sequence=12,
        accepted=False,
        validate_only=False,
        evaluated_positions=tuple(0.015 for _ in ROS2_JOINT_SI_ORDER),
        evaluated_sample_index=3,
        first_rejection_interpolation_fraction=0.75,
        first_body="arm_link_2",
        second_body="case_tooth",
        reason="collision rejected",
    )

    rejected = {
        "phase": "drilling",
        "sequence": 12,
        "waypointIndex": 0,
        "requestedPositionsSi": requested,
        **facade._preview_request_status(
            request,
            accepted=False,
            message=(
                "Task guard rejected drilling sequence 12: collision rejected "
                "(arm_link_2 ↔ case_tooth)"
            ),
        ),
    }
    evidence = facade._latch_incomplete_preview(
        "The phase guard rejected a requested waypoint: collision rejected",
        request=request,
        first_rejected=rejected,
    )

    assert evidence["acceptedWaypointCount"] == 1
    assert evidence["firstRejected"]["requestedPositionsSi"] == requested
    assert evidence["firstRejected"]["evaluatedStateStatus"] == "known"
    assert evidence["firstRejected"]["evaluatedPositionsSi"] == {
        name: 0.015 for name in ROS2_JOINT_SI_ORDER
    }
    assert evidence["firstRejected"]["evaluatedSampleIndex"] == 3
    assert evidence["firstRejected"]["firstRejectionInterpolationFraction"] == 0.75
    assert evidence["firstRejected"]["firstBody"] == "arm_link_2"
    assert evidence["firstRejected"]["secondBody"] == "case_tooth"
    assert evidence["firstRejected"]["nativeReason"] == "collision rejected"


def test_stopped_drill_request_appends_accepted_inflight_waypoint_to_full_prefix():
    facade, _parameter_node, _logic, bridge = make_facade()
    home = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    approach = {name: 0.01 for name in ROS2_JOINT_SI_ORDER}
    drill = {name: 0.02 for name in ROS2_JOINT_SI_ORDER}
    facade._accepted_motion_history = [
        {"positions": home, "phase": "home"},
        {"positions": approach, "phase": "approach"},
    ]
    facade._motion_history_task_fingerprint = "task-d"
    facade._guarded_preview_task_fingerprint = "task-d"
    facade._guarded_preview_phase = "drilling"
    request = {
        "taskFingerprint": "task-d",
        "guardSessionId": "session-d",
        "phase": "drilling",
        "sequence": 17,
        "waypointIndex": 0,
        "acceptedPrefixCount": 1,
        "requestedPositionsSi": drill,
    }
    bridge.task_status = SimpleNamespace(
        task_fingerprint="task-d",
        guard_session_id="session-d",
        phase="drilling",
        sequence=17,
        accepted=True,
        validate_only=False,
        reason="accepted",
        evaluated_positions=tuple(drill[name] for name in ROS2_JOINT_SI_ORDER),
    )

    evidence = facade._latch_incomplete_preview(
        "Manual Stop while a Drill waypoint was awaiting acknowledgement.",
        request=request,
    )
    facade._append_motion_history_waypoint(drill, "drilling", "task-d")
    facade._record_incomplete_preview_request_result(
        request, accepted=True, message="accepted"
    )

    assert evidence["firstRejected"] is None
    assert evidence["acceptedWaypointCount"] == 2
    assert evidence["acceptedPrefix"][-1] == {
        "phase": "drilling",
        "positionsSi": drill,
    }
    assert evidence["lastAcceptedHistoryPositionsSi"] == drill
    assert evidence["pendingRequestOutcome"]["accepted"] is True


def test_pending_request_rejected_after_manual_stop_records_first_rejection():
    facade, _parameter_node, _logic, bridge = make_facade()
    home = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    requested = {name: 0.02 for name in ROS2_JOINT_SI_ORDER}
    facade._accepted_motion_history = [{"positions": home, "phase": "home"}]
    facade._guarded_preview_task_fingerprint = "task-e"
    facade._guarded_preview_phase = "approach"
    request = {
        "taskFingerprint": "task-e",
        "guardSessionId": "session-e",
        "phase": "approach",
        "sequence": 1,
        "waypointIndex": 0,
        "acceptedPrefixCount": 0,
        "requestedPositionsSi": requested,
    }
    evidence = facade._latch_incomplete_preview(
        "Manual Stop while the first waypoint was awaiting acknowledgement.",
        request=request,
    )
    bridge.task_status = SimpleNamespace(
        task_fingerprint="task-e",
        guard_session_id="session-e",
        phase="approach",
        sequence=1,
        accepted=False,
        validate_only=False,
        evaluated_positions=tuple(0.01 for _ in ROS2_JOINT_SI_ORDER),
        evaluated_sample_index=2,
        reason="collision rejected",
    )

    facade._record_incomplete_preview_request_result(
        request,
        accepted=False,
        message="Task guard rejected approach sequence 1: collision rejected",
    )

    assert evidence["firstRejected"]["requestedPositionsSi"] == requested
    assert evidence["firstRejected"]["nativeReason"] == "collision rejected"
    assert evidence["firstRejected"]["evaluatedSampleIndex"] == 2


def test_timed_out_guard_request_does_not_reuse_same_sequence_stale_status():
    facade, _parameter_node, _logic, bridge = make_facade()
    request = {
        "taskFingerprint": "task-timeout",
        "guardSessionId": "current-session",
        "phase": "approach",
        "sequence": 1,
    }
    bridge.task_status = SimpleNamespace(
        task_fingerprint="task-timeout",
        guard_session_id="current-session",
        phase="approach",
        sequence=1,
        accepted=False,
        validate_only=False,
        evaluated_positions=tuple(0.015 for _ in ROS2_JOINT_SI_ORDER),
        evaluated_sample_index=3,
        first_rejection_interpolation_fraction=0.75,
        first_body="old_link",
        second_body="old_obstacle",
        reason="prior collision",
    )

    evidence = facade._preview_request_status(
        request,
        accepted=False,
        message="Task guard did not answer the phased simulation command.",
    )

    assert evidence["statusIdentityMatched"] is True
    assert evidence["statusMessageMatched"] is False
    assert evidence["evaluatedStateStatus"] == "unknown"
    assert evidence["evaluatedPositionsSi"] is None
    assert evidence["evaluatedSampleIndex"] is None
    assert evidence["firstBody"] == ""
    assert evidence["nativeReason"] == (
        "Task guard did not answer the phased simulation command."
    )


def test_rejected_first_guarded_waypoint_latches_with_zero_accepted_motion():
    facade, _parameter_node, _logic, bridge = make_facade()
    home = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    facade._accepted_motion_history = [{"positions": home, "phase": "home"}]
    facade._guarded_preview_task_fingerprint = "task-c"
    facade._guarded_preview_phase = "approach"
    request = {
        "taskFingerprint": "task-c",
        "phase": "approach",
        "sequence": 1,
        "waypointIndex": 0,
        "requestedPositionsSi": {name: 0.01 for name in ROS2_JOINT_SI_ORDER},
    }
    bridge.task_status = SimpleNamespace(
        task_fingerprint="different-task",
        phase="approach",
        sequence=1,
        accepted=False,
        validate_only=False,
        evaluated_positions=(0.005,),
        reason="stale status",
    )
    rejected = {
        "phase": "approach",
        "sequence": 1,
        "waypointIndex": 0,
        "requestedPositionsSi": request["requestedPositionsSi"],
        **facade._preview_request_status(
            request, accepted=False, message="native rejection"
        ),
    }

    evidence = facade._latch_incomplete_preview(
        "First guarded waypoint was rejected.",
        request=request,
        first_rejected=rejected,
    )

    assert evidence["acceptedWaypointCount"] == 0
    assert evidence["capturedHomePositionsSi"] == home
    assert evidence["firstRejected"]["evaluatedStateStatus"] == "unknown"
    assert evidence["firstRejected"]["evaluatedPositionsSi"] is None
    assert evidence["firstRejected"]["nativeReason"] == "native rejection"


def test_guarded_preview_rejection_and_return_paths_use_persistent_latch():
    source = (HELPERS / "DENTORobotWorkflowFacade.py").read_text(encoding="utf-8")
    preview = source.split("    def previewPhase(", 1)[1].split(
        "    def _apply_positions_si", 1
    )[0]
    rejected = preview.split("                if not ok:", 1)[1].split(
        "                status_getter", 1
    )[0]
    assert "first_rejected=failure" in rejected
    assert "_record_incomplete_preview_request_result" in rejected
    assert rejected.index("_latch_incomplete_preview") < rejected.index(
        "_clear_phase_session"
    )

    return_home = source.split("    def returnToTaskHome(", 1)[1].split(
        "    def ", 1
    )[0]
    assert return_home.index("if self._incomplete_preview_evidence is not None") < (
        return_home.index("self.stopGuardedPreview()")
    )
    assert '"incomplete_preview_blocks_motion"' in preview


def test_default_task_space_roi_uses_current_opened_gap_line_only():
    class FakeGapLine:
        def __init__(self, points, role="Step6CaseJawGapLine"):
            self.points = tuple(tuple(point) for point in points)
            self.role = role

        def IsA(self, class_name):
            return class_name == "vtkMRMLMarkupsLineNode"

        def GetAttribute(self, name):
            return self.role if name == "DENTOBOT.MarkupsRole" else None

        def GetNumberOfDefinedControlPoints(self):
            return len(self.points)

        def GetNthControlPointPositionWorld(self, index, point):
            point[:] = self.points[index]

        def GetID(self):
            return "gap-line-1"

    facade, parameter_node, logic, _bridge = make_facade()
    logic.STEP6_CASE_JAW_GAP_LINE_ROLE = "Step6CaseJawGapLine"
    logic.opening_issues = ()
    logic.step6CaseJawOpeningFreshnessIssues = (
        lambda _parameter: logic.opening_issues
    )
    parameter_node.caseFoundationOpeningRevision = 8
    parameter_node.step6CaseJawGapLine = FakeGapLine(
        ((2.0, 4.0, -6.0), (8.0, 10.0, 2.0))
    )

    result = facade.defaultTaskSpaceRoi()

    assert result.success
    assert result.payload == {
        "centerWorldRasMm": (5.0, 7.0, -2.0),
        "dimensionsMm": (200.0, 200.0, 200.0),
        "openingRevision": 8,
        "gapLineNodeId": "gap-line-1",
    }
    assert logic.updated == [] and logic.synced == 0

    logic.opening_issues = ("Case Foundation pose is stale.",)
    stale = facade.defaultTaskSpaceRoi()
    assert not stale.success and stale.code == "case_foundation_stale"

    logic.opening_issues = ()
    parameter_node.step6CaseJawGapLine = None
    missing = facade.defaultTaskSpaceRoi()
    assert not missing.success and missing.code == "incisor_gap_line_missing"

    parameter_node.step6CaseJawGapLine = FakeGapLine(
        ((2.0, 4.0, -6.0), (8.0, 10.0, 2.0)), role="OtherLine"
    )
    wrong_role = facade.defaultTaskSpaceRoi()
    assert (
        not wrong_role.success
        and wrong_role.code == "incisor_gap_line_wrong_role"
    )

    parameter_node.step6CaseJawGapLine = FakeGapLine(
        ((2.0, 4.0, -6.0), (8.0, 10.0, 2.0), (0.0, 0.0, 0.0))
    )
    ambiguous = facade.defaultTaskSpaceRoi()
    assert (
        not ambiguous.success
        and ambiguous.code == "incisor_gap_line_ambiguous"
    )


def test_roi_edit_invalidates_workspace_without_dropping_motion_plan():
    class FakeModel:
        def __init__(self):
            self.attributes = {}

        def SetAttribute(self, name, value):
            self.attributes[name] = value

    facade, _parameter_node, logic, _bridge = make_facade()
    model = FakeModel()
    logic.robotWorkspaceModelNode = lambda: model
    invalidated_plans = []
    facade.invalidateMotionPlan = lambda: invalidated_plans.append(True)
    facade._motion_plan = object()
    prior_plan = facade._motion_plan
    facade._runtime_validated_workspace_key = "current-workspace"

    facade.invalidateWorkspaceRuntimeValidation(invalidate_motion_plan=False)

    assert facade._runtime_validated_workspace_key == ""
    assert facade._motion_plan is prior_plan
    assert invalidated_plans == []
    assert model.attributes == {
        "DENTOBOT.WorkspaceRuntimeValidated": "false",
        "DENTOBOT.WorkspaceState": "Stale",
    }


def test_confirm_task_requires_existing_task_home_record():
    facade, _parameter_node, logic, _bridge = make_facade()
    logic.taskHomeRecord = lambda _parameter: None

    result = facade.confirmTask()

    assert not result.success
    assert result.code == "task_home_required"


def test_roi_candidates_solve_ik_before_static_validity_and_stale_source_rejects():
    events = []

    class FakeModel:
        def __init__(self):
            self.attributes = {}

        def SetAttribute(self, name, value):
            self.attributes[name] = value

    facade, parameter_node, logic, bridge = make_facade()
    model = FakeModel()
    parameter_node.robotBaseTransform.active = True
    parameter_node.robotWorkspaceSampleCount = 50
    facade._planning_scene_synchronized = True
    facade.defaultTaskSpaceRoi = lambda: RobotActionResult(
        True,
        "workspace_roi_ready",
        "ready",
        payload={
            "centerWorldRasMm": (0.0, 0.0, 0.0),
            "dimensionsMm": (200.0, 200.0, 200.0),
            "openingRevision": 8,
            "gapLineNodeId": "gap-line-1",
        },
    )
    logic.collisionSceneAuditFreshnessIssues = lambda _parameter: ()
    logic.collisionSceneAuditRecord = lambda _parameter: SimpleNamespace(
        audit_fingerprint="scene-current"
    )
    logic.step6PlanningContextFreshnessIssues = lambda _parameter: ()
    logic.step6TrajectorySummary = lambda _parameter: {
        "isValid": True,
        "entryRas": (0.0, 0.0, 0.0),
        "targetRas": (0.0, 0.0, 1.0),
    }
    logic.step6TrajectoryRevision = lambda _parameter: "trajectory-current"
    logic.confirmedTaskRecord = lambda _parameter: None
    home_positions = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    home = SimpleNamespace(
        joint_names=ROS2_JOINT_SI_ORDER,
        joint_positions_si=tuple(home_positions.values()),
        to_dict=lambda: dict(home_positions),
    )
    logic.taskHomeRecord = lambda _parameter: home
    facade.taskHomeRuntimeValidated = lambda _parameter=None: True
    logic.robotBaseFingerprint = lambda _parameter: "base-current"
    logic.robotProfileFingerprint = lambda: "robot-current"
    logic.step6TaskLimitsFingerprint = lambda _parameter: "limits-current"
    # These IDs belong to the motion-control module's parameter node, never to
    # the workflow node; keep the workflow fake strict so a misread fails here.
    assert not hasattr(parameter_node, "robotNodeID")
    assert not hasattr(parameter_node, "motionControlNodeID")
    motion_parameter = SimpleNamespace(
        robotNodeID="robot-current", motionControlNodeID="motion-current"
    )
    bridge.get_motion_control_logic = lambda: SimpleNamespace(
        getParameterNode=lambda: motion_parameter
    )
    facade._strict_guard_policy_fingerprint = lambda: "policy-current"
    logic.robotWorkspaceModelNode = lambda: model

    def build_workspace(_parameter, *, sample_result, algorithm):
        assert algorithm == "ROI3D+PositionAxisIK"
        events.append("builder")
        return model, sample_result

    logic.createOrUpdateRobotWorkspace = build_workspace

    def build_pose(position, target, count):
        assert len(position) == len(target) == 3 and count == 1
        events.append("pose")
        return (object(),)

    bridge.tool_pose_matrices_world_mm = build_pose
    bridge.set_moveit_tcp_goal_matrix = lambda _pose: (
        events.append("goal") or (True, "accepted", None)
    )
    ik_attempts = []
    allow_solution = [False]

    def solve_ik(*, seed_joint_positions_si, avoid_collisions):
        assert seed_joint_positions_si == home_positions
        assert avoid_collisions is True
        ik_attempts.append(1)
        events.append("ik")
        if len(ik_attempts) < 50 or not allow_solution[0]:
            return False, "no position-axis solution", {}, {
                "termination_reason": "NoSolution",
                "collision_check_status": "Checked",
            }
        solved = dict(home_positions)
        solved[ROS2_JOINT_SI_ORDER[0]] = 0.1
        return True, "solved", solved, {
            "termination_reason": "Converged",
            "collision_check_status": "Checked",
        }

    bridge.solve_moveit_tcp_position_axis_goal = solve_ik
    bridge.check_moveit_static_joint_state = lambda _positions: (
        events.append("static") or (True, "valid", True)
    )
    bridge.compute_moveit_static_tcp_pose_base_mm = lambda _positions: (
        events.append("fk") or (True, "MoveIt FK", (1.0, 2.0, 3.0))
    )

    def reject_home_path(**_kwargs):
        assert _kwargs["responsive_wait"] is True
        assert _kwargs["context_is_current"]() is True
        motion_parameter.motionControlNodeID = "motion-replaced"
        assert _kwargs["context_is_current"]() is False
        motion_parameter.motionControlNodeID = "motion-current"
        events.append("ompl")
        return SimpleNamespace(
            success=False,
            waypoint_joint_vectors_si=(),
            planner_start_source="explicit",
            message="no Home path",
            native_planner_message="no Home path",
        )

    bridge.plan_moveit_joint_goal = reject_home_path
    roi = TaskSpaceRoi((2.0, 3.0, 4.0), (20.0, 24.0, 28.0))
    current_source = {"openingRevision": 8, "gapLineNodeId": "gap-line-1"}

    stale = facade.generateWorkspaceCloud(
        roi=roi,
        roi_source={"openingRevision": 7, "gapLineNodeId": "gap-line-1"},
    )
    assert not stale.success and stale.code == "workspace_roi_source_stale"
    assert events == []
    assert model.attributes["DENTOBOT.WorkspaceRuntimeValidated"] == "false"
    assert model.attributes["DENTOBOT.WorkspaceState"] == "Stale"

    no_ik = facade.generateWorkspaceCloud(roi=roi, roi_source=current_source)
    assert not no_ik.success and no_ik.code == "workspace_no_ik_samples"
    assert no_ik.details["candidateCounts"]["positionAxisIkAttemptCount"] == 50
    assert no_ik.details["candidateCounts"]["positionAxisIkFailureCount"] == 50
    assert no_ik.details["candidateCounts"]["moveItStaticValidityAttemptCount"] == 0
    assert no_ik.details["terminationStatusCounts"] == {"NoSolution": 50}
    assert events.count("ik") == 50
    assert not any(event in {"static", "fk", "builder", "ompl"} for event in events)
    assert model.attributes["DENTOBOT.WorkspaceRuntimeValidated"] == "false"
    assert model.attributes["DENTOBOT.WorkspaceState"] == "Stale"

    events.clear()
    ik_attempts.clear()
    allow_solution[0] = True
    result = facade.generateWorkspaceCloud(roi=roi, roi_source=current_source)

    assert not result.success
    assert result.code == "workspace_no_home_connected_samples"
    assert result.details["candidateCounts"]["roiCandidateCount"] == 50
    assert result.details["candidateCounts"]["positionAxisIkAttemptCount"] == 50
    assert result.details["candidateCounts"]["positionAxisIkSuccessCount"] == 1
    assert result.details["candidateCounts"]["moveItStaticValidityAttemptCount"] == 1
    assert result.details["candidateCounts"]["homeConnectivityEvaluatedCount"] == 1
    assert result.details["taskAxisStatus"] == "ProvisionalSelectedTrajectory"
    assert events.count("ik") == 50
    first_static = events.index("static")
    last_ik = max(index for index, event in enumerate(events) if event == "ik")
    assert last_ik < first_static
    assert events.index("static") < events.index("ompl")
    assert events.index("builder") < events.index("ompl")
    assert model.attributes["DENTOBOT.WorkspaceRuntimeValidated"] == "false"
    assert model.attributes["DENTOBOT.WorkspaceState"] == "Provisional"


def test_workspace_runtime_validity_requires_current_roi_source_and_trajectory():
    facade, parameter_node, logic, _bridge = make_facade()
    parameter_node.robotBaseTransform.active = True
    facade._planning_scene_synchronized = True
    current_source = {
        "openingRevision": 8,
        "gapLineNodeId": "gap-line-current",
    }
    roi = TaskSpaceRoi((2.0, 3.0, 4.0), (20.0, 24.0, 28.0))
    source_fingerprint = fingerprint(current_source)
    trajectory_fingerprint = "trajectory-current"
    entry = (0.0, 0.0, 0.0)
    target = (0.0, 0.0, 1.0)
    axis_status = "ProvisionalSelectedTrajectory"
    axis_fingerprint = fingerprint(
        {
            "status": axis_status,
            "entry_ras_mm": entry,
            "target_ras_mm": target,
            "trajectory_fingerprint": trajectory_fingerprint,
            "task_fingerprint": "",
        }
    )
    home_positions = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    home = SimpleNamespace(
        to_dict=lambda: dict(home_positions),
    )
    logic.taskHomeRecord = lambda _parameter: home
    logic.collisionSceneAuditRecord = lambda _parameter: SimpleNamespace(
        audit_fingerprint="scene-current"
    )
    logic.step6PlanningContextFreshnessIssues = lambda _parameter: ()
    logic.step6TrajectorySummary = lambda _parameter: {
        "isValid": True,
        "entryRas": entry,
        "targetRas": target,
    }
    active_trajectory = [trajectory_fingerprint]
    logic.step6TrajectoryRevision = lambda _parameter: active_trajectory[0]
    logic.confirmedTaskRecord = lambda _parameter: None
    facade.taskHomeRuntimeValidated = lambda _parameter=None: True
    active_source = {
        "centerWorldRasMm": roi.center_world_ras_mm,
        "dimensionsMm": roi.dimensions_mm,
        **current_source,
    }
    facade.defaultTaskSpaceRoi = lambda: RobotActionResult(
        True,
        "workspace_roi_ready",
        "ready",
        payload=active_source,
    )
    payload = {
        "runtime_validation_status": "MoveItStaticStateValidity+BoundedHomeConnectivity",
        "runtime_evidence_schema_version": "2.0",
        "runtime_valid_sample_count": 1,
        "home_connectivity_evaluated_sample_count": 1,
        "home_connected_sample_count": 1,
        "home_connectivity_status": "BoundedSubsetEvaluated",
        "accepted_sample_evidence": [
            {
                "static_state_validity": {"status": "Valid"},
                "home_connectivity": {"status": "HomeConnected"},
            }
        ],
        "task_home_fingerprint": fingerprint(home.to_dict()),
        "collision_audit_fingerprint": "scene-current",
        "workspace_validation_policy_fingerprint": (
            facade._workspace_validation_policy_fingerprint()
        ),
        "roi_source": current_source,
        "roi_source_fingerprint": source_fingerprint,
        "roi": {
            "center_world_ras_mm": roi.center_world_ras_mm,
            "dimensions_mm": roi.dimensions_mm,
        },
        "roi_fingerprint": fingerprint(
            {
                "center_world_ras_mm": roi.center_world_ras_mm,
                "dimensions_mm": roi.dimensions_mm,
                "source_fingerprint": source_fingerprint,
            }
        ),
        "trajectory_fingerprint": trajectory_fingerprint,
        "task_axis_status": axis_status,
        "task_axis_fingerprint": axis_fingerprint,
        "task_fingerprint": "",
    }
    parameter_node.step6AssistedLimitProposalJson = json.dumps(payload)
    facade._runtime_validated_workspace_key = fingerprint(payload)

    assert facade.workspaceRuntimeValidated(parameter_node)
    saved_proposal = parameter_node.step6AssistedLimitProposalJson
    saved_runtime_key = facade._runtime_validated_workspace_key
    assert facade.workspaceRoiMatchesSavedEvidence(roi, current_source, parameter_node)
    assert facade.workspaceRoiMatchesSavedEvidence(roi, current_source)
    assert not facade.workspaceRoiMatchesSavedEvidence(
        TaskSpaceRoi((3.0, 3.0, 4.0), roi.dimensions_mm),
        current_source,
        parameter_node,
    )
    assert not facade.workspaceRoiMatchesSavedEvidence(
        roi,
        {**current_source, "openingRevision": current_source["openingRevision"] + 1},
        parameter_node,
    )
    assert not facade.workspaceRoiMatchesSavedEvidence(
        roi, {"openingRevision": True, "gapLineNodeId": "gap-line-current"}, parameter_node
    )
    assert not facade.workspaceRoiMatchesSavedEvidence("malformed", current_source, parameter_node)
    saved_payload = json.loads(saved_proposal)
    parameter_node.step6AssistedLimitProposalJson = json.dumps(
        {**saved_payload, "roi_source_fingerprint": "stale"}
    )
    assert not facade.workspaceRoiMatchesSavedEvidence(roi, current_source)
    parameter_node.step6AssistedLimitProposalJson = json.dumps(
        {**saved_payload, "roi_fingerprint": "stale"}
    )
    assert not facade.workspaceRoiMatchesSavedEvidence(roi, current_source)
    parameter_node.step6AssistedLimitProposalJson = "malformed"
    assert not facade.workspaceRoiMatchesSavedEvidence(roi, current_source)
    parameter_node.step6AssistedLimitProposalJson = saved_proposal
    assert parameter_node.step6AssistedLimitProposalJson == saved_proposal
    assert facade._runtime_validated_workspace_key == saved_runtime_key

    active_source = {
        "centerWorldRasMm": (2.0000004, 3.0000004, 4.0000004),
        "dimensionsMm": (200.0, 200.0, 200.0),
        **current_source,
    }
    assert not facade.workspaceRoiMatchesSavedEvidence(
        TaskSpaceRoi(
            active_source["centerWorldRasMm"],
            active_source["dimensionsMm"],
        ),
        current_source,
        parameter_node,
    )
    assert facade.workspaceRuntimeValidated(parameter_node)

    active_source = {
        **active_source,
        "openingRevision": current_source["openingRevision"] + 1,
    }
    assert not facade.workspaceRuntimeValidated(parameter_node)

    active_source = {
        "centerWorldRasMm": roi.center_world_ras_mm,
        "dimensionsMm": roi.dimensions_mm,
        **current_source,
    }
    active_trajectory[0] = "trajectory-changed"
    assert not facade.workspaceRuntimeValidated(parameter_node)


def test_approach_planning_needs_stroke_reach_not_workspace_before_guard_or_planner():
    # Operator 2026-10-02: the 6.3 workspace and limit review are optional; the
    # prerequisite is that the accepted Base reaches the whole drilling stroke.
    facade, parameter_node, logic, bridge = make_facade()
    parameter_node.robotBaseTransform.active = True
    parameter_node.step6MotionDiagnosticJson = ""
    logic.confirmedTaskFreshnessIssues = lambda _node: ()
    logic.assistedTaskLimitsReviewed = lambda _node: False
    logic.step6CurrentBaseStrokeReachability = lambda _node: {
        "reachable": False, "first_failed_station": "pre_entry"}
    facade.taskHomeRuntimeValidated = lambda _node=None: True
    facade.workspaceRuntimeValidated = lambda _node=None: False
    calls = []
    facade._prepare_phase_guard = lambda *_args, **_kwargs: calls.append("guard")
    facade._goal1_pre_entry_ik_candidates = lambda *_args, **_kwargs: calls.append(
        "planner"
    )

    result = facade.planApproachPhase()

    assert not result.success and result.code == "approach_plan_failed"
    assert "cannot reach the whole PreEntry-to-Target" in result.message
    assert "pre_entry" in result.message and "Find Reachable Base" in result.message
    assert "workspace" not in result.message.lower()
    assert calls == []
    assert bridge.phase_calls == []


def test_reach_envelope_sentence_names_stations_inside_and_outside():
    from DENTORobotWorkflowFacade import DENTORobotWorkflowFacade as Facade

    sentence = Facade._reach_envelope_sentence({"stations_inside": {
        "PreEntry": {"inside": True, "nearest_sample_mm": 3.0},
        "Target": {"inside": False, "nearest_sample_mm": 14.2},
    }})
    assert "PreEntry inside" in sentence
    assert "Target outside (14.2 mm from the nearest sample)" in sentence
    assert Facade._reach_envelope_sentence({}) == ""


def _provisional_workspace_confirmation_fixture():
    facade, parameter_node, logic, bridge = make_facade()
    home_positions = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    home = SimpleNamespace(
        joint_names=ROS2_JOINT_SI_ORDER,
        joint_positions_si=tuple(home_positions.values()),
        to_dict=lambda: dict(home_positions),
    )
    entry, target = (1.0, 2.0, 3.0), (1.0, 2.0, 13.0)
    trajectory_revision = "trajectory-current"
    snapshot = SimpleNamespace(
        snapshot_fingerprint="task-confirmed-current",
        trajectory_revision=trajectory_revision,
        entry_ras_mm=entry,
        target_ras_mm=target,
    )
    current_snapshot = [None]
    workspace_checks = []
    workspace_state_at_confirmation = []

    parameter_node.robotBaseTransform.active = True
    facade._planning_scene_synchronized = True
    facade.taskHomeRuntimeValidated = lambda _node=None: True
    logic.taskHomeRecord = lambda _node: home
    logic.collisionSceneAuditRecord = lambda _node: SimpleNamespace(
        audit_fingerprint="scene-current"
    )
    logic.step6PlanningContextFreshnessIssues = lambda _node: ()
    logic.step6TrajectorySummary = lambda _node: {
        "isValid": True,
        "entryRas": entry,
        "targetRas": target,
    }
    logic.step6TrajectoryRevision = lambda _node: trajectory_revision
    logic.confirmedTaskFreshnessIssues = lambda _node: ()
    logic.confirmedTaskRecord = lambda _node: current_snapshot[0]
    facade.defaultTaskSpaceRoi = lambda: RobotActionResult(
        True,
        "workspace_roi_ready",
        "ready",
        payload={
            "centerWorldRasMm": (2.0, 3.0, 4.0),
            "dimensionsMm": (20.0, 24.0, 28.0),
            "openingRevision": 8,
            "gapLineNodeId": "gap-line-current",
        },
    )

    roi_source = {
        "openingRevision": 8,
        "gapLineNodeId": "gap-line-current",
    }
    roi_center, roi_dimensions = (2.0, 3.0, 4.0), (20.0, 24.0, 28.0)
    roi_source_fingerprint = fingerprint(roi_source)
    task_axis_fingerprint = fingerprint({
        "status": "ProvisionalSelectedTrajectory",
        "entry_ras_mm": entry,
        "target_ras_mm": target,
        "trajectory_fingerprint": trajectory_revision,
        "task_fingerprint": "",
    })
    payload = {
        "runtime_validation_status": "MoveItStaticStateValidity+BoundedHomeConnectivity",
        "runtime_evidence_schema_version": "2.0",
        "runtime_valid_sample_count": 1,
        "home_connectivity_evaluated_sample_count": 1,
        "home_connected_sample_count": 1,
        "home_connectivity_status": "BoundedSubsetEvaluated",
        "accepted_sample_evidence": [
            {
                "static_state_validity": {"status": "Valid"},
                "home_connectivity": {"status": "HomeConnected"},
                "joint_positions_si": home_positions,
            }
        ],
        "candidate_counts": {"roiCandidateCount": 1, "homeConnectedCount": 1},
        "reviewed": True,
        "task_home_fingerprint": fingerprint(home.to_dict()),
        "collision_audit_fingerprint": "scene-current",
        "workspace_validation_policy_fingerprint": (
            facade._workspace_validation_policy_fingerprint()
        ),
        "roi_source": roi_source,
        "roi_source_fingerprint": roi_source_fingerprint,
        "roi": {
            "center_world_ras_mm": roi_center,
            "dimensions_mm": roi_dimensions,
        },
        "roi_fingerprint": fingerprint({
            "center_world_ras_mm": roi_center,
            "dimensions_mm": roi_dimensions,
            "source_fingerprint": roi_source_fingerprint,
        }),
        "trajectory_fingerprint": trajectory_revision,
        "task_axis_status": "ProvisionalSelectedTrajectory",
        "task_axis_fingerprint": task_axis_fingerprint,
        "task_fingerprint": "",
    }
    parameter_node.step6AssistedLimitProposalJson = json.dumps(payload)
    facade._runtime_validated_workspace_key = fingerprint(payload)

    workspace_runtime_validated = facade.workspaceRuntimeValidated

    def track_workspace_validation(node=None):
        result = workspace_runtime_validated(node)
        workspace_checks.append(result)
        return result

    facade.workspaceRuntimeValidated = track_workspace_validation

    def confirm_step6_task(_node):
        workspace_state_at_confirmation.append(
            workspace_checks[-1] if workspace_checks else None
        )
        current_snapshot[0] = snapshot
        return snapshot

    logic.confirmStep6Task = confirm_step6_task
    planner_calls = []
    facade.planApproachPhase = lambda: planner_calls.append(True)
    return (
        facade,
        parameter_node,
        logic,
        bridge,
        snapshot,
        payload,
        workspace_checks,
        workspace_state_at_confirmation,
        planner_calls,
    )


def _workspace_evidence_without_task_identity(payload):
    identity_fields = {"task_axis_status", "task_axis_fingerprint", "task_fingerprint"}
    return json.dumps(
        {key: value for key, value in payload.items() if key not in identity_fields},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _assert_task_confirmation_has_no_motion_authority(facade, bridge, planner_calls):
    assert facade._motion_plan is None
    assert not facade.previewActive
    assert not facade._guarded_preview_active
    assert facade._preview_timer is None
    assert bridge.applied == []
    assert bridge.phase_calls == []
    assert planner_calls == []


def test_confirm_task_rebinds_current_workspace_to_confirmed_snapshot():
    (
        facade,
        parameter_node,
        _logic,
        bridge,
        snapshot,
        before,
        workspace_checks,
        workspace_state_at_confirmation,
        planner_calls,
    ) = _provisional_workspace_confirmation_fixture()
    assert facade.workspaceRuntimeValidated(parameter_node)
    workspace_checks.clear()
    before_evidence = _workspace_evidence_without_task_identity(before)

    result = facade.confirmTask()

    assert result.success and result.code == "task_confirmed"
    assert workspace_state_at_confirmation == [True]
    after = json.loads(parameter_node.step6AssistedLimitProposalJson)
    assert after["task_axis_status"] == "ConfirmedCurrent"
    assert after["task_axis_fingerprint"] == fingerprint({
        "status": "ConfirmedCurrent",
        "entry_ras_mm": snapshot.entry_ras_mm,
        "target_ras_mm": snapshot.target_ras_mm,
        "trajectory_fingerprint": snapshot.trajectory_revision,
        "task_fingerprint": snapshot.snapshot_fingerprint,
    })
    assert after["task_fingerprint"] == snapshot.snapshot_fingerprint
    assert _workspace_evidence_without_task_identity(after) == before_evidence
    assert facade.workspaceRuntimeValidated(parameter_node)
    _assert_task_confirmation_has_no_motion_authority(facade, bridge, planner_calls)


def test_confirm_task_does_not_rebind_workspace_that_was_not_current():
    (
        facade,
        parameter_node,
        _logic,
        bridge,
        _snapshot,
        before,
        workspace_checks,
        workspace_state_at_confirmation,
        planner_calls,
    ) = _provisional_workspace_confirmation_fixture()
    facade._runtime_validated_workspace_key = "stale-workspace-key"
    before_json = parameter_node.step6AssistedLimitProposalJson
    assert not facade.workspaceRuntimeValidated(parameter_node)
    workspace_checks.clear()

    result = facade.confirmTask()

    assert result.success and result.code == "task_confirmed"
    assert workspace_state_at_confirmation == [False]
    assert parameter_node.step6AssistedLimitProposalJson == before_json
    assert json.loads(before_json)["task_axis_status"] == "ProvisionalSelectedTrajectory"
    assert not facade.workspaceRuntimeValidated(parameter_node)
    _assert_task_confirmation_has_no_motion_authority(facade, bridge, planner_calls)


def test_confirm_task_does_not_rebind_malformed_workspace_identity_or_payload():
    (
        facade,
        parameter_node,
        _logic,
        bridge,
        _snapshot,
        payload,
        workspace_checks,
        workspace_state_at_confirmation,
        planner_calls,
    ) = _provisional_workspace_confirmation_fixture()
    payload["task_axis_fingerprint"] = "malformed-axis-fingerprint"
    parameter_node.step6AssistedLimitProposalJson = json.dumps(payload)
    facade._runtime_validated_workspace_key = fingerprint(payload)
    malformed_identity_json = parameter_node.step6AssistedLimitProposalJson
    assert not facade.workspaceRuntimeValidated(parameter_node)
    workspace_checks.clear()
    identity_result = facade.confirmTask()
    assert identity_result.success and identity_result.code == "task_confirmed"
    assert workspace_state_at_confirmation == [False]
    assert parameter_node.step6AssistedLimitProposalJson == malformed_identity_json
    assert not facade.workspaceRuntimeValidated(parameter_node)
    _assert_task_confirmation_has_no_motion_authority(facade, bridge, planner_calls)

    (
        facade,
        parameter_node,
        _logic,
        bridge,
        _snapshot,
        _payload,
        workspace_checks,
        workspace_state_at_confirmation,
        planner_calls,
    ) = _provisional_workspace_confirmation_fixture()
    malformed_payload = "{not-json"
    parameter_node.step6AssistedLimitProposalJson = malformed_payload
    facade._runtime_validated_workspace_key = "malformed-workspace-payload"
    assert not facade.workspaceRuntimeValidated(parameter_node)
    workspace_checks.clear()

    payload_result = facade.confirmTask()

    assert payload_result.success and payload_result.code == "task_confirmed"
    assert workspace_state_at_confirmation == [None]
    assert parameter_node.step6AssistedLimitProposalJson == malformed_payload
    assert not facade.workspaceRuntimeValidated(parameter_node)
    _assert_task_confirmation_has_no_motion_authority(facade, bridge, planner_calls)


def test_disconnect_forwards_progress_without_changing_bridge_result():
    facade, _parameter_node, _logic, bridge = make_facade()
    phases = []

    def disconnect(_models, *, progress):
        progress("Removing collision objects", 1, 1)
        return True, "disconnected"

    bridge.disconnect_dentobot_motion_control = disconnect
    result = facade.disconnect(progress=lambda *args: phases.append(args))
    assert result.success
    assert phases == [
        ("Stopping simulation preview",),
        ("Removing collision objects", 1, 1),
    ]


def test_preentry_ik_diagnostic_retains_failed_seed_without_planning(monkeypatch):
    import DENTORobotWorkflowFacade as facade_module
    from DENTOStep6State import (
        build_task_home,
        build_task_snapshot,
        fingerprint,
        parse_motion_diagnostic_session,
        planner_comparison_scene_fingerprint,
    )

    facade, parameter_node, logic, bridge = make_facade()
    parameter_node.robotBaseTransform.active = True
    parameter_node.step6ApproachStandoffMm = 2.0
    parameter_node.step6AssistedLimitProposalJson = ""
    parameter_node.step6MotionDiagnosticJson = ""
    home_positions = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    home = build_task_home(
        home_positions,
        base_fingerprint="base-fingerprint",
        robot_profile_fingerprint="profile-fingerprint",
        runtime_validation_status="Validated",
        collision_audit_fingerprint="audit-fingerprint",
        guard_policy_fingerprint="guard-policy",
    )
    snapshot = build_task_snapshot(
        target_segment_id="target-segment",
        trajectory_revision="trajectory-fingerprint",
        entry_ras_mm=(0.0, 0.0, 10.0),
        target_ras_mm=(0.0, 0.0, 0.0),
        base_fingerprint="base-fingerprint",
        home_fingerprint=fingerprint(home.to_dict()),
        limits_fingerprint="limits-fingerprint",
        robot_profile_fingerprint="profile-fingerprint",
    )
    audit = SimpleNamespace(
        status="Acknowledged",
        runtime_acknowledgement={
            "status": "Acknowledged",
            "expected_policy_fingerprint": "collision-policy",
        },
        audit_fingerprint="audit-fingerprint",
        base_fingerprint="base-fingerprint",
        jaw_preparation_fingerprint="jaw-fingerprint",
        world_to_base_fingerprint="world-base-fingerprint",
        object_records=(),
    )
    scene_fingerprint = planner_comparison_scene_fingerprint(audit)
    identity = {
        "branch_id": "prepared-branch",
        "task": snapshot.snapshot_fingerprint,
        "base": snapshot.base_fingerprint,
        "home": snapshot.home_fingerprint,
        "trajectory": snapshot.trajectory_revision,
        "robot_profile": snapshot.robot_profile_fingerprint,
        "collision_audit": scene_fingerprint,
    }
    logic.confirmedTaskFreshnessIssues = lambda _node: ()
    logic.confirmedTaskRecord = lambda _node: snapshot
    logic.taskHomeRecord = lambda _node: home
    logic.collisionSceneAuditRecord = lambda _node: audit
    logic.step6ApproachPoints = lambda _node, _snapshot: (
        (0.0, 0.0, 15.0),
        (0.0, 0.0, 10.0),
    )
    logic.robotDescriptionPaths = lambda: ("fixture.urdf", None)
    facade.plannerComparisonIdentity = lambda: dict(identity)
    facade.taskHomeRuntimeValidated = lambda _node=None: True
    facade._planning_scene_synchronized = True
    monkeypatch.setattr(
        facade_module,
        "default_task_joint_limits_from_urdf",
        lambda _path: logic.getTaskJointLimits(parameter_node),
    )
    bridge.world_ras_mm_to_base_m = lambda point, _base: [
        float(value) / 1000.0 for value in point
    ]
    bridge.tool_pose_matrices_world_mm = lambda *_args, **_kwargs: [
        FakePoseMatrix(((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0)))
    ]
    bridge.set_moveit_tcp_goal_matrix = lambda _pose: (True, "goal set", object())
    best = {
        ROS2_JOINT_SI_ORDER[0]: 0.1,
        ROS2_JOINT_SI_ORDER[1]: 0.025,
        ROS2_JOINT_SI_ORDER[2]: -0.2,
        ROS2_JOINT_SI_ORDER[3]: 0.03,
        ROS2_JOINT_SI_ORDER[4]: 0.3,
    }
    bridge.solve_moveit_tcp_position_axis_goal = lambda **_kwargs: (
        False,
        "iteration limit",
        {},
        {
            "termination_reason": "max_iterations",
            "iteration_count": 64,
            "collision_check_status": "unavailable",
            "task_jacobian_condition_ratio": 0.02,
            "position_residual_mm": 0.8,
            "drilling_axis_residual_deg": 1.4,
            "best_joint_positions_si": dict(best),
            "collision_pairs": (),
        },
    )
    effects = []

    def forbidden(name):
        def call(*_args, **_kwargs):
            effects.append(name)
            raise AssertionError(f"diagnostic called forbidden operation: {name}")
        return call

    for name in (
        "plan_moveit_joint_goal",
        "plan_moveit_joint_path",
        "plan_moveit_cartesian_path",
        "configure_task_phase_guard",
        "validate_task_phase_joint_sequence",
        "check_moveit_static_joint_state",
        "compute_tcp_pose_world_ras_mm",
    ):
        setattr(bridge, name, forbidden(name))
    facade._prepare_phase_guard = forbidden("phase_guard")
    facade.planApproachPhase = forbidden("approach_plan")
    facade.generateWorkspaceCloud = forbidden("workspace_generation")
    facade.applyTaskHome = forbidden("apply_task_home")

    result = facade.checkPreEntryIK()

    assert result.success
    assert result.code == "preentry_ik_diagnostic_complete"
    session = parse_motion_diagnostic_session(
        parameter_node.step6MotionDiagnosticJson
    )
    logic.motionDiagnosticFreshnessIssues = lambda _node: ()
    logic.motionDiagnosticRecord = lambda _node: parse_motion_diagnostic_session(
        parameter_node.step6MotionDiagnosticJson
    )
    record = session.candidate_records[0]
    assert session.state == "Current"
    assert session.full_task_outcome["diagnostic_kind"] == "preentry_ik"
    assert session.full_task_outcome["stage1_p1_status"] == "NotRun"
    assert session.full_task_outcome["stage2_status"] == "NotRun"
    assert session.full_task_outcome["stage3_status"] == "NotRun"
    assert session.full_task_outcome["target_conditioning"]["standoff_mm"] == 2.0
    assert record["success"] is False
    assert record["waypoint_count"] == 0
    assert record["solver_success"] is False
    assert record["seed_provenance"] == "task_home"
    assert record["seed_joint_positions_si"] == home_positions
    assert record["best_joint_positions_si"] == best
    assert record["collision_check_status"] == "unavailable"
    assert record["endpoint_collision_clear"] is False
    assert record["position_residual_mm"] == 0.8
    assert record["drilling_axis_residual_deg"] == 1.4
    assert record["task_jacobian_condition_ratio"] == 0.02
    assert record["mechanical_joint_limit_margins"]
    assert record["reviewed_task_joint_limit_margins"]
    assert not facade.selectDiagnosticCandidate(0).success
    assert not facade.applyDiagnosticCandidate(0).success
    assert effects == []
    assert bridge.applied == []
    assert bridge.phase_calls == []


def _failed_preentry_diagnostic_payload(
    *, best=None, state="Current", stale_reason=""
):
    from DENTOStep6State import build_motion_diagnostic_session, canonical_json

    best = best or {
        name: 0.1 * (index + 1)
        for index, name in enumerate(ROS2_JOINT_SI_ORDER)
    }
    record = {
        "candidate_index": 0,
        "axial_roll_deg": 0.0,
        "success": False,
        "completion_fraction": 0.0,
        "completed_distance_mm": 0.0,
        "requested_distance_mm": 0.0,
        "waypoint_count": 0,
        "failure_classification": "position_axis_ik_failed",
        "full_chain_failure_stage": "preentry_ik",
        "solver_success": False,
        "solver_message": "native solver rejected the exact pose",
        "termination_reason": "iteration_limit",
        "collision_check_status": "unavailable",
        "position_residual_mm": 0.8,
        "drilling_axis_residual_deg": 1.4,
        "best_joint_positions_si": dict(best),
        "static_state_validity_status": "not_attempted",
        "authoritative_fk_status": "not_attempted",
    }
    session = build_motion_diagnostic_session(
        state=state,
        stale_reason=stale_reason,
        task_fingerprint="task",
        base_fingerprint="base",
        trajectory_fingerprint="trajectory",
        robot_profile_fingerprint="profile",
        collision_audit_fingerprint="scene",
        planning_parameters_fingerprint="parameters",
        candidate_records=(record,),
        selected_candidate_index=0,
        failure_classification="preentry_ik_endpoint_diagnostic_only",
        full_task_outcome={
            "diagnostic_kind": "preentry_ik",
            "target_conditioning": {
                "world_frame": "RAS_mm",
                "pre_entry_world_ras_mm": (1.0, 2.0, 3.0),
                "entry_world_ras_mm": (1.0, 2.0, 4.0),
                "target_world_ras_mm": (1.0, 2.0, 14.0),
                "drilling_axis_world_unit": (0.0, 0.0, 1.0),
            },
            "plan_authority": False,
            "route_selection_allowed": False,
        },
    )
    return canonical_json(session.to_dict())


def test_best_failed_preentry_inspects_static_fk_and_retains_exact_evidence():
    from DENTOStep6State import parse_motion_diagnostic_session

    facade, parameter_node, logic, bridge = make_facade()
    parameter_node.step6MotionDiagnosticJson = _failed_preentry_diagnostic_payload()
    logic.motionDiagnosticFreshnessIssues = lambda _node: ()
    valid = {
        name: 0.1 * (index + 1)
        for index, name in enumerate(ROS2_JOINT_SI_ORDER)
    }
    static_calls = []
    fk_calls = []
    shown = []
    evidence_calls = []
    bridge.check_moveit_static_joint_state = lambda positions: (
        static_calls.append(dict(positions)) or (False, "static collision", True)
    )
    pose = (
        (1.0, 0.0, 0.0, 1.0),
        (0.0, 1.0, 0.0, 2.0),
        (0.0, 0.0, 1.0, 4.0),
        (0.0, 0.0, 0.0, 1.0),
    )

    def compute_fk(positions, *, base_transform):
        fk_calls.append((dict(positions), base_transform))
        return True, "finite FK", pose

    bridge.compute_tcp_pose_world_ras_mm = compute_fk
    bridge.show_goal_robot_joint_positions = lambda positions, **kwargs: (
        shown.append((dict(positions), kwargs)) or (True, "displayed")
    )
    bridge.show_motion_diagnostic_evidence = lambda **kwargs: (
        evidence_calls.append(kwargs) or (True, "evidence shown")
    )
    accepted_before = dict(bridge.accepted)
    display_before = tuple(
        getattr(parameter_node, field)
        for field in (
            "robotJoint1Deg",
            "robotJoint2Mm",
            "robotJoint3Deg",
            "robotJoint4Mm",
            "robotJoint5Deg",
        )
    )

    result = facade.showDiagnosticCandidate(0)

    assert result.success and result.code == "diagnostic_candidate_shown"
    assert "failed PreEntry IK state inspected" in result.message
    assert "no IK success, accepted-state, guard, or route authority" in result.message
    assert static_calls == [valid]
    assert fk_calls == [(valid, parameter_node.robotBaseTransform)]
    assert shown == [(valid, {"diagnostic": True})]
    assert len(evidence_calls) == 1
    inspection = result.details["diagnosticInspection"]
    assert inspection["static_state_validity"] == {
        "status": "invalid",
        "authoritative": True,
        "message": "static collision",
    }
    assert inspection["fk"]["status"] == "passed"
    assert inspection["fk"]["pose_world_ras_mm"] == pose
    assert inspection["fk"]["drilling_axis_world_ras_unit"] == (0.0, 0.0, 1.0)
    assert inspection["expected"]["tcp_world_ras_mm"] == (1.0, 2.0, 3.0)
    assert inspection["position_residual_mm"] == 1.0
    assert inspection["drilling_axis_residual_deg"] == 0.0
    assert inspection["native"]["message"] == "native solver rejected the exact pose"
    assert inspection["native"]["termination_reason"] == "iteration_limit"
    updated = parse_motion_diagnostic_session(
        parameter_node.step6MotionDiagnosticJson
    ).candidate_records[0]
    assert updated["solver_success"] is False
    assert updated["static_state_validity_status"] == "Invalid"
    assert updated["authoritative_fk_status"] == "OutsideTolerance"
    assert updated["authoritative_position_residual_mm"] == 1.0
    assert updated["authoritative_drilling_axis_residual_deg"] == 0.0
    assert tuple(
        tuple(row) for row in updated["authoritative_tcp_pose_world_ras_mm"]
    ) == pose
    assert tuple(
        updated["authoritative_drilling_axis_world_ras_unit"]
    ) == (0.0, 0.0, 1.0)
    assert bridge.accepted == accepted_before
    assert bridge.applied == [] and bridge.phase_calls == []
    assert tuple(
        getattr(parameter_node, field)
        for field in (
            "robotJoint1Deg",
            "robotJoint2Mm",
            "robotJoint3Deg",
            "robotJoint4Mm",
            "robotJoint5Deg",
        )
    ) == display_before
    assert facade.motionPlan is None
    assert facade._accepted_motion_history == []


def test_best_failed_preentry_inspection_keeps_fk_independent_when_unavailable():
    facade, parameter_node, logic, bridge = make_facade()
    parameter_node.step6MotionDiagnosticJson = _failed_preentry_diagnostic_payload()
    logic.motionDiagnosticFreshnessIssues = lambda _node: ()
    static_calls = []
    fk_calls = []
    bridge.check_moveit_static_joint_state = lambda positions: (
        static_calls.append(dict(positions)) or (False, "query timed out", False)
    )
    bridge.compute_tcp_pose_world_ras_mm = lambda *args, **kwargs: (
        fk_calls.append((args, kwargs)) or (False, "FK unavailable", None)
    )
    bridge.show_goal_robot_joint_positions = lambda *_args, **_kwargs: (
        True,
        "displayed",
    )
    bridge.show_motion_diagnostic_evidence = lambda **_kwargs: (True, "evidence shown")

    result = facade.showDiagnosticCandidate(0)

    assert result.success
    assert static_calls and fk_calls
    inspection = result.details["diagnosticInspection"]
    assert inspection["static_state_validity"]["status"] == "unavailable"
    assert inspection["fk"]["status"] == "unknown"
    assert inspection["fk"]["message"] == "FK unavailable"
    assert inspection["position_residual_mm"] is None
    assert inspection["drilling_axis_residual_deg"] is None
    assert result.details["solver_success"] is False


def test_stale_or_replaced_preentry_identity_rejects_before_fk_or_display():
    facade, parameter_node, logic, bridge = make_facade()
    stale_payload = _failed_preentry_diagnostic_payload(
        state="Stale", stale_reason="saved scene changed"
    )
    parameter_node.step6MotionDiagnosticJson = stale_payload
    logic.motionDiagnosticFreshnessIssues = lambda _node: ()
    bridge.check_moveit_static_joint_state = lambda *_args: pytest.fail(
        "stale diagnostics must not query MoveIt"
    )
    bridge.compute_tcp_pose_world_ras_mm = lambda *_args, **_kwargs: pytest.fail(
        "stale diagnostics must not query FK"
    )
    bridge.show_goal_robot_joint_positions = lambda *_args, **_kwargs: pytest.fail(
        "stale diagnostics must not display a goal"
    )
    bridge.show_motion_diagnostic_evidence = lambda **_kwargs: pytest.fail(
        "stale diagnostics must not display evidence"
    )
    result = facade.showDiagnosticCandidate(0)
    assert not result.success and result.code == "diagnostic_candidate_stale"
    assert "saved scene changed" in result.message

    parameter_node.step6MotionDiagnosticJson = _failed_preentry_diagnostic_payload()
    logic.motionDiagnosticFreshnessIssues = lambda _node: ("base identity changed",)
    freshness_rejected = facade.showDiagnosticCandidate(0)
    assert not freshness_rejected.success
    assert freshness_rejected.code == "diagnostic_candidate_stale"
    assert "base identity changed" in freshness_rejected.message

    logic.motionDiagnosticFreshnessIssues = lambda _node: ()
    replacement = FakeParameterNode()
    active = {"node": parameter_node}
    facade._parameter_node_provider = lambda: active["node"]
    logic.motionDiagnosticFreshnessIssues = lambda _node: ()
    fk_calls = []

    def switch_case(_positions):
        active["node"] = replacement
        return True, "valid", True

    bridge.check_moveit_static_joint_state = switch_case
    bridge.compute_tcp_pose_world_ras_mm = lambda *args, **kwargs: (
        fk_calls.append((args, kwargs)) or (True, "fk", None)
    )
    switched = facade.showDiagnosticCandidate(0)
    assert not switched.success and switched.code == "diagnostic_candidate_stale"
    assert fk_calls == []

    active["node"] = parameter_node
    replacement_payload = _failed_preentry_diagnostic_payload(
        best={name: 0.02 for name in ROS2_JOINT_SI_ORDER}
    )
    parameter_node.step6MotionDiagnosticJson = _failed_preentry_diagnostic_payload()

    def replace_session(_positions):
        parameter_node.step6MotionDiagnosticJson = replacement_payload
        return True, "valid", True

    bridge.check_moveit_static_joint_state = replace_session
    replaced = facade.showDiagnosticCandidate(0)
    assert not replaced.success and replaced.code == "diagnostic_candidate_stale"
    assert parameter_node.step6MotionDiagnosticJson == replacement_payload
    assert fk_calls == []

    parameter_node.step6MotionDiagnosticJson = _failed_preentry_diagnostic_payload()
    bridge.check_moveit_static_joint_state = lambda _positions: (True, "valid", True)
    pose = (
        (1.0, 0.0, 0.0, 1.0),
        (0.0, 1.0, 0.0, 2.0),
        (0.0, 0.0, 1.0, 3.0),
        (0.0, 0.0, 0.0, 1.0),
    )

    def replace_session_during_fk(*_args, **_kwargs):
        parameter_node.step6MotionDiagnosticJson = replacement_payload
        return True, "fk", pose

    bridge.compute_tcp_pose_world_ras_mm = replace_session_during_fk
    replaced_after_fk = facade.showDiagnosticCandidate(0)
    assert not replaced_after_fk.success
    assert replaced_after_fk.code == "diagnostic_candidate_stale"
    assert replaced_after_fk.details["diagnosticInspection"]["status"] == "discarded"
    assert parameter_node.step6MotionDiagnosticJson == replacement_payload
    assert fk_calls == []


def test_clear_diagnostic_display_stops_only_owned_timer_and_preserves_guarded_preview():
    class Timer:
        def __init__(self):
            self.stop_calls = 0

        def stop(self):
            self.stop_calls += 1

    facade, _parameter_node, _logic, bridge = make_facade()
    clears = []
    bridge.clear_motion_diagnostic_display = lambda **kwargs: (
        clears.append(kwargs) or (True, "cleared")
    )
    guarded_timer = Timer()
    facade._preview_timer = guarded_timer
    facade._diagnostic_preview_timer = None
    facade._guarded_preview_active = True
    facade._incomplete_preview_evidence = {"retained": True}
    facade._accepted_motion_history = [{"accepted": True}]
    retained_evidence = facade._incomplete_preview_evidence
    retained_history = list(facade._accepted_motion_history)

    guarded_result = facade.clearDiagnosticDisplay()

    assert guarded_result.success
    assert guarded_timer.stop_calls == 0
    assert facade._preview_timer is guarded_timer
    assert facade._incomplete_preview_evidence is retained_evidence
    assert facade._accepted_motion_history == retained_history
    assert clears[-1] == {"hide_goal": False}

    facade._guarded_preview_active = False
    diagnostic_timer = Timer()
    facade._preview_timer = diagnostic_timer
    facade._diagnostic_preview_timer = diagnostic_timer
    diagnostic_result = facade.clearDiagnosticDisplay()
    assert diagnostic_result.success
    assert diagnostic_timer.stop_calls == 1
    assert facade._preview_timer is None
    assert facade._diagnostic_preview_timer is None


def test_goal1_preentry_failure_retains_geometry_and_session_fingerprint():
    from DENTOStep6State import parse_motion_diagnostic_session

    facade, parameter_node, logic, bridge = make_facade()
    parameter_node.robotBaseTransform.active = True
    parameter_node.step6ApproachStandoffMm = 4.5
    parameter_node.step6MotionDiagnosticJson = ""
    home_positions = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    home = SimpleNamespace(
        joint_names=tuple(ROS2_JOINT_SI_ORDER),
        joint_positions_si=tuple(
            home_positions[name] for name in ROS2_JOINT_SI_ORDER
        ),
    )
    snapshot = SimpleNamespace(
        snapshot_fingerprint="task-fingerprint",
        entry_ras_mm=(10.0, 20.0, 30.0),
        target_ras_mm=(10.0, 20.0, 20.0),
    )
    audit = SimpleNamespace(audit_fingerprint="audit-fingerprint")
    logic.confirmedTaskFreshnessIssues = lambda _node: ()
    logic.confirmedTaskRecord = lambda _node: snapshot
    logic.taskHomeRecord = lambda _node: home
    logic.collisionSceneAuditRecord = lambda _node: audit
    logic.robotBaseFingerprint = lambda _node: "base-fingerprint"
    logic.step6TrajectoryRevision = lambda _node: "trajectory-fingerprint"
    logic.robotProfileFingerprint = lambda: "profile-fingerprint"
    logic.step6ApproachPoints = lambda _node, _snapshot: (
        (10.0, 20.0, 33.5),
        (10.0, 20.0, 30.0),
    )
    facade.taskHomeRuntimeValidated = lambda _node=None: True
    facade.workspaceRuntimeValidated = lambda _node=None: True
    parameter_node.step6AssistedLimitProposalJson = json.dumps({"reviewed": True})
    facade._guide_fit_evidence = lambda _node: {}
    facade._tool_insertion_evidence = lambda *_args: {"planningAllowed": True}
    facade._prepare_phase_guard = lambda *_args, **_kwargs: (True, "prepared")

    seed_records = [
        {
            "candidate_index": index,
            "seed_provenance": "task_home" if index == 0 else "workspace_seed",
            "seed_joint_positions_si": dict(home_positions),
            "failure_classification": "position_axis_ik_failed",
            "solver_message": f"seed {index} failed",
            "position_residual_mm": position,
            "drilling_axis_residual_deg": axis,
        }
        for index, (position, axis) in enumerate(((0.6, 1.0), (0.4, 0.8)))
    ]

    def no_ik(_node, _pre_entry, _entry, _target, _home, *, seed_collector=None, **_kwargs):
        for record in seed_records:
            seed_collector(dict(record))
        return [], [
            "full seed 0 failure",
            "additional failure from seed 0",
            "full seed 1 failure",
        ]

    facade._goal1_pre_entry_ik_candidates = no_ik

    result = facade.planApproachPhase()

    assert not result.success
    assert result.code == "approach_plan_failed"
    assert "Best observed position/axis residual: 0.400 mm / 0.800°" in result.message
    assert "tolerances: 0.250 mm / 0.500°" in result.message
    assert "Full per-seed evidence is in Motion Diagnostics." in result.message
    assert "full seed 0 failure" not in result.message
    assert result.details["motionDiagnosticSessionFingerprint"]
    assert result.payload is None
    assert facade._motion_plan is None
    assert bridge.phase_calls == []

    session = parse_motion_diagnostic_session(parameter_node.step6MotionDiagnosticJson)
    assert session.session_fingerprint == result.details[
        "motionDiagnosticSessionFingerprint"
    ]
    outcome = session.full_task_outcome
    assert outcome["target_conditioning"] == {
        "world_frame": "RAS_mm",
        "pre_entry_world_ras_mm": [10.0, 20.0, 33.5],
        "entry_world_ras_mm": [10.0, 20.0, 30.0],
        "target_world_ras_mm": [10.0, 20.0, 20.0],
        "standoff_mm": 4.5,
    }
    assert outcome["blocked_stage"] == "preentry_ik"
    assert session.candidate_records[0]["message"] == "seed 0 failed"
    assert session.candidate_records[1]["message"] == "seed 1 failed"
    assert all(
        "additional failure from seed 0" not in record["message"]
        for record in session.candidate_records
    )
    assert all(
        record["success"] is False
        and record["waypoint_count"] == 0
        and record["full_chain_candidate_status"] == "Blocked"
        for record in session.candidate_records
    )


def _ready_stage_diagnostic_fixture(facade, parameter_node, monkeypatch):
    parameter_node.robotMotionPlanSampleCount = 5
    names = tuple(workflow_facade_module.JOINT_NAMES)
    home = {name: 0.0 for name in names}
    pre_entry = dict(home, **{names[0]: 0.1})
    entry_state = dict(home, **{names[0]: 0.2})
    target_state = dict(home, **{names[0]: 0.3})
    identity = {
        "branch_id": "branch",
        "task": "task",
        "base": "base",
        "home": "home",
        "trajectory": "trajectory",
        "robot_profile": "profile",
        "collision_audit": "scene",
    }
    audit = SimpleNamespace(audit_fingerprint="audit")
    parameter_node.step6MotionDiagnosticJson = "current-preentry-report"
    candidate_records = [{"candidate_index": 0, "success": False}]
    session = SimpleNamespace(
        schema_version="2.2",
        state="Current",
        task_fingerprint=identity["task"],
        base_fingerprint=identity["base"],
        trajectory_fingerprint=identity["trajectory"],
        robot_profile_fingerprint=identity["robot_profile"],
        collision_audit_fingerprint=audit.audit_fingerprint,
        full_task_outcome={"diagnostic_kind": "preentry_ik"},
        to_dict=lambda: {"candidate_records": candidate_records},
    )
    monkeypatch.setattr(
        workflow_facade_module,
        "parse_motion_diagnostic_session",
        lambda _payload: session,
    )
    facade.plannerComparisonIdentity = lambda: dict(identity)
    facade._step6_preentry_candidate_cache = {
        "identity": dict(identity),
        "candidate_records_fingerprint": fingerprint(candidate_records),
        "candidates": (
            {
                "positions": dict(pre_entry),
                "roll_deg": 0.0,
                "orientation": {
                    "rotationRas": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
                    "fingerprint": "orientation",
                },
            },
        ),
    }
    context = {
        "parameter_node": parameter_node,
        "snapshot": SimpleNamespace(snapshot_fingerprint=identity["task"]),
        "home": SimpleNamespace(),
        "collision_audit": audit,
        "identity": dict(identity),
        "home_positions": home,
        "pre_entry": (1.0, 2.0, 3.0),
        "entry": (4.0, 5.0, 6.0),
        "target": (7.0, 8.0, 9.0),
        "drill_axis": (0.0, 0.0, 1.0),
    }
    facade._step6_stage_context = lambda: context
    facade._replace_step6_stage_outcomes = lambda *_args, **_kwargs: True
    facade._strict_guard_policy_fingerprint = lambda: "guard-policy"
    facade._evaluate_step6_tcp_endpoint = lambda *_args, **_kwargs: {
        "status": "passed",
        "position_residual_mm": 0.0,
        "drilling_axis_residual_deg": 0.0,
    }
    facade._step6_stage_guard_evidence = lambda _context, _paths: {
        "status": "passed",
        "reason": "guard passed",
        "first_invalid_requested": {"status": "not_reached", "state": None},
        "first_invalid_evaluated": {"status": "unknown", "state": None},
        "last_valid": {"status": "passed", "requested_state": None},
        "clearance": {"status": "measured", "minimum_world_distance_m": 0.01},
    }
    return identity, context, home, pre_entry, entry_state, target_state


def test_step6_p2_and_p3_block_without_passed_predecessor_or_planner_call(monkeypatch):
    facade, parameter_node, _logic, bridge = make_facade()
    _ready_stage_diagnostic_fixture(facade, parameter_node, monkeypatch)
    planner_calls = []
    bridge.plan_moveit_joint_goal = lambda **_kwargs: planner_calls.append("P1")
    bridge.plan_moveit_cartesian_path = lambda **_kwargs: planner_calls.append("cartesian")

    p2 = facade.checkPlanningStage("P2")
    p3 = facade.checkPlanningStage("P3")

    assert not p2.success and p2.code == "planning_stage_blocked"
    assert "fresh, passed P1" in p2.message
    assert not p3.success and p3.code == "planning_stage_blocked"
    assert "fresh, passed P2" in p3.message
    assert planner_calls == []
    assert bridge.applied == []
    assert bridge.phase_calls == []
    assert facade._motion_plan is None
    assert facade._preflight_drilling_plan is None


def test_step6_p1_p2_p3_use_exact_predecessor_endpoint_without_motion_authority(monkeypatch):
    facade, parameter_node, _logic, bridge = make_facade()
    _identity, _context, home, pre_entry, entry_state, target_state = (
        _ready_stage_diagnostic_fixture(facade, parameter_node, monkeypatch)
    )
    calls = []

    def planned(path):
        return SimpleNamespace(
            success=True,
            message="planned",
            native_planner_message="planned",
            effective_planner_id="RRTConnect",
            waypoint_joint_vectors_si=tuple(dict(point) for point in path),
            waypoint_times_sec=(0.0, 1.0),
            fraction=1.0,
            coordinate_frame="world",
            start_position_error_mm=0.0,
            start_orientation_error_deg=0.0,
            last_valid_waypoint_index=len(path) - 1,
            last_valid_joint_positions_si=dict(path[-1]),
            first_invalid_requested_index=-1,
            first_invalid_ras_mm=None,
            first_invalid_joint_positions_si=None,
            first_invalid_collision_pairs=(),
            failure_classification="",
        )

    def plan_joint_goal(**kwargs):
        calls.append(("P1", kwargs))
        return planned((home, pre_entry))

    def plan_cartesian(**kwargs):
        calls.append(("P2" if len(calls) == 1 else "P3", kwargs))
        endpoint = entry_state if len(calls) == 2 else target_state
        return planned((kwargs["start_joint_positions_si"], endpoint))

    bridge.plan_moveit_joint_goal = plan_joint_goal
    bridge.plan_moveit_cartesian_path = plan_cartesian
    # Corridor composition has its own test; keep this one on the direct P1 call.
    facade._plan_home_to_preentry_with_corridor = (
        lambda _node, home_state, goal_state, **_kwargs: plan_joint_goal(
            start_joint_positions_si=home_state, goal_joint_positions_si=goal_state))

    results = [facade.checkPlanningStage(phase) for phase in ("P1", "P2", "P3")]

    assert all(result.success for result in results)
    assert [call[0] for call in calls] == ["P1", "P2", "P3"]
    assert calls[0][1]["start_joint_positions_si"] == home
    assert calls[0][1]["goal_joint_positions_si"] == pre_entry
    assert calls[1][1]["start_joint_positions_si"] == pre_entry
    assert calls[1][1]["entry_ras_mm"] == (1.0, 2.0, 3.0)
    assert calls[1][1]["target_ras_mm"] == (4.0, 5.0, 6.0)
    assert calls[2][1]["start_joint_positions_si"] == entry_state
    assert calls[2][1]["entry_ras_mm"] == (4.0, 5.0, 6.0)
    assert calls[2][1]["target_ras_mm"] == (7.0, 8.0, 9.0)
    assert all(result.payload["route_authority"] == "none" for result in results)
    assert [stage["route_authority"] for stage in facade._step6_stage_diagnostic_chain["stages"].values()] == [
        "none",
        "none",
        "none",
    ]
    assert facade._motion_plan is None
    assert facade._preflight_drilling_plan is None
    assert bridge.applied == []
    assert bridge.phase_calls == []


def test_step6_stage_guard_does_not_attribute_mismatched_native_status():
    names = tuple(workflow_facade_module.JOINT_NAMES)
    requested = {name: float(index) for index, name in enumerate(names)}
    mismatched_statuses = (
        SimpleNamespace(
            task_fingerprint="task",
            guard_session_id="stale-session",
            phase="approach",
            sequence=1,
            request_id="",
            validation_kind="transition",
            collision_scene_policy_fingerprint="current-policy",
            accepted=False,
            validate_only=True,
            checked_samples=1,
            requested_positions=tuple(requested[name] for name in names),
            evaluated_positions=tuple(requested[name] for name in names),
        ),
        SimpleNamespace(
            task_fingerprint="task",
            guard_session_id="current-session",
            phase="approach",
            sequence=1,
            request_id="",
            validation_kind="transition",
            collision_scene_policy_fingerprint="current-policy",
            accepted=False,
            validate_only=True,
            checked_samples=1,
            requested_positions=tuple(
                requested[name] + (0.1 if index == 0 else 0.0)
                for index, name in enumerate(names)
            ),
            evaluated_positions=tuple(requested[name] for name in names),
        ),
    )

    for mismatched in mismatched_statuses:
        facade, _parameter_node, _logic, bridge = make_facade()
        facade._configure_phase_guard = lambda *_args, **_kwargs: (True, "configured")
        facade._strict_guard_policy_fingerprint = lambda: "current-policy"
        bridge.current_task_guard_identity = lambda: {
            "task_fingerprint": "task",
            "guard_session_id": "current-session",
            "collision_scene_policy_fingerprint": "current-policy",
        }
        submitted = {}
        response = []

        def validate(_waypoints, _phases, **kwargs):
            submitted.update(kwargs)
            response.append(
                SimpleNamespace(**{
                    **vars(mismatched),
                    "request_id": f"{kwargs['request_id_prefix']}:0",
                })
            )
            return False, "rejected", 0

        bridge.validate_task_phase_waypoints = validate
        bridge.last_task_joint_status = lambda: response[-1]
        context = {
            "parameter_node": object(),
            "snapshot": SimpleNamespace(snapshot_fingerprint="task"),
            "home_positions": {name: 0.0 for name in names},
        }

        evidence = facade._step6_stage_guard_evidence(context, {"P1": (requested,)})

        assert submitted["request_id_prefix"]
        assert evidence["status"] == "unknown"
        assert evidence["first_invalid_evaluated"]["status"] == "unknown"
        assert evidence["first_invalid_evaluated"]["state"] is None
        assert evidence["clearance"]["status"] == "unknown"


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


def test_legacy_joint_request_fails_closed_without_mutating_pose():
    facade, parameter_node, logic, bridge = make_facade()

    def forbidden_context_access():
        raise AssertionError("legacy joint request accessed workflow context")

    facade._require_context = forbidden_context_access
    result = facade.requestJointValue(1, 12.5)
    assert not result.success
    assert result.code == "guarded_manual_jog_required"
    assert parameter_node.robotJoint1Deg == 0.0
    assert logic.updated == []
    assert bridge.applied == []
    assert bridge.phase_calls == []


def test_legacy_joint_request_preserves_unknown_manual_jog_latch():
    facade, parameter_node, logic, bridge = make_facade()
    facade._manual_jog_reconciliation_required = True
    facade._manual_jog_uncertainty = {"requestId": "unknown-request"}

    def forbidden_context_access():
        raise AssertionError("unknown-jog latch accessed workflow context")

    facade._require_context = forbidden_context_access
    result = facade.requestJointValue(1, 20.0)
    assert not result.success
    assert result.code == "manual_jog_reconciliation_required"
    assert result.details["manualJogReconciliationRequired"] is True
    assert result.details["manualJogStatus"] == "unknown"
    assert result.details["manualJogUncertainty"] == {"requestId": "unknown-request"}
    assert parameter_node.robotJoint1Deg == 0.0
    assert logic.updated == []
    assert bridge.applied == []
    assert bridge.phase_calls == []


def test_unrecognized_joint_request_is_rejected_without_runtime_access():
    facade, _parameter_node, logic, bridge = make_facade()

    def forbidden_context_access():
        raise AssertionError("unrecognized joint request accessed workflow context")

    facade._require_context = forbidden_context_access
    result = facade.requestJointValue("unexpected_joint", 20.0)
    assert not result.success
    assert logic.updated == []
    assert bridge.applied == []
    assert bridge.phase_calls == []


def test_legacy_preview_rejects_generic_plan_before_runtime(monkeypatch):
    facade, parameter_node, logic, bridge = make_facade()
    facade._motion_plan = SimpleNamespace(
        success=True,
        waypoint_joint_vectors_si=({name: 0.1 for name in ROS2_JOINT_SI_ORDER},),
    )

    def forbidden_context_access():
        raise AssertionError("legacy preview accessed workflow context")

    class ForbiddenTimer:
        def __init__(self):
            raise AssertionError("legacy preview created a Qt timer")

    monkeypatch.setitem(sys.modules, "qt", SimpleNamespace(QTimer=ForbiddenTimer))
    facade._require_context = forbidden_context_access
    finished = []
    result = facade.previewPlan(on_finished=finished.append)

    assert not result.success
    assert result.code == "guarded_phase_preview_required"
    assert finished == []
    assert facade._preview_timer is None
    assert parameter_node.robotJoint1Deg == 0.0
    assert logic.updated == []
    assert bridge.applied == []
    assert bridge.phase_calls == []


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
    assert result.details["manualSimulationRecordStatus"] == "unavailable"
    assert "pre-commit" in result.details[
        "manualSimulationRecordUnavailableReason"
    ]
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


def _complete_approach_preview_fixture():
    facade, _parameter_node, logic, bridge = make_facade()
    task_fingerprint = "current-task"
    session_id = "guard-session"
    policy_fingerprint = "guard-policy"
    orientation_fingerprint = "tool-orientation"
    positions = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    plan = workflow_facade_module.PhasePlan(
        success=True,
        message="complete route",
        task_fingerprint=task_fingerprint,
        requested_phase="approach",
        waypoint_joint_vectors_si=(dict(positions), dict(positions)),
        waypoint_phases=("approach", "terminal_contact"),
        strict_waypoint_count=1,
        contact_waypoint_count=1,
        source_waypoint_count=2,
        tool_orientation_fingerprint=orientation_fingerprint,
    )
    preflight = SimpleNamespace(
        success=True,
        waypoint_joint_vectors_si=(dict(positions), dict(positions)),
        waypoint_times_sec=(0.0, 1.0),
        fraction=1.0,
        coordinate_frame="base_link",
        start_position_error_mm=0.0,
        start_orientation_error_deg=0.0,
        axial_roll_deg=0.0,
    )
    last_sequence = (
        int(bridge.ROS2_TASK_GUARD_INITIAL_SEQUENCE)
        + plan.source_waypoint_count
        + len(preflight.waypoint_joint_vectors_si)
        - 1
    )
    snapshot = SimpleNamespace(snapshot_fingerprint=task_fingerprint)
    home = SimpleNamespace(
        joint_names=tuple(ROS2_JOINT_SI_ORDER),
        joint_positions_si=tuple(positions[name] for name in ROS2_JOINT_SI_ORDER),
    )
    logic.confirmedTaskFreshnessIssues = lambda _node: ()
    logic.confirmedTaskRecord = lambda _node: snapshot
    logic.taskHomeRecord = lambda _node: home
    bridge.monitored_joint_positions_si = lambda: dict(positions)
    bridge.current_task_guard_identity = lambda: {
        "task_fingerprint": task_fingerprint,
        "guard_session_id": session_id,
        "collision_scene_policy_fingerprint": policy_fingerprint,
    }
    bridge.last_task_joint_status = lambda: SimpleNamespace(
        task_fingerprint=task_fingerprint,
        guard_session_id=session_id,
        phase="drilling",
        sequence=last_sequence,
        accepted=True,
        validate_only=True,
    )
    facade._strict_guard_policy_fingerprint = lambda: policy_fingerprint
    facade._motion_plan = plan
    facade._phase_guard_task_fingerprint = task_fingerprint
    facade._phase_guard_session_id = session_id
    facade._phase_sequence = bridge.ROS2_TASK_GUARD_INITIAL_SEQUENCE
    facade._preflight_drilling_plan = preflight
    facade._preflight_task_fingerprint = task_fingerprint
    facade._preflight_orientation_commitment = {
        "policy": workflow_facade_module.DRILL_TOOL_FRAME_POLICY,
        "fingerprint": orientation_fingerprint,
        "toolAxisRas": (0.0, 0.0, 1.0),
    }
    facade._preflight_complete_approach_evidence = {
        "plan": plan,
        "taskFingerprint": task_fingerprint,
        "guardSessionId": session_id,
        "lastSequence": last_sequence,
        "policyFingerprint": policy_fingerprint,
    }
    return facade, logic, bridge, positions, plan


def test_blocked_stage2_and_stage3_approach_plans_cannot_preview():
    for failed_preflight in (None, SimpleNamespace(
        success=False, waypoint_joint_vectors_si=({"partial": True},)
    )):
        facade, _logic, bridge, _positions, _plan = (
            _complete_approach_preview_fixture()
        )
        facade._preflight_drilling_plan = failed_preflight
        facade._preflight_task_fingerprint = "current-task"
        facade._preflight_complete_approach_evidence = None

        result = facade.previewPhase("approach")

        assert not result.success
        assert result.code == "approach_full_chain_required"
        assert not facade.drillingPreflightReady
        assert bridge.phase_calls == []


def test_approach_preview_rejects_stale_preflight_identity():
    facade, _logic, bridge, _positions, _plan = _complete_approach_preview_fixture()
    facade._preflight_task_fingerprint = "old-task"

    result = facade.previewPhase("approach")

    assert not result.success
    assert result.code == "approach_full_chain_required"
    assert not facade.drillingPreflightReady
    assert bridge.phase_calls == []


def test_complete_approach_reaches_existing_home_guard_with_five_joints(monkeypatch):
    facade, _logic, bridge, positions, _plan = _complete_approach_preview_fixture()
    monitored = dict(positions)
    monitored[ROS2_JOINT_SI_ORDER[0]] = 0.1
    bridge.monitored_joint_positions_si = lambda: monitored

    rejected_home = facade.previewPhase("approach")

    assert not rejected_home.success
    assert rejected_home.code == "guarded_motion_history_home_mismatch"
    assert facade.drillingPreflightReady
    assert bridge.phase_calls == []

    monitored = dict(positions)
    monitored["unexpected_joint"] = 0.5
    bridge.monitored_joint_positions_si = lambda: monitored
    original_import = __import__

    def import_without_qt(name, *args, **kwargs):
        if name == "qt":
            raise ImportError("stop after preview authority checks")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", import_without_qt)
    extra_joint = facade.previewPhase("approach")

    assert not extra_joint.success
    assert extra_joint.code == "guarded_motion_history_home_mismatch"
    assert bridge.phase_calls == []


def test_drilling_preflight_ready_survives_drilling_plan_replacement():
    facade, _logic, _bridge, _positions, _approach_plan = (
        _complete_approach_preview_fixture()
    )
    parameter_node = facade._require_context()
    parameter_node.robotBaseTransform.active = True
    facade._completed_phase = "approach"
    facade._guide_fit_evidence = lambda _node: {"message": "guide current"}

    result = facade.planDrillingPhase()

    assert result.success and result.code == "drilling_plan_ready"
    assert facade._motion_plan is result.payload
    assert result.payload.requested_phase == "drilling"
    assert facade.drillingPreflightReady
    assert facade._phase_guard_task_fingerprint == "current-task"
    assert facade._phase_guard_session_id == "guard-session"
    assert (
        facade._preflight_complete_approach_evidence["drillingPlan"]
        is result.payload
    )


def test_drilling_preview_rejects_unbound_success_looking_plan():
    facade, _logic, bridge, positions, _approach_plan = (
        _complete_approach_preview_fixture()
    )
    facade._completed_phase = "approach"
    facade._motion_history_task_fingerprint = "current-task"
    facade._accepted_motion_history = [
        {"positions": dict(positions), "phase": "home"}
    ]
    facade._motion_plan = workflow_facade_module.PhasePlan(
        success=True,
        message="unbound drilling route",
        task_fingerprint="current-task",
        requested_phase="drilling",
        waypoint_joint_vectors_si=(dict(positions),),
        waypoint_phases=("drilling",),
        tool_orientation_fingerprint="tool-orientation",
    )

    result = facade.previewPhase("drilling")

    assert not result.success
    assert result.code == "drilling_preflight_required"
    assert bridge.phase_calls == []


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


def test_stage1_uses_every_bounded_home_connected_seed():
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
        def solve_moveit_tcp_position_axis_goal(
            *, seed_joint_positions_si=None, avoid_collisions=True
        ):
            assert isinstance(avoid_collisions, bool)
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

    bridge.audited.clear()
    diagnostic_candidates, diagnostic_failures = facade._goal1_pre_entry_ik_candidates(
        parameter_node,
        (0.0, 0.0, -2.0),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 10.0),
        home,
        include_workspace_seeds=False,
        avoid_collisions=False,
        require_generic_static=False,
        fixed_rotation_ras=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    )
    assert diagnostic_failures == []
    assert len(diagnostic_candidates) == 1
    assert diagnostic_candidates[0]["routeType"] == "direct"
    assert bridge.audited == []


def test_stage1_shared_endpoint_evaluator_stops_on_static_invalid():
    facade, parameter_node, _logic, bridge = make_facade()
    home = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    bridge.tool_pose_matrices_world_mm = lambda *_args, **_kwargs: [
        FakePoseMatrix(
            ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        )
    ]
    bridge.set_moveit_tcp_goal_matrix = lambda _pose: (True, "goal", object())
    bridge.solve_moveit_tcp_position_axis_goal = lambda **_kwargs: (
        True,
        "ik",
        dict(home),
        {},
    )
    bridge.check_moveit_static_joint_state = lambda _positions: (
        False,
        "static collision",
        True,
    )
    fk_calls = []

    def compute_fk(*_args, **_kwargs):
        fk_calls.append(True)
        return True, "fk", (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )

    bridge.compute_tcp_pose_world_ras_mm = compute_fk
    evaluations = []
    evaluate = facade._evaluate_step6_tcp_endpoint

    def capture_evaluation(*args, **kwargs):
        result = evaluate(*args, **kwargs)
        evaluations.append(result)
        return result

    facade._evaluate_step6_tcp_endpoint = capture_evaluation
    candidates, failures = facade._goal1_pre_entry_ik_candidates(
        parameter_node,
        (0.0, 0.0, -2.0),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 10.0),
        home,
        include_workspace_seeds=False,
    )

    assert candidates == []
    assert failures == ["canonical TCP IK state is invalid: static collision"]
    assert fk_calls == []
    assert len(evaluations) == 1
    assert evaluations[0]["step6_tcp_endpoint_evaluation_schema_version"] == "1.0"
    assert evaluations[0]["status"] == "failed"
    assert evaluations[0]["static_state_validity"] == {
        "status": "failed",
        "authoritative": True,
        "message": "static collision",
    }
    assert evaluations[0]["collision"] == {"status": "unknown", "pairs": None}
    assert evaluations[0]["fk"]["status"] == "not_reached"


def test_shared_endpoint_evaluator_records_clear_scene_and_pose_residuals():
    facade, parameter_node, _logic, bridge = make_facade()
    bridge.check_moveit_static_joint_state = lambda _positions: (
        True,
        "MoveIt accepted the explicit state.",
        True,
    )
    bridge.compute_tcp_pose_world_ras_mm = lambda *_args, **_kwargs: (
        True,
        "MoveIt FK returned a finite pose.",
        (
            (1.0, 0.0, 0.0, 1.0),
            (0.0, 1.0, 0.0, 2.0),
            (0.0, 0.0, 1.0, 3.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
    )

    result = facade._evaluate_step6_tcp_endpoint(
        parameter_node,
        {name: 0.0 for name in ROS2_JOINT_SI_ORDER},
        expected_tcp_world_ras_mm=(1.0, 2.0, 3.0),
        expected_drill_axis_world_ras_unit=(0.0, 0.0, 5.0),
    )

    assert result["status"] == "passed"
    assert result["static_state_validity"]["status"] == "passed"
    assert result["collision"] == {"status": "clear", "pairs": []}
    assert result["fk"]["status"] == "passed"
    assert result["position_residual_mm"] == 0.0
    assert result["drilling_axis_residual_deg"] == 0.0


def _manual_endpoint_probe(monkeypatch, *, identity_changes=False):
    facade, parameter_node, logic, bridge = make_facade()
    parameter_node.step6TaskHomeJson = ""
    parameter_node.robotBaseTransform.active = True
    parameter_node.step6PlanningContextImported = True
    parameter_node.step6TrajectoryRegistryJson = json.dumps(
        {"selected_branch_id": "branch-a", "prepared_branches": {"branch-a": {}}}
    )
    parameter_node.step6ToolFrame = "dentobot_drill_tcp"
    parameter_node.targetToothSegmentId = "tooth-segment"
    parameter_node.step6MotionDiagnosticJson = "preserve-this-record"
    facade._planning_scene_synchronized = True
    facade._planning_scene_object_count = 1

    snapshot = SimpleNamespace(
        snapshot_fingerprint="task-a",
        entry_ras_mm=(0.0, 0.0, 0.0),
        target_ras_mm=(0.0, 0.0, 10.0),
        base_fingerprint="base-a",
        home_fingerprint="home-a",
        trajectory_revision="trajectory-a",
        robot_profile_fingerprint="robot-a",
    )
    audit = SimpleNamespace(
        status="Acknowledged",
        runtime_acknowledgement={
            "status": "Acknowledged",
            "acknowledged_object_ids": ["jaw"],
        },
    )
    home = SimpleNamespace(to_dict=lambda: {"home": "home-a"})
    logic.step6AnatomyReviewFreshnessIssues = lambda _node: ()
    logic.step6CaseJawOpeningFreshnessIssues = lambda _node: ()
    logic.step6BasePlacementFreshnessIssues = lambda _node: ()
    logic.taskHomeFreshnessIssues = lambda _node: ()
    logic.confirmedTaskRecord = lambda _node: snapshot
    logic.collisionSceneAuditRecord = lambda _node: audit
    logic.taskHomeRecord = lambda _node: home
    logic.step6TrajectoryRevision = lambda _node: "trajectory-a"
    logic.robotBaseFingerprint = lambda _node: "base-a"
    logic.step6TaskLimitsFingerprint = lambda _node: "limits-a"
    logic.assistedTaskLimitsReviewed = lambda _node: True
    def joint_limits(joint_1_min=-30.0, joint_1_max=30.0):
        pair = lambda low, high: SimpleNamespace(minimum=low, maximum=high)
        return SimpleNamespace(
            joint_1=pair(joint_1_min, joint_1_max),
            joint_2=pair(0.0, 80.0),
            joint_3=pair(-90.0, 90.0),
            joint_4=pair(0.0, 75.0),
            joint_5=pair(-90.0, 90.0),
        )

    logic.robotDescriptionPaths = lambda: ("fixture.urdf", None)
    logic.getTaskJointLimits = lambda _node: joint_limits()
    mechanical_limits = joint_limits()
    monkeypatch.setattr(
        workflow_facade_module,
        "default_task_joint_limits_from_urdf",
        lambda _path: mechanical_limits,
    )
    logic.robotProfileFingerprint = lambda: "robot-a"
    logic.evaluatePreparedBranchEligibility = (
        lambda _node, _branch_id, *, registry: {"eligible": True}
    )
    monkeypatch.setattr(
        workflow_facade_module,
        "task_snapshot_invalidation_reasons",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        workflow_facade_module,
        "planner_comparison_scene_fingerprint",
        lambda _audit: "scene-a",
    )
    identity = {
        "branch_id": "branch-a",
        "task": "task-a",
        "base": "base-a",
        "home": "home-a",
        "trajectory": "trajectory-a",
        "robot_profile": "robot-a",
        "collision_audit": "scene-a",
    }
    if identity_changes:
        changed_identity = {**identity, "task": "task-b"}
        facade._identity_calls = 0

        def changing_identity():
            facade._identity_calls += 1
            return dict(identity) if facade._identity_calls == 1 else dict(changed_identity)

        facade.plannerComparisonIdentity = changing_identity
    else:
        facade.plannerComparisonIdentity = lambda: dict(identity)

    checked_positions = []
    bridge.check_moveit_static_joint_state = lambda positions: (
        checked_positions.append(dict(positions)) or (True, "static state clear", True)
    )
    fk_positions = []
    bridge.compute_tcp_pose_world_ras_mm = lambda positions, *, base_transform: (
        fk_positions.append((dict(positions), base_transform))
        or (
            True,
            "FK returned current tool pose",
            (
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 8.0),
                (0.0, 0.0, 0.0, 1.0),
            ),
        )
    )
    bridge.joint_command_status = lambda: SimpleNamespace(
        accepted=True,
        reason="latest command was accepted",
        minimum_clearance_m=0.001,
        minimum_self_distance_m=None,
        minimum_world_distance_m=None,
        first_body="",
        second_body="",
        world_object_count=1,
    )
    return facade, parameter_node, logic, bridge, checked_positions, fk_positions


def _set_manual_test_home(parameter_node, logic, payload):
    parameter_node.step6TaskHomeJson = "" if payload is None else json.dumps(payload)
    home = (
        None
        if payload is None
        else SimpleNamespace(
            base_fingerprint=payload["base_fingerprint"],
            to_dict=lambda: payload,
        )
    )
    logic.taskHomeRecord = lambda _node: home
    logic.taskHomeFreshnessIssues = lambda _node: (
        ("Save a case/base-specific Task Home.",)
        if home is None
        else ("Task Home belongs to a different base pose.",)
        if home.base_fingerprint != "base-a"
        else ()
    )
    return home


def test_manual_draft_state_evaluates_supplied_vector_read_only(monkeypatch):
    facade, _node, logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    request = dict(
        zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03))
    )
    accepted_before = dict(bridge.accepted)
    state_reads = []
    original_current_state = facade.currentRobotState

    def capture_current_state():
        state_reads.append(True)
        return original_current_state()

    facade.currentRobotState = capture_current_state
    events_before = list(facade._manual_simulation_events)
    history_before = list(facade._accepted_motion_history)

    result = facade.checkManualRobotDraftState(request)

    evaluation = result.details["manual_state_evaluation"]
    endpoint = evaluation["endpoint_evaluation"]
    assert result.success
    assert result.code == "manual_draft_evaluated"
    assert "not accepted" in result.message
    assert evaluation["input_status"] == "captured_review"
    assert evaluation["input_source"] == "captured_review"
    assert evaluation["input_joint_positions_si"] == request
    assert evaluation["input_joint_positions_si_after"] is None
    assert evaluation["requestedJointPositionsSi"] == request
    assert evaluation["draftWithinCommandLimits"] is True
    assert evaluation["limitAssessmentAuthoritative"] is True
    assert result.details["draftWithinCommandLimits"] is True
    assert result.details["limitMargins"] == evaluation["limitMargins"]
    assert evaluation["status"] == "passed"
    assert evaluation["target_endpoint_status"] == "failed"
    assert evaluation["identity_status"] == "current"
    assert endpoint["static_state_validity"] == {
        "status": "passed",
        "authoritative": True,
        "message": "static state clear",
    }
    assert endpoint["position_residual_mm"] == 2.0
    assert endpoint["drilling_axis_residual_deg"] == 0.0
    assert evaluation["routeAuthority"] == "none"
    assert evaluation["simulationOnly"] is True
    assert result.details["routeAuthority"] == "none"
    assert result.details["simulationOnly"] is True
    assert result.details["authoritative"] is True
    assert checked == [request]
    assert fk[0][0] == request
    assert state_reads == [True]
    assert bridge.accepted == accepted_before
    assert bridge.applied == []
    assert bridge.phase_calls == []
    assert logic.updated == []
    assert facade._manual_simulation_events == events_before
    assert facade._accepted_motion_history == history_before


def test_manual_draft_reports_reviewed_joint_limit_before_static_or_fk(monkeypatch):
    facade, _node, logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    task_limits = SimpleNamespace(
        joint_1=SimpleNamespace(minimum=-0.2, maximum=0.2),
        joint_2=SimpleNamespace(minimum=0.0, maximum=80.0),
        joint_3=SimpleNamespace(minimum=-90.0, maximum=90.0),
        joint_4=SimpleNamespace(minimum=0.0, maximum=75.0),
        joint_5=SimpleNamespace(minimum=-90.0, maximum=90.0),
    )
    logic.getTaskJointLimits = lambda _node: task_limits
    request = dict(zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03)))
    accepted_before = dict(bridge.accepted)
    diagnostic_before = _node.step6MotionDiagnosticJson

    result = facade.checkManualRobotDraftState(request)

    evaluation = result.details["manual_state_evaluation"]
    endpoint = evaluation["endpoint_evaluation"]
    assert not result.success and result.code == "manual_draft_state_invalid"
    assert result.details["draftWithinCommandLimits"] is False
    assert result.details["limitAssessmentAuthoritative"] is True
    assert evaluation["draftWithinCommandLimits"] is False
    assert evaluation["status"] == "failed"
    assert evaluation["identity_status"] == "current"
    assert evaluation["target_endpoint_status"] == "not_reached"
    assert endpoint["status"] == "not_reached"
    assert endpoint["static_state_validity"]["status"] == "not_reached"
    assert endpoint["static_state_validity"]["authoritative"] is False
    assert endpoint["fk"]["status"] == "not_reached"
    assert len(result.details["limitViolations"]) == 1
    violation = result.details["limitViolations"][0]
    assert violation["jointLabel"] == "J1"
    assert violation["jointName"] == ROS2_JOINT_SI_ORDER[0]
    assert violation["limitSource"] == "reviewed_task"
    assert violation["bound"] == "maximum"
    assert violation["boundDisplayValue"] == 0.2
    assert violation["unit"] == "deg"
    assert abs(violation["candidateDisplayValue"] - 0.5729577951308232) < 1.0e-12
    assert abs(violation["margin"] + 0.3729577951308232) < 1.0e-12
    assert "J1" in result.message and "reviewed_task maximum bound 0.2 deg" in result.message
    assert checked == [] and fk == []
    assert bridge.accepted == accepted_before
    assert bridge.applied == [] and bridge.phase_calls == []
    assert logic.updated == []
    assert _node.step6MotionDiagnosticJson == diagnostic_before


def test_manual_draft_reports_mechanical_limit_before_static_or_fk(monkeypatch):
    facade, _node, logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    reviewed_limits = SimpleNamespace(
        joint_1=SimpleNamespace(minimum=-40.0, maximum=40.0),
        joint_2=SimpleNamespace(minimum=0.0, maximum=80.0),
        joint_3=SimpleNamespace(minimum=-90.0, maximum=90.0),
        joint_4=SimpleNamespace(minimum=0.0, maximum=75.0),
        joint_5=SimpleNamespace(minimum=-90.0, maximum=90.0),
    )
    logic.getTaskJointLimits = lambda _node: reviewed_limits
    request = dict(zip(ROS2_JOINT_SI_ORDER, (0.6, 0.001, 0.02, 0.002, 0.03)))
    accepted_before = dict(bridge.accepted)

    result = facade.checkManualRobotDraftState(request)

    evaluation = result.details["manual_state_evaluation"]
    assert not result.success
    assert result.details["draftWithinCommandLimits"] is False
    assert result.details["limitViolations"][0]["limitSource"] == "mechanical"
    assert result.details["limitViolations"][0]["bound"] == "maximum"
    assert result.details["limitViolations"][0]["boundDisplayValue"] == 30.0
    assert evaluation["endpoint_evaluation"]["static_state_validity"]["status"] == "not_reached"
    assert checked == [] and fk == []
    assert bridge.accepted == accepted_before
    assert bridge.applied == [] and bridge.phase_calls == []
    assert logic.updated == []


def test_manual_draft_limit_inputs_unavailable_are_unknown_before_static_or_fk(
    monkeypatch,
):
    facade, _node, logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    request = dict(zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03)))
    accepted_before = dict(bridge.accepted)
    current_task_limits = logic.getTaskJointLimits
    current_mechanical_limits = workflow_facade_module.default_task_joint_limits_from_urdf

    for missing_source in ("reviewed_task", "mechanical"):
        logic.getTaskJointLimits = (
            (lambda _node: None)
            if missing_source == "reviewed_task"
            else current_task_limits
        )
        monkeypatch.setattr(
            workflow_facade_module,
            "default_task_joint_limits_from_urdf",
            (lambda _path: None)
            if missing_source == "mechanical"
            else current_mechanical_limits,
        )
        result = facade.checkManualRobotDraftState(request)

        evaluation = result.details["manual_state_evaluation"]
        assert not result.success
        assert result.code == "manual_draft_evaluation_incomplete"
        assert evaluation["status"] == "unknown"
        assert evaluation["identity_status"] == "current"
        assert evaluation["target_endpoint_status"] == "not_reached"
        assert evaluation["draftWithinCommandLimits"] is None
        assert result.details["draftWithinCommandLimits"] is None
        assert evaluation["endpoint_evaluation"]["static_state_validity"]["status"] == "not_reached"
        assert checked == [] and fk == []
        assert bridge.accepted == accepted_before
        assert bridge.applied == [] and bridge.phase_calls == []


def test_manual_draft_identity_unavailable_is_unknown_before_limit_or_static_check(
    monkeypatch,
):
    facade, _node, logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    facade._manual_jog_current_identity = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("identity unknown")
    )
    limit_calls = []
    logic.getTaskJointLimits = lambda _node: limit_calls.append(True)
    request = dict(zip(ROS2_JOINT_SI_ORDER, (0.6, 0.001, 0.02, 0.002, 0.03)))
    accepted_before = dict(bridge.accepted)

    result = facade.checkManualRobotDraftState(request)

    evaluation = result.details["manual_state_evaluation"]
    assert not result.success and result.code == "manual_draft_evaluation_incomplete"
    assert evaluation["status"] == "unknown"
    assert evaluation["identity_status"] == "unknown"
    assert evaluation["target_endpoint_status"] == "not_reached"
    assert result.details["draftWithinCommandLimits"] is None
    assert limit_calls == []
    assert checked == [] and fk == []
    assert bridge.accepted == accepted_before
    assert bridge.applied == [] and bridge.phase_calls == []


def test_manual_draft_state_suppresses_evidence_when_identity_becomes_stale(
    monkeypatch,
):
    facade, _node, _logic, bridge, checked, fk = _manual_endpoint_probe(
        monkeypatch, identity_changes=True
    )
    request = dict(
        zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03))
    )
    accepted_before = dict(bridge.accepted)

    result = facade.checkManualRobotDraftState(request)

    evaluation = result.details["manual_state_evaluation"]
    assert not result.success
    assert evaluation["stale"] is None
    assert evaluation["identity_status"] == "unknown"
    assert evaluation["input_status"] == "captured_review"
    assert evaluation["status"] == "unknown"
    assert evaluation["target_endpoint_status"] == "not_reached"
    assert evaluation["endpoint_evaluation"]["static_state_validity"]["status"] == "not_reached"
    assert checked == fk == []
    assert bridge.accepted == accepted_before
    assert bridge.applied == []
    assert bridge.phase_calls == []


def test_taskless_manual_draft_uses_authoritative_static_review_only(monkeypatch):
    facade, parameter_node, logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    logic.confirmedTaskRecord = lambda _node: None
    _set_manual_test_home(
        parameter_node,
        logic,
        {"base_fingerprint": "base-old", "joint_positions_si": [0.0] * 5},
    )
    request = dict(
        zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03))
    )
    accepted_before = dict(bridge.accepted)
    events_before = list(facade._manual_simulation_events)
    history_before = list(facade._accepted_motion_history)

    result = facade.checkManualRobotDraftState(request)

    evaluation = result.details["manual_state_evaluation"]
    identity = evaluation["identity_before"]
    endpoint = evaluation["endpoint_evaluation"]
    assert result.success and result.code == "manual_draft_evaluated"
    assert evaluation["status"] == "passed"
    assert evaluation["target_endpoint_status"] == "not_reached"
    assert evaluation["identity_status"] == "current"
    assert identity["branch_id"] == "branch-a"
    assert identity["task"].startswith("unconfirmed:")
    assert identity["base"] == "base-a"
    assert identity["home"].startswith("unconfirmed_home:")
    assert identity["trajectory"] == "trajectory-a"
    assert identity["robot_profile"] == "robot-a"
    assert identity["collision_audit"] == "scene-a"
    assert identity["limits"] == "limits-a"
    assert endpoint["static_state_validity"] == {
        "status": "passed",
        "authoritative": True,
        "message": "static state clear",
    }
    assert evaluation["target_ras_mm"] is None
    assert endpoint["position_residual_mm"] is None
    assert endpoint["drilling_axis_residual_deg"] is None
    assert checked == [request]
    assert fk[0][0] == request
    assert bridge.accepted == accepted_before
    assert bridge.applied == []
    assert bridge.phase_calls == []
    assert logic.updated == []
    assert facade._manual_simulation_events == events_before
    assert facade._accepted_motion_history == history_before
    assert not parameter_node.robotBaseMountLocked


def test_taskless_manual_draft_rejects_authoritative_static_failure(monkeypatch):
    facade, parameter_node, logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    logic.confirmedTaskRecord = lambda _node: None
    _set_manual_test_home(parameter_node, logic, None)
    bridge.check_moveit_static_joint_state = lambda positions: (
        checked.append(dict(positions)) or (False, "static collision", True)
    )
    request = dict(
        zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03))
    )
    accepted_before = dict(bridge.accepted)

    result = facade.checkManualRobotDraftState(request)

    evaluation = result.details["manual_state_evaluation"]
    endpoint = evaluation["endpoint_evaluation"]
    assert not result.success and result.code == "manual_draft_state_invalid"
    assert evaluation["status"] == "failed"
    assert evaluation["target_endpoint_status"] == "not_reached"
    assert evaluation["identity_before"]["home"].startswith("unconfirmed_home:")
    assert evaluation["identity_status"] == "current"
    assert endpoint["static_state_validity"] == {
        "status": "failed",
        "authoritative": True,
        "message": "static collision",
    }
    assert "static collision" in result.message
    assert "FK was not reached" in result.message
    assert checked == [request]
    assert fk == []
    assert bridge.accepted == accepted_before
    assert bridge.applied == []
    assert bridge.phase_calls == []
    assert logic.updated == []


def test_taskless_manual_draft_passes_without_a_home_record(monkeypatch):
    facade, parameter_node, logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    logic.confirmedTaskRecord = lambda _node: None
    _set_manual_test_home(parameter_node, logic, None)
    request = dict(
        zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03))
    )
    accepted_before = dict(bridge.accepted)

    result = facade.checkManualRobotDraftState(request)

    evaluation = result.details["manual_state_evaluation"]
    assert result.success and result.details["authoritative"] is True
    assert evaluation["identity_before"]["home"].startswith("unconfirmed_home:")
    assert evaluation["status"] == "passed"
    assert evaluation["target_endpoint_status"] == "not_reached"
    assert evaluation["endpoint_evaluation"]["static_state_validity"]["authoritative"]
    assert checked == [request] and fk[0][0] == request
    assert bridge.accepted == accepted_before
    assert bridge.applied == [] and bridge.phase_calls == [] and logic.updated == []


def test_taskless_manual_draft_becomes_unknown_when_home_is_created_during_query(
    monkeypatch,
):
    facade, parameter_node, logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    logic.confirmedTaskRecord = lambda _node: None
    _set_manual_test_home(parameter_node, logic, None)
    original_static_check = bridge.check_moveit_static_joint_state

    def check_then_create_home(positions):
        result = original_static_check(positions)
        _set_manual_test_home(
            parameter_node,
            logic,
            {"base_fingerprint": "base-a", "joint_positions_si": [0.1] * 5},
        )
        return result

    bridge.check_moveit_static_joint_state = check_then_create_home
    request = dict(
        zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03))
    )
    accepted_before = dict(bridge.accepted)

    result = facade.checkManualRobotDraftState(request)

    evaluation = result.details["manual_state_evaluation"]
    assert not result.success
    assert evaluation["identity_before"]["home"].startswith("unconfirmed_home:")
    assert evaluation["identity_after"]["home"].startswith("unconfirmed_home:")
    assert evaluation["identity_before"]["home"] != evaluation["identity_after"]["home"]
    assert evaluation["stale"] is True and evaluation["identity_status"] == "stale"
    assert evaluation["status"] == "unknown"
    assert evaluation["target_endpoint_status"] == "unknown"
    assert evaluation["endpoint_evaluation"]["static_state_validity"] == {
        "status": "passed",
        "authoritative": True,
        "message": "static state clear",
    }
    assert checked == [request] and fk[0][0] == request
    assert bridge.accepted == accepted_before
    assert bridge.applied == [] and bridge.phase_calls == []


def test_confirmed_manual_draft_and_jog_still_require_fresh_home(monkeypatch):
    request = dict(
        zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03))
    )
    for payload in (
        {"base_fingerprint": "base-old", "joint_positions_si": [0.0] * 5},
        None,
    ):
        facade, parameter_node, logic, bridge, checked, fk = _manual_endpoint_probe(
            monkeypatch
        )
        _set_manual_test_home(parameter_node, logic, payload)
        draft = facade.checkManualRobotDraftState(request)
        evaluation = draft.details["manual_state_evaluation"]
        assert not draft.success
        if payload is None:
            assert draft.code == "manual_draft_evaluation_incomplete"
            assert "Task Home" in evaluation["reason"]
            assert evaluation["status"] == "unknown"
            assert evaluation["identity_status"] == "unknown"
            assert evaluation["target_endpoint_status"] == "not_reached"
        else:
            assert evaluation["status"] == "unknown"
            assert evaluation["identity_status"] == "unknown"
            assert evaluation["target_endpoint_status"] == "not_reached"
        assert evaluation["endpoint_evaluation"]["static_state_validity"][
            "status"
        ] == "not_reached"
        assert checked == [] and fk == [] and bridge.applied == []

        facade, parameter_node, logic, bridge, request, *_rest = _manual_jog_probe(
            monkeypatch
        )
        _set_manual_test_home(parameter_node, logic, payload)
        jog = facade.guardManualRobotJog(request)
        assert not jog.success
        assert jog.details["guardAccepted"] is None
        assert jog.details["identityStatus"] == "unknown"
        assert jog.details["manualJogStatus"] == "unknown"
        assert bridge.raw_requests == [] and bridge.accepted != request


def test_taskless_manual_draft_becomes_unknown_when_limits_identity_changes(
    monkeypatch,
):
    facade, _node, logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    logic.confirmedTaskRecord = lambda _node: None
    limits_identity = ["limits-a"]
    logic.step6TaskLimitsFingerprint = lambda _node: limits_identity[0]
    original_static_check = bridge.check_moveit_static_joint_state

    def check_then_change_identity(positions):
        result = original_static_check(positions)
        limits_identity[0] = "limits-b"
        return result

    bridge.check_moveit_static_joint_state = check_then_change_identity
    request = dict(
        zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03))
    )
    accepted_before = dict(bridge.accepted)

    result = facade.checkManualRobotDraftState(request)

    evaluation = result.details["manual_state_evaluation"]
    assert not result.success
    assert evaluation["stale"] is True
    assert evaluation["identity_status"] == "stale"
    assert evaluation["status"] == "unknown"
    assert evaluation["target_endpoint_status"] == "unknown"
    assert evaluation["identity_before"] != evaluation["identity_after"]
    assert checked == [request]
    assert bridge.accepted == accepted_before
    assert bridge.applied == []
    assert bridge.phase_calls == []
    assert logic.updated == []


def test_taskless_manual_draft_discards_attribution_if_task_appears_during_query(
    monkeypatch,
):
    facade, _node, logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    task = SimpleNamespace(
        snapshot_fingerprint="task-a",
        entry_ras_mm=(0.0, 0.0, 0.0),
        target_ras_mm=(0.0, 0.0, 10.0),
        base_fingerprint="base-a",
        home_fingerprint="home-a",
        trajectory_revision="trajectory-a",
        robot_profile_fingerprint="robot-a",
    )
    current_task = [None]
    logic.confirmedTaskRecord = lambda _node: current_task[0]
    original_static_check = bridge.check_moveit_static_joint_state

    def check_then_confirm_task(positions):
        result = original_static_check(positions)
        current_task[0] = task
        return result

    bridge.check_moveit_static_joint_state = check_then_confirm_task
    request = dict(
        zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03))
    )
    accepted_before = dict(bridge.accepted)
    events_before = list(facade._manual_simulation_events)
    history_before = list(facade._accepted_motion_history)

    result = facade.checkManualRobotDraftState(request)

    evaluation = result.details["manual_state_evaluation"]
    assert not result.success
    assert evaluation["identity_before"]["task"].startswith("unconfirmed:")
    assert evaluation["identity_after"]["task"] == "task-a"
    assert evaluation["stale"] is True
    assert evaluation["identity_status"] == "stale"
    assert evaluation["status"] == "unknown"
    assert evaluation["target_endpoint_status"] == "unknown"
    assert checked == [request]
    assert bridge.accepted == accepted_before
    assert bridge.applied == []
    assert bridge.phase_calls == []
    assert logic.updated == []
    assert facade._manual_simulation_events == events_before
    assert facade._accepted_motion_history == history_before


def test_manual_draft_static_rejection_is_not_reported_as_success(monkeypatch):
    facade, _node, _logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    bridge.check_moveit_static_joint_state = lambda positions: (
        checked.append(dict(positions)) or (False, "static collision", True)
    )
    request = dict(
        zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03))
    )
    accepted_before = dict(bridge.accepted)

    result = facade.checkManualRobotDraftState(request)

    evaluation = result.details["manual_state_evaluation"]
    static = evaluation["endpoint_evaluation"]["static_state_validity"]
    assert not result.success
    assert result.code == "manual_draft_state_invalid"
    assert "static collision" in result.message
    assert "FK was not reached" in result.message
    assert evaluation["status"] == "failed"
    assert evaluation["target_endpoint_status"] == "failed"
    assert static == {
        "status": "failed",
        "authoritative": True,
        "message": "static collision",
    }
    assert checked == [request]
    assert fk == []
    assert bridge.accepted == accepted_before
    assert bridge.applied == []
    assert bridge.phase_calls == []


def test_manual_draft_state_rejects_invalid_vectors_without_authority(monkeypatch):
    facade, _node, _logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    request = dict(
        zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03))
    )
    invalid_vectors = (
        {**request, "unexpected_joint": 0.0},
        {name: value for name, value in request.items() if name != ROS2_JOINT_SI_ORDER[0]},
        {**request, ROS2_JOINT_SI_ORDER[0]: True},
        {**request, ROS2_JOINT_SI_ORDER[0]: float("nan")},
        {**request, ROS2_JOINT_SI_ORDER[0]: "0.01"},
    )

    for invalid in invalid_vectors:
        result = facade.checkManualRobotDraftState(invalid)
        evaluation = result.details["manual_state_evaluation"]
        assert not result.success
        assert result.code == "manual_draft_invalid_request"
        assert result.details["authoritative"] is False
        assert evaluation["status"] == "not_reached"
        assert evaluation["input_status"] == "invalid"
        assert evaluation["endpoint_evaluation"]["static_state_validity"][
            "authoritative"
        ] is False
        assert evaluation["routeAuthority"] == "none"
        assert evaluation["simulationOnly"] is True

    assert checked == []
    assert fk == []
    assert bridge.applied == []
    assert bridge.phase_calls == []


def test_manual_endpoint_check_separates_current_validity_from_target_residual(
    monkeypatch,
):
    facade, parameter_node, logic, bridge, checked, fk = _manual_endpoint_probe(
        monkeypatch
    )

    result = facade.checkStateValidity()

    evidence = result.details["manual_state_evaluation"]
    assert result.success
    assert evidence["status"] == "passed"
    assert evidence["target_endpoint_status"] == "failed"
    assert evidence["identity_status"] == "current"
    assert evidence["input_status"] == "current"
    assert evidence["endpoint_evaluation"]["static_state_validity"]["status"] == "passed"
    assert evidence["endpoint_evaluation"]["position_residual_mm"] == 2.0
    assert checked == [evidence["input_joint_positions_si"]]
    assert fk[0][0] == evidence["input_joint_positions_si"]
    assert "current-state static=passed" in result.message
    assert "target endpoint=failed" in result.message
    assert parameter_node.step6MotionDiagnosticJson == "preserve-this-record"
    assert bridge.applied == []
    assert bridge.phase_calls == []
    assert logic.updated == []


def test_manual_endpoint_check_marks_identity_change_stale(monkeypatch):
    facade, _parameter_node, _logic, _bridge, checked, _fk = _manual_endpoint_probe(
        monkeypatch, identity_changes=True
    )

    evidence = facade.checkStateValidity().details["manual_state_evaluation"]

    assert evidence["stale"] is True
    assert evidence["identity_status"] == "stale"
    assert evidence["status"] == "unknown"
    assert evidence["target_endpoint_status"] == "unknown"
    assert evidence["endpoint_evaluation"]["static_state_validity"]["status"] == "passed"
    assert len(checked) == 1


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


def test_post_preentry_motion_cost_uses_only_canonical_arm_joints():
    first = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    spindle_only = dict(first)
    arm_move = dict(first)
    arm_move[ROS2_JOINT_SI_ORDER[0]] = 0.5
    assert DENTORobotWorkflowFacade._arm_path_motion_cost(
        SimpleNamespace(waypoint_joint_vectors_si=(first, dict(first)))
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
    assert "validate_only" in source
    assert "preflight_positions_" in source


def _manual_jog_probe(monkeypatch):
    facade, parameter_node, logic, bridge = make_facade()
    parameter_node.step6TaskHomeJson = ""
    parameter_node.robotBaseTransform.active = True
    parameter_node.step6PlanningContextImported = True
    parameter_node.step6TrajectoryRegistryJson = json.dumps(
        {"selected_branch_id": "branch-a", "prepared_branches": {"branch-a": {}}}
    )
    parameter_node.targetToothSegmentId = "tooth-segment"
    parameter_node.step6ToolFrame = "dentobot_drill_tcp"
    facade._planning_scene_synchronized = True
    facade._planning_scene_object_count = 2

    snapshot = SimpleNamespace(
        snapshot_fingerprint="task-a",
        home_fingerprint="home-a",
        trajectory_revision="trajectory-a",
    )
    audit = SimpleNamespace(
        status="Acknowledged",
        runtime_acknowledgement={
            "status": "Acknowledged",
            "acknowledged_object_ids": ["jaw", "tooth"],
        },
    )
    home = SimpleNamespace(to_dict=lambda: {"home": "home-a"})
    logic.confirmedTaskRecord = lambda _node: snapshot
    logic.taskHomeRecord = lambda _node: home
    logic.taskHomeFreshnessIssues = lambda _node: ()
    logic.collisionSceneAuditRecord = lambda _node: audit
    logic.robotBaseFingerprint = lambda _node: "base-a"
    logic.robotProfileFingerprint = lambda: "robot-a"
    logic.step6TrajectoryRevision = lambda _node: "trajectory-a"
    logic.step6TaskLimitsFingerprint = lambda _node: "limits-a"
    logic.evaluatePreparedBranchEligibility = (
        lambda *_args, **_kwargs: {"eligible": True}
    )
    logic.robotDescriptionPaths = lambda: ("fake.urdf", "fake-root")
    facade._step6_read_only_freshness_issues = lambda _node, *, include_home=True: (
        logic.taskHomeFreshnessIssues(_node) if include_home else ()
    )
    monkeypatch.setattr(
        workflow_facade_module,
        "task_snapshot_invalidation_reasons",
        lambda *_args, **_kwargs: (),
    )
    monkeypatch.setattr(
        workflow_facade_module,
        "planner_comparison_scene_fingerprint",
        lambda _audit: "scene-a",
    )

    def limits(j1_min=-30.0, j1_max=30.0):
        pair = lambda low, high: SimpleNamespace(minimum=low, maximum=high)
        return SimpleNamespace(
            joint_1=pair(j1_min, j1_max),
            joint_2=pair(0.0, 80.0),
            joint_3=pair(-90.0, 90.0),
            joint_4=pair(0.0, 75.0),
            joint_5=pair(-90.0, 90.0),
        )

    mechanical = limits()
    task = limits()
    logic.getTaskJointLimits = lambda _node: task
    monkeypatch.setattr(
        workflow_facade_module,
        "default_task_joint_limits_from_urdf",
        lambda _path: mechanical,
    )
    bridge.accepted = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    scene_objects = ({"id": "jaw"}, {"id": "tooth"})

    def raw_status(accepted, requested, current, reason):
        return SimpleNamespace(
            accepted=accepted,
            reason=reason,
            operation="jog",
            query_only=False,
            requested_positions=tuple(requested[name] for name in ROS2_JOINT_SI_ORDER),
            accepted_positions=tuple(current[name] for name in ROS2_JOINT_SI_ORDER),
            checked_samples=3,
            minimum_clearance_m=0.001,
            minimum_self_distance_m=0.002,
            minimum_world_distance_m=0.003,
            first_body="",
            second_body="",
            world_object_count=2,
            world_objects=scene_objects,
            world_object_evidence_present=True,
        )

    bridge.raw_status = raw_status(True, bridge.accepted, bridge.accepted, "current")
    bridge.legacy_status_reads = []
    bridge.joint_command_status = lambda: bridge.legacy_status_reads.append(True) or bridge.raw_status
    bridge.last_accepted_joint_positions_si = lambda: dict(bridge.accepted)
    bridge.monitored_joint_positions_si = lambda: dict(bridge.accepted)
    bridge.manual_requests = []
    bridge.raw_requests = bridge.manual_requests
    bridge.raw_reject = False
    bridge.raw_silent = False
    bridge.manual_policy_id = workflow_facade_module.MANUAL_JOINT_POLICY_ID
    bridge.manual_request_id = None
    bridge.manual_session_id = None
    bridge.response_request_id = None
    bridge.response_session_id = None
    bridge.raw_policy_fingerprint = "task-phase-fingerprint-must-not-identify-raw-policy"
    bridge.query_requests = []
    bridge.query_accepted = None
    bridge.query_response_id = None
    bridge.query_session_id = None
    bridge.query_policy_id = None
    bridge.query_object_ids = None
    bridge.query_static_valid = False
    bridge.query_monitor_matches = True
    bridge.query_commit_fails = False
    bridge.query_commit_calls = []

    def apply_manual(positions, request_id, session_id):
        requested = {name: float(positions[name]) for name in ROS2_JOINT_SI_ORDER}
        bridge.manual_requests.append((requested, request_id, session_id))
        bridge.manual_request_id = request_id
        bridge.manual_session_id = session_id
        if bridge.raw_silent:
            return None, "manual guard timed out", None
        if bridge.raw_reject:
            bridge.raw_status = raw_status(
                False, requested, bridge.accepted, "self collision"
            )
            accepted = False
            message = "self collision"
        else:
            bridge.accepted = dict(requested)
            bridge.raw_status = raw_status(True, requested, bridge.accepted, "clear")
            accepted = True
            message = "clear"
        bridge.raw_status = SimpleNamespace(
            **bridge.raw_status.__dict__,
            request_id=bridge.response_request_id or bridge.manual_request_id,
            session_id=bridge.response_session_id or bridge.manual_session_id,
            policy_id=bridge.manual_policy_id,
            command_valid=True,
            collision_scene_policy_fingerprint=bridge.raw_policy_fingerprint,
        )
        return accepted, message, bridge.raw_status

    bridge.apply_manual_joint_positions_si = apply_manual

    def query_manual(echo, request_id, session_id):
        echo = {name: float(echo[name]) for name in ROS2_JOINT_SI_ORDER}
        bridge.query_requests.append((echo, request_id, session_id))
        accepted = bridge.query_accepted or bridge.accepted
        status = raw_status(
            bridge.query_static_valid, echo, accepted, "static collision"
        )
        ids = bridge.query_object_ids or ["jaw", "tooth"]
        status_values = dict(status.__dict__)
        status_values.update(
            request_id=bridge.query_response_id or request_id,
            session_id=bridge.query_session_id or session_id,
            policy_id=bridge.query_policy_id or workflow_facade_module.MANUAL_JOINT_POLICY_ID,
            command_valid=True,
            operation="state_query",
            query_only=True,
            world_objects=tuple({"id": value} for value in ids),
            collision_scene_policy_fingerprint=bridge.raw_policy_fingerprint,
        )
        status = SimpleNamespace(**status_values)
        return status, status.reason

    def wait_for_monitored(expected):
        if not bridge.query_monitor_matches:
            return False, "monitored state mismatch", dict(bridge.accepted), float("inf")
        return True, "matched", dict(expected), 0.0

    def commit_query(status, _echo, _request_id, _session_id):
        bridge.query_commit_calls.append(status)
        if bridge.query_commit_fails:
            return False, "commit failed"
        bridge.accepted = dict(zip(ROS2_JOINT_SI_ORDER, status.accepted_positions))
        return True, "committed"

    bridge.query_manual_joint_state_si = query_manual
    bridge.wait_for_monitored_joint_positions_si = wait_for_monitored
    bridge.accept_manual_joint_state_reconciliation = commit_query
    request = dict(
        zip(ROS2_JOINT_SI_ORDER, (0.01, 0.001, 0.02, 0.002, 0.03))
    )
    return facade, parameter_node, logic, bridge, request, limits, task, mechanical


def _manual_task_home_review_probe(monkeypatch):
    facade, parameter_node, logic, bridge, *_rest = _manual_jog_probe(monkeypatch)
    return facade, parameter_node, logic, bridge


def _unreviewed_taskless_home_review_probe(monkeypatch):
    facade, parameter_node, logic, bridge = _manual_task_home_review_probe(monkeypatch)
    logic.confirmedTaskRecord = lambda _node: None
    logic.assistedTaskLimitsReviewed = lambda _node: False
    return facade, parameter_node, logic, bridge


def _manual_task_home_candidate(values=(0.01, 0.001, 0.02, 0.002, 0.03)):
    return dict(zip(ROS2_JOINT_SI_ORDER, values))


def _home_draft_apply_probe(monkeypatch):
    facade, parameter_node, logic, bridge = _unreviewed_taskless_home_review_probe(monkeypatch)
    _set_manual_test_home(parameter_node, logic, None)
    goal = _manual_task_home_candidate()
    start = dict(bridge.accepted)
    bridge.home_plans = []

    def plan(**request):
        bridge.home_plans.append(request)
        return SimpleNamespace(success=True, message="planned", waypoint_joint_vectors_si=(start, goal))

    def apply(positions):
        bridge.applied.append(dict(positions))
        if bridge.reject:
            return False, "collision"
        bridge.accepted = dict(positions)
        return True, "accepted"

    bridge.plan_moveit_joint_goal = plan
    bridge.apply_joint_positions_si_to_motion_control = apply
    facade._checkStateValidity = lambda: RobotActionResult(
        True, "state_valid", "authoritative", details={"authoritative": True}
    )
    return facade, parameter_node, logic, bridge, start, goal


def test_home_draft_plan_apply_without_saved_home_preserves_separate_acceptance(monkeypatch):
    facade, node, logic, bridge, start, goal = _home_draft_apply_probe(monkeypatch)
    result = facade.applyTaskHomeDraft(goal)
    assert result.success and result.code == "task_home_draft_applied"
    assert bridge.home_plans[0]["start_joint_positions_si"] == start
    assert bridge.home_plans[0]["goal_joint_positions_si"] == goal
    assert bridge.applied == [start, goal]
    assert bridge.accepted == goal
    assert node.step6TaskHomeJson == "" and logic.taskHomeRecord(node) is None
    assert result.details["homeSaved"] is False
    assert result.details["runtimeValidated"] is False
    assert not facade._manual_jog_reconciliation_required
    assert not facade._manual_jog_in_progress
    assert facade.stageManualTaskHomeReview(goal).success


def test_home_draft_snaps_a_moveit_endpoint_within_goal_tolerance_through_the_guard(monkeypatch):
    """Live 2026-10-04: MoveIt ended 8.4e-5 from the draft and the 1e-12 check refused it."""
    facade, _node, _logic, bridge, start, goal = _home_draft_apply_probe(monkeypatch)
    near = {name: value + 8.4e-5 for name, value in goal.items()}
    bridge.plan_moveit_joint_goal = lambda **_kwargs: SimpleNamespace(
        success=True, message="planned", waypoint_joint_vectors_si=(start, near)
    )
    result = facade.applyTaskHomeDraft(goal)
    assert result.success and result.code == "task_home_draft_applied", result.message
    assert bridge.applied == [start, near, goal]  # the exact draft is its own guarded waypoint
    assert bridge.accepted == goal
    assert 8.0e-5 < result.details["finalSnapSi"] < 9.0e-5
    assert result.details["appliedWaypointCount"] == 3

    # A guard rejection of the snap waypoint is still a latched, reported failure.
    facade, _node, _logic, bridge, start, goal = _home_draft_apply_probe(monkeypatch)
    near = {name: value + 8.4e-5 for name, value in goal.items()}
    bridge.plan_moveit_joint_goal = lambda **_kwargs: SimpleNamespace(
        success=True, message="planned", waypoint_joint_vectors_si=(start, near)
    )
    accept = bridge.apply_joint_positions_si_to_motion_control
    bridge.apply_joint_positions_si_to_motion_control = (
        lambda positions: (False, "collision") if positions == goal else accept(positions)
    )
    result = facade.applyTaskHomeDraft(goal)
    assert not result.success and result.code == "task_home_draft_guard_rejected"
    assert facade._manual_jog_reconciliation_required


def test_home_draft_already_applied_is_a_noop_success_not_an_error(monkeypatch):
    """Live 2026-10-04: Plan + Apply after the draft was applied raised MoveIt's equal start/goal error."""
    facade, _node, _logic, bridge, _start, goal = _home_draft_apply_probe(monkeypatch)
    bridge.accepted = dict(goal)
    facade.currentRobotState = lambda: SimpleNamespace(joint_positions_si=dict(bridge.accepted))
    result = facade.applyTaskHomeDraft(goal)
    assert result.success and result.code == "task_home_draft_applied", result.message
    assert result.details["alreadyAtDraft"] is True
    assert bridge.home_plans == [] and bridge.applied == []
    assert not facade._manual_jog_reconciliation_required and not facade._manual_jog_in_progress

    # Within the monitored tolerance but not exact: no MoveIt, one guarded exact waypoint.
    facade, _node, _logic, bridge, _start, goal = _home_draft_apply_probe(monkeypatch)
    near = {name: value + 5.0e-5 for name, value in goal.items()}
    bridge.accepted = dict(near)
    facade.currentRobotState = lambda: SimpleNamespace(joint_positions_si=dict(bridge.accepted))
    result = facade.applyTaskHomeDraft(goal)
    assert result.success, result.message
    assert bridge.home_plans == [] and bridge.applied == [goal] and bridge.accepted == goal


def test_task_home_validation_gap_names_the_exact_clause():
    """Live 2026-10-04: enabling spindle contact silently un-validated Home and froze the 6.3 planner."""
    gap = workflow_facade_module.DENTORobotWorkflowFacade.taskHomeValidationGap
    record = SimpleNamespace(
        runtime_validation_status="Validated", collision_audit_fingerprint="audit-1",
        guard_policy_fingerprint="policy-default",
    )

    def make(**changes):
        state = dict(freshness=(), record=record, ros=True, audit="audit-1",
                     policy="policy-default", key="k", live_key="k")
        state.update(changes)
        node = SimpleNamespace(robotBaseTransform=object())
        logic = SimpleNamespace(
            taskHomeFreshnessIssues=lambda _n: state["freshness"],
            taskHomeRecord=lambda _n: state["record"],
            collisionSceneAuditRecord=lambda _n: SimpleNamespace(audit_fingerprint=state["audit"]),
            isRos2MotionControlActive=lambda _b: state["ros"],
        )
        fake = SimpleNamespace(
            _parameter_node=lambda: node, _logic=logic,
            _strict_guard_policy_fingerprint=lambda: state["policy"],
            _task_home_runtime_key=lambda _r: state["live_key"],
            _runtime_validated_task_home_key=state["key"],
        )
        return gap(fake, node)

    assert make() == ""
    assert "stale" in make(freshness=("Task Home belongs to a different base pose.",))
    assert "Save a case/base-specific Task Home" in make(record=None)
    assert "Connect ROS" in make(ros=False)
    assert "not live-validated" in make(record=SimpleNamespace(
        runtime_validation_status="Unreviewed", collision_audit_fingerprint="audit-1",
        guard_policy_fingerprint="policy-default"))
    assert "collision scene changed" in make(audit="audit-2")
    policy = make(policy="policy-contact")
    assert "different guard policy" in policy and "spindle-housing contact option" in policy
    assert "cleared by a later robot action" in make(live_key="other")


def test_home_draft_endpoint_beyond_goal_tolerance_is_still_refused(monkeypatch):
    facade, _node, _logic, bridge, start, goal = _home_draft_apply_probe(monkeypatch)
    far = {name: value + 5.0e-4 for name, value in goal.items()}
    bridge.plan_moveit_joint_goal = lambda **_kwargs: SimpleNamespace(
        success=True, message="planned", waypoint_joint_vectors_si=(start, far)
    )
    result = facade.applyTaskHomeDraft(goal)
    assert not result.success and "beyond the goal tolerance" in result.message
    assert bridge.applied == [] and bridge.accepted == start


def test_home_draft_plan_failure_or_wrong_endpoint_applies_nothing(monkeypatch):
    for success, endpoint in ((False, None), (True, "wrong"), (True, "nan")):
        facade, node, logic, bridge, start, goal = _home_draft_apply_probe(monkeypatch)
        wrong = dict(goal)
        wrong[ROS2_JOINT_SI_ORDER[0]] = float("nan") if endpoint == "nan" else 1.0
        bridge.plan_moveit_joint_goal = lambda **_kwargs: SimpleNamespace(
            success=success, message="no solution", waypoint_joint_vectors_si=(start, wrong)
        )
        result = facade.applyTaskHomeDraft(goal)
        assert not result.success
        assert bridge.applied == [] and bridge.accepted == start
        assert node.step6TaskHomeJson == "" and logic.taskHomeRecord(node) is None
        assert not facade._manual_jog_reconciliation_required
        assert not facade._manual_jog_in_progress


def test_home_draft_can_apply_exact_reviewed_candidate_but_not_an_edited_or_rejected_one(monkeypatch):
    for state in ("current", "edited", "rejected"):
        facade, _node, _logic, bridge, _start, goal = _home_draft_apply_probe(monkeypatch)
        assert facade.stageManualTaskHomeReview(goal).success
        if state == "edited":
            goal = {**goal, ROS2_JOINT_SI_ORDER[0]: 0.03}
        elif state == "rejected":
            facade._manual_task_home_review_status = "rejected"
        result = facade.applyTaskHomeDraft(goal)
        assert result.success is (state == "current")
        assert bool(bridge.home_plans) is (state == "current")
        assert facade._manual_task_home_review is not None


def test_home_draft_requires_current_scene_finite_state_and_no_outstanding_review(monkeypatch):
    for blocker in ("review", "uncertain", "reconcile", "scene", "start_nan", "bad_goal", "stale"):
        facade, _node, _logic, bridge, _start, goal = _home_draft_apply_probe(monkeypatch)
        if blocker == "review":
            facade._manual_task_home_review = {"candidate": goal}
        elif blocker == "uncertain":
            facade._manual_task_home_acceptance_uncertain = "may have committed"
        elif blocker == "reconcile":
            facade._manual_jog_reconciliation_required = True
        elif blocker == "scene":
            facade._planning_scene_synchronized = False
        elif blocker == "start_nan":
            bridge.monitored_joint_positions_si = lambda: {**bridge.accepted, ROS2_JOINT_SI_ORDER[0]: float("nan")}
        elif blocker == "bad_goal":
            goal = {**goal, "extra": 0.0}
        else:
            facade._step6_read_only_freshness_issues = lambda *_args, **_kwargs: ("stale Base",)
        result = facade.applyTaskHomeDraft(goal)
        assert not result.success, blocker
        assert bridge.home_plans == [] and bridge.applied == [], blocker


def test_home_draft_partial_or_unknown_application_latches_native_reconciliation(monkeypatch):
    for failure in ("guard", "monitor", "identity"):
        facade, _node, _logic, bridge, _start, goal = _home_draft_apply_probe(monkeypatch)
        if failure == "guard":
            apply = bridge.apply_joint_positions_si_to_motion_control
            def reject_goal(positions):
                if positions == goal:
                    return False, "collision"
                return apply(positions)
            bridge.apply_joint_positions_si_to_motion_control = reject_goal
        elif failure == "monitor":
            bridge.wait_for_monitored_joint_positions_si = lambda _goal: (False, "timeout", {}, float("inf"))
        else:
            identity = facade._manual_jog_current_identity
            reads = []
            def change_identity(*args, **kwargs):
                reads.append(True)
                current = identity(*args, **kwargs)
                return {**current, "base": "changed"} if len(reads) > 2 else current
            facade._manual_jog_current_identity = change_identity
        result = facade.applyTaskHomeDraft(goal)
        assert not result.success
        assert facade._manual_jog_reconciliation_required
        assert facade._manual_jog_uncertainty["forTaskHomeReview"] is True
        assert not facade._manual_jog_in_progress
        assert not facade.applyTaskHomeDraft(goal).success
        assert "Reconcile State" in result.message


def test_home_draft_reconciliation_keeps_home_setup_context_without_assisted_review(monkeypatch):
    facade, _node, _logic, bridge, _start, goal = _home_draft_apply_probe(monkeypatch)
    bridge.reject = True
    result = facade.applyTaskHomeDraft(goal)
    assert not result.success and facade._manual_jog_reconciliation_required
    reconciled = facade.reconcileManualRobotJog()
    assert reconciled.success, reconciled.message
    assert not facade._manual_jog_reconciliation_required
    assert bridge.query_requests
    assert facade._manual_task_home_review is None


def _offline_task_home_review_probe(monkeypatch):
    facade, parameter_node, logic, bridge = _manual_task_home_review_probe(monkeypatch)
    parameter_node.robotBaseTransform.active = False
    parameter_node.step6TrajectoryRegistryJson = json.dumps(
        {
            "selected_branch_id": "branch-a",
            "prepared_branches": {
                "branch-a": {
                    "primary_trajectory_id": "trajectory-id",
                    "trajectory_ids": ["trajectory-id"],
                    "revision": 3,
                    "verification_revision": 4,
                }
            },
        }
    )
    parameter_node.trajectoryLine = SimpleNamespace(
        GetAttribute=lambda _name: "trajectory-id"
    )
    logic.step6BasePlacementFreshnessIssues = lambda _node: ()
    logic.evaluateCaseFoundationEligibility = lambda _node: {
        "pose": {"eligible": True},
        "base": {"eligible": True},
    }
    logic.buildCaseFoundationSnapshot = lambda _node: SimpleNamespace(
        case_identity="case-a",
        foundation_fingerprint="foundation-a",
        to_dict=lambda: {
            "case": "case-a",
            "task_home_configuration": {"excluded": True},
        },
    )
    logic.step6TrajectoryRevision = lambda _node: "trajectory-revision-a"
    logic.evaluatePreparedBranchEligibility = (
        lambda *_args, **_kwargs: {"eligible": True}
    )
    logic.taskHomeFreshnessIssues = lambda _node: ()
    home_store = {"record": None, "saveCalls": []}

    def task_home_record(_node):
        return home_store["record"]

    def save_task_home(_node, *, runtime_validation, joint_positions_si):
        home_store["saveCalls"].append(
            (dict(runtime_validation), dict(joint_positions_si))
        )
        previous = home_store["record"]
        revision = 1 if previous is None else previous.revision + 1
        payload = {
            "revision": revision,
            "joint_names": list(ROS2_JOINT_SI_ORDER),
            "joint_positions_si": [
                joint_positions_si[name] for name in ROS2_JOINT_SI_ORDER
            ],
            "base_fingerprint": "base-a",
            "robot_profile_fingerprint": "robot-a",
            "runtime_validation_status": runtime_validation[
                "runtimeValidationStatus"
            ],
        }
        home_store["record"] = SimpleNamespace(
            revision=revision,
            joint_names=tuple(payload["joint_names"]),
            joint_positions_si=tuple(payload["joint_positions_si"]),
            base_fingerprint=payload["base_fingerprint"],
            robot_profile_fingerprint=payload["robot_profile_fingerprint"],
            runtime_validation_status=payload["runtime_validation_status"],
            to_dict=lambda: dict(payload),
        )
        _node.step6TaskHomeJson = json.dumps(payload, sort_keys=True)
        return home_store["record"]

    logic.taskHomeRecord = task_home_record
    logic.saveCurrentTaskHome = save_task_home
    return facade, parameter_node, logic, bridge, home_store


def _install_real_environment_snapshot(logic, parameter_node):
    environment = {
        "case_identity": "case-a",
        "anatomy_fingerprint": "anatomy-a",
        "source_volume_fingerprint": "volume-a",
        "source_segmentation_fingerprint": "segmentation-a",
        "jaw_source_fingerprint": "jaw-source-a",
        "jaw_landmarks_fingerprint": "landmarks-a",
        "robot_profile_fingerprint": "robot-a",
        "tool_identity": "tool-a",
        "tool_fingerprint": "tool-fingerprint-a",
        "base_matrix": tuple(float(index) for index in range(16)),
        "base_status": "RegisteredLocked",
        "base_locked": True,
        "base_fingerprint": "base-a",
        "base_authority": "reviewed",
        "base_revision": 1,
        "common_collision_fingerprint": "collision-a",
        "limits_fingerprint": "limits-a",
        "workspace_fingerprint": "workspace-a",
    }

    def build_snapshot(_node):
        raw_home = str(parameter_node.step6TaskHomeJson or "").strip()
        home = json.loads(raw_home) if raw_home else None
        return build_robot_environment_snapshot(
            **environment,
            task_home_configuration=home,
        )

    logic.buildCaseFoundationSnapshot = build_snapshot
    return environment, build_snapshot


def _real_task_home_writer():
    source = HELPERS / "dentobot_workflow" / "logic_robot.py"
    tree = ast.parse(source.read_text())
    logic_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RobotLogicMixin"
    )
    writer_node = next(
        node for node in logic_class.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "saveCurrentTaskHome"
    )
    namespace = {
        "build_task_home": build_task_home,
        "canonical_json": canonical_json,
        "joint_positions_si_from_display": lambda *_values: {},
        "parse_task_home": parse_task_home,
        "_": lambda message: message,
    }
    exec(
        compile(ast.Module(body=[writer_node], type_ignores=[]), str(source), "exec"),
        namespace,
    )
    return namespace["saveCurrentTaskHome"]


def test_offline_task_home_save_uses_reviewed_candidate_without_native_or_display_changes(
    monkeypatch,
):
    facade, parameter_node, logic, bridge, home_store = _offline_task_home_review_probe(
        monkeypatch
    )
    environment, build_snapshot = _install_real_environment_snapshot(
        logic, parameter_node
    )
    environment_fingerprint_before = build_snapshot(parameter_node).environment_fingerprint
    real_writer = _real_task_home_writer()

    def write_with_real_owner(node, *, runtime_validation, joint_positions_si):
        home_store["saveCalls"].append(
            (dict(runtime_validation), dict(joint_positions_si))
        )
        record = real_writer(
            logic,
            node,
            runtime_validation=runtime_validation,
            joint_positions_si=joint_positions_si,
        )
        home_store["record"] = record
        return record

    logic.saveCurrentTaskHome = write_with_real_owner
    logic.invalidateStep6TaskConfirmation = lambda _node, _message: None
    candidate = _manual_task_home_candidate()
    display_before = tuple(
        getattr(parameter_node, field)
        for field in (
            "robotJoint1Deg",
            "robotJoint2Mm",
            "robotJoint3Deg",
            "robotJoint4Mm",
            "robotJoint5Deg",
        )
    )
    bridge_before = dict(bridge.accepted)
    updates_before = list(logic.updated)

    staged = facade.stageManualTaskHomeReview(candidate)
    staged_identity = dict(facade._manual_task_home_review["identity"])
    saved = facade.acceptManualTaskHomeReview()
    environment_fingerprint_after = build_snapshot(parameter_node).environment_fingerprint
    identity_after = facade._manual_task_home_offline_identity(parameter_node)

    assert staged.success and staged.details["setupMode"] == "offline"
    assert saved.success and saved.code == "manual_task_home_configuration_saved"
    assert saved.details["acceptanceStatus"] == "configuration_saved"
    assert saved.details["runtimeValidated"] is False
    assert saved.details["acceptedJointPositionsSi"] is None
    assert saved.details["configuredJointPositionsSi"] == candidate
    assert saved.payload.revision == 1
    assert saved.payload.runtime_validation_status == "Unreviewed"
    assert dict(zip(saved.payload.joint_names, saved.payload.joint_positions_si)) == candidate
    assert home_store["record"] is saved.payload
    assert home_store["saveCalls"] == [
        ({"runtimeValidationStatus": "Unreviewed"}, candidate)
    ]
    assert environment_fingerprint_before != environment_fingerprint_after
    assert staged_identity["homeSnapshot"] != identity_after["homeSnapshot"]
    assert staged_identity["caseFoundationSnapshot"] == identity_after[
        "caseFoundationSnapshot"
    ]
    assert facade._manual_task_home_offline_non_home_identity(staged_identity) == (
        facade._manual_task_home_offline_non_home_identity(identity_after)
    )
    assert tuple(
        getattr(parameter_node, field)
        for field in (
            "robotJoint1Deg",
            "robotJoint2Mm",
            "robotJoint3Deg",
            "robotJoint4Mm",
            "robotJoint5Deg",
        )
    ) == display_before
    assert bridge.accepted == bridge_before
    assert bridge.applied == [] and bridge.phase_calls == []
    assert bridge.manual_requests == [] and bridge.query_requests == []
    assert logic.updated == updates_before


def test_offline_task_home_review_rejects_changed_real_environment_components(monkeypatch):
    for field in (
        "base_matrix",
        "anatomy_fingerprint",
        "limits_fingerprint",
        "workspace_fingerprint",
        "common_collision_fingerprint",
    ):
        facade, parameter_node, logic, _bridge, home_store = (
            _offline_task_home_review_probe(monkeypatch)
        )
        environment, build_snapshot = _install_real_environment_snapshot(
            logic, parameter_node
        )
        before_fingerprint = build_snapshot(parameter_node).environment_fingerprint
        candidate = _manual_task_home_candidate()
        staged = facade.stageManualTaskHomeReview(candidate)
        assert staged.success

        if field == "base_matrix":
            environment[field] = (environment[field][0] + 1.0,) + environment[field][1:]
        else:
            environment[field] += "-changed"
        assert build_snapshot(parameter_node).environment_fingerprint != before_fingerprint

        stale = facade.acceptManualTaskHomeReview()

        assert not stale.success and stale.code == "manual_task_home_review_stale"
        assert stale.details["identityStatus"] == "stale"
        assert home_store["saveCalls"] == []


def test_task_home_owner_writer_persists_explicit_candidate_as_unreviewed_schema_1_0():
    save_current_task_home = _real_task_home_writer()

    class LogicWriter:
        saveCurrentTaskHome = save_current_task_home

        def __init__(self):
            self.invalidated = []

        @staticmethod
        def step6BasePlacementFreshnessIssues(_node):
            return ()

        @staticmethod
        def taskHomeRecord(node):
            raw = str(node.step6TaskHomeJson or "").strip()
            return parse_task_home(raw) if raw else None

        @staticmethod
        def robotBaseFingerprint(_node):
            return "base-a"

        @staticmethod
        def robotProfileFingerprint():
            return "robot-a"

        def invalidateStep6TaskConfirmation(self, node, message):
            self.invalidated.append((node, message))

    node = FakeParameterNode()
    node.step6TaskHomeJson = ""
    node.robotJoint1Deg = 12.0
    node.robotJoint2Mm = 34.0
    node.robotJoint3Deg = -56.0
    node.robotJoint4Mm = 78.0
    node.robotJoint5Deg = -9.0
    display_before = (
        node.robotJoint1Deg,
        node.robotJoint2Mm,
        node.robotJoint3Deg,
        node.robotJoint4Mm,
        node.robotJoint5Deg,
    )
    candidate = _manual_task_home_candidate()
    logic = LogicWriter()

    returned = logic.saveCurrentTaskHome(
        node,
        runtime_validation={"runtimeValidationStatus": "Unreviewed"},
        joint_positions_si=candidate,
    )
    parsed = parse_task_home(node.step6TaskHomeJson)

    assert json.loads(node.step6TaskHomeJson)["schema_version"] == "1.0"
    assert parsed.schema_version == "1.0"
    assert parsed.runtime_validation_status == "Unreviewed"
    assert dict(zip(parsed.joint_names, parsed.joint_positions_si)) == candidate
    assert returned == parsed
    assert (
        node.robotJoint1Deg,
        node.robotJoint2Mm,
        node.robotJoint3Deg,
        node.robotJoint4Mm,
        node.robotJoint5Deg,
    ) == display_before
    assert logic.invalidated == [(node, "Task Home changed.")]


def test_offline_task_home_rejects_out_of_bounds_stale_and_changed_mode_candidates(
    monkeypatch,
):
    facade, _node, _logic, bridge, home_store = _offline_task_home_review_probe(
        monkeypatch
    )
    outside = _manual_task_home_candidate((1.0, 0.001, 0.02, 0.002, 0.03))
    rejected = facade.stageManualTaskHomeReview(outside)
    assert not rejected.success and rejected.code == "manual_task_home_review_rejected"
    assert "mechanical limits" in rejected.message
    assert home_store["saveCalls"] == []

    facade, _node, logic, _bridge, home_store = _offline_task_home_review_probe(
        monkeypatch
    )
    candidate = _manual_task_home_candidate()
    assert facade.stageManualTaskHomeReview(candidate).success
    logic.robotBaseFingerprint = lambda _node: "base-changed"
    stale = facade.acceptManualTaskHomeReview()
    assert not stale.success and stale.code == "manual_task_home_review_stale"
    assert stale.details["candidateJointPositionsSi"] == candidate
    assert home_store["saveCalls"] == []

    facade, parameter_node, _logic, _bridge, home_store = _offline_task_home_review_probe(
        monkeypatch
    )
    assert facade.stageManualTaskHomeReview(candidate).success
    parameter_node.robotBaseTransform.active = True
    changed_mode = facade.acceptManualTaskHomeReview()
    assert not changed_mode.success
    assert changed_mode.code == "manual_task_home_review_stale"
    assert changed_mode.details["candidateSetupMode"] == "offline"
    assert changed_mode.details["setupMode"] == "connected"
    assert home_store["saveCalls"] == []


def test_offline_task_home_latches_unknown_write_and_blocks_retry_or_cancel(
    monkeypatch,
):
    facade, _node, logic, bridge, home_store = _offline_task_home_review_probe(
        monkeypatch
    )
    candidate = _manual_task_home_candidate()
    save = logic.saveCurrentTaskHome

    def save_then_raise(*args, **kwargs):
        save(*args, **kwargs)
        raise RuntimeError("post-save reporting failed")

    logic.saveCurrentTaskHome = save_then_raise
    assert facade.stageManualTaskHomeReview(candidate).success
    result = facade.acceptManualTaskHomeReview()

    assert not result.success and result.code == "manual_task_home_acceptance_unknown"
    assert result.details["acceptanceStatus"] == "unknown"
    assert result.details["failureEvidence"]["ownerError"] == "post-save reporting failed"
    retry = facade.acceptManualTaskHomeReview()
    cancel = facade.cancelManualTaskHomeReview()
    assert retry.code == cancel.code == "manual_task_home_acceptance_unknown"
    assert retry.details["staged"] and cancel.details["staged"]
    assert retry.details["candidateJointPositionsSi"] == candidate
    assert home_store["saveCalls"] == [
        ({"runtimeValidationStatus": "Unreviewed"}, candidate)
    ]
    assert bridge.applied == [] and bridge.manual_requests == []


def test_offline_task_home_invalidation_failure_is_unknown_and_reentrancy_is_blocked(
    monkeypatch,
):
    facade, _node, _logic, _bridge, home_store = _offline_task_home_review_probe(
        monkeypatch
    )
    candidate = _manual_task_home_candidate()
    assert facade.stageManualTaskHomeReview(candidate).success
    facade.invalidateWorkspaceRuntimeValidation = lambda: (_ for _ in ()).throw(
        RuntimeError("workspace invalidation failed")
    )
    result = facade.acceptManualTaskHomeReview()
    assert not result.success and result.code == "manual_task_home_acceptance_unknown"
    assert result.details["failureEvidence"]["authorityInvalidationError"] == (
        "workspace invalidation failed"
    )
    assert facade.acceptManualTaskHomeReview().code == "manual_task_home_acceptance_unknown"
    assert facade.cancelManualTaskHomeReview().code == "manual_task_home_acceptance_unknown"
    assert home_store["saveCalls"]

    facade, _node, _logic, _bridge, home_store = _offline_task_home_review_probe(
        monkeypatch
    )
    candidate = _manual_task_home_candidate()
    assert facade.stageManualTaskHomeReview(candidate).success
    reentrant = []

    def invalidate_with_reentry():
        reentrant.extend(
            (
                facade.stageManualTaskHomeReview(_manual_task_home_candidate()),
                facade.acceptManualTaskHomeReview(),
                facade.cancelManualTaskHomeReview(),
            )
        )

    facade.invalidateWorkspaceRuntimeValidation = invalidate_with_reentry
    result = facade.acceptManualTaskHomeReview()
    assert result.success and result.code == "manual_task_home_configuration_saved"
    assert len(reentrant) == 3 and all(not action.success for action in reentrant)
    assert reentrant[1].code == reentrant[2].code == "manual_task_home_review_busy"
    assert facade._manual_task_home_review is None
    assert home_store["saveCalls"] == [
        ({"runtimeValidationStatus": "Unreviewed"}, candidate)
    ]


def test_connected_review_can_follow_offline_task_home_configuration(monkeypatch):
    facade, parameter_node, _logic, _bridge, home_store = _offline_task_home_review_probe(
        monkeypatch
    )
    candidate = _manual_task_home_candidate()
    assert facade.stageManualTaskHomeReview(candidate).success
    saved = facade.acceptManualTaskHomeReview()
    assert saved.success
    parameter_node.robotBaseTransform.active = True

    reviewed = facade.manualTaskHomeReview()

    assert reviewed.success and reviewed.details["setupMode"] == "connected"
    assert not reviewed.details["staged"]
    assert reviewed.details["acceptanceStatus"] == "review"
    assert reviewed.details["configuredJointPositionsSi"] == candidate
    assert reviewed.details["runtimeValidated"] is False
    assert len(home_store["saveCalls"]) == 1


def test_unreviewed_taskless_home_review_reads_and_stages_detached_current_candidate(
    monkeypatch,
):
    facade, parameter_node, logic, bridge = _unreviewed_taskless_home_review_probe(monkeypatch)
    candidate = _manual_task_home_candidate()
    accepted_before = bridge.last_accepted_joint_positions_si()
    monitored_before = bridge.monitored_joint_positions_si()
    applied_before = list(bridge.applied)
    home_json_before = parameter_node.step6TaskHomeJson

    current = facade.manualTaskHomeReview()
    staged = facade.stageManualTaskHomeReview(candidate)
    state = facade.manualTaskHomeReview()

    assert logic.confirmedTaskRecord(parameter_node) is None
    assert not logic.assistedTaskLimitsReviewed(parameter_node)
    assert current.success and current.details["identityStatus"] == "current"
    assert staged.success and staged.details["identityStatus"] == "current"
    assert staged.details["candidateJointPositionsSi"] == candidate
    assert staged.details["acceptedJointPositionsSi"] == accepted_before
    assert state.success and state.details["candidateJointPositionsSi"] == candidate
    assert bridge.last_accepted_joint_positions_si() == accepted_before
    assert bridge.monitored_joint_positions_si() == monitored_before
    assert bridge.accepted == accepted_before and bridge.applied == applied_before
    assert bridge.manual_requests == [] and bridge.phase_calls == []
    assert parameter_node.step6TaskHomeJson == home_json_before


def test_ordinary_manual_identity_still_requires_reviewed_limits_for_taskless_case(
    monkeypatch,
):
    facade, parameter_node, _logic, bridge = _unreviewed_taskless_home_review_probe(monkeypatch)
    accepted_before = bridge.last_accepted_joint_positions_si()
    monitored_before = bridge.monitored_joint_positions_si()

    try:
        facade._manual_jog_current_identity(parameter_node)
    except ValueError as exc:
        assert "Review the current assisted joint limits" in str(exc)
    else:
        raise AssertionError("unreviewed limits allowed ordinary manual identity")

    assert bridge.last_accepted_joint_positions_si() == accepted_before
    assert bridge.monitored_joint_positions_si() == monitored_before
    assert bridge.manual_requests == [] and bridge.phase_calls == []


def test_taskless_home_review_candidate_stales_when_limits_fingerprint_changes(
    monkeypatch,
):
    facade, parameter_node, logic, bridge = _unreviewed_taskless_home_review_probe(monkeypatch)
    candidate = _manual_task_home_candidate()
    accepted_before = bridge.last_accepted_joint_positions_si()
    monitored_before = bridge.monitored_joint_positions_si()
    assert facade.stageManualTaskHomeReview(candidate).success

    logic.step6TaskLimitsFingerprint = lambda _node: "limits-changed"
    stale = facade.manualTaskHomeReview()

    assert not stale.success and stale.details["identityStatus"] == "stale"
    assert stale.details["staged"]
    assert stale.details["candidateJointPositionsSi"] == candidate
    assert bridge.last_accepted_joint_positions_si() == accepted_before
    assert bridge.monitored_joint_positions_si() == monitored_before
    assert bridge.manual_requests == [] and bridge.phase_calls == []


def test_detached_task_home_review_stage_and_cancel_do_not_mutate_accepted_state(
    monkeypatch,
):
    facade, parameter_node, logic, bridge = _manual_task_home_review_probe(monkeypatch)
    candidate = _manual_task_home_candidate()
    accepted_before = dict(bridge.accepted)
    applied_before = list(bridge.applied)
    updated_before = list(logic.updated)
    home_json_before = parameter_node.step6TaskHomeJson

    staged = facade.stageManualTaskHomeReview(candidate)

    assert staged.success and staged.code == "manual_task_home_review_staged"
    assert staged.details["staged"]
    assert staged.details["candidateJointPositionsSi"] == candidate
    assert staged.details["acceptedJointPositionsSi"] == accepted_before
    assert staged.details["identityStatus"] == "current"
    assert staged.details["acceptanceStatus"] == "review"
    assert bridge.accepted == accepted_before and bridge.applied == applied_before
    assert bridge.manual_requests == [] and bridge.phase_calls == []
    assert logic.updated == updated_before and logic.synced == 0
    assert parameter_node.step6TaskHomeJson == home_json_before

    state = facade.manualTaskHomeReview()
    assert state.success and state.details["candidateJointPositionsSi"] == candidate
    cancelled = facade.cancelManualTaskHomeReview()
    assert cancelled.success and not cancelled.details["staged"]
    assert cancelled.details["candidateJointPositionsSi"] is None
    assert cancelled.details["acceptedJointPositionsSi"] == accepted_before
    assert bridge.accepted == accepted_before and bridge.applied == applied_before
    assert bridge.manual_requests == [] and bridge.phase_calls == []
    assert logic.updated == updated_before and logic.synced == 0
    assert parameter_node.step6TaskHomeJson == home_json_before


def test_detached_task_home_review_rejects_extra_joint_and_nonfinite_values(monkeypatch):
    facade, _node, _logic, bridge = _manual_task_home_review_probe(monkeypatch)
    candidate = _manual_task_home_candidate()
    results = (
        facade.stageManualTaskHomeReview({**candidate, "unexpected_joint": 0.0}),
        facade.stageManualTaskHomeReview(tuple(candidate.values()) + (0.0,)),
        facade.stageManualTaskHomeReview(
            {**candidate, ROS2_JOINT_SI_ORDER[0]: float("nan")}
        ),
    )

    assert all(not result.success for result in results)
    assert all(result.code == "manual_task_home_review_rejected" for result in results)
    assert all("J1–J5" in result.message for result in results)
    assert facade.manualTaskHomeReview().details["staged"] is False
    assert bridge.accepted == {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    assert bridge.applied == [] and bridge.manual_requests == []


def test_detached_task_home_review_retains_candidate_when_identity_goes_stale(
    monkeypatch,
):
    facade, _node, logic, bridge = _manual_task_home_review_probe(monkeypatch)
    candidate = _manual_task_home_candidate()
    assert facade.stageManualTaskHomeReview(candidate).success
    logic.step6TaskLimitsFingerprint = lambda _node: "limits-changed"
    facade.saveTaskHome = lambda: (_ for _ in ()).throw(
        AssertionError("stale candidate reached the Home owner")
    )

    state = facade.manualTaskHomeReview()
    result = facade.acceptManualTaskHomeReview()

    assert not state.success and state.details["identityStatus"] == "stale"
    assert not result.success and result.code == "manual_task_home_review_stale"
    assert result.details["identityStatus"] == "stale"
    assert result.details["candidateJointPositionsSi"] == candidate
    assert result.details["staged"]
    assert bridge.accepted == {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    assert bridge.applied == [] and bridge.manual_requests == []


def test_task_home_accept_rejects_candidate_different_from_accepted_pose(monkeypatch):
    facade, _node, _logic, bridge = _manual_task_home_review_probe(monkeypatch)
    candidate = _manual_task_home_candidate()
    assert facade.stageManualTaskHomeReview(candidate).success
    facade.saveTaskHome = lambda: (_ for _ in ()).throw(
        AssertionError("a noncurrent candidate reached the Home owner")
    )

    result = facade.acceptManualTaskHomeReview()

    assert not result.success and result.code == "manual_task_home_review_rejected"
    assert "separately guarded individual jog first" in result.message
    assert result.details["candidateJointPositionsSi"] == candidate
    assert result.details["acceptedJointPositionsSi"] == bridge.accepted
    assert result.details["acceptanceStatus"] == "rejected"
    assert bridge.applied == [] and bridge.manual_requests == []


def test_task_home_accept_blocks_unresolved_manual_jog(monkeypatch):
    facade, _node, _logic, bridge = _manual_task_home_review_probe(monkeypatch)
    candidate = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    assert facade.stageManualTaskHomeReview(candidate).success
    facade._manual_jog_reconciliation_required = True
    facade.saveTaskHome = lambda: (_ for _ in ()).throw(
        AssertionError("unresolved manual jog reached the Home owner")
    )

    result = facade.acceptManualTaskHomeReview()

    assert not result.success and result.details["acceptanceStatus"] == "rejected"
    assert result.details["staged"]
    assert result.details["candidateJointPositionsSi"] == candidate
    assert bridge.applied == [] and bridge.manual_requests == []


def test_task_home_accept_requires_monitored_and_displayed_pose_match(monkeypatch):
    for mismatch in ("monitored", "displayed"):
        facade, parameter_node, _logic, bridge = _manual_task_home_review_probe(monkeypatch)
        candidate = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
        assert facade.stageManualTaskHomeReview(candidate).success
        if mismatch == "monitored":
            bridge.monitored_joint_positions_si = lambda: {
                name: 0.1 if name == ROS2_JOINT_SI_ORDER[0] else 0.0
                for name in ROS2_JOINT_SI_ORDER
            }
        else:
            parameter_node.robotJoint1Deg = 1.0
        facade.saveTaskHome = lambda: (_ for _ in ()).throw(
            AssertionError("a nonmatching state reached the Home owner")
        )

        result = facade.acceptManualTaskHomeReview()

        assert not result.success and result.code == "manual_task_home_review_rejected"
        assert result.details["acceptanceStatus"] == "rejected"
        assert result.details["staged"] and result.details["candidateJointPositionsSi"] == candidate
        assert bridge.applied == [] and bridge.manual_requests == []


def test_task_home_review_clears_only_after_owner_acknowledges_save(monkeypatch):
    facade, _node, _logic, bridge = _manual_task_home_review_probe(monkeypatch)
    candidate = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    assert facade.stageManualTaskHomeReview(candidate).success
    owner_results = [
        RobotActionResult(False, "task_home_state_invalid", "validation unavailable"),
        RobotActionResult(True, "task_home_saved", "owner saved Home", details={"revision": 8}),
    ]
    calls = []

    def save_home():
        calls.append(True)
        return owner_results.pop(0)

    facade.saveTaskHome = save_home
    rejected = facade.acceptManualTaskHomeReview()
    assert not rejected.success and rejected.details["staged"]
    assert rejected.details["candidateJointPositionsSi"] == candidate
    assert rejected.details["acceptanceStatus"] == "rejected"
    assert rejected.details["failureEvidence"]["code"] == "task_home_state_invalid"

    accepted = facade.acceptManualTaskHomeReview()

    assert accepted.success and accepted.code == "manual_task_home_review_accepted"
    assert len(calls) == 2
    assert accepted.details["acceptanceStatus"] == "accepted"
    assert not accepted.details["staged"]
    assert accepted.details["candidateJointPositionsSi"] is None
    assert accepted.details["acceptedJointPositionsSi"] == candidate
    assert accepted.details["homeAcceptanceResult"]["code"] == "task_home_saved"
    assert bridge.applied == [] and bridge.manual_requests == []


def test_task_home_review_retains_candidate_on_owner_exception_without_commit(
    monkeypatch,
):
    facade, _node, _logic, bridge = _manual_task_home_review_probe(monkeypatch)
    candidate = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    assert facade.stageManualTaskHomeReview(candidate).success
    facade.saveTaskHome = lambda: (_ for _ in ()).throw(RuntimeError("precommit failure"))

    result = facade.acceptManualTaskHomeReview()

    assert not result.success and result.code == "manual_task_home_review_rejected"
    assert result.details["staged"]
    assert result.details["candidateJointPositionsSi"] == candidate
    assert result.details["acceptanceStatus"] == "rejected"
    assert result.details["failureEvidence"]["code"] == "task_home_failed"
    assert bridge.accepted == candidate and bridge.applied == []


def test_task_home_review_latches_uncertain_owner_commit(monkeypatch):
    facade, parameter_node, logic, bridge = _manual_task_home_review_probe(monkeypatch)
    logic.confirmedTaskRecord = lambda _node: None
    logic.assistedTaskLimitsReviewed = lambda _node: True
    candidate = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    assert facade.stageManualTaskHomeReview(candidate).success
    calls = []

    def save_home_then_raise():
        calls.append(True)
        parameter_node.step6TaskHomeJson = "new-home-record"
        raise RuntimeError("postcommit reporting failed")

    facade.saveTaskHome = save_home_then_raise
    result = facade.acceptManualTaskHomeReview()
    blocked_retry = facade.acceptManualTaskHomeReview()

    assert not result.success and result.code == "manual_task_home_acceptance_unknown"
    assert result.details["staged"]
    assert result.details["candidateJointPositionsSi"] == candidate
    assert result.details["acceptanceStatus"] == "unknown"
    assert result.details["acceptanceUncertainty"]
    assert not blocked_retry.success
    assert blocked_retry.code == "manual_task_home_acceptance_unknown"
    assert blocked_retry.details["staged"] and len(calls) == 1
    blocked_cancel = facade.cancelManualTaskHomeReview()
    assert not blocked_cancel.success
    assert blocked_cancel.code == "manual_task_home_acceptance_unknown"
    assert blocked_cancel.details["staged"]
    assert blocked_cancel.details["candidateJointPositionsSi"] == candidate
    assert blocked_cancel.details["acceptanceStatus"] == "unknown"
    assert blocked_cancel.details["failureEvidence"]["homeIdentityBefore"] != (
        blocked_cancel.details["failureEvidence"]["homeIdentityAfter"]
    )
    assert bridge.accepted == candidate and bridge.applied == []


def _uncertain_committed_task_home_review(monkeypatch):
    facade, parameter_node, logic, bridge = _manual_task_home_review_probe(monkeypatch)
    candidate = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    facade._strict_guard_policy_fingerprint = lambda: "guard-current"
    logic.confirmedTaskRecord = lambda _node: None
    logic.assistedTaskLimitsReviewed = lambda _node: True
    audit = SimpleNamespace(
        status="Acknowledged",
        audit_fingerprint="audit-current",
        runtime_acknowledgement={
            "status": "Acknowledged",
            "acknowledged_object_ids": ["jaw", "tooth"],
        },
    )
    logic.collisionSceneAuditRecord = lambda _node: audit
    previous_home = SimpleNamespace(revision=13, to_dict=lambda: {"revision": 13})
    parameter_node.step6TaskHomeJson = '{"revision":13}'
    logic.taskHomeRecord = lambda _node: previous_home
    home_payload = {
        "revision": 14,
        "joint_names": list(ROS2_JOINT_SI_ORDER),
        "joint_positions_si": [0.0] * len(ROS2_JOINT_SI_ORDER),
        "base_fingerprint": "base-a",
        "robot_profile_fingerprint": "robot-a",
        "runtime_validation_status": "Validated",
        "collision_audit_fingerprint": "audit-current",
        "guard_policy_fingerprint": "guard-current",
        "minimum_clearance_mm": 1.0,
        "world_object_count": 2,
    }
    current_home = SimpleNamespace(
        revision=14,
        joint_names=tuple(ROS2_JOINT_SI_ORDER),
        joint_positions_si=tuple(candidate[name] for name in ROS2_JOINT_SI_ORDER),
        base_fingerprint="base-a",
        robot_profile_fingerprint="robot-a",
        runtime_validation_status="Validated",
        collision_audit_fingerprint="audit-current",
        guard_policy_fingerprint="guard-current",
        minimum_clearance_mm=1.0,
        world_object_count=2,
        to_dict=lambda: dict(home_payload),
    )
    saves = []

    def save_home_then_raise():
        saves.append(True)
        parameter_node.step6TaskHomeJson = json.dumps(home_payload, sort_keys=True)
        logic.taskHomeRecord = lambda _node: current_home
        raise RuntimeError("post-save report failed")

    facade.saveTaskHome = save_home_then_raise
    assert facade.stageManualTaskHomeReview(candidate).success
    result = facade.acceptManualTaskHomeReview()
    assert not result.success
    assert result.code == "manual_task_home_acceptance_unknown"
    assert len(saves) == 1
    return facade, parameter_node, logic, bridge, candidate, current_home, saves


def test_home_reconciliation_accepts_exact_committed_native_state_without_second_save_or_motion(
    monkeypatch,
):
    facade, parameter_node, logic, bridge, candidate, current_home, saves = (
        _uncertain_committed_task_home_review(monkeypatch)
    )
    bridge.query_static_valid = True
    bridge.query_accepted = dict(candidate)
    freeze = facade._manual_task_home_review_failure["reconciliationFreeze"]
    assert freeze["homeBefore"]["revision"] == 13
    assert freeze["expectedRevision"] == 14
    assert freeze["candidateJointPositionsSi"] == candidate
    assert set(freeze["nonHomeIdentity"]) == {
        "branch_id", "base", "trajectory", "robot_profile", "collision_audit", "limits"
    }
    del facade.saveTaskHome
    native_query = bridge.query_manual_joint_state_si
    reentrant_results = []

    def query_while_locked(positions, request_id, session_id):
        reentrant_results.extend(
            (
                facade.saveTaskHome(),
                facade.guardManualRobotJog(candidate),
                facade.applyTaskHome(),
                facade.planApproachPhase(),
                facade.planDrillingPhase(),
                facade.previewPhase("approach"),
            )
        )
        return native_query(positions, request_id, session_id)

    bridge.query_manual_joint_state_si = query_while_locked
    applied_before = list(bridge.applied)
    requests_before = list(bridge.manual_requests)
    phases_before = list(bridge.phase_calls)
    updated_before = list(logic.updated)

    result = facade.reconcileManualTaskHomeAcceptance()

    request_id, session_id = bridge.query_requests[0][1:]
    assert result.success and result.code == "manual_task_home_reconciled"
    assert result.details["acceptanceStatus"] == "reconciled"
    assert not result.details["staged"]
    assert result.details["candidateJointPositionsSi"] is None
    assert result.details["acceptedJointPositionsSi"] == candidate
    assert result.details["homeRevision"] == 14
    assert result.details["nativeGuardEvidence"]["operation"] == "state_query"
    assert result.details["nativeGuardEvidence"]["queryOnly"] is True
    assert result.details["nativeGuardEvidence"]["staticStateValid"] is True
    assert result.details["nativeGuardEvidence"]["requestId"] == request_id
    assert result.details["nativeGuardEvidence"]["sessionId"] == session_id
    assert request_id and session_id and request_id != session_id
    assert bridge.query_commit_calls and len(bridge.query_commit_calls) == 1
    assert len(saves) == 1
    assert len(reentrant_results) == 6
    assert all(not action.success for action in reentrant_results)
    assert all(action.code == "manual_task_home_review_busy" for action in reentrant_results)
    assert bridge.applied == applied_before
    assert bridge.manual_requests == requests_before
    assert bridge.phase_calls == phases_before
    assert logic.updated == updated_before
    assert parameter_node.step6TaskHomeJson == json.dumps(
        current_home.to_dict(), sort_keys=True
    )
    assert facade._runtime_validated_task_home_key == facade._task_home_runtime_key(
        current_home
    )
    assert facade._runtime_task_home_evidence["jointPositionsSi"] == candidate


def test_task_home_reconciliation_keeps_unknown_when_saved_record_is_unchanged(
    monkeypatch,
):
    facade, parameter_node, logic, bridge, candidate, _home, _saves = (
        _uncertain_committed_task_home_review(monkeypatch)
    )
    original_record = SimpleNamespace(revision=13, to_dict=lambda: {"revision": 13})
    parameter_node.step6TaskHomeJson = '{"revision":13}'
    logic.taskHomeRecord = lambda _node: original_record
    uncertainty = facade._manual_task_home_acceptance_uncertain

    result = facade.reconcileManualTaskHomeAcceptance()

    assert not result.success and result.code == "manual_task_home_acceptance_unknown"
    assert result.details["acceptanceStatus"] == "unknown"
    assert result.details["candidateJointPositionsSi"] == candidate
    assert facade._manual_task_home_acceptance_uncertain == uncertainty
    assert bridge.query_requests == [] and bridge.query_commit_calls == []


def test_task_home_reconciliation_keeps_unknown_for_stale_identity_or_scene(
    monkeypatch,
):
    for stale in ("identity", "scene"):
        facade, _node, logic, bridge, candidate, _home, _saves = (
            _uncertain_committed_task_home_review(monkeypatch)
        )
        bridge.query_static_valid = True
        if stale == "identity":
            logic.step6TaskLimitsFingerprint = lambda _node: "limits-changed"
        else:
            bridge.query_object_ids = ["jaw"]

        result = facade.reconcileManualTaskHomeAcceptance()

        assert not result.success and result.code == "manual_task_home_acceptance_unknown"
        assert result.details["candidateJointPositionsSi"] == candidate
        assert facade._manual_task_home_acceptance_uncertain
        assert result.details["failureEvidence"]["reconciliationFailure"]
        assert bridge.query_commit_calls == []
        assert bool(bridge.query_requests) is (stale == "scene")


def test_task_home_reconciliation_keeps_unknown_for_native_or_monitored_mismatch(
    monkeypatch,
):
    for mismatch in ("native", "monitored", "displayed", "request", "session"):
        facade, parameter_node, _logic, bridge, candidate, _home, _saves = (
            _uncertain_committed_task_home_review(monkeypatch)
        )
        bridge.query_static_valid = True
        bridge.query_accepted = dict(candidate)
        if mismatch == "native":
            bridge.query_accepted = {
                **candidate,
                ROS2_JOINT_SI_ORDER[0]: 0.01,
            }
        elif mismatch == "monitored":
            bridge.query_monitor_matches = False
        elif mismatch == "displayed":
            parameter_node.robotJoint1Deg = 1.0
        elif mismatch == "request":
            bridge.query_response_id = "stale-request"
        else:
            bridge.query_session_id = "stale-session"

        result = facade.reconcileManualTaskHomeAcceptance()

        assert not result.success and result.code == "manual_task_home_acceptance_unknown"
        assert result.details["candidateJointPositionsSi"] == candidate
        assert facade._manual_task_home_acceptance_uncertain
        assert bridge.query_commit_calls == []


def test_manual_jog_reconciliation_reads_native_state_and_allows_static_failure(monkeypatch):
    facade, _node, _logic, bridge, request, *_rest = _manual_jog_probe(monkeypatch)
    bridge.raw_silent = True
    unknown = facade.guardManualRobotJog(request)
    assert not unknown.success
    assert unknown.details["manualJogReconciliationRequired"] is True
    accepted_before = dict(bridge.accepted)
    bridge.query_accepted = dict(request)
    motion_calls_before = (len(bridge.applied), len(bridge.phase_calls))

    result = facade.reconcileManualRobotJog()

    assert result.success
    assert result.code == "manual_jog_reconciled"
    assert result.details["manualJogReconciliationRequired"] is False
    assert result.details["acceptedJointPositionsSi"] == request
    assert result.details["collisionStatus"] == "invalid"
    assert result.details["nativeGuardEvidence"]["staticStateValid"] is False
    assert result.details["nativeGuardEvidence"]["operation"] == "state_query"
    assert result.details["nativeGuardEvidence"]["queryOnly"] is True
    assert bridge.query_requests[0][0] == request
    assert len(bridge.query_requests[0][0]) == 5  # Query uses the canonical joint vector.
    assert bridge.accepted == request and bridge.accepted != accepted_before
    assert len(bridge.manual_requests) == 1
    assert (len(bridge.applied), len(bridge.phase_calls)) == motion_calls_before
    assert not facade._manual_jog_reconciliation_required
    assert facade._manual_jog_uncertainty is None


def test_manual_jog_reconciliation_rejects_stale_id_scene_monitor_and_identity(monkeypatch):
    for mismatch in ("request", "scene", "malformed_scene", "monitor", "identity"):
        facade, _node, logic, bridge, request, *_rest = _manual_jog_probe(monkeypatch)
        bridge.raw_silent = True
        facade.guardManualRobotJog(request)
        bridge.query_accepted = dict(request)
        if mismatch == "request":
            bridge.query_response_id = "delayed-query"
        elif mismatch == "scene":
            bridge.query_object_ids = ["jaw", "other-tooth"]
        elif mismatch == "malformed_scene":
            query_manual = bridge.query_manual_joint_state_si

            def query_with_malformed_world_entry(echo, request_id, session_id):
                status, message = query_manual(echo, request_id, session_id)
                status = SimpleNamespace(
                    **status.__dict__,
                    world_objects=(*status.world_objects, {"id": ""}),
                )
                return status, message

            bridge.query_manual_joint_state_si = query_with_malformed_world_entry
        elif mismatch == "monitor":
            bridge.query_monitor_matches = False
        else:
            original_base_fingerprint = logic.robotBaseFingerprint
            original_query = bridge.query_manual_joint_state_si
            changed = {"value": False}

            def query_then_change(echo, request_id, session_id):
                response = original_query(echo, request_id, session_id)
                changed["value"] = True
                return response

            bridge.query_manual_joint_state_si = query_then_change
            logic.robotBaseFingerprint = lambda _node: (
                "base-b" if changed["value"] else original_base_fingerprint(_node)
            )
        accepted_before = dict(bridge.accepted)
        motion_calls_before = (len(bridge.applied), len(bridge.phase_calls))

        result = facade.reconcileManualRobotJog()

        assert not result.success, mismatch
        assert facade._manual_jog_reconciliation_required, mismatch
        assert bridge.accepted == accepted_before, mismatch
        assert bridge.query_commit_calls == [], mismatch
        assert len(bridge.manual_requests) == 1, mismatch
        assert (len(bridge.applied), len(bridge.phase_calls)) == motion_calls_before, mismatch


def test_manual_jog_accepts_only_exact_correlated_guard_ack_and_retains_rejection(
    monkeypatch,
):
    facade, _node, _logic, bridge, request, _limits, _task, _mechanical = (
        _manual_jog_probe(monkeypatch)
    )

    accepted = facade.guardManualRobotJog(request)

    assert accepted.success
    assert accepted.details["guardAccepted"] is True
    assert accepted.details["identityStatus"] == "current"
    assert accepted.details["acceptedJointPositionsSi"] == request
    assert accepted.details["manualJogReconciliationRequired"] is False
    assert set(accepted.details["acceptedJointPositionsSi"]) == set(ROS2_JOINT_SI_ORDER)
    assert accepted.details["nativeGuardEvidence"]["requestedPositionsSi"] == tuple(
        request[name] for name in ROS2_JOINT_SI_ORDER
    )
    assert accepted.details["limitMargins"][ROS2_JOINT_SI_ORDER[0]][
        "mechanical_within_limits"
    ]
    assert accepted.details["limitMargins"][ROS2_JOINT_SI_ORDER[0]][
        "reviewed_task_within_limits"
    ]
    assert accepted.details["routeAuthority"] == "none"
    assert accepted.details["nativeGuardEvidence"][
        "collisionScenePolicyIdentityStatus"
    ] == "manual_policy_id_correlated"
    assert accepted.details["nativeGuardEvidence"]["policyId"] == (
        workflow_facade_module.MANUAL_JOINT_POLICY_ID
    )
    request_id, session_id = bridge.manual_requests[0][1:]
    assert accepted.details["requestId"] == request_id
    assert accepted.details["sessionId"] == session_id == facade._manual_jog_session_id
    assert accepted.details["nativeGuardEvidence"]["requestId"] == request_id
    assert accepted.details["nativeGuardEvidence"]["sessionId"] == session_id
    assert accepted.details["nativeGuardEvidence"]["worldObjectIds"] == ("jaw", "tooth")
    assert accepted.details["nativeGuardEvidence"]["worldObjectCount"] == 2
    assert bridge.phase_calls == []
    facade.currentRobotState = lambda: SimpleNamespace(
        joint_positions_si=dict(bridge.accepted)
    )
    accepted_again = facade.guardManualRobotJog(request)
    assert accepted_again.success
    assert accepted_again.details["manualJogReconciliationRequired"] is False
    assert len(bridge.raw_requests) == 2
    first_request, second_request = bridge.manual_requests
    assert first_request[1] != second_request[1]
    assert first_request[2] == second_request[2] == facade._manual_jog_session_id
    assert not bridge.legacy_status_reads

    facade, _node, _logic, bridge, request, _limits, _task, _mechanical = (
        _manual_jog_probe(monkeypatch)
    )
    bridge.raw_reject = True
    rejected = facade.guardManualRobotJog(request)

    assert not rejected.success
    assert rejected.details["guardAccepted"] is False
    assert rejected.details["manualJogStatus"] == "rejected"
    assert rejected.details["rawGuardOutcome"] == "rejected"
    assert rejected.details["nativeGuardEvidence"]["reason"] == "self collision"
    assert rejected.details["requestedJointPositionsSi"] == request
    assert rejected.details["acceptedJointPositionsSi"] is None
    assert not rejected.details["acceptedStateMayHaveAdvanced"]
    assert rejected.details["manualJogReconciliationRequired"] is False
    rejected_request_id, rejected_session_id = bridge.manual_requests[0][1:]
    assert rejected.details["requestId"] == rejected_request_id
    assert rejected.details["sessionId"] == rejected_session_id
    assert rejected.details["nativeGuardEvidence"]["requestId"] == rejected_request_id
    assert rejected.details["nativeGuardEvidence"]["sessionId"] == rejected_session_id
    assert rejected.details["nativeGuardEvidence"]["policyId"] == (
        workflow_facade_module.MANUAL_JOINT_POLICY_ID
    )
    assert rejected.details["nativeGuardEvidence"]["worldObjectIds"] == (
        "jaw",
        "tooth",
    )
    bridge.raw_reject = False
    accepted_after_rejection = facade.guardManualRobotJog(request)
    assert accepted_after_rejection.success
    assert accepted_after_rejection.details["manualJogReconciliationRequired"] is False
    assert len(bridge.raw_requests) == 2


def test_taskless_manual_jog_uses_unconfirmed_identity_and_exact_guard_ack(
    monkeypatch,
):
    stale_home = {"base_fingerprint": "base-old", "joint_positions_si": [0.0] * 5}
    for payload in (stale_home, None):
        facade, parameter_node, logic, bridge, request, *_rest = _manual_jog_probe(
            monkeypatch
        )
        logic.confirmedTaskRecord = lambda _node: None
        logic.assistedTaskLimitsReviewed = lambda _node: True
        _set_manual_test_home(parameter_node, logic, payload)

        result = facade.guardManualRobotJog(request)

        identity = result.details["identityBefore"]
        evidence = result.details["nativeGuardEvidence"]
        request_id, session_id = bridge.manual_requests[0][1:]
        assert result.success and result.code == "manual_jog_accepted"
        assert identity["branch_id"] == "branch-a"
        assert identity["task"].startswith("unconfirmed:")
        assert identity["base"] == "base-a"
        assert identity["home"].startswith("unconfirmed_home:")
        assert identity["trajectory"] == "trajectory-a"
        assert identity["robot_profile"] == "robot-a"
        assert identity["collision_audit"] == "scene-a"
        assert identity["limits"] == "limits-a"
        assert result.details["identityStatus"] == "current"
        assert result.details["identityAfter"] == identity
        assert result.details["requestId"] == evidence["requestId"] == request_id
        assert result.details["sessionId"] == evidence["sessionId"] == session_id
        assert session_id == facade._manual_jog_session_id
        assert evidence["policyId"] == workflow_facade_module.MANUAL_JOINT_POLICY_ID
        assert evidence["worldObjectIds"] == ("jaw", "tooth")
        assert evidence["responseCorrelated"] is True
        assert evidence["requestedPositionsSi"] == tuple(
            request[name] for name in ROS2_JOINT_SI_ORDER
        )
        assert evidence["acceptedPositionsSi"] == tuple(
            request[name] for name in ROS2_JOINT_SI_ORDER
        )
        assert result.details["guardAccepted"] is True
        assert result.details["requestedJointPositionsSi"] == request
        assert result.details["acceptedJointPositionsSi"] == request
        assert bridge.phase_calls == []
        assert logic.updated == []


def test_taskless_manual_jog_becomes_unknown_when_home_is_edited_during_ack(
    monkeypatch,
):
    facade, parameter_node, logic, bridge, request, *_rest = _manual_jog_probe(
        monkeypatch
    )
    logic.confirmedTaskRecord = lambda _node: None
    logic.assistedTaskLimitsReviewed = lambda _node: True
    _set_manual_test_home(
        parameter_node,
        logic,
        {"base_fingerprint": "base-old", "revision": 1},
    )
    original_apply = bridge.apply_manual_joint_positions_si

    def apply_then_edit_home(positions, request_id, session_id):
        response = original_apply(positions, request_id, session_id)
        _set_manual_test_home(
            parameter_node,
            logic,
            {"base_fingerprint": "base-old", "revision": 2},
        )
        return response

    bridge.apply_manual_joint_positions_si = apply_then_edit_home

    result = facade.guardManualRobotJog(request)

    evidence = result.details["nativeGuardEvidence"]
    request_id, session_id = bridge.manual_requests[0][1:]
    assert not result.success and result.code == "manual_jog_identity_stale"
    assert result.details["identityBefore"]["home"].startswith("unconfirmed_home:")
    assert result.details["identityAfter"]["home"].startswith("unconfirmed_home:")
    assert result.details["identityBefore"]["home"] != result.details["identityAfter"]["home"]
    assert result.details["guardAccepted"] is None
    assert result.details["manualJogStatus"] == "unknown"
    assert result.details["identityStatus"] == "stale"
    assert evidence["responseCorrelated"] is True
    assert result.details["requestId"] == evidence["requestId"] == request_id
    assert result.details["sessionId"] == evidence["sessionId"] == session_id
    assert evidence["policyId"] == workflow_facade_module.MANUAL_JOINT_POLICY_ID
    assert evidence["worldObjectIds"] == ("jaw", "tooth")
    assert result.details["manualJogReconciliationRequired"] is True
    assert result.details["acceptedStateMayHaveAdvanced"] is True
    assert bridge.accepted == request


def test_manual_jog_preserves_unknown_and_stale_guard_evidence(monkeypatch):
    facade, _node, _logic, bridge, request, _limits, _task, _mechanical = (
        _manual_jog_probe(monkeypatch)
    )
    accepted_before = dict(bridge.accepted)
    bridge.raw_silent = True

    unknown = facade.guardManualRobotJog(request)

    assert not unknown.success
    assert unknown.details["guardAccepted"] is None
    assert unknown.details["manualJogStatus"] == "unknown"
    assert unknown.details["nativeGuardEvidence"]["responseCorrelated"] is False
    assert unknown.details["acceptedStateMayHaveAdvanced"] is True
    assert unknown.details["requestedJointPositionsSi"] == request
    assert unknown.details["acceptedJointPositionsSi"] is None
    assert unknown.details["manualJogReconciliationRequired"] is True
    request_id, session_id = bridge.manual_requests[0][1:]
    assert unknown.details["requestId"] == request_id
    assert unknown.details["sessionId"] == session_id
    assert unknown.details["nativeGuardEvidence"]["responseObserved"] is False
    assert unknown.details["nativeGuardEvidence"]["worldObjectIds"] == ()
    assert bridge.accepted == accepted_before

    submitted_count = len(bridge.raw_requests)
    blocked = facade.guardManualRobotJog(request)
    assert not blocked.success
    assert blocked.code == "manual_jog_reconciliation_required"
    assert blocked.details["manualJogReconciliationRequired"] is True
    assert len(bridge.raw_requests) == submitted_count
    assert bridge.accepted == accepted_before

    facade, _node, _logic, bridge, request, _limits, _task, _mechanical = (
        _manual_jog_probe(monkeypatch)
    )
    original_identity = facade.plannerComparisonIdentity
    identity_reads = 0

    def stale_identity():
        nonlocal identity_reads
        identity_reads += 1
        identity = original_identity()
        return identity if identity_reads == 1 else {**identity, "task": "task-b"}

    facade.plannerComparisonIdentity = stale_identity
    stale = facade.guardManualRobotJog(request)

    assert not stale.success
    assert stale.details["guardAccepted"] is None
    assert stale.details["identityStatus"] == "stale"
    assert stale.details["nativeGuardEvidence"]["accepted"] is True
    assert stale.details["acceptedStateMayHaveAdvanced"]
    assert stale.details["acceptedJointPositionsSi"] is None
    assert stale.details["manualJogReconciliationRequired"] is True

    accepted_after_stale = dict(bridge.accepted)
    submitted_count = len(bridge.raw_requests)
    blocked = facade.guardManualRobotJog(request)
    assert not blocked.success
    assert blocked.code == "manual_jog_reconciliation_required"
    assert blocked.details["manualJogReconciliationRequired"] is True
    assert len(bridge.raw_requests) == submitted_count
    assert bridge.accepted == accepted_after_stale


def test_manual_jog_latches_when_submitted_guard_call_raises(monkeypatch):
    facade, _node, _logic, bridge, request, *_rest = _manual_jog_probe(monkeypatch)
    accepted_before = dict(bridge.accepted)
    attempted = []

    def raise_after_submission(positions, request_id, session_id):
        attempted.append((dict(positions), request_id, session_id))
        raise RuntimeError("guard response lost")

    bridge.apply_manual_joint_positions_si = raise_after_submission

    result = facade.guardManualRobotJog(request)

    assert not result.success
    assert result.code == "manual_jog_guard_unknown"
    assert result.details["manualJogReconciliationRequired"] is True
    assert attempted[0][0] == request
    assert attempted[0][1] == result.details["requestId"]
    assert attempted[0][2] == facade._manual_jog_session_id
    assert bridge.accepted == accepted_before

    blocked = facade.guardManualRobotJog(request)
    assert blocked.code == "manual_jog_reconciliation_required"
    assert len(attempted) == 1
    assert bridge.accepted == accepted_before


def test_manual_jog_latches_when_post_submit_state_read_raises(monkeypatch):
    facade, _node, _logic, bridge, request, *_rest = _manual_jog_probe(monkeypatch)
    accepted_reads = 0
    original_accepted_reader = bridge.last_accepted_joint_positions_si

    def unexpected_post_submit_failure():
        nonlocal accepted_reads
        accepted_reads += 1
        if accepted_reads == 1:
            return original_accepted_reader()
        raise AssertionError("unexpected accepted-state reader failure")

    bridge.last_accepted_joint_positions_si = unexpected_post_submit_failure

    result = facade.guardManualRobotJog(request)

    assert not result.success
    assert result.code == "manual_jog_unknown"
    assert result.details["manualJogReconciliationRequired"] is True
    assert len(bridge.raw_requests) == 1
    accepted_after_failure = dict(bridge.accepted)
    blocked = facade.guardManualRobotJog(request)
    assert blocked.code == "manual_jog_reconciliation_required"
    assert len(bridge.raw_requests) == 1
    assert bridge.accepted == accepted_after_failure


def test_manual_jog_rejects_extra_joint_and_blocks_out_of_limits(monkeypatch):
    facade, _node, logic, bridge, request, limits, task, mechanical = (
        _manual_jog_probe(monkeypatch)
    )
    with_extra_joint = {**request, "unexpected_joint": 0.0}

    rejected_extra = facade.guardManualRobotJog(with_extra_joint)
    assert rejected_extra.details["rawGuardOutcome"] == "not_submitted"
    assert rejected_extra.details["manualJogStatus"] == "rejected"
    assert rejected_extra.details["manualJogReconciliationRequired"] is False
    assert bridge.raw_requests == []

    narrowed = limits(-1.0, 1.0)
    task.joint_1 = narrowed.joint_1
    reviewed_limit = facade.guardManualRobotJog(
        {**request, ROS2_JOINT_SI_ORDER[0]: 0.1}
    )
    assert reviewed_limit.details["manualJogStatus"] == "rejected"
    assert reviewed_limit.details["manualJogReconciliationRequired"] is False
    assert not reviewed_limit.details["limitMargins"][ROS2_JOINT_SI_ORDER[0]][
        "reviewed_task_within_limits"
    ]
    assert reviewed_limit.details["limitMargins"][ROS2_JOINT_SI_ORDER[0]][
        "mechanical_within_limits"
    ]

    broader = limits(-40.0, 40.0)
    task.joint_1 = broader.joint_1
    narrowed_mechanical = limits(-30.0, 30.0)
    mechanical.joint_1 = narrowed_mechanical.joint_1
    mechanical_limit = facade.guardManualRobotJog(
        {**request, ROS2_JOINT_SI_ORDER[0]: 0.6}
    )
    assert mechanical_limit.details["manualJogStatus"] == "rejected"
    assert mechanical_limit.details["manualJogReconciliationRequired"] is False
    assert not mechanical_limit.details["limitMargins"][ROS2_JOINT_SI_ORDER[0]][
        "mechanical_within_limits"
    ]

    nested = []
    apply_raw = bridge.apply_manual_joint_positions_si

    def reentrant_apply(positions, request_id, session_id):
        nested.append(facade.guardManualRobotJog(request))
        return apply_raw(positions, request_id, session_id)

    bridge.apply_manual_joint_positions_si = reentrant_apply
    outer = facade.guardManualRobotJog(request)
    assert outer.success
    assert len(nested) == 1
    assert nested[0].details["manualJogStatus"] == "unknown"
    assert nested[0].details["rawGuardOutcome"] == "not_submitted"
    assert len(bridge.raw_requests) == 1


def test_manual_jog_uses_raw_manual_policy_id_not_phase_fingerprint(monkeypatch):
    facade, _node, _logic, bridge, request, _limits, _task, _mechanical = (
        _manual_jog_probe(monkeypatch)
    )

    result = facade.guardManualRobotJog(request)

    assert result.success
    assert result.details["nativeGuardEvidence"][
        "collisionScenePolicyIdentityStatus"
    ] == "manual_policy_id_correlated"
    assert result.details["nativeGuardEvidence"][
        "collisionScenePolicyFingerprint"
    ] == bridge.raw_policy_fingerprint
    assert result.details["nativeGuardEvidence"]["policyId"] == (
        workflow_facade_module.MANUAL_JOINT_POLICY_ID
    )

    facade, _node, _logic, bridge, request, *_rest = _manual_jog_probe(monkeypatch)
    bridge.manual_policy_id = "task_phase_policy_fingerprint"
    mismatched = facade.guardManualRobotJog(request)
    assert not mismatched.success
    assert mismatched.details["guardAccepted"] is None
    assert mismatched.details["manualJogStatus"] == "unknown"
    assert mismatched.details["nativeGuardEvidence"]["responseCorrelated"] is False
    assert mismatched.details["manualJogReconciliationRequired"] is True


def test_manual_jog_latches_same_vector_reply_from_wrong_session(monkeypatch):
    facade, _node, _logic, bridge, request, *_rest = _manual_jog_probe(monkeypatch)
    bridge.response_session_id = "older-facade-session"

    result = facade.guardManualRobotJog(request)

    assert not result.success
    assert result.details["nativeGuardEvidence"]["requestedPositionsSi"] == tuple(
        request[name] for name in ROS2_JOINT_SI_ORDER
    )
    assert result.details["nativeGuardEvidence"]["responseCorrelated"] is False
    assert result.details["acceptedStateMayHaveAdvanced"] is True
    assert result.details["manualJogReconciliationRequired"] is True


def test_manual_simulation_record_captures_exact_accepted_rejected_and_unknown_jogs(
    monkeypatch,
):
    facade, _node, _logic, bridge, request, *_rest = _manual_jog_probe(monkeypatch)

    def compute_fk(positions, *, base_transform):
        assert base_transform is _node.robotBaseTransform
        point_x = float(positions[ROS2_JOINT_SI_ORDER[0]]) * 1000.0
        return True, "test FK", (
            (1.0, 0.0, 0.0, point_x),
            (0.0, 1.0, 0.0, 20.0),
            (0.0, 0.0, 2.0, 30.0),
            (0.0, 0.0, 0.0, 1.0),
        )

    bridge.compute_tcp_pose_world_ras_mm = compute_fk
    accepted = facade.guardManualRobotJog(request)
    accepted_record = parse_manual_simulation_record(facade.manualSimulationRecord())
    assert [event["kind"] for event in accepted_record["events"]] == [
        "requested",
        "guard_accepted",
    ]
    assert accepted_record["record_status"] == "historical_display_only"
    assert accepted_record["events"][0]["requested_joints"] == request
    assert accepted_record["events"][1]["accepted_joints"] == request
    accepted_event = accepted_record["events"][1]
    assert accepted_event["monitored_joints"] == request
    assert accepted_event["tcp_point_ras_mm"] == [10.0, 20.0, 30.0]
    assert accepted_event["tcp_pose_world_ras_mm"] == [
        1.0, 0.0, 0.0, 10.0,
        0.0, 1.0, 0.0, 20.0,
        0.0, 0.0, 2.0, 30.0,
        0.0, 0.0, 0.0, 1.0,
    ]
    assert accepted_event["drill_axis_world_ras_unit"] == [0.0, 0.0, 1.0]
    assert accepted_event["details"]["geometry_status"] == "accepted"
    assert accepted_event["details"]["configured_clearance_threshold_m"] == 0.001
    assert accepted_event["details"]["measured_minimum_self_distance_m"] == 0.002
    assert accepted_event["details"]["measured_minimum_world_distance_m"] == 0.003
    native = accepted_event["details"]["native_guard_evidence"]
    assert native["requestId"] == bridge.manual_requests[0][1]
    assert native["sessionId"] == facade._manual_jog_session_id
    assert native["policyId"] == workflow_facade_module.MANUAL_JOINT_POLICY_ID
    assert accepted_event["details"]["identity_before"] == accepted.details["identityBefore"]
    assert accepted_event["details"]["identity_after"] == accepted.details["identityAfter"]
    assert accepted_record["events"][1]["details"]["guard_policy_id"] == (
        workflow_facade_module.MANUAL_JOINT_POLICY_ID
    )
    assert accepted_record["events"][1]["details"]["guard_policy_fingerprint"] == "unknown"
    assert accepted_record["events"][1]["details"]["guard_request_id"] == (
        bridge.manual_requests[0][1]
    )
    assert accepted_record["events"][1]["details"]["guard_session_id"] == (
        facade._manual_jog_session_id
    )
    assert set(accepted_record["events"][1]["accepted_joints"]) == set(
        ROS2_JOINT_SI_ORDER
    )
    assert set(accepted_record["identity"]) == {
        "prepared_branch_id",
        "task_fingerprint",
        "base_fingerprint",
        "home_fingerprint",
        "trajectory_fingerprint",
        "robot_profile_fingerprint",
        "scene_fingerprint",
    }
    assert accepted.details["routeAuthority"] == "none"

    facade, _node, _logic, bridge, request, *_rest = _manual_jog_probe(monkeypatch)
    bridge.compute_tcp_pose_world_ras_mm = lambda positions, *, base_transform: (
        True,
        "test FK",
        (
            (1.0, 0.0, 0.0, float(positions[ROS2_JOINT_SI_ORDER[0]]) * 1000.0),
            (0.0, 1.0, 0.0, 20.0),
            (0.0, 0.0, 2.0, 30.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
    )
    bridge.raw_reject = True
    rejected = facade.guardManualRobotJog(request)
    rejected_record = parse_manual_simulation_record(facade.manualSimulationRecord())
    rejected_event = rejected_record["events"][1]
    assert [event["kind"] for event in rejected_record["events"]] == [
        "requested",
        "guard_rejected",
    ]
    assert rejected_event["accepted_joints"] == {
        name: 0.0 for name in ROS2_JOINT_SI_ORDER
    }
    assert rejected_event["details"]["geometry_status"] == "rejected_candidate"
    assert rejected_event["tcp_point_ras_mm"] == [10.0, 20.0, 30.0]
    assert rejected_event["drill_axis_world_ras_unit"] == [0.0, 0.0, 1.0]
    assert "tcp_path_ras_mm" not in rejected_event
    assert bridge.accepted == {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    assert rejected_event["details"]["native_guard_evidence"]["accepted"] is False
    assert rejected_event["native_failure_evidence"]["native"]["reason"] == "self collision"
    assert rejected.details["guardAccepted"] is False

    facade, _node, _logic, bridge, request, *_rest = _manual_jog_probe(monkeypatch)
    bridge.raw_silent = True
    unknown = facade.guardManualRobotJog(request)
    unknown_record = parse_manual_simulation_record(facade.manualSimulationRecord())
    assert [event["kind"] for event in unknown_record["events"]] == [
        "requested",
        "diagnostic",
    ]
    assert unknown_record["events"][1]["diagnostic"]["guard_accepted"] is None
    assert unknown_record["events"][1]["details"]["geometry_status"] == "unavailable"
    assert "tcp_pose_world_ras_mm" not in unknown_record["events"][1]
    assert unknown_record["events"][1]["details"]["native_guard_evidence"]["responseObserved"] is False
    assert unknown.details["acceptedJointPositionsSi"] is None


def test_manual_simulation_record_missing_fk_does_not_change_accepted_jog(monkeypatch):
    facade, _node, _logic, _bridge, request, *_rest = _manual_jog_probe(monkeypatch)

    result = facade.guardManualRobotJog(request)

    record = parse_manual_simulation_record(facade.manualSimulationRecord())
    assert result.success and result.code == "manual_jog_accepted"
    event = record["events"][1]
    assert [item["kind"] for item in record["events"]] == ["requested", "guard_accepted"]
    assert event["details"]["geometry_status"] == "unavailable"
    assert "FK helper is unavailable" in event["details"]["geometry_unavailable_reason"]
    assert "tcp_pose_world_ras_mm" not in event
    assert event["accepted_joints"] == request


def test_manual_simulation_base_acceptance_freezes_the_exportable_record():
    facade, _node, _logic, _bridge = make_facade()
    joints = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    identity = {
        "prepared_branch_id": "branch-a",
        "task_fingerprint": "task-a",
        "base_fingerprint": "base-a",
        "home_fingerprint": "home-a",
        "trajectory_fingerprint": "trajectory-a",
        "robot_profile_fingerprint": "robot-a",
        "scene_fingerprint": "scene-a",
    }
    facade._manual_simulation_identity = identity
    facade._manual_simulation_events = [
        {
            "kind": "requested",
            "monotonic_ns": 1,
            "requested_joints": joints,
        }
    ]
    matrix = [1.0 if index in (0, 5, 10, 15) else 0.0 for index in range(16)]
    result = facade._manual_simulation_finish_acceptance(
        RobotActionResult(True, "base_locked", "locked"),
        review_event={
            "kind": "review_base",
            "monotonic_ns": 2,
            "details": {"candidate_matrix_world_ras_mm": matrix},
        },
        acceptance_event={
            "kind": "accept_base",
            "monotonic_ns": 3,
            "details": {
                "accepted_fingerprint": "base-b",
                "accepted_matrix_world_ras_mm": matrix,
            },
        },
        unavailable_reason="identity unavailable",
    )
    record = parse_manual_simulation_record(result.details["manualSimulationRecord"])
    assert result.details["manualSimulationRecordStatus"] == "available"
    assert [event["kind"] for event in record["events"]] == [
        "requested",
        "review_base",
        "accept_base",
    ]
    assert facade.manualSimulationCompletedRecords() == (record,)
    next_identity = {
        "branch_id": "branch-b",
        "task": "task-b",
        "base": "base-b",
        "home": "home-b",
        "trajectory": "trajectory-b",
        "robot_profile": "robot-b",
        "collision_audit": "scene-b",
        "limits": "limits-b",
    }
    facade._manual_jog_current_identity = lambda _expected=None: next_identity
    assert facade.manualSimulationRecord() == record
    assert facade._manual_simulation_identity["task_fingerprint"] == "task-b"
    assert facade._manual_simulation_events == []


def test_manual_simulation_identity_change_preserves_nonempty_prior_ledger():
    facade, _node, _logic, _bridge = make_facade()
    joints = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    identity = {
        "branch_id": "branch-a",
        "task": "task-a",
        "base": "base-a",
        "home": "home-a",
        "trajectory": "trajectory-a",
        "robot_profile": "robot-a",
        "collision_audit": "scene-a",
        "limits": "limits-a",
    }
    facade._manual_simulation_begin(identity)
    facade._manual_simulation_append_event(
        {"kind": "requested", "monotonic_ns": 1, "requested_joints": joints}
    )
    facade._manual_simulation_begin(
        {**identity, "branch_id": "branch-b", "task": "task-b"}
    )
    completed = facade.manualSimulationCompletedRecords()
    assert len(completed) == 1
    assert completed[0]["identity"]["task_fingerprint"] == "task-a"
    assert completed[0]["events"][0]["kind"] == "requested"
    assert facade._manual_simulation_identity["task_fingerprint"] == "task-b"
    assert facade._manual_simulation_events == []


def _seed_prior_manual_simulation_ledger(facade):
    identity = {
        "prepared_branch_id": "branch-a",
        "task_fingerprint": "task-a",
        "base_fingerprint": "base-a",
        "home_fingerprint": "home-a",
        "trajectory_fingerprint": "trajectory-a",
        "robot_profile_fingerprint": "robot-a",
        "scene_fingerprint": "scene-a",
    }
    event = {
        "kind": "requested",
        "monotonic_ns": 1,
        "requested_joints": {name: 0.0 for name in ROS2_JOINT_SI_ORDER},
    }
    facade._manual_simulation_identity = identity
    facade._manual_simulation_events = [event]
    return event


def _manual_identity_unavailable():
    raise ValueError("current case identity unavailable")


def test_manual_base_acceptance_does_not_append_to_old_ledger_on_identity_failure():
    facade, parameter_node, logic, _bridge = make_facade()
    candidate = _manual_base_test_matrix(18.0)
    assert facade.stageManualBaseReview(candidate).success
    prior_event = _seed_prior_manual_simulation_ledger(facade)
    logic.robotBaseFingerprint = lambda _node: "base-current"
    facade._manual_jog_current_identity = _manual_identity_unavailable

    result = facade.acceptManualBaseReview()

    assert result.success and result.code == "base_locked"
    assert result.details["manualSimulationRecordStatus"] == "unavailable"
    assert parameter_node.robotBaseMountLocked
    assert facade._manual_simulation_base_matrix(parameter_node) == candidate
    completed = facade.manualSimulationCompletedRecords()
    assert len(completed) == 1
    assert completed[0]["identity"]["task_fingerprint"] == "task-a"
    assert completed[0]["events"] == [prior_event]


def test_manual_simulation_task_home_save_keeps_old_ledger_on_identity_failure():
    facade, parameter_node, logic, _bridge = make_facade()
    parameter_node.robotBaseTransform.active = True
    facade._planning_scene_synchronized = True
    prior_event = _seed_prior_manual_simulation_ledger(facade)
    facade._manual_jog_current_identity = _manual_identity_unavailable
    facade._apply_positions_si = lambda _positions: RobotActionResult(
        True, "manual_jog_accepted", "accepted"
    )
    facade._checkStateValidity = lambda: RobotActionResult(
        True,
        "state_valid",
        "valid",
        details={"authoritative": True, "minimumClearanceMm": 1.0, "worldObjectCount": 2},
    )
    facade._strict_guard_policy_fingerprint = lambda: "guard-a"
    logic.collisionSceneAuditRecord = lambda _node: SimpleNamespace(
        audit_fingerprint="scene-current"
    )
    saved = []
    home_record = SimpleNamespace(
        revision=14,
        guard_policy_fingerprint="guard-a",
        to_dict=lambda: {"revision": 14},
    )

    def save_home(_node, *, runtime_validation):
        saved.append(runtime_validation)
        parameter_node.step6TaskHomeJson = '{"revision":14}'
        return home_record

    logic.saveCurrentTaskHome = save_home

    result = facade.saveTaskHome()

    assert result.success and result.code == "task_home_saved"
    assert result.details["manualSimulationRecordStatus"] == "unavailable"
    assert saved and parameter_node.step6TaskHomeJson == '{"revision":14}'
    completed = facade.manualSimulationCompletedRecords()
    assert len(completed) == 1
    assert completed[0]["identity"]["task_fingerprint"] == "task-a"
    assert completed[0]["events"] == [prior_event]


def test_manual_base_diagnostic_is_not_appended_when_current_identity_fails():
    facade, _node, _logic, _bridge = make_facade()
    prior_event = _seed_prior_manual_simulation_ledger(facade)
    facade._manual_jog_current_identity = _manual_identity_unavailable

    facade._manual_base_record_acceptance_failure(
        "manual_base_acceptance_failed", "not accepted", "lock", "proven"
    )

    completed = facade.manualSimulationCompletedRecords()
    assert len(completed) == 1
    assert completed[0]["identity"]["task_fingerprint"] == "task-a"
    assert completed[0]["events"] == [prior_event]


def test_manual_simulation_record_reports_missing_identity():
    facade, _node, _logic, _bridge = make_facade()
    try:
        facade.manualSimulationRecord()
    except RuntimeError as exc:
        assert "recording is unavailable" in str(exc)
    else:
        raise AssertionError("record export must be unavailable without a complete identity")


def test_workspace_generation_rejects_reentrant_submission():
    facade, _parameter, _logic, _bridge = make_facade()
    facade._workspace_generation_active = True
    result = facade.generateWorkspaceCloud()
    assert not result.success and result.code == "workspace_busy"


def test_workspace_motion_identity_fails_closed_when_unavailable():
    facade, _parameter, _logic, bridge = make_facade()
    bridge.get_motion_control_logic = lambda: None
    try:
        facade._motionControlNodeIdentity()
    except ValueError as error:
        assert "identity is unavailable" in str(error)
    else:
        raise AssertionError("missing motion-control identity must fail closed")


def test_manual_base_verification_failure_names_failed_checks():
    facade, parameter_node, logic, _bridge = make_facade()
    candidate = _manual_base_test_matrix(12.9)
    assert facade.stageManualBaseReview(candidate).success

    def lock_without_reviewed_authority(node, locked):
        node.robotBaseMountLocked = bool(locked)  # authority intentionally left unreviewed

    logic.setRobotBaseMountLocked = lock_without_reviewed_authority
    result = facade.acceptManualBaseReview()

    assert not result.success and result.code == "manual_base_acceptance_unknown"
    assert "failed checks: authority_mismatch" in result.message
    evidence = facade.manualBaseReview().details["failureEvidence"]["verificationEvidence"]
    assert evidence["failedChecks"] == ["authority_mismatch"]
    assert evidence["baseLocked"] is True
    assert evidence["maxMatrixDelta"] <= 1.0e-9
    assert evidence["baseNodeReplaced"] is False


def test_straight_joint_path_check_samples_until_first_invalid_state():
    facade, _parameter, _logic, bridge = make_facade()
    start = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    goal = dict(start)
    goal["link-5_Revolute-5"] = 0.2
    seen = []

    def validity(sample):
        seen.append(sample["link-5_Revolute-5"])
        return (sample["link-5_Revolute-5"] < 0.1, "collision: spindle", True)

    bridge.check_moveit_static_joint_state = validity
    result = facade.checkStraightJointPath(start, goal)
    assert not result.success and result.code == "straight_path_blocked"
    assert 0.49 < result.details["first_invalid_fraction"] < 0.56
    assert result.details["route_authority"] == "none"
    bridge.check_moveit_static_joint_state = lambda sample: (True, "valid", True)
    clear = facade.checkStraightJointPath(start, goal)
    assert clear.success and clear.details["samples_checked"] == 11
    bridge.check_moveit_static_joint_state = lambda sample: (True, "", False)
    assert facade.checkStraightJointPath(start, goal).code == "straight_path_unknown"


def test_straight_joint_path_uses_shortest_angle_for_continuous_j5():
    facade, _parameter, _logic, bridge = make_facade()
    start = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    start["link-5_Revolute-5"] = 3.1
    goal = dict(start)
    goal["link-5_Revolute-5"] = -3.1
    bridge.check_moveit_static_joint_state = lambda sample: (True, "valid", True)
    result = facade.checkStraightJointPath(start, goal)
    assert result.success
    assert abs(result.details["joint_deltas"]["link-5_Revolute-5"]) < 0.1


def test_static_contact_filter_allows_only_burr_target_and_rejects_truncated_lists():
    allowed = (("burr", "dentobot_target_tooth_11"),)
    check = DENTORobotWorkflowFacade._allowed_only_static_contacts
    ok = "MoveIt rejected the explicit static joint state; contacts=dentobot_target_tooth_11<->burr"
    assert check(ok, allowed) == [["dentobot_target_tooth_11", "burr"]]
    spindle = ok + ", pneumatic_spindle-Copy<->dentobot_target_tooth_11"
    assert check(spindle, allowed) is None
    template = "MoveIt rejected ...; contacts=[Step 5C] DENTO Final Printable Template<->burr"
    assert check(template, allowed) is None
    truncated = ok + ", burr<->dentobot_target_tooth_11 (and 3 more)"
    assert check(truncated, allowed) is None
    assert check(ok, ()) is None
    assert check("MoveIt rejected the explicit static joint state", allowed) is None


def test_endpoint_evaluation_continues_to_fk_on_allowed_contact_only():
    facade, parameter_node, _logic, bridge = make_facade()
    message = "MoveIt rejected the explicit static joint state; contacts=burr<->dentobot_target_tooth_11"
    bridge.check_moveit_static_joint_state = lambda _positions: (False, message, True)
    reached = []
    bridge.compute_tcp_pose_world_ras_mm = lambda positions, base_transform=None: (
        reached.append(True) or (False, "fk unavailable in fake", None))
    positions = {name: 0.0 for name in ROS2_JOINT_SI_ORDER}
    allowed = facade._evaluate_step6_tcp_endpoint(
        parameter_node, positions, expected_tcp_world_ras_mm=(0.0, 0.0, 0.0),
        expected_drill_axis_world_ras_unit=(0.0, 0.0, 1.0),
        allowed_contact_pairs=(("burr", "dentobot_target_tooth_11"),),
    )
    assert reached == [True]
    assert allowed["static_state_validity"]["status"] == "allowed_contact"
    assert allowed["collision"] == {"status": "allowed_contact",
                                    "pairs": [["burr", "dentobot_target_tooth_11"]]}
    strict = facade._evaluate_step6_tcp_endpoint(
        parameter_node, positions, expected_tcp_world_ras_mm=(0.0, 0.0, 0.0),
        expected_drill_axis_world_ras_unit=(0.0, 0.0, 1.0),
    )
    assert strict["status"] == "failed" and strict["static_state_validity"]["status"] == "failed"
    assert reached == [True]  # strict path never reached FK


def _truncation_fixture():
    facade, parameter_node, logic, bridge = make_facade()
    entry = (0.0, 0.0, 0.0)
    target = (0.0, 0.0, 10.0)
    drilling = tuple({name: float(index) for name in ROS2_JOINT_SI_ORDER} for index in range(6))
    from DENTOROS2Bridge import MoveItCartesianResult

    plan = MoveItCartesianResult(
        True, "full line", fraction=1.0, waypoint_joint_vectors_si=drilling,
        waypoint_times_sec=tuple(float(i) for i in range(6)),
    )
    # TCP depth equals the waypoint index * 2 mm along +z.
    bridge.compute_tcp_position_world_ras_mm = lambda state, base_transform=None: (
        True, "ok", (0.0, 0.0, 2.0 * state["link-1_Revolute-1"]))
    snapshot = SimpleNamespace(snapshot_fingerprint="task-1", entry_ras_mm=entry, target_ras_mm=target)
    facade.guard_rearms = []
    facade._configure_phase_guard = lambda node, snap: (facade.guard_rearms.append(snap) or (True, "configured"))
    return facade, parameter_node, logic, bridge, plan, snapshot, entry, target


def test_spindle_collision_truncates_drilling_to_last_collision_free_waypoint():
    facade, parameter_node, _logic, _bridge, plan, snapshot, entry, target = _truncation_fixture()
    validated = []

    def validate(waypoints, phases, task_fingerprint=None):
        validated.append((len(waypoints), phases[-1]))
        return True, "accepted", -1

    prefix = ({name: 0.0 for name in ROS2_JOINT_SI_ORDER},) * 3
    shortened, truncation = facade._truncate_drilling_for_spindle_collision(
        parameter_node, snapshot, prefix, ("approach",) * 3, plan, 3, 3 + 4,
        ("pneumatic_spindle-Copy", "[Step 5C] DENTO Final Printable Template"),
        validate_chain=validate, entry=entry, target=target,
    )
    assert shortened.success is True
    assert len(shortened.waypoint_joint_vectors_si) == 4
    assert validated == [(7, "drilling")]
    assert facade.guard_rearms == [snapshot]  # fresh guard session (r8 stale-sequence rejection)
    assert truncation["completed_depth_mm"] == 6.0
    assert truncation["remaining_depth_mm"] == 4.0
    assert truncation["effective_target_ras_mm"] == [0.0, 0.0, 6.0]
    assert truncation["unreachable_segment_ras_mm"] == [[0.0, 0.0, 6.0], [0.0, 0.0, 10.0]]
    assert abs(shortened.fraction - 0.6) < 1e-12


def test_truncation_only_for_spindle_housing_and_requires_guard_acceptance():
    facade, parameter_node, _logic, _bridge, plan, snapshot, entry, target = _truncation_fixture()
    accept = lambda w, p, task_fingerprint=None: (True, "ok", -1)
    none, reason = facade._truncate_drilling_for_spindle_collision(
        parameter_node, snapshot, (), (), plan, 0, 4, ("burr", "template"),
        validate_chain=accept, entry=entry, target=target)
    assert none is None and "spindle-housing/template" in reason
    none, reason = facade._truncate_drilling_for_spindle_collision(
        parameter_node, snapshot, (), (), plan, 0, 4, ("pneumatic_spindle-Copy", "dentobot_target_tooth_11"),
        validate_chain=accept, entry=entry, target=target)
    assert none is None  # spindle-to-tooth is a failure, never truncated
    none, reason = facade._truncate_drilling_for_spindle_collision(
        parameter_node, snapshot, (), (), plan, 0, 1, ("pneumatic_spindle-Copy", "[Step 5C] DENTO Final Printable Template"),
        validate_chain=accept, entry=entry, target=target)
    assert none is None and "No spindle-collision-free" in reason
    reject = lambda w, p, task_fingerprint=None: (False, "still colliding", 2)
    none, reason = facade._truncate_drilling_for_spindle_collision(
        parameter_node, snapshot, (), (), plan, 0, 4, ("pneumatic_spindle-Copy", "[Step 5C] DENTO Final Printable Template"),
        validate_chain=reject, entry=entry, target=target)
    assert none is None and "still rejected" in reason


def test_preview_endpoint_uses_effective_target_for_shortened_drilling_plan():
    facade, parameter_node, logic, bridge = make_facade()
    last = {name: 0.5 for name in ROS2_JOINT_SI_ORDER}
    snapshot = SimpleNamespace(snapshot_fingerprint="task-1", entry_ras_mm=(0.0, 0.0, 0.0),
                               target_ras_mm=(0.0, 0.0, 10.0))
    logic.confirmedTaskRecord = lambda _parameter: snapshot
    bridge.wait_for_monitored_joint_positions_si = lambda expected: (True, "ok", expected, 0.0)
    bridge.compute_tcp_position_world_ras_mm = lambda state, base_transform=None: (True, "ok", (0.0, 0.0, 6.0))
    plan = SimpleNamespace(requested_phase="drilling", waypoint_joint_vectors_si=(last,))
    assert facade._verify_preview_endpoint(plan).code == "preview_endpoint_tcp_mismatch"
    facade._drilling_truncation = {"task_fingerprint": "task-1", "last_joint_positions_si": dict(last),
                                   "effective_target_ras_mm": [0.0, 0.0, 6.0]}
    assert facade._verify_preview_endpoint(plan).code == "preview_endpoint_verified"
    facade._drilling_truncation["task_fingerprint"] = "other-task"
    assert facade._verify_preview_endpoint(plan).code == "preview_endpoint_tcp_mismatch"


def test_p3_stage_truncation_reguards_and_reevaluates_effective_endpoint():
    facade, parameter_node, logic, bridge = make_facade()
    path = tuple({name: float(index) for name in ROS2_JOINT_SI_ORDER} for index in range(5))
    p1 = ({name: 0.0 for name in ROS2_JOINT_SI_ORDER},) * 2
    p2 = ({name: 0.0 for name in ROS2_JOINT_SI_ORDER},) * 2
    bridge.compute_tcp_position_world_ras_mm = lambda state, base_transform=None: (
        True, "ok", (0.0, 0.0, 2.0 * state["link-1_Revolute-1"]))
    logic.confirmedTaskRecord = lambda _parameter: SimpleNamespace(snapshot_fingerprint="task-1")
    guards = []
    facade._step6_stage_guard_evidence = lambda context, paths: (
        guards.append(len(paths["P3"])) or {"status": "passed"})
    facade._evaluate_step6_tcp_endpoint = lambda *a, **k: {"status": "passed"}
    context = {"parameter_node": parameter_node, "entry": (0.0, 0.0, 0.0),
               "target": (0.0, 0.0, 8.0), "drill_axis": (0.0, 0.0, 1.0)}
    failed = {"status": "failed", "named_pair": ["pneumatic_spindle-Copy", "[Step 5C] DENTO Final Printable Template"],
              "first_invalid_index": 4 + 3}
    result = facade._truncate_p3_stage_for_spindle_collision(
        context, {"P1": p1, "P2": p2, "P3": path}, path, failed)
    shortened, _paths, guard, endpoint, truncation = result
    assert len(shortened) == 3 and guards == [3]
    assert truncation["completed_depth_mm"] == 4.0 and truncation["remaining_depth_mm"] == 4.0
    assert facade._truncate_p3_stage_for_spindle_collision(
        context, {"P1": p1, "P2": p2, "P3": path}, path,
        {"status": "failed", "named_pair": ["burr", "template"], "first_invalid_index": 7}) is None


def test_mouth_portal_gate_maps_joint_path_to_tcp_path_and_fails_closed():
    facade, parameter_node, logic, bridge = make_facade()
    path = ({name: 0.0 for name in ROS2_JOINT_SI_ORDER}, {name: 1.0 for name in ROS2_JOINT_SI_ORDER})
    bridge.compute_tcp_position_world_ras_mm = lambda state, base_transform=None: (
        True, "ok", (0.0, 50.0 - 60.0 * state["link-1_Revolute-1"], 0.0))
    assert facade._step6_mouth_portal_gate(parameter_node, path) is None  # no portal support in fake
    seen = []
    logic.checkStep6MouthPortalGate = lambda _node, tcp: seen.append(tcp) or {"status": "passed"}
    assert facade._step6_mouth_portal_gate(parameter_node, path)["status"] == "passed"
    assert seen == [[(0.0, 50.0, 0.0), (0.0, -10.0, 0.0)]]

    def unavailable(_node, _tcp):
        raise ValueError("Mouth portal vertex 13 has no canine")

    logic.checkStep6MouthPortalGate = unavailable
    result = facade._step6_mouth_portal_gate(parameter_node, path)
    assert result["status"] == "failed" and result["reason"] == "portal_unavailable"


def test_mouth_portal_gate_reports_without_blocking_until_enforced():
    facade, _parameter, _logic, _bridge = make_facade()
    failed = {"status": "failed", "reason": "preentry_not_inside"}
    assert facade.MOUTH_PORTAL_GATE_MODE == "enforce"
    assert facade._mouth_portal_blocks(None) is False
    facade.MOUTH_PORTAL_GATE_MODE = "report"
    assert facade._mouth_portal_blocks(failed) is False
    facade.MOUTH_PORTAL_GATE_MODE = "enforce"
    assert facade._mouth_portal_blocks(failed) is True
    assert facade._mouth_portal_blocks({"status": "passed"}) is False
    assert facade._mouth_portal_blocks({"status": "skipped", "reason": "mouth_barrier_off"}) is False


def test_approach_corridor_composes_free_space_then_straight_descent_and_falls_back():
    from DENTOROS2Bridge import MoveItCartesianResult

    facade, parameter_node, _logic, bridge = make_facade()
    parameter_node.robotMotionPlanSampleCount = 5
    q = lambda v: {name: float(v) for name in ROS2_JOINT_SI_ORDER}
    calls = []

    def cartesian(**kwargs):
        assert kwargs["reverse_travel"] is True
        calls.append(("cartesian", kwargs["entry_ras_mm"], kwargs["target_ras_mm"]))
        return MoveItCartesianResult(True, "line", 1.0, (q(5), q(6), q(7)), (0.0, 0.1, 0.2))

    def joint(**kwargs):
        calls.append(("joint", kwargs["goal_joint_positions_si"]["link-1_Revolute-1"]))
        return MoveItCartesianResult(True, "free", 1.0, (q(0), q(3), q(7)), (0.0, 1.0, 2.0))

    bridge.plan_moveit_cartesian_path = cartesian
    bridge.plan_moveit_joint_goal = joint
    plan = facade._plan_home_to_preentry_with_corridor(
        parameter_node, q(0), q(5), pre_entry=(0.0, 0.0, -2.0), entry=(0.0, 0.0, 0.0),
        target=(0.0, 0.0, 10.0), fixed_rotation_ras=None, roll_deg=0.0, planner_context="t")
    assert calls[0] == ("cartesian", (0.0, 0.0, -2.0), (0.0, 0.0, -14.0))
    assert calls[1] == ("joint", 7.0)  # free-space goal is the approach point
    assert [p["link-1_Revolute-1"] for p in plan.waypoint_joint_vectors_si] == [0, 3, 7, 6, 5]
    assert plan.waypoint_joint_vectors_si[-1] == q(5) and "Approach corridor" in plan.message
    bridge.plan_moveit_cartesian_path = lambda **k: MoveItCartesianResult(False, "blocked")
    fallback = facade._plan_home_to_preentry_with_corridor(
        parameter_node, q(0), q(5), pre_entry=(0.0, 0.0, -2.0), entry=(0.0, 0.0, 0.0),
        target=(0.0, 0.0, 10.0), fixed_rotation_ras=None, roll_deg=0.0, planner_context="t")
    assert "corridor unavailable" in fallback.message


def test_approach_corridor_shortens_to_collision_free_prefix_or_reports_block():
    """S6-LIVE-01 2026-10-04: A was inside FDI43/lip slab; keep the clear prefix."""
    from DENTOROS2Bridge import MoveItCartesianResult

    facade, parameter_node, _logic, bridge = make_facade()
    parameter_node.robotMotionPlanSampleCount = 5
    q = lambda v: {name: float(v) for name in ROS2_JOINT_SI_ORDER}
    goals = []
    back = tuple(q(v) for v in (5, 6, 7, 8, 9))  # PreEntry .. 12 mm out, 3 mm apart
    bridge.plan_moveit_cartesian_path = lambda **k: MoveItCartesianResult(
        True, "line", 1.0, back, (0.0, 0.1, 0.2, 0.3, 0.4))

    def joint(**kwargs):
        goals.append(kwargs["goal_joint_positions_si"]["link-1_Revolute-1"])
        return MoveItCartesianResult(True, "free", 1.0, (q(0), q(kwargs["goal_joint_positions_si"]["link-1_Revolute-1"])), (0.0, 1.0))

    bridge.plan_moveit_joint_goal = joint
    blocked_from = {"value": 8.0}
    bridge.check_moveit_static_joint_state = lambda state: (
        (state["link-1_Revolute-1"] < blocked_from["value"]), "lip_slab <-> spindle", True)
    args = dict(pre_entry=(0.0, 0.0, -2.0), entry=(0.0, 0.0, 0.0), target=(0.0, 0.0, 10.0),
                fixed_rotation_ras=None, roll_deg=0.0, planner_context="t")
    plan = facade._plan_home_to_preentry_with_corridor(parameter_node, q(0), q(5), **args)
    assert goals[-1] == 7.0  # shortened approach point: last valid back-out state
    assert [p["link-1_Revolute-1"] for p in plan.waypoint_joint_vectors_si] == [0, 7, 6, 5]
    assert "6.00 mm out along the drill axis" in plan.message
    facade._approach_corridor_margin_samples = 1
    margin = facade._plan_home_to_preentry_with_corridor(parameter_node, q(0), q(5), **args)
    assert goals[-1] == 6.0 and "3.00 mm out along the drill axis" in margin.message
    facade._approach_corridor_margin_samples = 0
    blocked_from["value"] = 6.0
    fallback = facade._plan_home_to_preentry_with_corridor(parameter_node, q(0), q(5), **args)
    assert "axial corridor blocked 0.00 mm behind PreEntry: lip_slab <-> spindle" in fallback.message


def test_free_space_leg_is_replanned_independently_when_the_planner_returns_no_route():
    """S6-LIVE-01 2026-10-05: a single sampling call misses an existing route ~1 in 30."""
    import DENTORobotWorkflowFacade as module
    from DENTOROS2Bridge import MoveItCartesianResult

    facade, parameter_node, _logic, bridge = make_facade()
    q = lambda v: {name: float(v) for name in ROS2_JOINT_SI_ORDER}
    replies = [MoveItCartesianResult(False, "empty"), MoveItCartesianResult(True, "free", 1.0, (q(0), q(7)), (0.0, 1.0))]
    bridge.plan_moveit_joint_goal = lambda **k: replies.pop(0)
    plan = facade._plan_joint_goal_with_retries(start_joint_positions_si=q(0), goal_joint_positions_si=q(7))
    assert plan.success and "re-plan 2 of 8" in plan.message
    bridge.plan_moveit_joint_goal = lambda **k: MoveItCartesianResult(False, "empty")
    failed = facade._plan_joint_goal_with_retries(start_joint_positions_si=q(0), goal_joint_positions_si=q(7))
    assert not failed.success and f"no route in {module.STEP6_JOINT_PLAN_RETRIES} independent re-plans" in failed.message


def test_plan_approach_warns_when_case_policy_is_below_project_default():
    """S6-LIVE-01 2026-10-05: a case saved with 1 attempt (default 5) failed reliably."""
    import DENTORobotWorkflowFacade as module

    facade, _parameter_node, _logic, _bridge = make_facade()
    facade._plan_approach_phase = lambda **k: module.RobotActionResult(True, "ok", "planned", details={"a": 1})
    low = facade.planApproachPhase(planning_attempts=1)
    assert low.message.startswith("WARNING: planning attempts 1 is below the project default 5")
    assert low.details["planningPolicyBelowDefault"] is True and low.details["a"] == 1 and low.success
    default = facade.planApproachPhase(planning_attempts=module.STEP6_JOINT_PLANNING_ATTEMPTS)
    assert default.message == "planned"


def test_plan_approach_is_refused_when_moveit_scene_differs_from_slicer():
    """S6-LIVE-01 2026-10-06: refuse planning on a MoveGroup/Slicer scene mismatch."""
    import DENTORobotWorkflowFacade as module
    from types import SimpleNamespace

    facade, parameter_node, logic, bridge = make_facade()
    module.STEP6_SCENE_RESYNC_WAIT_SEC, saved_wait = 0.0, module.STEP6_SCENE_RESYNC_WAIT_SEC
    planned = []
    facade._plan_approach_phase = lambda **k: planned.append(1) or module.RobotActionResult(True, "ok", "planned")
    audit = SimpleNamespace(object_records=[{"outgoing_collision_object_id": "t31",
                                             "outgoing_bounds_base_link_mm": [0, 1, 0, 1, 0, 1]}])
    logic.collisionSceneAuditRecord = lambda node: audit
    bridge.read_moveit_world_object_bounds = lambda: (True, "1 object", [{"id": "t31", "bounds_mm": [19.4, 20.4, 0, 1, 0, 1]}])
    syncs = []
    logic.syncStep6MoveItPlanningScene = lambda node: syncs.append(1)
    refused = facade.planApproachPhase()
    assert not refused.success and refused.code == "moveit_scene_mismatch" and not planned
    assert "t31 (19.4 mm)" in refused.message and len(syncs) == module.STEP6_SCENE_REPAIR_ROUNDS
    scenes = [[{"id": "t31", "bounds_mm": [19.4, 20.4, 0, 1, 0, 1]}], [{"id": "t31", "bounds_mm": [0, 1, 0, 1, 0, 1]}]]
    bridge.read_moveit_world_object_bounds = lambda: (True, "1 object", scenes.pop(0))
    healed = facade.planApproachPhase()
    assert healed.success and healed.message.startswith("NOTE: MoveIt's planning scene differed") and planned
    planned.clear()
    bridge.read_moveit_world_object_bounds = lambda: (True, "1 object", [{"id": "t31", "bounds_mm": [0, 1, 0, 1, 0, 1]}])
    assert facade.planApproachPhase().success and planned
    bridge.read_moveit_world_object_bounds = lambda: (False, "timed out", [])
    unreadable = facade.planApproachPhase()
    assert not unreadable.success and "could not be read" in unreadable.message
    module.STEP6_SCENE_RESYNC_WAIT_SEC = saved_wait


def test_stage_checks_share_the_scene_gate_and_report_its_state():
    """Operator 2026-10-06: stage checks and Diagnose also re-sync and report the scene state."""
    import DENTORobotWorkflowFacade as module
    from types import SimpleNamespace

    facade, parameter_node, logic, bridge = make_facade()
    module.STEP6_SCENE_RESYNC_WAIT_SEC, saved_wait = 0.0, module.STEP6_SCENE_RESYNC_WAIT_SEC
    try:
        assert facade.ensureMoveItSceneMatches()["state"] == "not_checked"
        logic.collisionSceneAuditRecord = lambda node: SimpleNamespace(object_records=[
            {"outgoing_collision_object_id": "t", "outgoing_bounds_base_link_mm": [0, 1, 0, 1, 0, 1]}])
        logic.syncStep6MoveItPlanningScene = lambda node: None
        bridge.read_moveit_world_object_bounds = lambda: (True, "", [{"id": "t", "bounds_mm": [5, 6, 0, 1, 0, 1]}])
        refused = facade.checkPlanningStage("P1")
        assert not refused.success and refused.code == "moveit_scene_mismatch"
        assert refused.payload["diagnostic_status"] == "unknown"
        assert facade.lastMoveItSceneStatus["state"] == "mismatch"
        bridge.read_moveit_world_object_bounds = lambda: (True, "", [{"id": "t", "bounds_mm": [0, 1, 0, 1, 0, 1]}])
        assert facade.ensureMoveItSceneMatches()["state"] == "matched"
    finally:
        module.STEP6_SCENE_RESYNC_WAIT_SEC = saved_wait


def test_scene_repair_resends_only_differing_objects_one_at_a_time():
    """6 Oct root cause: a burst sync lost updates; repair re-sends only the stale objects."""
    import DENTORobotWorkflowFacade as module
    from types import SimpleNamespace

    facade, parameter_node, logic, bridge = make_facade()
    module.STEP6_SCENE_RESYNC_WAIT_SEC, saved_wait = 0.0, module.STEP6_SCENE_RESYNC_WAIT_SEC
    try:
        logic.collisionSceneAuditRecord = lambda node: SimpleNamespace(object_records=[
            {"outgoing_collision_object_id": i, "outgoing_bounds_base_link_mm": [0, 1, 0, 1, 0, 1]} for i in ("a", "b")])
        logic.syncStep6MoveItPlanningScene = lambda node: (_ for _ in ()).throw(AssertionError("no burst re-sync"))
        state = {"a": [5, 6, 0, 1, 0, 1], "b": [0, 1, 0, 1, 0, 1]}
        bridge.read_moveit_world_object_bounds = lambda: (True, "", [{"id": k, "bounds_mm": v} for k, v in state.items()])
        resent = []

        def republish(ids):
            resent.append(list(ids))
            for i in ids:
                state[i] = [0, 1, 0, 1, 0, 1]
            return True, "re-sent", list(ids)

        bridge.republish_moveit_obstacles = republish
        status = facade.ensureMoveItSceneMatches()
        assert status["state"] == "resynced" and not status["refuse"] and resent == [["a"]]
        assert status["repair_log"] == ["round 1: re-sent"]
    finally:
        module.STEP6_SCENE_RESYNC_WAIT_SEC = saved_wait


def test_spindle_guide_contact_option_reaches_guard_and_policy_fingerprint_only_when_on():
    import DENTOROS2Bridge as real_bridge

    facade, parameter_node, _logic, bridge = make_facade()
    for name in ("ROS2_RESEARCH_MINIMUM_CLEARANCE_M", "ROS2_JOINT_SI_ORDER",
                 "ROS2_PLANNING_GROUP", "ROS2_TOOL_TCP_LINK"):
        setattr(bridge, name, getattr(real_bridge, name))
    default_fingerprint = facade._strict_guard_policy_fingerprint()
    assert facade._spindle_guide_contact_allowed() is False
    parameter_node.step6AllowSpindleGuideContact = True
    assert facade._spindle_guide_contact_allowed() is True
    assert facade._strict_guard_policy_fingerprint() != default_fingerprint
    parameter_node.step6AllowSpindleGuideContact = False
    assert facade._strict_guard_policy_fingerprint() == default_fingerprint


def test_final_composed_chain_applies_spindle_template_truncation_in_drilling():
    # r7 2026-10-02: the final Stage 1 + axis + Stage 2 + drilling guard check
    # blocked on spindle-housing <-> template at the last drilling waypoint while
    # the chain preflight (without the axis segment) passed. Policy 2b applies there too.
    source = (HELPERS / "DENTORobotWorkflowFacade.py").read_text()
    start = source.index("drilling_offset = len(preflight_waypoints) - len(")
    block = source[start:source.index("First invalid composed waypoint", start)]
    assert "self._truncate_drilling_for_spindle_collision(" in block
    assert "int(invalid_index) >= drilling_offset" in block
    assert '"drillingTruncation": truncation_or_reason' in block
    assert "Truncation not applied" in block


def test_mouth_gate_rejected_candidate_returns_empty_plans_not_none():
    # r10 2026-10-02: Plan Approach crashed reading chain["axisPlan"].fraction
    # for a candidate rejected by the mouth portal gate.
    from types import SimpleNamespace as NS

    facade, parameter_node, _logic, _bridge = make_facade()
    facade._step6_mouth_portal_gate = lambda *_a, **_k: {"status": "failed", "reason": "crossing_outside_portal"}
    chain = facade._goal1_candidate_chain_preflight(
        parameter_node, NS(snapshot_fingerprint="t"), {"score": (0,), "rollDeg": 0.0},
        NS(waypoint_joint_vectors_si=()), pre_entry=(0, 0, 0), entry=(0, 0, 1), target=(0, 0, 2),
    )
    assert chain["status"] == "BlockedMouthPortalGate"
    assert chain["axisPlan"].fraction == 0.0 and chain["terminalPlan"].waypoint_joint_vectors_si == ()
    assert chain["drillingPlan"] is None


# --- S6-BASE-DIAGNOSE / S6-TRUNCATION-WARNING (operator 2026-10-02) ---------------


def _diagnose_fixture(*, reachable=True, preentry="EndpointChecksPassed", stages=None):
    facade, parameter_node, logic, _bridge = make_facade()
    calls = []
    facade._require_context = lambda: parameter_node
    logic.step6CurrentBaseStrokeReachability = lambda node: (
        calls.append("stroke") or {"reachable": reachable, "first_failed_station": "PreEntry"}
    )

    def preentry_ik(progress=None):
        calls.append("preentry")
        return SimpleNamespace(success=True, message="m", details={"diagnosticStatus": preentry}, payload=None)

    def stage(phase_id, progress=None):
        calls.append(phase_id)
        outcome = (stages or {}).get(phase_id, {"diagnostic_status": "passed", "reason": "ok", "endpoint_evidence": {}})
        return SimpleNamespace(success=True, message="m", details={"stageOutcome": outcome}, payload=outcome)

    facade.checkPreEntryIK = preentry_ik
    facade.checkPlanningStage = stage
    return facade, calls


def test_diagnose_base_always_cross_checks_kdl_against_moveit_fk():
    """Operator 2026-10-06: the frame check is a standard Diagnose row with verdict priority."""
    facade, calls = _diagnose_fixture(reachable=False)
    bridge = facade._bridge
    eye = ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
    shifted = ((1, 0, 0, 5.0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))
    facade._logic.taskHomeRecord = lambda node: SimpleNamespace(joint_names=("j",), joint_positions_si=(0.0,))
    bridge.compute_tcp_pose_world_ras_mm = lambda q, base_transform=None: (True, "", eye)
    bridge.compute_moveit_tcp_pose_world_ras_mm = lambda q, base_transform=None: (True, "", eye)
    summary = facade.diagnoseBase().details["baseDiagnosis"]
    assert summary["rows"][-1]["check"] == "frame_match" and summary["rows"][-1]["status"] == "PASS"
    assert summary["cause"] == "base_placement"  # planning failure still reported when frames agree
    bridge.compute_moveit_tcp_pose_world_ras_mm = lambda q, base_transform=None: (True, "", shifted)
    summary = facade.diagnoseBase().details["baseDiagnosis"]
    assert summary["cause_class"] == "frame_mismatch" and summary["rows"][-1]["status"] == "FAIL"


def test_diagnose_base_stops_at_base_placement():
    facade, calls = _diagnose_fixture(reachable=False)
    result = facade.diagnoseBase()
    summary = result.details["baseDiagnosis"]
    assert calls == ["stroke"]
    assert not result.success and summary["cause"] == "base_placement"
    assert "Find Reachable Base" in result.message


def test_diagnose_base_runs_all_checks_in_order_and_reports_truncation_warning():
    truncation = {
        "completed_depth_mm": 4.0, "requested_depth_mm": 9.741, "remaining_depth_mm": 5.741,
        "blocking_pair": ["[Step 5C] DENTO Final Printable Template", "pneumatic_spindle-Copy"],
    }
    p3 = {"diagnostic_status": "passed", "reason": "ok",
          "endpoint_evidence": {"plan": {"drilling_truncation": truncation}}}
    facade, calls = _diagnose_fixture(stages={"P3": p3})
    result = facade.diagnoseBase()
    assert calls == ["stroke", "preentry", "P1", "P2", "P3"]
    assert result.success and result.details["baseDiagnosis"]["status"] == "WARNING"
    assert "4.00 of 9.74 mm" in result.message


def test_diagnose_base_names_p2_collision_and_skips_p3():
    p2 = {"diagnostic_status": "failed", "reason": "guard rejected",
          "endpoint_evidence": {"phase_guard": {"named_pair": ["pneumatic_spindle-Copy", "upper lip"]}}}
    facade, calls = _diagnose_fixture(stages={"P2": p2})
    result = facade.diagnoseBase()
    assert calls == ["stroke", "preentry", "P1", "P2"]
    assert result.details["baseDiagnosis"]["cause"] == "entry_collision"
    assert "pneumatic_spindle-Copy ↔ upper lip" in result.message


def test_diagnose_base_exception_marks_the_pending_check_failed():
    facade, calls = _diagnose_fixture()

    def broken(phase_id, progress=None):
        raise RuntimeError("scene unavailable")

    facade.checkPlanningStage = broken
    result = facade.diagnoseBase()
    rows = result.details["baseDiagnosis"]["rows"]
    assert [row["status"] for row in rows] == ["PASS", "PASS", "FAIL", "NOT RUN", "NOT RUN"]
    assert "scene unavailable" in rows[2]["detail"]


def test_truncation_warning_text_names_depths_pair_and_remainder():
    import DENTORobotWorkflowFacade as module

    text = module._drilling_truncation_warning({
        "completed_depth_mm": 4.0, "requested_depth_mm": 9.741, "remaining_depth_mm": 5.741,
        "blocking_pair": ["template", "pneumatic_spindle-Copy"],
    })
    assert text.startswith("WARNING: drilling shortened")
    assert "4.00 of 9.74 mm" in text and "5.74 mm" in text and "not completed" in text
    assert "template ↔ pneumatic_spindle-Copy" in text


def test_plan_and_drill_results_carry_truncation_for_warning_state():
    source = (HELPERS / "DENTORobotWorkflowFacade.py").read_text()
    assert source.count('"drillingTruncation": self._drilling_truncation') >= 2
    manual = (HELPERS / "dentobot_workflow" / "widget_robot_manual.py").read_text()
    assert '"warning" if warning else "ok" if result.success else "error"' in manual


def test_dev_fast_mode_is_off_by_default_and_stamps_unevaluated_candidates(monkeypatch):
    import DENTORobotWorkflowFacade as module

    monkeypatch.delenv("DENTOBOT_STEP6_DEV_FIRST_COMPLETE_ROUTE", raising=False)
    facade, *_ = make_facade()
    assert facade._dev_first_complete_route is False
    assert module._dev_fast_mode_stamp({"mode": "all", "total": 11, "evaluated": 11}) == ""
    stamp = module._dev_fast_mode_stamp({"mode": "dev_first_complete", "total": 11, "evaluated": 2, "notEvaluated": 9})
    assert stamp.startswith("DEVELOPMENT FAST MODE: 9 of 11 candidates not evaluated")
    assert "not for acceptance or case comparison" in stamp
    monkeypatch.setenv("DENTOBOT_STEP6_DEV_FIRST_COMPLETE_ROUTE", "1")
    assert make_facade()[0]._dev_first_complete_route is True


def test_dev_fast_mode_breaks_only_on_complete_chain_and_records_evaluation():
    source = (HELPERS / "DENTORobotWorkflowFacade.py").read_text()
    block = source[source.index("planned_candidate_routes.append(route)"):]
    block = block[:block.index('if chain["status"] != "Complete":')]
    assert 'if dev_first_complete and chain["status"] == "Complete":' in block
    # Read once per plan so a mid-plan 6.3 run-option toggle cannot change it.
    assert "dev_first_complete = bool(self._dev_first_complete_route)" in source
    assert "notEvaluated=candidate_total - candidate_index - 1" in block and "break" in block
    assert '"candidateEvaluation": dict(self._candidate_evaluation)' in source
    assert "_dev_fast_mode_stamp(self._candidate_evaluation)" in source


def test_planned_route_outcome_carries_input_identity_fields():
    facade, *_ = make_facade()
    facade.plannerComparisonIdentity = lambda: {
        "task": "t", "base": "b", "home": "h", "trajectory": "tr",
        "robot_profile": "rp", "collision_audit": "ca", "branch_id": "br",
    }
    fields = facade._goal1_identity_fields()
    assert fields == {
        "task_identity_fingerprint": "t", "base_identity_fingerprint": "b",
        "home_identity_fingerprint": "h", "trajectory_identity_fingerprint": "tr",
        "robot_profile_identity_fingerprint": "rp", "collision_scene_identity_fingerprint": "ca",
        "branch_id": "br",
    }
    source = (HELPERS / "DENTORobotWorkflowFacade.py").read_text()
    block = source[source.index("def _persist_goal1_diagnostic("):]
    assert "**self._goal1_identity_fields()," in block[:block.index("\n    def ", 10)]


def test_complete_chains_rank_by_drilled_depth_before_arm_motion():
    """Operator 2026-10-03, r16 data: 4.25 mm (motion 0.1913) must beat 4.00 mm (0.1878)."""
    from DENTORobotWorkflowFacade import DENTORobotWorkflowFacade as F

    entry, target = (0.0, 0.0, 0.0), (0.0, 0.0, 9.741)
    full = SimpleNamespace(fraction=1.0)
    depth = F._complete_chain_drilled_depth_mm
    deep = depth("Complete", {"completed_depth_mm": 4.2512}, full, entry, target)
    shallow = depth("Complete", {"completed_depth_mm": 4.0004}, full, entry, target)
    assert (deep, shallow) == (4.25, 4.0)
    assert depth("Complete", None, full, entry, target) == 9.74
    assert depth("BlockedStage3PhaseGuard", {"completed_depth_mm": 4.0}, full, entry, target) == 0.0
    deep_score = (0, -deep, 0.1913, (0.1,))
    shallow_score = (0, -shallow, 0.1878, (0.1,))
    full_score = (0, -9.74, 0.25, (0.1,))
    assert sorted([shallow_score, deep_score, full_score])[0] == full_score
    assert min(shallow_score, deep_score) == deep_score
    # Equal rounded depth: arm motion decides.
    tied = (0, -depth("Complete", {"completed_depth_mm": 4.2498}, full, entry, target), 0.1890, (0.1,))
    assert min(deep_score, tied) == tied
    source = (HELPERS / "DENTORobotWorkflowFacade.py").read_text()
    assert "-self._complete_chain_drilled_depth_mm(" in source


def test_candidate_ranking_truncation_does_not_replay_the_accepted_prefix():
    """Operator 2026-10-03 option A: the candidate-level shortened chain equals the
    prefix the same guard session already accepted; only the final chain re-validates."""
    facade, parameter_node, _logic, _bridge, plan, snapshot, entry, target = _truncation_fixture()
    validated = []
    prefix = ({name: 0.0 for name in ROS2_JOINT_SI_ORDER},) * 3
    shortened, truncation = facade._truncate_drilling_for_spindle_collision(
        parameter_node, snapshot, prefix, ("approach",) * 3, plan, 3, 3 + 4,
        ("pneumatic_spindle-Copy", "[Step 5C] DENTO Final Printable Template"),
        validate_chain=lambda *a, **k: validated.append(a) or (True, "ok", -1),
        entry=entry, target=target, revalidate=False,
    )
    assert shortened.success is True and len(shortened.waypoint_joint_vectors_si) == 4
    assert validated == [] and facade.guard_rearms == []
    assert truncation["completed_depth_mm"] == 6.0
    source = (HELPERS / "DENTORobotWorkflowFacade.py").read_text()
    candidate = source[source.index("def _goal1_candidate_chain_preflight("):]
    candidate = candidate[:candidate.index("\n    def ", 10)]
    assert "revalidate=False," in candidate
    final = source[source.index("# Operator policy 2b (2026-10-02) also applies to the final"):]
    final = final[:final.index("if shortened is not None:")]
    assert "revalidate" not in final  # final composed chain keeps the full re-validation
