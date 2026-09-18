"""Unit tests for virtual_forehead_mount (no Slicer)."""

from __future__ import annotations

import numpy as np
import pytest

from dentobot_workflow.virtual_open_mouth_articulator import (
    dental_frame_from_landmarks,
)
from dentobot_workflow.virtual_forehead_mount import (
    DEFAULT_JOINT_DISPLAY,
    PLACEMENT_AUTHORITY,
    TCP_AIM_OPENED_LOWER_INCISOR,
    VirtualForeheadConfig,
    forehead_base_offset_matrix,
    forehead_relative_seating,
    propose_virtual_forehead_plane,
    seat_base_on_forehead,
    slide_base_for_tcp_target,
)


def _fixture_frame():
    left = np.array([-50.0, -45.0, -5.0])
    right = np.array([50.0, -45.0, -5.0])
    lower = np.array([0.0, -90.0, -12.0])
    return dental_frame_from_landmarks(left, right, lower), lower


def test_forehead_is_superior_of_incisor_and_not_from_a_robot() -> None:
    frame, lower = _fixture_frame()
    plane = propose_virtual_forehead_plane(frame, arch_scale=1.0)
    assert plane.diagnostics["placementAuthority"] == PLACEMENT_AUTHORITY
    assert plane.diagnostics["tcpAim"] == TCP_AIM_OPENED_LOWER_INCISOR
    assert float(np.dot(plane.origin_mm - lower, frame.z_hat)) > 50.0
    assert float(np.dot(plane.z_hat, frame.y_hat)) > 0.4
    assert abs(float(np.linalg.det(plane.matrix_world()[:3, :3])) - 1.0) < 1e-6


def test_fov_push_never_pulls_into_volume() -> None:
    frame, lower = _fixture_frame()
    # AABB whose superior face is above the naive glabella.
    bounds = np.array(
        [
            -80.0,
            80.0,
            -120.0,
            -20.0,
            -40.0,
            200.0,
        ]
    )
    plane = propose_virtual_forehead_plane(
        frame, arch_scale=1.0, volume_ras_bounds=bounds
    )
    assert plane.pushed_for_fov is True
    assert float(np.dot(plane.origin_mm, frame.z_hat)) >= 200.0 + 8.0 - 1e-6


def test_seat_uses_named_forehead_to_base_rotation() -> None:
    frame, _lower = _fixture_frame()
    plane = propose_virtual_forehead_plane(frame)
    identity = VirtualForeheadConfig(
        base_rx_deg=0.0,
        base_ry_deg=0.0,
        base_rz_deg=0.0,
        tu_mm=0.0,
        tv_mm=0.0,
        tz_mm=0.0,
    )
    base = seat_base_on_forehead(plane, config=identity)
    offset = forehead_base_offset_matrix(identity)
    expected = plane.matrix_world() @ offset
    assert np.allclose(base, expected)
    assert np.allclose(offset[:3, 2], np.array([0.0, 0.0, 1.0]), atol=1e-9)
    assert np.allclose(base[:3, 2], plane.z_hat, atol=1e-9)


def test_planar_slide_reduces_tcp_error() -> None:
    frame, lower = _fixture_frame()
    plane = propose_virtual_forehead_plane(frame)
    tcp_in_base = np.array([0.0, -80.0, 40.0])
    unslid = seat_base_on_forehead(plane)
    unslid_tcp = (unslid @ np.append(tcp_in_base, 1.0))[:3]
    target = unslid_tcp + 18.0 * plane.x_hat - 10.0 * plane.y_hat
    result = slide_base_for_tcp_target(plane, tcp_in_base, target)
    assert result["errorMm"] < float(np.linalg.norm(unslid_tcp - target)) - 1.0
    assert abs(float(result["slideUMm"])) <= 40.0 + 1e-6
    assert DEFAULT_JOINT_DISPLAY == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def test_propose_defaults_recover_operator_capture() -> None:
    frame, _lower = _fixture_frame()
    plane = propose_virtual_forehead_plane(frame)
    base = seat_base_on_forehead(plane)
    dumped = forehead_relative_seating(plane.matrix_world(), base)
    assert dumped["baseRxDeg"] == pytest.approx(-176.5538, abs=1e-3)
    assert dumped["baseRyDeg"] == pytest.approx(-83.1910, abs=1e-3)
    assert dumped["baseRzDeg"] == pytest.approx(86.5294, abs=1e-3)
    assert dumped["tuMm"] == pytest.approx(1.3063, abs=1e-3)
    assert dumped["tvMm"] == pytest.approx(8.8267, abs=1e-3)
    assert dumped["tzMm"] == pytest.approx(56.5915, abs=1e-3)
    extraoral = float(np.dot(base[:3, 3] - plane.origin_mm, plane.z_hat))
    assert extraoral > 0.0
    assert DEFAULT_JOINT_DISPLAY == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def test_x_axis_points_patient_right() -> None:
    frame, _ = _fixture_frame()
    plane = propose_virtual_forehead_plane(frame)
    assert float(np.dot(plane.x_hat, frame.x_hat)) > 0.7


def test_forehead_relative_seating_roundtrip() -> None:
    frame, _ = _fixture_frame()
    plane = propose_virtual_forehead_plane(frame)
    config = VirtualForeheadConfig(
        base_rx_deg=-40.0,
        base_ry_deg=18.0,
        base_rz_deg=7.5,
        tu_mm=12.0,
        tv_mm=-8.0,
        tz_mm=5.0,
    )
    seated = seat_base_on_forehead(plane, config=config)
    dumped = forehead_relative_seating(plane.matrix_world(), seated)
    assert dumped["baseRxDeg"] == pytest.approx(-40.0, abs=1e-4)
    assert dumped["baseRyDeg"] == pytest.approx(18.0, abs=1e-4)
    assert dumped["baseRzDeg"] == pytest.approx(7.5, abs=1e-4)
    assert dumped["tuMm"] == pytest.approx(12.0, abs=1e-4)
    assert dumped["tvMm"] == pytest.approx(-8.0, abs=1e-4)
    assert dumped["tzMm"] == pytest.approx(5.0, abs=1e-4)
