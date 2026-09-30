"""Host checks for Case Foundation fingerprint cache identity and hashing."""

import ast
import hashlib
import json
import logging
from pathlib import Path
import time
from types import SimpleNamespace


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_case_foundation.py"
)


def _load_logic():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    mixin = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "CaseFoundationLogicMixin"
    )
    names = {
        "_cachedCaseFoundationFingerprint",
        "_caseFoundationSegmentBinaryArray",
        "caseFoundationSourceSegmentationFingerprint",
    }
    extracted = ast.ClassDef(
        name="CaseFoundationLogicMixin",
        bases=[],
        keywords=[],
        body=[
            node
            for node in mixin.body
            if isinstance(node, ast.FunctionDef) and node.name in names
        ],
        decorator_list=[],
    )
    namespace = {
        "hashlib": hashlib,
        "json": json,
        "logging": logging,
        "time": time,
        "canonical_json": lambda value: json.dumps(
            value, sort_keys=True, separators=(",", ":")
        ),
        "fingerprint": lambda value: hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "vtk": SimpleNamespace(vtkStringArray=FakeStringArray),
        "np": SimpleNamespace(ascontiguousarray=lambda value: value),
        "slicer": SimpleNamespace(
            vtkMRMLSegmentationNode=SimpleNamespace(
                GetReferenceImageGeometryReferenceRole=lambda: "reference-image"
            ),
            util=SimpleNamespace(
                arrayFromSegmentBinaryLabelmap=lambda node, segment_id: node
                .GetBinaryLabelmapInternalRepresentation(segment_id)
                .array
            ),
        ),
    }
    module = ast.fix_missing_locations(ast.Module(body=[extracted], type_ignores=[]))
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace["CaseFoundationLogicMixin"]


class FakeStringArray:
    def __init__(self):
        self.values = []

    def GetNumberOfValues(self):
        return len(self.values)

    def GetValue(self, index):
        return self.values[index]


class FakeArray:
    shape = (2, 1, 1)

    def __init__(self, data):
        self.data = data

    def tobytes(self):
        raise AssertionError("fingerprint hashing must not copy array bytes")


class FakeLabelmap:
    def __init__(self, data):
        self.array = FakeArray(data)
        self.mtime = 1

    def GetMTime(self):
        return self.mtime

    def touch(self, data):
        self.array.data = data
        self.mtime += 1


class FakeSegment:
    def __init__(self, name, labelmap):
        self.name = name
        self.labelmap = labelmap
        self.mtime = 1

    def GetMTime(self):
        return self.mtime

    def GetName(self):
        return self.name


class FakeSegmentation:
    def __init__(self, segment):
        self.segment = segment
        self.mtime = 1
        self.reference_geometry = "geometry-v1"

    def GetConversionParameter(self, _name):
        return self.reference_geometry

    def GetSegmentIDs(self, result):
        result.values = ["segment-1"]

    def GetSegment(self, _segment_id):
        return self.segment

    def GetMTime(self):
        return self.mtime


class FakeNode:
    def __init__(self, segmentation, segment):
        self.segmentation = segmentation
        self.segment = segment
        self.mtime = 1
        self.attributes = {
            "DENTOBOT.SegmentMetricsJson": '{"sourceName":"tooth_fdi11"}',
            "DENTOBOT.ReviewState": "Pending",
        }

    def GetSegmentation(self):
        return self.segmentation

    def GetID(self):
        return "segmentation-node"

    def GetMTime(self):
        return self.mtime

    def GetAttribute(self, name):
        return self.attributes.get(name)

    def SetAttribute(self, name, value):
        self.attributes[name] = value
        self.mtime += 1

    def GetNodeReference(self, _role):
        return None

    def GetBinaryLabelmapInternalRepresentation(self, _segment_id):
        return self.segment.labelmap


def test_source_fingerprint_cache_tracks_content_and_ignores_review_attributes():
    mixin = _load_logic()

    class Logic(mixin):
        def __init__(self):
            self.build_count = 0

        def getSegmentationReviewRecords(self, node):
            self.build_count += 1
            metrics = json.loads(
                node.GetAttribute("DENTOBOT.SegmentMetricsJson") or "{}"
            )
            return [{"segmentId": "segment-1", "sourceName": metrics["sourceName"]}]

        def describeSegmentForReview(self, source_name):
            return {"name": source_name}

    labelmap = FakeLabelmap(b"closed-mask")
    segment = FakeSegment("tooth_fdi11", labelmap)
    segmentation = FakeSegmentation(segment)
    node = FakeNode(segmentation, segment)
    logic = Logic()

    original = logic.caseFoundationSourceSegmentationFingerprint(node)
    assert logic.build_count == 1
    node.SetAttribute("DENTOBOT.ReviewState", "Reviewed")
    node.SetAttribute("DENTOBOT.ReviewUpdatedUtc", "later")
    assert logic.caseFoundationSourceSegmentationFingerprint(node) == original
    assert logic.build_count == 1

    node.SetAttribute(
        "DENTOBOT.SegmentMetricsJson", '{"sourceName":"tooth_fdi12"}'
    )
    changed_metrics = logic.caseFoundationSourceSegmentationFingerprint(node)
    assert changed_metrics != original
    assert logic.build_count == 2

    segment.mtime += 1
    logic.caseFoundationSourceSegmentationFingerprint(node)
    assert logic.build_count == 3

    segmentation.reference_geometry = "geometry-v2"
    changed_geometry = logic.caseFoundationSourceSegmentationFingerprint(node)
    assert changed_geometry != changed_metrics
    assert logic.build_count == 4

    labelmap.touch(b"opened-mask")
    changed_mask = logic.caseFoundationSourceSegmentationFingerprint(node)
    assert changed_mask != changed_geometry
    assert logic.build_count == 5
