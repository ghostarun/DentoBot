"""Pure geometry helpers for draft DENTOBOT placement in Slicer RAS millimetres.

This module parses the tracked URDF but has no ROS, Slicer, controller, or
hardware dependency.  It is intentionally limited to visualization and manual
workspace exploration.
"""

from dataclasses import dataclass
from math import cos, isfinite, radians, sin, sqrt
from pathlib import Path
from xml.etree import ElementTree

import numpy as np


@dataclass(frozen=True)
class RobotLinkMeshPose:
    """One STL and its rigid mesh-millimetres-to-base-millimetres pose."""

    link_name: str
    mesh_path: Path
    matrix_base_from_link_mm: np.ndarray
    matrix_base_from_mesh_mm: np.ndarray


def _vector3(text: str | None, default: tuple[float, float, float]) -> np.ndarray:
    if text is None:
        return np.asarray(default, dtype=float)
    values = np.asarray([float(value) for value in text.split()], dtype=float)
    if values.shape != (3,) or not np.all(np.isfinite(values)):
        raise ValueError(f"Expected three finite values, received {text!r}.")
    return values


def pose_matrix_m(xyz_m: np.ndarray, rpy_rad: np.ndarray) -> np.ndarray:
    """Return a URDF fixed-axis roll/pitch/yaw homogeneous transform."""
    roll, pitch, yaw = (float(value) for value in rpy_rad)
    cr, sr = cos(roll), sin(roll)
    cp, sp = cos(pitch), sin(pitch)
    cy, sy = cos(yaw), sin(yaw)
    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = (
        (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
        (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
        (-sp, cp * sr, cp * cr),
    )
    matrix[:3, 3] = xyz_m
    return matrix


def axis_motion_matrix(joint_type: str, axis: np.ndarray, value_si: float) -> np.ndarray:
    """Return one URDF joint motion in radians or metres."""
    value = float(value_si)
    if not isfinite(value):
        raise ValueError("Joint position must be finite.")
    matrix = np.eye(4, dtype=float)
    if joint_type == "fixed":
        return matrix
    axis_norm = float(np.linalg.norm(axis))
    if axis_norm <= 0.0:
        raise ValueError("A movable joint has a zero-length axis.")
    x, y, z = axis / axis_norm
    if joint_type == "prismatic":
        matrix[:3, 3] = (x * value, y * value, z * value)
        return matrix
    if joint_type not in {"revolute", "continuous"}:
        raise ValueError(f"Unsupported movable joint type {joint_type!r}.")
    cosine, sine = cos(value), sin(value)
    one_minus_cosine = 1.0 - cosine
    matrix[:3, :3] = (
        (
            cosine + x * x * one_minus_cosine,
            x * y * one_minus_cosine - z * sine,
            x * z * one_minus_cosine + y * sine,
        ),
        (
            y * x * one_minus_cosine + z * sine,
            cosine + y * y * one_minus_cosine,
            y * z * one_minus_cosine - x * sine,
        ),
        (
            z * x * one_minus_cosine - y * sine,
            z * y * one_minus_cosine + x * sine,
            cosine + z * z * one_minus_cosine,
        ),
    )
    return matrix


def joint_positions_si_from_display(
    joint_1_deg: float,
    joint_2_mm: float,
    joint_3_deg: float,
    joint_4_mm: float,
    joint_5_deg: float,
    joint_6_deg: float,
) -> dict[str, float]:
    """Convert the Slicer controls into the tracked URDF joint names/units."""
    return {
        "link-1_Revolute-1": radians(float(joint_1_deg)),
        "link-2_Slider-2": float(joint_2_mm) / 1000.0,
        "link-3_Revolute-3": radians(float(joint_3_deg)),
        "link-4_Slider-4": float(joint_4_mm) / 1000.0,
        "link-5_Revolute-5": radians(float(joint_5_deg)),
        "pneumatic_spindle-Copy_Revolute-6": radians(float(joint_6_deg)),
    }


def robot_link_mesh_poses_mm(
    urdf_path: str | Path,
    package_root: str | Path,
    joint_positions_si: dict[str, float] | None = None,
) -> tuple[RobotLinkMeshPose, ...]:
    """Return every collision/visual mesh pose relative to URDF base_link."""
    urdf_path = Path(urdf_path).resolve()
    package_root = Path(package_root).resolve()
    root = ElementTree.parse(urdf_path).getroot()
    if root.tag != "robot":
        raise ValueError("The description does not contain a URDF robot root.")
    positions = dict(joint_positions_si or {})

    link_names = {link.get("name", "") for link in root.findall("link")}
    child_links: set[str] = set()
    joints: list[dict] = []
    for joint in root.findall("joint"):
        parent = joint.find("parent")
        child = joint.find("child")
        if parent is None or child is None:
            raise ValueError("A URDF joint is missing its parent or child.")
        origin = joint.find("origin")
        axis = joint.find("axis")
        child_name = child.get("link", "")
        child_links.add(child_name)
        joints.append(
            {
                "name": joint.get("name", ""),
                "type": joint.get("type", ""),
                "parent": parent.get("link", ""),
                "child": child_name,
                "origin": pose_matrix_m(
                    _vector3(
                        origin.get("xyz") if origin is not None else None,
                        (0.0, 0.0, 0.0),
                    ),
                    _vector3(
                        origin.get("rpy") if origin is not None else None,
                        (0.0, 0.0, 0.0),
                    ),
                ),
                "axis": _vector3(
                    axis.get("xyz") if axis is not None else None,
                    (1.0, 0.0, 0.0),
                ),
            }
        )
    roots = link_names - child_links
    if len(roots) != 1:
        raise ValueError(f"Expected one URDF root link, found {sorted(roots)}.")
    root_link = next(iter(roots))
    transforms_m = {root_link: np.eye(4, dtype=float)}
    pending = list(joints)
    while pending:
        progressed = False
        for joint in pending[:]:
            if joint["parent"] not in transforms_m:
                continue
            motion = axis_motion_matrix(
                joint["type"],
                joint["axis"],
                positions.get(joint["name"], 0.0),
            )
            transforms_m[joint["child"]] = (
                transforms_m[joint["parent"]] @ joint["origin"] @ motion
            )
            pending.remove(joint)
            progressed = True
        if not progressed:
            raise ValueError("The URDF joint graph is disconnected or cyclic.")

    poses: list[RobotLinkMeshPose] = []
    uri_prefix = "package://dentobot_description/"
    for link in root.findall("link"):
        visual = link.find("visual")
        if visual is None:
            continue
        mesh = visual.find("geometry/mesh")
        if mesh is None:
            continue
        filename = mesh.get("filename", "")
        if not filename.startswith(uri_prefix):
            raise ValueError(f"Unsupported robot mesh URI {filename!r}.")
        relative_path = Path(filename[len(uri_prefix) :])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"Robot mesh URI escapes the package: {filename!r}.")
        mesh_path = (package_root / relative_path).resolve()
        if not mesh_path.is_file():
            raise ValueError(f"Robot mesh is missing: {mesh_path}.")
        scale = _vector3(mesh.get("scale"), (1.0, 1.0, 1.0))
        if not np.allclose(scale, (0.001, 0.001, 0.001), atol=1e-12):
            raise ValueError(
                "Slicer robot loading currently requires the tracked 0.001 STL scale."
            )
        visual_origin = visual.find("origin")
        mesh_pose_m = transforms_m[link.get("name", "")] @ pose_matrix_m(
            _vector3(
                visual_origin.get("xyz") if visual_origin is not None else None,
                (0.0, 0.0, 0.0),
            ),
            _vector3(
                visual_origin.get("rpy") if visual_origin is not None else None,
                (0.0, 0.0, 0.0),
            ),
        )
        mesh_pose_mm = np.array(mesh_pose_m, dtype=float, copy=True)
        mesh_pose_mm[:3, 3] *= 1000.0
        link_pose_mm = np.array(
            transforms_m[link.get("name", "")],
            dtype=float,
            copy=True,
        )
        link_pose_mm[:3, 3] *= 1000.0
        poses.append(
            RobotLinkMeshPose(
                link_name=link.get("name", ""),
                mesh_path=mesh_path,
                matrix_base_from_link_mm=link_pose_mm,
                matrix_base_from_mesh_mm=mesh_pose_mm,
            )
        )
    if not poses:
        raise ValueError("The URDF contains no visual robot meshes.")
    return tuple(poses)


def orthonormal_plane_pose(plane_to_world: np.ndarray) -> np.ndarray:
    """Remove Markups plane scale/shear while preserving origin and handedness."""
    source = np.asarray(plane_to_world, dtype=float)
    if source.shape != (4, 4) or not np.all(np.isfinite(source)):
        raise ValueError("Mount-plane matrix must be finite 4 x 4 geometry.")
    z_axis = source[:3, 2]
    z_norm = float(np.linalg.norm(z_axis))
    if z_norm <= 1e-9:
        raise ValueError("Mount-plane normal is degenerate.")
    z_axis = z_axis / z_norm
    x_axis = source[:3, 0]
    x_axis = x_axis - float(np.dot(x_axis, z_axis)) * z_axis
    if float(np.linalg.norm(x_axis)) <= 1e-9:
        x_axis = source[:3, 1]
        x_axis = x_axis - float(np.dot(x_axis, z_axis)) * z_axis
    x_norm = float(np.linalg.norm(x_axis))
    if x_norm <= 1e-9:
        raise ValueError("Mount-plane in-plane axes are degenerate.")
    x_axis = x_axis / x_norm
    y_axis = np.cross(z_axis, x_axis)
    y_axis = y_axis / float(np.linalg.norm(y_axis))
    matrix = np.eye(4, dtype=float)
    matrix[:3, 0] = x_axis
    matrix[:3, 1] = y_axis
    matrix[:3, 2] = z_axis
    matrix[:3, 3] = source[:3, 3]
    return matrix


def local_nudge_matrix(
    base_to_world: np.ndarray,
    translation_local_mm: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation_local_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> np.ndarray:
    """Post-multiply one local-frame rigid translation/rotation adjustment."""
    base = np.asarray(base_to_world, dtype=float)
    if base.shape != (4, 4) or not np.all(np.isfinite(base)):
        raise ValueError("Robot-base matrix must be finite 4 x 4 geometry.")
    translation = np.asarray(translation_local_mm, dtype=float)
    rotation = np.asarray(rotation_local_deg, dtype=float)
    if translation.shape != (3,) or rotation.shape != (3,):
        raise ValueError("Nudge translation and rotation must each have three values.")
    delta = pose_matrix_m(translation, np.radians(rotation))
    return base @ delta


def hinge_rotation_matrix(
    hinge_left_mm: np.ndarray,
    hinge_right_mm: np.ndarray,
    angle_deg: float,
) -> np.ndarray:
    """Return a world-space rotation about the left-to-right TMJ hinge axis."""

    left = np.asarray(hinge_left_mm, dtype=float)
    right = np.asarray(hinge_right_mm, dtype=float)
    if left.shape != (3,) or right.shape != (3,):
        raise ValueError("TMJ hinge points must each contain three values.")
    if not np.all(np.isfinite(left)) or not np.all(np.isfinite(right)):
        raise ValueError("TMJ hinge points must be finite.")
    axis = right - left
    axis_norm = float(np.linalg.norm(axis))
    if axis_norm <= 1e-6:
        raise ValueError("Left and right TMJ points must be distinct.")
    axis /= axis_norm
    angle = radians(float(angle_deg))
    if not isfinite(angle):
        raise ValueError("Jaw opening angle must be finite.")
    x, y, z = axis
    cosine, sine = cos(angle), sin(angle)
    one_minus_cosine = 1.0 - cosine
    rotation = np.asarray(
        (
            (
                cosine + x * x * one_minus_cosine,
                x * y * one_minus_cosine - z * sine,
                x * z * one_minus_cosine + y * sine,
            ),
            (
                y * x * one_minus_cosine + z * sine,
                cosine + y * y * one_minus_cosine,
                y * z * one_minus_cosine - x * sine,
            ),
            (
                z * x * one_minus_cosine - y * sine,
                z * y * one_minus_cosine + x * sine,
                cosine + z * z * one_minus_cosine,
            ),
        ),
        dtype=float,
    )
    pivot = (left + right) * 0.5
    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = pivot - rotation @ pivot
    return matrix


def solve_hinge_rotation_for_gap(
    hinge_left_mm: np.ndarray,
    hinge_right_mm: np.ndarray,
    upper_incisor_mm: np.ndarray,
    lower_incisor_closed_mm: np.ndarray,
    target_gap_mm: float = 40.0,
    maximum_angle_deg: float = 60.0,
) -> tuple[float, np.ndarray, np.ndarray, float]:
    """Find the smallest-error pure hinge rotation for a draft incisor gap.

    Both opening directions are sampled because the landmark order and the
    model coordinate convention are deliberately user-defined in this draft
    experiment.  The result is geometric only and is not a TMJ motion model.
    """

    upper = np.asarray(upper_incisor_mm, dtype=float)
    lower = np.asarray(lower_incisor_closed_mm, dtype=float)
    if upper.shape != (3,) or lower.shape != (3,):
        raise ValueError("Incisor landmarks must each contain three values.")
    if not np.all(np.isfinite(upper)) or not np.all(np.isfinite(lower)):
        raise ValueError("Incisor landmarks must be finite.")
    target = float(target_gap_mm)
    maximum = float(maximum_angle_deg)
    if not isfinite(target) or target <= 0.0:
        raise ValueError("Target incisor gap must be positive and finite.")
    if not isfinite(maximum) or maximum <= 0.0 or maximum > 90.0:
        raise ValueError("Maximum draft jaw angle must be within 0–90 degrees.")

    # A 0.05-degree grid is intentionally simple, deterministic, and more
    # precise than this disposable workspace experiment requires.
    angles = np.linspace(-maximum, maximum, int(maximum * 40.0) + 1)
    best = None
    lower_h = np.append(lower, 1.0)
    for angle in angles:
        matrix = hinge_rotation_matrix(hinge_left_mm, hinge_right_mm, angle)
        opened = (matrix @ lower_h)[:3]
        gap = float(np.linalg.norm(opened - upper))
        candidate = (abs(gap - target), abs(float(angle)), float(angle), matrix, opened, gap)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    assert best is not None
    _error, _absolute_angle, angle, matrix, opened, gap = best
    return angle, matrix, opened, gap


def vtk_matrix_elements(matrix: np.ndarray) -> tuple[tuple[float, ...], ...]:
    """Return validated plain elements suitable for vtkMatrix4x4."""
    values = np.asarray(matrix, dtype=float)
    if values.shape != (4, 4) or not np.all(np.isfinite(values)):
        raise ValueError("Expected a finite 4 x 4 matrix.")
    return tuple(tuple(float(value) for value in row) for row in values)
