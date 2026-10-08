"""Host tests for the S6-ADVISOR-GUI-01 B-verification probe helpers (fakes only; no Slicer/ROS)."""

import json
import sys
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Testing"))

import step6_advisor_probe as probe  # noqa: E402

HOME = {"j1": 0.1, "j2": 0.2}


def fakes(**overrides):
    home = SimpleNamespace(joint_names=list(HOME), joint_positions_si=list(HOME.values()), revision=3,
                           validated_at_utc="2026-10-08T00:00:03Z")
    node = SimpleNamespace(robotBaseTransform=object(), robotBaseMountLocked=True, step6CaseJawTargetGapMm=40.0,
                           step6TrajectoryRegistryJson=json.dumps({"selected_branch_id": "b1"}),
                           step6AllowSpindleGuideContact=False, step6MouthBarrierEdgeMode="gum_line",
                           step6MouthBarrierLipMarginMm=2.0, step6MouthBarrierLipSlabMm=8.0,
                           step6MouthBarrierPortalEnlargeMm=5.0, step6TaskHomeJson='{"r":3}', step6BasePlacementRevision=7)
    logic = SimpleNamespace(taskHomeRecord=lambda n: home, isRos2MotionControlActive=lambda t: True,
                            confirmedTaskRecord=lambda n: SimpleNamespace(snapshot_fingerprint="task-1"),
                            collisionSceneAuditRecord=lambda n: SimpleNamespace(audit_fingerprint="audit-1"))
    facade = SimpleNamespace(taskHomeJointIdentity=lambda: {"accepted": dict(HOME), "monitored": dict(HOME), "displayed": dict(HOME)},
                             jointPlanningPolicy=lambda: {"planner_id": "RRT", "planning_attempts": 5, "planning_time_sec": 5.0},
                             approachCorridorMarginSamples=lambda: 0, taskHomeValidationGap=lambda n: "")
    return logic, facade, node, home


def snap(**kw):
    logic, facade, node, _ = fakes()
    return probe.invariant_snapshot(logic, facade, node, matrix_reader=lambda: [[1, 0, 0, 5]] * 4, **kw)


def test_snapshot_records_the_invariants_and_changes_are_classified():
    before = snap(label="before")
    assert before["home_joints_si"] == HOME and before["home_revision"] == 3 and before["barrier_tuning"] == [2.0, 8.0, 5.0]
    assert before["ros_active"] and before["home_validation_gap"] == "" and before["opening_mm"] == 40.0
    after = {**before, "label": "after", "home_revision": 5, "confirmed_task_fingerprint": "task-2", "opening_mm": 41.0}
    diff = probe.snapshot_diff(before, after, allow=probe.EXPECTED_AUTHORITY_DRIFT)
    assert diff["unexpected"] == ["opening_mm"] and set(diff["allowed"]) == {"home_revision", "confirmed_task_fingerprint"}
    assert probe.snapshot_diff(before, {**before, "label": "x"})["changed"] == []


def test_joint_equality_flags_each_source_and_an_absent_home():
    ok = snap()
    assert probe.joints_equal_saved(ok) == []
    drift = {**ok, "joints_si": {**ok["joints_si"], "monitored": {"j1": 0.1 + 1e-9, "j2": 0.2}}}
    assert probe.joints_equal_saved(drift) == ["monitored differs from the saved Home"]
    assert probe.joints_equal_saved({**ok, "joints_si": {"accepted": None}}) == ["accepted unavailable", "monitored unavailable", "displayed unavailable"]
    assert probe.joints_equal_saved({**ok, "home_joints_si": None}) == ["no saved Task Home"]


def test_owner_guard_refuses_and_counts_without_swallowing_and_restores():
    calls = []

    class Facade:
        def stageManualBaseReview(self, x):
            calls.append(("stage", x))
            return "staged"

        def connect(self):
            calls.append(("connect",))

    facade = Facade()
    guard = probe.OwnerGuard(facade, refuse=("connect",), count=("stageManualBaseReview",))
    with pytest.raises(RuntimeError, match="not permitted"):
        facade.connect()
    assert facade.stageManualBaseReview(1) == "staged" and calls == [("stage", 1)]
    assert guard.report() == {"connect": {"refused": 1}, "stageManualBaseReview": {"called": 1}} and guard.refused_total() == 1
    guard.restore()
    facade.connect()
    assert calls[-1] == ("connect",)
    assert "connect" not in vars(facade) and "stageManualBaseReview" not in vars(facade)  # no shadow left on the instance


def test_timeline_is_flushed_per_line_and_instrumentation_only_observes(tmp_path):
    timeline = probe.Timeline(tmp_path / "t" / "timeline.jsonl")
    session = SimpleNamespace(phase="evaluating", progress=lambda: {"phase": "evaluating", "stage": "baseline", "step": "diagnose · p1_route",
                                                                    "index": 0, "label": "baseline"},
                              step=lambda: SimpleNamespace(kind="step", message="m"))
    cancelled = []
    widget = SimpleNamespace(_advisorOnCancel=lambda: cancelled.append(1) or "cancelled")
    original_step = session.step
    bound_cancel_slot = widget._advisorOnCancel  # Qt captured this before instrumentation was installed
    previous_profile = sys.getprofile()
    undo = probe.instrument_session(session, widget, timeline)
    assert session.step().kind == "step" and bound_cancel_slot() == "cancelled" and cancelled == [1]
    rows = [json.loads(line) for line in (tmp_path / "t" / "timeline.jsonl").read_text().splitlines()]  # readable while open
    assert [r["kind"] for r in rows] == ["step_start", "step_end", "step_event", "cancel_handler_entry"]
    assert rows[0]["step"] == "diagnose · p1_route" and all(rows[i]["mono_ns"] <= rows[i + 1]["mono_ns"] for i in range(3))
    undo()
    assert sys.getprofile() is previous_profile
    assert session.step is original_step and widget._advisorOnCancel() == "cancelled"
    timeline.close()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), "invalid"])
def test_invalid_joint_values_cannot_pass_probe_equality(value):
    before = snap()
    before["joints_si"]["monitored"]["j1"] = value
    assert probe.joints_equal_saved(before) == ["monitored unavailable (invalid joint value)"]


def test_a_partial_guard_installation_is_undone_when_an_owner_is_missing():
    target = SimpleNamespace(connect=lambda: "original")
    original = target.connect
    with pytest.raises(AttributeError):
        probe.OwnerGuard(target, refuse=("connect", "absent"))
    assert target.connect is original and target.connect() == "original"


def test_failure_evidence_keeps_the_cause_and_counts_when_after_snapshot_is_unavailable(tmp_path):
    target = SimpleNamespace(connect=lambda: None)
    guard = probe.OwnerGuard(target, refuse=("connect",))
    with pytest.raises(RuntimeError):
        target.connect()
    path = tmp_path / "failure.json"
    result = probe.retain_command_failure(None, None, None, steps={"restore_issues": ["unknown"]},
                                         before={"home_revision": 1}, guards={"facade": guard}, path=path,
                                         failure=RuntimeError("first causal error"))
    assert result["first_failure"] == "RuntimeError: first causal error"
    assert result["guards"]["facade"]["connect"]["refused"] == 1
    assert result["after"] is None and "after_snapshot_error" in result
    assert json.loads(path.read_text()) == result
    guard.restore()


def test_cancel_latency_separates_the_independent_input_from_the_handler_and_the_covering_step():
    s = 1_000_000_000
    rows = [
        {"kind": "step_start", "mono_ns": 10 * s, "phase": "evaluating", "step": "diagnose · p1_route", "candidate": 3},
        {"kind": "step_end", "mono_ns": 40 * s},
        {"kind": "cancel_handler_entry", "mono_ns": 40 * s + 5_000_000},
        {"kind": "step_start", "mono_ns": 41 * s, "phase": "restoring", "step": "", "candidate": 3},
    ]
    helper = {"t_send_before_ns": 12 * s, "t_send_after_ns": 12 * s + 3_000_000}
    result = probe.cancel_latency(rows, helper)
    assert result["covering_step"]["step"] == "diagnose · p1_route" and result["covering_step"]["end_ns"] == 40 * s
    assert result["delivery_delay_ms"] == pytest.approx((40 * s + 5_000_000 - 12 * s - 3_000_000) / 1e6)  # ~28 s: delivery, not intent
    assert result["cancel_to_restore_start_ms"] == pytest.approx((41 * s - 40 * s - 5_000_000) / 1e6)
    # no handler yet (the click is still queued): no latency is invented
    assert "delivery_delay_ms" not in probe.cancel_latency(rows[:2], helper)


def test_cancel_handler_during_the_send_window_reports_bounds_and_missing_handler_is_incomplete():
    helper = {"t_send_before_ns": 100_000_000, "t_send_after_ns": 120_000_000}
    rows = [{"kind": "step_start", "mono_ns": 90_000_000, "phase": "evaluating", "step": "diagnose · p1_route"},
            {"kind": "step_end", "mono_ns": 104_000_000},
            {"kind": "cancel_handler_entry", "mono_ns": 105_000_000},
            {"kind": "step_start", "mono_ns": 125_000_000, "phase": "restoring"},
            {"kind": "step_event", "mono_ns": 150_000_000, "event": "done"}]
    measured = probe.cancel_latency(rows, helper)
    assert measured["delivery_delay_bounds_ms"] == [0.0, 5.0]
    assert measured["handler_during_send"] and "delivery_delay_ms" not in measured
    assert measured["measurement_complete"] and measured["send_window_ms"] == 20.0
    missing = probe.cancel_latency([r for r in rows if r["kind"] != "cancel_handler_entry"], helper)
    assert not missing["measurement_complete"] and missing["handler_ns"] is None
    assert not probe.cancel_latency(rows[:-1], helper)["measurement_complete"]
