"""Per-branch Step 6 working configuration (S6-MULTI-JAW-STALE-01): pure checks + wiring."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(PY))

from dentobot_workflow import step6_working_config as wc  # noqa: E402

BASE = [[1, 0, 0, 10.0], [0, 1, 0, 20.0], [0, 0, 1, 30.0], [0, 0, 0, 1]]
HOME = {"link-1_Revolute-1": 0.1, "link-2_Slider-2": 0.02}


def _record(**config):
    return {"branch_id": "guide-a", "branch_foundation_fingerprint": "F",
            "config": {"mouth_opening_mm": 42.0, "base_world_mm": BASE, "task_home_si": HOME,
                       "planner_id": "RRTConnectkConfigDefault", "planning_attempts": 5,
                       "planning_time_sec": 5.0, **config}}


def test_round_trip_is_canonical_and_validated():
    text = wc.dumps(_record())
    record = wc.loads(text)
    assert record["schema"] == wc.SCHEMA and record["config"]["mouth_opening_mm"] == 42.0
    assert wc.dumps(record) == text
    assert wc.loads("") is None
    for bad in ({"mouth_opening_mm": -1}, {"base_world_mm": [[1, 0], [0, 1]]},
                {"planning_attempts": 0}, {"mouth_opening_mm": float("nan")}):
        with pytest.raises(ValueError):
            wc.normalize(_record(**bad))


def test_differences_name_only_what_must_be_reapplied():
    stored = _record()
    assert wc.differences(stored, _record()) == []
    moved = [row[:] for row in BASE]
    moved[0][3] += 15.0
    current = _record(mouth_opening_mm=40.0, base_world_mm=moved, task_home_si=None, planning_attempts=1)
    assert wc.differences(stored, current) == ["mouth_opening_mm", "base_world_mm", "task_home_si",
                                               "planning_attempts"]
    # A record without a planner keeps the current planner.
    assert "planner_id" not in wc.differences(_record(planner_id=""), _record(planner_id="RRTstar"))


def test_binding_refuses_another_branch_or_foundation():
    record = _record()
    assert wc.binding_issue(record, "guide-a", "F") == ""
    assert "another PreparedBranch" in wc.binding_issue(record, "guide-b", "F")
    assert "another Case Foundation" in wc.binding_issue(record, "guide-a", "G")


def test_research_store_entries_convert_with_their_source_recorded():
    entry = {"branch_id": "guide-a", "status": "accepted 10/10", "config": _record()["config"],
             "diagnostics": {"status": "PASS"}, "evidence_dir": "/runs/x"}
    record = wc.from_research_entry(entry, "F")
    assert record["source"] == "imported from research store"
    assert record["branch_foundation_fingerprint"] == "F" and record["status"] == "accepted 10/10"


def _source(name):
    return (PY / name).read_text(encoding="utf-8")


def test_restore_never_moves_the_robot_and_save_is_branch_scoped():
    widget = _source("dentobot_workflow/widget_step6_branch_config.py")
    restore = widget[widget.index("def onRestoreStep6WorkingConfiguration"):]
    restore = restore[:restore.index("\n    def ", 10)]
    for forbidden in ("reviewTaskHomeButton", "acceptTaskHomeButton", "_onStep6ReviewManualTaskHome",
                      "_onStep6AcceptManualTaskHomeReview", "planApproachPhase", "facade.connect(",
                      "_onShellConnectRobot"):
        assert forbidden not in restore, forbidden
    assert "manualJogJointControls" in restore  # Task Home is only staged
    assert "self._step6WorkingConfigurationRestoreSucceeded = False" in restore
    assert "self._step6WorkingConfigurationRestoreSucceeded = True" in restore
    logic = _source("dentobot_workflow/logic_case_bundle.py")
    store = logic[logic.index("def storeStep6WorkingConfiguration"):]
    store = store[:store.index("\n    def ", 10)]
    assert 'eligibility["reason"] != "VALID"' in store


def test_panel_wiring_and_owners():
    panel = _source("DENTORobotSimulationPanel.py")
    assert '"save_branch_config": (1, 3)' in panel and '"restore_branch_config": 1' in panel
    assert 'self._invoke("save_branch_config")' in panel and 'self._invoke("restore_branch_config")' in panel
    shell = _source("dentobot_workflow/widget_robot_shell.py")
    assert '"save_branch_config": self.onSaveStep6WorkingConfiguration' in shell
    assert '"restore_branch_config": self.onRestoreStep6WorkingConfiguration' in shell
    assert "self._offerStep6WorkingConfigurationRestore()" in _source("dentobot_workflow/widget_step6_branch_config.py")


# --- optional approved lip/barrier tuning (S6-ADVISOR-GUI-01, contract C-LIP) ---------------------------
VARIANT = {"lip_margin_mm": 0.0, "lip_slab_mm": 4.0, "portal_enlarge_mm": 10.0}


def test_absent_barrier_tuning_means_the_production_defaults_and_old_records_stay_valid():
    record = wc.normalize(_record())
    assert record["config"]["barrier_tuning"] == {"lip_margin_mm": 2.0, "lip_slab_mm": 8.0, "portal_enlarge_mm": 5.0}
    assert wc.dumps(wc.loads(wc.dumps(_record()))) == wc.dumps(_record())  # canonical and stable
    assert wc.differences(_record(), _record(barrier_tuning=record["config"]["barrier_tuning"])) == []


def test_only_exactly_approved_tuning_values_are_stored_or_loaded():
    stored = wc.normalize(_record(barrier_tuning=VARIANT))
    assert stored["config"]["barrier_tuning"] == VARIANT
    assert wc.loads(wc.dumps(stored))["config"]["barrier_tuning"] == VARIANT
    for bad in ({**VARIANT, "lip_margin_mm": 1.0}, {**VARIANT, "lip_slab_mm": 6.0}, {**VARIANT, "portal_enlarge_mm": 7.5},
                {"lip_margin_mm": 0.0, "lip_slab_mm": 4.0}, {**VARIANT, "extra": 1}, "variant", [0.0, 4.0, 10.0]):
        with pytest.raises(ValueError):
            wc.normalize(_record(barrier_tuning=bad))
    with pytest.raises(ValueError):
        wc.loads(wc.dumps(stored).replace('"lip_slab_mm":4.0', '"lip_slab_mm":6.0'))  # a hand-edited stored value fails closed


def test_barrier_tuning_difference_is_named_so_restore_reapplies_it():
    assert wc.differences(_record(barrier_tuning=VARIANT), _record()) == ["barrier_tuning"]
    assert wc.differences(_record(), _record(barrier_tuning=VARIANT)) == ["barrier_tuning"]  # a live variant is reset to the saved default


def test_capture_restore_and_summary_use_the_production_owner_only():
    capture = _source("dentobot_workflow/logic_case_bundle.py")
    capture = capture[capture.index("def captureStep6WorkingConfiguration"):]
    capture = capture[:capture.index("\n    def ", 10)]
    assert '"barrier_tuning": self.step6MouthBarrierTuning(parameterNode)' in capture
    widget = _source("dentobot_workflow/widget_step6_branch_config.py")
    restore = widget[widget.index("def onRestoreStep6WorkingConfiguration"):]
    restore = restore[:restore.index("\n    def ", 10)]
    assert 'if "barrier_tuning" in diffs:' in restore
    assert 'self.logic.setStep6MouthBarrierTuning(self._parameterNode, **config["barrier_tuning"])' in restore
    assert "setattr(" not in restore and "step6MouthBarrierLip" not in restore  # never writes the node fields itself
    assert "_barrierTuningSummary(config)" in widget and "synchronize the planning scene" in restore
