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
* Nothing is auto-applied. ``apply_and_save`` is the only place that stores a
  configuration (``logic.storeStep6WorkingConfiguration``) and it requires the
  operator's acknowledgement of every review item.
* Search candidates are applied in the LIVE case and the original Step 6 state is
  restored when the session ends or is cancelled. An opening whose branch is no
  longer VALID after the live opening change is reported as "needs rebuild -
  operator review" and is never rebuilt automatically.
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
    "diagnose": "running full Diagnose (P1-P3)",
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


# ---------------------------------------------------------------------------
class FeasibilityAdvisorSession:
    """One step-driven ordered feasibility search for the active PreparedBranch."""

    def __init__(self, logic, facade, parameterNode, evidence_root, *, limits: fa.OrderedLimits = fa.OrderedLimits(),
                 target_fdi: str = "", stop_after_first_pass: bool = True,
                 opening_applier: Callable[[float], None] | None = None,
                 barrier_applier: Callable[[Mapping], None] | None = None,
                 ui_refresh: Callable[[], None] | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.logic, self.facade, self.node = logic, facade, parameterNode
        self.root = Path(evidence_root)
        self.limits = limits
        self.target_fdi = str(target_fdi)
        self.stop_after_first_pass = bool(stop_after_first_pass)
        self._opening_applier = opening_applier
        self._barrier_applier = barrier_applier
        self._ui_refresh = ui_refresh
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
        self.branch_id = ""
        self._base_identity: dict = {}
        self._candidates: list = []
        self._cursor = 0
        self._current: _Current | None = None
        self._approvals: dict = {}
        self._pending_gate = ""
        self._skipped_openings: set = set()
        self._declined_count = 0
        self._setup_error_run = 0
        self._cancel_requested = False
        self._restore_plan: list = []
        self._restore_state: dict = {}
        self._restore_observed: dict = {}
        self.restore_issues: list = []
        self.unavailable_stages: dict = {}
        if barrier_applier is None:
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
        return {"phase": self.phase, "stage": current.stage if current else "", "index": len(self.records),
                "total": self.total_candidates(),
                "step": current.plan[min(current.cursor, len(current.plan) - 1)] if current and current.plan else "",
                "label": current.label if current else ""}

    def _ctx_matrix(self, transform_node):
        import numpy as np
        import vtk

        matrix = vtk.vtkMatrix4x4()
        transform_node.GetMatrixTransformToWorld(matrix)
        return np.array([[matrix.GetElement(r, c) for c in range(4)] for r in range(4)])

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
            branch = logic.evaluatePreparedBranchEligibility(node)
        except (RuntimeError, ValueError, TypeError, KeyError) as exc:
            branch = {"reason": "UNKNOWN", "message": str(exc)}
        if branch.get("reason") != "VALID":
            issues.append(SetupIssue("The active PreparedBranch is not VALID: " + str(branch.get("message") or branch.get("reason")),
                                     fix_id="goto_6_1", fix_label="Select a valid branch / import Step 6 (6.1)"))
        ros = self._active()
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
        scene = None
        if ros:
            status = facade.lastMoveItSceneStatus()
            scene = (status or {}).get("state")
        observed = {
            "ros_connected": ros, "base_locked": bool(getattr(node, "robotBaseMountLocked", False)),
            "base_delta_mm": 0.0, "home_gap": str(facade.taskHomeValidationGap(node) or ""), "home_delta_si": 0.0,
            "task_confirmation_issues": [str(s) for s in (logic.confirmedTaskFreshnessIssues(node) or ())],
            "collision_audit_issues": [str(s) for s in (logic.collisionSceneAuditFreshnessIssues(node) or ())],
            "scene_state": scene, "scene_message": "",
        }
        covered = []
        if not getattr(node, "robotBaseMountLocked", False):
            covered.append("Base not accepted")
        if home is None:
            covered.append("Task Home not validated")
        for text in fa.precondition_issues(observed, self.limits):
            if any(text.startswith(prefix) for prefix in covered):
                continue  # already reported above as a blocking issue
            fix = classify_setup_issue(text)
            issues.append(SetupIssue(text, severity="advisory", fix_id=fix[0] if fix else "",
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
        eligibility = logic.evaluatePreparedBranchEligibility(node)
        self.branch_id = str(eligibility.get("branch_id") or "")
        opening = float(node.step6CaseJawTargetGapMm)
        self.baseline = fa.baseline_state(opening)
        self.original = {
            fa.MOUTH_OPENING_MM: opening, fa.PLANNER_ID: policy["planner_id"],
            fa.PLANNING_ATTEMPTS: int(policy["planning_attempts"]), fa.PLANNING_TIME_SEC: float(policy["planning_time_sec"]),
            fa.CORRIDOR_MARGIN_SAMPLES: int(facade.approachCorridorMarginSamples()),
            fa.SPINDLE_TEMPLATE_ALLOWANCE: bool(getattr(node, "step6AllowSpindleGuideContact", False)),
        }
        self._restore_state = {**self.baseline, **self.original}
        self._base_identity = {
            "schema": fa.ADVISOR_SCHEMA, "target_fdi": self.target_fdi, "branch_id": self.branch_id,
            "branch_foundation_fingerprint": str((eligibility.get("branch") or {}).get("branch_foundation_fingerprint") or ""),
            "robot_profile": logic.robotProfileFingerprint(),
            "saved_base": fa.fingerprint_of([round(float(v), 6) for v in self.saved_base.flatten()]),
            "saved_home": fa.fingerprint_of(self.saved_home), "limits": fa.fingerprint_of(vars(self.limits)),
        }
        self._candidates = [("baseline", dict(self.baseline)), *fa.ordered_candidates(self.baseline, self.limits)]
        self.phase = READY
        self.message = f"Ready: {len(self._candidates)} candidate states in the approved order."
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
        if self.phase == AWAITING_APPROVAL:
            return StepEvent("gate", fa.STAGE_PROMPTS.get(self._pending_gate, self._pending_gate), stage=self._pending_gate)
        if self._cancel_requested and self.phase != RESTORING:
            return self._begin_restore(CANCELLED, "Cancelled by the operator.")
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
        if self.phase == AWAITING_APPROVAL:
            return StepEvent("gate", fa.STAGE_PROMPTS.get(self._pending_gate, ""), stage=self._pending_gate)
        if self._cancel_requested:
            return self._begin_restore(CANCELLED, "Cancelled by the operator.")
        for _ in range(len(self._candidates) + 1):  # bounded scan, never an open-ended loop
            if self._cursor >= len(self._candidates):
                return self._begin_restore(EXHAUSTED, self._exhausted_message())
            stage, state = self._candidates[self._cursor]
            if stage in fa.SENSITIVE_STAGES and stage not in self.unavailable_stages:
                answer = self._approvals.get(stage)
                if answer is None:
                    self._pending_gate = stage
                    self.phase = AWAITING_APPROVAL
                    return StepEvent("gate", fa.STAGE_PROMPTS.get(stage, stage), stage=stage,
                                     total=sum(1 for s, _ in self._candidates if s == stage))
                if answer == "declined":
                    self._cursor += 1
                    self._declined_count += 1
                    continue
            self._cursor += 1
            if stage in self.unavailable_stages:
                return self._record_untested(stage, state, "lip/barrier variant", "needs operator review: "
                                             + self.unavailable_stages[stage], failed_step="apply_barrier")
            opening = float(state[fa.MOUTH_OPENING_MM])
            if opening in self._skipped_openings:
                self._declined_count += 1
                continue
            identity = {**self._base_identity, "state": fa.state_key(state)}
            reused = self.store.lookup(state, identity)
            if reused is not None:
                return self._register_reused(stage, reused)
            return self._start_candidate(stage, state, identity)
        return self._begin_restore(EXHAUSTED, self._exhausted_message())

    def _exhausted_message(self) -> str:
        if self.best_candidate() is not None:
            return "Search finished; the best candidate is staged for your review."
        return "No candidate within the approved limits passed. Escalate to the operator (limits, barrier, template or tool)."

    def _label(self, state) -> str:
        delta = fa.state_delta(state, self.baseline)
        return "-".join(f"{k}={v}" for k, v in sorted(delta.items())) or "baseline"

    def _start_candidate(self, stage, state, identity) -> StepEvent:
        index = len(self.records) + 1
        label = self._label(state)
        directory = self.root / f"candidate-{index:03d}-{label}"[:180]
        plan = [name for name in PLAN_STEPS if name != "apply_barrier" or self._barrier_applier is not None]
        violations = fa.state_violations(state, self.baseline[fa.MOUTH_OPENING_MM], self.limits)
        current = _Current(index, stage, state, label, directory, {} if violations else identity, plan)
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
        current.cursor += 1
        if name in APPLY_STEPS and current.apply_failed:
            return self._event(current, name, "skipped after an earlier apply error")
        self._progress_file(f"{STEP_TITLES[name]} ({current.label})")
        try:
            note = getattr(self, "_do_" + name)(current)
        except Exception as exc:  # recorded, never hidden
            note = None
            if name in APPLY_STEPS:
                current.apply_failed = True
                current.observed.setdefault("apply_errors", []).append(f"{name}: {exc}"[:300])
            else:
                current.steps[name] = {"result": fa.SETUP_ERROR, "reason": f"{name} could not run: {exc}"[:300]}
        self._refresh()
        if current.observed.get("needs_rebuild"):
            return self._needs_rebuild(current)
        if name in fa.EVALUATION_STEPS:
            result = (current.steps.get(name) or {}).get("result")
            if result not in (fa.PASSED, fa.WARNING_RESULT) or name == "diagnose":
                return self._finish_candidate(current)
        return self._event(current, name, note or STEP_TITLES[name])

    def _event(self, current, name, message) -> StepEvent:
        return StepEvent("step", message, stage=current.stage, step=name, index=current.index, total=self.total_candidates())

    # ---- apply steps (production owners only; no widget, no modal handling) ------------
    def _do_apply_barrier(self, current):
        self._barrier_applier(current.state)

    def _do_apply_opening(self, current):
        opening = float(current.state[fa.MOUTH_OPENING_MM])
        if abs(float(self.node.step6CaseJawTargetGapMm) - opening) <= 1e-6:
            return "opening unchanged"
        self._set_opening(opening)
        eligibility = self.logic.evaluatePreparedBranchEligibility(self.node)
        if eligibility.get("reason") != "VALID":
            current.observed["needs_rebuild"] = str(eligibility.get("message") or eligibility.get("reason"))
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
        return "Base accepted"

    def _do_apply_policy(self, current):
        state, node, facade = current.state, self.node, self.facade
        if not self._active():
            result = facade.connect(open_motion_module=False)
            if not (result.success or (result.details or {}).get("runtimeConnected")):
                raise RuntimeError("Connect failed: " + str(result.message)[:200])
        facade.setJointPlanningPolicy(state[fa.PLANNER_ID], int(state[fa.PLANNING_ATTEMPTS]), float(state[fa.PLANNING_TIME_SEC]))
        facade.setApproachCorridorMarginSamples(int(state[fa.CORRIDOR_MARGIN_SAMPLES]))
        if bool(getattr(node, "step6AllowSpindleGuideContact", False)) != bool(state[fa.SPINDLE_TEMPLATE_ALLOWANCE]):
            node.step6AllowSpindleGuideContact = bool(state[fa.SPINDLE_TEMPLATE_ALLOWANCE])
            current.observed["allowance_changed"] = True
        wanted = {"planner_id": state[fa.PLANNER_ID], "planning_attempts": int(state[fa.PLANNING_ATTEMPTS]),
                  "planning_time_sec": float(state[fa.PLANNING_TIME_SEC])}
        used = facade.jointPlanningPolicy()
        current.observed["policy_issues"] = ([] if {k: used[k] for k in wanted} == wanted
                                             else [f"facade policy {used} != {wanted}"])
        return "planning policy set"

    def _do_apply_home(self, current):
        facade = self.facade
        names = list(self.saved_home or {})
        if not names:
            raise RuntimeError("No saved Task Home to validate.")
        facade.cancelManualTaskHomeReview()
        staged = facade.stageManualTaskHomeReview({name: float(self.saved_home[name]) for name in names})
        current.observed["home_stage"] = [bool(staged.success), str(staged.code), str(staged.message)[:300]]
        if not staged.success:
            raise RuntimeError("Task Home was not staged: " + str(staged.message)[:200])
        accepted = facade.acceptManualTaskHomeReview()
        current.observed["home_accept"] = [bool(accepted.success), str(accepted.code), str(accepted.message)[:300]]
        if not accepted.success:
            raise RuntimeError("Task Home was not accepted: " + str(accepted.message)[:200])
        return "Task Home validated"

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
        live = {
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
            "home_delta_si": max((abs(float(current_home.get(k, 1e9)) - float(v)) for k, v in (self.saved_home or {}).items()),
                                 default=None) if self.saved_home else None,
            "task_confirmation_issues": [str(s) for s in (logic.confirmedTaskFreshnessIssues(node) or ())],
            "collision_audit_issues": [str(s) for s in (logic.collisionSceneAuditFreshnessIssues(node) or ())],
            "barrier_issues": self._barrier_issues(state),
            "spindle_template_allowance": bool(getattr(node, "step6AllowSpindleGuideContact", False)),
            "opening_mm": float(node.step6CaseJawTargetGapMm),
        })
        geometry = observed.setdefault("geometry_issues", [])
        if abs(observed["opening_mm"] - float(state[fa.MOUTH_OPENING_MM])) > 1e-6:
            geometry.append(f"opening {observed['opening_mm']} mm != requested {state[fa.MOUTH_OPENING_MM]} mm")
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

    def _do_diagnose(self, current):
        self.facade.invalidateMotionPlan()
        step = diagnose_step(self.facade.diagnoseBase())
        step["policy_used"] = self.facade.jointPlanningPolicy()
        current.steps["diagnose"] = step

    # ---- candidate completion ------------------------------------------------------------------
    def _needs_rebuild(self, current) -> StepEvent:
        opening = float(current.state[fa.MOUTH_OPENING_MM])
        self._skipped_openings.add(opening)
        record = fa.candidate_record(current.stage, current.state, self.baseline, {}, identity={},
                                     evidence_dir=str(current.directory))
        record.update(result=fa.UNTESTED, failed_step="rebuild", sequence=current.index,
                      reason=("needs rebuild - operator review: the branch is not VALID at this opening in the live case ("
                              + str(current.observed["needs_rebuild"])[:300] + "). No template was rebuilt."))
        self._current = None
        return self._finalize(record, current.directory, store=False)

    def _finish_candidate(self, current) -> StepEvent:
        steps = dict(current.steps)
        record = fa.candidate_record(current.stage, current.state, self.baseline, steps, identity=current.identity,
                                     evidence_dir=str(current.directory))
        record["sequence"] = current.index
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
            self._begin_restore(FOUND, f"Candidate {len(self.records)} ({change}) passed{warning}; staged for your review. "
                                       "Nothing was applied or saved.")
        elif reason == BLOCKED:
            self._begin_restore(BLOCKED, "Repeated setup errors: fix the setup shown in the diagnostics, then search again.")

    def should_stop(self) -> str:
        """FOUND / BLOCKED / '' after the latest record (checked by every finalize)."""

        if not self.records:
            return ""
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
        except Exception as exc:  # recorded, never hidden
            self.restore_issues.append(f"{name}: {exc}"[:300])
            self._restore_plan = []
        self._refresh()
        return StepEvent("restore", STEP_TITLES[name].replace("applying", "restoring"))

    def _finish_restore(self) -> StepEvent:
        if not self.restore_issues:
            try:
                observed = self._observe(self._restore_state, self._restore_observed)
                self.restore_issues += fa.precondition_issues({**observed, "base_delta_mm": 0.0}, self.limits)
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
        if self._declined_count:
            notes.append(f"{self._declined_count} candidate(s) were skipped (declined stage or skipped opening) and stay UNTESTED.")
        (self.root).mkdir(parents=True, exist_ok=True)
        (self.root / "advisor-ordered-report.md").write_text(
            fa.ordered_report_markdown(self.baseline, self.records, self.limits, notes=notes), encoding="utf-8")
        self._write(self.root, "advisor-ordered-records.json", self.records)

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
        record = dict(record or self.best_candidate() or {})
        if not record or record.get("result") not in (fa.PASSED, fa.WARNING_RESULT):
            raise ValueError("No passing candidate is staged.")
        missing = [item for item in self.required_acknowledgements(record) if item not in set(acknowledged)]
        if missing:
            raise PermissionError("Operator review required for: " + ", ".join(missing))
        eligibility = self.logic.evaluatePreparedBranchEligibility(self.node)
        if str(eligibility.get("branch_id") or "") != self.branch_id or str(
                (eligibility.get("branch") or {}).get("branch_foundation_fingerprint") or "") != self._base_identity["branch_foundation_fingerprint"]:
            raise ValueError("The active branch changed since the search; run it again.")
        config = working_configuration_record(record, self.saved_home, self.original)
        return self.logic.storeStep6WorkingConfiguration(self.node, config)
