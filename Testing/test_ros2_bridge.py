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
    ros2_node_list,
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
