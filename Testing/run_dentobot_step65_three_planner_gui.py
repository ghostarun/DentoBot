"""Opt-in, simulation-only Step 6.5 three-planner GUI comparison on one prepared target.

Requires a current package with an eligible PreparedBranch for DENTOBOT_FDI.
No base/Home repair, geometry change, guard bypass, preview, or hardware action.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

import qt
import slicer
import vtk

ROOT = Path("/workspace/ros2_ws/src/DentoBot")
sys.path.insert(0, str(ROOT / "DENTOWorkflow/Resources/Python"))
from DENTOCaseBundle import validate_case_bundle  # noqa: E402
from DENTOStep6State import PLANNER_COMPARISON_IDS, parse_planner_comparison  # noqa: E402

SOURCE = Path(os.environ["DENTOBOT_CASE_SOURCE"])
OUTPUT = Path(os.environ["DENTOBOT_EVIDENCE_DIR"])
FDI = os.environ["DENTOBOT_FDI"]
SAVED = OUTPUT / f"FDI{FDI}-three-planner.dentocase"
RECAPTURED = OUTPUT / f"FDI{FDI}-current-profile-home.dentocase"
REOPEN_ONLY = os.environ.get("DENTOBOT_REOPEN_ONLY") == "1"
TRACE_START_NS = time.monotonic_ns()
TRACE_SEQUENCE = 0
CURRENT = {"planner_id": "setup"}


def trace_event(event, **details):
    global TRACE_SEQUENCE
    TRACE_SEQUENCE += 1
    now = time.monotonic_ns()
    record = {
        "sequence": TRACE_SEQUENCE,
        "event": event,
        "utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": (now - TRACE_START_NS) / 1e9,
        "planner_id": CURRENT["planner_id"],
        **details,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "timeline.jsonl").open("a") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def trace_method(owner, name, phase):
    original = getattr(owner, name)
    call_number = 0

    def timed(*args, **kwargs):
        nonlocal call_number
        call_number += 1
        call_id = f"{phase}-{call_number}"
        context = str(kwargs.get("planner_context") or "")
        if phase == "trial":
            CURRENT["planner_id"] = str(kwargs.get("planner_id") or "unknown")
        if phase == "chain_preflight" and len(args) > 2:
            context = "roll_deg=" + str(args[2].get("rollDeg"))
        if phase == "guard_waypoints" and args:
            context = f"{len(args[0])} waypoints"
        start = time.monotonic_ns()
        trace_event("phase_start", phase=phase, call_id=call_id, context=context)
        result = None
        try:
            result = original(*args, **kwargs)
            return result
        except Exception as exc:
            trace_event("phase_error", phase=phase, call_id=call_id,
                        error=str(exc)[:400])
            raise
        finally:
            trace_event("phase_end", phase=phase, call_id=call_id,
                        duration_s=(time.monotonic_ns() - start) / 1e9,
                        success=getattr(result, "success", None),
                        status=result.get("status") if isinstance(result, dict) else None)
            if phase == "trial":
                CURRENT["planner_id"] = "between_trials"

    setattr(owner, name, timed)


def placement_review(attempt):
    session = attempt.get("session") or {}
    failed = next((item for item in session.get("stage_outcomes", ())
                   if item.get("status") == "Failed"), {})
    stage = str(failed.get("stage") or "unknown")
    reason = str(failed.get("reason") or attempt.get("message") or "")
    if not session:
        conclusion = "No diagnostic session; base/Home causality cannot be assessed."
    elif "preentry_ik" in stage or "preentry_ik" in reason.lower():
        conclusion = ("Base reach/orientation and Home-dependent IK seeds are plausible; "
                      "neither is proven without one controlled change.")
    elif "stage1" in stage:
        conclusion = ("Task Home and base-mount clearance may affect Home→PreEntry; "
                      "compare endpoint validity and the first collision before adjusting either.")
    elif "stage2" in stage or "stage3" in stage:
        conclusion = ("Changing Home can alter selected branches, and base placement may expose "
                      "another reachable tool frame; neither directly fixes a collision at the "
                      "same TCP frame. Compare fixed frame, pair, and pose first.")
    else:
        conclusion = "First blocker is not classified; no base/Home fix is inferred."
    return {"first_failed_stage": stage, "first_blocker": reason,
            "assessment": conclusion, "verdict": "hypothesis only; no placement changed"}


def collision_record(attempt):
    session = attempt.get("session") or {}
    records = session.get("candidate_records") or ()
    selected = session.get("selected_candidate_index")
    return next((item for item in records
                 if item.get("candidate_index") == selected
                 and item.get("first_invalid_joint_positions_si")
                 and item.get("guard_first_body") and item.get("guard_second_body")), None)


def bounds_overlap(first, second):
    return all(first[2*i] <= second[2*i+1] and second[2*i] <= first[2*i+1]
               for i in range(3))


def collision_views(facade, attempt, stem):
    """Render the selected first-invalid state; native guard text remains authority."""
    record = collision_record(attempt)
    if record is None:
        return {"images": [], "unavailable_reason": "No selected first-invalid collision state/pair."}
    pair = [record["guard_first_body"], record["guard_second_body"]]
    shown, reason = facade._bridge.show_goal_robot_joint_positions(
        record["first_invalid_joint_positions_si"])
    if not shown:
        return {"images": [], "pair": pair, "unavailable_reason": str(reason)}
    nodes = slicer.util.getNodesByClass("vtkMRMLModelNode")
    target = next((node for node in nodes
                   if node.GetAttribute("DENTOBOT.CollisionAuditCopy") == "true"
                   and node.GetAttribute("DENTOBOT.OutgoingCollisionObjectId") in pair), None)
    spindle = next((node for node in nodes if "pneumatic-spindle-copy_model_0_goal"
                    in str(node.GetName() or "").lower()
                    or "pneumatic_spindle-copy_model_0_goal"
                    in str(node.GetName() or "").lower()), None)
    if target is None or spindle is None:
        return {"images": [], "pair": pair,
                "unavailable_reason": "Collision audit target or display-only goal spindle is missing."}
    target_bounds = [0.0] * 6
    spindle_bounds = [0.0] * 6
    target.GetRASBounds(target_bounds)
    spindle.GetRASBounds(spindle_bounds)
    if not bounds_overlap(target_bounds, spindle_bounds):
        return {"images": [], "pair": pair,
                "unavailable_reason": "Native/display mismatch: reconstructed pair bounds do not overlap.",
                "target_bounds_world_ras_mm": target_bounds,
                "spindle_bounds_world_ras_mm": spindle_bounds}
    layout = slicer.app.layoutManager()
    old_layout = layout.layout
    layout.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView)
    view = layout.threeDWidget(0).threeDView()
    camera = view.cameraNode().GetCamera()
    camera_state = (camera.GetPosition(), camera.GetFocalPoint(), camera.GetViewUp(),
                    camera.GetParallelProjection(), camera.GetParallelScale())
    displays = [(node.GetDisplayNode(), node.GetDisplayNode().GetVisibility())
                for node in slicer.util.getNodesByClass("vtkMRMLDisplayableNode")
                if node.GetDisplayNode() is not None]
    images = []
    try:
        for display, _ in displays:
            display.SetVisibility(False)
        target.GetDisplayNode().SetVisibility(True)
        spindle.GetDisplayNode().SetVisibility(True)
        bounds = [0.0] * 6
        target.GetRASBounds(bounds)
        center = [(bounds[2*i] + bounds[2*i+1]) / 2.0 for i in range(3)]
        span = max(bounds[1]-bounds[0], bounds[3]-bounds[2], bounds[5]-bounds[4], 5.0)
        for label, direction, up in (
            ("bottom-inferior", (0, 0, -1), (0, 1, 0)),
            ("root-apical", (0, 0, 1), (0, 1, 0)),
            ("palatal-oblique", (0, 0.75, -0.66), (0, 0.66, 0.75)),
        ):
            camera.SetFocalPoint(*center)
            camera.SetPosition(*(center[i] + 1.7 * span * direction[i] for i in range(3)))
            camera.SetViewUp(*up)
            camera.SetParallelProjection(True)
            camera.SetParallelScale(0.65 * span)
            view.forceRender()
            events()
            path = OUTPUT / f"{stem}-collision-{label}.png"
            require(view.grab().save(str(path)), f"collision screenshot failed: {path}")
            images.append(str(path))
            trace_event("collision_view_saved", path=str(path), pair=pair, angle=label)
    finally:
        for display, visibility in displays:
            display.SetVisibility(visibility)
        camera.SetPosition(*camera_state[0])
        camera.SetFocalPoint(*camera_state[1])
        camera.SetViewUp(*camera_state[2])
        camera.SetParallelProjection(camera_state[3])
        camera.SetParallelScale(camera_state[4])
        layout.setLayout(old_layout)
    return {"images": images, "pair": pair,
            "joint_positions_si": record["first_invalid_joint_positions_si"],
            "scope": "Display-only first-invalid pose; native collision pair is authoritative."}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def events(seconds=0.2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def screenshot(name):
    path = OUTPUT / f"{name}.png"
    window = slicer.util.mainWindow()
    window.show()
    dialog = getattr(slicer.util.getModuleWidget("DENTOWorkflow")._robotSimulationPanel,
                     "_plannerComparisonDialog", None)
    if dialog is not None and dialog.isVisible():
        dialog.raise_()
        dialog.activateWindow()
    events()
    host = dialog if dialog is not None and dialog.isVisible() else window
    require(host.grab().save(str(path)), f"screenshot failed: {path}")
    trace_event("screenshot_saved", path=str(path))
    return str(path)


def success(result, label):
    require(result.success, f"{label}: {result.message}")


def placement_evidence(parameter, logic):
    matrix = vtk.vtkMatrix4x4()
    require(parameter.robotBaseTransform.GetMatrixTransformToWorld(matrix),
            "robot base transform cannot be resolved in world coordinates")
    home = logic.taskHomeRecord(parameter)
    require(home is not None, "Task Home evidence is missing")
    return {
        "base_world_ras_matrix": [[matrix.GetElement(i, j) for j in range(4)] for i in range(4)],
        "home_joints_si": dict(zip(home.joint_names, home.joint_positions_si)),
        "home_audit_fingerprint": home.collision_audit_fingerprint,
    }


def run():
    trace_event("run_start", fdi=FDI, source=str(SOURCE))
    require(FDI.isdigit() and len(FDI) == 2, "DENTOBOT_FDI must be a two-digit tooth code")
    require(SOURCE.is_file(), f"source package missing: {SOURCE}")
    require(not SAVED.exists(), f"refusing to overwrite: {SAVED}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    validate_case_bundle(SOURCE)
    trace_event("source_validated")
    slicer.util.selectModule("DENTOWorkflow")
    events(0.5)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget._openCaseBundle(str(SOURCE))
    trace_event("case_opened")
    events(0.5)
    parameter = widget._parameterNode
    logic = widget.logic
    registry = logic.syncDentoCaseTrajectoryRegistry(parameter)
    slots = registry["teeth"].get("FDI" + FDI, {}).get("trajectory_set", {}).get("slots", ())
    branches = [bid for slot in slots for bid in slot.get("prepared_branch_ids", ())]
    require(branches, f"FDI{FDI} has no PreparedBranch in this package")
    branch = next((bid for bid in branches if logic.evaluatePreparedBranchEligibility(parameter, bid)["eligible"]), None)
    require(branch, f"FDI{FDI} has no eligible PreparedBranch")
    trace_event("branch_selected", branch_id=branch)

    widget._setWorkflowStage(9, ensureVisible=True)
    widget._updateTemplateFinalization()
    selector = widget.ui.finalVerificationModelSelector
    index = next((i for i in range(1, selector.count) if "FDI" + FDI in str(selector.itemText(i))), -1)
    require(index > 0, f"FDI{FDI} is missing from the Step 5C guide selector")
    selector.setCurrentIndex(index)
    events()
    require(widget.ui.verifyFinalTemplateButton.enabled, "Step 5C verification disabled")
    widget.ui.verifyFinalTemplateButton.click()
    events(0.5)
    require(logic.evaluatePreparedBranchEligibility(parameter, branch)["eligible"], "Step 5C verification failed")
    trace_event("step5c_verified")
    widget._setWorkflowStage(10, ensureVisible=True)
    widget._updateStep6PlanningUi()
    require(widget.ui.importStep6PlanningContextButton.enabled, "Step 6A activation disabled")
    widget.ui.importStep6PlanningContextButton.click()
    events(0.5)
    require(parameter.step6PlanningContextImported, "Step 6A did not activate the branch")
    trace_event("step6a_activated")

    facade = widget._robotWorkflowFacade
    success(facade.loadRobot(), "load local MRML robot")
    connection = facade.connect(open_motion_module=False)
    require(connection.success, f"ROS/MoveIt connection failed: {connection.message}")
    trace_event("ros_connected")
    require(logic.taskHomeRecord(parameter) is not None, "no saved Task Home; no automatic replacement")
    home_issues = logic.taskHomeFreshnessIssues(parameter)
    recaptured = False
    if home_issues:
        require(home_issues == ("Task Home belongs to different robot resources.",),
                f"Task Home has an unrelated stale condition: {home_issues}")
        require(not RECAPTURED.exists(), f"refusing to overwrite: {RECAPTURED}")
        success(facade.saveTaskHome(), "recapture strict-guarded current-profile Task Home")
        recaptured = True
    if not facade.taskHomeRuntimeValidated(parameter):
        success(facade.applyTaskHome(), "validate saved Task Home")
    trace_event("task_home_validated")
    if not facade.workspaceRuntimeValidated(parameter):
        success(facade.generateWorkspaceCloud(), "regenerate workspace")
        success(facade.reviewAssistedLimits(), "review workspace limits")
    trace_event("workspace_validated")
    if logic.confirmedTaskRecord(parameter) is None or logic.confirmedTaskFreshnessIssues(parameter):
        success(facade.confirmTask(), "confirm current task")
    require(logic.confirmedTaskRecord(parameter) is not None, "task snapshot is not current")
    trace_event("task_confirmed")
    if recaptured:
        recapture_inspection = widget._createCaseBundle(RECAPTURED)
        validate_case_bundle(recapture_inspection.path)
    panel = widget._robotSimulationPanel
    widget._configureRobotSimulationShellSubstep(1)
    widget._updateStep6PlanningUi()
    images = [screenshot(f"FDI{FDI}-base-runtime")]
    widget._configureRobotSimulationShellSubstep(2)
    widget._updateStep6PlanningUi()
    images.append(screenshot(f"FDI{FDI}-task-home"))
    placement = placement_evidence(parameter, logic)
    widget._configureRobotSimulationShellSubstep(5)
    panel.setActiveSubstep(5)
    widget._updateStep6PlanningUi()
    require(panel.comparePlannersButton.enabled, "Step 6.5 comparison is gated")
    identity = facade.plannerComparisonIdentity()
    require(identity["branch_id"] == branch, "comparison selected the wrong branch")
    trace_event("comparison_ready", identity=identity, placement_evidence=placement,
                planning_policy=panel.planningPolicy())
    for owner, name, phase in (
        (facade, "planApproachPhase", "trial"),
        (facade, "_prepare_phase_guard", "scene_and_guard_setup"),
        (facade, "_goal1_pre_entry_ik_candidates", "preentry_ik"),
        (facade, "_goal1_clearance_waypoints", "clearance_candidates"),
        (facade, "_goal1_candidate_chain_preflight", "chain_preflight"),
        (facade._bridge, "plan_moveit_joint_goal", "joint_plan"),
        (facade._bridge, "diagnose_moveit_joint_segment", "joint_segment_diagnostic"),
        (facade._bridge, "plan_moveit_cartesian_path", "cartesian_plan"),
        (facade._bridge, "validate_task_phase_waypoints", "guard_waypoints"),
    ):
        trace_method(owner, name, phase)
    captured = set()
    collision_evidence = {}
    save_progress = widget._savePlannerComparisonProgress

    def save_and_capture_progress():
        save_progress()
        state = widget._plannerComparisonState
        if state is None:
            return
        for row, attempt in enumerate(state["attempts"]):
            if attempt["status"] == "NotRun" or row in captured:
                continue
            widget._onStep6ShowPlannerComparison()
            dialog = getattr(panel, "_plannerComparisonDialog", None)
            require(dialog is not None and dialog.isVisible(), "comparison dialog was not shown")
            table = dialog.findChild(qt.QTableWidget)
            require(table is not None, "comparison table is missing")
            table.selectRow(row)
            image = screenshot(f"FDI{FDI}-{('rrtconnect', 'rrt', 'rrtstar')[row]}-diagnostic")
            dialog.close()
            images.append(image)
            captured.add(row)
            reviews = [placement_review(item) for item in state["attempts"]]
            try:
                collision = collision_views(facade, attempt,
                                            f"FDI{FDI}-{('rrtconnect', 'rrt', 'rrtstar')[row]}")
            except Exception as exc:
                collision = {"images": [], "unavailable_reason": f"{type(exc).__name__}: {exc}"}
            collision_evidence[attempt["planner_id"]] = collision
            images.extend(collision["images"])
            if "collision" in reviews[row]["first_blocker"].lower() and not collision["images"]:
                state["cancel"] = True
                trace_event("collision_capture_unavailable", row=row,
                            reason=collision.get("unavailable_reason", "unknown"))
            (OUTPUT / "checkpoint.json").write_text(json.dumps({
                "identity": identity, "placement_evidence": placement,
                "attempts": state["attempts"], "placement_reviews": reviews,
                "screenshots": images, "collision_evidence": collision_evidence,
            }, indent=2, sort_keys=True) + "\n")
            trace_event("trial_checkpoint_saved", row=row, planner_id=attempt["planner_id"],
                        status=attempt["status"], screenshot=image,
                        first_failed_stage=reviews[row]["first_failed_stage"])

    widget._savePlannerComparisonProgress = save_and_capture_progress
    panel.comparePlannersButton.click()
    deadline = time.monotonic() + 900
    while getattr(widget, "_plannerComparisonState", None) and time.monotonic() < deadline:
        events(0.1)
    require(not getattr(widget, "_plannerComparisonState", None), "comparison timed out")
    record = parse_planner_comparison(parameter.step6PlannerComparisonJson)
    entry = record["branches"][branch]
    require(tuple(row["planner_id"] for row in entry["attempts"]) == PLANNER_COMPARISON_IDS,
            "planner order changed")
    require(entry["identity"] == identity, "comparison identity changed")
    require(not facade.motionPlan, "comparison incorrectly retained a guarded plan")
    require(len(captured) == 3, "the three planner screenshots were not captured")
    require(all(row["status"] != "NotRun" and row.get("session") is not None
                for row in entry["attempts"]), "one or more planners did not reach a diagnostic trial")
    require(facade.taskHomeRuntimeValidated(parameter), "comparison invalidated current Task Home")
    inspection = widget._createCaseBundle(SAVED)
    validate_case_bundle(inspection.path)
    result = {
        "fdi": FDI, "source": str(SOURCE), "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "branch_id": branch, "comparison": entry, "placement_evidence": placement,
        "placement_reviews": [placement_review(item) for item in entry["attempts"]],
        "recaptured_case": str(RECAPTURED) if recaptured else None,
        "saved_case": str(inspection.path),
        "saved_sha256": hashlib.sha256(inspection.path.read_bytes()).hexdigest(), "screenshots": images,
        "runtime_verdict": "diagnostic-only; operator review required",
    }
    (OUTPUT / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    trace_event("case_and_report_saved", case=str(inspection.path))
    print("DENTOBOT_THREE_PLANNER_GUI_RECORDED " + str(OUTPUT / "result.json"), flush=True)


def reopen():
    """Run in a fresh Slicer process, with no ROS connection or planner call."""
    trace_event("reopen_start", source=str(SOURCE))
    require(SOURCE.is_file(), f"saved comparison package missing: {SOURCE}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    validate_case_bundle(SOURCE)
    slicer.util.selectModule("DENTOWorkflow")
    events(0.5)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget._openCaseBundle(str(SOURCE))
    events(0.5)
    parameter = widget._parameterNode
    record = parse_planner_comparison(parameter.step6PlannerComparisonJson)
    registry = json.loads(parameter.step6TrajectoryRegistryJson)
    branch = registry["selected_branch_id"]
    require(branch in record["branches"], "selected PreparedBranch has no saved comparison")
    require(tuple(row["planner_id"] for row in record["branches"][branch]["attempts"]) == PLANNER_COMPARISON_IDS,
            "saved three-row report changed")
    require(not widget._robotWorkflowFacade.capabilities().connected, "offline reopen restored ROS authority")
    require(not widget._robotWorkflowFacade.motionPlan, "offline reopen restored a guarded plan")
    widget._setWorkflowStage(10, ensureVisible=True)
    widget._robotSimulationPanel.setActiveSubstep(5)
    widget._updateStep6PlanningUi()
    require(widget._robotSimulationPanel.showPlannerComparisonButton.enabled, "saved report not inspectable")
    widget._robotSimulationPanel.showPlannerComparisonButton.click()
    events()
    image = screenshot(f"FDI{FDI}-reopened-comparison")
    result = {"status": "OFFLINE_REOPEN_PASS", "source": str(SOURCE), "branch_id": branch,
              "screenshots": [image], "guarded_plan_restored": False, "ros_connected": False}
    (OUTPUT / "reopen-result.json").write_text(json.dumps(result, indent=2) + "\n")
    trace_event("reopen_verified")
    print("DENTOBOT_THREE_PLANNER_REOPEN_PASS " + str(OUTPUT / "reopen-result.json"), flush=True)


try:
    reopen() if REOPEN_ONLY else run()
    slicer.util.exit(0)
except Exception as exc:
    trace_event("run_failed", error=str(exc)[:400])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "failure.json").write_text(json.dumps({"error": str(exc)}, indent=2) + "\n")
    print("DENTOBOT_THREE_PLANNER_GUI_FAILED: " + str(exc), file=sys.stderr, flush=True)
    slicer.util.exit(1)
