"""Pure regression checks for the Case Foundation cache and stale-pose guard."""

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
        if isinstance(node, ast.ClassDef) and node.name == "CaseFoundationLogicMixin"
    )
    methods = {
        "_cachedCaseFoundationFingerprint",
        "_caseFoundationSegmentBinaryArray",
        "caseFoundationSourceSegmentationFingerprint",
        "requireCaseFoundationPose",
    }
    extracted = ast.ClassDef(
        name="CaseFoundationLogicMixin",
        bases=[],
        keywords=[],
        body=[
            node
            for node in mixin.body
            if isinstance(node, ast.FunctionDef) and node.name in methods
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
        "_": lambda value: value,
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
    shape = (1, 1, 1)

    def __init__(self, data):
        self.data = data
        self.mtime = 1

    def GetMTime(self):
        return self.mtime

    def touch(self, data):
        self.data = data
        self.mtime += 1

    def tobytes(self):
        return self.data


class FakeLabelmap:
    def __init__(self, array):
        self.array = array
        self.mtime = 1

    def GetMTime(self):
        return self.mtime

    def touch(self, data):
        self.array.touch(data)
        self.mtime += 1


class FakeSegment:
    def __init__(self, name, array):
        self.name = name
        self.labelmap = FakeLabelmap(array)
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
        self.attributes = {
            "DENTOBOT.SegmentMetricsJson": '{"semantic":{"version":1}}',
            "DENTOBOT.ReviewState": "Pending",
        }
        self.mtime = 1

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


def test_fingerprint_cache_tracks_source_inputs_but_ignores_review_attributes():
    mixin = _load_logic()

    class Logic(mixin):
        def __init__(self):
            self.build_count = 0

        def getSegmentationReviewRecords(self, _node):
            self.build_count += 1
            return [{"segmentId": "segment-1", "sourceName": "tooth_fdi11"}]

        def describeSegmentForReview(self, source_name):
            return {"name": source_name}

    array = FakeArray(b"closed-mask")
    segment = FakeSegment("tooth_fdi11", array)
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
        "DENTOBOT.SegmentMetricsJson", '{"semantic":{"version":2}}'
    )
    logic.caseFoundationSourceSegmentationFingerprint(node)
    assert logic.build_count == 2

    segment.mtime += 1
    logic.caseFoundationSourceSegmentationFingerprint(node)
    assert logic.build_count == 3

    segment.labelmap.touch(b"opened-mask")
    changed = logic.caseFoundationSourceSegmentationFingerprint(node)
    assert logic.build_count == 4
    assert changed != original


def test_explicitly_stale_case_foundation_pose_skips_full_evaluation():
    mixin = _load_logic()

    class Logic(mixin):
        def __init__(self):
            self.evaluation_count = 0

        def isStep6CaseJawTransformNode(self, transform):
            return transform is not None

        def evaluateCaseFoundationEligibility(self, _parameter_node):
            self.evaluation_count += 1
            raise AssertionError("full eligibility evaluation should not run")

    class Transform:
        def GetAttribute(self, name):
            return {
                "DENTOBOT.GeometryState": "Stale",
                "DENTOBOT.StaleReason": "source changed",
            }.get(name)

    logic = Logic()
    parameter_node = SimpleNamespace(step6CaseJawTransform=Transform())

    try:
        logic.requireCaseFoundationPose(parameter_node)
    except ValueError as error:
        assert str(error) == "source changed"
    else:
        raise AssertionError("stale pose must fail closed")
    assert logic.evaluation_count == 0
