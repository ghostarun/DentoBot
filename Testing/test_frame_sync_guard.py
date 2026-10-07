"""L1 checks for world-frame polydata access and raw-read guards."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTING_ROOT = PROJECT_ROOT / "Testing"
SOURCE_ROOT = PROJECT_ROOT / "DENTOWorkflow" / "Resources" / "Python"

# Keep imports anchored to this checkout when pytest is launched from elsewhere.
for _resource_path in (str(TESTING_ROOT), str(SOURCE_ROOT)):
    if _resource_path not in sys.path:
        sys.path.insert(0, _resource_path)


RAW_READ_ALLOWLIST = {
    # WHY: this helper applies full world pose, then inverse jaw opening, to
    # compute intentional closed-jaw provenance rather than audit world geometry.
    ("step6_feasibility_advisor_runner.py", "OrderedAdvisorRunner", "_template_poly_jaw_local"),
}

FORBIDDEN_READS = {
    "GetPolyData",
    "GetClosedSurfaceRepresentation",
    "GetRepresentation",
    "GetClosedSurfaceInternalRepresentation",
}


def _vtk():
    return pytest.importorskip("vtk")


def _point_polydata(vtk, point=(1.0, 2.0, 3.0)):
    points = vtk.vtkPoints()
    points.InsertNextPoint(*point)
    points.InsertNextPoint(point[0] + 1.0, point[1], point[2])
    points.InsertNextPoint(point[0], point[1] + 1.0, point[2])
    triangle = vtk.vtkTriangle()
    triangle.GetPointIds().SetId(0, 0)
    triangle.GetPointIds().SetId(1, 1)
    triangle.GetPointIds().SetId(2, 2)
    triangles = vtk.vtkCellArray()
    triangles.InsertNextCell(triangle)
    polydata = vtk.vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetPolys(triangles)
    return polydata


class _TransformNode:
    """Small MRML-like node whose local transform is nested under its parent."""

    def __init__(self, local_transform, parent=None):
        self.local_transform = local_transform
        self.parent = parent

    def GetParentTransformNode(self):
        return _TransformNode(self.local_transform, self.parent)

    def GetTransformToWorld(self, world_transform):
        # For pre-multiply composition, append ancestors first so the resulting
        # world matrix is root * parent * local.
        if self.parent is not None:
            self.parent.GetTransformToWorld(world_transform)
        world_transform.PreMultiply()
        world_transform.Concatenate(self.local_transform)


class _ModelNode(_TransformNode):
    def __init__(self, polydata, local_transform, parent=None):
        super().__init__(local_transform, parent)
        self.polydata = polydata

    def GetPolyData(self, destination=None):
        if destination is not None:
            destination.DeepCopy(self.polydata)
        return self.polydata


class _FakeSegmentation:
    def __init__(self, surfaces):
        self.surfaces = surfaces

    def GetSegment(self, segment_id):
        return object() if segment_id in self.surfaces else None


class _SegmentationNode(_TransformNode):
    def __init__(self, surfaces, local_transform, parent=None):
        super().__init__(local_transform, parent)
        self.surfaces = surfaces
        self.segmentation = _FakeSegmentation(surfaces)
        self.create_calls = 0

    def GetSegmentation(self):
        return self.segmentation

    def CreateClosedSurfaceRepresentation(self):
        self.create_calls += 1
        return True

    def GetClosedSurfaceRepresentation(self, segment_id, destination):
        source = self.surfaces.get(segment_id)
        if source is None:
            return False
        destination.DeepCopy(source)
        return True


def _nested_transforms(vtk):
    """Return scale(2) <- translate(5) <- translate(3), plus its expected x."""
    root = vtk.vtkTransform()
    root.Scale(2.0, 2.0, 2.0)
    parent = vtk.vtkTransform()
    parent.Translate(5.0, 0.0, 0.0)
    child = vtk.vtkTransform()
    child.Translate(3.0, 0.0, 0.0)
    root_node = _TransformNode(root)
    parent_node = _TransformNode(parent, root_node)
    model_node = _TransformNode(child, parent_node)
    # The input point x=1 becomes 1+3+5=9, then the root scale makes x=18.
    return model_node, 18.0


def test_model_world_polydata_applies_nested_transforms_without_mutating_source():
    vtk = _vtk()
    frame_sync = importlib.import_module("dentobot_workflow.frame_sync")
    source = _point_polydata(vtk)
    hierarchy, expected_x = _nested_transforms(vtk)
    model = _ModelNode(source, hierarchy.local_transform, hierarchy.parent)

    world = frame_sync.model_world_polydata(model)

    assert world is not source
    assert world.GetPoint(0) == pytest.approx((expected_x, 4.0, 6.0))
    world.GetPoints().SetPoint(0, 999.0, 999.0, 999.0)
    assert source.GetPoint(0) == pytest.approx((1.0, 2.0, 3.0))


def test_segment_world_polydata_creates_surface_and_applies_nested_transforms():
    vtk = _vtk()
    frame_sync = importlib.import_module("dentobot_workflow.frame_sync")
    source = _point_polydata(vtk)
    hierarchy, expected_x = _nested_transforms(vtk)
    segmentation = _SegmentationNode(
        {"jaw": source}, hierarchy.local_transform, hierarchy.parent
    )

    world = frame_sync.segment_world_polydata(segmentation, "jaw")

    assert segmentation.create_calls == 1
    assert world is not source
    assert world.GetPoint(0) == pytest.approx((expected_x, 4.0, 6.0))
    world.GetPoints().SetPoint(0, 999.0, 999.0, 999.0)
    assert source.GetPoint(0) == pytest.approx((1.0, 2.0, 3.0))


@pytest.mark.parametrize(
    "surfaces,segment_id",
    [({}, "missing"), ({"empty": None}, "empty")],
)
def test_segment_world_polydata_rejects_missing_or_empty_surface(surfaces, segment_id):
    vtk = _vtk()
    frame_sync = importlib.import_module("dentobot_workflow.frame_sync")
    prepared = {
        key: (_point_polydata(vtk) if value is not None else vtk.vtkPolyData())
        for key, value in surfaces.items()
    }
    segmentation = _SegmentationNode(prepared, vtk.vtkTransform())

    with pytest.raises((ValueError, RuntimeError)):
        frame_sync.segment_world_polydata(segmentation, segment_id)


def _raw_read_violations(source: str, filename: str):
    tree = ast.parse(source, filename=filename)
    violations = []
    class_stack: list[str] = []
    function_stack: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node):
            class_stack.append(node.name)
            self.generic_visit(node)
            class_stack.pop()

        def visit_FunctionDef(self, node):
            function_stack.append(node.name)
            self.generic_visit(node)
            function_stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_READS:
                location = (
                    Path(filename).name,
                    class_stack[-1] if class_stack else None,
                    function_stack[-1] if function_stack else None,
                )
                if location not in RAW_READ_ALLOWLIST:
                    violations.append((node.lineno, node.func.attr, location))
            self.generic_visit(node)

    Visitor().visit(tree)
    return violations


def _diagnostic_sources():
    candidates = set(TESTING_ROOT.glob("step6_*audit*.py"))
    candidates.update(TESTING_ROOT.glob("step6_feasibility_advisor_runner.py"))
    candidates.update(TESTING_ROOT.glob("step6_frame_sync*.py"))
    candidates.update(TESTING_ROOT.glob("step6_scene_mesh_compare.py"))
    candidates.update(TESTING_ROOT.glob("step6_frame_sync_known_answers.py"))
    candidates.update(TESTING_ROOT.glob("*frame_sync*audit*.py"))
    candidates.update(TESTING_ROOT.glob("*audit*frame_sync*.py"))
    candidates.update(PROJECT_ROOT.rglob("base_diagnosis.py"))
    return sorted(path for path in candidates if path.is_file())


def test_diagnostics_use_world_frame_accessors_for_surface_reads():
    sources = _diagnostic_sources()
    assert sources, "expected diagnostic source files to scan"
    violations = []
    for path in sources:
        violations.extend(
            (str(path.relative_to(PROJECT_ROOT)), *violation)
            for violation in _raw_read_violations(path.read_text(encoding="utf-8"), path.name)
        )
    assert not violations, f"raw polydata or segment-surface reads remain: {violations}"


def test_raw_read_allowlist_is_limited_to_the_named_helper():
    allowed = """
class OrderedAdvisorRunner:
    def _template_poly_jaw_local(self, node):
        return node.GetPolyData()
"""
    disallowed = """
class OrderedAdvisorRunner:
    def _template_poly_jaw_local(self, node):
        return node.GetPolyData()
    def other(self, node):
        return node.GetPolyData()
"""
    accessor = "world = model_world_polydata(node)\n"

    assert _raw_read_violations(allowed, "step6_feasibility_advisor_runner.py") == []
    assert len(_raw_read_violations(disallowed, "step6_feasibility_advisor_runner.py")) == 1
    assert _raw_read_violations(accessor, "step6_frame_audit.py") == []


def test_step6_audit_reexports_shared_accessors():
    shared = importlib.import_module("dentobot_workflow.frame_sync")
    audit = importlib.import_module("step6_frame_audit")

    assert audit.model_world_polydata is shared.model_world_polydata
    assert audit.segment_world_polydata is shared.segment_world_polydata
