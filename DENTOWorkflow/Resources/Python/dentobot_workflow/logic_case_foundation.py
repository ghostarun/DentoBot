"""Case Foundation identity, opened CBCT displays, and readiness gates."""

from __future__ import annotations

import time

from .runtime import *
from . import jaw_frame


def _canonical_case_foundation_landmark_positions(
    current_positions,
    saved_environment_json,
    current_landmarks_fingerprint,
    committed_pose_fingerprint,
) -> tuple:
    current = tuple(current_positions)
    if (
        not isinstance(saved_environment_json, str)
        or not current_landmarks_fingerprint
        or not committed_pose_fingerprint
    ):
        return current
    try:
        environment = json.loads(saved_environment_json)
        if not isinstance(environment, dict):
            return current
        saved_positions = environment.get("landmark_positions_ras_mm")
        if not isinstance(saved_positions, list) or len(saved_positions) != 12:
            return current
        if (
            environment.get("jaw_landmarks_fingerprint") != current_landmarks_fingerprint
            or environment.get("planning_pose_fingerprint") != committed_pose_fingerprint
        ):
            return current
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in saved_positions
        ):
            return current
        saved = tuple(float(value) for value in saved_positions)
        current_values = tuple(float(value) for value in current)
        if len(current_values) != 12 or not all(
            math.isfinite(value) for value in (*current_values, *saved)
        ):
            return current
        if any(
            abs(current_value - saved_value) > 1e-9
            or round(current_value, 9) != round(saved_value, 9)
            for current_value, saved_value in zip(current_values, saved)
        ):
            return current
        return saved
    except (TypeError, ValueError, OverflowError, RecursionError):
        return current


class CaseFoundationLogicMixin:
    CASE_FOUNDATION_HINGE_SCHEMA = "VirtualOpenMouthArticulatorV1"

    @classmethod
    def caseFoundationArticulatorConfig(cls):
        from dentobot_workflow.virtual_open_mouth_articulator import (
            CASE_FOUNDATION_ARTICULATOR_CONFIG,
        )

        return CASE_FOUNDATION_ARTICULATOR_CONFIG

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
            started = time.monotonic()
            cache[key] = builder()
            elapsed = time.monotonic() - started
            if elapsed >= 1.0:
                logging.info("DENTOBOT fingerprint %s rebuilt in %.3fs", key[0], elapsed)
                print("DENTOBOT_FINGERPRINT_BUILD", key[0], f"{elapsed:.3f}", flush=True)
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
                    "sha256": hashlib.sha256(array.data).hexdigest(),
                    "ijkToRas": geometry,
                }
            )

        return self._cachedCaseFoundationFingerprint(
            key,
            build,
        )

    @staticmethod
    def _caseFoundationSegmentBinaryArray(segmentationNode, segmentId):
        reference = segmentationNode.GetNodeReference(
            slicer.vtkMRMLSegmentationNode.GetReferenceImageGeometryReferenceRole()
        )
        referenceImage = reference.GetImageData() if reference else None
        if (
            referenceImage
            and referenceImage.GetPointData().GetScalars()
            and not segmentationNode.GetParentTransformNode()
            and not reference.GetParentTransformNode()
        ):
            internal = segmentationNode.GetBinaryLabelmapInternalRepresentation(segmentId)
            scalars = internal.GetPointData().GetScalars() if internal else None
            if scalars:
                referenceMatrix = vtk.vtkMatrix4x4()
                reference.GetIJKToRASMatrix(referenceMatrix)
                matrix = vtk.vtkMatrix4x4()
                internal.GetImageToWorldMatrix(matrix)
                extent = internal.GetExtent()
                referenceExtent = referenceImage.GetExtent()
                if all(
                    abs(matrix.GetElement(row, column) - referenceMatrix.GetElement(row, column)) <= 1e-8
                    for row in range(4) for column in range(4)
                ) and all(
                    referenceExtent[index] <= extent[index]
                    and extent[index + 1] <= referenceExtent[index + 1]
                    for index in (0, 2, 4)
                ):
                    internalArray = vtk_to_numpy(scalars).reshape(tuple(reversed(internal.GetDimensions())))
                    # Slicer's single-segment labelmap export emits VTK_SHORT with foreground 1.
                    array = np.zeros(tuple(reversed(referenceImage.GetDimensions())), dtype=np.int16)
                    slices = tuple(
                        slice(extent[index] - referenceExtent[index], extent[index + 1] - referenceExtent[index] + 1)
                        for index in (4, 2, 0)
                    )
                    label = segmentationNode.GetSegmentation().GetSegment(segmentId).GetLabelValue()
                    array[slices] = internalArray == label
                    return array
        return np.ascontiguousarray(
            slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, segmentId)
        )

    def caseFoundationSourceSegmentationFingerprint(self, segmentationNode) -> str:
        if not segmentationNode or not segmentationNode.GetSegmentation():
            return ""
        segmentation = segmentationNode.GetSegmentation()

        def input_key() -> tuple:
            referenceGeometry = str(
                segmentation.GetConversionParameter("Reference image geometry") or ""
            )
            metricsText = str(
                segmentationNode.GetAttribute("DENTOBOT.SegmentMetricsJson") or ""
            )
            # A restore invokes this input check hundreds of times. Reuse only
            # the pure text digest within that transaction, with exact text equality.
            metricsCache = getattr(self, "_caseBundleMetricsDigestCache", None)
            if metricsCache is not None and metricsCache.get("text") == metricsText:
                metricsDigest = metricsCache["digest"]
            else:
                try:
                    stableMetrics = canonical_json(json.loads(metricsText))
                except (TypeError, ValueError, json.JSONDecodeError):
                    stableMetrics = metricsText
                metricsDigest = hashlib.sha256(stableMetrics.encode("utf-8")).hexdigest()
                if metricsCache is not None:
                    metricsCache.clear()
                    metricsCache.update(text=metricsText, digest=metricsDigest)
            segmentIds = vtk.vtkStringArray()
            segmentation.GetSegmentIDs(segmentIds)
            segmentInputs = []
            for index in range(segmentIds.GetNumberOfValues()):
                segmentId = segmentIds.GetValue(index)
                segment = segmentation.GetSegment(segmentId)
                internal = segmentationNode.GetBinaryLabelmapInternalRepresentation(
                    segmentId
                )
                segmentInputs.append(
                    (
                        segmentId,
                        int(segment.GetMTime()) if segment else 0,
                        str(segment.GetName() or "") if segment else "",
                        int(internal.GetMTime()) if internal else 0,
                    )
                )
            return (
                "segmentation",
                segmentationNode.GetID(),
                segmentation.GetMTime(),
                referenceGeometry,
                metricsDigest,
                tuple(segmentInputs),
            )

        key = input_key()

        def build() -> str:
            records = []
            for review in self.getSegmentationReviewRecords(segmentationNode):
                segmentId = str(review.get("segmentId") or "")
                if not segmentId:
                    continue
                try:
                    array = self._caseFoundationSegmentBinaryArray(segmentationNode, segmentId)
                except RuntimeError:
                    return ""
                records.append(
                    {
                        "id": segmentId,
                        # The source fingerprint predates the semantic registry.
                        # Keep its legacy descriptor projection stable while
                        # semantic identity remains a separate planning gate.
                        "review": {
                            "segmentId": segmentId,
                            **self.describeSegmentForReview(
                                str(review.get("sourceName") or "")
                            ),
                        },
                        "shape": tuple(int(value) for value in array.shape),
                        "sha256": hashlib.sha256(array.data).hexdigest(),
                    }
                )
            return fingerprint(
                {
                    "referenceGeometry": key[3],
                    "segments": records,
                }
            ) if records else ""

        value = self._cachedCaseFoundationFingerprint(key, build)
        after = input_key()
        if after != key:
            logging.info("DENTOBOT source fingerprint inputs changed during export")
            print("DENTOBOT_FINGERPRINT_INPUTS_CHANGED", flush=True)
        return value

    def buildCaseFoundationSnapshot(self, parameterNode):
        volume = parameterNode.inputVolume
        segmentation = parameterNode.teethSegmentation
        transform = parameterNode.step6CaseJawTransform
        landmarks = parameterNode.step6CaseJawLandmarks
        base = parameterNode.robotBaseTransform
        positions = ()
        landmarksFingerprint = (
            self._step6CaseJawLandmarksFingerprint(landmarks)
            if self.isStep6CaseJawLandmarksNode(landmarks) else ""
        )
        if (
            self.isStep6CaseJawLandmarksNode(landmarks)
            and landmarks.GetNumberOfDefinedControlPoints() == 4
        ):
            positions = tuple(
                float(value)
                for point in self.step6CaseJawLandmarkPositions(landmarks)
                for value in point
            )
            positions = _canonical_case_foundation_landmark_positions(
                positions,
                parameterNode.step6EnvironmentJson,
                landmarksFingerprint,
                str(transform.GetAttribute("DENTOBOT.PlanningPoseFingerprint") or "")
                if transform else "",
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
            jaw_landmarks_fingerprint=landmarksFingerprint,
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
            if not self.isStep6CaseJawTransformNode(transform):
                pose = component(
                    False,
                    "STALE_MOUTH_OPENING",
                    _(
                        "Commit the AUTO Case Foundation open-mouth from the "
                        "reviewed segmentation, or optionally edit landmarks."
                    ),
                )
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
                legacy_schema = str(transform.GetAttribute("DENTOBOT.HingeModelSchema") or "")
                if legacy_schema in {
                    "",
                    "AnatomyDirectedPureTMJHingeRotationV2",
                }:
                    pose = component(
                        False,
                        "LEGACY_JAW_OPENING_UNSUPPORTED",
                        _("Legacy jaw-opening state unsupported; regeneration required."),
                    )
                else:
                    pose = component(
                        False,
                        "LEGACY_UNVERIFIED",
                        _("Review and promote the legacy mouth opening to the current Case Foundation."),
                    )
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
            "branch_foundation_fingerprint": self.caseFoundationBranchFingerprint(parameterNode, snapshot),
            "base_setup_fingerprint": snapshot.base_setup_fingerprint,
            "foundation_fingerprint": snapshot.foundation_fingerprint,
        }

    def requireCaseFoundationPose(self, parameterNode) -> dict[str, object]:
        result = self.evaluateCaseFoundationEligibility(parameterNode)
        if not result["pose"]["eligible"]:
            raise ValueError(result["pose"]["message"])
        return result

    def _caseFoundationForceManualAxis(self, parameterNode) -> bool:
        landmarks = parameterNode.step6CaseJawLandmarks
        return bool(
            landmarks
            and self.isStep6CaseJawLandmarksNode(landmarks)
            and str(landmarks.GetAttribute("DENTOBOT.ForceManualCondylarAxis") or "")
            .strip()
            .lower()
            in {"1", "true", "yes"}
        )

    def _solveCaseFoundationOpeningArticulator(
        self,
        parameterNode,
        targetGapMm: float,
    ):
        from dentobot_workflow.virtual_open_mouth_articulator import (
            OPEN_MOUTH_MODEL_VERSION,
            solve_auto_opening,
            transform_point,
        )

        force_manual = self._caseFoundationForceManualAxis(parameterNode)
        extraction_error = ""
        proposed_left = None
        proposed_right = None
        if force_manual:
            left, right, upper, lower = self.step6CaseJawLandmarkPositions(
                parameterNode.step6CaseJawLandmarks
            )
            self.validateStep6CaseJawLandmarkAnatomy(parameterNode)
            frame = None
            lateral_left, lateral_right = self.step6LateralArchReferencePoints(
                parameterNode
            )
            try:
                proposed_left, proposed_right, _confidence = (
                    self.step6EstimatePatientCondyleCentres(
                        parameterNode,
                        left,
                        right,
                        lower,
                    )
                )
            except ValueError as exc:
                extraction_error = str(exc)
            result = solve_auto_opening(
                upper_incisor_mm=upper,
                lower_incisor_mm=lower,
                target_opening_mm=float(targetGapMm),
                manual_condyle_left_mm=left,
                manual_condyle_right_mm=right,
                segmented_condyle_left_mm=proposed_left,
                segmented_condyle_right_mm=proposed_right,
                lateral_arch_left_mm=lateral_left,
                lateral_arch_right_mm=lateral_right,
                force_manual_axis=True,
                config=self.caseFoundationArticulatorConfig(),
            )
            result.provenance["landmarkSource"] = "MANUAL_OVERRIDE"
            result.provenance["manualCondyleLeftRasMm"] = left.tolist()
            result.provenance["manualCondyleRightRasMm"] = right.tolist()
        else:
            proposal = self.proposeCaseFoundationArticulatorInputs(parameterNode)
            upper = proposal["upperIncisorMm"]
            lower = proposal["lowerIncisorMm"]
            proposed_left = proposal["segmentedCondyleLeftMm"]
            proposed_right = proposal["segmentedCondyleRightMm"]
            extraction_error = str(proposal.get("segmentedExtractionError") or "")
            result = solve_auto_opening(
                upper_incisor_mm=upper,
                lower_incisor_mm=lower,
                target_opening_mm=float(targetGapMm),
                segmented_condyle_left_mm=proposed_left,
                segmented_condyle_right_mm=proposed_right,
                lateral_arch_left_mm=proposal["lateralLeftMm"],
                lateral_arch_right_mm=proposal["lateralRightMm"],
                dental_frame=proposal["dentalFrame"],
                force_manual_axis=False,
                config=self.caseFoundationArticulatorConfig(),
            )
            result.provenance["landmarkSource"] = "AUTO"
            result.provenance["autoUpperIncisorRasMm"] = np.asarray(upper).tolist()
            result.provenance["autoLowerIncisorRasMm"] = np.asarray(lower).tolist()
            result.provenance["autoLateralLeftRasMm"] = np.asarray(
                proposal["lateralLeftMm"]
            ).tolist()
            result.provenance["autoLateralRightRasMm"] = np.asarray(
                proposal["lateralRightMm"]
            ).tolist()
        if extraction_error:
            result.provenance.setdefault("hingeResolution", {})
            if isinstance(result.provenance["hingeResolution"], dict):
                result.provenance["hingeResolution"]["segmentedExtractionError"] = (
                    extraction_error
                )
        if proposed_left is not None and proposed_right is not None:
            result.provenance["segmentedCondyleLeftRasMm"] = np.asarray(
                proposed_left
            ).tolist()
            result.provenance["segmentedCondyleRightRasMm"] = np.asarray(
                proposed_right
            ).tolist()
        opened_lower = transform_point(result.matrix_world_ras, lower)
        result.provenance["openMouthModelVersion"] = OPEN_MOUTH_MODEL_VERSION
        return result, upper, opened_lower

    def previewCaseFoundationOpening(
        self,
        parameterNode,
        targetGapMm: float,
    ) -> dict[str, object]:
        transform = parameterNode.step6CaseJawTransform
        if not self.isStep6CaseJawTransformNode(transform):
            raise ValueError(_("Commit the initial Case Foundation opening first."))
        result, upper, openedLower = self._solveCaseFoundationOpeningArticulator(
            parameterNode,
            float(targetGapMm),
        )
        transform.SetMatrixTransformToParent(
            self._vtkFromNumpyMatrix(result.matrix_world_ras)
        )
        gapLine = parameterNode.step6CaseJawGapLine
        if gapLine and gapLine.IsA("vtkMRMLMarkupsLineNode"):
            gapLine.SetNthControlPointPositionWorld(0, *upper)
            gapLine.SetNthControlPointPositionWorld(1, *openedLower)
        parameterNode.caseFoundationPreviewUncommitted = True
        transform.SetAttribute(
            "DENTOBOT.ArticulatorProvenanceJson",
            canonical_json(result.provenance),
        )
        return {
            "angleDeg": float(result.theta_deg),
            "gapMm": float(result.achieved_opening_mm),
            "openedLowerIncisorRas": tuple(float(value) for value in openedLower),
            "openingParameterQ": float(result.q),
            "condylarTranslationMm": float(result.translation_mm),
            "hingeSource": result.hinge_source.value,
            "articulatorProvenance": result.provenance,
        }

    def probeCaseFoundationArticulator(
        self,
        parameterNode,
        targetGapMm: float | None = None,
    ) -> dict[str, object]:
        """Dry-run the virtual articulator for manual GUI testing (no scene commit)."""

        target = float(
            targetGapMm
            if targetGapMm is not None
            else parameterNode.step6CaseJawTargetGapMm
        )
        result, _upper, _opened_lower = self._solveCaseFoundationOpeningArticulator(
            parameterNode,
            target,
        )
        resolution = result.provenance.get("hingeResolution") or {}
        if not isinstance(resolution, dict):
            resolution = {}
        return {
            "targetGapMm": target,
            "achievedGapMm": float(result.achieved_opening_mm),
            "hingeSource": result.hinge_source.value,
            "axisConfidence": float(result.axis_confidence),
            "openingParameterQ": float(result.q),
            "thetaDeg": float(result.theta_deg),
            "condylarTranslationMm": float(result.translation_mm),
            "closedGapMm": float(result.closed_gap_mm),
            "profileMaxGapMm": float(
                result.provenance.get("profile_max_gap_mm", 0.0)
            ),
            "selection": str(resolution.get("selection") or result.hinge_source.value),
            "patientRejected": resolution.get("patientRejected"),
            "segmentedComparison": resolution.get("segmentedComparison"),
            "archScale": resolution.get("archScale"),
            "segmentedExtractionError": resolution.get("segmentedExtractionError"),
            "articulatorProvenance": result.provenance,
        }

    def _invalidateCaseFoundationPoseDependents(
        self, parameterNode, reason: str, *, openingOnly: bool = False
    ) -> None:
        """Invalidate everything bound to the Case Foundation pose.

        ``openingOnly``: only the mouth opening changed. PreparedBranches move
        rigidly with their jaw and every Step 4C/5C check is same-jaw, so Step 5C
        verification is kept; Step 6 task/Base/workspace state is still
        invalidated because it depends on the opened pose (S6-MULTI-JAW-STALE-01).
        """

        for model in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not openingOnly and self.isFinalPrintableTemplateModelNode(model):
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
        self._staleVirtualForeheadPrior(parameterNode, reason)

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

    def _staleVirtualForeheadPrior(self, parameterNode, reason: str) -> None:
        for node in (
            parameterNode.robotForeheadProxyModel,
            parameterNode.robotMountPlane,
        ):
            if node is None:
                continue
            if str(node.GetAttribute("DENTOBOT.PlacementAuthority") or "") != "VirtualForeheadPriorV1":
                continue
            node.SetAttribute("DENTOBOT.GeometryState", "Stale")
            node.SetAttribute("DENTOBOT.StaleReason", str(reason))

    def step6BasePlacementRevisionHighWater(self, parameterNode) -> int:
        """Highest Base revision ever issued for this case.

        The mark is persisted with the revision.  A case saved before the field existed has no mark, so the
        mark defaults to the current revision.
        """
        return max(
            int(parameterNode.step6BasePlacementRevision),
            int(getattr(parameterNode, "step6BasePlacementHighWater", 0) or 0),
        )

    def recordStep6BasePlacementRevision(self, parameterNode, revision: int) -> None:
        """Set the Base revision; the high-water mark is raised to it and never lowered.

        The advisor's exact restore reinstates an earlier revision through this owner, so a number issued during
        the search is never handed out again by a later real edit.
        """
        revision = int(revision)
        high_water = max(revision, self.step6BasePlacementRevisionHighWater(parameterNode))
        parameterNode.step6BasePlacementRevision = revision
        parameterNode.step6BasePlacementHighWater = high_water

    def issueStep6BasePlacementRevision(self, parameterNode) -> int:
        """Issue the next Base revision: one above every revision ever issued, so no number is reused."""
        issued = self.step6BasePlacementRevisionHighWater(parameterNode) + 1
        self.recordStep6BasePlacementRevision(parameterNode, issued)
        return issued

    def restoreStep6BaseIdentity(self, parameterNode, snapshot) -> None:
        """Reinstate the exact accepted Base identity captured before an advisor search.

        Only the advisor's exact-restore path calls this, after the production setBasePose owner has put the
        captured pose back.  It writes the captured lock, status, source, authority, foundation/profile
        attributes and revision WITHOUT advancing the revision, then refuses unless the resulting Base
        fingerprint equals the captured one.  Any other pose or binding stays a normal, revision-bumping edit.
        """

        base_transform = parameterNode.robotBaseTransform
        if not self.isRobotBaseTransformNode(base_transform):
            raise ValueError(_("Load the local Step 6 robot before restoring its base."))
        if not bool(snapshot.get("locked")):
            raise ValueError(_("The captured Base was not locked; its identity cannot be reinstated."))
        status = normalize_base_status(str(snapshot.get("status") or ""))
        if status not in {
            BasePlacementStatus.PROVISIONAL_LOCKED,
            BasePlacementStatus.REGISTERED_LOCKED,
        }:
            raise ValueError(_("The captured Base status is not a reviewed locked status."))
        trace = [self._baseIdentityCheckpoint(parameterNode, base_transform, "before-restore-writes")]
        was_modifying = parameterNode.StartModify()
        try:
            parameterNode.robotBaseMountLocked = True
            parameterNode.step6BasePlacementStatus = status.value
            parameterNode.step6BasePlacementSource = str(snapshot.get("source") or "")
            self.recordStep6BasePlacementRevision(parameterNode, int(snapshot["revision"]))
        finally:
            parameterNode.EndModify(was_modifying)
        trace.append(self._baseIdentityCheckpoint(parameterNode, base_transform, "after-lock-block"))
        base_transform.SetAttribute(
            self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
            str(snapshot.get("authority") or ""),
        )
        base_transform.SetAttribute(
            "DENTOBOT.CaseFoundationFingerprint",
            str(snapshot.get("case_foundation_fingerprint") or ""),
        )
        base_transform.SetAttribute(
            "DENTOBOT.RobotProfileFingerprint",
            str(snapshot.get("robot_profile_fingerprint") or ""),
        )
        base_transform.SetAttribute(
            "DENTOBOT.PlacementWarning",
            str(snapshot.get("placement_warning") or "") or None,
        )
        trace.append(self._baseIdentityCheckpoint(parameterNode, base_transform, "after-attribute-writes"))
        self._applyRobotBaseMountInteractionState(parameterNode, True)
        trace.append(self._baseIdentityCheckpoint(parameterNode, base_transform, "after-interaction-state"))
        if self.robotBaseFingerprint(parameterNode) != str(
            snapshot.get("base_fingerprint") or ""
        ):
            trace.append(self._baseIdentityCheckpoint(parameterNode, base_transform, "at-fingerprint-check"))
            error = ValueError(
                _("The reinstated Base does not match the captured Base identity.")
                + " " + self._baseIdentityDifferences(parameterNode, base_transform, snapshot)
            )
            error.base_identity_trace = trace
            raise error

    def _baseIdentityCheckpoint(self, parameterNode, base_transform, label: str) -> dict:
        """Read-only snapshot of every field the Base fingerprint hashes, for the restore trace."""
        matrix = self._worldMatrixFromTransform(base_transform)
        return {
            "label": label,
            "locked": bool(parameterNode.robotBaseMountLocked),
            "status": str(normalize_base_status(parameterNode.step6BasePlacementStatus).value),
            "source": str(parameterNode.step6BasePlacementSource or ""),
            "revision": int(parameterNode.step6BasePlacementRevision),
            "authority": str(base_transform.GetAttribute(self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE) or ""),
            "pose_9dp": [round(float(matrix.GetElement(row, column)), 9) for row in range(4) for column in range(4)],
        }

    def _baseIdentityDifferences(self, parameterNode, base_transform, snapshot) -> str:
        """Names each hashed field that differs from the captured identity (bounded; for the operator and evidence)."""
        live = self._baseIdentityCheckpoint(parameterNode, base_transform, "at-fingerprint-check")
        captured_status = str(normalize_base_status(snapshot.get("status") or "").value)
        differing = []
        if live["status"] != captured_status:
            differing.append(f"status {live['status']} != captured {captured_status}")
        if live["revision"] != int(snapshot.get("revision") or 0):
            differing.append(f"sourceRevision {live['revision']} != captured {int(snapshot.get('revision') or 0)}")
        if live["source"] != str(snapshot.get("source") or ""):
            differing.append(f"source {live['source']} != captured {snapshot.get('source')}")
        if live["authority"] != str(snapshot.get("authority") or ""):
            differing.append(f"authority {live['authority']} != captured {snapshot.get('authority')}")
        captured_matrix = [round(float(value), 9) for value in (snapshot.get("matrix") or [])]
        moved = sum(1 for a, b in zip(live["pose_9dp"], captured_matrix) if a != b)
        if len(captured_matrix) != 16 or moved:
            differing.append(f"pose elements differing at 9 dp: {moved}")
        return ("Differs: " + "; ".join(differing) + ".") if differing else "All hashed inputs equal the captured values."

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
            self.issueStep6BasePlacementRevision(parameterNode)
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
            openingOnly=True,
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

    # ---- owning-jaw provenance frame (S6-MULTI-JAW-STALE-01) -------------------
    def nodeJawOwner(self, parameterNode, node) -> str:
        owner = str(node.GetAttribute("DENTOBOT.JawOwner") or "")
        if owner in {"MovingLower", "FixedUpper"}:
            return owner
        return self._targetJawOwner(
            parameterNode,
            str(
                node.GetAttribute("DENTOBOT.TargetSegmentID")
                or node.GetAttribute("DENTOBOT.TargetSegmentId")  # Step 4C dock nodes
                or node.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE)
                or ""
            ),
        )

    def owningJawWorldMatrix(self, parameterNode, node):
        """Current world matrix of the jaw owning ``node``; None for the fixed upper jaw."""

        if self.nodeJawOwner(parameterNode, node) != "MovingLower":
            return None
        transform = parameterNode.step6CaseJawTransform
        if transform is None:
            raise ValueError(_("A mandibular node requires the Case Foundation jaw transform."))
        matrix = vtk.vtkMatrix4x4()
        transform.GetMatrixTransformToWorld(matrix)
        return [[matrix.GetElement(row, column) for column in range(4)] for row in range(4)]

    def owningJawFrameControlPoint(self, parameterNode, node, index: int) -> list[float]:
        """A control point in its owning-jaw frame (closed-mouth pose for the lower jaw).

        Nodes parented to the jaw transform return their local coordinates exactly,
        so the value never depends on the current mouth opening.
        """

        point = [0.0, 0.0, 0.0]
        if self.nodeJawOwner(parameterNode, node) != "MovingLower":
            node.GetNthControlPointPositionWorld(index, point)
            return [float(value) for value in point]
        transform = parameterNode.step6CaseJawTransform
        if transform is not None and node.GetParentTransformNode() is transform:
            node.GetNthControlPointPosition(index, point)
            return [float(value) for value in point]
        node.GetNthControlPointPositionWorld(index, point)
        return jaw_frame.to_owning_jaw_frame(
            {"originRas": point}, self.owningJawWorldMatrix(parameterNode, node)
        )["originRas"]

    def caseFoundationBranchFingerprint(self, parameterNode, snapshot=None) -> str:
        """Case Foundation identity a PreparedBranch binds to; the mouth opening is excluded."""

        snapshot = snapshot or self.buildCaseFoundationSnapshot(parameterNode)
        try:
            preparation = json.loads(
                str(parameterNode.step6CaseJawPreparationJson or "") or "{}"
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            preparation = {}
        return jaw_frame.branch_foundation_fingerprint(snapshot.to_dict(), preparation)

    def caseFoundationPlanningSurfaceCopy(
        self,
        parameterNode,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> vtk.vtkPolyData:
        """Return authoritative anatomy in the current opened planning frame."""

        surface = self._getClosedSurfaceWorldCopy(segmentationNode, segmentId)
        if (
            segmentationNode is not parameterNode.teethSegmentation
            or self._targetJawOwner(parameterNode, segmentId) != "MovingLower"
        ):
            return surface
        self.requireCaseFoundationPose(parameterNode)
        return self._step6CaseJawPolydataWorld(parameterNode, surface)

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
            normal = (
                tuple(node.GetNormalWorld())
                if node.IsA("vtkMRMLMarkupsPlaneNode") else None
            )
            positions = []
            for index in range(node.GetNumberOfControlPoints()):
                point = [0.0, 0.0, 0.0]
                node.GetNthControlPointPositionWorld(index, point)
                positions.append(tuple(point))
            node.SetAndObserveTransformNodeID(parent.GetID() if parent else None)
            for index, point in enumerate(positions):
                node.SetNthControlPointPositionWorld(index, *point)
            if normal is not None:
                node.SetNormalWorld(normal)
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
        node.SetAttribute(
            jaw_frame.BRANCH_FOUNDATION_ATTRIBUTE,
            foundation["branch_foundation_fingerprint"],
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
            mask = self._caseFoundationSegmentBinaryArray(segmentation, segmentId)
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
