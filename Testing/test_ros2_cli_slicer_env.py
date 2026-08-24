"""Regression test: embedded Slicer must not own or invoke the ROS CLI."""

from pathlib import Path


def test_ros_cli_is_confined_to_external_launchers():
    root = Path(__file__).resolve().parents[1]
    bridge = (root / "DENTOWorkflow/Resources/Python/DENTOROS2Bridge.py").read_text(
        encoding="utf-8"
    )
    assert "subprocess" not in bridge
    assert "run_ros2_cli" not in bridge
    launcher = (root / "Workspace/scripts/launch-dentoworkflow.bash").read_text(
        encoding="utf-8"
    )
    assert "ros2 launch dentobot_moveit_config simulation.launch.py" in launcher
    assert "/dentobot/simulation_status" in launcher


def test_gui_launcher_scopes_nounset_around_ros_generated_setup_files():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "Workspace/scripts/launch-dentoworkflow.bash").read_text(
        encoding="utf-8"
    )
    gui_block = launcher.split("Opening 3D Slicer directly", 1)[1]
    ros_source = gui_block.index("source /opt/ros/jazzy/setup.bash")
    overlay_source = gui_block.index(
        "source /workspace/ros2_ws/install/setup.bash"
    )
    nounset_disabled = gui_block.rfind("set +u", 0, ros_source)
    nounset_restored = gui_block.index("set -u", overlay_source)
    assert nounset_disabled >= 0
    assert nounset_disabled < ros_source < overlay_source < nounset_restored


def test_normal_gui_launch_restarts_the_dedicated_container():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "Workspace/scripts/launch-dentoworkflow.bash").read_text(
        encoding="utf-8"
    )
    reset = launcher.split('if docker inspect "${container_name}"', 1)[1].split(
        "container_runtime_safeguards", 1
    )[0]
    assert "if [[ ${check_only} == false ]]" in reset
    assert 'docker restart --timeout 30 "${container_name}"' in reset
    assert '"${compose_command[@]}" up -d' in reset
    assert "--force-recreate" not in reset
    assert "Existing DENTOBOT Slicer, ROS, MoveIt, and test processes" in reset
    assert "Save open Slicer scenes first" in reset
