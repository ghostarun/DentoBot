import colorsys
import json
import logging
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import qt
import vtk

import slicer
from slicer import (
    vtkMRMLMarkupsLineNode,
    vtkMRMLMarkupsROINode,
    vtkMRMLScalarVolumeNode,
    vtkMRMLSegmentationNode,
)
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.parameterNodeWrapper import parameterNodeWrapper
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleTest,
    ScriptedLoadableModuleWidget,
)
from slicer.util import VTKObservationMixin


@parameterNodeWrapper
class DENTOWorkflowParameterNode:
    """Persistent DENTOBOT workflow state stored in the MRML scene."""

    caseName: str = ""
    inputVolume: vtkMRMLScalarVolumeNode
    wslDistribution: str = ""
    wslPythonPath: str = ""
    stagingRoot: str = r"C:\DENTOBOTRuns"
    inferenceDevice: str = "cuda:0"
    roundTripVolume: vtkMRMLScalarVolumeNode
    teethSegmentation: vtkMRMLSegmentationNode
    targetToothSegmentId: str = ""
    targetToothBoundsRoi: vtkMRMLMarkupsROINode
    trajectoryLine: vtkMRMLMarkupsLineNode


class DENTOWorkflow(ScriptedLoadableModule):
    """DENTOBOT's focused case-imaging entry point."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.parent.title = _("DENTO Workflow")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "DENTOBOT")]
        self.parent.dependencies = ["DICOM"]
        self.parent.contributors = ["Taruneswar (IITM)"]
        self.parent.helpText = _(
            "DENTOBOT provides a focused workflow for opening a case, loading "
            "CBCT DICOM data through Slicer, running the external inference "
            "backend, and interactively reviewing the returned dental anatomy."
        )
        self.parent.acknowledgementText = _(
            "Developed as an academic research prototype at IIT Madras. "
            "This software is not validated for clinical use."
        )


class DENTOWorkflowWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Qt/MRML user interface for imaging and the external-compute bridge."""

    def __init__(self, parent=None) -> None:
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic: DENTOWorkflowLogic | None = None
        self._parameterNode: DENTOWorkflowParameterNode | None = None
        self._parameterNodeGuiTag = None
        self._sceneObserversActive = False
        self._volumeNodeIdsBeforeDICOM: set[str] | None = None
        self._lastDisplayedVolumeId: str | None = None
        self._backendProcess = None
        self._activeBackendRun: dict | None = None
        self._backendOutputLines: list[str] = []
        self._backendOutputBuffer = ""
        self._backendCancellationRequested = False
        self._reviewSegmentationNode = None
        self._reviewDisplayNode = None
        self._segmentReviewRecordsById: dict[str, dict] = {}
        self._reviewMetadataWarning = ""
        self._updatingSegmentationReviewUI = False
        self._processingSegmentationContentChange = False
        self._planningTrajectoryNode = None
        self._targetToothRecordsById: dict[str, dict] = {}
        self._updatingPlanningUI = False
        self._planningConstraintWarning = ""
        self._validTrajectoryPointsByNodeId: dict[str, list[list[float]]] = {}
        self._isCleaningUp = False

    def setup(self) -> None:
        super().setup()

        uiWidget = slicer.util.loadUI(self.resourcePath("UI/DENTOWorkflow.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        uiWidget.setMRMLScene(slicer.mrmlScene)

        self.logic = DENTOWorkflowLogic()
        if os.name != "nt":
            self.ui.wslDistributionLabel.visible = False
            self.ui.wslDistributionLineEdit.visible = False
            self.ui.wslPythonPathLabel.text = _("Backend Python:")
            self.ui.wslPythonPathLineEdit.toolTip = _(
                "Absolute path to the dedicated DENTOBOT backend Python in this container."
            )
            self.ui.stagingRootLineEdit.toolTip = _(
                "Absolute Linux directory for isolated NIfTI and JSON artifacts."
            )
            self.ui.backendDescriptionLabel.text = _(
                "Slicer owns UI and MRML. A separate Python environment in the "
                "Ubuntu container owns dependency-heavy inference."
            )
            self.ui.checkBackendButton.text = _("Check Ubuntu Backend")
            self.ui.roundTripButton.toolTip = _(
                "Export the selected volume to NIfTI, rewrite it in the "
                "isolated Ubuntu backend, validate it, and import it."
            )
            self.ui.segmentTeethButton.text = _("Run Teeth Segmentation (CPU)")

        self.ui.newCaseButton.connect("clicked(bool)", self.onNewCase)
        self.ui.openSceneButton.connect("clicked(bool)", self.onOpenScene)
        self.ui.openDicomButton.connect("clicked(bool)", self.onOpenDicomBrowser)
        self.ui.showVolumeButton.connect("clicked(bool)", self.onShowSelectedVolume)
        self.ui.inputVolumeSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onInputVolumeSelectionChanged,
        )
        self.ui.checkBackendButton.connect("clicked(bool)", self.onCheckBackend)
        self.ui.roundTripButton.connect("clicked(bool)", self.onRunRoundTrip)
        self.ui.segmentTeethButton.connect("clicked(bool)", self.onRunTeethSegmentation)
        self.ui.cancelBackendButton.connect("clicked(bool)", self.onCancelBackend)
        self.ui.reviewSegmentationSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onReviewSegmentationSelectionChanged,
        )
        self.ui.segmentSearchLineEdit.connect(
            "textChanged(QString)",
            self.onSegmentSearchTextChanged,
        )
        self.ui.segmentTreeWidget.connect(
            "itemChanged(QTreeWidgetItem*,int)",
            self.onSegmentTreeItemChanged,
        )
        self.ui.segmentTreeWidget.connect(
            "currentItemChanged(QTreeWidgetItem*,QTreeWidgetItem*)",
            self.onSegmentTreeCurrentItemChanged,
        )
        self.ui.showAllSegmentsButton.connect("clicked(bool)", self.onShowAllSegments)
        self.ui.hideAllSegmentsButton.connect("clicked(bool)", self.onHideAllSegments)
        self.ui.isolateSegmentButton.connect("clicked(bool)", self.onIsolateSelectedSegment)
        self.ui.editSelectedSegmentButton.connect(
            "clicked(bool)",
            self.onEditSelectedSegment,
        )
        self.ui.segmentation2DCheckBox.connect(
            "toggled(bool)",
            self.onSegmentation2DVisibilityToggled,
        )
        self.ui.segmentation3DCheckBox.connect(
            "toggled(bool)",
            self.onSegmentation3DVisibilityToggled,
        )
        self.ui.segmentation2DOpacitySlider.connect(
            "valueChanged(int)",
            self.onSegmentation2DOpacityChanged,
        )
        self.ui.segmentation3DOpacitySlider.connect(
            "valueChanged(int)",
            self.onSegmentation3DOpacityChanged,
        )
        self.ui.reviewStateComboBox.connect(
            "currentIndexChanged(int)",
            self.onReviewStateChanged,
        )
        self.ui.targetToothComboBox.connect(
            "currentIndexChanged(int)",
            self.onTargetToothChanged,
        )
        self.ui.trajectorySelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onTrajectorySelectionChanged,
        )
        self.ui.createTrajectoryButton.connect(
            "clicked(bool)",
            self.onCreateTrajectory,
        )
        self.ui.placeTrajectoryButton.connect(
            "clicked(bool)",
            self.onPlaceTrajectory,
        )
        self.ui.undoTrajectoryPointButton.connect(
            "clicked(bool)",
            self.onUndoTrajectoryPoint,
        )
        self.ui.resetTrajectoryButton.connect(
            "clicked(bool)",
            self.onResetTrajectory,
        )
        self.ui.lockTrajectoryButton.connect(
            "toggled(bool)",
            self.onTrajectoryLockToggled,
        )

        self._addSceneObservers()
        self.initializeParameterNode()

    def cleanup(self) -> None:
        self._isCleaningUp = True
        self._cancelBackendProcess(updateStatus=False)
        self.setParameterNode(None)
        self.removeObservers()
        self._sceneObserversActive = False

    def enter(self) -> None:
        self._addSceneObservers()
        self.initializeParameterNode()

    def exit(self) -> None:
        self.setParameterNode(None)
        self._removeSceneObservers()

    def _addSceneObservers(self) -> None:
        if self._sceneObserversActive:
            return
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        self._sceneObserversActive = True

    def _removeSceneObservers(self) -> None:
        if not self._sceneObserversActive:
            return
        self.removeObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.removeObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        self._sceneObserversActive = False

    def onSceneStartClose(self, caller=None, event=None) -> None:
        self._cancelBackendProcess(
            updateStatus=True,
            message=_("Backend process cancelled because the scene is closing."),
        )
        self.setParameterNode(None)
        self._lastDisplayedVolumeId = None

    def onSceneEndClose(self, caller=None, event=None) -> None:
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        if not self.logic:
            return

        self.setParameterNode(self.logic.getParameterNode())
        if os.name != "nt":
            if not self._parameterNode.wslPythonPath:
                self._parameterNode.wslPythonPath = "/opt/dentobot-venv/bin/python"
            if self._parameterNode.stagingRoot == r"C:\DENTOBOTRuns":
                self._parameterNode.stagingRoot = "/workspace/data/dentobot-runs"
            if self._parameterNode.inferenceDevice == "cuda:0":
                self._parameterNode.inferenceDevice = "cpu"

        newlyLoadedVolume = self._newlyLoadedDicomVolume()
        if newlyLoadedVolume:
            self._parameterNode.inputVolume = newlyLoadedVolume
        elif not self._parameterNode.inputVolume:
            latestVolume = self.logic.getLatestScalarVolumeNode()
            if latestVolume:
                self._parameterNode.inputVolume = latestVolume
        if not self._parameterNode.teethSegmentation:
            latestSegmentation = self.logic.getLatestTeethSegmentationNode()
            if latestSegmentation:
                self._parameterNode.teethSegmentation = latestSegmentation

        self._updateFromParameterNode()

    def setParameterNode(self, parameterNode: DENTOWorkflowParameterNode | None) -> None:
        if self._parameterNode:
            if self._parameterNodeGuiTag is not None:
                self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._updateFromParameterNode)

        self._parameterNode = parameterNode
        self._parameterNodeGuiTag = None

        if self._parameterNode:
            self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._updateFromParameterNode)
            self._updateFromParameterNode()
        else:
            self._bindSegmentationReviewNode(None)
            self._clearSegmentationReview()
            self._bindPlanningTrajectoryNode(None)
            self._clearPlanning()

    def _newlyLoadedDicomVolume(self) -> vtkMRMLScalarVolumeNode | None:
        if self._volumeNodeIdsBeforeDICOM is None or not self.logic:
            return None

        previousNodeIds = self._volumeNodeIdsBeforeDICOM
        self._volumeNodeIdsBeforeDICOM = None
        newVolumes = [
            node for node in self.logic.getScalarVolumeNodes()
            if node.GetID() not in previousNodeIds
        ]
        return newVolumes[-1] if newVolumes else None

    def _updateFromParameterNode(self, caller=None, event=None) -> None:
        if not self._parameterNode or not self.logic:
            return

        volumeNode = self._parameterNode.inputVolume
        self.ui.showVolumeButton.enabled = volumeNode is not None
        self._updateBackendControls()
        self._bindSegmentationReviewNode(self._parameterNode.teethSegmentation)
        self._updateSegmentationReview()
        self._bindPlanningTrajectoryNode(self._parameterNode.trajectoryLine)
        self._updatePlanning()

        if not volumeNode:
            self._setMetadataPlaceholders()
            self.ui.statusLabel.text = _("No CBCT volume selected.")
            self.ui.statusLabel.styleSheet = "color: #b36b00;"
            self._lastDisplayedVolumeId = None
            return

        try:
            metadata = self.logic.getVolumeMetadata(volumeNode)
        except ValueError as exc:
            self._setMetadataPlaceholders()
            self.ui.statusLabel.text = str(exc)
            self.ui.statusLabel.styleSheet = "color: #b00020;"
            return

        self.ui.volumeNameValueLabel.text = metadata["name"]
        self.ui.dimensionsValueLabel.text = metadata["dimensions"]
        self.ui.spacingValueLabel.text = metadata["spacing"]
        self.ui.scalarTypeValueLabel.text = metadata["scalarType"]
        self.ui.scalarRangeValueLabel.text = metadata["scalarRange"]
        self.ui.orientationValueLabel.text = metadata["orientation"]
        self.ui.geometryStatusValueLabel.text = metadata["geometryStatus"]
        self.ui.statusLabel.text = _("Ready. The selected volume is available for inspection.")
        self.ui.statusLabel.styleSheet = "color: #207227;"

        if volumeNode.GetID() != self._lastDisplayedVolumeId:
            self._showVolumeInSliceViews(volumeNode)

    def _bindSegmentationReviewNode(self, segmentationNode) -> None:
        """Observe the selected segmentation and its display state exactly once."""

        if segmentationNode is self._reviewSegmentationNode:
            displayNode = segmentationNode.GetDisplayNode() if segmentationNode else None
            if displayNode is self._reviewDisplayNode:
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

        self._reviewSegmentationNode = segmentationNode
        self._reviewDisplayNode = None

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

    def _onReviewSegmentationModified(self, caller=None, event=None) -> None:
        if not self._updatingSegmentationReviewUI:
            self._rebuildSegmentTree()
            self._refreshSegmentationInspection()
            self._updatePlanning()

    def _onReviewDisplayModified(self, caller=None, event=None) -> None:
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
            self._setSelectedSegmentDetailPlaceholders()
            self._setSegmentationProvenancePlaceholders()
            self._reviewMetadataWarning = ""
            self.ui.segmentationReviewStatusLabel.text = _(
                "Select a segmentation to review."
            )
            self.ui.segmentationReviewStatusLabel.styleSheet = "color: #b36b00;"
            self._setSegmentationReviewControlsEnabled(False)
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
            self.ui.reviewStateComboBox,
        ):
            widget.enabled = enabled
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
        finally:
            self._updatingSegmentationReviewUI = False
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
        if not self._parameterNode:
            return
        currentNode = self._parameterNode.teethSegmentation
        currentNodeId = currentNode.GetID() if currentNode else None
        selectedNodeId = segmentationNode.GetID() if segmentationNode else None
        if currentNodeId != selectedNodeId:
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
            self._parameterNode.teethSegmentation = segmentationNode
        self._bindSegmentationReviewNode(segmentationNode)
        self._updateSegmentationReview()
        # Parameter-node GUI bindings do not guarantee that the planning
        # refresh observer runs after this selection callback on every Slicer
        # version. Refresh Step 4A explicitly so existing segmentations become
        # immediately available to the target-tooth selector.
        self._updatePlanning()

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
        except ValueError as exc:
            slicer.util.errorDisplay(str(exc))

    def _bindPlanningTrajectoryNode(self, trajectoryNode) -> None:
        """Observe the selected trajectory once so measurements stay current."""

        if trajectoryNode is self._planningTrajectoryNode:
            return
        if self._planningTrajectoryNode:
            for trajectoryEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.removeObserver(
                    self._planningTrajectoryNode,
                    trajectoryEvent,
                    self._onPlanningTrajectoryModified,
                )
        self._planningTrajectoryNode = trajectoryNode
        if trajectoryNode:
            for trajectoryEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.addObserver(
                    trajectoryNode,
                    trajectoryEvent,
                    self._onPlanningTrajectoryModified,
                )

    def _onPlanningTrajectoryModified(self, caller=None, event=None) -> None:
        del caller, event
        if self._updatingPlanningUI or not self.logic:
            return
        self._updatingPlanningUI = True
        try:
            if self._planningTrajectoryNode:
                self.logic.labelTrajectoryControlPoints(
                    self._planningTrajectoryNode
                )
                self._enforceTrajectoryBounds(
                    self._planningTrajectoryNode
                )
        finally:
            self._updatingPlanningUI = False
        self._updatePlanning()

    def _ensureTargetBounds(
        self,
        segmentationNode,
        targetRecord: dict,
    ) -> tuple[float, ...] | None:
        """Create/update the visible active-tooth AABB and persist its node."""

        if not self._parameterNode or not self.logic:
            return None
        try:
            roiNode, bounds = self.logic.createOrUpdateTargetBoundsRoi(
                segmentationNode,
                targetRecord["segmentId"],
                self._parameterNode.targetToothBoundsRoi,
            )
        except (RuntimeError, ValueError) as exc:
            self._planningConstraintWarning = str(exc)
            self.ui.targetBoundsValueLabel.text = _("--")
            return None

        if self._parameterNode.targetToothBoundsRoi is not roiNode:
            self._parameterNode.targetToothBoundsRoi = roiNode
        self.ui.targetBoundsValueLabel.text = (
            self.logic.formatRasBounds(bounds)
        )
        trajectoryNode = self._parameterNode.trajectoryLine
        if trajectoryNode:
            if trajectoryNode.GetNodeReference(
                self.logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE
            ) is not roiNode:
                trajectoryNode.SetNodeReferenceID(
                    self.logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
                    roiNode.GetID(),
                )
        return bounds

    def _enforceTrajectoryBounds(self, trajectoryNode) -> bool:
        """Reject or restore any trajectory point outside the target-tooth AABB."""

        if (
            not trajectoryNode
            or not self._parameterNode
            or not self.logic
            or not self._parameterNode.teethSegmentation
            or not self._parameterNode.targetToothSegmentId
        ):
            return True
        try:
            report = self.logic.getTrajectoryBoundsReport(
                trajectoryNode,
                self._parameterNode.teethSegmentation,
                self._parameterNode.targetToothSegmentId,
            )
        except ValueError as exc:
            self._planningConstraintWarning = str(exc)
            return False

        invalidIndices = report["invalidPointIndices"]
        if not invalidIndices:
            summary = report["summary"]
            currentPoints = [
                list(point)
                for point in (
                    summary["entryRas"],
                    summary["targetRas"],
                )
                if point is not None
            ]
            previousPoints = self._validTrajectoryPointsByNodeId.get(
                trajectoryNode.GetID(),
                [],
            )
            if (
                not self._planningConstraintWarning
                or currentPoints != previousPoints
            ):
                self._planningConstraintWarning = ""
            self._validTrajectoryPointsByNodeId[
                trajectoryNode.GetID()
            ] = currentPoints
            return True

        previousPoints = self._validTrajectoryPointsByNodeId.get(
            trajectoryNode.GetID(),
            [],
        )
        bounds = report["bounds"]
        wasModifying = trajectoryNode.StartModify()
        try:
            for pointIndex in sorted(invalidIndices, reverse=True):
                previousPoint = (
                    previousPoints[pointIndex]
                    if pointIndex < len(previousPoints)
                    else None
                )
                if (
                    previousPoint is not None
                    and self.logic.isRasPointWithinBounds(
                        previousPoint,
                        bounds,
                    )
                ):
                    trajectoryNode.SetNthControlPointPositionWorld(
                        pointIndex,
                        previousPoint,
                    )
                else:
                    trajectoryNode.RemoveNthControlPoint(pointIndex)
        finally:
            trajectoryNode.EndModify(wasModifying)

        rejectedNames = ", ".join(
            ("Entry", "Target")[index] for index in invalidIndices
        )
        self._planningConstraintWarning = (
            _(
                "%1 was outside the selected tooth bounds and was rejected. "
                "Place both points inside the orange target box."
            ).replace("%1", rejectedNames)
        )
        return False

    def _applyTargetPriorityHighlight(self) -> None:
        """Keep the Step 4A target dominant over Step 3 review selection."""

        if (
            not self._parameterNode
            or not self.logic
            or not self._parameterNode.teethSegmentation
        ):
            return
        segmentationNode = self._parameterNode.teethSegmentation
        targetId = self._parameterNode.targetToothSegmentId
        if targetId in self._targetToothRecordsById:
            self.logic.setSegmentationVisibility2D(segmentationNode, True)
            self.logic.setSegmentationVisibility3D(segmentationNode, True)
            self.logic.setSegmentationSegmentVisibility(
                segmentationNode,
                targetId,
                True,
            )
            self.logic.setSegmentationSegmentHighlight(
                segmentationNode,
                targetId,
            )
            treeWidget = self.ui.segmentTreeWidget
            targetItem = None
            for groupIndex in range(treeWidget.topLevelItemCount):
                groupItem = treeWidget.topLevelItem(groupIndex)
                for childIndex in range(groupItem.childCount()):
                    item = groupItem.child(childIndex)
                    if str(item.data(0, qt.Qt.UserRole)) == targetId:
                        targetItem = item
                        break
                if targetItem:
                    break
            if targetItem and treeWidget.currentItem() is not targetItem:
                self._updatingSegmentationReviewUI = True
                try:
                    treeWidget.setCurrentItem(targetItem)
                finally:
                    self._updatingSegmentationReviewUI = False
                self._updateSelectedSegmentDetails(targetId)
        else:
            selectedId = self._selectedReviewSegmentId()
            self.logic.setSegmentationSegmentHighlight(
                segmentationNode,
                selectedId,
            )

    def _clearPlanning(self) -> None:
        if not hasattr(self, "ui"):
            return
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
            self.ui.lockTrajectoryButton.enabled = False
            self.ui.lockTrajectoryButton.checked = False
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

    def _updatePlanning(self) -> None:
        if not self._parameterNode or not self.logic:
            self._clearPlanning()
            return

        segmentationNode = self._parameterNode.teethSegmentation
        if not segmentationNode:
            self._clearPlanning()
            return

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

        trajectoryNode = self._parameterNode.trajectoryLine
        self._bindPlanningTrajectoryNode(trajectoryNode)
        if targetRecord and trajectoryNode:
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
        finally:
            self._updatingPlanningUI = False
        self._updateTrajectoryDetails(trajectoryNode)
        self._updatePlanningStatus(
            segmentationNode,
            targetRecord,
            trajectoryNode,
        )

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

    def onTargetToothChanged(self, index: int) -> None:
        if self._updatingPlanningUI or not self._parameterNode or not self.logic:
            return
        segmentId = (
            str(self.ui.targetToothComboBox.itemData(index))
            if index >= 0 and self.ui.targetToothComboBox.itemData(index)
            else ""
        )
        trajectoryNode = self._parameterNode.trajectoryLine
        if trajectoryNode:
            self._validTrajectoryPointsByNodeId.pop(
                trajectoryNode.GetID(),
                None,
            )
        self._planningConstraintWarning = ""
        self._parameterNode.targetToothSegmentId = segmentId
        if not segmentId and trajectoryNode:
            self.logic.clearTrajectoryTarget(
                trajectoryNode
            )
            trajectoryNode.SetNodeReferenceID(
                self.logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
                None,
            )
        elif segmentId and trajectoryNode:
            try:
                self.logic.configureTrajectoryTarget(
                    trajectoryNode,
                    self._parameterNode.teethSegmentation,
                    segmentId,
                )
            except ValueError as exc:
                slicer.util.errorDisplay(str(exc))
        self._updatePlanning()
        self._applyTargetPriorityHighlight()

    def onTrajectorySelectionChanged(self, trajectoryNode) -> None:
        if not self._parameterNode or not self.logic:
            return
        currentNode = self._parameterNode.trajectoryLine
        currentNodeId = currentNode.GetID() if currentNode else None
        selectedNodeId = trajectoryNode.GetID() if trajectoryNode else None
        if currentNodeId != selectedNodeId:
            self._parameterNode.trajectoryLine = trajectoryNode
            if currentNodeId:
                self._validTrajectoryPointsByNodeId.pop(
                    currentNodeId,
                    None,
                )
        self._bindPlanningTrajectoryNode(trajectoryNode)
        targetId = self._parameterNode.targetToothSegmentId
        if trajectoryNode and targetId:
            try:
                self.logic.configureTrajectoryTarget(
                    trajectoryNode,
                    self._parameterNode.teethSegmentation,
                    targetId,
                )
            except ValueError as exc:
                slicer.util.errorDisplay(str(exc))
        self._updatePlanning()

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
        if not slicer.util.confirmYesNoDisplay(
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
            trajectoryNode.SetLocked(False)
        self._updatePlanning()

    def _setMetadataPlaceholders(self) -> None:
        for label in (
            self.ui.volumeNameValueLabel,
            self.ui.dimensionsValueLabel,
            self.ui.spacingValueLabel,
            self.ui.scalarTypeValueLabel,
            self.ui.scalarRangeValueLabel,
            self.ui.orientationValueLabel,
            self.ui.geometryStatusValueLabel,
        ):
            label.text = _("--")

    def _showVolumeInSliceViews(self, volumeNode: vtkMRMLScalarVolumeNode) -> None:
        slicer.util.setSliceViewerLayers(background=volumeNode, fit=True)
        self._lastDisplayedVolumeId = volumeNode.GetID()

    def onShowSelectedVolume(self) -> None:
        if not self._parameterNode or not self._parameterNode.inputVolume:
            return
        with slicer.util.tryWithErrorDisplay(_("Could not display the selected volume.")):
            self._showVolumeInSliceViews(self._parameterNode.inputVolume)

    def onInputVolumeSelectionChanged(self, volumeNode) -> None:
        """Keep the visible selector authoritative and persist its exact node."""

        if not self._parameterNode:
            return
        parameterVolume = self._parameterNode.inputVolume
        parameterVolumeId = parameterVolume.GetID() if parameterVolume else None
        selectedVolumeId = volumeNode.GetID() if volumeNode else None
        if parameterVolumeId != selectedVolumeId:
            self._parameterNode.inputVolume = volumeNode
        self._updateBackendControls()

    def onOpenDicomBrowser(self) -> None:
        if not self.logic:
            return
        self._volumeNodeIdsBeforeDICOM = {
            node.GetID() for node in self.logic.getScalarVolumeNodes()
        }
        self.ui.statusLabel.text = _(
            "Opening Slicer's DICOM browser. Load a series, then return to DENTO Workflow."
        )
        slicer.util.selectModule("DICOM")

    def onOpenScene(self) -> None:
        scenePath = qt.QFileDialog.getOpenFileName(
            slicer.util.mainWindow(),
            _("Open DENTOBOT scene"),
            "",
            _("Slicer scene or bundle (*.mrml *.mrb);;All files (*)"),
        )
        if isinstance(scenePath, tuple):
            scenePath = scenePath[0]
        if not scenePath:
            return

        with slicer.util.tryWithErrorDisplay(_("Could not open the selected DENTOBOT scene."), waitCursor=True):
            slicer.util.loadScene(scenePath)

    def onNewCase(self) -> None:
        confirmed = slicer.util.confirmYesNoDisplay(
            _(
                "This removes all nodes from the current Slicer scene. "
                "Original DICOM files on disk are not modified. Save the current scene first if needed."
            ),
            windowTitle=_("Start a new DENTOBOT case?"),
        )
        if not confirmed:
            return

        slicer.mrmlScene.Clear(0)
        logging.info("Started a new empty DENTOBOT scene")

    def _backendConfiguration(self) -> tuple[str, str, str, str, str]:
        if not self._parameterNode:
            return "", "", "", "", ""
        return (
            "wsl" if os.name == "nt" else "local",
            self._parameterNode.wslDistribution.strip(),
            self._parameterNode.wslPythonPath.strip(),
            self._parameterNode.stagingRoot.strip(),
            self._parameterNode.inferenceDevice.strip(),
        )

    def _backendIsRunning(self) -> bool:
        return self._backendProcess is not None

    def _updateBackendControls(self) -> None:
        if not self._parameterNode:
            return
        executionMode, distribution, pythonPath, stagingRoot, _device = (
            self._backendConfiguration()
        )
        configured = bool(
            pythonPath and (executionMode == "local" or distribution)
        )
        running = self._backendIsRunning()
        self.ui.checkBackendButton.enabled = configured and not running
        self.ui.roundTripButton.enabled = bool(
            configured
            and stagingRoot
            and self._parameterNode.inputVolume
            and not running
        )
        self.ui.segmentTeethButton.enabled = bool(
            configured
            and stagingRoot
            and self._parameterNode.inputVolume
            and not running
        )
        self.ui.cancelBackendButton.enabled = running

        inputVolume = self.ui.inputVolumeSelector.currentNode()
        self.ui.bridgeInputValueLabel.text = (
            inputVolume.GetName() if inputVolume else _("--")
        )
        roundTripVolume = self._parameterNode.roundTripVolume
        self.ui.roundTripOutputValueLabel.text = (
            roundTripVolume.GetName() if roundTripVolume else _("--")
        )
        teethSegmentation = self._parameterNode.teethSegmentation
        self.ui.teethSegmentationValueLabel.text = (
            teethSegmentation.GetName() if teethSegmentation else _("--")
        )
        self.ui.teethMetricsValueLabel.text = self._teethMetricsText(
            teethSegmentation
        )

    @staticmethod
    def _teethMetricsText(segmentationNode) -> str:
        if not segmentationNode:
            return _("--")
        segmentCount = segmentationNode.GetAttribute("DENTOBOT.SegmentCount")
        runtimeSeconds = segmentationNode.GetAttribute("DENTOBOT.RuntimeSeconds")
        foregroundVolumeMm3 = segmentationNode.GetAttribute(
            "DENTOBOT.ForegroundVolumeMm3"
        )
        peakAllocatedBytes = segmentationNode.GetAttribute(
            "DENTOBOT.PeakAllocatedBytes"
        )
        if not all((segmentCount, runtimeSeconds, foregroundVolumeMm3)):
            return _("Metrics unavailable")
        device = segmentationNode.GetAttribute("DENTOBOT.ActualDevice") or _("unknown")
        memoryText = ""
        if peakAllocatedBytes and peakAllocatedBytes.lower() not in ("none", "null"):
            memoryText = (
                f"; {float(peakAllocatedBytes) / (1024.0 ** 3):.2f} GiB peak GPU"
            )
        return (
            _("%1 segments; %2 s; %3 cm^3 foreground; %4%5")
            .replace("%1", segmentCount)
            .replace("%2", f"{float(runtimeSeconds):.1f}")
            .replace("%3", f"{float(foregroundVolumeMm3) / 1000.0:.2f}")
            .replace("%4", device)
            .replace("%5", memoryText)
        )

    def _setBackendStatus(self, message: str, state: str = "neutral") -> None:
        colors = {
            "neutral": "#555555",
            "working": "#1f5f99",
            "success": "#207227",
            "warning": "#b36b00",
            "error": "#b00020",
        }
        self.ui.backendStatusLabel.text = message
        self.ui.backendStatusLabel.styleSheet = f"color: {colors[state]};"

    def _appendBackendLog(self, line: str) -> None:
        cleanedLine = line.rstrip()
        if not cleanedLine:
            return
        self._backendOutputLines.append(cleanedLine)
        if len(self._backendOutputLines) > 2000:
            del self._backendOutputLines[:-2000]
        self.ui.backendLogTextEdit.appendPlainText(cleanedLine)
        try:
            progressEvent = json.loads(cleanedLine)
        except json.JSONDecodeError:
            progressEvent = None
        if (
            isinstance(progressEvent, dict)
            and progressEvent.get("event") == "progress"
            and progressEvent.get("message")
        ):
            self._setBackendStatus(str(progressEvent["message"]), "working")

    def _validateBackendConfiguration(
        self,
        requireStagingRoot: bool,
    ) -> tuple[str, str, str, str, str]:
        executionMode, distribution, pythonPath, stagingRoot, device = (
            self._backendConfiguration()
        )
        if executionMode == "wsl" and not distribution:
            raise ValueError(_("Enter the exact WSL distribution name."))
        if not pythonPath.startswith("/"):
            raise ValueError(
                _("Enter an absolute Linux path to the DENTOBOT Conda environment's Python.")
            )
        if requireStagingRoot:
            self.logic.validateStagingRoot(stagingRoot, executionMode)
        if device not in ("cpu", "cuda:0"):
            raise ValueError(_("Inference device must be cpu or cuda:0."))
        return executionMode, distribution, pythonPath, stagingRoot, device

    def _startBackendProcess(
        self,
        arguments: list[str],
        operation: str,
        runId: str,
        runContext: dict | None = None,
    ) -> None:
        if self._backendIsRunning():
            raise RuntimeError(_("Another DENTOBOT backend process is already running."))

        self._backendOutputLines = []
        self._backendOutputBuffer = ""
        self.ui.backendLogTextEdit.clear()
        self._backendCancellationRequested = False
        self._activeBackendRun = {
            "operation": operation,
            "runId": runId,
            **(runContext or {}),
        }
        self._setBackendStatus(_("Starting inference backend..."), "working")

        def logCallback(line: str) -> None:
            if self._activeBackendRun and self._activeBackendRun["runId"] == runId:
                self._appendBackendLog(line)

        def completedCallback(returnCode: int) -> None:
            self._onBackendCompleted(runId, int(returnCode))

        try:
            try:
                self._backendProcess = slicer.util.launchConsoleProcess(
                    arguments,
                    useStartupEnvironment=True,
                    blocking=False,
                    logCallback=logCallback,
                    completedCallback=completedCallback,
                )
            except TypeError as exc:
                if "unexpected keyword argument" not in str(exc):
                    raise
                process = qt.QProcess()
                process.setProcessChannelMode(qt.QProcess.MergedChannels)
                processEnvironment = qt.QProcessEnvironment()
                for environmentName, environmentValue in (
                    slicer.util.startupEnvironment().items()
                ):
                    processEnvironment.insert(
                        str(environmentName),
                        str(environmentValue),
                    )
                process.setProcessEnvironment(processEnvironment)

                def drainOutput() -> None:
                    rawOutput = process.readAllStandardOutput().data()
                    if isinstance(rawOutput, str):
                        chunk = rawOutput
                    else:
                        chunk = rawOutput.decode("utf-8", errors="replace")
                    self._backendOutputBuffer += chunk
                    completeLines = self._backendOutputBuffer.splitlines(
                        keepends=True
                    )
                    self._backendOutputBuffer = ""
                    for outputLine in completeLines:
                        if outputLine.endswith(("\n", "\r")):
                            logCallback(outputLine.rstrip("\r\n"))
                        else:
                            self._backendOutputBuffer = outputLine

                def processFinished(
                    returnCode: int,
                    _exitStatus,
                ) -> None:
                    drainOutput()
                    if self._backendOutputBuffer:
                        logCallback(self._backendOutputBuffer)
                        self._backendOutputBuffer = ""
                    completedCallback(returnCode)

                process.connect(
                    "readyReadStandardOutput()",
                    drainOutput,
                )
                process.connect(
                    "finished(int,QProcess::ExitStatus)",
                    processFinished,
                )
                process.start(arguments[0], arguments[1:])
                if not process.waitForStarted(5000):
                    raise RuntimeError(
                        _("The inference backend process could not be started.")
                    )
                self._backendProcess = process
        except Exception:
            self._activeBackendRun = None
            self._backendCancellationRequested = False
            self._backendProcess = None
            self._updateBackendControls()
            raise
        self._updateBackendControls()

    def onCheckBackend(self) -> None:
        if not self.logic:
            return
        with slicer.util.tryWithErrorDisplay(
            _("Could not start the DENTOBOT backend health check.")
        ):
            executionMode, distribution, pythonPath, _stagingRoot, device = self._validateBackendConfiguration(
                requireStagingRoot=False
            )
            runId = uuid.uuid4().hex
            arguments = self.logic.buildHealthCommand(
                distribution=distribution,
                pythonPath=pythonPath,
                executionMode=executionMode,
                device=device,
            )
            self._startBackendProcess(
                arguments,
                "health",
                runId,
                {"device": device},
            )

    def onRunRoundTrip(self) -> None:
        if not self.logic or not self._parameterNode:
            return
        with slicer.util.tryWithErrorDisplay(
            _("Could not start the DENTOBOT NIfTI round trip."),
            waitCursor=True,
        ):
            volumeNode = self.ui.inputVolumeSelector.currentNode()
            if not volumeNode or not volumeNode.IsA("vtkMRMLScalarVolumeNode"):
                raise ValueError(_("Select a scalar CBCT volume first."))
            if (
                not self._parameterNode.inputVolume
                or self._parameterNode.inputVolume.GetID() != volumeNode.GetID()
            ):
                self._parameterNode.inputVolume = volumeNode
            if volumeNode.GetParentTransformNode():
                raise ValueError(
                    _(
                        "The selected volume has a parent transform. "
                        "Handle or harden that transform explicitly before this bridge test."
                    )
                )

            executionMode, distribution, pythonPath, stagingRoot, _device = self._validateBackendConfiguration(
                requireStagingRoot=True
            )
            self._setBackendStatus(
                _("Preparing the explicitly selected volume: %1")
                .replace("%1", volumeNode.GetName() or _("Unnamed volume")),
                "working",
            )
            runId = uuid.uuid4().hex
            runPaths = self.logic.createRoundTripRunPaths(
                stagingRoot,
                runId,
                executionMode=executionMode,
            )
            exported = slicer.util.exportNode(volumeNode, str(runPaths["input"]))
            if not exported or not runPaths["input"].is_file():
                raise RuntimeError(_("Slicer could not export the selected volume as NIfTI."))

            arguments = self.logic.buildRoundTripCommand(
                distribution=distribution,
                pythonPath=pythonPath,
                inputPath=runPaths["input"],
                outputPath=runPaths["output"],
                resultJsonPath=runPaths["result"],
                runId=runId,
                executionMode=executionMode,
            )
            self._startBackendProcess(
                arguments,
                "roundtrip",
                runId,
                {
                    "paths": runPaths,
                    "sourceVolumeId": volumeNode.GetID(),
                },
            )

    def onRunTeethSegmentation(self) -> None:
        if not self.logic or not self._parameterNode:
            return
        with slicer.util.tryWithErrorDisplay(
            _("Could not start DENTOBOT teeth segmentation."),
            waitCursor=True,
        ):
            volumeNode = self.ui.inputVolumeSelector.currentNode()
            if not volumeNode or not volumeNode.IsA("vtkMRMLScalarVolumeNode"):
                raise ValueError(_("Select a scalar CBCT volume first."))
            if (
                not self._parameterNode.inputVolume
                or self._parameterNode.inputVolume.GetID() != volumeNode.GetID()
            ):
                self._parameterNode.inputVolume = volumeNode
            if volumeNode.GetParentTransformNode():
                raise ValueError(
                    _(
                        "The selected volume has a parent transform. "
                        "Handle or harden that transform before segmentation."
                    )
                )

            executionMode, distribution, pythonPath, stagingRoot, device = self._validateBackendConfiguration(
                requireStagingRoot=True
            )
            self._setBackendStatus(
                _("Exporting %1 for teeth segmentation on %2...")
                .replace("%1", volumeNode.GetName() or _("Unnamed volume"))
                .replace("%2", device),
                "working",
            )
            runId = uuid.uuid4().hex
            runPaths = self.logic.createTeethSegmentationRunPaths(
                stagingRoot,
                runId,
                executionMode=executionMode,
            )
            exported = slicer.util.exportNode(volumeNode, str(runPaths["input"]))
            if not exported or not runPaths["input"].is_file():
                raise RuntimeError(
                    _("Slicer could not export the selected CBCT as NIfTI.")
                )

            arguments = self.logic.buildTeethSegmentationCommand(
                distribution=distribution,
                pythonPath=pythonPath,
                inputPath=runPaths["input"],
                outputPath=runPaths["output"],
                resultJsonPath=runPaths["result"],
                runId=runId,
                executionMode=executionMode,
                device=device,
            )
            self._startBackendProcess(
                arguments,
                "segment-teeth",
                runId,
                {
                    "paths": runPaths,
                    "sourceVolumeId": volumeNode.GetID(),
                    "device": device,
                },
            )

    def onCancelBackend(self) -> None:
        self._cancelBackendProcess(
            updateStatus=True,
            message=_("Cancellation requested. Waiting for the backend process to stop..."),
        )

    def _cancelBackendProcess(
        self,
        updateStatus: bool,
        message: str = "",
    ) -> None:
        if not self._backendProcess:
            return
        self._backendCancellationRequested = True
        if updateStatus:
            self._setBackendStatus(message or _("Cancellation requested."), "warning")
        try:
            self._backendProcess.terminate()
        except Exception:
            logging.exception("Failed to terminate DENTOBOT backend process")

    def _onBackendCompleted(self, runId: str, returnCode: int) -> None:
        if not self._activeBackendRun or self._activeBackendRun["runId"] != runId:
            return

        runContext = self._activeBackendRun
        wasCancelled = self._backendCancellationRequested
        self._backendProcess = None
        self._activeBackendRun = None
        self._backendCancellationRequested = False
        if self._isCleaningUp:
            return
        self._updateBackendControls()

        if wasCancelled:
            self._setBackendStatus(_("Backend process cancelled."), "warning")
            return

        try:
            if runContext["operation"] == "health":
                self._completeHealthCheck(returnCode)
            elif runContext["operation"] == "roundtrip":
                self._completeRoundTrip(runContext, returnCode)
            elif runContext["operation"] == "segment-teeth":
                self._completeTeethSegmentation(runContext, returnCode)
        except Exception as exc:
            logging.exception("DENTOBOT backend completion handling failed")
            self._setBackendStatus(str(exc), "error")

    def _completeHealthCheck(self, returnCode: int) -> None:
        report = self.logic.findJsonReport(self._backendOutputLines, "health")
        if not report:
            raise RuntimeError(
                _("The backend did not return a valid health JSON document.")
            )
        if report.get("schemaVersion") != "1.0":
            raise RuntimeError(_("The backend health schema version is not supported."))

        if returnCode != 0 or report.get("status") != "ok":
            errors = report.get("errors") or [
                _("Backend health check failed with exit code %1.").replace(
                    "%1", str(returnCode)
                )
            ]
            raise RuntimeError(" ".join(str(error) for error in errors))

        requestedDevice = str(report.get("requestedDevice") or _("unspecified"))
        openvinoDevices = report.get("openvino", {}).get("devices") or []
        acceleratorText = (
            _("; OpenVINO sees %1").replace(
                "%1", ", ".join(str(device) for device in openvinoDevices)
            )
            if openvinoDevices
            else ""
        )
        pythonVersion = report.get("python", {}).get("version", _("unknown"))
        self._setBackendStatus(
            _("Backend healthy: Python %1; explicit device %2%3.")
            .replace("%1", str(pythonVersion))
            .replace("%2", requestedDevice)
            .replace("%3", acceleratorText),
            "success",
        )

    def _completeTeethSegmentation(
        self,
        runContext: dict,
        returnCode: int,
    ) -> None:
        runPaths = runContext["paths"]
        resultPath = runPaths["result"]
        if not resultPath.is_file():
            raise RuntimeError(
                _("The backend did not create the expected segmentation metadata.")
            )

        report = json.loads(resultPath.read_text(encoding="utf-8"))
        self.logic.validateTeethSegmentationReport(
            report,
            runContext["runId"],
            expectedDevice=runContext.get("device"),
        )
        if returnCode != 0 or report.get("status") != "ok":
            errorCode = report.get("errorCode")
            errors = report.get("errors") or [
                _("Teeth segmentation failed with exit code %1.")
                .replace("%1", str(returnCode))
            ]
            prefix = f"[{errorCode}] " if errorCode else ""
            raise RuntimeError(prefix + " ".join(str(error) for error in errors))
        if not runPaths["output"].is_file():
            raise RuntimeError(_("The expected teeth segmentation NIfTI is missing."))

        sourceVolume = slicer.mrmlScene.GetNodeByID(runContext["sourceVolumeId"])
        if not sourceVolume:
            raise RuntimeError(_("The source CBCT volume is no longer in the scene."))

        labelmapNode = None
        colorTableNode = None
        segmentationNode = None
        try:
            labelmapNode = slicer.util.loadLabelVolume(
                str(runPaths["output"]),
                {"name": f"DENTOBOT_TeethLabels_{runContext['runId'][:8]}"},
            )
            if not labelmapNode:
                raise RuntimeError(
                    _("Slicer could not import the returned teeth label map.")
                )
            self.logic.validateMatchingVolumeGeometry(
                sourceVolume,
                labelmapNode,
                requireMatchingScalarType=False,
            )
            self.logic.validateLabelmapAgainstReport(labelmapNode, report)

            colorTableNode = self.logic.createTeethColorTable(
                report["labels"],
                runContext["runId"],
            )
            labelmapNode.CreateDefaultDisplayNodes()
            labelmapNode.GetDisplayNode().SetAndObserveColorNodeID(
                colorTableNode.GetID()
            )

            segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLSegmentationNode",
                f"DENTOsegmentation_Teeth_{runContext['runId'][:8]}",
            )
            segmentationNode.CreateDefaultDisplayNodes()
            segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(
                sourceVolume
            )
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
                labelmapNode,
                segmentationNode,
            )
            expectedSegmentCount = int(report["metrics"]["segmentCount"])
            actualSegmentCount = (
                segmentationNode.GetSegmentation().GetNumberOfSegments()
            )
            if actualSegmentCount != expectedSegmentCount:
                raise RuntimeError(
                    _(
                        "Imported segmentation contains %1 segments, but the "
                        "validated backend report specifies %2."
                    )
                    .replace("%1", str(actualSegmentCount))
                    .replace("%2", str(expectedSegmentCount))
                )

            self._setBackendStatus(
                _("Creating interactive 3D surfaces for validated labels..."),
                "working",
            )
            slicer.app.processEvents()
            segmentationNode.CreateClosedSurfaceRepresentation()
            displayNode = segmentationNode.GetDisplayNode()
            displayNode.SetVisibility(True)
            displayNode.SetVisibility2D(True)
            displayNode.SetVisibility3D(True)
            displayNode.SetOpacity3D(0.55)

            reviewMetadataWarning = (
                self.logic.applyTeethSegmentationReviewMetadata(
                    segmentationNode,
                    sourceVolume,
                    report,
                    resultMetadataPath=resultPath,
                    segmentationNiftiPath=runPaths["output"],
                )
            )
            if reviewMetadataWarning:
                logging.warning(reviewMetadataWarning)

            parameterNode = self.logic.getParameterNode()
            parameterNode.teethSegmentation = segmentationNode
            if self._parameterNode:
                self._updateBackendControls()
                self.ui.backendCollapsibleButton.collapsed = True
                self.ui.segmentationReviewCollapsibleButton.collapsed = False
            slicer.util.setSliceViewerLayers(background=sourceVolume, fit=False)
        except Exception:
            if segmentationNode:
                slicer.mrmlScene.RemoveNode(segmentationNode)
            raise
        finally:
            if labelmapNode:
                slicer.mrmlScene.RemoveNode(labelmapNode)
            if colorTableNode:
                slicer.mrmlScene.RemoveNode(colorTableNode)

        self._setBackendStatus(
            _(
                "Teeth segmentation completed on %1: %2 validated segments are "
                "visible in 2D and 3D. Review this research output before use."
            )
            .replace("%1", str(report["device"]["actual"]))
            .replace("%2", str(report["metrics"]["segmentCount"])),
            "success",
        )

    def _completeRoundTrip(self, runContext: dict, returnCode: int) -> None:
        runPaths = runContext["paths"]
        resultPath = runPaths["result"]
        if not resultPath.is_file():
            raise RuntimeError(
                _("The backend did not create the expected result JSON document.")
            )

        report = json.loads(resultPath.read_text(encoding="utf-8"))
        if report.get("schemaVersion") != "1.0" or report.get("command") != "roundtrip":
            raise RuntimeError(_("The backend result contract is not supported."))
        if report.get("runId") != runContext["runId"]:
            raise RuntimeError(_("The result run ID does not match the requested run."))
        if returnCode != 0 or report.get("status") != "ok":
            errors = report.get("errors") or [
                _("Round trip failed with exit code %1.").replace("%1", str(returnCode))
            ]
            raise RuntimeError(" ".join(str(error) for error in errors))
        if not report.get("geometryMatch") or not report.get("dataMatch"):
            raise RuntimeError(_("Backend round-trip validation did not pass."))
        if not runPaths["output"].is_file():
            raise RuntimeError(_("The expected round-trip NIfTI is missing."))

        sourceVolume = slicer.mrmlScene.GetNodeByID(runContext["sourceVolumeId"])
        if not sourceVolume:
            raise RuntimeError(_("The source CBCT volume is no longer in the scene."))

        outputVolume = slicer.util.loadVolume(
            str(runPaths["output"]),
            {"name": f"DENTOBOT_RoundTrip_{runContext['runId'][:8]}"},
        )
        if not outputVolume:
            raise RuntimeError(_("Slicer could not import the round-trip NIfTI."))
        outputVolume.SetName(f"DENTOBOT_RoundTrip_{runContext['runId'][:8]}")

        try:
            self.logic.validateMatchingVolumeGeometry(sourceVolume, outputVolume)
        except Exception:
            slicer.mrmlScene.RemoveNode(outputVolume)
            raise

        outputVolume.SetAttribute("DENTOBOT.BridgeOperation", "roundtrip")
        outputVolume.SetAttribute("DENTOBOT.RunId", runContext["runId"])
        outputVolume.SetAttribute("DENTOBOT.SourceVolumeID", sourceVolume.GetID())
        outputVolume.SetAttribute("DENTOBOT.ResultMetadataPath", str(resultPath))

        parameterNode = self.logic.getParameterNode()
        parameterNode.roundTripVolume = outputVolume
        if self._parameterNode:
            self._updateBackendControls()
        self._setBackendStatus(
            _(
                "Round trip passed for %1. Geometry and voxel data were validated; "
                "the returned volume is now in the MRML scene."
            ).replace("%1", sourceVolume.GetName() or _("Unnamed volume")),
            "success",
        )


class DENTOWorkflowLogic(ScriptedLoadableModuleLogic):
    """Reusable MRML, volume-geometry, and external-bridge operations."""

    BACKEND_MODULE = "dentobot_inference"
    REVIEW_METADATA_VERSION = "1.0"
    REVIEW_STATES = ("Unreviewed", "Needs Correction", "Reviewed")
    SOURCE_VOLUME_REFERENCE_ROLE = "DENTOBOT.SourceVolume"
    TARGET_SEGMENTATION_REFERENCE_ROLE = "DENTOBOT.TargetSegmentation"
    TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE = (
        "DENTOBOT.TargetBoundsSegmentation"
    )
    TARGET_BOUNDS_ROI_REFERENCE_ROLE = "DENTOBOT.TargetBoundsROI"
    SEGMENT_REVIEW_CATEGORY_ORDER = (
        "Teeth",
        "Pulp and root canals",
        "Jaws",
        "Neural and mandibular canals",
        "Sinuses and airway",
        "Restorations and implants",
        "Other anatomy",
    )

    def getParameterNode(self) -> DENTOWorkflowParameterNode:
        return DENTOWorkflowParameterNode(super().getParameterNode())

    def getScalarVolumeNodes(self) -> list[vtkMRMLScalarVolumeNode]:
        return list(slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"))

    def getLatestScalarVolumeNode(self) -> vtkMRMLScalarVolumeNode | None:
        volumeNodes = self.getScalarVolumeNodes()
        return volumeNodes[-1] if volumeNodes else None

    def getLatestTeethSegmentationNode(self) -> vtkMRMLSegmentationNode | None:
        """Return the latest Bridge C result, without selecting unrelated nodes."""

        segmentationNodes = list(
            slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
        )
        bridgeResults = [
            node
            for node in segmentationNodes
            if node.GetAttribute("DENTOBOT.BridgeOperation") == "segment-teeth"
        ]
        return bridgeResults[-1] if bridgeResults else None

    def getTargetToothRecords(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> list[dict]:
        """Return only whole-tooth segments eligible for draft targeting."""

        return [
            record
            for record in self.getSegmentationReviewRecords(segmentationNode)
            if record["category"] == "Teeth"
        ]

    def validateTargetTooth(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> dict:
        """Return the selected whole-tooth record or raise an actionable error."""

        if not isinstance(segmentId, str) or not segmentId.strip():
            raise ValueError(_("Select a target tooth before planning."))
        targetId = segmentId.strip()
        targetRecords = {
            record["segmentId"]: record
            for record in self.getTargetToothRecords(segmentationNode)
        }
        record = targetRecords.get(targetId)
        if not record:
            raise ValueError(
                _(
                    "The selected target does not exist or is not a whole-tooth "
                    "segment."
                )
            )
        return record

    def getTargetToothBoundsWorld(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> tuple[float, float, float, float, float, float]:
        """Return finite axis-aligned world-RAS bounds for one whole tooth."""

        self.validateTargetTooth(segmentationNode, segmentId)
        closedSurface = vtk.vtkPolyData()
        success = (
            slicer.vtkSlicerSegmentationsModuleLogic
            .GetSegmentClosedSurfaceRepresentation(
                segmentationNode,
                segmentId,
                closedSurface,
            )
        )
        if not success or closedSurface.GetNumberOfPoints() == 0:
            raise ValueError(
                _(
                    "The selected target tooth has no closed surface from "
                    "which to calculate placement bounds."
                )
            )
        bounds = tuple(float(value) for value in closedSurface.GetBounds())
        if (
            len(bounds) != 6
            or any(not math.isfinite(value) for value in bounds)
            or any(
                bounds[axis * 2 + 1] <= bounds[axis * 2]
                for axis in range(3)
            )
        ):
            raise ValueError(
                _("The selected target tooth has invalid world-RAS bounds.")
            )
        return bounds

    @staticmethod
    def formatRasBounds(
        bounds: tuple[float, float, float, float, float, float],
    ) -> str:
        """Format world-RAS axis-aligned bounds for the planning panel."""

        if len(bounds) != 6:
            raise ValueError(_("Six target-bound values are required."))
        return (
            f"R [{bounds[0]:.3f}, {bounds[1]:.3f}], "
            f"A [{bounds[2]:.3f}, {bounds[3]:.3f}], "
            f"S [{bounds[4]:.3f}, {bounds[5]:.3f}] mm"
        )

    def createOrUpdateTargetBoundsRoi(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
        roiNode: vtkMRMLMarkupsROINode | None = None,
    ) -> tuple[vtkMRMLMarkupsROINode, tuple[float, ...]]:
        """Create a locked visible ROI matching the selected tooth's RAS AABB."""

        targetRecord = self.validateTargetTooth(
            segmentationNode,
            segmentId,
        )
        bounds = self.getTargetToothBoundsWorld(
            segmentationNode,
            segmentId,
        )
        if not roiNode or not roiNode.IsA("vtkMRMLMarkupsROINode"):
            roiNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsROINode",
                f'DENTO Target Bounds FDI {targetRecord["fdiNumber"]}',
            )
        if not roiNode:
            raise RuntimeError(_("Slicer could not create target bounds."))

        center = [
            (bounds[axis * 2] + bounds[axis * 2 + 1]) / 2.0
            for axis in range(3)
        ]
        size = [
            bounds[axis * 2 + 1] - bounds[axis * 2]
            for axis in range(3)
        ]
        wasModifying = roiNode.StartModify()
        try:
            roiNode.SetName(
                f'DENTO Target Bounds FDI {targetRecord["fdiNumber"]}'
            )
            roiNode.SetCenterWorld(center)
            roiNode.SetSizeWorld(size)
            roiNode.SetLocked(True)
            roiNode.SetAttribute("DENTOBOT.BoundsRole", "TargetToothAABB")
            roiNode.SetAttribute(
                "DENTOBOT.CoordinateSystem",
                "SlicerRASmm",
            )
            roiNode.SetAttribute(
                "DENTOBOT.TargetSegmentID",
                targetRecord["segmentId"],
            )
            roiNode.SetAttribute(
                "DENTOBOT.TargetFdiNumber",
                targetRecord["fdiNumber"] or "",
            )
            roiNode.SetNodeReferenceID(
                self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE,
                segmentationNode.GetID(),
            )
        finally:
            roiNode.EndModify(wasModifying)

        roiNode.CreateDefaultDisplayNodes()
        displayNode = roiNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(True)
            displayNode.SetVisibility2D(True)
            displayNode.SetVisibility3D(True)
            displayNode.SetFillVisibility(False)
            displayNode.SetOutlineVisibility(True)
            displayNode.SetPropertiesLabelVisibility(False)
            displayNode.SetColor(1.0, 0.65, 0.0)
            displayNode.SetSelectedColor(1.0, 0.8, 0.2)
            if hasattr(displayNode, "SetHandlesInteractive"):
                displayNode.SetHandlesInteractive(False)
        return roiNode, bounds

    @staticmethod
    def isRasPointWithinBounds(
        point: list[float] | tuple[float, ...],
        bounds: tuple[float, float, float, float, float, float],
        toleranceMm: float = 1e-3,
    ) -> bool:
        """Return whether a point lies inside an inclusive world-RAS AABB."""

        if len(point) != 3 or len(bounds) != 6:
            raise ValueError(_("Invalid point or target bounds."))
        toleranceMm = float(toleranceMm)
        if not math.isfinite(toleranceMm) or toleranceMm < 0.0:
            raise ValueError(_("Bounds tolerance must be non-negative."))
        return all(
            bounds[axis * 2] - toleranceMm
            <= float(point[axis])
            <= bounds[axis * 2 + 1] + toleranceMm
            for axis in range(3)
        )

    def getTrajectoryBoundsReport(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> dict:
        """Report any Entry/Target points outside the selected tooth AABB."""

        summary = self.getTrajectorySummary(trajectoryNode)
        bounds = self.getTargetToothBoundsWorld(
            segmentationNode,
            segmentId,
        )
        points = (summary["entryRas"], summary["targetRas"])
        invalidIndices = [
            index
            for index, point in enumerate(points)
            if point is not None
            and not self.isRasPointWithinBounds(point, bounds)
        ]
        return {
            "bounds": bounds,
            "invalidPointIndices": invalidIndices,
            "allDefinedPointsWithinBounds": not invalidIndices,
            "summary": summary,
        }

    def createTrajectoryNode(
        self,
        name: str = "DENTO Trajectory",
    ) -> vtkMRMLMarkupsLineNode:
        """Create a draft entry-to-target line in the current MRML scene."""

        if not isinstance(name, str) or not name.strip():
            raise ValueError(_("Trajectory name must not be empty."))
        trajectoryNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsLineNode",
            name.strip(),
        )
        if not trajectoryNode:
            raise RuntimeError(_("Slicer could not create a trajectory line."))
        if trajectoryNode.GetMaximumNumberOfControlPoints() != 2:
            slicer.mrmlScene.RemoveNode(trajectoryNode)
            raise RuntimeError(
                _("The created trajectory does not enforce two control points.")
            )
        trajectoryNode.CreateDefaultDisplayNodes()
        trajectoryNode.SetAttribute("DENTOBOT.TrajectoryRole", "EntryToTarget")
        trajectoryNode.SetAttribute(
            "DENTOBOT.CoordinateSystem",
            "SlicerRASmm",
        )
        trajectoryNode.SetAttribute("DENTOBOT.PlanningStatus", "Draft")
        return trajectoryNode

    def configureTrajectoryTarget(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> dict:
        """Associate a draft trajectory with one authoritative tooth segment."""

        self.getTrajectorySummary(trajectoryNode)
        targetRecord = self.validateTargetTooth(segmentationNode, segmentId)
        wasModifying = trajectoryNode.StartModify()
        try:
            trajectoryNode.SetNodeReferenceID(
                self.TARGET_SEGMENTATION_REFERENCE_ROLE,
                segmentationNode.GetID(),
            )
            trajectoryNode.SetAttribute(
                "DENTOBOT.TargetSegmentID",
                targetRecord["segmentId"],
            )
            trajectoryNode.SetAttribute(
                "DENTOBOT.TargetSegmentName",
                targetRecord["sourceName"],
            )
            trajectoryNode.SetAttribute(
                "DENTOBOT.TargetFdiNumber",
                targetRecord["fdiNumber"] or "",
            )
            trajectoryNode.SetAttribute(
                "DENTOBOT.TrajectoryRole",
                "EntryToTarget",
            )
            trajectoryNode.SetAttribute(
                "DENTOBOT.CoordinateSystem",
                "SlicerRASmm",
            )
            trajectoryNode.SetAttribute("DENTOBOT.PlanningStatus", "Draft")
        finally:
            trajectoryNode.EndModify(wasModifying)
        self.labelTrajectoryControlPoints(trajectoryNode)
        return targetRecord

    def clearTrajectoryTarget(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> None:
        """Remove a stale target association without deleting trajectory geometry."""

        self.getTrajectorySummary(trajectoryNode)
        wasModifying = trajectoryNode.StartModify()
        try:
            trajectoryNode.SetNodeReferenceID(
                self.TARGET_SEGMENTATION_REFERENCE_ROLE,
                None,
            )
            trajectoryNode.SetNodeReferenceID(
                self.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
                None,
            )
            for attributeName in (
                "DENTOBOT.TargetSegmentID",
                "DENTOBOT.TargetSegmentName",
                "DENTOBOT.TargetFdiNumber",
            ):
                trajectoryNode.SetAttribute(attributeName, None)
        finally:
            trajectoryNode.EndModify(wasModifying)

    @staticmethod
    def labelTrajectoryControlPoints(
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> None:
        """Apply explicit Entry and Target labels to defined control points."""

        if not trajectoryNode or not trajectoryNode.IsA(
            "vtkMRMLMarkupsLineNode"
        ):
            raise ValueError(_("Select a valid trajectory line node."))
        labels = ("Entry", "Target")
        pointCount = min(
            trajectoryNode.GetNumberOfDefinedControlPoints(),
            len(labels),
        )
        for index in range(pointCount):
            if trajectoryNode.GetNthControlPointLabel(index) != labels[index]:
                trajectoryNode.SetNthControlPointLabel(index, labels[index])

    @staticmethod
    def formatRasPoint(point: list[float] | tuple[float, ...]) -> str:
        """Format one world-RAS point for a compact read-only UI value."""

        if not point or len(point) != 3:
            raise ValueError(_("A three-component RAS point is required."))
        return f"{point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f} mm"

    def getTrajectorySummary(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> dict:
        """Return current world-RAS points and length for a trajectory line."""

        if not trajectoryNode or not trajectoryNode.IsA(
            "vtkMRMLMarkupsLineNode"
        ):
            raise ValueError(_("Select a valid trajectory line node."))
        if trajectoryNode.GetMaximumNumberOfControlPoints() != 2:
            raise ValueError(
                _("The trajectory line must enforce exactly two control points.")
            )

        pointCount = trajectoryNode.GetNumberOfDefinedControlPoints()
        if pointCount < 0 or pointCount > 2:
            raise ValueError(
                _("The trajectory line contains an invalid number of points.")
            )
        points: list[list[float]] = []
        for index in range(pointCount):
            point = [0.0, 0.0, 0.0]
            trajectoryNode.GetNthControlPointPositionWorld(index, point)
            points.append(point)

        entryRas = points[0] if pointCount >= 1 else None
        targetRas = points[1] if pointCount >= 2 else None
        lengthMm = None
        if entryRas is not None and targetRas is not None:
            lengthMm = float(
                vtk.vtkMath.Distance2BetweenPoints(entryRas, targetRas) ** 0.5
            )
        return {
            "definedPointCount": pointCount,
            "entryRas": entryRas,
            "targetRas": targetRas,
            "lengthMm": lengthMm,
            "isValid": bool(lengthMm is not None and lengthMm > 1e-6),
        }

    def startTrajectoryPlacement(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> None:
        """Activate Slicer's one-at-a-time Markups placement for this line."""

        summary = self.getTrajectorySummary(trajectoryNode)
        if summary["definedPointCount"] >= 2:
            raise ValueError(
                _(
                    "The trajectory already has Entry and Target points. Move "
                    "them in a view or remove them in Markups before placing "
                    "again."
                )
            )
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if not selectionNode:
            raise RuntimeError(_("Slicer's selection node is unavailable."))
        selectionNode.SetReferenceActivePlaceNodeClassName(
            "vtkMRMLMarkupsLineNode"
        )
        selectionNode.SetActivePlaceNodeID(trajectoryNode.GetID())
        slicer.modules.markups.logic().StartPlaceMode(0)
        # Slicer 5.12 resets the active placement class to Fiducial when
        # StartPlaceMode is called. Reassert the selected line afterwards so
        # view clicks populate this two-point line instead of creating F_*
        # fiducial lists.
        selectionNode.SetActivePlaceNodeClassName(
            "vtkMRMLMarkupsLineNode"
        )
        selectionNode.SetActivePlaceNodeID(trajectoryNode.GetID())
        if (
            selectionNode.GetActivePlaceNodeID() != trajectoryNode.GetID()
            or selectionNode.GetActivePlaceNodeClassName()
            != "vtkMRMLMarkupsLineNode"
            or not selectionNode.GetActivePlaceNodePlacementValid()
        ):
            self.stopTrajectoryPlacement()
            raise RuntimeError(
                _("Slicer could not activate the selected trajectory line.")
            )

    @staticmethod
    def stopTrajectoryPlacement() -> None:
        """Return Slicer to view interaction without altering line geometry."""

        interactionNode = (
            slicer.app.applicationLogic().GetInteractionNode()
        )
        if not interactionNode:
            raise RuntimeError(_("Slicer's interaction node is unavailable."))
        interactionNode.SwitchToViewTransformMode()

    def applyTeethSegmentationReviewMetadata(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        sourceVolume: vtkMRMLScalarVolumeNode | None,
        report: dict,
        resultMetadataPath: str | Path | None = None,
        segmentationNiftiPath: str | Path | None = None,
    ) -> str:
        """Persist validated Bridge C provenance and per-label metrics in MRML."""

        segmentation, _displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        runId = str(report.get("runId") or "")
        self.validateTeethSegmentationReport(report, runId)
        if report.get("status") != "ok":
            raise ValueError(_("Only a successful segmentation can be reviewed."))

        labelsById = {
            int(label["id"]): label
            for label in report["labels"]
        }
        metricsById = {
            int(metric["id"]): metric
            for metric in report["metrics"]["perLabel"]
        }
        metricsByName = {
            str(metric["name"]): metric
            for metric in report["metrics"]["perLabel"]
        }
        segmentIds = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(segmentIds)
        segmentMetrics = []
        unmatchedSegmentNames = []
        for index in range(segmentIds.GetNumberOfValues()):
            segmentId = segmentIds.GetValue(index)
            segment = segmentation.GetSegment(segmentId)
            if not segment:
                continue
            sourceName = str(segment.GetName() or "")
            labelValue = int(segment.GetLabelValue())
            metric = metricsById.get(labelValue) or metricsByName.get(sourceName)
            if not metric:
                unmatchedSegmentNames.append(sourceName or segmentId)
                continue
            labelId = int(metric["id"])
            label = labelsById.get(labelId)
            segmentMetrics.append(
                {
                    "segmentId": segmentId,
                    "labelId": labelId,
                    "sourceName": str(
                        label["name"] if label else metric["name"]
                    ),
                    "voxelCount": int(metric["voxelCount"]),
                    "volumeMm3": float(metric["volumeMm3"]),
                }
            )

        metadataStatus = (
            "complete"
            if len(segmentMetrics) == int(report["metrics"]["segmentCount"])
            and not unmatchedSegmentNames
            else "partial"
        )
        metricsDocument = {
            "schemaVersion": self.REVIEW_METADATA_VERSION,
            "status": metadataStatus,
            "segments": segmentMetrics,
        }

        backend = report["backend"]
        packages = backend["packages"]
        model = report["model"]
        device = report["device"]
        metrics = report["metrics"]
        wasModifying = segmentationNode.StartModify()
        try:
            segmentationNode.SetAttribute(
                "DENTOBOT.BridgeOperation",
                "segment-teeth",
            )
            segmentationNode.SetAttribute("DENTOBOT.RunId", runId)
            if sourceVolume:
                segmentationNode.SetAttribute(
                    "DENTOBOT.SourceVolumeID",
                    sourceVolume.GetID(),
                )
                segmentationNode.SetNodeReferenceID(
                    self.SOURCE_VOLUME_REFERENCE_ROLE,
                    sourceVolume.GetID(),
                )
            if resultMetadataPath is not None:
                segmentationNode.SetAttribute(
                    "DENTOBOT.ResultMetadataPath",
                    str(resultMetadataPath),
                )
            if segmentationNiftiPath is not None:
                segmentationNode.SetAttribute(
                    "DENTOBOT.SegmentationNiftiPath",
                    str(segmentationNiftiPath),
                )
            segmentationNode.SetAttribute(
                "DENTOBOT.ModelTask",
                str(model["task"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ModelTaskId",
                str(model["taskId"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ModelSourceDataset",
                str(model.get("sourceDataset") or ""),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.CropTask",
                str(model.get("cropTask") or ""),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.CropTaskId",
                str(model["cropTaskId"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.BackendName",
                str(backend.get("name") or "dentobot-inference"),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.BackendVersion",
                str(backend.get("version") or ""),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.PythonVersion",
                str(backend.get("pythonVersion") or ""),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.PackageVersionsJson",
                json.dumps(packages, sort_keys=True, separators=(",", ":")),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.TotalSegmentatorVersion",
                str(packages["TotalSegmentator"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.RequestedDevice",
                str(device["requested"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ActualDevice",
                str(device["actual"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.RuntimeSeconds",
                str(report["runtimeSeconds"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.InferenceSeconds",
                str(report["inferenceSeconds"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.StartedAtUtc",
                str(report.get("startedAtUtc") or ""),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.CompletedAtUtc",
                str(report.get("completedAtUtc") or ""),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.SegmentCount",
                str(metrics["segmentCount"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ForegroundVolumeMm3",
                str(metrics["foregroundVolumeMm3"]),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.PeakAllocatedBytes",
                (
                    str(device["peakAllocatedBytes"])
                    if device["peakAllocatedBytes"] is not None
                    else ""
                ),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.SegmentMetricsJson",
                json.dumps(
                    metricsDocument,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewMetadataVersion",
                self.REVIEW_METADATA_VERSION,
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewMetadataStatus",
                metadataStatus,
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.SegmentMetricsValidity",
                (
                    "pre-correction-inference"
                    if segmentationNode.GetAttribute(
                        "DENTOBOT.CorrectionStartedUtc"
                    )
                    else "current"
                ),
            )
            if not segmentationNode.GetAttribute("DENTOBOT.ReviewState"):
                segmentationNode.SetAttribute(
                    "DENTOBOT.ReviewState",
                    self.REVIEW_STATES[0],
                )
        finally:
            segmentationNode.EndModify(wasModifying)

        if unmatchedSegmentNames:
            return _(
                "Per-label metrics could not be matched for: %1"
            ).replace("%1", ", ".join(unmatchedSegmentNames))
        return ""

    def ensureSegmentationReviewMetadata(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> str:
        """Migrate one older Bridge C result from its retained result.json."""

        self._segmentationAndDisplayNode(segmentationNode)
        if not segmentationNode.GetAttribute("DENTOBOT.ReviewState"):
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewState",
                self.REVIEW_STATES[0],
            )

        sourceVolume = segmentationNode.GetNodeReference(
            self.SOURCE_VOLUME_REFERENCE_ROLE
        )
        if not sourceVolume:
            sourceVolumeId = segmentationNode.GetAttribute(
                "DENTOBOT.SourceVolumeID"
            )
            sourceVolume = (
                slicer.mrmlScene.GetNodeByID(sourceVolumeId)
                if sourceVolumeId
                else None
            )
            if sourceVolume:
                segmentationNode.SetNodeReferenceID(
                    self.SOURCE_VOLUME_REFERENCE_ROLE,
                    sourceVolume.GetID(),
                )

        if (
            segmentationNode.GetAttribute("DENTOBOT.ReviewMetadataVersion")
            == self.REVIEW_METADATA_VERSION
            and segmentationNode.GetAttribute("DENTOBOT.SegmentMetricsJson")
        ):
            return ""

        resultPathText = segmentationNode.GetAttribute(
            "DENTOBOT.ResultMetadataPath"
        )
        if not resultPathText:
            return _(
                "Per-label metrics are unavailable because no result metadata "
                "path is stored on this segmentation."
            )
        resultPath = Path(resultPathText)
        if not resultPath.is_file():
            return _(
                "Per-label metrics are unavailable because the retained "
                "result.json file cannot be found."
            )
        try:
            report = json.loads(resultPath.read_text(encoding="utf-8"))
            runId = segmentationNode.GetAttribute("DENTOBOT.RunId") or ""
            self.validateTeethSegmentationReport(report, runId)
            return self.applyTeethSegmentationReviewMetadata(
                segmentationNode,
                sourceVolume,
                report,
                resultMetadataPath=resultPath,
                segmentationNiftiPath=segmentationNode.GetAttribute(
                    "DENTOBOT.SegmentationNiftiPath"
                ),
            )
        except Exception as exc:
            logging.warning(
                "Could not migrate DENTOBOT segmentation review metadata: %s",
                exc,
            )
            return _(
                "Per-label metrics could not be restored from result.json: %1"
            ).replace("%1", str(exc))

    def getSegmentationSegmentDetails(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> dict:
        """Return one selected segment's identity and quantitative metadata."""

        records = self.getSegmentationReviewRecords(segmentationNode)
        record = next(
            (
                candidate
                for candidate in records
                if candidate["segmentId"] == segmentId
            ),
            None,
        )
        if not record:
            raise ValueError(_("The selected segment does not exist."))

        metric = None
        metricsText = segmentationNode.GetAttribute(
            "DENTOBOT.SegmentMetricsJson"
        )
        if metricsText:
            try:
                metricsDocument = json.loads(metricsText)
                if (
                    metricsDocument.get("schemaVersion")
                    == self.REVIEW_METADATA_VERSION
                ):
                    metric = next(
                        (
                            candidate
                            for candidate in metricsDocument.get("segments", [])
                            if candidate.get("segmentId") == segmentId
                        ),
                        None,
                    )
            except (json.JSONDecodeError, AttributeError, TypeError):
                metric = None

        return {
            **record,
            "labelId": metric.get("labelId") if metric else None,
            "voxelCount": metric.get("voxelCount") if metric else None,
            "volumeMm3": metric.get("volumeMm3") if metric else None,
            "runId": segmentationNode.GetAttribute("DENTOBOT.RunId") or "",
            "metricsValidity": (
                segmentationNode.GetAttribute(
                    "DENTOBOT.SegmentMetricsValidity"
                )
                or "current"
            ),
        }

    def getSegmentationProvenance(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> dict[str, str]:
        """Return compact, presentation-ready provenance from MRML attributes."""

        self._segmentationAndDisplayNode(segmentationNode)
        sourceVolume = segmentationNode.GetNodeReference(
            self.SOURCE_VOLUME_REFERENCE_ROLE
        )
        sourceVolumeText = (
            sourceVolume.GetName() or _("Unnamed volume")
            if sourceVolume
            else segmentationNode.GetAttribute("DENTOBOT.SourceVolumeID")
            or _("Unavailable")
        )
        packages = {}
        packagesText = segmentationNode.GetAttribute(
            "DENTOBOT.PackageVersionsJson"
        )
        if packagesText:
            try:
                packages = json.loads(packagesText)
            except (json.JSONDecodeError, TypeError):
                packages = {}

        backendName = (
            segmentationNode.GetAttribute("DENTOBOT.BackendName")
            or "dentobot-inference"
        )
        backendVersion = (
            segmentationNode.GetAttribute("DENTOBOT.BackendVersion")
            or _("unknown")
        )
        totalSegmentatorVersion = (
            packages.get("TotalSegmentator")
            or segmentationNode.GetAttribute(
                "DENTOBOT.TotalSegmentatorVersion"
            )
            or _("unknown")
        )
        modelTask = (
            segmentationNode.GetAttribute("DENTOBOT.ModelTask")
            or _("unknown")
        )
        modelTaskId = (
            segmentationNode.GetAttribute("DENTOBOT.ModelTaskId")
            or _("unknown")
        )
        sourceDataset = (
            segmentationNode.GetAttribute("DENTOBOT.ModelSourceDataset")
            or _("unknown dataset")
        )
        cropTask = (
            segmentationNode.GetAttribute("DENTOBOT.CropTask")
            or _("unknown crop")
        )
        cropTaskId = (
            segmentationNode.GetAttribute("DENTOBOT.CropTaskId")
            or _("unknown")
        )
        inferenceSeconds = segmentationNode.GetAttribute(
            "DENTOBOT.InferenceSeconds"
        )
        runtimeSeconds = segmentationNode.GetAttribute(
            "DENTOBOT.RuntimeSeconds"
        )
        timingText = _("Unavailable")
        if inferenceSeconds and runtimeSeconds:
            timingText = (
                _("%1 s inference; %2 s total")
                .replace("%1", f"{float(inferenceSeconds):.1f}")
                .replace("%2", f"{float(runtimeSeconds):.1f}")
            )

        return {
            "runId": segmentationNode.GetAttribute("DENTOBOT.RunId")
            or _("Unavailable"),
            "sourceVolume": sourceVolumeText,
            "backend": (
                f"{backendName} {backendVersion}; "
                f"TotalSegmentator {totalSegmentatorVersion}"
            ),
            "model": (
                f"{modelTask} (task {modelTaskId}), {sourceDataset}; "
                f"{cropTask} crop (task {cropTaskId})"
            ),
            "device": segmentationNode.GetAttribute("DENTOBOT.ActualDevice")
            or _("Unavailable"),
            "timing": timingText,
            "completedAtUtc": segmentationNode.GetAttribute(
                "DENTOBOT.CompletedAtUtc"
            )
            or _("Unavailable"),
            "reviewState": self.getSegmentationReviewState(segmentationNode),
            "reviewUpdatedUtc": segmentationNode.GetAttribute(
                "DENTOBOT.ReviewUpdatedUtc"
            )
            or _("Not yet changed"),
            "lastSegmentationEditUtc": segmentationNode.GetAttribute(
                "DENTOBOT.LastSegmentationEditUtc"
            )
            or _("No edits recorded"),
            "correctionActivityUtc": (
                segmentationNode.GetAttribute(
                    "DENTOBOT.LastSegmentationEditUtc"
                )
                or segmentationNode.GetAttribute(
                    "DENTOBOT.CorrectionStartedUtc"
                )
                or _("No correction recorded")
            ),
            "metricsValidity": (
                segmentationNode.GetAttribute(
                    "DENTOBOT.SegmentMetricsValidity"
                )
                or "current"
            ),
        }

    def getSegmentationReviewState(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> str:
        self._segmentationAndDisplayNode(segmentationNode)
        state = (
            segmentationNode.GetAttribute("DENTOBOT.ReviewState")
            or self.REVIEW_STATES[0]
        )
        return state if state in self.REVIEW_STATES else self.REVIEW_STATES[0]

    def setSegmentationReviewState(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        state: str,
        updatedUtc: str | None = None,
    ) -> None:
        self._segmentationAndDisplayNode(segmentationNode)
        if state not in self.REVIEW_STATES:
            raise ValueError(_("The segmentation review state is invalid."))
        timestamp = updatedUtc or datetime.now(timezone.utc).isoformat()
        wasModifying = segmentationNode.StartModify()
        try:
            segmentationNode.SetAttribute("DENTOBOT.ReviewState", state)
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewUpdatedUtc",
                timestamp,
            )
            if state == "Reviewed":
                segmentationNode.SetAttribute(
                    "DENTOBOT.ReviewInvalidationReason",
                    None,
                )
        finally:
            segmentationNode.EndModify(wasModifying)

    def getSegmentationSourceVolume(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> vtkMRMLScalarVolumeNode:
        """Return the persisted source CBCT required by Segment Editor."""

        self._segmentationAndDisplayNode(segmentationNode)
        sourceVolume = segmentationNode.GetNodeReference(
            self.SOURCE_VOLUME_REFERENCE_ROLE
        )
        if not sourceVolume:
            sourceVolumeId = segmentationNode.GetAttribute(
                "DENTOBOT.SourceVolumeID"
            )
            sourceVolume = (
                slicer.mrmlScene.GetNodeByID(sourceVolumeId)
                if sourceVolumeId
                else None
            )
            if sourceVolume:
                segmentationNode.SetNodeReferenceID(
                    self.SOURCE_VOLUME_REFERENCE_ROLE,
                    sourceVolume.GetID(),
                )
        if (
            not sourceVolume
            or not sourceVolume.IsA("vtkMRMLScalarVolumeNode")
            or not sourceVolume.GetImageData()
        ):
            raise ValueError(
                _(
                    "The segmentation's source CBCT is unavailable. Restore "
                    "the source volume before correction."
                )
            )
        return sourceVolume

    def beginSegmentationCorrection(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
        startedUtc: str | None = None,
    ) -> dict[str, object]:
        """Validate an editor handoff and begin a conservative correction revision."""

        segmentation, _displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        if not segmentId or not segmentation.GetSegment(segmentId):
            raise ValueError(_("The selected segment does not exist."))
        sourceVolume = self.getSegmentationSourceVolume(segmentationNode)
        timestamp = startedUtc or datetime.now(timezone.utc).isoformat()
        wasModifying = segmentationNode.StartModify()
        try:
            segmentationNode.SetAttribute(
                "DENTOBOT.CorrectionStartedUtc",
                timestamp,
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.SegmentMetricsValidity",
                "pre-correction-inference",
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewState",
                "Needs Correction",
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewUpdatedUtc",
                timestamp,
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewInvalidationReason",
                "Correction workflow opened",
            )
        finally:
            segmentationNode.EndModify(wasModifying)
        logging.info(
            "DENTOBOT correction started for segment %s in node %s",
            segmentId,
            segmentationNode.GetID(),
        )
        return {
            "segmentationNode": segmentationNode,
            "sourceVolume": sourceVolume,
            "segmentId": segmentId,
        }

    def invalidateSegmentationReviewAfterEdit(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        editedUtc: str | None = None,
    ) -> bool:
        """Record a mask edit and invalidate a previously reviewed result."""

        self._segmentationAndDisplayNode(segmentationNode)
        timestamp = editedUtc or datetime.now(timezone.utc).isoformat()
        wasReviewed = (
            self.getSegmentationReviewState(segmentationNode) == "Reviewed"
        )
        wasModifying = segmentationNode.StartModify()
        try:
            segmentationNode.SetAttribute(
                "DENTOBOT.LastSegmentationEditUtc",
                timestamp,
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.SegmentMetricsValidity",
                "pre-correction-inference",
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.ReviewInvalidationReason",
                "Segmentation mask content changed",
            )
            if wasReviewed:
                segmentationNode.SetAttribute(
                    "DENTOBOT.ReviewState",
                    "Needs Correction",
                )
                segmentationNode.SetAttribute(
                    "DENTOBOT.ReviewUpdatedUtc",
                    timestamp,
                )
        finally:
            segmentationNode.EndModify(wasModifying)
        logging.info(
            "DENTOBOT segmentation content change recorded for node %s; "
            "previously reviewed=%s",
            segmentationNode.GetID(),
            wasReviewed,
        )
        return wasReviewed

    @classmethod
    def describeSegmentForReview(cls, sourceName: str) -> dict[str, str | None]:
        """Create a stable human-facing category and FDI-aware display name."""

        if not isinstance(sourceName, str) or not sourceName.strip():
            raise ValueError(_("A segment name is required for review."))

        normalizedName = sourceName.strip().lower()
        fdiMatch = re.search(r"_fdi(\d+)$", normalizedName)
        sourceFdiCode = fdiMatch.group(1) if fdiMatch else None
        baseName = (
            normalizedName[: fdiMatch.start()]
            if fdiMatch
            else normalizedName
        )

        if "pulp" in baseName:
            category = "Pulp and root canals"
        elif "canal" in baseName:
            category = "Neural and mandibular canals"
        elif "jawbone" in baseName or baseName in ("mandible", "maxilla"):
            category = "Jaws"
        elif "sinus" in baseName or "pharynx" in baseName or "airway" in baseName:
            category = "Sinuses and airway"
        elif any(
            token in baseName
            for token in ("bridge", "crown", "implant", "restoration")
        ):
            category = "Restorations and implants"
        elif (
            sourceFdiCode
            and len(sourceFdiCode) == 2
            and sourceFdiCode[0] in "1234"
            and sourceFdiCode[1] in "12345678"
        ):
            category = "Teeth"
        else:
            category = "Other anatomy"

        fdiNumber = sourceFdiCode
        if (
            category == "Pulp and root canals"
            and sourceFdiCode
            and len(sourceFdiCode) == 3
            and sourceFdiCode.startswith("1")
            and sourceFdiCode[1] in "1234"
            and sourceFdiCode[2] in "12345678"
        ):
            fdiNumber = sourceFdiCode[1:]

        anatomyName = " ".join(
            word.capitalize() for word in baseName.split("_") if word
        )
        if fdiNumber:
            displayName = f"FDI {fdiNumber} \u2014 {anatomyName}"
        else:
            displayName = anatomyName

        return {
            "sourceName": sourceName.strip(),
            "displayName": displayName,
            "category": category,
            "fdiNumber": fdiNumber,
            "sourceFdiCode": sourceFdiCode,
            "searchText": " ".join(
                value.lower()
                for value in (
                    sourceName.strip(),
                    displayName,
                    category,
                    sourceFdiCode or "",
                    fdiNumber or "",
                )
                if value
            ),
        }

    def getSegmentationReviewRecords(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> list[dict]:
        """Return deterministic segment records for the Step 3A explorer."""

        segmentation, _displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        segmentIds = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(segmentIds)
        categoryOrder = {
            category: index
            for index, category in enumerate(self.SEGMENT_REVIEW_CATEGORY_ORDER)
        }
        records = []
        for index in range(segmentIds.GetNumberOfValues()):
            segmentId = segmentIds.GetValue(index)
            segment = segmentation.GetSegment(segmentId)
            if not segment:
                continue
            descriptor = self.describeSegmentForReview(segment.GetName())
            records.append(
                {
                    "segmentId": segmentId,
                    **descriptor,
                }
            )
        records.sort(
            key=lambda record: (
                categoryOrder.get(
                    record["category"],
                    len(categoryOrder),
                ),
                int(record["fdiNumber"])
                if record["fdiNumber"] and record["fdiNumber"].isdigit()
                else 9999,
                record["displayName"].lower(),
            )
        )
        return records

    @staticmethod
    def _segmentationAndDisplayNode(
        segmentationNode: vtkMRMLSegmentationNode,
    ):
        if not segmentationNode or not segmentationNode.IsA(
            "vtkMRMLSegmentationNode"
        ):
            raise ValueError(_("Select a valid segmentation node."))
        segmentationNode.CreateDefaultDisplayNodes()
        segmentation = segmentationNode.GetSegmentation()
        displayNode = segmentationNode.GetDisplayNode()
        if not segmentation or not displayNode:
            raise ValueError(_("The segmentation does not have valid display data."))
        return segmentation, displayNode

    def setSegmentationSegmentVisibility(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
        visible: bool,
    ) -> None:
        segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        if not segmentId or not segmentation.GetSegment(segmentId):
            raise ValueError(_("The selected segment does not exist."))
        displayNode.SetVisibility(True)
        displayNode.SetSegmentVisibility(segmentId, bool(visible))

    def setAllSegmentationSegmentsVisibility(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        visible: bool,
    ) -> None:
        _segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        displayNode.SetVisibility(True)
        displayNode.SetAllSegmentsVisibility(bool(visible))

    def isolateSegmentationSegment(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> None:
        segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        if not segmentId or not segmentation.GetSegment(segmentId):
            raise ValueError(_("The selected segment does not exist."))
        displayNode.SetVisibility(True)
        displayNode.SetAllSegmentsVisibility(False)
        displayNode.SetSegmentVisibility(segmentId, True)

    def setSegmentationSegmentHighlight(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str | None,
        contextOpacity: float = 0.25,
    ) -> None:
        """Emphasize one segment using display opacity without changing masks."""

        segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        if segmentId is not None and not segmentation.GetSegment(segmentId):
            raise ValueError(_("The selected segment does not exist."))
        contextOpacity = self._validatedOpacity(contextOpacity)
        segmentIds = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(segmentIds)
        wasModifying = displayNode.StartModify()
        try:
            for index in range(segmentIds.GetNumberOfValues()):
                currentSegmentId = segmentIds.GetValue(index)
                isHighlighted = segmentId is None or currentSegmentId == segmentId
                displayNode.SetSegmentOpacity3D(
                    currentSegmentId,
                    1.0 if isHighlighted else contextOpacity,
                )
                displayNode.SetSegmentOpacity2DFill(
                    currentSegmentId,
                    1.0 if isHighlighted else contextOpacity,
                )
                displayNode.SetSegmentOpacity2DOutline(
                    currentSegmentId,
                    1.0 if isHighlighted else 0.65,
                )
        finally:
            displayNode.EndModify(wasModifying)

    def setSegmentationVisibility2D(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        visible: bool,
    ) -> None:
        _segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        displayNode.SetVisibility(True)
        displayNode.SetVisibility2D(bool(visible))

    def setSegmentationVisibility3D(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        visible: bool,
    ) -> None:
        _segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        displayNode.SetVisibility(True)
        displayNode.SetVisibility3D(bool(visible))

    def setSegmentationOpacity2D(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        opacity: float,
    ) -> None:
        _segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        opacity = self._validatedOpacity(opacity)
        displayNode.SetOpacity2DFill(opacity)
        displayNode.SetOpacity2DOutline(opacity)

    def setSegmentationOpacity3D(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        opacity: float,
    ) -> None:
        _segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        displayNode.SetOpacity3D(self._validatedOpacity(opacity))

    @staticmethod
    def _validatedOpacity(opacity: float) -> float:
        opacity = float(opacity)
        if not math.isfinite(opacity) or opacity < 0.0 or opacity > 1.0:
            raise ValueError(_("Segmentation opacity must be between 0 and 1."))
        return opacity

    def getVolumeMetadata(self, volumeNode: vtkMRMLScalarVolumeNode) -> dict[str, str]:
        if not volumeNode or not volumeNode.IsA("vtkMRMLScalarVolumeNode"):
            raise ValueError(_("Select a valid scalar CBCT volume."))

        imageData = volumeNode.GetImageData()
        if not imageData:
            raise ValueError(_("The selected volume does not contain image data."))

        dimensions = tuple(int(value) for value in imageData.GetDimensions())
        spacing = tuple(float(value) for value in volumeNode.GetSpacing())
        if any(value <= 0 for value in dimensions) or any(not math.isfinite(value) or value <= 0 for value in spacing):
            raise ValueError(_("The selected volume has invalid dimensions or spacing."))

        ijkToRas = vtk.vtkMatrix4x4()
        volumeNode.GetIJKToRASMatrix(ijkToRas)
        determinant = ijkToRas.Determinant()
        if not math.isfinite(determinant) or abs(determinant) < 1e-12:
            raise ValueError(_("The selected volume has invalid IJK-to-RAS geometry."))

        scalarRange = imageData.GetScalarRange()
        orientation = self._orientationDescription(ijkToRas)
        parentTransform = volumeNode.GetParentTransformNode()
        geometryStatus = _("Valid IJK-to-RAS geometry")
        if parentTransform:
            geometryStatus += _("; parent transform present")

        return {
            "name": volumeNode.GetName() or _("Unnamed volume"),
            "dimensions": f"{dimensions[0]} x {dimensions[1]} x {dimensions[2]} voxels",
            "spacing": f"{spacing[0]:.3f} x {spacing[1]:.3f} x {spacing[2]:.3f} mm",
            "scalarType": imageData.GetScalarTypeAsString(),
            "scalarRange": f"{scalarRange[0]:.3f} to {scalarRange[1]:.3f}",
            "orientation": orientation,
            "geometryStatus": geometryStatus,
        }

    @staticmethod
    def validateWindowsStagingRoot(stagingRoot: str) -> Path:
        """Validate an explicit local Windows drive path used for run artifacts."""

        if not stagingRoot:
            raise ValueError(_("Enter a Windows staging directory."))
        if stagingRoot.startswith("\\\\") or stagingRoot.startswith("//"):
            raise ValueError(
                _("UNC/network paths are not supported by the baseline WSL bridge.")
            )
        if not re.match(r"^[A-Za-z]:[\\/]", stagingRoot):
            raise ValueError(
                _("Use an absolute Windows drive path such as C:\\DENTOBOTRuns.")
            )
        return Path(stagingRoot)

    @staticmethod
    def validateStagingRoot(stagingRoot: str, executionMode: str) -> Path:
        """Validate the artifact root for the selected process boundary."""

        if executionMode == "wsl":
            return DENTOWorkflowLogic.validateWindowsStagingRoot(stagingRoot)
        if executionMode != "local":
            raise ValueError(_("Unsupported backend execution mode."))
        if not stagingRoot:
            raise ValueError(_("Enter an absolute Linux staging directory."))
        rootPath = Path(stagingRoot)
        if not rootPath.is_absolute():
            raise ValueError(_("Use an absolute Linux staging directory."))
        return rootPath

    @staticmethod
    def windowsPathToWslPath(windowsPath: str | Path) -> str:
        """Map an absolute Windows drive path to WSL's conventional /mnt path."""

        pathText = str(windowsPath)
        if pathText.startswith("\\\\") or pathText.startswith("//"):
            raise ValueError(_("UNC/network paths cannot be mapped by this bridge."))
        match = re.match(r"^([A-Za-z]):[\\/](.*)$", pathText)
        if not match:
            raise ValueError(_("Expected an absolute Windows drive path."))
        drive = match.group(1).lower()
        remainder = match.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{remainder}"

    @staticmethod
    def _wslExecutablePath() -> str:
        systemRoot = os.environ.get("SystemRoot", r"C:\Windows")
        return str(Path(systemRoot) / "System32" / "wsl.exe")

    def _buildWslPythonCommand(
        self,
        distribution: str,
        pythonPath: str,
        backendArguments: list[str],
    ) -> list[str]:
        distribution = distribution.strip()
        pythonPath = pythonPath.strip()
        if not distribution:
            raise ValueError(_("The WSL distribution name is required."))
        if not pythonPath.startswith("/"):
            raise ValueError(_("The WSL Python path must be an absolute Linux path."))
        return [
            self._wslExecutablePath(),
            "--distribution",
            distribution,
            "--exec",
            pythonPath,
            "-m",
            self.BACKEND_MODULE,
            *backendArguments,
        ]

    def _buildBackendPythonCommand(
        self,
        executionMode: str,
        distribution: str,
        pythonPath: str,
        backendArguments: list[str],
    ) -> list[str]:
        if executionMode == "wsl":
            return self._buildWslPythonCommand(
                distribution,
                pythonPath,
                backendArguments,
            )
        if executionMode != "local":
            raise ValueError(_("Unsupported backend execution mode."))
        if not pythonPath.startswith("/"):
            raise ValueError(_("The backend Python path must be absolute."))
        return [pythonPath, "-m", self.BACKEND_MODULE, *backendArguments]

    @staticmethod
    def _backendVisiblePath(path: Path, executionMode: str) -> str:
        if executionMode == "wsl":
            return DENTOWorkflowLogic.windowsPathToWslPath(path)
        if executionMode == "local":
            return str(path)
        raise ValueError(_("Unsupported backend execution mode."))

    def buildHealthCommand(
        self,
        distribution: str,
        pythonPath: str,
        executionMode: str = "wsl",
        device: str = "cuda:0",
    ) -> list[str]:
        """Build Bridge A without invoking a shell or activating an environment."""

        return self._buildBackendPythonCommand(
            executionMode,
            distribution,
            pythonPath,
            ["health", "--json", "--require-device", device],
        )

    def buildRoundTripCommand(
        self,
        distribution: str,
        pythonPath: str,
        inputPath: Path,
        outputPath: Path,
        resultJsonPath: Path,
        runId: str,
        executionMode: str = "wsl",
    ) -> list[str]:
        """Build Bridge B with explicit arguments and WSL-visible artifact paths."""

        return self._buildBackendPythonCommand(
            executionMode,
            distribution,
            pythonPath,
            [
                "roundtrip",
                "--input",
                self._backendVisiblePath(inputPath, executionMode),
                "--output",
                self._backendVisiblePath(outputPath, executionMode),
                "--result-json",
                self._backendVisiblePath(resultJsonPath, executionMode),
                "--run-id",
                runId,
            ],
        )

    def buildTeethSegmentationCommand(
        self,
        distribution: str,
        pythonPath: str,
        inputPath: Path,
        outputPath: Path,
        resultJsonPath: Path,
        runId: str,
        executionMode: str = "wsl",
        device: str = "cuda:0",
    ) -> list[str]:
        """Build Bridge C without shell activation or implicit CPU fallback."""

        return self._buildBackendPythonCommand(
            executionMode,
            distribution,
            pythonPath,
            [
                "segment-teeth",
                "--input",
                self._backendVisiblePath(inputPath, executionMode),
                "--output",
                self._backendVisiblePath(outputPath, executionMode),
                "--result-json",
                self._backendVisiblePath(resultJsonPath, executionMode),
                "--run-id",
                runId,
                "--device",
                device,
            ],
        )

    def createRoundTripRunPaths(
        self,
        stagingRoot: str,
        runId: str,
        executionMode: str = "wsl",
    ) -> dict[str, Path]:
        """Create one isolated artifact directory for a bridge run."""

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", runId):
            raise ValueError(_("The generated run ID is invalid."))
        rootPath = self.validateStagingRoot(stagingRoot, executionMode)
        runDirectory = rootPath / runId
        runDirectory.mkdir(parents=True, exist_ok=False)
        return {
            "directory": runDirectory,
            "input": runDirectory / "input.nii",
            "output": runDirectory / "roundtrip.nii",
            "result": runDirectory / "result.json",
        }

    def createTeethSegmentationRunPaths(
        self,
        stagingRoot: str,
        runId: str,
        executionMode: str = "wsl",
    ) -> dict[str, Path]:
        """Create one isolated artifact directory for a Bridge C inference."""

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", runId):
            raise ValueError(_("The generated run ID is invalid."))
        rootPath = self.validateStagingRoot(stagingRoot, executionMode)
        runDirectory = rootPath / runId
        runDirectory.mkdir(parents=True, exist_ok=False)
        return {
            "directory": runDirectory,
            "input": runDirectory / "input.nii",
            "output": runDirectory / "teeth-segmentation.nii",
            "result": runDirectory / "result.json",
        }

    @staticmethod
    def findJsonReport(lines: list[str], command: str) -> dict | None:
        """Find the last structured backend report among process output lines."""

        for line in reversed(lines):
            try:
                document = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(document, dict) and document.get("command") == command:
                return document
        return None

    @staticmethod
    def validateTeethSegmentationReport(
        report: dict,
        runId: str,
        expectedDevice: str | None = None,
    ) -> None:
        """Validate the schema before any returned label map enters MRML."""

        if not isinstance(report, dict):
            raise ValueError(_("The backend segmentation report is not a JSON object."))
        if (
            report.get("schemaVersion") != "1.0"
            or report.get("command") != "segment-teeth"
        ):
            raise ValueError(_("The backend segmentation contract is not supported."))
        if report.get("runId") != runId:
            raise ValueError(_("The segmentation result run ID does not match."))
        if report.get("status") not in ("ok", "error"):
            raise ValueError(_("The segmentation report has an invalid status."))
        if not isinstance(report.get("errors"), list):
            raise ValueError(_("The segmentation report error list is invalid."))
        if report.get("status") != "ok":
            return

        if not report.get("geometryMatch"):
            raise ValueError(_("Backend segmentation geometry validation did not pass."))
        if not report.get("labelValidationPassed"):
            raise ValueError(_("Backend segmentation label validation did not pass."))

        model = report.get("model")
        device = report.get("device")
        labels = report.get("labels")
        metrics = report.get("metrics")
        backend = report.get("backend")
        if not isinstance(model, dict) or model.get("task") != "teeth":
            raise ValueError(_("The backend did not report the required teeth model."))
        if model.get("taskId") != 113 or model.get("cropTaskId") != 115:
            raise ValueError(_("The backend model task identifiers are unexpected."))
        if not isinstance(device, dict):
            raise ValueError(_("The segmentation device metadata is missing."))
        requestedDevice = device.get("requested")
        actualDevice = device.get("actual")
        if (
            requestedDevice not in ("cpu", "cuda:0")
            or actualDevice != requestedDevice
            or (expectedDevice and requestedDevice != expectedDevice)
        ):
            raise ValueError(_("The segmentation device does not match the request."))
        if (
            not isinstance(backend, dict)
            or not isinstance(backend.get("packages"), dict)
            or not backend["packages"].get("TotalSegmentator")
        ):
            raise ValueError(_("TotalSegmentator version metadata is missing."))
        if not isinstance(labels, list) or not labels:
            raise ValueError(_("The TotalSegmentator teeth label map is missing."))
        if not isinstance(metrics, dict):
            raise ValueError(_("Segmentation metrics are missing."))

        labelIds = []
        for label in labels:
            if (
                not isinstance(label, dict)
                or not isinstance(label.get("id"), int)
                or label["id"] <= 0
                or not isinstance(label.get("name"), str)
                or not label["name"]
            ):
                raise ValueError(_("The segmentation label map is invalid."))
            labelIds.append(label["id"])
        if len(labelIds) != len(set(labelIds)):
            raise ValueError(_("The segmentation label map contains duplicate IDs."))
        labelNamesById = {
            int(label["id"]): str(label["name"])
            for label in labels
        }

        detectedLabelIds = metrics.get("detectedLabelIds")
        segmentCount = metrics.get("segmentCount")
        if (
            not isinstance(detectedLabelIds, list)
            or not detectedLabelIds
            or any(
                not isinstance(labelId, int) or labelId not in labelIds
                for labelId in detectedLabelIds
            )
            or len(detectedLabelIds) != len(set(detectedLabelIds))
        ):
            raise ValueError(_("Detected segmentation label IDs are invalid."))
        if segmentCount != len(detectedLabelIds):
            raise ValueError(_("The reported segmentation count is inconsistent."))
        perLabel = metrics.get("perLabel")
        if not isinstance(perLabel, list) or len(perLabel) != segmentCount:
            raise ValueError(_("Per-label segmentation metrics are inconsistent."))
        perLabelIds = []
        for labelMetric in perLabel:
            if (
                not isinstance(labelMetric, dict)
                or labelMetric.get("id") not in detectedLabelIds
                or labelMetric.get("name")
                != labelNamesById.get(labelMetric.get("id"))
                or not isinstance(labelMetric.get("voxelCount"), int)
                or labelMetric["voxelCount"] <= 0
                or not isinstance(labelMetric.get("volumeMm3"), (int, float))
                or not math.isfinite(float(labelMetric["volumeMm3"]))
                or float(labelMetric["volumeMm3"]) <= 0
            ):
                raise ValueError(_("A per-label segmentation metric is invalid."))
            perLabelIds.append(labelMetric["id"])
        if sorted(perLabelIds) != sorted(detectedLabelIds):
            raise ValueError(_("Per-label metric IDs are inconsistent."))
        if sum(
            int(labelMetric["voxelCount"])
            for labelMetric in perLabel
        ) != int(metrics.get("foregroundVoxelCount", -1)):
            raise ValueError(_("Foreground and per-label voxel counts differ."))
        for metricName in (
            "foregroundVoxelCount",
            "foregroundVolumeMm3",
            "voxelVolumeMm3",
        ):
            metricValue = metrics.get(metricName)
            if (
                not isinstance(metricValue, (int, float))
                or not math.isfinite(float(metricValue))
                or float(metricValue) <= 0
            ):
                raise ValueError(
                    _("The reported segmentation metric %1 is invalid.")
                    .replace("%1", metricName)
                )
        for metricName in (
            "runtimeSeconds",
            "inferenceSeconds",
        ):
            metricValue = report.get(metricName)
            if (
                not isinstance(metricValue, (int, float))
                or not math.isfinite(float(metricValue))
                or float(metricValue) < 0
            ):
                raise ValueError(
                    _("The reported inference metric %1 is invalid.")
                    .replace("%1", metricName)
                )
        peakAllocatedBytes = device.get("peakAllocatedBytes")
        if requestedDevice == "cuda:0":
            if not isinstance(peakAllocatedBytes, int) or peakAllocatedBytes < 0:
                raise ValueError(_("Peak GPU memory metadata is invalid."))
        elif peakAllocatedBytes is not None:
            raise ValueError(_("CPU inference must not report CUDA memory."))

    @staticmethod
    def validateLabelmapAgainstReport(labelmapNode, report: dict) -> None:
        """Verify imported MRML label values against the backend JSON."""

        if (
            not labelmapNode
            or not labelmapNode.IsA("vtkMRMLLabelMapVolumeNode")
            or not labelmapNode.GetImageData()
        ):
            raise ValueError(_("The returned node is not a valid label map volume."))
        labelArray = slicer.util.arrayFromVolume(labelmapNode)
        if not np.issubdtype(labelArray.dtype, np.integer):
            raise ValueError(_("The returned label map does not use integer voxels."))
        uniqueValues, voxelCounts = np.unique(labelArray, return_counts=True)
        actualCounts = {
            int(value): int(count)
            for value, count in zip(uniqueValues.tolist(), voxelCounts.tolist())
            if int(value) != 0
        }
        actualLabelIds = sorted(actualCounts)
        expectedLabelIds = sorted(
            int(value)
            for value in report["metrics"]["detectedLabelIds"]
        )
        if actualLabelIds != expectedLabelIds:
            raise ValueError(
                _("Imported label values do not match the validated backend report.")
            )
        expectedCounts = {
            int(labelMetric["id"]): int(labelMetric["voxelCount"])
            for labelMetric in report["metrics"]["perLabel"]
        }
        if actualCounts != expectedCounts:
            raise ValueError(
                _("Imported label voxel counts do not match the backend report.")
            )

    @staticmethod
    def createTeethColorTable(labels: list[dict], runId: str):
        """Create deterministic label names and colors for segmentation import."""

        if not labels:
            raise ValueError(_("Cannot create a color table without labels."))
        colorTableNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLColorTableNode",
            f"DENTOBOT_TeethColors_{runId[:8]}",
        )
        try:
            colorTableNode.SetTypeToUser()
            colorTableNode.SetNumberOfColors(
                max(int(label["id"]) for label in labels) + 1
            )
            colorTableNode.SetColor(0, "Background", 0.0, 0.0, 0.0, 0.0)
            for label in labels:
                labelId = int(label["id"])
                labelName = str(label["name"])
                hue = (labelId * 0.618033988749895) % 1.0
                red, green, blue = colorsys.hsv_to_rgb(hue, 0.68, 0.95)
                if not colorTableNode.SetColor(
                    labelId,
                    labelName,
                    red,
                    green,
                    blue,
                    1.0,
                ):
                    raise RuntimeError(
                        _("Could not assign color for teeth label %1.")
                        .replace("%1", str(labelId))
                    )
            return colorTableNode
        except Exception:
            slicer.mrmlScene.RemoveNode(colorTableNode)
            raise

    @staticmethod
    def validateMatchingVolumeGeometry(
        sourceVolume: vtkMRMLScalarVolumeNode,
        outputVolume: vtkMRMLScalarVolumeNode,
        tolerance: float = 1e-4,
        requireMatchingScalarType: bool = True,
    ) -> None:
        """Reject a returned MRML volume whose voxel grid differs from its source."""

        for volumeNode in (sourceVolume, outputVolume):
            if (
                not volumeNode
                or not volumeNode.IsA("vtkMRMLScalarVolumeNode")
                or not volumeNode.GetImageData()
            ):
                raise ValueError(_("Both bridge volumes must be valid scalar volumes."))

        sourceImage = sourceVolume.GetImageData()
        outputImage = outputVolume.GetImageData()
        if sourceImage.GetDimensions() != outputImage.GetDimensions():
            raise ValueError(_("Returned volume dimensions do not match the source."))
        if (
            requireMatchingScalarType
            and sourceImage.GetScalarType() != outputImage.GetScalarType()
        ):
            raise ValueError(_("Returned volume scalar type does not match the source."))

        sourceMatrix = vtk.vtkMatrix4x4()
        outputMatrix = vtk.vtkMatrix4x4()
        sourceVolume.GetIJKToRASMatrix(sourceMatrix)
        outputVolume.GetIJKToRASMatrix(outputMatrix)
        for row in range(4):
            for column in range(4):
                if (
                    abs(
                        sourceMatrix.GetElement(row, column)
                        - outputMatrix.GetElement(row, column)
                    )
                    > tolerance
                ):
                    raise ValueError(
                        _("Returned volume IJK-to-RAS geometry does not match the source.")
                    )

    @staticmethod
    def _orientationDescription(ijkToRas: vtk.vtkMatrix4x4) -> str:
        positiveLabels = ("R", "A", "S")
        negativeLabels = ("L", "P", "I")
        axisNames = ("I", "J", "K")
        descriptions = []

        for column, axisName in enumerate(axisNames):
            direction = [ijkToRas.GetElement(row, column) for row in range(3)]
            dominantAxis = max(range(3), key=lambda row: abs(direction[row]))
            label = (
                positiveLabels[dominantAxis]
                if direction[dominantAxis] >= 0
                else negativeLabels[dominantAxis]
            )
            descriptions.append(f"{axisName}->{label}")

        return ", ".join(descriptions) + " (Slicer RAS)"


class DENTOWorkflowTest(ScriptedLoadableModuleTest):
    """Slicer-native tests that do not launch WSL or external inference."""

    def setUp(self) -> None:
        slicer.mrmlScene.Clear(0)

    def runTest(self) -> None:
        self.setUp()
        try:
            self.test_DENTOWorkflowVolumeMetadataAndParameterNode()
            self.test_DENTOWorkflowBridgeContracts()
            self.test_DENTOWorkflowSegmentationReviewLogic()
            self.test_DENTOWorkflowTargetToothAndTrajectoryLogic()
        finally:
            self.setUp()

    def test_DENTOWorkflowVolumeMetadataAndParameterNode(self) -> None:
        logic = DENTOWorkflowLogic()

        with self.assertRaisesRegex(ValueError, "valid scalar"):
            logic.getVolumeMetadata(None)

        emptyVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", "EmptyVolume")
        with self.assertRaisesRegex(ValueError, "does not contain image data"):
            logic.getVolumeMetadata(emptyVolume)

        imageData = vtk.vtkImageData()
        imageData.SetDimensions(4, 5, 6)
        imageData.AllocateScalars(vtk.VTK_SHORT, 1)
        imageData.GetPointData().GetScalars().FillComponent(0, 42)

        volumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", "SyntheticCBCT")
        volumeNode.SetAndObserveImageData(imageData)
        volumeNode.SetSpacing(0.2, 0.3, 0.4)

        metadata = logic.getVolumeMetadata(volumeNode)
        self.assertEqual(metadata["dimensions"], "4 x 5 x 6 voxels")
        self.assertEqual(metadata["spacing"], "0.200 x 0.300 x 0.400 mm")
        self.assertEqual(metadata["orientation"], "I->R, J->A, K->S (Slicer RAS)")
        self.assertIn("Valid", metadata["geometryStatus"])
        self.assertEqual(logic.getLatestScalarVolumeNode(), volumeNode)

        parameterNode = logic.getParameterNode()
        parameterNode.caseName = "DeidentifiedCase"
        parameterNode.inputVolume = volumeNode
        parameterNode.wslDistribution = "Ubuntu-24.04"
        parameterNode.wslPythonPath = "/opt/conda/envs/dentobot/bin/python"
        parameterNode.stagingRoot = r"C:\DENTOBOTRuns"
        parameterNode.inferenceDevice = "cuda:0"
        parameterNode.roundTripVolume = volumeNode
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "SyntheticTeeth",
        )
        parameterNode.teethSegmentation = segmentationNode
        self.assertEqual(parameterNode.caseName, "DeidentifiedCase")
        self.assertEqual(parameterNode.inputVolume.GetID(), volumeNode.GetID())
        self.assertEqual(parameterNode.wslDistribution, "Ubuntu-24.04")
        self.assertEqual(
            parameterNode.wslPythonPath,
            "/opt/conda/envs/dentobot/bin/python",
        )
        self.assertEqual(parameterNode.inferenceDevice, "cuda:0")
        self.assertEqual(parameterNode.roundTripVolume.GetID(), volumeNode.GetID())
        self.assertEqual(
            parameterNode.teethSegmentation.GetID(),
            segmentationNode.GetID(),
        )

        self.delayDisplay("DENTOWorkflow Step 0 logic tests passed")

    def test_DENTOWorkflowBridgeContracts(self) -> None:
        logic = DENTOWorkflowLogic()

        self.assertEqual(
            logic.windowsPathToWslPath(r"C:\DENTOBOTRuns\a b\input.nii.gz"),
            "/mnt/c/DENTOBOTRuns/a b/input.nii.gz",
        )
        with self.assertRaisesRegex(ValueError, "absolute Windows"):
            logic.windowsPathToWslPath(r"relative\input.nii.gz")
        with self.assertRaisesRegex(ValueError, "UNC"):
            logic.windowsPathToWslPath(r"\\server\share\input.nii.gz")

        healthCommand = logic.buildHealthCommand(
            "Ubuntu-24.04",
            "/opt/conda/envs/dentobot/bin/python",
        )
        self.assertIsInstance(healthCommand, list)
        self.assertIn("--exec", healthCommand)
        self.assertIn("dentobot_inference", healthCommand)
        self.assertEqual(
            healthCommand[-4:],
            ["health", "--json", "--require-device", "cuda:0"],
        )

        localHealthCommand = logic.buildHealthCommand(
            "",
            "/opt/dentobot-venv/bin/python",
            executionMode="local",
            device="cpu",
        )
        self.assertEqual(localHealthCommand[0], "/opt/dentobot-venv/bin/python")
        self.assertNotIn("--exec", localHealthCommand)
        self.assertEqual(
            localHealthCommand[-4:],
            ["health", "--json", "--require-device", "cpu"],
        )

        inputPath = Path(r"C:\DENTOBOTRuns\run-1\input.nii.gz")
        outputPath = Path(r"C:\DENTOBOTRuns\run-1\roundtrip.nii.gz")
        resultPath = Path(r"C:\DENTOBOTRuns\run-1\result.json")
        roundTripCommand = logic.buildRoundTripCommand(
            "Ubuntu-24.04",
            "/opt/conda/envs/dentobot/bin/python",
            inputPath,
            outputPath,
            resultPath,
            "run-1",
        )
        self.assertIn("/mnt/c/DENTOBOTRuns/run-1/input.nii.gz", roundTripCommand)
        self.assertEqual(roundTripCommand[-2:], ["--run-id", "run-1"])

        teethCommand = logic.buildTeethSegmentationCommand(
            "Ubuntu-24.04",
            "/opt/conda/envs/dentobot/bin/python",
            Path(r"C:\DENTOBOTRuns\run-2\input.nii"),
            Path(r"C:\DENTOBOTRuns\run-2\teeth-segmentation.nii"),
            Path(r"C:\DENTOBOTRuns\run-2\result.json"),
            "run-2",
        )
        self.assertIn("segment-teeth", teethCommand)
        self.assertIn(
            "/mnt/c/DENTOBOTRuns/run-2/teeth-segmentation.nii",
            teethCommand,
        )
        self.assertIn("--run-id", teethCommand)
        self.assertEqual(teethCommand[-2:], ["--device", "cuda:0"])
        localTeethCommand = logic.buildTeethSegmentationCommand(
            "",
            "/opt/dentobot-venv/bin/python",
            Path("/workspace/data/run-3/input.nii"),
            Path("/workspace/data/run-3/teeth-segmentation.nii"),
            Path("/workspace/data/run-3/result.json"),
            "run-3",
            executionMode="local",
            device="cpu",
        )
        self.assertEqual(localTeethCommand[0], "/opt/dentobot-venv/bin/python")
        self.assertIn("/workspace/data/run-3/input.nii", localTeethCommand)
        self.assertEqual(localTeethCommand[-2:], ["--device", "cpu"])

        healthReport = {"command": "health", "status": "ok"}
        self.assertEqual(
            logic.findJsonReport(["noise", json.dumps(healthReport)], "health"),
            healthReport,
        )

        imageData = vtk.vtkImageData()
        imageData.SetDimensions(3, 4, 5)
        imageData.AllocateScalars(vtk.VTK_SHORT, 1)
        sourceVolume = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode",
            "BridgeSource",
        )
        sourceVolume.SetAndObserveImageData(imageData)
        sourceVolume.SetSpacing(0.2, 0.3, 0.4)

        outputImageData = vtk.vtkImageData()
        outputImageData.DeepCopy(imageData)
        outputVolume = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode",
            "BridgeOutput",
        )
        outputVolume.SetAndObserveImageData(outputImageData)
        outputVolume.SetSpacing(0.2, 0.3, 0.4)
        logic.validateMatchingVolumeGeometry(sourceVolume, outputVolume)

        outputVolume.SetSpacing(0.21, 0.3, 0.4)
        with self.assertRaisesRegex(ValueError, "IJK-to-RAS"):
            logic.validateMatchingVolumeGeometry(sourceVolume, outputVolume)

        teethReport = {
            "schemaVersion": "1.0",
            "command": "segment-teeth",
            "runId": "run-2",
            "status": "ok",
            "errors": [],
            "geometryMatch": True,
            "labelValidationPassed": True,
            "model": {
                "task": "teeth",
                "taskId": 113,
                "cropTaskId": 115,
            },
            "device": {
                "requested": "cuda:0",
                "actual": "cuda:0",
                "peakAllocatedBytes": 1024,
            },
            "backend": {
                "packages": {
                    "TotalSegmentator": "2.11.0",
                },
            },
            "labels": [
                {"id": 1, "name": "lower_jawbone"},
                {"id": 2, "name": "upper_jawbone"},
            ],
            "metrics": {
                "detectedLabelIds": [1],
                "segmentCount": 1,
                "foregroundVoxelCount": 1,
                "foregroundVolumeMm3": 0.024,
                "voxelVolumeMm3": 0.024,
                "perLabel": [
                    {
                        "id": 1,
                        "name": "lower_jawbone",
                        "voxelCount": 1,
                        "volumeMm3": 0.024,
                    },
                ],
            },
            "runtimeSeconds": 12.0,
            "inferenceSeconds": 10.0,
        }
        logic.validateTeethSegmentationReport(teethReport, "run-2")
        cpuReport = json.loads(json.dumps(teethReport))
        cpuReport["device"] = {
            "requested": "cpu",
            "actual": "cpu",
            "peakAllocatedBytes": None,
        }
        logic.validateTeethSegmentationReport(
            cpuReport,
            "run-2",
            expectedDevice="cpu",
        )
        cpuMetricsNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "CpuMetrics",
        )
        cpuMetricsNode.SetAttribute("DENTOBOT.SegmentCount", "1")
        cpuMetricsNode.SetAttribute("DENTOBOT.RuntimeSeconds", "12.0")
        cpuMetricsNode.SetAttribute("DENTOBOT.ForegroundVolumeMm3", "24.0")
        cpuMetricsNode.SetAttribute("DENTOBOT.ActualDevice", "cpu")
        cpuMetricsNode.SetAttribute("DENTOBOT.PeakAllocatedBytes", "")
        self.assertEqual(
            DENTOWorkflowWidget._teethMetricsText(cpuMetricsNode),
            "1 segments; 12.0 s; 0.02 cm^3 foreground; cpu",
        )
        with self.assertRaisesRegex(ValueError, "run ID"):
            logic.validateTeethSegmentationReport(teethReport, "different-run")

        labelImageData = vtk.vtkImageData()
        labelImageData.SetDimensions(3, 4, 5)
        labelImageData.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
        labelImageData.GetPointData().GetScalars().FillComponent(0, 0)
        labelmapNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLabelMapVolumeNode",
            "BridgeLabels",
        )
        labelmapNode.SetAndObserveImageData(labelImageData)
        labelmapNode.SetSpacing(0.2, 0.3, 0.4)
        labelArray = slicer.util.arrayFromVolume(labelmapNode)
        labelArray[0, 0, 0] = 1
        slicer.util.arrayFromVolumeModified(labelmapNode)
        logic.validateMatchingVolumeGeometry(
            sourceVolume,
            labelmapNode,
            requireMatchingScalarType=False,
        )
        logic.validateLabelmapAgainstReport(labelmapNode, teethReport)

        colorTableNode = logic.createTeethColorTable(
            teethReport["labels"],
            "run-2",
        )
        self.assertEqual(colorTableNode.GetColorName(1), "lower_jawbone")
        slicer.mrmlScene.RemoveNode(colorTableNode)

        self.delayDisplay("DENTOWorkflow bridge contract tests passed")

    def test_DENTOWorkflowSegmentationReviewLogic(self) -> None:
        logic = DENTOWorkflowLogic()

        with self.assertRaisesRegex(ValueError, "segment name"):
            logic.describeSegmentForReview("")

        toothDescriptor = logic.describeSegmentForReview(
            "upper_right_first_molar_fdi16"
        )
        self.assertEqual(toothDescriptor["category"], "Teeth")
        self.assertEqual(toothDescriptor["fdiNumber"], "16")
        self.assertEqual(
            toothDescriptor["displayName"],
            "FDI 16 \u2014 Upper Right First Molar",
        )

        pulpDescriptor = logic.describeSegmentForReview(
            "lower_left_canine_pulp_fdi133"
        )
        self.assertEqual(pulpDescriptor["category"], "Pulp and root canals")
        self.assertEqual(pulpDescriptor["fdiNumber"], "33")
        self.assertIn("133", pulpDescriptor["searchText"])

        canalDescriptor = logic.describeSegmentForReview(
            "left_inferior_alveolar_canal"
        )
        self.assertEqual(
            canalDescriptor["category"],
            "Neural and mandibular canals",
        )
        self.assertEqual(
            logic.describeSegmentForReview("upper_jawbone")["category"],
            "Jaws",
        )
        self.assertEqual(
            logic.describeSegmentForReview("left_maxillary_sinus")["category"],
            "Sinuses and airway",
        )
        self.assertEqual(
            logic.describeSegmentForReview("implant")["category"],
            "Restorations and implants",
        )

        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "ReviewSegmentation",
        )
        segmentationNode.SetAttribute(
            "DENTOBOT.BridgeOperation",
            "segment-teeth",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        segmentSpecifications = (
            ("tooth-16", "upper_right_first_molar_fdi16", 11),
            ("pulp-33", "lower_left_canine_pulp_fdi133", 63),
            ("jaw", "upper_jawbone", 2),
        )
        for segmentId, segmentName, labelValue in segmentSpecifications:
            segment = slicer.vtkSegment()
            segment.SetName(segmentName)
            segment.SetLabelValue(labelValue)
            segmentationNode.GetSegmentation().AddSegment(segment, segmentId)

        self.assertEqual(logic.getLatestTeethSegmentationNode(), segmentationNode)
        records = logic.getSegmentationReviewRecords(segmentationNode)
        self.assertEqual(len(records), 3)
        self.assertEqual(
            [record["category"] for record in records],
            ["Teeth", "Pulp and root canals", "Jaws"],
        )
        self.assertEqual(records[0]["segmentId"], "tooth-16")

        displayNode = segmentationNode.GetDisplayNode()
        logic.setAllSegmentationSegmentsVisibility(segmentationNode, False)
        for segmentId, _segmentName, _labelValue in segmentSpecifications:
            self.assertFalse(displayNode.GetSegmentVisibility(segmentId))

        logic.setSegmentationSegmentVisibility(
            segmentationNode,
            "pulp-33",
            True,
        )
        self.assertTrue(displayNode.GetSegmentVisibility("pulp-33"))
        with self.assertRaisesRegex(ValueError, "does not exist"):
            logic.setSegmentationSegmentVisibility(
                segmentationNode,
                "missing",
                True,
            )

        logic.setAllSegmentationSegmentsVisibility(segmentationNode, True)
        logic.setSegmentationSegmentHighlight(
            segmentationNode,
            "tooth-16",
        )
        self.assertAlmostEqual(
            displayNode.GetSegmentOpacity3D("tooth-16"),
            1.0,
        )
        self.assertAlmostEqual(
            displayNode.GetSegmentOpacity3D("jaw"),
            0.25,
        )
        logic.setSegmentationSegmentHighlight(segmentationNode, None)
        self.assertAlmostEqual(
            displayNode.GetSegmentOpacity3D("jaw"),
            1.0,
        )

        logic.isolateSegmentationSegment(segmentationNode, "jaw")
        self.assertTrue(displayNode.GetSegmentVisibility("jaw"))
        self.assertFalse(displayNode.GetSegmentVisibility("tooth-16"))
        self.assertFalse(displayNode.GetSegmentVisibility("pulp-33"))

        logic.setSegmentationVisibility2D(segmentationNode, False)
        logic.setSegmentationVisibility3D(segmentationNode, True)
        self.assertFalse(displayNode.GetVisibility2D())
        self.assertTrue(displayNode.GetVisibility3D())

        logic.setSegmentationOpacity2D(segmentationNode, 0.35)
        logic.setSegmentationOpacity3D(segmentationNode, 0.65)
        self.assertAlmostEqual(displayNode.GetOpacity2DFill(), 0.35)
        self.assertAlmostEqual(displayNode.GetOpacity2DOutline(), 0.35)
        self.assertAlmostEqual(displayNode.GetOpacity3D(), 0.65)
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            logic.setSegmentationOpacity3D(segmentationNode, 1.1)

        sourceVolume = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode",
            "ReviewSourceCBCT",
        )
        sourceImageData = vtk.vtkImageData()
        sourceImageData.SetDimensions(3, 3, 3)
        sourceImageData.AllocateScalars(vtk.VTK_SHORT, 1)
        sourceImageData.GetPointData().GetScalars().FillComponent(0, 0)
        sourceVolume.SetAndObserveImageData(sourceImageData)
        reviewReport = {
            "schemaVersion": "1.0",
            "command": "segment-teeth",
            "runId": "review-run",
            "status": "ok",
            "errors": [],
            "geometryMatch": True,
            "labelValidationPassed": True,
            "model": {
                "task": "teeth",
                "taskId": 113,
                "sourceDataset": "ToothFairy3",
                "cropTask": "craniofacial_structures",
                "cropTaskId": 115,
            },
            "device": {
                "requested": "cuda:0",
                "actual": "cuda:0",
                "peakAllocatedBytes": 2147483648,
            },
            "backend": {
                "name": "dentobot-inference",
                "version": "0.2.0",
                "pythonVersion": "3.10.20",
                "packages": {
                    "TotalSegmentator": "2.16.0",
                    "torch": "2.10.0+cu130",
                },
            },
            "labels": [
                {"id": 11, "name": "upper_right_first_molar_fdi16"},
                {"id": 63, "name": "lower_left_canine_pulp_fdi133"},
                {"id": 2, "name": "upper_jawbone"},
            ],
            "metrics": {
                "detectedLabelIds": [2, 11, 63],
                "segmentCount": 3,
                "foregroundVoxelCount": 600,
                "foregroundVolumeMm3": 75.0,
                "voxelVolumeMm3": 0.125,
                "perLabel": [
                    {
                        "id": 2,
                        "name": "upper_jawbone",
                        "voxelCount": 300,
                        "volumeMm3": 37.5,
                    },
                    {
                        "id": 11,
                        "name": "upper_right_first_molar_fdi16",
                        "voxelCount": 200,
                        "volumeMm3": 25.0,
                    },
                    {
                        "id": 63,
                        "name": "lower_left_canine_pulp_fdi133",
                        "voxelCount": 100,
                        "volumeMm3": 12.5,
                    },
                ],
            },
            "runtimeSeconds": 75.2,
            "inferenceSeconds": 70.1,
            "startedAtUtc": "2026-07-24T08:00:00+00:00",
            "completedAtUtc": "2026-07-24T08:01:15.200000+00:00",
        }
        metadataWarning = logic.applyTeethSegmentationReviewMetadata(
            segmentationNode,
            sourceVolume,
            reviewReport,
            resultMetadataPath=Path(r"C:\DENTOBOTRuns\review-run\result.json"),
            segmentationNiftiPath=Path(
                r"C:\DENTOBOTRuns\review-run\teeth-segmentation.nii"
            ),
        )
        self.assertEqual(metadataWarning, "")
        self.assertEqual(
            segmentationNode.GetNodeReference(
                logic.SOURCE_VOLUME_REFERENCE_ROLE
            ),
            sourceVolume,
        )
        self.assertEqual(
            segmentationNode.GetAttribute("DENTOBOT.ReviewMetadataStatus"),
            "complete",
        )
        self.assertEqual(
            logic.getSegmentationReviewState(segmentationNode),
            "Unreviewed",
        )

        toothDetails = logic.getSegmentationSegmentDetails(
            segmentationNode,
            "tooth-16",
        )
        self.assertEqual(toothDetails["labelId"], 11)
        self.assertEqual(toothDetails["voxelCount"], 200)
        self.assertAlmostEqual(toothDetails["volumeMm3"], 25.0)
        self.assertEqual(toothDetails["fdiNumber"], "16")

        provenance = logic.getSegmentationProvenance(segmentationNode)
        self.assertEqual(provenance["runId"], "review-run")
        self.assertEqual(provenance["sourceVolume"], "ReviewSourceCBCT")
        self.assertIn("dentobot-inference 0.2.0", provenance["backend"])
        self.assertIn("TotalSegmentator 2.16.0", provenance["backend"])
        self.assertIn("ToothFairy3", provenance["model"])
        self.assertEqual(provenance["device"], "cuda:0")

        reviewTimestamp = "2026-07-24T09:00:00+00:00"
        logic.setSegmentationReviewState(
            segmentationNode,
            "Reviewed",
            updatedUtc=reviewTimestamp,
        )
        self.assertEqual(
            logic.getSegmentationReviewState(segmentationNode),
            "Reviewed",
        )
        self.assertEqual(
            segmentationNode.GetAttribute("DENTOBOT.ReviewUpdatedUtc"),
            reviewTimestamp,
        )
        self.assertEqual(
            segmentationNode.GetAttribute(
                "DENTOBOT.SegmentMetricsValidity"
            ),
            "current",
        )
        with self.assertRaisesRegex(ValueError, "review state"):
            logic.setSegmentationReviewState(
                segmentationNode,
                "Clinically Validated",
            )

        with self.assertRaisesRegex(ValueError, "does not exist"):
            logic.beginSegmentationCorrection(
                segmentationNode,
                "missing",
            )
        correctionTimestamp = "2026-07-24T09:15:00+00:00"
        handoff = logic.beginSegmentationCorrection(
            segmentationNode,
            "tooth-16",
            startedUtc=correctionTimestamp,
        )
        self.assertEqual(handoff["segmentationNode"], segmentationNode)
        self.assertEqual(handoff["sourceVolume"], sourceVolume)
        self.assertEqual(handoff["segmentId"], "tooth-16")
        self.assertEqual(
            logic.getSegmentationReviewState(segmentationNode),
            "Needs Correction",
        )
        self.assertEqual(
            segmentationNode.GetAttribute("DENTOBOT.CorrectionStartedUtc"),
            correctionTimestamp,
        )
        self.assertEqual(
            logic.getSegmentationSegmentDetails(
                segmentationNode,
                "tooth-16",
            )["metricsValidity"],
            "pre-correction-inference",
        )
        self.assertEqual(
            logic.getSegmentationProvenance(segmentationNode)[
                "correctionActivityUtc"
            ],
            correctionTimestamp,
        )

        logic.setSegmentationReviewState(
            segmentationNode,
            "Reviewed",
            updatedUtc="2026-07-24T09:20:00+00:00",
        )
        self.assertIsNone(
            segmentationNode.GetAttribute(
                "DENTOBOT.ReviewInvalidationReason"
            )
        )
        editTimestamp = "2026-07-24T09:25:00+00:00"
        self.assertTrue(
            logic.invalidateSegmentationReviewAfterEdit(
                segmentationNode,
                editedUtc=editTimestamp,
            )
        )
        self.assertEqual(
            logic.getSegmentationReviewState(segmentationNode),
            "Needs Correction",
        )
        self.assertEqual(
            segmentationNode.GetAttribute(
                "DENTOBOT.LastSegmentationEditUtc"
            ),
            editTimestamp,
        )
        self.assertFalse(
            logic.invalidateSegmentationReviewAfterEdit(
                segmentationNode,
                editedUtc="2026-07-24T09:26:00+00:00",
            )
        )
        correctedProvenance = logic.getSegmentationProvenance(
            segmentationNode
        )
        self.assertEqual(
            correctedProvenance["lastSegmentationEditUtc"],
            "2026-07-24T09:26:00+00:00",
        )
        self.assertEqual(
            correctedProvenance["metricsValidity"],
            "pre-correction-inference",
        )
        self.assertEqual(
            correctedProvenance["correctionActivityUtc"],
            "2026-07-24T09:26:00+00:00",
        )

        sourceVolumeId = sourceVolume.GetID()
        segmentationNode.SetNodeReferenceID(
            logic.SOURCE_VOLUME_REFERENCE_ROLE,
            None,
        )
        segmentationNode.SetAttribute("DENTOBOT.SourceVolumeID", None)
        try:
            with self.assertRaisesRegex(ValueError, "source CBCT"):
                logic.beginSegmentationCorrection(
                    segmentationNode,
                    "tooth-16",
                )
        finally:
            segmentationNode.SetNodeReferenceID(
                logic.SOURCE_VOLUME_REFERENCE_ROLE,
                sourceVolumeId,
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.SourceVolumeID",
                sourceVolumeId,
            )

        self.delayDisplay("DENTOWorkflow Step 3A/3B/3C logic tests passed")

    def test_DENTOWorkflowTargetToothAndTrajectoryLogic(self) -> None:
        logic = DENTOWorkflowLogic()

        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "PlanningSegmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        for segmentId, segmentName in (
            ("tooth-16", "upper_right_first_molar_fdi16"),
            ("pulp-16", "upper_right_first_molar_pulp_fdi116"),
            ("jaw", "upper_jawbone"),
        ):
            segment = slicer.vtkSegment()
            segment.SetName(segmentName)
            cube = vtk.vtkCubeSource()
            cube.SetBounds(-1.0, 1.0, -2.0, 2.0, -3.0, 3.0)
            cube.Update()
            segment.AddRepresentation(
                slicer.vtkSegmentationConverter
                .GetSegmentationClosedSurfaceRepresentationName(),
                cube.GetOutput(),
            )
            segmentationNode.GetSegmentation().AddSegment(segment, segmentId)

        targetRecords = logic.getTargetToothRecords(segmentationNode)
        self.assertEqual(len(targetRecords), 1)
        self.assertEqual(targetRecords[0]["segmentId"], "tooth-16")
        self.assertEqual(targetRecords[0]["fdiNumber"], "16")
        self.assertEqual(
            logic.validateTargetTooth(
                segmentationNode,
                "tooth-16",
            )["sourceName"],
            "upper_right_first_molar_fdi16",
        )
        with self.assertRaisesRegex(ValueError, "whole-tooth"):
            logic.validateTargetTooth(segmentationNode, "pulp-16")
        with self.assertRaisesRegex(ValueError, "target tooth"):
            logic.validateTargetTooth(segmentationNode, "")

        targetBounds = logic.getTargetToothBoundsWorld(
            segmentationNode,
            "tooth-16",
        )
        self.assertEqual(
            targetBounds,
            (-1.0, 1.0, -2.0, 2.0, -3.0, 3.0),
        )
        self.assertTrue(
            logic.isRasPointWithinBounds(
                [0.0, 0.0, 0.0],
                targetBounds,
            )
        )
        self.assertFalse(
            logic.isRasPointWithinBounds(
                [2.0, 0.0, 0.0],
                targetBounds,
            )
        )
        targetBoundsRoi, roiBounds = logic.createOrUpdateTargetBoundsRoi(
            segmentationNode,
            "tooth-16",
        )
        self.assertTrue(targetBoundsRoi.IsA("vtkMRMLMarkupsROINode"))
        self.assertEqual(roiBounds, targetBounds)
        self.assertTrue(targetBoundsRoi.GetLocked())
        self.assertEqual(
            targetBoundsRoi.GetAttribute("DENTOBOT.TargetSegmentID"),
            "tooth-16",
        )

        with self.assertRaisesRegex(ValueError, "must not be empty"):
            logic.createTrajectoryNode(" ")
        trajectoryNode = logic.createTrajectoryNode("PlanningTrajectory")
        self.assertTrue(trajectoryNode.IsA("vtkMRMLMarkupsLineNode"))
        self.assertEqual(trajectoryNode.GetMaximumNumberOfControlPoints(), 2)
        self.assertEqual(
            trajectoryNode.GetAttribute("DENTOBOT.TrajectoryRole"),
            "EntryToTarget",
        )
        emptySummary = logic.getTrajectorySummary(trajectoryNode)
        self.assertEqual(emptySummary["definedPointCount"], 0)
        self.assertFalse(emptySummary["isValid"])

        targetRecord = logic.configureTrajectoryTarget(
            trajectoryNode,
            segmentationNode,
            "tooth-16",
        )
        self.assertEqual(targetRecord["fdiNumber"], "16")
        self.assertEqual(
            trajectoryNode.GetNodeReference(
                logic.TARGET_SEGMENTATION_REFERENCE_ROLE
            ),
            segmentationNode,
        )
        self.assertEqual(
            trajectoryNode.GetAttribute("DENTOBOT.TargetSegmentID"),
            "tooth-16",
        )
        self.assertEqual(
            trajectoryNode.GetAttribute("DENTOBOT.TargetFdiNumber"),
            "16",
        )
        logic.clearTrajectoryTarget(trajectoryNode)
        self.assertIsNone(
            trajectoryNode.GetNodeReference(
                logic.TARGET_SEGMENTATION_REFERENCE_ROLE
            )
        )
        self.assertIsNone(
            trajectoryNode.GetAttribute("DENTOBOT.TargetSegmentID")
        )
        logic.configureTrajectoryTarget(
            trajectoryNode,
            segmentationNode,
            "tooth-16",
        )

        trajectoryNode.AddControlPoint(vtk.vtkVector3d(0.0, 0.0, 0.0))
        logic.labelTrajectoryControlPoints(trajectoryNode)
        onePointSummary = logic.getTrajectorySummary(trajectoryNode)
        self.assertEqual(onePointSummary["definedPointCount"], 1)
        self.assertEqual(onePointSummary["entryRas"], [0.0, 0.0, 0.0])
        self.assertEqual(
            trajectoryNode.GetNthControlPointLabel(0),
            "Entry",
        )

        trajectoryNode.AddControlPoint(vtk.vtkVector3d(3.0, 4.0, 12.0))
        logic.labelTrajectoryControlPoints(trajectoryNode)
        completeSummary = logic.getTrajectorySummary(trajectoryNode)
        self.assertEqual(completeSummary["definedPointCount"], 2)
        self.assertAlmostEqual(completeSummary["lengthMm"], 13.0)
        self.assertTrue(completeSummary["isValid"])
        self.assertEqual(
            trajectoryNode.GetNthControlPointLabel(1),
            "Target",
        )
        self.assertEqual(
            logic.formatRasPoint(completeSummary["targetRas"]),
            "3.000, 4.000, 12.000 mm",
        )

        coincidentTrajectory = logic.createTrajectoryNode(
            "CoincidentTrajectory"
        )
        coincidentTrajectory.AddControlPoint(vtk.vtkVector3d(1.0, 2.0, 3.0))
        coincidentTrajectory.AddControlPoint(vtk.vtkVector3d(1.0, 2.0, 3.0))
        coincidentSummary = logic.getTrajectorySummary(coincidentTrajectory)
        self.assertEqual(coincidentSummary["lengthMm"], 0.0)
        self.assertFalse(coincidentSummary["isValid"])

        constrainedTrajectory = logic.createTrajectoryNode(
            "ConstrainedTrajectory"
        )
        constrainedTrajectory.AddControlPoint(
            vtk.vtkVector3d(0.0, 0.0, 0.0)
        )
        constrainedTrajectory.AddControlPoint(
            vtk.vtkVector3d(2.0, 0.0, 0.0)
        )
        boundsReport = logic.getTrajectoryBoundsReport(
            constrainedTrajectory,
            segmentationNode,
            "tooth-16",
        )
        self.assertEqual(boundsReport["invalidPointIndices"], [1])
        self.assertFalse(boundsReport["allDefinedPointsWithinBounds"])

        placementTrajectory = logic.createTrajectoryNode(
            "PlacementTrajectory"
        )
        logic.startTrajectoryPlacement(placementTrajectory)
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        self.assertEqual(
            selectionNode.GetActivePlaceNodeID(),
            placementTrajectory.GetID(),
        )
        self.assertEqual(
            selectionNode.GetActivePlaceNodeClassName(),
            "vtkMRMLMarkupsLineNode",
        )
        self.assertTrue(selectionNode.GetActivePlaceNodePlacementValid())
        logic.stopTrajectoryPlacement()

        parameterNode = logic.getParameterNode()
        parameterNode.teethSegmentation = segmentationNode
        parameterNode.targetToothSegmentId = "tooth-16"
        parameterNode.targetToothBoundsRoi = targetBoundsRoi
        parameterNode.trajectoryLine = trajectoryNode
        self.assertEqual(
            parameterNode.teethSegmentation.GetID(),
            segmentationNode.GetID(),
        )
        self.assertEqual(parameterNode.targetToothSegmentId, "tooth-16")
        self.assertEqual(
            parameterNode.targetToothBoundsRoi.GetID(),
            targetBoundsRoi.GetID(),
        )
        self.assertEqual(
            parameterNode.trajectoryLine.GetID(),
            trajectoryNode.GetID(),
        )

        self.delayDisplay(
            "DENTOWorkflow target-tooth and trajectory logic tests passed"
        )
