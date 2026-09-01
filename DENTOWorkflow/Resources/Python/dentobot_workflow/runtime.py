"""Shared Slicer/runtime imports for mechanically extracted mixins.

Domain modules will tighten these imports after relocation parity.
"""

import colorsys
import hashlib
import json
import logging
import math
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import ctk
import qt
import vtk

import slicer
from slicer import (
    vtkMRMLCrosshairNode,
    vtkMRMLMarkupsClosedCurveNode,
    vtkMRMLMarkupsFiducialNode,
    vtkMRMLMarkupsLineNode,
    vtkMRMLMarkupsPlaneNode,
    vtkMRMLMarkupsROINode,
    vtkMRMLLinearTransformNode,
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
from vtk.util.numpy_support import vtk_to_numpy

_helperDirectory = Path(__file__).resolve().parents[1]
if str(_helperDirectory) not in sys.path:
    sys.path.insert(0, str(_helperDirectory))

DENTOWORKFLOW_MODULE_DIRECTORY = Path(__file__).resolve().parents[3]

from DENTOTemplateGeometry import (
    analyze_surface_undercuts,
    create_hollow_sleeve,
    create_directional_blockout,
    create_research_shell,
    create_support_boundary_bridge,
    estimate_crown_cap_support_plane_normal,
    extract_directional_visible_support_surface,
    insertion_aligned_support_boundary_loop,
    largest_connected_surface_region,
    model_polydata_in_world,
    regularize_patient_contact_shell,
    remove_single_voxel_surface_speckles,
    surface_topology,
    write_stl_atomic,
)
from DENTOGuideGeometry import (
    combine_guide_geometry_sets,
    compute_target_docking_frame,
    create_independent_shell_contact_reinforcements,
    create_multi_trajectory_docking_geometry,
    create_target_frame_docking_geometry,
    evaluate_target_docking_obstacle_clearance,
    filter_tiny_occupied_region_artifacts,
    fuse_shell_and_docking_voxel,
    find_collision_aware_target_docking_yaw,
    normalize_docking_parameters,
    normalize_target_docking_parameters,
    subtract_guide_exclusion,
)
from DENTOCaseBundle import (
    CASE_BUNDLE_EXTENSION,
    CaseBundleError,
    build_robot_profile,
    create_case_bundle,
    extract_scene_mrb,
    lineage_snapshot_matches,
    lineage_snapshot_mismatch_path,
    validate_case_bundle,
)
from DENTOApplicationShell import (
    DENTOApplicationShell,
    GUI_MODE_LEGACY,
    GUI_MODE_SHELL,
    workspace_for_stage,
)
from DENTOViewPresets import (
    ANATOMY_DIMENSION_LABELS,
    ANATOMY_SCOPE_LABELS,
    CBCT_MODE_LABELS,
    DETAILED_ANATOMY_GROUP_CATEGORY,
    DETAILED_ANATOMY_GROUP_LABELS,
    OVERLAY_CATEGORY_MAP,
    OVERLAY_GROUP_LABELS,
    ViewComposition,
    anatomy_scopes_for_group,
    dental_jaw_from_fdi,
    group_segmentation_records_detailed,
    recommended_view_categories,
    recommended_view_composition,
    recommended_view_description,
)
from DENTOTrajectoryGeometry import infer_root_targets
from DENTORobotPlacement import (
    solve_anatomy_directed_hinge_rotation_for_gap,
    validate_patient_ras_condylar_landmarks,
    joint_positions_si_from_display,
    local_nudge_matrix,
    orthonormal_plane_pose,
    robot_link_mesh_poses_mm,
    solve_hinge_rotation_for_gap,
    world_transform_to_parent_local,
    vtk_matrix_elements,
)
from DENTORobotSimulationPanel import DENTORobotSimulationPanel
from DENTORobotWorkflowFacade import DENTORobotWorkflowFacade, PhasePlan
from DENTOROS2Bridge import (
    ROS2_DEFAULT_SLICER_NODE,
    ROS2_MOTION_ACTIVE_ATTRIBUTE,
    ROS2_ROBOT_NAME,
    acknowledge_moveit_collision_scene,
    apply_joint_positions_si_to_motion_control,
    clear_legacy_dentobot_moveit_source_attributes,
    clear_stale_ros2_motion_active_attributes,
    description_stack_running,
    disconnect_dentobot_motion_control,
    connect_dentobot_motion_control,
    ensure_default_ros2_node_in_scene,
    ensure_slicer_ros2_runtime,
    find_ros2_robot_by_name,
    is_ros2_runtime_unavailable_message,
    joint_command_status,
    last_accepted_joint_positions_si,
    mark_slicer_ros2_runtime_nodes_transient,
    plan_moveit_cartesian_path,
    prepare_dentobot_motion_diagnostics,
    release_default_ros2_node_singleton,
    remove_stale_moveit_obstacle_proxies,
    ros2_node_list,
    shutdown_slicer_adapter,
    sync_moveit_obstacle_polydata,
)
from DENTOPlatform import (
    BACKEND_DEVICE_ENVIRONMENT_VARIABLE as PLATFORM_BACKEND_DEVICE_ENVIRONMENT_VARIABLE,
    BACKEND_PYTHON_ENVIRONMENT_VARIABLE as PLATFORM_BACKEND_PYTHON_ENVIRONMENT_VARIABLE,
    EXECUTION_MODE_ENVIRONMENT_VARIABLE,
    RUN_ARTIFACT_ROOT_ENVIRONMENT_VARIABLE as PLATFORM_RUN_ARTIFACT_ROOT_ENVIRONMENT_VARIABLE,
    SUPPORTED_BACKEND_DEVICES,
    SUPPORTED_EXECUTION_MODES,
    WSL_DISTRIBUTION_ENVIRONMENT_VARIABLE as PLATFORM_WSL_DISTRIBUTION_ENVIRONMENT_VARIABLE,
    build_backend_python_command,
    default_execution_mode,
    launcher_backend_configuration,
    windows_path_to_wsl_path,
)
from DENTOStep6Planning import (
    CASE_VIEW_ROLES,
    MotionPlanResult,
    PlanningContextReport,
    TaskJointLimits,
    WorkspaceSampleResult,
    apply_task_joint_limits_to_display_ranges,
    apply_task_limit_range_to_value,
    build_task_joint_limits_from_parameter_values,
    combine_ras_bounds,
    default_task_joint_limits_from_urdf,
    evaluate_motion_configuration,
    plan_trajectory_motion,
    sample_filtered_tcp_workspace,
    sample_trajectory_world_mm,
    step6_motion_plan_robot_ready,
    validate_planning_context,
)
from DENTOStep6State import (
    BasePlacementStatus,
    MANUAL_SIMULATION_BASE_SOURCE,
    MotionPhase,
    QUARANTINED_CIRCULAR_BASE_SOURCE,
    approach_points,
    base_placement_source_issue,
    build_assisted_limit_proposal,
    build_collision_scene_audit,
    build_motion_diagnostic_session,
    build_phase_guard_configuration,
    build_task_home,
    build_task_snapshot,
    canonical_json,
    fingerprint,
    normalize_base_status,
    parse_task_snapshot,
    parse_task_home,
    parse_collision_scene_audit,
    parse_motion_diagnostic_session,
    task_snapshot_invalidation_reasons,
)


class _PublicEntrypointClassProxy:
    """Resolve a public class only when an extracted method actually uses it."""

    def __init__(self, class_name: str) -> None:
        self._class_name = class_name

    def _resolved(self):
        import DENTOWorkflow

        return getattr(DENTOWorkflow, self._class_name)

    def __call__(self, *args, **kwargs):
        return self._resolved()(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._resolved(), name)


DENTOWorkflowLogic = _PublicEntrypointClassProxy("DENTOWorkflowLogic")
DENTOWorkflowParameterNode = _PublicEntrypointClassProxy(
    "DENTOWorkflowParameterNode"
)


__all__ = tuple(
    name for name in globals() if not name.startswith("__")
)
