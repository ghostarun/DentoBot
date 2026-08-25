"""Extracted planning focus and assisted trajectory methods; public APIs remain on PlanningWidgetMixin."""

from __future__ import annotations

from .runtime import *


class PlanningFocusWidgetMixin:
    @staticmethod
    def _nodeSelectorComboBox(selector):
        """Return the PythonQt-accessible combo embedded in a node selector."""

        return next(
            (
                child
                for child in selector.children()
                if hasattr(child, "setItemData")
                and hasattr(child, "count")
            ),
            None,
        )

    def _updateNodeSelectorLineageSwatches(
        self,
        selector,
        acceptsNode,
    ) -> None:
        """Show persisted lineage colors beside owned nodes in a selector."""

        if not selector or not self.logic:
            return
        comboBox = self._nodeSelectorComboBox(selector)
        if comboBox is None:
            return
        for index in range(comboBox.count):
            node = selector.nodeFromIndex(index)
            if not acceptsNode(node):
                continue
            color = self.logic.lineageColorFromNode(node)
            if not color:
                comboBox.setItemData(
                    index,
                    qt.QColor(),
                    qt.Qt.DecorationRole,
                )
                continue
            qColor = qt.QColor(
                *(int(round(component * 255.0)) for component in color)
            )
            comboBox.setItemData(index, qColor, qt.Qt.DecorationRole)

    def _updateTrajectorySelectorColorSwatches(self) -> None:
        """Decorate every persisted trajectory group in the shared selector."""

        if not hasattr(self, "ui") or not self.logic:
            return
        self._updateNodeSelectorLineageSwatches(
            self.ui.trajectorySelector,
            self.logic.isDentobotTrajectoryNode,
        )

    @staticmethod
    def _lineageStyleSheet(
        color: tuple[float, float, float] | None,
        *,
        borderWidth: int = 8,
    ) -> str:
        """Return a readable Qt style using a lineage color as the anchor."""

        if not color:
            return (
                "QLabel { color: #555555; background-color: #eeeeee; "
                f"border-left: {borderWidth}px solid #999999; "
                "border-radius: 3px; padding: 5px 8px; }"
            )
        rgb = tuple(
            int(round(max(0.0, min(1.0, component)) * 255.0))
            for component in color
        )
        background = tuple(
            int(round(255 - (255 - component) * 0.18))
            for component in rgb
        )
        return (
            "QLabel { color: #151515; "
            f"background-color: rgb{background}; "
            f"border-left: {borderWidth}px solid rgb{rgb}; "
            "border-radius: 3px; padding: 5px 8px; font-weight: 600; }"
        )

    def _lineageSourceNode(self, nodes, targetSegmentId: str = ""):
        """Choose the first colored node matching the requested target."""

        if not self.logic:
            return None
        for node in nodes:
            if not node or not self.logic.lineageColorFromNode(node):
                continue
            if (
                targetSegmentId
                and node.GetAttribute(
                    self.logic.LINEAGE_TARGET_SEGMENT_ATTRIBUTE
                )
                != targetSegmentId
            ):
                continue
            return node
        if targetSegmentId:
            for className in (
                "vtkMRMLMarkupsLineNode",
                "vtkMRMLModelNode",
                "vtkMRMLMarkupsROINode",
            ):
                for node in slicer.util.getNodesByClass(className):
                    if (
                        node.GetAttribute(
                            self.logic.LINEAGE_TARGET_SEGMENT_ATTRIBUTE
                        )
                        == targetSegmentId
                        and self.logic.lineageColorFromNode(node)
                    ):
                        return node
        return None

    def _updateLineageBadge(
        self,
        label,
        node,
        linkedSteps: str,
        emptyText: str,
    ) -> None:
        """Render an explicit target-lineage badge in a downstream step."""

        color = self.logic.lineageColorFromNode(node) if node else None
        label.styleSheet = self._lineageStyleSheet(color)
        if not color:
            label.text = emptyText
            return
        fdiNumber = node.GetAttribute(
            self.logic.LINEAGE_TARGET_FDI_ATTRIBUTE
        ) or ""
        segmentId = node.GetAttribute(
            self.logic.LINEAGE_TARGET_SEGMENT_ATTRIBUTE
        ) or ""
        targetName = (
            _("FDI %1").replace("%1", fdiNumber)
            if fdiNumber
            else segmentId
            if segmentId
            else _("target tooth")
        )
        rgb255 = tuple(int(round(component * 255.0)) for component in color)
        colorHex = "#{:02X}{:02X}{:02X}".format(*rgb255)
        label.text = (
            _("%1 lineage: %2  •  %3  •  %4")
            .replace("%1", linkedSteps)
            .replace("%2", targetName)
            .replace("%3", colorHex)
            .replace("%4", _("same parent/child group"))
        )

    def _clearPlanning(self) -> None:
        if not hasattr(self, "ui"):
            return
        if self._trajectoryVerificationEnabled:
            self._restoreTrajectoryVerificationViewState(updateUi=False)
        self._updatingPlanningUI = True
        try:
            self._targetToothRecordsById = {}
            self.ui.targetToothComboBox.clear()
            self.ui.targetToothComboBox.addItem(_("Select target tooth..."), "")
            self.ui.targetToothComboBox.enabled = False
            self.ui.targetToothValueLabel.text = _("--")
            self.ui.targetToothSourceValueLabel.text = _("--")
            self.ui.createTrajectoryButton.enabled = False
            self.ui.placeTrajectoryButton.enabled = False
            self.ui.placeTrajectoryButton.text = _("Place Both Points")
            self.ui.undoTrajectoryPointButton.enabled = False
            self.ui.resetTrajectoryButton.enabled = False
            self.ui.deleteTrajectoryButton.enabled = False
            self.ui.lockTrajectoryButton.enabled = False
            self.ui.lockTrajectoryButton.checked = False
            self.ui.trajectoryLockStatusLabel.text = _(
                "NO TRAJECTORY SELECTED"
            )
            self.ui.trajectoryLockStatusLabel.styleSheet = (
                "color: #666666; font-weight: 600;"
            )
            self.ui.focusPlanningTargetButton.enabled = False
            self.ui.framePlanningTargetButton.enabled = False
            self.ui.restorePlanningViewButton.enabled = False
            self.ui.trajectoryEntryValueLabel.text = _("--")
            self.ui.trajectoryTargetValueLabel.text = _("--")
            self.ui.trajectoryLengthValueLabel.text = _("--")
            self.ui.targetBoundsValueLabel.text = _("--")
            self._planningConstraintWarning = ""
            self.ui.planningStatusLabel.text = _(
                "Select a dental segmentation before defining a target tooth."
            )
            self.ui.planningStatusLabel.styleSheet = "color: #b36b00;"
        finally:
            self._updatingPlanningUI = False
        self._updateTrajectoryPlacementModeControls()
        self._updateTrajectoryVerificationControls()
        self._updateAssistedTrajectoryControls()

    def _updateAssistedTrajectoryControls(self) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        segmentationNode = self._parameterNode.teethSegmentation
        segmentId = self._parameterNode.targetToothSegmentId
        targetRecord = self._targetToothRecordsById.get(segmentId)
        requestedCount = int(self._parameterNode.assistedTrajectoryCount)
        if requestedCount not in (1, 2):
            requestedCount = 2
            self._parameterNode.assistedTrajectoryCount = requestedCount

        entryNode = self._parameterNode.assistedTrajectoryEntries
        summary = None
        associationError = ""
        if entryNode and targetRecord:
            try:
                summary = self.logic.validateAssistedTrajectoryEntryAssociation(
                    entryNode,
                    segmentationNode,
                    segmentId,
                    requestedCount,
                )
            except ValueError as exc:
                associationError = str(exc)

        existingCount = (
            len(self.logic.dentobotTrajectoriesForTarget(segmentationNode, segmentId))
            if segmentationNode and targetRecord
            else 0
        )
        reviewed = bool(
            segmentationNode
            and self.logic.getSegmentationReviewState(segmentationNode) == "Reviewed"
        )
        self._updatingPlanningUI = True
        try:
            comboIndex = self.ui.assistedTrajectoryCountComboBox.findData(
                requestedCount
            )
            if comboIndex >= 0:
                self.ui.assistedTrajectoryCountComboBox.setCurrentIndex(comboIndex)
            canPrepare = bool(targetRecord and reviewed and existingCount == 0)
            self.ui.assistedTrajectoryCountComboBox.enabled = canPrepare
            self.ui.placeAssistedTrajectoryEntriesButton.enabled = canPrepare
            self.ui.generateAssistedTrajectoriesButton.enabled = bool(
                canPrepare and summary and summary["isComplete"]
            )
            self.ui.restoreAssistedTrajectoryFocusButton.enabled = bool(
                self._assistedTrajectoryFocusState
            )
            self.ui.restorePlanningViewButton.enabled = bool(
                self._workflowViewPriorState
            )
        finally:
            self._updatingPlanningUI = False

        if not targetRecord:
            message = _("Select a target tooth in Step 4A.")
            style = "color: #b36b00;"
        elif not reviewed:
            message = _("Mark the authoritative segmentation Reviewed first.")
            style = "color: #b36b00;"
        elif existingCount:
            message = _(
                "This tooth already has %1 trajectory node(s). Delete that set "
                "before assisted regeneration; existing plans are never overwritten."
            ).replace("%1", str(existingCount))
            style = "color: #b36b00;"
        elif associationError:
            message = associationError
            style = "color: #b36b00;"
        elif not summary:
            message = _(
                "Choose one or two trajectories, then place only the crown entry point(s)."
            )
            style = "color: #1f5f99;"
        elif not summary["isComplete"]:
            message = _("Placed %1 of %2 crown entry point(s).").replace(
                "%1", str(summary["definedPointCount"])
            ).replace("%2", str(summary["expectedCount"]))
            style = "color: #1f5f99;"
        else:
            message = _(
                "Entry points complete. Generate geometric root targets, then "
                "verify and correct every resulting trajectory in the oblique MPR."
            )
            style = "color: #207227;"
        self.ui.assistedTrajectoryStatusLabel.text = message
        self.ui.assistedTrajectoryStatusLabel.styleSheet = style

    def _startAssistedTrajectoryFocus(self) -> None:
        if not self._parameterNode or not self.logic:
            raise RuntimeError(_("DENTOWorkflow is not ready for target focus."))
        self._restoreTemplateSupportBoundaryFocus(updateUi=False)
        self._restoreAssistedTrajectoryFocus(updateUi=False)
        segmentationNode = self._parameterNode.teethSegmentation
        segmentId = self._parameterNode.targetToothSegmentId
        boundsRoi = self._parameterNode.targetToothBoundsRoi
        self._assistedTrajectoryFocusState = self.logic.applyTargetToothFocus(
            segmentationNode,
            segmentId,
            boundsRoi,
        )
        bounds = self.logic.getTargetToothBoundsWorld(
            segmentationNode,
            segmentId,
        )
        self._frameRasBoundsInViews(bounds)
        self._syncSegmentationDisplayControls()
        self._updateAssistedTrajectoryControls()

    @staticmethod
    def _workflowCrosshairNode() -> vtkMRMLCrosshairNode:
        """Return Slicer's singleton crosshair used by native 2D/3D picking."""

        node = slicer.mrmlScene.GetSingletonNode(
            "default",
            "vtkMRMLCrosshairNode",
        )
        if not node:
            raise RuntimeError(_("Slicer's shared crosshair node is unavailable."))
        return node

    def _setCrossViewNavigationChecked(self, checked: bool) -> None:
        if not hasattr(self, "ui"):
            return
        self._updatingCrossViewNavigationUI = True
        try:
            self.ui.crossViewNavigationCheckBox.checked = bool(checked)
        finally:
            self._updatingCrossViewNavigationUI = False

    def _enableCrossViewNavigation(self) -> None:
        """Enable accurate native crosshair picking and centred slice jumps."""

        crosshairNode = self._workflowCrosshairNode()
        if self._crossViewNavigationPriorState is None:
            self._crossViewNavigationPriorState = {
                "nodeId": crosshairNode.GetID(),
                "mode": int(crosshairNode.GetCrosshairMode()),
                "behavior": int(crosshairNode.GetCrosshairBehavior()),
                "thickness": int(crosshairNode.GetCrosshairThickness()),
                "fastPick3D": bool(crosshairNode.GetFastPick3D()),
            }
        wasModifying = crosshairNode.StartModify()
        try:
            crosshairNode.SetCrosshairMode(vtkMRMLCrosshairNode.ShowBasic)
            crosshairNode.SetCrosshairBehavior(
                vtkMRMLCrosshairNode.CenteredJumpSlice
            )
            crosshairNode.SetCrosshairThickness(vtkMRMLCrosshairNode.Fine)
            crosshairNode.SetFastPick3D(False)
        finally:
            crosshairNode.EndModify(wasModifying)
        self._setCrossViewNavigationChecked(True)

    def _restoreCrossViewNavigation(self, updateUi: bool = True) -> None:
        """Restore the exact native crosshair state captured on enable."""

        state = self._crossViewNavigationPriorState
        self._crossViewNavigationPriorState = None
        if state:
            crosshairNode = slicer.mrmlScene.GetNodeByID(state.get("nodeId"))
            if not crosshairNode:
                try:
                    crosshairNode = self._workflowCrosshairNode()
                except RuntimeError:
                    crosshairNode = None
            if crosshairNode:
                wasModifying = crosshairNode.StartModify()
                try:
                    crosshairNode.SetCrosshairMode(int(state["mode"]))
                    crosshairNode.SetCrosshairBehavior(int(state["behavior"]))
                    crosshairNode.SetCrosshairThickness(int(state["thickness"]))
                    crosshairNode.SetFastPick3D(bool(state["fastPick3D"]))
                finally:
                    crosshairNode.EndModify(wasModifying)
        if updateUi:
            self._setCrossViewNavigationChecked(False)

    def onCrossViewNavigationToggled(self, checked: bool) -> None:
        if self._updatingCrossViewNavigationUI:
            return
        try:
            if checked:
                self._enableCrossViewNavigation()
            else:
                self._restoreCrossViewNavigation(updateUi=False)
        except RuntimeError as exc:
            self._restoreCrossViewNavigation(updateUi=True)
            slicer.util.errorDisplay(str(exc))

    @staticmethod
    def _frameRasBoundsInViews(bounds) -> tuple[float, float, float]:
        """Centre finite world-RAS bounds in native Slicer 2D/3D views."""

        values = np.asarray(tuple(bounds), dtype=float)
        if values.shape != (6,) or not np.all(np.isfinite(values)):
            raise ValueError(_("Six finite world-RAS bounds are required."))
        minimum = np.asarray((values[0], values[2], values[4]), dtype=float)
        maximum = np.asarray((values[1], values[3], values[5]), dtype=float)
        extents = maximum - minimum
        if np.any(extents < 0.0):
            raise ValueError(_("World-RAS bounds have reversed limits."))
        center = (minimum + maximum) * 0.5
        paddedSpan = max(float(np.max(extents)) * 1.35, 2.0)

        try:
            slicer.modules.markups.logic().JumpSlicesToLocation(
                float(center[0]),
                float(center[1]),
                float(center[2]),
                True,
            )
        except Exception:
            logging.debug("Could not centre active slice views on workflow bounds.")

        layoutManager = slicer.app.layoutManager()
        if layoutManager:
            try:
                sliceViewNames = tuple(layoutManager.sliceViewNames())
            except Exception:
                sliceViewNames = ()
            for sliceViewName in sliceViewNames:
                try:
                    sliceWidget = layoutManager.sliceWidget(sliceViewName)
                    sliceView = sliceWidget.sliceView()
                    sliceNode = sliceWidget.mrmlSliceNode()
                    widthValue = getattr(sliceView, "width", 1)
                    heightValue = getattr(sliceView, "height", 1)
                    viewWidth = max(
                        int(widthValue() if callable(widthValue) else widthValue),
                        1,
                    )
                    viewHeight = max(
                        int(heightValue() if callable(heightValue) else heightValue),
                        1,
                    )
                    aspect = float(viewWidth) / float(viewHeight)
                    if aspect >= 1.0:
                        fieldWidth = paddedSpan * aspect
                        fieldHeight = paddedSpan
                    else:
                        fieldWidth = paddedSpan
                        fieldHeight = paddedSpan / aspect
                    oldField = sliceNode.GetFieldOfView()
                    fieldDepth = max(float(oldField[2]), paddedSpan)
                    sliceNode.SetFieldOfView(
                        fieldWidth,
                        fieldHeight,
                        fieldDepth,
                    )
                    sliceNode.UpdateMatrices()
                except Exception:
                    logging.debug(
                        "Could not fit workflow bounds in slice view %s.",
                        sliceViewName,
                    )

            try:
                threeDViewCount = int(layoutManager.threeDViewCount)
            except (AttributeError, TypeError, ValueError):
                try:
                    threeDViewCount = int(layoutManager.threeDViewCount())
                except Exception:
                    threeDViewCount = 0
            radius = max(float(np.linalg.norm(extents)) * 0.5, 1.0)
            for viewIndex in range(threeDViewCount):
                try:
                    threeDView = layoutManager.threeDWidget(viewIndex).threeDView()
                    cameraNode = threeDView.cameraNode()
                    camera = cameraNode.GetCamera()
                    oldPosition = np.asarray(camera.GetPosition(), dtype=float)
                    oldFocalPoint = np.asarray(camera.GetFocalPoint(), dtype=float)
                    outward = oldPosition - oldFocalPoint
                    norm = float(np.linalg.norm(outward))
                    if norm <= 1e-6 or not math.isfinite(norm):
                        outward = np.asarray((0.0, -1.0, 0.0), dtype=float)
                    else:
                        outward /= norm
                    camera.SetFocalPoint(*center.tolist())
                    camera.SetPosition(
                        *(center + outward * max(radius * 3.8, 8.0)).tolist()
                    )
                    camera.SetParallelScale(max(paddedSpan * 0.5, 1.0))
                    camera.OrthogonalizeViewUp()
                    cameraNode.Modified()
                    threeDView.resetCameraClippingRange()
                    threeDView.forceRender()
                except Exception:
                    logging.debug(
                        "Could not fit workflow bounds in 3D view %d.",
                        viewIndex,
                    )
        return tuple(float(value) for value in center)

    def onFocusPlanningTarget(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            self.logic.validateTargetTooth(
                self._parameterNode.teethSegmentation,
                self._parameterNode.targetToothSegmentId,
            )
            self._applyWorkflowViewPreset("trajectory_only")
            self._enableCrossViewNavigation()
            self.onFramePlanningTarget()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onRestorePlanningView(self) -> None:
        self._restoreWorkflowViewState(updateUi=True)
        self._updatePlanning()

    def onFramePlanningTarget(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            bounds = self.logic.getTargetToothBoundsWorld(
                self._parameterNode.teethSegmentation,
                self._parameterNode.targetToothSegmentId,
            )
            self._frameRasBoundsInViews(bounds)
            self._presentSelectedTrajectory(
                self._parameterNode.trajectoryLine,
                centerSlices=True,
            )
            self._enableCrossViewNavigation()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def _presentSelectedTrajectory(
        self,
        trajectoryNode,
        *,
        centerSlices: bool = True,
    ) -> None:
        """Reveal the exact selected line and centre slices without changing geometry."""

        if not trajectoryNode or not self.logic:
            return
        displayNode = trajectoryNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(True)
            if hasattr(displayNode, "SetVisibility2D"):
                displayNode.SetVisibility2D(True)
            if hasattr(displayNode, "SetVisibility3D"):
                displayNode.SetVisibility3D(True)
            displayNode.SetPointLabelsVisibility(True)
            displayNode.SetPropertiesLabelVisibility(True)
            displayNode.SetSliceProjection(True)
            displayNode.SetSliceProjectionUseFiducialColor(True)
            displayNode.SetSliceProjectionOpacity(1.0)
        trajectoryNode.SetSelectable(True)
        try:
            summary = self.logic.getTrajectorySummary(trajectoryNode)
        except ValueError:
            return
        points = [
            np.asarray(point, dtype=float)
            for point in (summary["entryRas"], summary["targetRas"])
            if point is not None
        ]
        if not points:
            return
        center = np.mean(np.vstack(points), axis=0)
        if centerSlices:
            try:
                slicer.modules.markups.logic().JumpSlicesToLocation(
                    float(center[0]),
                    float(center[1]),
                    float(center[2]),
                    True,
                )
            except Exception:
                logging.debug("Could not centre slices on the selected trajectory.")

    def _restoreAssistedTrajectoryFocus(self, updateUi: bool = True) -> None:
        state = self._assistedTrajectoryFocusState
        self._assistedTrajectoryFocusState = None
        if state and self.logic:
            self.logic.restoreTargetToothFocus(state)
        if (
            updateUi
            and not self._isCleaningUp
            and hasattr(self, "ui")
            and self._reviewSegmentationNode
        ):
            self._syncSegmentationDisplayControls()
            self._updateAssistedTrajectoryControls()

    def onRestoreAssistedTrajectoryFocus(self) -> None:
        self._restoreAssistedTrajectoryFocus(updateUi=True)

    def onAssistedTrajectoryCountChanged(self, index: int) -> None:
        if self._updatingPlanningUI or not self._parameterNode:
            return
        value = self.ui.assistedTrajectoryCountComboBox.itemData(index)
        try:
            count = int(value)
        except (TypeError, ValueError):
            return
        if count not in (1, 2):
            return
        self._parameterNode.assistedTrajectoryCount = count
        self._updateAssistedTrajectoryControls()

    def onPlaceAssistedTrajectoryEntries(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            segmentationNode = self._parameterNode.teethSegmentation
            segmentId = self._parameterNode.targetToothSegmentId
            self.logic.validateTargetTooth(segmentationNode, segmentId)
            if self.logic.getSegmentationReviewState(segmentationNode) != "Reviewed":
                raise ValueError(
                    _("Mark the authoritative segmentation Reviewed first.")
                )
            if self.logic.dentobotTrajectoriesForTarget(
                segmentationNode, segmentId
            ):
                raise ValueError(
                    _(
                        "Delete the target tooth's existing trajectory set before "
                        "placing a new assisted set."
                    )
                )
            currentNode = self._parameterNode.assistedTrajectoryEntries
            if self.logic.isAssistedTrajectoryEntryNode(currentNode):
                currentSummary = self.logic.getAssistedTrajectoryEntrySummary(
                    currentNode
                )
                if currentSummary["definedPointCount"] and not slicer.util.confirmYesNoDisplay(
                    _(
                        "Replace the current assisted crown entry points? The "
                        "existing points will be removed."
                    ),
                    windowTitle=_("Replace assisted Step 4A entries"),
                ):
                    return
            entryNode, _summary = self.logic.createOrResetAssistedTrajectoryEntries(
                segmentationNode,
                segmentId,
                self._parameterNode.assistedTrajectoryCount,
                currentNode,
            )
            self._parameterNode.assistedTrajectoryEntries = entryNode
            self._bindAssistedTrajectoryEntryNode(entryNode)
            self._startAssistedTrajectoryFocus()
            self.logic.startAssistedTrajectoryEntryPlacement(entryNode)
            self._updateAssistedTrajectoryControls()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onGenerateAssistedTrajectories(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            self.logic.stopTrajectoryPlacement()
            trajectories, analysis = self.logic.generateAssistedTrajectories(
                self._parameterNode.assistedTrajectoryEntries,
                self._parameterNode.teethSegmentation,
                self._parameterNode.targetToothSegmentId,
                self._parameterNode.assistedTrajectoryCount,
                self._parameterNode.targetToothBoundsRoi,
            )
            self._parameterNode.trajectoryLine = trajectories[0]
            self._bindPlanningTrajectoryNode(trajectories[0])
            self._restoreAssistedTrajectoryFocus(updateUi=False)
            separation = analysis.get("rootSeparationMm")
            detail = (
                _(" Root-branch separation estimate: %1 mm.").replace(
                    "%1", f"{float(separation):.2f}"
                )
                if separation is not None
                else ""
            )
            slicer.util.infoDisplay(
                _(
                    "Created %1 unlocked assisted trajectory node(s).%2 These "
                    "targets come from complete-tooth surface geometry, not a "
                    "canal centreline. Verify and correct every Entry/Target in "
                    "the trajectory-aligned MPR before approval."
                ).replace("%1", str(len(trajectories))).replace("%2", detail),
                windowTitle=_("Assisted Step 4A trajectories"),
            )
            self._updatePlanning()
            self._updateTemplateModeling()
            self._updateTemplateGuide()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))
