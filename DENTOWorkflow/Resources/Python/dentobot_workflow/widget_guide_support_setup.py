"""Extracted guide support setup methods; public APIs remain on GuideSupportWidgetMixin."""

from __future__ import annotations

from .runtime import *


class GuideSupportSetupWidgetMixin:
    def _clearTemplateModeling(self) -> None:
        if not hasattr(self, "ui"):
            return
        self._updatingTemplateUI = True
        try:
            self._templateSupportRecordsById = {}
            self._templateStatusWarning = ""
            self.ui.templateTargetToothValueLabel.text = _("--")
            self._updateLineageBadge(
                self.ui.templateModelingLineageLabel,
                None,
                _("Step 4A → Step 4B → Step 5A"),
                _(
                    "Target lineage: create a Step 4A trajectory to assign a color."
                ),
            )
            self.ui.templateSupportTeethListWidget.clear()
            self.ui.templateSupportTeethListWidget.enabled = False
            self._rebuildTemplateSupportArchSelector(None, [], [])
            self._reviseTemplateSupportPackageButton.enabled = False
            self._reviseTemplateSupportPackageButton.text = _(
                "Revise locked support package…"
            )
            self._templateSupportPackageSummaryLabel.text = _(
                "No locked Step 4B support package is available."
            )
            self._templateSupportPackageSummaryLabel.styleSheet = (
                "QLabel { color: #b36b00; background: #fff5df; "
                "border-left: 6px solid #b36b00; padding: 6px; }"
            )
            self._templateSupportPackageDetailsLabel.text = ""
            self.ui.draftTemplateSupportModelSelector.setCurrentNode(None)
            self.ui.templateSupportBoundaryCurveSelector.setCurrentNode(None)
            self.ui.templateSupportBoundaryPlaneSelector.setCurrentNode(None)
            self.ui.visibleTemplateSupportModelSelector.setCurrentNode(None)
            self.ui.templateSupportDirectionValueLabel.text = _(
                "Select a complete target trajectory in Step 4A."
            )
            self.ui.flipTemplateSupportDirectionButton.checked = False
            self.ui.flipTemplateSupportDirectionButton.enabled = False
            self.ui.createDraftTemplateSupportModelButton.enabled = False
            self.ui.createDraftTemplateSupportModelButton.text = _(
                "Create Draft Support Model"
            )
            self.ui.createDraftTemplateSupportModelButton.toolTip = _(
                "Create one draft model from the reviewed target and checked "
                "support teeth. Source segmentation surfaces are not modified."
            )
            self.ui.reviewSegmentationForTemplateButton.visible = False
            self.ui.reviewSegmentationForTemplateButton.enabled = False
            self.ui.deleteDraftTemplateSupportModelButton.enabled = False
            self.ui.focusTemplateSupportButton.enabled = False
            self.ui.frameTemplateSupportButton.enabled = False
            self.ui.restoreTemplateSupportFocusButton.enabled = False
            self.ui.createTemplateSupportBoundaryButton.enabled = False
            self.ui.createTemplateSupportPlaneButton.enabled = False
            self.ui.generateTemplateSupportBoundaryFromPlaneButton.enabled = False
            self.ui.generateVisibleTemplateSupportModelButton.enabled = False
            self.ui.deleteTemplateSupportSelectionButton.enabled = False
            self.ui.templateModelingStatusLabel.text = _(
                "Select a reviewed dental segmentation and target tooth."
            )
            self.ui.templateModelingStatusLabel.styleSheet = "color: #b36b00;"
            self.ui.templateSupportSurfaceStatusLabel.text = _(
                "Create the full support model, then draw a closed boundary "
                "around the erupted support surfaces."
            )
            self.ui.templateSupportSurfaceStatusLabel.styleSheet = "color: #b36b00;"
        finally:
            self._updatingTemplateUI = False

    def _bindTemplateSupportBoundaryNode(self, curveNode) -> None:
        """Observe the editable visible-support boundary exactly once."""

        if curveNode is self._templateSupportBoundaryNode:
            return
        if self._templateSupportBoundaryNode:
            self.removeObserver(
                self._templateSupportBoundaryNode,
                vtk.vtkCommand.ModifiedEvent,
                self._onTemplateSupportBoundaryModified,
            )
        self._templateSupportBoundaryNode = curveNode
        if curveNode:
            self.addObserver(
                curveNode,
                vtk.vtkCommand.ModifiedEvent,
                self._onTemplateSupportBoundaryModified,
            )

    def _bindTemplateInsertionDirectionNode(self, lineNode) -> None:
        """Observe the editable Approach-to-Seat insertion line exactly once."""

        if lineNode is self._templateInsertionDirectionNode:
            return
        if self._templateInsertionDirectionNode:
            self.removeObserver(
                self._templateInsertionDirectionNode,
                vtk.vtkCommand.ModifiedEvent,
                self._onTemplateInsertionDirectionModified,
            )
        self._templateInsertionDirectionNode = lineNode
        if lineNode:
            self.addObserver(
                lineNode,
                vtk.vtkCommand.ModifiedEvent,
                self._onTemplateInsertionDirectionModified,
            )

    def _invalidateTemplateUndercutDownstream(self, reason: str) -> bool:
        if not self._parameterNode or not self.logic:
            return False
        changed = self.logic.markTemplateUndercutOutputsStale(
            self._parameterNode.templateUndercutSurfaceModel,
            self._parameterNode.templateUndercutBlockoutModel,
            reason,
        )
        changed = self.logic.markPatientContactShellStale(
            self._parameterNode.patientContactShellModel,
            reason,
        ) or changed
        changed = self.logic.markFinalPrintableTemplateStale(
            self._parameterNode.finalPrintableTemplateModel,
            reason,
        ) or changed
        changed = self.logic.markFinalizedTemplateShellStale(
            self._parameterNode.finalizedTemplateShellModel,
            reason,
        ) or changed
        return changed

    def _onTemplateInsertionDirectionModified(self, caller=None, event=None) -> None:
        del event
        if (
            self._restoringTemplateInsertionDirection
            or not self._parameterNode
            or caller is not self._parameterNode.templateInsertionDirection
        ):
            return
        self._invalidateTemplateUndercutDownstream(
            _("The template insertion direction changed."),
        )
        qt.QTimer.singleShot(0, self._updateTemplateGuide)

    def _bindSelectedGuideTrajectoryNodes(self, trajectoryNodes: list) -> None:
        oldIds = {node.GetID() for node in self._guideTrajectoryObserverNodes if node}
        newIds = {node.GetID() for node in trajectoryNodes if node}
        if oldIds == newIds:
            return
        for node in self._guideTrajectoryObserverNodes:
            self.removeObserver(
                node,
                vtk.vtkCommand.ModifiedEvent,
                self._onSelectedGuideTrajectoryModified,
            )
        self._guideTrajectoryObserverNodes = list(trajectoryNodes)
        for node in self._guideTrajectoryObserverNodes:
            self.addObserver(
                node,
                vtk.vtkCommand.ModifiedEvent,
                self._onSelectedGuideTrajectoryModified,
            )

    def _onSelectedGuideTrajectoryModified(self, caller=None, event=None) -> None:
        del event
        if not self._parameterNode or caller not in self._guideTrajectoryObserverNodes:
            return
        reason = _("A source guide trajectory changed.")
        try:
            dockingSummary = self.logic.getTargetDockingAssemblySummary(
                self._parameterNode.targetDockingAssemblyModel
            )
            if caller in dockingSummary["trajectories"]:
                trajectoryGeometry = []
                for node in dockingSummary["trajectories"]:
                    trajectorySummary = self.logic.getTrajectorySummary(node)
                    trajectoryGeometry.append(
                        {
                            "entryRas": [
                                float(value)
                                for value in trajectorySummary["entryRas"]
                            ],
                            "targetRas": [
                                float(value)
                                for value in trajectorySummary["targetRas"]
                            ],
                        }
                    )
                currentGeometryJson = json.dumps(
                    trajectoryGeometry,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                if (
                    currentGeometryJson
                    == dockingSummary["trajectoryGeometryJson"]
                ):
                    # Markups also emits ModifiedEvent for scene restoration,
                    # lock state, labels, and display-only changes. Those are
                    # not trajectory geometry changes and must not invalidate
                    # the Step 4B/4C/5B chain.
                    return
                self.logic.markTargetDockingAssemblyStale(
                    self._parameterNode.targetDockingAssemblyModel,
                    reason,
                )
        except (RuntimeError, ValueError, json.JSONDecodeError):
            pass
        self.logic.markFinalPrintableTemplateStale(
            self._parameterNode.finalPrintableTemplateModel,
            reason,
        )
        qt.QTimer.singleShot(0, self._updateTargetDocking)
        qt.QTimer.singleShot(0, self._updateTemplateGuide)

    def _invalidateTemplateSupportSurfaceDownstream(self, reason: str) -> bool:
        if not self._parameterNode or not self.logic:
            return False
        changed = self.logic.markVisibleTemplateSupportModelStale(
            self._parameterNode.visibleTemplateSupportModel,
            reason,
        )
        changed = self.logic.markTemplateUndercutOutputsStale(
            self._parameterNode.templateUndercutSurfaceModel,
            self._parameterNode.templateUndercutBlockoutModel,
            reason,
        ) or changed
        changed = self.logic.markPatientContactShellStale(
            self._parameterNode.patientContactShellModel,
            reason,
        ) or changed
        changed = self.logic.markFinalPrintableTemplateStale(
            self._parameterNode.finalPrintableTemplateModel,
            reason,
        ) or changed
        changed = self.logic.markResearchTemplateModelsStale(
            self._parameterNode.researchTemplateShellModel,
            self._parameterNode.researchTemplateSleeveModel,
            reason,
        ) or changed
        changed = self.logic.markFinalizedTemplateShellStale(
            self._parameterNode.finalizedTemplateShellModel,
            reason,
        ) or changed
        return changed

    def _onTemplateSupportBoundaryModified(self, caller=None, event=None) -> None:
        del event
        if (
            self._restoringTemplateSupportBoundary
            or not self._parameterNode
            or caller is not self._parameterNode.templateSupportBoundaryCurve
        ):
            return
        previewModel = self._parameterNode.visibleTemplateSupportModel
        if self.logic.isVisibleTemplateSupportModelNode(previewModel):
            try:
                previewSummary = self.logic.getVisibleTemplateSupportModelSummary(
                    previewModel
                )
                if (
                    previewSummary["boundary"] is caller
                    and self.logic.templateSupportBoundaryMatchesGeometryJson(
                        caller,
                        previewSummary["boundaryGeometryJson"],
                    )
                ):
                    # Ignore non-geometric Markups modifications emitted while
                    # restoring a scene or changing display/lock state.
                    return
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass
        self._invalidateTemplateSupportSurfaceDownstream(
            _("The visible support boundary changed."),
        )
        qt.QTimer.singleShot(0, self._updateTemplateModeling)

    def _markCurrentDraftTemplateModelStale(self, reason: str) -> bool:
        if not self._parameterNode or not self.logic:
            return False
        changed = self.logic.markDraftTemplateSupportModelStale(
            self._parameterNode.draftTemplateSupportModel,
            reason,
        )
        changed = self.logic.markTargetDockingAssemblyStale(
            self._parameterNode.targetDockingAssemblyModel,
            reason,
        ) or changed
        return self._invalidateTemplateSupportSurfaceDownstream(reason) or changed

    def _selectedTemplateSupportSegmentIds(self) -> list[str]:
        selectedIds = []
        listWidget = self.ui.templateSupportTeethListWidget
        for itemIndex in range(listWidget.count):
            item = listWidget.item(itemIndex)
            segmentId = item.data(qt.Qt.UserRole)
            if segmentId and item.checkState() == qt.Qt.Checked:
                selectedIds.append(str(segmentId))
        return selectedIds

    def _updateTemplateSupportPackageSummary(
        self,
        targetRecord: dict | None,
        persistedSupportIds: list[str],
        modelNode,
        modelSummary: dict | None,
        modelError: str,
    ) -> None:
        """Render the Step 4B parent as a read-only Step 5A input package."""

        if not self._templateSupportPackageWidget:
            return
        selectionLocked = self.logic.isTemplateSupportSelectionLocked(modelNode)
        geometryCurrent = bool(
            modelSummary and modelSummary["geometryState"] == "Current"
        )
        if selectionLocked and geometryCurrent:
            summary = _(
                "Ready: this support package is locked in Step 4B and is the "
                "only support-tooth input used by Step 5A."
            )
            style = (
                "QLabel { color: #207227; background: #e8f5e9; "
                "border-left: 6px solid #207227; padding: 6px; }"
            )
        elif modelError:
            summary = _("Blocked: the Step 4B support package is invalid: %1").replace(
                "%1", modelError
            )
            style = (
                "QLabel { color: #b00020; background: #fdecef; "
                "border-left: 6px solid #b00020; padding: 6px; }"
            )
        elif modelSummary and not selectionLocked:
            summary = _(
                "Blocked: support-tooth selection is unlocked for revision. "
                "Return to Step 4B and update the draft to lock it again."
            )
            style = (
                "QLabel { color: #b36b00; background: #fff5df; "
                "border-left: 6px solid #b36b00; padding: 6px; }"
            )
        elif modelSummary:
            summary = _(
                "Blocked: the locked Step 4B support package is stale. Return "
                "to Step 4B and update it before continuing."
            )
            style = (
                "QLabel { color: #b36b00; background: #fff5df; "
                "border-left: 6px solid #b36b00; padding: 6px; }"
            )
        else:
            summary = _(
                "Blocked: no locked Step 4B support package is available."
            )
            style = (
                "QLabel { color: #b36b00; background: #fff5df; "
                "border-left: 6px solid #b36b00; padding: 6px; }"
            )

        supportIds = (
            modelSummary["supportSegmentIds"]
            if modelSummary
            else persistedSupportIds
        )
        targetName = (
            targetRecord.get("displayName")
            if targetRecord
            else (modelSummary or {}).get("targetSegmentId", "")
        ) or _("Not selected")
        supportNames = []
        for segmentId in supportIds:
            record = self._targetToothRecordsById.get(segmentId)
            supportNames.append(
                str(record.get("displayName")) if record else str(segmentId)
            )
        modelName = modelNode.GetName() if modelNode else _("Not created")
        stateText = (
            modelSummary["geometryState"]
            if modelSummary
            else _("Unavailable")
        )
        lockText = _("Locked") if selectionLocked else _("Unlocked")
        details = (
            _("Target: %1\nSupport teeth (%2): %3\nDraft: %4\nState: %5 • %6")
            .replace("%1", str(targetName))
            .replace("%2", str(len(supportNames)))
            .replace("%3", ", ".join(supportNames) or _("None"))
            .replace("%4", str(modelName))
            .replace("%5", str(stateText))
            .replace("%6", lockText)
        )
        self._templateSupportPackageSummaryLabel.text = summary
        self._templateSupportPackageSummaryLabel.styleSheet = style
        self._templateSupportPackageDetailsLabel.text = details

    def _startTemplateSupportBoundaryFocus(self) -> None:
        """Temporarily show only the tooth masks used by the support boundary."""

        if not self._parameterNode or not self.logic:
            raise RuntimeError(_("DENTOWorkflow is not ready for boundary placement."))
        self._restoreTemplateSupportBoundaryFocus(updateUi=False)
        contextModels = [
            self._parameterNode.draftTemplateSupportModel,
            self._parameterNode.visibleTemplateSupportModel,
        ]
        self._templateSupportBoundaryFocusState = (
            self.logic.applyTemplateSupportBoundaryFocus(
                self._parameterNode.teethSegmentation,
                self._parameterNode.draftTemplateSupportModel,
                contextModels=contextModels,
            )
        )
        self._syncSegmentationDisplayControls()
        self.ui.restoreTemplateSupportFocusButton.enabled = True

    def onFocusTemplateSupport(self) -> None:
        try:
            self._startTemplateSupportBoundaryFocus()
            self.onFrameTemplateSupport()
        except (RuntimeError, ValueError) as exc:
            self._restoreTemplateSupportBoundaryFocus(updateUi=False)
            slicer.util.errorDisplay(str(exc))

    def onFrameTemplateSupport(self) -> None:
        if not self._parameterNode:
            return
        modelNode = self._parameterNode.draftTemplateSupportModel
        if not modelNode or not modelNode.IsA("vtkMRMLModelNode"):
            slicer.util.errorDisplay(
                _("Create or select the Step 4B draft support model first.")
            )
            return
        bounds = [0.0] * 6
        modelNode.GetRASBounds(bounds)
        try:
            self._frameRasBoundsInViews(bounds)
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onRestoreTemplateSupportFocus(self) -> None:
        self._restoreTemplateSupportBoundaryFocus(updateUi=True)

    def _restoreTemplateSupportBoundaryFocus(self, updateUi: bool = True) -> None:
        """Restore the exact segmentation/model display state saved for Step 5A."""

        state = self._templateSupportBoundaryFocusState
        self._templateSupportBoundaryFocusState = None
        if not state or not self.logic:
            if hasattr(self, "ui"):
                self.ui.restoreTemplateSupportFocusButton.enabled = False
            return
        self.logic.restoreTemplateSupportBoundaryFocus(state)
        if hasattr(self, "ui"):
            self.ui.restoreTemplateSupportFocusButton.enabled = False
        if (
            updateUi
            and not self._isCleaningUp
            and hasattr(self, "ui")
            and self._reviewSegmentationNode
        ):
            self._syncSegmentationDisplayControls()

    def _updateTemplateModeling(self) -> None:
        if self._isCleaningUp or self._updatingTemplateUI:
            return
        if not self._parameterNode or not self.logic:
            self._clearTemplateModeling()
            return

        segmentationNode = self._parameterNode.teethSegmentation
        targetSegmentId = self._parameterNode.targetToothSegmentId
        targetRecord = self._targetToothRecordsById.get(targetSegmentId)
        modelNode = self._parameterNode.draftTemplateSupportModel
        self.logic.refreshWorkflowLineageColors()
        persistedSelectionError = ""
        archSelectionWarning = ""
        try:
            persistedSupportIds = self.logic.decodeTemplateSupportSegmentIds(
                self._parameterNode.templateSupportToothSegmentIdsJson
            )
        except ValueError as exc:
            persistedSupportIds = []
            persistedSelectionError = str(exc)

        # A locked current Step 4B model carries redundant selection
        # provenance.  Recover the parameter JSON from that parent on legacy
        # or partially-restored scenes, but never overwrite an intentionally
        # unlocked revision or a malformed saved value.
        if (
            not persistedSelectionError
            and not persistedSupportIds
            and self.logic.isDraftTemplateSupportModelNode(modelNode)
            and self.logic.isTemplateSupportSelectionLocked(modelNode)
        ):
            try:
                savedModelSummary = self.logic.getDraftTemplateSupportModelSummary(
                    modelNode
                )
                if (
                    savedModelSummary["geometryState"] == "Current"
                    and savedModelSummary["sourceSegmentation"] is segmentationNode
                    and savedModelSummary["targetSegmentId"] == targetSegmentId
                    and savedModelSummary["supportSegmentIds"]
                ):
                    persistedSupportIds = list(
                        savedModelSummary["supportSegmentIds"]
                    )
                    self._updatingTemplateUI = True
                    try:
                        self._parameterNode.templateSupportToothSegmentIdsJson = (
                            self.logic.encodeTemplateSupportSegmentIds(
                                persistedSupportIds
                            )
                        )
                    finally:
                        self._updatingTemplateUI = False
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass

        targetFdi = str(targetRecord.get("fdiNumber") or "") if targetRecord else ""
        targetArch = self.logic.dentalArchForFdi(targetFdi)
        sameArchRecords = [
            record
            for record in self._targetToothRecordsById.values()
            if self.logic.dentalArchForFdi(record.get("fdiNumber") or "")
            == targetArch
        ] if targetArch else []
        sameArchIds = {record["segmentId"] for record in sameArchRecords}
        removedOpposingArchIds = [
            segmentId
            for segmentId in persistedSupportIds
            if segmentId in self._targetToothRecordsById
            and segmentId not in sameArchIds
        ]
        if removedOpposingArchIds:
            persistedSupportIds = [
                segmentId
                for segmentId in persistedSupportIds
                if segmentId not in removedOpposingArchIds
            ]
            archSelectionWarning = _(
                "Opposing-jaw teeth were removed from the saved support "
                "selection because supports must share the target arch."
            )
            self._updatingTemplateUI = True
            try:
                self._parameterNode.templateSupportToothSegmentIdsJson = (
                    self.logic.encodeTemplateSupportSegmentIds(
                        persistedSupportIds
                    )
                )
            finally:
                self._updatingTemplateUI = False

        invalidSupportIds = [
            segmentId
            for segmentId in persistedSupportIds
            if (
                segmentId == targetSegmentId
                or segmentId not in self._targetToothRecordsById
            )
        ]
        availableRecords = [
            record
            for record in sameArchRecords
            if record["segmentId"] != targetSegmentId
        ]
        archOrder = {
            fdiNumber: index
            for index, fdiNumber in enumerate(
                sum((list(row) for row in self._templateSupportArchRows(targetFdi)), [])
            )
        }
        availableRecords.sort(
            key=lambda record: archOrder.get(
                str(record.get("fdiNumber") or ""),
                999,
            )
        )
        self._templateSupportRecordsById = {
            record["segmentId"]: record for record in availableRecords
        }

        self._updatingTemplateUI = True
        try:
            self.ui.templateTargetToothValueLabel.text = (
                targetRecord["displayName"] if targetRecord else _("--")
            )
            listWidget = self.ui.templateSupportTeethListWidget
            listWidget.clear()
            for record in availableRecords:
                item = qt.QListWidgetItem(record["displayName"])
                item.setData(qt.Qt.UserRole, record["segmentId"])
                item.setToolTip(
                    _("Source label: %1").replace(
                        "%1",
                        record["sourceName"],
                    )
                )
                item.setCheckState(
                    qt.Qt.Checked
                    if record["segmentId"] in persistedSupportIds
                    else qt.Qt.Unchecked
                )
                listWidget.addItem(item)
            listWidget.enabled = bool(targetRecord and availableRecords)
            self._rebuildTemplateSupportArchSelector(
                targetRecord,
                availableRecords,
                persistedSupportIds,
            )
            if self.ui.draftTemplateSupportModelSelector.currentNode() is not modelNode:
                self.ui.draftTemplateSupportModelSelector.setCurrentNode(
                    modelNode
                )
        finally:
            self._updatingTemplateUI = False

        lineageNode = self._lineageSourceNode(
            (
                modelNode,
                self._parameterNode.trajectoryLine,
                self._parameterNode.targetToothBoundsRoi,
            ),
            targetSegmentId,
        )
        self._updateLineageBadge(
            self.ui.templateModelingLineageLabel,
            lineageNode,
            _("Step 4A → Step 4B → Step 5A"),
            _(
                "Target lineage: create a Step 4A trajectory to assign a color."
            ),
        )
        self._updateNodeSelectorLineageSwatches(
            self.ui.draftTemplateSupportModelSelector,
            self.logic.isDraftTemplateSupportModelNode,
        )

        selectedSupportIds = self._selectedTemplateSupportSegmentIds()
        modelSummary = None
        modelError = ""
        if modelNode:
            try:
                modelSummary = self.logic.getDraftTemplateSupportModelSummary(
                    modelNode
                )
            except ValueError as exc:
                modelError = str(exc)

        if modelSummary:
            automaticSelectionStaleReason = _(
                "Current target or support-tooth selection differs."
            )
            selectionDiffers = bool(
                modelSummary["sourceSegmentation"] is not segmentationNode
                or modelSummary["targetSegmentId"] != targetSegmentId
                or set(modelSummary["supportSegmentIds"])
                != set(persistedSupportIds)
            )
            if selectionDiffers:
                self.logic.markDraftTemplateSupportModelStale(
                    modelNode,
                    automaticSelectionStaleReason,
                )
                modelSummary = self.logic.getDraftTemplateSupportModelSummary(
                    modelNode
                )

            elif (
                modelSummary["geometryState"] == "Stale"
                and modelSummary["staleReason"] == automaticSelectionStaleReason
            ):
                # A scene-load UI refresh can transiently expose an empty list.
                # The persisted IDs and model provenance are authoritative; if
                # they agree again, clear only this automatically-created stale
                # state. Never clear content/edit staleness here.
                modelNode.SetAttribute("DENTOBOT.GeometryState", "Current")
                modelNode.SetAttribute("DENTOBOT.StaleReason", None)
                modelSummary = self.logic.getDraftTemplateSupportModelSummary(
                    modelNode
                )

        selectionLocked = self.logic.isTemplateSupportSelectionLocked(modelNode)
        if (
            selectionLocked
            and modelNode
            and modelNode.GetAttribute("DENTOBOT.SupportSelectionLocked") is None
        ):
            # Make the legacy default explicit so the lock survives future
            # package exports without depending on compatibility behavior.
            modelNode.SetAttribute("DENTOBOT.SupportSelectionLocked", "true")
        selectionEditable = bool(
            targetRecord and availableRecords and not selectionLocked
        )
        self.ui.templateSupportTeethListWidget.enabled = selectionEditable
        for supportButton in self._templateSupportButtonsBySegmentId.values():
            supportButton.enabled = selectionEditable
        self._reviseTemplateSupportPackageButton.enabled = bool(
            modelSummary and selectionLocked
        )
        self._reviseTemplateSupportPackageButton.text = (
            _("Revise locked support package…")
            if selectionLocked
            else _("Selection unlocked — update the draft to lock")
        )
        if modelSummary and selectionLocked:
            self._templateSupportArchStatusLabel.text += _(
                " Package locked; use Revise before changing membership."
            )
        elif modelSummary:
            self._templateSupportArchStatusLabel.text += _(
                " Package unlocked; update the draft to lock the new membership."
            )

        self._updateTemplateSupportPackageSummary(
            targetRecord,
            persistedSupportIds,
            modelNode,
            modelSummary,
            modelError,
        )

        reviewState = (
            self.logic.getSegmentationReviewState(segmentationNode)
            if segmentationNode
            else ""
        )
        canCreate = bool(
            segmentationNode
            and targetRecord
            and selectedSupportIds
            and reviewState == "Reviewed"
            and not persistedSelectionError
            and not invalidSupportIds
            and not modelError
        )
        self.ui.createDraftTemplateSupportModelButton.enabled = canCreate
        self.ui.createDraftTemplateSupportModelButton.text = (
            _("Update Draft Support Model")
            if modelSummary
            else _("Create Draft Support Model")
        )
        needsReview = bool(segmentationNode and reviewState != "Reviewed")
        self.ui.reviewSegmentationForTemplateButton.visible = needsReview
        self.ui.reviewSegmentationForTemplateButton.enabled = needsReview
        self.ui.reviewSegmentationForTemplateButton.text = (
            _("Open Segmentation Review (%1)").replace(
                "%1",
                reviewState or _("Unreviewed"),
            )
        )
        if needsReview:
            self.ui.createDraftTemplateSupportModelButton.toolTip = _(
                "Blocked because the authoritative segmentation is %1. "
                "Open Segmentation Review, inspect it, and explicitly set "
                "Review state to Reviewed."
            ).replace("%1", reviewState or _("Unreviewed"))
        else:
            self.ui.createDraftTemplateSupportModelButton.toolTip = _(
                "Create or explicitly update one draft model from the target "
                "and all checked support teeth. Source segmentation surfaces "
                "are not modified."
            )
        self.ui.deleteDraftTemplateSupportModelButton.enabled = bool(
            modelNode
            and self.logic.isDraftTemplateSupportModelNode(modelNode)
        )
        hasSupportModel = bool(
            modelNode
            and self.logic.isDraftTemplateSupportModelNode(modelNode)
        )
        self.ui.focusTemplateSupportButton.enabled = hasSupportModel
        self.ui.frameTemplateSupportButton.enabled = hasSupportModel
        self.ui.restoreTemplateSupportFocusButton.enabled = bool(
            self._templateSupportBoundaryFocusState
        )

        if not segmentationNode:
            message = _("Select the authoritative dental segmentation.")
            style = "color: #b36b00;"
        elif not targetRecord:
            message = _("Select a target tooth in Step 4A.")
            style = "color: #b36b00;"
        elif persistedSelectionError:
            message = persistedSelectionError
            style = "color: #b00020;"
        elif invalidSupportIds:
            message = _(
                "The saved support selection contains unavailable or invalid "
                "whole-tooth segments: %1"
            ).replace("%1", ", ".join(invalidSupportIds))
            style = "color: #b00020;"
        elif archSelectionWarning:
            message = archSelectionWarning
            style = "color: #b36b00;"
        elif self._templateStatusWarning:
            message = self._templateStatusWarning
            style = "color: #b36b00;"
        elif not availableRecords:
            message = _(
                "No additional whole-tooth segments are available as supports."
            )
            style = "color: #b00020;"
        elif reviewState != "Reviewed":
            message = (
                _(
                    "Blocked: this segmentation is %1. Your %2 checked support "
                    "teeth are valid and preserved. Select Open Segmentation "
                    "Review, inspect the result, and set Review state to "
                    "Reviewed before creating derived template geometry."
                )
                .replace("%1", reviewState or _("Unreviewed"))
                .replace("%2", str(len(selectedSupportIds)))
            )
            style = "color: #b36b00;"
        elif not selectedSupportIds:
            message = _(
                "Click one or more available teeth in the same-jaw arch map. "
                "The highlighted target tooth is always included and cannot "
                "be toggled."
            )
            style = "color: #1f5f99;"
        elif modelError:
            message = modelError
            style = "color: #b00020;"
        elif modelSummary and modelSummary["geometryState"] == "Current":
            message = (
                _(
                    "Draft model is current for %1 manually selected support "
                    "teeth (%2 points, %3 cells)."
                )
                .replace("%1", str(len(selectedSupportIds)))
                .replace("%2", str(modelSummary["pointCount"]))
                .replace("%3", str(modelSummary["cellCount"]))
            )
            style = "color: #207227;"
        elif modelSummary:
            reason = modelSummary["staleReason"] or _(
                "The source selection changed."
            )
            message = (
                _("Draft model is stale: %1 Select Update to regenerate it.")
                .replace("%1", reason)
            )
            style = "color: #b36b00;"
        else:
            message = (
                _("Ready to create a draft model from the target and %1 support teeth.")
                .replace("%1", str(len(selectedSupportIds)))
            )
            style = "color: #1f5f99;"

        self.ui.templateModelingStatusLabel.text = message
        self.ui.templateModelingStatusLabel.styleSheet = style
        self._updateVisibleTemplateSupportSurfaceControls(modelSummary)
