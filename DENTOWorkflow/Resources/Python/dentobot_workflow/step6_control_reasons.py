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

from collections.abc import Mapping

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

# control attribute name -> ordered (flag, text) prerequisites
CONTROL_PREREQUISITES: dict[str, tuple[tuple[str | None, str], ...]] = {
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
    widgets: Mapping[str, object], flags: Mapping[str, object], base_tips: dict[str, str]
) -> dict[str, str]:
    """Append each control's reason to its tooltip; return the reasons written.

    ``base_tips`` remembers the tooltip the widget sets itself, so a refresh that
    re-assigns the tooltip is not doubled. Only tooltips are written.
    """

    reasons: dict[str, str] = {}
    for name, widget in widgets.items():
        tip = str(getattr(widget, "toolTip", "") or "")
        if (PREFIX not in tip) or name not in base_tips:
            base_tips[name] = tip.partition("\n\n" + PREFIX)[0]
        reason = step6_control_reason(
            name, bool(getattr(widget, "enabled", True)), _own_visible(widget), flags
        )
        reasons[name] = reason
        base = base_tips[name]
        widget.toolTip = base + ("\n\n" + reason if reason else "")
    return reasons
