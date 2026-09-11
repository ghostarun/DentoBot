"""Extracted robot scene and jaw setup methods; public APIs remain on RobotWidgetMixin."""

from __future__ import annotations

from .runtime import *


class RobotSceneWidgetMixin:
    def _captureCaseFoundationSessionSnapshot(self) -> bool:
        if not self._parameterNode or not self.logic:
            return False
        eligibility = self.logic.evaluateCaseFoundationEligibility(
            self._parameterNode
        )
        if not (
            eligibility["pose"]["eligible"]
            and eligibility["base"]["eligible"]
        ):
            return False
        environment = self.logic.buildCaseFoundationSnapshot(self._parameterNode)
        landmarks = self._parameterNode.step6CaseJawLandmarks
        self._caseFoundationSnapshot = {
            "sourceVolumeFingerprint": environment.source_volume_fingerprint,
            "sourceSegmentationFingerprint": environment.source_segmentation_fingerprint,
            "robotProfileFingerprint": environment.robot_profile_fingerprint,
            "landmarkPositionsRasMm": list(environment.landmark_positions_ras_mm),
            "landmarkEvidenceJson": str(
                landmarks.GetAttribute("DENTOBOT.SurfaceEvidenceJson") or ""
            ),
            "targetGapMm": environment.mouth_gap_mm,
            "openingRevision": environment.opening_revision,
            "baseMatrix": list(environment.base_matrix),
            "baseStatus": environment.base_status,
            "baseAuthority": environment.base_authority,
            "baseRevision": environment.base_revision,
        }
        return True

    def _tryApplySessionFoundation(self) -> bool:
        snapshot = self._caseFoundationSnapshot
        if (
            not snapshot
            or self._applyingSessionFoundation
            or not self._parameterNode
            or not self.logic
            or self._parameterNode.step6CaseJawTransform
            or not self._parameterNode.inputVolume
            or not self._parameterNode.teethSegmentation
            or self.logic.getSegmentationReviewState(
                self._parameterNode.teethSegmentation
            )
            != "Reviewed"
        ):
            return False
        self._applyingSessionFoundation = True
        try:
            volumeFingerprint = self.logic.caseFoundationSourceVolumeFingerprint(
                self._parameterNode.inputVolume
            )
            segmentationFingerprint = (
                self.logic.caseFoundationSourceSegmentationFingerprint(
                    self._parameterNode.teethSegmentation
                )
            )
            robotFingerprint = str(
                self.logic.caseBundleRobotProfile().get("identitySha256") or ""
            )
            if (
                volumeFingerprint != snapshot["sourceVolumeFingerprint"]
                or segmentationFingerprint
                != snapshot["sourceSegmentationFingerprint"]
                or robotFingerprint != snapshot["robotProfileFingerprint"]
            ):
                self.ui.step6CaseJawOpeningStatusLabel.text = _(
                    "Session Foundation not applied. Loaded source identities: "
                    "CBCT %1 / segmentation %2; cached identities: CBCT %3 / "
                    "segmentation %4."
                ).replace("%1", volumeFingerprint[:12]).replace(
                    "%2", segmentationFingerprint[:12]
                ).replace(
                    "%3", str(snapshot["sourceVolumeFingerprint"])[:12]
                ).replace(
                    "%4", str(snapshot["sourceSegmentationFingerprint"])[:12]
                )
                self.ui.step6CaseJawOpeningStatusLabel.styleSheet = "color: #b36b00;"
                return False
            values = tuple(float(value) for value in snapshot["landmarkPositionsRasMm"])
            if len(values) != 12:
                return False
            landmarks = self.logic.ensureStep6CaseJawLandmarksNode(None)
            landmarks.RemoveAllControlPoints()
            for index in range(4):
                point = values[index * 3:index * 3 + 3]
                landmarks.AddControlPointWorld(vtk.vtkVector3d(*point))
            landmarks.SetAttribute(
                "DENTOBOT.SurfaceEvidenceJson",
                str(snapshot["landmarkEvidenceJson"]),
            )
            self._parameterNode.step6CaseJawLandmarks = landmarks
            self._parameterNode.step6CaseJawTargetGapMm = float(
                snapshot["targetGapMm"]
            )
            self.logic.createOrUpdateStep6CaseJawOpening(self._parameterNode)
            self._parameterNode.caseFoundationOpeningRevision = int(
                snapshot["openingRevision"]
            )
            preparation = self.logic._step6CaseJawPreparationRecord(
                self._parameterNode
            )
            preparation["openingRevision"] = int(snapshot["openingRevision"])
            self._parameterNode.step6CaseJawPreparationJson = canonical_json(
                preparation
            )
            environment = self.logic.buildCaseFoundationSnapshot(
                self._parameterNode
            )
            transform = self._parameterNode.step6CaseJawTransform
            transform.SetAttribute(
                "DENTOBOT.PlanningPoseFingerprint",
                environment.planning_pose_fingerprint,
            )
            base = self.logic.ensureRobotBaseTransform(None)
            base.SetMatrixTransformToParent(
                self.logic._vtkFromNumpyMatrix(
                    np.asarray(snapshot["baseMatrix"], dtype=float).reshape(4, 4)
                )
            )
            base.SetAttribute(
                self.logic.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
                str(snapshot["baseAuthority"]),
            )
            base.SetAttribute(
                "DENTOBOT.CaseFoundationFingerprint",
                environment.planning_pose_fingerprint,
            )
            base.SetAttribute(
                "DENTOBOT.RobotProfileFingerprint",
                robotFingerprint,
            )
            self._parameterNode.robotBaseTransform = base
            self._parameterNode.robotBaseMountLocked = True
            self._parameterNode.step6BasePlacementStatus = str(
                snapshot["baseStatus"]
            )
            self._parameterNode.step6BasePlacementSource = MANUAL_SIMULATION_BASE_SOURCE
            self._parameterNode.step6BasePlacementRevision = int(
                snapshot["baseRevision"]
            )
            self.logic._applyRobotBaseMountInteractionState(
                self._parameterNode, True
            )
            return True
        finally:
            self._applyingSessionFoundation = False

    def _clearRobotPlacement(self) -> None:
        if not hasattr(self, "ui"):
            return
        self._bindRobotPlacementNodes(None, None)
        self._disableRobotKeyboardShortcuts()
        self._updatingRobotPlacementUI = True
        try:
            self.ui.robotBaseTransformSelector.setCurrentNode(None)
            self.ui.robotMountPlaneSelector.setCurrentNode(None)
            self.ui.robotPlacementStatusLabel.text = _(
                "Load the seven articulated robot meshes to begin placement."
            )
            self.ui.robotPlacementStatusLabel.styleSheet = "color: #b36b00;"
        finally:
            self._updatingRobotPlacementUI = False

    def _bindStep6CaseJawLandmarksNode(
        self,
        landmarksNode: vtkMRMLMarkupsFiducialNode | None,
    ) -> None:
        if landmarksNode is self._step6CaseJawLandmarksNode:
            return
        if self._step6CaseJawLandmarksNode:
            for landmarkEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.removeObserver(
                    self._step6CaseJawLandmarksNode,
                    landmarkEvent,
                    self._onStep6CaseJawLandmarksModified,
                )
        self._step6CaseJawLandmarksNode = landmarksNode
        if landmarksNode:
            for landmarkEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.addObserver(
                    landmarksNode,
                    landmarkEvent,
                    self._onStep6CaseJawLandmarksModified,
                )

    def _markStep6CaseJawOpeningStale(self, reason: str) -> None:
        if not self._parameterNode or not self.logic:
            return
        transform = self._parameterNode.step6CaseJawTransform
        if self.logic.isStep6CaseJawTransformNode(transform):
            transform.SetAttribute("DENTOBOT.GeometryState", "Stale")
            transform.SetAttribute("DENTOBOT.StaleReason", reason)
        model = self._parameterNode.step6OpenedLowerJawModel
        if self.logic.isStep6OpenedLowerJawModelNode(model):
            model.SetAttribute("DENTOBOT.GeometryState", "Stale")
        self.logic._invalidateCaseFoundationPoseDependents(
            self._parameterNode,
            reason,
        )
        self._step6MotionPlan = None
        if self._robotWorkflowFacade:
            self._robotWorkflowFacade.clearTransientState()

    def _onStep6CaseJawLandmarksModified(self, caller=None, event=None) -> None:
        del caller
        if (
            self._updatingStep6CaseJawLandmarks
            or not self._parameterNode
            or not self.logic
        ):
            return
        node = self._step6CaseJawLandmarksNode
        if not node or not self.logic.isStep6CaseJawLandmarksNode(node):
            return
        acceptedEvidence = None
        self._updatingStep6CaseJawLandmarks = True
        try:
            # Markups event ordering is not stable across interaction paths and
            # Slicer builds. A completed click may reach this observer first as
            # PointModifiedEvent or ModifiedEvent rather than exclusively as
            # PointPositionDefinedEvent. Finalize from MRML state: when the
            # pending index has become a defined point. The logic method is
            # idempotent after it clears PendingLandmarkIndex.
            pendingIndexText = str(
                node.GetAttribute("DENTOBOT.PendingLandmarkIndex") or ""
            )
            pendingPointIsDefined = bool(
                pendingIndexText.isdigit()
                and node.GetNumberOfDefinedControlPoints() > int(pendingIndexText)
            )
            if pendingPointIsDefined:
                acceptedEvidence = self.logic.finalizeStep6CaseJawLandmarkPlacement(
                    self._parameterNode,
                    node,
                )
            summary = self.logic.getStep6CaseJawLandmarkSummary(node)
        except ValueError as exc:
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))
            return
        finally:
            self._updatingStep6CaseJawLandmarks = False
        transform = self._parameterNode.step6CaseJawTransform
        coordinatesChanged = not summary["isComplete"]
        if not coordinatesChanged:
            coordinatesChanged = (
                transform.GetAttribute("DENTOBOT.LandmarksFingerprint")
                != self.logic._step6CaseJawLandmarksFingerprint(node)
            ) if self.logic.isStep6CaseJawTransformNode(transform) else False
        if self.logic.isStep6CaseJawTransformNode(transform) and coordinatesChanged:
            # vtkMRMLMarkupsNode emits ModifiedEvent for interaction-policy
            # changes such as lock/selectability. Only coordinate changes may
            # invalidate the anatomical transform.
            self._markStep6CaseJawOpeningStale(
                _("Case jaw landmarks changed; apply the mouth opening again.")
            )
        if summary["isComplete"]:
            self.logic.stopTrajectoryPlacement()
        self._updateStep6CaseJawOpeningControls()
        if acceptedEvidence and summary["isComplete"]:
            self._updateStep6CaseJawOpeningStatus(
                _(
                    "All four landmarks were projected to their intended source "
                    "surfaces. Review the labels and select Apply Open-Mouth "
                    "Transform."
                )
            )
        elif acceptedEvidence:
            nextIndex = int(summary["definedPointCount"])
            self._updateStep6CaseJawOpeningStatus(
                _(
                    "Accepted %1 on %2. Placement has stopped. Select %3 to arm "
                    "the next source surface."
                )
                .replace("%1", str(acceptedEvidence.get("label") or "landmark"))
                .replace(
                    "%2", str(acceptedEvidence.get("sourceSegmentId") or "surface")
                )
                .replace(
                    "%3", self.logic.caseFoundationLandmarkButtonLabels()[nextIndex]
                )
            )
        else:
            self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi()

    def _updateStep6CaseJawOpeningControls(self) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        self._tryApplySessionFoundation()
        sourceReady = bool(
            self._parameterNode.inputVolume
            and self._parameterNode.teethSegmentation
            and self.logic.getSegmentationReviewState(
                self._parameterNode.teethSegmentation
            )
            == "Reviewed"
        )
        rosActive = bool(
            self.logic.isRos2MotionControlActive(
                self._parameterNode.robotBaseTransform
            )
        )
        hasTransientOpening = any(
            node is not None
            for node in (
                self._parameterNode.step6CaseJawTransform,
                self._parameterNode.step6OpenedLowerJawModel,
                self._parameterNode.step6CaseJawGapLine,
            )
        )
        blocked = rosActive
        node = self._parameterNode.step6CaseJawLandmarks
        summary = None
        if node and self.logic.isStep6CaseJawLandmarksNode(node):
            try:
                summary = self.logic.getStep6CaseJawLandmarkSummary(node)
            except ValueError:
                summary = None
        pointCount = summary["definedPointCount"] if summary else 0
        complete = bool(summary and summary["isComplete"])
        pendingIndexText = (
            str(node.GetAttribute("DENTOBOT.PendingLandmarkIndex") or "")
            if node
            else ""
        )
        placementPending = pendingIndexText.isdigit()
        pendingIndex = int(pendingIndexText) if placementPending else -1
        evidenceIssues = (
            self.logic.step6CaseJawSurfaceEvidenceIssues(self._parameterNode)
            if complete
            else []
        )
        reviewedComplete = bool(complete and not evidenceIssues)
        labels = self.logic.caseFoundationLandmarkButtonLabels()
        self._updatingRobotPlacementUI = True
        try:
            if (
                self.ui.step6RegistryTrajectorySelector.currentNode()
                is not self._parameterNode.trajectoryLine
            ):
                wasRestoring = self._restoringTrajectoryAssociation
                self._restoringTrajectoryAssociation = True
                try:
                    self.ui.step6RegistryTrajectorySelector.setCurrentNode(
                        self._parameterNode.trajectoryLine
                    )
                finally:
                    self._restoringTrajectoryAssociation = wasRestoring
            self.ui.step6RegistrySelectionGroupBox.enabled = bool(
                not rosActive
            )
            try:
                registry = parse_trajectory_registry(
                    str(self._parameterNode.step6TrajectoryRegistryJson or "")
                )
                selectedId = str(registry.get("selected_branch_id") or "")
                branch = registry["prepared_branches"].get(selectedId)
                populated = sum(
                    slot["state"] != "Empty"
                    for tooth in registry["teeth"].values()
                    for slot in tooth["trajectory_set"]["slots"]
                )
                selectedText = (
                    f"{branch['target_id']} / {branch['primary_trajectory_id']}"
                    if branch
                    else _("No PreparedBranch is selected.")
                )
                guideText = (
                    _(" PreparedBranch %1 references %2 trajectory slot(s).")
                    .replace("%1", branch["branch_id"])
                    .replace("%2", str(len(branch["trajectory_ids"])))
                    if branch
                    else _(" No verified PreparedBranch is active.")
                )
                self.ui.step6RegistrySelectionStatusLabel.text = (
                    _("%1 Registry contains %2/96 populated slots.%3")
                    .replace("%1", selectedText)
                    .replace("%2", str(populated))
                    .replace("%3", guideText)
                )
                self.ui.step6RegistrySelectionStatusLabel.styleSheet = (
                    "color: #207227;" if branch else "color: #b36b00;"
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                self.ui.step6RegistrySelectionStatusLabel.text = _(
                    "No populated trajectory slot is selected."
                )
                self.ui.step6RegistrySelectionStatusLabel.styleSheet = "color: #b36b00;"
            self.ui.step6CaseJawOpeningGroupBox.enabled = bool(sourceReady or hasTransientOpening)
            self.ui.createStep6CaseJawLandmarksButton.enabled = bool(
                sourceReady
                and not blocked
                and (placementPending or not complete or evidenceIssues)
            )
            self.ui.createStep6CaseJawLandmarksButton.text = (
                _("Resolve / cancel placement — %1")
                .replace(
                    "%1",
                    self.logic.caseFoundationLandmarkPlacementHints()[pendingIndex],
                )
                if placementPending
                else _("Review / re-snap existing landmarks…")
                if complete and evidenceIssues
                else (
                    labels[pointCount]
                    if pointCount < len(labels)
                    else _("All landmarks reviewed")
                )
            )
            self.ui.clearStep6CaseJawLandmarksButton.enabled = bool(
                sourceReady
                and not blocked
                and (pointCount > 0 or placementPending)
            )
            self.ui.applyStep6CaseJawOpeningButton.enabled = bool(
                sourceReady and not blocked and reviewedComplete
            )
            self.ui.resetStep6CaseJawOpeningButton.enabled = bool(
                not rosActive
                and bool(self._parameterNode.caseFoundationPreviewUncommitted)
            )
            self.ui.clearCaseFoundationButton.enabled = bool(
                not rosActive
                and (
                    hasTransientOpening
                    or pointCount
                )
            )
            self.ui.forgetSessionFoundationButton.enabled = bool(
                getattr(self, "_caseFoundationSnapshot", None)
            )
            self.ui.caseFoundationGapSlider.enabled = bool(
                reviewedComplete
                and self.logic.isStep6CaseJawTransformNode(
                    self._parameterNode.step6CaseJawTransform
                )
                and not rosActive
            )
            if not bool(self._parameterNode.caseFoundationPreviewUncommitted):
                self.ui.caseFoundationGapSlider.blockSignals(True)
                self.ui.caseFoundationGapSlider.value = int(
                    round(float(self._parameterNode.step6CaseJawTargetGapMm) * 10.0)
                )
                self.ui.caseFoundationGapSlider.blockSignals(False)
        finally:
            self._updatingRobotPlacementUI = False

    def _updateStep6CaseJawOpeningStatus(
        self,
        message: str = "",
        error: bool = False,
    ) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        if message:
            self.ui.step6CaseJawOpeningStatusLabel.text = message
            self.ui.step6CaseJawOpeningStatusLabel.styleSheet = (
                "color: #b00020;" if error else "color: #207227;"
            )
            return
        if (
            not self._parameterNode.inputVolume
            or not self._parameterNode.teethSegmentation
            or self.logic.getSegmentationReviewState(
                self._parameterNode.teethSegmentation
            )
            != "Reviewed"
        ):
            text = _("Review the source CBCT segmentation before establishing the Case Foundation.")
            style = "color: #b36b00;"
        else:
            issues = self.logic.step6CaseJawOpeningFreshnessIssues(
                self._parameterNode
            )
            if issues:
                node = self._parameterNode.step6CaseJawLandmarks
                pointCount = (
                    node.GetNumberOfDefinedControlPoints()
                    if self.logic.isStep6CaseJawLandmarksNode(node)
                    else 0
                )
                evidenceIssues = (
                    self.logic.step6CaseJawSurfaceEvidenceIssues(
                        self._parameterNode
                    )
                    if pointCount == 4
                    else []
                )
                if pointCount == 4 and evidenceIssues:
                    text = _(
                        "The four visible landmark points have not passed the "
                        "guided Case Foundation surface workflow; their anatomical "
                        "positions have not been evaluated by the hinge solver. "
                        "Use Review / re-snap existing landmarks for an explicit "
                        "current-surface check, or Clear and arm each labelled "
                        "surface in sequence. Fallback is not authorized by this "
                        "operator-review prerequisite. %1"
                    ).replace("%1", " ".join(evidenceIssues))
                else:
                    text = (
                        _("Case jaw landmarks placed: %1/4. %2")
                        .replace("%1", str(pointCount))
                        .replace("%2", " ".join(issues))
                    )
                style = "color: #b36b00;"
            else:
                transform = self._parameterNode.step6CaseJawTransform
                angle = transform.GetAttribute("DENTOBOT.HingeAngleDeg") or "--"
                gap = transform.GetAttribute("DENTOBOT.AchievedIncisorGapMm") or "--"
                model = self._parameterNode.step6OpenedLowerJawModel
                try:
                    movingCount = len(
                        json.loads(
                            model.GetAttribute("DENTOBOT.MovingSegmentIdsJson") or "[]"
                        )
                    )
                except (TypeError, json.JSONDecodeError):
                    movingCount = 0
                text = _(
                    "Case Foundation current: rigid TMJ hinge display %1°, measured "
                    "incisor gap %2 mm; %3 lower-jaw surface(s) share the jaw transform."
                ).replace("%1", angle).replace("%2", gap).replace(
                    "%3", str(movingCount)
                )
                style = "color: #207227;"
        self.ui.step6CaseJawOpeningStatusLabel.text = text
        self.ui.step6CaseJawOpeningStatusLabel.styleSheet = style

    def _applyCaseFoundationAuthoringGate(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        pose = self.logic.evaluateCaseFoundationEligibility(
            self._parameterNode
        )["pose"]
        if pose["eligible"]:
            return
        keepPrefixes = ("frame", "focus", "restore", "show", "open")
        for section in (
            self.ui.planningCollapsibleButton,
            self.ui.templateModelingCollapsibleButton,
            self.ui.targetDockingCollapsibleButton,
            self.ui.templateGuideCollapsibleButton,
            self.ui.templateFinalizationCollapsibleButton,
        ):
            for button in section.findChildren(qt.QAbstractButton):
                name = str(button.objectName or "").lower()
                if not name.startswith(keepPrefixes):
                    button.enabled = False
            for widgetType in (
                qt.QComboBox,
                qt.QAbstractSpinBox,
                qt.QAbstractSlider,
                slicer.qMRMLNodeComboBox,
            ):
                for editor in section.findChildren(widgetType):
                    editor.enabled = False

    def onCreateStep6CaseJawLandmarks(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            if (
                not self._parameterNode.inputVolume
                or not self._parameterNode.teethSegmentation
                or self.logic.getSegmentationReviewState(
                    self._parameterNode.teethSegmentation
                )
                != "Reviewed"
            ):
                raise ValueError(_("Review the source segmentation first."))
            node = self.logic.ensureStep6CaseJawLandmarksNode(
                self._parameterNode.step6CaseJawLandmarks
            )
            self._parameterNode.step6CaseJawLandmarks = node
            self._bindStep6CaseJawLandmarksNode(node)
            pendingIndexText = str(
                node.GetAttribute("DENTOBOT.PendingLandmarkIndex") or ""
            )
            if pendingIndexText.isdigit():
                pendingIndex = int(pendingIndexText)
                if node.GetNumberOfDefinedControlPoints() > pendingIndex:
                    self._updatingStep6CaseJawLandmarks = True
                    try:
                        evidence = self.logic.finalizeStep6CaseJawLandmarkPlacement(
                            self._parameterNode,
                            node,
                        )
                    finally:
                        self._updatingStep6CaseJawLandmarks = False
                    self._updateStep6CaseJawOpeningControls()
                    self._updateStep6CaseJawOpeningStatus(
                        _(
                            "Recovered and accepted %1 on its current source "
                            "surface. Select the next labelled landmark action."
                        ).replace(
                            "%1",
                            str((evidence or {}).get("label") or "landmark"),
                        )
                    )
                else:
                    self.logic.cancelTransientStep6CaseJawLandmarkPlacement(
                        self._parameterNode
                    )
                    self._updateStep6CaseJawOpeningControls()
                    self._updateStep6CaseJawOpeningStatus(
                        _(
                            "Cancelled the unfinished landmark placement. "
                            "Select the labelled action again when ready."
                        )
                    )
                self._updateStep6PlanningUi()
                return
            summary = self.logic.getStep6CaseJawLandmarkSummary(node)
            if summary["isComplete"]:
                evidenceIssues = self.logic.step6CaseJawSurfaceEvidenceIssues(
                    self._parameterNode
                )
                if not evidenceIssues:
                    return
                if not slicer.util.confirmYesNoDisplay(
                    _(
                        "The four existing points do not have current Case Foundation "
                        "source-surface evidence. Review them against the four "
                        "current intended surfaces and project each point "
                        "exactly when it is within 5 mm? Nothing is accepted "
                        "automatically; a failed review leaves the points "
                        "unchanged."
                    ),
                    windowTitle=_("Review existing Case Foundation landmarks"),
                ):
                    return
                self.logic.stopTrajectoryPlacement()
                self.logic._restoreStep6CaseJawLandmarkPlacementVisibility(
                    self._parameterNode,
                    node,
                )
                self._updatingStep6CaseJawLandmarks = True
                try:
                    review = self.logic.reviewAndProjectExistingStep6CaseJawLandmarks(
                        self._parameterNode,
                        node,
                    )
                finally:
                    self._updatingStep6CaseJawLandmarks = False
                self._updateStep6CaseJawOpeningControls()
                self._updateStep6CaseJawOpeningStatus(
                    _(
                        "Reviewed all four existing points against their current "
                        "source surfaces; maximum exact-projection residual %1 "
                        "mm. Select Apply Open-Mouth Transform."
                    ).replace("%1", f"{review['maximumResidualMm']:.3f}")
                )
                self._updateStep6PlanningUi()
                return
            landmarkIndex = summary["definedPointCount"]
            segmentId = self.logic.prepareStep6CaseJawLandmarkPlacement(
                self._parameterNode,
                node,
                landmarkIndex,
            )
            self._updateStep6CaseJawOpeningStatus(
                _(
                    "Only source segment %2 is exposed for %1. Click its visible "
                    "surface in 3D (or place in MPR); the point is projected back "
                    "to that exact source surface before the next landmark."
                ).replace(
                    "%1",
                    self.logic.caseFoundationLandmarkPlacementHints()[landmarkIndex],
                ).replace("%2", segmentId)
            )
            self._updateStep6CaseJawOpeningControls()
        except (RuntimeError, ValueError) as exc:
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onClearStep6CaseJawLandmarks(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        node = self._parameterNode.step6CaseJawLandmarks
        if not self.logic.isStep6CaseJawLandmarksNode(node):
            return
        try:
            self.logic.stopTrajectoryPlacement()
            self.logic._restoreStep6CaseJawLandmarkPlacementVisibility(
                self._parameterNode,
                node,
            )
            if (
                self._parameterNode.step6CaseJawTransform
                or self._parameterNode.step6OpenedLowerJawModel
            ):
                self.logic.resetStep6CaseJawOpening(self._parameterNode)
            self._updatingStep6CaseJawLandmarks = True
            node.RemoveAllControlPoints()
            node.SetAttribute("DENTOBOT.SurfaceEvidenceJson", None)
            node.SetAttribute("DENTOBOT.PendingLandmarkIndex", None)
            node.SetAttribute("DENTOBOT.PendingSourceSegmentID", None)
            self._updatingStep6CaseJawLandmarks = False
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus(
                _("Case jaw landmarks cleared. Place Left TMJ first.")
            )
            self._updateStep6PlanningUi()
        except (RuntimeError, ValueError) as exc:
            self._updatingStep6CaseJawLandmarks = False
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onApplyStep6CaseJawOpening(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            _transform, _model, _gapLine, summary = (
                self.logic.createOrUpdateStep6CaseJawOpening(self._parameterNode)
            )
            if self._robotWorkflowFacade:
                self._robotWorkflowFacade.clearTransientState()
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus(
                _(
                    "Committed Case Foundation opening %1°; measured incisor gap "
                    "%2 mm. Continue to Step 4A or the Step 6 offline base setup."
                )
                .replace("%1", f"{summary['angleDeg']:.2f}")
                .replace("%2", f"{summary['gapMm']:.2f}")
            )
            self._applyStep6RecommendedView()
            self._updateStep6PlanningUi()
        except (RuntimeError, ValueError) as exc:
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onResetStep6CaseJawOpening(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            self.logic.revertCaseFoundationOpeningPreview(self._parameterNode)
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus(
                _("Restored the last committed Case Foundation opening.")
            )
        except (RuntimeError, ValueError) as exc:
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onStep6CaseJawTargetGapChanged(self, value: float = 0.0) -> None:
        if (
            self._updatingFromParameterNode
            or self._updatingRobotPlacementUI
            or not self._parameterNode
            or not self.logic
        ):
            return
        if self.logic.isStep6CaseJawTransformNode(
            self._parameterNode.step6CaseJawTransform
        ):
            try:
                self.logic.previewCaseFoundationOpening(self._parameterNode, value)
                self.logic.commitCaseFoundationOpeningPreview(self._parameterNode)
            except (RuntimeError, ValueError) as exc:
                self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi()

    def onCaseFoundationGapSliderPressed(self) -> None:
        if self._parameterNode:
            self._caseFoundationSliderChanged = False
            self._parameterNode.caseFoundationPreviewUncommitted = True

    def onCaseFoundationGapSliderChanged(self, value: int) -> None:
        if (
            self._updatingFromParameterNode
            or self._updatingRobotPlacementUI
            or not self._parameterNode
            or not self.logic
            or not self.logic.isStep6CaseJawTransformNode(
                self._parameterNode.step6CaseJawTransform
            )
        ):
            return
        gap = float(value) / 10.0
        self._caseFoundationSliderChanged = True
        self._parameterNode.step6CaseJawTargetGapMm = gap
        self.ui.step6CaseJawTargetGapSpinBox.blockSignals(True)
        self.ui.step6CaseJawTargetGapSpinBox.value = gap
        self.ui.step6CaseJawTargetGapSpinBox.blockSignals(False)
        try:
            summary = self.logic.previewCaseFoundationOpening(
                self._parameterNode, gap
            )
            self._updateStep6CaseJawOpeningStatus(
                _("Uncommitted preview: %1° / %2 mm.")
                .replace("%1", f"{summary['angleDeg']:.2f}")
                .replace("%2", f"{summary['gapMm']:.2f}")
            )
        except (RuntimeError, ValueError) as exc:
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
        self._updateStep6CaseJawOpeningControls()

    def onCaseFoundationGapSliderReleased(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        if not self._caseFoundationSliderChanged:
            self._parameterNode.caseFoundationPreviewUncommitted = False
            return
        try:
            self.logic.commitCaseFoundationOpeningPreview(self._parameterNode)
        except (RuntimeError, ValueError) as exc:
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            return
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi()

    def onClearCaseFoundation(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Clear the committed Case Foundation and mark dependent planning "
                "and base setup stale? Existing Step 4/5 geometry remains inspectable."
            ),
            windowTitle=_("Clear Case Foundation"),
        ):
            return
        self.logic.resetStep6CaseJawOpening(self._parameterNode)
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi()

    def onForgetSessionFoundation(self, checked: bool = False) -> None:
        del checked
        self._caseFoundationSnapshot = None
        self._updateStep6CaseJawOpeningControls()

    def onCaseFoundationGoToStep4(self, checked: bool = False) -> None:
        del checked
        self._setWorkflowStage(4)

    def onCaseFoundationGoToStep6(self, checked: bool = False) -> None:
        del checked
        self._setWorkflowStage(len(self._workflowStageEntries()) - 1)

    def onLoadRobotModel(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.loadRobot()
        if not result.success:
            slicer.util.errorDisplay(result.message)
            return
        self._updateRobotPlacement()
        self.onFrameStep6ResearchWorkspace()
        self._applyStep6RecommendedView()
        self._updateRobotPlacementStatus(result.message)

    def onCreateRobotMountPlane(self, checked: bool = False) -> None:
        del checked
        slicer.util.errorDisplay(
            _(
                "Legacy mount-plane creation is quarantined. It was derived "
                "from the robot base and cannot represent the forehead. Position "
                "the Manual Simulation Base directly in Robot + CBCT context."
            )
        )

    def onSnapRobotBaseToPlane(self, checked: bool = False) -> None:
        del checked
        slicer.util.errorDisplay(
            _(
                "Snap Base to Mount Plane is quarantined because the plane was "
                "derived from this same base. Use direct transform handles or "
                "local-axis nudges for the Manual Simulation Base."
            )
        )

    def onFlipRobotMountPlane(self, checked: bool = False) -> None:
        del checked
        slicer.util.errorDisplay(
            _(
                "The legacy mount plane is visualization-only and quarantined "
                "from placement. Edit the Manual Simulation Base directly."
            )
        )

    def _nudgeRobotBase(
        self,
        translationAxis: int | None,
        rotationAxis: int | None,
        direction: float,
    ) -> None:
        if not self._parameterNode or not self.logic:
            return
        if self._parameterNode.robotBaseMountLocked:
            return
        translation = [0.0, 0.0, 0.0]
        rotation = [0.0, 0.0, 0.0]
        if translationAxis is not None:
            translation[translationAxis] = (
                float(direction) * self._parameterNode.robotTranslationStepMm
            )
        if rotationAxis is not None:
            rotation[rotationAxis] = (
                float(direction) * self._parameterNode.robotRotationStepDeg
            )
        try:
            self.logic.nudgeRobotBase(
                self._parameterNode.robotBaseTransform,
                translationLocalMm=tuple(translation),
                rotationLocalDeg=tuple(rotation),
            )
            self._updateRobotPlacementStatus()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onRobotJointValueChanged(self, value: float) -> None:
        del value
        if (
            self._updatingRobotPlacementUI
            or self._updatingFromParameterNode
            or not self._parameterNode
            or not self.logic
            or not self._robotWorkflowFacade
            or self._robotWorkflowFacade.displaySyncActive
        ):
            return
        result = self._robotWorkflowFacade.requestCurrentJointState()
        if not result.success:
            self._updateRos2MotionControlStatus(
                _("ROS 2 joint update failed: %1").replace("%1", result.message)
            )
            self._updateRobotPlacement()
            return
        self._updateRobotPlacementStatus()

    def onRobotBaseTransformSelectionChanged(self, transformNode) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.robotBaseTransform = transformNode
        self._updateRobotPlacement()

    def onRobotMountPlaneSelectionChanged(self, planeNode) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.robotMountPlane = planeNode
        self._updateRobotPlacement()

    def onStep6CaseJawLandmarksSelectionChanged(self, node) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        if node and self.logic and not self.logic.isStep6CaseJawLandmarksNode(node):
            slicer.util.errorDisplay(_("Select the Step 6 case jaw landmark set."))
            return
        self._parameterNode.step6CaseJawLandmarks = node
        self._bindStep6CaseJawLandmarksNode(node)
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi()

    def onRobotKeyboardNudgeToggled(self, checked: bool) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.robotKeyboardNudgeEnabled = bool(checked)
        self._updateRobotKeyboardShortcutState()

    def onResetRobotJoints(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode:
            return
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.robotJoint1Deg = 0.0
            self._parameterNode.robotJoint2Mm = 0.0
            self._parameterNode.robotJoint3Deg = 0.0
            self._parameterNode.robotJoint4Mm = 0.0
            self._parameterNode.robotJoint5Deg = 0.0
            self._parameterNode.robotJoint6Deg = 0.0
        finally:
            self._parameterNode.EndModify(wasModifying)
        self._updateRobotPlacement()
        self._updateRobotPlacementStatus(_("All robot joints reset to selected zero."))

    def onResetRobotBase(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        baseTransform = self._parameterNode.robotBaseTransform
        if not self.logic.isRobotBaseTransformNode(baseTransform):
            return
        matrix = vtk.vtkMatrix4x4()
        matrix.Identity()
        baseTransform.SetAndObserveTransformNodeID(None)
        baseTransform.SetMatrixTransformToParent(matrix)
        baseTransform.SetAttribute(
            self.logic.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
            self.logic.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY,
        )
        baseTransform.SetAttribute("DENTOBOT.PlacementWarning", None)
        self._updateRobotPlacementStatus(_("Robot base reset to Slicer world RAS."))

    def onFrameStep6CaseScene(self, checked: bool = False) -> None:
        """Show the Case Foundation source in slice and 3D views."""
        del checked
        if not self._parameterNode or not self.logic:
            return
        self._showStep6CaseVolumeInSliceViewers()
        bounds = self.logic.step6CaseViewRasBounds(self._parameterNode)
        if bounds is None:
            return
        self._frameRasBoundsInViews(bounds)

    def onFrameStep6ResearchWorkspace(self, checked: bool = False) -> None:
        del checked
        if not self.logic:
            return
        bounds = self.logic.step6ResearchWorkspaceRasBounds(
            self.logic.robotModelNodes(),
            self.logic.step6CaseViewNodes(self._parameterNode),
        )
        if bounds is None:
            return
        self._frameRasBoundsInViews(bounds)

    def onFrameRobot(self, checked: bool = False) -> None:
        del checked
        self.onFrameStep6ResearchWorkspace()

    def onDeleteRobotSetup(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Delete the simulation-only robot meshes, link transforms, base "
                "transform, and mount plane from this scene?"
            ),
            windowTitle=_("Delete Step 6 robot setup"),
        ):
            return
        if self.logic.isRos2MotionControlActive(
            self._parameterNode.robotBaseTransform
        ):
            disconnect_dentobot_motion_control(self.logic.robotModelNodes())
        removed = self.logic.deleteRobotPlacement(
            self._parameterNode.robotBaseTransform,
            self._parameterNode.robotMountPlane,
        )
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.robotBaseTransform = None
            self._parameterNode.robotMountPlane = None
            self._parameterNode.robotKeyboardNudgeEnabled = False
        finally:
            self._parameterNode.EndModify(wasModifying)
        self._clearRobotPlacement()
        logging.info("Deleted %d Step 6 robot placement nodes", len(removed))
