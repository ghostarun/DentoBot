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
    SPINDLE_JOINT_NAME,
    fingerprint,
    parse_manual_simulation_record,
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
        self.inputVolume = object()
        self.teethSegmentation = object()
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
        parameter_node.robotJoint6Deg,
    )

    def forbidden_context_access():
        raise AssertionError("blocked motion path accessed workflow context")

    facade._require_context = forbidden_context_access
    results = (
        facade.applyTaskHome(),
        facade.saveTaskHome(),
        facade.requestJointValue(1, 15.0),
        facade.requestCurrentJointState(),
    )

    assert all(not result.success for result in results)
    assert all(result.code == "incomplete_preview_blocks_motion" for result in results)
    assert all(result.details["incompletePreview"]["status"] == "Incomplete"
               for result in results)
    assert bridge.applied == []
    assert bridge.phase_calls == []
    assert logic.updated == []
    assert original_display == (
        parameter_node.robotJoint1Deg,
        parameter_node.robotJoint2Mm,
        parameter_node.robotJoint3Deg,
        parameter_node.robotJoint4Mm,
        parameter_node.robotJoint5Deg,
        parameter_node.robotJoint6Deg,
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
    parameter_node.robotBaseTransform.active = True
    parameter_node.step6PlanningContextImported = True
    parameter_node.step6TrajectoryRegistryJson = json.dumps(
        {"selected_branch_id": "branch-a", "prepared_branches": {"branch-a": {}}}
    )
    parameter_node.step6ToolFrame = "dentobot_drill_tcp"
    parameter_node.targetToothSegmentId = "tooth-segment"
    parameter_node.step6MotionDiagnosticJson = "preserve-this-record"
    facade._planning_scene_synchronized = True

    snapshot = SimpleNamespace(
        snapshot_fingerprint="task-a",
        entry_ras_mm=(0.0, 0.0, 0.0),
        target_ras_mm=(0.0, 0.0, 10.0),
        base_fingerprint="base-a",
        home_fingerprint="home-a",
        trajectory_revision="trajectory-a",
        robot_profile_fingerprint="robot-a",
    )
    audit = SimpleNamespace(runtime_acknowledgement={"status": "Acknowledged"})
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


def test_manual_draft_state_evaluates_supplied_vector_read_only(monkeypatch):
    facade, _node, logic, bridge, checked, fk = _manual_endpoint_probe(monkeypatch)
    request = dict(
        zip(ROS2_JOINT_SI_ORDER, (0.6, 0.001, 0.02, 0.002, 0.03))
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
    assert evaluation["stale"] is True
    assert evaluation["identity_status"] == "stale"
    assert evaluation["input_status"] == "captured_review"
    assert evaluation["status"] == "unknown"
    assert evaluation["target_endpoint_status"] == "unknown"
    assert evaluation["endpoint_evaluation"]["static_state_validity"]["status"] == "passed"
    assert len(checked) == len(fk) == 1
    assert checked[0] == fk[0][0] == request
    assert bridge.accepted == accepted_before
    assert bridge.applied == []
    assert bridge.phase_calls == []


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
        {**request, SPINDLE_JOINT_NAME: 0.0},
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


def _manual_jog_probe(monkeypatch):
    facade, parameter_node, logic, bridge = make_facade()
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
    logic.collisionSceneAuditRecord = lambda _node: audit
    logic.robotBaseFingerprint = lambda _node: "base-a"
    logic.robotProfileFingerprint = lambda: "robot-a"
    logic.step6TrajectoryRevision = lambda _node: "trajectory-a"
    logic.step6TaskLimitsFingerprint = lambda _node: "limits-a"
    logic.evaluatePreparedBranchEligibility = (
        lambda *_args, **_kwargs: {"eligible": True}
    )
    logic.robotDescriptionPaths = lambda: ("fake.urdf", "fake-root")
    facade._step6_read_only_freshness_issues = lambda _node: ()
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
        status = raw_status(False, echo, accepted, "static collision")
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
    assert len(bridge.query_requests[0][0]) == 5  # J6 never enters the query.
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
    bridge.raw_reject = False
    accepted_after_rejection = facade.guardManualRobotJog(request)
    assert accepted_after_rejection.success
    assert accepted_after_rejection.details["manualJogReconciliationRequired"] is False
    assert len(bridge.raw_requests) == 2


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


def test_manual_jog_blocks_j6_out_of_limits_and_reentrant_submission(monkeypatch):
    facade, _node, logic, bridge, request, limits, task, mechanical = (
        _manual_jog_probe(monkeypatch)
    )
    with_j6 = {**request, SPINDLE_JOINT_NAME: 0.0}

    rejected_j6 = facade.guardManualRobotJog(with_j6)
    assert rejected_j6.details["rawGuardOutcome"] == "not_submitted"
    assert rejected_j6.details["manualJogStatus"] == "rejected"
    assert rejected_j6.details["manualJogReconciliationRequired"] is False

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
    accepted = facade.guardManualRobotJog(request)
    accepted_record = parse_manual_simulation_record(facade.manualSimulationRecord())
    assert [event["kind"] for event in accepted_record["events"]] == [
        "requested",
        "guard_accepted",
    ]
    assert accepted_record["record_status"] == "historical_display_only"
    assert accepted_record["events"][0]["requested_joints"] == request
    assert accepted_record["events"][1]["accepted_joints"] == request
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
    assert unknown.details["acceptedJointPositionsSi"] is None


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


def test_manual_simulation_record_reports_missing_identity():
    facade, _node, _logic, _bridge = make_facade()
    try:
        facade.manualSimulationRecord()
    except RuntimeError as exc:
        assert "recording is unavailable" in str(exc)
    else:
        raise AssertionError("record export must be unavailable without a complete identity")
