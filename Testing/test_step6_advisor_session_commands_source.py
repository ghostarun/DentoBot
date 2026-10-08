"""Static safety checks for the S6-ADVISOR-GUI-01 B-verification session commands and the cancel helper.

The commands only run inside a live approved Slicer session, so these host tests pin what they may and may not do:
they use production controls and guards, never approve a sensitive stage, never connect/jog, and the helper sends
at most one click. They do not prove runtime behaviour."""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTING = ROOT / "Testing"
COMMANDS = TESTING / "step6_session_commands"
sys.path.insert(0, str(TESTING))

import advisor_cancel_helper as helper  # noqa: E402

NAMES = ("advisor_precheck", "advisor_baseline", "advisor_consented_trials")
FORBIDDEN_CALLS = {"saveCurrentTaskHome", "saveTaskHome", "setBasePose", "lockBase", "applyJointPositions", "jog", "exit",
                   "removeNode", "unlockRobotBaseMountButton", "acceptManualTaskHomeReview", "stageManualTaskHomeReview",
                   "stageManualBaseReview", "acceptManualBaseReview", "connect", "disconnect"}


def _calls(name):
    tree = ast.parse((COMMANDS / f"{name}.py").read_text(encoding="utf-8"))
    return tree, [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def test_every_command_parses_and_calls_no_state_changing_owner_directly():
    for name in NAMES:
        tree, calls = _calls(name)
        def is_qt_signal_connect(c):  # QTimer.connect("timeout()", slot) is a Qt signal hookup, not the ROS owner
            return (isinstance(c.func, ast.Attribute) and c.func.attr == "connect" and c.args
                    and isinstance(c.args[0], ast.Constant) and c.args[0].value == "timeout()")

        called = {c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", "")
                  for c in calls if not is_qt_signal_connect(c)}
        # owners appear only as string names given to the guard (refuse/count), never as direct calls
        assert called.isdisjoint(FORBIDDEN_CALLS), (name, called & FORBIDDEN_CALLS)
        assert "result" in {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}


def test_the_precheck_is_read_only_and_stops_instead_of_repairing():
    source = (COMMANDS / "advisor_precheck.py").read_text(encoding="utf-8")
    assert ".click()" not in source and "OwnerGuard" not in source
    assert "raise RuntimeError" in source and "nothing was changed" in source


def test_the_dialog_commands_never_approve_a_stage_and_keep_consent_explicit():
    for name in ("advisor_baseline", "advisor_consented_trials"):
        source = (COMMANDS / f"{name}.py").read_text(encoding="utf-8")
        assert "DENTOBOTStep6AdvisorGateSkipButton" in source and "GateEvaluateButton" not in source
        assert "advisor-UNEXPECTED-GATE" in source and "unexpected sensitive-stage review gate" in source  # retained FAIL
        assert 'state["consentBox"].checked is False' in source  # default OFF is asserted before anything else
        assert 'state["closeButton"].click()' not in source  # the dialog stays open for the operator's verdict
        assert "-FAILURE" in source and "first_failure" in source  # the first causal failure is captured and recorded
        assert "refuse=(" in source and '"connect"' in source and '"disconnect"' in source
    baseline = (COMMANDS / "advisor_baseline.py").read_text(encoding="utf-8")
    assert 'consentBox"].checked = True' not in baseline  # run A never ticks the consent
    trials = (COMMANDS / "advisor_consented_trials.py").read_text(encoding="utf-8")
    assert trials.count('state["consentBox"].checked = True') == 1 and "fallback_inprocess_cancel" in trials
    assert 'state["startButton"].click()' not in trials and "found" in trials  # continues from Run A's open FOUND dialog
    assert "NO independent" in trials  # a fallback in-process Cancel fails the measurement instead of replacing it
    assert '"createOrUpdateStep6CaseJawOpening"' in trials and '"setStep6MouthBarrierTuning"' in trials  # refused


def test_cancel_helper_fires_only_on_the_armed_executing_substep_and_sends_at_most_one_click():
    arm = {"target_step": "diagnose · p1_route", "min_candidate": 2}
    open_row = {"kind": "step_start", "step": "diagnose · p1_route", "candidate": 2, "mono_ns": 5}
    assert helper.last_open_step([open_row])["mono_ns"] == 5 and helper.should_fire(open_row, arm)
    assert helper.last_open_step([open_row, {"kind": "step_end", "mono_ns": 9}]) is None  # step finished: not blocking
    assert not helper.should_fire({**open_row, "candidate": 1}, arm)  # the baseline is never cancelled
    assert not helper.should_fire({**open_row, "step": "preentry"}, arm)
    assert not helper.should_fire(None, arm)
    source = (TESTING / "advisor_cancel_helper.py").read_text(encoding="utf-8")
    assert source.count('"xdotool", "click"') == 1 and "Slicer" not in source.split('"""')[2]


def test_helper_ignores_a_half_written_last_timeline_line(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps({"kind": "step_start", "step": "x", "mono_ns": 1}) + "\n{\"kind\": \"st", encoding="utf-8")
    assert len(helper.read_rows(path)) == 1
