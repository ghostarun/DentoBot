# Drop the current task/phase plan the same way the production planner comparison does.
fc = mod("step6_full_chain_probe")
facade.invalidateMotionPlan()
widget._updateStep6PlanningUi()
_process_events(0.2)
snapshot = fc._snapshot(facade, getattr(facade, "_bridge", None), JOINT_NAMES)
result = {
    "route_preview": snapshot["route_preview"],
    "phase_guard_session_active": bool(getattr(facade, "_phase_guard_session_id", "")),
}
