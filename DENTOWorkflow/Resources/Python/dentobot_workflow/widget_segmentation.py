"""Extracted segmentation review UI methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from .runtime import *


class SegmentationWidgetMixin:
    def _bindSegmentationReviewNode(self, segmentationNode) -> None:
        """Observe the selected segmentation and its display state exactly once."""

        sourceVolume = None
        sourceVolumeDisplayNode = None
        if segmentationNode and self.logic:
            try:
                sourceVolume = self.logic.getSegmentationSourceVolume(
                    segmentationNode
                )
            except ValueError:
                pass
            if sourceVolume:
                sourceVolume.CreateDefaultDisplayNodes()
                sourceVolumeDisplayNode = sourceVolume.GetDisplayNode()
        if segmentationNode is self._reviewSegmentationNode:
            displayNode = segmentationNode.GetDisplayNode() if segmentationNode else None
            if (
                displayNode is self._reviewDisplayNode
                and sourceVolumeDisplayNode is self._reviewSourceVolumeDisplayNode
            ):
                return

        if self._reviewSegmentationNode:
            self.removeObserver(
                self._reviewSegmentationNode,
                vtk.vtkCommand.ModifiedEvent,
                self._onReviewSegmentationModified,
            )
            for segmentationEvent in (
                slicer.vtkSegmentation.SourceRepresentationModified,
                slicer.vtkSegmentation.SegmentAdded,
                slicer.vtkSegmentation.SegmentRemoved,
            ):
                self.removeObserver(
                    self._reviewSegmentationNode,
                    segmentationEvent,
                    self._onReviewSegmentationContentModified,
                )
        if self._reviewDisplayNode:
            self.removeObserver(
                self._reviewDisplayNode,
                vtk.vtkCommand.ModifiedEvent,
                self._onReviewDisplayModified,
            )
        if self._reviewSourceVolumeDisplayNode:
            self.removeObserver(
                self._reviewSourceVolumeDisplayNode,
                vtk.vtkCommand.ModifiedEvent,
                self._onReviewSourceVolumeDisplayModified,
            )

        self._reviewSegmentationNode = segmentationNode
        self._reviewDisplayNode = None
        self._reviewSourceVolumeNode = None
        self._reviewSourceVolumeDisplayNode = None

        if not segmentationNode:
            return

        segmentationNode.CreateDefaultDisplayNodes()
        self._reviewDisplayNode = segmentationNode.GetDisplayNode()
        self.addObserver(
            segmentationNode,
            vtk.vtkCommand.ModifiedEvent,
            self._onReviewSegmentationModified,
        )
        for segmentationEvent in (
            slicer.vtkSegmentation.SourceRepresentationModified,
            slicer.vtkSegmentation.SegmentAdded,
            slicer.vtkSegmentation.SegmentRemoved,
        ):
            self.addObserver(
                segmentationNode,
                segmentationEvent,
                self._onReviewSegmentationContentModified,
            )
        if self._reviewDisplayNode:
            self.addObserver(
                self._reviewDisplayNode,
                vtk.vtkCommand.ModifiedEvent,
                self._onReviewDisplayModified,
            )
        self._reviewSourceVolumeNode = sourceVolume
        self._reviewSourceVolumeDisplayNode = sourceVolumeDisplayNode
        if self._reviewSourceVolumeDisplayNode:
            volumeNodeId = sourceVolume.GetID()
            if volumeNodeId not in self._loadedVolumeDisplaySettingsByNodeId:
                self._loadedVolumeDisplaySettingsByNodeId[volumeNodeId] = (
                    self.logic.getScalarVolumeDisplaySettings(sourceVolume)
                )
            self.addObserver(
                self._reviewSourceVolumeDisplayNode,
                vtk.vtkCommand.ModifiedEvent,
                self._onReviewSourceVolumeDisplayModified,
            )

    def _onReviewSegmentationModified(self, caller=None, event=None) -> None:
        if not self._updatingSegmentationReviewUI:
            self._rebuildSegmentTree()
            self._refreshSegmentationInspection()
            self._updatePlanning()
            self._updateTemplateModeling()

    def _onReviewDisplayModified(self, caller=None, event=None) -> None:
        if not self._updatingSegmentationReviewUI:
            self._syncSegmentationDisplayControls()

    def _onReviewSourceVolumeDisplayModified(self, caller=None, event=None) -> None:
        if not self._updatingSegmentationReviewUI:
            self._syncSegmentationDisplayControls()

    def _onReviewSegmentationContentModified(
        self,
        caller=None,
        event=None,
    ) -> None:
        del event
        if (
            self._processingSegmentationContentChange
            or not self.logic
            or not self._reviewSegmentationNode
        ):
            return
        self._processingSegmentationContentChange = True
        self._updatingSegmentationReviewUI = True
        try:
            wasReviewed = self.logic.invalidateSegmentationReviewAfterEdit(
                self._reviewSegmentationNode
            )
        finally:
            self._updatingSegmentationReviewUI = False
            self._processingSegmentationContentChange = False

        self._rebuildSegmentTree()
        self._refreshSegmentationInspection()
        self._validTrajectoryPointsByNodeId.clear()
        self._updatePlanning()
        self._markCurrentDraftTemplateModelStale(
            _("Source segmentation content changed.")
        )
        self._markStep6CaseJawOpeningStale(
            _("Source segmentation content changed; re-apply the case jaw opening.")
        )
        self._updateTemplateModeling()
        self.ui.segmentationReviewStatusLabel.text = (
            _(
                "Mask content changed. Review state was reset to "
                "Needs Correction."
            )
            if wasReviewed
            else _(
                "Mask content changed. Inference metrics now describe the "
                "pre-edit result."
            )
        )
        self.ui.segmentationReviewStatusLabel.styleSheet = "color: #b36b00;"

    def _clearSegmentationReview(self) -> None:
        if not hasattr(self, "ui"):
            return
        self._updatingSegmentationReviewUI = True
        try:
            self._segmentReviewRecordsById = {}
            self.ui.segmentTreeWidget.clear()
            self.ui.segmentSearchLineEdit.clear()
            self.ui.segmentation2DCheckBox.checked = False
            self.ui.segmentation3DCheckBox.checked = False
            self.ui.segmentation2DOpacitySlider.value = 0
            self.ui.segmentation3DOpacitySlider.value = 0
            self.ui.segmentation2DOpacityValueLabel.text = _("0%")
            self.ui.segmentation3DOpacityValueLabel.text = _("0%")
            self.ui.segmentation2DRenderingModeComboBox.currentIndex = 0
            self.ui.cbctInterpolationCheckBox.checked = False
            self.ui.cbctAutoWindowLevelCheckBox.checked = False
            self.ui.cbctWindowSpinBox.value = 1.0
            self.ui.cbctLevelSpinBox.value = 0.0
            if self._cbctWindowSlider:
                self._cbctWindowSlider.enabled = False
                self._cbctWindowSlider.minimum = 1
                self._cbctWindowSlider.maximum = 10
                self._cbctWindowSlider.value = 10
                self._cbctWindowSliderValueLabel.text = _("--")
            if self._cbctLevelSlider:
                self._cbctLevelSlider.enabled = False
                self._cbctLevelSlider.minimum = -10
                self._cbctLevelSlider.maximum = 10
                self._cbctLevelSlider.value = 0
                self._cbctLevelSliderValueLabel.text = _("--")
            self.ui.cbctInvertGrayscaleCheckBox.checked = False
            self.ui.cbctGrayscaleDisplayStatusLabel.text = _(
                "Select a referenced source CBCT."
            )
            self.ui.cbctGrayscaleDisplayStatusLabel.styleSheet = ""
            self.ui.segmentationDisplayQualityStatusLabel.text = _(
                "Select a segmentation to configure review rendering."
            )
            self.ui.segmentationDisplayQualityStatusLabel.styleSheet = ""
            self._setSelectedSegmentDetailPlaceholders()
            self._setSegmentationProvenancePlaceholders()
            self._reviewMetadataWarning = ""
            self.ui.segmentationReviewStatusLabel.text = _(
                "Select a segmentation to review."
            )
            self.ui.segmentationReviewStatusLabel.styleSheet = "color: #b36b00;"
            self._setSegmentationReviewControlsEnabled(False)
            if self._applySceneDisplayPresetButton:
                self._applySceneDisplayPresetButton.enabled = bool(
                    self._parameterNode
                    and self._parameterNode.sceneDisplayPresetJson.strip()
                )
        finally:
            self._updatingSegmentationReviewUI = False

    def _setSegmentationReviewControlsEnabled(self, enabled: bool) -> None:
        for widget in (
            self.ui.segmentSearchLineEdit,
            self.ui.segmentTreeWidget,
            self.ui.showAllSegmentsButton,
            self.ui.hideAllSegmentsButton,
            self.ui.segmentation2DCheckBox,
            self.ui.segmentation3DCheckBox,
            self.ui.segmentation2DOpacitySlider,
            self.ui.segmentation3DOpacitySlider,
            self.ui.segmentation2DRenderingModeComboBox,
            self.ui.cbctInterpolationCheckBox,
            self.ui.cbctAutoWindowLevelCheckBox,
            self.ui.cbctWindowSpinBox,
            self.ui.cbctLevelSpinBox,
            self.ui.cbctInvertGrayscaleCheckBox,
            self.ui.cbctRestoreLoadedDisplayButton,
            self.ui.reviewStateComboBox,
        ):
            widget.enabled = enabled
        if self._cbctWindowSlider:
            self._cbctWindowSlider.enabled = bool(
                enabled and not self.ui.cbctAutoWindowLevelCheckBox.checked
            )
        if self._cbctLevelSlider:
            self._cbctLevelSlider.enabled = bool(
                enabled and not self.ui.cbctAutoWindowLevelCheckBox.checked
            )
        currentItem = self.ui.segmentTreeWidget.currentItem()
        hasSelectedSegment = bool(
            enabled and currentItem and currentItem.data(0, qt.Qt.UserRole)
        )
        self.ui.isolateSegmentButton.enabled = hasSelectedSegment
        self.ui.editSelectedSegmentButton.enabled = hasSelectedSegment

    def _updateSegmentationReview(self) -> None:
        if not self._reviewSegmentationNode or not self.logic:
            self._clearSegmentationReview()
            return
        self._updatingSegmentationReviewUI = True
        try:
            self._reviewMetadataWarning = (
                self.logic.ensureSegmentationReviewMetadata(
                    self._reviewSegmentationNode
                )
            )
            self.logic.ensureSegmentationDisplayQualityDefaults(
                self._reviewSegmentationNode
            )
        finally:
            self._updatingSegmentationReviewUI = False
        self._bindSegmentationReviewNode(self._reviewSegmentationNode)
        self._setSegmentationReviewControlsEnabled(True)
        self._rebuildSegmentTree()
        self._syncSegmentationDisplayControls()
        self._refreshSegmentationInspection()

    def _rebuildSegmentTree(self) -> None:
        if not self._reviewSegmentationNode or not self.logic:
            self._clearSegmentationReview()
            return

        selectedItem = self.ui.segmentTreeWidget.currentItem()
        selectedSegmentId = (
            str(selectedItem.data(0, qt.Qt.UserRole))
            if selectedItem and selectedItem.data(0, qt.Qt.UserRole)
            else None
        )
        records = self.logic.getSegmentationReviewRecords(
            self._reviewSegmentationNode
        )
        self._segmentReviewRecordsById = {
            record["segmentId"]: record for record in records
        }

        self._updatingSegmentationReviewUI = True
        try:
            treeWidget = self.ui.segmentTreeWidget
            treeWidget.clear()
            groups: dict[str, object] = {}
            selectedTreeItem = None
            displayNode = self._reviewSegmentationNode.GetDisplayNode()

            for record in records:
                category = record["category"]
                groupItem = groups.get(category)
                if groupItem is None:
                    groupItem = qt.QTreeWidgetItem(treeWidget)
                    groupItem.setText(0, category)
                    groupItem.setFirstColumnSpanned(True)
                    groupFont = groupItem.font(0)
                    groupFont.setBold(True)
                    groupItem.setFont(0, groupFont)
                    groups[category] = groupItem

                segmentItem = qt.QTreeWidgetItem(groupItem)
                segmentItem.setText(0, record["displayName"])
                segmentItem.setText(1, record["sourceName"])
                segmentItem.setToolTip(
                    0,
                    _("Source label: %1").replace("%1", record["sourceName"]),
                )
                segmentItem.setData(0, qt.Qt.UserRole, record["segmentId"])
                segmentItem.setCheckState(
                    0,
                    qt.Qt.Checked
                    if displayNode.GetSegmentVisibility(record["segmentId"])
                    else qt.Qt.Unchecked,
                )
                if record["segmentId"] == selectedSegmentId:
                    selectedTreeItem = segmentItem

            treeWidget.expandAll()
            if selectedTreeItem:
                treeWidget.setCurrentItem(selectedTreeItem)
        finally:
            self._updatingSegmentationReviewUI = False

        self._applySegmentFilter(self.ui.segmentSearchLineEdit.text)
        self._updateSegmentationReviewStatus()

    def _syncSegmentationDisplayControls(self) -> None:
        if not self._reviewSegmentationNode:
            self._clearSegmentationReview()
            return
        displayNode = self._reviewSegmentationNode.GetDisplayNode()
        if not displayNode:
            self._clearSegmentationReview()
            return

        self._updatingSegmentationReviewUI = True
        try:
            self.ui.segmentation2DCheckBox.checked = bool(
                displayNode.GetVisibility2D()
            )
            self.ui.segmentation3DCheckBox.checked = bool(
                displayNode.GetVisibility3D()
            )
            opacity2D = int(round(float(displayNode.GetOpacity2DFill()) * 100.0))
            opacity3D = int(round(float(displayNode.GetOpacity3D()) * 100.0))
            self.ui.segmentation2DOpacitySlider.value = opacity2D
            self.ui.segmentation3DOpacitySlider.value = opacity3D
            self.ui.segmentation2DOpacityValueLabel.text = f"{opacity2D}%"
            self.ui.segmentation3DOpacityValueLabel.text = f"{opacity3D}%"
            renderingMode = self.logic.getSegmentation2DRenderingMode(
                self._reviewSegmentationNode
            )
            self.ui.segmentation2DRenderingModeComboBox.currentIndex = (
                0
                if renderingMode
                == self.logic.SEGMENTATION_2D_RENDERING_MODE_SMOOTH
                else 1
            )
            sourceVolume = None
            try:
                sourceVolume = self.logic.getSegmentationSourceVolume(
                    self._reviewSegmentationNode
                )
            except ValueError:
                pass
            cbctInterpolated = bool(
                sourceVolume
                and self.logic.getScalarVolumeInterpolation(sourceVolume)
            )
            self.ui.cbctInterpolationCheckBox.checked = cbctInterpolated
            if sourceVolume:
                displaySettings = self.logic.getScalarVolumeDisplaySettings(
                    sourceVolume
                )
                scalarRange = sourceVolume.GetImageData().GetScalarRange()
                scalarSpan = max(float(scalarRange[1] - scalarRange[0]), 1.0)
                windowMaximum = max(
                    scalarSpan * 20.0,
                    float(displaySettings["window"]) * 2.0,
                    100.0,
                )
                levelMargin = scalarSpan * 10.0
                self.ui.cbctWindowSpinBox.minimum = 0.01
                self.ui.cbctWindowSpinBox.maximum = windowMaximum
                self.ui.cbctWindowSpinBox.singleStep = max(
                    scalarSpan / 100.0,
                    0.1,
                )
                self.ui.cbctLevelSpinBox.minimum = (
                    float(scalarRange[0]) - levelMargin
                )
                self.ui.cbctLevelSpinBox.maximum = (
                    float(scalarRange[1]) + levelMargin
                )
                self.ui.cbctLevelSpinBox.singleStep = max(
                    scalarSpan / 100.0,
                    0.1,
                )
                sliderScale = float(self._displaySliderScale)
                displayWindow = float(displaySettings["window"])
                displayLevel = float(displaySettings["level"])
                self._cbctWindowSlider.minimum = 1
                self._cbctWindowSlider.maximum = max(
                    1,
                    int(math.ceil(windowMaximum * sliderScale)),
                )
                self._cbctLevelSlider.minimum = int(
                    math.floor(
                        min(
                            float(scalarRange[0]) - levelMargin,
                            displayLevel - displayWindow,
                        )
                        * sliderScale
                    )
                )
                self._cbctLevelSlider.maximum = int(
                    math.ceil(
                        max(
                            float(scalarRange[1]) + levelMargin,
                            displayLevel + displayWindow,
                        )
                        * sliderScale
                    )
                )
                self.ui.cbctAutoWindowLevelCheckBox.checked = bool(
                    displaySettings["autoWindowLevel"]
                )
                self.ui.cbctWindowSpinBox.value = float(
                    displaySettings["window"]
                )
                self.ui.cbctLevelSpinBox.value = float(
                    displaySettings["level"]
                )
                windowValue = displayWindow
                levelValue = displayLevel
                self._cbctWindowSlider.value = int(
                    round(windowValue * sliderScale)
                )
                self._cbctLevelSlider.value = int(
                    round(levelValue * sliderScale)
                )
                self._cbctWindowSliderValueLabel.text = f"{windowValue:.1f}"
                self._cbctLevelSliderValueLabel.text = f"{levelValue:.1f}"
                self.ui.cbctInvertGrayscaleCheckBox.checked = bool(
                    displaySettings["invertedGrayscale"]
                )
                self.ui.cbctGrayscaleDisplayStatusLabel.text = _(
                    "Display only — window %1, level %2, %3 grayscale; "
                    "source voxels unchanged."
                ).replace(
                    "%1", f"{float(displaySettings['window']):.2f}"
                ).replace(
                    "%2", f"{float(displaySettings['level']):.2f}"
                ).replace(
                    "%3",
                    _("inverted")
                    if displaySettings["invertedGrayscale"]
                    else _("standard"),
                )
                self.ui.cbctGrayscaleDisplayStatusLabel.styleSheet = (
                    "color: #1f5f99;"
                )
            else:
                self.ui.cbctAutoWindowLevelCheckBox.checked = False
                self.ui.cbctWindowSpinBox.value = 1.0
                self.ui.cbctLevelSpinBox.value = 0.0
                self._cbctWindowSlider.minimum = 1
                self._cbctWindowSlider.maximum = 10
                self._cbctWindowSlider.value = 10
                self._cbctLevelSlider.minimum = -10
                self._cbctLevelSlider.maximum = 10
                self._cbctLevelSlider.value = 0
                self._cbctWindowSliderValueLabel.text = _("--")
                self._cbctLevelSliderValueLabel.text = _("--")
                self.ui.cbctInvertGrayscaleCheckBox.checked = False
                self.ui.cbctGrayscaleDisplayStatusLabel.text = _(
                    "The segmentation has no available source CBCT reference."
                )
                self.ui.cbctGrayscaleDisplayStatusLabel.styleSheet = (
                    "color: #b36b00;"
                )
            hasSourceVolume = bool(sourceVolume)
            self.ui.cbctAutoWindowLevelCheckBox.enabled = hasSourceVolume
            self.ui.cbctWindowSpinBox.enabled = bool(
                hasSourceVolume
                and not self.ui.cbctAutoWindowLevelCheckBox.checked
            )
            self.ui.cbctLevelSpinBox.enabled = bool(
                hasSourceVolume
                and not self.ui.cbctAutoWindowLevelCheckBox.checked
            )
            self._cbctWindowSlider.enabled = bool(
                hasSourceVolume
                and not self.ui.cbctAutoWindowLevelCheckBox.checked
            )
            self._cbctLevelSlider.enabled = bool(
                hasSourceVolume
                and not self.ui.cbctAutoWindowLevelCheckBox.checked
            )
            self.ui.cbctInvertGrayscaleCheckBox.enabled = hasSourceVolume
            self.ui.cbctInterpolationCheckBox.enabled = hasSourceVolume
            self.ui.cbctRestoreLoadedDisplayButton.enabled = bool(
                hasSourceVolume
                and sourceVolume.GetID()
                in self._loadedVolumeDisplaySettingsByNodeId
            )
            self._applySceneDisplayPresetButton.enabled = bool(
                self._parameterNode
                and self._parameterNode.sceneDisplayPresetJson.strip()
            )
            presetJson = (
                self._parameterNode.sceneDisplayPresetJson.strip()
                if self._parameterNode
                else ""
            )
            if presetJson:
                try:
                    savedPreset = json.loads(presetJson)
                    savedUtc = str(savedPreset.get("savedUtc") or _("unknown time"))
                    self._displayPresetStatusLabel.text = _(
                        "A case display preset is stored in this scene (%1)."
                    ).replace("%1", savedUtc)
                    self._displayPresetStatusLabel.styleSheet = "color: #207227;"
                except (TypeError, ValueError, json.JSONDecodeError):
                    self._displayPresetStatusLabel.text = _(
                        "The stored case display preset is invalid; save a new preset."
                    )
                    self._displayPresetStatusLabel.styleSheet = "color: #b00020;"
            else:
                self._displayPresetStatusLabel.text = _(
                    "Current MRML display settings save with the scene; no "
                    "separate preset has been stored yet."
                )
                self._displayPresetStatusLabel.styleSheet = "color: #1f5f99;"
            if renderingMode == self.logic.SEGMENTATION_2D_RENDERING_MODE_SMOOTH:
                modeText = _(
                    "Optional derived surface preview; non-authoritative and "
                    "not additional anatomical resolution."
                )
                modeColor = "#b36b00"
            else:
                modeText = _(
                    "Authoritative native binary-mask pixels, including the "
                    "acquired voxel stair-steps."
                )
                modeColor = "#207227"
            if sourceVolume:
                spacingText = " × ".join(
                    f"{float(value):.2f}" for value in sourceVolume.GetSpacing()
                )
                cbctText = _(
                    " CBCT: %1 mm voxels; interpolation %2."
                ).replace("%1", spacingText).replace(
                    "%2", _("on") if cbctInterpolated else _("off")
                )
            else:
                cbctText = _(" Source CBCT reference is unavailable.")
            self.ui.segmentationDisplayQualityStatusLabel.text = (
                modeText + cbctText
            )
            self.ui.segmentationDisplayQualityStatusLabel.styleSheet = (
                f"color: {modeColor};"
            )

            treeWidget = self.ui.segmentTreeWidget
            for groupIndex in range(treeWidget.topLevelItemCount):
                groupItem = treeWidget.topLevelItem(groupIndex)
                for childIndex in range(groupItem.childCount()):
                    segmentItem = groupItem.child(childIndex)
                    segmentId = str(segmentItem.data(0, qt.Qt.UserRole))
                    segmentItem.setCheckState(
                        0,
                        qt.Qt.Checked
                        if displayNode.GetSegmentVisibility(segmentId)
                        else qt.Qt.Unchecked,
                    )
        finally:
            self._updatingSegmentationReviewUI = False
        self._updateSegmentationReviewStatus()

    def _applySegmentFilter(self, filterText: str) -> None:
        filterText = str(filterText).strip().lower()
        treeWidget = self.ui.segmentTreeWidget
        for groupIndex in range(treeWidget.topLevelItemCount):
            groupItem = treeWidget.topLevelItem(groupIndex)
            visibleChildren = 0
            for childIndex in range(groupItem.childCount()):
                segmentItem = groupItem.child(childIndex)
                segmentId = str(segmentItem.data(0, qt.Qt.UserRole))
                record = self._segmentReviewRecordsById.get(segmentId, {})
                matches = not filterText or filterText in record.get("searchText", "")
                segmentItem.setHidden(not matches)
                visibleChildren += int(matches)
            groupItem.setHidden(visibleChildren == 0)
        self._updateSegmentationReviewStatus()

    def _updateSegmentationReviewStatus(self) -> None:
        if not self._reviewSegmentationNode:
            return
        displayNode = self._reviewSegmentationNode.GetDisplayNode()
        if not displayNode:
            return
        totalCount = len(self._segmentReviewRecordsById)
        visibleCount = sum(
            int(displayNode.GetSegmentVisibility(segmentId))
            for segmentId in self._segmentReviewRecordsById
        )
        matchingCount = sum(
            1
            for record in self._segmentReviewRecordsById.values()
            if not self.ui.segmentSearchLineEdit.text.strip().lower()
            or self.ui.segmentSearchLineEdit.text.strip().lower()
            in record["searchText"]
        )
        self.ui.segmentationReviewStatusLabel.text = (
            _("%1 of %2 labels match; %3 are visible.")
            .replace("%1", str(matchingCount))
            .replace("%2", str(totalCount))
            .replace("%3", str(visibleCount))
        )
        self.ui.segmentationReviewStatusLabel.styleSheet = "color: #207227;"

    def _selectedReviewSegmentId(self) -> str | None:
        currentItem = self.ui.segmentTreeWidget.currentItem()
        if not currentItem:
            return None
        value = currentItem.data(0, qt.Qt.UserRole)
        return str(value) if value else None

    def onReviewSegmentationSelectionChanged(self, segmentationNode) -> None:
        if (
            not self._parameterNode
            or self._restoringTrajectoryAssociation
            or self._updatingFromParameterNode
        ):
            return
        currentNode = self._parameterNode.teethSegmentation
        currentNodeId = currentNode.GetID() if currentNode else None
        selectedNodeId = segmentationNode.GetID() if segmentationNode else None
        if currentNodeId != selectedNodeId:
            self._restoringTrajectoryAssociation = True
            wasModifying = self._parameterNode.StartModify()
            try:
                self._markCurrentDraftTemplateModelStale(
                    _("Authoritative source segmentation changed.")
                )
                if self._parameterNode.trajectoryLine and self.logic:
                    self.logic.clearTrajectoryTarget(
                        self._parameterNode.trajectoryLine
                    )
                    self._parameterNode.trajectoryLine.SetNodeReferenceID(
                        self.logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
                        None,
                    )
                if (
                    self._parameterNode.targetToothBoundsRoi
                    and self._parameterNode.targetToothBoundsRoi.GetDisplayNode()
                ):
                    self._parameterNode.targetToothBoundsRoi.GetDisplayNode(
                    ).SetVisibility(False)
                self._parameterNode.targetToothSegmentId = ""
                self._validTrajectoryPointsByNodeId.clear()
                self._planningConstraintWarning = ""
                self._parameterNode.templateSupportToothSegmentIdsJson = "[]"
                self._parameterNode.teethSegmentation = segmentationNode
                self._reconcileAuthoritativeSegmentationSourceVolume()
            finally:
                self._parameterNode.EndModify(wasModifying)
                self._restoringTrajectoryAssociation = False
        self._bindSegmentationReviewNode(segmentationNode)
        self._updateSegmentationReview()
        # Parameter-node GUI bindings do not guarantee that the planning
        # refresh observer runs after this selection callback on every Slicer
        # version. Refresh Step 4A explicitly so existing segmentations become
        # immediately available to the target-tooth selector.
        self._updatePlanning()
        self._updateTemplateModeling()

    def onSegmentSearchTextChanged(self, filterText: str) -> None:
        if not self._updatingSegmentationReviewUI:
            self._applySegmentFilter(filterText)

    def onSegmentTreeItemChanged(self, item, column: int) -> None:
        if self._updatingSegmentationReviewUI or column != 0:
            return
        segmentId = item.data(0, qt.Qt.UserRole)
        if not segmentId or not self._reviewSegmentationNode or not self.logic:
            return
        self.logic.setSegmentationSegmentVisibility(
            self._reviewSegmentationNode,
            str(segmentId),
            item.checkState(0) == qt.Qt.Checked,
        )

    def onSegmentTreeCurrentItemChanged(self, currentItem, previousItem) -> None:
        del previousItem
        if self._updatingSegmentationReviewUI:
            return
        segmentId = (
            str(currentItem.data(0, qt.Qt.UserRole))
            if currentItem and currentItem.data(0, qt.Qt.UserRole)
            else None
        )
        self.ui.isolateSegmentButton.enabled = bool(segmentId)
        self.ui.editSelectedSegmentButton.enabled = bool(segmentId)
        if not segmentId:
            self._setSelectedSegmentDetailPlaceholders()
            if self._reviewSegmentationNode and self.logic:
                self._applyTargetPriorityHighlight()
            return
        record = self._segmentReviewRecordsById.get(segmentId)
        if record:
            if self._reviewSegmentationNode and self.logic:
                self._applyTargetPriorityHighlight()
            self.ui.segmentationReviewStatusLabel.text = (
                _(
                    "Review selection: %1. The Step 4A target remains the "
                    "priority viewport highlight when one is assigned."
                ).replace("%1", record["displayName"])
            )
            self.ui.segmentationReviewStatusLabel.styleSheet = "color: #1f5f99;"
            self._updateSelectedSegmentDetails(segmentId)

    def onShowAllSegments(self) -> None:
        if self._reviewSegmentationNode and self.logic:
            self.logic.setAllSegmentationSegmentsVisibility(
                self._reviewSegmentationNode,
                True,
            )
            self.logic.setSegmentationSegmentHighlight(
                self._reviewSegmentationNode,
                None,
            )

    def onHideAllSegments(self) -> None:
        if self._reviewSegmentationNode and self.logic:
            self.logic.setSegmentationSegmentHighlight(
                self._reviewSegmentationNode,
                None,
            )
            self.logic.setAllSegmentationSegmentsVisibility(
                self._reviewSegmentationNode,
                False,
            )

    def onIsolateSelectedSegment(self) -> None:
        segmentId = self._selectedReviewSegmentId()
        if segmentId and self._reviewSegmentationNode and self.logic:
            self.logic.setSegmentationSegmentHighlight(
                self._reviewSegmentationNode,
                None,
            )
            self.logic.isolateSegmentationSegment(
                self._reviewSegmentationNode,
                segmentId,
            )

    def onEditSelectedSegment(self) -> None:
        segmentId = self._selectedReviewSegmentId()
        if not segmentId or not self._reviewSegmentationNode or not self.logic:
            slicer.util.errorDisplay(
                _("Select a segmentation label before opening Segment Editor.")
            )
            return

        with slicer.util.tryWithErrorDisplay(
            _("Could not open the selected label in Segment Editor.")
        ):
            segmentEditorModule = getattr(
                slicer.modules,
                "segmenteditor",
                None,
            )
            if not segmentEditorModule:
                raise RuntimeError(
                    _("The built-in Segment Editor module is unavailable.")
                )
            moduleWidget = segmentEditorModule.widgetRepresentation().self()
            if not moduleWidget or not moduleWidget.editor:
                raise RuntimeError(
                    _("The built-in Segment Editor widget is unavailable.")
                )
            handoff = self.logic.beginSegmentationCorrection(
                self._reviewSegmentationNode,
                segmentId,
            )
            self.logic.setSegmentationSegmentHighlight(
                self._reviewSegmentationNode,
                None,
            )
            self.logic.setSegmentationSegmentVisibility(
                self._reviewSegmentationNode,
                segmentId,
                True,
            )
            slicer.util.setSliceViewerLayers(
                background=handoff["sourceVolume"],
                fit=False,
            )
            moduleWidget.editor.setSegmentationNode(
                handoff["segmentationNode"]
            )
            moduleWidget.editor.setSourceVolumeNode(handoff["sourceVolume"])
            moduleWidget.editor.setCurrentSegmentID(handoff["segmentId"])
            moduleWidget.editor.setActiveEffect(None)
            slicer.util.selectModule("SegmentEditor")

    def onSegmentation2DVisibilityToggled(self, visible: bool) -> None:
        if (
            not self._updatingSegmentationReviewUI
            and self._reviewSegmentationNode
            and self.logic
        ):
            self.logic.setSegmentationVisibility2D(
                self._reviewSegmentationNode,
                visible,
            )

    def onSegmentation3DVisibilityToggled(self, visible: bool) -> None:
        if (
            not self._updatingSegmentationReviewUI
            and self._reviewSegmentationNode
            and self.logic
        ):
            self.logic.setSegmentationVisibility3D(
                self._reviewSegmentationNode,
                visible,
            )

    def onSegmentation2DOpacityChanged(self, value: int) -> None:
        self.ui.segmentation2DOpacityValueLabel.text = f"{int(value)}%"
        if (
            not self._updatingSegmentationReviewUI
            and self._reviewSegmentationNode
            and self.logic
        ):
            self.logic.setSegmentationOpacity2D(
                self._reviewSegmentationNode,
                float(value) / 100.0,
            )

    def onSegmentation3DOpacityChanged(self, value: int) -> None:
        self.ui.segmentation3DOpacityValueLabel.text = f"{int(value)}%"
        if (
            not self._updatingSegmentationReviewUI
            and self._reviewSegmentationNode
            and self.logic
        ):
            self.logic.setSegmentationOpacity3D(
                self._reviewSegmentationNode,
                float(value) / 100.0,
            )

    def onSegmentation2DRenderingModeChanged(self, index: int) -> None:
        if (
            self._updatingSegmentationReviewUI
            or not self._reviewSegmentationNode
            or not self.logic
        ):
            return
        mode = (
            self.logic.SEGMENTATION_2D_RENDERING_MODE_SMOOTH
            if int(index) == 0
            else self.logic.SEGMENTATION_2D_RENDERING_MODE_NATIVE
        )
        with slicer.util.tryWithErrorDisplay(
            _("Could not change the 2D segmentation rendering mode.")
        ):
            self.logic.setSegmentation2DRenderingMode(
                self._reviewSegmentationNode,
                mode,
            )
        self._syncSegmentationDisplayControls()

    def onCbctInterpolationToggled(self, enabled: bool) -> None:
        if (
            self._updatingSegmentationReviewUI
            or not self._reviewSegmentationNode
            or not self.logic
        ):
            return
        with slicer.util.tryWithErrorDisplay(
            _("Could not change the source CBCT interpolation setting.")
        ):
            sourceVolume = self.logic.getSegmentationSourceVolume(
                self._reviewSegmentationNode
            )
            self.logic.setScalarVolumeInterpolation(sourceVolume, enabled)
        self._syncSegmentationDisplayControls()

    def onCbctAutoWindowLevelToggled(self, enabled: bool) -> None:
        if (
            self._updatingSegmentationReviewUI
            or not self._reviewSegmentationNode
            or not self.logic
        ):
            return
        with slicer.util.tryWithErrorDisplay(
            _("Could not change the source CBCT automatic window/level setting.")
        ):
            sourceVolume = self.logic.getSegmentationSourceVolume(
                self._reviewSegmentationNode
            )
            self.logic.setScalarVolumeAutoWindowLevel(sourceVolume, enabled)
        self._syncSegmentationDisplayControls()

    def onCbctWindowLevelChanged(self, _value: float) -> None:
        if (
            self._updatingSegmentationReviewUI
            or not self._reviewSegmentationNode
            or not self.logic
        ):
            return
        with slicer.util.tryWithErrorDisplay(
            _("Could not change the source CBCT window/level display.")
        ):
            sourceVolume = self.logic.getSegmentationSourceVolume(
                self._reviewSegmentationNode
            )
            self.logic.setScalarVolumeWindowLevel(
                sourceVolume,
                float(self.ui.cbctWindowSpinBox.value),
                float(self.ui.cbctLevelSpinBox.value),
            )
        self._syncSegmentationDisplayControls()

    def onCbctWindowLevelSliderChanged(self, _value: int) -> None:
        if (
            self._updatingSegmentationReviewUI
            or not self._reviewSegmentationNode
            or not self.logic
        ):
            return
        window = float(self._cbctWindowSlider.value) / self._displaySliderScale
        level = float(self._cbctLevelSlider.value) / self._displaySliderScale
        self._cbctWindowSliderValueLabel.text = f"{window:.1f}"
        self._cbctLevelSliderValueLabel.text = f"{level:.1f}"
        with slicer.util.tryWithErrorDisplay(
            _("Could not change the source CBCT window/level display.")
        ):
            sourceVolume = self.logic.getSegmentationSourceVolume(
                self._reviewSegmentationNode
            )
            self.logic.setScalarVolumeWindowLevel(sourceVolume, window, level)
        self._syncSegmentationDisplayControls()

    def _currentSceneDisplayPreset(self) -> dict:
        """Capture a node-independent display parameter set for this MRB."""

        if not self._parameterNode or not self.logic:
            raise ValueError(_("DENTOWorkflow is not ready."))
        segmentationNode = self._reviewSegmentationNode
        segmentationDisplay = (
            segmentationNode.GetDisplayNode() if segmentationNode else None
        )
        baselineDisplay = {}
        if (
            segmentationNode
            and self._workflowViewPriorState
            and self._workflowViewPriorState.get("segmentationNodeId")
            == segmentationNode.GetID()
        ):
            baselineDisplay = self._workflowViewPriorState.get(
                "segmentationDisplay", {}
            )
        if segmentationDisplay:
            segmentation2DVisible = bool(
                baselineDisplay.get(
                    "visibility2D",
                    segmentationDisplay.GetVisibility2D(),
                )
            )
            segmentation3DVisible = bool(
                baselineDisplay.get(
                    "visibility3D",
                    segmentationDisplay.GetVisibility3D(),
                )
            )
            segmentation2DOpacity = float(
                baselineDisplay.get(
                    "opacity2DFill",
                    segmentationDisplay.GetOpacity2DFill(),
                )
            )
            segmentation3DOpacity = float(
                baselineDisplay.get(
                    "opacity3D",
                    segmentationDisplay.GetOpacity3D(),
                )
            )
            renderingMode = self.logic.getSegmentation2DRenderingMode(
                segmentationNode
            )
        else:
            segmentation2DVisible = bool(
                self.ui.segmentation2DCheckBox.checked
            )
            segmentation3DVisible = bool(
                self.ui.segmentation3DCheckBox.checked
            )
            segmentation2DOpacity = float(
                self.ui.segmentation2DOpacitySlider.value
            ) / 100.0
            segmentation3DOpacity = float(
                self.ui.segmentation3DOpacitySlider.value
            ) / 100.0
            renderingMode = (
                self.logic.SEGMENTATION_2D_RENDERING_MODE_SMOOTH
                if int(self.ui.segmentation2DRenderingModeComboBox.currentIndex)
                == 0
                else self.logic.SEGMENTATION_2D_RENDERING_MODE_NATIVE
            )

        sourceVolume = None
        if segmentationNode:
            try:
                sourceVolume = self.logic.getSegmentationSourceVolume(
                    segmentationNode
                )
            except ValueError:
                pass
        volumeDisplay = (
            self.logic.getScalarVolumeDisplaySettings(sourceVolume)
            if sourceVolume
            else {
                "autoWindowLevel": bool(
                    self.ui.cbctAutoWindowLevelCheckBox.checked
                ),
                "window": float(self._cbctWindowSlider.value)
                / self._displaySliderScale,
                "level": float(self._cbctLevelSlider.value)
                / self._displaySliderScale,
                "invertedGrayscale": bool(
                    self.ui.cbctInvertGrayscaleCheckBox.checked
                ),
            }
        )
        return {
            "version": 2,
            "scope": "DENTOWorkflowSceneDisplayParameters",
            "segmentation2DVisible": segmentation2DVisible,
            "segmentation3DVisible": segmentation3DVisible,
            "segmentation2DOpacity": segmentation2DOpacity,
            "segmentation3DOpacity": segmentation3DOpacity,
            "segmentation2DRenderingMode": renderingMode,
            "autoWindowLevel": bool(volumeDisplay["autoWindowLevel"]),
            "window": float(volumeDisplay["window"]),
            "level": float(volumeDisplay["level"]),
            "invertedGrayscale": bool(volumeDisplay["invertedGrayscale"]),
            "interpolate": bool(
                self.logic.getScalarVolumeInterpolation(sourceVolume)
                if sourceVolume
                else self.ui.cbctInterpolationCheckBox.checked
            ),
            "savedUtc": datetime.now(timezone.utc).isoformat(),
        }

    def onSaveSceneDisplayPreset(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode:
            return
        try:
            preset = self._currentSceneDisplayPreset()
            self._parameterNode.sceneDisplayPresetJson = json.dumps(
                preset,
                sort_keys=True,
                separators=(",", ":"),
            )
            self._applySceneDisplayPresetButton.enabled = True
            self._displayPresetStatusLabel.text = _(
                "Node-independent display parameters saved in this MRML scene at %1."
            ).replace("%1", preset["savedUtc"])
            self._displayPresetStatusLabel.styleSheet = "color: #207227;"
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onApplySceneDisplayPreset(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            preset = json.loads(self._parameterNode.sceneDisplayPresetJson)
            if not isinstance(preset, dict) or int(preset.get("version", 0)) not in {1, 2}:
                raise ValueError(_("The saved case display preset is invalid."))
            segmentationNode = self._reviewSegmentationNode
            if not segmentationNode:
                self._displayPresetStatusLabel.text = _(
                    "Display parameters are stored in this scene. Select an "
                    "authoritative segmentation to apply them."
                )
                self._displayPresetStatusLabel.styleSheet = "color: #b36b00;"
                return
            sourceVolume = None
            try:
                sourceVolume = self.logic.getSegmentationSourceVolume(
                    segmentationNode
                )
            except ValueError:
                pass

            activeWorkflowPreset = self._workflowViewActivePresetKey
            activeWorkflowKeys = set(self._workflowViewVisibleKeys)
            if self._workflowViewPriorState:
                self._restoreWorkflowViewState(updateUi=False)
            self.logic.setSegmentationVisibility2D(
                segmentationNode,
                bool(preset["segmentation2DVisible"]),
            )
            self.logic.setSegmentationVisibility3D(
                segmentationNode,
                bool(preset["segmentation3DVisible"]),
            )
            self.logic.setSegmentationOpacity2D(
                segmentationNode,
                float(preset["segmentation2DOpacity"]),
            )
            self.logic.setSegmentationOpacity3D(
                segmentationNode,
                float(preset["segmentation3DOpacity"]),
            )
            self.logic.setSegmentation2DRenderingMode(
                segmentationNode,
                str(preset["segmentation2DRenderingMode"]),
            )
            if sourceVolume:
                if bool(preset["autoWindowLevel"]):
                    self.logic.setScalarVolumeAutoWindowLevel(sourceVolume, True)
                else:
                    self.logic.setScalarVolumeWindowLevel(
                        sourceVolume,
                        float(preset["window"]),
                        float(preset["level"]),
                    )
                self.logic.setScalarVolumeInvertedGrayscale(
                    sourceVolume,
                    bool(preset["invertedGrayscale"]),
                )
                self.logic.setScalarVolumeInterpolation(
                    sourceVolume,
                    bool(preset["interpolate"]),
                )
            if activeWorkflowPreset == "custom":
                self._applyWorkflowViewKeys(
                    activeWorkflowKeys,
                    activePresetKey="custom",
                    updateStatus=False,
                )
            elif activeWorkflowPreset:
                self._applyWorkflowViewPreset(
                    activeWorkflowPreset,
                    updateStatus=False,
                )
            self._syncSegmentationDisplayControls()
            self._displayPresetStatusLabel.text = _(
                "Saved scene display parameters applied; source voxels and masks are unchanged."
                if sourceVolume
                else "Segmentation display parameters applied; CBCT grayscale settings "
                "remain stored until a referenced source volume is available."
            )
            self._displayPresetStatusLabel.styleSheet = "color: #207227;"
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onCbctInvertGrayscaleToggled(self, inverted: bool) -> None:
        if (
            self._updatingSegmentationReviewUI
            or not self._reviewSegmentationNode
            or not self.logic
        ):
            return
        with slicer.util.tryWithErrorDisplay(
            _("Could not change the source CBCT grayscale direction.")
        ):
            sourceVolume = self.logic.getSegmentationSourceVolume(
                self._reviewSegmentationNode
            )
            self.logic.setScalarVolumeInvertedGrayscale(
                sourceVolume,
                inverted,
            )
        self._syncSegmentationDisplayControls()

    def onRestoreLoadedCbctDisplay(self) -> None:
        if not self._reviewSegmentationNode or not self.logic:
            return
        with slicer.util.tryWithErrorDisplay(
            _("Could not restore the loaded source CBCT display settings.")
        ):
            sourceVolume = self.logic.getSegmentationSourceVolume(
                self._reviewSegmentationNode
            )
            baseline = self._loadedVolumeDisplaySettingsByNodeId.get(
                sourceVolume.GetID()
            )
            if not baseline:
                raise ValueError(
                    _("No loaded display baseline is available for this CBCT.")
                )
            self.logic.restoreScalarVolumeDisplaySettings(
                sourceVolume,
                baseline,
            )
        self._syncSegmentationDisplayControls()

    def _setSelectedSegmentDetailPlaceholders(self) -> None:
        for label in (
            self.ui.selectedAnatomyValueLabel,
            self.ui.selectedSourceLabelValueLabel,
            self.ui.selectedFdiValueLabel,
            self.ui.selectedLabelIdValueLabel,
            self.ui.selectedVoxelCountValueLabel,
            self.ui.selectedVolumeValueLabel,
            self.ui.selectedMetricsStatusValueLabel,
        ):
            label.text = _("--")

    def _setSegmentationProvenancePlaceholders(self) -> None:
        for label in (
            self.ui.provenanceRunIdValueLabel,
            self.ui.provenanceSourceVolumeValueLabel,
            self.ui.provenanceBackendValueLabel,
            self.ui.provenanceModelValueLabel,
            self.ui.provenanceDeviceValueLabel,
            self.ui.provenanceTimingValueLabel,
            self.ui.provenanceCompletedValueLabel,
            self.ui.reviewUpdatedValueLabel,
            self.ui.correctionActivityValueLabel,
        ):
            label.text = _("--")
        self.ui.reviewStateComboBox.setCurrentIndex(0)
        self.ui.provenanceWarningLabel.text = ""

    def _refreshSegmentationInspection(self) -> None:
        self._updateSelectedSegmentDetails(self._selectedReviewSegmentId())
        self._updateSegmentationProvenance()

    def _updateSelectedSegmentDetails(self, segmentId: str | None) -> None:
        if not segmentId or not self._reviewSegmentationNode or not self.logic:
            self._setSelectedSegmentDetailPlaceholders()
            return
        try:
            details = self.logic.getSegmentationSegmentDetails(
                self._reviewSegmentationNode,
                segmentId,
            )
        except ValueError:
            self._setSelectedSegmentDetailPlaceholders()
            return

        self.ui.selectedAnatomyValueLabel.text = details["displayName"]
        self.ui.selectedSourceLabelValueLabel.text = details["sourceName"]
        self.ui.selectedFdiValueLabel.text = (
            _("FDI %1").replace("%1", details["fdiNumber"])
            if details["fdiNumber"]
            else _("--")
        )
        self.ui.selectedLabelIdValueLabel.text = (
            str(details["labelId"])
            if details["labelId"] is not None
            else _("--")
        )
        self.ui.selectedVoxelCountValueLabel.text = (
            f"{int(details['voxelCount']):,}"
            if details["voxelCount"] is not None
            else _("--")
        )
        volumeMm3 = details["volumeMm3"]
        self.ui.selectedVolumeValueLabel.text = (
            f"{float(volumeMm3):,.2f} mm\u00b3 "
            f"({float(volumeMm3) / 1000.0:,.3f} cm\u00b3)"
            if volumeMm3 is not None
            else _("--")
        )
        if details["voxelCount"] is None or details["volumeMm3"] is None:
            metricsStatus = _("Inference metrics unavailable")
        elif details["metricsValidity"] == "current":
            metricsStatus = _("Current for imported inference result")
        else:
            metricsStatus = _("Baseline inference values retained for comparison")
        self.ui.selectedMetricsStatusValueLabel.text = metricsStatus

    def _updateSegmentationProvenance(self) -> None:
        if not self._reviewSegmentationNode or not self.logic:
            self._setSegmentationProvenancePlaceholders()
            return
        provenance = self.logic.getSegmentationProvenance(
            self._reviewSegmentationNode
        )
        self._updatingSegmentationReviewUI = True
        try:
            self.ui.provenanceRunIdValueLabel.text = provenance["runId"]
            self.ui.provenanceSourceVolumeValueLabel.text = provenance[
                "sourceVolume"
            ]
            self.ui.provenanceBackendValueLabel.text = provenance["backend"]
            self.ui.provenanceModelValueLabel.text = provenance["model"]
            self.ui.provenanceDeviceValueLabel.text = provenance["device"]
            self.ui.provenanceTimingValueLabel.text = provenance["timing"]
            self.ui.provenanceCompletedValueLabel.text = provenance[
                "completedAtUtc"
            ]
            self.ui.reviewStateComboBox.setCurrentIndex(
                self.logic.REVIEW_STATES.index(provenance["reviewState"])
            )
            self.ui.reviewUpdatedValueLabel.text = provenance[
                "reviewUpdatedUtc"
            ]
            self.ui.correctionActivityValueLabel.text = provenance[
                "correctionActivityUtc"
            ]
            warnings = []
            if self._reviewMetadataWarning:
                warnings.append(self._reviewMetadataWarning)
            if provenance["metricsValidity"] != "current":
                warnings.append(
                    _(
                        "Per-label voxel and volume values describe the "
                        "imported inference result and may not match corrected "
                        "masks."
                    )
                )
            self.ui.provenanceWarningLabel.text = " ".join(warnings)
        finally:
            self._updatingSegmentationReviewUI = False

    def onReviewStateChanged(self, index: int) -> None:
        if (
            self._updatingSegmentationReviewUI
            or not self._reviewSegmentationNode
            or not self.logic
        ):
            return
        if index < 0 or index >= len(self.logic.REVIEW_STATES):
            return
        state = self.logic.REVIEW_STATES[index]
        try:
            self.logic.setSegmentationReviewState(
                self._reviewSegmentationNode,
                state,
            )
            self._updateSegmentationProvenance()
            self.ui.segmentationReviewStatusLabel.text = (
                _("Workflow review state saved as %1.")
                .replace("%1", state)
            )
            self.ui.segmentationReviewStatusLabel.styleSheet = "color: #207227;"
            self._updateTemplateModeling()
        except ValueError as exc:
            slicer.util.errorDisplay(str(exc))
