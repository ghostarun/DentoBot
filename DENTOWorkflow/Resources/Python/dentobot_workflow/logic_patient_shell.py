"""Extracted insertion undercut and patient shell methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


class PatientShellLogicMixin:
    @staticmethod
    def isTemplateInsertionDirectionNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsLineNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole")
            == "TemplateInsertionDirection"
        )

    @staticmethod
    def isTemplateUndercutSurfaceModelNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLModelNode")
            and node.GetAttribute("DENTOBOT.ModelRole")
            == "TemplateUndercutSurface"
        )

    @staticmethod
    def isTemplateUndercutBlockoutModelNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLModelNode")
            and node.GetAttribute("DENTOBOT.ModelRole")
            == "TemplateUndercutBlockout"
        )

    def createOrUpdateTemplateInsertionDirectionFromTrajectory(
        self,
        visibleSupportModel: vtkMRMLModelNode,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        *,
        reverseDirection: bool = False,
        lineNode: vtkMRMLMarkupsLineNode | None = None,
    ) -> vtkMRMLMarkupsLineNode:
        """Create a locked Approach→Seat line derived from Entry→Target."""

        visibleSummary = self.getVisibleTemplateSupportModelSummary(
            visibleSupportModel
        )
        sourceModel = visibleSummary["sourceModel"]
        directionSummary = self.resolveTemplateSupportTrajectoryDirection(
            sourceModel,
            trajectoryNode,
            reverseDirection=reverseDirection,
        )
        if lineNode and not self.isTemplateInsertionDirectionNode(lineNode):
            raise ValueError(_("The derived insertion-direction node has the wrong role."))
        if not lineNode:
            lineNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsLineNode",
                "[Step 5B] DENTO Insertion Direction from Trajectory",
            )
        if not lineNode:
            raise RuntimeError(_("Slicer could not create the insertion direction."))

        approach = (
            directionSummary["targetRas"]
            if directionSummary["reverseDirection"]
            else directionSummary["entryRas"]
        )
        seat = (
            directionSummary["entryRas"]
            if directionSummary["reverseDirection"]
            else directionSummary["targetRas"]
        )
        targetLabel = directionSummary["targetFdiNumber"] or _("target")
        wasModifying = lineNode.StartModify()
        try:
            lineNode.SetName(
                _("[Step 5B] DENTO Insertion from FDI %1 Trajectory").replace(
                    "%1",
                    targetLabel,
                )
            )
            lineNode.RemoveAllControlPoints()
            lineNode.SetAttribute(
                "DENTOBOT.MarkupsRole",
                "TemplateInsertionDirection",
            )
            lineNode.SetAttribute("DENTOBOT.Status", "ResearchOnly")
            lineNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
            lineNode.SetAttribute(
                "DENTOBOT.DirectionSemantics",
                "ApproachToSeat;RemovalIsOpposite;DerivedFromTrajectory",
            )
            lineNode.SetAttribute(
                "DENTOBOT.DirectionReversed",
                "true" if directionSummary["reverseDirection"] else "false",
            )
            lineNode.SetAttribute(
                "DENTOBOT.SourceTrajectoryGeometryJson",
                directionSummary["trajectoryGeometryJson"],
            )
            lineNode.SetNodeReferenceID(
                self.TEMPLATE_INSERTION_DIRECTION_SOURCE_SURFACE_REFERENCE_ROLE,
                visibleSupportModel.GetID(),
            )
            lineNode.SetNodeReferenceID(
                self.TEMPLATE_INSERTION_DIRECTION_SOURCE_TRAJECTORY_REFERENCE_ROLE,
                trajectoryNode.GetID(),
            )
            lineNode.AddControlPointWorld(vtk.vtkVector3d(*approach))
            lineNode.AddControlPointWorld(vtk.vtkVector3d(*seat))
            lineNode.SetNthControlPointLabel(0, "Approach")
            lineNode.SetNthControlPointLabel(1, "Seat")
            lineNode.SetLocked(True)
            lineNode.SetSelectable(False)
        finally:
            lineNode.EndModify(wasModifying)
        lineNode.CreateDefaultDisplayNodes()
        displayNode = lineNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(False)
            displayNode.SetVisibility2D(False)
            displayNode.SetVisibility3D(False)
            displayNode.SetPointLabelsVisibility(False)
            displayNode.SetColor(0.20, 0.85, 0.38)
            displayNode.SetSelectedColor(0.35, 1.0, 0.50)
        return lineNode

    def createOrResetTemplateInsertionDirection(
        self,
        visibleSupportModel: vtkMRMLModelNode,
        lineNode: vtkMRMLMarkupsLineNode | None = None,
    ) -> vtkMRMLMarkupsLineNode:
        visibleSummary = self.getVisibleTemplateSupportModelSummary(
            visibleSupportModel
        )
        if visibleSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale visible support surface first."))
        if lineNode:
            if not self.isTemplateInsertionDirectionNode(lineNode):
                raise ValueError(_("Select the DENTOBOT template insertion direction."))
            associatedSurface = lineNode.GetNodeReference(
                self.TEMPLATE_INSERTION_DIRECTION_SOURCE_SURFACE_REFERENCE_ROLE
            )
            if associatedSurface is not visibleSupportModel:
                raise ValueError(
                    _("The selected insertion direction belongs to another support surface.")
                )
        else:
            lineNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsLineNode",
                "[Step 5B] DENTO Template Insertion: Approach to Seat",
            )
        if not lineNode:
            raise RuntimeError(_("Slicer could not create the insertion direction."))

        wasModifying = lineNode.StartModify()
        try:
            lineNode.SetName("[Step 5B] DENTO Template Insertion: Approach to Seat")
            lineNode.RemoveAllControlPoints()
            lineNode.SetAttribute(
                "DENTOBOT.MarkupsRole",
                "TemplateInsertionDirection",
            )
            lineNode.SetAttribute("DENTOBOT.Status", "ResearchOnly")
            lineNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
            lineNode.SetAttribute(
                "DENTOBOT.DirectionSemantics",
                "ApproachToSeat;RemovalIsOpposite",
            )
            lineNode.SetNodeReferenceID(
                self.TEMPLATE_INSERTION_DIRECTION_SOURCE_SURFACE_REFERENCE_ROLE,
                visibleSupportModel.GetID(),
            )
            if lineNode.GetMaximumNumberOfControlPoints() != 2:
                raise RuntimeError(
                    _("Slicer's Markups line does not enforce two control points.")
                )
            lineNode.SetLocked(False)
            lineNode.SetSelectable(True)
        finally:
            lineNode.EndModify(wasModifying)
        lineNode.CreateDefaultDisplayNodes()
        displayNode = lineNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(True)
            displayNode.SetVisibility2D(True)
            displayNode.SetVisibility3D(True)
            displayNode.SetPointLabelsVisibility(True)
            displayNode.SetGlyphScale(1.35)
            displayNode.SetLineThickness(0.45)
            displayNode.SetColor(0.20, 0.85, 0.38)
            displayNode.SetSelectedColor(0.35, 1.0, 0.50)
        return lineNode

    def getTemplateInsertionDirectionSummary(
        self,
        lineNode: vtkMRMLMarkupsLineNode,
    ) -> dict:
        if not self.isTemplateInsertionDirectionNode(lineNode):
            raise ValueError(_("Create the DENTOBOT template insertion direction first."))
        pointCount = lineNode.GetNumberOfDefinedControlPoints()
        if pointCount != 2:
            raise ValueError(
                _("Place exactly two insertion points: Approach first, then Seat.")
            )
        points = []
        for index in range(2):
            point = [0.0, 0.0, 0.0]
            lineNode.GetNthControlPointPositionWorld(index, point)
            if any(not math.isfinite(float(value)) for value in point):
                raise ValueError(_("The insertion direction contains invalid coordinates."))
            points.append([float(value) for value in point])
            lineNode.SetNthControlPointLabel(index, "Approach" if index == 0 else "Seat")
        direction = np.asarray(points[1], dtype=float) - np.asarray(points[0], dtype=float)
        length = float(np.linalg.norm(direction))
        if length <= 1e-6:
            raise ValueError(_("Approach and Seat must be different world-RAS points."))
        insertion = direction / length
        removal = -insertion
        geometry = {
            "approachRas": points[0],
            "seatRas": points[1],
        }
        return {
            **geometry,
            "lengthMm": length,
            "insertionDirectionRas": tuple(float(value) for value in insertion),
            "removalDirectionRas": tuple(float(value) for value in removal),
            "geometryJson": json.dumps(
                geometry,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "sourceSurface": lineNode.GetNodeReference(
                self.TEMPLATE_INSERTION_DIRECTION_SOURCE_SURFACE_REFERENCE_ROLE
            ),
            "sourceTrajectory": lineNode.GetNodeReference(
                self.TEMPLATE_INSERTION_DIRECTION_SOURCE_TRAJECTORY_REFERENCE_ROLE
            ),
            "directionReversed": (
                lineNode.GetAttribute("DENTOBOT.DirectionReversed") == "true"
            ),
        }

    def templateCollisionAnatomyWorld(
        self,
        sourceModel: vtkMRMLModelNode,
    ) -> tuple[vtk.vtkPolyData, dict]:
        """Collect substantive same-arch teeth as collision-only anatomy."""

        sourceSummary = self.getDraftTemplateSupportModelSummary(sourceModel)
        segmentationNode = sourceSummary["sourceSegmentation"]
        targetRecord = self.validateTargetTooth(
            segmentationNode,
            sourceSummary["targetSegmentId"],
        )
        targetFdi = targetRecord.get("fdiNumber") or ""
        if len(targetFdi) != 2 or targetFdi[0] not in "1234":
            raise ValueError(
                _("The target tooth has no valid FDI arch for collision blockout.")
            )
        archQuadrants = "12" if targetFdi[0] in "12" else "34"
        collisionRecords = [
            record
            for record in self.getTargetToothRecords(segmentationNode)
            if len(record.get("fdiNumber") or "") == 2
            and (record.get("fdiNumber") or "")[0] in archQuadrants
        ]
        if not collisionRecords:
            raise ValueError(_("No same-arch tooth anatomy is available for blockout."))

        append = vtk.vtkAppendPolyData()
        perToothMetrics = []
        for record in collisionRecords:
            surface = self._getClosedSurfaceCopy(
                segmentationNode,
                record["segmentId"],
            )
            substantiveSurface, surfaceMetrics = largest_connected_surface_region(
                surface
            )
            append.AddInputData(substantiveSurface)
            perToothMetrics.append(
                {
                    "segmentId": record["segmentId"],
                    "fdiNumber": record.get("fdiNumber") or "",
                    **surfaceMetrics,
                }
            )
        append.Update()
        collisionWorld = vtk.vtkPolyData()
        collisionWorld.DeepCopy(append.GetOutput())
        topology = surface_topology(collisionWorld)
        return collisionWorld, {
            **topology,
            "method": "AuthoritativeSameArchLargestToothSurfaces",
            "targetFdiNumber": targetFdi,
            "archQuadrants": archQuadrants,
            "collisionSegmentIds": [
                record["segmentId"] for record in collisionRecords
            ],
            "collisionToothCount": len(collisionRecords),
            "ignoredSourceIslandCount": int(
                sum(
                    item["ignoredSurfaceRegionCount"]
                    for item in perToothMetrics
                )
            ),
            "toothMetrics": perToothMetrics,
        }

    def createOrUpdateTemplateUndercutAnalysis(
        self,
        sourceModel: vtkMRMLModelNode,
        visibleSupportModel: vtkMRMLModelNode,
        insertionDirection: vtkMRMLMarkupsLineNode,
        *,
        angleToleranceDeg: float,
        interproximalReliefMm: float,
        samplingSpacingMm: float,
        undercutModel: vtkMRMLModelNode | None = None,
        blockoutModel: vtkMRMLModelNode | None = None,
    ) -> tuple[vtkMRMLModelNode, vtkMRMLModelNode, dict]:
        sourceSummary = self.getDraftTemplateSupportModelSummary(sourceModel)
        visibleSummary = self.getVisibleTemplateSupportModelSummary(
            visibleSupportModel
        )
        directionSummary = self.getTemplateInsertionDirectionSummary(
            insertionDirection
        )
        if sourceSummary["geometryState"] != "Current":
            raise ValueError(_("Update the stale full support-anatomy model first."))
        if visibleSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale visible support surface first."))
        if visibleSummary["sourceModel"] is not sourceModel:
            raise ValueError(_("The visible support surface belongs to another source model."))
        if directionSummary["sourceSurface"] is not visibleSupportModel:
            raise ValueError(_("The insertion direction belongs to another support surface."))
        if sourceModel.GetAttribute("DENTOBOT.CoordinateConvention") != "WorldRASmm":
            raise ValueError(
                _(
                    "This legacy draft support model has an obsolete transform "
                    "contract. Update it before undercut processing."
                )
            )
        tolerance = float(angleToleranceDeg)
        interproximalRelief = float(interproximalReliefMm)
        spacing = float(samplingSpacingMm)
        if not math.isfinite(tolerance) or not 0.0 <= tolerance <= 45.0:
            raise ValueError(_("Undercut angle tolerance must be 0–45 degrees."))
        if not math.isfinite(spacing) or not 0.1 <= spacing <= 2.0:
            raise ValueError(_("Undercut processing resolution must be 0.10–2.00 mm."))
        if (
            not math.isfinite(interproximalRelief)
            or not 0.0 <= interproximalRelief <= 5.0
        ):
            raise ValueError(_("Interproximal relief must be 0.00–5.00 mm."))

        supportWorld = model_polydata_in_world(visibleSupportModel)
        collisionWorld, collisionMetrics = self.templateCollisionAnatomyWorld(
            sourceModel
        )
        undercutPolyData, undercutMetrics = analyze_surface_undercuts(
            supportWorld,
            directionSummary["insertionDirectionRas"],
            angle_tolerance_deg=tolerance,
        )
        padding = max(5.0, 4.0 * spacing)
        blockoutPolyData, blockoutMetrics = create_directional_blockout(
            collisionWorld,
            supportWorld,
            directionSummary["insertionDirectionRas"],
            sampling_spacing_mm=spacing,
            padding_mm=padding,
            interproximal_relief_mm=interproximalRelief,
        )
        blockoutMetrics["collisionAnatomy"] = collisionMetrics
        undercutModel = self._createOrReuseRoleModel(
            undercutModel,
            "TemplateUndercutSurface",
            "[Step 5B] DENTO Retentive Undercut Preview",
        )
        blockoutModel = self._createOrReuseRoleModel(
            blockoutModel,
            "TemplateUndercutBlockout",
            "[Step 5B] DENTO Directional Undercut Blockout",
        )
        timestamp = datetime.now(timezone.utc).isoformat()
        parameters = {
            "angleToleranceDeg": tolerance,
            "interproximalReliefMm": interproximalRelief,
            "processingResolutionMm": spacing,
            "paddingMm": padding,
        }
        parametersJson = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        for modelNode, role, polyData, metrics in (
            (
                undercutModel,
                "TemplateUndercutSurface",
                undercutPolyData,
                undercutMetrics,
            ),
            (
                blockoutModel,
                "TemplateUndercutBlockout",
                blockoutPolyData,
                blockoutMetrics,
            ),
        ):
            wasModifying = modelNode.StartModify()
            try:
                modelNode.SetAndObservePolyData(polyData)
                modelNode.SetAndObserveTransformNodeID(None)
                modelNode.SetAttribute("DENTOBOT.ModelRole", role)
                modelNode.SetAttribute("DENTOBOT.Status", "ResearchOnly")
                modelNode.SetAttribute("DENTOBOT.GeometryState", "Current")
                modelNode.SetAttribute("DENTOBOT.StaleReason", None)
                modelNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
                modelNode.SetAttribute("DENTOBOT.ParametersJson", parametersJson)
                modelNode.SetAttribute(
                    "DENTOBOT.InsertionGeometryJson",
                    directionSummary["geometryJson"],
                )
                modelNode.SetAttribute(
                    "DENTOBOT.SourceModelUpdatedUtc",
                    sourceModel.GetAttribute("DENTOBOT.UpdatedUtc") or "",
                )
                modelNode.SetAttribute(
                    "DENTOBOT.VisibleSupportUpdatedUtc",
                    visibleSupportModel.GetAttribute("DENTOBOT.UpdatedUtc") or "",
                )
                modelNode.SetAttribute(
                    "DENTOBOT.GeometryMetricsJson",
                    json.dumps(metrics, sort_keys=True, separators=(",", ":")),
                )
                modelNode.SetAttribute(
                    "DENTOBOT.CollisionSegmentIDsJson",
                    json.dumps(
                        collisionMetrics["collisionSegmentIds"],
                        separators=(",", ":"),
                    ),
                )
                modelNode.SetAttribute("DENTOBOT.UpdatedUtc", timestamp)
                modelNode.SetNodeReferenceID(
                    self.TEMPLATE_UNDERCUT_SOURCE_ANATOMY_REFERENCE_ROLE,
                    sourceModel.GetID(),
                )
                modelNode.SetNodeReferenceID(
                    self.TEMPLATE_UNDERCUT_SOURCE_SURFACE_REFERENCE_ROLE,
                    visibleSupportModel.GetID(),
                )
                modelNode.SetNodeReferenceID(
                    self.TEMPLATE_UNDERCUT_INSERTION_DIRECTION_REFERENCE_ROLE,
                    insertionDirection.GetID(),
                )
                modelNode.SetNodeReferenceID(
                    self.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE,
                    sourceSummary["sourceSegmentation"].GetID(),
                )
            finally:
                modelNode.EndModify(wasModifying)
            modelNode.CreateDefaultDisplayNodes()
        undercutDisplay = undercutModel.GetDisplayNode()
        if undercutDisplay:
            undercutDisplay.SetVisibility(True)
            undercutDisplay.SetVisibility2D(False)
            undercutDisplay.SetVisibility3D(True)
            undercutDisplay.SetColor(0.95, 0.12, 0.10)
            undercutDisplay.SetOpacity(0.95)
            undercutDisplay.SetBackfaceCulling(False)
        blockoutDisplay = blockoutModel.GetDisplayNode()
        if blockoutDisplay:
            blockoutDisplay.SetVisibility(False)
            blockoutDisplay.SetVisibility2D(False)
            blockoutDisplay.SetVisibility3D(True)
            blockoutDisplay.SetColor(0.20, 0.82, 0.42)
            blockoutDisplay.SetOpacity(0.30)
            blockoutDisplay.SetBackfaceCulling(False)
        lineageColor = self.lineageColorFromNode(sourceModel)
        if lineageColor:
            for modelNode in (undercutModel, blockoutModel):
                self.setNodeLineageColor(
                    modelNode,
                    lineageColor,
                    sourceModel.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE) or "",
                    sourceModel.GetAttribute(self.LINEAGE_TARGET_FDI_ATTRIBUTE) or "",
                )
        return undercutModel, blockoutModel, {
            "parameters": parameters,
            "direction": directionSummary,
            "undercut": undercutMetrics,
            "blockout": blockoutMetrics,
        }

    def getTemplateUndercutOutputSummary(
        self,
        modelNode: vtkMRMLModelNode,
        expectedRole: str,
    ) -> dict:
        accepts = (
            self.isTemplateUndercutSurfaceModelNode
            if expectedRole == "TemplateUndercutSurface"
            else self.isTemplateUndercutBlockoutModelNode
            if expectedRole == "TemplateUndercutBlockout"
            else None
        )
        if not accepts or not accepts(modelNode):
            raise ValueError(_("Select the expected DENTOBOT undercut output."))
        polyData = modelNode.GetPolyData()
        if expectedRole == "TemplateUndercutBlockout" and (
            not polyData or not polyData.GetNumberOfCells()
        ):
            raise ValueError(_("The directional blockout contains no geometry."))
        sourceModel = modelNode.GetNodeReference(
            self.TEMPLATE_UNDERCUT_SOURCE_ANATOMY_REFERENCE_ROLE
        )
        visibleSupport = modelNode.GetNodeReference(
            self.TEMPLATE_UNDERCUT_SOURCE_SURFACE_REFERENCE_ROLE
        )
        insertionDirection = modelNode.GetNodeReference(
            self.TEMPLATE_UNDERCUT_INSERTION_DIRECTION_REFERENCE_ROLE
        )
        if not self.isDraftTemplateSupportModelNode(sourceModel):
            raise ValueError(_("The undercut output lost its source anatomy."))
        if not self.isVisibleTemplateSupportModelNode(visibleSupport):
            raise ValueError(_("The undercut output lost its visible support surface."))
        if not self.isTemplateInsertionDirectionNode(insertionDirection):
            raise ValueError(_("The undercut output lost its insertion direction."))
        return {
            "geometryState": modelNode.GetAttribute("DENTOBOT.GeometryState") or "Unknown",
            "staleReason": modelNode.GetAttribute("DENTOBOT.StaleReason") or "",
            "sourceModel": sourceModel,
            "visibleSupport": visibleSupport,
            "insertionDirection": insertionDirection,
            "parametersJson": modelNode.GetAttribute("DENTOBOT.ParametersJson") or "",
            "insertionGeometryJson": modelNode.GetAttribute(
                "DENTOBOT.InsertionGeometryJson"
            ) or "",
            "sourceModelUpdatedUtc": modelNode.GetAttribute(
                "DENTOBOT.SourceModelUpdatedUtc"
            ) or "",
            "visibleSupportUpdatedUtc": modelNode.GetAttribute(
                "DENTOBOT.VisibleSupportUpdatedUtc"
            ) or "",
            "metrics": json.loads(
                modelNode.GetAttribute("DENTOBOT.GeometryMetricsJson") or "{}"
            ),
            "pointCount": int(polyData.GetNumberOfPoints()) if polyData else 0,
            "cellCount": int(polyData.GetNumberOfCells()) if polyData else 0,
        }

    @staticmethod
    def markTemplateUndercutOutputsStale(
        undercutModel: vtkMRMLModelNode | None,
        blockoutModel: vtkMRMLModelNode | None,
        reason: str,
    ) -> bool:
        changed = False
        for modelNode, accepts in (
            (undercutModel, DENTOWorkflowLogic.isTemplateUndercutSurfaceModelNode),
            (blockoutModel, DENTOWorkflowLogic.isTemplateUndercutBlockoutModelNode),
        ):
            if accepts(modelNode):
                modelNode.SetAttribute("DENTOBOT.GeometryState", "Stale")
                modelNode.SetAttribute(
                    "DENTOBOT.StaleReason",
                    str(reason).strip() or "Insertion direction or support surface changed.",
                )
                changed = True
        return changed

    def deleteTemplateUndercutWorkflow(
        self,
        insertionDirection: vtkMRMLMarkupsLineNode | None,
        undercutModel: vtkMRMLModelNode | None,
        blockoutModel: vtkMRMLModelNode | None,
    ) -> list[dict]:
        """Delete only the owned insertion/undercut subtree, preserving anatomy."""

        if insertionDirection and not self.isTemplateInsertionDirectionNode(
            insertionDirection
        ):
            raise ValueError(_("The selected insertion line is not owned by DENTOBOT."))
        if undercutModel and not self.isTemplateUndercutSurfaceModelNode(undercutModel):
            raise ValueError(_("The selected undercut preview is not owned by DENTOBOT."))
        if blockoutModel and not self.isTemplateUndercutBlockoutModelNode(blockoutModel):
            raise ValueError(_("The selected blockout is not owned by DENTOBOT."))
        nodes = [
            node
            for node in (undercutModel, blockoutModel, insertionDirection)
            if node
        ]
        if not nodes:
            return []
        parameterNode = self.getParameterNode()
        parameterNode.templateUndercutSurfaceModel = None
        parameterNode.templateUndercutBlockoutModel = None
        parameterNode.templateInsertionDirection = None
        removals = []
        for node in nodes:
            if slicer.mrmlScene.IsNodePresent(node):
                removals.append(self._removeSceneNodeAndOwnedAuxiliaries(node))
        return removals

    @staticmethod
    def isPatientContactShellModelNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLModelNode")
            and node.GetAttribute("DENTOBOT.ModelRole")
            == "PatientContactShell"
        )

    @staticmethod
    def patientContactShellParameters(
        clearanceMm: float,
        thicknessMm: float,
        samplingSpacingMm: float,
        blockoutSafetyMm: float = 0.0,
        voxelClosingMm: float = 0.0,
    ) -> dict[str, float]:
        values = {
            "fitClearanceMm": float(clearanceMm),
            "shellThicknessMm": float(thicknessMm),
            "processingResolutionMm": float(samplingSpacingMm),
            "blockoutSafetyMm": float(blockoutSafetyMm),
            "voxelClosingMm": float(voxelClosingMm),
        }
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError(_("Patient-contact shell parameters must be finite."))
        if values["fitClearanceMm"] < 0.0:
            raise ValueError(_("Patient/template fit clearance cannot be negative."))
        if values["shellThicknessMm"] <= 0.0:
            raise ValueError(_("Patient-contact shell thickness must be positive."))
        if not 0.1 <= values["processingResolutionMm"] <= 2.0:
            raise ValueError(
                _("Patient-contact shell processing resolution must be 0.10–2.00 mm.")
            )
        if not 0.0 <= values["blockoutSafetyMm"] <= 3.0:
            raise ValueError(_("Blockout safety must be between 0.00 and 3.00 mm."))
        if not 0.0 <= values["voxelClosingMm"] <= 5.0:
            raise ValueError(_("Voxel closing must be between 0.00 and 5.00 mm."))
        return values

    def validatePatientContactShellInputs(
        self,
        sourceModel: vtkMRMLModelNode,
        visibleSupportModel: vtkMRMLModelNode,
        insertionDirection: vtkMRMLMarkupsLineNode,
        blockoutModel: vtkMRMLModelNode,
        parameters: dict[str, float],
    ) -> dict:
        sourceSummary = self.getDraftTemplateSupportModelSummary(sourceModel)
        visibleSummary = self.getVisibleTemplateSupportModelSummary(
            visibleSupportModel
        )
        directionSummary = self.getTemplateInsertionDirectionSummary(
            insertionDirection
        )
        blockoutSummary = self.getTemplateUndercutOutputSummary(
            blockoutModel,
            "TemplateUndercutBlockout",
        )
        if sourceSummary["geometryState"] != "Current":
            raise ValueError(_("Update the stale full support-anatomy model first."))
        if visibleSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale visible support surface first."))
        if visibleSummary["sourceModel"] is not sourceModel:
            raise ValueError(
                _("The visible support surface belongs to another support model.")
            )
        if directionSummary["sourceSurface"] is not visibleSupportModel:
            raise ValueError(_("The insertion direction belongs to another support surface."))
        if blockoutSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale directional blockout first."))
        if (
            blockoutSummary["sourceModel"] is not sourceModel
            or blockoutSummary["visibleSupport"] is not visibleSupportModel
            or blockoutSummary["insertionDirection"] is not insertionDirection
        ):
            raise ValueError(_("The directional blockout belongs to different inputs."))
        if sourceModel.GetAttribute("DENTOBOT.CoordinateConvention") != "WorldRASmm":
            raise ValueError(
                _(
                    "This legacy draft support model has an obsolete transform "
                    "contract. Update it before generating the patient-contact shell."
                )
            )
        return {
            "sourceSummary": sourceSummary,
            "visibleSummary": visibleSummary,
            "directionSummary": directionSummary,
            "blockoutSummary": blockoutSummary,
            "parameters": parameters,
        }

    def _removePatientContactShellProcessingNodes(
        self,
        shellModel: vtkMRMLModelNode,
    ) -> list[dict]:
        if not self.isPatientContactShellModelNode(shellModel):
            return []
        dynamicRoles = (
            self.TEMPLATE_PATIENT_SHELL_MARGIN_MODELER_REFERENCE_ROLE,
            self.TEMPLATE_PATIENT_SHELL_HOLLOW_MODELER_REFERENCE_ROLE,
        )
        auxiliaryRoles = (
            self.TEMPLATE_PATIENT_SHELL_FITTING_SURFACE_REFERENCE_ROLE,
            self.TEMPLATE_PATIENT_SHELL_HOLLOW_CANDIDATE_REFERENCE_ROLE,
            self.TEMPLATE_PATIENT_SHELL_BOUNDARY_BRIDGE_REFERENCE_ROLE,
        )
        dynamicNodes = [
            shellModel.GetNodeReference(role)
            for role in dynamicRoles
            if shellModel.GetNodeReference(role)
        ]
        auxiliaryNodes = [
            shellModel.GetNodeReference(role)
            for role in auxiliaryRoles
            if shellModel.GetNodeReference(role)
        ]
        wasModifying = shellModel.StartModify()
        try:
            for role in (*dynamicRoles, *auxiliaryRoles):
                shellModel.SetNodeReferenceID(role, None)
        finally:
            shellModel.EndModify(wasModifying)

        removals = []
        for dynamicNode in dynamicNodes:
            if slicer.mrmlScene.IsNodePresent(dynamicNode):
                dynamicNode.SetContinuousUpdate(False)
                dynamicNodeId = dynamicNode.GetID()
                dynamicNodeName = dynamicNode.GetName() or ""
                slicer.mrmlScene.RemoveNode(dynamicNode)
                removals.append(
                    {
                        "nodeId": dynamicNodeId,
                        "nodeName": dynamicNodeName,
                        "auxiliaryNodeIds": [],
                    }
                )
        for auxiliaryNode in auxiliaryNodes:
            if (
                slicer.mrmlScene.IsNodePresent(auxiliaryNode)
                and auxiliaryNode.GetAttribute("DENTOBOT.AuxiliaryOwnerNodeID")
                == shellModel.GetID()
                and auxiliaryNode.GetAttribute("DENTOBOT.ModelRole")
                in {
                    "TemplateFittingSurface",
                    "TemplateHollowCandidate",
                    "TemplateSupportBoundaryBridge",
                }
            ):
                removals.append(
                    self._removeSceneNodeAndOwnedAuxiliaries(auxiliaryNode)
                )
        return removals

    def createOrUpdatePatientContactShell(
        self,
        sourceModel: vtkMRMLModelNode,
        visibleSupportModel: vtkMRMLModelNode,
        insertionDirection: vtkMRMLMarkupsLineNode,
        blockoutModel: vtkMRMLModelNode,
        *,
        clearanceMm: float,
        thicknessMm: float,
        samplingSpacingMm: float,
        blockoutSafetyMm: float = 0.0,
        voxelClosingMm: float = 0.0,
        shellModel: vtkMRMLModelNode | None = None,
    ) -> tuple[vtkMRMLModelNode, dict]:
        """Create a visible-support shell with Dynamic Modeler and voxel fit Boolean."""

        parameters = self.patientContactShellParameters(
            clearanceMm,
            thicknessMm,
            samplingSpacingMm,
            blockoutSafetyMm,
            voxelClosingMm,
        )
        inputs = self.validatePatientContactShellInputs(
            sourceModel,
            visibleSupportModel,
            insertionDirection,
            blockoutModel,
            parameters,
        )
        if not getattr(slicer.modules, "dynamicmodeler", None):
            raise RuntimeError(_("Slicer's Dynamic Modeler module is unavailable."))

        createdShell = shellModel is None
        if shellModel and not self.isPatientContactShellModelNode(shellModel):
            raise ValueError(_("Select the DENTOBOT patient-contact shell output."))
        if not shellModel:
            shellModel = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
                "[Step 5B] DENTO Undercut-Aware Patient-Contact Shell",
            )
        if not shellModel:
            raise RuntimeError(_("Slicer could not create the patient-contact shell."))
        shellModel.SetAttribute("DENTOBOT.ModelRole", "PatientContactShell")
        if not createdShell:
            self._removePatientContactShellProcessingNodes(shellModel)

        previousVisibility = bool(
            not createdShell
            and shellModel.GetDisplayNode()
            and shellModel.GetDisplayNode().GetVisibility()
        )
        fittingSurface = None
        hollowCandidate = None
        boundaryBridge = None
        marginNode = None
        hollowNode = None
        try:
            fittingSurface = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
                "[Step 5B] DENTO Clearance Fitting Surface (auxiliary)",
            )
            hollowCandidate = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
                "[Step 5B] DENTO Hollow Shell Candidate (auxiliary)",
            )
            boundaryBridge = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
                "[Step 5B] DENTO Support Boundary Bridge (auxiliary)",
            )
            if not fittingSurface or not hollowCandidate or not boundaryBridge:
                raise RuntimeError(_("Slicer could not create shell processing models."))
            for auxiliaryNode, role in (
                (fittingSurface, "TemplateFittingSurface"),
                (hollowCandidate, "TemplateHollowCandidate"),
                (boundaryBridge, "TemplateSupportBoundaryBridge"),
            ):
                auxiliaryNode.SetAttribute("DENTOBOT.ModelRole", role)
                auxiliaryNode.SetAttribute(
                    "DENTOBOT.AuxiliaryOwnerNodeID",
                    shellModel.GetID(),
                )
                auxiliaryNode.SetAndObserveTransformNodeID(None)
                auxiliaryNode.CreateDefaultDisplayNodes()
                auxiliaryNode.GetDisplayNode().SetVisibility(False)

            marginNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLDynamicModelerNode",
                "[Step 5B] DENTO Fit Clearance Margin (auxiliary)",
            )
            hollowNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLDynamicModelerNode",
                "[Step 5B] DENTO Patient Shell Hollow (auxiliary)",
            )
            if not marginNode or not hollowNode:
                raise RuntimeError(_("Slicer could not create Dynamic Modeler nodes."))
            for dynamicNode, role in (
                (marginNode, "PatientContactFitMargin"),
                (hollowNode, "PatientContactHollow"),
            ):
                dynamicNode.SetAttribute("DENTOBOT.DynamicModelerRole", role)
                dynamicNode.SetAttribute(
                    "DENTOBOT.AuxiliaryOwnerNodeID",
                    shellModel.GetID(),
                )
                dynamicNode.SetContinuousUpdate(False)

            shellModel.SetNodeReferenceID(
                self.TEMPLATE_PATIENT_SHELL_FITTING_SURFACE_REFERENCE_ROLE,
                fittingSurface.GetID(),
            )
            shellModel.SetNodeReferenceID(
                self.TEMPLATE_PATIENT_SHELL_HOLLOW_CANDIDATE_REFERENCE_ROLE,
                hollowCandidate.GetID(),
            )
            shellModel.SetNodeReferenceID(
                self.TEMPLATE_PATIENT_SHELL_BOUNDARY_BRIDGE_REFERENCE_ROLE,
                boundaryBridge.GetID(),
            )
            shellModel.SetNodeReferenceID(
                self.TEMPLATE_PATIENT_SHELL_MARGIN_MODELER_REFERENCE_ROLE,
                marginNode.GetID(),
            )
            shellModel.SetNodeReferenceID(
                self.TEMPLATE_PATIENT_SHELL_HOLLOW_MODELER_REFERENCE_ROLE,
                hollowNode.GetID(),
            )

            marginNode.SetToolName("Margin")
            marginNode.SetNodeReferenceID(
                "Margin.InputModel",
                visibleSupportModel.GetID(),
            )
            marginNode.SetNodeReferenceID(
                "Margin.OutputModel",
                fittingSurface.GetID(),
            )
            marginNode.SetAttribute(
                "Margin",
                f"{parameters['fitClearanceMm']:.9g}",
            )
            slicer.modules.dynamicmodeler.logic().RunDynamicModelerTool(
                marginNode
            )
            if (
                not fittingSurface.GetPolyData()
                or not fittingSurface.GetPolyData().GetNumberOfCells()
            ):
                raise RuntimeError(_("Dynamic Modeler Margin produced no fitting surface."))

            hollowNode.SetToolName("Hollow")
            hollowNode.SetNodeReferenceID(
                "Hollow.InputModel",
                fittingSurface.GetID(),
            )
            hollowNode.SetNodeReferenceID(
                "Hollow.OutputModel",
                hollowCandidate.GetID(),
            )
            hollowNode.SetAttribute(
                "ShellThickness",
                f"{parameters['shellThicknessMm']:.9g}",
            )
            slicer.modules.dynamicmodeler.logic().RunDynamicModelerTool(
                hollowNode
            )
            candidatePolyData = hollowCandidate.GetPolyData()
            if not candidatePolyData or not candidatePolyData.GetNumberOfCells():
                raise RuntimeError(_("Dynamic Modeler Hollow produced no shell candidate."))

            bridgePolyData, bridgeMetrics = create_support_boundary_bridge(
                self.templateSupportBoundaryControlPointsWorld(
                    inputs["visibleSummary"]["boundary"]
                ),
                inputs["directionSummary"]["removalDirectionRas"],
                fit_clearance_mm=(
                    parameters["fitClearanceMm"]
                    + parameters["blockoutSafetyMm"]
                ),
                shell_thickness_mm=parameters["shellThicknessMm"],
                sampling_spacing_mm=parameters["processingResolutionMm"],
            )
            boundaryBridge.SetAndObservePolyData(bridgePolyData)

            shellPolyData, metrics = regularize_patient_contact_shell(
                candidatePolyData,
                model_polydata_in_world(blockoutModel),
                fit_clearance_mm=(
                    parameters["fitClearanceMm"]
                    + parameters["blockoutSafetyMm"]
                ),
                sampling_spacing_mm=parameters["processingResolutionMm"],
                voxel_closing_mm=parameters["voxelClosingMm"],
                fitting_surface_world=model_polydata_in_world(fittingSurface),
                shell_thickness_mm=parameters["shellThicknessMm"],
                boundary_bridge_world=bridgePolyData,
                terminal_clip_planes_ras=(
                    inputs["visibleSummary"]["terminalClipPlanesRas"]
                ),
            )
            metrics["boundaryBridge"] = bridgeMetrics
            warnings = []
            if metrics["candidateRepairMode"] != "None":
                warnings.append(
                    _(
                        "Dynamic Modeler Hollow had %1 invalid edges; the shell "
                        "was reconstructed from its validated fitting surface "
                        "in the cropped voxel domain."
                    ).replace(
                        "%1",
                        str(
                            metrics["candidateTopology"][
                                "boundaryOrNonManifoldEdgeCount"
                            ]
                        ),
                    )
                )
            if metrics["removedSingleVoxelSpeckleCount"]:
                warnings.append(
                    _(
                        "Removed %1 isolated single-voxel contour artifacts "
                        "before shell topology verification."
                    ).replace(
                        "%1",
                        str(metrics["removedSingleVoxelSpeckleCount"]),
                    )
                )
            if metrics["surfaceRegionCount"] != 1:
                raise ValueError(
                    _(
                        "The support-boundary bridge did not connect all selected "
                        "tooth-shell components (%1 components remain). Redraw one "
                        "continuous loop around every intended support tooth."
                    ).replace("%1", str(metrics["surfaceRegionCount"]))
                )
            timestamp = datetime.now(timezone.utc).isoformat()
            parametersJson = json.dumps(
                parameters,
                sort_keys=True,
                separators=(",", ":"),
            )
            wasModifying = shellModel.StartModify()
            try:
                shellModel.SetName(
                    "[Step 5B] DENTO Undercut-Aware Patient-Contact Shell"
                )
                shellModel.SetAndObservePolyData(shellPolyData)
                shellModel.SetAndObserveTransformNodeID(None)
                shellModel.SetAttribute("DENTOBOT.ModelRole", "PatientContactShell")
                shellModel.SetAttribute(
                    "DENTOBOT.PatientShellSchemaVersion",
                    self.TEMPLATE_PATIENT_SHELL_SCHEMA_VERSION,
                )
                shellModel.SetAttribute("DENTOBOT.Status", "ResearchOnly")
                shellModel.SetAttribute("DENTOBOT.GeometryState", "Current")
                shellModel.SetAttribute("DENTOBOT.StaleReason", None)
                shellModel.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
                shellModel.SetAttribute("DENTOBOT.ParametersJson", parametersJson)
                shellModel.SetAttribute(
                    "DENTOBOT.SourceModelUpdatedUtc",
                    sourceModel.GetAttribute("DENTOBOT.UpdatedUtc") or "",
                )
                shellModel.SetAttribute(
                    "DENTOBOT.VisibleSupportUpdatedUtc",
                    visibleSupportModel.GetAttribute("DENTOBOT.UpdatedUtc") or "",
                )
                shellModel.SetAttribute(
                    "DENTOBOT.GeometryMetricsJson",
                    json.dumps(metrics, sort_keys=True, separators=(",", ":")),
                )
                shellModel.SetAttribute(
                    "DENTOBOT.ValidationWarningsJson",
                    json.dumps(warnings, separators=(",", ":")),
                )
                shellModel.SetAttribute("DENTOBOT.UndercutState", "Processed")
                shellModel.SetAttribute(
                    "DENTOBOT.InsertionGeometryJson",
                    inputs["directionSummary"]["geometryJson"],
                )
                shellModel.SetAttribute(
                    "DENTOBOT.BlockoutUpdatedUtc",
                    blockoutModel.GetAttribute("DENTOBOT.UpdatedUtc") or "",
                )
                shellModel.SetAttribute("DENTOBOT.UpdatedUtc", timestamp)
                shellModel.SetNodeReferenceID(
                    self.TEMPLATE_PATIENT_SHELL_SOURCE_ANATOMY_REFERENCE_ROLE,
                    sourceModel.GetID(),
                )
                shellModel.SetNodeReferenceID(
                    self.TEMPLATE_PATIENT_SHELL_SOURCE_SURFACE_REFERENCE_ROLE,
                    visibleSupportModel.GetID(),
                )
                shellModel.SetNodeReferenceID(
                    self.TEMPLATE_VISIBLE_SUPPORT_BOUNDARY_REFERENCE_ROLE,
                    inputs["visibleSummary"]["boundary"].GetID(),
                )
                shellModel.SetNodeReferenceID(
                    self.TEMPLATE_PATIENT_SHELL_INSERTION_DIRECTION_REFERENCE_ROLE,
                    insertionDirection.GetID(),
                )
                shellModel.SetNodeReferenceID(
                    self.TEMPLATE_PATIENT_SHELL_BLOCKOUT_REFERENCE_ROLE,
                    blockoutModel.GetID(),
                )
                shellModel.SetNodeReferenceID(
                    self.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE,
                    inputs["sourceSummary"]["sourceSegmentation"].GetID(),
                )
                shellModel.SetNodeReferenceID(
                    self.TEMPLATE_PATIENT_SHELL_FITTING_SURFACE_REFERENCE_ROLE,
                    fittingSurface.GetID(),
                )
                shellModel.SetNodeReferenceID(
                    self.TEMPLATE_PATIENT_SHELL_HOLLOW_CANDIDATE_REFERENCE_ROLE,
                    hollowCandidate.GetID(),
                )
                shellModel.SetNodeReferenceID(
                    self.TEMPLATE_PATIENT_SHELL_BOUNDARY_BRIDGE_REFERENCE_ROLE,
                    boundaryBridge.GetID(),
                )
                shellModel.SetNodeReferenceID(
                    self.TEMPLATE_PATIENT_SHELL_MARGIN_MODELER_REFERENCE_ROLE,
                    marginNode.GetID(),
                )
                shellModel.SetNodeReferenceID(
                    self.TEMPLATE_PATIENT_SHELL_HOLLOW_MODELER_REFERENCE_ROLE,
                    hollowNode.GetID(),
                )
            finally:
                shellModel.EndModify(wasModifying)

            shellModel.CreateDefaultDisplayNodes()
            displayNode = shellModel.GetDisplayNode()
            if displayNode:
                displayNode.SetVisibility(previousVisibility if not createdShell else True)
                displayNode.SetVisibility2D(False)
                displayNode.SetVisibility3D(True)
                displayNode.SetOpacity(1.0)
                displayNode.SetColor(0.95, 0.70, 0.18)
                displayNode.SetBackfaceCulling(False)
            lineageColor = self.lineageColorFromNode(sourceModel)
            if lineageColor:
                self.setNodeLineageColor(
                    shellModel,
                    lineageColor,
                    sourceModel.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE) or "",
                    sourceModel.GetAttribute(self.LINEAGE_TARGET_FDI_ATTRIBUTE) or "",
                )
            return shellModel, {
                "parameters": parameters,
                "metrics": metrics,
                "warnings": warnings,
            }
        except Exception:
            if self.isPatientContactShellModelNode(shellModel):
                self._removePatientContactShellProcessingNodes(shellModel)
                if createdShell and slicer.mrmlScene.IsNodePresent(shellModel):
                    self._removeSceneNodeAndOwnedAuxiliaries(shellModel)
                elif not createdShell:
                    self.markPatientContactShellStale(
                        shellModel,
                        _("Patient-contact shell regeneration failed."),
                    )
            raise

    def getPatientContactShellSummary(
        self,
        shellModel: vtkMRMLModelNode,
    ) -> dict:
        if not self.isPatientContactShellModelNode(shellModel):
            raise ValueError(_("Select the DENTOBOT patient-contact shell."))
        polyData = shellModel.GetPolyData()
        if not polyData or not polyData.GetNumberOfCells():
            raise ValueError(_("The patient-contact shell contains no geometry."))
        sourceModel = shellModel.GetNodeReference(
            self.TEMPLATE_PATIENT_SHELL_SOURCE_ANATOMY_REFERENCE_ROLE
        )
        visibleSupport = shellModel.GetNodeReference(
            self.TEMPLATE_PATIENT_SHELL_SOURCE_SURFACE_REFERENCE_ROLE
        )
        boundary = shellModel.GetNodeReference(
            self.TEMPLATE_VISIBLE_SUPPORT_BOUNDARY_REFERENCE_ROLE
        )
        sourceSegmentation = shellModel.GetNodeReference(
            self.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE
        )
        insertionDirection = shellModel.GetNodeReference(
            self.TEMPLATE_PATIENT_SHELL_INSERTION_DIRECTION_REFERENCE_ROLE
        )
        blockoutModel = shellModel.GetNodeReference(
            self.TEMPLATE_PATIENT_SHELL_BLOCKOUT_REFERENCE_ROLE
        )
        fittingSurface = shellModel.GetNodeReference(
            self.TEMPLATE_PATIENT_SHELL_FITTING_SURFACE_REFERENCE_ROLE
        )
        hollowCandidate = shellModel.GetNodeReference(
            self.TEMPLATE_PATIENT_SHELL_HOLLOW_CANDIDATE_REFERENCE_ROLE
        )
        boundaryBridge = shellModel.GetNodeReference(
            self.TEMPLATE_PATIENT_SHELL_BOUNDARY_BRIDGE_REFERENCE_ROLE
        )
        marginModeler = shellModel.GetNodeReference(
            self.TEMPLATE_PATIENT_SHELL_MARGIN_MODELER_REFERENCE_ROLE
        )
        hollowModeler = shellModel.GetNodeReference(
            self.TEMPLATE_PATIENT_SHELL_HOLLOW_MODELER_REFERENCE_ROLE
        )
        if not self.isDraftTemplateSupportModelNode(sourceModel):
            raise ValueError(_("The patient-contact shell lost its source anatomy."))
        if not self.isVisibleTemplateSupportModelNode(visibleSupport):
            raise ValueError(_("The patient-contact shell lost its visible support surface."))
        if not self.isTemplateSupportBoundaryNode(boundary):
            raise ValueError(_("The patient-contact shell lost its support boundary."))
        if not sourceSegmentation or not sourceSegmentation.IsA(
            "vtkMRMLSegmentationNode"
        ):
            raise ValueError(_("The patient-contact shell lost its segmentation reference."))
        if not self.isTemplateInsertionDirectionNode(insertionDirection):
            raise ValueError(_("The patient-contact shell lost its insertion direction."))
        if not self.isTemplateUndercutBlockoutModelNode(blockoutModel):
            raise ValueError(_("The patient-contact shell lost its directional blockout."))
        if (
            not fittingSurface
            or fittingSurface.GetAttribute("DENTOBOT.ModelRole")
            != "TemplateFittingSurface"
            or not hollowCandidate
            or hollowCandidate.GetAttribute("DENTOBOT.ModelRole")
            != "TemplateHollowCandidate"
            or not boundaryBridge
            or boundaryBridge.GetAttribute("DENTOBOT.ModelRole")
            != "TemplateSupportBoundaryBridge"
            or not marginModeler
            or not marginModeler.IsA("vtkMRMLDynamicModelerNode")
            or not hollowModeler
            or not hollowModeler.IsA("vtkMRMLDynamicModelerNode")
        ):
            raise ValueError(
                _(
                    "The patient-contact shell lost its owned boundary-bridge "
                    "or Margin/Hollow provenance nodes."
                )
            )
        return {
            "geometryState": shellModel.GetAttribute("DENTOBOT.GeometryState") or "Unknown",
            "staleReason": shellModel.GetAttribute("DENTOBOT.StaleReason") or "",
            "sourceModel": sourceModel,
            "visibleSupport": visibleSupport,
            "boundary": boundary,
            "sourceSegmentation": sourceSegmentation,
            "insertionDirection": insertionDirection,
            "blockoutModel": blockoutModel,
            "fittingSurface": fittingSurface,
            "hollowCandidate": hollowCandidate,
            "boundaryBridge": boundaryBridge,
            "marginModeler": marginModeler,
            "hollowModeler": hollowModeler,
            "parametersJson": shellModel.GetAttribute("DENTOBOT.ParametersJson") or "",
            "sourceModelUpdatedUtc": shellModel.GetAttribute(
                "DENTOBOT.SourceModelUpdatedUtc"
            ) or "",
            "visibleSupportUpdatedUtc": shellModel.GetAttribute(
                "DENTOBOT.VisibleSupportUpdatedUtc"
            ) or "",
            "insertionGeometryJson": shellModel.GetAttribute(
                "DENTOBOT.InsertionGeometryJson"
            ) or "",
            "blockoutUpdatedUtc": shellModel.GetAttribute(
                "DENTOBOT.BlockoutUpdatedUtc"
            ) or "",
            "metrics": json.loads(
                shellModel.GetAttribute("DENTOBOT.GeometryMetricsJson") or "{}"
            ),
            "warnings": json.loads(
                shellModel.GetAttribute("DENTOBOT.ValidationWarningsJson") or "[]"
            ),
            "undercutState": shellModel.GetAttribute("DENTOBOT.UndercutState") or "Unknown",
            "pointCount": int(polyData.GetNumberOfPoints()),
            "cellCount": int(polyData.GetNumberOfCells()),
        }

    @staticmethod
    def markPatientContactShellStale(
        shellModel: vtkMRMLModelNode | None,
        reason: str,
    ) -> bool:
        if not DENTOWorkflowLogic.isPatientContactShellModelNode(shellModel):
            return False
        shellModel.SetAttribute("DENTOBOT.GeometryState", "Stale")
        shellModel.SetAttribute(
            "DENTOBOT.StaleReason",
            str(reason).strip() or "Visible support or fit parameters changed.",
        )
        return True

    def deletePatientContactShell(
        self,
        shellModel: vtkMRMLModelNode,
    ) -> list[dict]:
        if not self.isPatientContactShellModelNode(shellModel):
            raise ValueError(_("Select a DENTOBOT patient-contact shell to delete."))
        parameterNode = self.getParameterNode()
        if parameterNode.patientContactShellModel is shellModel:
            parameterNode.patientContactShellModel = None
        removals = self._removePatientContactShellProcessingNodes(shellModel)
        if slicer.mrmlScene.IsNodePresent(shellModel):
            removals.append(self._removeSceneNodeAndOwnedAuxiliaries(shellModel))
        return removals
