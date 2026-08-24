"""Static contract tests for the in-Slicer DENTOBOT development reload."""

from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "DENTOWorkflow" / "DENTOWorkflow.py"
UI = ROOT / "DENTOWorkflow" / "Resources" / "UI" / "DENTOWorkflow.ui"
ROS_BRIDGE = (
    ROOT / "DENTOWorkflow" / "Resources" / "Python" / "DENTOROS2Bridge.py"
)


def test_reload_button_is_defined_in_the_persistent_workflow_ui() -> None:
    tree = ET.parse(UI)
    button = tree.find(".//widget[@name='reloadDENTOWorkflowButton']")
    assert button is not None
    text = button.find("./property[@name='text']/string")
    tooltip = button.find("./property[@name='toolTip']/string")
    assert text is not None and "Reload DENTOBOT" in (text.text or "")
    assert tooltip is not None and "without restarting Slicer" in (
        tooltip.text or ""
    )


def test_reload_uses_slicer_api_and_resets_adapter_owned_ros_nodes() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    handler = source.split("def onReloadDENTOWorkflowModule", 1)[1].split(
        "@staticmethod", 1
    )[0]
    reload_function = source.split("def _reloadDENTOWorkflowSources", 1)[1].split(
        "@staticmethod", 1
    )[0]
    assert "disconnect_dentobot_motion_control" in handler
    assert "shutdown_slicer_adapter()" in handler
    assert 'glob("DENTO*.py")' in reload_function
    assert 'reloadScriptedModule("DENTOWorkflow")' in reload_function
    assert "subprocess" not in handler


def test_scene_close_releases_slicer_side_ros_state_before_scene_rebind() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    handler = source.split("def onSceneStartClose", 1)[1].split(
        "def onSceneEndClose", 1
    )[0]
    parameter_release = handler.index("self.setParameterNode(None)")
    robot_disconnect = handler.index("disconnect_dentobot_motion_control")
    adapter_shutdown = handler.index("shutdown_slicer_adapter()")
    assert parameter_release < robot_disconnect < adapter_shutdown
    assert "self._step6MotionPreviewTimer.stop()" in handler


def test_ros_adapter_nodes_are_transient_across_scene_save_and_clear() -> None:
    workflow_source = WORKFLOW.read_text(encoding="utf-8")
    end_close = workflow_source.split("def onSceneEndClose", 1)[1].split(
        "def onSceneEndImport", 1
    )[0]
    end_import = workflow_source.split("def onSceneEndImport", 1)[1].split(
        "def onSceneStartSave", 1
    )[0]
    start_save = workflow_source.split("def onSceneStartSave", 1)[1].split(
        "def onSceneEndSave", 1
    )[0]
    bridge_source = ROS_BRIDGE.read_text(encoding="utf-8")
    assert "ensure_default_ros2_node_in_scene()" in end_close
    assert "QTimer.singleShot(0, self._initializeAfterSceneClose)" in end_close
    assert "mark_slicer_ros2_runtime_nodes_transient()" in end_import
    assert "mark_slicer_ros2_runtime_nodes_transient()" in start_save
    assert 'GetClassName().startswith("vtkMRMLROS2")' in bridge_source
    assert '"model", "goal_model", "goal_transform", "lookup", "parameter"' in bridge_source
    assert bridge_source.count("SaveWithSceneOff()") >= 4
    assert "_remove_ros2_node_reference" in bridge_source


def test_warm_lifecycle_never_queues_moveit_callbacks_with_native_wrappers() -> None:
    bridge_source = ROS_BRIDGE.read_text(encoding="utf-8")
    sync = bridge_source.split("def sync_moveit_obstacle_polydata", 1)[1].split(
        "def remove_stale_moveit_obstacle_proxies", 1
    )[0]
    disconnect = bridge_source.split("def disconnect_dentobot_motion_control", 1)[
        1
    ].split("def shutdown_slicer_adapter", 1)[0]
    assert "PublishMoveItObstacle" in sync
    assert "AddMoveItObstacle(" not in sync
    assert "RemoveMoveItObstacle(" not in disconnect
    assert "QTimer.singleShot" not in sync
    assert "QTimer.singleShot" not in disconnect


def test_robot_wait_does_not_query_root_before_urdf_parameter_arrives() -> None:
    bridge_source = ROS_BRIDGE.read_text(encoding="utf-8")
    waiter = bridge_source.split("def wait_for_robot_urdf", 1)[1].split(
        "def align_ros2_robot_to_base_transform", 1
    )[0]
    assert "IsParameterSet" in waiter
    assert waiter.index("IsParameterSet") < waiter.index(
        "root_and_tip = robot_node.FindRootAndTipLinks"
    )
    connect = bridge_source.split("def connect_dentobot_motion_control", 1)[1].split(
        "def _trajectory_time_seconds", 1
    )[0]
    assert "ros_logic.RemoveRobot" in connect
