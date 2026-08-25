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


def test_gui_launcher_allocates_a_tty_only_for_interactive_terminals():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "Workspace/scripts/launch-dentoworkflow.bash").read_text(
        encoding="utf-8"
    )
    gui_block = launcher.split("Opening 3D Slicer directly", 1)[1]
    assert "docker_exec_options=()" in gui_block
    assert "if [[ -t 0 && -t 1 ]]" in gui_block
    assert "docker_exec_options=(-it)" in gui_block
    assert 'docker exec "${docker_exec_options[@]}"' in gui_block


def test_gui_launcher_bounds_simulation_process_group_cleanup():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "Workspace/scripts/launch-dentoworkflow.bash").read_text(
        encoding="utf-8"
    )
    gui_block = launcher.split("Opening 3D Slicer directly", 1)[1]
    assert (
        "setsid ros2 launch dentobot_moveit_config simulation.launch.py"
        in gui_block
    )
    assert 'kill -INT -- "-${stack_pid}"' in gui_block
    assert 'kill -TERM -- "-${stack_pid}"' in gui_block
    assert 'kill -KILL -- "-${stack_pid}"' in gui_block


def test_gui_launcher_ensures_docker_daemon_before_compose():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "Workspace/scripts/launch-dentoworkflow.bash").read_text(
        encoding="utf-8"
    )
    ensure_idx = launcher.index("ensure_docker_daemon")
    compose_idx = launcher.index('"${compose_command[@]}" config -q')
    assert "docker_daemon_ready()" in launcher
    assert "start_docker_daemon()" in launcher
    assert "enable_docker_daemon_on_boot()" in launcher
    assert "try_systemctl start docker.socket docker.service" in launcher
    assert "try_systemctl enable docker.socket docker.service" in launcher
    assert ensure_idx < compose_idx
    assert launcher.index("ensure_docker_daemon\n") < compose_idx
