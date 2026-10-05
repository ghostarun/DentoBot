"""Runtime runner for the Feasibility Advisor (S6-LIVE-01 step 3, 2026-10-05).

Runs inside the Slicer session driver on a case COPY, simulation only. Each
candidate is applied through the existing GUI owners (Case Foundation opening,
6.1 Base review/accept, 6.3 planning policy), Task Home is re-validated, then:

1. screen: PreEntry IK endpoint must pass (cheap, static);
2. trials: P1 stage check ``trials`` times, all must plan;
3. full: the standard evidence package runs Diagnose This Base, which must be
   PASS or WARNING.

The baseline is restored at the end; nothing is applied as a recommendation.
Never touched: contact allowances, guard tolerances, barrier constants, tool,
drill axis.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import step6_case_evidence as evidence
from dentobot_workflow import feasibility_advisor as fa
from dentobot_workflow.base_placement_search import candidate_around_base


class AdvisorRunner:
    def __init__(self, namespace: dict, out_dir, reference_base_matrix, baseline: dict,
                 limits: fa.Limits = fa.Limits(), trials: int = 3):
        import numpy as np

        self.ns = namespace
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.reference = np.asarray(reference_base_matrix, dtype=float).reshape(4, 4)
        self.baseline = dict(baseline)
        self.limits = limits
        self.trials = int(trials)
        self.candidates: list[fa.Candidate] = []
        self.cache: dict[str, bool] = {}
        self.started = time.monotonic()

    # ---- helpers -------------------------------------------------------
    def _ev(self):
        import slicer

        slicer.app.processEvents()
        self.ns["widget"]._updateRobotPlacement()

    def _progress(self, text):
        (self.out / "progress.json").write_text(json.dumps({
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_sec": round(time.monotonic() - self.started, 1),
            "text": text,
            "evaluated": len(self.candidates),
        }, indent=2))

    def _active(self):
        logic, node = self.ns["logic"], self.ns["parameter_node"]
        return bool(logic.isRos2MotionControlActive(node.robotBaseTransform))

    def _set_policy_attempts(self, attempts: int):
        import qt
        import slicer

        panel = self.ns["panel"]
        if int(panel.planningPolicy()["planning_attempts"]) == int(attempts):
            return

        def configure():
            for w in slicer.app.topLevelWidgets():
                if w.isVisible() and str(w.windowTitle) == "DENTOBOT Step 6 Planning Parameters":
                    w.findChildren(qt.QSpinBox)[0].value = int(attempts)
                    w.findChild(qt.QDialogButtonBox).button(qt.QDialogButtonBox.Ok).click()

        timer = qt.QTimer()
        timer.setInterval(300)
        timer.connect("timeout()", configure)
        timer.start()
        try:
            self.ns["widget"]._step6SubstepComboBox.currentIndex = 3
            self._ev()
            panel.approachPlanningPolicyButton.click()
        finally:
            timer.stop()
        assert int(panel.planningPolicy()["planning_attempts"]) == int(attempts)

    # ---- apply one full lever state -------------------------------------
    def apply(self, state: dict):
        import vtk

        widget, panel, facade = self.ns["widget"], self.ns["panel"], self.ns["facade"]
        logic, node = self.ns["logic"], self.ns["parameter_node"]
        opening = float(state[fa.MOUTH_OPENING_MM])
        if abs(float(node.step6CaseJawTargetGapMm) - opening) > 1e-6:
            if self._active():
                facade.disconnect()
                self._ev()
            node.step6CaseJawTargetGapMm = opening
            widget.onApplyStep6CaseJawOpening()
            self._ev()
            logic.verifyFinalPrintableTemplate(node.finalPrintableTemplateModel)
            combo = widget.ui.workflowStageComboBox
            combo.currentIndex = next(i for i in range(combo.count) if str(combo.itemText(i)).startswith("6 "))
            self._ev()
            button = widget.ui.importStep6PlanningContextButton
            assert button.enabled, str(button.toolTip)
            button.click()
            self._ev()
        import numpy as np

        # Yaw only (u = v = depth = 0), so the forehead frame argument is unused.
        target = candidate_around_base(np.eye(4), self.reference, 0.0, 0.0, 0.0,
                                       float(state[fa.BASE_YAW_DEG]))
        current = vtk.vtkMatrix4x4()
        node.robotBaseTransform.GetMatrixTransformToWorld(current)
        same = all(abs(current.GetElement(r, c) - target[r][c]) < 1e-9 for r in range(4) for c in range(4))
        # A fresh session needs Step 6 selected, the planning context imported
        # and the robot (or fallback) loaded before the Base can be accepted.
        combo = widget.ui.workflowStageComboBox
        combo.currentIndex = next(i for i in range(combo.count) if str(combo.itemText(i)).startswith("6 "))
        self._ev()
        if widget.ui.importStep6PlanningContextButton.enabled:
            widget.ui.importStep6PlanningContextButton.click()
            self._ev()
        widget._step6SubstepComboBox.currentIndex = 1
        self._ev()
        if panel.loadFallbackButton.enabled:
            panel.loadFallbackButton.click()
            self._ev()
        if not same or not node.robotBaseMountLocked:
            if node.robotBaseMountLocked:
                result = facade.unlockBase()
                assert result.success, result.message
            result = facade.stageManualBaseReview(tuple(float(v) for v in target.flatten()))
            if not result.success:
                facade.cancelManualBaseReview()
                result = facade.stageManualBaseReview(tuple(float(v) for v in target.flatten()))
            assert result.success, result.message
            result = facade.acceptManualBaseReview()
            assert result.success, result.message
            self._ev()
        if not self._active():
            if panel.loadFallbackButton.enabled:
                panel.loadFallbackButton.click()
                self._ev()
            assert panel.connectButton.enabled, str(panel.connectButton.toolTip)
            panel.connectButton.click()
            self._ev()
        self._set_policy_attempts(int(state[fa.PLANNING_ATTEMPTS]))
        facade._approach_corridor_margin_samples = int(state.get(fa.CORRIDOR_MARGIN_SAMPLES, 0))
        widget._step6SubstepComboBox.currentIndex = 2
        self._ev()
        for name in ("cancelTaskHomeReviewButton", "resetManualJogDraftButton",
                     "reviewTaskHomeButton", "acceptTaskHomeButton"):
            button = getattr(panel, name)
            if button.enabled:
                button.click()
                self._ev()
        gap = facade.taskHomeValidationGap(node)
        assert not gap, gap
        widget._step6SubstepComboBox.currentIndex = 3
        self._ev()
        panel.confirmTaskButton.click()
        self._ev()

    # ---- evaluate one candidate (change relative to the baseline) --------
    def evaluate(self, change: dict) -> bool:
        state = {**self.baseline, **change}
        key = json.dumps(state, sort_keys=True)
        if key in self.cache:
            return self.cache[key]
        candidate = fa.Candidate(dict(change), cost=fa.candidate_cost(change, self.baseline, self.limits))
        self.candidates.append(candidate)
        self._progress(f"evaluating {change}")
        facade, panel = self.ns["facade"], self.ns["panel"]
        try:
            self.apply(state)
            # PreEntry IK is seeded and occasionally misses; allow 3 tries.
            for _ in range(3):
                panel.checkPreEntryIKButton.click()
                self._ev()
                if "EndpointChecksPassed" in str(panel.approachStatusLabel.text):
                    break
            if "EndpointChecksPassed" not in str(panel.approachStatusLabel.text):
                candidate.result = "screen_fail"
                candidate.detail = "PreEntry endpoint: " + str(panel.approachStatusLabel.text)[:120]
            else:
                passed = 0
                for _ in range(self.trials):
                    outcome = facade.checkPlanningStage("P1")
                    status = (outcome.payload or {}).get("diagnostic_status") if isinstance(outcome.payload, dict) else None
                    candidate.trials.append(status)
                    passed += status == "passed"
                    if status != "passed":
                        break
                candidate.result = "pass" if passed == self.trials else "fail"
                candidate.detail = f"P1 {passed}/{self.trials}"
        except Exception as exc:  # recorded, never hidden
            candidate.result = "fail"
            candidate.detail = f"setup error: {exc}"[:200]
        label = "-".join(f"{k}={v}" for k, v in sorted(change.items())) or "baseline"
        try:
            run_diagnose = "setup error" not in candidate.detail
            summary = evidence.capture_case_evidence(
                self.ns, self.out / f"candidate-{len(self.candidates):02d}-{label}", f"Candidate {change}",
                run_diagnose=run_diagnose)
            candidate.evidence_dir = f"candidate-{len(self.candidates):02d}-{label}"
            diagnosis = summary.get("diagnosis") or {}
            if candidate.result == "pass" and diagnosis.get("status") == "FAIL":
                candidate.result = "fail"
            candidate.detail += f"; Diagnose {diagnosis.get('status')} ({diagnosis.get('cause_class') or '-'})"
        except Exception as exc:
            candidate.detail += f"; evidence error: {exc}"[:120]
        ok = candidate.result == "pass"
        self.cache[key] = ok
        self._write_report("in progress")
        return ok

    def _write_report(self, cause_class, recommended=()):
        (self.out / "advisor-report.md").write_text(
            fa.report_markdown(self.baseline, cause_class, self.candidates, list(recommended), self.limits),
            encoding="utf-8")
        (self.out / "advisor-candidates.json").write_text(json.dumps(
            [c.__dict__ for c in self.candidates], indent=2, default=str))

    def run(self) -> dict:
        self._progress("baseline")
        baseline_ok = self.evaluate({})
        if baseline_ok:
            self._write_report("passed", [{}])
            return {"baseline_passes": True}
        diagnosis = getattr(self.ns["facade"], "_last_base_diagnosis", None) or {}
        cause_class = diagnosis.get("cause_class") or "unknown"
        baseline_candidate = self.candidates[0] if self.candidates else None
        if (
            baseline_candidate is not None
            and baseline_candidate.result in ("fail", "screen_fail")
            and diagnosis.get("status") != "FAIL"
        ):
            # The P1 trials failed but the later Diagnose run planned: the
            # failure is intermittent planning, not a named obstacle.
            cause_class = "narrow_passage"
        try:
            recommended = fa.search(cause_class, self.evaluate, self.baseline, self.limits)
        finally:
            self._progress("restoring baseline")
            try:
                self.apply(self.baseline)
            except Exception as exc:
                (self.out / "restore-error.txt").write_text(str(exc))
        self._write_report(cause_class, recommended)
        self._progress("done")
        return {"cause_class": cause_class, "recommended": recommended,
                "evaluated": len(self.candidates), "elapsed_sec": round(time.monotonic() - self.started, 1)}
