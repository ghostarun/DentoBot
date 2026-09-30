"""Source gates for the explicitly bounded headed Step 6 runner."""

import ast
from collections.abc import Mapping, Sequence
import hashlib
import importlib
import math
import os
from pathlib import Path
import re

import pytest


RUNNER = Path(__file__).with_name("run_dentobot_step6_headed_review.py")
SOURCE = RUNNER.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
JOINT_NAMES = ("J1", "J2", "J3", "J4", "J5")


def test_manual_workbench_uses_visible_step6_substep():
    shell = (RUNNER.parent.parent / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot_shell.py").read_text(encoding="utf-8")
    assert "3: (" in shell and "self._robotSimulationPanel.manualJogGroup," in shell
    assert "_configureRobotSimulationShellSubstep(5)" not in SOURCE
    assert SOURCE.count("_configureRobotSimulationShellSubstep(3)") >= 3


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
        "re": re,
    }
    namespace.update(extra_globals or {})
    module = ast.Module(body=[helper], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(RUNNER), "exec"), namespace)
    return namespace[name]


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


def _button_clicks(tree, button_name):
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "click"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == button_name
    ]


def test_headed_motion_requires_exact_opt_in_and_native_preflight():
    run = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    assert 'DENTOBOT_HEADED_ALLOW_JOG' in SOURCE
    assert "DENTOBOT_HEADED_NATIVE_SOURCE_SHA256" in SOURCE
    assert "DENTOBOT_HEADED_NATIVE_BINARY_SHA256" in SOURCE
    assert "DENTOBOT_HEADED_NATIVE_PACKAGE_PREFIX" in SOURCE
    assert "if (not allow_jog and not draft_only and not invalid_draft_review) or native is None:" in SOURCE
    assert "get_package_prefix" in SOURCE
    assert 're.fullmatch(r"[0-9a-fA-F]{64}", value)' in SOURCE
    assert 'source_hash != expected_source or binary_hash != expected_binary' in SOURCE
    assert "shared_install_prefix" in SOURCE
    assert "EXPECTED_NATIVE_SOURCE_SHA256" not in SOURCE
    assert "EXPECTED_NATIVE_BINARY_SHA256" not in SOURCE
    assert re.search(r"['\"][0-9a-fA-F]{64}['\"]", SOURCE) is None


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
    with pytest.raises(RuntimeError, match="must be exactly 'renovation' or 'integration'"):
        profile()


def test_runner_sends_at_most_one_guarded_jog_and_no_direct_route_or_preview_calls():
    calls = _calls(TREE)
    assert len(_button_clicks(TREE, "guardedManualJogButton")) == 1
    assert len(_button_clicks(TREE, "lockRobotBaseMountButton")) == 0
    assert SOURCE.count("_guard_click(widget, panel, target)") == 1
    assert calls.count("acceptManualBaseReview") == 0
    assert calls.count("acceptManualTaskHomeReview") == 0
    assert calls.count("planApproach") == 0
    assert calls.count("planDrilling") == 0
    assert calls.count("previewApproach") == 0
    assert calls.count("previewDrilling") == 0
    assert calls.count("reconcileManualRobotJog") == 0
    assert '"base_acceptance_attempted": False' in SOURCE


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
        "draft_state_control_visible",
        "native_version_preflight",
        "simulation_ros_connect_and_scene_readback",
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
    assert "base_acceptance_owner.click()" not in default_path
    assert "task_home_accept_owner.click()" not in default_path
    assert "base_acceptance_owner.click()" in acceptance_path
    assert "task_home_accept_owner.click()" in acceptance_path


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
        "base_acceptance_owner.click()",
        "_same_matrix(base_acceptance_stage_details.get('candidateMatrixWorldRasMm'), base_matrix)",
        "_same_matrix(base_after_details.get('acceptedMatrixWorldRasMm'), base_matrix)",
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
    assert "except" not in acceptance


def test_checklist_records_three_verdicts_and_no_case_save():
    assert '"PASS"' in SOURCE
    assert '"FAIL"' in SOURCE
    assert '"NOT_RUN"' in SOURCE
    assert '"saved_case": False' in SOURCE
    assert '"hardware_execution": False' in SOURCE
    assert '"route_authority": "none"' in SOURCE
    assert '"planner_calls": 0' in SOURCE
    assert '"preview_started": False' in SOURCE


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
    robot = "widget.ui.loadRobotModelButton"
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
