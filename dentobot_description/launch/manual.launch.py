"""Launch the DENTOBOT model with RViz and manual joint sliders."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description() -> LaunchDescription:
    """Start the simulation-only manual articulation workspace."""
    package_share = Path(get_package_share_directory("dentobot_description"))
    description_launch = package_share / "launch" / "description.launch.py"
    use_rviz = LaunchConfiguration("use_rviz")
    coarse_clearance_mm = LaunchConfiguration("coarse_clearance_mm")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "use_rviz",
                default_value="true",
                description="Start RViz beside the manual joint slider window.",
            ),
            DeclareLaunchArgument(
                "coarse_clearance_mm",
                default_value="5.0",
                description="Draft non-adjacent link AABB warning margin in mm.",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(str(description_launch)),
                launch_arguments={
                    "joint_state_mode": "manual",
                    "use_rviz": use_rviz,
                    "coarse_clearance_mm": coarse_clearance_mm,
                }.items(),
            ),
        ]
    )
