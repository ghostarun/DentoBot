"""Extracted workflow navigation and stage locks methods; public APIs remain on ViewerWidgetMixin."""

from __future__ import annotations

from .runtime import *


class WorkflowNavigationWidgetMixin:
    def _workflowStageEntries(self) -> list[tuple[str, object]]:
        """Return the ordered clinical/research workflow sections.

        The section widgets remain the existing CTK collapsible buttons so the
        navigation layer does not duplicate controls or MRML state.
        """

        entries = [
            (_("0 · Case"), self.ui.caseCollapsibleButton),
            (_("1 · Scan"), self.ui.imagingCollapsibleButton),
            (
                _("2 · Segmentation and Review"),
                self._segmentationReviewStageGroup
                or self.ui.segmentationReviewCollapsibleButton,
            ),
            (
                _("3 · Case Foundation (3A Open Mouth / 3B Robot Placement)"),
                self.ui.step6CaseJawOpeningGroupBox,
            ),
            (_("4A · Trajectory Planning"), self.ui.planningCollapsibleButton),
            (_("4B · Support Teeth and Draft"), self.ui.templateModelingCollapsibleButton),
            (_("4C · Guide Rails and Docks"), self.ui.targetDockingCollapsibleButton),
            (_("5A · Visible Support Surface"), self.ui.templateModelingCollapsibleButton),
            (_("5B · Shell and Guide Fusion"), self.ui.templateGuideCollapsibleButton),
            (_("5C · Verify and Export"), self.ui.templateFinalizationCollapsibleButton),
            (_("6 · Robot Placement"), self.ui.robotPlacementCollapsibleButton),
        ]
        if not step6_enabled():
            return entries[:-1]
        return entries

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
            self.ui.step6CaseJawOpeningGroupBox.visible = False
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
            "step6CaseJawLandmarks": 3,
            "step6CaseJawGapLine": 3,
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
            "Step6CaseJawLandmarks": 3,
            "Step6CaseJawGapLine": 3,
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
            if (
                allowInteraction
                and 4 <= ownerStage <= 9
                and self.logic
                and node.GetAttribute("DENTOBOT.MarkupsRole")
                != self.logic.STEP6_CASE_JAW_LANDMARKS_ROLE
                and not self.logic.evaluateCaseFoundationEligibility(
                    self._parameterNode
                )["pose"]["eligible"]
            ):
                allowInteraction = False
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
        if stageIndex <= 2:
            self._displayInspectionContext()
            return
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
        if stageIndex <= 2:
            self._displayInspectionContext()
            return
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
        if self._isOfflinePlacementSurfaceActive():
            self._ensureOfflinePlacementSceneVisible()

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

    def _isStep3BActive(self) -> bool:
        return bool(
            hasattr(self, "ui")
            and int(self.ui.workflowStageComboBox.currentIndex) == 3
            and int(getattr(self, "_step3SubstepIndex", 0)) == 1
            and step6_enabled()
        )

    def _isStep61Active(self) -> bool:
        if not hasattr(self, "ui"):
            return False
        entries = self._workflowStageEntries()
        return bool(
            entries
            and int(self.ui.workflowStageComboBox.currentIndex) == len(entries) - 1
            and int(getattr(self, "_step6SubstepIndex", 0)) == 1
        )

    def _isOfflinePlacementSurfaceActive(self) -> bool:
        return self._isStep3BActive() or self._isStep61Active()

    def _setupStep3SubstepNavigator(self) -> None:
        """Add 3A/3B navigator on the existing Case Foundation stage."""

        if self._step3SubstepNavigator is not None or not step6_enabled():
            return
        if not hasattr(self, "ui") or not hasattr(self.ui, "step6CaseJawOpeningGroupBox"):
            return
        parent = self.ui.step6CaseJawOpeningGroupBox
        layout = self.ui.step6CaseJawOpeningVerticalLayout
        navigator = qt.QGroupBox(
            _("Step 3 workflow — open mouth then offline robot placement"),
            parent,
        )
        navigator.objectName = "DENTOBOTStep3SubstepNavigator"
        navigatorLayout = qt.QGridLayout(navigator)
        navigatorLayout.setContentsMargins(8, 7, 8, 7)
        navigatorLayout.setHorizontalSpacing(6)
        previousButton = qt.QPushButton(_("‹ Back"), navigator)
        previousButton.objectName = "DENTOBOTStep3PreviousSubstepButton"
        comboBox = qt.QComboBox(navigator)
        comboBox.objectName = "DENTOBOTStep3SubstepComboBox"
        comboBox.addItem(_("3A — Open Mouth Setup"))
        comboBox.addItem(_("3B — Offline Robot Placement"))
        nextButton = qt.QPushButton(_("Next ›"), navigator)
        nextButton.objectName = "DENTOBOTStep3NextSubstepButton"
        hint = qt.QLabel(
            _(
                "3A commits the Case Foundation opening. 3B uses the same "
                "offline robot, virtual forehead, and Manual Simulation Base "
                "as Step 6.1 — one MRML allocation, not a second robot."
            ),
            navigator,
        )
        hint.wordWrap = True
        hint.styleSheet = "color: #5f6368;"
        navigatorLayout.addWidget(previousButton, 0, 0)
        navigatorLayout.addWidget(comboBox, 0, 1)
        navigatorLayout.addWidget(nextButton, 0, 2)
        navigatorLayout.addWidget(hint, 1, 0, 1, 3)
        navigatorLayout.setColumnStretch(1, 1)

        host = qt.QWidget(parent)
        host.objectName = "DENTOBOTStep3BPlacementHost"
        hostLayout = qt.QVBoxLayout(host)
        hostLayout.setContentsMargins(0, 0, 0, 0)
        hostLayout.setSpacing(4)
        continueButton = qt.QPushButton(
            _("Confirm placement and continue to Step 4A"),
            host,
        )
        continueButton.objectName = "DENTOBOTStep3BContinueToStep4Button"
        continueButton.toolTip = _(
            "Open Step 4A. Restored cases may skip 3B; Step 6.1 reports PASS "
            "only after virtual-forehead auto-placement on this surface."
        )
        hostLayout.addWidget(continueButton)
        host.visible = False

        # Keep the Designer 3A form/button layouts in place. Re-parenting those
        # nested layouts into a wrapper collapses the AUTO/confirm controls.
        layout.insertWidget(0, navigator)
        layout.addWidget(host)
        comboBox.connect("currentIndexChanged(int)", self._onStep3SubstepChanged)
        previousButton.connect("clicked(bool)", self._onPreviousStep3Substep)
        nextButton.connect("clicked(bool)", self._onNextStep3Substep)
        continueButton.connect("clicked(bool)", self.onStep3BGoToStep4)
        self._step3SubstepNavigator = navigator
        self._step3SubstepComboBox = comboBox
        self._step3PreviousSubstepButton = previousButton
        self._step3NextSubstepButton = nextButton
        self._step3AContentWidget = None
        self._step3BPlacementHost = host
        self._step3BContinueButton = continueButton
        stage_index = 3
        try:
            stage_index = int(self.ui.workflowStageComboBox.currentIndex)
        except (AttributeError, TypeError, ValueError):
            stage_index = 3
        initial = (
            self._recommendedStep3SubstepIndex()
            if stage_index == 3
            else 0
        )
        self._configureStep3Substep(initial)

    def _onStep3SubstepChanged(self, substep_index: int) -> None:
        if self._updatingStep3SubstepNavigation:
            return
        self._configureStep3Substep(substep_index)

    def _onPreviousStep3Substep(self, checked: bool = False) -> None:
        del checked
        self._configureStep3Substep(int(self._step3SubstepIndex) - 1)

    def _onNextStep3Substep(self, checked: bool = False) -> None:
        del checked
        self._configureStep3Substep(int(self._step3SubstepIndex) + 1)

    def _configureStep3Substep(self, substep_index: int) -> None:
        if self._step3SubstepNavigator is None:
            return
        index = max(0, min(int(substep_index), 1))
        self._step3SubstepIndex = index
        self._updatingStep3SubstepNavigation = True
        try:
            if self._step3SubstepComboBox is not None:
                self._step3SubstepComboBox.currentIndex = index
            if self._step3PreviousSubstepButton is not None:
                self._step3PreviousSubstepButton.enabled = index > 0
            if self._step3NextSubstepButton is not None:
                self._step3NextSubstepButton.enabled = index < 1
        finally:
            self._updatingStep3SubstepNavigation = False
        if self._step3BPlacementHost is not None:
            self._step3BPlacementHost.visible = index == 1
        self._setStep3AOriginalWidgetsVisible(index == 0)
        self.ui.step6CaseJawOpeningGroupBox.text = (
            _("3B — Offline Robot Placement")
            if index == 1
            else _("Case Foundation — Open Mouth Setup (required before Step 4A)")
        )
        self._syncOfflinePlacementHost()
        self._updateRobotKeyboardShortcutState()
        if index == 1:
            self._updateOfflinePlacementMirrorStatus()
            self._updateRobotPlacement()
            self._applyStep3BRecommendedView()
        elif self.ui.autoWorkflowViewCheckBox.checked:
            self._applyWorkflowViewPreset("recommended", updateStatus=False)

    def _setStep3AOriginalWidgetsVisible(self, visible: bool) -> None:
        if not hasattr(self, "ui"):
            return
        skip = {
            widget
            for widget in (
                self._step3SubstepNavigator,
                self._step3BPlacementHost,
            )
            if widget is not None
        }
        self._setLayoutTreeVisible(
            self.ui.step6CaseJawOpeningVerticalLayout,
            visible,
            skip,
        )

    def _setLayoutTreeVisible(self, layout, visible: bool, skip: set) -> None:
        if layout is None:
            return
        for index in range(self._qtLayoutCount(layout)):
            item = layout.itemAt(index)
            if item is None:
                continue
            widget = item.widget() if hasattr(item, "widget") else None
            nested = item.layout() if hasattr(item, "layout") else None
            if widget is not None:
                if widget in skip:
                    continue
                widget.visible = bool(visible)
            elif nested is not None:
                self._setLayoutTreeVisible(nested, visible, skip)

    def _applyStep3BRecommendedView(self) -> None:
        if not self._isStep3BActive():
            return
        self._applyWorkflowViewPreset("recommended", updateStatus=False)
        self._updateWorkflowViewControls()
        self._ensureOfflinePlacementSceneVisible()

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
            self.ui.step6CaseJawOpeningGroupBox.visible = index == 3
            self._configureTemplateModelingStage(index)
            self._updateStageExclusiveInteractionLocks(index)
            self.ui.stepTitleLabel.text = entries[index][0].upper()
        finally:
            self._updatingWorkflowNavigationUI = False
        self._updateTrajectoryPlacementModeControls()
        self._updateWorkflowNavigationButtons()
        self._activateWorkflowViewStage(index, stageChanged=stageChanged)
        self._syncScanContext()
        if index <= 2:
            self._displayInspectionContext()
        elif index == 3:
            self._maybeAutoCommitInspectionForCaseFoundation()
            self._updateStep6CaseJawOpeningControls()
            if self._step3SubstepNavigator is not None:
                if not self._workflowNavigationInitializedFromScene:
                    self._configureStep3Substep(self._recommendedStep3SubstepIndex())
                else:
                    self._configureStep3Substep(self._step3SubstepIndex)
        self._syncOfflinePlacementHost()
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
        if not self._parameterNode.inputVolume and not self._parameterNode.inspectedVolume:
            # A brand-new empty scene must open on the Case stage so the
            # operator can deliberately create a de-identified case or open a
            # saved scene. Once a case label exists, imaging is the next
            # recommendation, but the navigator never skips Case at first
            # initialization merely because no volume is loaded yet.
            return 1 if self._parameterNode.caseName.strip() else 0
        segmentationNode = self._parameterNode.teethSegmentation or self._parameterNode.inspectedSegmentation
        if not segmentationNode:
            return 2
        if self.logic.getSegmentationReviewState(segmentationNode) != "Reviewed":
            return 2
        if not self.logic.evaluateCaseFoundationEligibility(
            self._parameterNode
        )["pose"]["eligible"]:
            # The Case Foundation section is the dedicated stage 3.
            return 3
        if step6_enabled() and not self._offlinePlacementIsPresent():
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
        if getattr(self, "_pendingFreshCaseReset", False):
            return
        if not self._workflowNavigationInitializedFromScene:
            self._workflowNavigationInitializedFromScene = True
            self._setWorkflowStage(recommendedIndex, ensureVisible=False)
        elif self._applicationShell and self._applicationShell.active:
            self._applicationShell.syncStage(currentIndex, recommendedIndex)

    def _recommendedStep3SubstepIndex(self) -> int:
        if not self._parameterNode or not self.logic or not step6_enabled():
            return 0
        pose = self.logic.evaluateCaseFoundationEligibility(self._parameterNode)["pose"]
        if not pose.get("eligible"):
            return 0
        if not self._offlinePlacementIsPresent():
            return 1
        return 0

    def _offlinePlacementIsPresent(self) -> bool:
        if not self._parameterNode or not self.logic:
            return False
        try:
            state = str(
                self.logic.offlinePlacementMirrorState(self._parameterNode).get("state")
                or ""
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False
        return state in {"pass", "manual"}
