"""Live-state flags and widget lists behind the Step 6 reason annotations.

Each owner (the 6.1 refresh, the shell substep navigator, Case Foundation) reads
the widget state it already has and passes it to annotate_step6_controls. Nothing
here sets enabled or visible. A failure is logged and swallowed by the annotation
helper, so it never breaks the caller.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from DENTORobotWorkflowFacade import PhasePlan
from DENTOStep6State import MotionPhase

from .step6_control_reasons import (
    PANEL_CONTROLS,
    REFRESH_CONTROLS,
    SCENE_CONTROLS,
    annotate_step6_controls,
)

SHELL_CONTROLS = (
    "step6PlanningContextGroupBox",
    "ros2MotionControlGroupBox",
    "_step6PreviousSubstepButton",
    "_step6NextSubstepButton",
    "runtimeGroup",
    "collisionGroup",
)


def _base_tips(host) -> dict:
    return host.__dict__.setdefault("_step6ControlBaseTips", {})


def _widgets_for(host, panel, name: str) -> list:
    if name in ("manualJogSlider", "manualJogValue"):
        if panel is None:
            return []
        index = 0 if name == "manualJogSlider" else 1
        return [controls[index] for controls in getattr(panel, "manualJogJointControls", {}).values()]
    if name == "tcpNudgeButton":
        return list(getattr(panel, "tcpCartesianNudgeButtons", {}).values()) if panel is not None else []
    if name == "manualJogShortcut":
        return list(getattr(panel, "_manualJogKeyboardShortcuts", ())) if panel is not None else []
    if name == "tcpShortcut":
        return list(getattr(panel, "_tcpKeyboardShortcuts", ())) if panel is not None else []
    for owner in (host.ui, panel, host):
        widget = getattr(owner, name, None) if owner is not None else None
        if widget is not None:
            return [widget]
    return []


def _nav_flags(host) -> dict:
    combo = getattr(host, "_step6SubstepComboBox", None)
    index = int(combo.currentIndex) if combo is not None else 0
    return {
        "previous_substep_available": index > 0,
        "next_substep_available": index < 4,
        "comparison_running": bool(getattr(host, "_plannerComparisonState", None)),
    }


def _panel_flags(panel, facade_capabilities) -> dict:
    if panel is None:
        return {}
    mode = str(getattr(panel, "_taskHomeSetupMode", "unknown"))
    connected = mode == "connected"
    offline = mode == "offline"
    available = bool(getattr(panel, "_manualJogAvailable", False))
    busy = bool(getattr(panel, "_manualJogBusy", False))
    reconcile = bool(getattr(panel, "manualJogReconciliationRequired", False))
    accepted = getattr(panel, "_manualJogAcceptedJointPositionsSi", None)
    saved_home = bool(
        getattr(panel, "_taskHomeConfigurationReady", False)
        and getattr(panel, "_taskHomeConfiguredJointPositionsSi", None)
    )
    in_home_group = bool(getattr(panel, "_manualJogControlsInHomeGroup", False))
    reset_available = bool(connected and accepted)
    if offline:
        reset_available = bool(saved_home or getattr(panel, "_manualJogLocalJointPositionsSi", None))
    elif connected and in_home_group and saved_home:
        reset_available = True
    position = getattr(panel, "_manualEventPosition", None)
    return {
        "substep_6_2": getattr(panel, "_activeSubstep", 0) == 2,
        "substep_6_3": getattr(panel, "_activeSubstep", 0) == 3,
        "connected_runtime": connected,
        "manual_jog_available": available,
        "not_busy": not busy,
        "no_reconciliation": not reconcile,
        "reconciliation_required": reconcile,
        "reset_available": reset_available,
        "guard_available": bool(getattr(panel, "_manualJogGuardAvailable", False)),
        "manual_jog_group_visible": bool(panel.manualJogGroup.visible),
        "manual_keyboard_on": bool(panel.manualJogKeyboardEnabledCheckBox.checked),
        "no_text_focus": not panel._hasTcpTextEditorFocus(),
        "goal_group_visible": bool(panel.goalGroup.visible),
        "tcp_ik_available": bool(getattr(panel, "_tcpIkAvailable", False)),
        "tcp_drag_on": bool(getattr(panel, "_tcpDragEnabled", False)),
        "tcp_drag_checked": bool(panel.tcpDragEnabledCheckBox.checked),
        "tcp_keyboard_on": bool(panel.tcpKeyboardEnabledCheckBox.checked),
        "records_loaded": bool(getattr(panel, "_manualSimulationRecords", ())),
        "event_before": bool(position and position[0] > 0),
        "event_after": bool(position and 0 <= position[0] < position[1] - 1),
        "collision_check_available": bool(
            facade_capabilities and facade_capabilities.collision_check_available
        ),
        "runtime_connected": bool(facade_capabilities and facade_capabilities.connected),
    }


def _refresh_flags(host, refresh: Mapping[str, object]) -> dict:
    g = refresh.get
    panel = host._robotSimulationPanel
    facade = host._robotWorkflowFacade
    parameter = host._parameterNode
    locked = bool(g("locked"))
    ros2 = bool(g("ros2_active"))
    stage = bool(g("robot_stage_active"))
    review = g("review_result")
    control = host._manualBaseReviewControlState(
        bool(g("scene_prepared")), bool(g("robot_present")), locked, review, ros2
    )
    staged = bool(g("manual_base_review_staged"))
    identity = bool(g("manual_base_identity_current"))
    unknown = bool(g("manual_base_acceptance_unknown"))
    success = bool(getattr(review, "success", False))
    branch = g("branchEligibility")
    home_controls = g("task_home_controls") or {}
    plan = g("facade_plan")
    preview = bool(g("preview_active"))
    away = bool(g("away_from_home"))
    return {
        "scene_prepared": bool(g("scene_prepared")),
        "robot_present": bool(g("robot_present")),
        "base_locked": locked,
        "base_unlocked": not locked,
        "base_unlocked_or_recovery": not locked or bool(g("robot_recovery_allowed")),
        "base_stage_active": stage,
        "base_stage_idle": not stage,
        "base_accept_ready": not stage or (staged and identity and not unknown and success),
        "base_begin_ready": control["begin"],
        "base_candidate_cancellable": control["cancel"],
        "base_reconcile_available": control["reconcile"],
        "base_review_group": control["group"],
        "base_transform_node": bool(host.logic.isRobotBaseTransformNode(parameter.robotBaseTransform)),
        "action_idle": not getattr(host, "_workflowActionBusy", False),
        "ros2_active": ros2,
        "ros2_inactive": not ros2,
        "imported": bool(g("imported")),
        "branch_eligible": bool(branch and branch["eligible"]),
        "planning_anatomy_ready": bool(g("planning_anatomy_ready")),
        "home_runtime_validated": bool(g("home_runtime_validated")),
        "workspace_validated": bool(g("workspace_runtime_validated")),
        "workspace_validation_pending": not g("workspace_runtime_validated"),
        "workspace_model_present": bool(host.logic.robotWorkspaceModelNode()),
        "limit_proposal_present": bool(str(parameter.step6AssistedLimitProposalJson or "").strip()),
        "limit_review_pending": not g("assisted_reviewed"),
        "motion_preview_active": bool(
            getattr(host, "_step6MotionPreviewTimer", None) is not None
            or bool(facade and facade.previewActive)
        ),
        "motion_diagnostic_recorded": bool(str(parameter.step6MotionDiagnosticJson or "").strip()),
        "planner_comparison_recorded": bool(str(parameter.step6PlannerComparisonJson or "").strip()),
        "pre_entry_ik_ready": bool(panel is not None and panel.checkPreEntryIKButton.enabled),
        "template_model_present": parameter.finalPrintableTemplateModel is not None,
        "historical_template_override_enabled": os.environ.get(
            "DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE", ""
        ) == "1",
        "anatomy_review_available": bool(
            (facade and facade.anatomyReviewState.get("exists"))
            or (g("planning_anatomy_ready") and ros2 and os.environ.get(
                "DENTOBOT_ENABLE_HISTORICAL_ANATOMY_REVIEW", ""
            ) == "1")
        ),
        "away_from_home": away,
        "not_away_from_home": not away,
        "no_preview_active": not preview,
        "task_ready": bool(g("task_ready")),
        "runtime_ready": bool(g("runtime_ready")),
        "approach_plan_ready": bool(
            isinstance(plan, PhasePlan) and plan.success
            and plan.requested_phase == MotionPhase.APPROACH.value
        ),
        "drill_plan_ready": bool(
            isinstance(plan, PhasePlan) and plan.success
            and plan.requested_phase == MotionPhase.DRILLING.value
        ),
        "approach_complete": bool(g("approach_complete")),
        "drilling_preflight_ready": bool(g("drilling_preflight_ready")),
        "task_home_cancellable": bool(home_controls.get("cancel")),
        "task_home_reconcile_available": bool(home_controls.get("reconcile")),
    }



def annotate_refresh_controls(host, refresh: Mapping[str, object]) -> dict:
    """Annotate the 6.1 refresh's controls, including the panel and shell widgets they gate."""

    def entries():
        panel = host._robotSimulationPanel
        return [
            (name, widget)
            for name in (*REFRESH_CONTROLS, *PANEL_CONTROLS)
            for widget in _widgets_for(host, panel, name)
        ]

    def flags():
        panel = host._robotSimulationPanel
        values = _refresh_flags(host, refresh)
        values.update(_panel_flags(panel, refresh.get("facade_capabilities")))
        values.update(_nav_flags(host))
        return values

    return annotate_step6_controls("6.1 refresh", entries, flags, _base_tips(host))


def annotate_shell_controls(host) -> dict:
    """Annotate the shell's substep-visibility controls after the substep changes."""

    def entries():
        panel = host._robotSimulationPanel
        return [(name, widget) for name in SHELL_CONTROLS for widget in _widgets_for(host, panel, name)]

    return annotate_step6_controls("6.1 substep", entries, lambda: _nav_flags(host), _base_tips(host))


def annotate_case_foundation(host, scope: Mapping[str, object]) -> dict:
    """Annotate the Case Foundation controls from the locals of their refresh (``scope``)."""

    def entries():
        return [
            (name, getattr(host.ui, name))
            for name in SCENE_CONTROLS
            if getattr(host.ui, name, None) is not None
        ]

    def flags():
        parameter = host._parameterNode
        point_count = scope.get("pointCount", 0)
        placement_pending = bool(scope.get("placementPending"))
        return {
            "source_ready": bool(scope.get("sourceReady")),
            "ros_inactive": not bool(scope.get("rosActive")),
            "landmarks_actionable": bool(placement_pending or not scope.get("complete") or scope.get("evidenceIssues")),
            "landmarks_present": bool(point_count > 0 or placement_pending),
            "pose_eligible": bool(scope.get("pose_eligible")),
            "preview_uncommitted": bool(parameter.caseFoundationPreviewUncommitted),
            "foundation_content_present": bool(scope.get("hasTransientOpening") or point_count),
            "session_snapshot": bool(getattr(host, "_caseFoundationSnapshot", None)),
            "opening_transform": bool(host.logic.isStep6CaseJawTransformNode(parameter.step6CaseJawTransform)),
            "reviewed_complete": bool(scope.get("reviewedComplete")),
            "articulator_provenance": bool(getattr(host, "_lastArticulatorProvenanceJson", "")),
        }

    return annotate_step6_controls("case foundation", entries, flags, _base_tips(host))
