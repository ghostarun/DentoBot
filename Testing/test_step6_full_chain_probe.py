import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from Testing import step6_full_chain_probe as probe


JOINTS = ("J1", "J2", "J3", "J4", "J5")
_DEFAULT_GUARD_IDENTITY = object()
IDENTITY = {
    "branch_id": "branch-1", "task": "task-1", "base": "base-1",
    "home": "home-1", "trajectory": "trajectory-1",
    "robot_profile": "profile-1", "collision_audit": "audit-1",
}


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


def _session(stages=(), *, complete=False):
    outcome = _identity_outcome(
        diagnostic_kind="preentry_ik",
        target_conditioning={"drilling_axis_world_unit": [0.0, 0.0, 1.0]},
        status="Complete" if complete else "NotRun",
        tool_orientation_fingerprint="orientation-1" if complete else "",
    )
    return {
        "state": "Current", "task_fingerprint": IDENTITY["task"],
        "base_fingerprint": IDENTITY["base"],
        "trajectory_fingerprint": IDENTITY["trajectory"],
        "robot_profile_fingerprint": IDENTITY["robot_profile"],
        "session_fingerprint": "session-1", "full_task_outcome": outcome,
        "stage_outcomes": list(stages),
    }


class _Button:
    def __init__(self, action=None, enabled=True):
        self.enabled = enabled
        self.action = action
        self.clicks = 0

    def click(self):
        self.clicks += 1
        if self.action:
            self.action()


class _Label:
    def __init__(self, text="", state="ok"):
        self.text, self.state = text, state

    def property(self, key):
        return self.state if key == "dentobotState" else None


class _Speed:
    values = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)

    def __init__(self):
        self.currentIndex = 5

    @property
    def count(self):
        return len(self.values)

    def itemData(self, index):
        return self.values[index]

    def setCurrentIndex(self, index):
        self.currentIndex = index


class _Node:
    step6PlanningContextImported = True
    step6BasePlacementStatus = "Accepted"
    step6ToolFrame = "dentobot_drill_tcp"
    step6TrajectoryRegistryJson = json.dumps({"selected_branch_id": IDENTITY["branch_id"]})
    step6MotionDiagnosticJson = json.dumps(_session())
    inputVolume = SimpleNamespace(GetID=lambda: "case-volume")
    teethSegmentation = SimpleNamespace(GetID=lambda: "case-teeth")


class _Bridge:
    def __init__(self):
        self.accepted = dict.fromkeys(JOINTS, 0.0)
        self.monitored = dict(self.accepted)
        self.status = None
        self.identity = None

    def last_accepted_joint_positions_si(self):
        return dict(self.accepted)

    def monitored_joint_positions_si(self):
        return dict(self.monitored)

    def last_task_joint_status(self):
        return self.status

    def current_task_guard_identity(self):
        return dict(self.identity) if self.identity is not None else None


class _Logic:
    def __init__(self):
        self.limits_reviewed = True
        self.home = SimpleNamespace(joint_names=JOINTS, joint_positions_si=(0, 0, 0, 0, 0))

    def confirmedTaskRecord(self, _node):
        return SimpleNamespace(snapshot_fingerprint=IDENTITY["task"])

    def confirmedTaskFreshnessIssues(self, _node):
        return ()

    def evaluatePreparedBranchEligibility(self, *_args, **_kwargs):
        return {"eligible": True}

    def taskHomeRecord(self, _node):
        return self.home

    def assistedTaskLimitsReviewed(self, _node):
        return self.limits_reviewed

    def collisionSceneAuditRecord(self, _node):
        return SimpleNamespace(
            status="Acknowledged", runtime_acknowledgement={"status": "Acknowledged"}
        )


class _Facade:
    def __init__(self, widget, bridge):
        self.widget, self._bridge = widget, bridge
        self.motionPlan = None
        self.previewActive = False
        self.currentPreviewPhase = ""
        self.previewIndex = 0
        self.returnHomeRequired = False
        self.incompletePreviewEvidence = None
        self.drillingPreflightReady = False
        self.allow_full_chain = True

    def currentRobotState(self):
        return SimpleNamespace(
            scene_kind="case", base_locked=True, base_node_id="base-node",
            ros_motion_active=True, has_motion_plan=self.motionPlan is not None,
            joint_names=JOINTS, joint_positions_si=dict(self.widget.displayed),
        )

    def capabilities(self):
        return SimpleNamespace(
            simulation_only=True, connected=True, planning_scene_synchronized=True,
            planning_scene_object_count=4, tcp_link="dentobot_drill_tcp",
        )

    def plannerComparisonIdentity(self):
        return dict(IDENTITY)

    def taskHomeRuntimeValidated(self, _node):
        return True

    def workspaceRuntimeValidated(self, _node):
        return True

    def manualBaseReview(self):
        return SimpleNamespace(success=True, details={
            "staged": False, "identityStatus": "current",
            "acceptedMatrixWorldRasMm": [0.0] * 16,
        })

    def manualTaskHomeReview(self):
        return SimpleNamespace(success=True, details={
            "staged": False, "identityStatus": "current", "acceptanceStatus": "review",
        })

    def returnToTaskHome(self):
        return SimpleNamespace(
            success=False, code="guarded_return_partial_phase",
            message="Return Home is blocked after interrupted preview.",
        )


class _Widget:
    def __init__(self):
        self._parameterNode = _Node()
        self.logic = _Logic()
        self.displayed = dict.fromkeys(JOINTS, 0.0)
        self._workflowActionBusy = False


def _harness(*, plan_success=True, full_chain=True, p1_guard_identity=_DEFAULT_GUARD_IDENTITY):
    widget = _Widget()
    bridge = _Bridge()
    facade = _Facade(widget, bridge)
    facade.allow_full_chain = full_chain
    panel = SimpleNamespace(manualJogReconciliationRequired=False)
    panel._buttons = []

    def button(name, action=None, enabled=True):
        result = _Button(action, enabled)
        setattr(panel, name, result)
        panel._buttons.append(result)
        return result

    for stage in ("P1", "P2", "P3"):
        def diagnostic(stage=stage):
            session = _session()
            outcomes = []
            for old in ("P1", "P2", "P3"):
                if old > stage:
                    continue
                item = {
                    "phase_id": old, "status": "Passed", "diagnostic_status": "passed",
                    "reason": "checked", "route_authority": "none",
                }
                if old == "P1":
                    item["endpoint_evidence"] = {
                        "guard_policy_fingerprint": "policy-1",
                        "phase_guard": {
                            "status": "passed",
                            "collision_scene_policy_fingerprint": "policy-1",
                            "first_invalid_evaluated": {"guard_session_id": "guard-1"},
                        },
                    }
                outcomes.append(item)
            session["stage_outcomes"] = outcomes
            widget._parameterNode.step6MotionDiagnosticJson = json.dumps(session)
            if stage == "P1":
                bridge.identity = (
                    {
                        "task_fingerprint": IDENTITY["task"],
                        "guard_session_id": "guard-1",
                        "collision_scene_policy_fingerprint": "policy-1",
                    }
                    if p1_guard_identity is _DEFAULT_GUARD_IDENTITY
                    else p1_guard_identity
                )
            current_identity = bridge.identity or {}
            bridge.status = SimpleNamespace(
                task_fingerprint=current_identity.get("task_fingerprint", IDENTITY["task"]),
                guard_session_id=current_identity.get("guard_session_id", "guard-1"),
                collision_scene_policy_fingerprint=current_identity.get(
                    "collision_scene_policy_fingerprint", "policy-1"
                ),
                phase="approach" if stage == "P1" else stage,
                validate_only=True, accepted=True,
            )
        button(f"checkPlanning{stage}Button", diagnostic)

    panel.previewApproachButton = button("previewApproachButton", enabled=False)
    panel.previewDrillingButton = button("previewDrillingButton", enabled=False)
    panel.stopPreviewButton = button("stopPreviewButton", enabled=False)

    def plan():
        panel.approachStatusLabel.text = "Exact guarded plan status"
        panel.approachStatusLabel.state = "ok" if plan_success else "error"
        if not plan_success:
            return
        facade.motionPlan = SimpleNamespace(
            success=True, task_fingerprint=IDENTITY["task"], requested_phase="approach",
            waypoint_phases=("approach", "terminal_contact"),
            waypoint_joint_vectors_si=({"J1": 0.1}, {"J1": 0.2}, {"J1": 0.3}), source_waypoint_count=3,
            strict_waypoint_count=1, axis_waypoint_count=1, contact_waypoint_count=1,
            tool_orientation_fingerprint="orientation-1",
        )
        facade.drillingPreflightReady = full_chain
        panel.previewApproachButton.enabled = True
        stage_outcomes = [
            {"stage": name, "status": "Passed"}
            for name in ("stage1_free_space", "stage2_fixed_axis_terminal", "stage3_drilling")
        ]
        full = _identity_outcome(
            status="Complete", tool_orientation_fingerprint="orientation-1"
        )
        session = {
            "state": "Current", "task_fingerprint": IDENTITY["task"],
            "base_fingerprint": IDENTITY["base"],
            "trajectory_fingerprint": IDENTITY["trajectory"],
            "robot_profile_fingerprint": IDENTITY["robot_profile"],
            "session_fingerprint": "complete-1", "full_task_outcome": full,
            "stage_outcomes": stage_outcomes,
        }
        widget._parameterNode.step6MotionDiagnosticJson = json.dumps(session)

    button("planApproachButton", plan)

    def preview():
        facade.previewActive = True
        facade.currentPreviewPhase = "approach"
        facade.previewIndex = 1
        accepted = {**bridge.accepted, "J1": 0.1}
        bridge.accepted = accepted
        bridge.monitored = dict(accepted)
        widget.displayed = dict(accepted)
        bridge.status = SimpleNamespace(
            accepted=True, validate_only=False, phase="approach",
            task_fingerprint=IDENTITY["task"], sequence=1,
        )
        panel.stopPreviewButton.enabled = True

    def stop():
        facade.previewActive = False
        facade.returnHomeRequired = True
        return_button.enabled = True
        positions = dict(bridge.accepted)
        facade.incompletePreviewEvidence = {
            "status": "Incomplete", "endpointVerified": False,
            "phase": "approach", "taskFingerprint": IDENTITY["task"],
            "acceptedWaypointCount": 1,
            "acceptedPrefix": [
                {"phase": "home", "positionsSi": dict.fromkeys(JOINTS, 0.0)},
                {"phase": "approach", "positionsSi": positions},
            ],
            "lastAcceptedPositionsSi": positions,
        }

    panel.runtimeStatusLabel = _Label()
    return_button = button("returnHomeButton", enabled=False)
    def blocked_return():
        panel.runtimeStatusLabel.text = (
            "Guarded Return Home is blocked because a preview phase stopped before endpoint verification. "
            "The exact saved prefix is retained for review; recovery is not available in this session."
        )
    return_button.action = blocked_return

    # Replace the no-op buttons with their production-action stand-ins.
    panel.previewApproachButton.action = preview
    panel.stopPreviewButton.action = stop
    panel.previewSpeedCombo = _Speed()
    panel.previewSpeedMultiplier = lambda: panel.previewSpeedCombo.values[panel.previewSpeedCombo.currentIndex]
    panel.approachStatusLabel = _Label()
    widget._robotSimulationPanel = panel
    widget._robotWorkflowFacade = facade
    return widget, panel, facade


def _run(widget, panel, facade):
    return probe.run_full_chain_interruption_probe(
        widget, panel, facade,
        capture_callback=lambda stage: {"ui": Path(f"{stage}.png")},
        process_events=lambda _seconds: None,
        wait_until=lambda predicate, _timeout: True if predicate() else None,
    )


def test_precondition_failure_happens_before_any_production_action():
    widget, panel, facade = _harness()
    widget.logic.limits_reviewed = False
    with pytest.raises(probe.FullChainProbeError) as raised:
        _run(widget, panel, facade)
    assert all(button.clicks == 0 for button in panel._buttons)
    assert raised.value.evidence["failure"]["message"] == "current assisted joint limits are not reviewed"
    json.dumps(raised.value.evidence, allow_nan=False)


def test_diagnostics_are_display_only_and_plan_is_invoked_once_fail_closed():
    widget, panel, facade = _harness(plan_success=False)
    with pytest.raises(probe.FullChainProbeError) as raised:
        _run(widget, panel, facade)
    evidence = raised.value.evidence
    assert [e["phase_id"] for e in evidence["diagnostics"]] == ["P1", "P2", "P3"]
    assert all(e["display_only_state_unchanged"] and e["route_authority"] == "none" for e in evidence["diagnostics"])
    assert evidence["probe_local_button_invocations"]["plan_guarded_approach"] == 1
    assert evidence["plan_button_invocation_count"] == 1
    assert evidence["approach_status"]["text"] == "Exact guarded plan status"
    assert any(item["stage"] == "plan_guarded_approach_failed" for item in evidence["captures"])


def test_full_chain_and_first_accepted_prefix_stop_return_lockout_and_json_output():
    widget, panel, facade = _harness()
    result = _run(widget, panel, facade)
    json.dumps(result, allow_nan=False)
    assert result["guard_identity_before"] is None
    assert result["guard_identity_after_p1"] == {
        "task_fingerprint": IDENTITY["task"],
        "guard_session_id": "guard-1",
        "collision_scene_policy_fingerprint": "policy-1",
    }
    calls = result["probe_local_button_invocations"]
    assert calls["plan_guarded_approach"] == 1
    assert calls["preview_approach"] == calls["stop_preview_after_first_prefix"] == 1
    assert calls["return_home_after_interruption"] == 1
    assert "preview_drilling" not in calls and "plan_drilling" not in calls
    assert result["partial_diagnostic_preview_buttons_disabled"] is True
    assert result["interruption"]["incomplete_preview_evidence"]["acceptedWaypointCount"] == 1
    assert result["interruption"]["blocked_return_home"]["production_policy_code"] == "guarded_return_partial_phase"
    assert result["interruption"]["accepted_state_unchanged_by_return_attempt"] is True
    assert result["interruption"]["teleport_or_rollback"] is False
    assert result["fresh_complete_cycle"] == "NOT_RUN"


def test_incomplete_independent_chain_never_starts_preview():
    widget, panel, facade = _harness(full_chain=False)
    with pytest.raises(probe.FullChainProbeError) as raised:
        _run(widget, panel, facade)
    assert "independent full-chain drilling preflight" in raised.value.evidence["chain_error"]
    assert raised.value.evidence["probe_local_button_invocations"]["plan_guarded_approach"] == 1
    assert panel.previewApproachButton.clicks == 0


@pytest.mark.parametrize("p1_guard_identity", [
    {"task_fingerprint": "stale-task", "guard_session_id": "guard-1", "collision_scene_policy_fingerprint": "policy-1"},
    {"task_fingerprint": IDENTITY["task"], "guard_session_id": "stale-session", "collision_scene_policy_fingerprint": "policy-1"},
    {"task_fingerprint": IDENTITY["task"], "guard_session_id": "guard-1", "collision_scene_policy_fingerprint": "stale-policy"},
])
def test_p1_guard_identity_mismatch_stops_before_p2_p3_or_planner(p1_guard_identity):
    widget, panel, facade = _harness(p1_guard_identity=p1_guard_identity)
    with pytest.raises(probe.FullChainProbeError) as raised:
        _run(widget, panel, facade)
    evidence = raised.value.evidence
    assert evidence["guard_identity_before"] is None
    assert evidence["guard_identity_after_p1"] == p1_guard_identity
    assert panel.checkPlanningP1Button.clicks == 1
    assert panel.checkPlanningP2Button.clicks == panel.checkPlanningP3Button.clicks == 0
    assert panel.planApproachButton.clicks == 0
    assert "task/session/collision-policy guard identity" in evidence["failure"]["message"]
    json.dumps(evidence, allow_nan=False)
