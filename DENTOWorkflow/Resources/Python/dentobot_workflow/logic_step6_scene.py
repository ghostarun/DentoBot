"""Extracted Step 6 case and phantom preparation methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


from dentobot_workflow.logic_phantom_scene import PhantomSceneLogicMixin


class Step6SceneLogicMixin(PhantomSceneLogicMixin):









































    def step6CaseJawSegmentIds(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> dict[str, tuple[str, ...]]:
        """Classify rigid upper and lower case surfaces from reviewed labels."""
        upper: list[str] = []
        lower: list[str] = []
        upperJaw: list[str] = []
        lowerJaw: list[str] = []
        for record in self.getSegmentationReviewRecords(segmentationNode):
            segmentId = str(record.get("segmentId") or "")
            if not segmentId:
                continue
            category = str(record.get("category") or "")
            if category == "Teeth":
                jaw = dental_jaw_from_fdi(record.get("fdiNumber"))
                if jaw == "upper":
                    upper.append(segmentId)
                elif jaw == "lower":
                    lower.append(segmentId)
                continue
            if category != "Jaws":
                continue
            sourceName = str(record.get("sourceName") or "").strip().lower()
            if "mandible" in sourceName or sourceName.startswith("lower_jaw"):
                lowerJaw.append(segmentId)
            elif "maxilla" in sourceName or sourceName.startswith("upper_jaw"):
                upperJaw.append(segmentId)
        return {
            "upperTeeth": tuple(upper),
            "lowerTeeth": tuple(lower),
            "upperJaw": tuple(upperJaw),
            "lowerJaw": tuple(lowerJaw),
            "upper": tuple(dict.fromkeys((*upper, *upperJaw))),
            "lower": tuple(dict.fromkeys((*lower, *lowerJaw))),
        }

    def _step6CaseJawGeometryFingerprint(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentIds: tuple[str, ...],
    ) -> str:
        segmentation = segmentationNode.GetSegmentation()
        if not segmentation:
            return ""
        representationName = (
            slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName()
        )
        records = []
        for segmentId in segmentIds:
            segment = segmentation.GetSegment(segmentId)
            polydata = (
                segment.GetRepresentation(representationName)
                if segment
                else None
            )
            if not polydata:
                records.append({"id": segmentId, "missing": True})
                continue
            bounds = polydata.GetBounds()
            records.append(
                {
                    "id": segmentId,
                    "points": int(polydata.GetNumberOfPoints()),
                    "cells": int(polydata.GetNumberOfCells()),
                    "bounds": tuple(round(float(value), 6) for value in bounds),
                }
            )
        parentMatrix = vtk.vtkMatrix4x4()
        parentMatrix.Identity()
        parent = segmentationNode.GetParentTransformNode()
        if parent:
            parent.GetMatrixTransformToWorld(parentMatrix)
        return fingerprint(
            {
                "segmentationId": str(segmentationNode.GetID() or ""),
                "parentToWorldRas": tuple(
                    round(float(parentMatrix.GetElement(row, column)), 9)
                    for row in range(4)
                    for column in range(4)
                ),
                "segments": records,
            }
        )

    def _step6CaseJawLandmarksFingerprint(
        self,
        landmarks: vtkMRMLMarkupsFiducialNode,
    ) -> str:
        positions = self.step6CaseJawLandmarkPositions(landmarks)
        return fingerprint(
            {
                "role": self.STEP6_CASE_JAW_LANDMARKS_ROLE,
                "pointsWorldRasMm": tuple(
                    tuple(round(float(value), 9) for value in point)
                    for point in positions
                ),
            }
        )

    def _step6TargetAttachedGeometryFingerprint(self, parameterNode) -> str:
        trajectory = self.getTrajectorySummary(parameterNode.trajectoryLine)
        modelSources = (
            [parameterNode.finalPrintableTemplateModel]
            if parameterNode.finalPrintableTemplateModel
            else [
                parameterNode.draftTemplateSupportModel,
                parameterNode.targetDockingAssemblyModel,
            ]
        )
        modelRecords = []
        for model in modelSources:
            if not model:
                continue
            polydata = model_polydata_in_world(model)
            bounds = polydata.GetBounds() if polydata else (0.0,) * 6
            modelRecords.append(
                {
                    "id": str(model.GetID() or ""),
                    "role": str(model.GetAttribute("DENTOBOT.ModelRole") or ""),
                    "points": int(polydata.GetNumberOfPoints()) if polydata else 0,
                    "cells": int(polydata.GetNumberOfCells()) if polydata else 0,
                    "boundsWorldRasMm": tuple(
                        round(float(value), 6) for value in bounds
                    ),
                }
            )
        return fingerprint(
            {
                "targetSegmentId": str(parameterNode.targetToothSegmentId or ""),
                "targetJaw": self.step6TargetJaw(parameterNode),
                "entryWorldRasMm": tuple(
                    round(float(value), 9)
                    for value in trajectory.get("entryRas", ())
                ),
                "targetWorldRasMm": tuple(
                    round(float(value), 9)
                    for value in trajectory.get("targetRas", ())
                ),
                "models": modelRecords,
            }
        )

    def step6TargetJaw(self, parameterNode) -> str:
        segmentation = parameterNode.teethSegmentation
        targetId = str(parameterNode.targetToothSegmentId or "")
        if not segmentation or not targetId:
            return ""
        for record in self.getTargetToothRecords(segmentation):
            if str(record.get("segmentId") or "") == targetId:
                return dental_jaw_from_fdi(record.get("fdiNumber")) or ""
        return ""

    def step6CaseJawOpeningFreshnessIssues(self, parameterNode) -> list[str]:
        """Return reasons the imported case is not in a current open-mouth pose."""
        if not bool(parameterNode.step6PlanningContextImported):
            return []
        segmentation = parameterNode.teethSegmentation
        if segmentation is None:
            return [_("The authoritative dental segmentation is missing.")]
        landmarks = parameterNode.step6CaseJawLandmarks
        if not self.isStep6CaseJawLandmarksNode(landmarks):
            return [_("Place the four Step 6 case jaw landmarks.")]
        try:
            summary = self.getStep6CaseJawLandmarkSummary(landmarks)
        except ValueError as exc:
            return [str(exc)]
        if not summary["isComplete"]:
            return [
                _("Place all four case landmarks: Left TMJ, Right TMJ, upper incisor, lower incisor.")
            ]
        transform = parameterNode.step6CaseJawTransform
        model = parameterNode.step6OpenedLowerJawModel
        if not self.isStep6CaseJawTransformNode(transform):
            return [_("Apply the Step 6 case open-mouth transform.")]
        if not self.isStep6OpenedLowerJawModelNode(model):
            return [_("The derived opened lower-jaw planning surface is missing.")]
        if transform.GetAttribute("DENTOBOT.GeometryState") != "Current":
            return [
                transform.GetAttribute("DENTOBOT.StaleReason")
                or _("Re-apply the Step 6 case open-mouth transform.")
            ]
        if transform.GetParentTransformNode() is not None:
            return [_("The case TMJ transform must remain in world RAS.")]
        left, right, upper, lower = self.step6CaseJawLandmarkPositions(landmarks)
        _angle, expectedMatrix, _openedLower, _gap = solve_hinge_rotation_for_gap(
            left,
            right,
            upper,
            lower,
            float(parameterNode.step6CaseJawTargetGapMm),
        )
        actualVtk = vtk.vtkMatrix4x4()
        transform.GetMatrixTransformToWorld(actualVtk)
        actualMatrix = self._numpyFromVtkMatrix(actualVtk)
        if not np.allclose(actualMatrix, expectedMatrix, atol=1e-6, rtol=0.0):
            return [
                _("The case TMJ transform matrix changed; re-apply the mouth opening.")
            ]
        if model.GetParentTransformNode() is not transform:
            return [_("The opened lower-jaw surface is detached from its TMJ transform.")]
        if self.step6TargetJaw(parameterNode) == "lower":
            if not self.isStep6OpenedTrajectoryNode(
                parameterNode.step6OpenedTrajectoryLine
            ):
                return [_("The opened mandibular Entry-to-Target display is missing.")]
            if parameterNode.finalPrintableTemplateModel and not (
                self.isStep6OpenedTargetGeometryModelNode(
                    parameterNode.step6OpenedTargetGeometryModel
                )
            ):
                return [_("The opened mandibular template display is missing.")]
        sourceId = transform.GetNodeReferenceID("DENTOBOT.SourceSegmentation")
        if sourceId != segmentation.GetID():
            return [_("The open-mouth transform belongs to a different segmentation.")]
        if (
            transform.GetAttribute("DENTOBOT.LandmarksFingerprint")
            != self._step6CaseJawLandmarksFingerprint(landmarks)
        ):
            return [
                _("Case jaw landmarks changed; re-apply the mouth opening.")
            ]
        if transform.GetAttribute("DENTOBOT.TargetSegmentID") != str(
            parameterNode.targetToothSegmentId or ""
        ):
            return [
                _("The selected target changed; re-apply the case mouth opening.")
            ]
        if (
            transform.GetAttribute("DENTOBOT.TargetAttachedGeometryFingerprint")
            != self._step6TargetAttachedGeometryFingerprint(parameterNode)
        ):
            return [
                _("Target trajectory or guide geometry changed; re-apply the mouth opening.")
            ]
        segmentGroups = self.step6CaseJawSegmentIds(segmentation)
        lowerIds = segmentGroups["lower"]
        if not lowerIds:
            return [_("No lower-jaw or mandibular tooth surfaces are available.")]
        expectedFingerprint = self._step6CaseJawGeometryFingerprint(
            segmentation,
            lowerIds,
        )
        if transform.GetAttribute("DENTOBOT.SourceGeometryFingerprint") != expectedFingerprint:
            return [
                _("Lower-jaw segmentation geometry changed; re-apply the mouth opening.")
            ]
        if model.GetAttribute("DENTOBOT.SourceGeometryFingerprint") != expectedFingerprint:
            return [
                _("The opened lower-jaw surface provenance is stale.")
            ]
        requestedGap = float(parameterNode.step6CaseJawTargetGapMm)
        recordedGap = transform.GetAttribute("DENTOBOT.TargetIncisorGapMm")
        try:
            gapMatches = (
                recordedGap is not None
                and abs(float(recordedGap) - requestedGap) <= 1e-6
            )
        except (TypeError, ValueError):
            gapMatches = False
        if not gapMatches:
            return [_("The requested incisor gap changed; re-apply the mouth opening.")]
        return []

    def _restoreStep6CaseLowerJawVisibility(
        self,
        segmentationNode: vtkMRMLSegmentationNode | None,
        model: vtkMRMLModelNode | None,
    ) -> None:
        if not segmentationNode or not model:
            return
        display = segmentationNode.GetDisplayNode()
        if not display:
            return
        try:
            states = json.loads(
                model.GetAttribute("DENTOBOT.SourceSegmentVisibility3DJson") or "{}"
            )
        except (TypeError, json.JSONDecodeError):
            states = {}
        for segmentId, visible in states.items():
            if segmentationNode.GetSegmentation().GetSegment(str(segmentId)):
                display.SetSegmentVisibility3D(str(segmentId), bool(visible))

    def _restoreStep6CaseTargetAttachedVisibility(self, parameterNode) -> None:
        modelProxy = parameterNode.step6OpenedTargetGeometryModel
        if modelProxy:
            try:
                states = json.loads(
                    modelProxy.GetAttribute("DENTOBOT.SourceDisplayVisibilityJson")
                    or "{}"
                )
            except (TypeError, json.JSONDecodeError):
                states = {}
            for nodeId, visible in states.items():
                node = slicer.mrmlScene.GetNodeByID(str(nodeId))
                display = node.GetDisplayNode() if node else None
                if display:
                    display.SetVisibility(bool(visible))
        trajectoryProxy = parameterNode.step6OpenedTrajectoryLine
        if trajectoryProxy:
            try:
                state = json.loads(
                    trajectoryProxy.GetAttribute("DENTOBOT.SourceDisplayVisibilityJson")
                    or "{}"
                )
            except (TypeError, json.JSONDecodeError):
                state = {}
            source = parameterNode.trajectoryLine
            display = source.GetDisplayNode() if source else None
            if display:
                display.SetVisibility(bool(state.get("visible", True)))
                display.SetVisibility2D(bool(state.get("visible2D", True)))
                display.SetVisibility3D(bool(state.get("visible3D", True)))

    def _updateStep6CaseTargetAttachedDisplay(
        self,
        parameterNode,
        transform: vtkMRMLLinearTransformNode,
    ) -> None:
        """Create derived display proxies without moving Steps 0–5 source nodes."""
        if self.step6TargetJaw(parameterNode) != "lower":
            self._restoreStep6CaseTargetAttachedVisibility(parameterNode)
            for node in (
                parameterNode.step6OpenedTargetGeometryModel,
                parameterNode.step6OpenedTrajectoryLine,
            ):
                if node and slicer.mrmlScene.IsNodePresent(node):
                    slicer.mrmlScene.RemoveNode(node)
            parameterNode.step6OpenedTargetGeometryModel = None
            parameterNode.step6OpenedTrajectoryLine = None
            return

        modelSources = (
            [parameterNode.finalPrintableTemplateModel]
            if parameterNode.finalPrintableTemplateModel
            else [
                parameterNode.draftTemplateSupportModel,
                parameterNode.targetDockingAssemblyModel,
            ]
        )
        modelSources = [node for node in modelSources if node is not None]
        surfaces = [model_polydata_in_world(node) for node in modelSources]
        combined = self._appendPolydata(surfaces)
        if combined is not None:
            proxy = parameterNode.step6OpenedTargetGeometryModel
            if proxy and not self.isStep6OpenedTargetGeometryModelNode(proxy):
                raise ValueError(_("Select the Step 6 opened target-geometry model."))
            proxy = proxy or slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
                "[Step 6.0A] Opened Target-Attached Geometry",
            )
            proxy.SetName("[Step 6.0A] Opened Target-Attached Geometry")
            proxy.SetAttribute(
                "DENTOBOT.ModelRole",
                self.STEP6_OPENED_TARGET_GEOMETRY_MODEL_ROLE,
            )
            proxy.SetAttribute("DENTOBOT.GeometryState", "Current")
            try:
                visibility = json.loads(
                    proxy.GetAttribute("DENTOBOT.SourceDisplayVisibilityJson")
                    or "{}"
                )
            except (TypeError, json.JSONDecodeError):
                visibility = {}
            for source in modelSources:
                sourceDisplay = source.GetDisplayNode()
                if sourceDisplay and source.GetID() not in visibility:
                    visibility[source.GetID()] = bool(sourceDisplay.GetVisibility())
                if sourceDisplay:
                    sourceDisplay.SetVisibility(False)
            proxy.SetAttribute(
                "DENTOBOT.SourceDisplayVisibilityJson",
                canonical_json(visibility),
            )
            proxy.SetAndObservePolyData(combined)
            proxy.SetAndObserveTransformNodeID(transform.GetID())
            proxy.SetSelectable(False)
            proxy.CreateDefaultDisplayNodes()
            proxyDisplay = proxy.GetDisplayNode()
            if proxyDisplay:
                proxyDisplay.SetVisibility(True)
                proxyDisplay.SetVisibility2D(False)
                proxyDisplay.SetVisibility3D(True)
                proxyDisplay.SetColor(0.95, 0.76, 0.18)
                proxyDisplay.SetOpacity(float(parameterNode.step6GuidesOpacity))
            parameterNode.step6OpenedTargetGeometryModel = proxy

        trajectory = parameterNode.trajectoryLine
        summary = self.getTrajectorySummary(trajectory) if trajectory else {}
        if summary.get("isValid"):
            proxyLine = parameterNode.step6OpenedTrajectoryLine
            if proxyLine and not self.isStep6OpenedTrajectoryNode(proxyLine):
                raise ValueError(_("Select the Step 6 opened trajectory line."))
            proxyLine = proxyLine or slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsLineNode",
                "[Step 6.0A] Opened Entry-to-Target",
            )
            proxyLine.SetName("[Step 6.0A] Opened Entry-to-Target")
            proxyLine.SetAttribute(
                "DENTOBOT.MarkupsRole",
                self.STEP6_OPENED_TRAJECTORY_ROLE,
            )
            proxyLine.SetAttribute("DENTOBOT.GeometryState", "Current")
            sourceDisplay = trajectory.GetDisplayNode()
            if not proxyLine.GetAttribute("DENTOBOT.SourceDisplayVisibilityJson"):
                proxyLine.SetAttribute(
                    "DENTOBOT.SourceDisplayVisibilityJson",
                    canonical_json(
                        {
                            "visible": bool(sourceDisplay.GetVisibility())
                            if sourceDisplay
                            else True,
                            "visible2D": bool(sourceDisplay.GetVisibility2D())
                            if sourceDisplay
                            else True,
                            "visible3D": bool(sourceDisplay.GetVisibility3D())
                            if sourceDisplay
                            else True,
                        }
                    ),
                )
            if sourceDisplay:
                sourceDisplay.SetVisibility(False)
            proxyLine.SetAndObserveTransformNodeID(None)
            proxyLine.RemoveAllControlPoints()
            proxyLine.AddControlPointWorld(vtk.vtkVector3d(*summary["entryRas"]))
            proxyLine.AddControlPointWorld(vtk.vtkVector3d(*summary["targetRas"]))
            proxyLine.SetNthControlPointLabel(0, "Entry")
            proxyLine.SetNthControlPointLabel(1, "Target")
            proxyLine.SetLocked(True)
            proxyLine.SetAndObserveTransformNodeID(transform.GetID())
            proxyLine.CreateDefaultDisplayNodes()
            proxyDisplay = proxyLine.GetDisplayNode()
            if proxyDisplay:
                proxyDisplay.SetVisibility(True)
                proxyDisplay.SetVisibility2D(True)
                proxyDisplay.SetVisibility3D(True)
                proxyDisplay.SetColor(1.0, 0.25, 0.15)
                proxyDisplay.SetSelectedColor(1.0, 0.85, 0.15)
                proxyDisplay.SetLineThickness(0.5)
            parameterNode.step6OpenedTrajectoryLine = proxyLine

    def createOrUpdateStep6CaseJawOpening(
        self,
        parameterNode,
    ) -> tuple[vtkMRMLLinearTransformNode, vtkMRMLModelNode, vtkMRMLMarkupsLineNode, dict]:
        if not bool(parameterNode.step6PlanningContextImported):
            raise ValueError(_("Import the Steps 0–5 planning package first."))
        if bool(parameterNode.robotBaseMountLocked) or self.isRos2MotionControlActive(
            parameterNode.robotBaseTransform
        ):
            raise ValueError(
                _("Disconnect ROS and unlock the robot base before changing the case jaw pose.")
            )
        segmentation = parameterNode.teethSegmentation
        if segmentation is None:
            raise ValueError(_("The imported case has no authoritative dental segmentation."))
        lowerIds = self.step6CaseJawSegmentIds(segmentation)["lower"]
        if not lowerIds:
            raise ValueError(
                _("The imported segmentation has no mandibular jaw or lower-tooth surfaces.")
            )
        left, right, upper, lower = self.step6CaseJawLandmarkPositions(
            parameterNode.step6CaseJawLandmarks
        )
        angle, matrix, openedLower, gap = solve_hinge_rotation_for_gap(
            left,
            right,
            upper,
            lower,
            float(parameterNode.step6CaseJawTargetGapMm),
        )
        sourceSurface = self._segmentationSegmentsSurfaceWorld(
            segmentation,
            set(lowerIds),
        )
        if sourceSurface is None or sourceSurface.GetNumberOfPoints() == 0:
            raise ValueError(_("Could not build the lower-jaw closed surface."))
        sourceFingerprint = self._step6CaseJawGeometryFingerprint(
            segmentation,
            lowerIds,
        )

        transform = parameterNode.step6CaseJawTransform
        if transform and not self.isStep6CaseJawTransformNode(transform):
            raise ValueError(_("Select the Step 6 case jaw transform."))
        transform = transform or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLinearTransformNode",
            "[Step 6.0A] Case TMJ Mouth Opening",
        )
        transform.SetName("[Step 6.0A] Case TMJ Mouth Opening")
        transform.SetAttribute("DENTOBOT.TransformRole", self.STEP6_CASE_JAW_TRANSFORM_ROLE)
        transform.SetAttribute("DENTOBOT.SchemaVersion", self.STEP6_CASE_JAW_SCHEMA_VERSION)
        transform.SetAttribute("DENTOBOT.GeometryState", "Current")
        transform.SetAttribute("DENTOBOT.StaleReason", None)
        transform.SetAttribute("DENTOBOT.JawMotion", "PureTMJHingeRotation")
        transform.SetAttribute(
            "DENTOBOT.TargetIncisorGapMm",
            f"{float(parameterNode.step6CaseJawTargetGapMm):.6f}",
        )
        transform.SetAttribute("DENTOBOT.AchievedIncisorGapMm", f"{gap:.6f}")
        transform.SetAttribute("DENTOBOT.HingeAngleDeg", f"{angle:.6f}")
        transform.SetAttribute("DENTOBOT.SourceGeometryFingerprint", sourceFingerprint)
        transform.SetAttribute(
            "DENTOBOT.LandmarksFingerprint",
            self._step6CaseJawLandmarksFingerprint(
                parameterNode.step6CaseJawLandmarks
            ),
        )
        transform.SetAttribute(
            "DENTOBOT.TargetSegmentID",
            str(parameterNode.targetToothSegmentId or ""),
        )
        transform.SetAttribute(
            "DENTOBOT.TargetAttachedGeometryFingerprint",
            self._step6TargetAttachedGeometryFingerprint(parameterNode),
        )
        transform.SetAttribute("DENTOBOT.MovingSegmentIdsJson", canonical_json(lowerIds))
        transform.SetNodeReferenceID(
            "DENTOBOT.SourceSegmentation",
            segmentation.GetID(),
        )
        transform.SetAndObserveTransformNodeID(None)
        transform.SetMatrixTransformToParent(self._vtkFromNumpyMatrix(matrix))

        model = parameterNode.step6OpenedLowerJawModel
        if model and not self.isStep6OpenedLowerJawModelNode(model):
            raise ValueError(_("Select the Step 6 opened lower-jaw model."))
        model = model or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "[Step 6.0A] Opened Lower Jaw Planning Surface",
        )
        model.SetName("[Step 6.0A] Opened Lower Jaw Planning Surface")
        model.SetAttribute("DENTOBOT.ModelRole", self.STEP6_OPENED_LOWER_JAW_MODEL_ROLE)
        model.SetAttribute("DENTOBOT.SchemaVersion", self.STEP6_CASE_JAW_SCHEMA_VERSION)
        model.SetAttribute("DENTOBOT.GeometryState", "Current")
        model.SetAttribute("DENTOBOT.SourceGeometryFingerprint", sourceFingerprint)
        model.SetAttribute("DENTOBOT.MovingSegmentIdsJson", canonical_json(lowerIds))
        display = segmentation.GetDisplayNode()
        if display:
            try:
                visibility = json.loads(
                    model.GetAttribute("DENTOBOT.SourceSegmentVisibility3DJson")
                    or "{}"
                )
            except (TypeError, json.JSONDecodeError):
                visibility = {}
            for segmentId in lowerIds:
                if segmentId not in visibility:
                    visibility[segmentId] = bool(
                        display.GetSegmentVisibility3D(segmentId)
                    )
            model.SetAttribute(
                "DENTOBOT.SourceSegmentVisibility3DJson",
                canonical_json(visibility),
            )
        model.SetAndObservePolyData(sourceSurface)
        model.SetAndObserveTransformNodeID(transform.GetID())
        model.SetSelectable(False)
        model.CreateDefaultDisplayNodes()
        modelDisplay = model.GetDisplayNode()
        if modelDisplay:
            modelDisplay.SetVisibility(True)
            modelDisplay.SetVisibility2D(False)
            modelDisplay.SetVisibility3D(True)
            modelDisplay.SetColor(0.90, 0.74, 0.56)
            modelDisplay.SetOpacity(float(parameterNode.step6MasksOpacity))
        if display:
            for segmentId in lowerIds:
                display.SetSegmentVisibility3D(segmentId, False)

        gapLine = parameterNode.step6CaseJawGapLine
        if gapLine and (
            not gapLine.IsA("vtkMRMLMarkupsLineNode")
            or gapLine.GetAttribute("DENTOBOT.MarkupsRole")
            != self.STEP6_CASE_JAW_GAP_LINE_ROLE
        ):
            raise ValueError(_("Select the Step 6 case incisor-gap line."))
        gapLine = gapLine or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsLineNode",
            "[Step 6.0A] Case Incisor Gap",
        )
        gapLine.SetName("[Step 6.0A] Case Incisor Gap")
        gapLine.RemoveAllControlPoints()
        gapLine.AddControlPointWorld(vtk.vtkVector3d(*upper))
        gapLine.AddControlPointWorld(vtk.vtkVector3d(*openedLower))
        gapLine.SetNthControlPointLabel(0, "Upper incisor")
        gapLine.SetNthControlPointLabel(1, "Opened lower incisor")
        gapLine.SetLocked(True)
        gapLine.SetSelectable(False)
        gapLine.SetAttribute("DENTOBOT.MarkupsRole", self.STEP6_CASE_JAW_GAP_LINE_ROLE)
        gapLine.SetAttribute("DENTOBOT.SchemaVersion", self.STEP6_CASE_JAW_SCHEMA_VERSION)
        gapLine.CreateDefaultDisplayNodes()
        gapDisplay = gapLine.GetDisplayNode()
        if gapDisplay:
            gapDisplay.SetVisibility(True)
            gapDisplay.SetVisibility2D(True)
            gapDisplay.SetVisibility3D(True)
            gapDisplay.SetColor(0.15, 1.0, 0.25)
            gapDisplay.SetPointLabelsVisibility(True)
            gapDisplay.SetPropertiesLabelVisibility(True)

        parameterNode.step6CaseJawTransform = transform
        parameterNode.step6OpenedLowerJawModel = model
        parameterNode.step6CaseJawGapLine = gapLine
        self._updateStep6CaseTargetAttachedDisplay(parameterNode, transform)
        self.invalidateStep6TaskConfirmation(
            parameterNode,
            _("Case jaw opening changed."),
            makeBaseStale=True,
        )
        self.deleteRobotWorkspaceModel()
        return transform, model, gapLine, {
            "angleDeg": angle,
            "gapMm": gap,
            "openedLowerIncisorRas": openedLower,
            "movingSegmentCount": len(lowerIds),
        }

    def resetStep6CaseJawOpening(self, parameterNode) -> None:
        if bool(parameterNode.robotBaseMountLocked) or self.isRos2MotionControlActive(
            parameterNode.robotBaseTransform
        ):
            raise ValueError(
                _("Disconnect ROS and unlock the robot base before resetting the case jaw.")
            )
        model = parameterNode.step6OpenedLowerJawModel
        transform = parameterNode.step6CaseJawTransform
        gapLine = parameterNode.step6CaseJawGapLine
        self._restoreStep6CaseLowerJawVisibility(
            parameterNode.teethSegmentation,
            model,
        )
        self._restoreStep6CaseTargetAttachedVisibility(parameterNode)
        for node in (
            parameterNode.step6OpenedTrajectoryLine,
            parameterNode.step6OpenedTargetGeometryModel,
            gapLine,
            model,
            transform,
        ):
            if node and slicer.mrmlScene.IsNodePresent(node):
                slicer.mrmlScene.RemoveNode(node)
        parameterNode.step6OpenedTrajectoryLine = None
        parameterNode.step6OpenedTargetGeometryModel = None
        parameterNode.step6CaseJawTransform = None
        parameterNode.step6OpenedLowerJawModel = None
        parameterNode.step6CaseJawGapLine = None
        self.invalidateStep6TaskConfirmation(
            parameterNode,
            _("Case jaw opening was reset."),
            makeBaseStale=True,
        )
        self.deleteRobotWorkspaceModel()

    def deleteDraftPhantom(
        self,
        landmarks=None,
        transform=None,
        gapLine=None,
    ) -> list[str]:
        nodes = [
            *self.draftPhantomModelNodes(),
            *self.draftPhantomWorkspaceTransformNodes(),
            landmarks,
            transform,
            gapLine,
        ]
        removed = []
        for node in dict.fromkeys(node for node in nodes if node):
            if slicer.mrmlScene.IsNodePresent(node):
                removed.append(node.GetName())
                slicer.mrmlScene.RemoveNode(node)
        return removed
