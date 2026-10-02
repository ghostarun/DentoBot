# PreEntry IK, then two button-driven Plan -> Approach -> Drill -> Return Home cycles.
cycle_probe = mod("step6_complete_cycle_probe")
widget._configureRobotSimulationShellSubstep(3)
widget._updateStep6PlanningUi()
_show_step63_view(panel, 2, 0)
if not panel.checkPreEntryIKButton.enabled:
    raise RuntimeError("Check PreEntry IK is disabled.")
_modal_guarded_click(report, evidence_dir, run_id, panel.checkPreEntryIKButton, "session-preentry-ik")
_wait_until(lambda: not bool(getattr(widget, "_workflowActionBusy", False)), 600.0)
_process_events(0.1)
try:
    evidence = cycle_probe.run_complete_cycles(
        widget, panel, facade,
        process_events=_process_events,
        capture_callback=lambda stage: _capture(report, evidence_dir, run_id, f"session-cycle-{stage}"),
        joint_names=JOINT_NAMES,
        cycles=2,
        click_guard=lambda button, name: _modal_guarded_click(
            report, evidence_dir, run_id, button, f"session-cycle-{name}"),
    )
    result = {"passed": _complete_cycles_passed(evidence), "evidence": evidence}
except Exception as exc:
    result = {"passed": False, "error": f"{type(exc).__name__}: {exc}",
              "evidence": getattr(exc, "evidence", None)}
