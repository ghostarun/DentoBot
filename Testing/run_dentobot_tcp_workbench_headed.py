"""Headed no-case TCP workbench check with physical Qt key delivery."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping
from pathlib import Path
import re
import statistics
import sys
import time
import traceback

import qt
import slicer
import vtk


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
EXPECTED_HOST_ROOT = "/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-renovation"
EXPECTED_CONTAINER_ROOT = "/workspace/ros2_ws/src/DentoBot-step6-renovation"
EXPECTED_BRANCH = "feature/step6-workflow-renovation-20260925"
RUNS_ROOT = Path("/workspace/data/dentobot-runs").resolve()
NATIVE_BINARY_RELATIVE_PATH = Path("lib/dentobot_moveit_config/collision_guard")
DRAG_EVENT_TIMEOUT_SEC = 30.0
GOAL_CHANGE_TIMEOUT_SEC = 10.0
SOURCE_FILES = (
    "DENTOWorkflow/Resources/Python/DENTORobotSimulationPanel.py",
    "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py",
    "DENTOWorkflow/Resources/Python/DENTOROS2Bridge.py",
    "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot.py",
    "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot_shell.py",
)

for candidate in (PYTHON, Path(__file__).resolve().parent):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import DENTOROS2Bridge as bridge  # noqa: E402
from DENTOStep6State import JOINT_NAMES  # noqa: E402


class TcpProbeError(RuntimeError):
    """A headed TCP probe invariant or evidence check failed."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing exact headed-run input {name}.")
    return value


def _execution_paths() -> tuple[Path, Path, Path]:
    os.umask(0o077)
    evidence_dir = Path(_required_env("DENTOBOT_HEADED_EVIDENCE_DIR")).expanduser()
    if not evidence_dir.is_absolute():
        raise RuntimeError("DENTOBOT_HEADED_EVIDENCE_DIR must be absolute.")
    evidence_dir = evidence_dir.resolve()
    run_dir = evidence_dir.parent
    if evidence_dir.name != "evidence":
        raise RuntimeError("DENTOBOT_HEADED_EVIDENCE_DIR must be the run's evidence/ directory.")
    if RUNS_ROOT not in run_dir.parents:
        raise RuntimeError(f"Run directory must be below {RUNS_ROOT}.")
    if run_dir.parent != RUNS_ROOT:
        raise RuntimeError("Run directory must be one named child of the run root.")
    if str(ROOT.resolve()) != EXPECTED_CONTAINER_ROOT:
        raise RuntimeError(f"Mounted checkout is unexpected: {ROOT.resolve()}.")
    run_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    run_dir.chmod(0o700)
    if (run_dir / "result.json").exists():
        raise FileExistsError("Refusing to overwrite an existing result.json.")
    drag_ready = run_dir / "drag-ready.json"
    if drag_ready.exists():
        raise FileExistsError("Refusing a stale drag-ready.json rendezvous file.")
    evidence_dir.mkdir(mode=0o700, exist_ok=True)
    evidence_dir.chmod(0o700)
    if any(evidence_dir.iterdir()):
        raise FileExistsError("Evidence directory must be fresh and empty.")
    return run_dir, evidence_dir, run_dir / "result.json"


def _checkout_provenance() -> dict[str, object]:
    host_root = _required_env("DENTOBOT_HEADED_HOST_CHECKOUT_ROOT")
    branch = _required_env("DENTOBOT_HEADED_GIT_BRANCH")
    commit = _required_env("DENTOBOT_HEADED_GIT_HEAD")
    status_hash = _required_env("DENTOBOT_HEADED_GIT_STATUS_SHA256")
    if host_root != EXPECTED_HOST_ROOT or branch != EXPECTED_BRANCH:
        raise RuntimeError("Host checkout root or branch does not match the renovation checkout.")
    if re.fullmatch(r"[0-9a-fA-F]{40}", commit) is None:
        raise RuntimeError("DENTOBOT_HEADED_GIT_HEAD must be 40 hexadecimal characters.")
    if re.fullmatch(r"[0-9a-fA-F]{64}", status_hash) is None:
        raise RuntimeError("DENTOBOT_HEADED_GIT_STATUS_SHA256 must be 64 hexadecimal characters.")
    return {
        "container_checkout_root": str(ROOT.resolve()),
        "host_checkout_root": host_root,
        "branch": branch,
        "head_commit": commit.lower(),
        "worktree_status_sha256": status_hash.lower(),
        "source_sha256": {
            name: _sha256_file(ROOT / name)
            for name in SOURCE_FILES
        },
        "runner_sha256": _sha256_file(Path(__file__).resolve()),
    }


def _native_provenance() -> dict[str, object]:
    expected_source = _required_env("DENTOBOT_HEADED_NATIVE_SOURCE_SHA256").lower()
    expected_binary = _required_env("DENTOBOT_HEADED_NATIVE_BINARY_SHA256").lower()
    expected_prefix_text = _required_env("DENTOBOT_HEADED_NATIVE_PACKAGE_PREFIX")
    for name, value in (
        ("DENTOBOT_HEADED_NATIVE_SOURCE_SHA256", expected_source),
        ("DENTOBOT_HEADED_NATIVE_BINARY_SHA256", expected_binary),
    ):
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise RuntimeError(f"{name} must be 64 hexadecimal characters.")
    requested_prefix = Path(expected_prefix_text).expanduser()
    if not requested_prefix.is_absolute():
        raise RuntimeError("DENTOBOT_HEADED_NATIVE_PACKAGE_PREFIX must be absolute.")
    requested_prefix = requested_prefix.resolve()
    shared_prefix = (ROOT.parent.parent / "install/dentobot_moveit_config").resolve()
    if requested_prefix == shared_prefix:
        raise RuntimeError("Refusing the shared workspace install prefix.")
    from ament_index_python.packages import get_package_prefix

    package_prefix = Path(get_package_prefix("dentobot_moveit_config")).resolve()
    if package_prefix != requested_prefix:
        raise RuntimeError("Ament package prefix does not match the supplied isolated prefix.")
    source = ROOT / "dentobot_moveit_config/src/collision_guard.cpp"
    binary = package_prefix / NATIVE_BINARY_RELATIVE_PATH
    if not source.is_file() or not binary.is_file():
        raise RuntimeError("Exact collision_guard source or binary is unavailable.")
    source_hash = _sha256_file(source)
    binary_hash = _sha256_file(binary)
    if source_hash != expected_source or binary_hash != expected_binary:
        raise RuntimeError("Active collision_guard source/binary hashes do not match preflight.")
    return {
        "package": "dentobot_moveit_config",
        "package_prefix": str(package_prefix),
        "source_path": str(source.resolve()),
        "source_sha256": source_hash,
        "binary_path": str(binary.resolve()),
        "binary_sha256": binary_hash,
        "expected_source_sha256": expected_source,
        "expected_binary_sha256": expected_binary,
    }


def _mouse_drag_requested() -> bool:
    value = os.environ.get("DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG", "")
    if value not in ("", "0", "1"):
        raise RuntimeError("DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG must be '1', '0', or unset.")
    return value == "1"


def _write_json(path: Path, value: object, *, exclusive: bool = False) -> None:
    text = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if exclusive:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(text)
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def make_external_mouse_drag_callback(run_dir: Path):
    run_path = Path(run_dir)

    def callback(context):
        rendezvous = context["rendezvous"]
        _write_json(run_path / "drag-ready.json", rendezvous, exclusive=True)
        print("DENTOBOT_TCP_DRAG_READY", json.dumps(rendezvous, sort_keys=True), flush=True)
        delivered = context["wait_for_delivery"]()
        return {
            "method": "external_xdotool_rendezvous",
            "delivered": delivered["delivered"],
            "event_monotonic_ns": delivered["event_monotonic_ns"],
            "release_monotonic_ns": delivered["release_monotonic_ns"],
        }

    return callback


def _matrix(node) -> list[list[float]]:
    value = vtk.vtkMatrix4x4()
    node.GetMatrixTransformToParent(value)
    matrix = [
        [float(value.GetElement(row, column)) for column in range(4)]
        for row in range(4)
    ]
    if not all(math.isfinite(item) for row in matrix for item in row):
        raise RuntimeError("TCP goal matrix contains non-finite values.")
    return matrix


def _nodes_named(name: str) -> list[object]:
    scene = slicer.mrmlScene
    expected_class = (
        "vtkMRMLModelNode" if name == "ProbeSphere" else "vtkMRMLTransformNode"
    )
    candidate_name = re.compile(rf"{re.escape(name)}(?:_\d+)?\Z")
    nodes = []
    for index in range(scene.GetNumberOfNodes()):
        node = scene.GetNthNode(index)
        if node is None or not candidate_name.fullmatch(str(node.GetName())):
            continue
        is_a = getattr(node, "IsA", None)
        _require(callable(is_a), "Cannot verify a named TCP goal/model node type.")
        if is_a("vtkMRMLDisplayNode"):
            continue
        _require(is_a(expected_class),
                 f"Unexpected MRML node type uses reserved TCP name {node.GetName()}.")
        nodes.append(node)
    return nodes


def _passive_goal_cleanup_status(original_id, original_matrix):
    nodes = _nodes_named("ProbeSphere_Transform")
    if original_id is None:
        return ("removed", not nodes)
    if len(nodes) != 1:
        return ("unexpected", False)
    goal = nodes[0]
    display_getter = getattr(goal, "GetDisplayNode", None)
    display = display_getter() if callable(display_getter) else None
    editor_getter = getattr(display, "GetEditorVisibility", None)
    unchanged = (
        str(goal.GetID()) == original_id
        and goal.GetScene() == slicer.mrmlScene
        and callable(editor_getter)
        and not bool(editor_getter())
        and _matrix(goal) == original_matrix
    )
    return ("retained_passive" if unchanged else "unexpected", unchanged)


def _changed(before, after, tolerance: float = 1e-6) -> bool:
    return any(
        abs(float(before[row][column]) - float(after[row][column])) > tolerance
        for row in range(4)
        for column in range(4)
    )


def _process_events(seconds: float = 0.02, monitor=None) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        _process_event_turn()
        if monitor is not None:
            monitor()
        time.sleep(0.005)


def _process_event_turn() -> None:
    slicer.app.processEvents()
    logic = slicer.util.getModuleLogic("ROS2")
    if logic is not None:
        logic.Spin()


def _wait_goal_change(
    goal, before, timeout_sec: float = GOAL_CHANGE_TIMEOUT_SEC, monitor=None
):
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if monitor is not None:
            monitor()
        after = _matrix(goal)
        if _changed(before, after):
            return after, time.monotonic_ns()
        _process_event_turn()
        time.sleep(0.001)
    return _matrix(goal), None


def _measure_goal_change(
    goal,
    label: str,
    input_type: str,
    action,
    *,
    monitor=None,
) -> dict[str, object]:
    before = _matrix(goal)
    started_ns = time.monotonic_ns()
    delivery = action()
    after, observed_ns = _wait_goal_change(goal, before, monitor=monitor)
    if observed_ns is None or not _changed(before, after):
        raise RuntimeError(f"{label} did not produce an observed TCP goal change.")
    latency_ns = int(observed_ns - started_ns)
    if latency_ns < 0:
        raise RuntimeError(f"{label} produced invalid monotonic timing evidence.")
    return {
        "observation": label,
        "input_type": input_type,
        "delivery": delivery,
        "input_monotonic_ns": int(started_ns),
        "goal_observed_monotonic_ns": int(observed_ns),
        "latency_ns": latency_ns,
        "latency_ms": latency_ns / 1_000_000.0,
        "units": "ms",
        "goal_before": before,
        "goal_after": after,
        "goal_changed": True,
    }


def _deliver_key(widget, key, modifiers) -> dict[str, object]:
    qtest = getattr(qt, "QTest", None)
    key_click = getattr(qtest, "keyClick", None) if qtest is not None else None
    if callable(key_click):
        key_click(widget, key, modifiers)
        return {"method": "qt.QTest.keyClick", "delivered": True}
    key_event = getattr(qt, "QKeyEvent", None)
    send_event = getattr(qt.QApplication, "sendEvent", None)
    event_type = getattr(qt, "QEvent", None)
    if not callable(key_event) or not callable(send_event) or event_type is None:
        raise RuntimeError("Qt physical key delivery is unavailable; refusing callback fallback.")
    press = key_event(event_type.KeyPress, key, modifiers, "", False, 1)
    release = key_event(event_type.KeyRelease, key, modifiers, "", False, 1)
    send_event(widget, press)
    send_event(widget, release)
    return {"method": "QApplication.sendEvent(QKeyEvent)", "delivered": True}


def _focus(widget, monitor=None) -> None:
    widget.setFocus()
    _process_events(0.05, monitor)
    focused = qt.QApplication.focusWidget()
    if focused is not widget and focused != widget:
        raise RuntimeError("Could not give the requested visible workbench widget focus.")


def _ensure_visible(workflow_widget, control, monitor=None) -> None:
    scroll = getattr(workflow_widget, "_workflowContentScrollArea", None)
    if scroll is not None:
        scroll.ensureWidgetVisible(control, 0, 20)
    _process_events(0.05, monitor)
    if not control.isVisible():
        raise RuntimeError("Required TCP workbench control is not visible.")


def _joint_snapshot(widget, joint_order) -> dict[str, float]:
    positions = widget._robotJointPositionsSi()
    if not isinstance(positions, dict) or set(positions) != set(joint_order):
        raise RuntimeError("Accepted UI state does not contain exactly the canonical J1–J5 set.")
    snapshot = {name: float(positions[name]) for name in joint_order}
    if not all(math.isfinite(value) for value in snapshot.values()):
        raise RuntimeError("Accepted J1–J5 snapshot contains a non-finite value.")
    return snapshot


def _capture(evidence_dir: Path, name: str) -> str:
    window = slicer.util.mainWindow()
    if window is None or not window.isVisible():
        raise RuntimeError("Visible Slicer main window is unavailable for screenshot evidence.")
    path = evidence_dir / name
    pixmap = window.grab()
    if pixmap.isNull() or not pixmap.save(str(path)):
        raise RuntimeError(f"Could not save screenshot evidence {path.name}.")
    return path.name


class _DragEventObserver(qt.QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.first_drag_event_ns: int | None = None
        self.left_release_event_ns: int | None = None

    def eventFilter(self, _watched, event):
        event_type = event.type()
        if self.first_drag_event_ns is None and event_type == qt.QEvent.MouseMove:
            buttons = getattr(event, "buttons", 0)
            buttons = buttons() if callable(buttons) else buttons
            if int(buttons) & int(qt.Qt.LeftButton):
                self.first_drag_event_ns = time.monotonic_ns()
        elif (self.first_drag_event_ns is not None
              and self.left_release_event_ns is None
              and event_type == qt.QEvent.MouseButtonRelease):
            button = getattr(event, "button", 0)
            button = button() if callable(button) else button
            if int(button) == int(qt.Qt.LeftButton):
                self.left_release_event_ns = time.monotonic_ns()
        return False


def _latency_summary(samples: list[dict[str, object]]) -> dict[str, object]:
    values = sorted(float(sample["latency_ms"]) for sample in samples)
    if not values:
        return {
            "sample_count": 0,
            "median_ms": None,
            "p95_ms": None,
            "max_ms": None,
            "units": "ms",
        }
    p95 = values[max(0, math.ceil(0.95 * len(values)) - 1)]
    return {
        "sample_count": len(values),
        "median_ms": statistics.median(values),
        "p95_ms": p95,
        "max_ms": max(values),
        "units": "ms",
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TcpProbeError(message)


def _json_safe(value, label: str):
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TcpProbeError(f"{label} is not JSON-safe: {exc}") from exc
    return value


def _joint_map(values, label: str) -> dict[str, float]:
    if not isinstance(values, Mapping) or set(values) != set(JOINT_NAMES):
        raise TcpProbeError(f"{label} does not contain exactly J1–J5.")
    result = {name: float(values[name]) for name in JOINT_NAMES}
    if not all(math.isfinite(value) for value in result.values()):
        raise TcpProbeError(f"{label} contains a non-finite joint value.")
    return result


def _joint_states(facade) -> dict[str, dict[str, float]]:
    values = {
        "accepted_si": _joint_map(bridge.last_accepted_joint_positions_si(), "Accepted state"),
        "monitored_si": _joint_map(bridge.monitored_joint_positions_si(), "Monitored state"),
        "displayed_si": _joint_map(
            facade.currentRobotState().joint_positions_si, "Displayed state"
        ),
    }
    if not (values["accepted_si"] == values["monitored_si"]
            and values["accepted_si"] == values["displayed_si"]):
        raise TcpProbeError(
            "Accepted, monitored, and displayed J1–J5 state is not exactly equal."
        )
    return values


def _qt_value(value, name: str):
    result = getattr(value, name)
    return result() if callable(result) else result


def _rect(widget) -> list[int]:
    geometry = _qt_value(widget, "geometry")
    return [
        int(_qt_value(geometry, "x")),
        int(_qt_value(geometry, "y")),
        int(_qt_value(geometry, "width")),
        int(_qt_value(geometry, "height")),
    ]


def _owner(group) -> dict[str, object]:
    return {
        "object_name": str(_qt_value(group, "objectName")),
        "title": str(_qt_value(group, "title")),
        "visible": bool(group.isVisible()),
        "rect": _rect(group),
    }


def _owners(panel) -> dict[str, dict[str, object]]:
    result = {
        "planning_diagnostics": _owner(panel.approachGroup),
        "preview_control": _owner(panel.previewControlGroup),
    }
    _require("Planning & Diagnostics" in result["planning_diagnostics"]["title"],
             "Planning & Diagnostics owner identity is unavailable.")
    _require(result["preview_control"]["title"] == "Preview & Control",
             "Preview & Control owner identity is unavailable.")
    return result


def _scroll_evidence(widget) -> dict[str, object]:
    scroll = getattr(widget, "_workflowContentScrollArea", None)
    _require(scroll is not None, "Workflow scroll area is unavailable.")
    bar = scroll.verticalScrollBar()
    return {
        "minimum": int(_qt_value(bar, "minimum")),
        "maximum": int(_qt_value(bar, "maximum")),
        "value": int(_qt_value(bar, "value")),
        "page_step": int(_qt_value(bar, "pageStep")),
    }


def _layout_evidence(widget, panel) -> dict[str, object]:
    controls = {
        "tcp_drag": panel.tcpDragEnabledCheckBox,
        "translation_step": panel.tcpTranslationStepMm,
        "rotation_step": panel.tcpRotationStepDeg,
        "keyboard_opt_in": panel.tcpKeyboardEnabledCheckBox,
        "solve_ik": panel.solveIkButton,
        **{
            f"nudge_{'rotation' if key[0] else 'translation'}_{key[1]}_{'plus' if key[2] > 0 else 'minus'}": control
            for key, control in panel.tcpCartesianNudgeButtons.items()
        },
    }
    return {
        "control_rectangles": {name: _rect(control) for name, control in controls.items()},
        "scroll_range": _scroll_evidence(widget),
        "owners": _owners(panel),
    }


def _preconditions(widget, panel, facade, run_dir, capture_callback, mouse_callback,
                   require_case_scene):
    path = Path(run_dir)
    _require(path.is_absolute(), "run_dir must be absolute.")
    _require(not path.is_symlink(), "run_dir must not be a symlink.")
    _require(path.is_dir(), "run_dir must be an existing directory.")
    path = path.resolve(strict=True)
    _require(tuple(bridge.ROS2_JOINT_SI_ORDER) == tuple(JOINT_NAMES),
             "ROS joint order is not exactly canonical J1–J5.")
    _require(callable(capture_callback), "capture_callback must be callable.")
    _require(mouse_callback is None or callable(mouse_callback),
             "mouse_drag_callback must be callable when supplied.")
    _require(widget is not None and panel is not None and facade is not None,
             "The current Step 6 widget, panel, and façade are required.")
    _require(int(getattr(panel, "_activeSubstep", -1)) == 3
             and panel.goalGroup.isVisible(),
             "The visible TCP workbench must be in Step 6.3B.")
    state = facade.currentRobotState()
    capabilities = facade.capabilities()
    _require(not require_case_scene or state.scene_kind == "case",
             "The current ROS scene is not case-backed.")
    _require(capabilities.simulation_only is True
             and capabilities.connected is True
             and state.ros_motion_active is True,
             "A live simulation-only ROS/MoveIt connection is not current.")
    _require(capabilities.planning_ready is True
             and capabilities.ik_available is True
             and capabilities.collision_check_available is True
             and capabilities.planning_scene_synchronized is True,
             "Current MoveIt planning, IK, collision validity, or scene is unavailable.")
    _require(state.base_locked is True, "The current robot base is not locked.")
    _require(not facade.previewActive and state.preview_active is False
             and not facade.returnHomeRequired
             and state.return_home_required is False,
             "A preview or return-home authority is active.")
    _require(facade.motionPlan is None
             and getattr(widget, "_step6MotionPlan", None) is None
             and state.has_motion_plan is False,
             "A route plan is already present.")
    _require(panel.tcpDragEnabledCheckBox.checked is False
             and panel._tcpDragEnabled is False
             and panel.tcpKeyboardEnabledCheckBox.checked is False
             and not panel.solveIkButton.enabled
             and not panel.planGoalButton.enabled,
             "TCP drag, keyboard, Solve IK, or route controls are unexpectedly enabled.")
    _require(not any(bool(item.enabled) for item in panel._tcpKeyboardShortcuts),
             "TCP keyboard shortcuts are enabled before opt-in.")
    probe_nodes = _nodes_named("ProbeSphere")
    goal_nodes = _nodes_named("ProbeSphere_Transform")
    _require(not probe_nodes and len(goal_nodes) <= 1,
             "A probe model or duplicate TCP goal already exists.")
    goal_transform = goal_nodes[0] if goal_nodes else None
    goal_scene_current = None
    goal_editor_enabled = False
    if goal_transform is not None:
        goal_scene_current = goal_transform.GetScene() == slicer.mrmlScene
        display_getter = getattr(goal_transform, "GetDisplayNode", None)
        _require(callable(display_getter),
                 "Cannot verify the pre-existing TCP goal display state.")
        display_node = display_getter()
        if display_node is not None:
            editor_visibility = getattr(display_node, "GetEditorVisibility", None)
            _require(callable(editor_visibility),
                     "Cannot verify the pre-existing TCP goal editor visibility.")
            goal_editor_enabled = bool(editor_visibility())
    goal_transform_passive = goal_transform is None or bool(
        require_case_scene and goal_scene_current and not goal_editor_enabled
    )
    _require(not probe_nodes and goal_transform_passive,
             "A TCP probe model or non-passive/out-of-scope goal already exists.")
    motion_logic = bridge.get_motion_control_logic()
    target_reference = getattr(motion_logic, "obsNode", None)
    observer_tag = getattr(motion_logic, "obsTag", None)
    native_drag_enabled = getattr(bridge, "_native_tcp_drag_enabled", None)
    target_reference_matches_passive_goal = bool(
        require_case_scene
        and goal_transform is not None
        and goal_transform_passive
        and target_reference == goal_transform
    )
    target_reference_allowed = (
        target_reference is None or target_reference_matches_passive_goal
    )
    _require(motion_logic is not None
             and target_reference_allowed
             and observer_tag is None
             and native_drag_enabled is False,
             "A TCP goal observer or native drag control is already active.")
    states = _joint_states(facade)
    owners = _owners(panel)
    _require(owners["planning_diagnostics"]["visible"] is True,
             "Planning & Diagnostics is not visible in Step 6.3B.")
    passive_goal_transform = (
        {"present": False}
        if goal_transform is None
        else {
            "present": True,
            "editor_enabled": goal_editor_enabled,
            "scene_current": bool(goal_scene_current),
        }
    )
    goal_transform_identity = (
        str(goal_transform.GetID()) if goal_transform is not None else None
    )
    goal_transform_matrix = _matrix(goal_transform) if goal_transform is not None else None
    native_observer = {
        "target_reference_present": target_reference is not None,
        "target_reference_matches_passive_goal": target_reference_matches_passive_goal,
        "installed_observer": observer_tag is not None,
        "native_drag_enabled": bool(native_drag_enabled),
    }
    return (
        path, state, capabilities, states, owners, passive_goal_transform,
        native_observer, goal_transform_identity, goal_transform_matrix,
    )


def _assert_states(facade, expected, count, label):
    actual = _joint_states(facade)
    if actual != expected:
        raise TcpProbeError(
            f"Accepted, monitored, or displayed J1–J5 state changed during {label}."
        )
    count[0] += 1


def _add_latency(samples, label, input_type, started_ns, observed_ns, delivery):
    latency_ns = int(observed_ns - started_ns)
    _require(latency_ns >= 0, f"{label} produced invalid monotonic timing evidence.")
    samples.append({
        "observation": label,
        "input_type": input_type,
        "delivery": delivery,
        "input_monotonic_ns": int(started_ns),
        "goal_observed_monotonic_ns": int(observed_ns),
        "latency_ns": latency_ns,
        "latency_ms": latency_ns / 1_000_000.0,
        "units": "ms",
    })


def _assert_direction(sample, translation_axis, rotation_axis, sign):
    before, after = sample["goal_before"], sample["goal_after"]
    if translation_axis is not None:
        delta = after[translation_axis][3] - before[translation_axis][3]
    elif rotation_axis == 1:
        delta = sum((after[r][2] - before[r][2]) * before[r][0] for r in range(3))
    else:
        delta = sum((after[r][0] - before[r][0]) * before[r][1] for r in range(3))
    _require(delta * sign > 0, f"{sample['observation']} moved in the wrong direction.")


def _rendezvous(view, baseline):
    renderer = view.renderWindow().GetRenderers().GetFirstRenderer()
    _require(renderer is not None, "Three-dimensional view renderer is unavailable.")
    renderer.SetWorldPoint(baseline[0][3], baseline[1][3], baseline[2][3], 1.0)
    renderer.WorldToDisplay()
    xyz = renderer.GetDisplayPoint()
    origin = view.mapToGlobal(qt.QPoint(0, 0))
    height = int(_qt_value(view, "height"))
    return {
        "global_center_top_origin": [
            int(origin.x() + xyz[0]), int(origin.y() + height - xyz[1])
        ],
        "view_origin": [int(origin.x()), int(origin.y())],
        "view_size": [int(_qt_value(view, "width")), height],
        "goal_before": baseline,
    }


def run_case_bound_tcp_probe(
    widget,
    panel,
    facade,
    run_dir,
    capture_callback,
    *,
    mouse_drag_callback=None,
    require_case_scene=True,
) -> dict[str, object]:
    """Run the current Step 6.3B TCP probe and return compact JSON evidence.

    The optional mouse callback receives a mapping with run_dir and rendezvous;
    it must deliver one external drag and return JSON-safe evidence with
    delivered set to true.
    """
    evidence: dict[str, object] = {
        "route_authority": False,
        "preview_started": False,
        "hardware_or_drilling_action": False,
        "planner_calls": 0,
        "captures": {},
        "latency_samples": [],
        "latency_summary": _latency_summary([]),
    }
    started = False
    failure = None
    try:
        (
            path, state, capabilities, states_before, owners_before,
            goal_transform_before, native_observer_before,
            goal_transform_identity, goal_transform_matrix,
        ) = _preconditions(
            widget, panel, facade, run_dir, capture_callback, mouse_drag_callback,
            require_case_scene,
        )
        evidence.update({
            "run_dir": str(path),
            "live_capabilities": {
                "simulation_only": bool(capabilities.simulation_only),
                "connected": bool(capabilities.connected),
                "planning_ready": bool(capabilities.planning_ready),
                "planning_scene_synchronized": bool(capabilities.planning_scene_synchronized),
                "scene_kind": str(state.scene_kind),
            },
            "accepted_state_before": states_before["accepted_si"],
            "accepted_monitored_displayed_before": states_before,
            "owners_before": owners_before,
            "passive_goal_transform_before": goal_transform_before,
            "native_observer_before": native_observer_before,
            "default_off": True,
        })
        samples = evidence["latency_samples"]
        state_checks = [0]
        monitor = lambda: _assert_states(facade, states_before, state_checks, "TCP probe")
        started = True
        _ensure_visible(widget, panel.tcpDragEnabledCheckBox, monitor)
        evidence["layout_before"] = _layout_evidence(widget, panel)
        evidence["captures"]["default_off"] = _json_safe(
            capture_callback("default_off"), "default_off screenshot evidence"
        )

        enable_started = time.monotonic_ns()
        panel.tcpDragEnabledCheckBox.click()
        _process_events(0.25, monitor)
        motion_logic = bridge.get_motion_control_logic()
        goal = slicer.util.getNode("ProbeSphere_Transform")
        probe = slicer.util.getNode("ProbeSphere")
        _require(
            panel.tcpDragEnabledCheckBox.checked and panel._tcpDragEnabled
            and goal is not None and probe is not None
            and motion_logic is not None and motion_logic.obsNode is not None
            and bool(getattr(bridge, "_native_tcp_drag_enabled", True)),
            "Explicit TCP enable did not receive native acknowledgement.",
        )
        _require(panel.solveIkButton.enabled,
                 "Authoritative Solve IK did not enable after TCP acknowledgement.")
        _add_latency(
            samples, "explicit_tcp_drag_enable_ack", "button", enable_started,
            time.monotonic_ns(),
            {"method": "production_panel_checkbox", "delivered": True},
        )
        evidence["native_enable_acknowledged"] = True
        evidence["captures"]["enabled"] = _json_safe(
            capture_callback("enabled"), "enabled screenshot evidence"
        )
        panel.tcpTranslationStepMm.value = 0.1
        panel.tcpRotationStepDeg.value = 0.1
        baseline = _matrix(goal)
        view = slicer.app.layoutManager().threeDWidget(0).threeDView()

        if mouse_drag_callback is None:
            evidence["mouse_drag"] = {
                "status": "NOT_RUN", "reason": "No mouse_drag_callback was supplied."
            }
        else:
            observer = _DragEventObserver(view)
            view.installEventFilter(observer)
            try:
                def wait_for_delivery():
                    deadline = time.monotonic() + DRAG_EVENT_TIMEOUT_SEC
                    while time.monotonic() < deadline:
                        monitor()
                        if (observer.first_drag_event_ns is not None
                                and observer.left_release_event_ns is not None):
                            return {
                                "delivered": True,
                                "event_monotonic_ns": observer.first_drag_event_ns,
                                "release_monotonic_ns": observer.left_release_event_ns,
                            }
                        _process_event_turn()
                    raise TcpProbeError(
                        "External wrapper did not deliver both a Qt mouse drag and "
                        "its left-button release within 30 seconds."
                    )

                delivery = _json_safe(mouse_drag_callback({
                    "run_dir": str(path),
                    "rendezvous": _rendezvous(view, baseline),
                    "wait_for_delivery": wait_for_delivery,
                }), "mouse drag delivery evidence")
                _require(isinstance(delivery, Mapping) and delivery.get("delivered") is True,
                         "External mouse callback did not confirm drag delivery.")
                after, observed_ns = _wait_goal_change(
                    goal, baseline, DRAG_EVENT_TIMEOUT_SEC, monitor
                )
                _require(observed_ns is not None and _changed(baseline, after),
                         "External mouse drag did not move the TCP goal.")
                _require(observer.first_drag_event_ns is not None,
                         "No external Qt mouse-drag event was observed.")
                release_ns = delivery.get("release_monotonic_ns")
                _require(observer.left_release_event_ns is not None
                         and isinstance(release_ns, int)
                         and not isinstance(release_ns, bool)
                         and release_ns == observer.left_release_event_ns
                         and release_ns >= observer.first_drag_event_ns,
                         "External mouse callback did not confirm the observed Qt left-button release.")
                mouse_sample = {
                    "observation": "mouse_drag",
                    "timing_scope": "first_drag_event_to_goal_read_after_left_release",
                    "input_type": "mouse",
                    "delivery": delivery,
                    "input_monotonic_ns": int(observer.first_drag_event_ns),
                    "release_monotonic_ns": int(observer.left_release_event_ns),
                    "goal_observed_monotonic_ns": int(observed_ns),
                    "latency_ns": int(observed_ns - observer.first_drag_event_ns),
                    "latency_ms": int(observed_ns - observer.first_drag_event_ns) / 1_000_000.0,
                    "units": "ms",
                    "goal_before": baseline,
                    "goal_after": after,
                    "goal_changed": True,
                }
                _require(mouse_sample["latency_ns"] >= 0,
                         "Mouse drag produced invalid monotonic timing evidence.")
                samples.append(mouse_sample)
                restored, message, _ = bridge.set_moveit_tcp_goal_matrix(baseline)
                _require(restored, f"Could not restore the current TCP baseline: {message}")
                _process_events(0.25, monitor)
                _require(not _changed(baseline, _matrix(goal)),
                         "TCP goal did not return to its captured current baseline.")
                evidence["mouse_drag"] = {
                    "status": "PASS",
                    "goal_changed": True,
                    "goal_reset_to_baseline": True,
                    "delivery": delivery,
                }
            finally:
                view.removeEventFilter(observer)
            evidence["captures"]["after_mouse_drag"] = _json_safe(
                capture_callback("after_mouse_drag"), "after_mouse_drag screenshot evidence"
            )

        button_cases = (
            ("button_translation_x_minus", (False, 0, -1.0)),
            ("button_translation_x_plus", (False, 0, 1.0)),
            ("button_translation_y_minus", (False, 1, -1.0)),
            ("button_translation_y_plus", (False, 1, 1.0)),
            ("button_translation_z_minus", (False, 2, -1.0)),
            ("button_translation_z_plus", (False, 2, 1.0)),
            ("button_pitch_minus", (True, 1, -1.0)),
            ("button_pitch_plus", (True, 1, 1.0)),
            ("button_yaw_minus", (True, 2, -1.0)),
            ("button_yaw_plus", (True, 2, 1.0)),
        )
        for label, key in button_cases:
            button = panel.tcpCartesianNudgeButtons.get(key)
            _require(button is not None, f"Cartesian nudge button is missing: {label}.")
            _ensure_visible(widget, button, monitor)
            _require(button.isEnabled(), f"Cartesian nudge button is disabled: {label}.")
            sample = _measure_goal_change(
                goal, label, "button",
                lambda control=button: (
                    control.click(),
                    {"method": "production_panel_button", "delivered": True},
                )[1],
                monitor=monitor,
            )
            _assert_direction(sample, None if key[0] else key[1],
                              key[1] if key[0] else None, key[2])
            samples.append(sample)
            evidence[label] = {"status": "PASS", "goal_changed": True}
        evidence["captures"]["after_buttons"] = _json_safe(
            capture_callback("after_buttons"), "after_buttons screenshot evidence"
        )

        repeat = [bool(item.autoRepeat) for item in panel._tcpKeyboardShortcuts]
        _require(bool(repeat) and not any(repeat),
                 "TCP keyboard shortcut auto-repeat is not disabled.")
        evidence["keyboard_auto_repeat_disabled"] = True
        target = panel.tcpCartesianNudgeButtons[(False, 0, 1.0)]
        _ensure_visible(widget, panel.tcpKeyboardEnabledCheckBox, monitor)
        keyboard_started = time.monotonic_ns()
        panel.tcpKeyboardEnabledCheckBox.click()
        _process_events(0.05, monitor)
        _require(panel.tcpKeyboardEnabledCheckBox.checked and all(
            bool(item.enabled) for item in panel._tcpKeyboardShortcuts
        ), "Explicit keyboard opt-in did not enable TCP shortcuts.")
        _add_latency(
            samples, "explicit_tcp_keyboard_enable", "button", keyboard_started,
            time.monotonic_ns(),
            {"method": "production_panel_checkbox", "delivered": True},
        )
        key_cases = (
            ("key_translation_x_plus", qt.Qt.Key_Right, qt.Qt.NoModifier, (0, None, 1.0)),
            ("key_pitch_plus", qt.Qt.Key_Up, qt.Qt.ControlModifier, (None, 1, 1.0)),
            ("key_yaw_plus", qt.Qt.Key_Right, qt.Qt.ShiftModifier, (None, 2, 1.0)),
        )
        evidence["key_delivery_method"] = None
        for label, key, modifiers, direction in key_cases:
            _ensure_visible(widget, target, monitor)
            _focus(target, monitor)
            sample = _measure_goal_change(
                goal, label, "key",
                lambda target=target, value=key, mods=modifiers:
                    _deliver_key(target, value, mods),
                monitor=monitor,
            )
            if evidence["key_delivery_method"] is None:
                evidence["key_delivery_method"] = sample["delivery"]["method"]
            _assert_direction(sample, direction[0], direction[1], direction[2])
            samples.append(sample)
            evidence[label] = {"status": "PASS", "goal_changed": True}

        numeric = panel.tcpTranslationStepMm
        _ensure_visible(widget, numeric, monitor)
        before = _matrix(goal)
        _focus(numeric, monitor)
        numeric_started = time.monotonic_ns()
        numeric_delivery = _deliver_key(numeric, qt.Qt.Key_Right, qt.Qt.NoModifier)
        _process_events(0.1, monitor)
        _require(not _changed(before, _matrix(goal)),
                 "TCP shortcut changed the goal while a numeric editor had focus.")
        _add_latency(
            samples, "numeric_editor_focus_suppression", "key", numeric_started,
            time.monotonic_ns(), numeric_delivery,
        )
        goal_layout = panel.goalGroup.layout()
        _require(goal_layout is not None, "TCP workbench layout is unavailable.")
        text_widget = qt.QLineEdit(panel.goalGroup)
        try:
            text_widget.setObjectName("DENTOBOTTcpTextFocusProbe")
            text_widget.setText("focus probe")
            goal_layout.addWidget(text_widget)
            text_widget.show()
            _ensure_visible(widget, text_widget, monitor)
            before = _matrix(goal)
            _focus(text_widget, monitor)
            text_started = time.monotonic_ns()
            text_delivery = _deliver_key(text_widget, qt.Qt.Key_Right, qt.Qt.NoModifier)
            _process_events(0.1, monitor)
            _require(not _changed(before, _matrix(goal)),
                     "TCP shortcut changed the goal while a text editor had focus.")
            _add_latency(
                samples, "text_editor_focus_suppression", "key", text_started,
                time.monotonic_ns(), text_delivery,
            )
        finally:
            goal_layout.removeWidget(text_widget)
            text_widget.hide()
            text_widget.setParent(None)
            text_widget.deleteLater()
            _process_events(0.02, monitor)
        evidence["editor_focus_suppressed"] = {
            "numeric": {"delivery": numeric_delivery, "goal_unchanged": True},
            "text": {"delivery": text_delivery, "goal_unchanged": True},
        }

        keyboard_off_started = time.monotonic_ns()
        panel.tcpKeyboardEnabledCheckBox.click()
        _process_events(0.05, monitor)
        _require(not panel.tcpKeyboardEnabledCheckBox.checked and not any(
            bool(item.enabled) for item in panel._tcpKeyboardShortcuts
        ), "Keyboard opt-out did not disable every TCP shortcut.")
        _add_latency(
            samples, "explicit_tcp_keyboard_opt_out", "button", keyboard_off_started,
            time.monotonic_ns(),
            {"method": "production_panel_checkbox", "delivered": True},
        )
        for label, key, modifiers in (
            ("translation", qt.Qt.Key_Right, qt.Qt.NoModifier),
            ("orientation", qt.Qt.Key_Up, qt.Qt.ControlModifier),
        ):
            _ensure_visible(widget, target, monitor)
            _focus(target, monitor)
            before = _matrix(goal)
            started_ns = time.monotonic_ns()
            delivery = _deliver_key(target, key, modifiers)
            _process_events(0.1, monitor)
            _require(not _changed(before, _matrix(goal)),
                     f"TCP shortcut remained active after opt-out ({label}).")
            _add_latency(
                samples, f"keyboard_opt_out_{label}_suppression", "key",
                started_ns, time.monotonic_ns(), delivery,
            )
        evidence["keyboard_opt_out_suppressed"] = {
            "goal_unchanged": True, "all_shortcuts_disabled": True
        }

        restored, message, _ = bridge.set_moveit_tcp_goal_matrix(baseline)
        _require(restored, f"Could not restore the current TCP baseline: {message}")
        _process_events(0.25, monitor)
        _require(not _changed(baseline, _matrix(goal)),
                 "Solve IK goal was not restored to the current baseline.")
        draft_before = _joint_map(panel.manualJogJointPositionsSi(), "Pre-solve draft")
        _ensure_visible(widget, panel.solveIkButton, monitor)
        solve_started = time.monotonic_ns()
        panel.solveIkButton.click()
        _process_events(0.05, monitor)
        solve_observed = time.monotonic_ns()
        staged = _joint_map(panel.manualJogJointPositionsSi(), "Staged Solve IK draft")
        native_solution = tuple(bridge.get_motion_control_logic().last_ik_solution or ())
        _require(len(native_solution) == 5,
                 "Authoritative Solve IK did not return exactly five joints.")
        native_values = tuple(float(value) for value in native_solution)
        _require(all(math.isfinite(value) for value in native_values),
                 "Authoritative Solve IK returned a non-finite joint value.")
        matches = all(
            math.isclose(staged[name], native_values[index], rel_tol=0.0, abs_tol=1e-9)
            for index, name in enumerate(JOINT_NAMES)
        )
        evidence["solve_ik_observation"] = {
            "native_solution_si": dict(zip(JOINT_NAMES, native_values)),
            "staged_draft_si": staged,
            "matches_native_solution": matches,
            "status_text": str(panel.goalStatusLabel.text),
        }
        _require(matches, "Staged draft does not match the authoritative five-joint solution.")
        solve_text = str(panel.goalStatusLabel.text)
        _require("authoritative MoveIt static validity" in solve_text,
                 "Solve IK did not report authoritative MoveIt static validity.")
        _require(facade.motionPlan is None
                 and getattr(widget, "_step6MotionPlan", None) is None
                 and not facade.previewActive,
                 "Solve IK created route or preview authority.")
        _add_latency(
            samples, "authoritative_solve_and_draft_stage", "button",
            solve_started, solve_observed,
            {"method": "production_panel_solve_ik_button", "delivered": True},
        )
        evidence["authoritative_solve"] = {
            "button_clicked": True,
            "success_message": solve_text,
            "joint_order": list(JOINT_NAMES),
            "joint_count": len(native_values),
            "staged_j1_j5": staged,
            "matches_native_solution": matches,
            "draft_before": draft_before,
            "goal_restored_to_current_baseline": True,
            "latency_ms": (solve_observed - solve_started) / 1_000_000.0,
        }
        evidence["captures"]["after_solve_ik"] = _json_safe(
            capture_callback("after_solve_ik"), "after_solve_ik screenshot evidence"
        )
    except Exception as exc:
        failure = exc if isinstance(exc, TcpProbeError) else TcpProbeError(
            f"{type(exc).__name__}: {exc}"
        )
    finally:
        if started:
            try:
                if panel.tcpKeyboardEnabledCheckBox.checked:
                    panel.tcpKeyboardEnabledCheckBox.click()
                if panel.tcpDragEnabledCheckBox.checked:
                    panel.tcpDragEnabledCheckBox.click()
                _process_events(0.25)
                motion_logic = bridge.get_motion_control_logic()
                goal_status, goal_ok = _passive_goal_cleanup_status(
                    goal_transform_identity, goal_transform_matrix
                )
                observer_node = getattr(motion_logic, "obsNode", None)
                observer_tag = getattr(motion_logic, "obsTag", None)
                observer_reference_allowed = observer_node is None or (
                    goal_transform_identity is not None
                    and str(observer_node.GetID()) == goal_transform_identity
                    and goal_status == "retained_passive"
                )
                cleanup = {
                    "probe_removed": not _nodes_named("ProbeSphere"),
                    "goal_removed_or_original_passive": goal_ok,
                    "goal_transform_status": goal_status,
                    "observer_removed": observer_tag is None and observer_reference_allowed,
                    "native_drag_off": getattr(
                        bridge, "_native_tcp_drag_enabled", None
                    ) is False,
                    "keyboard_checkbox_off": not panel.tcpKeyboardEnabledCheckBox.checked,
                    "tcp_drag_checkbox_off": not panel.tcpDragEnabledCheckBox.checked,
                    "keyboard_shortcuts_off": not any(
                        bool(item.enabled) for item in panel._tcpKeyboardShortcuts
                    ),
                }
                evidence["cleanup"] = cleanup
                _require(all(
                    value is True for key, value in cleanup.items()
                    if key != "goal_transform_status"
                ),
                         "TCP disable cleanup left a probe, goal, observer, or enabled key.")
                evidence["captures"]["disabled"] = _json_safe(
                    capture_callback("disabled"), "disabled screenshot evidence"
                )
                widget._configureRobotSimulationShellSubstep(4)
                _process_events(0.05)
                preview_owner = _owner(panel.previewControlGroup)
                _require(preview_owner["visible"] is True,
                         "Preview & Control did not become visible on its substep.")
                _ensure_visible(widget, panel.previewControlGroup)
                evidence["owners_by_substep"] = {
                    "step6_3b_before": owners_before,
                    "step6_preview": {
                        "planning_diagnostics": _owner(panel.approachGroup),
                        "preview_control": preview_owner,
                    },
                }
                evidence["captures"]["preview_control_owner"] = _json_safe(
                    capture_callback("preview_control_owner"),
                    "Preview & Control screenshot evidence",
                )
                widget._configureRobotSimulationShellSubstep(3)
                _process_events(0.05)
                reentry_goal_status, reentry_goal_ok = _passive_goal_cleanup_status(
                    goal_transform_identity, goal_transform_matrix
                )
                motion_logic = bridge.get_motion_control_logic()
                observer_node = getattr(motion_logic, "obsNode", None)
                observer_tag = getattr(motion_logic, "obsTag", None)
                observer_reference_allowed = observer_node is None or (
                    goal_transform_identity is not None
                    and str(observer_node.GetID()) == goal_transform_identity
                    and reentry_goal_status == "retained_passive"
                )
                reentered = {
                    "substep_3": int(panel._activeSubstep) == 3,
                    "tcp_drag_default_off": not panel.tcpDragEnabledCheckBox.checked
                    and not panel._tcpDragEnabled,
                    "keyboard_default_off": not panel.tcpKeyboardEnabledCheckBox.checked
                    and not any(bool(item.enabled) for item in panel._tcpKeyboardShortcuts),
                    "probe_removed": not _nodes_named("ProbeSphere"),
                    "goal_removed_or_original_passive": reentry_goal_ok,
                    "goal_transform_status": reentry_goal_status,
                    "observer_removed": observer_tag is None and observer_reference_allowed,
                    "native_drag_off": getattr(
                        bridge, "_native_tcp_drag_enabled", None
                    ) is False,
                }
                reentry_ok = all(
                    value is True for key, value in reentered.items()
                    if key != "goal_transform_status"
                )
                evidence["reentered"] = reentered
                cleanup["default_off_after_reentry"] = reentry_ok
                cleanup["goal_transform_status_after_reentry"] = reentry_goal_status
                _require(reentry_ok,
                         "Step 6.3B re-entry did not return to clean default-off state.")
                _ensure_visible(widget, panel.approachGroup)
                evidence["owners_by_substep"]["step6_3b_after"] = _owners(panel)
                evidence["captures"]["planning_diagnostics_owner"] = _json_safe(
                    capture_callback("planning_diagnostics_owner"),
                    "Planning & Diagnostics screenshot evidence",
                )
                evidence["layout_after"] = _layout_evidence(widget, panel)
                if "accepted_state_before" in evidence:
                    states_after = _joint_states(facade)
                    evidence["accepted_monitored_displayed_after"] = states_after
                    _require(states_after == evidence["accepted_monitored_displayed_before"],
                             "Accepted, monitored, or displayed J1–J5 state changed during probe or cleanup.")
                    evidence["accepted_state"] = {
                        "before_si": evidence["accepted_state_before"],
                        "after_si": states_after["accepted_si"],
                        "unchanged": True,
                        "state_check_count": state_checks[0],
                    }
            except Exception as exc:
                evidence["cleanup_failure"] = f"{type(exc).__name__}: {exc}"
                if failure is None:
                    failure = exc if isinstance(exc, TcpProbeError) else TcpProbeError(
                        f"Cleanup failed: {type(exc).__name__}: {exc}"
                    )
        evidence["latency_summary"] = _latency_summary(evidence["latency_samples"])
    if failure is not None:
        failure.evidence = evidence
        raise failure
    evidence["latency_interpretation"] = (
        "Observed action-to-state-read durations; mouse timing includes completed "
        "drag/release before the goal read. Not first-paint latency, FPS, or a safety claim."
    )
    return _json_safe(evidence, "TCP probe evidence")


def run() -> int:
    run_dir, evidence_dir, result_path = _execution_paths()
    mouse_requested = _mouse_drag_requested()
    result: dict[str, object] = {
        "schema_version": "1.0",
        "status": "RUNNING",
        "case_source": None,
        "case_loaded": False,
        "run_dir": str(run_dir),
        "evidence_dir": str(evidence_dir),
        "mouse_drag_requested": mouse_requested,
        "latency_samples": [],
        "latency_summary": _latency_summary([]),
        "route_authority": False,
        "preview_started": False,
        "hardware_or_drilling_action": False,
        "planner_calls": 0,
    }
    _write_json(result_path, result, exclusive=True)
    try:
        result["checkout"] = _checkout_provenance()
        result["native"] = _native_provenance()
        slicer.util.selectModule("DENTOWorkflow")
        _process_events(1.0)
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        if widget is None:
            raise RuntimeError("DENTO Workflow module widget is unavailable.")
        widget._setWorkflowStage(len(widget._workflowStageEntries()) - 1)
        widget._configureRobotSimulationShellSubstep(3)
        _process_events(0.25)
        base = widget.logic.ensureRobotBaseTransform(widget._parameterNode.robotBaseTransform)
        widget._parameterNode.robotBaseTransform = base
        robot, message = bridge.connect_dentobot_motion_control(
            base,
            hide_mrml_robot=False,
            mrml_robot_models=[],
            open_motion_module=False,
            start_stack_if_needed=False,
            start_joint_command_stream=False,
        )
        if robot is None:
            raise RuntimeError(f"Simulation-only ROS/MoveIt connection failed: {message}")
        widget._refreshShellRobotCapabilities()
        widget._updateStep6PlanningUi()
        panel = widget._robotSimulationPanel
        facade = widget._robotWorkflowFacade
        image_names = {
            "default_off": "01-default-off.png",
            "enabled": "02-enabled.png",
            "after_mouse_drag": "03-after-mouse-drag.png",
            "after_buttons": "04-after-buttons.png",
            "after_solve_ik": "05-after-solve-ik.png",
            "disabled": "06-disabled.png",
            "preview_control_owner": "07-preview-control-owner.png",
            "planning_diagnostics_owner": "08-planning-diagnostics-owner.png",
        }

        def capture_callback(stage):
            return _capture(evidence_dir, image_names[stage])

        probe = run_case_bound_tcp_probe(
            widget,
            panel,
            facade,
            run_dir,
            capture_callback,
            mouse_drag_callback=(
                make_external_mouse_drag_callback(run_dir) if mouse_requested else None
            ),
            require_case_scene=False,
        )
        result.update(probe)
        result["evidence_dir"] = str(evidence_dir)
        result["screenshots"] = probe["captures"]
        if not mouse_requested:
            result["mouse_drag"] = {
                "status": "NOT_RUN",
                "reason": "external rendezvous opt-in is disabled",
            }
        result["status"] = "PASS"
    except Exception as exc:
        if hasattr(exc, "evidence"):
            result.update(exc.evidence)
            result["evidence_dir"] = str(evidence_dir)
            result["screenshots"] = result.get("captures", {})
        result["failure"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
        result["status"] = "FAIL"
    _write_json(result_path, result)
    marker = f"DENTOBOT_TCP_WORKBENCH_HEADED_{result['status']}"
    print(marker, json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    return 1 if result["status"] != "PASS" else 0


if __name__ == "__main__":
    try:
        exit_code = run()
    except Exception:
        traceback.print_exc()
        slicer.util.exit(1)
    else:
        slicer.util.exit(exit_code)
