"""Pure host checks for the Step 6 manual jog controls and mirror gate."""

from __future__ import annotations

import ast
import json
import math
import sys
from collections.abc import Mapping
from math import degrees, isfinite, radians
from pathlib import Path
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))
from DENTOStep6State import (  # noqa: E402
    build_manual_simulation_record,
    parse_manual_simulation_record,
)
from DENTOApplicationShell import workspace_for_stage  # noqa: E402

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
        PYTHON / "dentobot_workflow/widget_robot_shell.py",
        "RobotShellWidgetMixin",
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
        PYTHON / "dentobot_workflow/widget_robot_shell.py",
        "RobotShellWidgetMixin",
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


def _joint_limits(ranges):
    return SimpleNamespace(
        **{
            f"joint_{index}": SimpleNamespace(minimum=low, maximum=high)
            for index, (low, high) in enumerate(ranges, start=1)
        }
    )


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
        name: _method_node(shell, "RobotShellWidgetMixin", name)
        for name in (
            "_onShellConnectRobot",
            "_onShellSyncCollisionScene",
            "_onShellCheckManualRobotDraftState",
        )
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
    def to_si(j1, j2, j3, j4, j5, j6):
        return {
            JOINT_NAMES[0]: radians(j1),
            JOINT_NAMES[1]: j2 / 1000.0,
            JOINT_NAMES[2]: radians(j3),
            JOINT_NAMES[3]: j4 / 1000.0,
            JOINT_NAMES[4]: radians(j5),
            "pneumatic_spindle-Copy_Revolute-6": radians(j6),
        }

    names = {
        "setManualJogLimits",
        "setManualJogAvailability",
        "resetManualJogDraft",
        "_setManualJogDraftValues",
        "_onManualJogSliderChanged",
        "_onManualJogNumericChanged",
        "_updateManualJogDraftFromControls",
        "manualJogJointPositionsSi",
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
    panel.manualJogAcceptedStateLabel = _Control()
    panel.taskHomeCurrentStateLabel = _Control()
    panel.taskHomeCandidateLabel = _Control()
    panel.manualJogDraftLimitLabel = _Control()
    panel._manualJogLimits = {}
    panel._manualJogMechanicalLimits = None
    panel._manualJogAvailable = True
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
    assert "pneumatic_spindle-Copy_Revolute-6" not in panel.manualJogJointPositionsSi()
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
    assert "J6 excluded" in panel.taskHomeCurrentStateLabel.text
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
        PYTHON / "dentobot_workflow/widget_robot_shell.py",
        "RobotShellWidgetMixin",
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

    invalid_request = {**requested, "J6": 0.0}
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
            "_formatManualJogNativeEvidence",
            "_setManualJogStatus",
        },
        {
            "JOINT_NAMES": JOINT_NAMES,
            "Mapping": Mapping,
            "isfinite": math.isfinite,
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
    panel._manualJogMechanicalLimits = mechanical
    panel._manualJogLimitsValid = True
    panel._manualJogCommandLimitsValid = True
    panel._manualJogAvailable = True
    panel._manualJogGuardAvailable = True
    panel._manualJogGuardContextAvailable = True
    panel._manualJogBusy = False
    panel._manualJogAcceptedJointPositionsSi = {JOINT_NAMES[0]: 0.0}
    panel._manualJogDisplayValues = (0.0,) * 5
    panel.manualJogReconciliationRequired = False
    panel.manualJogJointControls = {}
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
    panel.setManualJogStatus("blocked", "Reconciliation required.", evidence)
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
        shell_path,
        "RobotShellWidgetMixin",
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

    def invoke(result):
        panel = Panel()
        facade = Facade(result)
        mirrors = []
        host = type("ShellProbe", (), {"_onShellReconcileManualRobotJog": method})()
        host._robotSimulationPanel = panel
        host._robotWorkflowFacade = facade
        host._workflowActionBusy = False
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
        shell_path,
        "RobotShellWidgetMixin",
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


def test_explicit_base_and_task_home_acceptance_use_the_facade_owners():
    base_accept = _methods(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        {"onLockRobotBaseMount"},
        {},
    )["onLockRobotBaseMount"]
    shell_methods = _methods(
        PYTHON / "dentobot_workflow/widget_robot_shell.py",
        "RobotShellWidgetMixin",
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
    assert '"Cancel Home Review"' in panel_source
    assert '"Accept Task Home"' in panel_source
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
    assert "does not change the accepted robot or ROS scene" in panel_source


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
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
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
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
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
        shell_path,
        "RobotShellWidgetMixin",
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
        "pneumatic_spindle-Copy_Revolute-6": radians(-90),
    }

    assert method(host, positions, publish_to_ros=False) == (True, "")
    assert (
        round(parameter_node.robotJoint1Deg, 6),
        parameter_node.robotJoint2Mm,
        round(parameter_node.robotJoint3Deg, 6),
        parameter_node.robotJoint4Mm,
        round(parameter_node.robotJoint5Deg, 6),
        round(parameter_node.robotJoint6Deg, 6),
    ) == (30.0, 12.0, -45.0, 3.5, 90.0, -90.0)
    assert parameter_node.modified == [17]
    assert robot_updates == [True]
    assert ros_checks == []


def test_task_home_review_displays_separate_j1_j5_states_and_failure_status():
    methods = _methods(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        {"_formatManualJogDisplayValues", "setManualTaskHomeReviewResult"},
        {
            "JOINT_NAMES": JOINT_NAMES,
            "Mapping": Mapping,
            "degrees": degrees,
            "isfinite": isfinite,
        },
    )
    panel = type("PanelProbe", (), methods)()
    panel.taskHomeCurrentStateLabel = _Control()
    panel.taskHomeCandidateLabel = _Control()
    panel.taskHomeReviewStatusLabel = _Control()
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
            },
        )
    )

    assert "Current accepted robot J1–J5" in panel.taskHomeCurrentStateLabel.text
    assert "Staged Task Home candidate" in panel.taskHomeCandidateLabel.text
    assert "J1 5.73 deg" in panel.taskHomeCurrentStateLabel.text
    assert "J1 11.46 deg" in panel.taskHomeCandidateLabel.text
    assert "Home review: review; identity: current" in panel.taskHomeReviewStatusLabel.text
    assert "use Guarded Manual Jog separately" in panel.taskHomeReviewStatusLabel.text
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
            },
        )
    )
    assert "use Guarded Manual Jog separately" not in panel.taskHomeReviewStatusLabel.text

    panel.setManualTaskHomeReviewResult(
        SimpleNamespace(
            success=False,
            message="native evidence unavailable",
            details={
                "staged": True,
                "candidateJointPositionsSi": candidate,
                "acceptedJointPositionsSi": {**accepted, "J6": 1.0},
                "identityStatus": "unknown",
                "acceptanceStatus": "unknown",
                "failureEvidence": {"reason": "scene status unavailable"},
                "acceptanceUncertainty": "save outcome may have committed",
            },
        )
    )
    assert "identity: unknown" in panel.taskHomeReviewStatusLabel.text
    assert "Failure evidence" in panel.taskHomeReviewStatusLabel.text
    assert "Acceptance uncertainty" in panel.taskHomeReviewStatusLabel.text
    assert "Current accepted robot J1–J5: unavailable" in panel.taskHomeCurrentStateLabel.text


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
        PYTHON / "dentobot_workflow/widget_robot_shell.py",
        "RobotShellWidgetMixin",
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

    panel.draft = {**candidate, "pneumatic_spindle-Copy_Revolute-6": 0.0}
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
    assert {
        "self.ui.step6TaskJointLimitsGroupBox",
        "self.ui.step6WorkspaceGroupBox",
        "self._robotSimulationPanel.homeGroup",
        "self._robotSimulationPanel.workspaceReviewGroup",
        "self._robotSimulationPanel.confirmationGroup",
        "self._robotSimulationPanel.manualJogGroup",
        "self._robotSimulationPanel.approachGroup",
        "self._robotSimulationPanel.drillingGroup",
    } <= visible[3]
    assert visible[4] == {"self._robotSimulationPanel.previewControlGroup"}
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
        "not away_from_home",
    ):
        assert condition in drilling

    imported_record = ast.dump(
        _method_node(shell_path, "RobotShellWidgetMixin", "_onStep6ImportManualRecord")
    )
    assert "previewApproachButton" not in imported_record
    assert "previewDrillingButton" not in imported_record
    stop = ast.unparse(
        _method_node(shell_path, "RobotShellWidgetMixin", "_onStep6StopPreview")
    )
    assert "resetPreviewProgress(result.message)" in stop


def test_manual_jog_action_buttons_are_split_into_narrow_rows():
    init = _method_node(
        PYTHON / "DENTORobotSimulationPanel.py",
        "DENTORobotSimulationPanel",
        "__init__",
    )
    buttons = {
        "resetManualJogDraftButton",
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
    assert "Axial roll: unconstrained (J6 excluded)" in source
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
    assert "Axial roll is unconstrained (J6 excluded)" in help_source
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
        {**candidate, "pneumatic_spindle-Copy_Revolute-6": 0.0},
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
