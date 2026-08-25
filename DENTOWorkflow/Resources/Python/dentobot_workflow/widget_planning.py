"""Extracted trajectory and docking UI methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from .runtime import *


from dentobot_workflow.widget_trajectory_view import TrajectoryViewWidgetMixin


from dentobot_workflow.widget_planning_focus import PlanningFocusWidgetMixin


from dentobot_workflow.widget_docking import DockingWidgetMixin


class PlanningWidgetMixin(DockingWidgetMixin, PlanningFocusWidgetMixin, TrajectoryViewWidgetMixin):


































































    def _updatePlanning(self) -> None:
        if not self._parameterNode or not self.logic:
            self._clearPlanning()
            return

        trajectoryNode = self._parameterNode.trajectoryLine
        trajectoryAssociationError = ""
        association = None
        if trajectoryNode:
            try:
                association = self.logic.getTrajectoryTargetAssociation(
                    trajectoryNode
                )
            except ValueError as exc:
                trajectoryAssociationError = str(exc)
        if association:
            associatedSegmentation = association["segmentationNode"]
            associatedTargetId = association["targetRecord"]["segmentId"]
            associatedRoi = association["targetBoundsRoi"]
            if (
                self._parameterNode.teethSegmentation is not associatedSegmentation
                or self._parameterNode.targetToothSegmentId != associatedTargetId
                or self._parameterNode.targetToothBoundsRoi is not associatedRoi
            ):
                self._restoringTrajectoryAssociation = True
                wasModifying = self._parameterNode.StartModify()
                try:
                    self._parameterNode.teethSegmentation = associatedSegmentation
                    self._parameterNode.targetToothSegmentId = associatedTargetId
                    self._parameterNode.targetToothBoundsRoi = associatedRoi
                finally:
                    self._parameterNode.EndModify(wasModifying)
                    self._restoringTrajectoryAssociation = False

        segmentationNode = self._parameterNode.teethSegmentation
        if not segmentationNode:
            self._clearPlanning()
            return

        wasUpdatingPlanningUI = self._updatingPlanningUI
        self._updatingPlanningUI = True
        try:
            self.logic.refreshWorkflowLineageColors()
            self.logic.refreshManagedTrajectoryNames()
            self.logic.refreshWorkflowNodeStepTags()
            if self.ui.trajectorySelector.currentNode() is not trajectoryNode:
                wasRestoringAssociation = self._restoringTrajectoryAssociation
                self._restoringTrajectoryAssociation = True
                try:
                    self.ui.trajectorySelector.setCurrentNode(trajectoryNode)
                finally:
                    self._restoringTrajectoryAssociation = (
                        wasRestoringAssociation
                    )
        finally:
            self._updatingPlanningUI = wasUpdatingPlanningUI

        try:
            targetRecords = self.logic.getTargetToothRecords(segmentationNode)
        except ValueError as exc:
            self._clearPlanning()
            self.ui.planningStatusLabel.text = str(exc)
            self.ui.planningStatusLabel.styleSheet = "color: #b00020;"
            return

        self._targetToothRecordsById = {
            record["segmentId"]: record for record in targetRecords
        }
        requestedTargetId = self._parameterNode.targetToothSegmentId
        targetRecord = self._targetToothRecordsById.get(requestedTargetId)
        if requestedTargetId and not targetRecord:
            if self._parameterNode.trajectoryLine:
                self.logic.clearTrajectoryTarget(
                    self._parameterNode.trajectoryLine
                )
            self._parameterNode.targetToothSegmentId = ""
            requestedTargetId = ""

        self._updatingPlanningUI = True
        try:
            self.ui.targetToothComboBox.clear()
            self.ui.targetToothComboBox.addItem(_("Select target tooth..."), "")
            selectedIndex = 0
            for index, record in enumerate(targetRecords, start=1):
                self.ui.targetToothComboBox.addItem(
                    record["displayName"],
                    record["segmentId"],
                )
                if record["segmentId"] == requestedTargetId:
                    selectedIndex = index
            self.ui.targetToothComboBox.setCurrentIndex(selectedIndex)
            self.ui.targetToothComboBox.enabled = bool(targetRecords)
            self.ui.createTrajectoryButton.enabled = bool(targetRecord)
            if targetRecord:
                self.ui.targetToothValueLabel.text = targetRecord["displayName"]
                self.ui.targetToothSourceValueLabel.text = targetRecord[
                    "sourceName"
                ]
            else:
                self.ui.targetToothValueLabel.text = _("--")
                self.ui.targetToothSourceValueLabel.text = _("--")
        finally:
            self._updatingPlanningUI = False

        targetBounds = None
        if trajectoryAssociationError:
            self._planningConstraintWarning = trajectoryAssociationError
        if targetRecord:
            targetBounds = self._ensureTargetBounds(
                segmentationNode,
                targetRecord,
            )
            self._applyTargetPriorityHighlight()
        else:
            self.ui.targetBoundsValueLabel.text = _("--")
            roiNode = self._parameterNode.targetToothBoundsRoi
            if roiNode and roiNode.GetDisplayNode():
                roiNode.GetDisplayNode().SetVisibility(False)

        self._updatingPlanningUI = True
        try:
            self.ui.focusPlanningTargetButton.enabled = bool(
                targetRecord and targetBounds is not None
            )
            self.ui.framePlanningTargetButton.enabled = bool(
                targetRecord and targetBounds is not None
            )
            self.ui.restorePlanningViewButton.enabled = bool(
                self._assistedTrajectoryFocusState
            )
        finally:
            self._updatingPlanningUI = False

        self.logic.refreshWorkflowLineageColors()
        self.logic.applyTrajectoryGroupEmphasis(
            segmentationNode,
            targetRecord["segmentId"] if targetRecord else "",
            trajectoryNode,
        )
        self._updateTrajectorySelectorColorSwatches()

        self._bindPlanningTrajectoryNode(trajectoryNode)
        if targetRecord and trajectoryNode and not trajectoryAssociationError:
            currentTargetNode = trajectoryNode.GetNodeReference(
                self.logic.TARGET_SEGMENTATION_REFERENCE_ROLE
            )
            currentTargetId = trajectoryNode.GetAttribute(
                "DENTOBOT.TargetSegmentID"
            )
            if (
                currentTargetNode is not segmentationNode
                or currentTargetId != targetRecord["segmentId"]
            ):
                self._updatingPlanningUI = True
                try:
                    self.logic.configureTrajectoryTarget(
                        trajectoryNode,
                        segmentationNode,
                        targetRecord["segmentId"],
                    )
                finally:
                    self._updatingPlanningUI = False
            roiNode = self._parameterNode.targetToothBoundsRoi
            if roiNode and trajectoryNode.GetNodeReference(
                self.logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE
            ) is not roiNode:
                trajectoryNode.SetNodeReferenceID(
                    self.logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
                    roiNode.GetID(),
                )
            if (
                targetBounds is not None
                and not self._planningConstraintWarning
            ):
                self._enforceTrajectoryBounds(trajectoryNode)

        summary = None
        if trajectoryNode:
            try:
                summary = self.logic.getTrajectorySummary(trajectoryNode)
            except ValueError:
                summary = None
        pointCount = summary["definedPointCount"] if summary else 0
        isLocked = bool(trajectoryNode and trajectoryNode.GetLocked())
        if trajectoryNode:
            trajectoryNode.SetSelectable(True)
            displayNode = trajectoryNode.GetDisplayNode()
            if displayNode:
                displayNode.SetPointLabelsVisibility(True)
                displayNode.SetPropertiesLabelVisibility(True)
        self._updatingPlanningUI = True
        try:
            self.ui.placeTrajectoryButton.enabled = bool(
                targetRecord
                and targetBounds is not None
                and trajectoryNode
                and not isLocked
                and pointCount < 2
            )
            self.ui.placeTrajectoryButton.text = (
                _("Place Both Points")
                if pointCount == 0
                else _("Place Target")
                if pointCount == 1
                else _("Trajectory Complete")
            )
            self.ui.undoTrajectoryPointButton.enabled = bool(
                trajectoryNode and pointCount > 0 and not isLocked
            )
            self.ui.resetTrajectoryButton.enabled = bool(
                trajectoryNode and pointCount > 0
            )
            self.ui.deleteTrajectoryButton.enabled = bool(
                trajectoryNode
                and self.logic.isDentobotTrajectoryNode(trajectoryNode)
            )
            canLock = bool(
                targetRecord
                and trajectoryNode
                and summary
                and summary["isValid"]
                and not self._planningConstraintWarning
            )
            self.ui.lockTrajectoryButton.enabled = bool(canLock or isLocked)
            self.ui.lockTrajectoryButton.checked = isLocked
            self.ui.lockTrajectoryButton.text = (
                _("Unlock Entry / Target Pair")
                if isLocked
                else _("Lock Valid Entry / Target Pair")
            )
            if not trajectoryNode:
                lockStatus = _("NO TRAJECTORY SELECTED")
                lockStyle = "color: #666666; font-weight: 600;"
            elif isLocked:
                lockStatus = _(
                    "LOCKED — geometry edits are disabled; point selection and "
                    "linked-view navigation remain available."
                )
                lockStyle = "color: #207227; font-weight: 700;"
            else:
                lockStatus = _(
                    "EDITABLE — Entry and Target can be placed or corrected."
                )
                lockStyle = "color: #b36b00; font-weight: 700;"
            self.ui.trajectoryLockStatusLabel.text = lockStatus
            self.ui.trajectoryLockStatusLabel.styleSheet = lockStyle
        finally:
            self._updatingPlanningUI = False
        self._updateTrajectoryPlacementModeControls()
        self._updateTrajectoryDetails(trajectoryNode)
        self._updatePlanningStatus(
            segmentationNode,
            targetRecord,
            trajectoryNode,
        )
        self._updateTrajectoryVerificationControls()
        self._updateAssistedTrajectoryControls()

    def _updateTrajectoryDetails(self, trajectoryNode) -> None:
        if not trajectoryNode or not self.logic:
            self.ui.trajectoryEntryValueLabel.text = _("--")
            self.ui.trajectoryTargetValueLabel.text = _("--")
            self.ui.trajectoryLengthValueLabel.text = _("--")
            return
        try:
            summary = self.logic.getTrajectorySummary(trajectoryNode)
        except ValueError as exc:
            self.ui.trajectoryEntryValueLabel.text = _("--")
            self.ui.trajectoryTargetValueLabel.text = _("--")
            self.ui.trajectoryLengthValueLabel.text = _("--")
            self.ui.planningStatusLabel.text = str(exc)
            self.ui.planningStatusLabel.styleSheet = "color: #b00020;"
            return

        self.ui.trajectoryEntryValueLabel.text = (
            self.logic.formatRasPoint(summary["entryRas"])
            if summary["entryRas"]
            else _("--")
        )
        self.ui.trajectoryTargetValueLabel.text = (
            self.logic.formatRasPoint(summary["targetRas"])
            if summary["targetRas"]
            else _("--")
        )
        self.ui.trajectoryLengthValueLabel.text = (
            f'{summary["lengthMm"]:.3f} mm'
            if summary["lengthMm"] is not None
            else _("--")
        )

    def _updatePlanningStatus(
        self,
        segmentationNode,
        targetRecord: dict | None,
        trajectoryNode,
    ) -> None:
        if not self._targetToothRecordsById:
            self.ui.planningStatusLabel.text = _(
                "The selected segmentation contains no recognized whole-tooth "
                "segments."
            )
            self.ui.planningStatusLabel.styleSheet = "color: #b00020;"
            return
        if not targetRecord:
            self.ui.planningStatusLabel.text = _(
                "Choose one tooth label as the draft planning target."
            )
            self.ui.planningStatusLabel.styleSheet = "color: #b36b00;"
            return
        if self._planningConstraintWarning:
            self.ui.planningStatusLabel.text = self._planningConstraintWarning
            self.ui.planningStatusLabel.styleSheet = "color: #b00020;"
            return
        if not trajectoryNode or not self.logic:
            self.ui.planningStatusLabel.text = _(
                "Target tooth saved. Create or select a trajectory line."
            )
            self.ui.planningStatusLabel.styleSheet = "color: #1f5f99;"
            return
        try:
            summary = self.logic.getTrajectorySummary(trajectoryNode)
        except ValueError as exc:
            self.ui.planningStatusLabel.text = str(exc)
            self.ui.planningStatusLabel.styleSheet = "color: #b00020;"
            return

        pointCount = summary["definedPointCount"]
        if pointCount == 0:
            message = _("Place the Entry point, followed by the Target point.")
            style = "color: #1f5f99;"
        elif pointCount == 1:
            message = _("Entry is defined. Place the Target point.")
            style = "color: #1f5f99;"
        elif not summary["isValid"]:
            message = _(
                "Entry and Target coincide. Move one point to define a "
                "non-zero trajectory."
            )
            style = "color: #b00020;"
        else:
            reviewState = self.logic.getSegmentationReviewState(
                segmentationNode
            )
            message = (
                _(
                    "Draft inputs complete for %1. Segmentation review state: "
                    "%2. This is not an approved drilling plan."
                )
                .replace("%1", targetRecord["displayName"])
                .replace("%2", reviewState)
            )
            style = "color: #207227;"
        self.ui.planningStatusLabel.text = message
        self.ui.planningStatusLabel.styleSheet = style

    @staticmethod
    def _workflowImpactText(impact: dict) -> str:
        return ", ".join(
            _("%1 (%2 object(s))")
            .replace("%1", str(stage["stage"]))
            .replace("%2", str(len(stage["nodeIds"])))
            for stage in impact.get("stages", [])
        )

    def _refreshAfterPlanningDownstreamDeletion(self) -> None:
        if not self._parameterNode:
            return
        self._bindTemplateSupportBoundaryNode(
            self._parameterNode.templateSupportBoundaryCurve
        )
        self._bindTemplateInsertionDirectionNode(
            self._parameterNode.templateInsertionDirection
        )
        self._updateTargetDocking()
        self._updateTemplateModeling()
        self._updateTemplateGuide()
        self._updateTemplateFinalization()
        self._updatePlanning()

    def _confirmAndDeleteTrajectoryDependents(
        self,
        trajectoryNode,
        actionText: str,
        *,
        impact: dict | None = None,
    ) -> bool:
        if not self.logic or not trajectoryNode:
            return True
        impact = impact or self.logic.getTrajectoryDependentWorkflowImpact(
            trajectoryNode
        )
        if not impact["hasDependents"]:
            if impact.get("flags", {}).get("selectedGuideReference"):
                try:
                    self.logic.deleteTrajectoryDependentWorkflow(
                        trajectoryNode,
                        impact=impact,
                    )
                except (RuntimeError, ValueError) as exc:
                    slicer.util.errorDisplay(str(exc))
                    return False
            return True
        trajectoryName = trajectoryNode.GetName() or _("Unnamed trajectory")
        if not slicer.util.confirmYesNoDisplay(
            _(
                "The trajectory “%1” already has downstream geometry. To %2, "
                "DENTOBOT must delete: %3. The authoritative segmentation, "
                "target tooth, target bounds, support-tooth choices, and other "
                "trajectories will be preserved. Continue?"
            ).replace("%1", trajectoryName).replace(
                "%2", actionText
            ).replace(
                "%3", self._workflowImpactText(impact)
            ),
            windowTitle=_("Backtrack dependent workflow"),
        ):
            return False
        try:
            result = self.logic.deleteTrajectoryDependentWorkflow(
                trajectoryNode,
                impact=impact,
            )
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))
            return False
        logging.info(
            "Backtracked %s before trajectory change; removed %d dependent nodes",
            trajectoryNode.GetID(),
            len(result["removedNodeIds"]),
        )
        self._refreshAfterPlanningDownstreamDeletion()
        return True

    def _confirmAndDeleteActivePlanningDownstream(
        self,
        actionText: str,
    ) -> bool:
        if not self.logic:
            return True
        impact = self.logic.getActivePlanningDownstreamImpact()
        if not impact["hasDependents"]:
            if impact.get("flags", {}).get("selectedGuideReference"):
                try:
                    self.logic.deleteActivePlanningDownstreamWorkflow(
                        impact=impact
                    )
                except (RuntimeError, ValueError) as exc:
                    slicer.util.errorDisplay(str(exc))
                    return False
            return True
        if not slicer.util.confirmYesNoDisplay(
            _(
                "The current target has downstream geometry. To %1, DENTOBOT "
                "must delete: %2. The authoritative segmentation, tooth masks, "
                "target bounds, and trajectory nodes will be preserved. Continue?"
            ).replace("%1", actionText).replace(
                "%2", self._workflowImpactText(impact)
            ),
            windowTitle=_("Backtrack current target workflow"),
        ):
            return False
        try:
            result = self.logic.deleteActivePlanningDownstreamWorkflow(
                impact=impact
            )
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))
            return False
        logging.info(
            "Backtracked active planning target; removed %d dependent nodes",
            len(result["removedNodeIds"]),
        )
        self._refreshAfterPlanningDownstreamDeletion()
        return True

    def onTargetToothChanged(self, index: int) -> None:
        if (
            self._updatingPlanningUI
            or self._restoringTrajectoryAssociation
            or not self._parameterNode
            or not self.logic
        ):
            return
        self._restoreAssistedTrajectoryFocus(updateUi=False)
        segmentId = (
            str(self.ui.targetToothComboBox.itemData(index))
            if index >= 0 and self.ui.targetToothComboBox.itemData(index)
            else ""
        )
        previousTargetId = self._parameterNode.targetToothSegmentId
        if segmentId != previousTargetId:
            if not self._confirmAndDeleteActivePlanningDownstream(
                _("switch the active target tooth")
            ):
                previousIndex = self.ui.targetToothComboBox.findData(
                    previousTargetId
                )
                self._updatingPlanningUI = True
                try:
                    self.ui.targetToothComboBox.setCurrentIndex(
                        previousIndex if previousIndex >= 0 else 0
                    )
                finally:
                    self._updatingPlanningUI = False
                return
            self._parameterNode.templateSupportToothSegmentIdsJson = "[]"
            self.logic.invalidateStep6TaskConfirmation(
                self._parameterNode,
                _("Target tooth changed."),
            )

        trajectoryNode = self._parameterNode.trajectoryLine
        trajectoryAssociation = None
        trajectoryAssociationInvalid = False
        if trajectoryNode:
            self._validTrajectoryPointsByNodeId.pop(
                trajectoryNode.GetID(),
                None,
            )
            try:
                trajectoryAssociation = (
                    self.logic.getTrajectoryTargetAssociation(trajectoryNode)
                )
            except ValueError as exc:
                slicer.util.errorDisplay(str(exc))
                trajectoryAssociationInvalid = True

        retainedTrajectory = None if trajectoryAssociationInvalid else trajectoryNode
        if trajectoryAssociation and not trajectoryAssociationInvalid:
            associatedTargetId = trajectoryAssociation["targetRecord"][
                "segmentId"
            ]
            if associatedTargetId != segmentId:
                retainedTrajectory = None
        elif trajectoryNode and segmentId:
            try:
                self.logic.configureTrajectoryTarget(
                    trajectoryNode,
                    self._parameterNode.teethSegmentation,
                    segmentId,
                )
            except ValueError as exc:
                slicer.util.errorDisplay(str(exc))
                retainedTrajectory = None
        elif trajectoryNode and not segmentId:
            retainedTrajectory = None

        previousRoi = self._parameterNode.targetToothBoundsRoi
        if (
            segmentId != previousTargetId
            and previousRoi
            and previousRoi.GetDisplayNode()
        ):
            previousRoi.GetDisplayNode().SetVisibility(False)
        self._planningConstraintWarning = ""
        self._restoringTrajectoryAssociation = True
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.targetToothSegmentId = segmentId
            self._parameterNode.trajectoryLine = retainedTrajectory
            if segmentId != previousTargetId:
                self._parameterNode.targetToothBoundsRoi = None
        finally:
            self._parameterNode.EndModify(wasModifying)
            self._restoringTrajectoryAssociation = False
        self._updatePlanning()
        self._updateTemplateModeling()
        self._applyTargetPriorityHighlight()

    def onTrajectorySelectionChanged(self, trajectoryNode) -> None:
        if (
            self._restoringTrajectoryAssociation
            or not self._parameterNode
            or not self.logic
        ):
            return
        previousNode = self._planningTrajectoryNode
        previousNodeId = previousNode.GetID() if previousNode else None
        selectedNodeId = trajectoryNode.GetID() if trajectoryNode else None
        association = None
        if trajectoryNode:
            try:
                association = self.logic.getTrajectoryTargetAssociation(
                    trajectoryNode
                )
            except ValueError as exc:
                slicer.util.errorDisplay(str(exc))
                self._restoringTrajectoryAssociation = True
                try:
                    self._parameterNode.trajectoryLine = previousNode
                    self.ui.trajectorySelector.setCurrentNode(previousNode)
                finally:
                    self._restoringTrajectoryAssociation = False
                return

        previousSegmentation = self._parameterNode.teethSegmentation
        previousTargetId = self._parameterNode.targetToothSegmentId
        if association:
            associatedSegmentation = association["segmentationNode"]
            associatedTargetId = association["targetRecord"]["segmentId"]
            if (
                previousSegmentation is not associatedSegmentation
                or previousTargetId != associatedTargetId
            ) and not self._confirmAndDeleteActivePlanningDownstream(
                _("switch to a trajectory for another target tooth")
            ):
                self._restoringTrajectoryAssociation = True
                try:
                    self._parameterNode.trajectoryLine = previousNode
                    self.ui.trajectorySelector.setCurrentNode(previousNode)
                finally:
                    self._restoringTrajectoryAssociation = False
                return
        self._restoringTrajectoryAssociation = True
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.trajectoryLine = trajectoryNode
            if association:
                associatedSegmentation = association["segmentationNode"]
                associatedTargetId = association["targetRecord"]["segmentId"]
                associatedRoi = association["targetBoundsRoi"]
                if (
                    previousSegmentation is not associatedSegmentation
                    or previousTargetId != associatedTargetId
                ):
                    self._parameterNode.templateSupportToothSegmentIdsJson = "[]"
                oldRoi = self._parameterNode.targetToothBoundsRoi
                if (
                    oldRoi
                    and oldRoi is not associatedRoi
                    and oldRoi.GetDisplayNode()
                ):
                    oldRoi.GetDisplayNode().SetVisibility(False)
                self._parameterNode.teethSegmentation = associatedSegmentation
                self._parameterNode.targetToothSegmentId = associatedTargetId
                self._parameterNode.targetToothBoundsRoi = associatedRoi
            elif trajectoryNode and self._parameterNode.targetToothSegmentId:
                self.logic.configureTrajectoryTarget(
                    trajectoryNode,
                    self._parameterNode.teethSegmentation,
                    self._parameterNode.targetToothSegmentId,
                )
        finally:
            self._parameterNode.EndModify(wasModifying)
            self._restoringTrajectoryAssociation = False

        if previousNodeId and previousNodeId != selectedNodeId:
            self._validTrajectoryPointsByNodeId.pop(previousNodeId, None)
        self._planningConstraintWarning = ""
        self._bindSegmentationReviewNode(self._parameterNode.teethSegmentation)
        self._updateSegmentationReview()
        self._bindPlanningTrajectoryNode(trajectoryNode)
        self._updatePlanning()
        self._updateTemplateModeling()
        self._updateTemplateGuide()
        if trajectoryNode:
            self._presentSelectedTrajectory(trajectoryNode)

    def onCreateTrajectory(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            targetRecord = self.logic.validateTargetTooth(
                self._parameterNode.teethSegmentation,
                self._parameterNode.targetToothSegmentId,
            )
            trajectoryNode = self.logic.createTrajectoryNode(
                f'DENTO Trajectory FDI {targetRecord["fdiNumber"]}'
            )
            self.logic.enableAutomaticTrajectoryName(trajectoryNode)
            self.logic.configureTrajectoryTarget(
                trajectoryNode,
                self._parameterNode.teethSegmentation,
                targetRecord["segmentId"],
            )
            self._parameterNode.trajectoryLine = trajectoryNode
            self._bindPlanningTrajectoryNode(trajectoryNode)
            self._updatePlanning()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onPlaceTrajectory(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            self.logic.validateTargetTooth(
                self._parameterNode.teethSegmentation,
                self._parameterNode.targetToothSegmentId,
            )
            self.logic.configureTrajectoryTarget(
                self._parameterNode.trajectoryLine,
                self._parameterNode.teethSegmentation,
                self._parameterNode.targetToothSegmentId,
            )
            self.logic.startTrajectoryPlacement(
                self._parameterNode.trajectoryLine
            )
            self._updatePlanning()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onUndoTrajectoryPoint(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        trajectoryNode = self._parameterNode.trajectoryLine
        if not trajectoryNode:
            return
        try:
            if trajectoryNode.GetLocked():
                raise ValueError(
                    _("Unlock the trajectory before removing a point.")
                )
            summary = self.logic.getTrajectorySummary(trajectoryNode)
            if summary["definedPointCount"] == 0:
                raise ValueError(_("The trajectory has no point to undo."))
            if not self._confirmAndDeleteTrajectoryDependents(
                trajectoryNode,
                _("remove its last Entry/Target point"),
            ):
                return
            self.logic.stopTrajectoryPlacement()
            trajectoryNode.RemoveNthControlPoint(
                summary["definedPointCount"] - 1
            )
            self._validTrajectoryPointsByNodeId.pop(
                trajectoryNode.GetID(),
                None,
            )
            self._planningConstraintWarning = ""
            self._enforceTrajectoryBounds(trajectoryNode)
            self._updatePlanning()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onResetTrajectory(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        trajectoryNode = self._parameterNode.trajectoryLine
        if not trajectoryNode:
            return
        summary = self.logic.getTrajectorySummary(trajectoryNode)
        if summary["definedPointCount"] == 0:
            return
        impact = self.logic.getTrajectoryDependentWorkflowImpact(
            trajectoryNode
        )
        if impact["hasDependents"]:
            if not self._confirmAndDeleteTrajectoryDependents(
                trajectoryNode,
                _("clear both Entry and Target points"),
                impact=impact,
            ):
                return
        elif not slicer.util.confirmYesNoDisplay(
                _(
                    "Clear both Entry and Target points from the selected "
                    "trajectory? This cannot be undone after the scene is saved."
                ),
                windowTitle=_("Clear Step 4A trajectory"),
            ):
            return
        self.logic.stopTrajectoryPlacement()
        trajectoryNode.SetLocked(False)
        trajectoryNode.RemoveAllControlPoints()
        self._validTrajectoryPointsByNodeId.pop(
            trajectoryNode.GetID(),
            None,
        )
        self._planningConstraintWarning = ""
        self._updatePlanning()

    def onDeleteTrajectory(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        trajectoryNode = self._parameterNode.trajectoryLine
        try:
            self.logic.validateDentobotTrajectoryForDeletion(trajectoryNode)
        except ValueError as exc:
            slicer.util.errorDisplay(str(exc))
            return
        trajectoryName = trajectoryNode.GetName() or _("Unnamed trajectory")
        impact = self.logic.getTrajectoryDependentWorkflowImpact(
            trajectoryNode
        )
        if impact["hasDependents"]:
            if not self._confirmAndDeleteTrajectoryDependents(
                trajectoryNode,
                _("permanently delete it"),
                impact=impact,
            ):
                return
        elif not slicer.util.confirmYesNoDisplay(
                _(
                    "Permanently delete the selected trajectory “%1”? The target "
                    "tooth, source segmentation, and target bounds will be kept. "
                    "This cannot be undone after the scene is saved."
                ).replace("%1", trajectoryName),
                windowTitle=_("Delete Step 4A trajectory"),
            ):
            return

        trajectoryId = trajectoryNode.GetID()
        self._bindPlanningTrajectoryNode(None)
        try:
            removal = self.logic.deleteTrajectoryNode(trajectoryNode)
        except (RuntimeError, ValueError) as exc:
            self._bindPlanningTrajectoryNode(trajectoryNode)
            slicer.util.errorDisplay(str(exc))
            return
        self._parameterNode.trajectoryLine = None
        self._validTrajectoryPointsByNodeId.pop(trajectoryId, None)
        self._planningConstraintWarning = ""
        logging.info(
            "Deleted DENTOBOT Step 4A trajectory %s and %d owned auxiliary nodes",
            removal["nodeId"],
            len(removal["auxiliaryNodeIds"]),
        )
        self._updatePlanning()

    def onTrajectoryLockToggled(self, locked: bool) -> None:
        if (
            self._updatingPlanningUI
            or not self._parameterNode
            or not self.logic
        ):
            return
        trajectoryNode = self._parameterNode.trajectoryLine
        if not trajectoryNode:
            return
        if locked:
            try:
                summary = self.logic.getTrajectorySummary(trajectoryNode)
                boundsReport = self.logic.getTrajectoryBoundsReport(
                    trajectoryNode,
                    self._parameterNode.teethSegmentation,
                    self._parameterNode.targetToothSegmentId,
                )
                if (
                    not summary["isValid"]
                    or summary["definedPointCount"] != 2
                    or not boundsReport["allDefinedPointsWithinBounds"]
                ):
                    raise ValueError(
                        _(
                            "A complete non-zero Entry/Target pair inside the "
                            "target bounds is required before locking."
                        )
                    )
                self.logic.stopTrajectoryPlacement()
                trajectoryNode.SetLocked(True)
            except (RuntimeError, ValueError) as exc:
                self._updatingPlanningUI = True
                try:
                    self.ui.lockTrajectoryButton.checked = False
                finally:
                    self._updatingPlanningUI = False
                slicer.util.errorDisplay(str(exc))
        else:
            if not self._confirmAndDeleteTrajectoryDependents(
                trajectoryNode,
                _("unlock and revise its Entry/Target points"),
            ):
                self._updatingPlanningUI = True
                try:
                    self.ui.lockTrajectoryButton.checked = True
                finally:
                    self._updatingPlanningUI = False
                trajectoryNode.SetLocked(True)
                return
            trajectoryNode.SetLocked(False)
        self._updatePlanning()
