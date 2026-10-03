# Which Find Reachable Base path-preflight obstacle makes vtkOBBTree log
# "vtkMath::Jacobi: Error extracting eigenfunctions" (r22: 14 warnings). Read only.
import math

import slicer
import vtk

model = slicer.app.errorLogModel()


def _jacobi_entries():
    return sum("Jacobi" in str(model.logEntryDescription(row))
               for row in range(int(model.logEntryCount())))


obstacles = logic.step6PathPreflightObstaclesWorld(parameter_node)
meshes = []
for name, polydata in obstacles:
    quality = vtk.vtkMeshQuality()
    quality.SetInputData(polydata)
    quality.SetTriangleQualityMeasureToArea()
    quality.Update()
    areas = quality.GetOutput().GetCellData().GetArray("Quality")
    zero_area = sum(1 for i in range(areas.GetNumberOfTuples()) if areas.GetValue(i) <= 1e-12) if areas else -1
    points = polydata.GetPoints()
    non_finite = sum(1 for i in range(polydata.GetNumberOfPoints())
                     if not all(math.isfinite(v) for v in points.GetPoint(i))) if points else 0
    before = _jacobi_entries()
    tree = vtk.vtkOBBTree()
    tree.SetDataSet(polydata)
    tree.BuildLocator()
    _process_events(0.05)
    meshes.append({
        "name": str(name),
        "points": int(polydata.GetNumberOfPoints()),
        "cells": int(polydata.GetNumberOfCells()),
        "non_polygon_cells": int(polydata.GetNumberOfCells() - polydata.GetNumberOfPolys()),
        "zero_area_triangles": int(zero_area),
        "non_finite_points": int(non_finite),
        "jacobi_warnings": int(_jacobi_entries() - before),
    })
result = {
    "obstacles": len(meshes),
    "jacobi_total": sum(m["jacobi_warnings"] for m in meshes),
    "meshes": meshes,
}
