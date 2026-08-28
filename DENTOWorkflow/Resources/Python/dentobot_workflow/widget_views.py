"""Extracted shared viewer and stage navigation methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from .runtime import *


from dentobot_workflow.widget_view_catalog import ViewCatalogWidgetMixin


from dentobot_workflow.widget_view_controls import ViewControlsWidgetMixin


from dentobot_workflow.widget_view_composition import ViewCompositionWidgetMixin


from dentobot_workflow.widget_navigation import WorkflowNavigationWidgetMixin


class ViewerWidgetMixin(WorkflowNavigationWidgetMixin, ViewCompositionWidgetMixin, ViewControlsWidgetMixin, ViewCatalogWidgetMixin):
    @staticmethod
    def _viewControlsSettings():
        """Return workstation/application settings, never MRML case state."""

        return qt.QSettings()

    def _viewControlsSettingBool(self, key: str, default: bool) -> bool:
        value = self._viewControlsSettings().value(key, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _restoreViewControlsPaletteGeometry(self) -> None:
        if not self._viewControlsPalette or self._viewControlsPaletteGeometryRestored:
            return
        settings = self._viewControlsSettings()
        geometry = settings.value(self.VIEW_CONTROLS_GEOMETRY_SETTING)
        restored = False
        if geometry is not None:
            try:
                restored = bool(self._viewControlsPalette.restoreGeometry(geometry))
            except (TypeError, ValueError):
                restored = False
        if not restored:
            self._viewControlsPalette.resize(430, 540)
        self._viewControlsPaletteGeometryRestored = True

    def _saveViewControlsPaletteGeometry(self) -> None:
        if not self._viewControlsPalette:
            return
        settings = self._viewControlsSettings()
        settings.setValue(
            self.VIEW_CONTROLS_GEOMETRY_SETTING,
            self._viewControlsPalette.saveGeometry(),
        )
        settings.sync()

    def onOpenViewControlsPalette(self, checked: bool = False) -> None:
        del checked
        if not self._viewControlsPalette:
            return
        self._updateWorkflowViewControls()
        if self._viewControlsTabWidget:
            self._viewControlsTabWidget.currentIndex = (
                self._viewControlsElementsTabIndex
            )
        self._restoreViewControlsPaletteGeometry()
        self._viewControlsPaletteDesiredVisible = True
        settings = self._viewControlsSettings()
        settings.setValue(self.VIEW_CONTROLS_VISIBLE_SETTING, True)
        settings.sync()
        self._viewControlsPalette.show()
        self._viewControlsPalette.raise_()
        self._viewControlsPalette.activateWindow()

    def onViewControlsPaletteFinished(self, result: int = 0) -> None:
        del result
        self._viewControlsPaletteDesiredVisible = False
        self._saveViewControlsPaletteGeometry()
        settings = self._viewControlsSettings()
        settings.setValue(self.VIEW_CONTROLS_VISIBLE_SETTING, False)
        settings.sync()

    def _hideViewControlsPalette(self, preservePreference: bool = True) -> None:
        if not self._viewControlsPalette:
            return
        self._saveViewControlsPaletteGeometry()
        if not preservePreference:
            self._viewControlsPaletteDesiredVisible = False
            settings = self._viewControlsSettings()
            settings.setValue(self.VIEW_CONTROLS_VISIBLE_SETTING, False)
            settings.sync()
        self._viewControlsPalette.hide()

    def _restoreViewControlsPaletteOnEnter(self) -> None:
        if not self._viewControlsPalette:
            return
        self._viewControlsPaletteDesiredVisible = self._viewControlsSettingBool(
            self.VIEW_CONTROLS_VISIBLE_SETTING,
            False,
        )
        if self._viewControlsPaletteDesiredVisible:
            self._viewControlsPalette.show()
            self._viewControlsPalette.raise_()

    def onGuidanceToolButtonToggled(self, checked: bool) -> None:
        if self.ui.showGuidanceCheckBox.checked != bool(checked):
            self.ui.showGuidanceCheckBox.checked = bool(checked)

    def onGuidanceCheckBoxToggled(self, checked: bool) -> None:
        if not self._guidanceToolButton:
            return
        wasBlocked = self._guidanceToolButton.blockSignals(True)
        self._guidanceToolButton.checked = bool(checked)
        self._guidanceToolButton.blockSignals(wasBlocked)

    def _replaceWindowLevelSpinBoxesWithSliders(self) -> None:
        formLayout = self.ui.cbctGrayscaleDisplayFormLayout
        self.ui.cbctWindowSpinBox.visible = False
        self.ui.cbctLevelSpinBox.visible = False
        formLayout.removeWidget(self.ui.cbctWindowSpinBox)
        formLayout.removeWidget(self.ui.cbctLevelSpinBox)

        def sliderField(objectName: str, initialValue: int):
            container = qt.QWidget(self.ui.cbctGrayscaleDisplayGroupBox)
            container.objectName = f"{objectName}Field"
            layout = qt.QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(5)
            slider = qt.QSlider(qt.Qt.Horizontal, container)
            slider.objectName = objectName
            slider.enabled = False
            slider.focusPolicy = qt.Qt.StrongFocus
            slider.tracking = True
            slider.value = int(initialValue)
            valueLabel = qt.QLabel("--", container)
            valueLabel.objectName = f"{objectName}ValueLabel"
            valueLabel.setMinimumWidth(64)
            valueLabel.alignment = qt.Qt.AlignRight | qt.Qt.AlignVCenter
            layout.addWidget(slider, 1)
            layout.addWidget(valueLabel)
            return container, slider, valueLabel

        windowField, self._cbctWindowSlider, self._cbctWindowSliderValueLabel = (
            sliderField("cbctWindowSlider", 10)
        )
        levelField, self._cbctLevelSlider, self._cbctLevelSliderValueLabel = (
            sliderField("cbctLevelSlider", 0)
        )
        self._cbctWindowSlider.toolTip = self.ui.cbctWindowSpinBox.toolTip
        self._cbctLevelSlider.toolTip = self.ui.cbctLevelSpinBox.toolTip
        formLayout.setWidget(1, qt.QFormLayout.FieldRole, windowField)
        formLayout.setWidget(2, qt.QFormLayout.FieldRole, levelField)
        self._cbctWindowSlider.connect(
            "valueChanged(int)", self.onCbctWindowLevelSliderChanged
        )
        self._cbctLevelSlider.connect(
            "valueChanged(int)", self.onCbctWindowLevelSliderChanged
        )

































    def onApplyRecommendedWorkflowView(self, checked: bool = False) -> None:
        """Apply the explicit recommendation for the active workflow step."""

        del checked
        self._applyWorkflowViewPreset("recommended")






















    def onWorkflowViewPresetChanged(self, index: int) -> None:
        if self._updatingWorkflowViewUI or index < 0:
            return
        presetKey = str(self.ui.workflowViewPresetComboBox.itemData(index) or "")
        if not presetKey or presetKey in {"scene", "custom"}:
            return
        self._applyWorkflowViewPreset(presetKey)

    def onWorkflowViewElementChanged(self, item) -> None:
        if self._updatingWorkflowViewUI or not item or not self._parameterNode:
            return
        key = str(item.data(qt.Qt.UserRole) or "")
        entry = self._workflowViewEntriesByKey.get(key)
        if not entry:
            return
        self._ensureWorkflowViewSnapshot()
        visible = item.checkState() == qt.Qt.Checked
        restriction = self._setWorkflowViewEntryVisible(entry, visible)
        if visible:
            self._workflowViewVisibleKeys.add(key)
        else:
            self._workflowViewVisibleKeys.discard(key)
        self._workflowViewActivePresetKey = "custom"
        self._workflowViewComposition = None
        if restriction:
            self.ui.workflowViewStatusLabel.text = restriction
            self.ui.workflowViewStatusLabel.styleSheet = "color: #b06a00;"
        else:
            self.ui.workflowViewStatusLabel.text = _(
                "Custom display selection; geometry and masks are unchanged."
            )
            self.ui.workflowViewStatusLabel.styleSheet = "color: #1f5f99;"
        # A manual element toggle is authoritative custom presentation.  The
        # Step 6 recommended preset prevents duplicate closed/open anatomy, but
        # it must not immediately undo the operator's explicit visibility
        # choice (including hiding the placement-only fallback).
        self._scheduleWorkflowViewControlsRefresh()

    def _removeWorkflowCreatedVolumeRenderingNodes(self) -> None:
        for nodeId in list(self._workflowViewCreatedRendererNodeIds):
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            if node:
                slicer.mrmlScene.RemoveNode(node)
        for nodeId in list(self._workflowViewCreatedPropertyNodeIds):
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            if not node:
                continue
            references = vtk.vtkCollection()
            try:
                slicer.mrmlScene.GetReferencingNodes(node, references)
            except Exception:
                continue
            if references.GetNumberOfItems() == 0:
                slicer.mrmlScene.RemoveNode(node)
        self._workflowViewCreatedRendererNodeIds.clear()
        self._workflowViewCreatedPropertyNodeIds.clear()

    def _restoreWorkflowViewState(self, updateUi: bool = True) -> None:
        state = self._workflowViewPriorState
        self._workflowViewPriorState = None
        self._workflowViewActivePresetKey = ""
        self._workflowViewVisibleKeys.clear()
        self._workflowViewComposition = None
        if state and self.logic:
            self._removeWorkflowCreatedVolumeRenderingNodes()
            for compositeId, compositeState in state.get(
                "sliceComposites",
                {},
            ).items():
                composite = slicer.mrmlScene.GetNodeByID(compositeId)
                if not composite:
                    continue
                composite.SetBackgroundVolumeID(compositeState.get("background"))
                composite.SetForegroundVolumeID(compositeState.get("foreground"))
                composite.SetLabelVolumeID(compositeState.get("label"))
                composite.SetForegroundOpacity(
                    float(compositeState.get("foregroundOpacity", 0.0))
                )
                composite.SetLabelOpacity(
                    float(compositeState.get("labelOpacity", 1.0))
                )
            for displayNodeId, visible in state.get("volumeRendering", {}).items():
                displayNode = slicer.mrmlScene.GetNodeByID(displayNodeId)
                if displayNode:
                    displayNode.SetVisibility(bool(visible))
            for segmentationState in state.get(
                "additionalSegmentations", {}
            ).values():
                self.logic.restoreWorkflowDisplayState(segmentationState)
            self.logic.restoreWorkflowDisplayState(state)
        if updateUi and hasattr(self, "ui"):
            self.ui.restorePlanningViewButton.enabled = False
            self.ui.workflowViewStatusLabel.text = _(
                "Previous segmentation and workflow-object display restored."
            )
            self.ui.workflowViewStatusLabel.styleSheet = "color: #207227;"
            self._updateWorkflowViewControls()
            self._updateTemplateGuideVisibilityControls()

    def _enforceStep6OpenedJawDisplaySeparation(self) -> None:
        """Keep closed-pose lower masks out of 3D while the opened proxy is current."""
        if (
            not self._parameterNode
            or not self.logic
            or self._step6SceneKind() != "case"
        ):
            return
        mode = str(self._parameterNode.step6CaseJawPreparationMode)
        if mode == "TargetJawFallback":
            if self.logic.step6TargetJawFallbackFreshnessIssues(self._parameterNode):
                return
            segmentation = self._parameterNode.teethSegmentation
            display = segmentation.GetDisplayNode() if segmentation else None
            if display:
                groups = self.logic.step6CaseJawSegmentIds(segmentation)
                for segmentId in groups["upper"] + groups["lower"]:
                    display.SetSegmentVisibility3D(segmentId, False)
            fallbackDisplay = (
                self._parameterNode.step6TargetJawFallbackAnatomy.GetDisplayNode()
                if self._parameterNode.step6TargetJawFallbackAnatomy
                else None
            )
            if fallbackDisplay:
                fallbackDisplay.SetVisibility3D(True)
            return
        if self.logic.step6CaseJawOpeningFreshnessIssues(self._parameterNode):
            return
        segmentation = self._parameterNode.teethSegmentation
        display = segmentation.GetDisplayNode() if segmentation else None
        if not display:
            return
        jawGroups = self.logic.step6CaseJawSegmentIds(segmentation)
        for segmentId in jawGroups["upper"] + jawGroups["lower"]:
            display.SetSegmentVisibility3D(segmentId, False)
        for derived in (
            self._parameterNode.step6FixedUpperAnatomy,
            self._parameterNode.step6MovingLowerAnatomy,
        ):
            derivedDisplay = derived.GetDisplayNode() if derived else None
            if derivedDisplay:
                derivedDisplay.SetVisibility3D(True)
        model = self._parameterNode.step6OpenedLowerJawModel
        modelDisplay = model.GetDisplayNode() if model else None
        if modelDisplay:
            modelDisplay.SetVisibility3D(True)
        if self.logic.step6TargetJaw(self._parameterNode) == "lower":
            sourceModels = (
                [self._parameterNode.finalPrintableTemplateModel]
                if self._parameterNode.finalPrintableTemplateModel
                else [
                    self._parameterNode.draftTemplateSupportModel,
                    self._parameterNode.targetDockingAssemblyModel,
                ]
            )
            for source in sourceModels:
                sourceDisplay = source.GetDisplayNode() if source else None
                if sourceDisplay:
                    sourceDisplay.SetVisibility(False)
            trajectory = self._parameterNode.trajectoryLine
            trajectoryDisplay = trajectory.GetDisplayNode() if trajectory else None
            if trajectoryDisplay:
                trajectoryDisplay.SetVisibility(False)
            for proxy in (
                self._parameterNode.step6OpenedTargetGeometryModel,
                self._parameterNode.step6OpenedTrajectoryLine,
            ):
                proxyDisplay = proxy.GetDisplayNode() if proxy else None
                if proxyDisplay:
                    proxyDisplay.SetVisibility(True)

    def onRestoreWorkflowView(self, checked: bool = False) -> None:
        del checked
        self._restoreWorkflowViewState(updateUi=True)

    def onFrameWorkflowView(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        boundsList = []
        for entry in self._workflowViewEntriesByKey.values():
            if self._workflowViewEntryCheckState(entry) == qt.Qt.Unchecked:
                continue
            if entry["kind"] == "node":
                bounds = [0.0] * 6
                entry["node"].GetRASBounds(bounds)
                boundsList.append(bounds)
            elif entry["kind"] == "nodes":
                for node in entry["nodes"]:
                    bounds = [0.0] * 6
                    node.GetRASBounds(bounds)
                    boundsList.append(bounds)
            elif entry["kind"] == "volume_rendering":
                bounds = [0.0] * 6
                entry["node"].GetRASBounds(bounds)
                boundsList.append(bounds)
            else:
                for segmentId in entry["segmentIds"]:
                    try:
                        boundsList.append(
                            self.logic.getSegmentationSegmentBoundsWorld(
                                entry.get("segmentationNode")
                                or self._parameterNode.teethSegmentation,
                                segmentId,
                            )
                        )
                    except ValueError:
                        continue
        finiteBounds = [
            tuple(float(value) for value in bounds)
            for bounds in boundsList
            if len(bounds) == 6
            and all(math.isfinite(float(value)) for value in bounds)
            and all(bounds[2 * axis + 1] > bounds[2 * axis] for axis in range(3))
        ]
        if not finiteBounds:
            self.ui.workflowViewStatusLabel.text = _(
                "No visible workflow geometry is available to frame."
            )
            self.ui.workflowViewStatusLabel.styleSheet = "color: #b36b00;"
            return
        combined = tuple(
            min(bounds[axis] for bounds in finiteBounds)
            if axis % 2 == 0
            else max(bounds[axis] for bounds in finiteBounds)
            for axis in range(6)
        )
        self._frameRasBoundsInViews(combined)
        self.ui.workflowViewStatusLabel.text = _(
            "Framed the currently visible workflow elements."
        )
        self.ui.workflowViewStatusLabel.styleSheet = "color: #207227;"

    def _hideLegacyPost5BControls(self) -> None:
        """Keep old scene fields readable while removing their superseded UI path."""

        obsoleteWidgetNames = (
            "templateGuideVisibilityGroupBox",
            "templateShellRoiLabel",
            "templateShellRoiSelector",
            "createTemplateShellRoiButton",
            "deleteTemplateShellRoiButton",
            "templateChannelDiameterLabel",
            "templateChannelDiameterSpinBox",
            "researchTemplateShellModelLabel",
            "researchTemplateShellModelSelector",
            "researchTemplateSleeveModelLabel",
            "researchTemplateSleeveModelSelector",
            "shellRoiVisibilityCheckBox",
            "shellModelVisibilityCheckBox",
            "sleeveModelVisibilityCheckBox",
            "generateResearchTemplateButton",
            "deleteResearchTemplateButton",
            "templateGuideStatusLabel",
            "templateGuideSafetyLabel",
            "templateFinalizationDescriptionLabel",
            "templateFinalizationLineageLabel",
            "templateFinalizationSourceLabel",
            "templateFinalizationSourceValueLabel",
            "templateFinalizationModeLabel",
            "templateFinalizationModeComboBox",
            "templateFinalizationKeepRegionLabel",
            "templateFinalizationKeepRegionComboBox",
            "templateTrimPlaneLabel",
            "templateTrimPlaneSelector",
            "templateTrimCurveLabel",
            "templateTrimCurveSelector",
            "finalizedTemplateShellModelLabel",
            "finalizedTemplateShellModelSelector",
            "templateFinalizationCameraFrameLabel",
            "templateFinalizationViewLockedCheckBox",
            "templateFinalizationYawLockedCheckBox",
            "continueTemplateFinalizationButton",
            "restoreTemplateFinalizationViewButton",
            "createTemplateTrimPlaneButton",
            "placeTemplateTrimCurveButton",
            "applyTemplateFinalizationButton",
            "openDynamicModelerButton",
            "deleteTemplateFinalizationButton",
            "exportResearchTemplateButton",
            "templateFinalizationStatusLabel",
            "templateFinalizationSafetyLabel",
        )
        for widgetName in obsoleteWidgetNames:
            widget = getattr(self.ui, widgetName, None)
            if widget:
                widget.visible = False
