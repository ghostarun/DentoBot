"""Launch the DENTOBOT description with simulated neutral joint states."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _joint_state_source(context, *, robot_description: str) -> list[Node]:
    """Select exactly one joint-state source, or leave it external."""
    mode = LaunchConfiguration("joint_state_mode").perform(context).strip().lower()
    if mode == "neutral":
        return [
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
            )
        ]
    if mode == "manual":
        coarse_clearance_mm = float(
            LaunchConfiguration("coarse_clearance_mm").perform(context)
        )
        return [
            Node(
                package="dentobot_description",
                executable="manual_joint_state_publisher",
                name="dentobot_manual_joint_state_publisher",
                output="screen",
                parameters=[
                    {
                        "robot_description": robot_description,
                        "coarse_clearance_mm": coarse_clearance_mm,
                    }
                ],
            )
        ]
    if mode == "slicer":
        return [
            Node(
                package="dentobot_description",
                executable="slicer_joint_state_publisher",
                name="dentobot_slicer_joint_state_publisher",
                output="screen",
                parameters=[
                    {
                        "robot_description": robot_description,
                        "publish_rate_hz": 10.0,
                        "command_topic": "dentobot/slicer_joint_positions",
                    }
                ],
            )
        ]
    if mode == "external":
        return []
    raise RuntimeError(
        "joint_state_mode must be one of: neutral, manual, slicer, or external; "
        f"received {mode!r}"
    )


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
            DeclareLaunchArgument(
                "joint_state_mode",
                default_value="neutral",
                description=(
                    "Joint-state source: neutral, manual, slicer, or external. "
                    "Manual starts the simulation-only slider window. "
                    "Slicer republishes Motion Control slider commands."
                ),
            ),
            DeclareLaunchArgument(
                "coarse_clearance_mm",
                default_value="5.0",
                description=(
                    "Draft AABB warning margin for non-adjacent link boxes. "
                    "Used only in manual mode."
                ),
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="dentobot_robot_state_publisher",
                output="screen",
                parameters=[{"robot_description": robot_description}],
            ),
            OpaqueFunction(
                function=_joint_state_source,
                kwargs={"robot_description": robot_description},
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
