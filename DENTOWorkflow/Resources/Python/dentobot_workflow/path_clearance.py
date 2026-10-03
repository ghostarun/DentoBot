"""Mesh-level straight-path clearance preflight for Base candidates (VTK only).

Simulation planning aid, not collision authority: MoveIt's synchronized
PlanningScene and the native guard remain authoritative. This module sweeps the
tool meshes (burr, spindle housing) along the straight joint-space path
Home -> PreEntry for a candidate Base and tests them against case obstacle
surfaces (template, teeth, jaws) with ``vtkCollisionDetectionFilter``. It lets
the Base search prefer candidates whose direct approach does not drive the
tool through the guide, which the P1 planner otherwise has to detour around.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import vtk

TOOL_LINKS = ("burr", "pneumatic_spindle-Copy")


def _vtk_matrix(matrix: np.ndarray) -> vtk.vtkMatrix4x4:
    out = vtk.vtkMatrix4x4()
    for row in range(4):
        for column in range(4):
            out.SetElement(row, column, float(matrix[row, column]))
    return out


def load_stl(path) -> vtk.vtkPolyData:
    reader = vtk.vtkSTLReader()
    reader.SetFileName(str(path))
    reader.Update()
    triangles = vtk.vtkTriangleFilter()
    triangles.SetInputConnection(reader.GetOutputPort())
    triangles.Update()
    out = vtk.vtkPolyData()
    out.DeepCopy(triangles.GetOutput())
    return out


def drop_zero_area_triangles(polydata: vtk.vtkPolyData, min_area_mm2: float = 1e-12) -> vtk.vtkPolyData:
    """Remove zero-area triangles (no surface) before building collision trees.

    vtkOBBTree divides by each node's summed triangle area; a node of only
    zero-area triangles gets NaN axes, logs "vtkMath::Jacobi: Error extracting
    eigenfunctions" and is not tested reliably. Segment closed surfaces carry
    4-498 such triangles each (r23 obstacle probe).
    """
    quality = vtk.vtkMeshQuality()
    quality.SetInputData(polydata)
    quality.SetTriangleQualityMeasureToArea()
    quality.Update()
    areas = quality.GetOutput().GetCellData().GetArray("Quality")
    if areas is None or min(areas.GetRange()) > min_area_mm2:
        return polydata
    threshold = vtk.vtkThreshold()
    threshold.SetInputConnection(quality.GetOutputPort())
    threshold.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_CELLS, "Quality")
    threshold.SetUpperThreshold(min_area_mm2)
    threshold.SetThresholdFunction(vtk.vtkThreshold.THRESHOLD_UPPER)
    surface = vtk.vtkGeometryFilter()
    surface.SetInputConnection(threshold.GetOutputPort())
    surface.Update()
    out = vtk.vtkPolyData()
    out.DeepCopy(surface.GetOutput())
    out.GetCellData().RemoveArray("Quality")
    return out


class ToolMeshSweep:
    """Tool meshes posed by robot FK, tested against fixed world obstacles."""

    def __init__(self, urdf_path, package_root, obstacles: list[tuple[str, vtk.vtkPolyData]],
                 tool_links: tuple[str, ...] = TOOL_LINKS):
        from DENTORobotPlacement import robot_link_mesh_poses_mm

        self._poses = robot_link_mesh_poses_mm
        self._urdf = Path(urdf_path)
        self._package = Path(package_root)
        self._tool_links = tuple(tool_links)
        reference = {pose.link_name: pose for pose in self._poses(self._urdf, self._package, None)}
        missing = [name for name in self._tool_links if name not in reference]
        if missing:
            raise ValueError("Robot tool meshes are missing: " + ", ".join(missing))
        self._tool_meshes = {name: load_stl(reference[name].mesh_path) for name in self._tool_links}
        valid = [(name, drop_zero_area_triangles(mesh)) for name, mesh in obstacles
                 if mesh is not None and mesh.GetNumberOfPoints() > 0]
        self._obstacle_names = [name for name, _mesh in valid]
        # Fast path: one filter per tool against all obstacles merged; names are
        # resolved per obstacle only after a merged hit.
        merged = vtk.vtkAppendPolyData()
        for _name, mesh in valid:
            merged.AddInputData(mesh)
        merged.Update()
        self._merged = vtk.vtkPolyData()
        self._merged.DeepCopy(merged.GetOutput())
        self._merged_filters = {tool: self._filter(mesh, self._merged)
                                for tool, mesh in self._tool_meshes.items()} if valid else {}
        self._named_filters = {tool: [(name, self._filter(mesh, obstacle)) for name, obstacle in valid]
                               for tool, mesh in self._tool_meshes.items()}

    @staticmethod
    def _filter(tool_mesh: vtk.vtkPolyData, obstacle: vtk.vtkPolyData):
        collision = vtk.vtkCollisionDetectionFilter()
        collision.SetInputData(0, tool_mesh)
        collision.SetInputData(1, obstacle)
        collision.SetMatrix(1, vtk.vtkMatrix4x4())
        collision.SetCollisionModeToFirstContact()
        collision.SetBoxTolerance(0.0)
        collision.SetCellTolerance(0.0)
        return collision

    def contacts(self, base_world_mm: np.ndarray, joints_si: dict[str, float]) -> list[tuple[str, str]]:
        poses = {pose.link_name: pose for pose in self._poses(self._urdf, self._package, joints_si)}
        hits = []
        for tool_name, merged_filter in self._merged_filters.items():
            matrix = _vtk_matrix(np.asarray(base_world_mm, float) @ poses[tool_name].matrix_base_from_mesh_mm)
            merged_filter.SetMatrix(0, matrix)
            merged_filter.Update()
            if merged_filter.GetNumberOfContacts() == 0:
                continue
            for obstacle_name, collision in self._named_filters[tool_name]:
                collision.SetMatrix(0, matrix)
                collision.Update()
                if collision.GetNumberOfContacts() > 0:
                    hits.append((tool_name, obstacle_name))
        return hits

    def straight_path(self, base_world_mm: np.ndarray, joint_names: list[str],
                      start_q: list[float], goal_q: list[float],
                      max_revolute_step_rad: float = 0.02,
                      max_prismatic_step_m: float = 0.0005) -> dict:
        deltas = []
        for name, start, goal in zip(joint_names, start_q, goal_q):
            delta = float(goal) - float(start)
            if name.endswith("Revolute-5"):
                delta = math.atan2(math.sin(delta), math.cos(delta))
            deltas.append(delta)
        steps = 1
        for name, delta in zip(joint_names, deltas):
            limit = max_prismatic_step_m if "Slider" in name else max_revolute_step_rad
            steps = max(steps, int(math.ceil(abs(delta) / limit)))
        for index in range(steps + 1):
            fraction = index / steps
            joints = {name: float(s) + d * fraction for name, s, d in zip(joint_names, start_q, deltas)}
            hits = self.contacts(base_world_mm, joints)
            if hits:
                return {"clear": False, "first_contact_fraction": fraction,
                        "samples_checked": index + 1, "steps": steps,
                        "contacts": [f"{a}<->{b}" for a, b in hits]}
        return {"clear": True, "samples_checked": steps + 1, "steps": steps, "contacts": []}
