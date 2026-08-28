"""Extracted widget initialization and setup methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from .runtime import *


class BootstrapWidgetMixin:
    def __init__(self, parent=None) -> None:
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic: DENTOWorkflowLogic | None = None
        self._parameterNode: DENTOWorkflowParameterNode | None = None
        self._parameterNodeGuiTag = None
        self._updatingFromParameterNode = False
        self._updatingWorkflowNavigationUI = False
        self._workflowNavigationInitializedFromScene = False
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
        self._reviewSourceVolumeNode = None
        self._reviewSourceVolumeDisplayNode = None
        self._loadedVolumeDisplaySettingsByNodeId: dict[str, dict] = {}
        self._uiWidget = None
        self._workflowContentScrollArea = None
        self._workflowContentWidget = None
        self._workflowContentLayout = None
        self._persistentDisplayGroupBox = None
        self._viewControlsPalette = None
        self._viewControlsTabWidget = None
        self._viewControlsElementsTabIndex = -1
        self._viewControlsDisplayTabIndex = -1
        self._viewControlsButton = None
        self._workflowViewStageLabel = None
        self._workflowRecommendedViewButton = None
        self._workflowViewAdvancedButton = None
        self._workflowJawViewButtons: dict[tuple[str, str], object] = {}
        self._workflowAnatomyComboBox = None
        self._workflowDimensionComboBox = None
        self._workflowCbctComboBox = None
        self._workflowOverlayButton = None
        self._workflowOverlayActions: dict[str, object] = {}
        self._workflowAdvancedTree = None
        self._workflowAutoRecommendCheckBox = None
        self._step6ViewContextWidget = None
        self._step6ViewContextLabel = None
        self._workflowViewComposition: ViewComposition | None = None
        self._workflowViewCreatedRendererNodeIds: set[str] = set()
        self._workflowViewCreatedPropertyNodeIds: set[str] = set()
        self._stageExclusiveInteractionPriorState: dict[str, dict] = {}
        self._guidanceToolButton = None
        self._viewControlsPaletteDesiredVisible = False
        self._viewControlsPaletteGeometryRestored = False
        self._applicationShell: DENTOApplicationShell | None = None
        self._guiModeButton = None
        self._cbctWindowSlider = None
        self._cbctLevelSlider = None
        self._cbctWindowSliderValueLabel = None
        self._cbctLevelSliderValueLabel = None
        self._displayPresetStatusLabel = None
        self._applySceneDisplayPresetButton = None
        self._displaySliderScale = 10.0
        self._segmentReviewRecordsById: dict[str, dict] = {}
        self._reviewMetadataWarning = ""
        self._updatingSegmentationReviewUI = False
        self._processingSegmentationContentChange = False
        self._planningTrajectoryNode = None
        self._planningTrajectoryDisplayNode = None
        self._draftJawLandmarksNode = None
        self._step6CaseJawLandmarksNode = None
        self._updatingStep6CaseJawLandmarks = False
        self._assistedTrajectoryEntryNode = None
        self._assistedTrajectoryFocusState: dict | None = None
        self._resumeAssistedTrajectoryFocusAfterSave = False
        self._crossViewNavigationPriorState: dict | None = None
        self._resumeCrossViewNavigationAfterSave = False
        self._updatingCrossViewNavigationUI = False
        self._targetToothRecordsById: dict[str, dict] = {}
        self._updatingPlanningUI = False
        self._updatingTargetDockingUI = False
        self._restoringTrajectoryAssociation = False
        self._planningConstraintWarning = ""
        self._validTrajectoryPointsByNodeId: dict[str, list[list[float]]] = {}
        self._planningTrajectoryGeometryByNodeId: dict[str, dict] = {}
        self._caseBundleRestoreDepth = 0
        self._caseBundleRestoreGeneration = 0
        self._trajectoryVerificationEnabled = False
        self._trajectoryVerificationAngleDeg = 0.0
        self._trajectoryVerificationPriorSliceState: dict | None = None
        self._trajectoryVerificationPriorDisplayState: dict | None = None
        self._trajectoryVerificationUpdatePending = False
        self._trajectoryVerificationPointInteractionActive = False
        self._trajectoryVerificationAppliedTrajectoryNodeId: str | None = None
        self._trajectoryVerificationLastAppliedAngleDeg: float | None = None
        self._updatingTrajectoryVerificationUI = False
        self._resumeTrajectoryVerificationAfterSave = False
        self._trajectoryVerificationResumeStateAfterSave: dict | None = None
        self._templateSupportRecordsById: dict[str, dict] = {}
        self._templateSupportArchWidget = None
        self._templateSupportArchGridLayout = None
        self._templateSupportArchStatusLabel = None
        self._reviseTemplateSupportPackageButton = None
        self._templateSupportPackageWidget = None
        self._templateSupportPackageSummaryLabel = None
        self._templateSupportPackageDetailsLabel = None
        self._returnToStep4BSupportButton = None
        self._templateSupportButtonsBySegmentId: dict[str, object] = {}
        self._unifiedTemplateReadinessGroup = None
        self._unifiedTemplateInputsGroup = None
        self._unifiedTemplateActionGroup = None
        self._updatingTemplateUI = False
        self._templateStatusWarning = ""
        self._templateSupportBoundaryNode = None
        self._restoringTemplateSupportBoundary = False
        self._templateSupportBoundaryFocusState: dict | None = None
        self._resumeTemplateSupportBoundaryFocusAfterSave = False
        self._templateInsertionDirectionNode = None
        self._templateInsertionDirectionGeometryByNodeId: dict[str, dict] = {}
        self._restoringTemplateInsertionDirection = False
        self._updatingTemplateGuideUI = False
        self._updatingGuideTrajectorySelectionUI = False
        self._guideTrajectoryObserverNodes: list[vtkMRMLMarkupsLineNode] = []
        self._updatingTemplateGuideVisibilityUI = False
        self._updatingWorkflowViewUI = False
        self._workflowViewRefreshScheduled = False
        self._workflowViewEntriesByKey: dict[str, dict] = {}
        self._workflowViewPriorState: dict | None = None
        self._workflowViewActivePresetKey = ""
        self._workflowViewVisibleKeys: set[str] = set()
        self._workflowViewStageIndex = -1
        self._resumeWorkflowViewPresetAfterSave = ""
        self._resumeWorkflowViewPriorStateAfterSave: dict | None = None
        self._resumeWorkflowViewVisibleKeysAfterSave: set[str] = set()
        self._resumeWorkflowViewCompositionAfterSave: ViewComposition | None = None
        self._updatingTemplateFinalizationUI = False
        self._templateFinalizationPriorVisibilityByNodeId: dict[str, bool] = {}
        self._templateFinalizationPriorLayoutId: int | None = None
        self._templateFinalizationPriorCameraState: dict | None = None
        self._templateFinalizationPriorViewNodeState: dict | None = None
        self._templateFinalizationPriorCrosshairMode: int | None = None
        self._templateFinalizationCamera = None
        self._templateFinalizationCameraFrame: dict | None = None
        self._templateFinalizationYawDegrees = 0.0
        self._templateFinalizationCameraCorrectionPending = False
        self._templateTrimPlaneNode = None
        self._templateTrimCurveNode = None
        self._restoringTemplateFinalizationCamera = False
        self._restoringTemplateTrimPlane = False
        self._robotKeyboardShortcuts: list[qt.QShortcut] = []
        self._robotBaseTransformNode = None
        self._lastRobotBasePoseFingerprint = ""
        self._robotWorkflowFacade: DENTORobotWorkflowFacade | None = None
        self._robotSimulationPanel: DENTORobotSimulationPanel | None = None
        self._step6SubstepNavigator = None
        self._step6SubstepComboBox = None
        self._step6PreviousSubstepButton = None
        self._step6NextSubstepButton = None
        self._step6SubstepIndex = 0
        self._updatingStep6SubstepNavigation = False
        self._step6ExpertDiagnosticHandoffActive = False
        self._step6ExpertReturnToolbar = None
        self._step6MotionPlan: MotionPlanResult | None = None
        self._step6MotionPreviewTimer = None
        self._step6MotionPreviewIndex = 0
        self._resumeRos2MotionActiveBaseIdsAfterSave: list[str] = []
        self._robotMountPlaneNode = None
        self._updatingRobotPlacementUI = False
        self._loadedCaseBundlePath: str = ""
        self._caseBundleRobotProfileCompatible: bool | None = None
        self._isCleaningUp = False

    def setup(self) -> None:
        super().setup()

        uiWidget = slicer.util.loadUI(self.resourcePath("UI/DENTOWorkflow.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        self._uiWidget = uiWidget
        uiWidget.setMRMLScene(slicer.mrmlScene)
        self._setupPersistentWorkflowShell(uiWidget)
        self._setupTrajectoryPlanningModes()
        self._setupTemplateSupportArchSelector()
        self.ui.draftTemplateSupportModelSelector.addAttribute(
            "vtkMRMLModelNode",
            "DENTOBOT.ModelRole",
            "TemplateSupportDraft",
        )
        self.ui.templateShellRoiSelector.addAttribute(
            "vtkMRMLMarkupsROINode",
            "DENTOBOT.MarkupsRole",
            "TemplateShellTrimROI",
        )
        self.ui.templateShellRoiSelector.setCurrentNode(None)
        self.ui.templateSupportBoundaryCurveSelector.addAttribute(
            "vtkMRMLMarkupsClosedCurveNode",
            "DENTOBOT.MarkupsRole",
            "TemplateSupportBoundary",
        )
        self.ui.templateSupportBoundaryPlaneSelector.addAttribute(
            "vtkMRMLMarkupsPlaneNode",
            "DENTOBOT.MarkupsRole",
            "TemplateSupportBoundaryPlane",
        )
        self.ui.visibleTemplateSupportModelSelector.addAttribute(
            "vtkMRMLModelNode",
            "DENTOBOT.ModelRole",
            "VisibleTemplateSupportSurface",
        )
        self.ui.patientContactShellModelSelector.addAttribute(
            "vtkMRMLModelNode",
            "DENTOBOT.ModelRole",
            "PatientContactShell",
        )
        self.ui.templateInsertionDirectionSelector.addAttribute(
            "vtkMRMLMarkupsLineNode",
            "DENTOBOT.MarkupsRole",
            "TemplateInsertionDirection",
        )
        self.ui.templateUndercutSurfaceModelSelector.addAttribute(
            "vtkMRMLModelNode",
            "DENTOBOT.ModelRole",
            "TemplateUndercutSurface",
        )
        self.ui.templateUndercutBlockoutModelSelector.addAttribute(
            "vtkMRMLModelNode",
            "DENTOBOT.ModelRole",
            "TemplateUndercutBlockout",
        )
        self.ui.finalPrintableTemplateModelSelector.addAttribute(
            "vtkMRMLModelNode",
            "DENTOBOT.ModelRole",
            "FinalPrintableTemplate",
        )
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
        self.ui.robotBaseTransformSelector.addAttribute(
            "vtkMRMLLinearTransformNode",
            "DENTOBOT.TransformRole",
            "RobotBase",
        )
        self.ui.robotMountPlaneSelector.addAttribute(
            "vtkMRMLMarkupsPlaneNode",
            "DENTOBOT.MarkupsRole",
            "RobotMountPlane",
        )
        self.ui.draftPhantomSkullSelector.addAttribute(
            "vtkMRMLModelNode",
            "DENTOBOT.PhantomPart",
            "Neurocranium",
        )
        self.ui.draftPhantomMandibleSelector.addAttribute(
            "vtkMRMLModelNode",
            "DENTOBOT.PhantomPart",
            "Mandible",
        )
        self.ui.draftJawLandmarksSelector.addAttribute(
            "vtkMRMLMarkupsFiducialNode",
            "DENTOBOT.MarkupsRole",
            "DraftJawLandmarks",
        )
        self.ui.step6CaseJawLandmarksSelector.addAttribute(
            "vtkMRMLMarkupsFiducialNode",
            "DENTOBOT.MarkupsRole",
            "Step6CaseJawLandmarks",
        )
        self.ui.targetDockingReferencePlaneSelector.addAttribute(
            "vtkMRMLMarkupsPlaneNode",
            "DENTOBOT.MarkupsRole",
            "TargetDockingReferencePlane",
        )
        self.ui.targetDockingAssemblyModelSelector.addAttribute(
            "vtkMRMLModelNode",
            "DENTOBOT.ModelRole",
            "TargetDockingAssembly",
        )
        self.ui.finalVerificationModelSelector.addAttribute(
            "vtkMRMLModelNode",
            "DENTOBOT.ModelRole",
            "FinalPrintableTemplate",
        )
        self.ui.trajectorySelector.addAttribute(
            "vtkMRMLMarkupsLineNode",
            "DENTOBOT.TrajectoryRole",
            "EntryToTarget",
        )

        self._setupUnifiedTemplateBuildPanel()

        # _setupPersistentWorkflowShell reparents the scrollable workflow
        # controls below a pinned header. qMRMLNodeComboBox does not reliably
        # retain the scene propagated by the original qMRMLWidget across that
        # reparenting (notably after loading an MRB), which leaves valid derived
        # nodes looking like empty selectors. Bind every selector explicitly
        # after the persistent shell and attribute filters have been installed.
        for nodeSelector in uiWidget.findChildren("qMRMLNodeComboBox"):
            nodeSelector.setMRMLScene(slicer.mrmlScene)

        self.logic = DENTOWorkflowLogic()
        self._robotWorkflowFacade = DENTORobotWorkflowFacade(
            self.logic,
            lambda: self._parameterNode,
        )
        self._setupWorkflowNavigation()
        self.ui.assistedTrajectoryCountComboBox.clear()
        self.ui.assistedTrajectoryCountComboBox.addItem(
            _("1 trajectory / root target"),
            1,
        )
        self.ui.assistedTrajectoryCountComboBox.addItem(
            _("2 trajectories / root targets"),
            2,
        )
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
                "Linux runtime owns dependency-heavy inference."
            )
            self.ui.checkBackendButton.text = _("Check Linux Backend")
            self.ui.roundTripButton.toolTip = _(
                "Export the selected volume to NIfTI, rewrite it in the "
                "isolated Linux backend, validate it, and import it."
            )
        else:
            self.ui.backendDescriptionLabel.text = _(
                "Native Windows Slicer owns UI and MRML. The dedicated Linux "
                "inference environment runs through WSL2."
            )
            self.ui.checkBackendButton.text = _("Check WSL Backend")
            self.ui.roundTripButton.toolTip = _(
                "Export the selected volume to a local Windows run folder, "
                "process it in WSL2, validate it, and import it."
            )

        self.ui.newCaseButton.connect("clicked(bool)", self.onNewCase)
        self.ui.saveCaseBundleButton.connect(
            "clicked(bool)", self.onSaveCaseBundle
        )
        self.ui.openCaseBundleButton.connect(
            "clicked(bool)", self.onOpenCaseBundle
        )
        self.ui.reloadDENTOWorkflowButton.connect(
            "clicked(bool)",
            self.onReloadDENTOWorkflowModule,
        )
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
        self.ui.segmentation2DRenderingModeComboBox.connect(
            "currentIndexChanged(int)",
            self.onSegmentation2DRenderingModeChanged,
        )
        self.ui.cbctInterpolationCheckBox.connect(
            "toggled(bool)",
            self.onCbctInterpolationToggled,
        )
        self.ui.cbctAutoWindowLevelCheckBox.connect(
            "toggled(bool)",
            self.onCbctAutoWindowLevelToggled,
        )
        self.ui.cbctWindowSpinBox.connect(
            "valueChanged(double)",
            self.onCbctWindowLevelChanged,
        )
        self.ui.cbctLevelSpinBox.connect(
            "valueChanged(double)",
            self.onCbctWindowLevelChanged,
        )
        self.ui.cbctInvertGrayscaleCheckBox.connect(
            "toggled(bool)",
            self.onCbctInvertGrayscaleToggled,
        )
        self.ui.cbctRestoreLoadedDisplayButton.connect(
            "clicked(bool)",
            self.onRestoreLoadedCbctDisplay,
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
        self.ui.focusPlanningTargetButton.connect(
            "clicked(bool)",
            self.onFocusPlanningTarget,
        )
        self.ui.framePlanningTargetButton.connect(
            "clicked(bool)",
            self.onFramePlanningTarget,
        )
        self.ui.restorePlanningViewButton.connect(
            "clicked(bool)",
            self.onRestorePlanningView,
        )
        self.ui.crossViewNavigationCheckBox.connect(
            "toggled(bool)",
            self.onCrossViewNavigationToggled,
        )
        self.ui.trajectoryVerificationEnabledCheckBox.connect(
            "toggled(bool)",
            self.onTrajectoryVerificationToggled,
        )
        self.ui.trajectoryVerificationRotationSlider.connect(
            "valueChanged(int)",
            self.onTrajectoryVerificationRotationChanged,
        )
        self.ui.resetTrajectoryVerificationButton.connect(
            "clicked(bool)",
            self.onResetTrajectoryVerification,
        )
        self.ui.trajectoryVerificationSmoothInterpolationCheckBox.connect(
            "toggled(bool)",
            self.onTrajectoryVerificationSmoothingToggled,
        )
        self.ui.assistedTrajectoryCountComboBox.connect(
            "currentIndexChanged(int)",
            self.onAssistedTrajectoryCountChanged,
        )
        self.ui.placeAssistedTrajectoryEntriesButton.connect(
            "clicked(bool)",
            self.onPlaceAssistedTrajectoryEntries,
        )
        self.ui.generateAssistedTrajectoriesButton.connect(
            "clicked(bool)",
            self.onGenerateAssistedTrajectories,
        )
        self.ui.restoreAssistedTrajectoryFocusButton.connect(
            "clicked(bool)",
            self.onRestoreAssistedTrajectoryFocus,
        )
        self.ui.targetDockingReferencePlaneSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onTargetDockingReferencePlaneSelectionChanged,
        )
        self.ui.targetDockingAssemblyModelSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onTargetDockingAssemblySelectionChanged,
        )
        self.ui.targetDockingIndividualDepthsCheckBox.connect(
            "toggled(bool)",
            self.onTargetDockingInputChanged,
        )
        self.ui.targetDockingYawSlider.connect(
            "valueChanged(int)",
            self.onTargetDockingYawChanged,
        )
        self.ui.applyTargetDockingYawButton.connect(
            "clicked(bool)",
            self.onApplyTargetDockingYaw,
        )
        self.ui.confirmTargetDockingYawButton.connect(
            "clicked(bool)",
            self.onConfirmTargetDockingYaw,
        )
        self.ui.targetDockingMeasurementsVisibleCheckBox.connect(
            "toggled(bool)",
            self.onTargetDockingMeasurementsVisibilityChanged,
        )
        for parameterWidget in (
            self.ui.targetDockingPatternRadiusSpinBox,
            self.ui.targetDockingOuterDiameterSpinBox,
            self.ui.targetDockingBoreDiameterSpinBox,
            self.ui.targetDockingConnectorDiameterSpinBox,
            self.ui.targetDockingConnectorThicknessSpinBox,
            self.ui.targetDockingSharedDepthSpinBox,
            self.ui.targetDockingCollisionClearanceSpinBox,
            self.ui.targetDockingDepth1SpinBox,
            self.ui.targetDockingDepth2SpinBox,
            self.ui.targetDockingDepth3SpinBox,
            self.ui.targetDockingDepth4SpinBox,
        ):
            parameterWidget.connect(
                "valueChanged(double)",
                self.onTargetDockingInputChanged,
            )
        self.ui.generateTargetDockingAssemblyButton.connect(
            "clicked(bool)",
            self.onGenerateTargetDockingAssembly,
        )
        self.ui.deleteTargetDockingAssemblyButton.connect(
            "clicked(bool)",
            self.onDeleteTargetDockingAssembly,
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
        self.ui.reviewSegmentationForTemplateButton.connect(
            "clicked(bool)",
            self.onReviewSegmentationForTemplate,
        )
        self.ui.deleteDraftTemplateSupportModelButton.connect(
            "clicked(bool)",
            self.onDeleteDraftTemplateSupportModel,
        )
        self._reviseTemplateSupportPackageButton.connect(
            "clicked(bool)",
            self.onReviseTemplateSupportPackage,
        )
        self._returnToStep4BSupportButton.connect(
            "clicked(bool)",
            self.onReturnToStep4BSupportSelection,
        )
        self.ui.focusTemplateSupportButton.connect(
            "clicked(bool)",
            self.onFocusTemplateSupport,
        )
        self.ui.frameTemplateSupportButton.connect(
            "clicked(bool)",
            self.onFrameTemplateSupport,
        )
        self.ui.restoreTemplateSupportFocusButton.connect(
            "clicked(bool)",
            self.onRestoreTemplateSupportFocus,
        )
        self.ui.templateSupportBoundaryCurveSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onTemplateSupportBoundarySelectionChanged,
        )
        self.ui.visibleTemplateSupportModelSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onVisibleTemplateSupportModelSelectionChanged,
        )
        self.ui.createTemplateSupportBoundaryButton.connect(
            "clicked(bool)",
            self.onCreateTemplateSupportBoundary,
        )
        self.ui.createTemplateSupportPlaneButton.connect(
            "clicked(bool)",
            self.onCreateTemplateSupportPlane,
        )
        self.ui.generateTemplateSupportBoundaryFromPlaneButton.connect(
            "clicked(bool)",
            self.onGenerateTemplateSupportBoundaryFromPlane,
        )
        self.ui.generateVisibleTemplateSupportModelButton.connect(
            "clicked(bool)",
            self.onGenerateVisibleTemplateSupportModel,
        )
        self.ui.deleteTemplateSupportSelectionButton.connect(
            "clicked(bool)",
            self.onDeleteTemplateSupportSelection,
        )
        self.ui.flipTemplateSupportDirectionButton.connect(
            "toggled(bool)",
            self.onTemplateSupportDirectionReversedToggled,
        )
        self.ui.patientContactShellModelSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onPatientContactShellSelectionChanged,
        )
        self.ui.generatePatientContactShellButton.connect(
            "clicked(bool)",
            self.onGeneratePatientContactShell,
        )
        self.ui.deletePatientContactShellButton.connect(
            "clicked(bool)",
            self.onDeletePatientContactShell,
        )
        self.ui.templateInsertionDirectionSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onTemplateInsertionDirectionSelectionChanged,
        )
        self.ui.templateUndercutSurfaceModelSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onTemplateUndercutOutputSelectionChanged,
        )
        self.ui.templateUndercutBlockoutModelSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onTemplateUndercutOutputSelectionChanged,
        )
        self.ui.createTemplateInsertionDirectionButton.connect(
            "clicked(bool)",
            self.onCreateTemplateInsertionDirection,
        )
        self.ui.deleteTemplateInsertionDirectionButton.connect(
            "clicked(bool)",
            self.onDeleteTemplateInsertionDirection,
        )
        self.ui.analyzeTemplateUndercutsButton.connect(
            "clicked(bool)",
            self.onAnalyzeTemplateUndercuts,
        )
        self.ui.finalPrintableTemplateModelSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onFinalPrintableTemplateSelectionChanged,
        )
        self.ui.generateFinalPrintableTemplateButton.connect(
            "clicked(bool)",
            self.onBuildOrUpdateCompleteTemplate,
        )
        self.ui.deleteFinalPrintableTemplateButton.connect(
            "clicked(bool)",
            self.onDeleteFinalPrintableTemplate,
        )
        self.ui.inspectTemplateFitButton.connect(
            "clicked(bool)",
            self.onInspectTemplateFit,
        )
        self.ui.inspectShellAndGuidesButton.connect(
            "clicked(bool)",
            self.onInspectShellAndGuides,
        )
        self.ui.inspectUnifiedTemplateButton.connect(
            "clicked(bool)",
            self.onInspectUnifiedTemplate,
        )
        for parameterWidget in (
            self.ui.templateUndercutAngleToleranceSpinBox,
            self.ui.templateInterproximalReliefSpinBox,
            self.ui.templateBlockoutSafetySpinBox,
            self.ui.templateShellVoxelClosingSpinBox,
            self.ui.templateDockingClearanceSpinBox,
            self.ui.templateReinforcementRadialSpinBox,
            self.ui.templateReinforcementDepthSpinBox,
        ):
            parameterWidget.connect(
                "valueChanged(double)",
                self.onTemplateGuideInputChanged,
            )
        self.ui.templateSupportCurveSamplingSpacingSpinBox.connect(
            "valueChanged(double)",
            self.onTemplateSupportSurfaceParameterChanged,
        )
        self.ui.templateSupportPlaneDepthSpinBox.connect(
            "valueChanged(double)",
            self.onTemplateSupportPlaneDepthChanged,
        )
        self.ui.templateSupportCrownCapSpinBox.connect(
            "valueChanged(double)",
            self.onTemplateSupportPlaneDepthChanged,
        )
        self.ui.templateTerminalSupportCoverageSpinBox.connect(
            "valueChanged(double)",
            self.onTemplateSupportSurfaceParameterChanged,
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
            self.ui.patientContactShellVisibilityCheckBox,
            self.ui.templateInsertionDirectionVisibilityCheckBox,
            self.ui.templateUndercutVisibilityCheckBox,
            self.ui.templateBlockoutVisibilityCheckBox,
            self.ui.supportBoundaryVisibilityCheckBox,
            self.ui.supportPlaneVisibilityCheckBox,
            self.ui.visibleSupportVisibilityCheckBox,
            self.ui.finalTemplateVisibilityCheckBox,
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
        self.ui.templateFinalizationYawLockedCheckBox.connect(
            "toggled(bool)",
            self.onTemplateFinalizationYawLockToggled,
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
        self.ui.finalVerificationModelSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onFinalVerificationModelSelectionChanged,
        )
        self.ui.verifyFinalTemplateButton.connect(
            "clicked(bool)",
            self.onVerifyFinalTemplate,
        )
        self.ui.showFinalTemplateButton.connect(
            "clicked(bool)",
            self.onShowFinalTemplate,
        )
        self.ui.exportFinalTemplateButton.connect(
            "clicked(bool)",
            self.onExportFinalTemplate,
        )
        self.ui.loadRobotModelButton.connect(
            "clicked(bool)",
            self.onLoadRobotModel,
        )
        self.ui.loadDraftPhantomButton.connect(
            "clicked(bool)",
            self.onLoadDraftPhantom,
        )
        self.ui.createDraftJawLandmarksButton.connect(
            "clicked(bool)",
            self.onCreateDraftJawLandmarks,
        )
        self.ui.clearDraftJawLandmarksButton.connect(
            "clicked(bool)",
            self.onClearDraftJawLandmarks,
        )
        self.ui.applyDraftJawOpeningButton.connect(
            "clicked(bool)",
            self.onApplyDraftJawOpening,
        )
        self.ui.resetDraftJawButton.connect(
            "clicked(bool)",
            self.onResetDraftJaw,
        )
        self.ui.deleteDraftPhantomButton.connect(
            "clicked(bool)",
            self.onDeleteDraftPhantom,
        )
        self.ui.createStep6CaseJawLandmarksButton.connect(
            "clicked(bool)",
            self.onCreateStep6CaseJawLandmarks,
        )
        self.ui.clearStep6CaseJawLandmarksButton.connect(
            "clicked(bool)",
            self.onClearStep6CaseJawLandmarks,
        )
        self.ui.applyStep6CaseJawOpeningButton.connect(
            "clicked(bool)",
            self.onApplyStep6CaseJawOpening,
        )
        self.ui.useStep6TargetJawFallbackButton.connect(
            "clicked(bool)",
            self.onUseStep6TargetJawFallback,
        )
        self.ui.resetStep6CaseJawOpeningButton.connect(
            "clicked(bool)",
            self.onResetStep6CaseJawOpening,
        )
        self.ui.step6CaseJawTargetGapSpinBox.connect(
            "valueChanged(double)",
            self.onStep6CaseJawTargetGapChanged,
        )
        self.ui.createRobotMountPlaneButton.connect(
            "clicked(bool)",
            self.onCreateRobotMountPlane,
        )
        self.ui.snapRobotBaseToPlaneButton.connect(
            "clicked(bool)",
            self.onSnapRobotBaseToPlane,
        )
        self.ui.flipRobotMountPlaneButton.connect(
            "clicked(bool)",
            self.onFlipRobotMountPlane,
        )
        self.ui.frameRobotButton.connect("clicked(bool)", self.onFrameStep6ResearchWorkspace)
        self.ui.connectRos2MotionButton.connect(
            "clicked(bool)",
            self.onConnectRos2MotionControl,
        )
        self.ui.disconnectRos2MotionButton.connect(
            "clicked(bool)",
            self.onDisconnectRos2MotionControl,
        )
        self.ui.resetRobotJointsButton.connect(
            "clicked(bool)",
            self.onResetRobotJoints,
        )
        self.ui.resetRobotBaseButton.connect(
            "clicked(bool)",
            self.onResetRobotBase,
        )
        self.ui.deleteRobotSetupButton.connect(
            "clicked(bool)",
            self.onDeleteRobotSetup,
        )
        self.ui.importStep6PlanningContextButton.connect(
            "clicked(bool)",
            self.onImportStep6PlanningContext,
        )
        self.ui.lockRobotBaseMountButton.connect(
            "clicked(bool)",
            self.onLockRobotBaseMount,
        )
        self.ui.unlockRobotBaseMountButton.connect(
            "clicked(bool)",
            self.onUnlockRobotBaseMount,
        )
        self.ui.applyTaskJointLimitsButton.connect(
            "clicked(bool)",
            self.onApplyTaskJointLimits,
        )
        self.ui.resetTaskJointLimitsButton.connect(
            "clicked(bool)",
            self.onResetTaskJointLimits,
        )
        self.ui.generateRobotWorkspaceButton.connect(
            "clicked(bool)",
            self.onGenerateRobotWorkspace,
        )
        self.ui.clearRobotWorkspaceButton.connect(
            "clicked(bool)",
            self.onClearRobotWorkspace,
        )
        for limitSpinBox in (
            self.ui.robotJoint1TaskMinSpinBox,
            self.ui.robotJoint1TaskMaxSpinBox,
            self.ui.robotJoint2TaskMinSpinBox,
            self.ui.robotJoint2TaskMaxSpinBox,
            self.ui.robotJoint3TaskMinSpinBox,
            self.ui.robotJoint3TaskMaxSpinBox,
            self.ui.robotJoint4TaskMinSpinBox,
            self.ui.robotJoint4TaskMaxSpinBox,
            self.ui.robotJoint5TaskMinSpinBox,
            self.ui.robotJoint5TaskMaxSpinBox,
            self.ui.robotJoint6TaskMinSpinBox,
            self.ui.robotJoint6TaskMaxSpinBox,
        ):
            limitSpinBox.connect(
                "valueChanged(double)",
                self._onTaskJointLimitSpinBoxChanged,
            )
        self.ui.planTrajectoryMotionButton.connect(
            "clicked(bool)",
            self.onPlanTrajectoryMotion,
        )
        self.ui.previewTrajectoryMotionButton.connect(
            "clicked(bool)",
            self.onPreviewTrajectoryMotion,
        )
        self.ui.stopTrajectoryMotionButton.connect(
            "clicked(bool)",
            self.onStopTrajectoryMotion,
        )
        for buttonName, translationAxis, rotationAxis, direction in (
            ("robotXMinusButton", 0, None, -1.0),
            ("robotXPlusButton", 0, None, 1.0),
            ("robotYMinusButton", 1, None, -1.0),
            ("robotYPlusButton", 1, None, 1.0),
            ("robotZMinusButton", 2, None, -1.0),
            ("robotZPlusButton", 2, None, 1.0),
            ("robotRxMinusButton", None, 0, -1.0),
            ("robotRxPlusButton", None, 0, 1.0),
            ("robotRyMinusButton", None, 1, -1.0),
            ("robotRyPlusButton", None, 1, 1.0),
            ("robotRzMinusButton", None, 2, -1.0),
            ("robotRzPlusButton", None, 2, 1.0),
        ):
            getattr(self.ui, buttonName).connect(
                "clicked(bool)",
                lambda checked=False, ta=translationAxis, ra=rotationAxis, d=direction:
                    self._nudgeRobotBase(ta, ra, d),
            )
        for jointSpinBox in (
            self.ui.robotJoint1SpinBox,
            self.ui.robotJoint2SpinBox,
            self.ui.robotJoint3SpinBox,
            self.ui.robotJoint4SpinBox,
            self.ui.robotJoint5SpinBox,
            self.ui.robotJoint6SpinBox,
        ):
            jointSpinBox.connect("valueChanged(double)", self.onRobotJointValueChanged)
        self.ui.robotBaseTransformSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onRobotBaseTransformSelectionChanged,
        )
        self.ui.robotMountPlaneSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onRobotMountPlaneSelectionChanged,
        )
        self.ui.draftPhantomSkullSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onDraftPhantomSelectionChanged,
        )
        self.ui.draftPhantomMandibleSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onDraftPhantomSelectionChanged,
        )
        self.ui.draftJawLandmarksSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onDraftJawLandmarksSelectionChanged,
        )
        self.ui.step6CaseJawLandmarksSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)",
            self.onStep6CaseJawLandmarksSelectionChanged,
        )
        self.ui.robotKeyboardNudgeCheckBox.connect(
            "toggled(bool)",
            self.onRobotKeyboardNudgeToggled,
        )
        self._setupRobotKeyboardShortcuts()

        self._hideLegacyPost5BControls()

        self._addSceneObservers()
        self.initializeParameterNode()
        self._setupApplicationShell()
