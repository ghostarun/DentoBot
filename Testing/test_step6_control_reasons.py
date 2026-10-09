"""Host checks: every gated Step 6 control in the refresh has a named reason.

Pure and source-level only (no Slicer/Qt). Scope: the widgets that
``_updateStep6PlanningUi`` enables, shows, hides or disables (6.1 Base and robot
setup, Task Home cancel/reconcile, 6.1-6.3 planning and drilling gates). The
Task Home review/accept/apply tooltips come from ``setTaskHomeActionBlockers``.
Not scanned yet: the advisor buttons, manual-jog and record controls, the
anatomy-review refresh, and the scene, placement and shell widgets.
"""

from __future__ import annotations

import ast
import itertools
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
PACKAGE = PYTHON / "dentobot_workflow"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))
from dentobot_workflow.step6_control_reasons import (  # noqa: E402
    CONTROL_PREREQUISITES,
    EXPLAINED_ELSEWHERE,
    PREFIX,
    apply_step6_control_tooltips,
    control_enabled,
    generic_reason,
    step6_control_reason,
    unexplained_step6_controls,
)

WIDGET = PACKAGE / "widget_robot.py"
MANUAL = PACKAGE / "widget_robot_manual.py"
PANEL = PYTHON / "DENTORobotSimulationPanel.py"
REFRESH = "_updateStep6PlanningUi"


def _method(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"method {name} not found")


def _is_owner(node: ast.AST) -> bool:
    """True for the ``panel`` name or the ``self.ui`` attribute that owns widgets."""

    return (isinstance(node, ast.Name) and node.id == "panel") or (
        isinstance(node, ast.Attribute) and node.attr == "ui"
    )


def _widget_name(node: ast.AST) -> str | None:
    """``self.ui.X`` or ``panel.X`` -> ``X``."""

    if isinstance(node, ast.Attribute) and _is_owner(node.value):
        return node.attr
    return None


def gated_targets(source: str, function_name: str) -> set[str]:
    """Widget names the function enables, shows, hides or disables (constant True ignored)."""

    func = _method(ast.parse(source), function_name)
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and not (
            isinstance(node.value, ast.Constant) and node.value.value is True
        ):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in {"enabled", "visible"}:
                    name = _widget_name(target.value)
                    if name:
                        names.add(name)
        elif isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
            for item in node.iter.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    names.add(item.value)
                elif isinstance(item, ast.Attribute):
                    names.add(item.attr)
        elif isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name) and node.func.id == "getattr"
                and len(node.args) >= 2 and _is_owner(node.args[0])
                and isinstance(node.args[1], ast.Constant)
            ):
                names.add(node.args[1].value)
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"setEnabled", "setVisible"}:
                name = _widget_name(node.func.value)
                if name:
                    names.add(name)
    return names


def _flag_keys_supplied(source: str) -> set[str]:
    method = _method(ast.parse(source), "_applyStep6ControlReasons")
    keys: set[str] = set()
    for node in ast.walk(method):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "flags" for t in node.targets)
            and isinstance(node.value, ast.Dict)
        ):
            keys.update(k.value for k in node.value.keys if isinstance(k, ast.Constant))
    return keys


def _own_flags(name: str) -> list[str]:
    return sorted({flag for flag, _text in CONTROL_PREREQUISITES[name] if flag})


def _combinations(flags: list[str]):
    for values in itertools.product((False, True), repeat=len(flags)):
        yield dict(zip(flags, values))


def test_prerequisite_table_is_well_formed():
    for name, prerequisites in CONTROL_PREREQUISITES.items():
        assert prerequisites, name
        for flag, text in prerequisites:
            assert flag is None or isinstance(flag, str), name
            assert text.strip() and not text.startswith(PREFIX), name


def test_refresh_gates_are_all_registered_or_explained_elsewhere():
    gated = gated_targets(WIDGET.read_text(encoding="utf-8"), REFRESH)
    assert gated, "no gated targets found in the refresh; the scanner is broken"
    unregistered = gated - set(CONTROL_PREREQUISITES) - set(EXPLAINED_ELSEWHERE)
    assert not unregistered, f"gated without a reason: {sorted(unregistered)}"
    stale = set(CONTROL_PREREQUISITES) - gated
    assert not stale, f"registered but no longer gated by the refresh: {sorted(stale)}"


def test_explained_elsewhere_names_point_at_a_real_explainer():
    trees = {
        "setTaskHomeActionBlockers": ast.parse(PANEL.read_text(encoding="utf-8")),
        "_explainDisabledPlannerButtons": ast.parse(MANUAL.read_text(encoding="utf-8")),
    }
    for name, explainer in EXPLAINED_ELSEWHERE.items():
        node = _method(trees[explainer], explainer)
        mentioned = {child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute)}
        mentioned |= {
            child.value for child in ast.walk(node)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        }
        assert name in mentioned, f"{name} is not explained by {explainer}"


def test_refresh_applies_reasons_and_flags_cover_the_table():
    calls = [
        node for node in ast.walk(_method(ast.parse(WIDGET.read_text(encoding="utf-8")), REFRESH))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_applyStep6ControlReasons"
    ]
    assert len(calls) == 1
    used = {flag for prereqs in CONTROL_PREREQUISITES.values() for flag, _ in prereqs if flag}
    missing = used - _flag_keys_supplied(MANUAL.read_text(encoding="utf-8"))
    assert not missing, f"flags used by the table but not supplied: {sorted(missing)}"


def test_every_disabled_or_hidden_control_has_a_named_reason_over_all_states():
    for name in CONTROL_PREREQUISITES:
        for flags in _combinations(_own_flags(name)):
            enabled = control_enabled(name, flags)
            # Visibility follows the same prerequisites in this table.
            reason = step6_control_reason(name, enabled, enabled, flags)
            if enabled:
                assert reason == "", (name, flags)
            else:
                assert reason.startswith(PREFIX) and reason != generic_reason(name), (
                    name, flags, reason,
                )
            assert not unexplained_step6_controls({name: (enabled, enabled)}, flags), name


def test_always_disabled_controls_state_their_retirement():
    always_off = [
        name for name, prereqs in CONTROL_PREREQUISITES.items()
        if all(flag is None for flag, _ in prereqs)
    ]
    assert {"previewTrajectoryMotionButton", "connectRos2MotionButton",
            "createRobotMountPlaneButton"} <= set(always_off)
    for name in always_off:
        reason = step6_control_reason(name, False, True, {})
        assert reason.startswith(PREFIX)
        assert any(word in reason for word in ("always disabled", "quarantined", "retired"))


def _stub(enabled=True, visible=True, tip=""):
    return SimpleNamespace(enabled=enabled, visible=visible, toolTip=tip)


def test_apply_writes_reason_and_restores_base_tip_without_doubling():
    widget = _stub(enabled=False, tip="Load the robot.")
    base_tips: dict[str, str] = {}
    widgets = {"loadRobotModelButton": widget}
    flags = {"scene_prepared": False, "base_unlocked_or_recovery": True}
    reasons = apply_step6_control_tooltips(widgets, flags, base_tips)
    first = widget.toolTip
    assert reasons["loadRobotModelButton"].startswith(PREFIX)
    assert first == "Load the robot.\n\n" + reasons["loadRobotModelButton"]
    apply_step6_control_tooltips(widgets, flags, base_tips)
    assert widget.toolTip == first  # a repeated refresh does not stack the reason
    widget.enabled = True
    apply_step6_control_tooltips(widgets, {"scene_prepared": True}, base_tips)
    assert widget.toolTip == "Load the robot."


def test_apply_reads_the_widgets_own_hidden_flag_not_its_ancestors():
    class Own:
        enabled = True
        toolTip = ""

        def __init__(self, hidden):
            self._hidden = hidden

        def isHidden(self):
            return self._hidden

    flags = {"scene_prepared": True}
    hidden = apply_step6_control_tooltips({"frameRobotButton": Own(True)}, flags, {})
    assert hidden["frameRobotButton"] == generic_reason("frameRobotButton")
    # Hidden only by an ancestor (its own flag is clear): no reason is needed.
    shown = apply_step6_control_tooltips({"frameRobotButton": Own(False)}, flags, {})
    assert shown["frameRobotButton"] == ""


def test_check_catches_a_disabled_control_without_a_reason():
    original = dict(CONTROL_PREREQUISITES)
    try:
        # Mutation 1: the only prerequisite has no text.
        CONTROL_PREREQUISITES["frameRobotButton"] = (("scene_prepared", ""),)
        assert unexplained_step6_controls(
            {"frameRobotButton": (False, True)}, {"scene_prepared": False}
        ) == ("frameRobotButton",)
        # Mutation 2: the control has no prerequisite at all.
        CONTROL_PREREQUISITES["frameRobotButton"] = ()
        assert unexplained_step6_controls(
            {"frameRobotButton": (False, True)}, {"scene_prepared": False}
        ) == ("frameRobotButton",)
    finally:
        CONTROL_PREREQUISITES.clear()
        CONTROL_PREREQUISITES.update(original)


def test_source_scan_flags_an_unregistered_gated_control():
    synthetic = (
        "class W:\n"
        "    def _updateStep6PlanningUi(self):\n"
        "        self.ui.brandNewGatedButton.enabled = self.flag\n"
        "        panel.otherButton.visible = False\n"
        "        panel.homeGroup.enabled = True\n"
    )
    found = gated_targets(synthetic, REFRESH)
    assert found == {"brandNewGatedButton", "otherButton"}
    assert found - set(CONTROL_PREREQUISITES) - set(EXPLAINED_ELSEWHERE) == found
