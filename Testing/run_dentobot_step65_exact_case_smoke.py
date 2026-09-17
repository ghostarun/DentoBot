"""Explicit saved-case simulation check, with opt-in historical x4 diagnosis.

This test restores the operator's x4 case, reconstructs only transient ROS 2
state, and exercises planning plus guarded preview.  It never exposes or calls
hardware execution.
"""

from __future__ import annotations

import json
import hashlib
import math
import os
import re
import sys
import time
import traceback
from uuid import uuid4
from pathlib import Path

import slicer
import vtk

EXPLICIT_CASE = os.environ.get("DENTOBOT_EXACT_CASE", "")
if not EXPLICIT_CASE and os.environ.get("DENTOBOT_ENABLE_HISTORICAL_X4_DIAGNOSTIC") != "1":
    raise RuntimeError(
        "Retired pre-surgery x4 fixture: select a reviewed clean case for acceptance. "
        "Historical diagnosis requires DENTOBOT_ENABLE_HISTORICAL_X4_DIAGNOSTIC=1."
    )

ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
MODULE = ROOT / "DENTOWorkflow"
TESTING = ROOT / "Testing"
for path in (HELPERS, MODULE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
if str(TESTING) not in sys.path:
    sys.path.insert(0, str(TESTING))

import DENTOROS2Bridge as bridge  # noqa: E402
from DENTOCaseBundle import CASE_BUNDLE_SCHEMA_VERSION, validate_case_bundle  # noqa: E402
from DENTOStep6State import (  # noqa: E402
    DENTOCASE_STATE_SCHEMA_VERSION,
    ROBOT_ENVIRONMENT_SCHEMA_VERSION,
    SIMULATION_TOOL_PROVENANCE,
    SPINDLE_JOINT_NAME,
    TRAJECTORY_REGISTRY_SCHEMA_VERSION,
    build_task_snapshot,
    fingerprint,
    motion_diagnostic_plan_selection,
    validate_simulation_target,
)
from DENTOTemplateGeometry import model_polydata_in_world  # noqa: E402
from run_dentobot_fdi31_recovery_diagnostic import (  # noqa: E402
    _capture_view,
    collision_scene_acknowledgement_evidence,
    corrected_native_build_identity,
)


if EXPLICIT_CASE and any(os.environ.get(name, "") == "1" for name in (
    "DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE",
    "DENTOBOT_ENABLE_HISTORICAL_ANATOMY_REVIEW",
    "DENTOBOT_AUDIT_ACTUAL_CONTACT_ONLY",
    "DENTOBOT_PLAN_ONLY",
    "DENTOBOT_GOAL1_ONLY",
    "DENTOBOT_FOCUSED_STAGE3_DIAG",
)):
    raise RuntimeError("Explicit full-case run cannot use historical overrides or partial-run modes.")

PACKAGE = Path(EXPLICIT_CASE or (
    "/workspace/data/Slicer_Saved/SampleStudy1/"
    "dentobot-case-step6x4.dentocase"
))
EXPECTED_TASK = "39201d8f79a4a9ebee2290dfe7f2f37415123187b8b654aee038dba27584c27c"
PREVIEW_TIMEOUT_SEC = float(os.environ.get("DENTOBOT_PREVIEW_TIMEOUT_SEC", "240"))
BASE_LOCAL_Z_OFFSET_MM = float(
    os.environ.get("DENTOBOT_BASE_LOCAL_Z_OFFSET_MM", "0")
)
EXPECTED_FDI = str(os.environ.get("DENTOBOT_EXPECTED_FDI", "")).strip()
P3_REVALIDATION_INPUT = str(
    os.environ.get("DENTOBOT_P3_REVALIDATION_INPUT", "")
).strip()
P4_INSERTION_INPUT = str(
    os.environ.get("DENTOBOT_P4_INSERTION_INPUT", "")
).strip()
P5_APPROACH_INPUT = str(
    os.environ.get("DENTOBOT_P5_APPROACH_INPUT", "")
).strip()
INSERTION_ONLY = bool(P4_INSERTION_INPUT)
APPROACH_ONLY = bool(P5_APPROACH_INPUT)
ENDPOINT_ONLY = (
    not INSERTION_ONLY
    and not APPROACH_ONLY
    and (
        os.environ.get("DENTOBOT_ENDPOINT_ONLY", "") == "1"
        or bool(P3_REVALIDATION_INPUT)
    )
)
OUTPUT_CASE = str(os.environ.get("DENTOBOT_OUTPUT_CASE", "")).strip()
REOPEN_SAVED_CASE = os.environ.get("DENTOBOT_REOPEN_SAVED_CASE", "") == "1"
LOCK_SELECTED_ROUTE = os.environ.get("DENTOBOT_LOCK_SELECTED_ROUTE", "") == "1"
DIAGNOSTIC_OUTPUT = str(
    os.environ.get("DENTOBOT_DIAGNOSTIC_OUTPUT", "/tmp/dentobot-exact-case-diagnostic.json")
).strip()
if REOPEN_SAVED_CASE and not OUTPUT_CASE:
    raise RuntimeError("DENTOBOT_REOPEN_SAVED_CASE=1 requires DENTOBOT_OUTPUT_CASE.")
if ENDPOINT_ONLY and not EXPLICIT_CASE:
    raise RuntimeError("DENTOBOT_ENDPOINT_ONLY=1 requires DENTOBOT_EXACT_CASE.")
if INSERTION_ONLY and not EXPLICIT_CASE:
    raise RuntimeError("DENTOBOT_P4_INSERTION_INPUT requires DENTOBOT_EXACT_CASE.")
if APPROACH_ONLY and not EXPLICIT_CASE:
    raise RuntimeError("DENTOBOT_P5_APPROACH_INPUT requires DENTOBOT_EXACT_CASE.")
if sum(bool(value) for value in (
    P3_REVALIDATION_INPUT,
    P4_INSERTION_INPUT,
    P5_APPROACH_INPUT,
)) > 1:
    raise RuntimeError("P3 static revalidation, P4 insertion, and P5 approach modes are mutually exclusive.")


def process_events(seconds: float = 0.25) -> None:
    deadline = time.monotonic() + float(seconds)
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        ros_logic = slicer.util.getModuleLogic("ROS2")
        if ros_logic is not None:
            ros_logic.Spin()
        time.sleep(0.01)


def wait_until(predicate, timeout_sec: float):
    deadline = time.monotonic() + float(timeout_sec)
    while time.monotonic() < deadline:
        process_events(0.05)
        result = predicate()
        if result:
            return result
    return None


def require_success(result, stage: str):
    if not result.success:
        details = json.dumps(result.details, sort_keys=True, default=str)
        raise RuntimeError(f"{stage}: {result.message}; details={details}")
    return result


P3_MAX_IK_SOLVES = 128
P3_HALTON_BASES = (2, 3, 5, 7, 11)
P3_REVOLUTE_DEDUP_RAD = 1.0e-4
P3_PRISMATIC_DEDUP_M = 1.0e-5
P3_REVALIDATION_SHA256 = (
    "8853f5208a87368d2611fd9c0a9737fe6b73b4da43de6851f4a428adee3f734c"
)
P3_REVALIDATION_MODE = "p3_endpoint_only_r4"
P3_R4_CASE_SUFFIX = "/c1-gatea-fdi31-20260915-r4/FDI31-step5c.dentocase"
P3_R4_CASE_SHA256 = "6235772e2d14d74b5417d42ed8a5e0cc160df82c77efd3014f589dd264113d83"
# collision_guard serializes status doubles with std::setprecision(12).  This
# is an attribution tolerance for that lossy status echo only, not a task or
# collision tolerance.
P3_STATUS_VECTOR_REL_TOL = 1.0e-12
P3_STATUS_VECTOR_ABS_TOL = 5.0e-13
P4_INPUT_SHA256 = "ec6ad4febcf202de3469303f53ceb4d8056f14d2d6e03272a467ba5938fce362"
P4_MAX_REPRESENTATIVES = 8
P4_MAX_IK_SOLVES = 1024
P4_MAX_AXIAL_STEP_MM = 0.25
P4_MAX_MIDPOINT_REFINEMENTS = 3
P5_INPUT_SHA256 = "3cc1759d1dc5042748d729d5e2a1ae784a94a60d33cb7c8350695b321492bc72"
P5_MAX_P4_WITNESSES = 1
P5_STAGE1_PLANNING_ATTEMPTS = 1
P5_STAGE1_ALLOWED_PLANNING_TIME_SEC = 5.0
P5_MONITORED_START_TIMEOUT_SEC = 1.0


def _halton_value(index: int, base: int) -> float:
    value = 0.0
    denominator = 1.0
    while index:
        denominator *= base
        index, remainder = divmod(index, base)
        value += remainder / denominator
    return value


def _p3_runtime_joint_ranges(robot_node) -> tuple[dict[str, object], ...]:
    names = tuple(str(value) for value in robot_node.GetJoints())
    lower = tuple(float(value) for value in robot_node.GetJointLowerPositionLimits())
    upper = tuple(float(value) for value in robot_node.GetJointUpperPositionLimits())
    types = tuple(str(value) for value in robot_node.GetJointTypes())
    expected_names = set(bridge.ROS2_JOINT_SI_ORDER) | {SPINDLE_JOINT_NAME}
    if (
        len(names) != len(lower)
        or len(names) != len(upper)
        or len(names) != len(types)
        or len(set(names)) != len(names)
        or set(names) != expected_names
    ):
        raise RuntimeError("P3 active joint API is incomplete, duplicated, or has an unexpected joint")
    native_ranges = dict(zip(names, zip(lower, upper, types)))
    expected_types = {
        "link-1_Revolute-1": "revolute",
        "link-2_Slider-2": "prismatic",
        "link-3_Revolute-3": "revolute",
        "link-4_Slider-4": "prismatic",
        "link-5_Revolute-5": "continuous",
    }
    ranges = []
    for name in bridge.ROS2_JOINT_SI_ORDER:
        minimum, maximum, joint_type = native_ranges[name]
        if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum >= maximum:
            raise RuntimeError(f"P3 active joint range is invalid for {name}")
        if joint_type != expected_types[name]:
            raise RuntimeError(f"P3 active joint type is invalid for {name}")
        ranges.append({"name": name, "lower": minimum, "upper": maximum, "type": joint_type})
    return tuple(ranges)


def _p3_positions_match(
    left: dict[str, float], right: dict[str, float], ranges: tuple[dict[str, object], ...]
) -> bool:
    for item in ranges:
        name = str(item["name"])
        joint_type = str(item["type"])
        threshold = P3_PRISMATIC_DEDUP_M if joint_type == "prismatic" else P3_REVOLUTE_DEDUP_RAD
        delta = abs(float(left[name]) - float(right[name]))
        if joint_type == "continuous":
            delta = abs((float(left[name]) - float(right[name]) + math.pi) % (2.0 * math.pi) - math.pi)
        if delta > threshold:
            return False
    return True


def _p3_normalized_margin(
    positions: dict[str, float], ranges: tuple[dict[str, object], ...]
) -> float:
    return min(
        min(float(positions[str(item["name"])]) - float(item["lower"]), float(item["upper"]) - float(positions[str(item["name"])]))
        / (float(item["upper"]) - float(item["lower"]))
        for item in ranges
    )


def _p3_jsonable(value, *, depth: int = 0):
    """Keep native status evidence JSON-safe without inventing unknown values."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if depth > 12:
        return "<depth-limit>"
    if isinstance(value, dict):
        return {
            str(key): _p3_jsonable(item, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_p3_jsonable(item, depth=depth + 1) for item in value]
    fields = getattr(value, "__dataclass_fields__", None)
    if fields:
        return {
            str(name): _p3_jsonable(getattr(value, name), depth=depth + 1)
            for name in fields
        }
    return str(value)


def _p3_finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _p3_canonical_solution(value):
    if not isinstance(value, dict) or set(value) != set(bridge.ROS2_JOINT_SI_ORDER):
        return None
    if any(isinstance(item, bool) for item in value.values()):
        return None
    try:
        return bridge.canonicalize_planning_joint_positions(value)
    except (KeyError, TypeError, ValueError):
        return None


def _p3_exact_vector(value, expected) -> bool:
    if (
        not isinstance(value, (list, tuple))
        or not isinstance(expected, (list, tuple))
        or len(value) != len(expected)
    ):
        return False
    if any(isinstance(item, bool) for item in (*value, *expected)):
        return False
    try:
        values = [float(item) for item in value]
        expected_values = [float(item) for item in expected]
    except (TypeError, ValueError):
        return False
    return all(
        math.isfinite(item)
        and math.isfinite(target)
        and math.isclose(
            item,
            target,
            rel_tol=P3_STATUS_VECTOR_REL_TOL,
            abs_tol=P3_STATUS_VECTOR_ABS_TOL,
        )
        for item, target in zip(values, expected_values)
    )


def _p3_exact_integer(value, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == int(expected)


def _p3_positions_within_ranges(
    positions: dict[str, float], ranges: tuple[dict[str, object], ...]
) -> bool:
    return all(
        str(item["name"]) in positions
        and math.isfinite(float(positions[str(item["name"])]))
        and float(item["lower"]) <= float(positions[str(item["name"])]) <= float(item["upper"])
        for item in ranges
    )


def _p3_policy_context(facade) -> dict[str, str]:
    expected = ""
    try:
        expected = str(facade._strict_guard_policy_fingerprint() or "")
    except (AttributeError, TypeError, ValueError):
        pass
    configured = ""
    guard_session_id = ""
    try:
        config = json.loads(str(getattr(bridge, "_last_task_config_json", "") or ""))
        configured = str(config.get("collision_scene_policy_fingerprint") or "")
        guard_session_id = str(config.get("guard_session_id") or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return {
        "expected": expected,
        "configured": configured,
        "active": expected if expected == configured else "",
        "guard_session_id": guard_session_id,
    }


def _p3_scene_context(
    logic, parameter_node, policy_context, *, allow_deferred_static_ack: bool = False
):
    audit = None
    error = ""
    try:
        audit = logic.collisionSceneAuditRecord(parameter_node)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        error = f"saved collision-scene audit is invalid: {exc}"
    deferred_static_ack = bool(
        audit is not None
        and str(getattr(audit, "status", "") or "")
        == "RuntimeAcknowledgementDeferred"
        and str(getattr(audit, "runtime_acknowledgement", {}).get("status") or "")
        == "Deferred"
    )
    if audit is None:
        error = error or "saved collision-scene audit is unavailable"
    elif (
        str(getattr(audit, "status", "") or "") != "Acknowledged"
        and not (allow_deferred_static_ack and deferred_static_ack)
    ):
        error = "saved collision-scene audit is not acknowledged"
    elif (
        str(getattr(audit, "runtime_acknowledgement", {}).get("status") or "")
        != "Acknowledged"
        and not (allow_deferred_static_ack and deferred_static_ack)
    ):
        error = "saved collision-scene runtime acknowledgement is unavailable"
    expected_objects = tuple(audit.object_records) if audit is not None else ()
    return {
        "expected_objects": expected_objects,
        "audit_status": str(getattr(audit, "status", "") or ""),
        "audit_fingerprint": str(getattr(audit, "audit_fingerprint", "") or ""),
        "error": error,
        "deferred_static_ack": deferred_static_ack,
        "policy": dict(policy_context),
    }


def _p3_connect_static_runtime(facade, logic, parameter_node) -> dict[str, object]:
    """Initialize only the simulated guard/FK dependencies, never a joint stream."""

    local_models = list(logic.robotModelNodes())
    robot_node, error = bridge.connect_dentobot_motion_control(
        parameter_node.robotBaseTransform,
        hide_mrml_robot=bool(local_models),
        mrml_robot_models=local_models,
        open_motion_module=False,
        start_stack_if_needed=False,
        start_joint_command_stream=False,
    )
    if error or robot_node is None:
        raise RuntimeError(error or "P3 static runtime could not create the simulated ROS robot")
    try:
        policy_fingerprint = str(facade._strict_guard_policy_fingerprint() or "")
        if not policy_fingerprint:
            raise RuntimeError("P3 static runtime has no active collision-scene policy identity")
        # Reuse the existing deferred acknowledgement route: the first
        # correlated static_state response, not a raw joint command, proves
        # the published scene below.
        object_count = int(
            logic.syncStep6MoveItPlanningScene(
                parameter_node,
                expected_policy_fingerprint=policy_fingerprint,
                defer_runtime_acknowledgement=True,
            )
        )
        timer = getattr(bridge, "_slicer_joint_command_timer", None)
        if timer is not None and timer.isActive():
            raise RuntimeError("P3 static runtime unexpectedly started the raw joint command stream")
        return {
            "mode": "simulation_static_guard_only",
            "raw_joint_command_stream_started": False,
            "raw_joint_command_stream_active": False,
            "collision_scene_object_count": object_count,
            "collision_scene_acknowledgement": "deferred to correlated static_state responses",
        }
    except Exception:
        bridge.disconnect_dentobot_motion_control(local_models)
        raise


def _p3_static_state_query(
    positions: dict[str, float],
    *,
    snapshot,
    sequence: int,
    request_id: str,
    scene_context: dict[str, object],
    phase: str = "drilling",
) -> dict[str, object]:
    """Issue one read-only native static query and fail closed on weak telemetry."""

    requested = bridge.joint_si_vector(positions)
    request = {
        "request_id": str(request_id),
        "validation_kind": "static_state",
        "phase": str(phase),
        "sequence": int(sequence),
        "validate_only": True,
        "task_fingerprint": str(snapshot.snapshot_fingerprint),
        "requested_positions": list(requested),
    }
    command_ok = False
    command_message = ""
    try:
        command_ok, command_message = bridge.apply_task_phase_joint_positions(
            positions,
            task_fingerprint=snapshot.snapshot_fingerprint,
            phase=str(phase),
            sequence=int(sequence),
            validate_only=True,
            validation_kind="static_state",
            request_id=str(request_id),
            timeout_sec=6.0,
        )
    except Exception as exc:
        command_message = f"native static query failed: {type(exc).__name__}: {exc}"
    try:
        status = bridge.last_task_joint_status()
    except Exception as exc:
        status = None
        command_message = command_message or (
            f"native static status read failed: {type(exc).__name__}: {exc}"
        )
    response = _p3_jsonable(status)
    reasons = []
    if not isinstance(response, dict):
        reasons.append("missing or malformed native TaskJointStatus response")
        response = None
    else:
        if response.get("request_id") != request_id:
            reasons.append("static response request identity is missing or mismatched")
        if response.get("validation_kind") != "static_state":
            reasons.append("static response validation kind is missing or mismatched")
        if response.get("phase") != str(phase):
            reasons.append("static response phase is missing or mismatched")
        if response.get("validate_only") is not True:
            reasons.append("static response is not explicitly validate-only")
        if not _p3_exact_integer(response.get("sequence"), sequence):
            reasons.append("static response sequence is missing or mismatched")
        if response.get("task_fingerprint") != snapshot.snapshot_fingerprint:
            reasons.append("static response task identity is missing or mismatched")
        expected_guard_session = str(
            scene_context["policy"].get("guard_session_id") or ""
        )
        if not expected_guard_session:
            reasons.append("active static guard session identity is missing")
        elif response.get("guard_session_id") != expected_guard_session:
            reasons.append("static response guard-session identity is missing or mismatched")
        if not isinstance(response.get("accepted"), bool):
            reasons.append("static response acceptance is missing or malformed")
        if not _p3_exact_vector(response.get("requested_positions"), requested):
            reasons.append("static response requested J1-J5 vector is missing or mismatched")
        if not _p3_exact_vector(response.get("starting_positions"), requested):
            reasons.append("static response starting J1-J5 vector is missing or mismatched")
        if not _p3_exact_vector(response.get("evaluated_positions"), requested):
            reasons.append("static response evaluated J1-J5 vector is missing or mismatched")
        if not _p3_exact_integer(response.get("evaluated_sample_index"), 1):
            reasons.append("static response evaluated sample index is not one")
        if not _p3_exact_integer(response.get("total_sample_count"), 1):
            reasons.append("static response sample count is not one")
        if not _p3_exact_integer(response.get("checked_samples"), 1):
            reasons.append("static response checked-sample count is not one")
        expected_policy = str(scene_context["policy"].get("active") or "")
        if not expected_policy:
            reasons.append("active collision-scene policy identity is missing or inconsistent")
        if response.get("collision_scene_policy_fingerprint") != expected_policy:
            reasons.append("static response policy fingerprint is missing or mismatched")
    observed_objects = (
        response.get("world_objects")
        if isinstance(response, dict) and isinstance(response.get("world_objects"), list)
        else ()
    )
    expected_policy = str(scene_context["policy"].get("active") or "")
    try:
        scene_ack = collision_scene_acknowledgement_evidence(
            scene_context["expected_objects"],
            observed_objects,
            expected_policy_fingerprint=expected_policy or None,
            observed_policy_fingerprint=(response or {}).get(
                "collision_scene_policy_fingerprint"
            ),
            readback_correlated=not reasons,
            reported_status=(
                ""
                if scene_context.get("deferred_static_ack")
                else str(scene_context.get("audit_status") or "")
            ),
        )
    except (TypeError, ValueError, KeyError) as exc:
        scene_ack = {
            "status": "Mismatch",
            "trusted": False,
            "attribution_allowed": False,
            "mismatches": [f"scene acknowledgement could not be evaluated: {exc}"],
        }
    if scene_context.get("error"):
        scene_ack = dict(scene_ack)
        scene_ack["trusted"] = False
        scene_ack["attribution_allowed"] = False
        scene_ack.setdefault("mismatches", []).append(str(scene_context["error"]))
    trustworthy = not reasons and scene_ack.get("trusted") is True
    reported_accepted = (
        response.get("accepted") if isinstance(response, dict) else None
    )
    classification = (
        "ACCEPTED"
        if trustworthy and reported_accepted is True
        else "REJECTED"
        if trustworthy and reported_accepted is False
        else "INCONCLUSIVE"
    )
    return {
        "accepted": reported_accepted if trustworthy else None,
        "reported_accepted": reported_accepted,
        "trustworthy_authoritative": trustworthy,
        "classification": classification,
        "message": str(command_message or (response or {}).get("reason") or ""),
        "evidence": {
            "request": request,
            "command_ok": bool(command_ok),
            "command_message": str(command_message or ""),
            "response": response,
            "scene_acknowledgement": scene_ack,
            "policy_identity": {
                "expected": expected_policy,
                "configured": scene_context["policy"].get("configured"),
                "reported": (response or {}).get(
                    "collision_scene_policy_fingerprint"
                ),
                "guard_session_id": scene_context["policy"].get(
                    "guard_session_id"
                ),
            },
            "corridor": {
                key: (response or {}).get(key)
                for key in (
                    "corridor_ok",
                    "corridor_progress",
                    "corridor_distance_m",
                    "minimum_world_distance_m",
                    "minimum_self_distance_m",
                )
            },
            "contacts": {
                key: (response or {}).get(key)
                for key in (
                    "first_body",
                    "second_body",
                    "nearest_point_first_base_m",
                    "nearest_point_second_base_m",
                )
            },
            "warnings": {
                key: (response or {}).get(key)
                for key in (
                    "guide_clearance_warning",
                    "guide_clearance_warning_sample_count",
                    "minimum_guide_clearance_warning_m",
                    "guide_clearance_warning_robot_link",
                    "guide_clearance_warning_object_id",
                    "guide_warning_kind",
                    "guide_clearance_warning_contact_penetration_m",
                    "guide_clearance_warning_contact_sample_count",
                    "guide_clearance_warning_contact_position_base_m",
                )
            },
            "trustworthy_authoritative": trustworthy,
            "inconclusive_reasons": list(reasons)
            + list(scene_ack.get("mismatches") or ())
            if not trustworthy
            else [],
        },
    }


def _p3_generic_static_diagnostic(positions):
    try:
        valid, message, authoritative = bridge.check_moveit_static_joint_state(positions)
        return {
            "valid": bool(valid) if authoritative else None,
            "reported_valid": bool(valid),
            "authoritative": bool(authoritative),
            "message": str(message or ""),
            "error": "",
        }
    except Exception as exc:
        return {
            "valid": None,
            "reported_valid": None,
            "authoritative": False,
            "message": "",
            "error": f"generic MoveIt static diagnostic failed: {type(exc).__name__}: {exc}",
        }


def _p3_native_fk_evidence(positions, *, base_transform) -> dict[str, object]:
    """Capture explicit-state FK without showing or applying the candidate."""

    try:
        moveit_ok, moveit_message, moveit_base_mm = (
            bridge.compute_moveit_static_tcp_pose_base_mm(positions, timeout_sec=2.0)
        )
    except Exception as exc:
        moveit_ok, moveit_message, moveit_base_mm = (
            False,
            f"MoveIt static FK failed: {type(exc).__name__}: {exc}",
            None,
        )
    try:
        world_ok, world_message, world_ras = bridge.compute_tcp_pose_world_ras_mm(
            positions,
            base_transform=base_transform,
        )
    except Exception as exc:
        world_ok, world_message, world_ras = (
            False,
            f"world-RAS FK failed: {type(exc).__name__}: {exc}",
            None,
        )
    return {
        "moveit_static_ok": bool(moveit_ok),
        "moveit_static_message": str(moveit_message or ""),
        "moveit_tcp_base_mm": _p3_jsonable(moveit_base_mm),
        "world_ras_ok": bool(world_ok),
        "world_ras_message": str(world_message or ""),
        "world_ras_pose_mm": _p3_jsonable(world_ras),
    }


def _p3_admissibility(
    *,
    position_residual_mm,
    axis_residual_deg,
    positions,
    ranges,
    static_query,
) -> tuple[bool, bool]:
    bounds_valid = bool(
        positions is not None and _p3_positions_within_ranges(positions, ranges)
    )
    kinematic_valid = bool(
        position_residual_mm is not None
        and axis_residual_deg is not None
        and position_residual_mm <= 0.25
        and axis_residual_deg <= 0.5
        and bounds_valid
    )
    return bounds_valid, bool(
        kinematic_valid
        and static_query["trustworthy_authoritative"]
        and static_query["accepted"] is True
    )


def _p3_reclassify_saved_static_record(record, ranges) -> dict[str, object]:
    """Correct only the known lossy native-status echo in retained evidence."""

    corrected = json.loads(json.dumps(record))
    evidence = corrected.get("native_static_evidence")
    evidence = dict(evidence) if isinstance(evidence, dict) else {}
    request = evidence.get("request")
    response = evidence.get("response")
    policy = evidence.get("policy_identity")
    scene_ack = evidence.get("scene_acknowledgement")
    request = request if isinstance(request, dict) else {}
    response = response if isinstance(response, dict) else {}
    policy = policy if isinstance(policy, dict) else {}
    scene_ack = scene_ack if isinstance(scene_ack, dict) else {}
    reasons = []

    def require(condition, reason):
        if not condition:
            reasons.append(reason)

    request_id = request.get("request_id")
    task_fingerprint = request.get("task_fingerprint")
    sequence = request.get("sequence")
    requested = request.get("requested_positions")
    require(evidence.get("command_ok") is True, "static command did not report success")
    require(isinstance(request_id, str) and request_id, "static request identity is missing")
    require(
        request.get("validation_kind") == "static_state"
        and response.get("validation_kind") == "static_state",
        "static validation kind is missing or mismatched",
    )
    require(
        request.get("phase") == "drilling" and response.get("phase") == "drilling",
        "static phase is missing or mismatched",
    )
    require(
        request.get("validate_only") is True and response.get("validate_only") is True,
        "static response is not explicitly validate-only",
    )
    require(
        isinstance(sequence, int)
        and not isinstance(sequence, bool)
        and sequence > 0
        and _p3_exact_integer(response.get("sequence"), sequence),
        "static response sequence is missing or mismatched",
    )
    require(
        isinstance(task_fingerprint, str)
        and task_fingerprint
        and response.get("task_fingerprint") == task_fingerprint,
        "static response task identity is missing or mismatched",
    )
    require(
        response.get("request_id") == request_id,
        "static response request identity is missing or mismatched",
    )
    expected_policy = policy.get("expected")
    guard_session_id = policy.get("guard_session_id")
    require(
        isinstance(expected_policy, str)
        and expected_policy
        and policy.get("configured") == expected_policy
        and policy.get("reported") == expected_policy
        and response.get("collision_scene_policy_fingerprint") == expected_policy,
        "static response policy fingerprint is missing or mismatched",
    )
    require(
        isinstance(guard_session_id, str)
        and guard_session_id
        and response.get("guard_session_id") == guard_session_id,
        "static response guard-session identity is missing or mismatched",
    )
    require(isinstance(response.get("accepted"), bool), "static response acceptance is missing or malformed")
    require(
        isinstance(requested, (list, tuple)) and len(requested) == 5,
        "static request J1-J5 vector is missing or malformed",
    )
    vector_deltas = {}
    if isinstance(requested, (list, tuple)) and len(requested) == 5:
        for field in ("requested_positions", "starting_positions", "evaluated_positions"):
            observed = response.get(field)
            matches = _p3_exact_vector(observed, requested)
            require(matches, f"static response {field} J1-J5 vector is missing or mismatched")
            if matches:
                vector_deltas[field] = max(
                    abs(float(actual) - float(expected))
                    for actual, expected in zip(observed, requested)
                )
    require(
        _p3_exact_integer(response.get("evaluated_sample_index"), 1)
        and _p3_exact_integer(response.get("total_sample_count"), 1)
        and _p3_exact_integer(response.get("checked_samples"), 1),
        "static response does not prove a one-state evaluation",
    )
    original_reasons = evidence.get("inconclusive_reasons")
    expected_original_reasons = [
        "static response requested J1-J5 vector is missing or mismatched",
        "static response starting J1-J5 vector is missing or mismatched",
        "static response evaluated J1-J5 vector is missing or mismatched",
        "scene readback is not correlated to this publication/request",
    ]
    require(
        original_reasons == expected_original_reasons,
        "original inconclusive reasons contain an issue other than the known status serialization defect",
    )
    require(
        scene_ack.get("mismatches") == [
            "scene readback is not correlated to this publication/request"
        ]
        and scene_ack.get("expected_object_ids") == scene_ack.get("observed_object_ids")
        and len(scene_ack.get("expected_object_ids") or ()) == 31
        and len(set(scene_ack.get("expected_object_ids") or ())) == 31
        and response.get("world_object_count") == 31
        and isinstance(response.get("world_objects"), list)
        and len(response.get("world_objects")) == 31
        and scene_ack.get("expected_policy_fingerprint") == expected_policy
        and scene_ack.get("observed_policy_fingerprint") == expected_policy
        and scene_ack.get("readback_correlated") is False
        and scene_ack.get("trusted") is False,
        "saved scene readback has a non-serialization mismatch",
    )
    trustworthy = not reasons
    reported_accepted = response.get("accepted") if trustworthy else None
    classification = (
        "ACCEPTED"
        if reported_accepted is True
        else "REJECTED"
        if reported_accepted is False
        else "INCONCLUSIVE"
    )
    corrected_scene_ack = dict(scene_ack)
    if trustworthy:
        corrected_scene_ack.update(
            {
                "status": "Acknowledged",
                "trusted": True,
                "attribution_allowed": True,
                "readback_correlated": True,
                "mismatches": [],
            }
        )
    bounds_valid, admissible = _p3_admissibility(
        position_residual_mm=corrected.get("position_residual_mm"),
        axis_residual_deg=corrected.get("axis_residual_deg"),
        positions=corrected.get("solution_joint_positions_si"),
        ranges=ranges,
        static_query={
            "trustworthy_authoritative": trustworthy,
            "accepted": reported_accepted,
        },
    )
    corrected["original_static_classification"] = {
        key: record.get(key)
        for key in (
            "phase_static_valid",
            "phase_static_authoritative",
            "static_state_classification",
            "authoritative_static_valid",
            "admissible",
        )
    }
    corrected.update(
        {
            "joint_bounds_valid": bounds_valid,
            "phase_static_valid": reported_accepted,
            "phase_static_authoritative": trustworthy,
            "static_state_classification": classification,
            "authoritative_static_valid": reported_accepted,
            "admissible": admissible,
        }
    )
    evidence["original_scene_acknowledgement"] = scene_ack
    evidence["scene_acknowledgement"] = corrected_scene_ack
    evidence["inconclusive_reasons"] = reasons
    evidence["posthoc_attribution"] = {
        "no_new_native_query": True,
        "native_status_serialization": "collision_guard std::setprecision(12)",
        "vector_relative_tolerance": P3_STATUS_VECTOR_REL_TOL,
        "vector_absolute_tolerance": P3_STATUS_VECTOR_ABS_TOL,
        "maximum_vector_delta": max(vector_deltas.values(), default=None),
        "vector_deltas": vector_deltas,
        "original_inconclusive_reasons": original_reasons,
    }
    corrected["native_static_evidence"] = evidence
    return corrected


def _p3_offline_reclassify_evidence(
    payload, *, source_path: str, source_sha256: str, case_sha256: str
) -> dict[str, object]:
    """Produce a companion report from retained responses; never query runtime."""

    if not isinstance(payload, dict) or payload.get("mode") != "p3_endpoint_revalidation_r4":
        raise ValueError("offline P3 correction requires one r4 static revalidation artifact")
    candidates = payload.get("candidates")
    input_evidence = payload.get("input")
    ranges = payload.get("active_joint_ranges")
    if (
        not isinstance(candidates, list)
        or len(candidates) != 21
        or payload.get("candidate_count") != 21
        or payload.get("converged_candidate_count") != 21
        or not str(payload.get("case") or "").endswith(P3_R4_CASE_SUFFIX)
        or case_sha256 != P3_R4_CASE_SHA256
        or not isinstance(input_evidence, dict)
        or input_evidence.get("sha256") != P3_REVALIDATION_SHA256
        or input_evidence.get("candidate_count") != P3_MAX_IK_SOLVES
        or not isinstance(ranges, list)
    ):
        raise ValueError("offline P3 correction input is not the locked 21-vector r4 batch")
    corrected = json.loads(json.dumps(payload))
    corrected_records = [
        _p3_reclassify_saved_static_record(record, tuple(ranges))
        for record in corrected["candidates"]
    ]
    request_ids = [
        record["native_static_evidence"]["request"].get("request_id")
        for record in corrected_records
    ]
    sequences = [
        record["native_static_evidence"]["request"].get("sequence")
        for record in corrected_records
    ]
    if (
        len(set(request_ids)) != len(request_ids)
        or not all(isinstance(value, str) and value for value in request_ids)
        or sequences != list(range(1, len(corrected_records) + 1))
    ):
        raise ValueError("offline P3 correction cannot prove unique increasing static requests")
    summary = _p3_summary(corrected_records)
    corrected.update(
        {
            "candidates": corrected_records,
            "valid_endpoint_count": summary["admissible"],
            "admissible_candidate_count": summary["admissible"],
            "phase_static_counts": {
                key: summary[key] for key in ("accepted", "rejected", "inconclusive")
            },
            "summary": summary,
            "result": _p3_result(
                summary,
                native_build_trusted=bool(corrected.get("native_build_trusted")),
            ),
            "evidence_kind": "offline_p3_static_attribution_correction",
            "source_evidence": {
                "path": str(source_path),
                "sha256": str(source_sha256),
                "locked_case": payload.get("case"),
                "locked_case_sha256": str(case_sha256),
                "original_result": payload.get("result"),
                "original_phase_static_counts": payload.get("phase_static_counts"),
                "native_query_count": 0,
                "ik_solve_count": 0,
                "reason": "correct only collision_guard 12-significant-digit status-vector serialization",
            },
        }
    )
    return corrected


def _p3_endpoint_metadata(facade, logic, parameter_node, snapshot, scene_context):
    task = (
        snapshot.to_dict()
        if hasattr(snapshot, "to_dict") and callable(snapshot.to_dict)
        else _p3_jsonable(snapshot)
    )
    native_build = corrected_native_build_identity()
    return {
        "task_fingerprint": str(snapshot.snapshot_fingerprint),
        "task_snapshot": task,
        "tcp_frame": str(snapshot.tool_frame),
        "tcp_provenance": str(snapshot.tool_provenance),
        "policy_identity": dict(scene_context["policy"]),
        "scene_audit": {
            "status": scene_context["audit_status"],
            "fingerprint": scene_context["audit_fingerprint"],
            "expected_object_count": len(scene_context["expected_objects"]),
            "error": scene_context["error"],
        },
        "native_build_identity": native_build,
        "native_build_trusted": bool(
            native_build.get("available")
            and native_build.get("matches_corrected_build")
        ),
    }


def _p3_summary(candidates):
    summary = {"accepted": 0, "rejected": 0, "inconclusive": 0, "admissible": 0}
    for record in candidates:
        if record.get("solution_joint_positions_si") is None:
            continue
        classification = str(record.get("static_state_classification") or "INCONCLUSIVE").lower()
        if classification not in ("accepted", "rejected", "inconclusive"):
            classification = "inconclusive"
        summary[classification] += 1
        if record.get("admissible") is True:
            summary["admissible"] += 1
    return summary


def _p3_result(summary, *, native_build_trusted: bool = True):
    if summary["inconclusive"] or not native_build_trusted:
        return "INCONCLUSIVE"
    return (
        "PASS"
        if summary["admissible"]
        else "NO_VALID_TARGET_SOLUTION_FOUND_IN_BOUNDED_SEARCH"
    )


def _p3_revalidation_input() -> tuple[Path, dict[str, object], tuple[dict[str, object], ...], str]:
    path = Path(P3_REVALIDATION_INPUT)
    if not path.is_file():
        raise RuntimeError(f"P3 revalidation input is missing: {path}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != P3_REVALIDATION_SHA256:
        raise RuntimeError(
            "P3 revalidation input SHA-256 mismatch: "
            f"expected {P3_REVALIDATION_SHA256}, got {digest}"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"P3 revalidation input is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("mode") != P3_REVALIDATION_MODE:
        raise RuntimeError(
            f"P3 revalidation input must use mode {P3_REVALIDATION_MODE}."
        )
    candidates = payload.get("candidates")
    declared_count = payload.get("candidate_count")
    if (
        not isinstance(candidates, list)
        or isinstance(declared_count, bool)
        or not isinstance(declared_count, int)
        or declared_count != len(candidates)
        or declared_count != P3_MAX_IK_SOLVES
    ):
        raise RuntimeError("P3 revalidation input candidate count is malformed.")
    converged = []
    indexes = set()
    for source_index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise RuntimeError(f"P3 revalidation candidate {source_index} is malformed.")
        solution = candidate.get("solution_joint_positions_si")
        if solution is None:
            continue
        candidate_index = candidate.get("candidate_index")
        if (
            isinstance(candidate_index, bool)
            or not isinstance(candidate_index, int)
            or candidate_index < 0
            or candidate_index in indexes
        ):
            raise RuntimeError("P3 revalidation source candidate indexes are malformed.")
        positions = _p3_canonical_solution(solution)
        if positions is None:
            raise RuntimeError(
                f"P3 revalidation candidate {candidate_index} lacks a finite canonical J1-J5 vector."
            )
        position_residual = _p3_finite_number(candidate.get("position_residual_mm"))
        axis_residual = _p3_finite_number(candidate.get("axis_residual_deg"))
        if position_residual is None or axis_residual is None:
            raise RuntimeError(
                f"P3 revalidation candidate {candidate_index} lacks finite saved residuals."
            )
        indexes.add(candidate_index)
        converged.append(
            {
                "source_candidate_index": candidate_index,
                "solution_joint_positions_si": positions,
                "position_residual_mm": position_residual,
                "axis_residual_deg": axis_residual,
            }
        )
    if len(converged) != 21:
        raise RuntimeError(
            "P3 revalidation input must contain exactly 21 finite canonical J1-J5 vectors; "
            f"found {len(converged)}."
        )
    if payload.get("converged_candidate_count") != len(converged):
        raise RuntimeError("P3 revalidation input converged-candidate count is malformed.")
    return path, payload, tuple(converged), digest


def _p3_revalidate_saved_candidates(
    facade, logic, parameter_node, snapshot
) -> dict[str, object]:
    """Recheck locked convergences only; this path never seeds or solves IK."""

    input_path, input_payload, source_records, input_sha256 = _p3_revalidation_input()
    robot_node = bridge.find_ros2_robot_by_name(bridge.ROS2_ROBOT_NAME)
    if robot_node is None:
        raise RuntimeError("P3 revalidation could not find the ROS robot")
    ranges = _p3_runtime_joint_ranges(robot_node)
    guard_ready, guard_message = facade._configure_phase_guard(
        parameter_node, snapshot, static_only=True
    )
    if not guard_ready:
        raise RuntimeError("P3 revalidation phase guard setup: " + str(guard_message))
    policy_context = _p3_policy_context(facade)
    scene_context = _p3_scene_context(
        logic, parameter_node, policy_context, allow_deferred_static_ack=True
    )
    request_prefix = f"p3-r4-revalidation-{uuid4().hex}"
    records = []
    static_sequence = 0
    for source in source_records:
        positions = source["solution_joint_positions_si"]
        source_index = int(source["source_candidate_index"])
        static_sequence += 1
        static_query = _p3_static_state_query(
            positions,
            snapshot=snapshot,
            sequence=static_sequence,
            request_id=f"{request_prefix}-{source_index}",
            scene_context=scene_context,
        )
        generic = _p3_generic_static_diagnostic(positions)
        native_fk = _p3_native_fk_evidence(
            positions,
            base_transform=parameter_node.robotBaseTransform,
        )
        position_residual = source["position_residual_mm"]
        axis_residual = source["axis_residual_deg"]
        bounds_valid, admissible = _p3_admissibility(
            position_residual_mm=position_residual,
            axis_residual_deg=axis_residual,
            positions=positions,
            ranges=ranges,
            static_query=static_query,
        )
        records.append(
            {
                "candidate_index": source_index,
                "source_candidate_index": source_index,
                "position_residual_mm": position_residual,
                "axis_residual_deg": axis_residual,
                "solution_joint_positions_si": positions,
                "joint_bounds_valid": bounds_valid,
                "generic_static_valid": generic["valid"],
                "generic_static_authoritative": generic["authoritative"],
                "generic_static_message": generic["message"] or generic["error"],
                "phase_static_valid": static_query["accepted"],
                "phase_static_authoritative": static_query["trustworthy_authoritative"],
                "phase_static_message": static_query["message"],
                "static_state_classification": static_query["classification"],
                "authoritative_static_valid": static_query["accepted"],
                "admissible": admissible,
                "retained_for_p4": False,
                "native_static_evidence": static_query["evidence"],
                "native_fk_evidence": native_fk,
            }
        )
    summary = _p3_summary(records)
    metadata = _p3_endpoint_metadata(facade, logic, parameter_node, snapshot, scene_context)
    source_indexes = [record["source_candidate_index"] for record in records]
    return {
        "mode": "p3_endpoint_revalidation_r4",
        "revalidation": True,
        "case": str(PACKAGE),
        "target_fdi": target_fdi(parameter_node),
        "entry_ras_mm": list(snapshot.entry_ras_mm),
        "target_ras_mm": list(snapshot.target_ras_mm),
        "tolerances": {"position_mm": 0.25, "axis_deg": 0.5},
        "active_joint_ranges": list(ranges),
        "candidate_count": len(records),
        "source_candidate_count": len(input_payload["candidates"]),
        "converged_candidate_count": len(records),
        "source_candidate_indexes": source_indexes,
        "valid_endpoint_count": summary["admissible"],
        "admissible_candidate_count": summary["admissible"],
        "phase_static_counts": {
            key: summary[key] for key in ("accepted", "rejected", "inconclusive")
        },
        "retained_representative_candidate_indices": [],
        "summary": summary,
        "result": _p3_result(
            summary,
            native_build_trusted=bool(metadata["native_build_trusted"]),
        ),
        "input": {
            "path": str(input_path),
            "sha256": input_sha256,
            "mode": input_payload["mode"],
            "candidate_count": len(input_payload["candidates"]),
            "source_candidate_indexes": source_indexes,
        },
        "input_path": str(input_path),
        "input_sha256": input_sha256,
        "seed_manifest": None,
        "seed_generation": {
            "performed": False,
            "reason": "revalidation consumes only locked converged vectors",
        },
        "ik_solve_count": 0,
        **metadata,
        "candidates": records,
        "forbidden_actions_observed": [
            "zero native position-axis IK calls",
            "no seed or manifest generation",
            "no Home-to-candidate transition; endpoint checks are static_state only",
            "no approach or drilling planner invocation",
            "no preview, raw joint command stream, or applied joint motion",
            "no external controller or hardware endpoint, spindle, or patient action",
            "only the locked r4 P3 candidate artifact was read; no r7/r13 or P2 case data",
        ],
    }


def endpoint_only_diagnostic(facade, logic, parameter_node, snapshot) -> dict[str, object]:
    """Run the r4-only P3 endpoint batch without planning or preview."""

    if P3_REVALIDATION_INPUT:
        return _p3_revalidate_saved_candidates(facade, logic, parameter_node, snapshot)
    home = logic.taskHomeRecord(parameter_node)
    if home is None:
        raise RuntimeError("P3 endpoint check requires a live validated Task Home")
    robot_node = bridge.find_ros2_robot_by_name(bridge.ROS2_ROBOT_NAME)
    if robot_node is None:
        raise RuntimeError("P3 endpoint check could not find the ROS robot")
    ranges = _p3_runtime_joint_ranges(robot_node)
    seeds: list[dict[str, object]] = []

    def add_seed(kind: str, positions: dict[str, float], provenance: object) -> None:
        if len(seeds) >= P3_MAX_IK_SOLVES:
            return
        canonical = bridge.canonicalize_planning_joint_positions(positions)
        if any(canonical == item["joint_positions_si"] for item in seeds):
            return
        seeds.append({"kind": kind, "provenance": provenance, "joint_positions_si": canonical})

    add_seed(
        "task_home",
        dict(zip(home.joint_names, home.joint_positions_si)),
        "r4_live_task_home",
    )
    try:
        workspace = json.loads(str(parameter_node.step6AssistedLimitProposalJson or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        workspace = {}
    for evidence in workspace.get("accepted_sample_evidence", ()):
        if not isinstance(evidence, dict):
            continue
        names = tuple(evidence.get("joint_names", ()))
        values = tuple(evidence.get("joint_positions_si", ()))
        connectivity = evidence.get("home_connectivity", {})
        if (
            names == bridge.ROS2_JOINT_SI_ORDER
            and len(values) == len(bridge.ROS2_JOINT_SI_ORDER)
            and isinstance(connectivity, dict)
            and connectivity.get("status") == "HomeConnected"
        ):
            add_seed(
                "workspace",
                dict(zip(names, values)),
                {"r4_workspace_sample_index": int(evidence.get("sample_index", len(seeds)))},
            )
    halton_index = 1
    while len(seeds) < P3_MAX_IK_SOLVES:
        add_seed(
            "halton_joint_limit_coverage",
            {
                str(item["name"]): float(item["lower"]) + _halton_value(halton_index, base)
                * (float(item["upper"]) - float(item["lower"]))
                for item, base in zip(ranges, P3_HALTON_BASES)
            },
            {"halton_index": halton_index, "bases": P3_HALTON_BASES},
        )
        halton_index += 1
    guard_ready, guard_message = facade._configure_phase_guard(parameter_node, snapshot)
    if not guard_ready:
        raise RuntimeError("P3 endpoint phase guard setup: " + str(guard_message))
    policy_context = _p3_policy_context(facade)
    scene_context = _p3_scene_context(logic, parameter_node, policy_context)
    target_world = bridge.tool_pose_matrices_world_mm(
        snapshot.entry_ras_mm, snapshot.target_ras_mm, 2
    )[-1]
    target_base = bridge._pose_matrices_world_to_base_mm(
        [target_world], parameter_node.robotBaseTransform
    )[0]
    candidates = []
    static_sequence = 0
    request_prefix = f"p3-r4-static-{uuid4().hex}"
    for candidate_index, seed in enumerate(seeds):
        positions_seed = dict(seed["joint_positions_si"])
        solution = robot_node.ComputeMoveItPositionAxisIK(
            target_base, bridge.ROS2_TOOL_TCP_LINK, bridge.joint_si_vector(positions_seed), 2.0, False
        )
        position_residual = _p3_finite_number(
            robot_node.GetLastMoveItPositionAxisIKPositionResidualMm()
        )
        axis_residual = _p3_finite_number(
            robot_node.GetLastMoveItPositionAxisIKAxisResidualDeg()
        )
        positions = (
            _p3_canonical_solution(
                dict(zip(bridge.ROS2_JOINT_SI_ORDER, tuple(solution)))
            )
            if solution
            else None
        )
        record = {
            "candidate_index": candidate_index,
            "seed": seed,
            "message": str(robot_node.GetLastMoveItPositionAxisIKMessage() or ""),
            "position_residual_mm": position_residual,
            "axis_residual_deg": axis_residual,
            "solution_joint_positions_si": positions,
            "joint_bounds_valid": False,
            "generic_static_valid": None,
            "generic_static_authoritative": None,
            "generic_static_message": "",
            "phase_static_valid": None,
            "phase_static_authoritative": False,
            "phase_static_message": "",
            "static_state_classification": "INCONCLUSIVE",
            "authoritative_static_valid": None,
            "admissible": False,
            "cluster_index": None,
            "retained_for_p4": False,
            "native_static_evidence": None,
            "native_fk_evidence": None,
        }
        if positions is not None:
            generic = _p3_generic_static_diagnostic(positions)
            static_sequence += 1
            static_query = _p3_static_state_query(
                positions,
                snapshot=snapshot,
                sequence=static_sequence,
                request_id=f"{request_prefix}-{candidate_index}",
                scene_context=scene_context,
            )
            native_fk = _p3_native_fk_evidence(
                positions,
                base_transform=parameter_node.robotBaseTransform,
            )
            bounds_valid, admissible = _p3_admissibility(
                position_residual_mm=position_residual,
                axis_residual_deg=axis_residual,
                positions=positions,
                ranges=ranges,
                static_query=static_query,
            )
            record.update(
                {
                    "joint_bounds_valid": bounds_valid,
                    "generic_static_valid": generic["valid"],
                    "generic_static_authoritative": generic["authoritative"],
                    "generic_static_message": generic["message"] or generic["error"],
                    "phase_static_valid": static_query["accepted"],
                    "phase_static_authoritative": static_query["trustworthy_authoritative"],
                    "phase_static_message": static_query["message"],
                    "static_state_classification": static_query["classification"],
                    "authoritative_static_valid": static_query["accepted"],
                    "admissible": admissible,
                    "native_static_evidence": static_query["evidence"],
                    "native_fk_evidence": native_fk,
                }
            )
        candidates.append(record)
    clusters: list[list[dict[str, object]]] = []
    for record in candidates:
        solution = record["solution_joint_positions_si"]
        if solution is None:
            continue
        for cluster_index, cluster in enumerate(clusters):
            if _p3_positions_match(solution, cluster[0]["solution_joint_positions_si"], ranges):
                record["cluster_index"] = cluster_index
                cluster.append(record)
                break
        else:
            record["cluster_index"] = len(clusters)
            clusters.append([record])
    admissible = [record for record in candidates if record["admissible"]]
    ranked = sorted(
        admissible,
        key=lambda record: (
            -_p3_normalized_margin(record["solution_joint_positions_si"], ranges),
            float(record["position_residual_mm"]),
            float(record["axis_residual_deg"]),
            tuple(float(record["solution_joint_positions_si"][name]) for name in bridge.ROS2_JOINT_SI_ORDER),
        ),
    )
    representatives = []
    retained_clusters = set()
    for record in ranked:
        cluster_index = int(record["cluster_index"])
        if cluster_index in retained_clusters or len(representatives) >= 8:
            continue
        record["retained_for_p4"] = True
        record["normalized_joint_bound_margin"] = _p3_normalized_margin(
            record["solution_joint_positions_si"], ranges
        )
        representatives.append(record["candidate_index"])
        retained_clusters.add(cluster_index)
    summary = _p3_summary(candidates)
    metadata = _p3_endpoint_metadata(facade, logic, parameter_node, snapshot, scene_context)
    return {
        "mode": "p3_endpoint_only_r4",
        "case": str(PACKAGE),
        "target_fdi": target_fdi(parameter_node),
        "entry_ras_mm": list(snapshot.entry_ras_mm),
        "target_ras_mm": list(snapshot.target_ras_mm),
        "tolerances": {"position_mm": 0.25, "axis_deg": 0.5},
        "seed_limit": P3_MAX_IK_SOLVES,
        "seed_manifest": seeds,
        "active_joint_ranges": list(ranges),
        "candidate_count": len(candidates),
        "converged_candidate_count": sum(record["solution_joint_positions_si"] is not None for record in candidates),
        "unique_solution_count": len(clusters),
        "valid_endpoint_count": len(admissible),
        "admissible_candidate_count": len(admissible),
        "phase_static_counts": {
            key: summary[key] for key in ("accepted", "rejected", "inconclusive")
        },
        "retained_representative_candidate_indices": representatives,
        "summary": summary,
        "result": _p3_result(
            summary,
            native_build_trusted=bool(metadata["native_build_trusted"]),
        ),
        **metadata,
        "candidates": candidates,
        "forbidden_actions_observed": [
            "no approach or drilling planner invocation",
            "no Home-to-candidate transition; endpoint checks are static_state only",
            "no preview or applied joint motion",
            "no external controller or hardware endpoint, spindle, or patient action",
            "no historical r7/r13 or P2 case input",
        ],
    }


def _p4_insertion_input() -> tuple[Path, dict[str, object], tuple[dict[str, object], ...], str]:
    """Load only the corrected r4 P3 evidence that supplies P4 candidates."""

    path = Path(P4_INSERTION_INPUT)
    if not path.is_file():
        raise RuntimeError("P4 insertion input is missing: " + str(path))
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != P4_INPUT_SHA256:
        raise RuntimeError("P4 insertion input SHA-256 does not match the locked P3 correction.")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("P4 insertion input is not valid JSON: " + str(exc)) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("P4 insertion input must be a JSON object.")
    if payload.get("mode") != "p3_endpoint_revalidation_r4" or payload.get("result") != "PASS":
        raise RuntimeError("P4 insertion input is not the corrected passing r4 P3 evidence.")
    if payload.get("case") != str(PACKAGE):
        raise RuntimeError("P4 insertion input references a different case.")
    source = payload.get("source_evidence")
    if not isinstance(source, dict):
        raise RuntimeError("P4 insertion input has no retained source-evidence record.")
    if (
        source.get("locked_case_sha256") != P3_R4_CASE_SHA256
        or source.get("sha256") != "d5a3ef8857b518a293d1ed7c8a9c750d0bfe0922110150242c4a4107729acd4f"
        or source.get("native_query_count") != 0
        or source.get("ik_solve_count") != 0
    ):
        raise RuntimeError("P4 insertion input does not preserve the locked corrected P3 provenance.")
    prior = payload.get("input")
    if not isinstance(prior, dict) or prior.get("sha256") != P3_REVALIDATION_SHA256:
        raise RuntimeError("P4 insertion input does not link the locked 21-vector P3 source.")
    counts = payload.get("phase_static_counts")
    if counts != {"accepted": 21, "rejected": 0, "inconclusive": 0}:
        raise RuntimeError("P4 insertion input has unexpected P3 phase-static counts.")
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list) or len(raw_candidates) != 21:
        raise RuntimeError("P4 insertion input must retain exactly 21 corrected P3 candidates.")
    records = []
    source_indexes = []
    for item in raw_candidates:
        if not isinstance(item, dict):
            raise RuntimeError("P4 insertion input contains a malformed candidate record.")
        positions = _p3_canonical_solution(item.get("solution_joint_positions_si"))
        source_index = item.get("source_candidate_index")
        if (
            positions is None
            or not isinstance(source_index, int)
            or isinstance(source_index, bool)
            or item.get("admissible") is not True
            or item.get("phase_static_valid") is not True
            or item.get("static_state_classification") != "ACCEPTED"
        ):
            raise RuntimeError("P4 insertion input contains a non-admissible corrected P3 candidate.")
        position_error = _p3_finite_number(item.get("position_residual_mm"))
        axis_error = _p3_finite_number(item.get("axis_residual_deg"))
        if (
            position_error is None
            or axis_error is None
            or position_error > 0.25
            or axis_error > 0.5
        ):
            raise RuntimeError("P4 insertion input contains an out-of-tolerance P3 candidate.")
        source_indexes.append(source_index)
        records.append(
            {
                "source_candidate_index": source_index,
                "target_joint_positions_si": positions,
                "position_residual_mm": position_error,
                "axis_residual_deg": axis_error,
                "p3_static_evidence": item.get("native_static_evidence"),
                "p3_native_fk_evidence": item.get("native_fk_evidence"),
            }
        )
    if source_indexes != list(prior.get("source_candidate_indexes") or ()):
        raise RuntimeError("P4 insertion input candidate-source ordering is not attributable.")
    if len(set(source_indexes)) != len(source_indexes):
        raise RuntimeError("P4 insertion input has duplicate source candidate indexes.")
    return path, payload, tuple(records), digest


def _p4_housing_status(p3_static_evidence) -> tuple[str, float | None]:
    """Keep a known guide warning distinct from literal housing clearance."""

    evidence = p3_static_evidence if isinstance(p3_static_evidence, dict) else {}
    response = evidence.get("response") if isinstance(evidence.get("response"), dict) else {}
    warning = response.get("guide_clearance_warning")
    distance = _p3_finite_number(response.get("minimum_world_distance_m"))
    if warning is True:
        return "AUTHORIZED_GUIDE_WARNING_NOT_HOUSING_CLEAR", None
    if warning is False and distance is not None and distance > 0.0:
        return "HOUSING_CLEAR", distance
    return "HOUSING_CLEAR_UNAVAILABLE", None


def _p4_select_representatives(
    candidates: tuple[dict[str, object], ...],
    ranges: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    """Reapply the P3 fixed clustering/ranking without adding an IK search."""

    clusters: list[list[dict[str, object]]] = []
    decorated = []
    for source in candidates:
        record = dict(source)
        positions = record["target_joint_positions_si"]
        for cluster_index, cluster in enumerate(clusters):
            if _p3_positions_match(positions, cluster[0]["target_joint_positions_si"], ranges):
                record["cluster_index"] = cluster_index
                cluster.append(record)
                break
        else:
            record["cluster_index"] = len(clusters)
            clusters.append([record])
        status, clearance_m = _p4_housing_status(record.get("p3_static_evidence"))
        record["p3_housing_status"] = status
        record["p3_housing_clearance_m"] = clearance_m
        record["normalized_joint_bound_margin"] = _p3_normalized_margin(
            positions, ranges
        )
        decorated.append(record)

    def ranking_key(record):
        status = record["p3_housing_status"]
        clearance = record["p3_housing_clearance_m"]
        return (
            0 if status == "HOUSING_CLEAR" else 1 if status.startswith("AUTHORIZED") else 2,
            0 if clearance is not None else 1,
            -float(clearance) if clearance is not None else 0.0,
            -float(record["normalized_joint_bound_margin"]),
            float(record["position_residual_mm"]),
            float(record["axis_residual_deg"]),
            tuple(
                float(record["target_joint_positions_si"][name])
                for name in bridge.ROS2_JOINT_SI_ORDER
            ),
        )

    selected = []
    selected_clusters = set()
    for record in sorted(decorated, key=ranking_key):
        cluster_index = int(record["cluster_index"])
        if cluster_index in selected_clusters:
            continue
        selected.append(record)
        selected_clusters.add(cluster_index)
        if len(selected) == P4_MAX_REPRESENTATIVES:
            break
    return tuple(selected)


def _p4_axial_fractions(
    entry_ras_mm: tuple[float, float, float],
    target_ras_mm: tuple[float, float, float],
) -> tuple[float, tuple[float, ...]]:
    length_mm = math.sqrt(
        sum(
            (float(target_ras_mm[index]) - float(entry_ras_mm[index])) ** 2
            for index in range(3)
        )
    )
    if not math.isfinite(length_mm) or length_mm <= 0.0:
        raise ValueError("P4 requires a finite non-zero Entry-to-Target trajectory.")
    count = max(2, int(math.ceil(length_mm / P4_MAX_AXIAL_STEP_MM)) + 1)
    return length_mm, tuple(index / float(count - 1) for index in range(count))


def _p4_fk_residual(
    native_fk_evidence: dict[str, object],
    requested_ras_mm: tuple[float, float, float],
    drilling_axis_ras: tuple[float, float, float],
) -> dict[str, object]:
    """Recompute XYZ/axis residual from explicit-state world-RAS FK evidence."""

    pose = native_fk_evidence.get("world_ras_pose_mm") if isinstance(native_fk_evidence, dict) else None
    try:
        rows = tuple(tuple(float(value) for value in row) for row in pose)
        if len(rows) != 4 or any(len(row) != 4 for row in rows):
            raise ValueError("world-RAS FK pose is not 4x4")
        position = tuple(rows[index][3] for index in range(3))
        axis = tuple(rows[index][2] for index in range(3))
        axis_norm = math.sqrt(sum(value * value for value in axis))
        requested_norm = math.sqrt(sum(value * value for value in drilling_axis_ras))
        if axis_norm <= 1.0e-12 or requested_norm <= 1.0e-12:
            raise ValueError("world-RAS FK drill axis is degenerate")
        position_error = math.sqrt(
            sum(
                (position[index] - float(requested_ras_mm[index])) ** 2
                for index in range(3)
            )
        )
        cosine = max(
            -1.0,
            min(
                1.0,
                sum(axis[index] * float(drilling_axis_ras[index]) for index in range(3))
                / (axis_norm * requested_norm),
            ),
        )
        return {
            "available": True,
            "position_error_mm": position_error,
            "axis_error_deg": math.degrees(math.acos(cosine)),
        }
    except (TypeError, ValueError, IndexError):
        return {
            "available": False,
            "position_error_mm": None,
            "axis_error_deg": None,
        }


def _p4_world_pose_at_fraction(reference_pose, entry_ras_mm, target_ras_mm, fraction):
    """Copy the fixed drilling axis while placing one requested axial sample."""

    import vtk

    value = float(fraction)
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise ValueError("P4 axial fraction must be within [0, 1].")
    pose = vtk.vtkMatrix4x4()
    pose.DeepCopy(reference_pose)
    for axis in range(3):
        pose.SetElement(
            axis,
            3,
            float(entry_ras_mm[axis])
            + value * (float(target_ras_mm[axis]) - float(entry_ras_mm[axis])),
        )
    return pose


def _p4_depth_mm(length_mm: float, fraction: float) -> float:
    return float(length_mm) * float(fraction)


def _p4_transition_query(
    start_positions: dict[str, float],
    requested_positions: dict[str, float],
    *,
    snapshot,
    sequence: int,
    request_id: str,
    scene_context: dict[str, object],
    phase: str = "drilling",
) -> dict[str, object]:
    """Validate exactly one read-only drilling edge and retain its native reply."""

    start = bridge.joint_si_vector(start_positions)
    requested = bridge.joint_si_vector(requested_positions)
    request = {
        "request_id": str(request_id),
        "validation_kind": "transition",
        "phase": str(phase),
        "sequence": int(sequence),
        "validate_only": True,
        "task_fingerprint": str(snapshot.snapshot_fingerprint),
        "starting_positions": list(start),
        "requested_positions": list(requested),
    }
    command_ok = False
    command_message = ""
    try:
        command_ok, command_message = bridge.apply_task_phase_joint_positions(
            requested_positions,
            task_fingerprint=snapshot.snapshot_fingerprint,
            phase=str(phase),
            sequence=int(sequence),
            validate_only=True,
            validation_kind="transition",
            request_id=str(request_id),
            timeout_sec=6.0,
        )
    except Exception as exc:
        command_message = f"native P4 edge query failed: {type(exc).__name__}: {exc}"
    try:
        status = bridge.last_task_joint_status()
    except Exception as exc:
        status = None
        command_message = command_message or (
            f"native P4 edge status read failed: {type(exc).__name__}: {exc}"
        )
    response = _p3_jsonable(status)
    reasons = []
    if not isinstance(response, dict):
        reasons.append("missing or malformed native TaskJointStatus response")
        response = None
    else:
        if response.get("request_id") != request_id:
            reasons.append("edge response request identity is missing or mismatched")
        if response.get("validation_kind") != "transition":
            reasons.append("edge response validation kind is missing or mismatched")
        if response.get("phase") != str(phase):
            reasons.append("edge response phase is missing or mismatched")
        if response.get("validate_only") is not True:
            reasons.append("edge response is not explicitly validate-only")
        if not _p3_exact_integer(response.get("sequence"), sequence):
            reasons.append("edge response sequence is missing or mismatched")
        if response.get("task_fingerprint") != snapshot.snapshot_fingerprint:
            reasons.append("edge response task identity is missing or mismatched")
        expected_guard_session = str(scene_context["policy"].get("guard_session_id") or "")
        if not expected_guard_session:
            reasons.append("active P4 guard session identity is missing")
        elif response.get("guard_session_id") != expected_guard_session:
            reasons.append("edge response guard-session identity is missing or mismatched")
        if not isinstance(response.get("accepted"), bool):
            reasons.append("edge response acceptance is missing or malformed")
        if not _p3_exact_vector(response.get("requested_positions"), requested):
            reasons.append("edge response requested J1-J5 vector is missing or mismatched")
        if not _p3_exact_vector(response.get("starting_positions"), start):
            reasons.append("edge response starting J1-J5 vector is missing or mismatched")
        total = response.get("total_sample_count")
        checked = response.get("checked_samples")
        index = response.get("evaluated_sample_index")
        if not (
            _p3_exact_integer(total, total) and total >= 1
            and _p3_exact_integer(checked, checked) and 0 <= checked <= total
            and (
                index is None
                or (_p3_exact_integer(index, index) and 1 <= index <= total)
            )
        ):
            reasons.append("edge response interpolation telemetry is malformed")
        if response.get("accepted") is True:
            if not _p3_exact_vector(response.get("evaluated_positions"), requested):
                reasons.append("accepted edge did not evaluate its requested endpoint")
            if index != total or checked != total:
                reasons.append("accepted edge did not evaluate every native interpolation sample")
            fraction = _p3_finite_number(response.get("interpolation_fraction"))
            if fraction is None or not math.isclose(fraction, 1.0, abs_tol=P3_STATUS_VECTOR_ABS_TOL):
                reasons.append("accepted edge did not report terminal interpolation fraction")
        elif checked > 0:
            evaluated = response.get("evaluated_positions")
            if not _p3_exact_vector(evaluated, evaluated):
                reasons.append("rejected edge has no finite native evaluated state")
    observed_objects = (
        response.get("world_objects")
        if isinstance(response, dict) and isinstance(response.get("world_objects"), list)
        else ()
    )
    expected_policy = str(scene_context["policy"].get("active") or "")
    try:
        scene_ack = collision_scene_acknowledgement_evidence(
            scene_context["expected_objects"],
            observed_objects,
            expected_policy_fingerprint=expected_policy or None,
            observed_policy_fingerprint=(response or {}).get(
                "collision_scene_policy_fingerprint"
            ),
            readback_correlated=not reasons,
            reported_status=(
                ""
                if scene_context.get("deferred_static_ack")
                else str(scene_context.get("audit_status") or "")
            ),
        )
    except (TypeError, ValueError, KeyError) as exc:
        scene_ack = {
            "status": "Mismatch",
            "trusted": False,
            "attribution_allowed": False,
            "mismatches": [f"edge scene acknowledgement could not be evaluated: {exc}"],
        }
    if scene_context.get("error"):
        scene_ack = dict(scene_ack)
        scene_ack["trusted"] = False
        scene_ack["attribution_allowed"] = False
        scene_ack.setdefault("mismatches", []).append(str(scene_context["error"]))
    trustworthy = not reasons and scene_ack.get("trusted") is True
    reported_accepted = response.get("accepted") if isinstance(response, dict) else None
    classification = (
        "ACCEPTED"
        if trustworthy and reported_accepted is True
        else "REJECTED"
        if trustworthy and reported_accepted is False
        else "INCONCLUSIVE"
    )
    return {
        "accepted": reported_accepted if trustworthy else None,
        "reported_accepted": reported_accepted,
        "trustworthy_authoritative": trustworthy,
        "classification": classification,
        "message": str(command_message or (response or {}).get("reason") or ""),
        "evidence": {
            "request": request,
            "command_ok": bool(command_ok),
            "command_message": str(command_message or ""),
            "response": response,
            "scene_acknowledgement": scene_ack,
            "policy_identity": {
                "expected": expected_policy,
                "configured": scene_context["policy"].get("configured"),
                "reported": (response or {}).get(
                    "collision_scene_policy_fingerprint"
                ),
                "guard_session_id": scene_context["policy"].get(
                    "guard_session_id"
                ),
            },
            "trustworthy_authoritative": trustworthy,
            "inconclusive_reasons": list(reasons)
            + list(scene_ack.get("mismatches") or ())
            if not trustworthy
            else [],
        },
    }


def _p4_ik_attempt(
    robot_node,
    *,
    seed_positions: dict[str, float],
    reference_pose,
    entry_ras_mm: tuple[float, float, float],
    target_ras_mm: tuple[float, float, float],
    drilling_axis_ras: tuple[float, float, float],
    fraction: float,
    refinement_level: int,
    ranges: tuple[dict[str, object], ...],
    base_transform,
    budget: dict[str, int],
) -> dict[str, object]:
    """Run one fixed-timeout neighbor-seeded position-axis IK query."""

    requested_ras_mm = tuple(
        float(entry_ras_mm[index])
        + float(fraction)
        * (float(target_ras_mm[index]) - float(entry_ras_mm[index]))
        for index in range(3)
    )
    result = {
        "fraction": float(fraction),
        "depth_mm": _p4_depth_mm(
            math.sqrt(
                sum(
                    (float(target_ras_mm[index]) - float(entry_ras_mm[index])) ** 2
                    for index in range(3)
                )
            ),
            fraction,
        ),
        "requested_ras_mm": list(requested_ras_mm),
        "seed_joint_positions_si": dict(seed_positions),
        "refinement_level": int(refinement_level),
        "classification": "INCONCLUSIVE",
        "accepted": False,
        "joint_positions_si": None,
        "native_message": "",
        "native_position_residual_mm": None,
        "native_axis_residual_deg": None,
        "native_fk_evidence": None,
        "fk_residual": None,
        "joint_continuity": None,
    }
    if budget["ik_solve_count"] >= P4_MAX_IK_SOLVES:
        result["native_message"] = "P4 global IK-solve cap reached before this sample."
        result["classification"] = "INCONCLUSIVE"
        result["budget_exhausted"] = True
        return result
    budget["ik_solve_count"] += 1
    result["solve_index"] = budget["ik_solve_count"]
    try:
        world_pose = _p4_world_pose_at_fraction(
            reference_pose, entry_ras_mm, target_ras_mm, fraction
        )
        base_pose = bridge._pose_matrices_world_to_base_mm(
            [world_pose], base_transform
        )[0]
        solution = robot_node.ComputeMoveItPositionAxisIK(
            base_pose,
            bridge.ROS2_TOOL_TCP_LINK,
            bridge.joint_si_vector(seed_positions),
            2.0,
            False,
        )
        result["native_message"] = str(
            robot_node.GetLastMoveItPositionAxisIKMessage() or ""
        )
        result["native_position_residual_mm"] = _p3_finite_number(
            robot_node.GetLastMoveItPositionAxisIKPositionResidualMm()
        )
        result["native_axis_residual_deg"] = _p3_finite_number(
            robot_node.GetLastMoveItPositionAxisIKAxisResidualDeg()
        )
    except Exception as exc:
        result["native_message"] = f"native P4 IK query failed: {type(exc).__name__}: {exc}"
        return result
    if not solution:
        result["classification"] = "REJECTED"
        return result
    positions = _p3_canonical_solution(
        dict(zip(bridge.ROS2_JOINT_SI_ORDER, tuple(solution)))
    )
    if positions is None:
        result["native_message"] = (
            result["native_message"] + " Native P4 IK reply is malformed."
        ).strip()
        return result
    continuity = bridge.moveit_joint_goal_diagnostics(seed_positions, positions)
    positions = dict(continuity["submitted_goal"])
    result["joint_positions_si"] = positions
    result["joint_continuity"] = continuity
    native_fk = _p3_native_fk_evidence(positions, base_transform=base_transform)
    fk_residual = _p4_fk_residual(
        native_fk, requested_ras_mm, drilling_axis_ras
    )
    result["native_fk_evidence"] = native_fk
    result["fk_residual"] = fk_residual
    native_position = result["native_position_residual_mm"]
    native_axis = result["native_axis_residual_deg"]
    if not _p3_positions_within_ranges(positions, ranges):
        result["classification"] = "REJECTED"
        result["native_message"] = result["native_message"] or "P4 IK solution violates active joint bounds."
        return result
    if native_position is None or native_axis is None or not fk_residual["available"]:
        return result
    if (
        native_position > 0.25
        or native_axis > 0.5
        or fk_residual["position_error_mm"] > 0.25
        or fk_residual["axis_error_deg"] > 0.5
    ):
        result["classification"] = "REJECTED"
        result["native_message"] = result["native_message"] or "P4 IK/FK residual exceeds the unchanged endpoint tolerance."
        return result
    result["classification"] = "ACCEPTED"
    result["accepted"] = True
    return result


def _p4_recover_segment(
    robot_node,
    *,
    start_state: dict[str, object],
    end_fraction: float,
    refinement_level: int,
    reference_pose,
    entry_ras_mm: tuple[float, float, float],
    target_ras_mm: tuple[float, float, float],
    drilling_axis_ras: tuple[float, float, float],
    ranges: tuple[dict[str, object], ...],
    base_transform,
    budget: dict[str, int],
    attempts: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    """Recover one backward interval, refining only a proven failed edge."""

    attempt = _p4_ik_attempt(
        robot_node,
        seed_positions=dict(start_state["joint_positions_si"]),
        reference_pose=reference_pose,
        entry_ras_mm=entry_ras_mm,
        target_ras_mm=target_ras_mm,
        drilling_axis_ras=drilling_axis_ras,
        fraction=end_fraction,
        refinement_level=refinement_level,
        ranges=ranges,
        base_transform=base_transform,
        budget=budget,
    )
    attempts.append(attempt)
    if attempt.get("accepted") is True:
        return [attempt], None
    if (
        attempt.get("classification") != "REJECTED"
        or attempt.get("budget_exhausted")
        or refinement_level >= P4_MAX_MIDPOINT_REFINEMENTS
    ):
        return [], attempt
    midpoint = (float(start_state["fraction"]) + float(end_fraction)) * 0.5
    left, failure = _p4_recover_segment(
        robot_node,
        start_state=start_state,
        end_fraction=midpoint,
        refinement_level=refinement_level + 1,
        reference_pose=reference_pose,
        entry_ras_mm=entry_ras_mm,
        target_ras_mm=target_ras_mm,
        drilling_axis_ras=drilling_axis_ras,
        ranges=ranges,
        base_transform=base_transform,
        budget=budget,
        attempts=attempts,
    )
    if failure is not None:
        return [], failure
    right, failure = _p4_recover_segment(
        robot_node,
        start_state=left[-1],
        end_fraction=end_fraction,
        refinement_level=refinement_level + 1,
        reference_pose=reference_pose,
        entry_ras_mm=entry_ras_mm,
        target_ras_mm=target_ras_mm,
        drilling_axis_ras=drilling_axis_ras,
        ranges=ranges,
        base_transform=base_transform,
        budget=budget,
        attempts=attempts,
    )
    return (left + right, failure) if failure is None else ([], failure)


def _p4_backward_continuation(
    robot_node,
    *,
    target_positions: dict[str, float],
    entry_ras_mm: tuple[float, float, float],
    target_ras_mm: tuple[float, float, float],
    ranges: tuple[dict[str, object], ...],
    base_transform,
    budget: dict[str, int],
) -> dict[str, object]:
    """Construct one Target-to-Entry neighbor-seeded diagnostic branch."""

    length_mm, forward_fractions = _p4_axial_fractions(entry_ras_mm, target_ras_mm)
    drilling_axis_ras = tuple(
        (float(target_ras_mm[index]) - float(entry_ras_mm[index])) / length_mm
        for index in range(3)
    )
    reference_pose = bridge.tool_pose_matrices_world_mm(
        entry_ras_mm, target_ras_mm, 2
    )[-1]
    recovered = [
        {
            "fraction": 1.0,
            "depth_mm": length_mm,
            "requested_ras_mm": list(target_ras_mm),
            "joint_positions_si": dict(target_positions),
            "classification": "ACCEPTED",
            "accepted": True,
            "source": "saved_p3_target",
            "refinement_level": 0,
        }
    ]
    attempts: list[dict[str, object]] = []
    failure = None
    for fraction in reversed(forward_fractions[:-1]):
        segment, failure = _p4_recover_segment(
            robot_node,
            start_state=recovered[-1],
            end_fraction=float(fraction),
            refinement_level=0,
            reference_pose=reference_pose,
            entry_ras_mm=entry_ras_mm,
            target_ras_mm=target_ras_mm,
            drilling_axis_ras=drilling_axis_ras,
            ranges=ranges,
            base_transform=base_transform,
            budget=budget,
            attempts=attempts,
        )
        if failure is not None:
            break
        recovered.extend(segment)
    complete = failure is None and math.isclose(
        float(recovered[-1]["fraction"]), 0.0, abs_tol=1.0e-12
    )
    return {
        "status": "COMPLETE" if complete else (
            "INCONCLUSIVE" if failure and failure.get("classification") == "INCONCLUSIVE" else "REJECTED"
        ),
        "trajectory_length_mm": length_mm,
        "maximum_axial_step_mm": P4_MAX_AXIAL_STEP_MM,
        "uniform_fraction_count": len(forward_fractions),
        "maximum_midpoint_refinements": P4_MAX_MIDPOINT_REFINEMENTS,
        "drilling_axis_ras": list(drilling_axis_ras),
        "backward_states": recovered,
        "ik_attempts": attempts,
        "failure": failure,
    }


def _p4_housing_clear_from_query(query: dict[str, object]) -> bool:
    response = (
        query.get("evidence", {}).get("response")
        if isinstance(query.get("evidence"), dict)
        else None
    )
    return bool(
        query.get("classification") == "ACCEPTED"
        and isinstance(response, dict)
        and response.get("guide_clearance_warning") is False
        and _p3_finite_number(response.get("minimum_world_distance_m")) is not None
        and float(response["minimum_world_distance_m"]) > 0.0
    )


def _p4_forward_guard_validation(
    facade,
    logic,
    parameter_node,
    snapshot,
    *,
    forward_states: list[dict[str, object]],
    request_prefix: str,
) -> dict[str, object]:
    """Validate the recovered Entry-to-Target edges in their true direction."""

    if len(forward_states) < 2:
        return {
            "status": "INCONCLUSIVE",
            "message": "P4 has no complete recovered Entry-to-Target state sequence.",
            "entry_static": None,
            "edges": [],
            "last_guard_accepted": None,
            "last_housing_clear": None,
            "first_rejected": None,
        }
    entry = forward_states[0]
    entry_positions = dict(entry["joint_positions_si"])
    guard_ready, guard_message = facade._configure_phase_guard(
        parameter_node,
        snapshot,
        static_only=True,
        preflight_start_positions_si=entry_positions,
    )
    if not guard_ready:
        return {
            "status": "INCONCLUSIVE",
            "message": "P4 explicit read-only preflight setup failed: " + str(guard_message),
            "entry_static": None,
            "edges": [],
            "last_guard_accepted": None,
            "last_housing_clear": None,
            "first_rejected": None,
        }
    scene_context = _p3_scene_context(
        logic,
        parameter_node,
        _p3_policy_context(facade),
        allow_deferred_static_ack=True,
    )
    entry_static = _p3_static_state_query(
        entry_positions,
        snapshot=snapshot,
        sequence=1,
        request_id=f"{request_prefix}-entry-static",
        scene_context=scene_context,
    )
    if entry_static["classification"] != "ACCEPTED":
        return {
            "status": entry_static["classification"],
            "message": "P4 recovered Entry static validation did not pass.",
            "entry_static": entry_static,
            "edges": [],
            "last_guard_accepted": None,
            "last_housing_clear": None,
            "first_rejected": {"state": entry, "query": entry_static},
            "scene_context": scene_context,
        }
    last_guard_accepted = {"state": entry, "query": entry_static}
    last_housing_clear = last_guard_accepted if _p4_housing_clear_from_query(entry_static) else None
    edges = []
    for index, end in enumerate(forward_states[1:], start=1):
        start = forward_states[index - 1]
        query = _p4_transition_query(
            dict(start["joint_positions_si"]),
            dict(end["joint_positions_si"]),
            snapshot=snapshot,
            sequence=index,
            request_id=f"{request_prefix}-edge-{index}",
            scene_context=scene_context,
        )
        edge = {
            "edge_index": index,
            "start_fraction": float(start["fraction"]),
            "end_fraction": float(end["fraction"]),
            "start_depth_mm": float(start["depth_mm"]),
            "end_depth_mm": float(end["depth_mm"]),
            "start_joint_positions_si": dict(start["joint_positions_si"]),
            "end_joint_positions_si": dict(end["joint_positions_si"]),
            "query": query,
        }
        edges.append(edge)
        if query["classification"] != "ACCEPTED":
            return {
                "status": query["classification"],
                "message": "P4 forward guard rejected or could not attribute an edge.",
                "entry_static": entry_static,
                "edges": edges,
                "last_guard_accepted": last_guard_accepted,
                "last_housing_clear": last_housing_clear,
                "first_rejected": edge,
                "scene_context": scene_context,
            }
        last_guard_accepted = {"state": end, "query": query}
        if _p4_housing_clear_from_query(query):
            last_housing_clear = last_guard_accepted
    return {
        "status": "COMPLETE",
        "message": "P4 native guard accepted every recovered forward drilling edge.",
        "entry_static": entry_static,
        "edges": edges,
        "last_guard_accepted": last_guard_accepted,
        "last_housing_clear": last_housing_clear,
        "first_rejected": None,
        "scene_context": scene_context,
    }


def _p4_ranges_match(expected, observed) -> bool:
    if not isinstance(expected, list) or len(expected) != len(observed):
        return False
    for old, current in zip(expected, observed):
        if not isinstance(old, dict) or old.get("name") != current.get("name"):
            return False
        if old.get("type") != current.get("type"):
            return False
        for field in ("lower", "upper"):
            left = _p3_finite_number(old.get(field))
            right = _p3_finite_number(current.get(field))
            if left is None or right is None or not math.isclose(
                left, right, rel_tol=0.0, abs_tol=1.0e-12
            ):
                return False
    return True


def _runtime_native_build_identity(prefix: str) -> dict[str, object]:
    """Bind a read-only diagnostic to launcher-hashed native guard artifacts."""

    identity = dict(corrected_native_build_identity())
    expected_source = str(
        os.environ.get(f"DENTOBOT_{prefix}_NATIVE_SOURCE_SHA256", "") or ""
    )
    expected_binary = str(
        os.environ.get(f"DENTOBOT_{prefix}_NATIVE_BINARY_SHA256", "") or ""
    )
    identity["launcher_expected_source_sha256"] = expected_source or None
    identity["launcher_expected_binary_sha256"] = expected_binary or None
    identity["matches_launcher_runtime_build"] = bool(
        identity.get("available")
        and expected_source
        and expected_binary
        and identity.get("source_sha256") == expected_source
        and identity.get("binary_sha256") == expected_binary
    )
    return identity


def _p4_runtime_native_build_identity() -> dict[str, object]:
    """Bind the P4 process to the launcher-hashed source and native binary."""

    identity = _runtime_native_build_identity("P4")
    identity["matches_p4_runtime_build"] = bool(
        identity["matches_launcher_runtime_build"]
    )
    return identity


def _p5_runtime_native_build_identity() -> dict[str, object]:
    """Bind the P5 process to the launcher-hashed source and native binary."""

    identity = _runtime_native_build_identity("P5")
    identity["matches_p5_runtime_build"] = bool(
        identity["matches_launcher_runtime_build"]
    )
    return identity


def _p4_capture_visual_evidence(parameter_node, report: dict[str, object]) -> dict[str, object]:
    """Capture labelled scene context without applying or rendering a P4 joint state."""

    output_dir = Path(DIAGNOSTIC_OUTPUT).parent / "screenshots"
    trajectory = getattr(parameter_node, "trajectoryLine", None)
    focus_nodes = [
        getattr(parameter_node, "teethSegmentation", None),
        trajectory,
        getattr(parameter_node, "finalPrintableTemplateModel", None),
    ]
    source_indexes = [
        str(branch.get("source_candidate_index"))
        for branch in report.get("branches", ())
        if isinstance(branch, dict) and branch.get("status") == "COMPLETE"
    ]
    witness = ",".join(source_indexes) if source_indexes else "none"
    evidence: dict[str, object] = {
        "mode": "scene_context_only",
        "joint_state_display": "No P4 recovered J1-J5 state was applied or rendered.",
        "captures": [],
        "capture_errors": [],
    }
    for stem, label, camera_nodes in (
        (
            "p4-scene-context",
            "P4 INSERTION DIAGNOSTIC | r4 scene context | "
            f"result={report.get('result')} | witness source={witness} | "
            "scene-only; no diagnostic J1-J5 state rendered",
            focus_nodes,
        ),
        (
            "p4-guide-trajectory",
            "P4 INSERTION DIAGNOSTIC | locked r4 guide / Entry-to-Target context | "
            "scene-only; no diagnostic J1-J5 state rendered",
            [trajectory, getattr(parameter_node, "finalPrintableTemplateModel", None)],
        ),
    ):
        try:
            capture = _capture_view(
                slicer,
                output_dir / f"{stem}.png",
                focus_nodes,
                label=label,
                camera_nodes=camera_nodes,
            )
            evidence["captures"].append(capture)
        except Exception as exc:
            evidence["capture_errors"].append(
                f"{stem}: {type(exc).__name__}: {exc}"
            )
    evidence["status"] = (
        "CAPTURED"
        if evidence["captures"]
        and all(capture.get("nonblank_machine_check") for capture in evidence["captures"])
        else "UNAVAILABLE"
    )
    return evidence


def p4_insertion_diagnostic(facade, logic, parameter_node, snapshot) -> dict[str, object]:
    """Run exactly the bounded P4 continuation experiment and nothing downstream."""

    input_path, input_payload, input_candidates, input_sha256 = _p4_insertion_input()
    if (
        input_payload.get("task_fingerprint") != snapshot.snapshot_fingerprint
        or input_payload.get("tcp_frame") != snapshot.tool_frame
        or input_payload.get("tcp_provenance") != snapshot.tool_provenance
        or tuple(input_payload.get("entry_ras_mm") or ())
        != tuple(snapshot.entry_ras_mm)
        or tuple(input_payload.get("target_ras_mm") or ())
        != tuple(snapshot.target_ras_mm)
        or input_payload.get("tolerances") != {"position_mm": 0.25, "axis_deg": 0.5}
    ):
        raise RuntimeError("P4 input no longer matches the locked r4 task/TCP/tolerance identity.")
    native_build = _p4_runtime_native_build_identity()
    if not native_build.get("matches_p4_runtime_build"):
        raise RuntimeError("P4 native guard source/binary identity is unavailable or changed after launcher preflight.")
    robot_node = bridge.find_ros2_robot_by_name(bridge.ROS2_ROBOT_NAME)
    if robot_node is None:
        raise RuntimeError("P4 insertion could not find the simulation ROS robot.")
    ranges = _p3_runtime_joint_ranges(robot_node)
    if not _p4_ranges_match(input_payload.get("active_joint_ranges"), ranges):
        raise RuntimeError("P4 active joint ranges/types differ from corrected P3 evidence.")
    representatives = _p4_select_representatives(input_candidates, ranges)
    if not representatives:
        raise RuntimeError("P4 found no retained corrected P3 target representative.")
    if len(representatives) > P4_MAX_REPRESENTATIVES:
        raise RuntimeError("P4 representative selection exceeded its fixed bound.")
    budget = {"ik_solve_count": 0}
    branches = []
    for representative in representatives:
        source_index = int(representative["source_candidate_index"])
        request_prefix = f"p4-r4-{uuid4().hex}-source-{source_index}"
        target_positions = dict(representative["target_joint_positions_si"])
        if budget["ik_solve_count"] >= P4_MAX_IK_SOLVES:
            branches.append(
                {
                    "source_candidate_index": source_index,
                    "cluster_index": int(representative["cluster_index"]),
                    "status": "INCONCLUSIVE",
                    "reason": "P4 global IK-solve cap reached before this candidate.",
                }
            )
            continue
        guard_ready, guard_message = facade._configure_phase_guard(
            parameter_node, snapshot, static_only=True
        )
        if not guard_ready:
            branches.append(
                {
                    "source_candidate_index": source_index,
                    "cluster_index": int(representative["cluster_index"]),
                    "status": "INCONCLUSIVE",
                    "reason": "P4 Target guard setup failed: " + str(guard_message),
                }
            )
            continue
        target_scene_context = _p3_scene_context(
            logic,
            parameter_node,
            _p3_policy_context(facade),
            allow_deferred_static_ack=True,
        )
        target_static = _p3_static_state_query(
            target_positions,
            snapshot=snapshot,
            sequence=1,
            request_id=f"{request_prefix}-target-static",
            scene_context=target_scene_context,
        )
        branch = {
            "source_candidate_index": source_index,
            "cluster_index": int(representative["cluster_index"]),
            "p3_position_residual_mm": float(representative["position_residual_mm"]),
            "p3_axis_residual_deg": float(representative["axis_residual_deg"]),
            "p3_housing_status": representative["p3_housing_status"],
            "p3_housing_clearance_m": representative["p3_housing_clearance_m"],
            "target_joint_positions_si": target_positions,
            "target_static": target_static,
            "construction": None,
            "forward_validation": None,
            "status": target_static["classification"],
        }
        if target_static["classification"] != "ACCEPTED":
            branches.append(branch)
            continue
        construction = _p4_backward_continuation(
            robot_node,
            target_positions=target_positions,
            entry_ras_mm=tuple(snapshot.entry_ras_mm),
            target_ras_mm=tuple(snapshot.target_ras_mm),
            ranges=ranges,
            base_transform=parameter_node.robotBaseTransform,
            budget=budget,
        )
        branch["construction"] = construction
        if construction["status"] != "COMPLETE":
            branch["status"] = construction["status"]
            branches.append(branch)
            continue
        forward_states = list(reversed(construction["backward_states"]))
        if any(
            float(later["fraction"]) + 1.0e-12 < float(earlier["fraction"])
            for earlier, later in zip(forward_states, forward_states[1:])
        ):
            branch["status"] = "INCONCLUSIVE"
            branch["reason"] = "P4 recovered path reversed into non-monotonic drilling depth."
            branches.append(branch)
            continue
        forward = _p4_forward_guard_validation(
            facade,
            logic,
            parameter_node,
            snapshot,
            forward_states=forward_states,
            request_prefix=request_prefix,
        )
        branch["forward_validation"] = forward
        branch["forward_states"] = forward_states
        branch["status"] = forward["status"]
        branches.append(branch)
    statuses = [str(branch.get("status") or "INCONCLUSIVE") for branch in branches]
    result = (
        "SAMPLED_PASS"
        if any(status == "COMPLETE" for status in statuses)
        else "INCONCLUSIVE"
        if budget["ik_solve_count"] >= P4_MAX_IK_SOLVES or any(
            status == "INCONCLUSIVE" for status in statuses
        )
        else "NO_VALID_SOLUTION_FOUND_IN_BOUNDED_CONTINUATION"
    )
    report = {
        "mode": "p4_insertion_r4",
        "result": result,
        "is_executable_motion_plan": False,
        "case": str(PACKAGE),
        "case_sha256": P3_R4_CASE_SHA256,
        "input": {
            "path": str(input_path),
            "sha256": input_sha256,
            "p3_raw_sha256": input_payload.get("source_evidence", {}).get("sha256"),
            "p3_original_input_sha256": input_payload.get("input_sha256"),
            "input_native_build_identity": input_payload.get("native_build_identity"),
        },
        "task_fingerprint": str(snapshot.snapshot_fingerprint),
        "task_snapshot": _p3_jsonable(snapshot),
        "tcp_frame": str(snapshot.tool_frame),
        "tcp_provenance": str(snapshot.tool_provenance),
        "entry_ras_mm": list(snapshot.entry_ras_mm),
        "target_ras_mm": list(snapshot.target_ras_mm),
        "tolerances": {"position_mm": 0.25, "axis_deg": 0.5},
        "active_joint_ranges": list(ranges),
        "native_build_identity": native_build,
        "representative_limit": P4_MAX_REPRESENTATIVES,
        "representative_count": len(representatives),
        "ik_solve_limit": P4_MAX_IK_SOLVES,
        "ik_solve_count": budget["ik_solve_count"],
        "maximum_axial_step_mm": P4_MAX_AXIAL_STEP_MM,
        "maximum_midpoint_refinements": P4_MAX_MIDPOINT_REFINEMENTS,
        "branches": branches,
        "forbidden_actions_observed": [
            "no MoveGroup/OMPL/path-planning request",
            "no workspace generation, preview, raw joint command stream, or applied joint motion",
            "no controller/hardware endpoint, spindle, patient, geometry, task, base, tool, limit, tolerance, or collision-policy change",
            "only locked r4 and corrected r4 P3 evidence inputs were read",
            "P4 ends before P5, Return Home, repeat, playback, or full-flow work",
        ],
    }
    report["visual_evidence"] = _p4_capture_visual_evidence(parameter_node, report)
    return report


def _p5_p4_input() -> tuple[Path, dict[str, object], dict[str, object], str]:
    """Load one complete P4 Entry witness without reopening P3 or a workspace."""

    path = Path(P5_APPROACH_INPUT)
    if not path.is_file():
        raise RuntimeError("P5 approach input is missing: " + str(path))
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != P5_INPUT_SHA256:
        raise RuntimeError("P5 approach input SHA-256 does not match locked P4 evidence.")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("P5 approach input is not valid JSON: " + str(exc)) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("P5 approach input must be a JSON object.")
    if (
        payload.get("mode") != "p4_insertion_r4"
        or payload.get("result") != "SAMPLED_PASS"
        or payload.get("case") != str(PACKAGE)
        or payload.get("case_sha256") != P3_R4_CASE_SHA256
    ):
        raise RuntimeError("P5 approach input is not the locked passing r4 P4 evidence.")
    task = payload.get("task_snapshot")
    if not isinstance(task, dict):
        raise RuntimeError("P5 approach input has no attributable P4 task snapshot.")
    ranges = payload.get("active_joint_ranges")
    if not isinstance(ranges, list) or len(ranges) != len(bridge.ROS2_JOINT_SI_ORDER):
        raise RuntimeError("P5 approach input has no complete P4 planning-joint ranges.")
    for branch in payload.get("branches") or ():
        if not isinstance(branch, dict) or branch.get("status") != "COMPLETE":
            continue
        source_index = branch.get("source_candidate_index")
        forward_states = branch.get("forward_states")
        forward = branch.get("forward_validation")
        if (
            not isinstance(source_index, int)
            or isinstance(source_index, bool)
            or not isinstance(forward_states, list)
            or len(forward_states) < 2
            or not isinstance(forward, dict)
            or forward.get("status") != "COMPLETE"
        ):
            continue
        entry = forward_states[0]
        if not isinstance(entry, dict):
            continue
        positions = _p3_canonical_solution(entry.get("joint_positions_si"))
        fk = entry.get("native_fk_evidence")
        pose = fk.get("world_ras_pose_mm") if isinstance(fk, dict) else None
        if positions is None or not isinstance(pose, list) or len(pose) != 4:
            continue
        if any(not isinstance(row, list) or len(row) != 4 for row in pose):
            continue
        return path, payload, branch, digest
    raise RuntimeError("P5 approach input has no complete, FK-attributed P4 Entry witness.")


def _p5_entry_rotation_ras(witness: dict[str, object]) -> tuple[tuple[float, ...], ...]:
    """Read the fixed P4 Entry orientation without deriving a new drill frame."""

    states = witness.get("forward_states") if isinstance(witness, dict) else None
    entry = states[0] if isinstance(states, list) and states else None
    fk = entry.get("native_fk_evidence") if isinstance(entry, dict) else None
    pose = fk.get("world_ras_pose_mm") if isinstance(fk, dict) else None
    try:
        rotation = tuple(
            tuple(float(pose[row][column]) for column in range(3))
            for row in range(3)
        )
    except (TypeError, ValueError, IndexError) as exc:
        raise RuntimeError("P5 P4 Entry FK orientation is malformed: " + str(exc)) from exc
    if not all(math.isfinite(value) for row in rotation for value in row):
        raise RuntimeError("P5 P4 Entry FK orientation is non-finite.")
    return rotation


def _p5_snapshot_from_monitored_start(logic, parameter_node, positions):
    """Build an ephemeral P5 identity; never save or apply a Task Home."""

    start = bridge.canonicalize_planning_joint_positions(positions)
    trajectory = logic.step6TrajectorySummary(parameter_node)
    if not trajectory.get("isValid"):
        raise RuntimeError("P5 requires the locked r4 Entry-to-Target trajectory.")
    return build_task_snapshot(
        target_segment_id=str(parameter_node.targetToothSegmentId or ""),
        trajectory_revision=logic.step6TrajectoryRevision(parameter_node),
        entry_ras_mm=trajectory["entryRas"],
        target_ras_mm=validate_simulation_target(
            trajectory["entryRas"], trajectory["targetRas"]
        ),
        base_fingerprint=logic.robotBaseFingerprint(parameter_node),
        home_fingerprint=fingerprint(
            {
                "mode": "p5_monitored_simulation_start_v1",
                "joint_names": list(bridge.ROS2_JOINT_SI_ORDER),
                "joint_positions_si": bridge.joint_si_vector(start),
            }
        ),
        limits_fingerprint=logic.step6TaskLimitsFingerprint(parameter_node),
        robot_profile_fingerprint=logic.robotProfileFingerprint(),
        tool_frame=str(parameter_node.step6ToolFrame),
        tool_provenance=SIMULATION_TOOL_PROVENANCE,
        corridor_radius_mm=float(parameter_node.step6TrajectoryCorridorRadiusMm),
    )


def _p5_snapshot_issues(snapshot, p4_snapshot: object) -> list[str]:
    """Allow only the explicit monitored-start identity delta from P4."""

    if not isinstance(p4_snapshot, dict):
        return ["P4 task snapshot is missing or malformed"]
    current = _p3_jsonable(snapshot)
    issues = []
    for name in (
        "schema_version",
        "target_segment_id",
        "trajectory_revision",
        "base_fingerprint",
        "limits_fingerprint",
        "robot_profile_fingerprint",
        "tool_frame",
        "tool_provenance",
    ):
        if p4_snapshot.get(name) != current.get(name):
            issues.append(f"P4/current task {name} differs")
    if not math.isclose(
        float(p4_snapshot.get("corridor_radius_mm", float("nan"))),
        float(current.get("corridor_radius_mm", float("nan"))),
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        issues.append("P4/current task corridor radius differs")
    for name in ("entry_ras_mm", "target_ras_mm"):
        prior = p4_snapshot.get(name)
        observed = current.get(name)
        if (
            not isinstance(prior, list)
            or not isinstance(observed, list)
            or len(prior) != 3
            or len(observed) != 3
            or any(
                not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1.0e-9)
                for left, right in zip(prior, observed)
            )
        ):
            issues.append(f"P4/current task {name} differs")
    return issues


def _p5_planner_identity() -> dict[str, object]:
    """Record the unchanged current single-planner configuration."""

    path = ROOT / "dentobot_moveit_config/config/ompl_planning.yaml"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {"available": False, "path": str(path), "error": str(exc)}
    text = raw.decode("utf-8", errors="replace")
    return {
        "available": "RRTConnectkConfigDefault" in text and "geometric::RRTConnect" in text,
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "configured_planner": "RRTConnectkConfigDefault",
        "configuration_changed": False,
    }


def _p5_validate_guard_edges(
    start_positions: dict[str, float],
    waypoints: tuple[dict[str, float], ...],
    *,
    phase: str,
    snapshot,
    first_sequence: int,
    request_prefix: str,
    scene_context: dict[str, object],
) -> dict[str, object]:
    """Retain every read-only P5 edge; P4's transition helper owns attribution."""

    current = bridge.canonicalize_planning_joint_positions(start_positions)
    edges = []
    for offset, requested in enumerate(waypoints):
        sequence = int(first_sequence) + offset
        requested = bridge.canonicalize_planning_joint_positions(requested)
        query = _p4_transition_query(
            current,
            requested,
            snapshot=snapshot,
            sequence=sequence,
            request_id=f"{request_prefix}-{phase}-edge-{offset + 1}",
            scene_context=scene_context,
            phase=phase,
        )
        edge = {
            "edge_index": offset + 1,
            "phase": str(phase),
            "sequence": sequence,
            "start_joint_positions_si": dict(current),
            "end_joint_positions_si": dict(requested),
            "query": query,
        }
        edges.append(edge)
        if query.get("classification") != "ACCEPTED":
            return {
                "status": str(query.get("classification") or "INCONCLUSIVE"),
                "edges": edges,
                "next_sequence": sequence + 1,
                "last_positions_si": dict(current),
                "first_rejected": edge,
            }
        current = requested
    return {
        "status": "COMPLETE",
        "edges": edges,
        "next_sequence": int(first_sequence) + len(waypoints),
        "last_positions_si": dict(current),
        "first_rejected": None,
    }


def _p5_finish(report: dict[str, object], result: str, message: str) -> dict[str, object]:
    report["result"] = str(result)
    report["message"] = str(message)
    report["raw_joint_command_stream_active_after"] = bool(
        getattr(bridge, "_slicer_joint_command_timer", None)
        and bridge._slicer_joint_command_timer.isActive()
    )
    report["adapter_native_positions_after"] = list(
        getattr(bridge, "_native_joint_positions", ())
    )
    before = report.get("adapter_native_positions_before")
    report["adapter_native_positions_unchanged"] = (
        isinstance(before, list)
        and _p3_exact_vector(before, report["adapter_native_positions_after"])
    )
    return report


def p5_approach_diagnostic(facade, logic, parameter_node) -> dict[str, object]:
    """Connect one monitored simulation start to one immutable P4 Entry witness."""

    input_path, p4_payload, witness, input_sha256 = _p5_p4_input()
    p5_native_build = _p5_runtime_native_build_identity()
    report: dict[str, object] = {
        "mode": "p5_approach_r4",
        "is_executable_motion_plan": False,
        "case": str(PACKAGE),
        "case_sha256": P3_R4_CASE_SHA256,
        "input": {
            "path": str(input_path),
            "sha256": input_sha256,
            "p4_task_fingerprint": p4_payload.get("task_fingerprint"),
            "p4_native_build_identity": p4_payload.get("native_build_identity"),
        },
        "p4_witness": {
            "source_candidate_index": witness.get("source_candidate_index"),
            "entry_joint_positions_si": _p3_canonical_solution(
                witness.get("forward_states", [{}])[0].get("joint_positions_si")
                if isinstance(witness.get("forward_states"), list)
                and witness.get("forward_states")
                and isinstance(witness.get("forward_states")[0], dict)
                else None
            ),
            "p4_forward_validation_status": (
                witness.get("forward_validation", {}).get("status")
                if isinstance(witness.get("forward_validation"), dict)
                else None
            ),
            "p4_forward_edge_count": len(
                witness.get("forward_validation", {}).get("edges", ())
            )
            if isinstance(witness.get("forward_validation"), dict)
            else None,
        },
        "native_build_identity": p5_native_build,
        "planner_identity": _p5_planner_identity(),
        "stage1_limits": {
            "p4_witness_limit": P5_MAX_P4_WITNESSES,
            "planning_attempts": P5_STAGE1_PLANNING_ATTEMPTS,
            "allowed_planning_time_sec": P5_STAGE1_ALLOWED_PLANNING_TIME_SEC,
        },
        "forbidden_actions_observed": [
            "no Task Home save/apply/reconfirmation or workspace generation",
            "no raw joint command stream, preview, applied joint motion, controller/hardware endpoint, spindle, or patient action",
            "no collision-policy, geometry, task, base, tool, limit, tolerance, or planner-configuration change",
            "only locked r4 and locked P4 evidence were read; no r7/r13/P2 input",
            "P5 ends before P6/P7, insertion preview, Return Home, playback, or full-flow work",
        ],
    }
    report["adapter_native_positions_before"] = list(
        getattr(bridge, "_native_joint_positions", ())
    )
    timer = getattr(bridge, "_slicer_joint_command_timer", None)
    report["raw_joint_command_stream_active_before"] = bool(
        timer is not None and timer.isActive()
    )
    if report["raw_joint_command_stream_active_before"]:
        return _p5_finish(
            report,
            "INCONCLUSIVE_RUNTIME_BOUNDARY",
            "P5 refused to plan while the raw joint command stream is active.",
        )
    if not p5_native_build.get("matches_p5_runtime_build"):
        return _p5_finish(
            report,
            "INCONCLUSIVE_NATIVE_BUILD_IDENTITY",
            "P5 native guard source/binary identity is unavailable or changed after launcher preflight.",
        )
    p4_native = p4_payload.get("native_build_identity")
    if not isinstance(p4_native, dict) or any(
        p4_native.get(name) != p5_native_build.get(name)
        for name in ("source_sha256", "binary_sha256")
    ):
        return _p5_finish(
            report,
            "INCONCLUSIVE_P4_BUILD_IDENTITY",
            "P5 native guard identity does not match the locked P4 witness.",
        )
    if not report["planner_identity"].get("available"):
        return _p5_finish(
            report,
            "INCONCLUSIVE_PLANNER_IDENTITY",
            "P5 could not verify the unchanged RRTConnect planner configuration.",
        )
    stack_status = _p3_jsonable(bridge.simulation_stack_status())
    report["simulation_stack_status"] = stack_status
    start = bridge.monitored_joint_positions_si()
    if not start:
        return _p5_finish(
            report,
            "INCONCLUSIVE_START_STATE_GATE",
            "P5 has no complete monitored /joint_states start vector.",
        )
    monitored_ok, monitored_message, monitored_observed, monitored_error = (
        bridge.wait_for_monitored_joint_positions_si(
            start,
            timeout_sec=P5_MONITORED_START_TIMEOUT_SEC,
        )
    )
    report["monitored_start"] = {
        "requested_joint_positions_si": dict(start),
        "stable": bool(monitored_ok),
        "message": str(monitored_message),
        "observed_joint_positions_si": dict(monitored_observed),
        "maximum_error": float(monitored_error),
    }
    if not monitored_ok:
        return _p5_finish(
            report,
            "INCONCLUSIVE_START_STATE_GATE",
            "P5 monitored simulation start is unavailable or unstable: " + str(monitored_message),
        )
    try:
        snapshot = _p5_snapshot_from_monitored_start(logic, parameter_node, start)
    except Exception as exc:
        return _p5_finish(
            report,
            "INCONCLUSIVE_TASK_IDENTITY",
            f"P5 could not construct its ephemeral monitored-start task identity: {type(exc).__name__}: {exc}",
        )
    report["task_snapshot"] = _p3_jsonable(snapshot)
    report["task_snapshot_origin"] = "ephemeral_r4_p5_monitored_simulation_start"
    report["task_home_snapshot_source"] = "not_saved_or_applied; monitored_simulation_start_only"
    issues = _p5_snapshot_issues(snapshot, p4_payload.get("task_snapshot"))
    report["p4_task_identity_issues"] = issues
    if issues:
        return _p5_finish(
            report,
            "INCONCLUSIVE_P4_WITNESS_IDENTITY",
            "P5 current task differs from the locked P4 witness: " + " | ".join(issues),
        )
    robot_node = bridge.find_ros2_robot_by_name(bridge.ROS2_ROBOT_NAME)
    if robot_node is None:
        return _p5_finish(
            report,
            "INCONCLUSIVE_RUNTIME_ROBOT",
            "P5 could not find the simulation ROS robot.",
        )
    try:
        ranges = _p3_runtime_joint_ranges(robot_node)
    except Exception as exc:
        return _p5_finish(
            report,
            "INCONCLUSIVE_JOINT_TOPOLOGY",
            f"P5 could not inspect runtime planning joints: {type(exc).__name__}: {exc}",
        )
    report["active_joint_ranges"] = list(ranges)
    if not _p4_ranges_match(p4_payload.get("active_joint_ranges"), ranges):
        return _p5_finish(
            report,
            "INCONCLUSIVE_JOINT_TOPOLOGY",
            "P5 active planning joint ranges/types differ from the locked P4 witness.",
        )
    entry_positions = _p3_canonical_solution(
        report["p4_witness"].get("entry_joint_positions_si")
    )
    if entry_positions is None:
        return _p5_finish(
            report,
            "INCONCLUSIVE_P4_WITNESS",
            "P5 selected P4 witness has no complete Entry joint vector.",
        )
    try:
        fixed_rotation_ras = _p5_entry_rotation_ras(witness)
        pre_entry, entry = logic.step6ApproachPoints(parameter_node, snapshot)
    except Exception as exc:
        return _p5_finish(
            report,
            "INCONCLUSIVE_APPROACH_GEOMETRY",
            f"P5 could not read the immutable PreEntry/Entry geometry: {type(exc).__name__}: {exc}",
        )
    report["pre_entry_ras_mm"] = list(pre_entry)
    report["entry_ras_mm"] = list(entry)
    report["p4_entry_fixed_rotation_ras"] = [list(row) for row in fixed_rotation_ras]
    guard_ready, guard_message = facade._configure_phase_guard(
        parameter_node,
        snapshot,
        static_only=True,
        preflight_start_positions_si=start,
    )
    report["guard_setup"] = {"ready": bool(guard_ready), "message": str(guard_message)}
    if not guard_ready:
        return _p5_finish(
            report,
            "INCONCLUSIVE_PHASE_GUARD_SETUP",
            "P5 read-only phase guard setup failed: " + str(guard_message),
        )
    scene_context = _p3_scene_context(
        logic,
        parameter_node,
        _p3_policy_context(facade),
        allow_deferred_static_ack=True,
    )
    start_static = _p3_static_state_query(
        dict(start),
        snapshot=snapshot,
        sequence=1,
        request_id=f"p5-r4-{uuid4().hex}-start-static",
        scene_context=scene_context,
        phase="approach",
    )
    report["start_static"] = start_static
    if start_static.get("classification") != "ACCEPTED":
        return _p5_finish(
            report,
            (
                "REJECTED_START_STATE_GATE"
                if start_static.get("classification") == "REJECTED"
                else "INCONCLUSIVE_START_STATE_GATE"
            ),
            "P5 native phase guard did not admit the monitored simulation start.",
        )
    candidates, ik_failures = facade._goal1_pre_entry_ik_candidates(
        parameter_node,
        pre_entry,
        entry,
        snapshot.target_ras_mm,
        entry_positions,
        include_workspace_seeds=False,
        avoid_collisions=False,
        require_generic_static=False,
        fixed_rotation_ras=fixed_rotation_ras,
    )
    report["pre_entry_ik"] = {
        "candidate_count": len(candidates),
        "candidate_limit": P5_MAX_P4_WITNESSES,
        "failures": list(ik_failures),
        "collision_policy": "authoritative_phase_guard_only_after_kinematic_FK_residual",
    }
    if not candidates:
        return _p5_finish(
            report,
            "NO_VALID_PREENTRY_IK_IN_BOUNDED_APPROACH",
            "P5 found no P4-Entry-seeded PreEntry position-axis IK state.",
        )
    candidate = candidates[0]
    report["pre_entry_ik"]["selected"] = _p3_jsonable(candidate)
    stage1 = bridge.plan_moveit_joint_goal(
        start_joint_positions_si=start,
        goal_joint_positions_si=candidate["positions"],
        refresh_planning_scene=True,
        planning_attempts=P5_STAGE1_PLANNING_ATTEMPTS,
        allowed_planning_time_sec=P5_STAGE1_ALLOWED_PLANNING_TIME_SEC,
        planner_context="p5_monitored_start_to_p4_seeded_preentry",
    )
    report["stage1_plan"] = _p3_jsonable(stage1)
    if not stage1.success or not stage1.waypoint_joint_vectors_si:
        return _p5_finish(
            report,
            "NO_ROUTE_WITHIN_P5_BOUND",
            "P5 Stage 1 found no monitored-start-to-PreEntry route within one current RRTConnect attempt.",
        )
    request_prefix = f"p5-r4-{uuid4().hex}-source-{witness['source_candidate_index']}"
    stage1_guard = _p5_validate_guard_edges(
        dict(start),
        tuple(stage1.waypoint_joint_vectors_si),
        phase="approach",
        snapshot=snapshot,
        # Sequence 1 belongs to the preceding static start query.  Keep the
        # complete P5 evidence stream strictly increasing even though the
        # native guard tracks static and transition sequences independently.
        first_sequence=2,
        request_prefix=request_prefix,
        scene_context=scene_context,
    )
    report["stage1_guard"] = stage1_guard
    if stage1_guard.get("status") != "COMPLETE":
        return _p5_finish(
            report,
            "REJECTED_STAGE1_GUARD"
            if stage1_guard.get("status") == "REJECTED"
            else "INCONCLUSIVE_STAGE1_GUARD",
            "P5 native guard did not accept every explicit Stage 1 edge.",
        )
    stage1_end = dict(stage1_guard["last_positions_si"])
    stage2 = bridge.plan_moveit_cartesian_path(
        entry_ras_mm=pre_entry,
        target_ras_mm=entry,
        sample_count=max(3, int(parameter_node.robotMotionPlanSampleCount)),
        base_transform=parameter_node.robotBaseTransform,
        avoid_collisions=False,
        minimum_fraction=1.0,
        start_joint_positions_si=stage1_end,
        fixed_rotation_ras=fixed_rotation_ras,
        position_axis_only=True,
        continuity_seed_positions_si=(),
    )
    report["stage2_plan"] = _p3_jsonable(stage2)
    if (
        not stage2.success
        or not stage2.waypoint_joint_vectors_si
        or not math.isclose(float(stage2.fraction), 1.0, rel_tol=0.0, abs_tol=1.0e-12)
    ):
        return _p5_finish(
            report,
            "INVALID_STAGE2_OR_INSERTION_CONSTRUCTION",
            "P5 could not construct a complete fixed-axis PreEntry-to-Entry Stage 2 witness.",
        )
    stage2_end = _p3_canonical_solution(stage2.waypoint_joint_vectors_si[-1])
    if stage2_end is None:
        return _p5_finish(
            report,
            "INCONCLUSIVE_STAGE2_ENDPOINT_ATTRIBUTION",
            "P5 Stage 2 returned no complete terminal J1-J5 state.",
        )
    drilling_axis = tuple(
        float(entry[index]) - float(pre_entry[index]) for index in range(3)
    )
    stage2_fk = _p3_native_fk_evidence(
        stage2_end,
        base_transform=parameter_node.robotBaseTransform,
    )
    stage2_residual = _p4_fk_residual(stage2_fk, tuple(entry), drilling_axis)
    report["stage2_endpoint"] = {
        "joint_positions_si": dict(stage2_end),
        "native_fk_evidence": stage2_fk,
        "fk_residual": stage2_residual,
    }
    if not stage2_residual.get("available"):
        return _p5_finish(
            report,
            "INCONCLUSIVE_STAGE2_ENDPOINT_ATTRIBUTION",
            "P5 could not attribute the actual Stage 2 endpoint to native TCP FK.",
        )
    if (
        float(stage2_residual["position_error_mm"]) > 0.25
        or float(stage2_residual["axis_error_deg"]) > 0.5
    ):
        return _p5_finish(
            report,
            "INVALID_STAGE2_OR_INSERTION_CONSTRUCTION",
            "P5 actual Stage 2 endpoint exceeds the frozen TCP position/axis tolerance.",
        )
    stage2_guard = _p5_validate_guard_edges(
        stage1_end,
        tuple(stage2.waypoint_joint_vectors_si),
        phase="terminal_contact",
        snapshot=snapshot,
        first_sequence=int(stage1_guard["next_sequence"]),
        request_prefix=request_prefix,
        scene_context=scene_context,
    )
    report["stage2_guard"] = stage2_guard
    if stage2_guard.get("status") != "COMPLETE":
        return _p5_finish(
            report,
            "REJECTED_STAGE2_GUARD"
            if stage2_guard.get("status") == "REJECTED"
            else "INCONCLUSIVE_STAGE2_GUARD",
            "P5 native guard did not accept every fixed-axis Stage 2 edge.",
        )
    p4_join = _p5_validate_guard_edges(
        dict(stage2_guard["last_positions_si"]),
        (entry_positions,),
        phase="terminal_contact",
        snapshot=snapshot,
        first_sequence=int(stage2_guard["next_sequence"]),
        request_prefix=request_prefix,
        scene_context=scene_context,
    )
    report["p4_entry_join_guard"] = p4_join
    if p4_join.get("status") != "COMPLETE":
        return _p5_finish(
            report,
            "REJECTED_P4_WITNESS_JOIN"
            if p4_join.get("status") == "REJECTED"
            else "INCONCLUSIVE_P4_WITNESS_JOIN",
            "P5 could not validate the final Stage 2 to saved-P4-Entry join.",
        )
    return _p5_finish(
        report,
        "SAMPLED_PASS",
        "P5 connected the fresh monitored simulation start through PreEntry and Stage 2 to one immutable P4 Entry witness; P4 retains the separate accepted Entry-to-Target proof.",
    )


def target_fdi(parameter_node) -> str:
    trajectory = getattr(parameter_node, "trajectoryLine", None)
    if trajectory is None:
        return ""
    return str(trajectory.GetAttribute("DENTOBOT.TargetFdiNumber") or "").strip()


def require_trajectory_guide_bore(parameter_node) -> dict[str, float]:
    minimum_mm = 2.0
    channel_mm = float(parameter_node.templateChannelDiameterMm)
    sleeve_inner_mm = float(parameter_node.templateSleeveInnerDiameterMm)
    if channel_mm < minimum_mm or sleeve_inner_mm < minimum_mm:
        raise RuntimeError(
            "saved trajectory-guide bore is below the required 2.0 mm: "
            f"channel={channel_mm:.3f} mm, sleeve={sleeve_inner_mm:.3f} mm"
        )
    return {
        "channelDiameterMm": channel_mm,
        "sleeveInnerDiameterMm": sleeve_inner_mm,
        "minimumRequiredMm": minimum_mm,
    }


def require_current_saved_case(inspection, expected_fdi: str) -> dict[str, object]:
    """Reject a legacy/partial save before reporting planner acceptance."""

    workflow = inspection.workflow
    step6 = workflow.get("step6")
    errors = []
    if str(inspection.manifest.get("schemaVersion") or "") != CASE_BUNDLE_SCHEMA_VERSION:
        errors.append(
            "outer case-bundle schema must be " + CASE_BUNDLE_SCHEMA_VERSION
        )
    trajectory_nodes = [
        node
        for node in workflow.get("nodes", ())
        if isinstance(node, dict) and node.get("field") == "trajectoryLine"
    ]
    workflow_fdi = ""
    if trajectory_nodes:
        attributes = trajectory_nodes[0].get("attributes", {})
        workflow_fdi = str(attributes.get("DENTOBOT.TargetFdiNumber") or "").strip()
        if not workflow_fdi:
            match = re.search(r"\bFDI\s*(\d+)", str(trajectory_nodes[0].get("name") or ""), re.I)
            workflow_fdi = match.group(1) if match else ""
    if not workflow_fdi:
        errors.append("saved trajectory has no target FDI identity")
    elif workflow_fdi.removeprefix("FDI") != str(expected_fdi or "").removeprefix("FDI"):
        errors.append(
            "saved trajectory target FDI is "
            + workflow_fdi
            + ", expected "
            + str(expected_fdi or "unknown")
        )
    if str(workflow.get("schemaVersion") or "") != DENTOCASE_STATE_SCHEMA_VERSION:
        errors.append(
            "workflow schema must be " + DENTOCASE_STATE_SCHEMA_VERSION
        )
    if not isinstance(step6, dict):
        errors.append("current Step 6 state is missing")
        step6 = {}
    environment = step6.get("environment")
    if not isinstance(environment, dict) or str(
        environment.get("schema_version") or ""
    ) != ROBOT_ENVIRONMENT_SCHEMA_VERSION:
        errors.append(
            "Case Foundation environment schema must be "
            + ROBOT_ENVIRONMENT_SCHEMA_VERSION
        )
    registry = step6.get("trajectoryRegistry")
    if not isinstance(registry, dict) or str(
        registry.get("schema_version") or ""
    ) != TRAJECTORY_REGISTRY_SCHEMA_VERSION:
        errors.append(
            "PreparedBranch registry schema must be "
            + TRAJECTORY_REGISTRY_SCHEMA_VERSION
        )
        registry = {}
    if step6.get("freshnessIssuesAtSave") != []:
        errors.append("save-time Step 6 freshness issues are present")
    branches = registry.get("prepared_branches")
    if not isinstance(branches, dict) or len(branches) != 1:
        errors.append("saved case must contain exactly one PreparedBranch")
        branches = {}
    selected_branch_id = str(registry.get("selected_branch_id") or "")
    branch = branches.get(selected_branch_id)
    if not isinstance(branch, dict):
        errors.append("saved selected PreparedBranch is missing")
        branch = {}
    if str(branch.get("state") or "") != "Current":
        errors.append("saved PreparedBranch is not current")
    for field in ("planning_pose_fingerprint", "verification_revision"):
        if not str(branch.get(field) or ""):
            errors.append(f"saved PreparedBranch lacks {field}")
    final_templates = [
        node
        for node in workflow.get("nodes", ())
        if isinstance(node, dict)
        and node.get("field") == "finalPrintableTemplateModel"
    ]
    final_attributes = (
        final_templates[0].get("attributes", {})
        if final_templates
        else {}
    )
    if str(final_attributes.get("DENTOBOT.FinalGuideSchemaVersion") or "") != "2.0":
        errors.append("Step 5C final guide schema must be 2.0")
    if str(final_attributes.get("DENTOBOT.VerificationState") or "") not in {
        "PASS",
        "WARNING",
    }:
        errors.append("Step 5C final guide is not verified")
    if errors:
        raise RuntimeError("saved current-case contract failed: " + "; ".join(errors))
    return {
        "workflowSchema": workflow.get("schemaVersion"),
        "environmentSchema": environment.get("schema_version"),
        "registrySchema": registry.get("schema_version"),
        "selectedBranchId": selected_branch_id,
        "preparedBranchCount": len(branches),
        "preparedBranchRevision": branch.get("revision"),
        "step5cGuideSchema": final_attributes.get(
            "DENTOBOT.FinalGuideSchemaVersion"
        ),
        "step5cVerificationState": final_attributes.get(
            "DENTOBOT.VerificationState"
        ),
        "expectedFdi": str(expected_fdi or "").removeprefix("FDI"),
        "savedFdi": workflow_fdi.removeprefix("FDI"),
    }


def base_point_m_to_world_ras_mm(point, base_transform):
    if point is None:
        return None
    matrix = vtk.vtkMatrix4x4()
    if base_transform.GetMatrixTransformToWorld(matrix) is False:
        return None
    source = [1000.0 * float(value) for value in point] + [1.0]
    target = [0.0, 0.0, 0.0, 0.0]
    matrix.MultiplyPoint(source, target)
    return [float(target[index]) for index in range(3)]


def capture_fdi21_contact_from_below(facade, diagnostic_payload):
    """Capture the isolated FDI21/spindle rejection from useful viewpoints."""

    records = diagnostic_payload.get("candidate_records", ())
    record = next(
        (
            item for item in records
            if isinstance(item, dict)
            and "71ddde60" in str(item.get("full_chain_guard_message") or "")
            and isinstance(item.get("first_invalid_joint_positions_si"), dict)
        ),
        None,
    )
    if record is None:
        raise RuntimeError("No retained FDI21/spindle rejected waypoint is available.")
    shown, message = facade._bridge.show_goal_robot_joint_positions(
        record["first_invalid_joint_positions_si"]
    )
    if not shown:
        raise RuntimeError("show rejected FDI21 state: " + message)

    fdi21_id = str(record.get("guard_first_body") or "")
    target_id = facade._logic.step6TargetCollisionObjectId(facade._require_context())
    for node in slicer.util.getNodesByClass("vtkMRMLDisplayableNode"):
        display = node.GetDisplayNode()
        if display is not None:
            display.SetVisibility(False)
    for node in slicer.util.getNodesByClass("vtkMRMLSliceNode"):
        node.SetSliceVisible(False)

    visible = []
    focus_nodes = []
    fdi21_node = None
    spindle_node = None
    for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
        display = node.GetDisplayNode()
        if display is None:
            continue
        display.SetVisibility(False)
        object_id = str(node.GetAttribute("DENTOBOT.OutgoingCollisionObjectId") or "")
        name = str(node.GetName() or "").lower()
        if node.GetAttribute("DENTOBOT.CollisionAuditCopy") == "true" and object_id == fdi21_id:
            display.SetVisibility(True); display.SetColor(1.0, 0.05, 0.05); display.SetOpacity(0.55)
            display.SetEdgeVisibility(True); display.SetEdgeColor(0.35, 0.0, 0.0); visible.append(node); focus_nodes.append(node)
            fdi21_node = node
        elif node.GetAttribute("DENTOBOT.CollisionAuditCopy") == "true" and object_id == target_id:
            display.SetVisibility(True); display.SetColor(0.1, 0.9, 0.2); display.SetOpacity(0.12)
            display.SetEdgeVisibility(True); display.SetEdgeColor(0.0, 0.35, 0.0); visible.append(node); focus_nodes.append(node)
        elif "pneumatic-spindle-copy_model_0_goal" in name or "pneumatic_spindle-copy_model_0_goal" in name:
            display.SetVisibility(True); display.SetColor(1.0, 0.45, 0.0); display.SetOpacity(0.6)
            display.SetEdgeVisibility(True); display.SetEdgeColor(0.35, 0.12, 0.0); visible.append(node)
            spindle_node = node
        elif "burr_model_0_goal" in name:
            display.SetVisibility(True); display.SetColor(1.0, 1.0, 0.0); display.SetOpacity(1.0)
            visible.append(node)
    if len(visible) < 3:
        raise RuntimeError("Could not isolate FDI21, FDI11, and the rejected spindle model.")

    intersection = vtk.vtkIntersectionPolyDataFilter()
    intersection.SetInputData(0, model_polydata_in_world(fdi21_node))
    intersection.SetInputData(1, model_polydata_in_world(spindle_node))
    intersection.Update()
    if intersection.GetOutput().GetNumberOfPoints() > 0:
        contact = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "FDI21 spindle mesh intersection")
        contact.SetAndObservePolyData(intersection.GetOutput())
        contact.CreateDefaultDisplayNodes()
        contact.GetDisplayNode().SetColor(1.0, 1.0, 0.0)
        contact.GetDisplayNode().SetLineWidth(8.0)
        contact.GetDisplayNode().SetVisibility(True)

    layout = slicer.app.layoutManager()
    layout.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView)
    process_events(0.5)
    view = layout.threeDWidget(0).threeDView()
    view.mrmlViewNode().SetAxisLabelsVisible(False)
    camera = view.cameraNode().GetCamera()
    bounds = [float("inf"), float("-inf"), float("inf"), float("-inf"), float("inf"), float("-inf")]
    for node in focus_nodes:
        current = [0.0] * 6
        node.GetRASBounds(current)
        for axis in range(3):
            bounds[2 * axis] = min(bounds[2 * axis], current[2 * axis])
            bounds[2 * axis + 1] = max(bounds[2 * axis + 1], current[2 * axis + 1])
    center = [(bounds[2*i] + bounds[2*i+1]) / 2.0 for i in range(3)]
    distance = max(bounds[1]-bounds[0], bounds[3]-bounds[2], bounds[5]-bounds[4]) * 1.7
    output = Path("/workspace/data/dentobot-runs/fdi21-blocker-20260909")
    output.mkdir(parents=True, exist_ok=True)
    views = {
        "bottom-inferior": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
        "root-apical": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
        "palatal-bottom-oblique": ((0.0, 0.75, -0.66), (0.0, 0.66, 0.75)),
    }
    screenshots = []
    for label, (direction, view_up) in views.items():
        camera.SetFocalPoint(*center)
        camera.SetPosition(*(center[i] + distance * direction[i] for i in range(3)))
        camera.SetViewUp(*view_up)
        camera.SetParallelProjection(True)
        camera.SetParallelScale(distance * 0.36)
        view.forceRender(); process_events(0.2)
        path = output / f"fdi21-contact-{label}.png"
        slicer.util.forceRenderAllViews()
        pixmap = view.grab()
        if not pixmap.save(str(path)):
            raise RuntimeError(f"Could not save {path}")
        screenshots.append(str(path))
    print("DENTOBOT_FDI21_BOTTOM_CAPTURE_PASS " + json.dumps({
        "candidate_index": record.get("candidate_index"),
        "collision_pair": [record.get("guard_first_body"), record.get("guard_second_body")],
        "screenshots": screenshots,
    }), flush=True)
    return screenshots


def preview_repeat_phase(facade, phase: str, waypoint_count: int):
    """Run one acknowledged repeat preview and retain bounded failure context."""

    finished = []
    progress = []
    require_success(
        facade.previewPhase(
            phase,
            interval_ms=50,
            on_progress=lambda index, total: progress.append((int(index), int(total))),
            on_finished=finished.append,
        ),
        f"start repeated {phase} preview",
    )
    if wait_until(lambda: finished, PREVIEW_TIMEOUT_SEC) is None:
        raise RuntimeError(
            f"Repeated {phase} preview timed out at "
            f"{progress[-1] if progress else (0, waypoint_count)}; "
            f"previewActive={facade.previewActive}, sequence={facade._phase_sequence}, "
            f"lastGuardStatus={bridge._last_task_status}"
        )
    return require_success(finished[-1], f"repeat {phase} preview")


def audit_actual_moveit_contacts(facade, diagnostic_payload: dict[str, object]):
    """Audit retained candidate paths without the separate 1 mm phase margin.

    This is intentionally a harness-only diagnostic.  It asks MoveIt to check
    each already-generated explicit joint state against its synchronized scene;
    it neither applies a waypoint nor starts guarded preview.  The normal
    Step-6 phase guard is deliberately *not* called here because its provisional
    non-target-tooth clearance envelope is the condition being classified.
    """

    records = diagnostic_payload.get("candidate_records", ())
    if not isinstance(records, list):
        records = ()
    outcomes = []
    for candidate_index, paths in sorted(facade._diagnostic_candidate_paths.items()):
        record = (
            records[candidate_index]
            if 0 <= int(candidate_index) < len(records)
            and isinstance(records[candidate_index], dict)
            else {}
        )
        stages = {}
        for stage in ("stage1", "stage2", "stage3"):
            waypoints = tuple(paths.get(stage, ()))
            valid_count = 0
            first_invalid = None
            for waypoint_index, positions in enumerate(waypoints):
                valid, message, authoritative = bridge.check_moveit_static_joint_state(
                    positions,
                    timeout_sec=2.0,
                )
                if not authoritative or not valid:
                    first_invalid = {
                        "waypoint_index": waypoint_index,
                        "authoritative": authoritative,
                        "message": message,
                    }
                    break
                valid_count += 1
            stages[stage] = {
                "waypoint_count": len(waypoints),
                "moveit_actual_mesh_valid_count": valid_count,
                "first_moveit_actual_mesh_invalid": first_invalid,
                "all_moveit_actual_mesh_valid": (
                    bool(waypoints) and first_invalid is None
                ),
            }
        outcomes.append(
            {
                "candidate_index": int(candidate_index),
                "route_type": record.get("route_type"),
                "ik_seed_sample_index": record.get("ik_seed_sample_index"),
                "housing_roll_deg": record.get("axial_roll_deg"),
                "full_chain_status": record.get("full_chain_candidate_status"),
                "stage2_fraction": record.get("stage2_fraction"),
                "stage3_fraction": record.get("stage3_fraction"),
                "phase_guard_margin_first_body": record.get("guard_first_body"),
                "phase_guard_margin_second_body": record.get("guard_second_body"),
                "phase_guard_minimum_distance_mm": (
                    None
                    if record.get("guard_minimum_world_distance_m") is None
                    else 1000.0 * float(record["guard_minimum_world_distance_m"])
                ),
                "stages": stages,
            }
        )
    return outcomes


def run() -> dict[str, object]:
    if not PACKAGE.is_file():
        raise RuntimeError(f"exact operator package is missing: {PACKAGE}")
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    if widget is None:
        raise RuntimeError("DENTOWorkflow widget is unavailable")
    widget._applyDENTOBOTGuiMode("legacy", persist=False)
    widget._openCaseBundle(PACKAGE)
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    parameter_node = widget._parameterNode
    logic = widget.logic
    facade = widget._robotWorkflowFacade
    if parameter_node is None or logic is None or facade is None:
        raise RuntimeError("restored Step 6 workflow services are unavailable")
    actual_fdi = target_fdi(parameter_node)
    if EXPECTED_FDI and actual_fdi != EXPECTED_FDI.removeprefix("FDI"):
        raise RuntimeError(
            f"expected FDI {EXPECTED_FDI}, restored trajectory is FDI {actual_fdi or 'unknown'}"
        )
    guide_bore = require_trajectory_guide_bore(parameter_node)
    if slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"):
        raise RuntimeError("the package serialized a transient ROS robot")
    package_issues = logic.step6PlanningPackageFreshnessIssues(parameter_node)
    jaw_issues = logic.step6CaseJawOpeningFreshnessIssues(parameter_node)
    home_issues = logic.taskHomeFreshnessIssues(parameter_node)
    # A current FDI31 package may intentionally stop at the offline Case
    # Foundation/base gate.  Missing Task Home is the normal 6.1 -> 6.2
    # transition and is created only after the live ROS/MoveIt runtime is
    # connected below.  Existing, malformed, or mismatched Home records still
    # fail closed here.
    home_record_at_restore = logic.taskHomeRecord(parameter_node)
    missing_home_at_restore = (
        home_record_at_restore is None
        and len(home_issues) == 1
        and "case/base-specific Task Home" in str(home_issues[0])
    )
    migration_home_issues = tuple(
        issue for issue in home_issues if "different robot resources" in str(issue).lower()
    )
    blocking_home_issues = tuple(
        issue
        for issue in home_issues
        if issue not in migration_home_issues
        and not (missing_home_at_restore and issue == home_issues[0])
    )
    task_issues = logic.confirmedTaskFreshnessIssues(parameter_node)
    # A saved task snapshot may intentionally become stale after a robot-profile
    # migration (for example the J2/J5 URDF update).  Geometry/jaw/home
    # corruption is still a hard restore failure, but the immutable snapshot
    # is expected to be explicitly reconfirmed after the live runtime is
    # reconstructed below.
    if package_issues or jaw_issues or blocking_home_issues:
        raise RuntimeError(
            "restored exact-case prerequisites are stale: "
            + " | ".join(
                " ".join(group)
                for group in (package_issues, jaw_issues, blocking_home_issues)
                if group
            )
        )
    # Case restore deliberately does not reactivate a PreparedBranch or live
    # Step 6 context.  Perform the same explicit production import that the
    # operator uses before Connect; registry eligibility alone is not active
    # branch state.
    if not bool(parameter_node.step6PlanningContextImported):
        try:
            planning_context = logic.importStep6PlanningContext(parameter_node)
        except (RuntimeError, ValueError) as exc:
            raise RuntimeError(
                "activate the verified PreparedBranch: " + str(exc)
            ) from exc
        if not planning_context.ready:
            raise RuntimeError(
                "activate the verified PreparedBranch: "
                + str(planning_context.message)
            )
    if not bool(parameter_node.step6PlanningContextImported):
        raise RuntimeError("verified PreparedBranch activation did not persist")
    restored_snapshot = logic.confirmedTaskRecord(parameter_node)
    restored_task_before_runtime = (
        restored_snapshot.snapshot_fingerprint if restored_snapshot is not None else ""
    )
    if not parameter_node.robotBaseMountLocked:
        raise RuntimeError("restored x4 robot base is not provisionally locked")

    require_success(facade.loadRobot(), "load local robot")
    if abs(BASE_LOCAL_Z_OFFSET_MM) > 1.0e-12:
        require_success(facade.unlockBase(), "unlock base for diagnostic offset")
        logic.nudgeRobotBase(
            parameter_node.robotBaseTransform,
            translationLocalMm=(0.0, 0.0, BASE_LOCAL_Z_OFFSET_MM),
        )
        # Let the placement observer consume the pose change while the base is
        # still intentionally unlocked.  Locking before this event is handled
        # can make the observer correctly treat the delayed change as stale.
        process_events(0.25)
        # The normal-window operator naturally leaves an event-loop turn
        # between clicking Nudge and Lock.  The headless harness must make the
        # placement observer's pose baseline explicit before issuing Lock;
        # otherwise a queued ModifiedEvent can invalidate the newly locked
        # state after the fact.
        widget._lastRobotBasePoseFingerprint = logic.robotBasePoseFingerprint(
            parameter_node.robotBaseTransform
        )
        require_success(facade.lockBase(), "lock diagnostically offset base")
        process_events(0.25)
        if not parameter_node.robotBaseMountLocked:
            raise RuntimeError("diagnostically offset robot base did not remain locked")
    if ENDPOINT_ONLY or INSERTION_ONLY or APPROACH_ONLY:
        # P3/P4/P5 diagnostics must never enter the normal Connect/Task Home path:
        # it applies raw joint commands and can plan a Home transition.
        diagnostic_name = (
            "P3 endpoint"
            if ENDPOINT_ONLY
            else "P4 insertion"
            if INSERTION_ONLY
            else "P5 approach"
        )
        if APPROACH_ONLY:
            # P5 builds its identity only after observing the fresh simulated
            # /joint_states vector below. It must not substitute or apply a
            # saved Task Home merely to obtain a planner start state.
            diagnostic_runtime = _p3_connect_static_runtime(
                facade, logic, parameter_node
            )
            endpoint_diagnostic = p5_approach_diagnostic(
                facade, logic, parameter_node
            )
            endpoint_diagnostic["confirmed_task_freshness_issues"] = list(task_issues)
            endpoint_diagnostic["runtime_initialization"] = diagnostic_runtime
            Path(DIAGNOSTIC_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
            Path(DIAGNOSTIC_OUTPUT).write_text(
                json.dumps(endpoint_diagnostic, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            return endpoint_diagnostic
        snapshot = restored_snapshot
        snapshot_origin = "restored_r4_confirmation"
        task_home_snapshot_source = "confirmed_task_snapshot"
        if snapshot is None:
            expected_missing_confirmation = "Confirm the immutable Step 6 task snapshot."
            unexpected_issues = tuple(
                issue for issue in task_issues if str(issue) != expected_missing_confirmation
            )
            if unexpected_issues:
                if ENDPOINT_ONLY:
                    raise RuntimeError(
                        "P3 endpoint check has non-confirmation task freshness issues: "
                        + " | ".join(str(issue) for issue in unexpected_issues)
                    )
                raise RuntimeError(
                    diagnostic_name
                    + " check has non-confirmation task freshness issues: "
                    + " | ".join(str(issue) for issue in unexpected_issues)
                )
            home = logic.taskHomeRecord(parameter_node)
            # Neither P3 static endpoint validation nor P4's recovered insertion
            # construction traverses Home. r4 has no persisted Task Home, so
            # retain a deterministic no-Home identity rather than creating,
            # applying, or reading any Home transition.
            home_fingerprint = (
                fingerprint(home.to_dict())
                if home is not None
                else fingerprint({"mode": "static_state_only_no_task_home"})
            )
            trajectory = logic.step6TrajectorySummary(parameter_node)
            snapshot = build_task_snapshot(
                target_segment_id=str(parameter_node.targetToothSegmentId or ""),
                trajectory_revision=logic.step6TrajectoryRevision(parameter_node),
                entry_ras_mm=trajectory["entryRas"],
                target_ras_mm=validate_simulation_target(
                    trajectory["entryRas"], trajectory["targetRas"]
                ),
                base_fingerprint=logic.robotBaseFingerprint(parameter_node),
                home_fingerprint=home_fingerprint,
                limits_fingerprint=logic.step6TaskLimitsFingerprint(parameter_node),
                robot_profile_fingerprint=logic.robotProfileFingerprint(),
                tool_frame=str(parameter_node.step6ToolFrame),
                tool_provenance=SIMULATION_TOOL_PROVENANCE,
                corridor_radius_mm=float(parameter_node.step6TrajectoryCorridorRadiusMm),
            )
            snapshot_origin = (
                "ephemeral_r4_p3_static_snapshot"
                if ENDPOINT_ONLY
                else "ephemeral_r4_p4_insertion_snapshot"
            )
            task_home_snapshot_source = (
                "saved_task_home"
                if home is not None
                else (
                    "not_required_for_static_state_only"
                    if ENDPOINT_ONLY
                    else "not_required_for_read_only_diagnostic"
                )
            )
        # Create only the simulation-local guard/FK dependencies after the
        # immutable diagnostic task identity is available; its raw stream remains
        # disabled throughout P3 and P4.
        diagnostic_runtime = _p3_connect_static_runtime(
            facade, logic, parameter_node
        )
        if ENDPOINT_ONLY:
            endpoint_diagnostic = endpoint_only_diagnostic(
                facade, logic, parameter_node, snapshot
            )
        else:
            endpoint_diagnostic = p4_insertion_diagnostic(
                facade, logic, parameter_node, snapshot
            )
        endpoint_diagnostic["task_snapshot_origin"] = snapshot_origin
        endpoint_diagnostic["task_home_snapshot_source"] = task_home_snapshot_source
        endpoint_diagnostic["confirmed_task_freshness_issues"] = list(task_issues)
        endpoint_diagnostic["runtime_initialization"] = diagnostic_runtime
        Path(DIAGNOSTIC_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
        Path(DIAGNOSTIC_OUTPUT).write_text(
            json.dumps(endpoint_diagnostic, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return endpoint_diagnostic
    selected_before_connect = slicer.util.selectedModule()
    connection = facade.connect(open_motion_module=False)
    task_home_remediated = False
    if not connection.success:
        if (
            connection.code != "task_home_scene_invalid_runtime_connected"
            or not facade.capabilities().connected
        ):
            raise RuntimeError(f"connect ROS/MoveIt: {connection.message}")
        # The x4 package intentionally remains immutable on disk.  Exercise the
        # same explicit operator recovery offered by 6.2: the rejected home has
        # already restored the current guard-accepted joint vector in the UI.
        require_success(facade.saveTaskHome(), "save remediated Task Home")
        require_success(facade.applyTaskHome(), "validate remediated Task Home")
        require_success(facade.confirmTask(), "confirm remediated task")
        task_home_remediated = True
    connected = connection
    # Rebuild the live evidence invalidated by the saved package's robot
    # profile or by the normal foundation-only starting state.  This follows
    # the normal 6.2→6.4 operator sequence; it is intentionally not an
    # automatic connect/restore action.
    if not facade.taskHomeRuntimeValidated(parameter_node):
        require_success(facade.saveTaskHome(), "save migrated Task Home")
        require_success(facade.applyTaskHome(), "apply migrated Task Home")
    if not facade.workspaceRuntimeValidated(parameter_node):
        require_success(facade.generateWorkspaceCloud(), "regenerate workspace")
        require_success(facade.reviewAssistedLimits(), "review regenerated limits")
    # Reconfirm an old snapshot only after all transient ROS/MoveIt evidence is
    # live.  This is the same explicit operator action required by 6.4 after a
    # robot-resource or policy revision; it must never be auto-connect state.
    if task_issues or logic.confirmedTaskRecord(parameter_node) is None:
        require_success(facade.confirmTask(), "reconfirm restored task")
    snapshot = logic.confirmedTaskRecord(parameter_node)
    template_collision_override = (
        os.environ.get("DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE", "")
        == "1"
    )
    if template_collision_override:
        require_success(
            facade.setTemplateCollisionExclusionForFunctionalSimulation(True),
            "enable explicit x4 template collision exclusion",
        )
    if os.environ.get("DENTOBOT_FOCUSED_STAGE3_DIAG", "") == "1":
        home_record = logic.taskHomeRecord(parameter_node)
        if home_record is None:
            raise RuntimeError("focused Stage-3 diagnostic has no Task Home")
        home_positions = bridge.canonicalize_planning_joint_positions(
            dict(zip(home_record.joint_names, home_record.joint_positions_si))
        )
        robot_node = bridge.find_ros2_robot_by_name(bridge.ROS2_ROBOT_NAME)
        if robot_node is None:
            raise RuntimeError("focused Stage-3 diagnostic could not find the ROS robot")
        dense_world = bridge.tool_pose_matrices_world_mm(
            snapshot.entry_ras_mm,
            snapshot.target_ras_mm,
            65,
        )
        dense_base = bridge._pose_matrices_world_to_base_mm(
            dense_world,
            parameter_node.robotBaseTransform,
        )
        seeds = [dict(home_positions)]
        try:
            proposal = json.loads(str(parameter_node.step6AssistedLimitProposalJson or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            proposal = {}
        for evidence in proposal.get("accepted_sample_evidence", ()):
            if not isinstance(evidence, dict):
                continue
            names = tuple(evidence.get("joint_names", ()))
            values = tuple(evidence.get("joint_positions_si", ()))
            if len(values) not in (5, 6):
                continue
            try:
                seed = bridge.canonicalize_planning_joint_positions(
                    dict(zip(names, (float(value) for value in values)))
                )
            except (TypeError, ValueError, KeyError):
                continue
            if seed not in seeds:
                seeds.append(seed)
            if len(seeds) >= 40:
                break
        pose = dense_base[60]
        def probe(seed):
            solution = robot_node.ComputeMoveItPositionAxisIK(
                pose,
                bridge.ROS2_TOOL_TCP_LINK,
                bridge.joint_si_vector(seed),
                2.0,
                False,
            )
            return {
                "solution": list(solution) if solution else None,
                "message": robot_node.GetLastMoveItPositionAxisIKMessage(),
                "position_residual_mm": robot_node.GetLastMoveItPositionAxisIKPositionResidualMm(),
                "axis_residual_deg": robot_node.GetLastMoveItPositionAxisIKAxisResidualDeg(),
                "best_joint_values": list(robot_node.GetLastMoveItPositionAxisIKBestJointValues()),
            }

        print("DENTOBOT_STAGE3_POSE60_DIAGNOSTIC", flush=True)
        print(json.dumps({
            "pose_index": 60,
            "pose_count": len(dense_base),
            "entry_ras_mm": list(snapshot.entry_ras_mm),
            "target_ras_mm": list(snapshot.target_ras_mm),
            "seed_count": len(seeds),
            "results": [
                {"seed_index": index, "seed": dict(seed), **probe(seed)}
                for index, seed in enumerate(seeds)
            ],
        }, indent=2, sort_keys=True), flush=True)
        slicer.util.exit(0)
    if slicer.util.selectedModule() != selected_before_connect:
        raise RuntimeError("routine Step 6 Connect left DENTOWorkflow")

    actual_contact_audit = (
        os.environ.get("DENTOBOT_AUDIT_ACTUAL_CONTACT_ONLY", "") == "1"
    )
    original_tool_insertion_evidence = None
    if actual_contact_audit:
        # The production P0 insertion limit is intentionally a hard block.  A
        # historical x4 path cannot be regenerated after that correction, so
        # this test-local bypass exists solely to classify *already requested*
        # candidate poses against MoveIt's mesh scene.  It is never persisted,
        # never exposed by the workflow UI, and never permits preview.
        original_tool_insertion_evidence = facade._tool_insertion_evidence
        facade._tool_insertion_evidence = lambda _entry, _target: {
            "status": "Pass",
            "code": "TEST_ONLY_INSERTION_LIMIT_BYPASS",
            "message": (
                "TEST ONLY: the production insertion hard-block was bypassed "
                "to audit historical x4 candidate geometry; no preview is allowed."
            ),
        }
    try:
        approach = facade.planApproachPhase()
    finally:
        if original_tool_insertion_evidence is not None:
            facade._tool_insertion_evidence = original_tool_insertion_evidence
    exact_diagnostic = None
    if EXPLICIT_CASE:
        exact_diagnostic = {
            "case": str(PACKAGE),
            "code": approach.code,
            "message": approach.message,
            "details": approach.details,
            "task": snapshot.to_dict(),
            "motion": json.loads(str(parameter_node.step6MotionDiagnosticJson or "{}")),
        }
        Path(DIAGNOSTIC_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
        Path(DIAGNOSTIC_OUTPUT).write_text(json.dumps(
            exact_diagnostic, indent=2, default=str
        ))
        if os.environ.get("DENTOBOT_CAPTURE_FDI21_BOTTOM", "") == "1":
            capture_fdi21_contact_from_below(facade, exact_diagnostic["motion"])
            slicer.util.exit(0)
            return {"diagnostic_only": True, "fdi21_bottom_capture": True}
    if not (
        approach.success
        or (
            os.environ.get("DENTOBOT_PLAN_ONLY", "") == "1"
            and approach.code == "approach_full_chain_blocked"
            and approach.payload is not None
        )
    ):
        require_success(approach, "plan Goal 1")
    approach_plan = approach.payload
    if actual_contact_audit:
        try:
            diagnostic_payload = json.loads(
                str(parameter_node.step6MotionDiagnosticJson or "")
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"actual-contact audit has no candidate diagnostic: {exc}"
            ) from exc
        outcomes = audit_actual_moveit_contacts(facade, diagnostic_payload)
        return {
            "diagnostic_only": True,
            "actual_contact_audit": True,
            "production_insertion_block_bypassed": True,
            "template_collision_exclusion_active": bool(
                facade.templateCollisionExclusionActive
            ),
            "planner_result_code": approach.code,
            "planner_full_task_status": approach.details.get("fullTaskStatus"),
            "candidate_outcomes": outcomes,
        }
    if os.environ.get("DENTOBOT_DIAG_APPROACH_ENDPOINT", "") == "1":
        endpoint = approach_plan.waypoint_joint_vectors_si[-1]
        fk_ok, fk_message, actual = bridge.compute_tcp_position_world_ras_mm(
            endpoint,
            base_transform=parameter_node.robotBaseTransform,
        )
        snapshot_for_diag = logic.confirmedTaskRecord(parameter_node)
        expected_entry = tuple(snapshot_for_diag.entry_ras_mm)
        try:
            diagnostic_session = json.loads(
                str(parameter_node.step6MotionDiagnosticJson or "")
            )
            diagnostic_records = diagnostic_session.get("candidate_records", [])
        except (TypeError, ValueError, json.JSONDecodeError):
            diagnostic_session = {}
            diagnostic_records = []
        error = (
            math.sqrt(sum((float(actual[index]) - expected_entry[index]) ** 2 for index in range(3)))
            if fk_ok and actual is not None
            else None
        )
        print("DENTOBOT_APPROACH_ENDPOINT_DIAGNOSTIC", flush=True)
        print(json.dumps({
            "planCode": approach.code,
            "planDetails": dict(approach.details),
            "waypointCount": len(approach_plan.waypoint_joint_vectors_si),
            "strictWaypointCount": approach_plan.strict_waypoint_count,
            "axisWaypointCount": approach_plan.axis_waypoint_count,
            "contactWaypointCount": approach_plan.contact_waypoint_count,
            "lastJoint": dict(endpoint),
            "fkOk": fk_ok,
            "fkMessage": fk_message,
            "actualTcpRasMm": actual,
            "expectedEntryRasMm": expected_entry,
            "endpointErrorMm": error,
            "selectedDiagnostic": (
                diagnostic_records[
                    int(diagnostic_session.get("selected_candidate_index", 0))
                ]
                if diagnostic_records
                and 0 <= int(diagnostic_session.get("selected_candidate_index", 0)) < len(diagnostic_records)
                else (diagnostic_records[0] if diagnostic_records else None)
            ),
        }, indent=2, sort_keys=True), flush=True)
        raise RuntimeError("diagnostic-only endpoint inspection")
    planned_path_nodes = [
        node
        for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
        if node.GetAttribute("DENTOBOT.Step6PhasePlanPath") == "true"
    ]
    if not 1 <= len(planned_path_nodes) <= 3:
        raise RuntimeError(
            "Goal 1 did not create the expected bounded set of stage paths."
        )
    for planned_path_node in planned_path_nodes:
        planned_path_polydata = planned_path_node.GetPolyData()
        if (
            planned_path_polydata is None
            or planned_path_polydata.GetNumberOfPoints() < 2
            or planned_path_polydata.GetNumberOfLines() < 1
        ):
            raise RuntimeError(
                "A Goal 1 stage path is empty or has no rendered path cells."
            )
    for waypoint in approach_plan.waypoint_joint_vectors_si:
        if len(waypoint) != len(bridge.ROS2_JOINT_SI_ORDER):
            raise RuntimeError("Goal 1 returned a non-planning joint vector")
    if not approach_plan.tool_orientation_fingerprint:
        raise RuntimeError("Goal 1 did not commit a Stage-1 drilling frame")
    if len(approach_plan.tool_axis_ras) != 3 or not math.isclose(
        sum(float(value) ** 2 for value in approach_plan.tool_axis_ras),
        1.0,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        raise RuntimeError("Goal 1 committed an invalid drilling-axis vector")
    if approach_plan.cartesian_fraction < 0.99:
        raise RuntimeError(
            f"Goal 1 terminal fraction is {approach_plan.cartesian_fraction}"
        )
    if approach_plan.coordinate_frame != bridge.ROS2_FIXED_FRAME:
        raise RuntimeError(
            f"Goal 1 used unexpected frame {approach_plan.coordinate_frame}"
        )
    if (
        approach_plan.start_position_error_mm is not None
        and approach_plan.start_position_error_mm
        > bridge.CARTESIAN_START_POSITION_TOLERANCE_MM
    ) or (
        approach_plan.start_orientation_error_deg is not None
        and approach_plan.start_orientation_error_deg
        > bridge.CARTESIAN_START_ORIENTATION_TOLERANCE_DEG
    ):
        raise RuntimeError(
            "Goal 1 start continuity is outside tolerance: "
            f"{approach_plan.start_position_error_mm} mm, "
            f"{approach_plan.start_orientation_error_deg} deg"
        )
    if LOCK_SELECTED_ROUTE:
        session = logic.motionDiagnosticRecord(parameter_node)
        if session is None:
            raise RuntimeError("requested route lock has no current motion diagnostic")
        selection_index = int(session.selected_candidate_index)
        locked = facade.applyDiagnosticCandidate(selection_index, lock=True)
        require_success(locked, "lock and re-plan selected Goal 1 route")
        approach = locked
        approach_plan = approach.payload
        if approach_plan is None:
            raise RuntimeError("locked Goal 1 route did not return a transient plan")
        if exact_diagnostic is not None:
            exact_diagnostic.update(
                {
                    "code": approach.code,
                    "message": approach.message,
                    "details": approach.details,
                    "motion": json.loads(
                        str(parameter_node.step6MotionDiagnosticJson or "{}")
                    ),
                }
            )
            Path(DIAGNOSTIC_OUTPUT).write_text(
                json.dumps(exact_diagnostic, indent=2, default=str)
            )
    if os.environ.get("DENTOBOT_PLAN_ONLY", "") == "1":
        try:
            diagnostic_payload = json.loads(
                str(parameter_node.step6MotionDiagnosticJson or "")
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            diagnostic_payload = {}
        candidate_outcomes = []
        for record in diagnostic_payload.get("candidate_records", ()):
            if not isinstance(record, dict):
                continue
            nearest_first_base = record.get(
                "guard_nearest_point_first_base_m"
            )
            nearest_second_base = record.get(
                "guard_nearest_point_second_base_m"
            )
            candidate_outcomes.append(
                {
                    "candidate_index": record.get("candidate_index"),
                    "route_type": record.get("route_type"),
                    "ik_seed_sample_index": record.get("ik_seed_sample_index"),
                    "axial_roll_deg": record.get("axial_roll_deg"),
                    "full_chain_status": record.get("full_chain_candidate_status"),
                    "failure_stage": record.get("full_chain_failure_stage"),
                    "first_invalid_stage_index": record.get(
                        "full_chain_first_invalid_stage_index"
                    ),
                    "stage2_fraction": record.get("stage2_fraction"),
                    "stage3_fraction": record.get("stage3_fraction"),
                    "first_cause": record.get("full_chain_failure_reason"),
                    "stage1_success": record.get("success"),
                    "stage1_waypoint_count": record.get("stage1_waypoint_count"),
                    "stage2_waypoint_count": record.get("stage2_waypoint_count"),
                    "stage3_waypoint_count": record.get("stage3_waypoint_count"),
                    "failure_classification": record.get("failure_classification"),
                    "first_invalid_collision_pairs": record.get(
                        "first_invalid_collision_pairs"
                    ),
                    "completed_distance_mm": record.get("completed_distance_mm"),
                    "requested_distance_mm": record.get("requested_distance_mm"),
                    "first_invalid_tcp_ras_mm": record.get(
                        "first_invalid_ras_mm"
                    ),
                    "first_invalid_joint_positions_si": record.get(
                        "first_invalid_joint_positions_si"
                    ),
                    "guard_first_body": record.get("guard_first_body"),
                    "guard_second_body": record.get("guard_second_body"),
                    "guard_minimum_world_distance_m": record.get(
                        "guard_minimum_world_distance_m"
                    ),
                    "guard_nearest_point_first_base_m": nearest_first_base,
                    "guard_nearest_point_second_base_m": nearest_second_base,
                    "guard_nearest_point_first_world_ras_mm": (
                        base_point_m_to_world_ras_mm(
                            nearest_first_base,
                            parameter_node.robotBaseTransform,
                        )
                    ),
                    "guard_nearest_point_second_world_ras_mm": (
                        base_point_m_to_world_ras_mm(
                            nearest_second_base,
                            parameter_node.robotBaseTransform,
                        )
                    ),
                }
            )
        return {
            "diagnostic_only": True,
            "base_local_z_offset_mm": BASE_LOCAL_Z_OFFSET_MM,
            "result_code": approach.code,
            "full_task_status": str(approach.details.get("fullTaskStatus") or ""),
            "blocked_stage": str(approach.details.get("blockedStage") or ""),
            "first_invalid_cause": str(approach.details.get("firstInvalidCause") or ""),
            "stage3_fraction": approach.details.get("drillingPreflightFraction"),
            "planning_joint_count": len(bridge.ROS2_JOINT_SI_ORDER),
            "stage_path_count": len(planned_path_nodes),
            "candidate_chain_outcomes": candidate_outcomes,
            "template_collision_exclusion_active": bool(
                facade.templateCollisionExclusionActive
            ),
        }
    approach_finished = []
    approach_progress = []
    require_success(
        facade.previewPhase(
            "approach",
            interval_ms=50,
            on_progress=lambda index, total: approach_progress.append(
                (int(index), int(total))
            ),
            on_finished=approach_finished.append,
        ),
        "start Goal 1 preview",
    )
    if wait_until(lambda: approach_finished, PREVIEW_TIMEOUT_SEC) is None:
        last_status = bridge._last_task_status
        raise RuntimeError(
            "Goal 1 guarded preview timed out at "
            f"{approach_progress[-1] if approach_progress else (0, len(approach_plan.waypoint_joint_vectors_si))}; "
            f"previewActive={facade.previewActive}, sequence={facade._phase_sequence}, "
            f"lastGuardStatus={last_status}"
        )
    approach_outcome = require_success(approach_finished[-1], "preview Goal 1")
    if facade.completedPhase != "approach":
        raise RuntimeError("Goal 1 did not establish the accepted Entry state")

    # The approach is an independently reviewable milestone.  Keep a focused
    # acceptance mode so a known/intentional Goal 2 reachability failure cannot
    # hide a valid Goal 1 preview during development.
    if os.environ.get("DENTOBOT_GOAL1_ONLY", "") == "1":
        accepted = bridge.last_accepted_joint_positions_si()
        if any(name not in accepted for name in bridge.ROS2_JOINT_SI_ORDER):
            raise RuntimeError("Goal 1 preview did not leave an accepted state")
        return {
            "package": PACKAGE.name,
            # Older step-6 packages may not contain an immutable task record;
            # the empty value is intentional until the live runtime has been
            # reconstructed and the task is explicitly reconfirmed below.
            "restored_task_fingerprint": restored_task_before_runtime,
            "planned_task_fingerprint": (
                snapshot.snapshot_fingerprint if snapshot is not None else ""
            ),
            "task_home_remediated": task_home_remediated,
            "task_home_migrated": bool(migration_home_issues),
            "goal1_strict_points": approach_plan.strict_waypoint_count,
            "goal1_axis_points": approach_plan.axis_waypoint_count,
            "goal1_terminal_points": approach_plan.contact_waypoint_count,
            "goal1_cartesian_fraction": approach_plan.cartesian_fraction,
            "goal1_start_position_error_mm": approach_plan.start_position_error_mm,
            "goal1_start_orientation_error_deg": approach_plan.start_orientation_error_deg,
            "goal1_exploratory_tool_contact_suppressed": bool(
                approach_outcome.details.get("exploratoryToolContactSuppressed", False)
            ),
            "goal1_suppressed_tool_contact_samples": int(
                approach_outcome.details.get("suppressedToolContactSampleCount", 0)
            ),
            "goal1_preview_complete": True,
            "goal1_result_code": approach.code,
            "full_task_status": str(
                approach.details.get("fullTaskStatus") or "Provisional"
            ),
            "full_task_blocked_stage": str(
                approach.details.get("blockedStage") or ""
            ),
            "full_task_blocker": str(
                approach.details.get("firstInvalidCause")
                or approach.details.get("terminalPlanningError")
                or approach.details.get("drillingPreflightError")
                or ""
            ),
            "terminal_planning_fraction": approach.details.get(
                "terminalPlanningFraction"
            ),
            "stage_path_count": len(planned_path_nodes),
            "planning_joint_count": len(bridge.ROS2_JOINT_SI_ORDER),
            "tool_orientation_fingerprint": (
                approach_plan.tool_orientation_fingerprint
            ),
            "tool_axis_ras": tuple(approach_plan.tool_axis_ras),
            "goal2_deferred": True,
            "hardware_execution_enabled": False,
        }

    drilling = require_success(facade.planDrillingPhase(), "plan Goal 2")
    drilling_plan = drilling.payload
    if (
        drilling_plan.tool_orientation_fingerprint
        != approach_plan.tool_orientation_fingerprint
        or tuple(drilling_plan.tool_axis_ras) != tuple(approach_plan.tool_axis_ras)
    ):
        raise RuntimeError(
            "Goal 2 did not inherit the exact Stage-1 drilling-frame commitment"
        )
    if drilling_plan.cartesian_fraction < 0.99:
        raise RuntimeError(
            f"Goal 2 Cartesian fraction is {drilling_plan.cartesian_fraction}"
        )
    if (
        drilling_plan.start_position_error_mm is None
        or drilling_plan.start_position_error_mm
        > bridge.CARTESIAN_START_POSITION_TOLERANCE_MM
        or drilling_plan.start_orientation_error_deg is None
        or drilling_plan.start_orientation_error_deg
        > bridge.CARTESIAN_START_ORIENTATION_TOLERANCE_DEG
    ):
        raise RuntimeError(
            "Goal 2 did not begin at the accepted Entry state: "
            f"{drilling_plan.start_position_error_mm} mm, "
            f"{drilling_plan.start_orientation_error_deg} deg"
        )
    drilling_finished = []
    drilling_progress = []
    require_success(
        facade.previewPhase(
            "drilling",
            interval_ms=50,
            on_progress=lambda index, total: drilling_progress.append(
                (int(index), int(total))
            ),
            on_finished=drilling_finished.append,
        ),
        "start Goal 2 preview",
    )
    if wait_until(lambda: drilling_finished, PREVIEW_TIMEOUT_SEC) is None:
        last_status = bridge._last_task_status
        raise RuntimeError(
            "Goal 2 guarded preview timed out at "
            f"{drilling_progress[-1] if drilling_progress else (0, len(drilling_plan.waypoint_joint_vectors_si))}; "
            f"previewActive={facade.previewActive}, sequence={facade._phase_sequence}, "
            f"lastGuardStatus={last_status}"
        )
    drilling_outcome = require_success(drilling_finished[-1], "preview Goal 2")
    if facade.completedPhase != "drilling":
        raise RuntimeError("Goal 2 did not complete under the phase guard")

    accepted = bridge.last_accepted_joint_positions_si()
    if any(name not in accepted for name in bridge.ROS2_JOINT_SI_ORDER):
        raise RuntimeError("final accepted planning-joint state is unavailable")
    robot = connected.payload
    actual_target_base_mm = vtk.vtkMatrix4x4()
    if robot.ComputeKDLFK(
        bridge.joint_si_vector(accepted),
        actual_target_base_mm,
        bridge.ROS2_TOOL_TCP_LINK,
    ) is None:
        raise RuntimeError("final provisional TCP FK failed")
    expected_target_base_m = bridge.world_ras_mm_to_base_m(
        snapshot.target_ras_mm,
        parameter_node.robotBaseTransform,
    )
    final_position_error_mm = math.sqrt(
        sum(
            (
                actual_target_base_mm.GetElement(axis, 3)
                - expected_target_base_m[axis] * 1000.0
            )
            ** 2
            for axis in range(3)
        )
    )
    if final_position_error_mm > bridge.CARTESIAN_START_POSITION_TOLERANCE_MM:
        raise RuntimeError(
            f"final TCP missed Target by {final_position_error_mm:.6f} mm"
        )

    first_return = require_success(
        facade.returnToTaskHome(), "guarded Return Home"
    )
    if not first_return.details.get("axialRetractionCompleted"):
        raise RuntimeError("first guarded return did not complete axial retraction")
    repeated_approach = require_success(
        facade.planApproachPhase(),
        "repeat Goal 1 planning",
    )
    repeated_approach_plan = repeated_approach.payload
    repeated_approach_outcome = preview_repeat_phase(
        facade,
        "approach",
        len(repeated_approach_plan.waypoint_joint_vectors_si),
    )
    if facade.completedPhase != "approach":
        raise RuntimeError("Repeated Goal 1 did not establish the accepted Entry state")
    repeated_drilling = require_success(
        facade.planDrillingPhase(),
        "repeat Goal 2 planning",
    )
    repeated_drilling_plan = repeated_drilling.payload
    if (
        repeated_drilling_plan.tool_orientation_fingerprint
        != repeated_approach_plan.tool_orientation_fingerprint
    ):
        raise RuntimeError("Repeated drilling did not retain its Stage-1 tool frame")
    repeated_drilling_outcome = preview_repeat_phase(
        facade,
        "drilling",
        len(repeated_drilling_plan.waypoint_joint_vectors_si),
    )
    if facade.completedPhase != "drilling":
        raise RuntimeError("Repeated Goal 2 did not complete under the phase guard")
    repeated_accepted = bridge.last_accepted_joint_positions_si()
    repeated_target_base_mm = vtk.vtkMatrix4x4()
    if robot.ComputeKDLFK(
        bridge.joint_si_vector(repeated_accepted),
        repeated_target_base_mm,
        bridge.ROS2_TOOL_TCP_LINK,
    ) is None:
        raise RuntimeError("Repeated final canonical-TCP FK failed")
    repeated_target_error_mm = math.sqrt(
        sum(
            (
                repeated_target_base_mm.GetElement(axis, 3)
                - expected_target_base_m[axis] * 1000.0
            )
            ** 2
            for axis in range(3)
        )
    )
    if repeated_target_error_mm > bridge.CARTESIAN_START_POSITION_TOLERANCE_MM:
        raise RuntimeError(
            "Repeated final TCP missed Target by "
            f"{repeated_target_error_mm:.6f} mm"
        )
    final_return = require_success(
        facade.returnToTaskHome(), "final guarded Return Home"
    )
    if not final_return.details.get("axialRetractionCompleted"):
        raise RuntimeError("final guarded return did not complete axial retraction")
    preflight_warning_count = int(
        approach.details.get("guideClearanceWarningCount", 0)
    )
    if preflight_warning_count <= 0:
        raise RuntimeError(
            "the exact case did not persist its expected guide-clearance warning"
        )
    saved_case_report = {}
    if OUTPUT_CASE:
        output_case = Path(OUTPUT_CASE)
        if output_case.suffix.lower() != ".dentocase":
            output_case = output_case.with_name(output_case.name + ".dentocase")
        if output_case.exists():
            raise RuntimeError(f"refusing to overwrite existing output case: {output_case}")
        inspection = widget._createCaseBundle(output_case)
        validate_case_bundle(inspection.path)
        current_case_contract = require_current_saved_case(
            inspection,
            actual_fdi,
        )
        saved_case_report = {
            "path": str(inspection.path),
            "packageId": inspection.manifest.get("packageId"),
            "sceneSha256": inspection.scene_sha256,
            "currentCaseContract": current_case_contract,
            "guideBore": require_trajectory_guide_bore(parameter_node),
            "reopened": False,
        }
        if REOPEN_SAVED_CASE:
            bridge.disconnect_dentobot_motion_control([])
            widget._openCaseBundle(inspection.path)
            process_events(1.0)
            widget = slicer.util.getModuleWidget("DENTOWorkflow")
            restored_parameter_node = widget._parameterNode
            if slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"):
                raise RuntimeError("saved Stage 6 case restored a live ROS robot")
            restored_fdi = target_fdi(restored_parameter_node)
            if EXPECTED_FDI and restored_fdi != EXPECTED_FDI.removeprefix("FDI"):
                raise RuntimeError(
                    "reopened case restored the wrong target FDI: "
                    f"{restored_fdi or 'unknown'}"
                )
            restored_guide_bore = require_trajectory_guide_bore(
                restored_parameter_node
            )
            restored_session = logic.motionDiagnosticRecord(restored_parameter_node)
            restored_selection = (
                motion_diagnostic_plan_selection(restored_session)
                if restored_session is not None
                else {"state": "auto"}
            )
            if LOCK_SELECTED_ROUTE and restored_selection.get("state") != "locked":
                raise RuntimeError("reopened case lost the locked route intent")
            saved_case_report.update(
                {
                    "reopened": True,
                    "restoredFdi": restored_fdi,
                    "restoredGuideBore": restored_guide_bore,
                    "restoredPlanSelection": restored_selection,
                }
            )
    return {
        "package": PACKAGE.name,
        "targetFdi": actual_fdi,
        "guideBore": guide_bore,
        "restored_task_fingerprint": restored_task_before_runtime,
        "planned_task_fingerprint": snapshot.snapshot_fingerprint,
        "task_home_remediated": task_home_remediated,
        "task_home_migrated": bool(migration_home_issues),
        "planning_frame": drilling_plan.coordinate_frame,
        "goal1_strict_points": approach_plan.strict_waypoint_count,
        "goal1_terminal_points": approach_plan.contact_waypoint_count,
        "goal1_cartesian_fraction": approach_plan.cartesian_fraction,
        "goal1_start_position_error_mm": approach_plan.start_position_error_mm,
        "goal1_start_orientation_error_deg": approach_plan.start_orientation_error_deg,
        "goal2_points": drilling_plan.contact_waypoint_count,
        "goal2_cartesian_fraction": drilling_plan.cartesian_fraction,
        "goal2_start_position_error_mm": drilling_plan.start_position_error_mm,
        "goal2_start_orientation_error_deg": drilling_plan.start_orientation_error_deg,
        "goal2_axial_roll_deg": drilling_plan.axial_roll_deg,
        "goal1_exploratory_tool_contact_suppressed": bool(
            approach_outcome.details.get("exploratoryToolContactSuppressed", False)
        ),
        "goal1_suppressed_tool_contact_samples": int(
            approach_outcome.details.get("suppressedToolContactSampleCount", 0)
        ),
        "goal2_exploratory_tool_contact_suppressed": bool(
            drilling_outcome.details.get("exploratoryToolContactSuppressed", False)
        ),
        "goal2_suppressed_tool_contact_samples": int(
            drilling_outcome.details.get("suppressedToolContactSampleCount", 0)
        ),
        "preflight_guide_clearance_warning_count": preflight_warning_count,
        "preflight_minimum_guide_clearance_warning_m": approach.details.get(
            "minimumGuideClearanceWarningM"
        ),
        "preflight_guide_warning_kinds": list(
            approach.details.get("guideClearanceWarningKinds", ())
        ),
        "preflight_guide_contact_penetration_mm": list(
            approach.details.get("guideClearanceWarningContactPenetrationMm", ())
        ),
        "goal1_guide_clearance_warning_count": int(
            approach_outcome.details.get("guideClearanceWarningCount", 0)
        ),
        "goal1_guide_warning_kinds": list(
            approach_outcome.details.get("guideClearanceWarningKinds", ())
        ),
        "goal2_guide_clearance_warning_count": int(
            drilling_outcome.details.get("guideClearanceWarningCount", 0)
        ),
        "goal2_guide_warning_kinds": list(
            drilling_outcome.details.get("guideClearanceWarningKinds", ())
        ),
        "first_return_axial_retraction_complete": bool(
            first_return.details.get("axialRetractionCompleted")
        ),
        "first_return_reverse_waypoint_count": int(
            first_return.details.get("acceptedReverseWaypointCount", 0)
        ),
        "first_return_guide_clearance_warning_count": int(
            first_return.details.get("guideClearanceWarningCount", 0)
        ),
        "first_return_guide_warning_kinds": list(
            first_return.details.get("guideClearanceWarningKinds", ())
        ),
        "repeat_goal1_guide_clearance_warning_count": int(
            repeated_approach_outcome.details.get(
                "guideClearanceWarningCount", 0
            )
        ),
        "repeat_goal2_guide_clearance_warning_count": int(
            repeated_drilling_outcome.details.get(
                "guideClearanceWarningCount", 0
            )
        ),
        "final_return_axial_retraction_complete": bool(
            final_return.details.get("axialRetractionCompleted")
        ),
        "final_return_reverse_waypoint_count": int(
            final_return.details.get("acceptedReverseWaypointCount", 0)
        ),
        "final_return_guide_clearance_warning_count": int(
            final_return.details.get("guideClearanceWarningCount", 0)
        ),
        "final_return_guide_warning_kinds": list(
            final_return.details.get("guideClearanceWarningKinds", ())
        ),
        "final_target_position_error_mm": final_position_error_mm,
        "repeat_final_target_position_error_mm": repeated_target_error_mm,
        "guarded_preview_complete": True,
        "guarded_return_home_complete": True,
        "repeat_guarded_preview_complete": True,
        "hardware_execution_enabled": False,
        "template_collision_exclusion_active": bool(
            facade.templateCollisionExclusionActive
        ),
        "savedCase": saved_case_report,
    }


try:
    report = run()
    print(
        "DENTOBOT_P5_APPROACH_COMPLETE"
        if APPROACH_ONLY
        else "DENTOBOT_P4_INSERTION_COMPLETE"
        if INSERTION_ONLY
        else "DENTOBOT_ENDPOINT_ONLY_COMPLETE"
        if ENDPOINT_ONLY
        else "DENTOBOT_STAGE3_ACTUAL_CONTACT_AUDIT"
        if os.environ.get("DENTOBOT_AUDIT_ACTUAL_CONTACT_ONLY", "") == "1"
        else "DENTOBOT_STEP65_PLAN_DIAGNOSTIC"
        if os.environ.get("DENTOBOT_PLAN_ONLY", "") == "1"
        else "DENTOBOT_STEP65_EXACT_CASE_PASS",
        flush=True,
    )
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    bridge.disconnect_dentobot_motion_control([])
    bridge.shutdown_slicer_adapter()
    slicer.mrmlScene.Clear(0)
    slicer.app.processEvents()
    slicer.util.exit(0)
except Exception as exc:
    print(f"DENTOBOT_STEP65_EXACT_CASE_FAILED: {exc}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
    try:
        bridge.disconnect_dentobot_motion_control([])
        bridge.shutdown_slicer_adapter()
    except Exception:
        pass
    slicer.util.exit(1)
