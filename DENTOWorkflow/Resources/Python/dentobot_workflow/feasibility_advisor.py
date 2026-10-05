"""Feasibility Advisor: search for the smallest change that makes Step 6 plan.

Operator plan 2026-10-05 (S6-LIVE-01, step 3). When the default configuration
fails, the advisor tries the operator-approved levers, least invasive first,
finds the minimum value that passes, and reports a ranked recommendation.
Nothing is applied without operator approval: the runner restores the baseline
after the search.

Levers are deliberately limited. Never searched: contact allowances, guard
tolerances, mouth-barrier constants, tool geometry or the drill axis.

Pure functions only; the runtime runner (Testing/step6_feasibility_advisor_runner.py)
applies candidates through the existing GUI owners and evaluates them.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

# Lever ids and their meaning.
PLANNING_ATTEMPTS = "planning_attempts"  # RRTConnect attempts (planning time unchanged)
BASE_YAW_DEG = "base_yaw_deg"  # yaw about the Base's own axis, relative to the baseline
MOUTH_OPENING_MM = "mouth_opening_mm"  # Case Foundation target incisor gap
CORRIDOR_MARGIN_SAMPLES = "corridor_margin_samples"  # approach point backed off from first contact

# Cause class -> searchable levers, least invasive first (mirrors
# base_diagnosis.CAUSE_CLASS_LEVERS; levers with no automatic owner are omitted).
CAUSE_CLASS_SEARCH = {
    # Base yaw is one of the last preferred adjustments in the robot design
    # (operator 2026-10-06): always searched after every other lever.
    "narrow_passage": (PLANNING_ATTEMPTS, CORRIDOR_MARGIN_SAMPLES, MOUTH_OPENING_MM, BASE_YAW_DEG),
    "barrier": (MOUTH_OPENING_MM, BASE_YAW_DEG),
    "anatomy_neighbour": (MOUTH_OPENING_MM, BASE_YAW_DEG),
    "template": (BASE_YAW_DEG,),
    "solver": (PLANNING_ATTEMPTS, CORRIDOR_MARGIN_SAMPLES, MOUTH_OPENING_MM, BASE_YAW_DEG),
    "unknown": (PLANNING_ATTEMPTS, CORRIDOR_MARGIN_SAMPLES, MOUTH_OPENING_MM, BASE_YAW_DEG),
}


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
