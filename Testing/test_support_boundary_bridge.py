"""Regression for terminal coverage cutting a closed collar into two rails."""
from pathlib import Path
import sys
import types

import pytest
import vtk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "DENTOWorkflow/Resources/Python"))
# This geometry path uses VTK only; MRML helpers are not invoked.
sys.modules.setdefault("slicer", types.ModuleType("slicer"))
from DENTOTemplateGeometry import create_support_boundary_bridge, regularize_patient_contact_shell


@pytest.mark.parametrize("angle", [0, 31])
def test_terminal_coverage_closes_collar_before_final_clipping(angle):
    transform = vtk.vtkTransform()
    transform.Translate(12, -7, 4)
    transform.RotateWXYZ(angle, 1, 2, 3)
    point = transform.TransformPoint
    vector = transform.TransformVector
    boundary = [point(p) for p in [(-5, -3, 0), (5, -3, 0), (5, 3, 0), (-5, 3, 0)]]
    planes = [
        {"originRas": point((-2, 0, 0)), "inwardNormalRas": vector((1, 0, 0))},
        {"originRas": point((2, 0, 0)), "inwardNormalRas": vector((-1, 0, 0))},
    ]
    arguments = dict(fit_clearance_mm=0.3, shell_thickness_mm=1.0, sampling_spacing_mm=0.2)
    old_collar, _ = create_support_boundary_bridge(boundary, vector((0, 0, 1)), **arguments)
    collar, metrics = create_support_boundary_bridge(
        boundary, vector((0, 0, 1)), terminal_clip_planes_ras=planes, **arguments
    )
    anatomy_source = vtk.vtkCubeSource()
    anatomy_source.SetBounds(-8, 8, -6, 6, -4, -2)
    anatomy_transform = vtk.vtkTransformPolyDataFilter()
    anatomy_transform.SetTransform(transform)
    anatomy_transform.SetInputConnection(anatomy_source.GetOutputPort())
    anatomy_transform.Update()
    assert metrics["terminalClosurePlaneCount"] == 2
    for bridge, expected_regions in [(old_collar, 2), (collar, 1)]:
        shell, result = regularize_patient_contact_shell(
            bridge, anatomy_transform.GetOutput(), fit_clearance_mm=0.3,
            sampling_spacing_mm=0.2, voxel_closing_mm=0.3,
            boundary_bridge_world=bridge, terminal_clip_planes_ras=planes,
        )
        assert result["surfaceRegionCount"] == expected_regions
        assert result["boundaryOrNonManifoldEdgeCount"] == 0
        assert shell.GetNumberOfCells() > 0
