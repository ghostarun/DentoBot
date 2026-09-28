"""Fresh-process, read-only qualification of the saved FDI11 five-DOF case.

Run only in a fresh Slicer process, with DENTOBOT_HEADED_CASE_SOURCE,
DENTOBOT_HEADED_CASE_SHA256, DENTOBOT_HEADED_EVIDENCE_DIR and the four
DENTOBOT_HEADED_GIT_* provenance variables supplied by the reviewed host
launcher. This script never connects ROS, jogs, plans, previews, or saves.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
from datetime import datetime, timezone

import slicer
import vtk


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
TESTING = ROOT / "Testing"
for _path in (PYTHON, TESTING):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from DENTOCaseBundle import validate_case_bundle  # noqa: E402
from DENTOStep6State import (  # noqa: E402
    JOINT_NAMES,
    MANUAL_SIMULATION_BASE_SOURCE,
    canonical_json,
    fingerprint,
    parse_manual_simulation_record,
    parse_robot_environment_snapshot,
    parse_task_home,
    parse_task_snapshot,
    parse_trajectory_registry,
)


EXPECTED_HOST_ROOT = "/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-renovation"
EXPECTED_CONTAINER_ROOT = "/workspace/ros2_ws/src/DentoBot-step6-renovation"
EXPECTED_BRANCH = "feature/step6-workflow-renovation-20260925"
EXPECTED_CASE = Path(
    "/workspace/data/Slicer_Saved/SampleStudy1/SEPT24/"
    "sept28_fdi11_step6_five_dof_acceptance.dentocase"
)
EXPECTED_JOINTS = tuple(JOINT_NAMES)
JOINT_LABELS = ("J1", "J2", "J3", "J4", "J5")
PROVENANCE_SOURCE_FILES = (
    "DENTOWorkflow/Resources/Python/DENTOCaseBundle.py",
    "DENTOWorkflow/Resources/Python/DENTOStep6State.py",
    "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_case_backend.py",
    "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_lifecycle.py",
    "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_views.py",
    "Testing/run_dentobot_step6_case_qualification.py",
)
CHECKS = (
    "checkout_provenance",
    "case_sha_and_bundle_validation",
    "saved_fdi11_task_branch_base_home_limits",
    "strict_fresh_open",
    "step6_active_branch_offline_task_home_restore",
    "opened_jaw_display",
    "five_dof_state_and_limits",
    "ros_disconnected",
    "historical_records_display_only_if_present",
    "no_live_plan_or_preview_authority",
    "source_case_unchanged",
    "ui_and_viewport_screenshots",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mapping(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} is missing or has an unknown shape.")
    return value


def _finite_values(values, count: int, label: str) -> list[float]:
    if isinstance(values, (str, bytes, dict)):
        raise ValueError(f"{label} must contain exactly {count} finite numbers.")
    try:
        sequence = list(values)
    except TypeError as exc:
        raise ValueError(f"{label} must contain exactly {count} finite numbers.") from exc
    if any(isinstance(value, (bool, str, bytes)) for value in sequence):
        raise ValueError(f"{label} must contain exactly {count} finite numbers.")
    result = [float(value) for value in sequence]
    if len(result) != count or not all(math.isfinite(value) for value in result):
        raise ValueError(f"{label} must contain exactly {count} finite numbers.")
    return result


def _require_match(actual, expected, label: str, tolerance: float = 1e-9) -> None:
    first = _finite_values(actual, len(expected), label)
    second = _finite_values(expected, len(expected), f"saved {label}")
    if any(abs(left - right) > tolerance for left, right in zip(first, second)):
        raise ValueError(f"Restored {label} differs from saved case evidence.")


def _private_evidence_dir() -> Path:
    value = os.environ.get("DENTOBOT_HEADED_EVIDENCE_DIR", "").strip()
    if not value:
        raise RuntimeError("Set DENTOBOT_HEADED_EVIDENCE_DIR to a fresh run evidence directory.")
    path = Path(value).expanduser()
    if not path.is_absolute() or path.is_symlink():
        raise RuntimeError("DENTOBOT_HEADED_EVIDENCE_DIR must be an absolute real directory.")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir():
        raise RuntimeError("DENTOBOT_HEADED_EVIDENCE_DIR is not a directory.")
    if any(path.iterdir()):
        raise RuntimeError("DENTOBOT_HEADED_EVIDENCE_DIR must be a fresh, empty run directory.")
    path = path.resolve(strict=True)
    path.chmod(0o700)
    info = path.stat()
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise RuntimeError("DENTOBOT_HEADED_EVIDENCE_DIR must belong to this user.")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise RuntimeError("DENTOBOT_HEADED_EVIDENCE_DIR must be private (0700 or stricter).")
    return path


def _checkout_evidence() -> dict:
    names = (
        "DENTOBOT_HEADED_HOST_CHECKOUT_ROOT",
        "DENTOBOT_HEADED_GIT_BRANCH",
        "DENTOBOT_HEADED_GIT_HEAD",
        "DENTOBOT_HEADED_GIT_STATUS_SHA256",
    )
    values = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError("Missing host Git provenance: " + ", ".join(missing))
    if values[names[0]] != EXPECTED_HOST_ROOT:
        raise RuntimeError("Host launcher reported an unexpected renovation checkout path.")
    if str(ROOT.resolve()) != EXPECTED_CONTAINER_ROOT:
        raise RuntimeError("Mounted DentoBot checkout path is not the renovation checkout.")
    if values[names[1]] != EXPECTED_BRANCH:
        raise RuntimeError("Host launcher reported an unexpected renovation branch.")
    if re.fullmatch(r"[0-9a-fA-F]{40}", values[names[2]]) is None:
        raise RuntimeError("DENTOBOT_HEADED_GIT_HEAD must be a full 40-character SHA.")
    if re.fullmatch(r"[0-9a-fA-F]{64}", values[names[3]]) is None:
        raise RuntimeError("DENTOBOT_HEADED_GIT_STATUS_SHA256 must be a 64-character SHA.")
    return {
        "checkout_root": str(ROOT.resolve()),
        "host_checkout_root": values[names[0]],
        "branch": values[names[1]],
        "head_commit": values[names[2]].lower(),
        "worktree_status_sha256": values[names[3]].lower(),
        "source_sha256": {
            name: _sha256_file(ROOT / name) for name in PROVENANCE_SOURCE_FILES
        },
    }


def _saved_case_evidence(workflow: dict) -> dict:
    step6 = _mapping(workflow.get("step6"), "saved Step 6 lineage")
    registry = parse_trajectory_registry(
        _mapping(step6.get("trajectoryRegistry"), "saved PreparedBranch registry")
    )
    saved_task = parse_task_snapshot(
        _mapping(step6.get("confirmedTask"), "saved confirmed FDI11 task")
    )
    saved_home = parse_task_home(
        _mapping(step6.get("taskHome"), "saved Task Home")
    )
    environment = parse_robot_environment_snapshot(
        _mapping(step6.get("environment"), "saved robot environment")
    )
    proposal = _mapping(step6.get("assistedLimitProposal"), "saved reviewed limits")
    if tuple(str(value) for value in proposal.get("joint_names", ())) != EXPECTED_JOINTS:
        raise ValueError("Saved reviewed limits do not contain exactly J1–J5 in order.")
    minima = _finite_values(proposal.get("minimum_display", ()), 5, "saved limit minima")
    maxima = _finite_values(proposal.get("maximum_display", ()), 5, "saved limit maxima")
    if proposal.get("reviewed") is not True or any(low >= high for low, high in zip(minima, maxima)):
        raise ValueError("Saved five-DOF task limits are not reviewed finite ranges.")
    if saved_task.limits_fingerprint != environment.limits_fingerprint:
        raise ValueError("Saved confirmed task and robot environment disagree on joint limits.")
    if environment.workspace_fingerprint != fingerprint(canonical_json(proposal)):
        raise ValueError("Saved reviewed limits do not match their environment fingerprint.")
    if tuple(saved_home.joint_names) != EXPECTED_JOINTS:
        raise ValueError("Saved Task Home does not contain exactly J1–J5 in canonical order.")
    if saved_home.runtime_validation_status != "Validated":
        raise ValueError("Saved Task Home is not runtime-validated in the saved lineage.")
    _require_match(
        saved_home.joint_positions_si,
        environment.task_home_configuration.get("joint_positions_si", ()),
        "saved Task Home joint values",
    )
    if saved_home.base_fingerprint != environment.base_fingerprint:
        raise ValueError("Saved Task Home does not match the saved Base fingerprint.")

    teeth = _mapping(registry.get("teeth"), "saved FDI registry teeth")
    fdi11 = _mapping(teeth.get("FDI11"), "saved FDI11 registry entry")
    branch_id = str(registry.get("selected_branch_id") or "")
    branches = _mapping(registry.get("prepared_branches"), "saved PreparedBranches")
    branch = _mapping(branches.get(branch_id), "saved selected PreparedBranch")
    if not branch_id or branch.get("state") != "Current":
        raise ValueError("The selected FDI11 PreparedBranch is absent or not Current.")
    if branch.get("target_id") != fdi11.get("target_id"):
        raise ValueError("The selected PreparedBranch does not belong to FDI11.")
    if saved_task.target_segment_id != str(fdi11.get("segment_id") or ""):
        raise ValueError("The saved confirmed task is not the FDI11 task.")
    fdi11_slots = _mapping(fdi11.get("trajectory_set"), "saved FDI11 trajectory set").get("slots")
    if not isinstance(fdi11_slots, list):
        raise ValueError("The saved FDI11 trajectory slots are unavailable.")
    fdi11_branch_ids = {
        str(branch_value)
        for slot in fdi11_slots
        for branch_value in _mapping(slot, "saved FDI11 trajectory slot").get("prepared_branch_ids", ())
    }
    if branch_id not in fdi11_branch_ids:
        raise ValueError("The selected PreparedBranch is not linked to an FDI11 trajectory.")

    base_placement = _mapping(step6.get("basePlacement"), "saved Base placement")
    foundation = _mapping(workflow.get("caseFoundation"), "saved Case Foundation")
    foundation_pose = _mapping(foundation.get("pose"), "saved Case Foundation pose")
    foundation_base = _mapping(foundation.get("base"), "saved Case Foundation Base")
    base_matrix = _finite_values(environment.base_matrix, 16, "saved Base matrix")
    if base_placement.get("fingerprint") != environment.base_fingerprint:
        raise ValueError("Saved Base lineage and robot environment fingerprints differ.")
    if (
        base_placement.get("status") != "ProvisionalLocked"
        or environment.base_status != "ProvisionalLocked"
        or base_placement.get("source") != MANUAL_SIMULATION_BASE_SOURCE
        or environment.base_authority != MANUAL_SIMULATION_BASE_SOURCE
        or environment.base_locked is not True
        or base_placement.get("sourceRevision") != environment.base_revision
        or foundation_pose.get("eligible") is not True
        or foundation_pose.get("code") != "VALID"
        or foundation_base.get("eligible") is not True
        or foundation_base.get("code") != "VALID"
    ):
        raise ValueError("Saved simulation Base source/status/lock or Case Foundation eligibility is not current.")
    return {
        "saved_step6_lineage_present": True,
        "target_tooth": "FDI11",
        "confirmed_task": saved_task.to_dict(),
        "selected_branch": {
            "branch_id": branch_id,
            "target_id": branch.get("target_id"),
            "state": branch.get("state"),
            "trajectory_ids": list(branch.get("trajectory_ids") or ()),
            "pairing_intent": branch.get("pairing_intent"),
        },
        "base": {
            "matrix_to_world_ras": base_matrix,
            "fingerprint": environment.base_fingerprint,
            "status": base_placement.get("status"),
            "source": base_placement.get("source"),
            "revision": base_placement.get("sourceRevision"),
            "locked": environment.base_locked,
            "case_foundation_pose": foundation_pose,
            "case_foundation_base": foundation_base,
        },
        "task_home": saved_home.to_dict(),
        "reviewed_limits": {
            "joint_names": list(EXPECTED_JOINTS),
            "display_joint_labels": list(JOINT_LABELS),
            "minimum_display": minima,
            "maximum_display": maxima,
            "reviewed": True,
            "fingerprint": environment.limits_fingerprint,
        },
        "robot_environment_fingerprint": environment.environment_fingerprint,
    }


def _capture_screenshots(label: str, evidence_dir: Path) -> dict:
    window = slicer.util.mainWindow()
    layout_manager = slicer.app.layoutManager()
    if window is None or layout_manager is None:
        raise RuntimeError("Slicer main window or layout manager is unavailable.")
    view_widget = layout_manager.threeDWidget(0)
    if view_widget is None:
        raise RuntimeError("Slicer 3D viewport is unavailable.")
    window.show()
    slicer.app.processEvents()
    ui_path = evidence_dir / f"{label}-ui.png"
    viewport_path = evidence_dir / f"{label}-viewport.png"
    if ui_path.exists() or viewport_path.exists():
        raise RuntimeError("Refusing to overwrite a qualification screenshot.")
    pixmap = window.grab()
    if pixmap.isNull() or not pixmap.save(str(ui_path)):
        raise RuntimeError("Could not capture the Slicer UI screenshot.")
    view = view_widget.threeDView()
    view.forceRender()
    capture = vtk.vtkWindowToImageFilter()
    capture.SetInput(view.renderWindow())
    capture.ReadFrontBufferOff()
    capture.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(viewport_path))
    writer.SetInputConnection(capture.GetOutputPort())
    writer.Write()
    if not viewport_path.is_file() or viewport_path.stat().st_size <= 0:
        raise RuntimeError("Could not capture the Slicer viewport screenshot.")
    return {
        "ui": {"path": ui_path.name, "sha256": _sha256_file(ui_path)},
        "viewport": {"path": viewport_path.name, "sha256": _sha256_file(viewport_path)},
    }


def _restored_case_evidence(widget, saved: dict) -> dict:
    logic = widget.logic
    panel = widget._robotSimulationPanel
    facade = widget._robotWorkflowFacade
    parameter = widget._parameterNode
    if not all((logic, panel, facade, parameter)):
        raise RuntimeError("Strict case open did not restore the Step 6 workflow API.")
    stage_index = int(parameter.workflowStageIndex)
    stage_entries = widget._workflowStageEntries()
    if not stage_entries:
        raise RuntimeError("Workflow stage identity is unavailable.")
    step6_index = len(stage_entries) - 1
    ui_stage_index = int(widget.ui.workflowStageComboBox.currentIndex)
    if stage_index != step6_index or ui_stage_index != step6_index:
        raise RuntimeError("Fresh reopen did not restore the saved Step 6 stage.")

    registry = parse_trajectory_registry(str(parameter.step6TrajectoryRegistryJson or ""))
    selected_branch = str(registry.get("selected_branch_id") or "")
    if selected_branch != saved["selected_branch"]["branch_id"]:
        raise RuntimeError("The FDI11 PreparedBranch selection changed on reopen.")
    if bool(parameter.step6PlanningContextImported):
        raise RuntimeError("Offline reopen unexpectedly restored active Step 6 planning context.")
    branch_result = logic.evaluatePreparedBranchEligibility(
        parameter, selected_branch, registry=registry
    )
    if branch_result.get("eligible") is not True or branch_result.get("reason") != "VALID":
        raise RuntimeError("The restored FDI11 PreparedBranch is not strictly current.")
    if logic.confirmedTaskRecord(parameter) is not None or str(parameter.step6ConfirmedTaskJson or "").strip():
        raise RuntimeError("Offline case open unexpectedly restored live task authority.")

    home = logic.taskHomeRecord(parameter)
    if home is None or home.runtime_validation_status != "Unreviewed":
        raise RuntimeError("Offline Task Home review status is missing or not Unreviewed.")
    if tuple(home.joint_names) != EXPECTED_JOINTS:
        raise RuntimeError("Restored Task Home does not contain exactly J1–J5.")
    if home.revision != saved["task_home"]["revision"]:
        raise RuntimeError("Offline Task Home revision differs from saved lineage.")
    _require_match(home.joint_positions_si, saved["task_home"]["joint_positions_si"], "Task Home joints")
    if home.base_fingerprint != saved["base"]["fingerprint"]:
        raise RuntimeError("Restored Task Home is not tied to the saved Base.")

    base = parameter.robotBaseTransform
    if base is None or not logic.isRobotBaseTransformNode(base):
        raise RuntimeError("Restored robot Base transform is unavailable.")
    matrix = vtk.vtkMatrix4x4()
    base.GetMatrixTransformToWorld(matrix)
    base_matrix = [matrix.GetElement(row, column) for row in range(4) for column in range(4)]
    _require_match(base_matrix, saved["base"]["matrix_to_world_ras"], "Base matrix", 1e-6)
    base_fingerprint = logic.robotBaseFingerprint(parameter)
    if base_fingerprint != saved["base"]["fingerprint"]:
        raise RuntimeError("Restored Base fingerprint differs from saved case evidence.")
    base_status = str(parameter.step6BasePlacementStatus or "")
    base_source = str(parameter.step6BasePlacementSource or "")
    base_revision = int(parameter.step6BasePlacementRevision)
    base_locked = bool(parameter.robotBaseMountLocked)
    if (
        base_status != saved["base"]["status"]
        or base_source != saved["base"]["source"]
        or base_revision != saved["base"]["revision"]
        or base_locked != saved["base"]["locked"]
    ):
        raise RuntimeError("Restored simulation Base status/source/revision/lock differs from saved lineage.")
    foundation = logic.evaluateCaseFoundationEligibility(parameter)
    for component_name in ("pose", "base"):
        component = _mapping(foundation.get(component_name), f"restored Case Foundation {component_name}")
        if component.get("eligible") is not True or component.get("code") != "VALID":
            raise RuntimeError(f"Restored Case Foundation {component_name} is not eligible.")
    base_issues = logic.step6BasePlacementFreshnessIssues(parameter)
    home_issues = logic.taskHomeFreshnessIssues(parameter)
    if base_issues or home_issues:
        raise RuntimeError("Restored Base/Home is not current: " + " ".join((*base_issues, *home_issues)))

    limits = logic.getTaskJointLimits(parameter)
    minimums = _finite_values(limits.as_display_vector(), 5, "restored limit minima")
    maximums = _finite_values(limits.as_display_max_vector(), 5, "restored limit maxima")
    if logic.assistedTaskLimitsReviewed(parameter) is not True:
        raise RuntimeError("Restored five-DOF limits are not marked reviewed.")
    limit_fingerprint = logic.step6TaskLimitsFingerprint(parameter)
    if limit_fingerprint != saved["reviewed_limits"]["fingerprint"]:
        raise RuntimeError("Restored five-DOF limits differ from saved task evidence.")
    _require_match(minimums, saved["reviewed_limits"]["minimum_display"], "limit minima")
    _require_match(maximums, saved["reviewed_limits"]["maximum_display"], "limit maxima")

    state = facade.currentRobotState()
    if tuple(state.joint_names) != EXPECTED_JOINTS or set(state.joint_positions_si) != set(EXPECTED_JOINTS):
        raise RuntimeError("Restored arm state is not exactly the canonical J1–J5 vector.")
    joint_values = _finite_values(
        [state.joint_positions_si[name] for name in EXPECTED_JOINTS],
        5,
        "restored current J1–J5 state",
    )
    current_joints = dict(zip(EXPECTED_JOINTS, joint_values))
    controls = getattr(panel, "manualJogJointControls", None)
    if not isinstance(controls, dict) or tuple(controls) != EXPECTED_JOINTS:
        raise RuntimeError("Restored Manual Jog controls do not contain exactly J1–J5.")

    source = parameter.teethSegmentation
    if source is None or source.GetDisplayNode() is None:
        raise RuntimeError("Closed-source segmentation display is unavailable.")
    source_display = source.GetDisplayNode()
    segment_ids = vtk.vtkStringArray()
    source.GetSegmentation().GetSegmentIDs(segment_ids)
    if segment_ids.GetNumberOfValues() == 0:
        raise RuntimeError("Saved source segmentation has no segment identity to qualify.")
    source_hidden = (
        not source_display.GetVisibility2D()
        and not source_display.GetVisibility3D()
        and all(
            not source_display.GetSegmentVisibility3D(segment_ids.GetValue(index))
            for index in range(segment_ids.GetNumberOfValues())
        )
    )
    opened = {}
    for label, node in (
        ("fixed_upper", parameter.step6FixedUpperAnatomy),
        ("moving_lower", parameter.step6MovingLowerAnatomy),
    ):
        display = node.GetDisplayNode() if node else None
        if display is None:
            raise RuntimeError(f"Opened {label} anatomy display is unavailable.")
        ids = vtk.vtkStringArray()
        node.GetSegmentation().GetSegmentIDs(ids)
        visible_segments = sum(
            bool(display.GetSegmentVisibility(ids.GetValue(index)))
            and bool(display.GetSegmentVisibility3D(ids.GetValue(index)))
            for index in range(ids.GetNumberOfValues())
        )
        opened[label] = {
            "node_visible": bool(display.GetVisibility()),
            "visible_3d": bool(display.GetVisibility3D()),
            "visible_segment_count_3d": visible_segments,
        }
        if not opened[label]["node_visible"] or not opened[label]["visible_3d"] or not visible_segments:
            raise RuntimeError(f"Opened {label} anatomy is not visible in the viewport.")
    if not source_hidden:
        raise RuntimeError("Closed-pose source segmentation is visible in the opened-jaw view.")

    capabilities = facade.capabilities()
    ros_nodes = slicer.util.getNodesByClass("vtkMRMLROS2RobotNode")
    if bool(capabilities.connected) or ros_nodes or logic.isRos2MotionControlActive(base):
        raise RuntimeError("ROS was connected or restored before an explicit connection.")

    records = getattr(panel, "_manualSimulationRecords", None)
    if not isinstance(records, (tuple, list)):
        raise RuntimeError("Historical-record display state is unavailable.")
    history = {"present": bool(records), "count": len(records), "authority": "display_only"}
    if records:
        for record in records:
            parsed = parse_manual_simulation_record(record)
            if parsed.get("record_status") != "historical_display_only":
                raise RuntimeError("A reopened manual record has live authority.")

    plan = facade.motionPlan
    preview_active = bool(facade.previewActive)
    guarded_preview_active = bool(facade._guarded_preview_active)
    return_home_required = bool(facade.returnHomeRequired)
    if (
        plan is not None
        or preview_active
        or guarded_preview_active
        or return_home_required
        or widget._step6MotionPlan is not None
    ):
        raise RuntimeError("Fresh reopen has live plan or preview authority.")
    return {
        "saved_stage_index": stage_index,
        "ui_stage_index": ui_stage_index,
        "step6_stage_label": str(widget.ui.workflowStageComboBox.currentText),
        "selected_prepared_branch": {
            "branch_id": selected_branch,
            "eligibility": branch_result.get("reason"),
            "eligible": True,
            "planning_context_imported": False,
        },
        "task_confirmation": "cleared_by_offline_restore_policy",
        "task_home": {
            "revision": home.revision,
            "joint_names": list(home.joint_names),
            "joint_positions_si": list(home.joint_positions_si),
            "runtime_validation_status": home.runtime_validation_status,
            "base_fingerprint": home.base_fingerprint,
            "freshness_issues": list(home_issues),
        },
        "base": {
            "matrix_to_world_ras": base_matrix,
            "fingerprint": base_fingerprint,
            "status": base_status,
            "source": base_source,
            "revision": base_revision,
            "locked": base_locked,
            "freshness_issues": list(base_issues),
            "case_foundation": foundation,
        },
        "current_arm_state": {
            "joint_names": list(state.joint_names),
            "joint_positions_si": current_joints,
            "manual_jog_control_names": list(controls),
            "sixth_arm_joint": False,
        },
        "reviewed_limits": {
            "joint_names": list(EXPECTED_JOINTS),
            "display_joint_labels": list(JOINT_LABELS),
            "minimum_display": minimums,
            "maximum_display": maximums,
            "reviewed": True,
            "fingerprint": limit_fingerprint,
        },
        "opened_jaw_display": {"source_hidden": True, "opened_anatomy": opened},
        "ros": {
            "connected": bool(capabilities.connected),
            "ros_robot_node_count": len(ros_nodes),
            "base_ros_motion_control_active": bool(logic.isRos2MotionControlActive(base)),
        },
        "historical_records": history,
        "route_preview": {
            "route_authority": "none",
            "motion_plan_present": plan is not None,
            "preview_active": preview_active,
            "guarded_preview_active": guarded_preview_active,
            "return_home_required": return_home_required,
            "planner_calls": 0,
        },
    }


def run() -> int:
    os.umask(0o077)
    evidence_dir = _private_evidence_dir()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = evidence_dir / f"step6_case_qualification_{run_id}.json"
    descriptor = os.open(str(report_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    report = {
        "schema_version": "1.0",
        "gate": "S6-LIVE-01 saved FDI11 five-DOF case qualification",
        "started_at_utc": _utc_now(),
        "status": "RUNNING",
        "report_path": str(report_path),
        "evidence_directory": str(evidence_dir),
        "case_source": str(EXPECTED_CASE),
        "case_sha256": None,
        "source_case_unchanged": None,
        "strict_production_open": False,
        "simulation_only": True,
        "hardware_execution": False,
        "ros_connect_calls": 0,
        "jog_requests": 0,
        "planner_calls": 0,
        "preview_calls": 0,
        "screenshots": {},
        "items": {name: {"status": "NOT_RUN"} for name in CHECKS},
    }

    def write_report():
        temporary = report_path.with_name(report_path.name + ".tmp")
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, report_path)

    def record(name: str, status: str, **details):
        report["items"][name] = {
            "status": status,
            "recorded_at_utc": _utc_now(),
            **details,
        }
        write_report()

    active = CHECKS[0]
    try:
        record(active, "RUNNING")
        report["checkout"] = _checkout_evidence()
        record(active, "PASS", **report["checkout"])

        active = CHECKS[1]
        record(active, "RUNNING")
        case_text = os.environ.get("DENTOBOT_HEADED_CASE_SOURCE", "").strip()
        expected_sha = os.environ.get("DENTOBOT_HEADED_CASE_SHA256", "").strip()
        case_path = Path(case_text).expanduser() if case_text else Path()
        if not case_text or not case_path.is_absolute():
            raise RuntimeError("DENTOBOT_HEADED_CASE_SOURCE must be the exact absolute case path.")
        if case_path != EXPECTED_CASE or any(parent.is_symlink() for parent in (case_path, *case_path.parents)):
            raise RuntimeError("DENTOBOT_HEADED_CASE_SOURCE must be the exact nonsymlink case path.")
        case_path = case_path.resolve(strict=True)
        if case_path != EXPECTED_CASE or not case_path.is_file():
            raise RuntimeError("DENTOBOT_HEADED_CASE_SOURCE is not the newly saved FDI11 acceptance case.")
        if re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha) is None:
            raise RuntimeError("DENTOBOT_HEADED_CASE_SHA256 must be an exact 64-character SHA-256.")
        case_sha = _sha256_file(case_path)
        if case_sha.lower() != expected_sha.lower():
            raise RuntimeError("The current case SHA-256 does not match DENTOBOT_HEADED_CASE_SHA256.")
        inspection = validate_case_bundle(case_path)
        if inspection.path.resolve() != case_path:
            raise RuntimeError("Production bundle validation returned a different case path.")
        report["case_sha256"] = case_sha
        record(active, "PASS", path=str(case_path), sha256=case_sha, size_bytes=case_path.stat().st_size,
               expected_sha256=expected_sha.lower(), bundle_valid=True)

        active = CHECKS[2]
        record(active, "RUNNING")
        saved = _saved_case_evidence(inspection.workflow)
        report["saved_case_evidence"] = saved
        record(active, "PASS", **saved)

        active = CHECKS[3]
        record(active, "RUNNING")
        main_window = slicer.util.mainWindow()
        if main_window is None:
            raise RuntimeError("Slicer main window is unavailable.")
        slicer.util.selectModule("DENTOWorkflow")
        for _ in range(3):
            slicer.app.processEvents()
            time.sleep(0.05)
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        if widget is None or not callable(getattr(widget, "_openCaseBundle", None)):
            raise RuntimeError("Production DENTOWorkflow case-open owner is unavailable.")
        opened_inspection = widget._openCaseBundle(str(case_path))
        if not opened_inspection or opened_inspection.path.resolve() != case_path:
            raise RuntimeError("Production case-open owner did not return the qualified case.")
        report["strict_production_open"] = True
        record(active, "PASS", owner="widget._openCaseBundle", bundle_integrity_validated=True,
               strict_post_hydration_open_returned=True)

        # Capture the opened Step 6 state before any further inspection.
        for _ in range(3):
            slicer.app.processEvents()
            time.sleep(0.05)
        screenshots = _capture_screenshots(f"step6-case-qualification-{run_id}", evidence_dir)
        report["screenshots"] = screenshots
        record(CHECKS[11], "PASS", **screenshots)

        active = CHECKS[4]
        record(active, "RUNNING")
        post_open = _restored_case_evidence(widget, saved)
        report["restored_case_evidence"] = post_open
        record(active, "PASS", saved_confirmed_task="verified_from_bundle_lineage",
               offline_confirmed_task=post_open["task_confirmation"],
               selected_prepared_branch=post_open["selected_prepared_branch"],
               task_home=post_open["task_home"])

        for name, field in (
            (CHECKS[5], "opened_jaw_display"),
            (CHECKS[6], "current_arm_state"),
            (CHECKS[7], "ros"),
            (CHECKS[8], "historical_records"),
            (CHECKS[9], "route_preview"),
        ):
            active = name
            evidence = post_open[field]
            if name == CHECKS[6]:
                evidence = {
                    "current_arm_state": evidence,
                    "reviewed_limits": post_open["reviewed_limits"],
                    "task_home": post_open["task_home"],
                }
            record(active, "PASS", **{field: evidence})

        active = CHECKS[10]
        record(active, "RUNNING")
        final_sha = _sha256_file(case_path)
        if final_sha != case_sha:
            raise RuntimeError("The source case changed during read-only qualification.")
        report["source_case_unchanged"] = True
        record(active, "PASS", sha256_before=case_sha, sha256_after=final_sha, unchanged=True)
        report["status"] = "PASS"
        report["completed_at_utc"] = _utc_now()
        write_report()
        print("DENTOBOT_STEP6_CASE_QUALIFICATION_PASS", flush=True)
        slicer.util.exit(0)
        return 0
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        if report["items"][active]["status"] in {"RUNNING", "NOT_RUN"}:
            record(active, "FAIL", reason=message)
        for name in CHECKS:
            if report["items"][name]["status"] == "NOT_RUN":
                report["items"][name] = {"status": "NOT_RUN", "reason": f"Stopped after {active}."}
        report["status"] = "FAILED"
        report["failure_or_stop_reason"] = message
        report["completed_at_utc"] = _utc_now()
        write_report()
        print(f"DENTOBOT_STEP6_CASE_QUALIFICATION_FAILED: {message}", file=sys.stderr, flush=True)
        slicer.util.exit(1)
        return 1


try:
    run()
except Exception as exc:
    print(f"DENTOBOT_STEP6_CASE_QUALIFICATION_SETUP_FAILED: {type(exc).__name__}: {exc}",
          file=sys.stderr, flush=True)
    slicer.util.exit(1)
