"""Source gates for the bounded no-case TCP headed runner."""

import ast
import math
import os
from pathlib import Path
import statistics
from types import SimpleNamespace

import pytest


TESTING = Path(__file__).resolve().parent
RUNNER = TESTING / "run_dentobot_tcp_workbench_headed.py"
SOURCE = RUNNER.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
PANEL = (TESTING.parent / "DENTOWorkflow/Resources/Python/DENTORobotSimulationPanel.py").read_text(
    encoding="utf-8"
)


def _function(tree, name):
    return next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def _calls(tree):
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    ]


def _attribute_calls(tree):
    return {
        node.func.attr
        for node in _calls(tree)
        if isinstance(node.func, ast.Attribute)
    }


def _string_constants(tree):
    return {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _run_helper(name, globals_):
    node = _function(TREE, name)
    module = ast.Module(body=[node], type_ignores=[])
    namespace = dict(globals_)
    exec(compile(ast.fix_missing_locations(module), str(RUNNER), "exec"), namespace)
    return namespace[name]


def test_exact_checkout_native_and_fresh_evidence_provenance_are_required():
    execution_paths = ast.unparse(_function(TREE, "_execution_paths"))
    checkout = ast.unparse(_function(TREE, "_checkout_provenance"))
    native = ast.unparse(_function(TREE, "_native_provenance"))
    for variable in (
        "DENTOBOT_HEADED_EVIDENCE_DIR",
        "DENTOBOT_HEADED_HOST_CHECKOUT_ROOT",
        "DENTOBOT_HEADED_GIT_BRANCH",
        "DENTOBOT_HEADED_GIT_HEAD",
        "DENTOBOT_HEADED_GIT_STATUS_SHA256",
    ):
        assert variable in execution_paths + checkout
    for variable in (
        "DENTOBOT_HEADED_NATIVE_SOURCE_SHA256",
        "DENTOBOT_HEADED_NATIVE_BINARY_SHA256",
        "DENTOBOT_HEADED_NATIVE_PACKAGE_PREFIX",
    ):
        assert variable in native
    assert "get_package_prefix" in native and "dentobot_moveit_config" in native
    assert "collision_guard.cpp" in native
    assert "NATIVE_BINARY_RELATIVE_PATH" in native
    assert "EXPECTED_HOST_ROOT" in checkout and "EXPECTED_BRANCH" in checkout
    assert "runner_sha256" in checkout and "source_sha256" in checkout
    assert "Refusing to overwrite an existing result.json" in execution_paths
    assert "Evidence directory must be fresh and empty" in execution_paths
    assert "DENTOBOT_HEADED_EVIDENCE_DIR must be the run's evidence/ directory" in execution_paths


def test_key_delivery_sends_qt_events_and_fails_closed_without_delivery_api():
    delivery = _function(TREE, "_deliver_key")
    source = ast.unparse(delivery)
    calls = _calls(delivery)
    assert "QTest" in source and "keyClick" in source
    assert "QKeyEvent" in source and "KeyPress" in source and "KeyRelease" in source
    assert "QApplication" in source and "sendEvent" in source
    assert "refusing callback fallback" in source
    assert any(
        isinstance(call.func, ast.Name) and call.func.id == "key_event"
        for call in calls
    )
    assert any(
        isinstance(call.func, ast.Name) and call.func.id == "send_event"
        and len(call.args) == 2
        and isinstance(call.args[0], ast.Name) and call.args[0].id == "widget"
        for call in calls
    )
    assert not ({"_onTcpKeyboardNudge", "_onTcpCartesianNudge"} & _attribute_calls(delivery))

    sent = []
    target = object()

    def send_event(widget, event):
        sent.append((widget, event))
        return True

    qtest_calls = []
    qtest = SimpleNamespace(keyClick=lambda widget, key, mods: qtest_calls.append((widget, key, mods)))
    deliver = _run_helper("_deliver_key", {"qt": SimpleNamespace(QTest=qtest)})
    assert deliver(target, 39, 0) == {"method": "qt.QTest.keyClick", "delivered": True}
    assert qtest_calls == [(target, 39, 0)]

    constructed = []

    def key_event(*args):
        event = object()
        constructed.append((args, event))
        return event

    fallback_qt = SimpleNamespace(
        QTest=None,
        QKeyEvent=key_event,
        QApplication=SimpleNamespace(sendEvent=send_event),
        QEvent=SimpleNamespace(KeyPress=6, KeyRelease=7),
    )
    deliver = _run_helper("_deliver_key", {"qt": fallback_qt})
    assert deliver(target, 39, 4) == {
        "method": "QApplication.sendEvent(QKeyEvent)",
        "delivered": True,
    }
    assert [args for args, _event in constructed] == [
        (6, 39, 4, "", False, 1),
        (7, 39, 4, "", False, 1),
    ]
    assert [widget for widget, _event in sent] == [target, target]
    assert [event for _widget, event in sent] == [event for _args, event in constructed]

    deliver = _run_helper(
        "_deliver_key",
        {"qt": SimpleNamespace(QTest=None, QKeyEvent=None, QApplication=object(), QEvent=None)},
    )
    with pytest.raises(RuntimeError, match="refusing callback fallback"):
        deliver(target, 39, 0)


def test_runner_delivers_representative_translation_pitch_and_yaw_keys_to_focused_widgets():
    run = ast.unparse(_function(TREE, "run"))
    assert "qt.Qt.Key_Right" in run and "qt.Qt.NoModifier" in run
    assert "qt.Qt.Key_Up" in run and "qt.Qt.ControlModifier" in run
    assert "qt.Qt.ShiftModifier" in run
    assert "_focus(key_target)" in run
    assert "_deliver_key(target, value, mods)" in run
    assert "tcpKeyboardEnabledCheckBox.click()" in run
    assert "numeric_editor_focus_suppressed" in run
    assert "keyboard_opt_out_suppressed" in run
    assert "focus_widget" in run and "QDoubleSpinBox" in _string_constants(_function(TREE, "run"))


def test_production_shortcut_gates_match_runner_focus_repeat_and_opt_out_checks():
    assert "shortcut.autoRepeat = False" in PANEL
    assert "shortcut.enabled = keyboard_allowed" in PANEL
    assert "not self.tcpKeyboardEnabledCheckBox.checked" in PANEL
    assert "or self._hasTcpTextEditorFocus()" in PANEL
    assert "QAbstractSpinBox" in PANEL
    run = ast.unparse(_function(TREE, "run"))
    assert "shortcut_auto_repeat" in run
    assert "all_shortcuts_disabled" in run
    assert "all" in _attribute_calls(_function(TREE, "run")) | {
        node.id for node in ast.walk(_function(TREE, "run")) if isinstance(node, ast.Name)
    }


def test_optional_mouse_rendezvous_preserves_xdotool_contract_and_times_qt_drag_event():
    mouse_opt_in = _run_helper("_mouse_drag_requested", {"os": os})
    old = os.environ.get("DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG")
    try:
        os.environ.pop("DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG", None)
        assert mouse_opt_in() is False
        os.environ["DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG"] = "0"
        assert mouse_opt_in() is False
        os.environ["DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG"] = "1"
        assert mouse_opt_in() is True
        os.environ["DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG"] = "yes"
        with pytest.raises(RuntimeError, match="must be '1', '0', or unset"):
            mouse_opt_in()
    finally:
        if old is None:
            os.environ.pop("DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG", None)
        else:
            os.environ["DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG"] = old

    source = SOURCE
    assert 'run_dir / "drag-ready.json"' in source
    assert '"global_center_top_origin"' in source
    assert '"view_origin"' in source and '"view_size"' in source
    assert '"DENTOBOT_TCP_DRAG_READY"' in source
    assert "qt.QEvent.MouseMove" in source and "qt.Qt.LeftButton" in source
    assert "view.installEventFilter(observer)" in source
    assert "view.removeEventFilter(observer)" in source
    assert "first_drag_event_ns = time.monotonic_ns()" in source
    assert "external_xdotool_rendezvous" in source
    assert "goal_reset_to_baseline" in source
    assert "DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG" in source


def test_button_and_key_goal_changes_use_monotonic_input_latency_samples_and_summary():
    measure = _function(TREE, "_measure_goal_change")
    measure_source = ast.unparse(measure)
    assert "time.monotonic_ns()" in measure_source
    assert "_wait_goal_change" in measure_source
    assert "goal_observed_monotonic_ns" in measure_source
    assert "latency_ns" in measure_source and "latency_ms" in measure_source
    assert "input_type" in measure_source and "goal_changed" in measure_source

    summary = _run_helper("_latency_summary", {"math": math, "statistics": statistics})
    measured = [
        {"latency_ms": value}
        for value in (1.0, 2.0, 3.0, 4.0, 9.0)
    ]
    assert summary(measured) == {
        "sample_count": 5,
        "median_ms": 3.0,
        "p95_ms": 9.0,
        "max_ms": 9.0,
        "units": "ms",
    }
    assert summary([])["units"] == "ms"
    run = ast.unparse(_function(TREE, "run"))
    for label in (
        "button_translation_x_plus",
        "button_pitch_plus",
        "button_yaw_plus",
        "key_translation_x_plus",
        "key_pitch_plus",
        "key_yaw_plus",
    ):
        assert label in run
    assert "latency_samples" in run and "latency_summary" in run


def test_explicit_probe_ack_solve_ik_accepted_state_and_disable_cleanup_are_gated():
    run = ast.unparse(_function(TREE, "run"))
    assert "tcpDragEnabledCheckBox.click()" in run
    assert "panel._tcpDragEnabled" in run
    assert "motion_logic.obsNode is not None" in run
    assert "ProbeSphere_Transform" in _string_constants(_function(TREE, "run"))
    assert "ProbeSphere" in _string_constants(_function(TREE, "run"))
    assert "solveIkButton.click()" in run
    assert "ROS2_JOINT_SI_ORDER" in run and "len(order) != 5" in run
    assert "matches_native_solution" in run
    assert "accepted_state_before" in run and "accepted_state_final" in run
    assert "tcpDragEnabledCheckBox.click()" in run
    assert "GetFirstNodeByName" in _attribute_calls(_function(TREE, "run"))
    assert "observer_removed" in run and "keyboard_checkbox_off" in run


def test_runner_is_no_case_simulation_only_and_calls_no_planner_preview_or_hardware_path():
    run = _function(TREE, "run")
    calls = _attribute_calls(run)
    assert "connect_dentobot_motion_control" in calls
    connection = next(
        call for call in _calls(run)
        if isinstance(call.func, ast.Attribute)
        and call.func.attr == "connect_dentobot_motion_control"
    )
    kwargs = {item.arg: ast.literal_eval(item.value) for item in connection.keywords}
    assert kwargs["start_stack_if_needed"] is False
    assert kwargs["start_joint_command_stream"] is False
    assert not ({"loadScene", "openFile", "plan", "plan_goal", "startPreview", "execute", "guardedManualJogButton"} & calls)
    constants = _string_constants(run)
    assert {"case_source", "case_loaded", "route_authority", "preview_started", "hardware_or_drilling_action"} <= constants
    assert "solveIkButton.click()" in ast.unparse(run)
    assert "_onShellSolveIk" not in ast.unparse(run)
