# S6-ADVISOR-GUI-01 bounded B verification, RUN A: the real dialog, consent OFF, baseline only (expected PASS -> FOUND ->
# restore). Production controls only. Forbidden owners are made to fail and are counted (expected 0 refusals).
# The dialog is LEFT OPEN in its "done" state: the operator's visual verdict is a stop before Run B continues from it.
# Evidence: screenshots (dialog/running/done), per-step timeline, invariants before/after, advisor evidence root.
import json
import step6_advisor_probe as probe

stamp = run_id + "-advisor-A"
before = probe.invariant_snapshot(logic, facade, parameter_node, label="before-run-A")
steps = {}
widget._configureRobotSimulationShellSubstep(3)
widget._updateStep6PlanningUi()
_process_events(0.3)
guard_facade = probe.OwnerGuard(
    facade,
    refuse=("connect", "disconnect", "stageManualBaseReview", "acceptManualBaseReview", "unlockBase",
            "stageManualTaskHomeReview", "acceptManualTaskHomeReview"),
    count=("confirmTask", "setJointPlanningPolicy", "ensureMoveItSceneMatches", "syncPlanningScene", "checkPreEntryIK",
           "checkPlanningStage"),
)
guard_logic = probe.OwnerGuard(
    logic, refuse=("createOrUpdateStep6CaseJawOpening", "importStep6PlanningContext", "setStep6MouthBarrierTuning"))
timeline = probe.Timeline(evidence_dir.parent / "session" / "advisor-A-timeline.jsonl")
modals = []


def unexpected_gate():
    """A sensitive-stage review gate is NOT part of this run: capture it, then dismiss it only through the dialog's own
    safe default ("Skip this stage"). The run is marked FAILED at the end (retained outcome, never hidden)."""

    modal = qt.QApplication.activeModalWidget()
    if modal is not None and str(modal.objectName) == "DENTOBOTStep6AdvisorGateMessageBox":
        modals.append({"utc": _utc_now(), "title": str(modal.windowTitle), "text": str(modal.text)[:300]})
        try:
            _capture(report, evidence_dir, run_id, f"advisor-UNEXPECTED-GATE-{len(modals)}")
        finally:
            for button in modal.findChildren(qt.QPushButton):
                if str(button.objectName) == "DENTOBOTStep6AdvisorGateSkipButton":
                    button.click()


gate_timer = qt.QTimer()
gate_timer.setInterval(300)
gate_timer.connect("timeout()", unexpected_gate)
undo = None
try:
    assert panel.findWorkingConfigButton.enabled, "the Find Working Configuration button is disabled"
    panel.findWorkingConfigButton.click()
    _process_events(0.5)
    state = widget._advisorState
    session = state["session"]
    assert state["consentBox"].checked is False, "consent must be OFF by default"
    undo = probe.instrument_session(session, widget, timeline)
    _capture(report, evidence_dir, run_id, "advisor-A-dialog-open")
    gate_timer.start()
    state["startButton"].click()
    t0 = time.monotonic()
    shots = {"running": False, "diagnose": False}
    while not session.finished and time.monotonic() - t0 < 1500.0:
        _process_events(0.25)
        step = str(session.progress().get("step") or "")
        if not shots["running"] and session.phase in ("evaluating", "searching"):
            shots["running"] = True
            _capture(report, evidence_dir, run_id, "advisor-A-running")
        if not shots["diagnose"] and step.startswith("diagnose"):
            shots["diagnose"] = True
            _capture(report, evidence_dir, run_id, "advisor-A-diagnose-rows")
    assert session.finished, "the advisor did not finish within the 25 minute bound"
    _process_events(0.5)
    _capture(report, evidence_dir, run_id, "advisor-A-done")
    steps["outcome"] = session.outcome
    steps["message"] = session.message
    steps["restore_issues"] = list(session.restore_issues)
    steps["records"] = [{k: r.get(k) for k in ("sequence", "stage", "result", "failed_step", "reason", "timings_sec")}
                        for r in session.records]
    steps["longest_step"] = session.longest_step()
    steps["home_ledger"] = session.home_ledger
    steps["evidence_root"] = str(session.root)
    steps["export"] = session.export_evidence()
    steps["unexpected_gates"] = modals
except BaseException as failure:
    try:  # the first causal failure gets its own state-matched screenshot (the runner's fail() does not capture)
        _capture(report, evidence_dir, run_id, "advisor-A-FAILURE")
    except Exception as capture_error:
        steps["failure_capture_error"] = str(capture_error)[:200]
    steps["first_failure"] = f"{type(failure).__name__}: {failure}"[:400]
    raise
finally:
    gate_timer.stop()
    if undo is not None:
        undo()
    timeline.close()
    guard_facade.restore()
    guard_logic.restore()
after = probe.invariant_snapshot(logic, facade, parameter_node, label="after-run-A")
diff = probe.snapshot_diff(before, after, allow=probe.EXPECTED_AUTHORITY_DRIFT)
(evidence_dir / f"{stamp}-snapshots.json").write_text(json.dumps({"before": before, "after": after, "diff": diff}, indent=2), encoding="utf-8")
result = {"steps": steps, "guards": {"facade": guard_facade.report(), "logic": guard_logic.report()},
          "invariant_diff": diff, "joint_issues_after": probe.joints_equal_saved(after)}
if modals:
    raise RuntimeError("run A met an unexpected sensitive-stage review gate (declined, retained): " + json.dumps(modals))
if guard_facade.refused_total() or guard_logic.refused_total():
    raise RuntimeError("a forbidden owner was attempted during run A: " + json.dumps(result["guards"]))
if diff["unexpected"] or result["joint_issues_after"]:
    raise RuntimeError("run A left an unexpected change: " + json.dumps(diff["unexpected"]) + str(result["joint_issues_after"]))
