"""Virtual forehead prior and approximate robot-base seating (world RAS mm).

Simulation visualization only: Unregistered / VisualizationOnly. Not physical
mount CAD, not collision authority, and not S6-U-02 closure.

Operator-captured defaults (2026-09-18, corrected after desired-vs-AUTO
screenshots):

- Default joints: URDF selected-zero (all published q = 0) after the 2026-08-14
  draft-zero absorption into joint origins.
- T_forehead_base: identity. URDF ``base_link`` +Z (chain after the integration
  ``base_link_to_link-1`` −90° X) maps to the forehead outward normal so the
  mechanism hangs extraoral/anterior of the plane, not down the face through
  the FOV. The earlier −90° X seating mapped +Z onto forehead +Y (toward the
  mouth) and is rejected.
- Planar TCP slide is **not** applied on propose. Sliding a compact q=0 TCP
  onto the opened incisor pulled the chain through the volume. Slide remains
  available for a later Entry aim; it is not the default extraoral seat.
- base_link skin offset: 0 mm (empty URDF root; contact face not separately
  measured).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
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
    base_rx_deg: float = 0.0
    base_ry_deg: float = 0.0
    base_rz_deg: float = 0.0
    base_link_contact_offset_mm: float = 0.0
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
    matrix[:3, 3] = np.array([0.0, 0.0, -float(config.base_link_contact_offset_mm)])
    return matrix


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
        "baseLinkContactOffsetMm": float(config.base_link_contact_offset_mm),
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
