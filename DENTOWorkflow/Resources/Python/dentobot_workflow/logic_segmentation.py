"""Extracted trajectory math and segmentation review methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


class SegmentationLogicMixin:
    @staticmethod
    def labelTrajectoryControlPoints(
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> None:
        """Apply explicit Entry and Target labels to defined control points."""

        if not trajectoryNode or not trajectoryNode.IsA(
            "vtkMRMLMarkupsLineNode"
        ):
            raise ValueError(_("Select a valid trajectory line node."))
        labels = ("Entry", "Target")
        pointCount = min(
            trajectoryNode.GetNumberOfDefinedControlPoints(),
            len(labels),
        )
        for index in range(pointCount):
            if trajectoryNode.GetNthControlPointLabel(index) != labels[index]:
                trajectoryNode.SetNthControlPointLabel(index, labels[index])

    @staticmethod
    def formatRasPoint(point: list[float] | tuple[float, ...]) -> str:
        """Format one world-RAS point for a compact read-only UI value."""

        if not point or len(point) != 3:
            raise ValueError(_("A three-component RAS point is required."))
        return f"{point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f} mm"

    def getTrajectorySummary(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> dict:
        """Return current world-RAS points and length for a trajectory line."""

        if not trajectoryNode or not trajectoryNode.IsA(
            "vtkMRMLMarkupsLineNode"
        ):
            raise ValueError(_("Select a valid trajectory line node."))
        self.enforceTrajectoryControlPointInvariant(trajectoryNode)

        pointCount = trajectoryNode.GetNumberOfDefinedControlPoints()
        if pointCount < 0 or pointCount > 2:
            raise ValueError(
                _("The trajectory line contains an invalid number of points.")
            )
        points: list[list[float]] = []
        for index in range(pointCount):
            point = [0.0, 0.0, 0.0]
            trajectoryNode.GetNthControlPointPositionWorld(index, point)
            points.append(point)

        entryRas = points[0] if pointCount >= 1 else None
        targetRas = points[1] if pointCount >= 2 else None
        lengthMm = None
        if entryRas is not None and targetRas is not None:
            lengthMm = float(
                vtk.vtkMath.Distance2BetweenPoints(entryRas, targetRas) ** 0.5
            )
        return {
            "definedPointCount": pointCount,
            "entryRas": entryRas,
            "targetRas": targetRas,
            "lengthMm": lengthMm,
            "isValid": bool(lengthMm is not None and lengthMm > 1e-6),
        }

    @staticmethod
    def computeTrajectoryFrame(
        entryRas,
        targetRas,
        *,
        epsilon: float = 1e-6,
        parallelThreshold: float = 0.95,
    ) -> dict:
        """Return a stable right-handed world-RAS frame around Entry→Target."""

        try:
            entry = np.asarray(entryRas, dtype=float)
            target = np.asarray(targetRas, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError(_("Entry and Target must be numeric RAS points.")) from exc
        if (
            entry.shape != (3,)
            or target.shape != (3,)
            or not np.all(np.isfinite(entry))
            or not np.all(np.isfinite(target))
        ):
            raise ValueError(_("Entry and Target must be finite three-component RAS points."))
        epsilonValue = float(epsilon)
        threshold = float(parallelThreshold)
        if not math.isfinite(epsilonValue) or epsilonValue <= 0.0:
            raise ValueError(_("Trajectory frame epsilon must be finite and positive."))
        if not math.isfinite(threshold) or not 0.0 < threshold < 1.0:
            raise ValueError(_("Trajectory reference threshold must be between zero and one."))

        direction = target - entry
        lengthMm = float(np.linalg.norm(direction))
        if not math.isfinite(lengthMm) or lengthMm <= epsilonValue:
            raise ValueError(_("Entry and Target must define a non-zero trajectory."))
        zAxis = direction / lengthMm
        reference = np.asarray((0.0, 0.0, 1.0), dtype=float)
        if abs(float(np.dot(reference, zAxis))) > threshold:
            reference = np.asarray((0.0, 1.0, 0.0), dtype=float)
        xAxis = np.cross(reference, zAxis)
        xLength = float(np.linalg.norm(xAxis))
        if not math.isfinite(xLength) or xLength <= epsilonValue:
            raise ValueError(_("Could not construct a transverse trajectory axis."))
        xAxis /= xLength
        yAxis = np.cross(zAxis, xAxis)
        yLength = float(np.linalg.norm(yAxis))
        if not math.isfinite(yLength) or yLength <= epsilonValue:
            raise ValueError(_("Could not construct an orthogonal trajectory frame."))
        yAxis /= yLength

        basis = np.column_stack((xAxis, yAxis, zAxis))
        if not np.allclose(basis.T @ basis, np.eye(3), atol=1e-8):
            raise ValueError(_("The computed trajectory frame is not orthonormal."))
        if float(np.linalg.det(basis)) <= 0.0:
            raise ValueError(_("The computed trajectory frame is not right-handed."))
        return {
            "entry": tuple(float(value) for value in entry),
            "target": tuple(float(value) for value in target),
            "midpoint": tuple(float(value) for value in (entry + target) * 0.5),
            "trajectory": tuple(float(value) for value in zAxis),
            "transverseX": tuple(float(value) for value in xAxis),
            "transverseY": tuple(float(value) for value in yAxis),
            "reference": tuple(float(value) for value in reference),
            "lengthMm": lengthMm,
        }

    @classmethod
    def computeTrajectorySliceMatrix(
        cls,
        entryRas,
        targetRas,
        angleDeg: float,
    ) -> vtk.vtkMatrix4x4:
        """Build SliceToRAS with trajectory vertical and contained in-plane."""

        angle = float(angleDeg)
        if not math.isfinite(angle):
            raise ValueError(_("Trajectory verification rotation must be finite."))
        frame = cls.computeTrajectoryFrame(entryRas, targetRas)
        xAxis = np.asarray(frame["transverseX"], dtype=float)
        yAxis = np.asarray(frame["transverseY"], dtype=float)
        zAxis = np.asarray(frame["trajectory"], dtype=float)
        theta = math.radians(angle)
        xRotated = math.cos(theta) * xAxis + math.sin(theta) * yAxis
        xRotated /= np.linalg.norm(xRotated)
        sliceNormal = np.cross(xRotated, zAxis)
        normalLength = float(np.linalg.norm(sliceNormal))
        if not math.isfinite(normalLength) or normalLength <= 1e-8:
            raise ValueError(_("Could not construct the longitudinal slice normal."))
        sliceNormal /= normalLength

        # Slicer's SliceToRAS columns are slice X, slice Y, slice normal, and
        # translation. Keeping the trajectory in column 1 makes Entry→Target
        # vertical in the 2D view; it is deliberately not the plane normal.
        matrix = vtk.vtkMatrix4x4()
        matrix.Identity()
        for row in range(3):
            matrix.SetElement(row, 0, float(xRotated[row]))
            matrix.SetElement(row, 1, float(zAxis[row]))
            matrix.SetElement(row, 2, float(sliceNormal[row]))
            matrix.SetElement(row, 3, float(frame["midpoint"][row]))
        return matrix

    @classmethod
    def transportTrajectorySliceMatrix(
        cls,
        previousSliceToRas,
        entryRas,
        targetRas,
        angleDeltaDeg: float = 0.0,
    ) -> vtk.vtkMatrix4x4:
        """Keep the prior longitudinal plane continuous across trajectory edits.

        The previous plane normal is projected onto the plane perpendicular to
        the corrected Entry→Target axis. This is the smallest normal change
        that makes the new trajectory lie in-plane. A slider delta is then
        applied around that corrected axis. If the new trajectory is parallel
        to the old normal, preserving the old plane is impossible; the prior
        horizontal axis supplies a stable finite fallback.
        """

        if not previousSliceToRas:
            raise ValueError(_("A previous SliceToRAS matrix is required."))
        angleDelta = float(angleDeltaDeg)
        if not math.isfinite(angleDelta):
            raise ValueError(_("Trajectory verification rotation delta must be finite."))
        frame = cls.computeTrajectoryFrame(entryRas, targetRas)
        zAxis = np.asarray(frame["trajectory"], dtype=float)
        previousX = np.asarray(
            [previousSliceToRas.GetElement(row, 0) for row in range(3)],
            dtype=float,
        )
        previousNormal = np.asarray(
            [previousSliceToRas.GetElement(row, 2) for row in range(3)],
            dtype=float,
        )
        if not np.all(np.isfinite(previousX)) or not np.all(
            np.isfinite(previousNormal)
        ):
            raise ValueError(_("The previous trajectory slice axes must be finite."))

        normalCandidate = previousNormal - np.dot(previousNormal, zAxis) * zAxis
        normalLength = float(np.linalg.norm(normalCandidate))
        if math.isfinite(normalLength) and normalLength > 1e-8:
            transportedNormal = normalCandidate / normalLength
            transportedX = np.cross(zAxis, transportedNormal)
        else:
            xCandidate = previousX - np.dot(previousX, zAxis) * zAxis
            xLength = float(np.linalg.norm(xCandidate))
            if not math.isfinite(xLength) or xLength <= 1e-8:
                raise ValueError(_("Could not transport the prior trajectory slice plane."))
            transportedX = xCandidate / xLength

        transportedXLength = float(np.linalg.norm(transportedX))
        if not math.isfinite(transportedXLength) or transportedXLength <= 1e-8:
            raise ValueError(_("Could not construct the transported slice X axis."))
        transportedX /= transportedXLength
        transportedY = np.cross(zAxis, transportedX)
        theta = math.radians(angleDelta)
        xRotated = (
            math.cos(theta) * transportedX
            + math.sin(theta) * transportedY
        )
        xRotated /= np.linalg.norm(xRotated)
        sliceNormal = np.cross(xRotated, zAxis)
        sliceNormal /= np.linalg.norm(sliceNormal)

        basis = np.column_stack((xRotated, zAxis, sliceNormal))
        if not np.allclose(basis.T @ basis, np.eye(3), atol=1e-8):
            raise ValueError(_("The transported trajectory slice is not orthonormal."))
        if float(np.linalg.det(basis)) <= 0.0:
            raise ValueError(_("The transported trajectory slice is not right-handed."))

        matrix = vtk.vtkMatrix4x4()
        matrix.Identity()
        for row in range(3):
            matrix.SetElement(row, 0, float(xRotated[row]))
            matrix.SetElement(row, 1, float(zAxis[row]))
            matrix.SetElement(row, 2, float(sliceNormal[row]))
            matrix.SetElement(row, 3, float(frame["midpoint"][row]))
        return matrix

    def startTrajectoryPlacement(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> None:
        """Activate Slicer's one-at-a-time Markups placement for this line."""

        summary = self.getTrajectorySummary(trajectoryNode)
        if summary["definedPointCount"] >= 2:
            raise ValueError(
                _(
                    "The trajectory already has Entry and Target points. Move "
                    "them in a view or remove them in Markups before placing "
                    "again."
                )
            )
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if not selectionNode:
            raise RuntimeError(_("Slicer's selection node is unavailable."))
        selectionNode.SetReferenceActivePlaceNodeClassName(
            "vtkMRMLMarkupsLineNode"
        )
        selectionNode.SetActivePlaceNodeID(trajectoryNode.GetID())
        slicer.modules.markups.logic().StartPlaceMode(0)
        # Slicer 5.12 resets the active placement class to Fiducial when
        # StartPlaceMode is called. Reassert the selected line afterwards so
        # view clicks populate this two-point line instead of creating F_*
        # fiducial lists.
        selectionNode.SetActivePlaceNodeClassName(
            "vtkMRMLMarkupsLineNode"
        )
        selectionNode.SetActivePlaceNodeID(trajectoryNode.GetID())
        if (
            selectionNode.GetActivePlaceNodeID() != trajectoryNode.GetID()
            or selectionNode.GetActivePlaceNodeClassName()
            != "vtkMRMLMarkupsLineNode"
            or not selectionNode.GetActivePlaceNodePlacementValid()
        ):
            self.stopTrajectoryPlacement()
            raise RuntimeError(
                _("Slicer could not activate the selected trajectory line.")
            )

    @staticmethod
    def startLinePlacement(lineNode: vtkMRMLMarkupsLineNode) -> None:
        """Activate one-at-a-time placement for an arbitrary two-point line."""

        if not lineNode or not lineNode.IsA("vtkMRMLMarkupsLineNode"):
            raise ValueError(_("Select a Markups line before placing points."))
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if not selectionNode:
            raise RuntimeError(_("Slicer's selection node is unavailable."))
        selectionNode.SetReferenceActivePlaceNodeClassName(
            "vtkMRMLMarkupsLineNode"
        )
        selectionNode.SetActivePlaceNodeID(lineNode.GetID())
        slicer.modules.markups.logic().StartPlaceMode(0)
        selectionNode.SetActivePlaceNodeClassName("vtkMRMLMarkupsLineNode")
        selectionNode.SetActivePlaceNodeID(lineNode.GetID())
        if (
            selectionNode.GetActivePlaceNodeID() != lineNode.GetID()
            or selectionNode.GetActivePlaceNodeClassName()
            != "vtkMRMLMarkupsLineNode"
            or not selectionNode.GetActivePlaceNodePlacementValid()
        ):
            DENTOWorkflowLogic.stopTrajectoryPlacement()
            raise RuntimeError(_("Slicer could not activate the selected line."))

    @staticmethod
    def stopTrajectoryPlacement() -> None:
        """Return Slicer to view interaction without altering line geometry."""

        interactionNode = (
            slicer.app.applicationLogic().GetInteractionNode()
        )
        if not interactionNode:
            raise RuntimeError(_("Slicer's interaction node is unavailable."))
        interactionNode.SwitchToViewTransformMode()

    def applyTeethSegmentationReviewMetadata(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        sourceVolume: vtkMRMLScalarVolumeNode | None,
        report: dict,
        resultMetadataPath: str | Path | None = None,
        segmentationNiftiPath: str | Path | None = None,
    ) -> str:
        """Persist validated Bridge C provenance and per-label metrics in MRML."""

        segmentation, _displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        runId = str(report.get("runId") or "")
        self.validateTeethSegmentationReport(report, runId)
        if report.get("status") != "ok":
            raise ValueError(_("Only a successful segmentation can be reviewed."))

        labelsById = {
            int(label["id"]): label
            for label in report["labels"]
        }
        metricsById = {
            int(metric["id"]): metric
            for metric in report["metrics"]["perLabel"]
        }
        metricsByName = {
            str(metric["name"]): metric
            for metric in report["metrics"]["perLabel"]
        }
        segmentIds = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(segmentIds)
        segmentMetrics = []
        unmatchedSegmentNames = []
        for index in range(segmentIds.GetNumberOfValues()):
            segmentId = segmentIds.GetValue(index)
            segment = segmentation.GetSegment(segmentId)
            if not segment:
                continue
            sourceName = str(segment.GetName() or "")
            labelValue = int(segment.GetLabelValue())
            metric = metricsById.get(labelValue) or metricsByName.get(sourceName)
            if not metric:
                unmatchedSegmentNames.append(sourceName or segmentId)
                continue
            labelId = int(metric["id"])
            label = labelsById.get(labelId)
            segmentMetrics.append(
                {
                    "segmentId": segmentId,
                    "labelId": labelId,
                    "sourceName": str(
                        label["name"] if label else metric["name"]
                    ),
                    "voxelCount": int(metric["voxelCount"]),
                    "volumeMm3": float(metric["volumeMm3"]),
                }
            )

        metadataStatus = (
            "complete"
            if len(segmentMetrics) == int(report["metrics"]["segmentCount"])
            and not unmatchedSegmentNames
            else "partial"
        )
        metricsDocument = {
            "schemaVersion": self.REVIEW_METADATA_VERSION,
            "status": metadataStatus,
            "segments": segmentMetrics,
        }

        backend = report["backend"]
        packages = backend["packages"]
        model = report["model"]
        device = report["device"]
        metrics = report["metrics"]
        wasModifying = segmentationNode.StartModify()
        try:
            segmentationNode.SetAttribute(
                "DENTOBOT.BridgeOperation",
                "segment-teeth",
            )
            segmentationNode.SetAttribute("DENTOBOT.RunId", runId)
            if sourceVolume:
                segmentationNode.SetAttribute(
                    "DENTOBOT.SourceVolumeID",
                    sourceVolume.GetID(),
                )
                segmentationNode.SetNodeReferenceID(
                    self.SOURCE_VOLUME_REFERENCE_ROLE,
                    sourceVolume.GetID(),
                )
            if resultMetadataPath is not None:
                segmentationNode.SetAttribute(
                    "DENTOBOT.ResultMetadataPath",
                    str(resultMetadataPath),
                )
            if segmentationNiftiPath is not None:
                segmentationNode.SetAttribute(
                    "DENTOBOT.SegmentationNiftiPath",
                    str(segmentationNiftiPath),
                )
            segmentationNode.SetAttribute(
                "DENTOBOT.ModelTask",
                str(model["task"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ModelTaskId",
                str(model["taskId"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ModelSourceDataset",
                str(model.get("sourceDataset") or ""),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.CropTask",
                str(model.get("cropTask") or ""),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.CropTaskId",
                str(model["cropTaskId"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.BackendName",
                str(backend.get("name") or "dentobot-inference"),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.BackendVersion",
                str(backend.get("version") or ""),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.PythonVersion",
                str(backend.get("pythonVersion") or ""),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.PackageVersionsJson",
                json.dumps(packages, sort_keys=True, separators=(",", ":")),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.TotalSegmentatorVersion",
                str(packages["TotalSegmentator"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.RequestedDevice",
                str(device["requested"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ActualDevice",
                str(device["actual"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.RuntimeSeconds",
                str(report["runtimeSeconds"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.InferenceSeconds",
                str(report["inferenceSeconds"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.StartedAtUtc",
                str(report.get("startedAtUtc") or ""),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.CompletedAtUtc",
                str(report.get("completedAtUtc") or ""),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.SegmentCount",
                str(metrics["segmentCount"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ForegroundVolumeMm3",
                str(metrics["foregroundVolumeMm3"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.PeakAllocatedBytes",
                (
                    str(device["peakAllocatedBytes"])
                    if device["peakAllocatedBytes"] is not None
                    else ""
                ),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.SegmentMetricsJson",
                json.dumps(
                    metricsDocument,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewMetadataVersion",
                self.REVIEW_METADATA_VERSION,
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewMetadataStatus",
                metadataStatus,
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.SegmentMetricsValidity",
                (
                    "pre-correction-inference"
                    if segmentationNode.GetAttribute(
                        "DENTOBOT.CorrectionStartedUtc"
                    )
                    else "current"
                ),
            )
            if not segmentationNode.GetAttribute("DENTOBOT.ReviewState"):
                segmentationNode.SetAttribute(
                    "DENTOBOT.ReviewState",
                    self.REVIEW_STATES[0],
                )
        finally:
            segmentationNode.EndModify(wasModifying)

        if unmatchedSegmentNames:
            return _(
                "Per-label metrics could not be matched for: %1"
            ).replace("%1", ", ".join(unmatchedSegmentNames))
        return ""

    def ensureSegmentationReviewMetadata(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> str:
        """Migrate one older Bridge C result from its retained result.json."""

        self._segmentationAndDisplayNode(segmentationNode)
        if not segmentationNode.GetAttribute("DENTOBOT.ReviewState"):
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewState",
                self.REVIEW_STATES[0],
            )

        sourceVolume = segmentationNode.GetNodeReference(
            self.SOURCE_VOLUME_REFERENCE_ROLE
        )
        if not sourceVolume:
            sourceVolumeId = segmentationNode.GetAttribute(
                "DENTOBOT.SourceVolumeID"
            )
            sourceVolume = (
                slicer.mrmlScene.GetNodeByID(sourceVolumeId)
                if sourceVolumeId
                else None
            )
            if sourceVolume:
                segmentationNode.SetNodeReferenceID(
                    self.SOURCE_VOLUME_REFERENCE_ROLE,
                    sourceVolume.GetID(),
                )

        if (
            segmentationNode.GetAttribute("DENTOBOT.ReviewMetadataVersion")
            == self.REVIEW_METADATA_VERSION
            and segmentationNode.GetAttribute("DENTOBOT.SegmentMetricsJson")
        ):
            return ""

        resultPathText = segmentationNode.GetAttribute(
            "DENTOBOT.ResultMetadataPath"
        )
        if not resultPathText:
            return _(
                "Per-label metrics are unavailable because no result metadata "
                "path is stored on this segmentation."
            )
        resultPath = Path(resultPathText)
        if not resultPath.is_file():
            return _(
                "Per-label metrics are unavailable because the retained "
                "result.json file cannot be found."
            )
        try:
            report = json.loads(resultPath.read_text(encoding="utf-8"))
            runId = segmentationNode.GetAttribute("DENTOBOT.RunId") or ""
            self.validateTeethSegmentationReport(report, runId)
            return self.applyTeethSegmentationReviewMetadata(
                segmentationNode,
                sourceVolume,
                report,
                resultMetadataPath=resultPath,
                segmentationNiftiPath=segmentationNode.GetAttribute(
                    "DENTOBOT.SegmentationNiftiPath"
                ),
            )
        except Exception as exc:
            logging.warning(
                "Could not migrate DENTOBOT segmentation review metadata: %s",
                exc,
            )
            return _(
                "Per-label metrics could not be restored from result.json: %1"
            ).replace("%1", str(exc))

    def getSegmentationSegmentDetails(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> dict:
        """Return one selected segment's identity and quantitative metadata."""

        records = self.getSegmentationReviewRecords(segmentationNode)
        record = next(
            (
                candidate
                for candidate in records
                if candidate["segmentId"] == segmentId
            ),
            None,
        )
        if not record:
            raise ValueError(_("The selected segment does not exist."))

        metric = None
        metricsText = segmentationNode.GetAttribute(
            "DENTOBOT.SegmentMetricsJson"
        )
        if metricsText:
            try:
                metricsDocument = json.loads(metricsText)
                if (
                    metricsDocument.get("schemaVersion")
                    == self.REVIEW_METADATA_VERSION
                ):
                    metric = next(
                        (
                            candidate
                            for candidate in metricsDocument.get("segments", [])
                            if candidate.get("segmentId") == segmentId
                        ),
                        None,
                    )
            except (json.JSONDecodeError, AttributeError, TypeError):
                metric = None

        return {
            **record,
            "labelId": metric.get("labelId") if metric else None,
            "voxelCount": metric.get("voxelCount") if metric else None,
            "volumeMm3": metric.get("volumeMm3") if metric else None,
            "runId": segmentationNode.GetAttribute("DENTOBOT.RunId") or "",
            "metricsValidity": (
                segmentationNode.GetAttribute(
                    "DENTOBOT.SegmentMetricsValidity"
                )
                or "current"
            ),
        }

    def getSegmentationProvenance(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> dict[str, str]:
        """Return compact, presentation-ready provenance from MRML attributes."""

        self._segmentationAndDisplayNode(segmentationNode)
        sourceVolume = segmentationNode.GetNodeReference(
            self.SOURCE_VOLUME_REFERENCE_ROLE
        )
        sourceVolumeText = (
            sourceVolume.GetName() or _("Unnamed volume")
            if sourceVolume
            else segmentationNode.GetAttribute("DENTOBOT.SourceVolumeID")
            or _("Unavailable")
        )
        packages = {}
        packagesText = segmentationNode.GetAttribute(
            "DENTOBOT.PackageVersionsJson"
        )
        if packagesText:
            try:
                packages = json.loads(packagesText)
            except (json.JSONDecodeError, TypeError):
                packages = {}

        backendName = (
            segmentationNode.GetAttribute("DENTOBOT.BackendName")
            or "dentobot-inference"
        )
        backendVersion = (
            segmentationNode.GetAttribute("DENTOBOT.BackendVersion")
            or _("unknown")
        )
        totalSegmentatorVersion = (
            packages.get("TotalSegmentator")
            or segmentationNode.GetAttribute(
                "DENTOBOT.TotalSegmentatorVersion"
            )
            or _("unknown")
        )
        modelTask = (
            segmentationNode.GetAttribute("DENTOBOT.ModelTask")
            or _("unknown")
        )
        modelTaskId = (
            segmentationNode.GetAttribute("DENTOBOT.ModelTaskId")
            or _("unknown")
        )
        sourceDataset = (
            segmentationNode.GetAttribute("DENTOBOT.ModelSourceDataset")
            or _("unknown dataset")
        )
        cropTask = (
            segmentationNode.GetAttribute("DENTOBOT.CropTask")
            or _("unknown crop")
        )
        cropTaskId = (
            segmentationNode.GetAttribute("DENTOBOT.CropTaskId")
            or _("unknown")
        )
        inferenceSeconds = segmentationNode.GetAttribute(
            "DENTOBOT.InferenceSeconds"
        )
        runtimeSeconds = segmentationNode.GetAttribute(
            "DENTOBOT.RuntimeSeconds"
        )
        timingText = _("Unavailable")
        if inferenceSeconds and runtimeSeconds:
            timingText = (
                _("%1 s inference; %2 s total")
                .replace("%1", f"{float(inferenceSeconds):.1f}")
                .replace("%2", f"{float(runtimeSeconds):.1f}")
            )

        return {
            "runId": segmentationNode.GetAttribute("DENTOBOT.RunId")
            or _("Unavailable"),
            "sourceVolume": sourceVolumeText,
            "backend": (
                f"{backendName} {backendVersion}; "
                f"TotalSegmentator {totalSegmentatorVersion}"
            ),
            "model": (
                f"{modelTask} (task {modelTaskId}), {sourceDataset}; "
                f"{cropTask} crop (task {cropTaskId})"
            ),
            "device": segmentationNode.GetAttribute("DENTOBOT.ActualDevice")
            or _("Unavailable"),
            "timing": timingText,
            "completedAtUtc": segmentationNode.GetAttribute(
                "DENTOBOT.CompletedAtUtc"
            )
            or _("Unavailable"),
            "reviewState": self.getSegmentationReviewState(segmentationNode),
            "reviewUpdatedUtc": segmentationNode.GetAttribute(
                "DENTOBOT.ReviewUpdatedUtc"
            )
            or _("Not yet changed"),
            "lastSegmentationEditUtc": segmentationNode.GetAttribute(
                "DENTOBOT.LastSegmentationEditUtc"
            )
            or _("No edits recorded"),
            "correctionActivityUtc": (
                segmentationNode.GetAttribute(
                    "DENTOBOT.LastSegmentationEditUtc"
                )
                or segmentationNode.GetAttribute(
                    "DENTOBOT.CorrectionStartedUtc"
                )
                or _("No correction recorded")
            ),
            "metricsValidity": (
                segmentationNode.GetAttribute(
                    "DENTOBOT.SegmentMetricsValidity"
                )
                or "current"
            ),
        }

    def getSegmentationReviewState(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> str:
        self._segmentationAndDisplayNode(segmentationNode)
        state = (
            segmentationNode.GetAttribute("DENTOBOT.ReviewState")
            or self.REVIEW_STATES[0]
        )
        return state if state in self.REVIEW_STATES else self.REVIEW_STATES[0]

    def setSegmentationReviewState(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        state: str,
        updatedUtc: str | None = None,
    ) -> None:
        self._segmentationAndDisplayNode(segmentationNode)
        if state not in self.REVIEW_STATES:
            raise ValueError(_("The segmentation review state is invalid."))
        timestamp = updatedUtc or datetime.now(timezone.utc).isoformat()
        wasModifying = segmentationNode.StartModify()
        try:
            segmentationNode.SetAttribute("DENTOBOT.ReviewState", state)
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewUpdatedUtc",
                timestamp,
            )
            if state == "Reviewed":
                segmentationNode.SetAttribute(
                    "DENTOBOT.ReviewInvalidationReason",
                    None,
                )
        finally:
            segmentationNode.EndModify(wasModifying)

    def getSegmentationSourceVolume(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> vtkMRMLScalarVolumeNode:
        """Return the persisted source CBCT required by Segment Editor."""

        self._segmentationAndDisplayNode(segmentationNode)
        sourceVolume = segmentationNode.GetNodeReference(
            self.SOURCE_VOLUME_REFERENCE_ROLE
        )
        if not sourceVolume:
            sourceVolumeId = segmentationNode.GetAttribute(
                "DENTOBOT.SourceVolumeID"
            )
            sourceVolume = (
                slicer.mrmlScene.GetNodeByID(sourceVolumeId)
                if sourceVolumeId
                else None
            )
            if sourceVolume:
                segmentationNode.SetNodeReferenceID(
                    self.SOURCE_VOLUME_REFERENCE_ROLE,
                    sourceVolume.GetID(),
                )
        if (
            not sourceVolume
            or not sourceVolume.IsA("vtkMRMLScalarVolumeNode")
            or not sourceVolume.GetImageData()
        ):
            raise ValueError(
                _(
                    "The segmentation's source CBCT is unavailable. Restore "
                    "the source volume before correction."
                )
            )
        return sourceVolume

    def beginSegmentationCorrection(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
        startedUtc: str | None = None,
    ) -> dict[str, object]:
        """Validate an editor handoff and begin a conservative correction revision."""

        segmentation, _displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        if not segmentId or not segmentation.GetSegment(segmentId):
            raise ValueError(_("The selected segment does not exist."))
        sourceVolume = self.getSegmentationSourceVolume(segmentationNode)
        previous2DRenderingMode = self.getSegmentation2DRenderingMode(
            segmentationNode
        )
        self.setSegmentation2DRenderingMode(
            segmentationNode,
            self.SEGMENTATION_2D_RENDERING_MODE_NATIVE,
        )
        timestamp = startedUtc or datetime.now(timezone.utc).isoformat()
        wasModifying = segmentationNode.StartModify()
        try:
            segmentationNode.SetAttribute(
                "DENTOBOT.CorrectionStartedUtc",
                timestamp,
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.SegmentMetricsValidity",
                "pre-correction-inference",
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewState",
                "Needs Correction",
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewUpdatedUtc",
                timestamp,
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewInvalidationReason",
                "Correction workflow opened",
            )
        finally:
            segmentationNode.EndModify(wasModifying)
        logging.info(
            "DENTOBOT correction started for segment %s in node %s",
            segmentId,
            segmentationNode.GetID(),
        )
        return {
            "segmentationNode": segmentationNode,
            "sourceVolume": sourceVolume,
            "segmentId": segmentId,
            "previous2DRenderingMode": previous2DRenderingMode,
        }

    def invalidateSegmentationReviewAfterEdit(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        editedUtc: str | None = None,
    ) -> bool:
        """Record a mask edit and invalidate a previously reviewed result."""

        self._segmentationAndDisplayNode(segmentationNode)
        timestamp = editedUtc or datetime.now(timezone.utc).isoformat()
        wasReviewed = (
            self.getSegmentationReviewState(segmentationNode) == "Reviewed"
        )
        wasModifying = segmentationNode.StartModify()
        try:
            segmentationNode.SetAttribute(
                "DENTOBOT.LastSegmentationEditUtc",
                timestamp,
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.SegmentMetricsValidity",
                "pre-correction-inference",
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewInvalidationReason",
                "Segmentation mask content changed",
            )
            if wasReviewed:
                segmentationNode.SetAttribute(
                    "DENTOBOT.ReviewState",
                    "Needs Correction",
                )
                segmentationNode.SetAttribute(
                    "DENTOBOT.ReviewUpdatedUtc",
                    timestamp,
                )
        finally:
            segmentationNode.EndModify(wasModifying)
        logging.info(
            "DENTOBOT segmentation content change recorded for node %s; "
            "previously reviewed=%s",
            segmentationNode.GetID(),
            wasReviewed,
        )
        return wasReviewed

    @classmethod
    def describeSegmentForReview(cls, sourceName: str) -> dict[str, str | None]:
        """Create a stable human-facing category and FDI-aware display name."""

        if not isinstance(sourceName, str) or not sourceName.strip():
            raise ValueError(_("A segment name is required for review."))

        normalizedName = sourceName.strip().lower()
        fdiMatch = re.search(r"_fdi(\d+)$", normalizedName)
        sourceFdiCode = fdiMatch.group(1) if fdiMatch else None
        baseName = (
            normalizedName[: fdiMatch.start()]
            if fdiMatch
            else normalizedName
        )

        if "pulp" in baseName:
            category = "Pulp and root canals"
        elif "canal" in baseName:
            category = "Neural and mandibular canals"
        elif "jawbone" in baseName or baseName in ("mandible", "maxilla"):
            category = "Jaws"
        elif "sinus" in baseName or "pharynx" in baseName or "airway" in baseName:
            category = "Sinuses and airway"
        elif any(
            token in baseName
            for token in ("bridge", "crown", "implant", "restoration")
        ):
            category = "Restorations and implants"
        elif (
            sourceFdiCode
            and len(sourceFdiCode) == 2
            and sourceFdiCode[0] in "1234"
            and sourceFdiCode[1] in "12345678"
        ):
            category = "Teeth"
        else:
            category = "Other anatomy"

        fdiNumber = sourceFdiCode
        if (
            category == "Pulp and root canals"
            and sourceFdiCode
            and len(sourceFdiCode) == 3
            and sourceFdiCode.startswith("1")
            and sourceFdiCode[1] in "1234"
            and sourceFdiCode[2] in "12345678"
        ):
            fdiNumber = sourceFdiCode[1:]

        anatomyName = " ".join(
            word.capitalize() for word in baseName.split("_") if word
        )
        if fdiNumber:
            displayName = f"FDI {fdiNumber} \u2014 {anatomyName}"
        else:
            displayName = anatomyName

        return {
            "sourceName": sourceName.strip(),
            "displayName": displayName,
            "category": category,
            "fdiNumber": fdiNumber,
            "sourceFdiCode": sourceFdiCode,
            "searchText": " ".join(
                value.lower()
                for value in (
                    sourceName.strip(),
                    displayName,
                    category,
                    sourceFdiCode or "",
                    fdiNumber or "",
                )
                if value
            ),
        }

    def getSegmentationReviewRecords(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> list[dict]:
        """Return deterministic segment records for the Step 3A explorer."""

        segmentation, _displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        segmentIds = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(segmentIds)
        categoryOrder = {
            category: index
            for index, category in enumerate(self.SEGMENT_REVIEW_CATEGORY_ORDER)
        }
        records = []
        for index in range(segmentIds.GetNumberOfValues()):
            segmentId = segmentIds.GetValue(index)
            segment = segmentation.GetSegment(segmentId)
            if not segment:
                continue
            descriptor = self.describeSegmentForReview(segment.GetName())
            records.append(
                {
                    "segmentId": segmentId,
                    **descriptor,
                }
            )
        records.sort(
            key=lambda record: (
                categoryOrder.get(
                    record["category"],
                    len(categoryOrder),
                ),
                int(record["fdiNumber"])
                if record["fdiNumber"] and record["fdiNumber"].isdigit()
                else 9999,
                record["displayName"].lower(),
            )
        )
        return records
