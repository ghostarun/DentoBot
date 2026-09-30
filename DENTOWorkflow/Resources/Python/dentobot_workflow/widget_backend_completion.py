"""Backend completion callbacks for the workflow widget."""

from __future__ import annotations

from .runtime import *


class BackendCompletionWidgetMixin:
    def _onBackendCompleted(self, runId: str, returnCode: int) -> None:
        if not self._activeBackendRun or self._activeBackendRun["runId"] != runId:
            return

        runContext = self._activeBackendRun
        wasCancelled = self._backendCancellationRequested
        self._backendProcess = None
        self._activeBackendRun = None
        self._backendCancellationRequested = False
        if self._isCleaningUp:
            return
        self._updateBackendControls()

        if wasCancelled:
            self._setBackendStatus(_("Backend process cancelled."), "warning")
            return

        try:
            if runContext["operation"] == "health":
                self._completeHealthCheck(returnCode)
            elif runContext["operation"] == "roundtrip":
                self._completeRoundTrip(runContext, returnCode)
            elif runContext["operation"] == "segment-teeth":
                self._completeTeethSegmentation(runContext, returnCode)
        except Exception as exc:
            logging.exception("DENTOBOT backend completion handling failed")
            self._setBackendStatus(str(exc), "error")

    def _completeHealthCheck(self, returnCode: int) -> None:
        report = self.logic.findJsonReport(self._backendOutputLines, "health")
        if not report:
            raise RuntimeError(
                _("The backend did not return a valid health JSON document.")
            )
        if report.get("schemaVersion") != "1.0":
            raise RuntimeError(_("The backend health schema version is not supported."))

        if returnCode != 0 or report.get("status") != "ok":
            errors = report.get("errors") or [
                _("Backend health check failed with exit code %1.").replace(
                    "%1", str(returnCode)
                )
            ]
            raise RuntimeError(" ".join(str(error) for error in errors))

        requestedDevice = str(report.get("requestedDevice") or _("unspecified"))
        openvinoDevices = report.get("openvino", {}).get("devices") or []
        acceleratorText = (
            _("; OpenVINO sees %1").replace(
                "%1", ", ".join(str(device) for device in openvinoDevices)
            )
            if openvinoDevices
            else ""
        )
        pythonVersion = report.get("python", {}).get("version", _("unknown"))
        self._setBackendStatus(
            _("Backend healthy: Python %1; explicit device %2%3.")
            .replace("%1", str(pythonVersion))
            .replace("%2", requestedDevice)
            .replace("%3", acceleratorText),
            "success",
        )

    def _completeTeethSegmentation(
        self,
        runContext: dict,
        returnCode: int,
    ) -> None:
        runPaths = runContext["paths"]
        resultPath = runPaths["result"]
        if not resultPath.is_file():
            raise RuntimeError(
                _("The backend did not create the expected segmentation metadata.")
            )

        report = json.loads(resultPath.read_text(encoding="utf-8"))
        self.logic.validateTeethSegmentationReport(
            report,
            runContext["runId"],
            expectedDevice=runContext.get("device"),
        )
        if returnCode != 0 or report.get("status") != "ok":
            errorCode = report.get("errorCode")
            errors = report.get("errors") or [
                _("Teeth segmentation failed with exit code %1.")
                .replace("%1", str(returnCode))
            ]
            prefix = f"[{errorCode}] " if errorCode else ""
            raise RuntimeError(prefix + " ".join(str(error) for error in errors))
        if not runPaths["output"].is_file():
            raise RuntimeError(_("The expected teeth segmentation NIfTI is missing."))

        sourceVolume = slicer.mrmlScene.GetNodeByID(runContext["sourceVolumeId"])
        if not sourceVolume:
            raise RuntimeError(_("The source CBCT volume is no longer in the scene."))

        labelmapNode = None
        colorTableNode = None
        segmentationNode = None
        try:
            labelmapNode = slicer.util.loadLabelVolume(
                str(runPaths["output"]),
                {"name": f"DENTOBOT_TeethLabels_{runContext['runId'][:8]}"},
            )
            if not labelmapNode:
                raise RuntimeError(
                    _("Slicer could not import the returned teeth label map.")
                )
            self.logic.validateMatchingVolumeGeometry(
                sourceVolume,
                labelmapNode,
                requireMatchingScalarType=False,
            )
            self.logic.validateLabelmapAgainstReport(labelmapNode, report)

            colorTableNode = self.logic.createTeethColorTable(
                report["labels"],
                runContext["runId"],
            )
            labelmapNode.CreateDefaultDisplayNodes()
            labelmapNode.GetDisplayNode().SetAndObserveColorNodeID(
                colorTableNode.GetID()
            )

            sourceName = str(sourceVolume.GetName() or "CBCT").strip()
            segmentationName = slicer.mrmlScene.GenerateUniqueName(
                f"[Teeth] {sourceName} — run {runContext['runId'][:8]}"
            )
            segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLSegmentationNode",
                segmentationName,
            )
            segmentationNode.CreateDefaultDisplayNodes()
            segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(
                sourceVolume
            )
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
                labelmapNode,
                segmentationNode,
            )
            expectedSegmentCount = int(report["metrics"]["segmentCount"])
            actualSegmentCount = (
                segmentationNode.GetSegmentation().GetNumberOfSegments()
            )
            if actualSegmentCount != expectedSegmentCount:
                raise RuntimeError(
                    _(
                        "Imported segmentation contains %1 segments, but the "
                        "validated backend report specifies %2."
                    )
                    .replace("%1", str(actualSegmentCount))
                    .replace("%2", str(expectedSegmentCount))
                )

            self._setBackendStatus(
                _("Creating interactive 3D surfaces for validated labels..."),
                "working",
            )
            slicer.app.processEvents()
            segmentationNode.CreateClosedSurfaceRepresentation()
            displayNode = segmentationNode.GetDisplayNode()
            displayNode.SetVisibility(True)
            displayNode.SetVisibility2D(True)
            displayNode.SetVisibility3D(True)
            displayNode.SetOpacity3D(0.55)

            reviewMetadataWarning = (
                self.logic.applyTeethSegmentationReviewMetadata(
                    segmentationNode,
                    sourceVolume,
                    report,
                    resultMetadataPath=resultPath,
                    segmentationNiftiPath=runPaths["output"],
                )
            )
            if reviewMetadataWarning:
                logging.warning(reviewMetadataWarning)

            # A new run gets a read-only inventory; loaded older runs wait for
            # the operator's Step 2 Check Pulp Masks action.
            self._setBackendStatus(_("Checking pulp masks for detected teeth..."), "working")
            slicer.app.processEvents()
            def updatePulpCheck(done, total, fdi, phase):
                phaseName = phase or _("Checking inventory")
                if fdi:
                    phaseName = _("%1 for FDI%2").replace("%1", phaseName).replace("%2", str(fdi))
                self._setBackendStatus(
                    _("Checking pulp masks: %1 (%2 of %3)...")
                    .replace("%1", phaseName)
                    .replace("%2", str(done)).replace("%3", str(total)), "working",
                )
                slicer.app.processEvents()
            try:
                pulpReport = self.logic.checkPulpInventory(segmentationNode, progress=updatePulpCheck)
            except (TypeError, ValueError, RuntimeError) as exc:
                logging.warning("Automatic pulp inventory failed for run %s: %s", runContext["runId"], exc)
                pulpReport = None

            parameterNode = self.logic.getParameterNode()
            sourceWasInspected = parameterNode.inspectedVolume == sourceVolume
            sourceVolume.SetNodeReferenceID("DENTOBOT.InspectedRun", segmentationNode.GetID())
            if sourceWasInspected:
                self.selectInspectionContext(sourceVolume, segmentationNode)
            else:
                segmentationNode.GetDisplayNode().SetVisibility(False)
            if self._parameterNode:
                self._updateBackendControls()
                self.ui.backendCollapsibleButton.collapsed = True
                self.ui.segmentationReviewCollapsibleButton.collapsed = False
        except Exception:
            if segmentationNode:
                slicer.mrmlScene.RemoveNode(segmentationNode)
            raise
        finally:
            if labelmapNode:
                slicer.mrmlScene.RemoveNode(labelmapNode)
            if colorTableNode:
                slicer.mrmlScene.RemoveNode(colorTableNode)

        completion = _(
            "Completed for %1 — %2 validated segments. Review result before use."
        ).replace("%1", sourceVolume.GetName() or _("Unnamed scan")).replace(
            "%2", str(report["metrics"]["segmentCount"])
        )
        if not sourceWasInspected:
            completion += _(" Current inspection was preserved; select this scan to review it.")
        if pulpReport:
            pulpCounts = pulpReport["counts"]
            completion += _(" Pulp check: %1 associated, %2 missing, %3 need attention. Open Step 2 for details.")\
                .replace("%1", str(pulpCounts["associated"]))\
                .replace("%2", str(pulpCounts["missing"]))\
                .replace("%3", str(pulpCounts["ambiguous"] + pulpCounts["cannot-evaluate"]))
        else:
            completion += _(" Pulp check could not finish; use Check Pulp Masks in Step 2.")
        self._setBackendStatus(completion, "success")
        if sourceWasInspected:
            self._updatePulpInventoryControls()

    def _completeRoundTrip(self, runContext: dict, returnCode: int) -> None:
        runPaths = runContext["paths"]
        resultPath = runPaths["result"]
        if not resultPath.is_file():
            raise RuntimeError(
                _("The backend did not create the expected result JSON document.")
            )

        report = json.loads(resultPath.read_text(encoding="utf-8"))
        if report.get("schemaVersion") != "1.0" or report.get("command") != "roundtrip":
            raise RuntimeError(_("The backend result contract is not supported."))
        if report.get("runId") != runContext["runId"]:
            raise RuntimeError(_("The result run ID does not match the requested run."))
        if returnCode != 0 or report.get("status") != "ok":
            errors = report.get("errors") or [
                _("Round trip failed with exit code %1.").replace("%1", str(returnCode))
            ]
            raise RuntimeError(" ".join(str(error) for error in errors))
        if not report.get("geometryMatch") or not report.get("dataMatch"):
            raise RuntimeError(_("Backend round-trip validation did not pass."))
        if not runPaths["output"].is_file():
            raise RuntimeError(_("The expected round-trip NIfTI is missing."))

        sourceVolume = slicer.mrmlScene.GetNodeByID(runContext["sourceVolumeId"])
        if not sourceVolume:
            raise RuntimeError(_("The source CBCT volume is no longer in the scene."))

        outputVolume = slicer.util.loadVolume(
            str(runPaths["output"]),
            {"name": f"DENTOBOT_RoundTrip_{runContext['runId'][:8]}"},
        )
        if not outputVolume:
            raise RuntimeError(_("Slicer could not import the round-trip NIfTI."))
        outputVolume.SetName(f"DENTOBOT_RoundTrip_{runContext['runId'][:8]}")

        try:
            self.logic.validateMatchingVolumeGeometry(sourceVolume, outputVolume)
        except Exception:
            slicer.mrmlScene.RemoveNode(outputVolume)
            raise

        outputVolume.SetAttribute("DENTOBOT.BridgeOperation", "roundtrip")
        outputVolume.SetAttribute("DENTOBOT.RunId", runContext["runId"])
        outputVolume.SetAttribute("DENTOBOT.SourceVolumeID", sourceVolume.GetID())
        outputVolume.SetAttribute("DENTOBOT.ResultMetadataPath", str(resultPath))

        parameterNode = self.logic.getParameterNode()
        parameterNode.roundTripVolume = outputVolume
        if self._parameterNode:
            self._updateBackendControls()
        self._setBackendStatus(
            _(
                "Round trip passed for %1. Geometry and voxel data were validated; "
                "the returned volume is now in the MRML scene."
            ).replace("%1", sourceVolume.GetName() or _("Unnamed volume")),
            "success",
        )
