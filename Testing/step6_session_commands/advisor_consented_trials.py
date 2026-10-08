# S6-ADVISOR-GUI-01 bounded B verification, RUN B (decision D1/O4): the real dialog with the Task Home consent TICKED.
# (continues from Run A's open dialog, after the operator's verdict) tick consent -> "Keep searching for alternatives" -> the first
# Base trial (production Base stage/accept) with the production Home revalidation of the UNCHANGED saved joints -> an
# independently timed Cancel during that trial's P1 Diagnose row (sent by Testing/advisor_cancel_helper.py outside Slicer)
# -> restore through the normal owners and a fresh revalidation of the original joints.
# Never approves a sensitive stage (unexpected gates remain untouched). connect/disconnect and the opening/barrier owners are refused.
# If the external helper never fires within the bound, an in-process Cancel is issued and flagged "not independent".
import json
import step6_advisor_probe as probe

stamp = run_id + "-advisor-B"
session_dir = evidence_dir.parent / "session"
before = probe.invariant_snapshot(logic, facade, parameter_node, label="before-run-B")
steps = {"fallback_inprocess_cancel": False}
widget._configureRobotSimulationShellSubstep(3)
widget._updateStep6PlanningUi()
_process_events(0.3)
guard_facade = probe.OwnerGuard(
    facade, refuse=("connect", "disconnect"),
    count=("stageManualBaseReview", "acceptManualBaseReview", "unlockBase", "stageManualTaskHomeReview",
           "acceptManualTaskHomeReview", "cancelManualTaskHomeReview", "confirmTask", "checkPreEntryIK",
           "checkPlanningStage"))
guard_logic = probe.OwnerGuard(
    logic, refuse=("createOrUpdateStep6CaseJawOpening", "importStep6PlanningContext", "setStep6MouthBarrierTuning"))
timeline = probe.Timeline(session_dir / "advisor-B-timeline.jsonl")
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


def pump_until(predicate, bound_sec, label):
    started = time.monotonic()
    while not predicate() and time.monotonic() - started < bound_sec:
        _process_events(0.25)
    assert predicate(), f"{label} did not happen within {bound_sec:.0f} s"


gate_timer = qt.QTimer()
gate_timer.setInterval(300)
gate_timer.connect("timeout()", unexpected_gate)
undo = None
try:
    state = getattr(widget, "_advisorState", None)
    assert state and state["session"].finished and state["session"].outcome == "found" and not state["session"].restore_issues, \
        "run B continues from Run A's open dialog in the FOUND/restored state (after the operator's verdict)"
    assert state["consentBox"].checked is False, "consent must be OFF by default (Run B ticks it explicitly)"
    _capture(report, evidence_dir, run_id, "advisor-B-dialog-done-consent-off")
    gate_timer.start()
    # Consent is ticked explicitly (default OFF), then Keep searching: the next candidates are Base trials with revalidation
    state["consentBox"].checked = True
    _capture(report, evidence_dir, run_id, "advisor-B-consent-ticked")
    _press(state["moreButton"], "Keep searching")
    session = widget._advisorState["session"]
    assert session.home_consent is not None, "the consent was not recorded for the continued search"
    undo = probe.instrument_session(session, widget, timeline)
    cancel = state["cancelButton"]

    def qt_value(obj, name):  # PythonQt exposes some Qt getters as properties and some as methods
        value = getattr(obj, name)
        return value() if callable(value) else value

    origin = cancel.mapToGlobal(qt.QPoint(0, 0))  # the call pattern the existing headed runner already uses
    centre_x = int(origin.x() + int(qt_value(cancel, "width")) // 2)
    centre_y = int(origin.y() + int(qt_value(cancel, "height")) // 2)
    (session_dir / "cancel-arm.json").write_text(json.dumps({
        "x": centre_x, "y": centre_y, "target_step": "diagnose · p1_route", "min_candidate": 2,
        "offset_sec": 2.0, "timeline": str(session_dir / "advisor-B-timeline.jsonl"), "armed_mono_ns": time.monotonic_ns()}), encoding="utf-8")
    _capture(report, evidence_dir, run_id, "advisor-B-keep-searching-started")
    t_arm = time.monotonic()
    shot = False
    while not session.finished and time.monotonic() - t_arm < 900.0:
        _process_events(0.25)
        if not shot and session.phase == "evaluating" and len(session.records) >= 1 and session.progress().get("index", 0) >= 1:
            shot = True
            _capture(report, evidence_dir, run_id, "advisor-B-first-trial-running")
        if (not session.finished and time.monotonic() - t_arm > 600.0 and not steps["fallback_inprocess_cancel"]):
            steps["fallback_inprocess_cancel"] = True  # the independent helper did not fire: not an independent measurement
            timeline.stamp("fallback_inprocess_cancel")
            _press(cancel, "Cancel")
    assert session.finished, "the continued search did not finish within the bound"
    _process_events(0.5)
    _capture(report, evidence_dir, run_id, "advisor-B-done")
    steps.update(outcome=session.outcome, message=session.message, restore_issues=list(session.restore_issues),
                 records=[{k: r.get(k) for k in ("sequence", "stage", "result", "failed_step", "reason", "timings_sec",
                                                 "home_revalidation", "home_rejected")} for r in session.records],
                 home_ledger=session.home_ledger, longest_step=session.longest_step(), evidence_root=str(session.root),
                 export=session.export_evidence(), unexpected_gates=modals)
    # the dialog stays open for the operator's visual verdict; the session stop command ends everything
except BaseException as failure:
    try:  # the first causal failure gets its own state-matched screenshot (the runner's fail() does not capture)
        _capture(report, evidence_dir, run_id, "advisor-B-FAILURE")
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
after = probe.invariant_snapshot(logic, facade, parameter_node, label="after-run-B")
diff = probe.snapshot_diff(before, after, allow=probe.EXPECTED_AUTHORITY_DRIFT)
(evidence_dir / f"{stamp}-snapshots.json").write_text(json.dumps({"before": before, "after": after, "diff": diff}, indent=2), encoding="utf-8")
result = {"steps": steps, "guards": {"facade": guard_facade.report(), "logic": guard_logic.report()},
          "invariant_diff": diff, "joint_issues_after": probe.joints_equal_saved(after)}
helper_path = session_dir / "cancel-helper.json"
receipt_deadline = time.monotonic() + 5.0
while not helper_path.exists() and time.monotonic() < receipt_deadline:
    _process_events(0.1)  # the external sender finishes its own receipt after the click; no replacement input
helper_result = json.loads(helper_path.read_text()) if helper_path.exists() else {}
result["external_cancel"] = helper_result
timeline_rows = [json.loads(line) for line in (session_dir / "advisor-B-timeline.jsonl").read_text().splitlines()]
if helper_result.get("sent"):
    result["cancel_latency"] = probe.cancel_latency(timeline_rows, helper_result)
    (session_dir / "advisor-B-cancel-latency.json").write_text(json.dumps(result["cancel_latency"], indent=2), encoding="utf-8")
if helper_result.get("sent") and not result["cancel_latency"].get("measurement_complete"):
    raise RuntimeError("external Cancel measurement is incomplete: handler/covering-step/restore/done stamps are required")
if not helper_result.get("sent") or steps.get("outcome") != "cancelled":
    raise RuntimeError("no externally cancelled trial was demonstrated; retained outcome is not a Cancel measurement")
if modals:
    raise RuntimeError("run B met an unexpected sensitive-stage review gate (untouched, retained): " + json.dumps(modals))
if steps["fallback_inprocess_cancel"]:
    raise RuntimeError("the independent cancel helper did not fire: an in-process Cancel ended the search, so NO independent "
                       "Cancel-latency measurement was obtained (outcome retained, not substituted)")
if guard_facade.refused_total() or guard_logic.refused_total():
    raise RuntimeError("a forbidden owner was attempted during run B: " + json.dumps(result["guards"]))
if diff["unexpected"] or result["joint_issues_after"] or steps.get("restore_issues"):
    raise RuntimeError("run B ended with an unexpected change or an unconfirmed restoration: " + json.dumps(
        {"unexpected": diff["unexpected"], "joints": result["joint_issues_after"], "restore": steps.get("restore_issues")}))
