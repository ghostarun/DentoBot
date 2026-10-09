"""Accept Base clears the restore's pending Base notice (S6-MULTI-JAW-STALE-01, live run 2026-10-09).

Live finding (evidence: S6-MULTI-JAW-STALE-01-20261009T164748Z, B-FDI34-v5b-branch.json): the restore wrote
"The Base is not accepted yet: press Accept Base ..." into the branch configuration status. A successful
Accept Base then locked the Base, but the status kept that sentence. The restore is the only writer of the
notice, and nothing re-derived the status when the Base became accepted.

The checks extract the real ``onLockRobotBaseMount`` (widget_robot.py) and the real
``_refreshStep6WorkingConfigurationStatus`` / ``_step6WorkingConfigurationSummary`` (widget_step6_branch_config.py)
from source. The collaborators are fakes with the same return shapes: the facade results, the branch record
and the status label. No Slicer, Qt or ROS is used.
"""

import ast
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "DENTOWorkflow" / "Resources" / "Python" / "dentobot_workflow"
ROBOT_WIDGET = PY / "widget_robot.py"
BRANCH_WIDGET = PY / "widget_step6_branch_config.py"

PENDING = (
    "The Base is not accepted yet: press Accept Base (it needs the ROS robot or local fallback loaded)."
)
RESTORED_WITH_PENDING = (
    "Step 6 already matches this branch's saved configuration: Opening 40.0 mm; Base origin (-117.2, 34.7, 175.2) mm; "
    "default planner, 5 attempt(s) / 5.0 s; Task Home not saved. " + PENDING
)


def _extract(path: Path, class_name: str, names: set, namespace: dict) -> dict:
    """Compile the named methods of ``class_name`` from ``path`` (decorators dropped) into ``namespace``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    found = {}
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            node.decorator_list = []
            module = ast.Module(body=[node], type_ignores=[])
            exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
            found[node.name] = namespace[node.name]
    missing = names - set(found)
    assert not missing, f"methods not found in {path.name}: {sorted(missing)}"
    return found


def _namespace():
    errors = []
    return {
        "_": lambda text: text,
        "logging": SimpleNamespace(exception=lambda *a, **k: None),
        "slicer": SimpleNamespace(util=SimpleNamespace(errorDisplay=lambda message: errors.append(message))),
        "__errors__": errors,
    }


def _extract_module_function(path: Path, name: str, namespace: dict) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(path), "exec"), namespace)


ROBOT_NS = _namespace()
BRANCH_NS = _namespace()
# The status summary uses the approved barrier defaults from mouth_portal (pure Python, no Slicer).
sys.path.insert(0, str(PY.parent))
from dentobot_workflow import mouth_portal  # noqa: E402

BRANCH_NS["DEFAULT_BARRIER_TUNING"] = mouth_portal.DEFAULT_BARRIER_TUNING
_extract_module_function(BRANCH_WIDGET, "_barrierTuningSummary", BRANCH_NS)


def _load_methods():
    # widget_robot.py's class is a mixin; find it by the method name, whatever its class is.
    tree = ast.parse(ROBOT_WIDGET.read_text(encoding="utf-8"))
    owner = next(
        node for node in tree.body if isinstance(node, ast.ClassDef)
        and any(isinstance(item, ast.FunctionDef) and item.name == "onLockRobotBaseMount" for item in node.body)
    )
    robot = _extract(ROBOT_WIDGET, owner.name, {"onLockRobotBaseMount"}, ROBOT_NS)
    owner_b = next(
        node for node in ast.parse(BRANCH_WIDGET.read_text(encoding="utf-8")).body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(item, ast.FunctionDef) and item.name == "_refreshStep6WorkingConfigurationStatus"
                for item in node.body)
    )
    branch = _extract(BRANCH_WIDGET, owner_b.name,
                      {"_refreshStep6WorkingConfigurationStatus", "_step6WorkingConfigurationSummary"}, BRANCH_NS)
    return robot, branch


ROBOT_METHODS, BRANCH_METHODS = _load_methods()


class FakePanel:
    def __init__(self, text):
        self.branchConfigStatusLabel = SimpleNamespace(text=text)
        self.reconcileManualBaseStateButton = SimpleNamespace(enabled=False)

    def showBranchConfigStatus(self, text, state="status"):
        self.branchConfigStatusLabel.text = str(text)


class FakeLogic:
    def __init__(self, record):
        self._record = record

    def step6WorkingConfiguration(self, node, branch_id=None):
        return self._record


class FakeFacade:
    def __init__(self, *, accept=None, lock=None):
        self._accept = accept
        self._lock = lock
        self.calls = []

    def acceptManualBaseReview(self):
        self.calls.append("accept")
        return self._accept

    def lockBase(self):
        self.calls.append("lock")
        return self._lock


def _result(success, message):
    return SimpleNamespace(success=success, message=message, code="test", details={})


RECORD = {
    "config": {
        "mouth_opening_mm": 40.0,
        "base_world_mm": [[1, 0, 0, -117.231], [0, 1, 0, 34.704], [0, 0, 1, 175.195], [0, 0, 0, 1]],
        "planner_id": "",
        "planning_attempts": 5,
        "planning_time_sec": 5.0,
        "task_home_si": None,
    }
}


class FakeWidget:
    """The methods the real ``onLockRobotBaseMount`` and refresh call, with the restore's status in the panel."""

    def __init__(self, *, manual_review, facade_results, status_text=RESTORED_WITH_PENDING):
        self._parameterNode = SimpleNamespace(robotBaseTransform=None)
        self.logic = FakeLogic(RECORD)
        self._robotWorkflowFacade = FakeFacade(**facade_results)
        self._robotSimulationPanel = FakePanel(status_text)
        self._manual_review = manual_review
        self.planning_messages = []
        self.refreshes = 0
        self._step6WorkingConfigurationSummary = BRANCH_METHODS["_step6WorkingConfigurationSummary"]

    # The real refresh is bound to the fake self below; these are the collaborators it does not own.
    def _isStep6RobotWorkflowActive(self):
        return self._manual_review

    def _isStep6ManualBaseReviewActive(self):
        return self._manual_review

    def _updateStep6PlanningUi(self, message="", error=False):
        self.planning_messages.append((message, error))

    def _updateRobotPlacement(self):
        return None

    def _isStep3BActive(self):
        return False

    def _captureCaseFoundationSessionSnapshot(self):
        return None

    def _refreshStep6WorkingConfigurationStatus(self):
        self.refreshes += 1
        BRANCH_METHODS["_refreshStep6WorkingConfigurationStatus"](self)

    def onLockRobotBaseMount(self, checked=False):
        return ROBOT_METHODS["onLockRobotBaseMount"](self, checked)

    @property
    def status_text(self):
        return self._robotSimulationPanel.branchConfigStatusLabel.text


def _widget(**kwargs):
    ROBOT_NS["__errors__"].clear()
    return FakeWidget(**kwargs)


def test_successful_accept_base_on_the_review_path_replaces_the_pending_notice():
    widget = _widget(manual_review=True,
                     facade_results={"accept": _result(True, "Base accepted."), "lock": None})
    assert PENDING in widget.status_text
    widget.onLockRobotBaseMount()
    assert widget.refreshes == 1
    assert PENDING not in widget.status_text
    assert "not accepted yet" not in widget.status_text
    assert widget.status_text.startswith("Saved for this branch: Opening 40.0 mm; Base origin (-117.2, 34.7, 175.2) mm;")
    assert widget._robotWorkflowFacade.calls == ["accept"]
    assert widget.planning_messages == [("Base accepted.", False)]


def test_successful_lock_base_path_replaces_the_pending_notice():
    widget = _widget(manual_review=False,
                     facade_results={"accept": None, "lock": _result(True, "Base locked.")})
    widget.onLockRobotBaseMount()
    assert widget.refreshes == 1
    assert "not accepted yet" not in widget.status_text
    assert widget._robotWorkflowFacade.calls == ["lock"]


def test_a_refused_accept_leaves_the_status_and_reports_the_error():
    widget = _widget(manual_review=True,
                     facade_results={"accept": _result(False, "Base candidate is not current."), "lock": None})
    widget.onLockRobotBaseMount()
    assert widget.refreshes == 0
    assert widget.status_text == RESTORED_WITH_PENDING
    assert ROBOT_NS["__errors__"] == ["Base candidate is not current."]
    assert widget.planning_messages == [("Base candidate is not current.", True)]


def test_a_refused_lock_leaves_the_status_and_reports_the_error():
    widget = _widget(manual_review=False,
                     facade_results={"accept": None, "lock": _result(False, "No robot loaded.")})
    widget.onLockRobotBaseMount()
    assert widget.refreshes == 0
    assert widget.status_text == RESTORED_WITH_PENDING
    assert ROBOT_NS["__errors__"] == ["No robot loaded."]


def test_the_refresh_reports_the_saved_record_not_a_stale_restore_sentence():
    widget = _widget(manual_review=True,
                     facade_results={"accept": _result(True, "Base accepted."), "lock": None})
    widget.onLockRobotBaseMount()
    summary = BRANCH_METHODS["_step6WorkingConfigurationSummary"](RECORD)
    assert widget.status_text == "Saved for this branch: " + summary
