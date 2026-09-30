"""Slicer-free regressions for Step 2 pulp inventory and bulk preparation."""

from __future__ import annotations

import ast
import hashlib
import json
import logging
from pathlib import Path
import runpy
from types import MethodType, SimpleNamespace

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow" / "Resources" / "Python"
ASSOCIATE_PULP_COMPONENTS = runpy.run_path(
    str(PYTHON / "dentobot_workflow" / "dental_semantics.py")
)["associate_pulp_components"]


class MissingTargetPulpError(ValueError):
    pass


class MutableString:
    def __init__(self, value=""):
        self.value = value

    def __str__(self):
        return str(self.value)


class Matrix:
    def GetElement(self, row, column):
        return 1.0 if row == column else 0.0


class Image:
    def __init__(self):
        self.extent = (0, 3, 0, 3, 0, 3)

    def GetExtent(self):
        return self.extent

    def GetImageToWorldMatrix(self, matrix):
        return None


class Segment:
    def __init__(self, label, tags=None):
        self.label = label
        self.tags = tags or {}

    def GetLabelValue(self):
        return self.label

    def GetTag(self, key, output):
        if key not in self.tags:
            return False
        output.value = self.tags[key]
        return True


class Segmentation:
    def __init__(self, segments=None):
        self.segments = segments or {}

    def GetSegment(self, segment_id):
        return self.segments[segment_id]


class SegmentationNode:
    def __init__(self, records, attributes=None):
        self.attributes = dict(attributes or {})
        self.segmentation = Segmentation()
        self.arrays = {}
        for index, record in enumerate(records, 1):
            segment_id = record["segmentId"]
            self.segmentation.segments[segment_id] = Segment(
                index, record.get("tags", {})
            )
            mask = np.zeros((4, 4, 4), dtype=np.uint8)
            mask[index % 3 + 1, 1, 1] = index
            self.arrays[segment_id] = mask

    def GetAttribute(self, key):
        return self.attributes.get(key)

    def SetAttribute(self, key, value):
        self.attributes[key] = value

    def GetSegmentation(self):
        return self.segmentation

    def GetBinaryLabelmapRepresentation(self, _segment_id, _image):
        _image.extent = getattr(self, "extent", (0, 3, 0, 3, 0, 3))
        return True


def test_fingerprint_survives_equivalent_labelmap_extent_change():
    records = _records(("t11", "11", "VALID"))
    first = _trusted_node(records)
    second = _trusted_node(records)
    first.arrays["t11"][:] = 0
    first.arrays["t11"][1, 1, 1] = 1
    second.arrays["t11"][:] = 0
    second.arrays["t11"][0, 0, 0] = 1
    second.extent = (1, 4, 1, 4, 1, 4)
    logic = _logic(records, first, {})
    assert logic._pulpInventoryFingerprint(first, records) == logic._pulpInventoryFingerprint(second, records)


def _extract_methods(path, class_name, names, globals_):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    source_class = next(
        item for item in tree.body
        if isinstance(item, ast.ClassDef) and item.name == class_name
    )
    methods = [
        item for item in source_class.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name in names
    ]
    assert {item.name for item in methods} == set(names)
    extracted = ast.ClassDef(
        name="ExtractedMethods", bases=[], keywords=[], body=methods,
        decorator_list=[],
    )
    namespace = dict(globals_)
    exec(compile(ast.fix_missing_locations(ast.Module([extracted], [])), str(path), "exec"), namespace)
    return namespace["ExtractedMethods"]


def _lineage_methods():
    return _extract_methods(
        PYTHON / "dentobot_workflow" / "logic_lineage.py",
        "LineageLogicMixin",
        {
            "_pulpInventoryFingerprint",
            "getPulpInventoryReport",
            "checkPulpInventory",
            "createMissingPulpCandidates",
            "getTargetPulpAssociation",
            "_prepareInventoryPulpEvidence",
        },
        {
            "hashlib": hashlib,
            "json": json,
            "np": np,
            "slicer": SimpleNamespace(
                vtkOrientedImageData=Image,
                util=SimpleNamespace(
                    arrayFromSegmentInternalBinaryLabelmap=lambda node, segment_id: node.arrays[segment_id]
                ),
            ),
            "vtk": SimpleNamespace(vtkMatrix4x4=Matrix, mutable=MutableString),
            "vtkMRMLSegmentationNode": object,
            "associate_pulp_components": ASSOCIATE_PULP_COMPONENTS,
            "_": lambda message: message,
            "MissingTargetPulpError": MissingTargetPulpError,
        },
    )


def _records(*items):
    records = []
    for item in items:
        segment_id, fdi, state, *rest = item
        record = {
            "segmentId": segment_id,
            "structureType": "TOOTH",
            "canonicalFdiNumber": fdi,
            "validationState": state,
        }
        if rest:
            record["tags"] = rest[0]
        records.append(record)
    return records


def _logic(records, node, associations):
    logic = _lineage_methods()()
    logic.PULP_REPORT_ATTRIBUTE = "DENTOBOT.PulpInventoryJson"
    logic.SEMANTIC_PERSISTENCE_ATTRIBUTE = "DENTOBOT.SemanticPersistence"
    logic.getSegmentationReviewRecords = lambda _node: records
    logic._semanticPersistenceIssues = lambda _node, _records: []
    logic.getSegmentationSourceVolume = lambda _node: object()
    logic.getSegmentationReviewState = lambda selected: (
        selected.GetAttribute("DENTOBOT.ReviewState") or "Needs Correction"
    )

    def target_association(_node, tooth_id, **_kwargs):
        result = associations.get(tooth_id, "missing")
        if result == "missing":
            raise MissingTargetPulpError("no associated pulp")
        if isinstance(result, Exception):
            raise result
        return {"pulpSegmentId": result}

    logic.getTargetPulpAssociation = target_association
    return logic


def _trusted_node(records):
    return SegmentationNode(
        records,
        {
            "DENTOBOT.SegmentMetricsJson": json.dumps({"semantic": {"schemaVersion": "1.0"}}),
            "DENTOBOT.SemanticPersistence": "current",
            "DENTOBOT.RunId": "legacy-run-1",
        },
    )


def test_inventory_counts_association_states_and_absent_adult_fdi_read_only():
    records = _records(
        ("t11", "11", "VALID"),
        ("t21", "21", "VALID"),
        ("t31", "31", "VALID"),
        ("t12", "12", "VALID"),
        ("t41", "41", "INVALID"),
    )
    node = _trusted_node(records)
    node.segmentation.segments.update({
        "p11": Segment(10),
        "p31": Segment(11, {"DENTOBOT.Derivation": "enclosed-tooth-void-v1"}),
    })
    candidate_mask = np.zeros((4, 4, 4), dtype=np.uint8)
    candidate_mask[1, 1, 1] = 11
    node.arrays.update({
        "p11": np.zeros((4, 4, 4), dtype=np.uint8),
        "p31": candidate_mask,
    })
    associations = {
        "t11": "p11",
        "t21": "missing",
        "t31": "p31",
        "t12": ValueError("pulp evidence is ambiguous"),
    }
    logic = _logic(records, node, associations)

    report = logic.checkPulpInventory(node)

    assert report["counts"] == {
        "associated": 1,
        "missing": 1,
        "candidate": 1,
        "cannot-evaluate": 1,
        "ambiguous": 1,
    }
    assert {row["toothSegmentId"]: row["status"] for row in report["rows"]} == {
        "t11": "associated",
        "t21": "missing",
        "t31": "candidate",
        "t12": "ambiguous",
        "t41": "cannot-evaluate",
    }
    assert next(row for row in report["rows"] if row["toothSegmentId"] == "t31")["voxelCount"] == 1
    assert len(report["absentFdi"]) == 27
    assert not {"11", "12", "21", "31", "41"}.intersection(report["absentFdi"])
    assert "48" in report["absentFdi"]
    assert len(node.segmentation.segments) == 7


def test_inventory_reuses_geometry_evidence_per_run_and_keeps_associations_target_specific():
    records = _records(("t11", "11", "VALID"), ("t21", "21", "VALID"))
    records.extend([
        {
            "segmentId": "p11",
            "structureType": "PULP",
            "canonicalFdiNumber": "11",
            "sourceFdiHint": "11",
            "validationState": "VALID",
        },
        {
            "segmentId": "p21",
            "structureType": "PULP",
            "canonicalFdiNumber": "21",
            "sourceFdiHint": "21",
            "validationState": "VALID",
        },
    ])
    node = _trusted_node(records)
    logic = _lineage_methods()()
    logic.PULP_REPORT_ATTRIBUTE = "DENTOBOT.PulpInventoryJson"
    logic.SEMANTIC_PERSISTENCE_ATTRIBUTE = "DENTOBOT.SemanticPersistence"
    logic.getSegmentationReviewRecords = lambda _node: records
    logic._semanticPersistenceIssues = lambda *_args: []
    logic.getSegmentationSourceVolume = lambda _node: object()
    logic.getSegmentationReviewState = lambda _node: "Reviewed"
    logic.validateTargetTooth = lambda _node, tooth_id: next(
        record for record in records if record["segmentId"] == tooth_id
    )
    logic._derivedPulpAssociation = lambda *_args: None

    surface_calls = []
    component_calls = []
    candidate_calls = []
    logic._getClosedSurfaceWorldCopy = lambda _node, segment_id: (
        surface_calls.append(segment_id) or SimpleNamespace(segment_id=segment_id)
    )

    def pulp_components(_node, pulp_record):
        segment_id = pulp_record["segmentId"]
        component_calls.append(segment_id)
        return [{
            "componentId": f"{segment_id}:component-1",
            "sourceSegmentId": segment_id,
            "pointsWorld": [(0.0, 0.0, 0.0)],
        }]

    def pulp_candidates(pulp_record, component, tooth_surfaces, progress=None):
        candidate_calls.append(component["sourceSegmentId"])
        if progress:
            for tooth_id in tooth_surfaces:
                progress(tooth_id)
        target_fdi = pulp_record["sourceFdiHint"]
        return [
            {
                "toothSegmentId": tooth_id,
                "toothFdiNumber": tooth["record"]["canonicalFdiNumber"],
                "sourceFdiHint": target_fdi,
                "insideFraction": 1.0 if tooth["record"]["canonicalFdiNumber"] == target_fdi else 0.0,
                "nearestToothFraction": 1.0 if tooth["record"]["canonicalFdiNumber"] == target_fdi else 0.0,
                "robustSurfaceDistanceMm": 0.1 if tooth["record"]["canonicalFdiNumber"] == target_fdi else 99.0,
            }
            for tooth_id, tooth in tooth_surfaces.items()
        ]

    logic._semanticPulpComponents = pulp_components
    logic._semanticPulpCandidates = pulp_candidates
    progress_events = []

    def progress(*event):
        progress_events.append(event)

    first = logic.checkPulpInventory(node, progress=progress)
    assert {row["toothSegmentId"]: (row["status"], row["pulpSegmentId"]) for row in first["rows"]} == {
        "t11": ("associated", "p11"),
        "t21": ("associated", "p21"),
    }
    phases = {event[3] for event in progress_events if len(event) == 4}
    assert phases >= {
        "Preparing tooth surfaces",
        "Preparing pulp components",
        "Scoring pulp candidates",
        "Checking target rows",
    }
    assert surface_calls == ["t11", "t21"]
    assert component_calls == ["p11", "p21"]
    assert candidate_calls == ["p11", "p21"]

    second = logic.checkPulpInventory(node, progress=progress)
    assert {row["toothSegmentId"]: (row["status"], row["pulpSegmentId"]) for row in second["rows"]} == {
        "t11": ("associated", "p11"),
        "t21": ("associated", "p21"),
    }
    assert surface_calls == ["t11", "t21", "t11", "t21"]
    assert component_calls == ["p11", "p21", "p11", "p21"]
    assert candidate_calls == ["p11", "p21", "p11", "p21"]

    association = logic.getTargetPulpAssociation(
        node, "t11", persist=False, requireReview=False
    )
    assert association["pulpSegmentId"] == "p11"
    assert surface_calls == ["t11", "t21"] * 3
    assert component_calls == ["p11", "p21"] * 3
    assert candidate_calls == ["p11", "p21"] * 3


def test_legacy_untrusted_run_is_unevaluable_and_step2_offers_manual_check():
    records = [{
        "segmentId": "legacy-tooth",
        "structureType": "TOOTH",
        "canonicalFdiNumber": None,
        "displayName": "upper_right_central_incisor_fdi11",
        "validationState": "UNRESOLVED",
    }]
    node = SegmentationNode(records, {"DENTOBOT.BridgeOperation": "segment-teeth"})
    logic = _logic(records, node, {})
    ui = SimpleNamespace(
        checkPulpMasksButton=SimpleNamespace(enabled=False),
        viewPulpReportButton=SimpleNamespace(enabled=False),
        createMissingPulpsButton=SimpleNamespace(enabled=False),
        pulpInventorySummaryLabel=SimpleNamespace(text=""),
    )
    widget_methods = _extract_methods(
        PYTHON / "dentobot_workflow" / "widget_segmentation.py",
        "SegmentationWidgetMixin",
        {"_updatePulpInventoryControls", "onCheckPulpMasks"},
        {"_": lambda message: message,
         "qt": SimpleNamespace(QProgressDialog=lambda *_args: SimpleNamespace(setCancelButton=lambda _value: None, setWindowModality=lambda _value: None, setAutoClose=lambda _value: None, setAutoReset=lambda _value: None, setRange=lambda *_values: None, show=lambda: None, close=lambda: None, setLabelText=lambda _value: None, setValue=lambda _value: None), Qt=SimpleNamespace(WindowModal=1)),
         "slicer": SimpleNamespace(util=SimpleNamespace(errorDisplay=lambda _message: None, mainWindow=lambda: None), app=SimpleNamespace(processEvents=lambda: None))},
    )
    widget = widget_methods()
    widget._reviewSegmentationNode = node
    widget.logic = logic
    widget.ui = ui
    widget._updatingSegmentationReviewUI = False
    opened = []
    widget._showPulpInventoryDialog = lambda selected, report: opened.append((selected, report))
    report = {"counts": {"associated": 0, "missing": 0, "candidate": 0, "cannot-evaluate": 1, "ambiguous": 0}, "rows": [], "absentFdi": []}
    checks = []
    logic.checkPulpInventory = lambda selected, progress=None: checks.append(selected) or report
    logic.getPulpInventoryReport = lambda _selected: None
    logic.createMissingPulpCandidates = lambda _selected: pytest.fail("checking must not create masks")

    widget._updatePulpInventoryControls()
    assert ui.checkPulpMasksButton.enabled
    assert not ui.viewPulpReportButton.enabled
    assert not ui.createMissingPulpsButton.enabled
    assert "Click Check Pulp Masks" in ui.pulpInventorySummaryLabel.text

    widget.onCheckPulpMasks()
    assert checks == [node]
    assert opened == [(node, report)]

    # The actual checker keeps identity from canonical metadata; a legacy display
    # name alone cannot turn this mask into FDI11 or trigger pulp lookup.
    node.attributes["DENTOBOT.SegmentMetricsJson"] = json.dumps({"segments": []})
    legacy_logic = _logic(records, node, {})
    audited = legacy_logic.checkPulpInventory(node)
    assert audited["rows"][0]["fdi"] == ""
    assert audited["rows"][0]["status"] == "cannot-evaluate"


def test_bulk_candidate_creation_keeps_partial_results_and_skips_existing_on_repeat():
    records = _records(("t11", "11", "VALID"), ("t21", "21", "VALID"))
    node = _trusted_node(records)
    node.SetAttribute("DENTOBOT.ReviewState", "Reviewed")
    logic = _logic(records, node, {"t11": "missing", "t21": "missing"})
    attempts = []

    def create_candidate(_self, _node, tooth_id, fdi, *, invalidateReview=False):
        attempts.append(tooth_id)
        if tooth_id == "t21" and attempts.count("t21") == 1:
            raise ValueError("enclosed region is occupied")
        candidate_id = f"derived-p{fdi}"
        node.segmentation.segments[candidate_id] = Segment(
            12, {"DENTOBOT.Derivation": "enclosed-tooth-void-v1"}
        )
        node.arrays[candidate_id] = np.zeros((4, 4, 4), dtype=np.uint8)
        records.append({
            "segmentId": candidate_id,
            "structureType": "PULP",
            "canonicalFdiNumber": f"1{fdi}",
            "validationState": "VALID",
        })
        logic_associations[tooth_id] = candidate_id
        return candidate_id, 52 if tooth_id == "t11" else 46

    logic._createEnclosedPulpCandidate = MethodType(create_candidate, logic)
    logic_associations = {"t11": "missing", "t21": "missing"}
    logic.getTargetPulpAssociation = lambda _node, tooth_id, **_kwargs: (
        {"pulpSegmentId": logic_associations[tooth_id]}
        if logic_associations[tooth_id] != "missing"
        else (_ for _ in ()).throw(MissingTargetPulpError("no associated pulp"))
    )
    logic.invalidateSegmentationReviewAfterEdit = lambda selected: selected.SetAttribute(
        "DENTOBOT.ReviewState", "Needs Correction"
    )
    logic.setSegmentationReviewState = lambda selected, state: selected.SetAttribute(
        "DENTOBOT.ReviewState", state
    )

    logic.checkPulpInventory(node)
    report = logic.createMissingPulpCandidates(node)

    assert report["createdCount"] == 1
    assert report["failedCount"] == 1
    rows = {row["toothSegmentId"]: row for row in report["rows"]}
    assert (rows["t11"]["status"], rows["t11"]["voxelCount"]) == ("created", 52)
    assert rows["t21"]["status"] == "failed"
    assert rows["t21"]["reason"] == "enclosed region is occupied"
    assert len([key for key in node.segmentation.segments if key.startswith("derived-")]) == 1
    assert node.GetAttribute("DENTOBOT.ReviewState") == "Needs Correction"
    assert rows["t11"]["reviewState"] == "Needs Correction"

    retried = logic.createMissingPulpCandidates(node)
    assert retried["createdCount"] == 1
    assert len([key for key in node.segmentation.segments if key.startswith("derived-")]) == 2
    assert attempts.count("t11") == 1
    assert attempts.count("t21") == 2


def test_bulk_candidate_widget_invalidates_before_refresh_and_closes_progress():
    events = []
    widget_ref = {}
    processing_states = []

    def process_events():
        widget = widget_ref.get("widget")
        if widget:
            processing_states.append(
                (
                    widget._processingSegmentationContentChange,
                    widget._updatingSegmentationReviewUI,
                )
            )

    dialog = SimpleNamespace(
        setCancelButton=lambda _value: None,
        setWindowModality=lambda _value: None,
        setAutoClose=lambda _value: None,
        setAutoReset=lambda _value: None,
        show=lambda: events.append("show"),
        setLabelText=lambda text: (
            events.append("refresh-label")
            if text == "Refreshing workflow eligibility..."
            else None
        ),
        setRange=lambda *_values: None,
        setValue=lambda _value: None,
        close=lambda: events.append("close"),
    )
    widget_methods = _extract_methods(
        PYTHON / "dentobot_workflow" / "widget_segmentation.py",
        "SegmentationWidgetMixin",
        {"onCreateMissingPulps"},
        {
            "_": lambda message: message,
            "qt": SimpleNamespace(
                QProgressDialog=lambda *_args: dialog,
                Qt=SimpleNamespace(WindowModal=1),
            ),
            "slicer": SimpleNamespace(
                util=SimpleNamespace(
                    mainWindow=lambda: None,
                    errorDisplay=lambda _message: None,
                ),
                app=SimpleNamespace(processEvents=process_events),
            ),
        },
    )
    logic = SimpleNamespace(
        getPulpInventoryReport=lambda _node: {"rows": [{"status": "missing"}]},
        createMissingPulpCandidates=lambda _node, progress: (
            progress(1, 1, "11") or {"createdCount": 1}
        ),
        invalidateCaseFoundationForSourceChange=lambda *_args: events.append("invalidate"),
    )
    node = object()
    widget = widget_methods()
    widget._reviewSegmentationNode = node
    widget._parameterNode = SimpleNamespace(teethSegmentation=node)
    widget.logic = logic
    widget_ref["widget"] = widget
    widget._rebuildSegmentTree = lambda: events.append("rebuild")
    widget._updatePlanning = lambda: events.append("planning")
    widget._updateTemplateModeling = lambda: events.append("template")
    widget._showPulpInventoryDialog = lambda *_args: events.append("report")

    widget.onCreateMissingPulps()

    assert events.index("invalidate") < events.index("planning")
    assert events.index("refresh-label") < events.index("planning")
    assert events.index("close") > events.index("template")
    assert events.index("close") < events.index("report")
    assert processing_states
    assert all(segmentation and review_ui for segmentation, review_ui in processing_states)
    assert not widget._processingSegmentationContentChange
    assert not widget._updatingSegmentationReviewUI


def test_restore_callbacks_are_noop_and_live_edit_invalidates_before_planning():
    widget_methods = _extract_methods(
        PYTHON / "dentobot_workflow" / "widget_segmentation.py",
        "SegmentationWidgetMixin",
        {
            "_onReviewSegmentationContentModified",
            "_commitPlanningSegmentationSelection",
        },
        {"_": lambda message: message},
    )
    events = []
    node = object()
    widget = widget_methods()
    widget._caseBundleRestoreDepth = 1
    widget._processingSegmentationContentChange = False
    widget._updatingSegmentationReviewUI = False
    widget._restoringTrajectoryAssociation = False
    widget._updatingFromParameterNode = False
    widget._reviewSegmentationNode = node
    widget._parameterNode = SimpleNamespace(teethSegmentation=node)
    widget.logic = SimpleNamespace(
        invalidateSegmentationReviewAfterEdit=lambda *_args: events.append("review"),
        invalidateCaseFoundationForSourceChange=lambda *_args: events.append("foundation"),
    )

    widget._onReviewSegmentationContentModified()
    widget._commitPlanningSegmentationSelection(object())
    assert events == []
    assert widget._parameterNode.teethSegmentation is node

    widget._caseBundleRestoreDepth = 0
    widget._validTrajectoryPointsByNodeId = {}
    widget.ui = SimpleNamespace(
        segmentationReviewStatusLabel=SimpleNamespace(text="", styleSheet="")
    )
    widget.logic.invalidateSegmentationReviewAfterEdit = (
        lambda _node: events.append("review") or True
    )
    widget._rebuildSegmentTree = lambda: events.append("rebuild")
    widget._refreshSegmentationInspection = lambda: events.append("inspect")
    widget._updatePlanning = lambda: events.append("planning")
    widget._updateTemplateModeling = lambda: events.append("template")

    widget._onReviewSegmentationContentModified()

    assert events.index("foundation") < events.index("planning")
    assert events.index("planning") < events.index("template")


def test_relevant_mask_edit_marks_report_stale_and_blocks_bulk_creation():
    records = _records(("t11", "11", "VALID"))
    node = _trusted_node(records)
    node.SetAttribute("DENTOBOT.BridgeOperation", "segment-teeth")
    logic = _logic(records, node, {"t11": "missing"})
    logic.checkPulpInventory(node)
    node.arrays["t11"][0, 0, 0] = 1

    report = logic.getPulpInventoryReport(node)
    assert report["stale"]
    with pytest.raises(ValueError, match="Check Pulp Masks"):
        logic.createMissingPulpCandidates(node)

    widget_methods = _extract_methods(
        PYTHON / "dentobot_workflow" / "widget_segmentation.py",
        "SegmentationWidgetMixin",
        {"_updatePulpInventoryControls"},
        {"_": lambda message: message},
    )
    widget = widget_methods()
    widget._reviewSegmentationNode = node
    widget.logic = logic
    widget.ui = SimpleNamespace(
        checkPulpMasksButton=SimpleNamespace(enabled=False),
        viewPulpReportButton=SimpleNamespace(enabled=False),
        createMissingPulpsButton=SimpleNamespace(enabled=False),
        pulpInventorySummaryLabel=SimpleNamespace(text=""),
    )
    widget._updatePulpInventoryControls()
    assert widget.ui.checkPulpMasksButton.enabled
    assert not widget.ui.createMissingPulpsButton.enabled
    assert "report is stale" in widget.ui.pulpInventorySummaryLabel.text


def test_new_segmentation_completion_runs_the_read_only_inventory_check(tmp_path):
    class Display:
        def SetAndObserveColorNodeID(self, _node_id):
            pass

        def SetVisibility(self, _visible):
            pass

        def SetVisibility2D(self, _visible):
            pass

        def SetVisibility3D(self, _visible):
            pass

        def SetOpacity3D(self, _opacity):
            pass

    class SourceVolume:
        def GetID(self):
            return "source-volume"

        def GetName(self):
            return "CBCT"

        def SetNodeReferenceID(self, _role, _node_id):
            pass

    class LabelMap:
        def CreateDefaultDisplayNodes(self):
            pass

        def GetDisplayNode(self):
            return Display()

    class ColorTable:
        def GetID(self):
            return "color-table"

    class ImportedSegmentation:
        def GetNumberOfSegments(self):
            return 1

    class OutputSegmentation:
        def __init__(self):
            self.display = Display()

        def CreateDefaultDisplayNodes(self):
            pass

        def SetReferenceImageGeometryParameterFromVolumeNode(self, _source):
            pass

        def GetSegmentation(self):
            return ImportedSegmentation()

        def CreateClosedSurfaceRepresentation(self):
            pass

        def GetDisplayNode(self):
            return self.display

        def GetID(self):
            return "segmentation-run"

    backend_methods = _extract_methods(
        PYTHON / "dentobot_workflow" / "widget_backend_completion.py",
        "BackendCompletionWidgetMixin",
        {"_completeTeethSegmentation"},
        {
            "json": json,
            "logging": logging,
            "_": lambda message: message,
            "slicer": SimpleNamespace(),
        },
    )
    backend = backend_methods()
    source = SourceVolume()
    segmentation = OutputSegmentation()
    removed = []
    slicer_stub = backend_methods._completeTeethSegmentation.__globals__["slicer"]
    slicer_stub.mrmlScene = SimpleNamespace(
        GetNodeByID=lambda _node_id: source,
        GenerateUniqueName=lambda name: name,
        AddNewNodeByClass=lambda *_args: segmentation,
        RemoveNode=lambda node: removed.append(node),
    )
    slicer_stub.util = SimpleNamespace(loadLabelVolume=lambda *_args, **_kwargs: LabelMap())
    slicer_stub.modules = SimpleNamespace(
        segmentations=SimpleNamespace(
            logic=lambda: SimpleNamespace(
                ImportLabelmapToSegmentationNode=lambda *_args: None
            )
        )
    )
    slicer_stub.app = SimpleNamespace(processEvents=lambda: None)

    class Logic:
        def __init__(self):
            self.inventory_calls = []

        def validateTeethSegmentationReport(self, *_args, **_kwargs):
            pass

        def validateMatchingVolumeGeometry(self, *_args, **_kwargs):
            pass

        def validateLabelmapAgainstReport(self, *_args, **_kwargs):
            pass

        def createTeethColorTable(self, *_args, **_kwargs):
            return ColorTable()

        def applyTeethSegmentationReviewMetadata(self, *_args, **_kwargs):
            return ""

        def checkPulpInventory(self, selected, progress=None):
            self.inventory_calls.append(selected)
            return {"counts": {"associated": 2, "missing": 3, "ambiguous": 1, "cannot-evaluate": 0}}

        def getParameterNode(self):
            return SimpleNamespace(inspectedVolume=source)

        def createMissingPulpCandidates(self, *_args):
            pytest.fail("automatic inventory must not create masks")

    logic = Logic()
    statuses = []
    backend.logic = logic
    backend._parameterNode = object()
    backend.ui = SimpleNamespace(
        backendCollapsibleButton=SimpleNamespace(collapsed=False),
        segmentationReviewCollapsibleButton=SimpleNamespace(collapsed=True),
    )
    backend._setBackendStatus = lambda message, state: statuses.append((message, state))
    backend._updateBackendControls = lambda: None
    backend._updatePulpInventoryControls = lambda: None
    backend.selectInspectionContext = lambda *_args: None

    result_path = tmp_path / "result.json"
    output_path = tmp_path / "teeth.nii.gz"
    result_path.write_text(json.dumps({
        "status": "ok",
        "schemaVersion": "1.0",
        "metrics": {"segmentCount": 1},
        "labels": [{"id": 11, "name": "tooth_fdi11"}],
    }), encoding="utf-8")
    output_path.write_bytes(b"fixture")
    try:
        backend._completeTeethSegmentation(
            {
                "runId": "new-run-1",
                "sourceVolumeId": "source-volume",
                "device": "cpu",
                "paths": {"result": result_path, "output": output_path},
            },
            0,
        )
    finally:
        result_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)

    assert logic.inventory_calls == [segmentation]
    assert len(removed) == 2
    assert segmentation not in removed
    assert statuses[-1][1] == "success"
    assert "Pulp check: 2 associated, 3 missing, 1 need attention" in statuses[-1][0]
