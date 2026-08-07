import colorsys
import json
import logging
import math
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import qt
import vtk

import slicer
from slicer import (
    vtkMRMLMarkupsClosedCurveNode,
    vtkMRMLMarkupsLineNode,
    vtkMRMLMarkupsPlaneNode,
    vtkMRMLMarkupsROINode,
    vtkMRMLModelNode,
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

_helperDirectory = Path(__file__).resolve().parent / "Resources" / "Python"
if str(_helperDirectory) not in sys.path:
    sys.path.insert(0, str(_helperDirectory))

from DENTOTemplateGeometry import (
    create_hollow_sleeve,
    create_research_shell,
    model_polydata_in_world,
    surface_topology,
    write_stl_atomic,
)


@parameterNodeWrapper
class DENTOWorkflowParameterNode:
    """Persistent DENTOBOT workflow state stored in the MRML scene."""

    caseName: str = ""
    inputVolume: vtkMRMLScalarVolumeNode
    useLauncherBackendConfiguration: bool = True
    wslDistribution: str = ""
    wslPythonPath: str = ""
    stagingRoot: str = ""
    inferenceDevice: str = "cuda:0"
    roundTripVolume: vtkMRMLScalarVolumeNode
    teethSegmentation: vtkMRMLSegmentationNode
    targetToothSegmentId: str = ""
    targetToothBoundsRoi: vtkMRMLMarkupsROINode
    trajectoryLine: vtkMRMLMarkupsLineNode
    templateSupportToothSegmentIdsJson: str = "[]"
    draftTemplateSupportModel: vtkMRMLModelNode
    templateShellRoi: vtkMRMLMarkupsROINode
    templateShellClearanceMm: float = 0.3
    templateShellThicknessMm: float = 1.5
    templateSamplingSpacingMm: float = 0.3
    templateChannelDiameterMm: float = 1.5
    templateSleeveOuterDiameterMm: float = 4.4
    templateSleeveInnerDiameterMm: float = 1.5
    templateSleeveHeightMm: float = 2.5
    researchTemplateShellModel: vtkMRMLModelNode
    researchTemplateSleeveModel: vtkMRMLModelNode
    templateFinalizationMode: str = "PlaneCut"
    templateFinalizationKeepRegion: str = "Negative"
    templateFinalizationViewLocked: bool = True
    templateTrimPlane: vtkMRMLMarkupsPlaneNode
    templateTrimCurve: vtkMRMLMarkupsClosedCurveNode
    finalizedTemplateShellModel: vtkMRMLModelNode


class DENTOWorkflow(ScriptedLoadableModule):
    """DENTOBOT's focused case-imaging entry point."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.parent.title = _("DENTO Workflow")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "DENTOBOT")]
        self.parent.dependencies = ["DICOM", "DynamicModeler", "Markups"]
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
        self._updatingFromParameterNode = False
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
        self._restoringTrajectoryAssociation = False
        self._planningConstraintWarning = ""
        self._validTrajectoryPointsByNodeId: dict[str, list[list[float]]] = {}
        self._templateSupportRecordsById: dict[str, dict] = {}
        self._updatingTemplateUI = False
        self._templateStatusWarning = ""
        self._updatingTemplateGuideUI = False
        self._updatingTemplateGuideVisibilityUI = False
        self._updatingTemplateFinalizationUI = False
        self._templateFinalizationPriorVisibilityByNodeId: dict[str, bool] = {}
        self._templateFinalizationCamera = None
        self._templateTrimPlaneNode = None
        self._templateTrimCurveNode = None
        self._restoringTemplateFinalizationCamera = False
        self._restoringTemplateTrimPlane = False
        self._isCleaningUp = False

    def setup(self) -> None:
        super().setup()

        uiWidget = slicer.util.loadUI(self.resourcePath("UI/DENTOWorkflow.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        uiWidget.setMRMLScene(slicer.mrmlScene)
        self.ui.templateShellRoiSelector.addAttribute(
            "vtkMRMLMarkupsROINode",
            "DENTOBOT.MarkupsRole",
            "TemplateShellTrimROI",
        )
        self.ui.templateShellRoiSelector.setCurrentNode(None)
        self.ui.templateTrimPlaneSelector.addAttribute(
            "vtkMRMLMarkupsPlaneNode",
            "DENTOBOT.MarkupsRole",
            "TemplateFinalizationPlane",
        )
        self.ui.templateTrimCurveSelector.addAttribute(
            "vtkMRMLMarkupsClosedCurveNode",
            "DENTOBOT.MarkupsRole",
            "TemplateFinalizationCurve",
        )
        self.ui.finalizedTemplateShellModelSelector.addAttribute(
            "vtkMRMLModelNode",
            "DENTOBOT.ModelRole",
            "FinalizedTemplateShell",
        )

        self.logic = DENTOWorkflowLogic()
        if os.name != "nt":
            self.ui.wslDistributionLabel.visible = False
            self.ui.wslDistributionLineEdit.visible = False
            self.ui.wslPythonPathLabel.text = _("Manual backend Python:")
            self.ui.wslPythonPathLineEdit.toolTip = _(
                "Advanced manual override for the dedicated DENTOBOT backend "
                "Python in this container. Normally the launcher supplies it."
            )
            self.ui.stagingRootLineEdit.toolTip = _(
                "Advanced manual override for the local run-records folder. "
                "Normally the launcher supplies it."
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
        else:
            self.ui.useLauncherBackendConfigurationCheckBox.visible = False

        self.ui.newCaseButton.connect("clicked(bool)", self.onNewCase)
        self.ui.openSceneButton.connect("clicked(bool)", self.onOpenScene)
        self.ui.openDicomButton.connect("clicked(bool)", self.onOpenDicomBrowser)
        self.ui.showVolumeButton.connect("clicked(bool)", self.onShowSelectedVolume)
        self.ui.inputVolumeSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onInputVolumeSelectionChanged,
        )
        self.ui.useLauncherBackendConfigurationCheckBox.connect(
            "toggled(bool)",
            self.onUseLauncherBackendConfigurationToggled,
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
        self.ui.deleteTrajectoryButton.connect(
            "clicked(bool)",
            self.onDeleteTrajectory,
        )
        self.ui.lockTrajectoryButton.connect(
            "toggled(bool)",
            self.onTrajectoryLockToggled,
        )
        self.ui.templateSupportTeethListWidget.connect(
            "itemChanged(QListWidgetItem*)",
            self.onTemplateSupportToothItemChanged,
        )
        self.ui.draftTemplateSupportModelSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onDraftTemplateSupportModelSelectionChanged,
        )
        self.ui.createDraftTemplateSupportModelButton.connect(
            "clicked(bool)",
            self.onCreateDraftTemplateSupportModel,
        )
        self.ui.deleteDraftTemplateSupportModelButton.connect(
            "clicked(bool)",
            self.onDeleteDraftTemplateSupportModel,
        )
        self.ui.templateShellRoiSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onTemplateGuideInputChanged,
        )
        self.ui.createTemplateShellRoiButton.connect(
            "clicked(bool)",
            self.onCreateTemplateShellRoi,
        )
        self.ui.deleteTemplateShellRoiButton.connect(
            "clicked(bool)",
            self.onDeleteTemplateShellRoi,
        )
        for visibilityCheckBox in (
            self.ui.targetBoundsVisibilityCheckBox,
            self.ui.trajectoryVisibilityCheckBox,
            self.ui.supportModelVisibilityCheckBox,
            self.ui.shellRoiVisibilityCheckBox,
            self.ui.shellModelVisibilityCheckBox,
            self.ui.sleeveModelVisibilityCheckBox,
        ):
            visibilityCheckBox.connect(
                "toggled(bool)",
                self.onTemplateGuideVisibilityChanged,
            )
        for parameterWidget in (
            self.ui.templateShellClearanceSpinBox,
            self.ui.templateShellThicknessSpinBox,
            self.ui.templateSamplingSpacingSpinBox,
            self.ui.templateChannelDiameterSpinBox,
            self.ui.templateSleeveOuterDiameterSpinBox,
            self.ui.templateSleeveInnerDiameterSpinBox,
            self.ui.templateSleeveHeightSpinBox,
        ):
            parameterWidget.connect(
                "valueChanged(double)",
                self.onTemplateGuideInputChanged,
            )
        self.ui.generateResearchTemplateButton.connect(
            "clicked(bool)",
            self.onGenerateResearchTemplate,
        )
        self.ui.deleteResearchTemplateButton.connect(
            "clicked(bool)",
            self.onDeleteResearchTemplate,
        )
        self.ui.continueTemplateFinalizationButton.connect(
            "clicked(bool)",
            self.onContinueTemplateFinalization,
        )
        self.ui.templateFinalizationModeComboBox.connect(
            "currentIndexChanged(int)",
            self.onTemplateFinalizationModeChanged,
        )
        self.ui.templateFinalizationKeepRegionComboBox.connect(
            "currentIndexChanged(int)",
            self.onTemplateFinalizationKeepRegionChanged,
        )
        self.ui.templateFinalizationViewLockedCheckBox.connect(
            "toggled(bool)",
            self.onTemplateFinalizationViewLockToggled,
        )
        self.ui.templateTrimPlaneSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onTemplateFinalizationInputChanged,
        )
        self.ui.templateTrimCurveSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onTemplateFinalizationInputChanged,
        )
        self.ui.createTemplateTrimPlaneButton.connect(
            "clicked(bool)",
            self.onCreateTemplateTrimPlane,
        )
        self.ui.placeTemplateTrimCurveButton.connect(
            "clicked(bool)",
            self.onPlaceTemplateTrimCurve,
        )
        self.ui.applyTemplateFinalizationButton.connect(
            "clicked(bool)",
            self.onApplyTemplateFinalization,
        )
        self.ui.restoreTemplateFinalizationViewButton.connect(
            "clicked(bool)",
            self.onRestoreTemplateFinalizationView,
        )
        self.ui.openDynamicModelerButton.connect(
            "clicked(bool)",
            self.onOpenDynamicModeler,
        )
        self.ui.deleteTemplateFinalizationButton.connect(
            "clicked(bool)",
            self.onDeleteTemplateFinalization,
        )
        self.ui.exportResearchTemplateButton.connect(
            "clicked(bool)",
            self.onExportResearchTemplate,
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
            self._clearTemplateModeling()
            self._clearTemplateGuide()
            self._clearTemplateFinalization()

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
        del caller, event
        if (
            self._updatingFromParameterNode
            or self._restoringTrajectoryAssociation
            or not self._parameterNode
            or not self.logic
        ):
            return
        self._updatingFromParameterNode = True
        try:
            self._updateFromParameterNodeOnce()
        finally:
            self._updatingFromParameterNode = False

    def _updateFromParameterNodeOnce(self) -> None:
        """Perform one non-reentrant parameter-to-widget synchronization."""

        volumeNode = self._parameterNode.inputVolume
        self.ui.showVolumeButton.enabled = volumeNode is not None
        self._updateBackendControls()
        self._bindSegmentationReviewNode(self._parameterNode.teethSegmentation)
        self._updateSegmentationReview()
        self._bindPlanningTrajectoryNode(self._parameterNode.trajectoryLine)
        self._updatePlanning()
        self._updateTemplateModeling()
        self._updateTemplateGuide()
        self._updateTemplateFinalization()

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
            self._updateTemplateModeling()

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
        self._markCurrentDraftTemplateModelStale(
            _("Source segmentation content changed.")
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
        if not self._parameterNode or self._restoringTrajectoryAssociation:
            return
        currentNode = self._parameterNode.teethSegmentation
        currentNodeId = currentNode.GetID() if currentNode else None
        selectedNodeId = segmentationNode.GetID() if segmentationNode else None
        if currentNodeId != selectedNodeId:
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
        previousRoi = self._parameterNode.targetToothBoundsRoi
        candidateRoi = previousRoi
        if not self.logic.isTargetBoundsRoiForTarget(
            candidateRoi,
            segmentationNode,
            targetRecord["segmentId"],
        ):
            candidateRoi = self.logic.findTargetBoundsRoi(
                segmentationNode,
                targetRecord["segmentId"],
            )
        try:
            roiNode, bounds = self.logic.createOrUpdateTargetBoundsRoi(
                segmentationNode,
                targetRecord["segmentId"],
                candidateRoi,
            )
        except (RuntimeError, ValueError) as exc:
            self._planningConstraintWarning = str(exc)
            self.ui.targetBoundsValueLabel.text = _("--")
            return None

        if (
            previousRoi
            and previousRoi is not roiNode
            and previousRoi.GetDisplayNode()
        ):
            previousRoi.GetDisplayNode().SetVisibility(False)
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

        trajectoryNode = self._parameterNode.trajectoryLine
        trajectoryAssociationError = ""
        association = None
        if trajectoryNode:
            try:
                association = self.logic.getTrajectoryTargetAssociation(
                    trajectoryNode
                )
            except ValueError as exc:
                trajectoryAssociationError = str(exc)
        if association:
            associatedSegmentation = association["segmentationNode"]
            associatedTargetId = association["targetRecord"]["segmentId"]
            associatedRoi = association["targetBoundsRoi"]
            if (
                self._parameterNode.teethSegmentation is not associatedSegmentation
                or self._parameterNode.targetToothSegmentId != associatedTargetId
                or self._parameterNode.targetToothBoundsRoi is not associatedRoi
            ):
                self._restoringTrajectoryAssociation = True
                wasModifying = self._parameterNode.StartModify()
                try:
                    self._parameterNode.teethSegmentation = associatedSegmentation
                    self._parameterNode.targetToothSegmentId = associatedTargetId
                    self._parameterNode.targetToothBoundsRoi = associatedRoi
                finally:
                    self._parameterNode.EndModify(wasModifying)
                    self._restoringTrajectoryAssociation = False

        segmentationNode = self._parameterNode.teethSegmentation
        if not segmentationNode:
            self._clearPlanning()
            return

        wasUpdatingPlanningUI = self._updatingPlanningUI
        self._updatingPlanningUI = True
        try:
            self.logic.refreshWorkflowLineageColors()
            self.logic.refreshManagedTrajectoryNames()
            self.logic.refreshWorkflowNodeStepTags()
        finally:
            self._updatingPlanningUI = wasUpdatingPlanningUI

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
        if trajectoryAssociationError:
            self._planningConstraintWarning = trajectoryAssociationError
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

        self.logic.refreshWorkflowLineageColors()
        self.logic.applyTrajectoryGroupEmphasis(
            segmentationNode,
            targetRecord["segmentId"] if targetRecord else "",
        )
        self._updateTrajectorySelectorColorSwatches()

        self._bindPlanningTrajectoryNode(trajectoryNode)
        if targetRecord and trajectoryNode and not trajectoryAssociationError:
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
            self.ui.deleteTrajectoryButton.enabled = bool(
                trajectoryNode
                and self.logic.isDentobotTrajectoryNode(trajectoryNode)
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
        if (
            self._updatingPlanningUI
            or self._restoringTrajectoryAssociation
            or not self._parameterNode
            or not self.logic
        ):
            return
        segmentId = (
            str(self.ui.targetToothComboBox.itemData(index))
            if index >= 0 and self.ui.targetToothComboBox.itemData(index)
            else ""
        )
        previousTargetId = self._parameterNode.targetToothSegmentId
        if segmentId != previousTargetId:
            self._markCurrentDraftTemplateModelStale(
                _("Target tooth selection changed.")
            )
            self._parameterNode.templateSupportToothSegmentIdsJson = "[]"

        trajectoryNode = self._parameterNode.trajectoryLine
        trajectoryAssociation = None
        trajectoryAssociationInvalid = False
        if trajectoryNode:
            self._validTrajectoryPointsByNodeId.pop(
                trajectoryNode.GetID(),
                None,
            )
            try:
                trajectoryAssociation = (
                    self.logic.getTrajectoryTargetAssociation(trajectoryNode)
                )
            except ValueError as exc:
                slicer.util.errorDisplay(str(exc))
                trajectoryAssociationInvalid = True

        retainedTrajectory = None if trajectoryAssociationInvalid else trajectoryNode
        if trajectoryAssociation and not trajectoryAssociationInvalid:
            associatedTargetId = trajectoryAssociation["targetRecord"][
                "segmentId"
            ]
            if associatedTargetId != segmentId:
                retainedTrajectory = None
        elif trajectoryNode and segmentId:
            try:
                self.logic.configureTrajectoryTarget(
                    trajectoryNode,
                    self._parameterNode.teethSegmentation,
                    segmentId,
                )
            except ValueError as exc:
                slicer.util.errorDisplay(str(exc))
                retainedTrajectory = None
        elif trajectoryNode and not segmentId:
            retainedTrajectory = None

        previousRoi = self._parameterNode.targetToothBoundsRoi
        if (
            segmentId != previousTargetId
            and previousRoi
            and previousRoi.GetDisplayNode()
        ):
            previousRoi.GetDisplayNode().SetVisibility(False)
        self._planningConstraintWarning = ""
        self._restoringTrajectoryAssociation = True
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.targetToothSegmentId = segmentId
            self._parameterNode.trajectoryLine = retainedTrajectory
            if segmentId != previousTargetId:
                self._parameterNode.targetToothBoundsRoi = None
        finally:
            self._parameterNode.EndModify(wasModifying)
            self._restoringTrajectoryAssociation = False
        self._updatePlanning()
        self._updateTemplateModeling()
        self._applyTargetPriorityHighlight()

    def onTrajectorySelectionChanged(self, trajectoryNode) -> None:
        if (
            self._restoringTrajectoryAssociation
            or not self._parameterNode
            or not self.logic
        ):
            return
        previousNode = self._planningTrajectoryNode
        previousNodeId = previousNode.GetID() if previousNode else None
        selectedNodeId = trajectoryNode.GetID() if trajectoryNode else None
        association = None
        if trajectoryNode:
            try:
                association = self.logic.getTrajectoryTargetAssociation(
                    trajectoryNode
                )
            except ValueError as exc:
                slicer.util.errorDisplay(str(exc))
                self._restoringTrajectoryAssociation = True
                try:
                    self._parameterNode.trajectoryLine = previousNode
                    self.ui.trajectorySelector.setCurrentNode(previousNode)
                finally:
                    self._restoringTrajectoryAssociation = False
                return

        previousSegmentation = self._parameterNode.teethSegmentation
        previousTargetId = self._parameterNode.targetToothSegmentId
        self._restoringTrajectoryAssociation = True
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.trajectoryLine = trajectoryNode
            if association:
                associatedSegmentation = association["segmentationNode"]
                associatedTargetId = association["targetRecord"]["segmentId"]
                associatedRoi = association["targetBoundsRoi"]
                if (
                    previousSegmentation is not associatedSegmentation
                    or previousTargetId != associatedTargetId
                ):
                    self._markCurrentDraftTemplateModelStale(
                        _("Selected trajectory targets a different tooth.")
                    )
                    self._parameterNode.templateSupportToothSegmentIdsJson = "[]"
                oldRoi = self._parameterNode.targetToothBoundsRoi
                if (
                    oldRoi
                    and oldRoi is not associatedRoi
                    and oldRoi.GetDisplayNode()
                ):
                    oldRoi.GetDisplayNode().SetVisibility(False)
                self._parameterNode.teethSegmentation = associatedSegmentation
                self._parameterNode.targetToothSegmentId = associatedTargetId
                self._parameterNode.targetToothBoundsRoi = associatedRoi
            elif trajectoryNode and self._parameterNode.targetToothSegmentId:
                self.logic.configureTrajectoryTarget(
                    trajectoryNode,
                    self._parameterNode.teethSegmentation,
                    self._parameterNode.targetToothSegmentId,
                )
        finally:
            self._parameterNode.EndModify(wasModifying)
            self._restoringTrajectoryAssociation = False

        if previousNodeId and previousNodeId != selectedNodeId:
            self._validTrajectoryPointsByNodeId.pop(previousNodeId, None)
        self._planningConstraintWarning = ""
        self._bindSegmentationReviewNode(self._parameterNode.teethSegmentation)
        self._updateSegmentationReview()
        self._bindPlanningTrajectoryNode(trajectoryNode)
        self._updatePlanning()
        self._updateTemplateModeling()
        self._updateTemplateGuide()

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
            self.logic.enableAutomaticTrajectoryName(trajectoryNode)
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

    def onDeleteTrajectory(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        trajectoryNode = self._parameterNode.trajectoryLine
        try:
            self.logic.validateDentobotTrajectoryForDeletion(trajectoryNode)
        except ValueError as exc:
            slicer.util.errorDisplay(str(exc))
            return
        trajectoryName = trajectoryNode.GetName() or _("Unnamed trajectory")
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Permanently delete the selected trajectory “%1”? The target "
                "tooth, source segmentation, and target bounds will be kept. "
                "This cannot be undone after the scene is saved."
            ).replace("%1", trajectoryName),
            windowTitle=_("Delete Step 4A trajectory"),
        ):
            return

        trajectoryId = trajectoryNode.GetID()
        self._bindPlanningTrajectoryNode(None)
        try:
            removal = self.logic.deleteTrajectoryNode(trajectoryNode)
        except (RuntimeError, ValueError) as exc:
            self._bindPlanningTrajectoryNode(trajectoryNode)
            slicer.util.errorDisplay(str(exc))
            return
        self._parameterNode.trajectoryLine = None
        self._validTrajectoryPointsByNodeId.pop(trajectoryId, None)
        self._planningConstraintWarning = ""
        logging.info(
            "Deleted DENTOBOT Step 4A trajectory %s and %d owned auxiliary nodes",
            removal["nodeId"],
            len(removal["auxiliaryNodeIds"]),
        )
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
                _("Step 4A → Step 5A"),
                _(
                    "Target lineage: create a Step 4A trajectory to assign a color."
                ),
            )
            self.ui.templateSupportTeethListWidget.clear()
            self.ui.templateSupportTeethListWidget.enabled = False
            self.ui.draftTemplateSupportModelSelector.setCurrentNode(None)
            self.ui.createDraftTemplateSupportModelButton.enabled = False
            self.ui.createDraftTemplateSupportModelButton.text = _(
                "Create Draft Support Model"
            )
            self.ui.deleteDraftTemplateSupportModelButton.enabled = False
            self.ui.templateModelingStatusLabel.text = _(
                "Select a reviewed dental segmentation and target tooth."
            )
            self.ui.templateModelingStatusLabel.styleSheet = "color: #b36b00;"
        finally:
            self._updatingTemplateUI = False

    def _markCurrentDraftTemplateModelStale(self, reason: str) -> bool:
        if not self._parameterNode or not self.logic:
            return False
        return self.logic.markDraftTemplateSupportModelStale(
            self._parameterNode.draftTemplateSupportModel,
            reason,
        )

    def _selectedTemplateSupportSegmentIds(self) -> list[str]:
        selectedIds = []
        listWidget = self.ui.templateSupportTeethListWidget
        for itemIndex in range(listWidget.count):
            item = listWidget.item(itemIndex)
            segmentId = item.data(qt.Qt.UserRole)
            if segmentId and item.checkState() == qt.Qt.Checked:
                selectedIds.append(str(segmentId))
        return selectedIds

    def _updateTemplateModeling(self) -> None:
        if self._updatingTemplateUI:
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
        try:
            persistedSupportIds = self.logic.decodeTemplateSupportSegmentIds(
                self._parameterNode.templateSupportToothSegmentIdsJson
            )
        except ValueError as exc:
            persistedSupportIds = []
            persistedSelectionError = str(exc)

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
            for record in self._targetToothRecordsById.values()
            if record["segmentId"] != targetSegmentId
        ]
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
            _("Step 4A → Step 5A"),
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

        if (
            modelSummary
            and (
                modelSummary["sourceSegmentation"] is not segmentationNode
                or modelSummary["targetSegmentId"] != targetSegmentId
                or modelSummary["supportSegmentIds"] != selectedSupportIds
            )
        ):
            self.logic.markDraftTemplateSupportModelStale(
                modelNode,
                _("Current target or support-tooth selection differs."),
            )
            modelSummary = self.logic.getDraftTemplateSupportModelSummary(
                modelNode
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
        self.ui.deleteDraftTemplateSupportModelButton.enabled = bool(
            modelNode
            and self.logic.isDraftTemplateSupportModelNode(modelNode)
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
        elif not availableRecords:
            message = _(
                "No additional whole-tooth segments are available as supports."
            )
            style = "color: #b00020;"
        elif reviewState != "Reviewed":
            message = _(
                "Mark the authoritative segmentation Reviewed before creating "
                "or updating the draft model."
            )
            style = "color: #b36b00;"
        elif not selectedSupportIds:
            message = _(
                "Manually check one or more support teeth. Any count is "
                "supported; no adjacency rule is imposed."
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

    def onTemplateSupportToothItemChanged(self, item) -> None:
        del item
        if (
            self._updatingTemplateUI
            or not self._parameterNode
            or not self.logic
        ):
            return
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
        self._updateTemplateModeling()

    def onCreateDraftTemplateSupportModel(self) -> None:
        if not self._parameterNode or not self.logic:
            return
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
            self._templateStatusWarning = ""
            logging.info(
                "DENTOBOT Step 5A draft model %s created/updated with "
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
                "teeth will be kept so a new draft can be created. This "
                "cannot be undone after the scene is saved."
            ).replace("%1", modelName),
            windowTitle=_("Delete Step 5A draft support model"),
        ):
            return

        try:
            removal = self.logic.deleteDraftTemplateSupportModel(modelNode)
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))
            return
        self._parameterNode.draftTemplateSupportModel = None
        self._templateStatusWarning = ""
        logging.info(
            "Deleted DENTOBOT Step 5A draft model %s and %d owned auxiliary nodes",
            removal["nodeId"],
            len(removal["auxiliaryNodeIds"]),
        )
        self._updateTemplateModeling()

    def _clearTemplateGuide(self) -> None:
        if not hasattr(self, "ui"):
            return
        self._updatingTemplateGuideUI = True
        try:
            self.ui.templateShellRoiSelector.setCurrentNode(None)
            self.ui.researchTemplateShellModelSelector.setCurrentNode(None)
            self.ui.researchTemplateSleeveModelSelector.setCurrentNode(None)
            self._updateLineageBadge(
                self.ui.templateGuideLineageLabel,
                None,
                _("Step 4A → Step 5A → Step 5B"),
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
            ):
                visibilityCheckBox.enabled = False
                visibilityCheckBox.checked = False
            self.ui.generateResearchTemplateButton.enabled = False
            self.ui.deleteResearchTemplateButton.enabled = False
            self.ui.exportResearchTemplateButton.enabled = False
            self.ui.templateGuideStatusLabel.text = _(
                "Create a current Step 5A model and a complete locked trajectory."
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

    def _updateTemplateGuide(self) -> None:
        if self._updatingTemplateGuideUI:
            return
        if not self._parameterNode or not self.logic:
            self._clearTemplateGuide()
            return

        supportModel = self._parameterNode.draftTemplateSupportModel
        trajectoryNode = self._parameterNode.trajectoryLine
        roiNode = self._parameterNode.templateShellRoi
        shellModel = self._parameterNode.researchTemplateShellModel
        sleeveModel = self._parameterNode.researchTemplateSleeveModel
        rejectedRoiWarning = ""
        if roiNode and not self.logic.isTemplateShellRoiNode(roiNode):
            rejectedRoiWarning = _(
                "Ignored a non-Step 5B ROI. Create the shell trim ROI with "
                "the Step 5B button; target-bounds and unrelated ROIs cannot "
                "be used for shell generation."
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
        self.logic.refreshWorkflowLineageColors()
        self.logic.refreshWorkflowNodeStepTags()
        lineageNode = self._lineageSourceNode(
            (
                supportModel,
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
            _("Step 4A → Step 5A → Step 5B"),
            _(
                "Inherited lineage: waiting for a colored Step 5A/Step 4A input."
            ),
        )
        for selector, acceptsNode in (
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
        self._updateTemplateGuideVisibilityControls()
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
                    _("Step 5A anatomy, trajectory, ROI, or dimensions changed."),
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

    def onCreateTemplateShellRoi(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            roiNode = self.logic.createOrResetTemplateShellRoi(
                self._parameterNode.draftTemplateSupportModel,
                self._parameterNode.templateShellRoi,
            )
            self._parameterNode.templateShellRoi = roiNode
            self._updateTemplateGuide()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onDeleteTemplateShellRoi(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        roiNode = self._parameterNode.templateShellRoi
        try:
            self.logic.validateTemplateShellRoiForDeletion(roiNode)
        except ValueError as exc:
            slicer.util.errorDisplay(str(exc))
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Permanently delete the Step 5B shell trim ROI? Existing "
                "shell and sleeve outputs will be kept but marked stale. "
                "The Step 5A anatomy, trajectory, and dimensions will be kept "
                "so a fresh ROI can be created."
            ),
            windowTitle=_("Delete Step 5B shell trim ROI"),
        ):
            return
        try:
            removal = self.logic.deleteTemplateShellRoi(roiNode)
            self._parameterNode.templateShellRoi = None
            self.logic.markResearchTemplateModelsStale(
                self._parameterNode.researchTemplateShellModel,
                self._parameterNode.researchTemplateSleeveModel,
                _("Shell trim ROI was deleted."),
            )
            logging.info(
                "Deleted DENTOBOT Step 5B shell ROI %s and %d owned auxiliary nodes",
                removal["nodeId"],
                len(removal["auxiliaryNodeIds"]),
            )
            self._updateTemplateGuide()
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onGenerateResearchTemplate(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        parameters = self._templateGuideParameters()
        try:
            shellModel, sleeveModel, details = self.logic.createOrUpdateResearchTemplate(
                self._parameterNode.draftTemplateSupportModel,
                self._parameterNode.trajectoryLine,
                self._parameterNode.templateShellRoi,
                clearanceMm=parameters["clearanceMm"],
                thicknessMm=parameters["thicknessMm"],
                samplingSpacingMm=parameters["samplingSpacingMm"],
                channelDiameterMm=parameters["channelDiameterMm"],
                sleeveOuterDiameterMm=parameters["sleeveOuterDiameterMm"],
                sleeveInnerDiameterMm=parameters["sleeveInnerDiameterMm"],
                sleeveHeightMm=parameters["sleeveHeightMm"],
                shellModelNode=self._parameterNode.researchTemplateShellModel,
                sleeveModelNode=self._parameterNode.researchTemplateSleeveModel,
            )
            self._parameterNode.researchTemplateShellModel = shellModel
            self._parameterNode.researchTemplateSleeveModel = sleeveModel
            logging.info(
                "Generated DENTOBOT Step 5B shell (%d triangles) and sleeve (%d triangles)",
                details["shell"]["triangleCount"],
                details["sleeve"]["triangleCount"],
            )
            self._updateTemplateGuide()
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            self.ui.templateGuideStatusLabel.text = str(exc)
            self.ui.templateGuideStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def onDeleteResearchTemplate(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Permanently delete the DENTOBOT Step 5B shell and sleeve? "
                "Any dependent Step 5C plane, curve, finalized shell, and Dynamic "
                "Modeler auxiliaries will also be deleted. The Step 5A anatomy, "
                "trajectory, ROI, and dimensions will be kept."
            ),
            windowTitle=_("Delete Step 5B research template"),
        ):
            return
        try:
            if (
                self._parameterNode.templateTrimPlane
                or self._parameterNode.templateTrimCurve
                or self._parameterNode.finalizedTemplateShellModel
            ):
                self.logic.deleteTemplateFinalization(
                    self._parameterNode.templateTrimPlane,
                    self._parameterNode.templateTrimCurve,
                    self._parameterNode.finalizedTemplateShellModel,
                )
                self._parameterNode.templateTrimPlane = None
                self._parameterNode.templateTrimCurve = None
                self._parameterNode.finalizedTemplateShellModel = None
            removals = self.logic.deleteResearchTemplateModels(
                self._parameterNode.researchTemplateShellModel,
                self._parameterNode.researchTemplateSleeveModel,
            )
            self._parameterNode.researchTemplateShellModel = None
            self._parameterNode.researchTemplateSleeveModel = None
            logging.info(
                "Deleted %d DENTOBOT Step 5B model nodes",
                len(removals),
            )
            self._updateTemplateGuide()
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def _clearTemplateFinalization(self) -> None:
        if not hasattr(self, "ui"):
            return
        self._bindTemplateFinalizationEditNodes(None, None)
        self._updatingTemplateFinalizationUI = True
        try:
            self.ui.templateFinalizationSourceValueLabel.text = _("--")
            self.ui.templateTrimPlaneSelector.setCurrentNode(None)
            self.ui.templateTrimCurveSelector.setCurrentNode(None)
            self.ui.finalizedTemplateShellModelSelector.setCurrentNode(None)
            self._updateLineageBadge(
                self.ui.templateFinalizationLineageLabel,
                None,
                _("Step 4A → Step 5A → Step 5B → Step 5C"),
                _("Inherited lineage: waiting for a current Step 5B shell."),
            )
            for button in (
                self.ui.continueTemplateFinalizationButton,
                self.ui.createTemplateTrimPlaneButton,
                self.ui.placeTemplateTrimCurveButton,
                self.ui.applyTemplateFinalizationButton,
                self.ui.openDynamicModelerButton,
                self.ui.deleteTemplateFinalizationButton,
                self.ui.exportResearchTemplateButton,
            ):
                button.enabled = False
            self.ui.restoreTemplateFinalizationViewButton.enabled = bool(
                self._templateFinalizationPriorVisibilityByNodeId
            )
            self.ui.templateFinalizationStatusLabel.text = _(
                "Generate a current Step 5B shell and sleeve first."
            )
            self.ui.templateFinalizationStatusLabel.styleSheet = "color: #b36b00;"
        finally:
            self._updatingTemplateFinalizationUI = False

    @staticmethod
    def _templateFinalizationModeFromIndex(index: int) -> str:
        return "CurveCut" if int(index) == 1 else "PlaneCut"

    @staticmethod
    def _templateFinalizationKeepChoices(mode: str) -> tuple[tuple[str, str], ...]:
        if mode == "CurveCut":
            return (
                (_("Inside closed curve"), "Inside"),
                (_("Outside closed curve"), "Outside"),
            )
        return (
            (_("Below horizontal plane (inferior / −S)"), "Negative"),
            (_("Above horizontal plane (superior / +S)"), "Positive"),
        )

    def _setTemplateFinalizationKeepChoices(self, mode: str, selected: str) -> None:
        comboBox = self.ui.templateFinalizationKeepRegionComboBox
        choices = self._templateFinalizationKeepChoices(mode)
        validValues = {value for _label, value in choices}
        if selected not in validValues:
            selected = choices[0][1]
            if self._parameterNode:
                self._parameterNode.templateFinalizationKeepRegion = selected
        comboBox.clear()
        selectedIndex = 0
        for index, (label, value) in enumerate(choices):
            comboBox.addItem(label, value)
            if value == selected:
                selectedIndex = index
        comboBox.setCurrentIndex(selectedIndex)

    def _bindTemplateFinalizationEditNodes(self, planeNode, curveNode) -> None:
        if self._templateTrimPlaneNode is not planeNode:
            if self._templateTrimPlaneNode:
                self.removeObserver(
                    self._templateTrimPlaneNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onTemplateTrimPlaneModified,
                )
            self._templateTrimPlaneNode = planeNode
            if planeNode:
                self.addObserver(
                    planeNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onTemplateTrimPlaneModified,
                )
        if self._templateTrimCurveNode is not curveNode:
            if self._templateTrimCurveNode:
                self.removeObserver(
                    self._templateTrimCurveNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onTemplateTrimCurveModified,
                )
            self._templateTrimCurveNode = curveNode
            if curveNode:
                self.addObserver(
                    curveNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onTemplateTrimCurveModified,
                )

    def _onTemplateTrimPlaneModified(self, caller=None, event=None) -> None:
        del event
        if (
            self._restoringTemplateTrimPlane
            or not self._parameterNode
            or caller is not self._parameterNode.templateTrimPlane
        ):
            return
        if (
            self._parameterNode.templateFinalizationViewLocked
            and caller.GetNumberOfDefinedControlPoints() >= 1
        ):
            normal = caller.GetNormalWorld()
            if any(abs(float(normal[index]) - (1.0 if index == 2 else 0.0)) > 1e-6 for index in range(3)):
                self._restoringTemplateTrimPlane = True
                try:
                    caller.SetNormalWorld((0.0, 0.0, 1.0))
                finally:
                    self._restoringTemplateTrimPlane = False
        self.logic.markFinalizedTemplateShellStale(
            self._parameterNode.finalizedTemplateShellModel,
            _("The Step 5C trim plane changed."),
        )
        qt.QTimer.singleShot(0, self._updateTemplateFinalization)

    def _onTemplateTrimCurveModified(self, caller=None, event=None) -> None:
        del event
        if not self._parameterNode or caller is not self._parameterNode.templateTrimCurve:
            return
        self.logic.markFinalizedTemplateShellStale(
            self._parameterNode.finalizedTemplateShellModel,
            _("The Step 5C margin curve changed."),
        )
        qt.QTimer.singleShot(0, self._updateTemplateFinalization)

    def _updateTemplateFinalization(self) -> None:
        if self._updatingTemplateFinalizationUI:
            return
        if not self._parameterNode or not self.logic:
            self._clearTemplateFinalization()
            return

        sourceShell = self._parameterNode.researchTemplateShellModel
        sleeveModel = self._parameterNode.researchTemplateSleeveModel
        planeNode = self._parameterNode.templateTrimPlane
        curveNode = self._parameterNode.templateTrimCurve
        finalShell = self._parameterNode.finalizedTemplateShellModel
        mode = (
            self._parameterNode.templateFinalizationMode
            if self._parameterNode.templateFinalizationMode in {"PlaneCut", "CurveCut"}
            else "PlaneCut"
        )
        keepRegion = self._parameterNode.templateFinalizationKeepRegion
        self._bindTemplateFinalizationEditNodes(planeNode, curveNode)

        sourceSummary = None
        sleeveSummary = None
        sourceError = ""
        try:
            sourceSummary = self.logic.getResearchTemplateModelSummary(
                sourceShell,
                "ResearchTemplateShell",
            )
            sleeveSummary = self.logic.getResearchTemplateModelSummary(
                sleeveModel,
                "ResearchTemplateSleeve",
            )
            if (
                sourceSummary["geometryState"] != "Current"
                or sleeveSummary["geometryState"] != "Current"
            ):
                raise ValueError(_("Regenerate stale Step 5B shell and sleeve outputs."))
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            sourceError = str(exc)

        editNode = planeNode if mode == "PlaneCut" else curveNode
        editError = ""
        if not sourceError and editNode:
            try:
                self.logic.validateTemplateFinalizationEditNode(
                    sourceShell,
                    editNode,
                    mode,
                )
            except ValueError as exc:
                editError = str(exc)

        finalSummary = None
        finalError = ""
        if finalShell:
            try:
                finalSummary = self.logic.getFinalizedTemplateShellSummary(finalShell)
                expectedGeometryJson = (
                    self.logic.templateFinalizationEditGeometryJson(editNode, mode)
                    if editNode and not editError
                    else ""
                )
                differs = bool(
                    sourceError
                    or editError
                    or finalSummary["sourceShell"] is not sourceShell
                    or finalSummary["sourceShellUpdatedUtc"]
                    != (sourceShell.GetAttribute("DENTOBOT.UpdatedUtc") or "")
                    or finalSummary["method"] != mode
                    or finalSummary["keepRegion"] != keepRegion
                    or finalSummary["editGeometryJson"] != expectedGeometryJson
                )
                if differs:
                    self.logic.markFinalizedTemplateShellStale(
                        finalShell,
                        _("Step 5B source or Step 5C trim settings changed."),
                    )
                    finalSummary = self.logic.getFinalizedTemplateShellSummary(finalShell)
            except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                finalError = str(exc)

        self.logic.refreshWorkflowLineageColors()
        self.logic.refreshWorkflowNodeStepTags()
        lineageNode = self._lineageSourceNode(
            (finalShell, editNode, sourceShell, sleeveModel),
            self._parameterNode.targetToothSegmentId,
        )
        self._updateLineageBadge(
            self.ui.templateFinalizationLineageLabel,
            lineageNode,
            _("Step 4A → Step 5A → Step 5B → Step 5C"),
            _("Inherited lineage: waiting for a current Step 5B shell."),
        )
        for selector, acceptsNode in (
            (self.ui.templateTrimPlaneSelector, self.logic.isTemplateTrimPlaneNode),
            (self.ui.templateTrimCurveSelector, self.logic.isTemplateTrimCurveNode),
            (
                self.ui.finalizedTemplateShellModelSelector,
                self.logic.isFinalizedTemplateShellModelNode,
            ),
        ):
            self._updateNodeSelectorLineageSwatches(selector, acceptsNode)

        self._updatingTemplateFinalizationUI = True
        try:
            self.ui.templateFinalizationSourceValueLabel.text = (
                sourceShell.GetName() if sourceShell else _("--")
            )
            self.ui.templateFinalizationModeComboBox.setCurrentIndex(
                1 if mode == "CurveCut" else 0
            )
            self._setTemplateFinalizationKeepChoices(mode, keepRegion)
            self.ui.templateFinalizationViewLockedCheckBox.checked = bool(
                self._parameterNode.templateFinalizationViewLocked
            )
            planeMode = mode == "PlaneCut"
            self.ui.templateTrimPlaneLabel.visible = planeMode
            self.ui.templateTrimPlaneSelector.visible = planeMode
            self.ui.createTemplateTrimPlaneButton.visible = planeMode
            self.ui.templateTrimCurveLabel.visible = not planeMode
            self.ui.templateTrimCurveSelector.visible = not planeMode
            self.ui.placeTemplateTrimCurveButton.visible = not planeMode
            sourceCurrent = not sourceError
            self.ui.continueTemplateFinalizationButton.enabled = sourceCurrent
            self.ui.createTemplateTrimPlaneButton.enabled = sourceCurrent
            self.ui.placeTemplateTrimCurveButton.enabled = sourceCurrent
            self.ui.restoreTemplateFinalizationViewButton.enabled = bool(
                self._templateFinalizationPriorVisibilityByNodeId
            )
            self.ui.applyTemplateFinalizationButton.enabled = bool(
                sourceCurrent and editNode and not editError
            )
            self.ui.openDynamicModelerButton.enabled = bool(
                finalSummary and finalSummary["dynamicModelerNode"]
            )
            self.ui.deleteTemplateFinalizationButton.enabled = bool(
                planeNode or curveNode or finalShell
            )
            finalCurrent = bool(
                finalSummary
                and finalSummary["geometryState"] == "Current"
                and not sourceError
                and finalSummary["sourceShell"] is sourceShell
            )
            self.ui.exportResearchTemplateButton.enabled = finalCurrent
        finally:
            self._updatingTemplateFinalizationUI = False

        if sourceError:
            message, style = sourceError, "color: #b36b00;"
        elif finalError:
            message, style = finalError, "color: #b00020;"
        elif editError:
            message, style = editError, "color: #b36b00;"
        elif not editNode:
            message, style = (
                _("Continue to isolate the raw shell, then create the selected trim control."),
                "color: #1f5f99;",
            )
        elif finalSummary and finalSummary["geometryState"] != "Current":
            message, style = (
                _("The finalized shell is stale. Preview / Apply Trim again."),
                "color: #b36b00;",
            )
        elif finalSummary:
            message, style = (
                _("The finalized shell is current and ready for explicit Step 5C STL export."),
                "color: #207227;",
            )
        else:
            message, style = (
                _("Adjust the trim control, verify the retained region, then preview the cut."),
                "color: #1f5f99;",
            )
        self.ui.templateFinalizationStatusLabel.text = message
        self.ui.templateFinalizationStatusLabel.styleSheet = style

    def onTemplateFinalizationInputChanged(self, *args) -> None:
        del args
        if not self._updatingTemplateFinalizationUI:
            self._updateTemplateFinalization()

    def onTemplateFinalizationModeChanged(self, index: int) -> None:
        if self._updatingTemplateFinalizationUI or not self._parameterNode:
            return
        mode = self._templateFinalizationModeFromIndex(index)
        self._parameterNode.templateFinalizationMode = mode
        choices = self._templateFinalizationKeepChoices(mode)
        self._parameterNode.templateFinalizationKeepRegion = choices[0][1]
        self.logic.markFinalizedTemplateShellStale(
            self._parameterNode.finalizedTemplateShellModel,
            _("The Step 5C trim method changed."),
        )
        self._updateTemplateFinalization()

    def onTemplateFinalizationKeepRegionChanged(self, index: int) -> None:
        if (
            self._updatingTemplateFinalizationUI
            or not self._parameterNode
            or index < 0
        ):
            return
        value = self.ui.templateFinalizationKeepRegionComboBox.itemData(index)
        if value:
            self._parameterNode.templateFinalizationKeepRegion = str(value)
            self.logic.markFinalizedTemplateShellStale(
                self._parameterNode.finalizedTemplateShellModel,
                _("The Step 5C retained region changed."),
            )
        self._updateTemplateFinalization()

    def _setTemplateTrimPlaneOrientationLock(self, locked: bool) -> None:
        planeNode = self._parameterNode.templateTrimPlane if self._parameterNode else None
        if not planeNode:
            return
        displayNode = planeNode.GetDisplayNode()
        if locked:
            self._restoringTemplateTrimPlane = True
            try:
                planeNode.SetNormalWorld((0.0, 0.0, 1.0))
            finally:
                self._restoringTemplateTrimPlane = False
        if displayNode:
            displayNode.SetHandlesInteractive(True)
            displayNode.SetTranslationHandleVisibility(True)
            displayNode.SetRotationHandleVisibility(not locked)

    def onTemplateFinalizationViewLockToggled(self, locked: bool) -> None:
        if self._updatingTemplateFinalizationUI or not self._parameterNode:
            return
        self._parameterNode.templateFinalizationViewLocked = bool(locked)
        self._setTemplateTrimPlaneOrientationLock(bool(locked))
        if locked and self._templateFinalizationCamera:
            self._lockTemplateFinalizationCamera(self._templateFinalizationCamera)

    def _lockTemplateFinalizationCamera(self, camera) -> None:
        if not camera or self._restoringTemplateFinalizationCamera:
            return
        focalPoint = camera.GetFocalPoint()
        position = camera.GetPosition()
        distance = max(
            math.sqrt(vtk.vtkMath.Distance2BetweenPoints(focalPoint, position)),
            1.0,
        )
        expectedPosition = (focalPoint[0], focalPoint[1] + distance, focalPoint[2])
        self._restoringTemplateFinalizationCamera = True
        try:
            camera.SetPosition(expectedPosition)
            camera.SetViewUp(0.0, 0.0, 1.0)
            camera.ParallelProjectionOn()
            camera.OrthogonalizeViewUp()
        finally:
            self._restoringTemplateFinalizationCamera = False

    def _onTemplateFinalizationCameraModified(self, caller=None, event=None) -> None:
        del event
        if (
            self._parameterNode
            and self._parameterNode.templateFinalizationViewLocked
        ):
            self._lockTemplateFinalizationCamera(caller)

    def _prepareTemplateFinalizationView(self, sourceShell) -> None:
        if not self._templateFinalizationPriorVisibilityByNodeId:
            for nodeIndex in range(slicer.mrmlScene.GetNumberOfNodes()):
                node = slicer.mrmlScene.GetNthNode(nodeIndex)
                if not node or not node.IsA("vtkMRMLDisplayableNode"):
                    continue
                displayNode = node.GetDisplayNode()
                if displayNode and node.GetID():
                    self._templateFinalizationPriorVisibilityByNodeId[node.GetID()] = bool(
                        displayNode.GetVisibility()
                    )
        for nodeId in self._templateFinalizationPriorVisibilityByNodeId:
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            displayNode = node.GetDisplayNode() if node else None
            if displayNode:
                displayNode.SetVisibility(False)
        sourceShell.GetDisplayNode().SetVisibility(True)
        editNode = (
            self._parameterNode.templateTrimPlane
            if self._parameterNode.templateFinalizationMode == "PlaneCut"
            else self._parameterNode.templateTrimCurve
        )
        if editNode and editNode.GetDisplayNode():
            editNode.GetDisplayNode().SetVisibility(True)

        layoutManager = slicer.app.layoutManager()
        if not layoutManager or layoutManager.threeDViewCount < 1:
            raise RuntimeError(_("No Slicer 3D view is available."))
        threeDView = layoutManager.threeDWidget(0).threeDView()
        camera = threeDView.cameraNode().GetCamera()
        if self._templateFinalizationCamera is not camera:
            if self._templateFinalizationCamera:
                self.removeObserver(
                    self._templateFinalizationCamera,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onTemplateFinalizationCameraModified,
                )
            self._templateFinalizationCamera = camera
            self.addObserver(
                camera,
                vtk.vtkCommand.ModifiedEvent,
                self._onTemplateFinalizationCameraModified,
            )
        bounds = [0.0] * 6
        sourceShell.GetRASBounds(bounds)
        center = tuple((bounds[2 * axis] + bounds[2 * axis + 1]) / 2.0 for axis in range(3))
        diagonal = math.sqrt(
            sum((bounds[2 * axis + 1] - bounds[2 * axis]) ** 2 for axis in range(3))
        )
        self._restoringTemplateFinalizationCamera = True
        try:
            camera.SetFocalPoint(center)
            camera.SetPosition(center[0], center[1] + max(diagonal * 2.0, 20.0), center[2])
            camera.SetViewUp(0.0, 0.0, 1.0)
            camera.ParallelProjectionOn()
            camera.SetParallelScale(
                max(bounds[1] - bounds[0], bounds[5] - bounds[4], 1.0) * 0.62
            )
            camera.OrthogonalizeViewUp()
            threeDView.resetCamera()
        finally:
            self._restoringTemplateFinalizationCamera = False
        if self._parameterNode.templateFinalizationViewLocked:
            self._lockTemplateFinalizationCamera(camera)
        threeDView.forceRender()

    def onContinueTemplateFinalization(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            sourceShell = self.logic.validateTemplateFinalizationSourceShell(
                self._parameterNode.researchTemplateShellModel
            )
            if self._parameterNode.templateFinalizationMode == "PlaneCut":
                planeNode = self._parameterNode.templateTrimPlane
                createdPlane = not planeNode
                if not planeNode:
                    planeNode = self.logic.createOrResetTemplateTrimPlane(sourceShell)
                    self._parameterNode.templateTrimPlane = planeNode
                self._setTemplateTrimPlaneOrientationLock(
                    self._parameterNode.templateFinalizationViewLocked
                )
            else:
                curveNode = self._parameterNode.templateTrimCurve
                if not curveNode:
                    curveNode = self.logic.createTemplateTrimCurve(sourceShell)
                    self._parameterNode.templateTrimCurve = curveNode
            self._prepareTemplateFinalizationView(sourceShell)
            if self._parameterNode.templateFinalizationMode == "PlaneCut" and createdPlane:
                self.logic.startHorizontalPlanePlacement(planeNode)
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onCreateTemplateTrimPlane(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            planeNode = self.logic.createOrResetTemplateTrimPlane(
                self._parameterNode.researchTemplateShellModel,
                self._parameterNode.templateTrimPlane,
            )
            self._parameterNode.templateTrimPlane = planeNode
            self._setTemplateTrimPlaneOrientationLock(
                self._parameterNode.templateFinalizationViewLocked
            )
            self._prepareTemplateFinalizationView(
                self._parameterNode.researchTemplateShellModel
            )
            self.logic.startHorizontalPlanePlacement(planeNode)
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onPlaceTemplateTrimCurve(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            curveNode = self._parameterNode.templateTrimCurve
            if not curveNode:
                curveNode = self.logic.createTemplateTrimCurve(
                    self._parameterNode.researchTemplateShellModel
                )
                self._parameterNode.templateTrimCurve = curveNode
            else:
                self.logic.validateTemplateFinalizationEditNode(
                    self._parameterNode.researchTemplateShellModel,
                    curveNode,
                    "CurveCut",
                    requireComplete=False,
                )
            self._prepareTemplateFinalizationView(
                self._parameterNode.researchTemplateShellModel
            )
            self.logic.startClosedCurvePlacement(curveNode)
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onApplyTemplateFinalization(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            self.logic.stopTrajectoryPlacement()
            finalShell, details = self.logic.createOrUpdateFinalizedTemplateShell(
                self._parameterNode.researchTemplateShellModel,
                self._parameterNode.templateTrimPlane,
                self._parameterNode.templateTrimCurve,
                self._parameterNode.templateFinalizationMode,
                self._parameterNode.templateFinalizationKeepRegion,
                self._parameterNode.finalizedTemplateShellModel,
            )
            self._parameterNode.finalizedTemplateShellModel = finalShell
            sourceDisplay = self._parameterNode.researchTemplateShellModel.GetDisplayNode()
            if sourceDisplay:
                sourceDisplay.SetVisibility(False)
            if finalShell.GetDisplayNode():
                finalShell.GetDisplayNode().SetVisibility(True)
            logging.info(
                "Generated DENTOBOT Step 5C finalized shell using %s/%s (%d triangles)",
                details["method"],
                details["keepRegion"],
                details["topology"]["triangleCount"],
            )
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            self.ui.templateFinalizationStatusLabel.text = str(exc)
            self.ui.templateFinalizationStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def onRestoreTemplateFinalizationView(self) -> None:
        for nodeId, visibility in self._templateFinalizationPriorVisibilityByNodeId.items():
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            displayNode = node.GetDisplayNode() if node else None
            if displayNode:
                displayNode.SetVisibility(visibility)
        self._templateFinalizationPriorVisibilityByNodeId.clear()
        if self._templateFinalizationCamera:
            self.removeObserver(
                self._templateFinalizationCamera,
                vtk.vtkCommand.ModifiedEvent,
                self._onTemplateFinalizationCameraModified,
            )
            self._templateFinalizationCamera = None
        self._updateTemplateFinalization()

    def onOpenDynamicModeler(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            summary = self.logic.getFinalizedTemplateShellSummary(
                self._parameterNode.finalizedTemplateShellModel
            )
            dynamicNode = summary["dynamicModelerNode"]
            if not dynamicNode:
                raise ValueError(_("Apply a Step 5C trim before opening Dynamic Modeler."))
            slicer.util.selectModule("DynamicModeler")
            moduleWidget = slicer.modules.dynamicmodeler.widgetRepresentation()
            treeView = slicer.util.findChild(moduleWidget, "SubjectHierarchyTreeView")
            if treeView:
                treeView.setCurrentNode(dynamicNode)
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onDeleteTemplateFinalization(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Delete the Step 5C plane, curve, finalized shell, and owned "
                "Dynamic Modeler auxiliaries? The raw Step 5B shell and sleeve will be kept."
            ),
            windowTitle=_("Delete Step 5C fit and trim"),
        ):
            return
        try:
            removals = self.logic.deleteTemplateFinalization(
                self._parameterNode.templateTrimPlane,
                self._parameterNode.templateTrimCurve,
                self._parameterNode.finalizedTemplateShellModel,
            )
            self._parameterNode.templateTrimPlane = None
            self._parameterNode.templateTrimCurve = None
            self._parameterNode.finalizedTemplateShellModel = None
            logging.info("Deleted %d DENTOBOT Step 5C nodes", len(removals))
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onExportResearchTemplate(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        directory = qt.QFileDialog.getExistingDirectory(
            slicer.util.mainWindow(),
            _("Select local folder for research STL files"),
            "",
        )
        if isinstance(directory, tuple):
            directory = directory[0]
        if not directory:
            return
        outputPaths = (
            Path(directory) / "DENTO_Research_Template_Shell.stl",
            Path(directory) / "DENTO_Research_Template_Sleeve.stl",
        )
        overwrite = False
        if any(path.exists() for path in outputPaths):
            overwrite = slicer.util.confirmYesNoDisplay(
                _("One or both STL files already exist. Replace them atomically?"),
                windowTitle=_("Replace research STL files"),
            )
            if not overwrite:
                return
        try:
            paths = self.logic.exportResearchTemplateStls(
                directory,
                self._parameterNode.finalizedTemplateShellModel,
                self._parameterNode.researchTemplateSleeveModel,
                overwrite=overwrite,
            )
            self.ui.templateFinalizationStatusLabel.text = (
                _("Exported research STL files: %1 and %2")
                .replace("%1", str(paths["shell"]))
                .replace("%2", str(paths["sleeve"]))
            )
            self.ui.templateFinalizationStatusLabel.styleSheet = "color: #207227;"
        except (OSError, RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

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
        return self.logic.resolveBackendConfiguration(
            "wsl" if os.name == "nt" else "local",
            self._parameterNode.wslDistribution.strip(),
            self._parameterNode.wslPythonPath.strip(),
            self._parameterNode.stagingRoot.strip(),
            self._parameterNode.inferenceDevice.strip(),
            self._parameterNode.useLauncherBackendConfiguration,
        )

    def onUseLauncherBackendConfigurationToggled(self, enabled: bool) -> None:
        if not self._parameterNode:
            return
        if self._parameterNode.useLauncherBackendConfiguration != bool(enabled):
            self._parameterNode.useLauncherBackendConfiguration = bool(enabled)
        self._updateBackendControls()

    def _backendIsRunning(self) -> bool:
        return self._backendProcess is not None

    def _updateBackendControls(self) -> None:
        if not self._parameterNode:
            return
        executionMode, distribution, pythonPath, stagingRoot, _device = (
            self._backendConfiguration()
        )
        launcherPython, launcherArtifactRoot = (
            self.logic.launcherBackendConfiguration()
        )
        launcherRequested = bool(
            executionMode == "local"
            and self._parameterNode.useLauncherBackendConfiguration
        )
        launcherAvailable = bool(launcherPython and launcherArtifactRoot)
        launcherActive = launcherRequested and launcherAvailable
        self.ui.wslPythonPathLineEdit.enabled = not launcherRequested
        self.ui.stagingRootLineEdit.enabled = not launcherRequested
        if launcherActive:
            self.ui.backendConfigurationSummaryLabel.text = _(
                "Managed automatically by the DENTOBOT launcher.\n"
                "Backend Python: %1\nRun records: %2"
            ).replace("%1", launcherPython).replace("%2", launcherArtifactRoot)
            self.ui.backendConfigurationSummaryLabel.styleSheet = (
                "color: #207227;"
            )
        elif launcherRequested:
            self.ui.backendConfigurationSummaryLabel.text = _(
                "Launcher configuration was not found. Start Slicer with "
                "scripts/launch-dentoworkflow.bash, or disable automatic "
                "configuration and enter the advanced overrides below."
            )
            self.ui.backendConfigurationSummaryLabel.styleSheet = (
                "color: #b00020;"
            )
        else:
            self.ui.backendConfigurationSummaryLabel.text = _(
                "Advanced manual override is active. These machine-specific "
                "paths are stored with the scene."
            )
            self.ui.backendConfigurationSummaryLabel.styleSheet = (
                "color: #b36b00;"
            )
        configured = bool(
            not (launcherRequested and not launcherAvailable)
            and pythonPath
            and (executionMode == "local" or distribution)
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
        launcherPython, launcherArtifactRoot = (
            self.logic.launcherBackendConfiguration()
        )
        if (
            executionMode == "local"
            and self._parameterNode
            and self._parameterNode.useLauncherBackendConfiguration
            and not (launcherPython and launcherArtifactRoot)
        ):
            raise ValueError(
                _(
                    "DENTOBOT launcher configuration is unavailable. Start "
                    "Slicer with scripts/launch-dentoworkflow.bash or disable "
                    "automatic configuration and enter manual overrides."
                )
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
                # Parent the fallback process to the module widget and break
                # its signal/closure references when it finishes.  A
                # parentless QProcess whose Python callbacks retain the
                # process can keep PythonQt/Slicer alive after the child has
                # already exited.
                process = qt.QProcess(self.parent)
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

                def releaseProcess() -> None:
                    for signal, callback in (
                        ("readyReadStandardOutput()", drainOutput),
                        ("finished(int,QProcess::ExitStatus)", processFinished),
                    ):
                        try:
                            process.disconnect(signal, callback)
                        except Exception:
                            logging.debug(
                                "DENTOBOT backend QProcess signal was already disconnected",
                                exc_info=True,
                            )
                    process.close()
                    process.deleteLater()

                def processFinished(
                    returnCode: int,
                    _exitStatus,
                ) -> None:
                    drainOutput()
                    if self._backendOutputBuffer:
                        logCallback(self._backendOutputBuffer)
                        self._backendOutputBuffer = ""
                    releaseProcess()
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
                    releaseProcess()
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
    BACKEND_PYTHON_ENVIRONMENT_VARIABLE = "DENTOBOT_BACKEND_PYTHON"
    RUN_ARTIFACT_ROOT_ENVIRONMENT_VARIABLE = "DENTOBOT_RUN_ARTIFACT_ROOT"
    REVIEW_METADATA_VERSION = "1.0"
    REVIEW_STATES = ("Unreviewed", "Needs Correction", "Reviewed")
    SOURCE_VOLUME_REFERENCE_ROLE = "DENTOBOT.SourceVolume"
    TARGET_SEGMENTATION_REFERENCE_ROLE = "DENTOBOT.TargetSegmentation"
    TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE = (
        "DENTOBOT.TargetBoundsSegmentation"
    )
    TARGET_BOUNDS_ROI_REFERENCE_ROLE = "DENTOBOT.TargetBoundsROI"
    TRAJECTORY_AUTO_NAME_ATTRIBUTE = "DENTOBOT.AutomaticTrajectoryName"
    LINEAGE_COLOR_ATTRIBUTE = "DENTOBOT.LineageColorRgb"
    LINEAGE_TARGET_SEGMENT_ATTRIBUTE = "DENTOBOT.LineageTargetSegmentID"
    LINEAGE_TARGET_FDI_ATTRIBUTE = "DENTOBOT.LineageTargetFdiNumber"
    TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE = (
        "DENTOBOT.TemplateSourceSegmentation"
    )
    TEMPLATE_MODEL_SCHEMA_VERSION = "1.0"
    TEMPLATE_GUIDE_SCHEMA_VERSION = "1.0"
    TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE = (
        "DENTOBOT.TemplateGuideSourceModel"
    )
    TEMPLATE_GUIDE_TRAJECTORY_REFERENCE_ROLE = (
        "DENTOBOT.TemplateGuideTrajectory"
    )
    TEMPLATE_GUIDE_ROI_REFERENCE_ROLE = "DENTOBOT.TemplateGuideROI"
    TEMPLATE_FINALIZATION_SCHEMA_VERSION = "1.0"
    TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE = (
        "DENTOBOT.TemplateFinalizationSourceShell"
    )
    TEMPLATE_FINALIZATION_EDIT_NODE_REFERENCE_ROLE = (
        "DENTOBOT.TemplateFinalizationEditNode"
    )
    TEMPLATE_FINALIZATION_DYNAMIC_MODELER_REFERENCE_ROLE = (
        "DENTOBOT.TemplateFinalizationDynamicModeler"
    )
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

    @classmethod
    def launcherBackendConfiguration(
        cls,
        environment: dict | None = None,
    ) -> tuple[str, str]:
        """Return launcher-provided paths without persisting them in MRML."""

        source = os.environ if environment is None else environment
        return (
            str(
                source.get(cls.BACKEND_PYTHON_ENVIRONMENT_VARIABLE) or ""
            ).strip(),
            str(
                source.get(cls.RUN_ARTIFACT_ROOT_ENVIRONMENT_VARIABLE) or ""
            ).strip(),
        )

    @classmethod
    def resolveBackendConfiguration(
        cls,
        executionMode: str,
        distribution: str,
        pythonPath: str,
        stagingRoot: str,
        device: str,
        useLauncherConfiguration: bool,
        environment: dict | None = None,
    ) -> tuple[str, str, str, str, str]:
        """Resolve portable launcher settings or explicit scene overrides."""

        executionMode = executionMode.strip()
        distribution = distribution.strip()
        pythonPath = pythonPath.strip()
        stagingRoot = stagingRoot.strip()
        device = device.strip()
        if executionMode == "local" and useLauncherConfiguration:
            launcherPython, launcherStagingRoot = (
                cls.launcherBackendConfiguration(environment)
            )
            if launcherPython and launcherStagingRoot:
                pythonPath = launcherPython
                stagingRoot = launcherStagingRoot
            else:
                pythonPath = ""
                stagingRoot = ""
        return (
            executionMode,
            distribution,
            pythonPath,
            stagingRoot,
            device,
        )

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

    @staticmethod
    def lineageColorForTarget(
        segmentId: str,
        fdiNumber: str = "",
    ) -> tuple[float, float, float]:
        """Return a stable vivid color for one authoritative target tooth."""

        normalizedSegmentId = str(segmentId or "").strip()
        if not normalizedSegmentId:
            raise ValueError(_("A target segment ID is required for lineage color."))
        fdiMatch = re.fullmatch(r"([1-4])([1-8])", str(fdiNumber or ""))
        if fdiMatch:
            ordinal = (int(fdiMatch.group(1)) - 1) * 8 + int(
                fdiMatch.group(2)
            ) - 1
        else:
            ordinal = (
                uuid.uuid5(uuid.NAMESPACE_OID, normalizedSegmentId).int % 32
            )
        hue = (0.055 + ordinal * 0.618033988749895) % 1.0
        return tuple(
            round(float(component), 6)
            for component in colorsys.hsv_to_rgb(hue, 0.74, 0.94)
        )

    @classmethod
    def lineageColorFromNode(cls, node) -> tuple[float, float, float] | None:
        """Read a validated persisted target-lineage color from one node."""

        if not node:
            return None
        try:
            values = json.loads(
                node.GetAttribute(cls.LINEAGE_COLOR_ATTRIBUTE) or "null"
            )
        except (json.JSONDecodeError, TypeError):
            return None
        if (
            not isinstance(values, list)
            or len(values) != 3
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
                or float(value) > 1.0
                for value in values
            )
        ):
            return None
        return tuple(float(value) for value in values)

    @classmethod
    def setNodeLineageColor(
        cls,
        node,
        color: tuple[float, float, float],
        segmentId: str,
        fdiNumber: str = "",
    ) -> bool:
        """Persist and display one visual lineage color without changing identity."""

        normalizedColor = tuple(round(float(value), 6) for value in color)
        if (
            len(normalizedColor) != 3
            or any(
                not math.isfinite(value) or value < 0.0 or value > 1.0
                for value in normalizedColor
            )
        ):
            raise ValueError(_("A lineage color must contain three RGB values."))
        serializedColor = json.dumps(
            list(normalizedColor),
            separators=(",", ":"),
        )
        normalizedSegmentId = str(segmentId or "").strip()
        normalizedFdi = str(fdiNumber or "").strip()
        changed = any(
            (
                node.GetAttribute(cls.LINEAGE_COLOR_ATTRIBUTE)
                != serializedColor,
                node.GetAttribute(cls.LINEAGE_TARGET_SEGMENT_ATTRIBUTE)
                != normalizedSegmentId,
                node.GetAttribute(cls.LINEAGE_TARGET_FDI_ATTRIBUTE)
                != normalizedFdi,
            )
        )
        if changed:
            wasModifying = node.StartModify()
            try:
                node.SetAttribute(cls.LINEAGE_COLOR_ATTRIBUTE, serializedColor)
                node.SetAttribute(
                    cls.LINEAGE_TARGET_SEGMENT_ATTRIBUTE,
                    normalizedSegmentId,
                )
                node.SetAttribute(
                    cls.LINEAGE_TARGET_FDI_ATTRIBUTE,
                    normalizedFdi,
                )
            finally:
                node.EndModify(wasModifying)
        if node.IsA("vtkMRMLDisplayableNode"):
            node.CreateDefaultDisplayNodes()
            displayNode = node.GetDisplayNode()
            if displayNode:
                displayNode.SetColor(*normalizedColor)
                if hasattr(displayNode, "SetSelectedColor"):
                    displayNode.SetSelectedColor(*normalizedColor)
                if hasattr(displayNode, "SetActiveColor"):
                    displayNode.SetActiveColor(*normalizedColor)
        return changed

    @classmethod
    def clearNodeLineageColor(cls, node) -> None:
        if not node:
            return
        attributeNames = (
            cls.LINEAGE_COLOR_ATTRIBUTE,
            cls.LINEAGE_TARGET_SEGMENT_ATTRIBUTE,
            cls.LINEAGE_TARGET_FDI_ATTRIBUTE,
        )
        if not any(node.GetAttribute(name) for name in attributeNames):
            return
        wasModifying = node.StartModify()
        try:
            for attributeName in attributeNames:
                node.SetAttribute(attributeName, None)
        finally:
            node.EndModify(wasModifying)

    def dentobotTrajectoriesForTarget(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> list[vtkMRMLMarkupsLineNode]:
        """Return every DENTOBOT trajectory in one authoritative tooth group."""

        segmentationId = segmentationNode.GetID() if segmentationNode else None
        return [
            node
            for node in slicer.util.getNodesByClass(
                "vtkMRMLMarkupsLineNode"
            )
            if (
                self.isDentobotTrajectoryNode(node)
                and node.GetAttribute("DENTOBOT.TargetSegmentID") == segmentId
                and node.GetNodeReference(
                    self.TARGET_SEGMENTATION_REFERENCE_ROLE
                )
                and node.GetNodeReference(
                    self.TARGET_SEGMENTATION_REFERENCE_ROLE
                ).GetID()
                == segmentationId
            )
        ]

    def isTargetBoundsRoiForTarget(
        self,
        roiNode: vtkMRMLMarkupsROINode | None,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> bool:
        """Return whether an ROI is the exact Step 4A bounds for one tooth."""

        referencedSegmentation = (
            roiNode.GetNodeReference(
                self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE
            )
            if roiNode and roiNode.IsA("vtkMRMLMarkupsROINode")
            else None
        )
        return bool(
            referencedSegmentation
            and segmentationNode
            and referencedSegmentation.GetID() == segmentationNode.GetID()
            and roiNode.GetAttribute("DENTOBOT.BoundsRole")
            == "TargetToothAABB"
            and roiNode.GetAttribute("DENTOBOT.TargetSegmentID") == segmentId
        )

    def findTargetBoundsRoi(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> vtkMRMLMarkupsROINode | None:
        """Find an existing exact target ROI so tooth switching creates no duplicate."""

        for roiNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsROINode"
        ):
            if self.isTargetBoundsRoiForTarget(
                roiNode,
                segmentationNode,
                segmentId,
            ):
                return roiNode
        return None

    def refreshWorkflowLineageColors(self) -> list[str]:
        """Propagate target-tooth colors through role/reference-linked descendants."""

        changedNodeIds = []
        groupColors: dict[tuple[str, str], tuple[float, float, float]] = {}
        groupFdi: dict[tuple[str, str], str] = {}
        for trajectoryNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsLineNode"
        ):
            if not self.isDentobotTrajectoryNode(trajectoryNode):
                continue
            try:
                self.enforceTrajectoryControlPointInvariant(trajectoryNode)
                segmentationNode = trajectoryNode.GetNodeReference(
                    self.TARGET_SEGMENTATION_REFERENCE_ROLE
                )
                segmentId = trajectoryNode.GetAttribute(
                    "DENTOBOT.TargetSegmentID"
                ) or ""
                targetRecord = self.validateTargetTooth(
                    segmentationNode,
                    segmentId,
                )
            except ValueError:
                continue
            key = (segmentationNode.GetID(), segmentId)
            fdiNumber = targetRecord.get("fdiNumber") or ""
            color = self.lineageColorForTarget(segmentId, fdiNumber)
            groupColors[key] = color
            groupFdi[key] = fdiNumber
            if self.setNodeLineageColor(
                trajectoryNode,
                color,
                segmentId,
                fdiNumber,
            ):
                changedNodeIds.append(trajectoryNode.GetID())

        for roiNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsROINode"
        ):
            if roiNode.GetAttribute("DENTOBOT.BoundsRole") != "TargetToothAABB":
                continue
            segmentationNode = roiNode.GetNodeReference(
                self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE
            )
            segmentId = roiNode.GetAttribute("DENTOBOT.TargetSegmentID") or ""
            key = (
                segmentationNode.GetID() if segmentationNode else "",
                segmentId,
            )
            color = groupColors.get(key)
            if color and self.setNodeLineageColor(
                roiNode,
                color,
                segmentId,
                groupFdi.get(key, ""),
            ):
                changedNodeIds.append(roiNode.GetID())

        supportLineages: dict[str, tuple[tuple[float, float, float], str, str]] = {}
        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isDraftTemplateSupportModelNode(modelNode):
                continue
            segmentationNode = modelNode.GetNodeReference(
                self.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE
            )
            segmentId = modelNode.GetAttribute("DENTOBOT.TargetSegmentID") or ""
            key = (
                segmentationNode.GetID() if segmentationNode else "",
                segmentId,
            )
            color = groupColors.get(key)
            if not color:
                continue
            fdiNumber = groupFdi.get(key, "")
            if self.setNodeLineageColor(
                modelNode,
                color,
                segmentId,
                fdiNumber,
            ):
                changedNodeIds.append(modelNode.GetID())
            supportLineages[modelNode.GetID()] = (
                color,
                segmentId,
                fdiNumber,
            )

        for roiNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsROINode"
        ):
            if not self.isTemplateShellRoiNode(roiNode):
                continue
            supportModel = roiNode.GetNodeReference(
                self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
            )
            lineage = (
                supportLineages.get(supportModel.GetID())
                if supportModel
                else None
            )
            if lineage and self.setNodeLineageColor(roiNode, *lineage):
                changedNodeIds.append(roiNode.GetID())

        researchLineages: dict[str, tuple[tuple[float, float, float], str, str]] = {}
        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isResearchTemplateModelNode(modelNode):
                continue
            supportModel = modelNode.GetNodeReference(
                self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
            )
            lineage = (
                supportLineages.get(supportModel.GetID())
                if supportModel
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())
            if lineage:
                researchLineages[modelNode.GetID()] = lineage

        for className, acceptsNode in (
            ("vtkMRMLMarkupsPlaneNode", self.isTemplateTrimPlaneNode),
            ("vtkMRMLMarkupsClosedCurveNode", self.isTemplateTrimCurveNode),
        ):
            for markupNode in slicer.util.getNodesByClass(className):
                if not acceptsNode(markupNode):
                    continue
                sourceShell = markupNode.GetNodeReference(
                    self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE
                )
                lineage = (
                    researchLineages.get(sourceShell.GetID())
                    if sourceShell
                    else None
                )
                if lineage and self.setNodeLineageColor(markupNode, *lineage):
                    changedNodeIds.append(markupNode.GetID())

        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isFinalizedTemplateShellModelNode(modelNode):
                continue
            sourceShell = modelNode.GetNodeReference(
                self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE
            )
            lineage = (
                researchLineages.get(sourceShell.GetID())
                if sourceShell
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())
        return changedNodeIds

    def applyTrajectoryGroupEmphasis(
        self,
        segmentationNode: vtkMRMLSegmentationNode | None,
        activeSegmentId: str,
    ) -> None:
        """Emphasize one tooth's trajectories while preserving visibility state."""

        activeSegmentationId = (
            segmentationNode.GetID() if segmentationNode else ""
        )
        for trajectoryNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsLineNode"
        ):
            if not self.isDentobotTrajectoryNode(trajectoryNode):
                continue
            displayNode = trajectoryNode.GetDisplayNode()
            if not displayNode:
                continue
            targetSegmentation = trajectoryNode.GetNodeReference(
                self.TARGET_SEGMENTATION_REFERENCE_ROLE
            )
            isActiveGroup = bool(
                activeSegmentId
                and targetSegmentation
                and targetSegmentation.GetID() == activeSegmentationId
                and trajectoryNode.GetAttribute("DENTOBOT.TargetSegmentID")
                == activeSegmentId
            )
            hasActiveGroup = bool(activeSegmentationId and activeSegmentId)
            displayNode.SetOpacity(
                1.0 if isActiveGroup else 0.38 if hasActiveGroup else 0.68
            )
            displayNode.SetLineThickness(0.55 if isActiveGroup else 0.25)
            displayNode.SetGlyphScale(1.45 if isActiveGroup else 1.0)
            displayNode.SetPointLabelsVisibility(isActiveGroup)

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
        roiIsMarkup = bool(
            roiNode and roiNode.IsA("vtkMRMLMarkupsROINode")
        )
        boundsRole = (
            roiNode.GetAttribute("DENTOBOT.BoundsRole")
            if roiIsMarkup
            else None
        )
        markupsRole = (
            roiNode.GetAttribute("DENTOBOT.MarkupsRole")
            if roiIsMarkup
            else None
        )
        reusedRoi = bool(
            roiIsMarkup
            and (
                (
                    boundsRole == "TargetToothAABB"
                    and roiNode.GetAttribute("DENTOBOT.TargetSegmentID")
                    == targetRecord["segmentId"]
                    and roiNode.GetNodeReference(
                        self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE
                    )
                    and roiNode.GetNodeReference(
                        self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE
                    ).GetID()
                    == segmentationNode.GetID()
                )
                or (not boundsRole and not markupsRole)
            )
        )
        previousVisibility = bool(
            reusedRoi
            and roiNode.GetDisplayNode()
            and roiNode.GetDisplayNode().GetVisibility()
        )
        if not reusedRoi:
            roiNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsROINode",
                f'[Step 4A] DENTO Target Bounds FDI {targetRecord["fdiNumber"]}',
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
                f'[Step 4A] DENTO Target Bounds FDI {targetRecord["fdiNumber"]}'
            )
            roiNode.SetCenterWorld(center)
            roiNode.SetSizeWorld(size)
            roiNode.SetLocked(True)
            roiNode.SetAttribute("DENTOBOT.BoundsRole", "TargetToothAABB")
            roiNode.SetAttribute("DENTOBOT.MarkupsRole", None)
            roiNode.SetAttribute("DENTOBOT.TemplateGuideSchemaVersion", None)
            roiNode.SetNodeReferenceID(
                self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE,
                None,
            )
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
            displayNode.SetVisibility(previousVisibility if reusedRoi else True)
            displayNode.SetVisibility2D(True)
            displayNode.SetVisibility3D(True)
            displayNode.SetFillVisibility(False)
            displayNode.SetOutlineVisibility(True)
            displayNode.SetPropertiesLabelVisibility(False)
            if hasattr(displayNode, "SetHandlesInteractive"):
                displayNode.SetHandlesInteractive(False)
        targetTrajectories = self.dentobotTrajectoriesForTarget(
            segmentationNode,
            targetRecord["segmentId"],
        )
        if targetTrajectories:
            self.setNodeLineageColor(
                roiNode,
                self.lineageColorForTarget(
                    targetRecord["segmentId"],
                    targetRecord.get("fdiNumber") or "",
                ),
                targetRecord["segmentId"],
                targetRecord.get("fdiNumber") or "",
            )
        else:
            self.clearNodeLineageColor(roiNode)
            if displayNode:
                displayNode.SetColor(1.0, 0.65, 0.0)
                displayNode.SetSelectedColor(1.0, 0.8, 0.2)
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

    @staticmethod
    def _isAuxiliaryNodeReferenced(auxiliaryNode) -> bool:
        """Return whether another scene node still owns an auxiliary node."""

        auxiliaryNodeId = auxiliaryNode.GetID() if auxiliaryNode else None
        if not auxiliaryNodeId:
            return False
        if auxiliaryNode.IsA("vtkMRMLDisplayNode"):
            for displayableNode in slicer.util.getNodesByClass(
                "vtkMRMLDisplayableNode"
            ):
                for index in range(displayableNode.GetNumberOfDisplayNodes()):
                    referencedNode = displayableNode.GetNthDisplayNode(index)
                    if (
                        referencedNode
                        and referencedNode.GetID() == auxiliaryNodeId
                    ):
                        return True
        if auxiliaryNode.IsA("vtkMRMLStorageNode"):
            for storableNode in slicer.util.getNodesByClass(
                "vtkMRMLStorableNode"
            ):
                referencedNode = storableNode.GetStorageNode()
                if (
                    referencedNode
                    and referencedNode.GetID() == auxiliaryNodeId
                ):
                    return True
        return False

    @classmethod
    def _removeSceneNodeAndOwnedAuxiliaries(cls, node) -> dict:
        """Remove one data node and only its now-unreferenced auxiliaries."""

        scene = slicer.mrmlScene
        if not node or not node.GetID() or not scene.IsNodePresent(node):
            raise ValueError(_("The selected node is no longer in the scene."))

        nodeId = node.GetID()
        nodeName = node.GetName() or ""
        auxiliaryNodes = {}
        if node.IsA("vtkMRMLDisplayableNode"):
            for index in range(node.GetNumberOfDisplayNodes()):
                auxiliaryNode = node.GetNthDisplayNode(index)
                if auxiliaryNode and auxiliaryNode.GetID():
                    auxiliaryNodes[auxiliaryNode.GetID()] = auxiliaryNode
        if node.IsA("vtkMRMLStorableNode"):
            storageNode = node.GetStorageNode()
            if storageNode and storageNode.GetID():
                auxiliaryNodes[storageNode.GetID()] = storageNode

        scene.RemoveNode(node)
        if scene.GetNodeByID(nodeId):
            raise RuntimeError(_("Slicer did not remove the selected node."))

        removedAuxiliaryNodeIds = []
        for auxiliaryNodeId, auxiliaryNode in auxiliaryNodes.items():
            if (
                scene.GetNodeByID(auxiliaryNodeId)
                and not cls._isAuxiliaryNodeReferenced(auxiliaryNode)
            ):
                scene.RemoveNode(auxiliaryNode)
                removedAuxiliaryNodeIds.append(auxiliaryNodeId)
        return {
            "nodeId": nodeId,
            "nodeName": nodeName,
            "auxiliaryNodeIds": removedAuxiliaryNodeIds,
        }

    @staticmethod
    def isDentobotTrajectoryNode(trajectoryNode) -> bool:
        return bool(
            trajectoryNode
            and trajectoryNode.IsA("vtkMRMLMarkupsLineNode")
            and trajectoryNode.GetAttribute("DENTOBOT.TrajectoryRole")
            == "EntryToTarget"
        )

    def validateDentobotTrajectoryForDeletion(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> None:
        if not self.isDentobotTrajectoryNode(trajectoryNode):
            raise ValueError(
                _("Select a DENTOBOT Step 4A trajectory to delete.")
            )
        if not slicer.mrmlScene.IsNodePresent(trajectoryNode):
            raise ValueError(_("The selected trajectory is no longer in the scene."))

    def deleteTrajectoryNode(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> dict:
        """Delete one DENTOBOT trajectory without deleting its target inputs."""

        self.validateDentobotTrajectoryForDeletion(trajectoryNode)
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if (
            selectionNode
            and selectionNode.GetActivePlaceNodeID() == trajectoryNode.GetID()
        ):
            self.stopTrajectoryPlacement()
        parameterNode = self.getParameterNode()
        if parameterNode.trajectoryLine is trajectoryNode:
            parameterNode.trajectoryLine = None
        return self._removeSceneNodeAndOwnedAuxiliaries(trajectoryNode)

    def enforceTrajectoryControlPointInvariant(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> None:
        """Enforce a non-destructive two-point Entry/Target line contract."""

        if not trajectoryNode or not trajectoryNode.IsA(
            "vtkMRMLMarkupsLineNode"
        ):
            raise ValueError(_("Select a valid trajectory line node."))
        if (
            trajectoryNode.GetNumberOfControlPoints() > 2
            or trajectoryNode.GetNumberOfDefinedControlPoints() > 2
        ):
            raise ValueError(
                _(
                    "A trajectory may contain only Entry and Target. Remove "
                    "extra points before using it in DENTOBOT."
                )
            )
        if trajectoryNode.GetMaximumNumberOfControlPoints() != 2:
            raise ValueError(
                _("The selected line does not enforce the two-point trajectory contract.")
            )
        self.labelTrajectoryControlPoints(trajectoryNode)

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
        self.enforceTrajectoryControlPointInvariant(trajectoryNode)
        return trajectoryNode

    def enableAutomaticTrajectoryName(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> None:
        """Opt a DENTOBOT trajectory into informative, managed display names."""

        if not self.isDentobotTrajectoryNode(trajectoryNode):
            raise ValueError(_("Select a DENTOBOT Step 4A trajectory."))
        trajectoryNode.SetAttribute(self.TRAJECTORY_AUTO_NAME_ATTRIBUTE, "1")

    @staticmethod
    def _trajectoryStateLabel(trajectorySummary: dict) -> str:
        pointCount = trajectorySummary["definedPointCount"]
        if pointCount == 0:
            return _("Empty")
        if pointCount == 1:
            return _("Entry only")
        return _("Complete") if trajectorySummary["isValid"] else _("Invalid")

    def refreshManagedTrajectoryNames(self) -> list[str]:
        """Disambiguate managed and legacy default trajectory names.

        Names are presentation only. Grouping and numbering use persisted MRML
        references and segment IDs, never editable node names.
        """

        trajectories = [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode")
            if self.isDentobotTrajectoryNode(node)
        ]
        for trajectoryNode in trajectories:
            name = trajectoryNode.GetName() or ""
            if re.fullmatch(
                r"(?:\[Step 4A\]\s+)?DENTO Trajectory FDI\s+\d+",
                name,
            ):
                trajectoryNode.SetAttribute(
                    self.TRAJECTORY_AUTO_NAME_ATTRIBUTE,
                    "1",
                )

        managedGroups: dict[tuple[str, str], list] = {}
        for trajectoryNode in trajectories:
            if trajectoryNode.GetAttribute(
                self.TRAJECTORY_AUTO_NAME_ATTRIBUTE
            ) != "1":
                continue
            segmentationNode = trajectoryNode.GetNodeReference(
                self.TARGET_SEGMENTATION_REFERENCE_ROLE
            )
            segmentId = trajectoryNode.GetAttribute(
                "DENTOBOT.TargetSegmentID"
            ) or ""
            key = (
                segmentationNode.GetID() if segmentationNode else "",
                segmentId,
            )
            managedGroups.setdefault(key, []).append(trajectoryNode)

        changedNodeIds = []
        for (_segmentationId, segmentId), group in managedGroups.items():
            for index, trajectoryNode in enumerate(group, start=1):
                fdiNumber = trajectoryNode.GetAttribute(
                    "DENTOBOT.TargetFdiNumber"
                ) or ""
                targetLabel = (
                    f"FDI {fdiNumber}"
                    if fdiNumber
                    else segmentId
                    if segmentId
                    else _("Unassigned")
                )
                stateLabel = self._trajectoryStateLabel(
                    self.getTrajectorySummary(trajectoryNode)
                )
                desiredName = _("[Step 4A] DENTO %1 - Trajectory %2 [%3]")
                desiredName = (
                    desiredName.replace("%1", targetLabel)
                    .replace("%2", str(index))
                    .replace("%3", stateLabel)
                )
                if trajectoryNode.GetName() != desiredName:
                    trajectoryNode.SetName(desiredName)
                    changedNodeIds.append(trajectoryNode.GetID())
        return changedNodeIds

    @staticmethod
    def ensureWorkflowNodeStepTag(node, stepName: str) -> bool:
        """Prefix one workflow-owned node for clear Slicer Data-view grouping."""

        if not node:
            return False
        currentName = node.GetName() or node.GetClassName()
        untaggedName = re.sub(
            r"^\[Step [^\]]+\]\s*",
            "",
            currentName,
        )
        desiredName = f"[{stepName}] {untaggedName}"
        if currentName == desiredName:
            return False
        node.SetName(desiredName)
        return True

    def refreshWorkflowNodeStepTags(self) -> list[str]:
        """Tag every DENTOBOT-owned Step 4A/5A/5B/5C scene object by role."""

        taggedNodeIds = []
        for trajectoryNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsLineNode"
        ):
            if (
                self.isDentobotTrajectoryNode(trajectoryNode)
                and self.ensureWorkflowNodeStepTag(
                    trajectoryNode,
                    "Step 4A",
                )
            ):
                taggedNodeIds.append(trajectoryNode.GetID())
        for roiNode in slicer.util.getNodesByClass("vtkMRMLMarkupsROINode"):
            stepName = None
            if roiNode.GetAttribute("DENTOBOT.BoundsRole") == "TargetToothAABB":
                stepName = "Step 4A"
            elif self.isTemplateShellRoiNode(roiNode):
                stepName = "Step 5B"
            if stepName and self.ensureWorkflowNodeStepTag(roiNode, stepName):
                taggedNodeIds.append(roiNode.GetID())
        for className, acceptsNode in (
            ("vtkMRMLMarkupsPlaneNode", self.isTemplateTrimPlaneNode),
            ("vtkMRMLMarkupsClosedCurveNode", self.isTemplateTrimCurveNode),
        ):
            for markupNode in slicer.util.getNodesByClass(className):
                if (
                    acceptsNode(markupNode)
                    and self.ensureWorkflowNodeStepTag(markupNode, "Step 5C")
                ):
                    taggedNodeIds.append(markupNode.GetID())
        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            role = modelNode.GetAttribute("DENTOBOT.ModelRole")
            stepName = (
                "Step 5A"
                if role == "TemplateSupportDraft"
                else "Step 5B"
                if role in {"ResearchTemplateShell", "ResearchTemplateSleeve"}
                else "Step 5C"
                if role == "FinalizedTemplateShell"
                else None
            )
            if stepName and self.ensureWorkflowNodeStepTag(modelNode, stepName):
                taggedNodeIds.append(modelNode.GetID())
        return taggedNodeIds

    def configureTrajectoryTarget(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> dict:
        """Associate a draft trajectory with one authoritative tooth segment."""

        self.enforceTrajectoryControlPointInvariant(trajectoryNode)
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
        self.setNodeLineageColor(
            trajectoryNode,
            self.lineageColorForTarget(
                targetRecord["segmentId"],
                targetRecord.get("fdiNumber") or "",
            ),
            targetRecord["segmentId"],
            targetRecord.get("fdiNumber") or "",
        )
        self.refreshWorkflowLineageColors()
        return targetRecord

    def getTrajectoryTargetAssociation(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> dict | None:
        """Return and validate a trajectory's persisted target association.

        An entirely unassociated Markups line returns ``None`` so it can be
        adopted for the active tooth. Partial or dangling persisted state is
        rejected rather than silently overwritten.
        """

        self.getTrajectorySummary(trajectoryNode)
        segmentationNode = trajectoryNode.GetNodeReference(
            self.TARGET_SEGMENTATION_REFERENCE_ROLE
        )
        segmentId = trajectoryNode.GetAttribute(
            "DENTOBOT.TargetSegmentID"
        ) or ""
        roiNode = trajectoryNode.GetNodeReference(
            self.TARGET_BOUNDS_ROI_REFERENCE_ROLE
        )
        hasOtherTargetMetadata = any(
            trajectoryNode.GetAttribute(attributeName)
            for attributeName in (
                "DENTOBOT.TargetSegmentName",
                "DENTOBOT.TargetFdiNumber",
            )
        )
        if not segmentationNode and not segmentId:
            if roiNode or hasOtherTargetMetadata:
                raise ValueError(
                    _(
                        "The selected trajectory has an incomplete saved target "
                        "association. Repair or delete it; DENTOBOT will not "
                        "guess from its editable name."
                    )
                )
            return None
        if not segmentationNode or not segmentId:
            raise ValueError(
                _(
                    "The selected trajectory has an incomplete saved target "
                    "association. Repair or delete it; DENTOBOT will not guess "
                    "from its editable name."
                )
            )
        if not segmentationNode.IsA("vtkMRMLSegmentationNode"):
            raise ValueError(
                _("The selected trajectory references an invalid segmentation.")
            )
        targetRecord = self.validateTargetTooth(segmentationNode, segmentId)
        if roiNode:
            if not roiNode.IsA("vtkMRMLMarkupsROINode"):
                raise ValueError(
                    _("The selected trajectory references an invalid target ROI.")
                )
            roiRole = roiNode.GetAttribute("DENTOBOT.BoundsRole")
            roiSegmentId = roiNode.GetAttribute("DENTOBOT.TargetSegmentID")
            roiSegmentation = roiNode.GetNodeReference(
                self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE
            )
            if (
                roiRole != "TargetToothAABB"
                or roiSegmentId != segmentId
                or roiSegmentation is not segmentationNode
            ):
                raise ValueError(
                    _(
                        "The selected trajectory's saved target ROI does not "
                        "match its target tooth association."
                    )
                )
        return {
            "segmentationNode": segmentationNode,
            "targetRecord": targetRecord,
            "targetBoundsRoi": roiNode,
        }

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
        self.clearNodeLineageColor(trajectoryNode)
        displayNode = trajectoryNode.GetDisplayNode()
        if displayNode:
            displayNode.SetColor(0.65, 0.65, 0.65)
            displayNode.SetSelectedColor(0.75, 0.75, 0.75)

    @staticmethod
    def encodeTemplateSupportSegmentIds(segmentIds: list[str]) -> str:
        """Serialize an ordered, unique list of manually selected support teeth."""

        if not isinstance(segmentIds, list):
            raise ValueError(_("Support-tooth segment IDs must be provided as a list."))
        normalizedIds = []
        seenIds = set()
        for value in segmentIds:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(_("Every support tooth must have a segment ID."))
            segmentId = value.strip()
            if segmentId in seenIds:
                raise ValueError(_("A support tooth cannot be selected more than once."))
            seenIds.add(segmentId)
            normalizedIds.append(segmentId)
        return json.dumps(normalizedIds, separators=(",", ":"))

    @staticmethod
    def decodeTemplateSupportSegmentIds(serializedIds: str) -> list[str]:
        """Read persisted support-tooth IDs without accepting malformed state."""

        try:
            values = json.loads(serializedIds or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError(_("Stored support-tooth selection is not valid JSON.")) from exc
        if not isinstance(values, list):
            raise ValueError(_("Stored support-tooth selection must be a list."))
        return DENTOWorkflowLogic._validateUniqueSegmentIdList(values)

    @staticmethod
    def _validateUniqueSegmentIdList(segmentIds: list) -> list[str]:
        normalizedIds = []
        seenIds = set()
        for value in segmentIds:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(_("Every support tooth must have a segment ID."))
            segmentId = value.strip()
            if segmentId in seenIds:
                raise ValueError(_("A support tooth cannot be selected more than once."))
            seenIds.add(segmentId)
            normalizedIds.append(segmentId)
        return normalizedIds

    def validateTemplateSupportSelection(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        targetSegmentId: str,
        supportSegmentIds: list[str],
    ) -> dict:
        """Validate one target plus any positive number of user-selected teeth."""

        targetRecord = self.validateTargetTooth(
            segmentationNode,
            targetSegmentId,
        )
        if self.getSegmentationReviewState(segmentationNode) != "Reviewed":
            raise ValueError(
                _(
                    "Mark the authoritative segmentation Reviewed before "
                    "creating a draft support-anatomy model."
                )
            )
        normalizedSupportIds = self._validateUniqueSegmentIdList(
            supportSegmentIds
        )
        if not normalizedSupportIds:
            raise ValueError(_("Select at least one support tooth."))
        if targetRecord["segmentId"] in normalizedSupportIds:
            raise ValueError(_("The target tooth cannot also be a support tooth."))

        toothRecordsById = {
            record["segmentId"]: record
            for record in self.getTargetToothRecords(segmentationNode)
        }
        supportRecords = []
        for supportId in normalizedSupportIds:
            record = toothRecordsById.get(supportId)
            if not record:
                raise ValueError(
                    _(
                        "A selected support tooth does not exist or is not a "
                        "whole-tooth segment: %1"
                    ).replace("%1", supportId)
                )
            supportRecords.append(record)
        return {
            "target": targetRecord,
            "supports": supportRecords,
            "supportSegmentIds": normalizedSupportIds,
        }

    @staticmethod
    def _getClosedSurfaceCopy(
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> vtk.vtkPolyData:
        closedSurface = vtk.vtkPolyData()
        success = (
            slicer.vtkSlicerSegmentationsModuleLogic
            .GetSegmentClosedSurfaceRepresentation(
                segmentationNode,
                segmentId,
                closedSurface,
            )
        )
        if (
            not success
            or closedSurface.GetNumberOfPoints() == 0
            or closedSurface.GetNumberOfCells() == 0
        ):
            raise ValueError(
                _(
                    "Selected tooth %1 has no usable closed-surface "
                    "representation."
                ).replace("%1", segmentId)
            )
        surfaceCopy = vtk.vtkPolyData()
        surfaceCopy.DeepCopy(closedSurface)
        return surfaceCopy

    def createOrUpdateDraftTemplateSupportModel(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        targetSegmentId: str,
        supportSegmentIds: list[str],
        modelNode: vtkMRMLModelNode | None = None,
    ) -> tuple[vtkMRMLModelNode, dict]:
        """Create a traceable draft model from unmodified whole-tooth surfaces."""

        selection = self.validateTemplateSupportSelection(
            segmentationNode,
            targetSegmentId,
            supportSegmentIds,
        )
        records = [selection["target"], *selection["supports"]]
        appendFilter = vtk.vtkAppendPolyData()
        sourcePointCount = 0
        sourceCellCount = 0
        for record in records:
            surfaceCopy = self._getClosedSurfaceCopy(
                segmentationNode,
                record["segmentId"],
            )
            sourcePointCount += surfaceCopy.GetNumberOfPoints()
            sourceCellCount += surfaceCopy.GetNumberOfCells()
            appendFilter.AddInputData(surfaceCopy)
        if self.getSegmentationReviewState(segmentationNode) != "Reviewed":
            raise ValueError(
                _(
                    "The segmentation review state changed while source "
                    "surfaces were being collected. Review it again first."
                )
            )
        appendFilter.Update()

        combinedSurface = vtk.vtkPolyData()
        combinedSurface.DeepCopy(appendFilter.GetOutput())
        bounds = tuple(float(value) for value in combinedSurface.GetBounds())
        if (
            combinedSurface.GetNumberOfPoints() != sourcePointCount
            or combinedSurface.GetNumberOfCells() != sourceCellCount
            or len(bounds) != 6
            or any(not math.isfinite(value) for value in bounds)
        ):
            raise RuntimeError(
                _("The draft support-anatomy model failed geometry validation.")
            )

        reusedModel = bool(
            modelNode and modelNode.IsA("vtkMRMLModelNode")
        )
        previousVisibility = bool(
            reusedModel
            and modelNode.GetDisplayNode()
            and modelNode.GetDisplayNode().GetVisibility()
        )
        if modelNode:
            if not modelNode.IsA("vtkMRMLModelNode"):
                raise ValueError(_("Select a valid draft model node."))
            if modelNode.GetAttribute("DENTOBOT.ModelRole") != "TemplateSupportDraft":
                raise ValueError(
                    _(
                        "The selected model is not a DENTOBOT draft "
                        "support-anatomy model."
                    )
                )
        else:
            modelNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
            )
        if not modelNode:
            raise RuntimeError(_("Slicer could not create the draft support model."))

        targetFdi = selection["target"].get("fdiNumber") or "Unknown"
        supportCount = len(selection["supports"])
        modelName = (
            f"[Step 5A] DENTO Template Support FDI {targetFdi} + "
            f"{supportCount} {'Teeth' if supportCount != 1 else 'Tooth'} Draft"
        )
        wasModifying = modelNode.StartModify()
        try:
            modelNode.SetName(modelName)
            modelNode.SetAndObservePolyData(combinedSurface)
            modelNode.SetAndObserveTransformNodeID(
                segmentationNode.GetTransformNodeID()
            )
            modelNode.SetNodeReferenceID(
                self.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE,
                segmentationNode.GetID(),
            )
            modelNode.SetAttribute("DENTOBOT.ModelRole", "TemplateSupportDraft")
            modelNode.SetAttribute(
                "DENTOBOT.TemplateModelSchemaVersion",
                self.TEMPLATE_MODEL_SCHEMA_VERSION,
            )
            modelNode.SetAttribute("DENTOBOT.Status", "DraftResearchOnly")
            modelNode.SetAttribute("DENTOBOT.GeometryState", "Current")
            modelNode.SetAttribute("DENTOBOT.StaleReason", None)
            modelNode.SetAttribute(
                "DENTOBOT.CoordinateConvention",
                "SegmentationLocalWithExplicitParentTransform",
            )
            modelNode.SetAttribute(
                "DENTOBOT.TargetSegmentID",
                selection["target"]["segmentId"],
            )
            modelNode.SetAttribute(
                "DENTOBOT.TargetFdiNumber",
                selection["target"].get("fdiNumber") or "",
            )
            modelNode.SetAttribute(
                "DENTOBOT.SupportSegmentIDsJson",
                self.encodeTemplateSupportSegmentIds(
                    selection["supportSegmentIds"]
                ),
            )
            modelNode.SetAttribute(
                "DENTOBOT.SupportFdiNumbersJson",
                json.dumps(
                    [
                        record.get("fdiNumber") or ""
                        for record in selection["supports"]
                    ],
                    separators=(",", ":"),
                ),
            )
            modelNode.SetAttribute(
                "DENTOBOT.SupportCount",
                str(supportCount),
            )
            modelNode.SetAttribute(
                "DENTOBOT.SourceSegmentNamesJson",
                json.dumps(
                    {
                        record["segmentId"]: record["sourceName"]
                        for record in records
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            modelNode.SetAttribute(
                "DENTOBOT.SourceReviewUpdatedUtc",
                segmentationNode.GetAttribute("DENTOBOT.ReviewUpdatedUtc") or "",
            )
            modelNode.SetAttribute(
                "DENTOBOT.UpdatedUtc",
                datetime.now(timezone.utc).isoformat(),
            )
            modelNode.SetAttribute(
                "DENTOBOT.SourcePointCount",
                str(sourcePointCount),
            )
            modelNode.SetAttribute(
                "DENTOBOT.SourceCellCount",
                str(sourceCellCount),
            )
        finally:
            modelNode.EndModify(wasModifying)

        modelNode.CreateDefaultDisplayNodes()
        displayNode = modelNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(previousVisibility if reusedModel else True)
            displayNode.SetVisibility2D(False)
            displayNode.SetVisibility3D(True)
            displayNode.SetOpacity(0.65)
        targetTrajectories = self.dentobotTrajectoriesForTarget(
            segmentationNode,
            selection["target"]["segmentId"],
        )
        if targetTrajectories:
            self.setNodeLineageColor(
                modelNode,
                self.lineageColorForTarget(
                    selection["target"]["segmentId"],
                    selection["target"].get("fdiNumber") or "",
                ),
                selection["target"]["segmentId"],
                selection["target"].get("fdiNumber") or "",
            )
        else:
            self.clearNodeLineageColor(modelNode)
            if displayNode:
                displayNode.SetColor(0.15, 0.72, 0.82)

        return modelNode, {
            "target": selection["target"],
            "supports": selection["supports"],
            "supportCount": supportCount,
            "pointCount": combinedSurface.GetNumberOfPoints(),
            "cellCount": combinedSurface.GetNumberOfCells(),
            "bounds": bounds,
        }

    @staticmethod
    def isDraftTemplateSupportModelNode(modelNode) -> bool:
        return bool(
            modelNode
            and modelNode.IsA("vtkMRMLModelNode")
            and modelNode.GetAttribute("DENTOBOT.ModelRole")
            == "TemplateSupportDraft"
        )

    def validateDraftTemplateSupportModelForDeletion(
        self,
        modelNode: vtkMRMLModelNode,
    ) -> None:
        if not self.isDraftTemplateSupportModelNode(modelNode):
            raise ValueError(
                _("Select a DENTOBOT Step 5A draft support model to delete.")
            )
        if not slicer.mrmlScene.IsNodePresent(modelNode):
            raise ValueError(_("The selected draft model is no longer in the scene."))

    def deleteDraftTemplateSupportModel(
        self,
        modelNode: vtkMRMLModelNode,
    ) -> dict:
        """Delete one Step 5A draft while preserving all source selections."""

        self.validateDraftTemplateSupportModelForDeletion(modelNode)
        parameterNode = self.getParameterNode()
        if parameterNode.draftTemplateSupportModel is modelNode:
            parameterNode.draftTemplateSupportModel = None
        return self._removeSceneNodeAndOwnedAuxiliaries(modelNode)

    @staticmethod
    def markDraftTemplateSupportModelStale(
        modelNode: vtkMRMLModelNode | None,
        reason: str,
    ) -> bool:
        """Mark only DENTOBOT draft support models stale without deleting them."""

        if (
            not modelNode
            or not modelNode.IsA("vtkMRMLModelNode")
            or modelNode.GetAttribute("DENTOBOT.ModelRole")
            != "TemplateSupportDraft"
        ):
            return False
        modelNode.SetAttribute("DENTOBOT.GeometryState", "Stale")
        modelNode.SetAttribute(
            "DENTOBOT.StaleReason",
            str(reason).strip() or "Source selection changed.",
        )
        return True

    def getDraftTemplateSupportModelSummary(
        self,
        modelNode: vtkMRMLModelNode,
    ) -> dict:
        """Return validated selection/provenance for one Step 5A model."""

        if (
            not modelNode
            or not modelNode.IsA("vtkMRMLModelNode")
            or modelNode.GetAttribute("DENTOBOT.ModelRole")
            != "TemplateSupportDraft"
        ):
            raise ValueError(_("Select a DENTOBOT draft support model."))
        polyData = modelNode.GetPolyData()
        if (
            not polyData
            or polyData.GetNumberOfPoints() == 0
            or polyData.GetNumberOfCells() == 0
        ):
            raise ValueError(_("The draft support model contains no geometry."))
        sourceNode = modelNode.GetNodeReference(
            self.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE
        )
        if not sourceNode or not sourceNode.IsA("vtkMRMLSegmentationNode"):
            raise ValueError(
                _("The draft support model has no authoritative segmentation.")
            )
        supportIds = self.decodeTemplateSupportSegmentIds(
            modelNode.GetAttribute("DENTOBOT.SupportSegmentIDsJson") or "[]"
        )
        return {
            "sourceSegmentation": sourceNode,
            "targetSegmentId": modelNode.GetAttribute(
                "DENTOBOT.TargetSegmentID"
            ) or "",
            "supportSegmentIds": supportIds,
            "supportCount": len(supportIds),
            "geometryState": modelNode.GetAttribute(
                "DENTOBOT.GeometryState"
            ) or "Unknown",
            "staleReason": modelNode.GetAttribute("DENTOBOT.StaleReason") or "",
            "pointCount": polyData.GetNumberOfPoints(),
            "cellCount": polyData.GetNumberOfCells(),
        }

    def createOrResetTemplateShellRoi(
        self,
        supportModelNode: vtkMRMLModelNode,
        roiNode: vtkMRMLMarkupsROINode | None = None,
        marginMm: float = 2.0,
    ) -> vtkMRMLMarkupsROINode:
        """Create/reset a world-RAS trim ROI around current Step 5A anatomy."""

        summary = self.getDraftTemplateSupportModelSummary(supportModelNode)
        if summary["geometryState"] != "Current":
            raise ValueError(_("Update the stale Step 5A support model first."))
        margin = float(marginMm)
        if not math.isfinite(margin) or margin < 0.0:
            raise ValueError(_("ROI margin must be a finite non-negative value."))
        worldSurface = model_polydata_in_world(supportModelNode)
        bounds = worldSurface.GetBounds()
        if len(bounds) != 6 or any(not math.isfinite(value) for value in bounds):
            raise RuntimeError(_("The Step 5A model has invalid world bounds."))

        reusedRoi = bool(
            roiNode and roiNode.IsA("vtkMRMLMarkupsROINode")
        )
        previousVisibility = bool(
            reusedRoi
            and roiNode.GetDisplayNode()
            and roiNode.GetDisplayNode().GetVisibility()
        )
        if roiNode:
            if not self.isTemplateShellRoiNode(roiNode):
                raise ValueError(
                    _(
                        "Select a DENTOBOT Step 5B shell trim ROI. Target-bounds "
                        "and unrelated ROIs cannot be adopted by Step 5B."
                    )
                )
            if roiNode.GetNodeReference(
                self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
            ) is not supportModelNode:
                raise ValueError(
                    _(
                        "The selected Step 5B ROI belongs to a different Step "
                        "5A support model. Delete it or select its source model."
                    )
                )
        else:
            roiNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsROINode",
                "[Step 5B] DENTO Research Template Shell ROI",
            )
        if not roiNode:
            raise RuntimeError(_("Slicer could not create the shell trim ROI."))

        center = [
            (float(bounds[2 * axis]) + float(bounds[2 * axis + 1])) / 2.0
            for axis in range(3)
        ]
        size = [
            float(bounds[2 * axis + 1] - bounds[2 * axis]) + 2.0 * margin
            for axis in range(3)
        ]
        roiNode.SetAndObserveTransformNodeID(None)
        roiNode.SetLocked(False)
        roiNode.SetName("[Step 5B] DENTO Research Template Shell ROI")
        roiNode.SetCenterWorld(*center)
        roiNode.SetSizeWorld(*size)
        roiNode.SetAttribute("DENTOBOT.MarkupsRole", "TemplateShellTrimROI")
        roiNode.SetAttribute(
            "DENTOBOT.TemplateGuideSchemaVersion",
            self.TEMPLATE_GUIDE_SCHEMA_VERSION,
        )
        roiNode.SetNodeReferenceID(
            self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE,
            supportModelNode.GetID(),
        )
        roiNode.CreateDefaultDisplayNodes()
        displayNode = roiNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(previousVisibility if reusedRoi else True)
        self.refreshWorkflowLineageColors()
        supportLineageColor = self.lineageColorFromNode(supportModelNode)
        if supportLineageColor:
            self.setNodeLineageColor(
                roiNode,
                supportLineageColor,
                supportModelNode.GetAttribute("DENTOBOT.TargetSegmentID") or "",
                supportModelNode.GetAttribute("DENTOBOT.TargetFdiNumber") or "",
            )
        elif displayNode:
            self.clearNodeLineageColor(roiNode)
            displayNode.SetColor(0.95, 0.65, 0.15)
            displayNode.SetSelectedColor(0.95, 0.65, 0.15)
        return roiNode

    @staticmethod
    def isTemplateShellRoiNode(roiNode) -> bool:
        return bool(
            roiNode
            and roiNode.IsA("vtkMRMLMarkupsROINode")
            and roiNode.GetAttribute("DENTOBOT.MarkupsRole")
            == "TemplateShellTrimROI"
            and not roiNode.GetAttribute("DENTOBOT.BoundsRole")
        )

    def validateTemplateShellRoiForDeletion(
        self,
        roiNode: vtkMRMLMarkupsROINode,
    ) -> None:
        if not self.isTemplateShellRoiNode(roiNode):
            raise ValueError(_("Select a DENTOBOT Step 5B shell trim ROI."))
        if not slicer.mrmlScene.IsNodePresent(roiNode):
            raise ValueError(_("The selected shell trim ROI is no longer in the scene."))

    def deleteTemplateShellRoi(
        self,
        roiNode: vtkMRMLMarkupsROINode,
    ) -> dict:
        """Delete only a DENTOBOT Step 5B ROI and its unshared auxiliaries."""

        self.validateTemplateShellRoiForDeletion(roiNode)
        parameterNode = self.getParameterNode()
        if parameterNode.templateShellRoi is roiNode:
            parameterNode.templateShellRoi = None
        return self._removeSceneNodeAndOwnedAuxiliaries(roiNode)

    @staticmethod
    def _templateGuideParameters(
        clearanceMm: float,
        thicknessMm: float,
        samplingSpacingMm: float,
        channelDiameterMm: float,
        sleeveOuterDiameterMm: float,
        sleeveInnerDiameterMm: float,
        sleeveHeightMm: float,
    ) -> dict[str, float]:
        values = {
            "clearanceMm": float(clearanceMm),
            "thicknessMm": float(thicknessMm),
            "samplingSpacingMm": float(samplingSpacingMm),
            "channelDiameterMm": float(channelDiameterMm),
            "sleeveOuterDiameterMm": float(sleeveOuterDiameterMm),
            "sleeveInnerDiameterMm": float(sleeveInnerDiameterMm),
            "sleeveHeightMm": float(sleeveHeightMm),
        }
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError(_("All Step 5B dimensions must be finite."))
        if values["clearanceMm"] < 0.0:
            raise ValueError(_("Shell clearance must be zero or greater."))
        for key in (
            "thicknessMm",
            "samplingSpacingMm",
            "channelDiameterMm",
            "sleeveOuterDiameterMm",
            "sleeveInnerDiameterMm",
            "sleeveHeightMm",
        ):
            if values[key] <= 0.0:
                raise ValueError(_("All non-clearance Step 5B dimensions must be positive."))
        if values["sleeveInnerDiameterMm"] >= values["sleeveOuterDiameterMm"]:
            raise ValueError(_("Sleeve inner diameter must be smaller than outer diameter."))
        if values["channelDiameterMm"] < values["sleeveInnerDiameterMm"]:
            raise ValueError(
                _("Shell channel diameter must be at least the sleeve inner diameter.")
            )
        return values

    def validateResearchTemplateInputs(
        self,
        supportModelNode: vtkMRMLModelNode,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        roiNode: vtkMRMLMarkupsROINode,
        parameters: dict[str, float],
    ) -> dict:
        supportSummary = self.getDraftTemplateSupportModelSummary(
            supportModelNode
        )
        if supportSummary["geometryState"] != "Current":
            raise ValueError(_("Update the stale Step 5A support model first."))
        if not self.isDentobotTrajectoryNode(trajectoryNode):
            raise ValueError(_("Select a DENTOBOT Step 4A trajectory."))
        trajectorySummary = self.getTrajectorySummary(trajectoryNode)
        if not trajectorySummary["isValid"] or trajectorySummary["definedPointCount"] != 2:
            raise ValueError(_("A complete non-zero Entry/Target trajectory is required."))
        if not trajectoryNode.GetLocked():
            raise ValueError(_("Lock the trajectory before generating Step 5B geometry."))
        trajectoryAssociation = self.getTrajectoryTargetAssociation(
            trajectoryNode
        )
        if not trajectoryAssociation:
            raise ValueError(
                _("Associate the Step 4A trajectory with the Step 5A target tooth.")
            )
        trajectorySegmentation = trajectoryAssociation["segmentationNode"]
        if (
            trajectorySegmentation.GetID()
            != supportSummary["sourceSegmentation"].GetID()
            or trajectoryAssociation["targetRecord"]["segmentId"]
            != supportSummary["targetSegmentId"]
        ):
            raise ValueError(
                _(
                    "The Step 4A trajectory and Step 5A model must belong to "
                    "the same target tooth lineage."
                )
            )
        if not self.isTemplateShellRoiNode(roiNode):
            raise ValueError(
                _(
                    "Create or select a DENTOBOT Step 5B shell trim ROI. "
                    "Step 4A target bounds cannot be used for shell generation."
                )
            )
        if roiNode.GetNodeReference(
            self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
        ) is not supportModelNode:
            raise ValueError(
                _("The shell trim ROI is not associated with the current Step 5A model.")
            )
        roiBounds = [0.0] * 6
        roiNode.GetRASBounds(roiBounds)
        if (
            any(not math.isfinite(value) for value in roiBounds)
            or any(roiBounds[2 * axis] >= roiBounds[2 * axis + 1] for axis in range(3))
        ):
            raise ValueError(_("The shell trim ROI has invalid world-RAS bounds."))
        return {
            "supportSummary": supportSummary,
            "trajectorySummary": trajectorySummary,
            "roiBoundsRas": tuple(float(value) for value in roiBounds),
            "parameters": parameters,
        }

    @staticmethod
    def _createOrReuseRoleModel(
        modelNode: vtkMRMLModelNode | None,
        role: str,
        name: str,
    ) -> vtkMRMLModelNode:
        if modelNode:
            if (
                not modelNode.IsA("vtkMRMLModelNode")
                or modelNode.GetAttribute("DENTOBOT.ModelRole") != role
            ):
                raise ValueError(_("A selected Step 5B output has the wrong role."))
        else:
            modelNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
                name,
            )
        if not modelNode:
            raise RuntimeError(_("Slicer could not create a Step 5B model."))
        modelNode.SetName(name)
        return modelNode

    def createOrUpdateResearchTemplate(
        self,
        supportModelNode: vtkMRMLModelNode,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        roiNode: vtkMRMLMarkupsROINode,
        *,
        clearanceMm: float,
        thicknessMm: float,
        samplingSpacingMm: float,
        channelDiameterMm: float,
        sleeveOuterDiameterMm: float,
        sleeveInnerDiameterMm: float,
        sleeveHeightMm: float,
        shellModelNode: vtkMRMLModelNode | None = None,
        sleeveModelNode: vtkMRMLModelNode | None = None,
    ) -> tuple[vtkMRMLModelNode, vtkMRMLModelNode, dict]:
        """Generate persistent research shell/sleeve models without trained models."""

        parameters = self._templateGuideParameters(
            clearanceMm,
            thicknessMm,
            samplingSpacingMm,
            channelDiameterMm,
            sleeveOuterDiameterMm,
            sleeveInnerDiameterMm,
            sleeveHeightMm,
        )
        inputs = self.validateResearchTemplateInputs(
            supportModelNode,
            trajectoryNode,
            roiNode,
            parameters,
        )
        trajectoryPoints = (
            inputs["trajectorySummary"]["entryRas"],
            inputs["trajectorySummary"]["targetRas"],
        )
        anatomyWorld = model_polydata_in_world(supportModelNode)
        shellPolyData, shellMetrics = create_research_shell(
            anatomyWorld,
            inputs["roiBoundsRas"],
            trajectoryPoints[0],
            trajectoryPoints[1],
            clearance_mm=parameters["clearanceMm"],
            thickness_mm=parameters["thicknessMm"],
            sampling_spacing_mm=parameters["samplingSpacingMm"],
            channel_diameter_mm=parameters["channelDiameterMm"],
            sleeve_outer_diameter_mm=parameters["sleeveOuterDiameterMm"],
            sleeve_inner_diameter_mm=parameters["sleeveInnerDiameterMm"],
            sleeve_height_mm=parameters["sleeveHeightMm"],
        )
        sleevePolyData, sleeveMetrics = create_hollow_sleeve(
            trajectoryPoints[0],
            trajectoryPoints[1],
            outer_diameter_mm=parameters["sleeveOuterDiameterMm"],
            inner_diameter_mm=parameters["sleeveInnerDiameterMm"],
            height_mm=parameters["sleeveHeightMm"],
        )

        implicitDistance = vtk.vtkImplicitPolyDataDistance()
        implicitDistance.SetInput(anatomyWorld)
        sleeveDistances = [
            float(implicitDistance.EvaluateFunction(sleevePolyData.GetPoint(index)))
            for index in range(sleevePolyData.GetNumberOfPoints())
        ]
        minimumSleeveDistance = min(sleeveDistances) if sleeveDistances else math.nan
        warnings = []
        if minimumSleeveDistance < -parameters["samplingSpacingMm"]:
            warnings.append(
                _(
                    "The sleeve surface overlaps the support anatomy; move the "
                    "Entry point to the external tooth surface before fabrication research."
                )
            )
        if shellMetrics["surfaceRegionCount"] > 2:
            warnings.append(
                _(
                    "The shell contains multiple surface regions; verify that selected "
                    "supports form one connected removable guide body."
                )
            )

        reusedShell = bool(
            shellModelNode and shellModelNode.IsA("vtkMRMLModelNode")
        )
        reusedSleeve = bool(
            sleeveModelNode and sleeveModelNode.IsA("vtkMRMLModelNode")
        )
        shellVisibility = bool(
            reusedShell
            and shellModelNode.GetDisplayNode()
            and shellModelNode.GetDisplayNode().GetVisibility()
        )
        sleeveVisibility = bool(
            reusedSleeve
            and sleeveModelNode.GetDisplayNode()
            and sleeveModelNode.GetDisplayNode().GetVisibility()
        )
        shellModelNode = self._createOrReuseRoleModel(
            shellModelNode,
            "ResearchTemplateShell",
            "[Step 5B] DENTO Research Template Shell",
        )
        sleeveModelNode = self._createOrReuseRoleModel(
            sleeveModelNode,
            "ResearchTemplateSleeve",
            "[Step 5B] DENTO Research Template Sleeve",
        )
        timestamp = datetime.now(timezone.utc).isoformat()
        parametersJson = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        warningsJson = json.dumps(warnings, separators=(",", ":"))
        trajectoryGeometryJson = json.dumps(
            {
                "entryRas": trajectoryPoints[0],
                "targetRas": trajectoryPoints[1],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        roiBoundsJson = json.dumps(
            inputs["roiBoundsRas"],
            separators=(",", ":"),
        )
        for modelNode, role, polyData, metrics in (
            (shellModelNode, "ResearchTemplateShell", shellPolyData, shellMetrics),
            (sleeveModelNode, "ResearchTemplateSleeve", sleevePolyData, sleeveMetrics),
        ):
            wasModifying = modelNode.StartModify()
            try:
                modelNode.SetAndObservePolyData(polyData)
                modelNode.SetAndObserveTransformNodeID(None)
                modelNode.SetAttribute("DENTOBOT.ModelRole", role)
                modelNode.SetAttribute(
                    "DENTOBOT.TemplateGuideSchemaVersion",
                    self.TEMPLATE_GUIDE_SCHEMA_VERSION,
                )
                modelNode.SetAttribute("DENTOBOT.Status", "ResearchOnly")
                modelNode.SetAttribute("DENTOBOT.GeometryState", "Current")
                modelNode.SetAttribute("DENTOBOT.StaleReason", None)
                modelNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
                modelNode.SetAttribute("DENTOBOT.ParametersJson", parametersJson)
                modelNode.SetAttribute(
                    "DENTOBOT.TrajectoryGeometryJson",
                    trajectoryGeometryJson,
                )
                modelNode.SetAttribute("DENTOBOT.RoiBoundsRasJson", roiBoundsJson)
                modelNode.SetAttribute(
                    "DENTOBOT.SourceModelUpdatedUtc",
                    supportModelNode.GetAttribute("DENTOBOT.UpdatedUtc") or "",
                )
                modelNode.SetAttribute(
                    "DENTOBOT.GeometryMetricsJson",
                    json.dumps(metrics, sort_keys=True, separators=(",", ":")),
                )
                modelNode.SetAttribute("DENTOBOT.ValidationWarningsJson", warningsJson)
                modelNode.SetAttribute("DENTOBOT.UpdatedUtc", timestamp)
                modelNode.SetNodeReferenceID(
                    self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE,
                    supportModelNode.GetID(),
                )
                modelNode.SetNodeReferenceID(
                    self.TEMPLATE_GUIDE_TRAJECTORY_REFERENCE_ROLE,
                    trajectoryNode.GetID(),
                )
                modelNode.SetNodeReferenceID(
                    self.TEMPLATE_GUIDE_ROI_REFERENCE_ROLE,
                    roiNode.GetID(),
                )
            finally:
                modelNode.EndModify(wasModifying)
            modelNode.CreateDefaultDisplayNodes()

        self.refreshWorkflowLineageColors()
        lineageColor = (
            self.lineageColorFromNode(supportModelNode)
            or self.lineageColorFromNode(trajectoryNode)
        )
        lineageSegmentId = (
            supportModelNode.GetAttribute("DENTOBOT.TargetSegmentID") or ""
        )
        lineageFdiNumber = (
            supportModelNode.GetAttribute("DENTOBOT.TargetFdiNumber") or ""
        )
        if lineageColor:
            for node in (
                supportModelNode,
                trajectoryNode,
                roiNode,
                shellModelNode,
                sleeveModelNode,
            ):
                self.setNodeLineageColor(
                    node,
                    lineageColor,
                    lineageSegmentId,
                    lineageFdiNumber,
                )

        shellDisplay = shellModelNode.GetDisplayNode()
        if shellDisplay:
            shellDisplay.SetVisibility(shellVisibility if reusedShell else True)
            if not lineageColor:
                shellDisplay.SetColor(0.20, 0.75, 0.85)
            shellDisplay.SetOpacity(0.72)
        sleeveDisplay = sleeveModelNode.GetDisplayNode()
        if sleeveDisplay:
            sleeveDisplay.SetVisibility(sleeveVisibility if reusedSleeve else True)
            if not lineageColor:
                sleeveDisplay.SetColor(0.80, 0.35, 0.85)
            sleeveDisplay.SetOpacity(0.90)
        return shellModelNode, sleeveModelNode, {
            "parameters": parameters,
            "shell": shellMetrics,
            "sleeve": sleeveMetrics,
            "minimumSleeveToAnatomyDistanceMm": minimumSleeveDistance,
            "warnings": warnings,
        }

    def validateTemplateFinalizationSourceShell(
        self,
        sourceShell: vtkMRMLModelNode,
    ) -> vtkMRMLModelNode:
        summary = self.getResearchTemplateModelSummary(
            sourceShell,
            "ResearchTemplateShell",
        )
        if summary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale Step 5B shell before finalization."))
        return sourceShell

    @staticmethod
    def isTemplateTrimPlaneNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsPlaneNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole")
            == "TemplateFinalizationPlane"
        )

    @staticmethod
    def isTemplateTrimCurveNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsClosedCurveNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole")
            == "TemplateFinalizationCurve"
        )

    @staticmethod
    def isFinalizedTemplateShellModelNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLModelNode")
            and node.GetAttribute("DENTOBOT.ModelRole")
            == "FinalizedTemplateShell"
        )

    def createOrResetTemplateTrimPlane(
        self,
        sourceShell: vtkMRMLModelNode,
        planeNode: vtkMRMLMarkupsPlaneNode | None = None,
    ) -> vtkMRMLMarkupsPlaneNode:
        sourceShell = self.validateTemplateFinalizationSourceShell(sourceShell)
        if planeNode:
            if not self.isTemplateTrimPlaneNode(planeNode):
                raise ValueError(_("Select a DENTOBOT Step 5C horizontal trim plane."))
            associatedSource = planeNode.GetNodeReference(
                self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE
            )
            if associatedSource is not sourceShell:
                raise ValueError(
                    _("The selected trim plane belongs to a different Step 5B shell.")
                )
        else:
            planeNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsPlaneNode",
                "[Step 5C] DENTO Horizontal Shell Trim Plane",
            )
        if not planeNode:
            raise RuntimeError(_("Slicer could not create the Step 5C trim plane."))

        bounds = [0.0] * 6
        sourceShell.GetRASBounds(bounds)
        center = tuple(
            (bounds[2 * axis] + bounds[2 * axis + 1]) / 2.0
            for axis in range(3)
        )
        planeNode.SetName("[Step 5C] DENTO Horizontal Shell Trim Plane")
        planeNode.SetPlaneType(planeNode.PlaneTypePointNormal)
        planeNode.SetOriginWorld(center)
        planeNode.SetNormalWorld((0.0, 0.0, 1.0))
        planeNode.SetSize(
            max((bounds[1] - bounds[0]) * 1.25, 1.0),
            max((bounds[3] - bounds[2]) * 1.25, 1.0),
        )
        planeNode.SetAttribute(
            "DENTOBOT.MarkupsRole",
            "TemplateFinalizationPlane",
        )
        planeNode.SetAttribute(
            "DENTOBOT.TemplateFinalizationSchemaVersion",
            self.TEMPLATE_FINALIZATION_SCHEMA_VERSION,
        )
        planeNode.SetAttribute("DENTOBOT.Status", "ResearchOnly")
        planeNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
        planeNode.SetNodeReferenceID(
            self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE,
            sourceShell.GetID(),
        )
        planeNode.CreateDefaultDisplayNodes()
        displayNode = planeNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(True)
            displayNode.SetHandlesInteractive(True)
            displayNode.SetTranslationHandleVisibility(True)
            displayNode.SetRotationHandleVisibility(False)
            displayNode.SetPropertiesLabelVisibility(False)
        lineageColor = self.lineageColorFromNode(sourceShell)
        if lineageColor:
            self.setNodeLineageColor(
                planeNode,
                lineageColor,
                sourceShell.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE) or "",
                sourceShell.GetAttribute(self.LINEAGE_TARGET_FDI_ATTRIBUTE) or "",
            )
        return planeNode

    def createTemplateTrimCurve(
        self,
        sourceShell: vtkMRMLModelNode,
    ) -> vtkMRMLMarkupsClosedCurveNode:
        sourceShell = self.validateTemplateFinalizationSourceShell(sourceShell)
        curveNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsClosedCurveNode",
            "[Step 5C] DENTO Closed Shell Margin Curve",
        )
        if not curveNode:
            raise RuntimeError(_("Slicer could not create the Step 5C margin curve."))
        curveNode.SetAttribute(
            "DENTOBOT.MarkupsRole",
            "TemplateFinalizationCurve",
        )
        curveNode.SetAttribute(
            "DENTOBOT.TemplateFinalizationSchemaVersion",
            self.TEMPLATE_FINALIZATION_SCHEMA_VERSION,
        )
        curveNode.SetAttribute("DENTOBOT.Status", "ResearchOnly")
        curveNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
        curveNode.SetNodeReferenceID(
            self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE,
            sourceShell.GetID(),
        )
        # Dynamic Modeler's Curve Cut maps this smooth closed path to the mesh.
        # Control points snap to the visible shell; using the shortest-distance
        # curve type itself can leave non-manifold seams on otherwise closed meshes.
        curveNode.SetCurveTypeToCardinalSpline()
        curveNode.CreateDefaultDisplayNodes()
        displayNode = curveNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(True)
            displayNode.SetPointLabelsVisibility(False)
            displayNode.SetPropertiesLabelVisibility(False)
            displayNode.SetSnapMode(displayNode.SnapModeToVisibleSurface)
            displayNode.SetGlyphScale(1.2)
        lineageColor = self.lineageColorFromNode(sourceShell)
        if lineageColor:
            self.setNodeLineageColor(
                curveNode,
                lineageColor,
                sourceShell.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE) or "",
                sourceShell.GetAttribute(self.LINEAGE_TARGET_FDI_ATTRIBUTE) or "",
            )
        return curveNode

    def validateTemplateFinalizationEditNode(
        self,
        sourceShell: vtkMRMLModelNode,
        editNode,
        mode: str,
        *,
        requireComplete: bool = True,
    ):
        self.validateTemplateFinalizationSourceShell(sourceShell)
        if mode not in {"PlaneCut", "CurveCut"}:
            raise ValueError(_("Select a supported Step 5C trim method."))
        if mode == "PlaneCut":
            if not self.isTemplateTrimPlaneNode(editNode):
                raise ValueError(_("Create the DENTOBOT Step 5C horizontal trim plane."))
            if requireComplete and editNode.GetNumberOfDefinedControlPoints() < 1:
                raise ValueError(_("The horizontal trim plane has no defined origin."))
        else:
            if not self.isTemplateTrimCurveNode(editNode):
                raise ValueError(_("Create the DENTOBOT Step 5C closed margin curve."))
            if requireComplete and editNode.GetNumberOfDefinedControlPoints() < 3:
                raise ValueError(
                    _("Place at least three points to define the closed margin curve.")
                )
            if (
                requireComplete
                and (
                    not editNode.GetCurvePointsWorld()
                    or editNode.GetCurvePointsWorld().GetNumberOfPoints() < 3
                )
            ):
                raise ValueError(_("The closed margin curve does not form a usable path."))
        if editNode.GetNodeReference(
            self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE
        ) is not sourceShell:
            raise ValueError(
                _("The Step 5C trim control belongs to a different raw shell.")
            )
        return editNode

    def templateFinalizationEditGeometryJson(self, editNode, mode: str) -> str:
        if mode == "PlaneCut":
            origin = editNode.GetOriginWorld()
            normal = editNode.GetNormalWorld()
            payload = {
                "normalRas": [float(value) for value in normal],
                "originRas": [float(value) for value in origin],
            }
        elif mode == "CurveCut":
            points = []
            for index in range(editNode.GetNumberOfDefinedControlPoints()):
                position = [0.0, 0.0, 0.0]
                editNode.GetNthControlPointPositionWorld(index, position)
                points.append([float(value) for value in position])
            payload = {
                "closed": bool(editNode.GetCurveClosed()),
                "controlPointsRas": points,
                "curveType": editNode.GetCurveTypeAsString(editNode.GetCurveType()),
            }
        else:
            raise ValueError(_("Select a supported Step 5C trim method."))
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _preparedFinalizationPolyData(polyData, capOpenBoundaries: bool) -> vtk.vtkPolyData:
        if not polyData or not polyData.GetNumberOfPoints() or not polyData.GetNumberOfCells():
            raise ValueError(_("The selected Dynamic Modeler cut region is empty."))
        previousPort = None
        if capOpenBoundaries:
            bounds = polyData.GetBounds()
            diagonal = math.sqrt(
                sum((bounds[2 * axis + 1] - bounds[2 * axis]) ** 2 for axis in range(3))
            )
            fillHoles = vtk.vtkFillHolesFilter()
            fillHoles.SetInputData(polyData)
            fillHoles.SetHoleSize(max(diagonal * 2.0, 1.0))
            previousPort = fillHoles.GetOutputPort()
        triangleFilter = vtk.vtkTriangleFilter()
        if previousPort:
            triangleFilter.SetInputConnection(previousPort)
        else:
            triangleFilter.SetInputData(polyData)
        cleanFilter = vtk.vtkCleanPolyData()
        cleanFilter.SetInputConnection(triangleFilter.GetOutputPort())
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputConnection(cleanFilter.GetOutputPort())
        normals.ConsistencyOn()
        normals.AutoOrientNormalsOn()
        normals.SplittingOff()
        normals.Update()
        output = vtk.vtkPolyData()
        output.DeepCopy(normals.GetOutput())
        return output

    @staticmethod
    def _finalizationDynamicOutputRoles() -> tuple[str, ...]:
        return (
            "PlaneCut.OutputNegativeModel",
            "PlaneCut.OutputPositiveModel",
            "CurveCut.OutputInside",
            "CurveCut.OutputOutside",
        )

    def _removeTemplateFinalizationProcessingNodes(
        self,
        finalShell: vtkMRMLModelNode,
    ) -> list[dict]:
        removals = []
        dynamicNode = finalShell.GetNodeReference(
            self.TEMPLATE_FINALIZATION_DYNAMIC_MODELER_REFERENCE_ROLE
        )
        if not dynamicNode:
            return removals
        outputNodes = []
        for role in self._finalizationDynamicOutputRoles():
            outputNode = dynamicNode.GetNodeReference(role)
            if outputNode and outputNode not in outputNodes:
                outputNodes.append(outputNode)
        finalShell.SetNodeReferenceID(
            self.TEMPLATE_FINALIZATION_DYNAMIC_MODELER_REFERENCE_ROLE,
            None,
        )
        if slicer.mrmlScene.IsNodePresent(dynamicNode):
            dynamicNode.SetContinuousUpdate(False)
            dynamicNodeId = dynamicNode.GetID()
            slicer.mrmlScene.RemoveNode(dynamicNode)
            removals.append(
                {"nodeId": dynamicNodeId, "nodeName": dynamicNode.GetName() or "", "auxiliaryNodeIds": []}
            )
        for outputNode in outputNodes:
            if (
                slicer.mrmlScene.IsNodePresent(outputNode)
                and outputNode.GetAttribute("DENTOBOT.ModelRole")
                == "TemplateFinalizationCutAuxiliary"
                and outputNode.GetAttribute("DENTOBOT.AuxiliaryOwnerNodeID")
                == finalShell.GetID()
            ):
                removals.append(self._removeSceneNodeAndOwnedAuxiliaries(outputNode))
        return removals

    def createOrUpdateFinalizedTemplateShell(
        self,
        sourceShell: vtkMRMLModelNode,
        planeNode: vtkMRMLMarkupsPlaneNode | None,
        curveNode: vtkMRMLMarkupsClosedCurveNode | None,
        mode: str,
        keepRegion: str,
        finalShell: vtkMRMLModelNode | None = None,
    ) -> tuple[vtkMRMLModelNode, dict]:
        sourceShell = self.validateTemplateFinalizationSourceShell(sourceShell)
        editNode = planeNode if mode == "PlaneCut" else curveNode
        self.validateTemplateFinalizationEditNode(sourceShell, editNode, mode)
        allowedRegions = (
            {"Negative", "Positive"}
            if mode == "PlaneCut"
            else {"Inside", "Outside"}
        )
        if keepRegion not in allowedRegions:
            raise ValueError(_("Select which Step 5C cut region to keep."))
        if not getattr(slicer.modules, "dynamicmodeler", None):
            raise RuntimeError(_("Slicer's Dynamic Modeler module is unavailable."))

        createdFinalShell = finalShell is None
        if finalShell and not self.isFinalizedTemplateShellModelNode(finalShell):
            raise ValueError(_("Select the DENTOBOT Step 5C finalized shell."))
        if not finalShell:
            finalShell = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
                "[Step 5C] DENTO Finalized Research Template Shell",
            )
        if not finalShell:
            raise RuntimeError(_("Slicer could not create the Step 5C finalized shell."))
        if not createdFinalShell:
            self._removeTemplateFinalizationProcessingNodes(finalShell)

        dynamicNode = None
        outputNodes = []
        try:
            dynamicNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLDynamicModelerNode",
                f"[Step 5C] DENTO {mode} Dynamic Modeler",
            )
            if not dynamicNode:
                raise RuntimeError(_("Slicer could not create a Dynamic Modeler node."))
            dynamicNode.SetAttribute(
                "DENTOBOT.DynamicModelerRole",
                "TemplateFinalizationCut",
            )
            dynamicNode.SetAttribute("DENTOBOT.AuxiliaryOwnerNodeID", finalShell.GetID())
            dynamicNode.SetContinuousUpdate(False)

            if mode == "PlaneCut":
                outputRoleByRegion = {
                    "Negative": "PlaneCut.OutputNegativeModel",
                    "Positive": "PlaneCut.OutputPositiveModel",
                }
                dynamicNode.SetToolName("Plane cut")
                dynamicNode.SetNodeReferenceID("PlaneCut.InputModel", sourceShell.GetID())
                dynamicNode.SetNodeReferenceID("PlaneCut.InputPlane", editNode.GetID())
                dynamicNode.SetAttribute("CapSurface", "1")
                dynamicNode.SetAttribute("OperationType", "Union")
            else:
                outputRoleByRegion = {
                    "Inside": "CurveCut.OutputInside",
                    "Outside": "CurveCut.OutputOutside",
                }
                dynamicNode.SetToolName("Curve cut")
                dynamicNode.SetNodeReferenceID("CurveCut.InputModel", sourceShell.GetID())
                dynamicNode.SetNodeReferenceID("CurveCut.InputCurve", editNode.GetID())
                dynamicNode.SetAttribute("CurveCut.StraightCut", "1")

            for region, outputRole in outputRoleByRegion.items():
                outputNode = slicer.mrmlScene.AddNewNodeByClass(
                    "vtkMRMLModelNode",
                    f"[Step 5C] DENTO {mode} {region} (auxiliary)",
                )
                if not outputNode:
                    raise RuntimeError(_("Slicer could not create a cut output node."))
                outputNode.SetAttribute(
                    "DENTOBOT.ModelRole",
                    "TemplateFinalizationCutAuxiliary",
                )
                outputNode.SetAttribute("DENTOBOT.AuxiliaryOwnerNodeID", finalShell.GetID())
                outputNode.CreateDefaultDisplayNodes()
                outputNode.GetDisplayNode().SetVisibility(False)
                outputNodes.append(outputNode)
                dynamicNode.SetNodeReferenceID(outputRole, outputNode.GetID())

            slicer.modules.dynamicmodeler.logic().RunDynamicModelerTool(dynamicNode)
            keptOutput = dynamicNode.GetNodeReference(outputRoleByRegion[keepRegion])
            finalizedPolyData = self._preparedFinalizationPolyData(
                keptOutput.GetPolyData() if keptOutput else None,
                capOpenBoundaries=mode == "CurveCut",
            )
            topology = surface_topology(finalizedPolyData)
            if topology["boundaryOrNonManifoldEdgeCount"] != 0:
                raise ValueError(
                    _(
                        "The Step 5C result is not watertight after capping; "
                        "adjust the trim control before export."
                    )
                )

            timestamp = datetime.now(timezone.utc).isoformat()
            finalShell.SetName("[Step 5C] DENTO Finalized Research Template Shell")
            finalShell.SetAndObservePolyData(finalizedPolyData)
            finalShell.SetAndObserveTransformNodeID(None)
            finalShell.SetAttribute("DENTOBOT.ModelRole", "FinalizedTemplateShell")
            finalShell.SetAttribute(
                "DENTOBOT.TemplateFinalizationSchemaVersion",
                self.TEMPLATE_FINALIZATION_SCHEMA_VERSION,
            )
            finalShell.SetAttribute("DENTOBOT.Status", "ResearchOnly")
            finalShell.SetAttribute("DENTOBOT.GeometryState", "Current")
            finalShell.SetAttribute("DENTOBOT.StaleReason", None)
            finalShell.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
            finalShell.SetAttribute("DENTOBOT.FinalizationMethod", mode)
            finalShell.SetAttribute("DENTOBOT.FinalizationKeepRegion", keepRegion)
            finalShell.SetAttribute(
                "DENTOBOT.FinalizationEditGeometryJson",
                self.templateFinalizationEditGeometryJson(editNode, mode),
            )
            finalShell.SetAttribute(
                "DENTOBOT.SourceShellUpdatedUtc",
                sourceShell.GetAttribute("DENTOBOT.UpdatedUtc") or "",
            )
            finalShell.SetAttribute(
                "DENTOBOT.GeometryMetricsJson",
                json.dumps(topology, sort_keys=True, separators=(",", ":")),
            )
            finalShell.SetAttribute("DENTOBOT.UpdatedUtc", timestamp)
            finalShell.SetNodeReferenceID(
                self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE,
                sourceShell.GetID(),
            )
            finalShell.SetNodeReferenceID(
                self.TEMPLATE_FINALIZATION_EDIT_NODE_REFERENCE_ROLE,
                editNode.GetID(),
            )
            finalShell.SetNodeReferenceID(
                self.TEMPLATE_FINALIZATION_DYNAMIC_MODELER_REFERENCE_ROLE,
                dynamicNode.GetID(),
            )
            finalShell.CreateDefaultDisplayNodes()
            lineageColor = self.lineageColorFromNode(sourceShell)
            if lineageColor:
                self.setNodeLineageColor(
                    finalShell,
                    lineageColor,
                    sourceShell.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE) or "",
                    sourceShell.GetAttribute(self.LINEAGE_TARGET_FDI_ATTRIBUTE) or "",
                )
            finalShell.GetDisplayNode().SetOpacity(0.82)
            finalShell.GetDisplayNode().SetVisibility(True)
            self.refreshWorkflowLineageColors()
            self.refreshWorkflowNodeStepTags()
            return finalShell, {
                "method": mode,
                "keepRegion": keepRegion,
                "topology": topology,
                "dynamicModelerNode": dynamicNode,
            }
        except Exception:
            if dynamicNode and slicer.mrmlScene.IsNodePresent(dynamicNode):
                slicer.mrmlScene.RemoveNode(dynamicNode)
            for outputNode in outputNodes:
                if slicer.mrmlScene.IsNodePresent(outputNode):
                    self._removeSceneNodeAndOwnedAuxiliaries(outputNode)
            if createdFinalShell and slicer.mrmlScene.IsNodePresent(finalShell):
                self._removeSceneNodeAndOwnedAuxiliaries(finalShell)
            elif finalShell:
                self.markFinalizedTemplateShellStale(
                    finalShell,
                    _("The latest Step 5C trim failed."),
                )
            raise

    def getFinalizedTemplateShellSummary(
        self,
        finalShell: vtkMRMLModelNode,
    ) -> dict:
        if not self.isFinalizedTemplateShellModelNode(finalShell):
            raise ValueError(_("Select the DENTOBOT Step 5C finalized shell."))
        polyData = finalShell.GetPolyData()
        if not polyData or not polyData.GetNumberOfPoints() or not polyData.GetNumberOfCells():
            raise ValueError(_("The Step 5C finalized shell contains no geometry."))
        return {
            "geometryState": finalShell.GetAttribute("DENTOBOT.GeometryState") or "Unknown",
            "staleReason": finalShell.GetAttribute("DENTOBOT.StaleReason") or "",
            "method": finalShell.GetAttribute("DENTOBOT.FinalizationMethod") or "",
            "keepRegion": finalShell.GetAttribute("DENTOBOT.FinalizationKeepRegion") or "",
            "editGeometryJson": finalShell.GetAttribute(
                "DENTOBOT.FinalizationEditGeometryJson"
            ) or "",
            "sourceShellUpdatedUtc": finalShell.GetAttribute(
                "DENTOBOT.SourceShellUpdatedUtc"
            ) or "",
            "sourceShell": finalShell.GetNodeReference(
                self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE
            ),
            "editNode": finalShell.GetNodeReference(
                self.TEMPLATE_FINALIZATION_EDIT_NODE_REFERENCE_ROLE
            ),
            "dynamicModelerNode": finalShell.GetNodeReference(
                self.TEMPLATE_FINALIZATION_DYNAMIC_MODELER_REFERENCE_ROLE
            ),
            **surface_topology(polyData),
        }

    @staticmethod
    def markFinalizedTemplateShellStale(
        finalShell: vtkMRMLModelNode | None,
        reason: str,
    ) -> bool:
        if not DENTOWorkflowLogic.isFinalizedTemplateShellModelNode(finalShell):
            return False
        finalShell.SetAttribute("DENTOBOT.GeometryState", "Stale")
        finalShell.SetAttribute(
            "DENTOBOT.StaleReason",
            str(reason).strip() or "Step 5C inputs changed.",
        )
        return True

    def deleteTemplateFinalization(
        self,
        planeNode: vtkMRMLMarkupsPlaneNode | None,
        curveNode: vtkMRMLMarkupsClosedCurveNode | None,
        finalShell: vtkMRMLModelNode | None,
    ) -> list[dict]:
        nodes = [node for node in (planeNode, curveNode, finalShell) if node]
        if not nodes:
            raise ValueError(_("There is no DENTOBOT Step 5C edit to delete."))
        if planeNode and not self.isTemplateTrimPlaneNode(planeNode):
            raise ValueError(_("The selected plane is not owned by DENTOBOT Step 5C."))
        if curveNode and not self.isTemplateTrimCurveNode(curveNode):
            raise ValueError(_("The selected curve is not owned by DENTOBOT Step 5C."))
        if finalShell and not self.isFinalizedTemplateShellModelNode(finalShell):
            raise ValueError(_("The selected shell is not owned by DENTOBOT Step 5C."))

        parameterNode = self.getParameterNode()
        parameterNode.templateTrimPlane = None
        parameterNode.templateTrimCurve = None
        parameterNode.finalizedTemplateShellModel = None
        removals = []
        if finalShell:
            removals.extend(self._removeTemplateFinalizationProcessingNodes(finalShell))
            if slicer.mrmlScene.IsNodePresent(finalShell):
                removals.append(self._removeSceneNodeAndOwnedAuxiliaries(finalShell))
        for editNode in (planeNode, curveNode):
            if editNode and slicer.mrmlScene.IsNodePresent(editNode):
                removals.append(self._removeSceneNodeAndOwnedAuxiliaries(editNode))
        return removals

    @staticmethod
    def startHorizontalPlanePlacement(planeNode: vtkMRMLMarkupsPlaneNode) -> None:
        if not DENTOWorkflowLogic.isTemplateTrimPlaneNode(planeNode):
            raise ValueError(_("Select a DENTOBOT Step 5C horizontal trim plane."))
        planeNode.RemoveAllControlPoints()
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if not selectionNode:
            raise RuntimeError(_("Slicer's selection node is unavailable."))
        selectionNode.SetReferenceActivePlaceNodeClassName(
            "vtkMRMLMarkupsPlaneNode"
        )
        selectionNode.SetActivePlaceNodeID(planeNode.GetID())
        slicer.modules.markups.logic().StartPlaceMode(0)
        selectionNode.SetActivePlaceNodeClassName(
            "vtkMRMLMarkupsPlaneNode"
        )
        selectionNode.SetActivePlaceNodeID(planeNode.GetID())

    @staticmethod
    def startClosedCurvePlacement(curveNode: vtkMRMLMarkupsClosedCurveNode) -> None:
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if not selectionNode:
            raise RuntimeError(_("Slicer's selection node is unavailable."))
        selectionNode.SetReferenceActivePlaceNodeClassName(
            "vtkMRMLMarkupsClosedCurveNode"
        )
        selectionNode.SetActivePlaceNodeID(curveNode.GetID())
        slicer.modules.markups.logic().StartPlaceMode(1)
        selectionNode.SetActivePlaceNodeClassName(
            "vtkMRMLMarkupsClosedCurveNode"
        )
        selectionNode.SetActivePlaceNodeID(curveNode.GetID())

    @staticmethod
    def isResearchTemplateModelNode(modelNode, role: str | None = None) -> bool:
        if not modelNode or not modelNode.IsA("vtkMRMLModelNode"):
            return False
        actualRole = modelNode.GetAttribute("DENTOBOT.ModelRole")
        validRoles = {"ResearchTemplateShell", "ResearchTemplateSleeve"}
        return actualRole == role if role else actualRole in validRoles

    def getResearchTemplateModelSummary(
        self,
        modelNode: vtkMRMLModelNode,
        expectedRole: str,
    ) -> dict:
        if not self.isResearchTemplateModelNode(modelNode, expectedRole):
            raise ValueError(_("Select the matching DENTOBOT Step 5B output model."))
        polyData = modelNode.GetPolyData()
        if not polyData or not polyData.GetNumberOfPoints() or not polyData.GetNumberOfCells():
            raise ValueError(_("A Step 5B output model contains no geometry."))
        topology = surface_topology(polyData)
        return {
            "role": expectedRole,
            "geometryState": modelNode.GetAttribute("DENTOBOT.GeometryState") or "Unknown",
            "staleReason": modelNode.GetAttribute("DENTOBOT.StaleReason") or "",
            "sourceModel": modelNode.GetNodeReference(
                self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
            ),
            "trajectory": modelNode.GetNodeReference(
                self.TEMPLATE_GUIDE_TRAJECTORY_REFERENCE_ROLE
            ),
            "roi": modelNode.GetNodeReference(self.TEMPLATE_GUIDE_ROI_REFERENCE_ROLE),
            "parametersJson": modelNode.GetAttribute("DENTOBOT.ParametersJson") or "{}",
            "trajectoryGeometryJson": modelNode.GetAttribute(
                "DENTOBOT.TrajectoryGeometryJson"
            ) or "{}",
            "roiBoundsRasJson": modelNode.GetAttribute(
                "DENTOBOT.RoiBoundsRasJson"
            ) or "[]",
            "sourceModelUpdatedUtc": modelNode.GetAttribute(
                "DENTOBOT.SourceModelUpdatedUtc"
            ) or "",
            "warnings": json.loads(
                modelNode.GetAttribute("DENTOBOT.ValidationWarningsJson") or "[]"
            ),
            **topology,
        }

    @staticmethod
    def markResearchTemplateModelsStale(
        shellModelNode: vtkMRMLModelNode | None,
        sleeveModelNode: vtkMRMLModelNode | None,
        reason: str,
    ) -> bool:
        changed = False
        for modelNode in (shellModelNode, sleeveModelNode):
            if not DENTOWorkflowLogic.isResearchTemplateModelNode(modelNode):
                continue
            modelNode.SetAttribute("DENTOBOT.GeometryState", "Stale")
            modelNode.SetAttribute(
                "DENTOBOT.StaleReason",
                str(reason).strip() or "Step 5B inputs changed.",
            )
            changed = True
        return changed

    def deleteResearchTemplateModels(
        self,
        shellModelNode: vtkMRMLModelNode | None,
        sleeveModelNode: vtkMRMLModelNode | None,
    ) -> list[dict]:
        nodes = [node for node in (shellModelNode, sleeveModelNode) if node]
        if not nodes:
            raise ValueError(_("There is no DENTOBOT Step 5B output to delete."))
        for node in nodes:
            if not self.isResearchTemplateModelNode(node):
                raise ValueError(_("A selected output is not owned by DENTOBOT Step 5B."))
        parameterNode = self.getParameterNode()
        if any(
            parameterNode.researchTemplateShellModel is node
            for node in nodes
        ):
            parameterNode.researchTemplateShellModel = None
        if any(
            parameterNode.researchTemplateSleeveModel is node
            for node in nodes
        ):
            parameterNode.researchTemplateSleeveModel = None
        return [self._removeSceneNodeAndOwnedAuxiliaries(node) for node in nodes]

    def exportResearchTemplateStls(
        self,
        directory: str | Path,
        shellModelNode: vtkMRMLModelNode,
        sleeveModelNode: vtkMRMLModelNode,
        *,
        overwrite: bool = False,
    ) -> dict[str, Path]:
        shellSummary = self.getFinalizedTemplateShellSummary(shellModelNode)
        sleeveSummary = self.getResearchTemplateModelSummary(
            sleeveModelNode,
            "ResearchTemplateSleeve",
        )
        if shellSummary["geometryState"] != "Current" or sleeveSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate stale Step 5B/5C outputs before STL export."))
        sourceShell = shellSummary["sourceShell"]
        sourceSummary = self.getResearchTemplateModelSummary(
            sourceShell,
            "ResearchTemplateShell",
        )
        if (
            sourceSummary["geometryState"] != "Current"
            or shellSummary["sourceShellUpdatedUtc"]
            != (sourceShell.GetAttribute("DENTOBOT.UpdatedUtc") or "")
        ):
            raise ValueError(_("Reapply Step 5C after the Step 5B source shell changes."))
        if shellSummary["boundaryOrNonManifoldEdgeCount"] != 0:
            raise ValueError(_("The Step 5C finalized shell is not watertight."))
        outputDirectory = Path(directory)
        if not outputDirectory.is_dir():
            raise ValueError(_("Select an existing local STL output directory."))
        paths = {
            "shell": outputDirectory / "DENTO_Research_Template_Shell.stl",
            "sleeve": outputDirectory / "DENTO_Research_Template_Sleeve.stl",
        }
        existing = [path.name for path in paths.values() if path.exists()]
        if existing and not overwrite:
            raise FileExistsError(
                _("STL output already exists: %1").replace("%1", ", ".join(existing))
            )
        return {
            "shell": write_stl_atomic(shellModelNode.GetPolyData(), paths["shell"]),
            "sleeve": write_stl_atomic(sleeveModelNode.GetPolyData(), paths["sleeve"]),
        }

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
        self.enforceTrajectoryControlPointInvariant(trajectoryNode)

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
            self.test_DENTOWorkflowDraftTemplateSupportModelLogic()
            self.test_DENTOWorkflowTemplateFinalizationDynamicModeler()
            self.test_DENTOWorkflowResearchTemplateGeometry()
            self.test_DENTOWorkflowSafeDeletionAndPersistence()
            self.test_DENTOWorkflowTrajectorySelectionRestoresTargetWidget()
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
        parameterNode.useLauncherBackendConfiguration = False
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
        self.assertFalse(parameterNode.useLauncherBackendConfiguration)
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
        localBackendPython = "/opt/dentobot-test-env/bin/python"
        launcherArtifactRoot = "/workspace/data/dentobot-runs"
        launcherEnvironment = {
            logic.BACKEND_PYTHON_ENVIRONMENT_VARIABLE: localBackendPython,
            logic.RUN_ARTIFACT_ROOT_ENVIRONMENT_VARIABLE: launcherArtifactRoot,
        }

        self.assertEqual(
            logic.launcherBackendConfiguration(launcherEnvironment),
            (localBackendPython, launcherArtifactRoot),
        )
        self.assertEqual(
            logic.resolveBackendConfiguration(
                "local",
                "ignored-distribution",
                "/manual/python",
                "/manual/runs",
                "cpu",
                True,
                launcherEnvironment,
            ),
            (
                "local",
                "ignored-distribution",
                localBackendPython,
                launcherArtifactRoot,
                "cpu",
            ),
        )
        self.assertEqual(
            logic.resolveBackendConfiguration(
                "local",
                "",
                "/manual/python",
                "/manual/runs",
                "cpu",
                False,
                launcherEnvironment,
            ),
            ("local", "", "/manual/python", "/manual/runs", "cpu"),
        )
        self.assertEqual(
            logic.resolveBackendConfiguration(
                "local",
                "",
                "/stale/python",
                "/stale/runs",
                "cpu",
                True,
                {},
            ),
            ("local", "", "", "", "cpu"),
        )

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
            localBackendPython,
            executionMode="local",
            device="cpu",
        )
        self.assertEqual(
            localHealthCommand[0],
            localBackendPython,
        )
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
            localBackendPython,
            Path("/workspace/data/run-3/input.nii"),
            Path("/workspace/data/run-3/teeth-segmentation.nii"),
            Path("/workspace/data/run-3/result.json"),
            "run-3",
            executionMode="local",
            device="cpu",
        )
        self.assertEqual(
            localTeethCommand[0],
            localBackendPython,
        )
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
        self.assertTrue(targetBoundsRoi.GetName().startswith("[Step 4A]"))
        targetBoundsRoi.GetDisplayNode().SetVisibility(False)
        reusedTargetBoundsRoi, _reusedBounds = (
            logic.createOrUpdateTargetBoundsRoi(
                segmentationNode,
                "tooth-16",
                targetBoundsRoi,
            )
        )
        self.assertIs(reusedTargetBoundsRoi, targetBoundsRoi)
        self.assertFalse(targetBoundsRoi.GetDisplayNode().GetVisibility())

        legacyGuideSource = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Legacy Cross-Role Guide Source",
        )
        targetBoundsRoi.SetAttribute(
            "DENTOBOT.MarkupsRole",
            "TemplateShellTrimROI",
        )
        targetBoundsRoi.SetAttribute(
            "DENTOBOT.TemplateGuideSchemaVersion",
            logic.TEMPLATE_GUIDE_SCHEMA_VERSION,
        )
        targetBoundsRoi.SetNodeReferenceID(
            logic.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE,
            legacyGuideSource.GetID(),
        )
        roiCountBeforeRepair = (
            slicer.mrmlScene.GetNodesByClass("vtkMRMLMarkupsROINode")
            .GetNumberOfItems()
        )
        repairedTargetBoundsRoi, repairedBounds = (
            logic.createOrUpdateTargetBoundsRoi(
                segmentationNode,
                "tooth-16",
                targetBoundsRoi,
            )
        )
        self.assertIs(repairedTargetBoundsRoi, targetBoundsRoi)
        self.assertEqual(repairedBounds, targetBounds)
        self.assertEqual(
            slicer.mrmlScene.GetNodesByClass("vtkMRMLMarkupsROINode")
            .GetNumberOfItems(),
            roiCountBeforeRepair,
        )
        self.assertEqual(
            targetBoundsRoi.GetAttribute("DENTOBOT.BoundsRole"),
            "TargetToothAABB",
        )
        self.assertIsNone(
            targetBoundsRoi.GetAttribute("DENTOBOT.MarkupsRole")
        )
        self.assertIsNone(
            targetBoundsRoi.GetAttribute(
                "DENTOBOT.TemplateGuideSchemaVersion"
            )
        )
        self.assertIsNone(
            targetBoundsRoi.GetNodeReference(
                logic.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
            )
        )
        self.assertTrue(targetBoundsRoi.GetLocked())

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
        trajectoryNode.SetNodeReferenceID(
            logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
            targetBoundsRoi.GetID(),
        )
        logic.refreshWorkflowLineageColors()
        lineage16 = logic.lineageColorFromNode(trajectoryNode)
        self.assertIsNotNone(lineage16)
        self.assertEqual(
            logic.lineageColorFromNode(targetBoundsRoi),
            lineage16,
        )
        self.assertEqual(
            trajectoryNode.GetAttribute(
                logic.LINEAGE_TARGET_SEGMENT_ATTRIBUTE
            ),
            "tooth-16",
        )

        secondTrajectory16 = logic.createTrajectoryNode(
            "Second FDI 16 trajectory"
        )
        logic.configureTrajectoryTarget(
            secondTrajectory16,
            segmentationNode,
            "tooth-16",
        )
        secondTrajectory16.SetNodeReferenceID(
            logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
            targetBoundsRoi.GetID(),
        )
        self.assertEqual(
            logic.lineageColorFromNode(secondTrajectory16),
            lineage16,
        )

        tooth15Segment = slicer.vtkSegment()
        tooth15Segment.SetName("upper_right_second_premolar_fdi15")
        tooth15Cube = vtk.vtkCubeSource()
        tooth15Cube.SetBounds(4.0, 6.0, -2.0, 2.0, -3.0, 3.0)
        tooth15Cube.Update()
        tooth15Segment.AddRepresentation(
            slicer.vtkSegmentationConverter
            .GetSegmentationClosedSurfaceRepresentationName(),
            tooth15Cube.GetOutput(),
        )
        segmentationNode.GetSegmentation().AddSegment(
            tooth15Segment,
            "tooth-15",
        )
        targetBoundsRoi15, _bounds15 = logic.createOrUpdateTargetBoundsRoi(
            segmentationNode,
            "tooth-15",
            targetBoundsRoi,
        )
        self.assertIsNot(targetBoundsRoi15, targetBoundsRoi)
        self.assertEqual(
            targetBoundsRoi.GetAttribute("DENTOBOT.TargetSegmentID"),
            "tooth-16",
        )
        self.assertIsNone(logic.lineageColorFromNode(targetBoundsRoi15))
        trajectory15 = logic.createTrajectoryNode("FDI 15 trajectory")
        logic.configureTrajectoryTarget(
            trajectory15,
            segmentationNode,
            "tooth-15",
        )
        trajectory15.SetNodeReferenceID(
            logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
            targetBoundsRoi15.GetID(),
        )
        logic.refreshWorkflowLineageColors()
        lineage15 = logic.lineageColorFromNode(trajectory15)
        self.assertIsNotNone(lineage15)
        self.assertNotEqual(lineage15, lineage16)
        self.assertEqual(
            logic.lineageColorFromNode(targetBoundsRoi15),
            lineage15,
        )

        trajectoryNode.SetName("User-renamed trajectory")
        persistedAssociation = logic.getTrajectoryTargetAssociation(
            trajectoryNode
        )
        self.assertEqual(
            persistedAssociation["targetRecord"]["segmentId"],
            "tooth-16",
        )
        self.assertIs(
            persistedAssociation["segmentationNode"],
            segmentationNode,
        )
        self.assertIs(
            persistedAssociation["targetBoundsRoi"],
            targetBoundsRoi,
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
        trajectoryNode.SetNodeReferenceID(
            logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
            targetBoundsRoi.GetID(),
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

        importedLine = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsLineNode",
            "Imported over-defined line",
        )
        importedLine.AddControlPoint(vtk.vtkVector3d(0.0, 0.0, 0.0))
        importedLine.AddControlPoint(vtk.vtkVector3d(0.1, 0.0, 0.0))
        rejectedPointIndex = importedLine.AddControlPoint(
            vtk.vtkVector3d(0.2, 0.0, 0.0)
        )
        logic.enforceTrajectoryControlPointInvariant(importedLine)
        self.assertEqual(importedLine.GetMaximumNumberOfControlPoints(), 2)
        self.assertEqual(importedLine.GetNumberOfDefinedControlPoints(), 2)
        self.assertLess(rejectedPointIndex, 0)
        self.assertEqual(importedLine.GetNthControlPointLabel(0), "Entry")
        self.assertEqual(importedLine.GetNthControlPointLabel(1), "Target")

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

        legacyEmpty = logic.createTrajectoryNode(
            "DENTO Trajectory FDI 16"
        )
        legacyComplete = logic.createTrajectoryNode(
            "DENTO Trajectory FDI 16"
        )
        for legacyTrajectory in (legacyEmpty, legacyComplete):
            logic.configureTrajectoryTarget(
                legacyTrajectory,
                segmentationNode,
                "tooth-16",
            )
        legacyComplete.AddControlPoint(vtk.vtkVector3d(-0.5, 0.0, 0.0))
        legacyComplete.AddControlPoint(vtk.vtkVector3d(0.5, 0.0, 0.0))
        renamedNodeIds = logic.refreshManagedTrajectoryNames()
        self.assertIn(legacyEmpty.GetID(), renamedNodeIds)
        self.assertIn(legacyComplete.GetID(), renamedNodeIds)
        self.assertNotEqual(legacyEmpty.GetName(), legacyComplete.GetName())
        self.assertIn("Empty", legacyEmpty.GetName())
        self.assertIn("Complete", legacyComplete.GetName())
        self.assertIn("Trajectory 1", legacyEmpty.GetName())
        self.assertIn("Trajectory 2", legacyComplete.GetName())
        self.assertTrue(legacyEmpty.GetName().startswith("[Step 4A]"))
        self.assertTrue(legacyComplete.GetName().startswith("[Step 4A]"))

        scenePath = Path(slicer.app.temporaryPath) / (
            f"dentobot-trajectory-association-{uuid.uuid4().hex}.mrb"
        )
        try:
            self.assertTrue(slicer.util.saveScene(str(scenePath)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(scenePath)))
        finally:
            scenePath.unlink(missing_ok=True)
        reloadedLogic = DENTOWorkflowLogic()
        reloadedParameterNode = reloadedLogic.getParameterNode()
        reloadedAssociation = reloadedLogic.getTrajectoryTargetAssociation(
            reloadedParameterNode.trajectoryLine
        )
        self.assertEqual(
            reloadedAssociation["targetRecord"]["segmentId"],
            "tooth-16",
        )
        self.assertIs(
            reloadedAssociation["segmentationNode"],
            reloadedParameterNode.teethSegmentation,
        )
        self.assertIs(
            reloadedAssociation["targetBoundsRoi"],
            reloadedParameterNode.targetToothBoundsRoi,
        )
        self.assertFalse(
            reloadedParameterNode.targetToothBoundsRoi
            .GetDisplayNode()
            .GetVisibility()
        )
        self.assertEqual(
            reloadedLogic.lineageColorFromNode(
                reloadedParameterNode.trajectoryLine
            ),
            reloadedLogic.lineageColorFromNode(
                reloadedParameterNode.targetToothBoundsRoi
            ),
        )

        self.delayDisplay(
            "DENTOWorkflow target association, naming, and trajectory logic tests passed"
        )

    def test_DENTOWorkflowTrajectorySelectionRestoresTargetWidget(self) -> None:
        slicer.mrmlScene.Clear(0)
        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()
        logic = widget.logic

        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "WidgetTrajectoryRestoreSegmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        for segmentId, segmentName, centerX in (
            ("tooth-14", "upper_right_first_premolar_fdi14", 0.0),
            ("tooth-15", "upper_right_second_premolar_fdi15", 5.0),
        ):
            cube = vtk.vtkCubeSource()
            cube.SetBounds(
                centerX - 1.0,
                centerX + 1.0,
                -1.0,
                1.0,
                -1.0,
                1.0,
            )
            cube.Update()
            segment = slicer.vtkSegment()
            segment.SetName(segmentName)
            segment.AddRepresentation(
                slicer.vtkSegmentationConverter
                .GetSegmentationClosedSurfaceRepresentationName(),
                cube.GetOutput(),
            )
            segmentationNode.GetSegmentation().AddSegment(segment, segmentId)

        roi14, _bounds14 = logic.createOrUpdateTargetBoundsRoi(
            segmentationNode,
            "tooth-14",
        )
        roi15, _bounds15 = logic.createOrUpdateTargetBoundsRoi(
            segmentationNode,
            "tooth-15",
        )
        self.assertIsNone(widget._parameterNode.templateShellRoi)
        self.assertIsNone(widget.ui.templateShellRoiSelector.currentNode())
        trajectory14 = logic.createTrajectoryNode(
            "DENTO Trajectory FDI 14"
        )
        logic.configureTrajectoryTarget(
            trajectory14,
            segmentationNode,
            "tooth-14",
        )
        trajectory14.SetNodeReferenceID(
            logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
            roi14.GetID(),
        )
        trajectory14.AddControlPoint(vtk.vtkVector3d(-0.5, 0.0, 0.0))
        trajectory14.AddControlPoint(vtk.vtkVector3d(0.5, 0.0, 0.0))
        trajectory15 = logic.createTrajectoryNode(
            "DENTO Trajectory FDI 15"
        )
        logic.configureTrajectoryTarget(
            trajectory15,
            segmentationNode,
            "tooth-15",
        )
        trajectory15.SetNodeReferenceID(
            logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
            roi15.GetID(),
        )
        trajectory15.AddControlPoint(vtk.vtkVector3d(4.5, 0.0, 0.0))
        trajectory15.AddControlPoint(vtk.vtkVector3d(5.5, 0.0, 0.0))
        logic.refreshWorkflowLineageColors()
        self.assertNotEqual(
            logic.lineageColorFromNode(trajectory14),
            logic.lineageColorFromNode(trajectory15),
        )

        parameterNode = widget._parameterNode
        widget._restoringTrajectoryAssociation = True
        wasModifying = parameterNode.StartModify()
        try:
            parameterNode.teethSegmentation = segmentationNode
            parameterNode.targetToothSegmentId = ""
            parameterNode.targetToothBoundsRoi = None
            parameterNode.trajectoryLine = trajectory14
        finally:
            parameterNode.EndModify(wasModifying)
            widget._restoringTrajectoryAssociation = False
        widget._updateFromParameterNode()
        self.assertEqual(parameterNode.targetToothSegmentId, "tooth-14")
        self.assertIs(parameterNode.targetToothBoundsRoi, roi14)
        self.assertIsNone(parameterNode.templateShellRoi)
        self.assertIsNone(widget.ui.templateShellRoiSelector.currentNode())
        self.assertEqual(
            str(
                widget.ui.targetToothComboBox.itemData(
                    widget.ui.targetToothComboBox.currentIndex
                )
            ),
            "tooth-14",
        )
        self.assertAlmostEqual(
            trajectory14.GetDisplayNode().GetOpacity(),
            1.0,
        )
        self.assertAlmostEqual(
            trajectory15.GetDisplayNode().GetOpacity(),
            0.38,
        )
        self.assertTrue(
            trajectory14.GetDisplayNode().GetPointLabelsVisibility()
        )
        self.assertFalse(
            trajectory15.GetDisplayNode().GetPointLabelsVisibility()
        )
        selectorComboBox = next(
            child
            for child in widget.ui.trajectorySelector.children()
            if hasattr(child, "setItemData")
            and hasattr(child, "count")
        )
        decoratedTrajectoryIds = set()
        for selectorIndex in range(selectorComboBox.count):
            selectorNode = widget.ui.trajectorySelector.nodeFromIndex(
                selectorIndex
            )
            if selectorNode in (trajectory14, trajectory15):
                decoration = selectorComboBox.itemData(
                    selectorIndex,
                    qt.Qt.DecorationRole,
                )
                self.assertTrue(decoration.isValid())
                decoratedTrajectoryIds.add(selectorNode.GetID())
        self.assertEqual(
            decoratedTrajectoryIds,
            {trajectory14.GetID(), trajectory15.GetID()},
        )

        tooth15Index = next(
            index
            for index in range(widget.ui.targetToothComboBox.count)
            if str(widget.ui.targetToothComboBox.itemData(index))
            == "tooth-15"
        )
        widget.ui.targetToothComboBox.setCurrentIndex(tooth15Index)
        self.assertEqual(parameterNode.targetToothSegmentId, "tooth-15")
        self.assertIsNone(parameterNode.trajectoryLine)
        self.assertIs(parameterNode.targetToothBoundsRoi, roi15)
        self.assertEqual(
            trajectory14.GetAttribute("DENTOBOT.TargetSegmentID"),
            "tooth-14",
        )
        self.assertIs(
            trajectory14.GetNodeReference(
                logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE
            ),
            roi14,
        )
        self.assertTrue(trajectory14.GetDisplayNode().GetVisibility())
        self.assertTrue(trajectory15.GetDisplayNode().GetVisibility())
        self.assertAlmostEqual(
            trajectory14.GetDisplayNode().GetOpacity(),
            0.38,
        )
        self.assertAlmostEqual(
            trajectory15.GetDisplayNode().GetOpacity(),
            1.0,
        )
        self.assertFalse(roi14.GetDisplayNode().GetVisibility())
        self.assertTrue(roi15.GetDisplayNode().GetVisibility())

        widget._restoringTrajectoryAssociation = True
        wasModifying = parameterNode.StartModify()
        try:
            parameterNode.teethSegmentation = segmentationNode
            parameterNode.targetToothSegmentId = "tooth-15"
            parameterNode.targetToothBoundsRoi = roi15
            parameterNode.trajectoryLine = None
        finally:
            parameterNode.EndModify(wasModifying)
            widget._restoringTrajectoryAssociation = False
        widget._updateFromParameterNode()

        widget.onTrajectorySelectionChanged(trajectory14)
        self.assertIs(parameterNode.teethSegmentation, segmentationNode)
        self.assertEqual(parameterNode.targetToothSegmentId, "tooth-14")
        self.assertIs(parameterNode.targetToothBoundsRoi, roi14)
        self.assertIs(parameterNode.trajectoryLine, trajectory14)
        self.assertEqual(
            str(
                widget.ui.targetToothComboBox.itemData(
                    widget.ui.targetToothComboBox.currentIndex
                )
            ),
            "tooth-14",
        )
        self.assertTrue(
            segmentationNode.GetDisplayNode().GetSegmentVisibility(
                "tooth-14"
            )
        )
        # Target restoration must not undo the user's/step switch's ROI hide.
        self.assertFalse(roi14.GetDisplayNode().GetVisibility())
        self.assertFalse(roi15.GetDisplayNode().GetVisibility())
        self.assertNotEqual(widget.ui.trajectoryLengthValueLabel.text, "--")

        parameterNode.templateShellRoi = roi14
        widget._updateFromParameterNode()
        self.assertIsNone(parameterNode.templateShellRoi)
        self.assertIsNone(widget.ui.templateShellRoiSelector.currentNode())
        self.assertTrue(slicer.mrmlScene.IsNodePresent(roi14))
        self.assertEqual(
            roi14.GetAttribute("DENTOBOT.BoundsRole"),
            "TargetToothAABB",
        )
        self.assertIsNone(roi14.GetAttribute("DENTOBOT.MarkupsRole"))

        supportModel = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Visibility Support",
        )
        supportModel.SetAttribute("DENTOBOT.ModelRole", "TemplateSupportDraft")
        supportModel.SetAttribute("DENTOBOT.TargetSegmentID", "tooth-14")
        supportModel.SetAttribute("DENTOBOT.TargetFdiNumber", "14")
        supportModel.SetNodeReferenceID(
            logic.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE,
            segmentationNode.GetID(),
        )
        shellRoi = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsROINode",
            "Visibility Shell ROI",
        )
        shellRoi.SetAttribute("DENTOBOT.MarkupsRole", "TemplateShellTrimROI")
        shellRoi.SetNodeReferenceID(
            logic.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE,
            supportModel.GetID(),
        )
        shellModel = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Visibility Shell",
        )
        shellModel.SetAttribute("DENTOBOT.ModelRole", "ResearchTemplateShell")
        shellModel.SetNodeReferenceID(
            logic.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE,
            supportModel.GetID(),
        )
        sleeveModel = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Visibility Sleeve",
        )
        sleeveModel.SetAttribute("DENTOBOT.ModelRole", "ResearchTemplateSleeve")
        sleeveModel.SetNodeReferenceID(
            logic.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE,
            supportModel.GetID(),
        )
        for node in (supportModel, shellRoi, shellModel, sleeveModel):
            node.CreateDefaultDisplayNodes()
            node.GetDisplayNode().SetVisibility(True)
        logic.refreshWorkflowLineageColors()
        lineage14 = logic.lineageColorFromNode(trajectory14)
        for descendantNode in (
            supportModel,
            shellRoi,
            shellModel,
            sleeveModel,
        ):
            self.assertEqual(
                logic.lineageColorFromNode(descendantNode),
                lineage14,
            )
        wasModifying = parameterNode.StartModify()
        try:
            parameterNode.draftTemplateSupportModel = supportModel
            parameterNode.templateShellRoi = shellRoi
            parameterNode.researchTemplateShellModel = shellModel
            parameterNode.researchTemplateSleeveModel = sleeveModel
        finally:
            parameterNode.EndModify(wasModifying)
        widget._updateTemplateModeling()
        widget._updateTemplateGuide()
        slicer.app.processEvents()
        self.assertIn("FDI 14", widget.ui.templateModelingLineageLabel.text)
        self.assertIn("FDI 14", widget.ui.templateGuideLineageLabel.text)
        self.assertIn(
            "border-left",
            widget.ui.templateModelingLineageLabel.styleSheet,
        )
        self.assertIn(
            "border-left",
            widget.ui.templateGuideLineageLabel.styleSheet,
        )
        for selector, expectedNode in (
            (widget.ui.draftTemplateSupportModelSelector, supportModel),
            (widget.ui.templateShellRoiSelector, shellRoi),
            (widget.ui.researchTemplateShellModelSelector, shellModel),
            (widget.ui.researchTemplateSleeveModelSelector, sleeveModel),
        ):
            selectorComboBox = widget._nodeSelectorComboBox(selector)
            decorated = False
            for selectorIndex in range(selectorComboBox.count):
                if selector.nodeFromIndex(selectorIndex) is not expectedNode:
                    continue
                decoration = selectorComboBox.itemData(
                    selectorIndex,
                    qt.Qt.DecorationRole,
                )
                decorated = decoration.isValid()
                break
            self.assertTrue(decorated)
        widget._updateTemplateGuideVisibilityControls()
        visibilityEntries = widget._templateGuideVisibilityEntries()
        self.assertEqual(len(visibilityEntries), 6)
        self.assertTrue(all(checkBox.enabled for checkBox, _node in visibilityEntries))
        self.assertTrue(
            all(
                "border-left" in checkBox.styleSheet
                for checkBox, _node in visibilityEntries
            )
        )
        widget._updatingTemplateGuideVisibilityUI = True
        try:
            for checkBox, _node in visibilityEntries:
                checkBox.checked = False
        finally:
            widget._updatingTemplateGuideVisibilityUI = False
        widget.onTemplateGuideVisibilityChanged()
        self.assertTrue(
            all(
                not node.GetDisplayNode().GetVisibility()
                for _checkBox, node in visibilityEntries
            )
        )
        widget.ui.shellRoiVisibilityCheckBox.checked = True
        self.assertTrue(shellRoi.GetDisplayNode().GetVisibility())
        self.assertFalse(roi14.GetDisplayNode().GetVisibility())

        # Legacy scenes may retain a target ID and owned nodes while their
        # parameter-node selections are empty. Show lineage without guessing
        # which of several matching trajectories should become selected.
        widget._restoringTrajectoryAssociation = True
        wasModifying = parameterNode.StartModify()
        try:
            parameterNode.teethSegmentation = None
            parameterNode.targetToothSegmentId = "tooth-14"
            parameterNode.targetToothBoundsRoi = None
            parameterNode.trajectoryLine = None
            parameterNode.draftTemplateSupportModel = None
            parameterNode.templateShellRoi = None
            parameterNode.researchTemplateShellModel = None
            parameterNode.researchTemplateSleeveModel = None
        finally:
            parameterNode.EndModify(wasModifying)
            widget._restoringTrajectoryAssociation = False
        widget._updateTemplateModeling()
        widget._updateTemplateGuide()
        self.assertIn("FDI 14", widget.ui.templateModelingLineageLabel.text)
        self.assertIn("FDI 14", widget.ui.templateGuideLineageLabel.text)

        self.delayDisplay(
            "DENTOWorkflow widget trajectory restoration and visibility test passed"
        )

    def test_DENTOWorkflowDraftTemplateSupportModelLogic(self) -> None:
        logic = DENTOWorkflowLogic()
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "TemplateSupportSegmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        transformNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLinearTransformNode",
            "TemplateSupportParentTransform",
        )
        segmentationNode.SetAndObserveTransformNodeID(transformNode.GetID())

        toothFixtures = [
            ("tooth-16", "upper_right_first_molar_fdi16"),
            ("tooth-11", "upper_right_central_incisor_fdi11"),
            ("tooth-12", "upper_right_lateral_incisor_fdi12"),
            ("tooth-13", "upper_right_canine_fdi13"),
            ("tooth-14", "upper_right_first_premolar_fdi14"),
            ("tooth-15", "upper_right_second_premolar_fdi15"),
            ("tooth-17", "upper_right_second_molar_fdi17"),
            ("tooth-18", "upper_right_third_molar_fdi18"),
            ("tooth-21", "upper_left_central_incisor_fdi21"),
            ("tooth-22", "upper_left_lateral_incisor_fdi22"),
            ("tooth-23", "upper_left_canine_fdi23"),
        ]
        sourceGeometryCounts = {}
        for toothIndex, (segmentId, segmentName) in enumerate(toothFixtures):
            segment = slicer.vtkSegment()
            segment.SetName(segmentName)
            cube = vtk.vtkCubeSource()
            centerX = float(toothIndex * 3)
            cube.SetBounds(
                centerX - 1.0,
                centerX + 1.0,
                -1.0,
                1.0,
                -2.0,
                2.0,
            )
            cube.Update()
            surfaceCopy = vtk.vtkPolyData()
            surfaceCopy.DeepCopy(cube.GetOutput())
            sourceGeometryCounts[segmentId] = (
                surfaceCopy.GetNumberOfPoints(),
                surfaceCopy.GetNumberOfCells(),
            )
            segment.AddRepresentation(
                slicer.vtkSegmentationConverter
                .GetSegmentationClosedSurfaceRepresentationName(),
                surfaceCopy,
            )
            segmentationNode.GetSegmentation().AddSegment(segment, segmentId)

        pulpSegment = slicer.vtkSegment()
        pulpSegment.SetName("upper_right_first_molar_pulp_fdi116")
        pulpCube = vtk.vtkCubeSource()
        pulpCube.SetBounds(-0.25, 0.25, -0.25, 0.25, -1.0, 1.0)
        pulpCube.Update()
        pulpSegment.AddRepresentation(
            slicer.vtkSegmentationConverter
            .GetSegmentationClosedSurfaceRepresentationName(),
            pulpCube.GetOutput(),
        )
        segmentationNode.GetSegmentation().AddSegment(
            pulpSegment,
            "pulp-16",
        )

        supportIds = [segmentId for segmentId, _name in toothFixtures[1:]]
        self.assertEqual(len(supportIds), 10)
        encodedSupportIds = logic.encodeTemplateSupportSegmentIds(
            supportIds
        )
        self.assertEqual(
            logic.decodeTemplateSupportSegmentIds(encodedSupportIds),
            supportIds,
        )
        with self.assertRaisesRegex(ValueError, "more than once"):
            logic.encodeTemplateSupportSegmentIds(
                [supportIds[0], supportIds[0]]
            )
        with self.assertRaisesRegex(ValueError, "Reviewed"):
            logic.createOrUpdateDraftTemplateSupportModel(
                segmentationNode,
                "tooth-16",
                supportIds,
            )

        logic.setSegmentationReviewState(
            segmentationNode,
            "Reviewed",
            updatedUtc="2026-08-03T12:00:00+00:00",
        )
        with self.assertRaisesRegex(ValueError, "at least one"):
            logic.validateTemplateSupportSelection(
                segmentationNode,
                "tooth-16",
                [],
            )
        with self.assertRaisesRegex(ValueError, "cannot also"):
            logic.validateTemplateSupportSelection(
                segmentationNode,
                "tooth-16",
                ["tooth-16"],
            )
        with self.assertRaisesRegex(ValueError, "whole-tooth"):
            logic.validateTemplateSupportSelection(
                segmentationNode,
                "tooth-16",
                ["pulp-16"],
            )
        with self.assertRaisesRegex(ValueError, "more than once"):
            logic.validateTemplateSupportSelection(
                segmentationNode,
                "tooth-16",
                [supportIds[0], supportIds[0]],
            )

        modelNode, details = logic.createOrUpdateDraftTemplateSupportModel(
            segmentationNode,
            "tooth-16",
            supportIds,
        )
        expectedPointCount = sum(
            pointCount
            for pointCount, _cellCount in sourceGeometryCounts.values()
        )
        expectedCellCount = sum(
            cellCount
            for _pointCount, cellCount in sourceGeometryCounts.values()
        )
        self.assertTrue(modelNode.IsA("vtkMRMLModelNode"))
        self.assertEqual(details["supportCount"], 10)
        self.assertEqual(details["pointCount"], expectedPointCount)
        self.assertEqual(details["cellCount"], expectedCellCount)
        self.assertEqual(
            modelNode.GetTransformNodeID(),
            transformNode.GetID(),
        )
        self.assertEqual(
            modelNode.GetNodeReference(
                logic.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE
            ),
            segmentationNode,
        )
        self.assertEqual(
            modelNode.GetAttribute("DENTOBOT.ModelRole"),
            "TemplateSupportDraft",
        )
        self.assertEqual(
            modelNode.GetAttribute("DENTOBOT.GeometryState"),
            "Current",
        )
        self.assertEqual(
            modelNode.GetAttribute("DENTOBOT.SupportCount"),
            "10",
        )
        self.assertEqual(
            logic.decodeTemplateSupportSegmentIds(
                modelNode.GetAttribute("DENTOBOT.SupportSegmentIDsJson")
            ),
            supportIds,
        )
        self.assertEqual(
            json.loads(
                modelNode.GetAttribute("DENTOBOT.SupportFdiNumbersJson")
            ),
            [segmentId.split("-")[1] for segmentId in supportIds],
        )
        self.assertIn("10 Teeth Draft", modelNode.GetName())
        self.assertTrue(modelNode.GetName().startswith("[Step 5A]"))
        self.assertTrue(all(math.isfinite(value) for value in details["bounds"]))

        for segmentId, expectedCounts in sourceGeometryCounts.items():
            sourceSurface = logic._getClosedSurfaceCopy(
                segmentationNode,
                segmentId,
            )
            self.assertEqual(
                (
                    sourceSurface.GetNumberOfPoints(),
                    sourceSurface.GetNumberOfCells(),
                ),
                expectedCounts,
            )

        summary = logic.getDraftTemplateSupportModelSummary(modelNode)
        self.assertEqual(summary["targetSegmentId"], "tooth-16")
        self.assertEqual(summary["supportSegmentIds"], supportIds)
        self.assertEqual(summary["supportCount"], 10)
        self.assertEqual(summary["geometryState"], "Current")

        parameterNode = logic.getParameterNode()
        parameterNode.teethSegmentation = segmentationNode
        parameterNode.targetToothSegmentId = "tooth-16"
        parameterNode.templateSupportToothSegmentIdsJson = encodedSupportIds
        parameterNode.draftTemplateSupportModel = modelNode
        self.assertEqual(
            logic.decodeTemplateSupportSegmentIds(
                parameterNode.templateSupportToothSegmentIdsJson
            ),
            supportIds,
        )
        self.assertEqual(
            parameterNode.draftTemplateSupportModel.GetID(),
            modelNode.GetID(),
        )

        modelNode.GetDisplayNode().SetVisibility(False)
        updatedModelNode, updatedDetails = (
            logic.createOrUpdateDraftTemplateSupportModel(
                segmentationNode,
                "tooth-16",
                supportIds[:2],
                modelNode,
            )
        )
        self.assertEqual(updatedModelNode.GetID(), modelNode.GetID())
        self.assertEqual(updatedDetails["supportCount"], 2)
        self.assertFalse(modelNode.GetDisplayNode().GetVisibility())
        self.assertEqual(
            modelNode.GetAttribute("DENTOBOT.SupportCount"),
            "2",
        )
        self.assertIn("2 Teeth Draft", modelNode.GetName())
        self.assertTrue(
            logic.markDraftTemplateSupportModelStale(
                modelNode,
                "Manual selection changed.",
            )
        )
        staleSummary = logic.getDraftTemplateSupportModelSummary(modelNode)
        self.assertEqual(staleSummary["geometryState"], "Stale")
        self.assertEqual(
            staleSummary["staleReason"],
            "Manual selection changed.",
        )

        logic.setSegmentationReviewState(
            segmentationNode,
            "Needs Correction",
            updatedUtc="2026-08-03T12:05:00+00:00",
        )
        with self.assertRaisesRegex(ValueError, "Reviewed"):
            logic.createOrUpdateDraftTemplateSupportModel(
                segmentationNode,
                "tooth-16",
                supportIds[:2],
                modelNode,
            )

        self.delayDisplay(
            "DENTOWorkflow Step 5A multi-support model logic tests passed"
        )

    def test_DENTOWorkflowTemplateFinalizationDynamicModeler(self) -> None:
        slicer.mrmlScene.Clear(0)
        logic = DENTOWorkflowLogic()
        sphere = vtk.vtkSphereSource()
        sphere.SetRadius(10.0)
        sphere.SetThetaResolution(64)
        sphere.SetPhiResolution(48)
        sphere.Update()
        sourceShell = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Synthetic current Step 5B shell",
        )
        sourceShell.SetAndObservePolyData(sphere.GetOutput())
        sourceShell.SetAttribute("DENTOBOT.ModelRole", "ResearchTemplateShell")
        sourceShell.SetAttribute("DENTOBOT.GeometryState", "Current")
        sourceShell.SetAttribute("DENTOBOT.UpdatedUtc", "2026-08-07T12:00:00+00:00")
        sourcePointCount = sourceShell.GetPolyData().GetNumberOfPoints()
        sourceCellCount = sourceShell.GetPolyData().GetNumberOfCells()

        planeNode = logic.createOrResetTemplateTrimPlane(sourceShell)
        planeNode.SetOriginWorld((0.0, 0.0, 2.0))
        self.assertTrue(logic.isTemplateTrimPlaneNode(planeNode))
        self.assertIs(
            planeNode.GetNodeReference(
                logic.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE
            ),
            sourceShell,
        )
        finalShell, planeResult = logic.createOrUpdateFinalizedTemplateShell(
            sourceShell,
            planeNode,
            None,
            "PlaneCut",
            "Negative",
        )
        self.assertEqual(planeResult["topology"]["boundaryOrNonManifoldEdgeCount"], 0)
        negativeTriangleCount = planeResult["topology"]["triangleCount"]
        finalShell, flippedPlaneResult = logic.createOrUpdateFinalizedTemplateShell(
            sourceShell,
            planeNode,
            None,
            "PlaneCut",
            "Positive",
            finalShell,
        )
        self.assertEqual(
            flippedPlaneResult["topology"]["boundaryOrNonManifoldEdgeCount"],
            0,
        )
        self.assertNotEqual(
            negativeTriangleCount,
            flippedPlaneResult["topology"]["triangleCount"],
        )

        curveNode = logic.createTemplateTrimCurve(sourceShell)
        curveRadius = math.sqrt(96.0)
        for index in range(16):
            angle = 2.0 * math.pi * index / 16.0
            curveNode.AddControlPointWorld(
                vtk.vtkVector3d(
                    curveRadius * math.cos(angle),
                    curveRadius * math.sin(angle),
                    2.0,
                )
            )
        finalShell, curveResult = logic.createOrUpdateFinalizedTemplateShell(
            sourceShell,
            planeNode,
            curveNode,
            "CurveCut",
            "Outside",
            finalShell,
        )
        self.assertEqual(curveResult["topology"]["boundaryOrNonManifoldEdgeCount"], 0)
        finalSummary = logic.getFinalizedTemplateShellSummary(finalShell)
        self.assertEqual(finalSummary["method"], "CurveCut")
        self.assertEqual(finalSummary["keepRegion"], "Outside")
        self.assertIs(finalSummary["sourceShell"], sourceShell)
        self.assertIs(finalSummary["editNode"], curveNode)
        self.assertIsNotNone(finalSummary["dynamicModelerNode"])
        self.assertEqual(sourceShell.GetPolyData().GetNumberOfPoints(), sourcePointCount)
        self.assertEqual(sourceShell.GetPolyData().GetNumberOfCells(), sourceCellCount)

        parameterNode = logic.getParameterNode()
        parameterNode.templateTrimPlane = planeNode
        parameterNode.templateTrimCurve = curveNode
        parameterNode.finalizedTemplateShellModel = finalShell
        finalId = finalShell.GetID()
        dynamicId = finalSummary["dynamicModelerNode"].GetID()
        removals = logic.deleteTemplateFinalization(
            planeNode,
            curveNode,
            finalShell,
        )
        self.assertGreaterEqual(len(removals), 6)
        self.assertIsNone(slicer.mrmlScene.GetNodeByID(finalId))
        self.assertIsNone(slicer.mrmlScene.GetNodeByID(dynamicId))
        self.assertTrue(slicer.mrmlScene.IsNodePresent(sourceShell))
        self.delayDisplay(
            "DENTOWorkflow Step 5C plane/curve Dynamic Modeler and clean deletion tests passed"
        )

    def test_DENTOWorkflowResearchTemplateGeometry(self) -> None:
        slicer.mrmlScene.Clear(0)
        logic = DENTOWorkflowLogic()
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "ResearchTemplateSegmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        for segmentId, segmentName, centerX in (
            ("tooth-16", "upper_right_first_molar_fdi16", 0.0),
            ("tooth-15", "upper_right_second_premolar_fdi15", 6.5),
        ):
            sphere = vtk.vtkSphereSource()
            sphere.SetCenter(centerX, 0.0, 0.0)
            sphere.SetRadius(4.0)
            sphere.SetThetaResolution(32)
            sphere.SetPhiResolution(24)
            sphere.Update()
            segment = slicer.vtkSegment()
            segment.SetName(segmentName)
            segment.AddRepresentation(
                slicer.vtkSegmentationConverter
                .GetSegmentationClosedSurfaceRepresentationName(),
                sphere.GetOutput(),
            )
            segmentationNode.GetSegmentation().AddSegment(segment, segmentId)

        logic.setSegmentationReviewState(
            segmentationNode,
            "Reviewed",
            updatedUtc="2026-08-06T12:00:00+00:00",
        )
        supportModel, _details = logic.createOrUpdateDraftTemplateSupportModel(
            segmentationNode,
            "tooth-16",
            ["tooth-15"],
        )
        trajectoryNode = logic.createTrajectoryNode("Research Template Trajectory")
        logic.configureTrajectoryTarget(
            trajectoryNode,
            segmentationNode,
            "tooth-16",
        )
        trajectoryNode.AddControlPoint(vtk.vtkVector3d(0.0, 0.0, 4.0))
        trajectoryNode.AddControlPoint(vtk.vtkVector3d(0.0, 0.0, 0.0))
        trajectoryNode.SetLocked(True)
        targetBoundsRoi, _targetBounds = logic.createOrUpdateTargetBoundsRoi(
            segmentationNode,
            "tooth-16",
        )
        lineageColor = logic.lineageColorFromNode(trajectoryNode)
        self.assertIsNotNone(lineageColor)
        for lineageNode in (
            targetBoundsRoi,
            trajectoryNode,
            supportModel,
        ):
            self.assertEqual(
                logic.lineageColorFromNode(lineageNode),
                lineageColor,
            )
        roiCountBeforeRejectedReset = (
            slicer.mrmlScene.GetNodesByClass("vtkMRMLMarkupsROINode")
            .GetNumberOfItems()
        )
        with self.assertRaisesRegex(ValueError, "Step 5B shell trim ROI"):
            logic.createOrResetTemplateShellRoi(
                supportModel,
                targetBoundsRoi,
            )
        self.assertEqual(
            slicer.mrmlScene.GetNodesByClass("vtkMRMLMarkupsROINode")
            .GetNumberOfItems(),
            roiCountBeforeRejectedReset,
        )
        self.assertEqual(
            targetBoundsRoi.GetAttribute("DENTOBOT.BoundsRole"),
            "TargetToothAABB",
        )
        self.assertIsNone(
            targetBoundsRoi.GetAttribute("DENTOBOT.MarkupsRole")
        )
        with self.assertRaisesRegex(ValueError, "Step 5B shell trim ROI"):
            logic.deleteTemplateShellRoi(targetBoundsRoi)
        self.assertTrue(slicer.mrmlScene.IsNodePresent(targetBoundsRoi))

        templateParameters = logic._templateGuideParameters(
            0.5,
            1.5,
            0.5,
            2.0,
            4.0,
            2.0,
            4.0,
        )
        with self.assertRaisesRegex(ValueError, "Step 4A target bounds"):
            logic.validateResearchTemplateInputs(
                supportModel,
                trajectoryNode,
                targetBoundsRoi,
                templateParameters,
            )

        roiNode = logic.createOrResetTemplateShellRoi(supportModel)
        unrelatedSupportModel = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Unrelated Step 5A Model",
        )
        roiNode.SetNodeReferenceID(
            logic.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE,
            unrelatedSupportModel.GetID(),
        )
        with self.assertRaisesRegex(ValueError, "different Step 5A"):
            logic.createOrResetTemplateShellRoi(supportModel, roiNode)
        with self.assertRaisesRegex(ValueError, "not associated"):
            logic.validateResearchTemplateInputs(
                supportModel,
                trajectoryNode,
                roiNode,
                templateParameters,
            )
        roiNode.SetNodeReferenceID(
            logic.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE,
            supportModel.GetID(),
        )
        wrongTargetTrajectory = logic.createTrajectoryNode(
            "Wrong target lineage"
        )
        logic.configureTrajectoryTarget(
            wrongTargetTrajectory,
            segmentationNode,
            "tooth-15",
        )
        wrongTargetTrajectory.AddControlPoint(
            vtk.vtkVector3d(6.5, 0.0, 4.0)
        )
        wrongTargetTrajectory.AddControlPoint(
            vtk.vtkVector3d(6.5, 0.0, 0.0)
        )
        wrongTargetTrajectory.SetLocked(True)
        with self.assertRaisesRegex(ValueError, "same target tooth lineage"):
            logic.validateResearchTemplateInputs(
                supportModel,
                wrongTargetTrajectory,
                roiNode,
                templateParameters,
            )

        shellModel, sleeveModel, result = logic.createOrUpdateResearchTemplate(
            supportModel,
            trajectoryNode,
            roiNode,
            clearanceMm=0.5,
            thicknessMm=1.5,
            samplingSpacingMm=0.5,
            channelDiameterMm=2.0,
            sleeveOuterDiameterMm=4.0,
            sleeveInnerDiameterMm=2.0,
            sleeveHeightMm=4.0,
        )
        self.assertTrue(
            logic.isResearchTemplateModelNode(
                shellModel,
                "ResearchTemplateShell",
            )
        )
        self.assertTrue(
            logic.isResearchTemplateModelNode(
                sleeveModel,
                "ResearchTemplateSleeve",
            )
        )
        self.assertEqual(
            result["shell"]["boundaryOrNonManifoldEdgeCount"],
            0,
        )
        self.assertEqual(
            result["sleeve"]["boundaryOrNonManifoldEdgeCount"],
            0,
        )
        self.assertGreater(result["shell"]["triangleCount"], 0)
        self.assertGreater(result["sleeve"]["triangleCount"], 0)
        logic.refreshWorkflowNodeStepTags()
        self.assertTrue(supportModel.GetName().startswith("[Step 5A]"))
        self.assertTrue(trajectoryNode.GetName().startswith("[Step 4A]"))
        self.assertTrue(roiNode.GetName().startswith("[Step 5B]"))
        self.assertTrue(shellModel.GetName().startswith("[Step 5B]"))
        self.assertTrue(sleeveModel.GetName().startswith("[Step 5B]"))
        for lineageNode in (
            targetBoundsRoi,
            trajectoryNode,
            supportModel,
            roiNode,
            shellModel,
            sleeveModel,
        ):
            self.assertEqual(
                logic.lineageColorFromNode(lineageNode),
                lineageColor,
            )
            displayColor = lineageNode.GetDisplayNode().GetColor()
            for componentIndex in range(3):
                self.assertAlmostEqual(
                    displayColor[componentIndex],
                    lineageColor[componentIndex],
                    places=5,
                )

        roiNode.GetDisplayNode().SetVisibility(False)
        shellModel.GetDisplayNode().SetVisibility(False)
        sleeveModel.GetDisplayNode().SetVisibility(False)

        # Match the live workflow: all parent inputs are already selected
        # before an update creates or replaces the derived Step 5B outputs.
        parameterNode = logic.getParameterNode()
        parameterNode.teethSegmentation = segmentationNode
        parameterNode.targetToothSegmentId = "tooth-16"
        parameterNode.templateSupportToothSegmentIdsJson = '["tooth-15"]'
        parameterNode.templateShellClearanceMm = 0.5
        parameterNode.templateShellThicknessMm = 1.5
        parameterNode.templateSamplingSpacingMm = 0.5
        parameterNode.templateChannelDiameterMm = 2.0
        parameterNode.templateSleeveOuterDiameterMm = 4.0
        parameterNode.templateSleeveInnerDiameterMm = 2.0
        parameterNode.templateSleeveHeightMm = 4.0
        parameterNode.draftTemplateSupportModel = supportModel
        parameterNode.trajectoryLine = trajectoryNode
        parameterNode.templateShellRoi = roiNode
        self.assertIs(
            logic.createOrResetTemplateShellRoi(supportModel, roiNode),
            roiNode,
        )
        shellModel, sleeveModel, _updatedResult = (
            logic.createOrUpdateResearchTemplate(
                supportModel,
                trajectoryNode,
                roiNode,
                clearanceMm=0.5,
                thicknessMm=1.5,
                samplingSpacingMm=0.5,
                channelDiameterMm=2.0,
                sleeveOuterDiameterMm=4.0,
                sleeveInnerDiameterMm=2.0,
                sleeveHeightMm=4.0,
                shellModelNode=shellModel,
                sleeveModelNode=sleeveModel,
            )
        )
        self.assertFalse(roiNode.GetDisplayNode().GetVisibility())
        self.assertFalse(shellModel.GetDisplayNode().GetVisibility())
        self.assertFalse(sleeveModel.GetDisplayNode().GetVisibility())

        parameterNode.researchTemplateShellModel = shellModel
        parameterNode.researchTemplateSleeveModel = sleeveModel
        trimPlane = logic.createOrResetTemplateTrimPlane(shellModel)
        finalizedShell, finalizationResult = (
            logic.createOrUpdateFinalizedTemplateShell(
                shellModel,
                trimPlane,
                None,
                "PlaneCut",
                "Negative",
            )
        )
        self.assertEqual(
            finalizationResult["topology"]["boundaryOrNonManifoldEdgeCount"],
            0,
        )
        parameterNode.templateFinalizationMode = "PlaneCut"
        parameterNode.templateFinalizationKeepRegion = "Negative"
        parameterNode.templateTrimPlane = trimPlane
        parameterNode.finalizedTemplateShellModel = finalizedShell

        exportDirectory = Path(slicer.app.temporaryPath) / (
            f"dentobot-step5c-export-{uuid.uuid4().hex}"
        )
        exportDirectory.mkdir(parents=True)
        try:
            with self.assertRaisesRegex(ValueError, "Step 5C finalized"):
                logic.exportResearchTemplateStls(
                    exportDirectory,
                    shellModel,
                    sleeveModel,
                )
            exported = logic.exportResearchTemplateStls(
                exportDirectory,
                finalizedShell,
                sleeveModel,
            )
            for path in exported.values():
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 84)
        finally:
            for path in exportDirectory.glob("*"):
                path.unlink()
            exportDirectory.rmdir()

        scenePath = Path(slicer.app.temporaryPath) / (
            f"dentobot-step5b-persistence-{uuid.uuid4().hex}.mrb"
        )
        try:
            self.assertTrue(slicer.util.saveScene(str(scenePath)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(scenePath)))
        finally:
            scenePath.unlink(missing_ok=True)

        reloadedLogic = DENTOWorkflowLogic()
        reloadedParameterNode = reloadedLogic.getParameterNode()
        reloadedShell = reloadedParameterNode.researchTemplateShellModel
        reloadedSleeve = reloadedParameterNode.researchTemplateSleeveModel
        reloadedTrimPlane = reloadedParameterNode.templateTrimPlane
        reloadedFinalizedShell = (
            reloadedParameterNode.finalizedTemplateShellModel
        )
        reloadedLineageColor = reloadedLogic.lineageColorFromNode(
            reloadedParameterNode.trajectoryLine
        )
        for lineageNode in (
            reloadedParameterNode.draftTemplateSupportModel,
            reloadedParameterNode.templateShellRoi,
            reloadedShell,
            reloadedSleeve,
            reloadedTrimPlane,
            reloadedFinalizedShell,
        ):
            self.assertEqual(
                reloadedLogic.lineageColorFromNode(lineageNode),
                reloadedLineageColor,
            )
        self.assertFalse(
            reloadedParameterNode.templateShellRoi
            .GetDisplayNode()
            .GetVisibility()
        )
        self.assertFalse(reloadedShell.GetDisplayNode().GetVisibility())
        self.assertFalse(reloadedSleeve.GetDisplayNode().GetVisibility())
        self.assertTrue(reloadedLogic.isTemplateTrimPlaneNode(reloadedTrimPlane))
        self.assertEqual(
            reloadedLogic.getFinalizedTemplateShellSummary(
                reloadedFinalizedShell
            )["geometryState"],
            "Current",
        )
        self.assertEqual(
            reloadedLogic.getResearchTemplateModelSummary(
                reloadedShell,
                "ResearchTemplateShell",
            )["geometryState"],
            "Current",
        )
        self.assertEqual(
            reloadedLogic.getResearchTemplateModelSummary(
                reloadedSleeve,
                "ResearchTemplateSleeve",
            )["geometryState"],
            "Current",
        )
        retainedSourceId = reloadedParameterNode.draftTemplateSupportModel.GetID()
        retainedTrajectoryId = reloadedParameterNode.trajectoryLine.GetID()
        retainedRoiId = reloadedParameterNode.templateShellRoi.GetID()
        retainedShellId = reloadedShell.GetID()
        retainedSleeveId = reloadedSleeve.GetID()
        retainedFinalizedShellId = reloadedFinalizedShell.GetID()
        unrelatedRoi = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsROINode",
            "Unrelated ROI",
        )
        with self.assertRaisesRegex(ValueError, "DENTOBOT Step 5B"):
            reloadedLogic.deleteTemplateShellRoi(unrelatedRoi)
        roiRemoval = reloadedLogic.deleteTemplateShellRoi(
            reloadedParameterNode.templateShellRoi
        )
        reloadedParameterNode.templateShellRoi = None
        reloadedLogic.markResearchTemplateModelsStale(
            reloadedShell,
            reloadedSleeve,
            "Shell trim ROI was deleted.",
        )
        reloadedLogic.markFinalizedTemplateShellStale(
            reloadedFinalizedShell,
            "The Step 5B source shell became stale.",
        )
        self.assertEqual(roiRemoval["nodeId"], retainedRoiId)
        self.assertIsNone(slicer.mrmlScene.GetNodeByID(retainedRoiId))
        self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(retainedSourceId))
        self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(retainedTrajectoryId))
        self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(retainedShellId))
        self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(retainedSleeveId))
        self.assertIsNotNone(
            slicer.mrmlScene.GetNodeByID(retainedFinalizedShellId)
        )
        for modelNode, role in (
            (reloadedShell, "ResearchTemplateShell"),
            (reloadedSleeve, "ResearchTemplateSleeve"),
        ):
            staleSummary = reloadedLogic.getResearchTemplateModelSummary(
                modelNode,
                role,
            )
            self.assertEqual(staleSummary["geometryState"], "Stale")
            self.assertEqual(
                staleSummary["staleReason"],
                "Shell trim ROI was deleted.",
            )
            self.assertIsNone(staleSummary["roi"])
        self.assertEqual(
            reloadedLogic.getFinalizedTemplateShellSummary(
                reloadedFinalizedShell
            )["geometryState"],
            "Stale",
        )
        finalizationRemovals = reloadedLogic.deleteTemplateFinalization(
            reloadedTrimPlane,
            reloadedParameterNode.templateTrimCurve,
            reloadedFinalizedShell,
        )
        self.assertGreaterEqual(len(finalizationRemovals), 5)
        removals = reloadedLogic.deleteResearchTemplateModels(
            reloadedShell,
            reloadedSleeve,
        )
        reloadedParameterNode.researchTemplateShellModel = None
        reloadedParameterNode.researchTemplateSleeveModel = None
        self.assertEqual(len(removals), 2)
        self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(retainedSourceId))
        self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(retainedTrajectoryId))
        self.assertIsNone(slicer.mrmlScene.GetNodeByID(retainedRoiId))

        self.delayDisplay(
            "DENTOWorkflow Steps 5B/5C geometry, STL, save/reload, ROI reset, and deletion tests passed"
        )

    def test_DENTOWorkflowSafeDeletionAndPersistence(self) -> None:
        slicer.mrmlScene.Clear(0)
        logic = DENTOWorkflowLogic()
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "DeletionPersistenceSegmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        for index, (segmentId, segmentName) in enumerate(
            (
                ("tooth-16", "upper_right_first_molar_fdi16"),
                ("tooth-15", "upper_right_second_premolar_fdi15"),
            )
        ):
            segment = slicer.vtkSegment()
            segment.SetName(segmentName)
            cube = vtk.vtkCubeSource()
            cube.SetBounds(
                float(index * 4 - 1),
                float(index * 4 + 1),
                -1.0,
                1.0,
                -2.0,
                2.0,
            )
            cube.Update()
            segment.AddRepresentation(
                slicer.vtkSegmentationConverter
                .GetSegmentationClosedSurfaceRepresentationName(),
                cube.GetOutput(),
            )
            segmentationNode.GetSegmentation().AddSegment(segment, segmentId)
        logic.setSegmentationReviewState(
            segmentationNode,
            "Reviewed",
            updatedUtc="2026-08-04T08:00:00+00:00",
        )

        roiNode, _bounds = logic.createOrUpdateTargetBoundsRoi(
            segmentationNode,
            "tooth-16",
        )
        trajectoryNode = logic.createTrajectoryNode("Delete Me Trajectory")
        logic.configureTrajectoryTarget(
            trajectoryNode,
            segmentationNode,
            "tooth-16",
        )
        trajectoryNode.SetNodeReferenceID(
            logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
            roiNode.GetID(),
        )
        trajectoryNode.AddControlPoint(vtk.vtkVector3d(-0.5, 0.0, 0.0))
        trajectoryNode.AddControlPoint(vtk.vtkVector3d(0.5, 0.0, 0.0))
        trajectoryNode.AddDefaultStorageNode()

        modelNode, _details = logic.createOrUpdateDraftTemplateSupportModel(
            segmentationNode,
            "tooth-16",
            ["tooth-15"],
        )
        modelNode.AddDefaultStorageNode()

        parameterNode = logic.getParameterNode()
        parameterNode.teethSegmentation = segmentationNode
        parameterNode.targetToothSegmentId = "tooth-16"
        parameterNode.targetToothBoundsRoi = roiNode
        parameterNode.trajectoryLine = trajectoryNode
        parameterNode.templateSupportToothSegmentIdsJson = (
            logic.encodeTemplateSupportSegmentIds(["tooth-15"])
        )
        parameterNode.draftTemplateSupportModel = modelNode

        trajectoryId = trajectoryNode.GetID()
        trajectoryDisplayId = trajectoryNode.GetDisplayNodeID()
        trajectoryStorageId = trajectoryNode.GetStorageNodeID()
        modelId = modelNode.GetID()
        modelDisplayId = modelNode.GetDisplayNodeID()
        modelStorageId = modelNode.GetStorageNodeID()
        segmentationId = segmentationNode.GetID()
        roiId = roiNode.GetID()

        sharedDisplayConsumer = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "SharedDisplayConsumer",
        )
        sharedDisplayConsumer.SetAndObservePolyData(modelNode.GetPolyData())
        sharedDisplayConsumer.SetAndObserveDisplayNodeID(modelDisplayId)

        unrelatedLine = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsLineNode",
            "Unrelated User Line",
        )
        unrelatedLine.CreateDefaultDisplayNodes()
        with self.assertRaisesRegex(ValueError, "DENTOBOT Step 4A"):
            logic.deleteTrajectoryNode(unrelatedLine)
        unrelatedModel = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Unrelated User Model",
        )
        with self.assertRaisesRegex(ValueError, "DENTOBOT Step 5A"):
            logic.deleteDraftTemplateSupportModel(unrelatedModel)

        trajectoryRemoval = logic.deleteTrajectoryNode(trajectoryNode)
        self.assertEqual(trajectoryRemoval["nodeId"], trajectoryId)
        self.assertIsNone(slicer.mrmlScene.GetNodeByID(trajectoryId))
        self.assertIsNone(slicer.mrmlScene.GetNodeByID(trajectoryDisplayId))
        self.assertIsNone(slicer.mrmlScene.GetNodeByID(trajectoryStorageId))
        self.assertIsNone(parameterNode.trajectoryLine)

        modelRemoval = logic.deleteDraftTemplateSupportModel(modelNode)
        self.assertEqual(modelRemoval["nodeId"], modelId)
        self.assertIsNone(slicer.mrmlScene.GetNodeByID(modelId))
        self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(modelDisplayId))
        self.assertIsNone(slicer.mrmlScene.GetNodeByID(modelStorageId))
        self.assertIsNone(parameterNode.draftTemplateSupportModel)

        self.assertEqual(parameterNode.teethSegmentation.GetID(), segmentationId)
        self.assertEqual(parameterNode.targetToothSegmentId, "tooth-16")
        self.assertEqual(parameterNode.targetToothBoundsRoi.GetID(), roiId)
        self.assertEqual(
            logic.decodeTemplateSupportSegmentIds(
                parameterNode.templateSupportToothSegmentIdsJson
            ),
            ["tooth-15"],
        )
        self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(segmentationId))
        self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(roiId))
        self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(unrelatedLine.GetID()))
        self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(unrelatedModel.GetID()))

        scenePath = Path(slicer.app.temporaryPath) / (
            f"dentobot-delete-persistence-{uuid.uuid4().hex}.mrb"
        )
        try:
            self.assertTrue(slicer.util.saveScene(str(scenePath)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(scenePath)))
        finally:
            scenePath.unlink(missing_ok=True)

        reloadedLogic = DENTOWorkflowLogic()
        reloadedParameterNode = reloadedLogic.getParameterNode()
        self.assertIsNone(reloadedParameterNode.trajectoryLine)
        self.assertIsNone(reloadedParameterNode.draftTemplateSupportModel)
        self.assertEqual(
            reloadedParameterNode.teethSegmentation.GetID(),
            segmentationId,
        )
        self.assertEqual(
            reloadedParameterNode.targetToothBoundsRoi.GetID(),
            roiId,
        )
        self.assertEqual(
            reloadedParameterNode.targetToothSegmentId,
            "tooth-16",
        )
        self.assertEqual(
            reloadedLogic.decodeTemplateSupportSegmentIds(
                reloadedParameterNode.templateSupportToothSegmentIdsJson
            ),
            ["tooth-15"],
        )
        self.assertIsNone(slicer.mrmlScene.GetNodeByID(trajectoryId))
        self.assertIsNone(slicer.mrmlScene.GetNodeByID(modelId))

        recreatedTrajectory = reloadedLogic.createTrajectoryNode(
            "Recreated Trajectory"
        )
        reloadedLogic.configureTrajectoryTarget(
            recreatedTrajectory,
            reloadedParameterNode.teethSegmentation,
            reloadedParameterNode.targetToothSegmentId,
        )
        recreatedModel, recreatedDetails = (
            reloadedLogic.createOrUpdateDraftTemplateSupportModel(
                reloadedParameterNode.teethSegmentation,
                reloadedParameterNode.targetToothSegmentId,
                ["tooth-15"],
            )
        )
        self.assertTrue(
            reloadedLogic.isDentobotTrajectoryNode(recreatedTrajectory)
        )
        self.assertTrue(
            reloadedLogic.isDraftTemplateSupportModelNode(recreatedModel)
        )
        self.assertEqual(recreatedDetails["supportCount"], 1)

        self.delayDisplay(
            "DENTOWorkflow safe deletion and save/reload tests passed"
        )
