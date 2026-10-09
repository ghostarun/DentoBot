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
REFRESH_OWNER_FILES = {
    "widget_robot.py": ("refresh", PACKAGE / "widget_robot.py"),
    "widget_robot_manual.py": ("refresh", PACKAGE / "widget_robot_manual.py"),
}
ADVISOR_FILE = PACKAGE / "widget_step6_advisor.py"

# Step 6 modules scanned in full: module file -> owner prefix of its registry keys.
STEP6_MODULES = {
    "widget_robot.py": "refresh",
    "widget_robot_manual.py": "refresh",
    "widget_step6_advisor.py": "advisor",
}

# Local variable names that stand for a registry name inside one module.
LOCAL_ALIASES = {
    ("widget_step6_advisor.py", "button"): ("advisor.fixButton",),
    ("widget_step6_advisor.py", "dialog"): ("advisor.dialog",),
}

# Sites that are not gated controls. Each needs its reason.
EXCEPTIONS = {
    ("widget_step6_advisor.py", "advisor.dialog"): "advisor window: opened, raised and closed; not a control",
}

Site = tuple[int, str, str, tuple[str, ...]]  # line, kind, raw expression, candidate names


def _method(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"method {name} not found")


def _loop_values(iterable: ast.AST) -> list[str] | None:
    """Names a literal loop tuple yields: constant strings or attribute names."""

    if not isinstance(iterable, ast.Tuple):
        return None
    values = []
    for item in iterable.elts:
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            values.append(item.value)
        elif isinstance(item, ast.Attribute):
            values.append(item.attr)
        else:
            return None
    return values


def _candidates(names: list[str], owner: str) -> tuple[str, ...]:
    out: list[str] = []
    for name in names:
        out.extend((name, f"{owner}.{name}"))
    return tuple(out)


def _resolve(expr: ast.AST, owner: str, env: dict, module: str) -> tuple[str, ...]:
    """Candidate registry names for the object a gate is applied to ('' when unresolved)."""

    if isinstance(expr, ast.Attribute):
        return _candidates([expr.attr], owner)
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
        return LOCAL_ALIASES.get((module, expr.id), ())
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


def scan_sites(source: str, module: str, owner: str) -> list[Site]:
    """Every enable/visibility/show/hide site in ``source`` with its candidate names."""

    sites: list[Site] = []

    def visit(node: ast.AST, env: dict) -> None:
        if isinstance(node, ast.For):
            inner = dict(env)
            values = _loop_values(node.iter)
            if values is not None and isinstance(node.target, ast.Name):
                inner[node.target.id] = values
            for child in node.body + node.orelse:
                visit(child, inner)
            return
        if isinstance(node, ast.Assign) and _getattr_alias(node, env):
            name, names = _getattr_alias(node, env)
            env[name] = names
        if isinstance(node, ast.Assign) and not (
            isinstance(node.value, ast.Constant) and node.value.value is True
        ):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in {"enabled", "visible"}:
                    sites.append((node.lineno, "assign", ast.unparse(target.value),
                                  _resolve(target.value, owner, env, module)))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"setEnabled", "setVisible", "hide", "show"}:
                sites.append((node.lineno, node.func.attr, ast.unparse(node.func.value),
                              _resolve(node.func.value, owner, env, module)))
        for child in ast.iter_child_nodes(node):
            visit(child, env)

    visit(ast.parse(source), {})
    return sites


def _known_names() -> set[str]:
    return set(CONTROL_PREREQUISITES) | set(EXPLAINED_ELSEWHERE) | {key for _m, key in EXCEPTIONS}


def unaccounted_sites(source: str, module: str, owner: str) -> list[Site]:
    known = _known_names()
    return [site for site in scan_sites(source, module, owner)
            if not any(name in known for name in site[3])]


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
    for module, owner in STEP6_MODULES.items():
        source = (PACKAGE / module).read_text(encoding="utf-8")
        sites = scan_sites(source, module, owner)
        assert sites, f"{module}: no gating sites found; the scanner is broken"
        unresolved = [site for site in sites if not site[3]]
        unaccounted = unaccounted_sites(source, module, owner)
        if unresolved or unaccounted:
            failures[module] = {
                "unresolved": [(line, expr) for line, _k, expr, names in unresolved],
                "unregistered": [(line, expr) for line, _k, expr, names in unaccounted if names],
            }
    assert not failures, failures


def test_registry_entries_are_gated_by_their_owner_module():
    refresh_names: set[str] = set()
    advisor_names: set[str] = set()
    for module, owner in STEP6_MODULES.items():
        source = (PACKAGE / module).read_text(encoding="utf-8")
        found = {name for site in scan_sites(source, module, owner) for name in site[3]}
        if owner == "advisor":
            advisor_names |= found
        else:
            refresh_names |= found
    assert set(REFRESH_CONTROLS) <= refresh_names, sorted(set(REFRESH_CONTROLS) - refresh_names)
    assert set(ADVISOR_CONTROLS) <= advisor_names, sorted(set(ADVISOR_CONTROLS) - advisor_names)


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


def test_each_owner_supplies_every_flag_its_table_uses():
    owners = {
        "refresh": (PACKAGE / "widget_robot_manual.py", "_applyStep6ControlReasons", REFRESH_CONTROLS),
        "advisor": (ADVISOR_FILE, "_advisorExplainControls", ADVISOR_CONTROLS),
    }
    for owner, (path, function, table) in owners.items():
        used = {flag for prereqs in table.values() for flag, _ in prereqs if flag}
        missing = used - _owner_flag_keys(path, function)
        assert not missing, (owner, sorted(missing))


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


def _load_refresh_method():
    tree = ast.parse((PACKAGE / "widget_robot_manual.py").read_text(encoding="utf-8"))
    method = _method(tree, "_applyStep6ControlReasons")
    namespace = {
        "REFRESH_CONTROLS": REFRESH_CONTROLS,
        "annotate_step6_controls": annotate_step6_controls,
        "Mapping": dict,
        "os": __import__("os"),
        "PhasePlan": type("PhasePlan", (), {}),
        "MotionPhase": SimpleNamespace(APPROACH=SimpleNamespace(value="approach"),
                                       DRILLING=SimpleNamespace(value="drilling")),
    }
    module = ast.fix_missing_locations(ast.Module(
        body=[ast.ClassDef(name="Mixin", bases=[], keywords=[], body=[method], decorator_list=[])],
        type_ignores=[],
    ))
    exec(compile(module, str(PACKAGE / "widget_robot_manual.py"), "exec"), namespace)
    return namespace["Mixin"]._applyStep6ControlReasons


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
    method = _load_refresh_method()
    host = _RefreshHost(logic=None)  # every logic-backed flag raises AttributeError
    before = {name: (w.enabled, w.visible) for name, w in vars(host.ui).items()}
    refresh = {"scene_prepared": True, "robot_present": False, "locked": False}
    with caplog.at_level(logging.ERROR):
        method(host, refresh)  # must not raise
    after = {name: (w.enabled, w.visible) for name, w in vars(host.ui).items()}
    assert after == before
    assert "Step 6 control reasons skipped for 6.1 refresh" in caplog.text


def test_refresh_annotation_writes_reasons_when_flags_compute(caplog):
    method = _load_refresh_method()
    logic = SimpleNamespace(
        isRobotBaseTransformNode=lambda node: False,
        robotWorkspaceModelNode=lambda: None,
    )
    host = _RefreshHost(logic=logic)
    with caplog.at_level(logging.ERROR):
        method(host, {"scene_prepared": True, "robot_present": False, "locked": False})
    assert host.ui.loadRobotModelButton.enabled is False  # the gate itself is untouched
    assert host.ui.loadRobotModelButton.toolTip.startswith("Load.\n\n" + PREFIX)
    assert host.ui.frameRobotButton.toolTip == "Frame."
    assert "skipped" not in caplog.text
