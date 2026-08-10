"""Trajectory guide assembly and robust printable-template fusion.

The labelmap-style Boolean sequence adapts the geometric strategy demonstrated
by SlicerFSP SurgicalGuide ``RingsAndBooleans``: reserve docking clearance in
the shell, add a load-spreading reinforcement collar, unite the docking solid,
and finally restore every trajectory channel.  DENTOBOT keeps its own annular
world-RAS guide primitive and explicit MRML provenance; this module does not
import SlicerFSP or depend on display names/global editor state.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

from DENTOTemplateGeometry import create_hollow_sleeve, surface_topology


MAX_SAMPLE_POINTS = 48_000_000


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
    """Build provisional annular docking, clearance, reinforcement, and channels."""

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
        "method": "WorldRASParameterizedAnnularDockingAssembly",
        "mechanicalSpecification": "ProvisionalDevelopmentGeometry",
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
    }
