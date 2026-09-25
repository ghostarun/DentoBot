"""Check SlicerROS2 robot meshes and MoveIt collision geometry without motion."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import slicer
import vtk

ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import DENTOROS2Bridge  # noqa: E402


EXPECTED_MODELS = {
    "link-1_model_0": "link-1",
    "link-2_model_0": "link-2",
    "link-3_model_0": "link-3",
    "link-4_model_0": "link-4",
    "link-5_model_0": "link-5",
    "pneumatic_spindle-Copy_model_0": "pneumatic_spindle-Copy",
    "burr_model_0": "burr",
}
PLANNING_GROUP = "dentobot_arm"
PROBE_NAME = "DENTOBOT_GEOMETRY_PROBE"


def process_events(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        ros_logic = slicer.util.getModuleLogic("ROS2")
        if ros_logic is not None:
            ros_logic.Spin()
        time.sleep(0.01)


def connect_robot(widget, bridge):
    deadline = time.monotonic() + 15.0
    message = "Simulation stack is not ready."
    while time.monotonic() < deadline:
        ready, message = bridge.ensure_slicer_ros2_runtime(require_stack=True)
        if ready:
            break
        process_events(0.1)
    else:
        raise RuntimeError(message)

    base = widget.logic.ensureRobotBaseTransform(widget._parameterNode.robotBaseTransform)
    widget._parameterNode.robotBaseTransform = base
    robot, error = bridge.connect_dentobot_motion_control(
        base,
        hide_mrml_robot=False,
        mrml_robot_models=[],
        open_motion_module=False,
        start_stack_if_needed=False,
        start_joint_command_stream=False,
    )
    if robot is None:
        raise RuntimeError(error)
    root_tip = robot.FindRootAndTipLinks()
    if not root_tip or root_tip[0] != "base_link":
        raise RuntimeError(f"Robot did not resolve from base_link: {root_tip}")
    return robot


def check_visual_models(robot):
    count = robot.GetNumberOfNodeReferences("model")
    if count != len(EXPECTED_MODELS):
        raise RuntimeError(f"Expected 7 SlicerROS2 visual models; found {count}.")

    actual = {}
    for index in range(count):
        model = robot.GetNthNodeReference("model", index)
        if model is None:
            raise RuntimeError(f"SlicerROS2 model reference {index} is empty.")
        name = str(model.GetName() or "")
        polydata = model.GetPolyData()
        points = polydata.GetNumberOfPoints() if polydata is not None else 0
        cells = polydata.GetNumberOfCells() if polydata is not None else 0
        if name not in EXPECTED_MODELS or name in actual:
            raise RuntimeError(f"Unexpected or duplicate robot model reference {name!r}.")
        if points == 0 or cells == 0:
            raise RuntimeError(f"Robot model {name!r} has empty polydata ({points}, {cells}).")
        actual[name] = {"link": EXPECTED_MODELS[name], "points": points, "cells": cells}

    if set(actual) != set(EXPECTED_MODELS):
        raise RuntimeError(f"Missing SlicerROS2 robot models: {sorted(set(EXPECTED_MODELS) - set(actual))}.")
    return [actual[name] for name in sorted(actual)]


def collision_pairs(robot):
    pairs = []
    for pair in robot.GetMoveItCollidingBodyPairs(PLANNING_GROUP, [0.0] * 5):
        fields = str(pair).split("\t", 1)
        if len(fields) == 2:
            pairs.append(fields)
    return pairs


def wait_for_probe_contact(robot, timeout=4.0):
    links = set(EXPECTED_MODELS.values())
    deadline = time.monotonic() + timeout
    last_pairs = []
    while time.monotonic() < deadline:
        last_pairs = collision_pairs(robot)
        for first, second in last_pairs:
            if first == PROBE_NAME and second in links:
                return [first, second]
            if second == PROBE_NAME and first in links:
                return [second, first]
        process_events(0.1)
    raise RuntimeError(f"No MoveIt probe-to-link collision; pairs={last_pairs}.")


def wait_for_probe_removed(robot, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(PROBE_NAME not in pair for pair in collision_pairs(robot)):
            return
        process_events(0.1)
    raise RuntimeError("MoveIt still reports contacts with the removed probe.")


def remove_probe(model, motion_logic, robot, additions_drained):
    if model is None:
        return
    try:
        if not additions_drained:
            # Drain AddMoveItObstacle's delayed republishes before sending REMOVE.
            process_events(1.1)
        if not motion_logic.RemoveMoveItObstacle(model, robot):
            raise RuntimeError("ROS2MotionControl could not remove the probe obstacle.")
        process_events(0.4)
        wait_for_probe_removed(robot, timeout=2.0)
    finally:
        if model.GetScene() is not None:
            slicer.mrmlScene.RemoveNode(model)


def run():
    bridge = DENTOROS2Bridge
    robot = motion_logic = probe = None
    owns_robot = False
    owns_adapter = False
    additions_drained = False
    report = None
    try:
        print("ROBOT_GEOMETRY step=initialize", flush=True)
        slicer.util.selectModule("DENTOWorkflow")
        slicer.app.processEvents()
        bridge = sys.modules.get("DENTOROS2Bridge", DENTOROS2Bridge)
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        if widget is None or widget._parameterNode is None:
            raise RuntimeError("DENTOWorkflow did not initialize its parameter node.")
        if bridge.find_ros2_robot_by_name(bridge.ROS2_ROBOT_NAME) is not None:
            raise RuntimeError("Start the smoke in a Slicer scene without an existing robot.")
        owns_adapter = True
        widget._setWorkflowStage(len(widget._workflowStageEntries()) - 1)
        slicer.app.processEvents()

        print("ROBOT_GEOMETRY step=connect", flush=True)
        owns_robot = True
        robot = connect_robot(widget, bridge)
        models = check_visual_models(robot)
        motion_logic = bridge.get_motion_control_logic()
        if motion_logic is None:
            raise RuntimeError("ROS2MotionControl logic is unavailable.")

        print("ROBOT_GEOMETRY step=static_collision_probe", flush=True)
        if slicer.mrmlScene.GetFirstNodeByName(PROBE_NAME) is not None:
            raise RuntimeError(f"Unexpected pre-existing model {PROBE_NAME}.")
        cube = vtk.vtkCubeSource()
        cube.SetBounds(-1000.0, 1000.0, -1000.0, 1000.0, -1000.0, 1000.0)
        cube.Update()
        probe = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", PROBE_NAME)
        probe.SetAndObservePolyData(cube.GetOutput())
        if not motion_logic.AddMoveItObstacle(probe, "base_link", robot):
            raise RuntimeError("Could not publish the temporary MoveIt geometry probe.")
        process_events(1.1)
        additions_drained = True
        contact = wait_for_probe_contact(robot)
        report = {
            "slicer_visual_models": models,
            "moveit_static_probe_contact": contact,
            "joint_positions": [0.0] * 5,
            "joint_command_stream": False,
            "case_loaded": False,
        }
    finally:
        bridge = sys.modules.get("DENTOROS2Bridge", bridge)
        try:
            remove_probe(probe, motion_logic, robot, additions_drained)
        finally:
            try:
                if owns_robot and bridge.find_ros2_robot_by_name(bridge.ROS2_ROBOT_NAME) is not None:
                    disconnected, error = bridge.disconnect_dentobot_motion_control([])
                    if not disconnected:
                        raise RuntimeError(f"Robot disconnect failed: {error}")
            finally:
                if owns_adapter:
                    bridge.shutdown_slicer_adapter()
    return report


try:
    result = run()
    print("DENTOBOT_ROBOT_GEOMETRY_PASS " + json.dumps(result, sort_keys=True), flush=True)
    slicer.util.exit(0)
except Exception as exc:
    print(f"DENTOBOT_ROBOT_GEOMETRY_FAILED: {exc}", file=sys.stderr, flush=True)
    slicer.util.exit(1)
