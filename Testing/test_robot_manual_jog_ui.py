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
        {"Mapping": Mapping, "isfinite": math.isfinite},
    )
    panel_type = type("PanelProbe", (), methods)
    panel = panel_type()
    panel._manualJogLimits = {"valid": True}
    panel._manualJogLimitsValid = True
    panel._manualJogAvailable = True
    panel._manualJogGuardAvailable = True
    panel._manualJogBusy = False
    panel._manualJogAcceptedJointPositionsSi = {JOINT_NAMES[0]: 0.0}
    panel.manualJogReconciliationRequired = False
    panel.manualJogJointControls = {}
    panel.resetManualJogDraftButton = _Control()
    panel.checkManualDraftStateButton = _Control()
    panel.reconcileManualJogButton = _Control()
    panel.guardedManualJogButton = _Control()
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
    assert '"reconcile_manual_jog": 5' in panel_source
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
    assert '"check_manual_draft_state": 5' in panel_source
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
        host._onShellCheckManualRobotDraftState(requested)
        return panel, facade, mirrors, accepted_updates

    failed = {
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
    panel, facade, mirrors, accepted_updates = invoke(failed, changed=changed_draft)
    assert facade.check_calls == [requested]
    assert facade.jog_calls == []
    assert mirrors == []
    assert accepted_updates == []
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
    off_target_panel, _facade, mirrors, _accepted_updates = invoke(off_target)
    assert mirrors == []
    assert "Static verdict: passed" in off_target_panel.manualDraftStateCheckStatusLabel.text
    assert "endpoint status failed" in off_target_panel.manualDraftStateCheckStatusLabel.text
    assert "position residual 5 mm" in off_target_panel.manualDraftStateCheckStatusLabel.text

    unknown, facade, mirrors, accepted_updates = invoke(
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
