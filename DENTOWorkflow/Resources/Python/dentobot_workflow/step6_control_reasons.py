"""Named reasons for disabled or hidden Step 6 controls (pure, no Slicer/Qt).

Each registered control lists its prerequisites as ordered ``(flag, text)``
pairs over the booleans the Step 6 refresh already computes. The enable and
visibility expressions stay where they are; this table only explains them.
A disabled or hidden control shows the text of its first unmet prerequisite.
If none is unmet, the control gets a generic line that names it, so a gap is
visible and reportable instead of a silent grey button. A ``None`` flag marks a
control that is always disabled (retired or quarantined); its text is the reason.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping

PREFIX = "Unavailable: "
_GENERIC = "{name} has no matched prerequisite in the current Step 6 state; report this state."

_SCENE = ("scene_prepared", "Complete Case Foundation — Open Mouth Setup first.")
_ROBOT = ("robot_present", "Load the robot in 6.1.")
_LOCKED = ("base_locked", "Accept and lock the Base in 6.1 first.")
_ROS = ("ros2_active", "Connect ROS + MoveIt in 6.1.")
_NO_ROS = ("ros2_inactive", "Disconnect ROS + MoveIt in 6.1 first.")
_IMPORTED = ("imported", "Activate a verified PreparedBranch in 6.0 first.")
_ANATOMY = ("planning_anatomy_ready", "Planning anatomy is not ready: complete Case Foundation — Open Mouth Setup.")
_HOME = ("home_runtime_validated", "Apply and live-validate Task Home in 6.2 first.")
_UNLOCKED = ("base_unlocked", "The Base is locked; unlock it in 6.1 to move the robot.")
_STAGE_IDLE = ("base_stage_idle", "The 6.1 Base review is active; accept or cancel it first.")
_BASE_STAGE = ("base_stage_active", "Open the 6.1 Base stage to use the numeric Base review.")
_ACTION_IDLE = ("action_idle", "Another Step 6 action is still running; wait for it to finish.")
_NO_PREVIEW = ("no_preview_active", "A simulated motion preview is active; stop it first.")
_AT_HOME = ("not_away_from_home", "The robot is away from Home; return Home first.")
_TASK = ("task_ready", "The 6.3 task snapshot is not current; see the confirmation status above.")
_RETIRED_PREVIEW = (None, "Retired control, always disabled; run simulated previews from the 6.3 Preview buttons.")
_RETIRED_CONNECT = (None, "Retired control, always disabled; use the Connect ROS + MoveIt button in the Step 6 panel.")
_RETIRED_DISCONNECT = (None, "Retired control, always disabled; use the Disconnect button in the Step 6 panel.")
_RETIRED_PLANE = (None, "Legacy plane is quarantined: it was derived from the robot base, not independent patient evidence.")

_NUDGE_BUTTONS = (
    "robotXMinusButton", "robotXPlusButton", "robotYMinusButton", "robotYPlusButton",
    "robotZMinusButton", "robotZPlusButton", "robotRxMinusButton", "robotRxPlusButton",
    "robotRyMinusButton", "robotRyPlusButton", "robotRzMinusButton", "robotRzPlusButton",
)

# Refresh-owned controls (widget_robot*.py _updateStep6PlanningUi): widget attribute -> (flag, text) prerequisites
REFRESH_CONTROLS: dict[str, tuple[tuple[str | None, str], ...]] = {
    # 6.1 groups and Base buttons (widget_robot.py refresh)
    "step6MountLockGroupBox": (_SCENE,),
    "step6TaskJointLimitsGroupBox": (_SCENE, _ROBOT, _ROS),
    "step6WorkspaceGroupBox": (_SCENE, _ROBOT, _ROS, _HOME),
    "step6TrajectoryPlanningGroupBox": (_LOCKED, _IMPORTED, _ANATOMY),
    "lockRobotBaseMountButton": (
        _SCENE, _ROBOT,
        ("base_unlocked", "The Base is already locked; unlock it in 6.1 to change it."),
        ("base_accept_ready", "Accept Base needs a staged, identity-current numeric Base review with a known lock outcome."),
        _ACTION_IDLE,
    ),
    "unlockRobotBaseMountButton": (("base_locked", "The Base is not locked, so there is nothing to unlock."),),
    "planTrajectoryMotionButton": (_LOCKED, _IMPORTED, _ANATOMY),
    "previewTrajectoryMotionButton": (_RETIRED_PREVIEW,),
    "stopTrajectoryMotionButton": (("motion_preview_active", "No simulated motion preview is running."),),
    "connectRos2MotionButton": (_RETIRED_CONNECT,),
    "disconnectRos2MotionButton": (_RETIRED_DISCONNECT,),
    "loadRobotModelButton": (
        _SCENE,
        ("base_unlocked_or_recovery", "The Base is locked; the robot model can be reloaded only to recover a missing model."),
    ),
    "frameRobotButton": (_SCENE,),
    "importStep6PlanningContextButton": (
        ("branch_eligible", "Complete Steps 4A–5C before activating a PreparedBranch."),
        _NO_ROS,
    ),
    "resetRobotBaseButton": (_SCENE, _ROBOT, _UNLOCKED),
    "createRobotMountPlaneButton": (_RETIRED_PLANE,),
    "flipRobotMountPlaneButton": (_RETIRED_PLANE,),
    "snapRobotBaseToPlaneButton": (_RETIRED_PLANE,),
    "robotMountPlaneSelector": (
        (None, "Legacy mount-plane selector is retired; place the Base with the 6.1 Base controls."),
    ),
    "robotBaseTransformSelector": (_STAGE_IDLE,),
    **{name: (_SCENE, _ROBOT, _UNLOCKED) for name in _NUDGE_BUTTONS},
    "robotKeyboardNudgeCheckBox": (_SCENE, _ROBOT, _UNLOCKED),
    "resetRobotJointsButton": (
        _ROBOT, _SCENE, _ROS, _STAGE_IDLE,
    ),
    "deleteRobotSetupButton": (
        _ROBOT,
        ("base_unlocked", "Unlock the Base in 6.1 before deleting the robot setup."),
    ),
    "applyTaskJointLimitsButton": (_ROBOT, _SCENE, _ROS),
    "resetTaskJointLimitsButton": (_ROBOT, _SCENE, _ROS),
    "generateRobotWorkspaceButton": (
        _SCENE, _ROBOT, _LOCKED, _ROS, _HOME,
        ("base_transform_node", "The robot base transform node is missing; reload the robot in 6.1."),
    ),
    "clearRobotWorkspaceButton": (("workspace_model_present", "There is no robot workspace model to clear."),),
    # 6.1 panel controls driven by the same refresh
    "beginManualBaseReviewButton": (
        _BASE_STAGE, _SCENE, _ROBOT, ("base_unlocked", "The Base is already locked."),
        ("base_begin_ready", "A staged or unverified Base review must be resolved before starting another."),
    ),
    "cancelManualBaseReviewButton": (
        _BASE_STAGE,
        ("base_candidate_cancellable", "No staged Base candidate can be cancelled, or its acceptance outcome is unknown."),
    ),
    "reconcileManualBaseStateButton": (
        _BASE_STAGE,
        ("base_reconcile_available", "Reconcile needs an unknown Base acceptance outcome, a current staged identity and live ROS."),
        _ACTION_IDLE,
    ),
    "manualBaseReviewGroup": (
        _BASE_STAGE,
        ("base_review_group", "Prepare the case scene and load the robot in 6.1 to open the numeric Base review."),
    ),
    "loadFallbackButton": (
        _SCENE,
        ("base_unlocked_or_recovery", "The Base is locked; the robot model can be reloaded only to recover a missing model."),
    ),
    "enableCbctRenderingButton": (_IMPORTED, _SCENE),
    "createProxyButton": (_SCENE, _NO_ROS),
    "motionDiagnosticsButton": (("motion_diagnostic_recorded", "No motion diagnostic is recorded for this case yet."),),
    "showPlannerComparisonButton": (("planner_comparison_recorded", "No planner comparison is recorded for this case yet."),),
    "reviewLimitsButton": (
        _SCENE, _ROS, _HOME,
        ("workspace_validated", "Validate the workspace at runtime first."),
        ("limit_proposal_present", "No assisted limit proposal is saved for this case."),
        ("limit_review_pending", "The assisted limit envelope is already reviewed."),
    ),
    "revalidateWorkspaceButton": (
        _SCENE, _ROS, _HOME,
        ("limit_proposal_present", "No assisted limit proposal is saved for this case."),
        ("workspace_validation_pending", "The workspace is already runtime-validated."),
    ),
    "connectButton": (
        ("runtime_ready", "Activate the PreparedBranch, lock the Base and prepare anatomy before connecting."),
        _NO_ROS,
    ),
    "disconnectButton": (_ROS,),
    # 6.2 Task Home cancel/reconcile (review, accept and apply use task_home_gate)
    "cancelTaskHomeReviewButton": (
        ("task_home_cancellable", "No staged Home candidate can be cancelled."),
        _ACTION_IDLE,
    ),
    "reconcileTaskHomeButton": (
        ("task_home_reconcile_available", "Reconcile needs an unresolved Home save outcome and a live ROS session."),
        _ACTION_IDLE,
    ),
    # 6.3 planning, drilling and anatomy review
    "diagnoseBaseButton": (("pre_entry_ik_ready", "Check Pre-Entry IK is unavailable; see its tooltip."),),
    "templateCollisionOverrideCheckBox": (
        _ANATOMY, _TASK, _ROS, _NO_PREVIEW, _AT_HOME,
        ("template_model_present", "No finalized printable template model."),
        ("historical_template_override_enabled", "The historical template override is disabled by configuration."),
    ),
    "anatomyReviewGroup": (
        _NO_PREVIEW, _AT_HOME,
        ("anatomy_review_available", "Anatomy review needs a saved review or ready planning anatomy with ROS active."),
    ),
    "previewApproachButton": (
        ("drilling_preflight_ready", "Approach planning must return a complete guarded Stage 3 preflight first."),
        ("approach_plan_ready", "Plan the Approach phase first."),
        _TASK, _ROS, _NO_PREVIEW, _AT_HOME,
    ),
    "stopPreviewButton": (("motion_preview_active", "No simulated motion preview is running."),),
    "returnHomeButton": (
        _ROS,
        ("away_from_home", "The robot is already at Home."),
        _NO_PREVIEW,
    ),
    "planDrillingButton": (
        _ANATOMY, _TASK, _ROS,
        ("approach_complete", "Complete the Approach motion before planning Drill."),
        ("drilling_preflight_ready", "Drill planning needs a complete guarded Stage 3 preflight."),
        _NO_PREVIEW,
    ),
    "previewDrillingButton": (
        ("drilling_preflight_ready", "Drill preview needs a complete guarded Stage 3 preflight."),
        ("approach_complete", "Complete the Approach motion before previewing Drill."),
        ("drill_plan_ready", "Plan the Drill phase first."),
        _TASK, _ROS, _NO_PREVIEW,
    ),
}

# Panel-owned controls (DENTORobotSimulationPanel.py), annotated by the refresh pass.
_TCP_ALLOWED = (
    ("substep_6_3", "TCP controls are available in the 6.3 workbench only."),
    ("connected_runtime", "TCP controls need a connected ROS + MoveIt runtime."),
    ("goal_group_visible", "The 6.3 goal section is hidden in this view."),
    ("tcp_drag_on", "Enable TCP drag first."),
    ("tcp_drag_checked", "Tick TCP drag to use Cartesian controls."),
)
_MANUAL_KEYBOARD = (
    ("substep_6_3", "Keyboard jog is available in the 6.3 workbench only."),
    ("manual_jog_group_visible", "The manual jog section is hidden in this view."),
    ("manual_jog_available", "Manual jog needs a valid draft, limits and a connected or offline setup."),
    ("not_busy", "Another Step 6 action is still running; wait for it to finish."),
    ("no_reconciliation", "A guarded jog outcome is unresolved; use Reconcile first."),
)
_NOT_BUSY = ("not_busy", "Another Step 6 action is still running; wait for it to finish.")
_MANUAL_AVAILABLE = ("manual_jog_available", "Manual jog needs a valid draft, limits and a connected or offline setup.")
_HISTORICAL_ANATOMY = ("historical_override", "The historical anatomy-review override is disabled by configuration.")
_REVIEW_EDITABLE = (
    _HISTORICAL_ANATOMY,
    ("review_exists", "No anatomy review exists yet; create one first."),
    ("review_not_active", "The anatomy review is already active."),
)
_GROUP_VIEW = (None, "This section belongs to another Step 6 view; open it from the view selector.")
_RETIRED_SHELL_GROUP = (None, "Retired ROS + MoveIt group; connect from the 6.1 Connect button.")
PANEL_CONTROLS: dict[str, tuple[tuple[str | None, str], ...]] = {
    "manualJogSlider": (_MANUAL_AVAILABLE, _NOT_BUSY),
    "manualJogValue": (_MANUAL_AVAILABLE, _NOT_BUSY),
    "resetManualJogDraftButton": (
        _MANUAL_AVAILABLE,
        ("reset_available", "Reset needs an accepted or saved Home state to return to."),
        _NOT_BUSY,
    ),
    "guardedManualJogButton": (
        ("guard_available", "Guarded jog needs a connected runtime with valid limits and the guard context."),
        _NOT_BUSY,
        ("no_reconciliation", "A guarded jog outcome is unresolved; use Reconcile first."),
    ),
    "checkManualDraftStateButton": (
        ("connected_runtime", "Check Draft State needs a connected ROS + MoveIt runtime."), _MANUAL_AVAILABLE, _NOT_BUSY,
    ),
    "reconcileManualJogButton": (
        ("connected_runtime", "Reconcile needs a connected ROS + MoveIt runtime."),
        _MANUAL_AVAILABLE,
        ("reconciliation_required", "No guarded jog outcome is unresolved."),
        _NOT_BUSY,
    ),
    "manualJogKeyboardEnabledCheckBox": _MANUAL_KEYBOARD,
    "manualJogKeyboardStepComboBox": _MANUAL_KEYBOARD,
    "manualJogShortcut": _MANUAL_KEYBOARD + (
        ("manual_keyboard_on", "Tick Keyboard jog to enable its shortcuts."),
        ("no_text_focus", "A text field has keyboard focus; click the viewer first."),
    ),
    "tcpDragEnabledCheckBox": (
        ("substep_6_3", "TCP drag is available in the 6.3 workbench only."),
        ("connected_runtime", "TCP drag needs a connected ROS + MoveIt runtime."),
    ),
    "tcpKeyboardEnabledCheckBox": _TCP_ALLOWED,
    "solveIkButton": (("tcp_ik_available", "IK is unavailable in this runtime."),) + _TCP_ALLOWED,
    "tcpTranslationStepMm": _TCP_ALLOWED,
    "tcpRotationStepDeg": _TCP_ALLOWED,
    "tcpNudgeButton": _TCP_ALLOWED,
    "tcpShortcut": _TCP_ALLOWED + (("tcp_keyboard_on", "Tick Keyboard TCP to enable its shortcuts."),),
    "autoTaskHomeButton": (
        ("substep_6_2", "Auto Task Home is available in the 6.2 Task Home view only."),
        ("connected_runtime", "Auto Task Home needs a connected ROS + MoveIt runtime."),
        ("tcp_ik_available", "Auto Task Home needs IK availability."),
    ),
    "planGoalButton": (
        (None, "Disabled for Step 6.3 manual exploration: a manual TCP path has no planned goal; use the planner buttons."),
    ),
    "clearManualRecordButton": (("records_loaded", "No historical simulation record is loaded."),),
    "manualSimulationRecordComboBox": (("records_loaded", "No historical simulation record is loaded."),),
    "previousManualSimulationEventButton": (
        ("records_loaded", "No historical simulation record is loaded."),
        ("event_before", "This is the first event in the record."),
    ),
    "nextManualSimulationEventButton": (
        ("records_loaded", "No historical simulation record is loaded."),
        ("event_after", "This is the last event in the record."),
    ),
    "syncCollisionButton": (("collision_check_available", "Collision checking is unavailable in the connected runtime."),),
    "checkStateButton": (("runtime_connected", "Check State needs a connected ROS + MoveIt runtime."),),
    "cancelPlannerComparisonButton": (("comparison_running", "No planner comparison is running."),),
    # Group and navigation visibility (the view or substep decides; no gate expression to restate).
    "visualizationGroup": (_GROUP_VIEW,),
    "homeGroup": (_GROUP_VIEW,),
    "workspaceReviewGroup": (_GROUP_VIEW,),
    "runtimeGroup": (_GROUP_VIEW,),
    "confirmationGroup": (_GROUP_VIEW,),
    "goalGroup": (_GROUP_VIEW,),
    "manualJogGroup": (_GROUP_VIEW,),
    "collisionGroup": (_GROUP_VIEW,),
    "approachGroup": (_GROUP_VIEW,),
    "drillingGroup": (_GROUP_VIEW,),
    "previewControlGroup": (_GROUP_VIEW,),
    "workbenchGroup": (_GROUP_VIEW,),
    "manualHistoryGroup": (_GROUP_VIEW,),
    "step6PlanningContextGroupBox": (_GROUP_VIEW,),
    "ros2MotionControlGroupBox": (_RETIRED_SHELL_GROUP,),
    "returnFromBaseButton": (
        (None, "Return to Workbench appears only after opening the 6.1 Base from the 6.3 workbench."),
    ),
    "returnFromHomeButton": (
        (None, "Return to Workbench appears only after opening Task Home from the 6.3 workbench."),
    ),
    "_step6PreviousSubstepButton": (("previous_substep_available", "This is the first Step 6 substep."),),
    "_step6NextSubstepButton": (("next_substep_available", "This is the last Step 6 substep."),),
}

# Case Foundation controls (widget_robot_scene.py _updateStep6CaseJawOpeningControls), annotated there.
SCENE_CONTROLS: dict[str, tuple[tuple[str | None, str], ...]] = {
    "step6RegistrySelectionGroupBox": (("ros_inactive", "Registry selection is locked while ROS + MoveIt is connected."),),
    "step6CaseJawOpeningGroupBox": (
        ("source_ready", "Case Foundation needs a reviewed teeth segmentation."),
    ),
    "createStep6CaseJawLandmarksButton": (
        ("source_ready", "Case Foundation needs a reviewed teeth segmentation."),
        ("ros_inactive", "Disconnect ROS + MoveIt to change the Case Foundation landmarks."),
        ("landmarks_actionable", "All landmarks are placed and current; clear them to place them again."),
    ),
    "clearStep6CaseJawLandmarksButton": (
        ("source_ready", "Case Foundation needs a reviewed teeth segmentation."),
        ("ros_inactive", "Disconnect ROS + MoveIt to change the Case Foundation landmarks."),
        ("landmarks_present", "There are no landmark points to clear."),
    ),
    "applyStep6CaseJawOpeningButton": (
        ("source_ready", "Case Foundation needs a reviewed teeth segmentation."),
        ("ros_inactive", "Disconnect ROS + MoveIt to open the mouth from Case Foundation."),
    ),
    "caseFoundationGoToStep4Button": (
        ("pose_eligible", "The Case Foundation pose is not eligible yet; complete the landmarks and opening."),
        ("ros_inactive", "Disconnect ROS + MoveIt before leaving Case Foundation."),
    ),
    "resetStep6CaseJawOpeningButton": (
        ("ros_inactive", "Disconnect ROS + MoveIt to reset the opening preview."),
        ("preview_uncommitted", "There is no uncommitted opening preview to reset."),
    ),
    "clearCaseFoundationButton": (
        ("ros_inactive", "Disconnect ROS + MoveIt to clear Case Foundation."),
        ("foundation_content_present", "There is no Case Foundation content to clear."),
    ),
    "forgetSessionFoundationButton": (("session_snapshot", "There is no session Case Foundation snapshot to forget."),),
    "caseFoundationGapSlider": (
        ("source_ready", "Case Foundation needs a reviewed teeth segmentation."),
        ("opening_transform", "The opening transform is missing; reopen the Case Foundation opening."),
        ("ros_inactive", "Disconnect ROS + MoveIt to change the opening gap."),
    ),
    "step6ForceManualCondylarAxisCheckBox": (
        ("reviewed_complete", "Complete and review the landmarks before forcing a manual condylar axis."),
        ("ros_inactive", "Disconnect ROS + MoveIt to change the condylar axis."),
    ),
    "probeCaseFoundationArticulatorButton": (
        ("source_ready", "Case Foundation needs a reviewed teeth segmentation."),
        ("ros_inactive", "Disconnect ROS + MoveIt to probe the articulator."),
    ),
    "copyCaseFoundationArticulatorJsonButton": (
        ("articulator_provenance", "No articulator probe has been recorded yet."),
    ),
}

# Advisor-owned controls (widget_step6_advisor.py): "advisor.<state key>" -> prerequisites
_ADVISOR_NOT_UNAVAILABLE = ("not_unavailable", "This advisor run applied its configuration or its restore did not confirm.")
_ADVISOR_NOT_BUSY = ("not_busy", "Another Step 6 action is still running; wait for it to finish.")
ADVISOR_CONTROLS: dict[str, tuple[tuple[str | None, str], ...]] = {
    "advisor.startButton": (
        ("idle", "A search is already running, paused or finished; close this run to start another."),
        _ADVISOR_NOT_UNAVAILABLE, _ADVISOR_NOT_BUSY,
    ),
    "advisor.cancelButton": (
        ("cancellable", "Cancel is available only while a search is running or paused."),
        ("cancel_not_requested", "Cancellation is already requested; baseline restoration is running."),
    ),
    "advisor.consentBox": (
        ("consent_window", "Consent is asked before a search starts or before Keep searching."),
        _ADVISOR_NOT_UNAVAILABLE, _ADVISOR_NOT_BUSY,
    ),
    "advisor.pauseConnectButton": (
        ("paused", "Connect ROS + MoveIt (6.1) appears only when the search is paused for a live connection."),
    ),
    "advisor.continueButton": (("paused", "Continue appears only when the search is paused."),),
    "advisor.moreButton": (
        ("done", "Keep searching is available after a finished search."),
        ("found", "The finished search found no candidate to continue from."),
        _ADVISOR_NOT_UNAVAILABLE,
    ),
    "advisor.applyButton": (
        ("done", "Apply & Save needs a finished search."),
        _ADVISOR_NOT_UNAVAILABLE,
        ("best_candidate", "Apply & Save needs a passing candidate from the finished search."),
    ),
    "advisor.exportButton": (
        ("not_running", "Export is unavailable while a search runs."),
        _ADVISOR_NOT_BUSY,
        ("has_baseline", "Export needs an advisor session with its recorded baseline."),
    ),
    "advisor.closeButton": (
        ("not_active", "Close is unavailable while a search runs or is paused; cancel it first."),
    ),
    "advisor.fixButton": (
        ("fix_idle", "Setup fixes wait until the running or paused search ends."),
        _ADVISOR_NOT_BUSY,
    ),
}
# Anatomy-review controls (DENTORobotSimulationPanel.setAnatomyReviewCandidates), annotated there.
ANATOMY_CONTROLS: dict[str, tuple[tuple[str | None, str], ...]] = {
    "createAnatomyReviewButton": (_HISTORICAL_ANATOMY,),
    "editAnatomyReviewButton": _REVIEW_EDITABLE,
    "anatomyReviewConfirmedCheckBox": _REVIEW_EDITABLE,
    "applyAnatomyReviewButton": _REVIEW_EDITABLE,
    "discardAnatomyReviewButton": (("review_exists", "No anatomy review exists to discard."),),
}
# Robot nudge keyboard shortcuts (widget_robot_placement.py), annotated there.
PLACEMENT_CONTROLS: dict[str, tuple[tuple[str | None, str], ...]] = {
    "robotNudgeShortcut": (
        ("placement_context", "Keyboard nudging works during the 6.1 Base review or Step 3B placement."),
        ("base_unlocked", "The Base is locked; unlock it to nudge with the keyboard."),
        ("keyboard_nudge_on", "Tick Keyboard nudge to use the shortcuts."),
        ("robot_transform_node", "The robot base transform node is missing; reload the robot in 6.1."),
    ),
}

# Motion-diagnostics and planner-comparison dialog buttons (closures in DENTORobotSimulationPanel.py).
DIALOG_CONTROLS: dict[str, tuple[tuple[str | None, str], ...]] = {
    "motionReviewButton": (("review_pending", "This diagnostic evidence is already reviewed."),),
    "motionPathButton": (("path_available", "No candidate path is available for this attempt."),),
    "motionPreviewButton": (("preview_available", "No diagnostic preview is available for this attempt."),),
    "motionApplyButton": (
        ("has_apply", "Applying a route is not available for this diagnostic."),
        ("preentry_ok", "Pre-Entry IK failed for this candidate, so it cannot be applied."),
        ("plan_complete", "Only a complete full-chain candidate can be applied."),
        ("plan_unlocked", "The route is locked; unlock it before applying another."),
    ),
    "motionLockButton": (
        ("has_apply", "Locking a route is not available for this diagnostic."),
        ("preentry_ok", "Pre-Entry IK failed for this candidate, so it cannot be locked."),
        ("plan_complete", "Only a complete full-chain candidate can be locked."),
        ("plan_unlocked", "The route is already locked."),
    ),
    "motionUnlockButton": (
        ("has_unlock", "Unlocking is not available for this diagnostic."),
        ("preentry_ok", "Pre-Entry IK failed for this candidate."),
        ("plan_locked", "Only a locked route can be unlocked."),
    ),
    "plannerReplayButton": (
        ("comparison_current", "This comparison is from an earlier plan; rerun the planner comparison."),
        ("attempt_has_paths", "This planner attempt has no path to replay."),
    ),
    "plannerChooseButton": (("attempt_run", "This planner attempt was not run, so it cannot be chosen."),),
}
CONTROL_PREREQUISITES: dict[str, tuple[tuple[str | None, str], ...]] = {
    **REFRESH_CONTROLS, **PANEL_CONTROLS, **ANATOMY_CONTROLS, **ADVISOR_CONTROLS, **SCENE_CONTROLS,
    **DIALOG_CONTROLS, **PLACEMENT_CONTROLS,
}

# Controls whose reasons come from a dedicated explainer (named in the test).
EXPLAINED_ELSEWHERE: dict[str, str] = {
    "reviewTaskHomeButton": "setTaskHomeActionBlockers",
    "acceptTaskHomeButton": "setTaskHomeActionBlockers",
    "applyTaskHomeButton": "setTaskHomeActionBlockers",
    "confirmTaskButton": "_explainDisabledPlannerButtons",
    "planApproachButton": "_explainDisabledPlannerButtons",
    "checkPreEntryIKButton": "_explainDisabledPlannerButtons",
    "checkPlanningP1Button": "_explainDisabledPlannerButtons",
    "checkPlanningP2Button": "_explainDisabledPlannerButtons",
    "checkPlanningP3Button": "_explainDisabledPlannerButtons",
    "comparePlannersButton": "_explainDisabledPlannerButtons",
}


def _met(flags: Mapping[str, object], flag: str | None) -> bool:
    return flag is not None and bool(flags.get(flag))


def control_enabled(name: str, flags: Mapping[str, object]) -> bool:
    """True when every prerequisite of ``name`` is met (the table's own expectation)."""

    return all(_met(flags, flag) for flag, _text in CONTROL_PREREQUISITES.get(name, ((None, ""),)))


def generic_reason(name: str) -> str:
    return PREFIX + _GENERIC.format(name=name)


def step6_control_reason(name: str, enabled: bool, visible: bool, flags: Mapping[str, object]) -> str:
    """Reason text for a control's current state; empty when it is enabled and visible."""

    if enabled and visible:
        return ""
    for flag, text in CONTROL_PREREQUISITES.get(name, ()):
        if not _met(flags, flag):
            return PREFIX + text
    return generic_reason(name)


def unexplained_step6_controls(
    states: Mapping[str, tuple[bool, bool]], flags: Mapping[str, object]
) -> tuple[str, ...]:
    """Names disabled or hidden whose only available reason is the generic line."""

    unexplained = []
    for name, (enabled, visible) in states.items():
        if enabled and visible:
            continue
        reason = step6_control_reason(name, enabled, visible, flags)
        if reason in ("", PREFIX) or reason == generic_reason(name):
            unexplained.append(name)
    return tuple(unexplained)


def _own_visible(widget: object) -> bool:
    is_hidden = getattr(widget, "isHidden", None)
    if callable(is_hidden):
        return not is_hidden()  # the widget's own flag, not ancestors'
    return bool(getattr(widget, "visible", True))


def apply_step6_control_tooltips(
    entries: Mapping[str, object] | Iterable[tuple[str, object]],
    flags: Mapping[str, object],
    base_tips: dict[int, str],
) -> dict[str, str]:
    """Append each control's reason to its tooltip; return the reasons written.

    ``entries`` maps a registry name to a widget, or yields ``(name, widget)``
    pairs when one name covers several widgets. ``base_tips`` remembers each
    widget's own tooltip (keyed by ``id``), so a refresh that re-assigns the
    tooltip is not doubled. Only tooltips are written.
    """

    items = entries.items() if isinstance(entries, Mapping) else entries
    reasons: dict[str, str] = {}
    for name, widget in items:
        key = id(widget)
        tip = str(getattr(widget, "toolTip", "") or "")
        if PREFIX not in tip or key not in base_tips:
            base_tips[key] = tip.partition("\n\n" + PREFIX)[0]
        reason = step6_control_reason(
            name, bool(getattr(widget, "enabled", True)), _own_visible(widget), flags
        )
        reasons[name] = reason
        base = base_tips[key]
        widget.toolTip = (base + "\n\n" + reason) if (base and reason) else (base or reason)
    return reasons


def annotate_step6_controls(label, entries, flags, base_tips: dict[int, str]) -> dict[str, str]:
    """Run one owner's annotation; a failure is logged and swallowed.

    ``entries()`` and ``flags()`` are called inside the guard, so a missing
    attribute or a bad branch dict cannot break the Step 6 refresh.
    """

    try:
        return apply_step6_control_tooltips(entries(), flags(), base_tips)
    except Exception:  # an annotation must never break the Step 6 refresh
        logging.exception("Step 6 control reasons skipped for %s", label)
        return {}
