"""Callable headed probe for Step 6 manual-record export and historical replay.

This helper is deliberately not auto-executed. Call it on Slicer's UI thread
with the workflow widget, its simulation panel, a private existing run
directory, and a callback accepting one stage label. It uses the production
export/import/display owners and never invokes planning, guard, preview, or ROS
bridge actions.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from collections.abc import Mapping
from pathlib import Path


class HistoricalRecordProbeError(RuntimeError):
    """The headed manual-record probe could not produce complete evidence."""


def _require_run_dir(run_dir: Path) -> Path:
    if not isinstance(run_dir, Path) or not run_dir.is_absolute():
        raise HistoricalRecordProbeError("run_dir must be an absolute pathlib.Path")
    try:
        resolved = run_dir.resolve(strict=True)
        info = run_dir.lstat()
    except OSError as exc:
        raise HistoricalRecordProbeError("run_dir must already exist") from exc
    if run_dir.is_symlink() or resolved != run_dir or not stat.S_ISDIR(info.st_mode):
        raise HistoricalRecordProbeError("run_dir must be a real directory, not a symlink")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise HistoricalRecordProbeError("run_dir must be owned by the current user")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise HistoricalRecordProbeError("run_dir permissions must be private (0700 or stricter)")
    return resolved


def _owner_globals(owner) -> dict:
    function = getattr(owner, "__func__", owner)
    namespace = getattr(function, "__globals__", None)
    if not isinstance(namespace, dict):
        raise HistoricalRecordProbeError("production UI owner has no inspectable module globals")
    return namespace


def _invoke_with_dialog_paths(owner, namespace, *, save_path=None, open_path=None):
    qt_module = namespace.get("qt")
    if qt_module is None or not hasattr(qt_module, "QFileDialog"):
        raise HistoricalRecordProbeError("production UI owner has no Qt file-dialog API")

    class RedirectedDialogs:
        @staticmethod
        def getSaveFileName(*_args, **_kwargs):
            if save_path is None:
                raise HistoricalRecordProbeError("unexpected save-file dialog request")
            return str(save_path)

        @staticmethod
        def getOpenFileName(*_args, **_kwargs):
            if open_path is None:
                raise HistoricalRecordProbeError("unexpected open-file dialog request")
            return str(open_path)

    class DialogProxy:
        QFileDialog = RedirectedDialogs

        def __getattr__(self, name):
            return getattr(qt_module, name)

    prior_qt = namespace["qt"]
    try:
        # Replace only this owner module's `qt` reference. The shared PythonQt
        # module and every other module's file-dialog API remain untouched.
        namespace["qt"] = DialogProxy()
        owner()
    finally:
        namespace["qt"] = prior_qt


def _require_ui_thread(namespace) -> None:
    slicer_module = namespace.get("slicer")
    qt_module = namespace.get("qt")
    app = getattr(slicer_module, "app", None)
    qthread = getattr(qt_module, "QThread", None)
    current = getattr(qthread, "currentThread", None)
    app_thread = getattr(app, "thread", None)
    if not callable(current) or not callable(app_thread):
        raise HistoricalRecordProbeError("cannot verify Slicer UI-thread ownership")
    try:
        if current() != app_thread():
            raise HistoricalRecordProbeError("probe must run synchronously on Slicer's UI thread")
    except HistoricalRecordProbeError:
        raise
    except Exception as exc:
        raise HistoricalRecordProbeError("could not verify Slicer UI-thread ownership") from exc


def _accepted_joints(panel, joint_names) -> dict[str, float]:
    value = getattr(panel, "_manualJogAcceptedJointPositionsSi", None)
    if not isinstance(value, Mapping) or set(value) != set(joint_names):
        raise HistoricalRecordProbeError("accepted J1–J5 snapshot is unavailable")
    try:
        snapshot = {name: float(value[name]) for name in joint_names}
    except (TypeError, ValueError, OverflowError) as exc:
        raise HistoricalRecordProbeError("accepted J1–J5 snapshot is invalid") from exc
    if not all(math.isfinite(number) for number in snapshot.values()):
        raise HistoricalRecordProbeError("accepted J1–J5 snapshot is non-finite")
    return snapshot


def _require_import_status(panel) -> None:
    label = getattr(panel, "manualRecordImportStatusLabel", None)
    property_reader = getattr(label, "property", None)
    if not callable(property_reader) or property_reader("dentobotState") != "ok":
        raise HistoricalRecordProbeError("historical record display/replay owner did not report success")


def _authority_snapshot(facade) -> tuple[object, dict[str, object]]:
    try:
        plan = facade.motionPlan
        phase = str(facade.currentPreviewPhase)
        preview_active = bool(facade.previewActive)
        guarded_preview_active = bool(facade._guarded_preview_active)
        preview_index = int(facade.previewIndex)
        return_home_required = bool(facade.returnHomeRequired)
    except Exception as exc:
        raise HistoricalRecordProbeError("route/preview authority snapshot is unavailable") from exc
    phases = getattr(plan, "waypoint_phases", ()) if plan is not None else ()
    try:
        phase_count = len(phases)
    except TypeError:
        phase_count = None
    return plan, {
        "motion_plan_present": plan is not None,
        "motion_plan_object_id": id(plan) if plan is not None else None,
        "motion_plan_success": getattr(plan, "success", None) if plan is not None else None,
        "motion_plan_task_fingerprint": (
            getattr(plan, "task_fingerprint", None) if plan is not None else None
        ),
        "motion_plan_phase_count": phase_count,
        "preview_active": preview_active,
        "guarded_preview_active": guarded_preview_active,
        "preview_phase": phase,
        "preview_index": preview_index,
        "return_home_required": return_home_required,
    }


def _capture(capture_callback, stage: str):
    value = capture_callback(stage)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_capture_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _capture_value(item) for key, item in value.items()}
    return repr(value)


def _capture_value(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _capture_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_capture_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_step6_historical_record_probe(widget, panel, run_dir: Path, capture_callback):
    """Export, reopen and step through one historical Step 6 manual record.

    ``capture_callback(stage)`` may save headed screenshots and return their
    paths or other small evidence. Recognized stages are ``before_export``,
    ``after_export``, ``after_import`` and ``after_event_step``.
    """

    run_dir = _require_run_dir(run_dir)
    if not callable(capture_callback):
        raise HistoricalRecordProbeError("capture_callback must be callable")
    if getattr(widget, "_robotSimulationPanel", None) is not panel:
        raise HistoricalRecordProbeError("panel is not the widget's production simulation panel")
    facade = getattr(widget, "_robotWorkflowFacade", None)
    export_owner = getattr(widget, "_onStep6ExportManualRecord", None)
    import_owner = getattr(widget, "_onStep6ImportManualRecord", None)
    if not callable(export_owner) or not callable(import_owner) or facade is None:
        raise HistoricalRecordProbeError("production export/import UI owners are unavailable")

    export_globals = _owner_globals(export_owner)
    import_globals = _owner_globals(import_owner)
    if export_globals is not import_globals:
        raise HistoricalRecordProbeError("export/import owners do not share one scoped dialog namespace")
    _require_ui_thread(export_globals)
    joint_names = tuple(export_globals.get("JOINT_NAMES", ()))
    if len(joint_names) != 5:
        raise HistoricalRecordProbeError("production J1–J5 joint order is unavailable")

    json_path = run_dir / "step6-manual-record-probe.json"
    report_path = run_dir / "step6-manual-record-probe.report.txt"
    for path in (json_path, report_path):
        if path.exists() or path.is_symlink():
            raise HistoricalRecordProbeError("probe refuses to overwrite existing evidence")

    accepted_before = _accepted_joints(panel, joint_names)
    plan_before, authority_before = _authority_snapshot(facade)
    captures = [{"stage": "before_export", "result": _capture(capture_callback, "before_export")}]

    _invoke_with_dialog_paths(export_owner, export_globals, save_path=json_path)
    for path in (json_path, report_path):
        if path.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
            raise HistoricalRecordProbeError("production export did not create both run-local artifacts")
        if path.resolve(strict=True).parent != run_dir:
            raise HistoricalRecordProbeError("production export escaped the private run directory")
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HistoricalRecordProbeError("exported manual-record JSON is unreadable") from exc
    records = [payload] if isinstance(payload, Mapping) else payload
    if not isinstance(records, list) or not records:
        raise HistoricalRecordProbeError("export did not contain a record collection")
    event_record_index = next(
        (
            index
            for index, record in enumerate(records)
            if isinstance(record, Mapping)
            and isinstance(record.get("events"), list)
            and any(
                isinstance(event, Mapping) and event.get("tcp_point_ras_mm") is not None
                for event in record["events"]
            )
        ),
        None,
    )
    if event_record_index is None:
        raise HistoricalRecordProbeError("export contains no manual record with a TCP sample")
    selected_record = records[event_record_index]
    if not selected_record.get("record_fingerprint") or not selected_record.get("schema_version"):
        raise HistoricalRecordProbeError("event-bearing record lacks schema provenance")
    captures.append({"stage": "after_export", "result": _capture(capture_callback, "after_export")})

    _invoke_with_dialog_paths(import_owner, import_globals, open_path=json_path)
    loaded_records = getattr(panel, "_manualSimulationRecords", None)
    if not isinstance(loaded_records, (tuple, list)):
        raise HistoricalRecordProbeError("production import owner did not load historical records")
    loaded_fingerprints = [
        item.get("record_fingerprint") if isinstance(item, Mapping) else None
        for item in loaded_records
    ]
    try:
        loaded_index = loaded_fingerprints.index(selected_record["record_fingerprint"])
    except ValueError as exc:
        raise HistoricalRecordProbeError("exported event-bearing record was not reopened") from exc
    selector = getattr(panel, "manualSimulationRecordComboBox", None)
    event_list = getattr(panel, "manualSimulationEventList", None)
    step_event = getattr(panel, "_stepManualSimulationEvent", None)
    if selector is None or event_list is None or not callable(step_event):
        raise HistoricalRecordProbeError("production historical replay controls are unavailable")
    selector.setCurrentIndex(loaded_index)
    if int(selector.currentIndex) != loaded_index:
        raise HistoricalRecordProbeError("could not select the reopened event-bearing record")
    _require_import_status(panel)
    captures.append({"stage": "after_import", "result": _capture(capture_callback, "after_import")})

    event_list.setCurrentRow(-1)
    if int(event_list.currentRow) != -1:
        raise HistoricalRecordProbeError("could not clear the event selection before replay step")
    step_event(1)
    event_index = int(event_list.currentRow)
    events = selected_record["events"]
    if not 0 <= event_index < len(events):
        raise HistoricalRecordProbeError("production replay did not select a saved event")
    displayed_event = events[event_index]
    details_widget = getattr(panel, "manualSimulationEventDetailsText", None)
    plain_text = getattr(details_widget, "toPlainText", None)
    displayed_text = plain_text() if callable(plain_text) else ""
    expected_heading = "Historical event {} of {}".format(event_index + 1, len(events))
    if expected_heading not in displayed_text or "Step-through selection only" not in displayed_text:
        raise HistoricalRecordProbeError("production event-step display evidence is unavailable")
    _require_import_status(panel)
    captures.append({"stage": "after_event_step", "result": _capture(capture_callback, "after_event_step")})

    accepted_after = _accepted_joints(panel, joint_names)
    plan_after, authority_after = _authority_snapshot(facade)
    accepted_unchanged = accepted_before == accepted_after
    authority_unchanged = plan_before is plan_after and authority_before == authority_after
    if not accepted_unchanged:
        raise HistoricalRecordProbeError("historical replay changed accepted J1–J5")
    if not authority_unchanged:
        raise HistoricalRecordProbeError("historical replay changed route/preview authority")

    event_order = [
        {
            "index": index,
            "kind": str(event.get("kind", "")),
            "monotonic_ns": event.get("monotonic_ns"),
        }
        for index, event in enumerate(selected_record["events"])
    ]
    return {
        "status": "PASS",
        "record_json": str(json_path),
        "record_report": str(report_path),
        "artifact_sha256": {
            "json": _sha256(json_path),
            "report": _sha256(report_path),
        },
        "record": {
            "schema_version": selected_record["schema_version"],
            "schema_fingerprint": selected_record["record_fingerprint"],
            "identity": dict(selected_record.get("identity") or {}),
            "event_order": event_order,
            "event_count": len(event_order),
        },
        "replay": {
            "record_index": loaded_index,
            "event_index": event_index,
            "event_kind": str(displayed_event.get("kind", "")),
            "authority": "historical_display_only",
        },
        "accepted_j1_j5": {
            "before": accepted_before,
            "after": accepted_after,
            "unchanged": accepted_unchanged,
        },
        "route_preview_authority": {
            "before": authority_before,
            "after": authority_after,
            "unchanged": authority_unchanged,
            "historical_record_authority": "display_only",
        },
        "captures": captures,
        "production_owners": {
            "export": getattr(export_owner, "__name__", type(export_owner).__name__),
            "import": getattr(import_owner, "__name__", type(import_owner).__name__),
        },
    }
