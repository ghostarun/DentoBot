"""Extracted Step 6 case and phantom preparation methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


from dentobot_workflow.logic_phantom_scene import PhantomSceneLogicMixin
from dentobot_workflow.logic_step6_landmark_review import (
    cancel_transient_step6_case_jaw_landmark_placement,
    review_and_project_existing_step6_case_jaw_landmarks,
)


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

    @staticmethod
    def _step6CaseJawPreparationRecord(parameterNode) -> dict:
        try:
            record = json.loads(
                str(parameterNode.step6CaseJawPreparationJson or "") or "{}"
            )
        except (TypeError, json.JSONDecodeError):
            return {}
        return record if isinstance(record, dict) else {}

    @classmethod
    def isStep6DerivedAnatomyNode(cls, node, role: str) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLSegmentationNode")
            and node.GetAttribute("DENTOBOT.SegmentationRole") == role
        )

    def _createStep6DerivedAnatomy(
        self,
        parameterNode,
        sourceNode: vtkMRMLSegmentationNode,
        segmentIds: tuple[str, ...],
        *,
        existingNode,
        name: str,
        role: str,
        mode: str,
        transformNode=None,
    ) -> vtkMRMLSegmentationNode:
        """Create a world-RAS, closed-surface-only proxy without resampling masks."""
        if existingNode and not self.isStep6DerivedAnatomyNode(existingNode, role):
            raise ValueError(_("A Step 6 derived-anatomy reference has the wrong role."))
        node = existingNode or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode", name
        )
        node.SetName(name)
        node.SetAttribute("DENTOBOT.SegmentationRole", role)
        node.SetAttribute("DENTOBOT.SchemaVersion", self.STEP6_CASE_JAW_SCHEMA_VERSION)
        node.SetAttribute("DENTOBOT.GeometryState", "Current")
        node.SetAttribute("DENTOBOT.PreparationMode", mode)
        node.SetAttribute("DENTOBOT.IntendedUse", "SimulationPlanningProxy")
        node.SetAttribute("DENTOBOT.SourceSegmentIdsJson", canonical_json(segmentIds))
        sourceFingerprint = self._step6CaseJawGeometryFingerprint(sourceNode, segmentIds)
        node.SetAttribute("DENTOBOT.SourceGeometryFingerprint", sourceFingerprint)
        node.SetNodeReferenceID("DENTOBOT.SourceSegmentation", sourceNode.GetID())
        node.SetAndObserveTransformNodeID(None)

        representationName = (
            slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName()
        )
        targetSegmentation = node.GetSegmentation()
        targetSegmentation.RemoveAllSegments()
        targetSegmentation.SetSourceRepresentationName(representationName)
        recordsById = {
            str(record.get("segmentId") or ""): record
            for record in self.getSegmentationReviewRecords(sourceNode)
        }
        for segmentId in segmentIds:
            sourceSegment = sourceNode.GetSegmentation().GetSegment(segmentId)
            worldSurface = self._segmentationSegmentsSurfaceWorld(
                sourceNode, {segmentId}
            )
            if (
                sourceSegment is None
                or worldSurface is None
                or worldSurface.GetNumberOfPoints() == 0
            ):
                raise ValueError(
                    _("Could not derive the reviewed anatomy segment %1.").replace(
                        "%1", str(segmentId)
                    )
                )
            copiedSurface = vtk.vtkPolyData()
            copiedSurface.DeepCopy(worldSurface)
            segment = slicer.vtkSegment()
            segment.SetName(sourceSegment.GetName())
            try:
                segment.SetColor(sourceSegment.GetColor())
            except TypeError:
                color = [0.7, 0.7, 0.7]
                sourceSegment.GetColor(color)
                segment.SetColor(*color)
            segment.SetTag("DENTOBOT.SourceSegmentID", str(segmentId))
            review = recordsById.get(str(segmentId), {})
            for tag, key in (
                ("DENTOBOT.FDINumber", "fdiNumber"),
                ("DENTOBOT.Category", "category"),
                ("DENTOBOT.SourceName", "sourceName"),
            ):
                value = review.get(key)
                if value not in (None, ""):
                    segment.SetTag(tag, str(value))
            segment.AddRepresentation(representationName, copiedSurface)
            targetSegmentation.AddSegment(segment, str(segmentId))

        node.SetAndObserveTransformNodeID(
            transformNode.GetID() if transformNode else None
        )
        node.CreateDefaultDisplayNodes()
        display = node.GetDisplayNode()
        if display:
            display.SetVisibility(True)
            display.SetVisibility2D(False)
            display.SetVisibility3D(True)
            display.SetOpacity3D(float(parameterNode.step6MasksOpacity))
            display.SetAllSegmentsVisibility(True)
        return node

    def _hideStep6SourceJawSegments(
        self,
        sourceNode: vtkMRMLSegmentationNode,
        ownerNode: vtkMRMLSegmentationNode,
        segmentIds: tuple[str, ...],
    ) -> None:
        display = sourceNode.GetDisplayNode()
        if not display:
            return
        try:
            visibility = json.loads(
                ownerNode.GetAttribute("DENTOBOT.SourceSegmentVisibility3DJson")
                or "{}"
            )
        except (TypeError, json.JSONDecodeError):
            visibility = {}
        for segmentId in segmentIds:
            if segmentId not in visibility:
                visibility[segmentId] = bool(display.GetSegmentVisibility3D(segmentId))
            display.SetSegmentVisibility3D(segmentId, False)
        ownerNode.SetAttribute(
            "DENTOBOT.SourceSegmentVisibility3DJson", canonical_json(visibility)
        )

    def _restoreStep6DerivedAnatomyVisibility(self, parameterNode) -> None:
        sourceNode = parameterNode.teethSegmentation
        display = sourceNode.GetDisplayNode() if sourceNode else None
        if not display:
            return
        for owner in (
            parameterNode.step6FixedUpperAnatomy,
            parameterNode.step6MovingLowerAnatomy,
            parameterNode.step6TargetJawFallbackAnatomy,
        ):
            if not owner:
                continue
            try:
                visibility = json.loads(
                    owner.GetAttribute("DENTOBOT.SourceSegmentVisibility3DJson")
                    or "{}"
                )
            except (TypeError, json.JSONDecodeError):
                visibility = {}
            for segmentId, visible in visibility.items():
                if sourceNode.GetSegmentation().GetSegment(str(segmentId)):
                    display.SetSegmentVisibility3D(str(segmentId), bool(visible))

    def step6CaseJawLandmarkSegmentAssociations(self, parameterNode) -> tuple[str, ...]:
        """Resolve the four landmark surfaces from reviewed segment metadata."""
        segmentation = parameterNode.teethSegmentation
        if segmentation is None:
            raise ValueError(_("The authoritative dental segmentation is missing."))
        groups = self.step6CaseJawSegmentIds(segmentation)
        if len(groups["lowerJaw"]) != 1:
            raise ValueError(
                _(
                    "Exactly one reviewed lower-jawbone segment is required for "
                    "the bilateral condylar landmarks."
                )
            )
        targetFdi = None
        targetId = str(parameterNode.targetToothSegmentId or "")
        records = self.getSegmentationReviewRecords(segmentation)
        for record in records:
            if str(record.get("segmentId") or "") == targetId:
                try:
                    targetFdi = int(record.get("fdiNumber"))
                except (TypeError, ValueError):
                    targetFdi = None
                break
        targetQuadrant = targetFdi // 10 if targetFdi else 0
        preferredUpper = 11 if targetQuadrant in {1, 4} else 21
        preferredLower = 41 if targetQuadrant in {1, 4} else 31

        teethByFdi: dict[int, str] = {}
        for record in records:
            if str(record.get("category") or "") != "Teeth":
                continue
            try:
                fdi = int(record.get("fdiNumber"))
            except (TypeError, ValueError):
                continue
            segmentId = str(record.get("segmentId") or "")
            if segmentId:
                teethByFdi[fdi] = segmentId

        def central(preferred: int, alternatives: tuple[int, int], jawName: str) -> str:
            if preferred in teethByFdi:
                return teethByFdi[preferred]
            available = [teethByFdi[fdi] for fdi in alternatives if fdi in teethByFdi]
            if len(available) == 1:
                return available[0]
            if not available:
                raise ValueError(
                    _(
                        "No reviewed %1 central-incisor surface is available for "
                        "the incisal landmark."
                    ).replace("%1", jawName)
                )
            raise ValueError(
                _(
                    "The %1 central-incisor landmark surface is ambiguous for "
                    "the selected target side."
                ).replace("%1", jawName)
            )

        lowerJaw = groups["lowerJaw"][0]
        return (
            lowerJaw,
            lowerJaw,
            central(preferredUpper, (11, 21), _("upper")),
            central(preferredLower, (31, 41), _("lower")),
        )

    def prepareStep6CaseJawLandmarkPlacement(
        self,
        parameterNode,
        landmarksNode: vtkMRMLMarkupsFiducialNode,
        landmarkIndex: int,
    ) -> str:
        associations = self.step6CaseJawLandmarkSegmentAssociations(parameterNode)
        if landmarkIndex < 0 or landmarkIndex >= len(associations):
            raise ValueError(_("All four case jaw landmarks are already placed."))
        segmentation = parameterNode.teethSegmentation
        display = segmentation.GetDisplayNode() if segmentation else None
        if display is None:
            raise ValueError(_("The dental segmentation display is unavailable."))
        segmentIds = tuple(self.step6CaseJawSegmentIds(segmentation)["upper"])
        segmentIds += tuple(self.step6CaseJawSegmentIds(segmentation)["lower"])
        visibility = {
            segmentId: bool(display.GetSegmentVisibility3D(segmentId))
            for segmentId in segmentIds
        }
        landmarksNode.SetAttribute(
            "DENTOBOT.PlacementVisibilitySnapshotJson",
            canonical_json(visibility),
        )
        expectedId = associations[landmarkIndex]
        for segmentId in segmentIds:
            display.SetSegmentVisibility3D(segmentId, segmentId == expectedId)
        landmarksNode.SetAttribute("DENTOBOT.PendingLandmarkIndex", str(landmarkIndex))
        landmarksNode.SetAttribute("DENTOBOT.PendingSourceSegmentID", expectedId)
        landmarksNode.CreateDefaultDisplayNodes()
        markupsDisplay = landmarksNode.GetDisplayNode()
        if markupsDisplay:
            markupsDisplay.SetSnapMode(markupsDisplay.SnapModeToVisibleSurface)
        self.startStep6CaseJawLandmarkPlacement(landmarksNode)
        return expectedId

    def _restoreStep6CaseJawLandmarkPlacementVisibility(
        self,
        parameterNode,
        landmarksNode,
    ) -> None:
        segmentation = parameterNode.teethSegmentation
        display = segmentation.GetDisplayNode() if segmentation else None
        if display:
            try:
                visibility = json.loads(
                    landmarksNode.GetAttribute(
                        "DENTOBOT.PlacementVisibilitySnapshotJson"
                    )
                    or "{}"
                )
            except (TypeError, json.JSONDecodeError):
                visibility = {}
            for segmentId, visible in visibility.items():
                if segmentation.GetSegmentation().GetSegment(str(segmentId)):
                    display.SetSegmentVisibility3D(str(segmentId), bool(visible))
        landmarksNode.SetAttribute("DENTOBOT.PlacementVisibilitySnapshotJson", None)

    def finalizeStep6CaseJawLandmarkPlacement(
        self,
        parameterNode,
        landmarksNode: vtkMRMLMarkupsFiducialNode,
    ) -> dict | None:
        pending = landmarksNode.GetAttribute("DENTOBOT.PendingLandmarkIndex")
        if pending in (None, ""):
            return None
        try:
            landmarkIndex = int(pending)
        except (TypeError, ValueError):
            return None
        if landmarksNode.GetNumberOfDefinedControlPoints() <= landmarkIndex:
            return None
        segmentId = str(
            landmarksNode.GetAttribute("DENTOBOT.PendingSourceSegmentID") or ""
        )
        segmentation = parameterNode.teethSegmentation
        surface = self._segmentationSegmentsSurfaceWorld(
            segmentation,
            {segmentId},
        ) if segmentation else None
        if surface is None or surface.GetNumberOfPoints() == 0:
            self._restoreStep6CaseJawLandmarkPlacementVisibility(
                parameterNode, landmarksNode
            )
            raise ValueError(_("The intended landmark surface is unavailable."))
        point = [0.0, 0.0, 0.0]
        landmarksNode.GetNthControlPointPositionWorld(landmarkIndex, point)
        locator = vtk.vtkStaticCellLocator()
        locator.SetDataSet(surface)
        locator.BuildLocator()
        closest = [0.0, 0.0, 0.0]
        cellId = vtk.reference(0)
        subId = vtk.reference(0)
        distanceSquared = vtk.reference(0.0)
        locator.FindClosestPoint(point, closest, cellId, subId, distanceSquared)
        residual = math.sqrt(max(0.0, float(distanceSquared)))
        if residual > 5.0:
            landmarksNode.RemoveNthControlPoint(landmarkIndex)
            self._restoreStep6CaseJawLandmarkPlacementVisibility(
                parameterNode, landmarksNode
            )
            raise ValueError(
                _(
                    "The landmark was more than 5 mm from its intended visible "
                    "surface and was rejected."
                )
            )
        landmarksNode.SetNthControlPointPositionWorld(
            landmarkIndex,
            vtk.vtkVector3d(*closest),
        )
        try:
            evidence = json.loads(
                landmarksNode.GetAttribute("DENTOBOT.SurfaceEvidenceJson") or "[]"
            )
        except (TypeError, json.JSONDecodeError):
            evidence = []
        evidence = [
            item
            for item in evidence
            if int(item.get("landmarkIndex", -1)) != landmarkIndex
        ]
        evidence.append(
            {
                "landmarkIndex": landmarkIndex,
                "label": self.DRAFT_JAW_LANDMARK_LABELS[landmarkIndex],
                "sourceSegmentId": segmentId,
                "sourceGeometryFingerprint": self._step6CaseJawGeometryFingerprint(
                    segmentation, (segmentId,)
                ),
                "placementMethod": "VisibleSurfaceSnapThenExactSourceProjection",
                "projectionResidualMm": residual,
                "pointWorldRasMm": [float(value) for value in closest],
                "mprReviewState": "Pending",
            }
        )
        evidence.sort(key=lambda item: int(item["landmarkIndex"]))
        landmarksNode.SetAttribute("DENTOBOT.SurfaceEvidenceJson", canonical_json(evidence))
        landmarksNode.SetAttribute("DENTOBOT.PendingLandmarkIndex", None)
        landmarksNode.SetAttribute("DENTOBOT.PendingSourceSegmentID", None)
        self._restoreStep6CaseJawLandmarkPlacementVisibility(
            parameterNode, landmarksNode
        )
        return evidence[-1]

    def reviewAndProjectExistingStep6CaseJawLandmarks(
        self,
        parameterNode,
        landmarksNode: vtkMRMLMarkupsFiducialNode,
        maximumResidualMm: float = 5.0,
    ) -> dict:
        return review_and_project_existing_step6_case_jaw_landmarks(
            self,
            parameterNode,
            landmarksNode,
            maximumResidualMm,
        )

    def cancelTransientStep6CaseJawLandmarkPlacement(
        self,
        parameterNode,
    ) -> dict:
        return cancel_transient_step6_case_jaw_landmark_placement(
            self,
            parameterNode,
        )

    def step6CaseJawSurfaceEvidenceIssues(self, parameterNode) -> list[str]:
        """Return source-surface provenance issues without judging anatomy."""
        landmarks = parameterNode.step6CaseJawLandmarks
        if not self.isStep6CaseJawLandmarksNode(landmarks):
            return [_('Place the four Step 6 case jaw landmarks.')]
        try:
            summary = self.getStep6CaseJawLandmarkSummary(landmarks)
        except ValueError as exc:
            return [str(exc)]
        if not summary["isComplete"]:
            return [
                _(
                    "Place all four case landmarks through the guided surface "
                    "workflow: Left TMJ, Right TMJ, upper incisor, lower incisor."
                )
            ]
        try:
            associations = self.step6CaseJawLandmarkSegmentAssociations(parameterNode)
        except ValueError as exc:
            return [str(exc)]
        try:
            evidence = json.loads(
                landmarks.GetAttribute("DENTOBOT.SurfaceEvidenceJson") or "[]"
            )
        except (TypeError, json.JSONDecodeError):
            evidence = []
        if len(evidence) != 4:
            return [
                _(
                    "All four landmarks must be placed with source-specific "
                    "surface snapping before opening the case jaw."
                )
            ]
        evidenceByIndex = {
            int(item.get("landmarkIndex", -1)): item for item in evidence
        }
        for index, segmentId in enumerate(associations):
            item = evidenceByIndex.get(index, {})
            if item.get("sourceSegmentId") != segmentId:
                return [_('A case jaw landmark has stale surface provenance.')]
            expected = self._step6CaseJawGeometryFingerprint(
                parameterNode.teethSegmentation, (segmentId,)
            )
            if item.get("sourceGeometryFingerprint") != expected:
                return [_('A landmark source surface changed after placement.')]
            recordedPoint = item.get("pointWorldRasMm")
            if not isinstance(recordedPoint, list) or len(recordedPoint) != 3:
                return [_('A case jaw landmark lacks its projected surface point.')]
            currentPoint = [0.0, 0.0, 0.0]
            landmarks.GetNthControlPointPositionWorld(index, currentPoint)
            if float(
                np.linalg.norm(
                    np.asarray(currentPoint, dtype=float)
                    - np.asarray(recordedPoint, dtype=float)
                )
            ) > 1e-6:
                return [
                    _(
                        "A case jaw landmark moved after source-surface projection; "
                        "clear and replace the landmarks through Step 6A."
                    )
                ]
        return []

    def validateStep6CaseJawLandmarkAnatomy(self, parameterNode) -> dict:
        evidenceIssues = self.step6CaseJawSurfaceEvidenceIssues(parameterNode)
        if evidenceIssues:
            raise ValueError(evidenceIssues[0])
        landmarks = parameterNode.step6CaseJawLandmarks
        left, right, upper, lower = self.step6CaseJawLandmarkPositions(landmarks)
        associations = self.step6CaseJawLandmarkSegmentAssociations(parameterNode)
        evidence = json.loads(
            landmarks.GetAttribute("DENTOBOT.SurfaceEvidenceJson") or "[]"
        )
        condylarReview = validate_patient_ras_condylar_landmarks(left, right)
        volume = parameterNode.inputVolume
        if volume:
            bounds = [0.0] * 6
            volume.GetRASBounds(bounds)
            for point in (left, right):
                margins = (
                    point[0] - bounds[0],
                    bounds[1] - point[0],
                    point[1] - bounds[2],
                    bounds[3] - point[1],
                    point[2] - bounds[4],
                    bounds[5] - point[2],
                )
                if min(float(value) for value in margins) < 1.0:
                    raise ValueError(
                        _(
                            "A condylar landmark is at the CBCT field-of-view "
                            "boundary; bilateral hinge anatomy may be cropped."
                        )
                    )
        return {
            "associations": associations,
            "evidence": evidence,
            "closedGapMm": float(np.linalg.norm(lower - upper)),
            "condylarReview": condylarReview,
        }

    def recordStep6CaseJawPreparationFailure(
        self,
        parameterNode,
        reason: str,
    ) -> bool:
        """Persist a current anatomy/solver failure that can authorize fallback."""
        if (
            not bool(parameterNode.step6PlanningContextImported)
            or bool(parameterNode.robotBaseMountLocked)
            or self.isRos2MotionControlActive(parameterNode.robotBaseTransform)
        ):
            return False
        segmentation = parameterNode.teethSegmentation
        targetJaw = self.step6TargetJaw(parameterNode)
        if segmentation is None or targetJaw not in {"upper", "lower"}:
            return False
        targetIds = self.step6CaseJawSegmentIds(segmentation)[targetJaw]
        if not targetIds:
            return False
        if self.step6CaseJawSurfaceEvidenceIssues(parameterNode):
            # Missing, legacy, manually moved, or stale landmark evidence is an
            # operator-review prerequisite, not an anatomy/solver failure.
            return False
        excluded = (
            "import the steps 0–5",
            "disconnect ros",
            "unlock the robot base",
            "place all four",
            "side-swapped",
            "implausibly close",
            "homologous superior levels",
        )
        reasonText = str(reason or "").strip()
        if not reasonText or any(value in reasonText.lower() for value in excluded):
            return False
        record = {
            "schemaVersion": self.STEP6_CASE_JAW_SCHEMA_VERSION,
            "status": "PrimaryPreparationFailed",
            "reason": reasonText,
            "targetJaw": targetJaw,
            "targetSegmentId": str(parameterNode.targetToothSegmentId or ""),
            "targetJawSegmentIds": list(targetIds),
            "sourceGeometryFingerprint": self._step6CaseJawGeometryFingerprint(
                segmentation, targetIds
            ),
            "recordedUtc": datetime.now(timezone.utc).isoformat(),
        }
        parameterNode.step6CaseJawLastFailureJson = canonical_json(record)
        return True

    def step6TargetJawFallbackFreshnessIssues(self, parameterNode) -> list[str]:
        if str(parameterNode.step6CaseJawPreparationMode) != "TargetJawFallback":
            return [_("Target-jaw-only fallback has not been prepared.")]
        segmentation = parameterNode.teethSegmentation
        targetJaw = self.step6TargetJaw(parameterNode)
        node = parameterNode.step6TargetJawFallbackAnatomy
        if segmentation is None or targetJaw not in {"upper", "lower"}:
            return [_("The fallback target-jaw source is unavailable.")]
        if not self.isStep6DerivedAnatomyNode(
            node, self.STEP6_TARGET_JAW_FALLBACK_ANATOMY_ROLE
        ):
            return [_("The target-jaw-only fallback anatomy is missing.")]
        if node.GetParentTransformNode() is not None:
            return [_("Fallback anatomy must remain in source world RAS.")]
        if node.GetAttribute("DENTOBOT.GeometryState") != "Current":
            return [_("The target-jaw-only fallback anatomy is stale.")]
        segmentIds = self.step6CaseJawSegmentIds(segmentation)[targetJaw]
        expected = self._step6CaseJawGeometryFingerprint(segmentation, segmentIds)
        if node.GetAttribute("DENTOBOT.SourceGeometryFingerprint") != expected:
            return [_("The target-jaw fallback source anatomy changed.")]
        if node.GetAttribute("DENTOBOT.TargetSegmentID") != str(
            parameterNode.targetToothSegmentId or ""
        ):
            return [_("The selected target changed after fallback preparation.")]
        return []

    def step6CaseJawPlacementFreshnessIssues(self, parameterNode) -> list[str]:
        """Return placement-only anatomy issues; fallback may satisfy this gate."""
        if not bool(parameterNode.step6PlanningContextImported):
            return []
        if str(parameterNode.step6CaseJawPreparationMode) == "TargetJawFallback":
            return self.step6TargetJawFallbackFreshnessIssues(parameterNode)
        return self.step6CaseJawOpeningFreshnessIssues(parameterNode)

    def createStep6TargetJawFallback(self, parameterNode) -> dict:
        """Expose the target jaw in its unchanged source pose for placement tests."""
        if bool(parameterNode.robotBaseMountLocked) or self.isRos2MotionControlActive(
            parameterNode.robotBaseTransform
        ):
            raise ValueError(_("Disconnect ROS and unlock the robot base first."))
        try:
            failure = json.loads(
                str(parameterNode.step6CaseJawLastFailureJson or "") or "{}"
            )
        except (TypeError, json.JSONDecodeError):
            failure = {}
        segmentation = parameterNode.teethSegmentation
        targetJaw = self.step6TargetJaw(parameterNode)
        if (
            not isinstance(failure, dict)
            or failure.get("status") != "PrimaryPreparationFailed"
            or segmentation is None
            or targetJaw not in {"upper", "lower"}
        ):
            raise ValueError(
                _(
                    "Run the primary jaw-opening preparation first; fallback is "
                    "enabled only after a recorded anatomy or solver failure."
                )
            )
        evidenceIssues = self.step6CaseJawSurfaceEvidenceIssues(parameterNode)
        if evidenceIssues:
            raise ValueError(evidenceIssues[0])
        segmentIds = self.step6CaseJawSegmentIds(segmentation)[targetJaw]
        fingerprintNow = self._step6CaseJawGeometryFingerprint(segmentation, segmentIds)
        if (
            failure.get("targetJaw") != targetJaw
            or failure.get("targetSegmentId")
            != str(parameterNode.targetToothSegmentId or "")
            or failure.get("sourceGeometryFingerprint") != fingerprintNow
        ):
            raise ValueError(
                _("The recorded primary failure is stale; retry primary preparation.")
            )

        self.resetStep6CaseJawOpening(parameterNode)
        parameterNode.step6CaseJawLastFailureJson = canonical_json(failure)
        node = self._createStep6DerivedAnatomy(
            parameterNode,
            segmentation,
            segmentIds,
            existingNode=None,
            name=f"[Step 6.0A Fallback] Unopened {targetJaw.title()} Jaw + Teeth",
            role=self.STEP6_TARGET_JAW_FALLBACK_ANATOMY_ROLE,
            mode="TargetJawFallback",
        )
        node.SetAttribute(
            "DENTOBOT.TargetSegmentID", str(parameterNode.targetToothSegmentId or "")
        )
        node.SetAttribute("DENTOBOT.IntendedUse", "PlacementTestingOnly")
        node.SetAttribute("DENTOBOT.OpenMouthValidity", "Unavailable")
        node.SetAttribute("DENTOBOT.CollisionPlanningValidity", "Blocked")
        jawGroups = self.step6CaseJawSegmentIds(segmentation)
        self._hideStep6SourceJawSegments(
            segmentation, node, jawGroups["upper"] + jawGroups["lower"]
        )
        record = {
            "schemaVersion": self.STEP6_CASE_JAW_SCHEMA_VERSION,
            "mode": "TargetJawFallback",
            "state": "ProvisionalPlacementOnly",
            "targetJaw": targetJaw,
            "targetSegmentId": str(parameterNode.targetToothSegmentId or ""),
            "segmentIds": list(segmentIds),
            "sourceGeometryFingerprint": fingerprintNow,
            "sourcePose": "UnchangedWorldRAS",
            "transformApplied": False,
            "primaryFailure": failure.get("reason", ""),
            "allowedUse": [
                "robot-placement",
                "task-home",
                "workspace-exploration",
            ],
            "blockedUse": [
                "ROS-connect",
                "collision-sync",
                "task-confirmation",
                "motion-planning",
                "drilling-preview",
            ],
        }
        parameterNode.step6TargetJawFallbackAnatomy = node
        parameterNode.step6CaseJawPreparationMode = "TargetJawFallback"
        parameterNode.step6CaseJawPreparationJson = canonical_json(record)
        self.invalidateStep6TaskConfirmation(
            parameterNode,
            _(
                "Target-jaw-only fallback prepared; collision and task planning "
                "remain blocked."
            ),
            makeBaseStale=True,
        )
        self.deleteRobotWorkspaceModel()
        return record

    def step6CaseJawOpeningFreshnessIssues(self, parameterNode) -> list[str]:
        """Return reasons the imported case is not in a current open-mouth pose."""
        if not bool(parameterNode.step6PlanningContextImported):
            return []
        mode = str(parameterNode.step6CaseJawPreparationMode or "ClosedSource")
        if mode == "TargetJawFallback":
            fallbackIssues = self.step6TargetJawFallbackFreshnessIssues(parameterNode)
            if fallbackIssues:
                return fallbackIssues
            return [
                _(
                    "Target-jaw-only fallback is placement-testing anatomy, not a "
                    "valid open-mouth collision/planning state."
                )
            ]
        if mode != "ProvisionalOpenProxy":
            return [_("Apply the Step 6 case open-mouth preparation.")]
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
        if transform.GetAttribute("DENTOBOT.SchemaVersion") != self.STEP6_CASE_JAW_SCHEMA_VERSION:
            return [_("The saved case jaw opening uses a legacy schema; review and re-apply it.")]
        if not self.isStep6OpenedLowerJawModelNode(model):
            return [_("The derived opened lower-jaw planning surface is missing.")]
        fixedUpper = parameterNode.step6FixedUpperAnatomy
        movingLower = parameterNode.step6MovingLowerAnatomy
        if not self.isStep6DerivedAnatomyNode(
            fixedUpper, self.STEP6_FIXED_UPPER_ANATOMY_ROLE
        ):
            return [_("The derived fixed upper-jaw anatomy is missing.")]
        if not self.isStep6DerivedAnatomyNode(
            movingLower, self.STEP6_MOVING_LOWER_ANATOMY_ROLE
        ):
            return [_("The derived moving lower-jaw anatomy is missing.")]
        if fixedUpper.GetParentTransformNode() is not None:
            return [_("Fixed upper-jaw anatomy must remain in world RAS.")]
        if movingLower.GetParentTransformNode() is not transform:
            return [_("Moving lower-jaw anatomy is detached from its hinge transform.")]
        if transform.GetAttribute("DENTOBOT.GeometryState") != "Current":
            return [
                transform.GetAttribute("DENTOBOT.StaleReason")
                or _("Re-apply the Step 6 case open-mouth transform.")
            ]
        if transform.GetParentTransformNode() is not None:
            return [_("The case TMJ transform must remain in world RAS.")]
        try:
            self.validateStep6CaseJawLandmarkAnatomy(parameterNode)
            left, right, upper, lower = self.step6CaseJawLandmarkPositions(landmarks)
            _angle, expectedMatrix, _openedLower, _gap = (
                solve_anatomy_directed_hinge_rotation_for_gap(
                    left,
                    right,
                    upper,
                    lower,
                    float(parameterNode.step6CaseJawTargetGapMm),
                )
            )
        except ValueError as exc:
            return [str(exc)]
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
        upperIds = segmentGroups["upper"]
        lowerIds = segmentGroups["lower"]
        if not upperIds:
            return [_("No upper-jaw or maxillary tooth surfaces are available.")]
        if not lowerIds:
            return [_("No lower-jaw or mandibular tooth surfaces are available.")]
        expectedUpperFingerprint = self._step6CaseJawGeometryFingerprint(
            segmentation,
            upperIds,
        )
        if (
            fixedUpper.GetAttribute("DENTOBOT.SourceGeometryFingerprint")
            != expectedUpperFingerprint
        ):
            return [_("Fixed upper-jaw segmentation geometry changed.")]
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
        if (
            movingLower.GetAttribute("DENTOBOT.SourceGeometryFingerprint")
            != expectedFingerprint
        ):
            return [_("Moving lower-jaw segmentation geometry changed.")]
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
        if parameterNode.step6TargetJawFallbackAnatomy:
            self._restoreStep6DerivedAnatomyVisibility(parameterNode)
            fallbackNode = parameterNode.step6TargetJawFallbackAnatomy
            if slicer.mrmlScene.IsNodePresent(fallbackNode):
                slicer.mrmlScene.RemoveNode(fallbackNode)
            parameterNode.step6TargetJawFallbackAnatomy = None
        jawGroups = self.step6CaseJawSegmentIds(segmentation)
        upperIds = jawGroups["upper"]
        lowerIds = jawGroups["lower"]
        if not upperIds:
            raise ValueError(
                _("The imported segmentation has no maxillary jaw or upper-tooth surfaces.")
            )
        if not lowerIds:
            raise ValueError(
                _("The imported segmentation has no mandibular jaw or lower-tooth surfaces.")
            )
        left, right, upper, lower = self.step6CaseJawLandmarkPositions(
            parameterNode.step6CaseJawLandmarks
        )
        self.validateStep6CaseJawLandmarkAnatomy(parameterNode)
        angle, matrix, openedLower, gap = solve_anatomy_directed_hinge_rotation_for_gap(
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
        upperFingerprint = self._step6CaseJawGeometryFingerprint(
            segmentation,
            upperIds,
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
        transform.SetAttribute("DENTOBOT.FixedSegmentIdsJson", canonical_json(upperIds))
        transform.SetAttribute("DENTOBOT.FixedGeometryFingerprint", upperFingerprint)
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
        fixedUpper = self._createStep6DerivedAnatomy(
            parameterNode,
            segmentation,
            upperIds,
            existingNode=parameterNode.step6FixedUpperAnatomy,
            name="[Step 6.0A] Fixed Upper Jaw + Teeth",
            role=self.STEP6_FIXED_UPPER_ANATOMY_ROLE,
            mode="ProvisionalOpenProxy",
        )
        movingLower = self._createStep6DerivedAnatomy(
            parameterNode,
            segmentation,
            lowerIds,
            existingNode=parameterNode.step6MovingLowerAnatomy,
            name="[Step 6.0A] Moving Lower Jaw + Teeth",
            role=self.STEP6_MOVING_LOWER_ANATOMY_ROLE,
            mode="ProvisionalOpenProxy",
            transformNode=transform,
        )
        self._hideStep6SourceJawSegments(segmentation, fixedUpper, upperIds)
        self._hideStep6SourceJawSegments(segmentation, movingLower, lowerIds)
        modelDisplay = model.GetDisplayNode()
        if modelDisplay:
            modelDisplay.SetVisibility3D(False)

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
        parameterNode.step6FixedUpperAnatomy = fixedUpper
        parameterNode.step6MovingLowerAnatomy = movingLower
        parameterNode.step6TargetJawFallbackAnatomy = None
        parameterNode.step6CaseJawGapLine = gapLine
        parameterNode.step6CaseJawPreparationMode = "ProvisionalOpenProxy"
        parameterNode.step6CaseJawPreparationJson = canonical_json(
            {
                "schemaVersion": self.STEP6_CASE_JAW_SCHEMA_VERSION,
                "mode": "ProvisionalOpenProxy",
                "state": "ProvisionalOpenProxy",
                "motionModel": "AnatomyDirectedPureTMJHingeRotation",
                "fixedUpperSegmentIds": list(upperIds),
                "movingLowerSegmentIds": list(lowerIds),
                "fixedUpperGeometryFingerprint": upperFingerprint,
                "movingLowerGeometryFingerprint": sourceFingerprint,
                "targetGapMm": float(parameterNode.step6CaseJawTargetGapMm),
                "achievedGapMm": float(gap),
                "hingeAngleDeg": float(angle),
                "worldRasMatrix": tuple(
                    tuple(float(value) for value in row) for row in matrix
                ),
                "sourceMasksResampled": False,
                "intendedUse": "SimulationPreviewOnly",
            }
        )
        parameterNode.step6CaseJawLastFailureJson = ""
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
        if self.isRos2MotionControlActive(parameterNode.robotBaseTransform):
            raise ValueError(
                _("Disconnect ROS before resetting the case jaw.")
            )
        model = parameterNode.step6OpenedLowerJawModel
        transform = parameterNode.step6CaseJawTransform
        gapLine = parameterNode.step6CaseJawGapLine
        self._restoreStep6CaseLowerJawVisibility(
            parameterNode.teethSegmentation,
            model,
        )
        self._restoreStep6DerivedAnatomyVisibility(parameterNode)
        self._restoreStep6CaseTargetAttachedVisibility(parameterNode)
        for node in (
            parameterNode.step6OpenedTrajectoryLine,
            parameterNode.step6OpenedTargetGeometryModel,
            parameterNode.step6TargetJawFallbackAnatomy,
            parameterNode.step6MovingLowerAnatomy,
            parameterNode.step6FixedUpperAnatomy,
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
        parameterNode.step6FixedUpperAnatomy = None
        parameterNode.step6MovingLowerAnatomy = None
        parameterNode.step6TargetJawFallbackAnatomy = None
        parameterNode.step6CaseJawPreparationMode = "ClosedSource"
        parameterNode.step6CaseJawPreparationJson = ""
        parameterNode.step6CaseJawLastFailureJson = ""
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
