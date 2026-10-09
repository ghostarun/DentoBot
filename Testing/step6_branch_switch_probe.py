"""Read-only per-PreparedBranch state probe (S6-MULTI-JAW-STALE-01).

A headed session calls capture_branch_switch_state(widget, label=...) before and after each
production action (Import, branch selection, opening change, save and reopen, Step A auto-connect)
and writes the JSON with write_state(). diff_branch_states() names what changed between two captures.

The probe never mutates. It does not call syncDentoCaseTrajectoryRegistry (that reconciles and
migrates the registry); it parses the stored registry JSON instead. It reads stored records,
the live Step 6 configuration through the production capture owner, MRML node fields, the
transform matrix, and button and label text. Every capture carries digests of the stored registry,
the stored records and the live configuration, so a before/after diff also shows any unintended write.

Research prototype; simulation only.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from DENTOStep6State import empty_trajectory_registry, parse_trajectory_registry
from dentobot_workflow import step6_working_config

VALID_BRANCH_STATE = "Current"
_IGNORED_KEYS = frozenset({"label", "captured_utc"})


def _digest(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _rounded(value, places: int = 9):
    if isinstance(value, float):
        return round(value, places)
    if isinstance(value, (list, tuple)):
        return [_rounded(item, places) for item in value]
    if isinstance(value, dict):
        return {key: _rounded(item, places) for key, item in value.items()}
    return value


def _config_summary(record: dict | None) -> dict | None:
    """Normalized stored or live configuration, with a digest of its canonical form."""

    if record is None:
        return None
    config = record["config"]
    return _rounded({
        "digest": _digest(step6_working_config.dumps(record)),
        "mouth_opening_mm": config["mouth_opening_mm"],
        "base_world_mm": config["base_world_mm"],
        "task_home_si": config["task_home_si"],
        "planner_id": config["planner_id"],
        "planning_attempts": config["planning_attempts"],
        "planning_time_sec": config["planning_time_sec"],
        "corridor_margin_samples": config["corridor_margin_samples"],
        "allow_spindle_guide_contact": config["allow_spindle_guide_contact"],
        "barrier_tuning": config["barrier_tuning"],
    })


def _button(widget, name: str) -> dict:
    control = getattr(getattr(widget, "ui", None), name, None)
    if control is None:
        return {"present": False}
    return {
        "present": True,
        "text": str(control.text),
        "enabled": bool(control.enabled),
        "visible": bool(control.visible),
    }


def capture_branch_switch_state(widget, *, label: str = "") -> dict:
    """Read the per-branch Step 6 state of the open case. Never mutates the case or the robot."""

    node = widget._parameterNode
    logic = widget.logic
    panel = widget._robotSimulationPanel
    registry_text = str(node.step6TrajectoryRegistryJson or "")
    registry = parse_trajectory_registry(registry_text) if registry_text else empty_trajectory_registry()
    selected = str(registry.get("selected_branch_id") or "")

    branches = {}
    for branch_id, branch in sorted(registry.get("prepared_branches", {}).items()):
        branches[branch_id] = {
            "target_id": branch.get("target_id"),
            "state": branch.get("state"),
            "stale_reason": branch.get("stale_reason", ""),
            "pairing_intent": branch.get("pairing_intent"),
            "selected": branch_id == selected,
            "stored": _config_summary(logic.step6WorkingConfiguration(node, branch_id)),
        }

    live_record = widget._currentStep6WorkingConfiguration()
    selected_record = logic.step6WorkingConfiguration(node, selected) if selected else None
    eligibility = logic.evaluatePreparedBranchEligibility(node, registry=registry)
    panel_label = getattr(panel, "branchConfigStatusLabel", None)
    return _rounded({
        "label": label,
        "registry": {
            "digest": _digest(registry_text),
            "schema_version": registry.get("schema_version"),
            "selected_branch_id": selected,
            "branch_count": len(branches),
            "branches_not_current": sorted(
                branch_id for branch_id, info in branches.items() if info["state"] != VALID_BRANCH_STATE
            ),
        },
        "branches": branches,
        "selected_eligibility": {
            "eligible": bool(eligibility.get("eligible")),
            "reason": eligibility.get("reason"),
            "message": eligibility.get("message"),
        },
        "live": _config_summary(live_record),
        "selected_differences": (
            step6_working_config.differences(selected_record, live_record)
            if selected_record is not None else None
        ),
        "base": {
            "robotBaseMountLocked": bool(node.robotBaseMountLocked),
            "step6BasePlacementStatus": str(node.step6BasePlacementStatus or ""),
            "step6PlanningContextImported": bool(node.step6PlanningContextImported),
        },
        "ros": {"motion_control_active": bool(logic.isRos2MotionControlActive(node.robotBaseTransform))},
        "ui": {
            "import_button": _button(widget, "importStep6PlanningContextButton"),
            "lock_base_button": _button(widget, "lockRobotBaseMountButton"),
            "branch_config_status": str(panel_label.text) if panel_label is not None else None,
        },
    })


def branches_not_current(state: dict) -> list:
    """Branch ids whose registry state is not Current (a stale or unverified branch)."""

    return list(state["registry"]["branches_not_current"])


def diff_branch_states(before: dict, after: dict) -> list:
    """Every leaf that differs between two captures, as sorted (path, before, after) records."""

    changes: list = []

    def walk(left, right, path):
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                if key in _IGNORED_KEYS and not path:
                    continue
                walk(left.get(key), right.get(key), f"{path}.{key}" if path else str(key))
        elif left != right:
            changes.append({"path": path, "before": left, "after": right})

    walk(before, after, "")
    return sorted(changes, key=lambda change: change["path"])


# Task Home compare tolerance. The jog and Task Home draft spinboxes show two decimals (degrees for revolute joints,
# mm for slider joints; DENTORobotSimulationPanel.py:1018 and :1133, value.decimals = 2). A saved joint therefore comes
# back rounded to 0.01 of its display unit, so the staged value can differ from the saved one by at most half of that
# step. The compare bound is that quantization (plus float slack), not a tighter physical tolerance.
TASK_HOME_DECIMALS = 2
TASK_HOME_HALF_STEP_DEG = 0.5 * 10 ** -TASK_HOME_DECIMALS  # 0.005 degree
TASK_HOME_HALF_STEP_MM = 0.5 * 10 ** -TASK_HOME_DECIMALS  # 0.005 mm
_TASK_HOME_FLOAT_SLACK = 1e-9


def task_home_quantization_bound_si(joint: str) -> float:
    """Largest staged-vs-saved difference, in SI units (rad or m), that display rounding can produce for ``joint``."""

    if "Slider" in joint:
        return TASK_HOME_HALF_STEP_MM / 1000.0 * (1.0 + _TASK_HOME_FLOAT_SLACK)
    return math.radians(TASK_HOME_HALF_STEP_DEG) * (1.0 + _TASK_HOME_FLOAT_SLACK)


def task_home_within_quantization(staged_si: dict, saved_si: dict) -> tuple[bool, dict]:
    """Compare a staged Task Home with the saved one at the displayed quantization.

    Returns (ok, detail). ``detail`` maps each joint to its difference and bound, so a failure names the joint.
    A joint that is missing on either side fails.
    """

    detail = {}
    ok = set(staged_si) == set(saved_si)
    for joint in sorted(set(staged_si) | set(saved_si)):
        if joint not in staged_si or joint not in saved_si:
            detail[joint] = {"staged": staged_si.get(joint), "saved": saved_si.get(joint), "within": False}
            continue
        delta = abs(float(staged_si[joint]) - float(saved_si[joint]))
        bound = task_home_quantization_bound_si(joint)
        within = delta <= bound
        detail[joint] = {"delta_si": delta, "bound_si": bound, "within": within}
        ok = ok and within
    return ok, detail


def write_state(state: dict, path) -> Path:
    """Write one capture as JSON to an evidence path (never to the case or the scene)."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
