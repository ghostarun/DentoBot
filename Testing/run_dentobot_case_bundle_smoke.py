"""Round-trip the operator Step 5C and Step 6 scenes as .dentocase packages."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import time

import slicer
import vtk


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOCaseBundle import validate_case_bundle  # noqa: E402


SOURCES = (
    Path("/workspace/data/Slicer_Saved/SampleStudy1/test1_5C_FD14.mrb"),
    Path("/workspace/data/Slicer_Saved/SampleStudy1/test1_6_FD14.mrb"),
)


def process_events(seconds: float = 0.5) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        ros_logic = slicer.util.getModuleLogic("ROS2")
        if ros_logic is not None:
            ros_logic.Spin()
        time.sleep(0.01)


def scene_geometry_signature() -> dict[str, object]:
    trajectories = []
    for node in slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode"):
        if node.GetAttribute("DENTOBOT.TrajectoryRole") != "EntryToTarget":
            continue
        points = []
        for index in range(node.GetNumberOfDefinedControlPoints()):
            point = [0.0, 0.0, 0.0]
            node.GetNthControlPointPositionWorld(index, point)
            points.append(tuple(float(value) for value in point))
        trajectories.append((node.GetName(), tuple(points)))
    models = []
    for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
        role = node.GetAttribute("DENTOBOT.ModelRole")
        if role not in {"TargetDockingAssembly", "FinalPrintableTemplate"}:
            continue
        bounds = [0.0] * 6
        node.GetRASBounds(bounds)
        polydata = node.GetPolyData()
        models.append(
            (
                role,
                int(polydata.GetNumberOfPoints()) if polydata else 0,
                int(polydata.GetNumberOfCells()) if polydata else 0,
                tuple(float(value) for value in bounds),
            )
        )
    bases = []
    for node in slicer.util.getNodesByClass("vtkMRMLLinearTransformNode"):
        if node.GetAttribute("DENTOBOT.TransformRole") != "RobotBase":
            continue
        matrix = vtk.vtkMatrix4x4()
        node.GetMatrixTransformToWorld(matrix)
        bases.append(
            tuple(
                float(matrix.GetElement(row, column))
                for row in range(4)
                for column in range(4)
            )
        )
    return {
        "trajectories": tuple(sorted(trajectories)),
        "models": tuple(sorted(models)),
        "bases": tuple(bases),
    }


def assert_signature_close(before: object, after: object, path: str = "scene") -> None:
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        if not math.isclose(float(before), float(after), abs_tol=1e-6):
            raise RuntimeError(f"{path} changed: {before} != {after}")
        return
    if isinstance(before, (tuple, list)) and isinstance(after, (tuple, list)):
        if len(before) != len(after):
            raise RuntimeError(f"{path} length changed")
        for index, (left, right) in enumerate(zip(before, after)):
            assert_signature_close(left, right, f"{path}[{index}]")
        return
    if isinstance(before, dict) and isinstance(after, dict):
        if before.keys() != after.keys():
            raise RuntimeError(f"{path} keys changed")
        for key in before:
            assert_signature_close(before[key], after[key], f"{path}.{key}")
        return
    if before != after:
        raise RuntimeError(f"{path} changed: {before!r} != {after!r}")


def assert_no_ros_runtime(widget) -> None:
    if slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"):
        raise RuntimeError("case package restored a live ROS robot")
    for node in slicer.util.getNodesByClass("vtkMRMLLinearTransformNode"):
        if node.GetAttribute("DENTOBOT.Ros2MotionControlActive") == "true":
            raise RuntimeError("case package restored a ROS-active flag")
    if widget._caseBundleRobotProfileCompatible is not True:
        raise RuntimeError("case package robot profile did not match this runtime")


def run() -> None:
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    results = []
    for source in SOURCES:
        if not source.is_file():
            raise RuntimeError(f"operator scene is missing: {source}")
        if not slicer.util.loadScene(str(source), {"clear": True}):
            raise RuntimeError(f"could not load operator scene: {source}")
        process_events(1.0)
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        before = scene_geometry_signature()
        location_before = (
            slicer.mrmlScene.GetURL() or "",
            slicer.mrmlScene.GetRootDirectory() or "",
        )
        bundle = Path(slicer.app.temporaryPath) / f"{source.stem}.dentocase"
        inspection = widget._createCaseBundle(bundle)
        location_after_save = (
            slicer.mrmlScene.GetURL() or "",
            slicer.mrmlScene.GetRootDirectory() or "",
        )
        if location_after_save != location_before:
            raise RuntimeError("case-package save changed the live scene location")
        validate_case_bundle(inspection.path)
        widget._openCaseBundle(inspection.path)
        process_events(1.0)
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        if slicer.mrmlScene.GetURL():
            raise RuntimeError("package load retained the temporary MRB save target")
        if Path(slicer.mrmlScene.GetRootDirectory()) != inspection.path.parent:
            raise RuntimeError("package load did not retain the package directory")
        assert_no_ros_runtime(widget)
        after = scene_geometry_signature()
        assert_signature_close(before, after)
        freshness = widget.logic.step6PlanningContextFreshnessIssues(
            widget._parameterNode
        )
        if freshness and widget._parameterNode.step6PlanningContextImported:
            raise RuntimeError("stale Step 6 context remained enabled")
        results.append(
            {
                "source": source.name,
                "bundleBytes": inspection.path.stat().st_size,
                "trajectoryCount": len(after["trajectories"]),
                "modelCount": len(after["models"]),
                "freshnessIssueCount": len(freshness),
                "freshnessIssues": tuple(freshness),
            }
        )
        bundle.unlink(missing_ok=True)

    print(f"DENTOBOT_CASE_BUNDLE_PASS {results}", flush=True)
    slicer.mrmlScene.Clear(0)
    process_events()
    slicer.util.exit(0)


try:
    run()
except Exception as exc:
    print(f"DENTOBOT_CASE_BUNDLE_FAILED: {exc}", file=sys.stderr, flush=True)
    slicer.util.exit(1)
