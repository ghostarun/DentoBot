# Fast checkpoint (operator 2026-10-02): Find Reachable Base -> accept Base ->
# accept the live state as Task Home -> confirm task. No workspace generation
# (optional since 2026-10-02). Production controls only; simulation only.
steps = {}


def stop(reason):
    raise RuntimeError(reason)


widget._configureRobotSimulationShellSubstep(1)
widget._updateStep6PlanningUi()
_process_events(0.1)
# The saved case keeps the accepted Base locked; unlock through the production
# control (disposable scene, same as the runner's base_stage_and_cancel).
if bool(parameter_node.robotBaseMountLocked):
    if not widget.ui.unlockRobotBaseMountButton.enabled:
        stop("Base unlock control is not enabled.")
    _press(widget.ui.unlockRobotBaseMountButton, 'Unlock Base')
    _process_events(0.1)
    if bool(parameter_node.robotBaseMountLocked):
        stop("Base unlock did not complete.")
# Unlocking re-stages the accepted Base as an identity candidate; cancel only that.
pre = dict(facade.manualBaseReview().details or {})
if (pre.get("staged") is True and pre.get("identityStatus") == "current"
        and _same_matrix(pre.get("candidateMatrixWorldRasMm"), pre.get("acceptedMatrixWorldRasMm"))
        and panel.cancelManualBaseReviewButton.enabled):
    _press(panel.cancelManualBaseReviewButton, 'Cancel Base Review')
    _process_events(0.1)
steps["base_unlocked"] = not bool(parameter_node.robotBaseMountLocked)
if not panel.beginManualBaseReviewButton.enabled:
    stop("Review Current Base is disabled.")
_press(panel.beginManualBaseReviewButton, 'Review Current Base')
_process_events(0.1)
_press(panel.searchBasePlacementButton, 'Find Reachable Base')
_process_events(0.2)
search = dict(getattr(widget, "_lastBasePlacementSearch", None) or {})
staged = dict(facade.manualBaseReview().details or {})
steps["find_reachable_base"] = {
    "verdict": search.get("verdict"),
    "evaluated": search.get("evaluated"),
    "feasible_count": search.get("feasible_count"),
    "best": {k: (search.get("best") or {}).get(k)
             for k in ("u_mm", "v_mm", "depth_mm", "minimum_slider_margin_mm")},
}
if search.get("best") is None or staged.get("staged") is not True:
    stop("Find Reachable Base staged no candidate.")
_capture(report, evidence_dir, run_id, "session-base-staged")
_modal_guarded_click(report, evidence_dir, run_id, widget.ui.lockRobotBaseMountButton, "session-base-accept")
_process_events(0.3)
accepted = dict(facade.manualBaseReview().details or {})
steps["base_accept"] = {k: accepted.get(k) for k in ("acceptanceStatus", "identityStatus", "staged")}

home_evidence = {"phase": "session_checkpoint"}
_accept_current_state_as_task_home(
    widget, panel, logic, parameter_node, facade, report, evidence_dir, run_id,
    phase="session-checkpoint", evidence=home_evidence, stop=stop,
)
steps["task_home_revision"] = home_evidence.get("home_revision_after")

widget._configureRobotSimulationShellSubstep(3)
widget._updateStep6PlanningUi()
_show_step63_view(panel, 2, 0)
if not panel.confirmTaskButton.enabled:
    stop("Confirm Immutable Task is disabled.")
_press(panel.confirmTaskButton, 'Confirm Task')
_process_events(0.2)
issues = list(logic.confirmedTaskFreshnessIssues(parameter_node))
steps["task_confirmed"] = logic.confirmedTaskRecord(parameter_node) is not None and not issues
steps["task_issues"] = issues
widget._updateStep6PlanningUi()
steps["plan_approach_enabled"] = bool(panel.planApproachButton.enabled)
_capture(report, evidence_dir, run_id, "session-checkpoint-ready")
if not steps["task_confirmed"] or not steps["plan_approach_enabled"]:
    stop(f"Checkpoint not ready: {steps}")
result = steps
