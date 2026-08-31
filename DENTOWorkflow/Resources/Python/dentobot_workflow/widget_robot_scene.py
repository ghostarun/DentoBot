"""Extracted robot scene and jaw setup methods; public APIs remain on RobotWidgetMixin."""

from __future__ import annotations

from .runtime import *


class RobotSceneWidgetMixin:
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

    def _updateDraftPhantomStatus(self, message: str = "", error: bool = False) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        if message:
            self.ui.draftOpenMouthStatusLabel.text = message
            self.ui.draftOpenMouthStatusLabel.styleSheet = (
                "color: #b00020;" if error else "color: #207227;"
            )
            return
        transform = self._parameterNode.draftJawTransform
        if self.logic.isDraftJawTransformNode(transform):
            angle = transform.GetAttribute("DENTOBOT.HingeAngleDeg") or "--"
            gap = transform.GetAttribute("DENTOBOT.AchievedIncisorGapMm") or "--"
            self.ui.draftOpenMouthStatusLabel.text = _(
                "Draft mouth open: pure TMJ hinge rotation %1°, measured incisor gap %2 mm."
            ).replace("%1", angle).replace("%2", gap)
            self.ui.draftOpenMouthStatusLabel.styleSheet = "color: #207227;"
        elif self.logic.draftPhantomModelNodes():
            pointCount = (
                self._parameterNode.draftJawLandmarks.GetNumberOfDefinedControlPoints()
                if self.logic.isDraftJawLandmarksNode(
                    self._parameterNode.draftJawLandmarks
                )
                else 0
            )
            self.ui.draftOpenMouthStatusLabel.text = _(
                "Draft phantom loaded. Jaw landmarks placed: %1/4."
            ).replace("%1", str(pointCount))
            self.ui.draftOpenMouthStatusLabel.styleSheet = "color: #b36b00;"
        else:
            self.ui.draftOpenMouthStatusLabel.text = _(
                "Load the local generic phantom to begin."
            )
            self.ui.draftOpenMouthStatusLabel.styleSheet = "color: #b36b00;"

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
        self.logic.invalidateStep6TaskConfirmation(
            self._parameterNode,
            reason,
            makeBaseStale=True,
        )
        self.logic.deleteRobotWorkspaceModel()
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
                    "%3", self.logic.draftJawLandmarkButtonLabels()[nextIndex]
                )
            )
        else:
            self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi()

    def _updateStep6CaseJawOpeningControls(self) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        imported = bool(self._parameterNode.step6PlanningContextImported)
        rosActive = bool(
            self.logic.isRos2MotionControlActive(
                self._parameterNode.robotBaseTransform
            )
        )
        blocked = bool(self._parameterNode.robotBaseMountLocked or rosActive)
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
        inFallback = (
            str(self._parameterNode.step6CaseJawPreparationMode)
            == "TargetJawFallback"
        )
        evidenceIssues = (
            self.logic.step6CaseJawSurfaceEvidenceIssues(self._parameterNode)
            if complete
            else []
        )
        reviewedComplete = bool(complete and not evidenceIssues)
        labels = self.logic.draftJawLandmarkButtonLabels()
        self._updatingRobotPlacementUI = True
        try:
            self.ui.step6CaseJawOpeningGroupBox.enabled = imported
            self.ui.createStep6CaseJawLandmarksButton.enabled = bool(
                imported
                and not blocked
                and not inFallback
                and (placementPending or not complete or evidenceIssues)
            )
            self.ui.createStep6CaseJawLandmarksButton.text = (
                _("Resolve / cancel placement — %1")
                .replace(
                    "%1",
                    self.logic.draftJawLandmarkPlacementHints()[pendingIndex],
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
                imported
                and not blocked
                and not inFallback
                and (pointCount > 0 or placementPending)
            )
            self.ui.applyStep6CaseJawOpeningButton.enabled = bool(
                imported and not blocked and not inFallback and reviewedComplete
            )
            self.ui.useStep6TargetJawFallbackButton.enabled = bool(
                imported
                and not blocked
                and reviewedComplete
                and str(self._parameterNode.step6CaseJawLastFailureJson or "").strip()
                and not inFallback
            )
            self.ui.resetStep6CaseJawOpeningButton.enabled = bool(
                imported
                and not rosActive
                and (
                    self.logic.isStep6CaseJawTransformNode(
                        self._parameterNode.step6CaseJawTransform
                    )
                    or self.logic.isStep6OpenedLowerJawModelNode(
                        self._parameterNode.step6OpenedLowerJawModel
                    )
                    or self.logic.isStep6DerivedAnatomyNode(
                        self._parameterNode.step6TargetJawFallbackAnatomy,
                        self.logic.STEP6_TARGET_JAW_FALLBACK_ANATOMY_ROLE,
                    )
                )
            )
            self.ui.resetStep6CaseJawOpeningButton.text = (
                _("Exit Fallback and Retry Primary 6A…")
                if inFallback
                else _("Reset Case Jaw Closed")
            )
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
        if not self._parameterNode.step6PlanningContextImported:
            text = _("Import the Steps 0–5 planning package first.")
            style = "color: #b36b00;"
        elif (
            str(self._parameterNode.step6CaseJawPreparationMode)
            == "TargetJawFallback"
            and not self.logic.step6TargetJawFallbackFreshnessIssues(
                self._parameterNode
            )
        ):
            record = self.logic._step6CaseJawPreparationRecord(self._parameterNode)
            text = _(
                "PLACEMENT-ONLY FALLBACK: showing the unopened %1 jaw and its "
                "teeth in unchanged source RAS. Robot placement, Task Home, and "
                "workspace exploration are available; ROS connect, collision "
                "sync, task confirmation, motion planning, and drilling remain "
                "blocked. Primary failure: %2"
            ).replace("%1", str(record.get("targetJaw") or "target")).replace(
                "%2", str(record.get("primaryFailure") or "not recorded")
            )
            style = "color: #b36b00; font-weight: bold;"
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
                        "guided Step 6A surface workflow; their anatomical "
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
                    "Case mouth open: TMJ hinge rotation %1°, measured incisor "
                    "gap %2 mm; %3 lower-jaw surface(s) drive Step 6 collision."
                ).replace("%1", angle).replace("%2", gap).replace(
                    "%3", str(movingCount)
                )
                style = "color: #207227;"
        self.ui.step6CaseJawOpeningStatusLabel.text = text
        self.ui.step6CaseJawOpeningStatusLabel.styleSheet = style

    def onCreateStep6CaseJawLandmarks(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            if not self._parameterNode.step6PlanningContextImported:
                raise ValueError(_("Import the Steps 0–5 planning package first."))
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
                        "The four existing points do not have current Step 6A "
                        "source-surface evidence. Review them against the four "
                        "current intended surfaces and project each point "
                        "exactly when it is within 5 mm? Nothing is accepted "
                        "automatically; a failed review leaves the points "
                        "unchanged."
                    ),
                    windowTitle=_("Review existing Step 6A landmarks"),
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
                    self.logic.draftJawLandmarkPlacementHints()[landmarkIndex],
                ).replace("%2", segmentId)
            )
            self._updateStep6CaseJawOpeningControls()
        except (RuntimeError, ValueError) as exc:
            fallbackAvailable = self.logic.recordStep6CaseJawPreparationFailure(
                self._parameterNode,
                str(exc),
            )
            self._updateStep6CaseJawOpeningControls()
            suffix = (
                _(
                    " The target-jaw-only placement fallback is now available; "
                    "it will not unlock ROS or task planning."
                )
                if fallbackAvailable
                else ""
            )
            self._updateStep6CaseJawOpeningStatus(str(exc) + suffix, error=True)
            slicer.util.errorDisplay(str(exc))

    def onUseStep6TargetJawFallback(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            record = self.logic.createStep6TargetJawFallback(self._parameterNode)
            if self._robotWorkflowFacade:
                self._robotWorkflowFacade.clearTransientState()
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus()
            self._applyStep6RecommendedView()
            self.onFrameStep6CaseScene()
            self._updateStep6PlanningUi(
                _(
                    "Target %1 jaw prepared in unchanged RAS for placement testing "
                    "only; ROS and motion planning remain blocked."
                ).replace("%1", str(record.get("targetJaw") or ""))
            )
        except (RuntimeError, ValueError) as exc:
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
                or self._parameterNode.step6TargetJawFallbackAnatomy
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
                    "Applied case TMJ opening %1°; measured incisor gap %2 mm. "
                    "Continue to 6.1 with the opened planning anatomy."
                )
                .replace("%1", f"{summary['angleDeg']:.2f}")
                .replace("%2", f"{summary['gapMm']:.2f}")
            )
            self._applyStep6RecommendedView()
            self._updateStep6PlanningUi()
        except (RuntimeError, ValueError) as exc:
            fallbackAvailable = self.logic.recordStep6CaseJawPreparationFailure(
                self._parameterNode,
                str(exc),
            )
            self._updateStep6CaseJawOpeningControls()
            suffix = (
                _(
                    " The target-jaw-only placement fallback is now available; "
                    "it will not unlock ROS or task planning."
                )
                if fallbackAvailable
                else ""
            )
            self._updateStep6CaseJawOpeningStatus(str(exc) + suffix, error=True)
            slicer.util.errorDisplay(str(exc))

    def onResetStep6CaseJawOpening(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            wasFallback = (
                str(self._parameterNode.step6CaseJawPreparationMode)
                == "TargetJawFallback"
            )
            if wasFallback and not slicer.util.confirmYesNoDisplay(
                _(
                    "Exit placement-only fallback, unlock/stale the saved robot "
                    "base, invalidate dependent Step 6 state, and clear all four "
                    "landmarks so primary Step 6A can be repeated?"
                ),
                windowTitle=_("Retry primary Step 6A"),
            ):
                return
            self.logic.resetStep6CaseJawOpening(self._parameterNode)
            if wasFallback:
                node = self._parameterNode.step6CaseJawLandmarks
                if self.logic.isStep6CaseJawLandmarksNode(node):
                    self.logic.stopTrajectoryPlacement()
                    self.logic._restoreStep6CaseJawLandmarkPlacementVisibility(
                        self._parameterNode,
                        node,
                    )
                    self._updatingStep6CaseJawLandmarks = True
                    try:
                        node.RemoveAllControlPoints()
                        node.SetAttribute("DENTOBOT.SurfaceEvidenceJson", None)
                        node.SetAttribute("DENTOBOT.PendingLandmarkIndex", None)
                        node.SetAttribute("DENTOBOT.PendingSourceSegmentID", None)
                    finally:
                        self._updatingStep6CaseJawLandmarks = False
            if self._robotWorkflowFacade:
                self._robotWorkflowFacade.clearTransientState()
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus(
                _(
                    "Exited placement-only fallback. The saved base pose is Stale "
                    "and unlocked; place Left TMJ to retry primary Step 6A."
                )
                if wasFallback
                else _("Case jaw reset to the closed source pose; Step 6 is blocked.")
            )
            self._applyStep6RecommendedView()
            self.onFrameStep6CaseScene()
            self._updateStep6PlanningUi()
        except (RuntimeError, ValueError) as exc:
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onStep6CaseJawTargetGapChanged(self, value: float = 0.0) -> None:
        del value
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
            self._markStep6CaseJawOpeningStale(
                _("Requested case incisor gap changed; apply the mouth opening again.")
            )
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi()

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

    def onLoadDraftPhantom(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        if not self._confirmStep6SceneSwitch("phantom"):
            return
        if self._parameterNode.step6PlanningContextImported:
            self._parameterNode.step6PlanningContextImported = False
        try:
            skull, mandible, models = self.logic.createOrUpdateDraftPhantom()
            self._parameterNode.draftPhantomSkullModel = skull
            self._parameterNode.draftPhantomMandibleModel = mandible
            self.onFrameStep6ResearchWorkspace()
            if self.logic.isRobotBaseTransformNode(
                self._parameterNode.robotBaseTransform
            ):
                self.logic.positionRobotBaseNearResearchPhantom(
                    self._parameterNode.robotBaseTransform,
                    models,
                )
            self._updateRobotPlacement()
            self._applyStep6RecommendedView()
            self._updateDraftPhantomStatus(
                _(
                    "Loaded generic BodyParts3D neurocranium, maxilla, and mandible. "
                    "Place the first jaw landmark next."
                )
            )
        except (RuntimeError, ValueError, OSError) as exc:
            self._updateDraftPhantomStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onCreateDraftJawLandmarks(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            node = self.logic.ensureDraftJawLandmarksNode(
                self._parameterNode.draftJawLandmarks
            )
            self._parameterNode.draftJawLandmarks = node
            self._bindDraftJawLandmarksNode(node)
            summary = self.logic.getDraftJawLandmarkSummary(node)
            if summary["isComplete"]:
                return
            self.logic.startDraftJawLandmarkPlacement(node)
            self._updateRobotPlacement()
            landmarkIndex = summary["definedPointCount"]
            placementHints = self.logic.draftJawLandmarkPlacementHints()
            self._updateDraftPhantomStatus(
                _(
                    "Click one point in a 3D view for %1, then pan to the next "
                    "landmark and press the button again."
                ).replace("%1", placementHints[landmarkIndex])
            )
        except (RuntimeError, ValueError) as exc:
            self._updateDraftPhantomStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onClearDraftJawLandmarks(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        node = self._parameterNode.draftJawLandmarks
        if not self.logic.isDraftJawLandmarksNode(node):
            return
        if node.GetNumberOfDefinedControlPoints() == 0:
            return
        try:
            self.logic.stopTrajectoryPlacement()
            self.logic.resetDraftJawOpening(
                self._parameterNode.draftPhantomMandibleModel,
                self._parameterNode.draftJawTransform,
                self._parameterNode.draftJawGapLine,
            )
            self._parameterNode.draftJawGapLine = None
            self.logic.clearDraftJawLandmarks(node)
            self._updateRobotPlacement()
            self._updateDraftPhantomStatus(
                _("Draft jaw landmarks cleared. Place the first landmark next.")
            )
        except (RuntimeError, ValueError) as exc:
            self._updateDraftPhantomStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def _bindDraftJawLandmarksNode(
        self,
        landmarksNode: vtkMRMLMarkupsFiducialNode | None,
    ) -> None:
        if landmarksNode is self._draftJawLandmarksNode:
            return
        if self._draftJawLandmarksNode:
            for landmarkEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.removeObserver(
                    self._draftJawLandmarksNode,
                    landmarkEvent,
                    self._onDraftJawLandmarksModified,
                )
        self._draftJawLandmarksNode = landmarksNode
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
                    self._onDraftJawLandmarksModified,
                )

    def _onDraftJawLandmarksModified(self, caller=None, event=None) -> None:
        del caller, event
        if not self._parameterNode or not self.logic:
            return
        node = self._draftJawLandmarksNode
        if not node or not self.logic.isDraftJawLandmarksNode(node):
            return
        try:
            summary = self.logic.getDraftJawLandmarkSummary(node)
        except ValueError:
            return
        pointCount = summary["definedPointCount"]
        if pointCount >= 4:
            self.logic.stopTrajectoryPlacement()
            if not self.logic.isDraftJawTransformNode(
                self._parameterNode.draftJawTransform
            ):
                try:
                    self.onApplyDraftJawOpening()
                except (RuntimeError, ValueError) as exc:
                    self._updateDraftPhantomStatus(str(exc), error=True)
                    slicer.util.errorDisplay(str(exc))
        self._updateDraftJawLandmarkControls()
        if pointCount < 4:
            self._updateDraftPhantomStatus()

    def _updateDraftJawLandmarkControls(self, phantomLoaded: bool | None = None) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        if phantomLoaded is None:
            phantomLoaded = bool(
                self._parameterNode.draftPhantomSkullModel
                and self._parameterNode.draftPhantomMandibleModel
            )
        node = self._parameterNode.draftJawLandmarks
        summary = None
        if node and self.logic.isDraftJawLandmarksNode(node):
            try:
                summary = self.logic.getDraftJawLandmarkSummary(node)
            except ValueError:
                summary = None
        pointCount = summary["definedPointCount"] if summary else 0
        isComplete = bool(summary and summary["isComplete"])
        buttonLabels = self.logic.draftJawLandmarkButtonLabels()
        self._updatingRobotPlacementUI = True
        try:
            self.ui.createDraftJawLandmarksButton.enabled = bool(
                phantomLoaded and not isComplete
            )
            self.ui.createDraftJawLandmarksButton.text = (
                buttonLabels[pointCount]
                if pointCount < len(buttonLabels)
                else _("All landmarks placed")
            )
            self.ui.clearDraftJawLandmarksButton.enabled = bool(
                phantomLoaded and pointCount > 0
            )
            self.ui.applyDraftJawOpeningButton.enabled = bool(
                phantomLoaded and isComplete
            )
        finally:
            self._updatingRobotPlacementUI = False

    def onApplyDraftJawOpening(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            transform, gapLine, summary = self.logic.createOrUpdateDraftJawOpening(
                self._parameterNode.draftPhantomMandibleModel,
                self._parameterNode.draftJawLandmarks,
                self._parameterNode.draftJawTransform,
                self._parameterNode.draftJawGapLine,
                self._parameterNode.draftJawTargetGapMm,
            )
            self._parameterNode.draftJawTransform = transform
            self._parameterNode.draftJawGapLine = gapLine
            self._updateRobotPlacement()
            self._updateDraftPhantomStatus(
                _(
                    "Draft mouth opened by pure TMJ hinge rotation %1°; measured "
                    "incisor gap %2 mm."
                )
                .replace("%1", f"{summary['angleDeg']:.2f}")
                .replace("%2", f"{summary['gapMm']:.2f}")
            )
        except (RuntimeError, ValueError) as exc:
            self._updateDraftPhantomStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onResetDraftJaw(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        self.logic.resetDraftJawOpening(
            self._parameterNode.draftPhantomMandibleModel,
            self._parameterNode.draftJawTransform,
            self._parameterNode.draftJawGapLine,
        )
        self._parameterNode.draftJawGapLine = None
        self._updateRobotPlacement()
        self._updateDraftPhantomStatus(_("Draft mandible reset to the closed source pose."))

    def onDeleteDraftPhantom(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        removed = self.logic.deleteDraftPhantom(
            self._parameterNode.draftJawLandmarks,
            self._parameterNode.draftJawTransform,
            self._parameterNode.draftJawGapLine,
        )
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.draftPhantomSkullModel = None
            self._parameterNode.draftPhantomMandibleModel = None
            self._parameterNode.draftJawLandmarks = None
            self._parameterNode.draftJawTransform = None
            self._parameterNode.draftJawGapLine = None
        finally:
            self._parameterNode.EndModify(wasModifying)
        self._bindDraftJawLandmarksNode(None)
        self._updateRobotPlacement()
        logging.info("Deleted %d disposable draft phantom nodes", len(removed))

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

    def onDraftPhantomSelectionChanged(self, node=None) -> None:
        del node
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.draftPhantomSkullModel = (
            self.ui.draftPhantomSkullSelector.currentNode()
        )
        self._parameterNode.draftPhantomMandibleModel = (
            self.ui.draftPhantomMandibleSelector.currentNode()
        )
        self._updateRobotPlacement()

    def onDraftJawLandmarksSelectionChanged(self, node) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.draftJawLandmarks = node
        self._bindDraftJawLandmarksNode(node)
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
        """Show the imported case in slice and 3D views (not the phantom workspace)."""
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
            self.logic.draftPhantomModelNodes(),
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
