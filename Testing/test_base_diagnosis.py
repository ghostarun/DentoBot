import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "DENTOWorkflow" / "Resources" / "Python"))

from dentobot_workflow import base_diagnosis as bd  # noqa: E402


def _stage(status, *, reason="r", pair=None, plan=None, gate=None):
    return {
        "diagnostic_status": status,
        "reason": reason,
        "endpoint_evidence": {
            "plan": dict(plan or {}),
            "phase_guard": {"named_pair": pair},
            "mouth_portal_gate": gate,
        },
    }


def test_base_placement_stops_at_first_check():
    rows = [bd.stroke_row({"reachable": False, "first_failed_station": "PreEntry"})]
    result = bd.summarize(rows)
    assert result["status"] == bd.FAIL and result["cause"] == "base_placement"
    assert "PreEntry" in result["verdict"] and "Find Reachable Base" in result["verdict"]
    assert [row["status"] for row in result["rows"]] == [bd.FAIL] + [bd.NOT_RUN] * 4


def test_preentry_collision_versus_solver():
    collided = bd.preentry_row(
        "NoEndpointPassed",
        [{"failure_classification": "collision_induced_ik_failure", "collision_pairs": [["spindle", "jaw"]]}],
    )
    assert collided["cause"] == "endpoint_collision" and "spindle ↔ jaw" in collided["detail"]
    solver = bd.preentry_row("NoEndpointPassed", [{"failure_classification": "iteration_limit"}])
    assert solver["cause"] == "solver"
    assert bd.preentry_row("EndpointChecksPassed")["status"] == bd.PASS


def test_p1_mouth_barrier_route_collision_and_planner():
    gate = bd.stage_row("P1", _stage("failed", gate={"status": "failed"}))
    assert gate["cause"] == "mouth_barrier"
    collision = bd.stage_row("P1", _stage("failed", pair=["link_3", "upper jaw"]))
    assert collision["cause"] == "route_collision" and "link_3 ↔ upper jaw" in collision["detail"]
    planner = bd.stage_row("P1", _stage("failed", reason="no plan found"))
    assert planner["cause"] == "planner_corridor"
    skipped_gate = bd.stage_row("P1", _stage("passed", gate={"status": "skipped"}))
    assert skipped_gate["status"] == bd.PASS


def test_p2_pair_from_plan_when_guard_has_none():
    row = bd.stage_row("P2", _stage("failed", plan={"first_invalid_collision_pairs": [["burr", "tooth_12"]]}))
    assert row["cause"] == "entry_collision" and "burr ↔ tooth_12" in row["detail"]


def test_truncated_drilling_is_a_warning_and_overall_warning():
    truncation = {
        "completed_depth_mm": 4.0, "requested_depth_mm": 9.741, "remaining_depth_mm": 5.741,
        "blocking_pair": ["[Step 5C] DENTO Final Printable Template", "pneumatic_spindle-Copy"],
    }
    rows = [
        bd.stroke_row({"reachable": True}),
        bd.preentry_row("EndpointChecksPassed"),
        bd.stage_row("P1", _stage("passed")),
        bd.stage_row("P2", _stage("passed")),
        bd.stage_row("P3", _stage("passed", plan={"drilling_truncation": truncation})),
    ]
    result = bd.summarize(rows)
    assert result["status"] == bd.WARNING and result["cause"] == "tool_geometry"
    assert "4.00 of 9.74 mm" in result["verdict"] and "5.74 mm not completed" in result["verdict"]
    assert "pneumatic_spindle-Copy" in result["verdict"]


def test_all_pass_and_incomplete():
    rows = [
        bd.stroke_row({"reachable": True}),
        bd.preentry_row("EndpointChecksPassed"),
        bd.stage_row("P1", _stage("passed")),
        bd.stage_row("P2", _stage("passed")),
        bd.stage_row("P3", _stage("passed")),
    ]
    assert bd.summarize(rows)["status"] == bd.PASS
    partial = bd.summarize(rows[:2])
    assert partial["status"] == bd.NOT_RUN
    assert [row["status"] for row in partial["rows"]][2:] == [bd.NOT_RUN] * 3


def test_failure_after_pass_marks_later_checks_not_run():
    rows = [
        bd.stroke_row({"reachable": True}),
        bd.preentry_row("EndpointChecksPassed"),
        bd.stage_row("P1", _stage("passed")),
        bd.stage_row("P2", _stage("failed", pair=["spindle", "lip"])),
    ]
    result = bd.summarize(rows)
    assert result["cause"] == "entry_collision"
    assert [row["status"] for row in result["rows"]] == [bd.PASS, bd.PASS, bd.PASS, bd.FAIL, bd.NOT_RUN]
