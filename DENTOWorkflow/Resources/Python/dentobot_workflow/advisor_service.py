"""Module-native feasibility search service (S6-ADVISOR-GUI-01, 2026-10-08).

Production logic for "Find Working Configuration" in Step 6.3; no widget code.
It ports the ordered search of ``Testing/step6_feasibility_advisor_runner.py``
(``OrderedAdvisorRunner``) onto the production owners (logic + facade) and makes
it **step-driven**: every call to ``step()`` (or ``next_candidate()`` /
``evaluate_step()``) performs ONE bounded unit of work and returns, so a
``qt.QTimer`` can drive it without freezing the UI and can cancel between
steps. This module has no blocking loops, no sleeps and no event pumping.

Safety contract (operator 2026-10-07 handoff, section 5):

* Cost order per candidate: apply -> prerequisites -> stroke reach -> PreEntry IK
  -> approach corridor (read-only screens) -> full Diagnose. The first failing
  evaluation step ends the candidate (``feasibility_advisor.candidate_record``).
* Clinically sensitive stages (opening, lip/barrier variants, Base yaw) never
  start before the operator explicitly approved that stage; a drilling-depth
  truncation (WARNING) is never "best" without an explicit acknowledgement.
* Candidate settings are temporarily applied to the live simulation for evaluation.
  ``apply_and_save`` is the only place that stores a branch configuration
  (``logic.storeStep6WorkingConfiguration``), and it requires the operator's
  acknowledgement of every review item.
* Search candidates temporarily change the LIVE simulation case and the original
  Step 6 state is restored when the session ends or is cancelled. Task Home stays
  untouched; if a candidate makes its existing validation stale, the search
  stops for explicit 6.2 review. An opening whose branch is no longer VALID is
  likewise stopped for operator review and never rebuilt automatically.
* No modal dialogs are dismissed or auto-answered here; failures are recorded.
* Contact allowances, guard margins, the 1 mm corridor minimum and the barrier
  are never changed (``feasibility_advisor.state_violations`` rejects them).
"""

from __future__ import annotations

import inspect
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dentobot_workflow import feasibility_advisor as fa
from dentobot_workflow import step6_working_config

TASK_ID = "S6-ADVISOR-GUI-01"
DEFAULT_ARTIFACT_ROOT = "/workspace/data/dentobot-runs"
MAX_CONSECUTIVE_SETUP_ERRORS = 3
REPORT_EVERY = 25  # the full report is rewritten every N candidates and at the end; candidate.json is per candidate

APPLY_STEPS = ("apply_barrier", "apply_opening", "apply_base", "apply_policy", "apply_home", "apply_confirm")
PLAN_STEPS = (*APPLY_STEPS, *fa.EVALUATION_STEPS)
STEP_TITLES = {
    "apply_barrier": "applying barrier variant", "apply_opening": "applying mouth opening",
    "apply_base": "applying Base", "apply_policy": "applying planning policy",
    "apply_home": "validating Task Home", "apply_confirm": "confirming task",
    "prerequisites": "checking prerequisites and scene", "stroke_reach": "checking stroke reach",
    "preentry": "checking PreEntry IK", "corridor": "checking approach corridor",
    "diagnose": "running Diagnose rows (P1-P3)",
}

# Session phases.
IDLE, READY, SEARCHING, EVALUATING, AWAITING_APPROVAL = "idle", "ready", "searching", "evaluating", "awaiting_approval"
RESTORING, DONE = "restoring", "done"
# Terminal outcomes (``outcome`` once phase == DONE).
FOUND, EXHAUSTED, CANCELLED, BLOCKED = "found", "exhausted", "cancelled", "blocked"

_RESULT_RANK = {fa.PASSED: 0, fa.WARNING_RESULT: 1, fa.ROUTE_FAILURE: 2, fa.ENDPOINT_COLLISION: 3,
                fa.UNREACHABLE: 4, fa.SETUP_ERROR: 5, fa.UNTESTED: 6}
_SENSITIVE_KEYS = {
    fa.MOUTH_OPENING_MM: "mouth opening", fa.BASE_YAW_DEG: "Base yaw",
    fa.LIP_MARGIN_MM: "lip/mouth barrier variant", fa.LIP_SLAB_MM: "lip/mouth barrier variant",
    fa.PORTAL_ENLARGE_MM: "lip/mouth barrier variant",
}
WARNING_REVIEW_ITEM = "drilling-depth truncation (WARNING)"


# ---------------------------------------------------------------------------
# Pure helpers (also used by the research runner).
def default_evidence_root(environ: Mapping | None = None, now: datetime | None = None) -> Path:
    """``<artifact root>/YYYY-MM-DD/S6-ADVISOR-GUI-01-<UTC start>`` (RUN-ARCHIVE-01 layout)."""

    environ = environ if environ is not None else {}
    base = Path(str(environ.get("DENTOBOT_RUN_ARTIFACT_ROOT") or DEFAULT_ARTIFACT_ROOT))
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return base / now.strftime("%Y-%m-%d") / f"{TASK_ID}-{now.strftime('%Y%m%dT%H%M%SZ')}"


def preentry_step(result) -> dict:
    """Classify one authoritative ``checkPreEntryIK`` result (structured v2 seeds)."""

    payload = getattr(result, "payload", None)
    to_dict = getattr(payload, "to_dict", None)
    session = to_dict() if callable(to_dict) else {}
    seeds = []
    for record in session.get("candidate_records") or ():
        seeds.append({k: record.get(k) for k in (
            "candidate_index", "seed_provenance", "route_type", "solver_success", "termination_reason",
            "collision_check_status", "collision_pairs", "best_joint_positions_si",
            "static_state_validity_status", "static_state_validity_message", "endpoint_check_status",
            "endpoint_collision_clear", "failure_classification", "position_residual_mm",
            "drilling_axis_residual_deg", "authoritative_position_residual_mm",
            "authoritative_drilling_axis_residual_deg")})
    raw = {"success": bool(result.success), "code": str(result.code), "message": str(result.message),
           "details": dict(result.details or {}), "seeds": seeds,
           "session_identity": {k: session.get(k) for k in (
               "session_fingerprint", "task_fingerprint", "base_fingerprint", "trajectory_fingerprint",
               "robot_profile_fingerprint", "collision_audit_fingerprint", "planning_parameters_fingerprint")}}
    step = fa.classify_preentry(raw)
    step["raw"] = raw
    return step


def corridor_step(result, limits: fa.OrderedLimits = fa.OrderedLimits()) -> dict:
    step = fa.classify_corridor({"success": result.success, "code": result.code, "message": result.message,
                                 "details": result.details}, limits)
    step["message"] = str(result.message)[:500]
    step["identity"] = (result.details or {}).get("identity")
    return step


def diagnose_step(result) -> dict:
    summary = result.payload if isinstance(result.payload, Mapping) else (result.details or {}).get("baseDiagnosis")
    return fa.classify_diagnosis(summary if isinstance(summary, Mapping) else {})


def sensitive_items(record: Mapping) -> list:
    """Operator-review items a candidate depends on (changed sensitive levers, WARNING)."""

    items = []
    for key in (record.get("change") or {}):
        label = _SENSITIVE_KEYS.get(key)
        if label and label not in items:
            items.append(label)
    if record.get("result") == fa.WARNING_RESULT:
        items.append(WARNING_REVIEW_ITEM)
    return items


def rank_key(record: Mapping) -> tuple:
    change = record.get("change") or {}
    stage = str(record.get("stage") or "")
    stage_index = fa.STAGE_ORDER.index(stage) if stage in fa.STAGE_ORDER else -1
    size = sum(abs(float(v)) for k, v in change.items() if isinstance(v, (int, float)) and not isinstance(v, bool))
    return (_RESULT_RANK.get(str(record.get("result")), 9), stage_index, round(size, 6), int(record.get("sequence", 0)))


def working_configuration_record(record: Mapping, saved_home: Mapping | None, original: Mapping) -> dict:
    """The Step 6 working configuration a passing candidate stands for (not stored here)."""

    observed = ((record.get("steps") or {}).get("prerequisites") or {}).get("observed") or {}
    base = observed.get("requested_base")
    if base is None:
        raise ValueError("The candidate has no recorded Base matrix.")
    state = record["state"]
    status = "advisor warning (drilling shortened)" if record.get("result") == fa.WARNING_RESULT else "advisor pass"
    return {
        "mouth_opening_mm": float(state[fa.MOUTH_OPENING_MM]),
        "base_world_mm": [list(map(float, row)) for row in base],
        "task_home_si": dict(saved_home) if saved_home else None,
        "planner_id": state[fa.PLANNER_ID], "planning_attempts": int(state[fa.PLANNING_ATTEMPTS]),
        "planning_time_sec": float(state[fa.PLANNING_TIME_SEC]),
        "corridor_margin_samples": int(state.get(fa.CORRIDOR_MARGIN_SAMPLES, 0)),
        "allow_spindle_guide_contact": bool(state.get(fa.SPINDLE_TEMPLATE_ALLOWANCE, False)),
        "barrier_tuning": {"lip_margin_mm": float(state.get(fa.LIP_MARGIN_MM, fa.DEFAULT_BARRIER[fa.LIP_MARGIN_MM])),
                           "lip_slab_mm": float(state.get(fa.LIP_SLAB_MM, fa.DEFAULT_BARRIER[fa.LIP_SLAB_MM])),
                           "portal_enlarge_mm": float(state.get(fa.PORTAL_ENLARGE_MM,
                                                                fa.DEFAULT_BARRIER[fa.PORTAL_ENLARGE_MM]))},
        "status": status, "source": "feasibility advisor (operator-approved)",
        "notes": "Change vs. baseline: " + json.dumps(record.get("change") or {}, sort_keys=True)
                 + (f"; review items: {', '.join(sensitive_items(record))}" if sensitive_items(record) else ""),
        "evidence_dir": str(record.get("evidence_dir") or ""),
        "diagnostics": {"advisor_state_key": record.get("state_key"), "identity": record.get("identity_fingerprint"),
                        "original_opening_mm": original.get(fa.MOUTH_OPENING_MM)},
    }


def classify_setup_issue(text: str) -> tuple:
    """Map a ``precondition_issues`` string to an operator fix action ``(id, label)``."""

    lowered = text.lower()
    for needle, fix in (
        ("not connected", ("connect", "Connect ROS + MoveIt (6.1)")),
        ("base not accepted", ("goto_6_1", "Go to 6.1: review and accept the Base")),
        ("accepted base differs", ("goto_6_1", "Go to 6.1: review and accept the Base")),
        ("task home", ("goto_6_2", "Go to 6.2: review and accept Task Home")),
        ("stale task confirmation", ("goto_6_3", "Go to 6.3: Confirm Task")),
        ("scene", ("sync_scene", "Sync the MoveIt planning scene (6.1)")),
        ("collision audit", ("sync_scene", "Sync the MoveIt planning scene (6.1)")),
    ):
        if needle in lowered:
            return fix
    return ()


@dataclass
class SetupIssue:
    message: str
    severity: str = "blocking"  # blocking: the search cannot start; advisory: the search applies it itself
    fix_id: str = ""
    fix_label: str = ""


@dataclass
class StepEvent:
    kind: str  # setup|gate|started|step|candidate|reused|skipped|found|restore|done|cancelled|blocked|idle
    message: str = ""
    stage: str = ""
    step: str = ""
    index: int = 0
    total: int = 0
    record: dict | None = None
    issues: list = field(default_factory=list)


@dataclass
class _Current:
    index: int
    stage: str
    state: dict
    label: str
    directory: Path
    identity: dict
    plan: list
    cursor: int = 0
    steps: dict = field(default_factory=dict)
    observed: dict = field(default_factory=dict)
    apply_failed: bool = False
    diagnosis_started: bool = False
    diagnosis_cursor: int = 0
    diagnosis_rows: list = field(default_factory=list)
    diagnosis_done: bool = False
    timings: dict = field(default_factory=dict)  # seconds per uninterruptible sub-step (responsiveness evidence)


class _HomeReviewRequired(RuntimeError):
    """A trial made saved Home validation stale; only the operator can review it."""


# ---------------------------------------------------------------------------
class FeasibilityAdvisorSession:
    """One step-driven ordered feasibility search for the active PreparedBranch."""

    def __init__(self, logic, facade, parameterNode, evidence_root, *, limits: fa.OrderedLimits = fa.OrderedLimits(),
                 target_fdi: str = "", stop_after_first_pass: bool = True,
                 opening_applier: Callable[[float], None] | None = None,
                 barrier_applier: Callable[[Mapping], None] | None = None,
                 ui_refresh: Callable[[], None] | None = None,
                 connect_wrapper: Callable[[Callable], object] | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.logic, self.facade, self.node = logic, facade, parameterNode
        self.root = Path(evidence_root)
        self.limits = limits
        self.target_fdi = str(target_fdi)
        self.stop_after_first_pass = bool(stop_after_first_pass)
        self._opening_applier = opening_applier
        if barrier_applier is None and callable(getattr(logic, "setStep6MouthBarrierTuning", None)):
            barrier_applier = self._apply_barrier_tuning  # the production parameter owner; no second store
        self._barrier_applier = barrier_applier
        self._ui_refresh = ui_refresh
        # Kept as an ignored keyword for compatibility with the first GUI draft.
        # Connect is always owned by the explicit 6.1 operator action.
        del connect_wrapper
        self._clock = clock
        self._started = clock()
        self.store = fa.CheckpointStore(self.root / "advisor-checkpoints.jsonl")
        self.records: list = []
        self.gate_log: list = []
        self.phase, self.outcome, self.message = IDLE, "", ""
        self.baseline: dict = {}
        self.original: dict = {}
        self.saved_base = None
        self.saved_home: dict | None = None
        self._saved_home_identity: dict = {}
        self.branch_id = ""
        self._base_identity: dict = {}
        self._identity_available = False
        self._identity_error = ""
        self._session_identity = fa.fingerprint_of([id(self), self._started])
        self._operator_review_block = False
        self._candidates: list = []
        self._cursor = 0
        self._current: _Current | None = None
        self._approvals: dict = {}
        self._pending_gate = ""
        self._skipped_openings: set = set()
        self._lip_evidence: list | None = None  # attributed baseline lip-slab contacts, computed at the lip stage
        self._synced_tuning: dict | None = None  # barrier tuning the audited/MoveIt scene is known to hold
        self._declined_count = 0
        self._setup_error_run = 0
        self._cancel_requested = False
        self._restore_plan: list = []
        self._restore_state: dict = {}
        self._restore_observed: dict = {}
        self.restore_issues: list = []
        self.unavailable_stages: dict = {}
        if self._barrier_applier is None:
            self.unavailable_stages["lip_variant"] = (
                "the module has no in-module barrier-variant applier; the approved lip/barrier variants are listed "
                "for operator review and are not evaluated")

    # ---- small accessors ------------------------------------------------------
    @property
    def finished(self) -> bool:
        return self.phase == DONE

    @property
    def pending_gate(self) -> str:
        return self._pending_gate

    def total_candidates(self) -> int:
        return len(self._candidates)

    def progress(self) -> dict:
        current = self._current
        step = current.plan[min(current.cursor, len(current.plan) - 1)] if current and current.plan else ""
        if current and step == "diagnose" and current.diagnosis_cursor < 7:
            from dentobot_workflow import base_diagnosis

            checks = base_diagnosis.CHECK_ORDER
            if current.diagnosis_cursor < len(checks):
                step = "diagnose · " + checks[current.diagnosis_cursor]
        return {"phase": self.phase, "stage": current.stage if current else "", "index": len(self.records),
                "total": self.total_candidates(),
                "step": step,
                "label": current.label if current else ""}

    def _ctx_matrix(self, transform_node):
        import numpy as np
        import vtk

        matrix = vtk.vtkMatrix4x4()
        transform_node.GetMatrixTransformToWorld(matrix)
        return np.array([[matrix.GetElement(r, c) for c in range(4)] for r in range(4)])

    def _persisted_registry(self) -> dict:
        """Read the saved registry directly; eligibility checks must not sync/migrate it."""

        raw = str(getattr(self.node, "step6TrajectoryRegistryJson", "") or "").strip()
        registry = json.loads(raw) if raw else {}
        if not isinstance(registry, dict):
            raise ValueError("the saved PreparedBranch registry is unavailable")
        branches = registry.get("prepared_branches")
        if not isinstance(branches, Mapping):
            raise ValueError("the saved PreparedBranch registry has no branch map")
        return registry

    @staticmethod
    def _home_record_identity(record) -> dict:
        if record is None:
            return {}
        to_dict = getattr(record, "to_dict", None)
        if callable(to_dict):
            value = to_dict()
            return dict(value) if isinstance(value, Mapping) else {}
        fields = (
            "joint_names", "joint_positions_si", "base_fingerprint", "robot_profile_fingerprint",
            "revision", "runtime_validation_status", "collision_audit_fingerprint", "guard_policy_fingerprint",
            "validated_at_utc", "minimum_clearance_mm", "world_object_count",
        )
        return {name: getattr(record, name) for name in fields if hasattr(record, name)}

    @staticmethod
    def _scene_source_identity(audit) -> dict:
        """Stable audited geometry identity, excluding MRML/runtime object IDs and timestamps."""

        rows = []
        for raw in getattr(audit, "object_records", ()) or ():
            if not isinstance(raw, Mapping):
                continue
            rows.append({key: raw.get(key) for key in (
                "source_name", "source_role", "classification", "source_fingerprint",
                "prepared_world_fingerprint", "outgoing_fingerprint", "jaw_transform_fingerprint",
                "jaw_transform_application_count", "world_to_base_application_count",
                "source_point_count", "source_cell_count", "outgoing_point_count", "outgoing_cell_count",
                "source_bounds_world_ras_mm", "prepared_bounds_world_ras_mm", "outgoing_bounds_base_link_mm",
                "connected_component_count", "boundary_or_nonmanifold_edge_count",
                "publisher_linear_scale_m_per_mm", "collision_padding_mm",
            )})
        rows.sort(key=lambda row: (str(row.get("source_role") or ""), str(row.get("source_name") or "")))
        return {"objects": rows, "fingerprint": fa.fingerprint_of(rows) if rows else ""}

    def _capture_input_identity(self) -> dict:
        """Capture current source identity using existing logic/facade records only."""

        logic, node = self.logic, self.node
        registry = self._persisted_registry()
        branch_id = str(registry.get("selected_branch_id") or "")
        branches = registry.get("prepared_branches") or {}
        branch = branches.get(branch_id) if branch_id else None
        if not isinstance(branch, Mapping) or not branch_id:
            raise ValueError("the selected PreparedBranch identity is unavailable")
        eligibility = logic.evaluatePreparedBranchEligibility(node, branch_id, registry=registry)
        if eligibility.get("reason") != "VALID":
            raise ValueError("the selected PreparedBranch is no longer VALID: "
                             + str(eligibility.get("message") or eligibility.get("reason")))
        if str(eligibility.get("branch_id") or "") != branch_id:
            raise ValueError("the selected PreparedBranch changed during identity capture")

        # This existing snapshot is read-only. Keep only source/environment fields
        # below; jaw opening and Base are candidate state and are captured separately.
        snapshot_fn = getattr(logic, "buildCaseFoundationSnapshot", None)
        if not callable(snapshot_fn):
            raise ValueError("the Case Foundation source snapshot API is unavailable")
        foundation = snapshot_fn(node)
        audit = logic.collisionSceneAuditRecord(node)
        home = logic.taskHomeRecord(node)
        confirmed = logic.confirmedTaskRecord(node)
        trajectory_ids = [str(value) for value in branch.get("trajectory_ids") or ()]
        trajectory_revisions = {}
        for tooth in (registry.get("teeth") or {}).values():
            for slot in ((tooth.get("trajectory_set") or {}).get("slots") or ()):
                trajectory_id = str(slot.get("trajectory_id") or "")
                if trajectory_id in trajectory_ids:
                    trajectory_revisions[trajectory_id] = str(slot.get("trajectory_fingerprint") or "")
        active_trajectory_revision = str(logic.step6TrajectoryRevision(node) or "")
        scene = self._scene_source_identity(audit) if audit is not None else {}
        if audit is not None:
            scene.update({
                "base_fingerprint": str(getattr(audit, "base_fingerprint", "") or ""),
                "jaw_preparation_fingerprint": str(getattr(audit, "jaw_preparation_fingerprint", "") or ""),
                "world_to_base_fingerprint": str(getattr(audit, "world_to_base_fingerprint", "") or ""),
                "runtime_acknowledgement_status": str(
                    (getattr(audit, "runtime_acknowledgement", {}) or {}).get("status") or ""
                ),
            })
            scene["fingerprint"] = fa.fingerprint_of({key: value for key, value in scene.items() if key != "fingerprint"})
        source_fields = (
            "case_identity", "anatomy_fingerprint", "source_volume_fingerprint", "source_segmentation_fingerprint",
            "jaw_source_fingerprint", "jaw_landmarks_fingerprint", "landmark_positions_ras_mm",
            "landmark_review_fingerprint", "hinge_model_schema", "jaw_configuration_fingerprint",
            "robot_profile_fingerprint", "tool_identity", "tool_fingerprint", "limits_fingerprint",
            "workspace_fingerprint",
        )
        source_environment = {
            key: (foundation.get(key) if isinstance(foundation, Mapping) else getattr(foundation, key, None))
            for key in source_fields
        }
        home_identity = self._home_record_identity(home)
        base_matrix = self._ctx_matrix(node.robotBaseTransform)
        policy = self.facade.jointPlanningPolicy()
        identity = {
            "schema": fa.ADVISOR_SCHEMA,
            "target_fdi": self.target_fdi,
            "selected_branch_id": branch_id,
            "branch_revision": str(branch.get("revision") or ""),
            "branch_foundation_fingerprint": str(branch.get("branch_foundation_fingerprint") or ""),
            "trajectory_ids": trajectory_ids,
            "trajectory_revisions": trajectory_revisions,
            "active_trajectory_revision": active_trajectory_revision,
            "source_environment": source_environment,
            "audited_scene_sources": scene,
            "collision_audit_status": str(getattr(audit, "status", "") or ""),
            "robot_profile": str(logic.robotProfileFingerprint() or ""),
            "confirmed_task_fingerprint": str(getattr(confirmed, "snapshot_fingerprint", "") or ""),
            "saved_base": fa.fingerprint_of([round(float(v), 9) for v in base_matrix.flatten()]),
            "saved_home": fa.fingerprint_of(home_identity),
            "mouth_barrier": {"edge_mode": str(getattr(node, "step6MouthBarrierEdgeMode", "") or ""),
                              "tuning": self._live_barrier_tuning()},
            "limits": fa.fingerprint_of(vars(self.limits)),
            "task_limits": str(logic.step6TaskLimitsFingerprint(node) or ""),
            "corridor_margin_samples": int(self.facade.approachCorridorMarginSamples()),
            "planning_policy": {key: policy.get(key) for key in (
                "planner_id", "planning_attempts", "planning_time_sec", "independent_replans")},
        }
        missing = []
        if not self.target_fdi:
            missing.append("active target identity")
        for key in ("branch_revision", "branch_foundation_fingerprint", "active_trajectory_revision",
                    "robot_profile", "confirmed_task_fingerprint", "saved_home", "task_limits"):
            if not identity.get(key):
                missing.append(key)
        if not home_identity:
            missing.append("saved Task Home identity")
        if not trajectory_ids or set(trajectory_revisions) != set(trajectory_ids) or not all(trajectory_revisions.values()):
            missing.append("selected branch trajectory revisions")
        if not all(source_environment.get(key) for key in (
                "case_identity", "anatomy_fingerprint", "source_volume_fingerprint", "source_segmentation_fingerprint",
                "jaw_source_fingerprint", "jaw_landmarks_fingerprint", "jaw_configuration_fingerprint",
                "tool_identity", "tool_fingerprint", "limits_fingerprint")):
            missing.append("source geometry/environment fingerprints")
        if (not scene.get("objects") or not scene.get("base_fingerprint")
                or not scene.get("jaw_preparation_fingerprint") or not scene.get("world_to_base_fingerprint")
                or not scene.get("runtime_acknowledgement_status") or not scene.get("fingerprint")
                or not identity["collision_audit_status"]):
            missing.append("audited scene geometry")
        if missing:
            raise ValueError("safe input identity unavailable: " + ", ".join(missing))
        return identity

    def _identity_matches_baseline(self) -> tuple[bool, str]:
        if not self._identity_available:
            return False, self._identity_error or "safe input identity is unavailable"
        try:
            current = self._capture_input_identity()
        except Exception as exc:
            return False, str(exc)[:300]
        if fa.fingerprint_of(current) != fa.fingerprint_of(self._base_identity):
            return False, "branch, trajectory, source geometry, Task Home, Base, limits, or audited scene changed"
        return True, ""

    def _home_currentness_issues(self) -> list:
        logic, facade, node = self.logic, self.facade, self.node
        issues = []
        if (getattr(facade, "_manual_task_home_acceptance_in_progress", False)
                or getattr(facade, "_manual_task_home_reconciliation_in_progress", False)):
            issues.append("a Task Home review or reconciliation is already in progress")
        if not self._active():
            issues.append("ROS/MoveIt is disconnected; use the explicit production Connect action in 6.1; "
                          "the advisor will not reconnect automatically")
        try:
            gap = str(facade.taskHomeValidationGap(node) or "")
        except Exception as exc:
            gap = "Task Home validation could not be checked: " + str(exc)
        if gap:
            issues.append(gap)
        freshness = getattr(logic, "taskHomeFreshnessIssues", None)
        if callable(freshness):
            try:
                issues.extend(str(item) for item in (freshness(node) or ()))
            except Exception as exc:
                issues.append("Task Home freshness could not be checked: " + str(exc))
        record = logic.taskHomeRecord(node)
        if record is None:
            issues.append("the saved Task Home is missing")
        elif fa.fingerprint_of(self._home_record_identity(record)) != fa.fingerprint_of(self._saved_home_identity):
            issues.append("the saved Task Home identity changed")
        return list(dict.fromkeys(str(issue) for issue in issues if issue))

    def _require_current_home(self, *, candidate_step: str) -> None:
        issues = self._home_currentness_issues()
        if issues:
            raise _HomeReviewRequired(
                "Task Home requires explicit 6.2 operator review after " + candidate_step + ": "
                + "; ".join(issues)[:400]
            )

    def _immutable_trial_setting_issues(self) -> list[str]:
        """Detect external changes to guard settings before every trial/check tick."""

        try:
            margin = int(self.facade.approachCorridorMarginSamples())
        except Exception as exc:
            return ["approach-corridor guard margin could not be read: " + str(exc)[:200]]
        expected_margin = int(self.original.get(fa.CORRIDOR_MARGIN_SAMPLES, margin))
        issues = []
        if margin != expected_margin:
            issues.append(f"approach-corridor guard margin changed from captured {expected_margin} to {margin}")
        allowance = bool(getattr(self.node, "step6AllowSpindleGuideContact", False))
        expected_allowance = bool(self.original.get(fa.SPINDLE_TEMPLATE_ALLOWANCE, allowance))
        if allowance != expected_allowance:
            issues.append("spindle-template contact allowance changed from its captured setting")
        return issues

    def _active(self) -> bool:
        return bool(self.logic.isRos2MotionControlActive(self.node.robotBaseTransform))

    def _refresh(self) -> None:
        if self._ui_refresh is not None:
            self._ui_refresh()

    def _write(self, directory: Path, name: str, payload) -> str:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
        return str(path)

    def _progress_file(self, text: str) -> None:
        self._write(self.root, "progress.json", {
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "elapsed_sec": round(self._clock() - self._started, 1),
            "text": text, "phase": self.phase, "evaluated": len(self.records), "total": self.total_candidates()})

    # ---- setup diagnostics (reuses precondition_issues) -------------------------
    def setup_report(self) -> list:
        """Why the search cannot start, or what it will have to fix itself, with fix actions."""

        node, logic, facade = self.node, self.logic, self.facade
        issues: list = []
        try:
            registry = self._persisted_registry()
            branch_id = str(registry.get("selected_branch_id") or "")
            branch = logic.evaluatePreparedBranchEligibility(node, branch_id, registry=registry)
        except (RuntimeError, ValueError, TypeError, KeyError) as exc:
            branch = {"reason": "UNKNOWN", "message": str(exc)}
        if branch.get("reason") != "VALID":
            issues.append(SetupIssue("The active PreparedBranch is not VALID: " + str(branch.get("message") or branch.get("reason")),
                                     fix_id="goto_6_1", fix_label="Select a valid branch / import Step 6 (6.1)"))
        try:
            self._live_barrier_tuning()
        except ValueError as exc:
            issues.append(SetupIssue("The mouth-barrier lip tuning on this case is not an approved value: " + str(exc)[:200],
                                     fix_id="goto_6_3", fix_label="Review the 6.3 mouth barrier / Restore Branch Step 6 Config"))
        ros = self._active()
        if not ros:
            issues.append(SetupIssue("ROS/MoveIt is not connected. Use the production Connect action in 6.1 before starting the advisor.",
                                     fix_id="connect", fix_label="Connect ROS + MoveIt (6.1)"))
        if not getattr(node, "step6PlanningContextImported", False):
            if ros:
                issues.append(SetupIssue("ROS is connected, which blocks importing the Step 6 planning context.",
                                         fix_id="disconnect", fix_label="Disconnect ROS (6.1), then import"))
            else:
                issues.append(SetupIssue("The Step 6 planning context is not imported.", fix_id="goto_6_1",
                                         fix_label="Import the Step 6 planning context (6.1)"))
        if not getattr(node, "robotBaseMountLocked", False):
            issues.append(SetupIssue("No accepted Base: the search needs the saved Base as its reference.",
                                     fix_id="goto_6_1", fix_label="Go to 6.1: review and accept the Base"))
        home = logic.taskHomeRecord(node)
        if home is None:
            issues.append(SetupIssue("No saved Task Home for this Base.", fix_id="goto_6_2",
                                     fix_label="Go to 6.2: review and accept Task Home"))
        elif not any(abs(float(v)) > 1e-12 for v in home.joint_positions_si):
            issues.append(SetupIssue("The saved Task Home is all zeros (not a reviewed Home).", fix_id="goto_6_2",
                                     fix_label="Go to 6.2: review and accept Task Home"))
        home_gap = str(facade.taskHomeValidationGap(node) or "")
        if home_gap:
            issues.append(SetupIssue("Task Home needs explicit 6.2 review: " + home_gap,
                                     fix_id="goto_6_2", fix_label="Go to 6.2: review and accept Task Home"))
        if (getattr(facade, "_manual_task_home_acceptance_in_progress", False)
                or getattr(facade, "_manual_task_home_reconciliation_in_progress", False)):
            issues.append(SetupIssue("A Task Home review or reconciliation is already in progress.",
                                     fix_id="goto_6_2", fix_label="Finish the current 6.2 review"))
        if bool(getattr(node, "step6AllowSpindleGuideContact", False)):
            issues.append(SetupIssue("The spindle-template contact allowance is ON; the advisor will not change it.",
                                     fix_id="goto_6_3", fix_label="Review the 6.3 contact policy"))
        scene = None
        if ros:
            status = facade.lastMoveItSceneStatus()
            scene = (status or {}).get("state")
        observed = {
            "ros_connected": ros, "base_locked": bool(getattr(node, "robotBaseMountLocked", False)),
            "base_delta_mm": 0.0, "home_gap": home_gap, "home_delta_si": 0.0,
            "task_confirmation_issues": [str(s) for s in (logic.confirmedTaskFreshnessIssues(node) or ())],
            "collision_audit_issues": [str(s) for s in (logic.collisionSceneAuditFreshnessIssues(node) or ())],
            "scene_state": scene, "scene_message": "",
        }
        covered = []
        if not ros:
            covered.append("ROS/MoveIt runtime not connected")
        if not getattr(node, "robotBaseMountLocked", False):
            covered.append("Base not accepted")
        if home is None or home_gap:
            covered.append("Task Home not validated")
        for text in fa.precondition_issues(observed, self.limits):
            if any(text.startswith(prefix) for prefix in covered):
                continue  # already reported above as a blocking issue
            fix = classify_setup_issue(text)
            severity = "blocking" if text.startswith("Task Home not validated") else "advisory"
            issues.append(SetupIssue(text, severity=severity, fix_id=fix[0] if fix else "",
                                     fix_label=fix[1] if fix else ""))
        return issues

    # ---- lifecycle --------------------------------------------------------------
    def prepare(self) -> list:
        """Capture the live state to restore, run setup diagnostics, build the candidate list."""

        node, logic, facade = self.node, self.logic, self.facade
        issues = self.setup_report()
        self.root.mkdir(parents=True, exist_ok=True)
        blocking = [i for i in issues if i.severity == "blocking"]
        if blocking:
            self.phase, self.outcome = DONE, BLOCKED
            self.message = "Setup must be fixed first: " + "; ".join(i.message for i in blocking)
            return issues
        home = logic.taskHomeRecord(node)
        policy = facade.jointPlanningPolicy()
        self.saved_base = self._ctx_matrix(node.robotBaseTransform)
        self.saved_home = dict(zip(home.joint_names, home.joint_positions_si))
        self._saved_home_identity = self._home_record_identity(home)
        registry = self._persisted_registry()
        self.branch_id = str(registry.get("selected_branch_id") or "")
        opening = float(node.step6CaseJawTargetGapMm)
        self.baseline = fa.baseline_state(opening)
        live_tuning = self._live_barrier_tuning()
        self._synced_tuning = dict(live_tuning) if live_tuning is not None else None
        if live_tuning is not None:
            self.baseline.update(live_tuning)
            if any(abs(live_tuning[k] - fa.DEFAULT_BARRIER[k]) > 1e-9 for k in fa.LIP_VARIANT_BOUNDS):
                self.unavailable_stages["lip_variant"] = (
                    "this branch already carries a non-default mouth-barrier variant; the lip stage is listed for "
                    "operator review and is not searched (the saved variant is never altered silently)")
        self.baseline[fa.CORRIDOR_MARGIN_SAMPLES] = int(facade.approachCorridorMarginSamples())
        self.baseline[fa.SPINDLE_TEMPLATE_ALLOWANCE] = bool(getattr(node, "step6AllowSpindleGuideContact", False))
        self.original = {
            fa.MOUTH_OPENING_MM: opening, fa.PLANNER_ID: policy["planner_id"],
            fa.PLANNING_ATTEMPTS: int(policy["planning_attempts"]), fa.PLANNING_TIME_SEC: float(policy["planning_time_sec"]),
            fa.CORRIDOR_MARGIN_SAMPLES: int(facade.approachCorridorMarginSamples()),
            fa.SPINDLE_TEMPLATE_ALLOWANCE: bool(getattr(node, "step6AllowSpindleGuideContact", False)),
            **(live_tuning or {}),
        }
        self._restore_state = {**self.baseline, **self.original}
        try:
            self._base_identity = self._capture_input_identity()
            self._identity_available = True
        except Exception as exc:
            self._base_identity = {
                "schema": fa.ADVISOR_SCHEMA, "reuse_scope": "session_only",
                "session_identity": self._session_identity,
            }
            self._identity_available = False
            self._identity_error = str(exc)[:300]
        self._candidates = [("baseline", dict(self.baseline)), *fa.ordered_candidates(self.baseline, self.limits)]
        self.phase = READY
        self.message = f"Ready: {len(self._candidates)} candidate states in the approved order."
        if not self._identity_available:
            self.message += " Checkpoint reuse and Apply & Save are disabled because a complete input identity is unavailable."
        return issues

    def cancel(self) -> None:
        """Request cancellation; takes effect at the next ``step()`` (never mid-step)."""

        if self.phase not in (DONE, RESTORING):
            self._cancel_requested = True

    def approve_stage(self, stage: str) -> None:
        self._approvals[stage] = "approved"
        self.gate_log.append({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stage": stage, "answer": "approved"})
        if self._pending_gate == stage:
            self._pending_gate = ""
            self.phase = SEARCHING
        self._write(self.root, "review-gates.json", self.gate_log)

    def decline_stage(self, stage: str) -> None:
        self._approvals[stage] = "declined"
        self.gate_log.append({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stage": stage, "answer": "declined"})
        if self._pending_gate == stage:
            self._pending_gate = ""
            self.phase = SEARCHING
        self._write(self.root, "review-gates.json", self.gate_log)

    # ---- the single driver entry point ------------------------------------------
    def step(self) -> StepEvent:
        """One unit of work: choose the next candidate, run one sub-step, or restore one step."""

        if self.phase == IDLE:
            return StepEvent("idle", "Call prepare() first.")
        if self.phase == DONE:
            return StepEvent("done", self.message)
        if self._cancel_requested and self.phase != RESTORING:
            return self._begin_restore(CANCELLED, "Cancelled by the operator.")
        if self.phase == AWAITING_APPROVAL:
            return StepEvent("gate", self._gate_message(self._pending_gate), stage=self._pending_gate)
        if self.phase == RESTORING:
            return self._restore_step()
        if self.phase == EVALUATING:
            return self.evaluate_step()
        return self.next_candidate()

    # ---- candidate selection ------------------------------------------------------
    def next_candidate(self) -> StepEvent:
        """Select the next candidate, honouring review gates, checkpoints and skips."""

        if self.phase in (DONE, RESTORING, IDLE):
            return StepEvent("done" if self.phase == DONE else "idle", self.message)
        if self._cancel_requested:
            return self._begin_restore(CANCELLED, "Cancelled by the operator.")
        if self.phase == AWAITING_APPROVAL:
            return StepEvent("gate", self._gate_message(self._pending_gate), stage=self._pending_gate)
        for _ in range(len(self._candidates) + 1):  # bounded scan, never an open-ended loop
            if self._cursor >= len(self._candidates):
                return self._begin_restore(EXHAUSTED, self._exhausted_message())
            stage, state = self._candidates[self._cursor]
            if stage == "lip_variant" and stage not in self.unavailable_stages:
                self._require_lip_slab_evidence()
            if stage in fa.SENSITIVE_STAGES and stage not in self.unavailable_stages:
                answer = self._approvals.get(stage)
                if answer is None:
                    self._pending_gate = stage
                    self.phase = AWAITING_APPROVAL
                    return StepEvent("gate", self._gate_message(stage), stage=stage,
                                     total=sum(1 for s, _ in self._candidates if s == stage))
                if answer == "declined":
                    self._cursor += 1
                    self._declined_count += 1
                    continue
            self._cursor += 1
            if stage in self.unavailable_stages:
                return self._record_untested(stage, state, "lip/barrier variant", self.unavailable_stages[stage],
                                             failed_step="apply_barrier")
            opening = float(state[fa.MOUTH_OPENING_MM])
            if opening in self._skipped_openings:
                self._declined_count += 1
                continue
            if stage == "baseline" and self._identity_available:
                matches, reason = self._identity_matches_baseline()
                if not matches:
                    self.phase, self.outcome = DONE, BLOCKED
                    self.message = "Checkpoint reuse refused because advisor inputs changed: " + reason
                    self._progress_file("blocked: " + self.message)
                    return StepEvent("blocked", self.message, stage=stage)
                identity = {**self._base_identity, "state": fa.state_key(state)}
                reused = self.store.lookup(state, identity)
                if reused is not None:
                    return self._register_reused(stage, reused)
            elif self._identity_available:
                # Later candidates have intentionally changed the live opening or Base.
                # Their scene identity cannot be proven before trial application, so
                # persisted candidate records remain evidence and are not reused.
                identity = {**self._base_identity, "state": fa.state_key(state), "reuse_scope": "no_transient_state_reuse"}
            else:
                identity = {"reuse_scope": "session_only", "session_identity": self._session_identity,
                            "state": fa.state_key(state)}
            return self._start_candidate(stage, state, identity)
        return self._begin_restore(EXHAUSTED, self._exhausted_message())

    def _require_lip_slab_evidence(self) -> None:
        """The approved lip variants run only on attributed current baseline evidence naming the lip slab."""

        if self._lip_evidence is None:
            baseline = next((r for r in self.records if r.get("stage") == "baseline"), None)
            self._lip_evidence = fa.lip_slab_blocker_evidence(baseline)
        if not self._lip_evidence:
            self.unavailable_stages["lip_variant"] = (
                f"no attributed current baseline evidence names the lip slab ({fa.LIP_SLAB_OBJECT_ID}) as a "
                "blocker, so the approved lip variants are not evaluated; they are listed for operator review")

    def _gate_message(self, stage: str) -> str:
        text = fa.STAGE_PROMPTS.get(stage, stage)
        if stage == "lip_variant" and self._lip_evidence:
            first = self._lip_evidence[0]
            text += (f" Baseline evidence: {' <-> '.join(first['pair'])} at {first['step']} "
                     f"(candidate {first.get('sequence')}).")
        return text

    def _exhausted_message(self) -> str:
        if self.best_candidate() is not None:
            return ("Search finished; the best candidate is listed for review. Its trial settings are being restored, "
                    "and no branch configuration has been retained or saved.")
        return "No candidate within the approved limits passed. Escalate to the operator (limits, barrier, template or tool)."

    def _label(self, state) -> str:
        delta = fa.state_delta(state, self.baseline)
        return "-".join(f"{k}={v}" for k, v in sorted(delta.items())) or "baseline"

    def _start_candidate(self, stage, state, identity) -> StepEvent:
        index = len(self.records) + 1
        label = self._label(state)
        directory = self.root / f"candidate-{index:03d}-{label}"[:180]
        plan = [name for name in PLAN_STEPS if name != "apply_barrier" or self._barrier_applier is not None]
        violations = fa.state_violations(
            state, self.baseline[fa.MOUTH_OPENING_MM], self.limits,
            expected_corridor_margin_samples=int(self.original[fa.CORRIDOR_MARGIN_SAMPLES]),
        )
        current = _Current(index, stage, state, label, directory, {} if violations else identity, plan)
        if stage == "lip_variant":
            current.observed["lip_slab_evidence"] = list(self._lip_evidence or [])
        self._current = current
        self.phase = EVALUATING
        if violations:
            current.steps["prerequisites"] = {"result": fa.SETUP_ERROR, "reason": "; ".join(violations)}
            current.cursor = len(plan)  # nothing is applied for an unapproved state
        return StepEvent("started", f"candidate {index}: {label}", stage=stage, index=index, total=self.total_candidates())

    def _register_reused(self, stage, reused) -> StepEvent:
        record = dict(reused, reused_from=reused.get("evidence_dir"), sequence=len(self.records) + 1)
        self.records.append(record)
        self.phase = SEARCHING
        self._after_record(record)
        return StepEvent("reused", "reused checkpoint (identity match): " + self._label(record["state"]), stage=stage,
                         index=len(self.records), total=self.total_candidates(), record=record)

    def _record_untested(self, stage, state, what, reason, *, failed_step) -> StepEvent:
        index = len(self.records) + 1
        directory = self.root / f"candidate-{index:03d}-{self._label(state)}"[:180]
        record = fa.candidate_record(stage, state, self.baseline, {}, identity={}, evidence_dir=str(directory))
        record.update(result=fa.UNTESTED, failed_step=failed_step, reason=reason[:500], sequence=index)
        return self._finalize(record, directory, store=False)

    # ---- sub-step evaluation ------------------------------------------------------
    def evaluate_step(self) -> StepEvent:
        """Run exactly ONE sub-step of the current candidate."""

        current = self._current
        if current is None or self.phase != EVALUATING:
            return StepEvent("idle", "No candidate is being evaluated.")
        if self._cancel_requested:
            return self._begin_restore(CANCELLED, "Cancelled by the operator.")
        if current.cursor >= len(current.plan):  # unapproved state recorded by _start_candidate
            return self._finish_candidate(current)
        name = current.plan[current.cursor]
        is_diagnose = name == "diagnose"
        if not is_diagnose:
            current.cursor += 1
        if name in APPLY_STEPS and current.apply_failed:
            return self._event(current, name, "skipped after an earlier apply error")
        home_issues = self._home_currentness_issues()
        if home_issues:
            return self._record_operator_review_block(
                current, name, "Task Home requires explicit 6.2 operator review before this trial step: "
                + "; ".join(home_issues)[:400]
            )
        if name in APPLY_STEPS or name in fa.EVALUATION_STEPS:
            immutable_issues = self._immutable_trial_setting_issues()
            if immutable_issues:
                return self._record_operator_review_block(
                    current, name, "Trial stopped because an immutable guard setting changed: "
                    + "; ".join(immutable_issues)
                )
        self._progress_file(f"{STEP_TITLES[name]} ({current.label})")
        step_started = self._clock()
        try:
            if is_diagnose:
                done, note = self._do_diagnose_step(current)
                if done:
                    current.cursor += 1
            else:
                note = getattr(self, "_do_" + name)(current)
        except Exception as exc:  # recorded, never hidden
            if isinstance(exc, _HomeReviewRequired):
                return self._record_operator_review_block(current, name, str(exc))
            note = None
            if name in APPLY_STEPS:
                current.apply_failed = True
                current.observed.setdefault("apply_errors", []).append(f"{name}: {exc}"[:300])
            elif is_diagnose:
                from dentobot_workflow import base_diagnosis

                check = base_diagnosis.CHECK_ORDER[min(current.diagnosis_cursor, len(base_diagnosis.CHECK_ORDER) - 1)]
                current.diagnosis_rows.append(base_diagnosis._row(
                    check, base_diagnosis.FAIL, f"Check could not run: {str(exc)[:300]}", "unknown"
                ))
                current.diagnosis_cursor += 1
                self._finish_diagnosis(current)
                note = f"Diagnose stopped at {check}: check could not run"
            else:
                current.steps[name] = {"result": fa.SETUP_ERROR, "reason": f"{name} could not run: {exc}"[:300]}
        label = name
        if is_diagnose and current.diagnosis_rows:
            label = "diagnose:" + str(current.diagnosis_rows[-1].get("check") or "")
        current.timings[label] = round(max(0.0, self._clock() - step_started), 3)
        self._refresh()
        if current.observed.get("needs_rebuild"):
            return self._needs_rebuild(current)
        if is_diagnose and not current.diagnosis_done:
            check = str((current.diagnosis_rows[-1] if current.diagnosis_rows else {}).get("check") or "")
            return self._event(current, name, note or STEP_TITLES[name], substep=check)
        if name in fa.EVALUATION_STEPS:
            result = (current.steps.get(name) or {}).get("result")
            if result not in (fa.PASSED, fa.WARNING_RESULT) or name == "diagnose":
                event = self._finish_candidate(current)
                if is_diagnose and current.diagnosis_rows:
                    event.step = "diagnose:" + str(current.diagnosis_rows[-1].get("check") or "")
                return event
        return self._event(current, name, note or STEP_TITLES[name])

    def _event(self, current, name, message, *, substep="") -> StepEvent:
        return StepEvent("step", message, stage=current.stage, step=(f"{name}:{substep}" if substep else name),
                         index=current.index, total=self.total_candidates())

    def _record_operator_review_block(self, current, failed_step: str, reason: str) -> StepEvent:
        self._operator_review_block = True
        directory = current.directory
        record = fa.candidate_record(current.stage, current.state, self.baseline, {}, identity=current.identity,
                                     evidence_dir=str(directory))
        record.update(result=fa.SETUP_ERROR, failed_step=failed_step, reason=reason[:500],
                      steps={**current.steps, failed_step: {"result": fa.SETUP_ERROR, "reason": reason[:500]}},
                      sequence=current.index, operator_review_required=True, timings_sec=dict(current.timings))
        self._current = None
        self.message = "Operator review required: " + reason[:300]
        event = self._finalize(record, directory, store=False)
        return StepEvent("candidate", event.message, stage=current.stage, step=failed_step,
                         index=len(self.records), total=self.total_candidates(), record=record)

    # ---- apply steps (production owners only; no widget, no modal handling) ------------
    def _live_barrier_tuning(self) -> dict | None:
        """The node's lip/barrier tuning through the production accessor (None when the owner is absent)."""

        getter = getattr(self.logic, "step6MouthBarrierTuning", None)
        if not callable(getter):
            return None
        tuning = getter(self.node)
        return {fa.LIP_MARGIN_MM: float(tuning["lip_margin_mm"]), fa.LIP_SLAB_MM: float(tuning["lip_slab_mm"]),
                fa.PORTAL_ENLARGE_MM: float(tuning["portal_enlarge_mm"])}

    def _barrier_geometry_fingerprint(self) -> str:
        """Fingerprint of the audited mouth-barrier objects (empty when no audit exists)."""

        audit = self.logic.collisionSceneAuditRecord(self.node)
        rows = [
            [raw.get(key) for key in ("source_name", "prepared_world_fingerprint", "outgoing_fingerprint")]
            for raw in getattr(audit, "object_records", ()) or ()
            if isinstance(raw, Mapping) and str(raw.get("source_role") or "") == "mouth-barrier"
        ]
        return fa.fingerprint_of(sorted(rows)) if rows else ""

    def _apply_barrier_tuning(self, state) -> str:
        """Set the approved tuning through the production owner, then re-sync and prove the scene changed.

        The MoveIt-vs-audit comparison cannot see a node-side barrier change, so the production
        ``syncPlanningScene`` owner is called explicitly while ROS is connected; with ROS disconnected
        the values are stored and the next production Connect publishes them.
        """

        before = self._barrier_geometry_fingerprint() if self._active() else ""
        wanted = {key: float(state[key]) for key in fa.LIP_VARIANT_BOUNDS}
        self.logic.setStep6MouthBarrierTuning(
            self.node, lip_margin_mm=float(state[fa.LIP_MARGIN_MM]), lip_slab_mm=float(state[fa.LIP_SLAB_MM]),
            portal_enlarge_mm=float(state[fa.PORTAL_ENLARGE_MM]))
        self.facade.invalidateMotionPlan()
        if not self._active():
            return "barrier tuning stored; the planning scene is published by the next production Connect"
        result = self.facade.syncPlanningScene()
        if not result.success:
            raise RuntimeError("Planning-scene sync after the barrier change failed: " + str(result.message)[:200])
        if not bool((result.details or {}).get("runtimeAcknowledged")):
            raise RuntimeError("MoveIt did not acknowledge the changed barrier scene")
        # The audited geometry must differ only when the scene was really holding other values (a failed
        # earlier sync leaves it on the previous tuning, so restoring that tuning is legitimately unchanged).
        if before and wanted != self._synced_tuning and self._barrier_geometry_fingerprint() == before:
            raise RuntimeError("The audited barrier geometry did not change after the tuning change")
        self._synced_tuning = wanted
        return "barrier tuning applied and the planning scene re-synchronized"

    def _do_apply_barrier(self, current):
        live = self._live_barrier_tuning()
        wanted = {key: float(current.state[key]) for key in fa.LIP_VARIANT_BOUNDS}
        if live is not None and all(abs(live[key] - wanted[key]) <= 1e-9 for key in wanted):
            return "barrier unchanged"
        return self._barrier_applier(current.state)

    def _do_apply_opening(self, current):
        opening = float(current.state[fa.MOUTH_OPENING_MM])
        if abs(float(self.node.step6CaseJawTargetGapMm) - opening) <= 1e-6:
            return "opening unchanged"
        self._set_opening(opening)
        registry = self._persisted_registry()
        eligibility = self.logic.evaluatePreparedBranchEligibility(
            self.node, self.branch_id, registry=registry
        )
        if eligibility.get("reason") != "VALID":
            current.observed["needs_rebuild"] = str(eligibility.get("message") or eligibility.get("reason"))
            return f"opening {opening} mm applied; the branch now needs operator review"
        if current.stage != "restore":
            self._require_current_home(candidate_step="the mouth-opening trial")
        return f"opening {opening} mm applied in the live case"

    def _set_opening(self, opening: float) -> None:
        if self._active():
            result = self.facade.disconnect()
            if not result.success:
                raise RuntimeError("Disconnect before changing the opening failed: " + str(result.message))
        if self._opening_applier is not None:
            self.node.step6CaseJawTargetGapMm = float(opening)
            self._opening_applier(float(opening))
        else:
            self.node.step6CaseJawTargetGapMm = float(opening)
            self.logic.createOrUpdateStep6CaseJawOpening(self.node)
            self.facade.clearTransientState()
        self.logic.importStep6PlanningContext(self.node)

    def _do_apply_base(self, current):
        import numpy as np
        from dentobot_workflow.base_placement_search import candidate_around_base

        state, node, facade = current.state, self.node, self.facade
        forehead = self.logic._foreheadFrameFromStoredPlane(node.robotMountPlane)
        target = candidate_around_base(forehead, self.saved_base, float(state[fa.BASE_U_MM]), float(state[fa.BASE_V_MM]),
                                       float(state[fa.BASE_DEPTH_MM]), float(state[fa.BASE_YAW_DEG]))
        current.observed["requested_base"] = target.tolist()
        same = bool(node.robotBaseMountLocked) and float(np.abs(self._ctx_matrix(node.robotBaseTransform) - target).max()) < 1e-9
        if same:
            return "Base unchanged"
        loaded = facade.loadRobot()
        if not loaded.success:
            raise RuntimeError("Load robot failed: " + str(loaded.message))
        if node.robotBaseMountLocked:
            result = facade.unlockBase()
            if not result.success:
                raise RuntimeError("Unlock Base failed: " + str(result.message))
        flat = tuple(float(v) for v in target.flatten())
        result = facade.stageManualBaseReview(flat)
        if not result.success:
            facade.cancelManualBaseReview()
            result = facade.stageManualBaseReview(flat)
        if result.success:
            result = facade.acceptManualBaseReview()
        current.observed["base_accept"] = [bool(result.success), str(result.code), str(result.message)[:300]]
        if not result.success:
            raise RuntimeError("Base was not accepted: " + str(result.message)[:200])
        if current.stage != "restore":
            self._require_current_home(candidate_step="the Base trial")
        return "Base accepted"

    def _do_apply_policy(self, current):
        state, node, facade = current.state, self.node, self.facade
        live_margin = int(facade.approachCorridorMarginSamples())
        wanted_margin = int(state[fa.CORRIDOR_MARGIN_SAMPLES])
        if live_margin != wanted_margin:
            raise RuntimeError(
                f"approach-corridor guard margin changed from captured {wanted_margin} to {live_margin}; "
                "the advisor will not change it"
            )
        live_allowance = bool(getattr(node, "step6AllowSpindleGuideContact", False))
        if live_allowance != bool(state[fa.SPINDLE_TEMPLATE_ALLOWANCE]):
            raise RuntimeError("spindle-template contact allowance changed; the advisor will not change it")
        facade.setJointPlanningPolicy(state[fa.PLANNER_ID], int(state[fa.PLANNING_ATTEMPTS]), float(state[fa.PLANNING_TIME_SEC]))
        wanted = {"planner_id": state[fa.PLANNER_ID], "planning_attempts": int(state[fa.PLANNING_ATTEMPTS]),
                  "planning_time_sec": float(state[fa.PLANNING_TIME_SEC])}
        used = facade.jointPlanningPolicy()
        current.observed["policy_issues"] = ([] if {k: used[k] for k in wanted} == wanted
                                             else [f"facade policy {used} != {wanted}"])
        return "planning policy set"

    def _do_apply_home(self, current):
        self._require_current_home(candidate_step="candidate evaluation" if current.stage != "restore"
                                   else "baseline restoration")
        return "saved Task Home identity and existing validation remain current"

    def _do_apply_confirm(self, current):
        result = self.facade.confirmTask()
        current.observed["confirm"] = [bool(result.success), str(result.code), str(result.message)[:300]]
        if not result.success:
            raise RuntimeError("Task was not confirmed: " + str(result.message)[:200])
        return "task confirmed"

    # ---- evaluation steps ------------------------------------------------------------------
    def _barrier_issues(self, state) -> list:
        import dentobot_workflow.mouth_portal as mp

        issues = []
        if str(getattr(self.node, "step6MouthBarrierEdgeMode", None) or "gum_line") != state[fa.BARRIER_EDGE_MODE]:
            issues.append(f"edge mode {self.node.step6MouthBarrierEdgeMode!r} != {state[fa.BARRIER_EDGE_MODE]!r}")
        live = self._live_barrier_tuning() or {
            fa.LIP_MARGIN_MM: inspect.signature(mp.shift_portal_to_lip_line).parameters["margin_mm"].default,
            fa.PORTAL_ENLARGE_MM: inspect.signature(mp.enlarge_portal).parameters["margin_mm"].default,
            fa.LIP_SLAB_MM: inspect.signature(mp.build_mouth_barrier).parameters["lip_thickness_mm"].default,
        }
        for key, value in live.items():
            if abs(float(value) - float(state[key])) > 1e-9:
                issues.append(f"{key} live {value} != requested {state[key]}")
        return issues

    def _observe(self, state, observed) -> dict:
        import numpy as np

        node, logic, facade = self.node, self.logic, self.facade
        home = logic.taskHomeRecord(node)
        current_home = dict(zip(home.joint_names, home.joint_positions_si)) if home is not None else {}
        requested = observed.get("requested_base")
        observed.update({
            "ros_connected": self._active(), "base_locked": bool(node.robotBaseMountLocked),
            "base_delta_mm": float(np.abs(self._ctx_matrix(node.robotBaseTransform) - np.asarray(requested, float)).max())
            if requested else None,
            "home_gap": str(facade.taskHomeValidationGap(node) or ""), "home_si": current_home,
            "home_identity_matches": (
                fa.fingerprint_of(self._home_record_identity(home))
                == fa.fingerprint_of(self._saved_home_identity)
            ),
            "home_delta_si": max((abs(float(current_home.get(k, 1e9)) - float(v)) for k, v in (self.saved_home or {}).items()),
                                 default=None) if self.saved_home else None,
            "task_confirmation_issues": [str(s) for s in (logic.confirmedTaskFreshnessIssues(node) or ())],
            "collision_audit_issues": [str(s) for s in (logic.collisionSceneAuditFreshnessIssues(node) or ())],
            "barrier_issues": self._barrier_issues(state),
            "spindle_template_allowance": bool(getattr(node, "step6AllowSpindleGuideContact", False)),
            "corridor_margin_samples": int(facade.approachCorridorMarginSamples()),
            "opening_mm": float(node.step6CaseJawTargetGapMm),
        })
        geometry = observed.setdefault("geometry_issues", [])
        if abs(observed["opening_mm"] - float(state[fa.MOUTH_OPENING_MM])) > 1e-6:
            geometry.append(f"opening {observed['opening_mm']} mm != requested {state[fa.MOUTH_OPENING_MM]} mm")
        if not observed["home_identity_matches"]:
            geometry.append("saved Task Home identity changed")
        if observed["corridor_margin_samples"] != int(state[fa.CORRIDOR_MARGIN_SAMPLES]):
            geometry.append("approach-corridor guard margin changed")
        for error in observed.get("apply_errors") or ():
            geometry.append("apply error: " + error)
        scene = facade.ensureMoveItSceneMatches()
        observed["scene_state"], observed["scene_message"] = scene.get("state"), scene.get("message")
        return observed

    def _do_prerequisites(self, current):
        observed = self._observe(current.state, current.observed)
        issues = fa.precondition_issues(observed, self.limits)
        current.steps["prerequisites"] = {"result": fa.SETUP_ERROR if issues else fa.PASSED,
                                          "reason": "; ".join(issues) if issues else "prerequisites and scene current",
                                          "observed": observed}

    def _do_stroke_reach(self, current):
        stroke = self.logic.step6CurrentBaseStrokeReachability(self.node)
        reachable = bool((stroke or {}).get("reachable"))
        current.steps["stroke_reach"] = {
            "result": fa.PASSED if reachable else fa.UNREACHABLE,
            "reason": "stroke reachable" if reachable else str((stroke or {}).get("first_failed_station") or "stroke unreachable"),
            "raw": stroke}

    def _do_preentry(self, current):
        current.steps["preentry"] = preentry_step(self.facade.checkPreEntryIK())

    def _do_corridor(self, current):
        step = corridor_step(self.facade.checkApproachCorridorClearance(), self.limits)
        current.steps["corridor"] = step

    def _do_diagnose_step(self, current) -> tuple[bool, str]:
        """Run one existing Diagnose row per service tick, preserving row order and stop-on-failure."""

        from dentobot_workflow import base_diagnosis

        if not current.diagnosis_started:
            self.facade.invalidateMotionPlan()
            current.diagnosis_started = True
        checks = base_diagnosis.CHECK_ORDER
        if current.diagnosis_cursor >= len(checks):
            self._finish_diagnosis(current)
            return True, "Diagnose rows complete"
        check = checks[current.diagnosis_cursor]
        row = None
        if check == "scene_match":
            scene_status = self.facade.ensureMoveItSceneMatches()
            if scene_status.get("state") == "not_checked":
                current.diagnosis_cursor += 1
                return False, "Diagnose scene comparison unavailable; continuing with stroke reach"
            comparison = scene_status.get("comparison") or {}
            row = base_diagnosis.scene_row(
                comparison if "expected_count" in comparison else None,
                unavailable_reason=str(comparison.get("summary") or ""),
            )
            if scene_status.get("state") == "resynced":
                row["detail"] += " MoveIt differed at first and was re-synchronized from Slicer."
        elif check == "stroke_reach":
            stroke_check = getattr(self.logic, "step6CurrentBaseStrokeReachability", None)
            stroke = stroke_check(self.node) if callable(stroke_check) else None
            row = base_diagnosis.stroke_row(stroke)
        elif check == "preentry_endpoint":
            result = self.facade.checkPreEntryIK()
            records = ()
            to_dict = getattr(getattr(result, "payload", None), "to_dict", None)
            if callable(to_dict):
                records = tuple(to_dict().get("candidate_records") or ())
            details = dict(getattr(result, "details", {}) or {})
            status = str(details.get("diagnosticStatus") or "")
            if not result.success and not status:
                status = str(result.message or "unknown")[:300]
            row = base_diagnosis.preentry_row(status, records)
        elif check in ("p1_route", "p2_entry", "p3_drilling"):
            phase_id = {"p1_route": "P1", "p2_entry": "P2", "p3_drilling": "P3"}[check]
            result = self.facade.checkPlanningStage(phase_id)
            outcome = result.payload if isinstance(result.payload, Mapping) else (
                (result.details or {}).get("stageOutcome")
            )
            if not isinstance(outcome, Mapping):
                outcome = {"diagnostic_status": "unknown", "reason": str(result.message or "Check returned no result.")[:300]}
            row = base_diagnosis.stage_row(phase_id, outcome)
        elif check == "frame_match":
            states = self.facade._frame_check_states()
            if not states:
                current.diagnosis_cursor += 1
                self._finish_diagnosis(current)
                return True, "Diagnose frame row unavailable in this runtime"
            row = base_diagnosis.frame_row(self.facade.frameConsistency(states))
        if row is None:
            row = base_diagnosis._row(check, base_diagnosis.FAIL, "Diagnose row could not run.", "unknown")
        current.diagnosis_rows.append(row)
        current.diagnosis_cursor += 1
        if row.get("status") == base_diagnosis.FAIL:
            self._finish_diagnosis(current)
            return True, f"Diagnose stopped at {check}: {row.get('detail') or row.get('status')}"
        if current.diagnosis_cursor >= len(checks):
            self._finish_diagnosis(current)
            return True, "Diagnose rows complete"
        return False, f"Diagnose row {check}: {row.get('status')}"

    def _finish_diagnosis(self, current) -> None:
        from dentobot_workflow import base_diagnosis

        summary = base_diagnosis.summarize(current.diagnosis_rows)
        step = fa.classify_diagnosis(summary)
        step["raw"] = summary
        step["policy_used"] = self.facade.jointPlanningPolicy()
        current.steps["diagnose"] = step
        current.diagnosis_done = True

    # ---- candidate completion ------------------------------------------------------------------
    def _needs_rebuild(self, current) -> StepEvent:
        opening = float(current.state[fa.MOUTH_OPENING_MM])
        self._skipped_openings.add(opening)
        reason = ("The PreparedBranch needs explicit operator review after the opening trial: "
                  + str(current.observed["needs_rebuild"])[:300]
                  + ". The service stopped and did not rebuild the branch.")
        return self._record_operator_review_block(current, "apply_opening", reason)

    def _finish_candidate(self, current) -> StepEvent:
        steps = dict(current.steps)
        record = fa.candidate_record(current.stage, current.state, self.baseline, steps, identity=current.identity,
                                     evidence_dir=str(current.directory))
        record["sequence"] = current.index
        record["timings_sec"] = dict(current.timings)
        self._current = None
        return self._finalize(record, current.directory, store=True)

    def _finalize(self, record, directory, *, store) -> StepEvent:
        record.setdefault("sequence", len(self.records) + 1)
        self._write(directory, "candidate.json", record)
        if store and record.get("result") != fa.UNTESTED and record.get("identity"):
            self.store.append(record)  # setup errors are filtered out on lookup
        self.records.append(record)
        self.phase = SEARCHING
        self._after_record(record)
        if len(self.records) % REPORT_EVERY == 0:
            self.write_reports()
        return StepEvent("candidate", f"{record['result']}: {record.get('reason') or ''}"[:300], stage=record["stage"],
                         index=len(self.records), total=self.total_candidates(), record=record)

    def _after_record(self, record) -> None:
        self._setup_error_run = self._setup_error_run + 1 if record.get("result") == fa.SETUP_ERROR else 0
        reason = self.should_stop()
        if reason == FOUND:
            change = ", ".join(f"{k}={v}" for k, v in sorted((record.get("change") or {}).items())) or "baseline"
            warning = " (WARNING: drilling shortened)" if record.get("result") == fa.WARNING_RESULT else ""
            self._begin_restore(
                FOUND,
                f"Candidate {len(self.records)} ({change}) passed{warning}. Trial settings were temporarily applied "
                "to the simulation; baseline restoration was attempted. Nothing has been retained or saved to the branch.",
            )
        elif reason == BLOCKED:
            text = self.message if self._operator_review_block else (
                "Repeated setup errors: fix the setup shown in the diagnostics, then search again."
            )
            self._begin_restore(BLOCKED, text)

    def should_stop(self) -> str:
        """FOUND / BLOCKED / '' after the latest record (checked by every finalize)."""

        if not self.records:
            return ""
        if self._operator_review_block:
            return BLOCKED
        last = self.records[-1]
        if last.get("stage") == "baseline" and last.get("result") == fa.SETUP_ERROR:
            return BLOCKED
        if self._setup_error_run >= MAX_CONSECUTIVE_SETUP_ERRORS:
            return BLOCKED
        if self.stop_after_first_pass and last.get("result") in (fa.PASSED, fa.WARNING_RESULT):
            return FOUND
        return ""

    # ---- restoring the operator's original state --------------------------------------------------
    def _begin_restore(self, outcome: str, message: str) -> StepEvent:
        self.outcome, self.message = outcome, message
        self._current = None
        self.phase = RESTORING
        plan = [n for n in APPLY_STEPS if n != "apply_barrier" or self._barrier_applier is not None]
        self._restore_plan = plan
        self._restore_observed = {}
        self.write_reports()
        return StepEvent("restore", "restoring the original Step 6 state", total=len(plan))

    def _restore_step(self) -> StepEvent:
        if not self._restore_plan:
            return self._finish_restore()
        name = self._restore_plan.pop(0)
        current = _Current(0, "restore", self._restore_state, "restore", self.root / "restore", {}, [name])
        current.observed = self._restore_observed
        try:
            getattr(self, "_do_" + name)(current)
            if self._restore_observed.get("needs_rebuild"):
                self.restore_issues.append(
                    f"{name}: PreparedBranch needs operator review; original opening could not be safely restored"
                )
                self._restore_plan = []
        except Exception as exc:  # recorded, never hidden
            self.restore_issues.append(f"{name}: {exc}"[:300])
            self._restore_plan = []
        self._refresh()
        return StepEvent("restore", STEP_TITLES[name].replace("applying", "restoring"))

    def _finish_restore(self) -> StepEvent:
        if not self.restore_issues:
            try:
                import numpy as np

                self._restore_observed["requested_base"] = self.saved_base.tolist()
                actual_base = self._ctx_matrix(self.node.robotBaseTransform)
                base_delta = float(np.abs(actual_base - self.saved_base).max())
                if base_delta > self.limits.base_tolerance_mm:
                    self.restore_issues.append(
                        f"restored Base differs from the captured Base by {base_delta:.6g} mm"
                    )
                else:
                    observed = self._observe(self._restore_state, self._restore_observed)
                    self.restore_issues += fa.precondition_issues(observed, self.limits)
                    if not self.restore_issues and self._identity_available:
                        matches, reason = self._identity_matches_baseline()
                        if not matches:
                            self.restore_issues.append("original input identity changed: " + reason[:300])
            except Exception as exc:  # recorded, never hidden
                self.restore_issues.append(f"restore check could not run: {exc}"[:300])
        self.phase = DONE
        if self.restore_issues:
            self.message += (" The original state could NOT be fully restored ("
                             + "; ".join(self.restore_issues)[:300]
                             + "): use 'Restore Branch Step 6 Config' or review 6.1-6.3 before continuing.")
        self.write_reports()
        self._progress_file("done: " + self.outcome)
        return StepEvent("done", self.message, issues=list(self.restore_issues))

    # ---- table, staging, evidence ----------------------------------------------------------------
    def ranked(self) -> list:
        """Rows for the ranked table (best first)."""

        rows = []
        for rank, record in enumerate(sorted(self.records, key=rank_key), 1):
            rows.append({
                "rank": rank, "stage": record.get("stage"), "change": dict(record.get("change") or {}),
                "change_text": ", ".join(f"{k}={v}" for k, v in sorted((record.get("change") or {}).items())) or "baseline",
                "result": record.get("result"), "failed_step": record.get("failed_step") or "",
                "reason": str(record.get("reason") or ""), "evidence_dir": record.get("evidence_dir") or "",
                "reused": bool(record.get("reused_from")), "review_items": sensitive_items(record),
                "state_key": record.get("state_key"),
            })
        return rows

    def best_candidate(self) -> dict | None:
        """First PASS in rank order, else the first WARNING; staged, never applied."""

        ordered = sorted(self.records, key=rank_key)
        for wanted in (fa.PASSED, fa.WARNING_RESULT):
            for record in ordered:
                if record.get("result") == wanted:
                    return record
        return None

    def required_acknowledgements(self, record: Mapping | None = None) -> list:
        record = record or self.best_candidate()
        return sensitive_items(record) if record else []

    def write_reports(self) -> None:
        if not self.baseline:
            return
        notes = [f"Outcome: {self.outcome or 'running'}; {self.message}"] + [
            f"Unavailable stage {stage}: {why}" for stage, why in self.unavailable_stages.items()]
        longest = self.longest_step()
        if longest:
            notes.append(f"Longest single uninterruptible step measured: {longest[0]:.1f} s (candidate {longest[1]}, "
                         f"{longest[2]}). The dialog cannot repaint or cancel inside one step; this is measured, not accepted.")
        if self._declined_count:
            notes.append(f"{self._declined_count} candidate(s) were skipped (declined stage or skipped opening) and stay UNTESTED.")
        (self.root).mkdir(parents=True, exist_ok=True)
        (self.root / "advisor-ordered-report.md").write_text(
            fa.ordered_report_markdown(self.baseline, self.records, self.limits, notes=notes), encoding="utf-8")
        self._write(self.root, "advisor-ordered-records.json", self.records)

    def longest_step(self) -> tuple | None:
        """``(seconds, candidate sequence, step)`` of the slowest recorded sub-step, or None."""

        best = None
        for record in self.records:
            for step, seconds in (record.get("timings_sec") or {}).items():
                if best is None or float(seconds) > best[0]:
                    best = (float(seconds), record.get("sequence"), step)
        return best

    def export_evidence(self) -> str:
        """Rewrite the report and records; returns the evidence directory."""

        self.write_reports()
        return str(self.root)

    # ---- the ONLY storing path ---------------------------------------------------------------------
    def apply_and_save(self, acknowledged: Sequence[str] = (), record: Mapping | None = None) -> dict:
        """Store the staged candidate as the active branch's working configuration.

        Called only from the operator's "Apply & Save to branch" click. It refuses while
        the session is running, when the staged candidate no longer matches the live
        branch, and unless every clinical review item was explicitly acknowledged.
        """

        if self.phase != DONE:
            raise PermissionError("The search is still running.")
        if self.restore_issues:
            raise PermissionError("Baseline restoration is incomplete; review 6.1-6.3 before saving.")
        if self.outcome == BLOCKED or self._operator_review_block:
            raise PermissionError("Apply & Save is unavailable until the required operator review is complete.")
        home_issues = self._home_currentness_issues()
        if home_issues:
            raise PermissionError("Apply & Save refused because Task Home needs explicit 6.2 review: "
                                  + "; ".join(home_issues)[:300])
        matches, identity_reason = self._identity_matches_baseline()
        if not matches:
            raise PermissionError("Apply & Save refused because the original input identity is not current: "
                                  + identity_reason)
        record = dict(record or self.best_candidate() or {})
        if not record or record.get("result") not in (fa.PASSED, fa.WARNING_RESULT):
            raise ValueError("No passing candidate is staged.")
        missing = [item for item in self.required_acknowledgements(record) if item not in set(acknowledged)]
        if missing:
            raise PermissionError("Operator review required for: " + ", ".join(missing))
        if str(self._base_identity.get("selected_branch_id") or "") != self.branch_id:
            raise ValueError("The active branch changed since the search; run it again.")
        config = working_configuration_record(record, self.saved_home, self.original)
        return self.logic.storeStep6WorkingConfiguration(self.node, config)
