"""Tests for DENTOROS2Bridge configuration and CLI helpers."""

from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HELPER_DIRECTORY = REPOSITORY_ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPER_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HELPER_DIRECTORY))

from DENTOROS2Bridge import (
    DESCRIPTION_LAUNCH_CMD,
    ROS2_FIXED_FRAME,
    ROS2_JOINT_STATES_TOPIC,
    ROS2_MOVE_GROUP_EXISTS,
    ROS2_ROBOT_NAME,
    ROS2_SLICER_JOINT_COMMAND_TOPIC,
    ROS2_URDF_PARAM_NAME,
    ROS2_URDF_PARAM_NODE,
    description_stack_running,
    ensure_ros2_slicer_modules,
    is_ros2_module_missing_message,
    ros2_node_list,
    ros2_unavailable_message,
    slicer_ros2_module_search_paths,
)


def test_ros2_bridge_constants_match_dentobot_launch():
    assert ROS2_ROBOT_NAME == "dentobot"
    assert ROS2_URDF_PARAM_NODE == "/dentobot_robot_state_publisher"
    assert ROS2_URDF_PARAM_NAME == "robot_description"
    assert ROS2_FIXED_FRAME == "base_link"
    assert ROS2_JOINT_STATES_TOPIC == "joint_states"
    assert ROS2_SLICER_JOINT_COMMAND_TOPIC == "dentobot/slicer_joint_positions"
    assert ROS2_MOVE_GROUP_EXISTS is False
    assert "dentobot_description" in DESCRIPTION_LAUNCH_CMD
    assert "joint_state_mode:=slicer" in DESCRIPTION_LAUNCH_CMD
    assert "use_rviz:=false" in DESCRIPTION_LAUNCH_CMD


def test_description_stack_running_reports_missing_node():
    ok, nodes, message = ros2_node_list()
    if not ok:
        assert message
        return
    running, hint = description_stack_running()
    if "/dentobot_robot_state_publisher" in nodes:
        assert running
        assert hint == ""
    else:
        assert not running
        assert "dentobot_robot_state_publisher" in hint


def test_ros2_unavailable_message_points_at_dentoworkflow_launcher():
    message = ros2_unavailable_message()
    assert "ROS2 Slicer module is not available" in message
    assert "launch-dentoworkflow.bash" in message
    assert "slicer_ros2_module" in message
    assert is_ros2_module_missing_message(message)
    assert is_ros2_module_missing_message(
        "The ROS2 Slicer module is not available. Use the dentobot SlicerROS2 container."
    )
    assert not is_ros2_module_missing_message(
        "ROS 2 node /dentobot_robot_state_publisher was not found."
    )


def test_slicer_ros2_module_search_paths_honors_env(tmp_path, monkeypatch):
    loadable = tmp_path / "qt-loadable-modules"
    loadable.mkdir()
    monkeypatch.setenv("SLICER_ROS2_MODULE_PATHS", str(loadable))
    monkeypatch.setattr(
        "DENTOROS2Bridge._ros2_pkg_prefix",
        lambda package="slicer_ros2_module": "",
    )
    paths = slicer_ros2_module_search_paths()
    assert loadable.resolve().as_posix() in paths


def test_ensure_ros2_slicer_modules_without_slicer_reports_launcher():
    ros_logic, motion_logic, error = ensure_ros2_slicer_modules()
    assert ros_logic is None
    assert motion_logic is None
    assert "launch-dentoworkflow.bash" in error


def test_dentoworkflow_launcher_merges_slicer_ros2_paths():
    launcher = (
        REPOSITORY_ROOT / "Workspace" / "scripts" / "launch-dentoworkflow.bash"
    )
    text = launcher.read_text(encoding="utf-8")
    assert "SLICER_ROS2_MODULE_PATHS" in text
    assert "slicer_ros2_module slicer.launch.py" in text
    assert "--additional-module-paths ${DENTOBOT_SLICER_MODULE_PATHS}" not in text
    assert "slicer.util.selectModule" in text
