from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

TESTING = Path(__file__).resolve().parent
if str(TESTING) not in sys.path:
    sys.path.insert(0, str(TESTING))

import step6_complete_cycle_probe as probe  # noqa: E402
import step6_full_chain_probe as full_chain  # noqa: E402


JOINTS = ("J1", "J2", "J3", "J4", "J5")
IDENTITY = {
    "branch_id": "branch-1", "task": "task-1", "base": "base-1",
    "home": "home-1", "trajectory": "trajectory-1",
    "robot_profile": "profile-1", "collision_audit": "audit-1",
}
HOME = dict.fromkeys(JOINTS, 0.0)
ENTRY = {**HOME, "J1": 0.1}
TARGET = {**HOME, "J1": 0.2}


@dataclass
class _Status:
    accepted: bool
    validate_only: bool
    task_fingerprint: str
    guard_session_id: str
    phase: str
    sequence: int = -1
    requested_positions: tuple[float, ...] = ()


class _Button:
    def __init__(self, action=None, enabled=True):
        self.action, self.enabled, self.clicks = action, enabled, 0

    def click(self):
        self.clicks += 1
        if self.action:
            self.action()


class _Speed:
    values = (0.25, 0.5, 1.0)

    def __init__(self):
        self.currentIndex = 2

    @property
    def count(self):
        return len(self.values)

    def itemData(self, index):
        return self.values[index]

    def setCurrentIndex(self, index):
        self.currentIndex = index


class _Bridge:
    CARTESIAN_START_POSITION_TOLERANCE_MM = 0.25
    CARTESIAN_START_ORIENTATION_TOLERANCE_DEG = 0.5

    def __init__(self, facade):
        self.facade = facade
        self.accepted, self.monitored = dict(HOME), dict(HOME)
        self.status, self.identity = None, None
        self.fk_offset = 0.0
        self.reject_reverse = False
        self.native_call_count = 0

    def last_accepted_joint_positions_si(self):
        return dict(self.accepted)

    def monitored_joint_positions_si(self):
        return dict(self.monitored)

    def last_task_joint_status(self):
        return self.status

    def current_task_guard_identity(self):
        return dict(self.identity) if self.identity else None

    def compute_tcp_pose_world_ras_mm(self, _positions, *, base_transform):
        assert base_transform == "base-transform"
        position = (1.0, 0.0, 0.0) if self.facade.completedPhase == "approach" else (2.0, 0.0, 0.0)
        matrix = (
            (1.0, 0.0, 0.0, position[0] + self.fk_offset),
            (0.0, 1.0, 0.0, position[1]),
            (0.0, 0.0, 1.0, position[2]),
            (0.0, 0.0, 0.0, 1.0),
        )
        return True, "fake authoritative FK", matrix

    def apply_task_phase_joint_positions(self, positions, *, task_fingerprint, phase, sequence):
        self.native_call_count += 1
        ok = not self.reject_reverse
        self.status = _Status(
            accepted=ok,
            validate_only=False,
            task_fingerprint=task_fingerprint,
            guard_session_id=self.identity["guard_session_id"],
            phase=phase,
            sequence=sequence,
            requested_positions=tuple(positions[name] for name in JOINTS),
        )
        if ok:
            self.accepted = dict(positions)
            self.monitored = dict(positions)
        return ok, "fake reverse accepted" if ok else "fake reverse rejected"


class _Facade:
    def __init__(self, widget):
        self.widget = widget
        self._bridge = _Bridge(self)
        self.motionPlan = None
        self.previewActive = False
        self.currentPreviewPhase = ""
        self.previewIndex = 0
        self.completedPhase = ""
        self.returnHomeRequired = False
        self.incompletePreviewEvidence = None
        self.drillingPreflightReady = False
        self._phase_guard_session_id = ""
        self._phase_sequence = 0
        self._accepted_motion_history = []
        self.plan_count = 0
        self.return_action_count = 0
        self.fail_chain = False

    def currentRobotState(self):
        return SimpleNamespace(
            scene_kind="case",
            joint_names=JOINTS,
            joint_positions_si=dict(self.widget.displayed),
            has_motion_plan=self.motionPlan is not None,
        )

    def plannerComparisonIdentity(self):
        return dict(IDENTITY)

    def returnToTaskHome(self):
        self.return_action_count += 1
        history = self._accepted_motion_history
        accepted_count = 0
        for current, destination in zip(reversed(history[1:]), reversed(history[:-1])):
            phase = "retraction" if current["phase"] in {"terminal_contact", "drilling", "retraction"} else "approach"
            ok, message = self._bridge.apply_task_phase_joint_positions(
                destination["positions"],
                task_fingerprint=IDENTITY["task"],
                phase=phase,
                sequence=self._phase_sequence,
            )
            if not ok:
                return SimpleNamespace(success=False, code="task_home_return_failed", message=message, details={})
            accepted_count += 1
            self._phase_sequence += 1
        self._bridge.accepted, self._bridge.monitored = dict(HOME), dict(HOME)
        self.widget.displayed = dict(HOME)
        self._accepted_motion_history = []
        self.motionPlan = None
        self.previewActive = False
        self.currentPreviewPhase = ""
        self.previewIndex = 0
        self.completedPhase = ""
        self.returnHomeRequired = False
        self.incompletePreviewEvidence = None
        self._phase_guard_session_id = ""
        self._robotSimulationPanel.runtimeStatusLabel.text = probe.RETURN_HOME_COMPLETE_TEXT
        self._robotSimulationPanel.planApproachButton.enabled = True
        self._robotSimulationPanel.previewApproachButton.enabled = False
        self._robotSimulationPanel.planDrillingButton.enabled = False
        self._robotSimulationPanel.previewDrillingButton.enabled = False
        details = {
            "axialRetractionCompleted": True,
            "acceptedReverseWaypointCount": accepted_count,
            "capturedHomeMaximumJointError": 0.0,
            "capturedHomeMonitoredJointPositionsSi": dict(HOME),
        }
        return SimpleNamespace(success=True, code="task_home_returned", message=probe.RETURN_HOME_COMPLETE_TEXT, details=details)


class _Logic:
    def taskHomeRecord(self, _node):
        return SimpleNamespace(joint_names=JOINTS, joint_positions_si=tuple(HOME.values()))


class _Node:
    robotBaseTransform = "base-transform"
    inputVolume = SimpleNamespace(GetID=lambda: "volume")
    teethSegmentation = SimpleNamespace(GetID=lambda: "teeth")
    step6MotionDiagnosticJson = ""


def _identity_outcome(**extra):
    return {
        "task_identity_fingerprint": IDENTITY["task"],
        "base_identity_fingerprint": IDENTITY["base"],
        "home_identity_fingerprint": IDENTITY["home"],
        "trajectory_identity_fingerprint": IDENTITY["trajectory"],
        "robot_profile_identity_fingerprint": IDENTITY["robot_profile"],
        "collision_scene_identity_fingerprint": IDENTITY["collision_audit"],
        "branch_id": IDENTITY["branch_id"],
        **extra,
    }


def _plan(phase, vectors, phases, orientation):
    return SimpleNamespace(
        success=True,
        task_fingerprint=IDENTITY["task"],
        requested_phase=phase,
        waypoint_joint_vectors_si=tuple(vectors),
        waypoint_phases=tuple(phases),
        source_waypoint_count=len(vectors),
        strict_waypoint_count=1,
        axis_waypoint_count=1,
        contact_waypoint_count=1,
        tool_orientation_fingerprint=orientation,
    )


def _harness(monkeypatch, *, fail_chain=False, fail_guard=False, endpoint_mismatch=False, reject_return=False):
    node = _Node()
    widget = SimpleNamespace(
        _parameterNode=node,
        logic=_Logic(),
        displayed=dict(HOME),
        _workflowActionBusy=False,
    )
    facade = _Facade(widget)
    panel = SimpleNamespace()
    panel.previewSpeedCombo = _Speed()
    panel.previewSpeedMultiplier = lambda: panel.previewSpeedCombo.values[panel.previewSpeedCombo.currentIndex]
    panel.previewProgressLabel = SimpleNamespace(text="", property=lambda _key: "ok")
    panel.approachStatusLabel = SimpleNamespace(text="", property=lambda _key: "ok")
    panel.drillingStatusLabel = SimpleNamespace(text="", property=lambda _key: "ok")
    panel.runtimeStatusLabel = SimpleNamespace(text="")

    def set_session(session_id):
        outcome = _identity_outcome(
            status="Complete",
            tool_orientation_fingerprint="orientation-1",
            tool_axis_ras=[0.0, 0.0, 1.0],
            target_conditioning={
                "entry_world_ras_mm": [1.0, 0.0, 0.0],
                "target_world_ras_mm": [2.0, 0.0, 0.0],
            },
        )
        node.step6MotionDiagnosticJson = json.dumps({
            "state": "Current",
            "task_fingerprint": IDENTITY["task"],
            "base_fingerprint": IDENTITY["base"],
            "trajectory_fingerprint": IDENTITY["trajectory"],
            "robot_profile_fingerprint": IDENTITY["robot_profile"],
            "session_fingerprint": session_id,
            "full_task_outcome": outcome,
            "stage_outcomes": [
                {"stage": stage, "status": "Passed"}
                for stage in ("stage1_free_space", "stage2_fixed_axis_terminal", "stage3_drilling")
            ],
        })

    def plan_approach():
        facade.plan_count += 1
        session_id = f"session-{facade.plan_count}"
        guard_id = f"guard-{facade.plan_count}"
        set_session(session_id)
        facade.motionPlan = _plan(
            "approach",
            ({**HOME, "J1": 0.05}, ENTRY),
            ("approach", "terminal_contact"),
            "orientation-1",
        )
        facade.drillingPreflightReady = not fail_chain
        facade._phase_guard_session_id = guard_id
        facade._phase_sequence = 10
        facade._accepted_motion_history = [{"positions": dict(HOME), "phase": "home"}]
        facade._bridge.identity = {
            "task_fingerprint": IDENTITY["task"],
            "guard_session_id": guard_id,
            "collision_scene_policy_fingerprint": "policy-1",
        }
        facade._bridge.status = _Status(
            accepted=not fail_guard,
            validate_only=True,
            task_fingerprint=IDENTITY["task"],
            guard_session_id=guard_id,
            phase="approach",
        )
        panel.previewApproachButton.enabled = True

    def finish_preview(phase, plan):
        facade.previewActive = True
        facade.currentPreviewPhase = phase
        facade.previewIndex = 0
        facade._preview_pumps = 0
        panel.previewProgressLabel.text = "preview active"
        facade._pending_plan = plan
        facade._pending_phase = phase

    def finish_events(_seconds):
        if not facade.previewActive:
            return
        facade._preview_pumps += 1
        if facade._preview_pumps < 2:
            return
        phase, plan = facade._pending_phase, facade._pending_plan
        vectors = tuple(plan.waypoint_joint_vectors_si)
        phases = tuple(plan.waypoint_phases)
        endpoint = dict(vectors[-1])
        facade._bridge.accepted = endpoint
        facade._bridge.monitored = endpoint
        widget.displayed = endpoint
        for vector, waypoint_phase in zip(vectors, phases):
            facade._accepted_motion_history.append({"positions": dict(vector), "phase": waypoint_phase})
        facade._phase_sequence += len(vectors)
        facade.previewActive = False
        facade.completedPhase = phase
        facade.previewIndex = len(vectors)
        facade.returnHomeRequired = True
        facade._bridge.status = SimpleNamespace(
            accepted=True,
            validate_only=False,
            task_fingerprint=IDENTITY["task"],
            guard_session_id=facade._phase_guard_session_id,
            phase=phases[-1],
        )
        panel.previewProgressLabel.text = probe.PREVIEW_COMPLETE_TEXT
        if phase == "approach":
            panel.planDrillingButton.enabled = True
        else:
            panel.returnHomeButton.enabled = True

    def plan_drill():
        facade.motionPlan = _plan(
            "drilling",
            ({**HOME, "J1": 0.15}, TARGET),
            ("drilling", "drilling"),
            "orientation-1",
        )
        panel.planDrillingButton.enabled = False
        panel.previewDrillingButton.enabled = True

    panel.planApproachButton = _Button(plan_approach)
    panel.previewApproachButton = _Button(enabled=False)
    panel.planDrillingButton = _Button(enabled=False)
    panel.previewDrillingButton = _Button(enabled=False)
    panel.returnHomeButton = _Button(enabled=False)
    panel.previewApproachButton.action = lambda: finish_preview("approach", facade.motionPlan)
    panel.planDrillingButton.action = plan_drill
    panel.previewDrillingButton.action = lambda: finish_preview("drilling", facade.motionPlan)
    panel.returnHomeButton.action = lambda: facade.returnToTaskHome()
    panel._robot = facade
    panel._widget = widget
    panel.manualJogReconciliationRequired = False
    widget._robotSimulationPanel = panel
    widget._robotWorkflowFacade = facade
    facade._robotSimulationPanel = panel
    if endpoint_mismatch:
        facade._bridge.fk_offset = 1.0
    if reject_return:
        facade._bridge.reject_reverse = True

    def preconditions(_widget, _panel, _facade, bridge):
        initial = full_chain._snapshot(_facade, bridge, JOINTS)
        return node, JOINTS, dict(IDENTITY), None, initial

    monkeypatch.setattr(probe, "ACTION_TIMEOUT_SEC", 0.01)
    monkeypatch.setattr(probe, "RETURN_HOME_TIMEOUT_SEC", 0.0)
    monkeypatch.setattr(full_chain, "_preconditions", preconditions)
    return widget, panel, facade, finish_events


def _run(widget, panel, facade, process_events):
    return probe.run_complete_cycles(
        widget,
        panel,
        facade,
        process_events=process_events,
        capture_callback=lambda stage: {"stage": stage},
        joint_names=JOINTS,
    )


def test_two_fresh_cycles_verify_endpoint_fk_and_observe_actual_reverse(monkeypatch):
    widget, panel, facade, process_events = _harness(monkeypatch)
    original_native = facade._bridge.apply_task_phase_joint_positions
    original_return = facade.returnToTaskHome
    result = _run(widget, panel, facade, process_events)

    assert result["fresh_repeat_completed"] is True
    assert result["route_fingerprint_comparison_used"] is False
    assert [cycle["route_provenance"]["diagnostic_session_fingerprint"] for cycle in result["cycles"]] == ["session-1", "session-2"]
    assert all(
        cycle["boundaries"]["approach_endpoint_verified"]["endpoint_fk"]["observation_kind"]
        == "post_completion_observation"
        for cycle in result["cycles"]
    )
    assert all(
        cycle["boundaries"]["drill_endpoint_verified"]["endpoint_fk"]["status"] == "passed"
        for cycle in result["cycles"]
    )
    assert all(
        cycle["boundaries"]["return_home_reverse_verified"]["phase_destination_sequence_matches_history"]
        for cycle in result["cycles"]
    )
    assert facade.return_action_count == 2
    assert facade._bridge.apply_task_phase_joint_positions == original_native
    assert facade.returnToTaskHome == original_return
    assert json.loads(json.dumps(result, allow_nan=False))["cycles"]


@pytest.mark.parametrize(
    "fail_chain, fail_guard, endpoint_mismatch",
    [(True, False, False), (False, True, False), (False, False, True)],
)
def test_incomplete_chain_guard_or_endpoint_mismatch_stops_before_drill(
    monkeypatch, fail_chain, fail_guard, endpoint_mismatch
):
    widget, panel, facade, process_events = _harness(
        monkeypatch,
        fail_chain=fail_chain,
        fail_guard=fail_guard,
        endpoint_mismatch=endpoint_mismatch,
    )
    with pytest.raises(probe.CompleteCycleProbeError) as raised:
        _run(widget, panel, facade, process_events)
    assert panel.planApproachButton.clicks == 1
    assert panel.planDrillingButton.clicks == 0
    assert panel.previewDrillingButton.clicks == 0
    assert raised.value.evidence["failure_state"]
    assert raised.value.evidence["captures"][-1]["stage"].startswith("failure_")


def test_failed_native_return_acknowledgement_cannot_advance_to_second_cycle(monkeypatch):
    widget, panel, facade, process_events = _harness(monkeypatch, reject_return=True)
    original_native = facade._bridge.apply_task_phase_joint_positions
    original_return = facade.returnToTaskHome
    with pytest.raises(probe.CompleteCycleProbeError) as raised:
        _run(widget, panel, facade, process_events)
    assert panel.planApproachButton.clicks == 1
    assert panel.returnHomeButton.clicks == 1
    assert facade.return_action_count == 1
    assert raised.value.evidence["cycles"][0]["boundaries"]["return_home_native_observation"]["native_calls"][0]["call_ok"] is False
    assert facade._bridge.apply_task_phase_joint_positions == original_native
    assert facade.returnToTaskHome == original_return
