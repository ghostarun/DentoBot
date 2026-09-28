"""Narrow headless Slicer/ROS integration check for the guarded manual jog.

This runner uses one disposable Slicer scene and the existing Step 6 façade/UI.
It never saves the opened case, plans a route, starts preview, or exposes a
hardware command. A rejected vector is optional and must be bound to the exact
source case and fixture identity in ``DENTOBOT_MANUAL_JOG_REJECTION_PLAN_JSON``.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

import slicer
import vtk


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
MODULE = ROOT / "DENTOWorkflow"
TESTING = ROOT / "Testing"
for candidate in (HELPERS, MODULE, TESTING):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import DENTOROS2Bridge as bridge  # noqa: E402
from DENTOCaseBundle import validate_case_bundle  # noqa: E402
from DENTORobotWorkflowFacade import (  # noqa: E402
    JOINT_DISPLAY_UNITS,
    JOINT_LIMIT_FIELDS,
    JOINT_NAMES,
)
from DENTOStep6Planning import (  # noqa: E402
    default_task_joint_limits_from_urdf,
    joint_limit_margin_evidence,
)
from DENTOStep6State import fingerprint  # noqa: E402
from step6_manual_jog_scenarios import (  # noqa: E402
    fixture_identity as _fixture_identity,
    rejection_plan as _rejection_plan,
)


REPORT_NAME = "manual_jog_headless.json"
ACCEPTED_DELTA_DEG = 0.1
MONITOR_TIMEOUT_SEC = 3.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite_vector(values, names=JOINT_NAMES) -> dict[str, float]:
    if not isinstance(values, Mapping) or set(values) != set(names):
        raise ValueError("Joint state must contain exactly J1–J5.")
    result = {name: float(values[name]) for name in names}
    if not all(math.isfinite(value) for value in result.values()):
        raise ValueError("Joint state contains a non-finite value.")
    return result


def _ordered_vector(values) -> list[float] | None:
    if isinstance(values, Mapping):
        try:
            row = _finite_vector(values)
        except (TypeError, ValueError, OverflowError):
            return None
        return [row[name] for name in JOINT_NAMES]
    if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
        if len(values) != len(JOINT_NAMES):
            return None
        try:
            row = [float(value) for value in values]
        except (TypeError, ValueError, OverflowError):
            return None
        return row if all(math.isfinite(value) for value in row) else None
    return None


def _process_events(seconds: float = 0.05) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        ros_logic = slicer.util.getModuleLogic("ROS2")
        if ros_logic is not None:
            ros_logic.Spin()
        time.sleep(0.01)


def _wait_until(predicate, timeout_sec: float = MONITOR_TIMEOUT_SEC):
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        _process_events(0.02)
        value = predicate()
        if value:
            return value
    return None


def _exactly_matches(left, right) -> bool:
    def ordered(values):
        if isinstance(values, Mapping):
            if set(values) != set(JOINT_NAMES):
                return None
            result = [float(values[name]) for name in JOINT_NAMES]
        elif isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            if len(values) != len(JOINT_NAMES):
                return None
            result = [float(value) for value in values]
        else:
            return None
        return result if all(math.isfinite(value) for value in result) else None

    try:
        first, second = ordered(left), ordered(right)
        return first is not None and second is not None and first == second
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _matches_at_display_precision(left, right) -> bool:
    try:
        first, second = _ordered_vector(left), _ordered_vector(right)
        return (
            first is not None
            and second is not None
            and all(abs(a - b) <= 1.0e-12 for a, b in zip(first, second))
        )
    except (TypeError, ValueError, OverflowError):
        return False


def _task_home_positions(record) -> dict[str, float]:
    names = tuple(str(name) for name in record.joint_names)
    values = tuple(float(value) for value in record.joint_positions_si)
    if len(names) != len(values) or set(names) != set(JOINT_NAMES):
        raise RuntimeError("Saved Task Home does not contain exactly J1–J5.")
    return _finite_vector(dict(zip(names, values)))


def _json_safe(value):
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _write_report(report_path: Path, report: dict[str, object]) -> None:
    report_path.write_text(
        json.dumps(_json_safe(report), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _scene_evidence(logic, parameter_node) -> dict[str, object]:
    audit = logic.collisionSceneAuditRecord(parameter_node)
    if audit is None:
        raise RuntimeError("The current case collision-scene audit is unavailable.")
    acknowledgement = dict(audit.runtime_acknowledgement or {})
    acknowledged_ids = sorted(
        str(value) for value in acknowledgement.get("acknowledged_object_ids", ())
        if str(value)
    )
    source_ids = sorted(
        str(item.get("outgoing_collision_object_id") or "")
        for item in audit.object_records
        if str(item.get("outgoing_collision_object_id") or "")
    )
    return {
        "audit_fingerprint": str(audit.audit_fingerprint),
        "status": str(audit.status),
        "base_fingerprint": str(audit.base_fingerprint),
        "runtime_acknowledgement": acknowledgement,
        "acknowledged_object_ids": acknowledged_ids,
        "source_object_ids": source_ids,
    }


def _identity(logic, parameter_node, facade) -> dict[str, object]:
    snapshot = logic.confirmedTaskRecord(parameter_node)
    home = logic.taskHomeRecord(parameter_node)
    if snapshot is None or home is None:
        raise RuntimeError("A current confirmed task and saved Task Home are required.")
    registry = json.loads(str(parameter_node.step6TrajectoryRegistryJson or "{}"))
    branch_id = str(registry.get("selected_branch_id") or "")
    if not branch_id:
        raise RuntimeError("A selected PreparedBranch is required.")
    identity = facade.plannerComparisonIdentity()
    home_positions = _task_home_positions(home)
    scene = _scene_evidence(logic, parameter_node)
    limits = logic.getTaskJointLimits(parameter_node)
    snapshot_data = snapshot.to_dict()
    task_core = {
        "target_segment_id": str(parameter_node.targetToothSegmentId or ""),
        "trajectory_revision": str(logic.step6TrajectoryRevision(parameter_node)),
        "entry_ras_mm": list(snapshot.entry_ras_mm),
        "target_ras_mm": list(snapshot.target_ras_mm),
        "base_fingerprint": str(logic.robotBaseFingerprint(parameter_node)),
        "limits_fingerprint": str(logic.step6TaskLimitsFingerprint(parameter_node)),
        "robot_profile_fingerprint": str(logic.robotProfileFingerprint()),
        "tool_frame": str(parameter_node.step6ToolFrame),
        "corridor_radius_mm": float(parameter_node.step6TrajectoryCorridorRadiusMm),
    }
    fixture_identity = _fixture_identity(
        branch_id=branch_id,
        task_core=task_core,
        home_revision=home.revision,
        home_joint_positions_si=home_positions,
        scene_source_object_ids=scene["source_object_ids"],
        scene_base_fingerprint=scene["base_fingerprint"],
        fingerprint_fn=fingerprint,
    )
    base = parameter_node.robotBaseTransform
    return {
        "branch_id": branch_id,
        "task_fingerprint": str(snapshot.snapshot_fingerprint),
        "task_snapshot": snapshot_data,
        "task_core": task_core,
        "task_core_fingerprint": fingerprint(task_core),
        "base_fingerprint": task_core["base_fingerprint"],
        "base_node_id": str(base.GetID()) if base is not None else "",
        "home_fingerprint": fingerprint(home.to_dict()),
        "home_revision": int(home.revision),
        "home_joint_positions_si": home_positions,
        "limits_fingerprint": task_core["limits_fingerprint"],
        "limits_display": {
            "minimum": list(limits.as_display_vector()),
            "maximum": list(limits.as_display_max_vector()),
        },
        "robot_profile_fingerprint": task_core["robot_profile_fingerprint"],
        "identity": dict(identity),
        "scene": scene,
        "fixture_identity": fixture_identity,
    }


def _current_task_core(logic, parameter_node) -> dict[str, object]:
    summary = logic.step6TrajectorySummary(parameter_node)
    if not summary.get("isValid"):
        raise RuntimeError("The current trajectory is not valid for task confirmation.")
    return {
        "target_segment_id": str(parameter_node.targetToothSegmentId or ""),
        "trajectory_revision": str(logic.step6TrajectoryRevision(parameter_node)),
        "entry_ras_mm": list(summary["entryRas"]),
        "target_ras_mm": list(summary["targetRas"]),
        "base_fingerprint": str(logic.robotBaseFingerprint(parameter_node)),
        "limits_fingerprint": str(logic.step6TaskLimitsFingerprint(parameter_node)),
        "robot_profile_fingerprint": str(logic.robotProfileFingerprint()),
        "tool_frame": str(parameter_node.step6ToolFrame),
        "corridor_radius_mm": float(parameter_node.step6TrajectoryCorridorRadiusMm),
    }


def _request_identity_stable(before, after) -> bool:
    stable_keys = (
        "branch_id", "task_fingerprint", "task_core_fingerprint",
        "base_fingerprint", "base_node_id", "home_fingerprint",
        "home_revision", "home_joint_positions_si", "limits_fingerprint",
        "robot_profile_fingerprint", "fixture_identity",
    )
    return (
        all(before.get(key) == after.get(key) for key in stable_keys)
        and before["scene"].get("audit_fingerprint")
        == after["scene"].get("audit_fingerprint")
        and before["scene"].get("source_object_ids")
        == after["scene"].get("source_object_ids")
        and before["scene"].get("acknowledged_object_ids")
        == after["scene"].get("acknowledged_object_ids")
        and before.get("identity") == after.get("identity")
    )


def _capture_screenshots(label: str, evidence_dir: Path) -> dict[str, str]:
    """Capture the actual current Slicer UI and viewport; never reconstruct a pose."""
    window = slicer.util.mainWindow()
    if window is None:
        raise RuntimeError("Slicer main window is unavailable for required evidence.")
    window.show()
    old_title = str(window.windowTitle)
    window.windowTitle = f"DENTOBOT guarded jog — {label}"
    try:
        _process_events(0.2)
        ui_path = evidence_dir / f"{label}-ui.png"
        pixmap = window.grab()
        if pixmap.isNull() or not pixmap.save(str(ui_path)):
            raise RuntimeError(f"Could not capture required UI screenshot: {ui_path.name}")

        view = slicer.app.layoutManager().threeDWidget(0).threeDView()
        view.forceRender()
        slicer.util.forceRenderAllViews()
        capture = vtk.vtkWindowToImageFilter()
        capture.SetInput(view.renderWindow())
        capture.ReadFrontBufferOff()
        capture.Update()
        viewport_path = evidence_dir / f"{label}-viewport.png"
        writer = vtk.vtkPNGWriter()
        writer.SetFileName(str(viewport_path))
        writer.SetInputConnection(capture.GetOutputPort())
        writer.Write()
        if not viewport_path.is_file() or viewport_path.stat().st_size <= 0:
            raise RuntimeError(
                f"Could not capture required viewport screenshot: {viewport_path.name}"
            )
        return {
            "captured_at_utc": _utc_now(),
            "ui": ui_path.name,
            "viewport": viewport_path.name,
        }
    finally:
        window.windowTitle = old_title


def _raw_guard_evidence(status) -> dict[str, object] | None:
    if status is None:
        return None
    objects = tuple(getattr(status, "world_objects", ()) or ())
    return {
        "accepted": getattr(status, "accepted", None),
        "reason": str(getattr(status, "reason", "") or ""),
        "requested_positions_si": _ordered_vector(
            dict(zip(JOINT_NAMES, getattr(status, "requested_positions", ())))
        ),
        "accepted_positions_si": _ordered_vector(
            dict(zip(JOINT_NAMES, getattr(status, "accepted_positions", ())))
        ),
        "checked_samples": int(getattr(status, "checked_samples", 0) or 0),
        "minimum_clearance_m": getattr(status, "minimum_clearance_m", None),
        "minimum_self_distance_m": getattr(status, "minimum_self_distance_m", None),
        "minimum_world_distance_m": getattr(status, "minimum_world_distance_m", None),
        "first_body": str(getattr(status, "first_body", "") or ""),
        "second_body": str(getattr(status, "second_body", "") or ""),
        "world_object_count": int(getattr(status, "world_object_count", 0) or 0),
        "world_object_evidence_present": bool(
            getattr(status, "world_object_evidence_present", False)
        ),
        "world_object_ids": sorted(
            str(item.get("id") or "") for item in objects
            if isinstance(item, dict) and str(item.get("id") or "")
        ),
        "collision_scene_policy_fingerprint": str(
            getattr(status, "collision_scene_policy_fingerprint", "") or ""
        ),
    }


def _actual_joint_state(facade) -> dict[str, object]:
    accepted = bridge.last_accepted_joint_positions_si()
    monitored = bridge.monitored_joint_positions_si()
    displayed = facade.currentRobotState().joint_positions_si
    return {
        "accepted_si": _finite_vector(accepted) if accepted else None,
        "monitored_si": _finite_vector(monitored) if monitored else None,
        "displayed_si": _finite_vector(displayed),
    }


def _display_values(positions: dict[str, float]) -> tuple[float, ...]:
    return (
        math.degrees(positions[JOINT_NAMES[0]]),
        positions[JOINT_NAMES[1]] * 1000.0,
        math.degrees(positions[JOINT_NAMES[2]]),
        positions[JOINT_NAMES[3]] * 1000.0,
        math.degrees(positions[JOINT_NAMES[4]]),
    )


def _within_both_limits(logic, parameter_node, positions: dict[str, float]):
    urdf_path, _package_root = logic.robotDescriptionPaths()
    evidence = joint_limit_margin_evidence(
        positions,
        joint_names=JOINT_NAMES,
        joint_limit_fields=JOINT_LIMIT_FIELDS[:5],
        display_units=JOINT_DISPLAY_UNITS[:5],
        mechanical_limits=default_task_joint_limits_from_urdf(urdf_path),
        task_limits=logic.getTaskJointLimits(parameter_node),
    )
    if evidence is None or any(
        row["mechanical_within_limits"] is not True
        or row["reviewed_task_within_limits"] is not True
        for row in evidence.values()
    ):
        return None
    return evidence


def _guard_click(widget, panel, target: dict[str, float]) -> dict[str, object]:
    if not panel.guardedManualJogButton.enabled:
        raise RuntimeError("The production Guarded Jog button is not enabled.")
    panel._setManualJogDraftValues(_display_values(target), notify=True)
    draft = panel.manualJogJointPositionsSi()
    if not _exactly_matches(draft, target):
        raise RuntimeError(
            "The visible numeric controls cannot represent this exact J1–J5 vector."
        )
    _process_events(0.1)
    panel.guardedManualJogButton.click()
    _process_events(0.1)
    evidence = dict(panel._manualJogEvidence or {})
    return {
        "draft_positions_si": draft,
        "status_text": str(panel.manualJogStatusLabel.text),
        "status_state": str(panel.manualJogStatusLabel.property("dentobotState") or ""),
        "panel_accepted_positions_si": (
            dict(panel._manualJogAcceptedJointPositionsSi)
            if panel._manualJogAcceptedJointPositionsSi else None
        ),
        "evidence": evidence,
    }


def run() -> dict[str, object]:
    output_text = os.environ.get("DENTOBOT_MANUAL_JOG_EVIDENCE_DIR", "").strip()
    if not output_text:
        raise RuntimeError("Set DENTOBOT_MANUAL_JOG_EVIDENCE_DIR to write a failure manifest.")
    evidence_dir = Path(output_text)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report_path = evidence_dir / REPORT_NAME
    if report_path.exists():
        raise RuntimeError(f"Refusing to overwrite existing evidence: {report_path}")
    case_sha256 = None
    report: dict[str, object] = {
        "schema_version": "1.0",
        "gate": "S6-LIVE-01 guarded manual J1-J5 jog",
        "started_at_utc": _utc_now(),
        "status": "RUNNING",
        "case_sha256": case_sha256,
        "case_saved": False,
        "simulation_only": True,
        "hardware_execution_enabled": False,
        "planner_calls": 0,
        "preview_started": False,
        "route_authority": "none",
        "evidence_directory": str(evidence_dir),
        "required_screenshot_files": [
            "pre-jog-context-ui.png", "pre-jog-context-viewport.png",
            "accepted-result-ui.png", "accepted-result-viewport.png",
            "unknown-result-ui.png", "unknown-result-viewport.png",
        ],
        "scenarios": {
            "accepted": {"status": "NOT_RUN"},
            "rejected": {"status": "NOT_RUN"},
            "unavailable": {"status": "NOT_RUN"},
        },
        "screenshots": {},
    }

    widget = logic = facade = parameter_node = None
    phase = "case_preflight"
    try:
        case_text = os.environ.get("DENTOBOT_MANUAL_JOG_CASE_SOURCE", "").strip()
        if not case_text:
            raise RuntimeError("Set DENTOBOT_MANUAL_JOG_CASE_SOURCE.")
        case_path = Path(case_text)
        report["case_source"] = str(case_path)
        if not case_path.is_file():
            raise RuntimeError(f"Saved Step 6 case is missing: {case_path}")
        case_sha256 = hashlib.sha256(case_path.read_bytes()).hexdigest()
        report["case_sha256"] = case_sha256
        validate_case_bundle(case_path)
        if any(
            os.environ.get(name, "") == "1"
            for name in (
                "DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE",
                "DENTOBOT_ENABLE_HISTORICAL_ANATOMY_REVIEW",
                "DENTOBOT_AUDIT_ACTUAL_CONTACT_ONLY",
            )
        ):
            raise RuntimeError("Historical overrides are forbidden in this gate.")
        if slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"):
            raise RuntimeError("Refusing a scene with an already-connected ROS robot.")

        slicer.util.selectModule("DENTOWorkflow")
        _process_events(0.5)
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        if widget is None:
            raise RuntimeError("DENTOWorkflow widget is unavailable.")
        widget._openCaseBundle(str(case_path))
        _process_events(0.5)
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        parameter_node = widget._parameterNode
        logic = widget.logic
        facade = widget._robotWorkflowFacade
        if parameter_node is None or logic is None or facade is None:
            raise RuntimeError("Restored Step 6 workflow services are unavailable.")
        if facade.capabilities().connected:
            raise RuntimeError("Refusing a pre-existing connected workflow session.")

        phase = "saved_fixture_preflight"
        freshness_groups = {
            "package": tuple(logic.step6PlanningPackageFreshnessIssues(parameter_node)),
            "jaw": tuple(logic.step6CaseJawOpeningFreshnessIssues(parameter_node)),
            "base": tuple(logic.step6BasePlacementFreshnessIssues(parameter_node)),
            "home": tuple(logic.taskHomeFreshnessIssues(parameter_node)),
            "task": tuple(logic.confirmedTaskFreshnessIssues(parameter_node)),
        }
        if any(freshness_groups.values()):
            raise RuntimeError(
                "The saved current task/Home/base/package is stale: "
                + json.dumps(freshness_groups, sort_keys=True, default=str)
            )
        if not bool(parameter_node.robotBaseMountLocked):
            raise RuntimeError("The saved robot base is not locked.")
        foundation = logic.evaluateCaseFoundationEligibility(parameter_node)
        if not foundation["pose"]["eligible"] or not foundation["base"]["eligible"]:
            raise RuntimeError("Saved Case Foundation pose/base is not eligible.")
        saved_identity = _identity(logic, parameter_node, facade)
        branch_id = saved_identity["branch_id"]
        branch = logic.evaluatePreparedBranchEligibility(parameter_node, branch_id)
        if not branch.get("eligible"):
            raise RuntimeError(
                "The selected PreparedBranch is stale: "
                + str(branch.get("message") or branch.get("reason") or "unknown")
            )
        branch_activation_needed = not bool(parameter_node.step6PlanningContextImported)
        if branch_activation_needed:
            activation = logic.importStep6PlanningContext(parameter_node)
            if not activation.ready:
                raise RuntimeError(
                    "Selected PreparedBranch activation failed: " + str(activation.message)
                )
        if logic.confirmedTaskFreshnessIssues(parameter_node):
            raise RuntimeError("Branch activation made the saved task snapshot stale.")
        if str(logic.robotBaseFingerprint(parameter_node)) != saved_identity["base_fingerprint"]:
            raise RuntimeError("Branch activation changed the saved robot-base identity.")
        report["fixture_identity"] = saved_identity["fixture_identity"]
        report["saved_identity"] = saved_identity
        report["setup"] = {
            "freshness_issues_before_connect": freshness_groups,
            "branch_activation_performed": (
                branch_activation_needed
                and bool(parameter_node.step6PlanningContextImported)
            ),
            "branch_id": branch_id,
            "no_geometry_or_limit_changes": True,
            "no_case_save_or_overwrite": True,
        }

        phase = "simulation_connect"
        load = facade.loadRobot()
        if not load.success:
            raise RuntimeError("Load local robot: " + load.message)
        if str(logic.robotBaseFingerprint(parameter_node)) != saved_identity["base_fingerprint"]:
            raise RuntimeError("Loading the local robot changed the base identity.")
        connection = facade.connect(open_motion_module=False)
        report["setup"]["connect"] = {
            "success": bool(connection.success),
            "code": str(connection.code),
            "message": str(connection.message),
            "details": dict(connection.details or {}),
        }
        if not connection.success:
            raise RuntimeError("Connect simulation ROS/MoveIt: " + connection.message)
        runtime_identity = _identity(logic, parameter_node, facade)
        report["runtime_identity_after_connect"] = runtime_identity
        if (
            runtime_identity["branch_id"] != saved_identity["branch_id"]
            or runtime_identity["base_fingerprint"] != saved_identity["base_fingerprint"]
            or runtime_identity["limits_fingerprint"] != saved_identity["limits_fingerprint"]
            or runtime_identity["robot_profile_fingerprint"]
            != saved_identity["robot_profile_fingerprint"]
        ):
            raise RuntimeError("Connect changed branch/base/limits/profile identity.")
        scene = runtime_identity["scene"]
        acknowledgement = scene["runtime_acknowledgement"]
        expected_ids = tuple(scene["acknowledged_object_ids"])
        raw_status = bridge.joint_command_status()
        status_evidence = _raw_guard_evidence(raw_status)
        if (
            scene["status"] != "Acknowledged"
            or acknowledgement.get("status") != "Acknowledged"
            or not expected_ids
            or tuple(scene["source_object_ids"]) != expected_ids
            or facade._planning_scene_object_count != len(expected_ids)
            or status_evidence is None
            or status_evidence["world_object_evidence_present"] is not True
            or tuple(status_evidence["world_object_ids"] or ()) != expected_ids
        ):
            raise RuntimeError("Current live collision scene is not fully acknowledged.")
        home_positions = dict(runtime_identity["home_joint_positions_si"])
        home_state = _wait_until(
            lambda: (
                _actual_joint_state(facade)
                if _exactly_matches(bridge.monitored_joint_positions_si(), home_positions)
                and _exactly_matches(bridge.last_accepted_joint_positions_si(), home_positions)
                else None
            )
        )
        if home_state is None:
            raise RuntimeError(
                "Connected monitored and accepted J1–J5 must exactly match the saved Task Home; "
                "no Home movement or repair was attempted."
            )

        # Validate only the already-reached saved Home. Block the planner call
        # so any deviation from the no-motion branch fails without planning.
        planner = getattr(facade._bridge, "plan_moveit_joint_goal", None)
        if not callable(planner):
            raise RuntimeError("The MoveIt plan hook could not be bounded for Home validation.")
        def forbidden_plan(*_args, **_kwargs):
            raise RuntimeError("Planner use is forbidden in the manual-jog gate.")
        facade._bridge.plan_moveit_joint_goal = forbidden_plan
        try:
            home_validation = facade.applyTaskHome()
        finally:
            facade._bridge.plan_moveit_joint_goal = planner
        report["setup"]["task_home_validation"] = {
            "success": bool(home_validation.success),
            "code": str(home_validation.code),
            "message": str(home_validation.message),
            "details": dict(home_validation.details or {}),
            "interpretation": "same-state guarded revalidation at saved Task Home; a guard command may still be submitted, but no joint displacement is expected",
            "same_saved_joint_vector": _exactly_matches(
                _task_home_positions(logic.taskHomeRecord(parameter_node)),
                home_positions,
            ),
        }
        if (
            not home_validation.success
            or home_validation.details.get("moveItPlanRequired") is not False
            or int(home_validation.details.get("moveItPlanWaypointCount", -1)) != 1
            or not report["setup"]["task_home_validation"]["same_saved_joint_vector"]
        ):
            raise RuntimeError(
                "Saved Task Home did not validate through the guarded no-motion branch."
            )

        post_home_task_core = _current_task_core(logic, parameter_node)
        post_home_record = logic.taskHomeRecord(parameter_node)
        report["setup"]["task_home_validation"].update(
            home_fingerprint_before=runtime_identity["home_fingerprint"],
            home_fingerprint_after=fingerprint(post_home_record.to_dict()),
            home_revision_before=runtime_identity["home_revision"],
            home_revision_after=int(post_home_record.revision),
            home_joint_positions_after=_task_home_positions(post_home_record),
        )
        if (
            post_home_task_core != saved_identity["task_core"]
            or _task_home_positions(post_home_record) != home_positions
            or int(post_home_record.revision) != int(runtime_identity["home_revision"])
            or str(post_home_record.base_fingerprint) != runtime_identity["base_fingerprint"]
            or str(post_home_record.robot_profile_fingerprint)
            != runtime_identity["robot_profile_fingerprint"]
            or _scene_evidence(logic, parameter_node)["audit_fingerprint"]
            != runtime_identity["scene"]["audit_fingerprint"]
        ):
            raise RuntimeError(
                "No-motion Home revalidation changed a protected base/task/limits/profile/scene input."
            )
        report["setup"]["identity_after_no_motion_home_revalidation"] = {
            "branch_id": branch_id,
            "task_core": post_home_task_core,
            "task_core_fingerprint": fingerprint(post_home_task_core),
            "base_fingerprint": str(logic.robotBaseFingerprint(parameter_node)),
            "limits_fingerprint": str(logic.step6TaskLimitsFingerprint(parameter_node)),
            "robot_profile_fingerprint": str(logic.robotProfileFingerprint()),
            "scene": _scene_evidence(logic, parameter_node),
            "home_fingerprint": fingerprint(post_home_record.to_dict()),
            "home_revision": int(post_home_record.revision),
            "home_joint_positions_si": _task_home_positions(post_home_record),
        }
        phase = "task_reconfirmation"
        confirmation = facade.confirmTask()
        report["setup"]["task_reconfirmation"] = {
            "success": bool(confirmation.success),
            "code": str(confirmation.code),
            "message": str(confirmation.message),
        }
        if not confirmation.success or logic.confirmedTaskFreshnessIssues(parameter_node):
            raise RuntimeError("Reconfirm unchanged task after Home validation failed.")
        current_identity = _identity(logic, parameter_node, facade)
        if any(
            current_identity[key] != saved_identity[key]
            for key in (
                "branch_id", "base_fingerprint", "limits_fingerprint",
                "robot_profile_fingerprint", "task_core_fingerprint",
            )
        ) or (
            current_identity["task_core"] != post_home_task_core
            or current_identity["scene"]["audit_fingerprint"]
            != runtime_identity["scene"]["audit_fingerprint"]
            or current_identity["scene"]["source_object_ids"]
            != runtime_identity["scene"]["source_object_ids"]
            or current_identity["scene"]["acknowledged_object_ids"]
            != runtime_identity["scene"]["acknowledged_object_ids"]
        ):
            raise RuntimeError("Task reconfirmation changed a protected fixture identity.")
        report["setup"]["task_reconfirmation"].update(
            task_fingerprint_before=saved_identity["task_fingerprint"],
            task_fingerprint_after=current_identity["task_fingerprint"],
            protected_inputs_fingerprint_before=saved_identity["task_core_fingerprint"],
            protected_inputs_fingerprint_after=current_identity["task_core_fingerprint"],
            home_fingerprint_before=runtime_identity["home_fingerprint"],
            home_fingerprint_after=current_identity["home_fingerprint"],
        )

        widget._setWorkflowStage(10, ensureVisible=True)
        widget._configureRobotSimulationShellSubstep(5)
        widget._updateStep6PlanningUi()
        panel = widget._robotSimulationPanel
        if panel is None or not panel.guardedManualJogButton.enabled:
            raise RuntimeError("Production Guarded Jog UI is not ready after current setup.")
        initial = _actual_joint_state(facade)
        if not (
            _exactly_matches(initial["accepted_si"], home_positions)
            and _exactly_matches(initial["monitored_si"], home_positions)
            and _exactly_matches(initial["displayed_si"], home_positions)
            and _exactly_matches(panel._manualJogAcceptedJointPositionsSi, home_positions)
        ):
            raise RuntimeError("UI, displayed robot, accepted state and monitor disagree at baseline.")

        baseline_display = _display_values(initial["accepted_si"])
        if any(abs(value - round(value, 2)) > 1e-10 for value in baseline_display):
            raise RuntimeError(
                "The visible numeric controls cannot preserve the exact current joint vector."
            )
        accepted_target = dict(initial["accepted_si"])
        plus = dict(accepted_target)
        minus = dict(accepted_target)
        plus[JOINT_NAMES[0]] += math.radians(ACCEPTED_DELTA_DEG)
        minus[JOINT_NAMES[0]] -= math.radians(ACCEPTED_DELTA_DEG)
        accepted_limits = _within_both_limits(logic, parameter_node, plus)
        if accepted_limits is None:
            accepted_limits = _within_both_limits(logic, parameter_node, minus)
            if accepted_limits is None:
                raise RuntimeError(
                    "Neither fixed J1 +/- 0.1 degree request fits both reviewed and mechanical limits."
                )
            accepted_target = minus
            accepted_direction = "J1 - 0.1 degree"
            accepted_j1_sign = -1
        else:
            accepted_target = plus
            accepted_direction = "J1 + 0.1 degree"
            accepted_j1_sign = 1
        theoretical_accepted_target = dict(accepted_target)
        if any(abs(value - round(value, 2)) > 1e-10 for value in _display_values(accepted_target)):
            raise RuntimeError("The fixed small J1 jog cannot be represented without changing other joints.")
        panel._setManualJogDraftValues(_display_values(accepted_target), notify=True)
        accepted_target = _finite_vector(panel.manualJogJointPositionsSi())
        accepted_limits = _within_both_limits(logic, parameter_node, accepted_target)
        if accepted_limits is None:
            raise RuntimeError("The visible J1 draft falls outside a current reviewed or mechanical limit.")
        if not _matches_at_display_precision(accepted_target, theoretical_accepted_target):
            raise RuntimeError("The visible J1 draft differs from the fixed 0.1 degree request.")
        report["setup"]["manual_request_limits"] = accepted_limits
        report["setup"]["accepted_request_direction"] = accepted_direction

        rejection_plan, rejection_skip_reason = _rejection_plan(
            os.environ.get("DENTOBOT_MANUAL_JOG_REJECTION_PLAN_JSON", ""),
            case_sha256=case_sha256,
            fixture_identity_value=saved_identity["fixture_identity"],
            finite_vector=_finite_vector,
        )
        if rejection_plan is not None:
            if not _matches_at_display_precision(
                rejection_plan["starting_positions_si"], accepted_target
            ):
                raise RuntimeError(
                    "Pre-reviewed rejection vector is not bound to the exact accepted-test starting state."
                )
            rejected_display_request = _display_values(
                rejection_plan["requested_positions_si"]
            )
            panel._setManualJogDraftValues(rejected_display_request, notify=True)
            representable_rejection = _finite_vector(panel.manualJogJointPositionsSi())
            if not _exactly_matches(
                representable_rejection, rejection_plan["requested_positions_si"]
            ):
                raise RuntimeError(
                    "The exact pre-reviewed rejection vector is not representable in the visible controls."
                )
            if _within_both_limits(logic, parameter_node, representable_rejection) is None:
                raise RuntimeError("Pre-reviewed rejection vector is outside current limits.")
            panel._setManualJogDraftValues(_display_values(accepted_target), notify=True)
            if not rejection_plan["review_reference"]:
                raise RuntimeError("Rejection plan requires a non-empty review_reference.")

        phase = "pre_jog_evidence"
        panel._setManualJogDraftValues(_display_values(accepted_target), notify=True)
        panel.setManualJogStatus(
            "unknown", "PRE-JOG: display-only draft; no guard request has been sent."
        )
        before = _identity(logic, parameter_node, facade)
        before_state = _actual_joint_state(facade)
        panel.setManualJogAcceptedState(before_state["accepted_si"])
        report["screenshots"]["pre_jog"] = _capture_screenshots(
            "pre-jog-context", evidence_dir
        )
        phase = "accepted_jog"
        accepted_ui = _guard_click(widget, panel, accepted_target)
        accepted_target = dict(accepted_ui["draft_positions_si"])
        accepted_after = _wait_until(
            lambda: (
                _actual_joint_state(facade)
                if _exactly_matches(bridge.last_accepted_joint_positions_si(), accepted_target)
                and _exactly_matches(bridge.monitored_joint_positions_si(), accepted_target)
                else None
            )
        ) or _actual_joint_state(facade)
        accepted_identity_after = _identity(logic, parameter_node, facade)
        accepted_identity_stable = _request_identity_stable(before, accepted_identity_after)
        accepted_native = accepted_ui["evidence"].get("nativeGuardEvidence") or {}
        report["scenarios"]["accepted"] = {
            "status": "PASS" if (
                accepted_ui["evidence"].get("guardAccepted") is True
                and accepted_ui["evidence"].get("manualJogStatus") == "accepted"
                and accepted_ui["evidence"].get("identityStatus") == "current"
                and accepted_native.get("freshResponse") is True
                and accepted_native.get("accepted") is True
                and accepted_native.get("worldObjectEvidencePresent") is True
                and tuple(accepted_native.get("worldObjectIds") or ()) == expected_ids
                and _exactly_matches(accepted_native.get("requestedPositionsSi"), accepted_target)
                and _exactly_matches(accepted_native.get("acceptedPositionsSi"), accepted_target)
                and _exactly_matches(accepted_ui["evidence"].get("acceptedJointPositionsSi"), accepted_target)
                and _exactly_matches(accepted_ui["panel_accepted_positions_si"], accepted_target)
                and _exactly_matches(accepted_after["accepted_si"], accepted_target)
                and _exactly_matches(accepted_after["monitored_si"], accepted_target)
                and _exactly_matches(accepted_after["displayed_si"], accepted_target)
                and accepted_identity_stable
            ) else "FAIL",
            "timestamp_utc": _utc_now(),
            "direction": accepted_direction,
            "requested_positions_si": accepted_target,
            "native_guard_evidence": accepted_native,
            "identity_stable": accepted_identity_stable,
            "accepted_before": before_state,
            "ui_result": accepted_ui,
            "accepted_after": accepted_after,
            "identity_before": before,
            "identity_after": accepted_identity_after,
            "raw_guard_status": _raw_guard_evidence(bridge.joint_command_status()),
        }
        phase = "accepted_jog_screenshots"
        report["screenshots"]["accepted"] = _capture_screenshots(
            "accepted-result", evidence_dir
        )
        if report["scenarios"]["accepted"]["status"] != "PASS":
            raise RuntimeError(
                "Accepted manual jog did not produce matching acknowledged accepted and monitored state."
            )

        phase = "rejection_jog"
        if rejection_plan is None:
            report["scenarios"]["rejected"] = {
                "status": "NOT_RUN",
                "reason": rejection_skip_reason,
            }
        else:
            report["required_screenshot_files"].extend(
                ["rejected-result-ui.png", "rejected-result-viewport.png"]
            )
            rejected_target = dict(rejection_plan["requested_positions_si"])
            reject_before = _identity(logic, parameter_node, facade)
            reject_state_before = _actual_joint_state(facade)
            if not _exactly_matches(reject_state_before["accepted_si"], rejection_plan["starting_positions_si"]):
                raise RuntimeError("Accepted simulation state changed before the rejection request.")
            rejected_ui = _guard_click(widget, panel, rejected_target)
            rejected_state_after = _actual_joint_state(facade)
            rejected_identity_after = _identity(logic, parameter_node, facade)
            rejected_raw = rejected_ui["evidence"].get("nativeGuardEvidence") or {}
            rejected_identity_stable = _request_identity_stable(
                reject_before, rejected_identity_after
            )
            rejected_pass = bool(
                rejected_ui["evidence"].get("guardAccepted") is False
                and rejected_ui["evidence"].get("manualJogStatus") == "rejected"
                and rejected_raw.get("freshResponse") is True
                and rejected_raw.get("accepted") is False
                and rejected_ui["evidence"].get("rawGuardOutcome") == "rejected"
                and rejected_raw.get("worldObjectEvidencePresent") is True
                and tuple(rejected_raw.get("worldObjectIds") or ()) == expected_ids
                and _exactly_matches(rejected_raw.get("requestedPositionsSi"), rejected_target)
                and _exactly_matches(rejected_raw.get("acceptedPositionsSi"), reject_state_before["accepted_si"])
                and _exactly_matches(rejected_state_after["accepted_si"], reject_state_before["accepted_si"])
                and _exactly_matches(rejected_state_after["monitored_si"], reject_state_before["monitored_si"])
                and _exactly_matches(rejected_ui["draft_positions_si"], rejected_target)
                and _exactly_matches(rejected_ui["panel_accepted_positions_si"], reject_state_before["accepted_si"])
                and rejected_identity_stable
            )
            report["scenarios"]["rejected"] = {
                "status": "PASS" if rejected_pass else "FAIL",
                "timestamp_utc": _utc_now(),
                "requested_positions_si": rejected_target,
                "native_guard_evidence": rejected_raw,
                "identity_stable": rejected_identity_stable,
                "review_reference": rejection_plan["review_reference"],
                "accepted_before": reject_state_before,
                "ui_result": rejected_ui,
                "accepted_after": rejected_state_after,
                "identity_before": reject_before,
                "identity_after": rejected_identity_after,
                "raw_guard_status": _raw_guard_evidence(bridge.joint_command_status()),
                "collision_pair": [
                    rejected_raw.get("firstBody"), rejected_raw.get("secondBody")
                ],
                "closeup_unavailable_reason": (
                    "No alternate camera view was reconstructed; screenshots retain the live current view."
                ),
            }
            report["screenshots"]["rejected"] = _capture_screenshots(
                "rejected-result", evidence_dir
            )
            if not rejected_pass:
                raise RuntimeError(
                    "Pre-reviewed rejection request did not produce a fresh guard rejection with unchanged accepted state."
                )

        current_accepted = _actual_joint_state(facade)["accepted_si"]
        unavailable_target = dict(current_accepted)
        unavailable_direction = "-" if accepted_j1_sign > 0 else "+"
        unavailable_target[JOINT_NAMES[0]] += math.radians(
            -ACCEPTED_DELTA_DEG if unavailable_direction == "-" else ACCEPTED_DELTA_DEG
        )
        if _within_both_limits(logic, parameter_node, unavailable_target) is None:
            raise RuntimeError("Fixed opposite-direction unknown draft is outside current limits.")
        panel._setManualJogDraftValues(_display_values(unavailable_target), notify=True)
        unavailable_target = _finite_vector(panel.manualJogJointPositionsSi())
        if (
            _within_both_limits(logic, parameter_node, unavailable_target) is None
            or not _matches_at_display_precision(
                unavailable_target,
                {
                    **current_accepted,
                    JOINT_NAMES[0]: current_accepted[JOINT_NAMES[0]]
                    + math.radians(
                        -ACCEPTED_DELTA_DEG
                        if unavailable_direction == "-"
                        else ACCEPTED_DELTA_DEG
                    ),
                },
            )
        ):
            raise RuntimeError("Fixed opposite-direction unknown draft cannot be represented within limits.")
        phase = "unavailable_jog_probe"
        unavailable_before = _identity(logic, parameter_node, facade)
        unavailable_state_before = _actual_joint_state(facade)
        original_apply = getattr(facade._bridge, "apply_joint_positions_si_to_motion_control", None)
        if not callable(original_apply):
            raise RuntimeError("Cannot construct the explicitly labeled unavailable-bridge probe.")
        setattr(facade._bridge, "apply_joint_positions_si_to_motion_control", None)
        try:
            unavailable_ui = _guard_click(widget, panel, unavailable_target)
        finally:
            setattr(facade._bridge, "apply_joint_positions_si_to_motion_control", original_apply)
        unavailable_state_after = _actual_joint_state(facade)
        unavailable_identity_after = _identity(logic, parameter_node, facade)
        unavailable_evidence = unavailable_ui["evidence"]
        unavailable_identity_stable = _request_identity_stable(
            unavailable_before, unavailable_identity_after
        )
        unavailable_pass = bool(
            unavailable_evidence.get("guardAccepted") is None
            and unavailable_evidence.get("rawGuardOutcome") == "not_submitted"
            and unavailable_evidence.get("manualJogStatus") == "unknown"
            and unavailable_ui["status_state"] == "blocked"
            and _exactly_matches(unavailable_ui["draft_positions_si"], unavailable_target)
            and _exactly_matches(unavailable_ui["panel_accepted_positions_si"], unavailable_state_before["accepted_si"])
            and _exactly_matches(unavailable_state_after["accepted_si"], unavailable_state_before["accepted_si"])
            and _exactly_matches(unavailable_state_after["monitored_si"], unavailable_state_before["monitored_si"])
            and _exactly_matches(unavailable_state_after["displayed_si"], unavailable_state_before["displayed_si"])
            and unavailable_evidence.get("nativeGuardEvidence") is None
            and unavailable_identity_stable
        )
        report["scenarios"]["unavailable"] = {
            "status": "PASS" if unavailable_pass else "FAIL",
            "timestamp_utc": _utc_now(),
            "probe_kind": "local_bridge_api_unavailable_probe",
            "native_request_submitted": False,
            "native_stale_response_tested": False,
            "requested_positions_si": unavailable_target,
            "native_guard_evidence": None,
            "identity_stable": unavailable_identity_stable,
            "accepted_before": unavailable_state_before,
            "ui_result": unavailable_ui,
            "accepted_after": unavailable_state_after,
            "identity_before": unavailable_before,
            "identity_after": unavailable_identity_after,
            "raw_guard_status": _raw_guard_evidence(bridge.joint_command_status()),
        }
        phase = "unknown_result_screenshots"
        report["screenshots"]["unavailable"] = _capture_screenshots(
            "unknown-result", evidence_dir
        )
        if not unavailable_pass:
            raise RuntimeError("Unavailable bridge probe did not retain the draft/state as unknown.")

        all_pass = all(
            report["scenarios"][name]["status"] == "PASS"
            for name in ("accepted", "rejected", "unavailable")
        )
        report["status"] = "PASS" if all_pass else "PARTIAL"
        report["finished_at_utc"] = _utc_now()
        report["limitations"] = [
            "Unavailable scenario is a local bridge-API-unavailable probe, not a native stale raw reply.",
            "Raw guard status has no request ID or policy fingerprint; the façade's current correlation limits remain visible.",
            "Headless evidence does not replace Tarun's normal-window simulation verdict.",
        ]
        phase = "report_write"
        _write_report(report_path, report)
        return report
    except Exception as exc:
        report["status"] = "FAIL"
        report["failure_phase"] = phase
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["finished_at_utc"] = _utc_now()
        _write_report(report_path, report)
        raise


try:
    report = run()
    if report["status"] == "PASS":
        print("DENTOBOT_MANUAL_JOG_HEADLESS_PASS", flush=True)
        status = 0
    else:
        print("DENTOBOT_MANUAL_JOG_HEADLESS_PARTIAL", flush=True)
        status = 0
    print(json.dumps(report, indent=2, sort_keys=True, default=str), flush=True)
except Exception as exc:
    print(f"DENTOBOT_MANUAL_JOG_HEADLESS_FAILED: {exc}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
    status = 1
finally:
    try:
        bridge.disconnect_dentobot_motion_control([])
        bridge.shutdown_slicer_adapter()
    except Exception:
        pass
    slicer.app.exit(status)
