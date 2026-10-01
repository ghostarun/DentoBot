"""Focused host tests for the opted-in offline Base/Home probe."""

import ast
import hashlib
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
import re


RUNNER = Path(__file__).with_name("run_dentobot_step6_headed_review.py")
TREE = ast.parse(RUNNER.read_text(encoding="utf-8"))
JOINT_NAMES = ("J1", "J2", "J3", "J4", "J5")
LOCAL_HOME = {name: index / 100.0 for index, name in enumerate(JOINT_NAMES, 1)}


def _extract(name, extra_globals=None):
    node = next(
        entry for entry in TREE.body
        if isinstance(entry, ast.FunctionDef) and entry.name == name
    )
    namespace = {
        "Mapping": Mapping,
        "Sequence": Sequence,
        "Path": Path,
        "math": math,
        "re": re,
        "JOINT_NAMES": JOINT_NAMES,
        "__file__": str(RUNNER),
    }
    namespace.update(extra_globals or {})
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(RUNNER), "exec"), namespace)
    return namespace[name]


class _Result:
    def __init__(self, details, success=True):
        self.details = details
        self.success = success
        self.message = ""


class _HomeRecord:
    def __init__(self, vector, revision=1, validation="Unreviewed"):
        self.joint_names = JOINT_NAMES
        self.joint_positions_si = tuple(vector[name] for name in JOINT_NAMES)
        self.revision = revision
        self.runtime_validation_status = validation
        self.base_fingerprint = "base-fingerprint"
        self.robot_profile_fingerprint = "profile-fingerprint"

    def to_dict(self):
        return {
            "joint_names": self.joint_names,
            "joint_positions_si": self.joint_positions_si,
            "revision": self.revision,
            "runtime_validation_status": self.runtime_validation_status,
            "base_fingerprint": self.base_fingerprint,
            "robot_profile_fingerprint": self.robot_profile_fingerprint,
        }


def test_connected_mismatch_preserves_saved_home_and_stops_before_controls():
    configured = dict(LOCAL_HOME)
    saved_home = _HomeRecord(configured)

    class Logic:
        def taskHomeRecord(self, _parameter_node):
            return saved_home

        def robotBaseFingerprint(self, _parameter_node):
            return "base-fingerprint"

        def robotProfileFingerprint(self):
            return "profile-fingerprint"

    class Facade:
        def __init__(self):
            self.review_calls = 0

        def manualTaskHomeReview(self):
            self.review_calls += 1
            return _Result({
                "setupMode": "connected",
                "identityStatus": "current",
                "staged": False,
                "acceptanceStatus": "configuration_saved",
            })

        def capabilities(self):
            return type("Capabilities", (), {"connected": True})()

        def taskHomeRuntimeValidated(self, _parameter_node):
            return False

        def __getattr__(self, name):
            raise AssertionError(f"native/motion facade call before match: {name}")

    class MustNotReachWidget:
        def __getattr__(self, name):
            raise AssertionError(f"UI action before matching state: {name}")

    accepted = dict(configured)
    accepted["J1"] += 0.01
    state = {
        "accepted_si": accepted,
        "monitored_si": dict(accepted),
        "displayed_si": dict(accepted),
    }
    logic = Logic()
    facade = Facade()
    offline = {
        "status": "PASS",
        "saved_home_vector_si": configured,
        "saved_home_after": {"revision": saved_home.revision},
    }
    report = {"offline_home_setup": offline}

    validate = _extract("_validate_offline_home_after_connection", {
        "_write_report": lambda _report: None,
        "_record": lambda target_report, name, status, **details: target_report.setdefault(
            "items", {}
        ).update({name: {"status": status, **details}}),
        "_finite_vector": _extract("_finite_vector"),
        "_exactly_matches": _extract("_exactly_matches"),
        "_actual_joint_state": lambda _facade: state,
    })

    try:
        validate(
            MustNotReachWidget(), MustNotReachWidget(), logic, object(), facade,
            report, Path("."), "test-run",
        )
    except RuntimeError as exc:
        assert "differs from current accepted pose" in str(exc)
    else:
        raise AssertionError("mismatched connected pose was not rejected")

    assert saved_home.to_dict()["joint_positions_si"] == tuple(
        configured[name] for name in JOINT_NAMES
    )
    assert offline["status"] == "FAIL"
    assert offline["post_connect_validation"]["mismatch"] is True
    assert offline["post_connect_validation"]["mismatch_action"] == (
        "stopped_without_staging_or_motion"
    )
    assert facade.review_calls == 1
    assert report["items"]["offline_base_home_configuration"]["status"] == "FAIL"


def test_offline_probe_rejects_connected_facade_and_keeps_first_failure():
    class ConnectedFacade:
        def capabilities(self):
            return type("Capabilities", (), {"connected": True})()

    report = {"items": {}}

    def record(target_report, name, status, **details):
        target_report["items"][name] = {"status": status, **details}

    helper = _extract("_run_offline_base_home_configuration", {
        "_write_report": lambda _report: None,
        "_record": record,
    })
    try:
        helper(
            object(), object(), object(), object(), ConnectedFacade(),
            Path("unused.dentocase"), "unused-hash", Path("output.dentocase"),
            report, Path("."), "test-run",
        )
    except RuntimeError as exc:
        assert str(exc) == "Offline Home probe requires ROS/MoveIt to remain disconnected."
    else:
        raise AssertionError("connected facade was accepted for offline setup")

    evidence = report["offline_home_setup"]
    assert evidence["status"] == "FAIL"
    assert evidence["reason"] == "Offline Home probe requires ROS/MoveIt to remain disconnected."
    assert report["items"]["offline_base_home_configuration"]["status"] == "FAIL"
    assert "robot_joint_parameters_before" not in evidence


def test_offline_opt_in_reaches_connect_and_validation_precedes_recovery_and_planning():
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    offline_call = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_run_offline_base_home_configuration"
    )
    native_gate = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.If)
        and "native is None" in ast.unparse(node.test)
        and "offline_home_setup_opt_in" in ast.unparse(node.test)
    )
    gate_names = {
        node.id for node in ast.walk(native_gate.test)
        if isinstance(node, ast.Name)
    }
    no_other_opt_ins = {name: False for name in gate_names}
    no_other_opt_ins["native"] = object()
    gate = compile(ast.Expression(native_gate.test), str(RUNNER), "eval")
    assert eval(gate, no_other_opt_ins) is True
    no_other_opt_ins["offline_home_setup_opt_in"] = True
    assert eval(gate, no_other_opt_ins) is False
    no_other_opt_ins["native"] = None
    assert eval(gate, no_other_opt_ins) is True

    connect_call = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "click"
        and isinstance(node.func.value, ast.Attribute)
        and ast.unparse(node.func.value) == "panel.connectButton"
    )
    post_connect_call = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_validate_offline_home_after_connection"
    )
    after_scene_recovery = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_ensure_current_home_workspace_task"
        and any(
            keyword.arg == "phase"
            and ast.literal_eval(keyword.value) == "after_scene_ack"
            for keyword in node.keywords
        )
    )
    before_planning_recovery = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_ensure_current_home_workspace_task"
        and any(
            keyword.arg == "phase"
            and ast.literal_eval(keyword.value) == "before_planning"
            for keyword in node.keywords
        )
    )
    selected_planning_calls = [
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"run_complete_cycles", "run_full_chain_interruption_probe"}
    ]

    assert offline_call.lineno < native_gate.lineno < connect_call.lineno
    assert connect_call.lineno < post_connect_call.lineno < after_scene_recovery.lineno
    assert selected_planning_calls
    assert before_planning_recovery.lineno < min(
        call.lineno for call in selected_planning_calls
    )
    check_names = _extract_module_constant("CHECK_NAMES")
    assert "offline_base_home_configuration" in check_names
    run_report = next(
        node.value for node in ast.walk(run)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name) and node.target.id == "report"
        and isinstance(node.value, ast.Dict)
        and any(
            isinstance(key, ast.Constant) and key.value == "items"
            for key in node.value.keys
        )
    )
    item_defaults = next(
        value for key, value in zip(run_report.keys, run_report.values)
        if isinstance(key, ast.Constant) and key.value == "items"
    )
    defaults = eval(
        compile(ast.Expression(item_defaults), str(RUNNER), "eval"),
        {"CHECK_NAMES": check_names},
    )
    assert defaults["offline_base_home_configuration"]["status"] == "NOT_RUN"


def _extract_module_constant(name):
    assignment = next(
        node for node in TREE.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name
                for target in node.targets)
    )
    return ast.literal_eval(assignment.value)
