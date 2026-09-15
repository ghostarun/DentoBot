"""Generate current single-target Step 4A-to-5C DENTOBOT cases.

Simulation/offline only.  The source package is opened read-only, derived
planning geometry is regenerated for each requested FDI target, and each
current package is saved and reopened before the next target is attempted.
Diagnostic screenshots are SHA-linked sidecars because case-bundle integrity
deliberately rejects untracked archive attachments.
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

import numpy as np
import qt
import slicer
import vtk
from vtk.util.numpy_support import vtk_to_numpy


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
for path in (HELPERS, ROOT / "DENTOWorkflow"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from DENTOCaseBundle import validate_case_bundle  # noqa: E402
from DENTOGuideGeometry import normalize_target_docking_parameters  # noqa: E402


SOURCE = Path(
    os.environ.get(
        "DENTOBOT_STAGE6_SOURCE",
        "/workspace/data/Slicer_Saved/SampleStudy1/"
        "dentobot-case-13sept.dentocase",
    )
)
OUTPUT_ROOT = Path(
    os.environ.get(
        "DENTOBOT_STAGE6_GENERATION_ROOT",
        "/workspace/data/Slicer_Saved/SampleStudy1",
    )
)
RUN_ID = os.environ.get("DENTOBOT_STAGE6_RUN_ID", "").strip() or (
    f"run-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-"
    f"{time.time_ns() % 1_000_000_000:09d}"
)
TARGET_FDI = tuple(
    value.strip().upper().removeprefix("FDI")
    for value in os.environ.get(
        "DENTOBOT_STAGE6_TARGETS", "31"
    ).split(",")
    if value.strip()
)


def process_events(seconds: float = 0.25) -> None:
    deadline = time.monotonic() + float(seconds)
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _target_key(target_fdi: str) -> str:
    return str(target_fdi).strip().upper().removeprefix("FDI")


def _target_directory(target_fdi: str) -> Path:
    return OUTPUT_ROOT / f"FDI{_target_key(target_fdi)}" / RUN_ID


def _campaign_directory() -> Path:
    return OUTPUT_ROOT / "central-incisors" / RUN_ID


def _case_path(target_fdi: str) -> Path:
    return _target_directory(target_fdi) / f"FDI{_target_key(target_fdi)}-step5c.dentocase"


def _diagnostic_path(target_fdi: str) -> Path:
    return (
        _target_directory(target_fdi)
        / "diagnostics"
        / f"FDI{_target_key(target_fdi)}-generation-diagnostic.json"
    )


def _write_target_diagnostic(target_fdi: str, payload: dict) -> Path:
    path = _diagnostic_path(target_fdi)
    path.parent.mkdir(parents=True, exist_ok=True)
    diagnostic = {
        "schemaVersion": "1.0",
        "kind": "stage6-target-generation",
        "targetFdi": f"FDI{_target_key(target_fdi)}",
        **payload,
    }
    path.write_text(
        json.dumps(diagnostic, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def _capture_screenshot_evidence(widget, target_fdi: str, label: str) -> dict:
    """Best-effort UI/viewport evidence that never hides the original failure."""

    directory = _target_directory(target_fdi) / "screenshots"
    result = {"directory": str(directory), "screenshots": [], "capture_errors": []}
    try:
        directory.mkdir(parents=True, exist_ok=True)
        ui_path = directory / f"{label}-ui.png"
        host = slicer.util.mainWindow() or getattr(widget, "_uiWidget", None)
        if host is None:
            raise RuntimeError("Slicer UI is unavailable")
        host.show()
        process_events(0.15)
        pixmap = host.grab()
        if pixmap.isNull() or not pixmap.save(str(ui_path)):
            raise RuntimeError(f"could not capture UI: {ui_path}")
        result["screenshots"].append(str(ui_path))
    except Exception as exc:
        result["capture_errors"].append(f"ui: {type(exc).__name__}: {exc}")
    try:
        viewport_path = directory / f"{label}-viewport.png"
        view = slicer.app.layoutManager().threeDWidget(0).threeDView()
        view.show()
        parameter = getattr(widget, "_parameterNode", None)
        focus = (
            getattr(parameter, "finalPrintableTemplateModel", None)
            or getattr(parameter, "targetDockingAssemblyModel", None)
        )
        if focus and focus.GetPolyData() and focus.GetPolyData().GetNumberOfPoints():
            bounds = [0.0] * 6
            focus.GetRASBounds(bounds)
            span = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4])
            if math.isfinite(span) and span > 1.0e-6:
                center = [(bounds[2 * axis] + bounds[2 * axis + 1]) / 2.0 for axis in range(3)]
                camera = view.cameraNode().GetCamera()
                camera.SetFocalPoint(*center)
                camera.SetPosition(center[0] + span, center[1] - span, center[2] + span)
                camera.SetViewUp(0.0, 0.0, 1.0)
                camera.ParallelProjectionOn()
                camera.SetParallelScale(max(5.0, 0.8 * span))
        view.forceRender()
        slicer.util.forceRenderAllViews()
        process_events(0.25)
        host = slicer.util.mainWindow()
        if host:
            origin = view.mapTo(host, qt.QPoint(0, 0))
            view_size = view.size
            if callable(view_size):
                view_size = view_size()
            pixmap = host.grab(qt.QRect(origin, view_size))
        else:
            pixmap = view.grab()
        if pixmap.isNull() or not pixmap.save(str(viewport_path)):
            capture_filter = vtk.vtkWindowToImageFilter()
            capture_filter.SetInput(view.renderWindow())
            capture_filter.ReadFrontBufferOff()
            capture_filter.Update()
            writer = vtk.vtkPNGWriter()
            writer.SetFileName(str(viewport_path))
            writer.SetInputConnection(capture_filter.GetOutputPort())
            writer.Write()
        if not viewport_path.is_file():
            raise RuntimeError(f"could not capture viewport: {viewport_path}")
        result["screenshots"].append(str(viewport_path))
    except Exception as exc:
        result["capture_errors"].append(f"viewport: {type(exc).__name__}: {exc}")
    return result


def _map_point(matrix, point) -> list[float]:
    mapped = matrix.MultiplyPoint((*[float(value) for value in point], 1.0))
    scale = float(mapped[3])
    require(math.isfinite(scale) and abs(scale) > 1.0e-12, "invalid point transform")
    result = [float(value) / scale for value in mapped[:3]]
    require(all(math.isfinite(value) for value in result), "invalid point transform")
    return result


def _crown_center_entry(logic, segmentation, segment_id: str) -> tuple[list[float], dict]:
    surface = logic._getClosedSurfaceCopy(segmentation, segment_id)
    points_data = surface.GetPoints().GetData() if surface.GetPoints() else None
    require(points_data is not None, f"FDI{segment_id} has no closed-surface points")
    points = np.asarray(vtk_to_numpy(points_data), dtype=float)
    require(points.ndim == 2 and points.shape[1] == 3 and len(points) >= 8,
            f"FDI{segment_id} surface is unusable")
    require(np.all(np.isfinite(points)), f"FDI{segment_id} surface is non-finite")
    centered = points - np.mean(points, axis=0)
    _eigenvalues, eigenvectors = np.linalg.eigh(centered.T @ centered)
    axis = np.asarray(eigenvectors[:, int(np.argmax(_eigenvalues))], dtype=float)
    axis /= float(np.linalg.norm(axis))
    if axis[2] < 0.0:
        axis *= -1.0
    projections = centered @ axis
    threshold = float(np.quantile(projections, 0.84))
    cap = points[projections >= threshold]
    require(len(cap) >= 3, f"FDI{segment_id} crown cap is too small")
    cap_center = np.mean(cap, axis=0)
    entry = points[int(np.argmin(np.linalg.norm(points - cap_center, axis=1)))]
    return [float(value) for value in entry], {
        "principal_axis_ras": [float(value) for value in axis],
        "cap_threshold": threshold,
        "cap_point_count": int(len(cap)),
        "entry_ras_mm": [float(value) for value in entry],
    }


def _remove_derived_planning_nodes(logic, parameter) -> None:
    """Clear source checkpoints without touching anatomy or Case Foundation."""

    parameter.trajectoryLine = None
    parameter.assistedTrajectoryEntries = None
    parameter.targetToothBoundsRoi = None
    parameter.targetDockingReferencePlane = None
    parameter.targetDockingAssemblyModel = None
    parameter.draftTemplateSupportModel = None
    parameter.templateSupportBoundaryCurve = None
    parameter.templateSupportBoundaryPlane = None
    parameter.visibleTemplateSupportModel = None
    parameter.templateInsertionDirection = None
    parameter.templateUndercutSurfaceModel = None
    parameter.templateUndercutBlockoutModel = None
    parameter.patientContactShellModel = None
    parameter.templateDockingAssemblyModel = None
    parameter.templateDockingClearanceModel = None
    parameter.templateDockingReinforcementModel = None
    parameter.templateDockingChannelsModel = None
    parameter.finalPrintableTemplateModel = None
    parameter.templateSupportToothSegmentIdsJson = "[]"
    parameter.step6TrajectoryRegistryJson = ""

    model_roles = {
        "TemplateSupportDraft",
        "VisibleTemplateSupportSurface",
        "TemplateSupportBoundaryBridge",
        "TemplateInsertionDirection",
        "TemplateUndercutSurface",
        "TemplateUndercutBlockout",
        "PatientContactShell",
        "TemplateFittingSurface",
        "TemplateHollowCandidate",
        "TemplateDockingAssembly",
        "TemplateDockingClearance",
        "TemplateDockingReinforcement",
        "TemplateDockingChannels",
        "FinalPrintableTemplate",
        "TargetDockingAssembly",
    }
    markup_roles = {
        "AssistedTrajectoryEntries",
        "TemplateSupportBoundary",
        "TemplateSupportBoundaryPlane",
        "TargetDockingReferencePlane",
        "TargetDockingMeasurement",
    }
    nodes = []
    for class_name in (
        "vtkMRMLMarkupsLineNode",
        "vtkMRMLMarkupsFiducialNode",
        "vtkMRMLMarkupsROINode",
        "vtkMRMLMarkupsClosedCurveNode",
        "vtkMRMLMarkupsPlaneNode",
        "vtkMRMLModelNode",
    ):
        nodes.extend(list(slicer.util.getNodesByClass(class_name)))
    for node in nodes:
        if logic.isDentobotTrajectoryNode(node) or node.GetAttribute(
            "DENTOBOT.BoundsRole"
        ) == "TargetToothAABB":
            slicer.mrmlScene.RemoveNode(node)
            continue
        if node.GetAttribute("DENTOBOT.ModelRole") in model_roles or node.GetAttribute(
            "DENTOBOT.MarkupsRole"
        ) in markup_roles:
            slicer.mrmlScene.RemoveNode(node)


def _apply_saved_fdi31_defaults(parameter) -> None:
    """Restore the latest FDI31 Step 4C values; guide bore stays >= 2 mm."""

    values = {
        "targetDockingPatternRadiusMm": 10.0,
        "targetDockingOuterDiameterMm": 3.0,
        "targetDockingBoreDiameterMm": 1.5,
        "targetDockingConnectorDiameterMm": 3.5,
        "targetDockingConnectorThicknessMm": 2.0,
        "targetDockingSharedDepthMm": 5.0,
        "targetDockingYawDeg": 35.0,
        "targetDockingCollisionClearanceMm": 0.5,
        "targetDockingIndividualDepthsEnabled": False,
        "targetDockingDepth1Mm": 5.0,
        "targetDockingDepth2Mm": 5.0,
        "targetDockingDepth3Mm": 5.0,
        "targetDockingDepth4Mm": 5.0,
        "targetDockingMeasurementsVisible": True,
        "targetDockingYawConfirmed": False,
        "templateChannelDiameterMm": 2.0,
        "templateSleeveInnerDiameterMm": 2.0,
        "templateSupportPlaneDepthMm": 4.0,
    }
    was_modifying = parameter.StartModify()
    try:
        for name, value in values.items():
            setattr(parameter, name, value)
    finally:
        parameter.EndModify(was_modifying)


def _support_selection(logic, segmentation, target_record: dict) -> tuple[list[str], dict]:
    target_fdi = str(target_record.get("fdiNumber") or "")
    records = logic.getTargetToothRecords(segmentation)
    by_fdi = {
        str(record.get("fdiNumber") or ""): record
        for record in records
        if record.get("fdiNumber")
    }
    # Preserve the reviewed FDI31 support package when it is available; for
    # the other requested teeth choose the four nearest teeth in the same arch.
    preferred = ("42", "41", "33", "32") if target_fdi == "31" else ()
    if preferred and all(value in by_fdi for value in preferred):
        selected_fdi = list(preferred)
        policy = "latest_saved_fdi31_support_ids"
    else:
        target_arch = logic.dentalArchForFdi(target_fdi)
        candidates = [
            value
            for value in by_fdi
            if value != target_fdi and logic.dentalArchForFdi(value) == target_arch
        ]
        selected_fdi = sorted(
            candidates,
            key=lambda value: (abs(int(value) - int(target_fdi)), int(value)),
        )[:4]
        policy = "nearest_four_same_arch_fdi"
    require(len(selected_fdi) >= 1, f"no same-arch support teeth for FDI{target_fdi}")
    return [by_fdi[value]["segmentId"] for value in selected_fdi], {
        "policy": policy,
        "target_fdi": target_fdi,
        "support_fdi": selected_fdi,
    }


def _set_confirmed_docking(parameter, plane, assembly, yaw: float) -> None:
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for node in (plane, assembly):
        node.SetAttribute("DENTOBOT.OrientationState", "Confirmed")
        node.SetAttribute("DENTOBOT.OrientationConfirmedUtc", timestamp)
    parameter.targetDockingReferencePlane = plane
    parameter.targetDockingAssemblyModel = assembly
    parameter.targetDockingYawDeg = float(yaw)
    parameter.targetDockingYawConfirmed = True


def _activation_preservation(logic, parameter, branch_id: str) -> dict:
    active_before = (
        parameter.trajectoryLine.GetID() if parameter.trajectoryLine else "",
        parameter.targetDockingAssemblyModel.GetID()
        if parameter.targetDockingAssemblyModel
        else "",
        parameter.templateInsertionDirection.GetID()
        if parameter.templateInsertionDirection
        else "",
        parameter.patientContactShellModel.GetID()
        if parameter.patientContactShellModel
        else "",
        parameter.finalPrintableTemplateModel.GetID()
        if parameter.finalPrintableTemplateModel
        else "",
        parameter.step6TrajectoryRegistryJson,
    )
    failed_message = ""
    try:
        logic.activateDentoCasePreparedBranch(parameter, "missing-branch")
    except (RuntimeError, ValueError) as exc:
        failed_message = str(exc)
    require(failed_message, "invalid PreparedBranch activation unexpectedly succeeded")
    active_after_failure = (
        parameter.trajectoryLine.GetID() if parameter.trajectoryLine else "",
        parameter.targetDockingAssemblyModel.GetID()
        if parameter.targetDockingAssemblyModel
        else "",
        parameter.templateInsertionDirection.GetID()
        if parameter.templateInsertionDirection
        else "",
        parameter.patientContactShellModel.GetID()
        if parameter.patientContactShellModel
        else "",
        parameter.finalPrintableTemplateModel.GetID()
        if parameter.finalPrintableTemplateModel
        else "",
        parameter.step6TrajectoryRegistryJson,
    )
    require(
        active_before == active_after_failure,
        "failed PreparedBranch activation changed the active plan",
    )
    logic.activateDentoCasePreparedBranch(parameter, branch_id)
    return {
        "failed_activation_preserved": True,
        "failed_activation_message": failed_message,
        "selected_branch_id": branch_id,
    }


def _step5c_gate(logic, parameter, final_model, verification, final_summary) -> dict:
    """Require the four geometry/identity gates before a case can be saved."""

    checks = {
        str(check.get("name") or ""): str(check.get("result") or "")
        for check in verification.get("checks", [])
        if isinstance(check, dict)
    }
    required_checks = (
        "Four through-open robot-dock bores",
        "Guide union and channel preservation",
        "One connected printable solid",
        "Single current-frame target dock",
        "Watertight manifold topology",
    )
    failed_checks = [name for name in required_checks if checks.get(name) != "PASS"]
    require(
        not failed_checks,
        "Step 5C geometry/identity gate failed: "
        + json.dumps(
            {"failed_checks": failed_checks, "checks": checks},
            sort_keys=True,
        ),
    )
    metrics = final_summary.get("metrics", {})
    require(
        int(metrics.get("occupiedVolumeRegionCount", 0)) == 1,
        "Step 5C requires one connected occupied printable volume",
    )
    require(
        int(metrics.get("channelResidualOccupiedSampleCount", -1)) == 0,
        "Step 5C requires zero residual protected-channel occupancy",
    )
    registry = logic.syncDentoCaseTrajectoryRegistry(parameter)
    branch_id = str(registry.get("selected_branch_id") or "")
    require(
        len(registry.get("prepared_branches", {})) == 1 and branch_id,
        "Step 5C requires exactly one selected PreparedBranch",
    )
    eligibility = logic.evaluatePreparedBranchEligibility(
        parameter,
        branch_id,
        registry=registry,
    )
    require(
        eligibility.get("eligible"),
        "Step 5C PreparedBranch is not current after verification: "
        + json.dumps(eligibility, sort_keys=True, default=str),
    )
    return {
        "required_checks": required_checks,
        "checks": checks,
        "metrics": {
            "occupiedVolumeRegionCount": int(metrics.get("occupiedVolumeRegionCount", 0)),
            "channelResidualOccupiedSampleCount": int(
                metrics.get("channelResidualOccupiedSampleCount", -1)
            ),
            "surfaceRegionCount": int(
                final_summary.get("metrics", {}).get("surfaceRegionCount", 0)
            ),
        },
        "prepared_branch_id": branch_id,
        "prepared_branch_eligibility": eligibility,
    }


def _semantic_snapshot(segmentation, pulp_segment_id: str) -> dict:
    """Read the persisted canonical registry without re-deriving raw names."""

    metrics_text = segmentation.GetAttribute("DENTOBOT.SegmentMetricsJson") or ""
    metrics = json.loads(metrics_text)
    semantic = metrics.get("semantic")
    require(isinstance(semantic, dict), "canonical semantic registry is missing")
    records = semantic.get("segments") or []
    pulp = next(
        (
            record
            for record in records
            if str(record.get("segmentId") or "") == str(pulp_segment_id)
        ),
        None,
    )
    require(pulp is not None, f"semantic registry lost pulp segment {pulp_segment_id}")
    return {
        "schemaVersion": segmentation.GetAttribute("DENTOBOT.SemanticSchemaVersion") or "",
        "status": segmentation.GetAttribute("DENTOBOT.SemanticStatus") or "",
        "fingerprint": segmentation.GetAttribute("DENTOBOT.SemanticFingerprint") or "",
        "pulp": pulp,
    }


def _reopen_diagnostic(logic, parameter, registry=None, eligibility=None) -> dict:
    """Capture the first restore mismatch without changing production state."""

    result = {
        "target_fdi": str(
            getattr(parameter.trajectoryLine, "GetAttribute", lambda _name: "")(
                "DENTOBOT.TargetFdiNumber"
            )
            if parameter.trajectoryLine
            else ""
        ),
        "parameter": {
            "step6BasePlacementStatus": str(parameter.step6BasePlacementStatus or ""),
            "step6BasePlacementRevision": int(parameter.step6BasePlacementRevision),
            "step6PlanningContextImported": bool(parameter.step6PlanningContextImported),
            "step6CaseJawPreparationMode": str(parameter.step6CaseJawPreparationMode or ""),
        },
    }
    try:
        result["foundation"] = logic.evaluateCaseFoundationEligibility(parameter)
    except Exception as exc:
        result["foundation_error"] = f"{type(exc).__name__}: {exc}"
    try:
        registry = registry or logic.syncDentoCaseTrajectoryRegistry(parameter)
        result["registry"] = registry
    except Exception as exc:
        result["registry_error"] = f"{type(exc).__name__}: {exc}"
    if eligibility is not None:
        result["prepared_branch_eligibility"] = eligibility
    branch = None
    if isinstance(registry, dict):
        branch_id = str(registry.get("selected_branch_id") or "")
        branch = (registry.get("prepared_branches") or {}).get(branch_id)
    if isinstance(branch, dict):
        result["branch"] = {
            "branch_id": branch.get("branch_id"),
            "state": branch.get("state"),
            "revision": branch.get("revision"),
            "verification_revision": branch.get("verification_revision"),
            "shell_node_id": branch.get("shell_node_id"),
            "insertion_direction_node_id": branch.get("insertion_direction_node_id"),
            "target_docking_node_id": branch.get("target_docking_node_id"),
            "template_node_id": branch.get("template_node_id"),
        }
        for label, node_id in (
            ("insertion", branch.get("insertion_direction_node_id")),
            ("shell", branch.get("shell_node_id")),
            ("docking", branch.get("target_docking_node_id")),
            ("template", branch.get("template_node_id")),
        ):
            node = slicer.mrmlScene.GetNodeByID(str(node_id or ""))
            if not node:
                result[f"{label}_error"] = "missing node"
                continue
            result[label] = {
                "id": node.GetID(),
                "class": node.GetClassName(),
                "model_role": node.GetAttribute("DENTOBOT.ModelRole") or "",
                "markups_role": node.GetAttribute("DENTOBOT.MarkupsRole") or "",
                "geometry_state": node.GetAttribute("DENTOBOT.GeometryState") or "",
                "orientation_state": node.GetAttribute("DENTOBOT.OrientationState") or "",
                "updated_utc": node.GetAttribute("DENTOBOT.UpdatedUtc") or "",
                "prepared_branch_revision": node.GetAttribute(
                    "DENTOBOT.PreparedBranchRevision"
                )
                or "",
            }
            if label == "shell":
                try:
                    summary = logic.getPatientContactShellSummary(node)
                    result[label]["insertion_direction_id"] = (
                        summary["insertionDirection"].GetID()
                        if summary.get("insertionDirection")
                        else ""
                    )
                    result[label]["insertion_geometry_json"] = summary.get(
                        "insertionGeometryJson", ""
                    )
                except Exception as exc:
                    result[label]["summary_error"] = f"{type(exc).__name__}: {exc}"
            elif label == "insertion":
                try:
                    summary = logic.getTemplateInsertionDirectionSummary(node)
                    result[label]["geometry_json"] = summary.get("geometryJson", "")
                    result[label]["raw_geometry_json"] = summary.get("rawGeometryJson", "")
                except Exception as exc:
                    result[label]["summary_error"] = f"{type(exc).__name__}: {exc}"
            elif label == "template":
                try:
                    summary = logic.getFinalPrintableTemplateSummary(node)
                    result[label]["verification_state"] = summary.get("verificationState", "")
                    result[label]["patient_shell_id"] = (
                        summary["patientShell"].GetID()
                        if summary.get("patientShell")
                        else ""
                    )
                except Exception as exc:
                    result[label]["summary_error"] = f"{type(exc).__name__}: {exc}"
    return result


def _target_case(widget, source: Path, target_fdi: str, output: Path) -> dict:
    inspection = widget._openCaseBundle(str(source))
    process_events(0.8)
    parameter = widget._parameterNode
    logic = widget.logic
    require(parameter is not None and logic is not None, "workflow state did not restore")
    foundation = logic.evaluateCaseFoundationEligibility(parameter)
    require(foundation["pose"]["eligible"], f"Case Foundation pose is not eligible: {foundation['pose']}")
    segmentation = parameter.teethSegmentation
    require(segmentation is not None, "reviewed teeth segmentation did not restore")
    _remove_derived_planning_nodes(logic, parameter)
    _apply_saved_fdi31_defaults(parameter)
    guide_bore = {
        "channel_diameter_mm": float(parameter.templateChannelDiameterMm),
        "sleeve_inner_diameter_mm": float(parameter.templateSleeveInnerDiameterMm),
        "minimum_required_mm": 2.0,
    }
    require(
        guide_bore["channel_diameter_mm"] >= guide_bore["minimum_required_mm"],
        "trajectory-guide channel must be at least 2.0 mm",
    )
    require(
        guide_bore["sleeve_inner_diameter_mm"]
        >= guide_bore["minimum_required_mm"],
        "trajectory-guide sleeve bore must be at least 2.0 mm",
    )

    record = next(
        (
            item
            for item in logic.getTargetToothRecords(segmentation)
            if str(item.get("fdiNumber") or "") == str(target_fdi)
        ),
        None,
    )
    require(record is not None, f"FDI{target_fdi} is unavailable in the reviewed segmentation")
    target_id = record["segmentId"]
    parameter.targetToothSegmentId = target_id
    parameter.teethSegmentation = segmentation
    roi, _bounds = logic.createOrUpdateTargetBoundsRoi(segmentation, target_id)
    parameter.targetToothBoundsRoi = roi

    entry_node, _ = logic.createOrResetAssistedTrajectoryEntries(
        segmentation, target_id, 1
    )
    parameter.assistedTrajectoryEntries = entry_node
    source_entry, entry_report = _crown_center_entry(logic, segmentation, target_id)
    entry_point = list(source_entry)
    if logic._targetJawOwner(parameter, target_id) == "MovingLower":
        entry_point = _map_point(logic._step6CaseJawMatrixWorld(parameter), source_entry)
    entry_node.AddControlPointWorld(vtk.vtkVector3d(*entry_point))
    logic.stopTrajectoryPlacement()
    trajectories, assisted_analysis = logic.generateAssistedTrajectories(
        entry_node, segmentation, target_id, 1, roi
    )
    require(len(trajectories) == 1, f"FDI{target_fdi} generated {len(trajectories)} trajectories")
    semantic_before = _semantic_snapshot(
        segmentation,
        assisted_analysis["pulpSegmentId"],
    )
    require(
        semantic_before["pulp"]["canonicalName"] == f"Pulp_FDI{target_fdi}",
        f"FDI{target_fdi} did not persist its canonical pulp name",
    )
    trajectory = trajectories[0]
    parameter.trajectoryLine = trajectory
    widget._bindPlanningTrajectoryNode(trajectory)
    bounds_report = logic.getTrajectoryBoundsReport(trajectory, segmentation, target_id)
    require(bounds_report["allDefinedPointsWithinBounds"], f"FDI{target_fdi} trajectory leaves target bounds")
    require(logic.getTrajectorySummary(trajectory)["isValid"], f"FDI{target_fdi} trajectory is invalid")
    trajectory.SetLocked(True)

    support_ids, support_report = _support_selection(logic, segmentation, record)
    draft, support_details = logic.createOrUpdateDraftTemplateSupportModel(
        segmentation, target_id, support_ids
    )
    parameter.draftTemplateSupportModel = draft
    parameter.templateSupportToothSegmentIdsJson = logic.encodeTemplateSupportSegmentIds(support_ids)

    boundary = logic.createOrResetTemplateSupportBoundary(draft)
    parameter.templateSupportBoundaryCurve = boundary
    plane, plane_details = logic.createOrUpdateTemplateSupportBoundaryPlane(
        draft,
        trajectory,
        reverseDirection=bool(parameter.templateSupportDirectionReversed),
        depthFromEntryMm=float(parameter.templateSupportPlaneDepthMm),
        crownCapPercent=float(parameter.templateSupportCrownCapPercent),
    )
    widget._restoringTemplateSupportBoundary = True
    try:
        boundary, boundary_metrics = logic.createOrUpdateTemplateSupportBoundaryFromPlane(
            draft,
            plane,
            trajectory,
            samplingSpacingMm=float(parameter.templateSupportCurveSamplingSpacingMm),
            curveNode=boundary,
        )
    finally:
        widget._restoringTemplateSupportBoundary = False
    parameter.templateSupportBoundaryPlane = plane
    parameter.templateSupportBoundaryCurve = boundary
    visible, visible_metrics = logic.createOrUpdateVisibleTemplateSupportModel(
        draft,
        boundary,
        directionTrajectory=trajectory,
        reverseDirection=bool(parameter.templateSupportDirectionReversed),
        samplingSpacingMm=float(parameter.templateSupportCurveSamplingSpacingMm),
        terminalCoveragePercent=float(parameter.templateTerminalSupportCoveragePercent),
    )
    insertion = visible.GetNodeReference(
        logic.TEMPLATE_VISIBLE_SUPPORT_INSERTION_DIRECTION_REFERENCE_ROLE
    )
    require(insertion is not None, f"FDI{target_fdi} insertion direction was not created")
    parameter.visibleTemplateSupportModel = visible
    parameter.templateInsertionDirection = insertion
    logic.setSelectedTemplateGuideTrajectories(draft, [trajectory])
    process_events(0.1)
    visible_summary = logic.getVisibleTemplateSupportModelSummary(visible)
    require(
        visible_summary["geometryState"] == "Current",
        f"FDI{target_fdi} Step 5A visible support became stale: "
        f"{visible_summary['staleReason']}",
    )

    undercut, blockout, undercut_details = logic.createOrUpdateTemplateUndercutAnalysis(
        draft,
        visible,
        insertion,
        angleToleranceDeg=float(parameter.templateUndercutAngleToleranceDeg),
        interproximalReliefMm=float(parameter.templateInterproximalReliefMm),
        samplingSpacingMm=float(parameter.templateSamplingSpacingMm),
    )
    parameter.templateUndercutSurfaceModel = undercut
    parameter.templateUndercutBlockoutModel = blockout
    shell, shell_details = logic.createOrUpdatePatientContactShell(
        draft,
        visible,
        insertion,
        blockout,
        clearanceMm=float(parameter.templateShellClearanceMm),
        thicknessMm=float(parameter.templateShellThicknessMm),
        samplingSpacingMm=float(parameter.templateSamplingSpacingMm),
        blockoutSafetyMm=float(parameter.templateBlockoutSafetyMm),
        voxelClosingMm=float(parameter.templateShellVoxelClosingMm),
    )
    parameter.patientContactShellModel = shell

    docking_parameters = normalize_target_docking_parameters(
        pattern_radius_mm=float(parameter.targetDockingPatternRadiusMm),
        outer_diameter_mm=float(parameter.targetDockingOuterDiameterMm),
        bore_diameter_mm=float(parameter.targetDockingBoreDiameterMm),
        connector_diameter_mm=float(parameter.targetDockingConnectorDiameterMm),
        connector_thickness_mm=float(parameter.targetDockingConnectorThicknessMm),
        shared_depth_mm=float(parameter.targetDockingSharedDepthMm),
        individual_depths_mm=tuple(
            float(getattr(parameter, f"targetDockingDepth{index}Mm"))
            for index in range(1, 5)
        ),
        individual_depths_enabled=bool(parameter.targetDockingIndividualDepthsEnabled),
        yaw_deg=float(parameter.targetDockingYawDeg),
        collision_clearance_mm=float(parameter.targetDockingCollisionClearanceMm),
        clearance_mm=float(parameter.templateDockingClearanceMm),
        reinforcement_radial_mm=float(parameter.templateReinforcementRadialMm),
        processing_resolution_mm=float(parameter.templateSamplingSpacingMm),
    )
    plane, assembly, docking_details = logic.createOrUpdateTargetDockingAssembly(
        segmentation,
        target_id,
        [trajectory],
        docking_parameters,
        supportModel=draft,
        autoSelectYaw=False,
        measurementsVisible=bool(parameter.targetDockingMeasurementsVisible),
    )
    collision_count = int(
        (docking_details.get("metrics", {}).get("collisionScreen") or {}).get(
            "collidingDockCount", 0
        )
    )
    requested_yaw = float(parameter.targetDockingYawDeg)
    auto_yaw_used = False
    if collision_count:
        plane, assembly, docking_details = logic.createOrUpdateTargetDockingAssembly(
            segmentation,
            target_id,
            [trajectory],
            docking_parameters,
            supportModel=draft,
            planeNode=plane,
            assemblyModel=assembly,
            autoSelectYaw=True,
            measurementsVisible=bool(parameter.targetDockingMeasurementsVisible),
        )
        auto_yaw_used = True
    selected_yaw = float(docking_details["parameters"]["yawDeg"])
    _set_confirmed_docking(parameter, plane, assembly, selected_yaw)

    final_model, role_models, final_details = logic.createOrUpdateFinalPrintableTemplate(
        shell,
        assembly,
        [trajectory],
        outerDiameterMm=float(parameter.templateSleeveOuterDiameterMm),
        innerDiameterMm=float(parameter.templateSleeveInnerDiameterMm),
        heightMm=float(parameter.templateSleeveHeightMm),
        dockingClearanceMm=float(parameter.templateDockingClearanceMm),
        reinforcementRadialMm=float(parameter.templateReinforcementRadialMm),
        reinforcementDepthMm=float(parameter.templateReinforcementDepthMm),
        samplingSpacingMm=float(parameter.templateSamplingSpacingMm),
    )
    parameter.templateDockingAssemblyModel = role_models["docking"]
    parameter.templateDockingClearanceModel = role_models["clearance"]
    parameter.templateDockingReinforcementModel = role_models["reinforcement"]
    parameter.templateDockingChannelsModel = role_models["channels"]
    parameter.finalPrintableTemplateModel = final_model
    verification = logic.verifyFinalPrintableTemplate(final_model)
    require(verification["overall"] in {"PASS", "WARNING"},
            f"FDI{target_fdi} Step 5C verification failed: {verification}")
    final_summary = logic.getFinalPrintableTemplateSummary(final_model)
    require(final_summary["schemaVersion"] == "2.0", f"FDI{target_fdi} has obsolete Step 5C schema")
    require(int(final_summary["metrics"].get("occupiedVolumeRegionCount", 0)) == 1,
            f"FDI{target_fdi} printable geometry is not one connected solid")
    require(int(final_summary["metrics"].get("channelResidualOccupiedSampleCount", -1)) == 0,
            f"FDI{target_fdi} has residual protected-channel occupancy")
    step5c_gate = _step5c_gate(
        logic,
        parameter,
        final_model,
        verification,
        final_summary,
    )

    registry = logic.syncDentoCaseTrajectoryRegistry(parameter)
    require(len(registry["prepared_branches"]) == 1,
            f"FDI{target_fdi} expected one PreparedBranch, got {len(registry['prepared_branches'])}")
    branch_id = str(registry["selected_branch_id"] or "")
    require(branch_id and branch_id in registry["prepared_branches"],
            f"FDI{target_fdi} has no selected PreparedBranch")
    eligibility = logic.evaluatePreparedBranchEligibility(parameter, branch_id, registry=registry)
    require(eligibility["eligible"], f"FDI{target_fdi} PreparedBranch is not eligible: {eligibility}")
    activation = _activation_preservation(logic, parameter, branch_id)

    facade = widget._robotWorkflowFacade
    require(facade is not None, "Step 6 robot façade is unavailable")
    load_result = facade.loadRobot()
    require(load_result.success, f"FDI{target_fdi} local robot load failed: {load_result.message}")
    lock_result = facade.lockBase()
    require(lock_result.success, f"FDI{target_fdi} base lock failed: {lock_result.message}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stl_path = logic.exportFinalPrintableTemplateStl(
        output.parent,
        final_model,
        overwrite=False,
    )
    require(stl_path.is_file(), f"FDI{target_fdi} verified STL was not written")
    stl_sha256 = hashlib.sha256(stl_path.read_bytes()).hexdigest()
    logic.prepareDentoCaseSchema3ForSave(parameter)
    saved_inspection = widget._createCaseBundle(str(output))
    saved_inspection = validate_case_bundle(output)
    require(output.is_file(), f"FDI{target_fdi} package was not written")

    reopened = widget._openCaseBundle(str(output))
    process_events(0.8)
    reopened_parameter = widget._parameterNode
    reopened_logic = widget.logic
    reopened_foundation = reopened_logic.evaluateCaseFoundationEligibility(reopened_parameter)
    reopened_registry = reopened_logic.syncDentoCaseTrajectoryRegistry(reopened_parameter)
    reopened_gate = reopened_logic.evaluatePreparedBranchEligibility(reopened_parameter)
    reopen_diagnostic = _reopen_diagnostic(
        reopened_logic,
        reopened_parameter,
        registry=reopened_registry,
        eligibility=reopened_gate,
    )
    require(reopened_foundation["pose"]["eligible"], f"FDI{target_fdi} reopened Case Foundation pose is stale")
    require(reopened_foundation["base"]["eligible"], f"FDI{target_fdi} reopened base is stale")
    require(len(reopened_registry["prepared_branches"]) == 1, f"FDI{target_fdi} reopen changed PreparedBranch count")
    require(
        reopened_gate["eligible"],
        f"FDI{target_fdi} reopened PreparedBranch is not eligible: "
        + json.dumps(reopen_diagnostic, sort_keys=True, default=str),
    )
    reopened_fdi = str(reopened_parameter.trajectoryLine.GetAttribute("DENTOBOT.TargetFdiNumber") or "")
    require(reopened_fdi == str(target_fdi), f"FDI{target_fdi} reopened as FDI{reopened_fdi}")
    semantic_after = _semantic_snapshot(
        reopened_parameter.teethSegmentation,
        assisted_analysis["pulpSegmentId"],
    )
    require(
        semantic_after == semantic_before,
        f"FDI{target_fdi} semantic registry changed across save/reopen",
    )
    diagnostic_evidence = _capture_screenshot_evidence(widget, target_fdi, "post-reopen")

    return {
        "target_fdi": str(target_fdi),
        "source_package": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "saved_package": str(output),
        "saved_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "verified_stl": {
            "path": str(stl_path),
            "sha256": stl_sha256,
            "size_bytes": stl_path.stat().st_size,
        },
        "guide_bore": guide_bore,
        "diagnostic_evidence": diagnostic_evidence,
        "package_schema": saved_inspection.manifest.get("schemaVersion"),
        "workflow_schema": saved_inspection.workflow.get("schemaVersion"),
        "foundation": foundation,
        "support_selection": support_report,
        "support_details": support_details,
        "trajectory": {
            "node_id": trajectory.GetID(),
            "entry": logic.getTrajectorySummary(trajectory),
            "assisted_analysis": assisted_analysis,
            "entry_report": entry_report,
            "bounds_report": bounds_report,
        },
        "step5a": {
            "plane": plane_details,
            "boundary": boundary_metrics,
            "visible": visible_metrics,
        },
        "step5b": {
            "undercut": undercut_details,
            "shell": shell_details,
        },
        "step4c": {
            "requested_yaw_deg": requested_yaw,
            "selected_yaw_deg": selected_yaw,
            "auto_yaw_used": auto_yaw_used,
            "details": docking_details,
        },
        "step5c": {
            "verification": verification,
            "summary": final_summary,
            "details": final_details,
            "gate": step5c_gate,
        },
        "prepared_branch": {
            "branch_id": branch_id,
            "eligibility": eligibility,
            "activation": activation,
        },
        "reopen": {
            "foundation": reopened_foundation,
            "prepared_branch_count": len(reopened_registry["prepared_branches"]),
            "eligibility": reopened_gate,
            "target_fdi": reopened_fdi,
            "diagnostic": reopen_diagnostic,
        },
        "semantic": {
            "before": semantic_before,
            "after": semantic_after,
            "round_trip_equal": semantic_after == semantic_before,
        },
    }


def _write_startup_failure_reports(exc: Exception) -> Path:
    """Persist a diagnostic manifest when the runner cannot initialize."""

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    failure = {
        "status": "FAIL",
        "error_type": type(exc).__name__,
        "error": str(exc),
        "traceback": traceback.format_exc(),
    }
    target_artifacts = {}
    for target_fdi in TARGET_FDI:
        directory = _target_directory(target_fdi)
        directory.mkdir(parents=True, exist_ok=True)
        report_path = directory / "report.json"
        report = {
            "target_fdi": str(target_fdi),
            "output_directory": str(directory),
            "case_path": str(_case_path(target_fdi)),
            **failure,
        }
        diagnostic_path = _write_target_diagnostic(target_fdi, report)
        report["diagnostic_path"] = str(diagnostic_path)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        target_artifacts[f"FDI{target_fdi}"] = {
            "directory": str(directory),
            "case": str(_case_path(target_fdi)),
            "report": str(report_path),
            "diagnostic": str(diagnostic_path),
            "stl": str(directory / "DENTO_Final_Printable_Template.stl"),
            "status": "FAIL",
        }
    manifest_path = _campaign_directory() / "generation-report.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "source_package": str(SOURCE),
                "run_id": RUN_ID,
                "targets": list(TARGET_FDI),
                "target_artifacts": target_artifacts,
                "startup_error": failure,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return manifest_path


def run() -> int:
    require(SOURCE.is_file(), f"missing generation source package: {SOURCE}")
    require(TARGET_FDI, "no target FDI values requested")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    require(
        slicer.util.getModuleLogic("ROS2") is not None,
        "SlicerROS2 module logic is unavailable; launch with installed SlicerROS2 module paths.",
    )
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    require(widget is not None and widget.logic is not None, "DENTOWorkflow widget did not initialize")

    reports = {}
    for target_fdi in TARGET_FDI:
        directory = _target_directory(target_fdi)
        directory.mkdir(parents=True, exist_ok=True)
        output = _case_path(target_fdi)
        report_path = directory / "report.json"
        try:
            report = {
                "status": "PASS",
                "output_directory": str(directory),
                **_target_case(widget, SOURCE, target_fdi, output),
            }
            diagnostic_path = _write_target_diagnostic(target_fdi, report)
            report["diagnostic_path"] = str(diagnostic_path)
            reports[str(target_fdi)] = report
            report_path.write_text(
                json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            print(f"STAGE6_TARGET_PASS FDI{target_fdi} " + json.dumps({"output": str(output)}, sort_keys=True), flush=True)
        except Exception as exc:
            report = {
                "status": "FAIL",
                "target_fdi": str(target_fdi),
                "output_directory": str(directory),
                "case_path": str(output),
                "source_package": str(SOURCE),
                "source_sha256": (
                    hashlib.sha256(SOURCE.read_bytes()).hexdigest()
                    if SOURCE.is_file()
                    else ""
                ),
                "verified_stl": {
                    "path": str(directory / "DENTO_Final_Printable_Template.stl"),
                    "sha256": (
                        hashlib.sha256(
                            (directory / "DENTO_Final_Printable_Template.stl").read_bytes()
                        ).hexdigest()
                        if (directory / "DENTO_Final_Printable_Template.stl").is_file()
                        else ""
                    ),
                },
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "diagnostic_evidence": _capture_screenshot_evidence(
                    widget, str(target_fdi), "failure"
                ),
            }
            diagnostic_path = _write_target_diagnostic(target_fdi, report)
            report["diagnostic_path"] = str(diagnostic_path)
            reports[str(target_fdi)] = report
            report_path.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(f"STAGE6_TARGET_FAIL FDI{target_fdi} " + json.dumps({"error": str(exc)}, sort_keys=True), flush=True)

    manifest = {
        "source_package": str(SOURCE),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "targets": list(TARGET_FDI),
        "target_artifacts": {
            f"FDI{target_fdi}": {
                "directory": str(_target_directory(target_fdi)),
                "case": str(_case_path(target_fdi)),
                "report": str(_target_directory(target_fdi) / "report.json"),
                "diagnostic": str(_diagnostic_path(target_fdi)),
                "stl": str(_target_directory(target_fdi) / "DENTO_Final_Printable_Template.stl"),
                "status": reports[str(target_fdi)]["status"],
            }
            for target_fdi in TARGET_FDI
        },
        "run_id": RUN_ID,
    }
    manifest_path = _campaign_directory() / "generation-report.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n")
    passed = sum(report.get("status") == "PASS" for report in reports.values())
    print(
        "STAGE6_TARGET_GENERATION_COMPLETE "
        + json.dumps({"passed": passed, "total": len(TARGET_FDI), "report": str(manifest_path)}, sort_keys=True),
        flush=True,
    )
    return 0 if passed == len(TARGET_FDI) else 1


try:
    exit_code = run()
except Exception as exc:
    try:
        failure_report = _write_startup_failure_reports(exc)
    except Exception as report_exc:
        failure_report = ""
        print(
            "STAGE6_TARGET_GENERATION_REPORT_FAIL "
            + json.dumps({"error_type": type(report_exc).__name__, "error": str(report_exc)}, sort_keys=True),
            file=sys.stderr,
            flush=True,
        )
    print(
        "STAGE6_TARGET_GENERATION_FAIL "
        + json.dumps(
            {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "report": str(failure_report),
                "traceback": traceback.format_exc(),
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )
    exit_code = 1
try:
    slicer.util.exit(exit_code)
except Exception:
    raise
