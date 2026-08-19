"""SlicerROS2 bridge helpers for DENTOBOT Step 6 motion-control integration.

Requires the ``ROS2`` and ``ROS2MotionControl`` Slicer modules (Jazzy
SlicerROS2 container).  This module does not command hardware.
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence, Tuple

# DENTOBOT ``description.launch.py`` node and parameter names.
ROS2_ROBOT_NAME = "dentobot"
ROS2_URDF_PARAM_NODE = "/dentobot_robot_state_publisher"
ROS2_URDF_PARAM_NAME = "robot_description"
ROS2_FIXED_FRAME = "base_link"
ROS2_TF_PREFIX = ""
ROS2_JOINT_STATES_TOPIC = "joint_states"
ROS2_MOVE_GROUP_EXISTS = False
ROS2_SLICER_JOINT_COMMAND_TOPIC = "dentobot/slicer_joint_positions"
ROS2_SLICER_JOINT_NODE = "dentobot_slicer_joint_state_publisher"
ROS2_COMPETING_JOINT_NODES = frozenset(
    {
        "dentobot_neutral_joint_state_publisher",
        "dentobot_manual_joint_state_publisher",
    }
)
ROS2_SLICER_JOINT_PUBLISH_INTERVAL_MS = 100

ROS2_ROBOT_NODE_ATTRIBUTE = "DENTOBOT.Ros2RobotName"
ROS2_MOTION_ACTIVE_ATTRIBUTE = "DENTOBOT.Ros2MotionControlActive"
ROS2_SLICER_JOINT_PUBLISHER_ATTRIBUTE = "DENTOBOT.SlicerJointCommandPublisher"
ROS2_DEFAULT_SLICER_NODE = "slicer"
ROS2_JOINT_SI_ORDER = (
    "link-1_Revolute-1",
    "link-2_Slider-2",
    "link-3_Revolute-3",
    "link-4_Slider-4",
    "link-5_Revolute-5",
    "pneumatic_spindle-Copy_Revolute-6",
)
_NODE_LIST_CACHE: Optional[tuple[float, bool, list[str], str]] = None
_NODE_LIST_CACHE_SEC = 1.5

# Slicer sets PYTHONHOME to its SuperBuild interpreter and puts
# python-install/bin first on PATH. The ros2 CLI shebang is /usr/bin/python3;
# inheriting PYTHONHOME makes that process load Slicer stdlib and fail
# (librcl_action.so / rclpy). Launch children use ``/usr/bin/env python3``,
# so a Slicer-first PATH starts the Python joint publisher with Slicer
# Python (no PyYAML) while C++ robot_state_publisher still comes up.
# Reset PATH, unset those variables, then source the overlay.
CONTAINER_SAFE_PATH = (
    "/opt/ros/jazzy/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
)
SLICER_PYTHON_UNSET = (
    "unset PYTHONHOME PYTHONPATH PYTHONEXECUTABLE PYTHONNOUSERSITE && "
    f'export PATH="{CONTAINER_SAFE_PATH}"'
)
CONTAINER_ROS_SETUP = (
    f"{SLICER_PYTHON_UNSET} && "
    "source /opt/ros/jazzy/setup.bash && "
    "source /workspace/ros2_ws/install/setup.bash"
)
DESCRIPTION_LAUNCH_CMD = (
    f"{CONTAINER_ROS_SETUP} && "
    "ros2 launch dentobot_description description.launch.py "
    "use_rviz:=false joint_state_mode:=slicer"
)
_SLICER_PYTHON_ENV_KEYS = (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONEXECUTABLE",
    "PYTHONNOUSERSITE",
)

PROCESS_EVENT_POLL_SEC = 0.2
URDF_WAIT_TIMEOUT_SEC = 30.0
STACK_START_WAIT_SEC = 8.0

ROS2_MODULE_NAME = "ROS2"
ROS2_MOTION_MODULE_NAME = "ROS2MotionControl"
SLICER_ROS2_PACKAGE = "slicer_ros2_module"
_DEFAULT_SLICER_ROS2_PREFIXES = (
    "/workspace/ros2_ws/install/slicer_ros2_module",
)
_SLICER_ROS2_RELATIVE_MODULE_DIRS = (
    "lib/Slicer-5.10/qt-loadable-modules",
    "lib/Slicer-5.10/qt-scripted-modules",
    "share/Slicer-5.10/qt-loadable-modules",
    "share/Slicer-5.10/qt-scripted-modules",
)
ROS2_UNAVAILABLE_MESSAGE = (
    "The ROS2 Slicer module is not available in this Slicer process. "
    "Close Slicer and start it with ./scripts/launch-dentoworkflow.bash "
    "(dentobot-slicerros2 + ros2 launch slicer_ros2_module slicer.launch.py). "
    "Host or Windows Slicer cannot load SlicerROS2."
)

_slicer_joint_command_timer = None
_slicer_joint_command_publisher = None


def _ros2_child_env() -> dict[str, str]:
    """Environment for ros2 CLI child processes launched from Slicer."""
    env = os.environ.copy()
    for key in _SLICER_PYTHON_ENV_KEYS:
        env.pop(key, None)
    env["PATH"] = CONTAINER_SAFE_PATH
    return env


def _terminate_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            return


def _log_tail(path: str, limit: int = 24) -> str:
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-limit:]).strip()


def slicer_mode_description_launch_pids() -> list[int]:
    """Return PIDs of ``ros2 launch dentobot_description`` slicer-mode stacks."""
    try:
        completed = subprocess.run(
            ["ps", "-eo", "pid=,args="],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    pids: list[int] = []
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if "ros2 launch dentobot_description" not in stripped:
            continue
        if "joint_state_mode:=slicer" not in stripped:
            continue
        pid_text = stripped.split(None, 1)[0]
        try:
            pids.append(int(pid_text))
        except ValueError:
            continue
    return pids


def stop_incomplete_slicer_description_launch() -> str:
    """Stop a slicer-mode launch that brought up RSP without the Python publisher."""
    if competing_joint_source_message(force=True):
        return ""
    if slicer_motion_stack_ready(force=True)[0]:
        return ""
    if not description_stack_running(force=True)[0]:
        return ""
    pids = slicer_mode_description_launch_pids()
    if not pids:
        return ""
    for pid in pids:
        _terminate_process_group(pid)
    _invalidate_node_list_cache()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not description_stack_running(force=True)[0]:
            return (
                "Stopped an incomplete Slicer-mode description launch "
                "(robot_state_publisher was up without "
                "dentobot_slicer_joint_state_publisher)."
            )
        time.sleep(0.2)
    return ""


def run_ros2_cli(
    args: Sequence[str],
    timeout: float,
) -> subprocess.CompletedProcess:
    """Run ``ros2`` after sourcing Jazzy and the workspace overlay."""
    quoted = " ".join(shlex.quote(part) for part in ("ros2", *args))
    return subprocess.run(
        ["bash", "-c", f"{CONTAINER_ROS_SETUP} && {quoted}"],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=_ros2_child_env(),
    )


def ros2_cli_available() -> bool:
    ok, _, _ = ros2_node_list()
    return ok


def ros2_node_list(*, force: bool = False) -> Tuple[bool, list[str], str]:
    """List ROS 2 nodes via a Slicer-safe sourced CLI (cached briefly)."""
    global _NODE_LIST_CACHE
    now = time.monotonic()
    if (
        not force
        and _NODE_LIST_CACHE is not None
        and now - _NODE_LIST_CACHE[0] < _NODE_LIST_CACHE_SEC
    ):
        return _NODE_LIST_CACHE[1], list(_NODE_LIST_CACHE[2]), _NODE_LIST_CACHE[3]
    try:
        completed = run_ros2_cli(("node", "list"), timeout=8)
    except (OSError, subprocess.SubprocessError) as exc:
        result = False, [], str(exc)
        _NODE_LIST_CACHE = (now, *result)
        return result
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        if "PYTHONHOME" in message or "rclpy" in message or "ros2cli" in message:
            message = (
                "ros2 CLI is not available in this Slicer process. "
                + (message.splitlines()[-1] if message else "")
            ).strip()
        result = False, [], message or "ros2 CLI is not available in this Slicer process."
        _NODE_LIST_CACHE = (now, *result)
        return result
    nodes = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    result = True, nodes, ""
    _NODE_LIST_CACHE = (now, True, list(nodes), "")
    return result


def _invalidate_node_list_cache() -> None:
    global _NODE_LIST_CACHE
    _NODE_LIST_CACHE = None


def _normalized_node_names(*, force: bool = False) -> Tuple[bool, set[str], str]:
    ok, nodes, message = ros2_node_list(force=force)
    if not ok:
        return False, set(), message
    return True, {node.lstrip("/") for node in nodes}, ""


def competing_joint_source_message(*, force: bool = False) -> str:
    """Return an error if a non-Slicer joint-state publisher owns /joint_states."""
    ok, names, message = _normalized_node_names(force=force)
    if not ok:
        return message
    found = sorted(names & ROS2_COMPETING_JOINT_NODES)
    if not found:
        return ""
    listed = ", ".join("/" + name for name in found)
    return (
        "A competing DENTOBOT joint-state publisher is already running "
        f"({listed}). Stop that launch before connecting Slicer Motion Control."
    )


def slicer_motion_stack_ready(*, force: bool = False) -> Tuple[bool, str]:
    """Return whether RSP and the Slicer joint-state publisher are both up."""
    competing = competing_joint_source_message(force=force)
    if competing:
        return False, competing
    ok, names, message = _normalized_node_names(force=force)
    if not ok:
        return False, message
    expected_rsp = ROS2_URDF_PARAM_NODE.lstrip("/")
    if expected_rsp in names and ROS2_SLICER_JOINT_NODE in names:
        return True, ""
    if expected_rsp in names:
        return False, (
            "/dentobot_robot_state_publisher is running without "
            "/dentobot_slicer_joint_state_publisher. Reload the DENTOBOT "
            "extension, then press Connect again so the leftover launch is "
            "stopped and restarted with joint_state_mode:=slicer."
        )
    return False, (
        "ROS 2 node /dentobot_robot_state_publisher was not found. "
        "Start the description stack first."
    )


def description_stack_running(*, force: bool = False) -> Tuple[bool, str]:
    """Return whether the DENTOBOT description launch appears to be running."""
    ok, names, message = _normalized_node_names(force=force)
    if not ok:
        return False, message
    expected = ROS2_URDF_PARAM_NODE.lstrip("/")
    if expected in names:
        return True, ""
    return False, (
        "ROS 2 node /dentobot_robot_state_publisher was not found. "
        "Start the description stack first."
    )


def start_description_stack_background() -> Tuple[bool, str]:
    """Launch ``description.launch.py`` without RViz from the Slicer process."""
    competing = competing_joint_source_message()
    if competing:
        return False, competing
    leftover = stop_incomplete_slicer_description_launch()
    _invalidate_node_list_cache()
    if slicer_motion_stack_ready(force=True)[0]:
        suffix = f" {leftover}" if leftover else ""
        return True, "Description stack is already running." + suffix
    if description_stack_running(force=True)[0]:
        return False, slicer_motion_stack_ready(force=True)[1]
    log_handle = tempfile.NamedTemporaryFile(
        prefix="dentobot-description-launch-",
        suffix=".log",
        delete=False,
    )
    log_path = log_handle.name
    try:
        process = subprocess.Popen(
            ["bash", "-c", DESCRIPTION_LAUNCH_CMD],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=_ros2_child_env(),
        )
    except OSError as exc:
        log_handle.close()
        return False, f"Failed to start description launch: {exc}"
    deadline = time.monotonic() + STACK_START_WAIT_SEC
    while time.monotonic() < deadline:
        if process.poll() not in (None, 0):
            log_handle.close()
            tail = _log_tail(log_path)
            detail = f" Launch log ({log_path}): {tail}" if tail else f" See {log_path}."
            prefix = f"{leftover} " if leftover else ""
            return False, (
                f"{prefix}Description launch exited before the Slicer "
                f"joint-state stack appeared.{detail}"
            )
        running, _ = slicer_motion_stack_ready(force=True)
        if running:
            log_handle.close()
            _invalidate_node_list_cache()
            prefix = f"{leftover} " if leftover else ""
            return True, f"{prefix}Description stack started.".strip()
        time.sleep(0.5)
    _terminate_process_group(process.pid)
    log_handle.close()
    tail = _log_tail(log_path)
    detail = f" Launch log ({log_path}): {tail}" if tail else f" See {log_path}."
    prefix = f"{leftover} " if leftover else ""
    return False, (
        f"{prefix}Description launch was started but the Slicer joint-state "
        f"stack did not appear within {STACK_START_WAIT_SEC:.0f} s.{detail}"
    )


def ros2_unavailable_message() -> str:
    return ROS2_UNAVAILABLE_MESSAGE


def is_ros2_module_missing_message(message: str) -> bool:
    lowered = (message or "").lower()
    return "ros2 slicer module is not available" in lowered


def is_ros2_runtime_unavailable_message(message: str) -> bool:
    lowered = (message or "").lower()
    return is_ros2_module_missing_message(lowered) or (
        "ros2 cli is not available" in lowered
    )


def _unique_existing_directories(candidates: Sequence[str]) -> list[str]:
    paths: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        normalized = os.path.abspath(candidate)
        if os.path.isdir(normalized) and normalized not in paths:
            paths.append(normalized)
    return paths


def _ros2_pkg_prefix(package: str = SLICER_ROS2_PACKAGE) -> str:
    if not ros2_cli_available():
        return ""
    try:
        completed = run_ros2_cli(("pkg", "prefix", package), timeout=8)
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return (completed.stdout or "").strip()


def slicer_ros2_module_search_paths() -> list[str]:
    """Return installed SlicerROS2 loadable/scripted module directories."""
    candidates: list[str] = []
    env_paths = os.environ.get("SLICER_ROS2_MODULE_PATHS", "")
    if env_paths:
        candidates.extend(env_paths.split(":"))

    prefixes = [_ros2_pkg_prefix()]
    prefixes.extend(_DEFAULT_SLICER_ROS2_PREFIXES)
    for prefix in prefixes:
        if not prefix:
            continue
        for relative in _SLICER_ROS2_RELATIVE_MODULE_DIRS:
            candidates.append(os.path.join(prefix, relative))
    return _unique_existing_directories(candidates)


def _module_logic(module_name: str):
    """Return Slicer module logic, or None.

    Import ``slicer`` here. This helper is a plain Python module, so a
    function-level ``import slicer`` elsewhere does not create a global name.
    The previous ``get_ros2_logic`` looked up a global ``slicer``, caught the
    ``NameError``, and reported ROS2 as missing even when it was loaded.
    """
    try:
        import slicer

        return slicer.util.getModuleLogic(module_name)
    except Exception:
        return None


def _prepend_ld_library_paths(paths: Sequence[str]) -> None:
    existing = os.environ.get("LD_LIBRARY_PATH", "")
    ordered: list[str] = []
    for path in [*paths, *existing.split(":")]:
        if path and path not in ordered:
            ordered.append(path)
    if ordered:
        os.environ["LD_LIBRARY_PATH"] = ":".join(ordered)


def _load_slicer_modules(module_names: Sequence[str], extra_paths: Sequence[str]) -> None:
    import slicer

    factory = slicer.app.moduleManager().factoryManager()
    _prepend_ld_library_paths(extra_paths)
    for path in extra_paths:
        try:
            current = list(factory.searchPaths())
        except Exception:
            current = []
        if path not in current:
            factory.addSearchPath(path)
    factory.registerModules()
    factory.instantiateModules()
    missing = [name for name in module_names if not factory.isLoaded(name)]
    if missing:
        factory.loadModules(list(missing))


def ensure_ros2_slicer_modules() -> Tuple[Optional[object], Optional[object], str]:
    """Load ROS2 / ROS2MotionControl if this Slicer process can see them."""
    ros_logic = _module_logic(ROS2_MODULE_NAME)
    motion_logic = _module_logic(ROS2_MOTION_MODULE_NAME)
    if ros_logic is not None and motion_logic is not None:
        return ros_logic, motion_logic, ""

    try:
        import slicer  # noqa: F401
    except ImportError:
        return None, None, ros2_unavailable_message()

    try:
        _load_slicer_modules(
            (ROS2_MODULE_NAME, ROS2_MOTION_MODULE_NAME),
            slicer_ros2_module_search_paths(),
        )
        if _module_logic(ROS2_MOTION_MODULE_NAME) is None:
            try:
                import slicer

                slicer.util.getModuleWidget(ROS2_MOTION_MODULE_NAME)
            except Exception:
                pass
    except Exception as exc:
        return None, None, f"{ros2_unavailable_message()} ({exc})"

    ros_logic = _module_logic(ROS2_MODULE_NAME)
    motion_logic = _module_logic(ROS2_MOTION_MODULE_NAME)
    if ros_logic is None:
        return None, None, ros2_unavailable_message()
    if motion_logic is None:
        return ros_logic, None, (
            "The ROS2MotionControl module is not available. "
            "Start Slicer with ./scripts/launch-dentoworkflow.bash."
        )
    return ros_logic, motion_logic, ""


def get_ros2_logic():
    logic = _module_logic(ROS2_MODULE_NAME)
    if logic is not None:
        return logic
    logic, _, _ = ensure_ros2_slicer_modules()
    return logic


def get_motion_control_logic():
    logic = _module_logic(ROS2_MOTION_MODULE_NAME)
    if logic is not None:
        return logic
    _, logic, _ = ensure_ros2_slicer_modules()
    return logic


def joint_si_vector(positions_si: Mapping[str, float]) -> list[float]:
    """Return movable-joint values in the tracked URDF / Motion Control order."""
    return [float(positions_si[name]) for name in ROS2_JOINT_SI_ORDER]


def slicer_ros2_runtime_status(
    *,
    require_stack: bool = False,
    require_slicer_node: bool = True,
) -> Tuple[bool, str]:
    """Return whether the Slicer ROS 2 node (and optionally the description stack) is usable."""
    ros_logic, _motion_logic, module_error = ensure_ros2_slicer_modules()
    if ros_logic is None:
        return False, module_error
    ros_node = ros_logic.GetDefaultROS2Node()
    if ros_node is None:
        return False, "ROS2 default node is not initialized."

    ok, names, message = _normalized_node_names(force=require_stack)
    if not ok:
        return False, message
    if require_slicer_node and ROS2_DEFAULT_SLICER_NODE not in names:
        return False, (
            "ROS 2 node /slicer was not found. Reload DENTO Workflow in a "
            "Slicer started with ./scripts/launch-dentoworkflow.bash."
        )
    if require_stack:
        stack_ok, stack_message = slicer_motion_stack_ready(force=require_stack)
        if not stack_ok:
            return False, stack_message
    return True, ""


def ensure_slicer_ros2_runtime(*, require_stack: bool = False) -> Tuple[bool, str]:
    """Load SlicerROS2 modules and optionally start the description stack."""
    ok, message = slicer_ros2_runtime_status(
        require_stack=False,
        require_slicer_node=False,
    )
    if not ok:
        return False, message
    if require_stack:
        started, start_message = start_description_stack_background()
        if not started:
            return False, start_message
        return slicer_ros2_runtime_status(require_stack=True, require_slicer_node=True)
    return slicer_ros2_runtime_status(require_stack=False, require_slicer_node=True)


def apply_joint_positions_si_to_motion_control(
    positions_si: Mapping[str, float],
) -> Tuple[bool, str]:
    """Push Step 6 joint values into ROS2 Motion Control and /joint_states."""
    try:
        import slicer
    except ImportError:
        return False, ros2_unavailable_message()
    try:
        motion_widget = slicer.util.getModuleWidget(ROS2_MOTION_MODULE_NAME)
    except Exception as exc:
        return False, f"ROS2MotionControl widget is not available ({exc})."
    if motion_widget is None:
        return False, "ROS2MotionControl widget is not available."
    values = joint_si_vector(positions_si)
    motion_widget.jointPositionsRad = list(values)
    setter = getattr(motion_widget, "_setJointUi_SIToSlicer", None)
    if callable(setter):
        setter(values)
    _publish_slicer_joint_command()
    return True, ""


def find_ros2_robot_by_name(robot_name: str):
    import slicer

    for node in slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"):
        if node.GetAttribute(ROS2_ROBOT_NODE_ATTRIBUTE) == robot_name:
            return node
    ros_logic = get_ros2_logic()
    if not ros_logic or not ros_logic.mDefaultROS2Node:
        return None
    return ros_logic.mDefaultROS2Node.GetRobotNodeByName(robot_name)


def wait_for_robot_urdf(
    robot_node,
    process_events: Callable[[], None],
    timeout_sec: float = URDF_WAIT_TIMEOUT_SEC,
) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        process_events()
        root_and_tip = robot_node.FindRootAndTipLinks()
        if root_and_tip and len(root_and_tip) >= 2:
            return True
        time.sleep(PROCESS_EVENT_POLL_SEC)
    return False


def align_ros2_robot_to_base_transform(robot_node, base_transform) -> bool:
    """Parent the root TF lookup under the Step 6 robot-base transform."""
    lookup = robot_node.GetNthNodeReference("lookup", 0)
    if lookup is None:
        return False
    lookup.SetAndObserveTransformNodeID(base_transform.GetID())
    return True


def set_mrml_link_models_visible(model_nodes: list, visible: bool) -> None:
    for model_node in model_nodes:
        display = model_node.GetDisplayNode()
        if display is None:
            model_node.CreateDefaultDisplayNodes()
            display = model_node.GetDisplayNode()
        if display:
            display.SetVisibility(visible)


def _motion_control_joint_positions() -> list[float]:
    import slicer

    try:
        motion_widget = slicer.util.getModuleWidget("ROS2MotionControl")
    except Exception:
        return []
    if motion_widget is None:
        return []
    positions = getattr(motion_widget, "jointPositionsRad", None)
    if not positions:
        return []
    return [float(value) for value in positions]


def _publish_slicer_joint_command() -> None:
    publisher = _slicer_joint_command_publisher
    if publisher is None:
        return
    positions = _motion_control_joint_positions()
    if not positions:
        return
    import vtk

    array = vtk.vtkDoubleArray()
    array.SetNumberOfValues(len(positions))
    for index, value in enumerate(positions):
        array.SetValue(index, value)
    publisher.Publish(array)


def start_slicer_joint_command_stream() -> Tuple[bool, str]:
    """Publish Motion Control slider values to the Slicer joint-state node."""
    global _slicer_joint_command_timer, _slicer_joint_command_publisher
    import qt

    ros_logic = get_ros2_logic()
    if ros_logic is None:
        return False, ros2_unavailable_message()
    ros_node = ros_logic.GetDefaultROS2Node()
    if ros_node is None:
        return False, "ROS2 default node is not initialized."

    publisher = ros_node.GetPublisherNodeByTopic(ROS2_SLICER_JOINT_COMMAND_TOPIC)
    if publisher is None:
        publisher = ros_node.CreateAndAddPublisherNode(
            "DoubleArray",
            ROS2_SLICER_JOINT_COMMAND_TOPIC,
        )
    if publisher is None:
        return False, (
            "Failed to create the Slicer joint-command publisher on "
            f"{ROS2_SLICER_JOINT_COMMAND_TOPIC}."
        )
    publisher.SetAttribute(ROS2_SLICER_JOINT_PUBLISHER_ATTRIBUTE, "true")
    _slicer_joint_command_publisher = publisher

    if _slicer_joint_command_timer is None:
        timer = qt.QTimer()
        timer.setInterval(ROS2_SLICER_JOINT_PUBLISH_INTERVAL_MS)
        timer.timeout.connect(_publish_slicer_joint_command)
        _slicer_joint_command_timer = timer
    _slicer_joint_command_timer.start()
    _publish_slicer_joint_command()
    return True, ""


def stop_slicer_joint_command_stream() -> None:
    """Stop streaming Motion Control sliders and remove the command publisher."""
    global _slicer_joint_command_timer, _slicer_joint_command_publisher
    if _slicer_joint_command_timer is not None:
        _slicer_joint_command_timer.stop()
        _slicer_joint_command_timer = None

    ros_logic = get_ros2_logic()
    ros_node = ros_logic.GetDefaultROS2Node() if ros_logic is not None else None
    if ros_node is not None:
        ros_node.RemoveAndDeletePublisherNode(ROS2_SLICER_JOINT_COMMAND_TOPIC)
    _slicer_joint_command_publisher = None


def connect_dentobot_motion_control(
    base_transform,
    hide_mrml_robot: bool = True,
    mrml_robot_models: Optional[list] = None,
    open_motion_module: bool = True,
    start_stack_if_needed: bool = True,
) -> Tuple[Optional[object], str]:
    """Load DENTOBOT in SlicerROS2 and configure Motion Control (no MoveIt)."""
    import slicer

    ros_logic, motion_logic, module_error = ensure_ros2_slicer_modules()
    if ros_logic is None:
        return None, module_error
    if motion_logic is None:
        return None, module_error or (
            "The ROS2MotionControl module is not available."
        )

    if start_stack_if_needed and not slicer_motion_stack_ready(force=True)[0]:
        started, start_message = start_description_stack_background()
        if not started:
            return None, start_message

    ready, ready_message = slicer_motion_stack_ready(force=True)
    if not ready:
        return None, ready_message

    ros_node = ros_logic.GetDefaultROS2Node()
    if ros_node is None:
        return None, "ROS2 default node is not initialized."

    existing = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
    if existing is not None:
        robot_node = existing
    else:
        robot_node = ros_node.CreateAndAddRobotNode(
            ROS2_ROBOT_NAME,
            ROS2_URDF_PARAM_NODE,
            ROS2_URDF_PARAM_NAME,
            ROS2_FIXED_FRAME,
            ROS2_TF_PREFIX,
        )
        if robot_node is None:
            return None, (
                "CreateAndAddRobotNode returned None. "
                f"Confirm parameter {ROS2_URDF_PARAM_NAME} on "
                f"{ROS2_URDF_PARAM_NODE}."
            )
        robot_node.SetAttribute(ROS2_ROBOT_NODE_ATTRIBUTE, ROS2_ROBOT_NAME)

    if not wait_for_robot_urdf(robot_node, slicer.app.processEvents):
        return None, (
            "Timed out waiting for the DENTOBOT URDF from ROS 2. "
            "Check /dentobot_robot_state_publisher and network discovery."
        )

    if base_transform is None:
        return None, "Select or create the Step 6 robot-base transform first."

    if not align_ros2_robot_to_base_transform(robot_node, base_transform):
        return None, "Failed to align the ROS 2 robot root lookup to the base transform."

    param_node = motion_logic.getParameterNode()
    param_node.robotNodeID = robot_node.GetID()
    param_node.jointStateTopic = ROS2_JOINT_STATES_TOPIC
    param_node.moveGroupExists = ROS2_MOVE_GROUP_EXISTS
    param_node.planningGroup = ""

    if not motion_logic.SetupRobotForMotionControl(param_node):
        return None, "SetupRobotForMotionControl failed."

    streamed, stream_message = start_slicer_joint_command_stream()
    if not streamed:
        return None, stream_message

    base_transform.SetAttribute(ROS2_MOTION_ACTIVE_ATTRIBUTE, "true")

    if hide_mrml_robot and mrml_robot_models:
        set_mrml_link_models_visible(mrml_robot_models, False)

    motion_widget = slicer.util.getModuleWidget("ROS2MotionControl")
    if motion_widget is not None:
        motion_widget.onUseButton()

    if open_motion_module:
        slicer.util.selectModule("ROS2MotionControl")

    return robot_node, ""


def disconnect_dentobot_motion_control(
    mrml_robot_models: Optional[list] = None,
) -> Tuple[bool, str]:
    import slicer

    ros_logic = get_ros2_logic()
    if ros_logic is None:
        return False, ros2_unavailable_message()

    stop_slicer_joint_command_stream()
    ros_logic.RemoveRobot(ROS2_ROBOT_NAME)

    motion_logic = get_motion_control_logic()
    if motion_logic is not None:
        motion_logic.ClearJointStateSubscriber()
        param_node = motion_logic.getParameterNode()
        if param_node.robotNodeID:
            param_node.robotNodeID = ""
        param_node.moveGroupExists = False

    for node in slicer.util.getNodesByClass("vtkMRMLLinearTransformNode"):
        if node.GetAttribute(ROS2_MOTION_ACTIVE_ATTRIBUTE) == "true":
            node.RemoveAttribute(ROS2_MOTION_ACTIVE_ATTRIBUTE)

    if mrml_robot_models:
        set_mrml_link_models_visible(mrml_robot_models, True)

    return True, "ROS 2 motion control disconnected."
