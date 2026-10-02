# Experiment (operator 2026-10-03 speed question): one Plan Guarded Approach
# with 3D rendering held paused only inside validate_task_phase_waypoints
# (validate-only guard loops; the displayed robot does not move there). The
# guard handshake keeps its normal timing (r19 016: a whole-plan pause exposed
# the sequence-0 handshake retry race). Session-only wrapper, restored after.
import time as _time

fc = mod("step6_full_chain_probe")
bridge_module = mod("DENTOROS2Bridge")
if facade.motionPlan is not None:
    facade.invalidateMotionPlan()
fc._enter_substep(widget, panel, fc.STEP6_PLANNING_SUBSTEP, _process_events)
widget._updateStep6PlanningUi()
if not panel.planApproachButton.enabled:
    raise RuntimeError("Plan Guarded Approach is disabled.")
bridge_module.task_command_wait_stats(reset=True)
original_validate = bridge_module.validate_task_phase_waypoints


def _validate_render_paused(*args, **kwargs):
    slicer.app.pauseRender()
    try:
        return original_validate(*args, **kwargs)
    finally:
        slicer.app.resumeRender()


started = _time.monotonic()
bridge_module.validate_task_phase_waypoints = _validate_render_paused
try:
    _modal_guarded_click(report, evidence_dir, run_id, panel.planApproachButton, "session-plan-validate-paused")
    _wait_until(lambda: not bool(getattr(widget, "_workflowActionBusy", False)), 3600.0)
finally:
    bridge_module.validate_task_phase_waypoints = original_validate
elapsed = _time.monotonic() - started
_process_events(0.2)
_capture(report, evidence_dir, run_id, "session-plan-validate-paused-ready")
stats = bridge_module.task_command_wait_stats()
truncation = getattr(facade, "drillingTruncation", None) or {}
session = __import__("json").loads(str(parameter_node.step6MotionDiagnosticJson or "{}"))
result = {
    "elapsed_sec": round(elapsed, 2),
    "plan_present": facade.motionPlan is not None,
    "status_state": panel.approachStatusLabel.property("dentobotState"),
    "status_text": str(panel.approachStatusLabel.text)[:300],
    "completed_depth_mm": truncation.get("completed_depth_mm"),
    "selected": (session.get("full_task_outcome") or {}).get("selected_candidate_index"),
    "candidate_evaluation": getattr(facade, "_candidate_evaluation", None),
    "guard_wait_stats": stats,
    "mean_wait_ms": round(1000 * stats["wait_sec"] / max(stats["calls"], 1), 2),
}
