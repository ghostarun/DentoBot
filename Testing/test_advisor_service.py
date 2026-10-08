"""Pure tests for the module-native feasibility search (S6-ADVISOR-GUI-01).

The session is driven with fakes for the logic, facade and parameter node; no
Slicer, ROS or MoveIt. Source-level checks assert the structural promises that
runtime fakes cannot (no blocking loops, one storing path).
"""

import ast
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

    step6CaseJawTargetGapMm = property(lambda self: self._world.opening,
                                       lambda self, v: setattr(self._world, "opening", float(v)))
    robotBaseMountLocked = property(lambda self: self._world.locked)


class World:
    """Shared fake of logic + facade + node; ``oracle`` decides each geometric check."""

    def __init__(self, *, oracle=None, opening=40.0, profile="profile-1", branch_valid=lambda w: True, home=HOME):
        self.calls = []
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
        self.home = None if home is None else SimpleNamespace(joint_names=list(home), joint_positions_si=list(home.values()))
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

    def _logic(self):
        w = self

        class Logic:
            def isRos2MotionControlActive(self, transform):
                return w.connected

            def evaluatePreparedBranchEligibility(self, node):
                if w.branch_valid(w):
                    return {"reason": "VALID", "message": "", "branch_id": "b1",
                            "branch": {"branch_foundation_fingerprint": "ff"}}
                return {"reason": "STEP5C_MISMATCH", "message": "template stale", "branch_id": "b1", "branch": {}}

            def taskHomeRecord(self, node):
                return w.home

            def robotProfileFingerprint(self):
                return w.profile

            def confirmedTaskFreshnessIssues(self, node):
                return ()

            def collisionSceneAuditFreshnessIssues(self, node):
                return ()

            def _foreheadFrameFromStoredPlane(self, plane):
                return np.eye(4)

            def createOrUpdateStep6CaseJawOpening(self, node):
                w._log("opening_applied")

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
                w.margin = n

            def setJointPlanningPolicy(self, planner, attempts, seconds):
                w._log("policy")
                w.policy.update(planner_id=planner, planning_attempts=attempts, planning_time_sec=seconds)

            def lastMoveItSceneStatus(self):
                return {"state": "matched"}

            def taskHomeValidationGap(self, node):
                return ""

            def disconnect(self, progress=None):
                w._log("disconnect")
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
                return ok()

            def cancelManualTaskHomeReview(self):
                return ok()

            def stageManualTaskHomeReview(self, joints):
                return ok()

            def acceptManualTaskHomeReview(self):
                w._log("home_accept")
                return ok()

            def confirmTask(self):
                w._log("confirm")
                return ok()

            def ensureMoveItSceneMatches(self):
                return {"state": "matched", "message": ""}

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
                status = w.oracle(w.view()).get("diagnose", "PASS")
                rows = [{"check": c, "status": "PASS"} for c in fa.DIAGNOSE_STAGE_CHECKS]
                if status == "WARNING":
                    rows[2]["status"] = "WARNING"
                summary = {"status": status, "verdict": "v", "rows": rows}
                return SimpleNamespace(success=True, code="d", message="m", details={"baseDiagnosis": summary}, payload=summary)

        return Facade()


def session(world, tmp_path, **kwargs):
    kwargs.setdefault("limits", SMALL)
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
    assert s.prepare() == [] or all(i.severity == "advisory" for i in s.prepare())
    events = drive(s)
    assert s.outcome == svc.FOUND and s.finished
    assert [r["stage"] for r in s.records] == ["baseline"] and s.records[0]["result"] == fa.PASSED
    assert s.best_candidate() is s.records[0] or s.best_candidate()["state_key"] == s.records[0]["state_key"]
    assert "store" not in world.calls  # staged, never applied or saved
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
    with pytest.raises(ValueError):
        s.apply_and_save()


def test_a_branch_needing_a_rebuild_is_reported_for_operator_review_and_never_built(tmp_path):
    world = World(oracle=lambda v: {"stroke": False}, branch_valid=lambda w: w.opening == 40.0)
    s = session(world, tmp_path)
    s.prepare()
    drive(s, approve=("opening",), decline=("base_yaw",))
    rebuild = [r for r in s.records if r.get("failed_step") == "rebuild"]
    assert [r["state"][fa.MOUTH_OPENING_MM] for r in rebuild] == [40.5, 41.0]  # one per opening, the rest skipped
    assert all(r["result"] == fa.UNTESTED and "needs rebuild - operator review" in r["reason"] for r in rebuild)
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
    evaluated = [r for r in first.records if r["result"] != fa.UNTESTED]

    again = World(oracle=oracle)
    second = svc.FeasibilityAdvisorSession(again.logic, again.facade, again.node, tmp_path / "run", limits=SMALL)
    second.prepare()
    drive(second, decline=("opening", "base_yaw"))
    reused = [r for r in second.records if r.get("reused_from")]
    assert len(reused) == len([r for r in evaluated if r["result"] != fa.SETUP_ERROR])
    assert "stroke" not in again.calls and "base_accept" not in again.calls  # nothing was re-run

    other = World(oracle=oracle, profile="profile-2")  # robot profile changed: identity differs
    third = svc.FeasibilityAdvisorSession(other.logic, other.facade, other.node, tmp_path / "run", limits=SMALL)
    third.prepare()
    drive(third, decline=("opening", "base_yaw"))
    assert not any(r.get("reused_from") for r in third.records)
    assert "stroke" in other.calls


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
