"""Round-trip the real FDI 14 Step 6 package without restoring ROS runtime."""

from __future__ import annotations

import math
import sys
import time
import zipfile
from pathlib import Path

import slicer
import vtk


SOURCE = Path(
    "/workspace/data/Slicer_Saved/SampleStudy1/test1_6_FD14.mrb"
)
ROUNDTRIP = Path(slicer.app.temporaryPath) / "dentobot-test1-6-fd14-roundtrip.mrb"


def process_events(seconds: float = 1.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        logic = slicer.util.getModuleLogic("ROS2")
        if logic is not None:
            logic.Spin()
        time.sleep(0.01)


def nodes_with_attribute(class_name: str, key: str, value: str):
    return [
        node
        for node in slicer.util.getNodesByClass(class_name)
        if node.GetAttribute(key) == value
    ]


def capture_geometry() -> dict[str, object]:
    trajectories = nodes_with_attribute(
        "vtkMRMLMarkupsLineNode", "DENTOBOT.TrajectoryRole", "EntryToTarget"
    )
    if len(trajectories) != 1:
        raise RuntimeError(f"expected one trajectory, found {len(trajectories)}")
    trajectory = trajectories[0]
    points = []
    for index in range(2):
        point = [0.0, 0.0, 0.0]
        trajectory.GetNthControlPointPositionWorld(index, point)
        points.append(tuple(point))
    length = math.dist(*points)

    templates = nodes_with_attribute(
        "vtkMRMLModelNode", "DENTOBOT.ModelRole", "FinalPrintableTemplate"
    )
    if len(templates) != 1:
        raise RuntimeError(f"expected one final template, found {len(templates)}")
    template = templates[0]
    bounds = [0.0] * 6
    template.GetRASBounds(bounds)

    bases = nodes_with_attribute(
        "vtkMRMLLinearTransformNode", "DENTOBOT.TransformRole", "RobotBase"
    )
    if len(bases) != 1:
        raise RuntimeError(f"expected one robot base, found {len(bases)}")
    matrix = vtk.vtkMatrix4x4()
    bases[0].GetMatrixTransformToWorld(matrix)
    matrix_values = tuple(
        matrix.GetElement(row, column)
        for row in range(4)
        for column in range(4)
    )
    return {
        "trajectory_points": tuple(points),
        "trajectory_length_mm": length,
        "template_bounds_ras": tuple(bounds),
        "template_points": template.GetPolyData().GetNumberOfPoints(),
        "template_cells": template.GetPolyData().GetNumberOfCells(),
        "base_matrix": matrix_values,
    }


def assert_close(before: dict[str, object], after: dict[str, object]) -> None:
    if before.keys() != after.keys():
        raise RuntimeError("round-trip geometry keys changed")
    for key in before:
        first, second = before[key], after[key]
        if isinstance(first, tuple):
            flat_first = tuple(
                item for value in first for item in value
            ) if first and isinstance(first[0], tuple) else first
            flat_second = tuple(
                item for value in second for item in value
            ) if second and isinstance(second[0], tuple) else second
            if len(flat_first) != len(flat_second) or any(
                abs(float(a) - float(b)) > 1e-6
                for a, b in zip(flat_first, flat_second)
            ):
                raise RuntimeError(f"{key} changed across round trip")
        elif isinstance(first, float):
            if abs(first - second) > 1e-6:
                raise RuntimeError(f"{key} changed across round trip")
        elif first != second:
            raise RuntimeError(f"{key} changed across round trip")


def assert_runtime_is_not_restored(widget) -> None:
    if slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"):
        raise RuntimeError("saved case restored a SlicerROS2 robot")
    bases = nodes_with_attribute(
        "vtkMRMLLinearTransformNode", "DENTOBOT.TransformRole", "RobotBase"
    )
    if any(
        base.GetAttribute("DENTOBOT.Ros2MotionControlActive") == "true"
        for base in bases
    ):
        raise RuntimeError("saved case retained a false ROS-active flag")
    if widget._parameterNode.step6PlanningContextImported:
        raise RuntimeError("stale Step 4B/5C geometry remained motion-enabled")
    if len(widget.logic.robotModelNodes()) != 7:
        raise RuntimeError("persistent MRML fallback robot was not restored")


def run() -> None:
    slicer.util.selectModule("DENTOWorkflow")
    process_events()
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    if not slicer.util.loadScene(str(SOURCE), {"clear": True}):
        raise RuntimeError(f"could not load {SOURCE}")
    process_events(2.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    assert_runtime_is_not_restored(widget)
    before = capture_geometry()

    if not slicer.util.saveScene(str(ROUNDTRIP)):
        raise RuntimeError("could not save sanitized Step 6 round trip")
    with zipfile.ZipFile(ROUNDTRIP) as archive:
        mrml_name = next(name for name in archive.namelist() if name.endswith(".mrml"))
        mrml = archive.read(mrml_name).decode("utf-8")
    if "<ROS2" in mrml or "vtkMRMLROS2" in mrml:
        raise RuntimeError("round-trip MRB serialized ROS runtime nodes")
    if "DENTOBOT.Ros2MotionControlActive:true" in mrml:
        raise RuntimeError("round-trip MRB serialized the ROS-active flag")

    if not slicer.util.loadScene(str(ROUNDTRIP), {"clear": True}):
        raise RuntimeError("could not reload sanitized Step 6 round trip")
    process_events(2.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    assert_runtime_is_not_restored(widget)
    after = capture_geometry()
    assert_close(before, after)

    print(
        "DENTOBOT_STEP6_RESTORE_PASS "
        f"trajectory_length_mm={after['trajectory_length_mm']:.9f} "
        f"template_points={after['template_points']}"
    )
    slicer.mrmlScene.Clear(0)
    process_events()
    ROUNDTRIP.unlink(missing_ok=True)
    slicer.util.exit(0)


try:
    run()
except Exception as exc:
    print(f"DENTOBOT_STEP6_RESTORE_FAILED: {exc}", file=sys.stderr)
    slicer.util.exit(1)
