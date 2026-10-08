"""Per-PreparedBranch Step 6 working configuration (S6-MULTI-JAW-STALE-01, 2026-10-07).

Step 6 is distinct per branch: each target tooth/trajectory may need its own mouth
opening, robot Base, Task Home and planning policy. The configuration that made a
branch work is stored on that branch's final-template node (saved with the
dentocase, switched with the branch) and re-applied on activation through the
normal Step 6 owners. Task Home is only staged as the jog draft: nothing moves
without the operator. ``barrier_tuning`` (lip margin/slab/portal enlargement, approved
bounds only) is optional; absent means the production defaults.

Pure helpers only (no Slicer imports). Simulation research configuration; not a
clinical prescription.
"""

from __future__ import annotations

import json
import math
from typing import Mapping

from . import mouth_portal

SCHEMA = "dentobot.step6.working_config.v1"
ATTRIBUTE = "DENTOBOT.Step6WorkingConfigJson"
# Research store used before 2026-10-07 (Testing/step6_branch_config.py).
RESEARCH_NODE_NAME = "[Research] DENTO Step 6 Working Configurations"
RESEARCH_ATTRIBUTE_PREFIX = "DENTOBOT.Research.Step6Config."

OPENING_TOLERANCE_MM = 1e-6
BASE_TOLERANCE_MM = 1e-6
HOME_TOLERANCE_SI = 1e-9
BARRIER_TOLERANCE_MM = 1e-9


def _finite(value, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def normalize(record: Mapping) -> dict:
    """Validated, canonical record; raises ValueError on anything malformed."""
    if not isinstance(record, Mapping):
        raise ValueError("working configuration must be an object")
    config = record.get("config", record)
    base = config.get("base_world_mm")
    rows = [list(row) for row in base] if base is not None else None
    if rows is None or len(rows) != 4 or any(len(row) != 4 for row in rows):
        raise ValueError("base_world_mm must be a 4x4 matrix")
    home = config.get("task_home_si")
    if home is not None and not isinstance(home, Mapping):
        raise ValueError("task_home_si must map joint names to SI values")
    opening = _finite(config["mouth_opening_mm"], "mouth_opening_mm")
    if opening <= 0:
        raise ValueError("mouth_opening_mm must be positive")
    attempts = int(config.get("planning_attempts", 5))
    seconds = _finite(config.get("planning_time_sec", 5.0), "planning_time_sec")
    if attempts < 1 or seconds <= 0:
        raise ValueError("planning policy must be positive")
    tuning_raw = config.get("barrier_tuning")
    if tuning_raw is None:
        tuning = dict(mouth_portal.DEFAULT_BARRIER_TUNING)
    elif not isinstance(tuning_raw, Mapping) or set(tuning_raw) != set(mouth_portal.BARRIER_TUNING_KEYS):
        raise ValueError("barrier_tuning must map exactly lip_margin_mm, lip_slab_mm and portal_enlarge_mm")
    else:
        tuning = mouth_portal.validated_barrier_tuning(**{k: tuning_raw[k] for k in mouth_portal.BARRIER_TUNING_KEYS})
    return {
        "schema": SCHEMA,
        "branch_id": str(record.get("branch_id") or ""),
        "branch_foundation_fingerprint": str(record.get("branch_foundation_fingerprint") or ""),
        "config": {
            "mouth_opening_mm": opening,
            "base_world_mm": [[_finite(v, "base_world_mm") for v in row] for row in rows],
            "task_home_si": None if home is None else {str(k): _finite(v, "task_home_si") for k, v in home.items()},
            "planner_id": str(config.get("planner_id") or ""),
            "planning_attempts": attempts,
            "planning_time_sec": seconds,
            "corridor_margin_samples": int(config.get("corridor_margin_samples", 0) or 0),
            "allow_spindle_guide_contact": bool(config.get("allow_spindle_guide_contact", False)),
            "barrier_tuning": tuning,
        },
        "status": str(record.get("status") or ""),
        "source": str(record.get("source") or "operator"),
        "recorded_utc": str(record.get("recorded_utc") or ""),
        "notes": str(record.get("notes") or ""),
        "diagnostics": dict(record.get("diagnostics") or {}),
        "evidence_dir": str(record.get("evidence_dir") or ""),
    }


def dumps(record: Mapping) -> str:
    return json.dumps(normalize(record), sort_keys=True, separators=(",", ":"))


def loads(text: str | None) -> dict | None:
    if not text:
        return None
    return normalize(json.loads(text))


def from_research_entry(entry: Mapping, branch_foundation_fingerprint: str = "") -> dict:
    """Convert a pre-2026-10-07 research-node entry (Testing/step6_branch_config.py)."""
    return normalize({
        **dict(entry),
        "branch_foundation_fingerprint": branch_foundation_fingerprint,
        "source": "imported from research store",
    })


def differences(stored: Mapping, current: Mapping) -> list[str]:
    """Fields of ``stored`` (normalized config) that the current Step 6 state lacks."""
    s = normalize(stored)["config"]
    c = normalize(current)["config"]
    out = []
    if abs(s["mouth_opening_mm"] - c["mouth_opening_mm"]) > OPENING_TOLERANCE_MM:
        out.append("mouth_opening_mm")
    if max(abs(a - b) for ra, rb in zip(s["base_world_mm"], c["base_world_mm"]) for a, b in zip(ra, rb)) \
            > BASE_TOLERANCE_MM:
        out.append("base_world_mm")
    if s["task_home_si"] is not None and (
        c["task_home_si"] is None
        or set(s["task_home_si"]) != set(c["task_home_si"])
        or max(abs(s["task_home_si"][k] - c["task_home_si"][k]) for k in s["task_home_si"]) > HOME_TOLERANCE_SI
    ):
        out.append("task_home_si")
    if any(abs(s["barrier_tuning"][k] - c["barrier_tuning"][k]) > BARRIER_TOLERANCE_MM
           for k in mouth_portal.BARRIER_TUNING_KEYS):
        out.append("barrier_tuning")
    for key in ("planner_id", "planning_attempts", "planning_time_sec", "corridor_margin_samples",
                "allow_spindle_guide_contact"):
        if key == "planner_id" and not s[key]:
            continue
        if s[key] != c[key]:
            out.append(key)
    return out


def binding_issue(record: Mapping, branch_id: str, branch_foundation_fingerprint: str) -> str:
    """Why a stored configuration must not be applied to this branch ("" if it may)."""
    data = normalize(record)
    if data["branch_id"] and data["branch_id"] != branch_id:
        return "The saved Step 6 configuration belongs to another PreparedBranch."
    if data["branch_foundation_fingerprint"] and data["branch_foundation_fingerprint"] != branch_foundation_fingerprint:
        return "The saved Step 6 configuration belongs to another Case Foundation."
    return ""
