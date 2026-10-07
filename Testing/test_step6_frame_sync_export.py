"""Source export mapping known answers; fake MRML nodes, no Slicer/ROS."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import vtk

sys.path.insert(0,str(Path(__file__).resolve().parent))
import step6_frame_sync_export as exporter


def poly():
    return exporter.audit_tools._mesh_polydata(np.array([[0,0,0],[1,0,0],[0,1,0.]],float), [[0,1,2]])


class Transform:
    def GetMatrixTransformToWorld(self, m):
        m.Identity(); m.SetElement(0,3,10)


class Model:
    def GetPolyData(self): return poly()
    def GetParentTransformNode(self): return None


def test_export_resolves_world_model_and_inverse_base_without_publishing(tmp_path):
    record={'outgoing_collision_object_id':'object','source_id':'vtkMRMLModelNode1'}
    audit=SimpleNamespace(object_records=[record])
    ns={'logic':SimpleNamespace(collisionSceneAuditRecord=lambda n:audit),
        'parameter_node':SimpleNamespace(robotBaseTransform=Transform()),
        'scene':SimpleNamespace(GetNodeByID=lambda i:Model())}
    destination=tmp_path/'export'
    result=exporter.export_scene(ns,destination)
    assert result['status']=='PASS'
    mesh=np.load(destination/result['objects'][0]['file'])
    assert np.allclose(mesh['vertices'],[[-10,0,0],[-9,0,0],[-10,1,0]])
    assert json.loads((destination/'manifest.json').read_text())['units']=='mm'
    with pytest.raises(FileExistsError): exporter.export_scene(ns,destination)


def test_unknown_source_is_an_explicit_failure_not_skip(tmp_path):
    record={'outgoing_collision_object_id':'missing','source_id':'unsupported'}
    ns={'logic':SimpleNamespace(collisionSceneAuditRecord=lambda n:SimpleNamespace(object_records=[record])),
        'parameter_node':SimpleNamespace(robotBaseTransform=Transform()), 'scene':object()}
    result=exporter.export_scene(ns,tmp_path/'bad')
    assert result['status']=='FAIL' and result['objects'][0]['status']=='FAIL'
    assert 'Unsupported' in result['objects'][0]['error']


def test_closed_lower_segment_receives_exactly_one_explicit_opening(monkeypatch):
    calls=[]
    monkeypatch.setattr(exporter,'segment_world_polydata',lambda seg,sid:poly())
    def opened(n,p):
        calls.append('opened'); return p
    ns={'logic':SimpleNamespace(_step6CaseJawPolydataWorld=opened), 'parameter_node':object(),
        'scene':SimpleNamespace(GetNodeByID=lambda i:object())}
    record={'source_id':'vtkMRMLSegmentationNode1:target:lower','jaw_transform_application_count':1}
    exporter.source_world_mesh(ns,record)
    assert calls==['opened']
    with pytest.raises(ValueError,match='number'):
        exporter.source_world_mesh(ns,{**record,'jaw_transform_application_count':2})
