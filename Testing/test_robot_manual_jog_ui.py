"""Pure host checks for the Step 6 manual jog controls and mirror gate."""

from __future__ import annotations

import ast
import json
import math
from collections.abc import Mapping
from math import degrees, isfinite, radians
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
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


def test_manual_jog_controls_use_reviewed_mechanical_intersection_and_keep_j6_fixed():
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
    panel.taskHomeCandidateLabel = _Control()
    panel._manualJogLimits = {}
    panel._manualJogAvailable = True
    panel._manualJogBusy = False
    panel._manualJogDraftInitialized = False
    panel._manualJogDisplayValues = (0.0,) * 5
    panel._manualJogEvidence = None
    panel.resetManualJogDraftButton = _Control()
    panel.guardedManualJogButton = _Control()
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
    assert panel.manualJogJointControls[JOINT_NAMES[0]][1].minimum == -90.0
    assert panel.manualJogJointControls[JOINT_NAMES[0]][1].maximum == 100.0

    _slider, j1, _label = panel.manualJogJointControls[JOINT_NAMES[0]]
    j1.setValue(120.0)
    panel._onManualJogNumericChanged(JOINT_NAMES[0], j1.value)
    assert j1.value == 100.0
    assert panel.manualJogJointControls[JOINT_NAMES[0]][0].value == 10000

    panel._onManualJogSliderChanged(JOINT_NAMES[3], 0)
    assert panel.manualJogJointControls[JOINT_NAMES[3]][1].value == -2.0
    assert set(panel.manualJogJointPositionsSi()) == set(JOINT_NAMES)
    assert "pneumatic_spindle-Copy_Revolute-6" not in panel.manualJogJointPositionsSi()
    assert len(ghost_updates) == 2
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
    assert "J1 10.00 deg" in panel.taskHomeCandidateLabel.text
    assert "J2 3.00 mm" in panel.taskHomeCandidateLabel.text
    assert "J5 30.00 deg" in panel.taskHomeCandidateLabel.text
    assert "J6 excluded" in panel.taskHomeCandidateLabel.text
    assert "pneumatic_spindle" not in panel.taskHomeCandidateLabel.text
    panel.setManualJogAcceptedState({})
    assert panel._manualJogAcceptedJointPositionsSi is None
    assert "state unavailable" in panel.taskHomeCandidateLabel.text

    panel._manualJogAcceptedJointPositionsSi = None
    incompatible = _joint_limits(
        ((200, 220), (-2, 4), (-45, 60), (-2, 2), (-170, 170))
    )
    panel.setManualJogLimits(mechanical, incompatible)
    panel.setManualJogAvailability(True, True)
    assert not panel.guardedManualJogButton.enabled


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

        def setManualJogStatus(self, state, message, evidence=None):
            self.status = (state, message)
            if evidence is not None:
                self.evidence = dict(evidence)

        def setManualJogRequestPending(self):
            self.pending = True

        def setManualJogRequestComplete(self):
            self.pending = False

        def setManualJogAcceptedState(self, positions):
            self.accepted.append(dict(positions))

    class Facade:
        def __init__(self, result):
            self.result = result
            self.calls = []

        def guardManualRobotJog(self, positions):
            self.calls.append(dict(positions))
            return self.result

    def invoke(details, *, success=True, request=None):
        result = SimpleNamespace(
            success=success, message="guard evidence", details=details
        )
        request = request or {
            name: float(index) for index, name in enumerate(JOINT_NAMES)
        }
        panel = Panel()
        panel.draft = dict(request)
        facade = Facade(result)
        mirrors = []
        host = type("ShellProbe", (), {"_onShellGuardedManualJog": method})()
        host._robotSimulationPanel = panel
        host._robotWorkflowFacade = facade
        host._workflowActionBusy = False
        host._setRobotJointsFromSi = lambda positions, *, publish_to_ros: (
            mirrors.append((dict(positions), publish_to_ros)) or (True, "")
        )
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


def test_explicit_base_and_home_acceptance_use_the_existing_facade_owners():
    base_accept = _methods(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        {"onLockRobotBaseMount"},
        {},
    )["onLockRobotBaseMount"]
    shell_methods = _methods(
        PYTHON / "dentobot_workflow/widget_robot_shell.py",
        "RobotShellWidgetMixin",
        {"_onStep6SaveTaskHome"},
        {},
    )

    class Facade:
        def __init__(self):
            self.calls = []
            self.result = SimpleNamespace(success=True, message="accepted")

        def lockBase(self):
            self.calls.append("lockBase")
            return self.result

        def saveTaskHome(self):
            self.calls.append("saveTaskHome")
            return self.result

    facade = Facade()
    base_host = SimpleNamespace(
        _parameterNode=object(),
        logic=object(),
        _robotWorkflowFacade=facade,
        _captureCaseFoundationSessionSnapshot=lambda: None,
        _isStep3BActive=lambda: False,
        _updateStep6PlanningUi=lambda *_args, **_kwargs: None,
    )
    base_accept(base_host)

    home_result_labels = []
    home_host = SimpleNamespace(
        _robotWorkflowFacade=facade,
        _robotSimulationPanel=SimpleNamespace(homeStatusLabel=object()),
        _setStep6PanelResult=lambda label, result: home_result_labels.append(
            (label, result)
        ),
        _updateStep6PlanningUi=lambda *_args, **_kwargs: None,
    )
    shell_methods["_onStep6SaveTaskHome"](home_host)

    assert facade.calls == ["lockBase", "saveTaskHome"]
    assert len(home_result_labels) == 1
    assert '"Accept Base"' in (
        PYTHON / "dentobot_workflow/widget_robot_shell.py"
    ).read_text(encoding="utf-8")
    assert '"Accept Task Home"' in (
        PYTHON / "DENTORobotSimulationPanel.py"
    ).read_text(encoding="utf-8")

    class Matrix:
        values = (
            (1.0, 0.0, 0.0, 1.0),
            (0.0, 1.0, 0.0, 2.0),
            (0.0, 0.0, 1.0, 3.0),
        )

        def GetElement(self, row, column):
            return self.values[row][column]

    base_pose_evidence = _methods(
        PYTHON / "dentobot_workflow/widget_robot.py",
        "RobotWidgetMixin",
        {"_step6BasePoseEvidence"},
        {
            "math": math,
            "vtk": SimpleNamespace(vtkMatrix4x4=Matrix),
            "_": str,
        },
    )["_step6BasePoseEvidence"]
    base = SimpleNamespace(GetMatrixTransformToWorld=lambda _matrix: None)
    logic = SimpleNamespace(
        isRobotBaseTransformNode=lambda node: node is base,
        robotBasePoseFingerprint=lambda _node: "0123456789abcdef",
    )
    review_host = SimpleNamespace(
        _parameterNode=SimpleNamespace(robotBaseTransform=base), logic=logic
    )
    evidence = base_pose_evidence(review_host)
    assert "world RAS origin (1.000, 2.000, 3.000) mm" in evidence
    assert "pose fingerprint 0123456789ab" in evidence


def test_manual_record_export_preserves_display_only_accepted_and_rejected_evidence(
    tmp_path,
):
    destination = tmp_path / "manual-simulation.json"
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
        {"Path": Path, "json": json, "qt": qt_stub, "slicer": slicer_stub, "_": str},
    )["_onStep6ExportManualRecord"]

    record = {
        "record_status": "historical_display_only",
        "events": [
            {"kind": "guard_rejected", "requested": {"J1": 0.1}},
            {"kind": "guard_accepted", "accepted": {"J1": 0.0}},
        ],
    }

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
        def __init__(self):
            self.error = None
            self.calls = 0

        def manualSimulationRecord(self):
            self.calls += 1
            if self.error:
                raise self.error
            return record

    panel = Panel()
    facade = Facade()
    host = SimpleNamespace(_robotSimulationPanel=panel, _robotWorkflowFacade=facade)
    export(host)

    assert facade.calls == 1
    assert json.loads(destination.read_text(encoding="utf-8")) == record
    assert "historical/display-only" in panel.export_status[1]
    assert panel.status_calls == 0
    assert panel.status == ("error", "Guard status: rejected — collision.")
    assert panel.evidence == {"lastGuardFailure": "collision"}

    facade.error = RuntimeError("complete Task Home identity is unavailable")
    export(host)
    assert len(dialog_calls) == 1
    assert panel.status_calls == 0
    assert panel.status == ("error", "Guard status: rejected — collision.")
    assert panel.export_status[0] == "blocked"
    assert "complete Task Home identity is unavailable" in panel.export_status[1]
    assert panel.evidence == {"lastGuardFailure": "collision"}
    assert len(errors) == 1
    assert "complete Task Home identity is unavailable" in errors[0]
