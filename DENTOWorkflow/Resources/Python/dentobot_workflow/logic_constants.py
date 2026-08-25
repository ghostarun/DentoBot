"""Persisted roles and schema constants exposed by DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


class LogicConstantsMixin:
    BACKEND_MODULE = "dentobot_inference"

    BACKEND_EXECUTION_MODE_ENVIRONMENT_VARIABLE = (
        EXECUTION_MODE_ENVIRONMENT_VARIABLE
    )

    BACKEND_PYTHON_ENVIRONMENT_VARIABLE = (
        PLATFORM_BACKEND_PYTHON_ENVIRONMENT_VARIABLE
    )

    RUN_ARTIFACT_ROOT_ENVIRONMENT_VARIABLE = (
        PLATFORM_RUN_ARTIFACT_ROOT_ENVIRONMENT_VARIABLE
    )

    WSL_DISTRIBUTION_ENVIRONMENT_VARIABLE = (
        PLATFORM_WSL_DISTRIBUTION_ENVIRONMENT_VARIABLE
    )

    BACKEND_DEVICE_ENVIRONMENT_VARIABLE = (
        PLATFORM_BACKEND_DEVICE_ENVIRONMENT_VARIABLE
    )

    REVIEW_METADATA_VERSION = "1.0"

    ROBOT_PLACEMENT_SCHEMA_VERSION = "0.3"

    ROBOT_BASE_ROLE = "RobotBase"

    STEP6_PLANNING_CONTEXT_ATTRIBUTE = "DENTOBOT.Step6PlanningContextImported"

    ROBOT_LINK_POSE_ROLE = "RobotLinkPose"

    ROBOT_LINK_MODEL_ROLE = "RobotLink"

    ROBOT_MOUNT_PLANE_ROLE = "RobotMountPlane"

    ROBOT_FOREHEAD_PROXY_ROLE = "RobotForeheadProxy"

    ROBOT_WORKSPACE_MODEL_ROLE = "RobotWorkspaceCloud"

    DRAFT_PHANTOM_MODEL_ROLE = "DraftOpenMouthPhantom"

    DRAFT_PHANTOM_SKULL_PART = "Neurocranium"

    DRAFT_PHANTOM_MAXILLA_PART = "Maxilla"

    DRAFT_PHANTOM_MANDIBLE_PART = "Mandible"

    DRAFT_JAW_LANDMARKS_ROLE = "DraftJawLandmarks"

    DRAFT_JAW_LANDMARK_LABELS = (
        "Left TMJ",
        "Right TMJ",
        "Upper incisor",
        "Lower incisor",
    )

    DRAFT_PHANTOM_WORKSPACE_ROLE = "DraftPhantomWorkspace"

    STEP_6_RESEARCH_PHANTOM_CENTER_RAS = (0.0, -150.0, 250.0)

    DRAFT_JAW_TRANSFORM_ROLE = "DraftJawTransform"

    DRAFT_JAW_GAP_LINE_ROLE = "DraftJawGapLine"

    STEP6_CASE_JAW_LANDMARKS_ROLE = "Step6CaseJawLandmarks"

    STEP6_CASE_JAW_TRANSFORM_ROLE = "Step6CaseJawTransform"

    STEP6_CASE_JAW_GAP_LINE_ROLE = "Step6CaseJawGapLine"

    STEP6_OPENED_LOWER_JAW_MODEL_ROLE = "Step6OpenedLowerJaw"

    STEP6_OPENED_TARGET_GEOMETRY_MODEL_ROLE = "Step6OpenedTargetGeometry"

    STEP6_OPENED_TRAJECTORY_ROLE = "Step6OpenedTrajectory"

    STEP6_CASE_JAW_SCHEMA_VERSION = "1.0"

    REVIEW_STATES = ("Unreviewed", "Needs Correction", "Reviewed")

    SOURCE_VOLUME_REFERENCE_ROLE = "DENTOBOT.SourceVolume"

    SEGMENTATION_2D_RENDERING_MODE_ATTRIBUTE = (
        "DENTOBOT.Segmentation2DRenderingMode"
    )

    SEGMENTATION_2D_RENDERING_MODE_SMOOTH = "smooth-surface-review"

    SEGMENTATION_2D_RENDERING_MODE_NATIVE = "native-mask-editing"

    SEGMENTATION_CLOSED_SURFACE_REPRESENTATION = "Closed surface"

    SEGMENTATION_BINARY_LABELMAP_REPRESENTATION = "Binary labelmap"

    SCALAR_VOLUME_GREY_COLOR_NODE_ID = "vtkMRMLColorTableNodeGrey"

    SCALAR_VOLUME_INVERTED_GREY_COLOR_NODE_ID = (
        "vtkMRMLColorTableNodeInvertedGrey"
    )

    TARGET_SEGMENTATION_REFERENCE_ROLE = "DENTOBOT.TargetSegmentation"

    TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE = (
        "DENTOBOT.TargetBoundsSegmentation"
    )

    TARGET_BOUNDS_ROI_REFERENCE_ROLE = "DENTOBOT.TargetBoundsROI"

    TRAJECTORY_AUTO_NAME_ATTRIBUTE = "DENTOBOT.AutomaticTrajectoryName"

    ASSISTED_ENTRY_SCHEMA_VERSION = "1.0"

    ASSISTED_ENTRY_SEGMENTATION_REFERENCE_ROLE = (
        "DENTOBOT.AssistedEntrySegmentation"
    )

    ASSISTED_TRAJECTORY_ENTRY_REFERENCE_ROLE = (
        "DENTOBOT.AssistedTrajectoryEntryMarkup"
    )

    LINEAGE_COLOR_ATTRIBUTE = "DENTOBOT.LineageColorRgb"

    LINEAGE_TARGET_SEGMENT_ATTRIBUTE = "DENTOBOT.LineageTargetSegmentID"

    LINEAGE_TARGET_FDI_ATTRIBUTE = "DENTOBOT.LineageTargetFdiNumber"

    TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE = (
        "DENTOBOT.TemplateSourceSegmentation"
    )

    TEMPLATE_MODEL_SCHEMA_VERSION = "1.0"

    TEMPLATE_SUPPORT_SURFACE_SCHEMA_VERSION = "2.1"

    TEMPLATE_SUPPORT_BOUNDARY_SOURCE_MODEL_REFERENCE_ROLE = (
        "DENTOBOT.TemplateSupportBoundarySourceModel"
    )

    TEMPLATE_SUPPORT_PLANE_SOURCE_MODEL_REFERENCE_ROLE = (
        "DENTOBOT.TemplateSupportPlaneSourceModel"
    )

    TEMPLATE_SUPPORT_PLANE_SOURCE_TRAJECTORY_REFERENCE_ROLE = (
        "DENTOBOT.TemplateSupportPlaneSourceTrajectory"
    )

    TEMPLATE_SUPPORT_BOUNDARY_INITIALIZER_PLANE_REFERENCE_ROLE = (
        "DENTOBOT.TemplateSupportBoundaryInitializerPlane"
    )

    TEMPLATE_VISIBLE_SUPPORT_SOURCE_MODEL_REFERENCE_ROLE = (
        "DENTOBOT.VisibleSupportSourceModel"
    )

    TEMPLATE_VISIBLE_SUPPORT_BOUNDARY_REFERENCE_ROLE = (
        "DENTOBOT.VisibleSupportBoundary"
    )

    TEMPLATE_VISIBLE_SUPPORT_DIRECTION_TRAJECTORY_REFERENCE_ROLE = (
        "DENTOBOT.VisibleSupportDirectionTrajectory"
    )

    TEMPLATE_VISIBLE_SUPPORT_INSERTION_DIRECTION_REFERENCE_ROLE = (
        "DENTOBOT.VisibleSupportInsertionDirection"
    )

    TEMPLATE_PATIENT_SHELL_SCHEMA_VERSION = "1.0"

    TEMPLATE_INSERTION_DIRECTION_SOURCE_SURFACE_REFERENCE_ROLE = (
        "DENTOBOT.InsertionDirectionSourceSurface"
    )

    TEMPLATE_INSERTION_DIRECTION_SOURCE_TRAJECTORY_REFERENCE_ROLE = (
        "DENTOBOT.InsertionDirectionSourceTrajectory"
    )

    TEMPLATE_UNDERCUT_SOURCE_SURFACE_REFERENCE_ROLE = (
        "DENTOBOT.UndercutSourceSurface"
    )

    TEMPLATE_UNDERCUT_SOURCE_ANATOMY_REFERENCE_ROLE = (
        "DENTOBOT.UndercutSourceAnatomy"
    )

    TEMPLATE_UNDERCUT_INSERTION_DIRECTION_REFERENCE_ROLE = (
        "DENTOBOT.UndercutInsertionDirection"
    )

    TEMPLATE_PATIENT_SHELL_BLOCKOUT_REFERENCE_ROLE = (
        "DENTOBOT.PatientShellBlockout"
    )

    TEMPLATE_PATIENT_SHELL_INSERTION_DIRECTION_REFERENCE_ROLE = (
        "DENTOBOT.PatientShellInsertionDirection"
    )

    TEMPLATE_PATIENT_SHELL_SOURCE_SURFACE_REFERENCE_ROLE = (
        "DENTOBOT.PatientShellSourceSurface"
    )

    TEMPLATE_PATIENT_SHELL_SOURCE_ANATOMY_REFERENCE_ROLE = (
        "DENTOBOT.PatientShellSourceAnatomy"
    )

    TEMPLATE_PATIENT_SHELL_FITTING_SURFACE_REFERENCE_ROLE = (
        "DENTOBOT.PatientShellFittingSurface"
    )

    TEMPLATE_PATIENT_SHELL_HOLLOW_CANDIDATE_REFERENCE_ROLE = (
        "DENTOBOT.PatientShellHollowCandidate"
    )

    TEMPLATE_PATIENT_SHELL_BOUNDARY_BRIDGE_REFERENCE_ROLE = (
        "DENTOBOT.PatientShellBoundaryBridge"
    )

    TEMPLATE_PATIENT_SHELL_MARGIN_MODELER_REFERENCE_ROLE = (
        "DENTOBOT.PatientShellMarginDynamicModeler"
    )

    TEMPLATE_PATIENT_SHELL_HOLLOW_MODELER_REFERENCE_ROLE = (
        "DENTOBOT.PatientShellHollowDynamicModeler"
    )

    TEMPLATE_GUIDE_SCHEMA_VERSION = "1.0"

    TARGET_DOCKING_SCHEMA_VERSION = "4.0"

    TARGET_DOCKING_SOURCE_SEGMENTATION_REFERENCE_ROLE = (
        "DENTOBOT.TargetDockingSourceSegmentation"
    )

    TARGET_DOCKING_SOURCE_TRAJECTORY_REFERENCE_ROLE = (
        "DENTOBOT.TargetDockingSourceTrajectory"
    )

    TARGET_DOCKING_SOURCE_SUPPORT_REFERENCE_ROLE = (
        "DENTOBOT.TargetDockingSourceSupportDraft"
    )

    TARGET_DOCKING_REFERENCE_PLANE_REFERENCE_ROLE = (
        "DENTOBOT.TargetDockingReferencePlane"
    )

    TARGET_DOCKING_MEASUREMENT_REFERENCE_ROLE = (
        "DENTOBOT.TargetDockingMeasurement"
    )

    TEMPLATE_SELECTED_GUIDE_TRAJECTORY_REFERENCE_ROLE = (
        "DENTOBOT.SelectedGuideTrajectory"
    )

    TEMPLATE_FINAL_GUIDE_SCHEMA_VERSION = "1.0"

    TEMPLATE_FINAL_GUIDE_PATIENT_SHELL_REFERENCE_ROLE = (
        "DENTOBOT.FinalGuidePatientShell"
    )

    TEMPLATE_FINAL_GUIDE_TARGET_DOCKING_REFERENCE_ROLE = (
        "DENTOBOT.FinalGuideTargetDockingAssembly"
    )

    TEMPLATE_FINAL_GUIDE_DOCKING_REFERENCE_ROLE = (
        "DENTOBOT.FinalGuideDockingAssembly"
    )

    TEMPLATE_FINAL_GUIDE_CLEARANCE_REFERENCE_ROLE = (
        "DENTOBOT.FinalGuideDockingClearance"
    )

    TEMPLATE_FINAL_GUIDE_REINFORCEMENT_REFERENCE_ROLE = (
        "DENTOBOT.FinalGuideReinforcement"
    )

    TEMPLATE_FINAL_GUIDE_CHANNELS_REFERENCE_ROLE = (
        "DENTOBOT.FinalGuideChannels"
    )

    TEMPLATE_FINAL_GUIDE_SOURCE_TRAJECTORY_REFERENCE_ROLE = (
        "DENTOBOT.FinalGuideSourceTrajectory"
    )

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

    TEMPLATE_FINALIZATION_ROI_REFERENCE_ROLE = (
        "DENTOBOT.TemplateFinalizationROI"
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
