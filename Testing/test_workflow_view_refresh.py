import ast
from pathlib import Path
from types import SimpleNamespace


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_navigation.py"
)


def _refresh_method():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    widget_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "WorkflowNavigationWidgetMixin"
    )
    method = next(
        node
        for node in widget_class.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_refreshWorkflowViewAfterStateChange"
    )
    namespace = {}
    code = compile(
        ast.Module(body=[method], type_ignores=[]),
        str(SOURCE),
        "exec",
    )
    exec(code, namespace)
    return namespace[method.name]


def test_refresh_enforces_step6_separation_without_view_snapshot():
    calls = []
    widget = SimpleNamespace(
        ui=SimpleNamespace(
            workflowStageComboBox=SimpleNamespace(currentIndex=3),
        ),
        _workflowViewPriorState=None,
        _updateWorkflowViewControls=lambda: calls.append("controls"),
        _enforceStep6OpenedJawDisplaySeparation=lambda: calls.append(
            "separation"
        ),
    )

    _refresh_method()(widget)

    assert calls == ["controls", "separation"]


def test_refresh_keeps_early_inspection_stage_path():
    calls = []
    widget = SimpleNamespace(
        ui=SimpleNamespace(
            workflowStageComboBox=SimpleNamespace(currentIndex=2),
        ),
        _displayInspectionContext=lambda: calls.append("inspection"),
        _updateWorkflowViewControls=lambda: calls.append("controls"),
        _enforceStep6OpenedJawDisplaySeparation=lambda: calls.append(
            "separation"
        ),
    )

    _refresh_method()(widget)

    assert calls == ["inspection"]
