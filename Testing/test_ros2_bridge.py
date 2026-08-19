"""Tests for DENTOROS2Bridge configuration and CLI helpers."""

from pathlib import Path
import sys
import time

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HELPER_DIRECTORY = REPOSITORY_ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPER_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HELPER_DIRECTORY))

from DENTOROS2Bridge import (
    CONTAINER_ROS_SETUP,
    CONTAINER_SAFE_PATH,
    DESCRIPTION_LAUNCH_CMD,
    ROS2_FIXED_FRAME,
    ROS2_JOINT_STATES_TOPIC,
    ROS2_MOVE_GROUP_EXISTS,
    ROS2_ROBOT_NAME,
    ROS2_JOINT_SI_ORDER,
    ROS2_SLICER_JOINT_COMMAND_TOPIC,
    ROS2_URDF_PARAM_NAME,
    ROS2_URDF_PARAM_NODE,
    SLICER_PYTHON_UNSET,
    _ros2_child_env,
    description_stack_running,
    ensure_ros2_slicer_modules,
    is_ros2_module_missing_message,
    is_ros2_runtime_unavailable_message,
    joint_si_vector,
    ros2_cli_available,
    ros2_node_list,
    ros2_unavailable_message,
    run_ros2_cli,
    slicer_motion_stack_ready,
    slicer_ros2_module_search_paths,
    slicer_ros2_runtime_status,
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
    assert "unset PYTHONHOME" in CONTAINER_ROS_SETUP
    assert SLICER_PYTHON_UNSET in DESCRIPTION_LAUNCH_CMD
    assert 'export PATH=' in CONTAINER_ROS_SETUP
    assert CONTAINER_SAFE_PATH in CONTAINER_ROS_SETUP
    assert "python-install" not in CONTAINER_SAFE_PATH
    assert "source /opt/ros/jazzy/setup.bash" in CONTAINER_ROS_SETUP


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
    assert is_ros2_runtime_unavailable_message(
        "ros2 CLI is not available in this Slicer process."
    )
    assert is_ros2_runtime_unavailable_message(message)


def test_ros2_child_env_strips_slicer_python_isolation(monkeypatch):
    monkeypatch.setenv("PYTHONHOME", "/opt/slicer/Slicer-SuperBuild/python-install")
    monkeypatch.setenv("PYTHONPATH", "/opt/slicer/fake")
    monkeypatch.setenv("PYTHONEXECUTABLE", "/opt/slicer/bin/python")
    monkeypatch.setenv("PYTHONNOUSERSITE", "1")
    monkeypatch.setenv(
        "PATH",
        "/opt/slicer/Slicer-SuperBuild/python-install/bin:/usr/bin",
    )
    monkeypatch.setenv("ROS_DOMAIN_ID", "73")
    env = _ros2_child_env()
    assert "PYTHONHOME" not in env
    assert "PYTHONPATH" not in env
    assert "PYTHONEXECUTABLE" not in env
    assert "PYTHONNOUSERSITE" not in env
    assert env["ROS_DOMAIN_ID"] == "73"
    assert env["PATH"] == CONTAINER_SAFE_PATH
    assert "python-install" not in env["PATH"]


def test_stale_node_list_cache_hides_slicer_publisher_until_forced(monkeypatch) -> None:
    import DENTOROS2Bridge as bridge

    bridge._NODE_LIST_CACHE = (
        time.monotonic(),
        True,
        ["/dentobot_robot_state_publisher", "/slicer"],
        "",
    )
    ready, message = slicer_motion_stack_ready()
    assert not ready
    assert "without" in message
    assert "dentobot_slicer_joint_state_publisher" in message

    def fake_node_list(*, force: bool = False):
        del force
        return True, [
            "/dentobot_robot_state_publisher",
            "/dentobot_slicer_joint_state_publisher",
            "/slicer",
        ], ""

    monkeypatch.setattr(bridge, "ros2_node_list", fake_node_list)
    ready, message = slicer_motion_stack_ready(force=True)
    assert ready
    assert message == ""
    bridge._NODE_LIST_CACHE = None


def test_connect_motion_control_forces_fresh_node_list() -> None:
    source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "DENTOROS2Bridge.py"
    ).read_text(encoding="utf-8")
    connect = source.split("def connect_dentobot_motion_control", 1)[1]
    connect = connect.split("\ndef ", 1)[0]
    assert "slicer_motion_stack_ready(force=True)" in connect
    assert "slicer_motion_stack_ready()" not in connect.replace(
        "slicer_motion_stack_ready(force=True)",
        "",
    )


def test_run_ros2_cli_uses_sourced_shell_without_slicer_python(monkeypatch):
    captured: dict = {}

    class Result:
        returncode = 0
        stdout = "usage: ros2\n"
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs.get("env")
        return Result()

    monkeypatch.setattr("DENTOROS2Bridge.subprocess.run", fake_run)
    monkeypatch.setenv("PYTHONHOME", "/opt/slicer/Slicer-SuperBuild/python-install")
    import DENTOROS2Bridge as bridge

    bridge._NODE_LIST_CACHE = None
    completed = run_ros2_cli(("--help",), timeout=8)
    assert completed.returncode == 0
    assert captured["command"][0] == "bash"
    assert captured["command"][1] == "-c"
    assert "unset PYTHONHOME" in captured["command"][2]
    assert "source /opt/ros/jazzy/setup.bash" in captured["command"][2]
    assert "ros2 --help" in captured["command"][2]
    assert "PYTHONHOME" not in captured["env"]
    bridge._NODE_LIST_CACHE = None
    Result.stdout = "/slicer\n"
    assert ros2_cli_available() is True
    assert "ros2 node list" in captured["command"][2]


def test_joint_si_vector_matches_tracked_urdf_order():
    from DENTORobotPlacement import joint_positions_si_from_display

    positions = joint_positions_si_from_display(10.0, 20.0, 30.0, 40.0, 50.0, 60.0)
    vector = joint_si_vector(positions)
    assert len(vector) == 6
    assert vector[0] == positions[ROS2_JOINT_SI_ORDER[0]]
    assert vector[-1] == positions[ROS2_JOINT_SI_ORDER[-1]]


def test_slicer_ros2_runtime_status_without_slicer_reports_launcher():
    ok, message = slicer_ros2_runtime_status()
    assert not ok
    assert "ROS2" in message or "launch-dentoworkflow.bash" in message


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


def test_get_ros2_logic_does_not_require_a_module_global_slicer():
    import DENTOROS2Bridge as bridge

    assert "slicer" not in vars(bridge)
    assert bridge.get_ros2_logic() is None
    assert "slicer" not in vars(bridge)
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
