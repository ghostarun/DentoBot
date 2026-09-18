"""Virtual Open-Mouth Articulator — pure geometry (Slicer RAS mm).

TRL-4 simulation prior: one mean-value q kinematic solver with rotation plus
coupled condylar-axis translation. See Workspace/docs/
DentoWorkflow_Virtual_Open_Mouth_Articulator_Agent_Prompt.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Any

import numpy as np

OPEN_MOUTH_MODEL_VERSION = "1.0"
HINGE_MODEL_SCHEMA = "VirtualOpenMouthArticulatorV1"
SOLVER_NAME = "virtual_open_mouth_articulator"
KINEMATICS_SOURCE = "MEAN_VALUE_PRIOR"

LEGACY_HINGE_SCHEMA = "AnatomyDirectedPureTMJHingeRotationV2"


class HingeSource(str, Enum):
    MANUAL = "MANUAL"
    PATIENT_CONDYLES_ESTIMATED = "PATIENT_CONDYLES_ESTIMATED"
    ARCH_INFERRED = "ARCH_INFERRED"
    PATIENT_CONDYLES_SEGMENTED = "PATIENT_CONDYLES_SEGMENTED"


@dataclass(frozen=True)
class VirtualArticulatorConfig:
    bonwill_side_mm: float = 102.0
    intercondylar_distance_mm: float = 100.0
    intercondylar_distance_min_mm: float = 70.0
    intercondylar_distance_max_mm: float = 130.0
    minimum_condylar_separation_mm: float = 20.0
    maximum_condylar_superior_offset_mm: float = 15.0
    axis_transverse_min_dot: float = 0.85
    condyle_posterior_min_mm: float = 5.0
    condyle_superior_min_mm: float = 0.0
    balkwill_angle_deg: float = 22.0
    condylar_guidance_angle_deg: float = 30.0
    arch_scale_min: float = 0.85
    arch_scale_max: float = 1.15
    reference_arch_width_mm: float = 50.0
    theta_max_deg: float = 42.0
    translation_max_mm: float = 14.0
    translation_profile_exponent: float = 1.35
    opening_tolerance_mm: float = 0.1
    bisection_iterations: int = 48


@dataclass(frozen=True)
class DentalFrame:
    origin_mm: np.ndarray
    x_hat: np.ndarray
    y_hat: np.ndarray
    z_hat: np.ndarray


@dataclass(frozen=True)
class VirtualCondylarAxis:
    left_point_mm: np.ndarray
    right_point_mm: np.ndarray
    midpoint_mm: np.ndarray
    axis_direction: np.ndarray
    source: HingeSource
    confidence: float


@dataclass(frozen=True)
class ArticulatorResult:
    matrix_world_ras: np.ndarray
    q: float
    theta_deg: float
    translation_mm: float
    requested_opening_mm: float
    achieved_opening_mm: float
    hinge_source: HingeSource
    axis_confidence: float
    closed_gap_mm: float
    provenance: dict[str, Any] = field(default_factory=dict)


def _as_point3(values: np.ndarray, name: str) -> np.ndarray:
    point = np.asarray(values, dtype=float).reshape(3)
    if not np.all(np.isfinite(point)):
        raise ValueError(f"{name} must be finite 3D coordinates.")
    return point


def _normalize(vector: np.ndarray, name: str) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-9:
        raise ValueError(f"{name} direction is degenerate.")
    return vector / norm


def rodrigues_rotation_3x3(axis_unit: np.ndarray, angle_rad: float) -> np.ndarray:
    axis = _normalize(_as_point3(axis_unit, "axis"), "axis")
    angle = float(angle_rad)
    if not isfinite(angle):
        raise ValueError("Rotation angle must be finite.")
    x, y, z = axis
    cosine, sine = np.cos(angle), np.sin(angle)
    one_minus = 1.0 - cosine
    return np.asarray(
        (
            (
                cosine + x * x * one_minus,
                x * y * one_minus - z * sine,
                x * z * one_minus + y * sine,
            ),
            (
                y * x * one_minus + z * sine,
                cosine + y * y * one_minus,
                y * z * one_minus - x * sine,
            ),
            (
                z * x * one_minus - y * sine,
                z * y * one_minus + x * sine,
                cosine + z * z * one_minus,
            ),
        ),
        dtype=float,
    )


def compose_mandible_open_transform(
    hinge_midpoint_mm: np.ndarray,
    axis_unit: np.ndarray,
    theta_rad: float,
    hinge_midpoint_after_mm: np.ndarray,
) -> np.ndarray:
    """Rigid transform matching spec §12 multiply order.

    T = Translate(Hq) @ Rotate(A, theta) @ Translate(-H0)
    Implemented as a single 4×4 with upper-left R and translation
    t = Hq - R @ H0.
    """

    h0 = _as_point3(hinge_midpoint_mm, "hinge midpoint")
    hq = _as_point3(hinge_midpoint_after_mm, "translated hinge midpoint")
    rotation = rodrigues_rotation_3x3(axis_unit, theta_rad)
    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = hq - rotation @ h0
    return matrix


def transform_point(matrix: np.ndarray, point_mm: np.ndarray) -> np.ndarray:
    mat = np.asarray(matrix, dtype=float)
    if mat.shape != (4, 4):
        raise ValueError("Transform must be 4×4.")
    point = _as_point3(point_mm, "point")
    homogeneous = np.append(point, 1.0)
    return (mat @ homogeneous)[:3]


def interincisal_distance_mm(
    upper_incisor_mm: np.ndarray,
    lower_incisor_mm: np.ndarray,
    mandible_transform: np.ndarray,
) -> float:
    upper = _as_point3(upper_incisor_mm, "upper incisor")
    lower_open = transform_point(mandible_transform, lower_incisor_mm)
    return float(np.linalg.norm(upper - lower_open))


def dental_frame_from_landmarks(
    condyle_left_mm: np.ndarray,
    condyle_right_mm: np.ndarray,
    lower_incisor_mm: np.ndarray,
) -> DentalFrame:
    left = _as_point3(condyle_left_mm, "left condyle")
    right = _as_point3(condyle_right_mm, "right condyle")
    incisor = _as_point3(lower_incisor_mm, "lower incisor")
    midpoint = 0.5 * (left + right)
    x_hat = _normalize(right - left, "left-right")
    raw_anterior = incisor - midpoint
    raw_anterior -= float(np.dot(raw_anterior, x_hat)) * x_hat
    y_hat = _normalize(raw_anterior, "anterior")
    z_hat = _normalize(np.cross(x_hat, y_hat), "superior")
    if float(z_hat[2]) < 0.0:
        z_hat = -z_hat
        y_hat = _normalize(np.cross(z_hat, x_hat), "anterior")
    return DentalFrame(origin_mm=incisor.copy(), x_hat=x_hat, y_hat=y_hat, z_hat=z_hat)


def guidance_direction(frame: DentalFrame, guidance_angle_deg: float) -> np.ndarray:
    gamma = np.radians(float(guidance_angle_deg))
    direction = np.cos(gamma) * frame.y_hat - np.sin(gamma) * frame.z_hat
    return _normalize(direction, "condylar guidance")


def virtual_condylar_axis_from_points(
    condyle_left_mm: np.ndarray,
    condyle_right_mm: np.ndarray,
    source: HingeSource,
    confidence: float,
) -> VirtualCondylarAxis:
    left = _as_point3(condyle_left_mm, "left condyle")
    right = _as_point3(condyle_right_mm, "right condyle")
    midpoint = 0.5 * (left + right)
    axis = _normalize(right - left, "condylar axis")
    conf = float(confidence)
    if not isfinite(conf) or conf < 0.0 or conf > 1.0:
        raise ValueError("Axis confidence must lie in [0, 1].")
    return VirtualCondylarAxis(
        left_point_mm=left,
        right_point_mm=right,
        midpoint_mm=midpoint,
        axis_direction=axis,
        source=source,
        confidence=conf,
    )


def virtual_condylar_axis_manual(
    condyle_left_mm: np.ndarray,
    condyle_right_mm: np.ndarray,
) -> VirtualCondylarAxis:
    return virtual_condylar_axis_from_points(
        condyle_left_mm,
        condyle_right_mm,
        HingeSource.MANUAL,
        1.0,
    )


def compare_condyle_centres(
    auto_left_mm: np.ndarray,
    auto_right_mm: np.ndarray,
    manual_left_mm: np.ndarray,
    manual_right_mm: np.ndarray,
) -> dict[str, float]:
    auto_left = _as_point3(auto_left_mm, "auto left condyle")
    auto_right = _as_point3(auto_right_mm, "auto right condyle")
    manual_left = _as_point3(manual_left_mm, "manual left condyle")
    manual_right = _as_point3(manual_right_mm, "manual right condyle")
    auto_sep = float(np.linalg.norm(auto_left - auto_right))
    manual_sep = float(np.linalg.norm(manual_left - manual_right))
    return {
        "autoSeparationMm": auto_sep,
        "manualSeparationMm": manual_sep,
        "separationDeltaMm": auto_sep - manual_sep,
        "leftOffsetMm": float(np.linalg.norm(auto_left - manual_left)),
        "rightOffsetMm": float(np.linalg.norm(auto_right - manual_right)),
    }


def validate_patient_condylar_axis(
    axis: VirtualCondylarAxis,
    frame: DentalFrame,
    lower_incisor_mm: np.ndarray,
    config: VirtualArticulatorConfig | None = None,
) -> dict[str, float]:
    config = config or VirtualArticulatorConfig()
    incisor = _as_point3(lower_incisor_mm, "lower incisor")
    left = _as_point3(axis.left_point_mm, "left condyle")
    right = _as_point3(axis.right_point_mm, "right condyle")
    if float(left[0]) >= float(right[0]):
        raise ValueError(
            "Left and right condylar landmarks appear side-swapped in patient RAS."
        )
    separation = float(np.linalg.norm(left - right))
    superior_offset = abs(float(left[2] - right[2]))
    if separation < float(config.minimum_condylar_separation_mm):
        raise ValueError("The bilateral condylar landmarks are implausibly close.")
    if superior_offset > float(config.maximum_condylar_superior_offset_mm):
        raise ValueError(
            "The condylar landmarks are not at homologous superior levels."
        )
    if separation < float(config.intercondylar_distance_min_mm):
        raise ValueError("The intercondylar span is below the plausible patient range.")
    if separation > float(config.intercondylar_distance_max_mm):
        raise ValueError("The intercondylar span exceeds the plausible patient range.")
    transverse = abs(float(np.dot(axis.axis_direction, frame.x_hat)))
    if transverse < float(config.axis_transverse_min_dot):
        raise ValueError("The condylar axis is not sufficiently transverse.")
    for label, point in (("left", left), ("right", right)):
        # Patient RAS: condyles are typically posterior (less negative Y) and
        # superior (greater Z) than the lower incisor in this workflow.
        if abs(float(incisor[1]) - float(point[1])) < float(
            config.condyle_posterior_min_mm
        ):
            raise ValueError(
                f"The {label} condylar centre is not posterior enough relative to the incisor."
            )
        if float(point[2]) - float(incisor[2]) < float(config.condyle_superior_min_mm):
            raise ValueError(
                f"The {label} condylar centre is not superior enough relative to the incisor."
            )
    return {
        "separationMm": separation,
        "superiorOffsetMm": superior_offset,
        "transverseAlignment": transverse,
    }


def estimate_arch_scale_from_lateral_width(
    left_lateral_mm: np.ndarray,
    right_lateral_mm: np.ndarray,
    config: VirtualArticulatorConfig | None = None,
) -> tuple[float, float]:
    config = config or VirtualArticulatorConfig()
    width = float(np.linalg.norm(_as_point3(right_lateral_mm, "right") - _as_point3(left_lateral_mm, "left")))
    if width <= 1e-6:
        return 1.0, 0.35
    raw = width / float(config.reference_arch_width_mm)
    scale = float(np.clip(raw, config.arch_scale_min, config.arch_scale_max))
    confidence = 1.0 if config.arch_scale_min <= raw <= config.arch_scale_max else 0.6
    return scale, confidence


def virtual_condylar_axis_arch_inferred(
    frame: DentalFrame,
    lower_incisor_mm: np.ndarray,
    config: VirtualArticulatorConfig | None = None,
    arch_scale: float = 1.0,
) -> VirtualCondylarAxis:
    config = config or VirtualArticulatorConfig()
    scale = float(arch_scale)
    if not isfinite(scale) or scale <= 0.0:
        raise ValueError("Arch scale must be positive and finite.")
    bonwill = scale * float(config.bonwill_side_mm)
    span = scale * float(config.intercondylar_distance_mm)
    if bonwill <= span * 0.5:
        raise ValueError("Bonwill side length must exceed half the intercondylar span.")
    incisor = _as_point3(lower_incisor_mm, "lower incisor")
    beta = np.radians(float(config.balkwill_angle_deg))
    radius = float(np.sqrt(bonwill * bonwill - (span * 0.5) ** 2))
    midpoint = (
        incisor
        - radius * np.cos(beta) * frame.y_hat
        + radius * np.sin(beta) * frame.z_hat
    )
    left = midpoint - (span * 0.5) * frame.x_hat
    right = midpoint + (span * 0.5) * frame.x_hat
    return virtual_condylar_axis_from_points(
        left,
        right,
        HingeSource.ARCH_INFERRED,
        min(1.0, 0.5 + 0.5 * scale),
    )


def validate_arch_inferred_axis(
    axis: VirtualCondylarAxis,
    frame: DentalFrame,
    lower_incisor_mm: np.ndarray,
    config: VirtualArticulatorConfig | None = None,
) -> dict[str, float]:
    config = config or VirtualArticulatorConfig()
    if axis.source is not HingeSource.ARCH_INFERRED:
        raise ValueError("Expected an arch-inferred condylar axis.")
    return validate_patient_condylar_axis(axis, frame, lower_incisor_mm, config)


@dataclass(frozen=True)
class HingeResolution:
    axis: VirtualCondylarAxis
    frame: DentalFrame
    diagnostics: dict[str, Any]


def resolve_virtual_condylar_axis(
    *,
    manual_condyle_left_mm: np.ndarray,
    manual_condyle_right_mm: np.ndarray,
    lower_incisor_mm: np.ndarray,
    segmented_condyle_left_mm: np.ndarray | None = None,
    segmented_condyle_right_mm: np.ndarray | None = None,
    lateral_arch_left_mm: np.ndarray | None = None,
    lateral_arch_right_mm: np.ndarray | None = None,
    force_manual_axis: bool = False,
    config: VirtualArticulatorConfig | None = None,
) -> HingeResolution:
    config = config or VirtualArticulatorConfig()
    frame = dental_frame_from_landmarks(
        manual_condyle_left_mm,
        manual_condyle_right_mm,
        lower_incisor_mm,
    )
    diagnostics: dict[str, Any] = {"frameOriginMm": frame.origin_mm.tolist()}
    if force_manual_axis:
        axis = virtual_condylar_axis_manual(
            manual_condyle_left_mm,
            manual_condyle_right_mm,
        )
        diagnostics["selection"] = "MANUAL_OVERRIDE"
        return HingeResolution(axis=axis, frame=frame, diagnostics=diagnostics)

    if segmented_condyle_left_mm is not None and segmented_condyle_right_mm is not None:
        comparison = compare_condyle_centres(
            segmented_condyle_left_mm,
            segmented_condyle_right_mm,
            manual_condyle_left_mm,
            manual_condyle_right_mm,
        )
        diagnostics["segmentedComparison"] = comparison
        axis = virtual_condylar_axis_from_points(
            segmented_condyle_left_mm,
            segmented_condyle_right_mm,
            HingeSource.PATIENT_CONDYLES_SEGMENTED,
            0.95,
        )
        try:
            diagnostics["patientValidation"] = validate_patient_condylar_axis(
                axis,
                frame,
                lower_incisor_mm,
                config,
            )
            diagnostics["selection"] = axis.source.value
            return HingeResolution(axis=axis, frame=frame, diagnostics=diagnostics)
        except ValueError as exc:
            diagnostics["patientRejected"] = str(exc)

    if lateral_arch_left_mm is not None and lateral_arch_right_mm is not None:
        scale, scale_confidence = estimate_arch_scale_from_lateral_width(
            lateral_arch_left_mm,
            lateral_arch_right_mm,
            config,
        )
    else:
        scale, scale_confidence = 1.0, 0.35
    diagnostics["archScale"] = scale
    diagnostics["archScaleConfidence"] = scale_confidence
    axis = virtual_condylar_axis_arch_inferred(
        frame,
        lower_incisor_mm,
        config,
        scale,
    )
    try:
        diagnostics["archValidation"] = validate_arch_inferred_axis(
            axis,
            frame,
            lower_incisor_mm,
            config,
        )
    except ValueError as exc:
        diagnostics["archRejected"] = str(exc)
        axis = virtual_condylar_axis_manual(
            manual_condyle_left_mm,
            manual_condyle_right_mm,
        )
        diagnostics["selection"] = "MANUAL_FALLBACK"
        diagnostics["manualFallbackReason"] = str(exc)
        return HingeResolution(axis=axis, frame=frame, diagnostics=diagnostics)
    diagnostics["selection"] = axis.source.value
    return HingeResolution(axis=axis, frame=frame, diagnostics=diagnostics)


def _attach_resolution_provenance(
    result: ArticulatorResult,
    resolution: HingeResolution,
) -> ArticulatorResult:
    provenance = dict(result.provenance)
    provenance["hingeResolution"] = resolution.diagnostics
    return ArticulatorResult(
        matrix_world_ras=result.matrix_world_ras,
        q=result.q,
        theta_deg=result.theta_deg,
        translation_mm=result.translation_mm,
        requested_opening_mm=result.requested_opening_mm,
        achieved_opening_mm=result.achieved_opening_mm,
        hinge_source=result.hinge_source,
        axis_confidence=result.axis_confidence,
        closed_gap_mm=result.closed_gap_mm,
        provenance=provenance,
    )


def solve_patient_condyle_opening(
    condyle_left_mm: np.ndarray,
    condyle_right_mm: np.ndarray,
    upper_incisor_mm: np.ndarray,
    lower_incisor_mm: np.ndarray,
    target_opening_mm: float,
    source: HingeSource = HingeSource.PATIENT_CONDYLES_SEGMENTED,
    confidence: float = 0.95,
    config: VirtualArticulatorConfig | None = None,
) -> ArticulatorResult:
    config = config or VirtualArticulatorConfig()
    frame = dental_frame_from_landmarks(
        condyle_left_mm,
        condyle_right_mm,
        lower_incisor_mm,
    )
    axis = virtual_condylar_axis_from_points(
        condyle_left_mm,
        condyle_right_mm,
        source,
        confidence,
    )
    validate_patient_condylar_axis(axis, frame, lower_incisor_mm, config)
    return solve_opening_for_target_mm(
        target_opening_mm,
        axis,
        frame,
        upper_incisor_mm,
        lower_incisor_mm,
        config,
    )


def solve_arch_inferred_opening(
    manual_condyle_left_mm: np.ndarray,
    manual_condyle_right_mm: np.ndarray,
    upper_incisor_mm: np.ndarray,
    lower_incisor_mm: np.ndarray,
    target_opening_mm: float,
    arch_scale: float = 1.0,
    config: VirtualArticulatorConfig | None = None,
) -> ArticulatorResult:
    config = config or VirtualArticulatorConfig()
    frame = dental_frame_from_landmarks(
        manual_condyle_left_mm,
        manual_condyle_right_mm,
        lower_incisor_mm,
    )
    axis = virtual_condylar_axis_arch_inferred(
        frame,
        lower_incisor_mm,
        config,
        arch_scale,
    )
    validate_arch_inferred_axis(axis, frame, lower_incisor_mm, config)
    return solve_opening_for_target_mm(
        target_opening_mm,
        axis,
        frame,
        upper_incisor_mm,
        lower_incisor_mm,
        config,
    )


def solve_auto_opening(
    *,
    manual_condyle_left_mm: np.ndarray,
    manual_condyle_right_mm: np.ndarray,
    upper_incisor_mm: np.ndarray,
    lower_incisor_mm: np.ndarray,
    target_opening_mm: float,
    segmented_condyle_left_mm: np.ndarray | None = None,
    segmented_condyle_right_mm: np.ndarray | None = None,
    lateral_arch_left_mm: np.ndarray | None = None,
    lateral_arch_right_mm: np.ndarray | None = None,
    force_manual_axis: bool = False,
    config: VirtualArticulatorConfig | None = None,
) -> ArticulatorResult:
    resolution = resolve_virtual_condylar_axis(
        manual_condyle_left_mm=manual_condyle_left_mm,
        manual_condyle_right_mm=manual_condyle_right_mm,
        lower_incisor_mm=lower_incisor_mm,
        segmented_condyle_left_mm=segmented_condyle_left_mm,
        segmented_condyle_right_mm=segmented_condyle_right_mm,
        lateral_arch_left_mm=lateral_arch_left_mm,
        lateral_arch_right_mm=lateral_arch_right_mm,
        force_manual_axis=force_manual_axis,
        config=config,
    )
    result = solve_opening_for_target_mm(
        target_opening_mm,
        resolution.axis,
        resolution.frame,
        upper_incisor_mm,
        lower_incisor_mm,
        config,
    )
    return _attach_resolution_provenance(result, resolution)


def opening_at_q(
    q: float,
    axis: VirtualCondylarAxis,
    frame: DentalFrame,
    config: VirtualArticulatorConfig,
    lower_incisor_mm: np.ndarray,
) -> tuple[np.ndarray, float, float]:
    q_value = float(q)
    if not isfinite(q_value) or q_value < 0.0 or q_value > 1.0:
        raise ValueError("Opening parameter q must lie in [0, 1].")
    theta_rad = np.radians(config.theta_max_deg * q_value)
    translation_mag = config.translation_max_mm * (q_value ** config.translation_profile_exponent)
    guidance = guidance_direction(frame, config.condylar_guidance_angle_deg)
    h0 = axis.midpoint_mm
    hq = h0 + translation_mag * guidance
    matrix = compose_mandible_open_transform(
        h0,
        axis.axis_direction,
        theta_rad,
        hq,
    )
    return matrix, float(np.degrees(theta_rad)), float(translation_mag)


def solve_opening_for_target_mm(
    target_opening_mm: float,
    axis: VirtualCondylarAxis,
    frame: DentalFrame,
    upper_incisor_mm: np.ndarray,
    lower_incisor_mm: np.ndarray,
    config: VirtualArticulatorConfig | None = None,
) -> ArticulatorResult:
    config = config or VirtualArticulatorConfig()
    target = float(target_opening_mm)
    if not isfinite(target) or target <= 0.0:
        raise ValueError("Target interincisal opening must be positive and finite.")
    upper = _as_point3(upper_incisor_mm, "upper incisor")
    lower = _as_point3(lower_incisor_mm, "lower incisor")
    identity = np.eye(4, dtype=float)
    closed_gap = interincisal_distance_mm(upper, lower, identity)
    if closed_gap >= target - config.opening_tolerance_mm:
        raise ValueError(
            "The closed interincisal distance already reaches the requested opening."
        )
    max_matrix, _, _ = opening_at_q(1.0, axis, frame, config, lower)
    max_gap = interincisal_distance_mm(upper, lower, max_matrix)
    if max_gap + config.opening_tolerance_mm < target:
        raise ValueError(
            "The requested opening exceeds the configured articulator profile maximum."
        )
    low = 0.0
    high = 1.0
    best_q = 0.0
    best_matrix = identity
    best_theta = 0.0
    best_translation = 0.0
    best_gap = closed_gap
    for _ in range(config.bisection_iterations):
        mid = 0.5 * (low + high)
        matrix, theta_deg, translation_mm = opening_at_q(
            mid, axis, frame, config, lower
        )
        gap = interincisal_distance_mm(upper, lower, matrix)
        if gap < target:
            low = mid
        else:
            high = mid
        if abs(gap - target) < abs(best_gap - target):
            best_q = mid
            best_matrix = matrix
            best_theta = theta_deg
            best_translation = translation_mm
            best_gap = gap
        if abs(gap - target) <= config.opening_tolerance_mm:
            best_q = mid
            best_matrix = matrix
            best_theta = theta_deg
            best_translation = translation_mm
            best_gap = gap
            break
    if best_gap > target + config.opening_tolerance_mm:
        raise ValueError(
            "The configured articulator profile cannot reach the requested opening."
        )
    provenance = {
        "solver": SOLVER_NAME,
        "openMouthModelVersion": OPEN_MOUTH_MODEL_VERSION,
        "hingeModelSchema": HINGE_MODEL_SCHEMA,
        "hinge_source": axis.source.value,
        "axis_confidence": float(axis.confidence),
        "kinematics_source": KINEMATICS_SOURCE,
        "target_opening_mm": target,
        "achieved_opening_mm": float(best_gap),
        "q": float(best_q),
        "theta_deg": float(best_theta),
        "translation_mm": float(best_translation),
        "closed_gap_mm": float(closed_gap),
    }
    return ArticulatorResult(
        matrix_world_ras=best_matrix,
        q=float(best_q),
        theta_deg=float(best_theta),
        translation_mm=float(best_translation),
        requested_opening_mm=target,
        achieved_opening_mm=float(best_gap),
        hinge_source=axis.source,
        axis_confidence=float(axis.confidence),
        closed_gap_mm=float(closed_gap),
        provenance=provenance,
    )


def solve_manual_oracle_opening(
    condyle_left_mm: np.ndarray,
    condyle_right_mm: np.ndarray,
    upper_incisor_mm: np.ndarray,
    lower_incisor_mm: np.ndarray,
    target_opening_mm: float,
    config: VirtualArticulatorConfig | None = None,
) -> ArticulatorResult:
    """Phase 1: four operator landmarks → MANUAL axis → shared q solver."""

    axis = virtual_condylar_axis_manual(condyle_left_mm, condyle_right_mm)
    frame = dental_frame_from_landmarks(
        condyle_left_mm,
        condyle_right_mm,
        lower_incisor_mm,
    )
    return solve_opening_for_target_mm(
        target_opening_mm,
        axis,
        frame,
        upper_incisor_mm,
        lower_incisor_mm,
        config,
    )


def is_legacy_jaw_opening_schema(schema: str | None) -> bool:
    value = str(schema or "").strip()
    if not value:
        return True
    return value == LEGACY_HINGE_SCHEMA


def legacy_jaw_opening_unsupported_message() -> str:
    return "Legacy jaw-opening state unsupported; regeneration required."
