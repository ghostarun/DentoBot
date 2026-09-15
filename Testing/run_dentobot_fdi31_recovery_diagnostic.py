"""Bounded Campaign-1 P1/P2 diagnostics for the frozen FDI31 package.

The script deliberately has no Slicer imports at module import time.  That
keeps the evidence/state helpers testable on the host and makes the selected
phase an explicit trust boundary.  P1 opens the saved r7 package and audits
the existing scene.  P2 uses only explicit-state MoveIt/FK queries and the
native task guard's ``validate_only`` path; it never starts the stack, opens a
planner, publishes the raw joint heartbeat, connects a controller, or sends a
physical command.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
import traceback
from typing import Any, Mapping, Sequence


RUN_ID = os.environ.get("DENTOBOT_RECOVERY_RUN_ID", "c1-p1p2-20260914-r1")
ALLOWED_PHASES = {"p1_scene_audit", "p2_state_contact"}
EXPECTED_TARGET_SEGMENT = "2.25.127809691704402484963988182477922906518"
EXPECTED_ENTRY_RAS_MM = (
    -95.57978088281602,
    -68.3080212750595,
    32.524279290412125,
)
EXPECTED_TARGET_RAS_MM = (
    -95.07911746332762,
    -74.1254665588325,
    29.29612472144273,
)
EXPECTED_DEPTH_MM = 6.67190493116205
POSITION_TOLERANCE_MM = 0.25
AXIS_TOLERANCE_DEG = 0.5
EXPECTED_NATIVE_SOURCE_SHA256 = "f2852e2bd9853f4dd2dc33ef170fbf3b46b09444ab7e279b0e54d8498f419c77"
EXPECTED_NATIVE_BINARY_SHA256 = "9667b3aa6091db70cbb32c118af68af8f1d43179f099c6344f9184e2549c9ce9"
CORRECTED_NATIVE_SOURCE_SHA256 = "8259a062b8c314fedb7a5ac95652a53ea280cfca2b67a6f6eda57b50ff2273b3"
CORRECTED_NATIVE_BINARY_SHA256 = "f1132ea07d81c39249539c05c8900c817f39d50a95a6574ac3974f17e512fc3d"


def phase_aware_static_interface_proposal() -> dict[str, Any]:
    """Describe the smallest native addition needed for an honest P2 static query."""

    return {
        "required": True,
        "available_in_current_sources": True,
        "status": "implemented_in_existing_task_guard_contract",
        "reason": (
            "MoveIt CheckMoveItStateValidity remains a generic comparison; the "
            "existing task-guard topic now also exposes a read-only phase-aware "
            "static predicate and correlated transition telemetry."
        ),
        "existing_command_topic": "/dentobot/task_joint_command",
        "existing_status_topic": "/dentobot/task_joint_status",
        "request_addition": {
            "validation_kind": "static_state",
            "request_id": "opaque-per-request-id",
            "task_fingerprint": "active immutable task",
            "guard_session_id": "active transient guard session",
            "phase": "approach|terminal_contact|drilling|retraction",
            "joint_positions": "ordered planning J1-J5 vector",
        },
        "response_addition": {
            "validation_kind": "static_state",
            "request_id": "echoed exactly",
            "requested_positions": "echoed exactly",
            "evaluated_positions": "same single requested state",
            "interpolation": {
                "mode": "none",
                "sample_count": 1,
                "interpolation_fraction": 1.0,
            },
            "collision_scene_policy_fingerprint": "echoed guard-scene policy identity",
        },
        "transition_telemetry_addition": {
            "request": {
                "validation_kind": "transition",
                "request_id": "opaque-per-request-id",
                "starting_positions": "guard preflight state actually used",
            },
            "response": {
                "validation_kind": "transition",
                "request_id": "echoed exactly",
                "starting_positions": "actual interpolation start",
                "requested_positions": "endpoint submitted by the runner",
                "evaluated_positions": "sample that was actually evaluated/rejected",
                "evaluated_sample_index": "one-based sample index",
                "interpolation_fraction": "fraction from actual start to request",
                "total_sample_count": "native interpolation count",
                "collision_scene_policy_fingerprint": "echoed guard-scene policy identity",
            },
        },
        "semantics": (
            "Evaluate one requested state with the existing phase policy, without "
            "mutating accepted or preflight state and without publishing motion."
        ),
        "implementation": {
            "native_owner": "dentobot_moveit_config/src/collision_guard.cpp",
            "bridge_owner": "DENTOWorkflow/Resources/Python/DENTOROS2Bridge.py",
            "scene_acknowledgement": "correlated static_state task-status readback",
        },
        "guard_policy_change": False,
    }


def phase_guard(phase: str) -> str:
    """Reject P3/P4 and accidental broad-run invocation before Slicer work."""

    value = str(phase or "").strip()
    if value not in ALLOWED_PHASES:
        raise ValueError(
            f"Campaign-1 diagnostic runner only permits {sorted(ALLOWED_PHASES)}; "
            f"received {value!r}."
        )
    return value


def _jsonable(value: Any, *, depth: int = 0) -> Any:
    """Convert bounded diagnostic values without turning unknowns into zero."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if depth > 12:
        return "<depth-limit>"
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name), depth=depth + 1)
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item, depth=depth + 1) for item in value]
    if hasattr(value, "GetID") and hasattr(value, "GetClassName"):
        return {
            "id": str(value.GetID() or ""),
            "name": str(value.GetName() or "") if hasattr(value, "GetName") else "",
            "class": str(value.GetClassName()),
        }
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _jsonable(value.to_dict(), depth=depth + 1)
        except Exception:
            pass
    try:
        item = value.item()
    except Exception:
        item = None
    if item is not None and item is not value:
        return _jsonable(item, depth=depth + 1)
    return str(value)


def atomic_json_write(path: str | Path, payload: Mapping[str, Any]) -> None:
    """Write one durable report without exposing a partial JSON artifact."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(destination.parent),
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def corrected_native_build_identity() -> dict[str, Any]:
    """Hash the source and install binary visible to the running Slicer container."""

    checkout = Path(__file__).resolve().parents[1]
    source_path = checkout / "dentobot_moveit_config/src/collision_guard.cpp"
    binary_candidates = (
        Path("/workspace/ros2_ws/install/dentobot_moveit_config/lib/dentobot_moveit_config/collision_guard"),
        checkout.parent.parent / "install/dentobot_moveit_config/lib/dentobot_moveit_config/collision_guard",
    )
    binary_path = next((path for path in binary_candidates if path.is_file()), None)
    result = {
        "source_path": str(source_path),
        "binary_path": str(binary_path) if binary_path is not None else None,
        "source_sha256": file_sha256(source_path) if source_path.is_file() else None,
        "binary_sha256": file_sha256(binary_path) if binary_path is not None else None,
    }
    result["available"] = bool(result["source_sha256"] and result["binary_sha256"])
    result["matches_corrected_build"] = bool(
        result["source_sha256"] == CORRECTED_NATIVE_SOURCE_SHA256
        and result["binary_sha256"] == CORRECTED_NATIVE_BINARY_SHA256
    )
    return result


def state_slot(
    name: str,
    *,
    positions_si: Mapping[str, Any] | None = None,
    stage: str | None = None,
    composed_index: int | None = None,
    stage_index: int | None = None,
    edge: Mapping[str, Any] | None = None,
    interpolation_fraction: float | None = None,
    fk: Mapping[str, Any] | None = None,
    axis_ras: Sequence[float] | None = None,
    axial_depth_mm: float | None = None,
    phase: str | None = None,
    guard_outcome: Mapping[str, Any] | None = None,
    relation_to_rejected: str | None = None,
    unknown_reason: str | None = None,
) -> dict[str, Any]:
    """Create one explicit state slot; absent states remain null."""

    available = positions_si is not None
    return {
        "name": str(name),
        "available": available,
        "joints_si": dict(positions_si) if available else None,
        "stage": stage,
        "composed_index": composed_index,
        "stage_index": stage_index,
        "edge": dict(edge) if edge is not None else None,
        "interpolation_fraction": interpolation_fraction,
        "fk": dict(fk) if fk is not None else None,
        "axis_ras": list(axis_ras) if axis_ras is not None else None,
        "axial_depth_mm": axial_depth_mm,
        "phase": phase,
        "guard_outcome": dict(guard_outcome) if guard_outcome is not None else None,
        "relation_to_rejected": relation_to_rejected,
        "unknown_reason": None if available else (unknown_reason or "not observed"),
    }


def static_state_record(
    *,
    positions_si: Mapping[str, Any] | None,
    valid: bool | None,
    message: str = "",
    authoritative: bool | None = None,
    phase_aware: bool = False,
    native_status: Mapping[str, Any] | None = None,
    source: str = "MoveIt CheckMoveItStateValidity",
) -> dict[str, Any]:
    """Keep an endpoint predicate separate from any phase transition result."""

    return {
        "kind": "static_state_validity",
        "predicate": source,
        "phase_aware": bool(phase_aware),
        "requested_state": {
            "joints_si": dict(positions_si) if positions_si is not None else None,
            "source": "retained_r13_candidate_endpoint",
        },
        "valid": valid,
        "authoritative": authoritative,
        "message": str(message or ""),
        "native": {
            "request_id": (native_status or {}).get("request_id"),
            "validation_kind": (native_status or {}).get("validation_kind"),
            "phase": (native_status or {}).get("phase"),
            "evaluated_positions": (native_status or {}).get("evaluated_positions"),
            "evaluated_sample_index": (native_status or {}).get("evaluated_sample_index"),
            "interpolation_fraction": (native_status or {}).get("interpolation_fraction"),
            "total_sample_count": (native_status or {}).get("total_sample_count"),
            "collision_scene_policy_fingerprint": (native_status or {}).get(
                "collision_scene_policy_fingerprint"
            ),
        },
        "attribution": (
            "endpoint static predicate only; it does not describe the Home-to-"
            "endpoint phase transition or its first rejected sample"
        ),
        "unknown_reason": None if positions_si is not None else "no candidate vector",
    }


def phase_transition_record(
    *,
    transition_id: str,
    start_positions_si: Mapping[str, Any] | None,
    requested_positions_si: Mapping[str, Any] | None,
    phase: str,
    sequence: int,
    validate_only: bool,
    native_status: Mapping[str, Any] | None = None,
    start_source: str = "setup Home seeded the guard preflight state",
    requested_source: str = "retained r13 candidate endpoint",
    joint_order: Sequence[str] = (),
) -> dict[str, Any]:
    """Record exactly what a phased guard command tested, without endpoint attribution."""

    status = dict(native_status or {})
    reported_validate_only = status.get("validate_only")
    if not isinstance(reported_validate_only, bool):
        reported_validate_only = bool(validate_only)
    checked_samples = status.get("checked_samples")
    if not isinstance(checked_samples, int) or checked_samples < 0:
        checked_samples = None
    reported_requested = status.get("requested_positions")
    reported_evaluated = status.get("evaluated_positions")
    evaluated_available = isinstance(reported_evaluated, (list, tuple)) and bool(
        reported_evaluated
    )
    sample_index = status.get("evaluated_sample_index")
    if not isinstance(sample_index, int) or sample_index < 1:
        sample_index = 1 if status.get("accepted") is False and checked_samples == 1 else None
    evaluated_fraction = status.get("interpolation_fraction")
    if evaluated_fraction is None and status.get("accepted") is False:
        evaluated_fraction = status.get("first_rejection_interpolation_fraction")
    first_sample_basis = (
        "native evaluated-sample telemetry is correlated to this request"
        if evaluated_available and sample_index is not None and evaluated_fraction is not None
        else "native status does not expose a complete evaluated-sample record"
    )
    return {
        "kind": "phase_transition_validity",
        "transition_id": str(transition_id),
        "phase": str(phase),
        "sequence": int(sequence),
        "validate_only": reported_validate_only,
        "starting_state": {
            "joints_si": dict(start_positions_si) if start_positions_si is not None else None,
            "source": str(start_source),
            "guard_role": "command start state; not an accepted r13 preceding edge",
            "native_reported_joints_si": status.get("starting_positions"),
            "native_accepted_positions": status.get("accepted_positions"),
            "joint_order": list(joint_order),
        },
        "requested_state": {
            "joints_si": dict(requested_positions_si) if requested_positions_si is not None else None,
            "source": str(requested_source),
            "is_static_endpoint_result": False,
        },
        "native_reported_requested_positions": reported_requested,
        "request_id": status.get("request_id"),
        "validation_kind": status.get("validation_kind"),
        "evaluated_or_rejected_sample": {
            "available": evaluated_available,
            "joints_si": reported_evaluated if evaluated_available else None,
            "sample_index": sample_index,
            "interpolation_fraction": evaluated_fraction,
            "native_checked_samples": checked_samples,
            "unknown_reason": (
                None
                if evaluated_available
                else "Native TaskJointStatus did not expose the evaluated sample vector."
            ),
            "sample_index_basis": first_sample_basis,
        },
        "result": {
            "accepted": status.get("accepted"),
            "reason": status.get("reason"),
            "corridor_ok": status.get("corridor_ok"),
            "corridor_progress": status.get("corridor_progress"),
            "minimum_world_distance_m": status.get("minimum_world_distance_m"),
            "first_body": status.get("first_body"),
            "second_body": status.get("second_body"),
            "attribution": "transition only; do not attribute this result to Target static validity",
        },
        "interpolation": {
            "method": "native joint interpolation from the guard preflight state",
            "total_sample_count": status.get("total_sample_count"),
            "checked_samples": checked_samples,
            "first_rejection_fraction": (
                status.get("first_rejection_interpolation_fraction")
                if status.get("accepted") is False
                else None
            ),
            "unknown_reason": (
                None
                if status.get("total_sample_count") is not None
                and evaluated_available
                and evaluated_fraction is not None
                else "Native status did not expose complete interpolation telemetry."
            ),
        },
        "attribution": (
            "The command validated a phase transition from setup Home/preflight to "
            "the requested endpoint; it is not a static Target verdict and not the "
            "retained r13 insertion edge."
        ),
    }


def _finite_matrix4(value: Any) -> list[list[float]] | None:
    try:
        rows = [[float(item) for item in row] for row in value]
    except (TypeError, ValueError):
        return None
    if len(rows) != 4 or any(len(row) != 4 for row in rows):
        return None
    if not all(math.isfinite(item) for row in rows for item in row):
        return None
    return rows


def compare_display_fk_transforms(
    displayed: Mapping[str, Any],
    native_fk: Mapping[str, Any],
    *,
    keys: Sequence[str] = ("tcp", "spindle"),
    translation_tolerance_mm: float = POSITION_TOLERANCE_MM,
    rotation_tolerance_deg: float = AXIS_TOLERANCE_DEG,
) -> dict[str, Any]:
    """Compare actual displayed link matrices against native FK, fail closed on absence."""

    comparisons: dict[str, Any] = {}
    for key in keys:
        observed = _finite_matrix4(displayed.get(key))
        expected = _finite_matrix4(native_fk.get(key))
        if observed is None or expected is None:
            comparisons[str(key)] = {
                "available": False,
                "match": None,
                "translation_error_mm": None,
                "rotation_error_deg": None,
                "unknown_reason": (
                    "No actual displayed transform and native FK pair was available; "
                    "a saved TCP marker is not accepted as mesh-transform evidence."
                ),
            }
            continue
        translation_error = math.sqrt(
            sum((observed[index][3] - expected[index][3]) ** 2 for index in range(3))
        )
        trace = sum(
            sum(expected[row][column] * observed[row][column] for row in range(3))
            for column in range(3)
        )
        cosine = max(-1.0, min(1.0, (trace - 1.0) / 2.0))
        rotation_error = math.degrees(math.acos(cosine))
        comparisons[str(key)] = {
            "available": True,
            "match": bool(
                translation_error <= float(translation_tolerance_mm)
                and rotation_error <= float(rotation_tolerance_deg)
            ),
            "translation_error_mm": translation_error,
            "rotation_error_deg": rotation_error,
            "translation_tolerance_mm": float(translation_tolerance_mm),
            "rotation_tolerance_deg": float(rotation_tolerance_deg),
        }
    available = all(item["available"] for item in comparisons.values()) if comparisons else False
    return {
        "available": available,
        "match": available and all(item["match"] is True for item in comparisons.values()),
        "comparisons": comparisons,
        "marker_only_rejected": True,
    }


def collision_scene_acknowledgement_evidence(
    expected_objects: Sequence[Mapping[str, Any]],
    observed_objects: Sequence[Mapping[str, Any]],
    *,
    expected_policy_fingerprint: str | None,
    observed_policy_fingerprint: str | None,
    readback_correlated: bool = False,
    reported_status: str = "",
) -> dict[str, Any]:
    """Require exact scene identity before native collision results are attributable."""

    expected_by_id = {
        str(record.get("outgoing_collision_object_id") or ""): record
        for record in expected_objects
        if str(record.get("outgoing_collision_object_id") or "")
    }
    observed_by_id = {
        str(record.get("id") or ""): record
        for record in observed_objects
        if str(record.get("id") or "")
    }
    mismatches: list[str] = []
    if set(expected_by_id) != set(observed_by_id):
        mismatches.append(
            "collision ID set differs: expected "
            f"{len(expected_by_id)}, observed {len(observed_by_id)}"
        )
    for object_id, expected in expected_by_id.items():
        observed = observed_by_id.get(object_id)
        if observed is None:
            continue
        expected_pose = expected.get("outgoing_pose_base_link_m_xyzw")
        observed_pose = observed.get("pose_base_link_m_xyzw")
        if expected_pose is None or observed_pose is None:
            mismatches.append(f"missing comparable base-link pose for {object_id}")
        else:
            try:
                if len(expected_pose) != 7 or len(observed_pose) != 7 or any(
                    abs(float(a) - float(b)) > 1.0e-9
                    for a, b in zip(expected_pose, observed_pose)
                ):
                    mismatches.append(f"runtime pose differs for {object_id}")
            except (TypeError, ValueError):
                mismatches.append(f"invalid comparable base-link pose for {object_id}")
        expected_bounds = expected.get("outgoing_bounds_base_link_mm")
        observed_bounds = observed.get("bounds_base_link_m")
        if expected_bounds is None or observed_bounds is None:
            mismatches.append(f"missing comparable bounds for {object_id}")
        else:
            try:
                if len(expected_bounds) != 6 or len(observed_bounds) != 6 or any(
                    abs(float(expected_value) * 0.001 - float(observed_value)) > 1.0e-6
                    for expected_value, observed_value in zip(expected_bounds, observed_bounds)
                ):
                    mismatches.append(f"runtime bounds differ for {object_id}")
            except (TypeError, ValueError):
                mismatches.append(f"invalid comparable bounds for {object_id}")
        if int(observed.get("shape_count", 0)) < 1:
            mismatches.append(f"runtime object {object_id} has no shape")
    if not expected_policy_fingerprint:
        mismatches.append("expected collision-scene policy fingerprint is missing")
    elif observed_policy_fingerprint != expected_policy_fingerprint:
        mismatches.append("runtime collision-scene policy fingerprint is missing or differs")
    if not readback_correlated:
        mismatches.append("scene readback is not correlated to this publication/request")
    if reported_status and reported_status != "Acknowledged":
        mismatches.append(f"native acknowledgement status was {reported_status}")
    return {
        "status": "Acknowledged" if not mismatches else "Mismatch",
        "trusted": not mismatches,
        "expected_object_ids": sorted(expected_by_id),
        "observed_object_ids": sorted(observed_by_id),
        "expected_policy_fingerprint": expected_policy_fingerprint or None,
        "observed_policy_fingerprint": observed_policy_fingerprint or None,
        "readback_correlated": bool(readback_correlated),
        "mismatches": mismatches,
        "attribution_allowed": not mismatches,
    }


def collision_scene_readback_trace(
    *,
    sync_result: Mapping[str, Any],
    collision_audit_result: Mapping[str, Any],
    task_statuses: Sequence[Mapping[str, Any]],
    acknowledgement: Mapping[str, Any],
) -> dict[str, Any]:
    """Explain the ordinary-audit versus later-task-status scene discrepancy."""

    audit_value = collision_audit_result.get("value") or {}
    exact = audit_value.get("runtime_acknowledgement") or {}
    later = []
    for status in task_statuses:
        if not status:
            continue
        later.append(
            {
                "request_id": status.get("request_id"),
                "validation_kind": status.get("validation_kind"),
                "phase": status.get("phase"),
                "sequence": status.get("sequence"),
                "validate_only": status.get("validate_only"),
                "world_object_count": status.get("world_object_count"),
                "world_object_ids": sorted(
                    str(record.get("id") or "")
                    for record in status.get("world_objects", ())
                    if isinstance(record, Mapping) and record.get("id")
                ),
                "channel": "/dentobot/task_joint_status",
            }
        )
    return {
        "exact_audit": {
            "sync_call_status": sync_result.get("status"),
            "acknowledgement_status": exact.get("status"),
            "world_object_count": exact.get("world_object_count"),
            "world_object_ids": exact.get("acknowledged_object_ids", []),
            "channel": "/dentobot/joint_command_status",
            "readback": "latest cached ordinary status after apply_joint_positions_si_to_motion_control",
            "request_correlation": False,
        },
        "later_guard_queries": later,
        "source_finding": [
            "The exact audit publishes the collision objects but defers the ordinary status-cache acknowledgement because that channel has no request correlation.",
            "The bounded diagnostic then configures one transient task session per candidate and issues a read-only static_state scene readback.",
            "The task status now echoes request_id, validation_kind, policy fingerprint, and exact native world IDs/poses/bounds.",
            "Only a matching correlated task-status readback may attribute the native static or transition result to the prepared scene.",
        ],
        "same_scene_identity_proven": bool(acknowledgement.get("trusted")),
        "native_attribution_allowed": bool(acknowledgement.get("attribution_allowed")),
    }


def contact_record(
    *,
    state_id: str,
    native_status: Mapping[str, Any] | None = None,
    historical: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize native contact telemetry and retain historical evidence separately."""

    status = dict(native_status or {})
    first = str(status.get("first_body") or "")
    second = str(status.get("second_body") or "")
    pair = [first, second] if first and second else None
    guide_contact = status.get("guide_clearance_warning_contact_position_base_m")
    nearest = {
        "first_base_m": status.get("nearest_point_first_base_m"),
        "second_base_m": status.get("nearest_point_second_base_m"),
    }
    target_pair = EXPECTED_TARGET_SEGMENT
    forbidden = bool(
        pair
        and any("pneumatic_spindle-Copy" in body for body in pair)
        and any("target_tooth" in body or target_pair in body for body in pair)
    )
    return {
        "schema_version": "1.0",
        "state_id": str(state_id),
        "native_status_available": bool(native_status),
        "native_pair": pair,
        "contact_class": (
            "FORBIDDEN_COLLISION"
            if forbidden
            else "GUIDE_WARNING"
            if status.get("guide_clearance_warning")
            else "AUTHORIZED_CONTACT"
            if status.get("exploratory_tool_contact_suppressed")
            else "NONE_OR_UNKNOWN"
        ),
        "native_contact_position_base_m": guide_contact,
        "native_nearest_points_base_m": nearest if any(nearest.values()) else None,
        "native_penetration_m": status.get(
            "guide_clearance_warning_contact_penetration_m"
        ),
        "native_depth": None,
        "native_depth_unknown_reason": (
            "TaskJointStatus exposes guard progress and contact penetration, but no "
            "separate native drilling-depth/contact-depth field."
        ),
        "native_clearance_m": status.get("minimum_world_distance_m"),
        "native_clearance_unknown_reason": (
            None
            if status.get("minimum_world_distance_m") is not None
            else "Native status did not expose a finite world-clearance metric."
        ),
        "contact_frame": "base_link" if native_status else None,
        "contact_length_unit": "metres" if native_status else None,
        "checked_samples": status.get("checked_samples") if native_status else None,
        "contact_count": None,
        "contact_count_unknown_reason": (
            "The guard status reports the first pair and bounded sample count, not "
            "an exhaustive contact list or truncation flag."
            if native_status
            else "No native contact status was available."
        ),
        "truncated": None,
        "truncation_unknown_reason": "Native contact-list truncation is not exposed.",
        "historical_r13": dict(historical) if historical is not None else None,
    }


def _call(label: str, function, *args, **kwargs) -> tuple[dict[str, Any], Any]:
    try:
        value = function(*args, **kwargs)
        return {"label": label, "status": "PASS", "value": _jsonable(value)}, value
    except Exception as exc:
        return {
            "label": label,
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }, None


def _node_ref(node) -> dict[str, Any] | None:
    if node is None:
        return None
    return {
        "id": str(node.GetID() or ""),
        "name": str(node.GetName() or ""),
        "class": str(node.GetClassName()),
    }


def _node_attributes(node) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        names = node.GetAttributeNames()
        for index in range(names.GetNumberOfValues()):
            name = str(names.GetValue(index))
            if name.startswith(("DENTOBOT.", "ROS2.")):
                values[name] = str(node.GetAttribute(name) or "")
    except Exception:
        pass
    return values


def _matrix_record(node) -> list[list[float]] | None:
    if node is None or not hasattr(node, "GetMatrixTransformToWorld"):
        return None
    try:
        import vtk

        matrix = vtk.vtkMatrix4x4()
        node.GetMatrixTransformToWorld(matrix)
        return [
            [float(matrix.GetElement(row, column)) for column in range(4)]
            for row in range(4)
        ]
    except Exception:
        return None


def _goal_robot_reference_nodes(robot, role: str) -> list[object]:
    if robot is None or not hasattr(robot, "GetNumberOfNodeReferences"):
        return []
    return [
        robot.GetNthNodeReference(role, index)
        for index in range(robot.GetNumberOfNodeReferences(role))
        if robot.GetNthNodeReference(role, index) is not None
    ]


def _goal_model_nodes(robot) -> list[object]:
    return _goal_robot_reference_nodes(robot, "goal_model")


def _goal_display_node_kind(name: str) -> str | None:
    lowered = str(name or "").lower()
    normalized = lowered.replace("_", "-")
    if "pneumatic-spindle-copy" in normalized:
        return "spindle"
    if (
        "burr-model-0-goal" in normalized
        or normalized.endswith("-burr")
        or normalized in {"burr", "burr-goal-transform"}
    ):
        return "burr"
    if "dentobot-drill-tcp" in normalized or "tool-tcp" in normalized:
        return "tcp"
    return None


def _refresh_goal_robot(bridge, fallback):
    try:
        return bridge.find_ros2_robot_by_name(bridge.ROS2_ROBOT_NAME) or fallback
    except Exception:
        return fallback


def _native_fk_world_rows(robot, positions_si, base_transform, bridge, link_name):
    """Compute one native KDL link pose without changing the robot state."""

    if robot is None or base_transform is None or positions_si is None:
        return None
    try:
        import vtk

        pose_base = vtk.vtkMatrix4x4()
        pose_base.Identity()
        if robot.ComputeKDLFK(
            bridge.visual_joint_si_vector(positions_si), pose_base, link_name
        ) is None:
            return None
        base_world = vtk.vtkMatrix4x4()
        if base_transform.GetMatrixTransformToWorld(base_world) is False:
            return None
        pose_world = vtk.vtkMatrix4x4()
        vtk.vtkMatrix4x4.Multiply4x4(base_world, pose_base, pose_world)
        return [
            [float(pose_world.GetElement(row, column)) for column in range(4)]
            for row in range(4)
        ]
    except Exception:
        return None


def _goal_robot_display_fk_evidence(robot, positions_si, base_transform, bridge) -> dict[str, Any]:
    """Compare real goal-model transforms; markers alone never satisfy this check."""

    displayed: dict[str, Any] = {}
    model_names: dict[str, str] = {}
    reference_catalog = []
    for role in ("goal_model", "goal_transform"):
        for model in _goal_robot_reference_nodes(robot, role):
            name = str(model.GetName() or "")
            matrix = _matrix_record(model)
            reference_catalog.append(
                {
                    "role": role,
                    "name": name,
                    "class": str(model.GetClassName() or "") if hasattr(model, "GetClassName") else "",
                    "matrix_available": matrix is not None,
                }
            )
            kind = _goal_display_node_kind(name)
            if kind is None or matrix is None:
                continue
            displayed.setdefault(kind, matrix)
            model_names.setdefault(kind, name)
    native = {
        key: _native_fk_world_rows(robot, positions_si, base_transform, bridge, link)
        for key, link in (
            ("tcp", bridge.ROS2_TOOL_TCP_LINK),
            ("spindle", "pneumatic_spindle-Copy"),
            ("burr", "burr"),
        )
    }
    return {
        "joint_state_si": dict(positions_si) if positions_si is not None else None,
        "displayed_model_names": model_names,
        "display_reference_catalog": reference_catalog,
        "native_fk_world_ras_mm": native,
        "tcp_spindle_comparison": compare_display_fk_transforms(
            displayed, native, keys=("tcp", "spindle")
        ),
        "burr_comparison": compare_display_fk_transforms(
            displayed, native, keys=("burr",)
        ),
        "tcp_marker_policy": (
            "marker may identify the native TCP location, but cannot substitute "
            "for an actual displayed TCP/link transform"
        ),
    }


def _style_goal_robot_for_closeup(robot) -> list[object]:
    """Colour display-only goal links; do not touch collision proxies or ACM."""

    selected = []
    for model in _goal_model_nodes(robot):
        display = model.GetDisplayNode()
        if display is None:
            continue
        kind = _goal_display_node_kind(model.GetName())
        if kind == "spindle":
            display.SetColor(1.0, 0.45, 0.0)
            display.SetOpacity(0.75)
            selected.append(model)
        elif kind == "burr":
            display.SetColor(1.0, 1.0, 0.0)
            display.SetOpacity(1.0)
            selected.append(model)
        elif kind == "tcp":
            display.SetColor(1.0, 0.1, 1.0)
            display.SetOpacity(1.0)
            selected.append(model)
    return selected


def scene_node_record(node) -> dict[str, Any]:
    """Capture identity, geometry counts, transforms, displays and provenance."""

    record = _node_ref(node) or {"id": "", "name": "", "class": ""}
    record["attributes"] = _node_attributes(node)
    parent = node.GetParentTransformNode() if hasattr(node, "GetParentTransformNode") else None
    record["parent"] = _node_ref(parent)
    display = node.GetDisplayNode() if hasattr(node, "GetDisplayNode") else None
    record["display"] = {
        "visibility": bool(display.GetVisibility()) if display else None,
        "visibility2D": bool(display.GetVisibility2D()) if display and hasattr(display, "GetVisibility2D") else None,
        "visibility3D": bool(display.GetVisibility3D()) if display and hasattr(display, "GetVisibility3D") else None,
    }
    matrix = _matrix_record(node)
    if matrix is not None:
        record["matrix_to_world_ras"] = matrix
    if node.IsA("vtkMRMLMarkupsNode"):
        points = []
        for index in range(node.GetNumberOfDefinedControlPoints()):
            point = [0.0, 0.0, 0.0]
            node.GetNthControlPointPositionWorld(index, point)
            points.append(
                {
                    "index": index,
                    "label": str(node.GetNthControlPointLabel(index) or ""),
                    "world_ras_mm": point,
                }
            )
        record["control_points"] = points
        record["locked"] = bool(node.GetLocked())
        record["selectable"] = bool(node.GetSelectable())
    if node.IsA("vtkMRMLModelNode"):
        polydata = node.GetPolyData()
        bounds = [0.0] * 6
        try:
            node.GetRASBounds(bounds)
        except Exception:
            bounds = None
        record["mesh"] = {
            "points": int(polydata.GetNumberOfPoints()) if polydata else 0,
            "cells": int(polydata.GetNumberOfCells()) if polydata else 0,
            "bounds_world_ras_mm": bounds,
        }
    if node.IsA("vtkMRMLScalarVolumeNode"):
        image = node.GetImageData()
        record["volume"] = {
            "dimensions": list(image.GetDimensions()) if image else [0, 0, 0],
            "spacing_mm": [float(value) for value in node.GetSpacing()],
            "ijk_to_ras": _matrix_record(node),
        }
    if node.IsA("vtkMRMLSegmentationNode"):
        segments = []
        try:
            import vtk

            ids = vtk.vtkStringArray()
            node.GetSegmentation().GetSegmentIDs(ids)
            for index in range(ids.GetNumberOfValues()):
                segment_id = ids.GetValue(index)
                segment = node.GetSegmentation().GetSegment(segment_id)
                segments.append(
                    {
                        "id": segment_id,
                        "name": str(segment.GetName() if segment else ""),
                        "visible": (
                            bool(node.GetDisplayNode().GetSegmentVisibility(segment_id))
                            if node.GetDisplayNode()
                            else None
                        ),
                    }
                )
        except Exception as exc:
            segments = [{"error": f"{type(exc).__name__}: {exc}"}]
        record["segments"] = segments
    return record


def _all_scene_records(slicer) -> list[dict[str, Any]]:
    return [
        scene_node_record(slicer.mrmlScene.GetNthNode(index))
        for index in range(slicer.mrmlScene.GetNumberOfNodes())
        if slicer.mrmlScene.GetNthNode(index) is not None
    ]


def _persistent_scene_fingerprint(slicer) -> str:
    records = []
    for record in _all_scene_records(slicer):
        attrs = record.get("attributes") or {}
        if record.get("class", "").startswith("vtkMRMLROS2"):
            continue
        if attrs.get("DENTOBOT.CollisionAuditCopy") == "true":
            continue
        if attrs.get("DENTOBOT.IntendedUse", "").startswith("DisplayOnly"):
            continue
        records.append(record)
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parameter_snapshot(parameter) -> dict[str, Any]:
    fields = (
        "caseName",
        "dentoCaseSchemaVersion",
        "targetToothSegmentId",
        "targetDockingYawConfirmed",
        "robotBaseMountLocked",
        "step6BasePlacementStatus",
        "step6BasePlacementSource",
        "step6BasePlacementRevision",
        "step6CaseJawPreparationMode",
        "step6PlanningContextImported",
        "step6ApproachStandoffMm",
        "step6TrajectoryCorridorRadiusMm",
        "step6ToolFrame",
        "step6TaskHomeJson",
        "step6ConfirmedTaskJson",
        "step6CollisionSceneAuditJson",
        "step6TrajectoryRegistryJson",
    )
    result: dict[str, Any] = {}
    for field in fields:
        value = getattr(parameter, field, None)
        if isinstance(value, str) and field.endswith("Json"):
            try:
                value = json.loads(value) if value else None
            except (TypeError, ValueError, json.JSONDecodeError):
                value = {"raw": value, "parse_error": True}
        result[field] = _jsonable(value)
    result["node_fields"] = {
        field: _node_ref(getattr(parameter, field, None))
        for field in (
            "inputVolume",
            "teethSegmentation",
            "targetToothBoundsRoi",
            "trajectoryLine",
            "draftTemplateSupportModel",
            "targetDockingReferencePlane",
            "targetDockingAssemblyModel",
            "templateInsertionDirection",
            "patientContactShellModel",
            "finalPrintableTemplateModel",
            "robotBaseTransform",
            "robotMountPlane",
            "robotForeheadProxyModel",
            "step6CaseJawLandmarks",
            "step6CaseJawTransform",
            "step6CaseJawGapLine",
            "step6OpenedLowerJawModel",
            "step6FixedUpperAnatomy",
            "step6MovingLowerAnatomy",
        )
    }
    return result


def _identity(path: Path, validate_case_bundle) -> dict[str, Any]:
    inspection = validate_case_bundle(path)
    return {
        "path": str(path),
        "sha256": file_sha256(path),
        "scene_sha256": inspection.scene_sha256,
        "manifest": _jsonable(inspection.manifest),
        "workflow": _jsonable(inspection.workflow),
        "robot_profile": _jsonable(inspection.robot_profile),
        "save_report": _jsonable(inspection.save_report),
    }


def _r13_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "available": False, "unknown_reason": "missing"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    keys = (
        "candidate_index",
        "planner_leg",
        "stage",
        "full_chain_candidate_status",
        "full_chain_failure_stage",
        "full_chain_first_invalid_index",
        "full_chain_first_invalid_stage_index",
        "first_invalid_joint_positions_si",
        "first_invalid_ras_mm",
        "guard_first_body",
        "guard_second_body",
        "guard_minimum_world_distance_m",
        "guard_nearest_point_first_base_m",
        "guard_nearest_point_second_base_m",
        "guideClearanceWarningCount",
        "guideClearanceWarningContactCount",
        "guideClearanceWarningPairs",
        "guideClearanceWarningContactPenetrationMm",
        "last_valid_joint_positions_si",
        "last_valid_waypoint_index",
        "message",
    )
    return {
        "path": str(path),
        "available": True,
        "sha256": file_sha256(path),
        "task": _jsonable(payload.get("task")),
        "motion": {
            "state": payload.get("motion", {}).get("state"),
            "candidate_records": [
                {key: _jsonable(candidate.get(key)) for key in keys}
                for candidate in payload.get("motion", {}).get("candidate_records", [])
            ],
        },
    }


def _selection(
    label: str,
    *,
    node=None,
    value: Any = None,
    rule: str,
    provenance: str,
    automatic: bool,
    confirmation: Any = None,
    warnings: Sequence[str] = (),
    downstream: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "label": label,
        "node": _node_ref(node),
        "value": _jsonable(value),
        "selection_rule": rule,
        "provenance": provenance,
        "automatic": bool(automatic),
        "confirmation": _jsonable(confirmation),
        "operator_confirmed_in_this_run": False,
        "operator_review_required": True,
        "warnings": list(warnings),
        "downstream_dependencies": list(downstream),
    }


def _workflow_step(number: str, title: str, selections: Sequence[Mapping[str, Any]], **details) -> dict[str, Any]:
    return {
        "workflow_order": number,
        "title": title,
        "automatic_selections": [dict(item) for item in selections],
        "operator_review": {
            "status": "PENDING",
            "acceptance_not_implied_by": [
                "execution approval",
                "generated confirmation flags",
                "machine PASS results",
            ],
        },
        **details,
    }


def _open_case(slicer, package: Path, process_events):
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    if widget is None or widget.logic is None:
        raise RuntimeError("DENTOWorkflow widget/logic is unavailable")
    apply_mode = getattr(widget, "_applyDENTOBOTGuiMode", None)
    if callable(apply_mode):
        apply_mode("legacy", persist=False)
    widget._openCaseBundle(str(package))
    process_events(1.0)
    parameter = widget._parameterNode
    if parameter is None:
        raise RuntimeError("case package did not restore a parameter node")
    return widget, parameter, widget.logic


def _process_events(slicer, seconds: float = 0.25) -> None:
    deadline = time.monotonic() + float(seconds)
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def _focus_bounds(nodes) -> tuple[list[float], float] | tuple[None, None]:
    bounds = [float("inf"), float("-inf")] * 3
    found = False
    for node in nodes:
        if node is None:
            continue
        values = [0.0] * 6
        try:
            node.GetRASBounds(values)
        except Exception:
            continue
        if not all(math.isfinite(float(value)) for value in values):
            continue
        found = True
        for axis in range(3):
            bounds[2 * axis] = min(bounds[2 * axis], values[2 * axis])
            bounds[2 * axis + 1] = max(bounds[2 * axis + 1], values[2 * axis + 1])
    if not found:
        return None, None
    span = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4])
    return bounds, span


def _annotate_capture(pixmap, label: str) -> None:
    """Add a non-authorizing review label to a raster capture only."""

    import qt

    painter = qt.QPainter(pixmap)
    painter.setRenderHint(qt.QPainter.Antialiasing, True)
    banner_height = min(66, max(48, int(pixmap.height() * 0.12)))
    painter.fillRect(
        qt.QRect(0, 0, pixmap.width(), banner_height),
        qt.QColor(20, 30, 45, 225),
    )
    font = qt.QFont()
    font.setBold(True)
    font.setPointSize(11)
    painter.setFont(font)
    painter.setPen(qt.QColor(255, 255, 255))
    painter.drawText(
        qt.QRect(14, 5, pixmap.width() - 28, banner_height - 10),
        qt.Qt.AlignLeft | qt.Qt.AlignVCenter | qt.Qt.TextWordWrap,
        str(label),
    )
    painter.end()


def _capture_view(
    slicer,
    path: Path,
    focus_nodes,
    *,
    label: str,
    camera_nodes=None,
) -> dict[str, Any]:
    """Capture one focused 3-D view and restore every changed display flag."""

    import vtk

    path.parent.mkdir(parents=True, exist_ok=True)
    focus_nodes = [node for node in focus_nodes if node is not None]
    camera_nodes = [node for node in (camera_nodes or focus_nodes) if node is not None]
    keep = {node.GetID() for node in focus_nodes}
    saved = []
    displayables = slicer.mrmlScene.GetNodes()
    for index in range(displayables.GetNumberOfItems()):
        node = displayables.GetItemAsObject(index)
        if node is None or not node.IsA("vtkMRMLDisplayableNode"):
            continue
        display = node.GetDisplayNode()
        if display is None:
            continue
        visibility3d = (
            int(display.GetVisibility3D())
            if hasattr(display, "GetVisibility3D")
            else None
        )
        segment_visibility = []
        is_focus = node.GetID() in keep
        if is_focus and node.IsA("vtkMRMLSegmentationNode"):
            try:
                segment_ids = vtk.vtkStringArray()
                node.GetSegmentation().GetSegmentIDs(segment_ids)
                representation_name = (
                    slicer.vtkSegmentationConverter
                    .GetSegmentationClosedSurfaceRepresentationName()
                )
                for segment_index in range(segment_ids.GetNumberOfValues()):
                    segment_id = segment_ids.GetValue(segment_index)
                    prior = bool(display.GetSegmentVisibility3D(segment_id))
                    segment_visibility.append((segment_id, prior))
                    segment = node.GetSegmentation().GetSegment(segment_id)
                    surface = (
                        segment.GetRepresentation(representation_name)
                        if segment is not None
                        else None
                    )
                    if surface is not None and surface.GetNumberOfPoints():
                        display.SetSegmentVisibility3D(segment_id, True)
            except Exception:
                # The top-level visibility is still useful when a particular
                # segmentation representation is unavailable.
                segment_visibility = []
        saved.append((display, int(display.GetVisibility()), visibility3d, segment_visibility))
        display.SetVisibility(1 if is_focus else 0)
        if hasattr(display, "SetVisibility3D"):
            display.SetVisibility3D(bool(is_focus))
    try:
        layout = slicer.app.layoutManager()
        layout.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView)
        host = slicer.util.mainWindow()
        if host is not None:
            host.show()
        _process_events(slicer, 0.4)
        view = layout.threeDWidget(0).threeDView()
        view.show()
        view.mrmlViewNode().SetAxisLabelsVisible(False)
        bounds, span = _focus_bounds(camera_nodes)
        if bounds is not None and span and span > 1.0e-6:
            center = [
                (bounds[2 * axis] + bounds[2 * axis + 1]) / 2.0
                for axis in range(3)
            ]
            camera = view.cameraNode().GetCamera()
            camera.SetFocalPoint(*center)
            camera.SetPosition(center[0] + span, center[1] - span, center[2] + span)
            camera.SetViewUp(0.0, 0.0, 1.0)
            camera.ParallelProjectionOn()
            camera.SetParallelScale(min(80.0, max(5.0, 0.65 * span)))
            reset_clipping = getattr(view, "resetCameraClippingRange", None)
            if callable(reset_clipping):
                reset_clipping()
            else:
                renderers = view.renderWindow().GetRenderers()
                renderer = renderers.GetFirstRenderer() if renderers else None
                if renderer is not None:
                    renderer.ResetCameraClippingRange()
        view.forceRender()
        slicer.util.forceRenderAllViews()
        _process_events(slicer, 0.4)
        render_window = view.renderWindow()
        render_window.Render()
        _process_events(slicer, 0.25)
        # Xvfb's VTK off-screen buffer can be a large uniform background; the
        # established project path captures the visible widget from the host.
        import qt

        view_size = view.size
        if callable(view_size):
            view_size = view_size()
        origin = view.mapTo(host, qt.QPoint(0, 0)) if host is not None else qt.QPoint(0, 0)
        pixmap = host.grab() if host is not None else None
        if pixmap is None or pixmap.isNull():
            raise RuntimeError(f"could not capture Slicer window with focused 3-D view: {path}")
        _annotate_capture(pixmap, label)
        if not pixmap.save(str(path)):
            raise RuntimeError(f"could not save Slicer window capture: {path}")
    finally:
        for display, visibility, visibility3d, segment_visibility in saved:
            display.SetVisibility(visibility)
            if visibility3d is not None and hasattr(display, "SetVisibility3D"):
                display.SetVisibility3D(bool(visibility3d))
            for segment_id, prior in segment_visibility:
                display.SetSegmentVisibility3D(segment_id, prior)
    size = path.stat().st_size if path.is_file() else 0
    return {
        "label": label,
        "path": str(path),
        "sha256": file_sha256(path) if size else None,
        "bytes": size,
        "nonblank_machine_check": size >= 1024,
        "framing": "Slicer window with focused 3-D view and raster review label; operator content review remains pending",
        "capture_method": "main_window_grab_with_review_label",
        "viewport_origin_in_window": [int(origin.x()), int(origin.y())],
        "viewport_size": [int(view_size.width()), int(view_size.height())],
    }


def _save_scene(slicer, path: Path, audit_mrb_runtime_separation) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    saved = bool(slicer.util.saveScene(str(path)))
    result = {"path": str(path), "save_returned": saved, "exists": path.is_file()}
    if path.is_file():
        result["sha256"] = file_sha256(path)
        result["bytes"] = path.stat().st_size
        result["runtime_separation"] = _jsonable(audit_mrb_runtime_separation(path))
    return result


def run_p1():
    import slicer

    root = Path(os.environ["DENTOBOT_RECOVERY_OUTPUT"])
    source = Path(os.environ.get("DENTOBOT_RECOVERY_SOURCE", ""))
    package = Path(os.environ["DENTOBOT_RECOVERY_PACKAGE"])
    r13 = Path(os.environ.get("DENTOBOT_RECOVERY_R13", ""))
    from DENTOCaseBundle import audit_mrb_runtime_separation, validate_case_bundle

    package_identity = _identity(package, validate_case_bundle)
    source_identity = (
        _identity(source, validate_case_bundle)
        if source.is_file()
        else {"path": str(source), "available": False, "unknown_reason": "missing"}
    )
    widget, parameter, logic = _open_case(slicer, package, lambda seconds=0.25: _process_events(slicer, seconds))

    registry_result, registry = _call(
        "case trajectory registry", logic.syncDentoCaseTrajectoryRegistry, parameter
    )
    foundation_result, foundation = _call(
        "Case Foundation eligibility", logic.evaluateCaseFoundationEligibility, parameter
    )
    eligibility_result, eligibility = _call(
        "PreparedBranch eligibility",
        logic.evaluatePreparedBranchEligibility,
        parameter,
        registry=registry,
    ) if registry is not None else ({"status": "SKIPPED", "label": "PreparedBranch eligibility"}, None)
    workflow_result, workflow_summary = _call(
        "case bundle workflow summary", logic.caseBundleWorkflowSummary, parameter
    )
    reviews_result, reviews = _call(
        "segmentation review records",
        logic.getSegmentationReviewRecords,
        parameter.teethSegmentation,
    ) if parameter.teethSegmentation else ({"status": "SKIPPED", "label": "segmentation review records"}, None)
    teeth_result, teeth = _call(
        "eligible target-tooth records",
        logic.getTargetToothRecords,
        parameter.teethSegmentation,
    ) if parameter.teethSegmentation else ({"status": "SKIPPED", "label": "eligible target-tooth records"}, None)
    target_result, target_record = _call(
        "selected target-tooth validation",
        logic.validateTargetTooth,
        parameter.teethSegmentation,
        str(parameter.targetToothSegmentId or ""),
    ) if parameter.teethSegmentation else ({"status": "SKIPPED", "label": "selected target-tooth validation"}, None)
    trajectory_result, trajectory_summary = _call(
        "Entry/Target trajectory summary", logic.getTrajectorySummary, parameter.trajectoryLine
    ) if parameter.trajectoryLine else ({"status": "SKIPPED", "label": "Entry/Target trajectory summary"}, None)
    assisted_nodes = [
        node
        for node in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
        if node.GetAttribute("DENTOBOT.MarkupsRole") == "AssistedTrajectoryEntries"
    ]
    assisted_result, assisted_summary = _call(
        "assisted Step-4A entry summary",
        logic.getAssistedTrajectoryEntrySummary,
        assisted_nodes[0],
    ) if assisted_nodes else ({"status": "SKIPPED", "label": "assisted Step-4A entry summary"}, None)
    guides_result, selected_guides = _call(
        "selected guide trajectories", logic.getSelectedTemplateGuideTrajectories
    )

    draft = parameter.draftTemplateSupportModel
    visible = parameter.visibleTemplateSupportModel
    docking = parameter.targetDockingAssemblyModel
    insertion = parameter.templateInsertionDirection
    shell = parameter.patientContactShellModel
    final_model = parameter.finalPrintableTemplateModel
    draft_result, draft_summary = _call("Step-4B draft support summary", logic.getDraftTemplateSupportModelSummary, draft) if draft else ({"status": "SKIPPED", "label": "Step-4B draft support summary"}, None)
    visible_result, visible_summary = _call("Step-4B visible support summary", logic.getVisibleTemplateSupportModelSummary, visible) if visible else ({"status": "SKIPPED", "label": "Step-4B visible support summary"}, None)
    docking_result, docking_summary = _call("Step-4C docking assembly summary", logic.getTargetDockingAssemblySummary, docking) if docking else ({"status": "SKIPPED", "label": "Step-4C docking assembly summary"}, None)
    insertion_result, insertion_summary = _call("Step-5B insertion direction summary", logic.getTemplateInsertionDirectionSummary, insertion) if insertion else ({"status": "SKIPPED", "label": "Step-5B insertion direction summary"}, None)
    shell_result, shell_summary = _call("Step-5C patient-contact shell summary", logic.getPatientContactShellSummary, shell) if shell else ({"status": "SKIPPED", "label": "Step-5C patient-contact shell summary"}, None)
    final_result, final_summary = _call("Step-5C final printable template summary", logic.getFinalPrintableTemplateSummary, final_model) if final_model else ({"status": "SKIPPED", "label": "Step-5C final printable template summary"}, None)

    final_shells = [
        node for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
        if node.GetAttribute("DENTOBOT.ModelRole") == "FinalizedTemplateShell"
    ]
    final_shell_result, final_shell_summary = _call(
        "Step-5C finalized shell summary",
        logic.getFinalizedTemplateShellSummary,
        final_shells[0],
    ) if final_shells else ({"status": "SKIPPED", "label": "Step-5C finalized shell summary"}, None)
    audit_result, collision_audit = _call(
        "saved collision-scene audit", logic.collisionSceneAuditRecord, parameter
    )
    package_freshness_result, package_freshness = _call(
        "Step-6 package freshness", logic.step6PlanningPackageFreshnessIssues, parameter
    )
    jaw_freshness_result, jaw_freshness = _call(
        "Step-6 jaw-opening freshness", logic.step6CaseJawOpeningFreshnessIssues, parameter
    )
    base_freshness_result, base_freshness = _call(
        "Step-6 base freshness", logic.step6BasePlacementFreshnessIssues, parameter
    )
    target_trajectory = trajectory_summary or {}
    endpoint_checks = {
        "target_segment_matches_frozen": str(parameter.targetToothSegmentId or "") == EXPECTED_TARGET_SEGMENT,
        "entry_matches_frozen": bool(target_trajectory.get("entryRas")) and all(
            abs(float(a) - float(b)) <= 1.0e-6
            for a, b in zip(target_trajectory.get("entryRas", ()), EXPECTED_ENTRY_RAS_MM)
        ),
        "target_matches_frozen": bool(target_trajectory.get("targetRas")) and all(
            abs(float(a) - float(b)) <= 1.0e-6
            for a, b in zip(target_trajectory.get("targetRas", ()), EXPECTED_TARGET_RAS_MM)
        ),
        "trajectory_length_mm": target_trajectory.get("lengthMm"),
        "frozen_depth_mm": EXPECTED_DEPTH_MM,
    }
    all_nodes = _all_scene_records(slicer)
    duplicate_groups: dict[str, list[str]] = {}
    for record in all_nodes:
        attrs = record.get("attributes") or {}
        key = "|".join(
            (
                record.get("class", ""),
                record.get("name", ""),
                attrs.get("DENTOBOT.ModelRole", ""),
                attrs.get("DENTOBOT.MarkupsRole", ""),
                attrs.get("DENTOBOT.TargetSegmentID", ""),
                attrs.get("DENTOBOT.OutgoingCollisionObjectId", ""),
            )
        )
        duplicate_groups.setdefault(key, []).append(record.get("id", ""))
    duplicates = {
        key: ids for key, ids in duplicate_groups.items() if key and len(ids) > 1
    }
    transforms = {
        field: scene_node_record(getattr(parameter, field, None))
        for field in (
            "robotBaseTransform",
            "robotMountPlane",
            "step6CaseJawTransform",
            "trajectoryLine",
            "templateInsertionDirection",
        )
        if getattr(parameter, field, None) is not None
    }
    p0_manifest = root.parent.parent / "c1-p0-20260914-r1" / "source_state_manifest.json"
    p0_state = json.loads(p0_manifest.read_text(encoding="utf-8")) if p0_manifest.is_file() else {}
    screenshots = []
    focus_context = [
        parameter.teethSegmentation,
        parameter.step6FixedUpperAnatomy,
        parameter.step6MovingLowerAnatomy,
        parameter.targetToothBoundsRoi,
        parameter.trajectoryLine,
        assisted_nodes[0] if assisted_nodes else None,
        parameter.finalPrintableTemplateModel,
        parameter.targetDockingAssemblyModel,
    ]
    focus_target = [
        parameter.teethSegmentation,
        parameter.targetToothBoundsRoi,
        parameter.trajectoryLine,
        assisted_nodes[0] if assisted_nodes else None,
        parameter.finalPrintableTemplateModel,
        parameter.targetDockingAssemblyModel,
    ]
    screenshots.append(_capture_view(
        slicer,
        root.parent / "screenshots" / "p1-context.png",
        focus_context,
        label="P1 | FDI 31 input context | saved anatomy + guide | review only",
        camera_nodes=focus_context,
    ))
    screenshots.append(_capture_view(
        slicer,
        root.parent / "screenshots" / "p1-target-guide-closeup.png",
        focus_target,
        label="P1 | FDI 31 Entry -> Target | guide relationship | review only",
        camera_nodes=[
            parameter.targetToothBoundsRoi,
            parameter.trajectoryLine,
            assisted_nodes[0] if assisted_nodes else None,
        ],
    ))
    scene = _save_scene(slicer, root.parent / "inspection-scene" / "fdi31-p1-scene.mrb", audit_mrb_runtime_separation)
    technical_errors = [
        result.get("error")
        for result in (
            registry_result,
            foundation_result,
            workflow_result,
            reviews_result,
            teeth_result,
            target_result,
            trajectory_result,
            draft_result,
            visible_result,
            docking_result,
            insertion_result,
            shell_result,
            final_result,
        )
        if result.get("status") == "ERROR"
    ]
    technical_pass = bool(
        scene.get("exists")
        and endpoint_checks["target_segment_matches_frozen"]
        and endpoint_checks["entry_matches_frozen"]
        and endpoint_checks["target_matches_frozen"]
        and not technical_errors
    )
    return {
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "phase": "P1",
        "status": "PASS" if technical_pass else "INCONCLUSIVE",
        "campaign_gate": "USER_REVIEW_REQUIRED",
        "operator_acceptance": "NOT_RECORDED",
        "package": package_identity,
        "immutable_source": source_identity,
        "retained_r13": _r13_summary(r13),
        "source_state_identity": {
            "p0_manifest": str(p0_manifest),
            "checkout_head": p0_state.get("checkout", {}).get("head"),
            "native_build_state": p0_state.get("native_build_state", {}),
            "expected_native_source_sha256": EXPECTED_NATIVE_SOURCE_SHA256,
            "expected_native_binary_sha256": EXPECTED_NATIVE_BINARY_SHA256,
        },
        "frames_and_units": {
            "case": "SlicerRAS/mm",
            "native_robot": "base_link/metres",
            "joints": "SI units; J1-J5 only; J6 fixed at zero",
        },
        "automatic_selections_in_workflow_order": [
            _workflow_step(
                "1",
                "Source, masks, jaw, Foundation and scene ownership",
                [
                    _selection("immutable source package", value=source_identity, rule="DENTOBOT_RECOVERY_SOURCE", provenance="saved frozen source", automatic=True, downstream=("scene audit",)),
                    _selection("diagnostic package", value=package_identity, rule="DENTOBOT_RECOVERY_PACKAGE", provenance="saved frozen r7 package", automatic=True, downstream=("steps 1-6 audit",)),
                    _selection("Case Foundation pose/base", node=parameter.robotBaseTransform, value=foundation, rule="restored parameter-node Case Foundation fields and existing eligibility API", provenance="saved package plus read-only eligibility", automatic=True, confirmation=getattr(parameter, "robotBaseMountLocked", None), downstream=("collision scene", "native FK")),
                ],
                source=source_identity,
                package=package_identity,
                foundation=foundation_result,
                parameter=_parameter_snapshot(parameter),
                scene_node_count=len(all_nodes),
                duplicates=duplicates,
                transforms=transforms,
                upper_lower_transform_rule="recorded from saved jaw/foundation attributes; no transform was regenerated",
            ),
            _workflow_step(
                "2",
                "Tooth/pulp semantics and target association",
                [
                    _selection("whole-tooth target segment", node=parameter.teethSegmentation, value={"segment_id": str(parameter.targetToothSegmentId or ""), "fdi": "FDI31", "record": target_record}, rule="getTargetToothRecords + validateTargetTooth", provenance="saved segmentation and spatial/source-hint semantic record", automatic=True, confirmation=getattr(parameter, "targetToothSegmentId", None), warnings=("Pulp association is recorded as semantic evidence; no new target was generated.",), downstream=("Entry/Target", "collision target object")),
                ],
                eligible_tooth_records=teeth_result,
                segmentation_review_records=reviews_result,
                selected_target=target_result,
                fallback_rules=[
                    "Whole-tooth records are fail-closed to VALID or MANUALLY_CONFIRMED.",
                    "FDI/spatial/source-hint association is evidence, not operator anatomical approval.",
                    "No missing pulp or target evidence was substituted during this audit.",
                ],
            ),
            _workflow_step(
                "3",
                "Step 4A Entry, Target, direction and depth",
                [
                    _selection("saved Entry/Target line", node=parameter.trajectoryLine, value=trajectory_summary, rule="restored parameter.trajectoryLine and getTrajectorySummary", provenance="saved r7 package", automatic=True, confirmation=getattr(parameter.trajectoryLine, "GetLocked", lambda: None)(), downstream=("support/guide/dock", "Step 6 task snapshot")),
                    _selection("assisted entry set", node=assisted_nodes[0] if assisted_nodes else None, value=assisted_summary, rule="existing AssistedTrajectoryEntries role; no generated entry fallback", provenance="saved package if present", automatic=True, confirmation=None, warnings=("Geometric Entry estimate is not anatomical approval.",), downstream=("support direction",)),
                ],
                trajectory=trajectory_result,
                assisted_entry=assisted_result,
                frozen_endpoint_checks=endpoint_checks,
                intended_endpoints={"entry_ras_mm": list(EXPECTED_ENTRY_RAS_MM), "target_ras_mm": list(EXPECTED_TARGET_RAS_MM), "depth_mm": EXPECTED_DEPTH_MM},
            ),
            _workflow_step(
                "4",
                "Supports, guides and docking",
                [
                    _selection("draft support", node=draft, value=draft_summary, rule="parameter.draftTemplateSupportModel", provenance="saved r7 package", automatic=True, confirmation=getattr(draft, "GetAttribute", lambda *_: None)("DENTOBOT.SelectionLocked") if draft else None, downstream=("visible support", "shell")),
                    _selection("visible support", node=visible, value=visible_summary, rule="parameter.visibleTemplateSupportModel", provenance="saved r7 package", automatic=True, confirmation=getattr(visible, "GetAttribute", lambda *_: None)("DENTOBOT.GeometryState") if visible else None, downstream=("insertion direction",)),
                    _selection("docking assembly", node=docking, value=docking_summary, rule="parameter.targetDockingAssemblyModel", provenance="saved r7 package", automatic=True, confirmation=getattr(parameter, "targetDockingYawConfirmed", None), warnings=("Guide bore and robot-dock bore are recorded as separate source roles/attributes.",), downstream=("Step 5", "collision payload")),
                ],
                selected_guides=guides_result,
                draft_support=draft_result,
                visible_support=visible_result,
                docking=docking_result,
            ),
            _workflow_step(
                "5",
                "Steps 5A-5C support extraction, blockout, shell and final geometry",
                [
                    _selection("insertion direction", node=insertion, value=insertion_summary, rule="parameter.templateInsertionDirection", provenance="saved r7 package", automatic=True, confirmation=None, downstream=("patient-contact shell",)),
                    _selection("patient-contact shell", node=shell, value=shell_summary, rule="parameter.patientContactShellModel", provenance="saved r7 package", automatic=True, confirmation=None, downstream=("final template",)),
                    _selection("final printable template", node=final_model, value=final_summary, rule="parameter.finalPrintableTemplateModel", provenance="saved r7 package", automatic=True, confirmation=None, warnings=("Valid STL/open boundary does not establish fit or operator acceptance.",), downstream=("Step 6 collision scene",)),
                    _selection("finalized shell", node=final_shells[0] if final_shells else None, value=final_shell_summary, rule="DENTOBOT.ModelRole=FinalizedTemplateShell", provenance="saved scene if present", automatic=True, confirmation=None, downstream=("final STL evidence",)),
                ],
                insertion_direction=insertion_result,
                patient_shell=shell_result,
                final_template=final_result,
                finalized_shell=final_shell_result,
            ),
            _workflow_step(
                "6",
                "Save/reopen and Step 6 identity",
                [
                    _selection("restored Step 6 package state", value=workflow_summary, rule="caseBundleWorkflowSummary after fresh _openCaseBundle", provenance="saved package plus read-only hydration", automatic=True, confirmation=parameter.step6PlanningContextImported, downstream=("P2 native scene audit",)),
                    _selection("collision payload", value=collision_audit, rule="saved collisionSceneAuditRecord; no native runtime in P1", provenance="saved package only", automatic=True, confirmation=None, warnings=("P1 does not claim native acknowledgement; P2 supplies the bounded runtime audit.",), downstream=("P2" ,)),
                ],
                workflow_summary=workflow_result,
                prepared_branch=eligibility_result,
                collision_audit=audit_result,
                freshness={"planning_package": package_freshness_result, "jaw": jaw_freshness_result, "base": base_freshness_result},
                native_acknowledged_contents=None,
                native_acknowledged_unknown_reason="P1 is a saved-scene audit; native ROS/MoveIt scene acknowledgement is deferred to P2.",
            ),
        ],
        "machine_checks": {
            "registry": registry_result,
            "foundation": foundation_result,
            "prepared_branch": eligibility_result,
            "endpoint_identity": endpoint_checks,
            "scene_save": scene,
            "technical_errors": technical_errors,
        },
        "object_manifest": {
            "schema_version": "1.0",
            "scene_fingerprint": _persistent_scene_fingerprint(slicer),
            "nodes": all_nodes,
            "duplicate_groups": duplicates,
        },
        "transform_manifest": {
            "schema_version": "1.0",
            "frames_and_units": {"world": "SlicerRAS/mm", "native": "base_link/metres"},
            "transforms": transforms,
        },
        "screenshots": screenshots,
        "inspection_scene": scene,
        "review_points": [
            "FDI31 tooth and pulp/semantic association",
            "saved Entry/Target and direction/depth",
            "support/guide/dock automatic selections and confirmations",
            "Step 5A-5C geometry, shell and final-template provenance",
            "upper/lower transform ownership and Step 6 collision payload identity",
        ],
        "forbidden_actions_observed": [
            "no generation or geometry correction",
            "no planner or full-flow execution",
            "no ROS/MoveIt runtime in P1",
            "no controller, spindle, robot motion or patient-facing action",
        ],
    }


def _home_positions(logic, parameter):
    try:
        record = logic.taskHomeRecord(parameter)
    except Exception:
        record = None
    if record is not None:
        return dict(zip(record.joint_names, record.joint_positions_si)), {
            "source": "saved_task_home",
            "record": _jsonable(record),
        }
    from DENTORobotPlacement import joint_positions_si_from_display

    positions = joint_positions_si_from_display(
        parameter.robotJoint1Deg,
        parameter.robotJoint2Mm,
        parameter.robotJoint3Deg,
        parameter.robotJoint4Mm,
        parameter.robotJoint5Deg,
        parameter.robotJoint6Deg,
    )
    positions.pop("pneumatic_spindle-Copy_Revolute-6", None)
    return positions, {
        "source": "saved_parameter_display_values",
        "record": None,
        "unknown_reason": "No parseable saved Task Home was available; display pose is setup-only evidence.",
    }


def _guard_outcome(status: Mapping[str, Any] | None, message: str = "") -> dict[str, Any]:
    if status is None:
        return {"available": False, "accepted": None, "reason": message or "native status unavailable"}
    return {
        "available": True,
        "accepted": status.get("accepted"),
        "reason": status.get("reason") or message,
        "request_id": status.get("request_id"),
        "validation_kind": status.get("validation_kind"),
        "phase": status.get("phase"),
        "sequence": status.get("sequence"),
        "validate_only": status.get("validate_only"),
        "requested_positions": status.get("requested_positions"),
        "first_body": status.get("first_body"),
        "second_body": status.get("second_body"),
        "starting_positions": status.get("starting_positions"),
        "evaluated_positions": status.get("evaluated_positions"),
        "evaluated_sample_index": status.get("evaluated_sample_index"),
        "interpolation_fraction": status.get("interpolation_fraction"),
        "total_sample_count": status.get("total_sample_count"),
        "checked_samples": status.get("checked_samples"),
        "corridor_progress": status.get("corridor_progress"),
        "minimum_world_distance_m": status.get("minimum_world_distance_m"),
        "guide_clearance_warning": status.get("guide_clearance_warning"),
        "exploratory_tool_contact_suppressed": status.get("exploratory_tool_contact_suppressed"),
    }


def _pose_metrics(rows, target_ras_mm, target_axis_ras):
    if not rows:
        return {"position_ras_mm": None, "axis_ras": None, "position_error_mm": None, "axis_error_deg": None}
    position = [float(rows[index][3]) for index in range(3)]
    axis = [float(rows[index][2]) for index in range(3)]
    norm = math.sqrt(sum(value * value for value in axis))
    if norm <= 1.0e-12:
        axis = None
        axis_error = None
    else:
        axis = [value / norm for value in axis]
        expected_norm = math.sqrt(sum(float(value) ** 2 for value in target_axis_ras))
        expected = [float(value) / expected_norm for value in target_axis_ras]
        cosine = max(-1.0, min(1.0, sum(a * b for a, b in zip(axis, expected))))
        axis_error = math.degrees(math.acos(cosine))
    position_error = math.sqrt(
        sum((position[index] - float(target_ras_mm[index])) ** 2 for index in range(3))
    )
    return {
        "position_ras_mm": position,
        "axis_ras": axis,
        "position_error_mm": position_error,
        "axis_error_deg": axis_error,
    }


def _joint_bounds(robot, positions, bridge):
    try:
        lower = list(robot.GetJointLowerPositionLimits())
        upper = list(robot.GetJointUpperPositionLimits())
        values = bridge.joint_si_vector(positions)
        within = len(lower) >= 5 and len(upper) >= 5 and all(
            float(lower[index]) <= float(values[index]) <= float(upper[index])
            for index in range(5)
        )
        return {
            "available": True,
            "within": within,
            "lower_si": lower[:5],
            "upper_si": upper[:5],
        }
    except Exception as exc:
        return {"available": False, "within": None, "unknown_reason": str(exc)}


def _native_context(bridge, base, home_positions, process_events):
    ready, message = bridge.ensure_slicer_ros2_runtime(require_stack=True)
    result = {"ready": bool(ready), "message": str(message or ""), "created_robot": False, "touched": False}
    if not ready:
        return result, None
    ros_logic, motion_logic, error = bridge.ensure_ros2_slicer_modules()
    if ros_logic is None or motion_logic is None:
        result.update({"ready": False, "message": error})
        return result, None
    ros_node = bridge.ensure_default_ros2_node_in_scene()
    if ros_node is None:
        result.update({"ready": False, "message": "ROS2 default node is unavailable."})
        return result, None
    robot = bridge.find_ros2_robot_by_name(bridge.ROS2_ROBOT_NAME)
    if robot is None:
        robot = ros_node.CreateAndAddRobotNode(
            bridge.ROS2_ROBOT_NAME,
            bridge.ROS2_URDF_PARAM_NODE,
            bridge.ROS2_URDF_PARAM_NAME,
            bridge.ROS2_FIXED_FRAME,
            bridge.ROS2_TF_PREFIX,
        )
        if robot is None:
            result.update({"ready": False, "message": "CreateAndAddRobotNode failed."})
            return result, None
        robot.SetAttribute(bridge.ROS2_ROBOT_NODE_ATTRIBUTE, bridge.ROS2_ROBOT_NAME)
        result["created_robot"] = True
    if not bridge.wait_for_robot_urdf(robot, process_events, timeout_sec=30.0):
        result.update({"ready": False, "message": "Timed out resolving the external URDF."})
        return result, None
    if not bridge.align_ros2_robot_to_base_transform(robot, base):
        result.update({"ready": False, "message": "Could not align native robot to the frozen base."})
        return result, None
    motion_parameter = motion_logic.getParameterNode()
    motion_parameter.robotNodeID = robot.GetID()
    motion_parameter.jointStateTopic = bridge.ROS2_JOINT_STATES_TOPIC
    motion_parameter.moveGroupExists = True
    motion_parameter.planningGroup = bridge.ROS2_PLANNING_GROUP
    if not motion_logic.SetupRobotForMotionControl(motion_parameter):
        result.update({"ready": False, "message": "SetupRobotForMotionControl failed."})
        return result, None
    if not bridge.align_ros2_goal_to_base_transform(robot, base):
        result.update({"ready": False, "message": "Could not align the native goal robot."})
        return result, None
    if not motion_logic.SetupMoveItPlanningGroup(robot, bridge.ROS2_PLANNING_GROUP):
        result.update({"ready": False, "message": "SetupMoveItPlanningGroup failed."})
        return result, None
    bridge._native_joint_positions = bridge.joint_si_vector(home_positions)
    bridge.mark_slicer_ros2_runtime_nodes_transient()
    result.update({"touched": True, "robot_id": robot.GetID(), "robot_name": robot.GetName()})
    return result, robot


def run_p2():
    import slicer
    import DENTOROS2Bridge as bridge
    from DENTORobotWorkflowFacade import DENTORobotWorkflowFacade
    from DENTOStep6State import parse_task_snapshot
    from DENTOCaseBundle import audit_mrb_runtime_separation, validate_case_bundle

    root = Path(os.environ["DENTOBOT_RECOVERY_OUTPUT"])
    package = Path(os.environ["DENTOBOT_RECOVERY_PACKAGE"])
    r13_path = Path(os.environ["DENTOBOT_RECOVERY_R13"])
    r13_payload = json.loads(r13_path.read_text(encoding="utf-8"))
    task = parse_task_snapshot(r13_payload["task"])
    widget, parameter, logic = _open_case(slicer, package, lambda seconds=0.25: _process_events(slicer, seconds))
    home_positions, home_identity = _home_positions(logic, parameter)
    facade = DENTORobotWorkflowFacade(logic, lambda: parameter, bridge=bridge)
    load_result = facade.loadRobot()
    local_robot_models = load_result.payload[1] if load_result.success and load_result.payload else []
    base = parameter.robotBaseTransform
    task_identity_checks = {
        "target_segment_matches": str(parameter.targetToothSegmentId or "") == task.target_segment_id == EXPECTED_TARGET_SEGMENT,
        "trajectory_matches": bool(parameter.trajectoryLine) and logic.step6TrajectoryRevision(parameter) == task.trajectory_revision,
        "base_matches": bool(base) and logic.robotBaseFingerprint(parameter) == task.base_fingerprint,
        "entry_matches": all(abs(float(a) - float(b)) <= 1.0e-6 for a, b in zip(task.entry_ras_mm, EXPECTED_ENTRY_RAS_MM)),
        "target_matches": all(abs(float(a) - float(b)) <= 1.0e-6 for a, b in zip(task.target_ras_mm, EXPECTED_TARGET_RAS_MM)),
    }
    identity_ok = all(task_identity_checks.values())
    native_info, robot = _native_context(
        bridge,
        base,
        home_positions,
        lambda seconds=0.25: _process_events(slicer, seconds),
    ) if identity_ok and load_result.success else (
        {"ready": False, "message": "Frozen task identity or local robot load failed.", "created_robot": False, "touched": False},
        None,
    )
    native_info["loaded_build_identity"] = corrected_native_build_identity()
    expected_scene_policy_fingerprint = (
        facade._strict_guard_policy_fingerprint() if native_info.get("ready") else ""
    )
    sync_result, obstacle_count = _call(
        "exact Step-6 collision payload sync",
        logic.syncStep6MoveItPlanningScene,
        parameter,
        expected_policy_fingerprint=expected_scene_policy_fingerprint,
        require_correlated_readback=True,
        defer_runtime_acknowledgement=True,
    ) if native_info.get("ready") else ({"label": "exact Step-6 collision payload sync", "status": "SKIPPED", "reason": native_info.get("message")}, None)
    collision_audit_result, collision_audit = _call(
        "native collision-scene audit record", logic.collisionSceneAuditRecord, parameter
    )
    audit_value = collision_audit_result.get("value") or {}
    reported_acknowledgement = audit_value.get("runtime_acknowledgement") or {}
    expected_scene_objects = audit_value.get("object_records") or ()
    observed_scene_objects = reported_acknowledgement.get("objects") or ()
    scene_acknowledgement = collision_scene_acknowledgement_evidence(
        expected_scene_objects,
        observed_scene_objects,
        expected_policy_fingerprint=expected_scene_policy_fingerprint or None,
        observed_policy_fingerprint=reported_acknowledgement.get(
            "collision_scene_policy_fingerprint"
        ),
        readback_correlated=reported_acknowledgement.get("readback_correlated") is True,
        reported_status=str(reported_acknowledgement.get("status") or ""),
    )
    scene_ready_for_attribution = scene_acknowledgement.get("trusted") is True
    # Setup/sync may annotate persistent source models; probe drift starts after that setup.
    runtime_scene_before = _persistent_scene_fingerprint(slicer)
    target_object_id = ""
    guidance_object_ids: tuple[str, ...] = ()
    proximity_object_ids: tuple[str, ...] = ()
    if native_info.get("ready"):
        target_object_id = str(logic.step6TargetCollisionObjectId(parameter) or "")
        guidance_object_ids = tuple(logic.step6GuidanceCollisionObjectIds(parameter))
        proximity_object_ids = tuple(logic.step6BurrProximityCollisionObjectIds(parameter))
    guard_setup_results = []
    handshake_state = None
    native_candidates = []
    contact_records = []
    r13_candidates = r13_payload.get("motion", {}).get("candidate_records", [])
    target_axis = (0.07504055058548376, -0.8719316812507053, -0.48384301069576907)
    if native_info.get("ready") and target_object_id:
        for candidate_index, candidate in enumerate(r13_candidates[:2]):
            positions = candidate.get("first_invalid_joint_positions_si") or candidate.get("last_valid_joint_positions_si")
            positions = {str(name): float(value) for name, value in (positions or {}).items() if str(name) in bridge.ROS2_JOINT_SI_ORDER}
            # Each candidate starts from the frozen/setup Home in a fresh guard session.
            bridge._native_joint_positions = bridge.joint_si_vector(home_positions)
            configured, configuration_message = bridge.configure_task_phase_guard(
                task_fingerprint=task.snapshot_fingerprint,
                target_object_id=target_object_id,
                clearance_exempt_object_ids=proximity_object_ids,
                base_transform=base,
                entry_ras_mm=task.entry_ras_mm,
                target_ras_mm=task.target_ras_mm,
                corridor_radius_mm=task.corridor_radius_mm,
                approach_standoff_mm=float(getattr(parameter, "step6ApproachStandoffMm", 0.0)),
                simulation_guide_clearance_object_ids=guidance_object_ids,
                collision_scene_policy_fingerprint=expected_scene_policy_fingerprint,
            )
            setup_status = bridge.last_task_joint_status()
            setup_status_dict = _jsonable(setup_status)
            setup_record = {
                "candidate_index": candidate_index,
                "configured": bool(configured),
                "message": configuration_message,
                "handshake_status": setup_status_dict,
            }
            guard_setup_results.append(setup_record)
            if candidate_index == 0:
                handshake_state = setup_status_dict
            scene_request_id = f"p2-candidate-{candidate_index}-scene-ack"
            scene_status = None
            if configured:
                scene_ack_ok, scene_ack_message = bridge.apply_task_phase_joint_positions(
                    home_positions,
                    task_fingerprint=task.snapshot_fingerprint,
                    phase="approach",
                    sequence=1,
                    validate_only=True,
                    validation_kind="static_state",
                    request_id=scene_request_id,
                    timeout_sec=6.0,
                )
                scene_status = _jsonable(bridge.last_task_joint_status())
                correlated = bool(
                    scene_status
                    and scene_status.get("request_id") == scene_request_id
                    and scene_status.get("validation_kind") == "static_state"
                )
                scene_acknowledgement = collision_scene_acknowledgement_evidence(
                    expected_scene_objects,
                    (scene_status or {}).get("world_objects") or (),
                    expected_policy_fingerprint=expected_scene_policy_fingerprint or None,
                    observed_policy_fingerprint=(scene_status or {}).get(
                        "collision_scene_policy_fingerprint"
                    ),
                    readback_correlated=correlated,
                    reported_status="Acknowledged" if correlated else "Mismatch",
                )
                scene_acknowledgement.update({
                    "source": "/dentobot/task_joint_status static_state scene acknowledgement",
                    "request_id": scene_request_id,
                    "static_predicate_accepted": (scene_status or {}).get("accepted"),
                    "static_predicate_message": scene_ack_message,
                    "scene_ack_command_ok": bool(scene_ack_ok),
                })
                scene_ready_for_attribution = scene_acknowledgement.get("trusted") is True
                setup_record.update({
                    "scene_ack_request_id": scene_request_id,
                    "scene_ack_status": scene_status,
                    "scene_ack_message": scene_ack_message,
                    "scene_acknowledgement": scene_acknowledgement,
                })
            else:
                scene_ready_for_attribution = False
                setup_record.update({
                    "scene_ack_request_id": scene_request_id,
                    "scene_ack_status": None,
                    "scene_ack_message": "Guard configuration was not acknowledged.",
                    "scene_acknowledgement": scene_acknowledgement,
                })
            if not scene_ready_for_attribution:
                contact_records.append(
                    contact_record(
                        state_id=f"p2-candidate-{candidate_index}-scene-untrusted",
                        historical={
                            "candidate_index": candidate_index,
                            "first_invalid_ras_mm": candidate.get("first_invalid_ras_mm"),
                            "scene_acknowledgement": scene_acknowledgement,
                        },
                    )
                )
                continue
            static_valid = static_message = static_authoritative = None
            fk_ok = fk_message = fk_base = None
            pose_ok = pose_message = pose_rows = None
            guard_ok = guard_message = None
            native_status = None
            static_status = None
            generic_static = None
            transition_start = None
            if configured and len(positions) == len(bridge.ROS2_JOINT_SI_ORDER):
                transition_start = dict(
                    zip(
                        bridge.ROS2_JOINT_SI_ORDER,
                        tuple(float(value) for value in bridge._native_joint_positions[:5]),
                    )
                )
                generic_static = bridge.check_moveit_static_joint_state(
                    positions, timeout_sec=2.0
                )
                static_request_id = f"p2-candidate-{candidate_index}-static"
                static_command_ok, static_command_message = bridge.apply_task_phase_joint_positions(
                    positions,
                    task_fingerprint=task.snapshot_fingerprint,
                    phase="drilling",
                    sequence=2,
                    validate_only=True,
                    validation_kind="static_state",
                    request_id=static_request_id,
                    timeout_sec=6.0,
                )
                static_status = _jsonable(bridge.last_task_joint_status())
                static_valid = (static_status or {}).get("accepted")
                static_message = static_command_message or (static_status or {}).get("reason")
                static_authoritative = bool(
                    static_status
                    and static_status.get("request_id") == static_request_id
                    and static_status.get("validation_kind") == "static_state"
                    and static_status.get("evaluated_sample_index") == 1
                    and static_status.get("total_sample_count") == 1
                )
                static_message = static_message or (
                    "Native phase-aware static-state query did not return a complete response."
                )
                fk_ok, fk_message, fk_base = bridge.compute_moveit_static_tcp_pose_base_mm(positions, timeout_sec=2.0)
                pose_ok, pose_message, pose_rows = bridge.compute_tcp_pose_world_ras_mm(positions, base_transform=base)
                transition_request_id = f"p2-candidate-{candidate_index}-transition"
                guard_ok, guard_message = bridge.apply_task_phase_joint_positions(
                    positions,
                    task_fingerprint=task.snapshot_fingerprint,
                    phase="drilling",
                    sequence=3,
                    validate_only=True,
                    validation_kind="transition",
                    request_id=transition_request_id,
                    timeout_sec=6.0,
                )
                native_status = _jsonable(bridge.last_task_joint_status())
            static_state = static_state_record(
                positions_si=positions or None,
                valid=static_valid,
                message=(
                    static_message
                    or "Static MoveIt state query was not run for this candidate."
                ),
                authoritative=static_authoritative,
                phase_aware=bool(static_authoritative),
                native_status=static_status,
                source="native phase-aware task-guard static_state",
            )
            static_state["generic_moveit_predicate"] = generic_static
            static_state["native_command_ok"] = static_command_ok if static_status is not None else None
            transition = phase_transition_record(
                transition_id=f"p2-candidate-{candidate_index}-home-to-target",
                start_positions_si=transition_start or (home_positions if configured else None),
                requested_positions_si=positions or None,
                phase="drilling",
                sequence=3,
                validate_only=True,
                native_status=native_status,
                joint_order=bridge.ROS2_JOINT_SI_ORDER,
            )
            metrics = _pose_metrics(pose_rows if pose_ok else None, task.target_ras_mm, target_axis)
            bounds = _joint_bounds(robot, positions, bridge) if robot is not None and positions else {"available": False, "within": None, "unknown_reason": "no candidate vector"}
            kinematic_valid = bool(
                positions
                and metrics.get("position_error_mm") is not None
                and metrics.get("axis_error_deg") is not None
                and metrics["position_error_mm"] <= POSITION_TOLERANCE_MM
                and metrics["axis_error_deg"] <= AXIS_TOLERANCE_DEG
                and bounds.get("within") is True
                and fk_ok
                and pose_ok
            )
            historical = {
                key: _jsonable(candidate.get(key))
                for key in (
                    "candidate_index",
                    "full_chain_failure_stage",
                    "full_chain_first_invalid_index",
                    "full_chain_first_invalid_stage_index",
                    "first_invalid_ras_mm",
                    "guard_first_body",
                    "guard_second_body",
                    "guard_nearest_point_first_base_m",
                    "guard_nearest_point_second_base_m",
                    "last_valid_joint_positions_si",
                    "last_valid_waypoint_index",
                )
            }
            state_id = f"p2-candidate-{candidate_index}-stage3-reconstructed"
            state = state_slot(
                state_id,
                positions_si=positions or None,
                stage=str(candidate.get("full_chain_failure_stage") or "stage3_drilling"),
                composed_index=candidate.get("full_chain_first_invalid_index"),
                stage_index=candidate.get("full_chain_first_invalid_stage_index"),
                edge={"method": "new bounded endpoint probe from setup Home/preflight", "exact_r13_edge": False},
                interpolation_fraction=None,
                fk={"moveit_base_position_mm": fk_base, "moveit_message": fk_message, "world_pose": pose_rows, "metrics": metrics, "kinematic_valid": kinematic_valid},
                axis_ras=metrics.get("axis_ras"),
                axial_depth_mm=EXPECTED_DEPTH_MM if metrics.get("position_error_mm") is not None else None,
                phase="drilling",
                guard_outcome=None,
                relation_to_rejected="requested endpoint state; separate static predicate and phase-transition result",
                unknown_reason="" if positions else "r13 candidate had no finite J1-J5 vector",
            )
            contact = contact_record(
                state_id=f"{state_id}-drilling-transition",
                native_status=native_status,
                historical=historical,
            )
            contact.update(
                {
                    "evidence_kind": "phase_transition",
                    "requested_state_id": state_id,
                    "transition_id": transition["transition_id"],
                    "target_static_attribution": "not permitted",
                }
            )
            native_candidates.append({
                "candidate_index": candidate_index,
                "r13": historical,
                "joints_si": positions or None,
                "static_validity": static_state,
                "moveit_fk": {"ok": fk_ok, "message": fk_message, "position_base_mm": fk_base},
                "world_fk": {"ok": pose_ok, "message": pose_message, "pose_world_ras": pose_rows, "metrics": metrics},
                "bounds": bounds,
                "kinematic_valid": kinematic_valid,
                "scene_acknowledgement": scene_acknowledgement,
                "static_status": static_status,
                "guard": {"kind": "phase_transition", "ok": guard_ok, "message": guard_message, "status": native_status},
                "requested_state": state,
                "transition": transition,
                "state": state,
                "contact": contact,
            })
            contact_records.append(contact)
    elif r13_candidates:
        for candidate_index, candidate in enumerate(r13_candidates[:2]):
            contact_records.append(
                contact_record(
                    state_id=f"p2-candidate-{candidate_index}-native-unavailable",
                    historical={
                        "candidate_index": candidate_index,
                        "first_invalid_ras_mm": candidate.get("first_invalid_ras_mm"),
                        "guard_first_body": candidate.get("guard_first_body"),
                        "guard_second_body": candidate.get("guard_second_body"),
                        "guard_nearest_point_first_base_m": candidate.get("guard_nearest_point_first_base_m"),
                        "guard_nearest_point_second_base_m": candidate.get("guard_nearest_point_second_base_m"),
                    },
                )
            )
    runtime_scene_after = _persistent_scene_fingerprint(slicer)
    scene_changed = runtime_scene_before != runtime_scene_after
    first_rejected = next((item for item in native_candidates if item.get("guard", {}).get("ok") is False), None)
    kinematic = next((item for item in native_candidates if item.get("kinematic_valid")), None)
    task_statuses = [
        entry.get("handshake_status")
        for entry in guard_setup_results
        if entry.get("handshake_status")
    ] + [
        entry.get("scene_ack_status")
        for entry in guard_setup_results
        if entry.get("scene_ack_status")
    ] + [
        item.get("static_status")
        for item in native_candidates
        if item.get("static_status")
    ] + [
        item.get("guard", {}).get("status")
        for item in native_candidates
        if item.get("guard", {}).get("status")
    ]
    scene_readback_trace = collision_scene_readback_trace(
        sync_result=sync_result,
        collision_audit_result=collision_audit_result,
        task_statuses=task_statuses,
        acknowledgement=scene_acknowledgement,
    )
    accepted_setup = handshake_state if handshake_state and handshake_state.get("accepted") else None
    last_guard_accepted = state_slot(
        "last_guard_accepted",
        positions_si=home_positions if accepted_setup else None,
        stage="setup_handshake" if accepted_setup else None,
        composed_index=None,
        stage_index=None,
        edge={"method": "native sequence-zero setup handshake", "preceding_rejected_sample": False} if accepted_setup else None,
        interpolation_fraction=None,
        fk=None,
        axis_ras=None,
        axial_depth_mm=None,
        phase="approach" if accepted_setup else None,
        guard_outcome=_guard_outcome(accepted_setup, native_info.get("message")) if accepted_setup else None,
        relation_to_rejected="setup handshake only; not the preceding accepted state of the retained r13 rejection" if accepted_setup else None,
        unknown_reason=None if accepted_setup else "native setup handshake was not observed as accepted",
    )
    last_housing_clear = (
        dict(last_guard_accepted, name="last_housing_clear", relation_to_rejected="setup handshake without native guide warning; not a r13 path sample")
        if accepted_setup and not accepted_setup.get("guide_clearance_warning")
        else state_slot("last_housing_clear", unknown_reason="No native accepted state without a guide warning was observed.")
    )
    if first_rejected is not None:
        rejected_transition = first_rejected["transition"]
        first_guard_rejected = {
            "name": "first_guard_rejected",
            "available": False,
            "joints_si": None,
            "phase": rejected_transition.get("phase"),
            "guard_outcome": rejected_transition.get("result"),
            "transition": rejected_transition,
            "requested_state": rejected_transition.get("requested_state"),
            "evaluated_or_rejected_sample": rejected_transition.get(
                "evaluated_or_rejected_sample"
            ),
            "relation_to_rejected": (
                "native rejection belongs to the Home-to-requested-endpoint transition; "
                "the separately recorded static Target predicate is not this result"
            ),
            "unknown_reason": rejected_transition.get(
                "evaluated_or_rejected_sample", {}
            ).get("unknown_reason"),
        }
    else:
        first_guard_rejected = state_slot(
            "first_guard_rejected",
            unknown_reason=(
                "No native drilling rejection was observed in this bounded reconstruction."
                if native_info.get("ready")
                else "Native runtime/contact status unavailable; retained r13 rejection is historical only."
            ),
        )
    target_state = kinematic["state"] if kinematic else (
        native_candidates[0]["state"] if native_candidates else state_slot(
            "target_state",
            unknown_reason="No finite native FK state was reconstructed.",
        )
    )
    target_state = dict(target_state, name="target_state")
    last_kinematic = dict(kinematic["state"], name="last_kinematically_valid") if kinematic else state_slot(
        "last_kinematically_valid",
        unknown_reason="No finite candidate passed the unchanged position/axis/tolerance/bounds reconstruction.",
    )
    historical_last_valid = [
        {
            "candidate_index": candidate.get("candidate_index"),
            "last_valid_joint_positions_si": candidate.get("last_valid_joint_positions_si"),
            "first_invalid_joint_positions_si": candidate.get("first_invalid_joint_positions_si"),
            "equality_caveat": "The retained r13 last_valid vector equals the rejected endpoint; it is not used as a preceding accepted state.",
        }
        for candidate in r13_candidates[:2]
    ]
    # A native probe may have added the exact target marker/collision highlight.
    historical_candidate = r13_candidates[0] if r13_candidates else {}
    historical_pair = []
    if historical_candidate.get("guard_first_body") and historical_candidate.get("guard_second_body"):
        historical_pair.append([
            historical_candidate["guard_first_body"],
            historical_candidate["guard_second_body"],
        ])
    collision_display_source = "none"
    goal_display_nodes = []
    display_fk_evidence = {
        "available": False,
        "unknown_reason": "No native goal robot was available for transform comparison.",
        "tcp_marker_policy": "marker-only evidence is not sufficient",
    }
    if native_candidates:
        first = native_candidates[0]
        display_ok, display_message = bridge.show_goal_robot_joint_positions(first.get("joints_si") or {})
        if display_ok:
            display_robot = _refresh_goal_robot(bridge, robot)
            goal_display_nodes = _style_goal_robot_for_closeup(display_robot)
            display_fk_evidence = _goal_robot_display_fk_evidence(
                display_robot,
                first.get("joints_si"),
                base,
                bridge,
            )
        pair = []
        status = first.get("guard", {}).get("status") or {}
        if status.get("first_body") and status.get("second_body"):
            pair.append([status["first_body"], status["second_body"]])
            collision_display_source = "native_guard_status"
        elif first.get("r13", {}).get("guard_first_body") and first.get("r13", {}).get("guard_second_body"):
            pair.append([first["r13"]["guard_first_body"], first["r13"]["guard_second_body"]])
            collision_display_source = "retained_r13_historical_pair"
        boundary_ok, boundary_message = bridge.show_motion_diagnostic_evidence(
            first_invalid_ras_mm=(first.get("r13", {}).get("first_invalid_ras_mm") or list(task.target_ras_mm)),
            collision_pairs=pair,
        )
    else:
        display_ok = None
        display_message = native_info.get("message")
        if historical_candidate:
            boundary_ok, boundary_message = bridge.show_motion_diagnostic_evidence(
                first_invalid_ras_mm=(historical_candidate.get("first_invalid_ras_mm") or list(task.target_ras_mm)),
                collision_pairs=historical_pair,
            )
            collision_display_source = "retained_r13_historical_pair" if historical_pair else "none"
        else:
            boundary_ok = None
            boundary_message = native_info.get("message")
    diagnostic_markers = [
        node
        for node in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
        if node.GetAttribute("DENTOBOT.MotionDiagnosticBoundary") == "true"
    ]
    audit_copies = [
        node
        for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
        if node.GetAttribute("DENTOBOT.CollisionAuditCopy") == "true"
    ]
    target_collision_nodes = []
    for node in audit_copies:
        if str(node.GetAttribute("DENTOBOT.OutgoingCollisionObjectId") or "") != target_object_id:
            continue
        display = node.GetDisplayNode()
        if display is not None:
            display.SetColor(0.1, 0.9, 0.2)
            display.SetOpacity(0.45)
        target_collision_nodes.append(node)
    diagnostic_source = "native_guard_probe" if native_candidates else "retained_r13_display_only"
    p2_context_nodes = [
        parameter.teethSegmentation,
        parameter.targetToothBoundsRoi,
        parameter.trajectoryLine,
        parameter.finalPrintableTemplateModel,
        parameter.targetDockingAssemblyModel,
    ] + diagnostic_markers + list(local_robot_models)
    screenshots = []
    screenshots.append(_capture_view(
        slicer,
        root.parent / "screenshots" / "p2-context.png",
        p2_context_nodes,
        label="P2 | native diagnostic context | display-only reconstruction | review only",
        camera_nodes=p2_context_nodes,
    ))
    if native_candidates or historical_candidate:
        screenshots.append(_capture_view(
            slicer,
            root.parent / "screenshots" / "p2-target-state.png",
            [
                parameter.teethSegmentation,
                parameter.targetToothBoundsRoi,
                parameter.trajectoryLine,
                parameter.finalPrintableTemplateModel,
            ] + diagnostic_markers + list(local_robot_models),
            label="P2 | retained rejected-state target | goal robot is display-only",
            camera_nodes=[parameter.targetToothBoundsRoi, parameter.trajectoryLine] + diagnostic_markers,
        ))
        screenshots.append(_capture_view(
            slicer,
            root.parent / "screenshots" / "p2-first-rejected-close-up.png",
            [
                parameter.teethSegmentation,
                parameter.finalPrintableTemplateModel,
                parameter.targetDockingAssemblyModel,
                parameter.trajectoryLine,
            ] + diagnostic_markers + list(local_robot_models),
            label="P2 | first rejected state | collision result is separately recorded",
            camera_nodes=[parameter.targetToothBoundsRoi, parameter.trajectoryLine] + diagnostic_markers,
        ))
        screenshots.append(_capture_view(
            slicer,
            root.parent / "screenshots" / "p2-visible-vs-collision-payload.png",
            [
                parameter.teethSegmentation,
                parameter.finalPrintableTemplateModel,
                parameter.trajectoryLine,
            ] + diagnostic_markers + audit_copies,
            label="P2 | displayed surfaces vs collision-audit meshes | red/cyan are display-only",
            camera_nodes=[parameter.targetToothBoundsRoi, parameter.trajectoryLine] + diagnostic_markers + audit_copies,
        ))
        closeup_nodes = target_collision_nodes + goal_display_nodes
        if closeup_nodes:
            screenshots.append(_capture_view(
                slicer,
                root.parent / "screenshots" / "p2-fdi31-burr-spindle-close-up.png",
                closeup_nodes,
                label=(
                    "P2 | FDI31 target collision mesh + burr + spindle | "
                    "display-only | surrounding anatomy hidden for display only | review only"
                ),
                camera_nodes=closeup_nodes,
            ))
    bridge.mark_slicer_ros2_runtime_nodes_transient()
    scene = _save_scene(slicer, root.parent / "inspection-scene" / "fdi31-p2-rejected-state.mrb", audit_mrb_runtime_separation)
    state_identity = {
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "phase": "P2",
        "task": _jsonable(task),
        "task_identity_checks": task_identity_checks,
        "package_sha256": file_sha256(package),
        "package_scene_sha256": validate_case_bundle(package).scene_sha256,
        "base_fingerprint": logic.robotBaseFingerprint(parameter) if base else None,
        "trajectory_revision": logic.step6TrajectoryRevision(parameter) if parameter.trajectoryLine else None,
        "robot_profile_fingerprint": logic.robotProfileFingerprint(),
        "tool_frame": task.tool_frame,
        "policy": {
            "tool_provenance": task.tool_provenance,
            "position_tolerance_mm": POSITION_TOLERANCE_MM,
            "axis_tolerance_deg": AXIS_TOLERANCE_DEG,
            "planning_joints": list(bridge.ROS2_JOINT_SI_ORDER),
            "spindle": "external; not a planning DOF; J6 fixed at zero",
            "strict_guard_policy_fingerprint": expected_scene_policy_fingerprint or None,
        },
        "native_build_identity": {
            "frozen_baseline_source_sha256": EXPECTED_NATIVE_SOURCE_SHA256,
            "frozen_baseline_binary_sha256": EXPECTED_NATIVE_BINARY_SHA256,
            "corrected_expected_source_sha256": CORRECTED_NATIVE_SOURCE_SHA256,
            "corrected_expected_binary_sha256": CORRECTED_NATIVE_BINARY_SHA256,
            "loaded": native_info.get("loaded_build_identity"),
            "identity_source": "P0 frozen source_state_manifest plus independent source/install-binary hashes from the running container",
        },
        "home": home_identity,
        "native_runtime": native_info,
        "native_scene": {
            "target_object_id": target_object_id or None,
            "guidance_object_ids": list(guidance_object_ids),
            "burr_proximity_object_ids": list(proximity_object_ids),
            "obstacle_count": obstacle_count,
            "ready_for_native_attribution": scene_ready_for_attribution,
            "sync": sync_result,
            "audit": collision_audit_result,
            "acknowledgement_contract": scene_acknowledgement,
            "readback_trace": scene_readback_trace,
        },
        "scene_fingerprint_before_probe": runtime_scene_before,
        "scene_fingerprint_after_probe": runtime_scene_after,
        "scene_changed_during_probe": scene_changed,
        "scene_change_unknown_reason": None if not scene_changed else "Persistent-scene digest changed during runtime; P2 is inconclusive until the delta is reviewed.",
        "display_evidence": {
            "source": diagnostic_source,
            "collision_pair_display_source": collision_display_source,
            "goal_robot": {"ok": display_ok, "message": display_message},
            "goal_robot_fk": display_fk_evidence,
            "close_up_contents": (
                "FDI31 collision-audit mesh, burr goal mesh and pneumatic spindle goal mesh; "
                "surrounding anatomy hidden by display visibility only"
            ),
            "boundary": {"ok": boundary_ok, "message": boundary_message},
            "first_invalid_marker_present": bool(diagnostic_markers),
            "collision_audit_copy_count": len(audit_copies),
        },
        "inspection_scene": scene,
    }
    atomic_json_write(root.parent / "state_identity.json", state_identity)
    atomic_json_write(root.parent / "contact_records.json", {"schema_version": "1.0", "run_id": RUN_ID, "phase": "P2", "records": contact_records})
    native_sufficient = bool(
        native_info.get("ready")
        and identity_ok
        and native_candidates
        and any(item.get("guard", {}).get("status") for item in native_candidates)
        and any(
            item.get("static_validity", {}).get("phase_aware") is True
            and item.get("static_validity", {}).get("native", {}).get(
                "validation_kind"
            ) == "static_state"
            for item in native_candidates
        )
        and native_info.get("loaded_build_identity", {}).get(
            "matches_corrected_build"
        ) is True
        and first_rejected is not None
        and scene_acknowledgement.get("trusted") is True
        and display_fk_evidence.get("tcp_spindle_comparison", {}).get("match") is True
        and display_fk_evidence.get("burr_comparison", {}).get("match") is True
        and not scene_changed
        and scene.get("exists")
    )
    status = "PASS" if native_sufficient else "INCONCLUSIVE"
    result = {
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "phase": "P2",
        "status": status,
        "campaign_gate": "USER_REVIEW_REQUIRED",
        "operator_acceptance": "NOT_RECORDED",
        "package": {"path": str(package), "sha256": file_sha256(package)},
        "r13": _r13_summary(r13_path),
        "task": _jsonable(task),
        "task_identity_checks": task_identity_checks,
        "states": {
            "last_kinematically_valid": last_kinematic,
            "last_guard_accepted": last_guard_accepted,
            "last_housing_clear": last_housing_clear,
            "first_guard_rejected": first_guard_rejected,
            "target_state": target_state,
        },
        "historical_last_valid_comparison": historical_last_valid,
        "bounded_reconstruction": {
            "candidate_count": len(native_candidates),
            "r13_path_reconstructed_exactly": False,
            "method": "saved r13 candidate vectors, a separate generic static predicate, and validate_only phased transition probes from setup Home",
            "static_state_and_transition_separate": True,
            "interpolation_fraction": None,
            "onset": None,
            "onset_unknown_reason": "No saved preceding accepted edge and no exact r13 waypoint path; screenshots cannot establish onset. P4 remains required for insertion/path evidence.",
            "guard_setup": guard_setup_results,
            "candidates": native_candidates,
        },
        "phase_aware_static_interface_proposal": phase_aware_static_interface_proposal(),
        "contact_records": {"path": str(root.parent / "contact_records.json"), "count": len(contact_records)},
        "state_identity": {"path": str(root.parent / "state_identity.json"), "scene_fingerprint_before_probe": runtime_scene_before, "scene_fingerprint_after_probe": runtime_scene_after},
        "screenshots": screenshots,
        "inspection_scene": scene,
        "machine_checks": {
            "local_robot_load": _jsonable(load_result),
            "native_context": native_info,
            "identity": task_identity_checks,
            "scene_changed_during_probe": scene_changed,
            "native_candidate_count": len(native_candidates),
            "native_probe_skipped_untrusted_scene": bool(
                native_info.get("ready")
                and target_object_id
                and not scene_ready_for_attribution
            ),
            "scene_acknowledgement_trusted": scene_acknowledgement.get("trusted"),
            "display_fk_trusted": display_fk_evidence.get("tcp_spindle_comparison", {}).get("match") is True
            and display_fk_evidence.get("burr_comparison", {}).get("match") is True,
            "native_sufficient_for_trust": native_sufficient,
        },
        "evidence_boundaries": [
            "Generated confirmation flags, native/test PASS, and execution approval are not input or geometry acceptance.",
            "A native body pair is preserved as reported; nearest points, contact count and depth remain null where not exposed.",
            "The retained r13 last_valid vector is not promoted to a preceding accepted state.",
            "The requested endpoint, generic static validity and Home-to-endpoint transition are separate records; transition rejection is not a Target static verdict.",
            "Scene IDs, poses, policy fingerprint and request correlation are required before new native collision results are attributable; later task-status object counts do not repair an unacknowledged audit.",
            "A saved TCP marker is display context only; actual goal-model TCP/spindle FK comparison is required and missing comparisons remain unknown.",
            "This is a bounded offline diagnostic reconstruction, not a full workflow, approach, insertion, repeat, playback, or clinical acceptance.",
        ],
        "forbidden_actions_observed": [
            "no planner or Stage-1/Stage-2/full-flow invocation",
            "no raw /dentobot/slicer_joint_positions publisher or heartbeat",
            "no controller connection, ExecuteTrajectory, powered spindle or robot motion",
            "no P3/P4 execution",
        ],
    }
    try:
        if native_info.get("created_robot"):
            disconnected, disconnect_message = bridge.disconnect_dentobot_motion_control(local_robot_models)
        else:
            disconnected, disconnect_message = False, "No diagnostic-created native robot was removed."
    except Exception as exc:
        disconnected, disconnect_message = False, f"cleanup error: {type(exc).__name__}: {exc}"
    finally:
        if native_info.get("touched"):
            bridge.shutdown_slicer_adapter()
    result["cleanup"] = {
        "diagnostic_created_robot": bool(native_info.get("created_robot")),
        "disconnect_attempted": bool(native_info.get("created_robot")),
        "disconnect_ok": disconnected,
        "message": disconnect_message,
        "operator_owned_session_preserved": not bool(native_info.get("created_robot")),
    }
    return result


def run():
    phase = phase_guard(os.environ.get("DENTOBOT_RECOVERY_PHASE", ""))
    return run_p1() if phase == "p1_scene_audit" else run_p2()


def main() -> int:
    phase = os.environ.get("DENTOBOT_RECOVERY_PHASE", "")
    output = Path(os.environ.get("DENTOBOT_RECOVERY_OUTPUT", "/tmp/dentobot-recovery.json"))
    try:
        report = run()
        atomic_json_write(output, report)
        print("DENTOBOT_FDI31_RECOVERY " + json.dumps(_jsonable(report), sort_keys=True), flush=True)
        return 0 if report.get("status") == "PASS" else 1
    except Exception as exc:
        failure = {
            "schema_version": "1.0",
            "run_id": RUN_ID,
            "phase": phase,
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        atomic_json_write(output, failure)
        print("DENTOBOT_FDI31_RECOVERY_FAILED " + json.dumps(failure, sort_keys=True), flush=True)
        return 1


if __name__ == "__main__":
    import slicer

    exit_code = main()
    # This is the only exit path.  It prevents the runner from falling through
    # into the DENTOWorkflow module's ordinary tests/planner code.
    slicer.util.exit(exit_code)
