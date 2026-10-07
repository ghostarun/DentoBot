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


# ---------------------------------------------------------------------------
# Ordered search runner (operator 2026-10-06, S6-MULTI-TARGET-01 FDI34).
#
# One full candidate state per evaluation, in this order, stopping at the first
# failure: [isolated scratch branch rebuild + jaw-local trajectory/template
# consistency] -> prerequisites/scene -> stroke reach -> authoritative PreEntry
# (structured v2 seeds) -> adaptive-corridor clearance (P1 rule, read-only) ->
# full Diagnose (P1-P3 + frame audit). S6-AUDIT-D-01 evidence (exact pairs,
# exported meshes, exact separation, effective MoveIt padding/scale) is captured
# for every candidate that reaches PreEntry. ``confirm`` evaluates exactly one
# candidate and never expands the search.

SPINDLE_LINK = "pneumatic_spindle-Copy"


class OrderedAdvisorRunner:
    def __init__(self, namespace: dict, out_dir, *, saved_base_matrix, target_fdi: str, branch_id: str,
                 baseline_opening_mm: float, limits: fa.OrderedLimits = fa.OrderedLimits(),
                 audit_bodies=("lip_slab", "fdi24"), checkpoint_path=None, scratch_root=None,
                 home_si: dict | None = None, home_seed_si: dict | None = None,
                 home_retract_ladder_mm=(15.0, 20.0, 25.0, 30.0, 35.0, 40.0)):
        import numpy as np

        self.ns = namespace
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        # Isolated scratch copies live under this run directory (default: out_dir).
        self.scratch_root = Path(scratch_root) if scratch_root is not None else self.out
        self.saved_base = np.asarray(saved_base_matrix, dtype=float).reshape(4, 4)
        self.target_fdi = str(target_fdi)
        self.branch_id = str(branch_id)
        self.limits = limits
        self.baseline = fa.baseline_state(baseline_opening_mm)
        self.audit_bodies = tuple(audit_bodies)
        self.store = fa.CheckpointStore(checkpoint_path or self.out / "advisor-checkpoints.jsonl")
        self.records: list[dict] = []
        self.reference_geometry: dict | None = None
        self._reference_poly = None
        self.geometry: dict = {}
        # An operator-named Home (joint name -> SI value) overrides the case lookup.
        self.saved_home: dict | None = dict(home_si) if home_si else None
        self.saved_home_source = "operator" if home_si else ""
        # Operator 2026-10-06 ("set any valid home, closer to the pre entry and orientation"):
        # Home = PreEntry joints with the horizontal slider retracted (orientation joints kept).
        self.home_seed_si = dict(home_seed_si) if home_seed_si else None
        self.home_retract_ladder_mm = tuple(float(v) for v in home_retract_ladder_mm)
        self.home_selection: dict = {}
        self.started = time.monotonic()

    # ---- context helpers ----------------------------------------------------
    def _ctx(self):
        ns = self.ns
        return ns["widget"], ns["panel"], ns["facade"], ns["logic"], ns["parameter_node"]

    def _ev(self, delay: float = 0.0):
        import slicer

        widget = self.ns["widget"]
        end = time.monotonic() + delay
        while True:
            slicer.app.processEvents()
            widget._updateRobotPlacement()
            if time.monotonic() >= end:
                return
            time.sleep(0.02)

    def _write(self, name: str, payload) -> str:
        path = self.out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
        return str(path)

    def _progress(self, text: str):
        self._write("progress.json", {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                      "elapsed_sec": round(time.monotonic() - self.started, 1), "text": text,
                                      "evaluated": len(self.records)})

    @staticmethod
    def _matrix(transform_node):
        import numpy as np
        import vtk

        m = vtk.vtkMatrix4x4()
        transform_node.GetMatrixTransformToWorld(m)
        return np.array([[m.GetElement(r, c) for c in range(4)] for r in range(4)])

    def _base_matrix(self):
        return self._matrix(self._ctx()[4].robotBaseTransform)

    def _jaw_matrix(self):
        """Opening transform for a lower-jaw target (its geometry moves with the jaw); identity otherwise."""
        import numpy as np

        logic, node = self._ctx()[3], self._ctx()[4]
        jaw = getattr(node, "step6CaseJawTransform", None)
        if jaw is None or logic._targetJawOwner(node, str(node.targetToothSegmentId or "")) != "MovingLower":
            return np.eye(4)
        return self._matrix(jaw)

    def _stage6(self):
        widget = self._ctx()[0]
        combo = widget.ui.workflowStageComboBox
        combo.currentIndex = next(i for i in range(combo.count) if str(combo.itemText(i)).startswith("6 "))
        self._ev(0.2)

    def _dismiss_modals(self, store: list):
        import qt
        import slicer

        def dismiss():
            for widget in slicer.app.topLevelWidgets():
                if widget.isVisible() and widget.inherits("QMessageBox"):
                    store.append(str(widget.text)[:300])
                    widget.accept()

        timer = qt.QTimer()
        timer.setInterval(400)
        timer.connect("timeout()", dismiss)
        timer.start()
        return timer

    # ---- isolation and geometry ---------------------------------------------
    def require_scratch(self):
        """Branch rebuilds run only on a case copy inside this run directory, never saved."""
        loaded = getattr(self.ns["widget"], "_loadedCaseBundlePath", None)
        if not loaded or self.scratch_root.resolve() not in Path(str(loaded)).resolve().parents:
            raise RuntimeError(f"Refusing to rebuild: loaded case {loaded!r} is not an isolated scratch copy "
                               f"under {self.scratch_root}")
        return str(loaded)

    def _template_poly_jaw_local(self):
        # Intentional jaw-local provenance oracle: map full world pose back to closed jaw.
        import vtk

        node = self._ctx()[4]
        model = node.finalPrintableTemplateModel
        poly = vtk.vtkPolyData()
        poly.DeepCopy(model.GetPolyData())
        world = vtk.vtkGeneralTransform()
        if model.GetParentTransformNode() is not None:
            model.GetParentTransformNode().GetTransformToWorld(world)
        to_local = vtk.vtkMatrix4x4()
        jaw = vtk.vtkMatrix4x4()
        jaw.DeepCopy(self._jaw_matrix().flatten().tolist())
        vtk.vtkMatrix4x4.Invert(jaw, to_local)
        combined = vtk.vtkGeneralTransform()
        combined.PostMultiply()
        combined.Concatenate(world)
        combined.Concatenate(to_local)
        transform = vtk.vtkTransformPolyDataFilter()
        transform.SetInputData(poly)
        transform.SetTransform(combined)
        transform.Update()
        return transform.GetOutput()

    def _jaw_local_trajectory(self):
        import numpy as np

        node = self._ctx()[4]
        inverse = np.linalg.inv(self._jaw_matrix())
        points = []
        for index in range(2):
            p = [0.0, 0.0, 0.0]
            node.trajectoryLine.GetNthControlPointPositionWorld(index, p)
            points.append((inverse @ np.r_[p, 1.0])[:3].round(4).tolist())
        return points

    @staticmethod
    def _surface_distances(poly, reference):
        import numpy as np
        import vtk

        def one_way(a, b):
            implicit = vtk.vtkImplicitPolyDataDistance()
            implicit.SetInput(b)
            return [abs(implicit.EvaluateFunction(a.GetPoint(i))) for i in range(a.GetNumberOfPoints())]

        both = np.array(one_way(poly, reference) + one_way(reference, poly))
        return float(np.percentile(both, 95)), float(both.max())

    def geometry_summary(self, reference_poly=None) -> dict:
        import vtk

        poly = self._template_poly_jaw_local()
        triangles = vtk.vtkTriangleFilter()
        triangles.SetInputData(poly)
        triangles.Update()
        mass = vtk.vtkMassProperties()
        mass.SetInputData(triangles.GetOutput())
        mass.Update()
        center = vtk.vtkCenterOfMass()
        center.SetInputData(poly)
        center.SetUseScalarsAsWeights(False)
        center.Update()
        template = {"bounds": list(poly.GetBounds()), "centroid": list(center.GetCenter()),
                    "volume_mm3": float(mass.GetVolume()), "points": int(poly.GetNumberOfPoints())}
        if reference_poly is not None:
            template["surface_distance_p95_mm"], template["surface_distance_max_mm"] = self._surface_distances(
                poly, reference_poly)
        return {"trajectory_mm": self._jaw_local_trajectory(), "template": template,
                "opening_mm": float(self._ctx()[4].step6CaseJawTargetGapMm)}, poly

    def capture_reference(self):
        """Reference branch geometry (jaw-local) and saved Home, before any change."""
        import vtk

        widget, panel, facade, logic, node = self._ctx()
        if facade is not None and logic.isRos2MotionControlActive(node.robotBaseTransform):
            facade.disconnect()
            self._ev(0.3)
        logic.activateDentoCasePreparedBranch(node, self.branch_id)
        self._ev(0.3)
        summary, poly = self.geometry_summary()
        writer = vtk.vtkXMLPolyDataWriter()
        writer.SetFileName(str(self.out / "reference-template-jaw-local.vtp"))
        writer.SetInputData(poly)
        writer.Write()
        self._reference_poly = poly
        self.reference_geometry = summary
        if self.saved_home is None:
            self.saved_home, self.saved_home_source = self.find_saved_home()
        self._write("reference.json", {"branch_id": self.branch_id, "geometry": summary,
                                       "saved_home_si": self.saved_home, "saved_home_source": self.saved_home_source,
                                       "saved_base": self.saved_base.tolist(),
                                       "loaded_case": str(getattr(widget, "_loadedCaseBundlePath", ""))})
        return summary

    def find_saved_home(self) -> tuple:
        """Saved Home: the case Task Home, else this branch's working configuration."""
        logic, node = self._ctx()[3], self._ctx()[4]
        home = logic.taskHomeRecord(node)
        if home is not None:
            return dict(zip(home.joint_names, home.joint_positions_si)), "case step6TaskHomeJson"
        try:
            import step6_branch_config

            config = (step6_branch_config.read(self.branch_id) or {}).get("config") or {}
        except Exception:  # research node absent or unreadable
            config = {}
        if config.get("task_home_si"):
            return dict(config["task_home_si"]), "branch working configuration"
        return None, "none saved"

    def near_preentry_home_candidates(self) -> list:
        """PreEntry seed with link-4_Slider-4 retracted, closest to PreEntry first (within limits)."""
        if not self.home_seed_si:
            return []
        out = []
        for retract in self.home_retract_ladder_mm:
            q = dict(self.home_seed_si)
            q["link-4_Slider-4"] = round(float(q["link-4_Slider-4"]) - retract / 1000.0, 6)
            if q["link-4_Slider-4"] >= 0.0:
                out.append((retract, q))
        return out

    def select_near_preentry_home(self) -> dict:
        """Screen candidates (read-only validity), guarded-jog to the first valid one.

        Returns the selection record; the existing Home review/accept flow then
        accepts the current pose. Nothing here relaxes a guard or collision rule.
        """
        import DENTOROS2Bridge as bridge

        facade = self._ctx()[2]
        record = {"strategy": "near_preentry", "seed_si": self.home_seed_si, "tried": [], "selected": None}
        for retract, q in self.near_preentry_home_candidates():
            valid, reason, authoritative = bridge.check_moveit_static_joint_state(q)
            row = {"retract_mm": retract, "joints_si": q, "static_valid": bool(valid),
                   "authoritative": bool(authoritative), "reason": str(reason)[:300]}
            record["tried"].append(row)
            if not (valid and authoritative):
                continue
            jog = facade.guardManualRobotJog(q)
            self._ev(0.5)
            row["jog"] = [bool(jog.success), str(jog.code), str(jog.message)[:300]]
            if jog.success:
                record["selected"] = {"retract_mm": retract, "joints_si": q}
                break
            if (jog.details or {}).get("manualJogReconciliationRequired"):
                row["stopped"] = "manual jog reconciliation required"
                break
        self.home_selection = record
        return record

    def require_saved_home(self):
        """Stop before any rebuild when there is no saved Home to validate (setup error)."""
        if not self.saved_home:
            raise RuntimeError(f"No saved Task Home for branch {self.branch_id} ({self.saved_home_source}); "
                               "the operator must name the Home before a candidate can be evaluated.")
        return self.saved_home

    def rebuild_branch(self, opening_mm: float) -> dict:
        """Isolated scratch rebuild of the target branch at ``opening_mm`` + consistency check."""
        import slicer
        import step6_multitarget_chain as chain

        self.require_scratch()
        widget, panel, facade, logic, node = self._ctx()
        if logic.isRos2MotionControlActive(node.robotBaseTransform):
            facade.disconnect()
            self._ev(0.3)
        self._stage6()
        node.step6CaseJawTargetGapMm = float(opening_mm)
        widget.onApplyStep6CaseJawOpening()
        self._ev(1.5)
        trajectory = next(n for n in slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode")
                          if n.GetName().startswith(f"[Step 4A] DENTO FDI {self.target_fdi} "))
        record = {"opening_mm": float(opening_mm)}
        try:
            record["build"] = chain.build_branch(widget, trajectory, self.target_fdi,
                                                 process_events=lambda d: self._ev(d))
        except Exception as exc:  # recorded, never hidden: the opening stays UNTESTED
            record.update(status="build_failed", error=str(exc)[:600])
            self.geometry[float(opening_mm)] = record
            self._write(f"rebuild-{opening_mm:.1f}mm.json", record)
            return record
        summary, _poly = self.geometry_summary(self._reference_poly)
        record["geometry"] = summary
        record["consistency"] = fa.compare_geometry(self.reference_geometry, summary, self.limits)
        record["status"] = "built" if record["consistency"]["status"] == "PASS" else "inconsistent"
        self.geometry[float(opening_mm)] = record
        self._write(f"rebuild-{opening_mm:.1f}mm.json", record)
        return record

    # ---- candidate application ----------------------------------------------
    def _barrier_issues(self, state) -> list:
        import inspect
        import dentobot_workflow.mouth_portal as mp

        node = self._ctx()[4]
        issues = []
        if str(node.step6MouthBarrierEdgeMode or "gum_line") != state[fa.BARRIER_EDGE_MODE]:
            issues.append(f"edge mode {node.step6MouthBarrierEdgeMode!r} != {state[fa.BARRIER_EDGE_MODE]!r}")
        live = {
            fa.LIP_MARGIN_MM: inspect.signature(mp.shift_portal_to_lip_line).parameters["margin_mm"].default,
            fa.PORTAL_ENLARGE_MM: inspect.signature(mp.enlarge_portal).parameters["margin_mm"].default,
            fa.LIP_SLAB_MM: inspect.signature(mp.build_mouth_barrier).parameters["lip_thickness_mm"].default,
        }
        for key, value in live.items():
            if abs(float(value) - float(state[key])) > 1e-9:
                issues.append(f"{key} live {value} != requested {state[key]}")
        return issues

    def _set_policy(self, state):
        import qt
        import slicer

        widget, panel, facade, logic, node = self._ctx()
        wanted = {"planner_id": state[fa.PLANNER_ID], "planning_attempts": int(state[fa.PLANNING_ATTEMPTS]),
                  "planning_time_sec": float(state[fa.PLANNING_TIME_SEC])}
        if panel.planningPolicy() != wanted:
            def configure():
                for w in slicer.app.topLevelWidgets():
                    if w.isVisible() and str(w.windowTitle) == "DENTOBOT Step 6 Planning Parameters":
                        combo = w.findChildren(qt.QComboBox)[0]
                        combo.currentIndex = next(i for i in range(combo.count)
                                                  if str(combo.itemData(i)) == wanted["planner_id"])
                        w.findChildren(qt.QSpinBox)[0].value = wanted["planning_attempts"]
                        w.findChildren(qt.QDoubleSpinBox)[0].value = wanted["planning_time_sec"]
                        w.findChild(qt.QDialogButtonBox).button(qt.QDialogButtonBox.Ok).click()

            timer = qt.QTimer()
            timer.setInterval(300)
            timer.connect("timeout()", configure)
            timer.start()
            try:
                widget._step6SubstepComboBox.currentIndex = 3
                self._ev()
                panel.approachPlanningPolicyButton.click()
            finally:
                timer.stop()
        # Diagnose plans with the facade policy, not the panel's: set and record both.
        facade.setJointPlanningPolicy(wanted["planner_id"], wanted["planning_attempts"], wanted["planning_time_sec"])
        issues = []
        if panel.planningPolicy() != wanted:
            issues.append(f"panel policy {panel.planningPolicy()} != {wanted}")
        used = facade.jointPlanningPolicy()
        if {k: used[k] for k in wanted} != wanted:
            issues.append(f"facade policy {used} != {wanted}")
        return issues

    def apply(self, state) -> dict:
        """Apply one full state through the GUI owners; returns the observed prerequisites."""
        import numpy as np
        from dentobot_workflow.base_placement_search import candidate_around_base

        widget, panel, facade, logic, node = self._ctx()
        observed = {"modals": []}
        timer = self._dismiss_modals(observed["modals"])
        try:
            geometry = self.geometry.get(float(state[fa.MOUTH_OPENING_MM]))
            if geometry is not None and geometry.get("status") != "built":
                observed["geometry_issues"] = [f"rebuild {geometry.get('status')}: "
                                               + str(geometry.get("error") or geometry.get("consistency"))[:300]]
            self._stage6()
            if widget.ui.importStep6PlanningContextButton.enabled:
                widget.ui.importStep6PlanningContextButton.click()
                self._ev()
            widget._step6SubstepComboBox.currentIndex = 1
            self._ev()
            if panel.loadFallbackButton.enabled:
                panel.loadFallbackButton.click()
                self._ev()
            forehead = logic._foreheadFrameFromStoredPlane(node.robotMountPlane)
            target = candidate_around_base(forehead, self.saved_base, float(state[fa.BASE_U_MM]),
                                           float(state[fa.BASE_V_MM]), float(state[fa.BASE_DEPTH_MM]),
                                           float(state[fa.BASE_YAW_DEG]))
            observed["requested_base"] = target.tolist()
            if node.robotBaseMountLocked:
                facade.unlockBase()
                self._ev()
            flat = tuple(float(v) for v in target.flatten())
            result = facade.stageManualBaseReview(flat)
            if not result.success:
                facade.cancelManualBaseReview()
                result = facade.stageManualBaseReview(flat)
            result = facade.acceptManualBaseReview()
            self._ev()
            observed["base_accept"] = [bool(result.success), str(result.message)[:200]]
            if not logic.isRos2MotionControlActive(node.robotBaseTransform) and panel.connectButton.enabled:
                panel.connectButton.click()
                self._ev()
            if bool(getattr(node, "step6AllowSpindleGuideContact", False)) != bool(state[fa.SPINDLE_TEMPLATE_ALLOWANCE]):
                node.step6AllowSpindleGuideContact = bool(state[fa.SPINDLE_TEMPLATE_ALLOWANCE])
                observed["allowance_changed"] = True
            observed["policy_issues"] = self._set_policy(state)
            facade._approach_corridor_margin_samples = int(state[fa.CORRIDOR_MARGIN_SAMPLES])
            widget._step6SubstepComboBox.currentIndex = 2
            self._ev()
            if self.home_seed_si:
                observed["home_selection"] = self.select_near_preentry_home()
            for name in ("cancelTaskHomeReviewButton", "resetManualJogDraftButton",
                         "reviewTaskHomeButton", "acceptTaskHomeButton"):
                button = getattr(panel, name)
                if button.enabled:
                    button.click()
                    self._ev()
            widget._step6SubstepComboBox.currentIndex = 3
            self._ev()
            panel.confirmTaskButton.click()
            self._ev()
        except Exception as exc:  # recorded, never hidden
            observed["apply_error"] = str(exc)[:400]
        finally:
            timer.stop()
        # ---- observed prerequisites (read back, never assumed) ----
        home = logic.taskHomeRecord(node)
        current_home = dict(zip(home.joint_names, home.joint_positions_si)) if home is not None else {}
        if self.home_seed_si and current_home:
            # Operator-directed Home: the reference is the Home accepted in this session.
            selected = (self.home_selection or {}).get("selected")
            self.saved_home = dict(current_home)
            self.saved_home_source = (f"operator-directed near-PreEntry (S4 retracted {selected['retract_mm']} mm)"
                                      if selected else "operator-directed: current pose (near-PreEntry jog not accepted)")
        observed.update({
            "ros_connected": bool(logic.isRos2MotionControlActive(node.robotBaseTransform)),
            "base_locked": bool(node.robotBaseMountLocked),
            "base_delta_mm": float(np.abs(self._base_matrix() - np.asarray(observed.get("requested_base"), float)).max())
            if observed.get("requested_base") else None,
            "home_gap": str(facade.taskHomeValidationGap(node) or ""),
            "home_si": current_home, "saved_home_si": self.saved_home, "saved_home_source": self.saved_home_source,
            "home_delta_si": max((abs(float(current_home.get(k, 1e9)) - float(v)) for k, v in (self.saved_home or {}).items()),
                                 default=None) if self.saved_home else None,
            "task_confirmation_issues": [str(s) for s in (logic.confirmedTaskFreshnessIssues(node) or ())],
            "collision_audit_issues": [str(s) for s in (logic.collisionSceneAuditFreshnessIssues(node) or ())],
            "barrier_issues": self._barrier_issues(state),
            "spindle_template_allowance": bool(getattr(node, "step6AllowSpindleGuideContact", False)),
            "opening_mm": float(node.step6CaseJawTargetGapMm),
        })
        if abs(observed["opening_mm"] - float(state[fa.MOUTH_OPENING_MM])) > 1e-6:
            observed.setdefault("geometry_issues", []).append(
                f"opening {observed['opening_mm']} mm != requested {state[fa.MOUTH_OPENING_MM]} mm")
        if observed.get("apply_error"):
            observed.setdefault("geometry_issues", []).append("apply error: " + observed["apply_error"])
        scene = facade.ensureMoveItSceneMatches()
        observed["scene_state"], observed["scene_message"] = scene.get("state"), scene.get("message")
        return observed

    # ---- evaluation steps -------------------------------------------------------
    def _identity(self, state) -> dict:
        widget, panel, facade, logic, node = self._ctx()
        geometry = self.geometry.get(float(state[fa.MOUTH_OPENING_MM])) or {}
        return {
            "schema": fa.ADVISOR_SCHEMA, "state": fa.state_key(state), "target_fdi": self.target_fdi,
            "branch_id": self.branch_id, "robot_profile": logic.robotProfileFingerprint(),
            "saved_base": fa.fingerprint_of([round(v, 6) for v in self.saved_base.flatten()]),
            "saved_home": fa.fingerprint_of(self.saved_home),
            "reference_geometry": fa.fingerprint_of(self.reference_geometry),
            "rebuilt_geometry": fa.fingerprint_of((geometry.get("geometry") or {}).get("template")),
        }

    def preentry(self) -> dict:
        widget, panel, facade, logic, node = self._ctx()
        result = facade.checkPreEntryIK()
        self._ev()
        session = getattr(result.payload, "to_dict", None)
        session = session() if callable(session) else {}
        seeds = []
        for record in session.get("candidate_records") or ():
            seeds.append({k: record.get(k) for k in (
                "candidate_index", "seed_provenance", "route_type", "solver_success", "termination_reason",
                "collision_check_status", "collision_pairs", "best_joint_positions_si",
                "static_state_validity_status", "static_state_validity_message", "endpoint_check_status",
                "endpoint_collision_clear", "failure_classification", "position_residual_mm",
                "drilling_axis_residual_deg", "authoritative_position_residual_mm",
                "authoritative_drilling_axis_residual_deg")})
        raw = {"success": bool(result.success), "code": str(result.code), "message": str(result.message),
               "details": dict(result.details or {}), "seeds": seeds,
               "session_identity": {k: session.get(k) for k in (
                   "session_fingerprint", "task_fingerprint", "base_fingerprint", "trajectory_fingerprint",
                   "robot_profile_fingerprint", "collision_audit_fingerprint", "planning_parameters_fingerprint")}}
        step = fa.classify_preentry(raw)
        step["raw"] = raw
        return step

    def corridor(self) -> dict:
        result = self._ctx()[2].checkApproachCorridorClearance()
        step = fa.classify_corridor({"success": result.success, "code": result.code, "message": result.message,
                                     "details": result.details})
        step["message"] = str(result.message)[:500]
        step["identity"] = (result.details or {}).get("identity")
        return step

    def diagnose(self, evidence_dir: Path, label: str) -> dict:
        widget, panel, facade, logic, node = self._ctx()
        facade.invalidateMotionPlan()
        summary = evidence.capture_case_evidence(self.ns, evidence_dir, label, run_diagnose=True)
        step = fa.classify_diagnosis(summary.get("diagnosis") or {})
        step.update(policy_used=facade.jointPlanningPolicy(), panel_policy=panel.planningPolicy(),
                    frame_audit=summary.get("frame_audit"), drilling=summary.get("drilling"),
                    corridor_mm=summary.get("corridor_mm"))
        return step

    # ---- S6-AUDIT-D-01 evidence ------------------------------------------------
    def _moveit_padding(self) -> dict:
        """Effective move_group padding/scale (read-only ``ros2 param get``)."""
        import subprocess

        out = {}
        for name in ("default_robot_padding", "robot_description_planning.default_robot_padding",
                     "robot_description_planning.default_robot_scale",
                     "robot_description_planning.default_object_padding"):
            try:
                done = subprocess.run(["ros2", "param", "get", "/move_group", name], capture_output=True,
                                      text=True, timeout=15)
                out[name] = (done.stdout or done.stderr).strip()[:200]
            except Exception as exc:
                out[name] = f"unavailable: {exc}"[:200]
        return out

    def _body_poly(self, key):
        """World geometry of an audited body (lip slab, template or tooth by FDI suffix)
        and the text that names it in MoveIt object ids."""
        widget, panel, facade, logic, node = self._ctx()
        if key == "lip_slab":
            for name, poly in logic.step6MouthBarrierPolydataWorld(node):
                if "lip" in name:
                    return name, poly, "lip_slab"
            return None, None, None
        if key == "template":
            import step6_frame_audit as frame_audit

            return "final_template", frame_audit.model_world_polydata(node.finalPrintableTemplateModel), "Template"
        segmentation = node.teethSegmentation
        seg = segmentation.GetSegmentation()
        for index in range(seg.GetNumberOfSegments()):
            segment_id = seg.GetNthSegmentID(index)
            if seg.GetSegment(segment_id).GetName().endswith(key):
                world = logic._segmentationSegmentsSurfaceWorld(segmentation, {segment_id})
                if segment_id in set(logic.step6CaseJawSegmentIds(segmentation).get("lower", ())):
                    world = logic._step6CaseJawPolydataWorld(node, world)
                return seg.GetSegment(segment_id).GetName(), world, segment_id
        return None, None, None

    def audit_state(self, joints: dict, out_dir: Path, tag: str) -> dict:
        """Same-state exact MoveIt pairs vs exact mesh separation and vertex sampling."""
        import numpy as np
        import vtk
        import DENTOROS2Bridge as bridge
        import step6_frame_audit as frame_audit

        widget, panel, facade, logic, node = self._ctx()
        out_dir.mkdir(parents=True, exist_ok=True)
        urdf, package_root = logic.robotDescriptionPaths()
        fk = frame_audit.UrdfFk(Path(urdf).read_text(encoding="utf-8"))
        origin, filename, scale = fk.collision(SPINDLE_LINK)
        mesh, triangles = frame_audit.read_binary_stl_mesh(
            Path(package_root) / filename.split("package://dentobot_description/", 1)[-1])
        pose = frame_audit.to_ras_mm(self._base_matrix(), fk.link_pose_m(SPINDLE_LINK, joints) @ origin)
        points = (pose @ np.c_[mesh * np.array(scale) * 1000.0, np.ones(len(mesh))].T).T[:, :3]
        np.savez_compressed(out_dir / f"{tag}-spindle-world.npz", vertices=points, triangles=triangles,
                            joints=json.dumps(joints), urdf_scale=np.array(scale))
        # Frames for the offline MoveIt-scene comparison (step6_audit_d_compare.py).
        owner = logic._targetJawOwner(node, str(node.targetToothSegmentId or ""))
        (out_dir / f"{tag}-frames.json").write_text(json.dumps(
            {"base_world_mm": self._base_matrix().tolist(), "jaw_world": self._jaw_matrix().tolist(),
             "jaw_owner": owner, "joints_si": dict(joints)}, indent=1), encoding="utf-8")
        valid, reason, authoritative = bridge.check_moveit_static_joint_state(joints)
        record = {"joints_si": dict(joints), "moveit_valid": bool(valid), "moveit_authoritative": bool(authoritative),
                  "moveit_reason": str(reason), "moveit_pairs": fa.pairs_from_text(reason),
                  "urdf_collision_scale": list(scale), "bodies": {}}
        for key in (*self.audit_bodies, "template"):
            name, poly, hint = self._body_poly(key)
            if poly is None or poly.GetNumberOfPoints() == 0:
                record["bodies"][key] = {"status": "no_geometry"}
                continue
            writer = vtk.vtkXMLPolyDataWriter()
            writer.SetFileName(str(out_dir / f"{tag}-{key}-world.vtp"))
            writer.SetInputData(poly)
            writer.Write()
            vertices, body_triangles = frame_audit.polydata_mesh(poly)
            exact = frame_audit.exact_mesh_separation(points, triangles, vertices, body_triangles)
            implicit = vtk.vtkImplicitPolyDataDistance()
            implicit.SetInput(poly)
            sampled = float(min(implicit.EvaluateFunction(tuple(p)) for p in points))
            record["bodies"][key] = {"body": name, "exact_distance_mm": exact["distance_mm"],
                                     "exact_intersecting": exact["intersecting"],
                                     "exact_pairs_evaluated": exact["pairs_evaluated"],
                                     "exact_lower_bound_mm": exact["search_mm"] if exact["distance_mm"] is None else None,
                                     "vertex_sampled_min_signed_mm": round(sampled, 4),
                                     "moveit_named": any(str(hint).lower() in b.lower() for pair in record["moveit_pairs"]
                                                         for b in pair if not b.startswith(SPINDLE_LINK))}
        return record

    # ---- one candidate --------------------------------------------------------------
    def evaluate(self, stage: str, state: dict) -> dict:
        violations = fa.state_violations(state, self.baseline[fa.MOUTH_OPENING_MM], self.limits)
        index = len(self.records) + 1
        label = "-".join(f"{k}={v}" for k, v in sorted(fa.state_delta(state, self.baseline).items())) or "baseline"
        cand_dir = self.out / f"candidate-{index:02d}-{label}"
        steps: dict = {}
        if violations:
            steps["prerequisites"] = {"result": fa.SETUP_ERROR, "reason": "; ".join(violations)}
            return self._finish(stage, state, steps, {}, cand_dir)
        opening = float(state[fa.MOUTH_OPENING_MM])
        current = float(self._ctx()[4].step6CaseJawTargetGapMm)
        if opening not in self.geometry and abs(current - opening) > 1e-6:
            self._progress(f"rebuilding branch at {opening} mm")
            rebuild = self.rebuild_branch(opening)
            if rebuild.get("status") == "build_failed":
                record = fa.candidate_record(stage, state, self.baseline, {}, identity={}, evidence_dir=str(cand_dir))
                record.update(result=fa.UNTESTED, failed_step="rebuild",
                              reason="untested — template build failed: " + str(rebuild.get("error"))[:300])
                return self._store(record, cand_dir)
        identity = self._identity(state)
        reused = self.store.lookup(state, identity)
        if reused is not None:
            record = dict(reused, reused_from=reused.get("evidence_dir"), evidence_dir=reused.get("evidence_dir"))
            self.records.append(record)
            return record
        self._progress(f"applying {label}")
        observed = self.apply(state)
        issues = fa.precondition_issues(observed, self.limits)
        steps["prerequisites"] = {"result": fa.SETUP_ERROR if issues else fa.PASSED,
                                  "reason": "; ".join(issues) if issues else "prerequisites and scene current",
                                  "observed": observed}
        if not issues:
            stroke = self._ctx()[3].step6CurrentBaseStrokeReachability(self._ctx()[4])
            steps["stroke_reach"] = {"result": fa.PASSED if (stroke or {}).get("reachable") else fa.UNREACHABLE,
                                     "reason": str((stroke or {}).get("first_failed_station") or "stroke reachable"),
                                     "raw": stroke}
        if steps.get("stroke_reach", {}).get("result") == fa.PASSED:
            self._progress("authoritative PreEntry check")
            steps["preentry"] = self.preentry()
            steps["preentry"]["audit"] = [self.audit_state(s["joints_si"], cand_dir / "audit-d", f"preentry-seed{s['seed']}")
                                          for s in steps["preentry"]["seeds"] if isinstance(s.get("joints_si"), dict)]
        if steps.get("preentry", {}).get("result") == fa.PASSED:
            self._progress("adaptive-corridor clearance")
            steps["corridor"] = self.corridor()
            blocked = steps["corridor"].get("first_blocked_state")
            if isinstance(blocked, dict):
                steps["corridor"]["audit"] = self.audit_state(blocked, cand_dir / "audit-d", "corridor-first-blocked")
        if steps.get("corridor", {}).get("result") == fa.PASSED:
            self._progress("full Diagnose P1-P3")
            steps["diagnose"] = self.diagnose(cand_dir / "evidence", f"FDI{self.target_fdi} {label}")
        steps["moveit_padding"] = self._moveit_padding()
        return self._finish(stage, state, steps, identity, cand_dir)

    def _finish(self, stage, state, steps, identity, cand_dir) -> dict:
        padding = steps.pop("moveit_padding", None)
        record = fa.candidate_record(stage, state, self.baseline, steps, identity=identity, evidence_dir=str(cand_dir))
        record["moveit_padding"] = padding
        return self._store(record, cand_dir)

    def _store(self, record, cand_dir) -> dict:
        cand_dir.mkdir(parents=True, exist_ok=True)
        (cand_dir / "candidate.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
        if record.get("result") != fa.UNTESTED and record.get("identity"):
            self.store.append(record)
        self.records.append(record)
        self.write_report()
        return record

    def write_report(self, notes=(), extra_untested=()):
        (self.out / "advisor-ordered-report.md").write_text(
            fa.ordered_report_markdown(self.baseline, self.records, self.limits,
                                       extra_untested=extra_untested, notes=notes), encoding="utf-8")
        self._write("advisor-ordered-records.json", self.records)

    def confirm(self, stage: str, state: dict, *, notes=(), extra_untested=()) -> dict:
        """Evaluate exactly ONE candidate, capture its first failure completely, stop."""
        self._progress(f"confirmation {fa.state_delta(state, self.baseline)}")
        record = self.evaluate(stage, state)
        self.write_report(notes=notes, extra_untested=extra_untested)
        self._progress(f"done: {record.get('result')} ({record.get('failed_step') or 'all steps'})")
        return record
