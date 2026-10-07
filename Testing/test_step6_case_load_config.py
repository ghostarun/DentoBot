"""Case-load-only restore/connect routing for S6-MULTI-JAW-STALE-01 Step A.

The widget checks extract the real mixin methods and run them against small
fakes. No Slicer, ROS, MoveIt, planner, or robot process is started here.
"""

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

from dentobot_workflow import step6_working_config as wc  # noqa: E402

BRANCH_WIDGET = PY / "dentobot_workflow" / "widget_step6_branch_config.py"
CASE_WIDGET = PY / "dentobot_workflow" / "widget_case_backend.py"
BASE = [[1, 0, 0, 10.0], [0, 1, 0, 20.0], [0, 0, 1, 30.0], [0, 0, 0, 1]]
HOME = {"link-1_Revolute-1": 0.1, "link-2_Slider-2": 0.02}


def _record(**changes):
    config = {
        "mouth_opening_mm": 42.0,
        "base_world_mm": BASE,
        "task_home_si": HOME,
        "planner_id": "RRTConnectkConfigDefault",
        "planning_attempts": 5,
        "planning_time_sec": 5.0,
        "corridor_margin_samples": 0,
        "allow_spindle_guide_contact": False,
    }
    config.update(changes)
    return {
        "branch_id": "guide-a",
        "branch_foundation_fingerprint": "foundation-a",
        "config": config,
    }


def _method_nodes(path, names, class_name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    found = {
        node.name: node
        for node in owner.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    }
    assert set(found) == set(names), f"missing methods: {set(names) - set(found)}"
    return found


def _widget_mixins():
    methods = _method_nodes(
        BRANCH_WIDGET,
        {
            "onImportStep6PlanningContext",
            "onRestoreStep6WorkingConfiguration",
            "_offerStep6WorkingConfigurationRestore",
            "_restoreBranchConfigurationOnCaseLoad",
        },
        "Step6BranchConfigWidgetMixin",
    )
    tree = ast.fix_missing_locations(
        ast.Module(
            body=[
                ast.ClassDef(
                    name="Step6BranchConfigWidgetMixin",
                    bases=[],
                    keywords=[],
                    body=list(methods.values()),
                    decorator_list=[],
                )
            ],
            type_ignores=[],
        )
    )
    slicer = SimpleNamespace(
        util=SimpleNamespace(
            confirmYesNoDisplay=lambda *args, **kwargs: True,
            errorDisplay=lambda *args, **kwargs: None,
        )
    )
    namespace = {
        "_": lambda value: value,
        "json": json,
        "math": math,
        "slicer": slicer,
        "step6_working_config": wc,
    }
    exec(compile(tree, str(BRANCH_WIDGET), "exec"), namespace)
    mixin = namespace["Step6BranchConfigWidgetMixin"]
    restore = mixin.onRestoreStep6WorkingConfiguration

    def tracked_restore(self, *args, **kwargs):
        self.events.append("restore")
        return restore(self, *args, **kwargs)

    mixin.onRestoreStep6WorkingConfiguration = tracked_restore
    return mixin, slicer


class _Control:
    def __init__(self, events, joint):
        self.events = events
        self.joint = joint
        self.values = []

    def setValue(self, value):
        self.events.append(("stage_home", self.joint, value))
        self.values.append(value)


class _Panel:
    def __init__(self, events):
        self.manualJogJointControls = {
            joint: (None, _Control(events, joint)) for joint in HOME
        }

    def showBranchConfigStatus(self, *args, **kwargs):
        pass

    def setPlanningPolicy(self, *args, **kwargs):
        pass


class _Facade:
    def __init__(self, harness):
        self.harness = harness
        self.policy = {
            "planner_id": "RRTConnectkConfigDefault",
            "planning_attempts": 5,
            "planning_time_sec": 5.0,
        }

    def jointPlanningPolicy(self):
        return dict(self.policy)

    def approachCorridorMarginSamples(self):
        return 0

    def setJointPlanningPolicy(self, planner, attempts, seconds):
        if self.harness.fail_policy:
            raise ValueError("policy apply failed after earlier restore work")
        self.policy = {
            "planner_id": planner,
            "planning_attempts": attempts,
            "planning_time_sec": seconds,
        }

    def setApproachCorridorMarginSamples(self, samples):
        pass

    def clearTransientState(self):
        pass

    def isRos2MotionControlActive(self, *args, **kwargs):
        return False

    def connect(self, *args, **kwargs):
        raise AssertionError("branch restore must use the shell Connect owner")

    def moveJoints(self, *args, **kwargs):
        raise AssertionError("restoring a saved Task Home must not move the robot")


class _Logic:
    def __init__(self, harness):
        self.harness = harness

    def step6WorkingConfiguration(self, node):
        return self.harness.record

    def evaluatePreparedBranchEligibility(self, node):
        return dict(self.harness.eligibility)

    def importStep6PlanningContext(self, node):
        self.harness.events.append("import")
        if self.harness.fail_import:
            raise ValueError("planning-context import failed")
        node.step6PlanningContextImported = True
        return SimpleNamespace(message="planning context imported")

    def isRos2MotionControlActive(self, *args, **kwargs):
        return False

    def createOrUpdateStep6CaseJawOpening(self, node):
        self.harness.events.append("opening")


_MIXIN, _SLICER = _widget_mixins()


class _Widget(_MIXIN):
    def __init__(self, *, stage=None, imported=False, record=None):
        self.events = []
        self.record = _record() if record is None else record
        self.current_config = self.record
        self.eligibility = {
            "reason": "VALID",
            "message": "",
            "branch_id": "guide-a",
            "branch": {"branch_foundation_fingerprint": "foundation-a"},
        }
        self.fail_import = False
        self.fail_policy = False
        self._parameterNode = SimpleNamespace(
            step6PlanningContextImported=imported,
            step6CaseJawTargetGapMm=42.0,
            robotBaseTransform=object(),
            robotBaseMountLocked=True,
            step6AllowSpindleGuideContact=False,
        )
        self.logic = _Logic(self)
        self._robotWorkflowFacade = _Facade(self)
        self._robotSimulationPanel = _Panel(self.events)
        self.ui = SimpleNamespace(
            workflowStageComboBox=SimpleNamespace(currentIndex=4 if stage is None else stage)
        )
        self._caseBundleRobotProfileCompatible = True
        self._workflowActionBusy = False
        self._updatingFromParameterNode = False
        self._step6WorkingConfigurationRestoreSucceeded = False

    def _workflowStageEntries(self):
        return [(str(index), object()) for index in range(5)]

    def _currentStep6WorkingConfiguration(self):
        return self.current_config

    def _step6WorkingConfigurationSummary(self, record):
        return "saved config"

    def _refreshStep6WorkingConfigurationStatus(self):
        pass

    def _onShellConnectRobot(self):
        self.events.append("shell_connect")
        return True

    def _applyTaskJointLimitsToJointSpinboxes(self):
        pass

    def _applyStep6RecommendedView(self):
        pass

    def onFrameStep6CaseScene(self):
        pass

    def _confirmStep6SceneSwitch(self, scope):
        return True

    def _updateStep6PlanningUi(self, *args, **kwargs):
        pass

    def _updateStep6CaseJawOpeningControls(self):
        pass

    def _updateRobotPlacement(self):
        pass

    def _onSetSpindleGuideContact(self, enabled):
        pass

    def _onStep6ReviewManualTaskHome(self, *args, **kwargs):
        raise AssertionError("manual restore must not review Task Home")

    def _onStep6AcceptManualTaskHomeReview(self, *args, **kwargs):
        raise AssertionError("manual restore must not accept Task Home")

    def _onShellMoveRobot(self, *args, **kwargs):
        raise AssertionError("branch restore must not move the robot")


def _restore_and_connect(widget):
    return widget._restoreBranchConfigurationOnCaseLoad()


def test_case_load_imports_restores_stages_equal_home_then_uses_shell_connect():
    widget = _Widget(imported=False)

    assert _restore_and_connect(widget) is True
    assert widget.events.index("import") < widget.events.index("restore") < widget.events.index("shell_connect")
    staged = [event for event in widget.events if isinstance(event, tuple) and event[0] == "stage_home"]
    assert {event[1] for event in staged} == set(HOME)
    assert widget._step6WorkingConfigurationRestoreSucceeded is True


def test_case_load_skips_reimport_when_context_is_already_imported():
    widget = _Widget(imported=True)

    assert _restore_and_connect(widget) is True
    assert "import" not in widget.events
    assert widget.events.index("restore") < widget.events.index("shell_connect")


@pytest.mark.parametrize(
    "change",
    [
        lambda widget: setattr(widget.ui.workflowStageComboBox, "currentIndex", 3),
        lambda widget: setattr(widget, "_caseBundleRobotProfileCompatible", False),
        lambda widget: setattr(widget, "_caseBundleRobotProfileCompatible", None),
        lambda widget: setattr(widget, "_caseBundleRobotProfileCompatible", 1),
        lambda widget: setattr(widget, "_workflowActionBusy", True),
        lambda widget: setattr(widget, "record", None),
        lambda widget: setattr(widget, "eligibility", {"reason": "STEP5C_MISMATCH", "message": "stale"}),
        lambda widget: setattr(widget, "eligibility", {"reason": "UNKNOWN", "message": "unknown"}),
        lambda widget: setattr(widget, "_parameterNode", None),
        lambda widget: setattr(widget, "logic", None),
        lambda widget: setattr(widget, "_robotWorkflowFacade", None),
        lambda widget: setattr(widget, "_robotSimulationPanel", None),
    ],
    ids=[
        "earlier-stage", "incompatible-profile", "unknown-profile", "truthy-non-bool-profile", "busy", "missing-config",
        "invalid-branch", "unknown-eligibility", "missing-node", "missing-logic",
        "missing-facade", "missing-panel",
    ],
)
def test_case_load_gates_do_not_restore_or_connect(change):
    widget = _Widget(imported=False)
    change(widget)

    assert _restore_and_connect(widget) is False
    assert "restore" not in widget.events
    assert "shell_connect" not in widget.events


def test_case_load_import_failure_never_restores_or_connects():
    widget = _Widget(imported=False)
    widget.fail_import = True

    assert _restore_and_connect(widget) is False
    assert "import" in widget.events
    assert "restore" not in widget.events
    assert "shell_connect" not in widget.events


def test_case_load_binding_or_partial_restore_failure_cannot_reuse_old_success():
    invalid = _Widget(imported=True, record={**_record(), "branch_id": "another-branch"})
    invalid._step6WorkingConfigurationRestoreSucceeded = True
    assert _restore_and_connect(invalid) is False
    assert invalid._step6WorkingConfigurationRestoreSucceeded is False
    assert "restore" in invalid.events and "shell_connect" not in invalid.events

    changed = _record(mouth_opening_mm=41.0)
    partial = _Widget(imported=True, record=changed)
    partial.current_config = _record(mouth_opening_mm=42.0)
    partial._step6WorkingConfigurationRestoreSucceeded = True
    partial.fail_policy = True
    assert _restore_and_connect(partial) is False
    assert "opening" in partial.events
    assert partial._step6WorkingConfigurationRestoreSucceeded is False
    assert "shell_connect" not in partial.events


def test_equal_config_manual_restore_stages_home_without_connecting():
    widget = _Widget(imported=True)

    widget.onRestoreStep6WorkingConfiguration()

    assert widget._step6WorkingConfigurationRestoreSucceeded is True
    assert any(event[0] == "stage_home" for event in widget.events if isinstance(event, tuple))
    assert "shell_connect" not in widget.events


def test_missing_home_control_fails_restore_and_case_load_stays_disconnected():
    widget = _Widget(imported=True)
    widget._robotSimulationPanel.manualJogJointControls.pop(next(iter(HOME)))
    widget._step6WorkingConfigurationRestoreSucceeded = True

    assert _restore_and_connect(widget) is False
    assert widget._step6WorkingConfigurationRestoreSucceeded is False
    assert "shell_connect" not in widget.events


def test_manual_import_confirmation_and_restore_never_auto_connect_or_accept_home():
    widget = _Widget(imported=False)
    saved = _record(planner_id="RRTstar")
    widget.record = saved
    widget.current_config = _record(planner_id="RRTConnectkConfigDefault")

    widget.onImportStep6PlanningContext()

    assert "import" in widget.events
    assert "restore" in widget.events
    assert not any(event == "shell_connect" for event in widget.events)
    assert any(isinstance(event, tuple) and event[0] == "stage_home" for event in widget.events)


def _call_name(call):
    node = call.func
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def test_manual_restore_source_stays_connect_free_and_case_load_uses_explicit_success():
    widget = ast.parse(BRANCH_WIDGET.read_text(encoding="utf-8"))
    owner = next(node for node in widget.body if isinstance(node, ast.ClassDef)
                 and node.name == "Step6BranchConfigWidgetMixin")
    methods = {node.name: node for node in owner.body if isinstance(node, ast.FunctionDef)}
    restore = methods["onRestoreStep6WorkingConfiguration"]
    restore_calls = {_call_name(node) for node in ast.walk(restore) if isinstance(node, ast.Call)}
    forbidden = {
        "self._onShellConnectRobot",
        "self._onStep6ReviewManualTaskHome",
        "self._onStep6AcceptManualTaskHomeReview",
        "self._onShellMoveRobot",
        "self.facade.connect",
        "facade.connect",
    }
    assert restore_calls.isdisjoint(forbidden)
    assert "manualJogJointControls" in ast.unparse(restore)
    restore_source = ast.get_source_segment(BRANCH_WIDGET.read_text(encoding="utf-8"), restore)
    assert "self._step6WorkingConfigurationRestoreSucceeded = False" in restore_source
    assert "self._step6WorkingConfigurationRestoreSucceeded = True" in restore_source

    auto = methods["_restoreBranchConfigurationOnCaseLoad"]
    auto_calls = [node for node in ast.walk(auto) if isinstance(node, ast.Call)]
    connect_calls = [node for node in auto_calls if _call_name(node) == "self._onShellConnectRobot"]
    restore_calls = [node for node in auto_calls if _call_name(node) == "self.onRestoreStep6WorkingConfiguration"]
    assert len(connect_calls) == len(restore_calls) == 1
    assert restore_calls[0].lineno < connect_calls[0].lineno
    auto_source = ast.get_source_segment(BRANCH_WIDGET.read_text(encoding="utf-8"), auto)
    assert "_step6WorkingConfigurationRestoreSucceeded" in auto_source
    assert "_caseBundleRobotProfileCompatible" in auto_source
    assert "_workflowActionBusy" in auto_source
    assert "workflowStageComboBox" in auto_source

    manual_import = methods["onImportStep6PlanningContext"]
    manual_names = {_call_name(node) for node in ast.walk(manual_import) if isinstance(node, ast.Call)}
    assert "self._offerStep6WorkingConfigurationRestore" in manual_names
    assert "self._restoreBranchConfigurationOnCaseLoad" not in manual_names


def test_shared_case_load_hook_runs_after_teardown_finalization_and_research_adoption():
    source = CASE_WIDGET.read_text(encoding="utf-8")
    tree = ast.parse(source)
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                 and node.name == "CaseBackendWidgetMixin")
    methods = {node.name: node for node in owner.body if isinstance(node, ast.FunctionDef)}
    open_case = methods["_openCaseBundle"]

    def line_for(predicate):
        matches = [node.lineno for node in ast.walk(open_case) if predicate(node)]
        assert matches, "required case-load step is missing"
        return min(matches)

    teardown_line = line_for(
        lambda node: isinstance(node, ast.Call) and _call_name(node) == "self._endCaseBundleRestore"
    )
    compatibility_assignments = [
        node.lineno for node in ast.walk(open_case)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and target.attr == "_caseBundleRobotProfileCompatible"
            for target in node.targets
        )
    ]
    assert compatibility_assignments
    compatibility_line = max(compatibility_assignments)
    adoption_line = line_for(
        lambda node: isinstance(node, ast.Call)
        and _call_name(node) == "self.logic.importResearchStep6WorkingConfigurations"
    )
    hook_line = line_for(
        lambda node: isinstance(node, ast.Call)
        and _call_name(node) == "self._restoreBranchConfigurationOnCaseLoad"
    )
    loaded_phase_line = line_for(
        lambda node: isinstance(node, ast.Call)
        and _call_name(node) == "phase"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "Case loaded"
    )
    assert teardown_line < compatibility_line < adoption_line < loaded_phase_line < hook_line

    # Both user-facing full-load routes share _openCaseBundle, so the same
    # guarded restore applies to File and case-library loads.
    for name in ("onOpenCaseBundle", "_openLibraryFullCase"):
        route_calls = {_call_name(node) for node in ast.walk(methods[name]) if isinstance(node, ast.Call)}
        assert "self._openCaseBundle" in route_calls

    caller = methods["onOpenCaseBundle"]
    caller_source = ast.get_source_segment(source, caller)
    assert "isRos2MotionControlActive" in caller_source
    assert "if rosConnected:" in caller_source
    assert "ROS is connected." in caller_source
    assert caller_source.index("self._openCaseBundle(") < caller_source.index("caseBundleStatusLabel.text = message")
