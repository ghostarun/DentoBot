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


def test_pair_classification_names_obstacle_class_and_tool_part():
    canine = "dentobot_tooth_2.25.86807283465178072659419388615512220786_23e609d0"
    assert bd.classify_pair([canine, "pneumatic_spindle-Copy"]) == {
        "bodies": [canine, "pneumatic_spindle-Copy"],
        "cause_class": "anatomy_neighbour",
        "tool_part": "spindle_housing",
    }
    assert bd.classify_pair(["dentobot_mouth_barrier_lip_slab", "pneumatic_spindle-Copy"])["cause_class"] == "barrier"
    template = bd.classify_pair(["[Step 5C] DENTO Final Printable Template", "burr"])
    assert template["cause_class"] == "template" and template["tool_part"] == "burr"
    assert bd.classify_pair(["dentobot_target_tooth_2.25.1", "burr"])["cause_class"] == "target_tooth"
    assert bd.classify_pair("not a pair") == {}


def test_blocked_corridor_message_names_pair_class_and_levers():
    """S6-LIVE-01 2026-10-04: corridor blocked by the lower canine at 40 mm opening."""
    reason = (
        "Approach corridor unavailable (axial corridor blocked 0.00 mm behind PreEntry: MoveIt rejected "
        "the explicit static joint state; contacts=dentobot_tooth_2.25.868_23e609d0<->pneumatic_spindle-Copy); "
        "direct plan: The planner returned an empty trajectory."
    )
    rows = [
        bd.stroke_row({"reachable": True}),
        bd.preentry_row("EndpointChecksPassed"),
        bd.stage_row("P1", _stage("failed", reason=reason)),
    ]
    result = bd.summarize(rows)
    assert result["status"] == bd.FAIL and result["cause_class"] == "anatomy_neighbour"
    assert result["blocking_pairs"][0]["tool_part"] == "spindle_housing"
    assert result["suggested_levers"][0].startswith("Mouth opening")
    assert "Neighbouring anatomy" in result["verdict"] and "spindle housing" in result["verdict"]


def test_empty_plan_without_contacts_is_a_narrow_passage():
    reason = (
        "Approach corridor unavailable (Home to approach point failed: MoveIt joint-goal planning failed "
        "after 5 stable-scene attempt(s): The planner returned an empty trajectory. code=99999 (FAILURE))"
    )
    row = bd.stage_row("P1", _stage("failed", reason=reason))
    assert row["cause"] == "planner_corridor" and row["cause_class"] == "narrow_passage"
    result = bd.summarize([bd.stroke_row({"reachable": True}), bd.preentry_row("EndpointChecksPassed"), row])
    assert result["suggested_levers"][0] == "Planning attempts/time"


def test_route_pair_from_plan_and_reach_class_and_no_levers_on_pass():
    row = bd.stage_row("P1", _stage("failed", plan={"first_invalid_collision_pairs": [
        ["[Step 5C] DENTO Final Printable Template", "burr"]]}))
    assert row["cause"] == "route_collision" and row["cause_class"] == "template"
    assert bd.stroke_row({"reachable": False})["cause_class"] == "reach"
    passed = bd.summarize([bd.stroke_row({"reachable": True}), bd.preentry_row("EndpointChecksPassed"),
                           bd.stage_row("P1", _stage("passed")), bd.stage_row("P2", _stage("passed")),
                           bd.stage_row("P3", _stage("passed"))])
    assert passed["status"] == bd.PASS and passed["suggested_levers"] == [] and passed["cause_class"] == ""


def test_unknown_stage_names_guard_reason_and_truncation_warning_is_template_class():
    unknown = _stage("unknown", reason="Approach corridor: planned.")
    unknown["endpoint_evidence"]["phase_guard"] = {
        "status": "unknown", "named_pair": None,
        "reason": "Task guard rejected approach sequence 1: Command guard session does not match the active preview session.",
    }
    row = bd.stage_row("P1", unknown)
    assert row["cause_class"] == "unknown" and "Guard evidence unavailable: Task guard rejected" in row["detail"]
    truncated = bd.stage_row("P3", _stage("passed", plan={"drilling_truncation": {
        "blocking_pair": ["[Step 5C] DENTO Final Printable Template", "pneumatic_spindle-Copy"],
        "completed_depth_mm": 3.64, "requested_depth_mm": 8.25, "remaining_depth_mm": 4.61}}))
    assert truncated["status"] == bd.WARNING and truncated["cause_class"] == "template"
    assert truncated["blocking_pairs"][0]["tool_part"] == "spindle_housing"


def test_truncation_feedback_explains_why_and_what_to_change():
    """Operator 2026-10-05: shortened drilling is a success with a warning plus why/what-to-change."""
    truncation = {
        "blocking_pair": ["[Step 5C] DENTO Final Printable Template", "pneumatic_spindle-Copy"],
        "completed_depth_mm": 3.64, "requested_depth_mm": 8.25, "remaining_depth_mm": 4.61,
    }
    feedback = bd.truncation_feedback(truncation, effective_protrusion_mm=7.0)
    assert "spindle housing meets the final printable template after 3.64 mm" in feedback["why"]
    assert any("by at least 4.61 mm" in c for c in feedback["what_to_change"])
    assert any("7.00 → ≥ 11.61 mm" in c for c in feedback["what_to_change"])
    row = bd.stage_row("P3", _stage("passed", plan={"drilling_truncation": {**truncation, "feedback": feedback}}))
    assert row["status"] == bd.WARNING and "To drill further:" in row["detail"]


def test_moveit_scene_comparison_flags_missing_extra_and_moved_objects():
    """S6-LIVE-01 2026-10-04: MoveGroup held FDI31 19.4 mm away from Slicer's copy."""
    expected = [
        {"outgoing_collision_object_id": "tooth_31", "outgoing_bounds_base_link_mm": [0, 10, 0, 10, 0, 10]},
        {"outgoing_collision_object_id": "lip_slab", "outgoing_bounds_base_link_mm": [0, 1, 0, 1, 0, 1]},
    ]
    same = [{"id": "tooth_31", "bounds_mm": [0, 10, 0, 10, 0, 10.01]}, {"id": "lip_slab", "bounds_mm": [0, 1, 0, 1, 0, 1]}]
    ok = bd.compare_moveit_scene(expected, same)
    assert ok["matches"] and bd.scene_row(ok)["status"] == bd.PASS
    moved = [{"id": "tooth_31", "bounds_mm": [19.4, 29.4, 0, 10, 0, 10]}, {"id": "extra", "bounds_mm": [0, 1, 0, 1, 0, 1]}]
    bad = bd.compare_moveit_scene(expected, moved)
    assert not bad["matches"] and bad["missing"] == ["lip_slab"] and bad["extra"] == ["extra"]
    assert bad["differing"] == [("tooth_31", 19.4)] and "tooth_31 (19.4 mm)" in bad["summary"]
    row = bd.scene_row(bad)
    assert row["status"] == bd.FAIL and row["cause_class"] == "scene_mismatch"
    result = bd.summarize([row, bd.stroke_row({"reachable": True})])
    assert result["status"] == bd.FAIL and result["rows"][0]["check"] == "scene_match"
    assert [r["status"] for r in result["rows"][1:]] == [bd.NOT_RUN] * 5
    assert bd.scene_row(None, unavailable_reason="timeout")["status"] == bd.FAIL


def test_frame_comparison_flags_offsets_and_always_reports_with_priority():
    import math
    eye = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    moved = [[1, 0, 0, 0.02], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    c, s_ = math.cos(math.radians(0.02)), math.sin(math.radians(0.02))
    turned = [[c, -s_, 0, 0], [s_, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    ok = bd.compare_frame_poses({"home": (eye, eye)})
    assert ok["matches"] and bd.frame_row(ok)["status"] == bd.PASS
    bad = bd.compare_frame_poses({"home": (eye, eye), "preentry": (eye, moved), "entry": (eye, turned), "x": (eye, None)})
    assert not bad["matches"] and [r["status"] for r in bad["rows"]] == [bd.PASS, bd.FAIL, bd.FAIL, bd.FAIL]
    row = bd.frame_row(bad)
    assert row["cause_class"] == "frame_mismatch" and "preentry" in row["detail"]
    # frame row is reported even after a planning failure, and its FAIL wins the verdict
    result = bd.summarize([bd.stroke_row({"reachable": True}), bd.preentry_row("NoEndpointPassed"), row])
    assert result["rows"][-1]["check"] == "frame_match" and result["cause_class"] == "frame_mismatch"
    assert "Coordinate frames disagree" in result["verdict"]
    passed = bd.summarize([bd.stroke_row({"reachable": True}), bd.preentry_row("EndpointChecksPassed"),
                           bd.stage_row("P1", _stage("passed")), bd.stage_row("P2", _stage("passed")),
                           bd.stage_row("P3", _stage("passed")), bd.frame_row(ok)])
    assert passed["status"] == bd.PASS and passed["rows"][-1]["status"] == bd.PASS


def test_frame_angle_is_not_inflated_by_column_norm_drift():
    eye = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    drift = [[1 - 4e-10, 0, 0, 0], [0, 1 - 4e-10, 0, 0], [0, 0, 1 - 4e-10, 0], [0, 0, 0, 1]]
    row = bd.compare_frame_poses({"home": (eye, drift)})["rows"][0]
    assert row["axis_deg"] < 1e-6
