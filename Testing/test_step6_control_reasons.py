"""Host checks: every gated Step 6 control has a named reason.

Pure and source-level only (no Slicer/Qt). The scanner reads every Step 6
module for enable, visibility and show/hide sites and resolves each target to a
registry name. A site with no registry entry, explained elsewhere, or a listed
exception fails the test.
"""

from __future__ import annotations

import ast
import itertools
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
PACKAGE = PYTHON / "dentobot_workflow"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))
from dentobot_workflow.step6_control_flags import annotate_refresh_controls  # noqa: E402
from dentobot_workflow.step6_control_reasons import (  # noqa: E402
    ADVISOR_CONTROLS,
    CONTROL_PREREQUISITES,
    EXPLAINED_ELSEWHERE,
    PREFIX,
    REFRESH_CONTROLS,
    annotate_step6_controls,
    apply_step6_control_tooltips,
    control_enabled,
    generic_reason,
    step6_control_reason,
    unexplained_step6_controls,
)

PANEL = PYTHON / "DENTORobotSimulationPanel.py"
ADVISOR_FILE = PACKAGE / "widget_step6_advisor.py"
REFRESH = "_updateStep6PlanningUi"

# Step 6 modules scanned in full: module file -> owner prefix for registry names.
STEP6_MODULES = {
    "widget_robot.py": "refresh",
    "widget_robot_manual.py": "refresh",
    "widget_step6_advisor.py": "advisor",
    "DENTORobotSimulationPanel.py": "panel",
    "widget_robot_scene.py": "scene",
    "widget_robot_shell.py": "shell",
    "widget_robot_placement.py": "placement",
}
# Cross-cutting modules: only their Step 6 sites (target names starting with "step6") are scanned.
CROSS_CUTTING_MODULES = {
    "widget_navigation.py": "step6",
    "widget_lifecycle.py": "step6",
    "widget_view_controls.py": "step6",
    "widget_application.py": "step6",
}
PANEL_FILE = "DENTORobotSimulationPanel.py"

# Local names that stand for a registry name: (module, name) or (module, function, name).
LOCAL_ALIASES = {
    ("widget_step6_advisor.py", "button"): ("advisor.fixButton",),
    ("widget_step6_advisor.py", "dialog"): ("advisor.dialog",),
    (PANEL_FILE, "_setupTcpKeyboardShortcuts", "shortcut"): ("tcpShortcut",),
    (PANEL_FILE, "_updateTcpCartesianControlState", "shortcut"): ("tcpShortcut",),
    (PANEL_FILE, "_setupManualJogKeyboardShortcuts", "shortcut"): ("manualJogShortcut",),
    (PANEL_FILE, "_updateManualJogKeyboardControlState", "shortcut"): ("manualJogShortcut",),
    (PANEL_FILE, "slider"): ("manualJogSlider",),
    (PANEL_FILE, "value"): ("manualJogValue",),
    (PANEL_FILE, "button"): ("tcpNudgeButton",),
    (PANEL_FILE, "selector"): ("manualSimulationRecordComboBox",),
    (PANEL_FILE, "replay"): ("plannerReplayButton",),
    (PANEL_FILE, "choose"): ("plannerChooseButton",),
    (PANEL_FILE, "review_button"): ("motionReviewButton",),
    (PANEL_FILE, "path_button"): ("motionPathButton",),
    (PANEL_FILE, "preview_button"): ("motionPreviewButton",),
    (PANEL_FILE, "apply_button"): ("motionApplyButton",),
    (PANEL_FILE, "lock_button"): ("motionLockButton",),
    (PANEL_FILE, "unlock_button"): ("motionUnlockButton",),
    (PANEL_FILE, "display_dialog"): ("panel.window",),
    (PANEL_FILE, "setup_dialog"): ("panel.window",),
    (PANEL_FILE, "home_dialog"): ("panel.window",),
    (PANEL_FILE, "dialog"): ("panel.window",),
    ("widget_robot_shell.py", "toolbar"): ("shell.toolbar",),
    ("widget_application.py", "step6Context"): ("application.step6Context",),
    ("widget_robot_placement.py", "shortcut"): ("robotNudgeShortcut",),
    (PANEL_FILE, "notice"): ("notice",),
    (PANEL_FILE, "task_limits_group"): ("step6TaskJointLimitsGroupBox",),
    ("widget_robot_scene.py", "widget"): ("scene.caseFoundationGate",),
    ("widget_robot_scene.py", "button"): ("scene.caseFoundationGate",),
    ("widget_robot_scene.py", "editor"): ("scene.caseFoundationGate",),
    ("widget_robot_placement.py", "dialog"): ("placement.window",),
    ("widget_robot_shell.py", "widget"): ("shell.placementHost",),
}

_WINDOW = "window opened and closed by its own button; not a gated control"
_LABEL = "status text, not a control; the nearby status line explains the state"
# Sites that are not gated controls. Each needs its reason.
EXCEPTIONS = {
    ("widget_step6_advisor.py", "advisor.dialog"): "advisor window: opened, raised and closed; not a control",
    (PANEL_FILE, "panel.window"): _WINDOW,
    (PANEL_FILE, "_setupToolsDialog"): _WINDOW,
    (PANEL_FILE, "_baseDiagnosisDialog"): _WINDOW,
    (PANEL_FILE, "_taskHomeDetailsDialog"): _WINDOW,
    (PANEL_FILE, "_manualRecordsDialog"): _WINDOW,
    (PANEL_FILE, "_planningToolsDialog"): _WINDOW,
    (PANEL_FILE, "_displayDialog"): _WINDOW,
    (PANEL_FILE, "_anatomyReviewDialog"): _WINDOW,
    (PANEL_FILE, "taskHomeCurrentStateLabel"): _LABEL,
    (PANEL_FILE, "taskHomeConfiguredStateLabel"): _LABEL,
    (PANEL_FILE, "taskHomeCandidateLabel"): _LABEL,
    (PANEL_FILE, "notice"): _LABEL,
    (PANEL_FILE, "plannerComparisonProgressLabel"): _LABEL,
    (PANEL_FILE, "_manualJogDetailsWidget"): "collapsible manual-jog details; its disclosure toggle is the control",
    (PANEL_FILE, "_step6SubstepNavigator"): "substep navigator container; hidden by the application shell",
    ("widget_robot_shell.py", "shell.toolbar"): "expert return toolbar container; its buttons are not gated here",
    ("widget_robot_shell.py", "shell.placementHost"):
        "offline placement host: the visualization group is reparented with the placement surface",
    ("widget_robot_shell.py", "_step6ExpertReturnToolbar"): "expert return toolbar container; its buttons are not gated here",
    ("widget_robot_shell.py", "_step6SubstepNavigator"): "substep navigator container; hidden by the application shell",
    ("widget_robot_shell.py", "robotPlacementDescriptionLabel"): _LABEL,
    ("widget_robot_shell.py", "_step61PlacementMirrorStatusLabel"): _LABEL,
    ("widget_robot_shell.py", "_step3BContinueButton"): "Step 3B continue button, owned by the Step 3B workflow",
    ("widget_robot_placement.py", "_step3BContinueButton"): "Step 3B continue button, owned by the Step 3B workflow",
    ("widget_robot_placement.py", "placement.window"): "candidate ranking window; opened and closed, not a control",
    ("widget_robot_placement.py", "verticalHeader"): "table header decoration, not a control",
    ("widget_robot_scene.py", "scene.caseFoundationGate"):
        "Case Foundation authoring gate: disables and restores editors of other sections dynamically; see report",
    ("widget_view_controls.py", "_step6ViewContextWidget"): "Step 6 view-context status container, not a control",
    ("widget_lifecycle.py", "_step6ExpertReturnToolbar"): "expert return toolbar container, shown and removed by lifecycle",
    ("widget_application.py", "application.step6Context"): "Step 6 context status container, not a control",
}

# Controls explained in the panel's own explainers (see EXPLAINED_ELSEWHERE).
Site = tuple[int, str, str, tuple[str, ...]]  # line, kind, raw expression, candidate names


def _method(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"method {name} not found")


def _loop_values(iterable: ast.AST) -> list[str] | None:
    """Names a literal loop tuple yields: constant strings, attribute names or local names."""

    if not isinstance(iterable, ast.Tuple):
        return None
    values = []
    for item in iterable.elts:
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            values.append(item.value)
        elif isinstance(item, ast.Attribute):
            values.append(item.attr)
        elif isinstance(item, ast.Name):
            values.append(item.id)
        else:
            return None
    return values


# Constructor parameters that stand for a named widget in another module.
NAME_SYNONYMS = {"task_limits_group": "step6TaskJointLimitsGroupBox"}


def _candidates(names: list[str], owner: str) -> tuple[str, ...]:
    out: list[str] = []
    for name in names:
        name = NAME_SYNONYMS.get(name, name)
        out.extend((name, f"{owner}.{name}"))
    return tuple(out)


def _resolve(expr: ast.AST, owner: str, env: dict, module: str, function: str) -> tuple[str, ...]:
    """Candidate registry names for the object a gate is applied to (empty when unresolved)."""

    if isinstance(expr, ast.Attribute):
        return _candidates([expr.attr], owner)
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute):
        return _candidates([expr.func.attr], owner)
    if isinstance(expr, ast.Subscript):
        key = expr.slice
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            return (f"{owner}.{key.value}",)
        if isinstance(key, ast.Name) and key.id in env:
            return tuple(f"{owner}.{value}" for value in env[key.id])
        return ()
    if isinstance(expr, ast.Name):
        if expr.id in env:
            return _candidates(env[expr.id], owner)
        scoped = LOCAL_ALIASES.get((module, function, expr.id))
        return scoped if scoped is not None else LOCAL_ALIASES.get((module, expr.id), ())
    return ()


def _getattr_alias(node: ast.Assign, env: dict) -> tuple[str, list[str]] | None:
    """``name = getattr(obj, <loop name or literal>, default)`` -> (name, the names it can hold)."""

    if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
        return None
    call = node.value
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            and call.func.id == "getattr" and len(call.args) >= 2):
        return None
    key = call.args[1]
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        return node.targets[0].id, [key.value]
    if isinstance(key, ast.Name) and key.id in env:
        return node.targets[0].id, list(env[key.id])
    return None


def scan_sites(source: str, module: str, owner: str, only_step6: bool = False) -> list[Site]:
    """Every enable/visibility/show/hide site in ``source`` with its candidate names."""

    sites: list[Site] = []

    def add(line, kind, expr_node, env, function):
        raw = ast.unparse(expr_node)
        if only_step6 and "step6" not in raw.lower():
            return
        sites.append((line, kind, raw, _resolve(expr_node, owner, env, module, function)))

    def visit(node: ast.AST, env: dict, function: str) -> None:
        if isinstance(node, ast.FunctionDef):
            function = node.name
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            values = _loop_values(node.value)
            if values is not None:
                env[f"tuple:{node.targets[0].id}"] = values
        if isinstance(node, ast.For):
            inner = dict(env)
            values = _loop_values(node.iter)
            if values is None and isinstance(node.iter, ast.Name):
                values = env.get(f"tuple:{node.iter.id}")
            if values is not None and isinstance(node.target, ast.Name):
                inner[node.target.id] = values
            for child in node.body + node.orelse:
                visit(child, inner, function)
            return
        if isinstance(node, ast.Assign) and _getattr_alias(node, env):
            name, names = _getattr_alias(node, env)
            env[name] = names
        if isinstance(node, ast.Assign) and not (
            isinstance(node.value, ast.Constant) and node.value.value is True
        ):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in {"enabled", "visible"}:
                    add(node.lineno, "assign", target.value, env, function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"setEnabled", "setVisible", "hide", "show"}:
                add(node.lineno, node.func.attr, node.func.value, env, function)
        for child in ast.iter_child_nodes(node):
            visit(child, env, function)

    visit(ast.parse(source), {}, "<module>")
    return sites


def _known_names() -> set[str]:
    return set(CONTROL_PREREQUISITES) | set(EXPLAINED_ELSEWHERE)


def _accounted(module: str, names: tuple[str, ...]) -> bool:
    known = _known_names()
    return any(name in known or (module, name) in EXCEPTIONS for name in names)


def scanned_sites(module: str, owner: str) -> list[Site]:
    source = (PACKAGE / module if module != PANEL_FILE else PANEL).read_text(encoding="utf-8")
    if module in CROSS_CUTTING_MODULES:
        return scan_sites(source, module, owner, only_step6=True)
    return scan_sites(source, module, owner)


def unaccounted_sites(source: str, module: str, owner: str) -> list[Site]:
    return [site for site in scan_sites(source, module, owner) if not _accounted(module, site[3])]


def _owner_flag_keys(path: Path, function: str) -> set[str]:
    keys: set[str] = set()
    for node in ast.walk(_method(ast.parse(path.read_text(encoding="utf-8")), function)):
        if isinstance(node, ast.Dict):
            keys.update(k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str))
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


def test_every_step6_module_gate_site_is_registered_or_explained():
    failures = {}
    modules = [(m, o) for m, o in STEP6_MODULES.items()] + [(m, "cross") for m in CROSS_CUTTING_MODULES]
    for module, owner in modules:
        sites = scanned_sites(module, owner)
        assert sites, f"{module}: no gating sites found; the scanner is broken"
        unresolved = [(line, expr) for line, _k, expr, names in sites if not names]
        unregistered = [(line, expr) for line, _k, expr, names in sites
                        if names and not _accounted(module, names)]
        if unresolved or unregistered:
            failures[module] = {"unresolved": unresolved, "unregistered": unregistered}
    assert not failures, failures


def test_every_registered_control_is_gated_by_some_step6_module():
    gated: set[str] = set()
    for module, owner in STEP6_MODULES.items():
        gated |= {name for site in scanned_sites(module, owner) for name in site[3]}
    for module in CROSS_CUTTING_MODULES:
        gated |= {name for site in scanned_sites(module, "cross") for name in site[3]}
    stale = set(CONTROL_PREREQUISITES) - gated
    assert not stale, f"registered but never gated by a scanned module: {sorted(stale)}"


def test_explained_elsewhere_names_point_at_a_real_explainer():
    trees = {
        "setTaskHomeActionBlockers": ast.parse(PANEL.read_text(encoding="utf-8")),
        "_explainDisabledPlannerButtons": ast.parse(
            (PACKAGE / "widget_robot_manual.py").read_text(encoding="utf-8")
        ),
    }
    for name, explainer in EXPLAINED_ELSEWHERE.items():
        node = _method(trees[explainer], explainer)
        mentioned = {child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute)}
        mentioned |= {
            child.value for child in ast.walk(node)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        }
        assert name in mentioned, f"{name} is not explained by {explainer}"


FLAG_SUPPLIERS = (
    (PACKAGE / "step6_control_flags.py", ("_refresh_flags", "_panel_flags", "_nav_flags",
                                          "annotate_case_foundation")),
    (ADVISOR_FILE, ("_advisorExplainControls",)),
    (PANEL, ("setAnatomyReviewCandidates", "showMotionDiagnostics", "showPlannerComparison")),
    (PACKAGE / "widget_robot_placement.py", ("_updateRobotKeyboardShortcutState",)),
)


def test_flags_used_by_the_tables_are_supplied_by_their_owners():
    supplied: set[str] = set()
    for path, functions in FLAG_SUPPLIERS:
        for function in functions:
            supplied |= _owner_flag_keys(path, function)
    used = {flag for prereqs in CONTROL_PREREQUISITES.values() for flag, _ in prereqs if flag}
    missing = used - supplied
    assert not missing, sorted(missing)


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
    retired = {
        "previewTrajectoryMotionButton", "connectRos2MotionButton", "disconnectRos2MotionButton",
        "createRobotMountPlaneButton", "flipRobotMountPlaneButton", "snapRobotBaseToPlaneButton",
    }
    always_off = {
        name for name, prereqs in CONTROL_PREREQUISITES.items()
        if all(flag is None for flag, _ in prereqs)
    }
    assert retired <= always_off
    for name in always_off:
        assert step6_control_reason(name, False, True, {}).startswith(PREFIX), name
    for name in retired:
        reason = step6_control_reason(name, False, True, {})
        assert any(word in reason for word in ("always disabled", "quarantined")), name


def _stub(enabled=True, visible=True, tip=""):
    return SimpleNamespace(enabled=enabled, visible=visible, toolTip=tip)


def test_apply_writes_reason_and_restores_base_tip_without_doubling():
    widget = _stub(enabled=False, tip="Load the robot.")
    base_tips: dict[int, str] = {}
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


def test_apply_accepts_several_widgets_under_one_name():
    buttons = [_stub(enabled=False, tip="Fix %d" % index) for index in range(2)]
    base_tips: dict[int, str] = {}
    apply_step6_control_tooltips(
        [("advisor.fixButton", button) for button in buttons],
        {"fix_idle": False, "not_busy": True}, base_tips,
    )
    assert all("Setup fixes wait" in button.toolTip for button in buttons)
    assert [button.toolTip.partition("\n\n")[0] for button in buttons] == ["Fix 0", "Fix 1"]


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


def test_scanner_flags_an_unregistered_gated_control_in_any_step6_module():
    synthetic = (
        "class W:\n"
        "    def _updateStep6PlanningUi(self):\n"
        "        self.ui.brandNewGatedButton.enabled = self.flag\n"
        "        panel.otherButton.visible = False\n"
        "        panel.homeGroup.enabled = True\n"
        "        for item in (panel.checkNewButton,):\n"
        "            item.setEnabled(False)\n"
    )
    expected = {"self.ui.brandNewGatedButton", "panel.otherButton", "item"}
    for module in ("widget_robot.py", "widget_step6_advisor.py"):
        flagged = {site[2] for site in unaccounted_sites(synthetic, module, "refresh")}
        assert flagged == expected, module
        assert not [site for site in scan_sites(synthetic, module, "refresh") if not site[3]]


class _RefreshHost:
    """Minimal stand-in for the widget; ``logic`` decides whether the flag computation raises."""

    def __init__(self, logic):
        self.logic = logic
        self._robotSimulationPanel = None
        self._robotWorkflowFacade = None
        self._parameterNode = SimpleNamespace(
            step6AssistedLimitProposalJson="", step6MotionDiagnosticJson="",
            step6PlannerComparisonJson="", robotBaseTransform=None, finalPrintableTemplateModel=None,
        )
        self.ui = SimpleNamespace(
            loadRobotModelButton=_stub(enabled=False, visible=True, tip="Load."),
            frameRobotButton=_stub(enabled=True, visible=True, tip="Frame."),
        )

    def _manualBaseReviewControlState(self, *_args):
        return {"group": False, "begin": False, "cancel": False, "reconcile": False}


def test_refresh_annotation_failure_leaves_enable_and_visibility_intact(caplog):
    host = _RefreshHost(logic=None)  # every logic-backed flag raises AttributeError
    before = {name: (w.enabled, w.visible) for name, w in vars(host.ui).items()}
    refresh = {"scene_prepared": True, "robot_present": False, "locked": False}
    with caplog.at_level(logging.ERROR):
        annotate_refresh_controls(host, refresh)  # must not raise
    after = {name: (w.enabled, w.visible) for name, w in vars(host.ui).items()}
    assert after == before
    assert "Step 6 control reasons skipped for 6.1 refresh" in caplog.text


def test_refresh_annotation_writes_reasons_when_flags_compute(caplog):
    logic = SimpleNamespace(
        isRobotBaseTransformNode=lambda node: False,
        robotWorkspaceModelNode=lambda: None,
    )
    host = _RefreshHost(logic=logic)
    with caplog.at_level(logging.ERROR):
        annotate_refresh_controls(host, {"scene_prepared": True, "robot_present": False, "locked": False})
    assert host.ui.loadRobotModelButton.enabled is False  # the gate itself is untouched
    assert host.ui.loadRobotModelButton.toolTip.startswith("Load.\n\n" + PREFIX)
    assert host.ui.frameRobotButton.toolTip == "Frame."
    assert "skipped" not in caplog.text
