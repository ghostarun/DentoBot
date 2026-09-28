"""Headed, bounded Step 6 GUI review for an approved current checkout.

The runner never saves the loaded case. ROS/scene synchronization and one
0.1-degree J1 jog require both the explicit jog flag and an exact native build
preflight. Unknown or rejected jog outcomes stop the run without retry. The
taskless-draft mode stops after its read-only draft check.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
from pathlib import Path
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

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
)
from DENTOStep6Planning import (  # noqa: E402
    default_task_joint_limits_from_urdf,
    joint_limit_margin_evidence,
)
from DENTOStep6State import JOINT_NAMES  # noqa: E402
from dentobot_workflow.offline_placement_status import (  # noqa: E402
    EXPECTED_ROBOT_LINK_COUNT,
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
SOURCE_FILES = (
    "DENTOWorkflow/Resources/Python/DENTORobotSimulationPanel.py",
    "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py",
    "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot.py",
    "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot_shell.py",
    "Testing/run_dentobot_manual_jog_headless.py",
)
CHECK_NAMES = (
    "checkout_and_case_provenance",
    "case_opened_and_step6_ui",
    "saved_case_ros_readiness_not_restored",
    "simulation_robot_models_loaded",
    "planning_context_imported",
    "base_controls_and_accepted_status",
    "draft_state_control_visible",
    "native_version_preflight",
    "simulation_ros_connect_and_scene_readback",
    "draft_state_read_only",
    "invalid_out_of_reviewed_range_draft",
    "single_guarded_j1_jog",
    "historical_record_export_reopen",
    "base_stage_and_cancel",
    "base_acceptance_trial",
    "task_home_review_acceptance_trial",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite_vector(values) -> dict[str, float]:
    if not isinstance(values, Mapping) or set(values) != set(JOINT_NAMES):
        raise ValueError("Joint state must contain exactly J1–J5.")
    result = {name: float(values[name]) for name in JOINT_NAMES}
    if not all(math.isfinite(value) for value in result.values()):
        raise ValueError("Joint state contains a non-finite value.")
    return result


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


def _capture_screenshots(label: str, evidence_dir: Path) -> dict[str, str]:
    window = slicer.util.mainWindow()
    if window is None:
        raise RuntimeError("Slicer main window is unavailable for required evidence.")
    window.show()
    old_title = str(window.windowTitle)
    window.windowTitle = f"DENTOBOT Step 6 review — {label}"
    try:
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
        return {"ui": ui_path.name, "viewport": viewport_path.name, "captured_at_utc": _utc_now()}
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


def _write_report(report: dict[str, object]) -> None:
    path = Path(str(report["report_path"]))
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(_json_safe(report), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _capture(report, evidence_dir: Path, run_id: str, key: str) -> dict[str, str]:
    paths = _capture_screenshots(f"{run_id}-{key}", evidence_dir)
    report["screenshots"][key] = paths
    _write_report(report)
    return paths


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


def _target_j1(logic, parameter_node, accepted: dict[str, float]):
    for sign in (1, -1):
        target = dict(accepted)
        target[JOINT_NAMES[0]] += sign * math.radians(ACCEPTED_DELTA_DEG)
        if _within_both_limits(logic, parameter_node, target) is not None:
            return target, f"J1 { '+' if sign > 0 else '-' } {ACCEPTED_DELTA_DEG:g} degree"
    raise RuntimeError("J1 +/- 0.1 degree is outside a current reviewed or mechanical limit.")


def run() -> int:
    output_text = os.environ.get("DENTOBOT_HEADED_EVIDENCE_DIR", "").strip()
    if not output_text:
        raise RuntimeError("Set DENTOBOT_HEADED_EVIDENCE_DIR to a private evidence directory.")
    allow_base_home_accept = (
        os.environ.get("DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT", "") == "1"
    )
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
        "simulation_only": True,
        "hardware_execution": False,
        "planner_calls": 0,
        "preview_started": False,
        "route_authority": "none",
        "review_mode": None,
        "taskless_draft_only": False,
        "historical_record_reopen_opt_in": False,
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
    _write_report(report)
    active_check = "checkout_and_case_provenance"
    outcome = "FAILED"
    message = ""

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
        report["checkout"] = _checkout_evidence()
        draft_only = _draft_only_requested()
        invalid_draft_review = _invalid_draft_review_requested()
        record_reopen = _historical_record_reopen_requested()
        allow_jog_requested = os.environ.get("DENTOBOT_HEADED_ALLOW_JOG", "") == "1"
        _validate_record_reopen_prerequisites(
            record_reopen, allow_jog_requested, draft_only
        )
        report["review_mode"] = (
            "taskless_draft_only" if draft_only
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
        load_button = widget.ui.loadRobotModelButton
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
            "accepted_base_status": _visible(widget.ui.step6MountLockStatusLabel),
        }
        if not all(visible_controls.values()):
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

        active_check = "draft_state_control_visible"
        widget._configureRobotSimulationShellSubstep(3)
        _process_events(0.1)
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

        if (not allow_jog and not draft_only and not invalid_draft_review) or native is None:
            reasons = []
            if not allow_jog and not draft_only and not invalid_draft_review:
                reasons.append(
                    "No guarded-jog, taskless-draft, or invalid-draft review opt-in is enabled."
                )
            if native is None:
                reasons.append("Exact native source/binary preflight is unavailable.")
            reason = " ".join(reasons)
            complete_not_run(
                ("simulation_ros_connect_and_scene_readback", "draft_state_read_only",
                 "invalid_out_of_reviewed_range_draft", "single_guarded_j1_jog",
                 "historical_record_export_reopen", "base_stage_and_cancel"),
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
            _capture(report, evidence_dir, run_id, "ros-scene-object-readback")
            _record(report, active_check, "PASS", connected=True, simulation_only=True,
                    scene=scene, screenshot=report["screenshots"]["ros-scene-object-readback"])

            active_check = "draft_state_read_only"
            widget._configureRobotSimulationShellSubstep(3)
            _process_events(0.1)
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
                base_acceptance_owner = widget.ui.lockRobotBaseMountButton
                if not base_acceptance_owner.enabled:
                    fail(active_check, "Existing Accept Base owner is not enabled for the staged candidate.",
                         stage_result=base_acceptance_stage_details)
                report["base_acceptance_attempted"] = True
                _write_report(report)
                base_acceptance_owner.click()
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
                            base_after_details.get("acceptedMatrixWorldRasMm"), base_matrix
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
                    accepted_matrix_unchanged=True,
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
