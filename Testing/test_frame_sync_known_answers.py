"""Proxy transform path and prepared Slicer regression source contract."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import vtk

sys.path.insert(0,str(Path(__file__).resolve().parent))
import step6_frame_sync_known_answers as known


def test_production_proxy_mismatch_is_detected_independently():
    mesh=known.audit._mesh_polydata(np.array([[0,0,0],[1,0,0],[0,1,0.]]),[[0,1,2]])
    class Base:
        def GetMatrixTransformToWorld(self,m):m.Identity();m.SetElement(0,3,10)
    model=SimpleNamespace(GetPolyData=lambda:mesh,GetParentTransformNode=lambda:None)
    parameter=SimpleNamespace(robotBaseTransform=Base(),finalPrintableTemplateModel=model,
        targetDockingAssemblyModel=model,patientContactShellModel=model)
    def proxy(world,base):
        transform=vtk.vtkTransform();transform.Translate(-10,0,0)
        f=vtk.vtkTransformPolyDataFilter();f.SetInputData(world);f.SetTransform(transform);f.Update()
        return f.GetOutput()
    logic=SimpleNamespace(_polydataWorldToRobotBase=proxy)
    assert all(r['status']=='PASS' for r in known.source_to_base_rows(logic,parameter))
    logic._polydataWorldToRobotBase=lambda world,base:world
    assert all(r['status']=='FAIL' for r in known.source_to_base_rows(logic,parameter))


def test_runtime_regression_requires_fixture_and_includes_each_known_edit():
    source=(Path(__file__).with_name('step6_frame_sync_known_answers.py')).read_text()
    for label in ('opening_plus_4_mm','base_plus_10_mm_u','base_yaw_plus_5_deg','branch_switch','save_reopen'):
        assert label in source
    assert 'canonicalTrajectoryGeometry' in source
    assert 'activateDentoCasePreparedBranch' in source
    assert '_createCaseBundle' in source and 'restore_offline_scene' in source
    assert 'syncStep6MoveItPlanningScene' not in source


def test_restore_barrier_covers_load_hydration_and_releases_on_error(monkeypatch):
    import pytest
    events = []
    parameter = object()
    widget = SimpleNamespace(_parameterNode=parameter)
    widget._beginCaseBundleRestore = lambda: events.append("begin") or 1
    widget._endCaseBundleRestore = lambda generation: events.append(("end", generation))
    widget._bindAndValidateRestoredCase = lambda workflow: events.append("bind")
    widget.setParameterNode = lambda node: events.append("set_parameter")
    widget._validateHydratedCaseBundle = lambda workflow: events.append("audit")
    widget.logic = SimpleNamespace(
        getParameterNode=lambda: parameter,
        hydrateDentoCaseStateAfterLoad=lambda node, schema: events.append("hydrate"),
    )
    fake = SimpleNamespace(
        util=SimpleNamespace(getModuleWidget=lambda name: widget,
                             loadScene=lambda path, options: events.append("load") or True),
        app=SimpleNamespace(processEvents=lambda: events.append("events")),
    )
    monkeypatch.setitem(sys.modules, "slicer", fake)
    assert known.restore_offline_scene("fixture.mrb", {}, "3.0") == (widget.logic, parameter)
    assert events == ["begin", "load", "bind", "set_parameter", "events", "hydrate", "audit", ("end", 1)]
    def fail(node, schema):
        raise ValueError("invalid registry")
    widget.logic.hydrateDentoCaseStateAfterLoad = fail
    events.clear()
    with pytest.raises(ValueError, match="invalid registry"):
        known.restore_offline_scene("fixture.mrb", {}, "3.0")
    assert events[-1] == ("end", 1)
    assert "audit" not in events
