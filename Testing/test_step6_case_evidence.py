import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import step6_case_evidence as ev  # noqa: E402


def _summary(rows, status="WARNING"):
    return {
        "label": "case",
        "captured_utc": "t",
        "conditions": {
            "target_gap_mm": 40.5, "opening_status": "40.52 mm", "allow_spindle_guide_contact": False,
            "policy": {"planner_id": "RRTConnectkConfigDefault"}, "base_origin_ras_mm": [1, 2, 3],
            "base_rotation_row0": [0, 1, 0], "template_state": "WARNING", "collision_audit": "abcdef0123456789",
        },
        "diagnosis": {"status": status, "cause_class": "template", "verdict": "v", "rows": rows,
                      "suggested_levers": []},
        "corridor_mm": ev.corridor_mm_from_rows(rows),
        "drilling": ev.drilling_from_rows(rows),
        "blocking_pairs": [],
        "images": ["diagnosis.png", "view-anterior.png"],
    }


def test_parses_corridor_and_drilling_and_renders_markdown():
    rows = [
        {"title": "3. Route", "status": "PASS", "cause_class": "",
         "detail": "Approach corridor: free-space Home -> approach point 1.71 mm out along the drill axis"},
        {"title": "5. Drilling", "status": "WARNING", "cause_class": "template",
         "detail": "Drilling shortened: 3.64 of 8.25 mm reached; 4.61 mm not completed (A | B)."},
    ]
    summary = _summary(rows)
    assert summary["corridor_mm"] == 1.71
    assert summary["drilling"] == {"completed_mm": 3.64, "requested_mm": 8.25, "remaining_mm": 4.61}
    text = ev.summary_markdown(summary)
    assert "| 5. Drilling | WARNING | template |" in text and "(A / B)" in text
    assert "![view-anterior.png](view-anterior.png)" in text and "OFF" in text


def test_missing_values_are_none():
    assert ev.corridor_mm_from_rows([{"detail": "no corridor"}]) is None
    assert ev.drilling_from_rows([]) is None


def test_pose_states_pick_passed_stage_ends_and_failed_first_invalid():
    chain = {"stages": {"P1": {"end": {"j": 1.0}}, "P3": {"end": {"j": 3.0}}}}
    outcomes = {
        "P1": {"diagnostic_status": "passed"},
        "P2": {"diagnostic_status": "failed",
               "endpoint_evidence": {"first_invalid_requested_state": {"status": "failed", "state": {"j": 2.5}}}},
    }
    assert ev.pose_states(chain, outcomes) == {
        "preentry": {"j": 1.0}, "drilling-end": {"j": 3.0}, "first-invalid-p2": {"j": 2.5}}
    assert ev.pose_states(None, None) == {}
