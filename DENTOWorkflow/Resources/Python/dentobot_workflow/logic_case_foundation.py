"""Case Foundation identity, opened CBCT displays, and readiness gates."""

from __future__ import annotations

from .runtime import *


class CaseFoundationLogicMixin:
    CASE_FOUNDATION_HINGE_SCHEMA = "AnatomyDirectedPureTMJHingeRotationV2"

    @classmethod
    def isStep6CaseJawLandmarksNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsFiducialNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole")
            == cls.STEP6_CASE_JAW_LANDMARKS_ROLE
        )

    @classmethod
    def isStep6CaseJawTransformNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLLinearTransformNode")
            and node.GetAttribute("DENTOBOT.TransformRole")
            == cls.STEP6_CASE_JAW_TRANSFORM_ROLE
        )

    @classmethod
    def isStep6OpenedLowerJawModelNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLModelNode")
            and node.GetAttribute("DENTOBOT.ModelRole")
            == cls.STEP6_OPENED_LOWER_JAW_MODEL_ROLE
        )

    @classmethod
    def isStep6OpenedTargetGeometryModelNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLModelNode")
            and node.GetAttribute("DENTOBOT.ModelRole")
            == cls.STEP6_OPENED_TARGET_GEOMETRY_MODEL_ROLE
        )

    @classmethod
    def isStep6OpenedTrajectoryNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsLineNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole")
            == cls.STEP6_OPENED_TRAJECTORY_ROLE
        )

    @classmethod
    def caseFoundationLandmarkPlacementHints(cls) -> tuple[str, ...]:
        return cls.CASE_FOUNDATION_LANDMARK_LABELS

    @classmethod
    def caseFoundationLandmarkButtonLabels(cls) -> tuple[str, ...]:
        return (
            _("Place first landmark (Left TMJ)"),
            _("Place second landmark (Right TMJ — first landmark is Left TMJ)"),
            _("Place third landmark (Upper incisor)"),
            _("Place fourth landmark (Lower incisor)"),
        )

    @classmethod
    def startStep6CaseJawLandmarkPlacement(
        cls,
        landmarksNode: vtkMRMLMarkupsFiducialNode,
    ) -> None:
        """Activate Slicer's native placement mode for Case Foundation landmarks."""

        if not cls.isStep6CaseJawLandmarksNode(landmarksNode):
            raise ValueError(_("Create the Case Foundation jaw landmarks first."))
        if landmarksNode.GetNumberOfDefinedControlPoints() >= 4:
            raise ValueError(_("All four Case Foundation landmarks are already placed."))
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if not selectionNode:
            raise RuntimeError(_("Slicer's selection node is unavailable."))
        selectionNode.SetReferenceActivePlaceNodeClassName(
            "vtkMRMLMarkupsFiducialNode"
        )
        selectionNode.SetActivePlaceNodeID(landmarksNode.GetID())
        slicer.modules.markups.logic().StartPlaceMode(0)
        selectionNode.SetActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
        selectionNode.SetActivePlaceNodeID(landmarksNode.GetID())
        if (
            selectionNode.GetActivePlaceNodeID() != landmarksNode.GetID()
            or selectionNode.GetActivePlaceNodeClassName()
            != "vtkMRMLMarkupsFiducialNode"
            or not selectionNode.GetActivePlaceNodePlacementValid()
        ):
            interactionNode = slicer.app.applicationLogic().GetInteractionNode()
            if interactionNode:
                interactionNode.SwitchToViewTransformMode()
            raise RuntimeError(
                _("Slicer could not activate Case Foundation landmark placement.")
            )

    def ensureStep6CaseJawLandmarksNode(self, node):
        if node and not self.isStep6CaseJawLandmarksNode(node):
            raise ValueError(_("Select the Case Foundation landmark set."))
        node = node or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsFiducialNode",
            "[Case Foundation] Jaw Landmarks",
        )
        node.SetName("[Case Foundation] Jaw Landmarks")
        if hasattr(node, "SetMaximumNumberOfControlPoints"):
            node.SetMaximumNumberOfControlPoints(
                len(self.CASE_FOUNDATION_LANDMARK_LABELS)
            )
        node.SetLocked(False)
        node.SetSelectable(True)
        node.SetAttribute("DENTOBOT.MarkupsRole", self.STEP6_CASE_JAW_LANDMARKS_ROLE)
        node.SetAttribute("DENTOBOT.SchemaVersion", self.STEP6_CASE_JAW_SCHEMA_VERSION)
        node.SetAttribute("DENTOBOT.Status", "CasePlanningInput")
        node.SetAttribute(
            "DENTOBOT.PlacementOrder",
            "LeftTMJ,RightTMJ,UpperCentralIncisor,LowerCentralIncisor",
        )
        node.CreateDefaultDisplayNodes()
        display = node.GetDisplayNode()
        if display:
            display.SetVisibility(True)
            display.SetVisibility2D(True)
            display.SetVisibility3D(True)
            display.SetColor(0.10, 0.85, 1.00)
            display.SetSelectedColor(1.0, 0.55, 0.10)
            display.SetPointLabelsVisibility(True)
            display.SetGlyphScale(1.4)
        return node

    def getStep6CaseJawLandmarkSummary(self, node) -> dict[str, object]:
        if not self.isStep6CaseJawLandmarksNode(node):
            raise ValueError(_("Create the Case Foundation landmarks first."))
        expected = len(self.CASE_FOUNDATION_LANDMARK_LABELS)
        count = node.GetNumberOfDefinedControlPoints()
        if count < 0 or count > expected:
            raise ValueError(_("The Case Foundation landmark set has an invalid point count."))
        for index in range(count):
            label = self.CASE_FOUNDATION_LANDMARK_LABELS[index]
            if node.GetNthControlPointLabel(index) != label:
                node.SetNthControlPointLabel(index, label)
        return {"definedPointCount": count, "isComplete": count == expected}

    def step6CaseJawLandmarkPositions(self, node) -> tuple[np.ndarray, ...]:
        if not self.getStep6CaseJawLandmarkSummary(node)["isComplete"]:
            raise ValueError(_("Place all four Case Foundation landmarks in order."))
        positions = []
        for index in range(4):
            point = [0.0, 0.0, 0.0]
            node.GetNthControlPointPositionWorld(index, point)
            positions.append(np.asarray(point, dtype=float))
        return tuple(positions)

    def hideLegacyDraftPhantomNodes(self) -> int:
        hidden = 0
        for node in slicer.util.getNodesByClass("vtkMRMLDisplayableNode"):
            if not (
                node.GetAttribute("DENTOBOT.ModelRole") == "DraftOpenMouthPhantom"
                or node.GetAttribute("DENTOBOT.MarkupsRole") in {
                    "DraftJawLandmarks",
                    "DraftJawGapLine",
                }
            ):
                continue
            display = node.GetDisplayNode()
            if display:
                display.SetVisibility(False)
            node.SetSelectable(False)
            hidden += 1
        return hidden

    def _cachedCaseFoundationFingerprint(self, key: tuple, builder) -> str:
        cache = getattr(self, "_caseFoundationFingerprintCache", None)
        if cache is None:
            cache = {}
            self._caseFoundationFingerprintCache = cache
        if key not in cache:
            if len(cache) >= 8:
                cache.clear()
            cache[key] = builder()
        return cache[key]

    @staticmethod
    def _foundationMatrixValues(node) -> tuple[float, ...]:
        if not node:
            return ()
        matrix = vtk.vtkMatrix4x4()
        node.GetMatrixTransformToWorld(matrix)
        return tuple(
            round(float(matrix.GetElement(row, column)), 9)
            for row in range(4)
            for column in range(4)
        )

    def caseFoundationSourceVolumeFingerprint(self, volumeNode) -> str:
        if not volumeNode or not volumeNode.GetImageData():
            return ""
        imageData = volumeNode.GetImageData()
        matrix = vtk.vtkMatrix4x4()
        volumeNode.GetIJKToRASMatrix(matrix)
        geometry = tuple(
            round(float(matrix.GetElement(row, column)), 9)
            for row in range(4)
            for column in range(4)
        )
        key = ("volume", volumeNode.GetID(), imageData.GetMTime(), geometry)

        def build() -> str:
            array = np.ascontiguousarray(slicer.util.arrayFromVolume(volumeNode))
            return fingerprint(
                {
                    "shape": tuple(int(value) for value in array.shape),
                    "dtype": str(array.dtype),
                    "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
                    "ijkToRas": geometry,
                }
            )

        return self._cachedCaseFoundationFingerprint(
            key,
            build,
        )

    def caseFoundationSourceSegmentationFingerprint(self, segmentationNode) -> str:
        if not segmentationNode or not segmentationNode.GetSegmentation():
            return ""
        segmentation = segmentationNode.GetSegmentation()
        key = (
            "segmentation",
            segmentationNode.GetID(),
            segmentation.GetMTime(),
            segmentationNode.GetMTime(),
        )

        def build() -> str:
            records = []
            for review in self.getSegmentationReviewRecords(segmentationNode):
                segmentId = str(review.get("segmentId") or "")
                if not segmentId:
                    continue
                try:
                    array = np.ascontiguousarray(
                        slicer.util.arrayFromSegmentBinaryLabelmap(
                            segmentationNode, segmentId
                        )
                    )
                except RuntimeError:
                    return ""
                records.append(
                    {
                        "id": segmentId,
                        "review": review,
                        "shape": tuple(int(value) for value in array.shape),
                        "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
                    }
                )
            return fingerprint(
                {
                    "referenceGeometry": str(
                        segmentation.GetConversionParameter(
                            "Reference image geometry"
                        )
                        or ""
                    ),
                    "segments": records,
                }
            ) if records else ""

        return self._cachedCaseFoundationFingerprint(key, build)

    def buildCaseFoundationSnapshot(self, parameterNode):
        volume = parameterNode.inputVolume
        segmentation = parameterNode.teethSegmentation
        transform = parameterNode.step6CaseJawTransform
        landmarks = parameterNode.step6CaseJawLandmarks
        base = parameterNode.robotBaseTransform
        positions = ()
        if (
            self.isStep6CaseJawLandmarksNode(landmarks)
            and landmarks.GetNumberOfDefinedControlPoints() == 4
        ):
            positions = tuple(
                float(value)
                for point in self.step6CaseJawLandmarkPositions(landmarks)
                for value in point
            )
        try:
            preparation = json.loads(
                str(parameterNode.step6CaseJawPreparationJson or "") or "{}"
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            preparation = {}
        try:
            home = json.loads(str(parameterNode.step6TaskHomeJson or "") or "null")
        except (TypeError, ValueError, json.JSONDecodeError):
            home = None
        anatomy = (
            self._caseBundleNodeRecord("teethSegmentation", segmentation)
            if segmentation else {}
        )
        robotProfile = self.caseBundleRobotProfile()
        return build_robot_environment_snapshot(
            case_identity=self._stableDentoCaseId(
                "case", parameterNode.caseName, fingerprint(anatomy)
            ),
            anatomy_fingerprint=fingerprint(anatomy),
            source_volume_fingerprint=self.caseFoundationSourceVolumeFingerprint(volume),
            source_segmentation_fingerprint=(
                self.caseFoundationSourceSegmentationFingerprint(segmentation)
            ),
            jaw_source_fingerprint=(
                str(transform.GetAttribute("DENTOBOT.SourceGeometryFingerprint") or "")
                if transform else ""
            ),
            jaw_landmarks_fingerprint=(
                self._step6CaseJawLandmarksFingerprint(landmarks)
                if self.isStep6CaseJawLandmarksNode(landmarks) else ""
            ),
            landmark_positions_ras_mm=positions,
            landmark_review_fingerprint=fingerprint(
                str(landmarks.GetAttribute("DENTOBOT.SurfaceEvidenceJson") or "")
            ) if landmarks else "",
            hinge_model_schema=str(
                preparation.get("hingeModelSchema")
                or (transform.GetAttribute("DENTOBOT.HingeModelSchema") if transform else "")
                or ""
            ),
            jaw_configuration_fingerprint=fingerprint(preparation),
            jaw_transform_matrix=self._foundationMatrixValues(transform),
            mouth_gap_mm=(
                float(parameterNode.step6CaseJawTargetGapMm) if transform else None
            ),
            opening_revision=int(parameterNode.caseFoundationOpeningRevision),
            robot_profile_fingerprint=str(robotProfile.get("identitySha256") or ""),
            tool_identity=str(parameterNode.step6ToolFrame or ""),
            tool_fingerprint=fingerprint({"toolFrame": str(parameterNode.step6ToolFrame or "")}),
            base_matrix=self._foundationMatrixValues(base),
            base_status=str(parameterNode.step6BasePlacementStatus),
            base_locked=bool(parameterNode.robotBaseMountLocked),
            base_fingerprint=self.robotBaseFingerprint(parameterNode),
            base_authority=str(parameterNode.step6BasePlacementSource or ""),
            base_revision=int(parameterNode.step6BasePlacementRevision),
            task_home_configuration=home,
            common_collision_fingerprint=fingerprint(
                {
                    "anatomy": fingerprint(anatomy),
                    "jaw": self._foundationMatrixValues(transform),
                    "robot": str(robotProfile.get("identitySha256") or ""),
                    "tool": str(parameterNode.step6ToolFrame or ""),
                }
            ),
            limits_fingerprint=self.step6TaskLimitsFingerprint(parameterNode),
            workspace_fingerprint=fingerprint(
                str(parameterNode.step6AssistedLimitProposalJson or "")
            ),
        )

    def evaluateCaseFoundationEligibility(self, parameterNode) -> dict[str, object]:
        def component(eligible: bool, code: str, message: str) -> dict[str, object]:
            return {"eligible": bool(eligible), "code": code, "message": str(message)}

        volume = parameterNode.inputVolume
        segmentation = parameterNode.teethSegmentation
        landmarks = parameterNode.step6CaseJawLandmarks
        transform = parameterNode.step6CaseJawTransform
        pose = component(False, "MISSING_REVIEWED_SEGMENTATION", _("Review the segmentation before creating the Case Foundation."))
        snapshot = self.buildCaseFoundationSnapshot(parameterNode)
        if (
            volume and segmentation
            and self.getSegmentationReviewState(segmentation) == "Reviewed"
        ):
            if not self.isStep6CaseJawLandmarksNode(landmarks):
                pose = component(False, "MISSING_LANDMARKS", _("Place the four Case Foundation landmarks."))
            elif landmarks.GetNumberOfDefinedControlPoints() != 4 or self.step6CaseJawSurfaceEvidenceIssues(parameterNode):
                pose = component(False, "INCOMPLETE_LANDMARK_REVIEW", _("Review all four Case Foundation landmarks on their source surfaces."))
            elif not self.isStep6CaseJawTransformNode(transform):
                pose = component(False, "STALE_MOUTH_OPENING", _("Calculate and commit the Case Foundation mouth opening."))
            elif (
                not parameterNode.caseFoundationFixedUpperVolume
                or not parameterNode.caseFoundationMovingLowerVolume
            ):
                pose = component(False, "MISSING_OPENED_ANATOMY", _("Reconstruct the opened Case Foundation CBCT displays."))
            elif (
                str(transform.GetAttribute("DENTOBOT.SourceVolumeFingerprint") or "")
                != snapshot.source_volume_fingerprint
                or str(transform.GetAttribute("DENTOBOT.SourceSegmentationFingerprint") or "")
                != snapshot.source_segmentation_fingerprint
            ):
                pose = component(False, "SOURCE_MISMATCH", _("The source CBCT or reviewed segmentation changed."))
            elif str(transform.GetAttribute("DENTOBOT.PlanningPoseFingerprint") or "") != snapshot.planning_pose_fingerprint:
                pose = component(False, "STALE_MOUTH_OPENING", _("The committed Case Foundation pose is stale."))
            elif str(transform.GetAttribute("DENTOBOT.HingeModelSchema") or "") != self.CASE_FOUNDATION_HINGE_SCHEMA:
                pose = component(False, "LEGACY_UNVERIFIED", _("Review and promote the legacy mouth opening to the current Case Foundation."))
            else:
                pose = component(True, "VALID", _("Case Foundation planning pose is current."))

        base = parameterNode.robotBaseTransform
        if not self.isRobotBaseTransformNode(base):
            baseResult = component(False, "BASE_MISSING", _("Load the offline robot and place its Manual Simulation Base."))
        elif str(parameterNode.step6BasePlacementStatus) == BasePlacementStatus.STALE.value:
            baseResult = component(False, "BASE_STALE", _("Review and lock the Manual Simulation Base again."))
        elif not bool(parameterNode.robotBaseMountLocked):
            baseResult = component(False, "BASE_UNLOCKED", _("Review and lock the Manual Simulation Base."))
        elif str(base.GetAttribute("DENTOBOT.CaseFoundationFingerprint") or "") != snapshot.planning_pose_fingerprint:
            baseResult = component(False, "BASE_STALE", _("The Manual Simulation Base belongs to another Case Foundation pose."))
        elif str(base.GetAttribute("DENTOBOT.RobotProfileFingerprint") or "") != snapshot.robot_profile_fingerprint:
            baseResult = component(False, "ROBOT_PROFILE_MISMATCH", _("The robot profile changed after base review."))
        else:
            baseResult = component(True, "VALID", _("Manual Simulation Base is current and reviewed."))
        return {
            "pose": pose,
            "base": baseResult,
            "source_volume_fingerprint": snapshot.source_volume_fingerprint,
            "source_segmentation_fingerprint": snapshot.source_segmentation_fingerprint,
            "planning_pose_fingerprint": snapshot.planning_pose_fingerprint,
            "base_setup_fingerprint": snapshot.base_setup_fingerprint,
            "foundation_fingerprint": snapshot.foundation_fingerprint,
        }

    def requireCaseFoundationPose(self, parameterNode) -> dict[str, object]:
        result = self.evaluateCaseFoundationEligibility(parameterNode)
        if not result["pose"]["eligible"]:
            raise ValueError(result["pose"]["message"])
        return result

    def previewCaseFoundationOpening(
        self,
        parameterNode,
        targetGapMm: float,
    ) -> dict[str, object]:
        transform = parameterNode.step6CaseJawTransform
        if not self.isStep6CaseJawTransformNode(transform):
            raise ValueError(_("Commit the initial Case Foundation opening first."))
        self.validateStep6CaseJawLandmarkAnatomy(parameterNode)
        left, right, upper, lower = self.step6CaseJawLandmarkPositions(
            parameterNode.step6CaseJawLandmarks
        )
        angle, matrix, openedLower, gap = solve_anatomy_directed_hinge_rotation_for_gap(
            left, right, upper, lower, float(targetGapMm)
        )
        transform.SetMatrixTransformToParent(self._vtkFromNumpyMatrix(matrix))
        gapLine = parameterNode.step6CaseJawGapLine
        if gapLine and gapLine.IsA("vtkMRMLMarkupsLineNode"):
            gapLine.SetNthControlPointPositionWorld(0, *upper)
            gapLine.SetNthControlPointPositionWorld(1, *openedLower)
        parameterNode.caseFoundationPreviewUncommitted = True
        return {
            "angleDeg": float(angle),
            "gapMm": float(gap),
            "openedLowerIncisorRas": tuple(float(value) for value in openedLower),
        }

    def _invalidateCaseFoundationPoseDependents(self, parameterNode, reason: str) -> None:
        for model in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if self.isFinalPrintableTemplateModelNode(model):
                model.SetAttribute("DENTOBOT.VerificationState", "NotVerified")
                model.SetAttribute("DENTOBOT.VerificationJson", None)
                model.SetAttribute("DENTOBOT.Step5CStaleReason", str(reason))
        self.syncDentoCaseTrajectoryRegistry(parameterNode)
        self.invalidateStep6TaskConfirmation(
            parameterNode,
            reason,
            makeBaseStale=True,
        )
        self.deleteRobotWorkspaceModel()

    def invalidateCaseFoundationForSourceChange(
        self,
        parameterNode,
        reason: str,
    ) -> None:
        """Retain inspectable geometry while invalidating every source-bound gate."""

        transform = parameterNode.step6CaseJawTransform
        if self.isStep6CaseJawTransformNode(transform):
            transform.SetAttribute("DENTOBOT.GeometryState", "Stale")
            transform.SetAttribute("DENTOBOT.StaleReason", str(reason))
        for node in (
            parameterNode.step6OpenedLowerJawModel,
            parameterNode.step6FixedUpperAnatomy,
            parameterNode.step6MovingLowerAnatomy,
        ):
            if node:
                node.SetAttribute("DENTOBOT.GeometryState", "Stale")
        for model in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if self.isFinalPrintableTemplateModelNode(model):
                model.SetAttribute("DENTOBOT.GeometryState", "Stale")
                model.SetAttribute("DENTOBOT.StaleReason", str(reason))
        for volume in (
            parameterNode.caseFoundationFixedUpperVolume,
            parameterNode.caseFoundationMovingLowerVolume,
        ):
            if volume and slicer.mrmlScene.IsNodePresent(volume):
                slicer.mrmlScene.RemoveNode(volume)
        parameterNode.caseFoundationFixedUpperVolume = None
        parameterNode.caseFoundationMovingLowerVolume = None
        parameterNode.step6CaseJawPreparationMode = "LegacyUnverified"
        parameterNode.step6PlanningContextImported = False
        self._invalidateCaseFoundationPoseDependents(parameterNode, reason)

    def invalidateCaseFoundationBase(self, parameterNode, reason: str) -> None:
        base = parameterNode.robotBaseTransform
        if not self.isRobotBaseTransformNode(base):
            return
        wasReviewed = bool(
            parameterNode.robotBaseMountLocked
            or normalize_base_status(parameterNode.step6BasePlacementStatus)
            in {
                BasePlacementStatus.PROVISIONAL_LOCKED,
                BasePlacementStatus.REGISTERED_LOCKED,
            }
        )
        parameterNode.robotBaseMountLocked = False
        parameterNode.step6BasePlacementStatus = BasePlacementStatus.STALE.value
        if wasReviewed:
            parameterNode.step6BasePlacementRevision = max(
                0, int(parameterNode.step6BasePlacementRevision)
            ) + 1
        self._applyRobotBaseMountInteractionState(parameterNode, False)
        self.invalidateStep6TaskConfirmation(parameterNode, reason)
        self.deleteRobotWorkspaceModel()

    def commitCaseFoundationOpeningPreview(self, parameterNode) -> dict[str, object]:
        if not bool(parameterNode.caseFoundationPreviewUncommitted):
            return self.evaluateCaseFoundationEligibility(parameterNode)
        summary = self.previewCaseFoundationOpening(
            parameterNode,
            float(parameterNode.step6CaseJawTargetGapMm),
        )
        transform = parameterNode.step6CaseJawTransform
        parameterNode.caseFoundationOpeningRevision = max(
            0, int(parameterNode.caseFoundationOpeningRevision)
        ) + 1
        transform.SetAttribute(
            "DENTOBOT.TargetIncisorGapMm",
            f"{float(parameterNode.step6CaseJawTargetGapMm):.6f}",
        )
        transform.SetAttribute("DENTOBOT.AchievedIncisorGapMm", f"{summary['gapMm']:.6f}")
        transform.SetAttribute("DENTOBOT.HingeAngleDeg", f"{summary['angleDeg']:.6f}")
        preparation = self._step6CaseJawPreparationRecord(parameterNode)
        preparation.update(
            {
                "mode": "CaseFoundationCurrent",
                "state": "Current",
                "openingRevision": int(parameterNode.caseFoundationOpeningRevision),
                "targetGapMm": float(parameterNode.step6CaseJawTargetGapMm),
                "achievedGapMm": float(summary["gapMm"]),
                "hingeAngleDeg": float(summary["angleDeg"]),
                "worldRasMatrix": tuple(
                    tuple(float(value) for value in row)
                    for row in self._numpyFromVtkMatrix(
                        self._worldMatrixFromTransform(transform)
                    )
                ),
            }
        )
        parameterNode.step6CaseJawPreparationJson = canonical_json(preparation)
        snapshot = self.buildCaseFoundationSnapshot(parameterNode)
        transform.SetAttribute(
            "DENTOBOT.PlanningPoseFingerprint",
            snapshot.planning_pose_fingerprint,
        )
        transform.SetAttribute("DENTOBOT.GeometryState", "Current")
        transform.SetAttribute("DENTOBOT.StaleReason", None)
        parameterNode.caseFoundationPreviewUncommitted = False
        self._invalidateCaseFoundationPoseDependents(
            parameterNode,
            _("Case Foundation opening changed."),
        )
        return {
            **self.evaluateCaseFoundationEligibility(parameterNode),
            "opening": summary,
        }

    def revertCaseFoundationOpeningPreview(self, parameterNode) -> None:
        transform = parameterNode.step6CaseJawTransform
        if not self.isStep6CaseJawTransformNode(transform):
            return
        preparation = self._step6CaseJawPreparationRecord(parameterNode)
        matrix = np.asarray(preparation.get("worldRasMatrix") or (), dtype=float)
        if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
            raise ValueError(_("The committed Case Foundation matrix is unavailable."))
        parameterNode.step6CaseJawTargetGapMm = float(
            preparation.get("targetGapMm", parameterNode.step6CaseJawTargetGapMm)
        )
        self.previewCaseFoundationOpening(
            parameterNode,
            float(parameterNode.step6CaseJawTargetGapMm),
        )
        parameterNode.caseFoundationPreviewUncommitted = False

    def _targetJawOwner(self, parameterNode, targetSegmentId: str) -> str:
        if not targetSegmentId or not parameterNode.teethSegmentation:
            return ""
        groups = self.step6CaseJawSegmentIds(
            parameterNode.teethSegmentation
        )
        if targetSegmentId in groups["lower"]:
            return "MovingLower"
        if targetSegmentId in groups["upper"]:
            return "FixedUpper"
        return ""

    def _reparentCaseFoundationNodePreservingWorld(self, node, parent) -> None:
        oldParent = node.GetParentTransformNode()
        if oldParent is parent:
            return
        if node.IsA("vtkMRMLModelNode"):
            polyData = node.GetPolyData()
            if not polyData:
                raise ValueError(_("The planning model has no geometry to transform."))
            transform = vtk.vtkGeneralTransform()
            slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(
                oldParent, parent, transform
            )
            transformFilter = vtk.vtkTransformPolyDataFilter()
            transformFilter.SetInputData(polyData)
            transformFilter.SetTransform(transform)
            transformFilter.Update()
            converted = vtk.vtkPolyData()
            converted.DeepCopy(transformFilter.GetOutput())
            node.SetAndObservePolyData(converted)
            node.SetAndObserveTransformNodeID(parent.GetID() if parent else None)
            return
        if node.IsA("vtkMRMLMarkupsNode"):
            positions = []
            for index in range(node.GetNumberOfControlPoints()):
                point = [0.0, 0.0, 0.0]
                node.GetNthControlPointPositionWorld(index, point)
                positions.append(tuple(point))
            node.SetAndObserveTransformNodeID(parent.GetID() if parent else None)
            for index, point in enumerate(positions):
                node.SetNthControlPointPositionWorld(index, *point)
            return
        raise ValueError(_("This workflow node cannot be attached to the jaw safely."))

    def bindCaseFoundationNode(self, parameterNode, node) -> str:
        targetSegmentId = str(
            node.GetAttribute("DENTOBOT.TargetSegmentID")
            or node.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE)
            or ""
        )
        jawOwner = self._targetJawOwner(parameterNode, targetSegmentId)
        if not jawOwner:
            return ""
        foundation = self.requireCaseFoundationPose(parameterNode)
        parent = (
            parameterNode.step6CaseJawTransform
            if jawOwner == "MovingLower"
            else None
        )
        self._reparentCaseFoundationNodePreservingWorld(node, parent)
        node.SetAttribute("DENTOBOT.JawOwner", jawOwner)
        node.SetAttribute("DENTOBOT.TargetSegmentID", targetSegmentId)
        node.SetAttribute(
            "DENTOBOT.PlanningPoseFingerprint",
            foundation["planning_pose_fingerprint"],
        )
        return jawOwner

    def refreshCaseFoundationNodeOwnership(self, parameterNode) -> list[str]:
        if not self.evaluateCaseFoundationEligibility(parameterNode)["pose"]["eligible"]:
            return []
        changed = []
        for node in slicer.util.getNodesByClass("vtkMRMLDisplayableNode"):
            if not (
                node.GetAttribute("DENTOBOT.TargetSegmentID")
                or node.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE)
            ):
                continue
            beforeParent = node.GetParentTransformNode()
            before = (
                beforeParent.GetID() if beforeParent else None,
                node.GetAttribute("DENTOBOT.JawOwner"),
                node.GetAttribute("DENTOBOT.PlanningPoseFingerprint"),
            )
            self.bindCaseFoundationNode(parameterNode, node)
            afterParent = node.GetParentTransformNode()
            after = (
                afterParent.GetID() if afterParent else None,
                node.GetAttribute("DENTOBOT.JawOwner"),
                node.GetAttribute("DENTOBOT.PlanningPoseFingerprint"),
            )
            if after != before:
                changed.append(node.GetID())
        return changed

    def rebuildCaseFoundationDisplayVolumes(self, parameterNode) -> tuple[object, object]:
        source = parameterNode.inputVolume
        segmentation = parameterNode.teethSegmentation
        if not source or not segmentation:
            raise ValueError(_("A source CBCT and reviewed segmentation are required."))
        groups = self.step6CaseJawSegmentIds(segmentation)
        lowerIds = groups["lower"]
        if not lowerIds:
            raise ValueError(_("The reviewed segmentation has no moving lower jaw."))
        sourceArray = np.asarray(slicer.util.arrayFromVolume(source))
        lowerMask = np.zeros(sourceArray.shape, dtype=bool)
        for segmentId in lowerIds:
            mask = np.asarray(
                slicer.util.arrayFromSegmentBinaryLabelmap(segmentation, segmentId)
            )
            if mask.shape != sourceArray.shape:
                raise ValueError(_("The reviewed segmentation does not share the source CBCT grid."))
            lowerMask |= mask.astype(bool)
        fill = float(np.min(sourceArray))
        fixedArray = np.array(sourceArray, copy=True)
        fixedArray[lowerMask] = fill
        movingArray = np.full(sourceArray.shape, fill, dtype=sourceArray.dtype)
        movingArray[lowerMask] = sourceArray[lowerMask]
        for field, name, array, transform in (
            ("caseFoundationFixedUpperVolume", "[Case Foundation] Fixed Upper CBCT", fixedArray, None),
            ("caseFoundationMovingLowerVolume", "[Case Foundation] Moving Lower CBCT", movingArray, parameterNode.step6CaseJawTransform),
        ):
            old = getattr(parameterNode, field)
            if old and slicer.mrmlScene.IsNodePresent(old):
                slicer.mrmlScene.RemoveNode(old)
            node = slicer.modules.volumes.logic().CloneVolumeGeneric(slicer.mrmlScene, source, name, False)
            slicer.util.updateVolumeFromArray(node, array)
            node.SetSaveWithScene(False)
            node.SetAttribute("DENTOBOT.VolumeRole", field)
            node.SetAttribute("DENTOBOT.Transient", "true")
            node.SetAndObserveTransformNodeID(transform.GetID() if transform else None)
            setattr(parameterNode, field, node)
        return (
            parameterNode.caseFoundationFixedUpperVolume,
            parameterNode.caseFoundationMovingLowerVolume,
        )
