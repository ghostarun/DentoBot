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
    assert 'saveScene' in source and 'loadScene' in source
    assert 'syncStep6MoveItPlanningScene' not in source
