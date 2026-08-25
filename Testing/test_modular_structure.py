import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "DENTOWorkflow" / "DENTOWorkflow.py"
PACKAGE = ROOT / "DENTOWorkflow" / "Resources" / "Python" / "dentobot_workflow"
MANIFEST = ROOT / "Testing" / "contracts" / "dentoworkflow_api.json"

MIXIN_OWNERS = {
    "BootstrapWidgetMixin": "DENTOWorkflowWidget",
    "ApplicationWidgetMixin": "DENTOWorkflowWidget",
    "WorkflowPanelsWidgetMixin": "DENTOWorkflowWidget",
    "LifecycleWidgetMixin": "DENTOWorkflowWidget",
    "SegmentationWidgetMixin": "DENTOWorkflowWidget",
    "TrajectoryViewWidgetMixin": "DENTOWorkflowWidget",
    "PlanningFocusWidgetMixin": "DENTOWorkflowWidget",
    "DockingWidgetMixin": "DENTOWorkflowWidget",
    "PlanningWidgetMixin": "DENTOWorkflowWidget",
    "GuideSupportSetupWidgetMixin": "DENTOWorkflowWidget",
    "GuideSupportWidgetMixin": "DENTOWorkflowWidget",
    "TemplateBuildWidgetMixin": "DENTOWorkflowWidget",
    "TemplateFinalizationWidgetMixin": "DENTOWorkflowWidget",
    "GuideBuildWidgetMixin": "DENTOWorkflowWidget",
    "CaseBackendWidgetMixin": "DENTOWorkflowWidget",
    "RobotShellWidgetMixin": "DENTOWorkflowWidget",
    "RobotPlacementWidgetMixin": "DENTOWorkflowWidget",
    "RobotSceneWidgetMixin": "DENTOWorkflowWidget",
    "RobotWidgetMixin": "DENTOWorkflowWidget",
    "ViewCatalogWidgetMixin": "DENTOWorkflowWidget",
    "ViewControlsWidgetMixin": "DENTOWorkflowWidget",
    "ViewCompositionWidgetMixin": "DENTOWorkflowWidget",
    "WorkflowNavigationWidgetMixin": "DENTOWorkflowWidget",
    "ViewerWidgetMixin": "DENTOWorkflowWidget",
    "LogicConstantsMixin": "DENTOWorkflowLogic",
    "CoreLogicMixin": "DENTOWorkflowLogic",
    "BackendLogicMixin": "DENTOWorkflowLogic",
    "DisplayLogicMixin": "DENTOWorkflowLogic",
    "SegmentationLogicMixin": "DENTOWorkflowLogic",
    "LineageLogicMixin": "DENTOWorkflowLogic",
    "PlanningDependencyLogicMixin": "DENTOWorkflowLogic",
    "WorkflowLogicMixin": "DENTOWorkflowLogic",
    "GuideSupportLogicMixin": "DENTOWorkflowLogic",
    "PatientShellLogicMixin": "DENTOWorkflowLogic",
    "DockingLogicMixin": "DENTOWorkflowLogic",
    "GuideLogicMixin": "DENTOWorkflowLogic",
    "FinalizationLogicMixin": "DENTOWorkflowLogic",
    "CaseBundleLogicMixin": "DENTOWorkflowLogic",
    "PhantomSceneLogicMixin": "DENTOWorkflowLogic",
    "Step6SceneLogicMixin": "DENTOWorkflowLogic",
    "RobotPlacementLogicMixin": "DENTOWorkflowLogic",
    "RobotSceneSyncLogicMixin": "DENTOWorkflowLogic",
    "RobotLogicMixin": "DENTOWorkflowLogic",
    "DENTOWorkflowTestMixin": "DENTOWorkflowTest",
}


def _classes(path: Path):
    return [
        node
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.ClassDef)
    ]


def _method_contract(node: ast.ClassDef) -> dict:
    result = {}
    for child in node.body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        result[child.name] = {
            "arguments": ast.unparse(child.args),
            "returns": ast.unparse(child.returns) if child.returns else "",
            "decorators": [ast.unparse(item) for item in child.decorator_list],
        }
    return result


def test_modularized_public_api_matches_verified_baseline():
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))["classes"]
    actual = {name: {} for name in expected}
    annotated_fields = {name: [] for name in expected}
    sources = [ENTRYPOINT, *sorted(PACKAGE.glob("*.py"))]
    for source in sources:
        for node in _classes(source):
            owner = MIXIN_OWNERS.get(node.name, node.name)
            if owner not in actual:
                continue
            for method_name, contract in _method_contract(node).items():
                assert method_name not in actual[owner], (
                    f"duplicate {owner}.{method_name} in {source}"
                )
                actual[owner][method_name] = contract
            if node.name == owner:
                annotated_fields[owner].extend(
                    child.target.id
                    for child in node.body
                    if isinstance(child, ast.AnnAssign)
                    and isinstance(child.target, ast.Name)
                )
    for class_name, contract in expected.items():
        for method_name, method_contract in contract["methods"].items():
            assert actual[class_name].get(method_name) == method_contract
        assert set(contract["annotated_fields"]).issubset(
            annotated_fields[class_name]
        )


def test_domain_mixins_do_not_import_the_public_entrypoint():
    for source in PACKAGE.glob("*.py"):
        if source.name in {"runtime.py", "slicer_tests.py"}:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "DENTOWorkflow", source
            elif isinstance(node, ast.Import):
                assert all(alias.name != "DENTOWorkflow" for alias in node.names), source


def test_all_internal_modules_are_installed_by_cmake():
    cmake = (ROOT / "DENTOWorkflow" / "CMakeLists.txt").read_text(
        encoding="utf-8"
    )
    for source in PACKAGE.glob("*.py"):
        relative = source.relative_to(ROOT / "DENTOWorkflow").as_posix()
        assert relative in cmake, relative


def test_active_workflow_modules_stay_within_context_budget():
    """Keep routine implementation files cheap to inspect in agent sessions."""

    assert len(ENTRYPOINT.read_text(encoding="utf-8").splitlines()) <= 500
    exemptions = {"runtime.py", "slicer_tests.py"}
    for source in PACKAGE.glob("*.py"):
        if source.name in exemptions:
            continue
        line_count = len(source.read_text(encoding="utf-8").splitlines())
        assert line_count <= 1500, f"{source.name}: {line_count} lines"


def test_domain_modules_add_no_process_or_network_boundary():
    forbidden_roots = {
        "multiprocessing",
        "requests",
        "socket",
        "subprocess",
        "threading",
        "urllib",
    }
    for source in PACKAGE.glob("*.py"):
        if source.name in {"runtime.py", "slicer_tests.py"}:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.partition(".")[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.partition(".")[0])
        assert imported_roots.isdisjoint(forbidden_roots), source
