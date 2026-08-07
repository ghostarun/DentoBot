"""Model-independent research template geometry for DENTO Workflow.

The routines in this file operate on VTK/MRML geometry only.  They do not run
trained models and they do not encode clinical or manufacturing approval.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import slicer
import vtk
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy


MAX_SAMPLE_POINTS = 12_000_000


def _finite_vector(values, expected_length: int, name: str) -> np.ndarray:
    vector = np.asarray(values, dtype=float)
    if vector.shape != (expected_length,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must contain {expected_length} finite values.")
    return vector


def _triangulated_clean_surface(poly_data: vtk.vtkPolyData) -> vtk.vtkPolyData:
    if not poly_data or not poly_data.GetNumberOfPoints():
        raise ValueError("Input anatomy contains no surface points.")

    triangle_filter = vtk.vtkTriangleFilter()
    triangle_filter.SetInputData(poly_data)
    triangle_filter.PassLinesOff()
    triangle_filter.PassVertsOff()

    clean_filter = vtk.vtkCleanPolyData()
    clean_filter.SetInputConnection(triangle_filter.GetOutputPort())

    normals_filter = vtk.vtkPolyDataNormals()
    normals_filter.SetInputConnection(clean_filter.GetOutputPort())
    normals_filter.ConsistencyOn()
    normals_filter.AutoOrientNormalsOn()
    normals_filter.SplittingOff()
    normals_filter.ComputePointNormalsOn()
    normals_filter.ComputeCellNormalsOff()
    normals_filter.Update()

    output = vtk.vtkPolyData()
    output.DeepCopy(normals_filter.GetOutput())
    if not output.GetNumberOfCells():
        raise ValueError("Input anatomy contains no usable surface cells.")
    return output


def model_polydata_in_world(model_node) -> vtk.vtkPolyData:
    """Return a deep world-RAS copy without modifying the source MRML model."""

    if not model_node or not model_node.IsA("vtkMRMLModelNode"):
        raise ValueError("Select a valid Step 5A support-anatomy model.")
    source = model_node.GetPolyData()
    if not source or not source.GetNumberOfPoints() or not source.GetNumberOfCells():
        raise ValueError("The Step 5A support-anatomy model has no usable geometry.")

    source_copy = vtk.vtkPolyData()
    source_copy.DeepCopy(source)
    parent_transform = model_node.GetParentTransformNode()
    if not parent_transform:
        return _triangulated_clean_surface(source_copy)

    world_transform = vtk.vtkGeneralTransform()
    slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(
        parent_transform,
        None,
        world_transform,
    )
    transform_filter = vtk.vtkTransformPolyDataFilter()
    transform_filter.SetInputData(source_copy)
    transform_filter.SetTransform(world_transform)
    transform_filter.Update()
    return _triangulated_clean_surface(transform_filter.GetOutput())


def surface_topology(poly_data: vtk.vtkPolyData) -> dict[str, int]:
    """Return compact mesh topology metrics used as research validity checks."""

    triangle_filter = vtk.vtkTriangleFilter()
    triangle_filter.SetInputData(poly_data)
    triangle_filter.Update()

    feature_edges = vtk.vtkFeatureEdges()
    feature_edges.SetInputConnection(triangle_filter.GetOutputPort())
    feature_edges.BoundaryEdgesOn()
    feature_edges.NonManifoldEdgesOn()
    feature_edges.FeatureEdgesOff()
    feature_edges.ManifoldEdgesOff()
    feature_edges.Update()

    connectivity = vtk.vtkPolyDataConnectivityFilter()
    connectivity.SetInputConnection(triangle_filter.GetOutputPort())
    connectivity.SetExtractionModeToAllRegions()
    connectivity.ColorRegionsOn()
    connectivity.Update()

    return {
        "pointCount": int(triangle_filter.GetOutput().GetNumberOfPoints()),
        "triangleCount": int(triangle_filter.GetOutput().GetNumberOfCells()),
        "boundaryOrNonManifoldEdgeCount": int(
            feature_edges.GetOutput().GetNumberOfCells()
        ),
        "surfaceRegionCount": int(connectivity.GetNumberOfExtractedRegions()),
    }


def _validate_template_parameters(
    clearance_mm: float,
    thickness_mm: float,
    sampling_spacing_mm: float,
    channel_diameter_mm: float,
    sleeve_outer_diameter_mm: float,
    sleeve_inner_diameter_mm: float,
    sleeve_height_mm: float,
) -> dict[str, float]:
    values = {
        "clearanceMm": float(clearance_mm),
        "thicknessMm": float(thickness_mm),
        "samplingSpacingMm": float(sampling_spacing_mm),
        "channelDiameterMm": float(channel_diameter_mm),
        "sleeveOuterDiameterMm": float(sleeve_outer_diameter_mm),
        "sleeveInnerDiameterMm": float(sleeve_inner_diameter_mm),
        "sleeveHeightMm": float(sleeve_height_mm),
    }
    if any(not math.isfinite(value) for value in values.values()):
        raise ValueError("All Step 5B dimensions must be finite.")
    if values["clearanceMm"] < 0.0:
        raise ValueError("Shell clearance must be zero or greater.")
    for key in (
        "thicknessMm",
        "samplingSpacingMm",
        "channelDiameterMm",
        "sleeveOuterDiameterMm",
        "sleeveInnerDiameterMm",
        "sleeveHeightMm",
    ):
        if values[key] <= 0.0:
            raise ValueError(f"{key} must be greater than zero.")
    if values["sleeveInnerDiameterMm"] >= values["sleeveOuterDiameterMm"]:
        raise ValueError("Sleeve inner diameter must be smaller than its outer diameter.")
    if values["channelDiameterMm"] < values["sleeveInnerDiameterMm"]:
        raise ValueError(
            "The shell channel diameter must be at least the sleeve inner diameter."
        )
    return values


def _trajectory_axis(entry_ras, target_ras) -> tuple[np.ndarray, np.ndarray, float]:
    entry = _finite_vector(entry_ras, 3, "Trajectory Entry")
    target = _finite_vector(target_ras, 3, "Trajectory Target")
    direction = target - entry
    length = float(np.linalg.norm(direction))
    if length <= 1e-6:
        raise ValueError("The Entry-to-Target trajectory must have non-zero length.")
    return entry, direction / length, length


def create_research_shell(
    anatomy_world: vtk.vtkPolyData,
    roi_bounds_ras,
    entry_ras,
    target_ras,
    *,
    clearance_mm: float,
    thickness_mm: float,
    sampling_spacing_mm: float,
    channel_diameter_mm: float,
    sleeve_outer_diameter_mm: float,
    sleeve_inner_diameter_mm: float,
    sleeve_height_mm: float,
) -> tuple[vtk.vtkPolyData, dict]:
    """Create an exterior distance-band shell, ROI trim, and drill channel."""

    parameters = _validate_template_parameters(
        clearance_mm,
        thickness_mm,
        sampling_spacing_mm,
        channel_diameter_mm,
        sleeve_outer_diameter_mm,
        sleeve_inner_diameter_mm,
        sleeve_height_mm,
    )
    bounds = _finite_vector(roi_bounds_ras, 6, "Shell ROI bounds")
    if any(bounds[2 * axis] >= bounds[2 * axis + 1] for axis in range(3)):
        raise ValueError("The shell ROI must have positive size in every axis.")
    entry, axis, trajectory_length = _trajectory_axis(entry_ras, target_ras)
    anatomy = _triangulated_clean_surface(anatomy_world)

    requested_spacing = parameters["samplingSpacingMm"]
    expanded_bounds = []
    for axis_index in range(3):
        expanded_bounds.extend(
            (
                float(bounds[2 * axis_index] - requested_spacing),
                float(bounds[2 * axis_index + 1] + requested_spacing),
            )
        )
    dimensions = tuple(
        max(
            3,
            int(
                math.ceil(
                    (expanded_bounds[2 * axis_index + 1]
                     - expanded_bounds[2 * axis_index])
                    / requested_spacing
                )
            )
            + 1,
        )
        for axis_index in range(3)
    )
    sample_point_count = int(np.prod(dimensions, dtype=np.int64))
    if sample_point_count > MAX_SAMPLE_POINTS:
        raise ValueError(
            "The ROI and sampling spacing request "
            f"{sample_point_count:,} samples; reduce the ROI or increase spacing "
            f"to stay below {MAX_SAMPLE_POINTS:,}."
        )

    implicit_distance = vtk.vtkImplicitPolyDataDistance()
    implicit_distance.SetInput(anatomy)
    sample = vtk.vtkSampleFunction()
    sample.SetImplicitFunction(implicit_distance)
    sample.SetModelBounds(*expanded_bounds)
    sample.SetSampleDimensions(*dimensions)
    sample.ComputeNormalsOff()
    sample.Update()

    sampled_image = sample.GetOutput()
    actual_spacing = tuple(float(value) for value in sampled_image.GetSpacing())
    origin = tuple(float(value) for value in sampled_image.GetOrigin())
    distances = vtk_to_numpy(sampled_image.GetPointData().GetScalars()).reshape(
        dimensions[2], dimensions[1], dimensions[0]
    )

    x = origin[0] + np.arange(dimensions[0], dtype=float) * actual_spacing[0]
    y = origin[1] + np.arange(dimensions[1], dtype=float) * actual_spacing[1]
    z = origin[2] + np.arange(dimensions[2], dtype=float) * actual_spacing[2]
    inside_roi = (
        (x[np.newaxis, np.newaxis, :] >= bounds[0])
        & (x[np.newaxis, np.newaxis, :] <= bounds[1])
        & (y[np.newaxis, :, np.newaxis] >= bounds[2])
        & (y[np.newaxis, :, np.newaxis] <= bounds[3])
        & (z[:, np.newaxis, np.newaxis] >= bounds[4])
        & (z[:, np.newaxis, np.newaxis] <= bounds[5])
    )
    shell_mask = (
        (distances >= parameters["clearanceMm"])
        & (
            distances
            <= parameters["clearanceMm"] + parameters["thicknessMm"]
        )
        & inside_roi
    )

    dx = x[np.newaxis, np.newaxis, :] - entry[0]
    dy = y[np.newaxis, :, np.newaxis] - entry[1]
    dz = z[:, np.newaxis, np.newaxis] - entry[2]
    projection = dx * axis[0] + dy * axis[1] + dz * axis[2]
    radial_squared = np.maximum(
        0.0,
        dx * dx + dy * dy + dz * dz - projection * projection,
    )
    channel_radius = parameters["channelDiameterMm"] / 2.0
    channel_mask = (
        (radial_squared <= channel_radius * channel_radius)
        & (projection >= -parameters["sleeveHeightMm"] - requested_spacing)
        & (projection <= trajectory_length + requested_spacing)
    )
    shell_mask[channel_mask] = False
    occupied_sample_count = int(np.count_nonzero(shell_mask))
    if not occupied_sample_count:
        raise ValueError(
            "The current ROI and shell dimensions produce no template geometry."
        )

    binary_image = vtk.vtkImageData()
    binary_image.DeepCopy(sampled_image)
    binary_scalars = numpy_to_vtk(
        np.ascontiguousarray(shell_mask.astype(np.uint8).ravel()),
        deep=True,
        array_type=vtk.VTK_UNSIGNED_CHAR,
    )
    binary_scalars.SetName("DENTOBOT.ResearchShellMask")
    binary_image.GetPointData().SetScalars(binary_scalars)

    contour = vtk.vtkFlyingEdges3D()
    contour.SetInputData(binary_image)
    contour.SetValue(0, 0.5)
    contour.ComputeNormalsOff()
    contour.ComputeGradientsOff()

    triangle_filter = vtk.vtkTriangleFilter()
    triangle_filter.SetInputConnection(contour.GetOutputPort())
    clean_filter = vtk.vtkCleanPolyData()
    clean_filter.SetInputConnection(triangle_filter.GetOutputPort())
    clean_filter.Update()

    shell = vtk.vtkPolyData()
    shell.DeepCopy(clean_filter.GetOutput())
    if not shell.GetNumberOfPoints() or not shell.GetNumberOfCells():
        raise RuntimeError("Slicer could not extract a shell surface from the mask.")
    topology = surface_topology(shell)
    if topology["boundaryOrNonManifoldEdgeCount"]:
        raise RuntimeError(
            "The generated shell is not watertight/manifold "
            f"({topology['boundaryOrNonManifoldEdgeCount']} invalid edges)."
        )
    return shell, {
        **parameters,
        **topology,
        "sampleDimensions": dimensions,
        "samplePointCount": sample_point_count,
        "occupiedSampleCount": occupied_sample_count,
        "actualSpacingMm": actual_spacing,
        "roiBoundsRas": tuple(float(value) for value in bounds),
        "trajectoryLengthMm": trajectory_length,
    }


def create_hollow_sleeve(
    entry_ras,
    target_ras,
    *,
    outer_diameter_mm: float,
    inner_diameter_mm: float,
    height_mm: float,
    resolution: int = 96,
) -> tuple[vtk.vtkPolyData, dict]:
    """Create a closed annular sleeve extending outward from Entry."""

    outer_diameter = float(outer_diameter_mm)
    inner_diameter = float(inner_diameter_mm)
    height = float(height_mm)
    if any(
        not math.isfinite(value)
        for value in (outer_diameter, inner_diameter, height)
    ):
        raise ValueError("Sleeve dimensions must be finite.")
    if inner_diameter <= 0.0 or outer_diameter <= inner_diameter or height <= 0.0:
        raise ValueError(
            "Sleeve dimensions require 0 < inner diameter < outer diameter and positive height."
        )
    if resolution < 12 or resolution > 720:
        raise ValueError("Sleeve resolution must be between 12 and 720.")

    entry, inward_axis, trajectory_length = _trajectory_axis(entry_ras, target_ras)
    outward_axis = -inward_axis
    reference = np.array((0.0, 0.0, 1.0), dtype=float)
    if abs(float(np.dot(reference, outward_axis))) > 0.9:
        reference = np.array((0.0, 1.0, 0.0), dtype=float)
    basis_u = np.cross(outward_axis, reference)
    basis_u /= np.linalg.norm(basis_u)
    basis_v = np.cross(outward_axis, basis_u)

    inner_radius = inner_diameter / 2.0
    outer_radius = outer_diameter / 2.0
    lower_center = entry
    upper_center = entry + outward_axis * height
    points = vtk.vtkPoints()
    rings = []
    for center, radius in (
        (lower_center, outer_radius),
        (upper_center, outer_radius),
        (lower_center, inner_radius),
        (upper_center, inner_radius),
    ):
        ring = []
        for index in range(resolution):
            angle = 2.0 * math.pi * index / resolution
            point = center + radius * (
                math.cos(angle) * basis_u + math.sin(angle) * basis_v
            )
            ring.append(points.InsertNextPoint(*point))
        rings.append(ring)

    outer_lower, outer_upper, inner_lower, inner_upper = rings
    triangles = vtk.vtkCellArray()

    def add_triangle(a: int, b: int, c: int) -> None:
        triangle = vtk.vtkTriangle()
        triangle.GetPointIds().SetId(0, a)
        triangle.GetPointIds().SetId(1, b)
        triangle.GetPointIds().SetId(2, c)
        triangles.InsertNextCell(triangle)

    for index in range(resolution):
        next_index = (index + 1) % resolution
        add_triangle(outer_lower[index], outer_lower[next_index], outer_upper[next_index])
        add_triangle(outer_lower[index], outer_upper[next_index], outer_upper[index])
        add_triangle(inner_lower[index], inner_upper[next_index], inner_lower[next_index])
        add_triangle(inner_lower[index], inner_upper[index], inner_upper[next_index])
        add_triangle(outer_lower[index], inner_lower[next_index], outer_lower[next_index])
        add_triangle(outer_lower[index], inner_lower[index], inner_lower[next_index])
        add_triangle(outer_upper[index], outer_upper[next_index], inner_upper[next_index])
        add_triangle(outer_upper[index], inner_upper[next_index], inner_upper[index])

    sleeve = vtk.vtkPolyData()
    sleeve.SetPoints(points)
    sleeve.SetPolys(triangles)
    sleeve = _triangulated_clean_surface(sleeve)
    topology = surface_topology(sleeve)
    if topology["boundaryOrNonManifoldEdgeCount"]:
        raise RuntimeError(
            "The generated sleeve is not watertight/manifold "
            f"({topology['boundaryOrNonManifoldEdgeCount']} invalid edges)."
        )
    return sleeve, {
        **topology,
        "outerDiameterMm": outer_diameter,
        "innerDiameterMm": inner_diameter,
        "heightMm": height,
        "resolution": int(resolution),
        "trajectoryLengthMm": trajectory_length,
        "entryRas": tuple(float(value) for value in entry),
        "outwardAxisRas": tuple(float(value) for value in outward_axis),
    }


def write_stl_atomic(poly_data: vtk.vtkPolyData, output_path: str | Path) -> Path:
    """Write one binary STL via a same-directory temporary file."""

    topology = surface_topology(poly_data)
    if topology["boundaryOrNonManifoldEdgeCount"]:
        raise ValueError("Only a watertight/manifold model can be exported to STL.")
    path = Path(output_path)
    if path.suffix.lower() != ".stl":
        raise ValueError("The STL output filename must end in .stl.")
    if not path.parent.is_dir():
        raise ValueError("The selected STL output directory does not exist.")

    temporary_path = path.with_name(f".{path.name}.dentobot-partial")
    writer = vtk.vtkSTLWriter()
    writer.SetFileName(str(temporary_path))
    writer.SetInputData(poly_data)
    writer.SetFileTypeToBinary()
    if writer.Write() != 1 or not temporary_path.is_file():
        if temporary_path.exists():
            temporary_path.unlink()
        raise RuntimeError(f"VTK could not write {path.name}.")
    os.replace(temporary_path, path)
    return path
