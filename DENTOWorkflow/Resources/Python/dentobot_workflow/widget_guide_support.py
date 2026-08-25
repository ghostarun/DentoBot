"""Extracted guide support UI methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from .runtime import *


from dentobot_workflow.widget_guide_support_setup import GuideSupportSetupWidgetMixin


class GuideSupportWidgetMixin(GuideSupportSetupWidgetMixin):


















    def onReviewSegmentationForTemplate(self) -> None:
        """Reveal the authoritative review gate without approving it implicitly."""

        if not self._parameterNode or not self.logic:
            return
        segmentationNode = self._parameterNode.teethSegmentation
        if not segmentationNode:
            slicer.util.errorDisplay(
                _("Select the authoritative dental segmentation first.")
            )
            return
        if self.ui.reviewSegmentationSelector.currentNode() is not segmentationNode:
            self.ui.reviewSegmentationSelector.setCurrentNode(segmentationNode)
        self.ui.templateModelingCollapsibleButton.collapsed = True
        self.ui.segmentationReviewCollapsibleButton.collapsed = False

        def focusReviewState() -> None:
            self.ui.reviewStateComboBox.setFocus(qt.Qt.OtherFocusReason)
            ancestor = self.ui.reviewStateComboBox.parent()
            while ancestor:
                if ancestor.inherits("QScrollArea"):
                    ancestor.ensureWidgetVisible(
                        self.ui.reviewStateComboBox,
                        20,
                        20,
                    )
                    break
                ancestor = ancestor.parent()

        qt.QTimer.singleShot(0, focusReviewState)

    def _updateVisibleTemplateSupportSurfaceControls(
        self,
        sourceSummary: dict | None,
    ) -> None:
        if not self._parameterNode or not self.logic:
            return
        sourceModel = self._parameterNode.draftTemplateSupportModel
        curveNode = self._parameterNode.templateSupportBoundaryCurve
        planeNode = self._parameterNode.templateSupportBoundaryPlane
        previewModel = self._parameterNode.visibleTemplateSupportModel
        directionTrajectory = self._parameterNode.trajectoryLine
        reverseDirection = bool(
            self._parameterNode.templateSupportDirectionReversed
        )
        spacing = float(self._parameterNode.templateSupportCurveSamplingSpacingMm)
        terminalCoveragePercent = float(
            self._parameterNode.templateTerminalSupportCoveragePercent
        )

        self._updatingTemplateUI = True
        try:
            if self.ui.templateSupportBoundaryCurveSelector.currentNode() is not curveNode:
                self.ui.templateSupportBoundaryCurveSelector.setCurrentNode(curveNode)
            if self.ui.templateSupportBoundaryPlaneSelector.currentNode() is not planeNode:
                self.ui.templateSupportBoundaryPlaneSelector.setCurrentNode(planeNode)
            if self.ui.visibleTemplateSupportModelSelector.currentNode() is not previewModel:
                self.ui.visibleTemplateSupportModelSelector.setCurrentNode(previewModel)
            self.ui.flipTemplateSupportDirectionButton.checked = reverseDirection
        finally:
            self._updatingTemplateUI = False

        directionSummary = None
        directionError = ""
        if sourceModel:
            try:
                directionSummary = self.logic.resolveTemplateSupportTrajectoryDirection(
                    sourceModel,
                    directionTrajectory,
                    reverseDirection=reverseDirection,
                )
            except (RuntimeError, ValueError) as exc:
                directionError = str(exc)
        else:
            directionError = _("Create the full support-anatomy model first.")
        self._updatingTemplateUI = True
        try:
            self.ui.flipTemplateSupportDirectionButton.enabled = bool(
                directionSummary
            )
            if directionSummary and reverseDirection:
                self.ui.templateSupportDirectionValueLabel.text = _(
                    "Override active: Target → Entry points toward the roots; "
                    "the opposite selects the crown side on every tooth."
                )
            elif directionSummary:
                self.ui.templateSupportDirectionValueLabel.text = _(
                    "Automatic: Entry → Target points toward the roots; the "
                    "opposite selects the crown side on every tooth."
                )
            else:
                self.ui.templateSupportDirectionValueLabel.text = directionError
        finally:
            self._updatingTemplateUI = False

        curveError = ""
        curveGeometryJson = ""
        if curveNode:
            try:
                self.logic.validateTemplateSupportBoundary(sourceModel, curveNode)
                curveGeometryJson = self.logic.templateSupportBoundaryGeometryJson(
                    curveNode
                )
            except (RuntimeError, ValueError) as exc:
                curveError = str(exc)

        planeError = ""
        if planeNode:
            try:
                self.logic.validateTemplateSupportBoundaryPlane(
                    sourceModel,
                    planeNode,
                    directionTrajectory,
                )
                if (
                    directionSummary
                    and planeNode.GetAttribute("DENTOBOT.DirectionGeometryJson")
                    != directionSummary["directionGeometryJson"]
                ):
                    raise ValueError(
                        _(
                            "The target trajectory or polarity changed. Reset "
                            "the insertion-aligned support plane."
                        )
                    )
                if not math.isclose(
                    float(
                        planeNode.GetAttribute("DENTOBOT.DepthFromEntryMm")
                        or "nan"
                    ),
                    float(self._parameterNode.templateSupportPlaneDepthMm),
                    rel_tol=0.0,
                    abs_tol=1e-8,
                ):
                    raise ValueError(
                        _("The support-plane depth changed. Reset the support plane.")
                    )
                if not math.isclose(
                    float(
                        planeNode.GetAttribute("DENTOBOT.CrownCapPercent")
                        or "nan"
                    ),
                    float(self._parameterNode.templateSupportCrownCapPercent),
                    rel_tol=0.0,
                    abs_tol=1e-8,
                ):
                    raise ValueError(
                        _(
                            "The crown-cap tilt fit changed. Reset the support plane."
                        )
                    )
            except (RuntimeError, ValueError) as exc:
                planeError = str(exc)

        previewSummary = None
        previewError = ""
        if previewModel:
            try:
                previewSummary = self.logic.getVisibleTemplateSupportModelSummary(
                    previewModel
                )
            except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                previewError = str(exc)

        if previewSummary:
            staleReason = ""
            if previewSummary["sourceModel"] is not sourceModel:
                staleReason = _("The selected full support model changed.")
            elif previewSummary["boundary"] is not curveNode:
                staleReason = _("The selected visible support boundary changed.")
            elif not sourceSummary or sourceSummary["geometryState"] != "Current":
                staleReason = _("The full support-anatomy model is stale.")
            elif previewSummary["sourceModelUpdatedUtc"] != (
                sourceModel.GetAttribute("DENTOBOT.UpdatedUtc") or ""
            ):
                staleReason = _("The full support-anatomy geometry was updated.")
            elif curveGeometryJson and not self.logic.templateSupportBoundaryMatchesGeometryJson(
                curveNode,
                previewSummary["boundaryGeometryJson"],
            ):
                staleReason = _("The visible support boundary geometry changed.")
            elif previewSummary["selectionMode"] != "TrajectoryDirection":
                staleReason = _(
                    "This legacy preview used area-based side selection."
                )
            elif not directionSummary:
                staleReason = directionError
            elif previewSummary["directionTrajectory"] is not directionTrajectory:
                staleReason = _("The target trajectory used for direction changed.")
            elif (
                previewSummary["directionGeometryJson"]
                != directionSummary["directionGeometryJson"]
            ):
                staleReason = _("The target trajectory points or polarity changed.")
            elif previewSummary["directionReversed"] != reverseDirection:
                staleReason = _("The crown/root direction polarity changed.")
            elif not math.isclose(
                previewSummary["samplingSpacingMm"],
                spacing,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                staleReason = _("The boundary sampling spacing changed.")
            elif not math.isclose(
                previewSummary["terminalSupportCoveragePercent"],
                terminalCoveragePercent,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                staleReason = _("The terminal support-tooth coverage changed.")
            if staleReason:
                self._invalidateTemplateSupportSurfaceDownstream(staleReason)
                previewSummary = self.logic.getVisibleTemplateSupportModelSummary(
                    previewModel
                )
            elif (
                previewSummary["geometryState"] == "Stale"
                and previewSummary["staleReason"]
                in {
                    _(
                        "The support-plane depth or crown-cap tilt fit changed; "
                        "regenerate the boundary and preview."
                    ),
                    _("The visible support boundary changed."),
                }
                and not planeError
            ):
                # A scene-load valueChanged signal used to mark the preview
                # stale even when the saved plane, curve, source model,
                # trajectory, polarity, and processing parameters all still
                # matched. Restore only this known no-op state after every
                # provenance comparison above has succeeded.
                previewModel.SetAttribute("DENTOBOT.GeometryState", "Current")
                previewModel.SetAttribute("DENTOBOT.StaleReason", None)
                previewSummary = self.logic.getVisibleTemplateSupportModelSummary(
                    previewModel
                )

        sourceCurrent = bool(
            sourceSummary and sourceSummary["geometryState"] == "Current"
        )
        curveComplete = bool(curveNode and not curveError and curveGeometryJson)
        planeCurrent = bool(planeNode and not planeError and directionSummary)
        self.ui.createTemplateSupportPlaneButton.enabled = bool(
            sourceCurrent and directionSummary
        )
        self.ui.generateTemplateSupportBoundaryFromPlaneButton.enabled = bool(
            sourceCurrent and planeCurrent and not previewError
        )
        self.ui.createTemplateSupportBoundaryButton.enabled = sourceCurrent
        self.ui.generateVisibleTemplateSupportModelButton.enabled = bool(
            sourceCurrent
            and curveComplete
            and directionSummary
            and not previewError
        )
        self.ui.deleteTemplateSupportSelectionButton.enabled = bool(
            self.logic.isTemplateSupportBoundaryNode(curveNode)
            or self.logic.isTemplateSupportBoundaryPlaneNode(planeNode)
            or self.logic.isVisibleTemplateSupportModelNode(previewModel)
        )

        if not sourceCurrent:
            message = _("Create or update the full support-anatomy model first.")
            style = "color: #b36b00;"
        elif planeError:
            message = planeError
            style = "color: #b36b00;"
        elif curveError:
            message = curveError
            style = "color: #b36b00;"
        elif directionError:
            message = directionError
            style = "color: #b36b00;"
        elif self._templateSupportBoundaryFocusState:
            message = _(
                "Boundary focus is active: only the target and checked support-"
                "tooth masks are shown. Place the closed loop, right-click to "
                "finish, then generate the preview; the prior display will be "
                "restored automatically."
            )
            style = "color: #1f5f99;"
        elif planeNode and not curveNode:
            message = _(
                "The insertion-aligned support plane is ready. Adjust only "
                "Plane depth from Entry, then select Generate Boundary + "
                "Preview. The generated curve remains editable."
            )
            style = "color: #1f5f99;"
        elif not curveNode:
            message = _(
                "Create the insertion-aligned support plane for the automatic "
                "workflow, or use Manual: Draw / Redraw Boundary as a fallback."
            )
            style = "color: #1f5f99;"
        elif not curveComplete:
            message = _(
                "Place at least three points directly on the orange support "
                "surfaces, then right-click to finish the closed loop."
            )
            style = "color: #1f5f99;"
        elif previewError:
            message = previewError
            style = "color: #b00020;"
        elif previewSummary and previewSummary["geometryState"] == "Current":
            selectedToothCount = int(
                previewSummary["metrics"].get(
                    "selectedToothCount",
                    previewSummary["metrics"].get("surfaceRegionCount", 0),
                )
            )
            sourceToothCount = int(
                previewSummary["metrics"].get(
                    "sourceToothCount",
                    previewSummary["metrics"].get("sourceSurfaceRegionCount", 0),
                )
            )
            omittedToothCount = int(
                previewSummary["metrics"].get(
                    "omittedToothCount",
                    max(0, sourceToothCount - selectedToothCount),
                )
            )
            ignoredIslandCount = int(
                previewSummary["metrics"].get("ignoredSourceIslandCount", 0)
            )
            ambiguousCount = sum(
                1
                for item in previewSummary["metrics"].get("toothMetrics", [])
                if item.get("directionSelectionAmbiguous")
            )
            terminalSupport = previewSummary["metrics"].get(
                "terminalSupport",
                {},
            )
            message = (
                _(
                    "Visible support preview is current (%1 points, %2 cells; "
                    "%3 of %4 selected teeth included by trajectory direction)."
                )
                .replace("%1", str(previewSummary["pointCount"]))
                .replace("%2", str(previewSummary["cellCount"]))
                .replace("%3", str(selectedToothCount))
                .replace("%4", str(sourceToothCount))
            )
            warnings = []
            if omittedToothCount:
                warnings.append(
                    _("%1 intended tooth/teeth were not mapped.").replace(
                        "%1",
                        str(omittedToothCount),
                    )
                )
            if ignoredIslandCount:
                warnings.append(
                    _(
                        "%1 extra disconnected mesh island(s) were ignored "
                        "inside their source tooth segments."
                    ).replace("%1", str(ignoredIslandCount))
                )
            if ambiguousCount:
                warnings.append(
                    _("%1 tooth side choice(s) were directionally close.").replace(
                        "%1",
                        str(ambiguousCount),
                    )
                )
            if terminalSupport.get("applied"):
                message += " " + (
                    _(
                        "Inward %1% coverage was applied to terminal support "
                        "tooth/teeth %2."
                    )
                    .replace(
                        "%1",
                        f"{previewSummary['terminalSupportCoveragePercent']:.0f}",
                    )
                    .replace(
                        "%2",
                        ", ".join(
                            terminalSupport.get(
                                "clippedTerminalSegmentIds",
                                [],
                            )
                        ),
                    )
                )
            if warnings:
                message += _(
                    " %1 Inspect the orange preview and review the segmentation "
                    "if ignored islands are unexpected."
                ).replace("%1", " ".join(warnings))
                style = "color: #b36b00;"
            else:
                style = "color: #207227;"
        elif previewSummary:
            message = _("Visible support preview is stale: %1").replace(
                "%1",
                previewSummary["staleReason"] or _("regeneration required"),
            )
            style = "color: #b36b00;"
        else:
            message = _(
                "Boundary and target-trajectory direction are ready. Generate "
                "the preview, then inspect the orange crown-side patches."
            )
            style = "color: #1f5f99;"
        self.ui.templateSupportSurfaceStatusLabel.text = message
        self.ui.templateSupportSurfaceStatusLabel.styleSheet = style

        self._updateNodeSelectorLineageSwatches(
            self.ui.visibleTemplateSupportModelSelector,
            self.logic.isVisibleTemplateSupportModelNode,
        )

    def onTemplateSupportToothItemChanged(self, item) -> None:
        del item
        if (
            self._updatingTemplateUI
            or not self._parameterNode
            or not self.logic
        ):
            return
        self._restoreTemplateSupportBoundaryFocus()
        selectedSupportIds = self._selectedTemplateSupportSegmentIds()
        serializedIds = self.logic.encodeTemplateSupportSegmentIds(
            selectedSupportIds
        )
        if (
            serializedIds
            != self._parameterNode.templateSupportToothSegmentIdsJson
        ):
            self._markCurrentDraftTemplateModelStale(
                _("Support-tooth selection changed.")
            )
            self._updatingTemplateUI = True
            try:
                self._parameterNode.templateSupportToothSegmentIdsJson = (
                    serializedIds
                )
            finally:
                self._updatingTemplateUI = False
        self._updateTemplateModeling()

    def onDraftTemplateSupportModelSelectionChanged(self, modelNode) -> None:
        if self._updatingTemplateUI or not self._parameterNode:
            return
        currentNode = self._parameterNode.draftTemplateSupportModel
        currentNodeId = currentNode.GetID() if currentNode else None
        selectedNodeId = modelNode.GetID() if modelNode else None
        if currentNodeId != selectedNodeId:
            self._parameterNode.draftTemplateSupportModel = modelNode
            reason = _("The authoritative Step 4B support package changed.")
            self.logic.markTargetDockingAssemblyStale(
                self._parameterNode.targetDockingAssemblyModel,
                reason,
            )
            self._invalidateTemplateSupportSurfaceDownstream(reason)
        self._updateTemplateModeling()

    def onReviseTemplateSupportPackage(self, checked: bool = False) -> None:
        """Explicitly unlock Step 4B and stale every dependent child."""

        del checked
        if not self._parameterNode or not self.logic:
            return
        modelNode = self._parameterNode.draftTemplateSupportModel
        if not self.logic.isDraftTemplateSupportModelNode(modelNode):
            slicer.util.errorDisplay(
                _("Create the Step 4B draft support package first.")
            )
            return
        if not self.logic.isTemplateSupportSelectionLocked(modelNode):
            self._updateTemplateModeling()
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Unlock the Step 4B support package for revision? The draft "
                "and all dependent Step 4C/5A/5B/5C geometry will be marked "
                "stale immediately. Select support teeth here, then Update "
                "Draft Support Model to lock the package again."
            ),
            windowTitle=_("Revise Step 4B support package"),
        ):
            return
        modelNode.SetAttribute("DENTOBOT.SupportSelectionLocked", "false")
        self._markCurrentDraftTemplateModelStale(
            _("The Step 4B support package was unlocked for revision.")
        )
        self._updateTemplateModeling()

    def onCreateDraftTemplateSupportModel(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        self._restoreTemplateSupportBoundaryFocus()
        try:
            supportSegmentIds = self._selectedTemplateSupportSegmentIds()
            modelNode, details = (
                self.logic.createOrUpdateDraftTemplateSupportModel(
                    self._parameterNode.teethSegmentation,
                    self._parameterNode.targetToothSegmentId,
                    supportSegmentIds,
                    self._parameterNode.draftTemplateSupportModel,
                )
            )
            self._parameterNode.templateSupportToothSegmentIdsJson = (
                self.logic.encodeTemplateSupportSegmentIds(
                    supportSegmentIds
                )
            )
            self._parameterNode.draftTemplateSupportModel = modelNode
            self._invalidateTemplateSupportSurfaceDownstream(
                _("The full support-anatomy model was regenerated."),
            )
            self._templateStatusWarning = ""
            logging.info(
                "DENTOBOT Step 4B draft model %s created/updated with "
                "%d support teeth, %d points, and %d cells",
                modelNode.GetID(),
                details["supportCount"],
                details["pointCount"],
                details["cellCount"],
            )
            self._updateTemplateModeling()
        except (RuntimeError, ValueError) as exc:
            self._templateStatusWarning = str(exc)
            self.ui.templateModelingStatusLabel.text = str(exc)
            self.ui.templateModelingStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def onDeleteDraftTemplateSupportModel(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        modelNode = self._parameterNode.draftTemplateSupportModel
        try:
            self.logic.validateDraftTemplateSupportModelForDeletion(modelNode)
        except ValueError as exc:
            slicer.util.errorDisplay(str(exc))
            return
        modelName = modelNode.GetName() or _("Unnamed draft support model")
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Permanently delete the draft support-anatomy model “%1”? "
                "The source segmentation, target tooth, and checked support "
                "teeth will be kept so a new draft can be created. Its visible "
                "support boundary and preview will also be removed. This "
                "cannot be undone after the scene is saved."
            ).replace("%1", modelName),
            windowTitle=_("Delete Step 4B draft support model"),
        ):
            return

        self._restoreTemplateSupportBoundaryFocus()
        try:
            if (
                self._parameterNode.templateSupportBoundaryCurve
                or self._parameterNode.templateSupportBoundaryPlane
                or self._parameterNode.visibleTemplateSupportModel
            ):
                if self.logic.isPatientContactShellModelNode(
                    self._parameterNode.patientContactShellModel
                ):
                    self._deleteFinalPrintableTemplateCascade()
                    self.logic.deletePatientContactShell(
                        self._parameterNode.patientContactShellModel
                    )
                self.logic.deleteTemplateUndercutWorkflow(
                    self._parameterNode.templateInsertionDirection,
                    self._parameterNode.templateUndercutSurfaceModel,
                    self._parameterNode.templateUndercutBlockoutModel,
                )
                self._bindTemplateInsertionDirectionNode(None)
                self.logic.deleteTemplateSupportSelection(
                    self._parameterNode.templateSupportBoundaryCurve,
                    self._parameterNode.visibleTemplateSupportModel,
                    self._parameterNode.templateSupportBoundaryPlane,
                )
                self._bindTemplateSupportBoundaryNode(None)
            removal = self.logic.deleteDraftTemplateSupportModel(modelNode)
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))
            return
        self._parameterNode.draftTemplateSupportModel = None
        self._templateStatusWarning = ""
        logging.info(
            "Deleted DENTOBOT Step 4B draft model %s and %d owned auxiliary nodes",
            removal["nodeId"],
            len(removal["auxiliaryNodeIds"]),
        )
        self._updateTemplateModeling()

    def onTemplateSupportBoundarySelectionChanged(self, curveNode) -> None:
        if self._updatingTemplateUI or not self._parameterNode:
            return
        currentNode = self._parameterNode.templateSupportBoundaryCurve
        if (currentNode.GetID() if currentNode else None) != (
            curveNode.GetID() if curveNode else None
        ):
            self._restoreTemplateSupportBoundaryFocus()
            self._parameterNode.templateSupportBoundaryCurve = curveNode
            self._bindTemplateSupportBoundaryNode(curveNode)
            self._invalidateTemplateSupportSurfaceDownstream(
                _("The selected visible support boundary changed."),
            )
        self._updateTemplateModeling()

    def onVisibleTemplateSupportModelSelectionChanged(self, modelNode) -> None:
        if self._updatingTemplateUI or not self._parameterNode:
            return
        currentNode = self._parameterNode.visibleTemplateSupportModel
        if (currentNode.GetID() if currentNode else None) != (
            modelNode.GetID() if modelNode else None
        ):
            self._restoreTemplateSupportBoundaryFocus()
            self._parameterNode.visibleTemplateSupportModel = modelNode
        self._updateTemplateModeling()

    def onTemplateSupportSurfaceParameterChanged(self, *args) -> None:
        del args
        if self._updatingTemplateUI or not self._parameterNode:
            return
        spacing = float(self.ui.templateSupportCurveSamplingSpacingSpinBox.value)
        terminalCoveragePercent = float(
            self.ui.templateTerminalSupportCoverageSpinBox.value
        )
        changed = bool(
            not math.isclose(
                self._parameterNode.templateSupportCurveSamplingSpacingMm,
                spacing,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            or not math.isclose(
                self._parameterNode.templateTerminalSupportCoveragePercent,
                terminalCoveragePercent,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        )
        self._parameterNode.templateSupportCurveSamplingSpacingMm = spacing
        self._parameterNode.templateTerminalSupportCoveragePercent = (
            terminalCoveragePercent
        )
        if changed:
            self._invalidateTemplateSupportSurfaceDownstream(
                _("Visible support-surface processing parameters changed."),
            )
        self._updateTemplateModeling()

    def onTemplateSupportDirectionReversedToggled(self, checked: bool) -> None:
        if self._updatingTemplateUI or not self._parameterNode:
            return
        reversedValue = bool(checked)
        if (
            self._parameterNode.templateSupportDirectionReversed
            != reversedValue
        ):
            self._parameterNode.templateSupportDirectionReversed = reversedValue
            self._invalidateTemplateSupportSurfaceDownstream(
                _("The target-trajectory crown/root polarity changed."),
            )
            if self._parameterNode.templateSupportBoundaryPlane and self.logic:
                try:
                    self.logic.createOrUpdateTemplateSupportBoundaryPlane(
                        self._parameterNode.draftTemplateSupportModel,
                        self._parameterNode.trajectoryLine,
                        reverseDirection=reversedValue,
                        depthFromEntryMm=(
                            self._parameterNode.templateSupportPlaneDepthMm
                        ),
                        crownCapPercent=(
                            self._parameterNode.templateSupportCrownCapPercent
                        ),
                        planeNode=(
                            self._parameterNode.templateSupportBoundaryPlane
                        ),
                    )
                except (RuntimeError, ValueError) as exc:
                    self.ui.templateSupportSurfaceStatusLabel.text = str(exc)
                    self.ui.templateSupportSurfaceStatusLabel.styleSheet = (
                        "color: #b00020;"
                    )
        self._updateTemplateModeling()

    def onCreateTemplateSupportBoundary(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        curveNode = self._parameterNode.templateSupportBoundaryCurve
        if curveNode and curveNode.GetNumberOfDefinedControlPoints() >= 3:
            if not slicer.util.confirmYesNoDisplay(
                _(
                    "Redraw the visible support boundary? Existing boundary "
                    "points will be cleared and downstream template geometry "
                    "will become stale."
                ),
                windowTitle=_("Redraw visible support boundary"),
            ):
                return
        try:
            curveNode = self.logic.createOrResetTemplateSupportBoundary(
                self._parameterNode.draftTemplateSupportModel,
                curveNode,
            )
            self._parameterNode.templateSupportBoundaryCurve = curveNode
            self._bindTemplateSupportBoundaryNode(curveNode)
            self._invalidateTemplateSupportSurfaceDownstream(
                _("The visible support boundary was redrawn."),
            )
            self._startTemplateSupportBoundaryFocus()
            self.logic.startClosedCurvePlacement(curveNode)
            self._updateTemplateModeling()
        except (RuntimeError, ValueError) as exc:
            self._restoreTemplateSupportBoundaryFocus()
            slicer.util.errorDisplay(str(exc))

    def onCreateTemplateSupportPlane(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            planeNode, _geometry = (
                self.logic.createOrUpdateTemplateSupportBoundaryPlane(
                    self._parameterNode.draftTemplateSupportModel,
                    self._parameterNode.trajectoryLine,
                    reverseDirection=(
                        self._parameterNode.templateSupportDirectionReversed
                    ),
                    depthFromEntryMm=(
                        self._parameterNode.templateSupportPlaneDepthMm
                    ),
                    crownCapPercent=(
                        self._parameterNode.templateSupportCrownCapPercent
                    ),
                    planeNode=self._parameterNode.templateSupportBoundaryPlane,
                )
            )
            self._parameterNode.templateSupportBoundaryPlane = planeNode
            self._invalidateTemplateSupportSurfaceDownstream(
                _("The insertion-aligned support plane was created or reset."),
            )
            self._updateTemplateModeling()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onTemplateSupportPlaneDepthChanged(self, value: float) -> None:
        del value
        if self._updatingTemplateUI or not self._parameterNode or not self.logic:
            return
        depth = float(self.ui.templateSupportPlaneDepthSpinBox.value)
        capPercent = float(self.ui.templateSupportCrownCapSpinBox.value)
        self._parameterNode.templateSupportPlaneDepthMm = depth
        self._parameterNode.templateSupportCrownCapPercent = capPercent
        planeNode = self._parameterNode.templateSupportBoundaryPlane
        if not planeNode:
            self._updateTemplateModeling()
            return
        try:
            storedDepth = float(
                planeNode.GetAttribute("DENTOBOT.DepthFromEntryMm") or "nan"
            )
            storedCapPercent = float(
                planeNode.GetAttribute("DENTOBOT.CrownCapPercent") or "nan"
            )
        except ValueError:
            storedDepth = math.nan
            storedCapPercent = math.nan
        if math.isclose(
            storedDepth,
            depth,
            rel_tol=0.0,
            abs_tol=1e-8,
        ) and math.isclose(
            storedCapPercent,
            capPercent,
            rel_tol=0.0,
            abs_tol=1e-8,
        ):
            # Parameter-wrapper restoration can emit valueChanged even though
            # the persisted support plane already has exactly these settings.
            self._updateTemplateModeling()
            return
        try:
            self.logic.createOrUpdateTemplateSupportBoundaryPlane(
                self._parameterNode.draftTemplateSupportModel,
                self._parameterNode.trajectoryLine,
                reverseDirection=(
                    self._parameterNode.templateSupportDirectionReversed
                ),
                depthFromEntryMm=depth,
                crownCapPercent=capPercent,
                planeNode=planeNode,
            )
            self._invalidateTemplateSupportSurfaceDownstream(
                _(
                    "The support-plane depth or crown-cap tilt fit changed; "
                    "regenerate the boundary and preview."
                ),
            )
            self._updateTemplateModeling()
        except (RuntimeError, ValueError) as exc:
            self.ui.templateSupportSurfaceStatusLabel.text = str(exc)
            self.ui.templateSupportSurfaceStatusLabel.styleSheet = "color: #b00020;"

    def onGenerateTemplateSupportBoundaryFromPlane(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        self._restoreTemplateSupportBoundaryFocus()
        self._restoringTemplateSupportBoundary = True
        try:
            curveNode, metrics = (
                self.logic.createOrUpdateTemplateSupportBoundaryFromPlane(
                    self._parameterNode.draftTemplateSupportModel,
                    self._parameterNode.templateSupportBoundaryPlane,
                    self._parameterNode.trajectoryLine,
                    samplingSpacingMm=(
                        self._parameterNode.templateSupportCurveSamplingSpacingMm
                    ),
                    curveNode=self._parameterNode.templateSupportBoundaryCurve,
                )
            )
            self._parameterNode.templateSupportBoundaryCurve = curveNode
            self._bindTemplateSupportBoundaryNode(curveNode)
            self._invalidateTemplateSupportSurfaceDownstream(
                _("The support boundary was regenerated from the support plane."),
            )
            logging.info(
                "Initialized Step 5A support boundary from plane with %d points; "
                "%d of %d selected teeth intersected",
                metrics["outputLoopPointCount"],
                metrics["intersectedToothCount"],
                metrics["sourceToothCount"],
            )
        except (RuntimeError, ValueError) as exc:
            self.ui.templateSupportSurfaceStatusLabel.text = str(exc)
            self.ui.templateSupportSurfaceStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))
            return
        finally:
            self._restoringTemplateSupportBoundary = False
        self._updateTemplateModeling()
        self.onGenerateVisibleTemplateSupportModel()

    def onGenerateVisibleTemplateSupportModel(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        self._restoreTemplateSupportBoundaryFocus()
        try:
            modelNode, metrics = self.logic.createOrUpdateVisibleTemplateSupportModel(
                self._parameterNode.draftTemplateSupportModel,
                self._parameterNode.templateSupportBoundaryCurve,
                directionTrajectory=self._parameterNode.trajectoryLine,
                reverseDirection=(
                    self._parameterNode.templateSupportDirectionReversed
                ),
                samplingSpacingMm=(
                    self._parameterNode.templateSupportCurveSamplingSpacingMm
                ),
                terminalCoveragePercent=(
                    self._parameterNode.templateTerminalSupportCoveragePercent
                ),
                outputModel=self._parameterNode.visibleTemplateSupportModel,
                insertionDirectionNode=(
                    self._parameterNode.templateInsertionDirection
                ),
            )
            self._parameterNode.visibleTemplateSupportModel = modelNode
            insertionDirection = modelNode.GetNodeReference(
                self.logic.TEMPLATE_VISIBLE_SUPPORT_INSERTION_DIRECTION_REFERENCE_ROLE
            )
            self._parameterNode.templateInsertionDirection = insertionDirection
            self._bindTemplateInsertionDirectionNode(insertionDirection)
            self.logic.markTemplateUndercutOutputsStale(
                self._parameterNode.templateUndercutSurfaceModel,
                self._parameterNode.templateUndercutBlockoutModel,
                _("The visible support surface was regenerated."),
            )
            self.logic.markPatientContactShellStale(
                self._parameterNode.patientContactShellModel,
                _("The visible support surface was regenerated."),
            )
            self.logic.markResearchTemplateModelsStale(
                self._parameterNode.researchTemplateShellModel,
                self._parameterNode.researchTemplateSleeveModel,
                _("The visible support surface was regenerated."),
            )
            self.logic.markFinalizedTemplateShellStale(
                self._parameterNode.finalizedTemplateShellModel,
                _("The visible support surface was regenerated."),
            )
            logging.info(
                "Generated visible support surface %s with %d points and %d triangles",
                modelNode.GetID(),
                metrics["pointCount"],
                metrics["triangleCount"],
            )
            self._updateTemplateModeling()
            self._updateTemplateGuide()
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            self.ui.templateSupportSurfaceStatusLabel.text = str(exc)
            self.ui.templateSupportSurfaceStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def onDeleteTemplateSupportSelection(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Delete the visible support boundary and its derived preview? "
                "The authoritative segmentation, target/support tooth selection, "
                "and full support-anatomy model will be preserved."
            ),
            windowTitle=_("Delete visible support selection"),
        ):
            return
        self._restoreTemplateSupportBoundaryFocus()
        try:
            self._invalidateTemplateSupportSurfaceDownstream(
                _("The visible support selection was deleted."),
            )
            if self.logic.isPatientContactShellModelNode(
                self._parameterNode.patientContactShellModel
            ):
                self._deleteFinalPrintableTemplateCascade()
                self.logic.deletePatientContactShell(
                    self._parameterNode.patientContactShellModel
                )
            self.logic.deleteTemplateUndercutWorkflow(
                self._parameterNode.templateInsertionDirection,
                self._parameterNode.templateUndercutSurfaceModel,
                self._parameterNode.templateUndercutBlockoutModel,
            )
            self._bindTemplateInsertionDirectionNode(None)
            self.logic.deleteTemplateSupportSelection(
                self._parameterNode.templateSupportBoundaryCurve,
                self._parameterNode.visibleTemplateSupportModel,
                self._parameterNode.templateSupportBoundaryPlane,
            )
            self._bindTemplateSupportBoundaryNode(None)
            self._updateTemplateModeling()
            self._updateTemplateGuide()
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))
