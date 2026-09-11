"""Versioned persistent-state contracts for the DENTOBOT Step 6 workflow.

This module is intentionally independent of Slicer and ROS.  It defines the
portable records that may be stored in MRML/.dentocase and the fingerprints
used to invalidate plans when an operator-relevant dependency changes.
Runtime ROS nodes, publishers, plans, and guard sessions are deliberately not
represented here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite, sqrt
from typing import Mapping, Sequence


STATE_SCHEMA_VERSION = "1.0"
DENTOCASE_STATE_SCHEMA_VERSION = "2.0"
ROBOT_ENVIRONMENT_SCHEMA_VERSION = "1.0"
ATTEMPT_CONTEXT_SCHEMA_VERSION = "1.0"
TRAJECTORY_REGISTRY_SCHEMA_VERSION = "2.0"
LEGACY_TRAJECTORY_REGISTRY_SCHEMA_VERSION = "1.0"
TRAJECTORY_SLOTS_PER_TOOTH = 3
DENTAL_FDI_TOOTH_IDS = tuple(
    f"FDI{quadrant}{tooth}"
    for quadrant in range(1, 5)
    for tooth in range(1, 9)
)
COLLISION_AUDIT_SCHEMA_VERSION = "1.0"
MOTION_DIAGNOSTIC_SCHEMA_VERSION = "2.1"
SUPPORTED_MOTION_DIAGNOSTIC_SCHEMA_VERSIONS = ("1.0", "2.0", "2.1")
MANUAL_SIMULATION_BASE_SOURCE = "manual-simulation-base"
QUARANTINED_CIRCULAR_BASE_SOURCE = "quarantined-circular-mount-plane"
"""Commandable robot joints used by MoveIt and the Step 6 guard.

The pneumatic spindle remains in the URDF as a visual/collision branch, but it
is deliberately absent from this planning order: its angular position is not a
robot command.  ``LEGACY_JOINT_NAMES`` is retained only to migrate old saved
six-value records at the persistence boundary.
"""
JOINT_NAMES = (
    "link-1_Revolute-1",
    "link-2_Slider-2",
    "link-3_Revolute-3",
    "link-4_Slider-4",
    "link-5_Revolute-5",
)
SPINDLE_JOINT_NAME = "pneumatic_spindle-Copy_Revolute-6"
LEGACY_JOINT_NAMES = JOINT_NAMES + (SPINDLE_JOINT_NAME,)
SPINDLE_LOCKED_VALUE_RAD = 0.0
SPINDLE_LOCK_TOLERANCE_RAD = 1.0e-9
SPINDLE_PLANNING_POLICY = "external-pressure-spindle-nonplanning-v2"
SIMULATION_TARGET_DEPTH_CAP_MM = 6.0
SIMULATION_TARGET_DEPTH_POLICY = "simulation-target-depth-cap-v1"
SIMULATION_TOOL_PROVENANCE = (
    "CAD-derived/provisional/un-calibrated; " + SIMULATION_TARGET_DEPTH_POLICY
)
# The five-DOF arm can command TCP XYZ plus the drilling-axis direction.  Roll
# about that axis belongs to the external pneumatic spindle and is not part of
# the MoveIt task constraint.  Bump the policy fingerprint so older full-frame
# evidence is explicitly stale after this kinematic correction.
DRILL_TOOL_FRAME_POLICY = "stage1-position-axis-authoritative-fk-v3"


def canonicalize_planning_joint_positions(
    joint_positions_si: Mapping[str, float],
) -> dict[str, float]:
    """Return a finite commandable J1–J5 vector.

    An optional historical spindle key is ignored at this boundary.  It is not
    canonicalized, constrained, or sent to MoveIt; old records are migrated by
    their parser and their pre-migration evidence is stale by fingerprint.
    """

    result = {name: float(joint_positions_si[name]) for name in JOINT_NAMES}
    if not all(isfinite(value) for value in result.values()):
        raise ValueError("planning joint vector must contain five finite values")
    return result


def spindle_is_locked(joint_positions_si: Mapping[str, float]) -> bool:
    """Compatibility check for legacy records; never used for planning."""
    try:
        value = float(joint_positions_si[SPINDLE_JOINT_NAME])
    except (KeyError, TypeError, ValueError):
        return False
    return isfinite(value) and abs(value - SPINDLE_LOCKED_VALUE_RAD) <= SPINDLE_LOCK_TOLERANCE_RAD


class BasePlacementStatus(str, Enum):
    UNLOCKED = "Unlocked"
    PROVISIONAL_LOCKED = "ProvisionalLocked"
    REGISTERED_LOCKED = "RegisteredLocked"
    STALE = "Stale"


class MotionPhase(str, Enum):
    APPROACH = "approach"
    TERMINAL_CONTACT = "terminal_contact"
    DRILLING = "drilling"
    RETRACTION = "retraction"


def _finite_tuple(values: Sequence[float], count: int, label: str) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if len(result) != count or not all(isfinite(value) for value in result):
        raise ValueError(f"{label} must contain {count} finite values")
    return result


def cap_simulation_target(
    entry_ras_mm: Sequence[float], target_ras_mm: Sequence[float]
) -> tuple[float, float, float]:
    """Return a finite simulation Target no deeper than the 6 mm cap."""

    try:
        entry = _finite_tuple(entry_ras_mm, 3, "Entry RAS")
        target = _finite_tuple(target_ras_mm, 3, "Target RAS")
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("Entry and Target must be three finite coordinates") from exc
    vector = tuple(target[index] - entry[index] for index in range(3))
    if not all(isfinite(value) for value in vector):
        raise ValueError("Entry-to-Target vector must have a finite length")
    length = sqrt(sum(value * value for value in vector))
    if not isfinite(length) or length <= 0.0:
        raise ValueError("Entry and Target must define a finite non-zero trajectory")
    if length <= SIMULATION_TARGET_DEPTH_CAP_MM:
        return target
    fraction = SIMULATION_TARGET_DEPTH_CAP_MM / length
    capped = tuple(
        entry[index] + fraction * vector[index] for index in range(3)
    )
    if not all(isfinite(value) for value in capped):
        raise ValueError("Capped simulation Target must contain finite coordinates")
    return capped


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _optional_finite_tuple(
    values: Sequence[float], count: int, label: str
) -> tuple[float, ...]:
    return () if not values else _finite_tuple(values, count, label)


@dataclass(frozen=True)
class RobotEnvironmentSnapshotV1:
    """Portable Step 6 state shared by every target in one case."""

    schema_version: str
    case_identity: str
    anatomy_fingerprint: str
    jaw_source_fingerprint: str
    jaw_landmarks_fingerprint: str
    jaw_configuration_fingerprint: str
    jaw_transform_matrix: tuple[float, ...]
    mouth_gap_mm: float | None
    robot_profile_fingerprint: str
    tool_identity: str
    tool_fingerprint: str
    base_matrix: tuple[float, ...]
    base_status: str
    base_locked: bool
    base_fingerprint: str
    task_home_configuration: dict[str, object] | None
    common_collision_fingerprint: str
    limits_fingerprint: str
    workspace_fingerprint: str
    environment_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["jaw_transform_matrix"] = list(self.jaw_transform_matrix)
        result["base_matrix"] = list(self.base_matrix)
        return result


def build_robot_environment_snapshot(
    *,
    case_identity: str = "",
    anatomy_fingerprint: str = "",
    jaw_source_fingerprint: str = "",
    jaw_landmarks_fingerprint: str = "",
    jaw_configuration_fingerprint: str = "",
    jaw_transform_matrix: Sequence[float] = (),
    mouth_gap_mm: float | None = None,
    robot_profile_fingerprint: str = "",
    tool_identity: str = "",
    tool_fingerprint: str = "",
    base_matrix: Sequence[float] = (),
    base_status: str = "Unlocked",
    base_locked: bool = False,
    base_fingerprint: str = "",
    task_home_configuration: Mapping[str, object] | None = None,
    common_collision_fingerprint: str = "",
    limits_fingerprint: str = "",
    workspace_fingerprint: str = "",
) -> RobotEnvironmentSnapshotV1:
    """Build a target-independent environment record, including incomplete cases."""

    gap = None if mouth_gap_mm is None else float(mouth_gap_mm)
    if gap is not None and (not isfinite(gap) or gap <= 0.0):
        raise ValueError("mouth gap must be a positive finite value")
    home = None if task_home_configuration is None else dict(task_home_configuration)
    if home:
        # Runtime validity belongs to the current process, never the package.
        for key in (
            "runtime_validation_status",
            "collision_audit_fingerprint",
            "guard_policy_fingerprint",
            "validated_at_utc",
            "minimum_clearance_mm",
            "world_object_count",
        ):
            home.pop(key, None)
    identity = {
        "schema_version": ROBOT_ENVIRONMENT_SCHEMA_VERSION,
        "case_identity": str(case_identity),
        "anatomy_fingerprint": str(anatomy_fingerprint),
        "jaw_source_fingerprint": str(jaw_source_fingerprint),
        "jaw_landmarks_fingerprint": str(jaw_landmarks_fingerprint),
        "jaw_configuration_fingerprint": str(jaw_configuration_fingerprint),
        "jaw_transform_matrix": list(
            _optional_finite_tuple(jaw_transform_matrix, 16, "jaw transform")
        ),
        "mouth_gap_mm": gap,
        "robot_profile_fingerprint": str(robot_profile_fingerprint),
        "tool_identity": str(tool_identity),
        "tool_fingerprint": str(tool_fingerprint),
        "base_matrix": list(_optional_finite_tuple(base_matrix, 16, "base matrix")),
        "base_status": normalize_base_status(base_status).value,
        "base_locked": bool(base_locked),
        "base_fingerprint": str(base_fingerprint),
        "task_home_configuration": home,
        "common_collision_fingerprint": str(common_collision_fingerprint),
        "limits_fingerprint": str(limits_fingerprint),
        "workspace_fingerprint": str(workspace_fingerprint),
    }
    return RobotEnvironmentSnapshotV1(
        environment_fingerprint=fingerprint(identity),
        jaw_transform_matrix=tuple(identity["jaw_transform_matrix"]),
        base_matrix=tuple(identity["base_matrix"]),
        **{
            key: value
            for key, value in identity.items()
            if key not in {"jaw_transform_matrix", "base_matrix"}
        },
    )


def parse_robot_environment_snapshot(
    payload: str | Mapping[str, object],
) -> RobotEnvironmentSnapshotV1:
    data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    if data.get("schema_version") != ROBOT_ENVIRONMENT_SCHEMA_VERSION:
        raise ValueError("unsupported robot-environment schema")
    rebuilt = build_robot_environment_snapshot(
        **{
            key: data.get(key)
            for key in (
                "case_identity",
                "anatomy_fingerprint",
                "jaw_source_fingerprint",
                "jaw_landmarks_fingerprint",
                "jaw_configuration_fingerprint",
                "jaw_transform_matrix",
                "mouth_gap_mm",
                "robot_profile_fingerprint",
                "tool_identity",
                "tool_fingerprint",
                "base_matrix",
                "base_status",
                "base_locked",
                "base_fingerprint",
                "task_home_configuration",
                "common_collision_fingerprint",
                "limits_fingerprint",
                "workspace_fingerprint",
            )
        }
    )
    if rebuilt.environment_fingerprint != data.get("environment_fingerprint"):
        raise ValueError("robot-environment fingerprint does not match its contents")
    return rebuilt


def robot_environment_invalidation_scopes(
    previous: RobotEnvironmentSnapshotV1,
    current: RobotEnvironmentSnapshotV1,
) -> tuple[str, ...]:
    """Return the narrowest persistent dependency scopes affected by a change."""

    scopes: set[str] = set()
    if any(
        getattr(previous, field) != getattr(current, field)
        for field in (
            "case_identity",
            "anatomy_fingerprint",
            "jaw_source_fingerprint",
            "jaw_landmarks_fingerprint",
            "jaw_configuration_fingerprint",
            "jaw_transform_matrix",
            "mouth_gap_mm",
        )
    ):
        scopes.update(("jaw", "base", "home", "attempt"))
    if any(
        getattr(previous, field) != getattr(current, field)
        for field in (
            "robot_profile_fingerprint",
            "tool_identity",
            "tool_fingerprint",
        )
    ):
        scopes.update(("base", "home", "attempt"))
    if any(
        getattr(previous, field) != getattr(current, field)
        for field in ("base_matrix", "base_status", "base_locked", "base_fingerprint")
    ):
        scopes.update(("home", "attempt"))
    if previous.task_home_configuration != current.task_home_configuration:
        scopes.add("attempt")
    if any(
        getattr(previous, field) != getattr(current, field)
        for field in (
            "common_collision_fingerprint",
            "limits_fingerprint",
            "workspace_fingerprint",
        )
    ):
        scopes.add("attempt")
    return tuple(scope for scope in ("jaw", "base", "home", "attempt") if scope in scopes)


@dataclass(frozen=True)
class AttemptContextV1:
    schema_version: str
    environment_fingerprint: str
    target_id: str
    tooth_id: str
    trajectory_id: str
    trajectory_fingerprint: str
    guide_set_id: str
    guide_set_fingerprint: str
    guide_mode: str
    planner_fingerprint: str
    start_state_fingerprint: str
    contact_mode: str
    phase_policy_fingerprint: str
    attempt_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_attempt_context(
    *,
    environment_fingerprint: str,
    target_id: str,
    tooth_id: str,
    trajectory_id: str,
    trajectory_fingerprint: str,
    guide_set_id: str = "",
    guide_set_fingerprint: str = "",
    guide_mode: str = "",
    planner_fingerprint: str = "",
    start_state_fingerprint: str = "",
    contact_mode: str = "",
    phase_policy_fingerprint: str = "",
) -> AttemptContextV1:
    tooth = str(tooth_id).upper()
    if tooth not in DENTAL_FDI_TOOTH_IDS:
        raise ValueError("attempt requires a permanent FDI tooth identifier")
    identity = {
        "schema_version": ATTEMPT_CONTEXT_SCHEMA_VERSION,
        "environment_fingerprint": str(environment_fingerprint),
        "target_id": str(target_id),
        "tooth_id": tooth,
        "trajectory_id": str(trajectory_id),
        "trajectory_fingerprint": str(trajectory_fingerprint),
        "guide_set_id": str(guide_set_id),
        "guide_set_fingerprint": str(guide_set_fingerprint),
        "guide_mode": str(guide_mode),
        "planner_fingerprint": str(planner_fingerprint),
        "start_state_fingerprint": str(start_state_fingerprint),
        "contact_mode": str(contact_mode),
        "phase_policy_fingerprint": str(phase_policy_fingerprint),
    }
    if not all(identity[key] for key in ("environment_fingerprint", "target_id", "trajectory_id", "trajectory_fingerprint")):
        raise ValueError("attempt context is missing a stable dependency identity")
    return AttemptContextV1(
        attempt_fingerprint=fingerprint(identity),
        **identity,
    )


def parse_attempt_context(payload: str | Mapping[str, object]) -> AttemptContextV1:
    data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    if data.get("schema_version") != ATTEMPT_CONTEXT_SCHEMA_VERSION:
        raise ValueError("unsupported attempt-context schema")
    rebuilt = build_attempt_context(
        **{
            key: data.get(key, "")
            for key in (
                "environment_fingerprint",
                "target_id",
                "tooth_id",
                "trajectory_id",
                "trajectory_fingerprint",
                "guide_set_id",
                "guide_set_fingerprint",
                "guide_mode",
                "planner_fingerprint",
                "start_state_fingerprint",
                "contact_mode",
                "phase_policy_fingerprint",
            )
        }
    )
    if rebuilt.attempt_fingerprint != data.get("attempt_fingerprint"):
        raise ValueError("attempt fingerprint does not match its contents")
    return rebuilt


def empty_trajectory_registry() -> dict[str, object]:
    return {
        "schema_version": TRAJECTORY_REGISTRY_SCHEMA_VERSION,
        "teeth": {
            tooth: {
                "target_id": "",
                "segment_id": "",
                "trajectory_set": {
                    "slots": [
                        {
                            "slot": slot,
                            "state": "Empty",
                            "trajectory_id": "",
                            "prepared_branch_ids": [],
                        }
                        for slot in range(1, TRAJECTORY_SLOTS_PER_TOOTH + 1)
                    ]
                },
            }
            for tooth in DENTAL_FDI_TOOTH_IDS
        },
        "prepared_branches": {},
        "selected_branch_id": "",
    }


def parse_trajectory_registry(payload: str | Mapping[str, object]) -> dict[str, object]:
    data = json.loads(payload) if isinstance(payload, str) else json.loads(canonical_json(payload))
    schema = data.get("schema_version")
    if schema == LEGACY_TRAJECTORY_REGISTRY_SCHEMA_VERSION:
        migrated = empty_trajectory_registry()
        migrated["teeth"] = data.get("teeth", {})
        for tooth in migrated["teeth"].values():
            legacy_tooth_guide = tooth.pop("guide_set", None)
            for slot in tooth.get("trajectory_set", {}).get("slots", []):
                guide = slot.pop("guide_set", None) or legacy_tooth_guide
                slot["prepared_branch_ids"] = []
                if (
                    not guide
                    or not guide.get("guide_set_id")
                    or str(slot.get("trajectory_id") or "")
                    not in guide.get("trajectory_ids", ())
                ):
                    continue
                branch_id = str(guide["guide_set_id"])
                migrated["prepared_branches"].setdefault(
                    branch_id,
                    {
                        "branch_id": branch_id,
                        "target_id": str(guide.get("target_id") or ""),
                        "trajectory_ids": [str(value) for value in guide.get("trajectory_ids", [])],
                        "primary_trajectory_id": str((guide.get("trajectory_ids") or [""])[0]),
                        "pairing_intent": (
                            "Single"
                            if len(guide.get("trajectory_ids", [])) == 1
                            else "LegacyUnverified"
                        ),
                        "target_docking_node_id": "",
                        "insertion_direction_node_id": "",
                        "template_id": str(guide.get("template_id") or ""),
                        "template_node_id": str(guide.get("template_node_id") or ""),
                        "shell_id": str(guide.get("shell_id") or ""),
                        "shell_node_id": str(guide.get("shell_node_id") or ""),
                        "model_node_ids": [str(value) for value in guide.get("model_node_ids", [])],
                        "revision": str(guide.get("fingerprint") or ""),
                        "verification_revision": "",
                        "state": "Stale",
                        "stale_reason": "Legacy branch requires explicit pairing and re-verification.",
                    },
                )
                if branch_id not in slot["prepared_branch_ids"]:
                    slot["prepared_branch_ids"].append(branch_id)
        selected = data.get("selected") or {}
        selected_branch_id = str(selected.get("guide_set_id") or "")
        if selected_branch_id in migrated["prepared_branches"]:
            migrated["selected_branch_id"] = selected_branch_id
        data = migrated
        schema = TRAJECTORY_REGISTRY_SCHEMA_VERSION
    if schema != TRAJECTORY_REGISTRY_SCHEMA_VERSION:
        raise ValueError("unsupported trajectory-registry schema")
    teeth = data.get("teeth")
    if not isinstance(teeth, dict) or tuple(sorted(teeth)) != tuple(sorted(DENTAL_FDI_TOOTH_IDS)):
        raise ValueError("trajectory registry must contain all 32 permanent teeth")
    trajectory_ids: set[str] = set()
    trajectory_owners: dict[str, tuple[str, str]] = {}
    target_ids: set[str] = set()
    for tooth in DENTAL_FDI_TOOTH_IDS:
        record = teeth[tooth]
        trajectory_set = record.get("trajectory_set") if isinstance(record, dict) else None
        slots = trajectory_set.get("slots") if isinstance(trajectory_set, dict) else None
        if not isinstance(slots, list) or [slot.get("slot") for slot in slots] != [1, 2, 3]:
            raise ValueError(f"{tooth} must contain three ordered trajectory slots")
        for slot in slots:
            slot.setdefault("prepared_branch_ids", [])
        for slot in slots:
            state = slot.get("state")
            trajectory_id = str(slot.get("trajectory_id") or "")
            if state == "Empty":
                if trajectory_id or slot.get("prepared_branch_ids"):
                    raise ValueError(
                        "an empty trajectory slot cannot have an identity or prepared branch"
                    )
                continue
            if state not in {"Current", "Stale"} or not trajectory_id:
                raise ValueError("a populated trajectory slot has invalid state")
            if trajectory_id in trajectory_ids:
                raise ValueError("trajectory identities must be unique")
            trajectory_ids.add(trajectory_id)
            trajectory_owners[trajectory_id] = (
                tooth,
                str(record.get("target_id") or ""),
            )
            if str(slot.get("target_id") or "") != str(record.get("target_id") or ""):
                raise ValueError("trajectory target identity does not match its tooth")
            branch_ids = slot.get("prepared_branch_ids")
            if not isinstance(branch_ids, list) or len(branch_ids) != len(set(branch_ids)):
                raise ValueError("trajectory prepared-branch references are invalid")
        target_id = str(record.get("target_id") or "")
        if target_id:
            if target_id in target_ids:
                raise ValueError("tooth target identities must be unique")
            target_ids.add(target_id)
    branches = data.get("prepared_branches")
    if not isinstance(branches, dict):
        raise ValueError("prepared-branch registry is invalid")
    slot_branch_ids = {
        str(branch_id)
        for tooth in teeth.values()
        for slot in tooth["trajectory_set"]["slots"]
        for branch_id in slot.get("prepared_branch_ids", [])
    }
    for branch_id, branch in branches.items():
        if not isinstance(branch, dict) or str(branch.get("branch_id") or "") != str(branch_id):
            raise ValueError("prepared branch identity is invalid")
        referenced = [str(value) for value in branch.get("trajectory_ids", [])]
        if not 1 <= len(referenced) <= 2 or len(referenced) != len(set(referenced)):
            raise ValueError("prepared branch requires one trajectory, or an explicit pair")
        if any(value not in trajectory_ids for value in referenced):
            raise ValueError("prepared branch references an unknown trajectory")
        owners = {trajectory_owners[value] for value in referenced}
        if len(owners) != 1 or next(iter(owners))[1] != str(branch.get("target_id") or ""):
            raise ValueError("prepared branch belongs to a different tooth target")
        if str(branch.get("primary_trajectory_id") or "") not in referenced:
            raise ValueError("prepared branch primary trajectory is invalid")
        if branch.get("pairing_intent") not in {"Single", "ExplicitPair", "LegacyUnverified"}:
            raise ValueError("prepared branch pairing intent is invalid")
        if branch.get("state") not in {"Current", "Stale"}:
            raise ValueError("prepared branch has invalid state")
        for trajectory_id in referenced:
            owner_tooth = trajectory_owners[trajectory_id][0]
            slot = next(
                item for item in teeth[owner_tooth]["trajectory_set"]["slots"]
                if item.get("trajectory_id") == trajectory_id
            )
            if str(branch_id) not in slot.get("prepared_branch_ids", []):
                raise ValueError("prepared branch is not referenced by every owning trajectory")
    if slot_branch_ids != set(str(value) for value in branches):
        raise ValueError("trajectory slots and prepared branches disagree")
    selected_branch_id = str(data.get("selected_branch_id") or "")
    if selected_branch_id and selected_branch_id not in branches:
        raise ValueError("selected prepared branch is not registered")
    return data


def upsert_trajectory_record(
    registry: Mapping[str, object],
    *,
    tooth_id: str,
    target_id: str,
    segment_id: str,
    trajectory_id: str,
    trajectory_node_id: str,
    trajectory_fingerprint: str,
    provenance: str,
    slot: int | None = None,
) -> dict[str, object]:
    data = parse_trajectory_registry(registry)
    tooth = str(tooth_id).upper()
    if tooth not in DENTAL_FDI_TOOTH_IDS:
        raise ValueError("trajectory requires a permanent FDI tooth identifier")
    target = data["teeth"][tooth]
    if target["target_id"] and target["target_id"] != str(target_id):
        raise ValueError("one tooth record cannot have multiple target identities")
    slots = target["trajectory_set"]["slots"]
    existing = next(
        (record for record in slots if record.get("trajectory_id") == trajectory_id),
        None,
    )
    if existing is None:
        empty = [record for record in slots if record["state"] == "Empty"]
        if not empty:
            raise ValueError(f"{tooth} already has three trajectories; a fourth is not allowed")
        if slot is None:
            existing = empty[0]
        else:
            existing = next((record for record in empty if record["slot"] == int(slot)), None)
            if existing is None:
                raise ValueError("requested trajectory slot is not empty")
    target["target_id"] = str(target_id)
    target["segment_id"] = str(segment_id)
    existing.update(
        {
            "state": "Current",
            "target_id": str(target_id),
            "trajectory_id": str(trajectory_id),
            "trajectory_node_id": str(trajectory_node_id),
            "trajectory_fingerprint": str(trajectory_fingerprint),
            "provenance": str(provenance),
            "evidence_state": "Unreviewed",
            "stale_reason": "",
        }
    )
    return parse_trajectory_registry(data)


def upsert_guide_set(
    registry: Mapping[str, object],
    *,
    guide_set_id: str,
    target_id: str,
    trajectory_ids: Sequence[str],
    template_id: str = "",
    template_node_id: str = "",
    shell_id: str = "",
    shell_node_id: str = "",
    model_node_ids: Sequence[str] = (),
    guide_fingerprint: str = "",
    primary_trajectory_id: str = "",
    pairing_intent: str = "Single",
    target_docking_node_id: str = "",
    insertion_direction_node_id: str = "",
    verification_revision: str = "",
    state: str = "Current",
) -> dict[str, object]:
    data = parse_trajectory_registry(registry)
    guide_id = str(guide_set_id)
    tooth = next(
        (
            record for record in data["teeth"].values()
            if str(record.get("target_id") or "") == str(target_id)
        ),
        None,
    )
    if tooth is None:
        raise ValueError("guide set has no matching tooth target")
    trajectory_ids = [str(value) for value in trajectory_ids]
    if not 1 <= len(trajectory_ids) <= 2:
        raise ValueError("a guide set requires one trajectory, or two at most")
    record = {
        "branch_id": guide_id,
        "target_id": str(target_id),
        "trajectory_ids": trajectory_ids,
        "primary_trajectory_id": str(primary_trajectory_id or trajectory_ids[0]),
        "pairing_intent": str(pairing_intent),
        "target_docking_node_id": str(target_docking_node_id),
        "insertion_direction_node_id": str(insertion_direction_node_id),
        "template_id": str(template_id),
        "template_node_id": str(template_node_id),
        "shell_id": str(shell_id),
        "shell_node_id": str(shell_node_id),
        "model_node_ids": [str(value) for value in model_node_ids],
        "revision": str(guide_fingerprint),
        "verification_revision": str(verification_revision),
        "state": str(state),
        "stale_reason": "",
    }
    for owner in data["teeth"].values():
        for slot_record in owner["trajectory_set"]["slots"]:
            slot_record["prepared_branch_ids"] = [
                value
                for value in slot_record["prepared_branch_ids"]
                if value != guide_id
            ]
    data["prepared_branches"][guide_id] = record
    matched = 0
    for slot in tooth["trajectory_set"]["slots"]:
        if slot.get("trajectory_id") in trajectory_ids:
            if guide_id not in slot["prepared_branch_ids"]:
                slot["prepared_branch_ids"].append(guide_id)
            matched += 1
    if matched != len(trajectory_ids):
        raise ValueError("guide set references an unknown tooth trajectory")
    return parse_trajectory_registry(data)


def stale_trajectory_record(
    registry: Mapping[str, object], trajectory_id: str, reason: str
) -> dict[str, object]:
    data = parse_trajectory_registry(registry)
    found = False
    for tooth in data["teeth"].values():
        for slot in tooth["trajectory_set"]["slots"]:
            if slot.get("trajectory_id") == trajectory_id:
                slot["state"] = "Stale"
                slot["evidence_state"] = "Stale"
                slot["stale_reason"] = str(reason)
                found = True
    for branch in data["prepared_branches"].values():
        if trajectory_id in branch.get("trajectory_ids", ()):
            branch["state"] = "Stale"
            branch["stale_reason"] = str(reason)
    if not found:
        raise ValueError("trajectory is not registered")
    return parse_trajectory_registry(data)


def select_prepared_branch(
    registry: Mapping[str, object], branch_id: str
) -> dict[str, object]:
    data = parse_trajectory_registry(registry)
    branch_id = str(branch_id)
    if branch_id not in data["prepared_branches"]:
        raise ValueError("prepared branch is not registered")
    data["selected_branch_id"] = branch_id
    return parse_trajectory_registry(data)


def prepared_branch_ids_for_trajectory(
    registry: Mapping[str, object], trajectory_id: str
) -> tuple[str, ...]:
    data = parse_trajectory_registry(registry)
    for tooth in data["teeth"].values():
        for slot in tooth["trajectory_set"]["slots"]:
            if slot.get("trajectory_id") == str(trajectory_id):
                return tuple(str(value) for value in slot["prepared_branch_ids"])
    raise ValueError("trajectory is not registered")


def select_trajectory_record(
    registry: Mapping[str, object], trajectory_id: str
) -> dict[str, object]:
    """Compatibility helper: select only an unambiguous current branch."""

    data = parse_trajectory_registry(registry)
    branch_ids = [
        value for value in prepared_branch_ids_for_trajectory(data, trajectory_id)
        if data["prepared_branches"][value].get("state") == "Current"
    ]
    if len(branch_ids) != 1:
        raise ValueError("trajectory does not resolve to exactly one current prepared branch")
    return select_prepared_branch(data, branch_ids[0])


def normalize_base_status(value: object) -> BasePlacementStatus:
    text = str(getattr(value, "value", value) or "").strip()
    try:
        return BasePlacementStatus(text)
    except ValueError:
        # Scenes saved by the former Boolean lock contract are restored as an
        # explicitly unreviewed provisional state, never as registered truth.
        return BasePlacementStatus.PROVISIONAL_LOCKED if text.lower() in {
            "true", "1", "locked", "legacylocked"
        } else BasePlacementStatus.UNLOCKED


def transition_base_status(
    current: BasePlacementStatus | str,
    action: str,
) -> BasePlacementStatus:
    state = normalize_base_status(current)
    action = str(action).strip().lower()
    if action == "unlock":
        return BasePlacementStatus.UNLOCKED
    if action == "provisional_lock":
        if state not in {BasePlacementStatus.UNLOCKED, BasePlacementStatus.STALE}:
            raise ValueError(f"cannot provisionally lock base from {state.value}")
        return BasePlacementStatus.PROVISIONAL_LOCKED
    if action == "registered_lock":
        raise ValueError("registered locking requires a future verified registration workflow")
    if action == "invalidate":
        return (
            BasePlacementStatus.UNLOCKED
            if state is BasePlacementStatus.UNLOCKED
            else BasePlacementStatus.STALE
        )
    raise ValueError(f"unknown base transition: {action}")


def base_placement_source_issue(
    status: BasePlacementStatus | str,
    source: object,
    locked: bool,
) -> str:
    """Return why a reviewed base is not valid for the bounded simulation loop."""

    state = normalize_base_status(status)
    if state is BasePlacementStatus.REGISTERED_LOCKED:
        # Registered locking is reserved for a later physical workflow. If it
        # ever becomes reachable, its own registration evidence is authoritative.
        return ""
    if not locked and state in {
        BasePlacementStatus.UNLOCKED,
        BasePlacementStatus.STALE,
    }:
        return ""
    if state is not BasePlacementStatus.PROVISIONAL_LOCKED or not locked:
        return "Base placement must be explicitly reviewed and locked for simulation."
    if str(source or "").strip() != MANUAL_SIMULATION_BASE_SOURCE:
        return (
            "The saved base source predates manual-simulation-base containment; "
            "unlock, review Robot + CBCT, position the base manually, and lock it again."
        )
    return ""


@dataclass(frozen=True)
class TaskHomeRecord:
    schema_version: str
    revision: int
    joint_names: tuple[str, ...]
    joint_positions_si: tuple[float, ...]
    base_fingerprint: str
    robot_profile_fingerprint: str
    runtime_validation_status: str = "Unreviewed"
    collision_audit_fingerprint: str = ""
    guard_policy_fingerprint: str = ""
    validated_at_utc: str = ""
    minimum_clearance_mm: float | None = None
    world_object_count: int = 0
    spindle_planning_policy: str = SPINDLE_PLANNING_POLICY
    spindle_locked_value_rad: float = SPINDLE_LOCKED_VALUE_RAD

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["joint_names"] = list(self.joint_names)
        result["joint_positions_si"] = list(self.joint_positions_si)
        return result


def build_task_home(
    joint_positions_si: Mapping[str, float],
    *,
    base_fingerprint: str,
    robot_profile_fingerprint: str,
    revision: int = 1,
    runtime_validation_status: str = "Unreviewed",
    collision_audit_fingerprint: str = "",
    guard_policy_fingerprint: str = "",
    validated_at_utc: str = "",
    minimum_clearance_mm: float | None = None,
    world_object_count: int = 0,
) -> TaskHomeRecord:
    canonical_positions = canonicalize_planning_joint_positions(joint_positions_si)
    values = _finite_tuple(
        [canonical_positions[name] for name in JOINT_NAMES],
        len(JOINT_NAMES),
        "Task Home joint vector",
    )
    if not base_fingerprint or not robot_profile_fingerprint:
        raise ValueError("Task Home requires base and robot-profile fingerprints")
    validation_status = str(runtime_validation_status or "Unreviewed")
    if validation_status not in {"Unreviewed", "Validated"}:
        raise ValueError("Task Home runtime validation status is invalid")
    clearance = (
        None if minimum_clearance_mm is None else float(minimum_clearance_mm)
    )
    if clearance is not None and not isfinite(clearance):
        raise ValueError("Task Home minimum clearance must be finite")
    return TaskHomeRecord(
        schema_version=STATE_SCHEMA_VERSION,
        revision=max(1, int(revision)),
        joint_names=JOINT_NAMES,
        joint_positions_si=values,
        base_fingerprint=str(base_fingerprint),
        robot_profile_fingerprint=str(robot_profile_fingerprint),
        runtime_validation_status=validation_status,
        collision_audit_fingerprint=str(collision_audit_fingerprint or ""),
        guard_policy_fingerprint=str(guard_policy_fingerprint or ""),
        validated_at_utc=str(validated_at_utc or ""),
        minimum_clearance_mm=clearance,
        world_object_count=max(0, int(world_object_count)),
        spindle_planning_policy=SPINDLE_PLANNING_POLICY,
        spindle_locked_value_rad=SPINDLE_LOCKED_VALUE_RAD,
    )


def parse_task_home(payload: str | Mapping[str, object]) -> TaskHomeRecord:
    data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    if data.get("schema_version") != STATE_SCHEMA_VERSION:
        raise ValueError("unsupported Task Home schema")
    names = tuple(str(value) for value in data.get("joint_names", ()))
    values = tuple(data.get("joint_positions_si", ()))
    if names == LEGACY_JOINT_NAMES:
        # Old six-joint homes are read as J1–J5 only.  Their old planning
        # evidence is invalidated by the new robot-profile/TCP fingerprint.
        names = JOINT_NAMES
        values = values[: len(JOINT_NAMES)]
    if names != JOINT_NAMES or len(values) != len(JOINT_NAMES):
        raise ValueError("Task Home joint order does not match the J1–J5 planning profile")
    return build_task_home(
        dict(zip(names, values)),
        base_fingerprint=str(data.get("base_fingerprint") or ""),
        robot_profile_fingerprint=str(data.get("robot_profile_fingerprint") or ""),
        revision=int(data.get("revision", 0)),
        runtime_validation_status=str(
            data.get("runtime_validation_status") or "Unreviewed"
        ),
        collision_audit_fingerprint=str(
            data.get("collision_audit_fingerprint") or ""
        ),
        guard_policy_fingerprint=str(data.get("guard_policy_fingerprint") or ""),
        validated_at_utc=str(data.get("validated_at_utc") or ""),
        minimum_clearance_mm=data.get("minimum_clearance_mm"),
        world_object_count=int(data.get("world_object_count", 0)),
    )


@dataclass(frozen=True)
class AssistedLimitProposal:
    schema_version: str
    revision: int
    joint_names: tuple[str, ...]
    minimum_display: tuple[float, ...]
    maximum_display: tuple[float, ...]
    accepted_sample_count: int
    workspace_fingerprint: str
    reviewed: bool = False

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        for key in ("joint_names", "minimum_display", "maximum_display"):
            result[key] = list(result[key])
        return result


def build_assisted_limit_proposal(
    accepted_display_vectors: Sequence[Sequence[float]],
    mechanical_minimum: Sequence[float],
    mechanical_maximum: Sequence[float],
    *,
    margin_fraction: float = 0.05,
    revision: int = 1,
    reviewed: bool = False,
) -> AssistedLimitProposal:
    def planning_display_vector(vector: Sequence[float]) -> tuple[float, ...]:
        values = tuple(float(value) for value in vector)
        # Workspace/UI compatibility vectors may still carry the fixed visual
        # spindle slot. Only J1–J5 participate in the proposal.
        if len(values) == len(JOINT_NAMES) + 1:
            values = values[: len(JOINT_NAMES)]
        return _finite_tuple(values, len(JOINT_NAMES), "workspace joint vector")

    samples = tuple(planning_display_vector(vector) for vector in accepted_display_vectors)
    if not samples:
        raise ValueError("assisted limits require at least one accepted workspace sample")
    mechanical_min = planning_display_vector(mechanical_minimum)
    mechanical_max = planning_display_vector(mechanical_maximum)
    margin_fraction = float(margin_fraction)
    if not 0.0 <= margin_fraction <= 0.5:
        raise ValueError("assisted-limit margin fraction must be between 0 and 0.5")
    minima = []
    maxima = []
    for index in range(len(JOINT_NAMES)):
        observed_min = min(sample[index] for sample in samples)
        observed_max = max(sample[index] for sample in samples)
        margin = max(
            (observed_max - observed_min) * margin_fraction,
            (mechanical_max[index] - mechanical_min[index]) * 0.005,
        )
        minima.append(max(mechanical_min[index], observed_min - margin))
        maxima.append(min(mechanical_max[index], observed_max + margin))
    workspace_payload = {
        "samples": samples,
        "mechanical_minimum": mechanical_min,
        "mechanical_maximum": mechanical_max,
    }
    return AssistedLimitProposal(
        schema_version=STATE_SCHEMA_VERSION,
        revision=max(1, int(revision)),
        joint_names=JOINT_NAMES,
        minimum_display=tuple(minima),
        maximum_display=tuple(maxima),
        accepted_sample_count=len(samples),
        workspace_fingerprint=fingerprint(workspace_payload),
        reviewed=bool(reviewed),
    )


@dataclass(frozen=True)
class TaskSnapshot:
    schema_version: str
    target_segment_id: str
    trajectory_revision: str
    entry_ras_mm: tuple[float, float, float]
    target_ras_mm: tuple[float, float, float]
    base_fingerprint: str
    home_fingerprint: str
    limits_fingerprint: str
    robot_profile_fingerprint: str
    tool_frame: str
    tool_provenance: str
    corridor_radius_mm: float
    snapshot_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["entry_ras_mm"] = list(self.entry_ras_mm)
        result["target_ras_mm"] = list(self.target_ras_mm)
        return result


def build_task_snapshot(
    *,
    target_segment_id: str,
    trajectory_revision: str,
    entry_ras_mm: Sequence[float],
    target_ras_mm: Sequence[float],
    base_fingerprint: str,
    home_fingerprint: str,
    limits_fingerprint: str,
    robot_profile_fingerprint: str,
    tool_frame: str = "dentobot_drill_tcp",
    tool_provenance: str = "CAD-derived/provisional/un-calibrated",
    corridor_radius_mm: float = 0.75,
) -> TaskSnapshot:
    entry = _finite_tuple(entry_ras_mm, 3, "Entry RAS")
    target = _finite_tuple(target_ras_mm, 3, "Target RAS")
    length = sqrt(sum((b - a) ** 2 for a, b in zip(entry, target)))
    if length <= 0.0:
        raise ValueError("Entry and Target must define a non-zero trajectory")
    required = {
        "target_segment_id": str(target_segment_id).strip(),
        "trajectory_revision": str(trajectory_revision).strip(),
        "base_fingerprint": str(base_fingerprint).strip(),
        "home_fingerprint": str(home_fingerprint).strip(),
        "limits_fingerprint": str(limits_fingerprint).strip(),
        "robot_profile_fingerprint": str(robot_profile_fingerprint).strip(),
        "tool_frame": str(tool_frame).strip(),
        "tool_provenance": str(tool_provenance).strip(),
    }
    if not all(required.values()):
        missing = ", ".join(key for key, value in required.items() if not value)
        raise ValueError(f"task snapshot is missing: {missing}")
    radius = float(corridor_radius_mm)
    if not isfinite(radius) or radius <= 0.0:
        raise ValueError("trajectory corridor radius must be positive")
    identity = {
        **required,
        "entry_ras_mm": entry,
        "target_ras_mm": target,
        "corridor_radius_mm": radius,
    }
    return TaskSnapshot(
        schema_version=STATE_SCHEMA_VERSION,
        entry_ras_mm=entry,
        target_ras_mm=target,
        corridor_radius_mm=radius,
        snapshot_fingerprint=fingerprint(identity),
        **required,
    )


def parse_task_snapshot(payload: str | Mapping[str, object]) -> TaskSnapshot:
    data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    if data.get("schema_version") != STATE_SCHEMA_VERSION:
        raise ValueError("unsupported confirmed-task schema")
    rebuilt = build_task_snapshot(
        target_segment_id=str(data.get("target_segment_id") or ""),
        trajectory_revision=str(data.get("trajectory_revision") or ""),
        entry_ras_mm=data.get("entry_ras_mm", ()),
        target_ras_mm=data.get("target_ras_mm", ()),
        base_fingerprint=str(data.get("base_fingerprint") or ""),
        home_fingerprint=str(data.get("home_fingerprint") or ""),
        limits_fingerprint=str(data.get("limits_fingerprint") or ""),
        robot_profile_fingerprint=str(data.get("robot_profile_fingerprint") or ""),
        tool_frame=str(data.get("tool_frame") or ""),
        tool_provenance=str(data.get("tool_provenance") or ""),
        corridor_radius_mm=float(data.get("corridor_radius_mm", 0.0)),
    )
    if rebuilt.snapshot_fingerprint != str(data.get("snapshot_fingerprint") or ""):
        raise ValueError("confirmed-task fingerprint does not match its contents")
    return rebuilt


def task_snapshot_invalidation_reasons(
    snapshot: TaskSnapshot,
    *,
    target_segment_id: str,
    trajectory_revision: str,
    base_fingerprint: str,
    home_fingerprint: str,
    limits_fingerprint: str,
    robot_profile_fingerprint: str,
    tool_frame: str,
) -> tuple[str, ...]:
    comparisons = (
        ("target tooth", snapshot.target_segment_id, target_segment_id),
        ("trajectory", snapshot.trajectory_revision, trajectory_revision),
        ("base pose", snapshot.base_fingerprint, base_fingerprint),
        ("Task Home", snapshot.home_fingerprint, home_fingerprint),
        ("assisted limits", snapshot.limits_fingerprint, limits_fingerprint),
        ("robot resources", snapshot.robot_profile_fingerprint, robot_profile_fingerprint),
        ("tool profile", snapshot.tool_frame, tool_frame),
    )
    return tuple(label for label, expected, actual in comparisons if expected != actual)


@dataclass(frozen=True)
class CollisionSceneAudit:
    """Persistent evidence for the collision payload prepared by Step 6.

    ROS publishers, proxy nodes, and MoveIt state remain transient.  This
    record stores only bounded geometry/transform evidence and explicitly
    distinguishes a successful publish call from runtime scene acknowledgement.
    """

    schema_version: str
    generated_at_utc: str
    status: str
    base_fingerprint: str
    jaw_preparation_fingerprint: str
    world_to_base_fingerprint: str
    object_records: tuple[dict[str, object], ...]
    runtime_acknowledgement: dict[str, object]
    audit_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["object_records"] = [dict(item) for item in self.object_records]
        result["runtime_acknowledgement"] = dict(self.runtime_acknowledgement)
        return result


def build_collision_scene_audit(
    *,
    status: str,
    base_fingerprint: str,
    jaw_preparation_fingerprint: str,
    world_to_base_fingerprint: str,
    object_records: Sequence[Mapping[str, object]],
    runtime_acknowledgement: Mapping[str, object],
    generated_at_utc: str = "",
) -> CollisionSceneAudit:
    """Validate and fingerprint a bounded outgoing collision-scene manifest."""

    normalized_records = tuple(
        json.loads(canonical_json(dict(record))) for record in object_records
    )
    object_ids = [
        str(record.get("outgoing_collision_object_id") or "").strip()
        for record in normalized_records
    ]
    if not normalized_records or not all(object_ids):
        raise ValueError("collision audit requires identified outgoing objects")
    if len(set(object_ids)) != len(object_ids):
        raise ValueError("collision audit outgoing object IDs must be unique")
    required_record_fields = (
        "source_id",
        "source_role",
        "classification",
        "source_fingerprint",
        "outgoing_fingerprint",
        "source_bounds_world_ras_mm",
        "outgoing_bounds_base_link_mm",
        "source_point_count",
        "source_cell_count",
        "outgoing_point_count",
        "outgoing_cell_count",
        "connected_component_count",
        "boundary_or_nonmanifold_edge_count",
        "jaw_transform_application_count",
        "world_to_base_application_count",
        "publisher_linear_scale_m_per_mm",
        "collision_padding_mm",
        "publish_status",
    )
    for record in normalized_records:
        missing = [name for name in required_record_fields if name not in record]
        if missing:
            raise ValueError(
                "collision audit object is missing: " + ", ".join(missing)
            )
        if int(record["jaw_transform_application_count"]) not in {0, 1}:
            raise ValueError("jaw transform must be applied zero or one time")
        if int(record["world_to_base_application_count"]) != 1:
            raise ValueError("world-to-base transform must be applied exactly once")
        if abs(float(record["publisher_linear_scale_m_per_mm"]) - 0.001) > 1e-12:
            raise ValueError("collision publisher scale must be 0.001 m/mm")
        if float(record["collision_padding_mm"]) < 0.0:
            raise ValueError("collision padding cannot be negative")
    generated = str(generated_at_utc or "").strip() or datetime.now(
        timezone.utc
    ).isoformat()
    identity = {
        "schema_version": COLLISION_AUDIT_SCHEMA_VERSION,
        "generated_at_utc": generated,
        "status": str(status).strip(),
        "base_fingerprint": str(base_fingerprint).strip(),
        "jaw_preparation_fingerprint": str(jaw_preparation_fingerprint).strip(),
        "world_to_base_fingerprint": str(world_to_base_fingerprint).strip(),
        "object_records": normalized_records,
        "runtime_acknowledgement": json.loads(
            canonical_json(dict(runtime_acknowledgement))
        ),
    }
    if not identity["status"] or not identity["base_fingerprint"]:
        raise ValueError("collision audit requires status and base fingerprint")
    return CollisionSceneAudit(
        audit_fingerprint=fingerprint(identity),
        **identity,
    )


def parse_collision_scene_audit(
    payload: str | Mapping[str, object],
) -> CollisionSceneAudit:
    data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    if data.get("schema_version") != COLLISION_AUDIT_SCHEMA_VERSION:
        raise ValueError("unsupported collision-audit schema")
    rebuilt = build_collision_scene_audit(
        status=str(data.get("status") or ""),
        base_fingerprint=str(data.get("base_fingerprint") or ""),
        jaw_preparation_fingerprint=str(
            data.get("jaw_preparation_fingerprint") or ""
        ),
        world_to_base_fingerprint=str(data.get("world_to_base_fingerprint") or ""),
        object_records=data.get("object_records", ()),
        runtime_acknowledgement=data.get("runtime_acknowledgement", {}),
        generated_at_utc=str(data.get("generated_at_utc") or ""),
    )
    if rebuilt.audit_fingerprint != str(data.get("audit_fingerprint") or ""):
        raise ValueError("collision-audit fingerprint does not match its contents")
    return rebuilt


@dataclass(frozen=True)
class MotionDiagnosticSession:
    schema_version: str
    generated_at_utc: str
    state: str
    stale_reason: str
    task_fingerprint: str
    base_fingerprint: str
    trajectory_fingerprint: str
    robot_profile_fingerprint: str
    collision_audit_fingerprint: str
    planning_parameters_fingerprint: str
    candidate_records: tuple[dict[str, object], ...]
    selected_candidate_index: int
    failure_classification: str
    operator_review_state: str
    stage_outcomes: tuple[dict[str, object], ...]
    full_task_outcome: dict[str, object]
    session_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["candidate_records"] = [
            dict(record) for record in self.candidate_records
        ]
        result["stage_outcomes"] = [dict(record) for record in self.stage_outcomes]
        result["full_task_outcome"] = dict(self.full_task_outcome)
        return result


def build_motion_diagnostic_session(
    *,
    state: str,
    stale_reason: str = "",
    task_fingerprint: str,
    base_fingerprint: str,
    trajectory_fingerprint: str,
    robot_profile_fingerprint: str,
    collision_audit_fingerprint: str,
    planning_parameters_fingerprint: str,
    candidate_records: Sequence[Mapping[str, object]],
    selected_candidate_index: int,
    failure_classification: str,
    operator_review_state: str = "Unreviewed",
    generated_at_utc: str = "",
    schema_version: str = MOTION_DIAGNOSTIC_SCHEMA_VERSION,
    stage_outcomes: Sequence[Mapping[str, object]] = (),
    full_task_outcome: Mapping[str, object] | None = None,
) -> MotionDiagnosticSession:
    schema = str(schema_version).strip()
    if schema not in SUPPORTED_MOTION_DIAGNOSTIC_SCHEMA_VERSIONS:
        raise ValueError("unsupported motion-diagnostic schema")
    records = tuple(json.loads(canonical_json(dict(item))) for item in candidate_records)
    if not records or len(records) > 32:
        raise ValueError("motion diagnostic requires 1–32 bounded candidates")
    selected = int(selected_candidate_index)
    if selected < 0 or selected >= len(records):
        raise ValueError("selected diagnostic candidate is out of range")
    required_context = {
        "task_fingerprint": str(task_fingerprint).strip(),
        "base_fingerprint": str(base_fingerprint).strip(),
        "trajectory_fingerprint": str(trajectory_fingerprint).strip(),
        "robot_profile_fingerprint": str(robot_profile_fingerprint).strip(),
        "collision_audit_fingerprint": str(collision_audit_fingerprint).strip(),
        "planning_parameters_fingerprint": str(
            planning_parameters_fingerprint
        ).strip(),
    }
    if not all(required_context.values()):
        missing = ", ".join(key for key, value in required_context.items() if not value)
        raise ValueError("motion diagnostic context is missing: " + missing)
    for record in records:
        for name in (
            "candidate_index",
            "axial_roll_deg",
            "success",
            "completion_fraction",
            "completed_distance_mm",
            "requested_distance_mm",
            "waypoint_count",
            "failure_classification",
        ):
            if name not in record:
                raise ValueError(f"motion diagnostic candidate is missing {name}")
        fraction_value = float(record["completion_fraction"])
        if not isfinite(fraction_value) or not 0.0 <= fraction_value <= 1.0:
            raise ValueError("candidate completion fraction must be in [0, 1]")
    generated = str(generated_at_utc or "").strip() or datetime.now(
        timezone.utc
    ).isoformat()
    stages = tuple(
        json.loads(canonical_json(dict(item))) for item in stage_outcomes
    )
    full_outcome = json.loads(canonical_json(dict(full_task_outcome or {})))
    if schema != "1.0":
        valid_stage_names = {
            "stage1_free_space",
            (
                "stage2_fixed_axis_terminal"
                if schema == MOTION_DIAGNOSTIC_SCHEMA_VERSION
                else "stage2_strict_axis"
            ),
            "stage3_drilling",
        }
        for stage in stages:
            if str(stage.get("stage") or "") not in valid_stage_names:
                raise ValueError("motion diagnostic contains an unknown stage outcome")
            if "status" not in stage:
                raise ValueError("motion diagnostic stage outcome is missing status")
    identity = {
        "schema_version": schema,
        "generated_at_utc": generated,
        "state": str(state).strip(),
        "stale_reason": str(stale_reason).strip(),
        **required_context,
        "candidate_records": records,
        "selected_candidate_index": selected,
        "failure_classification": str(failure_classification).strip(),
        "operator_review_state": str(operator_review_state).strip(),
    }
    if schema != "1.0":
        identity["stage_outcomes"] = stages
        identity["full_task_outcome"] = full_outcome
    if not identity["state"] or not identity["failure_classification"]:
        raise ValueError("motion diagnostic requires state and classification")
    return MotionDiagnosticSession(
        session_fingerprint=fingerprint(identity),
        stage_outcomes=stages,
        full_task_outcome=full_outcome,
        **{
            key: value
            for key, value in identity.items()
            if key not in {"stage_outcomes", "full_task_outcome"}
        },
    )


def parse_motion_diagnostic_session(
    payload: str | Mapping[str, object],
) -> MotionDiagnosticSession:
    data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    schema = str(data.get("schema_version") or "")
    if schema not in SUPPORTED_MOTION_DIAGNOSTIC_SCHEMA_VERSIONS:
        raise ValueError("unsupported motion-diagnostic schema")
    rebuilt = build_motion_diagnostic_session(
        state=str(data.get("state") or ""),
        stale_reason=str(data.get("stale_reason") or ""),
        task_fingerprint=str(data.get("task_fingerprint") or ""),
        base_fingerprint=str(data.get("base_fingerprint") or ""),
        trajectory_fingerprint=str(data.get("trajectory_fingerprint") or ""),
        robot_profile_fingerprint=str(data.get("robot_profile_fingerprint") or ""),
        collision_audit_fingerprint=str(data.get("collision_audit_fingerprint") or ""),
        planning_parameters_fingerprint=str(
            data.get("planning_parameters_fingerprint") or ""
        ),
        candidate_records=data.get("candidate_records", ()),
        selected_candidate_index=int(data.get("selected_candidate_index", -1)),
        failure_classification=str(data.get("failure_classification") or ""),
        operator_review_state=str(data.get("operator_review_state") or ""),
        generated_at_utc=str(data.get("generated_at_utc") or ""),
        schema_version=schema,
        stage_outcomes=data.get("stage_outcomes", ()),
        full_task_outcome=data.get("full_task_outcome", {}),
    )
    if rebuilt.session_fingerprint != str(data.get("session_fingerprint") or ""):
        raise ValueError("motion-diagnostic fingerprint does not match its contents")
    return rebuilt


@dataclass(frozen=True)
class PhaseGuardConfiguration:
    schema_version: str
    task_fingerprint: str
    target_object_id: str
    allowed_contact_pair: tuple[str, str]
    tool_tip_frame: str
    entry_ras_mm: tuple[float, float, float]
    target_ras_mm: tuple[float, float, float]
    corridor_radius_mm: float

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        for key in ("allowed_contact_pair", "entry_ras_mm", "target_ras_mm"):
            result[key] = list(result[key])
        return result


def build_phase_guard_configuration(
    snapshot: TaskSnapshot,
    *,
    target_object_id: str,
    burr_link: str = "burr",
) -> PhaseGuardConfiguration:
    target_object_id = str(target_object_id).strip()
    if not target_object_id:
        raise ValueError("phase guard requires a target planning-scene object")
    return PhaseGuardConfiguration(
        schema_version=STATE_SCHEMA_VERSION,
        task_fingerprint=snapshot.snapshot_fingerprint,
        target_object_id=target_object_id,
        allowed_contact_pair=(str(burr_link), target_object_id),
        tool_tip_frame=snapshot.tool_frame,
        entry_ras_mm=snapshot.entry_ras_mm,
        target_ras_mm=snapshot.target_ras_mm,
        corridor_radius_mm=snapshot.corridor_radius_mm,
    )


@dataclass(frozen=True)
class PhaseJointCommand:
    schema_version: str
    task_fingerprint: str
    phase: MotionPhase
    sequence: int
    joint_names: tuple[str, ...]
    joint_positions_si: tuple[float, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "task_fingerprint": self.task_fingerprint,
            "phase": self.phase.value,
            "sequence": self.sequence,
            "joint_names": list(self.joint_names),
            "joint_positions_si": list(self.joint_positions_si),
        }


def build_phase_joint_command(
    *,
    task_fingerprint: str,
    phase: MotionPhase | str,
    sequence: int,
    joint_positions_si: Mapping[str, float],
) -> PhaseJointCommand:
    try:
        phase_value = phase if isinstance(phase, MotionPhase) else MotionPhase(str(phase))
    except ValueError as exc:
        raise ValueError("unknown task motion phase") from exc
    if not task_fingerprint:
        raise ValueError("phase command requires a task fingerprint")
    if int(sequence) < 0:
        raise ValueError("phase command sequence must be non-negative")
    canonical_positions = canonicalize_planning_joint_positions(joint_positions_si)
    values = _finite_tuple(
        [canonical_positions[name] for name in JOINT_NAMES],
        len(JOINT_NAMES),
        "phase joint vector",
    )
    return PhaseJointCommand(
        schema_version=STATE_SCHEMA_VERSION,
        task_fingerprint=str(task_fingerprint),
        phase=phase_value,
        sequence=int(sequence),
        joint_names=JOINT_NAMES,
        joint_positions_si=values,
    )


def approach_points(
    entry_ras_mm: Sequence[float],
    target_ras_mm: Sequence[float],
    standoff_mm: float = 2.0,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    entry = _finite_tuple(entry_ras_mm, 3, "Entry RAS")
    target = _finite_tuple(target_ras_mm, 3, "Target RAS")
    vector = tuple(target[index] - entry[index] for index in range(3))
    length = sqrt(sum(value * value for value in vector))
    distance = float(standoff_mm)
    if length <= 0.0 or not isfinite(distance) or distance <= 0.0:
        raise ValueError("approach requires a non-zero trajectory and positive standoff")
    unit = tuple(value / length for value in vector)
    pre_entry = tuple(entry[index] - distance * unit[index] for index in range(3))
    return pre_entry, entry
