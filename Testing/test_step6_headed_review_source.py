"""Source gates for the explicitly bounded headed Step 6 runner."""

import ast
from collections.abc import Mapping, Sequence
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re

import pytest
from types import SimpleNamespace
import step6_manual_jog_scenarios as manual_jog_scenarios


RUNNER = Path(__file__).with_name("run_dentobot_step6_headed_review.py")
SOURCE = RUNNER.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
TCP_WORKBENCH = RUNNER.with_name("run_dentobot_tcp_workbench_headed.py")
TCP_WORKBENCH_TREE = ast.parse(TCP_WORKBENCH.read_text(encoding="utf-8"))
JOINT_NAMES = ("J1", "J2", "J3", "J4", "J5")


def test_manual_workbench_uses_visible_step6_substep():
    shell = (RUNNER.parent.parent / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot_shell.py").read_text(encoding="utf-8")
    panel = (RUNNER.parent.parent / "DENTOWorkflow/Resources/Python/DENTORobotSimulationPanel.py").read_text(encoding="utf-8")
    assert "3: (" in shell and "self._robotSimulationPanel.workbenchGroup," in shell
    assert 'self.step63ManualTabWidget.addTab(self.manualJogGroup, "Joints")' in panel
    assert "_configureRobotSimulationShellSubstep(5)" not in SOURCE
    assert SOURCE.count("_configureRobotSimulationShellSubstep(3)") >= 3


def test_step63_runner_selects_each_visible_control_surface():
    calls = []
    show = _extract_helper(
        "_show_step63_view",
        {"_process_events": lambda delay: calls.append(delay)},
    )
    tab = lambda: type("Tab", (), {"currentIndex": -1})()
    panel = type("Panel", (), {
        "step63TabWidget": tab(),
        "step63ManualTabWidget": tab(),
        "step63WorkspaceTabWidget": tab(),
        "step63PlanTabWidget": tab(),
    })()

    show(panel, 0, 1)
    assert (panel.step63TabWidget.currentIndex,
            panel.step63ManualTabWidget.currentIndex) == (0, 1)
    show(panel, 1, 2)
    assert (panel.step63TabWidget.currentIndex,
            panel.step63WorkspaceTabWidget.currentIndex) == (1, 2)
    show(panel, 2, 0)
    assert (panel.step63TabWidget.currentIndex,
            panel.step63PlanTabWidget.currentIndex) == (2, 0)
    assert calls == [0.1, 0.1, 0.1]


def _extract_helper(name, extra_globals=None):
    helper = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    namespace = {
        "math": math,
        "Mapping": Mapping,
        "Sequence": Sequence,
        "JOINT_NAMES": JOINT_NAMES,
        "Path": Path,
        "re": re,
    }
    namespace.update(extra_globals or {})
    module = ast.Module(body=[helper], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(RUNNER), "exec"), namespace)
    return namespace[name]


def _extract_tcp_workbench_helper(name, extra_globals=None):
    helper = next(
        node for node in TCP_WORKBENCH_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    namespace = {"os": os}
    namespace.update(extra_globals or {})
    module = ast.Module(body=[helper], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(TCP_WORKBENCH), "exec"), namespace)
    return namespace[name]


def _screenshot_capture_fixture(tmp_path, *, modal_mode=None):
    events = []

    class Pixmap:
        def __init__(self, name, *, null=False, save_ok=True, empty=False):
            self.name = name
            self.null = null
            self.save_ok = save_ok
            self.empty = empty

        def isNull(self):
            return self.null

        def save(self, path):
            events.append(f"{self.name}_save")
            if self.save_ok:
                Path(path).write_bytes(b"" if self.empty else b"screenshot")
            return self.save_ok

    modal = None
    if modal_mode is not None:
        class Modal:
            def grab(self):
                events.append("modal_grab")
                return Pixmap(
                    "modal",
                    null=modal_mode == "null",
                    save_ok=modal_mode != "save-failure",
                    empty=modal_mode == "empty",
                )

        modal = Modal()

    class Window:
        windowTitle = "original"

        def show(self):
            events.append("window_show")

        def grab(self):
            events.append("window_grab")
            return Pixmap("ui")

    class View:
        def forceRender(self):
            events.append("view_render")

        def renderWindow(self):
            return "render-window"

    view = View()

    class LayoutManager:
        def threeDWidget(self, _index):
            return self

        def threeDView(self):
            return view

    class VtkImageFilter:
        def SetInput(self, _window):
            pass

        def ReadFrontBufferOff(self):
            pass

        def Update(self):
            pass

        def GetOutputPort(self):
            return "image-output"

    class VtkPngWriter:
        def SetFileName(self, path):
            self.path = path

        def SetInputConnection(self, _output):
            pass

        def Write(self):
            events.append("viewport_save")
            Path(self.path).write_bytes(b"viewport")

    class SlicerUtil:
        def mainWindow(self):
            return window

        def forceRenderAllViews(self):
            events.append("force_render_all")

    class SlicerApp:
        def layoutManager(self):
            return LayoutManager()

    window = Window()
    qt = type("Qt", (), {
        "QApplication": type(
            "QApplication", (), {"activeModalWidget": staticmethod(lambda: modal)}
        )
    })
    slicer = type("Slicer", (), {"util": SlicerUtil(), "app": SlicerApp()})
    vtk = type("Vtk", (), {
        "vtkWindowToImageFilter": VtkImageFilter,
        "vtkPNGWriter": VtkPngWriter,
    })
    capture = _extract_helper("_capture_screenshots", {
        "Path": Path,
        "qt": qt,
        "slicer": slicer,
        "vtk": vtk,
        "_process_events": lambda _seconds: events.append("process_events"),
        "_utc_now": lambda: "2026-09-30T00:00:00Z",
    })
    return capture, events


def _module_constant(name):
    assignment = next(
        node for node in TREE.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    return ast.literal_eval(assignment.value)


def _calls(tree):
    return [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]


def _is_guarded_click(node, button_expression):
    """Match ``_modal_guarded_click(report, evidence_dir, run_id, <button>, stage)``."""
    return (
        isinstance(node, ast.Call)
        and ast.unparse(node.func) == "_modal_guarded_click"
        and len(node.args) >= 4
        and ast.unparse(node.args[3]) == button_expression
    )


def _button_clicks(tree, button_name):
    return [
        node for node in ast.walk(tree)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "click"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == button_name
        ) or (
            isinstance(node, ast.Call)
            and ast.unparse(node.func) == "_modal_guarded_click"
            and len(node.args) >= 4
            and isinstance(node.args[3], ast.Attribute)
            and node.args[3].attr == button_name
        )
    ]


def test_output_case_path_is_absolute_distinct_new_and_dentocase(tmp_path):
    validate = _extract_helper("_validate_output_case_path", {"Path": Path})
    source = tmp_path / "source.dentocase"
    source.write_bytes(b"source")
    output = tmp_path / "reviewed.dentocase"

    assert validate(str(output), source) == output
    with pytest.raises(ValueError, match="absolute path"):
        validate("relative/reviewed.dentocase", source)
    with pytest.raises(ValueError, match="end in .dentocase"):
        validate(str(tmp_path / "reviewed.zip"), source)
    with pytest.raises(ValueError, match="distinct"):
        validate(str(source), source)
    output.write_bytes(b"existing")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        validate(str(output), source)
    assert output.read_bytes() == b"existing"


def test_save_current_case_calls_production_owner_and_records_source_relation(tmp_path):
    validate = _extract_helper("_validate_output_case_path", {"Path": Path})
    sha_file = _extract_helper("_sha256_file", {"hashlib": hashlib})
    save = _extract_helper("_save_current_case", {
        "Path": Path,
        "os": os,
        "_validate_output_case_path": validate,
        "_sha256_file": sha_file,
    })
    source = tmp_path / "source.dentocase"
    output = tmp_path / "reviewed.dentocase"
    source.write_bytes(b"source archive")

    class Widget:
        destination = None

        def _createCaseBundle(self, destination):
            self.destination = destination
            temporary = Path(destination).with_suffix(".tmp")
            temporary.write_bytes(b"saved from workflow")
            os.replace(temporary, destination)
            return type("Inspection", (), {"path": Path(destination)})()

    widget = Widget()
    evidence = save(widget, output, source, sha_file(source))

    assert widget.destination == str(output)
    assert evidence["output_path"] == str(output)
    assert evidence["size_bytes"] == len(b"saved from workflow")
    assert evidence["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert evidence["source_relationship"] == {
        "source_path": str(source),
        "source_sha256": sha_file(source),
        "source_unchanged": True,
        "saved_from_current_workflow_session": True,
    }
    assert source.read_bytes() == b"source archive"


def test_save_current_case_never_calls_owner_for_existing_output(tmp_path):
    validate = _extract_helper("_validate_output_case_path", {"Path": Path})
    sha_file = _extract_helper("_sha256_file", {"hashlib": hashlib})
    save = _extract_helper("_save_current_case", {
        "Path": Path,
        "os": os,
        "_validate_output_case_path": validate,
        "_sha256_file": sha_file,
    })
    source = tmp_path / "source.dentocase"
    output = tmp_path / "reviewed.dentocase"
    source.write_bytes(b"source archive")
    output.write_bytes(b"keep me")

    class Widget:
        called = False

        def _createCaseBundle(self, destination):
            self.called = True
            raise AssertionError("existing output reached production save owner")

    widget = Widget()
    with pytest.raises(FileExistsError):
        save(widget, output, source, sha_file(source))
    assert widget.called is False
    assert output.read_bytes() == b"keep me"


def test_optional_save_is_last_selected_check_before_normal_pass_exit():
    run = next(node for node in TREE.body
               if isinstance(node, ast.FunctionDef) and node.name == "run")
    save_call = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_save_current_case"
    )
    success = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "outcome"
                for target in node.targets)
        and isinstance(node.value, ast.Constant)
        and node.value.value == "PASS"
    )
    gate = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "unpassed"
                for target in node.targets)
    )
    assert gate.lineno < save_call.lineno < success.lineno
    assert "_unpassed_selected_checks(report['items'])" in ast.unparse(gate.value)
    assert '"save_current_case"' in SOURCE
    assert '"DENTOBOT_HEADED_OUTPUT_CASE is unset."' in SOURCE

    unpassed = _extract_helper("_unpassed_selected_checks")
    assert unpassed({
        "pass": {"status": "PASS"},
        "native": {"status": "PREFLIGHT_PASS"},
        "skipped": {"status": "NOT_RUN"},
    }) == []
    assert unpassed({"failed": {"status": "FAIL"}}) == ["failed"]


def test_headed_motion_requires_exact_opt_in_and_native_preflight():
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    assert 'DENTOBOT_HEADED_ALLOW_JOG' in SOURCE
    assert "DENTOBOT_HEADED_NATIVE_SOURCE_SHA256" in SOURCE
    assert "DENTOBOT_HEADED_NATIVE_BINARY_SHA256" in SOURCE
    assert "DENTOBOT_HEADED_NATIVE_PACKAGE_PREFIX" in SOURCE
    native_gate = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.If) and "native is None" in ast.unparse(node.test)
    )
    assert ast.unparse(native_gate.test) == (
        "not allow_jog and (not draft_only) and (not invalid_draft_review) "
        "and (not joint_keyboard_opt_in) and (not workspace_diagnostic) and (not connect_only) "
        "and (not offline_home_setup_opt_in) and (not _exact_env_opt_in('DENTOBOT_HEADED_SESSION')) "
        "or native is None"
    )
    assert "get_package_prefix" in SOURCE
    assert 're.fullmatch(r"[0-9a-fA-F]{64}", value)' in SOURCE
    assert 'source_hash != expected_source or binary_hash != expected_binary' in SOURCE
    assert "shared_install_prefix" in SOURCE
    assert "EXPECTED_NATIVE_SOURCE_SHA256" not in SOURCE
    assert "EXPECTED_NATIVE_BINARY_SHA256" not in SOURCE
    assert re.search(r"['\"][0-9a-fA-F]{64}['\"]", SOURCE) is None


def test_session_checkpoint_selects_connect_with_all_scenario_opt_ins_off():
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    gates = [
        node for node in ast.walk(run)
        if isinstance(node, ast.If)
        and "offline_home_setup_opt_in" in ast.unparse(node.test)
        and "allow_jog" in ast.unparse(node.test)
    ]
    assert len(gates) == 2  # the PARTIAL condition and its mirrored explanation

    for gate in gates:
        expression = compile(ast.Expression(gate.test), str(RUNNER), "eval")

        def selected_session(enabled):
            def exact_opt_in(name):
                assert name == "DENTOBOT_HEADED_SESSION"
                return enabled

            return bool(eval(expression, {
                "allow_jog": False,
                "draft_only": False,
                "invalid_draft_review": False,
                "joint_keyboard_opt_in": False,
                "workspace_diagnostic": False,
                "connect_only": False,
                "offline_home_setup_opt_in": False,
                "native": object(),
                "_exact_env_opt_in": exact_opt_in,
            }))

        assert selected_session(False) is True  # default-off remains no-connect
        assert selected_session(True) is False  # explicit session reaches Connect + scene ack
        if "native is None" in ast.unparse(gate.test):
            context = {
                "allow_jog": False,
                "draft_only": False,
                "invalid_draft_review": False,
                "joint_keyboard_opt_in": False,
                "workspace_diagnostic": False,
                "connect_only": False,
                "offline_home_setup_opt_in": False,
                "native": None,
                "_exact_env_opt_in": lambda _name: True,
            }
            assert eval(expression, context) is True  # session never bypasses native provenance


def test_taskless_draft_opt_in_is_exact_and_excludes_motion_opt_ins(monkeypatch):
    draft_only_requested = _extract_helper("_draft_only_requested", {"os": os})
    monkeypatch.delenv("DENTOBOT_HEADED_DRAFT_ONLY", raising=False)
    monkeypatch.delenv("DENTOBOT_HEADED_ALLOW_JOG", raising=False)
    monkeypatch.delenv("DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT", raising=False)
    assert draft_only_requested() is False

    monkeypatch.setenv("DENTOBOT_HEADED_DRAFT_ONLY", "1")
    assert draft_only_requested() is True
    monkeypatch.setenv("DENTOBOT_HEADED_DRAFT_ONLY", "yes")
    with pytest.raises(RuntimeError, match="must be exactly '1', '0', or unset"):
        draft_only_requested()
    monkeypatch.setenv("DENTOBOT_HEADED_DRAFT_ONLY", "1")
    monkeypatch.setenv("DENTOBOT_HEADED_ALLOW_JOG", "1")
    with pytest.raises(RuntimeError, match="cannot be combined"):
        draft_only_requested()
    monkeypatch.setenv("DENTOBOT_HEADED_ALLOW_JOG", "")
    monkeypatch.setenv("DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT", "1")
    with pytest.raises(RuntimeError, match="cannot be combined"):
        draft_only_requested()


def test_invalid_draft_review_opt_in_accepts_only_exact_values(monkeypatch):
    requested = _extract_helper("_invalid_draft_review_requested", {"os": os})
    monkeypatch.delenv("DENTOBOT_HEADED_INVALID_DRAFT_REVIEW", raising=False)
    assert requested() is False
    monkeypatch.setenv("DENTOBOT_HEADED_INVALID_DRAFT_REVIEW", "0")
    assert requested() is False
    monkeypatch.setenv("DENTOBOT_HEADED_INVALID_DRAFT_REVIEW", "1")
    assert requested() is True
    for invalid in ("yes", "true", "01", " "):
        monkeypatch.setenv("DENTOBOT_HEADED_INVALID_DRAFT_REVIEW", invalid)
        with pytest.raises(RuntimeError, match="must be exactly '1', '0', or unset"):
            requested()


def test_record_reopen_opt_in_and_prerequisites_are_exact(monkeypatch):
    requested = _extract_helper("_historical_record_reopen_requested", {"os": os})
    validate = _extract_helper("_validate_record_reopen_prerequisites")
    monkeypatch.delenv("DENTOBOT_HEADED_RECORD_REOPEN", raising=False)
    assert requested() is False
    monkeypatch.setenv("DENTOBOT_HEADED_RECORD_REOPEN", "0")
    assert requested() is False
    monkeypatch.setenv("DENTOBOT_HEADED_RECORD_REOPEN", "1")
    assert requested() is True
    validate(True, True, False)
    with pytest.raises(RuntimeError, match="requires DENTOBOT_HEADED_ALLOW_JOG=1"):
        validate(True, False, False)
    with pytest.raises(RuntimeError, match="cannot be combined with taskless draft-only mode"):
        validate(True, True, True)
    for value in ("yes", "true", "01", " "):
        monkeypatch.setenv("DENTOBOT_HEADED_RECORD_REOPEN", value)
        with pytest.raises(RuntimeError, match="DENTOBOT_HEADED_RECORD_REOPEN must be exactly"):
            requested()


def test_manual_outcome_opt_ins_are_exact_and_require_the_existing_jog_gate(monkeypatch):
    requested = _extract_helper("_exact_env_opt_in", {"os": os})
    monkeypatch.delenv("DENTOBOT_HEADED_ALLOW_REJECTED_JOG", raising=False)
    assert requested("DENTOBOT_HEADED_ALLOW_REJECTED_JOG") is False
    monkeypatch.setenv("DENTOBOT_HEADED_ALLOW_REJECTED_JOG", "0")
    assert requested("DENTOBOT_HEADED_ALLOW_REJECTED_JOG") is False
    monkeypatch.setenv("DENTOBOT_HEADED_ALLOW_REJECTED_JOG", "1")
    assert requested("DENTOBOT_HEADED_ALLOW_REJECTED_JOG") is True
    for invalid in ("yes", "true", "01", " "):
        monkeypatch.setenv("DENTOBOT_HEADED_ALLOW_REJECTED_JOG", invalid)
        with pytest.raises(RuntimeError, match="must be exactly '1', '0', or unset"):
            requested("DENTOBOT_HEADED_ALLOW_REJECTED_JOG")

    run = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "run")
    run_source = ast.unparse(run)
    assert "DENTOBOT_HEADED_ALLOW_REJECTED_JOG=1 requires DENTOBOT_HEADED_ALLOW_JOG=1" in run_source
    assert "DENTOBOT_HEADED_ALLOW_UNKNOWN_RECONCILIATION=1 requires DENTOBOT_HEADED_ALLOW_JOG=1" in run_source
    assert "DENTOBOT_MANUAL_JOG_REJECTION_PLAN_JSON" in run_source


def test_workspace_diagnostic_admission_requires_home_opt_in_and_excludes_actions(monkeypatch):
    exact_opt_in = _extract_helper("_exact_env_opt_in", {"os": os})
    validate = _extract_helper(
        "_validate_workspace_diagnostic_opt_in",
        {"os": os, "_exact_env_opt_in": exact_opt_in},
    )
    incompatible = (
        "DENTOBOT_HEADED_DRAFT_ONLY",
        "DENTOBOT_HEADED_INVALID_DRAFT_REVIEW",
        "DENTOBOT_HEADED_RECORD_REOPEN",
        "DENTOBOT_HEADED_JOINT_KEYBOARD",
        "DENTOBOT_HEADED_TCP_CASE",
        "DENTOBOT_HEADED_BASE_HOME_UNCERTAINTY",
        "DENTOBOT_HEADED_COMPLETE_CYCLES",
        "DENTOBOT_HEADED_FULL_CHAIN",
        "DENTOBOT_HEADED_ALLOW_REJECTED_JOG",
        "DENTOBOT_HEADED_ALLOW_UNKNOWN_RECONCILIATION",
        "DENTOBOT_HEADED_ALLOW_JOG",
        "DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT",
        "DENTOBOT_HEADED_STOP_AFTER_WORKSPACE",
        "DENTOBOT_HEADED_OUTPUT_CASE",
    )
    for name in incompatible:
        monkeypatch.delenv(name, raising=False)
    assert validate() is False

    monkeypatch.setenv("DENTOBOT_HEADED_STOP_AFTER_WORKSPACE", "yes")
    with pytest.raises(RuntimeError, match="DENTOBOT_HEADED_STOP_AFTER_WORKSPACE must be exactly"):
        validate()
    monkeypatch.setenv("DENTOBOT_HEADED_STOP_AFTER_WORKSPACE", "1")
    with pytest.raises(RuntimeError, match="requires DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT=1"):
        validate()

    monkeypatch.setenv("DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT", "1")
    assert validate() is True
    assert os.environ.get("DENTOBOT_HEADED_ALLOW_JOG") is None

    monkeypatch.setenv("DENTOBOT_HEADED_ALLOW_JOG", "1")
    with pytest.raises(RuntimeError, match="requires DENTOBOT_HEADED_ALLOW_JOG"):
        validate()
    monkeypatch.setenv("DENTOBOT_HEADED_ALLOW_JOG", "0")
    for name in incompatible:
        if name in {
            "DENTOBOT_HEADED_ALLOW_JOG",
            "DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT",
            "DENTOBOT_HEADED_STOP_AFTER_WORKSPACE",
            "DENTOBOT_HEADED_OUTPUT_CASE",
        }:
            continue
        monkeypatch.setenv(name, "1")
        with pytest.raises(RuntimeError, match="cannot be combined"):
            validate()
        monkeypatch.setenv(name, "0")

    monkeypatch.setenv("DENTOBOT_HEADED_OUTPUT_CASE", "")
    with pytest.raises(RuntimeError, match="cannot be combined with DENTOBOT_HEADED_OUTPUT_CASE"):
        validate()


def test_shared_rejection_plan_binds_case_fixture_and_exact_start_vectors():
    headless_source = RUNNER.with_name("run_dentobot_manual_jog_headless.py").read_text(encoding="utf-8")
    assert "TESTING = ROOT / \"Testing\"" in headless_source
    assert "fixture_identity as _fixture_identity" in headless_source
    assert "rejection_plan as _rejection_plan" in headless_source
    assert "fixture_identity_value=saved_identity['fixture_identity']" in ast.unparse(
        ast.parse(headless_source)
    )

    def finite_vector(values):
        if not isinstance(values, Mapping) or set(values) != set(JOINT_NAMES):
            raise ValueError("expected exact J1-J5")
        result = {name: float(values[name]) for name in JOINT_NAMES}
        if not all(math.isfinite(value) for value in result.values()):
            raise ValueError("expected finite J1-J5")
        return result

    start = dict(zip(JOINT_NAMES, (0.0, 0.01, 0.0, 0.02, 0.0)))
    target = dict(start, J1=0.001)
    plan_json = json.dumps({
        "schema_version": "1.0",
        "case_sha256": "case-hash",
        "fixture_identity": "fixture-hash",
        "starting_positions_si": start,
        "requested_positions_si": target,
        "review_reference": "reviewed collision vector",
    })
    parsed, reason = manual_jog_scenarios.rejection_plan(
        plan_json,
        case_sha256="case-hash",
        fixture_identity_value="fixture-hash",
        finite_vector=finite_vector,
    )
    assert reason == ""
    assert parsed == {
        "starting_positions_si": start,
        "requested_positions_si": target,
        "case_sha256": "case-hash",
        "fixture_identity": "fixture-hash",
        "review_reference": "reviewed collision vector",
    }
    with pytest.raises(ValueError, match="different saved case"):
        manual_jog_scenarios.rejection_plan(
            plan_json,
            case_sha256="other-case",
            fixture_identity_value="fixture-hash",
            finite_vector=finite_vector,
        )
    with pytest.raises(ValueError, match="different fixture identity"):
        manual_jog_scenarios.rejection_plan(
            plan_json,
            case_sha256="case-hash",
            fixture_identity_value="other-fixture",
            finite_vector=finite_vector,
        )

    captured = {}

    def fingerprint_fn(value):
        captured["value"] = value
        return "fixture-hash"

    fixture = manual_jog_scenarios.fixture_identity(
        branch_id="branch",
        task_core={"task": "core"},
        home_revision=7,
        home_joint_positions_si=start,
        scene_source_object_ids=["case-object"],
        scene_base_fingerprint="base",
        fingerprint_fn=fingerprint_fn,
    )
    assert fixture == "fixture-hash"
    assert captured["value"] == {
        "branch_id": "branch",
        "task_core": {"task": "core"},
        "home_revision": 7,
        "home_joint_positions_si": start,
        "scene_source_object_ids": ["case-object"],
        "scene_base_fingerprint": "base",
    }


def test_historical_probe_loader_imports_callable_without_running_probe():
    load_probe = _extract_helper(
        "_load_historical_record_probe",
        {"importlib": importlib, "TESTING": RUNNER.parent},
    )
    helper_path = RUNNER.with_name("step6_historical_record_probe.py")
    helper_tree = ast.parse(helper_path.read_text(encoding="utf-8"))
    assert all(
        isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef))
        or (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
        for node in helper_tree.body
    )
    probe = load_probe()
    assert callable(probe)
    assert probe.__name__ == "run_step6_historical_record_probe"


def _valid_historical_probe_evidence(evidence_dir):
    paths = {
        "record_json": evidence_dir / "step6-manual-record-probe.json",
        "record_report": evidence_dir / "step6-manual-record-probe.report.txt",
    }
    paths["record_json"].write_text("{}\n", encoding="utf-8")
    paths["record_report"].write_text("event report\n", encoding="utf-8")
    hashes = {
        "json": hashlib.sha256(paths["record_json"].read_bytes()).hexdigest(),
        "report": hashlib.sha256(paths["record_report"].read_bytes()).hexdigest(),
    }
    joints = {name: float(index) for index, name in enumerate(JOINT_NAMES)}
    stages = ("before_export", "after_export", "after_import", "after_event_step")
    captures = []
    for stage in stages:
        ui_path = evidence_dir / f"{stage}-ui.png"
        viewport_path = evidence_dir / f"{stage}-viewport.png"
        ui_path.write_bytes(b"ui image")
        viewport_path.write_bytes(b"viewport image")
        captures.append(
            {
                "stage": stage,
                "result": {"ui": ui_path.name, "viewport": viewport_path.name},
            }
        )
    return {
        "status": "PASS",
        **{key: str(path) for key, path in paths.items()},
        "artifact_sha256": hashes,
        "record": {
            "event_order": [
                {"index": 0, "kind": "guarded_jog", "monotonic_ns": 123}
            ],
            "event_count": 1,
        },
        "replay": {"authority": "historical_display_only"},
        "accepted_j1_j5": {"before": joints, "after": dict(joints), "unchanged": True},
        "route_preview_authority": {
            "before": {"motion_plan_present": False, "preview_active": False},
            "after": {"motion_plan_present": False, "preview_active": False},
            "unchanged": True,
            "historical_record_authority": "display_only",
        },
        "captures": captures,
    }


def test_historical_probe_evidence_validator_checks_hash_events_authority_and_state(tmp_path):
    exact = _extract_helper(
        "_exactly_matches",
        {"math": math, "Mapping": Mapping, "Sequence": Sequence, "JOINT_NAMES": JOINT_NAMES},
    )
    sha_file = _extract_helper("_sha256_file", {"hashlib": hashlib})
    validate = _extract_helper(
        "_historical_record_probe_evidence_error",
        {
            "Mapping": Mapping,
            "Path": Path,
            "re": re,
            "_exactly_matches": exact,
            "_sha256_file": sha_file,
        },
    )
    tmp_path.chmod(0o700)
    evidence = _valid_historical_probe_evidence(tmp_path)
    assert validate(evidence, tmp_path) == ""

    wrong_hash = {**evidence, "artifact_sha256": {**evidence["artifact_sha256"], "json": "0" * 64}}
    assert validate(wrong_hash, tmp_path) == "record_json SHA-256 does not match the exported artifact"

    no_events = {**evidence, "record": {"event_order": [], "event_count": 0}}
    assert validate(no_events, tmp_path) == "event-bearing record order is unavailable or incomplete"

    changed_joints = {
        **evidence,
        "accepted_j1_j5": {
            **evidence["accepted_j1_j5"],
            "after": {**evidence["accepted_j1_j5"]["after"], "J1": 8.0},
        },
    }
    assert validate(changed_joints, tmp_path) == (
        "accepted J1–J5 changed or its unchanged evidence is unavailable"
    )

    changed_authority = {
        **evidence,
        "route_preview_authority": {
            **evidence["route_preview_authority"],
            "after": {"motion_plan_present": True, "preview_active": False},
        },
    }
    assert validate(changed_authority, tmp_path) == (
        "route/preview authority changed or its unchanged evidence is unavailable"
    )


def test_invalid_draft_candidate_uses_displayed_limits_and_spinbox_bounds():
    select = _extract_helper("_select_invalid_draft_candidate")

    class Spinbox:
        def __init__(self, minimum, maximum):
            self.minimum = minimum
            self.maximum = maximum
            self.decimals = 2

    class Label:
        def __init__(self, text):
            self.text = text

    reviewed = ((-180, 180), (-2, 4), (-90, 90), (-2, 2), (-170, 170))
    mechanical = ((-180, 180), (-5, 5), (-90, 90), (-2, 2), (-170, 170))
    panel = type("Panel", (), {})()
    panel.manualJogJointControls = {}
    for index, joint in enumerate(JOINT_NAMES):
        unit = "mm" if index in (1, 3) else "deg"
        low, high = reviewed[index]
        mech_low, mech_high = mechanical[index]
        panel.manualJogJointControls[joint] = (
            object(),
            Spinbox(mech_low, mech_high),
            Label(
                f"{joint} ({unit}); slider allowed: {low:.2f} to {high:.2f} {unit}; "
                f"numeric mechanical: {mech_low:.2f} to {mech_high:.2f} {unit}; "
                f"reviewed: {low:.2f} to {high:.2f} {unit}"
            ),
        )

    candidate, reason = select(panel, (10.0, 1.0, 20.0, 1.5, 30.0))
    assert reason == ""
    assert candidate["joint"] == "J2"
    assert candidate["bound"] == "maximum"
    assert candidate["reviewed_limit_display"] == 4.0
    assert candidate["candidate_display"] == 4.01
    assert candidate["joint_label"] == "J2"
    assert candidate["display_values"] == [10.0, 4.01, 20.0, 1.5, 30.0]
    assert candidate["candidate_display"] <= candidate["mechanical_maximum"]
    assert candidate["reviewed_limit_label"].endswith("reviewed: -2.00 to 4.00 mm")

    for joint in JOINT_NAMES:
        _slider, spinbox, label = panel.manualJogJointControls[joint]
        low, high = mechanical[JOINT_NAMES.index(joint)]
        unit = "mm" if JOINT_NAMES.index(joint) in (1, 3) else "deg"
        spinbox.minimum, spinbox.maximum = low, high
        label.text = (
            f"{joint} ({unit}); slider allowed: {low:.2f} to {high:.2f} {unit}; "
            f"numeric mechanical: {low:.2f} to {high:.2f} {unit}; "
            f"reviewed: {low:.2f} to {high:.2f} {unit}"
        )
    candidate, reason = select(panel, (0.0,) * 5)
    assert candidate is None
    assert "No one-display-step reviewed-limit overstep" in reason
    assert "J1: reviewed -180 to 180 deg; mechanical -180 to 180 deg" in reason


def test_invalid_draft_evidence_matches_display_units_and_facade_joint_labels():
    read_display = _extract_helper("_visible_manual_draft_display_values")
    match_violation = _extract_helper("_matching_reviewed_limit_violation")

    class Spinbox:
        def __init__(self, value):
            self.value = value

    panel = type("Panel", (), {})()
    display_values = (90.01, 1.23, -30.11, 2.22, 150.02)
    panel.manualJogJointControls = {
        joint: (object(), Spinbox(value), object())
        for joint, value in zip(JOINT_NAMES, display_values, strict=True)
    }
    observed_display = read_display(panel)
    requested_si = (
        math.radians(display_values[0]), display_values[1] / 1000.0,
        math.radians(display_values[2]), display_values[3] / 1000.0,
        math.radians(display_values[4]),
    )
    assert observed_display == display_values
    assert observed_display != requested_si

    candidate = {
        "joint": JOINT_NAMES[1],
        "joint_label": "J2",
        "bound": "maximum",
    }
    evidence = {
        "limitViolations": [
            {
                "jointLabel": "J2",
                "jointName": JOINT_NAMES[1],
                "limitSource": "reviewed_task",
                "bound": "maximum",
                "boundDisplayValue": 4.0,
                "candidateDisplayValue": 4.01,
            }
        ]
    }
    assert match_violation(evidence, candidate) == evidence["limitViolations"][0]
    evidence["limitViolations"][0]["jointLabel"] = "wrong-label"
    assert match_violation(evidence, candidate) is None


def test_invalid_draft_review_is_read_only_and_restores_before_guarded_jog():
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    run_source = ast.unparse(run)
    assert "_invalid_draft_review_requested()" in run_source
    assert "_select_invalid_draft_candidate(panel, _display_values(after_draft['accepted_si']))" in run_source
    assert "control.setValue(candidate['candidate_display'])" in run_source
    assert "_visible_manual_draft_display_values(panel)" in run_source
    assert "_matching_reviewed_limit_violation(invalid_evidence, candidate)" in run_source
    assert "panel.checkManualDraftStateButton.click()" in run_source
    assert "panel.guardedManualJogButton.enabled" in run_source
    assert "invalid_evidence.get('limitAssessmentAuthoritative') is not True" in run_source
    assert "invalid_evidence.get('routeAuthority') != 'none'" in run_source
    assert "report['planner_calls'] != 0" in run_source
    assert "report['preview_started'] is not False" in run_source
    assert "restored_before_any_guarded_jog" in run_source
    assert "_setManualJogDraftValues(_display_values(invalid_before['accepted_si'])" in run_source
    assert "'invalid_out_of_reviewed_range_draft', 'NOT_RUN'" in run_source
    assert run_source.index("restored_before_any_guarded_jog") < run_source.index(
        "_guard_click(widget, panel, target)"
    )

    candidate_helper = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_select_invalid_draft_candidate"
    )
    assert not _button_clicks(candidate_helper, "guardedManualJogButton")
    assert "120" not in ast.unparse(candidate_helper)


def test_git_provenance_is_host_supplied_and_mount_root_is_checked():
    checkout = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_checkout_evidence"
    )
    source = ast.unparse(checkout)
    for name in (
        "DENTOBOT_HEADED_GIT_HEAD",
        "DENTOBOT_HEADED_GIT_BRANCH",
        "DENTOBOT_HEADED_GIT_STATUS_SHA256",
        "DENTOBOT_HEADED_HOST_CHECKOUT_ROOT",
    ):
        assert name in source
    assert '"/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-renovation"' in SOURCE
    assert '"/workspace/ros2_ws/src/DentoBot-step6-renovation"' in SOURCE
    assert '"/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-5.10-integration"' in SOURCE
    assert '"/workspace/ros2_ws/src/DentoBot-step6-5.10-integration"' in SOURCE
    assert '"integration/step6-5.10-reviewed-20260927"' in SOURCE
    assert "profile['host_root']" in source
    assert "profile['container_root']" in source
    assert "profile['branch']" in source
    assert "host_git_preflight" in source
    assert "host_wrapper_environment" in source
    assert "[0-9a-fA-F]{40}" in source and "fullmatch" in source
    assert "[0-9a-fA-F]{64}" in source and "fullmatch" in source
    assert "_git_value" not in SOURCE
    assert "subprocess" not in SOURCE
    profile = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_checkout_profile"
    )
    assert "DENTOBOT_HEADED_PROVENANCE_MODE" in ast.unparse(profile)


def test_checkout_profile_accepts_only_renovation_or_explicit_integration(monkeypatch):
    profile = _extract_helper(
        "_checkout_profile",
        {"os": os, "CHECKOUT_PROFILES": _module_constant("CHECKOUT_PROFILES")},
    )
    monkeypatch.delenv("DENTOBOT_HEADED_PROVENANCE_MODE", raising=False)
    assert profile() == {
        "name": "renovation",
        "branch": "feature/step6-workflow-renovation-20260925",
        "host_root": "/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-renovation",
        "container_root": "/workspace/ros2_ws/src/DentoBot-step6-renovation",
    }

    monkeypatch.setenv("DENTOBOT_HEADED_PROVENANCE_MODE", "integration")
    assert profile() == {
        "name": "integration",
        "branch": "integration/step6-5.10-reviewed-20260927",
        "host_root": "/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-5.10-integration",
        "container_root": "/workspace/ros2_ws/src/DentoBot-step6-5.10-integration",
    }

    monkeypatch.setenv("DENTOBOT_HEADED_PROVENANCE_MODE", "custom")
    with pytest.raises(RuntimeError, match="must be exactly 'renovation', 'integration' or 'per-sha'"):
        profile()


def test_per_sha_profile_binds_the_exact_published_commit_to_its_detached_worktree(monkeypatch):
    profile = _extract_helper(
        "_checkout_profile",
        {"os": os, "re": re, "CHECKOUT_PROFILES": _module_constant("CHECKOUT_PROFILES")},
    )
    sha = "6dce03e04ecf901a05dd3c821def9dd2865d2462"
    monkeypatch.setenv("DENTOBOT_HEADED_PROVENANCE_MODE", "per-sha")
    monkeypatch.setenv("DENTOBOT_HEADED_GIT_HEAD", sha)
    assert profile() == {
        "name": "per-sha", "branch": "DETACHED",
        "host_root": "/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-6dce03e04ecf",
        "host_root_aliases": (
            "/home/light-tarun/dentobot/ros2_ws/src/DentoBot-visible-6dce03e04ecf",
        ),
        "container_root": "/workspace/ros2_ws/src/DentoBot-visible-6dce03e04ecf",
    }
    for bad in ("", "6dce03e", sha.upper(), sha[:39] + "g", sha + "0"):
        monkeypatch.setenv("DENTOBOT_HEADED_GIT_HEAD", bad)
        with pytest.raises(RuntimeError, match="40 lowercase hexadecimal"):
            profile()
    monkeypatch.delenv("DENTOBOT_HEADED_GIT_HEAD")
    with pytest.raises(RuntimeError, match="40 lowercase hexadecimal"):
        profile()


def test_per_sha_checkout_evidence_accepts_exact_host_roots_and_rejects_foreign(monkeypatch):
    sha = "6dce03e04ecf901a05dd3c821def9dd2865d2462"
    monkeypatch.setenv("DENTOBOT_HEADED_PROVENANCE_MODE", "per-sha")
    monkeypatch.setenv("DENTOBOT_HEADED_GIT_HEAD", sha)
    monkeypatch.setenv("DENTOBOT_HEADED_GIT_BRANCH", "DETACHED")
    monkeypatch.setenv("DENTOBOT_HEADED_GIT_STATUS_SHA256", "a" * 64)

    profile = _extract_helper(
        "_checkout_profile",
        {"os": os, "re": re, "CHECKOUT_PROFILES": _module_constant("CHECKOUT_PROFILES")},
    )
    selected = profile()
    checkout_evidence = _extract_helper("_checkout_evidence", {
        "_checkout_profile": profile,
        "os": os,
        "re": re,
        "Path": Path,
        "ROOT": Path(selected["container_root"]),
        "SOURCE_FILES": (),
        "_sha256_file": lambda _path: "f" * 64,
        "__file__": str(RUNNER),
    })

    accepted_roots = (selected["host_root"], *selected["host_root_aliases"])
    for root in accepted_roots:
        monkeypatch.setenv("DENTOBOT_HEADED_HOST_CHECKOUT_ROOT", root)
        evidence = checkout_evidence()
        assert evidence["container_checkout_root"] == selected["container_root"]
        assert evidence["host_git_preflight"]["checkout_root"] == root
        assert evidence["host_git_preflight"]["head_commit"] == sha

    monkeypatch.setenv(
        "DENTOBOT_HEADED_HOST_CHECKOUT_ROOT",
        "/home/tarun/dentobot/ros2_ws/src/DentoBot-visible-unrelated",
    )
    with pytest.raises(RuntimeError, match="unexpected checkout root"):
        checkout_evidence()


def test_runner_routes_guarded_scenarios_through_one_production_click_owner():
    calls = _calls(TREE)
    assert len(_button_clicks(TREE, "guardedManualJogButton")) == 1
    assert len(_button_clicks(TREE, "lockRobotBaseMountButton")) == 0
    assert SOURCE.count("_guard_click(widget, panel, target)") == 3
    assert calls.count("acceptManualBaseReview") == 0
    assert calls.count("acceptManualTaskHomeReview") == 0
    assert calls.count("planApproach") == 0
    assert calls.count("planDrilling") == 0
    assert calls.count("previewApproach") == 0
    assert calls.count("previewDrilling") == 0
    assert calls.count("reconcileManualRobotJog") == 0
    assert '"base_acceptance_attempted": False' in SOURCE


def test_case_bound_rejection_is_preflighted_and_uses_the_shared_guard_path():
    names = _module_constant("CHECK_NAMES")
    assert "case_bound_rejected_guard" in names
    run = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "run")
    run_source = ast.unparse(run)
    assert run_source.index("_prepare_case_bound_rejection(") < run_source.index("jog_ui = _guard_click(")
    assert run_source.index("_run_case_bound_rejection(") < run_source.index("_run_unknown_reconciliation(")

    fixture = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_manual_jog_fixture_identity"
    )
    fixture_source = ast.unparse(fixture)
    assert "entry_ras_mm" in fixture_source and "target_ras_mm" in fixture_source
    assert "scene_source_object_ids=scene['source_object_ids']" in fixture_source
    assert "scene_base_fingerprint=str(audit.base_fingerprint)" in fixture_source

    prepare = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_prepare_case_bound_rejection"
    )
    prepare_source = ast.unparse(prepare)
    assert "_rejection_plan(" in prepare_source
    assert "case_sha256=case_sha256" in prepare_source
    assert "fixture_identity_value=fixture_identity" in prepare_source
    assert "finite_vector=_finite_vector" in prepare_source
    assert "_within_both_limits(logic, parameter_node, target)" in prepare_source
    assert "_exactly_matches(plan['starting_positions_si'], accepted_target)" in prepare_source
    assert "_exactly_matches(visible_target, target)" in prepare_source

    rejected = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run_case_bound_rejection"
    )
    rejected_source = ast.unparse(rejected)
    for required in (
        "ui = _guard_click(widget, panel, target)",
        "native.get('responseObserved') is True",
        "native.get('responseCorrelated') is True",
        "native.get('accepted') is False",
        "native.get('worldObjectEvidencePresent') is True",
        "native.get('worldObjectIds')",
        "ui.get('draft_positions_si'), target",
        "after[key], before[key]",
        "'case-bound-rejected-jog'",
        "'case_bound_rejected_guard'",
    ):
        assert required in rejected_source
    assert not any(
        name in rejected_source
        for name in ("planApproach", "planDrilling", "previewApproach", "previewDrilling")
    )


def test_unknown_ack_wrapper_restores_bridge_and_uses_production_reconcile_owner():
    names = _module_constant("CHECK_NAMES")
    assert "unknown_reconcile_state" in names
    unknown = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run_unknown_reconciliation"
    )
    wrapper = next(
        node for node in ast.walk(unknown)
        if isinstance(node, ast.FunctionDef) and node.name == "stale_acknowledgement"
    )
    wrapper_calls = [
        node for node in ast.walk(wrapper)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "original_apply"
    ]
    assert len(wrapper_calls) == 1
    replacement = next(
        node for node in ast.walk(wrapper)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "dataclasses.replace"
    )
    assert {keyword.arg for keyword in replacement.keywords} == {"request_id", "session_id"}
    source = ast.unparse(unknown)
    assert "setattr(bridge_owner, 'apply_manual_joint_positions_si', stale_acknowledgement)" in source
    assert "setattr(bridge_owner, 'apply_manual_joint_positions_si', original_apply)" in source
    assert "panel.guardedManualJogButton.enabled is False" in source
    assert "'repeat_jog_blocked': not panel.guardedManualJogButton.enabled" in source
    assert "panel.reconcileManualJogButton.click()" in source
    assert "facade.reconcileManualRobotJog" not in source
    assert "query_evidence.get('operation') == 'state_query'" in source
    assert "reconciliation.get('identityBefore') == identity_before" in source
    assert "reconciliation.get('identityAfter') == identity_before" in source
    assert "current_identity == identity_before" in source
    assert "state_after['accepted_si'], native_accepted" in source
    assert "state_after['monitored_si'], monitored" in source
    assert "state_after['displayed_si'], native_accepted" in source
    assert "'unknown-reconciliation-required'" in source
    assert "'unknown-state-reconciled'" in source
    assert not any(
        name in source
        for name in ("planApproach", "planDrilling", "previewApproach", "previewDrilling")
    )


def test_taskless_draft_only_stops_with_evidence_before_jog_or_acceptance():
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    run_source = ast.unparse(run)
    assert "_draft_only_requested()" in run_source
    assert '"review_mode": None' in SOURCE
    assert '"taskless_draft_only": False' in SOURCE
    assert "confirmed_task_present = logic.confirmedTaskRecord(parameter_node) is not None" in run_source
    assert "Taskless draft-only mode requires a case with no confirmed task" in run_source

    stop = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Raise)
        and "Taskless draft-only review completed after Check Draft State" in ast.unparse(node)
    )
    draft_record = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_record"
        and any(
            keyword.arg == "evidence"
            and isinstance(keyword.value, ast.Name)
            and keyword.value.id == "draft_evidence"
            for keyword in node.keywords
        )
    )
    guarded_call = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_guard_click"
    )
    assert draft_record.lineno < stop.lineno < guarded_call.lineno
    assert "draft_evidence" in ast.unparse(draft_record)
    assert "draft-state-checked" in ast.unparse(draft_record)
    assert "complete_not_run(CHECK_NAMES, message)" in SOURCE


def test_historical_probe_is_opt_in_after_correlated_jog_and_before_base_stage():
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    calls = [
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
    ]
    jog = next(node for node in calls if ast.unparse(node.func) == "_guard_click")
    probe = next(node for node in calls if ast.unparse(node.func) == "probe")
    base_stage = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "active_check"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and node.value.value == "base_stage_and_cancel"
    )
    assert jog.lineno < probe.lineno < base_stage.lineno
    assert "_historical_record_reopen_requested()" in ast.unparse(run)
    assert "_validate_record_reopen_prerequisites(record_reopen, allow_jog_requested, draft_only)" in ast.unparse(run)
    assert "lambda stage: _capture(" in ast.unparse(run)
    assert "_historical_record_probe_evidence_error(probe_evidence, evidence_dir)" in ast.unparse(run)
    assert "DENTOBOT_HEADED_RECORD_REOPEN is unset or '0'." in ast.unparse(run)

    record_gate = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.If) and ast.unparse(node.test) == "record_reopen"
        and any(
            isinstance(child, ast.Call) and ast.unparse(child.func) == "probe"
            for child in ast.walk(node)
        )
    )
    assert not any(
        isinstance(node, ast.Call) and ast.unparse(node.func) == "probe"
        for node in ast.walk(ast.Module(body=record_gate.orelse, type_ignores=[]))
    )
    assert "planApproach" not in ast.unparse(record_gate)
    assert "previewApproach" not in ast.unparse(record_gate)
    assert "saveCase" not in ast.unparse(record_gate)
    assert '"route_authority": "none"' in SOURCE
    assert '"preview_started": False' in SOURCE


def test_base_home_acceptance_is_exactly_opt_in_and_keeps_default_checklist():
    checks = next(
        node.value for node in TREE.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "CHECK_NAMES"
                for target in node.targets)
    )
    previous_checks = (
        "checkout_and_case_provenance",
        "case_opened_and_step6_ui",
        "saved_case_ros_readiness_not_restored",
        "simulation_robot_models_loaded",
        "planning_context_imported",
        "base_controls_and_accepted_status",
        "offline_base_home_configuration",
        "draft_state_control_visible",
        "native_version_preflight",
        "base_profile_rebind_prerequisite",
        "simulation_ros_connect_and_scene_readback",
        "profile_migration_recovery_after_scene_ack",
        "draft_state_read_only",
        "invalid_out_of_reviewed_range_draft",
        "single_guarded_j1_jog",
        "historical_record_export_reopen",
        "base_stage_and_cancel",
        "base_acceptance_trial",
    )
    assert tuple(ast.literal_eval(checks))[:len(previous_checks)] == previous_checks
    assert "task_home_review_acceptance_trial" in ast.literal_eval(checks)

    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    opt_in = next(
        node.value for node in ast.walk(run)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "allow_base_home_accept"
                for target in node.targets)
    )
    assert isinstance(opt_in, ast.Compare)
    assert ast.unparse(opt_in.left) == (
        "os.environ.get('DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT', '')"
    )
    assert ast.literal_eval(opt_in.comparators[0]) == "1"

    gate = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.If)
        and ast.unparse(node.test) == "not allow_base_home_accept"
        and "'task_home_review_acceptance_trial'" in ast.unparse(node)
    )
    default_path = ast.unparse(gate.body)
    acceptance_path = ast.unparse(gate.orelse)
    assert "'base_acceptance_trial', 'NOT_RUN'" in default_path
    assert "'task_home_review_acceptance_trial', 'NOT_RUN'" in default_path
    assert "base_acceptance_owner, 'base-acceptance-accept'" not in default_path
    assert "task_home_accept_owner.click()" not in default_path
    assert "base_acceptance_owner, 'base-acceptance-accept'" in acceptance_path
    assert "task_home_accept_owner.click()" in acceptance_path


def test_stale_restored_base_rebind_precedes_connect_without_scene_ack():
    run = next(node for node in TREE.body
               if isinstance(node, ast.FunctionDef) and node.name == "run")
    rebind = next(node for node in TREE.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "_run_base_profile_rebind_prerequisite")
    checks = _module_constant("CHECK_NAMES")
    assert checks.index("base_profile_rebind_prerequisite") < checks.index(
        "simulation_ros_connect_and_scene_readback"
    )
    assert checks.index("simulation_ros_connect_and_scene_readback") < checks.index(
        "base_stage_and_cancel"
    ) < checks.index("base_acceptance_trial") < checks.index(
        "task_home_review_acceptance_trial"
    )

    rebind_source = ast.unparse(rebind)
    opt_in_gate = next(node for node in ast.walk(rebind)
                       if isinstance(node, ast.If)
                       and "allow_base_home_accept" in ast.unparse(node.test))
    assert ast.unparse(opt_in_gate.test) == (
        "not allow_base_home_accept or status != 'Stale' or locked"
    )
    assert "panel.beginManualBaseReviewButton.click()" in rebind_source
    assert "accept_owner = widget.ui.lockRobotBaseMountButton" in rebind_source
    assert "accept_owner.click()" in rebind_source
    review_click = next(node for node in ast.walk(rebind)
                        if isinstance(node, ast.Call)
                        and ast.unparse(node.func) == "panel.beginManualBaseReviewButton.click")
    accept_click = next(node for node in ast.walk(rebind)
                        if isinstance(node, ast.Call)
                        and ast.unparse(node.func) == "accept_owner.click")
    assert review_click.lineno < accept_click.lineno
    configure_base_controls = next(node for node in ast.walk(rebind)
                                   if isinstance(node, ast.Call)
                                   and ast.unparse(node)
                                   == "widget._configureRobotSimulationShellSubstep(1)")
    refresh_base_controls = next(node for node in ast.walk(rebind)
                                 if isinstance(node, ast.Call)
                                 and ast.unparse(node)
                                 == "widget._updateStep6PlanningUi()")
    assert configure_base_controls.lineno < refresh_base_controls.lineno < review_click.lineno
    assert configure_base_controls.lineno < accept_click.lineno
    active_base_guard = next(node for node in ast.walk(rebind)
                             if isinstance(node, ast.If)
                             and "panel._activeSubstep != 1" in ast.unparse(node.test)
                             and "panel.beginManualBaseReviewButton.enabled"
                             in ast.unparse(node.test))
    assert active_base_guard.lineno < review_click.lineno
    assert "_same_matrix(staged_details.get('candidateMatrixWorldRasMm'), accepted_matrix)" in rebind_source
    assert "_same_matrix(staged_details.get('acceptedMatrixWorldRasMm'), accepted_matrix)" in rebind_source
    assert "_same_matrix(after.get('acceptedMatrixWorldRasMm'), accepted_matrix)" in rebind_source
    assert "'accepted_matrix_unchanged': _same_matrix(" in rebind_source
    assert "'base_pose_fingerprint_unchanged': pose_fingerprint_after == pose_fingerprint_before" in rebind_source
    assert "'case_unchanged': case_hash_after == case_hash" in rebind_source
    assert "(not evidence['accepted_matrix_unchanged'])" in rebind_source
    assert "(not evidence['base_pose_fingerprint_unchanged'])" in rebind_source
    assert "(not evidence['case_unchanged'])" in rebind_source
    assert "'native_scene_acknowledgement': 'deferred_until_after_connect'" in rebind_source
    assert "evidence['scene_acknowledgement_deferred'] = True" in rebind_source
    assert "_scene_evidence(" not in rebind_source
    assert "syncCollisionButton" not in rebind_source

    rebind_call = next(node for node in ast.walk(run)
                       if isinstance(node, ast.Call)
                       and ast.unparse(node.func) == "_run_base_profile_rebind_prerequisite")
    connect_guard = next(node for node in ast.walk(run)
                         if isinstance(node, ast.If)
                         and ast.unparse(node.test) == "not panel.connectButton.enabled")
    connect_click = next(node for node in ast.walk(run)
                         if isinstance(node, ast.Call)
                         and ast.unparse(node.func) == "panel.connectButton.click")
    assert rebind_call.lineno < connect_guard.lineno < connect_click.lineno

    sync_click = next(node for node in ast.walk(run)
                      if isinstance(node, ast.Call)
                      and ast.unparse(node.func) == "panel.syncCollisionButton.click")
    scene_readback = next(node for node in ast.walk(run)
                          if isinstance(node, ast.Call)
                          and ast.unparse(node.func) == "_scene_evidence")
    scene_ack_gate = next(node for node in ast.walk(run)
                          if isinstance(node, ast.If)
                          and "scene_ack.get('status') != 'Acknowledged'"
                          in ast.unparse(node.test))
    assert connect_click.lineno < sync_click.lineno < scene_readback.lineno < scene_ack_gate.lineno

    later_run_clicks = [node for node in ast.walk(run)
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "click"
                        and node.lineno > connect_click.lineno]
    later_sources = [ast.unparse(node.func) for node in later_run_clicks]
    assert "panel.beginManualBaseReviewButton.click" in later_sources
    assert "panel.cancelManualBaseReviewButton.click" in later_sources
    assert any(_is_guarded_click(node, "base_acceptance_owner")
               and node.lineno > connect_click.lineno for node in ast.walk(run))
    assert "panel.reviewTaskHomeButton.click" in later_sources
    assert "task_home_accept_owner.click" in later_sources


def test_migrated_task_prerequisites_run_after_scene_ack_before_draft_and_rejection_identity():
    run = next(node for node in TREE.body
               if isinstance(node, ast.FunctionDef) and node.name == "run")
    checks = _module_constant("CHECK_NAMES")
    assert "profile_migration_recovery_after_scene_ack" in checks

    recovery = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_ensure_current_home_workspace_task"
        and any(keyword.arg == "phase"
                and ast.literal_eval(keyword.value) == "after_scene_ack"
                for keyword in node.keywords)
    )
    scene_ack_gate = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.If)
        and "scene_ack.get('status') != 'Acknowledged'" in ast.unparse(node.test)
    )
    rejection_identity = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name)
                and target.id == "manual_jog_fixture_identity"
                for target in node.targets)
        and isinstance(node.value, ast.Call)
        and ast.unparse(node.value.func) == "_manual_jog_fixture_identity"
    )
    draft_check = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and ast.unparse(node.func) == "panel.checkManualDraftStateButton.click"
    )
    assert scene_ack_gate.end_lineno < recovery.lineno
    assert recovery.lineno < rejection_identity.lineno < draft_check.lineno


def test_migrated_prerequisite_recovery_uses_production_controls_and_checks_evidence():
    ensure = next(node for node in TREE.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "_ensure_current_home_workspace_task")
    # Home staging/acceptance lives in a helper shared with session commands
    # (2026-10-02); ensure calls it before the workspace/limits/confirm clicks.
    home = next(node for node in TREE.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "_accept_current_state_as_task_home")
    source = ast.unparse(ensure) + "\n" + ast.unparse(home)
    home_lines = [next(node for node in _button_clicks(home, control)).lineno
                  for control in ("reviewTaskHomeButton", "acceptTaskHomeButton")]
    assert home_lines == sorted(home_lines)
    helper_call = next(
        node for node in ast.walk(ensure)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_accept_current_state_as_task_home"
    )
    click_lines = [helper_call.lineno]
    for control in ("generateRobotWorkspaceButton", "reviewLimitsButton", "confirmTaskButton"):
        click = next(node for node in _button_clicks(ensure, control))
        click_lines.append(click.lineno)
    assert click_lines == sorted(click_lines)

    for required in (
        "state_fields = ('accepted_si', 'monitored_si', 'displayed_si')",
        "_finite_vector(state_before['accepted_si'])",
        "accepted_si",
        "monitored_si",
        "displayed_si",
        "_exactly_matches",
        "candidateJointPositionsSi",
        "staged",
        "home_revision <= old_revision",
        "taskHomeRuntimeValidated",
        "runtime_validation_status != 'Validated'",
        "workspace",
        "confirmedTaskRecord",
        "confirmedTaskFreshnessIssues",
        "_sha256_file(case_path)",
        "case_hash",
        "route_authority",
        "planner_calls",
        "preview_started",
        "previewActive",
    ):
        assert required in source
    assert not any(
        name in source
        for name in ("planApproach", "planDrilling", "previewApproach", "previewDrilling")
    )


def test_workspace_review_uses_production_refresh_and_persists_last_boundary():
    ensure = next(node for node in TREE.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "_ensure_current_home_workspace_task")
    generation = next(node for node in ast.walk(ensure)
                      if _is_guarded_click(node, "widget.ui.generateRobotWorkspaceButton"))
    review = next(node for node in ast.walk(ensure)
                  if isinstance(node, ast.Call)
                  and ast.unparse(node.func) == "panel.reviewLimitsButton.click")
    markers = sorted(
        (node for node in ast.walk(ensure)
         if isinstance(node, ast.Assign)
         and ast.unparse(node.targets[0]) == "evidence['last_completed_boundary']"),
        key=lambda node: node.lineno,
    )
    assert [ast.literal_eval(node.value) for node in markers] == [
        "before_workspace_generation_click",
        "workspace_generation_returned_current",
        "before_assisted_limit_review_click",
        "assisted_limit_review_returned_current",
    ]
    assert markers[0].lineno < generation.lineno < markers[1].lineno
    assert markers[2].lineno < review.lineno < markers[3].lineno

    statements = ensure.body
    for marker in markers:
        next_statement = statements[statements.index(marker) + 1]
        assert isinstance(next_statement, ast.Expr)
        assert ast.unparse(next_statement.value) == "_write_report(report)"

    runtime_validation = next(node for node in ast.walk(ensure)
                              if isinstance(node, ast.If)
                              and "facade.workspaceRuntimeValidated(parameter_node) is not True"
                              in ast.unparse(node.test))
    limits_validation = next(node for node in ast.walk(ensure)
                             if isinstance(node, ast.If)
                             and "logic.assistedTaskLimitsReviewed(parameter_node) is not True"
                             in ast.unparse(node.test))
    assert generation.lineno < runtime_validation.lineno < markers[1].lineno
    assert review.lineno < limits_validation.lineno < markers[3].lineno
    assert not any(
        isinstance(node, ast.Call)
        and ast.unparse(node.func) == "widget._updateStep6PlanningUi"
        and generation.lineno < node.lineno < review.lineno
        for node in ast.walk(ensure)
    )

    production_source = (
        RUNNER.parent.parent
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot.py"
    ).read_text(encoding="utf-8")
    production_tree = ast.parse(production_source)
    production_handler = next(node for node in ast.walk(production_tree)
                              if isinstance(node, ast.FunctionDef)
                              and node.name == "onGenerateRobotWorkspace")
    cloud_generation = next(node for node in ast.walk(production_handler)
                            if isinstance(node, ast.Call)
                            and ast.unparse(node.func)
                            == "self._robotWorkflowFacade.generateWorkspaceCloud")
    production_refresh = next(node for node in ast.walk(production_handler)
                              if isinstance(node, ast.Call)
                              and ast.unparse(node.func) == "self._updateStep6PlanningUi"
                              and ast.unparse(node.args[0]) == "planning_message")
    busy_reset = next(node for node in ast.walk(production_handler)
                      if isinstance(node, ast.Assign)
                      and ast.unparse(node.targets[0]) == "self._workflowActionBusy"
                      and ast.unparse(node.value) == "False")
    assert cloud_generation.lineno < busy_reset.lineno < production_refresh.lineno


def test_migration_roi_recovery_uses_visible_production_source_control():
    ensure = next(node for node in TREE.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "_ensure_current_home_workspace_task")
    source = ast.unparse(ensure)
    assert "_onStep6UseCurrentIncisorMidpoint" not in source

    load_state = next(
        node for node in ast.walk(ensure)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "roi_loaded"
                for target in node.targets)
    )
    assert "_taskSpaceRoiInitialized" in ast.unparse(load_state.value)
    assert ast.unparse(load_state.value).startswith("not ")
    load_gate = next(
        node for node in ast.walk(ensure)
        if isinstance(node, ast.If) and ast.unparse(node.test) == "roi_loaded"
    )
    branch = ast.Module(body=load_gate.body, type_ignores=[])
    button_binding = next(
        node for node in ast.walk(branch)
        if isinstance(node, ast.Assign)
        and ast.unparse(node.value) == "panel.useCurrentIncisorMidpointButton"
    )
    button_name = ast.unparse(button_binding.targets[0])
    scroll = next(
        node for node in ast.walk(branch)
        if isinstance(node, ast.Call)
        and ast.unparse(node.func) == "_scroll_to_visible"
        and button_name in ast.unparse(node)
    )
    availability_gate = next(
        node for node in ast.walk(branch)
        if isinstance(node, ast.If)
        and ".enabled" in ast.unparse(node.test)
        and "_visible(" in ast.unparse(node.test)
        and button_name in ast.unparse(node.test)
    )
    click = next(
        node for node in ast.walk(branch)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "click"
        and ast.unparse(node.func.value) == button_name
    )
    process = next(
        node for node in ast.walk(branch)
        if isinstance(node, ast.Call)
        and ast.unparse(node.func) == "_process_events"
        and node.lineno > click.lineno
    )
    initialized_check = next(
        node for node in ast.walk(branch)
        if isinstance(node, ast.If)
        and "_taskSpaceRoiInitialized" in ast.unparse(node.test)
        and node.lineno > process.lineno
    )
    assert ast.unparse(initialized_check.test).startswith("not ")
    evidence_validation = next(
        node for node in ast.walk(ensure)
        if isinstance(node, ast.If)
        and "math.isfinite" in ast.unparse(node.test)
        and "roi_opening_revision" in ast.unparse(node.test)
        and "roi_gap_line_id" in ast.unparse(node.test)
        and node.lineno > process.lineno
    )
    math_check = next(
        node for node in ast.walk(evidence_validation)
        if isinstance(node, ast.Call)
        and ast.unparse(node.func) == "math.isfinite"
    )
    capture = next(
        node for node in ast.walk(ensure)
        if isinstance(node, ast.Call)
        and ast.unparse(node.func) == "_capture"
        and "task-space-roi-before-workspace" in ast.unparse(node)
    )
    assert button_binding.lineno < scroll.lineno < availability_gate.lineno < click.lineno
    assert click.lineno < process.lineno < initialized_check.lineno
    assert process.lineno < math_check.lineno
    assert process.lineno < evidence_validation.lineno < capture.lineno
    assert evidence_validation.end_lineno < capture.lineno
    assert capture.lineno < next(
        node.lineno for node in ast.walk(ensure)
        if _is_guarded_click(node, "widget.ui.generateRobotWorkspaceButton")
    )
    assert "_taskSpaceRoiOpeningRevision" in source
    assert "_taskSpaceRoiGapLineNodeId" in source
    assert "taskSpaceRoiCenterSpinBoxes" in source
    assert "taskSpaceRoiDimensionsSpinBoxes" in source
    assert "float(spin.value)" in source
    for field in (
        "_taskSpaceRoiOpeningRevision",
        "_taskSpaceRoiGapLineNodeId",
        "taskSpaceRoiCenterSpinBoxes",
        "taskSpaceRoiDimensionsSpinBoxes",
    ):
        read = next(
            node for node in ast.walk(ensure)
            if isinstance(node, ast.Attribute)
            and node.attr == field
            and node.lineno > process.lineno
        )
        assert read.lineno < evidence_validation.lineno
    assert "type(roi_opening_revision) is not int" in ast.unparse(evidence_validation.test)
    assert "not isinstance(roi_gap_line_id, str)" in ast.unparse(evidence_validation.test)
    assert "not roi_gap_line_id.strip()" in ast.unparse(evidence_validation.test)


def test_migration_prerequisites_are_rechecked_after_base_home_acceptance_before_save():
    run = next(node for node in TREE.body
               if isinstance(node, ast.FunctionDef) and node.name == "run")
    checks = _module_constant("CHECK_NAMES")
    assert "profile_migration_recovery_before_save" in checks
    before_save = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_ensure_current_home_workspace_task"
        and any(keyword.arg == "phase"
                and ast.literal_eval(keyword.value) == "before_save"
                for keyword in node.keywords)
    )
    base_accept = next(node for node in ast.walk(run)
                       if _is_guarded_click(node, "base_acceptance_owner"))
    home_accept = next(node for node in ast.walk(run)
                       if isinstance(node, ast.Call)
                       and ast.unparse(node.func) == "task_home_accept_owner.click")
    save = next(node for node in ast.walk(run)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_save_current_case")
    assert base_accept.lineno < before_save.lineno
    assert home_accept.lineno < before_save.lineno < save.lineno


def test_migration_prerequisite_failure_persists_each_post_confirmation_invariant():
    ensure = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_ensure_current_home_workspace_task"
    )
    source = ast.unparse(ensure)
    for field in (
        "confirmed_task_present",
        "confirmed_task_freshness_issues",
        "assisted_limits_reviewed",
        "task_home_runtime_validated",
        "workspace_runtime_validated",
        "route_preview_unchanged",
        "source_case_unchanged",
    ):
        assert repr(field) in source
    evidence_write = next(
        node for node in ast.walk(ensure)
        if isinstance(node, ast.Call)
        and ast.unparse(node) == "_write_report(report)"
        and node.lineno > next(
            item.lineno for item in ast.walk(ensure)
            if isinstance(item, ast.Assign)
            and "post_confirmation_invariants" in ast.unparse(item)
        )
    )
    combined_failure = next(
        node for node in ast.walk(ensure)
        if isinstance(node, ast.If)
        and "confirmed_after is None" in ast.unparse(node.test)
    )
    assert evidence_write.lineno < combined_failure.lineno


def test_opt_in_acceptance_verifies_base_home_owners_and_stops_on_first_failure():
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    gate = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.If)
        and ast.unparse(node.test) == "not allow_base_home_accept"
        and "'task_home_review_acceptance_trial'" in ast.unparse(node)
    )
    acceptance = ast.unparse(gate.orelse)
    for required in (
        "panel.beginManualBaseReviewButton.click()",
        "base_acceptance_owner = widget.ui.lockRobotBaseMountButton",
        "_modal_guarded_click(report, evidence_dir, run_id, base_acceptance_owner, 'base-acceptance-accept')",
        "_same_matrix(base_acceptance_stage_details.get('candidateMatrixWorldRasMm'), base_matrix)",
        "expected_accept_matrix = list(base_matrix)",
        "_same_matrix(base_after_details.get('acceptedMatrixWorldRasMm'), expected_accept_matrix)",
        "not bool(parameter_node.robotBaseMountLocked)",
        "scene_ack_after_base_accept.get('status') != 'Acknowledged'",
        "scene_after_base_accept['source_object_ids'] != scene_after_base_accept['acknowledged_object_ids']",
        "_scene_evidence(logic, parameter_node)",
        "panel.reviewTaskHomeButton.click()",
        "task_home_accept_owner = panel.acceptTaskHomeButton",
        "task_home_accept_owner.click()",
        "_display_values(home_state_before['accepted_si'])",
        "_representationally_matches(staged_task_home_details.get('candidateJointPositionsSi'), home_state_before['accepted_si'])",
        "home_json_after_stage != home_json_before_stage",
        "_exactly_matches(home_state_before[key], home_state_after_stage.get(key))",
        "prior_saved_home = logic.taskHomeRecord(parameter_node)",
        "prior_saved_home_revision",
        "saved_home_revision",
        "saved_home_revision > (prior_saved_home_revision or 0)",
        "acceptance_commit_inferred = bool(",
        "and saved_home_revision_advanced",
        "task_home_after_details.get('acceptanceStatus') != 'accepted'",
        "task_home_after_details.get('identityStatus') != 'current'",
        "task_home_after_details.get('staged') is not False",
        "saved_home.runtime_validation_status != 'Validated'",
        "home_state_unchanged = all(",
        "_exactly_matches(home_state_before[key], state_after_home_accept.get(key))",
        "task_home_after_details.get('acceptedJointPositionsSi')",
        "_representationally_matches(saved_home_vector, state_after_home_accept[key])",
        "saved_home_runtime_validation_status=saved_home.runtime_validation_status",
        "acceptance_commit={",
        "'status': 'inferred'",
        "'prior_saved_home_revision': prior_saved_home_revision",
        "'saved_home_revision': saved_home_revision",
        "_capture(report, evidence_dir, run_id, 'base-acceptance-staged')",
        "_capture(report, evidence_dir, run_id, 'base-acceptance-accepted')",
        "_capture(report, evidence_dir, run_id, 'task-home-review-staged')",
        "_capture(report, evidence_dir, run_id, 'task-home-review-accepted')",
        "_record(report, active_check, 'PASS'",
    ):
        assert required in acceptance
    assert "_guard_click(" not in acceptance
    assert "guardedManualJogButton.click()" not in acceptance
    assert "applyTaskHomeButton.click()" not in acceptance
    assert "planApproach" not in acceptance and "planDrilling" not in acceptance
    assert "previewApproach" not in acceptance and "previewDrilling" not in acceptance
    assert "saveCase" not in acceptance and "save_case" not in acceptance
    assert "hardware_execution" not in acceptance
    assert "homeAcceptanceResult" not in SOURCE

    prior_home = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "prior_saved_home"
                for target in node.targets)
    )
    prior_revision = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "prior_saved_home_revision"
                for target in node.targets)
    )
    accept_click = next(
        node for node in ast.walk(gate)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "click"
        and ast.unparse(node.func.value) == "task_home_accept_owner"
    )
    new_revision = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "saved_home_revision"
                for target in node.targets)
    )
    assert prior_home.lineno < prior_revision.lineno < accept_click.lineno < new_revision.lineno

    fail = next(
        node for node in run.body
        if isinstance(node, ast.FunctionDef) and node.name == "fail"
    )
    assert any(isinstance(node, ast.Raise) for node in ast.walk(fail))
    stopped_handler = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.ExceptHandler)
        and ast.unparse(node.type) == "Exception"
        and "Stopped after first failure" in ast.unparse(node)
    )
    assert "complete_not_run(CHECK_NAMES" in ast.unparse(stopped_handler)
    # The only handler is the modal watchdog, which still stops on first failure.
    assert acceptance.count("except") == acceptance.count("except UnexpectedModalError as exc:")
    assert "fail(active_check, f'Accept Base raised a modal: {exc.dialog_text}'" in acceptance


def test_checklist_records_three_verdicts_and_no_case_save():
    assert '"PASS"' in SOURCE
    assert '"FAIL"' in SOURCE
    assert '"NOT_RUN"' in SOURCE
    assert '"saved_case": False' in SOURCE
    assert '"hardware_execution": False' in SOURCE
    assert '"route_authority": "none"' in SOURCE
    assert '"planner_calls": 0' in SOURCE
    assert '"preview_started": False' in SOURCE


def test_case_tcp_external_mouse_drag_is_exact_opt_in_and_case_bound(monkeypatch):
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    call = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_case_bound_tcp_probe"
    )
    assert ast.unparse(call.args[3]) == "evidence_dir.parent"
    callback = next(
        keyword.value for keyword in call.keywords
        if keyword.arg == "mouse_drag_callback"
    )
    assert ast.unparse(callback) == (
        "make_external_mouse_drag_callback(evidence_dir.parent) "
        "if _mouse_drag_requested() else None"
    )
    assert "from run_dentobot_tcp_workbench_headed import (" in SOURCE
    assert "_mouse_drag_requested," in SOURCE
    assert "make_external_mouse_drag_callback," in SOURCE

    requested = _extract_tcp_workbench_helper("_mouse_drag_requested")
    monkeypatch.delenv("DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG", raising=False)
    assert requested() is False
    monkeypatch.setenv("DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG", "0")
    assert requested() is False
    monkeypatch.setenv("DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG", "1")
    assert requested() is True
    for value in ("yes", "true", "01", " "):
        monkeypatch.setenv("DENTOBOT_TCP_WORKBENCH_MOUSE_DRAG", value)
        with pytest.raises(RuntimeError, match="must be '1', '0', or unset"):
            requested()


def test_full_chain_probe_counts_follow_exception_evidence_without_false_preview():
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    chain_call = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_full_chain_interruption_probe"
    )
    handler = next(
        item for node in ast.walk(run) if isinstance(node, ast.Try)
        for item in node.handlers
        if item.name == "exc"
        and ast.unparse(item.type) == "Exception"
        and "_retain_full_chain_probe_counts" in ast.unparse(item)
    )
    handler_source = ast.unparse(handler)
    assert "_retain_full_chain_probe_counts(report, getattr(exc, 'evidence', None))" in handler_source
    assert handler_source.index("_retain_full_chain_probe_counts") < handler_source.index("fail(")
    assert '"PASS"' not in handler_source

    retain = _extract_helper("_retain_full_chain_probe_counts", {"Mapping": Mapping})
    report = {"planner_calls": 0, "preview_started": False}
    failed_before_preview = RuntimeError("preview not reached")
    failed_before_preview.evidence = {
        "probe_local_button_invocations": {
            "plan_guarded_approach": 1,
            "preview_approach": 0,
        }
    }
    retain(report, failed_before_preview.evidence)
    assert report == {"planner_calls": 1, "preview_started": False}

    failed_after_preview = RuntimeError("preview interrupted")
    failed_after_preview.evidence = {
        "probe_local_button_invocations": {
            "plan_guarded_approach": 1,
            "preview_approach": 1,
        }
    }
    retain(report, failed_after_preview.evidence)
    assert report == {"planner_calls": 1, "preview_started": True}


def test_complete_cycle_runner_opt_ins_are_itemized_and_fail_closed(monkeypatch):
    checks = _module_constant("CHECK_NAMES")
    assert "base_home_uncertainty" in checks
    assert "complete_cycles" in checks
    assert 'DENTOBOT_HEADED_BASE_HOME_UNCERTAINTY' in SOURCE
    assert 'DENTOBOT_HEADED_COMPLETE_CYCLES' in SOURCE
    assert 'DENTOBOT_HEADED_BASE_HOME_UNCERTAINTY is unset or \'0\'.' in SOURCE
    assert 'DENTOBOT_HEADED_COMPLETE_CYCLES is unset or \'0\'.' in SOURCE

    exact = _extract_helper("_exact_env_opt_in", {"os": os})
    for name in (
        "DENTOBOT_HEADED_BASE_HOME_UNCERTAINTY",
        "DENTOBOT_HEADED_COMPLETE_CYCLES",
    ):
        monkeypatch.delenv(name, raising=False)
        assert exact(name) is False
        monkeypatch.setenv(name, "0")
        assert exact(name) is False
        monkeypatch.setenv(name, "1")
        assert exact(name) is True
        monkeypatch.setenv(name, "true")
        with pytest.raises(RuntimeError, match="must be exactly '1', '0', or unset"):
            exact(name)

    validate = _extract_helper("_validate_step6_live_probe_opt_ins")
    common = {
        "base_home_uncertainty": False,
        "complete_cycles": False,
        "full_chain": False,
        "allow_jog": True,
        "allow_base_home_accept": True,
        "workspace_diagnostic": False,
        "draft_only": False,
    }
    validate(**{**common, "base_home_uncertainty": True})
    validate(**{**common, "complete_cycles": True})
    with pytest.raises(RuntimeError, match="separate fresh processes"):
        validate(**{**common, "complete_cycles": True, "full_chain": True})
    with pytest.raises(RuntimeError, match="workspace diagnostic"):
        validate(**{**common, "base_home_uncertainty": True, "workspace_diagnostic": True})
    with pytest.raises(RuntimeError, match="draft-only"):
        validate(**{**common, "complete_cycles": True, "draft_only": True})
    with pytest.raises(RuntimeError, match="ALLOW_JOG=1"):
        validate(**{**common, "complete_cycles": True, "allow_jog": False})
    with pytest.raises(RuntimeError, match="ALLOW_BASE_HOME_ACCEPT=1"):
        validate(**{**common, "base_home_uncertainty": True, "allow_base_home_accept": False})


def test_complete_cycle_runner_orders_uncertainty_tcp_cycles_and_interruption():
    run = next(node for node in TREE.body
               if isinstance(node, ast.FunctionDef) and node.name == "run")
    calls = {
        node.func.id: node.lineno
        for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {
            "run_base_home_uncertainty_probe",
            "run_case_bound_tcp_probe",
            "run_complete_cycles",
            "run_full_chain_interruption_probe",
        }
    }
    assert set(calls) == {
        "run_base_home_uncertainty_probe",
        "run_case_bound_tcp_probe",
        "run_complete_cycles",
        "run_full_chain_interruption_probe",
    }
    assert "make_expected_error_dialog_callback" in SOURCE
    assert _module_constant("BASE_HOME_UNCERTAINTY_DIALOG_TIMEOUT_SEC") == 180.0
    assert "dialog_timeout_sec = BASE_HOME_UNCERTAINTY_DIALOG_TIMEOUT_SEC" in SOURCE
    assert "timeout_sec=dialog_timeout_sec" in SOURCE
    assert (
        '"expected_error_dialog_combined_action_and_modal_appearance_timeout_sec"'
        in SOURCE
    )
    assert (
        "expected_error_dialog_combined_action_and_modal_appearance_timeout_sec=dialog_timeout_sec"
        in SOURCE
    )
    cycle_call = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_complete_cycles"
    )
    keywords = {keyword.arg: keyword.value for keyword in cycle_call.keywords}
    assert ast.unparse(keywords["cycles"]) == "2"
    assert ast.unparse(keywords["process_events"]) == "_process_events"
    assert ast.unparse(keywords["joint_names"]) == "JOINT_NAMES"
    assert calls["run_base_home_uncertainty_probe"] < calls["run_case_bound_tcp_probe"]
    assert calls["run_case_bound_tcp_probe"] < calls["run_complete_cycles"]
    assert calls["run_complete_cycles"] < calls["run_full_chain_interruption_probe"]


def test_complete_cycle_pass_gate_requires_two_fully_observed_cycles():
    passed = _extract_helper("_complete_cycles_passed", {"Mapping": Mapping})

    def valid_cycle(session, plan_id):
        endpoint_phase = {
            "endpoint_verified": True,
            "completion_observation": {
                "observed_active": True,
                "configured_preview_speed_multiplier": 0.25,
            },
            "endpoint_fk": {
                "status": "passed",
                "observation_kind": "post_completion_observation",
            },
        }
        return {
            "route_provenance": {
                "task_identity": "task",
                "diagnostic_session_fingerprint": session,
                "phase_guard_session_id": "guard-" + session,
                "approach_plan": {"plan_instance_id": plan_id},
            },
            "boundaries": {
                "approach_endpoint_verified": endpoint_phase,
                "drill_endpoint_verified": endpoint_phase,
                "return_home_verified": {
                    "phase_session_cleared": True,
                    "reverse_phase_execution_status_evidence": {
                        "phase_destination_sequence_matches_history": True,
                        "axial_retraction_completed": True,
                        "production_result_details_captured_by_read_only_observer": True,
                    },
                    "saved_home_error": {
                        "accepted_monitored_displayed_all_match_saved_home": True,
                    },
                },
            },
        }

    evidence = {
        "fresh_repeat_completed": True,
        "route_fingerprint_comparison_used": False,
        "cycles": [valid_cycle("session-1", 101), valid_cycle("session-2", 202)],
    }
    assert passed(evidence) is True
    recycled_address = {
        **evidence,
        "cycles": [valid_cycle("session-1", 101), valid_cycle("session-2", 101)],
    }
    assert passed(recycled_address) is True
    assert passed({**evidence, "cycles": evidence["cycles"][:1]}) is False
    stale_second = dict(evidence["cycles"][1])
    stale_second["route_provenance"] = {
        **stale_second["route_provenance"],
        "diagnostic_session_fingerprint": "session-1",
    }
    assert passed({**evidence, "cycles": [evidence["cycles"][0], stale_second]}) is False
    bad = {**evidence, "cycles": [dict(evidence["cycles"][0]), evidence["cycles"][1]]}
    bad["cycles"][0]["boundaries"] = dict(bad["cycles"][0]["boundaries"])
    bad["cycles"][0]["boundaries"]["return_home_verified"] = {
        **bad["cycles"][0]["boundaries"]["return_home_verified"],
        "phase_session_cleared": False,
    }
    assert passed(bad) is False


def test_complete_cycle_count_capture_ignores_malformed_counts_without_changing_verdict():
    retain = _extract_helper("_retain_complete_cycle_probe_counts", {"Mapping": Mapping})
    report = {
        "planner_calls": 0,
        "preview_started": False,
        "items": {"complete_cycles": {"status": "PASS"}},
    }
    retain(report, {
        "button_invocations": {
            "plan_guarded_approach": "not-a-count",
            "preview_approach": "NaN",
            "preview_drill": object(),
        },
    })
    assert report == {
        "planner_calls": 0,
        "preview_started": False,
        "items": {"complete_cycles": {"status": "PASS"}},
    }


def test_unconfirmed_draft_review_is_itemized_as_static_only_without_target_evidence():
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    run_source = ast.unparse(run)
    confirmed_task_capture = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "confirmed_task_present"
            for target in node.targets
        )
    )
    assert ast.unparse(confirmed_task_capture.value) == (
        "logic.confirmedTaskRecord(parameter_node) is not None"
    )
    draft_check = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "click"
        and ast.unparse(node.func.value) == "panel.checkManualDraftStateButton"
    )
    assert confirmed_task_capture.lineno < draft_check.lineno

    unconfirmed_guard = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.If)
        and "not confirmed_task_present" in ast.unparse(node.test)
        and "target_endpoint_status" in ast.unparse(node.test)
    )
    guard_source = ast.unparse(unconfirmed_guard.test)
    assert "target_endpoint_status != 'not_reached'" in guard_source
    assert "target_ras_mm is not None" in guard_source
    assert "value is not None for value in residuals.values()" in guard_source

    metadata_assignment = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "review_metadata"
            for target in node.targets
        )
    )
    assert isinstance(metadata_assignment.value, ast.Dict)
    metadata_values = {
        key.value: ast.unparse(value)
        for key, value in zip(metadata_assignment.value.keys, metadata_assignment.value.values)
    }
    assert metadata_values == {
        "confirmed_task_present": "confirmed_task_present",
        "review_scope": "review_scope",
        "target_endpoint_status": "target_endpoint_status",
        "target_ras_mm": "target_ras_mm",
        "residuals": "residuals",
    }

    item_record = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_record"
        and any(
            keyword.arg is None and ast.unparse(keyword.value) == "review_metadata"
            for keyword in node.keywords
        )
    )
    assert item_record is not None
    assert "**review_metadata" in run_source
    assert "'static_only_unconfirmed_task'" in run_source
    assert "'confirmed_task_endpoint'" in run_source


def test_jog_result_must_correlate_to_exact_scene_and_single_request():
    assert 'native_guard.get("responseCorrelated") is not True' in SOURCE
    assert 'native_guard.get("requestId") != jog_evidence.get("requestId")' in SOURCE
    assert 'native_guard.get("sessionId") != jog_evidence.get("sessionId")' in SOURCE
    assert 'native_guard.get("policyId") != bridge.ROS2_MANUAL_JOINT_POLICY_ID' in SOURCE
    assert 'native_guard.get("collisionScenePolicyIdentityStatus")' in SOURCE
    assert 'native_guard.get("worldObjectCount") != len(scene["source_object_ids"])' in SOURCE
    assert re.search(
        r'sorted\(str\(item\) for item in native_guard\.get\("worldObjectIds"\) or \(\)\)\s*!=\s*scene\["acknowledged_object_ids"\]',
        SOURCE,
    )
    assert "collisionScenePolicyFingerprint" not in SOURCE
    assert 'native_guard.get("bridgeReturnedAccepted") is not True' in SOURCE


def test_joint_display_roundtrip_and_cross_layer_comparison_allow_only_si_roundoff():
    matches = _extract_helper("_representationally_matches")
    assert matches({"J2": 0.00144}, {"J2": 0.0014399999999999999})
    assert matches({"J2": 0.0}, {"J2": 1.0e-12})
    assert not matches({"J2": 0.0}, {"J2": 1.0001e-12})
    # Relative tolerance would incorrectly accept this material SI difference.
    assert not matches({"J2": 1.0e3}, {"J2": 1.0e3 + 1.0e-11})
    assert not matches({"J2": 0.0}, {"J3": 0.0})

    guard_click = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_guard_click"
    )
    guard_source = ast.unparse(guard_click)
    assert "_setManualJogDraftValues(_display_values(target), notify=True)" in guard_source
    assert "_representationally_matches(draft, target)" in guard_source
    matcher_source = ast.unparse(
        next(
            node for node in TREE.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_representationally_matches"
        )
    )
    assert "math.isclose" in matcher_source
    assert "rel_tol=0.0" in matcher_source and "abs_tol=1e-12" in matcher_source

    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    run_source = ast.unparse(run)
    assert "_representationally_matches(before_draft['accepted_si'], before_draft['monitored_si'])" in run_source
    assert "_representationally_matches(before_draft['accepted_si'], before_draft['displayed_si'])" in run_source
    assert "_representationally_matches(requested_draft, before_draft['accepted_si'])" in run_source
    assert "_representationally_matches(matched[key], target)" in run_source


def test_native_request_and_accepted_echoes_remain_exact():
    matches = _extract_helper("_exactly_matches")
    exact = dict(zip(JOINT_NAMES, (0.0, 0.00144, 0.0, 0.02, 0.0)))
    rounded = dict(exact, **{JOINT_NAMES[1]: 0.0014399999999999999})
    assert matches(exact, exact)
    assert not matches(exact, rounded)

    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    native_guard_check = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.If)
        and "requestedPositionsSi" in ast.unparse(node.test)
    )
    native_guard_source = ast.unparse(native_guard_check.test)
    assert "_exactly_matches(native_guard.get('requestedPositionsSi'), target)" in native_guard_source
    assert "_exactly_matches(native_guard.get('acceptedPositionsSi'), target)" in native_guard_source
    assert "_representationally_matches" not in native_guard_source


def test_scene_readback_is_presence_only_and_manual_guard_supplies_authority():
    scene_helper = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_scene_evidence"
    )
    scene_source = ast.unparse(scene_helper)
    assert "'evidence_scope': 'object_presence_readback'" in scene_source
    assert "'authority_pending': 'native_manual_joint_guard'" in scene_source
    assert "collisionScenePolicyFingerprint" not in scene_source

    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    presence_gate = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.If)
        and "source_object_ids" in ast.unparse(node.test)
        and "acknowledged_object_ids" in ast.unparse(node.test)
    )
    presence_gate_source = ast.unparse(presence_gate.test)
    assert "scene_ack.get('status') != 'Acknowledged'" in presence_gate_source
    assert "scene['source_object_ids'] != scene['acknowledged_object_ids']" in presence_gate_source
    assert all(
        field not in presence_gate_source
        for field in ("trusted", "readback_correlated", "collisionScenePolicyFingerprint")
    )

    guard_gate = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.If)
        and "collisionScenePolicyIdentityStatus" in ast.unparse(node.test)
    )
    guard_gate_source = ast.unparse(guard_gate.test)
    for requirement in (
        "bridge.ROS2_MANUAL_JOINT_POLICY_ID",
        "manual_policy_id_correlated",
        "requestId",
        "sessionId",
        "worldObjectCount",
        "worldObjectIds",
    ):
        assert requirement in guard_gate_source


def test_production_robot_and_planning_context_prerequisites_precede_connect():
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    run_source = ast.unparse(run)
    button_aliases = {
        target.id: ast.unparse(node.value)
        for node in ast.walk(run)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Attribute)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    clicks = sorted(
        (node.lineno, button_aliases.get(node.func.value.id, node.func.value.id)
         if isinstance(node.func.value, ast.Name) else ast.unparse(node.func.value))
        for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "click"
    )
    button_order = [target for _line, target in clicks]
    robot = "panel.loadFallbackButton"
    context = "widget.ui.importStep6PlanningContextButton"
    connect = "panel.connectButton"
    assert button_order.count(robot) == 1
    assert button_order.count(context) == 1
    assert button_order.count(connect) == 1
    assert button_order.index(robot) < button_order.index(context) < button_order.index(connect)
    click_line = {target: line for line, target in clicks}
    for button in ("load_button", "import_button"):
        enabled_guards = [
            node.lineno for node in ast.walk(run)
            if isinstance(node, ast.If)
            and ast.unparse(node.test) == f"not {button}.enabled"
        ]
        assert enabled_guards and min(enabled_guards) < click_line[
            robot if button == "load_button" else context
        ]
    assert '"simulation_robot_models_loaded"' in SOURCE
    assert '"planning_context_imported"' in SOURCE
    assert "if not load_button.enabled" in run_source
    assert "if not import_button.enabled" in run_source
    assert "logic.robotModelNodes()" in run_source
    assert "len(logic.robotModelNodes()) == EXPECTED_ROBOT_LINK_COUNT" in run_source
    assert "if robot_models is None" in run_source
    assert "parameter_node.step6PlanningContextImported" in run_source
    assert "if not imported" in run_source
    assert "evaluatePreparedBranchEligibility(parameter_node)" in run_source
    assert "branch_before.get('eligible') is not True" in run_source
    assert "branch_before.get('reason') != 'VALID'" in run_source
    assert "branch_after.get('eligible') is not True" in run_source
    assert "branch_after.get('reason') != 'VALID'" in run_source
    assert "branch_after.get('branch_id') != branch_before.get('branch_id')" in run_source
    assert "widget._step6SceneKind() != 'case'" in run_source
    assigned_import_flag = any(
        isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
        and any(
            isinstance(target, ast.Attribute)
            and target.attr == "step6PlanningContextImported"
            for target in (
                node.targets if isinstance(node, ast.Assign)
                else [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign))
                else []
            )
        )
        for node in ast.walk(TREE)
    )
    assert not assigned_import_flag


def test_prerequisite_base_and_draft_controls_are_scrolled_before_screenshots():
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    scroll_calls = [
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_scroll_to_visible"
        and len(node.args) >= 2
    ]
    capture_calls = [
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_capture"
        and len(node.args) >= 4
        and isinstance(node.args[3], ast.Constant)
    ]
    expected = (
        ("load_button", "robot-models-loaded"),
        ("import_button", "planning-context-imported"),
        ("panel.manualBaseReviewGroup", "base-controls"),
        ("panel.manualJogGroup", "draft-state-control"),
    )
    for control, screenshot in expected:
        scroll = [
            node for node in scroll_calls
            if control in ast.unparse(node.args[1])
        ]
        capture = [
            node for node in capture_calls
            if node.args[3].value == screenshot
        ]
        assert scroll and capture
        assert any(item.lineno < shot.lineno for item in scroll for shot in capture)

    scroll_helper = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_scroll_to_visible"
    )
    helper_source = ast.unparse(scroll_helper)
    assert "isAncestorOf" in helper_source


def test_scroll_helper_uses_pythonqt_geometry_properties_and_checks_viewport():
    helper = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_scroll_to_visible"
    )
    source = ast.unparse(helper)
    geometry_properties = {
        ("control", "rect"),
        ("viewport", "width"),
        ("viewport", "height"),
        ("control", "width"),
        ("control", "height"),
    }
    accesses = {
        (ast.unparse(node.value), node.attr)
        for node in ast.walk(helper)
        if isinstance(node, ast.Attribute)
    }
    calls = {
        (ast.unparse(node.func.value), node.func.attr)
        for node in ast.walk(helper)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert geometry_properties <= accesses
    assert geometry_properties.isdisjoint(calls)

    intersection = next(
        node.value for node in ast.walk(helper)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "intersects_viewport"
            for target in node.targets
        )
    )
    intersection_accesses = {
        (ast.unparse(node.value), node.attr)
        for node in ast.walk(intersection)
        if isinstance(node, ast.Attribute)
    }
    assert isinstance(intersection, ast.BoolOp)
    assert geometry_properties - {("control", "rect")} <= intersection_accesses
    assert "ensureWidgetVisible" in source
    assert "if not intersects_viewport" in source


def test_scroll_helper_sets_vertical_scrollbar_then_recomputes_before_viewport_check():
    helper = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_scroll_to_visible"
    )
    ensure = next(
        node for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ensure_visible"
    )
    scrollbar = next(
        node for node in ast.walk(helper)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "scrollbar" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "verticalScrollBar"
        and ast.unparse(node.value.func.value) == "scroll_area"
    )
    scrollbar_set = next(
        node for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "setValue"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "scrollbar"
    )
    position_recompute = max(
        (
            node for node in ast.walk(helper)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "position" for target in node.targets)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "mapTo"
            and node.lineno > scrollbar_set.lineno
        ),
        key=lambda node: node.lineno,
    )
    viewport_check = next(
        node for node in ast.walk(helper)
        if isinstance(node, ast.If) and ast.unparse(node.test) == "not intersects_viewport"
    )
    assert ensure.lineno < scrollbar.lineno < scrollbar_set.lineno
    assert scrollbar_set.lineno < position_recompute.lineno < viewport_check.lineno


def test_scroll_helper_resets_horizontal_bar_scrolls_target_and_reports_oversize():
    scroll_to_visible = _extract_helper(
        "_scroll_to_visible",
        {
            "_process_events": lambda _seconds: None,
            "_visible": lambda control: control.isVisible(),
        },
    )

    class Point:
        def __init__(self, x, y):
            self._x, self._y = x, y

        def x(self):
            return self._x

        def y(self):
            return self._y

    class ScrollBar:
        def __init__(self, minimum, maximum, value):
            self.minimum, self.maximum, self.value = minimum, maximum, value

        def setValue(self, value):
            self.value = min(self.maximum, max(self.minimum, value))

    class Viewport:
        width, height = 300, 200

        def isAncestorOf(self, control):
            return control.parent is self

    class Control:
        rect = type("Rect", (), {"topLeft": lambda _self: Point(0, 0)})()
        height = 60

        def __init__(self, viewport, scroll_area, width):
            self.parent = viewport
            self.scroll_area = scroll_area
            self.width = width

        def isVisible(self):
            return True

        def mapTo(self, _viewport, _point):
            return Point(
                -(self.scroll_area.horizontalScrollBar().value - 10),
                260 - (self.scroll_area.verticalScrollBar().value - 5),
            )

    class ScrollArea:
        def __init__(self, viewport):
            self._viewport = viewport
            self._horizontal = ScrollBar(10, 110, 10)
            self._vertical = ScrollBar(5, 400, 5)

        def viewport(self):
            return self._viewport

        def horizontalScrollBar(self):
            return self._horizontal

        def verticalScrollBar(self):
            return self._vertical

        def ensureWidgetVisible(self, _control, _x, _y):
            self._horizontal.setValue(self._horizontal.maximum)

    def frame(width):
        viewport = Viewport()
        scroll_area = ScrollArea(viewport)
        widget = type("Widget", (), {"_workflowContentScrollArea": scroll_area})()
        control = Control(viewport, scroll_area, width)
        return scroll_to_visible(widget, control, "fake target"), scroll_area

    visible, scroll_area = frame(220)
    assert scroll_area.horizontalScrollBar().value == 10
    assert scroll_area.verticalScrollBar().value == 261
    assert visible["control_position"] == (0, 4)
    assert visible["control_size"] == (220, 60)
    assert visible["viewport_size"] == (300, 200)
    assert visible["horizontal_scrollbar_value"] == 10
    assert visible["horizontal_scrollbar_range"] == (10, 110)
    assert visible["vertical_scrollbar_value"] == 261
    assert visible["vertical_scrollbar_range"] == (5, 400)
    assert visible["visible_in_viewport"] is True
    assert visible["intersects_viewport"] is True
    assert visible["fully_visible_in_viewport"] is True
    assert visible["limitations"] == []

    oversized, scroll_area = frame(380)
    assert scroll_area.horizontalScrollBar().value == 10
    assert oversized["visible_in_viewport"] is True
    assert oversized["intersects_viewport"] is True
    assert oversized["fully_visible_in_viewport"] is False
    assert oversized["control_wider_than_viewport"] is True
    assert oversized["limitations"] == [
        "control is wider than the screenshot viewport; full width cannot fit"
    ]


def test_window_is_sized_before_capture_and_scroll_failures_include_geometry():
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    frame_calls = [
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and ast.unparse(node.func.value) == "main_window"
        and node.func.attr in {"resize", "move"}
    ]
    resize = next(node for node in frame_calls if node.func.attr == "resize")
    move = next(node for node in frame_calls if node.func.attr == "move")
    open_case = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_openCaseBundle"
    )
    capture_calls = [
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_capture"
    ]
    first_capture = min(capture_calls, key=lambda node: node.lineno)
    assert tuple(ast.literal_eval(arg) for arg in resize.args) == (1500, 850)
    assert tuple(ast.literal_eval(arg) for arg in move.args) == (0, 0)
    assert max(resize.lineno, move.lineno) < open_case.lineno < first_capture.lineno

    helper = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_scroll_to_visible"
    )
    details = next(
        node.value for node in ast.walk(helper)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "viewport_details"
            for target in node.targets
        )
    )
    for field in (
        "control_position",
        "control_size",
        "viewport_size",
        "horizontal_scrollbar_value",
        "horizontal_scrollbar_range",
        "vertical_scrollbar_value",
        "vertical_scrollbar_range",
    ):
        assert field in ast.unparse(details)
    for condition in ("not _visible(control)", "not intersects_viewport"):
        failure = next(
            node for node in ast.walk(helper)
            if isinstance(node, ast.If) and ast.unparse(node.test) == condition
        )
        assert any(
            isinstance(node, ast.Raise) and "viewport_details" in ast.unparse(node)
            for node in failure.body
        )


def test_joint_keyboard_draft_review_is_opt_in_physical_and_stops_before_jog():
    assert "manual_jog_keyboard_draft_check" in _module_constant("CHECK_NAMES")

    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    run_source = ast.unparse(run)
    assert "DENTOBOT_HEADED_JOINT_KEYBOARD" in run_source
    keyboard_check = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_run_manual_jog_keyboard_draft_check"
    )
    draft_check_click = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "click"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "checkManualDraftStateButton"
    )
    assert draft_check_click.lineno < keyboard_check.lineno
    assert "if joint_keyboard_only" in run_source
    assert "Joint keyboard draft-only review completed" in run_source

    helper = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_run_manual_jog_keyboard_draft_check"
    )
    helper_source = ast.unparse(helper)
    for required in (
        "manualJogKeyboardEnabledCheckBox",
        "manualJogKeyboardStepComboBox",
        "MANUAL_JOG_KEY_BINDINGS",
        "autoRepeat",
        "_deliver_key",
        "_setManualJogDraftValues",
        "numeric_editor_focus",
        "no_guard_request_plan_or_preview",
        "capture('failure')",
    ):
        assert required in helper_source
    assert "_onManualJogKeyboardNudge" not in helper_source
    assert "_guard_click" not in helper_source
    manual_control_lookups = [
        node for node in ast.walk(helper)
        if isinstance(node, ast.Subscript)
        and ast.unparse(node.value) == "panel.manualJogJointControls"
    ]
    assert manual_control_lookups
    assert all(
        not (
            isinstance(node.slice, ast.Constant)
            and node.slice.value in JOINT_NAMES
        )
        for node in manual_control_lookups
    )
    assert any(
        ast.unparse(node) == "panel.manualJogJointControls[JOINT_NAMES[0]]"
        for node in ast.walk(helper)
    )

    delivery = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_deliver_key"
    )
    delivery_source = ast.unparse(delivery)
    assert "QTest" in delivery_source and "keyClick" in delivery_source
    assert "QKeyEvent" in delivery_source and "sendEvent" in delivery_source
    assert "refusing callback fallback" in delivery_source
    assert "callback(" not in delivery_source


def test_keyboard_expected_si_uses_the_canonical_joint_name_at_each_display_index():
    state_path = (
        RUNNER.parent.parent
        / "DENTOWorkflow/Resources/Python/DENTOStep6State.py"
    )
    state_tree = ast.parse(state_path.read_text(encoding="utf-8"))
    canonical_names = ast.literal_eval(next(
        node.value for node in state_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "JOINT_NAMES"
            for target in node.targets
        )
    ))
    apply_step = _extract_helper(
        "_apply_display_step_to_expected_si", {"JOINT_NAMES": canonical_names}
    )
    before = {name: float(index) for index, name in enumerate(canonical_names)}
    for index, name in enumerate(canonical_names):
        expected = dict(before)
        expected[name] += 0.0001
        assert apply_step(before, index, 0.0001) == expected

    keyboard_check = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_run_manual_jog_keyboard_draft_check"
    )
    calls = sorted(
        (
            node for node in ast.walk(keyboard_check)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_apply_display_step_to_expected_si"
        ),
        key=lambda node: node.lineno,
    )
    assert len(calls) == 2
    assert ast.unparse(calls[0].args[1]) == "joint_index"
    assert ast.literal_eval(calls[1].args[1]) == 0


def test_workspace_diagnostic_finalizer_marks_scope_and_preserves_existing_verdicts():
    writes = []

    def retain_write(report):
        writes.append(json.loads(json.dumps(report)))

    finalize = _extract_helper("_finalize_workspace_diagnostic", {
        "_utc_now": lambda: "2026-09-30T00:00:00Z",
        "_write_report": retain_write,
    })
    report = {
        "status": "RUNNING",
        "items": {
            "workspace": {"status": "PASS", "reason": "workspace is current"},
            "scene": {"status": "NOT_RUN", "reason": "Not reached."},
            "save": {"status": "NOT_RUN", "reason": "Output case unset."},
            "earlier_failure": {"status": "FAIL", "reason": "existing failure"},
        },
    }

    finalize(report)

    assert report["status"] == "DIAGNOSTIC_PASS"
    assert report["completed_at_utc"] == "2026-09-30T00:00:00Z"
    assert "workspace-only diagnostic stop" in report["failure_or_stop_reason"]
    assert report["full_workflow_claimed"] is False
    assert report["items"]["workspace"] == {
        "status": "PASS",
        "reason": "workspace is current",
    }
    assert report["items"]["earlier_failure"] == {
        "status": "FAIL",
        "reason": "existing failure",
    }
    for name in ("scene", "save"):
        assert report["items"][name]["status"] == "NOT_RUN"
        assert "workspace-only diagnostic stop" in report["items"][name]["reason"]
    assert writes == [report]


def test_workspace_debugger_stop_precedes_later_actions():
    run = next(node for node in TREE.body
               if isinstance(node, ast.FunctionDef) and node.name == "run")
    ensure = next(node for node in TREE.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "_ensure_current_home_workspace_task")
    source = RUNNER.read_text(encoding="utf-8")
    assert ast.unparse(run.body[0]) == (
        "workspace_diagnostic = _validate_workspace_diagnostic_opt_in()"
    )
    native_gate = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.If) and "native is None" in ast.unparse(node.test)
    )
    assert "workspace_diagnostic" in ast.unparse(native_gate.test)
    assert "or native is None" in ast.unparse(run)
    ensure_call = next(
        node for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_ensure_current_home_workspace_task"
        and any(keyword.arg == "phase"
                and ast.literal_eval(keyword.value) == "after_scene_ack"
                for keyword in node.keywords)
    )
    assert any(keyword.arg == "workspace_diagnostic"
               and ast.unparse(keyword.value) == "workspace_diagnostic"
               for keyword in ensure_call.keywords)
    force_diagnostic = next(
        node for node in ast.walk(ensure)
        if isinstance(node, ast.If)
        and ast.unparse(node.test) == "workspace_diagnostic and phase == 'after_scene_ack'"
    )
    assert any(
        isinstance(statement, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "needs_recovery"
                for target in statement.targets)
        and ast.unparse(statement.value) == "True"
        for statement in force_diagnostic.body
    )
    stop = source.index('if _exact_env_opt_in("DENTOBOT_HEADED_STOP_AFTER_WORKSPACE"):')
    limits = source.index("if not panel.reviewLimitsButton.enabled:", stop)
    block = source[stop:limits]
    assert "DENTOBOT_HEADED_WORKSPACE_DIAGNOSTIC_PASS" in block
    assert "_finalize_workspace_diagnostic(report)" in block
    assert "slicer.util.exit(0)" in block
    assert "raise SystemExit(0)" in block
    assert ".click()" not in block


def test_integration_connect_only_requires_provenance_and_excludes_other_actions(monkeypatch):
    for name in tuple(os.environ):
        if name.startswith("DENTOBOT_HEADED_"):
            monkeypatch.delenv(name)
    exact_opt_in = _extract_helper("_exact_env_opt_in", {"os": os})
    requested = _extract_helper("_connect_only_requested", {"os": os, "_exact_env_opt_in": exact_opt_in})
    assert requested() is False
    monkeypatch.setenv("DENTOBOT_HEADED_CONNECT_ONLY", "yes")
    with pytest.raises(RuntimeError, match="exactly"):
        requested()
    monkeypatch.setenv("DENTOBOT_HEADED_CONNECT_ONLY", "1")
    with pytest.raises(RuntimeError, match="integration provenance"):
        requested()
    monkeypatch.setenv("DENTOBOT_HEADED_PROVENANCE_MODE", "integration")
    with pytest.raises(RuntimeError, match="native provenance"):
        requested()
    for name in ("NATIVE_SOURCE_SHA256", "NATIVE_BINARY_SHA256", "NATIVE_PACKAGE_PREFIX"):
        monkeypatch.setenv("DENTOBOT_HEADED_" + name, "reviewed")
    assert requested() is True
    for name in ("ALLOW_JOG", "ALLOW_BASE_HOME_ACCEPT", "STOP_AFTER_WORKSPACE", "OUTPUT_CASE"):
        monkeypatch.setenv("DENTOBOT_HEADED_" + name, "1")
        with pytest.raises(RuntimeError, match="other actions"):
            requested()
        monkeypatch.delenv("DENTOBOT_HEADED_" + name)

def test_active_modal_screenshot_precedes_window_and_viewport_without_showing_window(tmp_path):
    capture, events = _screenshot_capture_fixture(tmp_path, modal_mode="ok")

    result = capture("base-error", tmp_path)

    assert result["modal"] == "base-error-modal.png"
    assert (tmp_path / result["modal"]).read_bytes() == b"screenshot"
    assert events.index("modal_grab") < events.index("modal_save")
    assert events.index("modal_save") < events.index("window_grab")
    assert events.index("window_grab") < events.index("viewport_save")
    assert "window_show" not in events
    assert "process_events" not in events


@pytest.mark.parametrize(
    ("modal_mode", "message"),
    [
        ("null", "Could not capture active modal screenshot"),
        ("save-failure", "Could not save active modal screenshot"),
        ("empty", "Active modal screenshot is empty"),
    ],
)
def test_active_modal_capture_failures_stop_before_main_window_activation(
    tmp_path, modal_mode, message
):
    capture, events = _screenshot_capture_fixture(tmp_path, modal_mode=modal_mode)

    with pytest.raises(RuntimeError, match=message):
        capture("base-error", tmp_path)

    assert "window_show" not in events
    assert "window_grab" not in events


def test_screenshot_capture_keeps_no_modal_window_behavior(tmp_path):
    capture, events = _screenshot_capture_fixture(tmp_path)

    result = capture("ordinary-stage", tmp_path)

    assert result["modal"] is None
    assert events.index("window_show") < events.index("process_events")
    assert events.index("process_events") < events.index("window_grab")
    assert "viewport_save" in events


def test_offline_home_opt_in_requires_exact_value_and_separate_output_case(
    tmp_path, monkeypatch
):
    exact_opt_in = _extract_helper("_exact_env_opt_in", {"os": os})
    validate_output = _extract_helper("_validate_output_case_path", {"Path": Path})
    source_case = tmp_path / "source.dentocase"
    source_case.write_bytes(b"source")
    output_case = tmp_path / "offline-home.dentocase"

    monkeypatch.delenv("DENTOBOT_HEADED_OFFLINE_HOME_SETUP", raising=False)
    assert exact_opt_in("DENTOBOT_HEADED_OFFLINE_HOME_SETUP") is False
    monkeypatch.setenv("DENTOBOT_HEADED_OFFLINE_HOME_SETUP", "0")
    assert exact_opt_in("DENTOBOT_HEADED_OFFLINE_HOME_SETUP") is False
    monkeypatch.setenv("DENTOBOT_HEADED_OFFLINE_HOME_SETUP", "1")
    assert exact_opt_in("DENTOBOT_HEADED_OFFLINE_HOME_SETUP") is True
    monkeypatch.setenv("DENTOBOT_HEADED_OFFLINE_HOME_SETUP", "true")
    with pytest.raises(RuntimeError, match="must be exactly '1', '0', or unset"):
        exact_opt_in("DENTOBOT_HEADED_OFFLINE_HOME_SETUP")

    assert validate_output(str(output_case), source_case) == output_case
    with pytest.raises(ValueError, match="absolute path"):
        validate_output("offline-home.dentocase", source_case)
    with pytest.raises(ValueError, match="distinct from the source"):
        validate_output(str(source_case), source_case)
    output_case.write_bytes(b"existing")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        validate_output(str(output_case), source_case)


def test_before_planning_recovery_is_required_when_home_or_workspace_is_stale():
    ensure = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_ensure_current_home_workspace_task"
    )
    phase_gate = next(
        node for node in ast.walk(ensure)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and ast.unparse(node.test) == "phase in {'before_save', 'before_planning'}"
    )
    recovery_assignment = next(
        node for node in phase_gate.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "needs_recovery"
            for target in node.targets
        )
    )
    phase_expression = compile(
        ast.Expression(phase_gate.test), str(RUNNER), "eval"
    )
    recovery_expression = compile(
        ast.Expression(recovery_assignment.value), str(RUNNER), "eval"
    )

    for phase in ("before_save", "before_planning"):
        assert eval(phase_expression, {"phase": phase}) is True
    for home_current, workspace_current, expected in (
        (True, True, False),
        (False, True, True),
        (True, False, True),
        (False, False, True),
    ):
        actual = eval(
            recovery_expression,
            {
                "needs_recovery": False,
                "home_current": home_current,
                "workspace_current": workspace_current,
            },
        )
        assert actual is expected


def test_workspace_and_preentry_clicks_fail_fast_on_modal():
    source = ast.unparse(TREE)
    ensure = next(node for node in TREE.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "_ensure_current_home_workspace_task")
    assert not any(
        isinstance(node, ast.Call)
        and ast.unparse(node.func) == "widget.ui.generateRobotWorkspaceButton.click"
        for node in ast.walk(ensure)
    )
    assert any(_is_guarded_click(node, "panel.checkPreEntryIKButton") for node in ast.walk(TREE))
    assert "panel.checkPreEntryIKButton.click()" not in source
    assert "click_guard=lambda button, name: _modal_guarded_click(" in source
    assert "except UnexpectedModalError" in source


def _base_offset_helpers(environ=None):
    fake_os = SimpleNamespace(environ=dict(environ or {}))
    extra = {"BASE_OFFSET_ENV": "DENTOBOT_HEADED_BASE_OFFSET_RAS_MM", "BASE_OFFSET_MAX_MM": 42.5,
             "os": fake_os}
    return (
        _extract_helper("_parse_base_offset", extra),
        _extract_helper("_validate_base_offset_opt_in", extra),
        _extract_helper("_translated_matrix", extra),
    )


def test_base_offset_parser_accepts_bounded_finite_triplet_only():
    parse, _validate, _translate = _base_offset_helpers()
    assert parse(None) is None and parse("  ") is None
    assert parse("-0.4, -2.5, 12.9") == (-0.4, -2.5, 12.9)
    for bad in ("1,2", "1,2,x", "nan,0,0", "inf,0,0", "31,31,0"):
        with pytest.raises(RuntimeError):
            parse(bad)


def test_base_offset_requires_full_chain_gates_and_blocks_saving_modes():
    _parse, validate, _translate = _base_offset_helpers()
    validate(None, full_chain=False, allow_jog=False, allow_base_home_accept=False)
    with pytest.raises(RuntimeError, match="requires"):
        validate((0.0, 0.0, 1.0), full_chain=True, allow_jog=False, allow_base_home_accept=True)
    validate((0.0, 0.0, 1.0), full_chain=True, allow_jog=True, allow_base_home_accept=True)
    _parse, validate, _translate = _base_offset_helpers({"DENTOBOT_HEADED_OUTPUT_CASE": "/x.dentocase"})
    with pytest.raises(RuntimeError, match="cannot be combined"):
        validate((0.0, 0.0, 1.0), full_chain=True, allow_jog=True, allow_base_home_accept=True)
    _parse, validate, _translate = _base_offset_helpers({"DENTOBOT_HEADED_STOP_AFTER_WORKSPACE": "1"})
    with pytest.raises(RuntimeError, match="cannot be combined"):
        validate((0.0, 0.0, 1.0), full_chain=True, allow_jog=True, allow_base_home_accept=True)


def test_translated_matrix_changes_translation_only():
    _parse, _validate, translate = _base_offset_helpers()
    matrix = [float(i) for i in range(16)]
    shifted = translate(matrix, (1.0, -2.0, 3.0))
    assert [shifted[i] for i in (3, 7, 11)] == [4.0, 5.0, 14.0]
    assert all(shifted[i] == matrix[i] for i in range(16) if i not in (3, 7, 11))
    assert matrix[3] == 3.0  # input unchanged


def test_base_offset_is_staged_through_production_review_before_accept_owner():
    source = ast.unparse(TREE)
    stage = source.index("facade.stageManualBaseReview(expected_accept_matrix)")
    owner = source.index("base_acceptance_owner = widget.ui.lockRobotBaseMountButton")
    accept_click = source.index("base_acceptance_owner, 'base-acceptance-accept'")
    assert stage < owner < accept_click
    assert "base_after_details.get('acceptedMatrixWorldRasMm'), expected_accept_matrix" in source
    assert "report['base_offset_applied'] = base_offset is not None" in source


def test_identity_viewport_candidate_is_cancelled_only_when_equal_to_accepted_base():
    source = ast.unparse(TREE)
    unlock = source.index("Disposable-scene Base unlock did not complete.")
    guard = source.index("_same_matrix(pre_details.get('candidateMatrixWorldRasMm'), pre_details.get('acceptedMatrixWorldRasMm'))")
    cancel = source.index("report['identity_viewport_candidate_cancelled'] = True")
    review = source.index("base_before = _base_review(facade)")
    assert unlock < guard < cancel < review
    assert "pre_details.get('identityStatus') == 'current'" in source


def test_complete_cycles_run_preentry_ik_first_and_optional_base_diagnosis():
    branch = SOURCE[SOURCE.index('active_check = "complete_cycles"'):]
    branch = branch[:branch.index("run_complete_cycles(")]
    assert '"complete-cycle-preentry-ik"' in branch  # r13: probe needs a current PreEntry session
    assert 'os.environ.get("DENTOBOT_HEADED_DIAGNOSE_BASE", "") == "1"' in SOURCE
    assert "def _run_base_diagnosis(" in SOURCE and '"base_diagnosis",' in SOURCE
    assert "click_guard=lambda button, name: _modal_guarded_click(" in SOURCE


def test_session_mode_checkpoints_after_scene_ack_and_serves_commands():
    hook = SOURCE.index('if _exact_env_opt_in("DENTOBOT_HEADED_SESSION"):')
    assert hook < SOURCE.index('active_check = "profile_migration_recovery_after_scene_ack"', hook)
    assert "_serve_command_session(" in SOURCE and "run_session(namespace, session_dir, _process_events)" in SOURCE
    assert '"panel_callbacks_rebound": rebind_callbacks(panel._callbacks, widget)' in SOURCE
    assert '"Testing/step6_session_driver.py",' in SOURCE
