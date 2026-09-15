"""Retained Campaign-1 display-only review recapture driver.

This driver is deliberately separate from the production robot placement
policy.  It reconstructs two isolated review scenes from the retained MRB:
the endpoint scene first, then the Home-to-endpoint evaluated sample.  It
uses only the existing offline FK/mesh helpers and never starts ROS, MoveIt,
planning, a controller, or a trajectory.

The driver fails closed before an image when the requested state, prepared
geometry, displayed mesh transforms, saved native FK evidence, or save/reopen
pose identity cannot be compared.  Production robot link nodes remain
transient; only the review copy's exact local robot nodes are made persistent
in the separate review MRB.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


JOINT_ORDER = (
    "link-1_Revolute-1",
    "link-2_Slider-2",
    "link-3_Revolute-3",
    "link-4_Slider-4",
    "link-5_Revolute-5",
)
POSITION_TOLERANCE_MM = 0.25
ROTATION_TOLERANCE_DEG = 0.5
BOUNDS_TOLERANCE_MM = 0.05


class ReviewCaptureBlocked(RuntimeError):
    """Raised when review evidence is not strong enough to permit a capture."""


def _set_properties_label_visibility_if_supported(display) -> bool:
    method = getattr(display, "SetPropertiesLabelVisibility", None)
    if not callable(method):
        return False
    method(True)
    return True


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _matrix(value: Any) -> list[list[float]] | None:
    try:
        rows = [[float(item) for item in row] for row in value]
    except (TypeError, ValueError):
        return None
    if len(rows) != 4 or any(len(row) != 4 for row in rows):
        return None
    if not all(math.isfinite(item) for row in rows for item in row):
        return None
    return rows


def _matmul(left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]) -> list[list[float]]:
    return [
        [
            sum(float(left[row][inner]) * float(right[inner][column]) for inner in range(4))
            for column in range(4)
        ]
        for row in range(4)
    ]


def _rigid_inverse(value: Any) -> list[list[float]] | None:
    """Invert a finite rigid homogeneous RAS/mm transform."""

    matrix = _matrix(value)
    if matrix is None:
        return None
    rotation = [[matrix[row][column] for column in range(3)] for row in range(3)]
    inverse = [[rotation[column][row] for column in range(3)] for row in range(3)]
    translation = [matrix[row][3] for row in range(3)]
    result = [[0.0] * 4 for _ in range(4)]
    for row in range(3):
        for column in range(3):
            result[row][column] = inverse[row][column]
        result[row][3] = -sum(inverse[row][axis] * translation[axis] for axis in range(3))
    result[3][3] = 1.0
    return result


def _matrix_m_to_mm(value: Any) -> list[list[float]] | None:
    matrix = _matrix(value)
    if matrix is None:
        return None
    converted = [row[:] for row in matrix]
    for row in range(3):
        converted[row][3] *= 1000.0
    return converted


def _max_abs_difference(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right):
        return None
    values = []
    for first, second in zip(left, right):
        a = _finite(first)
        b = _finite(second)
        if a is None or b is None:
            return None
        values.append(abs(a - b))
    return max(values, default=0.0)


def compare_transform(
    expected: Any,
    observed: Any,
    *,
    translation_tolerance_mm: float = POSITION_TOLERANCE_MM,
    rotation_tolerance_deg: float = ROTATION_TOLERANCE_DEG,
) -> dict[str, Any]:
    """Compare two homogeneous RAS/mm matrices without accepting markers."""

    expected_matrix = _matrix(expected)
    observed_matrix = _matrix(observed)
    if expected_matrix is None or observed_matrix is None:
        return {
            "available": False,
            "match": None,
            "translation_error_mm": None,
            "rotation_error_deg": None,
            "unknown_reason": "One or both actual transform matrices are absent or non-finite.",
        }
    translation_error_mm = math.sqrt(
        sum(
            (expected_matrix[axis][3] - observed_matrix[axis][3]) ** 2
            for axis in range(3)
        )
    )
    relative = [
        [
            sum(
                expected_matrix[inner][row] * observed_matrix[inner][column]
                for inner in range(3)
            )
            for column in range(3)
        ]
        for row in range(3)
    ]
    cosine = max(-1.0, min(1.0, (sum(relative[index][index] for index in range(3)) - 1.0) / 2.0))
    rotation_error_deg = math.degrees(math.acos(cosine))
    return {
        "available": True,
        "match": bool(
            translation_error_mm <= float(translation_tolerance_mm)
            and rotation_error_deg <= float(rotation_tolerance_deg)
        ),
        "translation_error_mm": translation_error_mm,
        "rotation_error_deg": rotation_error_deg,
        "translation_tolerance_mm": float(translation_tolerance_mm),
        "rotation_tolerance_deg": float(rotation_tolerance_deg),
    }


def compare_bounds(
    expected: Any,
    observed: Any,
    *,
    tolerance_mm: float = BOUNDS_TOLERANCE_MM,
) -> dict[str, Any]:
    """Compare six world-RAS/mm bounds, preserving unknown as unknown."""

    expected_values = list(expected) if isinstance(expected, (list, tuple)) else []
    observed_values = list(observed) if isinstance(observed, (list, tuple)) else []
    difference = _max_abs_difference(expected_values, observed_values)
    if difference is None or len(expected_values) != 6:
        return {
            "available": False,
            "match": None,
            "max_abs_error_mm": None,
            "unknown_reason": "Both six-value world bounds are required.",
        }
    return {
        "available": True,
        "match": difference <= float(tolerance_mm),
        "max_abs_error_mm": difference,
        "tolerance_mm": float(tolerance_mm),
    }


def compare_robot_description_identity(expected: Any, observed: Any) -> dict[str, Any]:
    """Require the loaded robot profile to be the retained native profile."""

    expected_value = str(expected or "")
    observed_value = str(observed or "")
    available = bool(expected_value and observed_value)
    return {
        "available": available,
        "match": bool(available and expected_value == observed_value),
        "expected_identity_sha256": expected_value or None,
        "observed_identity_sha256": observed_value or None,
        "unknown_reason": (
            "Retained or loaded robot profile identity is missing."
            if not available
            else None
        ),
    }


def _joint_dict(values: Any) -> dict[str, float] | None:
    if isinstance(values, Mapping):
        result = {str(key): _finite(value) for key, value in values.items()}
        if any(value is None for value in result.values()):
            return None
        return {key: float(value) for key, value in result.items()}
    if isinstance(values, (list, tuple)) and len(values) == len(JOINT_ORDER):
        converted = [_finite(value) for value in values]
        if any(value is None for value in converted):
            return None
        return dict(zip(JOINT_ORDER, (float(value) for value in converted)))
    return None


def _same_joints(first: Mapping[str, float], second: Mapping[str, float], tolerance: float = 1e-12) -> bool:
    return (
        tuple(first.keys()) == tuple(second.keys())
        and all(abs(float(first[key]) - float(second[key])) <= tolerance for key in first)
    )


def load_review_state(
    rejected_state: Mapping[str, Any],
    state_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Extract endpoint and evaluated-transition states without conflating them."""

    states = rejected_state.get("states") or {}
    endpoint_record = states.get("target_state") or {}
    transition_record = states.get("first_guard_rejected") or {}
    transition = transition_record.get("transition") or {}
    evaluated = transition.get("evaluated_or_rejected_sample") or {}
    endpoint_joints = _joint_dict(endpoint_record.get("joints_si"))
    evaluated_joints = _joint_dict(evaluated.get("joints_si"))
    starting_joints = _joint_dict((transition.get("starting_state") or {}).get("joints_si"))
    requested_joints = _joint_dict((transition.get("requested_state") or {}).get("joints_si"))
    if endpoint_joints is None or evaluated_joints is None:
        raise ReviewCaptureBlocked("Saved endpoint and evaluated-sample joint vectors are required.")
    if starting_joints is None or requested_joints is None:
        raise ReviewCaptureBlocked(
            "Saved Home and requested-endpoint vectors are required for transition labels."
        )
    if _same_joints(endpoint_joints, evaluated_joints):
        raise ReviewCaptureBlocked("Endpoint and transition sample unexpectedly share one joint vector.")
    native_display = ((state_identity.get("display_evidence") or {}).get("goal_robot_fk") or {})
    native_joint_state = _joint_dict(native_display.get("joint_state_si"))
    if native_joint_state is None or not _same_joints(endpoint_joints, native_joint_state):
        raise ReviewCaptureBlocked(
            "Saved native display-FK evidence does not identify the retained endpoint vector."
        )
    transition_display = ((state_identity.get("display_evidence") or {}).get("transition_sample_fk") or {})
    if not isinstance(transition_display, Mapping):
        transition_display = {}
    transition_fk = (
        evaluated.get("native_fk_world_ras_mm")
        or transition.get("native_fk_world_ras_mm")
        or transition_display.get("native_fk_world_ras_mm")
        or {}
    )
    if not isinstance(transition_fk, Mapping):
        transition_fk = {}
    return {
        "endpoint": {
            "kind": "static_endpoint",
            "phase": str(endpoint_record.get("phase") or "drilling"),
            "joints_si": endpoint_joints,
            "native_fk_world_ras_mm": native_display.get("native_fk_world_ras_mm") or {},
            "native_state_source": "state_identity.display_evidence.goal_robot_fk",
            "static_result_label": "phase-aware static_state: rejected; native pair: final printable template ↔ spindle",
        },
        "transition": {
            "kind": "transition_sample",
            "phase": str(transition.get("phase") or transition_record.get("phase") or "drilling"),
            "joints_si": evaluated_joints,
            "sample_index": evaluated.get("sample_index"),
            "total_sample_count": transition.get("interpolation", {}).get("total_sample_count"),
            "interpolation_fraction": evaluated.get("interpolation_fraction"),
            "starting_joints_si": starting_joints,
            "requested_joints_si": requested_joints,
            "reason": ((transition.get("result") or {}).get("reason")),
            "native_fk_world_ras_mm": dict(transition_fk),
            "native_state_source": (
                "saved native evaluated-sample FK matrices"
                if transition_fk
                else "saved native evaluated joint vector only; no evaluated-sample FK matrices were retained"
            ),
            "static_result_label": "transition only; not Target static validity and not r13 insertion/onset",
        },
    }


def native_geometry_records(state_identity: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Index the exact native prepared-world object records by source role."""

    audit = (((state_identity.get("native_scene") or {}).get("audit") or {}).get("value") or {})
    records = audit.get("object_records") or []
    return {
        str(record.get("source_role")): record
        for record in records
        if isinstance(record, Mapping) and record.get("source_role")
    }


def review_capture_readiness(
    *,
    state_kind: str,
    state: Mapping[str, Any],
    geometry: Mapping[str, Any],
    display_robot: Mapping[str, Any],
    saved_pose_required: bool = True,
) -> dict[str, Any]:
    """Return a fail-closed capture decision used before every image."""

    checks = {
        "state_kind": state_kind in {"static_endpoint", "transition_sample"},
        "geometry": geometry.get("match") is True,
        "display_mesh_transforms": display_robot.get("mesh_transforms_match") is True,
        "native_exposed_fk": display_robot.get("native_exposed_fk_match") is True,
        "saved_pose_persistence": (
            display_robot.get("saved_pose_persistence_match") is True
            if saved_pose_required
            else True
        ),
    }
    if state_kind == "transition_sample":
        checks["native_evaluated_sample_fk"] = display_robot.get("native_evaluated_sample_fk_match") is True
    else:
        checks["native_evaluated_sample_fk"] = True
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "blocked_reason": None if all(checks.values()) else "One or more display/native/save-reopen parity checks did not pass.",
    }


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _read_world_matrix(node, matrix) -> None:
    direct = getattr(node, "GetMatrixTransformToWorld", None)
    if callable(direct):
        if direct(matrix) is False:
            raise ReviewCaptureBlocked(f"Could not read world transform for {node.GetName()}.")
        return
    parent_getter = getattr(node, "GetParentTransformNode", None)
    parent = parent_getter() if callable(parent_getter) else None
    if parent is None:
        matrix.Identity()
        return
    parent_world = getattr(parent, "GetMatrixTransformToWorld", None)
    if not callable(parent_world) or parent_world(matrix) is False:
        raise ReviewCaptureBlocked(f"Could not read parent world transform for {node.GetName()}.")


def _matrix_from_node(node) -> list[list[float]]:
    import vtk

    matrix = vtk.vtkMatrix4x4()
    _read_world_matrix(node, matrix)
    return [
        [float(matrix.GetElement(row, column)) for column in range(4)]
        for row in range(4)
    ]


def _model_bounds(node) -> list[float]:
    bounds = [0.0] * 6
    node.GetRASBounds(bounds)
    if not all(math.isfinite(float(value)) for value in bounds):
        raise ReviewCaptureBlocked(f"Could not read world bounds for {node.GetName()}.")
    return [float(value) for value in bounds]


def _set_review_persistence(logic, base, models, state_kind: str, joints: Mapping[str, float]) -> dict[str, Any]:
    """Persist only this review copy; production placement remains transient."""

    nodes = [base, *models, *logic.robotLinkTransformNodes()]
    unique_nodes = []
    seen = set()
    for node in nodes:
        if node is None or node.GetID() in seen:
            continue
        seen.add(node.GetID())
        unique_nodes.append(node)
    state_json = json.dumps(dict(joints), sort_keys=True, separators=(",", ":"))
    for node in unique_nodes:
        node.SetSaveWithScene(True)
        node.SetAttribute("DENTOBOT.ReviewOnlyRobotPose", "true")
        node.SetAttribute("DENTOBOT.ReviewOnlyStateKind", state_kind)
        node.SetAttribute("DENTOBOT.ReviewOnlyJointStateSiJson", state_json)
        if node.IsA("vtkMRMLModelNode"):
            node.SetAttribute("DENTOBOT.IntendedUse", "DisplayOnlyReview")
            node.SetAttribute("DENTOBOT.ExcludedFromCollision", "true")
        display = node.GetDisplayNode() if hasattr(node, "GetDisplayNode") else None
        if display is not None:
            display.SetSaveWithScene(True)
        storage = node.GetStorageNode() if hasattr(node, "GetStorageNode") else None
        if storage is not None:
            storage.SetSaveWithScene(True)
    return {
        "node_count": len(unique_nodes),
        "node_ids": [str(node.GetID()) for node in unique_nodes],
        "production_transient_policy_changed": False,
    }


def _set_review_parameter_joint_state(parameter, joints: Mapping[str, float]) -> dict[str, float]:
    """Persist the review pose through the workflow's existing rehydration path."""

    missing = [name for name in JOINT_ORDER if _finite(joints.get(name)) is None]
    if missing:
        raise ReviewCaptureBlocked(
            "The retained endpoint joint vector is missing finite values for: "
            + ", ".join(missing)
        )
    display_values = {
        "robotJoint1Deg": math.degrees(float(joints[JOINT_ORDER[0]])),
        "robotJoint2Mm": float(joints[JOINT_ORDER[1]]) * 1000.0,
        "robotJoint3Deg": math.degrees(float(joints[JOINT_ORDER[2]])),
        "robotJoint4Mm": float(joints[JOINT_ORDER[3]]) * 1000.0,
        "robotJoint5Deg": math.degrees(float(joints[JOINT_ORDER[4]])),
        # The retained native endpoint is the canonical non-spinning J1-J5
        # state; keep the visual-only J6 at its existing zero value.
        "robotJoint6Deg": 0.0,
    }
    start_modify = getattr(parameter, "StartModify", None)
    end_modify = getattr(parameter, "EndModify", None)
    token = start_modify() if callable(start_modify) else None
    try:
        for name, value in display_values.items():
            setattr(parameter, name, value)
    finally:
        if callable(end_modify):
            end_modify(token)
    return display_values


def _copy_world_model(slicer, polydata, name: str, color: tuple[float, float, float], opacity: float):
    import vtk

    model = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", name)
    copied = vtk.vtkPolyData()
    copied.DeepCopy(polydata)
    model.SetAndObservePolyData(copied)
    model.SetAndObserveTransformNodeID(None)
    model.SetAttribute("DENTOBOT.ReviewOnly", "true")
    model.SetAttribute("DENTOBOT.ReviewSourceFrame", "SlicerWorldRASmm")
    model.SetAttribute("DENTOBOT.ReviewRole", name)
    model.SetAttribute("DENTOBOT.IntendedUse", "DisplayOnlyReview")
    model.SetAttribute("DENTOBOT.ExcludedFromCollision", "true")
    model.SetSaveWithScene(True)
    model.CreateDefaultDisplayNodes()
    display = model.GetDisplayNode()
    if display is not None:
        display.SetSaveWithScene(True)
        display.SetVisibility(True)
        display.SetVisibility3D(True)
        display.SetColor(*color)
        display.SetOpacity(float(opacity))
        _set_properties_label_visibility_if_supported(display)
    storage = model.GetStorageNode()
    if storage is not None:
        storage.SetSaveWithScene(True)
    return model


def _require_single_jaw_preparation(native_record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the retained native contract before preparing the review copy."""

    try:
        application_count = int(native_record.get("jaw_transform_application_count"))
    except (TypeError, ValueError):
        application_count = -1
    fingerprint = str(native_record.get("jaw_transform_fingerprint") or "")
    if application_count != 1 or not fingerprint:
        raise ReviewCaptureBlocked(
            "The retained target contract does not prove exactly one Case Foundation "
            f"jaw preparation (count={application_count}, fingerprint={fingerprint or 'missing'})."
        )
    return {
        "native_jaw_transform_application_count": application_count,
        "applied_jaw_transform_application_count": 1,
        "native_jaw_transform_fingerprint": fingerprint,
        "source_frame": "segmentation closed-surface world RAS mm",
        "prepared_frame": "Case Foundation jaw-opened world RAS mm",
        "triangulation": {
            "filter": "vtkTriangleFilter",
            "pass_lines": False,
            "pass_verts": False,
        },
    }


def _validate_saved_jaw_preparation_identity(parameter, native_record: Mapping[str, Any]) -> dict[str, Any]:
    """Require the MRB's saved Case Foundation preparation to match native evidence."""

    transform = getattr(parameter, "step6CaseJawTransform", None)
    if transform is None:
        raise ReviewCaptureBlocked("The retained inspection MRB has no saved Case Foundation jaw transform.")
    mode = str(getattr(parameter, "step6CaseJawPreparationMode", "") or "")
    record = str(getattr(parameter, "step6CaseJawPreparationJson", "") or "")
    try:
        from DENTOStep6State import fingerprint

        runtime_fingerprint = fingerprint({"mode": mode, "record": record})
    except Exception as exc:
        raise ReviewCaptureBlocked(
            f"Could not fingerprint the saved Case Foundation preparation: {type(exc).__name__}: {exc}"
        ) from exc
    expected_fingerprint = str(native_record.get("jaw_transform_fingerprint") or "")
    if not expected_fingerprint or runtime_fingerprint != expected_fingerprint:
        raise ReviewCaptureBlocked(
            "The saved Case Foundation preparation fingerprint does not match the retained native evidence."
        )
    return {
        "mode": mode,
        "record_fingerprint": runtime_fingerprint,
        "native_record_fingerprint": expected_fingerprint,
        "transform_name": str(transform.GetName() or "") if hasattr(transform, "GetName") else "",
    }


def _ensure_case_foundation_display_volumes(logic, parameter) -> dict[str, Any]:
    """Restore only missing transient Case Foundation display volumes in the review copy."""

    fixed = getattr(parameter, "caseFoundationFixedUpperVolume", None)
    moving = getattr(parameter, "caseFoundationMovingLowerVolume", None)
    if fixed is not None and moving is not None:
        return {
            "restored": False,
            "source": "retained MRB transient Case Foundation display volumes",
        }
    rebuild = getattr(logic, "rebuildCaseFoundationDisplayVolumes", None)
    if not callable(rebuild):
        raise ReviewCaptureBlocked(
            "The retained MRB omitted Case Foundation display volumes and the existing offline restoration helper is unavailable."
        )
    try:
        fixed, moving = rebuild(parameter)
    except Exception as exc:
        raise ReviewCaptureBlocked(
            "Could not restore the omitted Case Foundation display volumes from the retained source scene: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if fixed is None or moving is None:
        raise ReviewCaptureBlocked(
            "The Case Foundation display-volume restoration returned an incomplete pair."
        )
    return {
        "restored": True,
        "source": "existing offline rebuildCaseFoundationDisplayVolumes helper",
        "fixed_upper_volume_present": True,
        "moving_lower_volume_present": True,
    }


def _triangle_filter_polydata(polydata):
    """Match the native collision audit's post-jaw triangulation semantics."""

    import vtk

    triangle = vtk.vtkTriangleFilter()
    triangle.SetInputData(polydata)
    triangle.PassLinesOff()
    triangle.PassVertsOff()
    triangle.Update()
    result = vtk.vtkPolyData()
    result.DeepCopy(triangle.GetOutput())
    return result


def _prepare_target_surface_for_review(
    logic,
    parameter,
    source_world,
    native_record: Mapping[str, Any],
):
    """Apply the frozen moving-jaw preparation exactly once to the review copy."""

    contract = _require_single_jaw_preparation(native_record)
    prepared_world = logic._step6CaseJawPolydataWorld(parameter, source_world)
    if prepared_world is None or prepared_world.GetNumberOfPoints() == 0:
        raise ReviewCaptureBlocked("The Case Foundation jaw preparation returned an empty target.")
    prepared_world = _triangle_filter_polydata(prepared_world)
    if prepared_world.GetNumberOfPoints() == 0 or prepared_world.GetNumberOfPolys() == 0:
        raise ReviewCaptureBlocked("The prepared target has no triangulated surface cells.")
    return prepared_world, contract


def _add_fiducial_labels(slicer, name: str, labels: Sequence[tuple[str, Sequence[float]]]):
    markups = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", name)
    markups.SetAttribute("DENTOBOT.ReviewOnly", "true")
    markups.SetSaveWithScene(True)
    markups.CreateDefaultDisplayNodes()
    display = markups.GetDisplayNode()
    if display is not None:
        display.SetSaveWithScene(True)
        display.SetPointLabelsVisibility(True)
        _set_properties_label_visibility_if_supported(display)
        display.SetVisibility(True)
        display.SetVisibility3D(True)
    for label, point in labels:
        markups.AddControlPointWorld(tuple(float(value) for value in point), label)
    return markups


def _make_corridor_model(slicer, entry, target, radius_mm: float):
    import vtk

    source = vtk.vtkLineSource()
    source.SetPoint1(*entry)
    source.SetPoint2(*target)
    source.Update()
    tube = vtk.vtkTubeFilter()
    tube.SetInputConnection(source.GetOutputPort())
    tube.SetRadius(float(radius_mm))
    tube.SetNumberOfSides(16)
    tube.CappingOn()
    tube.Update()
    model = _copy_world_model(
        slicer,
        tube.GetOutput(),
        "[Review] Entry-Target corridor (display only)",
        (0.95, 0.85, 0.15),
        0.28,
    )
    model.SetAttribute("DENTOBOT.ReviewCorridorRadiusMm", str(float(radius_mm)))
    model.SetAttribute("DENTOBOT.ReviewRole", "entry-target-corridor")
    return model


def _world_link_point(logic, base, joints: Mapping[str, float], link_name: str) -> list[float]:
    from DENTORobotPlacement import link_transforms_base_m

    urdf_path, package_root = logic.robotDescriptionPaths()
    local = _matrix_m_to_mm(
        link_transforms_base_m(urdf_path, package_root, dict(joints)).get(link_name)
    )
    if local is None:
        raise ReviewCaptureBlocked(f"Offline FK did not expose required {link_name} frame.")
    world = _matmul(_matrix_from_node(base), local)
    return [float(world[axis][3]) for axis in range(3)]


def _prepare_display_scene(
    slicer,
    logic,
    parameter,
    state_kind: str,
    state: Mapping[str, Any],
    target_native_record: Mapping[str, Any],
):
    target_id = str(parameter.targetToothSegmentId or "")
    if not target_id:
        raise ReviewCaptureBlocked("The retained inspection scene has no target segment ID.")
    target_source_world = logic._segmentationSegmentsSurfaceWorld(
        parameter.teethSegmentation,
        {target_id},
    )
    final_template = parameter.finalPrintableTemplateModel
    if target_source_world is None or target_source_world.GetNumberOfPoints() == 0:
        raise ReviewCaptureBlocked("The retained target has no prepared world surface.")
    if final_template is None:
        raise ReviewCaptureBlocked("The retained final printable template is missing.")
    target_source_evidence = logic._collisionAuditPolydataEvidence(target_source_world)
    case_foundation_display_repair = _ensure_case_foundation_display_volumes(logic, parameter)
    saved_jaw_preparation = _validate_saved_jaw_preparation_identity(
        parameter,
        target_native_record,
    )
    target_world, target_preparation = _prepare_target_surface_for_review(
        logic,
        parameter,
        target_source_world,
        target_native_record,
    )
    template_world = logic._step6TargetAttachedModelPolydataWorld(parameter, final_template)
    if template_world is None or template_world.GetNumberOfPoints() == 0:
        raise ReviewCaptureBlocked("The retained final template has no world surface.")
    target_model = _copy_world_model(
        slicer,
        target_world,
        "[Review] FDI31 prepared target tooth (world RAS)",
        (0.90, 0.15, 0.15),
        0.40,
    )
    target_model.SetAttribute(
        "DENTOBOT.ReviewTargetSourceFingerprint",
        str(target_source_evidence["fingerprint"]),
    )
    target_model.SetAttribute(
        "DENTOBOT.ReviewTargetSourceBoundsWorldRasMmJson",
        json.dumps(list(target_source_evidence["bounds"]), separators=(",", ":")),
    )
    target_model.SetAttribute(
        "DENTOBOT.ReviewTargetPreparationJson",
        json.dumps(target_preparation, sort_keys=True, separators=(",", ":")),
    )
    template_model = _copy_world_model(
        slicer,
        template_world,
        "[Review] Final printable template (world RAS)",
        (0.15, 0.80, 0.95),
        0.34,
    )
    line = parameter.trajectoryLine
    if line is None or line.GetNumberOfDefinedControlPoints() != 2:
        raise ReviewCaptureBlocked("The retained Entry-to-Target line is incomplete.")
    entry = [0.0, 0.0, 0.0]
    target = [0.0, 0.0, 0.0]
    line.GetNthControlPointPositionWorld(0, entry)
    line.GetNthControlPointPositionWorld(1, target)
    corridor = _make_corridor_model(
        slicer,
        entry,
        target,
        0.75,
    )
    base, robot_models = logic.createOrUpdateRobotPlacement(
        parameter.robotBaseTransform,
        dict(state["joints_si"]),
    )
    parameter.robotBaseTransform = base
    review_parameter_joint_state = _set_review_parameter_joint_state(
        parameter,
        state["joints_si"],
    )
    updated = logic.updateRobotJointPoses(dict(state["joints_si"]))
    if updated != 7:
        raise ReviewCaptureBlocked(f"Offline FK updated {updated} robot links; expected 7.")
    persistence = _set_review_persistence(
        logic,
        base,
        robot_models,
        state_kind,
        state["joints_si"],
    )
    state_points = {
        "evaluated_tcp": _world_link_point(
            logic,
            base,
            state["joints_si"],
            "dentobot_drill_tcp",
        )
    }
    if state_kind == "transition_sample":
        state_points["home_tcp"] = _world_link_point(
            logic,
            base,
            state["starting_joints_si"],
            "dentobot_drill_tcp",
        )
        state_points["requested_endpoint_tcp"] = _world_link_point(
            logic,
            base,
            state["requested_joints_si"],
            "dentobot_drill_tcp",
        )
    return {
        "base": base,
        "robot_models": robot_models,
        "target_model": target_model,
        "template_model": template_model,
        "target_source_evidence": target_source_evidence,
        "target_preparation": target_preparation,
        "case_foundation_display_repair": case_foundation_display_repair,
        "saved_jaw_preparation": saved_jaw_preparation,
        "review_parameter_joint_state": review_parameter_joint_state,
        "corridor_model": corridor,
        "entry": entry,
        "target": target,
        "state_points": state_points,
        "persistence": persistence,
    }


def _native_fk_comparisons(
    *,
    logic,
    base_world: list[list[float]],
    joint_positions_si: Mapping[str, float],
    native_fk: Mapping[str, Any],
):
    from DENTORobotPlacement import link_transforms_base_m

    urdf_path, package_root = logic.robotDescriptionPaths()
    local_frames = link_transforms_base_m(urdf_path, package_root, dict(joint_positions_si))
    links = {
        "tcp": "dentobot_drill_tcp",
        "burr": "burr",
        "spindle": "pneumatic_spindle-Copy",
    }
    comparisons = {}
    for evidence_name, link_name in links.items():
        local_mm = _matrix_m_to_mm(local_frames.get(link_name))
        expected = _matmul(base_world, local_mm) if local_mm is not None else None
        observed = native_fk.get(evidence_name)
        comparisons[evidence_name] = compare_transform(expected, observed)
    available = all(item["available"] for item in comparisons.values())
    matched = available and all(item["match"] is True for item in comparisons.values())
    return {
        "available": available,
        "match": matched,
        "comparisons": comparisons,
        "native_evidence_missing": [key for key, item in comparisons.items() if not item["available"]],
    }


def _observed_link_world_from_mesh(
    observed_mesh_world: Any,
    base_from_link_mm: Any,
    base_from_mesh_mm: Any,
) -> list[list[float]] | None:
    """Recover a link pose from its displayed mesh and visual-origin offset."""

    observed_mesh = _matrix(observed_mesh_world)
    base_from_link = _matrix(base_from_link_mm)
    base_from_mesh = _matrix(base_from_mesh_mm)
    link_from_mesh = (
        _matmul(_rigid_inverse(base_from_link), base_from_mesh)
        if base_from_link is not None and base_from_mesh is not None
        and _rigid_inverse(base_from_link) is not None
        else None
    )
    if observed_mesh is None or link_from_mesh is None:
        return None
    inverse_link_from_mesh = _rigid_inverse(link_from_mesh)
    if inverse_link_from_mesh is None:
        return None
    return _matmul(observed_mesh, inverse_link_from_mesh)


def _derive_tcp_world_from_displayed_spindle(
    *,
    observed_spindle_mesh_world: Any,
    base_from_spindle_link_mm: Any,
    base_from_spindle_mesh_mm: Any,
    base_from_tcp_mm: Any,
) -> dict[str, Any]:
    """Derive the meshless canonical TCP from the displayed spindle mesh."""

    spindle_link_world = _observed_link_world_from_mesh(
        observed_spindle_mesh_world,
        base_from_spindle_link_mm,
        base_from_spindle_mesh_mm,
    )
    spindle_link = _matrix(base_from_spindle_link_mm)
    tcp_link = _matrix(base_from_tcp_mm)
    spindle_to_tcp = (
        _matmul(_rigid_inverse(spindle_link), tcp_link)
        if spindle_link is not None and tcp_link is not None
        and _rigid_inverse(spindle_link) is not None
        else None
    )
    observed_tcp_world = (
        _matmul(spindle_link_world, spindle_to_tcp)
        if spindle_link_world is not None and spindle_to_tcp is not None
        else None
    )
    return {
        "available": observed_tcp_world is not None,
        "source_mesh_link": "pneumatic_spindle-Copy",
        "derived_frame": "dentobot_drill_tcp",
        "fixed_relation_source": "DENTORobotPlacement.link_transforms_base_m",
        "visual_origin_accounted": True,
        "observed_spindle_mesh_world_ras_mm": _matrix(observed_spindle_mesh_world),
        "observed_spindle_link_world_ras_mm": spindle_link_world,
        "spindle_link_to_tcp_ras_mm": spindle_to_tcp,
        "observed_tcp_world_ras_mm": observed_tcp_world,
        "unknown_reason": (
            "Displayed spindle mesh, visual-origin relation, or canonical TCP frame "
            "was unavailable or non-finite."
            if observed_tcp_world is None
            else None
        ),
    }


def _loaded_robot_description_identity(logic, expected_identity: Any) -> dict[str, Any]:
    try:
        profile = logic.caseBundleRobotProfile()
        observed_identity = profile.get("identitySha256") if isinstance(profile, Mapping) else None
    except Exception as exc:
        return {
            **compare_robot_description_identity(expected_identity, None),
            "error": f"{type(exc).__name__}: {exc}",
        }
    return compare_robot_description_identity(expected_identity, observed_identity)


def _display_robot_comparisons(
    logic,
    base,
    models,
    state: Mapping[str, Any],
    native_fk: Mapping[str, Any],
    native_robot_profile_fingerprint: Any,
):
    from DENTORobotPlacement import robot_link_mesh_poses_mm

    base_world = _matrix_from_node(base)
    urdf_path, package_root = logic.robotDescriptionPaths()
    from DENTORobotPlacement import link_transforms_base_m

    local_frames = link_transforms_base_m(urdf_path, package_root, dict(state["joints_si"]))
    poses = robot_link_mesh_poses_mm(urdf_path, package_root, dict(state["joints_si"]))
    pose_by_link = {pose.link_name: pose for pose in poses}
    actual_models = {
        str(model.GetAttribute("DENTOBOT.RobotLinkName") or ""): model
        for model in models
    }
    mesh_comparisons = {}
    model_link_comparisons = {}
    for link_name, pose in pose_by_link.items():
        expected_mesh = _matmul(base_world, _matrix(pose.matrix_base_from_mesh_mm))
        model = actual_models.get(link_name)
        actual_mesh = _matrix_from_node(model) if model is not None else None
        mesh_comparisons[link_name] = compare_transform(expected_mesh, actual_mesh)
        link_transform = model.GetParentTransformNode() if model is not None else None
        model_link_comparisons[link_name] = compare_transform(
            _matrix_from_node(link_transform) if link_transform is not None else None,
            actual_mesh,
        )
    mesh_available = all(item["available"] for item in mesh_comparisons.values())
    mesh_match = mesh_available and all(item["match"] is True for item in mesh_comparisons.values())
    model_link_available = all(item["available"] for item in model_link_comparisons.values())
    model_link_match = model_link_available and all(item["match"] is True for item in model_link_comparisons.values())
    native = _native_fk_comparisons(
        logic=logic,
        base_world=base_world,
        joint_positions_si=state["joints_si"],
        native_fk=native_fk,
    )
    robot_identity = _loaded_robot_description_identity(
        logic,
        native_robot_profile_fingerprint,
    )
    displayed_native = {}
    observed_links = {}
    for evidence_name, link_name in {
        "burr": "burr",
        "spindle": "pneumatic_spindle-Copy",
    }.items():
        pose = pose_by_link.get(link_name)
        model = actual_models.get(link_name)
        observed_mesh = _matrix_from_node(model) if model is not None else None
        observed_link = _observed_link_world_from_mesh(
            observed_mesh,
            pose.matrix_base_from_link_mm if pose is not None else None,
            pose.matrix_base_from_mesh_mm if pose is not None else None,
        )
        observed_links[evidence_name] = observed_link
        displayed_native[evidence_name] = compare_transform(
            native_fk.get(evidence_name),
            observed_link,
        )
    spindle_pose = pose_by_link.get("pneumatic_spindle-Copy")
    spindle_model = actual_models.get("pneumatic_spindle-Copy")
    tcp_base_mm = _matrix_m_to_mm(local_frames.get("dentobot_drill_tcp"))
    tcp_derivation = _derive_tcp_world_from_displayed_spindle(
        observed_spindle_mesh_world=(
            _matrix_from_node(spindle_model) if spindle_model is not None else None
        ),
        base_from_spindle_link_mm=(
            spindle_pose.matrix_base_from_link_mm if spindle_pose is not None else None
        ),
        base_from_spindle_mesh_mm=(
            spindle_pose.matrix_base_from_mesh_mm if spindle_pose is not None else None
        ),
        base_from_tcp_mm=tcp_base_mm,
    )
    observed_links["tcp"] = tcp_derivation["observed_tcp_world_ras_mm"]
    displayed_native["tcp"] = compare_transform(
        native_fk.get("tcp"),
        observed_links["tcp"],
    )
    displayed_native_available = all(item["available"] for item in displayed_native.values())
    displayed_native_match = (
        robot_identity["match"] is True
        and displayed_native_available
        and all(item["match"] is True for item in displayed_native.values())
    )
    return {
        "mesh_transforms_match": mesh_match,
        "mesh_transform_comparisons": mesh_comparisons,
        "model_link_transform_match": model_link_match,
        "model_link_transform_comparisons": model_link_comparisons,
        "native_exposed_fk_match": displayed_native_match,
        "native_exposed_fk_comparisons": native,
        "displayed_native_fk_match": displayed_native_match,
        "displayed_native_fk_comparisons": displayed_native,
        "robot_description_identity": robot_identity,
        "tcp_derivation": tcp_derivation,
        "derived_display_link_world_ras_mm": observed_links,
        "base_world_ras_mm": base_world,
        "displayed_model_world_ras_mm": {
            link_name: _matrix_from_node(actual_models.get(link_name))
            if actual_models.get(link_name) is not None
            else None
            for link_name in pose_by_link
        },
        "displayed_link_world_ras_mm": {
            link_name: _matrix_from_node(actual_models[link_name].GetParentTransformNode())
            if link_name in actual_models and actual_models[link_name].GetParentTransformNode() is not None
            else None
            for link_name in pose_by_link
        },
    }


def _review_node(slicer, class_name: str, role: str):
    nodes = [
        node
        for node in slicer.util.getNodesByClass(class_name)
        if node.GetAttribute("DENTOBOT.ReviewOnly") == "true"
        and node.GetAttribute("DENTOBOT.ReviewRole") == role
    ]
    if len(nodes) != 1:
        raise ReviewCaptureBlocked(
            f"Expected exactly one saved review {role!r} node, found {len(nodes)}."
        )
    return nodes[0]


def _review_labels(slicer, state_kind: str):
    expected_name = (
        "[Review] STATIC ENDPOINT labels"
        if state_kind == "static_endpoint"
        else "[Review] TRANSITION SAMPLE labels"
    )
    nodes = [
        node
        for node in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
        if node.GetAttribute("DENTOBOT.ReviewOnly") == "true"
        and node.GetName() == expected_name
    ]
    if len(nodes) != 1:
        raise ReviewCaptureBlocked(
            f"Expected exactly one saved review label node {expected_name!r}, found {len(nodes)}."
        )
    return [nodes[0]]


def _reloaded_review_scene(slicer, logic, parameter, state_kind: str):
    base = parameter.robotBaseTransform or next(
        (
            node
            for node in slicer.util.getNodesByClass("vtkMRMLLinearTransformNode")
            if node.GetAttribute("DENTOBOT.TransformRole") == logic.ROBOT_BASE_ROLE
        ),
        None,
    )
    if base is None:
        raise ReviewCaptureBlocked("Review MRB did not restore the robot base transform.")
    models = logic.robotModelNodes()
    transforms = logic.robotLinkTransformNodes()
    if len(models) != 7 or len(transforms) != 7:
        raise ReviewCaptureBlocked(
            "Review MRB did not restore exactly seven robot models and link transforms."
        )
    return {
        "base": base,
        "robot_models": models,
        "target_model": _review_node(
            slicer, "vtkMRMLModelNode", "[Review] FDI31 prepared target tooth (world RAS)"
        ),
        "template_model": _review_node(
            slicer, "vtkMRMLModelNode", "[Review] Final printable template (world RAS)"
        ),
        "corridor_model": _review_node(
            slicer, "vtkMRMLModelNode", "entry-target-corridor"
        ),
        "label_nodes": _review_labels(slicer, state_kind),
    }


def _pose_persistence_comparisons(before: Mapping[str, Any], after: Mapping[str, Any]):
    comparisons = {}
    before_models = before.get("displayed_model_world_ras_mm") or {}
    after_models = after.get("displayed_model_world_ras_mm") or {}
    before_links = before.get("displayed_link_world_ras_mm") or {}
    after_links = after.get("displayed_link_world_ras_mm") or {}
    for link_name in sorted(set(before_models) | set(after_models)):
        comparisons[f"model:{link_name}"] = compare_transform(
            before_models.get(link_name), after_models.get(link_name)
        )
    for link_name in sorted(set(before_links) | set(after_links)):
        comparisons[f"link:{link_name}"] = compare_transform(
            before_links.get(link_name), after_links.get(link_name)
        )
    available = bool(comparisons) and all(item["available"] for item in comparisons.values())
    match = available and all(item["match"] is True for item in comparisons.values())
    return {
        "available": available,
        "match": match,
        "comparisons": comparisons,
    }


def _geometry_comparisons(
    logic,
    target_model,
    template_model,
    native_records,
    *,
    target_source_evidence: Mapping[str, Any] | None = None,
    target_preparation: Mapping[str, Any] | None = None,
):
    target_record = native_records.get("selected-target-tooth")
    template_record = native_records.get("verified-final-template")
    if target_record is None or template_record is None:
        return {"match": False, "reason": "Native target/template geometry records are missing."}
    target_evidence = logic._collisionAuditPolydataEvidence(target_model.GetPolyData())
    template_evidence = logic._collisionAuditPolydataEvidence(template_model.GetPolyData())
    if target_source_evidence is None:
        source_fingerprint = target_model.GetAttribute(
            "DENTOBOT.ReviewTargetSourceFingerprint"
        )
        try:
            source_bounds = json.loads(
                target_model.GetAttribute("DENTOBOT.ReviewTargetSourceBoundsWorldRasMmJson")
                or "[]"
            )
        except (TypeError, json.JSONDecodeError):
            source_bounds = None
        target_source_evidence = {
            "fingerprint": source_fingerprint,
            "bounds": source_bounds,
        }
    if target_preparation is None:
        try:
            target_preparation = json.loads(
                target_model.GetAttribute("DENTOBOT.ReviewTargetPreparationJson")
                or "{}"
            )
        except (TypeError, json.JSONDecodeError):
            target_preparation = None
    target_source_match = bool(
        target_source_evidence
        and target_source_evidence.get("fingerprint") == target_record.get("source_fingerprint")
    )
    target_source_bounds = compare_bounds(
        target_record.get("source_bounds_world_ras_mm"),
        target_source_evidence.get("bounds") if target_source_evidence else None,
    )
    comparisons = {
        "target": {
            "source_fingerprint_match": target_source_match,
            "source_bounds": target_source_bounds,
            "fingerprint_match": target_evidence["fingerprint"] == target_record.get("prepared_world_fingerprint"),
            "bounds": compare_bounds(target_record.get("prepared_bounds_world_ras_mm"), target_evidence["bounds"]),
            "display_fingerprint": target_evidence["fingerprint"],
            "native_fingerprint": target_record.get("prepared_world_fingerprint"),
            "native_jaw_transform_application_count": target_record.get("jaw_transform_application_count"),
            "applied_jaw_transform_application_count": (
                target_preparation.get("applied_jaw_transform_application_count")
                if target_preparation
                else None
            ),
            "jaw_transform_fingerprint": target_record.get("jaw_transform_fingerprint"),
        },
        "final_template": {
            "fingerprint_match": template_evidence["fingerprint"] == template_record.get("prepared_world_fingerprint"),
            "bounds": compare_bounds(template_record.get("prepared_bounds_world_ras_mm"), template_evidence["bounds"]),
            "display_fingerprint": template_evidence["fingerprint"],
            "native_fingerprint": template_record.get("prepared_world_fingerprint"),
        },
    }
    match = all(
        item["fingerprint_match"]
        and item["bounds"].get("match") is True
        and (
            name != "target"
            or (
                item["source_fingerprint_match"]
                and item["source_bounds"].get("match") is True
                and item["native_jaw_transform_application_count"] == 1
                and item["applied_jaw_transform_application_count"] == 1
            )
        )
        for name, item in comparisons.items()
    )
    return {"match": match, "comparisons": comparisons}


def _state_labels(slicer, state_kind: str, state: Mapping[str, Any], scene: Mapping[str, Any]):
    if state_kind == "static_endpoint":
        return [
            _add_fiducial_labels(
                slicer,
                "[Review] STATIC ENDPOINT labels",
                [
                    ("FDI31 prepared target", scene["target"]),
                    ("Entry", scene["entry"]),
                    ("Target", scene["target"]),
                    (
                        "Endpoint TCP (derived spindle mesh + URDF; native checked)",
                        scene["state_points"]["evaluated_tcp"],
                    ),
                ],
            )
        ]
    return [
        _add_fiducial_labels(
            slicer,
            "[Review] TRANSITION SAMPLE labels",
            [
                ("Entry", scene["entry"]),
                ("Target", scene["target"]),
                ("Home TCP (offline FK)", scene["state_points"]["home_tcp"]),
                ("Requested endpoint TCP (offline FK)", scene["state_points"]["requested_endpoint_tcp"]),
                (
                    f"Evaluated TCP {state.get('sample_index')}/{state.get('total_sample_count')} "
                    f"f={state.get('interpolation_fraction')} (offline FK; native required)",
                    scene["state_points"]["evaluated_tcp"],
                ),
            ],
        )
    ]


def _fresh_scene(slicer, inspection_mrb: Path):
    if not slicer.util.loadScene(str(inspection_mrb)):
        raise ReviewCaptureBlocked(f"Could not load retained inspection MRB: {inspection_mrb}")
    slicer.util.selectModule("DENTOWorkflow")
    from DENTOWorkflow import DENTOWorkflowLogic

    logic = DENTOWorkflowLogic()
    parameter = logic.getParameterNode()
    if parameter is None:
        raise ReviewCaptureBlocked("Retained inspection MRB did not restore a DENTOWorkflow parameter node.")
    return logic, parameter


def _capture_one(
    slicer,
    inspection_mrb: Path,
    output_dir: Path,
    state_kind: str,
    state: Mapping[str, Any],
    native_records: Mapping[str, Mapping[str, Any]],
    native_fk: Mapping[str, Any],
    native_robot_profile_fingerprint: Any,
    output_stem: str,
) -> dict[str, Any]:
    from run_dentobot_fdi31_recovery_diagnostic import _capture_view, _process_events, file_sha256

    slicer.mrmlScene.Clear(0)
    logic, parameter = _fresh_scene(slicer, inspection_mrb)
    scene = _prepare_display_scene(
        slicer,
        logic,
        parameter,
        state_kind,
        state,
        native_records.get("selected-target-tooth") or {},
    )
    geometry = _geometry_comparisons(
        logic,
        scene["target_model"],
        scene["template_model"],
        native_records,
        target_source_evidence=scene["target_source_evidence"],
        target_preparation=scene["target_preparation"],
    )
    display_robot = _display_robot_comparisons(
        logic,
        scene["base"],
        scene["robot_models"],
        state,
        native_fk,
        native_robot_profile_fingerprint,
    )
    # A saved P2 packet contains endpoint native FK but not a native FK matrix
    # for the rejected interpolated sample.  Do not silently substitute offline
    # FK and call it native transition evidence.
    evaluated_native_available = bool(state.get("native_fk_world_ras_mm"))
    display_robot["native_evaluated_sample_fk_match"] = (
        display_robot["native_exposed_fk_match"] if state_kind == "static_endpoint" else evaluated_native_available
    )
    readiness = review_capture_readiness(
        state_kind=state_kind,
        state=state,
        geometry=geometry,
        display_robot=display_robot,
        saved_pose_required=False,
    )
    pre_save = {
        "state_kind": state_kind,
        "state": dict(state),
        "geometry": geometry,
        "display_robot": display_robot,
        "case_foundation_display_repair": scene["case_foundation_display_repair"],
        "saved_jaw_preparation": scene["saved_jaw_preparation"],
        "review_parameter_joint_state": scene["review_parameter_joint_state"],
        "readiness": readiness,
    }
    if not readiness["ready"]:
        return {
            "status": "BLOCKED",
            "phase": "pre_save_parity",
            "pre_save": pre_save,
            "reason": readiness["blocked_reason"],
        }
    for label_node in _state_labels(slicer, state_kind, state, scene):
        scene.setdefault("label_nodes", []).append(label_node)
    output_dir.mkdir(parents=True, exist_ok=True)
    scene_path = output_dir / f"{output_stem}.mrb"
    if not slicer.util.saveScene(str(scene_path)):
        raise ReviewCaptureBlocked(f"Could not save review scene: {scene_path}")
    pre_reload_ids = [str(node.GetID()) for node in logic.robotLinkTransformNodes()]
    slicer.mrmlScene.Clear(0)
    logic, parameter = _fresh_scene(slicer, scene_path)
    try:
        reloaded_scene = _reloaded_review_scene(slicer, logic, parameter, state_kind)
    except ReviewCaptureBlocked as exc:
        return {
            "status": "BLOCKED",
            "phase": "save_reopen",
            "reason": str(exc),
            "pre_save_transform_ids": pre_reload_ids,
            "reloaded_model_count": len(logic.robotModelNodes()),
            "reloaded_transform_count": len(logic.robotLinkTransformNodes()),
        }
    reloaded_state = dict(state)
    reloaded_geometry = _geometry_comparisons(
        logic,
        reloaded_scene["target_model"],
        reloaded_scene["template_model"],
        native_records,
    )
    reloaded_robot = _display_robot_comparisons(
        logic,
        reloaded_scene["base"],
        reloaded_scene["robot_models"],
        reloaded_state,
        native_fk,
        native_robot_profile_fingerprint,
    )
    reloaded_robot["native_evaluated_sample_fk_match"] = (
        reloaded_robot["native_exposed_fk_match"] if state_kind == "static_endpoint" else evaluated_native_available
    )
    pose_persistence = _pose_persistence_comparisons(display_robot, reloaded_robot)
    persistence = {
        "robot_models": len(reloaded_scene["robot_models"]) == 7,
        "link_transforms": len(logic.robotLinkTransformNodes()) == 7,
        "review_pose_attributes": all(
            node.GetAttribute("DENTOBOT.ReviewOnlyJointStateSiJson")
            for node in [
                reloaded_scene["base"],
                *reloaded_scene["robot_models"],
                *logic.robotLinkTransformNodes(),
            ]
        ),
        "world_transform_match": pose_persistence["match"],
    }
    reloaded_robot["saved_pose_persistence_match"] = all(persistence.values())
    reloaded_readiness = review_capture_readiness(
        state_kind=state_kind,
        state=state,
        geometry=reloaded_geometry,
        display_robot=reloaded_robot,
    )
    if not reloaded_readiness["ready"]:
        return {
            "status": "BLOCKED",
            "phase": "post_reopen_parity",
            "pre_save": pre_save,
            "post_reopen": {
                "geometry": reloaded_geometry,
                "display_robot": reloaded_robot,
                "persistence": persistence,
                "pose_persistence": pose_persistence,
                "readiness": reloaded_readiness,
            },
            "reason": reloaded_readiness["blocked_reason"],
        }
    focus_nodes = [
        reloaded_scene["target_model"],
        reloaded_scene["template_model"],
        reloaded_scene["corridor_model"],
        *reloaded_scene["robot_models"],
        *reloaded_scene.get("label_nodes", []),
    ]
    if state_kind == "static_endpoint":
        label = (
            "STATIC ENDPOINT | reopened review scene | exact retained endpoint | "
            "phase-aware static_state: REJECTED | native pair: final template ↔ spindle | "
            "contact point/depth/clearance: UNKNOWN | review only"
        )
    else:
        label = (
            "TRANSITION SAMPLE | reopened review scene | actual evaluated sample "
            f"{state.get('sample_index')}/{state.get('total_sample_count')} | "
            f"fraction {state.get('interpolation_fraction')} | Home → endpoint corridor rejection | "
            "NOT r13 insertion/onset | review only"
        )
    context_image_path = output_dir / f"{output_stem}-context.png"
    context_capture = _capture_view(
        slicer,
        context_image_path,
        focus_nodes,
        label=label + " | context",
        camera_nodes=[reloaded_scene["target_model"], reloaded_scene["template_model"], *reloaded_scene["robot_models"]],
    )
    closeup_image_path = output_dir / f"{output_stem}-closeup.png"
    closeup_capture = _capture_view(
        slicer,
        closeup_image_path,
        focus_nodes,
        label=label + " | spindle/burr/TCP close-up",
        camera_nodes=[
            reloaded_scene["target_model"],
            reloaded_scene["template_model"],
            *[
                model
                for model in reloaded_scene["robot_models"]
                if str(model.GetAttribute("DENTOBOT.RobotLinkName") or "")
                in {"pneumatic_spindle-Copy", "burr"}
            ],
        ],
    )
    _process_events(slicer, 0.2)
    return {
        "status": "PASS",
        "state_kind": state_kind,
        "scene": {"path": str(scene_path), "sha256": file_sha256(scene_path)},
        "image": context_capture,
        "images": [context_capture, closeup_capture],
        "pre_save": pre_save,
        "post_reopen": {
            "geometry": reloaded_geometry,
            "display_robot": reloaded_robot,
            "persistence": persistence,
            "pose_persistence": pose_persistence,
            "readiness": reloaded_readiness,
        },
    }


def deferred_transition_report(state: Mapping[str, Any]) -> dict[str, Any]:
    """Keep transition numbers while explicitly omitting its image capture."""

    native_fk_available = bool(state.get("native_fk_world_ras_mm"))
    return {
        "status": "NOT_RUN",
        "state_kind": "transition_sample",
        "runtime_entered": False,
        "native_fk_available": native_fk_available,
        "reason": (
            "Endpoint-only review; transition image deferred because saved native "
            "evaluated-sample FK is unavailable."
            if not native_fk_available
            else "Endpoint-only review; transition capture was explicitly deferred."
        ),
        "state": dict(state),
    }


def run(slicer) -> dict[str, Any]:
    root = Path(os.environ.get("DENTOBOT_C1_RECAPTURE_SOURCE_ROOT", "/workspace/data/Slicer_Saved/SampleStudy1/FDI31"))
    retained = root / "planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected"
    inspection_mrb = Path(os.environ.get("DENTOBOT_C1_RECAPTURE_INSPECTION_MRB", retained / "inspection-scene/fdi31-p2-rejected-state.mrb"))
    rejected_path = Path(os.environ.get("DENTOBOT_C1_RECAPTURE_REJECTED_STATE", retained / "rejected_state.json"))
    identity_path = Path(os.environ.get("DENTOBOT_C1_RECAPTURE_STATE_IDENTITY", retained / "state_identity.json"))
    output_dir = Path(os.environ.get("DENTOBOT_C1_RECAPTURE_OUTPUT", retained / "display-only-recapture-20260915-corrected"))
    endpoint_only = os.environ.get("DENTOBOT_C1_RECAPTURE_ENDPOINT_ONLY", "").strip().lower() == "true"
    rejected = _read_json(rejected_path)
    identity = _read_json(identity_path)
    states = load_review_state(rejected, identity)
    native_records = native_geometry_records(identity)
    static_state = states["endpoint"]
    native_fk = static_state["native_fk_world_ras_mm"]
    native_robot_profile_fingerprint = identity.get("robot_profile_fingerprint")
    result = {
        "schema_version": "2.0",
        "review_type": (
            "offline_display_only_endpoint_review"
            if endpoint_only
            else "offline_display_only_recapture_source_corrected"
        ),
        "capture_mode": "endpoint_only" if endpoint_only else "endpoint_and_transition",
        "run_id": str(rejected.get("run_id") or ""),
        "operator_confirmed_in_this_run": False,
        "operator_acceptance": "NOT_RECORDED",
        "source": {
            "inspection_mrb": str(inspection_mrb),
            "rejected_state_json": str(rejected_path),
            "state_identity_json": str(identity_path),
        },
        "runtime_boundary": {
            "ros_launched": False,
            "moveit_launched": False,
            "native_diagnostics_run": False,
            "planner_run": False,
            "controller_connected": False,
            "spindle_activated": False,
            "trajectory_executed": False,
            "collision_policy_changed": False,
            "actual_template_moved": False,
            "anatomy_or_tool_geometry_changed": False,
        },
        "state_separation": {
            "endpoint": static_state,
            "transition": states["transition"],
            "same_scene_reused": False,
            "fresh_scene_per_capture": True,
        },
        "static_endpoint": _capture_one(
            slicer,
            inspection_mrb,
            output_dir,
            "static_endpoint",
            static_state,
            native_records,
            native_fk,
            native_robot_profile_fingerprint,
            "01-static-endpoint",
        ),
    }
    transition_state = states["transition"]
    if endpoint_only:
        result["transition_sample"] = deferred_transition_report(transition_state)
        result["status"] = (
            "PASS" if result["static_endpoint"].get("status") == "PASS" else "BLOCKED"
        )
        return result
    # Do not present a transition frame unless native FK for its evaluated sample
    # is actually saved.  The retained P2 packet contains only its joint vector.
    result["transition_sample"] = _capture_one(
        slicer,
        inspection_mrb,
        output_dir,
        "transition_sample",
        transition_state,
        native_records,
        transition_state["native_fk_world_ras_mm"],
        native_robot_profile_fingerprint,
        "02-transition-sample-1-of-134",
    )
    result["status"] = (
        "PASS"
        if result["static_endpoint"].get("status") == "PASS"
        and result["transition_sample"].get("status") == "PASS"
        else "BLOCKED"
    )
    return result


def main() -> int:
    import slicer

    try:
        result = run(slicer)
    except Exception as exc:
        endpoint_only = os.environ.get("DENTOBOT_C1_RECAPTURE_ENDPOINT_ONLY", "").strip().lower() == "true"
        result = {
            "schema_version": "2.0",
            "review_type": (
                "offline_display_only_endpoint_review"
                if endpoint_only
                else "offline_display_only_recapture_source_corrected"
            ),
            "capture_mode": "endpoint_only" if endpoint_only else "endpoint_and_transition",
            "status": "ERROR",
            "operator_confirmed_in_this_run": False,
            "operator_acceptance": "NOT_RECORDED",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    output = Path(os.environ.get("DENTOBOT_C1_RECAPTURE_MANIFEST", "/tmp/dentobot-c1-display-only-recapture-corrected.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("DENTOBOT_C1_DISPLAY_ONLY_RECAPTURE " + json.dumps(result, sort_keys=True), flush=True)
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    import slicer

    slicer.util.exit(main())
