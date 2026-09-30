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


def test_patient_shell_fallback_progress_skips_hollow_candidate():
    candidate = vtk.vtkPlaneSource()
    candidate.SetOrigin(-3, -3, 0)
    candidate.SetPoint1(3, -3, 0)
    candidate.SetPoint2(-3, 3, 0)
    candidate.Update()

    anatomy_source = vtk.vtkCubeSource()
    anatomy_source.SetBounds(-1, 1, -1, 1, 2, 2.5)
    anatomy_source.Update()

    progress = []
    shell, metrics = regularize_patient_contact_shell(
        candidate.GetOutput(),
        anatomy_source.GetOutput(),
        fit_clearance_mm=0.0,
        sampling_spacing_mm=0.5,
        fitting_surface_world=candidate.GetOutput(),
        shell_thickness_mm=1.0,
        progress=lambda phase, done, total: progress.append(
            (phase, done, total)
        ),
    )

    assert shell.GetNumberOfCells() > 0
    assert metrics["surfaceRegionCount"] == 1
    assert metrics["boundaryOrNonManifoldEdgeCount"] == 0
    assert progress == [
        ("Patient-shell distance field: anatomy clearance", 1, 2),
        ("Patient-shell distance field: fitting surface", 2, 2),
    ]


def test_saved_fixture_shell_mode_is_explicit_and_preserves_boundary(monkeypatch):
    import ast
    import os
    source = Path(__file__).with_name("run_dentobot_pulp_shell_smoke.py")
    helper = next(n for n in ast.parse(source.read_text()).body
                  if isinstance(n, ast.FunctionDef) and n.name == "_shell_only_requested")
    namespace = {"os": os}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(source), "exec"), namespace)
    requested = namespace["_shell_only_requested"]
    for name in ("DENTOBOT_TEST_SHELL_ONLY", "DENTOBOT_TEST_AUTO_BOUNDARY", "DENTOBOT_TEST_STEP4A_ONLY"):
        monkeypatch.delenv(name, raising=False)
    assert requested() is False
    monkeypatch.setenv("DENTOBOT_TEST_SHELL_ONLY", "yes")
    with pytest.raises(ValueError, match="exactly"):
        requested()
    monkeypatch.setenv("DENTOBOT_TEST_SHELL_ONLY", "1")
    assert requested() is True
    for name in ("DENTOBOT_TEST_AUTO_BOUNDARY", "DENTOBOT_TEST_STEP4A_ONLY"):
        monkeypatch.setenv(name, "1")
        with pytest.raises(ValueError, match="saved boundary"):
            requested()
        monkeypatch.delenv(name)


def test_shell_capture_resets_clipping_after_each_camera_move(tmp_path):
    import ast
    from types import SimpleNamespace
    source = Path(__file__).with_name("run_dentobot_pulp_shell_smoke.py")
    helper = next(n for n in ast.parse(source.read_text()).body
                  if isinstance(n, ast.FunctionDef) and n.name == "_capture_final_dock_screenshots")
    cube = vtk.vtkCubeSource()
    cube.Update()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(cube.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    renderer = vtk.vtkRenderer()
    renderer.AddActor(actor)
    window = vtk.vtkRenderWindow()
    window.AddRenderer(renderer)
    camera = renderer.GetActiveCamera()
    camera.SetClippingRange(100, 200)
    captures = []
    def save(path):
        captures.append((camera.GetClippingRange(), camera.GetDistance()))
        return True
    noop = lambda *args: None
    display = SimpleNamespace(**{name: noop for name in (
        "SetVisibility", "SetColor", "SetOpacity", "SetEdgeVisibility", "SetEdgeColor")})
    view = SimpleNamespace(mrmlViewNode=lambda: SimpleNamespace(SetAxisLabelsVisible=noop),
        cameraNode=lambda: SimpleNamespace(GetCamera=lambda: camera), renderWindow=lambda: window,
        forceRender=noop, grab=lambda: SimpleNamespace(save=save))
    layout = SimpleNamespace(setLayout=noop, threeDWidget=lambda i: SimpleNamespace(threeDView=lambda: view))
    slicer_stub = SimpleNamespace(app=SimpleNamespace(layoutManager=lambda: layout),
        util=SimpleNamespace(getNodesByClass=lambda cls: [display], forceRenderAllViews=noop),
        vtkMRMLLayoutNode=SimpleNamespace(SlicerLayoutOneUp3DView=0))
    namespace = {"Path": Path, "slicer": slicer_stub}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(source), "exec"), namespace)
    final = SimpleNamespace(GetDisplayNode=lambda: display, GetPolyData=cube.GetOutput)
    details = {"assembly": {"targetDocking": {"docks": [
        {"topFaceCenterRas": [0, 0, 0], "axisRas": [0, 0, 1], "label": "+X"}]}}}
    assert len(namespace[helper.name](final, details, str(tmp_path))) == 2
    assert all(near < distance < far for (near, far), distance in captures)
