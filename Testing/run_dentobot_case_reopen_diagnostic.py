"""Read-only diagnostic for a saved DENTOBOT case-package reopen.

The runner does not generate geometry, connect ROS, or change the package on
disk.  It records the first PreparedBranch eligibility result and the
persisted shell/insertion/template identities after a fresh MRML restore.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import traceback
import types

import qt
import slicer
import vtk


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
MODULE = ROOT / "DENTOWorkflow"
for path in (HELPERS, MODULE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from DENTOCaseBundle import validate_case_bundle  # noqa: E402


PACKAGE = Path(os.environ.get("DENTOBOT_REOPEN_PACKAGE", ""))
ALLOW_FOUNDATION_ONLY = (
    os.environ.get("DENTOBOT_REOPEN_ALLOW_FOUNDATION_ONLY", "") == "1"
)
OUTPUT = Path(
    os.environ.get(
        "DENTOBOT_REOPEN_DIAGNOSTIC_OUTPUT",
        "/tmp/dentobot-case-reopen-diagnostic.json",
    )
)
EVIDENCE_DIR = Path(
    os.environ.get(
        "DENTOBOT_REOPEN_EVIDENCE_DIR",
        str(OUTPUT.parent / "evidence-final"),
    )
)
REFRESH_EVENTS: list[dict[str, object]] = []
VISIBLE_REFRESH_EVENTS: list[dict[str, object]] = []
FINAL_STALE_EVENTS: list[dict[str, object]] = []


def process_events(seconds: float = 0.25) -> None:
    deadline = time.monotonic() + float(seconds)
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def capture_screenshot_evidence(widget, parameter) -> dict[str, object]:
    """Capture the reopened package without changing scene or runtime state."""

    result: dict[str, object] = {
        "directory": str(EVIDENCE_DIR),
        "screenshots": [],
        "capture_errors": [],
        "viewportGeometry": {},
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    keep_ids = {
        node.GetID()
        for node in (
            getattr(parameter, "finalPrintableTemplateModel", None),
            getattr(parameter, "targetDockingAssemblyModel", None),
        )
        if node is not None
    }
    saved_visibility = []
    displayables = slicer.mrmlScene.GetNodes()
    for index in range(displayables.GetNumberOfItems()):
        node = displayables.GetItemAsObject(index)
        if not node or not node.IsA("vtkMRMLDisplayableNode"):
            continue
        display = node.GetDisplayNode()
        if display is None:
            continue
        saved_visibility.append((display, int(display.GetVisibility())))
        display.SetVisibility(1 if node.GetID() in keep_ids else 0)
    try:
        host = slicer.util.mainWindow() or getattr(widget, "_uiWidget", None)
        if host is None:
            raise RuntimeError("Slicer UI is unavailable")
        host.show()
        process_events(0.25)
        path = EVIDENCE_DIR / "reopened-ui.png"
        pixmap = host.grab()
        if pixmap.isNull() or not pixmap.save(str(path)):
            raise RuntimeError(f"could not capture UI: {path}")
        result["screenshots"].append(str(path))
    except Exception as exc:
        result["capture_errors"].append(f"ui: {type(exc).__name__}: {exc}")
    try:
        view = slicer.app.layoutManager().threeDWidget(0).threeDView()
        view.show()
        focus_candidates = [
            getattr(parameter, "targetDockingAssemblyModel", None),
            getattr(parameter, "finalPrintableTemplateModel", None),
        ]
        focus_candidates = [
            node for node in focus_candidates if node is not None
        ]
        focus_nodes = [
            node
            for node in (focus_candidates[:1] or focus_candidates)
            if node is not None
            and node.GetPolyData()
            and node.GetPolyData().GetNumberOfPoints()
        ]
        if focus_nodes:
            bounds = [float("inf"), float("-inf")] * 3
            for focus in focus_nodes:
                focus_bounds = [0.0] * 6
                focus.GetRASBounds(focus_bounds)
                for axis in range(3):
                    bounds[2 * axis] = min(
                        bounds[2 * axis],
                        focus_bounds[2 * axis],
                    )
                    bounds[2 * axis + 1] = max(
                        bounds[2 * axis + 1],
                        focus_bounds[2 * axis + 1],
                    )
            span = max(
                bounds[1] - bounds[0],
                bounds[3] - bounds[2],
                bounds[5] - bounds[4],
            )
            if span > 1.0e-6:
                center = [
                    (bounds[2 * axis] + bounds[2 * axis + 1]) / 2.0
                    for axis in range(3)
                ]
                camera = view.cameraNode().GetCamera()
                camera.SetFocalPoint(*center)
                camera.SetPosition(
                    center[0] + span,
                    center[1] - span,
                    center[2] + span,
                )
                camera.SetViewUp(0.0, 0.0, 1.0)
                camera.ParallelProjectionOn()
                camera.SetParallelScale(min(20.0, max(5.0, 0.4 * span)))
        view.forceRender()
        slicer.util.forceRenderAllViews()
        process_events(0.5)
        render_window = view.renderWindow()
        render_window.Render()
        host = slicer.util.mainWindow()
        view_size = view.size
        if callable(view_size):
            view_size = view_size()
        origin = view.mapTo(host, qt.QPoint(0, 0)) if host else qt.QPoint(0, 0)
        width = getattr(view_size, "width")
        height = getattr(view_size, "height")
        if callable(width):
            width = width()
        if callable(height):
            height = height()
        main_width = getattr(host, "width") if host else 0
        main_height = getattr(host, "height") if host else 0
        if callable(main_width):
            main_width = main_width()
        if callable(main_height):
            main_height = main_height()
        result["viewportGeometry"] = {
            "viewSize": [int(width), int(height)],
            "originInMainWindow": [int(origin.x()), int(origin.y())],
            "mainWindowSize": [int(main_width), int(main_height)] if host else [],
        }
        path = EVIDENCE_DIR / "reopened-viewport.png"
        capture_filter = vtk.vtkWindowToImageFilter()
        capture_filter.SetInput(render_window)
        capture_filter.ReadFrontBufferOff()
        capture_filter.Update()
        writer = vtk.vtkPNGWriter()
        writer.SetFileName(str(path))
        writer.SetInputConnection(capture_filter.GetOutputPort())
        writer.Write()
        if not path.is_file() or path.stat().st_size < 1024:
            if host:
                pixmap = host.grab(qt.QRect(origin, view_size))
                if pixmap.isNull() or not pixmap.save(str(path)):
                    raise RuntimeError(f"could not capture viewport: {path}")
        result["screenshots"].append(str(path))
    except Exception as exc:
        result["capture_errors"].append(
            f"viewport: {type(exc).__name__}: {exc}"
        )
    for display, visibility in saved_visibility:
        display.SetVisibility(visibility)
    return result


def node_record(node) -> dict[str, object]:
    if node is None:
        return {"present": False}
    return {
        "present": True,
        "id": node.GetID(),
        "class": node.GetClassName(),
        "modelRole": node.GetAttribute("DENTOBOT.ModelRole") or "",
        "markupsRole": node.GetAttribute("DENTOBOT.MarkupsRole") or "",
        "geometryState": node.GetAttribute("DENTOBOT.GeometryState") or "",
        "orientationState": node.GetAttribute("DENTOBOT.OrientationState") or "",
        "updatedUtc": node.GetAttribute("DENTOBOT.UpdatedUtc") or "",
        "preparedBranchRevision": node.GetAttribute(
            "DENTOBOT.PreparedBranchRevision"
        )
        or "",
    }


def transform_record(node) -> dict[str, object]:
    """Record the effective world transform of one transformable MRML node."""

    if node is None:
        return {"present": False}
    parent = node.GetParentTransformNode()
    matrix = vtk.vtkMatrix4x4()
    matrix.Identity()
    if hasattr(node, "GetMatrixTransformToWorld"):
        node.GetMatrixTransformToWorld(matrix)
    elif parent:
        parent.GetMatrixTransformToWorld(matrix)
    return {
        "present": True,
        "id": node.GetID(),
        "name": node.GetName(),
        "class": node.GetClassName(),
        "parentId": parent.GetID() if parent else "",
        "parentName": parent.GetName() if parent else "",
        "matrixToWorld": [
            round(float(matrix.GetElement(row, column)), 9)
            for row in range(4)
            for column in range(4)
        ],
    }


def _bounds_record(surface) -> list[float] | None:
    if surface is None or surface.GetNumberOfPoints() == 0:
        return None
    return [round(float(value), 6) for value in surface.GetBounds()]


def segmentation_display_audit(node, logic) -> dict[str, object]:
    """Capture source/derived mask pose and display state without mutating MRML."""

    if node is None:
        return {"present": False}
    display = node.GetDisplayNode()
    segmentation = node.GetSegmentation()
    reviews = {}
    try:
        reviews = {
            str(record.get("segmentId") or ""): record
            for record in logic.getSegmentationReviewRecords(node)
            if str(record.get("segmentId") or "")
        }
    except Exception as exc:
        reviews = {"__error__": {"error": f"{type(exc).__name__}: {exc}"}}
    segment_records = []
    if segmentation:
        segment_ids = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(segment_ids)
        for index in range(segment_ids.GetNumberOfValues()):
            segment_id = segment_ids.GetValue(index)
            segment = segmentation.GetSegment(segment_id)
            review = reviews.get(segment_id, {})
            local_surface = None
            if segment:
                local_surface = segment.GetRepresentation(
                    slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName()
                )
            try:
                world_surface = logic._segmentationSegmentsSurfaceWorld(
                    node, {segment_id}
                )
            except Exception:
                world_surface = None
            segment_records.append(
                {
                    "id": segment_id,
                    "name": segment.GetName() if segment else "",
                    "category": str(review.get("category") or ""),
                    "fdiNumber": str(review.get("fdiNumber") or ""),
                    "sourceName": str(review.get("sourceName") or ""),
                    "visible": bool(
                        display.GetSegmentVisibility(segment_id)
                    )
                    if display
                    else None,
                    "visible3D": bool(
                        display.GetSegmentVisibility3D(segment_id)
                    )
                    if display
                    else None,
                    "localBounds": _bounds_record(local_surface),
                    "worldBounds": _bounds_record(world_surface),
                }
            )
    return {
        "present": True,
        "id": node.GetID(),
        "name": node.GetName(),
        "class": node.GetClassName(),
        "segmentationRole": node.GetAttribute("DENTOBOT.SegmentationRole") or "",
        "sourceSegmentIdsJson": node.GetAttribute(
            "DENTOBOT.SourceSegmentIdsJson"
        )
        or "",
        "sourceSegmentVisibility3DJson": node.GetAttribute(
            "DENTOBOT.SourceSegmentVisibility3DJson"
        )
        or "",
        "display": {
            "visibility": bool(display.GetVisibility()) if display else None,
            "visibility2D": bool(display.GetVisibility2D()) if display else None,
            "visibility3D": bool(display.GetVisibility3D()) if display else None,
        },
        "transform": transform_record(node),
        "segments": segment_records,
    }


def build_mask_display_audit(parameter, logic) -> dict[str, object]:
    transform = parameter.step6CaseJawTransform
    return {
        "source": segmentation_display_audit(parameter.teethSegmentation, logic),
        "fixedUpper": segmentation_display_audit(
            parameter.step6FixedUpperAnatomy, logic
        ),
        "movingLower": segmentation_display_audit(
            parameter.step6MovingLowerAnatomy, logic
        ),
        "openedLowerJawModel": transform_record(parameter.step6OpenedLowerJawModel),
        "jawTransform": transform_record(transform),
        "jawTransformAttributes": {
            "movingSegmentIdsJson": transform.GetAttribute(
                "DENTOBOT.MovingSegmentIdsJson"
            )
            or "",
            "fixedSegmentIdsJson": transform.GetAttribute(
                "DENTOBOT.FixedSegmentIdsJson"
            )
            or "",
        }
        if transform
        else {},
    }


def run() -> dict[str, object]:
    require(PACKAGE.is_file(), f"missing reopen package: {PACKAGE}")
    inspection = validate_case_bundle(PACKAGE)
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    require(widget is not None and widget.logic is not None, "DENTOWorkflow is unavailable")
    refreshEvents = REFRESH_EVENTS
    originalInvalidate = widget._invalidateTemplateSupportSurfaceDownstream

    def captureInvalidate(self, reason: str):
        refreshEvents.append(
            {
                "reason": str(reason),
                "stack": traceback.format_stack(limit=8),
            }
        )
        return originalInvalidate(reason)

    widget._invalidateTemplateSupportSurfaceDownstream = types.MethodType(
        captureInvalidate,
        widget,
    )

    originalVisibleRefresh = widget._updateVisibleTemplateSupportSurfaceControls

    def captureVisibleRefresh(self, sourceSummary):
        if len(VISIBLE_REFRESH_EVENTS) < 40:
            event: dict[str, object] = {}
            parameterNode = self._parameterNode
            previewNode = (
                parameterNode.visibleTemplateSupportModel
                if parameterNode
                else None
            )
            trajectoryNode = parameterNode.trajectoryLine if parameterNode else None
            try:
                previewSummary = self.logic.getVisibleTemplateSupportModelSummary(
                    previewNode
                )
                event["preview"] = {
                    "nodeId": previewNode.GetID() if previewNode else "",
                    "directionGeometryJson": previewSummary.get(
                        "directionGeometryJson", ""
                    ),
                    "directionReversed": previewSummary.get(
                        "directionReversed", False
                    ),
                    "directionTrajectoryId": (
                        previewSummary["directionTrajectory"].GetID()
                        if previewSummary.get("directionTrajectory")
                        else ""
                    ),
                    "geometryState": previewSummary.get("geometryState", ""),
                }
                directionSummary = self.logic.resolveTemplateSupportTrajectoryDirection(
                    parameterNode.draftTemplateSupportModel,
                    trajectoryNode,
                    reverseDirection=bool(
                        parameterNode.templateSupportDirectionReversed
                    ),
                )
                event["resolved"] = {
                    "trajectoryId": trajectoryNode.GetID() if trajectoryNode else "",
                    "directionGeometryJson": directionSummary.get(
                        "directionGeometryJson", ""
                    ),
                    "directionReversed": bool(
                        parameterNode.templateSupportDirectionReversed
                    ),
                }
            except Exception as exc:
                event["error"] = f"{type(exc).__name__}: {exc}"
            VISIBLE_REFRESH_EVENTS.append(event)
        return originalVisibleRefresh(sourceSummary)

    widget._updateVisibleTemplateSupportSurfaceControls = types.MethodType(
        captureVisibleRefresh,
        widget,
    )
    originalFinalStale = widget.logic.markFinalPrintableTemplateStale

    def captureFinalStale(finalModel, reason: str):
        FINAL_STALE_EVENTS.append(
            {
                "nodeId": finalModel.GetID() if finalModel else "",
                "reason": str(reason),
                "stack": traceback.format_stack(limit=8),
            }
        )
        return originalFinalStale(finalModel, reason)

    widget.logic.markFinalPrintableTemplateStale = captureFinalStale
    widget._openCaseBundle(str(PACKAGE))
    process_events(1.0)
    parameter = widget._parameterNode
    logic = widget.logic
    require(parameter is not None and logic is not None, "case state did not restore")
    registry = logic.syncDentoCaseTrajectoryRegistry(parameter)
    eligibility = logic.evaluatePreparedBranchEligibility(parameter)
    foundation = logic.evaluateCaseFoundationEligibility(parameter)
    branch_id = str(registry.get("selected_branch_id") or "")
    branch = (registry.get("prepared_branches") or {}).get(branch_id) or {}
    foundation_only = bool(
        not branch
        and foundation["pose"]["eligible"]
        and parameter.robotBaseTransform is not None
        and not slicer.util.getNodesByClass("vtkMRMLROS2RobotNode")
    )
    records = {
        "insertion": node_record(
            slicer.mrmlScene.GetNodeByID(str(branch.get("insertion_direction_node_id") or ""))
        ),
        "shell": node_record(
            slicer.mrmlScene.GetNodeByID(str(branch.get("shell_node_id") or ""))
        ),
        "docking": node_record(
            slicer.mrmlScene.GetNodeByID(str(branch.get("target_docking_node_id") or ""))
        ),
        "template": node_record(
            slicer.mrmlScene.GetNodeByID(str(branch.get("template_node_id") or ""))
        ),
    }
    insertion = slicer.mrmlScene.GetNodeByID(
        str(branch.get("insertion_direction_node_id") or "")
    )
    shell = slicer.mrmlScene.GetNodeByID(str(branch.get("shell_node_id") or ""))
    if insertion:
        try:
            summary = logic.getTemplateInsertionDirectionSummary(insertion)
            records["insertion"]["geometryJson"] = summary["geometryJson"]
            records["insertion"]["rawGeometryJson"] = summary["rawGeometryJson"]
        except Exception as exc:
            records["insertion"]["summaryError"] = f"{type(exc).__name__}: {exc}"
    if shell:
        try:
            summary = logic.getPatientContactShellSummary(shell)
            records["shell"]["insertionDirectionId"] = (
                summary["insertionDirection"].GetID()
                if summary.get("insertionDirection")
                else ""
            )
            records["shell"]["insertionGeometryJson"] = summary.get(
                "insertionGeometryJson", ""
            )
        except Exception as exc:
            records["shell"]["summaryError"] = f"{type(exc).__name__}: {exc}"
    screenshot_evidence = capture_screenshot_evidence(widget, parameter)
    mask_display_audit = build_mask_display_audit(parameter, logic)
    return {
        "status": (
            "PASS"
            if eligibility.get("eligible")
            or (ALLOW_FOUNDATION_ONLY and foundation_only)
            else "FAIL"
        ),
        "package": str(PACKAGE),
        "packageSha256": __import__("hashlib").sha256(PACKAGE.read_bytes()).hexdigest(),
        "manifestSchema": inspection.manifest.get("schemaVersion"),
        "workflowSchema": inspection.workflow.get("schemaVersion"),
        "foundation": foundation,
        "foundationOnly": foundation_only,
        "allowFoundationOnly": ALLOW_FOUNDATION_ONLY,
        "parameter": {
            "basePlacementRevision": int(parameter.step6BasePlacementRevision),
            "basePlacementStatus": str(parameter.step6BasePlacementStatus or ""),
            "baseLocked": bool(parameter.robotBaseMountLocked),
            "planningContextImported": bool(parameter.step6PlanningContextImported),
            "caseFoundationPreparationMode": str(
                parameter.step6CaseJawPreparationMode or ""
            ),
        },
        "registry": registry,
        "preparedBranchEligibility": eligibility,
        "branch": branch,
        "nodes": records,
        "maskDisplayAudit": mask_display_audit,
        "screenshotEvidence": screenshot_evidence,
        "supportSurfaceRefreshEvents": refreshEvents,
        "visibleSupportRefreshEvents": VISIBLE_REFRESH_EVENTS,
        "finalPrintableTemplateStaleEvents": FINAL_STALE_EVENTS,
    }


try:
    report = run()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    print("DENTOBOT_CASE_REOPEN_DIAGNOSTIC " + json.dumps(report, sort_keys=True), flush=True)
    slicer.util.exit(0 if report["status"] == "PASS" else 1)
except Exception as exc:
    failure = {
        "status": "ERROR",
        "package": str(PACKAGE),
        "errorType": type(exc).__name__,
        "error": str(exc),
        "traceback": traceback.format_exc(),
        "supportSurfaceRefreshEvents": REFRESH_EVENTS,
        "visibleSupportRefreshEvents": VISIBLE_REFRESH_EVENTS,
        "finalPrintableTemplateStaleEvents": FINAL_STALE_EVENTS,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
    print("DENTOBOT_CASE_REOPEN_DIAGNOSTIC_FAILED " + json.dumps(failure, sort_keys=True), file=sys.stderr, flush=True)
    slicer.util.exit(1)
