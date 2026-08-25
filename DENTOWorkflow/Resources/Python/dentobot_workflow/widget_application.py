"""Extracted application shell lifecycle methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from .runtime import *


class ApplicationWidgetMixin:
    def _setupApplicationShell(self) -> None:
        """Install the opt-in six-workspace shell without duplicating controls."""
        if self._applicationShell is not None:
            return
        self._setupRobotSimulationShellPanel()
        self._guiModeButton = qt.QPushButton(
            _("Try New GUI"),
            self.ui.workflowNavigationGroupBox,
        )
        self._guiModeButton.objectName = "switchDENTOBOTGuiModeButton"
        self._guiModeButton.toolTip = _(
            "Switch between the current eleven-stage module and the new "
            "six-workspace DENTOBOT application shell. MRML and backend state "
            "are shared; no case data is copied."
        )
        self.ui.workflowNavigationLayout.addWidget(
            self._guiModeButton,
            3,
            0,
            1,
            4,
        )
        self._guiModeButton.connect(
            "clicked(bool)",
            self.onToggleDENTOBOTGuiMode,
        )
        self._applicationShell = DENTOApplicationShell(
            main_window=slicer.util.mainWindow(),
            module_layout=self.layout,
            workflow_widget=self._uiWidget,
            ui=self.ui,
            set_stage=lambda index: self._setWorkflowStage(index),
            resource_path=self.resourcePath,
            on_mode_requested=self._applyDENTOBOTGuiMode,
            on_substep_selected=self._onApplicationShellSubstepSelected,
            on_view_controls_requested=self.onOpenViewControlsPalette,
        )
        self._applyDENTOBOTGuiMode(
            DENTOApplicationShell.storedGuiMode(),
            persist=False,
        )

    def onToggleDENTOBOTGuiMode(self, checked: bool = False) -> None:
        del checked
        if not self._applicationShell:
            return
        target = (
            GUI_MODE_LEGACY
            if self._applicationShell.active
            else GUI_MODE_SHELL
        )
        self._applyDENTOBOTGuiMode(target)

    def _applyDENTOBOTGuiMode(
        self,
        mode: str,
        *,
        persist: bool = True,
    ) -> None:
        if not self._applicationShell:
            return
        mode = GUI_MODE_SHELL if mode == GUI_MODE_SHELL else GUI_MODE_LEGACY
        if persist:
            DENTOApplicationShell.storeGuiMode(mode)
        if mode == GUI_MODE_SHELL:
            try:
                stage_index = int(self.ui.workflowStageComboBox.currentIndex)
                recommended = self._recommendedWorkflowStageIndex()
                self._applicationShell.activate(stage_index, recommended)
                self._applicationShell.updateCaseAndRuntime(
                    self._parameterNode.caseName if self._parameterNode else "",
                )
                self._guiModeButton.text = _("New GUI Active")
            except RuntimeError as exc:
                DENTOApplicationShell.storeGuiMode(GUI_MODE_LEGACY)
                self._applicationShell.deactivate()
                self._guiModeButton.text = _("Try New GUI")
                slicer.util.errorDisplay(str(exc))
        else:
            self._applicationShell.deactivate()
            self._restoreLegacyRobotSimulationGroups()
            self._guiModeButton.text = _("Try New GUI")

    def onReloadDENTOWorkflowModule(self, checked: bool = False) -> None:
        """Reload DENTOBOT Python sources while preserving Slicer and ROS."""

        del checked
        button = self.ui.reloadDENTOWorkflowButton
        button.enabled = False
        button.text = _("Reloading DENTOBOT module…")
        try:
            if find_ros2_robot_by_name(ROS2_ROBOT_NAME) is not None:
                ok, message = disconnect_dentobot_motion_control(
                    self.logic.robotModelNodes() if self.logic else [],
                )
                if not ok:
                    raise RuntimeError(message)
            shutdown_slicer_adapter()
            slicer.util.mainWindow().statusBar().showMessage(
                _("Reloading DENTOBOT Python sources; MRML scene and ROS stack remain."),
            )
            qt.QTimer.singleShot(0, self._reloadDENTOWorkflowSources)
        except Exception as exc:
            button.enabled = True
            button.text = _("Reload DENTOBOT Module (Developer)")
            logging.exception("DENTOBOT module reload preflight failed")
            slicer.util.errorDisplay(
                _("DENTOBOT reload failed before module replacement: %1").replace(
                    "%1", str(exc)
                )
            )

    @staticmethod
    def _reloadDENTOWorkflowSources() -> None:
        """Evict helper modules, then use Slicer's supported scripted reload."""

        try:
            helper_module_names = sorted(
                path.stem for path in _helperDirectory.glob("DENTO*.py")
            )
            for module_name in helper_module_names:
                sys.modules.pop(module_name, None)
            internal_module_names = sorted(
                (
                    module_name
                    for module_name in sys.modules
                    if module_name == "dentobot_workflow"
                    or module_name.startswith("dentobot_workflow.")
                ),
                key=lambda module_name: (module_name.count("."), module_name),
                reverse=True,
            )
            for module_name in internal_module_names:
                sys.modules.pop(module_name, None)
            slicer.util.reloadScriptedModule("DENTOWorkflow")
            slicer.util.mainWindow().statusBar().showMessage(
                _("DENTOBOT module reloaded. Reconnect the ROS robot if required."),
                5000,
            )
        except Exception as exc:
            logging.exception("DENTOBOT scripted module reload failed")
            slicer.util.errorDisplay(
                _("DENTOBOT module reload failed: %1").replace("%1", str(exc))
            )

    @staticmethod
    def _qtLayoutCount(layout) -> int:
        count = getattr(layout, "count", 0)
        return int(count() if callable(count) else count)

    @classmethod
    def _detachNestedLayout(cls, parentLayout, nestedLayout) -> None:
        """Remove one child layout while preserving all of its widgets."""

        for index in range(cls._qtLayoutCount(parentLayout)):
            item = parentLayout.itemAt(index)
            itemLayout = item.layout() if item and hasattr(item, "layout") else None
            if itemLayout is nestedLayout:
                parentLayout.takeAt(index)
                return

    def _setupPersistentWorkflowShell(self, uiWidget) -> None:
        """Build a compact fixed header and a reusable floating view palette."""

        rootLayout = self.ui.verticalLayout
        rootLayout.setSpacing(4)

        # The stage selector and the most frequent viewport actions stay fixed
        # above the independently scrolling active stage. Reuse the Designer
        # widgets so every existing signal and display-state binding remains
        # authoritative.
        navigationLayout = self.ui.workflowNavigationLayout
        while self._qtLayoutCount(navigationLayout):
            navigationLayout.takeAt(0)
        navigationLayout.setContentsMargins(4, 4, 4, 4)
        navigationLayout.setHorizontalSpacing(4)
        navigationLayout.setVerticalSpacing(4)
        self.ui.workflowNavigationGroupBox.title = ""
        self.ui.workflowNavigationGroupBox.toolTip = _(
            "Select one active workflow stage. The active stage is the only "
            "stage shown in the task area below."
        )

        self.ui.previousWorkflowStageButton.text = "‹"
        self.ui.previousWorkflowStageButton.toolTip = _("Previous workflow stage")
        self.ui.previousWorkflowStageButton.setFixedWidth(30)
        self.ui.nextWorkflowStageButton.text = "›"
        self.ui.nextWorkflowStageButton.toolTip = _("Next workflow stage")
        self.ui.nextWorkflowStageButton.setFixedWidth(30)
        self.ui.workflowStageStatusLabel.text = "●"
        self.ui.workflowStageStatusLabel.wordWrap = False
        self.ui.workflowStageStatusLabel.alignment = (
            qt.Qt.AlignCenter | qt.Qt.AlignVCenter
        )
        self.ui.workflowStageStatusLabel.setFixedWidth(18)
        self.ui.workflowStageStatusLabel.toolTip = _(
            "The recommended next stage is not available yet."
        )

        navigationLayout.addWidget(self.ui.previousWorkflowStageButton, 0, 0)
        navigationLayout.addWidget(self.ui.workflowStageComboBox, 0, 1)
        navigationLayout.addWidget(self.ui.workflowStageStatusLabel, 0, 2)
        navigationLayout.addWidget(self.ui.nextWorkflowStageButton, 0, 3)
        navigationLayout.setColumnStretch(1, 1)

        self.ui.workflowViewPresetFormLayout.removeWidget(
            self.ui.workflowViewPresetComboBox
        )
        self.ui.workflowViewPresetLabel.visible = False
        self.ui.workflowViewPresetComboBox.toolTip = _(
            "Apply a stage-aware visibility preset. Detailed element controls "
            "are available in View Controls."
        )
        self.ui.workflowViewPresetComboBox.setSizePolicy(
            qt.QSizePolicy.Expanding,
            qt.QSizePolicy.Fixed,
        )
        self._viewControlsButton = qt.QPushButton(
            _("View…"),
            self.ui.workflowNavigationGroupBox,
        )
        self._viewControlsButton.objectName = "openViewControlsPaletteButton"
        self._viewControlsButton.toolTip = _(
            "Open the movable Elements and Display control palette."
        )
        self._viewControlsButton.setFixedWidth(50)
        self.ui.frameWorkflowViewButton.text = _("Frame")
        self.ui.frameWorkflowViewButton.setFixedWidth(50)
        self.ui.restoreWorkflowViewButton.text = _("Restore")
        self.ui.restoreWorkflowViewButton.setFixedWidth(58)
        self._guidanceToolButton = qt.QToolButton(
            self.ui.workflowNavigationGroupBox
        )
        self._guidanceToolButton.objectName = "workflowGuidanceToolButton"
        self._guidanceToolButton.text = "?"
        self._guidanceToolButton.checkable = True
        self._guidanceToolButton.checked = bool(
            self.ui.showGuidanceCheckBox.checked
        )
        self._guidanceToolButton.toolTip = _(
            "Show or hide detailed workflow guidance and safety notes."
        )
        self._guidanceToolButton.setFixedWidth(26)

        quickActionsWidget = qt.QWidget(self.ui.workflowNavigationGroupBox)
        quickActionsWidget.objectName = "compactWorkflowViewActionsWidget"
        quickActionsLayout = qt.QHBoxLayout(quickActionsWidget)
        quickActionsLayout.setContentsMargins(0, 0, 0, 0)
        quickActionsLayout.setSpacing(4)
        quickActionsLayout.addWidget(self.ui.workflowViewPresetComboBox, 1)
        quickActionsLayout.addWidget(self._viewControlsButton)
        quickActionsLayout.addWidget(self.ui.frameWorkflowViewButton)
        quickActionsLayout.addWidget(self.ui.restoreWorkflowViewButton)
        quickActionsLayout.addWidget(self._guidanceToolButton)
        navigationLayout.addWidget(quickActionsWidget, 1, 0, 1, 6)
        self.ui.showGuidanceCheckBox.visible = False
        self.ui.reloadDENTOWorkflowButton.text = _("Reload Module (Dev)")
        self.ui.reloadDENTOWorkflowButton.toolTip = _(
            "Reload DENTOWorkflow.py and all DENTO helper Python modules from "
            "repository source without restarting Slicer or the container. "
            "The MRML scene and external ROS stack remain; active backend work "
            "is cancelled and the SlicerROS2 robot is disconnected first."
        )
        self.ui.reloadDENTOWorkflowButton.styleSheet = "font-size: 10px;"
        navigationLayout.addWidget(
            self.ui.reloadDENTOWorkflowButton,
            2,
            0,
            1,
            4,
        )
        self.ui.stepTitleLabel.visible = False
        self.ui.researchStatusLabel.setMaximumHeight(18)
        self.ui.researchStatusLabel.styleSheet = (
            "font-size: 10px; font-weight: 600; color: #b36b00;"
        )

        # Selected volume details belong to the CBCT stage, not to the fixed
        # application chrome.
        rootLayout.removeWidget(self.ui.metadataGroupBox)
        self.ui.imagingVerticalLayout.addWidget(self.ui.metadataGroupBox)

        # Build a nonmodal tool palette and move the existing viewport widgets
        # into it. Reparenting avoids duplicate state, callbacks, and MRML
        # contracts.
        palette = qt.QDialog(slicer.util.mainWindow())
        palette.objectName = "DENTOWorkflowViewControlsPalette"
        palette.windowTitle = _("DENTOBOT View Controls")
        palette.modal = False
        palette.setWindowFlags(
            qt.Qt.Tool | qt.Qt.WindowTitleHint | qt.Qt.WindowCloseButtonHint
        )
        palette.setAttribute(qt.Qt.WA_DeleteOnClose, False)
        paletteLayout = qt.QVBoxLayout(palette)
        paletteLayout.setContentsMargins(6, 6, 6, 6)
        paletteLayout.setSpacing(4)
        tabs = qt.QTabWidget(palette)
        tabs.objectName = "viewControlsTabWidget"
        paletteLayout.addWidget(tabs)

        elementsPage = qt.QWidget(tabs)
        elementsPage.objectName = "viewControlsElementsPage"
        elementsLayout = qt.QVBoxLayout(elementsPage)
        elementsLayout.setContentsMargins(8, 8, 8, 8)
        elementsLayout.setSpacing(8)

        stageLabel = qt.QLabel(elementsPage)
        stageLabel.objectName = "workflowViewStageLabel"
        stageLabel.wordWrap = True
        stageLabel.styleSheet = "font-weight: 600; color: #1f5f99;"
        elementsLayout.addWidget(stageLabel)
        recommendedButton = qt.QPushButton(
            _("Apply Recommended View for This Step"),
            elementsPage,
        )
        recommendedButton.objectName = "applyRecommendedWorkflowViewButton"
        recommendedButton.toolTip = _(
            "Show only the anatomy and workflow objects normally needed for "
            "the active step. This changes MRML display visibility only."
        )
        elementsLayout.addWidget(recommendedButton)

        step6Context = qt.QFrame(elementsPage)
        step6Context.objectName = "workflowStep6ViewContextFrame"
        step6Context.frameShape = qt.QFrame.StyledPanel
        step6ContextLayout = qt.QVBoxLayout(step6Context)
        step6ContextLayout.setContentsMargins(8, 6, 8, 6)
        step6ContextTitle = qt.QLabel(_("ROBOT WORKSPACE VIEW"), step6Context)
        step6ContextTitle.styleSheet = "font-weight: 700; color: #7a3e00;"
        step6ContextLayout.addWidget(step6ContextTitle)
        step6ContextLabel = qt.QLabel(step6Context)
        step6ContextLabel.objectName = "workflowStep6ViewContextLabel"
        step6ContextLabel.wordWrap = True
        step6ContextLayout.addWidget(step6ContextLabel)
        step6Context.visible = False
        elementsLayout.addWidget(step6Context)

        compositionGroup = qt.QGroupBox(_("View composition"), elementsPage)
        compositionGroup.objectName = "workflowViewCompositionGroupBox"
        compositionLayout = qt.QFormLayout(compositionGroup)
        compositionLayout.setContentsMargins(8, 8, 8, 8)
        compositionLayout.setHorizontalSpacing(8)
        compositionLayout.setVerticalSpacing(5)

        anatomyCombo = qt.QComboBox(compositionGroup)
        anatomyCombo.objectName = "workflowAnatomyScopeComboBox"
        for key, label in ANATOMY_SCOPE_LABELS.items():
            anatomyCombo.addItem(_(label), key)
        anatomyCombo.toolTip = _(
            "Choose a metadata-classified anatomy group. No mask geometry is edited."
        )
        compositionLayout.addRow(_("Anatomy:"), anatomyCombo)

        dimensionCombo = qt.QComboBox(compositionGroup)
        dimensionCombo.objectName = "workflowAnatomyDimensionComboBox"
        for key, label in ANATOMY_DIMENSION_LABELS.items():
            dimensionCombo.addItem(_(label), key)
        compositionLayout.addRow(_("Show in:"), dimensionCombo)

        cbctCombo = qt.QComboBox(compositionGroup)
        cbctCombo.objectName = "workflowCbctModeComboBox"
        for key, label in CBCT_MODE_LABELS.items():
            cbctCombo.addItem(_(label), key)
        cbctCombo.toolTip = _(
            "3D intensity rendering uses the CBCT voxels and a Slicer transfer "
            "function. It is not a segmentation mask or collision surface."
        )
        compositionLayout.addRow(_("CBCT:"), cbctCombo)

        overlayButton = qt.QToolButton(compositionGroup)
        overlayButton.objectName = "workflowOverlayGroupsToolButton"
        overlayButton.text = _("Choose overlays…")
        overlayButton.popupMode = qt.QToolButton.InstantPopup
        overlayMenu = qt.QMenu(overlayButton)
        for key, label in OVERLAY_GROUP_LABELS.items():
            action = overlayMenu.addAction(_(label))
            action.checkable = True
            action.connect(
                "toggled(bool)",
                lambda checked, overlayKey=key: self._onWorkflowOverlayToggled(
                    overlayKey,
                    checked,
                ),
            )
            self._workflowOverlayActions[key] = action
        overlayButton.setMenu(overlayMenu)
        compositionLayout.addRow(_("Overlays:"), overlayButton)
        elementsLayout.addWidget(compositionGroup)

        self.ui.workflowViewStatusLabel.wordWrap = True
        self.ui.workflowViewVerticalLayout.removeWidget(
            self.ui.workflowViewStatusLabel
        )
        elementsLayout.addWidget(self.ui.workflowViewStatusLabel)
        advancedButton = ctk.ctkCollapsibleButton(elementsPage)
        advancedButton.objectName = "workflowAdvancedElementsCollapsibleButton"
        advancedButton.text = _("Advanced objects")
        advancedButton.collapsed = False
        advancedLayout = qt.QVBoxLayout(advancedButton)
        advancedLayout.setContentsMargins(8, 8, 8, 8)
        advancedLayout.setSpacing(5)
        autoRecommend = qt.QCheckBox(
            _("Apply the recommended composition when entering a step"),
            advancedButton,
        )
        autoRecommend.objectName = "workflowAutoRecommendedViewCheckBox"
        autoRecommend.checked = bool(self.ui.autoWorkflowViewCheckBox.checked)
        autoRecommend.connect(
            "toggled(bool)",
            self._onWorkflowAutoRecommendToggled,
        )
        advancedLayout.addWidget(autoRecommend)
        objectTree = qt.QTreeWidget(advancedButton)
        objectTree.objectName = "workflowAdvancedObjectTreeWidget"
        objectTree.headerHidden = True
        objectTree.setColumnCount(1)
        objectTree.setMinimumHeight(250)
        objectTree.setSizePolicy(
            qt.QSizePolicy.Expanding,
            qt.QSizePolicy.Expanding,
        )
        objectTree.connect(
            "itemChanged(QTreeWidgetItem*,int)",
            self.onWorkflowViewTreeItemChanged,
        )
        advancedLayout.addWidget(objectTree, 1)
        self.ui.autoWorkflowViewCheckBox.visible = False
        self.ui.workflowViewElementsLabel.visible = False
        self.ui.workflowViewElementsListWidget.visible = False
        volumeRenderingNote = qt.QLabel(
            _(
                "Volume rendering is a 3D intensity rendering of the CBCT, "
                "not a segmentation mask. Opening, refreshing, or automatically "
                "applying Views never creates one; only the explicit CBCT 3D choice does."
            ),
            advancedButton,
        )
        volumeRenderingNote.objectName = "workflowVolumeRenderingExplanationLabel"
        volumeRenderingNote.wordWrap = True
        volumeRenderingNote.styleSheet = "color: #6b6b6b; font-style: italic;"
        advancedLayout.addWidget(volumeRenderingNote)
        elementsLayout.addWidget(advancedButton)
        elementsLayout.addStretch(1)
        self._workflowViewStageLabel = stageLabel
        self._workflowRecommendedViewButton = recommendedButton
        self._workflowViewAdvancedButton = advancedButton
        self._workflowAnatomyComboBox = anatomyCombo
        self._workflowDimensionComboBox = dimensionCombo
        self._workflowCbctComboBox = cbctCombo
        self._workflowOverlayButton = overlayButton
        self._workflowAdvancedTree = objectTree
        self._workflowAutoRecommendCheckBox = autoRecommend
        self._step6ViewContextWidget = step6Context
        self._step6ViewContextLabel = step6ContextLabel
        anatomyCombo.connect(
            "currentIndexChanged(int)",
            self.onWorkflowViewCompositionChanged,
        )
        dimensionCombo.connect(
            "currentIndexChanged(int)",
            self.onWorkflowViewCompositionChanged,
        )
        cbctCombo.connect(
            "currentIndexChanged(int)",
            self.onWorkflowViewCompositionChanged,
        )
        recommendedButton.connect(
            "clicked(bool)",
            self.onApplyRecommendedWorkflowView,
        )
        advancedButton.collapsed = True
        self._viewControlsElementsTabIndex = tabs.addTab(
            elementsPage,
            _("Elements"),
        )

        displayPage = qt.QWidget(tabs)
        displayPage.objectName = "viewControlsDisplayPage"
        displayLayout = qt.QVBoxLayout(displayPage)
        displayLayout.setContentsMargins(8, 8, 8, 8)
        displayLayout.setSpacing(5)
        self._persistentDisplayGroupBox = displayPage

        segmentationDisplayWidget = qt.QWidget(displayPage)
        segmentationDisplayWidget.objectName = "persistentSegmentationDisplayWidget"
        segmentationDisplayLayout = qt.QGridLayout(segmentationDisplayWidget)
        segmentationDisplayLayout.setContentsMargins(0, 0, 0, 0)
        segmentationDisplayLayout.setHorizontalSpacing(5)
        segmentationDisplayLayout.setVerticalSpacing(3)
        for widget, row, column, columnSpan in (
            (self.ui.segmentation2DCheckBox, 0, 0, 1),
            (self.ui.segmentation2DOpacitySlider, 0, 1, 1),
            (self.ui.segmentation2DOpacityValueLabel, 0, 2, 1),
            (self.ui.segmentation3DCheckBox, 1, 0, 1),
            (self.ui.segmentation3DOpacitySlider, 1, 1, 1),
            (self.ui.segmentation3DOpacityValueLabel, 1, 2, 1),
            (self.ui.segmentation2DRenderingModeLabel, 2, 0, 1),
            (self.ui.segmentation2DRenderingModeComboBox, 2, 1, 2),
            (self.ui.segmentationDisplayQualityStatusLabel, 3, 0, 3),
        ):
            self.ui.segmentationDisplayGridLayout.removeWidget(widget)
            segmentationDisplayLayout.addWidget(
                widget,
                row,
                column,
                1,
                columnSpan,
            )
        displayLayout.addWidget(segmentationDisplayWidget)
        self.ui.segmentationReviewVerticalLayout.removeWidget(
            self.ui.cbctGrayscaleDisplayGroupBox
        )
        displayLayout.addWidget(self.ui.cbctGrayscaleDisplayGroupBox)
        self._replaceWindowLevelSpinBoxesWithSliders()

        presetButtons = qt.QWidget(displayPage)
        presetButtons.objectName = "sceneDisplayPresetButtonsWidget"
        presetLayout = qt.QHBoxLayout(presetButtons)
        presetLayout.setContentsMargins(0, 0, 0, 0)
        presetLayout.setSpacing(5)
        savePresetButton = qt.QPushButton(
            _("Save Display Preset in Scene"), presetButtons
        )
        savePresetButton.objectName = "saveSceneDisplayPresetButton"
        savePresetButton.toolTip = _(
            "Store a reusable parameter set for overlay opacity, 2D "
            "representation, and CBCT grayscale mapping in this MRML scene. "
            "The preset is not bound to one DICOM or segmentation node ID."
        )
        self._applySceneDisplayPresetButton = qt.QPushButton(
            _("Apply Saved Preset"), presetButtons
        )
        self._applySceneDisplayPresetButton.objectName = (
            "applySceneDisplayPresetButton"
        )
        self._applySceneDisplayPresetButton.enabled = False
        presetLayout.addWidget(savePresetButton)
        presetLayout.addWidget(self._applySceneDisplayPresetButton)
        displayLayout.addWidget(presetButtons)
        self._displayPresetStatusLabel = qt.QLabel(
            _(
                "Current MRML display settings save with the scene; no separate "
                "preset has been stored yet."
            ),
            displayPage,
        )
        self._displayPresetStatusLabel.objectName = "sceneDisplayPresetStatusLabel"
        self._displayPresetStatusLabel.wordWrap = True
        self._displayPresetStatusLabel.styleSheet = "color: #1f5f99;"
        displayLayout.addWidget(self._displayPresetStatusLabel)
        savePresetButton.connect("clicked(bool)", self.onSaveSceneDisplayPreset)
        self._applySceneDisplayPresetButton.connect(
            "clicked(bool)", self.onApplySceneDisplayPreset
        )
        displayLayout.addStretch(1)
        self._viewControlsDisplayTabIndex = tabs.addTab(
            displayPage,
            _("Display"),
        )

        self._viewControlsPalette = palette
        self._viewControlsTabWidget = tabs
        self._restoreViewControlsPaletteGeometry()
        self._viewControlsPaletteDesiredVisible = self._viewControlsSettingBool(
            self.VIEW_CONTROLS_VISIBLE_SETTING,
            False,
        )
        self._viewControlsButton.connect(
            "clicked(bool)",
            self.onOpenViewControlsPalette,
        )
        self._guidanceToolButton.connect(
            "toggled(bool)",
            self.onGuidanceToolButtonToggled,
        )
        self.ui.showGuidanceCheckBox.connect(
            "toggled(bool)",
            self.onGuidanceCheckBoxToggled,
        )
        palette.connect("finished(int)", self.onViewControlsPaletteFinished)

        # The Designer container has donated all active controls and must never
        # consume fixed panel height.
        rootLayout.removeWidget(self.ui.workflowViewGroupBox)
        self.ui.workflowViewGroupBox.visible = False

        # Only the active stage lives in this independently scrolling region.
        contentWidget = qt.QWidget(uiWidget)
        contentWidget.objectName = "workflowScrollableContentWidget"
        contentLayout = qt.QVBoxLayout(contentWidget)
        contentLayout.setContentsMargins(0, 0, 0, 0)
        contentLayout.setSpacing(4)
        contentWidgets = (
            self.ui.introLabel,
            self.ui.caseCollapsibleButton,
            self.ui.imagingCollapsibleButton,
            self.ui.backendCollapsibleButton,
            self.ui.segmentationReviewCollapsibleButton,
            self.ui.planningCollapsibleButton,
            self.ui.assistedTrajectoryCollapsibleButton,
            self.ui.targetDockingCollapsibleButton,
            self.ui.templateModelingCollapsibleButton,
            self.ui.templateGuideCollapsibleButton,
            self.ui.templateFinalizationCollapsibleButton,
            self.ui.robotPlacementCollapsibleButton,
        )
        for widget in contentWidgets:
            rootLayout.removeWidget(widget)
            contentLayout.addWidget(widget)

        # Remove the designer's final expanding spacer from the fixed header;
        # the inner content layout owns the expansion from this point onward.
        for index in reversed(range(self._qtLayoutCount(rootLayout))):
            item = rootLayout.itemAt(index)
            spacer = item.spacerItem() if item and hasattr(item, "spacerItem") else None
            if spacer:
                rootLayout.takeAt(index)
        contentLayout.addStretch(1)

        scrollArea = qt.QScrollArea(uiWidget)
        scrollArea.objectName = "workflowContentScrollArea"
        scrollArea.widgetResizable = True
        scrollArea.frameShape = qt.QFrame.NoFrame
        scrollArea.horizontalScrollBarPolicy = qt.Qt.ScrollBarAlwaysOff
        scrollArea.setMinimumHeight(100)
        scrollArea.setSizePolicy(
            qt.QSizePolicy.Preferred,
            qt.QSizePolicy.Expanding,
        )
        scrollArea.setWidget(contentWidget)
        rootLayout.addWidget(scrollArea, 1)
        uiWidget.setMinimumHeight(0)
        uiWidget.setSizePolicy(
            qt.QSizePolicy.Preferred,
            qt.QSizePolicy.Ignored,
        )
        self._workflowContentScrollArea = scrollArea
        self._workflowContentWidget = contentWidget
        self._workflowContentLayout = contentLayout
