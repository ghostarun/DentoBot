import ast
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
sys.path.insert(0, str(PYTHON))

import DENTOROS2Bridge as bridge
from DENTOStep6State import JOINT_NAMES, build_manual_simulation_record


class _PointIds:
    def SetNumberOfIds(self, count):
        self.ids = [None] * count

    def SetId(self, index, value):
        self.ids[index] = value


class _PolyLine:
    def __init__(self):
        self.ids = _PointIds()

    def GetPointIds(self):
        return self.ids


class _CellArray:
    def __init__(self):
        self.cells = []

    def InsertNextCell(self, cell):
        self.cells.append(tuple(cell.GetPointIds().ids))


class _Points:
    def __init__(self):
        self.points = []

    def InsertNextPoint(self, *point):
        self.points.append(tuple(point))


class _PolyData:
    def SetPoints(self, points):
        self.points = points

    def SetLines(self, lines):
        self.lines = lines


class _Display:
    def __init__(self):
        self.color = None
        self.selected_color = None
        self.visible = False

    def SetVisibility(self, value):
        self.visible = value

    def SetColor(self, *color):
        self.color = tuple(color)

    def SetSelectedColor(self, *color):
        self.selected_color = tuple(color)

    def SetOpacity(self, value):
        self.opacity = value

    def SetLineWidth(self, value):
        self.line_width = value

    def SetGlyphScale(self, value):
        self.glyph_scale = value


class _Node:
    def __init__(self, class_name, name):
        self.class_name = class_name
        self.name = name
        self.attributes = {}
        self.points = []
        self.display = None
        self.saved_with_scene = True

    def SetName(self, name):
        self.name = name

    def SetAttribute(self, name, value):
        self.attributes[name] = value

    def GetAttribute(self, name):
        return self.attributes.get(name)

    def SaveWithSceneOff(self):
        self.saved_with_scene = False

    def CreateDefaultDisplayNodes(self):
        self.display = _Display()

    def GetDisplayNode(self):
        return self.display

    def AddControlPointWorld(self, point, label):
        self.points.append((tuple(point), label))

    def SetLocked(self, value):
        self.locked = value

    def SetAndObservePolyData(self, polydata):
        self.polydata = polydata


class _Scene:
    def __init__(self):
        self.nodes = []

    def AddNewNodeByClass(self, class_name, name):
        node = _Node(class_name, name)
        self.nodes.append(node)
        return node

    def RemoveNode(self, node):
        self.nodes.remove(node)


class _SlicerUtil:
    def __init__(self, scene):
        self.scene = scene

    def getNodesByClass(self, class_name):
        return [node for node in self.scene.nodes if node.class_name == class_name]


@pytest.fixture
def mrml(monkeypatch):
    scene = _Scene()
    fake_slicer = SimpleNamespace(mrmlScene=scene, util=_SlicerUtil(scene))
    fake_vtk = SimpleNamespace(
        vtkCellArray=_CellArray,
        vtkPoints=_Points,
        vtkPolyData=_PolyData,
        vtkPolyLine=_PolyLine,
        vtkVector3d=lambda *point: tuple(point),
    )
    monkeypatch.setitem(sys.modules, "slicer", fake_slicer)
    monkeypatch.setitem(sys.modules, "vtk", fake_vtk)
    return scene


def _accepted(time_ns, x, *, point=True):
    event = {
        "kind": "guard_accepted",
        "monotonic_ns": time_ns,
        "requested_joints": {name: 0.0 for name in JOINT_NAMES},
        "accepted_joints": {name: 0.0 for name in JOINT_NAMES},
    }
    if point:
        event["tcp_point_ras_mm"] = [float(x), 0.0, 0.0]
    return event


def _record(events):
    return build_manual_simulation_record(
        identity={
            "prepared_branch_id": "branch-a",
            "task_fingerprint": "task-a",
            "base_fingerprint": "base-a",
            "home_fingerprint": "home-a",
            "trajectory_fingerprint": "trajectory-a",
            "robot_profile_fingerprint": "robot-a",
            "scene_fingerprint": "scene-a",
        },
        events=events,
    )


def _phase_node(scene):
    node = scene.AddNewNodeByClass("vtkMRMLModelNode", "Planned phase path")
    node.SetAttribute(bridge.ROS2_PHASE_PATH_ATTRIBUTE, "true")
    node.SetAttribute("DENTOBOT.IntendedUse", "DisplayOnlyPhasePlan")
    return node


def test_manual_record_paths_reparse_split_segments_and_clear_only_owned_nodes(mrml):
    phase = _phase_node(mrml)
    record = _record(
        [
            {
                "kind": "requested",
                "monotonic_ns": 1,
                "requested_joints": {name: 0.0 for name in JOINT_NAMES},
                "tcp_point_ras_mm": [9.0, 0.0, 0.0],
            },
            _accepted(2, 0),
            {"kind": "requested", "monotonic_ns": 3, "requested_joints": {name: 0.0 for name in JOINT_NAMES}},
            _accepted(4, 1),
            {
                "kind": "guard_rejected",
                "monotonic_ns": 5,
                "requested_joints": {name: 1.0 for name in JOINT_NAMES},
                "accepted_joints": {name: 0.0 for name in JOINT_NAMES},
                "native_failure_evidence": {"reason": "collision"},
                "tcp_point_ras_mm": [2.0, 0.0, 0.0],
            },
            _accepted(6, 3),
            _accepted(7, 4),
            {
                "kind": "diagnostic",
                "monotonic_ns": 8,
                "diagnostic": {"guard_accepted": None},
                "tcp_point_ras_mm": [5.0, 0.0, 0.0],
            },
            _accepted(9, 6),
            _accepted(10, 7),
        ]
    )

    ok, message = bridge.show_manual_simulation_record_paths(record)

    assert ok and "historical manual simulation evidence" in message
    assert phase in mrml.nodes
    owned = [
        node
        for node in mrml.nodes
        if node.GetAttribute(bridge.ROS2_MANUAL_SIMULATION_HISTORICAL_PATH_ATTRIBUTE) == "true"
    ]
    assert owned
    assert all(node.GetAttribute("DENTOBOT.IntendedUse") == "HistoricalDisplayOnly" for node in owned)
    assert all(node.saved_with_scene is False for node in owned)
    path = next(node for node in owned if node.class_name == "vtkMRMLModelNode")
    assert path.polydata.points.points == [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (3.0, 0.0, 0.0),
        (4.0, 0.0, 0.0),
        (6.0, 0.0, 0.0),
        (7.0, 0.0, 0.0),
    ]
    assert path.polydata.lines.cells == [(0, 1), (2, 3), (4, 5)]
    requested = next(node for node in owned if "Requested" in node.name)
    rejected = next(node for node in owned if "Rejected" in node.name)
    assert requested.display.color != rejected.display.color
    assert len(requested.points) == len(rejected.points) == 1

    bridge.clear_manual_simulation_record_paths()
    assert mrml.nodes == [phase]


def test_manual_record_paths_without_samples_reports_unavailable_and_invalidates_old_view(mrml):
    phase = _phase_node(mrml)
    stale = mrml.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "old path marker")
    stale.SetAttribute(bridge.ROS2_MANUAL_SIMULATION_HISTORICAL_PATH_ATTRIBUTE, "true")
    record = _record([{"kind": "diagnostic", "monotonic_ns": 1, "diagnostic": {"status": "unknown"}}])

    ok, message = bridge.show_manual_simulation_record_paths(record)

    assert not ok and "no recorded TCP points" in message
    assert mrml.nodes == [phase]

    record["record_fingerprint"] = "tampered"
    ok, message = bridge.show_manual_simulation_record_paths(record)
    assert not ok and "record is invalid" in message
    assert mrml.nodes == [phase]


def test_manual_record_path_renderer_has_no_fk_or_motion_calls():
    source = (PYTHON / "DENTOROS2Bridge.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "show_manual_simulation_record_paths"
    )
    calls = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
    }
    assert "parse_manual_simulation_record" in calls
    assert calls.isdisjoint(
        {
            "ComputeKDLFK",
            "compute_tcp_pose_world_ras_mm",
            "plan_moveit_cartesian_path",
            "publish_manual_jog",
            "publish_joint_positions",
        }
    )
