"""Isolated Slicer check: Step 4A display/endpoints, then case shell/fusion.

Run only under the approved serialized runtime protocol. Never saves the input.
"""
import hashlib
import json
import os
from pathlib import Path
import traceback

import qt
import slicer

SOURCE = Path(os.environ.get(
    "DENTOBOT_CASE_SOURCE",
    "/workspace/data/Slicer_Saved/SampleStudy1/FDI11/dentobot-case-step5b.dentocase",
))
EXPECTED_FDI = os.environ.get("DENTOBOT_EXPECTED_FDI", "11")
CASE_MARKER = f"DENTOBOT_FDI{EXPECTED_FDI}"


def _capture_final_dock_screenshots(final, details: dict, directory: str) -> list[str]:
    """Capture an overview and top-down evidence image for every fused dock."""

    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    # The case bundle also contains segmentation, markups, labels and planning
    # geometry.  Hide every display node first so the capture is final-fusion only.
    for node in slicer.util.getNodesByClass("vtkMRMLDisplayNode"):
        node.SetVisibility(False)
    display = final.GetDisplayNode()
    display.SetVisibility(True)
    display.SetColor(0.36, 0.08, 0.64)
    display.SetOpacity(1.0)
    display.SetEdgeVisibility(True)
    display.SetEdgeColor(0.95, 0.95, 0.95)
    layout = slicer.app.layoutManager()
    layout.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView)
    view = layout.threeDWidget(0).threeDView()
    view.mrmlViewNode().SetAxisLabelsVisible(False)
    camera = view.cameraNode().GetCamera()
    bounds = final.GetPolyData().GetBounds()
    center = tuple((bounds[2 * axis] + bounds[2 * axis + 1]) / 2.0 for axis in range(3))
    span = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4])
    paths = []

    def capture(label: str) -> None:
        path = output / f"final-fusion-{label}.png"
        view.forceRender()
        slicer.util.forceRenderAllViews()
        if not view.grab().save(str(path)):
            raise RuntimeError(f"Could not save final-fusion screenshot {path}")
        paths.append(str(path))

    camera.SetFocalPoint(*center)
    camera.SetPosition(center[0] + span, center[1] - span, center[2] + span)
    camera.SetViewUp(0.0, 0.0, 1.0)
    camera.ParallelProjectionOn()
    camera.SetParallelScale(span * 0.65)
    capture("overview")
    for dock in details["assembly"]["targetDocking"]["docks"]:
        top = tuple(float(value) for value in dock["topFaceCenterRas"])
        axis = tuple(float(value) for value in dock["axisRas"])
        view_up = (0.0, 1.0, 0.0) if abs(axis[2]) > 0.9 else (0.0, 0.0, 1.0)
        camera.SetFocalPoint(*(top[axis_index] + 1.5 * axis[axis_index] for axis_index in range(3)))
        camera.SetPosition(*(top[axis_index] - 35.0 * axis[axis_index] for axis_index in range(3)))
        camera.SetViewUp(*view_up)
        camera.ParallelProjectionOn()
        camera.SetParallelScale(5.0)
        camera.OrthogonalizeViewUp()
        capture(f"dock-{dock['label'].replace('+', 'plus').replace('-', 'minus')}")
    return paths


def run():
    stage = "step4a-display"
    try:
        automatic_boundary = os.environ.get("DENTOBOT_TEST_AUTO_BOUNDARY") == "1"
        step4a_only = os.environ.get("DENTOBOT_TEST_STEP4A_ONLY") == "1"
        if not automatic_boundary:
            from DENTOWorkflow import DENTOWorkflowTest
            test = DENTOWorkflowTest()
            test.delayDisplay = lambda *args, **kwargs: None
            test.setUp()
            test.test_DENTOWorkflowSegmentationReviewLogic()
            print("DENTOBOT_STEP4A_DISPLAY_PASS", flush=True)
            test.setUp()
            stage = "assisted-endpoints"
            test.test_DENTOWorkflowAssistedRootTrajectoryGeneration()
            print("DENTOBOT_ASSISTED_PULP_PASS", flush=True)
            test.setUp()
            if step4a_only:
                print("DENTOBOT_STEP4A_P0_PASS", flush=True)
                slicer.util.exit(0)
                return
        stage = "load-fdi11"
        checksum = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        slicer.util.selectModule("DENTOWorkflow")
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        widget._openCaseBundle(str(SOURCE))
        slicer.app.processEvents()
        parameter = widget._parameterNode
        source_summary = widget.logic.getDraftTemplateSupportModelSummary(parameter.draftTemplateSupportModel)
        target = widget.logic.validateTargetTooth(source_summary["sourceSegmentation"], source_summary["targetSegmentId"])
        assert str(target["fdiNumber"]) == EXPECTED_FDI, (
            f"Package target is not FDI{EXPECTED_FDI}"
        )
        stage = "saved-boundary"
        boundary = parameter.templateSupportBoundaryCurve
        if automatic_boundary:
            stage = "automatic-boundary"
            boundary, boundary_metrics = widget.logic.createOrUpdateTemplateSupportBoundaryFromPlane(
                parameter.draftTemplateSupportModel, parameter.templateSupportBoundaryPlane,
                parameter.trajectoryLine,
                samplingSpacingMm=parameter.templateSupportCurveSamplingSpacingMm,
                curveNode=boundary,
            )
            parameter.templateSupportBoundaryCurve = boundary
            print(CASE_MARKER + "_AUTO_BOUNDARY_PASS " + json.dumps(boundary_metrics), flush=True)
        widget.logic.validateTemplateSupportBoundary(parameter.draftTemplateSupportModel, boundary)
        points = widget.logic.templateSupportBoundaryControlPointsWorld(boundary)
        print(CASE_MARKER + "_BOUNDARY " + json.dumps({"controlPointCount": len(points), "mapping": boundary.GetAttribute("DENTOBOT.BoundaryMappingMethod")}), flush=True)
        stage = "visible-preview"
        preview, preview_metrics = widget.logic.createOrUpdateVisibleTemplateSupportModel(
            parameter.draftTemplateSupportModel, boundary,
            directionTrajectory=parameter.trajectoryLine,
            reverseDirection=parameter.templateSupportDirectionReversed,
            samplingSpacingMm=parameter.templateSupportCurveSamplingSpacingMm,
            terminalCoveragePercent=parameter.templateTerminalSupportCoveragePercent,
            outputModel=parameter.visibleTemplateSupportModel,
            insertionDirectionNode=parameter.templateInsertionDirection,
        )
        parameter.visibleTemplateSupportModel = preview
        parameter.templateInsertionDirection = preview.GetNodeReference(widget.logic.TEMPLATE_VISIBLE_SUPPORT_INSERTION_DIRECTION_REFERENCE_ROLE)
        print(CASE_MARKER + "_PREVIEW_PASS " + json.dumps(preview_metrics), flush=True)
        stage = "preflight"
        widget._completeTemplateBuildPreflight()
        stage = "blockout"
        widget._createOrUpdateTemplateUndercuts()
        stage = "patient-shell"
        widget._createOrUpdatePatientContactShell()
        shell = widget.logic.getPatientContactShellSummary(parameter.patientContactShellModel)
        assert shell["geometryState"] == "Current"
        assert shell["metrics"]["surfaceRegionCount"] == 1
        assert shell["metrics"]["boundaryOrNonManifoldEdgeCount"] == 0
        print(CASE_MARKER + "_SHELL_PASS", flush=True)
        stage = "unified-template"
        final, _, details = widget._createOrUpdateFinalPrintableTemplate()
        summary = widget.logic.getFinalPrintableTemplateSummary(final)
        assert summary["geometryState"] == "Current"
        assert final.GetPolyData().GetNumberOfCells() > 0
        assert details["fusion"]["occupiedVolumeRegionCount"] == 1
        assert details["fusion"]["boundaryOrNonManifoldEdgeCount"] == 0
        assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == checksum, "Source package changed"
        capture_directory = os.environ.get("DENTOBOT_CAPTURE_FINAL_DOCKS_DIR")
        if capture_directory:
            print(
                "DENTOBOT_FINAL_FUSION_DOCK_CAPTURE " + json.dumps(
                    _capture_final_dock_screenshots(final, details, capture_directory)
                ),
                flush=True,
            )
        print("DENTOBOT_PULP_SHELL_PASS " + json.dumps({
            "sourceSha256": checksum,
            "automaticBoundary": automatic_boundary,
            "shellRegions": shell["metrics"]["surfaceRegionCount"],
            "shellInvalidEdges": shell["metrics"]["boundaryOrNonManifoldEdgeCount"],
            "finalCells": final.GetPolyData().GetNumberOfCells(),
            "fusion": details["fusion"],
        }), flush=True)
        slicer.util.exit(0)
    except Exception as exc:
        traceback.print_exc()
        print("DENTOBOT_PULP_SHELL_FAIL " + json.dumps({"stage": stage, "error": str(exc)}), flush=True)
        slicer.util.exit(1)


qt.QTimer.singleShot(0, run)
