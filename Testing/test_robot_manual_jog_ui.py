"""Pure host checks for the Step 6 manual jog controls and mirror gate."""

from __future__ import annotations

import ast
import json
import math
import sys
from collections.abc import Mapping, Sequence
from math import degrees, isfinite, radians
from pathlib import Path
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
ROBOT_MANUAL = PYTHON / "dentobot_workflow/widget_robot_manual.py"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))
from DENTOStep6State import (  # noqa: E402
    build_manual_simulation_record,
    parse_manual_simulation_record,
)
from DENTOStep6Planning import TaskSpaceRoi  # noqa: E402
from DENTOApplicationShell import workspace_for_stage  # noqa: E402
from DENTORobotPlacement import joint_positions_si_from_display  # noqa: E402

JOINT_NAMES = (
    "link-1_Revolute-1",
    "link-2_Slider-2",
    "link-3_Revolute-3",
    "link-4_Slider-4",
    "link-5_Revolute-5",
)


def _methods(path: Path, class_name: str, names: set[str], namespace: dict):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    selected = [
        node
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]
    assert {node.name for node in selected} == names
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(selected, type_ignores=[])),
            str(path),
            "exec",
        ),
        namespace,
    )
    return {name: namespace[name] for name in names}


def _method_node(path: Path, class_name: str, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def _class_constant(path: Path, class_name: str, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    assignment = next(
        node
        for node in cls.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    return ast.literal_eval(assignment.value)


def _attribute_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_attribute_name(node.value)}.{node.attr}"
    return ""


def _manual_record(label, events):
    identity = {
        name: f"{label}-{name}"
        for name in (
            "prepared_branch_id",
            "task_fingerprint",
            "base_fingerprint",
            "home_fingerprint",
            "trajectory_fingerprint",
            "robot_profile_fingerprint",
            "scene_fingerprint",
        )
    }
    return build_manual_simulation_record(identity=identity, events=events)


def _manual_record_export_harness(tmp_path, completed, active):
    destination = tmp_path / "manual-simulation-records.json"
    dialog_calls = []
    errors = []
    qt_stub = SimpleNamespace(
        QFileDialog=SimpleNamespace(
            getSaveFileName=lambda *_args: (
                dialog_calls.append(True)
                or (str(destination), "JSON files (*.json)")
            )
        )
    )
    slicer_stub = SimpleNamespace(
        util=SimpleNamespace(
            mainWindow=lambda: None,
            errorDisplay=lambda message: errors.append(str(message)),
        )
    )
    export = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {"_onStep6ExportManualRecord"},
        {
            "Path": Path,
            "json": json,
            "Mapping": Mapping,
            "qt": qt_stub,
            "slicer": slicer_stub,
            "_": str,
            "parse_manual_simulation_record": parse_manual_simulation_record,
        },
    )["_onStep6ExportManualRecord"]

    class Panel:
        def __init__(self):
            self.status = ("error", "Guard status: rejected — collision.")
            self.evidence = {"lastGuardFailure": "collision"}
            self.status_calls = 0
            self.export_status = None

        def setManualJogStatus(self, state, message, evidence=None):
            self.status_calls += 1
            self.status = (state, message)
            if evidence is not None:
                self.evidence = dict(evidence)

        def setManualRecordExportStatus(self, state, message):
            self.export_status = (state, message)

    class Facade:
        def manualSimulationCompletedRecords(self):
            return completed

        def manualSimulationRecord(self):
            return active

    panel = Panel()
    host = SimpleNamespace(
        _robotSimulationPanel=panel,
        _robotWorkflowFacade=Facade(),
    )
    return export, host, panel, destination, dialog_calls, errors


def _manual_record_import_harness(
    tmp_path, payload, *, path_result=(True, "shown"), previous_records=None
):
    source = tmp_path / "manual-simulation-records.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    dialog_calls = []
    errors = []
    cleared_paths = []
    shown_paths = []

    def show_path(record):
        shown_paths.append(record)
        return path_result

    qt_stub = SimpleNamespace(
        QFileDialog=SimpleNamespace(
            getOpenFileName=lambda *_args: (
                dialog_calls.append(True)
                or (str(source), "JSON files (*.json)")
            )
        )
    )
    slicer_stub = SimpleNamespace(
        util=SimpleNamespace(
            mainWindow=lambda: None,
            errorDisplay=lambda message: errors.append(str(message)),
        )
    )
    namespace = {
        "json": json,
        "Mapping": Mapping,
        "qt": qt_stub,
        "slicer": slicer_stub,
        "_": str,
        "parse_manual_simulation_record": parse_manual_simulation_record,
        "clear_manual_simulation_record_paths": lambda: cleared_paths.append(True),
        "show_manual_simulation_record_paths": show_path,
    }
    methods = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {
            "_onStep6ImportManualRecord",
            "_onStep6ShowManualRecord",
            "_onStep6ClearManualRecord",
        },
        namespace,
    )

    class Panel:
        def __init__(self):
            self.import_status = None
            self.records = previous_records
            self.previewApproachButton = SimpleNamespace(enabled=False)
            self.previewDrillingButton = SimpleNamespace(enabled=False)
            self.approachPlanningButton = SimpleNamespace(enabled=False)
            self.drillingPlanningButton = SimpleNamespace(enabled=False)

        def setManualRecordImportStatus(self, state, message):
            self.import_status = (state, message)

        def setManualSimulationRecords(self, records):
            self.records = tuple(records)

        def clearManualSimulationRecords(self):
            self.records = ()

    class Facade:
        def __init__(self):
            self.calls = []

        def __getattr__(self, name):
            def unexpected(*_args, **_kwargs):
                self.calls.append(name)
                raise AssertionError(f"historical UI must not call facade.{name}")

            return unexpected

    panel = Panel()
    facade = Facade()
    host = SimpleNamespace(_robotSimulationPanel=panel, _robotWorkflowFacade=facade)
    for name, method in methods.items():
        setattr(host, name, method.__get__(host, type(host)))
    return (
        host,
        panel,
        source,
        dialog_calls,
        errors,
        cleared_paths,
        shown_paths,
        facade,
    )


class _Control:
    def __init__(self, value=0):
        self.value = value
        self.minimum = 0.0
        self.maximum = 10000.0
        self.enabled = True
        self._signals_blocked = False

    def blockSignals(self, blocked):
        self._signals_blocked = bool(blocked)

    def setRange(self, minimum, maximum):
        self.minimum, self.maximum = float(minimum), float(maximum)
        self.setValue(self.value)

    def setValue(self, value):
        self.value = min(self.maximum, max(self.minimum, float(value)))

    def style(self):
        return self

    def unpolish(self, _widget):
        pass

    def polish(self, _widget):
        pass

    def setProperty(self, _key, _value):
        pass


class _PresentationControl(_Control):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.toolTip = ""
        self.visible = True

    def setText(self, text):
        self.text = str(text)

    def setToolTip(self, text):
        self.toolTip = str(text)

    def setVisible(self, visible):
        self.visible = bool(visible)


class _TwoDecimalSpinBox(_Control):
    """Faithful host stand-in for the jog QDoubleSpinBox display precision."""

    decimals = 2

    def setRange(self, minimum, maximum):
        self.minimum, self.maximum = float(minimum), float(maximum)
        self.setValue(self.value)

    def setValue(self, value):
        bounded = min(self.maximum, max(self.minimum, float(value)))
        rounded = round(bounded, self.decimals)
        self.value = min(self.maximum, max(self.minimum, rounded))


def _joint_limits(ranges):
    return SimpleNamespace(
        **{
            f"joint_{index}": SimpleNamespace(minimum=low, maximum=high)
            for index, (low, high) in enumerate(ranges, start=1)
        }
    )


def _manual_jog_presentation_controls():
    return {
        joint: {
            field: _PresentationControl()
            for field in ("comparison", "lower", "upper", "notice", "details")
        }
        for joint in JOINT_NAMES
    }


def test_manual_jog_joint_presentation_compares_accepted_state_and_keeps_draft_visible():
    methods = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        {"_updateManualJogJointPresentation"},
        {
            "JOINT_NAMES": JOINT_NAMES,
            "degrees": degrees,
            "isfinite": isfinite,
            "Mapping": Mapping,
        },
    )
    panel = type("PanelProbe", (), methods)()
    units = ("deg", "mm", "deg", "mm", "deg")
    accepted_display = (10.0, 2.0, -20.0, -1.0, 5.0)
    draft_display = (12.0, 1.0, -23.0, 1.5, 9.0)
    accepted = {
        joint: radians(value) if unit == "deg" else value / 1000.0
        for joint, value, unit in zip(
            JOINT_NAMES, accepted_display, units, strict=True
        )
    }
    mechanical = (
        (-30.0, 30.0),
        (-8.0, 8.0),
        (-40.0, 40.0),
        (-5.0, 5.0),
        (-50.0, 50.0),
    )
    reviewed = (
        (-20.0, 20.0),
        (-3.0, 3.0),
        (-30.0, 30.0),
        (-4.0, 4.0),
        (-45.0, 45.0),
    )
    panel._manualJogJointPresentation = _manual_jog_presentation_controls()
    panel.manualJogJointControls = {
        joint: (_Control(), _PresentationControl(), _PresentationControl())
        for joint in JOINT_NAMES
    }
    panel._manualJogDisplayValues = draft_display
    panel._manualJogAcceptedJointPositionsSi = accepted
    panel._manualJogSliderRanges = reviewed
    panel._manualJogMechanicalLimits = mechanical
    panel._manualJogLimits = (reviewed, reviewed)
    panel._manualJogLimitsValid = True
    panel._manualJogCommandLimitsValid = True
    panel._manualJogAvailable = True
    panel._manualJogDraftInitialized = False
    panel._manualJogBusy = False
    panel._taskHomeSetupMode = "connected"
    panel.manualJogReconciliationRequired = False
    action_calls = []
    panel._invoke = lambda *args, **kwargs: action_calls.append((args, kwargs))

    panel._updateManualJogJointPresentation()
    for joint in JOINT_NAMES:
        comparison = panel._manualJogJointPresentation[joint]["comparison"]
        assert comparison.text == "Draft unavailable"
        assert "not been initialized" in comparison.toolTip
        assert "Δ" not in comparison.text

    panel._manualJogDraftInitialized = True
    panel._updateManualJogJointPresentation()

    comparisons = [
        panel._manualJogJointPresentation[joint]["comparison"].text
        for joint in JOINT_NAMES
    ]
    for text, accepted_value, delta, unit in zip(
        comparisons,
        accepted_display,
        (2.0, -1.0, -3.0, 2.5, 4.0),
        units,
        strict=True,
    ):
        assert f"Accepted {accepted_value:.2f} {unit}" in text
        assert f"{delta:+.2f} {unit}" in text
    for index, (joint, unit, bounds) in enumerate(
        zip(JOINT_NAMES, units, reviewed, strict=True), start=1
    ):
        lower, upper = bounds
        presentation = panel._manualJogJointPresentation[joint]
        assert unit in presentation["lower"].text
        assert f"{lower:.2f}" in presentation["lower"].text
        assert f"{upper:.2f}" in presentation["upper"].text
        detail = presentation["details"].text.lower()
        assert f"j{index}" in detail
        assert "mechanical" in detail
        assert "reviewed" in detail
        assert "command" in detail

    panel._manualJogDisplayValues = (25.0, *draft_display[1:])
    panel.manualJogJointControls[JOINT_NAMES[0]][1].value = 25.0
    panel._updateManualJogJointPresentation()
    notice = panel._manualJogJointPresentation[JOINT_NAMES[0]]["notice"]
    assert notice.text == "Outside slider range; draft retained."
    assert notice.visible
    assert panel.manualJogJointControls[JOINT_NAMES[0]][1].value == 25.0
    assert panel._manualJogAcceptedJointPositionsSi == accepted
    assert action_calls == []

    def expect_unavailable(expected, reason):
        panel._updateManualJogJointPresentation()
        for joint in JOINT_NAMES:
            comparison = panel._manualJogJointPresentation[joint]["comparison"]
            assert comparison.text == expected
            assert reason in comparison.toolTip.lower()
            assert "Δ" not in comparison.text

    panel._taskHomeSetupMode = "offline"
    expect_unavailable("Accepted — offline", "offline")
    panel._taskHomeSetupMode = "unknown"
    expect_unavailable("Accepted unavailable", "unknown")
    panel._taskHomeSetupMode = "connected"
    panel._manualJogBusy = True
    expect_unavailable("Accepted — pending", "guarded jog")
    panel._manualJogBusy = False
    panel.manualJogReconciliationRequired = True
    expect_unavailable("Accepted — uncertain", "reconciliation")
    panel.manualJogReconciliationRequired = False
    panel._manualJogAcceptedJointPositionsSi = None
    expect_unavailable("Accepted unavailable", "accepted")
    panel._manualJogAcceptedJointPositionsSi = {
        **accepted,
        "extra-joint": 0.0,
    }
    expect_unavailable("Accepted unavailable", "invalid")
    panel._manualJogAcceptedJointPositionsSi = {
        **accepted,
        JOINT_NAMES[0]: math.nan,
    }
    expect_unavailable("Accepted unavailable", "invalid")

    panel._manualJogAcceptedJointPositionsSi = accepted
    panel._manualJogAvailable = False
    panel._manualJogDraftInitialized = True
    panel._manualJogSliderRanges = ()
    panel._manualJogMechanicalLimits = None
    panel._manualJogLimits = None
    panel._manualJogLimitsValid = False
    panel._manualJogCommandLimitsValid = False
    panel._updateManualJogJointPresentation()
    # Limits unavailable does not erase a previously initialized numeric draft.
    assert panel._manualJogDisplayValues[0] == 25.0
    for joint in JOINT_NAMES:
        presentation = panel._manualJogJointPresentation[joint]
        assert presentation["lower"].text == "--"
        assert presentation["upper"].text == "--"
        assert "-20.00" not in presentation["details"].text
        assert "20.00" not in presentation["details"].text


def test_manual_jog_availability_accepts_taskless_current_identity_and_fails_closed():
    method = _methods(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        {"_manualJogIdentityCurrent"},
        {},
    )["_manualJogIdentityCurrent"]
    parameter_node = object()
    observed = []
    facade = SimpleNamespace(
        _manual_jog_current_identity=lambda node: (
            observed.append(node) or {"task": "unconfirmed:current-identity"}
        )
    )
    host = SimpleNamespace(_robotWorkflowFacade=facade, _parameterNode=parameter_node)

    assert method(host) is True
    assert observed == [parameter_node]

    def stale_identity(_node):
        raise ValueError("task, branch, base, Home, limits, or scene identity changed")

    facade._manual_jog_current_identity = stale_identity
    assert method(host) is False
    assert method(SimpleNamespace(_robotWorkflowFacade=None)) is False


def test_manual_jog_planning_refresh_follows_connect_sync_and_draft_checks():
    shell = PYTHON / "dentobot_workflow/widget_robot_shell.py"
    handlers = {
        "_onShellConnectRobot": _method_node(
            shell, "RobotShellWidgetMixin", "_onShellConnectRobot"
        ),
        "_onShellSyncCollisionScene": _method_node(
            ROBOT_MANUAL, "RobotManualWidgetMixin", "_onShellSyncCollisionScene"
        ),
        "_onShellCheckManualRobotDraftState": _method_node(
            ROBOT_MANUAL,
            "RobotManualWidgetMixin",
            "_onShellCheckManualRobotDraftState",
        ),
    }

    def line_of_call(method, name):
        return next(
            node.lineno
            for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == name
        )

    def line_clearing_busy(method):
        return next(
            node.lineno
            for node in ast.walk(method)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Attribute)
                and target.attr == "_workflowActionBusy"
                for target in node.targets
            )
            and isinstance(node.value, ast.Constant)
            and node.value.value is False
        )

    for name in ("_onShellConnectRobot", "_onShellCheckManualRobotDraftState"):
        assert line_of_call(handlers[name], "_updateStep6PlanningUi") > line_clearing_busy(
            handlers[name]
        )
    sync = handlers["_onShellSyncCollisionScene"]
    assert line_of_call(sync, "_updateStep6PlanningUi") > line_of_call(
        sync, "syncPlanningScene"
    )

    planning_ui = _method_node(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        "_updateStep6PlanningUi",
    )
    availability = next(
        node
        for node in ast.walk(planning_ui)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "setManualJogAvailability"
    )
    jog_available = next(
        keyword.value
        for keyword in availability.keywords
        if keyword.arg == "jog_available"
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_manualJogIdentityCurrent"
        for node in ast.walk(jog_available)
    )


def test_manual_jog_numeric_drafts_use_mechanical_bounds_and_gate_reviewed_limits():
    def to_si(j1, j2, j3, j4, j5):
        return {
            JOINT_NAMES[0]: radians(j1),
            JOINT_NAMES[1]: j2 / 1000.0,
            JOINT_NAMES[2]: radians(j3),
            JOINT_NAMES[3]: j4 / 1000.0,
            JOINT_NAMES[4]: radians(j5),
        }

    names = {
        "setManualJogLimits",
        "setManualJogAvailability",
        "_updateManualJogResetLabel",
        "_updateManualJogKeyboardControlState",
        "resetManualJogDraft",
        "_setManualJogDraftValues",
        "_onManualJogSliderChanged",
        "_onManualJogNumericChanged",
        "_updateManualJogDraftFromControls",
        "manualJogJointPositionsSi",
        "_updateManualJogJointPresentation",
        "setManualJogAcceptedState",
        "_formatManualJogDisplayValues",
        "_setManualJogStatus",
    }
    methods = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        names,
        {
            "JOINT_NAMES": JOINT_NAMES,
            "Mapping": Mapping,
            "degrees": degrees,
            "isfinite": isfinite,
            "joint_positions_si_from_display": to_si,
        },
    )
    panel_type = type("PanelProbe", (), methods)
    panel = panel_type()
    panel.manualJogJointControls = {
        name: (_Control(), _Control(), _Control()) for name in JOINT_NAMES
    }
    panel._manualJogJointPresentation = _manual_jog_presentation_controls()
    for index, (joint, unit) in enumerate(
        zip(JOINT_NAMES, ("deg", "mm", "deg", "mm", "deg"), strict=True),
        start=1,
    ):
        panel.manualJogJointControls[joint][2].text = f"J{index} ({unit})"
    panel.manualJogAcceptedStateLabel = _Control()
    panel.taskHomeCurrentStateLabel = _Control()
    panel.taskHomeCandidateLabel = _Control()
    panel.manualJogDraftLimitLabel = _Control()
    panel._manualJogLimits = {}
    panel._manualJogMechanicalLimits = None
    panel._manualJogAvailable = True
    panel._taskHomeSetupMode = "connected"
    panel._taskHomeConfigurationReady = False
    panel._taskHomeConfiguredJointPositionsSi = None
    panel._manualJogControlsInHomeGroup = False
    panel._manualJogLocalJointPositionsSi = None
    panel._manualJogGuardContextAvailable = True
    panel._manualJogCommandLimitsValid = False
    panel._manualJogBusy = False
    panel._manualJogDraftInitialized = False
    panel._manualJogDisplayValues = (0.0,) * 5
    panel._manualJogAcceptedJointPositionsSi = None
    panel._manualJogEvidence = None
    panel.resetManualJogDraftButton = _Control()
    panel.checkManualDraftStateButton = _Control()
    panel.reconcileManualJogButton = _Control()
    panel.guardedManualJogButton = _Control()
    panel.manualJogReconciliationRequired = False
    panel._manualJogGuardAvailable = True
    panel.manualJogDraftStateLabel = _Control()
    panel.manualJogStatusLabel = _Control()
    ghost_updates = []
    panel._invoke = lambda action, state: ghost_updates.append((action, state))

    mechanical = _joint_limits(
        ((-180, 180), (-5, 5), (-90, 90), (-3, 3), (-180, 180))
    )
    reviewed = _joint_limits(
        ((-90, 100), (-2, 4), (-45, 60), (-2, 2), (-170, 170))
    )
    panel.setManualJogLimits(mechanical, reviewed)

    units = ("deg", "mm", "deg", "mm", "deg")
    for index, (joint, unit) in enumerate(
        zip(JOINT_NAMES, units, strict=True), start=1
    ):
        assert panel.manualJogJointControls[joint][2].text == f"J{index} ({unit})"
        detail = panel._manualJogJointPresentation[joint]["details"].text.lower()
        assert f"j{index}" in detail
        assert "mechanical" in detail
        assert "reviewed" in detail
        assert "command" in detail

    assert panel._manualJogLimits[0] == (
        (-90.0, 100.0),
        (-2.0, 4.0),
        (-45.0, 60.0),
        (-2.0, 2.0),
        (-170.0, 170.0),
    )
    assert panel.manualJogJointControls[JOINT_NAMES[0]][1].minimum == -180.0
    assert panel.manualJogJointControls[JOINT_NAMES[0]][1].maximum == 180.0

    _slider, j1, _label = panel.manualJogJointControls[JOINT_NAMES[0]]
    panel.setManualJogAvailability(True, True)
    j1.setValue(120.0)
    panel._onManualJogNumericChanged(JOINT_NAMES[0], j1.value)
    assert j1.value == 120.0
    assert panel.manualJogJointControls[JOINT_NAMES[0]][0].value == 10000
    assert panel.checkManualDraftStateButton.enabled
    assert not panel.guardedManualJogButton.enabled
    assert "J1 120.00 deg exceeds reviewed task maximum 100.00 deg" in (
        panel.manualJogDraftLimitLabel.text
    )
    assert "Check Draft State remains available" in panel.manualJogDraftLimitLabel.text
    assert ghost_updates[-1][0] == "manual_draft_changed"

    narrower_reviewed = _joint_limits(
        ((-80, 90), (-2, 4), (-45, 60), (-2, 2), (-170, 170))
    )
    panel.setManualJogLimits(mechanical, narrower_reviewed)
    assert j1.value == 120.0
    assert panel.checkManualDraftStateButton.enabled
    assert not panel.guardedManualJogButton.enabled

    panel._onManualJogSliderChanged(JOINT_NAMES[3], 0)
    assert panel.manualJogJointControls[JOINT_NAMES[3]][1].value == -2.0
    assert set(panel.manualJogJointPositionsSi()) == set(JOINT_NAMES)
    assert len(ghost_updates) == 3
    assert all(action == "manual_draft_changed" for action, _state in ghost_updates)

    panel.setManualJogAcceptedState(
        {
            JOINT_NAMES[0]: radians(10),
            JOINT_NAMES[1]: 0.003,
            JOINT_NAMES[2]: radians(-20),
            JOINT_NAMES[3]: 0.0015,
            JOINT_NAMES[4]: radians(30),
        }
    )
    assert "J1 10.00 deg" in panel.taskHomeCurrentStateLabel.text
    assert "J2 3.00 mm" in panel.taskHomeCurrentStateLabel.text
    assert "J5 30.00 deg" in panel.taskHomeCurrentStateLabel.text
    assert "five-DOF arm" in panel.taskHomeCurrentStateLabel.text
    assert "pneumatic_spindle" not in panel.taskHomeCurrentStateLabel.text
    panel.resetManualJogDraft()
    assert panel.manualJogJointControls[JOINT_NAMES[0]][1].value == 10.0
    assert panel.manualJogJointControls[JOINT_NAMES[3]][1].value == 1.5
    assert panel.guardedManualJogButton.enabled
    assert "within mechanical and reviewed task limits" in (
        panel.manualJogDraftLimitLabel.text
    )
    panel.setManualJogAcceptedState({})
    assert panel._manualJogAcceptedJointPositionsSi is None
    assert "unavailable" in panel.taskHomeCurrentStateLabel.text

    panel._manualJogAcceptedJointPositionsSi = None
    incompatible = _joint_limits(
        ((200, 220), (-2, 4), (-45, 60), (-2, 2), (-170, 170))
    )
    panel.setManualJogLimits(mechanical, incompatible)
    panel.setManualJogAvailability(True, True)
    assert not panel.guardedManualJogButton.enabled
    assert panel.checkManualDraftStateButton.enabled


def test_manual_jog_mirrors_only_current_exact_guard_acceptance_and_keeps_failure_evidence():
    method = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {"_onShellGuardedManualJog"},
        {
            "JOINT_NAMES": JOINT_NAMES,
            "Mapping": Mapping,
            "isfinite": isfinite,
        },
    )["_onShellGuardedManualJog"]

    class Panel:
        def __init__(self):
            self.draft = {name: 0.0 for name in JOINT_NAMES}
            self.status = None
            self.evidence = None
            self.accepted = []
            self.pending = False
            self.manualJogReconciliationRequired = False

        def setManualJogStatus(self, state, message, evidence=None):
            self.status = (state, message)
            if evidence is not None:
                self.evidence = dict(evidence)
                if evidence.get("manualJogReconciliationRequired") is True:
                    self.manualJogReconciliationRequired = True

        def setManualJogRequestPending(self):
            self.pending = True

        def setManualJogRequestComplete(self):
            self.pending = False

        def setManualJogAcceptedState(self, positions):
            self.accepted.append(dict(positions))

    class Facade:
        def __init__(self, result, exception):
            self.result = result
            self.exception = exception
            self.calls = []

        def guardManualRobotJog(self, positions):
            self.calls.append(dict(positions))
            if self.exception:
                raise self.exception
            return self.result

    refresh_states = []

    def invoke(
        details,
        *,
        success=True,
        request=None,
        code="manual_jog_guard_unknown",
        exception=None,
        repeat=False,
    ):
        result = SimpleNamespace(
            success=success, message="guard evidence", details=details, code=code
        )
        request = request if request is not None else {
            name: float(index) for index, name in enumerate(JOINT_NAMES)
        }
        panel = Panel()
        panel.draft = dict(request)
        facade = Facade(result, exception)
        mirrors = []
        host = type("ShellProbe", (), {"_onShellGuardedManualJog": method})()
        host._robotSimulationPanel = panel
        host._robotWorkflowFacade = facade
        host._workflowActionBusy = False
        host._updateStep6PlanningUi = lambda: refresh_states.append(
            host._workflowActionBusy
        )
        host._setRobotJointsFromSi = lambda positions, *, publish_to_ros: (
            mirrors.append((dict(positions), publish_to_ros)) or (True, "")
        )
        host._onShellGuardedManualJog(request)
        if repeat:
            host._onShellGuardedManualJog(request)
        return panel, facade, mirrors

    requested = {name: float(index) for index, name in enumerate(JOINT_NAMES)}
    accepted_details = {
        "identityStatus": "current",
        "guardAccepted": True,
        "acceptedJointPositionsSi": dict(requested),
        "monitoredStateStatus": "current",
    }
    panel, facade, mirrors = invoke(accepted_details)
    assert facade.calls == [requested]
    assert mirrors == [(requested, False)]
    assert panel.accepted == [requested]
    assert panel.draft == requested
    assert panel.status[0] == "ok"
    assert panel.evidence == accepted_details
    assert refresh_states[-1] is False

    pending_details = {
        **accepted_details,
        "monitoredStateStatus": "not_converged",
    }
    panel, _facade, mirrors = invoke(pending_details)
    assert mirrors == [(requested, False)]
    assert panel.accepted == [requested]
    assert panel.status[0] == "ok"
    assert "Monitored-state status: not_converged." in panel.status[1]
    assert panel.evidence == pending_details

    for details, success in (
        ({**accepted_details, "identityStatus": "stale"}, True),
        (
            {
                **accepted_details,
                "acceptedJointPositionsSi": {**requested, JOINT_NAMES[0]: 9.0},
            },
            True,
        ),
        ({"identityStatus": "current", "guardAccepted": False}, False),
        ({"identityStatus": "unknown", "guardAccepted": None}, False),
    ):
        panel, _facade, mirrors = invoke(details, success=success)
        assert mirrors == []
        assert panel.accepted == []
        assert panel.draft == requested
        assert panel.status[0] in {"error", "blocked"}
        assert panel.evidence == details

    unknown_details = {
        "identityStatus": "unknown",
        "guardAccepted": None,
        "monitoredStateStatus": "not_converged",
    }
    panel, _facade, mirrors = invoke(unknown_details, success=False)
    assert mirrors == []
    assert panel.accepted == []
    assert panel.draft == requested
    assert "confirmed accepted state shown" in panel.status[1]
    assert "simulated robot may have advanced" in panel.status[1]
    assert "stop jogging until reconciled" in panel.status[1]
    assert "accepted robot is unchanged" not in panel.status[1]

    pre_submit_details = {
        "identityStatus": "unknown",
        "guardAccepted": None,
        "rawGuardOutcome": "not_submitted",
        "manualJogReconciliationRequired": False,
    }
    panel, facade, mirrors = invoke(
        pre_submit_details, success=False, repeat=True
    )
    assert facade.calls == [requested, requested]
    assert mirrors == []
    assert "no jog was submitted" in panel.status[1]
    assert "state was not changed by this request" in panel.status[1]
    assert "simulated robot may have advanced" not in panel.status[1]
    assert not panel.manualJogReconciliationRequired

    panel, _facade, mirrors = invoke(
        {},
        success=False,
        exception=RuntimeError("reply was lost"),
        repeat=True,
    )
    assert mirrors == []
    assert panel.accepted == []
    assert panel.draft == requested
    assert "confirmed accepted state shown" in panel.status[1]
    assert "simulated robot may have advanced" in panel.status[1]
    assert "stop jogging until reconciled" in panel.status[1]
    assert panel.manualJogReconciliationRequired
    assert _facade.calls == [requested]

    flagged = {**unknown_details, "manualJogReconciliationRequired": True}
    panel, _facade, mirrors = invoke(flagged, success=False)
    assert mirrors == []
    assert panel.accepted == []
    assert panel.draft == requested
    assert panel.status[0] == "blocked"
    assert "reconciliation is required" in panel.status[1]

    panel, _facade, mirrors = invoke(
        unknown_details,
        success=False,
        code="manual_jog_reconciliation_required",
    )
    assert mirrors == []
    assert panel.accepted == []
    assert panel.draft == requested
    assert panel.status[0] == "blocked"
    assert panel.evidence["manualJogReconciliationRequired"] is True

    invalid_request = {**requested, "unexpected_joint": 0.0}
    panel, facade, mirrors = invoke({}, request=invalid_request)
    assert facade.calls == []
    assert mirrors == []
    assert panel.accepted == []
    assert "no jog was submitted" in panel.status[1]


def test_manual_jog_native_evidence_is_visible_finite_and_locks_jog():
    methods = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        {
            "setManualJogAvailability",
            "setManualJogStatus",
            "_updateManualJogJointPresentation",
            "_updateManualJogKeyboardControlState",
            "_formatManualJogNativeEvidence",
            "_formatManualJogDisplayValues",
            "_setManualJogStatus",
        },
        {
            "JOINT_NAMES": JOINT_NAMES,
            "Mapping": Mapping,
            "isfinite": math.isfinite,
            "degrees": degrees,
        },
    )
    panel_type = type("PanelProbe", (), methods)
    panel = panel_type()
    mechanical = (
        (-180, 180),
        (-5, 5),
        (-90, 90),
        (-3, 3),
        (-180, 180),
    )
    panel._manualJogLimits = (mechanical, mechanical)
    panel._manualJogSliderRanges = mechanical
    panel._manualJogMechanicalLimits = mechanical
    panel._manualJogLimitsValid = True
    panel._manualJogCommandLimitsValid = True
    panel._taskHomeSetupMode = "connected"
    panel._taskHomeConfigurationReady = False
    panel._taskHomeConfiguredJointPositionsSi = None
    panel._manualJogAvailable = True
    panel._manualJogGuardAvailable = True
    panel._manualJogGuardContextAvailable = True
    panel._manualJogBusy = False
    panel._manualJogDraftInitialized = True
    panel._manualJogAcceptedJointPositionsSi = dict.fromkeys(JOINT_NAMES, 0.0)
    panel._manualJogDisplayValues = (1.0, 2.0, 3.0, 4.0, 5.0)
    panel.manualJogReconciliationRequired = False
    panel.manualJogJointControls = {
        joint: (_Control(), _Control(value), _Control())
        for joint, value in zip(JOINT_NAMES, panel._manualJogDisplayValues, strict=True)
    }
    panel._manualJogJointPresentation = _manual_jog_presentation_controls()
    panel.resetManualJogDraftButton = _Control()
    panel.checkManualDraftStateButton = _Control()
    panel.reconcileManualJogButton = _Control()
    panel.guardedManualJogButton = _Control()
    panel.manualJogDraftLimitLabel = _Control()
    panel.manualJogStatusLabel = _Control()
    panel._manualJogEvidence = None

    evidence = {
        "manualJogReconciliationRequired": True,
        "monitoredStateStatus": "not_converged",
        "nativeGuardEvidence": {
            "firstBody": "arm_link_4",
            "secondBody": "case_surface",
            "minimumClearanceM": 0.00125,
            "minimumSelfDistanceM": 0.0025,
            "minimumWorldDistanceM": 0.00475,
        },
    }
    panel._updateManualJogJointPresentation()
    assert "Δ" in panel._manualJogJointPresentation[JOINT_NAMES[0]]["comparison"].text
    panel.setManualJogStatus("blocked", "Reconciliation required.", evidence)
    comparison = panel._manualJogJointPresentation[JOINT_NAMES[0]]["comparison"]
    assert comparison.text == "Accepted — uncertain"
    assert "reconciliation" in comparison.toolTip.lower()
    assert "first body: arm_link_4" in panel.manualJogStatusLabel.text
    assert "second body: case_surface" in panel.manualJogStatusLabel.text
    assert "required clearance: 0.00125 m" in panel.manualJogStatusLabel.text
    assert "measured self distance: 0.0025 m" in panel.manualJogStatusLabel.text
    assert "measured world distance: 0.00475 m" in panel.manualJogStatusLabel.text
    assert "monitored state: not_converged" in panel.manualJogStatusLabel.text
    assert panel.manualJogReconciliationRequired

    panel.setManualJogAvailability(True, True)
    assert not panel.guardedManualJogButton.enabled
    assert panel.checkManualDraftStateButton.enabled
    assert panel.reconcileManualJogButton.enabled

    unavailable = panel._formatManualJogNativeEvidence(
        {
            "monitoredStateStatus": "",
            "nativeGuardEvidence": {
                "firstBody": "",
                "secondBody": None,
                "minimumClearanceM": math.nan,
                "minimumSelfDistanceM": math.inf,
            },
        }
    )
    assert "first body: unavailable" in unavailable
    assert "second body: unavailable" in unavailable
    assert "required clearance: unavailable" in unavailable
    assert "measured self distance: unavailable" in unavailable
    assert "measured world distance: unavailable" in unavailable
    assert "monitored state: unavailable" in unavailable
    assert panel._formatManualJogNativeEvidence(
        {"manualJogReconciliationRequired": True}
    ) == ""
    assert panel._formatManualJogNativeEvidence(
        {
            "nativeGuardEvidence": None,
            "monitoredStateStatus": "unavailable/unknown",
        }
    ) == ""


def test_reconcile_button_only_mirrors_a_successful_query_and_preserves_draft():
    shell_path = PYTHON / "dentobot_workflow/widget_robot_shell.py"
    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    method = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {"_onShellReconcileManualRobotJog"},
        {"JOINT_NAMES": JOINT_NAMES, "Mapping": Mapping, "isfinite": isfinite},
    )["_onShellReconcileManualRobotJog"]
    panel_source = panel_path.read_text(encoding="utf-8")
    shell_source = shell_path.read_text(encoding="utf-8")
    assert '"reconcile_manual_jog": 3' in panel_source
    assert "self.reconcileManualJogButton.clicked.connect(" in panel_source
    assert '"reconcile_manual_jog": self._onShellReconcileManualRobotJog' in shell_source

    draft = {name: float(index + 1) for index, name in enumerate(JOINT_NAMES)}
    accepted = {name: float(index) for index, name in enumerate(JOINT_NAMES)}
    details = {
        "identityStatus": "current",
        "monitoredStateStatus": "matched",
        "manualJogReconciliationRequired": False,
        "collisionStatus": "invalid",
        "acceptedJointPositionsSi": accepted,
        "nativeGuardEvidence": {
            "responseCorrelated": True,
            "operation": "state_query",
            "queryOnly": True,
        },
    }

    class Panel:
        def __init__(self):
            self.manualJogReconciliationRequired = True
            self.draft = dict(draft)
            self.accepted = []
            self.status = None
            self.pending = False

        def setManualJogRequestPending(self):
            self.pending = True

        def setManualJogRequestComplete(self):
            self.pending = False

        def setManualJogAcceptedState(self, positions, *, preserve_draft=False):
            self.accepted.append((dict(positions), preserve_draft))

        def setManualJogStatus(self, state, message, evidence=None):
            self.status = (state, message)
            if evidence is not None and "manualJogReconciliationRequired" in evidence:
                self.manualJogReconciliationRequired = (
                    evidence["manualJogReconciliationRequired"] is True
                )

    class Facade:
        def __init__(self, result):
            self.result = result
            self.calls = 0

        def reconcileManualRobotJog(self):
            self.calls += 1
            return self.result

    refresh_states = []

    def invoke(result):
        panel = Panel()
        facade = Facade(result)
        mirrors = []
        host = type("ShellProbe", (), {"_onShellReconcileManualRobotJog": method})()
        host._robotSimulationPanel = panel
        host._robotWorkflowFacade = facade
        host._workflowActionBusy = False
        host._updateStep6PlanningUi = lambda: refresh_states.append(
            host._workflowActionBusy
        )
        host._setRobotJointsFromSi = lambda positions, *, publish_to_ros: (
            mirrors.append((dict(positions), publish_to_ros)) or (True, "")
        )
        host._onShellReconcileManualRobotJog()
        return panel, facade, mirrors

    success = SimpleNamespace(
        success=True,
        code="manual_jog_reconciled",
        message="state reconciled",
        details=details,
    )
    panel, facade, mirrors = invoke(success)
    assert facade.calls == 1
    assert mirrors == [(accepted, False)]
    assert panel.accepted == [(accepted, True)]
    assert panel.draft == draft
    assert not panel.manualJogReconciliationRequired
    assert "Static collision validity: invalid" in panel.status[1]
    assert refresh_states[-1] is False

    failure = SimpleNamespace(
        success=False,
        code="manual_jog_reconciliation_monitor_mismatch",
        message="monitored state mismatch",
        details={"manualJogReconciliationRequired": True},
    )
    panel, facade, mirrors = invoke(failure)
    assert facade.calls == 1
    assert mirrors == []
    assert panel.accepted == []
    assert panel.draft == draft
    assert panel.manualJogReconciliationRequired
    assert not panel.pending


def test_manual_draft_state_check_is_read_only_and_marks_stale_results():
    shell_path = PYTHON / "dentobot_workflow/widget_robot_shell.py"
    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    check_method = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {"_onShellCheckManualRobotDraftState"},
        {"JOINT_NAMES": JOINT_NAMES, "Mapping": Mapping, "isfinite": isfinite},
    )["_onShellCheckManualRobotDraftState"]
    panel_methods = _methods(
        panel_path,
        "DENTORobotSimulationPanel",
        {"setManualDraftStateCheckResult"},
        {"Mapping": Mapping, "isfinite": isfinite},
    )
    panel_source = panel_path.read_text(encoding="utf-8")
    shell_source = shell_path.read_text(encoding="utf-8")
    assert '"check_manual_draft_state": 3' in panel_source
    assert "self.checkManualDraftStateButton.clicked.connect(" in panel_source
    assert '"check_manual_draft_state", self.manualJogJointPositionsSi()' in panel_source
    assert '"check_manual_draft_state": self._onShellCheckManualRobotDraftState' in shell_source

    requested = {name: float(index) for index, name in enumerate(JOINT_NAMES)}
    changed_draft = {**requested, JOINT_NAMES[0]: requested[JOINT_NAMES[0]] + 1.0}

    def invoke(details, *, changed=None):
        panel_type = type("PanelProbe", (), panel_methods)
        panel = panel_type()
        panel.currentDraft = dict(requested)
        panel.manualJogReconciliationRequired = True
        panel.manualJogDraftStateLabel = _Control()
        panel.manualJogDraftStateLabel.text = "Draft state: current ghost"
        panel.manualJogAcceptedStateLabel = _Control()
        panel.manualJogAcceptedStateLabel.text = "Accepted state: preserved"
        panel.manualDraftStateCheckStatusLabel = _Control()
        panel.manualJogJointPositionsSi = lambda: dict(panel.currentDraft)
        accepted_updates = []
        panel.setManualJogAcceptedState = lambda positions: accepted_updates.append(
            dict(positions)
        )

        result = SimpleNamespace(
            success=False,
            message="static evaluation returned",
            details=details,
        )

        class Facade:
            def __init__(self):
                self.check_calls = []
                self.jog_calls = []

            def checkManualRobotDraftState(self, positions):
                self.check_calls.append(dict(positions))
                if changed is not None:
                    panel.currentDraft = dict(changed)
                return result

            def guardManualRobotJog(self, positions):
                self.jog_calls.append(dict(positions))
                raise AssertionError("draft evaluation must never jog")

        facade = Facade()
        mirrors = []
        host = type("ShellProbe", (), {"_onShellCheckManualRobotDraftState": check_method})()
        host._robotSimulationPanel = panel
        host._robotWorkflowFacade = facade
        host._workflowActionBusy = False
        host._setRobotJointsFromSi = lambda *args, **kwargs: mirrors.append(
            (args, kwargs)
        )
        planning_refresh_busy = []
        host._updateStep6PlanningUi = lambda: planning_refresh_busy.append(
            host._workflowActionBusy
        )
        host._onShellCheckManualRobotDraftState(requested)
        return panel, facade, mirrors, accepted_updates, planning_refresh_busy

    failed = {
        "draftWithinCommandLimits": False,
        "limitAssessmentAuthoritative": True,
        "limitViolations": [
            {
                "jointLabel": "J1",
                "jointName": JOINT_NAMES[0],
                "limitSource": "reviewed_task",
                "bound": "maximum",
                "boundDisplayValue": 100.0,
                "candidateDisplayValue": 120.0,
                "unit": "deg",
                "margin": -20.0,
            }
        ],
        "manual_state_evaluation": {
            "status": "failed",
            "identity_status": "current",
            "target_endpoint_status": "off_target",
            "reason": "Static evaluator rejected the draft.",
            "endpoint_evaluation": {
                "static_state_validity": {
                    "status": "failed",
                    "message": "native collision",
                    "authoritative": True,
                },
                "position_residual_mm": 2.75,
                "drilling_axis_residual_deg": 8.0,
            },
        },
        "nativeGuardEvidence": {"reason": "raw guard returned collision."},
        "requestedJointPositionsSi": dict(requested),
        "simulationOnly": True,
        "routeAuthority": "none",
    }
    panel, facade, mirrors, accepted_updates, planning_refresh_busy = invoke(
        failed, changed=changed_draft
    )
    assert facade.check_calls == [requested]
    assert facade.jog_calls == []
    assert mirrors == []
    assert accepted_updates == []
    assert planning_refresh_busy == [False]
    assert panel.manualJogAcceptedStateLabel.text == "Accepted state: preserved"
    assert panel.manualJogDraftStateLabel.text == "Draft state: current ghost"
    assert panel._manualDraftStateCheckEvidence == failed
    assert panel._manualDraftStateCheckRequested == requested
    assert "Draft-state check: stale" in panel.manualDraftStateCheckStatusLabel.text
    assert "Static verdict: failed" in panel.manualDraftStateCheckStatusLabel.text
    assert "identity status: current" in panel.manualDraftStateCheckStatusLabel.text
    assert "endpoint status off_target" in panel.manualDraftStateCheckStatusLabel.text
    assert "position residual 2.75 mm" in panel.manualDraftStateCheckStatusLabel.text
    assert "drilling-axis residual 8 deg" in panel.manualDraftStateCheckStatusLabel.text
    assert "Evaluator: Static evaluator rejected the draft." in panel.manualDraftStateCheckStatusLabel.text
    assert "Static validity: native collision" in panel.manualDraftStateCheckStatusLabel.text
    assert "Native: raw guard returned collision." in panel.manualDraftStateCheckStatusLabel.text
    assert "Command limits: outside command limits; assessment authoritative." in (
        panel.manualDraftStateCheckStatusLabel.text
    )
    assert "J1 120.00 deg violates reviewed_task maximum 100.00 deg" in (
        panel.manualDraftStateCheckStatusLabel.text
    )
    assert "margin -20.00 deg" in panel.manualDraftStateCheckStatusLabel.text

    off_target = {
        "manual_state_evaluation": {
            "status": "passed",
            "identity_status": "current",
            "target_endpoint_status": "failed",
            "endpoint_evaluation": {
                "static_state_validity": {
                    "status": "passed",
                    "message": "static state clear",
                },
                "position_residual_mm": 5.0,
                "drilling_axis_residual_deg": 12.0,
            },
        }
    }
    off_target_panel, _facade, mirrors, _accepted_updates, _refreshes = invoke(
        off_target
    )
    assert mirrors == []
    assert "Static verdict: passed" in off_target_panel.manualDraftStateCheckStatusLabel.text
    assert "endpoint status failed" in off_target_panel.manualDraftStateCheckStatusLabel.text
    assert "position residual 5 mm" in off_target_panel.manualDraftStateCheckStatusLabel.text

    unknown, facade, mirrors, accepted_updates, _refreshes = invoke(
        {"manual_state_evaluation": {}}
    )
    assert facade.check_calls == [requested]
    assert facade.jog_calls == []
    assert mirrors == []
    assert accepted_updates == []
    assert "Static verdict: unknown" in unknown.manualDraftStateCheckStatusLabel.text
    assert "identity status: unknown" in unknown.manualDraftStateCheckStatusLabel.text
    assert "endpoint status unknown" in unknown.manualDraftStateCheckStatusLabel.text
    assert "position residual unavailable" in unknown.manualDraftStateCheckStatusLabel.text
    assert "drilling-axis residual unavailable" in unknown.manualDraftStateCheckStatusLabel.text


def test_workspace_generation_refreshes_planning_ui_after_busy_clears():
    events = []
    progress_instances = []

    class Label:
        def setProperty(self, _name, _value):
            pass

        def style(self):
            return self

        def unpolish(self, _label):
            pass

        def polish(self, _label):
            pass

    host = SimpleNamespace(
        _parameterNode=object(),
        logic=object(),
        _robotWorkflowFacade=SimpleNamespace(
            generateWorkspaceCloud=lambda **_kwargs: SimpleNamespace(
                success=True, message="generated", details={}
            )
        ),
        _workflowActionBusy=False,
        _step6TaskSpaceRoiDraft=lambda: ("roi", "source"),
        _robotSimulationPanel=SimpleNamespace(taskSpaceRoiStatusLabel=Label()),
    )

    class Progress:
        def __init__(self, _title):
            self.closed = False
            progress_instances.append(self)

        def update(self, *_args, **_kwargs):
            pass

        def close(self):
            events.append(("close", host._workflowActionBusy))
            self.closed = True

    def refresh(message="", error=False):
        events.append(
            ("refresh", host._workflowActionBusy, message, error, progress_instances[0].closed)
        )

    host._updateStep6PlanningUi = refresh
    host.ui = SimpleNamespace(
        robotWorkspaceStatusLabel=Label(),
        clearRobotWorkspaceButton=SimpleNamespace(enabled=False),
    )
    on_generate = _methods(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        {"onGenerateRobotWorkspace"},
        {
            "WorkflowProgress": Progress,
            "_": lambda message: message,
            "slicer": SimpleNamespace(
                util=SimpleNamespace(errorDisplay=lambda _message: None)
            ),
        },
    )["onGenerateRobotWorkspace"]

    on_generate(host)

    assert events == [
        ("close", True),
        ("refresh", False, "generated", False, True),
    ]
    assert host.ui.robotWorkspaceStatusLabel.text.startswith("generated")
    assert host.ui.clearRobotWorkspaceButton.enabled is True


def test_explicit_base_and_task_home_acceptance_use_the_facade_owners():
    base_accept = _methods(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        {"onLockRobotBaseMount"},
        {},
    )["onLockRobotBaseMount"]
    shell_methods = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {"_onStep6AcceptManualTaskHomeReview"},
        {
            "JOINT_NAMES": JOINT_NAMES,
            "Mapping": Mapping,
            "isfinite": isfinite,
        },
    )

    class Facade:
        def __init__(self):
            self.calls = []
            self.result = SimpleNamespace(
                success=True,
                message="accepted",
                details={
                    "identityStatus": "current",
                    "acceptanceStatus": "accepted",
                    "setupMode": "connected",
                    "acceptedJointPositionsSi": {
                        name: float(index)
                        for index, name in enumerate(JOINT_NAMES)
                    },
                },
            )

        def lockBase(self):
            self.calls.append("lockBase")
            return self.result

        def acceptManualTaskHomeReview(self):
            self.calls.append("acceptManualTaskHomeReview")
            return self.result

        def saveTaskHome(self):
            raise AssertionError("Task Home UI must use the review façade")

    facade = Facade()
    base_host = SimpleNamespace(
        _parameterNode=object(),
        logic=object(),
        _robotWorkflowFacade=facade,
        _isStep6RobotWorkflowActive=lambda: False,
        _captureCaseFoundationSessionSnapshot=lambda: None,
        _isStep3BActive=lambda: False,
        _updateStep6PlanningUi=lambda *_args, **_kwargs: None,
    )
    base_accept(base_host)

    home_mirrors = []
    home_host = SimpleNamespace(
        _robotWorkflowFacade=facade,
        _robotSimulationPanel=SimpleNamespace(
            setManualJogAcceptedState=lambda positions, **kwargs: home_mirrors.append(
                (dict(positions), kwargs)
            ),
            setManualTaskHomeReviewResult=lambda result: None,
        ),
        _updateStep6PlanningUi=lambda *_args, **_kwargs: None,
        _workflowActionBusy=False,
    )
    shell_methods["_onStep6AcceptManualTaskHomeReview"](home_host)

    assert facade.calls == ["lockBase", "acceptManualTaskHomeReview"]
    assert home_mirrors == [
        (
            facade.result.details["acceptedJointPositionsSi"],
            {"preserve_draft": True},
        )
    ]
    assert '"Accept Base"' in (
        PYTHON / "dentobot_workflow/widget_robot_shell.py"
    ).read_text(encoding="utf-8")
    panel_source = (PYTHON / "DENTORobotSimulationPanel.py").read_text(
        encoding="utf-8"
    )
    assert '"Review Draft as Task Home"' in panel_source
    assert '"Back to Edit / Cancel Review"' in panel_source
    assert '"Save Home Configuration"' in panel_source
    assert '"Accept and Validate Task Home"' in panel_source
    assert '"save_home"' not in panel_source
    assert '"save_home"' not in (
        PYTHON / "dentobot_workflow/widget_robot_shell.py"
    ).read_text(encoding="utf-8")

    class Matrix:
        values = (
            (1.0, 0.0, 0.0, 1.0),
            (0.0, 1.0, 0.0, 2.0),
            (0.0, 0.0, 1.0, 3.0),
        )

        def GetElement(self, row, column):
            return self.values[row][column]

    base_pose_methods = _methods(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        {"_syncManualBaseCandidateGhost", "_step6BasePoseEvidence"},
        {
            "Mapping": Mapping,
            "math": math,
            "vtk": SimpleNamespace(vtkMatrix4x4=Matrix),
            "_": str,
        },
    )
    base_pose_evidence = base_pose_methods["_step6BasePoseEvidence"]
    base = SimpleNamespace(GetMatrixTransformToWorld=lambda _matrix: None)
    logic = SimpleNamespace(
        isRobotBaseTransformNode=lambda node: node is base,
        robotBasePoseFingerprint=lambda _node: "0123456789abcdef",
        showManualBaseCandidateGhost=lambda _candidate: (True, "shown"),
        clearManualBaseCandidateGhost=lambda: None,
    )
    review_panel = SimpleNamespace(
        manualBaseReviewStatusLabel=SimpleNamespace(text=""),
        cancelManualBaseReviewButton=SimpleNamespace(enabled=False),
    )
    review_host = SimpleNamespace(
        _parameterNode=SimpleNamespace(robotBaseTransform=base),
        logic=logic,
        _robotSimulationPanel=review_panel,
    )
    review_host._syncManualBaseCandidateGhost = lambda result=None: (
        base_pose_methods["_syncManualBaseCandidateGhost"](review_host, result)
    )
    evidence = base_pose_evidence(review_host)
    assert "world RAS origin (1.000, 2.000, 3.000) mm" in evidence
    assert "pose fingerprint 0123456789ab" in evidence
    base_pose_evidence(
        review_host,
        SimpleNamespace(
            details={
                "staged": True,
                "identityStatus": "current",
                "candidateMatrixWorldRasMm": tuple(np.eye(4).reshape(-1)),
            }
        ),
    )
    assert "Staging alone leaves the accepted robot model and ROS scene unchanged" in (
        review_panel.manualBaseReviewStatusLabel.text
    )
    base_pose_evidence(
        review_host,
        SimpleNamespace(
            details={
                "staged": True,
                "identityStatus": "unknown",
                "candidateMatrixWorldRasMm": tuple(np.eye(4).reshape(-1)),
                "acceptanceStatus": "unknown",
                "acceptanceUncertainty": "native planning scene state unknown",
            }
        ),
    )
    assert "Native scene state is unverified" in review_panel.manualBaseReviewStatusLabel.text
    assert "blocked until runtime reconciliation" in review_panel.manualBaseReviewStatusLabel.text


def test_manual_base_candidate_ghost_refresh_shows_only_current_draft_and_clears():
    class Matrix:
        values = (
            (1.0, 0.0, 0.0, 1.0),
            (0.0, 1.0, 0.0, 2.0),
            (0.0, 0.0, 1.0, 3.0),
        )

        def GetElement(self, row, column):
            return self.values[row][column]

    methods = _methods(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        {"_syncManualBaseCandidateGhost", "_step6BasePoseEvidence"},
        {"Mapping": Mapping, "math": math, "vtk": SimpleNamespace(vtkMatrix4x4=Matrix), "_": str},
    )

    class Logic:
        def __init__(self):
            self.calls = []
            self.ghost = None
            self.local_models_available = True
            self.accepted_matrix = tuple(np.eye(4).reshape(-1))

        def isRobotBaseTransformNode(self, node):
            return node is base

        def robotBasePoseFingerprint(self, _node):
            return "accepted-base"

        def showManualBaseCandidateGhost(self, candidate):
            candidate = tuple(candidate)
            self.calls.append(("show", candidate))
            if not self.local_models_available:
                return False, "local robot models are unavailable"
            self.ghost = candidate
            return True, "shown"

        def clearManualBaseCandidateGhost(self):
            self.calls.append(("clear",))
            self.ghost = None

    base = SimpleNamespace(GetMatrixTransformToWorld=lambda _matrix: None)
    accepted_matrix = tuple(np.eye(4).reshape(-1))
    candidate = tuple(np.eye(4).reshape(-1) + np.array([0, 0, 0, 4] + [0] * 12))
    logic = Logic()
    panel = SimpleNamespace(
        manualBaseReviewStatusLabel=SimpleNamespace(text=""),
        cancelManualBaseReviewButton=SimpleNamespace(enabled=False),
    )

    class Host:
        _syncManualBaseCandidateGhost = methods["_syncManualBaseCandidateGhost"]
        _step6BasePoseEvidence = methods["_step6BasePoseEvidence"]

        def __init__(self):
            self._parameterNode = SimpleNamespace(robotBaseTransform=base)
            self.logic = logic
            self._robotSimulationPanel = panel

    host = Host()
    staged = SimpleNamespace(
        details={
            "staged": True,
            "identityStatus": "current",
            "candidateMatrixWorldRasMm": candidate,
            "acceptedMatrixWorldRasMm": accepted_matrix,
            "acceptanceStatus": "review",
        }
    )
    host._step6BasePoseEvidence(staged)
    assert logic.calls == [("show", candidate)]
    assert logic.ghost == candidate
    assert "Cyan translucent ghost" in panel.manualBaseReviewStatusLabel.text
    assert "solid robot shows the accepted Base" in panel.manualBaseReviewStatusLabel.text

    unknown = SimpleNamespace(
        details={
            **staged.details,
            "acceptanceStatus": "unknown",
            "acceptanceUncertainty": "native scene state unknown",
            "failureEvidence": {"lock": "acknowledgement unavailable"},
        }
    )
    host._step6BasePoseEvidence(unknown)
    assert logic.calls == [("show", candidate)]
    assert logic.ghost == candidate
    assert "may reflect an uncertain native state" in panel.manualBaseReviewStatusLabel.text
    assert "acknowledgement unavailable" in panel.manualBaseReviewStatusLabel.text

    base = SimpleNamespace(
        GetID=lambda: "vtkMRMLTransformNode2",
        GetMatrixTransformToWorld=lambda _matrix: None,
    )
    host._parameterNode = SimpleNamespace(
        GetID=lambda: "vtkMRMLScriptedModuleNode2",
        robotBaseTransform=base,
    )
    host._step6BasePoseEvidence(staged)
    assert logic.calls[-1] == ("show", candidate)
    assert logic.ghost == candidate

    logic.local_models_available = False
    unavailable_candidate = list(candidate)
    unavailable_candidate[3] += 1.0
    unavailable = host._step6BasePoseEvidence(
        SimpleNamespace(
            details={
                **staged.details,
                "candidateMatrixWorldRasMm": unavailable_candidate,
            }
        )
    )
    assert "Candidate visualization unavailable" in unavailable
    assert "local robot models are unavailable" in panel.manualBaseReviewStatusLabel.text
    assert "candidate remains unaccepted" in panel.manualBaseReviewStatusLabel.text
    assert logic.calls[-2] == ("show", tuple(unavailable_candidate))
    assert logic.calls[-1] == ("clear",)
    assert logic.ghost is None

    logic.local_models_available = True
    for status in (
        SimpleNamespace(
            details={
                "staged": False,
                "identityStatus": "current",
                "acceptanceStatus": "review",
            }
        ),
        SimpleNamespace(
            details={
                "staged": False,
                "identityStatus": "current",
                "acceptanceStatus": "accepted",
            }
        ),
        SimpleNamespace(
            details={
                "staged": True,
                "identityStatus": "case_changed",
                "candidateMatrixWorldRasMm": candidate,
            }
        ),
    ):
        host._step6BasePoseEvidence(staged)
        assert logic.ghost == candidate
        host._step6BasePoseEvidence(status)
        assert logic.calls[-1] == ("clear",)
        assert logic.ghost is None

    assert logic.accepted_matrix == accepted_matrix
    assert all(call[0] in {"show", "clear"} for call in logic.calls)
    panel_source = (PYTHON / "DENTORobotSimulationPanel.py").read_text(encoding="utf-8")
    assert "cyan translucent ghost" in panel_source


def test_viewport_base_drag_updates_only_the_detached_review_candidate():
    class Matrix:
        def GetElement(self, row, column):
            return 1.0 if row == column else (12.0 if (row, column) == (0, 3) else 0.0)

    method = _methods(
        PYTHON / "dentobot_workflow/widget_robot_placement.py",
        "RobotPlacementWidgetMixin",
        {"_onManualBaseCandidateInteractionModified"},
        {"vtk": SimpleNamespace(vtkMatrix4x4=Matrix), "math": math},
    )["_onManualBaseCandidateInteractionModified"]
    staged = []
    messages = []
    node = SimpleNamespace(GetMatrixTransformToWorld=lambda _matrix: None)
    panel = SimpleNamespace(
        setBaseInteractionStatus=lambda state, text: messages.append((state, text)),
        manualBaseReviewStatusLabel=SimpleNamespace(text=""),
    )
    host = SimpleNamespace(
        _manualBaseCandidateInteractionNode=node,
        _updatingManualBaseCandidateFromViewport=False,
        _isStep6ManualBaseReviewActive=lambda: True,
        _parameterNode=SimpleNamespace(robotBaseMountLocked=False),
        _robotWorkflowFacade=SimpleNamespace(
            stageManualBaseReview=lambda values: (
                staged.append(tuple(values))
                or SimpleNamespace(success=True, message="staged")
            )
        ),
        _robotSimulationPanel=panel,
        _manualBaseCandidateGhostKey="old",
    )

    method(host, node)

    assert len(staged) == 1
    assert staged[0][3] == 12.0
    assert host._manualBaseCandidateGhostKey is None
    assert messages == [
        ("ok", "Base unlocked · viewport drag active on the detached candidate.")
    ]
    assert "accepted Base is unchanged" in panel.manualBaseReviewStatusLabel.text

    host._parameterNode.robotBaseMountLocked = True
    method(host, node)
    assert len(staged) == 1


def test_step6_base_nudge_stages_detached_candidate_and_never_mutates_accepted_base():
    nudge = _methods(
        PYTHON / "dentobot_workflow/widget_robot_scene.py",
        "RobotSceneWidgetMixin",
        {"_nudgeRobotBase"},
        {"np": np, "local_nudge_matrix": _local_nudge_matrix_for_test},
    )["_nudgeRobotBase"]

    class Facade:
        def __init__(self, result):
            self.result = result
            self.staged = []

        def manualBaseReview(self):
            return SimpleNamespace(
                success=True,
                details={
                    "identityStatus": "current",
                    "staged": False,
                    "acceptedMatrixWorldRasMm": tuple(np.eye(4).reshape(-1)),
                    "candidateMatrixWorldRasMm": None,
                },
            )

        def stageManualBaseReview(self, matrix):
            self.staged.append(tuple(matrix))
            return self.result

    accepted_mutations = []
    facade = Facade(SimpleNamespace(success=False, message="stage rejected"))
    host = SimpleNamespace(
        _parameterNode=SimpleNamespace(
            robotBaseMountLocked=False,
            robotTranslationStepMm=2.0,
            robotRotationStepDeg=1.0,
        ),
        logic=SimpleNamespace(
            nudgeRobotBase=lambda *_args, **_kwargs: accepted_mutations.append(True)
        ),
        _robotWorkflowFacade=facade,
        _isStep6RobotWorkflowActive=lambda: True,
        _isStep6ManualBaseReviewActive=lambda: True,
        _updateStep6PlanningUi=lambda *_args, **_kwargs: None,
    )
    nudge(host, 0, None, 1.0)

    assert len(facade.staged) == 1
    assert facade.staged[0][3] == 2.0
    assert accepted_mutations == []


def _local_nudge_matrix_for_test(base, translation_local_mm, rotation_local_deg):
    matrix = np.asarray(base, dtype=float).copy()
    matrix[:3, 3] += np.asarray(translation_local_mm, dtype=float)
    assert tuple(rotation_local_deg) == (0.0, 0.0, 0.0)
    return matrix


def test_step6_base_accept_mirrors_only_after_facade_acknowledgement():
    accept = _methods(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        {"onLockRobotBaseMount"},
        {"slicer": SimpleNamespace(util=SimpleNamespace(errorDisplay=lambda _msg: None))},
    )["onLockRobotBaseMount"]
    for success, expected_updates in ((True, 1), (False, 0)):
        calls = []
        facade = SimpleNamespace(
            acceptManualBaseReview=lambda: (
                calls.append("accept")
                or SimpleNamespace(success=success, message="accepted" if success else "rejected")
            )
        )
        host = SimpleNamespace(
            _parameterNode=object(),
            logic=object(),
            _robotWorkflowFacade=facade,
            _isStep6RobotWorkflowActive=lambda: True,
            _isStep6ManualBaseReviewActive=lambda: True,
            _updateStep6PlanningUi=lambda *_args, **_kwargs: None,
            _updateRobotPlacement=lambda: calls.append("mirror"),
        )
        accept(host)
        assert calls.count("accept") == 1
        assert calls.count("mirror") == expected_updates


def test_manual_base_review_keeps_stale_cancel_available_and_blocks_unknown_acceptance():
    control_state = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {"_manualBaseReviewControlState"},
        {},
    )["_manualBaseReviewControlState"]

    stale_host = SimpleNamespace()
    stale = SimpleNamespace(
        success=False,
        details={"staged": True, "identityStatus": "case_changed"},
    )
    stale_state = control_state(stale_host, False, False, False, stale)
    assert stale_state["group"] is True
    assert stale_state["cancel"] is True
    assert stale_state["accept"] is False

    uncertain = SimpleNamespace(
        success=False,
        details={
            "staged": True,
            "identityStatus": "current",
            "acceptanceStatus": "unknown",
            "acceptanceUncertainty": "native scene acknowledgement unknown",
        },
    )
    uncertain_state = control_state(stale_host, True, True, False, uncertain)
    assert uncertain_state["group"] is True
    assert uncertain_state["cancel"] is False
    assert uncertain_state["accept"] is False
    assert uncertain_state["acceptance_unknown"] is True


def test_manual_base_reconcile_requires_unknown_status_and_current_ros_scene():
    control_state = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {"_manualBaseReviewControlState"},
        {},
    )["_manualBaseReviewControlState"]
    host = SimpleNamespace()
    uncertain = SimpleNamespace(
        success=True,
        details={
            "staged": True,
            "identityStatus": "current",
            "acceptanceStatus": "unknown",
            "acceptanceUncertainty": "native scene acknowledgement unknown",
        },
    )
    uncertain_state = control_state(host, True, True, False, uncertain, True)
    assert uncertain_state["reconcile"] is True
    assert uncertain_state["accept"] is False
    assert uncertain_state["cancel"] is False
    cancelled = SimpleNamespace(
        success=True,
        details={**uncertain.details, "staged": False},
    )
    cancelled_state = control_state(host, True, True, False, cancelled, True)
    assert cancelled_state["reconcile"] is False
    assert cancelled_state["cancel"] is False
    assert cancelled_state["accept"] is False
    assert control_state(host, True, True, False, uncertain, False)["reconcile"] is False
    assert control_state(host, False, True, False, uncertain, True)["reconcile"] is False
    assert control_state(host, True, False, False, uncertain, True)["reconcile"] is False
    stale = SimpleNamespace(
        success=False,
        details={**uncertain.details, "identityStatus": "unknown"},
    )
    assert control_state(host, True, True, False, stale, True)["reconcile"] is False
    current = SimpleNamespace(
        success=True,
        details={**uncertain.details, "acceptanceStatus": "review", "acceptanceUncertainty": ""},
    )
    assert control_state(host, True, True, False, current, True)["reconcile"] is False


def test_manual_base_reconcile_calls_facade_once_and_preserves_review_evidence():
    shell_path = PYTHON / "dentobot_workflow/widget_robot_shell.py"
    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    robot_path = PYTHON / "dentobot_workflow/widget_robot.py"
    error_calls = []
    callback = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {"_onStep6ReconcileManualBaseAcceptance"},
        {
            "Mapping": Mapping,
            "slicer": SimpleNamespace(
                util=SimpleNamespace(errorDisplay=lambda message: error_calls.append(str(message)))
            ),
        },
    )["_onStep6ReconcileManualBaseAcceptance"]
    assert '"reconcile_manual_base": 1' in panel_path.read_text(encoding="utf-8")
    assert '"reconcile_manual_base": self._onStep6ReconcileManualBaseAcceptance' in shell_path.read_text(encoding="utf-8")
    assert "reconcileManualBaseStateButton.enabled" in robot_path.read_text(encoding="utf-8")
    assert 'self._invoke("reconcile_manual_base")' in panel_path.read_text(encoding="utf-8")

    candidate = tuple(float(value) for value in np.eye(4).reshape(-1))
    failure = {"code": "manual_base_acceptance_unknown", "rollbackStatus": "unknown"}

    def invoke(success):
        error_calls.clear()
        calls = []
        panel = SimpleNamespace(
            manualBaseReviewStatusLabel=SimpleNamespace(text="Accepted Base and draft evidence visible."),
            setManualJogAcceptedState=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("Base reconciliation must not mirror accepted state")
            ),
        )
        result = SimpleNamespace(
            success=success,
            message="native acknowledgement confirmed" if success else "native acknowledgement unavailable",
            details={
                "staged": True,
                "candidateMatrixWorldRasMm": candidate,
                "acceptanceStatus": "current" if success else "unknown",
                "failureEvidence": failure,
                "acceptanceUncertainty": "" if success else "native scene remains unknown",
            },
        )

        class Facade:
            def reconcileManualBaseAcceptance(self):
                calls.append("reconcile")
                return result

            def acceptManualBaseReview(self):
                raise AssertionError("Reconciliation must not accept the candidate")

        def refresh(message, error=False):
            calls.append(("refresh", message, error))
            panel.manualBaseReviewStatusLabel.text = (
                "Accepted Base and draft evidence visible; preserved failure evidence."
            )

        host = SimpleNamespace(
            _robotSimulationPanel=panel,
            _robotWorkflowFacade=Facade(),
            _workflowActionBusy=False,
            _updateStep6PlanningUi=refresh,
        )
        callback(host)
        return host, panel, calls, list(error_calls)

    host, panel, calls, errors = invoke(True)
    assert [call[0] if isinstance(call, tuple) else call for call in calls] == ["reconcile", "refresh"]
    assert calls[1][2] is False
    assert "accepted Base/native scene was reconciled" in panel.manualBaseReviewStatusLabel.text
    assert "candidate remains staged" in panel.manualBaseReviewStatusLabel.text
    assert "Staged Base draft evidence" in panel.manualBaseReviewStatusLabel.text
    assert "Preserved Base acceptance failure evidence" in panel.manualBaseReviewStatusLabel.text
    assert errors == []
    assert host._workflowActionBusy is False

    host, panel, calls, errors = invoke(False)
    assert [call[0] if isinstance(call, tuple) else call for call in calls] == ["reconcile", "refresh"]
    assert calls[1][2] is True
    assert "state remains unresolved" in panel.manualBaseReviewStatusLabel.text
    assert "native acknowledgement unavailable" in panel.manualBaseReviewStatusLabel.text
    assert "Preserved Base acceptance failure evidence" in panel.manualBaseReviewStatusLabel.text
    assert "accepted Base/native scene was reconciled" not in panel.manualBaseReviewStatusLabel.text
    assert "unchanged" not in panel.manualBaseReviewStatusLabel.text.lower()
    assert errors and "state remains unresolved" in errors[0]
    assert host._workflowActionBusy is False


def test_manual_record_export_includes_completed_and_active_records_and_report(tmp_path):
    accepted = {name: float(index) / 10.0 for index, name in enumerate(JOINT_NAMES)}
    requested = {name: value + 0.01 for name, value in accepted.items()}
    completed = _manual_record(
        "completed-1",
        [
            {
                "kind": "guard_accepted",
                "monotonic_ns": 1,
                "requested_joints": accepted,
                "accepted_joints": accepted,
                "details": {"identity_status": "current", "guard_outcome": "accepted"},
            },
            {
                "kind": "guard_rejected",
                "monotonic_ns": 2,
                "requested_joints": requested,
                "accepted_joints": accepted,
                "native_failure_evidence": {"status": "known", "reason": "collision"},
            },
        ],
    )
    completed_later = _manual_record(
        "completed-2",
        [
            {
                "kind": "diagnostic",
                "monotonic_ns": 3,
                "diagnostic": {
                    "clearance_status": "unknown",
                    "conditioning_status": "unavailable",
                },
            }
        ],
    )
    active = _manual_record(
        "active",
        [{"kind": "requested", "monotonic_ns": 4, "requested_joints": requested}],
    )
    export, host, panel, destination, _dialogs, errors = _manual_record_export_harness(
        tmp_path, (completed, completed_later), active
    )

    export(host)

    records = json.loads(destination.read_text(encoding="utf-8"))
    assert records == [completed, completed_later, active]
    report = destination.with_suffix(".report.txt").read_text(encoding="utf-8")
    assert "Records exported: 3" in report
    assert "Events (2): guard_accepted=1, guard_rejected=1" in report
    assert "Events (1): diagnostic=1" in report
    assert "completed-1-task_fingerprint" in report
    assert '"status": "known"' in report
    assert '"clearance_status": "unknown"' in report
    assert '"conditioning_status": "unavailable"' in report
    assert panel.export_status[0] == "ok"
    assert "companion report" in panel.export_status[1]
    assert panel.status_calls == 0
    assert panel.status == ("error", "Guard status: rejected — collision.")
    assert panel.evidence == {"lastGuardFailure": "collision"}
    assert errors == []


def test_manual_record_export_preserves_completed_multiplicity_and_deduplicates_latest_fallback(
    tmp_path,
):
    first = _manual_record(
        "first", [{"kind": "requested", "monotonic_ns": 1, "requested_joints": {n: 0.0 for n in JOINT_NAMES}}]
    )
    latest = _manual_record(
        "latest", [{"kind": "requested", "monotonic_ns": 2, "requested_joints": {n: 0.1 for n in JOINT_NAMES}}]
    )
    export, host, _panel, destination, _dialogs, _errors = _manual_record_export_harness(
        tmp_path, (first, latest, latest), latest
    )

    export(host)

    records = json.loads(destination.read_text(encoding="utf-8"))
    assert records == [first, latest, latest]


def test_manual_record_export_rejects_invalid_record_without_opening_dialog(tmp_path):
    valid = _manual_record(
        "invalid", [{"kind": "requested", "monotonic_ns": 1, "requested_joints": {n: 0.0 for n in JOINT_NAMES}}]
    )
    invalid = {**valid, "record_fingerprint": "tampered"}
    export, host, panel, destination, dialogs, errors = _manual_record_export_harness(
        tmp_path, (invalid,), invalid
    )

    export(host)

    assert dialogs == []
    assert not destination.exists()
    assert panel.export_status[0] == "blocked"
    assert "fingerprint does not match" in panel.export_status[1]
    assert len(errors) == 1
    assert panel.status_calls == 0
    assert panel.status == ("error", "Guard status: rejected — collision.")
    assert panel.evidence == {"lastGuardFailure": "collision"}


def test_manual_record_export_reports_companion_write_failure_without_changing_guard(
    tmp_path, monkeypatch
):
    active = _manual_record(
        "active", [{"kind": "requested", "monotonic_ns": 1, "requested_joints": {n: 0.0 for n in JOINT_NAMES}}]
    )
    export, host, panel, destination, _dialogs, errors = _manual_record_export_harness(
        tmp_path, (), active
    )
    original_write_text = Path.write_text
    writes = []

    def fail_companion(path, data, *, encoding=None):
        writes.append(path)
        if len(writes) == 2:
            raise OSError("read-only report destination")
        return original_write_text(path, data, encoding=encoding)

    monkeypatch.setattr(Path, "write_text", fail_companion)
    export(host)

    assert writes == [destination, destination.with_suffix(".report.txt")]
    assert json.loads(destination.read_text(encoding="utf-8")) == [active]
    assert panel.export_status[0] == "error"
    assert "may be incomplete" in panel.export_status[1]
    assert len(errors) == 1
    assert panel.status_calls == 0
    assert panel.status == ("error", "Guard status: rejected — collision.")
    assert panel.evidence == {"lastGuardFailure": "collision"}


def test_manual_record_import_validates_array_and_uses_only_historical_paths(tmp_path):
    accepted = {name: float(index) / 10.0 for index, name in enumerate(JOINT_NAMES)}
    record = _manual_record(
        "imported",
        [
            {
                "kind": "requested",
                "monotonic_ns": 1,
                "requested_joints": accepted,
            },
            {
                "kind": "guard_accepted",
                "monotonic_ns": 2,
                "requested_joints": accepted,
                "accepted_joints": accepted,
                "monitored_joints": accepted,
            },
        ],
    )
    second = _manual_record(
        "imported-second",
        [{"kind": "diagnostic", "monotonic_ns": 3, "diagnostic": {"status": "unknown"}}],
    )
    (
        host,
        panel,
        _source,
        dialogs,
        errors,
        cleared_paths,
        shown_paths,
        facade,
    ) = _manual_record_import_harness(tmp_path, [record, second])
    authority_before = (
        panel.previewApproachButton.enabled,
        panel.previewDrillingButton.enabled,
        panel.approachPlanningButton.enabled,
        panel.drillingPlanningButton.enabled,
    )

    host._onStep6ImportManualRecord()

    assert dialogs == [True]
    assert panel.records == (record, second)
    assert panel.import_status[0] == "ok"
    assert "Validated 2" in panel.import_status[1]
    assert len(cleared_paths) == 1
    assert shown_paths == []
    assert facade.calls == []
    assert authority_before == (
        panel.previewApproachButton.enabled,
        panel.previewDrillingButton.enabled,
        panel.approachPlanningButton.enabled,
        panel.drillingPlanningButton.enabled,
    )
    host._onStep6ShowManualRecord(panel.records[0])
    assert shown_paths == [record]
    assert "shown" in panel.import_status[1]
    host._onStep6ClearManualRecord()
    assert len(cleared_paths) == 2
    assert panel.records == ()
    assert facade.calls == []
    assert errors == []


def test_manual_record_import_rejects_bad_fingerprint_without_clearing_current_history(
    tmp_path,
):
    valid = _manual_record(
        "tampered", [{"kind": "requested", "monotonic_ns": 1, "requested_joints": {n: 0.0 for n in JOINT_NAMES}}]
    )
    invalid = {**valid, "record_fingerprint": "tampered"}
    previous = _manual_record(
        "previous", [{"kind": "requested", "monotonic_ns": 1, "requested_joints": {n: 0.0 for n in JOINT_NAMES}}]
    )
    (
        host,
        panel,
        _source,
        dialogs,
        errors,
        cleared_paths,
        shown_paths,
        facade,
    ) = _manual_record_import_harness(
        tmp_path, invalid, previous_records=(previous,)
    )

    host._onStep6ImportManualRecord()

    assert dialogs == [True]
    assert panel.records == (previous,)
    assert panel.import_status[0] == "blocked"
    assert "fingerprint does not match" in panel.import_status[1]
    assert "previous historical selection and display remain unchanged" in panel.import_status[1]
    assert errors and "fingerprint does not match" in errors[0]
    assert cleared_paths == []
    assert shown_paths == []
    assert facade.calls == []


def test_historical_path_unavailable_keeps_validated_event_details(tmp_path):
    record = _manual_record(
        "no-tcp",
        [{"kind": "diagnostic", "monotonic_ns": 1, "diagnostic": {"tcp": "unknown"}}],
    )
    (
        host,
        panel,
        _source,
        _dialogs,
        errors,
        _cleared_paths,
        shown_paths,
        facade,
    ) = _manual_record_import_harness(
        tmp_path, record, path_result=(False, "record contains no TCP points")
    )
    host._onStep6ImportManualRecord()
    host._onStep6ShowManualRecord(panel.records[0])

    assert shown_paths == [record]
    assert len(_cleared_paths) == 2
    assert panel.records == (record,)
    assert panel.import_status[0] == "unavailable"
    assert "record contains no TCP points" in panel.import_status[1]
    assert errors == []
    assert facade.calls == []


def test_manual_record_import_caps_aggregate_event_count_before_replacing_history(tmp_path):
    record = _manual_record(
        "too-many-events",
        [
            {"kind": "diagnostic", "monotonic_ns": index, "diagnostic": {"status": "unknown"}}
            for index in range(10_001)
        ],
    )
    previous = _manual_record(
        "previous", [{"kind": "requested", "monotonic_ns": 1, "requested_joints": {n: 0.0 for n in JOINT_NAMES}}]
    )
    (
        host,
        panel,
        _source,
        _dialogs,
        errors,
        cleared_paths,
        shown_paths,
        facade,
    ) = _manual_record_import_harness(tmp_path, [record], previous_records=(previous,))

    host._onStep6ImportManualRecord()

    assert panel.records == (previous,)
    assert panel.import_status[0] == "blocked"
    assert "10,000 event limit" in panel.import_status[1]
    assert errors and "10,000 event limit" in errors[0]
    assert cleared_paths == []
    assert shown_paths == []
    assert facade.calls == []


def test_historical_event_stepping_selects_evidence_without_scene_or_facade_calls():
    accepted = {name: float(index) / 10.0 for index, name in enumerate(JOINT_NAMES)}
    requested = {name: value + 0.01 for name, value in accepted.items()}
    record = _manual_record(
        "steps",
        [
            {"kind": "requested", "monotonic_ns": 10, "requested_joints": requested},
            {
                "kind": "guard_accepted",
                "monotonic_ns": 20,
                "requested_joints": accepted,
                "accepted_joints": accepted,
                "monitored_joints": accepted,
            },
            {
                "kind": "guard_rejected",
                "monotonic_ns": 30,
                "requested_joints": requested,
                "accepted_joints": accepted,
                "native_failure_evidence": {"status": "known", "reason": "collision"},
            },
            {
                "kind": "diagnostic",
                "monotonic_ns": 40,
                "diagnostic": {"clearance": "unknown", "conditioning": "unavailable"},
            },
        ],
    )
    second_record = _manual_record(
        "steps-second",
        [{"kind": "diagnostic", "monotonic_ns": 50, "diagnostic": {"source": "second"}}],
    )

    class Signal:
        def __init__(self):
            self.callback = None

        def connect(self, callback):
            self.callback = callback

        def emit(self, value):
            if self.callback:
                self.callback(value)

    class EventList:
        def __init__(self):
            self.items = []
            self.currentRow = -1
            self.currentRowChanged = Signal()
            self.signals_blocked = False

        def blockSignals(self, blocked):
            self.signals_blocked = bool(blocked)

        def clear(self):
            self.items.clear()
            self.currentRow = -1

        def addItem(self, text):
            self.items.append(text)

        def setCurrentRow(self, row):
            self.currentRow = row
            if not self.signals_blocked:
                self.currentRowChanged.emit(row)

    class Selector:
        def __init__(self):
            self.items = []
            self.currentIndex = -1
            self.currentIndexChanged = Signal()
            self.signals_blocked = False

        def blockSignals(self, blocked):
            self.signals_blocked = bool(blocked)

        def clear(self):
            self.items.clear()

        def addItem(self, text):
            self.items.append(text)

        def setCurrentIndex(self, index):
            self.currentIndex = index
            if not self.signals_blocked:
                self.currentIndexChanged.emit(index)

    class Text:
        def __init__(self):
            self.text = ""

        def setPlainText(self, text):
            self.text = text

    methods = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        {
            "setManualSimulationRecords",
            "_onManualSimulationRecordChanged",
            "_onManualSimulationEventChanged",
            "_stepManualSimulationEvent",
        },
        {"json": json},
    )
    callbacks = []
    host = SimpleNamespace(
        _manualSimulationRecords=(),
        _invoke=lambda name, *args: callbacks.append((name, *args)),
        manualSimulationRecordComboBox=Selector(),
        manualSimulationEventList=EventList(),
        manualSimulationRecordIdentityLabel=SimpleNamespace(text=""),
        manualSimulationEventDetailsText=Text(),
        previousManualSimulationEventButton=SimpleNamespace(enabled=False),
        nextManualSimulationEventButton=SimpleNamespace(enabled=False),
        clearManualRecordButton=SimpleNamespace(enabled=False),
        previewApproachButton=SimpleNamespace(enabled=False),
        previewDrillingButton=SimpleNamespace(enabled=False),
        planApproachButton=SimpleNamespace(enabled=False),
        planDrillingButton=SimpleNamespace(enabled=False),
    )
    preview_state_before = (
        host.previewApproachButton.enabled,
        host.previewDrillingButton.enabled,
        host.planApproachButton.enabled,
        host.planDrillingButton.enabled,
    )
    for name, method in methods.items():
        setattr(host, name, method.__get__(host, type(host)))
    host.manualSimulationEventList.currentRowChanged.connect(
        host._onManualSimulationEventChanged
    )
    host.manualSimulationRecordComboBox.currentIndexChanged.connect(
        host._onManualSimulationRecordChanged
    )

    host.setManualSimulationRecords(
        [
            parse_manual_simulation_record(record),
            parse_manual_simulation_record(second_record),
        ]
    )

    assert len(host.manualSimulationEventList.items) == 4
    assert len(host.manualSimulationRecordComboBox.items) == 2
    assert "REQUESTED" in host.manualSimulationEventList.items[0]
    assert "ACCEPTED" in host.manualSimulationEventList.items[1]
    assert "REJECTED" in host.manualSimulationEventList.items[2]
    assert "DIAGNOSTIC" in host.manualSimulationEventList.items[3]
    assert "record_fingerprint" in host.manualSimulationRecordIdentityLabel.text
    assert callbacks == [("show_manual_record", record)]

    host._stepManualSimulationEvent(1)
    assert host.manualSimulationEventList.currentRow == 1
    assert "guard_accepted" in host.manualSimulationEventDetailsText.text
    host._stepManualSimulationEvent(1)
    assert host.manualSimulationEventList.currentRow == 2
    assert '"reason": "collision"' in host.manualSimulationEventDetailsText.text
    assert '"tcp_point_ras_mm": "unknown (not recorded)"' in (
        host.manualSimulationEventDetailsText.text
    )
    host._stepManualSimulationEvent(1)
    assert host.manualSimulationEventList.currentRow == 3
    assert '"clearance": "unknown"' in host.manualSimulationEventDetailsText.text
    assert '"conditioning": "unavailable"' in host.manualSimulationEventDetailsText.text
    host._stepManualSimulationEvent(1)
    assert host.manualSimulationEventList.currentRow == 3
    host._stepManualSimulationEvent(-1)
    assert host.manualSimulationEventList.currentRow == 2
    assert callbacks == [("show_manual_record", record)]
    host.manualSimulationRecordComboBox.setCurrentIndex(1)
    assert "steps-second-task_fingerprint" in host.manualSimulationRecordIdentityLabel.text
    assert len(host.manualSimulationEventList.items) == 1
    assert "diagnostic" in host.manualSimulationEventDetailsText.text
    assert callbacks == [("show_manual_record", record), ("show_manual_record", second_record)]
    assert preview_state_before == (
        host.previewApproachButton.enabled,
        host.previewDrillingButton.enabled,
        host.planApproachButton.enabled,
        host.planDrillingButton.enabled,
    )


def test_set_robot_joints_from_si_converts_radians_without_publishing():
    source = PYTHON / "dentobot_workflow/widget_robot.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    math_imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "math"
        and any(alias.name == "degrees" for alias in node.names)
    ]
    namespace = {}
    exec(
        compile(
            ast.Module(body=math_imports, type_ignores=[]), str(source), "exec"
        ),
        namespace,
    )
    method = _methods(
        source,
        "RobotWidgetMixin",
        {"_setRobotJointsFromSi"},
        namespace,
    )["_setRobotJointsFromSi"]

    class ParameterNode:
        robotBaseTransform = object()

        def __init__(self):
            self.modified = []

        def StartModify(self):
            return 17

        def EndModify(self, previous):
            self.modified.append(previous)

    parameter_node = ParameterNode()
    robot_updates = []
    ros_checks = []
    host = SimpleNamespace(
        _parameterNode=parameter_node,
        _updateRobotPlacement=lambda: robot_updates.append(True),
        logic=SimpleNamespace(
            isRos2MotionControlActive=lambda *_args: ros_checks.append(True) or True
        ),
    )
    positions = {
        JOINT_NAMES[0]: radians(30),
        JOINT_NAMES[1]: 0.012,
        JOINT_NAMES[2]: radians(-45),
        JOINT_NAMES[3]: 0.0035,
        JOINT_NAMES[4]: radians(90),
    }

    assert method(host, positions, publish_to_ros=False) == (True, "")
    assert (
        round(parameter_node.robotJoint1Deg, 6),
        parameter_node.robotJoint2Mm,
        round(parameter_node.robotJoint3Deg, 6),
        parameter_node.robotJoint4Mm,
        round(parameter_node.robotJoint5Deg, 6),
    ) == (30.0, 12.0, -45.0, 3.5, 90.0)
    assert parameter_node.modified == [17]
    assert robot_updates == [True]
    assert ros_checks == []


def test_task_home_review_displays_separate_j1_j5_states_and_failure_status():
    methods = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        {
            "_formatManualJogDisplayValues",
            "_updateManualJogResetLabel",
            "setManualTaskHomeReviewResult",
            "_updateManualJogJointPresentation",
        },
        {
            "JOINT_NAMES": JOINT_NAMES,
            "Mapping": Mapping,
            "degrees": degrees,
            "isfinite": isfinite,
        },
    )
    panel = type("PanelProbe", (), methods)()
    panel.acceptTaskHomeButton = _Control()
    panel.resetManualJogDraftButton = _Control()
    panel.taskHomeCurrentStateLabel = _Control()
    panel.taskHomeConfiguredStateLabel = _Control()
    panel.taskHomeCandidateLabel = _Control()
    panel.taskHomeReviewStatusLabel = _Control()
    panel._manualJogAcceptedJointPositionsSi = None
    panel._manualJogLocalJointPositionsSi = None
    panel._taskHomeSetupMode = "unknown"
    panel._taskHomeConfigurationReady = False
    panel._taskHomeConfiguredJointPositionsSi = None
    accepted = {
        name: float(index + 1) / 10.0 for index, name in enumerate(JOINT_NAMES)
    }
    candidate = {**accepted, JOINT_NAMES[0]: accepted[JOINT_NAMES[0]] + 0.1}
    panel.setManualTaskHomeReviewResult(
        SimpleNamespace(
            success=True,
            message="candidate staged",
            details={
                "staged": True,
                "candidateJointPositionsSi": candidate,
                "acceptedJointPositionsSi": accepted,
                "identityStatus": "current",
                "acceptanceStatus": "review",
                "setupMode": "connected",
            },
        )
    )

    assert "Current accepted robot J1–J5" in panel.taskHomeCurrentStateLabel.text
    assert "Staged Task Home candidate" in panel.taskHomeCandidateLabel.text
    assert "J1 5.73 deg" in panel.taskHomeCurrentStateLabel.text
    assert "J1 11.46 deg" in panel.taskHomeCandidateLabel.text
    assert "Home review: review; identity: current" in panel.taskHomeReviewStatusLabel.text
    assert "use Plan + Apply Home Draft" in panel.taskHomeReviewStatusLabel.text
    assert "Home review sends no motion" in panel.taskHomeReviewStatusLabel.text
    assert "pneumatic_spindle" not in panel.taskHomeCandidateLabel.text

    rounded_candidate = dict(accepted)
    rounded_candidate[JOINT_NAMES[0]] += 5.0e-13
    panel.setManualTaskHomeReviewResult(
        SimpleNamespace(
            success=True,
            message="roundoff-only difference",
            details={
                "staged": True,
                "candidateJointPositionsSi": rounded_candidate,
                "acceptedJointPositionsSi": accepted,
                "identityStatus": "current",
                "acceptanceStatus": "review",
                "setupMode": "connected",
            },
        )
    )
    assert "use Plan + Apply Home Draft" not in panel.taskHomeReviewStatusLabel.text

    panel.setManualTaskHomeReviewResult(
        SimpleNamespace(
            success=False,
            message="native evidence unavailable",
            details={
                "staged": True,
                "candidateJointPositionsSi": candidate,
                "acceptedJointPositionsSi": {**accepted, "unexpected_joint": 1.0},
                "identityStatus": "unknown",
                "acceptanceStatus": "unknown",
                "setupMode": "connected",
                "failureEvidence": {"reason": "scene status unavailable"},
                "acceptanceUncertainty": "save outcome may have committed",
            },
        )
    )
    assert "identity: unknown" in panel.taskHomeReviewStatusLabel.text
    assert "Failure evidence" in panel.taskHomeReviewStatusLabel.text
    assert "Acceptance uncertainty" in panel.taskHomeReviewStatusLabel.text
    assert "Current accepted robot J1–J5: unavailable" in panel.taskHomeCurrentStateLabel.text


def test_task_home_mode_labels_and_offline_configuration_never_claim_live_acceptance():
    methods = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        {"_formatManualJogDisplayValues", "_updateManualJogResetLabel", "setManualTaskHomeReviewResult", "_updateManualJogJointPresentation"},
        {
            "JOINT_NAMES": JOINT_NAMES,
            "Mapping": Mapping,
            "degrees": degrees,
            "isfinite": isfinite,
        },
    )
    panel = type("PanelProbe", (), methods)()
    for name in (
        "acceptTaskHomeButton",
        "resetManualJogDraftButton",
        "manualJogAcceptedStateLabel",
        "taskHomeCurrentStateLabel",
        "taskHomeConfiguredStateLabel",
        "taskHomeCandidateLabel",
        "taskHomeReviewStatusLabel",
    ):
        setattr(panel, name, _Control())
    panel._manualJogAcceptedJointPositionsSi = None
    panel._manualJogLocalJointPositionsSi = None
    panel._taskHomeSetupMode = "unknown"
    panel._taskHomeConfigurationReady = False
    panel._taskHomeConfiguredJointPositionsSi = None

    configured = {name: float(index + 1) / 10.0 for index, name in enumerate(JOINT_NAMES)}
    panel.setManualTaskHomeReviewResult(
        SimpleNamespace(
            success=True,
            message="offline configuration saved",
            details={
                "setupMode": "offline",
                "identityStatus": "current",
                "acceptanceStatus": "configuration_saved",
                "configurationReady": True,
                "runtimeValidated": False,
                "configuredJointPositionsSi": configured,
                "staged": True,
                "candidateJointPositionsSi": configured,
                "acceptedJointPositionsSi": None,
            },
        )
    )
    assert panel._taskHomeSetupMode == "offline"
    assert panel.acceptTaskHomeButton.text == "Save Home Configuration"
    assert panel.resetManualJogDraftButton.text == "Reset Draft to Saved Home Configuration"
    assert panel._manualJogAcceptedJointPositionsSi is None
    assert "unavailable while offline" in panel.taskHomeCurrentStateLabel.text
    assert "configuration only; not live-validated" in panel.taskHomeConfiguredStateLabel.text
    assert "use Plan + Apply Home Draft" not in panel.taskHomeReviewStatusLabel.text

    panel._manualJogAcceptedJointPositionsSi = dict(configured)
    panel.setManualTaskHomeReviewResult(
        SimpleNamespace(
            success=True,
            message="setup mode unavailable",
            details={
                "setupMode": "unrecognized",
                "identityStatus": "current",
                "acceptanceStatus": "accepted",
                "acceptedJointPositionsSi": configured,
                "staged": False,
            },
        )
    )
    assert panel._taskHomeSetupMode == "unknown"
    assert panel.acceptTaskHomeButton.text == "Task Home Mode Unknown"
    assert panel.resetManualJogDraftButton.text == "Reset Draft Unavailable"
    assert panel._manualJogAcceptedJointPositionsSi is None
    assert "setup mode is unknown" in panel.taskHomeCurrentStateLabel.text


def test_offline_draft_uses_mechanical_limits_and_disables_native_jog_actions():
    def to_si(j1, j2, j3, j4, j5):
        return {
            JOINT_NAMES[0]: radians(j1),
            JOINT_NAMES[1]: j2 / 1000.0,
            JOINT_NAMES[2]: radians(j3),
            JOINT_NAMES[3]: j4 / 1000.0,
            JOINT_NAMES[4]: radians(j5),
        }

    names = {
        "setManualJogLimits",
        "setManualJogAvailability",
        "_updateManualJogResetLabel",
        "resetManualJogDraft",
        "_setManualJogDraftValues",
        "manualJogJointPositionsSi",
        "_formatManualJogDisplayValues",
        "_updateManualJogJointPresentation",
        "_setManualJogStatus",
    }
    methods = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        names,
        {
            "JOINT_NAMES": JOINT_NAMES,
            "Mapping": Mapping,
            "degrees": degrees,
            "isfinite": isfinite,
            "joint_positions_si_from_display": to_si,
        },
    )
    panel = type("PanelProbe", (), methods)()
    panel.manualJogJointControls = {
        name: (_Control(), _Control(), _Control()) for name in JOINT_NAMES
    }
    panel._manualJogJointPresentation = {}
    for index, (joint, unit) in enumerate(
        zip(JOINT_NAMES, ("deg", "mm", "deg", "mm", "deg"), strict=True),
        start=1,
    ):
        panel.manualJogJointControls[joint][2].text = f"J{index} ({unit})"
    for name in (
        "manualJogAcceptedStateLabel",
        "taskHomeCurrentStateLabel",
        "manualJogDraftLimitLabel",
        "manualJogDraftStateLabel",
        "manualJogStatusLabel",
    ):
        setattr(panel, name, _Control())
    for name in (
        "resetManualJogDraftButton",
        "checkManualDraftStateButton",
        "reconcileManualJogButton",
        "guardedManualJogButton",
    ):
        setattr(panel, name, _Control())
    panel._updateManualJogKeyboardControlState = lambda: None
    panel._invoke_calls = []
    panel._invoke = lambda action, state: panel._invoke_calls.append((action, state))
    panel._manualJogLimits = {}
    panel._manualJogSliderRanges = ()
    panel._manualJogMechanicalLimits = None
    panel._manualJogLimitsValid = False
    panel._manualJogCommandLimitsValid = False
    panel._manualJogAvailable = False
    panel._manualJogGuardAvailable = False
    panel._manualJogGuardContextAvailable = False
    panel._manualJogBusy = False
    panel._manualJogDraftInitialized = False
    panel._manualJogDisplayValues = (0.0,) * 5
    panel._manualJogAcceptedJointPositionsSi = None
    panel._manualJogLocalJointPositionsSi = None
    panel._manualJogEvidence = None
    panel._manualJogLimitViolations = ()
    panel._manualJogDraftWithinCommandLimits = False
    panel.manualJogReconciliationRequired = True
    panel._taskHomeSetupMode = "offline"
    panel._taskHomeConfigurationReady = True
    panel._manualJogControlsInHomeGroup = False
    panel._taskHomeConfiguredJointPositionsSi = {
        JOINT_NAMES[0]: radians(5),
        JOINT_NAMES[1]: 0.005,
        JOINT_NAMES[2]: radians(-3),
        JOINT_NAMES[3]: 0.004,
        JOINT_NAMES[4]: radians(2),
    }

    mechanical = _joint_limits(((-10, 10),) * 5)
    invalid_reviewed = _joint_limits(((20, 10),) * 5)
    panel.setManualJogLimits(mechanical, invalid_reviewed)
    panel.setManualJogAvailability(True, True)

    assert panel._manualJogAvailable is True
    assert panel._manualJogSliderRanges == ((-10.0, 10.0),) * 5
    for index, (joint, unit) in enumerate(
        zip(JOINT_NAMES, ("deg", "mm", "deg", "mm", "deg"), strict=True),
        start=1,
    ):
        assert panel.manualJogJointControls[joint][2].text == f"J{index} ({unit})"
    assert "within mechanical limits" in panel.manualJogDraftLimitLabel.text
    assert panel.manualJogJointControls[JOINT_NAMES[0]][0].enabled
    assert panel.manualJogJointControls[JOINT_NAMES[0]][1].enabled
    assert not panel.checkManualDraftStateButton.enabled
    assert not panel.reconcileManualJogButton.enabled
    assert not panel.guardedManualJogButton.enabled
    assert panel.resetManualJogDraftButton.enabled

    panel._manualJogAcceptedJointPositionsSi = {
        JOINT_NAMES[0]: radians(-8),
        JOINT_NAMES[1]: -0.008,
        JOINT_NAMES[2]: radians(7),
        JOINT_NAMES[3]: -0.007,
        JOINT_NAMES[4]: radians(-6),
    }
    panel.resetManualJogDraft()
    assert panel.manualJogJointControls[JOINT_NAMES[0]][1].value == 5.0
    assert panel.manualJogJointControls[JOINT_NAMES[1]][1].value == 5.0
    assert panel._invoke_calls[-1][0] == "manual_draft_changed"

    panel._taskHomeSetupMode = "connected"
    panel._manualJogControlsInHomeGroup = True
    panel._manualJogAcceptedJointPositionsSi = None
    panel.setManualJogAvailability(True, True)
    panel._updateManualJogResetLabel()
    assert panel.resetManualJogDraftButton.enabled
    assert panel.resetManualJogDraftButton.text == "Reset Draft to Saved Home Configuration"
    panel.resetManualJogDraft()
    assert panel.manualJogJointControls[JOINT_NAMES[0]][1].value == 5.0

    panel._manualJogAcceptedJointPositionsSi = {
        JOINT_NAMES[0]: radians(-8),
        JOINT_NAMES[1]: -0.008,
        JOINT_NAMES[2]: radians(7),
        JOINT_NAMES[3]: -0.007,
        JOINT_NAMES[4]: radians(-6),
    }
    panel._manualJogControlsInHomeGroup = False
    panel._updateManualJogResetLabel()
    assert panel.resetManualJogDraftButton.text == "Reset Draft to Accepted Current State"
    panel.resetManualJogDraft()
    assert panel.manualJogJointControls[JOINT_NAMES[0]][1].value == -8.0

    panel._taskHomeSetupMode = "unknown"
    panel.setManualJogAvailability(True, True)
    assert panel._manualJogAvailable is False
    assert not panel.manualJogJointControls[JOINT_NAMES[0]][0].enabled
    assert not panel.manualJogJointControls[JOINT_NAMES[0]][1].enabled
    assert not panel.resetManualJogDraftButton.enabled
    assert not panel.checkManualDraftStateButton.enabled
    assert not panel.reconcileManualJogButton.enabled
    assert not panel.guardedManualJogButton.enabled


def test_tcp_native_ik_controls_require_connected_setup_mode():
    methods = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        {"_tcpCartesianControlsAllowed", "_updateTcpCartesianControlState"},
        {},
    )
    panel = type("PanelProbe", (), methods)()
    panel._activeSubstep = 3
    panel._taskHomeSetupMode = "offline"
    panel._tcpDragEnabled = True
    panel._tcpIkAvailable = True
    panel.goalGroup = _Control()
    panel.goalGroup.visible = True
    panel.tcpDragEnabledCheckBox = _Control()
    panel.tcpDragEnabledCheckBox.checked = True
    panel.tcpKeyboardEnabledCheckBox = _Control()
    panel.tcpKeyboardEnabledCheckBox.checked = True
    panel.solveIkButton = _Control()
    panel.tcpCartesianNudgeButtons = {"x": _Control()}
    panel.tcpTranslationStepMm = _Control()
    panel.tcpRotationStepDeg = _Control()
    panel._tcpKeyboardShortcuts = []

    panel._updateTcpCartesianControlState()
    assert not panel.tcpDragEnabledCheckBox.enabled
    assert not panel.tcpKeyboardEnabledCheckBox.enabled
    assert not panel.solveIkButton.enabled
    assert not panel.tcpCartesianNudgeButtons["x"].enabled
    assert not panel.tcpTranslationStepMm.enabled
    assert not panel.tcpRotationStepDeg.enabled

    panel._taskHomeSetupMode = "connected"
    panel._updateTcpCartesianControlState()
    assert panel.tcpDragEnabledCheckBox.enabled
    assert panel.tcpKeyboardEnabledCheckBox.enabled
    assert panel.solveIkButton.enabled
    assert panel.tcpCartesianNudgeButtons["x"].enabled
    assert panel.tcpTranslationStepMm.enabled
    assert panel.tcpRotationStepDeg.enabled

    panel._taskHomeSetupMode = "unknown"
    panel._updateTcpCartesianControlState()
    assert not panel.tcpDragEnabledCheckBox.enabled
    assert not panel.tcpKeyboardEnabledCheckBox.enabled
    assert not panel.solveIkButton.enabled


def test_manual_draft_refresh_uses_live_ghost_only_when_connected():
    bridge_calls = []
    panel_methods = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        {"_formatManualJogDisplayValues", "setManualJogDraftDisplayResult"},
        {"JOINT_NAMES": JOINT_NAMES},
    )
    panel_type = type("PanelProbe", (), panel_methods)
    method = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {"_onShellManualJogDraftChanged"},
        {
            "Mapping": Mapping,
            "show_goal_robot_joint_positions": lambda positions: (
                bridge_calls.append(dict(positions)) or (True, "ghost updated")
            ),
        },
    )["_onShellManualJogDraftChanged"]

    positions = {name: float(index) for index, name in enumerate(JOINT_NAMES)}
    for setup_mode, message in (
        ("offline", "Home configuration draft retained"),
        ("unknown", "setup mode is unknown"),
    ):
        panel = panel_type()
        panel._taskHomeSetupMode = setup_mode
        panel._manualJogDisplayValues = (1.0, 2.0, 3.0, 4.0, 5.0)
        panel.manualJogDraftStateLabel = _Control()
        method(SimpleNamespace(_robotSimulationPanel=panel), positions)
        assert message in panel.manualJogDraftStateLabel.text
        assert "ghost updated" not in panel.manualJogDraftStateLabel.text
        assert "display-only candidate shown" not in panel.manualJogDraftStateLabel.text
        assert bridge_calls == []

    connected_panel = panel_type()
    connected_panel._taskHomeSetupMode = "connected"
    connected_panel._manualJogDisplayValues = (1.0, 2.0, 3.0, 4.0, 5.0)
    connected_panel.manualJogDraftStateLabel = _Control()
    method(SimpleNamespace(_robotSimulationPanel=connected_panel), positions)
    assert "display-only candidate shown" in connected_panel.manualJogDraftStateLabel.text
    assert bridge_calls == [positions]


def test_home_apply_handler_plans_current_draft_and_does_not_claim_home_validation():
    calls = []
    draft = {name: float(index) for index, name in enumerate(JOINT_NAMES)}
    outcome = SimpleNamespace(success=True, message="Draft applied; review to save Home.",
                              details={"homeSaved": False, "runtimeValidated": False})
    method = _methods(
        PYTHON / "dentobot_workflow/widget_robot_shell.py", "RobotShellWidgetMixin",
        {"_onStep6ApplyTaskHome"},
        {"slicer": SimpleNamespace(util=SimpleNamespace(errorDisplay=lambda message: calls.append(message)))},
    )["_onStep6ApplyTaskHome"]
    panel = SimpleNamespace(manualJogJointPositionsSi=lambda: dict(draft), homeStatusLabel=object())
    facade = SimpleNamespace(
        applyTaskHomeDraft=lambda positions: calls.append(("draft", positions)) or outcome,
        applyTaskHome=lambda: (_ for _ in ()).throw(AssertionError("saved Home must not be used")),
    )
    host = SimpleNamespace(
        _robotWorkflowFacade=facade, _robotSimulationPanel=panel, _workflowActionBusy=False,
        _updateRobotPlacement=lambda: calls.append("placement"),
        _updateStep6PlanningUi=lambda *args, **kwargs: calls.append(("ui", args, kwargs)),
        _setStep6PanelResult=lambda label, result: calls.append(("result", label, result)),
    )
    method(host)
    assert calls[0] == ("draft", draft)
    assert calls[-1] == ("result", panel.homeStatusLabel, outcome)
    assert host._workflowActionBusy is False
    host._workflowActionBusy = True
    before = list(calls)
    method(host)
    assert calls == before


def test_cancelled_rejected_task_home_can_start_a_fresh_review_without_bypassing_gates():
    method = _methods(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        {"_manualTaskHomeReviewControlState"},
        {"JOINT_NAMES": JOINT_NAMES, "Mapping": Mapping, "isfinite": isfinite},
    )["_manualTaskHomeReviewControlState"]
    accepted = {name: 0.0 for name in JOINT_NAMES}
    for setup_mode, live_scene in (("connected", True), ("offline", False)):
        details = {
            "setupMode": setup_mode,
            "staged": False,
            "identityStatus": "current",
            "acceptanceStatus": "rejected",
            "acceptanceFailure": {"code": "task_home_collision_rejected"},
            "acceptanceUncertainty": "",
            "candidateJointPositionsSi": None,
            "acceptedJointPositionsSi": dict(accepted),
        }

        def controls(**changes):
            return method(
                None, live_scene,
                SimpleNamespace(success=True, details={**details, **changes}),
            )

        assert controls() == {
            "group": True, "review": True, "cancel": False,
            "accept": False, "reconcile": False,
        }, setup_mode
        for invalid in (
            {"identityStatus": "stale"},
            {"identityStatus": "unknown"},
            {"setupMode": "unknown"},
            {"acceptanceStatus": "unknown"},
            {"acceptanceUncertainty": "save outcome may have committed"},
        ):
            assert controls(**invalid)["review"] is False, (setup_mode, invalid)
        assert method(
            None, live_scene, SimpleNamespace(success=False, details=details)
        )["review"] is False
        if setup_mode == "connected":
            assert method(
                None, False, SimpleNamespace(success=True, details=details)
            )["review"] is False

        # A rejected staged candidate still needs cancellation/restaging.
        # It cannot be accepted even if it matches the current robot joints.
        staged = controls(staged=True, candidateJointPositionsSi=dict(accepted))
        assert staged["review"] is False
        assert staged["accept"] is False
        assert staged["cancel"] is True
        uncertain = controls(
            staged=True, acceptanceUncertainty="save outcome may have committed"
        )
        assert uncertain["review"] is False
        assert uncertain["accept"] is False
        assert uncertain["cancel"] is False
        assert uncertain["reconcile"] is (setup_mode == "connected")


def test_task_home_review_buttons_require_current_identity_and_matching_candidate():
    method = _methods(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        {"_manualTaskHomeReviewControlState"},
        {
            "JOINT_NAMES": JOINT_NAMES,
            "Mapping": Mapping,
            "isfinite": isfinite,
        },
    )["_manualTaskHomeReviewControlState"]
    accepted = {name: float(index) for index, name in enumerate(JOINT_NAMES)}
    details = {
        "staged": True,
        "candidateJointPositionsSi": dict(accepted),
        "acceptedJointPositionsSi": dict(accepted),
        "identityStatus": "current",
        "acceptanceStatus": "review",
        "setupMode": "connected",
    }
    host = type("WidgetProbe", (), {"_manualTaskHomeReviewControlState": method})()
    assert host._manualTaskHomeReviewControlState(
        True, SimpleNamespace(success=True, details=details)
    ) == {
        "group": True,
        "review": False,
        "cancel": True,
        "accept": True,
        "reconcile": False,
    }
    assert host._manualTaskHomeReviewControlState(
        False, SimpleNamespace(success=True, details=details)
    ) == {
        "group": True,
        "review": False,
        "cancel": True,
        "accept": False,
        "reconcile": False,
    }

    unknown_mode = {
        **details,
        "setupMode": "unknown",
        "acceptanceStatus": "accepted",
    }
    assert host._manualTaskHomeReviewControlState(
        True, SimpleNamespace(success=True, details=unknown_mode)
    ) == {
        "group": True,
        "review": False,
        "cancel": True,
        "accept": False,
        "reconcile": False,
    }
    unknown_uncertain = {
        **unknown_mode,
        "acceptanceStatus": "unknown",
        "acceptanceUncertainty": "save outcome may have committed",
    }
    assert host._manualTaskHomeReviewControlState(
        True,
        SimpleNamespace(success=True, details=unknown_uncertain),
    )["reconcile"] is False

    offline_saved = {
        "setupMode": "offline",
        "staged": False,
        "candidateJointPositionsSi": None,
        "acceptedJointPositionsSi": None,
        "identityStatus": "current",
        "acceptanceStatus": "configuration_saved",
        "configurationReady": True,
        "runtimeValidated": False,
    }
    assert host._manualTaskHomeReviewControlState(
        False, SimpleNamespace(success=True, details=offline_saved)
    ) == {
        "group": True,
        "review": True,
        "cancel": False,
        "accept": False,
        "reconcile": False,
    }
    offline_staged = {
        **offline_saved,
        "staged": True,
        "candidateJointPositionsSi": dict(accepted),
        "acceptanceStatus": "review",
    }
    assert host._manualTaskHomeReviewControlState(
        False, SimpleNamespace(success=True, details=offline_staged)
    )["accept"] is True
    assert host._manualTaskHomeReviewControlState(
        False,
        SimpleNamespace(
            success=False,
            details={
                **offline_staged,
                "identityStatus": "unknown",
                "acceptanceUncertainty": "save outcome may have committed",
            },
        ),
    )["accept"] is False
    for invalid in (
        {**details, "identityStatus": "stale"},
        {**details, "identityStatus": "unknown"},
        {
            **details,
            "candidateJointPositionsSi": {
                **accepted,
                JOINT_NAMES[0]: accepted[JOINT_NAMES[0]] + 1.0,
            },
        },
    ):
        state = host._manualTaskHomeReviewControlState(
            True, SimpleNamespace(success=True, details=invalid)
        )
        assert state["accept"] is False
        assert state["cancel"] is True
        assert state["reconcile"] is False
    roundoff = dict(details)
    roundoff["candidateJointPositionsSi"] = {
        **accepted,
        JOINT_NAMES[0]: accepted[JOINT_NAMES[0]] + 5.0e-13,
    }
    assert host._manualTaskHomeReviewControlState(
        True, SimpleNamespace(success=True, details=roundoff)
    )["accept"] is True

    uncertain = {
        **details,
        "identityStatus": "stale",
        "acceptanceStatus": "unknown",
        "acceptanceUncertainty": "save outcome may have committed",
    }
    uncertain_result = SimpleNamespace(success=False, details=uncertain)
    state = host._manualTaskHomeReviewControlState(True, uncertain_result)
    assert state["accept"] is False
    assert state["cancel"] is False
    assert state["reconcile"] is True
    assert host._manualTaskHomeReviewControlState(False, uncertain_result)[
        "reconcile"
    ] is False
    assert host._manualTaskHomeReviewControlState(
        True,
        SimpleNamespace(
            success=False,
            details={**uncertain, "staged": False},
        ),
    )["reconcile"] is False
    assert host._manualTaskHomeReviewControlState(
        True,
        SimpleNamespace(
            success=False,
            details={**uncertain, "acceptanceUncertainty": ""},
        ),
    )["reconcile"] is False


def test_manual_task_home_stage_cancel_and_accept_delegate_without_preaccept_mutation():
    methods = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {
            "_onStep6ReviewManualTaskHome",
            "_onStep6CancelManualTaskHomeReview",
            "_onStep6AcceptManualTaskHomeReview",
            "_onStep6ReconcileManualTaskHomeAcceptance",
        },
        {
            "JOINT_NAMES": JOINT_NAMES,
            "Mapping": Mapping,
            "isfinite": isfinite,
            "slicer": SimpleNamespace(
                util=SimpleNamespace(errorDisplay=lambda _message: None)
            ),
        },
    )
    accepted = {name: float(index) / 10.0 for index, name in enumerate(JOINT_NAMES)}
    candidate = {**accepted, JOINT_NAMES[0]: accepted[JOINT_NAMES[0]] + 0.1}
    staged = SimpleNamespace(
        success=True,
        message="review staged",
        details={
            "staged": True,
            "candidateJointPositionsSi": candidate,
            "acceptedJointPositionsSi": accepted,
            "identityStatus": "current",
            "acceptanceStatus": "review",
        },
    )
    cancelled = SimpleNamespace(
        success=True,
        message="review cancelled",
        details={
            "staged": False,
            "candidateJointPositionsSi": None,
            "acceptedJointPositionsSi": accepted,
            "identityStatus": "current",
            "acceptanceStatus": "review",
        },
    )
    rejected = SimpleNamespace(
        success=False,
        message="candidate differs from accepted robot state",
        details={**staged.details, "acceptanceStatus": "rejected"},
    )
    accepted_result = SimpleNamespace(
        success=True,
        message="Task Home accepted",
        details={
            "staged": False,
            "candidateJointPositionsSi": None,
            "acceptedJointPositionsSi": accepted,
            "identityStatus": "current",
            "acceptanceStatus": "accepted",
            "setupMode": "connected",
        },
    )

    class Panel:
        def __init__(self, draft):
            self.draft = dict(draft)
            self.accepted_mirrors = []
            self.review_results = []
            self.taskHomeReviewStatusLabel = _Control()
            self.draft_clears = 0

        def manualJogJointPositionsSi(self):
            return dict(self.draft)

        def setManualTaskHomeReviewResult(self, result):
            self.review_results.append(result)
            details = result.details
            self.taskHomeReviewStatusLabel.text = (
                "Failure evidence: " + str(details.get("failureEvidence"))
                + " Acceptance uncertainty: "
                + str(details.get("acceptanceUncertainty"))
            )

        def setManualJogAcceptedState(self, positions, *, preserve_draft=False):
            self.accepted_mirrors.append((dict(positions), preserve_draft))

        def clearManualJogDraft(self):
            self.draft_clears += 1
            self.draft.clear()

    class Facade:
        def __init__(self):
            self.calls = []
            self.status = SimpleNamespace(
                success=True,
                message="current review identity",
                details={
                    "staged": False,
                    "candidateJointPositionsSi": None,
                    "acceptedJointPositionsSi": accepted,
                    "identityStatus": "current",
                    "acceptanceStatus": "review",
                },
            )
            self.accept_result = rejected
            self.reconcile_result = SimpleNamespace(
                success=False,
                message="live Home state could not be confirmed",
                details={
                    **staged.details,
                    "identityStatus": "stale",
                    "acceptanceStatus": "unknown",
                    "acceptanceUncertainty": "save outcome may have committed",
                    "failureEvidence": {"save": "result unavailable"},
                },
            )

        def manualTaskHomeReview(self):
            self.calls.append(("review",))
            return self.status

        def stageManualTaskHomeReview(self, positions):
            self.calls.append(("stage", dict(positions)))
            self.status = staged
            return staged

        def cancelManualTaskHomeReview(self):
            self.calls.append(("cancel",))
            self.status = cancelled
            return cancelled

        def acceptManualTaskHomeReview(self):
            self.calls.append(("accept",))
            return self.accept_result

        def reconcileManualTaskHomeAcceptance(self):
            self.calls.append(("reconcile_home",))
            return self.reconcile_result

        def saveTaskHome(self):
            raise AssertionError("Home review must not call direct saveTaskHome")

        def guardManualRobotJog(self, _positions):
            raise AssertionError("Home review must never send motion")

    facade = Facade()
    panel = Panel(candidate)
    host = type(
        "ShellProbe",
        (),
        {
            **methods,
            "_updateStep6PlanningUi": lambda self, *_args, **_kwargs: None,
        },
    )()
    host._robotSimulationPanel = panel
    host._robotWorkflowFacade = facade
    host._workflowActionBusy = False
    host._onStep6ReviewManualTaskHome()
    assert facade.calls == [("review",), ("stage", candidate)]
    assert set(facade.calls[1][1]) == set(JOINT_NAMES)
    assert panel.accepted_mirrors == []
    assert host._workflowActionBusy is False

    host._onStep6CancelManualTaskHomeReview()
    assert facade.calls[-1] == ("cancel",)
    assert panel.accepted_mirrors == []

    host._onStep6AcceptManualTaskHomeReview()
    assert facade.calls[-1] == ("accept",)
    assert panel.accepted_mirrors == []

    facade.accept_result = accepted_result
    host._onStep6AcceptManualTaskHomeReview()
    assert facade.calls[-1] == ("accept",)
    assert panel.accepted_mirrors == [(accepted, True)]
    assert host._workflowActionBusy is False

    facade.accept_result = SimpleNamespace(
        success=True,
        message="offline configuration saved",
        details={
            **accepted_result.details,
            "setupMode": "offline",
            "acceptanceStatus": "configuration_saved",
        },
    )
    host._onStep6AcceptManualTaskHomeReview()
    assert panel.accepted_mirrors == [(accepted, True)]

    facade.accept_result = SimpleNamespace(
        success=True,
        message="setup mode unavailable",
        details={
            **accepted_result.details,
            "setupMode": "unknown",
        },
    )
    host._onStep6AcceptManualTaskHomeReview()
    assert panel.accepted_mirrors == [(accepted, True)]

    panel.draft = {**candidate, "unexpected_joint": 0.0}
    stage_calls_before = sum(call[0] == "stage" for call in facade.calls)
    host._onStep6ReviewManualTaskHome()
    stage_calls_after = sum(call[0] == "stage" for call in facade.calls)
    assert stage_calls_before == stage_calls_after
    assert panel.accepted_mirrors == [(accepted, True)]
    assert "exactly J1–J5" in panel.taskHomeReviewStatusLabel.text

    draft_before_reconcile = dict(panel.draft)
    mirrors_before_reconcile = list(panel.accepted_mirrors)
    reconciled = facade.reconcile_result
    host._onStep6ReconcileManualTaskHomeAcceptance()
    assert facade.calls.count(("reconcile_home",)) == 1
    assert facade.calls[-1] == ("reconcile_home",)
    assert panel.review_results[-1] is reconciled
    assert panel.draft == draft_before_reconcile
    assert panel.draft_clears == 0
    assert panel.accepted_mirrors == mirrors_before_reconcile
    assert "Reconcile Task Home State remains unresolved" in panel.taskHomeReviewStatusLabel.text
    assert "issued no Home save or jog" in panel.taskHomeReviewStatusLabel.text
    assert "save outcome may have committed" in panel.taskHomeReviewStatusLabel.text
    assert "result unavailable" in panel.taskHomeReviewStatusLabel.text
    assert host._workflowActionBusy is False

    resolved = SimpleNamespace(
        success=True,
        message="facade confirmed the saved Home after task identity changed",
        details={
            **staged.details,
            "identityStatus": "stale",
            "acceptanceStatus": "accepted",
            "acceptanceUncertainty": "",
        },
    )
    facade.reconcile_result = resolved
    host._onStep6ReconcileManualTaskHomeAcceptance()
    assert facade.calls.count(("reconcile_home",)) == 2
    assert panel.review_results[-1] is resolved
    assert panel.draft == draft_before_reconcile
    assert panel.accepted_mirrors == mirrors_before_reconcile
    assert "Reconcile Task Home State succeeded" in panel.taskHomeReviewStatusLabel.text
    assert "no Home save or jog" in panel.taskHomeReviewStatusLabel.text


def test_step6_two_area_navigation_ownership_and_preview_authority():
    titles = workspace_for_stage(10).substep_titles
    assert len(titles) == 5
    assert titles[3:] == ("Planning & Diagnostics", "Preview & Control")

    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    owners = _class_constant(
        panel_path, "DENTORobotSimulationPanel", "ACTION_OWNER_SUBSTEP"
    )
    assert owners["connect"] == 1
    assert owners["review_task_home"] == owners["cancel_task_home_review"] == (2, 3)
    assert owners["accept_task_home_review"] == owners["reconcile_task_home"] == (2, 3)
    assert owners["apply_home"] == 2
    assert owners["review_limits"] == 3
    assert owners["confirm_task"] == 3
    assert all(
        owners[action] == 3
        for action in (
            "plan_approach",
            "plan_drilling",
            "check_preentry_ik",
            "check_planning_p1",
            "check_planning_p2",
            "check_planning_p3",
        )
    )
    assert all(
        owners[action] == 4
        for action in (
            "preview_approach",
            "preview_drilling",
            "stop_preview",
            "return_home",
        )
    )


    shell_path = PYTHON / "dentobot_workflow/widget_robot_shell.py"
    shell_source = shell_path.read_text(encoding="utf-8")
    assert "for title in workspace_for_stage(10).substep_titles" in shell_source
    navigator = _method_node(
        shell_path, "RobotShellWidgetMixin", "_configureRobotSimulationShellSubstep"
    )
    visible_assignment = next(
        node
        for node in ast.walk(navigator)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "visible_by_substep"
            for target in node.targets
        )
    )
    visible = {
        key.value: {_attribute_name(item) for item in value.elts}
        for key, value in zip(
            visible_assignment.value.keys, visible_assignment.value.values, strict=True
        )
    }
    assert visible[3] == {"self._robotSimulationPanel.workbenchGroup"}
    assert visible[2] == {"self._robotSimulationPanel.homeGroup"}
    assert "self._robotSimulationPanel.manualJogGroup" not in visible[2]
    assert visible[4] == {"self._robotSimulationPanel.previewControlGroup"}
    assert "controls.setParent(panel.homeGroup)" not in shell_source
    assert "controls.setParent(panel.manualJogGroup)" not in shell_source
    assert "panel._manualJogControlsInHomeGroup = index == 2" in shell_source
    home_action_visibility = [
        ast.unparse(node.value)
        for node in ast.walk(navigator)
        if isinstance(node, ast.Assign)
        and any(
            _attribute_name(target)
            == "self._robotSimulationPanel.applyTaskHomeButton.visible"
            for target in node.targets
        )
    ]
    assert home_action_visibility == ["index == 2"]

    bootstrap_source = (PYTHON / "dentobot_workflow/widget_bootstrap.py").read_text(
        encoding="utf-8"
    )
    robot_source = (PYTHON / "dentobot_workflow/widget_robot.py").read_text(
        encoding="utf-8"
    )
    assert "previewTrajectoryMotionButton.connect(" not in bootstrap_source
    assert "onPreviewTrajectoryMotion" not in robot_source
    assert "previewPlan(" not in robot_source

    panel_source = panel_path.read_text(encoding="utf-8")
    assert panel_source.count("self.manualJogJointControls = {}") == 1
    assert 'self.step63TabWidget.addTab(self.step63ManualPage, "Manual")' in panel_source
    assert 'self.step63TabWidget.addTab(self.step63WorkspacePage, "Workspace")' in panel_source
    assert 'self.step63TabWidget.addTab(self.step63PlanPage, "Plan")' in panel_source
    assert 'self.step63ManualTabWidget.addTab(self.manualJogGroup, "Joints")' in panel_source
    assert 'self.step63ManualTabWidget.addTab(self.goalGroup, "TCP")' in panel_source
    assert "qt.QVBoxLayout(dialog).addWidget(self.manualHistoryGroup)" in panel_source
    assert "qt.QVBoxLayout(dialog).addWidget(self.anatomyReviewGroup)" in panel_source
    assert "self.manualHistoryGroup.hide()" in panel_source
    assert "self.anatomyReviewGroup.hide()" in panel_source
    for button in (
        "previewApproachButton",
        "previewDrillingButton",
        "stopPreviewButton",
        "returnHomeButton",
    ):
        assert panel_source.count(f"self.{button}.clicked.connect(") == 1
        assert f"self.{button} = qt.QPushButton(" in panel_source
    assert '"Preview Approach", self.previewControlGroup' in panel_source
    assert '"Preview Drill", self.previewControlGroup' in panel_source
    assert '"Stop Preview", self.previewControlGroup' in panel_source
    assert '"Guarded Return Home", self.previewControlGroup' in panel_source
    assert "Partial diagnostic paths remain display-only." in panel_source

    update = _method_node(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        "_updateStep6PlanningUi",
    )
    enabled = {}
    for node in ast.walk(update):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            name = _attribute_name(target)
            if name in {
                "panel.previewApproachButton.enabled",
                "panel.previewDrillingButton.enabled",
            }:
                enabled[name] = ast.unparse(node.value)
    approach = enabled["panel.previewApproachButton.enabled"]
    drilling = enabled["panel.previewDrillingButton.enabled"]
    for condition in (
        "drilling_preflight_ready",
        "isinstance(facade_plan, PhasePlan)",
        "facade_plan.success",
        "facade_plan.requested_phase == MotionPhase.APPROACH.value",
        "task_ready",
        "ros2_active",
        "not preview_active",
        "not away_from_home",
    ):
        assert condition in approach
    for condition in (
        "drilling_preflight_ready",
        "approach_complete",
        "isinstance(facade_plan, PhasePlan)",
        "facade_plan.success",
        "facade_plan.requested_phase == MotionPhase.DRILLING.value",
        "task_ready",
        "ros2_active",
        "not preview_active",
    ):
        assert condition in drilling
    # r16 (2026-10-03): Drill follows a completed Approach, so the robot is
    # necessarily away from Task Home; only Approach preview requires Home.
    assert "away_from_home" not in drilling

    imported_record = ast.dump(
        _method_node(
            ROBOT_MANUAL,
            "RobotManualWidgetMixin",
            "_onStep6ImportManualRecord",
        )
    )
    assert "previewApproachButton" not in imported_record
    assert "previewDrillingButton" not in imported_record
    stop = ast.unparse(
        _method_node(shell_path, "RobotShellWidgetMixin", "_onStep6StopPreview")
    )
    assert "resetPreviewProgress(result.message)" in stop


def test_step63_owner_handoff_preserves_originating_workbench_tab():
    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    methods = _methods(
        panel_path,
        "DENTORobotSimulationPanel",
        {"_openStep63Owner", "_returnToStep63"},
        {},
    )
    panel = type("Step63OwnerHandoffProbe", (), methods)()
    navigation = []
    panel._activeSubstep = 3
    panel._step63Navigate = navigation.append
    panel._step63ReturnTab = 0
    panel.step63TabWidget = SimpleNamespace(currentIndex=2)
    button_type = type(
        "Button",
        (),
        {"visible": False, "hide": lambda self: setattr(self, "visible", False)},
    )
    panel.returnFromBaseButton = button_type()
    panel.returnFromHomeButton = button_type()

    panel._openStep63Owner(1)
    assert navigation == [1]
    assert panel._step63ReturnTab == 2
    assert panel.returnFromBaseButton.visible
    assert not panel.returnFromHomeButton.visible

    panel._returnToStep63()
    assert navigation == [1, 3]
    assert panel.step63TabWidget.currentIndex == 2
    assert not panel.returnFromBaseButton.visible
    assert not panel.returnFromHomeButton.visible


def test_manual_jog_action_buttons_are_split_into_narrow_rows():
    init = _method_node(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        "__init__",
    )
    buttons = {
        "checkManualDraftStateButton",
        "reconcileManualJogButton",
        "guardedManualJogButton",
        "exportManualRecordButton",
    }
    horizontal_layouts = {
        target.id
        for node in ast.walk(init)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and _attribute_name(node.value.func) == "qt.QHBoxLayout"
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    rows = {}
    for node in ast.walk(init):
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Attribute)
            or node.func.attr != "addWidget"
            or not isinstance(node.func.value, ast.Name)
            or node.func.value.id not in horizontal_layouts
            or not node.args
        ):
            continue
        button = _attribute_name(node.args[0]).removeprefix("self.")
        if button in buttons:
            rows.setdefault(node.func.value.id, set()).add(button)

    action_rows = list(rows.values())
    assert set.union(*action_rows) == buttons
    assert any(
        isinstance(node, ast.Call)
        and _attribute_name(node.func) == "self._manualJogControlsLayout.addWidget"
        and node.args
        and _attribute_name(node.args[0]) == "self.resetManualJogDraftButton"
        for node in ast.walk(init)
    )
    assert len(action_rows) >= 2
    assert max(map(len, action_rows)) <= 3


def test_cartesian_tcp_surface_is_step6_3_owned_and_explicitly_drag_gated():
    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    owners = _class_constant(
        panel_path, "DENTORobotSimulationPanel", "ACTION_OWNER_SUBSTEP"
    )
    assert owners["create_goal"] == -1
    assert owners["solve_ik"] == 3
    assert owners["set_tcp_drag_enabled"] == owners["nudge_tcp_goal"] == 3
    assert owners["plan_goal"] == -1

    source = panel_path.read_text(encoding="utf-8")
    assert '"Enable TCP Drag"' in source
    assert "createGoalButton" not in source
    assert "Create / Show TCP Goal" not in source
    assert "self.tcpDragEnabledCheckBox.checked = False" in source
    assert "exact J1–J5 MoveIt kinematic IK" in source
    assert "Pitch and yaw tilt the TCP/drill " in source
    assert "Axial roll is unconstrained by the five-DOF arm." in source
    assert '"Roll (local TCP, deg)"' not in source
    assert "they do not check collision validity" in source
    assert "collision-aware evaluation and stages its J1–J5 result as a draft" in source
    assert "A failed or missing live IK pose remains visual/rejected review." in source
    assert "Guarded Jog after authoritative guard acknowledgement advances accepted " in source
    assert "no route or preview authority" in source
    assert "translation_axis: int | None" in source
    assert "rotation_axis: int | None" in source
    assert "J1–J5 " in source
    assert "numeric fields accept typing and focused arrow-key adjustment." in source

    show_result = _methods(
        panel_path,
        "DENTORobotSimulationPanel",
        {"showGoalResult"},
        {"_show_result": lambda label, result: setattr(label, "text", result.message)},
    )["showGoalResult"]
    status = SimpleNamespace(text="")
    panel = SimpleNamespace(
        goalStatusLabel=status,
        _show_result=lambda label, result: setattr(label, "text", result.message),
    )
    show_result(panel, SimpleNamespace(message="IK rejected"))
    assert "IK rejected" in status.text
    assert "kinematic-only ghost review, not collision validity" in status.text
    assert "Guarded Jog with authoritative guard acknowledgement" in status.text
    assert "no route or preview authority" in status.text

    methods = _methods(
        panel_path,
        "DENTORobotSimulationPanel",
        {"_tcpCartesianControlsAllowed", "_onTcpCartesianNudge"},
        {"isfinite": isfinite},
    )
    panel_type = type("TcpProbe", (), methods)
    calls = []
    panel = panel_type()
    panel._activeSubstep = 3
    panel._taskHomeSetupMode = "connected"
    panel.goalGroup = SimpleNamespace(visible=True)
    panel._tcpDragEnabled = False
    panel.tcpDragEnabledCheckBox = SimpleNamespace(checked=False)
    panel.tcpTranslationStepMm = SimpleNamespace(value=1.25)
    panel.tcpRotationStepDeg = SimpleNamespace(value=4.0)
    panel._invoke = lambda action, payload: calls.append((action, payload))

    panel._onTcpCartesianNudge(0, None, 1.0)
    assert calls == []

    panel._tcpDragEnabled = True
    panel.tcpDragEnabledCheckBox.checked = True
    panel._onTcpCartesianNudge(0, None, -1.0)
    assert calls == [
        (
            "nudge_tcp_goal",
            {
                "translation_ras_mm": [-1.25, 0.0, 0.0],
                "rotation_local_rpy_deg": [0.0, 0.0, 0.0],
                "source": "button",
            },
        )
    ]
    payload = calls[0][1]
    assert set(payload) == {
        "translation_ras_mm",
        "rotation_local_rpy_deg",
        "source",
    }
    assert sum(value != 0.0 for value in payload["translation_ras_mm"]) == 1
    assert sum(value != 0.0 for value in payload["rotation_local_rpy_deg"]) == 0


def test_tcp_keyboard_binding_mapping_and_text_editor_gate():
    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    bindings = _class_constant(
        panel_path, "DENTORobotSimulationPanel", "TCP_KEY_BINDINGS"
    )
    assert dict(
        (key, (translation, rotation, direction))
        for key, translation, rotation, direction in bindings
    ) == {
        "Left": (0, None, -1.0),
        "Right": (0, None, 1.0),
        "Down": (1, None, -1.0),
        "Up": (1, None, 1.0),
        "PgDown": (2, None, -1.0),
        "PgUp": (2, None, 1.0),
        "Ctrl+Down": (None, 1, -1.0),
        "Ctrl+Up": (None, 1, 1.0),
        "Shift+Left": (None, 2, -1.0),
        "Shift+Right": (None, 2, 1.0),
    }
    assert "Shift+Down" not in dict((key, value) for key, *value in bindings)
    assert "Shift+Up" not in dict((key, value) for key, *value in bindings)
    help_text = _method_node(panel_path, "DENTORobotSimulationPanel", "__init__")
    help_source = ast.unparse(help_text)
    assert "Axial roll is unconstrained by the five-DOF arm." in help_source
    assert "Ctrl+↓/↑ pitch" in help_source
    assert "Shift+←/→ yaw" in help_source

    methods = _methods(
        panel_path,
        "DENTORobotSimulationPanel",
        {"_onTcpCartesianNudge", "_onTcpKeyboardNudge"},
        {"isfinite": isfinite},
    )
    panel_type = type("TcpKeyboardProbe", (), methods)
    calls = []
    panel = panel_type()
    panel._tcpCartesianControlsAllowed = lambda: True
    panel.tcpKeyboardEnabledCheckBox = SimpleNamespace(checked=True)
    panel.tcpTranslationStepMm = SimpleNamespace(value=1.0)
    panel.tcpRotationStepDeg = SimpleNamespace(value=5.0)
    panel._hasTcpTextEditorFocus = lambda: False
    panel._invoke = lambda action, payload: calls.append((action, payload))
    panel._onTcpKeyboardNudge(None, 1, -1.0)
    assert calls[0][1] == {
        "translation_ras_mm": [0.0, 0.0, 0.0],
        "rotation_local_rpy_deg": [0.0, -5.0, 0.0],
        "source": "keyboard",
    }
    panel._hasTcpTextEditorFocus = lambda: True
    panel._onTcpKeyboardNudge(0, None, 1.0)
    assert len(calls) == 1


def test_manual_joint_keyboard_nudges_are_opt_in_draft_only_and_unit_aware():
    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    bindings = _class_constant(
        panel_path, "DENTORobotSimulationPanel", "MANUAL_JOG_KEY_BINDINGS"
    )
    assert bindings == (
        ("Q", 0, 1.0),
        ("A", 0, -1.0),
        ("W", 1, 1.0),
        ("S", 1, -1.0),
        ("E", 2, 1.0),
        ("D", 2, -1.0),
        ("R", 3, 1.0),
        ("F", 3, -1.0),
        ("T", 4, 1.0),
        ("G", 4, -1.0),
    )
    initializer = ast.unparse(
        _method_node(panel_path, "DENTORobotSimulationPanel", "__init__")
    )
    assert "Enable joint keyboard nudges" in initializer
    assert "self.manualJogKeyboardEnabledCheckBox.checked = False" in initializer
    assert "degrees_step:g" in initializer
    assert "millimeters_step:g" in initializer
    assert "((0.1, 0.1), (0.5, 0.5), (1.0, 1.0))" in initializer
    assert "J1 Q/A, J2 W/S, J3 E/D, J4 R/F, J5 T/G" in initializer

    class Signal:
        def __init__(self):
            self.callbacks = []

        def connect(self, callback):
            self.callbacks.append(callback)

        def disconnect(self, callback):
            self.callbacks.remove(callback)

        def emit(self, *args):
            for callback in tuple(self.callbacks):
                callback(*args)

    class KeySequence:
        def __init__(self, key):
            self.key = key

    class Shortcut:
        def __init__(self, sequence, parent):
            self.sequence = sequence
            self.parent = parent
            self.activated = Signal()
            self.enabled = True

        def trigger(self):
            if self.enabled:
                self.activated.emit()

    application = SimpleNamespace(focusChanged=Signal())
    qt = SimpleNamespace(
        QShortcut=Shortcut,
        QKeySequence=KeySequence,
        Qt=SimpleNamespace(WidgetWithChildrenShortcut="widget_with_children"),
        QApplication=SimpleNamespace(instance=lambda: application),
    )

    def to_si(j1, j2, j3, j4, j5):
        return {
            JOINT_NAMES[0]: radians(j1),
            JOINT_NAMES[1]: j2 / 1000.0,
            JOINT_NAMES[2]: radians(j3),
            JOINT_NAMES[3]: j4 / 1000.0,
            JOINT_NAMES[4]: radians(j5),
        }

    methods = _methods(
        panel_path,
        "DENTORobotSimulationPanel",
        {
            "_setupManualJogKeyboardShortcuts",
            "_connectManualJogKeyboardFocusUpdates",
            "_manualJogKeyboardControlsAllowed",
            "_updateManualJogKeyboardControlState",
            "_onManualJogKeyboardNudge",
            "_onManualJogNumericChanged",
            "_updateManualJogDraftFromControls",
            "_formatManualJogDisplayValues",
            "manualJogJointPositionsSi",
        },
        {
            "JOINT_NAMES": JOINT_NAMES,
            "isfinite": math.isfinite,
            "joint_positions_si_from_display": to_si,
            "qt": qt,
        },
    )
    panel_type = type("ManualJointKeyboardProbe", (), methods)
    panel_type.MANUAL_JOG_KEY_BINDINGS = bindings
    panel = panel_type()
    panel._activeSubstep = 3
    panel.manualJogGroup = SimpleNamespace(visible=True, destroyed=Signal())
    panel._manualJogAvailable = True
    panel._manualJogGuardContextAvailable = True
    panel._manualJogBusy = False
    panel._manualJogDraftInitialized = False
    panel.manualJogReconciliationRequired = False
    panel.manualJogKeyboardEnabledCheckBox = _Control()
    panel.manualJogKeyboardEnabledCheckBox.checked = False
    panel.manualJogKeyboardStepComboBox = SimpleNamespace(
        currentData=(0.25, 0.75), enabled=False
    )
    panel._manualJogKeyboardShortcuts = []
    text_focus = [False]
    panel._hasTcpTextEditorFocus = lambda: text_focus[0]
    panel._updateManualJogKeyboardControlState()

    class SpinBox(_Control):
        def __init__(self, value):
            super().__init__(value)
            self.minimum, self.maximum = -100.0, 100.0
            self.on_value_changed = None

        def setValue(self, value):
            super().setValue(value)
            if not self._signals_blocked and self.on_value_changed:
                self.on_value_changed(self.value)

    values = (10.0, 2.0, -5.0, 1.0, 30.0)
    mechanical = ((-100.0, 100.0),) * 5
    panel._manualJogLimits = (mechanical, mechanical)
    panel._manualJogSliderRanges = mechanical
    panel._manualJogDisplayValues = values
    accepted = {joint: float(index) for index, joint in enumerate(JOINT_NAMES)}
    panel._manualJogAcceptedJointPositionsSi = accepted.copy()
    panel.manualJogJointControls = {}
    for index, joint in enumerate(JOINT_NAMES):
        spinbox = SpinBox(values[index])
        spinbox.on_value_changed = (
            lambda value, name=joint: panel._onManualJogNumericChanged(name, value)
        )
        panel.manualJogJointControls[joint] = (_Control(), spinbox, _Control())
    panel.manualJogDraftStateLabel = _Control()
    panel.setManualJogAvailability = lambda *_args: None
    panel._setManualJogStatus = lambda *_args: None
    updates = []
    panel._invoke = lambda action, state: updates.append((action, dict(state)))
    panel._setupManualJogKeyboardShortcuts()
    panel._updateManualJogKeyboardControlState()

    shortcuts = panel._manualJogKeyboardShortcuts
    assert [shortcut.sequence.key for shortcut in shortcuts] == [
        key for key, _index, _direction in bindings
    ]
    assert all(shortcut.parent is panel.manualJogGroup for shortcut in shortcuts)
    assert all(
        shortcut.context == "widget_with_children" and not shortcut.autoRepeat
        for shortcut in shortcuts
    )
    assert not any(shortcut.enabled for shortcut in shortcuts)
    shortcuts[0].trigger()
    assert updates == []

    panel.manualJogKeyboardEnabledCheckBox.checked = True
    panel._updateManualJogKeyboardControlState()
    assert panel.manualJogKeyboardStepComboBox.enabled
    assert all(shortcut.enabled for shortcut in shortcuts)
    for shortcut, (_key, joint_index, direction) in zip(
        shortcuts, bindings, strict=True
    ):
        before = tuple(
            float(panel.manualJogJointControls[joint][1].value)
            for joint in JOINT_NAMES
        )
        shortcut.trigger()
        after = tuple(
            float(panel.manualJogJointControls[joint][1].value)
            for joint in JOINT_NAMES
        )
        step = 0.25 if joint_index in (0, 2, 4) else 0.75
        assert after[joint_index] == before[joint_index] + step * direction
        assert all(
            after[index] == before[index]
            for index in range(len(JOINT_NAMES))
            if index != joint_index
        )
    assert len(updates) == len(bindings)
    assert all(action == "manual_draft_changed" for action, _state in updates)
    assert panel._manualJogAcceptedJointPositionsSi == accepted

    panel._connectManualJogKeyboardFocusUpdates()
    text_focus[0] = True
    application.focusChanged.emit(None, object())
    assert not any(shortcut.enabled for shortcut in shortcuts)
    before_focus_nudge = tuple(
        float(panel.manualJogJointControls[joint][1].value) for joint in JOINT_NAMES
    )
    panel._onManualJogKeyboardNudge(0, 1.0)
    assert tuple(
        float(panel.manualJogJointControls[joint][1].value) for joint in JOINT_NAMES
    ) == before_focus_nudge
    text_focus[0] = False
    application.focusChanged.emit(None, None)
    assert all(shortcut.enabled for shortcut in shortcuts)
    text_focus[0] = True
    application.focusChanged.emit(None, object())
    panel.manualJogGroup.destroyed.emit(None)
    assert panel._manualJogKeyboardFocusSlot not in application.focusChanged.callbacks
    text_focus[0] = False

    blocked_states = (
        (4, True, False, False),
        (3, True, False, True),
        (3, True, True, False),
    )
    for blocked_state in blocked_states:
        (
            panel._activeSubstep,
            panel.manualJogGroup.visible,
            panel._manualJogBusy,
            panel.manualJogReconciliationRequired,
        ) = blocked_state
        panel._updateManualJogKeyboardControlState()
        assert not panel.manualJogKeyboardEnabledCheckBox.enabled
        assert not panel.manualJogKeyboardStepComboBox.enabled
        assert not any(shortcut.enabled for shortcut in shortcuts)
        assert not panel.manualJogKeyboardEnabledCheckBox.checked


def test_tcp_drag_toggle_and_substep_exit_disable_native_drag_once():
    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    methods = _methods(
        panel_path,
        "DENTORobotSimulationPanel",
        {
            "_onTcpDragEnabledToggled",
            "_setTcpKeyboardChecked",
            "_disableTcpDragForSubstepChange",
            "_updateTcpCartesianControlState",
            "_tcpCartesianControlsAllowed",
            "setActiveSubstep",
            "_updateManualJogKeyboardControlState",
        },
        {},
    )
    panel_type = type("TcpDragGateProbe", (), methods)

    class CheckBox(_Control):
        def __init__(self, checked=False):
            super().__init__()
            self.checked = checked

    calls = []
    panel = panel_type()
    panel._activeSubstep = 3
    panel._taskHomeSetupMode = "connected"
    panel.goalGroup = SimpleNamespace(visible=True)
    panel._tcpDragEnabled = False
    panel.tcpDragEnabledCheckBox = CheckBox(True)
    panel.tcpKeyboardEnabledCheckBox = CheckBox(False)
    panel.solveIkButton = _Control()
    panel._tcpIkAvailable = True
    panel.tcpCartesianNudgeButtons = {"x": _Control()}
    panel.tcpTranslationStepMm = _Control()
    panel.tcpRotationStepDeg = _Control()
    panel._tcpKeyboardShortcuts = [_Control()]
    panel._callbacks = {"set_tcp_drag_enabled": lambda enabled: calls.append(enabled)}
    panel._invoke = lambda action, enabled: calls.append(enabled) or bool(enabled)
    panel._onTcpDragEnabledToggled(True)
    assert panel._tcpDragEnabled
    assert panel.solveIkButton.enabled
    assert calls == [True]

    panel.tcpDragEnabledCheckBox.checked = False
    panel._onTcpDragEnabledToggled(False)
    assert not panel._tcpDragEnabled
    assert not panel.solveIkButton.enabled
    assert calls == [True, False]

    panel.tcpDragEnabledCheckBox.checked = True
    panel._onTcpDragEnabledToggled(True)
    assert panel._tcpDragEnabled
    assert calls == [True, False, True]

    panel.setActiveSubstep(4)
    assert panel._activeSubstep == 4
    assert not panel._tcpDragEnabled
    assert not panel.solveIkButton.enabled
    assert not panel.tcpDragEnabledCheckBox.checked
    assert calls == [True, False, True, False]
    panel.setActiveSubstep(1)
    assert calls == [True, False, True, False]

    failed = panel_type()
    failed._activeSubstep = 3
    failed._taskHomeSetupMode = "connected"
    failed.goalGroup = SimpleNamespace(visible=True)
    failed._tcpDragEnabled = False
    failed.tcpDragEnabledCheckBox = CheckBox(True)
    failed.tcpKeyboardEnabledCheckBox = CheckBox(False)
    failed.tcpCartesianNudgeButtons = {"x": _Control()}
    failed.tcpTranslationStepMm = _Control()
    failed.tcpRotationStepDeg = _Control()
    failed.solveIkButton = _Control()
    failed._tcpIkAvailable = True
    failed._tcpKeyboardShortcuts = [_Control()]
    failed.runtimeStatusLabel = _Control()
    failed._callbacks = {"set_tcp_drag_enabled": lambda _enabled: False}
    failure_calls = []
    failed._invoke = lambda action, enabled: (
        failure_calls.append((action, enabled)) or False
    )
    failed._onTcpDragEnabledToggled(True)
    failed._updateTcpCartesianControlState()
    assert not failed._tcpDragEnabled
    assert not failed.tcpDragEnabledCheckBox.checked
    assert not failed.tcpCartesianNudgeButtons["x"].enabled
    assert not failed.tcpTranslationStepMm.enabled
    assert not failed.tcpRotationStepDeg.enabled
    assert not failed.solveIkButton.enabled
    assert not failed.tcpKeyboardEnabledCheckBox.enabled
    assert failed.runtimeStatusLabel.text.startswith("TCP drag remains disabled")
    assert failure_calls == [
        ("set_tcp_drag_enabled", True),
        ("set_tcp_drag_enabled", False),
    ]


def test_solve_ik_stays_disabled_until_drag_ack_and_capability_refresh_respects_gate():
    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    methods = _methods(
        panel_path,
        "DENTORobotSimulationPanel",
        {"_tcpCartesianControlsAllowed", "_updateTcpCartesianControlState"},
        {},
    )
    panel_type = type("TcpIkEnableProbe", (), methods)
    panel = panel_type()
    panel._activeSubstep = 3
    panel._taskHomeSetupMode = "connected"
    panel.goalGroup = SimpleNamespace(visible=True)
    panel._tcpDragEnabled = False
    panel._tcpIkAvailable = True
    panel.tcpDragEnabledCheckBox = SimpleNamespace(checked=False, enabled=False)
    panel.tcpKeyboardEnabledCheckBox = SimpleNamespace(checked=False, enabled=False)
    panel.solveIkButton = _Control()
    panel.tcpCartesianNudgeButtons = {"x": _Control()}
    panel.tcpTranslationStepMm = _Control()
    panel.tcpRotationStepDeg = _Control()
    panel._tcpKeyboardShortcuts = [_Control()]

    panel._updateTcpCartesianControlState()
    assert not panel.solveIkButton.enabled
    assert not panel.tcpCartesianNudgeButtons["x"].enabled

    panel._tcpDragEnabled = True
    panel.tcpDragEnabledCheckBox.checked = True
    panel._updateTcpCartesianControlState()
    assert panel.solveIkButton.enabled
    assert panel.tcpCartesianNudgeButtons["x"].enabled

    update = _method_node(panel_path, "DENTORobotSimulationPanel", "updateCapabilities")
    assignments = [
        node
        for node in ast.walk(update)
        if isinstance(node, ast.Assign)
    ]
    assert not any(
        any(_attribute_name(target) == "self.solveIkButton.enabled" for target in node.targets)
        for node in assignments
    )
    assert any(
        any(_attribute_name(target) == "self._tcpIkAvailable" for target in node.targets)
        and "capabilities.ik_available" in ast.unparse(node.value)
        for node in assignments
    )
    assert any(
        isinstance(node, ast.Call)
        and _attribute_name(node.func) == "self._updateTcpCartesianControlState"
        for node in ast.walk(update)
    )


def test_tcp_ik_solution_stages_only_complete_finite_mechanical_j1_j5_draft():
    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    names = {
        "stageTcpIkSolution",
        "_setManualJogDraftValues",
        "_formatManualJogDisplayValues",
        "_setManualJogStatus",
    }
    methods = _methods(
        panel_path,
        "DENTORobotSimulationPanel",
        names,
        {
            "Mapping": Mapping,
            "JOINT_NAMES": JOINT_NAMES,
            "degrees": degrees,
            "isfinite": isfinite,
        },
    )
    panel_type = type("TcpIkStageProbe", (), methods)

    class SpinBox(_Control):
        def __init__(self, minimum, maximum):
            super().__init__()
            self.minimum, self.maximum = minimum, maximum

    controls = {}
    mechanical = (
        (-180.0, 180.0),
        (0.0, 80.0),
        (-90.0, 300.0),
        (0.0, 75.0),
        (-180.0, 180.0),
    )
    for joint, (minimum, maximum) in zip(JOINT_NAMES, mechanical, strict=True):
        controls[joint] = (_Control(), SpinBox(minimum, maximum), _Control())

    def make_panel():
        panel = panel_type()
        panel._manualJogLimits = (mechanical, mechanical)
        panel._manualJogSliderRanges = mechanical
        panel._manualJogMechanicalLimits = mechanical
        panel._manualJogAvailable = True
        panel._manualJogGuardContextAvailable = True
        panel._manualJogDisplayValues = (10.0, 25.0, 30.0, 40.0, 50.0)
        panel._manualJogAcceptedJointPositionsSi = {
            joint: float(index) for index, joint in enumerate(JOINT_NAMES)
        }
        panel.manualJogJointControls = controls
        panel.manualJogDraftStateLabel = _Control()
        panel.manualJogStatusLabel = _Control()
        panel.setManualJogAvailability = lambda *_args: None
        panel._invoke_calls = []
        panel._invoke = lambda action, state: panel._invoke_calls.append(
            (action, dict(state))
        )
        panel.manualJogJointPositionsSi = lambda: {
            JOINT_NAMES[0]: math.radians(panel._manualJogDisplayValues[0]),
            JOINT_NAMES[1]: panel._manualJogDisplayValues[1] / 1000.0,
            JOINT_NAMES[2]: math.radians(panel._manualJogDisplayValues[2]),
            JOINT_NAMES[3]: panel._manualJogDisplayValues[3] / 1000.0,
            JOINT_NAMES[4]: math.radians(panel._manualJogDisplayValues[4]),
        }
        return panel

    panel = make_panel()
    accepted_before = dict(panel._manualJogAcceptedJointPositionsSi)
    candidate = {
        JOINT_NAMES[0]: math.radians(20.0),
        JOINT_NAMES[1]: 0.030,
        JOINT_NAMES[2]: math.radians(45.0),
        JOINT_NAMES[3]: 0.050,
        JOINT_NAMES[4]: math.radians(-60.0),
    }
    assert panel.stageTcpIkSolution(candidate) is True
    assert tuple(round(value, 2) for value in panel._manualJogDisplayValues) == (
        20.0,
        30.0,
        45.0,
        50.0,
        -60.0,
    )
    assert panel._invoke_calls[-1][0] == "manual_draft_changed"
    assert set(panel._invoke_calls[-1][1]) == set(JOINT_NAMES)
    assert panel._manualJogAcceptedJointPositionsSi == accepted_before
    assert "not accepted robot state" in panel.manualJogDraftStateLabel.text

    for invalid in (
        {joint: value for joint, value in candidate.items() if joint != JOINT_NAMES[4]},
        {**candidate, JOINT_NAMES[0]: math.nan},
        {**candidate, "unexpected_joint": 0.0},
        {**candidate, JOINT_NAMES[1]: 0.500},
    ):
        panel = make_panel()
        draft_before = tuple(panel._manualJogDisplayValues)
        assert panel.stageTcpIkSolution(invalid) is False
        assert panel._manualJogDisplayValues == draft_before
        assert panel._invoke_calls == []
        assert "not staged" in panel.manualJogDraftStateLabel.text
        assert panel.manualJogStatusLabel.text.startswith(
            "TCP IK result rejected; draft retained."
        )


def test_motion_diagnostic_target_coordinates_are_display_only_and_exact_session_gated():
    panel_method = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        {"_motionDiagnosticTargetConditioningText"},
        {"Mapping": Mapping, "isfinite": isfinite},
    )["_motionDiagnosticTargetConditioningText"]
    if isinstance(panel_method, staticmethod):
        panel_method = panel_method.__func__
    conditioning = {
        "world_frame": "RAS_mm",
        "pre_entry_world_ras_mm": (-1.23456, 2.0, 3.0),
        "entry_world_ras_mm": (4.0, 5.0, 6.0),
        "target_world_ras_mm": (7.0, 8.0, 9.0),
        "standoff_mm": 2.5,
    }
    current = SimpleNamespace(
        state="Current",
        stale_reason="",
        session_fingerprint="exact-session",
        full_task_outcome={"target_conditioning": conditioning},
    )
    text = panel_method(current, exact_current_session=True)
    assert "PreEntry (-1.235, 2.000, 3.000)" in text
    assert "Entry (4.000, 5.000, 6.000)" in text
    assert "Target (7.000, 8.000, 9.000)" in text
    assert "standoff 2.500 mm" in text
    assert "Exact current diagnostic snapshot at display time" in text
    assert "DISPLAY ONLY — no route authority" in text

    stale = SimpleNamespace(
        state="Stale",
        stale_reason="task identity changed",
        session_fingerprint="exact-session",
        full_task_outcome={"target_conditioning": conditioning},
    )
    stale_text = panel_method(stale, exact_current_session=True)
    assert "Stale saved diagnostic snapshot" in stale_text
    assert "Exact current diagnostic snapshot at display time" not in stale_text
    assert "DISPLAY ONLY — no route authority" in stale_text

    class FakeDisplay:
        def __init__(self):
            self.properties = {}

        def __getattr__(self, name):
            return lambda *values: self.properties.__setitem__(name, values)

    class FakeMarker:
        def __init__(self):
            self.attributes = {}
            self.points = []
            self.display = FakeDisplay()

        def SetAttribute(self, name, value):
            self.attributes[name] = value

        def GetAttribute(self, name):
            return self.attributes.get(name)

        def SetSaveWithScene(self, value):
            self.saved_with_scene = value

        def CreateDefaultDisplayNodes(self):
            pass

        def AddControlPointWorld(self, vector, label):
            self.points.append((vector.coordinates, label))

        def SetLocked(self, value):
            self.locked = value

        def GetDisplayNode(self):
            return self.display

    class FakeScene:
        def __init__(self):
            self.nodes = []

        def AddNewNodeByClass(self, _class_name, _name):
            node = FakeMarker()
            self.nodes.append(node)
            return node

        def RemoveNode(self, node):
            self.nodes.remove(node)

    scene = FakeScene()
    shell_methods = _methods(
        PYTHON / "dentobot_workflow/widget_robot_shell.py",
        "RobotShellWidgetMixin",
        {
            "_clearStep6TargetConditioningFiducials",
            "_showStep6TargetConditioningFiducials",
        },
        {
            "Mapping": Mapping,
            "isfinite": isfinite,
            "slicer": SimpleNamespace(
                mrmlScene=scene,
                util=SimpleNamespace(getNodesByClass=lambda _class: list(scene.nodes)),
            ),
            "vtk": SimpleNamespace(
                vtkVector3d=lambda *coordinates: SimpleNamespace(coordinates=coordinates)
            ),
        },
    )
    host_type = type("TargetFiducialProbe", (), shell_methods)
    host = host_type()
    assert host._showStep6TargetConditioningFiducials(current, "exact-session") is True
    assert len(scene.nodes) == 1
    marker = scene.nodes[0]
    assert [label for _point, label in marker.points] == [
        "PreEntry TCP",
        "Entry TCP",
        "Target TCP",
    ]
    assert marker.locked is True
    assert marker.saved_with_scene is False
    assert marker.attributes["DENTOBOT.IntendedUse"] == "DisplayOnlyDiagnosticSnapshot"
    assert marker.display.properties["SetSaveWithScene"] == (False,)
    assert not any(
        any(word in key.lower() for word in ("collision", "guard", "route"))
        for key in marker.attributes
    )

    host._clearStep6TargetConditioningFiducials()
    assert scene.nodes == []
    assert host._showStep6TargetConditioningFiducials(stale, "exact-session") is False
    assert scene.nodes == []


def test_motion_diagnostic_failed_preentry_candidate_callback_requires_exact_session():
    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    method = _methods(
        panel_path,
        "DENTORobotSimulationPanel",
        {"_invokeMotionDiagnosticCandidate"},
        {},
    )["_invokeMotionDiagnosticCandidate"]
    if isinstance(method, staticmethod):
        method = method.__func__
    calls = []

    def show_candidate(index):
        calls.append(index)
        return "shown"

    assert method(
        show_candidate,
        2,
        exact_current_session=True,
        preentry_ik_failure=True,
    ) == "shown"
    assert method(
        show_candidate,
        3,
        exact_current_session=False,
        preentry_ik_failure=True,
    ) is None
    assert method(
        show_candidate,
        4,
        exact_current_session=False,
        preentry_ik_failure=False,
    ) == "shown"
    assert calls == [2, 4]
    source = panel_path.read_text(encoding="utf-8")
    assert "not accepted, " in source
    assert "not verified collision-free" in source
    assert "route, preview, or motion authority" in source


def test_current_incisor_roi_load_preserves_only_exact_saved_workspace_evidence():
    shell_path = PYTHON / "dentobot_workflow/widget_robot_shell.py"
    loader = _methods(
        shell_path,
        "RobotShellWidgetMixin",
        {"_onStep6UseCurrentIncisorMidpoint"},
        {"Mapping": Mapping, "Sequence": Sequence, "TaskSpaceRoi": TaskSpaceRoi, "isfinite": isfinite},
    )["_onStep6UseCurrentIncisorMidpoint"]

    class Label:
        def setProperty(self, *_args):
            pass

        def style(self):
            return self

        def unpolish(self, *_args):
            pass

        def polish(self, *_args):
            pass

    class Spin:
        minimum = -1.0e9
        maximum = 1.0e9
        decimals = 6

        def __init__(self):
            self.value = 0.0
            self.enabled = False

    payload = {
        "centerWorldRasMm": (10.1, 20.2, 30.3),
        "dimensionsMm": (100.0, 100.0, 100.0),
        "openingRevision": 7,
        "gapLineNodeId": "gap-line-7",
    }

    def invoke(
        matches_saved,
        runtime_current,
        roi_payload=payload,
        result_success=True,
    ):
        invalidations = []
        comparisons = []

        class Facade:
            def defaultTaskSpaceRoi(self):
                return SimpleNamespace(
                    success=result_success,
                    message="ROI source unavailable" if not result_success else "",
                    payload=roi_payload,
                )

            def workspaceRoiMatchesSavedEvidence(self, roi, roi_source, parameter_node):
                comparisons.append((roi, roi_source, parameter_node))
                return matches_saved

            def workspaceRuntimeValidated(self, parameter_node):
                return runtime_current

        panel = SimpleNamespace(
            taskSpaceRoiCenterSpinBoxes=[Spin() for _ in range(3)],
            taskSpaceRoiDimensionsSpinBoxes=[Spin() for _ in range(3)],
            taskSpaceRoiStatusLabel=Label(),
            _taskSpaceRoiStatusContext="",
            _taskSpaceRoiOpeningRevision=None,
            _taskSpaceRoiGapLineNodeId="",
            _taskSpaceRoiInitialized=False,
            _loadingTaskSpaceRoi=False,
        )
        parameter_node = object()
        host = SimpleNamespace(
            _robotWorkflowFacade=Facade(),
            _robotSimulationPanel=panel,
            _parameterNode=parameter_node,
            _onStep6TaskSpaceRoiEdited=lambda: invalidations.append("invalidated"),
        )
        loaded = loader(host)
        assert panel._loadingTaskSpaceRoi is False
        if (
            result_success
            and isinstance(roi_payload, Mapping)
            and {"centerWorldRasMm", "dimensionsMm", "openingRevision", "gapLineNodeId"}
            <= roi_payload.keys()
        ):
            assert comparisons == [
                (
                    TaskSpaceRoi((10.1, 20.2, 30.3), (100.0, 100.0, 100.0)),
                    {"openingRevision": 7, "gapLineNodeId": "gap-line-7"},
                    parameter_node,
                )
            ]
        else:
            assert comparisons == []
        return panel, invalidations, loaded

    current, invalidations, loaded = invoke(True, True)
    assert loaded is True
    assert invalidations == []
    assert "exact saved workspace roi/source match" in current.taskSpaceRoiStatusLabel.text.lower()
    assert "is current" in current.taskSpaceRoiStatusLabel.text

    preserved, invalidations, loaded = invoke(True, False)
    assert loaded is True
    assert invalidations == []
    assert "needs runtime revalidation" in preserved.taskSpaceRoiStatusLabel.text

    _, invalidations, loaded = invoke(False, False)
    assert loaded is True
    assert invalidations == ["invalidated"]

    unavailable, invalidations, loaded = invoke(
        True, True, roi_payload=None, result_success=False
    )
    assert loaded is False
    assert invalidations == []
    assert "source issue" in unavailable.taskSpaceRoiStatusLabel.text.lower()

    malformed, invalidations, loaded = invoke(
        True,
        True,
        roi_payload={"centerWorldRasMm": (10.0, 20.0, 30.0)},
    )
    assert loaded is False
    assert invalidations == []
    assert "dimensionsmm" in malformed.taskSpaceRoiStatusLabel.text.lower()


def test_manual_task_space_roi_spinbox_edits_still_invalidate_workspace():
    invalidations = []
    panel_method = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        {"_onTaskSpaceRoiEdited"},
        {},
    )["_onTaskSpaceRoiEdited"]
    workflow_method = _methods(
        PYTHON / "dentobot_workflow/widget_robot_shell.py",
        "RobotShellWidgetMixin",
        {"_onStep6TaskSpaceRoiEdited"},
        {},
    )["_onStep6TaskSpaceRoiEdited"]
    shell = SimpleNamespace(
        _robotWorkflowFacade=SimpleNamespace(
            invalidateWorkspaceRuntimeValidation=lambda **kwargs: invalidations.append(kwargs)
        ),
        logic=SimpleNamespace(robotWorkspaceModelNode=lambda: None),
    )
    panel = SimpleNamespace(
        _loadingTaskSpaceRoi=True,
        _taskSpaceRoiStatusContext="current source",
        taskSpaceRoiStatusLabel=SimpleNamespace(
            text="",
            setProperty=lambda *_args: None,
            style=lambda: SimpleNamespace(unpolish=lambda *_args: None, polish=lambda *_args: None),
        ),
        _callbacks={"roi_edited": lambda: workflow_method(shell)},
    )
    panel_method(panel)
    assert invalidations == []
    panel._loadingTaskSpaceRoi = False
    panel_method(panel)
    assert invalidations == [{"invalidate_motion_plan": False}]


def test_phase_plan_buttons_require_runtime_workspace_and_reviewed_limits():
    path = PYTHON / "dentobot_workflow/widget_robot.py"
    update = _method_node(path, "RobotWidgetMixin", "_updateStep6PlanningUi")
    assignments = {
        target: node.value
        for node in ast.walk(update)
        if isinstance(node, ast.Assign)
        for target in (_attribute_name(item) for item in node.targets)
        if target
    }
    readiness = next(
        node.value
        for node in ast.walk(update)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "phase_planning_ready" for target in node.targets)
    )
    names = {node.id for node in ast.walk(readiness) if isinstance(node, ast.Name)}
    # Operator 2026-10-02: the 6.3 workspace is an optional visual.
    assert not {"workspace_runtime_validated", "assisted_reviewed"} & names
    assert assignments["panel.planApproachButton.enabled"].id == "phase_planning_ready"
    assert assignments["panel.comparePlannersButton.enabled"].id == "phase_planning_ready"
    diagnostic = next(
        node.value
        for node in ast.walk(update)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "stage_diagnostic_enabled" for target in node.targets)
    )
    diagnostic_names = {node.id for node in ast.walk(diagnostic) if isinstance(node, ast.Name)}
    assert not {"workspace_runtime_validated", "assisted_reviewed"}.intersection(diagnostic_names)

    ready = {
        "planning_anatomy_ready": True,
        "task_ready": True,
        "ros2_active": True,
        "home_runtime_validated": True,
        "workspace_runtime_validated": True,
        "assisted_reviewed": True,
        "away_from_home": False,
        "self": SimpleNamespace(_plannerComparisonState=None),
    }
    expression = compile(ast.Expression(readiness), str(path), "eval")
    assert eval(expression, ready) is True
    for optional in ("workspace_runtime_validated", "assisted_reviewed"):
        assert eval(expression, dict(ready, **{optional: False})) is True
    for missing in ("task_ready", "home_runtime_validated"):
        assert eval(expression, dict(ready, **{missing: False})) is False

    source = path.read_text(encoding="utf-8")
    assert "Revalidate or generate workspace evidence in 6.3." not in source
    assert "Review and apply assisted joint limits in 6.3." not in source


def test_unknown_base_main_action_routes_to_existing_reconciliation_owner():
    calls = []
    accept = _methods(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        {"onLockRobotBaseMount"},
        {"slicer": SimpleNamespace(util=SimpleNamespace(errorDisplay=lambda _message: None))},
    )["onLockRobotBaseMount"]
    host = SimpleNamespace(
        _parameterNode=object(),
        logic=object(),
        _robotWorkflowFacade=SimpleNamespace(
            acceptManualBaseReview=lambda: calls.append("accept")
        ),
        _robotSimulationPanel=SimpleNamespace(
            reconcileManualBaseStateButton=SimpleNamespace(enabled=True)
        ),
        _isStep6RobotWorkflowActive=lambda: True,
        _isStep6ManualBaseReviewActive=lambda: True,
        _onStep6ReconcileManualBaseAcceptance=lambda: calls.append("reconcile"),
    )
    accept(host)
    assert calls == ["reconcile"]

    source = (PYTHON / "dentobot_workflow/widget_robot.py").read_text(encoding="utf-8")
    assert '"Reconcile Base State" if reconcile_base else "Accept Base"' in source
    assert "(control_state[\"accept\"] or reconcile_base)" in source


def test_manual_jog_exact_draft_survives_two_decimal_spinbox_rounding():
    methods = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        {
            "setManualJogLimits",
            "setManualJogAcceptedState",
            "_updateManualJogResetLabel",
            "resetManualJogDraft",
            "stageTcpIkSolution",
            "_setManualJogDraftValues",
            "_onManualJogSliderChanged",
            "_onManualJogNumericChanged",
            "_updateManualJogDraftFromControls",
            "manualJogJointPositionsSi",
            "_formatManualJogDisplayValues",
            "_updateManualJogJointPresentation",
            "_setManualJogStatus",
        },
        {
            "JOINT_NAMES": JOINT_NAMES,
            "Mapping": Mapping,
            "degrees": degrees,
            "isfinite": isfinite,
            "joint_positions_si_from_display": joint_positions_si_from_display,
        },
    )
    panel = type("PanelProbe", (), methods)()
    panel.manualJogJointControls = {
        joint: (_Control(), _TwoDecimalSpinBox(), _Control())
        for joint in JOINT_NAMES
    }
    panel._manualJogJointPresentation = {}
    for name in (
        "manualJogAcceptedStateLabel",
        "taskHomeCurrentStateLabel",
        "manualJogDraftStateLabel",
        "manualJogStatusLabel",
        "manualJogDraftLimitLabel",
    ):
        setattr(panel, name, _Control())
    panel._manualJogLimits = {}
    panel._manualJogSliderRanges = ()
    panel._manualJogMechanicalLimits = None
    panel._manualJogLimitsValid = False
    panel._manualJogCommandLimitsValid = False
    panel._manualJogAvailable = True
    panel._manualJogGuardContextAvailable = True
    panel._manualJogBusy = False
    panel._manualJogDraftInitialized = False
    panel._manualJogDisplayValues = (0.0,) * 5
    panel._manualJogAcceptedJointPositionsSi = None
    panel._taskHomeSetupMode = "connected"
    panel._taskHomeConfigurationReady = False
    panel._taskHomeConfiguredJointPositionsSi = None
    panel._manualJogControlsInHomeGroup = False
    panel._manualJogEvidence = None
    panel.manualJogReconciliationRequired = False
    panel._invoke_calls = []
    panel._invoke = lambda action, state: panel._invoke_calls.append(
        (action, dict(state))
    )

    def set_availability(draft_available, guard_context_available):
        panel._manualJogAvailable = bool(draft_available)
        panel._manualJogGuardContextAvailable = bool(guard_context_available)
        panel._manualJogGuardAvailable = bool(
            draft_available and guard_context_available
        )

    panel.setManualJogAvailability = set_availability

    def assert_positions_close(actual, expected):
        assert set(actual) == set(JOINT_NAMES)
        for joint in JOINT_NAMES:
            assert math.isclose(
                actual[joint], expected[joint], rel_tol=0.0, abs_tol=1.0e-12
            ), (joint, actual[joint], expected[joint])

    def display_from_si(positions):
        return (
            degrees(positions[JOINT_NAMES[0]]),
            positions[JOINT_NAMES[1]] * 1000.0,
            degrees(positions[JOINT_NAMES[2]]),
            positions[JOINT_NAMES[3]] * 1000.0,
            degrees(positions[JOINT_NAMES[4]]),
        )

    mechanical = _joint_limits(
        ((-180, 180), (-10, 50), (-90, 90), (-10, 50), (-180, 180))
    )
    reviewed = _joint_limits(
        ((-180, 180), (-10, 50), (-90, 90), (-10, 50), (-180, 180))
    )
    panel.setManualJogLimits(mechanical, reviewed)

    accepted_before = {
        JOINT_NAMES[0]: radians(0.222222221),
        JOINT_NAMES[1]: 0.011111111,
        JOINT_NAMES[2]: radians(-0.333333333),
        JOINT_NAMES[3]: 0.022222222,
        JOINT_NAMES[4]: radians(0.444444444),
    }
    panel.setManualJogAcceptedState(accepted_before)
    panel._invoke_calls.clear()

    ik_candidate = {
        JOINT_NAMES[0]: 0.123456789,
        JOINT_NAMES[1]: 0.0123456789,
        JOINT_NAMES[2]: -0.456789012,
        JOINT_NAMES[3]: 0.0345678912,
        JOINT_NAMES[4]: 1.23456789,
    }
    candidate_display = display_from_si(ik_candidate)
    assert panel.stageTcpIkSolution(ik_candidate) is True
    for actual, expected in zip(
        panel._manualJogDisplayValues, candidate_display, strict=True
    ):
        assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-12)
    assert any(
        not math.isclose(value, round(value, 2), rel_tol=0.0, abs_tol=1.0e-8)
        for value in candidate_display
    )
    for joint, expected in zip(JOINT_NAMES, candidate_display, strict=True):
        assert panel.manualJogJointControls[joint][1].value == round(expected, 2)
    assert_positions_close(panel.manualJogJointPositionsSi(), ik_candidate)
    assert panel._manualJogAcceptedJointPositionsSi == accepted_before
    assert [action for action, _state in panel._invoke_calls] == [
        "manual_draft_changed"
    ]
    assert_positions_close(panel._invoke_calls[-1][1], ik_candidate)

    narrower_reviewed = _joint_limits(
        ((-10, 20), (0, 20), (-40, 0), (0, 40), (60, 90))
    )
    panel.setManualJogLimits(mechanical, narrower_reviewed)
    for actual, expected in zip(
        panel._manualJogDisplayValues, candidate_display, strict=True
    ):
        assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-12)
    assert_positions_close(panel.manualJogJointPositionsSi(), ik_candidate)

    other_values = tuple(panel._manualJogDisplayValues)
    numeric_joint = JOINT_NAMES[1]
    numeric_spin = panel.manualJogJointControls[numeric_joint][1]
    numeric_spin.setValue(17.89123)
    numeric_display = numeric_spin.value
    panel._onManualJogNumericChanged(numeric_joint, numeric_display)
    expected_after_numeric = list(other_values)
    expected_after_numeric[1] = numeric_display
    for index, (actual, expected) in enumerate(
        zip(panel._manualJogDisplayValues, expected_after_numeric, strict=True)
    ):
        assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-12), index

    other_values = tuple(panel._manualJogDisplayValues)
    slider_joint = JOINT_NAMES[4]
    slider_position = 1234
    slider_minimum, slider_maximum = panel._manualJogLimits[0][4]
    exact_slider_value = slider_minimum + (
        slider_maximum - slider_minimum
    ) * slider_position / 10000.0
    panel._onManualJogSliderChanged(slider_joint, slider_position)
    expected_after_slider = list(other_values)
    expected_after_slider[4] = exact_slider_value
    for index, (actual, expected) in enumerate(
        zip(panel._manualJogDisplayValues, expected_after_slider, strict=True)
    ):
        assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-12), index
    assert [action for action, _state in panel._invoke_calls] == [
        "manual_draft_changed"
    ] * len(panel._invoke_calls)

    assert panel._manualJogAcceptedJointPositionsSi == accepted_before

    reset_state = {
        JOINT_NAMES[0]: radians(11.123456789),
        JOINT_NAMES[1]: 0.0135792468,
        JOINT_NAMES[2]: radians(50.23456789),
        JOINT_NAMES[3]: 0.0246801357,
        JOINT_NAMES[4]: radians(-66.987654321),
    }
    panel.setManualJogAcceptedState(reset_state)
    panel.resetManualJogDraft()
    reset_display = display_from_si(reset_state)
    for actual, expected in zip(
        panel._manualJogDisplayValues, reset_display, strict=True
    ):
        assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-12)
    assert_positions_close(panel.manualJogJointPositionsSi(), reset_state)
    assert_positions_close(panel._invoke_calls[-1][1], reset_state)

    narrowed_mechanical = _joint_limits(
        ((-180, 180), (-10, 50), (-90, 50.12), (-10, 50), (-180, 180))
    )
    narrowed_reviewed = _joint_limits(
        ((-180, 180), (-10, 50), (-90, 50.12), (-10, 50), (-180, 180))
    )
    panel.setManualJogLimits(narrowed_mechanical, narrowed_reviewed)
    clamped_display = list(reset_display)
    clamped_display[2] = 50.12
    for actual, expected in zip(
        panel._manualJogDisplayValues, clamped_display, strict=True
    ):
        assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-12)
    assert panel.manualJogJointControls[JOINT_NAMES[2]][1].maximum == 50.12
    assert panel.manualJogJointControls[JOINT_NAMES[2]][1].value == 50.12
    assert panel._manualJogAcceptedJointPositionsSi == reset_state
    assert [action for action, _state in panel._invoke_calls] == [
        "manual_draft_changed"
    ] * len(panel._invoke_calls)

def test_step6_legacy_joint_spinboxes_keep_values_and_use_mechanical_ranges():
    path = PYTHON / "dentobot_workflow/widget_robot.py"
    mechanical_ranges = (
        (-180.0, 180.0),
        (0.0, 80.0),
        (-90.0, 90.0),
        (0.0, 75.0),
        (-180.0, 180.0),
    )
    reviewed_ranges = (
        (-10.0, 20.0),
        (0.0, 20.0),
        (-40.0, 0.0),
        (0.0, 40.0),
        (60.0, 90.0),
    )
    mechanical = _joint_limits(mechanical_ranges)
    reviewed = _joint_limits(reviewed_ranges)
    limits_reads = []
    urdf_reads = []

    def apply_reviewed_range(value, joint_limit):
        minimum = float(joint_limit.minimum)
        maximum = float(joint_limit.maximum)
        return minimum, maximum, min(maximum, max(minimum, float(value)))

    method = _methods(
        path,
        "RobotWidgetMixin",
        {"_applyTaskJointLimitsToJointSpinboxes"},
        {
            "default_task_joint_limits_from_urdf": lambda urdf_path: (
                urdf_reads.append(urdf_path) or mechanical
            ),
            "apply_task_limit_range_to_value": apply_reviewed_range,
        },
    )["_applyTaskJointLimitsToJointSpinboxes"]

    class SpinBox:
        def __init__(self, value, *, signals_blocked=False):
            self.value = float(value)
            self.minimum = -1000.0
            self.maximum = 1000.0
            self.read_only = False
            self._signals_blocked = bool(signals_blocked)
            self.block_calls = []
            self.range_calls = []
            self.value_calls = []
            self.events = []

        def blockSignals(self, blocked):
            previous = self._signals_blocked
            self.block_calls.append(bool(blocked))
            self._signals_blocked = bool(blocked)
            return previous

        def setRange(self, minimum, maximum):
            self.minimum, self.maximum = float(minimum), float(maximum)
            self.range_calls.append((self.minimum, self.maximum))
            if self.value < self.minimum:
                self.setValue(self.minimum)
            elif self.value > self.maximum:
                self.setValue(self.maximum)

        def setMinimum(self, minimum):
            self.minimum = float(minimum)

        def setMaximum(self, maximum):
            self.maximum = float(maximum)

        def setValue(self, value):
            self.value_calls.append(float(value))
            self.value = min(self.maximum, max(self.minimum, float(value)))
            if not self._signals_blocked:
                self.events.append(self.value)

        def setReadOnly(self, read_only):
            self.read_only = bool(read_only)

    values = (25.0, 35.0, 45.0, 50.0, 50.0)
    prior_signal_states = (True, False, True, False, True)
    spinboxes = [
        SpinBox(value, signals_blocked=blocked)
        for value, blocked in zip(values, prior_signal_states, strict=True)
    ]
    class ParameterNode:
        def __init__(self):
            self._track_writes = False
            self.writes = []
            self.robotJoint1Deg = 111.0
            self.robotJoint2Mm = 222.0
            self.robotJoint3Deg = 333.0
            self.robotJoint4Mm = 444.0
            self.robotJoint5Deg = 555.0
            self._track_writes = True

        def __setattr__(self, name, value):
            if getattr(self, "_track_writes", False) and not name.startswith("_"):
                self.writes.append((name, value))
            object.__setattr__(self, name, value)

    class NoNativeWrites:
        def __getattr__(self, name):
            raise AssertionError(f"Step 6 range setup touched native API {name}")

    node = ParameterNode()
    node_before = vars(node).copy()
    logic = SimpleNamespace(
        robotDescriptionPaths=lambda: ("fixture.urdf", None),
        getTaskJointLimits=lambda _node: limits_reads.append(True) or reviewed,
    )
    host = SimpleNamespace(
        _parameterNode=node,
        logic=logic,
        _robotWorkflowFacade=NoNativeWrites(),
        _bridge=NoNativeWrites(),
        ui=SimpleNamespace(
            **{
                f"robotJoint{index}SpinBox": spinbox
                for index, spinbox in enumerate(spinboxes, start=1)
            }
        ),
        _isStep6RobotWorkflowActive=lambda: True,
    )

    method(host)

    assert urdf_reads == ["fixture.urdf"]
    assert limits_reads == []
    assert tuple(spinbox.value for spinbox in spinboxes) == values
    assert tuple(spinbox.read_only for spinbox in spinboxes) == (True,) * 5
    assert tuple(spinbox._signals_blocked for spinbox in spinboxes) == prior_signal_states
    assert [spinbox.range_calls for spinbox in spinboxes] == [
        [limits] for limits in mechanical_ranges
    ]
    assert all(spinbox.value_calls == [] and spinbox.events == [] for spinbox in spinboxes)
    assert vars(node) == node_before
    assert node.writes == []

    host._isStep6RobotWorkflowActive = lambda: False
    method(host)
    assert len(limits_reads) == 1
    assert tuple(spinbox.read_only for spinbox in spinboxes) == (False,) * 5
    assert tuple(spinbox.value for spinbox in spinboxes) == tuple(
        min(high, max(low, value))
        for value, (low, high) in zip(values, reviewed_ranges, strict=True)
    )
    assert all(spinbox.value_calls for spinbox in spinboxes)


def test_reset_all_joints_is_disabled_for_the_step6_robot_stage():
    path = PYTHON / "dentobot_workflow/widget_robot.py"
    update = _method_node(path, "RobotWidgetMixin", "_updateStep6PlanningUi")
    reset_assignment = next(
        node
        for node in ast.walk(update)
        if isinstance(node, ast.Assign)
        and any(
            _attribute_name(target) == "self.ui.resetRobotJointsButton.enabled"
            for target in node.targets
        )
    )
    expression = compile(ast.Expression(reset_assignment.value), str(path), "eval")
    prerequisites = {
        "robot_present": True,
        "scene_prepared": True,
        "ros2_active": True,
    }

    assert eval(expression, {**prerequisites, "robot_stage_active": True}) is False
    assert eval(expression, {**prerequisites, "robot_stage_active": False}) is True


def test_bootstrap_initializes_action_busy_before_first_home_action_and_refresh_does_not_reset():
    bootstrap_path = PYTHON / "dentobot_workflow/widget_bootstrap.py"
    base_events = []

    class ScriptedBase:
        @staticmethod
        def __init__(widget, _parent=None):
            base_events.append("scripted-base")

    class ObservationMixin:
        @staticmethod
        def __init__(widget):
            base_events.append("observation-mixin")

    initialize = _methods(
        bootstrap_path,
        "BootstrapWidgetMixin",
        {"__init__"},
        {
            "ScriptedLoadableModuleWidget": ScriptedBase,
            "VTKObservationMixin": ObservationMixin,
        },
    )["__init__"]
    widget = SimpleNamespace()
    initialize(widget)

    assert widget._workflowActionBusy is False
    assert base_events == ["scripted-base", "observation-mixin"]

    action_events = []
    panel = SimpleNamespace(manualBaseReviewStatusLabel=SimpleNamespace(text=""))

    class Facade:
        def reconcileManualBaseAcceptance(self):
            action_events.append(("reconcile", widget._workflowActionBusy))
            return SimpleNamespace(success=True, message="reconciled", details={})

    widget._robotSimulationPanel = panel
    widget._robotWorkflowFacade = Facade()
    widget._updateStep6PlanningUi = lambda message, error: action_events.append(
        ("refresh", widget._workflowActionBusy, message, error)
    )
    reconcile = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {"_onStep6ReconcileManualBaseAcceptance"},
        {"Mapping": Mapping},
    )["_onStep6ReconcileManualBaseAcceptance"]
    reconcile(widget)

    assert action_events[0] == ("reconcile", True)
    assert action_events[1][0:2] == ("refresh", False)
    assert widget._workflowActionBusy is False

    refresh = _method_node(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        "_updateStep6PlanningUi",
    )
    assert not any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and target.attr == "_workflowActionBusy"
            for target in node.targets
        )
        for node in ast.walk(refresh)
    )


def test_deferred_step6_navigator_scroll_handles_live_none_and_destroyed_scroll_area():
    shell_path = PYTHON / "dentobot_workflow/widget_robot_shell.py"
    configure = _method_node(
        shell_path,
        "RobotShellWidgetMixin",
        "_configureRobotSimulationShellSubstep",
    )
    timer_call = next(
        node for node in ast.walk(configure)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "singleShot"
        and ast.unparse(node.func.value) == "qt.QTimer"
        and len(node.args) == 2
        and ast.unparse(node.args[1])
        == "self._ensureStep6SubstepNavigatorVisible"
    )
    assert ast.literal_eval(timer_call.args[0]) == 0
    ensure_visible = _methods(
        shell_path,
        "RobotShellWidgetMixin",
        {"_ensureStep6SubstepNavigatorVisible"},
        {},
    )["_ensureStep6SubstepNavigatorVisible"]
    calls = []

    class LiveScrollArea:
        def ensureWidgetVisible(self, navigator, x_margin, y_margin):
            calls.append((navigator, x_margin, y_margin))

    class DestroyedScrollArea:
        def ensureWidgetVisible(self, _navigator, _x_margin, _y_margin):
            calls.append("destroyed")
            raise ValueError("wrapped C++ object has been deleted")

    class NoNativeFacade:
        def __getattr__(self, name):
            raise AssertionError(f"deferred scroll made a native call: {name}")

    class Host:
        def __init__(self, scroll_area):
            self._workflowContentScrollArea = scroll_area
            self._step6SubstepNavigator = "step6-navigator"
            self._robotWorkflowFacade = NoNativeFacade()

    live_host = Host(LiveScrollArea())
    ensure_visible(live_host)
    assert calls == [("step6-navigator", 0, 20)]

    none_host = Host(None)
    ensure_visible(none_host)
    assert calls == [("step6-navigator", 0, 20)]

    destroyed_host = Host(DestroyedScrollArea())
    ensure_visible(destroyed_host)
    assert calls == [("step6-navigator", 0, 20), "destroyed"]


def test_joint_tcp_and_diagnostic_layouts_wrap_without_content_sized_widths():
    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    source = panel_path.read_text(encoding="utf-8")
    initialize = _method_node(
        panel_path, "DENTORobotSimulationPanel", "__init__"
    )
    initialize_source = ast.get_source_segment(source, initialize)
    assert 'joint_labels = ("J1", "J2", "J3", "J4", "J5")' in initialize_source
    assert 'units = ("deg", "mm", "deg", "mm", "deg")' in initialize_source
    assert 'joint_label = qt.QLabel(f"{label} ({unit})", row)' in initialize_source
    assert "joint_label.wordWrap = False" in initialize_source
    assert "joint_label.setMinimumWidth(56)" in initialize_source
    assert (
        "qt.QSizePolicy.Minimum, qt.QSizePolicy.Fixed" in initialize_source
    )
    assert "comparison.wordWrap = True" in initialize_source
    assert "header.addWidget(joint_label)" in initialize_source
    assert "header.addWidget(comparison, 1)" in initialize_source
    assert "header.addWidget(value)" in initialize_source
    assert "self.manualJogJointControls[joint] = (slider, value, joint_label)" in initialize_source
    assert "row_layout.addLayout(header)" in initialize_source
    assert "row_layout.addWidget(slider)" in initialize_source
    assert "row_layout.addLayout(endpoints)" in initialize_source
    assert "row_layout.addWidget(notice)" in initialize_source
    assert "joint_rows.setRowStretch" not in initialize_source
    assert "slider.setMinimumWidth(0)" in initialize_source
    assert "qt.QSizePolicy.Expanding, qt.QSizePolicy.Fixed" in initialize_source
    assert "value.setMinimumWidth(95)" in initialize_source
    assert 'self.taskHomeJointEditor = qt.QGroupBox(' in initialize_source
    assert 'joint_rows.addWidget(row)' in initialize_source
    assert 'home_joint_layout.addWidget(slider, index * 2, 2)' in initialize_source
    assert "qt.QSizePolicy.Preferred, qt.QSizePolicy.Fixed" in initialize_source
    assert "self.manualJogControlsGroup.setSizePolicy(" in initialize_source
    assert "qt.QSizePolicy.Preferred, qt.QSizePolicy.Maximum" in initialize_source
    assert "manualJogDetailsToggle = qt.QToolButton" in initialize_source
    assert "self.manualJogDetailsToggle.setCheckable(True)" in initialize_source
    assert "self.manualJogDetailsToggle.toggled.connect(" in initialize_source
    assert "self._manualJogDetailsWidget.hide()" in initialize_source
    assert "linear_step_label.wordWrap = True" in initialize_source
    assert "angular_step_label.wordWrap = True" in initialize_source
    assert "label_widget.setMinimumWidth(0)" in initialize_source
    assert "Home configuration mechanical bounds" not in initialize_source
    assert "reviewed guard limits" not in initialize_source

    diagnostics = _method_node(
        panel_path, "DENTORobotSimulationPanel", "showMotionDiagnostics"
    )
    diagnostics_source = ast.get_source_segment(source, diagnostics)
    assert "resizeColumnsToContents" not in diagnostics_source
    assert "setLineWrapMode(qt.QPlainTextEdit.WidgetWidth)" in diagnostics_source
    assert "dialog_buttons.addLayout(display_buttons)" in diagnostics_source
    assert "dialog_buttons.addLayout(route_buttons)" in diagnostics_source
    assert "stage_table.setMinimumWidth(0)" in diagnostics_source
    assert "table.setMinimumWidth(0)" in diagnostics_source
    for action in (
        "beginManualBaseReviewButton",
        "cancelManualBaseReviewButton",
        "reconcileManualBaseStateButton",
        "reviewTaskHomeButton",
        "cancelTaskHomeReviewButton",
        "acceptTaskHomeButton",
        "reconcileTaskHomeButton",
        "applyTaskHomeButton",
    ):
        assert f"self.{action}.toolTip = (" in initialize_source


def test_failed_pose_inspection_summary_reports_requested_vs_actual_without_safety_claim():
    method = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        {"_motionDiagnosticInspectionSummary"},
        {"Mapping": Mapping, "isfinite": isfinite},
    )["_motionDiagnosticInspectionSummary"]
    if isinstance(method, staticmethod):
        method = method.__func__
    text = method(
        {
            "diagnosticInspection": {
                "status": "current",
                "expected": {
                    "tcp_world_ras_mm": (10.0, 20.0, 30.0),
                    "drilling_axis_world_ras_unit": (0.0, 0.0, -1.0),
                },
                "fk": {
                    "status": "passed",
                    "message": "FK completed",
                    "pose_world_ras_mm": (
                        (0.0, -1.0, 0.0, 10.2),
                        (1.0, 0.0, 0.0, 19.9),
                        (0.0, 0.0, 1.0, 30.4),
                        (0.0, 0.0, 0.0, 1.0),
                    ),
                    "drilling_axis_world_ras_unit": (0.01, 0.0, -0.9999),
                },
                "position_residual_mm": 0.4583,
                "drilling_axis_residual_deg": 0.573,
                "static_state_validity": {
                    "status": "invalid",
                    "authoritative": True,
                    "message": "state validity check failed",
                },
                "native": {
                    "message": "No solution",
                    "termination_reason": "iteration limit",
                    "collision_check_status": "not_run",
                },
            }
        }
    )

    assert "Requested TCP RAS mm (10, 20, 30)" in text
    assert "FK TCP RAS mm (10.2, 19.9, 30.4)" in text
    assert "(0, 0, -1) / (0.01, 0, -0.9999)" in text
    assert "0.4583 mm / 0.573 deg" in text
    assert "Read-only static validity: invalid (authoritative: yes)" in text
    assert "state validity check failed" in text
    assert "No solution" in text
    assert "termination: iteration limit" in text
    assert "native collision-check status: not_run" in text
    assert "not accepted or route-authorized" in text
    assert "collision-free" not in text.lower()
    malformed_pose = method(
        {
            "diagnosticInspection": {
                "fk": {"pose_world_ras_mm": ((1.0, 2.0, 3.0),)},
            }
        }
    )
    assert "FK TCP RAS mm not reported" in malformed_pose


def test_diagnostic_dialog_open_does_not_inspect_until_deliberate_seed_selection():
    panel_path = PYTHON / "DENTORobotSimulationPanel.py"
    source = panel_path.read_text(encoding="utf-8")
    show = _method_node(
        panel_path, "DENTORobotSimulationPanel", "showMotionDiagnostics"
    )
    select = next(
        node
        for node in ast.walk(show)
        if isinstance(node, ast.FunctionDef) and node.name == "select_candidate"
    )
    invoke = next(
        node
        for node in ast.walk(select)
        if isinstance(node, ast.Call)
        and _attribute_name(node.func)
        == "self._invokeMotionDiagnosticCandidate"
    )
    no_inspection_guard = next(
        node
        for node in ast.walk(select)
        if isinstance(node, ast.If) and ast.unparse(node.test) == "not inspect"
    )
    assert no_inspection_guard.end_lineno < invoke.lineno
    initial_selection = next(
        node
        for node in ast.walk(show)
        if isinstance(node, ast.Call)
        and _attribute_name(node.func) == "select_candidate"
        and any(
            keyword.arg == "inspect" and ast.literal_eval(keyword.value) is False
            for keyword in node.keywords
        )
    )
    current_cell_connection = next(
        node
        for node in ast.walk(show)
        if isinstance(node, ast.Call)
        and _attribute_name(node.func) == "table.currentCellChanged.connect"
    )
    cell_click_connection = next(
        node
        for node in ast.walk(show)
        if isinstance(node, ast.Call)
        and _attribute_name(node.func) == "table.cellClicked.connect"
    )
    assert initial_selection.lineno < current_cell_connection.lineno
    assert initial_selection.lineno < cell_click_connection.lineno
    assert "No pose is displayed automatically" in source


def test_diagnostic_cleanup_preserves_same_generation_enrichment_and_clears_context_changes():
    shell_path = PYTHON / "dentobot_workflow/widget_robot_shell.py"
    generations = {
        "initial": SimpleNamespace(
            schema_version="2.3",
            generated_at_utc="2026-10-01T00:00:00Z",
            task_fingerprint="task-1",
            base_fingerprint="base-1",
            trajectory_fingerprint="trajectory-1",
            robot_profile_fingerprint="profile-1",
            collision_audit_fingerprint="audit-1",
            planning_parameters_fingerprint="planning-1",
            session_fingerprint="session-before-inspection",
            state="Current",
            stale_reason="",
        ),
        "enriched": SimpleNamespace(
            schema_version="2.3",
            generated_at_utc="2026-10-01T00:00:00Z",
            task_fingerprint="task-1",
            base_fingerprint="base-1",
            trajectory_fingerprint="trajectory-1",
            robot_profile_fingerprint="profile-1",
            collision_audit_fingerprint="audit-1",
            planning_parameters_fingerprint="planning-1",
            session_fingerprint="session-after-inspection",
            state="Current",
            stale_reason="",
        ),
        "new-generation": SimpleNamespace(
            schema_version="2.3",
            generated_at_utc="2026-10-01T00:05:00Z",
            task_fingerprint="task-1",
            base_fingerprint="base-1",
            trajectory_fingerprint="trajectory-1",
            robot_profile_fingerprint="profile-1",
            collision_audit_fingerprint="audit-1",
            planning_parameters_fingerprint="planning-1",
            session_fingerprint="session-new-generation",
            state="Current",
            stale_reason="",
        ),
        "stale": SimpleNamespace(
            schema_version="2.3",
            generated_at_utc="2026-10-01T00:00:00Z",
            task_fingerprint="task-1",
            base_fingerprint="base-1",
            trajectory_fingerprint="trajectory-1",
            robot_profile_fingerprint="profile-1",
            collision_audit_fingerprint="audit-1",
            planning_parameters_fingerprint="planning-1",
            session_fingerprint="stale-session",
            state="Stale",
            stale_reason="base changed",
        ),
    }
    clear_calls = []
    errors = []
    diagnostic_namespace = {
        "parse_motion_diagnostic_session": lambda payload: generations[payload],
        "clear_motion_diagnostic_display": lambda: (_ for _ in ()).throw(
            AssertionError("bridge fallback used despite façade owner")
        ),
        "slicer": SimpleNamespace(
            util=SimpleNamespace(
                getNodesByClass=lambda _name: [],
                errorDisplay=lambda message: errors.append(str(message)),
            ),
            mrmlScene=SimpleNamespace(),
        ),
    }
    shell_methods = _methods(
        shell_path,
        "RobotShellWidgetMixin",
        {"_clearStep6TargetConditioningFiducials"},
        diagnostic_namespace,
    )
    shell_methods.update(
        _methods(
            ROBOT_MANUAL,
            "RobotManualWidgetMixin",
            {
                "_step6MotionDiagnosticGenerationIdentity",
                "_clearStep6MotionDiagnosticDisplay",
                "_clearStep6MotionDiagnosticDisplayIfContextChanged",
            },
            diagnostic_namespace,
        )
    )
    host_type = type("DiagnosticCleanupProbe", (), shell_methods)
    host = host_type()
    node = SimpleNamespace(step6MotionDiagnosticJson="initial")

    class Facade:
        def clearDiagnosticDisplay(self):
            clear_calls.append("facade")
            return SimpleNamespace(success=True, message="cleared")

    class Dialog:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    dialog = Dialog()
    host._parameterNode = node
    host._robotWorkflowFacade = Facade()
    host._robotSimulationPanel = SimpleNamespace(
        _diagnosticDialog=dialog,
        approachStatusLabel=SimpleNamespace(
            text="", setProperty=lambda *_args: None
        ),
    )
    host.logic = SimpleNamespace(motionDiagnosticFreshnessIssues=lambda _node: ())
    host._clearStep6TargetConditioningFiducials = (
        lambda: clear_calls.append("no-fiducial-nodes")
    )
    host._step6DiagnosticDisplayContext = (
        node,
        host._step6MotionDiagnosticGenerationIdentity(generations["initial"]),
    )
    host._tcpDragEnabled = True
    host.manualJogDraft = {"j1": 0.125}
    host.acceptedRobotState = {"j1": 0.25}
    host.historicalManualPaths = ["historical"]
    host.guardedPreviewPath = ["live-preview"]

    node.step6MotionDiagnosticJson = "enriched"
    assert host._clearStep6MotionDiagnosticDisplayIfContextChanged() is False
    assert clear_calls == []
    assert dialog.close_calls == 0

    node.step6MotionDiagnosticJson = "new-generation"
    assert host._clearStep6MotionDiagnosticDisplayIfContextChanged() is True
    assert clear_calls == ["no-fiducial-nodes", "facade"]
    assert dialog.close_calls == 1
    assert host._step6DiagnosticDisplayContext is None
    assert host._tcpDragEnabled is True
    assert host.manualJogDraft == {"j1": 0.125}
    assert host.acceptedRobotState == {"j1": 0.25}
    assert host.historicalManualPaths == ["historical"]
    assert host.guardedPreviewPath == ["live-preview"]
    assert errors == []

    host._step6DiagnosticDisplayContext = (
        node,
        host._step6MotionDiagnosticGenerationIdentity(generations["initial"]),
    )
    node.step6MotionDiagnosticJson = ""
    assert host._clearStep6MotionDiagnosticDisplayIfContextChanged() is True
    assert dialog.close_calls == 2

    host._step6DiagnosticDisplayContext = (
        node,
        host._step6MotionDiagnosticGenerationIdentity(generations["initial"]),
    )
    node.step6MotionDiagnosticJson = "enriched"
    host.logic.motionDiagnosticFreshnessIssues = lambda _node: (
        "Motion diagnostic belongs to a different base pose.",
    )
    assert host._clearStep6MotionDiagnosticDisplayIfContextChanged() is True
    assert dialog.close_calls == 3

    host._step6DiagnosticDisplayContext = (
        node,
        host._step6MotionDiagnosticGenerationIdentity(generations["initial"]),
    )
    host._parameterNode = SimpleNamespace(step6MotionDiagnosticJson="enriched")
    host.logic.motionDiagnosticFreshnessIssues = lambda _node: ()
    assert host._clearStep6MotionDiagnosticDisplayIfContextChanged() is True
    assert dialog.close_calls == 4

    host._parameterNode = node
    node.step6MotionDiagnosticJson = "stale"
    host._step6DiagnosticDisplayContext = (
        node,
        host._step6MotionDiagnosticGenerationIdentity(generations["initial"]),
    )
    assert host._clearStep6MotionDiagnosticDisplayIfContextChanged() is True
    assert dialog.close_calls == 5
    assert clear_calls.count("no-fiducial-nodes") == 5
    assert clear_calls.count("facade") == 5


def test_diagnostic_cleanup_uses_bridge_fallback_and_reports_failure():
    shell_path = PYTHON / "dentobot_workflow/widget_robot_shell.py"
    errors = []
    bridge_calls = []
    cleanup = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {"_clearStep6MotionDiagnosticDisplay"},
        {
            "clear_motion_diagnostic_display": lambda: (
                bridge_calls.append(True) or (False, "marker cleanup refused")
            ),
            "slicer": SimpleNamespace(
                util=SimpleNamespace(errorDisplay=lambda text: errors.append(str(text)))
            ),
        },
    )
    host = type("DiagnosticBridgeCleanupProbe", (), cleanup)()
    panel = SimpleNamespace(
        approachStatusLabel=SimpleNamespace(
            text="", setProperty=lambda *_args: None
        )
    )
    host._robotSimulationPanel = panel
    host._robotWorkflowFacade = None
    host._step6DiagnosticDisplayContext = (object(), ("generation",))
    host._tcpDragEnabled = True
    host._manualJogDraft = {"j1": 0.125}
    host._clearStep6TargetConditioningFiducials = lambda: None

    assert host._clearStep6MotionDiagnosticDisplay() is False
    assert bridge_calls == [True]
    assert panel.approachStatusLabel.text == (
        "Motion diagnostic display cleanup failed: marker cleanup refused"
    )
    assert errors == [panel.approachStatusLabel.text]
    assert host._step6DiagnosticDisplayContext is None
    assert host._tcpDragEnabled is True
    assert host._manualJogDraft == {"j1": 0.125}


def test_diagnostic_dialog_finish_cleans_up_independent_of_target_fiducial_visibility():
    shell_path = PYTHON / "dentobot_workflow/widget_robot_shell.py"
    show = _method_node(
        shell_path, "RobotShellWidgetMixin", "_onStep6ShowMotionDiagnostics"
    )
    source = ast.get_source_segment(shell_path.read_text(encoding="utf-8"), show)
    finished_connect = source.index('"finished(int)"')
    exact_current_branch = source.index("if exact_current_session:")
    assert finished_connect < exact_current_branch
    assert "lambda _result: self._clearStep6MotionDiagnosticDisplay()" in source

    substep = _method_node(
        shell_path,
        "RobotShellWidgetMixin",
        "_configureRobotSimulationShellSubstep",
    )
    assert any(
        isinstance(node, ast.Call)
        and _attribute_name(node.func)
        == "self._clearStep6MotionDiagnosticDisplay"
        for node in ast.walk(substep)
    )


def test_direct_reopen_resolves_only_fresh_current_diagnostic_fingerprint():
    shell_path = PYTHON / "dentobot_workflow/widget_robot_shell.py"
    resolver = _methods(
        ROBOT_MANUAL,
        "RobotManualWidgetMixin",
        {"_step6ExactMotionDiagnosticDisplayFingerprint"},
        {},
    )["_step6ExactMotionDiagnosticDisplayFingerprint"]
    host_type = type("DiagnosticFingerprintProbe", (), {resolver.__name__: resolver})
    host = host_type()
    node = object()
    checker_calls = []
    host._parameterNode = node
    host.logic = SimpleNamespace(
        motionDiagnosticFreshnessIssues=lambda parameter_node: (
            checker_calls.append(parameter_node) or ()
        )
    )
    current = SimpleNamespace(
        session_fingerprint="current-fingerprint",
        state="Current",
        stale_reason="",
    )

    assert host._step6ExactMotionDiagnosticDisplayFingerprint(current) == (
        "current-fingerprint"
    )
    assert checker_calls == [node]
    assert host._step6ExactMotionDiagnosticDisplayFingerprint(
        current, "current-fingerprint"
    ) == "current-fingerprint"
    assert checker_calls == [node]
    assert host._step6ExactMotionDiagnosticDisplayFingerprint(
        current, "different-fingerprint"
    ) == ""
    assert checker_calls == [node]
    host.logic.motionDiagnosticFreshnessIssues = lambda _node: []
    assert host._step6ExactMotionDiagnosticDisplayFingerprint(current) == (
        "current-fingerprint"
    )
    host.logic.motionDiagnosticFreshnessIssues = lambda _node: None
    assert host._step6ExactMotionDiagnosticDisplayFingerprint(current) == ""

    stale = SimpleNamespace(
        session_fingerprint="stale-fingerprint",
        state="Stale",
        stale_reason="base changed",
    )
    assert host._step6ExactMotionDiagnosticDisplayFingerprint(stale) == ""
    host.logic.motionDiagnosticFreshnessIssues = lambda _node: ("base changed",)
    assert host._step6ExactMotionDiagnosticDisplayFingerprint(current) == ""
    host.logic = SimpleNamespace()
    assert host._step6ExactMotionDiagnosticDisplayFingerprint(current) == ""

    show = _method_node(
        shell_path, "RobotShellWidgetMixin", "_onStep6ShowMotionDiagnostics"
    )
    assert any(
        isinstance(node, ast.Call)
        and _attribute_name(node.func)
        == "self._step6ExactMotionDiagnosticDisplayFingerprint"
        and len(node.args) == 2
        and ast.unparse(node.args[1]) == "expected_fingerprint"
        for node in ast.walk(show)
    )


def _placement_modified_host(acceptance_in_progress, locked=True):
    method = _methods(
        PYTHON / "dentobot_workflow/widget_robot_placement.py",
        "RobotPlacementWidgetMixin",
        {"_onRobotPlacementNodeModified"},
        {"_": lambda text: text},
    )["_onRobotPlacementNodeModified"]
    invalidations = []
    attributes = {}
    base = SimpleNamespace(SetAttribute=lambda name, value: attributes.__setitem__(name, value))
    workspace_attrs = {}
    logic = SimpleNamespace(
        robotBasePoseFingerprint=lambda _node: "moved",
        ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE="authority",
        ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY="unreviewed",
        invalidateStep6TaskConfirmation=lambda node, reason, makeBaseStale=False: invalidations.append(makeBaseStale),
        robotWorkspaceModelNode=lambda: SimpleNamespace(SetAttribute=lambda k, v: workspace_attrs.__setitem__(k, v)),
    )
    cleared = []
    host = SimpleNamespace(
        _updatingRobotPlacementUI=False,
        logic=logic,
        _parameterNode=SimpleNamespace(robotBaseTransform=base, robotBaseMountLocked=locked,
                                       step6BasePlacementRevision=0),
        _lastRobotBasePoseFingerprint="before",
        _robotWorkflowFacade=SimpleNamespace(
            manualBaseAcceptanceInProgress=acceptance_in_progress,
            clearTransientState=lambda: cleared.append(True),
        ),
        _step6MotionPlan="plan",
        ui=SimpleNamespace(robotWorkspaceStatusLabel=SimpleNamespace(text="", styleSheet="")),
        _updateRobotPlacementStatus=lambda: None,
    )
    method(host, base)
    return host, attributes, invalidations, cleared, workspace_attrs


def test_accept_base_owned_move_does_not_unreview_or_unlock_base():
    host, attributes, invalidations, cleared, workspace = _placement_modified_host(True)
    assert attributes == {} and invalidations == [] and cleared == []
    assert host._lastRobotBasePoseFingerprint == "moved"
    assert workspace == {"DENTOBOT.WorkspaceState": "Stale"}  # Base really moved


def test_operator_move_of_locked_base_still_unreviews_and_makes_stale():
    host, attributes, invalidations, cleared, _workspace = _placement_modified_host(False)
    assert attributes["authority"] == "unreviewed"
    assert invalidations == [True] and cleared == [True]


def test_spindle_guide_contact_option_syncs_both_checkboxes_and_invalidates_task():
    method = _methods(
        PYTHON / "dentobot_workflow/widget_robot_placement.py",
        "RobotPlacementWidgetMixin",
        {"_onSetSpindleGuideContact"},
        {"_": lambda text: text},
    )["_onSetSpindleGuideContact"]

    class Box:
        def __init__(self):
            self.checked = False
        def blockSignals(self, value):
            return False

    invalidated = []
    step4, step63 = Box(), Box()
    host = SimpleNamespace(
        _parameterNode=SimpleNamespace(step6AllowSpindleGuideContact=False),
        logic=SimpleNamespace(invalidateStep6TaskConfirmation=lambda node, reason: invalidated.append(reason)),
        _step4SpindleGuideContactCheckBox=step4,
        _robotSimulationPanel=SimpleNamespace(allowSpindleGuideContactCheckBox=step63),
    )
    method(host, True)
    assert host._parameterNode.step6AllowSpindleGuideContact is True
    assert step4.checked and step63.checked and len(invalidated) == 1
    method(host, True)
    assert len(invalidated) == 1  # no change, no invalidation


def test_mouth_barrier_edge_mode_syncs_combo_and_invalidates_task():
    method = _methods(
        PYTHON / "dentobot_workflow/widget_robot_placement.py",
        "RobotPlacementWidgetMixin",
        {"_onSetMouthBarrierEdgeMode"},
        {"_": lambda text: text},
    )["_onSetMouthBarrierEdgeMode"]

    class Combo:
        modes = ("gum_line", "biting_edge", "off")
        def __init__(self):
            self.currentIndex = 0
        def findData(self, mode):
            return self.modes.index(mode)
        def blockSignals(self, value):
            return False

    invalidated = []
    combo = Combo()
    host = SimpleNamespace(
        _parameterNode=SimpleNamespace(step6MouthBarrierEdgeMode="gum_line"),
        logic=SimpleNamespace(invalidateStep6TaskConfirmation=lambda node, reason: invalidated.append(reason)),
        _robotSimulationPanel=SimpleNamespace(mouthBarrierEdgeModeComboBox=combo),
    )
    method(host, "biting_edge")
    assert host._parameterNode.step6MouthBarrierEdgeMode == "biting_edge"
    assert combo.currentIndex == 1 and len(invalidated) == 1
    method(host, "biting_edge")
    assert len(invalidated) == 1  # no change, no invalidation
    method(host, "nonsense")  # unknown values fall back to the default
    assert host._parameterNode.step6MouthBarrierEdgeMode == "gum_line" and combo.currentIndex == 0


def test_mouth_barrier_combo_is_in_63_advanced_options_and_routed():
    panel = (PYTHON / "DENTORobotSimulationPanel.py").read_text()
    shell = (PYTHON / "dentobot_workflow/widget_robot_shell.py").read_text()
    assert 'objectName = "DENTOBOTMouthBarrierEdgeMode63"' in panel
    for mode in ('"gum_line"', '"biting_edge"', '"off"'):
        assert mode in panel
    assert '"set_mouth_barrier_edge_mode"' in panel
    assert '"set_mouth_barrier_edge_mode": self._onSetMouthBarrierEdgeMode' in shell
    state = (PYTHON / "dentobot_workflow/parameter_state.py").read_text()
    assert 'step6MouthBarrierEdgeMode: str = "gum_line"' in state


def test_display_toggles_for_mouth_barrier_and_reach_envelope_are_wired():
    panel = (PYTHON / "DENTORobotSimulationPanel.py").read_text()
    shell = (PYTHON / "dentobot_workflow/widget_robot_shell.py").read_text()
    placement = (PYTHON / "dentobot_workflow/widget_robot_placement.py").read_text()
    bootstrap = (PYTHON / "dentobot_workflow/widget_bootstrap.py").read_text()
    assert 'objectName = "DENTOBOTShowMouthBarrier63"' in panel
    assert '"set_show_mouth_barrier"' in panel
    assert '"set_show_mouth_barrier": self._onSetShowMouthBarrier' in shell
    assert 'objectName = "DENTOBOTShowReachEnvelope63"' in placement
    assert "self._setupReachEnvelopeOption()" in bootstrap
    methods = _methods(
        PYTHON / "dentobot_workflow/widget_robot_placement.py",
        "RobotPlacementWidgetMixin",
        {"_onSetShowMouthBarrier", "_onSetShowReachEnvelope", "_syncCheckBox"},
        {"_": lambda text: text},
    )

    class Box:
        def __init__(self):
            self.checked = True
        def blockSignals(self, value):
            return False

    shown = []
    barrier_box, envelope_box = Box(), Box()
    host = SimpleNamespace(
        _parameterNode=SimpleNamespace(step6ShowMouthBarrier=True, step6ShowMouthBarrierSurface=False,
                                       step6ShowReachEnvelope=True),
        logic=SimpleNamespace(
            setStep6MouthBarrierVisible=lambda value, surface=False: shown.append(("barrier", value, surface)),
            setStep6ReachEnvelopeVisible=lambda value: shown.append(("envelope", value)),
        ),
        _robotSimulationPanel=SimpleNamespace(showMouthBarrierCheckBox=barrier_box),
        _showReachEnvelopeCheckBox=envelope_box,
        _syncCheckBox=methods["_syncCheckBox"],
    )
    methods["_onSetShowMouthBarrier"](host, False)
    methods["_onSetShowReachEnvelope"](host, False)
    assert shown == [("barrier", False, False), ("envelope", False)]
    assert host._parameterNode.step6ShowMouthBarrier is False and barrier_box.checked is False
    assert host._parameterNode.step6ShowReachEnvelope is False and envelope_box.checked is False


def test_diagnose_base_button_is_owned_by_planning_substep_and_wired():
    panel = (PYTHON / "DENTORobotSimulationPanel.py").read_text()
    shell = (PYTHON / "dentobot_workflow/widget_robot_shell.py").read_text()
    robot = (PYTHON / "dentobot_workflow/widget_robot.py").read_text()
    assert '"diagnose_base": 3,' in panel
    assert 'self.diagnoseBaseButton.objectName = "DENTOBOTDiagnoseBaseButton"' in panel
    assert 'self._invoke("diagnose_base")' in panel
    assert "def showBaseDiagnosisDialog(self, summary)" in panel
    assert 'getattr(self, "_baseDiagnosisDialog", None),' in panel  # hidden outside 6.3
    assert '"diagnose_base": self._onStep6DiagnoseBase,' in shell
    assert "self._robotWorkflowFacade.diagnoseBase(" in shell
    assert "diagnose_button.enabled = bool(panel.checkPreEntryIKButton.enabled)" in robot


def test_unreachable_remainder_is_a_labelled_tube_cleared_with_phase_paths():
    bridge = (PYTHON / "DENTOROS2Bridge.py").read_text()
    assert "vtk.vtkTubeFilter()" in bridge and '"[Step 6] Drilling Not Completed"' in bridge
    assert 'f"Not completed: {remaining_mm:.2f} mm (collision)"' in bridge
    assert 'for class_name in ("vtkMRMLModelNode", "vtkMRMLMarkupsFiducialNode"):' in bridge


def test_drill_preview_gate_follows_completed_approach_not_task_home():
    robot = (PYTHON / "dentobot_workflow/widget_robot.py").read_text()
    gate = robot[robot.index("panel.previewDrillingButton.enabled = bool("):]
    gate = gate[:gate.index("\n            )")]
    assert "and approach_complete" in gate
    assert "and not away_from_home" not in gate  # r16: Approach always leaves Home
    approach_gate = robot[robot.index("panel.previewApproachButton.enabled = bool("):]
    approach_gate = approach_gate[:approach_gate.index("\n            )")]
    assert "away_from_home" in approach_gate or "returnHomeRequired" in robot


def test_task_space_box_is_optional_off_by_default_with_side_and_opacity_controls():
    """Operator 2026-10-03: incisor-centred task-space box off by default, adjustable
    side, distinct colour from the mouth barrier, low default opacities."""
    panel = (PYTHON / "DENTORobotSimulationPanel.py").read_text()
    shell = (PYTHON / "dentobot_workflow/widget_robot_shell.py").read_text()
    logic = (PYTHON / "dentobot_workflow/logic_robot_scene_sync.py").read_text()
    overlays = (PYTHON / "dentobot_workflow/logic_robot_overlays.py").read_text()
    state = (PYTHON / "dentobot_workflow/parameter_state.py").read_text()
    assert "self.showTaskSpaceBoxCheckBox.checked = False" in panel
    assert "self.taskSpaceBoxSideSpinBox.value = 200.0" in panel
    assert "self.taskSpaceBoxOpacitySlider.value = 10" in panel
    assert "self.mouthBarrierOpacitySlider.value = 12" in panel
    assert "step6ShowTaskSpaceBox: bool = False" in state
    assert "step6MouthBarrierOpacity: float = 0.12" in state
    assert '"set_task_space_box": self._onSetTaskSpaceBox' in shell
    assert "self.logic.setStep6ViewFrameBoxVisible(False)" in shell
    assert "display.SetColor(0.20, 0.55, 1.0)" in overlays  # box: cool blue
    assert "display.SetColor(0.95, 0.45, 0.60)" in logic  # barrier: rose
    assert 'SetAttribute("DENTOBOT.DisplayOpacity", "0.35")' not in logic
    methods = _methods(
        PYTHON / "dentobot_workflow/widget_robot_placement.py",
        "RobotPlacementWidgetMixin",
        {"_onSetTaskSpaceBox", "_onSetMouthBarrierOpacity", "_step6TaskSpaceBoxCenter"},
        {"_": lambda text: text},
    )
    boxes, opacities = [], []
    host = SimpleNamespace(
        _parameterNode=SimpleNamespace(step6ShowTaskSpaceBox=False, step6TaskSpaceBoxSideMm=200.0,
                                       step6TaskSpaceBoxOpacity=0.1, step6MouthBarrierOpacity=0.12),
        logic=SimpleNamespace(
            TASK_SPACE_BOX_MAX_OPACITY=0.30,
            updateStep6TaskSpaceBox=lambda *args: boxes.append(args),
            setStep6MouthBarrierOpacity=opacities.append,
        ),
        _robotSimulationPanel=SimpleNamespace(
            _taskSpaceRoiInitialized=False, taskSpaceBoxStatusLabel=SimpleNamespace(text="x")),
        _robotWorkflowFacade=SimpleNamespace(defaultTaskSpaceRoi=lambda: SimpleNamespace(
            success=True, payload={"centerWorldRasMm": (1.0, 2.0, 3.0)})),
    )
    host._step6TaskSpaceBoxCenter = lambda: methods["_step6TaskSpaceBoxCenter"](host)
    methods["_onSetTaskSpaceBox"](host, True, 120.0, 0.25)
    assert boxes == [((1.0, 2.0, 3.0), 120.0, 0.25, True)]
    assert host._parameterNode.step6ShowTaskSpaceBox is True
    assert host._parameterNode.step6TaskSpaceBoxSideMm == 120.0
    assert host._robotSimulationPanel.taskSpaceBoxStatusLabel.text == ""
    methods["_onSetTaskSpaceBox"](host, False, 120.0, 0.25)
    assert boxes[-1] == (None, 120.0, 0.25, False)
    methods["_onSetMouthBarrierOpacity"](host, 1.7)
    assert opacities == [1.0] and host._parameterNode.step6MouthBarrierOpacity == 1.0


def test_mouth_barrier_display_is_a_thick_black_outline_plus_optional_full_surface():
    """Operator 2026-10-04: the solid lip slab/cheek walls hid the relevant anatomy.
    The viewport shows a strong black entry outline; the old full barrier is an
    optional extra (off by default) drawn together with it. MoveIt always gets every part."""
    logic = (PYTHON / "dentobot_workflow/logic_robot_scene_sync.py").read_text()
    poly = logic[logic.index("    def step6MouthBarrierPolydataWorld("):logic.index("    def _step6MouthBarrierModels(")]
    assert "self._showStep6MouthBarrier(parts, barrier.opening.vertices_mm," in poly
    assert "return parts" in poly  # MoveIt/preflight still get every barrier part
    show = logic[logic.index("    def _showStep6MouthBarrier("):logic.index("    def checkStep6MouthPortalGate(")]
    assert "vtk.vtkTubeFilter()" in show and "SetLines(" in show
    assert "display.SetColor(0.0, 0.0, 0.0)" in show  # outline: black
    assert "MOUTH_ENTRY_OUTLINE_RADIUS_MM = 1.5" in logic
    assert "vtkAppendPolyData" in show and "display.SetColor(0.95, 0.45, 0.60)" in show  # optional surface
    state = (PYTHON / "dentobot_workflow/parameter_state.py").read_text()
    panel = (PYTHON / "DENTORobotSimulationPanel.py").read_text()
    assert "step6ShowMouthBarrierSurface: bool = False" in state
    assert "self.showMouthBarrierSurfaceCheckBox.checked = False" in panel
    methods = _methods(
        PYTHON / "dentobot_workflow/widget_robot_placement.py",
        "RobotPlacementWidgetMixin",
        {"_onSetShowMouthBarrierSurface", "_syncCheckBox"},
        {"_": lambda text: text},
    )
    shown = []
    host = SimpleNamespace(
        _parameterNode=SimpleNamespace(step6ShowMouthBarrier=True, step6ShowMouthBarrierSurface=False),
        logic=SimpleNamespace(setStep6MouthBarrierVisible=lambda *args: shown.append(args)),
        _robotSimulationPanel=None, _syncCheckBox=methods["_syncCheckBox"],
    )
    methods["_onSetShowMouthBarrierSurface"](host, True)
    assert shown == [(True, True)] and host._parameterNode.step6ShowMouthBarrierSurface is True
    composition = (PYTHON / "dentobot_workflow/widget_view_composition.py").read_text()
    assert '("nodes:step6MouthBarrierSurface", "step6ShowMouthBarrierSurface", False)' in composition


def test_task_space_box_opacity_is_capped_at_30_percent_and_hidden_box_is_not_reshown():
    """Operator 2026-10-04: the box has no use above 30 % opacity, and it popped up
    at random points in Step 6 because every status refresh re-showed it."""
    panel = (PYTHON / "DENTORobotSimulationPanel.py").read_text()
    logic = (PYTHON / "dentobot_workflow/logic_robot_overlays.py").read_text()
    placement = (PYTHON / "dentobot_workflow/widget_robot_placement.py").read_text()
    assert "self.taskSpaceBoxOpacitySlider.minimum, self.taskSpaceBoxOpacitySlider.maximum = 0, 30" in panel
    assert "TASK_SPACE_BOX_MAX_OPACITY = 0.30" in logic
    box = logic[logic.index("    def updateStep6TaskSpaceBox("):logic.index("    def step6TaskSpaceBoxExists(")]
    assert "min(self.TASK_SPACE_BOX_MAX_OPACITY," in box
    status = placement[placement.index("    def _updateRobotPlacementStatus("):]
    assert "not self.logic.step6TaskSpaceBoxExists()" in status
    assert "step6TaskSpaceBoxShown()" not in status
    methods = _methods(
        PYTHON / "dentobot_workflow/widget_robot_placement.py",
        "RobotPlacementWidgetMixin",
        {"_onSetTaskSpaceBox"},
        {"_": lambda text: text},
    )
    boxes = []
    host = SimpleNamespace(
        _parameterNode=SimpleNamespace(step6ShowTaskSpaceBox=False, step6TaskSpaceBoxSideMm=200.0,
                                       step6TaskSpaceBoxOpacity=0.1),
        logic=SimpleNamespace(TASK_SPACE_BOX_MAX_OPACITY=0.30,
                              updateStep6TaskSpaceBox=lambda *args: boxes.append(args)),
        _robotSimulationPanel=None,
        _step6TaskSpaceBoxCenter=lambda: (1.0, 2.0, 3.0),
    )
    methods["_onSetTaskSpaceBox"](host, True, 200.0, 0.9)
    assert boxes[-1][2] == 0.30 and host._parameterNode.step6TaskSpaceBoxOpacity == 0.30


def test_run_options_offer_dev_fast_mode_and_depth_peeling_before_planning():
    """Operator 2026-10-03: depth peeling as a GUI option before planning, alongside
    the development fast mode. Both display/run options; fast mode stays off."""
    panel = (PYTHON / "DENTORobotSimulationPanel.py").read_text()
    shell = (PYTHON / "dentobot_workflow/widget_robot_shell.py").read_text()
    logic = (PYTHON / "dentobot_workflow/logic_robot_overlays.py").read_text()
    assert "self.devFastModeCheckBox.checked = False" in panel
    assert "self.depthPeelingCheckBox.checked = True" in panel
    group = panel.index("self.planningRunOptionsGroup = qt.QGroupBox(")
    assert group < panel.index("self.planApproachButton = qt.QPushButton(")
    assert '"set_dev_fast_mode": self._onSetDevFastMode' in shell
    assert '"set_depth_peeling": self._onSetDepthPeeling' in shell
    assert "view_node.SetUseDepthPeeling(bool(enabled))" in logic
    methods = _methods(
        PYTHON / "dentobot_workflow/widget_robot_placement.py",
        "RobotPlacementWidgetMixin",
        {"_onSetDevFastMode", "_onSetDepthPeeling"},
        {"_": lambda text: text},
    )
    peeling = []
    host = SimpleNamespace(
        _robotWorkflowFacade=SimpleNamespace(_dev_first_complete_route=False),
        logic=SimpleNamespace(setStep6DepthPeeling=peeling.append),
    )
    methods["_onSetDevFastMode"](host, True)
    assert host._robotWorkflowFacade._dev_first_complete_route is True
    methods["_onSetDevFastMode"](host, False)
    assert host._robotWorkflowFacade._dev_first_complete_route is False
    methods["_onSetDepthPeeling"](host, False)
    assert peeling == [False]


def test_robot_mesh_load_hides_only_the_expected_stl_coordinate_warning():
    """Error log 2026-10-03: AddModel(path, RAS) still warns that the URDF STL has
    no coordinate header. Warnings are hidden only during the load and restored."""
    shell = (PYTHON / "dentobot_workflow/widget_robot_shell.py").read_text()
    logic = (PYTHON / "dentobot_workflow/logic_robot_placement.py").read_text()
    assert "self.logic.addRobotMeshModel(pose.mesh_path)" in shell
    assert "model = self.addRobotMeshModel(pose.mesh_path)" in logic
    assert logic.count("AddModel(") == 1
    state = {"display": True, "seen": None}

    class VtkObject:
        @staticmethod
        def GetGlobalWarningDisplay():
            return state["display"]

        @staticmethod
        def GlobalWarningDisplayOff():
            state["display"] = False

        @staticmethod
        def SetGlobalWarningDisplay(value):
            state["display"] = value

    def add_model(path, coordinates):
        state["seen"] = (path, coordinates, state["display"])
        if path == "missing.stl":
            raise RuntimeError("load failed")
        return "model"

    slicer = SimpleNamespace(
        vtkMRMLStorageNode=SimpleNamespace(CoordinateSystemRAS=0),
        modules=SimpleNamespace(models=SimpleNamespace(logic=lambda: SimpleNamespace(AddModel=add_model))),
    )
    methods = _methods(
        PYTHON / "dentobot_workflow/logic_robot_placement.py",
        "RobotPlacementLogicMixin",
        {"addRobotMeshModel"},
        {"vtk": SimpleNamespace(vtkObject=VtkObject), "slicer": slicer},
    )
    load = methods["addRobotMeshModel"]
    load = getattr(load, "__func__", load)
    assert load("link-1.stl") == "model"
    assert state["seen"] == ("link-1.stl", 0, False) and state["display"] is True
    try:
        load("missing.stl")
    except RuntimeError:
        pass
    assert state["display"] is True


def test_ghost_drag_observes_transform_modified_so_accept_uses_dragged_pose():
    """Operator 2026-10-04: dragging the Base ghost then Accept snapped back. Matrix
    edits fire TransformModifiedEvent only, so the candidate was never restaged."""
    events = []
    methods = _methods(
        PYTHON / "dentobot_workflow/widget_robot_placement.py",
        "RobotPlacementWidgetMixin",
        {"_bindManualBaseCandidateInteractionNode"},
        {"slicer": SimpleNamespace(vtkMRMLTransformNode=SimpleNamespace(
            TransformModifiedEvent="TransformModified")),
         "vtk": SimpleNamespace(vtkCommand=SimpleNamespace(ModifiedEvent="Modified"))},
    )
    host = SimpleNamespace(
        _onManualBaseCandidateInteractionModified=object(),
        addObserver=lambda node, event, callback: events.append(("add", event)),
        removeObserver=lambda node, event, callback: events.append(("remove", event)),
    )
    first, second = object(), object()
    methods["_bindManualBaseCandidateInteractionNode"](host, first)
    methods["_bindManualBaseCandidateInteractionNode"](host, second)
    assert events == [("add", "TransformModified"), ("remove", "TransformModified"),
                      ("add", "TransformModified")]


def test_find_reachable_base_result_survives_the_base_review_refresh():
    """Operator 2026-10-04: Find Reachable Base gave no feedback; its message was
    overwritten by the Base-review label refresh."""
    methods = _methods(
        PYTHON / "dentobot_workflow/widget_robot_placement.py",
        "RobotPlacementWidgetMixin",
        {"_onStep6SearchBasePlacement", "_showBasePlacementSearchNote",
         "_basePlacementSearchNoteText", "_stageAroundBaseResult"},
        {"_": lambda text: text},
    )
    label = SimpleNamespace(text="")
    refreshes = []
    node = SimpleNamespace(robotBaseMountLocked=True, robotBaseTransform="base")
    fingerprint = {"value": "f1"}
    host = SimpleNamespace(
        _parameterNode=node,
        _robotSimulationPanel=SimpleNamespace(manualBaseReviewStatusLabel=label),
        _robotWorkflowFacade=SimpleNamespace(),
        logic=SimpleNamespace(robotBasePoseFingerprint=lambda base: fingerprint["value"]),
    )
    host._updateStep6PlanningUi = lambda message="", error=False: refreshes.append((message, error))
    host._showBasePlacementSearchNote = lambda m, error: methods["_showBasePlacementSearchNote"](host, m, error)
    note = lambda: methods["_basePlacementSearchNoteText"](host)
    methods["_onStep6SearchBasePlacement"].__globals__.update(
        slicer=SimpleNamespace(app=SimpleNamespace(processEvents=lambda: None),
                               util=SimpleNamespace(confirmYesNoDisplay=lambda text: False)))
    methods["_onStep6SearchBasePlacement"](host)  # locked; operator declines the board
    assert "the Base is locked" in note() and refreshes[-1][1] is True
    node.robotBaseMountLocked = False
    assert note() == ""  # stale once the lock state changes

    calls, choice, confirm, staged = [], [None], [False], []
    level1_best = {"matrix_world_ras_mm": [2.0] * 16, "u_mm": 0.0, "v_mm": 0.0,
                   "minimum_slider_margin_mm": 16.3,
                   "clearance": {"clear": False, "failed": "start",
                                 "contacts": ["pneumatic_spindle-Copy<->BARRIER:lip_slab"]}}
    around = {"matrix_world_ras_mm": [1.0] * 16, "depth_mm": 15.0, "u_mm": 0.0, "v_mm": 10.0,
              "yaw_deg": 0.0, "minimum_slider_margin_mm": 7.4, "minimum_revolute_margin_deg": 11.2}
    level2 = [around]

    def search(_node, progress=None, **options):
        calls.append(options)
        if options.get("exhaustive"):
            return {"best": around, "ranked": [around, dict(around, yaw_deg=-10.0)],
                    "evaluated": 3969, "feasible_count": 2000, "clear_count": 600}
        if options.get("deep"):
            return {"best": level2[0], "evaluated": 61, "feasible_count": 52, "clear_count": 1}
        return {"best": level1_best, "evaluated": 249, "feasible_count": 182, "barrier_clear": False}

    host.logic.searchForeheadBasePlacement = search
    host._robotWorkflowFacade.stageManualBaseReview = lambda m: staged.append(m) or SimpleNamespace(success=True)
    host._askBaseSearchLevel = lambda reason: choice[0]
    boards = []
    host._openBaseCandidateBoard = boards.append
    host._stageAroundBaseResult = lambda r, level: methods["_stageAroundBaseResult"](host, r, level)
    methods["_onStep6SearchBasePlacement"].__globals__.update(
        qt=SimpleNamespace(QApplication=SimpleNamespace(
            setOverrideCursor=lambda cursor: None, restoreOverrideCursor=lambda: None),
            Qt=SimpleNamespace(WaitCursor=0)),
        slicer=SimpleNamespace(app=SimpleNamespace(processEvents=lambda: None),
                               util=SimpleNamespace(confirmYesNoDisplay=lambda text: confirm[0])))
    methods["_onStep6SearchBasePlacement"](host)  # level 1 fails, operator cancels
    assert calls == [{}] and staged == []
    assert "Level 1 failed" in note() and "182 forehead-plane Bases" in note() and "lip_slab" in note()
    choice[0] = 2
    methods["_onStep6SearchBasePlacement"](host)  # operator picks level 2
    assert calls[-1] == {"reference": "current", "deep": True} and staged == [tuple([1.0] * 16)]
    assert "Level 2 staged: depth +15 mm, u +0 / v +10 mm, yaw +0 deg" in note()
    choice[0], level2[0], confirm[0] = 2, None, True
    calls.clear(); staged.clear()
    methods["_onStep6SearchBasePlacement"](host)  # level 2 empty -> confirmed level 3
    assert calls[1:] == [{"reference": "current", "deep": True},
                         {"reference": "forehead_seat", "deep": True, "exhaustive": True}]
    assert staged == [tuple([1.0] * 16)] and "Level 3 staged" in note()
    assert "1) depth +15 mm" in note() and "2) depth +15 mm, u +0 / v +10 mm, yaw -10 deg" in note()
    assert len(boards) == 1 and boards[0]["clear_count"] == 600  # level 3 offered the board
    choice[0], confirm[0] = 3, False
    calls.clear()
    methods["_onStep6SearchBasePlacement"](host)  # operator picks level 3 directly, no board
    assert calls[-1] == {"reference": "forehead_seat", "deep": True, "exhaustive": True}
    assert len(boards) == 1
    choice[0] = 4
    calls.clear(); staged.clear()
    methods["_onStep6SearchBasePlacement"](host)  # level 4: board without auto staging
    assert calls[-1] == {"reference": "forehead_seat", "deep": True, "exhaustive": True}
    assert len(boards) == 2 and staged == []
    node.robotBaseMountLocked = True
    confirm[0] = True
    calls.clear(); staged.clear()
    methods["_onStep6SearchBasePlacement"](host)  # locked Base: preview-only board, no staging
    assert calls == [{"reference": "forehead_seat", "deep": True, "exhaustive": True}]
    assert len(boards) == 3 and staged == []
    node.robotBaseMountLocked = False
    widget_source = (PYTHON / "dentobot_workflow/widget_robot_placement.py").read_text()
    board = widget_source[widget_source.index("    def _openBaseCandidateBoard("):]
    assert "self.logic.showManualBaseCandidateGhost(matrix)" in board  # locked: display-only
    assert "dialog.finished.connect(lambda _result=0: clear_preview())" in board
    assert "dialog.setModal(False)" in board and "table.itemSelectionChanged.connect(preview)" in board
    assert "facade.stageManualBaseReview(tuple(previous))" in board  # cancel restores
    level1_best["clearance"] = {"clear": True}
    calls.clear(); staged.clear()
    search_result = search
    host.logic.searchForeheadBasePlacement = lambda n, progress=None, **o: dict(
        search_result(n, progress, **o), barrier_clear=True)
    methods["_onStep6SearchBasePlacement"](host)  # level 1 succeeds: no prompt
    assert calls == [{}] and staged == [tuple([2.0] * 16)] and "Level 1: 182 of 249" in note()
    logic = (PYTHON / "dentobot_workflow/logic_robot_placement.py").read_text()
    propose = logic[logic.index("    def proposeVirtualForeheadAndBase("):]
    assert "deep = search(deep=True)" in propose and '"barrierClear"' in propose  # one-click fallback
    fingerprint["value"] = "f2"
    assert note() == ""  # stale once the Base pose changes
    robot = (PYTHON / "dentobot_workflow/widget_robot.py").read_text()
    assert '"_basePlacementSearchNoteText", lambda: "")()' in robot


def test_planning_aid_toggles_win_over_every_view_preset_and_keep_low_opacity():
    """Operator 2026-10-04: barrier and task-space box reappeared (box at full
    opacity) after Base acceptance and other 6.1/6.2 refreshes."""
    methods = _methods(
        PYTHON / "dentobot_workflow/widget_view_composition.py",
        "ViewCompositionWidgetMixin",
        {"_discardHiddenStep6PlanningAids"},
        {},
    )
    keys = {"nodes:step6MouthBarrier", "nodes:step6ReachEnvelope",
            "nodes:step6TaskSpaceBox", "nodes:step6MrmlRobot"}
    host = SimpleNamespace(_parameterNode=SimpleNamespace(
        step6ShowMouthBarrier=False, step6ShowReachEnvelope=True, step6ShowTaskSpaceBox=False))
    methods["_discardHiddenStep6PlanningAids"](host, keys)
    assert keys == {"nodes:step6ReachEnvelope", "nodes:step6MrmlRobot"}
    controls = (PYTHON / "dentobot_workflow/widget_view_controls.py").read_text()
    sink = controls[controls.index("    def _applyWorkflowViewKeys("):]
    assert "self._discardHiddenStep6PlanningAids(visibleKeys)" in sink[:sink.index("managedNodes")]
    logic = (PYTHON / "dentobot_workflow/logic_robot_overlays.py").read_text()
    box = logic[logic.index("    def updateStep6TaskSpaceBox("):logic.index("    def step6TaskSpaceBoxShown(")]
    assert 'node.SetAttribute("DENTOBOT.DisplayOpacity", f"{opacity:.2f}")' in box
    panel = (PYTHON / "DENTORobotSimulationPanel.py").read_text()
    assert "self.displayShowMouthBarrierCheckBox = qt.QCheckBox(" in panel
    assert "self.displayShowTaskSpaceBoxCheckBox = qt.QCheckBox(" in panel


def test_collision_readback_redelivers_only_missing_objects_then_rechecks():
    """Connect 2026-10-04: the guard received 32 of 34 collision objects (reliable,
    depth-10 /collision_object) and Connect failed. Re-send only the missing ones."""
    from DENTOStep6State import redeliver_missing_collision_objects

    sent, checks = [], []
    def acknowledge():
        checks.append(1)
        return {"status": "Acknowledged", "acknowledged_object_ids": ["a", "b", "c"]}
    first = {"status": "Mismatch", "acknowledged_object_ids": ["a"]}
    result = redeliver_missing_collision_objects(first, {"a": 0, "b": 0, "c": 0}, sent.append, acknowledge)
    assert sent == ["b", "c"] and len(checks) == 1
    assert result["status"] == "Acknowledged" and result["redelivered_object_ids"] == ["b", "c"]
    stuck = lambda: {"status": "Mismatch", "acknowledged_object_ids": ["a"]}
    sent.clear()
    result = redeliver_missing_collision_objects(first, ["a", "b"], sent.append, stuck, attempts=2)
    assert sent == ["b", "b"] and result["status"] == "Mismatch"  # bounded, still fails closed
    sent.clear()
    bounds_only = {"status": "Mismatch", "acknowledged_object_ids": ["a", "b"]}
    assert redeliver_missing_collision_objects(bounds_only, ["a", "b"], sent.append, stuck) == bounds_only
    assert sent == []  # nothing missing: no redelivery masks a bounds mismatch
    stale = {"status": "Mismatch", "acknowledged_object_ids": ["a", "b"],
             "mismatches": ["runtime bounds differ for b: expected base_link bounds=(1,) mm"]}
    sent.clear()
    result = redeliver_missing_collision_objects(stale, ["a", "b"], sent.append, acknowledge)
    assert sent == ["b"] and result["status"] == "Acknowledged"  # stale pose re-sent
    sync = (PYTHON / "dentobot_workflow/logic_robot_scene_sync.py").read_text()
    assert "acknowledgement = redeliver_missing_collision_objects(" in sync
