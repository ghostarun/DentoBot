"""Explicit saved-case simulation check, with opt-in historical x4 diagnosis.

This test restores the operator's x4 case, reconstructs only transient ROS 2
state, and exercises planning plus guarded preview.  It never exposes or calls
hardware execution.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import traceback
from pathlib import Path

import slicer
import vtk

EXPLICIT_CASE = os.environ.get("DENTOBOT_EXACT_CASE", "")
if not EXPLICIT_CASE and os.environ.get("DENTOBOT_ENABLE_HISTORICAL_X4_DIAGNOSTIC") != "1":
    raise RuntimeError(
        "Retired pre-surgery x4 fixture: select a reviewed clean case for acceptance. "
        "Historical diagnosis requires DENTOBOT_ENABLE_HISTORICAL_X4_DIAGNOSTIC=1."
    )

ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
MODULE = ROOT / "DENTOWorkflow"
for path in (HELPERS, MODULE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import DENTOROS2Bridge as bridge  # noqa: E402
from DENTOTemplateGeometry import model_polydata_in_world  # noqa: E402


if EXPLICIT_CASE and any(os.environ.get(name, "") == "1" for name in (
    "DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE",
    "DENTOBOT_ENABLE_HISTORICAL_ANATOMY_REVIEW",
    "DENTOBOT_AUDIT_ACTUAL_CONTACT_ONLY",
    "DENTOBOT_PLAN_ONLY",
    "DENTOBOT_GOAL1_ONLY",
    "DENTOBOT_FOCUSED_STAGE3_DIAG",
)):
    raise RuntimeError("Explicit full-case run cannot use historical overrides or partial-run modes.")

PACKAGE = Path(EXPLICIT_CASE or (
    "/workspace/data/Slicer_Saved/SampleStudy1/"
    "dentobot-case-step6x4.dentocase"
))
EXPECTED_TASK = "39201d8f79a4a9ebee2290dfe7f2f37415123187b8b654aee038dba27584c27c"
PREVIEW_TIMEOUT_SEC = float(os.environ.get("DENTOBOT_PREVIEW_TIMEOUT_SEC", "240"))
BASE_LOCAL_Z_OFFSET_MM = float(
    os.environ.get("DENTOBOT_BASE_LOCAL_Z_OFFSET_MM", "0")
)


def process_events(seconds: float = 0.25) -> None:
    deadline = time.monotonic() + float(seconds)
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        ros_logic = slicer.util.getModuleLogic("ROS2")
        if ros_logic is not None:
            ros_logic.Spin()
        time.sleep(0.01)


def wait_until(predicate, timeout_sec: float):
    deadline = time.monotonic() + float(timeout_sec)
    while time.monotonic() < deadline:
        process_events(0.05)
        result = predicate()
        if result:
            return result
    return None


def require_success(result, stage: str):
    if not result.success:
        details = json.dumps(result.details, sort_keys=True, default=str)
        raise RuntimeError(f"{stage}: {result.message}; details={details}")
    return result


def base_point_m_to_world_ras_mm(point, base_transform):
    if point is None:
        return None
    matrix = vtk.vtkMatrix4x4()
    if base_transform.GetMatrixTransformToWorld(matrix) is False:
        return None
    source = [1000.0 * float(value) for value in point] + [1.0]
    target = [0.0, 0.0, 0.0, 0.0]
    matrix.MultiplyPoint(source, target)
    return [float(target[index]) for index in range(3)]


def capture_fdi21_contact_from_below(facade, diagnostic_payload):
    """Capture the isolated FDI21/spindle rejection from useful viewpoints."""

    records = diagnostic_payload.get("candidate_records", ())
    record = next(
        (
            item for item in records
            if isinstance(item, dict)
            and "71ddde60" in str(item.get("full_chain_guard_message") or "")
            and isinstance(item.get("first_invalid_joint_positions_si"), dict)
        ),
        None,
    )
    if record is None:
        raise RuntimeError("No retained FDI21/spindle rejected waypoint is available.")
    shown, message = facade._bridge.show_goal_robot_joint_positions(
        record["first_invalid_joint_positions_si"]
    )
    if not shown:
        raise RuntimeError("show rejected FDI21 state: " + message)

    fdi21_id = str(record.get("guard_first_body") or "")
    target_id = facade._logic.step6TargetCollisionObjectId(facade._require_context())
    for node in slicer.util.getNodesByClass("vtkMRMLDisplayableNode"):
        display = node.GetDisplayNode()
        if display is not None:
            display.SetVisibility(False)
    for node in slicer.util.getNodesByClass("vtkMRMLSliceNode"):
        node.SetSliceVisible(False)

    visible = []
    focus_nodes = []
    fdi21_node = None
    spindle_node = None
    for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
        display = node.GetDisplayNode()
        if display is None:
            continue
        display.SetVisibility(False)
        object_id = str(node.GetAttribute("DENTOBOT.OutgoingCollisionObjectId") or "")
        name = str(node.GetName() or "").lower()
        if node.GetAttribute("DENTOBOT.CollisionAuditCopy") == "true" and object_id == fdi21_id:
            display.SetVisibility(True); display.SetColor(1.0, 0.05, 0.05); display.SetOpacity(0.55)
            display.SetEdgeVisibility(True); display.SetEdgeColor(0.35, 0.0, 0.0); visible.append(node); focus_nodes.append(node)
            fdi21_node = node
        elif node.GetAttribute("DENTOBOT.CollisionAuditCopy") == "true" and object_id == target_id:
            display.SetVisibility(True); display.SetColor(0.1, 0.9, 0.2); display.SetOpacity(0.12)
            display.SetEdgeVisibility(True); display.SetEdgeColor(0.0, 0.35, 0.0); visible.append(node); focus_nodes.append(node)
        elif "pneumatic-spindle-copy_model_0_goal" in name or "pneumatic_spindle-copy_model_0_goal" in name:
            display.SetVisibility(True); display.SetColor(1.0, 0.45, 0.0); display.SetOpacity(0.6)
            display.SetEdgeVisibility(True); display.SetEdgeColor(0.35, 0.12, 0.0); visible.append(node)
            spindle_node = node
        elif "burr_model_0_goal" in name:
            display.SetVisibility(True); display.SetColor(1.0, 1.0, 0.0); display.SetOpacity(1.0)
            visible.append(node)
    if len(visible) < 3:
        raise RuntimeError("Could not isolate FDI21, FDI11, and the rejected spindle model.")

    intersection = vtk.vtkIntersectionPolyDataFilter()
    intersection.SetInputData(0, model_polydata_in_world(fdi21_node))
    intersection.SetInputData(1, model_polydata_in_world(spindle_node))
    intersection.Update()
    if intersection.GetOutput().GetNumberOfPoints() > 0:
        contact = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "FDI21 spindle mesh intersection")
        contact.SetAndObservePolyData(intersection.GetOutput())
        contact.CreateDefaultDisplayNodes()
        contact.GetDisplayNode().SetColor(1.0, 1.0, 0.0)
        contact.GetDisplayNode().SetLineWidth(8.0)
        contact.GetDisplayNode().SetVisibility(True)

    layout = slicer.app.layoutManager()
    layout.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView)
    process_events(0.5)
    view = layout.threeDWidget(0).threeDView()
    view.mrmlViewNode().SetAxisLabelsVisible(False)
    camera = view.cameraNode().GetCamera()
    bounds = [float("inf"), float("-inf"), float("inf"), float("-inf"), float("inf"), float("-inf")]
    for node in focus_nodes:
        current = [0.0] * 6
        node.GetRASBounds(current)
        for axis in range(3):
            bounds[2 * axis] = min(bounds[2 * axis], current[2 * axis])
            bounds[2 * axis + 1] = max(bounds[2 * axis + 1], current[2 * axis + 1])
    center = [(bounds[2*i] + bounds[2*i+1]) / 2.0 for i in range(3)]
    distance = max(bounds[1]-bounds[0], bounds[3]-bounds[2], bounds[5]-bounds[4]) * 1.7
    output = Path("/workspace/data/dentobot-runs/fdi21-blocker-20260909")
    output.mkdir(parents=True, exist_ok=True)
    views = {
        "bottom-inferior": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
        "root-apical": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
        "palatal-bottom-oblique": ((0.0, 0.75, -0.66), (0.0, 0.66, 0.75)),
    }
    screenshots = []
    for label, (direction, view_up) in views.items():
        camera.SetFocalPoint(*center)
        camera.SetPosition(*(center[i] + distance * direction[i] for i in range(3)))
        camera.SetViewUp(*view_up)
        camera.SetParallelProjection(True)
        camera.SetParallelScale(distance * 0.36)
        view.forceRender(); process_events(0.2)
        path = output / f"fdi21-contact-{label}.png"
        slicer.util.forceRenderAllViews()
        pixmap = view.grab()
        if not pixmap.save(str(path)):
            raise RuntimeError(f"Could not save {path}")
        screenshots.append(str(path))
    print("DENTOBOT_FDI21_BOTTOM_CAPTURE_PASS " + json.dumps({
        "candidate_index": record.get("candidate_index"),
        "collision_pair": [record.get("guard_first_body"), record.get("guard_second_body")],
        "screenshots": screenshots,
    }), flush=True)
    return screenshots


def preview_repeat_phase(facade, phase: str, waypoint_count: int):
    """Run one acknowledged repeat preview and retain bounded failure context."""

    finished = []
    progress = []
    require_success(
        facade.previewPhase(
            phase,
            interval_ms=50,
            on_progress=lambda index, total: progress.append((int(index), int(total))),
            on_finished=finished.append,
        ),
        f"start repeated {phase} preview",
    )
    if wait_until(lambda: finished, PREVIEW_TIMEOUT_SEC) is None:
        raise RuntimeError(
            f"Repeated {phase} preview timed out at "
            f"{progress[-1] if progress else (0, waypoint_count)}; "
            f"previewActive={facade.previewActive}, sequence={facade._phase_sequence}, "
            f"lastGuardStatus={bridge._last_task_status}"
        )
    return require_success(finished[-1], f"repeat {phase} preview")


def audit_actual_moveit_contacts(facade, diagnostic_payload: dict[str, object]):
    """Audit retained candidate paths without the separate 1 mm phase margin.

    This is intentionally a harness-only diagnostic.  It asks MoveIt to check
    each already-generated explicit joint state against its synchronized scene;
    it neither applies a waypoint nor starts guarded preview.  The normal
    Step-6 phase guard is deliberately *not* called here because its provisional
    non-target-tooth clearance envelope is the condition being classified.
    """

    records = diagnostic_payload.get("candidate_records", ())
    if not isinstance(records, list):
        records = ()
    outcomes = []
    for candidate_index, paths in sorted(facade._diagnostic_candidate_paths.items()):
        record = (
            records[candidate_index]
            if 0 <= int(candidate_index) < len(records)
            and isinstance(records[candidate_index], dict)
            else {}
        )
        stages = {}
        for stage in ("stage1", "stage2", "stage3"):
            waypoints = tuple(paths.get(stage, ()))
            valid_count = 0
            first_invalid = None
            for waypoint_index, positions in enumerate(waypoints):
                valid, message, authoritative = bridge.check_moveit_static_joint_state(
                    positions,
                    timeout_sec=2.0,
                )
                if not authoritative or not valid:
                    first_invalid = {
                        "waypoint_index": waypoint_index,
                        "authoritative": authoritative,
                        "message": message,
                    }
                    break
                valid_count += 1
            stages[stage] = {
                "waypoint_count": len(waypoints),
                "moveit_actual_mesh_valid_count": valid_count,
                "first_moveit_actual_mesh_invalid": first_invalid,
                "all_moveit_actual_mesh_valid": (
                    bool(waypoints) and first_invalid is None
                ),
            }
        outcomes.append(
            {
                "candidate_index": int(candidate_index),
                "route_type": record.get("route_type"),
                "ik_seed_sample_index": record.get("ik_seed_sample_index"),
                "housing_roll_deg": record.get("axial_roll_deg"),
                "full_chain_status": record.get("full_chain_candidate_status"),
                "stage2_fraction": record.get("stage2_fraction"),
                "stage3_fraction": record.get("stage3_fraction"),
                "phase_guard_margin_first_body": record.get("guard_first_body"),
                "phase_guard_margin_second_body": record.get("guard_second_body"),
                "phase_guard_minimum_distance_mm": (
                    None
                    if record.get("guard_minimum_world_distance_m") is None
                    else 1000.0 * float(record["guard_minimum_world_distance_m"])
                ),
                "stages": stages,
            }
        )
    return outcomes


def run() -> dict[str, object]:
    if not PACKAGE.is_file():
        raise RuntimeError(f"exact operator package is missing: {PACKAGE}")
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    if widget is None:
        raise RuntimeError("DENTOWorkflow widget is unavailable")
    widget._applyDENTOBOTGuiMode("legacy", persist=False)
    widget._openCaseBundle(PACKAGE)
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    parameter_node = widget._parameterNode
    logic = widget.logic
    facade = widget._robotWorkflowFacade
    if parameter_node is None or logic is None or facade is None:
        raise RuntimeError("restored Step 6 workflow services are unavailable")
    if slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"):
        raise RuntimeError("the package serialized a transient ROS robot")
    package_issues = logic.step6PlanningPackageFreshnessIssues(parameter_node)
    jaw_issues = logic.step6CaseJawOpeningFreshnessIssues(parameter_node)
    home_issues = logic.taskHomeFreshnessIssues(parameter_node)
    # The historical x4 fixture predates the five-DOF/canonical-TCP robot
    # profile.  Its geometry and base remain valid, but its persisted Home is
    # expected to be stale at this migration boundary.  Exercise the explicit
    # live revalidation path below instead of misclassifying that expected
    # fingerprint change as a package-integrity failure.
    migration_home_issues = tuple(
        issue for issue in home_issues if "different robot resources" in str(issue).lower()
    )
    blocking_home_issues = tuple(
        issue for issue in home_issues if issue not in migration_home_issues
    )
    task_issues = logic.confirmedTaskFreshnessIssues(parameter_node)
    # A saved task snapshot may intentionally become stale after a robot-profile
    # migration (for example the J2/J5 URDF update).  Geometry/jaw/home
    # corruption is still a hard restore failure, but the immutable snapshot
    # is expected to be explicitly reconfirmed after the live runtime is
    # reconstructed below.
    if package_issues or jaw_issues or blocking_home_issues:
        raise RuntimeError(
            "restored x4 prerequisites are stale: "
            + " | ".join(
                " ".join(group)
                for group in (package_issues, jaw_issues, blocking_home_issues)
                if group
            )
        )
    restored_snapshot = logic.confirmedTaskRecord(parameter_node)
    restored_task_before_runtime = (
        restored_snapshot.snapshot_fingerprint if restored_snapshot is not None else ""
    )
    if not parameter_node.robotBaseMountLocked:
        raise RuntimeError("restored x4 robot base is not provisionally locked")

    require_success(facade.loadRobot(), "load local robot")
    if abs(BASE_LOCAL_Z_OFFSET_MM) > 1.0e-12:
        require_success(facade.unlockBase(), "unlock base for diagnostic offset")
        logic.nudgeRobotBase(
            parameter_node.robotBaseTransform,
            translationLocalMm=(0.0, 0.0, BASE_LOCAL_Z_OFFSET_MM),
        )
        # Let the placement observer consume the pose change while the base is
        # still intentionally unlocked.  Locking before this event is handled
        # can make the observer correctly treat the delayed change as stale.
        process_events(0.25)
        # The normal-window operator naturally leaves an event-loop turn
        # between clicking Nudge and Lock.  The headless harness must make the
        # placement observer's pose baseline explicit before issuing Lock;
        # otherwise a queued ModifiedEvent can invalidate the newly locked
        # state after the fact.
        widget._lastRobotBasePoseFingerprint = logic.robotBasePoseFingerprint(
            parameter_node.robotBaseTransform
        )
        require_success(facade.lockBase(), "lock diagnostically offset base")
        process_events(0.25)
        if not parameter_node.robotBaseMountLocked:
            raise RuntimeError("diagnostically offset robot base did not remain locked")
    selected_before_connect = slicer.util.selectedModule()
    connection = facade.connect(open_motion_module=False)
    task_home_remediated = False
    if not connection.success:
        if (
            connection.code != "task_home_scene_invalid_runtime_connected"
            or not facade.capabilities().connected
        ):
            raise RuntimeError(f"connect ROS/MoveIt: {connection.message}")
        # The x4 package intentionally remains immutable on disk.  Exercise the
        # same explicit operator recovery offered by 6.2: the rejected home has
        # already restored the current guard-accepted joint vector in the UI.
        require_success(facade.saveTaskHome(), "save remediated Task Home")
        require_success(facade.applyTaskHome(), "validate remediated Task Home")
        require_success(facade.confirmTask(), "confirm remediated task")
        task_home_remediated = True
    connected = connection
    # Rebuild the live evidence invalidated by the saved package's legacy
    # robot-profile migration.  This follows the normal 6.2→6.4 operator
    # sequence; it is intentionally not an automatic connect/restore action.
    if not facade.taskHomeRuntimeValidated(parameter_node):
        require_success(facade.saveTaskHome(), "save migrated Task Home")
        require_success(facade.applyTaskHome(), "apply migrated Task Home")
    if not facade.workspaceRuntimeValidated(parameter_node):
        require_success(facade.generateWorkspaceCloud(), "regenerate workspace")
        require_success(facade.reviewAssistedLimits(), "review regenerated limits")
    # Reconfirm an old snapshot only after all transient ROS/MoveIt evidence is
    # live.  This is the same explicit operator action required by 6.4 after a
    # robot-resource or policy revision; it must never be auto-connect state.
    if task_issues or logic.confirmedTaskRecord(parameter_node) is None:
        require_success(facade.confirmTask(), "reconfirm restored task")
    snapshot = logic.confirmedTaskRecord(parameter_node)
    template_collision_override = (
        os.environ.get("DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE", "")
        == "1"
    )
    if template_collision_override:
        require_success(
            facade.setTemplateCollisionExclusionForFunctionalSimulation(True),
            "enable explicit x4 template collision exclusion",
        )
    if os.environ.get("DENTOBOT_FOCUSED_STAGE3_DIAG", "") == "1":
        home_record = logic.taskHomeRecord(parameter_node)
        if home_record is None:
            raise RuntimeError("focused Stage-3 diagnostic has no Task Home")
        home_positions = bridge.canonicalize_planning_joint_positions(
            dict(zip(home_record.joint_names, home_record.joint_positions_si))
        )
        robot_node = bridge.find_ros2_robot_by_name(bridge.ROS2_ROBOT_NAME)
        if robot_node is None:
            raise RuntimeError("focused Stage-3 diagnostic could not find the ROS robot")
        dense_world = bridge.tool_pose_matrices_world_mm(
            snapshot.entry_ras_mm,
            snapshot.target_ras_mm,
            65,
        )
        dense_base = bridge._pose_matrices_world_to_base_mm(
            dense_world,
            parameter_node.robotBaseTransform,
        )
        seeds = [dict(home_positions)]
        try:
            proposal = json.loads(str(parameter_node.step6AssistedLimitProposalJson or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            proposal = {}
        for evidence in proposal.get("accepted_sample_evidence", ()):
            if not isinstance(evidence, dict):
                continue
            names = tuple(evidence.get("joint_names", ()))
            values = tuple(evidence.get("joint_positions_si", ()))
            if len(values) not in (5, 6):
                continue
            try:
                seed = bridge.canonicalize_planning_joint_positions(
                    dict(zip(names, (float(value) for value in values)))
                )
            except (TypeError, ValueError, KeyError):
                continue
            if seed not in seeds:
                seeds.append(seed)
            if len(seeds) >= 40:
                break
        pose = dense_base[60]
        def probe(seed):
            solution = robot_node.ComputeMoveItPositionAxisIK(
                pose,
                bridge.ROS2_TOOL_TCP_LINK,
                bridge.joint_si_vector(seed),
                2.0,
                False,
            )
            return {
                "solution": list(solution) if solution else None,
                "message": robot_node.GetLastMoveItPositionAxisIKMessage(),
                "position_residual_mm": robot_node.GetLastMoveItPositionAxisIKPositionResidualMm(),
                "axis_residual_deg": robot_node.GetLastMoveItPositionAxisIKAxisResidualDeg(),
                "best_joint_values": list(robot_node.GetLastMoveItPositionAxisIKBestJointValues()),
            }

        print("DENTOBOT_STAGE3_POSE60_DIAGNOSTIC", flush=True)
        print(json.dumps({
            "pose_index": 60,
            "pose_count": len(dense_base),
            "entry_ras_mm": list(snapshot.entry_ras_mm),
            "target_ras_mm": list(snapshot.target_ras_mm),
            "seed_count": len(seeds),
            "results": [
                {"seed_index": index, "seed": dict(seed), **probe(seed)}
                for index, seed in enumerate(seeds)
            ],
        }, indent=2, sort_keys=True), flush=True)
        slicer.util.exit(0)
    if slicer.util.selectedModule() != selected_before_connect:
        raise RuntimeError("routine Step 6 Connect left DENTOWorkflow")

    actual_contact_audit = (
        os.environ.get("DENTOBOT_AUDIT_ACTUAL_CONTACT_ONLY", "") == "1"
    )
    original_tool_insertion_evidence = None
    if actual_contact_audit:
        # The production P0 insertion limit is intentionally a hard block.  A
        # historical x4 path cannot be regenerated after that correction, so
        # this test-local bypass exists solely to classify *already requested*
        # candidate poses against MoveIt's mesh scene.  It is never persisted,
        # never exposed by the workflow UI, and never permits preview.
        original_tool_insertion_evidence = facade._tool_insertion_evidence
        facade._tool_insertion_evidence = lambda _entry, _target: {
            "status": "Pass",
            "code": "TEST_ONLY_INSERTION_LIMIT_BYPASS",
            "message": (
                "TEST ONLY: the production insertion hard-block was bypassed "
                "to audit historical x4 candidate geometry; no preview is allowed."
            ),
        }
    try:
        approach = facade.planApproachPhase()
    finally:
        if original_tool_insertion_evidence is not None:
            facade._tool_insertion_evidence = original_tool_insertion_evidence
    if EXPLICIT_CASE:
        exact_diagnostic = {
            "case": str(PACKAGE),
            "code": approach.code,
            "message": approach.message,
            "details": approach.details,
            "task": snapshot.to_dict(),
            "motion": json.loads(str(parameter_node.step6MotionDiagnosticJson or "{}")),
        }
        Path("/tmp/dentobot-exact-case-diagnostic.json").write_text(json.dumps(
            exact_diagnostic, indent=2, default=str
        ))
        if os.environ.get("DENTOBOT_CAPTURE_FDI21_BOTTOM", "") == "1":
            capture_fdi21_contact_from_below(facade, exact_diagnostic["motion"])
            slicer.util.exit(0)
            return {"diagnostic_only": True, "fdi21_bottom_capture": True}
    if not (
        approach.success
        or (
            os.environ.get("DENTOBOT_PLAN_ONLY", "") == "1"
            and approach.code == "approach_full_chain_blocked"
            and approach.payload is not None
        )
    ):
        require_success(approach, "plan Goal 1")
    approach_plan = approach.payload
    if actual_contact_audit:
        try:
            diagnostic_payload = json.loads(
                str(parameter_node.step6MotionDiagnosticJson or "")
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"actual-contact audit has no candidate diagnostic: {exc}"
            ) from exc
        outcomes = audit_actual_moveit_contacts(facade, diagnostic_payload)
        return {
            "diagnostic_only": True,
            "actual_contact_audit": True,
            "production_insertion_block_bypassed": True,
            "template_collision_exclusion_active": bool(
                facade.templateCollisionExclusionActive
            ),
            "planner_result_code": approach.code,
            "planner_full_task_status": approach.details.get("fullTaskStatus"),
            "candidate_outcomes": outcomes,
        }
    if os.environ.get("DENTOBOT_DIAG_APPROACH_ENDPOINT", "") == "1":
        endpoint = approach_plan.waypoint_joint_vectors_si[-1]
        fk_ok, fk_message, actual = bridge.compute_tcp_position_world_ras_mm(
            endpoint,
            base_transform=parameter_node.robotBaseTransform,
        )
        snapshot_for_diag = logic.confirmedTaskRecord(parameter_node)
        expected_entry = tuple(snapshot_for_diag.entry_ras_mm)
        try:
            diagnostic_session = json.loads(
                str(parameter_node.step6MotionDiagnosticJson or "")
            )
            diagnostic_records = diagnostic_session.get("candidate_records", [])
        except (TypeError, ValueError, json.JSONDecodeError):
            diagnostic_session = {}
            diagnostic_records = []
        error = (
            math.sqrt(sum((float(actual[index]) - expected_entry[index]) ** 2 for index in range(3)))
            if fk_ok and actual is not None
            else None
        )
        print("DENTOBOT_APPROACH_ENDPOINT_DIAGNOSTIC", flush=True)
        print(json.dumps({
            "planCode": approach.code,
            "planDetails": dict(approach.details),
            "waypointCount": len(approach_plan.waypoint_joint_vectors_si),
            "strictWaypointCount": approach_plan.strict_waypoint_count,
            "axisWaypointCount": approach_plan.axis_waypoint_count,
            "contactWaypointCount": approach_plan.contact_waypoint_count,
            "lastJoint": dict(endpoint),
            "fkOk": fk_ok,
            "fkMessage": fk_message,
            "actualTcpRasMm": actual,
            "expectedEntryRasMm": expected_entry,
            "endpointErrorMm": error,
            "selectedDiagnostic": (
                diagnostic_records[
                    int(diagnostic_session.get("selected_candidate_index", 0))
                ]
                if diagnostic_records
                and 0 <= int(diagnostic_session.get("selected_candidate_index", 0)) < len(diagnostic_records)
                else (diagnostic_records[0] if diagnostic_records else None)
            ),
        }, indent=2, sort_keys=True), flush=True)
        raise RuntimeError("diagnostic-only endpoint inspection")
    planned_path_nodes = [
        node
        for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
        if node.GetAttribute("DENTOBOT.Step6PhasePlanPath") == "true"
    ]
    if not 1 <= len(planned_path_nodes) <= 3:
        raise RuntimeError(
            "Goal 1 did not create the expected bounded set of stage paths."
        )
    for planned_path_node in planned_path_nodes:
        planned_path_polydata = planned_path_node.GetPolyData()
        if (
            planned_path_polydata is None
            or planned_path_polydata.GetNumberOfPoints() < 2
            or planned_path_polydata.GetNumberOfLines() < 1
        ):
            raise RuntimeError(
                "A Goal 1 stage path is empty or has no rendered path cells."
            )
    for waypoint in approach_plan.waypoint_joint_vectors_si:
        if len(waypoint) != len(bridge.ROS2_JOINT_SI_ORDER):
            raise RuntimeError("Goal 1 returned a non-planning joint vector")
    if not approach_plan.tool_orientation_fingerprint:
        raise RuntimeError("Goal 1 did not commit a Stage-1 drilling frame")
    if len(approach_plan.tool_axis_ras) != 3 or not math.isclose(
        sum(float(value) ** 2 for value in approach_plan.tool_axis_ras),
        1.0,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        raise RuntimeError("Goal 1 committed an invalid drilling-axis vector")
    if approach_plan.cartesian_fraction < 0.99:
        raise RuntimeError(
            f"Goal 1 terminal fraction is {approach_plan.cartesian_fraction}"
        )
    if approach_plan.coordinate_frame != bridge.ROS2_FIXED_FRAME:
        raise RuntimeError(
            f"Goal 1 used unexpected frame {approach_plan.coordinate_frame}"
        )
    if (
        approach_plan.start_position_error_mm is not None
        and approach_plan.start_position_error_mm
        > bridge.CARTESIAN_START_POSITION_TOLERANCE_MM
    ) or (
        approach_plan.start_orientation_error_deg is not None
        and approach_plan.start_orientation_error_deg
        > bridge.CARTESIAN_START_ORIENTATION_TOLERANCE_DEG
    ):
        raise RuntimeError(
            "Goal 1 start continuity is outside tolerance: "
            f"{approach_plan.start_position_error_mm} mm, "
            f"{approach_plan.start_orientation_error_deg} deg"
        )
    if os.environ.get("DENTOBOT_PLAN_ONLY", "") == "1":
        try:
            diagnostic_payload = json.loads(
                str(parameter_node.step6MotionDiagnosticJson or "")
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            diagnostic_payload = {}
        candidate_outcomes = []
        for record in diagnostic_payload.get("candidate_records", ()):
            if not isinstance(record, dict):
                continue
            nearest_first_base = record.get(
                "guard_nearest_point_first_base_m"
            )
            nearest_second_base = record.get(
                "guard_nearest_point_second_base_m"
            )
            candidate_outcomes.append(
                {
                    "candidate_index": record.get("candidate_index"),
                    "route_type": record.get("route_type"),
                    "ik_seed_sample_index": record.get("ik_seed_sample_index"),
                    "axial_roll_deg": record.get("axial_roll_deg"),
                    "full_chain_status": record.get("full_chain_candidate_status"),
                    "failure_stage": record.get("full_chain_failure_stage"),
                    "first_invalid_stage_index": record.get(
                        "full_chain_first_invalid_stage_index"
                    ),
                    "stage2_fraction": record.get("stage2_fraction"),
                    "stage3_fraction": record.get("stage3_fraction"),
                    "first_cause": record.get("full_chain_failure_reason"),
                    "stage1_success": record.get("success"),
                    "stage1_waypoint_count": record.get("stage1_waypoint_count"),
                    "stage2_waypoint_count": record.get("stage2_waypoint_count"),
                    "stage3_waypoint_count": record.get("stage3_waypoint_count"),
                    "failure_classification": record.get("failure_classification"),
                    "first_invalid_collision_pairs": record.get(
                        "first_invalid_collision_pairs"
                    ),
                    "completed_distance_mm": record.get("completed_distance_mm"),
                    "requested_distance_mm": record.get("requested_distance_mm"),
                    "first_invalid_tcp_ras_mm": record.get(
                        "first_invalid_ras_mm"
                    ),
                    "first_invalid_joint_positions_si": record.get(
                        "first_invalid_joint_positions_si"
                    ),
                    "guard_first_body": record.get("guard_first_body"),
                    "guard_second_body": record.get("guard_second_body"),
                    "guard_minimum_world_distance_m": record.get(
                        "guard_minimum_world_distance_m"
                    ),
                    "guard_nearest_point_first_base_m": nearest_first_base,
                    "guard_nearest_point_second_base_m": nearest_second_base,
                    "guard_nearest_point_first_world_ras_mm": (
                        base_point_m_to_world_ras_mm(
                            nearest_first_base,
                            parameter_node.robotBaseTransform,
                        )
                    ),
                    "guard_nearest_point_second_world_ras_mm": (
                        base_point_m_to_world_ras_mm(
                            nearest_second_base,
                            parameter_node.robotBaseTransform,
                        )
                    ),
                }
            )
        return {
            "diagnostic_only": True,
            "base_local_z_offset_mm": BASE_LOCAL_Z_OFFSET_MM,
            "result_code": approach.code,
            "full_task_status": str(approach.details.get("fullTaskStatus") or ""),
            "blocked_stage": str(approach.details.get("blockedStage") or ""),
            "first_invalid_cause": str(approach.details.get("firstInvalidCause") or ""),
            "stage3_fraction": approach.details.get("drillingPreflightFraction"),
            "planning_joint_count": len(bridge.ROS2_JOINT_SI_ORDER),
            "stage_path_count": len(planned_path_nodes),
            "candidate_chain_outcomes": candidate_outcomes,
            "template_collision_exclusion_active": bool(
                facade.templateCollisionExclusionActive
            ),
        }
    approach_finished = []
    approach_progress = []
    require_success(
        facade.previewPhase(
            "approach",
            interval_ms=50,
            on_progress=lambda index, total: approach_progress.append(
                (int(index), int(total))
            ),
            on_finished=approach_finished.append,
        ),
        "start Goal 1 preview",
    )
    if wait_until(lambda: approach_finished, PREVIEW_TIMEOUT_SEC) is None:
        last_status = bridge._last_task_status
        raise RuntimeError(
            "Goal 1 guarded preview timed out at "
            f"{approach_progress[-1] if approach_progress else (0, len(approach_plan.waypoint_joint_vectors_si))}; "
            f"previewActive={facade.previewActive}, sequence={facade._phase_sequence}, "
            f"lastGuardStatus={last_status}"
        )
    approach_outcome = require_success(approach_finished[-1], "preview Goal 1")
    if facade.completedPhase != "approach":
        raise RuntimeError("Goal 1 did not establish the accepted Entry state")

    # The approach is an independently reviewable milestone.  Keep a focused
    # acceptance mode so a known/intentional Goal 2 reachability failure cannot
    # hide a valid Goal 1 preview during development.
    if os.environ.get("DENTOBOT_GOAL1_ONLY", "") == "1":
        accepted = bridge.last_accepted_joint_positions_si()
        if any(name not in accepted for name in bridge.ROS2_JOINT_SI_ORDER):
            raise RuntimeError("Goal 1 preview did not leave an accepted state")
        return {
            "package": PACKAGE.name,
            # Older step-6 packages may not contain an immutable task record;
            # the empty value is intentional until the live runtime has been
            # reconstructed and the task is explicitly reconfirmed below.
            "restored_task_fingerprint": restored_task_before_runtime,
            "planned_task_fingerprint": (
                snapshot.snapshot_fingerprint if snapshot is not None else ""
            ),
            "task_home_remediated": task_home_remediated,
            "task_home_migrated": bool(migration_home_issues),
            "goal1_strict_points": approach_plan.strict_waypoint_count,
            "goal1_axis_points": approach_plan.axis_waypoint_count,
            "goal1_terminal_points": approach_plan.contact_waypoint_count,
            "goal1_cartesian_fraction": approach_plan.cartesian_fraction,
            "goal1_start_position_error_mm": approach_plan.start_position_error_mm,
            "goal1_start_orientation_error_deg": approach_plan.start_orientation_error_deg,
            "goal1_exploratory_tool_contact_suppressed": bool(
                approach_outcome.details.get("exploratoryToolContactSuppressed", False)
            ),
            "goal1_suppressed_tool_contact_samples": int(
                approach_outcome.details.get("suppressedToolContactSampleCount", 0)
            ),
            "goal1_preview_complete": True,
            "goal1_result_code": approach.code,
            "full_task_status": str(
                approach.details.get("fullTaskStatus") or "Provisional"
            ),
            "full_task_blocked_stage": str(
                approach.details.get("blockedStage") or ""
            ),
            "full_task_blocker": str(
                approach.details.get("firstInvalidCause")
                or approach.details.get("terminalPlanningError")
                or approach.details.get("drillingPreflightError")
                or ""
            ),
            "terminal_planning_fraction": approach.details.get(
                "terminalPlanningFraction"
            ),
            "stage_path_count": len(planned_path_nodes),
            "planning_joint_count": len(bridge.ROS2_JOINT_SI_ORDER),
            "tool_orientation_fingerprint": (
                approach_plan.tool_orientation_fingerprint
            ),
            "tool_axis_ras": tuple(approach_plan.tool_axis_ras),
            "goal2_deferred": True,
            "hardware_execution_enabled": False,
        }

    drilling = require_success(facade.planDrillingPhase(), "plan Goal 2")
    drilling_plan = drilling.payload
    if (
        drilling_plan.tool_orientation_fingerprint
        != approach_plan.tool_orientation_fingerprint
        or tuple(drilling_plan.tool_axis_ras) != tuple(approach_plan.tool_axis_ras)
    ):
        raise RuntimeError(
            "Goal 2 did not inherit the exact Stage-1 drilling-frame commitment"
        )
    if drilling_plan.cartesian_fraction < 0.99:
        raise RuntimeError(
            f"Goal 2 Cartesian fraction is {drilling_plan.cartesian_fraction}"
        )
    if (
        drilling_plan.start_position_error_mm is None
        or drilling_plan.start_position_error_mm
        > bridge.CARTESIAN_START_POSITION_TOLERANCE_MM
        or drilling_plan.start_orientation_error_deg is None
        or drilling_plan.start_orientation_error_deg
        > bridge.CARTESIAN_START_ORIENTATION_TOLERANCE_DEG
    ):
        raise RuntimeError(
            "Goal 2 did not begin at the accepted Entry state: "
            f"{drilling_plan.start_position_error_mm} mm, "
            f"{drilling_plan.start_orientation_error_deg} deg"
        )
    drilling_finished = []
    drilling_progress = []
    require_success(
        facade.previewPhase(
            "drilling",
            interval_ms=50,
            on_progress=lambda index, total: drilling_progress.append(
                (int(index), int(total))
            ),
            on_finished=drilling_finished.append,
        ),
        "start Goal 2 preview",
    )
    if wait_until(lambda: drilling_finished, PREVIEW_TIMEOUT_SEC) is None:
        last_status = bridge._last_task_status
        raise RuntimeError(
            "Goal 2 guarded preview timed out at "
            f"{drilling_progress[-1] if drilling_progress else (0, len(drilling_plan.waypoint_joint_vectors_si))}; "
            f"previewActive={facade.previewActive}, sequence={facade._phase_sequence}, "
            f"lastGuardStatus={last_status}"
        )
    drilling_outcome = require_success(drilling_finished[-1], "preview Goal 2")
    if facade.completedPhase != "drilling":
        raise RuntimeError("Goal 2 did not complete under the phase guard")

    accepted = bridge.last_accepted_joint_positions_si()
    if any(name not in accepted for name in bridge.ROS2_JOINT_SI_ORDER):
        raise RuntimeError("final accepted planning-joint state is unavailable")
    robot = connected.payload
    actual_target_base_mm = vtk.vtkMatrix4x4()
    if robot.ComputeKDLFK(
        bridge.joint_si_vector(accepted),
        actual_target_base_mm,
        bridge.ROS2_TOOL_TCP_LINK,
    ) is None:
        raise RuntimeError("final provisional TCP FK failed")
    expected_target_base_m = bridge.world_ras_mm_to_base_m(
        snapshot.target_ras_mm,
        parameter_node.robotBaseTransform,
    )
    final_position_error_mm = math.sqrt(
        sum(
            (
                actual_target_base_mm.GetElement(axis, 3)
                - expected_target_base_m[axis] * 1000.0
            )
            ** 2
            for axis in range(3)
        )
    )
    if final_position_error_mm > bridge.CARTESIAN_START_POSITION_TOLERANCE_MM:
        raise RuntimeError(
            f"final TCP missed Target by {final_position_error_mm:.6f} mm"
        )

    first_return = require_success(
        facade.returnToTaskHome(), "guarded Return Home"
    )
    if not first_return.details.get("axialRetractionCompleted"):
        raise RuntimeError("first guarded return did not complete axial retraction")
    repeated_approach = require_success(
        facade.planApproachPhase(),
        "repeat Goal 1 planning",
    )
    repeated_approach_plan = repeated_approach.payload
    repeated_approach_outcome = preview_repeat_phase(
        facade,
        "approach",
        len(repeated_approach_plan.waypoint_joint_vectors_si),
    )
    if facade.completedPhase != "approach":
        raise RuntimeError("Repeated Goal 1 did not establish the accepted Entry state")
    repeated_drilling = require_success(
        facade.planDrillingPhase(),
        "repeat Goal 2 planning",
    )
    repeated_drilling_plan = repeated_drilling.payload
    if (
        repeated_drilling_plan.tool_orientation_fingerprint
        != repeated_approach_plan.tool_orientation_fingerprint
    ):
        raise RuntimeError("Repeated drilling did not retain its Stage-1 tool frame")
    repeated_drilling_outcome = preview_repeat_phase(
        facade,
        "drilling",
        len(repeated_drilling_plan.waypoint_joint_vectors_si),
    )
    if facade.completedPhase != "drilling":
        raise RuntimeError("Repeated Goal 2 did not complete under the phase guard")
    repeated_accepted = bridge.last_accepted_joint_positions_si()
    repeated_target_base_mm = vtk.vtkMatrix4x4()
    if robot.ComputeKDLFK(
        bridge.joint_si_vector(repeated_accepted),
        repeated_target_base_mm,
        bridge.ROS2_TOOL_TCP_LINK,
    ) is None:
        raise RuntimeError("Repeated final canonical-TCP FK failed")
    repeated_target_error_mm = math.sqrt(
        sum(
            (
                repeated_target_base_mm.GetElement(axis, 3)
                - expected_target_base_m[axis] * 1000.0
            )
            ** 2
            for axis in range(3)
        )
    )
    if repeated_target_error_mm > bridge.CARTESIAN_START_POSITION_TOLERANCE_MM:
        raise RuntimeError(
            "Repeated final TCP missed Target by "
            f"{repeated_target_error_mm:.6f} mm"
        )
    final_return = require_success(
        facade.returnToTaskHome(), "final guarded Return Home"
    )
    if not final_return.details.get("axialRetractionCompleted"):
        raise RuntimeError("final guarded return did not complete axial retraction")
    preflight_warning_count = int(
        approach.details.get("guideClearanceWarningCount", 0)
    )
    if preflight_warning_count <= 0:
        raise RuntimeError(
            "the exact case did not persist its expected guide-clearance warning"
        )
    return {
        "package": PACKAGE.name,
        "restored_task_fingerprint": restored_task_before_runtime,
        "planned_task_fingerprint": snapshot.snapshot_fingerprint,
        "task_home_remediated": task_home_remediated,
        "task_home_migrated": bool(migration_home_issues),
        "planning_frame": drilling_plan.coordinate_frame,
        "goal1_strict_points": approach_plan.strict_waypoint_count,
        "goal1_terminal_points": approach_plan.contact_waypoint_count,
        "goal1_cartesian_fraction": approach_plan.cartesian_fraction,
        "goal1_start_position_error_mm": approach_plan.start_position_error_mm,
        "goal1_start_orientation_error_deg": approach_plan.start_orientation_error_deg,
        "goal2_points": drilling_plan.contact_waypoint_count,
        "goal2_cartesian_fraction": drilling_plan.cartesian_fraction,
        "goal2_start_position_error_mm": drilling_plan.start_position_error_mm,
        "goal2_start_orientation_error_deg": drilling_plan.start_orientation_error_deg,
        "goal2_axial_roll_deg": drilling_plan.axial_roll_deg,
        "goal1_exploratory_tool_contact_suppressed": bool(
            approach_outcome.details.get("exploratoryToolContactSuppressed", False)
        ),
        "goal1_suppressed_tool_contact_samples": int(
            approach_outcome.details.get("suppressedToolContactSampleCount", 0)
        ),
        "goal2_exploratory_tool_contact_suppressed": bool(
            drilling_outcome.details.get("exploratoryToolContactSuppressed", False)
        ),
        "goal2_suppressed_tool_contact_samples": int(
            drilling_outcome.details.get("suppressedToolContactSampleCount", 0)
        ),
        "preflight_guide_clearance_warning_count": preflight_warning_count,
        "preflight_minimum_guide_clearance_warning_m": approach.details.get(
            "minimumGuideClearanceWarningM"
        ),
        "preflight_guide_warning_kinds": list(
            approach.details.get("guideClearanceWarningKinds", ())
        ),
        "preflight_guide_contact_penetration_mm": list(
            approach.details.get("guideClearanceWarningContactPenetrationMm", ())
        ),
        "goal1_guide_clearance_warning_count": int(
            approach_outcome.details.get("guideClearanceWarningCount", 0)
        ),
        "goal1_guide_warning_kinds": list(
            approach_outcome.details.get("guideClearanceWarningKinds", ())
        ),
        "goal2_guide_clearance_warning_count": int(
            drilling_outcome.details.get("guideClearanceWarningCount", 0)
        ),
        "goal2_guide_warning_kinds": list(
            drilling_outcome.details.get("guideClearanceWarningKinds", ())
        ),
        "first_return_axial_retraction_complete": bool(
            first_return.details.get("axialRetractionCompleted")
        ),
        "first_return_reverse_waypoint_count": int(
            first_return.details.get("acceptedReverseWaypointCount", 0)
        ),
        "first_return_guide_clearance_warning_count": int(
            first_return.details.get("guideClearanceWarningCount", 0)
        ),
        "first_return_guide_warning_kinds": list(
            first_return.details.get("guideClearanceWarningKinds", ())
        ),
        "repeat_goal1_guide_clearance_warning_count": int(
            repeated_approach_outcome.details.get(
                "guideClearanceWarningCount", 0
            )
        ),
        "repeat_goal2_guide_clearance_warning_count": int(
            repeated_drilling_outcome.details.get(
                "guideClearanceWarningCount", 0
            )
        ),
        "final_return_axial_retraction_complete": bool(
            final_return.details.get("axialRetractionCompleted")
        ),
        "final_return_reverse_waypoint_count": int(
            final_return.details.get("acceptedReverseWaypointCount", 0)
        ),
        "final_return_guide_clearance_warning_count": int(
            final_return.details.get("guideClearanceWarningCount", 0)
        ),
        "final_return_guide_warning_kinds": list(
            final_return.details.get("guideClearanceWarningKinds", ())
        ),
        "final_target_position_error_mm": final_position_error_mm,
        "repeat_final_target_position_error_mm": repeated_target_error_mm,
        "guarded_preview_complete": True,
        "guarded_return_home_complete": True,
        "repeat_guarded_preview_complete": True,
        "hardware_execution_enabled": False,
        "template_collision_exclusion_active": bool(
            facade.templateCollisionExclusionActive
        ),
    }


try:
    report = run()
    print(
        "DENTOBOT_STAGE3_ACTUAL_CONTACT_AUDIT"
        if os.environ.get("DENTOBOT_AUDIT_ACTUAL_CONTACT_ONLY", "") == "1"
        else "DENTOBOT_STEP65_PLAN_DIAGNOSTIC"
        if os.environ.get("DENTOBOT_PLAN_ONLY", "") == "1"
        else "DENTOBOT_STEP65_EXACT_CASE_PASS",
        flush=True,
    )
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    bridge.disconnect_dentobot_motion_control([])
    bridge.shutdown_slicer_adapter()
    slicer.mrmlScene.Clear(0)
    slicer.app.processEvents()
    slicer.util.exit(0)
except Exception as exc:
    print(f"DENTOBOT_STEP65_EXACT_CASE_FAILED: {exc}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
    try:
        bridge.disconnect_dentobot_motion_control([])
        bridge.shutdown_slicer_adapter()
    except Exception:
        pass
    slicer.util.exit(1)
