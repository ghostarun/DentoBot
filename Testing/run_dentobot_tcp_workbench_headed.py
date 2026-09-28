"""Headed no-case TCP workbench check with physical Qt key delivery."""

from __future__ import annotations

import hashlib
import json
import math
import os
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
DRAG_EVENT_TIMEOUT_SEC = 25.0
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


def _changed(before, after, tolerance: float = 1e-6) -> bool:
    return any(
        abs(float(before[row][column]) - float(after[row][column])) > tolerance
        for row in range(4)
        for column in range(4)
    )


def _process_events(seconds: float = 0.02) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        _process_event_turn()
        time.sleep(0.005)


def _process_event_turn() -> None:
    slicer.app.processEvents()
    logic = slicer.util.getModuleLogic("ROS2")
    if logic is not None:
        logic.Spin()


def _wait_goal_change(goal, before, timeout_sec: float = GOAL_CHANGE_TIMEOUT_SEC):
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
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
) -> dict[str, object]:
    before = _matrix(goal)
    started_ns = time.monotonic_ns()
    delivery = action()
    after, observed_ns = _wait_goal_change(goal, before)
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


def _focus(widget) -> None:
    widget.setFocus()
    _process_events(0.05)
    focused = qt.QApplication.focusWidget()
    if focused is not widget and focused != widget:
        raise RuntimeError("Could not give the requested visible workbench widget focus.")


def _ensure_visible(workflow_widget, control) -> None:
    scroll = getattr(workflow_widget, "_workflowContentScrollArea", None)
    if scroll is not None:
        scroll.ensureWidgetVisible(control, 0, 20)
    _process_events(0.05)
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

    def eventFilter(self, _watched, event):
        if self.first_drag_event_ns is None and event.type() == qt.QEvent.MouseMove:
            buttons = getattr(event, "buttons", 0)
            buttons = buttons() if callable(buttons) else buttons
            if int(buttons) & int(qt.Qt.LeftButton):
                self.first_drag_event_ns = time.monotonic_ns()
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


def _unchanged(before, after, label: str) -> dict[str, object]:
    changed = before != after
    if changed:
        raise RuntimeError(f"Accepted J1–J5 state changed during {label}.")
    return {"before_si": before, "after_si": after, "unchanged": True}


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
    widget = panel = None
    failure = None
    samples: list[dict[str, object]] = []
    screenshots: dict[str, str] = {}
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
        if panel is None or not panel.goalGroup.isVisible():
            raise RuntimeError("The Step 6.3 TCP workbench is not visible.")
        _ensure_visible(widget, panel.tcpDragEnabledCheckBox)
        if panel.tcpDragEnabledCheckBox.checked or panel._tcpDragEnabled:
            raise RuntimeError("TCP probe was not default-off before explicit enable.")
        if (
            panel.tcpKeyboardEnabledCheckBox.checked
            or panel.solveIkButton.enabled
            or panel.planGoalButton.enabled
        ):
            raise RuntimeError("TCP keyboard/Solve IK/route controls were unexpectedly enabled before probe opt-in.")
        if (
            slicer.mrmlScene.GetFirstNodeByName("ProbeSphere") is not None
            or slicer.mrmlScene.GetFirstNodeByName("ProbeSphere_Transform") is not None
        ):
            raise RuntimeError("Default-off TCP probe already exists in the MRML scene.")
        screenshots["default_off"] = _capture(evidence_dir, "01-default-off.png")
        result["default_off"] = True

        result["accepted_state_before"] = _joint_snapshot(widget, bridge.ROS2_JOINT_SI_ORDER)

        panel.tcpDragEnabledCheckBox.click()
        _process_events(0.25)
        motion_logic = bridge.get_motion_control_logic()
        goal = slicer.util.getNode("ProbeSphere_Transform")
        probe = slicer.util.getNode("ProbeSphere")
        if not (
            panel.tcpDragEnabledCheckBox.checked
            and panel._tcpDragEnabled
            and goal is not None
            and probe is not None
            and motion_logic is not None
            and motion_logic.obsNode is not None
        ):
            raise RuntimeError("Explicit TCP enable did not receive and retain native acknowledgement.")
        if not panel.solveIkButton.enabled:
            raise RuntimeError("Authoritative Solve IK did not enable after TCP acknowledgement.")
        result["native_enable_acknowledged"] = True
        screenshots["enabled"] = _capture(evidence_dir, "02-enabled.png")

        panel.tcpTranslationStepMm.value = 0.1
        panel.tcpRotationStepDeg.value = 0.1
        view = slicer.app.layoutManager().threeDWidget(0).threeDView()
        if mouse_requested:
            observer = _DragEventObserver(view)
            view.installEventFilter(observer)
            try:
                before = _matrix(goal)
                ras = [before[0][3], before[1][3], before[2][3]]
                renderer = view.renderWindow().GetRenderers().GetFirstRenderer()
                if renderer is None:
                    raise RuntimeError("Three-dimensional view renderer is unavailable.")
                renderer.SetWorldPoint(ras[0], ras[1], ras[2], 1.0)
                renderer.WorldToDisplay()
                xyz = renderer.GetDisplayPoint()
                origin = view.mapToGlobal(qt.QPoint(0, 0))
                height = int(view.height)
                rendezvous = {
                    "global_center_top_origin": [
                        int(origin.x() + xyz[0]),
                        int(origin.y() + height - xyz[1]),
                    ],
                    "view_origin": [int(origin.x()), int(origin.y())],
                    "view_size": [int(view.width), height],
                    "goal_before": before,
                }
                _write_json(run_dir / "drag-ready.json", rendezvous, exclusive=True)
                print("DENTOBOT_TCP_DRAG_READY", json.dumps(rendezvous, sort_keys=True), flush=True)
                after, observed_ns = _wait_goal_change(goal, before, DRAG_EVENT_TIMEOUT_SEC)
                if observed_ns is None or not _changed(before, after):
                    raise RuntimeError("External xdotool rendezvous did not move the TCP goal.")
                if observer.first_drag_event_ns is None:
                    raise RuntimeError("No Qt mouse-drag event was observed from the external wrapper.")
                latency_ns = int(observed_ns - observer.first_drag_event_ns)
                if latency_ns < 0:
                    raise RuntimeError("Mouse drag produced invalid monotonic latency evidence.")
                samples.append({
                    "observation": "mouse_drag",
                    "input_type": "mouse",
                    "delivery": {"method": "external_xdotool_rendezvous", "delivered": True},
                    "input_monotonic_ns": int(observer.first_drag_event_ns),
                    "goal_observed_monotonic_ns": int(observed_ns),
                    "latency_ns": latency_ns,
                    "latency_ms": latency_ns / 1_000_000.0,
                    "units": "ms",
                    "goal_before": before,
                    "goal_after": after,
                    "goal_changed": True,
                })
                restored, restore_message, _restored_goal = bridge.set_moveit_tcp_goal_matrix(before)
                if not restored:
                    raise RuntimeError(f"Could not restore the pre-drag review goal: {restore_message}")
                _process_events(0.25)
                if _changed(before, _matrix(goal)):
                    raise RuntimeError("TCP review goal did not return to its pre-drag matrix.")
                result["mouse_drag"] = {
                    "status": "PASS",
                    "goal_changed": True,
                    "goal_reset_to_baseline": True,
                }
            finally:
                view.removeEventFilter(observer)
                observer = None
            screenshots["after_mouse_drag"] = _capture(evidence_dir, "03-after-mouse-drag.png")
        else:
            result["mouse_drag"] = {"status": "NOT_RUN", "reason": "external rendezvous opt-in is disabled"}

        button_cases = (
            ("button_translation_x_plus", (False, 0, 1.0)),
            ("button_pitch_plus", (True, 1, 1.0)),
            ("button_yaw_plus", (True, 2, 1.0)),
        )
        for label, key in button_cases:
            button = panel.tcpCartesianNudgeButtons.get(key)
            if button is None:
                raise RuntimeError(f"Visible enabled Cartesian nudge button is missing: {label}.")
            _ensure_visible(widget, button)
            if not button.isEnabled():
                raise RuntimeError(f"Cartesian nudge button is disabled: {label}.")
            sample = _measure_goal_change(
                goal, label, "button", lambda control=button: control.click()
            )
            samples.append(sample)
            result[label] = {"status": "PASS", "goal_changed": sample["goal_changed"]}
        screenshots["after_buttons"] = _capture(evidence_dir, "04-after-buttons.png")

        shortcut_auto_repeat = [bool(shortcut.autoRepeat) for shortcut in panel._tcpKeyboardShortcuts]
        if not shortcut_auto_repeat or any(shortcut_auto_repeat):
            raise RuntimeError("TCP keyboard shortcut auto-repeat is not disabled.")
        result["keyboard_auto_repeat_disabled"] = True

        key_target = panel.tcpCartesianNudgeButtons[(False, 0, 1.0)]
        _ensure_visible(widget, panel.tcpKeyboardEnabledCheckBox)
        panel.tcpKeyboardEnabledCheckBox.click()
        _process_events(0.05)
        if not panel.tcpKeyboardEnabledCheckBox.checked or not all(
            bool(shortcut.enabled) for shortcut in panel._tcpKeyboardShortcuts
        ):
            raise RuntimeError("Explicit keyboard opt-in did not enable TCP shortcuts.")
        key_cases = (
            ("key_translation_x_plus", qt.Qt.Key_Right, qt.Qt.NoModifier),
            ("key_pitch_plus", qt.Qt.Key_Up, qt.Qt.ControlModifier),
            ("key_yaw_plus", qt.Qt.Key_Right, qt.Qt.ShiftModifier),
        )
        result["key_delivery_method"] = None
        for label, key, modifiers in key_cases:
            _ensure_visible(widget, key_target)
            _focus(key_target)
            sample = _measure_goal_change(
                goal,
                label,
                "key",
                lambda target=key_target, value=key, mods=modifiers:
                    _deliver_key(target, value, mods),
            )
            if result["key_delivery_method"] is None:
                result["key_delivery_method"] = sample["delivery"]["method"]
            samples.append(sample)
            result[label] = {"status": "PASS", "goal_changed": sample["goal_changed"]}

        focus_before = _matrix(goal)
        numeric = panel.tcpTranslationStepMm
        numeric_before = float(numeric.value)
        _ensure_visible(widget, numeric)
        _focus(numeric)
        focus_delivery = _deliver_key(numeric, qt.Qt.Key_Right, qt.Qt.NoModifier)
        _process_events(0.1)
        focus_after = _matrix(goal)
        if _changed(focus_before, focus_after):
            raise RuntimeError("TCP shortcut changed the goal while a numeric editor had focus.")
        result["numeric_editor_focus_suppressed"] = {
            "delivery": focus_delivery,
            "goal_unchanged": True,
            "focus_widget": "QDoubleSpinBox",
            "numeric_value_before": numeric_before,
            "numeric_value_after": float(numeric.value),
        }

        panel.tcpKeyboardEnabledCheckBox.click()
        _process_events(0.05)
        if panel.tcpKeyboardEnabledCheckBox.checked or any(
            bool(shortcut.enabled) for shortcut in panel._tcpKeyboardShortcuts
        ):
            raise RuntimeError("Keyboard opt-out did not disable every TCP shortcut.")
        _ensure_visible(widget, key_target)
        _focus(key_target)
        opt_out_before = _matrix(goal)
        opt_out_delivery = _deliver_key(key_target, qt.Qt.Key_Right, qt.Qt.NoModifier)
        _process_events(0.1)
        if _changed(opt_out_before, _matrix(goal)):
            raise RuntimeError("TCP shortcut remained active after explicit keyboard opt-out.")
        opt_out_orientation_before = _matrix(goal)
        opt_out_orientation_delivery = _deliver_key(
            key_target, qt.Qt.Key_Up, qt.Qt.ControlModifier
        )
        _process_events(0.1)
        if _changed(opt_out_orientation_before, _matrix(goal)):
            raise RuntimeError("TCP orientation shortcut remained active after keyboard opt-out.")
        result["keyboard_opt_out_suppressed"] = {
            "translation_delivery": opt_out_delivery,
            "orientation_delivery": opt_out_orientation_delivery,
            "goal_unchanged": True,
            "all_shortcuts_disabled": True,
        }

        accepted_before = result["accepted_state_before"]
        draft_before_solve = panel.manualJogJointPositionsSi()
        _ensure_visible(widget, panel.solveIkButton)
        solve_started_ns = time.monotonic_ns()
        panel.solveIkButton.click()
        _process_events(1.0)
        solve_observed_ns = time.monotonic_ns()
        staged = panel.manualJogJointPositionsSi()
        native_solution = tuple(bridge.get_motion_control_logic().last_ik_solution or ())
        order = tuple(bridge.ROS2_JOINT_SI_ORDER)
        if len(order) != 5 or len(native_solution) != 5 or set(staged) != set(order):
            raise RuntimeError("Authoritative Solve IK did not produce exactly five staged joints.")
        staged_matches_solution = all(
            math.isclose(float(staged[name]), float(native_solution[index]), rel_tol=0.0, abs_tol=1e-9)
            for index, name in enumerate(order)
        )
        if not staged_matches_solution:
            raise RuntimeError("Staged J1–J5 draft does not match the authoritative Solve IK result.")
        solve_text = str(panel.goalStatusLabel.text)
        if "authoritative MoveIt static validity" not in solve_text:
            raise RuntimeError("Solve IK did not report authoritative MoveIt static validity.")
        solve_timing = {
            "input_type": "button",
            "observation": "authoritative_solve_and_draft_stage",
            "input_monotonic_ns": solve_started_ns,
            "draft_observed_monotonic_ns": solve_observed_ns,
            "latency_ns": solve_observed_ns - solve_started_ns,
            "latency_ms": (solve_observed_ns - solve_started_ns) / 1_000_000.0,
            "units": "ms",
            "draft_before": draft_before_solve,
            "draft_after": staged,
            "staged_matches_authoritative_five_joint_solution": True,
        }
        screenshots["after_solve_ik"] = _capture(evidence_dir, "05-after-solve-ik.png")

        accepted_after = _joint_snapshot(widget, order)
        result["accepted_state"] = _unchanged(accepted_before, accepted_after, "TCP exploration and Solve IK")
        result["authoritative_solve"] = {
            "button_clicked": True,
            "success_message": solve_text,
            "joint_order": list(order),
            "joint_count": len(native_solution),
            "staged_j1_j5": staged,
            "matches_native_solution": staged_matches_solution,
            "latency": solve_timing,
        }
        result["route_authority"] = False
        result["preview_started"] = False
        result["hardware_or_drilling_action"] = False
        result["planner_calls"] = 0
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
        result["failure"] = failure
        result["traceback"] = traceback.format_exc()
    finally:
        if panel is not None:
            try:
                if panel.tcpKeyboardEnabledCheckBox.checked:
                    panel.tcpKeyboardEnabledCheckBox.click()
                if panel.tcpDragEnabledCheckBox.checked:
                    panel.tcpDragEnabledCheckBox.click()
                _process_events(0.25)
                motion_logic = bridge.get_motion_control_logic()
                result["cleanup"] = {
                    "probe_removed": slicer.mrmlScene.GetFirstNodeByName("ProbeSphere") is None,
                    "goal_removed": slicer.mrmlScene.GetFirstNodeByName("ProbeSphere_Transform") is None,
                    "observer_removed": motion_logic is None or motion_logic.obsNode is None,
                    "keyboard_checkbox_off": not panel.tcpKeyboardEnabledCheckBox.checked,
                    "tcp_drag_checkbox_off": not panel.tcpDragEnabledCheckBox.checked,
                }
                cleanup = result["cleanup"]
                if not all(cleanup.values()):
                    raise RuntimeError("TCP disable cleanup left a probe, goal, observer, or enabled key.")
                screenshots["disabled"] = _capture(evidence_dir, "06-disabled.png")
            except Exception as exc:
                failure = failure or f"Cleanup failed: {type(exc).__name__}: {exc}"
                result["cleanup_failure"] = f"{type(exc).__name__}: {exc}"
        result["latency_samples"] = samples
        result["latency_summary"] = _latency_summary(samples)
        result["screenshots"] = screenshots
        if failure is None:
            try:
                if widget is not None:
                    accepted_end = _joint_snapshot(widget, bridge.ROS2_JOINT_SI_ORDER)
                    result["accepted_state_final"] = _unchanged(
                        result["accepted_state_before"], accepted_end, "runner cleanup"
                    )
            except Exception as exc:
                failure = f"Final state check failed: {type(exc).__name__}: {exc}"
        result["status"] = "FAIL" if failure else "PASS"
        if failure:
            result["failure"] = failure
        _write_json(result_path, result)

    marker = f"DENTOBOT_TCP_WORKBENCH_HEADED_{result['status']}"
    print(marker, json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    return 1 if result["status"] != "PASS" else 0


try:
    exit_code = run()
except Exception:
    traceback.print_exc()
    slicer.util.exit(1)
else:
    slicer.util.exit(exit_code)
