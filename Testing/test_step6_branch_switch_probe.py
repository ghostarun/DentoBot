"""Host checks for the read-only per-branch probe (S6-MULTI-JAW-STALE-01). No Slicer or ROS process."""

import ast
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(PY))
sys.path.insert(0, str(ROOT / "Testing"))

from DENTOStep6State import empty_trajectory_registry, parse_trajectory_registry  # noqa: E402
from dentobot_workflow import step6_working_config as wc  # noqa: E402
import step6_branch_switch_probe as probe  # noqa: E402

PROBE = ROOT / "Testing" / "step6_branch_switch_probe.py"
BASE = [[1.0, 0.0, 0.0, -97.889], [0.0, 1.0, 0.0, 13.212], [0.0, 0.0, 1.0, 187.347], [0.0, 0.0, 0.0, 1.0]]
FOUNDATION = "foundation-a"
MUTATING = {
    "syncDentoCaseTrajectoryRegistry", "onRestoreStep6WorkingConfiguration", "onImportStep6PlanningContext",
    "onSaveStep6WorkingConfiguration", "_onShellConnectRobot", "_onShellDisconnectRobot", "connect",
    "disconnect", "setValue", "click", "SetAttribute", "SetMatrixTransformToParent",
    "SetAndObserveTransformNodeID", "storeStep6WorkingConfiguration", "importResearchStep6WorkingConfigurations",
    "setJointPlanningPolicy", "createOrUpdateStep6CaseJawOpening", "stageManualBaseReview",
    "acceptManualBaseReview", "cancelManualBaseReview", "setBasePose", "lockBase", "unlockBase",
    "setRobotBaseMountLocked", "setStep6MouthBarrierTuning", "clearTransientState", "importStep6PlanningContext",
    "activateDentoCasePreparedBranch", "setattr",
}


def _config(opening=40.0, planner="RRTConnectkConfigDefault", home=None):
    return {
        "mouth_opening_mm": opening,
        "base_world_mm": BASE,
        "task_home_si": home,
        "planner_id": planner,
        "planning_attempts": 5,
        "planning_time_sec": 5.0,
        "corridor_margin_samples": 0,
        "allow_spindle_guide_contact": False,
    }


def _branch(branch_id, target, state="Current", reason=""):
    return {
        "branch_id": branch_id,
        "target_id": target,
        "state": state,
        "stale_reason": reason,
        "pairing_intent": "Single",
        "branch_foundation_fingerprint": FOUNDATION,
        "template_node_id": "vtkMRMLModelNode-" + branch_id,
        "trajectory_ids": ["traj-" + branch_id],
        "primary_trajectory_id": "traj-" + branch_id,
    }


def _tooth(tooth, branch_id, trajectory_id):
    """One tooth whose first slot carries one prepared branch (the shape parse_trajectory_registry checks)."""

    target = "target-" + tooth
    return {
        "target_id": target,
        "segment_id": "segment-" + tooth,
        "trajectory_set": {"slots": [
            {"slot": 1, "state": "Current", "trajectory_id": trajectory_id, "target_id": target,
             "prepared_branch_ids": [branch_id]},
            {"slot": 2, "state": "Empty", "trajectory_id": "", "prepared_branch_ids": []},
            {"slot": 3, "state": "Empty", "trajectory_id": "", "prepared_branch_ids": []},
        ]},
    }


def _registry_text(selected="guide-lower-34"):
    registry = empty_trajectory_registry()
    registry["teeth"]["FDI11"] = _tooth("FDI11", "guide-upper-11", "traj-guide-upper-11")
    registry["teeth"]["FDI34"] = _tooth("FDI34", "guide-lower-34", "traj-guide-lower-34")
    registry["teeth"]["FDI21"] = _tooth("FDI21", "guide-upper-21", "traj-guide-upper-21")
    registry["selected_branch_id"] = selected
    registry["prepared_branches"] = {
        "guide-upper-11": _branch("guide-upper-11", "target-FDI11"),
        "guide-lower-34": _branch("guide-lower-34", "target-FDI34"),
        "guide-upper-21": _branch("guide-upper-21", "target-FDI21", state="Stale",
                                  reason="Step 5C template is stale."),
    }
    return json.dumps(registry, sort_keys=True)


class FakeNode:
    def __init__(self, registry_text):
        self.step6TrajectoryRegistryJson = registry_text
        self.robotBaseMountLocked = False
        self.step6BasePlacementStatus = "Unlocked"
        self.step6PlanningContextImported = True
        self.robotBaseTransform = object()


class FakeTemplate:
    def __init__(self, record_text):
        self.record_text = record_text

    def GetAttribute(self, name):
        return self.record_text


class FakeLogic:
    """Read owners only. Any mutating or syncing call is an AttributeError, so the probe cannot make one."""

    def __init__(self, records, selected_eligible=True):
        self._records = records  # branch id -> normalized record text
        self._selected_eligible = selected_eligible
        self.calls = []

    def step6WorkingConfiguration(self, node, branchId=""):
        self.calls.append("step6WorkingConfiguration")
        text = self._records.get(branchId)
        return wc.loads(text) if text else None

    def evaluatePreparedBranchEligibility(self, node, branchId=None, *, registry=None, _forVerification=False):
        self.calls.append("evaluatePreparedBranchEligibility")
        selected = str((registry or {}).get("selected_branch_id") or "")
        eligible = self._selected_eligible
        return {
            "eligible": eligible,
            "reason": "VALID" if eligible else "STALE",
            "message": "PreparedBranch is current and verified." if eligible else "Step 5C is stale.",
            "branch_id": selected,
        }

    def isRos2MotionControlActive(self, base):
        self.calls.append("isRos2MotionControlActive")
        return False


class FakeWidget:
    def __init__(self, *, registry_text=None, records=None, live=None, selected_eligible=True):
        self._parameterNode = FakeNode(registry_text or _registry_text())
        self.logic = FakeLogic(records or {}, selected_eligible)
        self._live = live if live is not None else wc.normalize(
            {"branch_id": "guide-lower-34", "config": _config()})
        self._robotSimulationPanel = SimpleNamespace(branchConfigStatusLabel=SimpleNamespace(
            text="Saved for this branch: Opening 40.0 mm"))
        self.ui = SimpleNamespace(
            importStep6PlanningContextButton=SimpleNamespace(
                text="Activate Verified PreparedBranch for Step 6", enabled=True, visible=True),
            lockRobotBaseMountButton=SimpleNamespace(text="Accept Base", enabled=False, visible=True),
        )

    def _currentStep6WorkingConfiguration(self):
        return self._live


def _records(opening_lower=40.0):
    return {
        "guide-lower-34": wc.dumps({"branch_id": "guide-lower-34", "branch_foundation_fingerprint": FOUNDATION,
                                    "config": _config(opening=opening_lower, home={"link-1_Revolute-1": 0.1})}),
        "guide-upper-11": wc.dumps({"branch_id": "guide-upper-11", "branch_foundation_fingerprint": FOUNDATION,
                                    "config": _config(opening=45.9, planner="")}),
    }


def test_capture_reports_each_branch_its_stored_configuration_and_the_live_differences():
    widget = FakeWidget(records=_records(), live=wc.normalize({"branch_id": "guide-lower-34",
                                                               "config": _config(opening=40.0)}))

    state = probe.capture_branch_switch_state(widget, label="before-select")

    registry = state["registry"]
    assert registry["selected_branch_id"] == "guide-lower-34"
    assert registry["branch_count"] == 3
    assert registry["branches_not_current"] == ["guide-upper-21"]
    assert probe.branches_not_current(state) == ["guide-upper-21"]
    selected = state["branches"]["guide-lower-34"]
    assert selected["selected"] is True and selected["state"] == "Current"
    assert selected["stored"]["mouth_opening_mm"] == 40.0
    assert state["branches"]["guide-upper-11"]["stored"]["mouth_opening_mm"] == 45.9
    assert state["branches"]["guide-upper-11"]["stored"]["planner_id"] == ""
    assert state["branches"]["guide-upper-21"]["stored"] is None
    assert state["live"]["mouth_opening_mm"] == 40.0
    assert state["selected_differences"] == ["task_home_si"]  # saved Home is not staged on the live state
    assert state["selected_eligibility"]["eligible"] is True
    assert state["selected_eligibility"]["reason"] == "VALID"
    assert state["base"]["robotBaseMountLocked"] is False
    assert state["ui"]["import_button"]["text"] == "Activate Verified PreparedBranch for Step 6"
    assert state["ui"]["lock_base_button"] == {"present": True, "text": "Accept Base",
                                               "enabled": False, "visible": True}
    assert state["ui"]["branch_config_status"].startswith("Saved for this branch")
    assert state["label"] == "before-select"


def test_capture_is_read_only_and_never_calls_a_mutating_owner():
    widget = FakeWidget(records=_records())
    node_before = dict(vars(widget._parameterNode))  # shallow: the transform object must be the same instance
    registry_before = widget._parameterNode.step6TrajectoryRegistryJson

    state = probe.capture_branch_switch_state(widget)

    assert vars(widget._parameterNode) == node_before
    assert widget._parameterNode.step6TrajectoryRegistryJson == registry_before
    assert set(widget.logic.calls) <= {
        "step6WorkingConfiguration", "evaluatePreparedBranchEligibility", "isRos2MotionControlActive",
    }
    assert state["registry"]["digest"] == probe._digest(registry_before)


def test_digests_change_when_the_stored_record_or_the_registry_changes():
    base_state = probe.capture_branch_switch_state(FakeWidget(records=_records()))
    changed_record = _records(opening_lower=41.0)
    moved_state = probe.capture_branch_switch_state(FakeWidget(records=changed_record))
    registry_state = probe.capture_branch_switch_state(
        FakeWidget(records=_records(), registry_text=_registry_text(selected="guide-upper-11")))

    assert base_state["branches"]["guide-lower-34"]["stored"]["digest"] != \
        moved_state["branches"]["guide-lower-34"]["stored"]["digest"]
    assert base_state["registry"]["digest"] != registry_state["registry"]["digest"]
    assert base_state["registry"]["digest"] == probe.capture_branch_switch_state(
        FakeWidget(records=_records()))["registry"]["digest"]


def test_diff_names_exactly_the_changed_leaves_and_ignores_labels():
    before = probe.capture_branch_switch_state(FakeWidget(records=_records()), label="before")
    after = probe.capture_branch_switch_state(FakeWidget(records=_records(opening_lower=41.0)), label="after")

    assert probe.diff_branch_states(before, before) == []
    changes = probe.diff_branch_states(before, after)
    paths = [change["path"] for change in changes]
    assert "branches.guide-lower-34.stored.mouth_opening_mm" in paths
    assert "branches.guide-lower-34.stored.digest" in paths
    assert all(path.split(".")[0] != "label" for path in paths)
    assert "registry.digest" not in paths  # the stored registry itself did not change
    opening = next(c for c in changes if c["path"] == "branches.guide-lower-34.stored.mouth_opening_mm")
    assert (opening["before"], opening["after"]) == (40.0, 41.0)


def test_a_switch_between_branches_is_visible_in_the_selection_and_eligibility():
    before = probe.capture_branch_switch_state(FakeWidget(records=_records()))
    upper = probe.capture_branch_switch_state(
        FakeWidget(records=_records(), registry_text=_registry_text(selected="guide-upper-11"),
                   selected_eligible=False))

    paths = {change["path"] for change in probe.diff_branch_states(before, upper)}
    assert "registry.selected_branch_id" in paths
    assert "selected_eligibility.eligible" in paths
    assert "branches.guide-upper-11.selected" in paths


def test_write_state_stores_one_json_capture_at_the_evidence_path(tmp_path):
    state = probe.capture_branch_switch_state(FakeWidget(records=_records()), label="before")

    written = probe.write_state(state, tmp_path / "branch-switch" / "before.json")

    assert json.loads(written.read_text(encoding="utf-8")) == json.loads(json.dumps(state))
    assert written.parent.name == "branch-switch"


def test_the_probe_source_names_no_mutating_owner_and_stays_ascii():
    source = PROBE.read_text(encoding="utf-8")
    source.encode("ascii")  # the session driver decodes scripts as ASCII
    called = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute):
                called.add(target.attr)
            elif isinstance(target, ast.Name):
                called.add(target.id)
    assert called.isdisjoint(MUTATING), called & MUTATING
    assert "setattr(" not in source


def test_the_registry_fixture_is_a_current_schema_registry():
    registry = parse_trajectory_registry(_registry_text())
    assert registry["schema_version"] == "3.0"
    assert sorted(registry["prepared_branches"]) == ["guide-lower-34", "guide-upper-11", "guide-upper-21"]


def test_unreadable_selected_record_is_reported_as_missing_not_invented():
    widget = FakeWidget(records={})
    state = probe.capture_branch_switch_state(widget)
    assert state["branches"]["guide-lower-34"]["stored"] is None
    assert state["selected_differences"] is None


def test_missing_ui_controls_are_reported_not_faked():
    widget = FakeWidget(records=_records())
    widget.ui = SimpleNamespace()
    state = probe.capture_branch_switch_state(widget)
    assert state["ui"]["import_button"] == {"present": False}
    assert state["ui"]["lock_base_button"] == {"present": False}


# --- Task Home compare tolerance: the display quantization (DENTORobotSimulationPanel.py:1018, :1133) -----------

LIVE_FDI14_REVOLUTE = "link-1_Revolute-1"  # saved 0.006981317 rad (0.4 degree); live staged delta was 6.98e-5 rad


def test_the_live_fdi14_delta_passes_the_quantization_compare():
    saved = 0.006981317
    ok, detail = probe.task_home_within_quantization({LIVE_FDI14_REVOLUTE: saved + 6.98e-5},
                                                     {LIVE_FDI14_REVOLUTE: saved})
    assert ok, detail
    assert detail[LIVE_FDI14_REVOLUTE]["bound_si"] == pytest.approx(math.radians(0.005), rel=1e-6)


def test_one_full_display_step_is_outside_the_quantization_bound():
    saved = 0.006981317
    ok, detail = probe.task_home_within_quantization({LIVE_FDI14_REVOLUTE: saved + math.radians(0.01)},
                                                     {LIVE_FDI14_REVOLUTE: saved})
    assert not ok and detail[LIVE_FDI14_REVOLUTE]["within"] is False


def test_slider_joints_use_the_millimetre_quantization_in_metres():
    joint = "link-2_Slider-2"
    assert probe.task_home_quantization_bound_si(joint) == pytest.approx(5e-6, rel=1e-6)
    assert probe.task_home_within_quantization({joint: 0.03044 + 4e-6}, {joint: 0.03044})[0] is True
    assert probe.task_home_within_quantization({joint: 0.03044 + 6e-6}, {joint: 0.03044})[0] is False


def test_identical_and_mismatched_joint_sets_are_judged_by_name():
    assert probe.task_home_within_quantization({"a_Revolute-1": 0.1}, {"a_Revolute-1": 0.1})[0] is True
    ok, detail = probe.task_home_within_quantization({"a_Revolute-1": 0.1}, {"b_Revolute-2": 0.1})
    assert ok is False and detail["a_Revolute-1"]["within"] is False and detail["b_Revolute-2"]["within"] is False


def test_the_spin_rounding_of_any_saved_angle_is_inside_the_bound():
    # The gate's staged value is what the 2-decimal spin shows: round(degrees, 2). Every such value must pass.
    for degrees in (0.0, 0.4, 7.0, 12.345, 179.999, -33.333, 0.005, 0.015, 90.0):
        saved = math.radians(degrees)
        staged = math.radians(round(degrees, probe.TASK_HOME_DECIMALS))
        ok, detail = probe.task_home_within_quantization({LIVE_FDI14_REVOLUTE: staged},
                                                         {LIVE_FDI14_REVOLUTE: saved})
        assert ok, (degrees, detail)
