"""Externally owned, simulation-only DENTOBOT description and MoveIt stack."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description() -> LaunchDescription:
    description_share = Path(get_package_share_directory("dentobot_description"))
    urdf_path = description_share / "urdf" / "dentobot.urdf"

    moveit_config = (
        MoveItConfigsBuilder("dentobot", package_name="dentobot_moveit_config")
        .robot_description(file_path=str(urdf_path))
        .robot_description_semantic(file_path="config/dentobot.srdf")
        .robot_description_kinematics(file_path="config/kinematics.yaml")
        .joint_limits(file_path="config/joint_limits.yaml")
        .planning_pipelines(pipelines=["ompl"])
        .to_moveit_configs()
    )

    robot_description = moveit_config.robot_description["robot_description"]
    return LaunchDescription(
        [
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="dentobot_robot_state_publisher",
                output="screen",
                parameters=[{"robot_description": robot_description}],
            ),
            Node(
                package="dentobot_description",
                executable="slicer_joint_state_publisher",
                name="dentobot_slicer_joint_state_publisher",
                output="screen",
                parameters=[
                    {
                        "robot_description": robot_description,
                        "publish_rate_hz": 20.0,
                        "command_topic": "/dentobot/validated_joint_positions",
                    }
                ],
            ),
            Node(
                package="moveit_ros_move_group",
                executable="move_group",
                name="move_group",
                output="screen",
                parameters=[
                    moveit_config.to_dict(),
                    {
                        "allow_trajectory_execution": False,
                        "default_robot_padding": 0.005,
                        "publish_robot_description": True,
                        "publish_robot_description_semantic": True,
                        "publish_planning_scene": True,
                    },
                ],
            ),
            Node(
                package="dentobot_moveit_config",
                executable="collision_guard",
                name="dentobot_collision_guard",
                output="screen",
                parameters=[
                    moveit_config.to_dict(),
                    {
                        "group_name": "dentobot_arm",
                        "raw_command_topic": "/dentobot/slicer_joint_positions",
                        "accepted_command_topic": "/dentobot/validated_joint_positions",
                        "status_topic": "/dentobot/joint_command_status",
                        "minimum_clearance_m": 0.005,
                        "maximum_revolute_step_rad": 0.017453292519943295,
                        "maximum_prismatic_step_m": 0.0005,
                        "maximum_interpolation_samples": 1000,
                    },
                ],
            ),
            Node(
                package="dentobot_description",
                executable="simulation_status_publisher",
                name="dentobot_simulation_status_publisher",
                output="screen",
            ),
        ]
    )
