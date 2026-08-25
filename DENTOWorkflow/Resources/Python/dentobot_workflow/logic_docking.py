"""Extracted target docking geometry methods; public APIs remain on GuideLogicMixin."""

from __future__ import annotations

from .runtime import *


class DockingLogicMixin:
    @staticmethod
    def isTargetDockingReferencePlaneNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsPlaneNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole")
            == "TargetDockingReferencePlane"
        )

    @staticmethod
    def isTargetDockingAssemblyModelNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLModelNode")
            and node.GetAttribute("DENTOBOT.ModelRole")
            == "TargetDockingAssembly"
        )

    def targetDockingTrajectoriesForTarget(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        targetSegmentId: str,
    ) -> list[vtkMRMLMarkupsLineNode]:
        trajectories = self.dentobotTrajectoriesForTarget(
            segmentationNode,
            targetSegmentId,
        )
        if len(trajectories) > 2:
            raise ValueError(
                _(
                    "Step 4C supports at most two target-tooth trajectories. "
                    "Delete or reassign extra trajectories before generating docks."
                )
            )
        for trajectoryNode in trajectories:
            summary = self.getTrajectorySummary(trajectoryNode)
            if not summary["isValid"] or summary["definedPointCount"] != 2:
                raise ValueError(
                    _("Complete both Entry and Target on every target-tooth trajectory.")
                )
            if not trajectoryNode.GetLocked():
                raise ValueError(
                    _("Verify and lock every target-tooth trajectory before Step 4C.")
                )
        if not trajectories:
            raise ValueError(
                _("Create, verify, and lock one or two target-tooth trajectories first.")
            )
        return trajectories

    def _targetDockingObstacleSurfaces(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        targetRecord: dict,
        supportSegmentIds: list[str] | None = None,
    ) -> tuple[list[vtk.vtkPolyData], list[str], list[str]]:
        """Return other same-jaw whole teeth used by the draft yaw screen."""

        targetArch = self.dentalArchForFdi(targetRecord.get("fdiNumber") or "")
        if not targetArch:
            raise ValueError(
                _(
                    "The target tooth has no valid permanent-tooth FDI arch; "
                    "automatic same-jaw dock screening is unavailable."
                )
            )
        surfaces = []
        segmentIds = []
        omittedSegmentIds = []
        supportOrder = {
            segmentId: index
            for index, segmentId in enumerate(supportSegmentIds or [])
        }
        records = sorted(
            self.getTargetToothRecords(segmentationNode),
            key=lambda record: (
                record["segmentId"] not in supportOrder,
                supportOrder.get(record["segmentId"], 10_000),
                record["segmentId"],
            ),
        )
        for record in records:
            segmentId = record["segmentId"]
            if (
                segmentId == targetRecord["segmentId"]
                or self.dentalArchForFdi(record.get("fdiNumber") or "")
                != targetArch
            ):
                continue
            try:
                surfaces.append(
                    self._getClosedSurfaceWorldCopy(segmentationNode, segmentId)
                )
                segmentIds.append(segmentId)
            except ValueError:
                omittedSegmentIds.append(segmentId)
        return surfaces, segmentIds, omittedSegmentIds

    def _removeTargetDockingMeasurementNodes(
        self,
        assemblyModel: vtkMRMLModelNode | None,
    ) -> list[str]:
        if not assemblyModel:
            return []
        role = self.TARGET_DOCKING_MEASUREMENT_REFERENCE_ROLE
        nodes = [
            assemblyModel.GetNthNodeReference(role, index)
            for index in range(assemblyModel.GetNumberOfNodeReferences(role))
        ]
        assemblyModel.RemoveNodeReferenceIDs(role)
        removedIds = []
        for node in nodes:
            if node and node.GetID() and slicer.mrmlScene.IsNodePresent(node):
                removedIds.append(node.GetID())
                self._removeSceneNodeAndOwnedAuxiliaries(node)
        return removedIds

    def _createTargetDockingMeasurementLine(
        self,
        assemblyModel: vtkMRMLModelNode,
        name: str,
        startRas,
        endRas,
        role: str,
        color: tuple[float, float, float],
        visible: bool,
    ) -> vtkMRMLMarkupsLineNode:
        node = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsLineNode",
            name,
        )
        if not node:
            raise RuntimeError(_("Slicer could not create a Step 4C annotation."))
        wasModifying = node.StartModify()
        try:
            node.SetName(name)
            node.SetAttribute("DENTOBOT.MarkupsRole", "TargetDockingMeasurement")
            node.SetAttribute("DENTOBOT.MeasurementRole", role)
            node.SetAttribute("DENTOBOT.OwnerAssemblyNodeID", assemblyModel.GetID())
            node.SetAttribute("DENTOBOT.Status", "ResearchOnly")
            node.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
            node.AddControlPointWorld(vtk.vtkVector3d(*startRas))
            node.AddControlPointWorld(vtk.vtkVector3d(*endRas))
            node.SetNthControlPointLabel(0, "")
            node.SetNthControlPointLabel(1, "")
            node.SetLocked(True)
            node.SetSelectable(False)
        finally:
            node.EndModify(wasModifying)
        node.CreateDefaultDisplayNodes()
        displayNode = node.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(bool(visible))
            displayNode.SetVisibility2D(bool(visible))
            displayNode.SetVisibility3D(bool(visible))
            displayNode.SetPointLabelsVisibility(False)
            displayNode.SetPropertiesLabelVisibility(True)
            displayNode.SetSliceProjection(True)
            displayNode.SetSliceProjectionUseFiducialColor(True)
            displayNode.SetSliceProjectionOpacity(1.0)
            displayNode.SetColor(*color)
            displayNode.SetSelectedColor(*color)
            displayNode.SetLineThickness(0.32)
            displayNode.SetGlyphScale(0.7)
            if hasattr(displayNode, "SetTextScale"):
                displayNode.SetTextScale(2.0)
        return node

    def createTargetDockingMeasurementNodes(
        self,
        assemblyModel: vtkMRMLModelNode,
        frame: dict,
        metrics: dict,
        parameters: dict,
        *,
        visible: bool,
    ) -> list[vtkMRMLMarkupsLineNode]:
        """Create referenced, read-only Step 4C dimension annotations."""

        self._removeTargetDockingMeasurementNodes(assemblyModel)
        origin = np.asarray(frame["originRas"], dtype=float)
        zAxis = np.asarray(frame["zAxisRas"], dtype=float)
        zAxis /= np.linalg.norm(zAxis)
        maxDepth = max(float(value) for value in parameters["depthsMm"])
        nodes = [
            self._createTargetDockingMeasurementLine(
                assemblyModel,
                _("[Step 4C Measure] Assumed crown centroid / occlusal normal"),
                origin - zAxis * max(3.0, 0.35 * maxDepth),
                origin + zAxis * max(6.0, 1.15 * maxDepth),
                "CentroidNormal",
                (0.20, 0.90, 1.00),
                visible,
            )
        ]
        outerDiameter = float(parameters["outerDiameterMm"])
        boreDiameter = float(parameters["boreDiameterMm"])
        for dock in metrics["docks"]:
            dockLabel = str(dock["label"])
            top = np.asarray(dock["topFaceCenterRas"], dtype=float)
            terminal = np.asarray(dock["terminalCenterRas"], dtype=float)
            radial = top - origin
            radialLength = float(np.linalg.norm(radial))
            radialDirection = radial / radialLength
            diameterDirection = np.cross(zAxis, radialDirection)
            diameterDirection /= np.linalg.norm(diameterDirection)
            nodes.append(
                self._createTargetDockingMeasurementLine(
                    assemblyModel,
                    _("[Step 4C Measure] Dock %1 radius = %2 mm")
                    .replace("%1", dockLabel)
                    .replace("%2", f"{radialLength:.2f}"),
                    origin,
                    top,
                    "CentroidDistance",
                    (1.00, 0.78, 0.10),
                    visible,
                )
            )
            nodes.append(
                self._createTargetDockingMeasurementLine(
                    assemblyModel,
                    _("[Step 4C Measure] Dock %1 OD = %2 mm; bore = %3 mm")
                    .replace("%1", dockLabel)
                    .replace("%2", f"{outerDiameter:.2f}")
                    .replace("%3", f"{boreDiameter:.2f}"),
                    top - diameterDirection * (outerDiameter / 2.0),
                    top + diameterDirection * (outerDiameter / 2.0),
                    "DockDiameter",
                    (1.00, 0.35, 0.80),
                    visible,
                )
            )
            nodes.append(
                self._createTargetDockingMeasurementLine(
                    assemblyModel,
                    _("[Step 4C Measure] Dock %1 depth = %2 mm")
                    .replace("%1", dockLabel)
                    .replace("%2", f"{float(dock['depthMm']):.2f}"),
                    top,
                    terminal,
                    "DockDepth",
                    (0.45, 1.00, 0.38),
                    visible,
                )
            )
        self._setRepeatedNodeReferences(
            assemblyModel,
            self.TARGET_DOCKING_MEASUREMENT_REFERENCE_ROLE,
            nodes,
        )
        return nodes

    def createOrUpdateTargetDockingAssembly(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        targetSegmentId: str,
        trajectories: list[vtkMRMLMarkupsLineNode],
        parameters: dict,
        *,
        supportModel: vtkMRMLModelNode | None = None,
        planeNode: vtkMRMLMarkupsPlaneNode | None = None,
        assemblyModel: vtkMRMLModelNode | None = None,
        autoSelectYaw: bool = False,
        measurementsVisible: bool = True,
    ) -> tuple[vtkMRMLMarkupsPlaneNode, vtkMRMLModelNode, dict]:
        targetRecord = self.validateTargetTooth(segmentationNode, targetSegmentId)
        supportSummary = self.getDraftTemplateSupportModelSummary(supportModel)
        if supportSummary["geometryState"] != "Current":
            raise ValueError(_("Update the stale Step 4B support-anatomy draft first."))
        if supportSummary["sourceSegmentation"] is not segmentationNode:
            raise ValueError(_("The Step 4B support draft belongs to another segmentation."))
        if supportSummary["targetSegmentId"] != targetRecord["segmentId"]:
            raise ValueError(_("The Step 4B support draft belongs to another target tooth."))
        supportSegmentIds = supportSummary["supportSegmentIds"]
        if self.getSegmentationReviewState(segmentationNode) != "Reviewed":
            raise ValueError(_("Mark the authoritative segmentation Reviewed first."))
        expectedTrajectories = self.targetDockingTrajectoriesForTarget(
            segmentationNode,
            targetRecord["segmentId"],
        )
        if [node.GetID() for node in trajectories] != [
            node.GetID() for node in expectedTrajectories
        ]:
            raise ValueError(
                _("Step 4C must use the complete ordered target-tooth trajectory set.")
            )
        trajectoryGeometry = []
        for trajectoryNode in trajectories:
            summary = self.getTrajectorySummary(trajectoryNode)
            trajectoryGeometry.append(
                {
                    "entryRas": [float(value) for value in summary["entryRas"]],
                    "targetRas": [float(value) for value in summary["targetRas"]],
                }
            )
        toothSurfaceWorld = self._getClosedSurfaceWorldCopy(
            segmentationNode,
            targetRecord["segmentId"],
        )
        frame = compute_target_docking_frame(
            toothSurfaceWorld,
            trajectoryGeometry,
            crown_cap_fraction=0.10,
        )
        obstacleSurfaces, obstacleSegmentIds, omittedObstacleSegmentIds = (
            self._targetDockingObstacleSurfaces(
                segmentationNode,
                targetRecord,
                supportSegmentIds,
            )
        )
        parameters = dict(parameters)
        autoYawSearch = None
        if autoSelectYaw:
            autoYawSearch = find_collision_aware_target_docking_yaw(
                frame,
                parameters,
                obstacleSurfaces,
            )
            parameters["yawDeg"] = float(autoYawSearch["selectedYawDeg"])
            collisionScreen = autoYawSearch["selectedClearanceReport"]
        else:
            collisionScreen = evaluate_target_docking_obstacle_clearance(
                frame,
                parameters,
                obstacleSurfaces,
            )
        surfaces, metrics = create_target_frame_docking_geometry(
            frame,
            parameters,
        )
        metrics = {
            **metrics,
            "collisionScreen": collisionScreen,
            "autoYawSearch": autoYawSearch,
            "obstacleScope": "SelectedSupportsFirstThenAllOtherWholeTeethOnTargetFdiArch",
            "supportSegmentIds": list(supportSegmentIds),
            "obstacleSegmentIds": list(obstacleSegmentIds),
            "omittedObstacleSegmentIds": list(omittedObstacleSegmentIds),
        }

        if planeNode and not self.isTargetDockingReferencePlaneNode(planeNode):
            raise ValueError(_("Select the DENTOBOT Step 4C target reference plane."))
        if assemblyModel and not self.isTargetDockingAssemblyModelNode(assemblyModel):
            raise ValueError(_("Select the DENTOBOT Step 4C docking assembly."))
        planeNode = planeNode or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsPlaneNode",
            "[Step 4C] DENTO Target Crown Occlusal Dock Plane",
        )
        assemblyModel = assemblyModel or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "[Step 4C] DENTO Four Independent Robot Docks",
        )
        if not planeNode or not assemblyModel:
            raise RuntimeError(_("Slicer could not create the Step 4C docking nodes."))

        parametersJson = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        frameJson = json.dumps(frame, sort_keys=True, separators=(",", ":"))
        trajectoryJson = json.dumps(
            trajectoryGeometry,
            sort_keys=True,
            separators=(",", ":"),
        )
        timestamp = datetime.now(timezone.utc).isoformat()
        planeWasModifying = planeNode.StartModify()
        try:
            planeNode.SetName("[Step 4C] DENTO Target Crown Occlusal Dock Plane")
            planeNode.SetPlaneType(planeNode.PlaneTypePointNormal)
            if hasattr(planeNode, "SetNormalPointRequired"):
                planeNode.SetNormalPointRequired(False)
            planeNode.SetOriginWorld(frame["originRas"])
            planeNode.SetNormalWorld(frame["zAxisRas"])
            planeSize = max(10.0, 2.4 * float(parameters["patternRadiusMm"]))
            planeNode.SetSize(planeSize, planeSize)
            planeNode.SetLocked(True)
            planeNode.SetSelectable(False)
            planeNode.SetAttribute("DENTOBOT.MarkupsRole", "TargetDockingReferencePlane")
            planeNode.SetAttribute(
                "DENTOBOT.TargetDockingSchemaVersion",
                self.TARGET_DOCKING_SCHEMA_VERSION,
            )
            planeNode.SetAttribute("DENTOBOT.Status", "ResearchOnly")
            planeNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
            planeNode.SetAttribute("DENTOBOT.FrameJson", frameJson)
            planeNode.SetAttribute("DENTOBOT.ParametersJson", parametersJson)
            planeNode.SetAttribute("DENTOBOT.TrajectoryGeometryJson", trajectoryJson)
            planeNode.SetAttribute("DENTOBOT.TargetSegmentId", targetRecord["segmentId"])
            planeNode.SetAttribute("DENTOBOT.OrientationState", "Draft")
            planeNode.SetAttribute("DENTOBOT.OrientationConfirmedUtc", None)
            planeNode.SetAttribute(
                "DENTOBOT.ObstacleSegmentIdsJson",
                json.dumps(obstacleSegmentIds, separators=(",", ":")),
            )
            planeNode.SetAttribute(
                "DENTOBOT.SupportSegmentIdsJson",
                json.dumps(supportSegmentIds, separators=(",", ":")),
            )
            planeNode.SetNodeReferenceID(
                self.TARGET_DOCKING_SOURCE_SUPPORT_REFERENCE_ROLE,
                supportModel.GetID(),
            )
            planeNode.SetAttribute("DENTOBOT.UpdatedUtc", timestamp)
            planeNode.SetNodeReferenceID(
                self.TARGET_DOCKING_SOURCE_SEGMENTATION_REFERENCE_ROLE,
                segmentationNode.GetID(),
            )
            self._setRepeatedNodeReferences(
                planeNode,
                self.TARGET_DOCKING_SOURCE_TRAJECTORY_REFERENCE_ROLE,
                trajectories,
            )
        finally:
            planeNode.EndModify(planeWasModifying)
        planeNode.CreateDefaultDisplayNodes()
        planeDisplay = planeNode.GetDisplayNode()
        if planeDisplay:
            planeDisplay.SetVisibility(True)
            planeDisplay.SetVisibility2D(True)
            planeDisplay.SetVisibility3D(True)
            planeDisplay.SetHandlesInteractive(False)
            planeDisplay.SetTranslationHandleVisibility(False)
            planeDisplay.SetRotationHandleVisibility(False)
            planeDisplay.SetScaleHandleVisibility(False)
            planeDisplay.SetOpacity(0.22)
            planeDisplay.SetColor(0.20, 0.75, 0.95)

        modelWasModifying = assemblyModel.StartModify()
        try:
            assemblyModel.SetName("[Step 4C] DENTO Four Independent Robot Docks")
            assemblyModel.SetAndObservePolyData(surfaces["preview"])
            assemblyModel.SetAndObserveTransformNodeID(None)
            assemblyModel.SetAttribute("DENTOBOT.ModelRole", "TargetDockingAssembly")
            assemblyModel.SetAttribute(
                "DENTOBOT.TargetDockingSchemaVersion",
                self.TARGET_DOCKING_SCHEMA_VERSION,
            )
            assemblyModel.SetAttribute("DENTOBOT.Status", "ResearchOnly")
            assemblyModel.SetAttribute("DENTOBOT.GeometryState", "Current")
            assemblyModel.SetAttribute("DENTOBOT.StaleReason", None)
            assemblyModel.SetAttribute("DENTOBOT.OrientationState", "Draft")
            assemblyModel.SetAttribute("DENTOBOT.OrientationConfirmedUtc", None)
            assemblyModel.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
            assemblyModel.SetAttribute("DENTOBOT.TargetSegmentId", targetRecord["segmentId"])
            assemblyModel.SetAttribute(
                "DENTOBOT.ObstacleSegmentIdsJson",
                json.dumps(obstacleSegmentIds, separators=(",", ":")),
            )
            assemblyModel.SetAttribute(
                "DENTOBOT.SupportSegmentIdsJson",
                json.dumps(supportSegmentIds, separators=(",", ":")),
            )
            assemblyModel.SetAttribute(
                "DENTOBOT.SupportDraftUpdatedUtc", supportSummary["updatedUtc"]
            )
            assemblyModel.SetAttribute(
                "DENTOBOT.OmittedObstacleSegmentIdsJson",
                json.dumps(omittedObstacleSegmentIds, separators=(",", ":")),
            )
            assemblyModel.SetAttribute("DENTOBOT.ParametersJson", parametersJson)
            assemblyModel.SetAttribute("DENTOBOT.FrameJson", frameJson)
            assemblyModel.SetAttribute("DENTOBOT.TrajectoryGeometryJson", trajectoryJson)
            assemblyModel.SetAttribute(
                "DENTOBOT.GeometryMetricsJson",
                json.dumps(metrics, sort_keys=True, separators=(",", ":")),
            )
            assemblyModel.SetAttribute("DENTOBOT.UpdatedUtc", timestamp)
            assemblyModel.SetNodeReferenceID(
                self.TARGET_DOCKING_SOURCE_SEGMENTATION_REFERENCE_ROLE,
                segmentationNode.GetID(),
            )
            assemblyModel.SetNodeReferenceID(
                self.TARGET_DOCKING_SOURCE_SUPPORT_REFERENCE_ROLE,
                supportModel.GetID(),
            )
            assemblyModel.SetNodeReferenceID(
                self.TARGET_DOCKING_REFERENCE_PLANE_REFERENCE_ROLE,
                planeNode.GetID(),
            )
            self._setRepeatedNodeReferences(
                assemblyModel,
                self.TARGET_DOCKING_SOURCE_TRAJECTORY_REFERENCE_ROLE,
                trajectories,
            )
        finally:
            assemblyModel.EndModify(modelWasModifying)
        assemblyModel.CreateDefaultDisplayNodes()
        modelDisplay = assemblyModel.GetDisplayNode()
        if modelDisplay:
            modelDisplay.SetVisibility(True)
            modelDisplay.SetVisibility2D(False)
            modelDisplay.SetVisibility3D(True)
            modelDisplay.SetColor(0.12, 0.75, 0.92)
            modelDisplay.SetBackfaceCulling(False)
        lineageColor = self.lineageColorForTarget(
            targetRecord["segmentId"],
            targetRecord.get("fdiNumber") or "",
        )
        self.setNodeLineageColor(
            assemblyModel,
            lineageColor,
            targetRecord["segmentId"],
            targetRecord.get("fdiNumber") or "",
        )
        self.setNodeLineageColor(
            planeNode,
            lineageColor,
            targetRecord["segmentId"],
            targetRecord.get("fdiNumber") or "",
        )
        measurementNodes = self.createTargetDockingMeasurementNodes(
            assemblyModel,
            frame,
            metrics,
            parameters,
            visible=bool(measurementsVisible),
        )
        return planeNode, assemblyModel, {
            "frame": frame,
            "parameters": parameters,
            "surfaces": surfaces,
            "metrics": metrics,
            "measurementNodes": measurementNodes,
        }

    def getTargetDockingAssemblySummary(self, assemblyModel: vtkMRMLModelNode) -> dict:
        if not self.isTargetDockingAssemblyModelNode(assemblyModel):
            raise ValueError(_("Select the DENTOBOT Step 4C docking assembly."))
        polyData = assemblyModel.GetPolyData()
        if not polyData or not polyData.GetNumberOfCells():
            raise ValueError(_("The Step 4C docking assembly contains no geometry."))
        segmentationNode = assemblyModel.GetNodeReference(
            self.TARGET_DOCKING_SOURCE_SEGMENTATION_REFERENCE_ROLE
        )
        planeNode = assemblyModel.GetNodeReference(
            self.TARGET_DOCKING_REFERENCE_PLANE_REFERENCE_ROLE
        )
        supportModel = assemblyModel.GetNodeReference(
            self.TARGET_DOCKING_SOURCE_SUPPORT_REFERENCE_ROLE
        )
        if not segmentationNode or not segmentationNode.IsA("vtkMRMLSegmentationNode"):
            raise ValueError(_("The Step 4C assembly lost its segmentation reference."))
        if not self.isTargetDockingReferencePlaneNode(planeNode):
            raise ValueError(_("The Step 4C assembly lost its reference plane."))
        role = self.TARGET_DOCKING_SOURCE_TRAJECTORY_REFERENCE_ROLE
        trajectories = [
            assemblyModel.GetNthNodeReference(role, index)
            for index in range(assemblyModel.GetNumberOfNodeReferences(role))
            if assemblyModel.GetNthNodeReference(role, index)
        ]
        if not trajectories:
            raise ValueError(_("The Step 4C assembly lost its source trajectories."))
        schemaVersion = assemblyModel.GetAttribute(
            "DENTOBOT.TargetDockingSchemaVersion"
        ) or "Legacy"
        geometryState = assemblyModel.GetAttribute("DENTOBOT.GeometryState") or "Unknown"
        staleReason = assemblyModel.GetAttribute("DENTOBOT.StaleReason") or ""
        if schemaVersion != self.TARGET_DOCKING_SCHEMA_VERSION:
            geometryState = "Stale"
            staleReason = _(
                "This Step 4C assembly predates collision-aware yaw with support-anatomy provenance and the "
                "explicit orientation-confirmation contract; regenerate it."
            )
        elif not self.isDraftTemplateSupportModelNode(supportModel):
            geometryState = "Stale"
            staleReason = _(
                "The Step 4C assembly lost its Step 4B support-anatomy reference."
            )
        else:
            supportSummary = self.getDraftTemplateSupportModelSummary(supportModel)
            storedSupportIds = json.loads(
                assemblyModel.GetAttribute("DENTOBOT.SupportSegmentIdsJson") or "[]"
            )
            storedSupportUpdatedUtc = (
                assemblyModel.GetAttribute("DENTOBOT.SupportDraftUpdatedUtc") or ""
            )
            if supportSummary["geometryState"] != "Current":
                geometryState = "Stale"
                staleReason = _("The referenced Step 4B support draft is stale.")
            elif supportSummary["sourceSegmentation"] is not segmentationNode:
                geometryState = "Stale"
                staleReason = _("The Step 4B support draft uses another segmentation.")
            elif supportSummary["targetSegmentId"] != (
                assemblyModel.GetAttribute("DENTOBOT.TargetSegmentId") or ""
            ):
                geometryState = "Stale"
                staleReason = _("The Step 4B support draft uses another target tooth.")
            elif supportSummary["supportSegmentIds"] != storedSupportIds:
                geometryState = "Stale"
                staleReason = _("The Step 4B support selection changed.")
            elif supportSummary["updatedUtc"] != storedSupportUpdatedUtc:
                geometryState = "Stale"
                staleReason = _("The Step 4B support geometry changed.")
        measurementRole = self.TARGET_DOCKING_MEASUREMENT_REFERENCE_ROLE
        measurementNodes = [
            assemblyModel.GetNthNodeReference(measurementRole, index)
            for index in range(
                assemblyModel.GetNumberOfNodeReferences(measurementRole)
            )
            if assemblyModel.GetNthNodeReference(measurementRole, index)
        ]
        return {
            "schemaVersion": schemaVersion,
            "geometryState": geometryState,
            "staleReason": staleReason,
            "segmentation": segmentationNode,
            "targetSegmentId": assemblyModel.GetAttribute("DENTOBOT.TargetSegmentId") or "",
            "plane": planeNode,
            "supportModel": supportModel,
            "supportSegmentIds": json.loads(
                assemblyModel.GetAttribute("DENTOBOT.SupportSegmentIdsJson") or "[]"
            ),
            "supportDraftUpdatedUtc": (
                assemblyModel.GetAttribute("DENTOBOT.SupportDraftUpdatedUtc") or ""
            ),
            "trajectories": trajectories,
            "parametersJson": assemblyModel.GetAttribute("DENTOBOT.ParametersJson") or "",
            "frame": json.loads(assemblyModel.GetAttribute("DENTOBOT.FrameJson") or "{}"),
            "trajectoryGeometryJson": assemblyModel.GetAttribute("DENTOBOT.TrajectoryGeometryJson") or "",
            "metrics": json.loads(
                assemblyModel.GetAttribute("DENTOBOT.GeometryMetricsJson") or "{}"
            ),
            "orientationState": (
                assemblyModel.GetAttribute("DENTOBOT.OrientationState") or "Draft"
            ),
            "orientationConfirmedUtc": (
                assemblyModel.GetAttribute("DENTOBOT.OrientationConfirmedUtc") or ""
            ),
            "obstacleSegmentIds": json.loads(
                assemblyModel.GetAttribute("DENTOBOT.ObstacleSegmentIdsJson") or "[]"
            ),
            "omittedObstacleSegmentIds": json.loads(
                assemblyModel.GetAttribute("DENTOBOT.OmittedObstacleSegmentIdsJson")
                or "[]"
            ),
            "measurementNodes": measurementNodes,
            "updatedUtc": assemblyModel.GetAttribute("DENTOBOT.UpdatedUtc") or "",
            "pointCount": int(polyData.GetNumberOfPoints()),
            "cellCount": int(polyData.GetNumberOfCells()),
        }

    @staticmethod
    def markTargetDockingAssemblyStale(
        assemblyModel: vtkMRMLModelNode | None,
        reason: str,
    ) -> bool:
        if not DENTOWorkflowLogic.isTargetDockingAssemblyModelNode(assemblyModel):
            return False
        assemblyModel.SetAttribute("DENTOBOT.GeometryState", "Stale")
        assemblyModel.SetAttribute("DENTOBOT.OrientationState", "Draft")
        assemblyModel.SetAttribute("DENTOBOT.OrientationConfirmedUtc", None)
        planeNode = assemblyModel.GetNodeReference(
            "DENTOBOT.TargetDockingReferencePlane"
        )
        if planeNode:
            planeNode.SetAttribute("DENTOBOT.OrientationState", "Draft")
            planeNode.SetAttribute("DENTOBOT.OrientationConfirmedUtc", None)
        assemblyModel.SetAttribute(
            "DENTOBOT.StaleReason",
            str(reason).strip() or "Target trajectory or docking parameter changed.",
        )
        return True

    def deleteTargetDockingAssembly(
        self,
        assemblyModel: vtkMRMLModelNode,
    ) -> list[dict]:
        summary = self.getTargetDockingAssemblySummary(assemblyModel)
        parameterNode = self.getParameterNode()
        parameterNode.targetDockingAssemblyModel = None
        parameterNode.targetDockingReferencePlane = None
        parameterNode.targetDockingYawConfirmed = False
        removals = []
        measurementNodes = list(summary.get("measurementNodes") or [])
        assemblyModel.RemoveNodeReferenceIDs(
            self.TARGET_DOCKING_MEASUREMENT_REFERENCE_ROLE
        )
        for node in (*measurementNodes, assemblyModel, summary["plane"]):
            if node and slicer.mrmlScene.IsNodePresent(node):
                removals.append(self._removeSceneNodeAndOwnedAuxiliaries(node))
        return removals
