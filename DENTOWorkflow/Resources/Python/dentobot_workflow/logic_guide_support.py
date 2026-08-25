"""Extracted guide support geometry and state methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


class GuideSupportLogicMixin:
    @staticmethod
    def encodeTemplateSupportSegmentIds(segmentIds: list[str]) -> str:
        """Serialize an ordered, unique list of manually selected support teeth."""

        if not isinstance(segmentIds, list):
            raise ValueError(_("Support-tooth segment IDs must be provided as a list."))
        normalizedIds = []
        seenIds = set()
        for value in segmentIds:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(_("Every support tooth must have a segment ID."))
            segmentId = value.strip()
            if segmentId in seenIds:
                raise ValueError(_("A support tooth cannot be selected more than once."))
            seenIds.add(segmentId)
            normalizedIds.append(segmentId)
        return json.dumps(normalizedIds, separators=(",", ":"))

    @staticmethod
    def decodeTemplateSupportSegmentIds(serializedIds: str) -> list[str]:
        """Read persisted support-tooth IDs without accepting malformed state."""

        try:
            values = json.loads(serializedIds or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError(_("Stored support-tooth selection is not valid JSON.")) from exc
        if not isinstance(values, list):
            raise ValueError(_("Stored support-tooth selection must be a list."))
        return DENTOWorkflowLogic._validateUniqueSegmentIdList(values)

    @staticmethod
    def _validateUniqueSegmentIdList(segmentIds: list) -> list[str]:
        normalizedIds = []
        seenIds = set()
        for value in segmentIds:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(_("Every support tooth must have a segment ID."))
            segmentId = value.strip()
            if segmentId in seenIds:
                raise ValueError(_("A support tooth cannot be selected more than once."))
            seenIds.add(segmentId)
            normalizedIds.append(segmentId)
        return normalizedIds

    def validateTemplateSupportSelection(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        targetSegmentId: str,
        supportSegmentIds: list[str],
    ) -> dict:
        """Validate one target plus any positive number of user-selected teeth."""

        targetRecord = self.validateTargetTooth(
            segmentationNode,
            targetSegmentId,
        )
        if self.getSegmentationReviewState(segmentationNode) != "Reviewed":
            raise ValueError(
                _(
                    "Mark the authoritative segmentation Reviewed before "
                    "creating a draft support-anatomy model."
                )
            )
        normalizedSupportIds = self._validateUniqueSegmentIdList(
            supportSegmentIds
        )
        if not normalizedSupportIds:
            raise ValueError(_("Select at least one support tooth."))
        if targetRecord["segmentId"] in normalizedSupportIds:
            raise ValueError(_("The target tooth cannot also be a support tooth."))

        toothRecordsById = {
            record["segmentId"]: record
            for record in self.getTargetToothRecords(segmentationNode)
        }
        supportRecords = []
        targetArch = self.dentalArchForFdi(targetRecord.get("fdiNumber") or "")
        if not targetArch:
            raise ValueError(
                _("The target tooth has no valid permanent-tooth FDI arch.")
            )
        for supportId in normalizedSupportIds:
            record = toothRecordsById.get(supportId)
            if not record:
                raise ValueError(
                    _(
                        "A selected support tooth does not exist or is not a "
                        "whole-tooth segment: %1"
                    ).replace("%1", supportId)
                )
            if self.dentalArchForFdi(record.get("fdiNumber") or "") != targetArch:
                raise ValueError(
                    _(
                        "Support tooth %1 is on the opposing jaw. Every support "
                        "must share the target tooth's arch."
                    ).replace("%1", record.get("displayName") or supportId)
                )
            supportRecords.append(record)
        return {
            "target": targetRecord,
            "supports": supportRecords,
            "supportSegmentIds": normalizedSupportIds,
        }

    @staticmethod
    def _getClosedSurfaceCopy(
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> vtk.vtkPolyData:
        closedSurface = vtk.vtkPolyData()
        success = (
            slicer.vtkSlicerSegmentationsModuleLogic
            .GetSegmentClosedSurfaceRepresentation(
                segmentationNode,
                segmentId,
                closedSurface,
            )
        )
        if (
            not success
            or closedSurface.GetNumberOfPoints() == 0
            or closedSurface.GetNumberOfCells() == 0
        ):
            raise ValueError(
                _(
                    "Selected tooth %1 has no usable closed-surface "
                    "representation."
                ).replace("%1", segmentId)
            )
        surfaceCopy = vtk.vtkPolyData()
        surfaceCopy.DeepCopy(closedSurface)
        return surfaceCopy

    @classmethod
    def _getClosedSurfaceWorldCopy(
        cls,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> vtk.vtkPolyData:
        # Slicer's segmentation closed-surface accessor already returns the
        # representation in world RAS, including any parent transform.  A
        # second transform here would displace Step 4B from the shell.
        return cls._getClosedSurfaceCopy(segmentationNode, segmentId)

    def createOrUpdateDraftTemplateSupportModel(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        targetSegmentId: str,
        supportSegmentIds: list[str],
        modelNode: vtkMRMLModelNode | None = None,
    ) -> tuple[vtkMRMLModelNode, dict]:
        """Create a traceable draft model from unmodified whole-tooth surfaces."""

        selection = self.validateTemplateSupportSelection(
            segmentationNode,
            targetSegmentId,
            supportSegmentIds,
        )
        records = [selection["target"], *selection["supports"]]
        appendFilter = vtk.vtkAppendPolyData()
        sourcePointCount = 0
        sourceCellCount = 0
        for record in records:
            surfaceCopy = self._getClosedSurfaceCopy(
                segmentationNode,
                record["segmentId"],
            )
            sourcePointCount += surfaceCopy.GetNumberOfPoints()
            sourceCellCount += surfaceCopy.GetNumberOfCells()
            appendFilter.AddInputData(surfaceCopy)
        if self.getSegmentationReviewState(segmentationNode) != "Reviewed":
            raise ValueError(
                _(
                    "The segmentation review state changed while source "
                    "surfaces were being collected. Review it again first."
                )
            )
        appendFilter.Update()

        combinedSurface = vtk.vtkPolyData()
        combinedSurface.DeepCopy(appendFilter.GetOutput())
        bounds = tuple(float(value) for value in combinedSurface.GetBounds())
        if (
            combinedSurface.GetNumberOfPoints() != sourcePointCount
            or combinedSurface.GetNumberOfCells() != sourceCellCount
            or len(bounds) != 6
            or any(not math.isfinite(value) for value in bounds)
        ):
            raise RuntimeError(
                _("The draft support-anatomy model failed geometry validation.")
            )

        reusedModel = bool(
            modelNode and modelNode.IsA("vtkMRMLModelNode")
        )
        previousVisibility = bool(
            reusedModel
            and modelNode.GetDisplayNode()
            and modelNode.GetDisplayNode().GetVisibility()
        )
        if modelNode:
            if not modelNode.IsA("vtkMRMLModelNode"):
                raise ValueError(_("Select a valid draft model node."))
            if modelNode.GetAttribute("DENTOBOT.ModelRole") != "TemplateSupportDraft":
                raise ValueError(
                    _(
                        "The selected model is not a DENTOBOT draft "
                        "support-anatomy model."
                    )
                )
        else:
            modelNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
            )
        if not modelNode:
            raise RuntimeError(_("Slicer could not create the draft support model."))

        targetFdi = selection["target"].get("fdiNumber") or "Unknown"
        supportCount = len(selection["supports"])
        modelName = (
            f"[Step 4B] DENTO Template Support FDI {targetFdi} + "
            f"{supportCount} {'Teeth' if supportCount != 1 else 'Tooth'} Draft"
        )
        wasModifying = modelNode.StartModify()
        try:
            modelNode.SetName(modelName)
            modelNode.SetAndObservePolyData(combinedSurface)
            # GetSegmentClosedSurfaceRepresentation returns world-RAS geometry.
            # Do not retain the segmentation's parent transform or the model
            # would be transformed a second time in display/processing.
            modelNode.SetAndObserveTransformNodeID(None)
            modelNode.SetNodeReferenceID(
                self.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE,
                segmentationNode.GetID(),
            )
            modelNode.SetAttribute("DENTOBOT.ModelRole", "TemplateSupportDraft")
            modelNode.SetAttribute(
                "DENTOBOT.TemplateModelSchemaVersion",
                self.TEMPLATE_MODEL_SCHEMA_VERSION,
            )
            modelNode.SetAttribute("DENTOBOT.Status", "DraftResearchOnly")
            modelNode.SetAttribute("DENTOBOT.GeometryState", "Current")
            modelNode.SetAttribute("DENTOBOT.StaleReason", None)
            modelNode.SetAttribute("DENTOBOT.SupportSelectionLocked", "true")
            modelNode.SetAttribute(
                "DENTOBOT.CoordinateConvention",
                "WorldRASmm",
            )
            modelNode.SetAttribute(
                "DENTOBOT.TargetSegmentID",
                selection["target"]["segmentId"],
            )
            modelNode.SetAttribute(
                "DENTOBOT.TargetFdiNumber",
                selection["target"].get("fdiNumber") or "",
            )
            modelNode.SetAttribute(
                "DENTOBOT.SupportSegmentIDsJson",
                self.encodeTemplateSupportSegmentIds(
                    selection["supportSegmentIds"]
                ),
            )
            modelNode.SetAttribute(
                "DENTOBOT.SupportFdiNumbersJson",
                json.dumps(
                    [
                        record.get("fdiNumber") or ""
                        for record in selection["supports"]
                    ],
                    separators=(",", ":"),
                ),
            )
            modelNode.SetAttribute(
                "DENTOBOT.SupportCount",
                str(supportCount),
            )
            modelNode.SetAttribute(
                "DENTOBOT.SourceSegmentNamesJson",
                json.dumps(
                    {
                        record["segmentId"]: record["sourceName"]
                        for record in records
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            modelNode.SetAttribute(
                "DENTOBOT.SourceReviewUpdatedUtc",
                segmentationNode.GetAttribute("DENTOBOT.ReviewUpdatedUtc") or "",
            )
            modelNode.SetAttribute(
                "DENTOBOT.UpdatedUtc",
                datetime.now(timezone.utc).isoformat(),
            )
            modelNode.SetAttribute(
                "DENTOBOT.SourcePointCount",
                str(sourcePointCount),
            )
            modelNode.SetAttribute(
                "DENTOBOT.SourceCellCount",
                str(sourceCellCount),
            )
        finally:
            modelNode.EndModify(wasModifying)

        modelNode.CreateDefaultDisplayNodes()
        displayNode = modelNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(previousVisibility if reusedModel else True)
            displayNode.SetVisibility2D(False)
            displayNode.SetVisibility3D(True)
            displayNode.SetOpacity(0.65)
        targetTrajectories = self.dentobotTrajectoriesForTarget(
            segmentationNode,
            selection["target"]["segmentId"],
        )
        if targetTrajectories:
            self.setNodeLineageColor(
                modelNode,
                self.lineageColorForTarget(
                    selection["target"]["segmentId"],
                    selection["target"].get("fdiNumber") or "",
                ),
                selection["target"]["segmentId"],
                selection["target"].get("fdiNumber") or "",
            )
        else:
            self.clearNodeLineageColor(modelNode)
            if displayNode:
                displayNode.SetColor(0.15, 0.72, 0.82)

        return modelNode, {
            "target": selection["target"],
            "supports": selection["supports"],
            "supportCount": supportCount,
            "pointCount": combinedSurface.GetNumberOfPoints(),
            "cellCount": combinedSurface.GetNumberOfCells(),
            "bounds": bounds,
        }

    @staticmethod
    def isDraftTemplateSupportModelNode(modelNode) -> bool:
        return bool(
            modelNode
            and modelNode.IsA("vtkMRMLModelNode")
            and modelNode.GetAttribute("DENTOBOT.ModelRole")
            == "TemplateSupportDraft"
        )

    @classmethod
    def isTemplateSupportSelectionLocked(cls, modelNode) -> bool:
        """Return the persistent Step 4B ownership lock (legacy drafts lock)."""

        if not cls.isDraftTemplateSupportModelNode(modelNode):
            return False
        return (
            modelNode.GetAttribute("DENTOBOT.SupportSelectionLocked") or "true"
        ).strip().lower() != "false"

    def validateDraftTemplateSupportModelForDeletion(
        self,
        modelNode: vtkMRMLModelNode,
    ) -> None:
        if not self.isDraftTemplateSupportModelNode(modelNode):
            raise ValueError(
                _("Select a DENTOBOT Step 4B draft support model to delete.")
            )
        if not slicer.mrmlScene.IsNodePresent(modelNode):
            raise ValueError(_("The selected draft model is no longer in the scene."))

    def deleteDraftTemplateSupportModel(
        self,
        modelNode: vtkMRMLModelNode,
    ) -> dict:
        """Delete one Step 4B draft while preserving all source selections."""

        self.validateDraftTemplateSupportModelForDeletion(modelNode)
        parameterNode = self.getParameterNode()
        if parameterNode.draftTemplateSupportModel is modelNode:
            parameterNode.draftTemplateSupportModel = None
        return self._removeSceneNodeAndOwnedAuxiliaries(modelNode)

    @staticmethod
    def markDraftTemplateSupportModelStale(
        modelNode: vtkMRMLModelNode | None,
        reason: str,
    ) -> bool:
        """Mark only DENTOBOT draft support models stale without deleting them."""

        if (
            not modelNode
            or not modelNode.IsA("vtkMRMLModelNode")
            or modelNode.GetAttribute("DENTOBOT.ModelRole")
            != "TemplateSupportDraft"
        ):
            return False
        modelNode.SetAttribute("DENTOBOT.GeometryState", "Stale")
        modelNode.SetAttribute(
            "DENTOBOT.StaleReason",
            str(reason).strip() or "Source selection changed.",
        )
        return True

    def getDraftTemplateSupportModelSummary(
        self,
        modelNode: vtkMRMLModelNode,
    ) -> dict:
        """Return validated selection/provenance for one Step 4B draft."""

        if (
            not modelNode
            or not modelNode.IsA("vtkMRMLModelNode")
            or modelNode.GetAttribute("DENTOBOT.ModelRole")
            != "TemplateSupportDraft"
        ):
            raise ValueError(_("Select a DENTOBOT draft support model."))
        polyData = modelNode.GetPolyData()
        if (
            not polyData
            or polyData.GetNumberOfPoints() == 0
            or polyData.GetNumberOfCells() == 0
        ):
            raise ValueError(_("The draft support model contains no geometry."))
        sourceNode = modelNode.GetNodeReference(
            self.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE
        )
        if not sourceNode or not sourceNode.IsA("vtkMRMLSegmentationNode"):
            raise ValueError(
                _("The draft support model has no authoritative segmentation.")
            )
        supportIds = self.decodeTemplateSupportSegmentIds(
            modelNode.GetAttribute("DENTOBOT.SupportSegmentIDsJson") or "[]"
        )
        return {
            "sourceSegmentation": sourceNode,
            "targetSegmentId": modelNode.GetAttribute(
                "DENTOBOT.TargetSegmentID"
            ) or "",
            "supportSegmentIds": supportIds,
            "supportCount": len(supportIds),
            "selectionLocked": self.isTemplateSupportSelectionLocked(modelNode),
            "geometryState": modelNode.GetAttribute(
                "DENTOBOT.GeometryState"
            ) or "Unknown",
            "staleReason": modelNode.GetAttribute("DENTOBOT.StaleReason") or "",
            "pointCount": polyData.GetNumberOfPoints(),
            "cellCount": polyData.GetNumberOfCells(),
            "updatedUtc": modelNode.GetAttribute("DENTOBOT.UpdatedUtc") or "",
        }

    @staticmethod
    def isTemplateSupportBoundaryNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsClosedCurveNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole")
            == "TemplateSupportBoundary"
        )

    @staticmethod
    def isTemplateSupportBoundaryPlaneNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsPlaneNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole")
            == "TemplateSupportBoundaryPlane"
        )

    @staticmethod
    def isVisibleTemplateSupportModelNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLModelNode")
            and node.GetAttribute("DENTOBOT.ModelRole")
            == "VisibleTemplateSupportSurface"
        )

    def createOrResetTemplateSupportBoundary(
        self,
        sourceModel: vtkMRMLModelNode,
        curveNode: vtkMRMLMarkupsClosedCurveNode | None = None,
    ) -> vtkMRMLMarkupsClosedCurveNode:
        """Create one editable closed boundary on the current support anatomy."""

        sourceSummary = self.getDraftTemplateSupportModelSummary(sourceModel)
        if sourceSummary["geometryState"] != "Current":
            raise ValueError(_("Update the stale full support-anatomy model first."))
        if curveNode:
            if not self.isTemplateSupportBoundaryNode(curveNode):
                raise ValueError(_("Select a DENTOBOT visible-support boundary."))
            associatedSource = curveNode.GetNodeReference(
                self.TEMPLATE_SUPPORT_BOUNDARY_SOURCE_MODEL_REFERENCE_ROLE
            )
            if associatedSource is not sourceModel:
                raise ValueError(
                    _("The selected support boundary belongs to another support model.")
                )
        else:
            curveNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsClosedCurveNode",
                "[Step 5A] DENTO Visible Support Surface Boundary",
            )
        if not curveNode:
            raise RuntimeError(_("Slicer could not create the visible-support boundary."))

        wasModifying = curveNode.StartModify()
        try:
            curveNode.SetName("[Step 5A] DENTO Visible Support Surface Boundary")
            curveNode.RemoveAllControlPoints()
            curveNode.SetAttribute(
                "DENTOBOT.MarkupsRole",
                "TemplateSupportBoundary",
            )
            curveNode.SetAttribute(
                "DENTOBOT.TemplateSupportSurfaceSchemaVersion",
                self.TEMPLATE_SUPPORT_SURFACE_SCHEMA_VERSION,
            )
            curveNode.SetAttribute("DENTOBOT.Status", "ResearchOnly")
            curveNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
            curveNode.SetAttribute(
                "DENTOBOT.BoundaryMappingMethod",
                "PerConnectedSurfaceDijkstra",
            )
            curveNode.SetNodeReferenceID(
                self.TEMPLATE_SUPPORT_BOUNDARY_SOURCE_MODEL_REFERENCE_ROLE,
                sourceModel.GetID(),
            )
            # The selected tooth segments are separate closed surfaces.  Keep
            # the user-visible boundary continuous across interdental gaps;
            # geometry extraction maps it geodesically on each tooth instead.
            curveNode.SetCurveTypeToLinear()
            curveNode.SetAndObserveShortestDistanceSurfaceNode(None)
            if hasattr(curveNode, "SetCurveClosed"):
                curveNode.SetCurveClosed(True)
            curveNode.SetLocked(False)
            curveNode.SetSelectable(True)
        finally:
            curveNode.EndModify(wasModifying)

        curveNode.CreateDefaultDisplayNodes()
        displayNode = curveNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(True)
            displayNode.SetVisibility2D(True)
            displayNode.SetVisibility3D(True)
            displayNode.SetPointLabelsVisibility(False)
            displayNode.SetPropertiesLabelVisibility(False)
            displayNode.SetSnapMode(displayNode.SnapModeToVisibleSurface)
            displayNode.SetGlyphScale(1.35)
            displayNode.SetLineThickness(0.35)
            displayNode.SetSelectedColor(1.0, 0.55, 0.05)
            displayNode.SetColor(1.0, 0.72, 0.15)
        lineageColor = self.lineageColorFromNode(sourceModel)
        if lineageColor:
            self.setNodeLineageColor(
                curveNode,
                lineageColor,
                sourceModel.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE) or "",
                sourceModel.GetAttribute(self.LINEAGE_TARGET_FDI_ATTRIBUTE) or "",
            )
        return curveNode

    def createOrUpdateTemplateSupportBoundaryPlane(
        self,
        sourceModel: vtkMRMLModelNode,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        *,
        reverseDirection: bool = False,
        depthFromEntryMm: float = 3.0,
        crownCapPercent: float = 10.0,
        planeNode: vtkMRMLMarkupsPlaneNode | None = None,
    ) -> tuple[vtkMRMLMarkupsPlaneNode, dict]:
        """Create a locked plane normal to Entry→Target at one scalar depth."""

        sourceSummary = self.getDraftTemplateSupportModelSummary(sourceModel)
        if sourceSummary["geometryState"] != "Current":
            raise ValueError(_("Update the stale full support-anatomy model first."))
        direction = self.resolveTemplateSupportTrajectoryDirection(
            sourceModel,
            trajectoryNode,
            reverseDirection=reverseDirection,
        )
        depth = float(depthFromEntryMm)
        if not math.isfinite(depth) or depth < -10.0 or depth > 20.0:
            raise ValueError(_("Support-plane depth must be between -10 and 20 mm."))
        capPercent = float(crownCapPercent)
        if not math.isfinite(capPercent) or not 5.0 <= capPercent <= 30.0:
            raise ValueError(_("Crown-cap tilt fit must be between 5% and 30%."))
        entry = np.asarray(direction["entryRas"], dtype=float)
        insertion = np.asarray(direction["insertionDirectionRas"], dtype=float)
        origin = entry + depth * insertion
        segmentIds = [
            sourceSummary["targetSegmentId"],
            *sourceSummary["supportSegmentIds"],
        ]
        toothSurfaces = [
            {
                "segmentId": segmentId,
                "polyData": self._getClosedSurfaceCopy(
                    sourceSummary["sourceSegmentation"],
                    segmentId,
                ),
            }
            for segmentId in segmentIds
        ]
        planeNormal, tiltMetrics = estimate_crown_cap_support_plane_normal(
            toothSurfaces,
            insertion,
            crown_cap_fraction=capPercent / 100.0,
        )
        if planeNode:
            if not self.isTemplateSupportBoundaryPlaneNode(planeNode):
                raise ValueError(_("Select the DENTOBOT Step 5A support plane."))
            if planeNode.GetNodeReference(
                self.TEMPLATE_SUPPORT_PLANE_SOURCE_MODEL_REFERENCE_ROLE
            ) is not sourceModel:
                raise ValueError(_("The support plane belongs to another draft model."))
        else:
            planeNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsPlaneNode",
                "[Step 5A] DENTO Insertion-Aligned Support Plane",
            )
        if not planeNode:
            raise RuntimeError(_("Slicer could not create the Step 5A support plane."))

        bounds = [0.0] * 6
        sourceModel.GetRASBounds(bounds)
        diagonal = math.sqrt(
            sum(
                (bounds[2 * axis + 1] - bounds[2 * axis]) ** 2
                for axis in range(3)
            )
        )
        wasModifying = planeNode.StartModify()
        try:
            planeNode.SetName("[Step 5A] DENTO Insertion-Aligned Support Plane")
            planeNode.SetPlaneType(planeNode.PlaneTypePointNormal)
            if hasattr(planeNode, "SetNormalPointRequired"):
                planeNode.SetNormalPointRequired(False)
            planeNode.SetOriginWorld(tuple(float(value) for value in origin))
            planeNode.SetNormalWorld(planeNormal)
            planeNode.SetSize(max(diagonal * 1.15, 5.0), max(diagonal * 1.15, 5.0))
            planeNode.SetLocked(True)
            planeNode.SetSelectable(False)
            planeNode.SetAttribute(
                "DENTOBOT.MarkupsRole",
                "TemplateSupportBoundaryPlane",
            )
            planeNode.SetAttribute(
                "DENTOBOT.TemplateSupportSurfaceSchemaVersion",
                self.TEMPLATE_SUPPORT_SURFACE_SCHEMA_VERSION,
            )
            planeNode.SetAttribute("DENTOBOT.Status", "ResearchOnly")
            planeNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
            planeNode.SetAttribute("DENTOBOT.PlaneConstraint", "TrajectoryDepthOnly")
            planeNode.SetAttribute("DENTOBOT.DepthFromEntryMm", f"{depth:.9g}")
            planeNode.SetAttribute("DENTOBOT.CrownCapPercent", f"{capPercent:.9g}")
            planeNode.SetAttribute(
                "DENTOBOT.CrownCapTiltMetricsJson",
                json.dumps(tiltMetrics, sort_keys=True, separators=(",", ":")),
            )
            planeNode.SetAttribute(
                "DENTOBOT.DirectionGeometryJson",
                direction["directionGeometryJson"],
            )
            planeNode.SetNodeReferenceID(
                self.TEMPLATE_SUPPORT_PLANE_SOURCE_MODEL_REFERENCE_ROLE,
                sourceModel.GetID(),
            )
            planeNode.SetNodeReferenceID(
                self.TEMPLATE_SUPPORT_PLANE_SOURCE_TRAJECTORY_REFERENCE_ROLE,
                trajectoryNode.GetID(),
            )
        finally:
            planeNode.EndModify(wasModifying)
        planeNode.CreateDefaultDisplayNodes()
        displayNode = planeNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(True)
            displayNode.SetVisibility2D(True)
            displayNode.SetVisibility3D(True)
            displayNode.SetHandlesInteractive(False)
            displayNode.SetTranslationHandleVisibility(False)
            displayNode.SetRotationHandleVisibility(False)
            displayNode.SetScaleHandleVisibility(False)
            displayNode.SetPointLabelsVisibility(False)
            displayNode.SetPropertiesLabelVisibility(False)
            displayNode.SetOpacity(0.35)
            displayNode.SetColor(1.0, 0.78, 0.12)
        lineageColor = self.lineageColorFromNode(sourceModel)
        if lineageColor:
            self.setNodeLineageColor(
                planeNode,
                lineageColor,
                sourceModel.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE) or "",
                sourceModel.GetAttribute(self.LINEAGE_TARGET_FDI_ATTRIBUTE) or "",
            )
        return planeNode, {
            "originRas": tuple(float(value) for value in origin),
            "normalRas": planeNormal,
            "depthFromEntryMm": depth,
            "crownCapPercent": capPercent,
            "tiltMetrics": tiltMetrics,
            "directionGeometryJson": direction["directionGeometryJson"],
        }

    def validateTemplateSupportBoundaryPlane(
        self,
        sourceModel: vtkMRMLModelNode,
        planeNode: vtkMRMLMarkupsPlaneNode,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> vtkMRMLMarkupsPlaneNode:
        sourceSummary = self.getDraftTemplateSupportModelSummary(sourceModel)
        if sourceSummary["geometryState"] != "Current":
            raise ValueError(_("Update the stale full support-anatomy model first."))
        if not self.isTemplateSupportBoundaryPlaneNode(planeNode):
            raise ValueError(_("Create the insertion-aligned Step 5A support plane."))
        if planeNode.GetNodeReference(
            self.TEMPLATE_SUPPORT_PLANE_SOURCE_MODEL_REFERENCE_ROLE
        ) is not sourceModel:
            raise ValueError(_("The support plane belongs to another draft model."))
        if planeNode.GetNodeReference(
            self.TEMPLATE_SUPPORT_PLANE_SOURCE_TRAJECTORY_REFERENCE_ROLE
        ) is not trajectoryNode:
            raise ValueError(_("Reset the support plane for the selected trajectory."))
        origin = np.asarray(planeNode.GetOriginWorld(), dtype=float)
        normal = np.asarray(planeNode.GetNormalWorld(), dtype=float)
        if (
            origin.shape != (3,)
            or normal.shape != (3,)
            or not np.all(np.isfinite(origin))
            or not np.all(np.isfinite(normal))
            or float(np.linalg.norm(normal)) <= 1e-9
        ):
            raise ValueError(_("The Step 5A support plane geometry is invalid."))
        return planeNode

    def createOrUpdateTemplateSupportBoundaryFromPlane(
        self,
        sourceModel: vtkMRMLModelNode,
        planeNode: vtkMRMLMarkupsPlaneNode,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        *,
        samplingSpacingMm: float = 0.5,
        curveNode: vtkMRMLMarkupsClosedCurveNode | None = None,
    ) -> tuple[vtkMRMLMarkupsClosedCurveNode, dict]:
        """Initialize the authoritative editable curve from the support plane."""

        self.validateTemplateSupportBoundaryPlane(
            sourceModel,
            planeNode,
            trajectoryNode,
        )
        sourceSummary = self.getDraftTemplateSupportModelSummary(sourceModel)
        segmentIds = [
            sourceSummary["targetSegmentId"],
            *sourceSummary["supportSegmentIds"],
        ]
        surfaces = [
            {
                "segmentId": segmentId,
                "polyData": self._getClosedSurfaceCopy(
                    sourceSummary["sourceSegmentation"],
                    segmentId,
                ),
            }
            for segmentId in segmentIds
        ]
        loopPoints, metrics = insertion_aligned_support_boundary_loop(
            surfaces,
            planeNode.GetOriginWorld(),
            planeNode.GetNormalWorld(),
            sampling_spacing_mm=samplingSpacingMm,
        )
        curveNode = self.createOrResetTemplateSupportBoundary(
            sourceModel,
            curveNode,
        )
        wasModifying = curveNode.StartModify()
        try:
            for pointIndex, point in enumerate(loopPoints):
                curveNode.AddControlPointWorld(vtk.vtkVector3d(*point))
                curveNode.SetNthControlPointLabel(pointIndex, f"P{pointIndex + 1}")
            curveNode.SetAttribute(
                "DENTOBOT.BoundaryMappingMethod",
                "InsertionAlignedPlaneConvexHullThenPerToothDijkstra",
            )
            curveNode.SetAttribute(
                "DENTOBOT.PlaneInitializerMetricsJson",
                json.dumps(metrics, sort_keys=True, separators=(",", ":")),
            )
            curveNode.SetAttribute(
                "DENTOBOT.GeneratedFromPlaneGeometryJson",
                self.templateSupportBoundaryGeometryJson(curveNode),
            )
            curveNode.SetNodeReferenceID(
                self.TEMPLATE_SUPPORT_BOUNDARY_INITIALIZER_PLANE_REFERENCE_ROLE,
                planeNode.GetID(),
            )
        finally:
            curveNode.EndModify(wasModifying)
        return curveNode, metrics

    @staticmethod
    def templateSupportBoundaryControlPointsWorld(
        curveNode: vtkMRMLMarkupsClosedCurveNode,
    ) -> list[list[float]]:
        if not DENTOWorkflowLogic.isTemplateSupportBoundaryNode(curveNode):
            raise ValueError(_("Select a DENTOBOT visible-support boundary."))
        pointCount = curveNode.GetNumberOfDefinedControlPoints()
        if pointCount < 3:
            raise ValueError(
                _("Place at least three points to define the visible support boundary.")
            )
        points = []
        for pointIndex in range(pointCount):
            point = [0.0, 0.0, 0.0]
            curveNode.GetNthControlPointPositionWorld(pointIndex, point)
            if any(not math.isfinite(float(value)) for value in point):
                raise ValueError(_("The visible support boundary contains invalid points."))
            points.append([float(value) for value in point])
        return points

    @staticmethod
    def templateSupportBoundaryGeometryJson(
        curveNode: vtkMRMLMarkupsClosedCurveNode,
    ) -> str:
        points = DENTOWorkflowLogic.templateSupportBoundaryControlPointsWorld(
            curveNode
        )
        return json.dumps(points, separators=(",", ":"))

    @staticmethod
    def templateSupportBoundaryMatchesGeometryJson(
        curveNode: vtkMRMLMarkupsClosedCurveNode,
        storedGeometryJson: str,
        toleranceMm: float = 1e-4,
    ) -> bool:
        """Compare persisted Markups coordinates with serialization tolerance."""

        try:
            current = np.asarray(
                DENTOWorkflowLogic.templateSupportBoundaryControlPointsWorld(
                    curveNode
                ),
                dtype=float,
            )
            stored = np.asarray(json.loads(storedGeometryJson), dtype=float)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        return bool(
            current.shape == stored.shape
            and current.ndim == 2
            and current.shape[1:] == (3,)
            and np.all(np.isfinite(stored))
            and np.allclose(
                current,
                stored,
                rtol=0.0,
                atol=float(toleranceMm),
            )
        )

    def validateTemplateSupportBoundary(
        self,
        sourceModel: vtkMRMLModelNode,
        curveNode: vtkMRMLMarkupsClosedCurveNode,
    ) -> vtkMRMLMarkupsClosedCurveNode:
        sourceSummary = self.getDraftTemplateSupportModelSummary(sourceModel)
        if sourceSummary["geometryState"] != "Current":
            raise ValueError(_("Update the stale full support-anatomy model first."))
        if not self.isTemplateSupportBoundaryNode(curveNode):
            raise ValueError(_("Create the DENTOBOT visible-support boundary first."))
        if curveNode.GetNodeReference(
            self.TEMPLATE_SUPPORT_BOUNDARY_SOURCE_MODEL_REFERENCE_ROLE
        ) is not sourceModel:
            raise ValueError(
                _("The visible-support boundary does not reference the current support model.")
            )
        if curveNode.GetNumberOfDefinedControlPoints() < 3:
            raise ValueError(
                _("Place at least three boundary points around the erupted support surfaces.")
            )
        self.templateSupportBoundaryGeometryJson(curveNode)
        return curveNode

    def resolveTemplateSupportTrajectoryDirection(
        self,
        sourceModel: vtkMRMLModelNode,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        *,
        reverseDirection: bool = False,
    ) -> dict:
        """Resolve Entry→Target as insertion and its opposite as crown side."""

        sourceSummary = self.getDraftTemplateSupportModelSummary(sourceModel)
        if sourceSummary["geometryState"] != "Current":
            raise ValueError(_("Update the stale full support-anatomy model first."))
        if not self.isDentobotTrajectoryNode(trajectoryNode):
            raise ValueError(
                _(
                    "Select a complete Step 4A trajectory for the target tooth. "
                    "It supplies the template crown-to-root direction."
                )
            )
        association = self.getTrajectoryTargetAssociation(trajectoryNode)
        if not association:
            raise ValueError(_("The selected trajectory has no target-tooth association."))
        if association["segmentationNode"] is not sourceSummary["sourceSegmentation"]:
            raise ValueError(_("The selected trajectory belongs to another segmentation."))
        if (
            association["targetRecord"]["segmentId"]
            != sourceSummary["targetSegmentId"]
        ):
            raise ValueError(
                _("Select a Step 4A trajectory associated with the Step 5A target tooth.")
            )
        trajectorySummary = self.getTrajectorySummary(trajectoryNode)
        if not trajectorySummary["isValid"]:
            raise ValueError(
                _("Complete distinct Entry and Target points before generating the preview.")
            )
        entry = np.asarray(trajectorySummary["entryRas"], dtype=float)
        target = np.asarray(trajectorySummary["targetRas"], dtype=float)
        insertion = target - entry
        insertion /= float(np.linalg.norm(insertion))
        reversedValue = bool(reverseDirection)
        if reversedValue:
            insertion = -insertion
        crownDirection = -insertion
        trajectoryGeometry = {
            "entryRas": [float(value) for value in entry],
            "targetRas": [float(value) for value in target],
        }
        directionGeometry = {
            **trajectoryGeometry,
            "reverseDirection": reversedValue,
        }
        return {
            "trajectory": trajectoryNode,
            "trajectoryName": trajectoryNode.GetName() or _("Unnamed trajectory"),
            "targetSegmentId": sourceSummary["targetSegmentId"],
            "targetFdiNumber": (
                trajectoryNode.GetAttribute("DENTOBOT.TargetFdiNumber") or ""
            ),
            "entryRas": trajectoryGeometry["entryRas"],
            "targetRas": trajectoryGeometry["targetRas"],
            "reverseDirection": reversedValue,
            "insertionDirectionRas": tuple(
                float(value) for value in insertion
            ),
            "crownDirectionRas": tuple(
                float(value) for value in crownDirection
            ),
            "trajectoryGeometryJson": json.dumps(
                trajectoryGeometry,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "directionGeometryJson": json.dumps(
                directionGeometry,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }

    def createOrUpdateVisibleTemplateSupportModel(
        self,
        sourceModel: vtkMRMLModelNode,
        curveNode: vtkMRMLMarkupsClosedCurveNode,
        *,
        directionTrajectory: vtkMRMLMarkupsLineNode,
        reverseDirection: bool = False,
        samplingSpacingMm: float = 0.5,
        terminalCoveragePercent: float = 50.0,
        outputModel: vtkMRMLModelNode | None = None,
        insertionDirectionNode: vtkMRMLMarkupsLineNode | None = None,
    ) -> tuple[vtkMRMLModelNode, dict]:
        """Extract and persist only the clinician-selected visible support patch."""

        sourceSummary = self.getDraftTemplateSupportModelSummary(sourceModel)
        self.validateTemplateSupportBoundary(sourceModel, curveNode)
        directionSummary = self.resolveTemplateSupportTrajectoryDirection(
            sourceModel,
            directionTrajectory,
            reverseDirection=reverseDirection,
        )
        spacing = float(samplingSpacingMm)
        if not math.isfinite(spacing) or spacing < 0.1 or spacing > 2.0:
            raise ValueError(_("Boundary sampling must be between 0.10 and 2.00 mm."))
        terminalCoverage = float(terminalCoveragePercent) / 100.0
        if (
            not math.isfinite(terminalCoverage)
            or not 0.25 <= terminalCoverage <= 1.0
        ):
            raise ValueError(_("Terminal support coverage must be 25–100%."))

        sourceSegmentation = sourceSummary["sourceSegmentation"]
        segmentIds = [
            sourceSummary["targetSegmentId"],
            *sourceSummary["supportSegmentIds"],
        ]
        sourceNames = json.loads(
            sourceModel.GetAttribute("DENTOBOT.SourceSegmentNamesJson") or "{}"
        )
        toothSurfaces = [
            {
                "segmentId": segmentId,
                "displayName": sourceNames.get(segmentId) or segmentId,
                "isTarget": segmentId == sourceSummary["targetSegmentId"],
                "polyData": self._getClosedSurfaceCopy(
                    sourceSegmentation,
                    segmentId,
                ),
            }
            for segmentId in segmentIds
        ]
        patch, metrics = extract_directional_visible_support_surface(
            toothSurfaces,
            self.templateSupportBoundaryControlPointsWorld(curveNode),
            directionSummary["crownDirectionRas"],
            sampling_spacing_mm=spacing,
            terminal_coverage_fraction=terminalCoverage,
        )
        reusedOutputModel = bool(outputModel)
        if outputModel:
            if not self.isVisibleTemplateSupportModelNode(outputModel):
                raise ValueError(_("The selected visible-support preview has the wrong role."))
        else:
            outputModel = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
                "[Step 5A] DENTO Visible Tooth Support Surface",
            )
        if not outputModel:
            raise RuntimeError(_("Slicer could not create the visible-support preview."))

        boundaryGeometryJson = self.templateSupportBoundaryGeometryJson(curveNode)
        timestamp = datetime.now(timezone.utc).isoformat()
        previousVisibility = bool(
            outputModel.GetDisplayNode()
            and outputModel.GetDisplayNode().GetVisibility()
        )
        wasModifying = outputModel.StartModify()
        try:
            outputModel.SetName("[Step 5A] DENTO Visible Tooth Support Surface")
            outputModel.SetAndObservePolyData(patch)
            outputModel.SetAndObserveTransformNodeID(None)
            outputModel.SetAttribute(
                "DENTOBOT.ModelRole",
                "VisibleTemplateSupportSurface",
            )
            outputModel.SetAttribute(
                "DENTOBOT.TemplateSupportSurfaceSchemaVersion",
                self.TEMPLATE_SUPPORT_SURFACE_SCHEMA_VERSION,
            )
            outputModel.SetAttribute("DENTOBOT.Status", "ResearchOnly")
            outputModel.SetAttribute("DENTOBOT.GeometryState", "Current")
            outputModel.SetAttribute("DENTOBOT.StaleReason", None)
            outputModel.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
            outputModel.SetAttribute(
                "DENTOBOT.SelectionMode",
                "TrajectoryDirection",
            )
            outputModel.SetAttribute(
                "DENTOBOT.DirectionReversed",
                "true" if directionSummary["reverseDirection"] else "false",
            )
            outputModel.SetAttribute(
                "DENTOBOT.DirectionGeometryJson",
                directionSummary["directionGeometryJson"],
            )
            outputModel.SetAttribute(
                "DENTOBOT.CrownDirectionRasJson",
                json.dumps(
                    directionSummary["crownDirectionRas"],
                    separators=(",", ":"),
                ),
            )
            outputModel.SetAttribute("DENTOBOT.SamplingSpacingMm", f"{spacing:.9g}")
            outputModel.SetAttribute(
                "DENTOBOT.TerminalSupportCoverageFraction",
                f"{terminalCoverage:.9g}",
            )
            outputModel.SetAttribute(
                "DENTOBOT.TerminalClipPlanesJson",
                json.dumps(
                    metrics.get("terminalClipPlanesRas", []),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            outputModel.SetAttribute(
                "DENTOBOT.SupportBoundaryGeometryJson",
                boundaryGeometryJson,
            )
            outputModel.SetAttribute(
                "DENTOBOT.SourceModelUpdatedUtc",
                sourceModel.GetAttribute("DENTOBOT.UpdatedUtc") or "",
            )
            outputModel.SetAttribute(
                "DENTOBOT.GeometryMetricsJson",
                json.dumps(metrics, sort_keys=True, separators=(",", ":")),
            )
            outputModel.SetAttribute("DENTOBOT.UpdatedUtc", timestamp)
            outputModel.SetNodeReferenceID(
                self.TEMPLATE_VISIBLE_SUPPORT_SOURCE_MODEL_REFERENCE_ROLE,
                sourceModel.GetID(),
            )
            outputModel.SetNodeReferenceID(
                self.TEMPLATE_VISIBLE_SUPPORT_BOUNDARY_REFERENCE_ROLE,
                curveNode.GetID(),
            )
            outputModel.SetNodeReferenceID(
                self.TEMPLATE_VISIBLE_SUPPORT_DIRECTION_TRAJECTORY_REFERENCE_ROLE,
                directionTrajectory.GetID(),
            )
            outputModel.SetNodeReferenceID(
                self.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE,
                sourceSegmentation.GetID(),
            )
        finally:
            outputModel.EndModify(wasModifying)

        outputModel.CreateDefaultDisplayNodes()
        displayNode = outputModel.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(
                previousVisibility if reusedOutputModel else True
            )
            displayNode.SetVisibility2D(False)
            displayNode.SetVisibility3D(True)
            displayNode.SetOpacity(0.92)
            displayNode.SetColor(1.0, 0.62, 0.10)
            displayNode.SetBackfaceCulling(False)
        sourceDisplay = sourceModel.GetDisplayNode()
        if sourceDisplay:
            sourceDisplay.SetOpacity(0.18)
        insertionDirection = self.createOrUpdateTemplateInsertionDirectionFromTrajectory(
            outputModel,
            directionTrajectory,
            reverseDirection=directionSummary["reverseDirection"],
            lineNode=(
                outputModel.GetNodeReference(
                    self.TEMPLATE_VISIBLE_SUPPORT_INSERTION_DIRECTION_REFERENCE_ROLE
                )
                or insertionDirectionNode
            ),
        )
        outputModel.SetNodeReferenceID(
            self.TEMPLATE_VISIBLE_SUPPORT_INSERTION_DIRECTION_REFERENCE_ROLE,
            insertionDirection.GetID(),
        )
        return outputModel, metrics

    def getVisibleTemplateSupportModelSummary(
        self,
        modelNode: vtkMRMLModelNode,
    ) -> dict:
        if not self.isVisibleTemplateSupportModelNode(modelNode):
            raise ValueError(_("Select the DENTOBOT visible-support preview."))
        polyData = modelNode.GetPolyData()
        if not polyData or not polyData.GetNumberOfPoints() or not polyData.GetNumberOfCells():
            raise ValueError(_("The visible-support preview contains no geometry."))
        sourceModel = modelNode.GetNodeReference(
            self.TEMPLATE_VISIBLE_SUPPORT_SOURCE_MODEL_REFERENCE_ROLE
        )
        boundary = modelNode.GetNodeReference(
            self.TEMPLATE_VISIBLE_SUPPORT_BOUNDARY_REFERENCE_ROLE
        )
        sourceSegmentation = modelNode.GetNodeReference(
            self.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE
        )
        directionTrajectory = modelNode.GetNodeReference(
            self.TEMPLATE_VISIBLE_SUPPORT_DIRECTION_TRAJECTORY_REFERENCE_ROLE
        )
        insertionDirection = modelNode.GetNodeReference(
            self.TEMPLATE_VISIBLE_SUPPORT_INSERTION_DIRECTION_REFERENCE_ROLE
        )
        if not self.isDraftTemplateSupportModelNode(sourceModel):
            raise ValueError(_("The visible-support preview has no valid source model."))
        if not self.isTemplateSupportBoundaryNode(boundary):
            raise ValueError(_("The visible-support preview has no valid boundary."))
        if not sourceSegmentation or not sourceSegmentation.IsA("vtkMRMLSegmentationNode"):
            raise ValueError(_("The visible-support preview lost its authoritative segmentation."))
        metrics = json.loads(
            modelNode.GetAttribute("DENTOBOT.GeometryMetricsJson") or "{}"
        )
        terminalClipPlanes = json.loads(
            modelNode.GetAttribute("DENTOBOT.TerminalClipPlanesJson") or "[]"
        )
        if not isinstance(terminalClipPlanes, list):
            raise ValueError(_("The visible-support terminal clipping metadata is invalid."))
        return {
            "geometryState": modelNode.GetAttribute("DENTOBOT.GeometryState") or "Unknown",
            "staleReason": modelNode.GetAttribute("DENTOBOT.StaleReason") or "",
            "sourceModel": sourceModel,
            "boundary": boundary,
            "sourceSegmentation": sourceSegmentation,
            "directionTrajectory": directionTrajectory,
            "insertionDirection": insertionDirection,
            "selectionMode": modelNode.GetAttribute("DENTOBOT.SelectionMode") or "",
            "directionReversed": (
                modelNode.GetAttribute("DENTOBOT.DirectionReversed") == "true"
            ),
            "directionGeometryJson": modelNode.GetAttribute(
                "DENTOBOT.DirectionGeometryJson"
            ) or "",
            "samplingSpacingMm": float(
                modelNode.GetAttribute("DENTOBOT.SamplingSpacingMm") or "nan"
            ),
            "terminalSupportCoveragePercent": 100.0 * float(
                modelNode.GetAttribute(
                    "DENTOBOT.TerminalSupportCoverageFraction"
                )
                or "nan"
            ),
            "terminalClipPlanesRas": terminalClipPlanes,
            "boundaryGeometryJson": modelNode.GetAttribute(
                "DENTOBOT.SupportBoundaryGeometryJson"
            ) or "",
            "sourceModelUpdatedUtc": modelNode.GetAttribute(
                "DENTOBOT.SourceModelUpdatedUtc"
            ) or "",
            "pointCount": int(polyData.GetNumberOfPoints()),
            "cellCount": int(polyData.GetNumberOfCells()),
            "metrics": metrics,
        }

    @staticmethod
    def markVisibleTemplateSupportModelStale(
        modelNode: vtkMRMLModelNode | None,
        reason: str,
    ) -> bool:
        if not DENTOWorkflowLogic.isVisibleTemplateSupportModelNode(modelNode):
            return False
        modelNode.SetAttribute("DENTOBOT.GeometryState", "Stale")
        modelNode.SetAttribute(
            "DENTOBOT.StaleReason",
            str(reason).strip() or "Visible support selection changed.",
        )
        return True

    def deleteTemplateSupportSelection(
        self,
        curveNode: vtkMRMLMarkupsClosedCurveNode | None,
        modelNode: vtkMRMLModelNode | None,
        planeNode: vtkMRMLMarkupsPlaneNode | None = None,
    ) -> list[dict]:
        nodes = [node for node in (modelNode, curveNode, planeNode) if node]
        if not nodes:
            raise ValueError(_("There is no DENTOBOT visible support selection to delete."))
        if curveNode and not self.isTemplateSupportBoundaryNode(curveNode):
            raise ValueError(_("The selected curve is not owned by DENTOBOT Step 5A."))
        if modelNode and not self.isVisibleTemplateSupportModelNode(modelNode):
            raise ValueError(_("The selected preview is not owned by DENTOBOT Step 5A."))
        if planeNode and not self.isTemplateSupportBoundaryPlaneNode(planeNode):
            raise ValueError(_("The selected support plane is not owned by DENTOBOT Step 5A."))
        parameterNode = self.getParameterNode()
        parameterNode.visibleTemplateSupportModel = None
        parameterNode.templateSupportBoundaryCurve = None
        parameterNode.templateSupportBoundaryPlane = None
        removals = []
        for node in nodes:
            if slicer.mrmlScene.IsNodePresent(node):
                removals.append(self._removeSceneNodeAndOwnedAuxiliaries(node))
        return removals
