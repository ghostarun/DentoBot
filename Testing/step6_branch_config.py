"""Per-branch Step 6 working configurations inside one dentocase (S6-MULTI-TARGET-01).

Research/testing only, not a product feature. Step 6 is distinct per PreparedBranch:
each target tooth/trajectory can need its own mouth opening, Base, Task Home and
planning policy. This helper stores, per branch id, the configuration that made the
planner work plus its diagnostics summary, evidence path and series result, in one
scene node that the dentocase save/restore carries:

    vtkMRMLScriptedModuleNode "[Research] DENTO Step 6 Working Configurations"
    attribute "DENTOBOT.Research.Step6Config.<branch_id>" = JSON

``apply_branch_config`` activates the branch and re-applies its configuration through
the existing GUI owners (Step 6 opening, 6.1 Base review/accept, 6.2 Home, 6.3 policy,
Confirm) so the working conditions can be checked and previewed after a restore.
Simulation only.
"""

from __future__ import annotations

import json
import math
import time

NODE_NAME = "[Research] DENTO Step 6 Working Configurations"
ATTRIBUTE_PREFIX = "DENTOBOT.Research.Step6Config."


def _store_node(create: bool = True):
    import slicer

    for node in slicer.util.getNodesByClass("vtkMRMLScriptedModuleNode"):
        if node.GetName() == NODE_NAME:
            return node
    if not create:
        return None
    node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScriptedModuleNode", NODE_NAME)
    node.SetAttribute("DENTOBOT.Research", "Step6WorkingConfigurations; simulation research only")
    return node


def read_all() -> dict:
    node = _store_node(create=False)
    if node is None:
        return {}
    out = {}
    for name in node.GetAttributeNames() or ():
        if name.startswith(ATTRIBUTE_PREFIX):
            out[name[len(ATTRIBUTE_PREFIX):]] = json.loads(node.GetAttribute(name))
    return out


def read(branch_id: str) -> dict | None:
    return read_all().get(branch_id)


def _base_matrix(node) -> list:
    import vtk

    matrix = vtk.vtkMatrix4x4()
    node.robotBaseTransform.GetMatrixTransformToWorld(matrix)
    return [[matrix.GetElement(r, c) for c in range(4)] for r in range(4)]


def capture_current(ns: dict) -> dict:
    """The live Step 6 configuration of the active branch."""
    logic, node, panel, facade = ns["logic"], ns["parameter_node"], ns["panel"], ns["facade"]
    home = logic.taskHomeRecord(node)
    policy = panel.planningPolicy()
    return {
        "mouth_opening_mm": float(node.step6CaseJawTargetGapMm),
        "base_world_mm": _base_matrix(node),
        "task_home_si": dict(zip(home.joint_names, home.joint_positions_si)) if home else None,
        "planning_attempts": int(policy["planning_attempts"]),
        "planning_time_sec": float(policy["planning_time_sec"]),
        "corridor_margin_samples": int(getattr(facade, "_approach_corridor_margin_samples", 0) or 0),
        "allow_spindle_guide_contact": bool(node.step6AllowSpindleGuideContact),
    }


def record(ns: dict, branch_id: str, *, target_fdi: str, trajectory: str, config: dict | None = None,
           levers_applied=(), diagnostics: dict | None = None, evidence_dir: str = "",
           series: dict | None = None, status: str = "", notes: str = "") -> dict:
    entry = {
        "branch_id": branch_id,
        "target_fdi": str(target_fdi),
        "trajectory": trajectory,
        "status": status,
        "config": config or capture_current(ns),
        "levers_applied": list(levers_applied),
        "diagnostics": diagnostics or {},
        "evidence_dir": evidence_dir,
        "series": series or {},
        "notes": notes,
        "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _store_node().SetAttribute(ATTRIBUTE_PREFIX + branch_id, json.dumps(entry, default=str))
    return entry


def diagnostics_summary(diagnosis: dict, frame_audit: dict | None = None, drilling: dict | None = None) -> dict:
    return {
        "status": diagnosis.get("status"),
        "verdict": str(diagnosis.get("verdict", ""))[:600],
        "cause_class": diagnosis.get("cause_class"),
        "rows": [(r.get("check"), r.get("status"), str(r.get("detail", ""))[:200]) for r in diagnosis.get("rows", [])],
        "frame_audit": frame_audit or {},
        "drilling": drilling or {},
    }


def activate_branch(ns: dict, branch_id: str) -> None:
    logic, node = ns["logic"], ns["parameter_node"]
    if logic.isRos2MotionControlActive(node.robotBaseTransform):
        result = ns["facade"].disconnect()
        assert result.success, result.message
    logic.activateDentoCasePreparedBranch(node, branch_id)


def apply_branch_config(ns: dict, branch_id: str, *, process_events, config: dict | None = None) -> list:
    """Activate ``branch_id`` and re-apply its stored (or given) Step 6 configuration."""
    widget, panel, facade = ns["widget"], ns["panel"], ns["facade"]
    logic, node = ns["logic"], ns["parameter_node"]
    config = config or (read(branch_id) or {}).get("config")
    if not config:
        raise ValueError(f"no stored Step 6 configuration for {branch_id}")
    steps = []

    def ev():
        process_events(0.2)
        widget._updateRobotPlacement()

    activate_branch(ns, branch_id)
    ev()
    steps.append("branch")
    combo = widget.ui.workflowStageComboBox
    combo.currentIndex = next(i for i in range(combo.count) if str(combo.itemText(i)).startswith("6 "))
    ev()
    if abs(float(node.step6CaseJawTargetGapMm) - float(config["mouth_opening_mm"])) > 1e-6:
        node.step6CaseJawTargetGapMm = float(config["mouth_opening_mm"])
        widget.onApplyStep6CaseJawOpening()
        ev()
        steps.append(("opening", float(config["mouth_opening_mm"])))
    widget._updateStep6PlanningUi()
    ev()
    button = widget.ui.importStep6PlanningContextButton
    assert button.enabled, "import disabled: " + str(button.toolTip)
    button.click()
    ev()
    steps.append("import")
    widget._step6SubstepComboBox.currentIndex = 1
    ev()
    if panel.loadFallbackButton.enabled:
        panel.loadFallbackButton.click()
        ev()
    target = [v for row in config["base_world_mm"] for v in row]
    if max(abs(a - b) for a, b in zip([v for row in _base_matrix(node) for v in row], target)) > 1e-9 \
            or not node.robotBaseMountLocked:
        if node.robotBaseMountLocked:
            result = facade.unlockBase()
            assert result.success, result.message
        result = facade.stageManualBaseReview(tuple(target))
        if not result.success:
            facade.cancelManualBaseReview()
            result = facade.stageManualBaseReview(tuple(target))
        assert result.success, result.message
        result = facade.acceptManualBaseReview()
        assert result.success, result.message
        ev()
        steps.append("base")
    if panel.connectButton.enabled:
        panel.connectButton.click()
        ev()
        steps.append("connect")
    facade._approach_corridor_margin_samples = int(config.get("corridor_margin_samples", 0))
    widget._step6SubstepComboBox.currentIndex = 2
    ev()
    home = config.get("task_home_si")
    names = ("cancelTaskHomeReviewButton", "resetManualJogDraftButton", "reviewTaskHomeButton", "acceptTaskHomeButton")
    if home and any(abs(v) > 1e-12 for v in home.values()):
        if panel.cancelTaskHomeReviewButton.enabled:
            panel.cancelTaskHomeReviewButton.click()
            ev()
        for joint, value in home.items():
            panel.manualJogJointControls[joint][1].setValue(value * 1000.0 if "Slider" in joint else math.degrees(value))
            ev()
        names = ("reviewTaskHomeButton", "acceptTaskHomeButton")
    for name in names:
        button = getattr(panel, name)
        if button.enabled:
            button.click()
            ev()
    gap = facade.taskHomeValidationGap(node)
    steps.append(("home_gap", gap))
    widget._step6SubstepComboBox.currentIndex = 3
    ev()
    panel.confirmTaskButton.click()
    ev()
    steps.append("confirm")
    return steps
