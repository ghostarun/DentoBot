"""Exercise DENTOWorkflow scene replacement with SlicerROS2 loaded."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import slicer


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import DENTOROS2Bridge  # noqa: E402


def process_events(seconds: float = 0.5) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        ros_logic = slicer.util.getModuleLogic("ROS2")
        if ros_logic is not None:
            ros_logic.Spin()
        time.sleep(0.01)


def assert_ros_subscriber_references_are_valid() -> None:
    ros_node = DENTOROS2Bridge.ensure_default_ros2_node_in_scene()
    if ros_node is None:
        raise RuntimeError("SlicerROS2 default node is detached from the active scene")
    for index in range(ros_node.GetNumberOfNodeReferences("subscriber")):
        subscriber = ros_node.GetNthNodeReference("subscriber", index)
        if subscriber is None or not subscriber.IsA("vtkMRMLROS2SubscriberNode"):
            raise RuntimeError("SlicerROS2 default node retained a stale subscriber reference")


def connect_robot(widget):
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        ready, _message = DENTOROS2Bridge.ensure_slicer_ros2_runtime(
            require_stack=True
        )
        if ready:
            break
        process_events(0.1)
    else:
        raise RuntimeError(_message)
    base_transform = widget.logic.ensureRobotBaseTransform(
        widget._parameterNode.robotBaseTransform
    )
    widget._parameterNode.robotBaseTransform = base_transform
    robot, error = DENTOROS2Bridge.connect_dentobot_motion_control(
        base_transform,
        hide_mrml_robot=False,
        mrml_robot_models=[],
        open_motion_module=False,
        start_stack_if_needed=False,
    )
    if robot is None:
        raise RuntimeError(error)
    root_tip = robot.FindRootAndTipLinks()
    if not root_tip or root_tip[0] != "base_link":
        raise RuntimeError(f"ROS robot did not resolve after warm connect: {root_tip}")
    return base_transform


def run() -> None:
    global DENTOROS2Bridge
    print("LIFECYCLE step=initialize", flush=True)
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    if widget is None or widget._parameterNode is None:
        raise RuntimeError("DENTOWorkflow widget did not initialize")
    widget._setWorkflowStage(len(widget._workflowStageEntries()) - 1)
    process_events(2.0)
    if DENTOROS2Bridge._status_subscriber is None:
        raise RuntimeError("DENTOBOT ROS status subscriber did not initialize in Step 6")
    if DENTOROS2Bridge._status_subscriber.GetSaveWithScene():
        raise RuntimeError("ROS status subscriber must not be serialized in case MRBs")
    assert_ros_subscriber_references_are_valid()

    print("LIFECYCLE step=first_connect", flush=True)
    base_transform = connect_robot(widget)
    widget.logic.setRobotBaseMountLocked(widget._parameterNode, True)
    if base_transform.GetAttribute("DENTOBOT.RobotBaseMountLocked") != "true":
        raise RuntimeError("Slicer 5.10 transform display lock was not applied")

    scene_path = Path(slicer.app.temporaryPath) / "dentobot-scene-lifecycle.mrb"
    sentinel = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLTextNode",
        "DENTOBOT scene lifecycle sentinel",
    )
    sentinel.SetText("scene replacement survived")
    if not slicer.util.saveScene(str(scene_path)):
        raise RuntimeError("Could not save scene lifecycle fixture")

    # The developer reload must synchronously tear down the Slicer-side robot
    # while preserving case geometry and the externally owned ROS stack.
    old_widget_id = id(widget)
    print("LIFECYCLE step=module_reload", flush=True)
    widget.ui.reloadDENTOWorkflowButton.click()
    process_events(4.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    if widget is None or id(widget) == old_widget_id:
        raise RuntimeError("DENTOWorkflow scripted module was not replaced")
    DENTOROS2Bridge = sys.modules["DENTOROS2Bridge"]
    if DENTOROS2Bridge.find_ros2_robot_by_name(DENTOROS2Bridge.ROS2_ROBOT_NAME):
        raise RuntimeError("ROS robot survived developer reload teardown")
    assert_ros_subscriber_references_are_valid()
    print("LIFECYCLE step=connect_after_reload", flush=True)
    connect_robot(widget)

    print("LIFECYCLE step=new_empty_case", flush=True)
    slicer.mrmlScene.Clear(0)
    process_events(1.0)
    if widget._parameterNode is None:
        raise RuntimeError("Parameter node was not rebound after New Empty Case")
    assert_ros_subscriber_references_are_valid()
    if DENTOROS2Bridge.find_ros2_robot_by_name(DENTOROS2Bridge.ROS2_ROBOT_NAME):
        raise RuntimeError("ROS robot survived New Empty Case teardown")

    # A second warm connection proves that no stale parameter/TF observer was
    # retained by the previous robot graph.
    print("LIFECYCLE step=connect_after_clear", flush=True)
    connect_robot(widget)
    disconnected, error = DENTOROS2Bridge.disconnect_dentobot_motion_control([])
    if not disconnected:
        raise RuntimeError(error)

    print("LIFECYCLE step=saved_scene_reload", flush=True)
    if not slicer.util.loadScene(str(scene_path), {"clear": True}):
        raise RuntimeError("Could not reload scene lifecycle fixture")
    process_events(2.0)
    reloaded = slicer.mrmlScene.GetFirstNodeByName(
        "DENTOBOT scene lifecycle sentinel"
    )
    if reloaded is None or reloaded.GetText() != "scene replacement survived":
        raise RuntimeError("Saved scene did not reload after adapter teardown")
    if widget._parameterNode is None:
        raise RuntimeError("Parameter node was not rebound after saved-scene load")
    if (
        widget._parameterNode.robotBaseTransform is None
        or not widget._parameterNode.robotBaseMountLocked
    ):
        raise RuntimeError("Locked Step 6 robot-base state was not restored")
    assert_ros_subscriber_references_are_valid()

    print("DENTOBOT_SCENE_LIFECYCLE_PASS")
    if DENTOROS2Bridge.find_ros2_robot_by_name(DENTOROS2Bridge.ROS2_ROBOT_NAME):
        DENTOROS2Bridge.disconnect_dentobot_motion_control([])
    DENTOROS2Bridge.shutdown_slicer_adapter()
    scene_path.unlink(missing_ok=True)
    slicer.util.exit(0)


try:
    run()
except Exception as exc:
    print(f"DENTOBOT_SCENE_LIFECYCLE_FAILED: {exc}", file=sys.stderr)
    DENTOROS2Bridge.shutdown_slicer_adapter()
    slicer.util.exit(1)
