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
from enum import Enum
from math import isfinite, sqrt
from typing import Mapping, Sequence


STATE_SCHEMA_VERSION = "1.0"
JOINT_NAMES = (
    "link-1_Revolute-1",
    "link-2_Slider-2",
    "link-3_Revolute-3",
    "link-4_Slider-4",
    "link-5_Revolute-5",
    "pneumatic_spindle-Copy_Revolute-6",
)


class BasePlacementStatus(str, Enum):
    UNLOCKED = "Unlocked"
    PROVISIONAL_LOCKED = "ProvisionalLocked"
    REGISTERED_LOCKED = "RegisteredLocked"
    STALE = "Stale"


class MotionPhase(str, Enum):
    APPROACH = "approach"
    TERMINAL_CONTACT = "terminal_contact"
    DRILLING = "drilling"


def _finite_tuple(values: Sequence[float], count: int, label: str) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if len(result) != count or not all(isfinite(value) for value in result):
        raise ValueError(f"{label} must contain {count} finite values")
    return result


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


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


@dataclass(frozen=True)
class TaskHomeRecord:
    schema_version: str
    revision: int
    joint_names: tuple[str, ...]
    joint_positions_si: tuple[float, ...]
    base_fingerprint: str
    robot_profile_fingerprint: str

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
) -> TaskHomeRecord:
    values = _finite_tuple(
        [joint_positions_si[name] for name in JOINT_NAMES],
        len(JOINT_NAMES),
        "Task Home joint vector",
    )
    if not base_fingerprint or not robot_profile_fingerprint:
        raise ValueError("Task Home requires base and robot-profile fingerprints")
    return TaskHomeRecord(
        schema_version=STATE_SCHEMA_VERSION,
        revision=max(1, int(revision)),
        joint_names=JOINT_NAMES,
        joint_positions_si=values,
        base_fingerprint=str(base_fingerprint),
        robot_profile_fingerprint=str(robot_profile_fingerprint),
    )


def parse_task_home(payload: str | Mapping[str, object]) -> TaskHomeRecord:
    data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    if data.get("schema_version") != STATE_SCHEMA_VERSION:
        raise ValueError("unsupported Task Home schema")
    names = tuple(str(value) for value in data.get("joint_names", ()))
    if names != JOINT_NAMES:
        raise ValueError("Task Home joint order does not match the DENTOBOT profile")
    return build_task_home(
        dict(zip(names, data.get("joint_positions_si", ()))),
        base_fingerprint=str(data.get("base_fingerprint") or ""),
        robot_profile_fingerprint=str(data.get("robot_profile_fingerprint") or ""),
        revision=int(data.get("revision", 0)),
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
    samples = tuple(
        _finite_tuple(vector, len(JOINT_NAMES), "workspace joint vector")
        for vector in accepted_display_vectors
    )
    if not samples:
        raise ValueError("assisted limits require at least one accepted workspace sample")
    mechanical_min = _finite_tuple(mechanical_minimum, len(JOINT_NAMES), "mechanical minima")
    mechanical_max = _finite_tuple(mechanical_maximum, len(JOINT_NAMES), "mechanical maxima")
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
    tool_frame: str = "dentobot_drill_tip_provisional",
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
    values = _finite_tuple(
        [joint_positions_si[name] for name in JOINT_NAMES],
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
