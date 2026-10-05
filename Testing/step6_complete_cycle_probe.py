"""Fail-closed headed probe for two fresh complete Step 6 preview cycles.

The probe runs on Slicer's UI thread. It uses only production panel buttons,
current façade/bridge evidence, and the shared full-chain probe utilities. It
does not call planner, preview, Return Home, or persistence methods directly.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from datetime import datetime, timezone

import step6_full_chain_probe as full_chain


ACTION_TIMEOUT_SEC = 300.0
PREVIEW_START_TIMEOUT_SEC = 15.0
PREVIEW_COMPLETION_TIMEOUT_SEC = 900.0
# Return Home replays the retraction plus the reversed approach corridor; 300 s cut off
# completed returns at long corridors (S6-LIVE-01 2026-10-04/05). Same bound as previews.
RETURN_HOME_TIMEOUT_SEC = PREVIEW_COMPLETION_TIMEOUT_SEC
SLOW_PREVIEW_MULTIPLIER = 0.25
PREVIEW_COMPLETE_TEXT = "Guarded preview complete; endpoint verified."
RETURN_HOME_COMPLETE_TEXT = (
    "Guarded axial retraction and reverse approach completed; the monitored "
    "MoveIt state matches Task Home."
)


class CompleteCycleProbeError(full_chain.FullChainProbeError):
    """A current-state, button-flow, or completion invariant was not proved."""


def _wait_for(predicate, *, stage, timeout_sec, process_events, evidence, observe):
    start = time.monotonic()
    deadline = start + float(timeout_sec)
    while True:
        if predicate():
            return
        now = time.monotonic()
        if now >= deadline:
            timeout = {
                "stage": stage,
                "timeout_sec": float(timeout_sec),
                "elapsed_sec": max(0.0, now - start),
                "last_observed": full_chain._jsonable(observe()),
            }
            evidence.setdefault("timeouts", []).append(timeout)
            raise TimeoutError(f"{stage} did not complete within {timeout_sec:g} seconds")
        process_events(0.05)


def _home_vector(logic, parameter_node, joint_names):
    home = logic.taskHomeRecord(parameter_node)
    names = tuple(getattr(home, "joint_names", ()))
    positions = tuple(getattr(home, "joint_positions_si", ()))
    if names != tuple(joint_names) or len(positions) != len(joint_names):
        raise ValueError("current runtime Task Home does not match the canonical J1-J5 order")
    try:
        result = {name: float(value) for name, value in zip(names, positions)}
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("current runtime Task Home contains an invalid joint value") from exc
    if not all(math.isfinite(value) for value in result.values()):
        raise ValueError("current runtime Task Home contains a non-finite joint value")
    return result


def _assert_converged(snapshot, *, stage, expected=None):
    joints = snapshot["joints_si"]
    accepted = joints["accepted"]
    if not (
        full_chain._same_vector(accepted, joints["monitored"])
        and full_chain._same_vector(accepted, joints["displayed"])
    ):
        raise ValueError(f"{stage} accepted, monitored, and displayed J1-J5 do not converge")
    if expected is not None and not full_chain._same_vector(accepted, expected):
        raise ValueError(f"{stage} accepted J1-J5 do not match the expected endpoint")


def _plan_evidence(plan, *, joint_names, expected_phase, stage):
    if plan is None or getattr(plan, "success", False) is not True:
        raise ValueError(f"{stage} has no successful production PhasePlan")
    if str(getattr(plan, "requested_phase", "")) != expected_phase:
        raise ValueError(f"{stage} PhasePlan is not for {expected_phase}")
    vectors = tuple(getattr(plan, "waypoint_joint_vectors_si", ()) or ())
    if not vectors:
        raise ValueError(f"{stage} PhasePlan has no waypoint evidence")
    try:
        waypoints = []
        for index, vector in enumerate(vectors):
            if not isinstance(vector, Mapping) or set(vector) != set(joint_names):
                raise ValueError(f"waypoint {index} is not complete J1-J5 evidence")
            waypoint = {name: float(vector[name]) for name in joint_names}
            if not all(math.isfinite(value) for value in waypoint.values()):
                raise ValueError(f"waypoint {index} contains a non-finite joint value")
            waypoints.append(waypoint)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{stage} PhasePlan waypoint evidence is invalid: {exc}") from exc
    phases = tuple(str(value) for value in getattr(plan, "waypoint_phases", ()) or ())
    if len(phases) != len(waypoints):
        raise ValueError(f"{stage} PhasePlan waypoint and phase counts differ")
    return {
        "plan_instance_id": id(plan),
        "plan_task_fingerprint": str(getattr(plan, "task_fingerprint", "") or ""),
        "requested_phase": expected_phase,
        "waypoint_count": len(waypoints),
        "waypoints_joint_si": waypoints,
        "waypoint_phases": list(phases),
        "source_waypoint_count": int(getattr(plan, "source_waypoint_count", 0) or 0),
        "tool_orientation_fingerprint": str(
            getattr(plan, "tool_orientation_fingerprint", "") or ""
        ),
        "expected_endpoint_joints_si": waypoints[-1],
        "last_waypoint_guard_phase": phases[-1],
    }


def _phase_observation(facade, panel, bridge, phase_label):
    label = full_chain._label(phase_label)
    status_reader = getattr(bridge, "last_task_joint_status", None)
    identity_reader = getattr(bridge, "current_task_guard_identity", None)
    return {
        "preview_active": bool(getattr(facade, "previewActive", False)),
        "preview_phase": str(getattr(facade, "currentPreviewPhase", "") or ""),
        "preview_index": int(getattr(facade, "previewIndex", 0) or 0),
        "completed_phase": str(getattr(facade, "completedPhase", "") or ""),
        "progress_label": label,
        "incomplete_preview_evidence": full_chain._jsonable(
            getattr(facade, "incompletePreviewEvidence", None)
        ),
        "guard_status": full_chain._jsonable(status_reader() if callable(status_reader) else None),
        "guard_identity": full_chain._jsonable(identity_reader() if callable(identity_reader) else None),
    }


def _wait_for_phase_completion(
    facade,
    panel,
    bridge,
    *,
    phase,
    status_label,
    process_events,
    evidence,
    stage,
):
    start = time.monotonic()
    start_deadline = start + PREVIEW_START_TIMEOUT_SEC
    completion_deadline = start + PREVIEW_COMPLETION_TIMEOUT_SEC
    saw_active = False
    while True:
        active = bool(getattr(facade, "previewActive", False))
        if active:
            saw_active = True
        completed_phase = str(getattr(facade, "completedPhase", "") or "")
        progress = full_chain._label(panel.previewProgressLabel)
        incomplete = getattr(facade, "incompletePreviewEvidence", None)
        observed = _phase_observation(facade, panel, bridge, panel.previewProgressLabel)
        if saw_active and completed_phase == phase and progress["text"] == PREVIEW_COMPLETE_TEXT:
            return {
                "observed_active": True,
                "completed_status_observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "completion_elapsed_sec": max(0.0, time.monotonic() - start),
                **observed,
            }
        if incomplete is not None:
            raise ValueError(
                f"{stage} retained incomplete preview evidence instead of a verified endpoint"
            )
        if saw_active and not active:
            raise ValueError(
                f"{stage} stopped without production endpoint-verified completion"
            )
        now = time.monotonic()
        if not saw_active and now >= start_deadline:
            timeout = {
                "stage": stage + "_start",
                "timeout_sec": PREVIEW_START_TIMEOUT_SEC,
                "elapsed_sec": max(0.0, now - start),
                "last_observed": full_chain._jsonable(observed),
            }
            evidence.setdefault("timeouts", []).append(timeout)
            raise TimeoutError(f"{stage} did not start within {PREVIEW_START_TIMEOUT_SEC:g} seconds")
        if saw_active and now >= completion_deadline:
            timeout = {
                "stage": stage + "_completion",
                "timeout_sec": PREVIEW_COMPLETION_TIMEOUT_SEC,
                "elapsed_sec": max(0.0, now - start),
                "last_observed": full_chain._jsonable(observed),
            }
            evidence.setdefault("timeouts", []).append(timeout)
            raise TimeoutError(
                f"{stage} did not reach a verified endpoint within "
                f"{PREVIEW_COMPLETION_TIMEOUT_SEC:g} seconds"
            )
        process_events(0.05)


def _endpoint_fk_observation(bridge, parameter_node, session, joints_si, *, phase, drilling_truncation=None):
    outcome = session.get("full_task_outcome")
    conditioning = outcome.get("target_conditioning") if isinstance(outcome, Mapping) else None
    if not isinstance(conditioning, Mapping) or not isinstance(outcome, Mapping):
        raise ValueError(f"{phase} endpoint FK has no persisted target conditioning")
    endpoint_key = "entry_world_ras_mm" if phase == "approach" else "target_world_ras_mm"
    expected_position = conditioning.get(endpoint_key)
    drafted_target = expected_position
    endpoint_kind = "entry" if phase == "approach" else "drafted_target"
    # Policy 2b (2026-10-02): a spindle-truncated drilling plan ends at its
    # effective target; the drafted remainder is reported, not reached (r16).
    if phase == "drilling" and isinstance(drilling_truncation, Mapping) and (
        drilling_truncation.get("effective_target_ras_mm") is not None
    ):
        expected_position = drilling_truncation["effective_target_ras_mm"]
        endpoint_kind = "effective_truncated_target"
    expected_axis = outcome.get("tool_axis_ras")
    if (
        not isinstance(expected_position, (tuple, list))
        or len(expected_position) != 3
        or not isinstance(expected_axis, (tuple, list))
        or len(expected_axis) != 3
    ):
        raise ValueError(f"{phase} endpoint FK target or tool axis is incomplete")
    try:
        expected_position = tuple(float(value) for value in expected_position)
        expected_axis = tuple(float(value) for value in expected_axis)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{phase} endpoint FK target contains an invalid value") from exc
    if not all(math.isfinite(value) for value in (*expected_position, *expected_axis)):
        raise ValueError(f"{phase} endpoint FK target contains a non-finite value")
    fk = getattr(bridge, "compute_tcp_pose_world_ras_mm", None)
    if not callable(fk):
        raise ValueError("authoritative MoveIt TCP pose FK reader is unavailable")
    fk_ok, fk_message, raw_pose = fk(
        joints_si, base_transform=getattr(parameter_node, "robotBaseTransform", None)
    )
    if not fk_ok or raw_pose is None:
        raise ValueError(f"{phase} post-completion endpoint FK failed: {fk_message}")
    try:
        pose = tuple(tuple(float(raw_pose[row][column]) for column in range(4)) for row in range(4))
    except (IndexError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{phase} post-completion endpoint FK returned an invalid pose") from exc
    if not all(math.isfinite(value) for row in pose for value in row):
        raise ValueError(f"{phase} post-completion endpoint FK returned a non-finite pose")
    position_error = math.sqrt(
        sum((pose[index][3] - expected_position[index]) ** 2 for index in range(3))
    )
    actual_axis = tuple(pose[row][2] for row in range(3))
    expected_length = math.sqrt(sum(value * value for value in expected_axis))
    actual_length = math.sqrt(sum(value * value for value in actual_axis))
    if expected_length <= 1.0e-12 or actual_length <= 1.0e-12:
        raise ValueError(f"{phase} endpoint FK has a degenerate tool axis")
    cosine = max(-1.0, min(1.0, sum(a * b for a, b in zip(actual_axis, expected_axis)) / (actual_length * expected_length)))
    axis_error = math.degrees(math.acos(cosine))
    position_tolerance = float(getattr(bridge, "CARTESIAN_START_POSITION_TOLERANCE_MM", 0.25))
    axis_tolerance = float(getattr(bridge, "CARTESIAN_START_ORIENTATION_TOLERANCE_DEG", 0.5))
    if position_error > position_tolerance or axis_error > axis_tolerance:
        raise ValueError(
            f"{phase} post-completion endpoint FK residual is "
            f"{position_error:.6g} mm / {axis_error:.6g} deg"
        )
    return {
        "observation_kind": "post_completion_observation",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "authoritative_reader": "bridge.compute_tcp_pose_world_ras_mm",
        "fk_message": str(fk_message or ""),
        "accepted_joints_si": dict(joints_si),
        "expected_endpoint_world_ras_mm": expected_position,
        "expected_endpoint_kind": endpoint_kind,
        "drafted_endpoint_world_ras_mm": drafted_target,
        "drilling_truncation": full_chain._jsonable(drilling_truncation) if phase == "drilling" else None,
        "actual_pose_world_ras_mm": pose,
        "expected_tool_axis_ras": expected_axis,
        "position_residual_mm": position_error,
        "position_tolerance_mm": position_tolerance,
        "axis_residual_deg": axis_error,
        "axis_tolerance_deg": axis_tolerance,
        "status": "passed",
    }


def _verify_phase_result(
    facade,
    bridge,
    parameter_node,
    joint_names,
    *,
    phase,
    plan_evidence,
    phase_guard_session_id,
    expected_guard_identity,
    task_fingerprint,
    session_fingerprint,
    session_identity,
    snapshot,
):
    _assert_converged(
        snapshot,
        stage=f"{phase} endpoint",
        expected=plan_evidence["expected_endpoint_joints_si"],
    )
    if bool(getattr(facade, "previewActive", False)):
        raise ValueError(f"{phase} preview remains active after completion callback")
    if str(getattr(facade, "completedPhase", "") or "") != phase:
        raise ValueError(f"{phase} completion did not set the production completed-phase state")
    preview_index_observed = getattr(facade, "previewIndex", None)
    try:
        preview_index_observed = int(preview_index_observed)
    except (TypeError, ValueError, OverflowError):
        preview_index_observed = None
    waypoints = plan_evidence.get("waypoints_joint_si")
    waypoint_phases = plan_evidence.get("waypoint_phases")
    history = getattr(facade, "_accepted_motion_history", None)
    if getattr(facade, "_motion_history_task_fingerprint", None) != task_fingerprint:
        raise ValueError(f"{phase} accepted-motion history belongs to another task")
    if (
        not isinstance(history, (tuple, list))
        or not isinstance(waypoints, list)
        or not isinstance(waypoint_phases, list)
        or len(waypoints) != plan_evidence.get("waypoint_count")
        or len(waypoint_phases) != len(waypoints)
        or len(history) < len(waypoints)
    ):
        raise ValueError(f"{phase} accepted-motion history is missing planned waypoint evidence")
    history_suffix = history[-len(waypoints):]
    verified_history_suffix = []
    for index, (record, expected_positions, expected_phase) in enumerate(
        zip(history_suffix, waypoints, waypoint_phases)
    ):
        if not isinstance(record, Mapping):
            raise ValueError(f"{phase} accepted-motion history record {index} is malformed")
        positions = record.get("positions")
        if not isinstance(positions, Mapping) or set(positions) != set(joint_names):
            raise ValueError(f"{phase} accepted-motion history record {index} lacks canonical J1-J5 state")
        try:
            positions = {name: float(positions[name]) for name in joint_names}
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{phase} accepted-motion history record {index} has invalid joints") from exc
        if not all(math.isfinite(value) for value in positions.values()):
            raise ValueError(f"{phase} accepted-motion history record {index} has non-finite joints")
        observed_phase = str(record.get("phase") or "")
        if observed_phase != expected_phase or not full_chain._same_vector(
            positions, expected_positions
        ):
            raise ValueError(
                f"{phase} accepted-motion history record {index} does not match its planned waypoint and phase"
            )
        verified_history_suffix.append(
            {"phase": observed_phase, "positions_si": positions}
        )
    current_guard_identity = bridge.current_task_guard_identity()
    if (
        not isinstance(current_guard_identity, Mapping)
        or current_guard_identity.get("task_fingerprint") != task_fingerprint
        or current_guard_identity.get("guard_session_id") != phase_guard_session_id
        or current_guard_identity.get("guard_session_id") != expected_guard_identity.get("guard_session_id")
        or current_guard_identity.get("collision_scene_policy_fingerprint")
        != expected_guard_identity.get("collision_scene_policy_fingerprint")
    ):
        raise ValueError(f"{phase} current native guard identity is stale or mismatched")
    status = bridge.last_task_joint_status()
    expected_guard_phase = plan_evidence["last_waypoint_guard_phase"]
    if not (
        status is not None
        and getattr(status, "accepted", None) is True
        and getattr(status, "validate_only", None) is False
        and str(getattr(status, "task_fingerprint", "") or "") == task_fingerprint
        and str(getattr(status, "guard_session_id", "") or "") == phase_guard_session_id
        and str(getattr(status, "phase", "") or "") == expected_guard_phase
    ):
        raise ValueError(f"{phase} final native guard status is not the accepted current endpoint")
    session = full_chain._read_session(parameter_node)
    if (
        session.get("session_fingerprint") != session_fingerprint
        or session.get("state") != "Current"
        or not full_chain._session_context_matches(session, session_identity)
        or not full_chain._identity_matches_session(session, session_identity)
    ):
        raise ValueError(f"{phase} endpoint is not attached to the same current diagnostic session")
    fk = _endpoint_fk_observation(
        bridge, parameter_node, session, snapshot["joints_si"]["accepted"], phase=phase,
        drilling_truncation=getattr(facade, "drillingTruncation", None),
    )
    return {
        "native_status": full_chain._jsonable(status),
        "current_guard_identity": full_chain._jsonable(current_guard_identity),
        "diagnostic_session_fingerprint": session_fingerprint,
        "preview_index_observed_after_completion": preview_index_observed,
        "verified_accepted_motion_history_waypoint_count": len(verified_history_suffix),
        "verified_accepted_motion_history_phase_sequence": [
            record["phase"] for record in verified_history_suffix
        ],
        "verified_accepted_motion_history_suffix": verified_history_suffix,
        "post_completion_endpoint_fk": fk,
    }


def _cycle_ready(widget, panel, facade, bridge, *, identity, home, initial_nodes, joint_names):
    if getattr(widget, "_robotSimulationPanel", None) is not panel:
        raise ValueError("provided panel is not the widget's production simulation panel")
    if getattr(widget, "_robotWorkflowFacade", None) is not facade:
        raise ValueError("provided façade is not the widget's production workflow façade")
    if getattr(widget, "_workflowActionBusy", False):
        raise ValueError("another workflow action is already busy")
    state = facade.currentRobotState()
    if str(getattr(state, "scene_kind", "")) != "case":
        raise ValueError("current scene is no longer the exact active case")
    if dict(facade.plannerComparisonIdentity()) != dict(identity):
        raise ValueError("case, task, Base, Home, route, profile, or scene identity changed between cycles")
    parameter_node = getattr(widget, "_parameterNode", None)
    nodes = {
        "input_volume_id": str(parameter_node.inputVolume.GetID()),
        "teeth_segmentation_id": str(parameter_node.teethSegmentation.GetID()),
    }
    if nodes != initial_nodes:
        raise ValueError("active case node identity changed between cycles")
    snapshot = full_chain._snapshot(facade, bridge, joint_names)
    route = snapshot["route_preview"]
    if (
        route["motion_plan_present"]
        or route["preview_active"]
        or route["return_home_required"]
        or route["incomplete_preview_evidence"] is not None
        or bool(getattr(facade, "completedPhase", ""))
        or bool(getattr(facade, "_phase_guard_session_id", ""))
    ):
        raise ValueError("a prior plan, preview, incomplete phase, or guard session remains active")
    _assert_converged(snapshot, stage="cycle start", expected=home)
    if not full_chain._button_enabled(panel.planApproachButton):
        raise ValueError("production Plan Guarded Approach is disabled at the cycle boundary")
    if full_chain._button_enabled(panel.previewApproachButton) or full_chain._button_enabled(panel.previewDrillingButton):
        raise ValueError("production preview authority is enabled before the fresh cycle plan")
    return snapshot


def run_complete_cycles(
    widget,
    panel,
    facade,
    *,
    process_events,
    capture_callback,
    joint_names,
    cycles=2,
    click_guard=None,
) -> dict[str, object]:
    """Run exactly two button-driven Approach→Drill→Return Home cycles.

    A failed route, phase, monitored endpoint, Return Home, timeout, or stale
    second plan raises :class:`CompleteCycleProbeError` with all evidence
    collected before the failure. The helper intentionally leaves any active
    or incomplete route in place for review.
    """

    evidence: dict[str, object] = {
        "probe": "step6_complete_cycles",
        "cycles_requested": cycles,
        "cycles": [],
        "captures": [],
        "timeouts": [],
        "button_invocations": {
            "plan_guarded_approach": 0,
            "preview_approach": 0,
            "prepare_drill_preview": 0,
            "preview_drill": 0,
            "return_home": 0,
        },
    }
    saved_speed_index = None
    speed = getattr(panel, "previewSpeedCombo", None)
    stage_for_failure = "preconditions"

    def press(button, name, substep):
        # Each action is owned by one Step 6 substep; enter it first (r12).
        full_chain._enter_substep(widget, panel, substep, process_events)
        if click_guard is None:
            button.click()
        else:
            click_guard(button, name)

    try:
        if isinstance(cycles, bool) or cycles != 2:
            raise ValueError("the headed complete-cycle probe runs exactly two cycles")
        if not callable(process_events) or not callable(capture_callback):
            raise ValueError("process_events and capture_callback must be callable")
        try:
            requested_joint_names = tuple(str(name) for name in joint_names)
        except TypeError as exc:
            raise ValueError("joint_names must provide the canonical J1-J5 sequence") from exc
        if len(requested_joint_names) != 5 or len(set(requested_joint_names)) != 5:
            raise ValueError("joint_names must contain five distinct canonical joints")
        bridge = getattr(facade, "_bridge", None)
        if bridge is None or not all(
            callable(getattr(bridge, name, None))
            for name in (
                "last_accepted_joint_positions_si",
                "monitored_joint_positions_si",
                "last_task_joint_status",
                "current_task_guard_identity",
            )
        ):
            raise ValueError("current accepted/monitored/native guard evidence is unavailable")
        parameter_node, canonical_names, identity, initial_guard, initial = (
            full_chain._preconditions(widget, panel, facade, bridge)
        )
        if tuple(canonical_names) != requested_joint_names:
            raise ValueError("provided joint_names do not match the current canonical J1-J5 order")
        home = _home_vector(widget.logic, parameter_node, canonical_names)
        _assert_converged(initial, stage="initial case state", expected=home)
        initial_nodes = {
            "input_volume_id": str(widget._parameterNode.inputVolume.GetID()),
            "teeth_segmentation_id": str(widget._parameterNode.teethSegmentation.GetID()),
        }
        evidence.update(
            {
                "identity": full_chain._jsonable(identity),
                "active_case_nodes": initial_nodes,
                "task_home_joints_si": home,
                "initial_guard_identity": full_chain._jsonable(initial_guard),
                "initial_state": initial,
            }
        )
        full_chain._capture(capture_callback, evidence["captures"], "initial_case_home")

        if speed is None:
            raise ValueError("production preview speed control is unavailable")
        saved_speed_index = int(getattr(speed, "currentIndex"))
        slow_index = next(
            (
                index
                for index in range(int(getattr(speed, "count")))
                if math.isclose(
                    float(speed.itemData(index)),
                    SLOW_PREVIEW_MULTIPLIER,
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
            ),
            None,
        )
        if slow_index is None:
            raise ValueError("production 0.25x preview speed option is unavailable")
        prior_plan = None
        prior_session_fingerprint = ""
        prior_phase_guard_session = ""

        for cycle_number in (1, 2):
            cycle: dict[str, object] = {
                "cycle": cycle_number,
                "button_invocations": {
                    "plan_guarded_approach": 0,
                    "preview_approach": 0,
                    "prepare_drill_preview": 0,
                    "preview_drill": 0,
                    "return_home": 0,
                },
                "boundaries": {},
            }
            evidence["cycles"].append(cycle)
            boundaries = cycle["boundaries"]
            stage_for_failure = f"cycle_{cycle_number}_start"
            boundary = _cycle_ready(
                widget,
                panel,
                facade,
                bridge,
                identity=identity,
                home=home,
                initial_nodes=initial_nodes,
                joint_names=canonical_names,
            )
            boundaries["start"] = boundary
            full_chain._capture(
                capture_callback,
                evidence["captures"],
                f"cycle_{cycle_number}_home_ready",
            )

            stage_for_failure = f"cycle_{cycle_number}_guarded_plan"
            before_plan = full_chain._snapshot(facade, bridge, canonical_names)
            if not full_chain._button_enabled(panel.planApproachButton):
                raise ValueError("production Plan Guarded Approach is disabled")
            press(panel.planApproachButton, "plan_guarded_approach", full_chain.STEP6_PLANNING_SUBSTEP)
            evidence["button_invocations"]["plan_guarded_approach"] += 1
            cycle["button_invocations"]["plan_guarded_approach"] += 1
            process_events(0.05)
            _wait_for(
                lambda: not bool(getattr(widget, "_workflowActionBusy", False)),
                stage=stage_for_failure,
                timeout_sec=ACTION_TIMEOUT_SEC,
                process_events=process_events,
                evidence=evidence,
                observe=lambda: {
                    "busy": bool(getattr(widget, "_workflowActionBusy", False)),
                    "approach_status": full_chain._label(panel.approachStatusLabel),
                    "route": full_chain._snapshot(facade, bridge, canonical_names)["route_preview"],
                },
            )
            post_plan = full_chain._snapshot(facade, bridge, canonical_names)
            _assert_converged(post_plan, stage="guarded plan", expected=home)
            if not all(
                full_chain._same_vector(
                    before_plan["joints_si"][key], post_plan["joints_si"][key]
                )
                for key in ("accepted", "monitored", "displayed")
            ):
                raise ValueError("planning changed accepted, monitored, or displayed J1-J5")
            approach_label = full_chain._label(panel.approachStatusLabel)
            chain = full_chain._require_complete_chain(
                facade, panel, parameter_node, identity, bridge
            )
            if approach_label["dentobot_state"] not in full_chain.ok_states(facade):
                raise ValueError("production Plan Guarded Approach status reports failure")
            approach_plan = facade.motionPlan
            approach_plan_evidence = _plan_evidence(
                approach_plan,
                joint_names=canonical_names,
                expected_phase="approach",
                stage="Approach plan",
            )
            phase_guard_session_id = str(
                getattr(facade, "_phase_guard_session_id", "") or ""
            )
            session = full_chain._read_session(parameter_node)
            session_fingerprint = str(session.get("session_fingerprint") or "")
            guard_identity = bridge.current_task_guard_identity()
            if (
                not phase_guard_session_id
                or not isinstance(guard_identity, Mapping)
                or guard_identity.get("guard_session_id") != phase_guard_session_id
            ):
                raise ValueError("current complete route has no matching active phase-guard identity")
            if not session_fingerprint:
                raise ValueError("current complete route has no diagnostic session fingerprint")
            if cycle_number == 2 and (
                approach_plan is prior_plan
                or session_fingerprint == prior_session_fingerprint
                or phase_guard_session_id == prior_phase_guard_session
            ):
                raise ValueError("second cycle did not create a fresh plan and guard/session identity")
            prior_plan = approach_plan
            prior_session_fingerprint = session_fingerprint
            prior_phase_guard_session = phase_guard_session_id
            cycle["route_provenance"] = {
                "task_identity": full_chain._jsonable(identity),
                "diagnostic_session_fingerprint": session_fingerprint,
                "phase_guard_session_id": phase_guard_session_id,
                "current_native_guard_identity": full_chain._jsonable(guard_identity),
                "target_conditioning": full_chain._jsonable(
                    session.get("full_task_outcome", {}).get("target_conditioning")
                ),
                "tool_axis_ras": full_chain._jsonable(
                    session.get("full_task_outcome", {}).get("tool_axis_ras")
                ),
                "full_chain": chain,
                "approach_plan": approach_plan_evidence,
            }
            boundaries["guarded_plan_ready"] = post_plan
            full_chain._capture(
                capture_callback,
                evidence["captures"],
                f"cycle_{cycle_number}_guarded_plan_ready",
            )

            stage_for_failure = f"cycle_{cycle_number}_approach_preview"
            speed.setCurrentIndex(slow_index)
            if not math.isclose(
                float(panel.previewSpeedMultiplier()),
                SLOW_PREVIEW_MULTIPLIER,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            ):
                raise ValueError("production preview speed did not select 0.25x")
            if not full_chain._button_enabled(panel.previewApproachButton):
                raise ValueError("production Preview Approach button is disabled")
            phase_start = time.monotonic()
            press(panel.previewApproachButton, "preview_approach", full_chain.STEP6_PREVIEW_SUBSTEP)
            evidence["button_invocations"]["preview_approach"] += 1
            cycle["button_invocations"]["preview_approach"] += 1
            process_events(0.05)
            approach_completion = _wait_for_phase_completion(
                facade,
                panel,
                bridge,
                phase="approach",
                status_label=panel.approachStatusLabel,
                process_events=process_events,
                evidence=evidence,
                stage=stage_for_failure,
            )
            approach_snapshot = full_chain._snapshot(facade, bridge, canonical_names)
            approach_status = _verify_phase_result(
                facade,
                bridge,
                parameter_node,
                canonical_names,
                phase="approach",
                plan_evidence=approach_plan_evidence,
                phase_guard_session_id=phase_guard_session_id,
                expected_guard_identity=chain["guard_identity"],
                task_fingerprint=identity["task"],
                session_fingerprint=session_fingerprint,
                session_identity=identity,
                snapshot=approach_snapshot,
            )
            progress = full_chain._label(panel.previewProgressLabel)
            boundaries["approach_endpoint_verified"] = {
                "state": approach_snapshot,
                "completion_observation": {
                    **approach_completion,
                    "elapsed_after_button_click_sec": max(0.0, time.monotonic() - phase_start),
                    "configured_preview_speed_multiplier": SLOW_PREVIEW_MULTIPLIER,
                    "measurement_semantics": "button_click_to_completed_status_observation; not first paint",
                },
                "production_endpoint_status": progress,
                "guard_evidence": approach_status,
                "endpoint_fk": approach_status["post_completion_endpoint_fk"],
                "endpoint_verified": True,
            }
            full_chain._capture(
                capture_callback,
                evidence["captures"],
                f"cycle_{cycle_number}_approach_endpoint_verified",
            )

            stage_for_failure = f"cycle_{cycle_number}_prepare_drill"
            if not full_chain._button_enabled(panel.planDrillingButton):
                raise ValueError("production Prepare Drill Preview button is disabled after Approach")
            press(panel.planDrillingButton, "prepare_drill_preview", full_chain.STEP6_PLANNING_SUBSTEP)
            evidence["button_invocations"]["prepare_drill_preview"] += 1
            cycle["button_invocations"]["prepare_drill_preview"] += 1
            process_events(0.05)
            _wait_for(
                lambda: not bool(getattr(widget, "_workflowActionBusy", False)),
                stage=stage_for_failure,
                timeout_sec=ACTION_TIMEOUT_SEC,
                process_events=process_events,
                evidence=evidence,
                observe=lambda: {
                    "busy": bool(getattr(widget, "_workflowActionBusy", False)),
                    "drilling_status": full_chain._label(panel.drillingStatusLabel),
                    "route": full_chain._snapshot(facade, bridge, canonical_names)["route_preview"],
                },
            )
            drilling_plan = facade.motionPlan
            drilling_label = full_chain._label(panel.drillingStatusLabel)
            if drilling_label["dentobot_state"] not in full_chain.ok_states(facade):
                raise ValueError("production Prepare Drill Preview status reports failure")
            drill_plan_evidence = _plan_evidence(
                drilling_plan,
                joint_names=canonical_names,
                expected_phase="drilling",
                stage="Drill plan",
            )
            if (
                drill_plan_evidence["plan_task_fingerprint"] != identity["task"]
                or drill_plan_evidence["tool_orientation_fingerprint"]
                != chain["tool_orientation_fingerprint"]
                or drill_plan_evidence["source_waypoint_count"] <= 0
                or not full_chain._button_enabled(panel.previewDrillingButton)
            ):
                raise ValueError("production Drill plan is stale or Drill preview is still disabled")
            drill_session = full_chain._read_session(parameter_node)
            if (
                drill_session.get("session_fingerprint") != session_fingerprint
                or drill_session.get("state") != "Current"
                or not full_chain._session_context_matches(drill_session, identity)
                or not full_chain._identity_matches_session(drill_session, identity)
            ):
                raise ValueError("production Drill plan is not attached to the fresh current full-chain session")
            boundaries["drill_plan_ready"] = {
                "state": full_chain._snapshot(facade, bridge, canonical_names),
                "status": drilling_label,
                "plan": drill_plan_evidence,
            }
            full_chain._capture(
                capture_callback,
                evidence["captures"],
                f"cycle_{cycle_number}_drill_plan_ready",
            )

            stage_for_failure = f"cycle_{cycle_number}_drill_preview"
            if not full_chain._button_enabled(panel.previewDrillingButton):
                raise ValueError("production Preview Drill button is disabled")
            phase_start = time.monotonic()
            press(panel.previewDrillingButton, "preview_drill", full_chain.STEP6_PREVIEW_SUBSTEP)
            evidence["button_invocations"]["preview_drill"] += 1
            cycle["button_invocations"]["preview_drill"] += 1
            process_events(0.05)
            drill_completion = _wait_for_phase_completion(
                facade,
                panel,
                bridge,
                phase="drilling",
                status_label=panel.drillingStatusLabel,
                process_events=process_events,
                evidence=evidence,
                stage=stage_for_failure,
            )
            drill_snapshot = full_chain._snapshot(facade, bridge, canonical_names)
            drill_status = _verify_phase_result(
                facade,
                bridge,
                parameter_node,
                canonical_names,
                phase="drilling",
                plan_evidence=drill_plan_evidence,
                phase_guard_session_id=phase_guard_session_id,
                expected_guard_identity=chain["guard_identity"],
                task_fingerprint=identity["task"],
                session_fingerprint=session_fingerprint,
                session_identity=identity,
                snapshot=drill_snapshot,
            )
            boundaries["drill_endpoint_verified"] = {
                "state": drill_snapshot,
                "completion_observation": {
                    **drill_completion,
                    "elapsed_after_button_click_sec": max(0.0, time.monotonic() - phase_start),
                    "configured_preview_speed_multiplier": SLOW_PREVIEW_MULTIPLIER,
                    "measurement_semantics": "button_click_to_completed_status_observation; not first paint",
                },
                "production_endpoint_status": full_chain._label(panel.previewProgressLabel),
                "guard_evidence": drill_status,
                "endpoint_fk": drill_status["post_completion_endpoint_fk"],
                "endpoint_verified": True,
            }
            full_chain._capture(
                capture_callback,
                evidence["captures"],
                f"cycle_{cycle_number}_drill_endpoint_verified",
            )

            stage_for_failure = f"cycle_{cycle_number}_return_home"
            if not full_chain._button_enabled(panel.returnHomeButton):
                raise ValueError("production Guarded Return Home button is disabled after Drill")
            history_evidence = _motion_history_evidence(facade, canonical_names, home)
            pre_return = full_chain._snapshot(facade, bridge, canonical_names)
            _assert_converged(pre_return, stage="pre-Return Home")
            if (
                not pre_return["route_preview"]["return_home_required"]
                or pre_return["route_preview"]["incomplete_preview_evidence"] is not None
                or str(getattr(facade, "completedPhase", "") or "") != "drilling"
            ):
                raise ValueError("Return Home did not follow a verified complete Drill phase")
            return_before_text = str(getattr(panel.runtimeStatusLabel, "text", "") or "")
            starting_sequence = getattr(facade, "_phase_sequence", None)
            if isinstance(starting_sequence, bool) or not isinstance(starting_sequence, int):
                raise ValueError("current guarded phase sequence is unavailable before Return Home")
            boundaries["return_home_started"] = {
                "state": pre_return,
                "production_status_before_click": return_before_text,
                "accepted_motion_history": history_evidence,
                "phase_sequence_before_return": starting_sequence,
                "production_shell_retains_result_details": False,
                "probe_captures_result_details_during_button_callback": True,
            }
            evidence["button_invocations"]["return_home"] += 1
            cycle["button_invocations"]["return_home"] += 1
            return_observations = _observe_return_home_button(
                panel, facade, bridge, canonical_names
            )
            boundaries["return_home_native_observation"] = full_chain._jsonable(
                return_observations
            )
            boundaries["return_home_reverse_verified"] = _verify_return_home_calls(
                return_observations,
                history_evidence,
                task_fingerprint=identity["task"],
                phase_guard_session_id=phase_guard_session_id,
                starting_sequence=starting_sequence,
                joint_names=canonical_names,
            )
            process_events(0.05)

            def returned_home():
                if str(getattr(panel.runtimeStatusLabel, "text", "") or "") != RETURN_HOME_COMPLETE_TEXT:
                    return False
                current = full_chain._snapshot(facade, bridge, canonical_names)
                route = current["route_preview"]
                return bool(
                    not route["motion_plan_present"]
                    and not route["preview_active"]
                    and not route["return_home_required"]
                    and route["incomplete_preview_evidence"] is None
                    and not str(getattr(facade, "completedPhase", "") or "")
                    and not str(getattr(facade, "_phase_guard_session_id", "") or "")
                    and _same_identity(facade, identity)
                    and _home_converged(current, home)
                )

            _wait_for(
                returned_home,
                stage=stage_for_failure,
                timeout_sec=RETURN_HOME_TIMEOUT_SEC,
                process_events=process_events,
                evidence=evidence,
                observe=lambda: {
                    "runtime_status": str(getattr(panel.runtimeStatusLabel, "text", "") or ""),
                    "state": full_chain._snapshot(facade, bridge, canonical_names),
                    "completed_phase": str(getattr(facade, "completedPhase", "") or ""),
                    "phase_guard_session_id": str(getattr(facade, "_phase_guard_session_id", "") or ""),
                },
            )
            returned = full_chain._snapshot(facade, bridge, canonical_names)
            _assert_converged(returned, stage="verified Return Home", expected=home)
            post_history_raw = getattr(facade, "_accepted_motion_history", None)
            post_history = full_chain._jsonable(post_history_raw)
            boundaries["return_home_verified"] = {
                "state": returned,
                "production_status": str(getattr(panel.runtimeStatusLabel, "text", "") or ""),
                "phase_session_cleared": not bool(getattr(facade, "_phase_guard_session_id", "")),
                "accepted_motion_history_before_return": history_evidence,
                "accepted_motion_history_after_return": post_history,
                "reverse_phase_execution_status_evidence": {
                    **boundaries["return_home_reverse_verified"],
                    "production_result_details_captured_by_read_only_observer": True,
                },
                "saved_home_error": _home_error_evidence(returned, home),
                "identity_unchanged": True,
            }
            full_chain._capture(
                capture_callback,
                evidence["captures"],
                f"cycle_{cycle_number}_home_returned",
            )

        evidence["final_state"] = full_chain._snapshot(facade, bridge, canonical_names)
        evidence["fresh_repeat_completed"] = True
        evidence["route_fingerprint_comparison_used"] = False
        return full_chain._jsonable(evidence)
    except CompleteCycleProbeError:
        raise
    except Exception as exc:
        evidence["failure"] = {
            "stage": stage_for_failure,
            "type": type(exc).__name__,
            "message": str(exc),
        }
        try:
            if facade is not None and getattr(facade, "_bridge", None) is not None:
                evidence["failure_state"] = full_chain._snapshot(
                    facade,
                    facade._bridge,
                    tuple(str(name) for name in joint_names),
                )
            if callable(capture_callback):
                full_chain._capture(
                    capture_callback,
                    evidence["captures"],
                    "failure_" + str(stage_for_failure),
                )
        except Exception as capture_exc:
            evidence["failure_capture_error"] = str(capture_exc)
        raise CompleteCycleProbeError(str(exc), evidence) from exc
    finally:
        if (
            saved_speed_index is not None
            and speed is not None
            and not bool(getattr(facade, "previewActive", False))
        ):
            try:
                speed.setCurrentIndex(saved_speed_index)
                process_events(0.05)
            except Exception:
                # Preserve the route result if UI speed restoration alone fails.
                pass


def _same_identity(facade, identity):
    try:
        return dict(facade.plannerComparisonIdentity()) == dict(identity)
    except Exception:
        return False


def _home_converged(snapshot, home):
    joints = snapshot["joints_si"]
    return bool(
        full_chain._same_vector(joints["accepted"], home)
        and full_chain._same_vector(joints["monitored"], home)
        and full_chain._same_vector(joints["displayed"], home)
    )


def _motion_history_evidence(facade, joint_names, home):
    history = getattr(facade, "_accepted_motion_history", None)
    if not isinstance(history, (tuple, list)) or len(history) < 2:
        raise ValueError("production Return Home has no retained accepted-motion history")
    records = []
    for index, record in enumerate(history):
        if not isinstance(record, Mapping):
            raise ValueError(f"accepted-motion history record {index} is malformed")
        positions = record.get("positions")
        if not isinstance(positions, Mapping) or set(positions) != set(joint_names):
            raise ValueError(f"accepted-motion history record {index} lacks complete J1-J5 state")
        try:
            positions = {name: float(positions[name]) for name in joint_names}
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"accepted-motion history record {index} has invalid joints") from exc
        if not all(math.isfinite(value) for value in positions.values()):
            raise ValueError(f"accepted-motion history record {index} has non-finite joints")
        phase = str(record.get("phase") or "")
        if phase not in {"home", "approach", "terminal_contact", "drilling", "retraction"}:
            raise ValueError(f"accepted-motion history record {index} has unknown phase {phase!r}")
        records.append({"phase": phase, "positions_si": positions})
    if records[0]["phase"] != "home" or not full_chain._same_vector(
        records[0]["positions_si"], home
    ):
        raise ValueError("accepted-motion history does not begin at the saved Task Home")
    phases = [record["phase"] for record in records]
    if not all(required in phases for required in ("approach", "terminal_contact", "drilling")):
        raise ValueError("accepted-motion history does not demonstrate Approach, axial contact, and Drill phases")
    reverse_phases = [
        "retraction"
        if record["phase"] in {"terminal_contact", "drilling", "retraction"}
        else "approach"
        for record in reversed(records[1:])
    ]
    if "retraction" not in reverse_phases or "approach" not in reverse_phases:
        raise ValueError("accepted-motion history does not map to axial retraction and reverse approach")
    return {
        "records": records,
        "observed_forward_phase_sequence": phases,
        "reverse_phase_sequence_derived_from_history": reverse_phases,
        "reverse_phase_execution_count_retained_by_shell": False,
    }


def _home_error_evidence(snapshot, home):
    joints = snapshot["joints_si"]
    errors = {
        key: {
            name: abs(float(joints[key][name]) - float(home[name]))
            for name in home
        }
        for key in ("accepted", "monitored", "displayed")
    }
    return {
        "per_joint_absolute_error_si": errors,
        "accepted_monitored_displayed_all_match_saved_home": _home_converged(
            snapshot, home
        ),
        "error_source": "post_return_home_state_observation",
    }


def _observe_return_home_button(panel, facade, bridge, joint_names):
    """Observe the production button callback and its native reverse calls once."""
    native_method_name = "apply_task_phase_joint_positions"
    native_original = getattr(bridge, native_method_name, None)
    return_original = getattr(facade, "returnToTaskHome", None)
    status_reader = getattr(bridge, "last_task_joint_status", None)
    accepted_reader = getattr(bridge, "last_accepted_joint_positions_si", None)
    if not callable(native_original) or not callable(return_original):
        raise ValueError("production Return Home native/action observer is unavailable")
    if not callable(status_reader) or not callable(accepted_reader):
        raise ValueError("production Return Home accepted acknowledgement readers are unavailable")
    observations: dict[str, object] = {"native_calls": [], "production_result": None}

    def observed_native_call(*args, **kwargs):
        requested = args[0] if args else kwargs.get("positions")
        try:
            requested = {name: float(requested[name]) for name in joint_names}
        except (KeyError, TypeError, ValueError, OverflowError):
            requested = None
        request = {
            "requested_positions_si": requested,
            "task_fingerprint": str(kwargs.get("task_fingerprint") or ""),
            "phase": str(kwargs.get("phase") or ""),
            "sequence": kwargs.get("sequence"),
        }
        try:
            result = native_original(*args, **kwargs)
        except Exception as exc:
            observations["native_calls"].append(
                {**request, "call_exception": f"{type(exc).__name__}: {exc}"}
            )
            raise
        call_ok = bool(result[0]) if isinstance(result, (tuple, list)) and result else False
        message = str(result[1] if isinstance(result, (tuple, list)) and len(result) > 1 else "")
        try:
            status = status_reader()
        except Exception as exc:
            status = None
            status_error = f"{type(exc).__name__}: {exc}"
        else:
            status_error = None
        try:
            accepted = accepted_reader()
            accepted = (
                {name: float(accepted[name]) for name in joint_names}
                if isinstance(accepted, Mapping)
                else None
            )
        except Exception as exc:
            accepted = None
            accepted_error = f"{type(exc).__name__}: {exc}"
        else:
            accepted_error = None
        observations["native_calls"].append(
            {
                **request,
                "call_ok": call_ok,
                "call_message": message,
                "native_status_immediately_after_call": full_chain._jsonable(status),
                "native_status_read_error": status_error,
                "accepted_state_echo_immediately_after_call_si": accepted,
                "accepted_state_read_error": accepted_error,
            }
        )
        return result

    def observed_return_action(*args, **kwargs):
        result = return_original(*args, **kwargs)
        observations["production_result"] = {
            "success": getattr(result, "success", None),
            "code": str(getattr(result, "code", "") or ""),
            "message": str(getattr(result, "message", "") or ""),
            "details": full_chain._jsonable(getattr(result, "details", None)),
        }
        return result

    setattr(bridge, native_method_name, observed_native_call)
    setattr(facade, "returnToTaskHome", observed_return_action)
    try:
        panel.returnHomeButton.click()
    finally:
        setattr(bridge, native_method_name, native_original)
        setattr(facade, "returnToTaskHome", return_original)
    return observations


def _verify_return_home_calls(
    observations,
    history_evidence,
    *,
    task_fingerprint,
    phase_guard_session_id,
    starting_sequence,
    joint_names,
):
    expected = []
    records = history_evidence["records"]
    for current, destination in zip(reversed(records[1:]), reversed(records[:-1])):
        expected.append(
            {
                "positions_si": destination["positions_si"],
                "phase": (
                    "retraction"
                    if current["phase"] in {"terminal_contact", "drilling", "retraction"}
                    else "approach"
                ),
            }
        )
    calls = observations.get("native_calls")
    if not isinstance(calls, list) or len(calls) != len(expected) or not calls:
        raise ValueError("observed guarded reverse calls do not match retained accepted-motion history")
    for index, (call, target) in enumerate(zip(calls, expected)):
        status = call.get("native_status_immediately_after_call")
        accepted = call.get("accepted_state_echo_immediately_after_call_si")
        if (
            call.get("call_ok") is not True
            or call.get("task_fingerprint") != task_fingerprint
            or call.get("phase") != target["phase"]
            or call.get("sequence") != starting_sequence + index
            or not full_chain._same_vector(call.get("requested_positions_si"), target["positions_si"])
            or not isinstance(status, Mapping)
            or status.get("accepted") is not True
            or status.get("validate_only") is not False
            or status.get("task_fingerprint") != task_fingerprint
            or status.get("guard_session_id") != phase_guard_session_id
            or status.get("phase") != target["phase"]
            or status.get("sequence") != starting_sequence + index
            or not full_chain._same_vector(accepted, target["positions_si"])
        ):
            raise ValueError(f"guarded reverse acknowledgement {index} does not match its accepted history destination")
    result = observations.get("production_result")
    details = result.get("details") if isinstance(result, Mapping) else None
    home_error = details.get("capturedHomeMaximumJointError") if isinstance(details, Mapping) else None
    try:
        home_error = float(home_error)
    except (TypeError, ValueError, OverflowError):
        home_error = math.nan
    if (
        not isinstance(result, Mapping)
        or result.get("success") is not True
        or not isinstance(details, Mapping)
        or details.get("axialRetractionCompleted") is not True
        or details.get("acceptedReverseWaypointCount") != len(expected)
        or not math.isfinite(home_error)
        or not full_chain._same_vector(
            details.get("capturedHomeMonitoredJointPositionsSi"), records[0]["positions_si"]
        )
    ):
        raise ValueError("production Return Home result details do not confirm the observed guarded reverse and Home")
    return {
        "native_calls": calls,
        "production_result": result,
        "observed_native_reverse_call_count": len(calls),
        "accepted_reverse_waypoint_count_from_production_result": details[
            "acceptedReverseWaypointCount"
        ],
        "axial_retraction_completed": True,
        "captured_home_maximum_joint_error_from_production_result": home_error,
        "accepted_home_monitored_state_from_production_result": full_chain._jsonable(
            details.get("capturedHomeMonitoredJointPositionsSi")
        ),
        "phase_destination_sequence_matches_history": True,
    }
