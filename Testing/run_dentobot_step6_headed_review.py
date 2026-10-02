"""Headed, bounded Step 6 GUI review for an approved current checkout.

ROS/scene synchronization and manual commands require the explicit jog flag
and exact native preflight. Saving a reviewed current case is separately
opt-in. Rejected and unknown outcome scenarios have separate opt-ins; neither
retries a jog. The taskless-draft mode stops after its read-only draft check.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import dataclasses
from pathlib import Path
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

import qt
import slicer
import vtk


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
TESTING = ROOT / "Testing"
for candidate in (PYTHON, TESTING):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import DENTOROS2Bridge as bridge  # noqa: E402
from DENTOCaseBundle import validate_case_bundle  # noqa: E402
from DENTORobotWorkflowFacade import (  # noqa: E402
    JOINT_DISPLAY_UNITS,
    JOINT_LIMIT_FIELDS,
    TaskSpaceRoi,
)
from DENTOStep6Planning import (  # noqa: E402
    default_task_joint_limits_from_urdf,
    joint_limit_margin_evidence,
)
from DENTOStep6State import JOINT_NAMES, fingerprint  # noqa: E402
from dentobot_workflow.offline_placement_status import (  # noqa: E402
    EXPECTED_ROBOT_LINK_COUNT,
)
from step6_manual_jog_scenarios import (  # noqa: E402
    fixture_identity as _fixture_identity,
    rejection_plan as _rejection_plan,
)
from run_dentobot_tcp_workbench_headed import (  # noqa: E402
    _mouse_drag_requested,
    make_external_mouse_drag_callback,
    run_case_bound_tcp_probe,
)
from step6_full_chain_probe import run_full_chain_interruption_probe  # noqa: E402
from step6_base_home_uncertainty_probe import (  # noqa: E402
    run_base_home_uncertainty_probe,
)
from step6_complete_cycle_probe import run_complete_cycles  # noqa: E402
from step6_expected_error_dialog import (  # noqa: E402
    UnexpectedModalError,
    make_expected_error_dialog_callback,
    make_modal_watchdog_click,
)


CHECKOUT_PROFILES = {
    "renovation": {
        "branch": "feature/step6-workflow-renovation-20260925",
        "host_root": "/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-renovation",
        "container_root": "/workspace/ros2_ws/src/DentoBot-step6-renovation",
    },
    "integration": {
        "branch": "integration/step6-5.10-reviewed-20260927",
        "host_root": "/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-5.10-integration",
        "container_root": "/workspace/ros2_ws/src/DentoBot-step6-5.10-integration",
    },
}
NATIVE_BINARY_RELATIVE_PATH = Path(
    "lib/dentobot_moveit_config/collision_guard"
)
ACCEPTED_DELTA_DEG = 0.1
BASE_HOME_UNCERTAINTY_DIALOG_TIMEOUT_SEC = 180.0
SOURCE_FILES = (
    "DENTOWorkflow/Resources/Python/DENTORobotSimulationPanel.py",
    "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py",
    "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_robot.py",
    "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot.py",
    "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot_shell.py",
    "Testing/run_dentobot_manual_jog_headless.py",
    "Testing/step6_base_home_uncertainty_probe.py",
    "Testing/step6_complete_cycle_probe.py",
    "Testing/step6_expected_error_dialog.py",
    "Testing/step6_session_driver.py",
)
CHECK_NAMES = (
    "checkout_and_case_provenance",
    "case_opened_and_step6_ui",
    "saved_case_ros_readiness_not_restored",
    "simulation_robot_models_loaded",
    "planning_context_imported",
    "base_controls_and_accepted_status",
    "offline_base_home_configuration",
    "draft_state_control_visible",
    "native_version_preflight",
    "base_profile_rebind_prerequisite",
    "simulation_ros_connect_and_scene_readback",
    "profile_migration_recovery_after_scene_ack",
    "draft_state_read_only",
    "invalid_out_of_reviewed_range_draft",
    "single_guarded_j1_jog",
    "historical_record_export_reopen",
    "base_stage_and_cancel",
    "base_acceptance_trial",
    "task_home_review_acceptance_trial",
    "profile_migration_recovery_before_save",
    "case_bound_rejected_guard",
    "unknown_reconcile_state",
    "save_current_case",
    "manual_jog_keyboard_draft_check",
    "base_home_uncertainty",
    "case_bound_tcp_workbench",
    "planning_prerequisites",
    "base_diagnosis",
    "complete_cycles",
    "full_chain_interruption",
    "simulation_ros_disconnect",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_output_case_path(output_text: str, source_path: Path) -> Path:
    output_path = Path(output_text)
    if not output_path.is_absolute():
        raise ValueError("DENTOBOT_HEADED_OUTPUT_CASE must be an absolute path.")
    if output_path.suffix != ".dentocase":
        raise ValueError("DENTOBOT_HEADED_OUTPUT_CASE must end in .dentocase.")
    output_path = output_path.resolve(strict=False)
    if output_path == source_path.resolve():
        raise ValueError("The output case must be distinct from the source case.")
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError(f"Refusing to overwrite existing output: {output_path}")
    return output_path


def _unpassed_selected_checks(items: Mapping[str, object]) -> list[str]:
    return [
        name for name, item in items.items()
        if name != "save_current_case"
        and item.get("status") != "NOT_RUN"
        and item.get("status") not in {"PASS", "PREFLIGHT_PASS"}
    ]


def _save_current_case(widget, output_path: Path, source_path: Path,
                       source_sha256: str) -> dict[str, object]:
    output_path = _validate_output_case_path(str(output_path), source_path)
    source_path = source_path.resolve()
    if _sha256_file(source_path) != source_sha256:
        raise RuntimeError("The source case changed before the reviewed save.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        str(output_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
    )
    try:
        reservation = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        current = output_path.stat()
        if (current.st_dev, current.st_ino) != (reservation.st_dev, reservation.st_ino):
            raise FileExistsError(f"Output reservation was replaced: {output_path}")
        inspection = widget._createCaseBundle(str(output_path))
        if Path(inspection.path).resolve() != output_path or not output_path.is_file():
            raise RuntimeError("The production save owner did not create the requested case.")
        output_stat = output_path.stat()
        if (output_stat.st_dev, output_stat.st_ino) == (reservation.st_dev, reservation.st_ino):
            raise RuntimeError("The production save owner did not replace its reservation.")
        if _sha256_file(source_path) != source_sha256:
            raise RuntimeError("The source case changed during the reviewed save.")
        return {
            "output_path": str(output_path),
            "size_bytes": output_stat.st_size,
            "sha256": _sha256_file(output_path),
            "source_relationship": {
                "source_path": str(source_path),
                "source_sha256": source_sha256,
                "source_unchanged": True,
                "saved_from_current_workflow_session": True,
            },
        }
    finally:
        try:
            current = output_path.stat()
        except FileNotFoundError:
            current = None
        if current and (current.st_dev, current.st_ino) == (reservation.st_dev, reservation.st_ino):
            output_path.unlink()


def _finite_vector(values) -> dict[str, float]:
    if not isinstance(values, Mapping) or set(values) != set(JOINT_NAMES):
        raise ValueError("Joint state must contain exactly J1–J5.")
    result = {name: float(values[name]) for name in JOINT_NAMES}
    if not all(math.isfinite(value) for value in result.values()):
        raise ValueError("Joint state contains a non-finite value.")
    return result


def _apply_display_step_to_expected_si(before_si, joint_index: int, delta_si: float):
    expected = dict(before_si)
    expected[JOINT_NAMES[joint_index]] += delta_si
    return expected


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
        return first is not None and first == second
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _representationally_matches(left, right) -> bool:
    def ordered(values):
        if isinstance(values, Mapping):
            names = tuple(name for name in JOINT_NAMES if name in values)
            if not names or set(values) != set(names):
                return None
        elif isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            if len(values) != len(JOINT_NAMES):
                return None
            names = JOINT_NAMES
            values = dict(zip(names, values))
        else:
            return None
        result = [float(values[name]) for name in names]
        return (names, result) if all(math.isfinite(value) for value in result) else None

    try:
        first, second = ordered(left), ordered(right)
        return (
            first is not None
            and second is not None
            and first[0] == second[0]
            and all(
                math.isclose(a, b, rel_tol=0.0, abs_tol=1.0e-12)
                for a, b in zip(first[1], second[1])
            )
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


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


def _process_events(seconds: float = 0.05) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        ros_logic = slicer.util.getModuleLogic("ROS2")
        if ros_logic is not None:
            ros_logic.Spin()
        time.sleep(0.01)


def _wait_until(predicate, timeout_sec: float = 3.0):
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        _process_events(0.02)
        value = predicate()
        if value:
            return value
    return None


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


def _scene_evidence(logic, parameter_node) -> dict[str, object]:
    audit = logic.collisionSceneAuditRecord(parameter_node)
    if audit is None:
        raise RuntimeError("Current case collision-scene audit is unavailable.")
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
        "evidence_scope": "object_presence_readback",
        "authority_pending": "native_manual_joint_guard",
        "runtime_acknowledgement": acknowledgement,
        "acknowledged_object_ids": acknowledged_ids,
        "source_object_ids": source_ids,
    }


def _p1_straight_path_checks(logic, facade, parameter_node, evidence, limit=5) -> list:
    """Diagnostic only: straight Home->PreEntry joint path validity per endpoint."""
    home = logic.taskHomeRecord(parameter_node)
    if home is None:
        return [{"status": "no_task_home"}]
    start = dict(zip(home.joint_names, home.joint_positions_si))
    records = ((evidence.get("diagnostic_sessions") or {}).get("P1") or {}).get("candidate_records") \
        or (evidence.get("preentry_diagnostic_session") or {}).get("candidate_records") or []
    checks = []
    for record in records:
        if (record.get("termination_reason") != "converged"
                or record.get("collision_check_status") != "clear"
                or record.get("static_state_validity_status") != "Valid"):
            continue
        goal = record.get("best_joint_positions_si") or {}
        result = facade.checkStraightJointPath(start, goal)
        checks.append({"candidate_index": record.get("candidate_index"),
                       "code": result.code, "success": bool(result.success),
                       "message": str(result.message)[:300],
                       "details": _json_safe(dict(result.details or {}))})
        if len(checks) >= limit:
            break
    return checks


def _install_base_lock_tracer(logic, facade, traces) -> None:
    """Diagnostic only: record lock/pose calls and lock/authority flips during Accept."""
    import traceback

    authority_name = getattr(logic, "ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE",
                             "DENTOBOT.RobotBasePlacementAuthority")

    def state():
        node = facade._parameter_node()
        base = getattr(node, "robotBaseTransform", None)
        return {
            "parameter_node_id": str(node.parameterNode.GetID()) if hasattr(node, "parameterNode") else str(id(node)),
            "locked": bool(getattr(node, "robotBaseMountLocked", False)),
            "base_id": str(base.GetID()) if base is not None else None,
            "authority": str(base.GetAttribute(authority_name) or "") if base is not None else None,
        }

    original_lock = logic.setRobotBaseMountLocked
    original_pose = facade.setBasePose
    original_lock_base = facade.lockBase

    def traced_lock(node, locked, *args, **kwargs):
        import sys

        entry = {"call": f"setRobotBaseMountLocked({bool(locked)})", "before": state(),
                 "stack": traceback.format_stack(limit=30), "profile": []}
        traces.append(entry)
        profile = entry["profile"]
        previous = sys.getprofile()

        def hook(frame, event, arg):
            del arg
            if event not in ("call", "return") or len(profile) > 30000:
                return
            filename = frame.f_code.co_filename
            if "DENTOWorkflow" not in filename and "dentobot" not in filename.lower():
                return
            try:
                value = bool(node.robotBaseMountLocked)
                authority = ""
                base = node.robotBaseTransform
                if base is not None:
                    authority = str(base.GetAttribute(authority_name) or "")
            except Exception:
                value, authority = None, None
            code = frame.f_code
            profile.append([event, code.co_name,
                            code.co_filename.rsplit("/", 1)[-1] + ":" + str(frame.f_lineno),
                            value, authority])

        sys.setprofile(hook)
        try:
            return original_lock(node, locked, *args, **kwargs)
        finally:
            sys.setprofile(previous)
            entry["after"] = state()

    def traced_pose(matrix, *args, **kwargs):
        entry = {"call": "setBasePose", "before": state(), "stack": traceback.format_stack(limit=30)}
        traces.append(entry)
        try:
            return original_pose(matrix, *args, **kwargs)
        finally:
            entry["after"] = state()

    def traced_lock_base(*args, **kwargs):
        entry = {"call": "lockBase", "before": state(), "stack": traceback.format_stack(limit=12)}
        traces.append(entry)
        result = original_lock_base(*args, **kwargs)
        entry["after"] = state()
        entry["result"] = {"success": bool(result.success), "code": str(result.code),
                           "message": str(result.message)[:400]}
        return result

    last = {"locked": None, "authority": None}

    def watch(caller=None, event=None):
        del caller, event
        try:
            current = state()
        except Exception:
            return
        for key in ("locked", "authority"):
            if last[key] is not None and current[key] != last[key]:
                traces.append({"call": f"flip:{key}", "from": last[key], "to": current[key],
                               "stack": traceback.format_stack(limit=30)})
            last[key] = current[key]

    node = facade._parameter_node()
    observed = []
    wrapped = getattr(node, "parameterNode", None)
    if wrapped is not None:
        observed.append((wrapped, wrapped.AddObserver(vtk.vtkCommand.ModifiedEvent, watch)))
    base = getattr(node, "robotBaseTransform", None)
    if base is not None:
        observed.append((base, base.AddObserver(vtk.vtkCommand.ModifiedEvent, watch)))
    watch()
    logic._dentobotTraceObservers = observed
    logic.setRobotBaseMountLocked = traced_lock
    facade.setBasePose = traced_pose
    facade.lockBase = traced_lock_base


def _remove_base_lock_tracer(logic, facade) -> None:
    for node, tag in getattr(logic, "_dentobotTraceObservers", ()):
        node.RemoveObserver(tag)
    if "_dentobotTraceObservers" in vars(logic):
        delattr(logic, "_dentobotTraceObservers")
    for owner, name in ((logic, "setRobotBaseMountLocked"), (facade, "setBasePose"), (facade, "lockBase")):
        if name in vars(owner):
            delattr(owner, name)


def _modal_guarded_click(report, evidence_dir: Path, run_id: str, button, stage: str) -> None:
    """Click a production control; a modal fails the run fast instead of blocking it."""
    click = make_modal_watchdog_click(
        qt,
        qt.QApplication.activeModalWidget,
        lambda capture_stage: _capture(report, evidence_dir, run_id, capture_stage),
    )
    click(button, stage)


def _capture_screenshots(label: str, evidence_dir: Path) -> dict[str, str]:
    window = slicer.util.mainWindow()
    if window is None:
        raise RuntimeError("Slicer main window is unavailable for required evidence.")
    missing = object()
    active_modal_reader = getattr(qt.QApplication, "activeModalWidget", missing)
    if active_modal_reader is missing:
        raise RuntimeError("Qt active-modal-widget reader is unavailable for required evidence.")
    active_modal = active_modal_reader() if callable(active_modal_reader) else active_modal_reader
    modal_path = None
    if active_modal is not None:
        modal_grab = getattr(active_modal, "grab", None)
        if not callable(modal_grab):
            raise RuntimeError("Active modal does not provide a screenshot capture method.")
        modal_pixmap = modal_grab()
        modal_is_null = getattr(modal_pixmap, "isNull", None)
        modal_save = getattr(modal_pixmap, "save", None)
        if modal_pixmap is None or not callable(modal_is_null) or modal_is_null():
            raise RuntimeError(f"Could not capture active modal screenshot: {label}-modal.png")
        modal_path = evidence_dir / f"{label}-modal.png"
        if not callable(modal_save) or not modal_save(str(modal_path)):
            raise RuntimeError(f"Could not save active modal screenshot: {modal_path.name}")
        if not modal_path.is_file() or modal_path.stat().st_size <= 0:
            raise RuntimeError(f"Active modal screenshot is empty: {modal_path.name}")
    old_title = str(window.windowTitle)
    window.windowTitle = f"DENTOBOT Step 6 review — {label}"
    try:
        if active_modal is None:
            window.show()
            _process_events(0.2)
        ui_path = evidence_dir / f"{label}-ui.png"
        pixmap = window.grab()
        if pixmap.isNull() or not pixmap.save(str(ui_path)):
            raise RuntimeError(f"Could not capture UI screenshot: {ui_path.name}")
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
            raise RuntimeError(f"Could not capture viewport screenshot: {viewport_path.name}")
        return {
            "ui": ui_path.name,
            "viewport": viewport_path.name,
            "modal": modal_path.name if modal_path is not None else None,
            "captured_at_utc": _utc_now(),
        }
    finally:
        window.windowTitle = old_title


def _guard_click(widget, panel, target: dict[str, float]) -> dict[str, object]:
    if not panel.guardedManualJogButton.enabled:
        raise RuntimeError("Production Guarded Jog button is not enabled.")
    panel._setManualJogDraftValues(_display_values(target), notify=True)
    draft = panel.manualJogJointPositionsSi()
    if not _representationally_matches(draft, target):
        raise RuntimeError("Visible controls cannot represent the J1–J5 request within 1e-12 SI.")
    _process_events(0.1)
    panel.guardedManualJogButton.click()
    _process_events(0.1)
    return {
        "draft_positions_si": draft,
        "status_text": str(panel.manualJogStatusLabel.text),
        "status_state": str(panel.manualJogStatusLabel.property("dentobotState") or ""),
        "panel_accepted_positions_si": (
            dict(panel._manualJogAcceptedJointPositionsSi)
            if panel._manualJogAcceptedJointPositionsSi else None
        ),
        "evidence": dict(panel._manualJogEvidence or {}),
    }


def _checkout_evidence() -> dict[str, object]:
    profile = _checkout_profile()
    host_root = os.environ.get("DENTOBOT_HEADED_HOST_CHECKOUT_ROOT", "")
    branch = os.environ.get("DENTOBOT_HEADED_GIT_BRANCH", "")
    commit = os.environ.get("DENTOBOT_HEADED_GIT_HEAD", "")
    status_sha256 = os.environ.get("DENTOBOT_HEADED_GIT_STATUS_SHA256", "")
    missing = [
        name for name, value in (
            ("DENTOBOT_HEADED_HOST_CHECKOUT_ROOT", host_root),
            ("DENTOBOT_HEADED_GIT_BRANCH", branch),
            ("DENTOBOT_HEADED_GIT_HEAD", commit),
            ("DENTOBOT_HEADED_GIT_STATUS_SHA256", status_sha256),
        ) if not value
    ]
    if missing:
        raise LookupError("Host Git preflight is missing: " + ", ".join(missing))

    container_root = ROOT.resolve()
    if host_root != profile["host_root"]:
        raise RuntimeError(
            "Host wrapper reported an unexpected checkout root: "
            f"{host_root}; expected {profile['host_root']}."
        )
    if str(container_root) != profile["container_root"]:
        raise RuntimeError(
            "Mounted checkout root is unexpected: "
            f"{container_root}; expected {profile['container_root']}."
        )
    if branch != profile["branch"]:
        raise RuntimeError(
            f"Host wrapper reported branch {branch}; expected {profile['branch']}."
        )
    if re.fullmatch(r"[0-9a-fA-F]{40}", commit) is None:
        raise RuntimeError("DENTOBOT_HEADED_GIT_HEAD must be exactly 40 hexadecimal characters.")
    if re.fullmatch(r"[0-9a-fA-F]{64}", status_sha256) is None:
        raise RuntimeError(
            "DENTOBOT_HEADED_GIT_STATUS_SHA256 must be exactly 64 hexadecimal characters."
        )
    source_hashes = {
        name: _sha256_file(ROOT / name)
        for name in SOURCE_FILES
    }
    return {
        "profile": profile["name"],
        "container_checkout_root": str(container_root),
        "host_git_preflight": {
            "source": "host_wrapper_environment",
            "checkout_root": host_root,
            "branch": branch,
            "head_commit": commit.lower(),
            "worktree_status_sha256": status_sha256.lower(),
        },
        "step6_source_sha256": source_hashes,
        "runner_sha256": _sha256_file(Path(__file__).resolve()),
    }


def _checkout_profile() -> dict[str, str]:
    mode = os.environ.get("DENTOBOT_HEADED_PROVENANCE_MODE", "renovation")
    if mode not in CHECKOUT_PROFILES:
        raise RuntimeError(
            "DENTOBOT_HEADED_PROVENANCE_MODE must be exactly 'renovation' or 'integration'."
        )
    return {"name": mode, **CHECKOUT_PROFILES[mode]}


def _draft_only_requested() -> bool:
    value = os.environ.get("DENTOBOT_HEADED_DRAFT_ONLY", "")
    if value not in {"", "0", "1"}:
        raise RuntimeError("DENTOBOT_HEADED_DRAFT_ONLY must be exactly '1', '0', or unset.")
    draft_only = value == "1"
    if draft_only and (
        os.environ.get("DENTOBOT_HEADED_ALLOW_JOG", "") == "1"
        or os.environ.get("DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT", "") == "1"
    ):
        raise RuntimeError(
            "Taskless draft-only mode cannot be combined with jog or Base/Home acceptance opt-ins."
        )
    return draft_only


def _connect_only_requested() -> bool:
    enabled = _exact_env_opt_in("DENTOBOT_HEADED_CONNECT_ONLY")
    if not enabled:
        return False
    if os.environ.get("DENTOBOT_HEADED_PROVENANCE_MODE") != "integration":
        raise RuntimeError("Connect-only review requires the integration provenance mode.")
    incompatible = (
        "DENTOBOT_HEADED_ALLOW_JOG", "DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT",
        "DENTOBOT_HEADED_DRAFT_ONLY", "DENTOBOT_HEADED_INVALID_DRAFT_REVIEW",
        "DENTOBOT_HEADED_RECORD_REOPEN", "DENTOBOT_HEADED_JOINT_KEYBOARD",
        "DENTOBOT_HEADED_TCP_CASE", "DENTOBOT_HEADED_FULL_CHAIN",
        "DENTOBOT_HEADED_ALLOW_REJECTED_JOG", "DENTOBOT_HEADED_ALLOW_UNKNOWN_RECONCILIATION",
        "DENTOBOT_HEADED_STOP_AFTER_WORKSPACE",
    )
    if any(_exact_env_opt_in(name) for name in incompatible) or "DENTOBOT_HEADED_OUTPUT_CASE" in os.environ:
        raise RuntimeError("Connect-only review cannot enable other actions or save a case.")
    if not all(os.environ.get(name, "").strip() for name in (
        "DENTOBOT_HEADED_NATIVE_SOURCE_SHA256", "DENTOBOT_HEADED_NATIVE_BINARY_SHA256",
        "DENTOBOT_HEADED_NATIVE_PACKAGE_PREFIX",
    )):
        raise RuntimeError("Connect-only review requires exact native provenance.")
    return True


def _invalid_draft_review_requested() -> bool:
    value = os.environ.get("DENTOBOT_HEADED_INVALID_DRAFT_REVIEW", "")
    if value not in {"", "0", "1"}:
        raise RuntimeError(
            "DENTOBOT_HEADED_INVALID_DRAFT_REVIEW must be exactly '1', '0', or unset."
        )
    return value == "1"


def _historical_record_reopen_requested() -> bool:
    value = os.environ.get("DENTOBOT_HEADED_RECORD_REOPEN", "")
    if value not in {"", "0", "1"}:
        raise RuntimeError(
            "DENTOBOT_HEADED_RECORD_REOPEN must be exactly '1', '0', or unset."
        )
    return value == "1"


def _validate_record_reopen_prerequisites(record_reopen: bool, allow_jog: bool, draft_only: bool) -> None:
    if record_reopen and (not allow_jog or draft_only):
        raise RuntimeError(
            "DENTOBOT_HEADED_RECORD_REOPEN requires DENTOBOT_HEADED_ALLOW_JOG=1 "
            "and cannot be combined with taskless draft-only mode."
        )


def _exact_env_opt_in(name: str) -> bool:
    value = os.environ.get(name, "")
    if value not in {"", "0", "1"}:
        raise RuntimeError(f"{name} must be exactly '1', '0', or unset.")
    return value == "1"


def _validate_step6_live_probe_opt_ins(
    *,
    base_home_uncertainty: bool,
    complete_cycles: bool,
    full_chain: bool,
    allow_jog: bool,
    allow_base_home_accept: bool,
    workspace_diagnostic: bool,
    draft_only: bool,
) -> None:
    selected = base_home_uncertainty or complete_cycles
    if complete_cycles and full_chain:
        raise RuntimeError(
            "DENTOBOT_HEADED_COMPLETE_CYCLES and DENTOBOT_HEADED_FULL_CHAIN "
            "must run in separate fresh processes."
        )
    if selected and workspace_diagnostic:
        raise RuntimeError("Base/Home uncertainty and complete-cycle probes cannot run in workspace diagnostic mode.")
    if selected and draft_only:
        raise RuntimeError("Base/Home uncertainty and complete-cycle probes cannot run in taskless draft-only mode.")
    if selected and not allow_jog:
        raise RuntimeError("These headed Step 6 probes require DENTOBOT_HEADED_ALLOW_JOG=1.")
    if selected and not allow_base_home_accept:
        raise RuntimeError("These headed Step 6 probes require DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT=1.")


def _validate_workspace_diagnostic_opt_in() -> bool:
    if not _exact_env_opt_in("DENTOBOT_HEADED_STOP_AFTER_WORKSPACE"):
        return False
    if _exact_env_opt_in("DENTOBOT_HEADED_ALLOW_JOG"):
        raise RuntimeError(
            "Workspace diagnostic mode requires DENTOBOT_HEADED_ALLOW_JOG unset or '0'."
        )
    if not _exact_env_opt_in("DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT"):
        raise RuntimeError(
            "Workspace diagnostic mode requires DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT=1."
        )
    incompatible = (
        "DENTOBOT_HEADED_DRAFT_ONLY",
        "DENTOBOT_HEADED_INVALID_DRAFT_REVIEW",
        "DENTOBOT_HEADED_RECORD_REOPEN",
        "DENTOBOT_HEADED_JOINT_KEYBOARD",
        "DENTOBOT_HEADED_TCP_CASE",
        "DENTOBOT_HEADED_BASE_HOME_UNCERTAINTY",
        "DENTOBOT_HEADED_COMPLETE_CYCLES",
        "DENTOBOT_HEADED_FULL_CHAIN",
        "DENTOBOT_HEADED_ALLOW_REJECTED_JOG",
        "DENTOBOT_HEADED_ALLOW_UNKNOWN_RECONCILIATION",
        "DENTOBOT_HEADED_OFFLINE_HOME_SETUP",
    )
    enabled = [name for name in incompatible if _exact_env_opt_in(name)]
    if enabled:
        raise RuntimeError(
            "Workspace diagnostic mode cannot be combined with: " + ", ".join(enabled)
        )
    if "DENTOBOT_HEADED_OUTPUT_CASE" in os.environ:
        raise RuntimeError(
            "Workspace diagnostic mode cannot be combined with DENTOBOT_HEADED_OUTPUT_CASE."
        )
    if "DENTOBOT_HEADED_OFFLINE_HOME_CASE_OUTPUT" in os.environ:
        raise RuntimeError(
            "Workspace diagnostic mode cannot be combined with DENTOBOT_HEADED_OFFLINE_HOME_CASE_OUTPUT."
        )
    return True


def _load_historical_record_probe():
    helper_path = TESTING / "step6_historical_record_probe.py"
    spec = importlib.util.spec_from_file_location(
        "_dentobot_step6_historical_record_probe", str(helper_path)
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the callable historical-record probe.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    probe = getattr(module, "run_step6_historical_record_probe", None)
    if not callable(probe):
        raise RuntimeError("Historical-record helper has no callable probe entrypoint.")
    return probe


def _historical_record_probe_evidence_error(evidence, evidence_dir: Path) -> str | None:
    if not isinstance(evidence, Mapping) or evidence.get("status") != "PASS":
        return "callable probe did not return PASS evidence"
    expected_artifacts = {
        "record_json": "step6-manual-record-probe.json",
        "record_report": "step6-manual-record-probe.report.txt",
    }
    hashes = evidence.get("artifact_sha256")
    if not isinstance(hashes, Mapping):
        return "artifact hashes are unavailable"
    for field, filename in expected_artifacts.items():
        try:
            path = Path(str(evidence[field]))
            if path.is_symlink():
                return f"{field} must not be a symlink"
            resolved = path.resolve(strict=True)
            if (
                path.name != filename
                or resolved.parent != evidence_dir.resolve(strict=True)
                or not resolved.is_file()
            ):
                return f"{field} is outside the private evidence directory"
            expected_hash = str(hashes["json" if field == "record_json" else "report"])
            if re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash) is None:
                return f"{field} SHA-256 is invalid"
            if _sha256_file(resolved) != expected_hash.lower():
                return f"{field} SHA-256 does not match the exported artifact"
        except (KeyError, OSError, TypeError, ValueError):
            return f"{field} evidence is unavailable"

    record = evidence.get("record")
    events = record.get("event_order") if isinstance(record, Mapping) else None
    if (
        not isinstance(events, list)
        or not events
        or record.get("event_count") != len(events)
        or any(
            not isinstance(event, Mapping)
            or event.get("index") != index
            or not str(event.get("kind") or "")
            for index, event in enumerate(events)
        )
    ):
        return "event-bearing record order is unavailable or incomplete"

    replay = evidence.get("replay")
    if not isinstance(replay, Mapping) or replay.get("authority") != "historical_display_only":
        return "reopened record is not explicitly display-only"
    joints = evidence.get("accepted_j1_j5")
    if (
        not isinstance(joints, Mapping)
        or joints.get("unchanged") is not True
        or not _exactly_matches(joints.get("before"), joints.get("after"))
    ):
        return "accepted J1–J5 changed or its unchanged evidence is unavailable"
    authority = evidence.get("route_preview_authority")
    if (
        not isinstance(authority, Mapping)
        or authority.get("unchanged") is not True
        or authority.get("before") != authority.get("after")
        or authority.get("historical_record_authority") != "display_only"
    ):
        return "route/preview authority changed or its unchanged evidence is unavailable"
    captures = evidence.get("captures")
    required_stages = {"before_export", "after_export", "after_import", "after_event_step"}
    captured_by_stage = {
        item.get("stage"): item
        for item in captures
        if isinstance(item, Mapping)
    } if isinstance(captures, list) else {}
    if not required_stages.issubset(captured_by_stage):
        return "state-matched historical-record screenshots are incomplete"
    for stage in required_stages:
        result = captured_by_stage[stage].get("result")
        if not isinstance(result, Mapping):
            return "state-matched historical-record screenshots are incomplete"
        for field in ("ui", "viewport"):
            try:
                screenshot = Path(str(result[field]))
                if not screenshot.is_absolute():
                    screenshot = evidence_dir / screenshot
                if screenshot.is_symlink():
                    return "state-matched historical-record screenshots must not be symlinks"
                resolved = screenshot.resolve(strict=True)
                if resolved.parent != evidence_dir.resolve(strict=True) or resolved.stat().st_size <= 0:
                    return "state-matched historical-record screenshots are outside the private evidence directory"
            except (KeyError, OSError, TypeError, ValueError):
                return "state-matched historical-record screenshots are incomplete"
    return ""


def _select_invalid_draft_candidate(panel, accepted_display_values):
    """Select one small overstep from the limits currently displayed by the UI."""
    if len(accepted_display_values) != len(JOINT_NAMES):
        return None, "Accepted display state does not contain exactly J1–J5."
    display_values = [float(value) for value in accepted_display_values]
    if not all(math.isfinite(value) for value in display_values):
        return None, "Accepted display state contains a non-finite J1–J5 value."

    units = ("deg", "mm", "deg", "mm", "deg")
    considered = []
    for index, (joint, unit) in enumerate(zip(JOINT_NAMES, units, strict=True)):
        try:
            _slider, spinbox, label = panel.manualJogJointControls[joint]
            label_text = str(label.text)
            match = re.search(
                r"; reviewed:\s*([+-]?\d+(?:\.\d+)?)\s+to\s+"
                r"([+-]?\d+(?:\.\d+)?)\s+(deg|mm)\s*$",
                label_text,
            )
            if not match or match.group(3) != unit:
                considered.append(f"{joint}: current reviewed-limit display unavailable")
                continue
            lower, upper = float(match.group(1)), float(match.group(2))
            mechanical_minimum = float(spinbox.minimum)
            mechanical_maximum = float(spinbox.maximum)
            decimals = int(spinbox.decimals)
            quantum = 10.0 ** -decimals
            if (
                not all(math.isfinite(value) for value in (
                    lower, upper, mechanical_minimum, mechanical_maximum, quantum
                ))
                or upper < lower
                or mechanical_maximum < mechanical_minimum
                or quantum <= 0.0
            ):
                considered.append(f"{joint}: displayed/mechanical bounds are invalid")
                continue
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
            considered.append(f"{joint}: current reviewed/mechanical controls unavailable")
            continue

        for bound, candidate in (("maximum", upper + quantum), ("minimum", lower - quantum)):
            inside_mechanical = (
                mechanical_minimum <= candidate <= mechanical_maximum
            )
            outside_reviewed = candidate > upper if bound == "maximum" else candidate < lower
            if inside_mechanical and outside_reviewed:
                values = list(display_values)
                values[index] = candidate
                return {
                    "joint": joint,
                    "joint_label": f"J{index + 1}",
                    "joint_index": index,
                    "bound": bound,
                    "reviewed_limit_display": upper if bound == "maximum" else lower,
                    "candidate_display": candidate,
                    "display_values": values,
                    "reviewed_limit_label": label_text,
                    "mechanical_minimum": mechanical_minimum,
                    "mechanical_maximum": mechanical_maximum,
                }, ""
        considered.append(
            f"{joint}: reviewed {lower:g} to {upper:g} {unit}; mechanical "
            f"{mechanical_minimum:g} to {mechanical_maximum:g} {unit}"
        )

    return None, (
        "No one-display-step reviewed-limit overstep fits inside the current "
        "mechanical spinbox bounds. Considered: " + "; ".join(considered)
    )


def _visible_manual_draft_display_values(panel) -> tuple[float, ...]:
    return tuple(
        float(panel.manualJogJointControls[joint][1].value)
        for joint in JOINT_NAMES
    )


def _matching_reviewed_limit_violation(evidence, candidate):
    violations = evidence.get("limitViolations") if isinstance(evidence, Mapping) else None
    if not isinstance(violations, (list, tuple)):
        return None
    return next(
        (
            item for item in violations
            if isinstance(item, Mapping)
            and item.get("jointLabel") == candidate["joint_label"]
            and item.get("jointName") == candidate["joint"]
            and item.get("limitSource") == "reviewed_task"
            and item.get("bound") == candidate["bound"]
        ),
        None,
    )


def _native_preflight() -> dict[str, object]:
    expected_source = os.environ.get("DENTOBOT_HEADED_NATIVE_SOURCE_SHA256", "").strip()
    expected_binary = os.environ.get("DENTOBOT_HEADED_NATIVE_BINARY_SHA256", "").strip()
    expected_prefix_text = os.environ.get(
        "DENTOBOT_HEADED_NATIVE_PACKAGE_PREFIX", ""
    ).strip()
    missing = [
        name for name, value in (
            ("DENTOBOT_HEADED_NATIVE_SOURCE_SHA256", expected_source),
            ("DENTOBOT_HEADED_NATIVE_BINARY_SHA256", expected_binary),
            ("DENTOBOT_HEADED_NATIVE_PACKAGE_PREFIX", expected_prefix_text),
        ) if not value
    ]
    if missing:
        raise LookupError("Native preflight is missing: " + ", ".join(missing))
    for name, value in (
        ("DENTOBOT_HEADED_NATIVE_SOURCE_SHA256", expected_source),
        ("DENTOBOT_HEADED_NATIVE_BINARY_SHA256", expected_binary),
    ):
        if re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
            raise RuntimeError(f"{name} must be exactly 64 hexadecimal characters.")
    expected_source = expected_source.lower()
    expected_binary = expected_binary.lower()
    requested_prefix = Path(expected_prefix_text).expanduser()
    if not requested_prefix.is_absolute():
        raise RuntimeError("DENTOBOT_HEADED_NATIVE_PACKAGE_PREFIX must be absolute.")
    requested_prefix = requested_prefix.resolve()
    shared_install_prefix = (
        ROOT.parent.parent / "install/dentobot_moveit_config"
    ).resolve()
    if requested_prefix == shared_install_prefix:
        raise RuntimeError(
            "Refusing the shared ROS workspace install prefix; use an isolated native overlay."
        )

    from ament_index_python.packages import get_package_prefix

    package_prefix = Path(get_package_prefix("dentobot_moveit_config")).resolve()
    if package_prefix == shared_install_prefix:
        raise RuntimeError(
            "Ament selected the shared ROS workspace install prefix; refusing native preflight."
        )
    if package_prefix != requested_prefix:
        raise RuntimeError(
            "Ament-selected ROS package prefix does not match the explicitly supplied "
            f"isolated prefix: {package_prefix}; expected {requested_prefix}"
        )
    source = ROOT / "dentobot_moveit_config/src/collision_guard.cpp"
    binary = package_prefix / NATIVE_BINARY_RELATIVE_PATH
    if not source.is_file() or not binary.is_file():
        raise RuntimeError(
            f"Native preflight files are missing: source={source}, binary={binary}"
        )
    source_hash = _sha256_file(source)
    binary_hash = _sha256_file(binary)
    if source_hash != expected_source or binary_hash != expected_binary:
        raise RuntimeError(
            "The active checkout source or ament-selected collision_guard binary "
            "does not match the supplied preflight hashes."
        )
    return {
        "package_prefix": str(package_prefix),
        "source_path": str(source.resolve()),
        "source_sha256": source_hash,
        "binary_path": str(binary.resolve()),
        "binary_sha256": binary_hash,
        "expected_source_sha256": expected_source,
        "expected_binary_sha256": expected_binary,
    }


def _visible(widget) -> bool:
    method = getattr(widget, "isVisible", None)
    return bool(method()) if callable(method) else bool(widget.visible)


def _show_step63_view(panel, primary: int, secondary: int = 0) -> None:
    panel.step63TabWidget.currentIndex = primary
    if primary == 0:
        panel.step63ManualTabWidget.currentIndex = secondary
    elif primary == 1:
        panel.step63WorkspaceTabWidget.currentIndex = secondary
    elif primary == 2:
        panel.step63PlanTabWidget.currentIndex = secondary
    _process_events(0.1)


def _scroll_to_visible(widget, control, label: str) -> dict[str, object]:
    scroll_area = getattr(widget, "_workflowContentScrollArea", None)
    ensure_visible = getattr(scroll_area, "ensureWidgetVisible", None)
    viewport_getter = getattr(scroll_area, "viewport", None)
    if not callable(ensure_visible) or not callable(viewport_getter):
        raise RuntimeError(f"Workflow scroll area is unavailable for the {label} screenshot.")
    viewport = viewport_getter()
    if viewport is None or not viewport.isAncestorOf(control):
        raise RuntimeError(f"The {label} control is outside the workflow scroll area.")
    ensure_visible(control, 0, 0)
    _process_events(0.1)
    horizontal_scrollbar = scroll_area.horizontalScrollBar()
    horizontal_scrollbar.setValue(horizontal_scrollbar.minimum)
    _process_events(0.1)
    scrollbar = scroll_area.verticalScrollBar()
    rect = control.rect
    position = control.mapTo(viewport, rect.topLeft())
    if position.y() < 0 or position.y() + control.height > viewport.height:
        scrollbar.setValue(scrollbar.value + position.y() - 4)
        _process_events(0.1)
        rect = control.rect
        position = control.mapTo(viewport, rect.topLeft())
    control_size = (control.width, control.height)
    viewport_size = (viewport.width, viewport.height)
    limitations = []
    if control.width > viewport.width:
        limitations.append(
            "control is wider than the screenshot viewport; full width cannot fit"
        )
    if control.height > viewport.height:
        limitations.append(
            "control is taller than the screenshot viewport; full height cannot fit"
        )
    viewport_details = (
        f"control_position=({position.x()}, {position.y()}), "
        f"control_size={control_size}, viewport_size={viewport_size}, "
        f"horizontal_scrollbar_value={horizontal_scrollbar.value}, "
        f"horizontal_scrollbar_range=({horizontal_scrollbar.minimum}, "
        f"{horizontal_scrollbar.maximum}), "
        f"vertical_scrollbar_value={scrollbar.value}, "
        f"vertical_scrollbar_range=({scrollbar.minimum}, {scrollbar.maximum})"
    )
    if not _visible(control):
        raise RuntimeError(
            f"The {label} control is not visible after scrolling: {viewport_details}."
        )
    intersects_viewport = (
        position.x() < viewport.width
        and position.y() < viewport.height
        and position.x() + control.width > 0
        and position.y() + control.height > 0
    )
    if not intersects_viewport:
        raise RuntimeError(
            f"The {label} control is outside the screenshot viewport: {viewport_details}."
        )
    fully_visible = (
        position.x() >= 0
        and position.y() >= 0
        and position.x() + control.width <= viewport.width
        and position.y() + control.height <= viewport.height
    )
    return {
        "control": label,
        "visible_in_viewport": True,
        "intersects_viewport": True,
        "fully_visible_in_viewport": fully_visible,
        "control_wider_than_viewport": control.width > viewport.width,
        "limitations": limitations,
        "control_position": (position.x(), position.y()),
        "control_size": control_size,
        "viewport_size": viewport_size,
        "horizontal_scrollbar_value": horizontal_scrollbar.value,
        "horizontal_scrollbar_range": (
            horizontal_scrollbar.minimum,
            horizontal_scrollbar.maximum,
        ),
        "vertical_scrollbar_value": scrollbar.value,
        "vertical_scrollbar_range": (scrollbar.minimum, scrollbar.maximum),
    }


def _valid_matrix(value) -> bool:
    try:
        values = tuple(float(item) for item in value)
    except (TypeError, ValueError, OverflowError):
        return False
    return len(values) == 16 and all(math.isfinite(item) for item in values)


BASE_OFFSET_ENV = "DENTOBOT_HEADED_BASE_OFFSET_RAS_MM"
BASE_OFFSET_MAX_MM = 42.5  # +-30 mm on both forehead-plane axes


def _parse_base_offset(text: str | None) -> tuple[float, float, float] | None:
    """Parse ``"dx,dy,dz"`` (world RAS mm); unset/blank means no offset."""
    if text is None or not str(text).strip():
        return None
    parts = [part.strip() for part in str(text).split(",")]
    if len(parts) != 3:
        raise RuntimeError(f"{BASE_OFFSET_ENV} must be 'dx,dy,dz' in world RAS mm.")
    try:
        offset = tuple(float(part) for part in parts)
    except ValueError as exc:
        raise RuntimeError(f"{BASE_OFFSET_ENV} components must be numbers.") from exc
    if not all(math.isfinite(value) for value in offset):
        raise RuntimeError(f"{BASE_OFFSET_ENV} components must be finite.")
    if math.sqrt(sum(value * value for value in offset)) > BASE_OFFSET_MAX_MM:
        raise RuntimeError(f"{BASE_OFFSET_ENV} norm must be at most {BASE_OFFSET_MAX_MM:g} mm.")
    return offset


def _validate_base_offset_opt_in(offset, *, full_chain: bool, allow_jog: bool,
                                 allow_base_home_accept: bool) -> None:
    if offset is None:
        return
    if not (full_chain and allow_jog and allow_base_home_accept):
        raise RuntimeError(
            f"{BASE_OFFSET_ENV} requires DENTOBOT_HEADED_FULL_CHAIN=1, "
            "DENTOBOT_HEADED_ALLOW_JOG=1 and DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT=1."
        )
    blocked = [name for name in (
        "DENTOBOT_HEADED_STOP_AFTER_WORKSPACE", "DENTOBOT_HEADED_OFFLINE_HOME_SETUP",
        "DENTOBOT_HEADED_COMPLETE_CYCLES", "DENTOBOT_HEADED_BASE_HOME_UNCERTAINTY",
    ) if os.environ.get(name, "") == "1"]
    blocked += [name for name in (
        "DENTOBOT_HEADED_OUTPUT_CASE", "DENTOBOT_HEADED_OFFLINE_HOME_CASE_OUTPUT",
    ) if name in os.environ]
    if blocked:
        raise RuntimeError(f"{BASE_OFFSET_ENV} cannot be combined with: " + ", ".join(blocked))


def _translated_matrix(matrix, offset) -> list[float]:
    """Return a row-major 4x4 copy with only the translation column shifted."""
    values = [float(value) for value in matrix]
    for row, delta in enumerate(offset):
        values[row * 4 + 3] += float(delta)
    return values


def _same_matrix(left, right) -> bool:
    if not _valid_matrix(left) or not _valid_matrix(right):
        return False
    return all(
        math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1.0e-9)
        for a, b in zip(left, right)
    )


def _record(report: dict[str, object], name: str, status: str, **details) -> None:
    report["items"][name] = {
        "status": status,
        "recorded_at_utc": _utc_now(),
        **_json_safe(details),
    }
    _write_report(report)


def _retain_full_chain_probe_counts(report, evidence) -> None:
    if not isinstance(evidence, Mapping):
        return
    invocations = evidence.get("probe_local_button_invocations")
    if not isinstance(invocations, Mapping):
        return
    report["planner_calls"] = invocations.get(
        "plan_guarded_approach", report["planner_calls"]
    )
    if "preview_approach" in invocations:
        report["preview_started"] = invocations["preview_approach"] > 0


def _retain_complete_cycle_probe_counts(report, evidence) -> None:
    if not isinstance(evidence, Mapping):
        return
    invocations = evidence.get("button_invocations")
    if not isinstance(invocations, Mapping):
        return
    try:
        report["planner_calls"] += int(invocations.get("plan_guarded_approach", 0))
    except (TypeError, ValueError, OverflowError):
        pass
    for key in ("preview_approach", "preview_drill"):
        try:
            if int(invocations.get(key, 0) or 0) > 0:
                report["preview_started"] = True
        except (TypeError, ValueError, OverflowError):
            continue


def _complete_cycles_passed(evidence) -> bool:
    if (
        not isinstance(evidence, Mapping)
        or evidence.get("fresh_repeat_completed") is not True
        or evidence.get("route_fingerprint_comparison_used") is not False
        or not isinstance(evidence.get("cycles"), list)
        or len(evidence["cycles"]) != 2
    ):
        return False
    observed_fresh_identities = []
    for cycle in evidence["cycles"]:
        boundaries = cycle.get("boundaries") if isinstance(cycle, Mapping) else None
        provenance = cycle.get("route_provenance") if isinstance(cycle, Mapping) else None
        if not isinstance(boundaries, Mapping) or not isinstance(provenance, Mapping):
            return False
        if not all(provenance.get(key) for key in (
            "task_identity", "diagnostic_session_fingerprint", "phase_guard_session_id"
        )):
            return False
        if not all(isinstance(provenance.get(key), str) for key in (
            "diagnostic_session_fingerprint", "phase_guard_session_id"
        )):
            return False
        approach_plan = provenance.get("approach_plan")
        plan_instance_id = (
            approach_plan.get("plan_instance_id")
            if isinstance(approach_plan, Mapping)
            else None
        )
        if isinstance(plan_instance_id, bool) or not isinstance(plan_instance_id, int):
            return False
        observed_fresh_identities.append((
            provenance["diagnostic_session_fingerprint"],
            provenance["phase_guard_session_id"],
            approach_plan["plan_instance_id"],
        ))
        for phase_name in ("approach_endpoint_verified", "drill_endpoint_verified"):
            phase = boundaries.get(phase_name)
            completion = phase.get("completion_observation") if isinstance(phase, Mapping) else None
            endpoint = phase.get("endpoint_fk") if isinstance(phase, Mapping) else None
            if (
                not isinstance(phase, Mapping)
                or phase.get("endpoint_verified") is not True
                or not isinstance(completion, Mapping)
                or completion.get("observed_active") is not True
                or completion.get("configured_preview_speed_multiplier") != 0.25
                or not isinstance(endpoint, Mapping)
                or endpoint.get("status") != "passed"
                or endpoint.get("observation_kind") != "post_completion_observation"
            ):
                return False
        returned = boundaries.get("return_home_verified")
        reverse = returned.get("reverse_phase_execution_status_evidence") if isinstance(returned, Mapping) else None
        home_error = returned.get("saved_home_error") if isinstance(returned, Mapping) else None
        if (
            not isinstance(returned, Mapping)
            or returned.get("phase_session_cleared") is not True
            or not isinstance(reverse, Mapping)
            or reverse.get("phase_destination_sequence_matches_history") is not True
            or reverse.get("axial_retraction_completed") is not True
            or reverse.get("production_result_details_captured_by_read_only_observer") is not True
            or not isinstance(home_error, Mapping)
            or home_error.get("accepted_monitored_displayed_all_match_saved_home") is not True
        ):
            return False
    return len(set(observed_fresh_identities)) == 2 and all(
        observed_fresh_identities[0][index] != observed_fresh_identities[1][index]
        # Python object addresses may be reused after the previous plan is released.
        for index in range(2)
    )


def _write_report(report: dict[str, object]) -> None:
    path = Path(str(report["report_path"]))
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(_json_safe(report), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _finalize_workspace_diagnostic(report: dict[str, object]) -> None:
    reason = (
        "Intentional workspace-only diagnostic stop after current workspace generation; "
        "downstream checks were not run."
    )
    for item in report["items"].values():
        if item["status"] == "NOT_RUN":
            item["reason"] = reason
    report.update({
        "status": "DIAGNOSTIC_PASS",
        "completed_at_utc": _utc_now(),
        "failure_or_stop_reason": reason,
        "full_workflow_claimed": False,
        "screenrecording": {
            "status": "external_wrapper_required",
            "scope": "complete Slicer process",
        },
    })
    _write_report(report)


def _serve_command_session(namespace, widget, panel, facade, report, evidence_dir: Path) -> None:
    from step6_session_driver import rebind_callbacks, run_session

    session_dir = evidence_dir.parent / "session"
    namespace = {
        **namespace,
        "live_objects": lambda: [widget, getattr(widget, "logic", None), facade, panel],
        "after_reload": lambda: {
            "panel_callbacks_rebound": rebind_callbacks(panel._callbacks, widget),
        },
    }
    report["session_mode"] = {"status": "serving", "session_dir": str(session_dir)}
    _write_report(report)
    outcome = run_session(namespace, session_dir, _process_events)
    reason = (
        f"Command session ended ({outcome['reason']}); later checks ran only as "
        "session commands (see session/outbox)."
    )
    for item in report["items"].values():
        if item["status"] == "NOT_RUN":
            item["reason"] = reason
    report.update({
        "status": "SESSION_END",
        "completed_at_utc": _utc_now(),
        "failure_or_stop_reason": reason,
        "full_workflow_claimed": False,
        "session_mode": {"status": "ended", "session_dir": str(session_dir), **outcome},
    })
    _write_report(report)
    print("DENTOBOT_HEADED_SESSION_END", flush=True)
    slicer.util.exit(0)
    raise SystemExit(0)


def _run_base_diagnosis(widget, panel, facade, report, evidence_dir: Path, run_id: str) -> None:
    """S6-BASE-DIAGNOSE: click Diagnose This Base in 6.3 and keep its table as evidence."""
    check = "base_diagnosis"
    button = getattr(panel, "diagnoseBaseButton", None)
    if button is None or not bool(button.enabled):
        _record(report, check, "FAIL", reason="Diagnose This Base control is missing or disabled.")
        return
    try:
        _modal_guarded_click(report, evidence_dir, run_id, button, "base-diagnosis-click")
    except UnexpectedModalError as exc:
        _record(report, check, "FAIL", reason=f"Diagnose This Base raised a modal: {exc.dialog_text}")
        return
    _wait_until(lambda: not bool(getattr(widget, "_workflowActionBusy", False)), 900.0)
    _process_events(0.2)
    summary = getattr(facade, "_last_base_diagnosis", None)
    report["base_diagnosis"] = summary
    dialog = getattr(panel, "_baseDiagnosisDialog", None)
    if dialog is not None and bool(dialog.visible):
        path = evidence_dir / f"{run_id}-base-diagnosis-dialog.png"
        dialog.grab().save(str(path))
        report["screenshots"]["base-diagnosis-dialog"] = {"dialog": str(path)}
    _capture(report, evidence_dir, run_id, "base-diagnosis")
    if not isinstance(summary, dict) or summary.get("status") not in ("PASS", "WARNING", "FAIL"):
        _record(report, check, "FAIL", reason="Diagnose This Base returned no completed summary.",
                base_diagnosis=summary)
        return
    # The check passes when the diagnosis completes; its verdict is evidence.
    _record(report, check, "PASS", verdict=summary.get("verdict"), diagnosis_status=summary.get("status"),
            base_diagnosis=summary)
    if dialog is not None:
        dialog.hide()


def _capture(report, evidence_dir: Path, run_id: str, key: str) -> dict[str, str]:
    paths = _capture_screenshots(f"{run_id}-{key}", evidence_dir)
    report["screenshots"][key] = paths
    _write_report(report)
    return paths


STEP6_DISPLAY_MODEL_ROLES = (
    "Step6MouthBarrierDisplay", "Step6ReachEnvelope", "Step6WorkspaceHomeConnected", "RobotWorkspaceCloud",
)


def _step6_display_models_state() -> list[dict[str, object]]:
    """Visibility evidence for the barrier, reach envelope and workspace models."""
    records = []
    for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
        role = node.GetAttribute("DENTOBOT.ModelRole")
        if role not in STEP6_DISPLAY_MODEL_ROLES:
            continue
        display = node.GetDisplayNode()
        bounds = [0.0] * 6
        node.GetRASBounds(bounds)
        polydata = node.GetPolyData()
        records.append({
            "name": node.GetName(),
            "role": role,
            "visible": bool(display.GetVisibility()) if display else None,
            "visible_3d": bool(display.GetVisibility3D()) if display else None,
            "opacity": float(display.GetOpacity()) if display else None,
            "view_node_ids": [display.GetNthViewNodeID(i) for i in range(display.GetNumberOfViewNodeIDs())] if display else [],
            "world_bounds_ras_mm": [round(float(v), 2) for v in bounds],
            "points": int(polydata.GetNumberOfPoints()) if polydata else 0,
            "cells": int(polydata.GetNumberOfCells()) if polydata else 0,
            "summary": node.GetAttribute("DENTOBOT.MouthBarrierSummary") or node.GetAttribute("DENTOBOT.ReachEnvelopeSummary"),
        })
    return records


def _capture_anterior_view(report, evidence_dir: Path, run_id: str, key: str) -> dict[str, str]:
    """Front-view screenshot for barrier/envelope evidence; camera restored after."""
    view = slicer.app.layoutManager().threeDWidget(0).threeDView()
    camera_node = slicer.modules.cameras.logic().GetViewActiveCameraNode(view.mrmlViewNode())
    saved = (camera_node.GetPosition(), camera_node.GetFocalPoint(), camera_node.GetViewUp(),
             camera_node.GetParallelScale(), camera_node.GetViewAngle())
    try:
        import ctk
        view.lookFromViewAxis(ctk.ctkAxesWidget.Anterior)
        view.resetFocalPoint()
        _process_events(0.2)
        return _capture(report, evidence_dir, run_id, key)
    finally:
        # Restore through the MRML camera node (r10: renderer-only restore was
        # overwritten by the camera node, changing later screenshots).
        position, focal, view_up, parallel_scale, view_angle = saved
        camera_node.SetPosition(position)
        camera_node.SetFocalPoint(focal)
        camera_node.SetViewUp(view_up)
        camera_node.SetParallelScale(parallel_scale)
        camera_node.SetViewAngle(view_angle)
        camera_node.ResetClippingRange()
        view.forceRender()
        _process_events(0.1)


def _deliver_key(control, key, modifiers) -> dict[str, object]:
    qtest = getattr(qt, "QTest", None)
    key_click = getattr(qtest, "keyClick", None) if qtest is not None else None
    if callable(key_click):
        key_click(control, key, modifiers)
        return {"method": "qt.QTest.keyClick", "delivered": True}
    key_event = getattr(qt, "QKeyEvent", None)
    send_event = getattr(qt.QApplication, "sendEvent", None)
    event_type = getattr(qt, "QEvent", None)
    if not callable(key_event) or not callable(send_event) or event_type is None:
        raise RuntimeError("Qt physical key delivery is unavailable; refusing callback fallback.")
    press = key_event(event_type.KeyPress, key, modifiers, "", False, 1)
    release = key_event(event_type.KeyRelease, key, modifiers, "", False, 1)
    send_event(control, press)
    send_event(control, release)
    return {"method": "QApplication.sendEvent(QKeyEvent)", "delivered": True}


def _focus(control) -> None:
    control.setFocus()
    _process_events(0.05)
    focused = qt.QApplication.focusWidget()
    if focused is not control and focused != control:
        raise RuntimeError("Could not focus the requested visible Step 6.3 child.")


def _run_manual_jog_keyboard_draft_check(
    widget, panel, facade, report, evidence_dir: Path, run_id: str
) -> None:
    name = "manual_jog_keyboard_draft_check"
    checkbox = panel.manualJogKeyboardEnabledCheckBox
    step_combo = panel.manualJogKeyboardStepComboBox
    key_target = panel.checkManualDraftStateButton
    original_step_index = int(step_combo.currentIndex)
    evidence: dict[str, object] = {
        "opt_in": "DENTOBOT_HEADED_JOINT_KEYBOARD=1",
        "scope": "visible Step 6.3 manual-jog group",
        "key_target": "Check Draft State button (non-editor child)",
        "delivery": "physical Qt key events",
        "key_events": [],
        "screenshots": {},
        "screenshot_framing": {},
    }
    accepted_before = None
    authority_before = None
    failure = None

    def authority_state():
        plan = facade.motionPlan
        events = getattr(facade, "_manual_simulation_events", ())
        records = facade.manualSimulationCompletedRecords()
        return {
            "jog_requests": int(report["jog_requests"]),
            "manual_jog_in_progress": bool(getattr(facade, "_manual_jog_in_progress", False)),
            "manual_jog_busy": bool(panel._manualJogBusy),
            "manual_jog_reconciliation_required": bool(panel.manualJogReconciliationRequired),
            "manual_jog_event_count": len(events),
            "manual_jog_event_fingerprint": fingerprint(_json_safe(events)),
            "manual_simulation_record_count": len(records),
            "manual_simulation_records_fingerprint": fingerprint(_json_safe(records)),
            "motion_plan_present": plan is not None,
            "motion_plan_identity": id(plan) if plan is not None else None,
            "preview_active": bool(
                facade.previewActive or getattr(facade, "_guarded_preview_active", False)
            ),
            "return_home_required": bool(facade.returnHomeRequired),
            "route_authority": report["route_authority"],
            "planner_calls": int(report["planner_calls"]),
            "preview_started": report["preview_started"],
        }

    def draft_diagnostics():
        jog_evidence = getattr(panel, "_manualJogEvidence", None)
        return {
            "manual_jog_status": str(panel.manualJogStatusLabel.text),
            "manual_jog_evidence_fingerprint": (
                fingerprint(_json_safe(jog_evidence)) if jog_evidence is not None else None
            ),
        }

    def capture(label: str) -> dict[str, str]:
        frame = _scroll_to_visible(widget, panel.manualJogGroup, label)
        paths = _capture(report, evidence_dir, run_id, f"manual-jog-keyboard-{label}")
        evidence["screenshots"][label] = paths
        evidence["screenshot_framing"][label] = frame
        _record(report, name, "RUNNING", **evidence)
        return paths

    def assert_runtime_state(label: str) -> dict[str, object]:
        state = _actual_joint_state(facade)
        if not all(state.get(key) for key in ("accepted_si", "monitored_si", "displayed_si")):
            raise RuntimeError(f"Accepted, monitored, or displayed state is unavailable after {label}.")
        if not all(
            _exactly_matches(accepted_before[key], state[key])
            for key in ("accepted_si", "monitored_si", "displayed_si")
        ):
            raise RuntimeError(f"Keyboard draft input changed accepted simulation state after {label}.")
        authority_after = authority_state()
        if authority_after != authority_before:
            raise RuntimeError(f"Keyboard draft input changed guard, plan, or preview state after {label}.")
        return {"joint_state": state, "authority_unchanged": True}

    try:
        if (
            getattr(panel, "_activeSubstep", None) != 3
            or not _visible(panel.manualJogGroup)
            or not _visible(checkbox)
            or not _visible(step_combo)
            or not _visible(key_target)
        ):
            raise RuntimeError("The Step 6.3 Manual Jog controls are not visible and active.")
        if not checkbox.enabled or not step_combo.enabled:
            raise RuntimeError("The keyboard opt-in controls are disabled in visible Step 6.3.")

        accepted_before = _actual_joint_state(facade)
        if not all(accepted_before.get(key) for key in ("accepted_si", "monitored_si", "displayed_si")):
            raise RuntimeError("Accepted, monitored, or displayed J1–J5 state is unavailable.")
        baseline_si = _finite_vector(panel.manualJogJointPositionsSi())
        baseline_display = _visible_manual_draft_display_values(panel)
        if not _representationally_matches(baseline_si, accepted_before["accepted_si"]):
            raise RuntimeError("Keyboard draft check must begin at the accepted J1–J5 pose.")

        expected_bindings = (
            ("Q", 0, 1.0), ("A", 0, -1.0),
            ("W", 1, 1.0), ("S", 1, -1.0),
            ("E", 2, 1.0), ("D", 2, -1.0),
            ("R", 3, 1.0), ("F", 3, -1.0),
            ("T", 4, 1.0), ("G", 4, -1.0),
        )
        if tuple(panel.MANUAL_JOG_KEY_BINDINGS) != expected_bindings:
            raise RuntimeError("The production J1–J5 keyboard mapping differs from Q/A W/S E/D R/F T/G.")
        shortcuts = tuple(panel._manualJogKeyboardShortcuts)
        if len(shortcuts) != len(expected_bindings):
            raise RuntimeError("The production J1–J5 keyboard shortcut set is incomplete.")
        if any(bool(shortcut.autoRepeat) for shortcut in shortcuts):
            raise RuntimeError("Manual-jog keyboard shortcut auto-repeat is not disabled.")
        evidence["shortcut_count"] = len(shortcuts)
        evidence["keyboard_auto_repeat_disabled"] = True
        evidence["accepted_state_before"] = accepted_before
        evidence["draft_si_before"] = baseline_si
        evidence["draft_display_before"] = baseline_display
        authority_before = authority_state()
        if (
            authority_before["jog_requests"] != 0
            or authority_before["manual_jog_in_progress"]
            or authority_before["manual_jog_busy"]
            or authority_before["manual_jog_reconciliation_required"]
            or authority_before["manual_jog_event_count"] != 0
            or authority_before["manual_simulation_record_count"] != 0
            or authority_before["motion_plan_present"]
            or authority_before["route_authority"] != "none"
            or authority_before["planner_calls"] != 0
            or authority_before["preview_started"] is not False
            or authority_before["preview_active"]
        ):
            raise RuntimeError("Guard, plan, or preview activity is already present before keyboard review.")
        evidence["authority_before"] = authority_before
        evidence["draft_diagnostics_before"] = draft_diagnostics()
        _record(report, name, "RUNNING", **evidence)

        if checkbox.checked or any(bool(shortcut.enabled) for shortcut in shortcuts):
            raise RuntimeError("Joint keyboard shortcuts were enabled before explicit opt-in.")
        step_combo.currentIndex = 0
        _process_events(0.05)
        default_steps = tuple(float(value) for value in step_combo.currentData)
        if len(default_steps) != 2 or not all(
            math.isclose(value, 0.1, rel_tol=0.0, abs_tol=1e-12)
            for value in default_steps
        ):
            raise RuntimeError("The default joint keyboard step is not 0.1 degree / 0.1 mm.")

        _focus(key_target)
        before_display = _visible_manual_draft_display_values(panel)
        delivery = _deliver_key(key_target, qt.Qt.Key_Q, qt.Qt.NoModifier)
        _process_events(0.05)
        if not _representationally_matches(
            _visible_manual_draft_display_values(panel), before_display
        ):
            raise RuntimeError("J1 Q changed the draft before explicit keyboard opt-in.")
        unchanged = assert_runtime_state("the pre-opt-in J1 Q key")
        evidence["pre_opt_in"] = {
            "checkbox_checked": False,
            "all_shortcuts_disabled": True,
            "key": "Q",
            "delivery": delivery,
            "draft_unchanged": True,
            **unchanged,
        }
        capture("before-opt-in")

        checkbox.click()
        _process_events(0.05)
        if not checkbox.checked or not all(bool(shortcut.enabled) for shortcut in shortcuts):
            raise RuntimeError("Explicit keyboard opt-in did not enable the J1–J5 shortcuts.")
        evidence["opt_in"] = {
            "checkbox_checked": True,
            "step_combo_enabled": bool(step_combo.enabled),
            "all_shortcuts_enabled": True,
        }
        capture("opted-in")

        units = ("deg", "mm", "deg", "mm", "deg")
        pairs = (("J1", "Q", "A"), ("J2", "W", "S"), ("J3", "E", "D"),
                 ("J4", "R", "F"), ("J5", "T", "G"))
        for joint_index, (joint, positive_key, negative_key) in enumerate(pairs):
            for key_name, direction in ((positive_key, 1.0), (negative_key, -1.0)):
                current_steps = tuple(float(value) for value in step_combo.currentData)
                displayed_step = current_steps[0 if units[joint_index] == "deg" else 1]
                delta = direction * displayed_step
                before_display = _visible_manual_draft_display_values(panel)
                before_si = _finite_vector(panel.manualJogJointPositionsSi())
                expected_display = list(before_display)
                expected_display[joint_index] += delta
                _focus(key_target)
                delivery = _deliver_key(
                    key_target, getattr(qt.Qt, f"Key_{key_name}"), qt.Qt.NoModifier
                )
                _process_events(0.05)
                after_display = _visible_manual_draft_display_values(panel)
                if not _representationally_matches(after_display, expected_display):
                    raise RuntimeError(
                        f"{key_name} did not change only {joint} by {delta:g} {units[joint_index]}."
                    )
                expected_si = _apply_display_step_to_expected_si(
                    before_si,
                    joint_index,
                    math.radians(delta) if units[joint_index] == "deg" else delta / 1000.0,
                )
                after_si = _finite_vector(panel.manualJogJointPositionsSi())
                if not _representationally_matches(after_si, expected_si):
                    raise RuntimeError(f"{key_name} draft SI value does not match its displayed-unit step.")
                runtime = assert_runtime_state(f"{joint} {key_name}")
                event = {
                    "joint": joint,
                    "key": key_name,
                    "direction": "positive" if direction > 0 else "negative",
                    "display_unit": units[joint_index],
                    "displayed_step": delta,
                    "before_display": before_display,
                    "after_display": after_display,
                    "before_si": before_si,
                    "after_si": after_si,
                    "only_selected_draft_changed": True,
                    "draft_diagnostics_after": draft_diagnostics(),
                    "delivery": delivery,
                    **runtime,
                }
                evidence["key_events"].append(event)
                event_label = f"{joint.lower()}-{event['direction']}"
                event["screenshot"] = capture(event_label)
                _record(report, name, "RUNNING", **evidence)

        step_combo.currentIndex = 1
        _process_events(0.05)
        changed_steps = tuple(float(value) for value in step_combo.currentData)
        if len(changed_steps) != 2 or not all(
            math.isclose(value, 0.5, rel_tol=0.0, abs_tol=1e-12)
            for value in changed_steps
        ):
            raise RuntimeError("Selecting the changed keyboard step did not display 0.5 degree / 0.5 mm.")
        before_display = _visible_manual_draft_display_values(panel)
        before_si = _finite_vector(panel.manualJogJointPositionsSi())
        expected_display = list(before_display)
        expected_display[0] += changed_steps[0]
        _focus(key_target)
        delivery = _deliver_key(key_target, qt.Qt.Key_Q, qt.Qt.NoModifier)
        _process_events(0.05)
        after_display = _visible_manual_draft_display_values(panel)
        if not _representationally_matches(after_display, expected_display):
            raise RuntimeError("Changed keyboard step did not move J1 draft by the displayed 0.5 degree.")
        expected_si = _apply_display_step_to_expected_si(
            before_si, 0, math.radians(changed_steps[0])
        )
        after_si = _finite_vector(panel.manualJogJointPositionsSi())
        if not _representationally_matches(after_si, expected_si):
            raise RuntimeError("Changed-step J1 draft SI value does not match the displayed 0.5 degree.")
        changed_step = {
            "key": "Q",
            "joint": "J1",
            "display_unit": "deg",
            "displayed_step": changed_steps[0],
            "before_display": before_display,
            "after_display": after_display,
            "before_si": before_si,
            "after_si": after_si,
            "only_selected_draft_changed": True,
            "draft_diagnostics_after": draft_diagnostics(),
            "delivery": delivery,
            **assert_runtime_state("the changed-step J1 Q key"),
        }
        evidence["changed_step_size"] = changed_step
        capture("changed-step")

        editor = panel.manualJogJointControls[JOINT_NAMES[0]][1]
        _focus(editor)
        if any(bool(shortcut.enabled) for shortcut in shortcuts):
            raise RuntimeError("J1–J5 shortcuts remained enabled while a numeric editor had focus.")
        editor_before = float(editor.value)
        draft_before_editor_key = _visible_manual_draft_display_values(panel)
        delivery = _deliver_key(editor, qt.Qt.Key_Q, qt.Qt.NoModifier)
        _process_events(0.05)
        if not _representationally_matches(
            _visible_manual_draft_display_values(panel), draft_before_editor_key
        ):
            raise RuntimeError("The focused numeric editor did not suppress the J1 Q shortcut.")
        editor_step = float(editor.singleStep)
        if editor_before + editor_step <= float(editor.maximum):
            editor_key, editor_direction = qt.Qt.Key_Up, 1.0
        elif editor_before - editor_step >= float(editor.minimum):
            editor_key, editor_direction = qt.Qt.Key_Down, -1.0
        else:
            raise RuntimeError("The J1 numeric editor has no available arrow-key step.")
        usable_delivery = _deliver_key(editor, editor_key, qt.Qt.NoModifier)
        _process_events(0.05)
        editor_after = float(editor.value)
        if not math.isclose(
            editor_after, editor_before + editor_direction * editor_step,
            rel_tol=0.0, abs_tol=1e-9,
        ):
            raise RuntimeError("The focused J1 numeric editor did not accept its normal arrow-key input.")
        evidence["numeric_editor_focus"] = {
            "shortcut_suppressed": True,
            "shortcut_delivery": delivery,
            "editor_remained_usable": True,
            "arrow_key_delivery": usable_delivery,
            "editor_before": editor_before,
            "editor_after": editor_after,
            "editor_step": editor_step,
            "focus_widget": "QDoubleSpinBox",
            "draft_diagnostics_after": draft_diagnostics(),
            **assert_runtime_state("the focused numeric editor test"),
        }
        capture("numeric-editor")

        checkbox.click()
        _process_events(0.05)
        if checkbox.checked or any(bool(shortcut.enabled) for shortcut in shortcuts):
            raise RuntimeError("Opting out did not immediately disable every J1–J5 shortcut.")
        before_display = _visible_manual_draft_display_values(panel)
        _focus(key_target)
        delivery = _deliver_key(key_target, qt.Qt.Key_Q, qt.Qt.NoModifier)
        _process_events(0.05)
        if not _representationally_matches(
            _visible_manual_draft_display_values(panel), before_display
        ):
            raise RuntimeError("J1 Q remained active after keyboard opt-out.")
        evidence["opt_out"] = {
            "checkbox_checked": False,
            "all_shortcuts_disabled": True,
            "key": "Q",
            "delivery": delivery,
            "draft_unchanged": True,
            "draft_diagnostics_after": draft_diagnostics(),
            **assert_runtime_state("the post-opt-out J1 Q key"),
        }
        capture("opted-out")
        evidence["authority_after"] = authority_state()
        evidence["no_guard_request_plan_or_preview"] = evidence["authority_after"] == authority_before
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
        evidence["failure"] = failure
        try:
            evidence["state_at_failure"] = _actual_joint_state(facade)
            evidence["authority_at_failure"] = authority_state()
            evidence["draft_diagnostics_at_failure"] = draft_diagnostics()
            evidence["opt_in_at_failure"] = bool(checkbox.checked)
            focus_widget = qt.QApplication.focusWidget()
            evidence["focus_at_failure"] = (
                str(focus_widget.objectName) if focus_widget is not None else None
            )
        except Exception as evidence_exc:
            evidence["failure_state_capture_error"] = (
                f"{type(evidence_exc).__name__}: {evidence_exc}"
            )
        try:
            capture("failure")
        except Exception as screenshot_exc:
            evidence["failure_screenshot_error"] = f"{type(screenshot_exc).__name__}: {screenshot_exc}"
    finally:
        try:
            if checkbox.checked:
                checkbox.click()
            _process_events(0.05)
            step_combo.currentIndex = original_step_index
            if accepted_before is not None:
                panel._setManualJogDraftValues(
                    _display_values(accepted_before["accepted_si"]), notify=True
                )
                _process_events(0.05)
                restored_si = _finite_vector(panel.manualJogJointPositionsSi())
                if not _representationally_matches(restored_si, accepted_before["accepted_si"]):
                    raise RuntimeError("Could not restore the manual draft to accepted J1–J5.")
                state_after = _actual_joint_state(facade)
                if not all(
                    _exactly_matches(accepted_before[key], state_after[key])
                    for key in ("accepted_si", "monitored_si", "displayed_si")
                ):
                    raise RuntimeError("Cleanup changed accepted, monitored, or displayed J1–J5 state.")
                evidence["restored_draft_si"] = restored_si
                evidence["accepted_state_unchanged_after_cleanup"] = True
            if checkbox.checked or any(bool(shortcut.enabled) for shortcut in panel._manualJogKeyboardShortcuts):
                raise RuntimeError("Keyboard opt-out cleanup did not disable all shortcuts.")
            evidence["cleanup"] = {
                "keyboard_opted_out": True,
                "step_index_restored": int(step_combo.currentIndex) == original_step_index,
                "draft_restored_to_accepted": accepted_before is not None,
            }
            if evidence["cleanup"]["step_index_restored"] is not True:
                raise RuntimeError("Could not restore the selected keyboard step size.")
            if authority_before is not None:
                authority_after_cleanup = authority_state()
                if authority_after_cleanup != authority_before:
                    raise RuntimeError("Cleanup changed guard, plan, or preview state.")
                evidence["authority_after_cleanup"] = authority_after_cleanup
                evidence["no_guard_request_plan_or_preview"] = True
            if accepted_before is not None:
                capture("restored")
        except Exception as cleanup_exc:
            cleanup_error = f"{type(cleanup_exc).__name__}: {cleanup_exc}"
            evidence["cleanup_error"] = cleanup_error
            failure = failure or cleanup_error
            try:
                evidence["state_at_cleanup_failure"] = _actual_joint_state(facade)
                evidence["authority_at_cleanup_failure"] = authority_state()
                evidence["draft_diagnostics_at_cleanup_failure"] = draft_diagnostics()
                capture("cleanup-failure")
            except Exception as screenshot_exc:
                evidence["cleanup_failure_screenshot_error"] = (
                    f"{type(screenshot_exc).__name__}: {screenshot_exc}"
                )
        status = "FAIL" if failure else "PASS"
        if status == "FAIL":
            evidence["failure"] = failure
        _record(report, name, status, **evidence)

    if failure:
        raise RuntimeError(failure)


def _base_review(facade):
    result = facade.manualBaseReview()
    if not result.success:
        raise RuntimeError(f"Manual Base status is unavailable: {result.message}")
    details = dict(result.details or {})
    if details.get("staged") is True:
        raise RuntimeError("A detached Base candidate was already staged; preserving it.")
    if details.get("identityStatus") != "current":
        raise RuntimeError("Accepted Base identity is stale or unknown.")
    if details.get("acceptanceStatus") == "unknown" or details.get("acceptanceUncertainty"):
        raise RuntimeError("Accepted Base outcome is unknown; stopping before Base actions.")
    if not _valid_matrix(details.get("acceptedMatrixWorldRasMm")):
        raise RuntimeError("Accepted Base matrix evidence is unavailable or invalid.")
    return result


def _run_base_profile_rebind_prerequisite(
    widget, panel, logic, parameter_node, facade, case_path, case_hash,
    allow_base_home_accept, report, evidence_dir, run_id,
):
    status = str(parameter_node.step6BasePlacementStatus or "")
    locked = bool(parameter_node.robotBaseMountLocked)
    if not allow_base_home_accept or status != "Stale" or locked:
        reason = "Base rebind requires the exact opt-in and a Stale, unlocked Base."
        report["base_profile_rebind_prerequisite"] = {"status": "NOT_RUN", "reason": reason}
        _record(report, "base_profile_rebind_prerequisite", "NOT_RUN", reason=reason)
        return

    widget._configureRobotSimulationShellSubstep(1)
    widget._updateStep6PlanningUi()
    _process_events(0.1)
    if panel._activeSubstep != 1:
        raise RuntimeError("Production Manual Base controls are not active for the stale Base rebind.")

    review = facade.manualBaseReview()
    before = dict(review.details or {})
    base = parameter_node.robotBaseTransform
    accepted_matrix = tuple(before.get("acceptedMatrixWorldRasMm") or ())
    profile_before = str(logic.robotProfileFingerprint() or "")
    saved_profile_before = str(base.GetAttribute("DENTOBOT.RobotProfileFingerprint") or "")
    pose_fingerprint_before = str(logic.robotBasePoseFingerprint(base) or "")
    base_fingerprint_before = str(logic.robotBaseFingerprint(parameter_node) or "")
    placement_revision_before = int(parameter_node.step6BasePlacementRevision)
    evidence = {
        "status": "RUNNING",
        "case_sha256_before": case_hash,
        "base_status_before": status,
        "base_locked_before": locked,
        "accepted_matrix_world_ras_mm_before": accepted_matrix,
        "base_pose_fingerprint_before": pose_fingerprint_before,
        "base_fingerprint_before": base_fingerprint_before,
        "saved_robot_profile_fingerprint_before": saved_profile_before,
        "current_robot_profile_fingerprint": profile_before,
        "placement_revision_before": placement_revision_before,
        "native_scene_acknowledgement": "deferred_until_after_connect",
    }
    report["base_profile_rebind_prerequisite"] = evidence
    _write_report(report)
    if (
        facade.capabilities().connected
        or not review.success
        or before.get("staged") is True
        or before.get("identityStatus") != "current"
        or before.get("acceptanceStatus") == "unknown"
        or before.get("acceptanceUncertainty")
        or not _valid_matrix(accepted_matrix)
        or not profile_before
        or not saved_profile_before
        or saved_profile_before == profile_before
        or not pose_fingerprint_before
        or not base_fingerprint_before
        or _sha256_file(case_path) != case_hash
    ):
        evidence.update({"status": "FAIL", "reason": "Stale Base did not satisfy profile-rebind preconditions."})
        _write_report(report)
        raise RuntimeError(
            "Stale Base does not match the unlocked current-profile migration preconditions."
        )

    if panel._activeSubstep != 1 or not panel.beginManualBaseReviewButton.enabled:
        evidence.update({"status": "FAIL", "reason": "Production Review Current Base was disabled."})
        _write_report(report)
        raise RuntimeError("Production Review Current Base is disabled for the stale Base rebind.")
    panel.beginManualBaseReviewButton.click()
    _process_events(0.1)
    staged = facade.manualBaseReview()
    staged_details = dict(staged.details or {})
    if (
        not staged.success
        or staged_details.get("staged") is not True
        or staged_details.get("identityStatus") != "current"
        or not _same_matrix(staged_details.get("candidateMatrixWorldRasMm"), accepted_matrix)
        or not _same_matrix(staged_details.get("acceptedMatrixWorldRasMm"), accepted_matrix)
        or bool(parameter_node.robotBaseMountLocked)
        or str(parameter_node.step6BasePlacementStatus or "") != "Stale"
        or str(logic.robotProfileFingerprint() or "") != profile_before
        or str(logic.robotBasePoseFingerprint(base) or "") != pose_fingerprint_before
        or str(logic.robotBaseFingerprint(parameter_node) or "") != base_fingerprint_before
    ):
        evidence.update({"status": "FAIL", "stage_result": staged_details})
        raise RuntimeError("Production Base review did not stage a detached copy of the unchanged accepted matrix.")
    evidence["stage_result"] = staged_details
    evidence["screenshot_staged"] = _capture(
        report, evidence_dir, run_id, "base-profile-rebind-staged"
    )
    _write_report(report)

    accept_owner = widget.ui.lockRobotBaseMountButton
    if not accept_owner.enabled:
        evidence.update({"status": "FAIL", "reason": "Existing Accept Base owner was disabled."})
        _write_report(report)
        raise RuntimeError("Existing Accept Base owner is disabled for the staged profile rebind.")
    accept_owner.click()
    _process_events(0.2)
    evidence["screenshot_accepted"] = _capture(
        report, evidence_dir, run_id, "base-profile-rebind-accepted"
    )
    after_result = facade.manualBaseReview()
    after = dict(after_result.details or {})
    profile_after = str(logic.robotProfileFingerprint() or "")
    saved_profile_after = str(base.GetAttribute("DENTOBOT.RobotProfileFingerprint") or "")
    pose_fingerprint_after = str(logic.robotBasePoseFingerprint(base) or "")
    base_fingerprint_after = str(logic.robotBaseFingerprint(parameter_node) or "")
    case_hash_after = _sha256_file(case_path)
    evidence.update({
        "status": "PASS",
        "accept_owner": str(accept_owner.text),
        "accept_result": after,
        "base_status_after": str(parameter_node.step6BasePlacementStatus or ""),
        "base_locked_after": bool(parameter_node.robotBaseMountLocked),
        "accepted_matrix_world_ras_mm_after": after.get("acceptedMatrixWorldRasMm"),
        "base_pose_fingerprint_after": pose_fingerprint_after,
        "base_fingerprint_after": base_fingerprint_after,
        "saved_robot_profile_fingerprint_after": saved_profile_after,
        "current_robot_profile_fingerprint_after": profile_after,
        "placement_revision_after": int(parameter_node.step6BasePlacementRevision),
        "case_sha256_after": case_hash_after,
        "accepted_matrix_unchanged": _same_matrix(
            after.get("acceptedMatrixWorldRasMm"), accepted_matrix
        ),
        "base_pose_fingerprint_unchanged": pose_fingerprint_after == pose_fingerprint_before,
        "current_profile_rebound": (
            saved_profile_before != profile_before
            and saved_profile_after == profile_before == profile_after
        ),
        "base_fingerprint_rebound_for_lock": (
            base_fingerprint_after != base_fingerprint_before
            and int(parameter_node.step6BasePlacementRevision) == placement_revision_before + 1
        ),
        "case_unchanged": case_hash_after == case_hash,
    })
    _write_report(report)
    if (
        not after_result.success
        or after.get("staged") is True
        or after.get("candidateMatrixWorldRasMm") is not None
        or after.get("identityStatus") != "current"
        or after.get("acceptanceStatus") == "unknown"
        or after.get("acceptanceUncertainty")
        or not bool(parameter_node.robotBaseMountLocked)
        or str(parameter_node.step6BasePlacementStatus or "") == "Stale"
        or not evidence["accepted_matrix_unchanged"]
        or not evidence["base_pose_fingerprint_unchanged"]
        or not evidence["current_profile_rebound"]
        or not evidence["base_fingerprint_rebound_for_lock"]
        or not evidence["case_unchanged"]
        or facade.capabilities().connected
    ):
        evidence["status"] = "FAIL"
        _write_report(report)
        raise RuntimeError(
            "Preconnect Accept Base did not prove the current-profile rebind with unchanged Base pose and case."
        )
    evidence["scene_acknowledgement_deferred"] = True
    _record(
        report,
        "base_profile_rebind_prerequisite",
        "PASS",
        **{key: value for key, value in evidence.items() if key != "status"},
    )


def _target_j1(logic, parameter_node, accepted: dict[str, float]):
    for sign in (1, -1):
        target = dict(accepted)
        target[JOINT_NAMES[0]] += sign * math.radians(ACCEPTED_DELTA_DEG)
        if _within_both_limits(logic, parameter_node, target) is not None:
            return target, f"J1 { '+' if sign > 0 else '-' } {ACCEPTED_DELTA_DEG:g} degree"
    raise RuntimeError("J1 +/- 0.1 degree is outside a current reviewed or mechanical limit.")


def _run_offline_base_home_configuration(
    widget, panel, logic, parameter_node, facade, case_path, case_hash,
    output_path, report, evidence_dir, run_id,
):
    name = "offline_base_home_configuration"
    evidence = {
        "status": "RUNNING",
        "opt_in": "DENTOBOT_HEADED_OFFLINE_HOME_SETUP=1",
        "acceptance_opt_in": "DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT=1",
        "case_sha256_before": case_hash,
        "offline_case_output": str(output_path),
        "screenshots": {},
        "screenshot_framing": {},
    }
    report["offline_home_setup"] = evidence
    report[name] = evidence
    _write_report(report)

    def stop(reason, **details):
        evidence.update({"status": "FAIL", "reason": reason, **details})
        _record(report, name, "FAIL", **{k: v for k, v in evidence.items() if k != "status"})
        raise RuntimeError(reason)

    def physical_joints():
        return tuple(float(getattr(parameter_node, field)) for field in (
            "robotJoint1Deg", "robotJoint2Mm", "robotJoint3Deg",
            "robotJoint4Mm", "robotJoint5Deg",
        ))

    try:
        if facade.capabilities().connected:
            stop("Offline Home probe requires ROS/MoveIt to remain disconnected.")
        if _sha256_file(case_path) != case_hash:
            stop("The source case changed before offline Base/Home setup.")
        profile = str(logic.robotProfileFingerprint() or "")
        if not profile:
            stop("The current robot profile fingerprint is unavailable.")
        joints_before = physical_joints()
        home_before = logic.taskHomeRecord(parameter_node)
        home_revision_before = int(home_before.revision) if home_before is not None else 0
        evidence.update({
            "robot_profile_fingerprint_before": profile,
            "robot_joint_parameters_before": joints_before,
            "saved_home_before": home_before.to_dict() if home_before else None,
            "saved_home_revision_before": home_revision_before,
            "route_preview_before": {
                "route_authority": report.get("route_authority"),
                "planner_calls": report.get("planner_calls"),
                "preview_started": report.get("preview_started"),
                "preview_active": bool(facade.previewActive),
            },
            "jog_requests_before": report.get("jog_requests", 0),
        })
        if evidence["route_preview_before"]["route_authority"] != "none" or evidence["route_preview_before"]["planner_calls"] != 0 or evidence["route_preview_before"]["preview_started"] or evidence["route_preview_before"]["preview_active"]:
            stop("Route or preview authority exists before the offline probe.")

        widget._configureRobotSimulationShellSubstep(1)
        widget._updateStep6PlanningUi()
        _process_events(0.1)
        if panel._activeSubstep != 1:
            stop("Production 6.1 Base controls are not active.")
        before_result = _base_review(facade)
        base_matrix = tuple(before_result.details["acceptedMatrixWorldRasMm"])
        evidence["base_matrix_before"] = base_matrix
        evidence["base_locked_before"] = bool(parameter_node.robotBaseMountLocked)
        evidence["base_status_before"] = str(parameter_node.step6BasePlacementStatus or "")
        evidence["screenshot_framing"]["base_before"] = _scroll_to_visible(
            widget, panel.manualBaseReviewGroup, "offline Base before review"
        )
        evidence["screenshots"]["base_before"] = _capture(
            report, evidence_dir, run_id, "offline-home-base-before"
        )

        if bool(parameter_node.robotBaseMountLocked):
            unlock = widget.ui.unlockRobotBaseMountButton
            if not unlock.enabled:
                stop("Production 6.1 Unlock Base control is disabled.")
            unlock.click()
            _process_events(0.1)
            if bool(parameter_node.robotBaseMountLocked):
                stop("Production Unlock Base did not unlock the accepted Base.")
        unlocked = facade.manualBaseReview()
        if not unlocked.success or unlocked.details.get("staged") is True or not _same_matrix(unlocked.details.get("acceptedMatrixWorldRasMm"), base_matrix):
            stop("Unlocking Base changed its matrix or left a detached candidate.", review=unlocked.details)
        evidence["screenshot_framing"]["base_unlocked"] = _scroll_to_visible(
            widget, panel.manualBaseReviewGroup, "unlocked offline Base"
        )
        evidence["screenshots"]["base_unlocked"] = _capture(
            report, evidence_dir, run_id, "offline-home-base-unlocked"
        )
        if not panel.beginManualBaseReviewButton.enabled:
            stop("Production Review Current Base control is disabled.")
        panel.beginManualBaseReviewButton.click()
        _process_events(0.1)
        staged_result = facade.manualBaseReview()
        staged = dict(staged_result.details or {})
        if not staged_result.success or staged.get("identityStatus") != "current" or staged.get("staged") is not True or staged.get("acceptanceStatus") == "unknown" or staged.get("acceptanceUncertainty") or not _same_matrix(staged.get("candidateMatrixWorldRasMm"), base_matrix) or not _same_matrix(staged.get("acceptedMatrixWorldRasMm"), base_matrix):
            stop("Review Current Base did not stage the unchanged accepted matrix.", review=staged)
        evidence["base_review_staged"] = staged
        evidence["screenshot_framing"]["base_staged"] = _scroll_to_visible(
            widget, panel.manualBaseReviewGroup, "staged offline Base"
        )
        evidence["screenshots"]["base_staged"] = _capture(
            report, evidence_dir, run_id, "offline-home-base-staged"
        )
        accept_base = widget.ui.lockRobotBaseMountButton
        if not accept_base.enabled:
            stop("Production Accept Base owner is disabled for the unchanged matrix.")
        accept_base.click()
        _process_events(0.2)
        accepted_result = facade.manualBaseReview()
        accepted = dict(accepted_result.details or {})
        base = parameter_node.robotBaseTransform
        current_profile = str(logic.robotProfileFingerprint() or "")
        base_profile = str(base.GetAttribute("DENTOBOT.RobotProfileFingerprint") or "")
        base_issues = tuple(logic.step6BasePlacementFreshnessIssues(parameter_node))
        foundation = logic.evaluateCaseFoundationEligibility(parameter_node)
        if not accepted_result.success or accepted.get("identityStatus") != "current" or accepted.get("staged") is True or accepted.get("candidateMatrixWorldRasMm") is not None or accepted.get("acceptanceStatus") == "unknown" or accepted.get("acceptanceUncertainty") or not parameter_node.robotBaseMountLocked or not _same_matrix(accepted.get("acceptedMatrixWorldRasMm"), base_matrix) or current_profile != profile or base_profile != profile or base_issues or not foundation.get("base", {}).get("eligible"):
            stop("Accept Base did not leave an unchanged, current, eligible Base.", review=accepted, base_freshness_issues=base_issues, foundation_base=foundation.get("base"), robot_profile_fingerprint=current_profile, base_profile_fingerprint=base_profile)
        evidence["base_matrix_after"] = tuple(accepted["acceptedMatrixWorldRasMm"])
        evidence["base_current_and_eligible"] = True
        evidence["robot_profile_fingerprint_after"] = current_profile
        evidence["screenshot_framing"]["base_accepted"] = _scroll_to_visible(
            widget, panel.manualBaseReviewGroup, "accepted offline Base"
        )
        evidence["screenshots"]["base_accepted"] = _capture(
            report, evidence_dir, run_id, "offline-home-base-accepted"
        )

        widget._configureRobotSimulationShellSubstep(2)
        widget._updateStep6PlanningUi()
        _process_events(0.1)
        if panel._activeSubstep != 2:
            stop("Production 6.2 Task Home controls are not active.")
        local_pose = _finite_vector(widget._robotJointPositionsSi())
        reset_review = facade.manualTaskHomeReview()
        reset_review_details = dict(reset_review.details or {})
        if not reset_review.success:
            stop("Could not determine the current production Reset Draft target.", review=reset_review_details)
        reset_target = (
            _finite_vector(reset_review_details.get("configuredJointPositionsSi"))
            if reset_review_details.get("configurationReady") is True
            else local_pose
        )
        if reset_target is None:
            stop(
                "Production Home Reset has no finite current configuration or local pose.",
                reset_review=reset_review_details,
            )
        evidence["reset_target_source"] = (
            "saved_home_configuration"
            if reset_review_details.get("configurationReady") is True
            else "current_local_pose"
        )
        evidence["reset_target_joint_positions_si"] = reset_target
        reset_button = panel.resetManualJogDraftButton
        if not reset_button.enabled:
            stop("Production 6.2 Reset Draft to Local Robot Pose is disabled.")
        reset_button.click()
        _process_events(0.05)
        draft = _finite_vector(panel.manualJogJointPositionsSi())
        if not _exactly_matches(draft, reset_target):
            stop(
                "6.2 Reset Draft did not use its current saved-Home/local-pose target.",
                reset_target=reset_target,
                observed_draft=draft,
            )
        evidence["offline_draft_joint_positions_si"] = draft
        evidence["screenshot_framing"]["home_draft_before_review"] = _scroll_to_visible(
            widget, panel.homeGroup, "offline Home draft before review"
        )
        evidence["screenshots"]["home_draft_before_review"] = _capture(
            report, evidence_dir, run_id, "offline-home-draft-before-review"
        )
        if not panel.reviewTaskHomeButton.enabled:
            stop("Production Review Draft as Task Home control is disabled.")
        panel.reviewTaskHomeButton.click()
        _process_events(0.1)
        staged_home_result = facade.manualTaskHomeReview()
        staged_home = dict(staged_home_result.details or {})
        if not staged_home_result.success or staged_home.get("setupMode") != "offline" or staged_home.get("identityStatus") != "current" or staged_home.get("staged") is not True or staged_home.get("acceptanceStatus") != "review" or not _exactly_matches(staged_home.get("candidateJointPositionsSi"), draft) or staged_home.get("acceptedJointPositionsSi") is not None:
            stop("Offline Review Draft did not stage the exact local J1–J5 vector.", review=staged_home)
        evidence["home_review_staged"] = staged_home
        evidence["screenshot_framing"]["home_staged"] = _scroll_to_visible(
            widget, panel.homeGroup, "staged offline Home"
        )
        evidence["screenshots"]["home_staged"] = _capture(
            report, evidence_dir, run_id, "offline-home-staged"
        )
        if not panel.acceptTaskHomeButton.enabled:
            stop("Production Save Home Configuration control is disabled.")
        panel.acceptTaskHomeButton.click()
        _process_events(0.1)
        saved_result = facade.manualTaskHomeReview()
        saved_details = dict(saved_result.details or {})
        home_after = logic.taskHomeRecord(parameter_node)
        saved_vector = _finite_vector(dict(zip(home_after.joint_names, home_after.joint_positions_si))) if home_after is not None else None
        if not saved_result.success or saved_details.get("setupMode") != "offline" or saved_details.get("identityStatus") != "current" or saved_details.get("staged") is not False or saved_details.get("acceptanceStatus") != "configuration_saved" or saved_details.get("runtimeValidated") is not False or saved_details.get("acceptedJointPositionsSi") is not None or saved_details.get("acceptanceUncertainty") or home_after is None or home_after.revision != home_revision_before + 1 or home_after.runtime_validation_status != "Unreviewed" or not _exactly_matches(saved_vector, draft) or not _exactly_matches(saved_details.get("configuredJointPositionsSi"), draft) or home_after.base_fingerprint != str(logic.robotBaseFingerprint(parameter_node) or "") or home_after.robot_profile_fingerprint != profile:
            stop("Offline Save Home did not create the exact next Unreviewed configuration.", review=saved_details, saved_home=home_after.to_dict() if home_after else None)
        if not _exactly_matches(physical_joints(), joints_before):
            stop("Physical J1–J5 parameter values changed during offline configuration.")
        base_after_home = _base_review(facade)
        base_after_home_details = dict(base_after_home.details or {})
        current_base_fingerprint = str(logic.robotBaseFingerprint(parameter_node) or "")
        base_issues_after_home = tuple(logic.step6BasePlacementFreshnessIssues(parameter_node))
        if not base_after_home.success or base_after_home_details.get("identityStatus") != "current" or base_after_home_details.get("staged") is True or base_after_home_details.get("acceptanceStatus") == "unknown" or base_after_home_details.get("acceptanceUncertainty") or not _same_matrix(base_after_home_details.get("acceptedMatrixWorldRasMm"), base_matrix) or current_base_fingerprint != home_after.base_fingerprint or base_issues_after_home:
            stop("Base identity or matrix changed while saving offline Home.", base_review=base_after_home_details, base_freshness_issues=base_issues_after_home)
        if facade.capabilities().connected:
            stop("ROS/MoveIt connected during offline Base/Home setup.")
        controls_disabled = {
            "check_draft_state": not panel.checkManualDraftStateButton.enabled,
            "reconcile_manual_jog": not panel.reconcileManualJogButton.enabled,
            "guarded_jog": not panel.guardedManualJogButton.enabled,
            "tcp_drag": not panel.tcpDragEnabledCheckBox.enabled,
            "solve_ik": not panel.solveIkButton.enabled,
            "plan_goal": not panel.planGoalButton.enabled,
            "plan_approach": not panel.planApproachButton.enabled,
            "compare_planners": not panel.comparePlannersButton.enabled,
            "plan_drilling": not panel.planDrillingButton.enabled,
            "preview_approach": not panel.previewApproachButton.enabled,
            "preview_drilling": not panel.previewDrillingButton.enabled,
        }
        if not all(controls_disabled.values()):
            stop("A native guard, IK, planner, or preview control remained enabled offline.", controls_disabled=controls_disabled)
        route_preview_after = {
            "route_authority": report.get("route_authority"),
            "planner_calls": report.get("planner_calls"),
            "preview_started": report.get("preview_started"),
            "preview_active": bool(facade.previewActive),
        }
        evidence["route_preview_after"] = route_preview_after
        evidence["jog_requests_after"] = report.get("jog_requests", 0)
        if route_preview_after["route_authority"] != "none" or route_preview_after["planner_calls"] != 0 or route_preview_after["preview_started"] is not False or route_preview_after["preview_active"] or report.get("jog_requests", 0) != evidence["jog_requests_before"]:
            stop("Offline setup changed jog, planner, route, or preview authority.")
        evidence.update({
            "saved_home_after": home_after.to_dict(),
            "saved_home_revision_after": home_after.revision,
            "saved_home_vector_si": saved_vector,
            "robot_joint_parameters_after": physical_joints(),
            "controls_disabled": controls_disabled,
            "no_staged_or_uncertain_state": True,
            "ros_inactive_throughout": True,
            "case_sha256_after": _sha256_file(case_path),
        })
        if evidence["case_sha256_after"] != case_hash:
            stop("Source case changed during offline Home setup.")
        evidence["screenshot_framing"]["home_saved"] = _scroll_to_visible(
            widget, panel.homeGroup, "saved offline Home"
        )
        evidence["screenshots"]["home_saved"] = _capture(
            report, evidence_dir, run_id, "offline-home-saved"
        )
        save_evidence = _save_current_case(widget, output_path, case_path, case_hash)
        validate_case_bundle(output_path)
        evidence["saved_case"] = save_evidence
        evidence["provenance"] = {
            "checkout": report.get("checkout"),
            "runner_sha256": _sha256_file(Path(__file__).resolve()),
            "input_case_sha256": case_hash,
            "offline_case_sha256": save_evidence["sha256"],
            "opt_in": evidence["opt_in"],
            "acceptance_opt_in": evidence["acceptance_opt_in"],
        }
        evidence["status"] = "PASS"
        report["offline_saved_case"] = save_evidence
        _record(report, name, "PASS", **{k: v for k, v in evidence.items() if k != "status"})
        return evidence
    except Exception as exc:
        if evidence.get("status") == "RUNNING":
            evidence.update({"status": "FAIL", "reason": f"{type(exc).__name__}: {exc}"})
            _record(report, name, "FAIL", **{k: v for k, v in evidence.items() if k != "status"})
        raise


def _validate_offline_home_after_connection(
    widget, panel, logic, parameter_node, facade, report, evidence_dir, run_id,
):
    offline = report.get("offline_home_setup")
    if not isinstance(offline, Mapping) or offline.get("status") != "PASS":
        return None
    evidence = {"status": "RUNNING", "screenshots": {}, "screenshot_framing": {}}
    offline["post_connect_validation"] = evidence
    _write_report(report)

    def stop(reason, **details):
        evidence.update({"status": "FAIL", "reason": reason, **details})
        offline["status"] = "FAIL"
        _record(
            report,
            "offline_base_home_configuration",
            "FAIL",
            reason=reason,
            offline_home_setup=offline,
            post_connect_validation=evidence,
        )
        _write_report(report)
        raise RuntimeError(reason)

    saved_home = logic.taskHomeRecord(parameter_node)
    saved_vector = offline.get("saved_home_vector_si")
    saved_home_evidence = offline.get("saved_home_after")
    current_base_fingerprint = str(logic.robotBaseFingerprint(parameter_node) or "")
    current_profile_fingerprint = str(logic.robotProfileFingerprint() or "")
    review = facade.manualTaskHomeReview()
    review_details = dict(review.details or {})
    saved_home_vector_now = (
        _finite_vector(dict(zip(saved_home.joint_names, saved_home.joint_positions_si)))
        if saved_home is not None else None
    )
    if not facade.capabilities().connected or not review.success or review_details.get("setupMode") != "connected" or review_details.get("identityStatus") != "current" or review_details.get("staged") is True or review_details.get("acceptanceStatus") == "unknown" or review_details.get("acceptanceUncertainty") or saved_home is None or not isinstance(saved_home_evidence, Mapping) or saved_home.revision != saved_home_evidence.get("revision") or saved_home.runtime_validation_status != "Unreviewed" or not _exactly_matches(saved_home_vector_now, saved_vector) or saved_home.base_fingerprint != current_base_fingerprint or saved_home.robot_profile_fingerprint != current_profile_fingerprint or facade.taskHomeRuntimeValidated(parameter_node) is not False:
        stop("Saved offline Home identity/configuration was not preserved Unreviewed after ROS scene acknowledgement.", review=review_details, saved_home=saved_home.to_dict() if saved_home else None, saved_home_evidence=saved_home_evidence, current_base_fingerprint=current_base_fingerprint, current_profile_fingerprint=current_profile_fingerprint)
    state = _actual_joint_state(facade)
    accepted = state.get("accepted_si")
    evidence["saved_home_vector_si"] = saved_vector
    evidence["saved_home_record_before_validation"] = saved_home.to_dict()
    evidence["saved_home_revision_before_validation"] = saved_home.revision
    evidence["base_fingerprint_before_validation"] = current_base_fingerprint
    evidence["robot_profile_fingerprint_before_validation"] = current_profile_fingerprint
    evidence["current_state"] = state
    if not accepted or not _exactly_matches(saved_vector, accepted):
        stop("Saved offline Home differs from current accepted pose; stopping without staging or motion.", mismatch=True, configured_home=saved_vector, accepted_current_pose=accepted, monitored_current_pose=state.get("monitored_si"), displayed_current_pose=state.get("displayed_si"), mismatch_action="stopped_without_staging_or_motion")
    if not all(_exactly_matches(accepted, state.get(key)) for key in ("monitored_si", "displayed_si")):
        stop("Accepted, monitored, and displayed J1–J5 differ after ROS acknowledgement.", state=state)
    widget._configureRobotSimulationShellSubstep(2)
    widget._updateStep6PlanningUi()
    _process_events(0.1)
    if panel._activeSubstep != 2 or not panel.resetManualJogDraftButton.enabled:
        stop("Production 6.2 Home Reset control is unavailable.")
    evidence["screenshot_framing"]["before_validation"] = _scroll_to_visible(
        widget, panel.homeGroup, "offline Home before runtime validation"
    )
    evidence["screenshots"]["before_validation"] = _capture(
        report, evidence_dir, run_id, "offline-home-postconnect-before-validation"
    )
    panel.resetManualJogDraftButton.click()
    _process_events(0.05)
    if not _exactly_matches(panel.manualJogJointPositionsSi(), saved_vector):
        stop("6.2 Reset Draft did not restore the saved offline Home.")
    if not panel.reviewTaskHomeButton.enabled:
        stop("Production Review Draft as Task Home is disabled for the matching pose.")
    panel.reviewTaskHomeButton.click()
    _process_events(0.1)
    staged = facade.manualTaskHomeReview()
    staged_details = dict(staged.details or {})
    if not staged.success or staged_details.get("identityStatus") != "current" or staged_details.get("staged") is not True or staged_details.get("acceptanceStatus") != "review" or not _exactly_matches(staged_details.get("candidateJointPositionsSi"), saved_vector) or not _exactly_matches(staged_details.get("acceptedJointPositionsSi"), accepted):
        stop("6.2 review did not stage saved Home matching current accepted state.", stage_result=staged_details)
    if not panel.acceptTaskHomeButton.enabled:
        stop("Production Accept and Validate Task Home is disabled for the matching pose.")
    evidence["staged_review"] = staged_details
    panel.acceptTaskHomeButton.click()
    _process_events(0.2)
    accepted_review = facade.manualTaskHomeReview()
    accepted_details = dict(accepted_review.details or {})
    validated_home = logic.taskHomeRecord(parameter_node)
    validated_vector = _finite_vector(dict(zip(validated_home.joint_names, validated_home.joint_positions_si))) if validated_home is not None else None
    post_state = _actual_joint_state(facade)
    evidence.update({
        "accepted_review": accepted_details,
        "validated_home": validated_home.to_dict() if validated_home else None,
        "validated_vector_si": validated_vector,
        "post_validation_state": post_state,
    })
    if not accepted_review.success or accepted_details.get("identityStatus") != "current" or accepted_details.get("acceptanceStatus") != "accepted" or accepted_details.get("staged") is not False or accepted_details.get("runtimeValidated") is not True or validated_home is None or validated_home.runtime_validation_status != "Validated" or facade.taskHomeRuntimeValidated(parameter_node) is not True or not _exactly_matches(validated_vector, saved_vector) or not all(_exactly_matches(saved_vector, post_state.get(key)) for key in ("accepted_si", "monitored_si", "displayed_si")):
        stop("Explicit connected validation did not preserve and validate the saved Home vector.")
    evidence["screenshot_framing"]["after_validation"] = _scroll_to_visible(
        widget, panel.homeGroup, "validated offline Home"
    )
    evidence["screenshots"]["after_validation"] = _capture(
        report, evidence_dir, run_id, "offline-home-postconnect-after-validation"
    )
    evidence["status"] = "PASS"
    evidence["runtime_validated_same_saved_vector"] = True
    _record(
        report,
        "offline_base_home_configuration",
        "PASS",
        offline_home_setup=offline,
        post_connect_validation=evidence,
    )
    _write_report(report)
    return evidence


def _accept_current_state_as_task_home(
    widget, panel, logic, parameter_node, facade, report, evidence_dir, run_id,
    *, phase, evidence, stop,
):
    """Stage and accept the exact live J1-J5 state as Task Home (production controls)."""
    widget._configureRobotSimulationShellSubstep(3)
    widget._updateStep6PlanningUi()
    _show_step63_view(panel, 0, 0)
    state_before = _actual_joint_state(facade)
    state_fields = ("accepted_si", "monitored_si", "displayed_si")
    if (
        not all(state_before.get(name) for name in state_fields)
        or not all(_exactly_matches(state_before["accepted_si"], state_before[name])
                   for name in state_fields[1:])
    ):
        stop("Accepted, monitored, and displayed current state must match exactly for J1–J5.")
    accepted = _finite_vector(state_before["accepted_si"])
    old_home_json = str(parameter_node.step6TaskHomeJson or "")
    old_home = logic.taskHomeRecord(parameter_node)
    old_revision = getattr(old_home, "revision", None) if old_home is not None else 0
    if isinstance(old_revision, bool) or not isinstance(old_revision, int) or old_revision < 0:
        stop("Saved Task Home revision is invalid; acceptance stopped before staging.")
    old_runtime_validated = facade.taskHomeRuntimeValidated(parameter_node)
    existing_review = facade.manualTaskHomeReview()
    existing_details = dict(existing_review.details or {})
    if (
        not existing_review.success
        or existing_details.get("identityStatus") != "current"
        or existing_details.get("staged") is True
        or existing_details.get("acceptanceStatus") == "unknown"
        or existing_details.get("acceptanceUncertainty")
    ):
        stop("Task Home review is stale, staged, or uncertain; preserving the existing candidate.")

    panel._setManualJogDraftValues(_display_values(accepted), notify=True)
    if not _representationally_matches(panel.manualJogJointPositionsSi(), accepted):
        stop("Visible controls cannot represent the exact current J1–J5 Home vector.")
    widget._configureRobotSimulationShellSubstep(2)
    widget._updateStep6PlanningUi()
    _process_events(0.1)
    if not panel.reviewTaskHomeButton.enabled:
        stop("Production Review Draft as Task Home control is disabled.")
    panel.reviewTaskHomeButton.click()
    _process_events(0.1)
    staged = facade.manualTaskHomeReview()
    staged_details = dict(staged.details or {})
    staged_state = _actual_joint_state(facade)
    staged_home = logic.taskHomeRecord(parameter_node)
    if (
        not staged.success
        or staged_details.get("identityStatus") != "current"
        or staged_details.get("staged") is not True
        or staged_details.get("acceptanceStatus") != "review"
        or not _representationally_matches(staged_details.get("candidateJointPositionsSi"), accepted)
        or not _representationally_matches(staged_details.get("acceptedJointPositionsSi"), accepted)
        or str(parameter_node.step6TaskHomeJson or "") != old_home_json
        or (getattr(staged_home, "revision", None) if staged_home is not None else None) != old_revision
        or facade.taskHomeRuntimeValidated(parameter_node) != old_runtime_validated
        or not all(_exactly_matches(state_before[name], staged_state.get(name)) for name in state_fields)
    ):
        stop("Task Home candidate was not detached from saved Home and live J1–J5 state.")
    evidence.update({"home_candidate": staged_details, "home_state_before": state_before})
    evidence["screenshots"] = {}
    _write_report(report)
    _scroll_to_visible(widget, panel.homeGroup, "profile migration Task Home candidate")
    evidence["screenshots"]["home_staged"] = _capture(
        report, evidence_dir, run_id, f"{phase}-task-home-staged"
    )
    if not panel.acceptTaskHomeButton.enabled:
        stop("Production Accept Task Home control is disabled for the detached candidate.")
    report["task_home_acceptance_attempted"] = True
    _write_report(report)
    panel.acceptTaskHomeButton.click()
    _process_events(0.2)
    _scroll_to_visible(widget, panel.homeGroup, "profile migration accepted Task Home")
    evidence["screenshots"]["home_accepted"] = _capture(
        report, evidence_dir, run_id, f"{phase}-task-home-accepted"
    )
    accepted_review = facade.manualTaskHomeReview()
    accepted_details = dict(accepted_review.details or {})
    saved_home = logic.taskHomeRecord(parameter_node)
    saved_home_vector = (
        _finite_vector(dict(zip(saved_home.joint_names, saved_home.joint_positions_si)))
        if saved_home is not None else None
    )
    home_revision = getattr(saved_home, "revision", None) if saved_home is not None else None
    accepted_state = _actual_joint_state(facade)
    if (
        not accepted_review.success
        or accepted_details.get("identityStatus") != "current"
        or accepted_details.get("acceptanceStatus") != "accepted"
        or accepted_details.get("staged") is not False
        or accepted_details.get("acceptanceUncertainty")
        or not isinstance(home_revision, int)
        or isinstance(home_revision, bool)
        or home_revision <= old_revision
        or saved_home is None
        or saved_home.runtime_validation_status != "Validated"
        or facade.taskHomeRuntimeValidated(parameter_node) is not True
        or saved_home_vector is None
        or not all(_representationally_matches(saved_home_vector, accepted_state.get(name))
                   for name in state_fields)
        or not all(_exactly_matches(state_before[name], accepted_state.get(name))
                   for name in state_fields)
        or not _representationally_matches(accepted_details.get("acceptedJointPositionsSi"), accepted)
    ):
        stop("Accepted Task Home is not a new runtime-validated record matching live J1–J5 state.")
    evidence.update({
        "home_revision_before": old_revision,
        "home_revision_after": home_revision,
        "saved_home": saved_home.to_dict(),
        "home_state_after_accept": accepted_state,
    })
    _write_report(report)


def _ensure_current_home_workspace_task(
    widget, panel, logic, parameter_node, facade, case_path, case_hash,
    report, evidence_dir, run_id, *, phase, check_name, skip_reason=None,
    workspace_diagnostic=False,
):
    evidence = {"phase": phase, "status": "RUNNING", "case_sha256_before": case_hash}
    report[check_name] = evidence
    _write_report(report)

    def stop(reason):
        evidence.update({"status": "FAIL", "reason": reason})
        _write_report(report)
        raise RuntimeError(reason)

    if skip_reason:
        evidence.update({"status": "NOT_RUN", "reason": skip_reason})
        _record(report, check_name, "NOT_RUN", phase=phase, reason=skip_reason)
        return

    if _sha256_file(case_path) != case_hash:
        stop("The source case changed before current Home/workspace/task review.")
    confirmed = logic.confirmedTaskRecord(parameter_node)
    task_issues = (
        tuple(logic.confirmedTaskFreshnessIssues(parameter_node))
        if confirmed is not None else ("Confirmed task is absent.",)
    )
    limits_reviewed = bool(logic.assistedTaskLimitsReviewed(parameter_node))
    home_current = bool(facade.taskHomeRuntimeValidated(parameter_node))
    workspace_current = bool(facade.workspaceRuntimeValidated(parameter_node))
    current = {
        "assisted_limits_reviewed": limits_reviewed,
        "confirmed_task_present": confirmed is not None,
        "confirmed_task_freshness_issues": task_issues,
        "task_home_runtime_validated": home_current,
        "workspace_runtime_validated": workspace_current,
    }
    needs_recovery = not limits_reviewed or confirmed is None or bool(task_issues)
    if phase in {"before_save", "before_planning"}:
        needs_recovery = needs_recovery or not home_current or not workspace_current
    if workspace_diagnostic and phase == "after_scene_ack":
        needs_recovery = True
    evidence["prerequisites_before"] = current
    if not needs_recovery:
        evidence.update({"status": "NOT_RUN", "already_current": True})
        _record(
            report, check_name, "NOT_RUN", phase=phase, already_current=True,
            prerequisites=current,
        )
        return

    authority_before = {
        "route_authority": report["route_authority"],
        "planner_calls": report["planner_calls"],
        "preview_started": report["preview_started"],
        "preview_active": bool(facade.previewActive),
        "return_home_required": bool(facade.returnHomeRequired),
    }
    if (
        authority_before["route_authority"] != "none"
        or authority_before["planner_calls"] != 0
        or authority_before["preview_started"] is not False
        or authority_before["preview_active"]
        or authority_before["return_home_required"]
    ):
        stop("Route or preview authority is already present; prerequisite repair stopped.")
    evidence["route_preview_before"] = authority_before

    _accept_current_state_as_task_home(
        widget, panel, logic, parameter_node, facade, report, evidence_dir, run_id,
        phase=phase, evidence=evidence, stop=stop,
    )

    widget._configureRobotSimulationShellSubstep(3)
    widget._updateStep6PlanningUi()
    _show_step63_view(panel, 1, 1)
    saved_workspace_json_before_roi = str(
        parameter_node.step6AssistedLimitProposalJson or ""
    )
    runtime_workspace_key_before_roi = str(
        getattr(facade, "_runtime_validated_workspace_key", "") or ""
    )
    workspace_model = logic.robotWorkspaceModelNode()
    workspace_model_state_before_roi = (
        {
            name: workspace_model.GetAttribute(name)
            for name in (
                "DENTOBOT.WorkspaceRuntimeValidated",
                "DENTOBOT.WorkspaceState",
            )
        }
        if workspace_model is not None
        else None
    )
    roi_loaded = not bool(getattr(panel, "_taskSpaceRoiInitialized", False))
    if roi_loaded:
        roi_button = panel.useCurrentIncisorMidpointButton
        roi_button_frame = _scroll_to_visible(
            widget, roi_button, "Use current incisor midpoint"
        )
        if not roi_button.enabled or not _visible(roi_button):
            stop("Production Use current incisor midpoint control is not visible and enabled.")
        roi_button.click()
        _process_events(0.1)
        if not getattr(panel, "_taskSpaceRoiInitialized", False):
            stop("Production Use current incisor midpoint did not initialize the ROI draft.")
        roi_action = "loaded_from_current_incisor_midpoint"
    else:
        roi_button_frame = None
        roi_action = "reused_current_local_draft"
    try:
        roi_center = tuple(float(spin.value) for spin in panel.taskSpaceRoiCenterSpinBoxes)
        roi_dimensions = tuple(
            float(spin.value) for spin in panel.taskSpaceRoiDimensionsSpinBoxes
        )
        roi_opening_revision = panel._taskSpaceRoiOpeningRevision
        roi_gap_line_id = panel._taskSpaceRoiGapLineNodeId
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        stop(f"The displayed Task Space ROI draft is incomplete: {exc}")
    if (
        len(roi_center) != 3
        or len(roi_dimensions) != 3
        or not all(math.isfinite(value) for value in roi_center + roi_dimensions)
        or not all(value > 0.0 for value in roi_dimensions)
        or type(roi_opening_revision) is not int
        or roi_opening_revision < 0
        or not isinstance(roi_gap_line_id, str)
        or not roi_gap_line_id.strip()
    ):
        stop("The displayed Task Space ROI draft or its opening source identity is invalid.")
    displayed_roi = TaskSpaceRoi(
        center_world_ras_mm=roi_center,
        dimensions_mm=roi_dimensions,
    )
    displayed_roi_source = {
        "openingRevision": roi_opening_revision,
        "gapLineNodeId": roi_gap_line_id,
    }
    roi_matches_saved_evidence = bool(
        facade.workspaceRoiMatchesSavedEvidence(
            displayed_roi, displayed_roi_source, parameter_node
        )
    )
    workspace_model_state_after_roi = (
        {
            name: workspace_model.GetAttribute(name)
            for name in (
                "DENTOBOT.WorkspaceRuntimeValidated",
                "DENTOBOT.WorkspaceState",
            )
        }
        if workspace_model is not None
        else None
    )
    if roi_loaded and saved_workspace_json_before_roi and roi_matches_saved_evidence:
        if (
            str(parameter_node.step6AssistedLimitProposalJson or "")
            != saved_workspace_json_before_roi
            or str(getattr(facade, "_runtime_validated_workspace_key", "") or "")
            != runtime_workspace_key_before_roi
            or workspace_model_state_after_roi != workspace_model_state_before_roi
            or "Exact saved workspace ROI/source match"
            not in str(panel.taskSpaceRoiStatusLabel.text)
        ):
            stop(
                "Loading the exact saved incisor ROI changed or mislabeled workspace evidence."
            )
    roi_frame = _scroll_to_visible(
        widget, panel.taskSpaceRoiStatusLabel, "Task Space ROI draft evidence"
    )
    evidence["task_space_roi_draft"] = {
        "action": roi_action,
        "loaded_from_current_incisor_midpoint": roi_loaded,
        "reused_existing_local_draft": not roi_loaded,
        "center_world_ras_mm": roi_center,
        "dimensions_mm": roi_dimensions,
        "opening_revision": roi_opening_revision,
        "gap_line_node_id": roi_gap_line_id,
        "status_text": str(panel.taskSpaceRoiStatusLabel.text),
        "matches_saved_evidence": roi_matches_saved_evidence,
        "saved_evidence_preserved": bool(
            not (roi_loaded and saved_workspace_json_before_roi and roi_matches_saved_evidence)
            or (
                str(parameter_node.step6AssistedLimitProposalJson or "")
                == saved_workspace_json_before_roi
                and str(getattr(facade, "_runtime_validated_workspace_key", "") or "")
                == runtime_workspace_key_before_roi
                and workspace_model_state_after_roi == workspace_model_state_before_roi
            )
        ),
    }
    evidence["task_space_roi_screenshot_framing"] = {
        "midpoint_control": roi_button_frame,
        "draft_status": roi_frame,
    }
    _write_report(report)
    evidence["screenshots"]["task_space_roi_draft_before_generation"] = _capture(
        report, evidence_dir, run_id, f"{phase}-task-space-roi-before-workspace"
    )
    _write_report(report)
    _show_step63_view(panel, 1, 0)
    if not widget.ui.generateRobotWorkspaceButton.enabled:
        stop("Production Generate Robot Workspace control is disabled after Task Home validation.")
    evidence["last_completed_boundary"] = "before_workspace_generation_click"
    _write_report(report)
    try:
        _modal_guarded_click(
            report, evidence_dir, run_id, widget.ui.generateRobotWorkspaceButton,
            f"{phase}-workspace-generation",
        )
    except UnexpectedModalError as exc:
        evidence["workspace_modal_text"] = exc.dialog_text
        stop(f"Workspace generation raised a modal: {exc.dialog_text}")
    _process_events(0.1)
    if facade.workspaceRuntimeValidated(parameter_node) is not True:
        stop("Production workspace generation did not produce current runtime validation.")
    evidence["workspace_runtime_validated"] = True
    evidence["last_completed_boundary"] = "workspace_generation_returned_current"
    _write_report(report)
    evidence["screenshots"]["workspace_generated"] = _capture(
        report, evidence_dir, run_id, f"{phase}-workspace-generated"
    )
    evidence["display_models_after_workspace"] = _step6_display_models_state()
    try:
        evidence["screenshots"]["workspace_generated_anterior"] = _capture_anterior_view(
            report, evidence_dir, run_id, f"{phase}-workspace-generated-anterior"
        )
    except Exception as exc:  # evidence aid only
        evidence["anterior_view_error"] = str(exc)
    _write_report(report)
    if _exact_env_opt_in("DENTOBOT_HEADED_STOP_AFTER_WORKSPACE"):
        evidence.update({
            "status": "PASS",
            "diagnostic_stop": "workspace_generation_returned_current",
            "planner_preview_authority": False,
        })
        _record(
            report,
            check_name,
            "PASS",
            **{key: value for key, value in evidence.items() if key != "status"},
        )
        _finalize_workspace_diagnostic(report)
        print("DENTOBOT_HEADED_WORKSPACE_DIAGNOSTIC_PASS", flush=True)
        slicer.util.exit(0)
        raise SystemExit(0)

    _show_step63_view(panel, 1, 1)
    if not panel.reviewLimitsButton.enabled:
        stop("Production Review and Apply Suggested Limits control is disabled.")
    evidence["last_completed_boundary"] = "before_assisted_limit_review_click"
    _write_report(report)
    panel.reviewLimitsButton.click()
    _process_events(0.1)
    if (
        logic.assistedTaskLimitsReviewed(parameter_node) is not True
        or facade.workspaceRuntimeValidated(parameter_node) is not True
    ):
        stop("Assisted limits were not explicitly reviewed against the current workspace.")
    evidence["assisted_limits_reviewed"] = True
    evidence["last_completed_boundary"] = "assisted_limit_review_returned_current"
    _write_report(report)
    evidence["screenshots"]["limits_reviewed"] = _capture(
        report, evidence_dir, run_id, f"{phase}-limits-reviewed"
    )

    widget._updateStep6PlanningUi()
    _show_step63_view(panel, 2, 0)
    if not panel.confirmTaskButton.enabled:
        stop("Production Confirm Immutable Task control is disabled after current review.")
    panel.confirmTaskButton.click()
    _process_events(0.1)
    evidence["screenshots"]["task_confirmed"] = _capture(
        report, evidence_dir, run_id, f"{phase}-task-confirmed"
    )
    confirmed_after = logic.confirmedTaskRecord(parameter_node)
    task_issues_after = tuple(logic.confirmedTaskFreshnessIssues(parameter_node))
    authority_after = {
        "route_authority": report["route_authority"],
        "planner_calls": report["planner_calls"],
        "preview_started": report["preview_started"],
        "preview_active": bool(facade.previewActive),
        "return_home_required": bool(facade.returnHomeRequired),
    }
    case_hash_after = _sha256_file(case_path)
    evidence["post_confirmation_invariants"] = {
        "confirmed_task_present": confirmed_after is not None,
        "confirmed_task_freshness_issues": task_issues_after,
        "assisted_limits_reviewed": bool(
            logic.assistedTaskLimitsReviewed(parameter_node)
        ),
        "task_home_runtime_validated": bool(
            facade.taskHomeRuntimeValidated(parameter_node)
        ),
        "workspace_runtime_validated": bool(
            facade.workspaceRuntimeValidated(parameter_node)
        ),
        "route_preview_unchanged": authority_after == authority_before,
        "source_case_unchanged": case_hash_after == case_hash,
    }
    _write_report(report)
    if (
        confirmed_after is None
        or task_issues_after
        or not logic.assistedTaskLimitsReviewed(parameter_node)
        or not facade.taskHomeRuntimeValidated(parameter_node)
        or not facade.workspaceRuntimeValidated(parameter_node)
        or authority_after != authority_before
        or case_hash_after != case_hash
    ):
        stop("Current confirmed prerequisites, unchanged source SHA, or no-route/no-preview authority failed.")
    evidence.update({
        "status": "PASS",
        "confirmed_task": confirmed_after.to_dict(),
        "confirmed_task_freshness_issues": task_issues_after,
        "case_sha256_after": case_hash_after,
        "source_case_unchanged": True,
        "route_preview_after": authority_after,
        "planner_preview_authority": False,
    })
    _record(
        report, check_name, "PASS",
        **{key: value for key, value in evidence.items() if key != "status"},
    )


def _manual_jog_fixture_identity(logic, parameter_node):
    snapshot = logic.confirmedTaskRecord(parameter_node)
    home = logic.taskHomeRecord(parameter_node)
    if snapshot is None or home is None:
        raise RuntimeError("A current confirmed task and saved Task Home are required.")
    registry = json.loads(str(parameter_node.step6TrajectoryRegistryJson or "{}"))
    branch_id = str(registry.get("selected_branch_id") or "")
    if not branch_id:
        raise RuntimeError("A selected PreparedBranch is required.")
    home_names = tuple(str(name) for name in home.joint_names)
    home_values = tuple(float(value) for value in home.joint_positions_si)
    if len(home_names) != len(home_values) or set(home_names) != set(JOINT_NAMES):
        raise RuntimeError("Saved Task Home does not contain exactly J1–J5.")
    home_positions = _finite_vector(dict(zip(home_names, home_values)))
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
    scene = _scene_evidence(logic, parameter_node)
    audit = logic.collisionSceneAuditRecord(parameter_node)
    if audit is None:
        raise RuntimeError("The current case collision-scene audit is unavailable.")
    return _fixture_identity(
        branch_id=branch_id,
        task_core=task_core,
        home_revision=home.revision,
        home_joint_positions_si=home_positions,
        scene_source_object_ids=scene["source_object_ids"],
        scene_base_fingerprint=str(audit.base_fingerprint),
        fingerprint_fn=fingerprint,
    )


def _prepare_case_bound_rejection(
    raw_plan, case_sha256, fixture_identity, logic, parameter_node, panel, accepted_target,
):
    plan, reason = _rejection_plan(
        raw_plan,
        case_sha256=case_sha256,
        fixture_identity_value=fixture_identity,
        finite_vector=_finite_vector,
    )
    if plan is None:
        raise RuntimeError("An exact rejection plan is required: " + reason)
    if not _exactly_matches(plan["starting_positions_si"], accepted_target):
        raise RuntimeError(
            "Pre-reviewed rejection vector is not bound to the exact post-acceptance starting state."
        )
    if not plan["review_reference"]:
        raise RuntimeError("Rejection plan requires a non-empty review_reference.")
    target = plan["requested_positions_si"]
    limits = _within_both_limits(logic, parameter_node, target)
    if limits is None:
        raise RuntimeError("Pre-reviewed rejection vector is outside current reviewed or mechanical limits.")
    if _exactly_matches(target, plan["starting_positions_si"]):
        raise RuntimeError("Pre-reviewed rejection vector must differ from its bound starting state.")
    panel._setManualJogDraftValues(_display_values(target), notify=True)
    visible_target = _finite_vector(panel.manualJogJointPositionsSi())
    panel._setManualJogDraftValues(_display_values(accepted_target), notify=True)
    restored_target = _finite_vector(panel.manualJogJointPositionsSi())
    if not _exactly_matches(visible_target, target):
        raise RuntimeError("Visible numeric controls cannot preserve the exact reviewed rejection vector.")
    if not _exactly_matches(restored_target, accepted_target):
        raise RuntimeError("Could not restore the accepted draft after rejection-plan preflight.")
    return plan, limits


def _run_case_bound_rejection(
    widget, panel, logic, parameter_node, facade, case_sha256, fixture_identity,
    scene, plan, limits, report, evidence_dir, run_id,
):
    target = plan["requested_positions_si"]
    if _manual_jog_fixture_identity(logic, parameter_node) != fixture_identity:
        raise RuntimeError("Case fixture identity changed after rejection-plan preflight.")
    current_limits = _within_both_limits(logic, parameter_node, target)
    if current_limits is None:
        raise RuntimeError("Pre-reviewed rejection vector no longer fits current limits.")
    limits = current_limits
    if scene["source_object_ids"] != scene["acknowledged_object_ids"]:
        raise RuntimeError("Case collision objects are not fully acknowledged before rejection review.")

    panel._setManualJogDraftValues(_display_values(target), notify=True)
    visible_target = _finite_vector(panel.manualJogJointPositionsSi())
    if not _exactly_matches(visible_target, target):
        raise RuntimeError("Visible numeric controls cannot preserve the exact reviewed rejection vector.")
    if not panel.guardedManualJogButton.enabled:
        raise RuntimeError("Production Guarded Jog is disabled before the rejected request.")
    before = _actual_joint_state(facade)
    if not all(_exactly_matches(before[key], plan["starting_positions_si"])
               for key in ("accepted_si", "monitored_si", "displayed_si")):
        raise RuntimeError("Accepted, monitored, and displayed state differ from the reviewed rejection start.")
    identity_before = facade._manual_jog_current_identity(parameter_node)
    ui = _guard_click(widget, panel, target)
    report["jog_requests"] += 1
    after = _actual_joint_state(facade)
    identity_after = facade._manual_jog_current_identity(parameter_node)
    evidence = dict(ui.get("evidence") or {})
    native = evidence.get("nativeGuardEvidence") or {}
    rejected_frame = _scroll_to_visible(widget, panel.manualJogGroup, "native rejected manual jog")
    screenshot = _capture(report, evidence_dir, run_id, "case-bound-rejected-jog")
    passed = bool(
        evidence.get("manualJogStatus") == "rejected"
        and evidence.get("guardAccepted") is False
        and evidence.get("rawGuardOutcome") == "rejected"
        and evidence.get("identityStatus") == "current"
        and native.get("responseObserved") is True
        and native.get("responseCorrelated") is True
        and bool(native.get("requestId"))
        and native.get("requestId") == evidence.get("requestId")
        and bool(native.get("sessionId"))
        and native.get("sessionId") == evidence.get("sessionId")
        and native.get("policyId") == bridge.ROS2_MANUAL_JOINT_POLICY_ID
        and native.get("collisionScenePolicyIdentityStatus") == "manual_policy_id_correlated"
        and native.get("accepted") is False
        and native.get("bridgeReturnedAccepted") is False
        and bool(native.get("reason"))
        and native.get("worldObjectEvidencePresent") is True
        and native.get("worldObjectCount") == len(scene["source_object_ids"])
        and sorted(str(value) for value in native.get("worldObjectIds") or ())
        == scene["acknowledged_object_ids"]
        and _exactly_matches(native.get("requestedPositionsSi"), target)
        and _exactly_matches(native.get("acceptedPositionsSi"), before["accepted_si"])
        and _exactly_matches(ui.get("draft_positions_si"), target)
        and _exactly_matches(panel.manualJogJointPositionsSi(), target)
        and _exactly_matches(ui.get("panel_accepted_positions_si"), before["accepted_si"])
        and all(_exactly_matches(after[key], before[key])
                for key in ("accepted_si", "monitored_si", "displayed_si"))
        and identity_before == identity_after
    )
    details = {
        "case_sha256": case_sha256,
        "fixture_identity": fixture_identity,
        "review_reference": plan["review_reference"],
        "starting_positions_si": plan["starting_positions_si"],
        "requested_positions_si": target,
        "limit_evidence": limits,
        "native_guard_evidence": native,
        "ui_result": ui,
        "identity_before": identity_before,
        "identity_after": identity_after,
        "accepted_monitored_displayed_before": before,
        "accepted_monitored_displayed_after": after,
        "accepted_monitored_displayed_unchanged": passed,
        "draft_retained": _exactly_matches(panel.manualJogJointPositionsSi(), target),
        "screenshot": screenshot,
        "screenshot_framing": rejected_frame,
        "route_authority": report["route_authority"],
        "planner_calls": report["planner_calls"],
        "preview_started": report["preview_started"],
    }
    report.setdefault("outcome_scenarios", {})["rejected"] = {
        "status": "PASS" if passed else "FAIL",
        **details,
    }
    if not passed:
        _record(report, "case_bound_rejected_guard", "FAIL",
                reason="The case-bound request did not produce correlated native rejection evidence with retained draft and unchanged state.",
                **details)
        raise RuntimeError("Case-bound native rejection evidence failed its acceptance gate.")
    _record(report, "case_bound_rejected_guard", "PASS", **details)


def _run_unknown_reconciliation(
    widget, panel, logic, parameter_node, facade, scene, report, evidence_dir, run_id,
):
    before = _actual_joint_state(facade)
    if not all(before.get(key) for key in ("accepted_si", "monitored_si", "displayed_si")):
        raise RuntimeError("Accepted, monitored, or displayed state is unavailable before unknown-jog injection.")
    identity_before = facade._manual_jog_current_identity(parameter_node)
    target, direction = _target_j1(logic, parameter_node, before["accepted_si"])
    panel._setManualJogDraftValues(_display_values(target), notify=True)
    target = _finite_vector(panel.manualJogJointPositionsSi())
    if _within_both_limits(logic, parameter_node, target) is None:
        raise RuntimeError("Unknown-result J1 request is outside current reviewed or mechanical limits.")
    if not panel.guardedManualJogButton.enabled:
        raise RuntimeError("Production Guarded Jog is disabled before unknown-result injection.")

    bridge_owner = facade._bridge
    original_apply = getattr(bridge_owner, "apply_manual_joint_positions_si", None)
    if not callable(original_apply):
        raise RuntimeError("The correlated manual-jog bridge function is unavailable.")
    wrapper_calls = []

    def stale_acknowledgement(*args, **kwargs):
        if wrapper_calls:
            raise RuntimeError("Runner refuses a second native manual-jog request.")
        call = {
            "requested_positions_si": _finite_vector(args[0] if args else kwargs.get("positions_si")),
            "request_id": args[1] if len(args) > 1 else kwargs.get("request_id"),
            "session_id": args[2] if len(args) > 2 else kwargs.get("session_id"),
        }
        wrapper_calls.append(call)
        result = original_apply(*args, **kwargs)
        if not isinstance(result, (tuple, list)) or len(result) != 3 or result[2] is None:
            call["status_correlation_altered"] = False
            return result
        accepted, message, status = result
        mismatched = dataclasses.replace(
            status,
            request_id=f"runner-stale-{status.request_id}",
            session_id=f"runner-stale-{status.session_id}",
        )
        call.update(
            status_correlation_altered=True,
            original_status_request_id=status.request_id,
            original_status_session_id=status.session_id,
            returned_status_request_id=mismatched.request_id,
            returned_status_session_id=mismatched.session_id,
            underlying_apply_accepted=accepted,
            underlying_native_accepted=status.accepted,
        )
        return accepted, message, mismatched

    setattr(bridge_owner, "apply_manual_joint_positions_si", stale_acknowledgement)
    try:
        ui = _guard_click(widget, panel, target)
    finally:
        setattr(bridge_owner, "apply_manual_joint_positions_si", original_apply)
    wrapper_restored = getattr(bridge_owner, "apply_manual_joint_positions_si", None) is original_apply
    report["jog_requests"] += len(wrapper_calls)
    after_unknown = _actual_joint_state(facade)
    identity_after_unknown = facade._manual_jog_current_identity(parameter_node)
    unknown_evidence = dict(ui.get("evidence") or {})
    unknown_native = unknown_evidence.get("nativeGuardEvidence") or {}
    unknown_frame = _scroll_to_visible(widget, panel.manualJogGroup, "unknown manual-jog acknowledgement")
    unknown_screenshot = _capture(report, evidence_dir, run_id, "unknown-reconciliation-required")
    unknown_latched = bool(
        unknown_evidence.get("manualJogStatus") == "unknown"
        and unknown_evidence.get("guardAccepted") is None
        and unknown_evidence.get("manualJogReconciliationRequired") is True
        and panel.manualJogReconciliationRequired is True
        and panel.manualJogStatusLabel.property("dentobotState") == "blocked"
        and panel.guardedManualJogButton.enabled is False
        and unknown_native.get("responseObserved") is True
        and unknown_native.get("responseCorrelated") is False
        and bool(wrapper_calls)
        and len(wrapper_calls) == 1
        and wrapper_calls[0].get("status_correlation_altered") is True
        and wrapper_calls[0].get("requested_positions_si") == target
        and unknown_native.get("requestId")
        == wrapper_calls[0].get("returned_status_request_id")
        and unknown_native.get("sessionId")
        == wrapper_calls[0].get("returned_status_session_id")
        and unknown_native.get("requestId") != unknown_evidence.get("requestId")
        and unknown_native.get("sessionId") != unknown_evidence.get("sessionId")
        and wrapper_calls[0].get("underlying_apply_accepted") is True
        and wrapper_calls[0].get("underlying_native_accepted") is True
        and unknown_evidence.get("acceptedStateMayHaveAdvanced") is True
        and _exactly_matches(unknown_native.get("requestedPositionsSi"), target)
        and _exactly_matches(unknown_native.get("acceptedPositionsSi"), target)
        and _exactly_matches(after_unknown.get("accepted_si"), target)
        and _exactly_matches(unknown_evidence.get("requestedJointPositionsSi"), target)
        and _exactly_matches(ui.get("draft_positions_si"), target)
        and _exactly_matches(ui.get("panel_accepted_positions_si"), before["accepted_si"])
        and wrapper_restored
        and identity_before == identity_after_unknown
    )
    report.setdefault("outcome_scenarios", {})["unknown"] = {
        "status": "LATCHED" if unknown_latched else "FAIL",
        "requested_positions_si": target,
        "direction": direction,
        "wrapper_calls": wrapper_calls,
        "wrapper_restored": wrapper_restored,
        "native_guard_evidence": unknown_native,
        "ui_result": ui,
        "identity_before": identity_before,
        "identity_after_unknown": identity_after_unknown,
        "state_before": before,
        "state_after_unknown": after_unknown,
        "screenshot": unknown_screenshot,
        "screenshot_framing": unknown_frame,
        "repeat_jog_blocked": not panel.guardedManualJogButton.enabled,
        "route_authority": report["route_authority"],
        "planner_calls": report["planner_calls"],
        "preview_started": report["preview_started"],
    }
    _write_report(report)
    if not unknown_latched:
        failure_details = {
            key: value for key, value in report["outcome_scenarios"]["unknown"].items()
            if key != "status"
        }
        _record(report, "unknown_reconcile_state", "FAIL",
                reason="The controlled mismatched acknowledgement did not preserve a blocked unknown state.",
                **failure_details)
        raise RuntimeError("Controlled unknown jog failed to latch for reconciliation.")
    if not panel.reconcileManualJogButton.enabled:
        raise RuntimeError("Production Reconcile State is not enabled for the unknown jog.")

    panel.reconcileManualJogButton.click()
    _process_events(0.2)
    reconciliation = dict(panel._manualJogEvidence or {})
    query_evidence = reconciliation.get("nativeGuardEvidence") or {}
    state_after = _actual_joint_state(facade)
    current_identity = facade._manual_jog_current_identity(parameter_node)
    native_accepted = reconciliation.get("acceptedJointPositionsSi")
    monitored = reconciliation.get("monitoredJointPositionsSi")
    identity_matched = bool(
        reconciliation.get("identityStatus") == "current"
        and reconciliation.get("identityBefore") == identity_before
        and reconciliation.get("identityAfter") == identity_before
        and current_identity == identity_before
    )
    state_matched = bool(
        isinstance(native_accepted, Mapping)
        and isinstance(monitored, Mapping)
        and _exactly_matches(state_after["accepted_si"], native_accepted)
        and _exactly_matches(state_after["monitored_si"], monitored)
        and _representationally_matches(state_after["monitored_si"], native_accepted)
        and _representationally_matches(state_after["displayed_si"], native_accepted)
        and _exactly_matches(panel._manualJogAcceptedJointPositionsSi, native_accepted)
    )
    reconciled = bool(
        reconciliation.get("manualJogStatus") == "reconciled"
        and reconciliation.get("manualJogReconciliationRequired") is False
        and panel.manualJogReconciliationRequired is False
        and panel.manualJogStatusLabel.property("dentobotState") == "ok"
        and not panel.reconcileManualJogButton.enabled
        and query_evidence.get("responseCorrelated") is True
        and query_evidence.get("responseObserved") is True
        and query_evidence.get("operation") == "state_query"
        and query_evidence.get("queryOnly") is True
        and query_evidence.get("policyId") == bridge.ROS2_MANUAL_JOINT_POLICY_ID
        and query_evidence.get("requestId") == reconciliation.get("queryRequestId")
        and query_evidence.get("sessionId") == reconciliation.get("sessionId")
        and _exactly_matches(query_evidence.get("requestedPositionsSi"), target)
        and _exactly_matches(query_evidence.get("acceptedPositionsSi"), native_accepted)
        and query_evidence.get("worldObjectEvidencePresent") is True
        and query_evidence.get("worldObjectCount") == len(scene["source_object_ids"])
        and sorted(str(value) for value in query_evidence.get("worldObjectIds") or ())
        == scene["acknowledged_object_ids"]
        and identity_matched
        and state_matched
    )
    reconcile_frame = _scroll_to_visible(widget, panel.manualJogGroup, "reconciled manual-jog state")
    reconcile_screenshot = _capture(report, evidence_dir, run_id, "unknown-state-reconciled")
    details = {
        **report["outcome_scenarios"]["unknown"],
        "status": "PASS" if reconciled else "FAIL",
        "reconciliation_evidence": reconciliation,
        "query_native_evidence": query_evidence,
        "current_identity_after_reconciliation": current_identity,
        "identity_matched_exactly": identity_matched,
        "state_after_reconciliation": state_after,
        "accepted_monitored_displayed_converged": state_matched,
        "reconciliation_screenshot": reconcile_screenshot,
        "reconciliation_screenshot_framing": reconcile_frame,
        "reconciliation_button_invoked": True,
        "route_authority_after": report["route_authority"],
        "planner_calls_after": report["planner_calls"],
        "preview_started_after": report["preview_started"],
    }
    report["outcome_scenarios"]["unknown"] = details
    _write_report(report)
    if not reconciled:
        failure_details = {key: value for key, value in details.items() if key != "status"}
        _record(report, "unknown_reconcile_state", "FAIL",
                reason="Production Reconcile State did not prove exact current identity and accepted/monitored/displayed convergence.",
                **failure_details)
        raise RuntimeError("Production Reconcile State failed its exact identity/state gate.")
    _record(
        report,
        "unknown_reconcile_state",
        "PASS",
        **{key: value for key, value in details.items() if key != "status"},
    )


def run() -> int:
    workspace_diagnostic = _validate_workspace_diagnostic_opt_in()
    output_text = os.environ.get("DENTOBOT_HEADED_EVIDENCE_DIR", "").strip()
    if not output_text:
        raise RuntimeError("Set DENTOBOT_HEADED_EVIDENCE_DIR to a private evidence directory.")
    allow_base_home_accept = os.environ.get("DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT", "") == "1"
    os.umask(0o077)
    evidence_dir = Path(output_text).expanduser()
    evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    evidence_dir = evidence_dir.resolve()
    evidence_dir.chmod(0o700)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = evidence_dir / f"step6_headed_review_{run_id}.json"
    try:
        fd = os.open(str(report_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError as exc:
        raise RuntimeError(f"Refusing to overwrite existing evidence: {report_path}") from exc

    report: dict[str, object] = {
        "schema_version": "1.0",
        "gate": "S6-LIVE-01 bounded headed Step 6 review",
        "started_at_utc": _utc_now(),
        "status": "RUNNING",
        "operator_verdict": None,
        "full_workflow_claimed": False,
        "report_path": str(report_path),
        "evidence_directory": str(evidence_dir),
        "case_source": None,
        "case_sha256_before_open": None,
        "case_sha256_after_open": None,
        "saved_case": False,
        "offline_saved_case": None,
        "simulation_only": True,
        "hardware_execution": False,
        "planner_calls": 0,
        "preview_started": False,
        "route_authority": "none",
        "review_mode": None,
        "taskless_draft_only": False,
        "manual_jog_keyboard_draft_only": False,
        "historical_record_reopen_opt_in": False,
        "base_home_uncertainty_opt_in": False,
        "complete_cycles_opt_in": False,
        "offline_home_setup_opt_in": False,
        "scenario_opt_ins": {
            "rejected_guard": False,
            "unknown_reconciliation": False,
            "joint_keyboard_draft": False,
            "base_home_uncertainty": False,
            "complete_cycles": False,
            "offline_home_setup": False,
            "workspace_diagnostic": False,
        },
        "outcome_scenarios": {
            "rejected": {"status": "NOT_RUN"},
            "unknown": {"status": "NOT_RUN"},
        },
        "manual_jog_fixture_identity": None,
        "jog_requests": 0,
        "base_acceptance_attempted": False,
        "task_home_acceptance_attempted": False,
        "base_home_accept_opt_in": allow_base_home_accept,
        "screenshots": {},
        "items": {
            name: {"status": "NOT_RUN", "reason": "Not reached."}
            for name in CHECK_NAMES
        },
    }
    output_case_text = os.environ.get("DENTOBOT_HEADED_OUTPUT_CASE")
    output_case_path = None
    if output_case_text is None:
        report["items"]["save_current_case"] = {
            "status": "NOT_RUN",
            "reason": "DENTOBOT_HEADED_OUTPUT_CASE is unset.",
        }
    _write_report(report)
    active_check = "checkout_and_case_provenance"
    outcome = "FAILED"
    message = ""
    allow_rejected_guard = False
    allow_unknown_reconciliation = False
    offline_home_setup_opt_in = False
    offline_home_output_text = os.environ.get(
        "DENTOBOT_HEADED_OFFLINE_HOME_CASE_OUTPUT"
    )
    offline_home_output_path = None
    manual_jog_fixture_identity = None
    rejection_plan = None
    rejection_limits = None

    def complete_not_run(names, reason):
        for item in names:
            if report["items"][item]["status"] == "NOT_RUN":
                _record(report, item, "NOT_RUN", reason=reason)

    def fail(name, reason, **details):
        nonlocal active_check
        active_check = name
        _record(report, name, "FAIL", reason=reason, **details)
        raise RuntimeError(reason)

    try:
        connect_only = _connect_only_requested()
        report["checkout"] = _checkout_evidence()
        report["connect_only"] = connect_only
        active_check = "offline_base_home_configuration"
        try:
            offline_home_setup_opt_in = _exact_env_opt_in(
                "DENTOBOT_HEADED_OFFLINE_HOME_SETUP"
            )
        except RuntimeError as exc:
            fail(active_check, str(exc))
        report["offline_home_setup_opt_in"] = offline_home_setup_opt_in
        report["scenario_opt_ins"]["offline_home_setup"] = offline_home_setup_opt_in
        if offline_home_setup_opt_in:
            try:
                allow_base_home_accept = _exact_env_opt_in(
                    "DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT"
                )
            except RuntimeError as exc:
                fail(active_check, str(exc))
            if not allow_base_home_accept:
                fail(
                    active_check,
                    "DENTOBOT_HEADED_OFFLINE_HOME_SETUP=1 requires "
                    "DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT=1.",
                )
            if not str(offline_home_output_text or "").strip():
                fail(
                    active_check,
                    "DENTOBOT_HEADED_OFFLINE_HOME_SETUP=1 requires a unique "
                    "DENTOBOT_HEADED_OFFLINE_HOME_CASE_OUTPUT .dentocase path.",
                )
        elif offline_home_output_text is not None:
            fail(
                active_check,
                "DENTOBOT_HEADED_OFFLINE_HOME_CASE_OUTPUT requires "
                "DENTOBOT_HEADED_OFFLINE_HOME_SETUP=1.",
            )
        active_check = "checkout_and_case_provenance"
        draft_only = _draft_only_requested()
        invalid_draft_review = _invalid_draft_review_requested()
        record_reopen = _historical_record_reopen_requested()
        joint_keyboard_opt_in = _exact_env_opt_in("DENTOBOT_HEADED_JOINT_KEYBOARD")
        tcp_case_opt_in = _exact_env_opt_in("DENTOBOT_HEADED_TCP_CASE")
        full_chain_opt_in = _exact_env_opt_in("DENTOBOT_HEADED_FULL_CHAIN")
        try:
            base_offset = _parse_base_offset(os.environ.get(BASE_OFFSET_ENV))
            _validate_base_offset_opt_in(
                base_offset,
                full_chain=full_chain_opt_in,
                allow_jog=os.environ.get("DENTOBOT_HEADED_ALLOW_JOG", "") == "1",
                allow_base_home_accept=allow_base_home_accept,
            )
        except RuntimeError as exc:
            fail("base_acceptance_trial", str(exc))
        report["base_offset_requested_ras_mm"] = list(base_offset) if base_offset else None
        report["base_offset_applied"] = False
        try:
            base_home_uncertainty_opt_in = _exact_env_opt_in(
                "DENTOBOT_HEADED_BASE_HOME_UNCERTAINTY"
            )
        except RuntimeError as exc:
            fail("base_home_uncertainty", str(exc))
        try:
            complete_cycles_opt_in = _exact_env_opt_in(
                "DENTOBOT_HEADED_COMPLETE_CYCLES"
            )
        except RuntimeError as exc:
            fail("complete_cycles", str(exc))
        allow_rejected_guard = _exact_env_opt_in("DENTOBOT_HEADED_ALLOW_REJECTED_JOG")
        allow_unknown_reconciliation = _exact_env_opt_in(
            "DENTOBOT_HEADED_ALLOW_UNKNOWN_RECONCILIATION"
        )
        allow_jog_requested = os.environ.get("DENTOBOT_HEADED_ALLOW_JOG", "") == "1"
        report["base_home_uncertainty_opt_in"] = base_home_uncertainty_opt_in
        report["complete_cycles_opt_in"] = complete_cycles_opt_in
        try:
            _validate_step6_live_probe_opt_ins(
                base_home_uncertainty=base_home_uncertainty_opt_in,
                complete_cycles=complete_cycles_opt_in,
                full_chain=full_chain_opt_in,
                allow_jog=allow_jog_requested,
                allow_base_home_accept=allow_base_home_accept,
                workspace_diagnostic=workspace_diagnostic,
                draft_only=draft_only,
            )
        except RuntimeError as exc:
            failing_item = (
                "complete_cycles" if complete_cycles_opt_in
                else "base_home_uncertainty" if base_home_uncertainty_opt_in
                else "full_chain_interruption"
            )
            fail(failing_item, str(exc))
        joint_keyboard_only = joint_keyboard_opt_in and not (
            allow_jog_requested or draft_only or invalid_draft_review
        )
        report["scenario_opt_ins"] = {
            "rejected_guard": allow_rejected_guard,
            "unknown_reconciliation": allow_unknown_reconciliation,
            "allow_jog": allow_jog_requested,
            "joint_keyboard_draft": joint_keyboard_opt_in,
            "case_bound_tcp": tcp_case_opt_in,
            "full_chain_interruption": full_chain_opt_in,
            "base_home_uncertainty": base_home_uncertainty_opt_in,
            "complete_cycles": complete_cycles_opt_in,
            "offline_home_setup": offline_home_setup_opt_in,
            "workspace_diagnostic": workspace_diagnostic,
        }
        if (tcp_case_opt_in or full_chain_opt_in) and not (
            allow_jog_requested and allow_base_home_accept
        ):
            fail(
                "case_bound_tcp_workbench" if tcp_case_opt_in else "full_chain_interruption",
                "Case-bound 6.3 probes require the current guarded-jog and Base/Home acceptance gates.",
            )
        report["manual_jog_keyboard_draft_only"] = joint_keyboard_only
        if not joint_keyboard_opt_in:
            report["items"]["manual_jog_keyboard_draft_check"] = {
                "status": "NOT_RUN",
                "reason": "DENTOBOT_HEADED_JOINT_KEYBOARD is unset or '0'.",
            }
        if allow_rejected_guard and not allow_jog_requested:
            fail(
                "case_bound_rejected_guard",
                "DENTOBOT_HEADED_ALLOW_REJECTED_JOG=1 requires DENTOBOT_HEADED_ALLOW_JOG=1.",
            )
        if allow_unknown_reconciliation and not allow_jog_requested:
            fail(
                "unknown_reconcile_state",
                "DENTOBOT_HEADED_ALLOW_UNKNOWN_RECONCILIATION=1 requires DENTOBOT_HEADED_ALLOW_JOG=1.",
            )
        rejection_plan_json = os.environ.get("DENTOBOT_MANUAL_JOG_REJECTION_PLAN_JSON", "")
        if allow_rejected_guard and not rejection_plan_json.strip():
            fail(
                "case_bound_rejected_guard",
                "DENTOBOT_HEADED_ALLOW_REJECTED_JOG=1 requires DENTOBOT_MANUAL_JOG_REJECTION_PLAN_JSON.",
            )
        _validate_record_reopen_prerequisites(
            record_reopen, allow_jog_requested, draft_only
        )
        report["review_mode"] = (
            "workspace_diagnostic" if workspace_diagnostic
            else "manual_jog_keyboard_draft_only" if joint_keyboard_only
            else "taskless_draft_only" if draft_only
            else "invalid_draft_review" if invalid_draft_review
            else "bounded_jog_base_home_review"
        )
        report["taskless_draft_only"] = draft_only
        report["invalid_draft_review_opt_in"] = invalid_draft_review
        report["historical_record_reopen_opt_in"] = record_reopen
        if not record_reopen:
            _record(
                report,
                "historical_record_export_reopen",
                "NOT_RUN",
                reason="DENTOBOT_HEADED_RECORD_REOPEN is unset or '0'.",
            )
        _write_report(report)
        case_text = os.environ.get("DENTOBOT_HEADED_CASE_SOURCE", "").strip()
        if not case_text:
            fail(active_check, "Set DENTOBOT_HEADED_CASE_SOURCE to the exact reviewed .dentocase.")
        case_path = Path(case_text).expanduser().resolve()
        if not case_path.is_file():
            fail(active_check, f"Saved case does not exist: {case_path}")
        if output_case_text is not None:
            try:
                output_case_path = _validate_output_case_path(
                    output_case_text, case_path
                )
            except Exception as exc:
                fail(
                    "save_current_case",
                    f"{type(exc).__name__}: {exc}",
                    output_path=output_case_text,
                )
        if offline_home_setup_opt_in:
            try:
                offline_home_output_path = _validate_output_case_path(
                    str(offline_home_output_text), case_path
                )
                if (
                    output_case_path is not None
                    and offline_home_output_path == output_case_path
                ):
                    raise ValueError(
                        "Offline and final case outputs must use distinct paths."
                    )
            except Exception as exc:
                fail(
                    "offline_base_home_configuration",
                    f"{type(exc).__name__}: {exc}",
                    input_path=str(case_path),
                    offline_output_path=offline_home_output_text,
                    final_output_path=(
                        str(output_case_path) if output_case_path is not None else None
                    ),
                )
            report["offline_home_setup_case_output"] = str(
                offline_home_output_path
            )
        else:
            report["items"]["offline_base_home_configuration"] = {
                "status": "NOT_RUN",
                "reason": "DENTOBOT_HEADED_OFFLINE_HOME_SETUP is unset or '0'.",
            }
        report["case_source"] = str(case_path)
        case_hash = _sha256_file(case_path)
        validate_case_bundle(case_path)
        forbidden_overrides = tuple(
            name for name in (
                "DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE",
                "DENTOBOT_ENABLE_HISTORICAL_ANATOMY_REVIEW",
                "DENTOBOT_AUDIT_ACTUAL_CONTACT_ONLY",
            ) if os.environ.get(name) == "1"
        )
        if forbidden_overrides:
            fail(active_check, "Historical overrides are forbidden in this current-case review.",
                 enabled_overrides=list(forbidden_overrides))
        report["case_sha256_before_open"] = case_hash
        _record(report, active_check, "PASS", case_source=str(case_path), case_sha256=case_hash,
                case_bundle_valid=True)

        active_check = "case_opened_and_step6_ui"
        main_window = slicer.util.mainWindow()
        if main_window is None:
            fail(active_check, "Slicer main window is unavailable for headed review.")
        main_window.resize(1500, 850)
        main_window.move(0, 0)
        main_window.show()
        _process_events(0.1)
        slicer.util.selectModule("DENTOWorkflow")
        _process_events(0.3)
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        if widget is None:
            fail(active_check, "DENTOWorkflow widget is unavailable.")
        # The package is opened only in this disposable Slicer process; it is never saved.
        widget._openCaseBundle(str(case_path))
        _process_events(0.5)
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        widget._setWorkflowStage(10, ensureVisible=True)
        widget._configureRobotSimulationShellSubstep(1)
        widget._updateStep6PlanningUi()
        panel = widget._robotSimulationPanel
        facade = widget._robotWorkflowFacade
        logic = widget.logic
        parameter_node = widget._parameterNode
        if not all((panel, facade, logic, parameter_node)):
            fail(active_check, "Restored Step 6 UI or workflow services are unavailable.")
        if widget._step6SceneKind() != "case" or not _visible(panel.visualizationGroup):
            fail(active_check, "The opened package did not show the Step 6 case UI.")
        case_hash_after = _sha256_file(case_path)
        if case_hash_after != case_hash:
            fail(active_check, "The source .dentocase changed while it was opened.")
        report["case_sha256_after_open"] = case_hash_after
        report["case_open"] = {"path": str(case_path), "sha256": case_hash, "saved": False}
        _capture(report, evidence_dir, run_id, "case-step6-ui")
        _record(report, active_check, "PASS", step6_stage=10, step6_substep=1,
                case_sha256_before=case_hash, case_sha256_after=case_hash_after,
                screenshot=report["screenshots"]["case-step6-ui"])

        active_check = "saved_case_ros_readiness_not_restored"
        capabilities = facade.capabilities()
        if capabilities.connected:
            fail(active_check, "Saved case unexpectedly restored a connected ROS session.")
        if capabilities.simulation_only is not True:
            fail(active_check, "Workflow did not report simulation-only capability.")
        _capture(report, evidence_dir, run_id, "saved-case-ros-not-restored")
        _record(report, active_check, "PASS", connected=False,
                simulation_only=True,
                ros_robot_node_count=len(slicer.util.getNodesByClass("vtkMRMLROS2RobotNode")),
                screenshot=report["screenshots"]["saved-case-ros-not-restored"])

        active_check = "simulation_robot_models_loaded"
        widget._configureRobotSimulationShellSubstep(1)
        widget._updateStep6PlanningUi()
        load_button = panel.loadFallbackButton
        if not load_button.enabled:
            fail(active_check, "Production Load Robot control is not enabled.",
                 button_text=str(load_button.text),
                 local_robot_model_count=len(logic.robotModelNodes()))
        _scroll_to_visible(widget, load_button, "Load Robot")
        load_button.click()
        _process_events(0.2)
        robot_models = _wait_until(
            lambda: logic.robotModelNodes()
            if len(logic.robotModelNodes()) == EXPECTED_ROBOT_LINK_COUNT
            else None
        )
        robot_model_count = len(logic.robotModelNodes())
        if robot_models is None:
            fail(active_check, "Production Load Robot did not load all local robot models.",
                 expected_model_count=EXPECTED_ROBOT_LINK_COUNT,
                 actual_model_count=robot_model_count)
        load_frame = _scroll_to_visible(widget, load_button, "loaded robot/Base controls")
        _capture(report, evidence_dir, run_id, "robot-models-loaded")
        _record(report, active_check, "PASS", production_control=str(load_button.text),
                local_robot_models_loaded=True,
                local_robot_model_count=robot_model_count,
                expected_model_count=EXPECTED_ROBOT_LINK_COUNT,
                screenshot=report["screenshots"]["robot-models-loaded"],
                screenshot_framing=load_frame)

        active_check = "planning_context_imported"
        widget._configureRobotSimulationShellSubstep(0)
        widget._updateStep6PlanningUi()
        import_button = widget.ui.importStep6PlanningContextButton
        branch_before = logic.evaluatePreparedBranchEligibility(parameter_node)
        if branch_before.get("eligible") is not True or branch_before.get("reason") != "VALID":
            fail(active_check, "Current PreparedBranch is not eligible for Step 6 context import.",
                 branch_eligibility=branch_before)
        if not import_button.enabled:
            fail(active_check, "Production Import Planning Context control is not enabled.",
                 button_text=str(import_button.text),
                 branch_eligibility=branch_before)
        _scroll_to_visible(widget, import_button, "Import Planning Context")
        import_button.click()
        _process_events(0.2)
        imported = _wait_until(lambda: bool(parameter_node.step6PlanningContextImported))
        branch_after = logic.evaluatePreparedBranchEligibility(parameter_node)
        if not imported:
            fail(active_check, "Production Import Planning Context did not set the imported state.",
                 step6_planning_context_imported=bool(parameter_node.step6PlanningContextImported),
                 branch_eligibility=branch_after)
        if (branch_after.get("eligible") is not True
                or branch_after.get("reason") != "VALID"
                or branch_after.get("branch_id") != branch_before.get("branch_id")):
            fail(active_check, "PreparedBranch eligibility changed or became stale after context import.",
                 branch_before=branch_before, branch_after=branch_after,
                 step6_planning_context_imported=True)
        import_frame = _scroll_to_visible(widget, import_button, "imported planning context")
        _capture(report, evidence_dir, run_id, "planning-context-imported")
        _record(report, active_check, "PASS", production_control=str(import_button.text),
                step6_planning_context_imported=True,
                branch_eligibility=branch_after,
                branch_id=branch_after["branch_id"],
                screenshot=report["screenshots"]["planning-context-imported"],
                screenshot_framing=import_frame)

        active_check = "base_controls_and_accepted_status"
        widget._configureRobotSimulationShellSubstep(1)
        widget._updateStep6PlanningUi()
        base_status = _base_review(facade)
        base_details = dict(base_status.details or {})
        visible_controls = {
            "group": _visible(panel.manualBaseReviewGroup),
            "review_current_base": _visible(panel.beginManualBaseReviewButton),
            "cancel_review": _visible(panel.cancelManualBaseReviewButton),
            "unlock_base": _visible(widget.ui.unlockRobotBaseMountButton),
            "accept_base": _visible(widget.ui.lockRobotBaseMountButton),
            "reconcile_base": _visible(panel.reconcileManualBaseStateButton),
            "accepted_base_status": _visible(widget.ui.step6MountLockStatusLabel),
        }
        state_action_visible = any(
            visible_controls[name]
            for name in (
                "review_current_base",
                "cancel_review",
                "unlock_base",
                "accept_base",
                "reconcile_base",
            )
        )
        if not (
            visible_controls["group"]
            and visible_controls["accepted_base_status"]
            and state_action_visible
        ):
            fail(active_check, "Manual Base controls or accepted Base status are not visible.",
                 controls=visible_controls)
        base_frame = _scroll_to_visible(widget, panel.manualBaseReviewGroup,
                                        "Manual Base review")
        _capture(report, evidence_dir, run_id, "base-controls")
        _record(report, active_check, "PASS", controls=visible_controls,
                accepted_base_status=str(widget.ui.step6MountLockStatusLabel.text),
                accepted_matrix_world_ras_mm=base_details["acceptedMatrixWorldRasMm"],
                candidate_staged=False, base_locked=bool(parameter_node.robotBaseMountLocked),
                screenshot=report["screenshots"]["base-controls"],
                screenshot_framing=base_frame)

        if offline_home_setup_opt_in:
            active_check = "offline_base_home_configuration"
            _run_offline_base_home_configuration(
                widget, panel, logic, parameter_node, facade,
                case_path, case_hash, offline_home_output_path,
                report, evidence_dir, run_id,
            )

        active_check = "draft_state_control_visible"
        widget._configureRobotSimulationShellSubstep(3)
        _show_step63_view(panel, 0, 0)
        if not _visible(panel.manualJogGroup) or not _visible(panel.checkManualDraftStateButton):
            fail(active_check, "Read-only Check Draft State control is not visible.")
        draft_frame = _scroll_to_visible(widget, panel.manualJogGroup,
                                         "manual draft controls")
        _capture(report, evidence_dir, run_id, "draft-state-control")
        _record(report, active_check, "PASS", visible=True,
                control_text=str(panel.checkManualDraftStateButton.text),
                screenshot=report["screenshots"]["draft-state-control"],
                screenshot_framing=draft_frame)

        active_check = "native_version_preflight"
        allow_jog = os.environ.get("DENTOBOT_HEADED_ALLOW_JOG", "") == "1"
        native_preflight_requested = any(
            os.environ.get(name, "").strip()
            for name in (
                "DENTOBOT_HEADED_NATIVE_SOURCE_SHA256",
                "DENTOBOT_HEADED_NATIVE_BINARY_SHA256",
                "DENTOBOT_HEADED_NATIVE_PACKAGE_PREFIX",
            )
        )
        if native_preflight_requested:
            native = _native_preflight()
            report["native_preflight"] = native
            _record(report, active_check, "PASS", **native)
        else:
            native = None
            _record(report, active_check, "NOT_RUN",
                    reason="No exact native source/binary version preflight was provided.")

        if (
            not allow_jog
            and not draft_only
            and not invalid_draft_review
            and not joint_keyboard_opt_in
            and not workspace_diagnostic
            and not connect_only
            and not offline_home_setup_opt_in
        ) or native is None:
            reasons = []
            if (
                not allow_jog
                and not draft_only
                and not invalid_draft_review
                and not joint_keyboard_opt_in
                and not workspace_diagnostic
                and not connect_only
                and not offline_home_setup_opt_in
            ):
                reasons.append(
                    "No guarded-jog, taskless-draft, invalid-draft, joint-keyboard, workspace-diagnostic, connect-only, or offline-Home setup opt-in is enabled."
                )
            if native is None:
                reasons.append("Exact native source/binary preflight is unavailable.")
            reason = " ".join(reasons)
            complete_not_run(
                ("simulation_ros_connect_and_scene_readback", "draft_state_read_only",
                 "invalid_out_of_reviewed_range_draft", "single_guarded_j1_jog",
                 "historical_record_export_reopen", "base_stage_and_cancel",
                 "case_bound_rejected_guard", "unknown_reconcile_state",
                 "profile_migration_recovery_after_scene_ack",
                 "profile_migration_recovery_before_save",
                 "manual_jog_keyboard_draft_check"),
                reason,
            )
            _record(report, "base_acceptance_trial", "NOT_RUN",
                    reason=(
                        "Base/Home acceptance trials were not reached because the required "
                        "guarded J1 and Base stage/cancel checks did not pass; Accept Base "
                        "and Accept Task Home were never called."
                    ))
            _record(report, "task_home_review_acceptance_trial", "NOT_RUN",
                    reason=(
                        "Base/Home acceptance trials were not reached because the required "
                        "guarded J1 and Base stage/cancel checks did not pass; Accept Base "
                        "and Accept Task Home were never called."
                    ))
            outcome = "PARTIAL"
            message = reason
        else:
            confirmed_task_present = logic.confirmedTaskRecord(parameter_node) is not None
            if draft_only and confirmed_task_present:
                fail(
                    "draft_state_read_only",
                    "Taskless draft-only mode requires a case with no confirmed task; no ROS connection was started.",
                    confirmed_task_present=True,
                )
            active_check = "base_profile_rebind_prerequisite"
            _run_base_profile_rebind_prerequisite(
                widget, panel, logic, parameter_node, facade, case_path, case_hash,
                allow_base_home_accept, report, evidence_dir, run_id,
            )
            active_check = "simulation_ros_connect_and_scene_readback"
            widget._configureRobotSimulationShellSubstep(1)
            _process_events(0.1)
            if facade.capabilities().connected:
                fail(active_check, "A ROS session was already connected before the explicit connection trial.")
            if not panel.connectButton.enabled:
                fail(active_check, "Production simulation ROS Connect control is not enabled.")
            panel.connectButton.click()
            _process_events(0.2)
            capabilities = facade.capabilities()
            if capabilities.connected is not True or capabilities.simulation_only is not True:
                fail(active_check, "Simulation-only ROS/MoveIt connection did not become current.",
                     connected=bool(capabilities.connected), simulation_only=bool(capabilities.simulation_only),
                     status_text=str(panel.runtimeStatusLabel.text))
            if not panel.syncCollisionButton.enabled:
                fail(active_check, "Production case collision-scene audit/sync control is not enabled.")
            panel.syncCollisionButton.click()
            _process_events(0.2)
            scene = _scene_evidence(logic, parameter_node)
            scene_ack = scene["runtime_acknowledgement"]
            if (scene_ack.get("status") != "Acknowledged"
                    or not scene["source_object_ids"]
                    or scene["source_object_ids"] != scene["acknowledged_object_ids"]):
                fail(active_check, "Native collision-scene object-presence readback did not match the case objects.",
                     scene=scene)
            report["simulation_scene_readback"] = scene
            if connect_only:
                _capture(report, evidence_dir, run_id, "ros-scene-object-readback")
                _record(report, active_check, "PASS", connected=True, simulation_only=True,
                        scene=scene, screenshot=report["screenshots"]["ros-scene-object-readback"])
                active_check = "simulation_ros_disconnect"
                if not panel.disconnectButton.enabled:
                    fail(active_check, "Production Disconnect control is not enabled.")
                disconnect_started = time.monotonic()
                panel.disconnectButton.click()
                _process_events(0.2)
                if facade.capabilities().connected:
                    fail(active_check, "Production Disconnect did not release the ROS session.")
                if _sha256_file(case_path) != case_hash:
                    fail(active_check, "Connect/Disconnect modified the source package.")
                _capture(report, evidence_dir, run_id, "ros-disconnected")
                _record(report, active_check, "PASS", connected=False,
                        wall_seconds=time.monotonic() - disconnect_started,
                        screenshot=report["screenshots"]["ros-disconnected"])
                report["bounded_connect_disconnect"] = "PASS"
                raise LookupError("Bounded restore/Connect/Disconnect passed; remaining workflow actions were intentionally not run.")
            if offline_home_setup_opt_in:
                active_check = "offline_base_home_configuration"
                _validate_offline_home_after_connection(
                    widget, panel, logic, parameter_node, facade,
                    report, evidence_dir, run_id,
                )
            if _exact_env_opt_in("DENTOBOT_HEADED_SESSION"):
                # Operator 2026-10-02: checkpoint after connect + scene ack, then
                # serve command scripts with hot reload instead of restarting.
                _serve_command_session(
                    {**globals(), **locals()}, widget, panel, facade, report, evidence_dir,
                )
            active_check = "profile_migration_recovery_after_scene_ack"
            _ensure_current_home_workspace_task(
                widget, panel, logic, parameter_node, facade, case_path, case_hash,
                report, evidence_dir, run_id, phase="after_scene_ack",
                check_name=active_check,
                skip_reason=(
                    "Taskless draft-only mode preserves its read-only checkpoint."
                    if draft_only else (
                        "Joint keyboard draft-only mode does not require Task Home or workspace recovery."
                        if joint_keyboard_only else None
                    )
                ),
                workspace_diagnostic=workspace_diagnostic,
            )
            confirmed_task_present = logic.confirmedTaskRecord(parameter_node) is not None
            active_check = "simulation_ros_connect_and_scene_readback"
            if allow_rejected_guard:
                manual_jog_fixture_identity = _manual_jog_fixture_identity(
                    logic, parameter_node
                )
                report["manual_jog_fixture_identity"] = manual_jog_fixture_identity
            _capture(report, evidence_dir, run_id, "ros-scene-object-readback")
            _record(report, active_check, "PASS", connected=True, simulation_only=True,
                    scene=scene, screenshot=report["screenshots"]["ros-scene-object-readback"])

            active_check = "draft_state_read_only"
            widget._configureRobotSimulationShellSubstep(3)
            _show_step63_view(panel, 0, 0)
            before_draft = _actual_joint_state(facade)
            if not all(before_draft.get(name) for name in ("accepted_si", "monitored_si", "displayed_si")):
                fail(active_check, "Accepted, monitored, or displayed J1–J5 state is unavailable.",
                     before=before_draft)
            if not (_representationally_matches(before_draft["accepted_si"], before_draft["monitored_si"])
                    and _representationally_matches(before_draft["accepted_si"], before_draft["displayed_si"])):
                fail(active_check, "Accepted, monitored, and displayed states differ before the read-only check.",
                     before=before_draft)
            panel._setManualJogDraftValues(_display_values(before_draft["accepted_si"]), notify=True)
            requested_draft = _finite_vector(panel.manualJogJointPositionsSi())
            if not _representationally_matches(requested_draft, before_draft["accepted_si"]):
                fail(active_check, "Visible draft controls cannot represent the accepted J1–J5 vector within 1e-12 SI.")
            panel.checkManualDraftStateButton.click()
            _process_events(0.1)
            draft_evidence = dict(panel._manualDraftStateCheckEvidence or {})
            evaluation = draft_evidence.get("manual_state_evaluation") or {}
            endpoint = evaluation.get("endpoint_evaluation") or {}
            static = endpoint.get("static_state_validity") or {}
            target_endpoint_status = evaluation.get("target_endpoint_status")
            target_ras_mm = evaluation.get("target_ras_mm")
            residuals = {
                "position_residual_mm": endpoint.get("position_residual_mm"),
                "drilling_axis_residual_deg": endpoint.get("drilling_axis_residual_deg"),
            }
            review_scope = (
                "confirmed_task_endpoint"
                if confirmed_task_present
                else "static_only_unconfirmed_task"
            )
            review_metadata = {
                "confirmed_task_present": confirmed_task_present,
                "review_scope": review_scope,
                "target_endpoint_status": target_endpoint_status,
                "target_ras_mm": target_ras_mm,
                "residuals": residuals,
            }
            if (
                not confirmed_task_present
                and (
                    target_endpoint_status != "not_reached"
                    or target_ras_mm is not None
                    or any(value is not None for value in residuals.values())
                )
            ):
                fail(
                    active_check,
                    "Unconfirmed-task draft review reported target endpoint evidence or residuals.",
                    **review_metadata,
                    evidence=draft_evidence,
                )
            if (evaluation.get("status") != "passed"
                    or static.get("status") != "passed"
                    or static.get("authoritative") is not True
                    or evaluation.get("identity_status") != "current"):
                fail(active_check, "Check Draft State returned failed or unknown live evidence; stopping without retry.",
                     **review_metadata,
                     evidence=draft_evidence)
            after_draft = _actual_joint_state(facade)
            if not all(after_draft.get(name) for name in ("accepted_si", "monitored_si", "displayed_si")):
                fail(active_check, "Accepted, monitored, or displayed state is unavailable after Check Draft State.",
                     **review_metadata,
                     evidence=draft_evidence, after=after_draft)
            unchanged = all(
                _exactly_matches(before_draft[key], after_draft[key])
                for key in ("accepted_si", "monitored_si", "displayed_si")
            )
            if not unchanged:
                fail(active_check, "Read-only Check Draft State changed the accepted simulation state.",
                     **review_metadata,
                     before=before_draft, after=after_draft, evidence=draft_evidence)
            draft_checked_frame = _scroll_to_visible(widget, panel.manualJogGroup,
                                                     "checked manual draft controls")
            _capture(report, evidence_dir, run_id, "draft-state-checked")
            _record(report, active_check, "PASS", requested=requested_draft,
                    **review_metadata,
                    verdict=static.get("status"), authoritative=static.get("authoritative"),
                    identity_status=evaluation.get("identity_status"),
                    accepted_state_unchanged=True, before=before_draft, after=after_draft,
                    evidence=draft_evidence,
                    screenshot=report["screenshots"]["draft-state-checked"],
                    screenshot_framing=draft_checked_frame)

            if joint_keyboard_opt_in:
                active_check = "manual_jog_keyboard_draft_check"
                _run_manual_jog_keyboard_draft_check(
                    widget, panel, facade, report, evidence_dir, run_id
                )
                if joint_keyboard_only:
                    active_check = "single_guarded_j1_jog"
                    raise LookupError(
                        "Joint keyboard draft-only review completed; guarded jog, planning, "
                        "and preview were not requested."
                    )

            if invalid_draft_review:
                active_check = "invalid_out_of_reviewed_range_draft"
                candidate, unavailable_reason = _select_invalid_draft_candidate(
                    panel, _display_values(after_draft["accepted_si"])
                )
                if candidate is None:
                    _record(
                        report,
                        active_check,
                        "NOT_RUN",
                        reason=unavailable_reason,
                        screenshot=report["screenshots"]["draft-state-checked"],
                        no_motion_sent=True,
                    )
                    active_check = "single_guarded_j1_jog"
                    raise LookupError(
                        "Invalid draft review was NOT_RUN: " + unavailable_reason
                        + " No motion was sent."
                    )

                invalid_before = _actual_joint_state(facade)
                if not all(
                    _exactly_matches(invalid_before[key], after_draft[key])
                    for key in ("accepted_si", "monitored_si", "displayed_si")
                ):
                    fail(
                        active_check,
                        "Accepted, monitored, or displayed pose changed before the invalid-draft check.",
                        before=after_draft,
                        current=invalid_before,
                    )
                if panel.manualJogReconciliationRequired:
                    fail(
                        active_check,
                        "Manual-jog reconciliation is required before the invalid-draft review.",
                    )
                if not panel.guardedManualJogButton.enabled:
                    fail(
                        active_check,
                        "Guarded Jog was not enabled for the accepted in-limit baseline pose.",
                    )
                control = panel.manualJogJointControls[candidate["joint"]][1]
                invalid_record = None
                try:
                    control.setValue(candidate["candidate_display"])
                    _process_events(0.1)
                    requested_invalid = _finite_vector(panel.manualJogJointPositionsSi())
                    if not _representationally_matches(
                        _visible_manual_draft_display_values(panel),
                        candidate["display_values"],
                    ):
                        fail(
                            active_check,
                            "The production numeric control did not retain the selected overstep.",
                            candidate=candidate,
                            requested=requested_invalid,
                        )
                    if panel.guardedManualJogButton.enabled:
                        fail(
                            active_check,
                            "Guarded Jog remained enabled for the out-of-reviewed-range draft.",
                            candidate=candidate,
                        )

                    panel.checkManualDraftStateButton.click()
                    _process_events(0.1)
                    invalid_evidence = dict(panel._manualDraftStateCheckEvidence or {})
                    invalid_evaluation = invalid_evidence.get("manual_state_evaluation") or {}
                    violation = _matching_reviewed_limit_violation(
                        invalid_evidence, candidate
                    )
                    if (
                        invalid_evidence.get("draftWithinCommandLimits") is not False
                        or invalid_evidence.get("limitAssessmentAuthoritative") is not True
                        or invalid_evaluation.get("status") != "failed"
                        or invalid_evaluation.get("identity_status") != "current"
                        or invalid_evaluation.get("target_endpoint_status") != "not_reached"
                        or not isinstance(violation, Mapping)
                        or invalid_evidence.get("routeAuthority") != "none"
                        or invalid_evidence.get("simulationOnly") is not True
                        or report["route_authority"] != "none"
                        or report["planner_calls"] != 0
                        or report["preview_started"] is not False
                        or report["jog_requests"] != 0
                        or panel.manualJogReconciliationRequired
                    ):
                        fail(
                            active_check,
                            "Check Draft State did not return current authoritative reviewed-limit evidence with no route/preview authority.",
                            candidate=candidate,
                            evidence=invalid_evidence,
                        )
                    violation_value = float(violation.get("candidateDisplayValue"))
                    violation_bound = float(violation.get("boundDisplayValue"))
                    outside_bound = (
                        violation_value > violation_bound
                        if candidate["bound"] == "maximum"
                        else violation_value < violation_bound
                    )
                    if (
                        not math.isfinite(violation_value)
                        or not math.isfinite(violation_bound)
                        or not outside_bound
                        or panel.guardedManualJogButton.enabled
                    ):
                        fail(
                            active_check,
                            "Authoritative reviewed-limit evidence did not match the numeric overstep or Guarded Jog remained enabled.",
                            candidate=candidate,
                            violation=dict(violation),
                        )
                    invalid_after = _actual_joint_state(facade)
                    if not all(
                        _exactly_matches(invalid_before[key], invalid_after[key])
                        for key in ("accepted_si", "monitored_si", "displayed_si")
                    ):
                        fail(
                            active_check,
                            "The read-only invalid-draft check changed accepted, monitored, or displayed pose.",
                            before=invalid_before,
                            after=invalid_after,
                            evidence=invalid_evidence,
                        )
                    invalid_frame = _scroll_to_visible(
                        widget, panel.manualJogGroup,
                        "out-of-reviewed-range manual draft",
                    )
                    invalid_screenshot = _capture(
                        report, evidence_dir, run_id,
                        "invalid-out-of-reviewed-range-draft",
                    )
                    invalid_record = {
                        "selected_candidate": candidate,
                        "requested_positions_si": requested_invalid,
                        "accepted_state_label": str(panel.manualJogAcceptedStateLabel.text),
                        "draft_state_label": str(panel.manualJogDraftStateLabel.text),
                        "draft_limit_label": str(panel.manualJogDraftLimitLabel.text),
                        "check_status_label": str(panel.manualDraftStateCheckStatusLabel.text),
                        "guard_status_label": str(panel.manualJogStatusLabel.text),
                        "guarded_jog_enabled": bool(panel.guardedManualJogButton.enabled),
                        "accepted_simulation_state_unchanged": True,
                        "state_before": invalid_before,
                        "state_after": invalid_after,
                        "evidence": invalid_evidence,
                        "route_authority": report["route_authority"],
                        "planner_calls": report["planner_calls"],
                        "preview_started": report["preview_started"],
                        "screenshot": invalid_screenshot,
                        "screenshot_framing": invalid_frame,
                    }
                finally:
                    panel._setManualJogDraftValues(
                        _display_values(invalid_before["accepted_si"]), notify=True
                    )
                    _process_events(0.1)
                    restored_draft = _finite_vector(panel.manualJogJointPositionsSi())
                    if not _representationally_matches(
                        restored_draft, invalid_before["accepted_si"]
                    ):
                        raise RuntimeError(
                            "Could not restore the invalid draft to the accepted J1–J5 pose; no subsequent action is allowed."
                        )
                    if not panel.guardedManualJogButton.enabled:
                        raise RuntimeError(
                            "Guarded Jog did not re-enable for the restored accepted pose; no subsequent action is allowed."
                        )
                invalid_record["restored_draft_positions_si"] = restored_draft
                invalid_record["restored_before_any_guarded_jog"] = True
                _record(report, active_check, "PASS", **invalid_record)
            else:
                _record(
                    report,
                    "invalid_out_of_reviewed_range_draft",
                    "NOT_RUN",
                    reason="DENTOBOT_HEADED_INVALID_DRAFT_REVIEW is unset or '0'.",
                )

            if draft_only:
                active_check = "single_guarded_j1_jog"
                raise LookupError(
                    "Taskless draft-only review completed after Check Draft State; "
                    "guarded jog and Base/Home checks were intentionally not run."
                )

            if not allow_jog:
                active_check = "single_guarded_j1_jog"
                raise LookupError(
                    "Read-only Step 6 draft checks completed; DENTOBOT_HEADED_ALLOW_JOG is not enabled, so no motion or Base/Home checks were run."
                )

            active_check = "single_guarded_j1_jog"
            if panel.manualJogReconciliationRequired:
                fail(active_check, "Manual jog reconciliation is already required; no jog was sent.")
            accepted_before = after_draft["accepted_si"]
            target, direction = _target_j1(logic, parameter_node, accepted_before)
            panel._setManualJogDraftValues(_display_values(target), notify=True)
            target = _finite_vector(panel.manualJogJointPositionsSi())
            one_j1_step = math.radians(ACCEPTED_DELTA_DEG)
            if (not math.isclose(
                    abs(target[JOINT_NAMES[0]] - accepted_before[JOINT_NAMES[0]]),
                    one_j1_step, rel_tol=0.0, abs_tol=1.0e-12)
                    or not _representationally_matches(
                        {name: target[name] for name in JOINT_NAMES[1:]},
                        {name: accepted_before[name] for name in JOINT_NAMES[1:]},
                    )
                    or _within_both_limits(logic, parameter_node, target) is None):
                fail(active_check, "Visible controls do not preserve one in-limit 0.1-degree J1-only request.",
                     target=target, accepted_before=accepted_before)
            if allow_rejected_guard:
                active_check = "case_bound_rejected_guard"
                rejection_plan, rejection_limits = _prepare_case_bound_rejection(
                    rejection_plan_json,
                    case_hash,
                    manual_jog_fixture_identity,
                    logic,
                    parameter_node,
                    panel,
                    target,
                )
                report.setdefault("outcome_scenarios", {})["rejected"] = {
                    "status": "PREFLIGHT_PASS",
                    "case_sha256": case_hash,
                    "fixture_identity": manual_jog_fixture_identity,
                    "review_reference": rejection_plan["review_reference"],
                    "starting_positions_si": rejection_plan["starting_positions_si"],
                    "requested_positions_si": rejection_plan["requested_positions_si"],
                    "limit_evidence": rejection_limits,
                }
                _write_report(report)
                active_check = "single_guarded_j1_jog"
            if not panel.guardedManualJogButton.enabled:
                fail(active_check, "Production Guarded Jog control is not enabled.")
            jog_ui = _guard_click(widget, panel, target)
            report["jog_requests"] = 1
            _capture(report, evidence_dir, run_id, "guarded-j1-jog-result")
            jog_evidence = dict(jog_ui.get("evidence") or {})
            if (jog_evidence.get("manualJogStatus") != "accepted"
                    or jog_evidence.get("guardAccepted") is not True
                    or jog_evidence.get("identityStatus") != "current"):
                fail(active_check, "Single guarded J1 jog was rejected or unknown; stopping with no retry.",
                     direction=direction, jog_ui=jog_ui, evidence=jog_evidence,
                     state_query_after_unknown=False)
            native_guard = jog_evidence.get("nativeGuardEvidence") or {}
            if (native_guard.get("responseObserved") is not True
                    or native_guard.get("responseCorrelated") is not True
                    or not str(native_guard.get("requestId") or "")
                    or native_guard.get("requestId") != jog_evidence.get("requestId")
                    or not str(native_guard.get("sessionId") or "")
                    or native_guard.get("sessionId") != jog_evidence.get("sessionId")
                    or native_guard.get("policyId") != bridge.ROS2_MANUAL_JOINT_POLICY_ID
                    or native_guard.get("collisionScenePolicyIdentityStatus")
                    != "manual_policy_id_correlated"
                    or native_guard.get("commandValid") is not True
                    or native_guard.get("accepted") is not True
                    or native_guard.get("bridgeReturnedAccepted") is not True
                    or native_guard.get("worldObjectEvidencePresent") is not True
                    or native_guard.get("worldObjectCount") != len(scene["source_object_ids"])
                    or sorted(str(item) for item in native_guard.get("worldObjectIds") or ())
                    != scene["acknowledged_object_ids"]
                    or not _exactly_matches(native_guard.get("requestedPositionsSi"), target)
                    or not _exactly_matches(native_guard.get("acceptedPositionsSi"), target)):
                fail(active_check, "Guard acknowledgement did not match the single J1 request and case-object readback.",
                     direction=direction, jog_ui=jog_ui, native_guard=native_guard)
            matched = _wait_until(
                lambda: _actual_joint_state(facade)
                if _exactly_matches(bridge.last_accepted_joint_positions_si(), target)
                and _representationally_matches(bridge.monitored_joint_positions_si(), target)
                else None
            )
            if not matched or not all(
                (_exactly_matches(matched[key], target) if key == "accepted_si"
                 else _representationally_matches(matched[key], target))
                for key in ("accepted_si", "monitored_si", "displayed_si")
            ):
                fail(active_check, "Accepted guarded J1 jog did not match accepted, monitored, and displayed state.",
                     direction=direction, target=target, observed=matched, jog_ui=jog_ui)
            _record(report, active_check, "PASS", direction=direction, target=target,
                    jog_requests=1, jog_ui=jog_ui, native_guard=native_guard,
                    accepted_monitored_displayed_match=True,
                    screenshot=report["screenshots"]["guarded-j1-jog-result"])

            if allow_rejected_guard:
                active_check = "case_bound_rejected_guard"
                _run_case_bound_rejection(
                    widget, panel, logic, parameter_node, facade, case_hash,
                    manual_jog_fixture_identity, scene, rejection_plan,
                    rejection_limits, report, evidence_dir, run_id,
                )
            else:
                _record(
                    report,
                    "case_bound_rejected_guard",
                    "NOT_RUN",
                    reason="DENTOBOT_HEADED_ALLOW_REJECTED_JOG is unset or '0'.",
                )

            if allow_unknown_reconciliation:
                active_check = "unknown_reconcile_state"
                _run_unknown_reconciliation(
                    widget, panel, logic, parameter_node, facade, scene,
                    report, evidence_dir, run_id,
                )
            else:
                _record(
                    report,
                    "unknown_reconcile_state",
                    "NOT_RUN",
                    reason="DENTOBOT_HEADED_ALLOW_UNKNOWN_RECONCILIATION is unset or '0'.",
                )

            active_check = "historical_record_export_reopen"
            if record_reopen:
                probe = _load_historical_record_probe()
                probe_evidence = probe(
                    widget,
                    panel,
                    evidence_dir,
                    lambda stage: _capture(
                        report,
                        evidence_dir,
                        run_id,
                        f"historical-record-{stage}",
                    ),
                )
                evidence_error = _historical_record_probe_evidence_error(
                    probe_evidence, evidence_dir
                )
                if evidence_error:
                    fail(
                        active_check,
                        "Historical-record export/reopen failed: " + evidence_error,
                        probe_evidence=probe_evidence,
                    )
                _record(
                    report,
                    active_check,
                    "PASS",
                    record_json=probe_evidence["record_json"],
                    record_report=probe_evidence["record_report"],
                    artifact_sha256=probe_evidence["artifact_sha256"],
                    event_order=probe_evidence["record"]["event_order"],
                    accepted_j1_j5=probe_evidence["accepted_j1_j5"],
                    route_preview_authority=probe_evidence["route_preview_authority"],
                    probe_evidence=probe_evidence,
                )

            active_check = "base_stage_and_cancel"
            widget._configureRobotSimulationShellSubstep(1)
            widget._updateStep6PlanningUi()
            _process_events(0.1)
            if bool(parameter_node.robotBaseMountLocked):
                if not widget.ui.unlockRobotBaseMountButton.enabled:
                    fail(active_check, "Disposable-scene Base unlock control is not enabled.")
                widget.ui.unlockRobotBaseMountButton.click()
                _process_events(0.1)
                if bool(parameter_node.robotBaseMountLocked):
                    fail(active_check, "Disposable-scene Base unlock did not complete.")
            # Unlocking in 6.1 lets the viewport interaction node re-stage the
            # accepted Base as an identity candidate. Cancel only that exact
            # identity candidate through the production control; preserve any other.
            pre_review = facade.manualBaseReview()
            pre_details = dict(pre_review.details or {})
            if (pre_review.success and pre_details.get("staged") is True
                    and pre_details.get("identityStatus") == "current"
                    and _same_matrix(pre_details.get("candidateMatrixWorldRasMm"),
                                     pre_details.get("acceptedMatrixWorldRasMm"))
                    and panel.cancelManualBaseReviewButton.enabled):
                panel.cancelManualBaseReviewButton.click()
                _process_events(0.1)
                report["identity_viewport_candidate_cancelled"] = True
            base_before = _base_review(facade)
            base_fingerprint = logic.robotBaseFingerprint(parameter_node)
            base_matrix = tuple(base_before.details["acceptedMatrixWorldRasMm"])
            if not panel.beginManualBaseReviewButton.enabled:
                fail(active_check, "Production Review Current Base control is not enabled after safe unlock.")
            panel.beginManualBaseReviewButton.click()
            _process_events(0.1)
            staged = facade.manualBaseReview()
            staged_details = dict(staged.details or {})
            candidate = staged_details.get("candidateMatrixWorldRasMm")
            accepted_matrix = staged_details.get("acceptedMatrixWorldRasMm")
            if (not staged.success or staged_details.get("staged") is not True
                    or staged_details.get("identityStatus") != "current"
                    or not _valid_matrix(candidate)
                    or not _same_matrix(candidate, base_matrix)
                    or not _same_matrix(accepted_matrix, base_matrix)
                    or logic.robotBaseFingerprint(parameter_node) != base_fingerprint):
                fail(active_check, "Base candidate did not stage as a detached copy of the unchanged accepted Base.",
                     stage_result=staged_details)
            if not panel.cancelManualBaseReviewButton.enabled:
                fail(active_check, "Cancel Review did not enable for the staged candidate.")
            staged_frame = _scroll_to_visible(widget, panel.manualBaseReviewGroup,
                                              "staged Manual Base review")
            if not _visible(panel.cancelManualBaseReviewButton):
                fail(active_check, "Cancel Review control is not visible.")
            _capture(report, evidence_dir, run_id, "base-candidate-staged")
            panel.cancelManualBaseReviewButton.click()
            _process_events(0.1)
            cancelled = facade.manualBaseReview()
            cancelled_details = dict(cancelled.details or {})
            if (not cancelled.success or cancelled_details.get("staged") is True
                    or cancelled_details.get("candidateMatrixWorldRasMm") is not None
                    or logic.robotBaseFingerprint(parameter_node) != base_fingerprint
                    or not _same_matrix(cancelled_details.get("acceptedMatrixWorldRasMm"), base_matrix)):
                fail(active_check, "Cancel Review did not clear only the candidate and retain the accepted Base.",
                     cancel_result=cancelled_details)
            cancelled_frame = _scroll_to_visible(widget, panel.manualBaseReviewGroup,
                                                 "cancelled Manual Base review")
            _capture(report, evidence_dir, run_id, "base-candidate-cancelled")
            _record(report, active_check, "PASS", staged_candidate=candidate,
                    accepted_matrix_unchanged=True, candidate_cleared=True,
                    base_left_unlocked=not bool(parameter_node.robotBaseMountLocked),
                    case_saved=False,
                    screenshots={"staged": report["screenshots"]["base-candidate-staged"],
                                 "cancelled": report["screenshots"]["base-candidate-cancelled"]},
                    screenshot_framing={"staged": staged_frame,
                                        "cancelled": cancelled_frame})

            if not allow_base_home_accept:
                opt_out_reason = (
                    "DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT is not exactly '1'; "
                    "Base and Task Home acceptance were not attempted."
                )
                _record(report, "base_acceptance_trial", "NOT_RUN",
                        reason=opt_out_reason)
                _record(report, "task_home_review_acceptance_trial", "NOT_RUN",
                        reason=opt_out_reason)
            else:
                active_check = "base_acceptance_trial"
                base_before_accept = _base_review(facade)
                base_before_details = dict(base_before_accept.details or {})
                if (bool(parameter_node.robotBaseMountLocked)
                        or not _same_matrix(
                            base_before_details.get("acceptedMatrixWorldRasMm"),
                            base_matrix,
                        )
                        or logic.robotBaseFingerprint(parameter_node) != base_fingerprint):
                    fail(active_check,
                         "Accepted Base identity, lock, or matrix changed before the opt-in acceptance trial.",
                         review=base_before_details,
                         base_locked=bool(parameter_node.robotBaseMountLocked),
                         robot_base_fingerprint=logic.robotBaseFingerprint(parameter_node))
                if not panel.beginManualBaseReviewButton.enabled:
                    fail(active_check, "Production Review Current Base control is not enabled for acceptance.")
                panel.beginManualBaseReviewButton.click()
                _process_events(0.1)
                base_acceptance_staged_frame = _scroll_to_visible(
                    widget, panel.manualBaseReviewGroup, "Base acceptance candidate"
                )
                _capture(report, evidence_dir, run_id, "base-acceptance-staged")
                base_acceptance_stage = facade.manualBaseReview()
                base_acceptance_stage_details = dict(base_acceptance_stage.details or {})
                if (not base_acceptance_stage.success
                        or base_acceptance_stage_details.get("staged") is not True
                        or base_acceptance_stage_details.get("identityStatus") != "current"
                        or not _same_matrix(
                            base_acceptance_stage_details.get("candidateMatrixWorldRasMm"),
                            base_matrix,
                        )
                        or not _same_matrix(
                            base_acceptance_stage_details.get("acceptedMatrixWorldRasMm"),
                            base_matrix,
                        )
                        or bool(parameter_node.robotBaseMountLocked)
                        or logic.robotBaseFingerprint(parameter_node) != base_fingerprint):
                    fail(active_check,
                         "Production Base review did not stage the exact accepted matrix without changing Base state.",
                         stage_result=base_acceptance_stage_details,
                         base_locked=bool(parameter_node.robotBaseMountLocked),
                         robot_base_fingerprint=logic.robotBaseFingerprint(parameter_node),
                         screenshot=report["screenshots"].get("base-acceptance-staged"))
                expected_accept_matrix = list(base_matrix)
                if os.environ.get("DENTOBOT_HEADED_FIND_REACHABLE_BASE", "") == "1":
                    # Production "Find Reachable Base" (IK + mesh path preflight)
                    # stages the candidate; acceptance then uses the normal owner.
                    widget._onStep6SearchBasePlacement()
                    _process_events(0.2)
                    search_report = dict(getattr(widget, "_lastBasePlacementSearch", None) or {})
                    found = dict(facade.manualBaseReview().details or {})
                    candidate_matrix = found.get("candidateMatrixWorldRasMm")
                    report["find_reachable_base"] = {
                        "verdict": search_report.get("verdict"),
                        "evaluated": search_report.get("evaluated"),
                        "feasible_count": search_report.get("feasible_count"),
                        "best": {k: (search_report.get("best") or {}).get(k)
                                 for k in ("u_mm", "v_mm", "depth_mm", "minimum_slider_margin_mm")},
                        "path_preflight": search_report.get("path_preflight"),
                        "depth_fallback": search_report.get("depth_fallback"),
                        "staged_candidate": candidate_matrix,
                        "status_text": str(panel.manualBaseReviewStatusLabel.text),
                    }
                    if not _valid_matrix(candidate_matrix) or search_report.get("best") is None:
                        fail(active_check, "Find Reachable Base did not stage a candidate.",
                             find_reachable_base=report["find_reachable_base"])
                    expected_accept_matrix = [float(v) for v in candidate_matrix]
                    _capture(report, evidence_dir, run_id, "base-find-reachable-staged")
                    report["base_offset_applied"] = True
                if base_offset is not None:
                    expected_accept_matrix = _translated_matrix(base_matrix, base_offset)
                    offset_stage = facade.stageManualBaseReview(expected_accept_matrix)
                    offset_details = dict(offset_stage.details or {})
                    if (not offset_stage.success
                            or offset_details.get("staged") is not True
                            or not _same_matrix(
                                offset_details.get("candidateMatrixWorldRasMm"),
                                expected_accept_matrix,
                            )
                            or not _same_matrix(
                                offset_details.get("acceptedMatrixWorldRasMm"), base_matrix
                            )
                            or logic.robotBaseFingerprint(parameter_node) != base_fingerprint):
                        fail(active_check,
                             "Production Base review did not stage the requested translated candidate.",
                             stage_result=offset_details,
                             requested_offset_ras_mm=list(base_offset))
                    _process_events(0.1)
                    _capture(report, evidence_dir, run_id, "base-offset-staged")
                base_acceptance_owner = widget.ui.lockRobotBaseMountButton
                if not base_acceptance_owner.enabled:
                    fail(active_check, "Existing Accept Base owner is not enabled for the staged candidate.",
                         stage_result=base_acceptance_stage_details)
                report["base_acceptance_attempted"] = True
                _write_report(report)
                base_lock_traces = []
                if base_offset is not None:
                    _install_base_lock_tracer(logic, facade, base_lock_traces)
                try:
                    _modal_guarded_click(
                        report, evidence_dir, run_id, base_acceptance_owner,
                        "base-acceptance-accept",
                    )
                except UnexpectedModalError as exc:
                    failure_review = dict(facade.manualBaseReview().details or {})
                    fail(active_check, f"Accept Base raised a modal: {exc.dialog_text}",
                         review=failure_review,
                         base_lock_traces=base_lock_traces,
                         verification_evidence=(failure_review.get("failureEvidence") or {}).get(
                             "verificationEvidence"),
                         requested_offset_ras_mm=list(base_offset) if base_offset else None)
                finally:
                    _remove_base_lock_tracer(logic, facade)
                report["base_lock_traces"] = base_lock_traces
                _process_events(0.2)
                base_acceptance_accepted_frame = _scroll_to_visible(
                    widget, panel.manualBaseReviewGroup, "accepted Base review"
                )
                _capture(report, evidence_dir, run_id, "base-acceptance-accepted")
                base_after_accept = facade.manualBaseReview()
                base_after_details = dict(base_after_accept.details or {})
                scene_after_base_accept = _scene_evidence(logic, parameter_node)
                scene_ack_after_base_accept = scene_after_base_accept["runtime_acknowledgement"]
                case_hash_after_base_accept = _sha256_file(case_path)
                if (not base_after_accept.success
                        or base_after_details.get("staged") is True
                        or base_after_details.get("candidateMatrixWorldRasMm") is not None
                        or base_after_details.get("identityStatus") != "current"
                        or base_after_details.get("acceptanceStatus") == "unknown"
                        or base_after_details.get("acceptanceUncertainty")
                        or not bool(parameter_node.robotBaseMountLocked)
                        or not _same_matrix(
                            base_after_details.get("acceptedMatrixWorldRasMm"), expected_accept_matrix
                        )
                        or facade._planning_scene_synchronized is not True
                        or scene_after_base_accept["status"] != "Acknowledged"
                        or scene_ack_after_base_accept.get("status") != "Acknowledged"
                        or not scene_after_base_accept["source_object_ids"]
                        or scene_after_base_accept["source_object_ids"]
                        != scene_after_base_accept["acknowledged_object_ids"]
                        or case_hash_after_base_accept != case_hash):
                    fail(active_check,
                         "Accept Base did not leave a current locked Base with the unchanged matrix, acknowledged native scene, and unchanged case file.",
                         review=base_after_details,
                         base_locked=bool(parameter_node.robotBaseMountLocked),
                         scene=scene_after_base_accept,
                         planning_scene_synchronized=bool(facade._planning_scene_synchronized),
                         case_sha256_before=case_hash,
                         case_sha256_after=case_hash_after_base_accept,
                         screenshots={
                             "staged": report["screenshots"].get("base-acceptance-staged"),
                             "accepted": report["screenshots"].get("base-acceptance-accepted"),
                         })
                report["base_offset_applied"] = base_offset is not None
                _record(
                    report,
                    active_check,
                    "PASS",
                    opt_in_environment="DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT=1",
                    production_stage_control=str(panel.beginManualBaseReviewButton.text),
                    production_accept_owner=str(base_acceptance_owner.text),
                    owner_success_observed=True,
                    identity_status=base_after_details.get("identityStatus"),
                    base_locked=True,
                    accepted_matrix_world_ras_mm=base_after_details["acceptedMatrixWorldRasMm"],
                    accepted_matrix_unchanged=base_offset is None,
                    base_offset_ras_mm=list(base_offset) if base_offset else None,
                    base_matrix_before_world_ras_mm=list(base_matrix),
                    candidate_cleared=True,
                    native_scene_resynchronized=True,
                    planning_scene_synchronized=True,
                    scene=scene_after_base_accept,
                    case_sha256_before=case_hash,
                    case_sha256_after=case_hash_after_base_accept,
                    screenshots={
                        "staged": report["screenshots"]["base-acceptance-staged"],
                        "accepted": report["screenshots"]["base-acceptance-accepted"],
                    },
                    screenshot_framing={
                        "staged": base_acceptance_staged_frame,
                        "accepted": base_acceptance_accepted_frame,
                    },
                )

                active_check = "task_home_review_acceptance_trial"
                widget._configureRobotSimulationShellSubstep(3)
                widget._updateStep6PlanningUi()
                _show_step63_view(panel, 0, 0)
                home_before_review = facade.manualTaskHomeReview()
                home_before_details = dict(home_before_review.details or {})
                if (not home_before_review.success
                        or home_before_details.get("identityStatus") != "current"
                        or home_before_details.get("staged") is True
                        or home_before_details.get("acceptanceStatus") == "unknown"
                        or home_before_details.get("acceptanceUncertainty")):
                    fail(active_check, "Task Home review identity is stale or unknown before staging; existing evidence is preserved.",
                         review=home_before_details)
                home_state_before = _actual_joint_state(facade)
                if not all(home_state_before.get(name)
                           for name in ("accepted_si", "monitored_si", "displayed_si")):
                    fail(active_check, "Accepted, monitored, or displayed J1–J5 state is unavailable before Task Home review.",
                         state=home_state_before)
                if not (_representationally_matches(home_state_before["accepted_si"], home_state_before["monitored_si"])
                        and _representationally_matches(home_state_before["accepted_si"], home_state_before["displayed_si"])):
                    fail(active_check, "Accepted, monitored, and displayed J1–J5 states differ before Task Home review.",
                         state=home_state_before)
                panel._setManualJogDraftValues(
                    _display_values(home_state_before["accepted_si"]), notify=True
                )
                home_draft = _finite_vector(panel.manualJogJointPositionsSi())
                if not _representationally_matches(home_draft, home_state_before["accepted_si"]):
                    fail(active_check, "The visible manual draft cannot represent the current accepted Home vector within 1e-12 SI.",
                         draft=home_draft, accepted=home_state_before["accepted_si"])
                widget._configureRobotSimulationShellSubstep(2)
                widget._updateStep6PlanningUi()
                if not _visible(panel.homeGroup):
                    fail(active_check, "Production 6.2 Task Home review controls are not visible.")
                home_json_before_stage = str(parameter_node.step6TaskHomeJson or "")
                home_runtime_validated_before_stage = facade.taskHomeRuntimeValidated(parameter_node)
                if not panel.reviewTaskHomeButton.enabled:
                    fail(active_check, "Production Review Draft as Task Home control is not enabled.",
                         review=home_before_details)
                panel.reviewTaskHomeButton.click()
                _process_events(0.1)
                task_home_staged_frame = _scroll_to_visible(
                    widget, panel.homeGroup, "staged Task Home review"
                )
                _capture(report, evidence_dir, run_id, "task-home-review-staged")
                staged_task_home_review = facade.manualTaskHomeReview()
                staged_task_home_details = dict(staged_task_home_review.details or {})
                home_state_after_stage = _actual_joint_state(facade)
                home_json_after_stage = str(parameter_node.step6TaskHomeJson or "")
                home_runtime_validated_after_stage = facade.taskHomeRuntimeValidated(parameter_node)
                if (not staged_task_home_review.success
                        or staged_task_home_details.get("identityStatus") != "current"
                        or staged_task_home_details.get("staged") is not True
                        or staged_task_home_details.get("acceptanceStatus") != "review"
                        or not _representationally_matches(
                            staged_task_home_details.get("candidateJointPositionsSi"), home_state_before["accepted_si"]
                        )
                        or home_json_after_stage != home_json_before_stage
                        or home_runtime_validated_after_stage != home_runtime_validated_before_stage
                        or not all(_exactly_matches(home_state_before[key], home_state_after_stage.get(key))
                                   for key in ("accepted_si", "monitored_si", "displayed_si"))):
                    fail(active_check,
                         "Review Draft as Task Home failed or staging changed accepted state or saved Home.",
                         stage_result=staged_task_home_details,
                         state_before=home_state_before,
                         state_after=home_state_after_stage,
                         home_json_unchanged=home_json_after_stage == home_json_before_stage,
                         runtime_validated_before=home_runtime_validated_before_stage,
                         runtime_validated_after=home_runtime_validated_after_stage,
                         screenshot=report["screenshots"].get("task-home-review-staged"))
                if not panel.acceptTaskHomeButton.enabled:
                    fail(active_check, "Existing Accept Task Home control is not enabled for the staged current pose.",
                         stage_result=staged_task_home_details)
                task_home_accept_owner = panel.acceptTaskHomeButton
                prior_saved_home = logic.taskHomeRecord(parameter_node)
                prior_saved_home_revision = (
                    getattr(prior_saved_home, "revision", None)
                    if prior_saved_home is not None
                    else None
                )
                if (prior_saved_home is not None
                        and (isinstance(prior_saved_home_revision, bool)
                             or not isinstance(prior_saved_home_revision, int)
                             or prior_saved_home_revision < 1)):
                    fail(active_check,
                         "The previously saved Task Home record has an invalid revision; acceptance stopped before clicking its owner.",
                         prior_saved_home=(prior_saved_home.to_dict()
                                           if hasattr(prior_saved_home, "to_dict") else None),
                         prior_saved_home_revision=prior_saved_home_revision)
                report["task_home_acceptance_attempted"] = True
                _write_report(report)
                task_home_accept_owner.click()
                _process_events(0.2)
                task_home_accepted_frame = _scroll_to_visible(
                    widget, panel.homeGroup, "accepted Task Home review"
                )
                _capture(report, evidence_dir, run_id, "task-home-review-accepted")
                task_home_after_accept = facade.manualTaskHomeReview()
                task_home_after_details = dict(task_home_after_accept.details or {})
                saved_home = logic.taskHomeRecord(parameter_node)
                saved_home_vector = (
                    _finite_vector(dict(zip(saved_home.joint_names, saved_home.joint_positions_si)))
                    if saved_home is not None
                    else None
                )
                saved_home_revision = (
                    getattr(saved_home, "revision", None)
                    if saved_home is not None
                    else None
                )
                saved_home_revision_advanced = (
                    isinstance(saved_home_revision, int)
                    and not isinstance(saved_home_revision, bool)
                    and saved_home_revision > (prior_saved_home_revision or 0)
                )
                state_after_home_accept = _actual_joint_state(facade)
                case_hash_after_home_accept = _sha256_file(case_path)
                acceptance_commit_inferred = bool(
                    task_home_after_accept.success
                    and task_home_after_details.get("identityStatus") == "current"
                    and task_home_after_details.get("acceptanceStatus") == "accepted"
                    and task_home_after_details.get("staged") is False
                    and saved_home is not None
                    and saved_home_revision_advanced
                )
                home_state_unchanged = all(
                    _exactly_matches(home_state_before[key], state_after_home_accept.get(key))
                    for key in ("accepted_si", "monitored_si", "displayed_si")
                )
                route_preview_state = {
                    "route_authority": report["route_authority"],
                    "planner_calls": report["planner_calls"],
                    "preview_started": report["preview_started"],
                    "preview_active": bool(facade.previewActive),
                    "return_home_required": bool(facade.returnHomeRequired),
                }
                if (not task_home_after_accept.success
                        or task_home_after_details.get("identityStatus") != "current"
                        or task_home_after_details.get("acceptanceStatus") != "accepted"
                        or task_home_after_details.get("staged") is not False
                        or task_home_after_details.get("candidateJointPositionsSi") is not None
                        or not acceptance_commit_inferred
                        or not saved_home_revision_advanced
                        or saved_home is None
                        or saved_home.runtime_validation_status != "Validated"
                        or facade.taskHomeRuntimeValidated(parameter_node) is not True
                        or saved_home_vector is None
                        or not home_state_unchanged
                        or not all(state_after_home_accept.get(key)
                                   for key in ("accepted_si", "monitored_si", "displayed_si"))
                        or not _representationally_matches(
                            task_home_after_details.get("acceptedJointPositionsSi"),
                            home_state_before["accepted_si"],
                        )
                        or not all(_representationally_matches(
                            state_after_home_accept["accepted_si"], state_after_home_accept[key]
                        ) for key in ("monitored_si", "displayed_si"))
                        or not all(_representationally_matches(saved_home_vector, state_after_home_accept[key])
                                   for key in ("accepted_si", "monitored_si", "displayed_si"))
                        or route_preview_state["route_authority"] != "none"
                        or route_preview_state["planner_calls"] != 0
                        or route_preview_state["preview_started"] is not False
                        or route_preview_state["preview_active"]
                        or route_preview_state["return_home_required"]
                        or case_hash_after_home_accept != case_hash):
                    fail(active_check,
                         "Accept Task Home verification did not show a new live-validated saved Home matching accepted/monitored/displayed state without route/preview authority or case-file mutation.",
                         review=task_home_after_details,
                         acceptance_commit_inferred=acceptance_commit_inferred,
                         prior_saved_home=(prior_saved_home.to_dict()
                                           if prior_saved_home is not None else None),
                         prior_saved_home_revision=prior_saved_home_revision,
                         saved_home_revision=saved_home_revision,
                         saved_home_revision_advanced=saved_home_revision_advanced,
                         home_state_unchanged=home_state_unchanged,
                         saved_home=(saved_home.to_dict() if saved_home is not None else None),
                         saved_home_vector=saved_home_vector,
                         state=state_after_home_accept,
                         runtime_validated=(
                             facade.taskHomeRuntimeValidated(parameter_node)
                             if saved_home is not None else False
                         ),
                         route_preview_state=route_preview_state,
                         case_sha256_before=case_hash,
                         case_sha256_after=case_hash_after_home_accept,
                         screenshots={
                             "staged": report["screenshots"].get("task-home-review-staged"),
                             "accepted": report["screenshots"].get("task-home-review-accepted"),
                         })
                _record(
                    report,
                    active_check,
                    "PASS",
                    production_review_control=str(panel.reviewTaskHomeButton.text),
                    production_accept_owner=str(task_home_accept_owner.text),
                    acceptance_commit={
                        "status": "inferred",
                        "basis": (
                            "fresh facade review reports accepted/current/not-staged "
                            "and the saved TaskHomeRecord revision advanced"
                        ),
                        "prior_saved_home_revision": prior_saved_home_revision,
                        "saved_home_revision": saved_home_revision,
                        "revision_advanced": saved_home_revision_advanced,
                    },
                    identity_status=task_home_after_details.get("identityStatus"),
                    accepted_home=True,
                    runtime_validated=True,
                    saved_home=saved_home.to_dict(),
                    saved_home_revision=saved_home_revision,
                    saved_home_runtime_validation_status=saved_home.runtime_validation_status,
                    saved_home_vector_si=saved_home_vector,
                    accepted_monitored_displayed_state=state_after_home_accept,
                    home_state_unchanged=home_state_unchanged,
                    candidate_cleared=True,
                    route_preview_state=route_preview_state,
                    saved_case=False,
                    case_sha256_before=case_hash,
                    case_sha256_after=case_hash_after_home_accept,
                    screenshots={
                        "staged": report["screenshots"]["task-home-review-staged"],
                        "accepted": report["screenshots"]["task-home-review-accepted"],
                    },
                    screenshot_framing={
                        "staged": task_home_staged_frame,
                        "accepted": task_home_accepted_frame,
                    },
                )
            if base_home_uncertainty_opt_in:
                active_check = "base_home_uncertainty"
                dialog_timeout_sec = BASE_HOME_UNCERTAINTY_DIALOG_TIMEOUT_SEC
                accepted_trials = {
                    "base_acceptance_trial": report["items"]["base_acceptance_trial"]["status"],
                    "task_home_review_acceptance_trial": report["items"]["task_home_review_acceptance_trial"]["status"],
                    "base_acceptance_attempted": report["base_acceptance_attempted"],
                    "task_home_acceptance_attempted": report["task_home_acceptance_attempted"],
                }
                if (
                    not allow_jog_requested
                    or not allow_base_home_accept
                    or any(accepted_trials[name] != "PASS" for name in (
                        "base_acceptance_trial", "task_home_review_acceptance_trial"
                    ))
                    or not accepted_trials["base_acceptance_attempted"]
                    or not accepted_trials["task_home_acceptance_attempted"]
                ):
                    fail(
                        active_check,
                        "Base/Home uncertainty requires completed guarded-jog and Base/Home acceptance trials.",
                        acceptance_prerequisites=accepted_trials,
                        expected_error_dialog_combined_action_and_modal_appearance_timeout_sec=dialog_timeout_sec,
                    )
                report["items"][active_check][
                    "expected_error_dialog_combined_action_and_modal_appearance_timeout_sec"
                ] = dialog_timeout_sec
                _write_report(report)
                capture_uncertainty = lambda stage: _capture(
                    report, evidence_dir, run_id, f"base-home-uncertainty-{stage}"
                )
                try:
                    active_modal_widget = getattr(
                        qt.QApplication, "activeModalWidget", None
                    )
                    if active_modal_widget is None:
                        raise RuntimeError("Qt active-modal-widget reader is unavailable.")
                    dialog_callback = make_expected_error_dialog_callback(
                        qt,
                        active_modal_widget,
                        capture_uncertainty,
                        timeout_sec=dialog_timeout_sec,
                    )
                    uncertainty_evidence = run_base_home_uncertainty_probe(
                        widget,
                        panel,
                        facade,
                        process_events=_process_events,
                        capture_callback=capture_uncertainty,
                        joint_names=JOINT_NAMES,
                        expected_error_dialog_callback=dialog_callback,
                    )
                except Exception as exc:
                    fail(
                        active_check,
                        f"{type(exc).__name__}: {exc}",
                        acceptance_prerequisites=accepted_trials,
                        expected_error_dialog_combined_action_and_modal_appearance_timeout_sec=dialog_timeout_sec,
                        probe_evidence=getattr(exc, "evidence", None),
                    )
                if (
                    not isinstance(uncertainty_evidence, Mapping)
                    or uncertainty_evidence.get("status") != "probe_complete"
                ):
                    fail(
                        active_check,
                        "Base/Home uncertainty probe did not return probe_complete evidence.",
                        acceptance_prerequisites=accepted_trials,
                        expected_error_dialog_combined_action_and_modal_appearance_timeout_sec=dialog_timeout_sec,
                        probe_evidence=uncertainty_evidence,
                    )
                _record(
                    report,
                    active_check,
                    "PASS",
                    expected_error_dialog_combined_action_and_modal_appearance_timeout_sec=dialog_timeout_sec,
                    probe_evidence=uncertainty_evidence,
                )
            else:
                _record(
                    report,
                    "base_home_uncertainty",
                    "NOT_RUN",
                    reason="DENTOBOT_HEADED_BASE_HOME_UNCERTAINTY is unset or '0'.",
                )

            if tcp_case_opt_in:
                active_check = "case_bound_tcp_workbench"
                widget._configureRobotSimulationShellSubstep(3)
                _show_step63_view(panel, 0, 1)
                try:
                    tcp_evidence = run_case_bound_tcp_probe(
                        widget, panel, facade, evidence_dir.parent,
                        lambda stage: _capture(
                            report, evidence_dir, run_id, f"tcp-{stage}"
                        ),
                        mouse_drag_callback=(
                            make_external_mouse_drag_callback(evidence_dir.parent)
                            if _mouse_drag_requested() else None
                        ),
                    )
                except Exception as exc:
                    fail(
                        active_check,
                        f"{type(exc).__name__}: {exc}",
                        probe_evidence=getattr(exc, "evidence", None),
                    )
                _record(report, active_check, "PASS", probe_evidence=tcp_evidence)
            else:
                _record(report, "case_bound_tcp_workbench", "NOT_RUN",
                        reason="DENTOBOT_HEADED_TCP_CASE is unset or '0'.")

            if complete_cycles_opt_in or full_chain_opt_in:
                active_check = "planning_prerequisites"
                _ensure_current_home_workspace_task(
                    widget, panel, logic, parameter_node, facade, case_path, case_hash,
                    report, evidence_dir, run_id, phase="before_planning",
                    check_name=active_check,
                )
                widget._configureRobotSimulationShellSubstep(3)
                widget._updateStep6PlanningUi()
                _show_step63_view(panel, 2, 0)
                planning_controls = {
                    "plan_approach_enabled": bool(panel.planApproachButton.enabled),
                    "compare_planners_enabled": bool(panel.comparePlannersButton.enabled),
                    "status_text": str(panel.confirmationStatusLabel.text),
                }
                prerequisites = report.get("planning_prerequisites", {})
                if not all(
                    planning_controls[name]
                    for name in (
                        "plan_approach_enabled",
                        "compare_planners_enabled",
                    )
                ):
                    fail(
                        active_check,
                        "Current Home, workspace, reviewed limits, and task confirmation "
                        "did not enable the selected planning probe controls.",
                        prerequisite_evidence=prerequisites,
                        planning_controls=planning_controls,
                    )
                _record(
                    report,
                    active_check,
                    "PASS",
                    phase="before_planning",
                    prerequisite_evidence=prerequisites,
                    planning_controls=planning_controls,
                )
                if os.environ.get("DENTOBOT_HEADED_DIAGNOSE_BASE", "") == "1":
                    _run_base_diagnosis(widget, panel, facade, report, evidence_dir, run_id)
            else:
                _record(
                    report,
                    "planning_prerequisites",
                    "NOT_RUN",
                    reason=(
                        "Neither DENTOBOT_HEADED_COMPLETE_CYCLES nor "
                        "DENTOBOT_HEADED_FULL_CHAIN is selected."
                    ),
                )

            if complete_cycles_opt_in:
                active_check = "complete_cycles"
                accepted_trials = {
                    "base_acceptance_trial": report["items"]["base_acceptance_trial"]["status"],
                    "task_home_review_acceptance_trial": report["items"]["task_home_review_acceptance_trial"]["status"],
                    "base_acceptance_attempted": report["base_acceptance_attempted"],
                    "task_home_acceptance_attempted": report["task_home_acceptance_attempted"],
                }
                if (
                    not allow_jog_requested
                    or not allow_base_home_accept
                    or any(accepted_trials[name] != "PASS" for name in (
                        "base_acceptance_trial", "task_home_review_acceptance_trial"
                    ))
                    or not accepted_trials["base_acceptance_attempted"]
                    or not accepted_trials["task_home_acceptance_attempted"]
                ):
                    fail(
                        active_check,
                        "Complete cycles require completed guarded-jog and Base/Home acceptance trials.",
                        acceptance_prerequisites=accepted_trials,
                    )
                widget._configureRobotSimulationShellSubstep(3)
                widget._updateStep6PlanningUi()
                _show_step63_view(panel, 2, 0)
                if not panel.checkPreEntryIKButton.enabled:
                    fail(active_check, "Current PreEntry IK diagnostic control is disabled.")
                try:
                    _modal_guarded_click(
                        report, evidence_dir, run_id, panel.checkPreEntryIKButton,
                        "complete-cycle-preentry-ik",
                    )
                except UnexpectedModalError as exc:
                    fail(active_check, f"PreEntry IK raised a modal: {exc.dialog_text}")
                _wait_until(lambda: not bool(getattr(widget, "_workflowActionBusy", False)), 600.0)
                _process_events(0.1)
                try:
                    cycle_evidence = run_complete_cycles(
                        widget,
                        panel,
                        facade,
                        process_events=_process_events,
                        capture_callback=lambda stage: _capture(
                            report, evidence_dir, run_id, f"complete-cycle-{stage}"
                        ),
                        joint_names=JOINT_NAMES,
                        cycles=2,
                        click_guard=lambda button, name: _modal_guarded_click(
                            report, evidence_dir, run_id, button, f"complete-cycle-{name}"
                        ),
                    )
                except Exception as exc:
                    cycle_evidence = getattr(exc, "evidence", None)
                    _retain_complete_cycle_probe_counts(report, cycle_evidence)
                    fail(
                        active_check,
                        f"{type(exc).__name__}: {exc}",
                        acceptance_prerequisites=accepted_trials,
                        probe_evidence=cycle_evidence,
                    )
                _retain_complete_cycle_probe_counts(report, cycle_evidence)
                if not _complete_cycles_passed(cycle_evidence):
                    fail(
                        active_check,
                        "Complete-cycle probe returned missing or incomplete cycle evidence.",
                        acceptance_prerequisites=accepted_trials,
                        probe_evidence=cycle_evidence,
                    )
                _record(report, active_check, "PASS", probe_evidence=cycle_evidence)
            else:
                _record(
                    report,
                    "complete_cycles",
                    "NOT_RUN",
                    reason="DENTOBOT_HEADED_COMPLETE_CYCLES is unset or '0'.",
                )

            if full_chain_opt_in:
                active_check = "full_chain_interruption"
                widget._configureRobotSimulationShellSubstep(3)
                widget._updateStep6PlanningUi()
                _show_step63_view(panel, 2, 0)
                if not panel.checkPreEntryIKButton.enabled:
                    fail(active_check, "Current PreEntry IK diagnostic control is disabled.")
                try:
                    _modal_guarded_click(
                        report, evidence_dir, run_id, panel.checkPreEntryIKButton,
                        "chain-preentry-ik",
                    )
                except UnexpectedModalError as exc:
                    fail(active_check, f"PreEntry IK raised a modal: {exc.dialog_text}")
                _process_events(0.1)
                try:
                    chain_evidence = run_full_chain_interruption_probe(
                        widget, panel, facade,
                        lambda stage: _capture(
                            report, evidence_dir, run_id, f"chain-{stage}"
                        ),
                        _process_events, _wait_until,
                        click_guard=lambda button, name: _modal_guarded_click(
                            report, evidence_dir, run_id, button, f"chain-{name}"
                        ),
                    )
                except Exception as exc:
                    _retain_full_chain_probe_counts(
                        report, getattr(exc, "evidence", None)
                    )
                    probe_failure_evidence = getattr(exc, "evidence", None)
                    report["drilling_truncation"] = getattr(facade, "drillingTruncation", None)
                    if (os.environ.get("DENTOBOT_HEADED_P1_STRAIGHT_PATH_CHECK", "") == "1"
                            and isinstance(probe_failure_evidence, dict)):
                        probe_failure_evidence["p1_straight_path_checks"] = (
                            _p1_straight_path_checks(logic, facade, parameter_node,
                                                     probe_failure_evidence)
                        )
                    fail(
                        active_check,
                        f"{type(exc).__name__}: {exc}",
                        probe_evidence=probe_failure_evidence,
                    )
                _retain_full_chain_probe_counts(report, chain_evidence)
                report["drilling_truncation"] = getattr(facade, "drillingTruncation", None)
                _record(report, active_check, "PASS", probe_evidence=chain_evidence)
            else:
                _record(report, "full_chain_interruption", "NOT_RUN",
                        reason="DENTOBOT_HEADED_FULL_CHAIN is unset or '0'.")

            if output_case_path is not None:
                active_check = "profile_migration_recovery_before_save"
                _ensure_current_home_workspace_task(
                    widget, panel, logic, parameter_node, facade, case_path, case_hash,
                    report, evidence_dir, run_id, phase="before_save",
                    check_name=active_check,
                    skip_reason=(
                        "Taskless draft-only mode preserves its read-only checkpoint."
                        if draft_only else None
                    ),
                )
                widget._updateStep6PlanningUi()
                _process_events(0.1)
                planning_controls = {
                    "plan_approach_enabled": bool(panel.planApproachButton.enabled),
                    "compare_planners_enabled": bool(panel.comparePlannersButton.enabled),
                    "status_text": str(panel.confirmationStatusLabel.text),
                }
                report[active_check]["planning_controls"] = planning_controls
                _write_report(report)
                if not all(
                    planning_controls[name]
                    for name in (
                        "plan_approach_enabled",
                        "compare_planners_enabled",
                    )
                ):
                    fail(
                        active_check,
                        "Current Home, workspace, reviewed limits, and task confirmation "
                        "did not enable the phased planning controls.",
                        planning_controls=planning_controls,
                    )
                active_check = "save_current_case"
                unpassed = _unpassed_selected_checks(report["items"])
                if unpassed:
                    fail(
                        active_check,
                        "Cannot save the current case because selected checks did not pass.",
                        output_path=str(output_case_path),
                        unpassed_checks=unpassed,
                    )
                try:
                    save_evidence = _save_current_case(
                        widget, output_case_path, case_path, case_hash
                    )
                except Exception as exc:
                    fail(
                        active_check,
                        f"{type(exc).__name__}: {exc}",
                        output_path=str(output_case_path),
                        source_relationship={
                            "source_path": str(case_path),
                            "source_sha256": case_hash,
                        },
                    )
                report["saved_case"] = True
                _record(report, active_check, "PASS", **save_evidence)
            outcome = "PASS"

    except LookupError as exc:
        outcome = "PARTIAL"
        message = str(exc)
        if report["items"][active_check]["status"] == "NOT_RUN":
            _record(report, active_check, "NOT_RUN", reason=message)
        complete_not_run(CHECK_NAMES, message)
    except Exception as exc:
        outcome = "FAILED"
        message = f"{type(exc).__name__}: {exc}"
        if report["items"][active_check]["status"] == "NOT_RUN":
            _record(report, active_check, "FAIL", reason=message)
        complete_not_run(CHECK_NAMES, f"Stopped after first failure: {message}")

    report["status"] = outcome
    report["failure_or_stop_reason"] = message or None
    report["completed_at_utc"] = _utc_now()
    report["screenrecording"] = {
        "status": "external_wrapper_required",
        "scope": "complete Slicer process",
    }
    _write_report(report)
    print(f"DENTOBOT_STEP6_HEADED_REVIEW_{outcome}", flush=True)
    if message:
        print(message, file=sys.stderr, flush=True)
    slicer.util.exit(0 if outcome in {"PASS", "PARTIAL"} else 1)
    return 0 if outcome in {"PASS", "PARTIAL"} else 1


try:
    run()
except Exception as exc:
    print(f"DENTOBOT_STEP6_HEADED_REVIEW_SETUP_FAILED: {type(exc).__name__}: {exc}",
          file=sys.stderr, flush=True)
    slicer.util.exit(1)
