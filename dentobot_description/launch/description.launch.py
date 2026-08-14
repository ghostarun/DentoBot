"""Launch the DENTOBOT description with simulated neutral joint states."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Create a visualization-only launch graph with no command interfaces."""
    package_share = Path(get_package_share_directory("dentobot_description"))
    urdf_path = package_share / "urdf" / "dentobot.urdf"
    rviz_path = package_share / "rviz" / "dentobot_description.rviz"
    robot_description = urdf_path.read_text(encoding="utf-8")
    use_rviz = LaunchConfiguration("use_rviz")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "use_rviz",
                default_value="true",
                description="Start RViz with the DENTOBOT description preset.",
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="dentobot_robot_state_publisher",
                output="screen",
                parameters=[{"robot_description": robot_description}],
            ),
            Node(
                package="dentobot_description",
                executable="neutral_joint_state_publisher",
                name="dentobot_neutral_joint_state_publisher",
                output="screen",
                parameters=[
                    {
                        "robot_description": robot_description,
                        "publish_rate_hz": 10.0,
                    }
                ],
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                name="dentobot_description_rviz",
                output="screen",
                arguments=["-d", str(rviz_path)],
                condition=IfCondition(use_rviz),
            ),
        ]
    )
