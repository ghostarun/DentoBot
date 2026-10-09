"""Pure tests for the module-native feasibility search (S6-ADVISOR-GUI-01).

The session is driven with fakes for the logic, facade and parameter node; no
Slicer, ROS or MoveIt. Source-level checks assert the structural promises that
runtime fakes cannot (no blocking loops, one storing path).
"""

import ast
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(PYTHON))

from dentobot_workflow import advisor_service as svc  # noqa: E402
from dentobot_workflow import feasibility_advisor as fa  # noqa: E402

SERVICE_SOURCE = PYTHON / "dentobot_workflow" / "advisor_service.py"
SAVED_BASE = np.eye(4)
SAVED_BASE[:3, 3] = (100.0, 200.0, 300.0)
HOME = {"j1": 0.1, "j2": -0.2, "j3": 0.3, "j4": 0.0, "j5": 0.5}
SMALL = fa.OrderedLimits(lateral_range_mm=10.0, vertical_range_mm=10.0, vertical_grid_step_mm=10.0,
                         depth_range_mm=5.0, max_opening_mm=41.0, max_yaw_deg=10.0)
LANDMARK_POINTS = tuple(float(v) for v in range(12))  # four RAS points: legacy Case Foundation landmarks


def ok(code="ok", message="", **kwargs):
    return SimpleNamespace(success=True, code=code, message=message, details=kwargs.pop("details", {}),
                           payload=kwargs.pop("payload", None))


def fail(code="bad", message="refused", **kwargs):
    return SimpleNamespace(success=False, code=code, message=message, details=kwargs.pop("details", {}),
                           payload=None)


class Transform:
    def __init__(self, matrix):
        self.matrix = np.array(matrix, dtype=float)

    def GetMatrixTransformToWorld(self, out):
        for r in range(4):
            for c in range(4):
                out.SetElement(r, c, float(self.matrix[r, c]))


class Payload:
    def to_dict(self):
        return {"candidate_records": [{
            "candidate_index": 0, "static_state_validity_status": "Valid", "endpoint_check_status": "Passed",
            "best_joint_positions_si": dict(HOME), "collision_pairs": []}], "session_fingerprint": "s"}


class Node:
    """Parameter-node fake: opening and lock state live on the shared World."""

    def __init__(self, world):
        self._world = world
        self.robotBaseTransform = world.base
        self.robotMountPlane = object()
        self.step6PlanningContextImported = True
        self.step6AllowSpindleGuideContact = False
        self.step6MouthBarrierEdgeMode = "gum_line"

    @property
    def step6TrajectoryRegistryJson(self):
        return self._world.registry_json()

    step6CaseJawTargetGapMm = property(lambda self: self._world.opening,
                                       lambda self, v: setattr(self._world, "opening", float(v)))
    robotBaseMountLocked = property(lambda self: self._world.locked)


class World:
    """Shared fake of logic + facade + node; ``oracle`` decides each geometric check."""

    def __init__(self, *, oracle=None, opening=40.0, profile="profile-1", branch_valid=lambda w: True,
                 home=HOME, stale_home_on_base_change=False, stale_home_on_opening=False,
                 disconnect_drops_connection=False, full_identity=True, landmarks_present=True,
                 landmark_points=LANDMARK_POINTS):
        self.calls = []
        self.landmarks_present = landmarks_present  # False: no Step 6 case jaw landmarks node exists
        self.landmark_points = tuple(landmark_points)
        self.opening = opening
        self.connected = True
        self.locked = True
        self.base = Transform(SAVED_BASE)
        self.staged = None
        self.policy = {"planner_id": "RRTConnectkConfigDefault", "planning_attempts": 5, "planning_time_sec": 5.0,
                       "independent_replans": 3}
        self.margin = 0
        self.stored = []
        self.oracle = oracle or (lambda view: {})
        self.profile = profile
        self.branch_valid = branch_valid
        self.home_stale = False
        self.home_review_in_progress = False
        self.stale_home_on_base_change = stale_home_on_base_change
        self.stale_home_on_opening = stale_home_on_opening
        self.disconnect_drops_connection = disconnect_drops_connection
        self.full_identity = full_identity
        self.last_scene_status = {"state": "matched"}  # facade lastMoveItSceneStatus is a @property (None or dict)
        self.branch_revision = "branch-revision-1"
        self.branch_foundation = "branch-foundation-1"
        self.source_volume_fingerprint = "volume-1"
        self.trajectory_fingerprint = "trajectory-fingerprint-1"
        self.active_trajectory_revision = "active-trajectory-revision-1"
        self.scene_object = {
            "source_name": "target-tooth", "source_role": "TargetTooth", "classification": "target_tooth",
            "source_fingerprint": "source-geometry-1", "prepared_world_fingerprint": "prepared-geometry-1",
            "outgoing_fingerprint": "outgoing-geometry-1", "jaw_transform_fingerprint": "jaw-transform-1",
            "jaw_transform_application_count": 1, "world_to_base_application_count": 1,
            "source_point_count": 20, "source_cell_count": 15, "outgoing_point_count": 20,
            "outgoing_cell_count": 15, "source_bounds_world_ras_mm": [0, 1, 0, 1, 0, 1],
            "prepared_bounds_world_ras_mm": [0, 1, 0, 1, 0, 1],
            "outgoing_bounds_base_link_mm": [0, 1, 0, 1, 0, 1], "connected_component_count": 1,
            "boundary_or_nonmanifold_edge_count": 0, "publisher_linear_scale_m_per_mm": 0.001,
            "collision_padding_mm": 0.0, "publish_status": "Published",
        }
        self.drift_on_restore = False
        self.home = None if home is None else SimpleNamespace(
            joint_names=list(home), joint_positions_si=list(home.values()), base_fingerprint="base-fp-1",
            robot_profile_fingerprint=profile, revision="home-revision-1", runtime_validation_status="Validated",
            collision_audit_fingerprint="audit-fp-1", guard_policy_fingerprint="guard-fp-1",
            validated_at_utc="2026-10-07T00:00:00Z", minimum_clearance_mm=1.0, world_object_count=1)
        self.node = Node(self)
        self.logic = self._logic()
        self.facade = self._facade()

    def view(self):
        m = self.base.matrix
        yaw = math.degrees(math.atan2(m[1, 0], m[0, 0]))
        return {"opening": self.opening, "u": round(m[0, 3] - 100.0, 6), "v": round(m[1, 3] - 200.0, 6),
                "depth": round(m[2, 3] - 300.0, 6), "yaw": round(yaw, 6)}

    def _log(self, name):
        self.calls.append(name)

    def registry_json(self):
        return json.dumps({
            "selected_branch_id": "b1",
            "prepared_branches": {"b1": {
                "state": "Current", "revision": self.branch_revision,
                "branch_foundation_fingerprint": self.branch_foundation,
                "trajectory_ids": ["traj-1"], "pairing_intent": "Single",
            }},
            "teeth": {"34": {"trajectory_set": {"slots": [{
                "trajectory_id": "traj-1", "trajectory_fingerprint": self.trajectory_fingerprint,
                "state": "Current",
            }]}}},
        })

    def _logic(self):
        w = self

        class Logic:
            def isRos2MotionControlActive(self, transform):
                return w.connected

            def evaluatePreparedBranchEligibility(self, node, branch_id=None, *, registry=None):
                if registry is None:
                    raise AssertionError("identity evaluation must use the explicitly persisted registry")
                branch_id = str(branch_id or registry.get("selected_branch_id") or "")
                branch = (registry.get("prepared_branches") or {}).get(branch_id) or {}
                if w.branch_valid(w):
                    return {"reason": "VALID", "message": "", "branch_id": branch_id, "branch": branch}
                return {"reason": "STEP5C_MISMATCH", "message": "template stale", "branch_id": branch_id, "branch": branch}

            def taskHomeRecord(self, node):
                return w.home

            def robotProfileFingerprint(self):
                return w.profile

            def step6TrajectoryRevision(self, node):
                return w.active_trajectory_revision

            def step6TaskLimitsFingerprint(self, node):
                return "task-limits-1"

            def buildCaseFoundationSnapshot(self, node):
                # Production returns an empty landmark fingerprint and no positions when no landmarks node exists.
                if w.landmarks_present:
                    landmark_positions = tuple(float(v) for v in w.landmark_points)
                    landmarks_fingerprint = fa.fingerprint_of(list(landmark_positions))
                else:
                    landmark_positions, landmarks_fingerprint = (), ""
                values = {
                    "case_identity": "case-1", "anatomy_fingerprint": "anatomy-1",
                    "source_volume_fingerprint": w.source_volume_fingerprint,
                    "source_segmentation_fingerprint": "segmentation-1",
                    "jaw_source_fingerprint": "jaw-source-1", "jaw_landmarks_fingerprint": landmarks_fingerprint,
                    "landmark_positions_ras_mm": landmark_positions,
                    "landmark_review_fingerprint": "landmark-review-1", "hinge_model_schema": "hinge-v1",
                    "jaw_configuration_fingerprint": "jaw-config-1", "robot_profile_fingerprint": w.profile,
                    "tool_identity": "dentobot_drill_tcp", "tool_fingerprint": "tool-fingerprint-1",
                    "limits_fingerprint": "limits-1", "workspace_fingerprint": "workspace-1",
                }
                if not w.full_identity:
                    values["jaw_source_fingerprint"] = ""
                return SimpleNamespace(**values)

            def collisionSceneAuditRecord(self, node):
                return SimpleNamespace(
                    status="Acknowledged", object_records=[dict(w.scene_object)],
                    base_fingerprint="base-fp-1",
                    jaw_preparation_fingerprint="jaw-preparation-1", world_to_base_fingerprint="world-to-base-1",
                    runtime_acknowledgement={"status": "Acknowledged"}, audit_fingerprint="audit-fp-1",
                )

            def confirmedTaskRecord(self, node):
                return SimpleNamespace(snapshot_fingerprint="confirmed-task-1")

            def taskHomeFreshnessIssues(self, node):
                return ("Task Home belongs to another Base pose.",) if w.home_stale else ()

            def confirmedTaskFreshnessIssues(self, node):
                return ()

            def collisionSceneAuditFreshnessIssues(self, node):
                return ()

            def _foreheadFrameFromStoredPlane(self, plane):
                return np.eye(4)

            def createOrUpdateStep6CaseJawOpening(self, node):
                w._log("opening_applied")
                if w.stale_home_on_opening:
                    w.home_stale = float(w.opening) != 40.0

            def importStep6PlanningContext(self, node):
                w._log("import_context")

            def step6CurrentBaseStrokeReachability(self, node):
                w._log("stroke")
                reachable = w.oracle(w.view()).get("stroke", True)
                return {"reachable": reachable, "first_failed_station": None if reachable else "Target"}

            def storeStep6WorkingConfiguration(self, node, record):
                w._log("store")
                w.stored.append(record)
                return dict(record)

        return Logic()

    def _facade(self):
        w = self

        class Facade:
            def jointPlanningPolicy(self):
                return dict(w.policy)

            def approachCorridorMarginSamples(self):
                return w.margin

            def setApproachCorridorMarginSamples(self, n):
                w._log("set_margin")
                w.margin = n

            def setJointPlanningPolicy(self, planner, attempts, seconds):
                w._log("policy")
                w.policy.update(planner_id=planner, planning_attempts=attempts, planning_time_sec=seconds)

            @property
            def lastMoveItSceneStatus(self):
                return w.last_scene_status

            def taskHomeValidationGap(self, node):
                if w.home_stale:
                    return "Task Home stale after trial Base/opening."
                if not w.connected:
                    return "Connect ROS + MoveIt in 6.1; Task Home validation needs the live runtime."
                return ""

            @property
            def _manual_task_home_acceptance_in_progress(self):
                return w.home_review_in_progress

            @property
            def _manual_task_home_reconciliation_in_progress(self):
                return False

            def disconnect(self, progress=None):
                w._log("disconnect")
                if w.disconnect_drops_connection:
                    w.connected = False
                return ok()

            def connect(self, *, open_motion_module=False, progress=None):
                w._log("connect")
                w.connected = True
                return ok()

            def loadRobot(self):
                w._log("load_robot")
                return ok()

            def unlockBase(self):
                w._log("unlock")
                w.locked = False
                return ok()

            def stageManualBaseReview(self, flat):
                w.staged = np.array(flat, dtype=float).reshape(4, 4)
                return ok()

            def cancelManualBaseReview(self):
                w.staged = None
                return ok()

            def acceptManualBaseReview(self):
                w._log("base_accept")
                w.base.matrix = w.staged
                w.locked = True
                is_saved = np.allclose(w.base.matrix, SAVED_BASE, atol=1e-9)
                if is_saved:
                    w.home_stale = False
                    if w.drift_on_restore:
                        w.base.matrix[0, 3] += 0.05
                elif w.stale_home_on_base_change:
                    w.home_stale = True
                return ok()

            def cancelManualTaskHomeReview(self):
                w._log("home_cancel")
                return ok()

            def stageManualTaskHomeReview(self, joints):
                w._log("home_stage")
                return ok()

            def acceptManualTaskHomeReview(self):
                w._log("home_accept")
                return ok()

            def confirmTask(self):
                w._log("confirm")
                return ok()

            def ensureMoveItSceneMatches(self):
                w._log("scene_match")
                return {"state": "matched", "message": "", "comparison": {
                    "expected_count": 1, "matches": True, "summary": "All test objects match."}}

            def checkPlanningStage(self, phase_id):
                w._log("diagnose_" + str(phase_id).lower())
                oracle = w.oracle(w.view())
                verdict = oracle.get("diagnose_" + str(phase_id), "passed")
                status = "passed" if verdict in (True, "passed", "PASS") else "blocked"
                outcome = {"diagnostic_status": status, "reason": "test stage " + status}
                if phase_id == "P3" and oracle.get("diagnose") == "WARNING":
                    outcome["endpoint_evidence"] = {"plan": {"drilling_truncation": {
                        "completed_depth_mm": 4.0, "requested_depth_mm": 5.0, "remaining_depth_mm": 1.0,
                        "blocking_pair": [],
                    }}}
                return ok(payload=outcome)

            def _frame_check_states(self):
                w._log("diagnose_frame_states")
                return ["entry"]

            def frameConsistency(self, states):
                w._log("diagnose_frame_consistency")
                return {"matches": True, "summary": "Frames match.",
                        "rows": [{"state": "entry", "status": "PASS"}]}

            def checkManualRobotDraftState(self, positions, **kwargs):
                w._log("manual_robot_draft")
                return ok()

            def clearTransientState(self):
                w._log("clear")

            def invalidateMotionPlan(self):
                pass

            def checkPreEntryIK(self, *, progress=None):
                w._log("preentry")
                if not w.oracle(w.view()).get("preentry", True):
                    failed = {"candidate_index": 0, "static_state_validity_status": "Invalid",
                              "endpoint_check_status": "Failed", "collision_pairs": []}
                    return SimpleNamespace(success=True, code="x", message="", details={"diagnosticStatus": "NoIk"},
                                           payload=SimpleNamespace(to_dict=lambda: {"candidate_records": [failed]}))
                return ok(details={"diagnosticStatus": "EndpointChecksPassed"}, payload=Payload())

            def checkApproachCorridorClearance(self):
                w._log("corridor")
                if not w.oracle(w.view()).get("corridor", True):
                    return fail("approach_corridor_blocked", "blocked",
                                details={"corridor_mm": 0.2, "minimum_mm": 1.0, "validity_authoritative": True})
                return ok(details={"corridor_mm": 3.0, "minimum_mm": 1.0, "validity_authoritative": True})

            def diagnoseBase(self, *, progress=None):
                w._log("diagnose")
                raise AssertionError("service must run one existing Diagnose row per tick")

        return Facade()


def session(world, tmp_path, **kwargs):
    kwargs.setdefault("limits", SMALL)
    kwargs.setdefault("target_fdi", "34")
    s = svc.FeasibilityAdvisorSession(world.logic, world.facade, world.node, tmp_path / "run", **kwargs)
    return s


def drive(s, *, approve=(), decline=(), max_steps=100000, on_step=None):
    """Drive like the QTimer does: one step() per call; answer gates; return the events."""
    events = []
    for _ in range(max_steps):
        event = s.step()
        events.append(event)
        if event.kind == "gate":
            (s.approve_stage if event.stage in approve else s.decline_stage)(event.stage)
        if on_step:
            on_step(s, event)
        if s.finished:
            return events
    raise AssertionError("session did not finish")


# ---------------------------------------------------------------------------
def test_baseline_pass_stops_restores_and_stages_without_storing(tmp_path):
    world = World()
    s = session(world, tmp_path)
    issues = s.prepare()
    assert issues == [] or all(i.severity == "advisory" for i in issues)
    events = drive(s)
    assert s.outcome == svc.FOUND and s.finished
    assert [r["stage"] for r in s.records] == ["baseline"] and s.records[0]["result"] == fa.PASSED
    assert s.best_candidate() is s.records[0] or s.best_candidate()["state_key"] == s.records[0]["state_key"]
    assert "store" not in world.calls  # staged, never applied or saved
    assert "temporarily applied" in s.message and "saved to the branch" in s.message
    assert any(e.kind == "restore" for e in events)
    assert (tmp_path / "run" / "advisor-ordered-report.md").exists()


def test_candidates_follow_the_agreed_order_with_yaw_last_and_a_bounded_opening_grid(tmp_path):
    world = World(oracle=lambda v: {"stroke": False})
    s = session(world, tmp_path, stop_after_first_pass=True)
    s.prepare()
    drive(s, approve=("lip_variant", "opening", "base_yaw"))
    assert s.outcome == svc.EXHAUSTED
    stages = []
    for record in s.records:
        if not stages or stages[-1] != record["stage"]:
            stages.append(record["stage"])
    assert stages == ["baseline", "base_lateral", "base_lateral_vertical", "lip_variant", "opening", "base_depth", "base_yaw"]
    assert s.records[-1]["stage"] == "base_yaw"
    openings = sorted({r["state"][fa.MOUTH_OPENING_MM] for r in s.records if r["stage"] == "opening"})
    assert openings == [40.5, 41.0]
    assert all(o <= 46.0 and abs(o / 0.5 - round(o / 0.5)) < 1e-9 for o in openings)
    assert all(abs(r["state"][fa.BASE_YAW_DEG]) <= SMALL.max_yaw_deg for r in s.records)
    # the unrestricted default limits never leave 46 mm / 0.5 mm either
    states = [st for stage, st in fa.ordered_candidates(fa.baseline_state(40.06)) if stage == "opening"]
    assert max(st[fa.MOUTH_OPENING_MM] for st in states) == 46.0
    assert min(st[fa.MOUTH_OPENING_MM] for st in states) == 40.5


def test_sensitive_stages_never_start_without_explicit_approval(tmp_path):
    world = World(oracle=lambda v: {"stroke": False})
    s = session(world, tmp_path)
    s.prepare()
    seen_openings, gates = [], []

    def watch(sess, event):
        if event.kind == "gate":
            gates.append(event.stage)
        seen_openings.append(world.opening)

    drive(s, approve=(), decline=("opening", "base_yaw"), on_step=watch)
    assert gates == ["opening", "base_yaw"]
    assert max(seen_openings) == 40.0  # the opening was never changed without approval
    assert not any(r["stage"] in ("opening", "base_yaw") for r in s.records)
    assert all(abs(r["state"][fa.BASE_YAW_DEG]) == 0 for r in s.records)
    assert [g["answer"] for g in s.gate_log] == ["declined", "declined"]
    assert (tmp_path / "run" / "review-gates.json").exists()


def test_cancel_while_waiting_for_a_review_gate_starts_restore(tmp_path):
    world = World(oracle=lambda v: {"stroke": False})
    s = session(world, tmp_path)
    s.prepare()
    for _ in range(1000):
        event = s.step()
        if event.kind == "gate":
            break
    assert event.stage == "opening" and s.phase == svc.AWAITING_APPROVAL
    calls_before = list(world.calls)
    s.cancel()
    assert s.step().kind == "restore"
    drive(s)
    assert s.outcome == svc.CANCELLED and s.finished
    assert world.calls.count("opening_applied") == calls_before.count("opening_applied")


def test_connection_and_task_home_owners_are_never_called_automatically(tmp_path):
    world = World()
    wrapper_calls = []
    s = session(world, tmp_path, connect_wrapper=lambda call: wrapper_calls.append(call))
    s.prepare()
    drive(s)
    assert not wrapper_calls
    assert "connect" not in world.calls
    assert not {"home_cancel", "home_stage", "home_accept", "manual_robot_draft"}.intersection(world.calls)

    disconnected = World()
    disconnected.connected = False
    wrapper_calls.clear()
    blocked = session(disconnected, tmp_path / "offline", connect_wrapper=lambda call: wrapper_calls.append(call))
    issues = blocked.prepare()
    assert blocked.outcome == svc.BLOCKED and any("not connected" in issue.message for issue in issues)
    assert not wrapper_calls and "connect" not in disconnected.calls


def test_opening_disconnect_requires_production_connect_before_any_more_checks(tmp_path):
    world = World(oracle=lambda v: {"stroke": False}, disconnect_drops_connection=True)
    wrapper_calls = []
    s = session(world, tmp_path, connect_wrapper=lambda call: wrapper_calls.append(call))
    assert s.prepare() == []
    drive(s, approve=("opening",), decline=("base_yaw",))

    assert s.outcome == svc.BLOCKED and s.finished
    record = next(row for row in s.records if row["stage"] == "opening")
    assert record["failed_step"] == "apply_opening" and record["operator_review_required"]
    assert "explicit production Connect action in 6.1" in record["reason"]
    disconnect_index = world.calls.index("disconnect")
    assert not {"stroke", "preentry", "corridor", "diagnose", "planning_stage"}.intersection(
        world.calls[disconnect_index + 1:]
    )
    assert "connect" not in world.calls and not wrapper_calls
    assert s.restore_issues  # Task Home validation cannot be reused while ROS/MoveIt is disconnected.
    with pytest.raises(PermissionError, match="restoration is incomplete"):
        s.apply_and_save()


def test_preexisting_task_home_review_is_preserved_and_blocks_setup(tmp_path):
    world = World()
    world.home_review_in_progress = True
    s = session(world, tmp_path)
    issues = s.prepare()
    assert s.outcome == svc.BLOCKED
    assert any("already in progress" in issue.message for issue in issues)
    assert not {"home_cancel", "home_stage", "home_accept"}.intersection(world.calls)


def test_captured_nonzero_guard_margin_is_immutable_through_trial_and_restore(tmp_path):
    world = World()
    world.margin = 3
    s = session(world, tmp_path)
    s.prepare()
    assert s.baseline[fa.CORRIDOR_MARGIN_SAMPLES] == 3
    drive(s)
    assert world.margin == 3 and "set_margin" not in world.calls
    assert not s.restore_issues


def test_guard_setting_change_between_ticks_stops_before_the_next_trial_mutation(tmp_path):
    world = World()
    s = session(world, tmp_path)
    s.prepare()
    event = s.step()  # starts the baseline candidate
    assert event.kind == "started"
    event = s.step()  # apply opening, unchanged
    assert event.step == "apply_opening"
    world.margin = 4
    event = s.step()  # must refuse before Base is changed
    assert event.kind == "candidate" and event.record["operator_review_required"]
    assert "guard setting changed" in event.record["reason"]
    assert "base_accept" not in world.calls
    drive(s)
    assert s.restore_issues and np.allclose(world.base.matrix, SAVED_BASE)


def test_stale_home_after_base_trial_stops_for_explicit_62_review_without_accepting_home(tmp_path):
    world = World(oracle=lambda v: {"stroke": False}, stale_home_on_base_change=True)
    original_home = world.home
    s = session(world, tmp_path)
    s.prepare()
    drive(s, decline=("opening", "base_yaw"))
    assert s.outcome == svc.BLOCKED and s.finished
    assert len(s.records) == 2
    record = s.records[-1]
    assert record["operator_review_required"] and record["failed_step"] == "apply_base"
    assert "6.2 operator review" in record["reason"]
    assert world.home is original_home
    assert not {"home_cancel", "home_stage", "home_accept", "manual_robot_draft"}.intersection(world.calls)
    assert np.allclose(world.base.matrix, SAVED_BASE) and not world.home_stale
    with pytest.raises(PermissionError, match="operator review"):
        s.apply_and_save()


def test_current_home_allows_base_candidate_evaluation_without_any_home_write(tmp_path):
    world = World(oracle=lambda v: {"stroke": False})
    s = session(world, tmp_path)
    s.prepare()
    for _ in range(500):
        event = s.step()
        if event.kind == "candidate" and event.stage == "base_lateral":
            break
    assert event.kind == "candidate" and event.record["failed_step"] == "stroke_reach"
    assert not event.record.get("operator_review_required")
    assert not {"home_cancel", "home_stage", "home_accept", "manual_robot_draft"}.intersection(world.calls)


def test_a_gate_holds_the_search_until_answered_and_approval_unlocks_only_that_stage(tmp_path):
    world = World(oracle=lambda v: {"stroke": False})
    s = session(world, tmp_path)
    s.prepare()
    for _ in range(100000):
        event = s.step()
        if event.kind == "gate":
            break
    assert s.phase == svc.AWAITING_APPROVAL and event.stage == "opening"
    before = len(s.records)
    assert s.step().kind == "gate" and s.step().kind == "gate" and len(s.records) == before
    s.approve_stage("opening")
    event = s.step()
    assert event.kind == "started" and event.stage == "opening"
    assert s.pending_gate == ""
    # yaw still needs its own approval
    seen = set()
    for _ in range(100000):
        event = s.step()
        seen.add(event.stage)
        if event.kind == "gate":
            assert event.stage == "base_yaw"
            break
    assert "base_yaw" not in {r["stage"] for r in s.records}


def test_lip_variants_are_listed_for_operator_review_not_evaluated(tmp_path):
    world = World(oracle=lambda v: {"stroke": False})
    s = session(world, tmp_path)
    s.prepare()
    drive(s, decline=("opening", "base_yaw"))
    lip = [r for r in s.records if r["stage"] == "lip_variant"]
    assert len(lip) == len(fa.LIP_VARIANTS)
    assert all(r["result"] == fa.UNTESTED and "operator review" in r["reason"] for r in lip)
    assert [g for g in s.gate_log if g["stage"] == "lip_variant"] == []  # nothing evaluated, nothing to approve


def test_cancel_takes_effect_between_steps_and_restores_the_original_state(tmp_path):
    world = World(oracle=lambda v: {"corridor": False})
    s = session(world, tmp_path)
    s.prepare()
    for _ in range(1000):
        event = s.step()
        if event.kind == "step" and event.index == 2 and event.step == "apply_base":
            break
    assert not np.allclose(world.base.matrix, SAVED_BASE)  # candidate 2 moved the Base
    s.cancel()
    assert s.step().kind == "restore"  # the cancel is honoured at the next step, before any evaluation
    drive(s)
    assert s.outcome == svc.CANCELLED and s.finished and s._current is None
    assert np.allclose(world.base.matrix, SAVED_BASE) and world.opening == 40.0
    assert [r["stage"] for r in s.records] == ["baseline"]  # the interrupted candidate has no result


def test_cancel_between_substeps_runs_no_further_evaluation_calls(tmp_path):
    world = World()
    s = session(world, tmp_path, stop_after_first_pass=False)
    s.prepare()
    # baseline is candidate 1; run its steps until PreEntry has been requested, then cancel
    for _ in range(100):
        event = s.step()
        if event.kind == "step" and event.step == "preentry":
            break
    s.cancel()
    seen = list(world.calls)
    drive(s)
    assert s.outcome == svc.CANCELLED
    for forbidden in ("corridor", "diagnose"):
        assert forbidden not in world.calls[len(seen):]
    assert len(s.records) == 0  # the interrupted candidate is not recorded as a result
    assert world.opening == 40.0 and np.allclose(world.base.matrix, SAVED_BASE)


def test_restore_returns_opening_base_and_policy_to_the_original_after_the_search(tmp_path):
    world = World(oracle=lambda v: {"stroke": v["opening"] >= 41.0 and v["u"] == 10.0})
    world.policy.update(planning_attempts=8, planning_time_sec=9.0)
    s = session(world, tmp_path)
    s.prepare()
    drive(s, approve=("opening",), decline=("base_yaw",))
    assert s.outcome == svc.FOUND
    assert world.opening == 40.0
    assert np.allclose(world.base.matrix, SAVED_BASE)
    assert world.policy["planning_attempts"] == 8 and world.policy["planning_time_sec"] == 9.0
    assert s.restore_issues == []
    best = s.best_candidate()
    assert best["state"][fa.MOUTH_OPENING_MM] == 41.0 and best["state"][fa.BASE_U_MM] == 10.0
    assert svc.sensitive_items(best) == ["mouth opening"]
    assert "store" not in world.calls


def test_restore_measures_actual_base_drift_and_blocks_apply_and_save(tmp_path):
    world = World(oracle=lambda v: {"corridor": False})
    world.drift_on_restore = True
    s = session(world, tmp_path)
    s.prepare()
    drive(s, decline=("opening", "base_yaw"))
    assert s.finished and s.restore_issues
    assert not np.allclose(world.base.matrix, SAVED_BASE)
    assert any("restored Base differs" in issue for issue in s.restore_issues)
    assert "could NOT be fully restored" in s.message
    with pytest.raises(PermissionError, match="restoration is incomplete"):
        s.apply_and_save()


def test_stop_at_first_failing_step_for_each_candidate(tmp_path):
    def oracle(view):
        if view["u"] == 5.0 or view["u"] == -5.0:
            return {"stroke": False}
        if view["u"] == 10.0:
            return {"preentry": False}
        if view["u"] == -10.0:
            return {"corridor": False}
        return {"stroke": False}

    world = World(oracle=oracle)
    s = session(world, tmp_path)
    s.prepare()
    drive(s, decline=("opening", "base_yaw"))
    by_u = {r["state"][fa.BASE_U_MM]: r for r in s.records if r["stage"] == "base_lateral"}
    assert by_u[10.0]["failed_step"] == "preentry" and by_u[10.0]["result"] == fa.UNREACHABLE
    assert by_u[-10.0]["failed_step"] == "corridor" and by_u[-10.0]["result"] == fa.ROUTE_FAILURE
    assert by_u[10.0]["steps"].keys() == {"prerequisites", "stroke_reach", "preentry"}
    assert by_u[-10.0]["steps"].keys() == {"prerequisites", "stroke_reach", "preentry", "corridor"}
    assert by_u[5.0]["failed_step"] == "stroke_reach" and set(by_u[5.0]["steps"]) == {"prerequisites", "stroke_reach"}
    # the expensive full Diagnose only ran for candidates that passed every read-only screen
    diagnosed = [r for r in s.records if "diagnose" in r["steps"]]
    assert all(set(r["steps"]) == set(fa.EVALUATION_STEPS) for r in diagnosed)


def test_full_diagnose_runs_last_and_a_warning_never_outranks_a_pass(tmp_path):
    world = World(oracle=lambda v: {"diagnose": "WARNING"} if v["u"] == 0 else {"stroke": v["u"] == 5.0})
    s = session(world, tmp_path, stop_after_first_pass=False)
    s.prepare()
    for _ in range(100000):
        event = s.step()
        if event.kind == "gate":
            break
        if s.finished:
            break
        if len(s.records) >= 4:
            break
    ranked = s.ranked()
    assert ranked[0]["result"] == fa.PASSED and ranked[0]["change"] == {fa.BASE_U_MM: 5.0}
    baseline = next(r for r in ranked if r["change_text"] == "baseline")
    assert baseline["result"] == fa.WARNING_RESULT and baseline["rank"] > ranked[0]["rank"]
    assert svc.WARNING_REVIEW_ITEM in baseline["review_items"]
    # WARNING record in the order list: diagnose happened after the screens
    steps = list(next(r for r in s.records if r["stage"] == "baseline")["steps"])
    assert steps == ["prerequisites", "stroke_reach", "preentry", "corridor", "diagnose"]


def test_diagnose_runs_ordered_rows_one_per_tick_and_stops_at_first_failure(tmp_path):
    world = World(oracle=lambda v: {"diagnose_P2": "blocked"})
    s = session(world, tmp_path, stop_after_first_pass=False)
    s.prepare()
    diagnose_events = []
    for _ in range(100):
        event = s.step()
        if event.step.startswith("diagnose"):
            diagnose_events.append(event.step)
        if event.kind == "candidate" and event.stage == "baseline":
            break
    assert diagnose_events == [
        "diagnose:scene_match", "diagnose:stroke_reach", "diagnose:preentry_endpoint",
        "diagnose:p1_route", "diagnose:p2_entry",
    ]
    record = next(r for r in s.records if r["stage"] == "baseline")
    rows = record["steps"]["diagnose"]["raw"]["rows"]
    by_check = {row["check"]: row["status"] for row in rows}
    assert by_check["p2_entry"] == "FAIL" and by_check["p3_drilling"] == "NOT RUN"
    assert "diagnose_p3" not in world.calls and "diagnose_frame_states" not in world.calls
    assert "diagnose" not in world.calls  # the aggregate facade method was never used


def test_cancel_between_diagnose_rows_runs_no_later_native_check(tmp_path):
    # This verifies service-tick call boundaries only; it makes no claim about
    # interrupting or keeping the UI responsive inside a native check.
    world = World()
    s = session(world, tmp_path, stop_after_first_pass=False)
    s.prepare()
    for _ in range(100):
        event = s.step()
        if event.step == "diagnose:scene_match":
            break
    assert event.step == "diagnose:scene_match"
    before = list(world.calls)
    s.cancel()
    assert s.step().kind == "restore"
    drive(s)
    assert s.outcome == svc.CANCELLED
    assert len([name for name in world.calls if name == "stroke"]) == before.count("stroke")
    assert "diagnose_p1" not in world.calls and "diagnose_p2" not in world.calls


def test_no_auto_apply_store_only_through_apply_and_save_with_acknowledgements(tmp_path):
    world = World(oracle=lambda v: {"stroke": v["opening"] >= 40.5})
    s = session(world, tmp_path)
    s.prepare()
    with pytest.raises(PermissionError):
        s.apply_and_save()  # still running
    drive(s, approve=("opening",), decline=("base_yaw",))
    assert "store" not in world.calls
    best = s.best_candidate()
    assert best["state"][fa.MOUTH_OPENING_MM] == 40.5
    with pytest.raises(PermissionError, match="mouth opening"):
        s.apply_and_save()
    with pytest.raises(PermissionError):
        s.apply_and_save(acknowledged=["Base yaw"])
    assert world.calls.count("store") == 0
    saved = s.apply_and_save(acknowledged=["mouth opening"])
    assert world.calls.count("store") == 1
    config = world.stored[0]
    assert config["mouth_opening_mm"] == 40.5 and config["task_home_si"] == HOME
    assert config["base_world_mm"][0][3] == 100.0 and config["allow_spindle_guide_contact"] is False
    assert saved["mouth_opening_mm"] == 40.5


def test_an_engineering_only_pass_needs_no_acknowledgement_but_a_warning_does(tmp_path):
    world = World(oracle=lambda v: {"diagnose": "WARNING"})
    s = session(world, tmp_path)
    s.prepare()
    drive(s)
    assert s.records[0]["result"] == fa.WARNING_RESULT
    assert s.required_acknowledgements() == [svc.WARNING_REVIEW_ITEM]
    with pytest.raises(PermissionError):
        s.apply_and_save()
    s.apply_and_save(acknowledged=[svc.WARNING_REVIEW_ITEM])
    assert world.calls.count("store") == 1

    world = World()
    s = session(world, tmp_path / "plain")
    s.prepare()
    drive(s)
    assert s.required_acknowledgements() == []
    s.apply_and_save()
    assert world.calls.count("store") == 1


def test_apply_and_save_refuses_a_stale_branch(tmp_path):
    world = World()
    s = session(world, tmp_path)
    s.prepare()
    drive(s)
    world.branch_valid = lambda w: False
    with pytest.raises(PermissionError, match="input identity"):
        s.apply_and_save()


def test_a_branch_needing_a_rebuild_is_reported_for_operator_review_and_never_built(tmp_path):
    world = World(oracle=lambda v: {"stroke": False}, branch_valid=lambda w: w.opening == 40.0)
    s = session(world, tmp_path)
    s.prepare()
    drive(s, approve=("opening",), decline=("base_yaw",))
    rebuild = [r for r in s.records if r.get("failed_step") == "apply_opening"]
    assert [r["state"][fa.MOUTH_OPENING_MM] for r in rebuild] == [40.5]
    assert rebuild[0]["result"] == fa.SETUP_ERROR and rebuild[0].get("operator_review_required")
    assert "operator review" in rebuild[0]["reason"]
    assert s.outcome == svc.BLOCKED  # stop after the first stale branch candidate
    assert world.opening == 40.0  # restored
    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert "build_branch" not in source and "rebuild_branch" not in source


def test_checkpoint_reuse_only_on_an_exact_identity_match(tmp_path):
    oracle = lambda v: {"stroke": False}  # noqa: E731
    world = World(oracle=oracle)
    first = session(world, tmp_path)
    first.prepare()
    drive(first, decline=("opening", "base_yaw"))
    assert first.records and not any(r.get("reused_from") for r in first.records)

    again = World(oracle=oracle)
    second = svc.FeasibilityAdvisorSession(again.logic, again.facade, again.node, tmp_path / "run", limits=SMALL,
                                           target_fdi="34")
    second.prepare()
    event = second.next_candidate()
    assert event.kind == "reused" and len(second.records) == 1
    assert "stroke" not in again.calls  # baseline alone is reusable before transient trial changes

    other = World(oracle=oracle, profile="profile-2")  # robot profile changed: identity differs
    third = svc.FeasibilityAdvisorSession(other.logic, other.facade, other.node, tmp_path / "run", limits=SMALL,
                                          target_fdi="34")
    third.prepare()
    event = third.next_candidate()
    assert event.kind == "started" and not any(r.get("reused_from") for r in third.records)
    assert "stroke" not in other.calls  # the changed baseline was started fresh, not cached


@pytest.mark.parametrize("mutation", ["branch_revision", "trajectory_fingerprint", "scene", "source_geometry"])
def test_changed_baseline_inputs_refuse_checkpoint_reuse_before_trial(mutation, tmp_path):
    world = World()
    s = session(world, tmp_path)
    s.prepare()
    if mutation == "branch_revision":
        world.branch_revision = "branch-revision-2"  # branch ID remains b1
    elif mutation == "trajectory_fingerprint":
        world.trajectory_fingerprint = "trajectory-fingerprint-2"  # same branch ID and trajectory ID
    elif mutation == "scene":
        world.scene_object["outgoing_fingerprint"] = "outgoing-geometry-2"
    else:
        world.source_volume_fingerprint = "volume-2"
    event = s.next_candidate()
    assert event.kind == "blocked" and s.outcome == svc.BLOCKED
    assert not s.records and "stroke" not in world.calls and "base_accept" not in world.calls


def test_incomplete_identity_is_session_only_and_disables_apply_and_save(tmp_path):
    world = World(full_identity=False)
    s = session(world, tmp_path)
    s.prepare()
    assert not s._identity_available and s._base_identity["reuse_scope"] == "session_only"
    drive(s)
    assert s.best_candidate() is not None
    with pytest.raises(PermissionError, match="identity"):
        s.apply_and_save()


def test_setup_errors_are_never_checkpointed_or_reused(tmp_path):
    class BrokenWorld(World):
        pass

    world = World()
    world.facade.confirmTask = lambda: fail("task_home_runtime_validation_required", "Home not validated")
    s = session(world, tmp_path)
    s.prepare()
    drive(s)
    assert s.outcome == svc.BLOCKED  # the baseline itself is a setup error: stop, do not search
    assert s.records[0]["result"] == fa.SETUP_ERROR and len(s.records) == 1
    store = fa.CheckpointStore(tmp_path / "run" / "advisor-checkpoints.jsonl")
    assert store.lookup(s.records[0]["state"], {**s._base_identity, "state": fa.state_key(s.records[0]["state"])}) is None
    assert "Task was not confirmed" in s.records[0]["reason"] or "stale" in s.records[0]["reason"] or "Task" in s.records[0]["reason"]


def test_every_step_is_bounded_and_never_blocks(tmp_path):
    world = World(oracle=lambda v: {"stroke": v["u"] == 0.0 and v["v"] == 0.0 and v["opening"] > 40.5})
    s = session(world, tmp_path)
    s.prepare()
    worst = 0
    for _ in range(100000):
        before = len(world.calls)
        event = s.step()
        worst = max(worst, len(world.calls) - before)
        if event.kind == "gate":
            s.approve_stage(event.stage) if event.stage == "opening" else s.decline_stage(event.stage)
        if s.finished:
            break
    assert s.finished
    assert worst <= 8  # one apply/evaluation sub-step per call


def test_service_source_has_no_blocking_loops_sleeps_or_event_pumping_or_modal_handling():
    tree = ast.parse(SERVICE_SOURCE.read_text(encoding="utf-8"))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.While)]
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            called.add(func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", ""))
    assert called.isdisjoint({"sleep", "processEvents", "accept", "click", "exec_", "_dismiss_modals", "QTimer"})
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.partition(".")[0])
    assert imported.isdisjoint({"qt", "slicer", "ctk", "threading", "subprocess", "asyncio"})
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in ("QMessageBox", "QTimer")]


def _calls_in(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return tree, {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    }


def test_service_has_no_connect_jog_or_direct_task_home_authority_calls():
    """D1/O4 (Tarun "do it", 2026-10-08) supersedes the old no-automatic-Home rule ONLY for the explicit-consent
    search through the existing owners, which live in advisor_home.HomeRevalidator. Everything else stays forbidden."""

    package = SERVICE_SOURCE.parent
    forbidden_everywhere = {
        "connect", "saveCurrentTaskHome", "saveTaskHome", "recordTaskHomeRuntimeValidation", "checkManualRobotDraftState",
        "applyJointPositions", "setBasePose", "lockBase", "invalidateStep6TaskConfirmation",
    }
    owners = {"cancelManualTaskHomeReview", "stageManualTaskHomeReview", "acceptManualTaskHomeReview"}
    for name in ("advisor_service.py", "advisor_identity.py", "advisor_home.py"):
        tree, called = _calls_in(package / name)
        assert called.isdisjoint(forbidden_everywhere), name
        assert not {method for method in called if "jog" in method.casefold()}, name
        assert not {method for method in called
                    if "connect" in method.casefold() and not method.casefold().startswith("disconnect")}, name
        assert "diagnoseBase" not in called, name
        if name != "advisor_home.py":
            assert called.isdisjoint(owners), name  # the service itself never calls a Home owner
    tree, called = _calls_in(package / "advisor_home.py")
    assert {"stageManualTaskHomeReview", "acceptManualTaskHomeReview"} <= called  # called here, and only here
    assert "cancelManualTaskHomeReview" in (package / "advisor_home.py").read_text(encoding="utf-8")
    stores = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)}
    assert stores <= {"saved", "root", "ledger", "consecutive_rejections", "expected_identity", "info", "logic", "facade",
                      "node", "unknown_outcome"}  # never writes a Home record, validation flag or cached key
    apply_home = next(n for n in ast.walk(ast.parse(SERVICE_SOURCE.read_text(encoding="utf-8")))
                      if isinstance(n, ast.FunctionDef) and n.name == "_do_apply_home")
    home_calls = {n.func.attr for n in ast.walk(apply_home) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert home_calls == {"_require_current_home", "revalidate", "_active", "get"}


def test_the_storing_call_exists_only_inside_apply_and_save():
    tree = ast.parse(SERVICE_SOURCE.read_text(encoding="utf-8"))
    owners = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if isinstance(child, ast.Attribute) and child.attr == "storeStep6WorkingConfiguration":
                    owners.append(node.name)
    assert owners == ["apply_and_save"]


def test_unavailable_setup_is_reported_with_fix_actions_and_blocks_the_search(tmp_path):
    world = World(home=None)
    s = session(world, tmp_path)
    issues = s.prepare()
    assert s.finished and s.outcome == svc.BLOCKED
    blocking = [i for i in issues if i.severity == "blocking"]
    assert blocking and blocking[0].fix_id == "goto_6_2"
    assert s.step().kind == "done"

    world = World()
    world.node.step6PlanningContextImported = False
    issues = session(world, tmp_path / "ros").setup_report()
    assert any(i.fix_id == "disconnect" and "blocks importing" in i.message for i in issues)

    world = World(home=dict.fromkeys(HOME, 0.0))
    issues = session(world, tmp_path / "zero").setup_report()
    assert any("all zeros" in i.message for i in issues)


def test_setup_report_reads_the_moveit_scene_status_property_when_ros_is_connected(tmp_path):
    # Production lastMoveItSceneStatus is a property returning None or a dict: read it, never call it.
    cases = {"none": (None, "(not checked)"), "matched": ({"state": "matched"}, None),
             "mismatch": ({"state": "mismatch"}, "(mismatch)")}
    for name, (status, expected) in cases.items():
        world = World()
        world.last_scene_status = status
        scene = [i for i in session(world, tmp_path / name).setup_report() if "MoveIt scene" in i.message]
        if expected is None:
            assert not scene, name
        else:
            assert len(scene) == 1 and expected in scene[0].message and scene[0].fix_id == "sync_scene", name


def test_setup_issue_text_from_precondition_issues_maps_to_fix_actions():
    mapping = {text: svc.classify_setup_issue(text) for text in (
        "ROS/MoveIt runtime not connected", "Base not accepted/locked",
        "Task Home not validated: stale", "stale task confirmation: x",
        "MoveIt scene does not match Slicer (mismatch): x")}
    assert [m[0] for m in mapping.values()] == ["connect", "goto_6_1", "goto_6_2", "goto_6_3", "sync_scene"]
    assert svc.classify_setup_issue("something else") == ()


def test_default_evidence_root_follows_the_run_archive_layout():
    now = datetime(2026, 10, 8, 3, 4, 5, tzinfo=timezone.utc)
    root = svc.default_evidence_root({"DENTOBOT_RUN_ARTIFACT_ROOT": "/x/runs"}, now)
    assert root == Path("/x/runs/2026-10-08/S6-ADVISOR-GUI-01-20261008T030405Z")
    assert str(svc.default_evidence_root({}, now)).startswith("/workspace/data/dentobot-runs/2026-10-08/")


def test_ranked_table_rows_carry_change_class_failed_step_reason_and_evidence(tmp_path):
    world = World(oracle=lambda v: {"stroke": v["u"] == 5.0})
    s = session(world, tmp_path, stop_after_first_pass=False)
    s.prepare()
    for _ in range(100000):
        event = s.step()
        if event.kind == "gate" or s.finished or len(s.records) >= 5:
            break
    rows = s.ranked()
    assert rows and {"rank", "change_text", "result", "failed_step", "reason", "evidence_dir", "review_items"} <= set(rows[0])
    assert rows[0]["result"] == fa.PASSED and Path(rows[0]["evidence_dir"], "candidate.json").exists()
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))


# --- measured, not accepted: per-step durations (S6-P2-03 responsiveness evidence) -----------------------
class _Ticking:
    """Deterministic clock: every reading advances by ``step`` seconds."""

    def __init__(self, step=0.5):
        self.now, self.step = 0.0, step

    def __call__(self):
        self.now += self.step
        return self.now


def test_every_uninterruptible_step_duration_is_recorded_and_the_longest_is_reported(tmp_path):
    world = World()
    s = session(world, tmp_path, clock=_Ticking(0.5))
    s.prepare()
    drive(s)
    timings = s.records[0]["timings_sec"]
    assert {"prerequisites", "stroke_reach", "preentry", "corridor"} <= set(timings)
    assert any(key.startswith("diagnose:") for key in timings)  # one entry per Diagnose row
    assert all(value > 0 for value in timings.values())
    longest = s.longest_step()
    assert longest is not None and longest[0] == max(timings.values()) and longest[1] == 1
    report = (tmp_path / "run" / "advisor-ordered-report.md").read_text(encoding="utf-8")
    assert "Longest single uninterruptible step measured" in report and "not accepted" in report
    saved = json.loads((s.records[0]["evidence_dir"] and Path(s.records[0]["evidence_dir"]) / "candidate.json").read_text())
    assert saved["timings_sec"] == timings


def test_no_timing_means_nothing_measured_and_no_claim(tmp_path):
    world = World()
    s = session(world, tmp_path)
    assert s.longest_step() is None


# ---------------------------------------------------------------------------
# S6-ADVISOR-GUI-01 F1: the Base revision is part of the Task Home binding (sourceRevision in the Base
# fingerprint).  The shared World fake above clears staleness whenever the pose returns to the saved
# pose, so it cannot show the bug; BaseIdentityModel installs a test-only model of the production
# identity (revision, pose, lock, authority, audit and runtime-validation key) on that same World.

class BaseIdentityModel:
    ORIGINAL_REVISION = 37

    def __init__(self, world):
        self.w = world
        self.revision = self.ORIGINAL_REVISION
        self.high_water = self.ORIGINAL_REVISION  # the production mark: issued revisions never repeat
        self.status, self.source = "ProvisionalLocked", "ManualSimulationBase"
        self.authority = "ManualSimulationBaseReviewed"
        self.confirmed = True
        self.runtime_key_ok = True
        self.drift_on_reinstate = False
        self.audit_fp = self._audit_fp()
        world.home.base_fingerprint = self.fingerprint()
        world.home.collision_audit_fingerprint = self.audit_fp
        self._install()

    def pose(self):
        return tuple(round(float(v), 9) for v in self.w.base.matrix.flatten())

    def fingerprint(self):
        return fa.fingerprint_of({"pose": self.pose(), "locked": bool(self.w.locked), "status": self.status,
                                  "source": self.source, "revision": self.revision, "authority": self.authority})

    def _audit_fp(self):
        return fa.fingerprint_of({"base": self.fingerprint(), "pose": self.pose()})

    def _issue(self):
        self.revision = max(self.revision, self.high_water) + 1
        self.high_water = self.revision

    def _install(self):
        m, w = self, self.w

        def unlock():
            w._log("unlock")
            if w.locked:
                w.locked = False
                m.status, m.source, m.authority = "Unlocked", "operator-unlocked", "ManualSimulationBaseUnreviewed"
                m._issue()
                m.confirmed = False
                m.runtime_key_ok = False
            return ok()

        def accept():
            w._log("base_accept")
            w.base.matrix = np.array(w.staged, dtype=float)
            w.locked = True
            m.status, m.source, m.authority = "ProvisionalLocked", "ManualSimulationBase", "ManualSimulationBaseReviewed"
            m._issue()
            m.confirmed = False
            m.audit_fp = m._audit_fp()
            return ok()

        def snapshot():
            w._log("identity_snapshot")
            return {"matrix": [float(v) for v in w.base.matrix.flatten()], "locked": bool(w.locked),
                    "status": m.status, "source": m.source, "revision": m.revision, "authority": m.authority,
                    "case_foundation_fingerprint": "cf-1", "robot_profile_fingerprint": w.profile,
                    "placement_warning": "", "base_fingerprint": m.fingerprint(),
                    "collision_audit_json": "audit:" + m.audit_fp, "collision_audit_fingerprint": m.audit_fp,
                    "confirmed_task_fingerprint": "confirmed-task-1" if m.confirmed else "",
                    "task_home_key": "home-key-1", "runtime_task_home_key": "home-key-1" if m.runtime_key_ok else ""}

        def reinstate(snap):
            w._log("reinstate")
            if w.locked:
                unlock()  # the production unlock owner runs first; the captured binding replaces its revision
            w.base.matrix = np.array(snap["matrix"], dtype=float).reshape(4, 4)
            if m.drift_on_reinstate:
                w.base.matrix[0, 3] += 0.05
            if not np.allclose(w.base.matrix, np.array(snap["matrix"]).reshape(4, 4), atol=1e-9):
                return fail("base_identity_pose_mismatch", "the reinstated pose differs from the captured pose")
            w.locked = True
            m.status, m.source, m.authority = snap["status"], snap["source"], snap["authority"]
            m.revision = int(snap["revision"])
            m.high_water = max(m.high_water, m.revision)
            m.audit_fp = snap["collision_audit_fingerprint"]
            m.runtime_key_ok = bool(snap["runtime_task_home_key"]) and snap["task_home_key"] == "home-key-1"
            return ok()

        def gap(node=None):
            if w.logic.taskHomeFreshnessIssues(node):
                return "Task Home is stale: Task Home belongs to a different base pose."
            if not w.connected:
                return "Connect ROS + MoveIt in 6.1; Task Home validation needs the live runtime."
            if not m.runtime_key_ok:
                return "Task Home validation was cleared by a later robot action; re-validate it in 6.2."
            if m.audit_fp != w.home.collision_audit_fingerprint:
                return "The collision scene changed since Task Home was validated."
            return ""

        def confirm():
            w._log("confirm")
            if gap():
                return fail("task_home_runtime_validation_required", gap())
            m.confirmed = True
            return ok()

        w.facade.unlockBase = unlock
        w.facade.acceptManualBaseReview = accept
        w.facade.manualBaseIdentitySnapshot = snapshot
        w.facade.reinstateManualBaseIdentity = reinstate
        w.facade.taskHomeValidationGap = gap
        w.facade.confirmTask = confirm
        w.logic.robotBaseFingerprint = lambda node: m.fingerprint()
        w.logic.taskHomeFreshnessIssues = lambda node: (
            ("Task Home belongs to a different base pose.",) if m.fingerprint() != w.home.base_fingerprint else ())
        w.logic.collisionSceneAuditRecord = lambda node: SimpleNamespace(
            status="Acknowledged", object_records=[dict(w.scene_object)], base_fingerprint=m.fingerprint(),
            jaw_preparation_fingerprint="jaw-preparation-1", world_to_base_fingerprint="world-to-base-1",
            runtime_acknowledgement={"status": "Acknowledged"}, audit_fingerprint=m.audit_fp)
        w.logic.confirmedTaskRecord = lambda node: (
            SimpleNamespace(snapshot_fingerprint="confirmed-task-1") if m.confirmed else None)
        w.logic.confirmedTaskFreshnessIssues = lambda node: (
            () if m.confirmed else ("Confirm the immutable Step 6 task snapshot.",))


def test_restore_after_a_consent_off_base_trial_reinstates_the_original_base_identity(tmp_path):
    world = World(oracle=lambda v: {"stroke": False})
    model = BaseIdentityModel(world)
    original = model.fingerprint()
    s = session(world, tmp_path)
    s.prepare()
    drive(s, decline=("opening", "base_yaw"))
    trial = s.records[-1]
    assert trial["stage"] == "base_lateral" and trial["failed_step"] == "apply_base"
    assert trial["operator_review_required"]  # the consent-OFF stop for 6.2 review is unchanged
    assert s.outcome == svc.BLOCKED
    assert world.calls.count("reinstate") == 1
    assert np.allclose(world.base.matrix, SAVED_BASE, atol=1e-9)
    assert model.revision == BaseIdentityModel.ORIGINAL_REVISION and model.fingerprint() == original
    assert model.high_water == BaseIdentityModel.ORIGINAL_REVISION + 3  # trial 38, 39; reinstatement unlock 40
    assert world.logic.taskHomeFreshnessIssues(world.node) == ()
    assert world.facade.taskHomeValidationGap(world.node) == ""
    assert model.confirmed
    assert s.restore_issues == [] and "could NOT" not in s.message


def test_restore_that_does_not_land_on_the_exact_pose_leaves_home_stale_and_blocked(tmp_path):
    world = World(oracle=lambda v: {"stroke": False})
    model = BaseIdentityModel(world)
    model.drift_on_reinstate = True
    s = session(world, tmp_path)
    s.prepare()
    drive(s, decline=("opening", "base_yaw"))
    assert s.outcome == svc.BLOCKED and s.finished
    assert any(issue.startswith("apply_base: Base identity was not reinstated") for issue in s.restore_issues)
    assert "could NOT be fully restored" in s.message
    assert world.logic.taskHomeFreshnessIssues(world.node)  # never marked fresh when the pose is not exact
    assert world.facade.taskHomeValidationGap(world.node).startswith("Task Home is stale")
    assert "confirm" not in world.calls[world.calls.index("reinstate"):]  # restore stops at the failed step


def test_restore_to_a_target_that_differs_from_the_captured_pose_never_reinstates_identity(tmp_path):
    world = World(oracle=lambda v: {"stroke": False})
    model = BaseIdentityModel(world)
    s = session(world, tmp_path)
    s.prepare()
    shifted = SAVED_BASE.copy()
    shifted[0, 3] += 0.5  # the restore target is 0.5 mm away from the Base captured at search start
    s.saved_base = shifted
    drive(s, decline=("opening", "base_yaw"))
    assert "reinstate" not in world.calls
    assert s.restore_issues and s.restore_issues[0].startswith("apply_home")  # the stale Home stops restoration
    assert world.logic.taskHomeFreshnessIssues(world.node)  # Home stays stale; no identity was claimed


def test_a_normal_operator_base_edit_still_bumps_the_revision_and_stales_task_home(tmp_path):
    world = World()
    model = BaseIdentityModel(world)
    original = model.fingerprint()
    edited = SAVED_BASE.copy()
    edited[0, 3] += 3.0
    assert world.facade.unlockBase().success
    assert world.facade.stageManualBaseReview(edited.flatten().tolist()).success
    assert world.facade.acceptManualBaseReview().success
    assert model.revision == BaseIdentityModel.ORIGINAL_REVISION + 2
    assert model.fingerprint() != original
    assert world.logic.taskHomeFreshnessIssues(world.node)
    assert world.facade.taskHomeValidationGap(world.node).startswith("Task Home is stale")
    assert "reinstate" not in world.calls


def test_cancel_during_a_candidate_before_its_base_moves_leaves_the_base_identity_untouched(tmp_path):
    world = World(oracle=lambda v: {"stroke": False})
    model = BaseIdentityModel(world)
    s = session(world, tmp_path)
    s.prepare()
    for _ in range(1000):
        event = s.step()
        if event.kind == "step" and event.index == 2 and event.step == "apply_opening":
            break
    assert model.revision == BaseIdentityModel.ORIGINAL_REVISION  # the Base has not moved yet
    s.cancel()
    drive(s)
    assert s.outcome == svc.CANCELLED and s.restore_issues == []
    assert model.revision == BaseIdentityModel.ORIGINAL_REVISION
    assert "reinstate" not in world.calls and "base_accept" not in world.calls
    assert world.facade.taskHomeValidationGap(world.node) == ""


def test_next_operator_edit_after_an_exact_restore_never_reissues_a_trial_revision(tmp_path):
    world = World(oracle=lambda v: {"stroke": False})
    model = BaseIdentityModel(world)
    s = session(world, tmp_path)
    s.prepare()
    drive(s, decline=("opening", "base_yaw"))
    assert model.revision == BaseIdentityModel.ORIGINAL_REVISION and model.high_water == 40
    edited = SAVED_BASE.copy()
    edited[0, 3] += 3.0
    assert world.facade.unlockBase().success  # issues 41
    assert world.facade.stageManualBaseReview(edited.flatten().tolist()).success
    assert world.facade.acceptManualBaseReview().success  # issues 42, never a trial number
    assert model.revision == 42 and model.high_water == 42
    assert world.logic.taskHomeFreshnessIssues(world.node)  # Task Home is stale


# --- F5/F6: legacy jaw landmarks are optional for the input identity (S6-ADVISOR-GUI-01) -------------------
def test_absent_landmarks_node_gives_a_stable_available_identity_across_reopen(tmp_path):
    world = World(landmarks_present=False)
    s = session(world, tmp_path)
    s.prepare()
    assert s._identity_available and s._identity_error == ""
    first = s._capture_input_identity()
    assert first["source_environment"]["jaw_landmarks_fingerprint"] == "absent:v1"
    assert first == s._capture_input_identity()  # stable across two computations
    reopened = session(World(landmarks_present=False), tmp_path / "reopened")  # save/reopen-equivalent state
    reopened.prepare()
    assert reopened._identity_available and reopened._capture_input_identity() == first


def test_a_missing_landmark_field_is_not_the_absent_sentinel_and_still_fails_closed(tmp_path):
    world = World(landmarks_present=False)
    production_snapshot = world.logic.buildCaseFoundationSnapshot

    def snapshot_without_the_field(node):
        snapshot = production_snapshot(node)
        del snapshot.jaw_landmarks_fingerprint  # a malformed snapshot is not an explicit absence
        return snapshot

    world.logic.buildCaseFoundationSnapshot = snapshot_without_the_field
    s = session(world, tmp_path)
    s.prepare()
    assert not s._identity_available
    assert "source geometry/environment fingerprints" in s._identity_error


def test_present_landmarks_are_still_fingerprinted_and_a_moved_point_changes_identity(tmp_path):
    world = World()
    s = session(world, tmp_path)
    s.prepare()
    before = s._capture_input_identity()
    fingerprint = before["source_environment"]["jaw_landmarks_fingerprint"]
    assert fingerprint and fingerprint != "absent:v1"
    points = list(world.landmark_points)
    points[4] += 0.5  # one coordinate of the second landmark
    world.landmark_points = tuple(points)
    after = s._capture_input_identity()
    assert after["source_environment"]["jaw_landmarks_fingerprint"] not in ("", fingerprint, "absent:v1")
    assert s._identity_matches_baseline()[0] is False


def test_creating_landmarks_after_an_absent_baseline_makes_the_identity_stale(tmp_path):
    world = World(landmarks_present=False)
    s = session(world, tmp_path)
    s.prepare()
    assert s._identity_available and s._identity_matches_baseline() == (True, "")
    drive(s)
    assert s.outcome == svc.FOUND
    world.landmarks_present = True  # the operator later creates and places the legacy landmarks
    with pytest.raises(PermissionError, match="original input identity is not current"):
        s.apply_and_save()
    assert "store" not in world.calls


def test_absent_landmarks_do_not_block_setup_or_apply_and_save_for_a_stable_case(tmp_path):
    world = World(landmarks_present=False)
    s = session(world, tmp_path)
    issues = s.prepare()
    assert s.phase == svc.READY and s._identity_available
    assert not [issue for issue in issues if issue.severity != "advisory"]
    drive(s)
    assert s.outcome == svc.FOUND
    s.apply_and_save()
    assert world.calls.count("store") == 1


def test_an_identity_blocker_is_a_visible_setup_row_for_the_mode_it_blocks(tmp_path):
    world = World(full_identity=False)  # a source fingerprint is missing: identity unavailable
    s = session(world, tmp_path)
    issues = s.setup_report()
    rows = [issue for issue in issues if "safe input identity unavailable" in issue.message]
    # consent OFF: Apply & Save and checkpoint reuse only (batch category consent_apply); the search still runs
    assert len(rows) == 1 and rows[0].severity == "advisory" and rows[0].blocks == "consent_apply"
    assert "Apply & Save to branch" in rows[0].message and "source geometry/environment" in rows[0].message
    issues = s.prepare()
    assert s.phase == svc.READY and any(issue.message == rows[0].message for issue in issues)  # never "no issues"
    assert not s._identity_available


def test_an_identity_blocker_with_consent_on_blocks_the_consent_search_not_all(tmp_path):
    from dentobot_workflow import advisor_home as ah  # the approved consent wording (test-only import)
    world = World(full_identity=False)
    s = session(world, tmp_path)
    s.grant_home_revalidation_consent(ah.CONSENT_TEXT)
    rows = [issue for issue in s.setup_report() if "safe input identity unavailable" in issue.message]
    assert len(rows) == 1 and rows[0].severity == "blocking" and rows[0].blocks == "consent_apply"
    assert rows[0].blocks != "all"  # never the default: the Start without consent still runs after unticking consent


def test_the_setup_table_kind_text_follows_the_batch_blocks_category():
    source = (PYTHON / "dentobot_workflow" / "widget_step6_advisor.py").read_text(encoding="utf-8")
    assert "_ADVISOR_KIND_TEXT.get(issue.blocks" in source
    assert '"consent_apply": "Blocks consent search and Apply' in source
    assert "blocks_apply" not in source  # the retired F5 severity never reaches the table


# S6-ADVISOR-GUI-01 UI batch: F3 production planning-policy capture, F4 what each setup row blocks.
def test_search_runs_on_the_current_production_policy_not_the_default(tmp_path):
    world = World()
    world.policy["planning_time_sec"] = 10.0  # facade default: RRTConnectkConfigDefault, 5 attempts, 10.0 s
    s = session(world, tmp_path)
    s.prepare()
    assert s.baseline[fa.PLANNING_TIME_SEC] == 10.0 and s.original[fa.PLANNING_TIME_SEC] == 10.0
    assert s.baseline[fa.PLANNER_ID] == "RRTConnectkConfigDefault" and s.baseline[fa.PLANNING_ATTEMPTS] == 5
    assert s.planning_policy_source.startswith("facade ")
    assert all(state[fa.PLANNING_TIME_SEC] == 10.0 for _, state in s._candidates)
    drive(s)
    assert s.records and all(r["state"][fa.PLANNING_TIME_SEC] == 10.0 for r in s.records)
    assert s.records[0]["planning_policy"] == {"planner_id": "RRTConnectkConfigDefault", "planning_attempts": 5,
                                               "planning_time_sec": 10.0, "source": s.planning_policy_source}
    assert world.policy["planning_time_sec"] == 10.0  # restored to the captured production value
    report = (tmp_path / "run" / "advisor-ordered-report.md").read_text(encoding="utf-8")
    fixed = next(line for line in report.splitlines() if line.startswith("**Fixed:**"))
    assert "'planning_time_sec': 10.0" in fixed and "facade" in fixed and "DEFAULT_POLICY" not in fixed


def test_policy_fallback_is_used_and_recorded_only_without_a_facade_policy(tmp_path):
    world = World()

    def unavailable():
        raise RuntimeError("facade not ready")

    world.facade.jointPlanningPolicy = unavailable
    s = session(world, tmp_path)
    s.prepare()
    assert s.baseline[fa.PLANNING_TIME_SEC] == fa.DEFAULT_POLICY[fa.PLANNING_TIME_SEC] == 5.0
    assert s.planning_policy_source.startswith("fallback feasibility_advisor.DEFAULT_POLICY")
    assert "facade not ready" in s.planning_policy_source


def test_apply_and_save_persists_the_captured_policy_not_the_default(tmp_path):
    world = World(oracle=lambda v: {"stroke": v["opening"] >= 40.5})
    world.policy["planning_time_sec"] = 10.0
    s = session(world, tmp_path)
    s.prepare()
    drive(s, approve=("opening",), decline=("base_yaw",))
    s.apply_and_save(acknowledged=["mouth opening"])
    config = world.stored[0]
    assert config["planning_time_sec"] == 10.0 and config["planning_attempts"] == 5
    assert config["planner_id"] == "RRTConnectkConfigDefault"


def test_setup_rows_state_what_they_block_from_the_gate_that_reads_them(tmp_path):
    assert svc.advisory_blocks("stale task confirmation: Confirm the task") == "consent_apply"
    assert svc.advisory_blocks("MoveIt scene does not match Slicer (not checked): ") == "auto"
    assert svc.advisory_blocks("collision audit: stale") == "passes"

    world = World(home=None)
    issues = session(world, tmp_path / "blocked").setup_report()
    assert issues and all(i.blocks == "all" for i in issues if i.severity == "blocking")

    world = World()
    world.logic.confirmedTaskFreshnessIssues = lambda node: ("Confirm the immutable task again",)
    stale = [i for i in session(world, tmp_path / "stale").setup_report() if i.message.startswith("stale task confirmation")]
    assert len(stale) == 1 and stale[0].severity == "advisory" and stale[0].blocks == "consent_apply"

    world = World()
    world.last_scene_status = {"state": "mismatch"}
    scene = [i for i in session(world, tmp_path / "scene").setup_report() if "MoveIt scene" in i.message]
    assert len(scene) == 1 and scene[0].blocks == "auto"
