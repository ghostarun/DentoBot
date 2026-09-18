"""Virtual forehead prior and approximate robot-base seating (world RAS mm).

Simulation visualization only: Unregistered / VisualizationOnly. Not physical
mount CAD, not collision authority, and not S6-U-02 closure.

Operator-captured defaults (2026-09-18 interactive dump, joints remain
URDF-zero):

- ``T_world_base = T_world_forehead @ T_rel`` with
  ``base_rx_deg=-176.5538``, ``base_ry_deg=-83.1910``, ``base_rz_deg=86.5294``,
  ``tu_mm=1.3063``, ``tv_mm=8.8267``, ``tz_mm=56.5915``.
- Those numbers are forehead-frame relative, not screenshot RAS.
- Planar TCP slide is **not** applied on propose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, copysign, degrees, isfinite, pi, sqrt
from typing import Any

import numpy as np

from dentobot_workflow.virtual_open_mouth_articulator import (
    DentalFrame,
    _as_point3,
    _normalize,
    estimate_arch_scale_from_lateral_width,
)

VIRTUAL_FOREHEAD_PRIOR_VERSION = "1.0"
PLACEMENT_AUTHORITY = "VirtualForeheadPriorV1"
TCP_AIM_OPENED_LOWER_INCISOR = "OPENED_LOWER_INCISOR"

# Display units: deg, mm, deg, mm, deg, deg (J1..J6).
DEFAULT_JOINT_DISPLAY = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class VirtualForeheadConfig:
    glabella_superior_mm: float = 90.0
    glabella_posterior_from_incisor_mm: float = 12.0
    forehead_recline_from_anterior_deg: float = 18.0
    patch_width_mm: float = 140.0
    patch_height_mm: float = 85.0
    patch_depth_mm: float = 28.0
    fov_clearance_mm: float = 8.0
    max_planar_slide_mm: float = 40.0
    max_yaw_deg: float = 15.0
    base_rx_deg: float = -176.5538
    base_ry_deg: float = -83.1910
    base_rz_deg: float = 86.5294
    tu_mm: float = 1.3063
    tv_mm: float = 8.8267
    tz_mm: float = 56.5915
    apply_tcp_slide_on_propose: bool = False


@dataclass(frozen=True)
class VirtualForeheadPlane:
    origin_mm: np.ndarray
    x_hat: np.ndarray
    y_hat: np.ndarray
    z_hat: np.ndarray
    arch_scale: float
    pushed_for_fov: bool
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def matrix_world(self) -> np.ndarray:
        matrix = np.eye(4, dtype=float)
        matrix[:3, 0] = self.x_hat
        matrix[:3, 1] = self.y_hat
        matrix[:3, 2] = self.z_hat
        matrix[:3, 3] = self.origin_mm
        return matrix


def _rotation_xyz_deg(rx: float, ry: float, rz: float) -> np.ndarray:
    ax, ay, az = np.radians([rx, ry, rz])
    cx, sx = np.cos(ax), np.sin(ax)
    cy, sy = np.cos(ay), np.sin(ay)
    cz, sz = np.cos(az), np.sin(az)
    rx_m = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]])
    ry_m = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
    rz_m = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]])
    return rz_m @ ry_m @ rx_m


def forehead_base_offset_matrix(config: VirtualForeheadConfig | None = None) -> np.ndarray:
    config = config or VirtualForeheadConfig()
    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = _rotation_xyz_deg(
        config.base_rx_deg, config.base_ry_deg, config.base_rz_deg
    )
    matrix[:3, 3] = np.array(
        [float(config.tu_mm), float(config.tv_mm), float(config.tz_mm)]
    )
    return matrix


def _rigid_inverse(matrix: np.ndarray) -> np.ndarray:
    inverse = np.eye(4, dtype=float)
    rotation = np.asarray(matrix, dtype=float)[:3, :3]
    inverse[:3, :3] = rotation.T
    inverse[:3, 3] = -rotation.T @ np.asarray(matrix, dtype=float)[:3, 3]
    return inverse


def euler_xyz_deg_from_rotation(rotation: np.ndarray) -> tuple[float, float, float]:
    """Inverse of ``_rotation_xyz_deg`` (R = Rz @ Ry @ Rx)."""

    matrix = np.asarray(rotation, dtype=float)
    sine_y = -float(matrix[2, 0])
    cosine_y = sqrt(max(0.0, 1.0 - sine_y * sine_y))
    if cosine_y > 1e-8:
        rx = atan2(float(matrix[2, 1]), float(matrix[2, 2]))
        ry = atan2(sine_y, cosine_y)
        rz = atan2(float(matrix[1, 0]), float(matrix[0, 0]))
    else:
        rx = atan2(-float(matrix[0, 1]), float(matrix[1, 1]))
        ry = copysign(pi / 2.0, sine_y)
        rz = 0.0
    return (degrees(rx), degrees(ry), degrees(rz))


def forehead_relative_seating(
    t_world_forehead: np.ndarray,
    t_world_base: np.ndarray,
) -> dict[str, Any]:
    relative = _rigid_inverse(t_world_forehead) @ np.asarray(t_world_base, dtype=float)
    rx, ry, rz = euler_xyz_deg_from_rotation(relative[:3, :3])
    tu, tv, tz = (float(v) for v in relative[:3, 3])
    line = (
        f"base_rx_deg={rx:.4f} base_ry_deg={ry:.4f} base_rz_deg={rz:.4f} "
        f"tu_mm={tu:.4f} tv_mm={tv:.4f} tz_mm={tz:.4f}"
    )
    return {
        "baseRxDeg": rx,
        "baseRyDeg": ry,
        "baseRzDeg": rz,
        "tuMm": tu,
        "tvMm": tv,
        "tzMm": tz,
        "copyLine": line,
        "matrix_forehead_from_base": relative,
    }


def propose_virtual_forehead_plane(
    frame: DentalFrame,
    *,
    arch_scale: float = 1.0,
    volume_ras_bounds: np.ndarray | None = None,
    config: VirtualForeheadConfig | None = None,
) -> VirtualForeheadPlane:
    config = config or VirtualForeheadConfig()
    scale = float(arch_scale)
    if not isfinite(scale) or scale <= 0.0:
        raise ValueError("Arch scale must be positive and finite.")
    incisor = _as_point3(frame.origin_mm, "incisor")
    superior = float(config.glabella_superior_mm) * scale
    posterior = float(config.glabella_posterior_from_incisor_mm) * scale
    origin = incisor + superior * frame.z_hat - posterior * frame.y_hat
    recline = np.radians(float(config.forehead_recline_from_anterior_deg))
    normal = _normalize(
        np.cos(recline) * frame.y_hat + np.sin(recline) * frame.z_hat,
        "forehead normal",
    )
    y_up = frame.z_hat - float(np.dot(frame.z_hat, normal)) * normal
    if float(np.linalg.norm(y_up)) <= 1e-9:
        y_up = frame.y_hat - float(np.dot(frame.y_hat, normal)) * normal
    y_up = _normalize(y_up, "forehead up")
    # Right-handed: X patient-right, Y toward the mouth, Z outward.
    y_hat = -y_up
    x_hat = _normalize(np.cross(y_hat, normal), "forehead right")
    if float(np.dot(x_hat, frame.x_hat)) < 0.0:
        x_hat = -x_hat
        y_hat = _normalize(np.cross(normal, x_hat), "forehead toward mouth")
    else:
        y_hat = _normalize(np.cross(normal, x_hat), "forehead toward mouth")
    pushed = False
    if volume_ras_bounds is not None:
        origin, pushed = _push_origin_outside_superior_aabb(
            origin, frame.z_hat, volume_ras_bounds, float(config.fov_clearance_mm)
        )
    diagnostics = {
        "priorVersion": VIRTUAL_FOREHEAD_PRIOR_VERSION,
        "placementAuthority": PLACEMENT_AUTHORITY,
        "archScale": scale,
        "glabellaSuperiorMm": superior,
        "glabellaPosteriorMm": posterior,
        "reclineDeg": float(config.forehead_recline_from_anterior_deg),
        "pushedForFov": pushed,
        "tcpAim": TCP_AIM_OPENED_LOWER_INCISOR,
        "defaultJointDisplay": list(DEFAULT_JOINT_DISPLAY),
        "baseRxDeg": float(config.base_rx_deg),
        "baseRyDeg": float(config.base_ry_deg),
        "baseRzDeg": float(config.base_rz_deg),
        "tuMm": float(config.tu_mm),
        "tvMm": float(config.tv_mm),
        "tzMm": float(config.tz_mm),
    }
    return VirtualForeheadPlane(
        origin_mm=origin,
        x_hat=x_hat,
        y_hat=y_hat,
        z_hat=normal,
        arch_scale=scale,
        pushed_for_fov=pushed,
        diagnostics=diagnostics,
    )


def _push_origin_outside_superior_aabb(
    origin: np.ndarray,
    superior_hat: np.ndarray,
    bounds: np.ndarray,
    clearance_mm: float,
) -> tuple[np.ndarray, bool]:
    box = np.asarray(bounds, dtype=float).reshape(6)
    mins = np.array([box[0], box[2], box[4]], dtype=float)
    maxs = np.array([box[1], box[3], box[5]], dtype=float)
    corners = [
        np.array([x, y, z], dtype=float)
        for x in (mins[0], maxs[0])
        for y in (mins[1], maxs[1])
        for z in (mins[2], maxs[2])
    ]
    superior_extent = max(float(np.dot(corner, superior_hat)) for corner in corners)
    current = float(np.dot(origin, superior_hat))
    needed = superior_extent + float(clearance_mm)
    if current + 1e-9 >= needed:
        return origin, False
    return origin + (needed - current) * superior_hat, True


def seat_base_on_forehead(
    plane: VirtualForeheadPlane,
    *,
    slide_u_mm: float = 0.0,
    slide_v_mm: float = 0.0,
    yaw_deg: float = 0.0,
    config: VirtualForeheadConfig | None = None,
) -> np.ndarray:
    config = config or VirtualForeheadConfig()
    forehead = plane.matrix_world()
    slide = np.eye(4, dtype=float)
    slide[:3, 3] = float(slide_u_mm) * plane.x_hat + float(slide_v_mm) * plane.y_hat
    yaw = np.eye(4, dtype=float)
    yaw[:3, :3] = _rotation_xyz_deg(0.0, 0.0, float(yaw_deg))
    return forehead @ slide @ yaw @ forehead_base_offset_matrix(config)


def _tcp_world_mm(
    plane: VirtualForeheadPlane,
    tcp_in_base_mm: np.ndarray,
    slide_u_mm: float,
    slide_v_mm: float,
    yaw_deg: float,
    config: VirtualForeheadConfig,
) -> np.ndarray:
    base = seat_base_on_forehead(
        plane,
        slide_u_mm=slide_u_mm,
        slide_v_mm=slide_v_mm,
        yaw_deg=yaw_deg,
        config=config,
    )
    point = np.append(_as_point3(tcp_in_base_mm, "tcp in base"), 1.0)
    return (base @ point)[:3]


def slide_base_for_tcp_target(
    plane: VirtualForeheadPlane,
    tcp_in_base_mm: np.ndarray,
    target_world_mm: np.ndarray,
    *,
    config: VirtualForeheadConfig | None = None,
) -> dict[str, float | np.ndarray]:
    """Least-squares-style grid search of planar slide + small yaw (frozen FK)."""

    config = config or VirtualForeheadConfig()
    target = _as_point3(target_world_mm, "tcp target")
    tcp_base = _as_point3(tcp_in_base_mm, "tcp in base")
    max_s = float(config.max_planar_slide_mm)
    max_yaw = float(config.max_yaw_deg)
    best = None
    for u in np.linspace(-max_s, max_s, 9):
        for v in np.linspace(-max_s, max_s, 9):
            for yaw in np.linspace(-max_yaw, max_yaw, 7):
                world = _tcp_world_mm(plane, tcp_base, u, v, yaw, config)
                err = float(np.linalg.norm(world - target))
                if best is None or err < best[0]:
                    best = (err, float(u), float(v), float(yaw), world)
    assert best is not None
    err, u0, v0, yaw0, _world = best
    span_s = max_s / 8.0
    span_y = max_yaw / 6.0
    for u in np.linspace(u0 - span_s, u0 + span_s, 7):
        for v in np.linspace(v0 - span_s, v0 + span_s, 7):
            for yaw in np.linspace(yaw0 - span_y, yaw0 + span_y, 5):
                world = _tcp_world_mm(plane, tcp_base, u, v, yaw, config)
                dist = float(np.linalg.norm(world - target))
                if dist < err:
                    err, u0, v0, yaw0 = dist, float(u), float(v), float(yaw)
    matrix = seat_base_on_forehead(
        plane, slide_u_mm=u0, slide_v_mm=v0, yaw_deg=yaw0, config=config
    )
    return {
        "errorMm": err,
        "slideUMm": u0,
        "slideVMm": v0,
        "yawDeg": yaw0,
        "matrix_world_ras": matrix,
    }


def arch_scale_from_laterals(
    left_mm: np.ndarray,
    right_mm: np.ndarray,
) -> float:
    scale, _confidence = estimate_arch_scale_from_lateral_width(left_mm, right_mm)
    return float(scale)
