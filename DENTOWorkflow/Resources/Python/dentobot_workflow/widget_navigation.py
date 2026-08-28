"""Extracted workflow navigation and stage locks methods; public APIs remain on ViewerWidgetMixin."""

from __future__ import annotations

from .runtime import *


class WorkflowNavigationWidgetMixin:
    def _workflowStageEntries(self) -> list[tuple[str, object]]:
        """Return the ordered clinical/research workflow sections.

        The section widgets remain the existing CTK collapsible buttons so the
        navigation layer does not duplicate controls or MRML state.
        """

        return [
            (_("Case"), self.ui.caseCollapsibleButton),
            (_("1 · CBCT Imaging"), self.ui.imagingCollapsibleButton),
            (_("2 · AI Segmentation"), self.ui.backendCollapsibleButton),
            (_("3 · Review and Correct"), self.ui.segmentationReviewCollapsibleButton),
            (_("4A · Trajectory Planning"), self.ui.planningCollapsibleButton),
            (_("4B · Support Teeth and Draft"), self.ui.templateModelingCollapsibleButton),
            (_("4C · Guide Rails and Docks"), self.ui.targetDockingCollapsibleButton),
            (_("5A · Visible Support Surface"), self.ui.templateModelingCollapsibleButton),
            (_("5B · Shell and Guide Fusion"), self.ui.templateGuideCollapsibleButton),
            (_("5C · Verify and Export"), self.ui.templateFinalizationCollapsibleButton),
            (_("6 · Robot Placement"), self.ui.robotPlacementCollapsibleButton),
        ]

    def _setupWorkflowNavigation(self) -> None:
        """Initialize the one-visible-stage wizard over the existing controls."""

        self._updatingWorkflowNavigationUI = True
        try:
            self.ui.workflowStageComboBox.clear()
            for stageIndex, (stageLabel, _section) in enumerate(
                self._workflowStageEntries()
            ):
                self.ui.workflowStageComboBox.addItem(stageLabel)
                self.ui.workflowStageComboBox.setItemData(
                    stageIndex,
                    _(
                        "Open this workflow stage for inspection or continuation. "
                        "Restored cases are not forced through a linear stage lock; "
                        "the stage's own actions still validate saved prerequisites."
                    ),
                    qt.Qt.ToolTipRole,
                )
            self.ui.workflowStageComboBox.enabled = True
            self.ui.workflowStageComboBox.currentIndex = 0
            entries = self._workflowStageEntries()
            for section in {entry[1] for entry in entries}:
                active = section is entries[0][1]
                section.visible = active
                section.collapsed = not active
            self.ui.assistedTrajectoryCollapsibleButton.collapsed = True
            self.ui.assistedTrajectoryCollapsibleButton.visible = False
        finally:
            self._updatingWorkflowNavigationUI = False

        self.ui.workflowStageComboBox.connect(
            "currentIndexChanged(int)",
            self.onWorkflowStageChanged,
        )
        self.ui.previousWorkflowStageButton.connect(
            "clicked(bool)",
            self.onPreviousWorkflowStage,
        )
        self.ui.nextWorkflowStageButton.connect(
            "clicked(bool)",
            self.onNextWorkflowStage,
        )
        self.ui.showGuidanceCheckBox.connect(
            "toggled(bool)",
            self.onShowGuidanceToggled,
        )
        self.ui.showBackendLogCheckBox.connect(
            "toggled(bool)",
            self.onShowBackendLogToggled,
        )
        self.ui.workflowViewPresetComboBox.connect(
            "currentIndexChanged(int)",
            self.onWorkflowViewPresetChanged,
        )
        self.ui.workflowViewElementsListWidget.connect(
            "itemChanged(QListWidgetItem*)",
            self.onWorkflowViewElementChanged,
        )
        self.ui.frameWorkflowViewButton.connect(
            "clicked(bool)",
            self.onFrameWorkflowView,
        )
        self.ui.restoreWorkflowViewButton.connect(
            "clicked(bool)",
            self.onRestoreWorkflowView,
        )
        connectedSections = set()
        for _index, (_stageLabel, section) in enumerate(self._workflowStageEntries()):
            if section in connectedSections:
                continue
            connectedSections.add(section)
            section.connect(
                "contentsCollapsed(bool)",
                lambda collapsed, activeSection=section: self._onWorkflowSectionCollapsed(
                    activeSection, collapsed
                ),
            )
        self._setGuidanceVisible(False)
        self._updateWorkflowNavigationButtons()
        self._setWorkflowViewAvailability(False)

    @staticmethod
    def _normalizedTrajectoryPlacementMode(mode: str) -> str:
        return "Assisted" if str(mode).strip() == "Assisted" else "Manual"

    def _trajectoryPlacementMode(self) -> str:
        if not self._parameterNode:
            return "Manual"
        return self._normalizedTrajectoryPlacementMode(
            self._parameterNode.trajectoryPlacementMode
        )

    def _updateTrajectoryPlacementModeControls(self) -> None:
        if not hasattr(self, "ui"):
            return
        mode = self._trajectoryPlacementMode()
        comboBox = self.ui.trajectoryPlacementModeComboBox
        self._updatingPlanningUI = True
        try:
            selectedIndex = comboBox.findData(mode)
            comboBox.currentIndex = max(int(selectedIndex), 0)
            manualVisible = mode == "Manual"
            for widget in (
                self.ui.createTrajectoryButton,
                self.ui.placeTrajectoryButton,
                self.ui.undoTrajectoryPointButton,
                self.ui.resetTrajectoryButton,
            ):
                widget.visible = manualVisible
            stageIndex = int(self.ui.workflowStageComboBox.currentIndex)
            assistedVisible = mode == "Assisted" and stageIndex == 4
            self.ui.assistedTrajectoryCollapsibleButton.visible = assistedVisible
            if assistedVisible:
                self.ui.assistedTrajectoryCollapsibleButton.collapsed = False
        finally:
            self._updatingPlanningUI = False

    def onTrajectoryPlacementModeChanged(self, index: int) -> None:
        if self._updatingPlanningUI or not self._parameterNode:
            return
        mode = self.ui.trajectoryPlacementModeComboBox.itemData(int(index))
        normalizedMode = self._normalizedTrajectoryPlacementMode(mode)
        if self._parameterNode.trajectoryPlacementMode != normalizedMode:
            self._parameterNode.trajectoryPlacementMode = normalizedMode
        self._updateTrajectoryPlacementModeControls()
        self._updatePlanning()

    def _guidanceWidgets(self) -> list[object]:
        widgetNames = (
            "introLabel",
            "dicomInstructionLabel",
            "backendDescriptionLabel",
            "runArtifactsExplanationLabel",
            "segmentationSafetyLabel",
            "segmentationReviewDescriptionLabel",
            "segmentationReviewSafetyLabel",
            "planningDescriptionLabel",
            "planningSafetyLabel",
            "assistedTrajectoryDescriptionLabel",
            "assistedTrajectorySafetyLabel",
            "targetDockingDescriptionLabel",
            "targetDockingSafetyLabel",
            "templateModelingDescriptionLabel",
            "templateModelingSafetyLabel",
            "templateGuideDescriptionLabel",
            "templateDockingFusionDescriptionLabel",
            "templateGuideSafetyLabel",
            "finalVerificationDescriptionLabel",
            "finalVerificationSafetyLabel",
        )
        return [
            getattr(self.ui, widgetName)
            for widgetName in widgetNames
            if hasattr(self.ui, widgetName)
        ]

    def _setGuidanceVisible(self, visible: bool) -> None:
        for widget in self._guidanceWidgets():
            widget.visible = bool(visible)

    def onShowGuidanceToggled(self, visible: bool) -> None:
        self._setGuidanceVisible(visible)

    def onShowBackendLogToggled(self, visible: bool) -> None:
        self.ui.backendLogTextEdit.visible = bool(visible)

    def _workflowOwnedMarkupStages(self) -> dict[object, int]:
        """Return editable-stage ownership for DENTOBOT markups only."""

        if not self._parameterNode:
            return {}
        stages: dict[object, int] = {}
        fieldStages = {
            "targetToothBoundsRoi": 4,
            "trajectoryLine": 4,
            "assistedTrajectoryEntries": 4,
            "targetDockingReferencePlane": 6,
            "templateSupportBoundaryCurve": 7,
            "templateSupportBoundaryPlane": 7,
            "templateInsertionDirection": 8,
            "templateShellRoi": 8,
            "templateTrimPlane": 9,
            "templateTrimCurve": 9,
            "draftJawLandmarks": 10,
            "draftJawGapLine": 10,
            "step6CaseJawLandmarks": 10,
            "step6CaseJawGapLine": 10,
            "step6OpenedTrajectoryLine": 10,
            "robotMountPlane": 10,
        }
        for fieldName, stage in fieldStages.items():
            node = getattr(self._parameterNode, fieldName, None)
            if node and node.IsA("vtkMRMLMarkupsNode"):
                stages[node] = stage
        roleStages = {
            "TemplateSupportBoundary": 7,
            "TemplateSupportBoundaryPlane": 7,
            "TargetDockingReferencePlane": 6,
            "TargetDockingMeasurement": 6,
            "TemplateShellTrimROI": 8,
            "RobotMountPlane": 10,
            "DraftJawLandmarks": 10,
            "DraftJawGapLine": 10,
            "Step6CaseJawLandmarks": 10,
            "Step6CaseJawGapLine": 10,
        }
        for node in slicer.util.getNodesByClass(
            "vtkMRMLDisplayableNode"
        ):
            if not node.IsA("vtkMRMLMarkupsNode"):
                continue
            if node.GetAttribute("DENTOBOT.TrajectoryRole"):
                stages[node] = 4
                continue
            if node.GetAttribute("DENTOBOT.BoundsRole"):
                stages[node] = 4
                continue
            role = node.GetAttribute("DENTOBOT.MarkupsRole") or ""
            if role in roleStages:
                stages[node] = roleStages[role]
        return stages

    def _step6OwnedMarkupMayInteract(self, node) -> bool:
        if not self._parameterNode or not self.logic:
            return False
        role = node.GetAttribute("DENTOBOT.MarkupsRole") or ""
        sceneKind = self._step6SceneKind()
        if role == self.logic.STEP6_CASE_JAW_LANDMARKS_ROLE:
            return bool(
                sceneKind == "case"
                and self.logic.step6CaseJawOpeningFreshnessIssues(
                    self._parameterNode
                )
            )
        if role == self.logic.DRAFT_JAW_LANDMARKS_ROLE:
            return bool(
                sceneKind == "phantom"
                and not self._parameterNode.draftJawTransform
            )
        if role == self.logic.ROBOT_MOUNT_PLANE_ROLE:
            return bool(
                self._step6RobotPresent()
                and not self._parameterNode.robotBaseMountLocked
                and not self.logic.isRos2MotionControlActive(
                    self._parameterNode.robotBaseTransform
                )
            )
        return False

    def _restoreStageExclusiveInteractionLocks(self) -> None:
        for nodeId, state in list(
            self._stageExclusiveInteractionPriorState.items()
        ):
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            if node:
                node.SetLocked(bool(state["locked"]))
                node.SetSelectable(bool(state["selectable"]))
        self._stageExclusiveInteractionPriorState.clear()

    def _updateStageExclusiveInteractionLocks(self, stageIndex: int) -> None:
        """Make non-owning workflow markups non-selectable and non-draggable."""

        if self._caseBundleRestoreDepth > 0:
            # Package lineage is validated against intrinsic MRML lock state.
            # Stage-exclusive locks are process-local interaction policy and
            # are reapplied only after the restore transaction completes.
            return
        ownedStages = self._workflowOwnedMarkupStages()
        restrictedIds = set()
        for node, ownerStage in ownedStages.items():
            allowInteraction = ownerStage == int(stageIndex)
            if allowInteraction and ownerStage == 10:
                allowInteraction = self._step6OwnedMarkupMayInteract(node)
            nodeId = node.GetID()
            if not nodeId:
                continue
            if allowInteraction:
                prior = self._stageExclusiveInteractionPriorState.pop(
                    nodeId,
                    None,
                )
                if prior:
                    node.SetLocked(bool(prior["locked"]))
                    node.SetSelectable(bool(prior["selectable"]))
                continue
            restrictedIds.add(nodeId)
            self._stageExclusiveInteractionPriorState.setdefault(
                nodeId,
                {
                    "locked": bool(node.GetLocked()),
                    "selectable": bool(node.GetSelectable()),
                },
            )
            node.SetLocked(True)
            node.SetSelectable(False)
        for nodeId in list(self._stageExclusiveInteractionPriorState):
            if nodeId in restrictedIds:
                continue
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            prior = self._stageExclusiveInteractionPriorState.pop(nodeId)
            if node:
                node.SetLocked(bool(prior["locked"]))
                node.SetSelectable(bool(prior["selectable"]))

    def _activateWorkflowViewStage(
        self,
        stageIndex: int,
        *,
        stageChanged: bool,
    ) -> None:
        active = bool(self._parameterNode and self.logic)
        self._workflowViewStageIndex = stageIndex
        if stageIndex == 4:
            try:
                self._enableCrossViewNavigation()
            except RuntimeError as exc:
                self.ui.crossViewNavigationStatusLabel.text = str(exc)
                self.ui.crossViewNavigationStatusLabel.styleSheet = (
                    "color: #b00020;"
                )
        else:
            self._restoreCrossViewNavigation(updateUi=False)
        self._updateWorkflowViewControls()
        if stageChanged:
            if self.ui.autoWorkflowViewCheckBox.checked:
                self._applyWorkflowViewPreset("recommended")
            else:
                self._workflowViewActivePresetKey = "custom"
                self._workflowViewVisibleKeys = {
                    entry["key"]
                    for entry in self._workflowViewEntriesByKey.values()
                    if self._workflowViewEntryCheckState(entry)
                    != qt.Qt.Unchecked
                }
                self.ui.workflowViewStatusLabel.text = _(
                    "Current scene visibility is unchanged; choose a quick "
                    "view or toggle individual elements."
                )
                self.ui.workflowViewStatusLabel.styleSheet = "color: #1f5f99;"
                self._updateWorkflowViewControls()

    def _refreshWorkflowViewAfterStateChange(self) -> None:
        """Keep an active display preset authoritative as MRML inputs change."""

        stageIndex = int(self.ui.workflowStageComboBox.currentIndex)
        self._updateWorkflowViewControls()
        if not self._workflowViewPriorState:
            return
        if self._workflowViewActivePresetKey == "custom":
            availableKeys = set(self._workflowViewEntriesByKey)
            visibleKeys = self._workflowViewVisibleKeys & availableKeys
            self._applyWorkflowViewKeys(
                visibleKeys,
                activePresetKey="custom",
                updateStatus=False,
            )
        elif self._workflowViewActivePresetKey:
            self._applyWorkflowViewPreset(
                self._workflowViewActivePresetKey,
                updateStatus=False,
            )

    def onWorkflowStageChanged(self, index: int) -> None:
        if self._updatingWorkflowNavigationUI:
            return
        self._setWorkflowStage(index)

    def onPreviousWorkflowStage(self, checked: bool = False) -> None:
        del checked
        self._setWorkflowStage(self.ui.workflowStageComboBox.currentIndex - 1)

    def onNextWorkflowStage(self, checked: bool = False) -> None:
        del checked
        self._setWorkflowStage(self.ui.workflowStageComboBox.currentIndex + 1)

    def _setWorkflowStage(self, index: int, ensureVisible: bool = True) -> None:
        entries = self._workflowStageEntries()
        if not entries:
            return
        index = max(0, min(int(index), len(entries) - 1))
        previousIndex = int(self.ui.workflowStageComboBox.currentIndex)
        stageChanged = index != previousIndex
        self._updatingWorkflowNavigationUI = True
        try:
            self.ui.workflowStageComboBox.currentIndex = index
            activeSection = entries[index][1]
            for section in {entry[1] for entry in entries}:
                isActive = section is activeSection
                section.visible = isActive
                section.collapsed = not isActive
            self._configureTemplateModelingStage(index)
            self._updateStageExclusiveInteractionLocks(index)
            self.ui.stepTitleLabel.text = entries[index][0].upper()
        finally:
            self._updatingWorkflowNavigationUI = False
        self._updateTrajectoryPlacementModeControls()
        self._updateWorkflowNavigationButtons()
        self._activateWorkflowViewStage(index, stageChanged=stageChanged)
        self._updateWorkflowNavigationRecommendation()
        if self._applicationShell and self._applicationShell.active:
            self._applicationShell.syncStage(
                index,
                self._recommendedWorkflowStageIndex(),
            )
        self._updateRobotKeyboardShortcutState()
        if index == len(entries) - 1:
            # ROS status nodes are intentionally lazy: entering Step 6 is the
            # lifecycle boundary that may create them.
            self._updateRos2MotionControlStatus()
        if ensureVisible:
            qt.QTimer.singleShot(
                0,
                lambda section=entries[index][1]: self._ensureWorkflowSectionVisible(
                    section
                ),
            )

    def _onWorkflowSectionCollapsed(self, section, collapsed: bool) -> None:
        if self._updatingWorkflowNavigationUI:
            return
        currentIndex = int(self.ui.workflowStageComboBox.currentIndex)
        if self._workflowStageEntries()[currentIndex][1] is not section or not collapsed:
            return
        # A wizard stage is not a free accordion. Keep the one active section
        # open so the task area can never become an empty stack of headers.
        self._updatingWorkflowNavigationUI = True
        try:
            section.collapsed = False
        finally:
            self._updatingWorkflowNavigationUI = False

    def _configureTemplateModelingStage(self, stageIndex: int) -> None:
        """Expose support selection in 4B and surface refinement in 5A."""

        if not hasattr(self, "ui"):
            return
        selectionStage = stageIndex == 5
        surfaceStage = stageIndex == 7
        if not (selectionStage or surfaceStage):
            return
        self.ui.templateModelingCollapsibleButton.text = (
            _("Step 4B — Select Support Teeth and Build Anatomy Draft")
            if selectionStage
            else _("Step 5A — Define the Visible Support Surface")
        )
        self.ui.templateModelingDescriptionLabel.text = (
            _(
                "Select same-jaw support teeth and create the complete, world-RAS "
                "anatomy draft used by Step 4C collision screening. Source masks "
                "are never modified."
            )
            if selectionStage
            else _(
                "Refine the already selected support anatomy to the clinically "
                "visible erupted contact surface using the automatic plane or an "
                "editable boundary."
            )
        )
        selectionWidgets = (
            self.ui.templateTargetToothTitleLabel,
            self.ui.templateTargetToothValueLabel,
            self._templateSupportArchWidget,
            self.ui.draftTemplateSupportModelTitleLabel,
            self.ui.draftTemplateSupportModelSelector,
            self.ui.reviewSegmentationForTemplateButton,
            self.ui.createDraftTemplateSupportModelButton,
            self.ui.deleteDraftTemplateSupportModelButton,
        )
        surfaceWidgets = (
            self.ui.templateSupportBoundaryCurveLabel,
            self.ui.templateSupportBoundaryCurveSelector,
            self.ui.templateSupportSelectionModeLabel,
            self.ui.templateSupportDirectionValueLabel,
            self.ui.flipTemplateSupportDirectionButton,
            self.ui.templateSupportCurveSamplingSpacingLabel,
            self.ui.templateSupportCurveSamplingSpacingSpinBox,
            self.ui.templateTerminalSupportCoverageLabel,
            self.ui.templateTerminalSupportCoverageSpinBox,
            self.ui.visibleTemplateSupportModelLabel,
            self.ui.visibleTemplateSupportModelSelector,
            self.ui.templateSupportBoundaryPlaneLabel,
            self.ui.templateSupportBoundaryPlaneSelector,
            self.ui.templateSupportPlaneDepthLabel,
            self.ui.templateSupportPlaneDepthSpinBox,
            self.ui.templateSupportCrownCapLabel,
            self.ui.templateSupportCrownCapSpinBox,
            self.ui.createTemplateSupportPlaneButton,
            self.ui.generateTemplateSupportBoundaryFromPlaneButton,
            self.ui.createTemplateSupportBoundaryButton,
            self.ui.generateVisibleTemplateSupportModelButton,
            self.ui.deleteTemplateSupportSelectionButton,
            self.ui.templateSupportSurfaceStatusLabel,
        )
        for widget in selectionWidgets:
            widget.visible = selectionStage
        # This hidden QListWidget is only the persistent adapter behind the
        # Step 4B arch map. It has been removed from the form layout and must
        # remain hidden in every stage.
        self.ui.templateSupportTeethListWidget.visible = False
        self.ui.templateSupportTeethTitleLabel.visible = False
        self._templateSupportPackageWidget.visible = surfaceStage
        for widget in surfaceWidgets:
            if widget:
                widget.visible = surfaceStage
        self.ui.templateSupportViewControlsGroupBox.visible = True

    def onReturnToStep4BSupportSelection(self, checked: bool = False) -> None:
        """Navigate from the Step 5A consumer view to the Step 4B owner."""

        del checked
        self._setWorkflowStage(5)

    def _ensureWorkflowSectionVisible(self, section) -> None:
        if not self._workflowContentScrollArea:
            return
        self._workflowContentScrollArea.ensureWidgetVisible(section, 0, 0)
        scrollBar = self._workflowContentScrollArea.verticalScrollBar()
        scrollBar.setValue(max(0, int(section.y) - 4))

    def _updateWorkflowNavigationButtons(self) -> None:
        count = len(self._workflowStageEntries())
        index = int(self.ui.workflowStageComboBox.currentIndex)
        self.ui.previousWorkflowStageButton.enabled = index > 0
        self.ui.nextWorkflowStageButton.enabled = 0 <= index < count - 1

    def _recommendedWorkflowStageIndex(self) -> int:
        if not self._parameterNode:
            return 0
        if not self._parameterNode.inputVolume:
            # A brand-new empty scene must open on the Case stage so the
            # operator can deliberately create a de-identified case or open a
            # saved scene. Once a case label exists, imaging is the next
            # recommendation, but the navigator never skips Case at first
            # initialization merely because no volume is loaded yet.
            return 1 if self._parameterNode.caseName.strip() else 0
        segmentationNode = self._parameterNode.teethSegmentation
        if not segmentationNode:
            return 2
        if self.logic.getSegmentationReviewState(segmentationNode) != "Reviewed":
            return 3
        trajectoryNode = self._parameterNode.trajectoryLine
        if not trajectoryNode or trajectoryNode.GetNumberOfDefinedControlPoints() < 2:
            return 4
        if not trajectoryNode.GetLocked():
            return 4
        supportModel = self._parameterNode.draftTemplateSupportModel
        if (
            not supportModel
            or supportModel.GetAttribute("DENTOBOT.GeometryState") != "Current"
        ):
            return 5
        dockingModel = self._parameterNode.targetDockingAssemblyModel
        if (
            not dockingModel
            or dockingModel.GetAttribute("DENTOBOT.GeometryState") != "Current"
            or dockingModel.GetAttribute("DENTOBOT.OrientationState") != "Confirmed"
        ):
            return 6
        if not self._parameterNode.visibleTemplateSupportModel:
            return 7
        if not self._parameterNode.finalPrintableTemplateModel:
            return 8
        return 9

    def _updateWorkflowNavigationRecommendation(self) -> None:
        recommendedIndex = self._recommendedWorkflowStageIndex()
        entries = self._workflowStageEntries()
        recommendation = _("Recommended next: %1").replace(
            "%1",
            entries[recommendedIndex][0],
        )
        self.ui.workflowStageStatusLabel.text = "●"
        self.ui.workflowStageStatusLabel.toolTip = recommendation
        self.ui.workflowStageStatusLabel.accessibleName = recommendation
        currentIndex = int(self.ui.workflowStageComboBox.currentIndex)
        indicatorColor = "#207227" if currentIndex == recommendedIndex else "#1f5f99"
        self.ui.workflowStageStatusLabel.styleSheet = (
            f"color: {indicatorColor}; font-size: 15px;"
        )
        self.ui.workflowStageComboBox.toolTip = _(
            "Open any workflow stage for inspection or continuation; saved "
            "prerequisites gate actions, not navigation. %1"
        ).replace("%1", recommendation)
        if not self._workflowNavigationInitializedFromScene:
            self._workflowNavigationInitializedFromScene = True
            self._setWorkflowStage(recommendedIndex, ensureVisible=False)
        elif self._applicationShell and self._applicationShell.active:
            self._applicationShell.syncStage(currentIndex, recommendedIndex)
