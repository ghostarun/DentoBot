"""Feasibility Advisor: search for the smallest change that makes Step 6 plan.

Operator plan 2026-10-05 (S6-LIVE-01, step 3). When the default configuration
fails, the advisor tries the operator-approved levers, least invasive first,
finds the minimum value that passes, and reports a ranked recommendation.
Nothing is applied without operator approval: the runner restores the baseline
after the search.

Levers are deliberately limited. Never searched: contact allowances, guard
tolerances, the 1 mm approach-corridor minimum, tool geometry or the drill
axis. The mouth barrier is never disabled; only the operator-approved bounded
lip variants (2026-10-06) are levers.

The ordered search (operator 2026-10-06, S6-MULTI-TARGET-01) evaluates one
full candidate state at a time with structured v2 evidence and separates
setup errors, unreachable endpoints, endpoint collisions and route failures.

Pure functions only; the runtime runner (Testing/step6_feasibility_advisor_runner.py)
applies candidates through the existing GUI owners and evaluates them.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Lever ids and their meaning.
PLANNING_ATTEMPTS = "planning_attempts"  # RRTConnect attempts (planning time unchanged)
BASE_YAW_DEG = "base_yaw_deg"  # yaw about the Base's own axis, relative to the baseline
MOUTH_OPENING_MM = "mouth_opening_mm"  # Case Foundation target incisor gap
CORRIDOR_MARGIN_SAMPLES = "corridor_margin_samples"  # approach point backed off from first contact

# Cause class -> searchable levers and advisory lever texts: see LEVER_REGISTRY,
# CAUSE_CLASS_SEARCH and CAUSE_CLASS_ADVISORY below (single source, 2026-10-08).


@dataclass(frozen=True)
class Limits:
    """Operator bounds. The opening maximum should be the patient's measured maximum."""

    max_opening_mm: float = 46.0  # operator 2026-10-05: patient maximum opening
    opening_resolution_mm: float = 0.5
    opening_coarse_step_mm: float = 2.0
    yaw_step_deg: float = 5.0
    max_yaw_deg: float = 20.0
    attempts_ladder: tuple = (5, 10)
    default_attempts: int = 5  # project default STEP6_JOINT_PLANNING_ATTEMPTS
    margin_ladder: tuple = (1, 2, 4)
    # Acceptability weights: cost per unit of change (operator-tunable).
    cost_per_attempt: float = 0.05
    cost_per_yaw_deg: float = 0.2
    cost_per_opening_mm: float = 1.0
    cost_per_margin_sample: float = 0.02


@dataclass
class Candidate:
    levers: dict
    cost: float = 0.0
    result: str = "untested"  # untested | pass | fail | screen_fail
    detail: str = ""
    evidence_dir: str = ""
    trials: list = field(default_factory=list)


def candidate_cost(changes: Mapping[str, float], baseline: Mapping[str, float], limits: Limits) -> float:
    cost = 0.0
    if PLANNING_ATTEMPTS in changes:
        cost += limits.cost_per_attempt * max(0.0, changes[PLANNING_ATTEMPTS] - baseline.get(PLANNING_ATTEMPTS, 1))
    if BASE_YAW_DEG in changes:
        cost += limits.cost_per_yaw_deg * abs(changes[BASE_YAW_DEG])
    if CORRIDOR_MARGIN_SAMPLES in changes:
        cost += limits.cost_per_margin_sample * changes[CORRIDOR_MARGIN_SAMPLES]
    if MOUTH_OPENING_MM in changes:
        cost += limits.cost_per_opening_mm * max(0.0, changes[MOUTH_OPENING_MM] - baseline.get(MOUTH_OPENING_MM, 0.0))
    return round(cost, 4)


def yaw_ladder(limits: Limits) -> list:
    """+5, -5, +10, -10, ... up to the limit (smallest change first)."""
    values = []
    step = limits.yaw_step_deg
    k = 1
    while k * step <= limits.max_yaw_deg + 1e-9:
        values += [k * step, -k * step]
        k += 1
    return values


def opening_coarse_ladder(baseline_mm: float, limits: Limits) -> list:
    values = []
    value = baseline_mm + limits.opening_coarse_step_mm
    while value <= limits.max_opening_mm + 1e-9:
        values.append(round(value, 3))
        value += limits.opening_coarse_step_mm
    if not values or values[-1] < limits.max_opening_mm - 1e-9:
        values.append(float(limits.max_opening_mm))
    return values


def bisect_minimum(evaluate: Callable[[float], bool], low_fail: float, high_pass: float,
                   resolution: float) -> float:
    """Smallest passing value at ``resolution`` between a failing and a passing value."""
    low, high = float(low_fail), float(high_pass)
    while high - low > resolution + 1e-9:
        middle = round((low + high) / 2.0 / resolution) * resolution
        if middle <= low + 1e-9 or middle >= high - 1e-9:
            break
        if evaluate(middle):
            high = middle
        else:
            low = middle
    return high


def search_single_lever(lever: str, evaluate: Callable[[dict], bool], baseline: Mapping[str, float],
                        limits: Limits) -> dict | None:
    """Minimum passing change for one lever, or None. ``evaluate`` gets the change dict."""
    if lever == PLANNING_ATTEMPTS:
        for attempts in limits.attempts_ladder:
            if attempts > baseline.get(PLANNING_ATTEMPTS, 1) and evaluate({PLANNING_ATTEMPTS: attempts}):
                return {PLANNING_ATTEMPTS: attempts}
        return None
    if lever == CORRIDOR_MARGIN_SAMPLES:
        for margin in limits.margin_ladder:
            if evaluate({CORRIDOR_MARGIN_SAMPLES: margin}):
                return {CORRIDOR_MARGIN_SAMPLES: margin}
        return None
    if lever == BASE_YAW_DEG:
        for yaw in yaw_ladder(limits):
            if evaluate({BASE_YAW_DEG: yaw}):
                return {BASE_YAW_DEG: yaw}
        return None
    if lever == MOUTH_OPENING_MM:
        start = float(baseline.get(MOUTH_OPENING_MM, 40.0))
        previous = start
        for value in opening_coarse_ladder(start, limits):
            if evaluate({MOUTH_OPENING_MM: value}):
                best = bisect_minimum(lambda v: evaluate({MOUTH_OPENING_MM: v}), previous, value,
                                      limits.opening_resolution_mm)
                return {MOUTH_OPENING_MM: best}
            previous = value
        return None
    raise ValueError(f"Unknown lever {lever!r}")


def search(cause_class: str, evaluate: Callable[[dict], bool], baseline: Mapping[str, float],
           limits: Limits = Limits(), *, combine_with=None) -> list:
    """Return passing change sets (single levers first, then bounded pairs), cheapest first.

    ``combine_with`` (optional) lists fixed partial changes to pair with the
    opening search when no single lever passes (e.g. the best yaw values).
    """
    found = []
    # Reliability preflight (S6-LIVE-01 2026-10-05): a case policy below the
    # project default is a configuration error, not a geometry problem.
    if baseline.get(PLANNING_ATTEMPTS, limits.default_attempts) < limits.default_attempts:
        reset = {PLANNING_ATTEMPTS: limits.default_attempts}
        if evaluate(reset):
            return [reset]
    levers = CAUSE_CLASS_SEARCH.get(cause_class, CAUSE_CLASS_SEARCH["unknown"])
    for lever in levers:
        change = search_single_lever(lever, evaluate, baseline, limits)
        if change is not None:
            found.append(change)
    if not found and MOUTH_OPENING_MM in levers:
        for partial in combine_with or [{BASE_YAW_DEG: y} for y in yaw_ladder(limits)[:4]]:
            change = search_single_lever(
                MOUTH_OPENING_MM, lambda c, p=partial: evaluate({**p, **c}), baseline, limits)
            if change is not None:
                found.append({**partial, **change})
                break
    return sorted(found, key=lambda c: candidate_cost(c, baseline, limits))


def report_markdown(baseline: Mapping[str, float], cause_class: str, candidates: Sequence[Candidate],
                    recommended: Sequence[dict], limits: Limits) -> str:
    lines = [
        "# Feasibility Advisor report",
        "",
        "SIMULATION ONLY. Nothing was applied: the baseline was restored after the search.",
        "Planning reliability: independent re-plans are active (STEP6_JOINT_PLAN_RETRIES); a planning-attempts "
        "value below the project default is tried first as a reset, before any geometry lever.",
        "",
        f"**Baseline:** {dict(baseline)} · **Baseline cause class:** `{cause_class}`",
        f"**Limits:** opening ≤ {limits.max_opening_mm} mm (resolution {limits.opening_resolution_mm} mm), "
        f"yaw ≤ ±{limits.max_yaw_deg}° (step {limits.yaw_step_deg}°), attempts {list(limits.attempts_ladder)}",
        "",
        "| # | Change | Cost | Result | Detail | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    for index, candidate in enumerate(candidates, 1):
        detail = str(candidate.detail).replace("|", "/")[:160]
        lines.append(
            f"| {index} | {candidate.levers} | {candidate.cost} | {candidate.result} | {detail} | "
            f"{candidate.evidence_dir or '-'} |"
        )
    lines += ["", "## Recommendation (minimal change, cheapest first)", ""]
    if recommended:
        for change in recommended:
            lines.append(f"- {change} (cost {candidate_cost(change, baseline, limits)})")
    else:
        lines.append("- No change within the limits passed. Escalate: review limits, barrier, template or tool (operator).")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Ordered search with structured evidence (operator 2026-10-06,
# S6-MULTI-TARGET-01 FDI34). Agreed order: Base lateral -> lateral+vertical ->
# approved bounded lip variants -> opening <= max in 0.5 mm steps (lateral, then
# lateral+vertical at each opening) -> Base depth -> Base yaw last. Every
# candidate is a full state; nothing is inferred for an untested state.

ADVISOR_SCHEMA = "dentobot.feasibility_advisor.ordered/1"
BASE_U_MM = "base_u_mm"  # forehead lateral (patient left/right), relative to the saved Base
BASE_V_MM = "base_v_mm"  # forehead vertical (inferior/superior)
BASE_DEPTH_MM = "base_depth_mm"  # forehead normal
BARRIER_EDGE_MODE = "barrier_edge_mode"
LIP_MARGIN_MM = "lip_margin_mm"  # mouth_portal.LIP_LINE_MARGIN_MM
LIP_SLAB_MM = "lip_slab_mm"  # mouth_portal.BARRIER_LIP_THICKNESS_MM
PORTAL_ENLARGE_MM = "portal_enlarge_mm"  # mouth_portal.PORTAL_ENLARGE_MM
SPINDLE_TEMPLATE_ALLOWANCE = "spindle_template_allowance"  # step6AllowSpindleGuideContact
PLANNER_ID = "planner_id"
PLANNING_TIME_SEC = "planning_time_sec"

DEFAULT_BARRIER = {BARRIER_EDGE_MODE: "gum_line", LIP_MARGIN_MM: 2.0, LIP_SLAB_MM: 8.0, PORTAL_ENLARGE_MM: 5.0}
DEFAULT_POLICY = {PLANNER_ID: "RRTConnectkConfigDefault", PLANNING_ATTEMPTS: 5, PLANNING_TIME_SEC: 5.0}
# Operator-approved lip variants (2026-10-06): margin 2 -> 0, slab 8 -> 4, portal
# 5 -> 10 and their combinations. The stem-may-touch rule needs a housing/stem
# collision split that does not exist, so it is never generated here.
LIP_VARIANT_BOUNDS = {LIP_MARGIN_MM: (0.0, 2.0), LIP_SLAB_MM: (4.0, 8.0), PORTAL_ENLARGE_MM: (5.0, 10.0)}
# LIP_VARIANT_BOUNDS is only the representational hull shown by the registry. The permitted values are
# exactly the two per lever below (production default, approved endpoint); nothing in between is approved.
LIP_APPROVED_VALUES = {LIP_MARGIN_MM: (2.0, 0.0), LIP_SLAB_MM: (8.0, 4.0), PORTAL_ENLARGE_MM: (5.0, 10.0)}
LIP_SLAB_OBJECT_ID = "dentobot_mouth_barrier_lip_slab"  # MoveIt id of mouth_portal's "lip_slab" part
LIP_VARIANTS = (
    {LIP_MARGIN_MM: 0.0},
    {LIP_SLAB_MM: 4.0},
    {PORTAL_ENLARGE_MM: 10.0},
    {LIP_MARGIN_MM: 0.0, LIP_SLAB_MM: 4.0},
    {LIP_MARGIN_MM: 0.0, PORTAL_ENLARGE_MM: 10.0},
    {LIP_SLAB_MM: 4.0, PORTAL_ENLARGE_MM: 10.0},
    {LIP_MARGIN_MM: 0.0, LIP_SLAB_MM: 4.0, PORTAL_ENLARGE_MM: 10.0},
)
# STAGE_ORDER is derived from LEVER_REGISTRY (below), the single lever source.

# Candidate outcomes. The first four are failures and are never merged.
SETUP_ERROR = "setup_error"  # prerequisites, invalid Home, stale confirmation, scene mismatch
UNREACHABLE = "unreachable"  # stroke outside joint limits or no IK state without a contact
ENDPOINT_COLLISION = "endpoint_collision"  # a converged PreEntry state collides (named pairs)
ROUTE_FAILURE = "route_failure"  # corridor below the minimum, or P1-P3 failed
PASSED, WARNING_RESULT, UNTESTED = "pass", "warning", "untested"
FAILURE_CLASSES = (SETUP_ERROR, UNREACHABLE, ENDPOINT_COLLISION, ROUTE_FAILURE)
EVALUATION_STEPS = ("prerequisites", "stroke_reach", "preentry", "corridor", "diagnose")
DIAGNOSE_STAGE_CHECKS = ("p1_route", "p2_entry", "p3_drilling")

_PAIR_TEXT = re.compile(r"([A-Za-z0-9_.\-]+)\s*(?:<->|↔)\s*([A-Za-z0-9_.\-]+)")
_CONTACT_LIST = re.compile(r"contacts=(.*?)(?=\)|;|$)")


@dataclass(frozen=True)
class OrderedLimits:
    max_opening_mm: float = 46.0
    opening_step_mm: float = 0.5
    lateral_step_mm: float = 5.0
    lateral_range_mm: float = 30.0
    vertical_grid_step_mm: float = 10.0
    vertical_range_mm: float = 30.0
    depth_step_mm: float = 5.0
    depth_range_mm: float = 10.0
    yaw_step_deg: float = 5.0
    max_yaw_deg: float = 20.0
    corridor_minimum_mm: float = 1.0  # STEP6_APPROACH_CORRIDOR_MIN_MM; never relaxed
    home_tolerance_si: float = 1.0e-9
    base_tolerance_mm: float = 1.0e-6
    jaw_trajectory_tolerance_mm: float = 0.01
    template_bounds_tolerance_mm: float = 0.5
    template_centroid_tolerance_mm: float = 0.25
    template_volume_tolerance_fraction: float = 0.02
    template_surface_p95_tolerance_mm: float = 0.5



# ---------------------------------------------------------------------------
# Single lever registry (S6-ADVISOR-GUI-01, 2026-10-08). Diagnose's advisory
# levers (base_diagnosis), the legacy single-lever search and the ordered search
# all read this one table: priority (lower = tried earlier), approved bounds,
# whether a change is clinically sensitive (operator review gate before the first
# candidate and never auto-applied) and the existing owner that applies it.

@dataclass(frozen=True)
class LeverSpec:
    id: str
    label: str
    priority: int
    owner: str
    clinical_review: bool = False
    stage: str = ""  # ordered-search stage driven by this lever ("" = never auto-searched there)
    bounds: Mapping = field(default_factory=dict)

    @property
    def in_ordered_search(self) -> bool:
        return bool(self.stage)


_LIMITS = OrderedLimits()
LEVER_REGISTRY = {spec.id: spec for spec in (
    LeverSpec(PLANNING_ATTEMPTS, "Planning attempts/time", 10, "facade.setJointPlanningPolicy",
              bounds={PLANNING_ATTEMPTS: (1, 10), PLANNING_TIME_SEC: (0.5, 60.0)}),
    LeverSpec(CORRIDOR_MARGIN_SAMPLES, "Approach-corridor margin", 20, "facade.setApproachCorridorMarginSamples",
              bounds={CORRIDOR_MARGIN_SAMPLES: (0, 4)}),
    LeverSpec("find_reachable_base", "Find Reachable Base (6.1)", 29, "6.1 Find Reachable Base (operator tool)"),
    LeverSpec("base_lateral", "Base translation", 30, "facade.stageManualBaseReview/acceptManualBaseReview",
              stage="base_lateral",
              bounds={BASE_U_MM: (-_LIMITS.lateral_range_mm, _LIMITS.lateral_range_mm),
                      "step_mm": _LIMITS.lateral_step_mm}),
    LeverSpec("base_lateral_vertical", "Base translation (lateral + vertical)", 31,
              "facade.stageManualBaseReview/acceptManualBaseReview", stage="base_lateral_vertical",
              bounds={BASE_U_MM: (-_LIMITS.lateral_range_mm, _LIMITS.lateral_range_mm),
                      BASE_V_MM: (-_LIMITS.vertical_range_mm, _LIMITS.vertical_range_mm),
                      "grid_step_mm": _LIMITS.vertical_grid_step_mm}),
    LeverSpec("lip_variant", "Lip/mouth barrier variant (bounded; never disabled)", 40,
              "mouth_portal constants (operator-approved variants)", clinical_review=True,
              stage="lip_variant", bounds=dict(LIP_VARIANT_BOUNDS)),
    LeverSpec(MOUTH_OPENING_MM, "Mouth opening (+0.5 mm steps, within the patient maximum)", 50,
              "logic.createOrUpdateStep6CaseJawOpening (Case Foundation)", clinical_review=True,
              stage="opening", bounds={MOUTH_OPENING_MM: ("baseline", _LIMITS.max_opening_mm),
                                       "step_mm": _LIMITS.opening_step_mm}),
    LeverSpec("base_depth", "Base depth (forehead normal)", 60,
              "facade.stageManualBaseReview/acceptManualBaseReview", stage="base_depth",
              bounds={BASE_DEPTH_MM: (-_LIMITS.depth_range_mm, _LIMITS.depth_range_mm),
                      "step_mm": _LIMITS.depth_step_mm}),
    LeverSpec("target_review", "Review the PreEntry standoff and drill axis (operator)", 70,
              "operator", clinical_review=True),
    LeverSpec("template_review", "Template sleeve/relief review (operator, not automatic)", 71,
              "operator", clinical_review=True),
    LeverSpec("ik_budget", "PreEntry IK seeds/budget", 72, "facade.checkPreEntryIK"),
    LeverSpec("scene_resync", "Re-sync the Step 6 planning scene (6.1 Connect / scene sync), then re-run", 73,
              "6.1 Connect / scene sync"),
    LeverSpec("frame_check", "Stop: check the robot description and Base transform before any planning (operator)",
              74, "operator", clinical_review=True),
    LeverSpec(BASE_YAW_DEG, "Base yaw (±5° steps; last resort)", 90, "facade.stageManualBaseReview/acceptManualBaseReview",
              clinical_review=True, stage="base_yaw",
              bounds={BASE_YAW_DEG: (-_LIMITS.max_yaw_deg, _LIMITS.max_yaw_deg), "step_deg": _LIMITS.yaw_step_deg}),
    # A WARNING result (drilling shortened) is never auto-accepted; the search does not edit depth.
    LeverSpec("drilling_depth", "Drilling-depth truncation (WARNING; operator decision)", 99, "operator",
              clinical_review=True),
)}
# Ordered-search stages and the stages that need an explicit operator review gate.
STAGE_ORDER = tuple(spec.stage for spec in sorted(LEVER_REGISTRY.values(), key=lambda s: s.priority) if spec.stage)
SENSITIVE_STAGES = tuple(stage for stage in STAGE_ORDER
                         if LEVER_REGISTRY[next(s.id for s in LEVER_REGISTRY.values() if s.stage == stage)].clinical_review)
STAGE_PROMPTS = {
    "lip_variant": "Evaluate bounded lip/mouth-barrier variants? (The barrier is never disabled.)",
    "opening": f"Evaluate mouth openings up to {_LIMITS.max_opening_mm:g} mm in {_LIMITS.opening_step_mm:g} mm steps?",
    "base_yaw": f"Evaluate Base yaw up to ±{_LIMITS.max_yaw_deg:g}° (last resort)?",
}


def lever_for_stage(stage: str) -> LeverSpec:
    return next(spec for spec in LEVER_REGISTRY.values() if spec.stage == stage)


def stage_requires_review(stage: str) -> bool:
    return stage in SENSITIVE_STAGES


# Cause class -> searchable levers, least invasive first. Levers with no
# automatic owner are omitted; Base yaw is always last (operator 2026-10-06).
CAUSE_CLASS_SEARCH = {
    "narrow_passage": (PLANNING_ATTEMPTS, CORRIDOR_MARGIN_SAMPLES, MOUTH_OPENING_MM, BASE_YAW_DEG),
    "barrier": (MOUTH_OPENING_MM, BASE_YAW_DEG),
    "anatomy_neighbour": (MOUTH_OPENING_MM, BASE_YAW_DEG),
    "template": (BASE_YAW_DEG,),
    "solver": (PLANNING_ATTEMPTS, CORRIDOR_MARGIN_SAMPLES, MOUTH_OPENING_MM, BASE_YAW_DEG),
    "unknown": (PLANNING_ATTEMPTS, CORRIDOR_MARGIN_SAMPLES, MOUTH_OPENING_MM, BASE_YAW_DEG),
}
# Cause class -> advisory levers shown by Diagnose (lever id, operator text), least
# invasive first. Advisory only: contact allowances, guard tolerances and tool/axis
# changes are never suggested.
CAUSE_CLASS_ADVISORY = {
    "reach": (("find_reachable_base", "Find Reachable Base (6.1)"), ("base_lateral", "Base translation")),
    "anatomy_neighbour": ((MOUTH_OPENING_MM, "Mouth opening (+0.5 mm steps, within the patient maximum)"),
                          (BASE_YAW_DEG, "Base yaw (±5° steps; last resort)")),
    "target_tooth": (("target_review", "Review the PreEntry standoff and drill axis (operator)"),),
    "barrier": (("base_lateral", "Base translation"), (MOUTH_OPENING_MM, "Mouth opening"),
                (BASE_YAW_DEG, "Base yaw (±5° steps; last resort)")),
    "template": (("template_review", "Template sleeve/relief review (operator, not automatic)"),
                 (BASE_YAW_DEG, "Base yaw (±5° steps; last resort)")),
    "narrow_passage": ((PLANNING_ATTEMPTS, "Planning attempts/time"),
                       (CORRIDOR_MARGIN_SAMPLES, "Approach-corridor margin"),
                       (BASE_YAW_DEG, "Base yaw (±5° steps; last resort)")),
    "solver": (("ik_budget", "PreEntry IK seeds/budget"),),
    "scene_mismatch": (("scene_resync", "Re-sync the Step 6 planning scene (6.1 Connect / scene sync), then re-run"),),
    "frame_mismatch": (("frame_check", "Stop: check the robot description and Base transform before any planning (operator)"),),
    "unknown": (),
}


def advisory_lever_texts(cause_class: str) -> tuple:
    return tuple(text for _lever_id, text in CAUSE_CLASS_ADVISORY.get(cause_class, ()))


def baseline_state(opening_mm: float) -> dict:
    """Saved Base, default barrier and policy, no allowance, at ``opening_mm``."""
    return {
        MOUTH_OPENING_MM: float(opening_mm), BASE_U_MM: 0.0, BASE_V_MM: 0.0, BASE_DEPTH_MM: 0.0,
        BASE_YAW_DEG: 0.0, **DEFAULT_BARRIER, **DEFAULT_POLICY, CORRIDOR_MARGIN_SAMPLES: 0,
        SPINDLE_TEMPLATE_ALLOWANCE: False,
    }


def _symmetric_ladder(step: float, limit: float) -> list:
    values = [0.0]
    k = 1
    while k * step <= limit + 1e-9:
        values += [round(k * step, 6), round(-k * step, 6)]
        k += 1
    return values


def lateral_offsets(limits: OrderedLimits) -> list:
    """u = 0, +5, -5, +10, ... (v = depth = yaw = 0)."""
    return _symmetric_ladder(limits.lateral_step_mm, limits.lateral_range_mm)


def lateral_vertical_offsets(limits: OrderedLimits) -> list:
    """(u, v) with v != 0, least vertical first, then least lateral."""
    us = _symmetric_ladder(limits.vertical_grid_step_mm, limits.lateral_range_mm)
    vs = [v for v in _symmetric_ladder(limits.vertical_grid_step_mm, limits.vertical_range_mm) if v]
    pairs = [(u, v) for u in us for v in vs]
    return sorted(pairs, key=lambda p: (abs(p[1]), abs(p[0]), p[1] < 0, p[0] < 0))


def opening_ladder(baseline_mm: float, limits: OrderedLimits) -> list:
    """Absolute 0.5 mm grid strictly above the baseline, up to the patient maximum
    (40.06 -> 40.5, 41.0, ... 46.0)."""
    step = limits.opening_step_mm
    k = math.floor(float(baseline_mm) / step + 1e-9) + 1
    values = []
    while k * step <= limits.max_opening_mm + 1e-9:
        values.append(round(k * step, 3))
        k += 1
    return values


def ordered_candidates(baseline: Mapping, limits: OrderedLimits = OrderedLimits()) -> Iterator[tuple]:
    """Yield ``(stage, state)`` in the agreed order; the baseline itself is not yielded.

    Depth and yaw are generated at the baseline opening with the saved Base
    position (open question: whether they should also run at other openings).
    """
    base = dict(baseline)
    for u in lateral_offsets(limits):
        if u:
            yield "base_lateral", {**base, BASE_U_MM: u}
    for u, v in lateral_vertical_offsets(limits):
        yield "base_lateral_vertical", {**base, BASE_U_MM: u, BASE_V_MM: v}
    for variant in LIP_VARIANTS:
        yield "lip_variant", {**base, **variant}
    for opening in opening_ladder(base[MOUTH_OPENING_MM], limits):
        for u in lateral_offsets(limits):
            yield "opening", {**base, MOUTH_OPENING_MM: opening, BASE_U_MM: u}
        for u, v in lateral_vertical_offsets(limits):
            yield "opening", {**base, MOUTH_OPENING_MM: opening, BASE_U_MM: u, BASE_V_MM: v}
    for n in _symmetric_ladder(limits.depth_step_mm, limits.depth_range_mm):
        if n:
            yield "base_depth", {**base, BASE_DEPTH_MM: n}
    for yaw in yaw_ladder(Limits(yaw_step_deg=limits.yaw_step_deg, max_yaw_deg=limits.max_yaw_deg)):
        yield "base_yaw", {**base, BASE_YAW_DEG: yaw}


def state_violations(state: Mapping, baseline_opening_mm: float, limits: OrderedLimits = OrderedLimits(),
                     *, expected_corridor_margin_samples: int = 0) -> list:
    """Reasons a candidate state is outside the approved search (empty when valid)."""
    issues = []
    if str(state.get(BARRIER_EDGE_MODE)) != DEFAULT_BARRIER[BARRIER_EDGE_MODE]:
        issues.append(f"mouth barrier edge mode must stay {DEFAULT_BARRIER[BARRIER_EDGE_MODE]!r} (barrier never disabled)")
    for key, approved in LIP_APPROVED_VALUES.items():
        value = state.get(key)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not any(abs(float(value) - a) <= 1e-9 for a in approved)):
            issues.append(f"{key}={value!r} is not an approved value {approved[0]} (default) or {approved[1]}")
    if bool(state.get(SPINDLE_TEMPLATE_ALLOWANCE)):
        issues.append("spindle-template allowance must be OFF")
    if int(state.get(CORRIDOR_MARGIN_SAMPLES, 0) or 0) != int(expected_corridor_margin_samples):
        issues.append("corridor margin differs from the captured immutable guard setting")
    for key, value in DEFAULT_POLICY.items():
        if state.get(key) != value:
            issues.append(f"planning policy {key}={state.get(key)!r} differs from {value!r}")
    opening = float(state.get(MOUTH_OPENING_MM, -1.0))
    if opening > limits.max_opening_mm + 1e-9 or opening < float(baseline_opening_mm) - 1e-9:
        issues.append(f"opening {opening} mm outside {baseline_opening_mm}-{limits.max_opening_mm} mm")
    steps = opening / limits.opening_step_mm
    if abs(opening - float(baseline_opening_mm)) > 1e-9 and abs(steps - round(steps)) > 1e-6:
        issues.append(f"opening {opening} mm is not on the {limits.opening_step_mm} mm grid")
    if abs(float(state.get(BASE_YAW_DEG, 0.0))) > limits.max_yaw_deg + 1e-9:
        issues.append("Base yaw beyond the limit")
    return issues


def state_key(state: Mapping) -> str:
    """Canonical, rounding-stable key for one full candidate state."""
    def norm(value):
        return round(float(value), 4) if isinstance(value, float) else value
    return json.dumps({k: norm(v) for k, v in sorted(state.items())}, sort_keys=True)


def state_delta(state: Mapping, baseline: Mapping) -> dict:
    return {k: v for k, v in state.items() if baseline.get(k) != v}


def fingerprint_of(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ---- structured evidence -------------------------------------------------
def _normal_pair(a, b) -> tuple:
    return tuple(sorted((str(a).strip(), str(b).strip())))


def pairs_from_text(text) -> list:
    """Every pair in MoveIt's ``contacts=A<->B, C<->D (and N more)`` list; object ids
    may contain spaces (``[Step 5C] DENTO Final Printable Template``)."""
    text = str(text or "")
    pairs = []
    for block in _CONTACT_LIST.findall(text):
        block = re.sub(r"\s*\(and \d+ more$", "", block.strip())
        for item in block.split(", "):
            if "<->" in item:
                a, b = item.split("<->", 1)
                pairs.append(list(_normal_pair(a, b)))
    if not pairs:
        pairs = [list(_normal_pair(a, b)) for a, b in _PAIR_TEXT.findall(text)]
    unique = []
    for pair in pairs:
        if pair not in unique:
            unique.append(pair)
    return unique


def seed_contact_pairs(seed: Mapping) -> list:
    """Exact pairs for one IK seed: collision-aware IK pairs plus MoveIt's static
    validity contacts (which name pairs only in the message text)."""
    found = []
    for pair in seed.get("collision_pairs") or ():
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            found.append(list(_normal_pair(pair[0], pair[1])))
    found += pairs_from_text(seed.get("static_state_validity_message"))
    unique = []
    for pair in found:
        if pair not in unique:
            unique.append(pair)
    return unique


def lip_slab_blocker_evidence(record: Mapping | None) -> list:
    """Attributed contact evidence in ONE candidate record that names the lip slab.

    The approved lip variants run only when the current baseline's own recorded contacts
    (PreEntry seeds, approach corridor, Diagnose rows) include the lip slab. Absent or
    unknown evidence returns ``[]`` (the stage is then skipped, never assumed).
    """

    if not isinstance(record, Mapping):
        return []
    steps = record.get("steps") or {}
    found = []

    def note(step, pairs):
        for pair in pairs or ():
            if isinstance(pair, (list, tuple)) and LIP_SLAB_OBJECT_ID in [str(x).strip() for x in pair]:
                entry = {"step": step, "pair": [str(x).strip() for x in pair[:2]]}
                if entry not in found:
                    found.append(entry)

    for step in ("preentry", "corridor"):
        note(step, (steps.get(step) or {}).get("pairs"))
    diagnose = steps.get("diagnose") or {}
    note("diagnose", diagnose.get("pairs"))
    for row in ((diagnose.get("raw") or {}).get("rows") or ()):
        if isinstance(row, Mapping):
            note("diagnose:" + str(row.get("check")), row.get("blocking_pairs"))
    return [{**entry, "sequence": record.get("sequence"), "state_key": record.get("state_key"),
             "evidence_dir": record.get("evidence_dir"), "reused_from": record.get("reused_from")}
            for entry in found]


def classify_preentry(record: Mapping) -> dict:
    """Classify one authoritative PreEntry IK result (success/code/details/seeds)."""
    seeds = [dict(s) for s in record.get("seeds") or ()]
    status = str((record.get("details") or {}).get("diagnosticStatus") or "")
    per_seed = []
    for seed in seeds:
        pairs = seed_contact_pairs(seed)
        per_seed.append({
            "seed": seed.get("candidate_index"), "provenance": seed.get("seed_provenance"),
            "pairs": pairs, "joints_si": seed.get("best_joint_positions_si"),
            "termination": seed.get("termination_reason"), "classification": seed.get("failure_classification"),
            "static_validity": seed.get("static_state_validity_status"),
            "position_residual_mm": seed.get("position_residual_mm"),
            "axis_residual_deg": seed.get("drilling_axis_residual_deg"),
        })
    pairs = []
    for row in per_seed:
        pairs += [p for p in row["pairs"] if p not in pairs]
    out = {"status": status, "code": str(record.get("code") or ""), "seeds": per_seed, "pairs": pairs}
    if not record.get("success"):
        return {**out, "result": SETUP_ERROR, "reason": "PreEntry check refused: " + str(record.get("message") or "")[:300]}
    if status == "EndpointChecksPassed":
        valid = [s for s in seeds if s.get("static_state_validity_status") == "Valid"
                 and s.get("endpoint_check_status") == "Passed"]
        if valid:
            return {**out, "result": PASSED, "reason": f"{len(valid)} collision-checked PreEntry state(s)"}
        return {**out, "result": SETUP_ERROR, "reason": "EndpointChecksPassed without a Valid/Passed seed record"}
    if pairs:
        return {**out, "result": ENDPOINT_COLLISION,
                "reason": "converged PreEntry state(s) collide: " + "; ".join("<->".join(p) for p in pairs[:4])}
    if not seeds:
        return {**out, "result": SETUP_ERROR, "reason": f"no seed records ({status or 'no status'})"}
    return {**out, "result": UNREACHABLE, "reason": f"no PreEntry IK state and no named contact ({status})"}


def classify_corridor(result: Mapping, limits: OrderedLimits = OrderedLimits()) -> dict:
    """``result``: success/code/message/details of checkApproachCorridorClearance."""
    details = dict(result.get("details") or {})
    corridor = details.get("corridor_mm")
    out = {"corridor_mm": corridor, "minimum_mm": details.get("minimum_mm"), "code": str(result.get("code") or ""),
           "pairs": pairs_from_text(details.get("blocked_message")),
           "first_blocked_state": details.get("first_blocked_state"),
           "validity_authoritative": details.get("validity_authoritative")}
    if details.get("minimum_mm") is not None and abs(float(details["minimum_mm"]) - limits.corridor_minimum_mm) > 1e-9:
        return {**out, "result": SETUP_ERROR, "reason": f"corridor minimum changed to {details['minimum_mm']} mm"}
    if result.get("success") and corridor is not None and float(corridor) >= limits.corridor_minimum_mm - 1e-9:
        if details.get("validity_authoritative") is False:
            return {**out, "result": SETUP_ERROR, "reason": "corridor validity queries were not authoritative"}
        return {**out, "result": PASSED, "reason": f"corridor {float(corridor):.2f} mm"}
    code = out["code"]
    if code in ("approach_corridor_blocked", "approach_corridor_unavailable"):
        return {**out, "result": ROUTE_FAILURE, "reason": str(result.get("message") or "")[:300]}
    return {**out, "result": SETUP_ERROR, "reason": "corridor check could not run: " + str(result.get("message") or "")[:300]}


def classify_diagnosis(summary: Mapping) -> dict:
    """Full Diagnose acceptance: scene, stroke, PreEntry, P1, P2 and P3 must all run
    and be PASS/WARNING. An endpoint pass alone is never success."""
    rows = {str(r.get("check")): dict(r) for r in summary.get("rows") or ()}
    status = str(summary.get("status") or "")
    out = {"status": status, "verdict": summary.get("verdict"), "pairs": list(summary.get("blocking_pairs") or ()),
           "rows": [(r.get("check"), r.get("status"), str(r.get("detail") or "")[:300]) for r in summary.get("rows") or ()]}
    failing = next((r for r in summary.get("rows") or () if r.get("status") == "FAIL"), None)
    if failing is not None:
        check = str(failing.get("check"))
        result = {"scene_match": SETUP_ERROR, "frame_match": SETUP_ERROR, "stroke_reach": UNREACHABLE,
                  "preentry_endpoint": ENDPOINT_COLLISION if failing.get("blocking_pairs") else UNREACHABLE,
                  }.get(check, ROUTE_FAILURE)
        if check == "preentry_endpoint" and "could not run" in str(failing.get("detail")):
            result = SETUP_ERROR
        return {**out, "result": result, "failed_check": check, "reason": str(failing.get("detail") or "")[:400]}
    missing = [c for c in DIAGNOSE_STAGE_CHECKS if rows.get(c, {}).get("status") not in ("PASS", "WARNING")]
    if missing or status not in ("PASS", "WARNING"):
        return {**out, "result": SETUP_ERROR, "failed_check": (missing or ["verdict"])[0],
                "reason": f"Diagnose incomplete ({status}); not run: {', '.join(missing) or '-'}"}
    return {**out, "result": WARNING_RESULT if status == "WARNING" else PASSED, "failed_check": "",
            "reason": str(summary.get("verdict") or "")[:400]}


def precondition_issues(observed: Mapping, limits: OrderedLimits = OrderedLimits()) -> list:
    """Setup checks that must hold before any geometric evaluation of a candidate."""
    issues = []
    if not observed.get("ros_connected"):
        issues.append("ROS/MoveIt runtime not connected")
    if not observed.get("base_locked"):
        issues.append("Base not accepted/locked")
    delta = observed.get("base_delta_mm")
    if delta is None or float(delta) > limits.base_tolerance_mm:
        issues.append(f"accepted Base differs from the requested candidate ({delta} mm)")
    if observed.get("home_gap"):
        issues.append("Task Home not validated: " + str(observed["home_gap"])[:200])
    home_delta = observed.get("home_delta_si")
    if home_delta is None or float(home_delta) > limits.home_tolerance_si:
        issues.append(f"Task Home differs from the saved Home ({home_delta})")
    if observed.get("task_confirmation_issues"):
        issues.append("stale task confirmation: " + "; ".join(map(str, observed["task_confirmation_issues"]))[:240])
    scene = str(observed.get("scene_state") or "")
    if scene not in ("matched", "resynced"):
        issues.append(f"MoveIt scene does not match Slicer ({scene or 'not checked'}): "
                      + str(observed.get("scene_message") or "")[:200])
    for issue in observed.get("collision_audit_issues") or ():
        issues.append("collision audit: " + str(issue)[:200])
    for key, label in (("barrier_issues", "barrier"), ("policy_issues", "policy"), ("geometry_issues", "geometry")):
        for issue in observed.get(key) or ():
            issues.append(f"{label}: {issue}")
    if observed.get("spindle_template_allowance"):
        issues.append("spindle-template allowance is ON")
    return issues


def compare_geometry(reference: Mapping, candidate: Mapping, limits: OrderedLimits = OrderedLimits()) -> dict:
    """Jaw-local consistency of a rebuilt branch against the reference branch.

    Each summary: ``trajectory_mm`` (Entry/Target, jaw-local) and ``template``
    (jaw-local bounds, centroid, volume, two-sided surface distance to the reference).
    """
    rows = []

    def row(name, value, tolerance):
        ok = value is not None and math.isfinite(float(value)) and float(value) <= tolerance + 1e-12
        rows.append({"check": name, "value": None if value is None else round(float(value), 4),
                     "tolerance": tolerance, "status": "PASS" if ok else "FAIL"})

    ref_t, cand_t = reference.get("trajectory_mm"), candidate.get("trajectory_mm")
    traj = None
    if ref_t and cand_t and len(ref_t) == len(cand_t):
        traj = max(abs(float(a) - float(b)) for p, q in zip(ref_t, cand_t) for a, b in zip(p, q))
    row("jaw_local_trajectory_max_delta_mm", traj, limits.jaw_trajectory_tolerance_mm)
    ref_m, cand_m = reference.get("template") or {}, candidate.get("template") or {}
    bounds = None
    if ref_m.get("bounds") and cand_m.get("bounds"):
        bounds = max(abs(float(a) - float(b)) for a, b in zip(ref_m["bounds"], cand_m["bounds"]))
    row("template_bounds_max_delta_mm", bounds, limits.template_bounds_tolerance_mm)
    centroid = None
    if ref_m.get("centroid") and cand_m.get("centroid"):
        centroid = math.dist([float(v) for v in ref_m["centroid"]], [float(v) for v in cand_m["centroid"]])
    row("template_centroid_delta_mm", centroid, limits.template_centroid_tolerance_mm)
    volume = None
    if ref_m.get("volume_mm3") and cand_m.get("volume_mm3") is not None:
        volume = abs(float(cand_m["volume_mm3"]) - float(ref_m["volume_mm3"])) / float(ref_m["volume_mm3"])
    row("template_volume_delta_fraction", volume, limits.template_volume_tolerance_fraction)
    row("template_surface_distance_p95_mm", cand_m.get("surface_distance_p95_mm"),
        limits.template_surface_p95_tolerance_mm)
    return {"status": "PASS" if all(r["status"] == "PASS" for r in rows) else "FAIL", "rows": rows,
            "template_surface_distance_max_mm": cand_m.get("surface_distance_max_mm")}


def candidate_record(stage: str, state: Mapping, baseline: Mapping, steps: Mapping, *, identity: Mapping,
                     evidence_dir: str = "", reused_from: str = "") -> dict:
    """One candidate: stop at the first failing evaluation step, keep its full evidence."""
    result, failed_step, reason = PASSED, "", ""
    for name in EVALUATION_STEPS:
        step = steps.get(name)
        if step is None:
            result, failed_step, reason = SETUP_ERROR, name, f"{name} not evaluated"
            break
        if step.get("result") not in (PASSED, WARNING_RESULT):
            result, failed_step, reason = step.get("result") or SETUP_ERROR, name, str(step.get("reason") or "")
            break
        if step.get("result") == WARNING_RESULT:
            result = WARNING_RESULT
    if result in (PASSED, WARNING_RESULT):
        reason = str(steps["diagnose"].get("reason") or "")
    return {
        "schema": ADVISOR_SCHEMA, "stage": stage, "state": dict(state), "state_key": state_key(state),
        "change": state_delta(state, baseline), "result": result, "failed_step": failed_step,
        "reason": reason[:500], "steps": {k: v for k, v in steps.items() if v is not None},
        "identity": dict(identity), "identity_fingerprint": fingerprint_of(identity),
        "evidence_dir": evidence_dir, "reused_from": reused_from,
    }


class CheckpointStore:
    """Append-only JSONL of completed candidates; reused only on an exact identity match.

    Records without the ordered schema (e.g. the v1/v2 harness JSON) are never reused.
    """

    def __init__(self, path):
        self.path = Path(path)

    def records(self) -> list:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def lookup(self, state: Mapping, identity: Mapping) -> dict | None:
        key, wanted = state_key(state), fingerprint_of(identity)
        for record in reversed(self.records()):
            if (record.get("schema") == ADVISOR_SCHEMA and record.get("state_key") == key
                    and record.get("identity_fingerprint") == wanted
                    and record.get("result") in (PASSED, WARNING_RESULT, *FAILURE_CLASSES)
                    and record.get("result") != SETUP_ERROR):
                return record
        return None

    def append(self, record: Mapping) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def untested_summary(records: Sequence[Mapping], baseline: Mapping, limits: OrderedLimits = OrderedLimits(),
                     extra_untested: Sequence[Mapping] = ()) -> dict:
    """Count, per stage, generated states with no record; they stay UNTESTED (never failed)."""
    done = {r.get("state_key") for r in records}
    counts = {}
    for stage, state in ordered_candidates(baseline, limits):
        if state_key(state) not in done:
            counts[stage] = counts.get(stage, 0) + 1
    return {"untested_per_stage": counts, "explicit": [dict(e) for e in extra_untested]}


def ordered_report_markdown(baseline: Mapping, records: Sequence[Mapping], limits: OrderedLimits = OrderedLimits(),
                            *, extra_untested: Sequence[Mapping] = (), notes: Sequence[str] = ()) -> str:
    lines = [
        "# Feasibility Advisor — ordered search report",
        "",
        "SIMULATION ONLY. Nothing is applied or accepted by this report; a pass is a candidate for "
        "operator review, never a minimum opening or an optimal Base.",
        "",
        f"**Order:** {' → '.join(STAGE_ORDER)} · **Baseline:** `{state_key(baseline)}`",
        f"**Fixed:** barrier {DEFAULT_BARRIER} (never disabled), corridor minimum {limits.corridor_minimum_mm} mm, "
        f"policy {DEFAULT_POLICY}, spindle-template allowance OFF",
        "",
        "| # | Stage | Change | Result | Failed step | Reason | Pairs | Corridor mm | Identity | Evidence |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for index, record in enumerate(records, 1):
        steps = record.get("steps") or {}
        pairs = []
        for step in steps.values():
            pairs += ["<->".join(map(str, p[:2])) for p in step.get("pairs") or () if isinstance(p, (list, tuple))]
        corridor = (steps.get("corridor") or {}).get("corridor_mm")
        reason = str(record.get("reason") or "").replace("|", "/")[:180]
        lines.append(
            f"| {index} | {record.get('stage')} | {record.get('change')} | {record.get('result')} | "
            f"{record.get('failed_step') or '-'} | {reason} | {'; '.join(sorted(set(pairs)))[:160] or '-'} | "
            f"{'-' if corridor is None else round(float(corridor), 2)} | {record.get('identity_fingerprint')} | "
            f"{record.get('evidence_dir') or '-'}{' (reused)' if record.get('reused_from') else ''} |")
    summary = untested_summary(records, baseline, limits, extra_untested)
    lines += ["", "## Untested (no inference)", ""]
    for item in summary["explicit"]:
        lines.append(f"- {item}")
    for stage in STAGE_ORDER:
        if summary["untested_per_stage"].get(stage):
            lines.append(f"- {stage}: {summary['untested_per_stage'][stage]} generated state(s) untested")
    if notes:
        lines += ["", "## Notes", ""] + [f"- {note}" for note in notes]
    return "\n".join(lines) + "\n"
