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
COLLISION_AUDIT_SCHEMA_VERSION = "1.0"
MOTION_DIAGNOSTIC_SCHEMA_VERSION = "1.0"
MANUAL_SIMULATION_BASE_SOURCE = "manual-simulation-base"
QUARANTINED_CIRCULAR_BASE_SOURCE = "quarantined-circular-mount-plane"
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
    values = _finite_tuple(
        [joint_positions_si[name] for name in JOINT_NAMES],
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
    session_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["candidate_records"] = [
            dict(record) for record in self.candidate_records
        ]
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
) -> MotionDiagnosticSession:
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
    identity = {
        "schema_version": MOTION_DIAGNOSTIC_SCHEMA_VERSION,
        "generated_at_utc": generated,
        "state": str(state).strip(),
        "stale_reason": str(stale_reason).strip(),
        **required_context,
        "candidate_records": records,
        "selected_candidate_index": selected,
        "failure_classification": str(failure_classification).strip(),
        "operator_review_state": str(operator_review_state).strip(),
    }
    if not identity["state"] or not identity["failure_classification"]:
        raise ValueError("motion diagnostic requires state and classification")
    return MotionDiagnosticSession(
        session_fingerprint=fingerprint(identity),
        **identity,
    )


def parse_motion_diagnostic_session(
    payload: str | Mapping[str, object],
) -> MotionDiagnosticSession:
    data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    if data.get("schema_version") != MOTION_DIAGNOSTIC_SCHEMA_VERSION:
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
