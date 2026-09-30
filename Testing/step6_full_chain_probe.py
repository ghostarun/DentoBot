"""Fail-closed headed probe for Step 6 full-chain planning and interruption.

Call on Slicer's UI thread with the production widget/panel/facade. The probe
only uses their existing controls and evidence; it never repairs prerequisites
or invokes a planner/preview API directly.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path


class FullChainProbeError(RuntimeError):
    """A required current-state or headed-run invariant could not be proved."""

    def __init__(self, message: str, evidence: Mapping[str, object]):
        self.evidence = _jsonable(evidence)
        super().__init__(message)


def _jsonable(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return str(value)


def _same_vector(first, second, *, tolerance=1.0e-9) -> bool:
    if not isinstance(first, Mapping) or not isinstance(second, Mapping):
        return False
    if set(first) != set(second) or not first:
        return False
    try:
        return all(
            math.isclose(float(first[name]), float(second[name]), rel_tol=0.0, abs_tol=tolerance)
            for name in first
        )
    except (TypeError, ValueError, OverflowError):
        return False


def _button_enabled(button) -> bool:
    return bool(getattr(button, "enabled", False))


def _label(label) -> dict[str, object]:
    text = str(getattr(label, "text", ""))
    state = None
    reader = getattr(label, "property", None)
    if callable(reader):
        try:
            state = reader("dentobotState")
        except Exception:
            state = None
    return {"text": text, "dentobot_state": state}


def _capture(capture_callback, captures, stage):
    try:
        captures.append({"stage": stage, "result": _jsonable(capture_callback(stage))})
    except Exception as exc:
        raise RuntimeError(f"screenshot capture failed at {stage}: {exc}") from exc


def _snapshot(facade, bridge, joint_names):
    state = facade.currentRobotState()
    accepted = bridge.last_accepted_joint_positions_si()
    monitored = bridge.monitored_joint_positions_si()
    displayed = getattr(state, "joint_positions_si", None)
    if any(
        not isinstance(vector, Mapping) or set(vector) != set(joint_names)
        for vector in (accepted, monitored, displayed)
    ):
        raise ValueError("accepted, monitored, and displayed J1-J5 evidence is incomplete")
    try:
        vectors = {
            key: {name: float(value[name]) for name in joint_names}
            for key, value in (
                ("accepted", accepted), ("monitored", monitored), ("displayed", displayed)
            )
        }
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("joint evidence contains an invalid value") from exc
    if not all(math.isfinite(number) for vector in vectors.values() for number in vector.values()):
        raise ValueError("joint evidence contains a non-finite value")
    plan = facade.motionPlan
    route = {
        "motion_plan_present": plan is not None,
        "motion_plan_id": id(plan) if plan is not None else None,
        "motion_plan_success": getattr(plan, "success", None) if plan is not None else None,
        "preview_active": bool(facade.previewActive),
        "preview_phase": str(facade.currentPreviewPhase),
        "preview_index": int(facade.previewIndex),
        "return_home_required": bool(facade.returnHomeRequired),
        "incomplete_preview_evidence": _jsonable(facade.incompletePreviewEvidence),
        "displayed_has_plan": bool(getattr(state, "has_motion_plan", False)),
    }
    return {"joints_si": vectors, "route_preview": route}


def _require_same_display_only(before, after, stage, before_guard, after_guard):
    for key in ("accepted", "monitored", "displayed"):
        if not _same_vector(before["joints_si"][key], after["joints_si"][key]):
            raise ValueError(f"{stage} changed {key} J1-J5 state")
    if before["route_preview"] != after["route_preview"]:
        raise ValueError(f"{stage} changed route/preview authority")
    if _jsonable(before_guard) != _jsonable(after_guard):
        if after_guard is None or not bool(getattr(after_guard, "validate_only", False)):
            raise ValueError(f"{stage} added a non-validate-only guard request")
        if str(getattr(after_guard, "task_fingerprint", "")) == "":
            raise ValueError(f"{stage} changed guard status without current task identity")


def _read_session(parameter_node):
    raw = str(getattr(parameter_node, "step6MotionDiagnosticJson", "") or "")
    try:
        session = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("current motion-diagnostic session is absent or malformed") from exc
    if not isinstance(session, Mapping):
        raise ValueError("current motion-diagnostic session is not an object")
    return dict(session)


def _identity_matches_session(session, identity):
    outcome = session.get("full_task_outcome")
    if not isinstance(outcome, Mapping):
        return False
    expected = {
        "task_identity_fingerprint": identity["task"],
        "base_identity_fingerprint": identity["base"],
        "home_identity_fingerprint": identity["home"],
        "trajectory_identity_fingerprint": identity["trajectory"],
        "robot_profile_identity_fingerprint": identity["robot_profile"],
        "collision_scene_identity_fingerprint": identity["collision_audit"],
        "branch_id": identity["branch_id"],
    }
    return all(outcome.get(key) == value for key, value in expected.items())


def _session_context_matches(session, identity):
    return all(
        session.get(field) == identity[key]
        for field, key in (
            ("task_fingerprint", "task"),
            ("base_fingerprint", "base"),
            ("trajectory_fingerprint", "trajectory"),
            ("robot_profile_fingerprint", "robot_profile"),
        )
    )


def _require_complete_chain(facade, panel, parameter_node, identity, bridge):
    task_fingerprint = identity["task"]
    plan = facade.motionPlan
    if plan is None or not bool(getattr(plan, "success", False)):
        raise ValueError("Plan Guarded Approach produced no successful current PhasePlan")
    if str(getattr(plan, "task_fingerprint", "")) != task_fingerprint:
        raise ValueError("PhasePlan task fingerprint is not current")
    if str(getattr(plan, "requested_phase", "")) != "approach":
        raise ValueError("current PhasePlan is not the guarded Approach plan")
    phases = tuple(str(value) for value in getattr(plan, "waypoint_phases", ()))
    for field in ("source_waypoint_count", "strict_waypoint_count", "axis_waypoint_count", "contact_waypoint_count"):
        if int(getattr(plan, field, 0)) <= 0:
            raise ValueError(f"complete-chain PhasePlan has no {field}")
    if "approach" not in phases or "terminal_contact" not in phases:
        raise ValueError("PhasePlan omits guarded Approach or terminal-contact waypoints")
    if not bool(facade.drillingPreflightReady):
        raise ValueError("independent full-chain drilling preflight is not current")
    guard_identity = bridge.current_task_guard_identity()
    guard_status = bridge.last_task_joint_status()
    if (
        not isinstance(guard_identity, Mapping)
        or guard_identity.get("task_fingerprint") != task_fingerprint
        or not guard_identity.get("guard_session_id")
        or not guard_identity.get("collision_scene_policy_fingerprint")
        or guard_status is None
        or getattr(guard_status, "task_fingerprint", "") != task_fingerprint
        or getattr(guard_status, "guard_session_id", "") != guard_identity.get("guard_session_id")
        or not bool(getattr(guard_status, "validate_only", False))
        or not bool(getattr(guard_status, "accepted", False))
    ):
        raise ValueError("current complete-chain validate-only guard status/identity is unavailable")
    session = _read_session(parameter_node)
    outcome = session.get("full_task_outcome")
    if (
        session.get("state") != "Current"
        or not _session_context_matches(session, identity)
        or dict(facade.plannerComparisonIdentity()) != dict(identity)
        or not isinstance(outcome, Mapping)
        or outcome.get("status") not in {"Complete", "CompletedWithWarnings"}
        or not outcome.get("tool_orientation_fingerprint")
    ):
        raise ValueError("persisted full-chain diagnostic is not current and complete")
    stage_statuses = {
        str(item.get("stage")): str(item.get("status"))
        for item in session.get("stage_outcomes", ())
        if isinstance(item, Mapping)
    }
    if any(
        stage_statuses.get(stage) != "Passed"
        for stage in ("stage1_free_space", "stage2_fixed_axis_terminal", "stage3_drilling")
    ):
        raise ValueError("persisted full-chain diagnostic lacks three passed stages")
    if not _button_enabled(panel.previewApproachButton):
        raise ValueError("production Preview Approach remains disabled for the complete chain")
    if _button_enabled(panel.previewDrillingButton):
        raise ValueError("production Drill preview bypassed its own Approach prerequisite")
    return {
        "plan_task_fingerprint": task_fingerprint,
        "plan_waypoint_count": len(tuple(getattr(plan, "waypoint_joint_vectors_si", ()))),
        "plan_waypoint_phases": list(phases),
        "drilling_preflight_ready": True,
        "diagnostic_session_fingerprint": session.get("session_fingerprint"),
        "full_task_status": outcome.get("status"),
        "tool_orientation_fingerprint": outcome["tool_orientation_fingerprint"],
        "independent_guard_status": _jsonable(guard_status),
        "guard_identity": _jsonable(guard_identity),
        "preview_approach_enabled": True,
        "preview_drilling_enabled": False,
    }


def _preconditions(widget, panel, facade, bridge):
    if getattr(widget, "_robotSimulationPanel", None) is not panel:
        raise ValueError("provided panel is not the widget's production simulation panel")
    if getattr(widget, "_robotWorkflowFacade", None) is not facade:
        raise ValueError("provided facade is not the widget's production workflow facade")
    parameter_node = getattr(widget, "_parameterNode", None)
    logic = getattr(widget, "logic", None)
    if parameter_node is None or logic is None:
        raise ValueError("current Step 6 parameter node or logic is unavailable")
    if getattr(widget, "_workflowActionBusy", False):
        raise ValueError("another workflow action is already busy")
    if getattr(panel, "manualJogReconciliationRequired", False):
        raise ValueError("manual-jog reconciliation is required")

    state = facade.currentRobotState()
    capabilities = facade.capabilities()
    identity = dict(facade.plannerComparisonIdentity())
    required_identity = ("branch_id", "task", "base", "home", "trajectory", "robot_profile", "collision_audit")
    if any(not str(identity.get(key) or "") for key in required_identity):
        raise ValueError("case/branch/task/Base/Home/scene comparison identity is incomplete")
    if str(getattr(state, "scene_kind", "")) != "case":
        raise ValueError("current scene is not the exact active case")
    for name in ("inputVolume", "teethSegmentation"):
        node = getattr(parameter_node, name, None)
        get_id = getattr(node, "GetID", None)
        if node is None or not callable(get_id) or not get_id():
            raise ValueError(f"current case identity lacks {name} node evidence")
    if not bool(getattr(parameter_node, "step6PlanningContextImported", False)):
        raise ValueError("a current PreparedBranch is not activated")
    if not bool(getattr(state, "base_locked", False)) or not str(getattr(state, "base_node_id", "")):
        raise ValueError("current Base is not accepted and locked")
    if str(getattr(parameter_node, "step6BasePlacementStatus", "")).lower() in {"", "stale", "unlocked"}:
        raise ValueError("current Base placement status is not accepted")
    base_review = facade.manualBaseReview()
    if (
        not bool(getattr(base_review, "success", False))
        or base_review.details.get("staged") is not False
        or base_review.details.get("identityStatus") != "current"
        or base_review.details.get("acceptedMatrixWorldRasMm") is None
        or base_review.details.get("acceptanceStatus") == "unknown"
        or base_review.details.get("acceptanceUncertainty")
    ):
        raise ValueError("current accepted Base review evidence is incomplete or uncertain")

    confirmed = logic.confirmedTaskRecord(parameter_node)
    issues = tuple(logic.confirmedTaskFreshnessIssues(parameter_node))
    if confirmed is None or issues or str(confirmed.snapshot_fingerprint) != identity["task"]:
        raise ValueError("confirmed current task does not match the active case identity")
    registry = json.loads(str(parameter_node.step6TrajectoryRegistryJson or "{}"))
    branch_id = str(registry.get("selected_branch_id") or "")
    if branch_id != identity["branch_id"]:
        raise ValueError("selected PreparedBranch does not match current comparison identity")
    branch = logic.evaluatePreparedBranchEligibility(parameter_node, branch_id, registry=registry)
    if not isinstance(branch, Mapping) or not branch.get("eligible"):
        raise ValueError("current PreparedBranch is not eligible")
    if not facade.taskHomeRuntimeValidated(parameter_node):
        raise ValueError("five-joint Task Home is not runtime-validated")
    if not facade.workspaceRuntimeValidated(parameter_node):
        raise ValueError("current workspace is not runtime-validated")
    if not logic.assistedTaskLimitsReviewed(parameter_node):
        raise ValueError("current assisted joint limits are not reviewed")
    home_review = facade.manualTaskHomeReview()
    if (
        not bool(getattr(home_review, "success", False))
        or home_review.details.get("staged") is not False
        or home_review.details.get("identityStatus") != "current"
        or home_review.details.get("acceptanceStatus") == "unknown"
        or home_review.details.get("acceptanceUncertainty")
    ):
        raise ValueError("Task Home detached review is stale or unresolved")
    home = logic.taskHomeRecord(parameter_node)
    names = tuple(getattr(state, "joint_names", ()))
    if len(names) != 5 or tuple(getattr(home, "joint_names", ())) != names:
        raise ValueError("runtime-validated Task Home does not contain the canonical five joints")
    home_vector = dict(zip(names, getattr(home, "joint_positions_si", ())))
    if len(home_vector) != 5:
        raise ValueError("runtime-validated Task Home vector is incomplete")

    if (
        not bool(getattr(capabilities, "simulation_only", False))
        or not bool(getattr(capabilities, "connected", False))
        or not bool(getattr(capabilities, "planning_scene_synchronized", False))
        or int(getattr(capabilities, "planning_scene_object_count", 0)) <= 0
        or not bool(getattr(state, "ros_motion_active", False))
    ):
        raise ValueError("simulation-only ROS/MoveIt or acknowledged scene is not current")
    audit = logic.collisionSceneAuditRecord(parameter_node)
    acknowledgement = getattr(audit, "runtime_acknowledgement", {})
    if (
        audit is None
        or getattr(audit, "status", None) != "Acknowledged"
        or not isinstance(acknowledgement, Mapping)
        or acknowledgement.get("status") != "Acknowledged"
    ):
        raise ValueError("current collision scene acknowledgement is unavailable")
    tcp = str(getattr(capabilities, "tcp_link", "") or "")
    tool = str(getattr(parameter_node, "step6ToolFrame", "") or "")
    if not tcp or tcp != tool:
        raise ValueError("canonical runtime TCP and current Step 6 tool frame do not match")
    guard_identity_reader = getattr(bridge, "current_task_guard_identity", None)
    guard_identity = guard_identity_reader() if callable(guard_identity_reader) else None

    preentry = _read_session(parameter_node)
    outcome = preentry.get("full_task_outcome")
    conditioning = outcome.get("target_conditioning") if isinstance(outcome, Mapping) else None
    axis = conditioning.get("drilling_axis_world_unit") if isinstance(conditioning, Mapping) else None
    if (
        preentry.get("state") != "Current"
        or preentry.get("task_fingerprint") != identity["task"]
        or not _identity_matches_session(preentry, identity)
        or not isinstance(outcome, Mapping)
        or outcome.get("diagnostic_kind") != "preentry_ik"
        or not isinstance(axis, (list, tuple))
        or len(axis) != 3
        or not all(math.isfinite(float(value)) for value in axis)
    ):
        raise ValueError("current canonical task-derived TCP orientation identity is unavailable")

    snapshot = _snapshot(facade, bridge, names)
    joints = snapshot["joints_si"]
    if not (
        _same_vector(joints["accepted"], joints["monitored"])
        and _same_vector(joints["accepted"], joints["displayed"])
        and _same_vector(joints["accepted"], home_vector)
    ):
        raise ValueError("accepted, monitored, displayed, and Task Home J1-J5 differ")
    route = snapshot["route_preview"]
    if (
        route["motion_plan_present"]
        or route["preview_active"]
        or route["return_home_required"]
        or route["incomplete_preview_evidence"] is not None
        or bool(getattr(state, "has_motion_plan", False))
    ):
        raise ValueError("route, plan, preview, or Return Home obligation already exists")
    # Production stage diagnostics reject this exact live phase-session gate.
    # No public façade query exposes it, so read only the existing gate value.
    if bool(getattr(facade, "_phase_guard_session_id", "")):
        raise ValueError("an active task phase-guard session already exists")
    if _button_enabled(panel.previewApproachButton) or _button_enabled(panel.previewDrillingButton):
        raise ValueError("preview authority is already enabled before diagnostics")
    if not _button_enabled(panel.planApproachButton):
        raise ValueError("production Plan Guarded Approach prerequisites are not enabled")
    if any(not _button_enabled(getattr(panel, f"checkPlanning{stage}Button", None)) for stage in ("P1", "P2", "P3")):
        raise ValueError("one or more production P1/P2/P3 diagnostic buttons are disabled")
    return parameter_node, names, identity, guard_identity, snapshot


def run_full_chain_interruption_probe(
    widget,
    panel,
    facade,
    capture_callback,
    process_events,
    wait_until,
) -> dict[str, object]:
    """Run P1/P2/P3, one guarded-plan attempt, and a stopped Approach preview."""

    evidence: dict[str, object] = {
        "probe": "step6_full_chain_interruption",
        "probe_local_button_invocations": {
            "diagnostic_P1": 0,
            "diagnostic_P2": 0,
            "diagnostic_P3": 0,
            "plan_guarded_approach": 0,
            "preview_approach": 0,
            "stop_preview_after_first_prefix": 0,
            "return_home_after_interruption": 0,
        },
        "captures": [],
        "fresh_complete_cycle": "NOT_RUN",
    }
    captures = evidence["captures"]
    invocations = evidence["probe_local_button_invocations"]
    try:
        if not all(callable(value) for value in (capture_callback, process_events, wait_until)):
            raise ValueError("capture_callback, process_events, and wait_until must be callable")
        bridge = getattr(facade, "_bridge", None)
        if bridge is None or not all(callable(getattr(bridge, name, None)) for name in (
            "last_accepted_joint_positions_si", "monitored_joint_positions_si",
            "last_task_joint_status", "current_task_guard_identity",
        )):
            raise ValueError("existing bridge accepted/monitored/guard evidence queries are unavailable")
        parameter_node, joint_names, identity, guard_identity, initial = _preconditions(
            widget, panel, facade, bridge
        )
        evidence.update({
            "identity": identity,
            "active_case_nodes": {
                "input_volume_id": str(widget._parameterNode.inputVolume.GetID()),
                "teeth_segmentation_id": str(widget._parameterNode.teethSegmentation.GetID()),
            },
            "guard_identity_before": _jsonable(guard_identity),
            "guard_status_before": _jsonable(bridge.last_task_joint_status()),
            "initial_state": initial,
            "probe_local_facade_call_invocations": {},
        })
        _capture(capture_callback, captures, "before_diagnostics")

        def click(button, name):
            if not _button_enabled(button):
                raise ValueError(f"production {name} button is disabled")
            invocations[name] = int(invocations.get(name, 0)) + 1
            button.click()
            process_events(0.05)

        diagnostics = []
        for index, stage in enumerate(("P1", "P2", "P3")):
            before = _snapshot(facade, bridge, joint_names)
            guard_before = bridge.last_task_joint_status()
            button = getattr(panel, f"checkPlanning{stage}Button")
            click(button, f"diagnostic_{stage}")
            if wait_until(lambda: not bool(getattr(widget, "_workflowActionBusy", False)), 30.0) is None and bool(getattr(widget, "_workflowActionBusy", False)):
                _capture(capture_callback, captures, f"after_{stage.lower()}")
                raise ValueError(f"{stage} workflow busy flag did not clear")
            _capture(capture_callback, captures, f"after_{stage.lower()}")
            after = _snapshot(facade, bridge, joint_names)
            guard_after = bridge.last_task_joint_status()
            _require_same_display_only(before, after, stage, guard_before, guard_after)
            session = _read_session(parameter_node)
            if (
                session.get("state") != "Current"
                or not _identity_matches_session(session, identity)
            ):
                raise ValueError(f"{stage} diagnostic session identity is not current")
            outcomes = [item for item in session.get("stage_outcomes", ()) if isinstance(item, Mapping)]
            outcome = next((item for item in outcomes if item.get("phase_id") == stage), None)
            if outcome is None:
                raise ValueError(f"{stage} result is missing from the current diagnostic session")
            if outcome.get("route_authority") != "none":
                raise ValueError(f"{stage} diagnostic claimed route authority")
            diagnostics.append({
                "phase_id": stage,
                "status": outcome.get("status"),
                "diagnostic_status": outcome.get("diagnostic_status"),
                "reason": outcome.get("reason"),
                "session_fingerprint": session.get("session_fingerprint"),
                "guard_status_after": _jsonable(guard_after),
                "route_authority": "none",
                "display_only_state_unchanged": True,
            })
            evidence["diagnostics"] = diagnostics
            if stage == "P1":
                p1_guard_identity = bridge.current_task_guard_identity()
                p1_guard_status = bridge.last_task_joint_status()
                endpoint = outcome.get("endpoint_evidence")
                phase_guard = endpoint.get("phase_guard") if isinstance(endpoint, Mapping) else None
                evaluated_guard = (
                    phase_guard.get("first_invalid_evaluated")
                    if isinstance(phase_guard, Mapping) else None
                )
                policy_fingerprint = (
                    endpoint.get("guard_policy_fingerprint")
                    if isinstance(endpoint, Mapping) else None
                )
                evidence["guard_identity_after_p1"] = _jsonable(p1_guard_identity)
                evidence["guard_status_after_p1"] = _jsonable(p1_guard_status)
                if (
                    not isinstance(p1_guard_identity, Mapping)
                    or p1_guard_identity.get("task_fingerprint") != identity["task"]
                    or not p1_guard_identity.get("guard_session_id")
                    or not p1_guard_identity.get("collision_scene_policy_fingerprint")
                    or p1_guard_identity.get("collision_scene_policy_fingerprint") != policy_fingerprint
                    or not isinstance(phase_guard, Mapping)
                    or phase_guard.get("collision_scene_policy_fingerprint") != policy_fingerprint
                    or not isinstance(evaluated_guard, Mapping)
                    or evaluated_guard.get("guard_session_id") != p1_guard_identity.get("guard_session_id")
                    or p1_guard_status is None
                    or getattr(p1_guard_status, "task_fingerprint", "") != identity["task"]
                    or getattr(p1_guard_status, "guard_session_id", "") != p1_guard_identity.get("guard_session_id")
                    or getattr(p1_guard_status, "collision_scene_policy_fingerprint", "") != policy_fingerprint
                    or not bool(getattr(p1_guard_status, "validate_only", False))
                    or str(getattr(p1_guard_status, "phase", "")) != "approach"
                ):
                    raise ValueError("P1 did not configure an exact current task/session/collision-policy guard identity")
            if index < 2 and not _button_enabled(getattr(panel, f"checkPlanning{('P2', 'P3')[index]}Button")):
                raise ValueError(f"production UI disabled the next independent diagnostic after {stage}")

        if _button_enabled(panel.previewApproachButton) or _button_enabled(panel.previewDrillingButton):
            raise ValueError("partial P1/P2/P3 diagnostic evidence enabled a preview")
        evidence["partial_diagnostic_preview_buttons_disabled"] = True
        _capture(capture_callback, captures, "partial_diagnostics_preview_locked")

        if not _button_enabled(panel.planApproachButton):
            raise ValueError("production Plan Guarded Approach became disabled")
        pre_plan_state = _snapshot(facade, bridge, joint_names)
        click(panel.planApproachButton, "plan_guarded_approach")
        if wait_until(lambda: not bool(getattr(widget, "_workflowActionBusy", False)), 300.0) is None and bool(getattr(widget, "_workflowActionBusy", False)):
            raise ValueError("Plan Guarded Approach workflow busy flag did not clear")
        label = _label(panel.approachStatusLabel)
        post_plan_state = _snapshot(facade, bridge, joint_names)
        if any(
            not _same_vector(pre_plan_state["joints_si"][key], post_plan_state["joints_si"][key])
            for key in ("accepted", "monitored", "displayed")
        ):
            _capture(capture_callback, captures, "plan_guarded_approach_failed")
            evidence.update({
                "plan_button_invocation_count": invocations.get("plan_guarded_approach", 0),
                "approach_status": label,
                "phase_result_or_diagnostic_identity": _jsonable(_read_session(parameter_node)),
                "guard_status_after_plan": _jsonable(bridge.last_task_joint_status()),
                "guard_identity_after_plan": _jsonable(bridge.current_task_guard_identity()),
                "chain_error": "Plan Guarded Approach changed accepted, monitored, or displayed J1-J5.",
            })
            raise ValueError("Plan Guarded Approach changed accepted, monitored, or displayed J1-J5")
        try:
            chain = _require_complete_chain(facade, panel, parameter_node, identity, bridge)
            if label["dentobot_state"] not in (None, "ok"):
                raise ValueError("Plan Guarded Approach UI reported a failed phase result")
        except Exception as exc:
            _capture(capture_callback, captures, "plan_guarded_approach_failed")
            evidence.update({
                "plan_button_invocation_count": invocations.get("plan_guarded_approach", 0),
                    "approach_status": label,
                    "phase_result_or_diagnostic_identity": _jsonable(_read_session(parameter_node)),
                    "guard_status_after_plan": _jsonable(bridge.last_task_joint_status()),
                    "guard_identity_after_plan": _jsonable(bridge.current_task_guard_identity()),
                    "chain_error": str(exc),
            })
            raise ValueError(f"Plan Guarded Approach failed closed: {label['text']} ({exc})") from exc
        evidence["complete_chain"] = chain
        evidence["plan_button_invocation_count"] = invocations.get("plan_guarded_approach", 0)
        evidence["approach_status"] = label
        evidence["post_plan_state"] = post_plan_state
        _capture(capture_callback, captures, "complete_guarded_chain_ready")

        speed = panel.previewSpeedCombo
        prior_speed_index = int(getattr(speed, "currentIndex"))
        slow_index = next(
            (i for i in range(int(speed.count)) if math.isclose(float(speed.itemData(i)), 0.25, abs_tol=1.0e-12)),
            None,
        )
        if slow_index is None:
            raise ValueError("slowest ordinary 0.25x preview speed is unavailable")
        setter = getattr(speed, "setCurrentIndex", None)
        setter(slow_index) if callable(setter) else setattr(speed, "currentIndex", slow_index)
        if not math.isclose(float(panel.previewSpeedMultiplier()), 0.25, rel_tol=0.0, abs_tol=1.0e-12):
            raise ValueError("production preview speed did not select 0.25x")
        click(panel.previewApproachButton, "preview_approach")

        def first_ack():
            status = bridge.last_task_joint_status()
            plan = facade.motionPlan
            total = len(tuple(getattr(plan, "waypoint_joint_vectors_si", ()))) if plan is not None else 0
            return bool(
                bool(facade.previewActive)
                and int(facade.previewIndex) >= 1
                and int(facade.previewIndex) < total
                and status is not None
                and bool(getattr(status, "accepted", False))
                and not bool(getattr(status, "validate_only", False))
                and str(getattr(status, "phase", "")) == "approach"
                and str(getattr(status, "task_fingerprint", "")) == identity["task"]
            )

        if wait_until(first_ack, 60.0) is None and not first_ack():
            raise ValueError("no accepted Approach waypoint acknowledgement arrived before timeout")
        first_status = bridge.last_task_joint_status()
        prefix_state = _snapshot(facade, bridge, joint_names)
        evidence["first_accepted_preview_ack"] = _jsonable(first_status)
        evidence["accepted_prefix_state"] = prefix_state
        _capture(capture_callback, captures, "after_first_accepted_approach_waypoint")
        if not _button_enabled(panel.stopPreviewButton):
            raise ValueError("production Stop control is not enabled after the first accepted waypoint")
        click(panel.stopPreviewButton, "stop_preview_after_first_prefix")
        if wait_until(lambda: not bool(facade.previewActive), 10.0) is None and bool(facade.previewActive):
            raise ValueError("production Stop did not deactivate preview")
        setter = getattr(speed, "setCurrentIndex", None)
        setter(prior_speed_index) if callable(setter) else setattr(speed, "currentIndex", prior_speed_index)
        process_events(0.05)

        stopped = _snapshot(facade, bridge, joint_names)
        incomplete = facade.incompletePreviewEvidence
        if (
            bool(facade.previewActive)
            or not bool(facade.returnHomeRequired)
            or not isinstance(incomplete, Mapping)
            or incomplete.get("status") != "Incomplete"
            or incomplete.get("endpointVerified") is not False
            or incomplete.get("phase") != "approach"
            or incomplete.get("taskFingerprint") != identity["task"]
            or int(incomplete.get("acceptedWaypointCount", 0)) < 1
            or len(incomplete.get("acceptedPrefix", ())) < 2
            or not _same_vector(
                incomplete.get("lastAcceptedPositionsSi"), stopped["joints_si"]["accepted"]
            )
            or not _same_vector(
                incomplete["acceptedPrefix"][-1].get("positionsSi"), stopped["joints_si"]["accepted"]
            )
        ):
            raise ValueError("Stop did not retain the current accepted prefix and Return Home obligation")
        _capture(capture_callback, captures, "interrupted_prefix_retained")

        return_before = stopped["joints_si"]["accepted"]
        if not _button_enabled(panel.returnHomeButton):
            raise ValueError("production Return Home control is not enabled for the current interrupted prefix")
        evidence["probe_local_button_invocations"]["return_home_after_interruption"] = 1
        panel.returnHomeButton.click()
        process_events(0.05)
        runtime_label = getattr(panel, "runtimeStatusLabel", None)
        return_message = str(getattr(runtime_label, "text", ""))
        if return_message != (
            "Guarded Return Home is blocked because a preview phase stopped before endpoint verification. "
            "The exact saved prefix is retained for review; recovery is not available in this session."
        ):
            raise ValueError("production Return Home UI did not report the interrupted-phase lockout")
        returned = _snapshot(facade, bridge, joint_names)
        if (
            not _same_vector(return_before, returned["joints_si"]["accepted"])
            or not _same_vector(stopped["joints_si"]["displayed"], returned["joints_si"]["displayed"])
            or not bool(facade.returnHomeRequired)
            or _jsonable(facade.incompletePreviewEvidence) != _jsonable(incomplete)
        ):
            raise ValueError("blocked Return Home changed accepted/displayed state or cleared interruption evidence")
        evidence.update({
            "interruption": {
                "preview_active_after_stop": bool(facade.previewActive),
                "return_home_required": bool(facade.returnHomeRequired),
                "incomplete_preview_evidence": _jsonable(incomplete),
                "blocked_return_home": {
                    "success": False,
                    "visible_status": return_message,
                    "production_policy_code": "guarded_return_partial_phase",
                    "policy_code_source": "DENTORobotWorkflowFacade.returnToTaskHome source; UI callback discards structured result",
                },
                "accepted_state_unchanged_by_return_attempt": True,
                "displayed_state_unchanged_by_return_attempt": True,
                "teleport_or_rollback": False,
                "hardware_controller_or_drill_action": False,
            },
            "final_state": returned,
            "guard_identity_after": _jsonable(bridge.current_task_guard_identity()),
            "fresh_complete_cycle": "NOT_RUN",
        })
        _capture(capture_callback, captures, "final_interrupted_state")
        return _jsonable(evidence)
    except FullChainProbeError:
        raise
    except Exception as exc:
        evidence["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        raise FullChainProbeError(str(exc), evidence) from exc
