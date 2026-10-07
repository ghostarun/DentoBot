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
