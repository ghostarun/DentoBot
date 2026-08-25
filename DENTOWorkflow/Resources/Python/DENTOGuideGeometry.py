"""Trajectory guides, robot-interface docks, and printable-template fusion.

The labelmap-style Boolean sequence adapts the geometric strategy demonstrated
by SlicerFSP SurgicalGuide ``RingsAndBooleans``: reserve docking clearance in
the shell, add load-spreading attachment geometry, unite the guide solids, and
finally restore every channel.  The trajectory-aligned drill-guide sleeves and
the four occlusal-plane robot docks are intentionally separate geometry
families.  DENTOBOT keeps explicit world-RAS/MRML provenance; this module does
not import SlicerFSP or depend on display names/global editor state.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

from DENTOTemplateGeometry import create_hollow_sleeve, surface_topology


MAX_SAMPLE_POINTS = 48_000_000
MAX_DISCARDED_OCCUPIED_ARTIFACT_VOLUME_MM3 = 0.1


def _vector(values, label: str) -> np.ndarray:
    result = np.asarray(values, dtype=float)
    if result.shape != (3,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{label} must contain three finite world-RAS values.")
    return result


def _triangulated_clean(poly_data: vtk.vtkPolyData) -> vtk.vtkPolyData:
    if not poly_data or not poly_data.GetNumberOfCells():
        raise ValueError("A non-empty polygonal surface is required.")
    triangle = vtk.vtkTriangleFilter()
    triangle.SetInputData(poly_data)
    clean = vtk.vtkCleanPolyData()
    clean.SetInputConnection(triangle.GetOutputPort())
    clean.Update()
    output = vtk.vtkPolyData()
    output.DeepCopy(clean.GetOutput())
    return output


def _append_surfaces(surfaces: Sequence[vtk.vtkPolyData]) -> vtk.vtkPolyData:
    append = vtk.vtkAppendPolyData()
    appended = 0
    for surface in surfaces:
        if surface and surface.GetNumberOfCells():
            append.AddInputData(surface)
            appended += 1
    if not appended:
        raise ValueError("At least one non-empty guide surface is required.")
    append.Update()
    return _triangulated_clean(append.GetOutput())


def filter_tiny_occupied_region_artifacts(
    ranked_labels: np.ndarray,
    occupied_region_sizes: Sequence[int],
    voxel_spacing_mm: Sequence[float],
) -> tuple[np.ndarray, dict]:
    """Retain one printable region when every other region is microscopic noise."""

    labels = np.asarray(ranked_labels)
    region_sizes = [int(size) for size in occupied_region_sizes]
    spacing = np.asarray(voxel_spacing_mm, dtype=float)
    if (
        spacing.shape != (3,)
        or not np.all(np.isfinite(spacing))
        or np.any(spacing <= 0)
    ):
        raise ValueError(
            "Occupied-region voxel spacing must contain three positive values."
        )
    voxel_volume_mm3 = float(np.prod(spacing))
    maximum_artifact_sample_count = max(
        1,
        int(
            math.floor(
                MAX_DISCARDED_OCCUPIED_ARTIFACT_VOLUME_MM3
                / voxel_volume_mm3
                + 1e-12
            )
        ),
    )
    retained_region_sizes = [
        size for size in region_sizes if size > maximum_artifact_sample_count
    ]
    cleanup_applied = (
        len(region_sizes) > 1
        and len(retained_region_sizes) == 1
        and len(retained_region_sizes) < len(region_sizes)
    )
    removed_region_sizes = (
        [size for size in region_sizes if size <= maximum_artifact_sample_count]
        if cleanup_applied
        else []
    )
    filtered_mask = labels == 1 if cleanup_applied else labels > 0
    final_region_sizes = retained_region_sizes if cleanup_applied else region_sizes
    return filtered_mask, {
        "rawOccupiedVolumeRegionCount": len(region_sizes),
        "rawOccupiedVolumeRegionSizes": region_sizes,
        "occupiedVolumeRegionCount": len(final_region_sizes),
        "occupiedVolumeRegionSizes": final_region_sizes,
        "occupiedArtifactVoxelVolumeMm3": voxel_volume_mm3,
        "maximumDiscardedOccupiedArtifactVolumeMm3": (
            MAX_DISCARDED_OCCUPIED_ARTIFACT_VOLUME_MM3
        ),
        "maximumDiscardedOccupiedArtifactSampleCount": (
            maximum_artifact_sample_count
        ),
        "removedTinyOccupiedRegionCount": len(removed_region_sizes),
        "removedTinyOccupiedSampleCount": sum(removed_region_sizes),
        "removedTinyOccupiedApproximateVolumeMm3": (
            sum(removed_region_sizes) * voxel_volume_mm3
        ),
        "removedSingleVoxelOccupiedRegionCount": sum(
            1 for size in removed_region_sizes if size == 1
        ),
        "removedSingleVoxelOccupiedSampleCount": sum(
            size for size in removed_region_sizes if size == 1
        ),
        "tinyOccupiedArtifactCleanupApplied": cleanup_applied,
    }


def _unit(values, label: str) -> np.ndarray:
    vector = _vector(values, label)
    length = float(np.linalg.norm(vector))
    if length <= 1e-8:
        raise ValueError(f"{label} must have non-zero length.")
    return vector / length


def _stable_transverse_axis(axis: np.ndarray) -> np.ndarray:
    references = np.eye(3, dtype=float)
    reference = references[int(np.argmin(np.abs(references @ axis)))]
    transverse = reference - float(np.dot(reference, axis)) * axis
    length = float(np.linalg.norm(transverse))
    if length <= 1e-8:
        raise ValueError("Could not construct a stable transverse docking axis.")
    return transverse / length


def compute_target_docking_frame(
    tooth_surface_world: vtk.vtkPolyData,
    trajectories: Sequence[dict],
    *,
    crown_cap_fraction: float = 0.10,
) -> dict:
    """Derive a deterministic target-tooth occlusal frame in world RAS.

    The frame origin is the crown-cap centroid.  Approved trajectory axes
    establish crown/root polarity, while +Z is the fitted target-crown
    occlusal-plane normal oriented crown-to-root.  +X follows the dominant
    crown-cap direction projected into that plane, with a deterministic RAS
    fallback for near-circular caps; +Y completes a right-handed frame.  No
    world axis is interpreted as anatomical.
    """

    surface = _triangulated_clean(tooth_surface_world)
    point_data = surface.GetPoints().GetData() if surface.GetPoints() else None
    if not point_data:
        raise ValueError("The target tooth has no usable world-RAS surface points.")
    points = np.asarray(vtk_to_numpy(point_data), dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] < 12:
        raise ValueError("The target tooth surface is too small for a docking frame.")
    fraction = float(crown_cap_fraction)
    if not math.isfinite(fraction) or not 0.05 <= fraction <= 0.30:
        raise ValueError("Docking crown-cap fraction must be 5–30%.")
    if not trajectories or len(trajectories) > 2:
        raise ValueError("The target docking frame requires one or two trajectories.")

    axes = []
    trajectory_geometry = []
    for index, trajectory in enumerate(trajectories):
        entry = _vector(trajectory.get("entryRas"), f"Trajectory {index + 1} Entry")
        target = _vector(trajectory.get("targetRas"), f"Trajectory {index + 1} Target")
        axis = _unit(target - entry, f"Trajectory {index + 1} axis")
        if axes and float(np.dot(axis, axes[0])) < 0.0:
            axis = -axis
        axes.append(axis)
        trajectory_geometry.append(
            {
                "entryRas": [float(value) for value in entry],
                "targetRas": [float(value) for value in target],
                "axisRas": [float(value) for value in axis],
            }
        )
    mean_trajectory_axis = _unit(
        np.mean(np.asarray(axes), axis=0),
        "Mean trajectory axis",
    )
    deviations = [
        math.degrees(
            math.acos(
                float(np.clip(np.dot(axis, mean_trajectory_axis), -1.0, 1.0))
            )
        )
        for axis in axes
    ]

    crown_scores = points @ (-mean_trajectory_axis)
    threshold = float(np.quantile(crown_scores, 1.0 - fraction))
    crown_points = points[crown_scores >= threshold]
    if crown_points.shape[0] < 6:
        crown_points = points[np.argsort(crown_scores)[-max(6, points.shape[0] // 20):]]
    origin = np.mean(crown_points, axis=0)
    centered = crown_points - origin
    covariance = centered.T @ centered
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)

    normal_candidate = np.asarray(eigenvectors[:, int(np.argmin(eigenvalues))], dtype=float)
    normal_length = float(np.linalg.norm(normal_candidate))
    occlusal_method = "TargetCrownCapPca"
    occlusal_fallback_reason = ""
    if normal_length <= 1e-8:
        z_axis = mean_trajectory_axis.copy()
        occlusal_method = "MeanTrajectoryPerpendicularFallback"
        occlusal_fallback_reason = "Crown-cap covariance was degenerate."
    else:
        normal_candidate /= normal_length
        if float(np.dot(normal_candidate, mean_trajectory_axis)) < 0.0:
            normal_candidate = -normal_candidate
        normal_alignment = float(np.dot(normal_candidate, mean_trajectory_axis))
        if normal_alignment < 0.50:
            z_axis = mean_trajectory_axis.copy()
            occlusal_method = "MeanTrajectoryPerpendicularFallback"
            occlusal_fallback_reason = (
                "Target crown-cap fit exceeded the 60-degree safety tilt limit."
            )
        else:
            z_axis = normal_candidate

    candidate = np.asarray(eigenvectors[:, int(np.argmax(eigenvalues))], dtype=float)
    candidate -= float(np.dot(candidate, z_axis)) * z_axis
    if float(np.linalg.norm(candidate)) <= 1e-8:
        candidate = _stable_transverse_axis(z_axis)
        x_method = "StableRasProjectionFallback"
    else:
        candidate /= float(np.linalg.norm(candidate))
        stable = _stable_transverse_axis(z_axis)
        if float(np.dot(candidate, stable)) < 0.0:
            candidate = -candidate
        x_method = "CrownCapPrincipalAxis"
    x_axis = candidate
    y_axis = _unit(np.cross(z_axis, x_axis), "Docking frame Y axis")
    x_axis = _unit(np.cross(y_axis, z_axis), "Docking frame X axis")
    matrix = np.eye(4, dtype=float)
    matrix[:3, 0] = x_axis
    matrix[:3, 1] = y_axis
    matrix[:3, 2] = z_axis
    matrix[:3, 3] = origin
    return {
        "originRas": [float(value) for value in origin],
        "xAxisRas": [float(value) for value in x_axis],
        "yAxisRas": [float(value) for value in y_axis],
        "zAxisRas": [float(value) for value in z_axis],
        "meanTrajectoryAxisRas": [
            float(value) for value in mean_trajectory_axis
        ],
        "occlusalNormalRas": [float(value) for value in z_axis],
        "matrixColumnMajorRas": [
            float(matrix[row, column])
            for column in range(4)
            for row in range(4)
        ],
        "method": "TrajectoryPolarityTargetCrownOcclusalFrameV2",
        "xAxisMethod": x_method,
        "occlusalPlaneMethod": occlusal_method,
        "occlusalPlaneFallbackReason": occlusal_fallback_reason,
        "occlusalTiltFromMeanTrajectoryDeg": float(
            math.degrees(
                math.acos(
                    float(
                        np.clip(
                            np.dot(z_axis, mean_trajectory_axis),
                            -1.0,
                            1.0,
                        )
                    )
                )
            )
        ),
        "crownCapCovarianceEigenvalues": [
            float(value) for value in eigenvalues
        ],
        "crownCapFraction": fraction,
        "crownCapPointCount": int(crown_points.shape[0]),
        "crownScoreThresholdMm": threshold,
        "trajectoryCount": len(trajectory_geometry),
        "trajectoryGeometry": trajectory_geometry,
        "maxTrajectoryAxisDeviationDeg": float(max(deviations, default=0.0)),
        "orthonormalError": float(
            np.max(np.abs(matrix[:3, :3].T @ matrix[:3, :3] - np.eye(3)))
        ),
        "determinant": float(np.linalg.det(matrix[:3, :3])),
    }


def normalize_target_docking_parameters(
    *,
    pattern_radius_mm: float,
    outer_diameter_mm: float,
    bore_diameter_mm: float,
    connector_diameter_mm: float,
    connector_thickness_mm: float,
    shared_depth_mm: float,
    individual_depths_mm: Sequence[float],
    individual_depths_enabled: bool,
    clearance_mm: float,
    reinforcement_radial_mm: float,
    processing_resolution_mm: float,
    yaw_deg: float = 0.0,
    collision_clearance_mm: float = 0.5,
) -> dict:
    depths = [float(value) for value in individual_depths_mm]
    if len(depths) != 4:
        raise ValueError("Exactly four target-frame docking depths are required.")
    shared_depth = float(shared_depth_mm)
    values = {
        "patternRadiusMm": float(pattern_radius_mm),
        "outerDiameterMm": float(outer_diameter_mm),
        "boreDiameterMm": float(bore_diameter_mm),
        "connectorDiameterMm": float(connector_diameter_mm),
        "connectorThicknessMm": float(connector_thickness_mm),
        "sharedDepthMm": shared_depth,
        "clearanceMm": float(clearance_mm),
        "reinforcementRadialMm": float(reinforcement_radial_mm),
        "processingResolutionMm": float(processing_resolution_mm),
        "yawDeg": float(yaw_deg),
        "collisionClearanceMm": float(collision_clearance_mm),
    }
    if any(not math.isfinite(value) for value in [*values.values(), *depths]):
        raise ValueError("Target-frame docking dimensions must be finite.")
    if not 2.0 <= values["patternRadiusMm"] <= 40.0:
        raise ValueError("Centroid-to-dock radius must be 2–40 mm.")
    if not 0.2 <= values["boreDiameterMm"] < values["outerDiameterMm"]:
        raise ValueError("Dock dimensions require 0.2 mm ≤ bore < outer diameter.")
    if values["outerDiameterMm"] > 12.0:
        raise ValueError("Dock outer diameter must not exceed 12 mm.")
    if values["connectorDiameterMm"] < values["outerDiameterMm"]:
        raise ValueError("Connector width must be at least the dock outer diameter.")
    if values["connectorThicknessMm"] <= 0.0:
        raise ValueError("Connector thickness must be positive.")
    if values["clearanceMm"] < 0.0 or values["reinforcementRadialMm"] <= 0.0:
        raise ValueError("Dock clearance cannot be negative and reinforcement must be positive.")
    if not 0.1 <= values["processingResolutionMm"] <= 2.0:
        raise ValueError("Dock processing resolution must be 0.10–2.00 mm.")
    if not -180.0 <= values["yawDeg"] <= 180.0:
        raise ValueError("Dock yaw must be between -180 and 180 degrees.")
    if not 0.0 <= values["collisionClearanceMm"] <= 10.0:
        raise ValueError("Dock collision clearance must be 0–10 mm.")
    active_depths = depths if bool(individual_depths_enabled) else [shared_depth] * 4
    if any(depth <= 0.0 or depth > 30.0 for depth in active_depths):
        raise ValueError("Every docking depth must be greater than 0 and at most 30 mm.")
    values["individualDepthsEnabled"] = bool(individual_depths_enabled)
    values["depthsMm"] = active_depths
    values["configuredIndividualDepthsMm"] = depths
    values["mechanicalSpecification"] = (
        "ProvisionalResearchFourIndependentOcclusalDocksV2"
    )
    values["layoutSpecification"] = "FourIndependentOcclusalTangentDockBranches"
    values["topFaceDatum"] = "TargetCrownOcclusalPlane"
    values["depthDirection"] = "OcclusalNormalCrownToRoot"
    values["centralHubEnabled"] = False
    return values


def _target_docking_directions(frame: dict, yaw_deg: float) -> tuple[np.ndarray, ...]:
    x_axis = _unit(frame.get("xAxisRas"), "Docking frame X axis")
    y_axis = _unit(frame.get("yAxisRas"), "Docking frame Y axis")
    angle = math.radians(float(yaw_deg))
    x_rotated = math.cos(angle) * x_axis + math.sin(angle) * y_axis
    y_rotated = -math.sin(angle) * x_axis + math.cos(angle) * y_axis
    return (
        _unit(x_rotated, "Yaw-rotated docking X axis"),
        _unit(y_rotated, "Yaw-rotated docking Y axis"),
        _unit(-x_rotated, "Yaw-rotated docking -X axis"),
        _unit(-y_rotated, "Yaw-rotated docking -Y axis"),
    )


def _sample_target_docking_obstacles(
    obstacle_surfaces_world: Sequence[vtk.vtkPolyData],
) -> tuple[np.ndarray, int]:
    """Return one deterministic point cache for a complete yaw sweep."""

    point_sets = []
    source_point_count = 0
    for surface in obstacle_surfaces_world:
        surface = _triangulated_clean(surface)
        points_data = surface.GetPoints().GetData() if surface.GetPoints() else None
        if not points_data:
            continue
        points = np.asarray(vtk_to_numpy(points_data), dtype=float)
        source_point_count += int(points.shape[0])
        if points.shape[0] > 20000:
            indices = np.linspace(0, points.shape[0] - 1, 20000, dtype=int)
            points = points[indices]
        point_sets.append(points)
    obstacle_points = (
        np.vstack(point_sets)
        if point_sets
        else np.empty((0, 3), dtype=float)
    )
    return obstacle_points, source_point_count


def _evaluate_target_docking_obstacle_points(
    frame: dict,
    parameters: dict,
    obstacle_points: np.ndarray,
    *,
    obstacle_surface_count: int,
    source_point_count: int,
) -> dict:
    origin = _vector(frame.get("originRas"), "Docking frame origin")
    depth_axis = _unit(frame.get("zAxisRas"), "Docking depth axis")
    directions = _target_docking_directions(frame, parameters.get("yawDeg", 0.0))
    radius = float(parameters["patternRadiusMm"])
    dock_radius = float(parameters["outerDiameterMm"]) / 2.0
    requested_clearance = float(parameters.get("collisionClearanceMm", 0.0))
    effective_radius = dock_radius + requested_clearance
    depths = [float(value) for value in parameters["depthsMm"]]

    per_dock = []
    for index, (direction, depth) in enumerate(zip(directions, depths)):
        top_center = origin + radius * direction
        if obstacle_points.size:
            relative = obstacle_points - top_center
            axial = relative @ depth_axis
            transverse = relative - axial[:, None] * depth_axis
            radial = np.linalg.norm(transverse, axis=1)
            radial_gap = radial - effective_radius
            axial_gap = np.maximum(np.maximum(-axial, axial - depth), 0.0)
            outside = np.sqrt(np.maximum(radial_gap, 0.0) ** 2 + axial_gap ** 2)
            inside = np.minimum(
                np.maximum(
                    radial_gap,
                    np.maximum(-axial, axial - depth),
                ),
                0.0,
            )
            signed_distance = outside + inside
            minimum = float(np.min(signed_distance))
            colliding_count = int(np.count_nonzero(signed_distance <= 0.0))
        else:
            minimum = None
            colliding_count = 0
        per_dock.append(
            {
                "index": index,
                "topFaceCenterRas": [float(value) for value in top_center],
                "minimumSampledClearanceMm": minimum,
                "collidingSamplePointCount": colliding_count,
                "collisionDetected": bool(colliding_count),
            }
        )
    finite_clearances = [
        item["minimumSampledClearanceMm"]
        for item in per_dock
        if item["minimumSampledClearanceMm"] is not None
        and math.isfinite(item["minimumSampledClearanceMm"])
    ]
    return {
        "method": "SameArchSurfacePointFiniteCylinderScreenV1",
        "yawDeg": float(parameters.get("yawDeg", 0.0)),
        "requestedClearanceMm": requested_clearance,
        "obstacleSurfaceCount": int(obstacle_surface_count),
        "sourceObstaclePointCount": source_point_count,
        "sampledObstaclePointCount": int(obstacle_points.shape[0]),
        "collidingDockCount": sum(
            int(item["collisionDetected"]) for item in per_dock
        ),
        "collidingSamplePointCount": sum(
            item["collidingSamplePointCount"] for item in per_dock
        ),
        "minimumSampledClearanceMm": (
            float(min(finite_clearances)) if finite_clearances else None
        ),
        "docks": per_dock,
    }


def evaluate_target_docking_obstacle_clearance(
    frame: dict,
    parameters: dict,
    obstacle_surfaces_world: Sequence[vtk.vtkPolyData],
) -> dict:
    """Evaluate finite dock-cylinder clearance against same-arch tooth surfaces.

    This is a deterministic draft-placement screen, not clinical collision
    validation. It samples the supplied closed-surface vertices against the
    analytical finite cylinders and reports every assumption and result.
    """

    obstacle_points, source_point_count = _sample_target_docking_obstacles(
        obstacle_surfaces_world
    )
    return _evaluate_target_docking_obstacle_points(
        frame,
        parameters,
        obstacle_points,
        obstacle_surface_count=len(obstacle_surfaces_world),
        source_point_count=source_point_count,
    )


def find_collision_aware_target_docking_yaw(
    frame: dict,
    parameters: dict,
    obstacle_surfaces_world: Sequence[vtk.vtkPolyData],
    *,
    step_deg: float = 5.0,
) -> dict:
    """Choose the least-colliding deterministic draft yaw around the frame Z axis."""

    step = float(step_deg)
    if not math.isfinite(step) or not 1.0 <= step <= 30.0:
        raise ValueError("Automatic docking-yaw step must be 1–30 degrees.")
    candidate_count = max(1, int(math.ceil(360.0 / step)))
    obstacle_points, source_point_count = _sample_target_docking_obstacles(
        obstacle_surfaces_world
    )
    candidates = []
    for index in range(candidate_count):
        yaw = -180.0 + index * (360.0 / candidate_count)
        candidate_parameters = dict(parameters)
        candidate_parameters["yawDeg"] = yaw
        report = _evaluate_target_docking_obstacle_points(
            frame,
            candidate_parameters,
            obstacle_points,
            obstacle_surface_count=len(obstacle_surfaces_world),
            source_point_count=source_point_count,
        )
        clearance = report["minimumSampledClearanceMm"]
        candidates.append(
            {
                "yawDeg": yaw,
                "report": report,
                "rank": (
                    int(report["collidingDockCount"]),
                    int(report["collidingSamplePointCount"]),
                    -float(clearance) if clearance is not None else -math.inf,
                    abs(float(yaw)),
                    float(yaw),
                ),
            }
        )
    winner = min(candidates, key=lambda item: item["rank"])
    return {
        "method": "DeterministicSameArchYawSweepV1",
        "stepDeg": 360.0 / candidate_count,
        "candidateCount": candidate_count,
        "selectedYawDeg": float(winner["yawDeg"]),
        "selectedClearanceReport": winner["report"],
        "collisionFreeCandidateCount": sum(
            int(item["report"]["collidingDockCount"] == 0)
            for item in candidates
        ),
    }


def _closed_cylinder(
    center_ras,
    axis_ras,
    *,
    length_mm: float,
    radius_mm: float,
    resolution: int = 96,
) -> vtk.vtkPolyData:
    center = _vector(center_ras, "Cylinder center")
    axis = _vector(axis_ras, "Cylinder axis")
    axis_length = float(np.linalg.norm(axis))
    length = float(length_mm)
    radius = float(radius_mm)
    if axis_length <= 1e-8:
        raise ValueError("Cylinder axis must have non-zero length.")
    if not math.isfinite(length) or not math.isfinite(radius):
        raise ValueError("Cylinder dimensions must be finite.")
    if length <= 0.0 or radius <= 0.0:
        raise ValueError("Cylinder length and radius must be positive.")
    axis /= axis_length

    cylinder = vtk.vtkCylinderSource()
    cylinder.SetRadius(radius)
    cylinder.SetHeight(length)
    cylinder.SetResolution(int(resolution))
    cylinder.CappingOn()
    cylinder.Update()

    source_axis = np.array((0.0, 1.0, 0.0), dtype=float)
    rotation_axis = np.cross(source_axis, axis)
    rotation_axis_length = float(np.linalg.norm(rotation_axis))
    transform = vtk.vtkTransform()
    transform.PostMultiply()
    if rotation_axis_length > 1e-10:
        rotation_axis /= rotation_axis_length
        angle = math.degrees(
            math.acos(float(np.clip(np.dot(source_axis, axis), -1.0, 1.0)))
        )
        transform.RotateWXYZ(angle, *rotation_axis)
    elif float(np.dot(source_axis, axis)) < 0.0:
        transform.RotateWXYZ(180.0, 1.0, 0.0, 0.0)
    transform.Translate(*center)
    transform_filter = vtk.vtkTransformPolyDataFilter()
    transform_filter.SetInputConnection(cylinder.GetOutputPort())
    transform_filter.SetTransform(transform)
    transform_filter.Update()
    return _triangulated_clean(transform_filter.GetOutput())


def _voxel_boolean_components(
    additive_surfaces: Sequence[vtk.vtkPolyData],
    subtractive_surfaces: Sequence[vtk.vtkPolyData] = (),
    *,
    spacing_mm: float,
    scalar_name: str,
) -> tuple[vtk.vtkPolyData, dict]:
    """Resolve overlapping closed primitives in one cropped binary domain."""

    spacing = float(spacing_mm)
    if not math.isfinite(spacing) or not 0.1 <= spacing <= 2.0:
        raise ValueError("Voxel Boolean resolution must be 0.10–2.00 mm.")
    additive = [_triangulated_clean(surface) for surface in additive_surfaces]
    subtractive = [_triangulated_clean(surface) for surface in subtractive_surfaces]
    if not additive:
        raise ValueError("At least one additive docking primitive is required.")
    all_surfaces = [*additive, *subtractive]
    bounds = [math.inf, -math.inf, math.inf, -math.inf, math.inf, -math.inf]
    for surface in all_surfaces:
        surface_bounds = surface.GetBounds()
        for axis in range(3):
            bounds[2 * axis] = min(bounds[2 * axis], surface_bounds[2 * axis])
            bounds[2 * axis + 1] = max(
                bounds[2 * axis + 1], surface_bounds[2 * axis + 1]
            )
    padding = max(1.0, 3.0 * spacing)
    sample_bounds = tuple(
        value + (-padding if index % 2 == 0 else padding)
        for index, value in enumerate(bounds)
    )
    dimensions = tuple(
        max(
            3,
            int(
                math.ceil(
                    (sample_bounds[2 * axis + 1] - sample_bounds[2 * axis])
                    / spacing
                )
            )
            + 1,
        )
        for axis in range(3)
    )
    sample_count = int(np.prod(dimensions, dtype=np.int64))
    if sample_count > MAX_SAMPLE_POINTS:
        raise ValueError(
            "The target-docking voxel domain requests "
            f"{sample_count:,} samples; increase processing resolution."
        )

    template_image = None

    def mask_for(surface: vtk.vtkPolyData) -> np.ndarray:
        nonlocal template_image
        implicit = vtk.vtkImplicitPolyDataDistance()
        implicit.SetInput(surface)
        sample = vtk.vtkSampleFunction()
        sample.SetImplicitFunction(implicit)
        sample.SetModelBounds(*sample_bounds)
        sample.SetSampleDimensions(*dimensions)
        sample.ComputeNormalsOff()
        sample.Update()
        if template_image is None:
            template_image = vtk.vtkImageData()
            template_image.DeepCopy(sample.GetOutput())
        return vtk_to_numpy(
            sample.GetOutput().GetPointData().GetScalars()
        ).reshape(dimensions[2], dimensions[1], dimensions[0]) <= 0.0

    result_mask = np.zeros(
        (dimensions[2], dimensions[1], dimensions[0]),
        dtype=bool,
    )
    for surface in additive:
        result_mask |= mask_for(surface)
    additive_count = int(np.count_nonzero(result_mask))
    subtract_count = 0
    excluded_occupied_count = 0
    for surface in subtractive:
        subtract_mask = mask_for(surface)
        subtract_count += int(np.count_nonzero(subtract_mask))
        excluded_occupied_count += int(np.count_nonzero(result_mask & subtract_mask))
        result_mask &= ~subtract_mask
    result_mask[0, :, :] = False
    result_mask[-1, :, :] = False
    result_mask[:, 0, :] = False
    result_mask[:, -1, :] = False
    result_mask[:, :, 0] = False
    result_mask[:, :, -1] = False
    occupied = int(np.count_nonzero(result_mask))
    if not occupied:
        raise ValueError("Target-docking Boolean produced no occupied volume.")

    binary_image = vtk.vtkImageData()
    binary_image.DeepCopy(template_image)
    scalars = numpy_to_vtk(
        np.ascontiguousarray(result_mask.astype(np.uint8).ravel()),
        deep=True,
        array_type=vtk.VTK_UNSIGNED_CHAR,
    )
    scalars.SetName(str(scalar_name))
    binary_image.GetPointData().SetScalars(scalars)
    contour = vtk.vtkFlyingEdges3D()
    contour.SetInputData(binary_image)
    contour.SetValue(0, 0.5)
    contour.ComputeNormalsOff()
    contour.ComputeGradientsOff()
    triangle = vtk.vtkTriangleFilter()
    triangle.SetInputConnection(contour.GetOutputPort())
    clean = vtk.vtkCleanPolyData()
    clean.SetInputConnection(triangle.GetOutputPort())
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputConnection(clean.GetOutputPort())
    normals.ConsistencyOn()
    normals.AutoOrientNormalsOn()
    normals.SplittingOff()
    normals.Update()
    output = vtk.vtkPolyData()
    output.DeepCopy(normals.GetOutput())
    topology = surface_topology(output)
    if topology["boundaryOrNonManifoldEdgeCount"]:
        raise RuntimeError(
            "Target-docking Boolean is not watertight/manifold "
            f"({topology['boundaryOrNonManifoldEdgeCount']} invalid edges)."
        )
    return output, {
        **topology,
        "method": "TightVoxelPrimitiveBoolean",
        "requestedSpacingMm": spacing,
        "actualSpacingMm": tuple(float(value) for value in binary_image.GetSpacing()),
        "sampleBoundsRas": sample_bounds,
        "sampleDimensions": dimensions,
        "samplePointCount": sample_count,
        "occupiedSampleCount": occupied,
        "additiveSampleCount": additive_count,
        "subtractiveSampleCount": subtract_count,
        "excludedOccupiedSampleCount": excluded_occupied_count,
    }


def create_target_frame_docking_geometry(
    frame: dict,
    parameters: dict,
) -> tuple[dict[str, vtk.vtkPolyData], dict]:
    """Create four independent hollow docks in the target-crown frame.

    Each robot-facing top/opening centre lies exactly on the fitted target
    crown/occlusal plane.  Adjustable depth proceeds along the crown-to-root
    occlusal normal.  No solid is placed at the crown centroid and no radial
    spoke is routed across the trajectory-guide envelope; attachment to the
    patient shell is generated independently for each dock during Step 5B.
    """

    origin = _vector(frame.get("originRas"), "Docking frame origin")
    x_axis = _unit(frame.get("xAxisRas"), "Docking frame X axis")
    y_axis = _unit(frame.get("yAxisRas"), "Docking frame Y axis")
    z_axis = _unit(frame.get("zAxisRas"), "Docking frame Z axis")
    if (
        abs(float(np.dot(x_axis, y_axis))) > 1e-5
        or abs(float(np.dot(x_axis, z_axis))) > 1e-5
        or abs(float(np.dot(y_axis, z_axis))) > 1e-5
        or float(np.dot(np.cross(x_axis, y_axis), z_axis)) < 0.999
    ):
        raise ValueError("The target docking frame must be right-handed and orthonormal.")

    radius = float(parameters["patternRadiusMm"])
    outer_radius = float(parameters["outerDiameterMm"]) / 2.0
    bore_radius = float(parameters["boreDiameterMm"]) / 2.0
    clearance = float(parameters["clearanceMm"])
    reinforcement = float(parameters["reinforcementRadialMm"])
    depths = [float(value) for value in parameters["depthsMm"]]
    spacing = float(parameters["processingResolutionMm"])
    yaw_deg = float(parameters.get("yawDeg", 0.0))
    directions = _target_docking_directions(frame, yaw_deg)
    labels = ("+X", "+Y", "-X", "-Y")

    docking_parts = []
    clearance_parts = []
    reinforcement_parts = []
    channel_parts = []
    dock_metrics = []
    # Frame +Z is the fitted crown-to-root occlusal normal.  The designated
    # robot-facing top surface is the end cap on the reference plane; dock
    # depth proceeds from that face toward the shell/root side along +Z.
    depth_axis = z_axis
    for index, (direction, label, depth) in enumerate(zip(directions, labels, depths)):
        top_center = origin + radius * direction
        dock_component = _closed_cylinder(
            top_center + depth_axis * (depth / 2.0),
            depth_axis,
            length_mm=depth,
            radius_mm=outer_radius,
        )
        docking_parts.append(dock_component)
        channel = _closed_cylinder(
            top_center + depth_axis * (depth / 2.0),
            depth_axis,
            length_mm=depth + 2.0 * spacing,
            radius_mm=bore_radius,
        )
        channel_parts.append(channel)
        clearance_parts.append(
            _closed_cylinder(
                top_center + depth_axis * (depth / 2.0),
                depth_axis,
                length_mm=depth + 2.0 * clearance,
                radius_mm=outer_radius + clearance,
            )
        )
        reinforcement_component = _closed_cylinder(
            top_center + depth_axis * ((depth + reinforcement) / 2.0),
            depth_axis,
            length_mm=depth + reinforcement,
            radius_mm=outer_radius + reinforcement,
        )
        reinforcement_parts.append(reinforcement_component)
        terminal_center = top_center + depth_axis * depth
        dock_metrics.append(
            {
                "index": index,
                "label": label,
                "topFaceCenterRas": [float(value) for value in top_center],
                # Retain the old key for scene/report readers while making its
                # top-face meaning explicit in the schema-v2 fields.
                "topCenterRas": [float(value) for value in top_center],
                "terminalCenterRas": [
                    float(value) for value in terminal_center
                ],
                "axisRas": [float(value) for value in depth_axis],
                "extrusionDirectionRas": [
                    float(value) for value in depth_axis
                ],
                "depthMm": depth,
                "radialDistanceMm": radius,
                "topFacePlaneResidualMm": float(
                    np.dot(top_center - origin, z_axis)
                ),
                "topPlaneResidualMm": float(np.dot(top_center - origin, z_axis)),
                "terminalPlaneOffsetMm": float(
                    np.dot(terminal_center - origin, z_axis)
                ),
            }
        )

    docking, docking_topology = _voxel_boolean_components(
        docking_parts,
        spacing_mm=spacing,
        scalar_name="DENTOBOT.TargetDockingSolidMask",
    )
    clearance_surface, clearance_topology = _voxel_boolean_components(
        clearance_parts,
        spacing_mm=spacing,
        scalar_name="DENTOBOT.TargetDockingClearanceMask",
    )
    reinforcement_surface, reinforcement_topology = _voxel_boolean_components(
        reinforcement_parts,
        spacing_mm=spacing,
        scalar_name="DENTOBOT.TargetDockingReinforcementMask",
    )
    channels, channel_topology = _voxel_boolean_components(
        channel_parts,
        spacing_mm=spacing,
        scalar_name="DENTOBOT.TargetDockingChannelsMask",
    )
    preview, preview_topology = _voxel_boolean_components(
        docking_parts,
        channel_parts,
        spacing_mm=spacing,
        scalar_name="DENTOBOT.TargetDockingPreviewMask",
    )
    surfaces = {
        "preview": preview,
        "docking": docking,
        "clearance": clearance_surface,
        "reinforcement": reinforcement_surface,
        "channels": channels,
        "dockComponents": list(docking_parts),
        "reinforcementComponents": list(reinforcement_parts),
    }
    return surfaces, {
        "method": "TargetFrameFourIndependentOcclusalTangentDocksV2",
        "mechanicalSpecification": parameters.get(
            "mechanicalSpecification",
            "ProvisionalResearchFourIndependentOcclusalDocksV2",
        ),
        "layoutSpecification": "FourIndependentOcclusalTangentDockBranches",
        "topFaceDatum": "TargetCrownOcclusalPlane",
        "depthDirection": "OcclusalNormalCrownToRoot",
        "frame": dict(frame),
        "parameters": dict(parameters),
        "yawDeg": yaw_deg,
        "dockCount": 4,
        "independentDockComponentCount": 4,
        "centralHubPresent": False,
        "radialSpokeCount": 0,
        "docks": dock_metrics,
        "topPlaneMaxResidualMm": float(
            max(abs(item["topPlaneResidualMm"]) for item in dock_metrics)
        ),
        "topology": {
            "preview": preview_topology,
            "docking": docking_topology,
            "clearance": clearance_topology,
            "reinforcement": reinforcement_topology,
            "channels": channel_topology,
        },
    }


def combine_guide_geometry_sets(
    geometry_sets: Sequence[dict[str, vtk.vtkPolyData]],
) -> dict[str, vtk.vtkPolyData]:
    """Append guide families for one final cropped voxel fusion."""

    if not geometry_sets:
        raise ValueError("At least one guide geometry set is required.")
    required = ("docking", "clearance", "reinforcement", "channels")
    return {
        key: _append_surfaces([geometry[key] for geometry in geometry_sets])
        for key in required
    }


def create_shell_contact_reinforcement(
    shell_world: vtk.vtkPolyData,
    docking_world: vtk.vtkPolyData,
    *,
    bridge_diameter_mm: float,
    endpoint_overlap_mm: float | None = None,
    maximum_gap_mm: float = 12.0,
) -> tuple[vtk.vtkPolyData, dict]:
    """Create a recorded load-spreading link from docking to the shell.

    The closest sampled docking-surface point is connected to its closest
    patient-shell point.  Both ends overlap by one bridge radius so the
    subsequent cropped voxel union has a real volumetric connection rather
    than relying on coincident/tangent polygons.
    """

    shell = _triangulated_clean(shell_world)
    docking = _triangulated_clean(docking_world)
    diameter = float(bridge_diameter_mm)
    endpoint_overlap = (
        diameter / 2.0
        if endpoint_overlap_mm is None
        else float(endpoint_overlap_mm)
    )
    maximum_gap = float(maximum_gap_mm)
    if not math.isfinite(diameter) or diameter <= 0.0:
        raise ValueError("Shell-contact bridge diameter must be positive.")
    if not math.isfinite(endpoint_overlap) or endpoint_overlap <= 0.0:
        raise ValueError("Shell-contact endpoint overlap must be positive.")
    if not math.isfinite(maximum_gap) or maximum_gap <= 0.0:
        raise ValueError("Maximum shell-contact gap must be positive.")
    shell_locator = vtk.vtkStaticCellLocator()
    shell_locator.SetDataSet(shell)
    shell_locator.BuildLocator()
    point_count = int(docking.GetNumberOfPoints())
    if point_count <= 0:
        raise ValueError("Docking geometry contains no points for shell contact.")
    sample_step = max(1, int(math.ceil(point_count / 6000.0)))
    best_distance = math.inf
    best_docking = None
    best_shell = None
    point = [0.0, 0.0, 0.0]
    for point_index in range(0, point_count, sample_step):
        docking.GetPoint(point_index, point)
        closest = [0.0, 0.0, 0.0]
        cell_id = vtk.reference(0)
        sub_id = vtk.reference(0)
        distance_squared = vtk.reference(0.0)
        shell_locator.FindClosestPoint(
            point,
            closest,
            cell_id,
            sub_id,
            distance_squared,
        )
        distance = math.sqrt(max(0.0, float(distance_squared)))
        if distance < best_distance:
            best_distance = distance
            best_docking = np.asarray(point, dtype=float).copy()
            best_shell = np.asarray(closest, dtype=float)
    if best_docking is None or best_shell is None or not math.isfinite(best_distance):
        raise RuntimeError("Could not locate a shell-contact point for the docking assembly.")
    if best_distance > maximum_gap:
        raise ValueError(
            "The docking assembly is too far from the patient shell for a "
            f"controlled reinforcement bridge ({best_distance:.2f} mm > "
            f"{maximum_gap:.2f} mm)."
        )
    axis = best_shell - best_docking
    if best_distance <= 1e-6:
        shell_center = np.asarray(shell.GetCenter(), dtype=float)
        axis = shell_center - best_docking
        if float(np.linalg.norm(axis)) <= 1e-6:
            axis = np.asarray((0.0, 0.0, 1.0), dtype=float)
    axis = _unit(axis, "Shell-contact bridge axis")
    radius = diameter / 2.0
    overlap = endpoint_overlap
    bridge_start = best_docking - axis * overlap
    bridge_end = best_shell + axis * overlap
    bridge_center = (bridge_start + bridge_end) / 2.0
    bridge_length = float(np.linalg.norm(bridge_end - bridge_start))
    bridge = _closed_cylinder(
        bridge_center,
        axis,
        length_mm=bridge_length,
        radius_mm=radius,
    )
    return bridge, {
        "method": "ClosestSurfaceOverlappingCylindricalReinforcement",
        "bridgeDiameterMm": diameter,
        "surfaceGapMm": best_distance,
        "maximumGapMm": maximum_gap,
        "endpointOverlapMm": overlap,
        "dockingPointRas": tuple(float(value) for value in best_docking),
        "shellPointRas": tuple(float(value) for value in best_shell),
        "axisRas": tuple(float(value) for value in axis),
        "sampledDockingPointCount": int(math.ceil(point_count / sample_step)),
        "topology": surface_topology(bridge),
    }


def create_independent_shell_contact_reinforcements(
    shell_world: vtk.vtkPolyData,
    dock_components_world: Sequence[vtk.vtkPolyData],
    *,
    bridge_diameter_mm: float,
    endpoint_overlap_mm: float,
    maximum_gap_mm: float = 12.0,
) -> tuple[vtk.vtkPolyData, dict]:
    """Attach every independent robot dock to the patient shell.

    A separate closest-surface branch is built for each dock component.  This
    avoids a crown-centred hub and makes a missing/unreachable branch a hard
    generation error instead of silently leaving a floating dock.
    """

    components = [
        _triangulated_clean(component)
        for component in dock_components_world
        if component and component.GetNumberOfCells()
    ]
    if len(components) != 4:
        raise ValueError(
            "Exactly four independent robot-dock components are required for shell attachment."
        )
    branches = []
    branch_metrics = []
    for index, component in enumerate(components):
        branch, metrics = create_shell_contact_reinforcement(
            shell_world,
            component,
            bridge_diameter_mm=bridge_diameter_mm,
            endpoint_overlap_mm=endpoint_overlap_mm,
            maximum_gap_mm=maximum_gap_mm,
        )
        branches.append(branch)
        branch_metrics.append({"dockIndex": index, **metrics})
    combined = _append_surfaces(branches)
    return combined, {
        "method": "FourIndependentClosestSurfaceDockAttachments",
        "branchCount": len(branches),
        "bridgeDiameterMm": float(bridge_diameter_mm),
        "endpointOverlapMm": float(endpoint_overlap_mm),
        "maximumGapMm": float(maximum_gap_mm),
        "branches": branch_metrics,
        "topology": surface_topology(combined),
    }


def subtract_guide_exclusion(
    source_world: vtk.vtkPolyData,
    exclusion_world: vtk.vtkPolyData,
    *,
    spacing_mm: float,
    scalar_name: str,
) -> tuple[vtk.vtkPolyData, dict]:
    """Clip a derived robot-interface surface against a protected guide envelope."""

    output, metrics = _voxel_boolean_components(
        [source_world],
        [exclusion_world],
        spacing_mm=spacing_mm,
        scalar_name=scalar_name,
    )
    return output, {
        **metrics,
        "method": "ProtectedTrajectoryGuideEnvelopeSubtraction",
        "sourceTopology": surface_topology(source_world),
        "exclusionTopology": surface_topology(exclusion_world),
    }


def normalize_docking_parameters(
    *,
    outer_diameter_mm: float,
    inner_diameter_mm: float,
    height_mm: float,
    clearance_mm: float,
    reinforcement_radial_mm: float,
    reinforcement_depth_mm: float,
    processing_resolution_mm: float,
) -> dict[str, float]:
    values = {
        "outerDiameterMm": float(outer_diameter_mm),
        "innerDiameterMm": float(inner_diameter_mm),
        "heightMm": float(height_mm),
        "clearanceMm": float(clearance_mm),
        "reinforcementRadialMm": float(reinforcement_radial_mm),
        "reinforcementDepthMm": float(reinforcement_depth_mm),
        "processingResolutionMm": float(processing_resolution_mm),
    }
    if any(not math.isfinite(value) for value in values.values()):
        raise ValueError("Docking dimensions must be finite.")
    if not 0.0 < values["innerDiameterMm"] < values["outerDiameterMm"]:
        raise ValueError("Docking diameters require 0 < inner < outer.")
    if values["heightMm"] <= 0.0 or values["reinforcementDepthMm"] <= 0.0:
        raise ValueError("Docking height and reinforcement depth must be positive.")
    if values["clearanceMm"] < 0.0:
        raise ValueError("Docking clearance cannot be negative.")
    if values["reinforcementRadialMm"] <= values["clearanceMm"]:
        raise ValueError(
            "Reinforcement radial width must exceed docking clearance so the collar can bridge to the shell."
        )
    if not 0.1 <= values["processingResolutionMm"] <= 2.0:
        raise ValueError("Guide processing resolution must be 0.10–2.00 mm.")
    return values


def create_multi_trajectory_docking_geometry(
    trajectories: Sequence[dict],
    parameters: dict[str, float],
) -> tuple[dict[str, vtk.vtkPolyData], dict]:
    """Build trajectory-aligned drill-guide sleeves and local shell collars.

    Despite the retained function name, these annular solids are drill-guide
    geometry.  They are not any of the four Step 4B robot/registration docks.
    """

    if not trajectories:
        raise ValueError("Select at least one complete trajectory for docking generation.")
    docking_parts = []
    clearance_parts = []
    reinforcement_parts = []
    channel_parts = []
    trajectory_metrics = []
    outer_radius = parameters["outerDiameterMm"] / 2.0
    inner_radius = parameters["innerDiameterMm"] / 2.0
    height = parameters["heightMm"]
    clearance = parameters["clearanceMm"]
    reinforcement_depth = parameters["reinforcementDepthMm"]
    reinforcement_height = reinforcement_depth + min(1.0, height)

    for index, trajectory in enumerate(trajectories):
        entry = _vector(trajectory.get("entryRas"), f"Trajectory {index + 1} Entry")
        target = _vector(trajectory.get("targetRas"), f"Trajectory {index + 1} Target")
        inward = target - entry
        trajectory_length = float(np.linalg.norm(inward))
        if trajectory_length <= 1e-6:
            raise ValueError(f"Trajectory {index + 1} Entry and Target coincide.")
        inward /= trajectory_length
        outward = -inward

        docking, docking_metrics = create_hollow_sleeve(
            entry,
            target,
            outer_diameter_mm=parameters["outerDiameterMm"],
            inner_diameter_mm=parameters["innerDiameterMm"],
            height_mm=height,
        )
        clearance_length = height + 2.0 * clearance + reinforcement_depth
        clearance_center = entry + outward * (
            (height + clearance - reinforcement_depth) / 2.0
        )
        clearance_solid = _closed_cylinder(
            clearance_center,
            outward,
            length_mm=clearance_length,
            radius_mm=outer_radius + clearance,
        )
        reinforcement_start = entry + inward * reinforcement_depth
        reinforcement, reinforcement_metrics = create_hollow_sleeve(
            reinforcement_start,
            reinforcement_start + inward,
            outer_diameter_mm=(
                parameters["outerDiameterMm"]
                + 2.0 * parameters["reinforcementRadialMm"]
            ),
            inner_diameter_mm=parameters["innerDiameterMm"],
            height_mm=reinforcement_height,
        )
        channel_length = height + reinforcement_depth + 4.0
        channel_center = entry + outward * ((height - reinforcement_depth) / 2.0)
        channel = _closed_cylinder(
            channel_center,
            outward,
            length_mm=channel_length,
            radius_mm=inner_radius,
        )
        docking_parts.append(docking)
        clearance_parts.append(clearance_solid)
        reinforcement_parts.append(reinforcement)
        channel_parts.append(channel)
        trajectory_metrics.append(
            {
                "index": index,
                "entryRas": tuple(float(value) for value in entry),
                "targetRas": tuple(float(value) for value in target),
                "axisRas": tuple(float(value) for value in inward),
                "trajectoryLengthMm": trajectory_length,
                "docking": docking_metrics,
                "reinforcement": reinforcement_metrics,
            }
        )

    surfaces = {
        "docking": _append_surfaces(docking_parts),
        "clearance": _append_surfaces(clearance_parts),
        "reinforcement": _append_surfaces(reinforcement_parts),
        "channels": _append_surfaces(channel_parts),
    }
    return surfaces, {
        "method": "WorldRASTrajectoryGuideSleeveAssembly",
        "mechanicalSpecification": "ProvisionalTrajectoryGuideSleeve",
        "trajectoryCount": len(trajectory_metrics),
        "trajectories": trajectory_metrics,
        "parameters": dict(parameters),
        "topology": {
            name: surface_topology(surface)
            for name, surface in surfaces.items()
        },
    }


def fuse_shell_and_docking_voxel(
    shell_world: vtk.vtkPolyData,
    docking_world: vtk.vtkPolyData,
    clearance_world: vtk.vtkPolyData,
    reinforcement_world: vtk.vtkPolyData,
    channels_world: vtk.vtkPolyData,
    *,
    sampling_spacing_mm: float,
) -> tuple[vtk.vtkPolyData, dict]:
    """Fuse shell and guide assembly in a cropped binary domain."""

    spacing = float(sampling_spacing_mm)
    if not math.isfinite(spacing) or not 0.1 <= spacing <= 2.0:
        raise ValueError("Guide fusion resolution must be 0.10–2.00 mm.")
    surfaces = {
        "shell": _triangulated_clean(shell_world),
        "docking": _triangulated_clean(docking_world),
        "clearance": _triangulated_clean(clearance_world),
        "reinforcement": _triangulated_clean(reinforcement_world),
        "channels": _triangulated_clean(channels_world),
    }
    union_bounds = [math.inf, -math.inf, math.inf, -math.inf, math.inf, -math.inf]
    for surface in surfaces.values():
        bounds = surface.GetBounds()
        for axis in range(3):
            union_bounds[2 * axis] = min(union_bounds[2 * axis], bounds[2 * axis])
            union_bounds[2 * axis + 1] = max(
                union_bounds[2 * axis + 1], bounds[2 * axis + 1]
            )
    padding = max(2.0, 4.0 * spacing)
    sample_bounds = tuple(
        value + (-padding if index % 2 == 0 else padding)
        for index, value in enumerate(union_bounds)
    )
    dimensions = tuple(
        max(
            3,
            int(
                math.ceil(
                    (sample_bounds[2 * axis + 1] - sample_bounds[2 * axis])
                    / spacing
                )
            )
            + 1,
        )
        for axis in range(3)
    )
    sample_point_count = int(np.prod(dimensions, dtype=np.int64))
    if sample_point_count > MAX_SAMPLE_POINTS:
        raise ValueError(
            "The shell/guide fusion domain requests "
            f"{sample_point_count:,} samples; increase processing resolution."
        )

    sampled_images = {}
    distance_arrays = {}
    for name, surface in surfaces.items():
        implicit = vtk.vtkImplicitPolyDataDistance()
        implicit.SetInput(surface)
        sample = vtk.vtkSampleFunction()
        sample.SetImplicitFunction(implicit)
        sample.SetModelBounds(*sample_bounds)
        sample.SetSampleDimensions(*dimensions)
        sample.ComputeNormalsOff()
        sample.Update()
        sampled_images[name] = sample.GetOutput()
        distance_arrays[name] = vtk_to_numpy(
            sample.GetOutput().GetPointData().GetScalars()
        ).reshape(dimensions[2], dimensions[1], dimensions[0])

    shell_mask = distance_arrays["shell"] <= 0.0
    docking_mask = distance_arrays["docking"] <= 0.0
    clearance_mask = distance_arrays["clearance"] <= 0.0
    reinforcement_mask = distance_arrays["reinforcement"] <= 0.0
    channel_mask = distance_arrays["channels"] <= 0.0
    final_mask = (
        (shell_mask & ~clearance_mask)
        | reinforcement_mask
        | docking_mask
    )
    final_mask &= ~channel_mask
    final_mask[0, :, :] = False
    final_mask[-1, :, :] = False
    final_mask[:, 0, :] = False
    final_mask[:, -1, :] = False
    final_mask[:, :, 0] = False
    final_mask[:, :, -1] = False
    occupied_count = int(np.count_nonzero(final_mask))
    if not occupied_count:
        raise ValueError("Shell/docking fusion produced no occupied printable volume.")

    binary_image = vtk.vtkImageData()
    binary_image.DeepCopy(sampled_images["shell"])
    binary_scalars = numpy_to_vtk(
        np.ascontiguousarray(final_mask.astype(np.uint8).ravel()),
        deep=True,
        array_type=vtk.VTK_UNSIGNED_CHAR,
    )
    binary_scalars.SetName("DENTOBOT.FinalPrintableTemplateMask")
    binary_image.GetPointData().SetScalars(binary_scalars)
    occupied_connectivity = vtk.vtkImageConnectivityFilter()
    occupied_connectivity.SetInputData(binary_image)
    occupied_connectivity.SetExtractionModeToAllRegions()
    occupied_connectivity.SetScalarRange(1.0, 1.0)
    occupied_connectivity.SetLabelModeToSizeRank()
    occupied_connectivity.Update()
    occupied_region_sizes_array = occupied_connectivity.GetExtractedRegionSizes()
    raw_occupied_region_sizes = [
        int(occupied_region_sizes_array.GetValue(index))
        for index in range(occupied_region_sizes_array.GetNumberOfValues())
    ]
    ranked_labels = vtk_to_numpy(
        occupied_connectivity.GetOutput().GetPointData().GetScalars()
    ).reshape(dimensions[2], dimensions[1], dimensions[0])
    filtered_mask, occupied_artifact_metrics = (
        filter_tiny_occupied_region_artifacts(
            ranked_labels,
            raw_occupied_region_sizes,
            binary_image.GetSpacing(),
        )
    )
    if occupied_artifact_metrics["tinyOccupiedArtifactCleanupApplied"]:
        final_mask = filtered_mask
        occupied_count = int(np.count_nonzero(final_mask))
        binary_scalars = numpy_to_vtk(
            np.ascontiguousarray(final_mask.astype(np.uint8).ravel()),
            deep=True,
            array_type=vtk.VTK_UNSIGNED_CHAR,
        )
        binary_scalars.SetName("DENTOBOT.FinalPrintableTemplateMask")
        binary_image.GetPointData().SetScalars(binary_scalars)
    occupied_volume_region_count = int(
        occupied_artifact_metrics["occupiedVolumeRegionCount"]
    )
    occupied_region_sizes = occupied_artifact_metrics[
        "occupiedVolumeRegionSizes"
    ]
    if occupied_volume_region_count != 1:
        raise RuntimeError(
            "Final shell/docking fusion contains "
            f"{occupied_volume_region_count} disconnected occupied volumes "
            f"with voxel sizes {occupied_region_sizes}."
        )
    contour = vtk.vtkFlyingEdges3D()
    contour.SetInputData(binary_image)
    contour.SetValue(0, 0.5)
    contour.ComputeNormalsOff()
    contour.ComputeGradientsOff()
    triangle = vtk.vtkTriangleFilter()
    triangle.SetInputConnection(contour.GetOutputPort())
    clean = vtk.vtkCleanPolyData()
    clean.SetInputConnection(triangle.GetOutputPort())
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputConnection(clean.GetOutputPort())
    normals.ConsistencyOn()
    normals.AutoOrientNormalsOn()
    normals.SplittingOff()
    normals.Update()
    final_surface = vtk.vtkPolyData()
    final_surface.DeepCopy(normals.GetOutput())
    topology = surface_topology(final_surface)
    if topology["boundaryOrNonManifoldEdgeCount"]:
        raise RuntimeError(
            "Final shell/docking fusion is not watertight/manifold "
            f"({topology['boundaryOrNonManifoldEdgeCount']} invalid edges)."
        )
    mass = vtk.vtkMassProperties()
    mass.SetInputData(final_surface)
    mass.Update()
    return final_surface, {
        **topology,
        "method": "TightVoxelClearanceReinforcementDockingUnion",
        "requestedSpacingMm": spacing,
        "actualSpacingMm": tuple(
            float(value) for value in binary_image.GetSpacing()
        ),
        "sampleBoundsRas": sample_bounds,
        "sampleDimensions": dimensions,
        "samplePointCount": sample_point_count,
        "occupiedSampleCount": occupied_count,
        "volumeMm3": float(mass.GetVolume()),
        "surfaceAreaMm2": float(mass.GetSurfaceArea()),
        "channelSampleCount": int(np.count_nonzero(channel_mask)),
        "dockingSampleCount": int(np.count_nonzero(docking_mask)),
        "reinforcementSampleCount": int(np.count_nonzero(reinforcement_mask)),
        **occupied_artifact_metrics,
    }
