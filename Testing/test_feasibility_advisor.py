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
