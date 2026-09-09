"""Isolated Slicer check: assisted endpoints, then saved FDI11 shell/fusion.

Run only under the approved serialized runtime protocol. Never saves the input.
"""
import hashlib
import json
import os
from pathlib import Path
import traceback

import qt
import slicer

SOURCE = Path("/workspace/data/Slicer_Saved/SampleStudy1/FDI11/dentobot-case-step5b.dentocase")


def run():
    stage = "assisted-endpoints"
    try:
        automatic_boundary = os.environ.get("DENTOBOT_TEST_AUTO_BOUNDARY") == "1"
        if not automatic_boundary:
            from DENTOWorkflow import DENTOWorkflowTest
            test = DENTOWorkflowTest()
            test.delayDisplay = lambda *args, **kwargs: None
            test.setUp()
            test.test_DENTOWorkflowAssistedRootTrajectoryGeneration()
            print("DENTOBOT_ASSISTED_PULP_PASS", flush=True)
            test.setUp()
        stage = "load-fdi11"
        checksum = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        slicer.util.selectModule("DENTOWorkflow")
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        widget._openCaseBundle(str(SOURCE))
        slicer.app.processEvents()
        parameter = widget._parameterNode
        source_summary = widget.logic.getDraftTemplateSupportModelSummary(parameter.draftTemplateSupportModel)
        target = widget.logic.validateTargetTooth(source_summary["sourceSegmentation"], source_summary["targetSegmentId"])
        assert str(target["fdiNumber"]) == "11", "Package target is not FDI11"
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
            print("DENTOBOT_FDI11_AUTO_BOUNDARY_PASS " + json.dumps(boundary_metrics), flush=True)
        widget.logic.validateTemplateSupportBoundary(parameter.draftTemplateSupportModel, boundary)
        points = widget.logic.templateSupportBoundaryControlPointsWorld(boundary)
        print("DENTOBOT_FDI11_BOUNDARY " + json.dumps({"controlPointCount": len(points), "mapping": boundary.GetAttribute("DENTOBOT.BoundaryMappingMethod")}), flush=True)
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
        print("DENTOBOT_FDI11_PREVIEW_PASS " + json.dumps(preview_metrics), flush=True)
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
        print("DENTOBOT_FDI11_SHELL_PASS", flush=True)
        stage = "unified-template"
        final, _, details = widget._createOrUpdateFinalPrintableTemplate()
        summary = widget.logic.getFinalPrintableTemplateSummary(final)
        assert summary["geometryState"] == "Current"
        assert final.GetPolyData().GetNumberOfCells() > 0
        assert details["fusion"]["occupiedVolumeRegionCount"] == 1
        assert details["fusion"]["boundaryOrNonManifoldEdgeCount"] == 0
        assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == checksum, "Source package changed"
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
