"""Assisted Step 4A and exact binary-mask regressions; no Slicer runtime."""
import ast
from pathlib import Path
import sys
from types import MethodType, SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "DENTOWorkflow/Resources/Python"))
from DENTOTrajectoryGeometry import first_mask_intersection


def test_assisted_entry_placement_is_one_point_per_button_click():
    logic_source_path = (
        Path(__file__).resolve().parents[1]
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_workflow.py"
    )
    logic_tree = ast.parse(logic_source_path.read_text(encoding="utf-8"))
    logic_method = next(
        node
        for node in ast.walk(logic_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "startAssistedTrajectoryEntryPlacement"
    )

    class SelectionStub:
        def __init__(self):
            self.node_id = None
            self.class_name = None

        def SetReferenceActivePlaceNodeClassName(self, class_name):
            self.class_name = class_name

        def SetActivePlaceNodeID(self, node_id):
            self.node_id = node_id

        def SetActivePlaceNodeClassName(self, class_name):
            self.class_name = class_name

        def GetActivePlaceNodeID(self):
            return self.node_id

        def GetActivePlaceNodePlacementValid(self):
            return True

    selection = SelectionStub()
    markups_calls = []
    stop_calls = []
    slicer_stub = SimpleNamespace(
        app=SimpleNamespace(
            applicationLogic=lambda: SimpleNamespace(
                GetSelectionNode=lambda: selection
            )
        ),
        modules=SimpleNamespace(
            markups=SimpleNamespace(
                logic=lambda: SimpleNamespace(
                    StartPlaceMode=lambda persistent: markups_calls.append(persistent)
                )
            )
        ),
    )

    class PlacementLogicStub:
        @staticmethod
        def isAssistedTrajectoryEntryNode(node):
            return bool(node and node.IsA("vtkMRMLMarkupsFiducialNode"))

        @staticmethod
        def stopTrajectoryPlacement():
            stop_calls.append(True)

    class PlacementEntryStub:
        def IsA(self, class_name):
            return class_name == "vtkMRMLMarkupsFiducialNode"

        def GetID(self):
            return "assisted-entry"

    namespace = {
        "DENTOWorkflowLogic": PlacementLogicStub,
        "slicer": slicer_stub,
        "_": lambda message: message,
    }
    logic_method.decorator_list = []
    exec(
        compile(
            ast.fix_missing_locations(ast.Module([logic_method], [])),
            "<assisted-placement>",
            "exec",
        ),
        namespace,
    )
    placement = namespace["startAssistedTrajectoryEntryPlacement"]
    entry = PlacementEntryStub()
    placement(entry)
    placement(entry)
    assert markups_calls == [0, 0]
    assert stop_calls == []
    assert selection.node_id == "assisted-entry"
    assert selection.class_name == "vtkMRMLMarkupsFiducialNode"

    widget_source_path = (
        Path(__file__).resolve().parents[1]
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_planning_focus.py"
    )
    widget_tree = ast.parse(widget_source_path.read_text(encoding="utf-8"))
    widget_method = next(
        node
        for node in ast.walk(widget_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "onPlaceAssistedTrajectoryEntries"
    )

    segmentation = object()

    class EntrySetStub:
        def __init__(self):
            self.defined = 0

        def GetNodeReference(self, _role):
            return segmentation

        def GetAttribute(self, name):
            return "seg1" if name == "DENTOBOT.TargetSegmentID" else ""

    entry_set = EntrySetStub()

    class AssistedLogicStub:
        ASSISTED_ENTRY_SEGMENTATION_REFERENCE_ROLE = "segmentation"

        def __init__(self):
            self.create_calls = 0
            self.start_calls = []

        def validateTargetTooth(self, _segmentation, _segment_id):
            return {"segmentId": "seg1"}

        def getSegmentationReviewState(self, _segmentation):
            return "Reviewed"

        def dentobotTrajectoriesForTarget(self, _segmentation, _segment_id):
            return []

        def isAssistedTrajectoryEntryNode(self, node):
            return node is entry_set

        def getAssistedTrajectoryEntrySummary(self, node):
            return {
                "expectedCount": 2,
                "definedPointCount": node.defined,
                "isComplete": node.defined == 2,
            }

        def createOrResetAssistedTrajectoryEntries(
            self, _segmentation, _segment_id, _expected_count, _current_node
        ):
            self.create_calls += 1
            return entry_set, {}

        def startAssistedTrajectoryEntryPlacement(self, node):
            self.start_calls.append(node)

    logic = AssistedLogicStub()
    parameter_node = SimpleNamespace(
        teethSegmentation=segmentation,
        targetToothSegmentId="seg1",
        assistedTrajectoryCount=2,
        assistedTrajectoryEntries=None,
    )
    confirm_calls = []
    errors = []
    slicer_stub.util = SimpleNamespace(
        confirmYesNoDisplay=lambda *args, **kwargs: (
            confirm_calls.append(True) or True
        ),
        errorDisplay=lambda message: errors.append(message),
    )

    class WidgetStub:
        def __init__(self):
            self._parameterNode = parameter_node
            self.logic = logic

        def _bindAssistedTrajectoryEntryNode(self, _node):
            return None

        def _startAssistedTrajectoryFocus(self):
            return None

        def _updateAssistedTrajectoryControls(self):
            return None

    widget_namespace = {"slicer": slicer_stub, "_": lambda message: message}
    widget_method.decorator_list = []
    exec(
        compile(
            ast.fix_missing_locations(ast.Module([widget_method], [])),
            "<assisted-widget>",
            "exec",
        ),
        widget_namespace,
    )
    place = MethodType(
        widget_namespace["onPlaceAssistedTrajectoryEntries"], WidgetStub()
    )
    place()
    assert logic.create_calls == 1
    assert logic.start_calls == [entry_set]
    assert parameter_node.assistedTrajectoryEntries is entry_set

    entry_set.defined = 1
    place()
    assert logic.create_calls == 1
    assert logic.start_calls == [entry_set, entry_set]
    assert confirm_calls == []
    assert errors == []


def test_first_pulp_boundary_single_dual_and_misses():
    mask = np.zeros((9, 3, 3), dtype=np.uint8)
    mask[2, :, :] = 1
    mask[6, :, :] = 1
    for entries in ([(0, 0, 0)], [(0, 0, 0), (2, 2, 0)]):
        for entry in entries:
            target = (*entry[:2], 8)
            assert first_mask_intersection(mask, entry, target) == pytest.approx(1.5 / 8)
    assert first_mask_intersection(mask, (1, 1, 8), (1, 1, 0)) == pytest.approx(1.5 / 8)
    assert first_mask_intersection(mask, (0, 0, 0), (2, 2, 8)) == pytest.approx(1.5 / 8)
    assert first_mask_intersection(mask, (10, 20, 30), (10, 20, 38), (10, 20, 30)) == pytest.approx(1.5 / 8)
    for entry, target in [((5, 0, 0), (5, 0, 8)), ((0, 0, 0), (0, 0, 1))]:
        with pytest.raises(ValueError, match="does not intersect"):
            first_mask_intersection(mask, entry, target)
    with pytest.raises(ValueError, match="inside or touching"):
        first_mask_intersection(mask, (1, 1, 2), (1, 1, 8))
    with pytest.raises(ValueError, match="empty"):
        first_mask_intersection(np.zeros_like(mask), (0, 0, 0), (0, 0, 8))
    with pytest.raises(ValueError, match="non-finite"):
        first_mask_intersection(mask, (float("nan"), 0, 0), (0, 0, 8))
