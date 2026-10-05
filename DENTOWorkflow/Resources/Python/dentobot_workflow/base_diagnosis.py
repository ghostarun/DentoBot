"""Diagnose This Base: ordered Step 6 checks and the first failing cause.

Operator decision 2026-10-02 (`S6-BASE-DIAGNOSE`). The checks run in a fixed
order and stop at the first failure:

1. stroke reach at the accepted Base   -> base placement
2. PreEntry endpoint (IK + collision)  -> collision or solver
3. P1 Home -> PreEntry route           -> mouth barrier, route collision, planner
4. P2 PreEntry -> Entry                -> entry collision
5. P3 Entry -> Target drilling         -> drilling collision; a spindle-housing
                                          truncation is a warning (policy 2b)

Pure functions only; the facade runs the existing checks and passes their
results here. Diagnostics carry no route or preview authority.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

CHECK_ORDER = ("stroke_reach", "preentry_endpoint", "p1_route", "p2_entry", "p3_drilling")
CHECK_TITLES = {
    "stroke_reach": "1. Base reaches the whole drilling stroke",
    "preentry_endpoint": "2. PreEntry endpoint is reachable and collision-free",
    "p1_route": "3. Route Task Home → PreEntry",
    "p2_entry": "4. Approach PreEntry → Entry",
    "p3_drilling": "5. Drilling Entry → Target",
}
CAUSE_TITLES = {
    "base_placement": "Base placement",
    "endpoint_collision": "Collision at PreEntry",
    "solver": "IK solver",
    "mouth_barrier": "Mouth barrier",
    "route_collision": "Collision on the Home → PreEntry route",
    "planner_corridor": "Planner / approach corridor",
    "entry_collision": "Collision PreEntry → Entry",
    "drilling_collision": "Collision while drilling",
    "tool_geometry": "Tool geometry (drilling shortened)",
    "unknown": "Unknown",
}
PASS, FAIL, WARNING, NOT_RUN = "PASS", "FAIL", "WARNING", "NOT RUN"

# Cause classes (operator 2026-10-05, Feasibility Advisor step 1): what kind of
# thing blocks the plan, independent of which check found it.
CAUSE_CLASS_TITLES = {
    "reach": "Reach / joint limits",
    "anatomy_neighbour": "Neighbouring anatomy",
    "target_tooth": "Target tooth",
    "barrier": "Mouth barrier (lip slab / cheek)",
    "template": "Final printable template",
    "narrow_passage": "Narrow passage (endpoints valid, planner found no route)",
    "solver": "IK solver",
    "unknown": "Unknown",
}
# Least invasive first. Advisory only: nothing here is applied automatically, and
# contact allowances, guard tolerances and tool/axis changes are never suggested.
CAUSE_CLASS_LEVERS = {
    "reach": ("Find Reachable Base (6.1)", "Base translation"),
    "anatomy_neighbour": ("Mouth opening (+0.5 mm steps, within the patient maximum)", "Base yaw (±5° steps)"),
    "target_tooth": ("Review the PreEntry standoff and drill axis (operator)",),
    "barrier": ("Base yaw (±5° steps)", "Base translation", "Mouth opening"),
    "template": ("Base yaw (±5° steps)", "Template sleeve/relief review (operator, not automatic)"),
    "narrow_passage": ("Planning attempts/time", "Approach-corridor margin", "Base yaw (±5° steps)"),
    "solver": ("PreEntry IK seeds/budget",),
    "unknown": (),
}
_CONTACTS = re.compile(r"contacts=(.+?)<->([^\s;,)]+)")
_EMPTY_PLAN = ("empty trajectory", "code=99999")


def classify_body(name) -> str:
    text = str(name or "")
    lower = text.lower()
    if lower.startswith("dentobot_mouth_barrier"):
        return "barrier"
    if lower.startswith("dentobot_target_tooth"):
        return "target_tooth"
    if lower.startswith(("dentobot_tooth", "dentobot_jaw")):
        return "anatomy_neighbour"
    if any(word in text for word in ("Template", "Docking", "Support", "Guide")):
        return "template"
    if lower == "burr":
        return "burr"
    if lower.startswith("pneumatic_spindle"):
        return "spindle_housing"
    if lower.startswith("link-") or lower == "base_link":
        return "arm_link"
    return "unknown"


def classify_pair(pair) -> dict:
    """Name the obstacle class and the robot/tool part of one contact pair."""
    if not (isinstance(pair, Sequence) and not isinstance(pair, str) and len(pair) >= 2):
        return {}
    kinds = [classify_body(pair[0]), classify_body(pair[1])]
    tool = [k for k in kinds if k in ("burr", "spindle_housing", "arm_link")]
    obstacle = [k for k in kinds if k not in ("burr", "spindle_housing", "arm_link")]
    return {
        "bodies": [str(pair[0]), str(pair[1])],
        "cause_class": obstacle[0] if obstacle else "unknown",
        "tool_part": tool[0] if tool else "unknown",
    }


def contact_pairs_from_text(text) -> list:
    """Pairs named as ``contacts=A<->B`` in planner/validity messages."""
    return [[a.strip(), b.strip()] for a, b in _CONTACTS.findall(str(text or ""))]


def _row(check: str, status: str, detail: str, cause: str = "", *,
         cause_class: str = "", pairs=()) -> dict:
    classified = [c for c in (classify_pair(p) for p in pairs) if c]
    if not cause_class and classified:
        cause_class = classified[0]["cause_class"]
    return {
        "cause_class": cause_class,
        "cause_class_title": CAUSE_CLASS_TITLES.get(cause_class, "") if cause_class else "",
        "blocking_pairs": classified,
        "check": check,
        "title": CHECK_TITLES[check],
        "status": status,
        "cause": cause,
        "cause_title": CAUSE_TITLES.get(cause, "") if cause else "",
        "detail": str(detail),
    }


def _pair_text(pair) -> str:
    if isinstance(pair, Sequence) and not isinstance(pair, str) and len(pair) >= 2:
        return f"{pair[0]} ↔ {pair[1]}"
    return ""


def stroke_row(stroke: Mapping | None) -> dict:
    if not isinstance(stroke, Mapping):
        return _row("stroke_reach", FAIL, "Stroke reachability is unavailable.", "unknown")
    if stroke.get("reachable"):
        return _row("stroke_reach", PASS, "PreEntry, Entry and Target are inside the joint limits.")
    station = stroke.get("first_failed_station") or "unknown station"
    return _row(
        "stroke_reach",
        FAIL,
        f"The accepted Base cannot reach {station} inside the joint limits. "
        "Use Find Reachable Base in 6.1.",
        "base_placement",
        cause_class="reach",
    )


def preentry_row(diagnostic_status: str, candidate_records: Sequence[Mapping] = ()) -> dict:
    if diagnostic_status == "EndpointChecksPassed":
        return _row("preentry_endpoint", PASS, "At least one collision-checked PreEntry state exists.")
    pairs = []
    raw_pairs = []
    collision = False
    for record in candidate_records or ():
        classification = str(record.get("failure_classification") or "")
        if "collision" in classification:
            collision = True
        for pair in record.get("collision_pairs") or ():
            text = _pair_text(pair)
            if text and text not in pairs:
                pairs.append(text)
                raw_pairs.append(pair)
    if collision or pairs:
        named = f" ({'; '.join(pairs[:3])})" if pairs else ""
        return _row(
            "preentry_endpoint",
            FAIL,
            f"The arm reaches PreEntry, but every candidate state collides{named}.",
            "endpoint_collision",
            pairs=raw_pairs,
        )
    return _row(
        "preentry_endpoint",
        FAIL,
        f"PreEntry IK found no state ({diagnostic_status or 'no result'}) although the stroke "
        "check passed; the solver budget or seeds are the suspect.",
        "solver",
        cause_class="solver",
    )


def stage_row(phase_id: str, outcome: Mapping | None) -> dict:
    check = {"P1": "p1_route", "P2": "p2_entry", "P3": "p3_drilling"}[phase_id]
    if not isinstance(outcome, Mapping):
        return _row(check, FAIL, f"{phase_id} returned no result.", "unknown")
    evidence = outcome.get("endpoint_evidence") or {}
    plan = evidence.get("plan") or {}
    guard = evidence.get("phase_guard") or {}
    truncation = plan.get("drilling_truncation")
    status = str(outcome.get("diagnostic_status") or "")
    if status == "passed":
        if phase_id == "P3" and isinstance(truncation, Mapping):
            pair = _pair_text(truncation.get("blocking_pair"))
            return _row(
                check,
                WARNING,
                f"Drilling shortened: {float(truncation.get('completed_depth_mm', 0.0)):.2f} of "
                f"{float(truncation.get('requested_depth_mm', 0.0)):.2f} mm reached; "
                f"{float(truncation.get('remaining_depth_mm', 0.0)):.2f} mm not completed"
                + (f" ({pair})" if pair else "") + ".",
                "tool_geometry",
                pairs=[truncation.get("blocking_pair")] if pair else (),
            )
        return _row(check, PASS, str(outcome.get("reason") or "Passed."))
    reason = str(outcome.get("reason") or "Stage checks did not pass.")
    gate = evidence.get("mouth_portal_gate")
    if phase_id == "P1" and isinstance(gate, Mapping) and gate.get("status") not in (None, "passed", "skipped"):
        return _row(check, FAIL, reason, "mouth_barrier", cause_class="barrier")
    raw = []
    for candidate in (guard.get("named_pair"), *(plan.get("first_invalid_collision_pairs") or ())):
        if _pair_text(candidate) and list(candidate[:2]) not in raw:
            raw.append(list(candidate[:2]))
    # A blocked approach corridor names its pair only in the message text.
    for candidate in contact_pairs_from_text(reason) + contact_pairs_from_text(plan.get("message")):
        if candidate not in raw:
            raw.append(candidate)
    if raw:
        cause = {"P1": "route_collision", "P2": "entry_collision", "P3": "drilling_collision"}[phase_id]
        return _row(check, FAIL, f"{reason} Blocking pair: {_pair_text(raw[0])}.", cause, pairs=raw)
    if status == "unknown":
        # Never silent: name the evidence that could not be established.
        why = str(guard.get("reason") or "") if guard.get("status") == "unknown" else ""
        detail = f"{reason} Guard evidence unavailable: {why}" if why else reason
        return _row(check, FAIL, detail, "unknown", cause_class="unknown")
    cause = {"P1": "planner_corridor", "P2": "entry_collision", "P3": "drilling_collision"}[phase_id]
    empty = any(marker in reason for marker in _EMPTY_PLAN)
    return _row(check, FAIL, reason, cause, cause_class="narrow_passage" if empty else "unknown")


def summarize(rows: Sequence[Mapping]) -> dict:
    """Complete the ordered table (NOT RUN after the first failure) and the verdict."""
    by_check = {row["check"]: dict(row) for row in rows}
    table = []
    stopped = False
    verdict_row = None
    warning_row = None
    for check in CHECK_ORDER:
        row = by_check.get(check)
        if stopped or row is None:
            table.append(_row(check, NOT_RUN, "Not run: an earlier check failed." if stopped else "Not run."))
            stopped = stopped or row is None
            continue
        table.append(row)
        if row["status"] == FAIL:
            stopped = True
            verdict_row = row
        elif row["status"] == WARNING and warning_row is None:
            warning_row = row
    if verdict_row is not None:
        status, cause, detail = FAIL, verdict_row["cause"] or "unknown", verdict_row["detail"]
    elif all(row["status"] in (PASS, WARNING) for row in table):
        if warning_row is not None:
            status, cause, detail = WARNING, warning_row["cause"], warning_row["detail"]
        else:
            status, cause, detail = PASS, "", "Base, endpoints, route and drilling stroke all passed."
    else:
        status, cause, detail = NOT_RUN, "unknown", "The diagnosis did not complete."
    verdict = (
        f"{CAUSE_TITLES.get(cause, cause)}: {detail}" if cause else detail
    )
    source = verdict_row if verdict_row is not None else warning_row
    cause_class = str((source or {}).get("cause_class") or "")
    levers = list(CAUSE_CLASS_LEVERS.get(cause_class, ())) if status == FAIL else []
    if status == FAIL and cause_class:
        verdict += f" Cause class: {CAUSE_CLASS_TITLES.get(cause_class, cause_class)}."
        parts = sorted({p["tool_part"] for p in (source or {}).get("blocking_pairs") or () if p.get("tool_part") != "unknown"})
        if parts:
            verdict += " Tool part: " + ", ".join(part.replace("_", " ") for part in parts) + "."
        if levers:
            verdict += " Suggested levers (advisory, least invasive first): " + "; ".join(levers) + "."
    return {
        "status": status,
        "cause": cause,
        "cause_class": cause_class,
        "blocking_pairs": list((source or {}).get("blocking_pairs") or ()),
        "suggested_levers": levers,
        "verdict": verdict,
        "rows": table,
    }
