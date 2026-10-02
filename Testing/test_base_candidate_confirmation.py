import Testing.run_step6_base_candidate_confirmation as confirm


def _report(base="PASS", chain="FAIL", reason="", records=(), sessions=None):
    return {"items": {
        "base_acceptance_trial": {"status": base, "reason": "base broke"},
        "full_chain_interruption": {"status": chain, "reason": reason, "probe_evidence": {
            "preentry_diagnostic_session": {"candidate_records": list(records)},
            "diagnostic_sessions": sessions or {},
        }},
    }}


def test_classification_separates_placement_collision_and_planner():
    assert confirm.classify(_report(base="FAIL"))[0] == "base_acceptance_failed"
    assert confirm.classify(_report(chain="PASS"))[0] == "full_chain_pass"
    unreachable = "P1 was not reached: PreEntry IK produced no collision-checked endpoint candidate."
    assert confirm.classify(_report(reason=unreachable,
                                    records=[{"termination_reason": "iteration_limit"}]))[0] == "preentry_ik_unreachable"
    assert confirm.classify(_report(reason=unreachable,
                                    records=[{"collision_check_status": "colliding"}]))[0] == "preentry_collision"
    planner = _report(reason="P1 did not configure ...", sessions={
        "P1": {"stage_outcomes": [{"status": "Failed", "reason": "empty trajectory"}]}})
    assert confirm.classify(planner) == ("planner_failed:P1", "empty trajectory")


def test_distinct_candidates_skip_near_duplicates():
    ranked = [{"u_mm": 0.0, "v_mm": -14.0}, {"u_mm": 1.0, "v_mm": -14.0},
              {"u_mm": -5.0, "v_mm": -14.0}, {"u_mm": 0.0, "v_mm": -20.0}]
    picks = confirm.distinct_candidates(ranked, 3, 4.0)
    assert [(p["u_mm"], p["v_mm"]) for p in picks] == [(0.0, -14.0), (-5.0, -14.0), (0.0, -20.0)]


def test_overall_verdicts():
    assert confirm.overall([{"classification": "full_chain_pass"},
                            {"classification": "planner_failed:P1"}]).startswith("placement_resolved")
    assert confirm.overall([{"classification": "planner_failed:P1"}] * 3).startswith("planner_fault_likely")
    assert confirm.overall([{"classification": "preentry_collision"}] * 2).startswith("collision_blocker")


def test_straight_path_evidence_confirms_planner_or_path_collision():
    base = {"P1": {"stage_outcomes": [{"status": "Failed", "reason": "empty trajectory"}]}}
    clear = _report(reason="P1 ...", sessions=base)
    clear["items"]["full_chain_interruption"]["probe_evidence"]["p1_straight_path_checks"] = [
        {"code": "straight_path_clear"}, {"code": "straight_path_clear"}]
    assert confirm.classify(clear)[0] == "planner_fault_confirmed:P1"
    blocked = _report(reason="P1 ...", sessions=base)
    blocked["items"]["full_chain_interruption"]["probe_evidence"]["p1_straight_path_checks"] = [
        {"code": "straight_path_blocked"}]
    assert confirm.classify(blocked)[0] == "p1_path_collision"
    assert confirm.overall([{"classification": "planner_fault_confirmed:P1"}] * 2).startswith(
        "planner_fault_confirmed")
