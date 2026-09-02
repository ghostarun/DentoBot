"""Authoritative MRML parameter-node schema."""

from __future__ import annotations

from .runtime import *


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
    trajectoryPlacementMode: str = "Manual"
    assistedTrajectoryEntries: vtkMRMLMarkupsFiducialNode
    assistedTrajectoryCount: int = 2
    targetDockingReferencePlane: vtkMRMLMarkupsPlaneNode
    targetDockingAssemblyModel: vtkMRMLModelNode
    targetDockingPatternRadiusMm: float = 15.0
    targetDockingOuterDiameterMm: float = 3.0
    targetDockingBoreDiameterMm: float = 1.0
    targetDockingConnectorDiameterMm: float = 3.5
    targetDockingConnectorThicknessMm: float = 2.0
    targetDockingSharedDepthMm: float = 5.0
    targetDockingYawDeg: float = 0.0
    targetDockingCollisionClearanceMm: float = 0.5
    targetDockingYawConfirmed: bool = False
    targetDockingMeasurementsVisible: bool = True
    targetDockingIndividualDepthsEnabled: bool = False
    targetDockingDepth1Mm: float = 5.0
    targetDockingDepth2Mm: float = 5.0
    targetDockingDepth3Mm: float = 5.0
    targetDockingDepth4Mm: float = 5.0
    templateSupportToothSegmentIdsJson: str = "[]"
    draftTemplateSupportModel: vtkMRMLModelNode
    templateSupportBoundaryCurve: vtkMRMLMarkupsClosedCurveNode
    templateSupportBoundaryPlane: vtkMRMLMarkupsPlaneNode
    templateSupportPlaneDepthMm: float = 3.0
    templateSupportCrownCapPercent: float = 10.0
    templateSupportCurveSamplingSpacingMm: float = 0.5
    templateTerminalSupportCoveragePercent: float = 50.0
    templateSupportSelectionMode: str = "Smallest"
    templateSupportDirectionReversed: bool = False
    visibleTemplateSupportModel: vtkMRMLModelNode
    templateInsertionDirection: vtkMRMLMarkupsLineNode
    templateUndercutAngleToleranceDeg: float = 5.0
    templateInterproximalReliefMm: float = 1.0
    templateBlockoutSafetyMm: float = 0.1
    templateShellVoxelClosingMm: float = 0.3
    templateUndercutSurfaceModel: vtkMRMLModelNode
    templateUndercutBlockoutModel: vtkMRMLModelNode
    patientContactShellModel: vtkMRMLModelNode
    templateShellRoi: vtkMRMLMarkupsROINode
    templateShellClearanceMm: float = 0.3
    templateShellThicknessMm: float = 1.5
    templateSamplingSpacingMm: float = 0.3
    templateChannelDiameterMm: float = 1.5
    templateSleeveOuterDiameterMm: float = 4.4
    templateSleeveInnerDiameterMm: float = 1.5
    templateSleeveHeightMm: float = 2.5
    templateDockingClearanceMm: float = 0.3
    templateReinforcementRadialMm: float = 1.0
    templateReinforcementDepthMm: float = 2.0
    templateDockingAssemblyModel: vtkMRMLModelNode
    templateDockingClearanceModel: vtkMRMLModelNode
    templateDockingReinforcementModel: vtkMRMLModelNode
    templateDockingChannelsModel: vtkMRMLModelNode
    finalPrintableTemplateModel: vtkMRMLModelNode
    researchTemplateShellModel: vtkMRMLModelNode
    researchTemplateSleeveModel: vtkMRMLModelNode
    templateFinalizationMode: str = "PlaneCut"
    templateFinalizationKeepRegion: str = "Negative"
    templateFinalizationViewLocked: bool = True
    templateFinalizationYawLocked: bool = False
    templateTrimPlane: vtkMRMLMarkupsPlaneNode
    templateTrimCurve: vtkMRMLMarkupsClosedCurveNode
    finalizedTemplateShellModel: vtkMRMLModelNode
    robotBaseTransform: vtkMRMLLinearTransformNode
    robotMountPlane: vtkMRMLMarkupsPlaneNode
    robotForeheadProxyModel: vtkMRMLModelNode
    draftPhantomSkullModel: vtkMRMLModelNode
    draftPhantomMandibleModel: vtkMRMLModelNode
    draftJawLandmarks: vtkMRMLMarkupsFiducialNode
    draftJawTransform: vtkMRMLLinearTransformNode
    draftJawGapLine: vtkMRMLMarkupsLineNode
    draftJawTargetGapMm: float = 40.0
    step6CaseJawLandmarks: vtkMRMLMarkupsFiducialNode
    step6CaseJawTransform: vtkMRMLLinearTransformNode
    step6CaseJawGapLine: vtkMRMLMarkupsLineNode
    step6OpenedLowerJawModel: vtkMRMLModelNode
    step6FixedUpperAnatomy: vtkMRMLSegmentationNode
    step6MovingLowerAnatomy: vtkMRMLSegmentationNode
    step6TargetJawFallbackAnatomy: vtkMRMLSegmentationNode
    step6OpenedTargetGeometryModel: vtkMRMLModelNode
    step6OpenedTrajectoryLine: vtkMRMLMarkupsLineNode
    step6CaseJawTargetGapMm: float = 40.0
    step6CaseJawPreparationMode: str = "ClosedSource"
    step6CaseJawPreparationJson: str = ""
    step6CaseJawLastFailureJson: str = ""
    robotJoint1Deg: float = 0.0
    robotJoint2Mm: float = 0.0
    robotJoint3Deg: float = 0.0
    robotJoint4Mm: float = 0.0
    robotJoint5Deg: float = 0.0
    robotJoint6Deg: float = 0.0
    robotTranslationStepMm: float = 1.0
    robotRotationStepDeg: float = 1.0
    robotKeyboardNudgeEnabled: bool = False
    robotBaseMountLocked: bool = False
    step6BasePlacementStatus: str = "Unlocked"
    step6BasePlacementSource: str = "operator-unlocked"
    step6BasePlacementRevision: int = 0
    step6ForeheadProxyWidthMm: float = 140.0
    step6ForeheadProxyHeightMm: float = 85.0
    step6ForeheadProxyDepthMm: float = 28.0
    step6ForeheadProxyOffsetMm: float = 0.0
    step6TaskHomeJson: str = ""
    step6AssistedLimitProposalJson: str = ""
    step6ConfirmedTaskJson: str = ""
    step6CollisionSceneAuditJson: str = ""
    step6MotionDiagnosticJson: str = ""
    step6ApproachStandoffMm: float = 2.0
    # Retained only for older .dentocase/MRML packages. Planner v4 validates
    # the complete PreEntry→Entry line with the independent phase guard.
    step6TerminalContactToleranceMm: float = 0.25
    step6TrajectoryCorridorRadiusMm: float = 0.75
    step6ToolFrame: str = "dentobot_drill_tip_provisional"
    step6CbctVolumeRenderingNodeId: str = ""
    step6CbctOpacity: float = 0.18
    step6MasksOpacity: float = 0.45
    step6RobotOpacity: float = 1.0
    step6GoalRobotOpacity: float = 0.35
    step6GuidesOpacity: float = 0.65
    step6MountPlaneOpacity: float = 0.35
    step6TrajectoryOpacity: float = 1.0
    step6ForeheadProxyOpacity: float = 0.20
    step6CollisionAuditOpacity: float = 0.45
    step6PlanningContextImported: bool = False
    robotMotionPlanSampleCount: int = 12
    robotCoarseSelfClearanceMm: float = 5.0
    robotEnvironmentClearanceMm: float = 2.0
    robotWorkspaceSampleCount: int = 600
    robotJoint1TaskMinDeg: float = -25.38
    robotJoint1TaskMaxDeg: float = 334.62
    robotJoint2TaskMinMm: float = 0.0
    robotJoint2TaskMaxMm: float = 80.0
    robotJoint3TaskMinDeg: float = -62.46
    robotJoint3TaskMaxDeg: float = 297.54
    robotJoint4TaskMinMm: float = 0.0
    robotJoint4TaskMaxMm: float = 75.0
    robotJoint5TaskMinDeg: float = -180.0
    robotJoint5TaskMaxDeg: float = 180.0
    robotJoint6TaskMinDeg: float = -360.0
    robotJoint6TaskMaxDeg: float = 360.0
    sceneDisplayPresetJson: str = ""
