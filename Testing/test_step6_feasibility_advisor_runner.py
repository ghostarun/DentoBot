"""Host checks of the ordered advisor runner paths that need no Slicer runtime."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "DENTOWorkflow" / "Resources" / "Python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dentobot_workflow import feasibility_advisor as fa  # noqa: E402
import step6_feasibility_advisor_runner as runner_module  # noqa: E402


def _runner(tmp_path, loaded=None, gap=40.0, scratch_root=None):
    node = SimpleNamespace(step6CaseJawTargetGapMm=gap)
    widget = SimpleNamespace(_loadedCaseBundlePath=loaded)
    namespace = {"widget": widget, "panel": None, "facade": None, "logic": None, "parameter_node": node}
    return runner_module.OrderedAdvisorRunner(
        namespace, tmp_path / "run", saved_base_matrix=np.eye(4), target_fdi="34",
        branch_id="guide-f8a3caff373bddb4f157", baseline_opening_mm=gap, scratch_root=scratch_root)


def test_unapproved_state_is_a_setup_error_without_touching_the_scene(tmp_path, monkeypatch):
    runner = _runner(tmp_path)
    monkeypatch.setattr(runner, "apply", lambda state: pytest.fail("apply must not run"))
    record = runner.evaluate("lip_variant", {**runner.baseline, fa.BARRIER_EDGE_MODE: "off"})
    assert record["result"] == fa.SETUP_ERROR and record["failed_step"] == "prerequisites"
    assert "barrier never disabled" in record["reason"]
    assert (Path(record["evidence_dir"]) / "candidate.json").exists()
    assert not runner.store.records()  # setup errors carry no identity and are never checkpointed


def test_rebuild_refuses_anything_but_a_scratch_copy_in_the_run_directory(tmp_path):
    with pytest.raises(RuntimeError, match="isolated scratch"):
        _runner(tmp_path, loaded="/workspace/data/shared/sample.dentocase").require_scratch()
    with pytest.raises(RuntimeError):
        _runner(tmp_path, loaded=None).require_scratch()
    inside = tmp_path / "run" / "scratch" / "case.dentocase"
    assert _runner(tmp_path, loaded=str(inside)).require_scratch() == str(inside)
    # Confirmation package layout: case in <run>/scratch, results in <run>/confirmation-...
    package_case = tmp_path / "scratch" / "fdi34-scratch.dentocase"
    with pytest.raises(RuntimeError):
        _runner(tmp_path, loaded=str(package_case)).require_scratch()
    assert _runner(tmp_path, loaded=str(package_case), scratch_root=tmp_path).require_scratch() == str(package_case)


def test_failed_template_build_leaves_the_opening_untested(tmp_path, monkeypatch):
    runner = _runner(tmp_path)

    def failed_build(opening):
        runner.geometry[opening] = {"opening_mm": opening, "status": "build_failed", "error": "8 islands"}
        return runner.geometry[opening]

    monkeypatch.setattr(runner, "rebuild_branch", failed_build)
    monkeypatch.setattr(runner, "apply", lambda state: pytest.fail("apply must not run"))
    record = runner.evaluate("opening", {**runner.baseline, fa.MOUTH_OPENING_MM: 41.0})
    assert record["result"] == fa.UNTESTED and record["failed_step"] == "rebuild"
    assert record["reason"].startswith("untested — template build failed")
    report = (tmp_path / "run" / "advisor-ordered-report.md").read_text()
    assert "untested — template build failed" in report


def test_confirm_evaluates_exactly_one_candidate(tmp_path, monkeypatch):
    runner = _runner(tmp_path)
    calls = []

    def evaluate(stage, state):
        calls.append(state)
        record = fa.candidate_record(stage, state, runner.baseline,
                                     {"prerequisites": {"result": fa.SETUP_ERROR, "reason": "home"}}, identity={})
        runner.records.append(record)
        return record

    monkeypatch.setattr(runner, "evaluate", evaluate)
    state = {**runner.baseline, fa.MOUTH_OPENING_MM: 42.0, fa.BASE_U_MM: 15.0}
    record = runner.confirm("opening", state, extra_untested=[{"opening_mm": 41.0, "status": "untested"}])
    assert len(calls) == 1 and record["result"] == fa.SETUP_ERROR
    progress = json.loads((tmp_path / "run" / "progress.json").read_text())
    assert progress["text"].startswith("done: setup_error")


def test_missing_saved_home_stops_before_any_rebuild(tmp_path):
    runner = _runner(tmp_path)
    runner.saved_home_source = "none saved"
    with pytest.raises(RuntimeError, match="No saved Task Home"):
        runner.require_saved_home()
    named = runner_module.OrderedAdvisorRunner(
        runner.ns, tmp_path / "run2", saved_base_matrix=np.eye(4), target_fdi="34", branch_id="b",
        baseline_opening_mm=40.0, home_si={"link-1_Revolute-1": 0.0})
    assert named.require_saved_home() == {"link-1_Revolute-1": 0.0} and named.saved_home_source == "operator"


def test_near_preentry_home_candidates_keep_orientation_and_retract_slider_4(tmp_path):
    seed = {"link-1_Revolute-1": 0.1998, "link-2_Slider-2": 0.0303, "link-3_Revolute-3": -0.1637,
            "link-4_Slider-4": 0.0609, "link-5_Revolute-5": 0.4931}
    runner = runner_module.OrderedAdvisorRunner(
        {"widget": None, "panel": None, "facade": None, "logic": None, "parameter_node": None},
        tmp_path / "run", saved_base_matrix=np.eye(4), target_fdi="34", branch_id="b",
        baseline_opening_mm=40.0, home_seed_si=seed, home_retract_ladder_mm=(15.0, 40.0, 70.0))
    candidates = runner.near_preentry_home_candidates()
    assert [r for r, _q in candidates] == [15.0, 40.0]  # 70 mm would leave the slider range
    for retract, q in candidates:
        assert abs(q["link-4_Slider-4"] - (0.0609 - retract / 1000.0)) < 1e-9
        assert all(q[k] == seed[k] for k in seed if k != "link-4_Slider-4")
