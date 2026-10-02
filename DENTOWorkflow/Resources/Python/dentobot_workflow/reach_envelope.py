"""Visual reach envelope around Step 6.3 workspace samples (VTK only).

Operator 2026-10-02: the 6.3 FK workspace is an optional visual. This module
turns the static-valid TCP samples (all solved with the case drill axis, inside
the incisor-centred task-space box) into a translucent surface, and reports
whether the task stations lie inside it. Display aid only: a station outside
the envelope is not proof the task is impossible, and inside is not proof it is
feasible; the planner, MoveIt scene and phase guard remain authoritative.
"""

from __future__ import annotations

import numpy as np
import vtk

ALPHA_SPACING_FACTOR = 2.5  # alpha radius = factor x median nearest-sample spacing


def _median_spacing(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    deltas = points[:, None, :] - points[None, :, :]
    distances = np.sqrt((deltas ** 2).sum(axis=2))
    np.fill_diagonal(distances, np.inf)
    return float(np.median(distances.min(axis=1)))


def _delaunay(points: np.ndarray, alpha: float) -> vtk.vtkUnstructuredGrid:
    vtk_points = vtk.vtkPoints()
    for point in points:
        vtk_points.InsertNextPoint(*(float(v) for v in point))
    cloud = vtk.vtkPolyData()
    cloud.SetPoints(vtk_points)
    delaunay = vtk.vtkDelaunay3D()
    delaunay.SetInputData(cloud)
    delaunay.SetAlpha(float(alpha))
    delaunay.AlphaTrisOff()
    delaunay.AlphaLinesOff()
    delaunay.AlphaVertsOff()
    delaunay.Update()
    grid = vtk.vtkUnstructuredGrid()
    grid.DeepCopy(delaunay.GetOutput())
    return grid


def envelope(points_mm) -> tuple[vtk.vtkPolyData, vtk.vtkUnstructuredGrid, str]:
    """(surface, tetrahedral volume, method). Alpha shape; convex hull fallback."""
    points = np.unique(np.asarray(points_mm, dtype=float).reshape(-1, 3), axis=0)
    if len(points) < 4:
        return vtk.vtkPolyData(), vtk.vtkUnstructuredGrid(), "too_few_samples"
    spacing = _median_spacing(points)
    grid, method = None, ""
    if spacing > 0.0:
        grid = _delaunay(points, ALPHA_SPACING_FACTOR * spacing)
        method = f"alpha_shape(alpha={ALPHA_SPACING_FACTOR * spacing:.1f} mm)"
    if grid is None or grid.GetNumberOfCells() == 0:
        grid = _delaunay(points, 0.0)
        method = "convex_hull"
    surface_filter = vtk.vtkDataSetSurfaceFilter()
    surface_filter.SetInputData(grid)
    surface_filter.Update()
    surface = vtk.vtkPolyData()
    surface.DeepCopy(surface_filter.GetOutput())
    return surface, grid, method


def points_inside(grid: vtk.vtkUnstructuredGrid, points_mm) -> list[bool]:
    """Whether each point lies in a tetrahedron of the envelope volume."""
    if grid.GetNumberOfCells() == 0:
        return [False for _ in points_mm]
    locator = vtk.vtkCellLocator()
    locator.SetDataSet(grid)
    locator.BuildLocator()
    return [locator.FindCell([float(v) for v in point]) >= 0 for point in points_mm]


def nearest_sample_mm(samples_mm, point_mm) -> float:
    samples = np.asarray(samples_mm, dtype=float).reshape(-1, 3)
    if not len(samples):
        return float("inf")
    return float(np.min(np.linalg.norm(samples - np.asarray(point_mm, float), axis=1)))
