# Plan Guarded Approach once (no preview) and report the selected candidate.
fc = mod("step6_full_chain_probe")
fc._enter_substep(widget, panel, fc.STEP6_PLANNING_SUBSTEP, _process_events)
widget._updateStep6PlanningUi()
if not panel.planApproachButton.enabled:
    raise RuntimeError("Plan Guarded Approach is disabled.")
_modal_guarded_click(report, evidence_dir, run_id, panel.planApproachButton, "session-plan-only")
_wait_until(lambda: not bool(getattr(widget, "_workflowActionBusy", False)), 3600.0)
_process_events(0.2)
_capture(report, evidence_dir, run_id, "session-plan-only-ready")
truncation = getattr(facade, "drillingTruncation", None) or {}
result = {
    "status_text": str(panel.approachStatusLabel.text)[:600],
    "status_state": panel.approachStatusLabel.property("dentobotState"),
    "plan_present": facade.motionPlan is not None,
    "completed_depth_mm": truncation.get("completed_depth_mm"),
    "requested_depth_mm": truncation.get("requested_depth_mm"),
    "candidate_evaluation": getattr(facade, "_candidate_evaluation", None),
}
