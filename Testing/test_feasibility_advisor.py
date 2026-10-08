import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "DENTOWorkflow" / "Resources" / "Python"))

from dentobot_workflow import feasibility_advisor as fa  # noqa: E402

BASE = {fa.PLANNING_ATTEMPTS: 1, fa.BASE_YAW_DEG: 0.0, fa.MOUTH_OPENING_MM: 40.0}


def test_ladders_are_smallest_change_first_and_bounded():
    limits = fa.Limits(max_yaw_deg=10.0, max_opening_mm=45.0)
    assert fa.yaw_ladder(limits) == [5.0, -5.0, 10.0, -10.0]
    assert fa.opening_coarse_ladder(40.0, limits) == [42.0, 44.0, 45.0]


def test_bisect_finds_minimum_at_resolution():
    calls = []

    def passes(value):
        calls.append(value)
        return value >= 40.5

    assert fa.bisect_minimum(passes, 40.0, 42.0, 0.5) == 40.5
    assert len(calls) <= 3


def test_opening_search_reproduces_s6_live_01_minimum():
    """4 Oct evidence: 40.06 fails, >= 40.5 passes (with +10 deg yaw)."""
    seen = []

    def evaluate(change):
        seen.append(change)
        return change.get(fa.MOUTH_OPENING_MM, 0) >= 40.5

    found = fa.search_single_lever(fa.MOUTH_OPENING_MM, evaluate, BASE, fa.Limits())
    assert found == {fa.MOUTH_OPENING_MM: 40.5}
    assert seen[0] == {fa.MOUTH_OPENING_MM: 42.0}


def test_search_pairs_opening_with_yaw_when_no_single_lever_passes():
    def evaluate(change):
        return change.get(fa.BASE_YAW_DEG) == 10.0 and change.get(fa.MOUTH_OPENING_MM, 0) >= 40.5

    found = fa.search("anatomy_neighbour", evaluate, BASE, fa.Limits())
    assert found == [{fa.BASE_YAW_DEG: 10.0, fa.MOUTH_OPENING_MM: 40.5}]


def test_search_ranks_by_cost_and_attempts_need_increase():
    def evaluate(change):
        return change.get(fa.PLANNING_ATTEMPTS, 0) >= 10 or abs(change.get(fa.BASE_YAW_DEG, 0)) >= 5

    at_default = {**BASE, fa.PLANNING_ATTEMPTS: 5}
    found = fa.search("narrow_passage", evaluate, at_default, fa.Limits())
    assert found[0] == {fa.PLANNING_ATTEMPTS: 10}
    assert {fa.BASE_YAW_DEG: 5.0} in found
    assert fa.search_single_lever(fa.PLANNING_ATTEMPTS, lambda c: True, {fa.PLANNING_ATTEMPTS: 10}, fa.Limits()) is None


def test_report_lists_candidates_and_never_applies():
    candidate = fa.Candidate({fa.MOUTH_OPENING_MM: 40.5}, cost=0.5, result="pass", detail="3/3 | P1")
    text = fa.report_markdown(BASE, "anatomy_neighbour", [candidate], [{fa.MOUTH_OPENING_MM: 40.5}], fa.Limits())
    assert "Nothing was applied" in text and "3/3 / P1" in text and "cost 0.5" in text
    empty = fa.report_markdown(BASE, "template", [], [], fa.Limits())
    assert "No change within the limits passed" in empty


def test_corridor_margin_is_tried_before_yaw_for_narrow_passages():
    tried = []

    def evaluate(change):
        tried.append(change)
        return change.get(fa.CORRIDOR_MARGIN_SAMPLES, 0) >= 2

    found = fa.search("narrow_passage", evaluate, BASE, fa.Limits())
    assert found[0] == {fa.CORRIDOR_MARGIN_SAMPLES: 2}
    assert tried.index({fa.CORRIDOR_MARGIN_SAMPLES: 1}) < tried.index({fa.BASE_YAW_DEG: 5.0})
    assert fa.Limits().max_opening_mm == 46.0


def test_policy_below_default_is_reset_first_and_stops_the_search():
    tried = []

    def evaluate(change):
        tried.append(change)
        return change.get(fa.PLANNING_ATTEMPTS) == 5

    assert fa.search("narrow_passage", evaluate, BASE, fa.Limits()) == [{fa.PLANNING_ATTEMPTS: 5}]
    assert tried == [{fa.PLANNING_ATTEMPTS: 5}]
    at_default = {**BASE, fa.PLANNING_ATTEMPTS: 5}
    tried.clear()
    fa.search("template", lambda c: tried.append(c) or False, at_default, fa.Limits(max_yaw_deg=5.0))
    assert {fa.PLANNING_ATTEMPTS: 5} not in tried


def test_base_yaw_is_always_the_last_lever():
    """Operator 2026-10-06: Base yaw is one of the last preferred adjustments."""
    for levers in fa.CAUSE_CLASS_SEARCH.values():
        if fa.BASE_YAW_DEG in levers:
            assert levers[-1] == fa.BASE_YAW_DEG


# ---- ordered search (operator 2026-10-06, S6-MULTI-TARGET-01 FDI34) ----------
LIP = "dentobot_mouth_barrier_lip_slab"
TOOTH24 = "dentobot_tooth_2.25.175780709850645902717525655867293195040_bc0fd9c2"
SPINDLE = "pneumatic_spindle-Copy"


def _seed(**overrides):
    seed = {"candidate_index": 0, "seed_provenance": "task_home", "solver_success": True,
            "termination_reason": "converged", "collision_check_status": "clear", "collision_pairs": [],
            "best_joint_positions_si": {"link-1_Revolute-1": 0.1}, "static_state_validity_status": "Valid",
            "static_state_validity_message": "MoveIt accepted the explicit static joint state",
            "endpoint_check_status": "Passed", "failure_classification": "preentry_ik_endpoint_checks_pass_route_not_run",
            "position_residual_mm": 0.0015, "drilling_axis_residual_deg": 4.5e-6}
    seed.update(overrides)
    return seed


def _preentry(status, seeds, success=True):
    return {"success": success, "code": "preentry_ik_diagnostic_complete", "message": "m",
            "details": {"diagnosticStatus": status}, "seeds": seeds}


def test_ordered_candidates_follow_the_agreed_order_and_lateral_first():
    base = fa.baseline_state(40.06)
    stages = []
    for stage, state in fa.ordered_candidates(base):
        if not stages or stages[-1] != stage:
            stages.append(stage)
        assert not fa.state_violations(state, 40.06), (stage, state)
    assert stages == list(fa.STAGE_ORDER)
    candidates = list(fa.ordered_candidates(base))
    lateral = [s for st, s in candidates if st == "base_lateral"]
    assert [s[fa.BASE_U_MM] for s in lateral[:4]] == [5.0, -5.0, 10.0, -10.0]
    assert all(s[fa.BASE_V_MM] == 0 and s[fa.BASE_DEPTH_MM] == 0 and s[fa.BASE_YAW_DEG] == 0 for s in lateral)
    vertical = [s for st, s in candidates if st == "base_lateral_vertical"]
    assert abs(vertical[0][fa.BASE_V_MM]) == 10.0 and vertical[0][fa.BASE_U_MM] == 0.0
    assert all(s[fa.BASE_V_MM] != 0 for s in vertical)
    yaw_first = next(i for i, (st, _s) in enumerate(candidates) if st == "base_yaw")
    assert all(st == "base_yaw" for st, _s in candidates[yaw_first:])


def test_opening_ladder_uses_the_absolute_half_mm_grid_and_never_exceeds_the_maximum():
    limits = fa.OrderedLimits()
    ladder = fa.opening_ladder(40.06, limits)
    assert ladder[:4] == [40.5, 41.0, 41.5, 42.0] and ladder[-1] == 46.0
    assert fa.opening_ladder(46.0, limits) == []
    base = fa.baseline_state(40.06)
    opening = [s for st, s in fa.ordered_candidates(base) if st == "opening"]
    first_42 = [s for s in opening if s[fa.MOUTH_OPENING_MM] == 42.0]
    assert [s[fa.BASE_U_MM] for s in first_42[:5]] == [0.0, 5.0, -5.0, 10.0, -10.0]
    assert all(s[fa.BASE_V_MM] == 0 for s in first_42[:13]) and first_42[13][fa.BASE_V_MM] != 0


def test_the_42mm_u15_confirmation_state_is_valid_and_on_the_agreed_path():
    base = fa.baseline_state(40.06)
    state = {**base, fa.MOUTH_OPENING_MM: 42.0, fa.BASE_U_MM: 15.0}
    assert fa.state_violations(state, 40.06) == []
    assert ("opening", state) in list(fa.ordered_candidates(base))
    assert fa.state_delta(state, base) == {fa.MOUTH_OPENING_MM: 42.0, fa.BASE_U_MM: 15.0}
    assert state[fa.LIP_MARGIN_MM] == 2.0 and state[fa.LIP_SLAB_MM] == 8.0 and state[fa.PORTAL_ENLARGE_MM] == 5.0
    assert state[fa.PLANNING_ATTEMPTS] == 5 and state[fa.PLANNING_TIME_SEC] == 5.0
    assert state[fa.SPINDLE_TEMPLATE_ALLOWANCE] is False


def test_unapproved_states_are_refused_never_searched():
    base = fa.baseline_state(40.06)
    assert fa.state_violations({**base, fa.BARRIER_EDGE_MODE: "off"}, 40.06)
    assert fa.state_violations({**base, fa.LIP_SLAB_MM: 2.0}, 40.06)
    assert fa.state_violations({**base, fa.SPINDLE_TEMPLATE_ALLOWANCE: True}, 40.06)
    assert fa.state_violations({**base, fa.PLANNING_TIME_SEC: 10.0}, 40.06)
    assert fa.state_violations({**base, fa.CORRIDOR_MARGIN_SAMPLES: 1}, 40.06)
    assert fa.state_violations({**base, fa.MOUTH_OPENING_MM: 46.5}, 40.06)
    assert fa.state_violations({**base, fa.MOUTH_OPENING_MM: 41.25}, 40.06)
    for variant in fa.LIP_VARIANTS:
        assert not fa.state_violations({**base, **variant}, 40.06)


def test_captured_guard_margin_is_an_immutable_expectation_not_a_search_lever():
    base = {**fa.baseline_state(40.0), fa.CORRIDOR_MARGIN_SAMPLES: 3}
    assert fa.state_violations(base, 40.0)  # default expects the zero-margin state
    assert fa.state_violations(base, 40.0, expected_corridor_margin_samples=2)
    assert fa.state_violations(base, 40.0, expected_corridor_margin_samples=4)
    assert fa.state_violations(base, 40.0, expected_corridor_margin_samples=3) == []
    assert base[fa.CORRIDOR_MARGIN_SAMPLES] == 3


def test_preentry_classification_separates_collision_reach_and_setup():
    # 42.0 mm u+0 (recorded): converged, contacts only in the static-validity message.
    lip = _seed(static_state_validity_status="Invalid", endpoint_check_status="NotRun",
                failure_classification="static_state_invalid",
                static_state_validity_message=f"MoveIt rejected the explicit static joint state; contacts={LIP}<->{SPINDLE}")
    out = fa.classify_preentry(_preentry("NoEndpointPassed", [lip]))
    assert out["result"] == fa.ENDPOINT_COLLISION and out["pairs"] == [sorted([LIP, SPINDLE])]
    # 40.5 mm u+20 (recorded): 'position_axis_ik_failed' but terminated by a named collision.
    tooth = _seed(solver_success=False, termination_reason="colliding", collision_check_status="colliding",
                  collision_pairs=[[TOOTH24, SPINDLE]], static_state_validity_status="not_attempted",
                  failure_classification="position_axis_ik_failed", static_state_validity_message="")
    assert fa.classify_preentry(_preentry("NoEndpointPassed", [tooth]))["result"] == fa.ENDPOINT_COLLISION
    two = _seed(static_state_validity_status="Invalid",
                static_state_validity_message=f"rejected; contacts={LIP}<->{SPINDLE}, {TOOTH24}<->{SPINDLE}")
    assert len(fa.classify_preentry(_preentry("NoEndpointPassed", [two]))["pairs"]) == 2
    assert fa.classify_preentry(_preentry("EndpointChecksPassed", [_seed()]))["result"] == fa.PASSED
    no_ik = _seed(solver_success=False, termination_reason="no_solution", static_state_validity_status="not_attempted",
                  static_state_validity_message="", failure_classification="position_axis_ik_failed")
    assert fa.classify_preentry(_preentry("NoEndpointPassed", [no_ik]))["result"] == fa.UNREACHABLE
    refused = _preentry("", [], success=False)
    refused["message"] = "Task confirmation is missing or stale: base changed"
    assert fa.classify_preentry(refused)["result"] == fa.SETUP_ERROR
    assert fa.classify_preentry(_preentry("EndpointChecksPassed", []))["result"] == fa.SETUP_ERROR


def test_corridor_classification_keeps_the_1mm_minimum():
    blocked = {"success": False, "code": "approach_corridor_blocked",
               "message": f"axial corridor blocked 0.73 mm behind PreEntry: contacts={TOOTH24}<->{SPINDLE}",
               "details": {"corridor_mm": 0.73, "minimum_mm": 1.0, "validity_authoritative": True,
                           "blocked_message": f"contacts={TOOTH24}<->{SPINDLE}"}}
    out = fa.classify_corridor(blocked)
    assert out["result"] == fa.ROUTE_FAILURE and out["pairs"] == [sorted([TOOTH24, SPINDLE])]
    clear = {"success": True, "code": "approach_corridor_clear", "message": "",
             "details": {"corridor_mm": 1.71, "minimum_mm": 1.0, "validity_authoritative": True}}
    assert fa.classify_corridor(clear)["result"] == fa.PASSED
    relaxed = {**clear, "details": {**clear["details"], "minimum_mm": 0.5}}
    assert fa.classify_corridor(relaxed)["result"] == fa.SETUP_ERROR
    unverified = {**clear, "details": {**clear["details"], "validity_authoritative": False}}
    assert fa.classify_corridor(unverified)["result"] == fa.SETUP_ERROR
    refused = {"success": False, "code": "approach_corridor_check_failed", "message": "Run PreEntry IK", "details": {}}
    assert fa.classify_corridor(refused)["result"] == fa.SETUP_ERROR


def _rows(**status):
    order = ("scene_match", "stroke_reach", "preentry_endpoint", "p1_route", "p2_entry", "p3_drilling", "frame_match")
    return [{"check": c, "status": status.get(c, "PASS"), "detail": f"{c} detail", "blocking_pairs": []} for c in order]


def test_diagnose_acceptance_requires_p1_to_p3_not_just_the_endpoint():
    # 41.5 mm u+15 (recorded): PreEntry PASS, P1 FAIL on the corridor, P2/P3 NOT RUN.
    failed = fa.classify_diagnosis({"status": "FAIL", "rows": _rows(p1_route="FAIL", p2_entry="NOT RUN",
                                                                  p3_drilling="NOT RUN")})
    assert failed["result"] == fa.ROUTE_FAILURE and failed["failed_check"] == "p1_route"
    incomplete = fa.classify_diagnosis({"status": "NOT RUN", "rows": _rows(p2_entry="NOT RUN", p3_drilling="NOT RUN")})
    assert incomplete["result"] == fa.SETUP_ERROR
    assert fa.classify_diagnosis({"status": "WARNING", "rows": _rows(p3_drilling="WARNING")})["result"] == fa.WARNING_RESULT
    assert fa.classify_diagnosis({"status": "PASS", "rows": _rows()})["result"] == fa.PASSED
    assert fa.classify_diagnosis({"status": "FAIL", "rows": _rows(scene_match="FAIL")})["result"] == fa.SETUP_ERROR
    assert fa.classify_diagnosis({"status": "FAIL", "rows": _rows(stroke_reach="FAIL")})["result"] == fa.UNREACHABLE


def _observed(**overrides):
    observed = {"ros_connected": True, "base_locked": True, "base_delta_mm": 0.0, "home_gap": "",
                "home_delta_si": 0.0, "task_confirmation_issues": [], "scene_state": "matched",
                "collision_audit_issues": [], "barrier_issues": [], "policy_issues": [], "geometry_issues": [],
                "spindle_template_allowance": False}
    observed.update(overrides)
    return observed


def test_invalid_home_stale_confirmation_and_scene_mismatch_stop_the_candidate():
    assert fa.precondition_issues(_observed()) == []
    assert fa.precondition_issues(_observed(scene_state="resynced")) == []
    assert fa.precondition_issues(_observed(home_gap="Task Home is not validated in this session"))
    assert fa.precondition_issues(_observed(home_delta_si=0.01))
    assert fa.precondition_issues(_observed(home_delta_si=None))
    assert fa.precondition_issues(_observed(task_confirmation_issues=["base changed"]))
    assert fa.precondition_issues(_observed(scene_state="mismatch"))
    assert fa.precondition_issues(_observed(scene_state="not_checked"))
    assert fa.precondition_issues(_observed(base_delta_mm=0.5))
    assert fa.precondition_issues(_observed(spindle_template_allowance=True))
    assert fa.precondition_issues(_observed(geometry_issues=["rebuild inconsistent"]))


def test_candidate_record_stops_at_the_first_failure_and_endpoint_pass_is_not_success():
    base = fa.baseline_state(40.06)
    state = {**base, fa.MOUTH_OPENING_MM: 42.0, fa.BASE_U_MM: 15.0}
    ok = {"result": fa.PASSED, "reason": "ok"}
    blocked = {"result": fa.ROUTE_FAILURE, "reason": "corridor 0.73 mm", "pairs": [[TOOTH24, SPINDLE]]}
    record = fa.candidate_record("opening", state, base, {"prerequisites": ok, "stroke_reach": ok, "preentry": ok,
                                                          "corridor": blocked}, identity={"a": 1})
    assert record["result"] == fa.ROUTE_FAILURE and record["failed_step"] == "corridor"
    endpoint_only = fa.candidate_record("opening", state, base, {"prerequisites": ok, "stroke_reach": ok,
                                                                 "preentry": ok}, identity={"a": 1})
    assert endpoint_only["result"] == fa.SETUP_ERROR and endpoint_only["failed_step"] == "corridor"
    full = fa.candidate_record("opening", state, base, {name: ok for name in fa.EVALUATION_STEPS}, identity={"a": 1})
    assert full["result"] == fa.PASSED and full["change"] == {fa.MOUTH_OPENING_MM: 42.0, fa.BASE_U_MM: 15.0}
    warn = fa.candidate_record("opening", state, base, {**{n: ok for n in fa.EVALUATION_STEPS},
                                                        "diagnose": {"result": fa.WARNING_RESULT, "reason": "drill"}},
                               identity={"a": 1})
    assert warn["result"] == fa.WARNING_RESULT


def test_checkpoints_reuse_only_identity_matched_complete_records(tmp_path):
    base = fa.baseline_state(40.06)
    state = {**base, fa.MOUTH_OPENING_MM: 42.0, fa.BASE_U_MM: 15.0}
    store = fa.CheckpointStore(tmp_path / "checkpoints.jsonl")
    ok = {"result": fa.PASSED, "reason": "ok"}
    blocked = {"result": fa.ROUTE_FAILURE, "reason": "corridor"}
    identity = {"template": "abc", "home": "h1"}
    record = fa.candidate_record("opening", state, base, {"prerequisites": ok, "stroke_reach": ok, "preentry": ok,
                                                          "corridor": blocked}, identity=identity)
    store.append(record)
    assert store.lookup(state, identity)["result"] == fa.ROUTE_FAILURE
    assert store.lookup(state, {**identity, "home": "h2"}) is None
    assert store.lookup({**state, fa.BASE_U_MM: 20.0}, identity) is None
    setup = fa.candidate_record("opening", {**state, fa.BASE_U_MM: 10.0}, base,
                                {"prerequisites": {"result": fa.SETUP_ERROR, "reason": "home"}}, identity=identity)
    store.append(setup)
    assert store.lookup({**state, fa.BASE_U_MM: 10.0}, identity) is None  # setup errors are re-run
    (tmp_path / "v2.jsonl").write_text('{"label": "step4 42.0mm u+15", "result": "preentry_pass"}\n')
    assert fa.CheckpointStore(tmp_path / "v2.jsonl").lookup(state, identity) is None


def test_untested_states_are_reported_as_untested_never_failed():
    base = fa.baseline_state(40.06)
    state = {**base, fa.MOUTH_OPENING_MM: 42.0, fa.BASE_U_MM: 15.0}
    ok = {"result": fa.PASSED, "reason": "ok"}
    record = fa.candidate_record("opening", state, base, {"prerequisites": ok, "stroke_reach": ok, "preentry": ok,
                                                          "corridor": {"result": fa.ROUTE_FAILURE, "reason": "c"}},
                                 identity={"a": 1})
    text = fa.ordered_report_markdown(base, [record], extra_untested=[
        {"opening_mm": 41.0, "status": "untested — template build failed"}])
    assert "untested — template build failed" in text
    assert "base_lateral:" in text and "generated state(s) untested" in text
    assert "never a minimum opening or an optimal Base" in text
    summary = fa.untested_summary([record], base)
    assert summary["untested_per_stage"]["opening"] == len(
        [s for st, s in fa.ordered_candidates(base) if st == "opening"]) - 1


def test_rebuilt_branch_geometry_must_match_the_reference_in_the_jaw_frame():
    reference = {"trajectory_mm": [[0, 0, 0], [0, 0, 10]],
                 "template": {"bounds": [0, 10, 0, 10, 0, 5], "centroid": [5, 5, 2.5], "volume_mm3": 400.0}}
    same = {"trajectory_mm": [[0, 0, 0.004], [0, 0, 10]],
            "template": {"bounds": [0.1, 10, 0, 10, 0, 5], "centroid": [5.05, 5, 2.5], "volume_mm3": 404.0,
                         "surface_distance_p95_mm": 0.2, "surface_distance_max_mm": 0.6}}
    assert fa.compare_geometry(reference, same)["status"] == "PASS"
    moved = {**same, "trajectory_mm": [[0, 0, 0.5], [0, 0, 10]]}
    assert fa.compare_geometry(reference, moved)["status"] == "FAIL"
    islands = {**same, "template": {**same["template"], "surface_distance_p95_mm": 1.2}}
    assert fa.compare_geometry(reference, islands)["status"] == "FAIL"
    missing = {"trajectory_mm": same["trajectory_mm"], "template": {}}
    assert fa.compare_geometry(reference, missing)["status"] == "FAIL"


# ---- single lever registry (S6-ADVISOR-GUI-01) ----------------------------------
def test_registry_orders_ordered_stages_and_puts_yaw_last():
    ordered = sorted(fa.LEVER_REGISTRY.values(), key=lambda s: s.priority)
    stages = [s.stage for s in ordered if s.stage]
    assert tuple(stages) == fa.STAGE_ORDER
    assert fa.STAGE_ORDER == ("base_lateral", "base_lateral_vertical", "lip_variant", "opening", "base_depth", "base_yaw")
    assert fa.STAGE_ORDER[-1] == "base_yaw"
    assert max(s.priority for s in fa.LEVER_REGISTRY.values() if s.id != "drilling_depth") == fa.LEVER_REGISTRY[fa.BASE_YAW_DEG].priority
    # the order the generator actually yields follows the registry's stage order
    seen = []
    for stage, _state in fa.ordered_candidates(fa.baseline_state(40.0)):
        if not seen or seen[-1] != stage:
            seen.append(stage)
    assert seen == list(fa.STAGE_ORDER)


def test_registry_flags_clinically_sensitive_levers_and_owners():
    sensitive = {s.id for s in fa.LEVER_REGISTRY.values() if s.clinical_review}
    assert {"lip_variant", fa.MOUTH_OPENING_MM, fa.BASE_YAW_DEG, "drilling_depth"} <= sensitive
    assert fa.SENSITIVE_STAGES == ("lip_variant", "opening", "base_yaw")
    for engineering in ("base_lateral", "base_lateral_vertical", "base_depth", fa.PLANNING_ATTEMPTS,
                        fa.CORRIDOR_MARGIN_SAMPLES):
        assert not fa.LEVER_REGISTRY[engineering].clinical_review
    assert all(spec.owner for spec in fa.LEVER_REGISTRY.values())
    # depth truncation is a WARNING outcome, never an auto-searched lever
    assert not fa.LEVER_REGISTRY["drilling_depth"].in_ordered_search
    assert set(fa.STAGE_PROMPTS) == set(fa.SENSITIVE_STAGES)


def test_registry_bounds_match_the_ordered_limits():
    limits = fa.OrderedLimits()
    opening = fa.LEVER_REGISTRY[fa.MOUTH_OPENING_MM].bounds
    assert opening[fa.MOUTH_OPENING_MM][1] == limits.max_opening_mm == 46.0
    assert opening["step_mm"] == limits.opening_step_mm == 0.5
    assert fa.LEVER_REGISTRY[fa.BASE_YAW_DEG].bounds[fa.BASE_YAW_DEG] == (-limits.max_yaw_deg, limits.max_yaw_deg)
    assert fa.LEVER_REGISTRY["lip_variant"].bounds == fa.LIP_VARIANT_BOUNDS


def test_search_and_advisory_tables_reference_registered_levers_with_yaw_last():
    for cause, levers in fa.CAUSE_CLASS_SEARCH.items():
        assert all(lever in fa.LEVER_REGISTRY for lever in levers), cause
        priorities = [fa.LEVER_REGISTRY[lever].priority for lever in levers]
        assert priorities == sorted(priorities), cause
        assert levers[-1] == fa.BASE_YAW_DEG
    for cause, entries in fa.CAUSE_CLASS_ADVISORY.items():
        assert all(lever_id in fa.LEVER_REGISTRY for lever_id, _text in entries), cause
        if any(lever_id == fa.BASE_YAW_DEG for lever_id, _ in entries):
            assert entries[-1][0] == fa.BASE_YAW_DEG, cause


def test_diagnose_levers_come_from_the_registry():
    from dentobot_workflow import base_diagnosis as bd

    assert set(bd.CAUSE_CLASS_LEVERS) == set(fa.CAUSE_CLASS_ADVISORY)
    for cause in fa.CAUSE_CLASS_ADVISORY:
        assert bd.CAUSE_CLASS_LEVERS[cause] == fa.advisory_lever_texts(cause)
    assert bd.CAUSE_CLASS_LEVERS["barrier"] == (
        "Base translation", "Mouth opening", "Base yaw (±5° steps; last resort)")
