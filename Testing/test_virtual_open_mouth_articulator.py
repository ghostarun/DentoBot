"""Unit tests for virtual_open_mouth_articulator (no Slicer)."""

from __future__ import annotations

import numpy as np
import pytest

from dentobot_workflow.virtual_open_mouth_articulator import (
    HINGE_MODEL_SCHEMA,
    HingeSource,
    VirtualArticulatorConfig,
    compare_condyle_centres,
    compose_mandible_open_transform,
    dental_frame_from_landmarks,
    interincisal_distance_mm,
    is_legacy_jaw_opening_schema,
    legacy_jaw_opening_unsupported_message,
    opening_at_q,
    resolve_virtual_condylar_axis,
    solve_arch_inferred_opening,
    solve_manual_oracle_opening,
    solve_patient_condyle_opening,
    transform_point,
    validate_patient_condylar_axis,
    virtual_condylar_axis_from_points,
    virtual_condylar_axis_manual,
)


def _fixture_landmarks() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    left = np.array([-50.0, -45.0, -5.0])
    right = np.array([50.0, -45.0, -5.0])
    upper = np.array([0.0, -90.0, -10.0])
    lower = np.array([0.0, -90.0, -12.0])
    return left, right, upper, lower


def test_q_zero_is_identity() -> None:
    left, right, upper, lower = _fixture_landmarks()
    axis = virtual_condylar_axis_manual(left, right)
    frame = dental_frame_from_landmarks(left, right, lower)
    config = VirtualArticulatorConfig()
    matrix, theta, translation = opening_at_q(0.0, axis, frame, config, lower)
    assert theta == pytest.approx(0.0)
    assert translation == pytest.approx(0.0)
    np.testing.assert_allclose(matrix, np.eye(4), atol=1e-9)
    closed = interincisal_distance_mm(upper, lower, matrix)
    assert closed == pytest.approx(2.0, abs=1e-6)


def test_compose_matches_explicit_multiply_order() -> None:
    h0 = np.array([0.0, 0.0, 0.0])
    hq = np.array([1.0, -2.0, 3.0])
    axis = np.array([1.0, 0.0, 0.0])
    theta = np.radians(15.0)
    composed = compose_mandible_open_transform(h0, axis, theta, hq)
    point = np.array([4.0, 5.0, 6.0])
    t_neg = np.eye(4)
    t_neg[:3, 3] = -h0
    t_pos = np.eye(4)
    t_pos[:3, 3] = hq
    rotation = np.eye(4)
    rotation[:3, :3] = composed[:3, :3]
    explicit = t_pos @ rotation @ t_neg
    expected = transform_point(explicit, point)
    actual = transform_point(composed, point)
    np.testing.assert_allclose(actual, expected, atol=1e-9)


def test_rigid_distance_preservation() -> None:
    left, right, upper, lower = _fixture_landmarks()
    axis = virtual_condylar_axis_manual(left, right)
    frame = dental_frame_from_landmarks(left, right, lower)
    matrix, _, _ = opening_at_q(0.65, axis, frame, VirtualArticulatorConfig(), lower)
    p1 = lower + np.array([12.0, -3.0, 4.0])
    p2 = lower + np.array([-8.0, 6.0, 2.0])
    before = float(np.linalg.norm(p1 - p2))
    after = float(
        np.linalg.norm(transform_point(matrix, p1) - transform_point(matrix, p2))
    )
    assert after == pytest.approx(before, abs=1e-6)


def test_deterministic_repeated_solve() -> None:
    left, right, upper, lower = _fixture_landmarks()
    first = solve_manual_oracle_opening(left, right, upper, lower, 40.0)
    second = solve_manual_oracle_opening(left, right, upper, lower, 40.0)
    np.testing.assert_allclose(first.matrix_world_ras, second.matrix_world_ras, atol=1e-9)
    assert first.q == pytest.approx(second.q)
    assert first.achieved_opening_mm == pytest.approx(second.achieved_opening_mm, abs=0.11)


def test_monotonic_opening_with_q() -> None:
    left, right, upper, lower = _fixture_landmarks()
    axis = virtual_condylar_axis_manual(left, right)
    frame = dental_frame_from_landmarks(left, right, lower)
    config = VirtualArticulatorConfig()
    gaps = []
    for q in (0.0, 0.25, 0.5, 0.75, 1.0):
        matrix, _, _ = opening_at_q(q, axis, frame, config, lower)
        gaps.append(interincisal_distance_mm(upper, lower, matrix))
    assert gaps == sorted(gaps)


def test_manual_oracle_reaches_target_opening() -> None:
    left, right, upper, lower = _fixture_landmarks()
    result = solve_manual_oracle_opening(left, right, upper, lower, 40.0)
    assert result.hinge_source is HingeSource.MANUAL
    assert result.achieved_opening_mm == pytest.approx(40.0, abs=0.11)
    assert result.provenance["hingeModelSchema"] == HINGE_MODEL_SCHEMA
    assert result.provenance["hinge_source"] == "MANUAL"


def test_upper_incisor_untransformed_by_mandible_matrix() -> None:
    left, right, upper, lower = _fixture_landmarks()
    result = solve_manual_oracle_opening(left, right, upper, lower, 35.0)
    moved_lower = transform_point(result.matrix_world_ras, lower)
    assert moved_lower[2] < lower[2]
    assert float(np.linalg.norm(upper - moved_lower)) == pytest.approx(
        result.achieved_opening_mm, abs=0.11
    )


def test_legacy_schema_detection() -> None:
    assert is_legacy_jaw_opening_schema("AnatomyDirectedPureTMJHingeRotationV2")
    assert not is_legacy_jaw_opening_schema(HINGE_MODEL_SCHEMA)
    assert "regeneration required" in legacy_jaw_opening_unsupported_message()


def test_patient_axis_solve_reaches_target() -> None:
    left, right, upper, lower = _fixture_landmarks()
    result = solve_patient_condyle_opening(
        left,
        right,
        upper,
        lower,
        40.0,
        source=HingeSource.PATIENT_CONDYLES_SEGMENTED,
    )
    assert result.hinge_source is HingeSource.PATIENT_CONDYLES_SEGMENTED
    assert result.achieved_opening_mm == pytest.approx(40.0, abs=0.11)


def test_patient_axis_rejects_swapped_lr() -> None:
    left, right, upper, lower = _fixture_landmarks()
    axis = virtual_condylar_axis_from_points(
        right,
        left,
        HingeSource.PATIENT_CONDYLES_SEGMENTED,
        0.9,
    )
    frame = dental_frame_from_landmarks(left, right, lower)
    with pytest.raises(ValueError, match="side-swapped"):
        validate_patient_condylar_axis(axis, frame, lower)


def test_patient_axis_rejects_implausible_span() -> None:
    left, right, upper, lower = _fixture_landmarks()
    right = left + np.array([5.0, 0.0, 0.0])
    axis = virtual_condylar_axis_from_points(
        left,
        right,
        HingeSource.PATIENT_CONDYLES_SEGMENTED,
        0.9,
    )
    frame = dental_frame_from_landmarks(left, right, lower)
    with pytest.raises(ValueError, match="implausibly close"):
        validate_patient_condylar_axis(axis, frame, lower)


def test_compare_condyle_centres_reports_offsets() -> None:
    left, right, _, _ = _fixture_landmarks()
    metrics = compare_condyle_centres(
        left,
        right,
        left + np.array([2.0, 0.0, 0.0]),
        right - np.array([1.0, 0.0, 0.0]),
    )
    assert metrics["leftOffsetMm"] == pytest.approx(2.0)
    assert metrics["rightOffsetMm"] == pytest.approx(1.0)


def test_resolve_prefers_segmented_axis_when_valid() -> None:
    left, right, upper, lower = _fixture_landmarks()
    resolution = resolve_virtual_condylar_axis(
        manual_condyle_left_mm=left,
        manual_condyle_right_mm=right,
        lower_incisor_mm=lower,
        segmented_condyle_left_mm=left + np.array([1.0, 0.0, 0.0]),
        segmented_condyle_right_mm=right - np.array([1.0, 0.0, 0.0]),
    )
    assert resolution.axis.source is HingeSource.PATIENT_CONDYLES_SEGMENTED


def test_arch_inferred_opening_reaches_target() -> None:
    left, right, upper, lower = _fixture_landmarks()
    result = solve_arch_inferred_opening(left, right, upper, lower, 35.0, arch_scale=1.0)
    assert result.hinge_source is HingeSource.ARCH_INFERRED
    assert result.achieved_opening_mm == pytest.approx(35.0, abs=0.11)


def test_arch_scale_clamps_smoothly() -> None:
    left = np.array([-22.5, -90.0, -12.0])
    right = np.array([22.5, -90.0, -12.0])
    config = VirtualArticulatorConfig(reference_arch_width_mm=50.0)
    from dentobot_workflow.virtual_open_mouth_articulator import (
        estimate_arch_scale_from_lateral_width,
    )

    scale, _ = estimate_arch_scale_from_lateral_width(left, right, config)
    assert scale == pytest.approx(0.9, abs=1e-6)


def test_invalid_bonwill_geometry_fails() -> None:
    left, right, upper, lower = _fixture_landmarks()
    config = VirtualArticulatorConfig(bonwill_side_mm=40.0, intercondylar_distance_mm=100.0)
    with pytest.raises(ValueError, match="Bonwill"):
        solve_arch_inferred_opening(
            left,
            right,
            upper,
            lower,
            30.0,
            arch_scale=1.0,
            config=config,
        )
