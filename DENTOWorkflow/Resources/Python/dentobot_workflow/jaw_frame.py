"""Owning-jaw provenance frame for Step 4A-5C (S6-MULTI-JAW-STALE-01, 2026-10-07).

A PreparedBranch (trajectory -> 4C dock -> 5C template) is rigidly attached to its
target's jaw: mandibular nodes live under the TMJ mouth-opening transform, maxillary
nodes in world RAS. Every 4C/5C check is same-jaw (fit, topology, trajectory/dock
relationships, same-jaw collision screen), so the mouth opening moves a branch
without changing whether it is valid. Provenance identity is therefore recorded in
the owning-jaw frame (world RAS for the upper jaw; jaw-local, i.e. the closed-mouth
pose, for the lower jaw), and a branch binds to the Case Foundation identity with
the opening excluded. Construction always uses current world geometry.

Pure helpers only (no Slicer imports).
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from DENTOStep6State import fingerprint

PROVENANCE_FRAME_ATTRIBUTE = "DENTOBOT.ProvenanceFrame"
OWNING_JAW_FRAME = "OwningJawRASmm"
BRANCH_FOUNDATION_ATTRIBUTE = "DENTOBOT.BranchFoundationFingerprint"

# Dock-frame / provenance keys by geometric kind. Unknown "*Ras" keys fail closed.
POINT_KEYS = frozenset({"originRas", "entryRas", "targetRas", "approachRas", "seatRas"})
DIRECTION_KEYS = frozenset({
    "axisRas", "xAxisRas", "yAxisRas", "zAxisRas", "meanTrajectoryAxisRas", "occlusalNormalRas",
    "insertionDirectionRas", "removalDirectionRas",
})
MATRIX_KEYS = frozenset({"matrixColumnMajorRas"})

# Case Foundation preparation fields that change with the opening (logic_step6_scene).
OPENING_PREPARATION_KEYS = frozenset({
    "articulatorProvenance", "openingRevision", "targetGapMm", "achievedGapMm", "hingeAngleDeg",
    "openingParameterQ", "condylarTranslationMm", "worldRasMatrix", "hingeSource",
})
# Opening-independent planning-pose identity a PreparedBranch binds to.
BRANCH_FOUNDATION_KEYS = (
    "source_volume_fingerprint", "source_segmentation_fingerprint", "jaw_source_fingerprint",
    "jaw_landmarks_fingerprint", "landmark_positions_ras_mm", "landmark_review_fingerprint",
    "hinge_model_schema",
)


def matrix4(values) -> np.ndarray:
    """4x4 from a 4x4 nested sequence or 16 row-major values."""
    matrix = np.asarray(values, dtype=float).reshape(4, 4)
    if not np.all(np.isfinite(matrix)):
        raise ValueError("jaw matrix is not finite")
    return matrix


def rigid_inverse(matrix) -> np.ndarray:
    m = matrix4(matrix)
    rotation = m[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6) or abs(np.linalg.det(rotation) - 1.0) > 1e-6:
        raise ValueError("jaw transform is not rigid")
    out = np.eye(4)
    out[:3, :3] = rotation.T
    out[:3, 3] = -rotation.T @ m[:3, 3]
    return out


def transform_point(matrix, point) -> list[float]:
    m = matrix4(matrix)
    return [float(v) for v in m[:3, :3] @ np.asarray(point, dtype=float) + m[:3, 3]]


def transform_direction(matrix, direction) -> list[float]:
    return [float(v) for v in matrix4(matrix)[:3, :3] @ np.asarray(direction, dtype=float)]


def _transform_column_major(matrix, values) -> list[float]:
    local = np.asarray(values, dtype=float).reshape(4, 4).T  # column-major -> matrix
    moved = matrix4(matrix) @ local
    return [float(moved[row, column]) for column in range(4) for row in range(4)]


def transform_provenance(value, matrix):
    """Rigidly map a provenance record (dock frame, trajectory/insertion geometry)."""
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            if key in POINT_KEYS:
                out[key] = transform_point(matrix, item)
            elif key in DIRECTION_KEYS:
                out[key] = transform_direction(matrix, item)
            elif key in MATRIX_KEYS:
                out[key] = _transform_column_major(matrix, item)
            elif isinstance(key, str) and key.endswith("Ras"):
                raise ValueError(f"unknown coordinate field {key!r}; cannot change its frame")
            else:
                out[key] = transform_provenance(item, matrix)
        return out
    if isinstance(value, (list, tuple)) and value and all(isinstance(v, Mapping) for v in value):
        return [transform_provenance(v, matrix) for v in value]
    return value


def to_owning_jaw_frame(value, jaw_world_matrix):
    """World-RAS provenance -> owning-jaw frame. ``None`` matrix = upper jaw (identity)."""
    if jaw_world_matrix is None:
        return value
    return transform_provenance(value, rigid_inverse(jaw_world_matrix))


def to_world(value, jaw_world_matrix):
    """Owning-jaw provenance -> current world RAS (construction inputs)."""
    if jaw_world_matrix is None:
        return value
    return transform_provenance(value, jaw_world_matrix)


def opening_invariant_preparation(preparation: Mapping) -> dict:
    return {k: v for k, v in dict(preparation or {}).items() if k not in OPENING_PREPARATION_KEYS}


def branch_foundation_fingerprint(pose_identity: Mapping, preparation: Mapping) -> str:
    """Case Foundation identity for PreparedBranch binding, mouth opening excluded."""
    record = {key: pose_identity.get(key) for key in BRANCH_FOUNDATION_KEYS}
    if isinstance(record.get("landmark_positions_ras_mm"), tuple):
        record["landmark_positions_ras_mm"] = list(record["landmark_positions_ras_mm"])
    record["jaw_configuration"] = opening_invariant_preparation(preparation)
    return fingerprint(record)


def round_provenance(value, digits: int = 6):
    """Reload/transform-stable identity values (rigid round trips differ by ~1e-12 mm)."""
    if isinstance(value, Mapping):
        return {k: round_provenance(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [round_provenance(v, digits) for v in value]
    if isinstance(value, float):
        rounded = round(value, digits)
        return 0.0 if rounded == 0 else rounded
    return value


def provenance_matches(left, right, tolerance: float = 1e-5) -> bool:
    """Numeric comparison of two provenance records (same keys, values within tolerance)."""
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(provenance_matches(left[k], right[k], tolerance) for k in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(provenance_matches(a, b, tolerance) for a, b in zip(left, right))
    if isinstance(left, (int, float)) and isinstance(right, (int, float)) and not isinstance(left, bool):
        return abs(float(left) - float(right)) <= tolerance
    return left == right


def migrate_world_provenance(value, jaw_world_matrix, *, stamped_pose: str, current_pose: str):
    """Legacy world-RAS provenance -> owning-jaw frame, only when provably recorded at this pose.

    Returns the converted value, or None when the record was stamped at another
    planning pose (its build-time jaw matrix is unknown; it stays stale).
    """
    if not stamped_pose or stamped_pose != current_pose:
        return None
    return to_owning_jaw_frame(value, jaw_world_matrix)


def jaw_matrix_or_none(owner: str, jaw_world_matrix: Sequence | None):
    """The owning jaw's world matrix for a MovingLower node; None for upper/unowned."""
    if owner != "MovingLower":
        return None
    if jaw_world_matrix is None:
        raise ValueError("a mandibular node requires the Case Foundation jaw transform")
    return matrix4(jaw_world_matrix)
