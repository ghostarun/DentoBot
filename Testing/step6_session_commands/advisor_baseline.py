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
    """Capture the first unexpected gate and leave the modal untouched for the operator's verdict.

    The command remains blocked in the modal's event loop. The external supervisor must treat the retained
    unexpected-gate file as a stop, submit no further commands, and preserve the owned session for review.
    No consent, Skip, cancellation or dismissal is injected by this watcher.
    """
    modal = qt.QApplication.activeModalWidget()
    if modal is not None and str(modal.objectName) == "DENTOBOTStep6AdvisorGateMessageBox":
        gate_timer.stop()
        modals.append({"utc": _utc_now(), "title": str(modal.windowTitle), "text": str(modal.text)[:300]})
        timeline.stamp("unexpected_gate_stop")
        payload = {"status": "STOP_UNEXPECTED_MODAL", "modal": modals[-1], "before": before,
                   "guards": {"facade": guard_facade.report(), "logic": guard_logic.report()}}
        path = evidence_dir / f"{stamp}-unexpected-gate.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            _capture(report, evidence_dir, run_id, "advisor-UNEXPECTED-GATE-1")
            payload["at_stop"] = probe.invariant_snapshot(logic, facade, parameter_node, label="unexpected-gate")
        except Exception as capture_error:
            payload["capture_error"] = str(capture_error)[:200]
        finally:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


gate_timer = qt.QTimer()
gate_timer.setInterval(300)
gate_timer.connect("timeout()", unexpected_gate)
undo = None
try:
    assert panel.findWorkingConfigButton.enabled, "the Find Working Configuration button is disabled"
    _press(panel.findWorkingConfigButton, "Find Working Configuration")
    _process_events(0.5)
    state = widget._advisorState
    session = state["session"]
    assert state["consentBox"].checked is False, "consent must be OFF by default"
    undo = probe.instrument_session(session, widget, timeline)
    _capture(report, evidence_dir, run_id, "advisor-A-dialog-open")
    gate_timer.start()
    _press(state["startButton"], "Start search")
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
    result = probe.retain_command_failure(
        logic, facade, parameter_node, steps=steps, before=before,
        guards={"facade": guard_facade, "logic": guard_logic},
        path=evidence_dir / f"{stamp}-failure.json", failure=failure)
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
result["baseline_success"] = (steps.get("outcome") == "found" and not steps.get("restore_issues")
                              and len(steps.get("records", [])) == 1
                              and steps["records"][0].get("result") in ("pass", "warning"))
if not result["baseline_success"]:
    _capture(report, evidence_dir, run_id, "advisor-A-first-outcome-failure")
if modals:
    raise RuntimeError("run A met an unexpected sensitive-stage review gate (untouched, retained): " + json.dumps(modals))
if guard_facade.refused_total() or guard_logic.refused_total():
    raise RuntimeError("a forbidden owner was attempted during run A: " + json.dumps(result["guards"]))
if diff["unexpected"] or result["joint_issues_after"]:
    raise RuntimeError("run A left an unexpected change: " + json.dumps(diff["unexpected"]) + str(result["joint_issues_after"]))
