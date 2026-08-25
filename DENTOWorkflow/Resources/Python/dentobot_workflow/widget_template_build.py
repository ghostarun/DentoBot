"""Extracted unified template build methods; public APIs remain on GuideBuildWidgetMixin."""

from __future__ import annotations

from .runtime import *


class TemplateBuildWidgetMixin:
    def _clearTemplateGuide(self) -> None:
        if not hasattr(self, "ui"):
            return
        self._updatingTemplateGuideUI = True
        try:
            self.ui.templateInsertionDirectionSelector.setCurrentNode(None)
            self.ui.templateUndercutSurfaceModelSelector.setCurrentNode(None)
            self.ui.templateUndercutBlockoutModelSelector.setCurrentNode(None)
            self.ui.patientContactShellModelSelector.setCurrentNode(None)
            self.ui.finalPrintableTemplateModelSelector.setCurrentNode(None)
            self.ui.templateGuideTrajectoriesListWidget.clear()
            self.ui.patientContactShellSourceValueLabel.text = _("--")
            self.ui.createTemplateInsertionDirectionButton.enabled = False
            self.ui.deleteTemplateInsertionDirectionButton.enabled = False
            self.ui.analyzeTemplateUndercutsButton.enabled = False
            self.ui.generateFinalPrintableTemplateButton.enabled = False
            self.ui.deleteFinalPrintableTemplateButton.enabled = False
            self.ui.inspectTemplateFitButton.enabled = False
            self.ui.inspectShellAndGuidesButton.enabled = False
            self.ui.inspectUnifiedTemplateButton.enabled = False
            self.ui.templateDockingFusionStatusLabel.text = _(
                "Generate an undercut-aware patient-contact shell first."
            )
            self.ui.templateDockingFusionStatusLabel.styleSheet = "color: #b36b00;"
            self.ui.generatePatientContactShellButton.enabled = False
            self.ui.deletePatientContactShellButton.enabled = False
            self.ui.patientContactShellStatusLabel.text = _(
                "Generate a current visible support preview in Step 5A first."
            )
            self.ui.patientContactShellStatusLabel.styleSheet = "color: #b36b00;"
            self.ui.templateShellRoiSelector.setCurrentNode(None)
            self.ui.researchTemplateShellModelSelector.setCurrentNode(None)
            self.ui.researchTemplateSleeveModelSelector.setCurrentNode(None)
            self._updateLineageBadge(
                self.ui.templateGuideLineageLabel,
                None,
                _("Step 4A → Step 4B → Step 5A → Step 5B"),
                _(
                    "Inherited lineage: waiting for a colored Step 5A/Step 4A input."
                ),
            )
            self.ui.createTemplateShellRoiButton.enabled = False
            self.ui.deleteTemplateShellRoiButton.enabled = False
            for visibilityCheckBox in (
                self.ui.targetBoundsVisibilityCheckBox,
                self.ui.trajectoryVisibilityCheckBox,
                self.ui.supportModelVisibilityCheckBox,
                self.ui.shellRoiVisibilityCheckBox,
                self.ui.shellModelVisibilityCheckBox,
                self.ui.sleeveModelVisibilityCheckBox,
                self.ui.patientContactShellVisibilityCheckBox,
                self.ui.templateInsertionDirectionVisibilityCheckBox,
                self.ui.templateUndercutVisibilityCheckBox,
                self.ui.templateBlockoutVisibilityCheckBox,
                self.ui.supportBoundaryVisibilityCheckBox,
                self.ui.supportPlaneVisibilityCheckBox,
                self.ui.visibleSupportVisibilityCheckBox,
                self.ui.finalTemplateVisibilityCheckBox,
            ):
                visibilityCheckBox.enabled = False
                visibilityCheckBox.checked = False
            self.ui.generateResearchTemplateButton.enabled = False
            self.ui.deleteResearchTemplateButton.enabled = False
            self.ui.exportResearchTemplateButton.enabled = False
            self.ui.templateGuideStatusLabel.text = _(
                "Create a current Step 4B support draft and Step 5A visible support preview, then lock the trajectory."
            )
            self.ui.templateGuideStatusLabel.styleSheet = "color: #b36b00;"
        finally:
            self._updatingTemplateGuideUI = False

    def _templateGuideParameters(self) -> dict[str, float]:
        if not self._parameterNode:
            return {}
        return {
            "clearanceMm": self._parameterNode.templateShellClearanceMm,
            "thicknessMm": self._parameterNode.templateShellThicknessMm,
            "samplingSpacingMm": self._parameterNode.templateSamplingSpacingMm,
            "channelDiameterMm": self._parameterNode.templateChannelDiameterMm,
            "sleeveOuterDiameterMm": self._parameterNode.templateSleeveOuterDiameterMm,
            "sleeveInnerDiameterMm": self._parameterNode.templateSleeveInnerDiameterMm,
            "sleeveHeightMm": self._parameterNode.templateSleeveHeightMm,
        }

    def _templateGuideVisibilityEntries(self) -> tuple[tuple[object, object], ...]:
        if not self._parameterNode:
            return ()
        return (
            (
                self.ui.targetBoundsVisibilityCheckBox,
                self._parameterNode.targetToothBoundsRoi,
            ),
            (
                self.ui.trajectoryVisibilityCheckBox,
                self._parameterNode.trajectoryLine,
            ),
            (
                self.ui.supportModelVisibilityCheckBox,
                self._parameterNode.draftTemplateSupportModel,
            ),
            (
                self.ui.shellRoiVisibilityCheckBox,
                self._parameterNode.templateShellRoi,
            ),
            (
                self.ui.shellModelVisibilityCheckBox,
                self._parameterNode.researchTemplateShellModel,
            ),
            (
                self.ui.sleeveModelVisibilityCheckBox,
                self._parameterNode.researchTemplateSleeveModel,
            ),
            (
                self.ui.patientContactShellVisibilityCheckBox,
                self._parameterNode.patientContactShellModel,
            ),
            (
                self.ui.templateInsertionDirectionVisibilityCheckBox,
                self._parameterNode.templateInsertionDirection,
            ),
            (
                self.ui.templateUndercutVisibilityCheckBox,
                self._parameterNode.templateUndercutSurfaceModel,
            ),
            (
                self.ui.templateBlockoutVisibilityCheckBox,
                self._parameterNode.templateUndercutBlockoutModel,
            ),
            (
                self.ui.supportBoundaryVisibilityCheckBox,
                self._parameterNode.templateSupportBoundaryCurve,
            ),
            (
                self.ui.supportPlaneVisibilityCheckBox,
                self._parameterNode.templateSupportBoundaryPlane,
            ),
            (
                self.ui.visibleSupportVisibilityCheckBox,
                self._parameterNode.visibleTemplateSupportModel,
            ),
            (
                self.ui.finalTemplateVisibilityCheckBox,
                self._parameterNode.finalPrintableTemplateModel,
            ),
        )

    def _updateTemplateGuideVisibilityControls(self) -> None:
        self._updatingTemplateGuideVisibilityUI = True
        try:
            for checkBox, node in self._templateGuideVisibilityEntries():
                displayNode = node.GetDisplayNode() if node else None
                checkBox.enabled = bool(displayNode)
                checkBox.checked = bool(
                    displayNode and displayNode.GetVisibility()
                )
                color = (
                    self.logic.lineageColorFromNode(node)
                    if self.logic and node
                    else None
                )
                checkBox.styleSheet = (
                    self._lineageStyleSheet(
                        color,
                        borderWidth=6,
                    ).replace("QLabel", "QCheckBox")
                    if color
                    else ""
                )
        finally:
            self._updatingTemplateGuideVisibilityUI = False

    def onTemplateGuideVisibilityChanged(self, *args) -> None:
        del args
        if (
            self._updatingTemplateGuideVisibilityUI
            or self._updatingTemplateGuideUI
        ):
            return
        for checkBox, node in self._templateGuideVisibilityEntries():
            displayNode = node.GetDisplayNode() if node else None
            if displayNode and checkBox.enabled:
                displayNode.SetVisibility(bool(checkBox.checked))
        self._updateTemplateGuideVisibilityControls()

    def _updateTemplateGuideTrajectoryList(self, sourceModel) -> None:
        try:
            included = self.logic.getTargetDockingAssemblySummary(
                self._parameterNode.targetDockingAssemblyModel
            )["trajectories"]
        except (RuntimeError, ValueError):
            try:
                included = self.logic.getEligibleTemplateGuideTrajectories(
                    sourceModel
                )
            except (RuntimeError, ValueError):
                included = []
        self._updatingGuideTrajectorySelectionUI = True
        try:
            self.ui.templateGuideTrajectoriesListWidget.clear()
            for trajectoryNode in included:
                association = self.logic.getTrajectoryTargetAssociation(trajectoryNode)
                targetRecord = association["targetRecord"] if association else {}
                fdiNumber = targetRecord.get("fdiNumber") or "--"
                try:
                    summary = self.logic.getTrajectorySummary(trajectoryNode)
                    ready = bool(
                        summary["isValid"]
                        and summary["definedPointCount"] == 2
                        and trajectoryNode.GetLocked()
                    )
                except ValueError:
                    ready = False
                state = (
                    _("included automatically — approved/locked")
                    if ready
                    else _("included automatically — incomplete or unlocked")
                )
                item = qt.QListWidgetItem(
                    _("FDI %1 — %2 (%3)")
                    .replace("%1", str(fdiNumber))
                    .replace("%2", trajectoryNode.GetName() or _("Unnamed trajectory"))
                    .replace("%3", state)
                )
                item.setData(qt.Qt.UserRole, trajectoryNode.GetID())
                item.setFlags(item.flags() | qt.Qt.ItemIsSelectable)
                if not ready:
                    item.setToolTip(
                        _("Complete and lock this trajectory in Step 4A before building.")
                    )
                self.ui.templateGuideTrajectoriesListWidget.addItem(item)
        finally:
            self._updatingGuideTrajectorySelectionUI = False

    def _selectedTemplateGuideTrajectoryItems(self) -> list[vtkMRMLMarkupsLineNode]:
        selected = []
        listWidget = self.ui.templateGuideTrajectoriesListWidget
        for itemIndex in range(listWidget.count):
            item = listWidget.item(itemIndex)
            if item.checkState() != qt.Qt.Checked:
                continue
            node = slicer.mrmlScene.GetNodeByID(str(item.data(qt.Qt.UserRole)))
            if node:
                selected.append(node)
        return selected

    def _updateFinalPrintableTemplateControls(self, patientShell, sourceModel) -> None:
        targetDockingAssembly = self._parameterNode.targetDockingAssemblyModel
        selectedTrajectories = []
        try:
            targetDockingSummary = self.logic.getTargetDockingAssemblySummary(
                targetDockingAssembly
            )
            selectedTrajectories = targetDockingSummary["trajectories"]
        except (RuntimeError, ValueError, json.JSONDecodeError):
            targetDockingSummary = None
        if sourceModel:
            self._updateTemplateGuideTrajectoryList(sourceModel)
        self._bindSelectedGuideTrajectoryNodes(selectedTrajectories)
        finalModel = self._parameterNode.finalPrintableTemplateModel
        if self.ui.finalPrintableTemplateModelSelector.currentNode() is not finalModel:
            self._updatingTemplateGuideUI = True
            try:
                self.ui.finalPrintableTemplateModelSelector.setCurrentNode(finalModel)
            finally:
                self._updatingTemplateGuideUI = False
        self._updateNodeSelectorLineageSwatches(
            self.ui.finalPrintableTemplateModelSelector,
            self.logic.isFinalPrintableTemplateModelNode,
        )
        inputError = ""
        normalizedParameters = None
        validatedInputs = None
        try:
            normalizedParameters = normalize_docking_parameters(
                outer_diameter_mm=self._parameterNode.templateSleeveOuterDiameterMm,
                inner_diameter_mm=self._parameterNode.templateSleeveInnerDiameterMm,
                height_mm=self._parameterNode.templateSleeveHeightMm,
                clearance_mm=self._parameterNode.templateDockingClearanceMm,
                reinforcement_radial_mm=(
                    self._parameterNode.templateReinforcementRadialMm
                ),
                reinforcement_depth_mm=(
                    self._parameterNode.templateReinforcementDepthMm
                ),
                processing_resolution_mm=self._parameterNode.templateSamplingSpacingMm,
            )
            validatedInputs = self.logic._validateFinalGuideInputs(
                patientShell,
                targetDockingAssembly,
                selectedTrajectories,
                normalizedParameters,
            )
        except (RuntimeError, ValueError) as exc:
            inputError = str(exc)

        finalSummary = None
        outputError = ""
        if finalModel:
            try:
                finalSummary = self.logic.getFinalPrintableTemplateSummary(finalModel)
            except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                outputError = str(exc)
        if finalSummary and finalSummary["geometryState"] == "Current":
            currentTrajectoryGeometry = [
                {
                    "entryRas": record["entryRas"],
                    "targetRas": record["targetRas"],
                }
                for record in validatedInputs["trajectories"]
            ] if validatedInputs else []
            staleReason = ""
            if inputError:
                staleReason = inputError
            elif finalSummary["patientShell"] is not patientShell:
                staleReason = _("The patient-contact shell changed.")
            elif finalSummary["targetDockingAssembly"] is not targetDockingAssembly:
                staleReason = _("The Step 4C docking assembly changed.")
            elif finalSummary["trajectories"] != selectedTrajectories:
                staleReason = _("The selected guide trajectories changed.")
            elif finalSummary["parametersJson"] != json.dumps(
                normalizedParameters,
                sort_keys=True,
                separators=(",", ":"),
            ):
                staleReason = _("Docking clearance, reinforcement, dimensions, or resolution changed.")
            elif finalSummary["trajectoryGeometryJson"] != json.dumps(
                currentTrajectoryGeometry,
                sort_keys=True,
                separators=(",", ":"),
            ):
                staleReason = _("A source trajectory geometry changed.")
            elif finalSummary["patientShellUpdatedUtc"] != (
                patientShell.GetAttribute("DENTOBOT.UpdatedUtc") or ""
            ):
                staleReason = _("The patient-contact shell was regenerated.")
            elif finalSummary["targetDockingUpdatedUtc"] != (
                targetDockingAssembly.GetAttribute("DENTOBOT.UpdatedUtc") or ""
            ):
                staleReason = _("The Step 4C docking assembly was regenerated.")
            if staleReason:
                self.logic.markFinalPrintableTemplateStale(finalModel, staleReason)
                finalSummary = self.logic.getFinalPrintableTemplateSummary(finalModel)

        buildPreflightError = ""
        try:
            self._completeTemplateBuildPreflight()
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            buildPreflightError = str(exc)

        patientShellCurrent = False
        if patientShell:
            try:
                patientShellCurrent = (
                    self.logic.getPatientContactShellSummary(patientShell)[
                        "geometryState"
                    ]
                    == "Current"
                )
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass
        finalCurrent = bool(
            finalSummary and finalSummary["geometryState"] == "Current"
        )
        self.ui.generateFinalPrintableTemplateButton.enabled = bool(
            not finalCurrent and not buildPreflightError and not outputError
        )
        if finalCurrent:
            self.ui.generateFinalPrintableTemplateButton.text = _(
                "Unified Template Is Current"
            )
        else:
            self.ui.generateFinalPrintableTemplateButton.text = _(
                "Build / Update Unified Template"
            )
        self.ui.deleteFinalPrintableTemplateButton.enabled = bool(
            self.logic.isFinalPrintableTemplateModelNode(finalModel)
        )
        self.ui.inspectTemplateFitButton.enabled = bool(
            self.logic.isVisibleTemplateSupportModelNode(
                self._parameterNode.visibleTemplateSupportModel
            )
            or self.logic.isTemplateUndercutSurfaceModelNode(
                self._parameterNode.templateUndercutSurfaceModel
            )
            or self.logic.isTemplateUndercutBlockoutModelNode(
                self._parameterNode.templateUndercutBlockoutModel
            )
            or self.logic.isPatientContactShellModelNode(patientShell)
        )
        self.ui.inspectShellAndGuidesButton.enabled = bool(
            self.logic.isPatientContactShellModelNode(patientShell)
        )
        self.ui.inspectUnifiedTemplateButton.enabled = finalCurrent
        if outputError:
            message, style = outputError, "color: #b00020;"
        elif buildPreflightError:
            message, style = buildPreflightError, "color: #b36b00;"
        elif finalCurrent:
            message = (
                _(
                    "Unified template is current (%1 trajectory/trajectories, %2 triangles, "
                    "%3 connected occupied volume(s), four target-frame docks); final verification is required."
                )
                .replace("%1", str(len(finalSummary["trajectories"])))
                .replace("%2", str(finalSummary["metrics"].get("triangleCount", "--")))
                .replace(
                    "%3",
                    str(
                        finalSummary["metrics"].get(
                            "occupiedVolumeRegionCount",
                            "--",
                        )
                    ),
                )
            )
            style = "color: #b36b00;"
        elif patientShellCurrent:
            message = _(
                "Patient shell is cached and current. Build will reuse it and compute "
                "only the trajectory-guide/four-dock fusion that is missing or stale."
            )
            style = "color: #1f5f99;"
        elif finalSummary:
            message = _("Unified template is stale: %1").replace(
                "%1",
                finalSummary["staleReason"] or _("regeneration required"),
            )
            style = "color: #b36b00;"
        else:
            message = _(
                "Inputs are ready. Build will generate only missing or stale blockout, "
                "patient-shell, and unified guide/dock stages."
            )
            style = "color: #1f5f99;"
        self.ui.templateDockingFusionStatusLabel.text = message
        self.ui.templateDockingFusionStatusLabel.styleSheet = style

    def _updateTemplateGuide(self) -> None:
        if self._updatingTemplateGuideUI:
            return
        if not self._parameterNode or not self.logic:
            self._clearTemplateGuide()
            return

        supportModel = self._parameterNode.draftTemplateSupportModel
        visibleSupportModel = self._parameterNode.visibleTemplateSupportModel
        insertionDirection = self._parameterNode.templateInsertionDirection
        if visibleSupportModel:
            try:
                referencedInsertion = (
                    self.logic.getVisibleTemplateSupportModelSummary(
                        visibleSupportModel
                    )["insertionDirection"]
                )
            except (RuntimeError, ValueError, json.JSONDecodeError):
                referencedInsertion = None
            if (
                self.logic.isTemplateInsertionDirectionNode(referencedInsertion)
                and insertionDirection is not referencedInsertion
            ):
                self._updatingTemplateGuideUI = True
                try:
                    self._parameterNode.templateInsertionDirection = referencedInsertion
                    insertionDirection = referencedInsertion
                    self._bindTemplateInsertionDirectionNode(referencedInsertion)
                finally:
                    self._updatingTemplateGuideUI = False
        undercutModel = self._parameterNode.templateUndercutSurfaceModel
        blockoutModel = self._parameterNode.templateUndercutBlockoutModel
        patientContactShell = self._parameterNode.patientContactShellModel
        trajectoryNode = self._parameterNode.trajectoryLine
        roiNode = self._parameterNode.templateShellRoi
        shellModel = self._parameterNode.researchTemplateShellModel
        sleeveModel = self._parameterNode.researchTemplateSleeveModel
        rejectedRoiWarning = ""
        if roiNode and not self.logic.isTemplateShellRoiNode(roiNode):
            rejectedRoiWarning = _(
                "Ignored a non-Step 5B ROI. Create the automatic shell bounds "
                "ROI with the Step 5B button; target-bounds and unrelated ROIs "
                "cannot be used for shell generation."
            )
            logging.warning(
                "Cleared invalid Step 5B ROI reference to %s (%s)",
                roiNode.GetID(),
                roiNode.GetName() or "unnamed ROI",
            )
            self._updatingTemplateGuideUI = True
            try:
                self._parameterNode.templateShellRoi = None
                self.ui.templateShellRoiSelector.setCurrentNode(None)
            finally:
                self._updatingTemplateGuideUI = False
            roiNode = None
        elif roiNode:
            self.logic.enforceWorkflowRoiNonInteractive(roiNode)
        self.logic.refreshWorkflowLineageColors()
        self.logic.refreshWorkflowNodeStepTags()
        lineageNode = self._lineageSourceNode(
            (
                supportModel,
                visibleSupportModel,
                insertionDirection,
                undercutModel,
                blockoutModel,
                patientContactShell,
                trajectoryNode,
                roiNode,
                shellModel,
                sleeveModel,
            ),
            self._parameterNode.targetToothSegmentId,
        )
        self._updateLineageBadge(
            self.ui.templateGuideLineageLabel,
            lineageNode,
            _("Step 4A → Step 4B → Step 5A → Step 5B"),
            _(
                "Inherited lineage: waiting for a colored Step 5A/Step 4A input."
            ),
        )
        for selector, acceptsNode in (
            (
                self.ui.templateInsertionDirectionSelector,
                self.logic.isTemplateInsertionDirectionNode,
            ),
            (
                self.ui.templateUndercutSurfaceModelSelector,
                self.logic.isTemplateUndercutSurfaceModelNode,
            ),
            (
                self.ui.templateUndercutBlockoutModelSelector,
                self.logic.isTemplateUndercutBlockoutModelNode,
            ),
            (
                self.ui.patientContactShellModelSelector,
                self.logic.isPatientContactShellModelNode,
            ),
            (
                self.ui.templateShellRoiSelector,
                self.logic.isTemplateShellRoiNode,
            ),
            (
                self.ui.researchTemplateShellModelSelector,
                self.logic.isResearchTemplateModelNode,
            ),
            (
                self.ui.researchTemplateSleeveModelSelector,
                self.logic.isResearchTemplateModelNode,
            ),
        ):
            self._updateNodeSelectorLineageSwatches(
                selector,
                acceptsNode,
            )

        selectorNodes = (
            (self.ui.templateInsertionDirectionSelector, insertionDirection),
            (self.ui.templateUndercutSurfaceModelSelector, undercutModel),
            (self.ui.templateUndercutBlockoutModelSelector, blockoutModel),
            (self.ui.patientContactShellModelSelector, patientContactShell),
        )
        if any(selector.currentNode() is not node for selector, node in selectorNodes):
            self._updatingTemplateGuideUI = True
            try:
                for selector, node in selectorNodes:
                    selector.setCurrentNode(node)
            finally:
                self._updatingTemplateGuideUI = False
        self.ui.patientContactShellSourceValueLabel.text = (
            visibleSupportModel.GetName()
            if self.logic.isVisibleTemplateSupportModelNode(visibleSupportModel)
            else _("--")
        )
        visibleCurrent = False
        try:
            visibleCurrent = (
                self.logic.getVisibleTemplateSupportModelSummary(
                    visibleSupportModel
                )["geometryState"]
                == "Current"
            )
        except (RuntimeError, ValueError, json.JSONDecodeError):
            pass
        self.ui.createTemplateInsertionDirectionButton.enabled = visibleCurrent
        self.ui.deleteTemplateInsertionDirectionButton.enabled = bool(
            self.logic.isTemplateInsertionDirectionNode(insertionDirection)
            or self.logic.isTemplateUndercutSurfaceModelNode(undercutModel)
            or self.logic.isTemplateUndercutBlockoutModelNode(blockoutModel)
        )

        directionSummary = None
        directionError = ""
        try:
            directionSummary = self.logic.getTemplateInsertionDirectionSummary(
                insertionDirection
            )
            if directionSummary["sourceSurface"] is not visibleSupportModel:
                raise ValueError(
                    _("The insertion direction belongs to another support surface.")
                )
            visibleSummaryForDirection = (
                self.logic.getVisibleTemplateSupportModelSummary(
                    visibleSupportModel
                )
            )
            if (
                directionSummary["sourceTrajectory"]
                and directionSummary["sourceTrajectory"]
                is not visibleSummaryForDirection["directionTrajectory"]
            ):
                raise ValueError(
                    _("The insertion direction belongs to another trajectory.")
                )
        except (RuntimeError, ValueError) as exc:
            directionError = str(exc)

        undercutParameters = {
            "angleToleranceDeg": float(
                self._parameterNode.templateUndercutAngleToleranceDeg
            ),
            "interproximalReliefMm": float(
                self._parameterNode.templateInterproximalReliefMm
            ),
            "processingResolutionMm": float(
                self._parameterNode.templateSamplingSpacingMm
            ),
            "paddingMm": max(
                5.0,
                4.0 * float(self._parameterNode.templateSamplingSpacingMm),
            ),
        }
        undercutParametersJson = json.dumps(
            undercutParameters,
            sort_keys=True,
            separators=(",", ":"),
        )
        undercutSummary = None
        blockoutSummary = None
        undercutOutputError = ""
        for modelNode, role in (
            (undercutModel, "TemplateUndercutSurface"),
            (blockoutModel, "TemplateUndercutBlockout"),
        ):
            if not modelNode:
                continue
            try:
                summary = self.logic.getTemplateUndercutOutputSummary(
                    modelNode,
                    role,
                )
                if role == "TemplateUndercutSurface":
                    undercutSummary = summary
                else:
                    blockoutSummary = summary
            except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                undercutOutputError = str(exc)
        if directionSummary and (undercutSummary or blockoutSummary):
            staleReason = ""
            for summary in (undercutSummary, blockoutSummary):
                if not summary or summary["geometryState"] != "Current":
                    continue
                if summary["sourceModel"] is not supportModel:
                    staleReason = _("The full support anatomy changed.")
                elif summary["visibleSupport"] is not visibleSupportModel:
                    staleReason = _("The visible support surface changed.")
                elif summary["insertionDirection"] is not insertionDirection:
                    staleReason = _("The insertion direction node changed.")
                elif summary["parametersJson"] != undercutParametersJson:
                    staleReason = _("Undercut tolerance or processing resolution changed.")
                elif summary["insertionGeometryJson"] != directionSummary["geometryJson"]:
                    staleReason = _("The insertion direction points changed.")
                elif summary["sourceModelUpdatedUtc"] != (
                    supportModel.GetAttribute("DENTOBOT.UpdatedUtc") or ""
                ):
                    staleReason = _("The full support anatomy was regenerated.")
                elif summary["visibleSupportUpdatedUtc"] != (
                    visibleSupportModel.GetAttribute("DENTOBOT.UpdatedUtc") or ""
                ):
                    staleReason = _("The visible support surface was regenerated.")
                if staleReason:
                    break
            if staleReason:
                self.logic.markTemplateUndercutOutputsStale(
                    undercutModel,
                    blockoutModel,
                    staleReason,
                )
                if undercutSummary:
                    undercutSummary = self.logic.getTemplateUndercutOutputSummary(
                        undercutModel,
                        "TemplateUndercutSurface",
                    )
                if blockoutSummary:
                    blockoutSummary = self.logic.getTemplateUndercutOutputSummary(
                        blockoutModel,
                        "TemplateUndercutBlockout",
                    )
        blockoutCurrent = bool(
            blockoutSummary and blockoutSummary["geometryState"] == "Current"
        )
        self.ui.analyzeTemplateUndercutsButton.enabled = bool(
            visibleCurrent and directionSummary and not undercutOutputError
        )

        patientParameters = None
        patientInputError = ""
        try:
            patientParameters = self.logic.patientContactShellParameters(
                self._parameterNode.templateShellClearanceMm,
                self._parameterNode.templateShellThicknessMm,
                self._parameterNode.templateSamplingSpacingMm,
                self._parameterNode.templateBlockoutSafetyMm,
                self._parameterNode.templateShellVoxelClosingMm,
            )
            self.logic.validatePatientContactShellInputs(
                supportModel,
                visibleSupportModel,
                insertionDirection,
                blockoutModel,
                patientParameters,
            )
        except (RuntimeError, ValueError) as exc:
            patientInputError = str(exc)

        patientSummary = None
        patientOutputError = ""
        if patientContactShell:
            try:
                patientSummary = self.logic.getPatientContactShellSummary(
                    patientContactShell
                )
            except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                patientOutputError = str(exc)
        if patientSummary and patientSummary["geometryState"] == "Current":
            staleReason = ""
            currentParametersJson = (
                json.dumps(
                    patientParameters,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                if patientParameters
                else ""
            )
            if patientInputError:
                staleReason = patientInputError
            elif patientSummary["sourceModel"] is not supportModel:
                staleReason = _("The full support-anatomy model changed.")
            elif patientSummary["visibleSupport"] is not visibleSupportModel:
                staleReason = _("The visible support surface changed.")
            elif patientSummary["insertionDirection"] is not insertionDirection:
                staleReason = _("The insertion direction changed.")
            elif patientSummary["blockoutModel"] is not blockoutModel:
                staleReason = _("The directional blockout changed.")
            elif patientSummary["parametersJson"] != currentParametersJson:
                staleReason = _("Shell fit, blockout, smoothing, or resolution changed.")
            elif patientSummary["sourceModelUpdatedUtc"] != (
                supportModel.GetAttribute("DENTOBOT.UpdatedUtc") or ""
            ):
                staleReason = _("The full support anatomy was regenerated.")
            elif patientSummary["visibleSupportUpdatedUtc"] != (
                visibleSupportModel.GetAttribute("DENTOBOT.UpdatedUtc") or ""
            ):
                staleReason = _("The visible support surface was regenerated.")
            elif patientSummary["insertionGeometryJson"] != directionSummary["geometryJson"]:
                staleReason = _("The insertion direction points changed.")
            elif patientSummary["blockoutUpdatedUtc"] != (
                blockoutModel.GetAttribute("DENTOBOT.UpdatedUtc") or ""
            ):
                staleReason = _("The directional blockout was regenerated.")
            if staleReason:
                self.logic.markPatientContactShellStale(
                    patientContactShell,
                    staleReason,
                )
                patientSummary = self.logic.getPatientContactShellSummary(
                    patientContactShell
                )

        self.ui.generatePatientContactShellButton.enabled = bool(
            not patientInputError and not patientOutputError
        )
        self.ui.deletePatientContactShellButton.enabled = bool(
            self.logic.isPatientContactShellModelNode(patientContactShell)
        )
        if patientOutputError:
            patientMessage, patientStyle = patientOutputError, "color: #b00020;"
        elif undercutOutputError:
            patientMessage, patientStyle = undercutOutputError, "color: #b00020;"
        elif not visibleCurrent:
            patientMessage, patientStyle = (
                _("Generate a current visible support preview in Step 5A first."),
                "color: #b36b00;",
            )
        elif directionError:
            patientMessage, patientStyle = directionError, "color: #b36b00;"
        elif not blockoutCurrent:
            if blockoutSummary:
                patientMessage = _("Directional blockout is stale: %1").replace(
                    "%1",
                    blockoutSummary["staleReason"] or _("regeneration required"),
                )
            else:
                patientMessage = _(
                    "Insertion direction is ready. Analyze undercuts to create the "
                    "directional blockout."
                )
            patientStyle = "color: #1f5f99;"
        elif patientInputError:
            patientMessage, patientStyle = patientInputError, "color: #b36b00;"
        elif patientSummary and patientSummary["geometryState"] == "Current":
            patientMessage = (
                _(
                    "Undercut-aware patient-contact shell is current (%1 triangles, "
                    "%2 component(s))."
                )
                .replace(
                    "%1",
                    str(patientSummary["metrics"].get("triangleCount", "--")),
                )
                .replace(
                    "%2",
                    str(patientSummary["metrics"].get("surfaceRegionCount", "--")),
                )
            )
            if patientSummary["warnings"]:
                patientMessage += " " + " ".join(patientSummary["warnings"])
                patientStyle = "color: #b36b00;"
            else:
                patientStyle = "color: #207227;"
        elif patientSummary:
            patientMessage = _("Patient-contact shell is stale: %1").replace(
                "%1",
                patientSummary["staleReason"] or _("regeneration required"),
            )
            patientStyle = "color: #b36b00;"
        else:
            patientMessage = _(
                "Directional blockout and fit parameters are current. Generate the "
                "undercut-aware patient-contact shell."
            )
            patientStyle = "color: #1f5f99;"
        self.ui.patientContactShellStatusLabel.text = patientMessage
        self.ui.patientContactShellStatusLabel.styleSheet = patientStyle
        self._updateFinalPrintableTemplateControls(patientContactShell, supportModel)
        self._updateTemplateGuideVisibilityControls()
        # The remaining research-shell/ROI/sleeve controller below is retained
        # only so older scenes can still deserialize their derived nodes.  It
        # is no longer part of, or executed by, the active 5B workflow.
        return
        self.ui.createTemplateShellRoiButton.enabled = bool(
            supportModel
            and self.logic.isDraftTemplateSupportModelNode(supportModel)
        )
        self.ui.deleteTemplateShellRoiButton.enabled = bool(
            self.logic.isTemplateShellRoiNode(roiNode)
            and slicer.mrmlScene.IsNodePresent(roiNode)
        )

        inputError = ""
        parameters = self._templateGuideParameters()
        normalizedParameters = None
        validatedInputs = None
        try:
            normalizedParameters = self.logic._templateGuideParameters(
                parameters["clearanceMm"],
                parameters["thicknessMm"],
                parameters["samplingSpacingMm"],
                parameters["channelDiameterMm"],
                parameters["sleeveOuterDiameterMm"],
                parameters["sleeveInnerDiameterMm"],
                parameters["sleeveHeightMm"],
            )
            validatedInputs = self.logic.validateResearchTemplateInputs(
                supportModel,
                trajectoryNode,
                roiNode,
                normalizedParameters,
            )
        except (RuntimeError, ValueError) as exc:
            inputError = str(exc)

        summaries = []
        outputError = ""
        for modelNode, role in (
            (shellModel, "ResearchTemplateShell"),
            (sleeveModel, "ResearchTemplateSleeve"),
        ):
            if not modelNode:
                summaries.append(None)
                continue
            try:
                summaries.append(
                    self.logic.getResearchTemplateModelSummary(modelNode, role)
                )
            except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                summaries.append(None)
                outputError = str(exc)

        shellSummary, sleeveSummary = summaries
        if (shellSummary or sleeveSummary) and not validatedInputs:
            self.logic.markResearchTemplateModelsStale(
                shellModel,
                sleeveModel,
                inputError or _("A required Step 5B input is unavailable."),
            )
            if shellSummary:
                shellSummary = self.logic.getResearchTemplateModelSummary(
                    shellModel,
                    "ResearchTemplateShell",
                )
            if sleeveSummary:
                sleeveSummary = self.logic.getResearchTemplateModelSummary(
                    sleeveModel,
                    "ResearchTemplateSleeve",
                )
        if validatedInputs and shellSummary and sleeveSummary:
            currentTrajectoryJson = json.dumps(
                {
                    "entryRas": validatedInputs["trajectorySummary"]["entryRas"],
                    "targetRas": validatedInputs["trajectorySummary"]["targetRas"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            currentRoiJson = json.dumps(
                validatedInputs["roiBoundsRas"],
                separators=(",", ":"),
            )
            currentParametersJson = json.dumps(
                normalizedParameters,
                sort_keys=True,
                separators=(",", ":"),
            )
            sourceUpdatedUtc = supportModel.GetAttribute("DENTOBOT.UpdatedUtc") or ""
            differs = any(
                summary["sourceModel"] is not supportModel
                or summary["trajectory"] is not trajectoryNode
                or summary["roi"] is not roiNode
                or summary["parametersJson"] != currentParametersJson
                or summary["trajectoryGeometryJson"] != currentTrajectoryJson
                or summary["roiBoundsRasJson"] != currentRoiJson
                or summary["sourceModelUpdatedUtc"] != sourceUpdatedUtc
                for summary in (shellSummary, sleeveSummary)
            )
            if differs:
                self.logic.markResearchTemplateModelsStale(
                    shellModel,
                    sleeveModel,
                    _("Step 4B support draft, trajectory, ROI, or dimensions changed."),
                )
                shellSummary = self.logic.getResearchTemplateModelSummary(
                    shellModel,
                    "ResearchTemplateShell",
                )
                sleeveSummary = self.logic.getResearchTemplateModelSummary(
                    sleeveModel,
                    "ResearchTemplateSleeve",
                )

        canGenerate = bool(validatedInputs and not outputError)
        bothCurrent = bool(
            shellSummary
            and sleeveSummary
            and shellSummary["geometryState"] == "Current"
            and sleeveSummary["geometryState"] == "Current"
        )
        self.ui.generateResearchTemplateButton.enabled = canGenerate
        self.ui.deleteResearchTemplateButton.enabled = bool(
            self.logic.isResearchTemplateModelNode(shellModel)
            or self.logic.isResearchTemplateModelNode(sleeveModel)
        )

        if rejectedRoiWarning:
            message, style = rejectedRoiWarning, "color: #b00020;"
        elif outputError:
            message, style = outputError, "color: #b00020;"
        elif inputError:
            message, style = inputError, "color: #b36b00;"
        elif shellSummary and sleeveSummary and not bothCurrent:
            message, style = (
                _("Step 5B outputs are stale. Regenerate after reviewing the current inputs."),
                "color: #b36b00;",
            )
        elif bothCurrent:
            warnings = list(dict.fromkeys(shellSummary["warnings"] + sleeveSummary["warnings"]))
            if warnings:
                message = _("Research template generated with warnings: %1").replace(
                    "%1", " ".join(warnings)
                )
                style = "color: #b36b00;"
            else:
                message = (
                    _("Research shell and sleeve are current and ready for Step 5C fit and trim.")
                )
                style = "color: #207227;"
        else:
            message, style = (
                _("Inputs are ready. Generate the research shell and sleeve."),
                "color: #1f5f99;",
            )
        self.ui.templateGuideStatusLabel.text = message
        self.ui.templateGuideStatusLabel.styleSheet = style

    def onTemplateGuideInputChanged(self, *args) -> None:
        del args
        if not self._updatingTemplateGuideUI:
            self._updateTemplateGuide()
            self._updateTemplateFinalization()

    def onPatientContactShellSelectionChanged(self, modelNode) -> None:
        if self._updatingTemplateGuideUI or not self._parameterNode:
            return
        currentNode = self._parameterNode.patientContactShellModel
        if (currentNode.GetID() if currentNode else None) != (
            modelNode.GetID() if modelNode else None
        ):
            self._parameterNode.patientContactShellModel = modelNode
        self._updateTemplateGuide()

    def onTemplateInsertionDirectionSelectionChanged(self, lineNode) -> None:
        if self._updatingTemplateGuideUI or not self._parameterNode:
            return
        currentNode = self._parameterNode.templateInsertionDirection
        if (currentNode.GetID() if currentNode else None) != (
            lineNode.GetID() if lineNode else None
        ):
            self._parameterNode.templateInsertionDirection = lineNode
            self._bindTemplateInsertionDirectionNode(lineNode)
            self._invalidateTemplateUndercutDownstream(
                _("The selected template insertion direction changed."),
            )
        self._updateTemplateGuide()

    def onTemplateUndercutOutputSelectionChanged(self, *args) -> None:
        del args
        if self._updatingTemplateGuideUI or not self._parameterNode:
            return
        self._parameterNode.templateUndercutSurfaceModel = (
            self.ui.templateUndercutSurfaceModelSelector.currentNode()
        )
        self._parameterNode.templateUndercutBlockoutModel = (
            self.ui.templateUndercutBlockoutModelSelector.currentNode()
        )
        self._updateTemplateGuide()

    def onCreateTemplateInsertionDirection(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            visibleSupport = self._parameterNode.visibleTemplateSupportModel
            visibleSummary = self.logic.getVisibleTemplateSupportModelSummary(
                visibleSupport
            )
            trajectoryNode = visibleSummary["directionTrajectory"]
            lineNode = self.logic.createOrUpdateTemplateInsertionDirectionFromTrajectory(
                visibleSupport,
                trajectoryNode,
                reverseDirection=visibleSummary["directionReversed"],
                lineNode=self._parameterNode.templateInsertionDirection,
            )
            visibleSupport.SetNodeReferenceID(
                self.logic.TEMPLATE_VISIBLE_SUPPORT_INSERTION_DIRECTION_REFERENCE_ROLE,
                lineNode.GetID(),
            )
            self._parameterNode.templateInsertionDirection = lineNode
            self._bindTemplateInsertionDirectionNode(lineNode)
            self._invalidateTemplateUndercutDownstream(
                _("The trajectory-derived template insertion direction was refreshed."),
            )
            self._updateTemplateGuide()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onCreateManualTemplateInsertionDirection(self) -> None:
        """Legacy developer fallback retained outside the routine UI path."""

        if not self._parameterNode or not self.logic:
            return
        try:
            lineNode = self.logic.createOrResetTemplateInsertionDirection(
                self._parameterNode.visibleTemplateSupportModel,
                self._parameterNode.templateInsertionDirection,
            )
            self._parameterNode.templateInsertionDirection = lineNode
            self._bindTemplateInsertionDirectionNode(lineNode)
            self._invalidateTemplateUndercutDownstream(
                _("The manual template insertion direction was reset."),
            )
            self.logic.startLinePlacement(lineNode)
            self._updateTemplateGuide()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onDeleteTemplateInsertionDirection(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Delete the insertion direction, undercut preview, and directional "
                "blockout? The patient-contact shell will also be deleted because it "
                "depends on this blockout. Visible support anatomy is preserved."
            ),
            windowTitle=_("Delete insertion and undercut workflow"),
        ):
            return
        try:
            if self.logic.isPatientContactShellModelNode(
                self._parameterNode.patientContactShellModel
            ):
                self._deleteFinalPrintableTemplateCascade()
                self.logic.deletePatientContactShell(
                    self._parameterNode.patientContactShellModel
                )
            removals = self.logic.deleteTemplateUndercutWorkflow(
                self._parameterNode.templateInsertionDirection,
                self._parameterNode.templateUndercutSurfaceModel,
                self._parameterNode.templateUndercutBlockoutModel,
            )
            self._bindTemplateInsertionDirectionNode(None)
            logging.info(
                "Deleted template insertion/undercut subtree containing %d nodes",
                len(removals),
            )
            self._updateTemplateGuide()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def _createOrUpdateTemplateUndercuts(self):
        if not self._parameterNode or not self.logic:
            raise RuntimeError(_("DENTOWorkflow is not ready."))
        undercutModel, blockoutModel, details = (
            self.logic.createOrUpdateTemplateUndercutAnalysis(
                self._parameterNode.draftTemplateSupportModel,
                self._parameterNode.visibleTemplateSupportModel,
                self._parameterNode.templateInsertionDirection,
                angleToleranceDeg=(
                    self._parameterNode.templateUndercutAngleToleranceDeg
                ),
                interproximalReliefMm=(
                    self._parameterNode.templateInterproximalReliefMm
                ),
                samplingSpacingMm=self._parameterNode.templateSamplingSpacingMm,
                undercutModel=self._parameterNode.templateUndercutSurfaceModel,
                blockoutModel=self._parameterNode.templateUndercutBlockoutModel,
            )
        )
        self._parameterNode.templateUndercutSurfaceModel = undercutModel
        self._parameterNode.templateUndercutBlockoutModel = blockoutModel
        self.logic.markPatientContactShellStale(
            self._parameterNode.patientContactShellModel,
            _("The directional undercut blockout was regenerated."),
        )
        logging.info(
            "Updated directional blockout %s from %d retentive surface cells",
            blockoutModel.GetID(),
            details["undercut"]["undercutTriangleCount"],
        )
        self._updateTemplateGuide()
        return undercutModel, blockoutModel, details

    def onAnalyzeTemplateUndercuts(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            self._createOrUpdateTemplateUndercuts()
        except (RuntimeError, ValueError) as exc:
            self.ui.patientContactShellStatusLabel.text = str(exc)
            self.ui.patientContactShellStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def onTemplateGuideTrajectoryItemChanged(self, item) -> None:
        del item
        if (
            self._updatingGuideTrajectorySelectionUI
            or self._updatingTemplateGuideUI
            or not self._parameterNode
            or not self.logic
        ):
            return
        try:
            selected = self._selectedTemplateGuideTrajectoryItems()
            self.logic.setSelectedTemplateGuideTrajectories(
                self._parameterNode.draftTemplateSupportModel,
                selected,
            )
            self.logic.markFinalPrintableTemplateStale(
                self._parameterNode.finalPrintableTemplateModel,
                _("The selected guide trajectories changed."),
            )
            self._updateTemplateGuide()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onFinalPrintableTemplateSelectionChanged(self, modelNode) -> None:
        if self._updatingTemplateGuideUI or not self._parameterNode:
            return
        self._parameterNode.finalPrintableTemplateModel = modelNode
        self._updateTemplateGuide()

    def _createOrUpdateFinalPrintableTemplate(self):
        if not self._parameterNode or not self.logic:
            raise RuntimeError(_("DENTOWorkflow is not ready."))
        targetDockingAssembly = self._parameterNode.targetDockingAssemblyModel
        try:
            trajectories = self.logic.getTargetDockingAssemblySummary(
                targetDockingAssembly
            )["trajectories"]
        except (RuntimeError, ValueError, json.JSONDecodeError):
            trajectories = []
        finalModel, roleModels, details = (
            self.logic.createOrUpdateFinalPrintableTemplate(
                self._parameterNode.patientContactShellModel,
                targetDockingAssembly,
                trajectories,
                outerDiameterMm=self._parameterNode.templateSleeveOuterDiameterMm,
                innerDiameterMm=self._parameterNode.templateSleeveInnerDiameterMm,
                heightMm=self._parameterNode.templateSleeveHeightMm,
                dockingClearanceMm=self._parameterNode.templateDockingClearanceMm,
                reinforcementRadialMm=(
                    self._parameterNode.templateReinforcementRadialMm
                ),
                reinforcementDepthMm=(
                    self._parameterNode.templateReinforcementDepthMm
                ),
                samplingSpacingMm=self._parameterNode.templateSamplingSpacingMm,
                dockingModel=self._parameterNode.templateDockingAssemblyModel,
                clearanceModel=self._parameterNode.templateDockingClearanceModel,
                reinforcementModel=(
                    self._parameterNode.templateDockingReinforcementModel
                ),
                channelsModel=self._parameterNode.templateDockingChannelsModel,
                finalModel=self._parameterNode.finalPrintableTemplateModel,
            )
        )
        self._parameterNode.templateDockingAssemblyModel = roleModels["docking"]
        self._parameterNode.templateDockingClearanceModel = roleModels["clearance"]
        self._parameterNode.templateDockingReinforcementModel = roleModels[
            "reinforcement"
        ]
        self._parameterNode.templateDockingChannelsModel = roleModels["channels"]
        self._parameterNode.finalPrintableTemplateModel = finalModel
        logging.info(
            "Generated unified template %s from %d trajectories with %d triangles",
            finalModel.GetID(),
            details["assembly"]["trajectoryCount"],
            details["fusion"]["triangleCount"],
        )
        self._updateTemplateGuide()
        self._updateTemplateFinalization()
        return finalModel, roleModels, details

    def onGenerateFinalPrintableTemplate(self) -> None:
        """Compatibility action: rebuild only the unified fusion stage."""

        if not self._parameterNode or not self.logic:
            return
        try:
            self._createOrUpdateFinalPrintableTemplate()
        except (RuntimeError, ValueError) as exc:
            self.ui.templateDockingFusionStatusLabel.text = str(exc)
            self.ui.templateDockingFusionStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def _completeTemplateBuildPreflight(self) -> dict:
        if not self._parameterNode or not self.logic:
            raise RuntimeError(_("DENTOWorkflow is not ready."))
        sourceSummary = self.logic.getDraftTemplateSupportModelSummary(
            self._parameterNode.draftTemplateSupportModel
        )
        if sourceSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale Step 4B support draft first."))
        visibleSummary = self.logic.getVisibleTemplateSupportModelSummary(
            self._parameterNode.visibleTemplateSupportModel
        )
        if visibleSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale visible support preview first."))
        if visibleSummary["sourceModel"] is not self._parameterNode.draftTemplateSupportModel:
            raise ValueError(_("The visible support preview belongs to another support model."))
        directionSummary = self.logic.getTemplateInsertionDirectionSummary(
            self._parameterNode.templateInsertionDirection
        )
        if directionSummary["sourceSurface"] is not self._parameterNode.visibleTemplateSupportModel:
            raise ValueError(_("Refresh the insertion direction from the current trajectory."))
        dockingSummary = self.logic.getTargetDockingAssemblySummary(
            self._parameterNode.targetDockingAssemblyModel
        )
        if dockingSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale Step 4C docking assembly first."))
        if dockingSummary["orientationState"] != "Confirmed":
            raise ValueError(
                _(
                    "Confirm the collision-screened Step 4C dock orientation "
                    "before building the complete template."
                )
            )
        if (
            dockingSummary["segmentation"] is not sourceSummary["sourceSegmentation"]
            or dockingSummary["targetSegmentId"] != sourceSummary["targetSegmentId"]
        ):
            raise ValueError(_("The Step 4C assembly belongs to another target anatomy."))
        if not dockingSummary["trajectories"]:
            raise ValueError(_("The Step 4C assembly has no source trajectory."))
        for trajectoryNode in dockingSummary["trajectories"]:
            trajectorySummary = self.logic.getTrajectorySummary(trajectoryNode)
            if (
                not trajectorySummary["isValid"]
                or trajectorySummary["definedPointCount"] != 2
                or not trajectoryNode.GetLocked()
            ):
                raise ValueError(
                    _("Complete and lock every Step 4A source trajectory first.")
                )
        return {
            "sourceSummary": sourceSummary,
            "visibleSummary": visibleSummary,
            "directionSummary": directionSummary,
            "dockingSummary": dockingSummary,
        }

    def onBuildOrUpdateCompleteTemplate(self) -> None:
        """Generate only missing/stale Step 5B stages, then inspect the result."""

        if not self._parameterNode or not self.logic:
            return
        generatedStages = []
        reusedStages = []
        try:
            # Preflight the inexpensive plan/dock contracts before any voxel work.
            self._completeTemplateBuildPreflight()
            self._updateTemplateGuide()

            blockoutCurrent = False
            try:
                blockoutCurrent = (
                    self.logic.getTemplateUndercutOutputSummary(
                        self._parameterNode.templateUndercutBlockoutModel,
                        "TemplateUndercutBlockout",
                    )["geometryState"]
                    == "Current"
                )
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass
            if blockoutCurrent:
                reusedStages.append(_("directional blockout"))
            else:
                self._createOrUpdateTemplateUndercuts()
                generatedStages.append(_("directional blockout"))

            shellCurrent = False
            try:
                shellCurrent = (
                    self.logic.getPatientContactShellSummary(
                        self._parameterNode.patientContactShellModel
                    )["geometryState"]
                    == "Current"
                )
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass
            if shellCurrent:
                reusedStages.append(_("patient shell"))
            else:
                self._createOrUpdatePatientContactShell()
                generatedStages.append(_("patient shell"))

            self._updateTemplateGuide()
            finalCurrent = False
            try:
                finalCurrent = (
                    self.logic.getFinalPrintableTemplateSummary(
                        self._parameterNode.finalPrintableTemplateModel
                    )["geometryState"]
                    == "Current"
                )
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass
            if finalCurrent:
                reusedStages.append(_("unified guide/dock fusion"))
            else:
                self._createOrUpdateFinalPrintableTemplate()
                generatedStages.append(_("unified guide/dock fusion"))

            self.ui.templateDockingFusionGroupBox.collapsed = False
            self._applyWorkflowViewPreset("final_only")
            self.onFrameWorkflowView()
            generatedText = ", ".join(generatedStages) or _("none")
            reusedText = ", ".join(reusedStages) or _("none")
            self.ui.templateDockingFusionStatusLabel.text = (
                _("Complete template is current. Generated: %1. Reused: %2.")
                .replace("%1", generatedText)
                .replace("%2", reusedText)
            )
            self.ui.templateDockingFusionStatusLabel.styleSheet = "color: #207227;"
        except (RuntimeError, ValueError) as exc:
            self.ui.templateDockingFusionGroupBox.collapsed = False
            self.ui.templateDockingFusionStatusLabel.text = str(exc)
            self.ui.templateDockingFusionStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def _inspectTemplatePreset(self, presetKey: str) -> None:
        if not self._parameterNode or not self.logic:
            return
        self._applyWorkflowViewPreset(presetKey)
        self.onFrameWorkflowView()

    def onInspectTemplateFit(self) -> None:
        self._inspectTemplatePreset("undercut_analysis")

    def onInspectShellAndGuides(self) -> None:
        self._inspectTemplatePreset("shell_guides")

    def onInspectUnifiedTemplate(self) -> None:
        self._inspectTemplatePreset("final_only")

    def onDeleteFinalPrintableTemplate(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        finalModel = self._parameterNode.finalPrintableTemplateModel
        if not self.logic.isFinalPrintableTemplateModelNode(finalModel):
            slicer.util.errorDisplay(_("Select the DENTOBOT unified template to delete."))
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Delete the unified template and its docking, clearance, reinforcement, "
                "and channel provenance models? The patient-contact shell, trajectories, "
                "and authoritative segmentation are preserved."
            ),
            windowTitle=_("Delete unified printable template"),
        ):
            return
        try:
            removals = self.logic.deleteFinalPrintableTemplate(finalModel)
            logging.info(
                "Deleted unified template subtree containing %d nodes",
                len(removals),
            )
            self._updateTemplateGuide()
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def _deleteFinalPrintableTemplateCascade(self) -> list[dict]:
        finalModel = (
            self._parameterNode.finalPrintableTemplateModel
            if self._parameterNode
            else None
        )
        if not self.logic.isFinalPrintableTemplateModelNode(finalModel):
            return []
        return self.logic.deleteFinalPrintableTemplate(finalModel)
