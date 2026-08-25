"""Slicer-native DENTOWorkflow regression suite.

Imported only through the public DENTOWorkflowTest compatibility class.
"""

import colorsys
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
    MotionPhase,
    approach_points,
    build_assisted_limit_proposal,
    build_phase_guard_configuration,
    build_task_home,
    build_task_snapshot,
    canonical_json,
    fingerprint,
    normalize_base_status,
    parse_task_snapshot,
    parse_task_home,
    task_snapshot_invalidation_reasons,
)


from DENTOWorkflow import DENTOWorkflowLogic, DENTOWorkflowWidget


class DENTOWorkflowTestMixin:
    """Slicer-native tests that do not launch WSL or external inference."""

    def setUp(self) -> None:
        slicer.mrmlScene.Clear(0)

    def runTest(self) -> None:
        testNames = (
            "test_DENTOWorkflowVolumeMetadataAndParameterNode",
            "test_DENTOWorkflowBridgeContracts",
            "test_DENTOWorkflowSegmentationReviewLogic",
            "test_DENTOWorkflowTrajectoryObliqueMprMath",
            "test_DENTOWorkflowAssistedRootTrajectoryGeneration",
            "test_DENTOWorkflowTargetToothAndTrajectoryLogic",
            "test_DENTOWorkflowDraftTemplateSupportModelLogic",
            "test_DENTOWorkflowTemplateSupportBoundaryFocusDisplay",
            "test_DENTOWorkflowDirectionalSupportSideSelection",
            "test_DENTOWorkflowPatientContactShellVoxelFallback",
            "test_DENTOWorkflowTargetDockingBindingPreservesConfirmation",
            "test_DENTOWorkflowTargetDockingYawMath",
            "test_DENTOWorkflowTinyFusionArtifactFiltering",
            "test_DENTOWorkflowVisibleTemplateSupportSurface",
            "test_DENTOWorkflowTemplateFinalizationCameraMath",
            "test_DENTOWorkflowTemplateFinalizationPlaneConstraint",
            "test_DENTOWorkflowTemplateFinalizationDynamicModeler",
            "test_DENTOWorkflowResearchTemplateGeometry",
            "test_DENTOWorkflowSafeDeletionAndPersistence",
            "test_DENTOWorkflowTrajectoryBacktrackingAfterSceneReload",
            "test_DENTOWorkflowWorkflowDisplaySelection",
            "test_DENTOWorkflowWorkflowNavigationWidget",
            "test_DENTOWorkflowRobotPlacementLogic",
            "test_DENTOWorkflowRobotPlacementWidget",
            "test_DENTOWorkflowStep6CaseViewWidget",
            "test_DENTOWorkflowStep6CaseJawOpening",
            "test_DENTOWorkflowStep6NativePlacementPersistence",
            "test_DENTOWorkflowStep6JointLimitSpinboxes",
            "test_DENTOWorkflowViewControlsPaletteWidget",
            "test_DENTOWorkflowUnifiedTemplatePanelLayout",
            "test_DENTOWorkflowCompleteTemplateBuildCaching",
            "test_DENTOWorkflowSceneDisplayPresetWidget",
            "test_DENTOWorkflowSavedSceneAuthoritativeSourceRestoration",
            "test_DENTOWorkflowWorkflowViewSelectorWidget",
            "test_DENTOWorkflowTrajectorySelectionRestoresTargetWidget",
            "test_DENTOWorkflowTemplateReviewGateWidget",
            "test_DENTOWorkflowInsertionAlignedSupportPlaneBoundary",
        )
        try:
            for testName in testNames:
                self.setUp()
                getattr(self, testName)()
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
        self.assertTrue(parameterNode.templateFinalizationViewLocked)
        self.assertFalse(parameterNode.templateFinalizationYawLocked)
        self.assertEqual(parameterNode.templateSupportSelectionMode, "Smallest")
        self.assertFalse(parameterNode.templateSupportDirectionReversed)
        self.assertEqual(parameterNode.trajectoryPlacementMode, "Manual")
        self.assertEqual(parameterNode.sceneDisplayPresetJson, "")
        self.assertAlmostEqual(
            parameterNode.templateSupportCurveSamplingSpacingMm,
            0.5,
        )
        self.assertIsNone(parameterNode.templateSupportBoundaryCurve)
        self.assertIsNone(parameterNode.visibleTemplateSupportModel)
        self.assertIsNone(parameterNode.templateInsertionDirection)
        self.assertIsNone(parameterNode.templateUndercutSurfaceModel)
        self.assertIsNone(parameterNode.templateUndercutBlockoutModel)
        self.assertAlmostEqual(parameterNode.templateUndercutAngleToleranceDeg, 5.0)
        self.assertAlmostEqual(parameterNode.templateBlockoutSafetyMm, 0.1)
        self.assertAlmostEqual(parameterNode.templateShellVoxelClosingMm, 0.3)
        self.assertIsNone(parameterNode.patientContactShellModel)
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
            logic.BACKEND_EXECUTION_MODE_ENVIRONMENT_VARIABLE: "local",
            logic.BACKEND_PYTHON_ENVIRONMENT_VARIABLE: localBackendPython,
            logic.RUN_ARTIFACT_ROOT_ENVIRONMENT_VARIABLE: launcherArtifactRoot,
            logic.BACKEND_DEVICE_ENVIRONMENT_VARIABLE: "cpu",
        }

        self.assertEqual(
            logic.launcherBackendConfiguration(launcherEnvironment),
            (
                "local",
                "",
                localBackendPython,
                launcherArtifactRoot,
                "cpu",
            ),
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
                "",
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
                "wsl",
                "stale-distribution",
                "/stale/python",
                "/stale/runs",
                "cuda:0",
                True,
                {},
            ),
            ("", "", "", "", ""),
        )

        windowsLauncherEnvironment = {
            logic.BACKEND_EXECUTION_MODE_ENVIRONMENT_VARIABLE: "wsl",
            logic.WSL_DISTRIBUTION_ENVIRONMENT_VARIABLE: "Ubuntu-24.04",
            logic.BACKEND_PYTHON_ENVIRONMENT_VARIABLE: (
                "/home/user/miniconda3/envs/dentobot/bin/python"
            ),
            logic.RUN_ARTIFACT_ROOT_ENVIRONMENT_VARIABLE: r"C:\DENTOBOTRuns",
            logic.BACKEND_DEVICE_ENVIRONMENT_VARIABLE: "cuda:0",
        }
        self.assertEqual(
            logic.resolveBackendConfiguration(
                "wsl",
                "manual-distribution",
                "/manual/python",
                r"D:\ManualRuns",
                "cpu",
                True,
                windowsLauncherEnvironment,
            ),
            (
                "wsl",
                "Ubuntu-24.04",
                "/home/user/miniconda3/envs/dentobot/bin/python",
                r"C:\DENTOBOTRuns",
                "cuda:0",
            ),
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
        logic.setScalarVolumeInterpolation(sourceVolume, False)
        self.assertFalse(logic.getScalarVolumeInterpolation(sourceVolume))
        logic.setScalarVolumeInterpolation(sourceVolume, True)
        self.assertTrue(logic.getScalarVolumeInterpolation(sourceVolume))
        sourceVoxelsBeforeDisplayChanges = np.array(
            slicer.util.arrayFromVolume(sourceVolume),
            copy=True,
        )
        logic.setScalarVolumeWindowLevel(sourceVolume, 1200.0, 350.0)
        displayBaseline = logic.getScalarVolumeDisplaySettings(sourceVolume)
        self.assertFalse(displayBaseline["autoWindowLevel"])
        self.assertAlmostEqual(displayBaseline["window"], 1200.0)
        self.assertAlmostEqual(displayBaseline["level"], 350.0)
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            logic.setScalarVolumeWindowLevel(sourceVolume, 0.0, 0.0)
        logic.setScalarVolumeWindowLevel(sourceVolume, 800.0, 100.0)
        logic.setScalarVolumeInvertedGrayscale(sourceVolume, True)
        invertedSettings = logic.getScalarVolumeDisplaySettings(sourceVolume)
        self.assertTrue(invertedSettings["invertedGrayscale"])
        self.assertEqual(
            invertedSettings["colorNodeId"],
            logic.SCALAR_VOLUME_INVERTED_GREY_COLOR_NODE_ID,
        )
        logic.setScalarVolumeAutoWindowLevel(sourceVolume, True)
        self.assertTrue(
            logic.getScalarVolumeDisplaySettings(sourceVolume)[
                "autoWindowLevel"
            ]
        )
        logic.restoreScalarVolumeDisplaySettings(sourceVolume, displayBaseline)
        restoredDisplay = logic.getScalarVolumeDisplaySettings(sourceVolume)
        self.assertEqual(restoredDisplay, displayBaseline)
        self.assertTrue(
            np.array_equal(
                sourceVoxelsBeforeDisplayChanges,
                slicer.util.arrayFromVolume(sourceVolume),
            )
        )

        displayQualityNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "DisplayQualitySegmentation",
        )
        displayQualityNode.CreateDefaultDisplayNodes()
        displayQualitySegment = slicer.vtkSegment()
        displayQualitySegment.SetName("display-quality-test")
        sphereSource = vtk.vtkSphereSource()
        sphereSource.SetRadius(2.0)
        sphereSource.Update()
        displayQualitySegment.AddRepresentation(
            logic.SEGMENTATION_CLOSED_SURFACE_REPRESENTATION,
            sphereSource.GetOutput(),
        )
        displayQualityNode.GetSegmentation().AddSegment(
            displayQualitySegment,
            "display-quality-test",
        )
        self.assertEqual(
            logic.ensureSegmentationDisplayQualityDefaults(displayQualityNode),
            logic.SEGMENTATION_2D_RENDERING_MODE_NATIVE,
        )
        displayQualityDisplayNode = displayQualityNode.GetDisplayNode()
        self.assertEqual(
            displayQualityDisplayNode.GetPreferredDisplayRepresentationName2D(),
            logic.SEGMENTATION_BINARY_LABELMAP_REPRESENTATION,
        )
        logic.setSegmentation2DRenderingMode(
            displayQualityNode,
            logic.SEGMENTATION_2D_RENDERING_MODE_SMOOTH,
        )
        self.assertEqual(
            displayQualityDisplayNode.GetPreferredDisplayRepresentationName2D(),
            logic.SEGMENTATION_CLOSED_SURFACE_REPRESENTATION,
        )
        logic.setSegmentation2DRenderingMode(
            displayQualityNode,
            logic.SEGMENTATION_2D_RENDERING_MODE_NATIVE,
        )
        self.assertEqual(
            logic.getSegmentation2DRenderingMode(displayQualityNode),
            logic.SEGMENTATION_2D_RENDERING_MODE_NATIVE,
        )
        self.assertEqual(
            displayQualityDisplayNode.GetPreferredDisplayRepresentationName2D(),
            logic.SEGMENTATION_BINARY_LABELMAP_REPRESENTATION,
        )
        with self.assertRaisesRegex(ValueError, "rendering mode"):
            logic.setSegmentation2DRenderingMode(displayQualityNode, "invalid")

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
        displayNode.SetPreferredDisplayRepresentationName2D(
            logic.SEGMENTATION_CLOSED_SURFACE_REPRESENTATION
        )
        segmentationNode.SetAttribute(
            logic.SEGMENTATION_2D_RENDERING_MODE_ATTRIBUTE,
            logic.SEGMENTATION_2D_RENDERING_MODE_SMOOTH,
        )
        handoff = logic.beginSegmentationCorrection(
            segmentationNode,
            "tooth-16",
            startedUtc=correctionTimestamp,
        )
        self.assertEqual(handoff["segmentationNode"], segmentationNode)
        self.assertEqual(handoff["sourceVolume"], sourceVolume)
        self.assertEqual(handoff["segmentId"], "tooth-16")
        self.assertEqual(
            handoff["previous2DRenderingMode"],
            logic.SEGMENTATION_2D_RENDERING_MODE_SMOOTH,
        )
        self.assertEqual(
            logic.getSegmentation2DRenderingMode(segmentationNode),
            logic.SEGMENTATION_2D_RENDERING_MODE_NATIVE,
        )
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

    def test_DENTOWorkflowTrajectoryObliqueMprMath(self) -> None:
        frame = DENTOWorkflowLogic.computeTrajectoryFrame(
            (1.0, 2.0, 3.0),
            (4.0, 6.0, 15.0),
        )
        basis = np.column_stack(
            (
                frame["transverseX"],
                frame["transverseY"],
                frame["trajectory"],
            )
        )
        self.assertTrue(np.allclose(basis.T @ basis, np.eye(3), atol=1e-8))
        self.assertAlmostEqual(float(np.linalg.det(basis)), 1.0, places=7)
        self.assertEqual(frame["midpoint"], (2.5, 4.0, 9.0))
        self.assertAlmostEqual(frame["lengthMm"], 13.0, places=7)

        verticalFrame = DENTOWorkflowLogic.computeTrajectoryFrame(
            (10.0, 20.0, 30.0),
            (10.0, 20.0, 50.0),
        )
        self.assertEqual(verticalFrame["reference"], (0.0, 1.0, 0.0))
        self.assertTrue(
            np.allclose(verticalFrame["transverseX"], (1.0, 0.0, 0.0))
        )
        zeroMatrix = DENTOWorkflowLogic.computeTrajectorySliceMatrix(
            verticalFrame["entry"],
            verticalFrame["target"],
            0.0,
        )
        quarterMatrix = DENTOWorkflowLogic.computeTrajectorySliceMatrix(
            verticalFrame["entry"],
            verticalFrame["target"],
            90.0,
        )
        self.assertTrue(
            np.allclose(
                [zeroMatrix.GetElement(row, 1) for row in range(3)],
                (0.0, 0.0, 1.0),
            )
        )
        self.assertTrue(
            np.allclose(
                [zeroMatrix.GetElement(row, 3) for row in range(3)],
                (10.0, 20.0, 40.0),
            )
        )
        self.assertTrue(
            np.allclose(
                [quarterMatrix.GetElement(row, 0) for row in range(3)],
                (0.0, 1.0, 0.0),
                atol=1e-8,
            )
        )
        for matrix in (zeroMatrix, quarterMatrix):
            matrixBasis = np.asarray(
                [
                    [matrix.GetElement(row, column) for column in range(3)]
                    for row in range(3)
                ]
            )
            self.assertTrue(
                np.allclose(matrixBasis.T @ matrixBasis, np.eye(3), atol=1e-8)
            )
            self.assertAlmostEqual(float(np.linalg.det(matrixBasis)), 1.0, places=7)
            normal = matrixBasis[:, 2]
            midpoint = np.asarray(
                [matrix.GetElement(row, 3) for row in range(3)]
            )
            for point in (verticalFrame["entry"], verticalFrame["target"]):
                self.assertAlmostEqual(
                    float(np.dot(np.asarray(point) - midpoint, normal)),
                    0.0,
                    places=7,
                )

        inPlaneTarget = (14.0, 20.0, 50.0)
        transportedMatrix = DENTOWorkflowLogic.transportTrajectorySliceMatrix(
            zeroMatrix,
            verticalFrame["entry"],
            inPlaneTarget,
            0.0,
        )
        previousNormal = np.asarray(
            [zeroMatrix.GetElement(row, 2) for row in range(3)]
        )
        transportedNormal = np.asarray(
            [transportedMatrix.GetElement(row, 2) for row in range(3)]
        )
        self.assertTrue(
            np.allclose(transportedNormal, previousNormal, atol=1e-8)
        )
        self.assertTrue(
            np.allclose(
                [transportedMatrix.GetElement(row, 3) for row in range(3)],
                (12.0, 20.0, 40.0),
                atol=1e-8,
            )
        )

        deltaMatrix = DENTOWorkflowLogic.transportTrajectorySliceMatrix(
            transportedMatrix,
            verticalFrame["entry"],
            inPlaneTarget,
            30.0,
        )
        outOfPlaneMatrix = DENTOWorkflowLogic.transportTrajectorySliceMatrix(
            zeroMatrix,
            verticalFrame["entry"],
            (10.0, 30.0, 50.0),
            0.0,
        )
        singularFallbackMatrix = (
            DENTOWorkflowLogic.transportTrajectorySliceMatrix(
                zeroMatrix,
                verticalFrame["entry"],
                (10.0, 0.0, 30.0),
                0.0,
            )
        )
        for matrix, entry, target in (
            (transportedMatrix, verticalFrame["entry"], inPlaneTarget),
            (deltaMatrix, verticalFrame["entry"], inPlaneTarget),
            (
                outOfPlaneMatrix,
                verticalFrame["entry"],
                (10.0, 30.0, 50.0),
            ),
            (
                singularFallbackMatrix,
                verticalFrame["entry"],
                (10.0, 0.0, 30.0),
            ),
        ):
            transportedBasis = np.asarray(
                [
                    [matrix.GetElement(row, column) for column in range(3)]
                    for row in range(3)
                ]
            )
            self.assertTrue(
                np.allclose(
                    transportedBasis.T @ transportedBasis,
                    np.eye(3),
                    atol=1e-8,
                )
            )
            self.assertAlmostEqual(
                float(np.linalg.det(transportedBasis)),
                1.0,
                places=7,
            )
            midpoint = np.asarray(
                [matrix.GetElement(row, 3) for row in range(3)]
            )
            normal = transportedBasis[:, 2]
            for point in (entry, target):
                self.assertAlmostEqual(
                    float(np.dot(np.asarray(point) - midpoint, normal)),
                    0.0,
                    places=7,
                )
        with self.assertRaisesRegex(ValueError, "non-zero trajectory"):
            DENTOWorkflowLogic.computeTrajectoryFrame((1, 2, 3), (1, 2, 3))
        with self.assertRaisesRegex(ValueError, "rotation must be finite"):
            DENTOWorkflowLogic.computeTrajectorySliceMatrix(
                (0, 0, 0),
                (0, 0, 1),
                float("nan"),
            )
        with self.assertRaisesRegex(ValueError, "rotation delta must be finite"):
            DENTOWorkflowLogic.transportTrajectorySliceMatrix(
                zeroMatrix,
                (0, 0, 0),
                (0, 0, 1),
                float("nan"),
            )
        self.delayDisplay("DENTOWorkflow trajectory oblique-MPR math tests passed")

    def test_DENTOWorkflowAssistedRootTrajectoryGeneration(self) -> None:
        logic = DENTOWorkflowLogic()

        crown = vtk.vtkSphereSource()
        crown.SetThetaResolution(48)
        crown.SetPhiResolution(32)
        crown.Update()
        crownTransform = vtk.vtkTransform()
        crownTransform.Scale(3.0, 2.6, 2.0)
        crownFilter = vtk.vtkTransformPolyDataFilter()
        crownFilter.SetTransform(crownTransform)
        crownFilter.SetInputConnection(crown.GetOutputPort())

        append = vtk.vtkAppendPolyData()
        append.AddInputConnection(crownFilter.GetOutputPort())
        for centerX in (-1.55, 1.55):
            root = vtk.vtkCylinderSource()
            root.SetRadius(0.78)
            root.SetHeight(8.0)
            root.SetResolution(48)
            root.CappingOn()
            transformMatrix = vtk.vtkMatrix4x4()
            transformMatrix.Identity()
            transformMatrix.SetElement(0, 3, centerX)
            transformMatrix.SetElement(1, 1, 0.0)
            transformMatrix.SetElement(1, 2, 1.0)
            transformMatrix.SetElement(2, 1, 1.0)
            transformMatrix.SetElement(2, 2, 0.0)
            transformMatrix.SetElement(2, 3, 5.5)
            rootTransform = vtk.vtkTransform()
            rootTransform.SetMatrix(transformMatrix)
            rootFilter = vtk.vtkTransformPolyDataFilter()
            rootFilter.SetTransform(rootTransform)
            rootFilter.SetInputConnection(root.GetOutputPort())
            append.AddInputConnection(rootFilter.GetOutputPort())
        append.Update()

        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "AssistedTrajectorySegmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        segment = slicer.vtkSegment()
        segment.SetName("upper_right_first_molar_fdi16")
        segment.AddRepresentation(
            slicer.vtkSegmentationConverter
            .GetSegmentationClosedSurfaceRepresentationName(),
            append.GetOutput(),
        )
        segmentationNode.GetSegmentation().AddSegment(segment, "tooth-16")
        adjacentSegment = slicer.vtkSegment()
        adjacentSegment.SetName("upper_right_second_premolar_fdi15")
        adjacentSegment.AddRepresentation(
            slicer.vtkSegmentationConverter
            .GetSegmentationClosedSurfaceRepresentationName(),
            crownFilter.GetOutput(),
        )
        segmentationNode.GetSegmentation().AddSegment(
            adjacentSegment,
            "tooth-15",
        )
        logic.setSegmentationReviewState(segmentationNode, "Reviewed")
        targetBoundsRoi, _bounds = logic.createOrUpdateTargetBoundsRoi(
            segmentationNode,
            "tooth-16",
        )
        segmentationDisplay = segmentationNode.GetDisplayNode()
        segmentationDisplay.SetSegmentVisibility("tooth-16", False)
        segmentationDisplay.SetSegmentVisibility("tooth-15", True)
        targetBoundsRoi.GetDisplayNode().SetVisibility(False)
        focusState = logic.applyTargetToothFocus(
            segmentationNode,
            "tooth-16",
            targetBoundsRoi,
        )
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("tooth-16"))
        self.assertFalse(segmentationDisplay.GetSegmentVisibility("tooth-15"))
        self.assertTrue(targetBoundsRoi.GetDisplayNode().GetVisibility())
        logic.restoreTargetToothFocus(focusState)
        self.assertFalse(segmentationDisplay.GetSegmentVisibility("tooth-16"))
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("tooth-15"))
        self.assertFalse(targetBoundsRoi.GetDisplayNode().GetVisibility())

        entryNode, emptySummary = logic.createOrResetAssistedTrajectoryEntries(
            segmentationNode,
            "tooth-16",
            2,
        )
        self.assertTrue(logic.isAssistedTrajectoryEntryNode(entryNode))
        self.assertEqual(emptySummary["expectedCount"], 2)
        self.assertFalse(emptySummary["isComplete"])
        entryNode.AddControlPointWorld(vtk.vtkVector3d(-1.35, 0.0, -0.8))
        entryNode.AddControlPointWorld(vtk.vtkVector3d(1.35, 0.0, -0.8))
        entrySummary = logic.validateAssistedTrajectoryEntryAssociation(
            entryNode,
            segmentationNode,
            "tooth-16",
            2,
        )
        self.assertTrue(entrySummary["isComplete"])
        self.assertEqual(entryNode.GetNthControlPointLabel(0), "Entry 1")
        self.assertEqual(entryNode.GetNthControlPointLabel(1), "Entry 2")

        trajectories, analysis = logic.generateAssistedTrajectories(
            entryNode,
            segmentationNode,
            "tooth-16",
            2,
            targetBoundsRoi,
        )
        self.assertEqual(len(trajectories), 2)
        self.assertEqual(analysis["rootCount"], 2)
        self.assertGreater(analysis["rootSeparationMm"], 1.0)
        self.assertTrue(entryNode.GetLocked())
        for index, trajectoryNode in enumerate(trajectories):
            summary = logic.getTrajectorySummary(trajectoryNode)
            self.assertTrue(summary["isValid"])
            self.assertGreater(summary["targetRas"][2], summary["entryRas"][2])
            self.assertEqual(
                trajectoryNode.GetAttribute("DENTOBOT.AssistedRootOrdinal"),
                str(index + 1),
            )
            self.assertEqual(
                trajectoryNode.GetAttribute("DENTOBOT.AssistedTargetState"),
                "RequiresManualVerification",
            )
            self.assertIs(
                trajectoryNode.GetNodeReference(
                    logic.ASSISTED_TRAJECTORY_ENTRY_REFERENCE_ROLE
                ),
                entryNode,
            )
            self.assertIs(
                trajectoryNode.GetNodeReference(
                    logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE
                ),
                targetBoundsRoi,
            )
            self.assertFalse(trajectoryNode.GetLocked())
        self.assertLess(
            logic.getTrajectorySummary(trajectories[0])["targetRas"][0],
            logic.getTrajectorySummary(trajectories[1])["targetRas"][0],
        )

        with self.assertRaisesRegex(ValueError, "already has"):
            logic.generateAssistedTrajectories(
                entryNode,
                segmentationNode,
                "tooth-16",
                2,
                targetBoundsRoi,
            )

        parameterNode = logic.getParameterNode()
        parameterNode.teethSegmentation = segmentationNode
        parameterNode.targetToothSegmentId = "tooth-16"
        parameterNode.assistedTrajectoryEntries = entryNode
        parameterNode.assistedTrajectoryCount = 2
        parameterNode.trajectoryLine = trajectories[0]
        scenePath = Path(slicer.app.temporaryPath) / (
            f"dentobot-assisted-trajectories-{uuid.uuid4().hex}.mrb"
        )
        try:
            self.assertTrue(slicer.util.saveScene(str(scenePath)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(scenePath)))
        finally:
            scenePath.unlink(missing_ok=True)
        reloadedLogic = DENTOWorkflowLogic()
        reloadedParameterNode = reloadedLogic.getParameterNode()
        self.assertEqual(reloadedParameterNode.assistedTrajectoryCount, 2)
        self.assertTrue(
            reloadedLogic.isAssistedTrajectoryEntryNode(
                reloadedParameterNode.assistedTrajectoryEntries
            )
        )
        self.assertEqual(
            len(
                reloadedLogic.dentobotTrajectoriesForTarget(
                    reloadedParameterNode.teethSegmentation,
                    "tooth-16",
                )
            ),
            2,
        )
        self.delayDisplay("DENTOWorkflow assisted root-trajectory tests passed")

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

    def test_DENTOWorkflowWorkflowNavigationWidget(self) -> None:
        slicer.mrmlScene.Clear(0)
        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()

        self.assertEqual(widget.ui.workflowStageComboBox.count, 11)
        self.assertEqual(widget._recommendedWorkflowStageIndex(), 0)
        self.assertEqual(widget.ui.workflowStageComboBox.currentIndex, 0)
        self.assertFalse(widget.ui.caseCollapsibleButton.collapsed)
        self.assertTrue(widget.ui.imagingCollapsibleButton.collapsed)
        self.assertFalse(widget.ui.caseCollapsibleButton.isHidden())
        self.assertTrue(widget.ui.imagingCollapsibleButton.isHidden())
        self.assertEqual(
            sum(
                not section.isHidden()
                for _label, section in widget._workflowStageEntries()
            ),
            1,
        )
        self.assertIn("Case", widget.ui.workflowStageStatusLabel.toolTip)
        widget._parameterNode.caseName = "NavigationTestCase"
        self.assertEqual(widget._recommendedWorkflowStageIndex(), 1)
        widget._parameterNode.caseName = ""
        widget._setWorkflowStage(4, ensureVisible=False)
        self.assertEqual(widget.ui.workflowStageComboBox.currentIndex, 4)
        self.assertFalse(widget.ui.planningCollapsibleButton.collapsed)
        self.assertFalse(widget.ui.planningCollapsibleButton.isHidden())
        self.assertTrue(widget.ui.caseCollapsibleButton.isHidden())
        self.assertTrue(
            widget._viewControlsTabWidget.isTabEnabled(
                widget._viewControlsElementsTabIndex
            )
        )
        self.assertTrue(widget.ui.assistedTrajectoryCollapsibleButton.isHidden())
        self.assertEqual(widget._trajectoryPlacementMode(), "Manual")
        widget.ui.trajectoryPlacementModeComboBox.currentIndex = 1
        slicer.app.processEvents()
        self.assertEqual(widget._trajectoryPlacementMode(), "Assisted")
        self.assertFalse(widget.ui.assistedTrajectoryCollapsibleButton.isHidden())
        self.assertFalse(widget.ui.assistedTrajectoryCollapsibleButton.collapsed)
        self.assertTrue(widget.ui.createTrajectoryButton.isHidden())
        widget.ui.trajectoryPlacementModeComboBox.currentIndex = 0
        slicer.app.processEvents()
        self.assertTrue(widget.ui.assistedTrajectoryCollapsibleButton.isHidden())
        self.assertFalse(widget.ui.createTrajectoryButton.isHidden())
        self.assertIsNotNone(widget._workflowContentScrollArea)
        self.assertIs(
            widget.ui.workflowNavigationGroupBox.parentWidget(),
            widget._uiWidget,
        )
        self.assertIsNot(
            widget.ui.planningCollapsibleButton.parentWidget(),
            widget._uiWidget,
        )
        self.assertTrue(
            all(
                section.collapsed and section.isHidden()
                for index, (_label, section) in enumerate(
                    widget._workflowStageEntries()
                )
                if index != 4
            )
        )
        self.assertIs(
            widget.ui.metadataGroupBox.parentWidget(),
            widget.ui.imagingCollapsibleButton,
        )
        self.assertTrue(widget.ui.workflowViewGroupBox.isHidden())
        self.assertIsNotNone(widget._viewControlsPalette)
        self.assertEqual(widget._viewControlsTabWidget.count, 2)
        self.assertEqual(
            widget._viewControlsTabWidget.tabText(
                widget._viewControlsElementsTabIndex
            ),
            "Elements",
        )
        self.assertEqual(
            widget._viewControlsTabWidget.tabText(
                widget._viewControlsDisplayTabIndex
            ),
            "Display",
        )
        widget._uiWidget.resize(405, 650)
        slicer.app.processEvents()
        self.assertLessEqual(
            widget._guidanceToolButton.x + widget._guidanceToolButton.width,
            widget.ui.workflowNavigationGroupBox.width,
        )
        self.assertLessEqual(
            widget.ui.workflowNavigationGroupBox.height,
            90,
        )
        widget.ui.showGuidanceCheckBox.checked = True
        self.assertFalse(widget.ui.planningDescriptionLabel.isHidden())
        widget.ui.showGuidanceCheckBox.checked = False
        self.assertTrue(widget.ui.planningDescriptionLabel.isHidden())
        widget.ui.showBackendLogCheckBox.checked = True
        self.assertFalse(widget.ui.backendLogTextEdit.isHidden())
        widget.ui.showBackendLogCheckBox.checked = False
        self.assertTrue(widget.ui.backendLogTextEdit.isHidden())
        self.assertTrue(widget.ui.metadataGroupBox.collapsed)
        self.assertTrue(widget.ui.selectedSegmentDetailsGroupBox.collapsed)
        self.assertTrue(widget.ui.segmentationProvenanceGroupBox.collapsed)
        self.assertTrue(widget.ui.planningSummaryGroupBox.collapsed)
        self.assertTrue(widget.ui.trajectoryVerificationGroupBox.collapsed)
        self.assertTrue(widget.ui.patientContactShellGroupBox.collapsed)
        self.assertFalse(widget.ui.templateDockingFusionGroupBox.collapsed)
        self.assertTrue(widget.ui.templateGuideVisibilityGroupBox.collapsed)

        widget._setWorkflowStage(5, ensureVisible=False)
        self.assertEqual(widget.ui.workflowStageComboBox.currentIndex, 5)
        self.assertFalse(widget.ui.templateModelingCollapsibleButton.collapsed)
        self.assertTrue(widget.ui.templateSupportTeethListWidget.isHidden())
        self.assertFalse(widget._templateSupportArchWidget.isHidden())
        self.assertTrue(widget._templateSupportPackageWidget.isHidden())
        self.assertGreaterEqual(widget._templateSupportArchWidget.minimumHeight, 178)
        self.assertTrue(widget.ui.createTemplateSupportPlaneButton.isHidden())
        widget._setWorkflowStage(7, ensureVisible=False)
        self.assertTrue(widget.ui.templateSupportTeethListWidget.isHidden())
        self.assertTrue(widget._templateSupportArchWidget.isHidden())
        self.assertFalse(widget._templateSupportPackageWidget.isHidden())
        self.assertTrue(widget.ui.draftTemplateSupportModelSelector.isHidden())
        self.assertFalse(widget.ui.createTemplateSupportPlaneButton.isHidden())
        widget.onReturnToStep4BSupportSelection()
        self.assertEqual(widget.ui.workflowStageComboBox.currentIndex, 5)
        self.assertFalse(widget._templateSupportArchWidget.isHidden())
        self.assertTrue(widget.ui.planningCollapsibleButton.collapsed)
        self.assertTrue(widget.ui.planningCollapsibleButton.isHidden())
        self.assertTrue(widget.ui.assistedTrajectoryCollapsibleButton.isHidden())
        widget._setWorkflowStage(0, ensureVisible=False)
        self.assertTrue(
            widget._viewControlsTabWidget.isTabEnabled(
                widget._viewControlsElementsTabIndex
            )
        )
        self.assertTrue(
            widget._viewControlsTabWidget.isTabEnabled(
                widget._viewControlsDisplayTabIndex
            )
        )

        self.delayDisplay("DENTOWorkflow compact workflow navigation test passed")

    def test_DENTOWorkflowViewControlsPaletteWidget(self) -> None:
        """The nonmodal palette must reuse controls and remember workstation state."""

        slicer.mrmlScene.Clear(0)
        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()
        settings = widget._viewControlsSettings()
        visibleKey = widget.VIEW_CONTROLS_VISIBLE_SETTING
        geometryKey = widget.VIEW_CONTROLS_GEOMETRY_SETTING
        hadVisible = bool(settings.contains(visibleKey))
        hadGeometry = bool(settings.contains(geometryKey))
        oldVisible = settings.value(visibleKey) if hadVisible else None
        oldGeometry = settings.value(geometryKey) if hadGeometry else None
        elementsParent = widget.ui.workflowViewElementsListWidget.parentWidget()
        displayParent = widget.ui.segmentation2DOpacitySlider.parentWidget()
        try:
            settings.setValue(visibleKey, False)
            widget._viewControlsPaletteDesiredVisible = False
            widget._viewControlsPalette.resize(471, 531)
            widget.onOpenViewControlsPalette()
            slicer.app.processEvents()
            self.assertTrue(widget._viewControlsPalette.isVisible())
            self.assertFalse(widget._viewControlsPalette.modal)
            self.assertTrue(widget._viewControlsPaletteDesiredVisible)
            self.assertTrue(widget._viewControlsSettingBool(visibleKey, False))
            self.assertIs(
                widget.ui.workflowViewElementsListWidget.parentWidget(),
                elementsParent,
            )
            self.assertIs(
                widget.ui.segmentation2DOpacitySlider.parentWidget(),
                displayParent,
            )

            widget._hideViewControlsPalette(preservePreference=True)
            self.assertFalse(widget._viewControlsPalette.isVisible())
            self.assertTrue(widget._viewControlsSettingBool(visibleKey, False))
            self.assertTrue(settings.contains(geometryKey))
            widget._restoreViewControlsPaletteOnEnter()
            slicer.app.processEvents()
            self.assertTrue(widget._viewControlsPalette.isVisible())

            widget._viewControlsPalette.hide()
            widget.onViewControlsPaletteFinished()
            self.assertFalse(widget._viewControlsSettingBool(visibleKey, True))
            self.assertFalse(widget._viewControlsPaletteDesiredVisible)
        finally:
            widget._viewControlsPalette.hide()
            if hadVisible:
                settings.setValue(visibleKey, oldVisible)
            else:
                settings.remove(visibleKey)
            if hadGeometry:
                settings.setValue(geometryKey, oldGeometry)
            else:
                settings.remove(geometryKey)
            settings.sync()

        self.delayDisplay("DENTOWorkflow floating view palette test passed")

    def test_DENTOWorkflowSceneDisplayPresetWidget(self) -> None:
        """Palette sliders and the case preset must remain MRML-scene state."""

        slicer.mrmlScene.Clear(0)
        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()
        logic = widget.logic

        imageData = vtk.vtkImageData()
        imageData.SetDimensions(4, 4, 4)
        imageData.AllocateScalars(vtk.VTK_SHORT, 1)
        imageData.GetPointData().GetScalars().FillComponent(0, 42)
        volumeNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode",
            "DisplayPresetCBCT",
        )
        volumeNode.SetAndObserveImageData(imageData)
        volumeNode.CreateDefaultDisplayNodes()
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "DisplayPresetSegmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        cube = vtk.vtkCubeSource()
        cube.Update()
        segment = slicer.vtkSegment()
        segment.SetName("upper_right_first_premolar_fdi14")
        segment.AddRepresentation(
            slicer.vtkSegmentationConverter
            .GetSegmentationClosedSurfaceRepresentationName(),
            cube.GetOutput(),
        )
        segmentationNode.GetSegmentation().AddSegment(segment, "tooth-14")
        segmentationNode.SetNodeReferenceID(
            logic.SOURCE_VOLUME_REFERENCE_ROLE,
            volumeNode.GetID(),
        )
        segmentationNode.SetAttribute("DENTOBOT.SourceVolumeID", volumeNode.GetID())

        parameterNode = logic.getParameterNode()
        parameterNode.inputVolume = volumeNode
        parameterNode.teethSegmentation = segmentationNode
        widget.setParameterNode(parameterNode)
        logic.setSegmentationOpacity2D(segmentationNode, 0.37)
        logic.setSegmentationOpacity3D(segmentationNode, 0.61)
        logic.setScalarVolumeWindowLevel(volumeNode, 800.0, 350.0)
        logic.setScalarVolumeInvertedGrayscale(volumeNode, True)
        logic.setScalarVolumeInterpolation(volumeNode, False)
        widget._syncSegmentationDisplayControls()
        self.assertTrue(widget.ui.cbctWindowSpinBox.isHidden())
        self.assertTrue(widget.ui.cbctLevelSpinBox.isHidden())
        self.assertEqual(widget._cbctWindowSlider.value, 8000)
        self.assertEqual(widget._cbctLevelSlider.value, 3500)

        widget.onSaveSceneDisplayPreset()
        savedPresetJson = parameterNode.sceneDisplayPresetJson
        self.assertTrue(savedPresetJson)
        savedPreset = json.loads(savedPresetJson)
        self.assertEqual(savedPreset["version"], 2)
        self.assertNotIn("segmentationNodeId", savedPreset)
        self.assertNotIn("volumeNodeId", savedPreset)
        logic.setSegmentationOpacity2D(segmentationNode, 0.9)
        logic.setSegmentationOpacity3D(segmentationNode, 0.2)
        logic.setScalarVolumeWindowLevel(volumeNode, 1200.0, 600.0)
        logic.setScalarVolumeInvertedGrayscale(volumeNode, False)
        logic.setScalarVolumeInterpolation(volumeNode, True)
        widget.onApplySceneDisplayPreset()
        segmentationDisplay = segmentationNode.GetDisplayNode()
        restoredVolumeDisplay = logic.getScalarVolumeDisplaySettings(volumeNode)
        self.assertAlmostEqual(segmentationDisplay.GetOpacity2DFill(), 0.37)
        self.assertAlmostEqual(segmentationDisplay.GetOpacity3D(), 0.61)
        self.assertAlmostEqual(restoredVolumeDisplay["window"], 800.0)
        self.assertAlmostEqual(restoredVolumeDisplay["level"], 350.0)
        self.assertTrue(restoredVolumeDisplay["invertedGrayscale"])
        self.assertFalse(restoredVolumeDisplay["interpolate"])

        scenePath = Path(slicer.app.temporaryPath) / (
            f"dentobot-display-preset-{uuid.uuid4().hex}.mrb"
        )
        try:
            self.assertTrue(slicer.util.saveScene(str(scenePath)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(scenePath)))
            reloadedPreset = DENTOWorkflowLogic().getParameterNode()
            self.assertEqual(reloadedPreset.sceneDisplayPresetJson, savedPresetJson)
        finally:
            scenePath.unlink(missing_ok=True)

        self.delayDisplay("DENTOWorkflow scene display preset test passed")

    def test_DENTOWorkflowUnifiedTemplatePanelLayout(self) -> None:
        """Keep every Step 5B input before result and action controls."""

        slicer.mrmlScene.Clear(0)
        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()
        widget._setWorkflowStage(8, ensureVisible=False)
        slicer.app.processEvents()

        layout = widget.ui.templateGuideVerticalLayout
        orderedWidgets = (
            widget._unifiedTemplateReadinessGroup,
            widget._unifiedTemplateInputsGroup,
            widget.ui.patientContactShellGroupBox,
            widget.ui.templateDockingFusionGroupBox,
            widget._unifiedTemplateActionGroup,
        )
        indices = [layout.indexOf(item) for item in orderedWidgets]
        self.assertEqual(indices, sorted(indices))
        self.assertTrue(all(index >= 0 for index in indices))
        self.assertTrue(widget.ui.patientContactShellGroupBox.collapsed)
        self.assertFalse(widget.ui.templateDockingFusionGroupBox.collapsed)
        self.assertIs(
            widget.ui.generateFinalPrintableTemplateButton.parent(),
            widget._unifiedTemplateActionGroup,
        )
        self.assertIs(
            widget.ui.deleteFinalPrintableTemplateButton.parent(),
            widget._unifiedTemplateActionGroup,
        )
        self.assertEqual(
            widget.ui.generateFinalPrintableTemplateButton.text,
            "Build / Update Unified Template",
        )
        for spinBox in (
            widget.ui.templateShellClearanceSpinBox,
            widget.ui.templateShellThicknessSpinBox,
            widget.ui.templateSamplingSpacingSpinBox,
            widget.ui.templateSleeveOuterDiameterSpinBox,
            widget.ui.templateSleeveInnerDiameterSpinBox,
            widget.ui.templateSleeveHeightSpinBox,
            widget.ui.templateDockingClearanceSpinBox,
            widget.ui.templateReinforcementRadialSpinBox,
            widget.ui.templateReinforcementDepthSpinBox,
        ):
            self.assertTrue(
                widget._unifiedTemplateInputsGroup.isAncestorOf(spinBox)
            )
        self.delayDisplay("DENTOWorkflow unified-template panel layout test passed")

    def test_DENTOWorkflowCompleteTemplateBuildCaching(self) -> None:
        """Complete build and inspection must reuse current expensive stages."""

        slicer.mrmlScene.Clear(0)
        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()
        shellNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Cached shell",
        )
        shellNode.SetAttribute("DENTOBOT.UpdatedUtc", "cached-shell-timestamp")
        blockoutNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Cached blockout",
        )
        finalNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Cached final template",
        )
        widget._parameterNode.patientContactShellModel = shellNode
        widget._parameterNode.templateUndercutBlockoutModel = blockoutNode
        widget._parameterNode.finalPrintableTemplateModel = finalNode

        states = {"blockout": "Current", "shell": "Current", "final": "Current"}
        generated = []
        inspected = []
        originalMethods = {
            "preflight": widget._completeTemplateBuildPreflight,
            "updateGuide": widget._updateTemplateGuide,
            "updateFinalization": widget._updateTemplateFinalization,
            "undercuts": widget._createOrUpdateTemplateUndercuts,
            "shell": widget._createOrUpdatePatientContactShell,
            "final": widget._createOrUpdateFinalPrintableTemplate,
            "preset": widget._applyWorkflowViewPreset,
            "frame": widget.onFrameWorkflowView,
            "blockoutSummary": widget.logic.getTemplateUndercutOutputSummary,
            "shellSummary": widget.logic.getPatientContactShellSummary,
            "finalSummary": widget.logic.getFinalPrintableTemplateSummary,
        }
        try:
            widget._completeTemplateBuildPreflight = lambda: {}
            widget._updateTemplateGuide = lambda: None
            widget._updateTemplateFinalization = lambda: None
            widget._createOrUpdateTemplateUndercuts = lambda: generated.append(
                "blockout"
            )
            widget._createOrUpdatePatientContactShell = lambda: generated.append(
                "shell"
            )
            widget._createOrUpdateFinalPrintableTemplate = lambda: generated.append(
                "final"
            )
            widget._applyWorkflowViewPreset = lambda key, **kwargs: inspected.append(
                key
            )
            widget.onFrameWorkflowView = lambda checked=False: None
            widget.logic.getTemplateUndercutOutputSummary = (
                lambda node, role: {"geometryState": states["blockout"]}
            )
            widget.logic.getPatientContactShellSummary = (
                lambda node: {"geometryState": states["shell"]}
            )
            widget.logic.getFinalPrintableTemplateSummary = (
                lambda node: {"geometryState": states["final"]}
            )

            widget.onBuildOrUpdateCompleteTemplate()
            self.assertEqual(generated, [])
            self.assertEqual(
                shellNode.GetAttribute("DENTOBOT.UpdatedUtc"),
                "cached-shell-timestamp",
            )
            self.assertIn("Reused", widget.ui.templateDockingFusionStatusLabel.text)

            states["final"] = "Stale"
            widget.onBuildOrUpdateCompleteTemplate()
            self.assertEqual(generated, ["final"])
            self.assertEqual(
                shellNode.GetAttribute("DENTOBOT.UpdatedUtc"),
                "cached-shell-timestamp",
            )

            inspected.clear()
            widget.onInspectTemplateFit()
            widget.onInspectShellAndGuides()
            widget.onInspectUnifiedTemplate()
            self.assertEqual(
                inspected,
                ["undercut_analysis", "shell_guides", "final_only"],
            )
            self.assertEqual(generated, ["final"])
        finally:
            widget._completeTemplateBuildPreflight = originalMethods["preflight"]
            widget._updateTemplateGuide = originalMethods["updateGuide"]
            widget._updateTemplateFinalization = originalMethods[
                "updateFinalization"
            ]
            widget._createOrUpdateTemplateUndercuts = originalMethods[
                "undercuts"
            ]
            widget._createOrUpdatePatientContactShell = originalMethods["shell"]
            widget._createOrUpdateFinalPrintableTemplate = originalMethods["final"]
            widget._applyWorkflowViewPreset = originalMethods["preset"]
            widget.onFrameWorkflowView = originalMethods["frame"]
            widget.logic.getTemplateUndercutOutputSummary = originalMethods[
                "blockoutSummary"
            ]
            widget.logic.getPatientContactShellSummary = originalMethods[
                "shellSummary"
            ]
            widget.logic.getFinalPrintableTemplateSummary = originalMethods[
                "finalSummary"
            ]

        self.delayDisplay("DENTOWorkflow cached complete-template build test passed")

    def test_DENTOWorkflowSavedSceneAuthoritativeSourceRestoration(self) -> None:
        """Scene reload must retain workflow refs and restore the matching CBCT."""

        slicer.mrmlScene.Clear(0)
        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()
        logic = widget.logic

        def addVolume(name: str, fillValue: int):
            imageData = vtk.vtkImageData()
            imageData.SetDimensions(8, 8, 8)
            imageData.AllocateScalars(vtk.VTK_SHORT, 1)
            imageData.GetPointData().GetScalars().FillComponent(0, fillValue)
            volumeNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLScalarVolumeNode",
                name,
            )
            volumeNode.SetAndObserveImageData(imageData)
            volumeNode.CreateDefaultDisplayNodes()
            return volumeNode

        def addSegmentation(name: str, sourceVolume, segmentId: str):
            segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLSegmentationNode",
                name,
            )
            segmentationNode.CreateDefaultDisplayNodes()
            cube = vtk.vtkCubeSource()
            cube.SetBounds(-1.0, 1.0, -1.0, 1.0, -2.0, 2.0)
            cube.Update()
            segment = slicer.vtkSegment()
            segment.SetName("upper_right_first_premolar_fdi14")
            segment.AddRepresentation(
                slicer.vtkSegmentationConverter
                .GetSegmentationClosedSurfaceRepresentationName(),
                cube.GetOutput(),
            )
            segmentationNode.GetSegmentation().AddSegment(segment, segmentId)
            segmentationNode.SetAttribute(
                "DENTOBOT.BridgeOperation",
                "segment-teeth",
            )
            segmentationNode.SetNodeReferenceID(
                logic.SOURCE_VOLUME_REFERENCE_ROLE,
                sourceVolume.GetID(),
            )
            segmentationNode.SetAttribute(
                "DENTOBOT.SourceVolumeID",
                sourceVolume.GetID(),
            )
            return segmentationNode

        sourceVolume = addVolume("AuthoritativeSource", 10)
        unrelatedVolume = addVolume("UnrelatedComparison", 20)
        authoritativeSegmentation = addSegmentation(
            "AuthoritativeSegmentation",
            sourceVolume,
            "tooth-14",
        )
        unrelatedSegmentation = addSegmentation(
            "UnrelatedSegmentation",
            unrelatedVolume,
            "other-tooth-14",
        )
        trajectoryNode = logic.createTrajectoryNode("Persisted trajectory")
        logic.configureTrajectoryTarget(
            trajectoryNode,
            authoritativeSegmentation,
            "tooth-14",
        )
        trajectoryNode.AddControlPointWorld(vtk.vtkVector3d(0.0, 0.0, 2.0))
        trajectoryNode.AddControlPointWorld(vtk.vtkVector3d(0.0, 0.0, -2.0))

        parameterNode = logic.getParameterNode()
        parameterNode.inputVolume = unrelatedVolume
        parameterNode.teethSegmentation = authoritativeSegmentation
        parameterNode.targetToothSegmentId = "tooth-14"
        parameterNode.trajectoryLine = trajectoryNode
        widget.setParameterNode(parameterNode)
        widget._reconcileAuthoritativeSegmentationSourceVolume()
        self.assertIs(parameterNode.inputVolume, sourceVolume)
        self.assertEqual(parameterNode.targetToothSegmentId, "tooth-14")
        self.assertIs(parameterNode.trajectoryLine, trajectoryNode)

        sourceVolumeId = sourceVolume.GetID()
        segmentationId = authoritativeSegmentation.GetID()
        trajectoryId = trajectoryNode.GetID()
        scenePath = Path(slicer.app.temporaryPath) / (
            f"dentobot-authoritative-reload-{uuid.uuid4().hex}.mrb"
        )
        try:
            self.assertTrue(slicer.util.saveScene(str(scenePath)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(scenePath)))
            widget.initializeParameterNode()
            restored = widget._parameterNode
            self.assertEqual(restored.inputVolume.GetID(), sourceVolumeId)
            self.assertEqual(restored.teethSegmentation.GetID(), segmentationId)
            self.assertEqual(restored.targetToothSegmentId, "tooth-14")
            self.assertEqual(restored.trajectoryLine.GetID(), trajectoryId)

            widget.onReviewSegmentationSelectionChanged(
                slicer.util.getNode("UnrelatedSegmentation")
            )
            self.assertEqual(
                restored.inputVolume.GetName(),
                "UnrelatedComparison",
            )
            self.assertEqual(restored.targetToothSegmentId, "")
        finally:
            scenePath.unlink(missing_ok=True)

        self.delayDisplay(
            "DENTOWorkflow authoritative source and saved-scene restoration test passed"
        )

    def test_DENTOWorkflowWorkflowDisplaySelection(self) -> None:
        """Display filtering must be exact, reversible, and geometry-neutral."""

        slicer.mrmlScene.Clear(0)
        logic = DENTOWorkflowLogic()
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "Workflow display segmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        for segmentId, centerX in (
            ("target", 0.0),
            ("support", 4.0),
            ("other", 8.0),
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
            segment.SetName(segmentId)
            segment.AddRepresentation(
                slicer.vtkSegmentationConverter
                .GetSegmentationClosedSurfaceRepresentationName(),
                cube.GetOutput(),
            )
            segmentationNode.GetSegmentation().AddSegment(segment, segmentId)

        boundsNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsROINode",
            "Workflow display bounds",
        )
        boundsNode.CreateDefaultDisplayNodes()
        shellNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Workflow display shell",
        )
        shellSource = vtk.vtkCubeSource()
        shellSource.Update()
        shellNode.SetAndObservePolyData(shellSource.GetOutput())
        shellNode.CreateDefaultDisplayNodes()

        segmentationDisplay = segmentationNode.GetDisplayNode()
        segmentationDisplay.SetVisibility(True)
        segmentationDisplay.SetVisibility2D(True)
        segmentationDisplay.SetVisibility3D(True)
        segmentationDisplay.SetSegmentVisibility("target", False)
        segmentationDisplay.SetSegmentVisibility("support", True)
        segmentationDisplay.SetSegmentVisibility("other", True)
        segmentationDisplay.SetSegmentOpacity3D("support", 0.42)
        boundsNode.GetDisplayNode().SetVisibility(True)
        shellNode.GetDisplayNode().SetVisibility(False)
        snapshot = logic.captureWorkflowDisplayState(
            segmentationNode,
            [boundsNode, shellNode],
        )

        targetResult = logic.applyWorkflowDisplaySelection(
            segmentationNode,
            {"target"},
            [boundsNode, shellNode],
            {boundsNode.GetID()},
        )
        self.assertEqual(targetResult["visibleSegmentIds"], ["target"])
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("target"))
        self.assertFalse(segmentationDisplay.GetSegmentVisibility("support"))
        self.assertFalse(segmentationDisplay.GetSegmentVisibility("other"))
        self.assertTrue(boundsNode.GetDisplayNode().GetVisibility())
        self.assertFalse(shellNode.GetDisplayNode().GetVisibility())
        self.assertEqual(
            logic.getSegmentationSegmentBoundsWorld(
                segmentationNode,
                "support",
            ),
            (3.0, 5.0, -1.0, 1.0, -1.0, 1.0),
        )

        logic.applyWorkflowDisplaySelection(
            segmentationNode,
            set(),
            [boundsNode, shellNode],
            {shellNode.GetID()},
        )
        self.assertFalse(segmentationDisplay.GetVisibility())
        self.assertFalse(boundsNode.GetDisplayNode().GetVisibility())
        self.assertTrue(shellNode.GetDisplayNode().GetVisibility())

        logic.restoreWorkflowDisplayState(snapshot)
        self.assertTrue(segmentationDisplay.GetVisibility())
        self.assertFalse(segmentationDisplay.GetSegmentVisibility("target"))
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("support"))
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("other"))
        self.assertAlmostEqual(
            segmentationDisplay.GetSegmentOpacity3D("support"),
            0.42,
        )
        self.assertTrue(boundsNode.GetDisplayNode().GetVisibility())
        self.assertFalse(shellNode.GetDisplayNode().GetVisibility())

        self.delayDisplay("DENTOWorkflow workflow display filtering tests passed")

    def test_DENTOWorkflowWorkflowViewSelectorWidget(self) -> None:
        """Stage presets and save callbacks must preserve the prior view."""

        slicer.mrmlScene.Clear(0)
        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()
        widget.ui.autoWorkflowViewCheckBox.checked = False
        logic = widget.logic

        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "Workflow selector segmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        for segmentId, segmentName, centerX in (
            ("tooth-14", "upper_right_first_premolar_fdi14", 0.0),
            ("tooth-15", "upper_right_second_premolar_fdi15", 4.0),
            ("tooth-16", "upper_right_first_molar_fdi16", 8.0),
            ("tooth-36", "lower_left_first_molar_fdi36", 12.0),
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

        pulp = vtk.vtkCubeSource()
        pulp.SetBounds(-0.2, 0.2, -0.2, 0.2, -0.7, 0.7)
        pulp.Update()
        pulpSegment = slicer.vtkSegment()
        pulpSegment.SetName("upper_right_first_premolar_pulp_fdi114")
        pulpSegment.AddRepresentation(
            slicer.vtkSegmentationConverter
            .GetSegmentationClosedSurfaceRepresentationName(),
            pulp.GetOutput(),
        )
        segmentationNode.GetSegmentation().AddSegment(
            pulpSegment,
            "pulp-14",
        )

        boundsNode, _bounds = logic.createOrUpdateTargetBoundsRoi(
            segmentationNode,
            "tooth-14",
        )
        trajectoryNode = logic.createTrajectoryNode(
            "Workflow selector trajectory"
        )
        logic.configureTrajectoryTarget(
            trajectoryNode,
            segmentationNode,
            "tooth-14",
        )
        trajectoryNode.SetNodeReferenceID(
            logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
            boundsNode.GetID(),
        )
        trajectoryNode.AddControlPointWorld(vtk.vtkVector3d(0.0, 0.0, 0.8))
        trajectoryNode.AddControlPointWorld(vtk.vtkVector3d(0.0, 0.0, -0.8))
        trajectoryNode.SetLocked(True)
        secondTrajectoryNode = logic.createTrajectoryNode(
            "Workflow selector second trajectory"
        )
        logic.configureTrajectoryTarget(
            secondTrajectoryNode,
            segmentationNode,
            "tooth-14",
        )
        secondTrajectoryNode.SetNodeReferenceID(
            logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
            boundsNode.GetID(),
        )
        secondTrajectoryNode.AddControlPointWorld(
            vtk.vtkVector3d(0.4, 0.0, 0.8)
        )
        secondTrajectoryNode.AddControlPointWorld(
            vtk.vtkVector3d(0.4, 0.0, -0.8)
        )
        secondTrajectoryNode.SetLocked(True)
        shellNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Workflow selector shell",
        )
        shellSource = vtk.vtkCubeSource()
        shellSource.SetBounds(-2.0, 6.0, -2.0, 2.0, -2.0, 2.0)
        shellSource.Update()
        shellNode.SetAndObservePolyData(shellSource.GetOutput())
        shellNode.CreateDefaultDisplayNodes()
        shellNode.SetAttribute("DENTOBOT.ModelRole", "PatientContactShell")
        volumeNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode",
            "Workflow selector CBCT",
        )
        imageData = vtk.vtkImageData()
        imageData.SetDimensions(8, 8, 8)
        imageData.AllocateScalars(vtk.VTK_SHORT, 1)
        volumeNode.SetAndObserveImageData(imageData)
        volumeNode.CreateDefaultDisplayNodes()

        parameterNode = logic.getParameterNode()
        parameterNode.inputVolume = volumeNode
        parameterNode.teethSegmentation = segmentationNode
        parameterNode.targetToothSegmentId = "tooth-14"
        parameterNode.targetToothBoundsRoi = boundsNode
        parameterNode.trajectoryLine = trajectoryNode
        parameterNode.templateSupportToothSegmentIdsJson = (
            logic.encodeTemplateSupportSegmentIds(["tooth-15"])
        )
        parameterNode.patientContactShellModel = shellNode
        widget.setParameterNode(parameterNode)

        unrelatedSegmentation = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "Unrelated scene segmentation",
        )
        unrelatedSegmentation.CreateDefaultDisplayNodes()
        unrelatedCube = vtk.vtkCubeSource()
        unrelatedCube.SetBounds(20.0, 22.0, -1.0, 1.0, -1.0, 1.0)
        unrelatedCube.Update()
        unrelatedSegment = slicer.vtkSegment()
        unrelatedSegment.SetName("upper_left_central_incisor_fdi21")
        unrelatedSegment.AddRepresentation(
            slicer.vtkSegmentationConverter
            .GetSegmentationClosedSurfaceRepresentationName(),
            unrelatedCube.GetOutput(),
        )
        unrelatedSegmentation.GetSegmentation().AddSegment(
            unrelatedSegment,
            "unrelated-21",
        )
        unrelatedSegmentation.GetDisplayNode().SetVisibility(True)
        unrelatedSegmentation.GetDisplayNode().SetAllSegmentsVisibility(True)

        segmentationDisplay = segmentationNode.GetDisplayNode()
        segmentationDisplay.SetVisibility(True)
        segmentationDisplay.SetAllSegmentsVisibility(True)
        boundsNode.GetDisplayNode().SetVisibility(True)
        trajectoryNode.GetDisplayNode().SetVisibility(False)
        secondTrajectoryNode.GetDisplayNode().SetVisibility(True)
        shellNode.GetDisplayNode().SetVisibility(False)

        widget._setWorkflowStage(4, ensureVisible=False)
        widget._applyWorkflowViewPreset("recommended")
        self.assertTrue(boundsNode.GetDisplayNode().GetVisibility())
        self.assertTrue(trajectoryNode.GetDisplayNode().GetVisibility())
        self.assertFalse(secondTrajectoryNode.GetDisplayNode().GetVisibility())
        widget._applyWorkflowViewPreset("target_only")
        self.assertTrue(widget.ui.workflowViewGroupBox.isHidden())
        self.assertIsNotNone(widget._workflowAnatomyComboBox)
        self.assertIsNotNone(widget._workflowCbctComboBox)
        self.assertIsNotNone(widget._workflowAdvancedTree)
        self.assertGreater(widget._workflowAdvancedTree.topLevelItemCount, 0)
        self.assertTrue(
            widget._viewControlsTabWidget.isTabEnabled(
                widget._viewControlsElementsTabIndex
            )
        )
        self.assertIn("segments:target", widget._workflowViewEntriesByKey)
        self.assertIn(
            f"trajectory:{trajectoryNode.GetID()}",
            widget._workflowViewEntriesByKey,
        )
        volumeRenderingLogic = slicer.modules.volumerendering.logic()
        self.assertIsNone(
            volumeRenderingLogic.GetFirstVolumeRenderingDisplayNode(volumeNode)
        )
        self.assertNotIn(
            f"volumeRendering:{volumeNode.GetID()}",
            widget._workflowViewEntriesByKey,
        )
        self.assertIn(
            f"segments:anatomy:upper_teeth:{segmentationNode.GetID()}",
            widget._workflowViewEntriesByKey,
        )
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("tooth-14"))
        self.assertFalse(segmentationDisplay.GetSegmentVisibility("tooth-15"))
        self.assertFalse(segmentationDisplay.GetSegmentVisibility("tooth-16"))
        self.assertFalse(boundsNode.GetDisplayNode().GetVisibility())
        self.assertFalse(trajectoryNode.GetDisplayNode().GetVisibility())

        widget._applyJawTeethView("upper", "2d")
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("tooth-14"))
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("tooth-16"))
        self.assertFalse(segmentationDisplay.GetSegmentVisibility("tooth-36"))
        self.assertTrue(segmentationDisplay.GetVisibility2D())
        self.assertFalse(segmentationDisplay.GetVisibility3D())
        self.assertFalse(unrelatedSegmentation.GetDisplayNode().GetVisibility())
        self.assertEqual(
            widget._workflowViewEntriesByKey[
                f"segments:anatomy:upper_teeth:{unrelatedSegmentation.GetID()}"
            ]["category"],
            "scene_mask",
        )
        widget._applyJawTeethView("lower", "3d")
        self.assertFalse(segmentationDisplay.GetSegmentVisibility("tooth-14"))
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("tooth-36"))
        self.assertFalse(segmentationDisplay.GetVisibility2D())
        self.assertTrue(segmentationDisplay.GetVisibility3D())
        widget._applyJawTeethView("all", "both")
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("tooth-14"))
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("tooth-36"))
        self.assertTrue(segmentationDisplay.GetVisibility2D())
        self.assertTrue(segmentationDisplay.GetVisibility3D())

        widget._applyWorkflowViewPreset("trajectory_only")
        self.assertIn(
            "segments:targetDetail",
            widget._workflowViewEntriesByKey,
        )
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("tooth-14"))
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("pulp-14"))
        self.assertTrue(trajectoryNode.GetDisplayNode().GetVisibility())
        self.assertFalse(secondTrajectoryNode.GetDisplayNode().GetVisibility())
        self.assertTrue(
            trajectoryNode.GetDisplayNode().GetPointLabelsVisibility()
        )

        widget._applyWorkflowViewPreset("plan")
        self.assertTrue(boundsNode.GetDisplayNode().GetVisibility())
        self.assertTrue(trajectoryNode.GetDisplayNode().GetVisibility())
        self.assertTrue(secondTrajectoryNode.GetDisplayNode().GetVisibility())

        widget._setWorkflowStage(8, ensureVisible=False)
        widget._applyWorkflowViewPreset("shell_only")
        self.assertFalse(segmentationDisplay.GetVisibility())
        self.assertFalse(trajectoryNode.GetDisplayNode().GetVisibility())
        self.assertFalse(secondTrajectoryNode.GetDisplayNode().GetVisibility())
        self.assertTrue(shellNode.GetDisplayNode().GetVisibility())

        widget.onSceneStartSave()
        self.assertTrue(segmentationDisplay.GetVisibility())
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("tooth-14"))
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("tooth-15"))
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("tooth-16"))
        self.assertTrue(boundsNode.GetDisplayNode().GetVisibility())
        self.assertTrue(secondTrajectoryNode.GetDisplayNode().GetVisibility())
        self.assertFalse(shellNode.GetDisplayNode().GetVisibility())
        widget.onSceneEndSave()
        self.assertFalse(segmentationDisplay.GetVisibility())
        self.assertTrue(shellNode.GetDisplayNode().GetVisibility())

        widget.onRestoreWorkflowView()
        self.assertTrue(segmentationDisplay.GetVisibility())
        self.assertTrue(segmentationDisplay.GetSegmentVisibility("tooth-15"))
        self.assertTrue(boundsNode.GetDisplayNode().GetVisibility())
        self.assertFalse(shellNode.GetDisplayNode().GetVisibility())

        widget._applyWorkflowViewComposition(
            ViewComposition(
                anatomy_scope="full_anatomy",
                anatomy_dimension="3d",
                cbct_mode="intensity_3d",
                anatomy_opacity=0.35,
            ),
            recommended=False,
            allowRendererCreation=True,
        )
        createdRendering = volumeRenderingLogic.GetFirstVolumeRenderingDisplayNode(
            volumeNode
        )
        self.assertIsNotNone(createdRendering)
        self.assertTrue(createdRendering.GetVisibility())
        self.assertIn(
            createdRendering.GetID(),
            widget._workflowViewCreatedRendererNodeIds,
        )
        self.assertAlmostEqual(
            segmentationDisplay.GetSegmentOpacity3D("tooth-14"),
            0.35,
        )
        widget.onRestoreWorkflowView()
        self.assertIsNone(
            volumeRenderingLogic.GetFirstVolumeRenderingDisplayNode(volumeNode)
        )

        supportBoundary = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsClosedCurveNode",
            "Step 5A interaction lock regression",
        )
        supportBoundary.SetAttribute(
            "DENTOBOT.MarkupsRole",
            "TemplateSupportBoundary",
        )
        supportBoundary.SetLocked(False)
        supportBoundary.SetSelectable(True)
        parameterNode.templateSupportBoundaryCurve = supportBoundary
        robotStage = len(widget._workflowStageEntries()) - 1
        widget._setWorkflowStage(robotStage, ensureVisible=False)
        self.assertTrue(supportBoundary.GetLocked())
        self.assertFalse(supportBoundary.GetSelectable())
        widget._setWorkflowStage(7, ensureVisible=False)
        self.assertFalse(supportBoundary.GetLocked())
        self.assertTrue(supportBoundary.GetSelectable())
        widget._setWorkflowStage(0, ensureVisible=False)
        self.assertIn(
            f"segments:anatomy:upper_teeth:{segmentationNode.GetID()}",
            widget._workflowViewEntriesByKey,
        )
        self.assertTrue(widget.ui.workflowViewGroupBox.isHidden())
        self.assertTrue(
            widget._viewControlsTabWidget.isTabEnabled(
                widget._viewControlsElementsTabIndex
            )
        )
        self.assertTrue(
            widget._viewControlsTabWidget.isTabEnabled(
                widget._viewControlsDisplayTabIndex
            )
        )

        self.delayDisplay("DENTOWorkflow workflow view selector tests passed")

    def test_DENTOWorkflowTrajectorySelectionRestoresTargetWidget(self) -> None:
        slicer.mrmlScene.Clear(0)
        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()
        logic = widget.logic
        for selector in widget._uiWidget.findChildren("qMRMLNodeComboBox"):
            self.assertIs(
                selector.mrmlScene(),
                slicer.mrmlScene,
                f"{selector.objectName} lost its MRML scene binding",
            )

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
        trajectory14Sibling = logic.createTrajectoryNode(
            "DENTO Trajectory FDI 14"
        )
        logic.configureTrajectoryTarget(
            trajectory14Sibling,
            segmentationNode,
            "tooth-14",
        )
        trajectory14Sibling.SetNodeReferenceID(
            logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
            roi14.GetID(),
        )
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
        logic.refreshManagedTrajectoryNames()
        self.assertIn("Trajectory 1 [Complete]", trajectory14.GetName())
        self.assertIn("Trajectory 2 [Empty]", trajectory14Sibling.GetName())
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
        self.assertAlmostEqual(
            trajectory14Sibling.GetDisplayNode().GetOpacity(),
            0.32,
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
            if selectorNode in (
                trajectory14,
                trajectory14Sibling,
                trajectory15,
            ):
                decoration = selectorComboBox.itemData(
                    selectorIndex,
                    qt.Qt.DecorationRole,
                )
                self.assertTrue(decoration.isValid())
                decoratedTrajectoryIds.add(selectorNode.GetID())
        self.assertEqual(
            decoratedTrajectoryIds,
            {
                trajectory14.GetID(),
                trajectory14Sibling.GetID(),
                trajectory15.GetID(),
            },
        )

        widget.onTrajectorySelectionChanged(trajectory14Sibling)
        self.assertIs(parameterNode.trajectoryLine, trajectory14Sibling)
        self.assertEqual(parameterNode.targetToothSegmentId, "tooth-14")
        self.assertIs(
            widget.ui.trajectorySelector.currentNode(),
            trajectory14Sibling,
        )
        self.assertAlmostEqual(
            trajectory14Sibling.GetDisplayNode().GetOpacity(),
            1.0,
        )
        self.assertAlmostEqual(
            trajectory14.GetDisplayNode().GetOpacity(),
            0.32,
        )
        self.assertEqual(widget.ui.trajectoryLengthValueLabel.text, "--")
        widget.onTrajectorySelectionChanged(trajectory14)
        self.assertIs(parameterNode.trajectoryLine, trajectory14)
        self.assertAlmostEqual(
            trajectory14.GetDisplayNode().GetOpacity(),
            1.0,
        )
        self.assertAlmostEqual(
            trajectory14Sibling.GetDisplayNode().GetOpacity(),
            0.32,
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
        self.assertEqual(len(visibilityEntries), 14)
        self.assertTrue(
            all(checkBox.enabled == bool(node) for checkBox, node in visibilityEntries)
        )
        self.assertTrue(
            all(
                "border-left" in checkBox.styleSheet
                for checkBox, node in visibilityEntries
                if node
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
                if node
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

    def test_DENTOWorkflowRobotPlacementLogic(self) -> None:
        """Load articulated STLs and exercise plane snap plus local base nudges."""

        logic = DENTOWorkflowLogic()
        parameterNode = logic.getParameterNode()
        self.assertIsNone(parameterNode.robotBaseTransform)
        self.assertIsNone(parameterNode.robotMountPlane)
        self.assertAlmostEqual(parameterNode.robotTranslationStepMm, 1.0)
        self.assertAlmostEqual(parameterNode.robotRotationStepDeg, 1.0)
        self.assertFalse(parameterNode.robotKeyboardNudgeEnabled)

        zeroPositions = joint_positions_si_from_display(0, 0, 0, 0, 0, 0)
        baseTransform, models = logic.createOrUpdateRobotPlacement(
            None,
            zeroPositions,
        )
        parameterNode.robotBaseTransform = baseTransform
        self.assertTrue(logic.isRobotBaseTransformNode(baseTransform))
        self.assertTrue(baseTransform.GetName().startswith("[Step 6]"))
        self.assertEqual(len(models), 7)
        self.assertEqual(len(logic.robotLinkTransformNodes()), 7)
        for modelNode in models:
            self.assertIsNotNone(modelNode.GetPolyData())
            self.assertGreater(modelNode.GetPolyData().GetNumberOfPoints(), 0)
            linkTransform = modelNode.GetParentTransformNode()
            self.assertIsNotNone(linkTransform)
            self.assertIs(linkTransform.GetParentTransformNode(), baseTransform)
        linkOneModel = logic._nodeByRobotLink(models, "link-1")
        rawReader = vtk.vtkSTLReader()
        rawReader.SetFileName(linkOneModel.GetAttribute("DENTOBOT.SourceMeshPath"))
        rawReader.Update()
        self.assertTrue(
            np.allclose(
                linkOneModel.GetPolyData().GetBounds(),
                rawReader.GetOutput().GetBounds(),
                atol=1e-6,
            )
        )

        linkFiveTransform = logic._nodeByRobotLink(
            logic.robotLinkTransformNodes(),
            "link-5",
        )
        before = vtk.vtkMatrix4x4()
        linkFiveTransform.GetMatrixTransformToParent(before)
        movedPositions = dict(zeroPositions)
        movedPositions["link-4_Slider-4"] = 0.01
        self.assertEqual(logic.updateRobotJointPoses(movedPositions), 7)
        after = vtk.vtkMatrix4x4()
        linkFiveTransform.GetMatrixTransformToParent(after)
        self.assertLess(
            after.GetElement(0, 3) - before.GetElement(0, 3),
            -9.99,
        )

        planeNode = logic.createOrResetRobotMountPlane(None, baseTransform)
        parameterNode.robotMountPlane = planeNode
        self.assertTrue(logic.isRobotMountPlaneNode(planeNode))
        self.assertTrue(planeNode.GetName().startswith("[Step 6]"))
        self.assertFalse(planeNode.GetLocked())
        self.assertTrue(planeNode.GetSelectable())
        planeNode.SetOriginWorld((10.0, 20.0, 30.0))
        planeNode.SetNormalWorld((0.0, 1.0, 0.0))
        snapped = logic.snapRobotBaseToPlane(baseTransform, planeNode)
        self.assertTrue(np.allclose(snapped[:3, 3], (10.0, 20.0, 30.0)))
        self.assertTrue(np.allclose(snapped[:3, 2], (0.0, 1.0, 0.0)))
        nudged = logic.nudgeRobotBase(
            baseTransform,
            translationLocalMm=(0.0, 0.0, 2.0),
        )
        self.assertTrue(np.allclose(nudged[:3, 3], (10.0, 22.0, 30.0)))

        scenePath = Path(slicer.app.temporaryPath) / (
            f"dentobot-robot-lab-{uuid.uuid4().hex}.mrb"
        )
        try:
            self.assertTrue(slicer.util.saveScene(str(scenePath)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(scenePath)))
        finally:
            scenePath.unlink(missing_ok=True)
        reloadedLogic = DENTOWorkflowLogic()
        reloadedParameterNode = reloadedLogic.getParameterNode()
        self.assertTrue(reloadedLogic.isRobotBaseTransformNode(
            reloadedParameterNode.robotBaseTransform
        ))
        self.assertTrue(reloadedLogic.isRobotMountPlaneNode(
            reloadedParameterNode.robotMountPlane
        ))
        self.assertEqual(len(reloadedLogic.robotModelNodes()), 7)
        self.assertEqual(len(reloadedLogic.robotLinkTransformNodes()), 7)
        reloadedMatrix = vtk.vtkMatrix4x4()
        reloadedParameterNode.robotBaseTransform.GetMatrixTransformToWorld(
            reloadedMatrix
        )
        self.assertTrue(np.allclose(
            tuple(reloadedMatrix.GetElement(axis, 3) for axis in range(3)),
            (10.0, 22.0, 30.0),
        ))

        removed = reloadedLogic.deleteRobotPlacement(
            reloadedParameterNode.robotBaseTransform,
            reloadedParameterNode.robotMountPlane,
        )
        self.assertEqual(len(removed), 16)
        self.assertEqual(reloadedLogic.robotModelNodes(), [])
        self.assertEqual(reloadedLogic.robotLinkTransformNodes(), [])
        self.delayDisplay("DENTOWorkflow robot placement logic test passed")

    def test_DENTOWorkflowDraftOpenMouthRobotWorkspace(self) -> None:
        """Load the sample skull, open its jaw, and place the robot at the forehead."""

        logic = DENTOWorkflowLogic()
        parameterNode = logic.getParameterNode()
        skull, mandible, phantomModels = logic.createOrUpdateDraftPhantom()
        self.assertEqual(len(phantomModels), 3)
        self.assertGreater(skull.GetPolyData().GetNumberOfPoints(), 40000)
        self.assertGreater(mandible.GetPolyData().GetNumberOfPoints(), 10000)
        parameterNode.draftPhantomSkullModel = skull
        parameterNode.draftPhantomMandibleModel = mandible

        landmarks = logic.createOrResetDraftJawLandmarks(None)
        landmarkWorldPoints = logic.draftPhantomExampleLandmarksWorldRas()
        for point in landmarkWorldPoints:
            landmarks.AddControlPointWorld(vtk.vtkVector3d(*point))
        parameterNode.draftJawLandmarks = landmarks
        jawTransform, gapLine, jawSummary = logic.createOrUpdateDraftJawOpening(
            mandible,
            landmarks,
            None,
            None,
            40.0,
        )
        parameterNode.draftJawTransform = jawTransform
        parameterNode.draftJawGapLine = gapLine
        self.assertAlmostEqual(jawSummary["gapMm"], 40.0, delta=0.1)
        self.assertIs(mandible.GetParentTransformNode(), jawTransform)
        self.assertEqual(gapLine.GetNumberOfDefinedControlPoints(), 2)
        self.assertEqual(len(logic.draftPhantomWorkspaceTransformNodes()), 1)

        maxilla = next(
            model
            for model in phantomModels
            if model.GetAttribute("DENTOBOT.PhantomPart")
            == logic.DRAFT_PHANTOM_MAXILLA_PART
        )
        skullBounds = [0.0] * 6
        maxillaBounds = [0.0] * 6
        mandibleBounds = [0.0] * 6
        skull.GetRASBounds(skullBounds)
        maxilla.GetRASBounds(maxillaBounds)
        mandible.GetRASBounds(mandibleBounds)
        maxillaCenter = np.asarray(
            (
                (maxillaBounds[0] + maxillaBounds[1]) * 0.5,
                (maxillaBounds[2] + maxillaBounds[3]) * 0.5,
                (maxillaBounds[4] + maxillaBounds[5]) * 0.5,
            ),
            dtype=float,
        )
        mandibleCenter = np.asarray(
            (
                (mandibleBounds[0] + mandibleBounds[1]) * 0.5,
                (mandibleBounds[2] + mandibleBounds[3]) * 0.5,
                (mandibleBounds[4] + mandibleBounds[5]) * 0.5,
            ),
            dtype=float,
        )
        self.assertLess(np.linalg.norm(mandibleCenter - maxillaCenter), 150.0)
        self.assertLess(abs(mandibleCenter[0] - maxillaCenter[0]), 80.0)

        for index in range(2):
            tmjWorld = [0.0, 0.0, 0.0]
            landmarks.GetNthControlPointPositionWorld(index, tmjWorld)
            self.assertTrue(
                np.allclose(tmjWorld, landmarkWorldPoints[index], atol=1e-3)
            )

        baseTransform, robotModels = logic.createOrUpdateRobotPlacement(
            None,
            joint_positions_si_from_display(0, 0, 0, 0, 0, 0),
        )
        parameterNode.robotBaseTransform = baseTransform
        foreheadWorld = logic.draftPhantomNativePointToWorldRas(
            logic.draftPhantomExampleForeheadPlaneNativeRas()
        )
        mountPlane = logic.createOrResetRobotMountPlane(None, baseTransform)
        mountPlane.SetOriginWorld(tuple(foreheadWorld))
        mountPlane.SetNormalWorld((0.0, -1.0, 0.0))
        parameterNode.robotMountPlane = mountPlane
        snapped = logic.snapRobotBaseToPlane(baseTransform, mountPlane)
        self.assertTrue(np.allclose(snapped[:3, 3], foreheadWorld, atol=1e-3))
        self.assertEqual(len(robotModels), 7)

        scenePath = Path(slicer.app.temporaryPath) / (
            f"dentobot-open-mouth-workspace-{uuid.uuid4().hex}.mrb"
        )
        try:
            self.assertTrue(slicer.util.saveScene(str(scenePath)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(scenePath)))
        finally:
            scenePath.unlink(missing_ok=True)
        reloadedLogic = DENTOWorkflowLogic()
        reloadedParameterNode = reloadedLogic.getParameterNode()
        self.assertEqual(len(reloadedLogic.draftPhantomModelNodes()), 3)
        self.assertTrue(reloadedLogic.isDraftJawTransformNode(
            reloadedParameterNode.draftJawTransform
        ))
        self.assertTrue(reloadedLogic.isRobotBaseTransformNode(
            reloadedParameterNode.robotBaseTransform
        ))
        self.assertEqual(len(reloadedLogic.robotModelNodes()), 7)

        removedPhantom = reloadedLogic.deleteDraftPhantom(
            reloadedParameterNode.draftJawLandmarks,
            reloadedParameterNode.draftJawTransform,
            reloadedParameterNode.draftJawGapLine,
        )
        removedRobot = reloadedLogic.deleteRobotPlacement(
            reloadedParameterNode.robotBaseTransform,
            reloadedParameterNode.robotMountPlane,
        )
        self.assertEqual(len(removedPhantom), 7)
        self.assertEqual(len(removedRobot), 16)
        self.delayDisplay("DENTOWorkflow draft open-mouth robot workspace test passed")

    def test_DENTOWorkflowRobotPlacementWidget(self) -> None:
        """Exercise the Step 6 controls and shortcut safety gate."""

        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()
        parameterNode = widget._parameterNode
        robotStageIndex = len(widget._workflowStageEntries()) - 1
        widget._setWorkflowStage(robotStageIndex, ensureVisible=False)
        self.assertEqual(
            widget.ui.workflowStageComboBox.itemText(robotStageIndex),
            "6 · Robot Placement",
        )
        self.assertTrue(
            widget.ui.robotPlacementCollapsibleButton.text.startswith("Step 6")
        )
        self.assertFalse(widget.ui.draftOpenMouthPhantomGroupBox.isHidden())
        self.assertFalse(widget.ui.step6CaseJawOpeningGroupBox.isHidden())
        self.assertFalse(widget.ui.step6CaseJawOpeningGroupBox.enabled)
        self.assertAlmostEqual(widget.ui.draftJawTargetGapSpinBox.value, 40.0)
        self.assertAlmostEqual(widget.ui.step6CaseJawTargetGapSpinBox.value, 40.0)
        self.assertFalse(widget.ui.robotPlacementCollapsibleButton.isHidden())
        self.assertTrue(widget.ui.caseCollapsibleButton.isHidden())
        self.assertEqual(len(widget._robotKeyboardShortcuts), 10)
        self.assertTrue(
            all(not shortcut.enabled for shortcut in widget._robotKeyboardShortcuts)
        )

        widget.onLoadDraftPhantom()
        self.assertEqual(len(widget.logic.draftPhantomModelNodes()), 3)
        self.assertTrue(all(
            model.GetDisplayNode().GetVisibility()
            for model in widget.logic.draftPhantomModelNodes()
        ))
        self.assertIsNotNone(parameterNode.draftPhantomMandibleModel)
        self.assertEqual(widget._step6SceneKind(), "phantom")
        self.assertTrue(widget.ui.step6MountLockGroupBox.enabled)
        self.assertFalse(widget.ui.planTrajectoryMotionButton.enabled)
        widget.onLoadRobotModel()
        self.assertTrue(widget.logic.isRobotBaseTransformNode(
            parameterNode.robotBaseTransform
        ))
        self.assertEqual(len(widget.logic.robotModelNodes()), 7)
        self.assertIn("nodes:step6Phantom", widget._workflowViewEntriesByKey)
        self.assertIn("nodes:step6MrmlRobot", widget._workflowViewEntriesByKey)
        recommended = widget._workflowViewRecommendedCategories(robotStageIndex)
        self.assertIn("phantom", recommended)
        self.assertIn("robot_mrml", recommended)
        landmarks = widget.logic.createOrResetDraftJawLandmarks(None)
        for point in widget.logic.draftPhantomExampleLandmarksWorldRas():
            landmarks.AddControlPointWorld(vtk.vtkVector3d(*point))
        parameterNode.draftJawLandmarks = landmarks
        widget.onApplyDraftJawOpening()
        self.assertTrue(widget.logic.isDraftJawTransformNode(
            parameterNode.draftJawTransform
        ))
        self.assertIn("measured incisor gap", widget.ui.draftOpenMouthStatusLabel.text)
        widget.ui.robotKeyboardNudgeCheckBox.checked = True
        slicer.app.processEvents()
        self.assertTrue(parameterNode.robotKeyboardNudgeEnabled)
        self.assertTrue(
            all(shortcut.enabled for shortcut in widget._robotKeyboardShortcuts)
        )

        before = vtk.vtkMatrix4x4()
        parameterNode.robotBaseTransform.GetMatrixTransformToWorld(before)
        widget._nudgeRobotBase(0, None, 1.0)
        after = vtk.vtkMatrix4x4()
        parameterNode.robotBaseTransform.GetMatrixTransformToWorld(after)
        self.assertAlmostEqual(
            after.GetElement(0, 3) - before.GetElement(0, 3),
            parameterNode.robotTranslationStepMm,
            places=6,
        )

        widget.onCreateRobotMountPlane()
        self.assertTrue(widget.logic.isRobotMountPlaneNode(
            parameterNode.robotMountPlane
        ))
        linkFiveTransform = widget.logic._nodeByRobotLink(
            widget.logic.robotLinkTransformNodes(),
            "link-5",
        )
        beforeJoint = vtk.vtkMatrix4x4()
        linkFiveTransform.GetMatrixTransformToParent(beforeJoint)
        widget.ui.robotJoint4SpinBox.value = 10.0
        slicer.app.processEvents()
        afterJoint = vtk.vtkMatrix4x4()
        linkFiveTransform.GetMatrixTransformToParent(afterJoint)
        self.assertLess(
            afterJoint.GetElement(0, 3) - beforeJoint.GetElement(0, 3),
            -9.99,
        )
        widget._setWorkflowStage(robotStageIndex - 1, ensureVisible=False)
        self.assertTrue(
            all(not shortcut.enabled for shortcut in widget._robotKeyboardShortcuts)
        )
        removed = widget.logic.deleteRobotPlacement(
            parameterNode.robotBaseTransform,
            parameterNode.robotMountPlane,
        )
        self.assertEqual(len(removed), 16)
        removedPhantom = widget.logic.deleteDraftPhantom(
            parameterNode.draftJawLandmarks,
            parameterNode.draftJawTransform,
            parameterNode.draftJawGapLine,
        )
        self.assertEqual(len(removedPhantom), 7)
        wasModifying = parameterNode.StartModify()
        try:
            parameterNode.robotBaseTransform = None
            parameterNode.robotMountPlane = None
            parameterNode.robotKeyboardNudgeEnabled = False
            parameterNode.draftPhantomSkullModel = None
            parameterNode.draftPhantomMandibleModel = None
            parameterNode.draftJawLandmarks = None
            parameterNode.draftJawTransform = None
            parameterNode.draftJawGapLine = None
        finally:
            parameterNode.EndModify(wasModifying)
        widget._clearRobotPlacement()
        self.delayDisplay("DENTOWorkflow robot placement widget test passed")

    def test_DENTOWorkflowStep6CaseJawOpening(self) -> None:
        """Case opening preserves source data and drives mandibular Step 6 world geometry."""
        logic = DENTOWorkflowLogic()
        parameterNode = logic.getParameterNode()
        segmentation = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "Step6CaseJawMasks",
        )
        segmentation.CreateDefaultDisplayNodes()
        segmentation.GetSegmentation().SetSourceRepresentationName(
            slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName()
        )

        def addCubeSegment(segmentId, name, bounds):
            source = vtk.vtkCubeSource()
            source.SetBounds(*bounds)
            source.Update()
            segment = slicer.vtkSegment()
            segment.SetName(name)
            segment.AddRepresentation(
                slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName(),
                source.GetOutput(),
            )
            segmentation.GetSegmentation().AddSegment(segment, segmentId)

        addCubeSegment(
            "upper-tooth-16",
            "upper_right_first_molar_fdi16",
            (-5.0, 5.0, -93.0, -87.0, -13.0, -7.0),
        )
        addCubeSegment(
            "lower-tooth-36",
            "lower_left_first_molar_fdi36",
            (-5.0, 5.0, -93.0, -87.0, -15.0, -9.0),
        )
        addCubeSegment(
            "maxilla",
            "maxilla",
            (-45.0, 45.0, -100.0, -50.0, -25.0, 5.0),
        )
        addCubeSegment(
            "mandible",
            "mandible",
            (-45.0, 45.0, -100.0, -45.0, -30.0, -5.0),
        )
        segmentation.GetDisplayNode().SetAllSegmentsVisibility(True)
        parameterNode.teethSegmentation = segmentation
        parameterNode.targetToothSegmentId = "lower-tooth-36"

        trajectory = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsLineNode",
            "Step6MandibularTrajectory",
        )
        trajectory.AddControlPointWorld(vtk.vtkVector3d(0.0, -88.0, -8.0))
        trajectory.AddControlPointWorld(vtk.vtkVector3d(0.0, -90.0, -13.0))
        trajectory.SetLocked(True)
        trajectory.SetAttribute("DENTOBOT.CoordinateSystem", "SlicerRASmm")
        parameterNode.trajectoryLine = trajectory

        docking = self._addStep6CaseCubeModel(
            "Step6MandibularDocking",
            (-4.0, 4.0, -94.0, -86.0, -16.0, -6.0),
        )
        docking.SetAttribute("DENTOBOT.ModelRole", "TargetDockingAssembly")
        docking.SetAttribute("DENTOBOT.GeometryState", "Current")
        docking.SetAttribute("DENTOBOT.OrientationState", "Confirmed")
        parameterNode.targetDockingAssemblyModel = docking
        finalTemplate = self._addStep6CaseCubeModel(
            "Step6MandibularTemplate",
            (-8.0, 8.0, -98.0, -82.0, -18.0, -4.0),
        )
        finalTemplate.SetAttribute("DENTOBOT.ModelRole", "FinalPrintableTemplate")
        finalTemplate.SetAttribute("DENTOBOT.GeometryState", "Current")
        finalTemplate.SetAttribute("DENTOBOT.VerificationState", "PASS")
        parameterNode.finalPrintableTemplateModel = finalTemplate
        parameterNode.step6PlanningContextImported = True

        landmarks = logic.ensureStep6CaseJawLandmarksNode(None)
        for point in (
            (-50.0, 0.0, 0.0),
            (50.0, 0.0, 0.0),
            (0.0, -90.0, -10.0),
            (0.0, -90.0, -12.0),
        ):
            landmarks.AddControlPointWorld(vtk.vtkVector3d(*point))
        parameterNode.step6CaseJawLandmarks = landmarks
        sourceLowerBounds = logic.getSegmentationSegmentBoundsWorld(
            segmentation,
            "lower-tooth-36",
        )
        sourceTrajectory = logic.getTrajectorySummary(trajectory)
        transform, openedJaw, gapLine, opening = (
            logic.createOrUpdateStep6CaseJawOpening(parameterNode)
        )

        self.assertAlmostEqual(opening["gapMm"], 40.0, delta=0.1)
        self.assertTrue(logic.isStep6CaseJawTransformNode(transform))
        self.assertIs(openedJaw.GetParentTransformNode(), transform)
        self.assertEqual(gapLine.GetNumberOfDefinedControlPoints(), 2)
        self.assertFalse(
            segmentation.GetDisplayNode().GetSegmentVisibility3D("lower-tooth-36")
        )
        self.assertEqual(
            tuple(sourceLowerBounds),
            tuple(
                logic.getSegmentationSegmentBoundsWorld(
                    segmentation,
                    "lower-tooth-36",
                )
            ),
        )
        self.assertIsNone(finalTemplate.GetParentTransformNode())
        self.assertIs(
            parameterNode.step6OpenedTargetGeometryModel.GetParentTransformNode(),
            transform,
        )
        transformedTrajectory = logic.step6TrajectorySummary(parameterNode)
        self.assertFalse(
            np.allclose(
                sourceTrajectory["targetRas"],
                transformedTrajectory["targetRas"],
            )
        )
        openedTarget = [0.0, 0.0, 0.0]
        parameterNode.step6OpenedTrajectoryLine.GetNthControlPointPositionWorld(
            1,
            openedTarget,
        )
        self.assertTrue(
            np.allclose(
                openedTarget,
                transformedTrajectory["targetRas"],
                atol=1e-6,
            )
        )
        self.assertFalse(logic.step6CaseJawOpeningFreshnessIssues(parameterNode))
        self.assertFalse(logic.step6PlanningContextFreshnessIssues(parameterNode))

        scenePath = Path(slicer.app.temporaryPath) / (
            f"dentobot-case-jaw-opening-{uuid.uuid4().hex}.mrb"
        )
        try:
            self.assertTrue(slicer.util.saveScene(str(scenePath)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(scenePath)))
            reloadedLogic = DENTOWorkflowLogic()
            reloaded = reloadedLogic.getParameterNode()
            self.assertTrue(reloaded.step6PlanningContextImported)
            self.assertFalse(
                reloadedLogic.step6CaseJawOpeningFreshnessIssues(reloaded)
            )
            self.assertTrue(
                reloadedLogic.isStep6OpenedLowerJawModelNode(
                    reloaded.step6OpenedLowerJawModel
                )
            )
            reloadedLogic.resetStep6CaseJawOpening(reloaded)
            self.assertIsNone(reloaded.step6CaseJawTransform)
            self.assertIsNone(reloaded.step6OpenedLowerJawModel)
            self.assertTrue(
                reloaded.teethSegmentation.GetDisplayNode().GetSegmentVisibility3D(
                    "lower-tooth-36"
                )
            )
        finally:
            scenePath.unlink(missing_ok=True)

        self.delayDisplay("DENTOWorkflow Step 6 case jaw-opening test passed")

    def _addStep6CaseCubeModel(self, name: str, bounds) -> vtkMRMLModelNode:
        cube = vtk.vtkCubeSource()
        cube.SetBounds(*bounds)
        cube.Update()
        model = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", name)
        model.SetAndObservePolyData(cube.GetOutput())
        model.CreateDefaultDisplayNodes()
        return model

    def test_DENTOWorkflowStep6NativePlacementPersistence(self) -> None:
        """Explicit CBCT context and persistent placement state round-trip safely."""

        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()
        logic = widget.logic
        parameterNode = widget._parameterNode
        image = vtk.vtkImageData()
        image.SetDimensions(9, 8, 7)
        image.AllocateScalars(vtk.VTK_SHORT, 1)
        image.GetPointData().GetScalars().FillComponent(0, 625.0)
        volume = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode", "Step6NativePersistenceCBCT"
        )
        volume.SetAndObserveImageData(image)
        ijk_to_ras = vtk.vtkMatrix4x4()
        ijk_to_ras.DeepCopy(
            (
                0.31, 0.0, 0.0, -42.5,
                0.0, 0.27, 0.0, 18.25,
                0.0, 0.0, 0.34, 73.75,
                0.0, 0.0, 0.0, 1.0,
            )
        )
        volume.SetIJKToRASMatrix(ijk_to_ras)
        volume.CreateDefaultDisplayNodes()
        volume.GetDisplayNode().SetWindowLevel(1800.0, 500.0)

        segmentation = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode", "Step6NativePersistenceMasks"
        )
        segmentation.CreateDefaultDisplayNodes()
        segment = slicer.vtkSegment()
        segment.SetName("FDI 14")
        tooth_source = vtk.vtkSphereSource()
        tooth_source.SetCenter(-41.0, 19.0, 74.5)
        tooth_source.SetRadius(1.25)
        tooth_source.Update()
        segment.AddRepresentation(
            slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName(),
            tooth_source.GetOutput(),
        )
        segmentation.GetSegmentation().AddSegment(segment, "tooth-fdi-14")
        parameterNode.inputVolume = volume
        parameterNode.teethSegmentation = segmentation
        parameterNode.targetToothSegmentId = "tooth-fdi-14"

        matrix_before = vtk.vtkMatrix4x4()
        volume.GetIJKToRASMatrix(matrix_before)
        geometry_before = tuple(
            float(matrix_before.GetElement(row, column))
            for row in range(4) for column in range(4)
        )
        dimensions_before = tuple(volume.GetImageData().GetDimensions())
        scalar_range_before = tuple(volume.GetImageData().GetScalarRange())
        mask_bounds_before = logic.getSegmentationSegmentBoundsWorld(
            segmentation, "tooth-fdi-14"
        )

        widget._updateWorkflowViewControls()
        self.assertEqual(
            len(slicer.util.getNodesByClass("vtkMRMLVolumeRenderingDisplayNode")),
            0,
        )
        first_renderer = logic.enableStep6CbctVolumeRendering(
            parameterNode, "current"
        )
        second_renderer = logic.enableStep6CbctVolumeRendering(
            parameterNode, "current"
        )
        self.assertIs(first_renderer, second_renderer)
        self.assertEqual(
            len(slicer.util.getNodesByClass("vtkMRMLVolumeRenderingDisplayNode")),
            1,
        )
        logic.setStep6Appearance(
            parameterNode, "cbct", visible=True, opacity=0.37
        )
        logic.setStep6Appearance(
            parameterNode, "masks", visible=True, opacity=0.42
        )

        base, models = logic.createOrUpdateRobotPlacement(
            None,
            joint_positions_si_from_display(0, 0, 0, 0, 0, 0),
        )
        base_matrix = vtk.vtkMatrix4x4()
        base_matrix.Identity()
        base_matrix.SetElement(0, 3, 180.0)
        base_matrix.SetElement(1, 3, -75.0)
        base.SetMatrixTransformToParent(base_matrix)
        parameterNode.robotBaseTransform = base
        plane = logic.createOrResetRobotMountPlane(None, base)
        parameterNode.robotMountPlane = plane
        proxy = logic.createOrUpdateStep6ForeheadProxy(parameterNode)
        parameterNode.robotForeheadProxyModel = proxy
        logic.setStep6Appearance(
            parameterNode, "robot", visible=True, opacity=0.73
        )
        logic.setStep6Appearance(
            parameterNode, "mount_plane", visible=True, opacity=0.31
        )
        logic.setStep6Appearance(
            parameterNode, "forehead_proxy", visible=True, opacity=0.22
        )
        logic.setRobotBaseMountLocked(parameterNode, True)
        task_home = logic.saveCurrentTaskHome(parameterNode)
        self.assertFalse(logic.taskHomeFreshnessIssues(parameterNode))

        matrix_after = vtk.vtkMatrix4x4()
        volume.GetIJKToRASMatrix(matrix_after)
        self.assertEqual(
            geometry_before,
            tuple(
                float(matrix_after.GetElement(row, column))
                for row in range(4) for column in range(4)
            ),
        )
        self.assertEqual(dimensions_before, tuple(volume.GetImageData().GetDimensions()))
        self.assertEqual(scalar_range_before, tuple(volume.GetImageData().GetScalarRange()))
        self.assertEqual(
            tuple(mask_bounds_before),
            tuple(logic.getSegmentationSegmentBoundsWorld(segmentation, "tooth-fdi-14")),
        )

        case_bounds = logic._nodeRasBounds(volume)
        robot_bounds = [logic._modelRasBounds(model) for model in models]
        proxy_bounds = logic._modelRasBounds(proxy)
        union = logic.combinedRasBounds([case_bounds, proxy_bounds, *robot_bounds])
        self.assertIsNotNone(union)
        self.assertLessEqual(union[0], case_bounds[0])
        self.assertGreaterEqual(union[1], max(bounds[1] for bounds in robot_bounds))

        scene_path = Path(slicer.app.temporaryPath) / (
            f"dentobot-step6-native-persistence-{uuid.uuid4().hex}.mrb"
        )
        try:
            self.assertTrue(slicer.util.saveScene(str(scene_path)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(scene_path)))
            reloaded_logic = DENTOWorkflowLogic()
            reloaded = reloaded_logic.getParameterNode()
            self.assertEqual(
                reloaded.step6BasePlacementStatus,
                BasePlacementStatus.PROVISIONAL_LOCKED.value,
            )
            self.assertTrue(reloaded.robotBaseMountLocked)
            self.assertEqual(len(reloaded_logic.step6ForeheadProxyNodes()), 1)
            self.assertEqual(
                reloaded.robotForeheadProxyModel.GetAttribute("DENTOBOT.IntendedUse"),
                "VisualizationOnly",
            )
            self.assertEqual(
                reloaded.robotForeheadProxyModel.GetAttribute("DENTOBOT.ExcludedFromCollision"),
                "true",
            )
            self.assertAlmostEqual(reloaded.step6CbctOpacity, 0.37)
            self.assertAlmostEqual(reloaded.step6MasksOpacity, 0.42)
            self.assertAlmostEqual(reloaded.step6RobotOpacity, 0.73)
            self.assertAlmostEqual(reloaded.step6MountPlaneOpacity, 0.31)
            self.assertAlmostEqual(reloaded.step6ForeheadProxyOpacity, 0.22)
            reloaded_home = reloaded_logic.taskHomeRecord(reloaded)
            self.assertEqual(reloaded_home, task_home)
            self.assertFalse(reloaded_logic.taskHomeFreshnessIssues(reloaded))
            self.assertEqual(
                len(slicer.util.getNodesByClass("vtkMRMLVolumeRenderingDisplayNode")),
                1,
            )
            restored_matrix = vtk.vtkMatrix4x4()
            reloaded.inputVolume.GetIJKToRASMatrix(restored_matrix)
            restored_geometry = tuple(
                float(restored_matrix.GetElement(row, column))
                for row in range(4) for column in range(4)
            )
            self.assertTrue(
                all(
                    abs(before - after) <= 1e-6
                    for before, after in zip(geometry_before, restored_geometry)
                )
            )
        finally:
            scene_path.unlink(missing_ok=True)

        self.delayDisplay("DENTOWorkflow native Step 6 persistence test passed")

    def test_DENTOWorkflowStep6CaseViewWidget(self) -> None:
        """Import must frame the case package, not the phantom research origin."""

        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()
        parameterNode = widget._parameterNode
        widget._setWorkflowStage(10, ensureVisible=False)

        imageData = vtk.vtkImageData()
        imageData.SetDimensions(8, 8, 8)
        imageData.AllocateScalars(vtk.VTK_SHORT, 1)
        volume = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode",
            "Step6CaseVolume",
        )
        volume.SetAndObserveImageData(imageData)
        volume.SetSpacing(1.0, 1.0, 1.0)
        volume.SetOrigin(40.0, 10.0, 0.0)
        volume.CreateDefaultDisplayNodes()

        segmentation = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "Step6CaseSegmentation",
        )
        segmentation.CreateDefaultDisplayNodes()
        segment = slicer.vtkSegment()
        segment.SetName("target-tooth")
        tooth = vtk.vtkCubeSource()
        tooth.SetBounds(42.0, 48.0, 12.0, 18.0, 1.0, 6.0)
        tooth.Update()
        segment.AddRepresentation(
            slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName(),
            tooth.GetOutput(),
        )
        segmentation.GetSegmentation().AddSegment(segment, "tooth-11")

        trajectory = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsLineNode",
            "Step6CaseTrajectory",
        )
        trajectory.AddControlPointWorld(vtk.vtkVector3d(45.0, 15.0, 5.0))
        trajectory.AddControlPointWorld(vtk.vtkVector3d(46.0, 15.0, 2.0))
        trajectory.SetLocked(True)
        trajectory.SetAttribute("DENTOBOT.CoordinateSystem", "SlicerRASmm")
        docks = self._addStep6CaseCubeModel(
            "Step6CaseDocks",
            (43.0, 47.0, 13.0, 17.0, 0.5, 4.0),
        )
        docks.SetAttribute("DENTOBOT.GeometryState", "Current")
        docks.SetAttribute("DENTOBOT.OrientationState", "Confirmed")
        template = self._addStep6CaseCubeModel(
            "Step6CaseTemplate",
            (40.0, 50.0, 10.0, 20.0, 0.0, 5.0),
        )
        template.SetAttribute("DENTOBOT.GeometryState", "Current")
        template.SetAttribute("DENTOBOT.VerificationState", "PASS")
        boundsRoi = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsROINode",
            "Step6CaseBounds",
        )
        boundsRoi.CreateDefaultDisplayNodes()
        boundsRoi.SetCenterWorld(45.0, 15.0, 2.5)
        boundsRoi.SetSizeWorld(10.0, 10.0, 5.0)

        wasModifying = parameterNode.StartModify()
        try:
            parameterNode.inputVolume = volume
            parameterNode.teethSegmentation = segmentation
            parameterNode.targetToothSegmentId = "tooth-11"
            parameterNode.trajectoryLine = trajectory
            parameterNode.targetDockingAssemblyModel = docks
            parameterNode.finalPrintableTemplateModel = template
            parameterNode.targetToothBoundsRoi = boundsRoi
        finally:
            parameterNode.EndModify(wasModifying)

        widget.onImportStep6PlanningContext()
        self.assertTrue(parameterNode.step6PlanningContextImported)
        self.assertEqual(widget._step6SceneKind(), "case")
        self.assertIn("node:step6Volume", widget._workflowViewEntriesByKey)
        self.assertIn("node:step6Bounds", widget._workflowViewEntriesByKey)
        recommended = widget._workflowViewRecommendedCategories(10)
        self.assertIn("case_volume", recommended)
        self.assertIn("bounds", recommended)
        self.assertNotIn("phantom", recommended)

        caseBounds = widget.logic.step6CaseViewRasBounds(parameterNode)
        self.assertIsNotNone(caseBounds)
        self.assertGreaterEqual(caseBounds[0], 39.0)
        self.assertLessEqual(caseBounds[1], 51.0)
        self.assertGreaterEqual(caseBounds[2], 9.0)
        self.assertLessEqual(caseBounds[3], 21.0)

        layoutManager = slicer.app.layoutManager()
        if layoutManager is not None:
            redWidget = layoutManager.sliceWidget("Red")
            if redWidget is not None:
                composite = redWidget.mrmlSliceCompositeNode()
                self.assertEqual(composite.GetBackgroundVolumeID(), volume.GetID())

        self.delayDisplay("DENTOWorkflow Step 6 case-into-view widget test passed")

    def test_DENTOWorkflowStep6JointLimitSpinboxes(self) -> None:
        """Apply task limits must set the merged value spinbox min/max and clamp."""

        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()
        widget._setWorkflowStage(9, ensureVisible=False)
        self.assertIsNone(getattr(widget.ui, "robotJointControlGroupBox", None))
        self.assertEqual(
            widget.ui.robotJoint1TaskMinSpinBox.parent(),
            widget.ui.robotJoint1SpinBox.parent(),
        )
        widget.ui.robotJoint1TaskMinSpinBox.value = 10.0
        widget.ui.robotJoint1TaskMaxSpinBox.value = 20.0
        widget.ui.robotJoint1SpinBox.value = 0.0
        slicer.app.processEvents()
        widget.onApplyTaskJointLimits()
        self.assertAlmostEqual(widget.ui.robotJoint1SpinBox.minimum, 10.0, places=2)
        self.assertAlmostEqual(widget.ui.robotJoint1SpinBox.maximum, 20.0, places=2)
        self.assertGreaterEqual(widget.ui.robotJoint1SpinBox.value, 10.0)
        self.assertLessEqual(widget.ui.robotJoint1SpinBox.value, 20.0)

        widget.ui.robotJoint2TaskMinSpinBox.value = 5.0
        widget.ui.robotJoint2TaskMaxSpinBox.value = 15.0
        slicer.app.processEvents()
        widget._onTaskJointLimitSpinBoxChanged()
        self.assertAlmostEqual(widget.ui.robotJoint2SpinBox.minimum, 5.0, places=2)
        self.assertAlmostEqual(widget.ui.robotJoint2SpinBox.maximum, 15.0, places=2)
        self.delayDisplay("DENTOWorkflow Step 6 merged joint-limit spinbox test passed")

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
        opposingToothSegment = slicer.vtkSegment()
        opposingToothSegment.SetName("lower_right_first_molar_fdi46")
        opposingCube = vtk.vtkCubeSource()
        opposingCube.SetBounds(-1.0, 1.0, -1.0, 1.0, -8.0, -4.0)
        opposingCube.Update()
        opposingToothSegment.AddRepresentation(
            slicer.vtkSegmentationConverter
            .GetSegmentationClosedSurfaceRepresentationName(),
            opposingCube.GetOutput(),
        )
        segmentationNode.GetSegmentation().AddSegment(
            opposingToothSegment,
            "tooth-46",
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
        with self.assertRaisesRegex(ValueError, "opposing jaw"):
            logic.validateTemplateSupportSelection(
                segmentationNode,
                "tooth-16",
                ["tooth-46"],
            )
        self.assertEqual(logic.dentalArchForFdi("16"), "Upper")
        self.assertEqual(logic.dentalArchForFdi("46"), "Lower")

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
        self.assertIsNone(modelNode.GetTransformNodeID())
        self.assertEqual(
            modelNode.GetAttribute("DENTOBOT.CoordinateConvention"),
            "WorldRASmm",
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
            modelNode.GetAttribute("DENTOBOT.SupportSelectionLocked"),
            "true",
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
        self.assertTrue(modelNode.GetName().startswith("[Step 4B]"))
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
        self.assertTrue(summary["selectionLocked"])

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
        modelNode.SetAttribute("DENTOBOT.SupportSelectionLocked", "false")
        self.assertFalse(logic.isTemplateSupportSelectionLocked(modelNode))
        legacyLockNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "LegacySupportLock",
        )
        legacyLockNode.SetAttribute("DENTOBOT.ModelRole", "TemplateSupportDraft")
        self.assertTrue(logic.isTemplateSupportSelectionLocked(legacyLockNode))

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
            "DENTOWorkflow Step 4B multi-support model logic tests passed"
        )

    def test_DENTOWorkflowTemplateReviewGateWidget(self) -> None:
        """Make a new segmentation's required review action explicit in Step 4B."""

        slicer.mrmlScene.Clear(0)
        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.initializeParameterNode()
        logic = widget.logic

        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "NewUnreviewedDentalSegmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        widget._restoringTrajectoryAssociation = True
        try:
            widget.ui.reviewSegmentationSelector.setCurrentNode(segmentationNode)
        finally:
            widget._restoringTrajectoryAssociation = False
        parameterNode = widget._parameterNode
        widget._updatingFromParameterNode = True
        try:
            wasModifying = parameterNode.StartModify()
            try:
                parameterNode.teethSegmentation = segmentationNode
                parameterNode.targetToothSegmentId = "tooth-14"
                parameterNode.templateSupportToothSegmentIdsJson = (
                    logic.encodeTemplateSupportSegmentIds(["tooth-15"])
                )
            finally:
                parameterNode.EndModify(wasModifying)
        finally:
            widget._updatingFromParameterNode = False
        widget._targetToothRecordsById = {
            "tooth-14": {
                "segmentId": "tooth-14",
                "displayName": "FDI 14 — Upper Right First Premolar",
                "sourceName": "upper_right_first_premolar_fdi14",
                "fdiNumber": "14",
            },
            "tooth-15": {
                "segmentId": "tooth-15",
                "displayName": "FDI 15 — Upper Right Second Premolar",
                "sourceName": "upper_right_second_premolar_fdi15",
                "fdiNumber": "15",
            },
        }
        widget._updateTemplateModeling()

        targetArchButton = slicer.util.findChild(
            widget._templateSupportArchWidget,
            "templateSupportToothFdi14Button",
        )
        supportArchButton = widget._templateSupportButtonsBySegmentId[
            "tooth-15"
        ]
        opposingArchButtons = slicer.util.findChildren(
            widget._templateSupportArchWidget,
            name="templateSupportToothFdi45Button",
        )
        self.assertTrue(targetArchButton.checked)
        self.assertFalse(targetArchButton.enabled)
        self.assertTrue(supportArchButton.checked)
        self.assertTrue(supportArchButton.enabled)
        self.assertEqual(opposingArchButtons, [])
        self.assertIn("Upper jaw only", widget._templateSupportArchStatusLabel.text)

        self.assertEqual(
            logic.getSegmentationReviewState(segmentationNode),
            "Unreviewed",
        )
        self.assertFalse(widget.ui.createDraftTemplateSupportModelButton.enabled)
        self.assertTrue(widget.ui.reviewSegmentationForTemplateButton.enabled)
        self.assertIn(
            "Unreviewed",
            widget.ui.reviewSegmentationForTemplateButton.text,
        )
        self.assertIn("1 checked support", widget.ui.templateModelingStatusLabel.text)

        widget.onReviewSegmentationForTemplate()
        self.assertFalse(widget.ui.segmentationReviewCollapsibleButton.collapsed)
        self.assertTrue(widget.ui.templateModelingCollapsibleButton.collapsed)
        self.assertIs(
            widget.ui.reviewSegmentationSelector.currentNode(),
            segmentationNode,
        )

        logic.setSegmentationReviewState(
            segmentationNode,
            "Reviewed",
            updatedUtc="2026-08-11T12:00:00+00:00",
        )
        widget._updateTemplateModeling()
        self.assertTrue(widget.ui.createDraftTemplateSupportModelButton.enabled)
        self.assertFalse(widget.ui.reviewSegmentationForTemplateButton.visible)

        supportSource = vtk.vtkSphereSource()
        supportSource.SetRadius(2.0)
        supportSource.Update()
        supportModel = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "[Step 4B] Locked FDI 14 Support Package",
        )
        supportModel.SetAndObservePolyData(supportSource.GetOutput())
        supportModel.SetAttribute("DENTOBOT.ModelRole", "TemplateSupportDraft")
        supportModel.SetAttribute("DENTOBOT.GeometryState", "Current")
        supportModel.SetAttribute("DENTOBOT.SupportSelectionLocked", "true")
        supportModel.SetAttribute("DENTOBOT.TargetSegmentID", "tooth-14")
        supportModel.SetAttribute(
            "DENTOBOT.SupportSegmentIDsJson",
            logic.encodeTemplateSupportSegmentIds(["tooth-15"]),
        )
        supportModel.SetNodeReferenceID(
            logic.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE,
            segmentationNode.GetID(),
        )
        widget._updatingFromParameterNode = True
        try:
            wasModifying = parameterNode.StartModify()
            try:
                parameterNode.templateSupportToothSegmentIdsJson = "[]"
                parameterNode.draftTemplateSupportModel = supportModel
            finally:
                parameterNode.EndModify(wasModifying)
        finally:
            widget._updatingFromParameterNode = False
        widget._updateTemplateModeling()
        supportArchButton = widget._templateSupportButtonsBySegmentId[
            "tooth-15"
        ]
        self.assertEqual(
            logic.decodeTemplateSupportSegmentIds(
                parameterNode.templateSupportToothSegmentIdsJson
            ),
            ["tooth-15"],
        )
        self.assertFalse(supportArchButton.enabled)
        self.assertTrue(widget._reviseTemplateSupportPackageButton.enabled)
        self.assertIn("Package locked", widget._templateSupportArchStatusLabel.text)
        self.assertIn("FDI 15", widget._templateSupportPackageDetailsLabel.text)
        self.assertIn("Ready", widget._templateSupportPackageSummaryLabel.text)

        originalConfirm = slicer.util.confirmYesNoDisplay
        slicer.util.confirmYesNoDisplay = lambda *args, **kwargs: True
        try:
            widget.onReviseTemplateSupportPackage()
        finally:
            slicer.util.confirmYesNoDisplay = originalConfirm
        self.assertEqual(
            supportModel.GetAttribute("DENTOBOT.SupportSelectionLocked"),
            "false",
        )
        self.assertEqual(
            supportModel.GetAttribute("DENTOBOT.GeometryState"),
            "Stale",
        )
        supportArchButton = widget._templateSupportButtonsBySegmentId[
            "tooth-15"
        ]
        self.assertTrue(supportArchButton.enabled)
        self.assertIn("unlocked", widget._templateSupportPackageSummaryLabel.text)

        self.delayDisplay(
            "DENTOWorkflow Step 4B ownership and Step 5A consumer widget test passed"
        )

    def test_DENTOWorkflowInsertionAlignedSupportPlaneBoundary(self) -> None:
        """Initialize a three-tooth support loop from a locked trajectory plane."""

        logic = DENTOWorkflowLogic()
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "InsertionPlaneSupportSegmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        fixtures = (
            ("tooth-13", "upper_right_canine_fdi13", -8.0),
            ("tooth-14", "upper_right_first_premolar_fdi14", 0.0),
            ("tooth-15", "upper_right_second_premolar_fdi15", 8.0),
        )
        for segmentId, segmentName, centerX in fixtures:
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
            updatedUtc="2026-08-11T12:00:00+00:00",
        )
        supportModel, _details = logic.createOrUpdateDraftTemplateSupportModel(
            segmentationNode,
            "tooth-14",
            ["tooth-13", "tooth-15"],
        )
        trajectoryNode = logic.createTrajectoryNode("Insertion Plane Trajectory")
        logic.configureTrajectoryTarget(
            trajectoryNode,
            segmentationNode,
            "tooth-14",
        )
        trajectoryNode.AddControlPoint(vtk.vtkVector3d(0.0, 0.0, 5.0))
        trajectoryNode.AddControlPoint(vtk.vtkVector3d(0.0, 0.0, -5.0))

        planeNode, planeGeometry = logic.createOrUpdateTemplateSupportBoundaryPlane(
            supportModel,
            trajectoryNode,
            depthFromEntryMm=3.0,
        )
        self.assertTrue(logic.isTemplateSupportBoundaryPlaneNode(planeNode))
        self.assertTrue(planeNode.GetLocked())
        self.assertFalse(planeNode.GetSelectable())
        self.assertTrue(
            np.allclose(planeGeometry["originRas"], (0.0, 0.0, 2.0))
        )
        self.assertTrue(
            np.allclose(planeGeometry["normalRas"], (0.0, 0.0, -1.0))
        )

        curveNode, boundaryMetrics = (
            logic.createOrUpdateTemplateSupportBoundaryFromPlane(
                supportModel,
                planeNode,
                trajectoryNode,
                samplingSpacingMm=0.5,
            )
        )
        self.assertEqual(boundaryMetrics["intersectedToothCount"], 3)
        self.assertGreater(curveNode.GetNumberOfDefinedControlPoints(), 3)
        self.assertIs(
            curveNode.GetNodeReference(
                logic.TEMPLATE_SUPPORT_BOUNDARY_INITIALIZER_PLANE_REFERENCE_ROLE
            ),
            planeNode,
        )
        for point in logic.templateSupportBoundaryControlPointsWorld(curveNode):
            self.assertAlmostEqual(point[2], 2.0, places=5)

        previewNode, previewMetrics = logic.createOrUpdateVisibleTemplateSupportModel(
            supportModel,
            curveNode,
            directionTrajectory=trajectoryNode,
            samplingSpacingMm=0.5,
            terminalCoveragePercent=50.0,
        )
        self.assertEqual(previewMetrics["selectedToothCount"], 3)
        self.assertEqual(previewMetrics["omittedToothCount"], 0)
        self.assertTrue(previewMetrics["terminalSupport"]["applied"])
        crownDirection = np.asarray(
            previewMetrics["crownDirectionRas"],
            dtype=float,
        )
        for clipPlane in previewMetrics["terminalClipPlanesRas"]:
            inwardNormal = np.asarray(
                clipPlane["inwardNormalRas"],
                dtype=float,
            )
            self.assertAlmostEqual(
                float(np.dot(inwardNormal, crownDirection)),
                0.0,
                places=6,
            )
            self.assertTrue(clipPlane["splitPlaneContainsInsertionAxis"])

        parameterNode = logic.getParameterNode()
        wasModifying = parameterNode.StartModify()
        try:
            parameterNode.teethSegmentation = segmentationNode
            parameterNode.targetToothSegmentId = "tooth-14"
            parameterNode.trajectoryLine = trajectoryNode
            parameterNode.templateSupportToothSegmentIdsJson = (
                logic.encodeTemplateSupportSegmentIds(
                    ["tooth-13", "tooth-15"]
                )
            )
            parameterNode.draftTemplateSupportModel = supportModel
            parameterNode.templateSupportBoundaryPlane = planeNode
            parameterNode.templateSupportBoundaryCurve = curveNode
            parameterNode.visibleTemplateSupportModel = previewNode
        finally:
            parameterNode.EndModify(wasModifying)
        scenePath = Path(slicer.app.temporaryPath) / (
            f"dentobot-step5a-plane-{uuid.uuid4().hex}.mrb"
        )
        try:
            self.assertTrue(slicer.util.saveScene(str(scenePath)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(scenePath)))
            reloadedLogic = DENTOWorkflowLogic()
            reloadedParameterNode = reloadedLogic.getParameterNode()
            reloadedSupportModel = (
                reloadedParameterNode.draftTemplateSupportModel
            )
            reloadedPlane = reloadedParameterNode.templateSupportBoundaryPlane
            reloadedCurve = reloadedParameterNode.templateSupportBoundaryCurve
            reloadedPreview = reloadedParameterNode.visibleTemplateSupportModel
            reloadedSupportSummary = (
                reloadedLogic.getDraftTemplateSupportModelSummary(
                    reloadedSupportModel
                )
            )
            self.assertTrue(reloadedSupportSummary["selectionLocked"])
            self.assertEqual(
                reloadedSupportSummary["supportSegmentIds"],
                ["tooth-13", "tooth-15"],
            )
            self.assertEqual(
                reloadedLogic.decodeTemplateSupportSegmentIds(
                    reloadedParameterNode.templateSupportToothSegmentIdsJson
                ),
                ["tooth-13", "tooth-15"],
            )
            self.assertTrue(
                reloadedLogic.isTemplateSupportBoundaryPlaneNode(reloadedPlane)
            )
            self.assertIs(
                reloadedCurve.GetNodeReference(
                    reloadedLogic
                    .TEMPLATE_SUPPORT_BOUNDARY_INITIALIZER_PLANE_REFERENCE_ROLE
                ),
                reloadedPlane,
            )
            reloadedSummary = (
                reloadedLogic.getVisibleTemplateSupportModelSummary(
                    reloadedPreview
                )
            )
            self.assertEqual(reloadedSummary["geometryState"], "Current")
            self.assertTrue(
                reloadedLogic.templateSupportBoundaryMatchesGeometryJson(
                    reloadedCurve,
                    reloadedSummary["boundaryGeometryJson"],
                )
            )
            removals = reloadedLogic.deleteTemplateSupportSelection(
                reloadedCurve,
                reloadedPreview,
                reloadedPlane,
            )
            self.assertFalse(slicer.mrmlScene.IsNodePresent(reloadedCurve))
            self.assertFalse(slicer.mrmlScene.IsNodePresent(reloadedPreview))
            self.assertFalse(slicer.mrmlScene.IsNodePresent(reloadedPlane))
        finally:
            if scenePath.exists():
                scenePath.unlink()
        self.assertEqual(len(removals), 3)

        self.delayDisplay(
            "DENTOWorkflow insertion-aligned support-plane test passed"
        )

    def test_DENTOWorkflowDirectionalSupportSideSelection(self) -> None:
        """Choose crown-side patches per tooth despite size and mesh islands."""

        toothSurfaces = []
        specifications = (
            ("tooth-large-left", -7.0, 4.5, 1.5),
            ("tooth-small-middle", 2.0, 3.2, -1.2),
            ("tooth-large-right", 10.0, 4.8, 0.7),
        )
        for segmentId, centerX, radius, _boundaryZ in specifications:
            primary = vtk.vtkSphereSource()
            primary.SetCenter(centerX, 0.0, 0.0)
            primary.SetRadius(radius)
            primary.SetThetaResolution(64)
            primary.SetPhiResolution(48)
            primary.Update()
            artifact = vtk.vtkSphereSource()
            artifact.SetCenter(centerX, 20.0, -20.0)
            artifact.SetRadius(0.4)
            artifact.SetThetaResolution(16)
            artifact.SetPhiResolution(12)
            artifact.Update()
            append = vtk.vtkAppendPolyData()
            append.AddInputData(primary.GetOutput())
            append.AddInputData(artifact.GetOutput())
            append.Update()
            surface = vtk.vtkPolyData()
            surface.DeepCopy(append.GetOutput())
            toothSurfaces.append(
                {
                    "segmentId": segmentId,
                    "displayName": segmentId,
                    "isTarget": segmentId == "tooth-small-middle",
                    "polyData": surface,
                }
            )

        def boundaryPoint(centerX, radius, boundaryZ, angleDeg):
            crossRadius = math.sqrt(max(0.0, radius * radius - boundaryZ * boundaryZ))
            angle = math.radians(angleDeg)
            return (
                centerX + crossRadius * math.cos(angle),
                crossRadius * math.sin(angle),
                boundaryZ,
            )

        left = specifications[0]
        middle = specifications[1]
        right = specifications[2]
        loopPoints = (
            boundaryPoint(right[1], right[2], right[3], 0.0),
            boundaryPoint(right[1], right[2], right[3], 90.0),
            boundaryPoint(middle[1], middle[2], middle[3], 90.0),
            boundaryPoint(left[1], left[2], left[3], 90.0),
            boundaryPoint(left[1], left[2], left[3], 180.0),
            boundaryPoint(left[1], left[2], left[3], 270.0),
            boundaryPoint(middle[1], middle[2], middle[3], 270.0),
            boundaryPoint(right[1], right[2], right[3], 270.0),
        )
        crownPatch, crownMetrics = extract_directional_visible_support_surface(
            toothSurfaces,
            loopPoints,
            (0.0, 0.0, 1.0),
            sampling_spacing_mm=0.35,
        )
        rootPatch, rootMetrics = extract_directional_visible_support_surface(
            toothSurfaces,
            loopPoints,
            (0.0, 0.0, -1.0),
            sampling_spacing_mm=0.35,
        )
        self.assertEqual(crownMetrics["sourceToothCount"], 3)
        self.assertEqual(crownMetrics["selectedToothCount"], 3)
        self.assertEqual(crownMetrics["omittedToothCount"], 0)
        self.assertEqual(crownMetrics["sourceSurfaceRegionCount"], 6)
        self.assertEqual(crownMetrics["ignoredSourceIslandCount"], 3)
        self.assertTrue(crownMetrics["terminalSupport"]["applied"])
        self.assertEqual(
            set(crownMetrics["terminalSupport"]["clippedTerminalSegmentIds"]),
            {"tooth-large-left", "tooth-large-right"},
        )
        self.assertEqual(len(crownMetrics["terminalClipPlanesRas"]), 2)
        self.assertEqual(rootMetrics["selectedToothCount"], 3)
        self.assertGreater(crownPatch.GetBounds()[5], 4.0)
        self.assertLess(rootPatch.GetBounds()[4], -4.0)
        self.assertEqual(
            {item["selectedCandidate"] for item in crownMetrics["toothMetrics"]},
            {"Smaller", "Larger"},
        )
        for toothMetrics in crownMetrics["toothMetrics"]:
            self.assertGreater(
                toothMetrics["selectedDirectionScoreMm"],
                toothMetrics["otherDirectionScoreMm"],
            )

    def test_DENTOWorkflowTemplateSupportBoundaryFocusDisplay(self) -> None:
        """Isolate subject tooth masks temporarily and restore exact display state."""

        slicer.mrmlScene.Clear(0)
        logic = DENTOWorkflowLogic()
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "BoundaryFocusSegmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        for segmentId, segmentName, centerX in (
            ("tooth-16", "upper_right_first_molar_fdi16", -5.0),
            ("tooth-15", "upper_right_second_premolar_fdi15", 0.0),
            ("tooth-14", "upper_right_first_premolar_fdi14", 5.0),
            ("jaw", "upper_jawbone", 12.0),
        ):
            sphere = vtk.vtkSphereSource()
            sphere.SetCenter(centerX, 0.0, 0.0)
            sphere.SetRadius(2.0)
            sphere.SetThetaResolution(24)
            sphere.SetPhiResolution(18)
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
            updatedUtc="2026-08-11T12:00:00+00:00",
        )
        sourceModel, _details = logic.createOrUpdateDraftTemplateSupportModel(
            segmentationNode,
            "tooth-16",
            ["tooth-15"],
        )

        displayNode = segmentationNode.GetDisplayNode()
        displayNode.SetVisibility(False)
        displayNode.SetVisibility2D(False)
        displayNode.SetVisibility3D(True)
        displayNode.SetOpacity3D(0.47)
        displayNode.SetOpacity2DFill(0.38)
        displayNode.SetOpacity2DOutline(0.59)
        originalSegmentStates = {
            "tooth-16": (False, 0.21, 0.31, 0.41),
            "tooth-15": (True, 0.52, 0.62, 0.72),
            "tooth-14": (True, 0.83, 0.73, 0.63),
            "jaw": (True, 0.94, 0.84, 0.74),
        }
        for segmentId, values in originalSegmentStates.items():
            displayNode.SetSegmentVisibility(segmentId, values[0])
            displayNode.SetSegmentOpacity3D(segmentId, values[1])
            displayNode.SetSegmentOpacity2DFill(segmentId, values[2])
            displayNode.SetSegmentOpacity2DOutline(segmentId, values[3])
        sourceModel.GetDisplayNode().SetVisibility(True)
        sourcePointCount = sourceModel.GetPolyData().GetNumberOfPoints()

        state = logic.applyTemplateSupportBoundaryFocus(
            segmentationNode,
            sourceModel,
            contextModels=[sourceModel],
        )
        self.assertEqual(
            state["subjectSegmentIds"],
            ["tooth-16", "tooth-15"],
        )
        self.assertEqual(state["hiddenSegmentCount"], 2)
        self.assertTrue(displayNode.GetVisibility())
        self.assertTrue(displayNode.GetVisibility2D())
        self.assertTrue(displayNode.GetVisibility3D())
        for segmentId in ("tooth-16", "tooth-15"):
            self.assertTrue(displayNode.GetSegmentVisibility(segmentId))
            self.assertAlmostEqual(displayNode.GetSegmentOpacity3D(segmentId), 1.0)
            self.assertAlmostEqual(
                displayNode.GetSegmentOpacity2DFill(segmentId),
                1.0,
            )
        self.assertFalse(displayNode.GetSegmentVisibility("tooth-14"))
        self.assertFalse(displayNode.GetSegmentVisibility("jaw"))
        self.assertFalse(sourceModel.GetDisplayNode().GetVisibility())
        self.assertEqual(
            sourceModel.GetPolyData().GetNumberOfPoints(),
            sourcePointCount,
        )

        logic.restoreTemplateSupportBoundaryFocus(state)
        self.assertFalse(displayNode.GetVisibility())
        self.assertFalse(displayNode.GetVisibility2D())
        self.assertTrue(displayNode.GetVisibility3D())
        self.assertAlmostEqual(displayNode.GetOpacity3D(), 0.47)
        self.assertAlmostEqual(displayNode.GetOpacity2DFill(), 0.38)
        self.assertAlmostEqual(displayNode.GetOpacity2DOutline(), 0.59)
        for segmentId, values in originalSegmentStates.items():
            self.assertEqual(
                bool(displayNode.GetSegmentVisibility(segmentId)),
                values[0],
            )
            self.assertAlmostEqual(displayNode.GetSegmentOpacity3D(segmentId), values[1])
            self.assertAlmostEqual(
                displayNode.GetSegmentOpacity2DFill(segmentId),
                values[2],
            )
            self.assertAlmostEqual(
                displayNode.GetSegmentOpacity2DOutline(segmentId),
                values[3],
            )
        self.assertTrue(sourceModel.GetDisplayNode().GetVisibility())
        self.delayDisplay(
            "DENTOWorkflow support-boundary subject-mask focus tests passed"
        )

    def test_DENTOWorkflowPatientContactShellVoxelFallback(self) -> None:
        """Repair an invalid Hollow extrusion and union its boundary bridge."""

        mainCube = vtk.vtkCubeSource()
        mainCube.SetBounds(-2.0, 2.0, -2.0, 2.0, -2.0, 2.0)
        mainCube.Update()
        voxelSpeckle = vtk.vtkCubeSource()
        voxelSpeckle.SetBounds(5.0, 5.3, 5.0, 5.3, 5.0, 5.3)
        voxelSpeckle.Update()
        substantiveIsland = vtk.vtkCubeSource()
        substantiveIsland.SetBounds(8.0, 9.0, 8.0, 9.0, 8.0, 9.0)
        substantiveIsland.Update()
        appendArtifacts = vtk.vtkAppendPolyData()
        appendArtifacts.AddInputData(mainCube.GetOutput())
        appendArtifacts.AddInputData(voxelSpeckle.GetOutput())
        appendArtifacts.AddInputData(substantiveIsland.GetOutput())
        appendArtifacts.Update()
        filteredArtifacts, artifactMetrics = (
            remove_single_voxel_surface_speckles(
                appendArtifacts.GetOutput(),
                (0.3, 0.3, 0.3),
            )
        )
        self.assertEqual(artifactMetrics["rawSurfaceRegionCount"], 3)
        self.assertEqual(
            artifactMetrics["removedSingleVoxelSpeckleCount"],
            1,
        )
        self.assertEqual(artifactMetrics["retainedSurfaceRegionCount"], 2)
        self.assertEqual(surface_topology(filteredArtifacts)["surfaceRegionCount"], 2)

        anatomySource = vtk.vtkCubeSource()
        anatomySource.SetBounds(-5.0, 5.0, -5.0, 5.0, -5.0, 0.0)
        anatomySource.Update()
        anatomy = vtk.vtkPolyData()
        anatomy.DeepCopy(anatomySource.GetOutput())

        fittingSource = vtk.vtkPlaneSource()
        fittingSource.SetOrigin(-3.0, -3.0, 0.3)
        fittingSource.SetPoint1(3.0, -3.0, 0.3)
        fittingSource.SetPoint2(-3.0, 3.0, 0.3)
        fittingSource.SetXResolution(24)
        fittingSource.SetYResolution(24)
        fittingSource.Update()
        fittingSurface = vtk.vtkPolyData()
        fittingSurface.DeepCopy(fittingSource.GetOutput())
        invalidHollowCandidate = vtk.vtkPolyData()
        invalidHollowCandidate.DeepCopy(fittingSurface)

        boundaryPoints = (
            (-3.0, -3.0, 0.0),
            (3.0, -3.0, 0.0),
            (3.0, 3.0, 0.0),
            (-3.0, 3.0, 0.0),
        )
        bridge, bridgeMetrics = create_support_boundary_bridge(
            boundaryPoints,
            (0.0, 0.0, 1.0),
            fit_clearance_mm=0.3,
            shell_thickness_mm=1.0,
            sampling_spacing_mm=0.2,
        )
        self.assertEqual(bridgeMetrics["method"], "LiftedClosedBoundaryCollar")
        self.assertEqual(bridgeMetrics["boundaryOrNonManifoldEdgeCount"], 0)

        shell, metrics = regularize_patient_contact_shell(
            invalidHollowCandidate,
            anatomy,
            fit_clearance_mm=0.3,
            sampling_spacing_mm=0.2,
            voxel_closing_mm=0.3,
            fitting_surface_world=fittingSurface,
            shell_thickness_mm=1.0,
            boundary_bridge_world=bridge,
            terminal_clip_planes_ras=[
                {
                    "segmentId": "left-terminal",
                    "originRas": (-2.0, 0.0, 0.0),
                    "inwardNormalRas": (1.0, 0.0, 0.0),
                    "coverageFraction": 0.5,
                },
                {
                    "segmentId": "right-terminal",
                    "originRas": (2.0, 0.0, 0.0),
                    "inwardNormalRas": (-1.0, 0.0, 0.0),
                    "coverageFraction": 0.5,
                },
            ],
        )
        self.assertGreater(
            metrics["candidateTopology"]["boundaryOrNonManifoldEdgeCount"],
            0,
        )
        self.assertEqual(
            metrics["method"],
            "DynamicModelerHollowWithFittingSurfaceDistanceFieldFallback",
        )
        self.assertEqual(
            metrics["candidateRepairMode"],
            "FittingSurfaceDistanceBand",
        )
        self.assertTrue(metrics["boundaryBridgeIntegrated"])
        self.assertEqual(metrics["boundaryOrNonManifoldEdgeCount"], 0)
        self.assertEqual(metrics["surfaceRegionCount"], 1)
        self.assertEqual(metrics["imageBoundaryOccupiedSampleCount"], 0)
        self.assertGreater(metrics["croppedDomainPaddingMm"], 1.0)
        self.assertGreaterEqual(metrics["closingReachEstimateMm"], 0.3)
        self.assertEqual(metrics["terminalClipPlaneCount"], 2)
        self.assertGreaterEqual(shell.GetBounds()[0], -2.3)
        self.assertLessEqual(shell.GetBounds()[1], 2.3)
        self.assertGreater(shell.GetNumberOfCells(), 0)
        self.delayDisplay(
            "DENTOWorkflow invalid-Hollow fallback and boundary-bridge tests passed"
        )

    def test_DENTOWorkflowTargetDockingBindingPreservesConfirmation(self) -> None:
        """GUI binding must not turn a restored confirmed dock back to Draft."""

        widget = slicer.modules.dentoworkflow.widgetRepresentation().self()
        widget.setParameterNode(None)
        logic = widget.logic
        parameterNode = logic.getParameterNode()
        parameterNode.targetDockingPatternRadiusMm = 12.0
        parameterNode.targetDockingOuterDiameterMm = 3.0
        parameterNode.targetDockingBoreDiameterMm = 1.0
        parameterNode.targetDockingConnectorDiameterMm = 3.5
        parameterNode.targetDockingConnectorThicknessMm = 2.0
        parameterNode.targetDockingSharedDepthMm = 5.0
        parameterNode.targetDockingIndividualDepthsEnabled = False
        parameterNode.targetDockingDepth1Mm = 5.0
        parameterNode.targetDockingDepth2Mm = 5.0
        parameterNode.targetDockingDepth3Mm = 5.0
        parameterNode.targetDockingDepth4Mm = 5.0
        parameterNode.targetDockingCollisionClearanceMm = 0.5
        parameterNode.templateDockingClearanceMm = 0.3
        parameterNode.templateReinforcementRadialMm = 1.0
        parameterNode.templateSamplingSpacingMm = 0.3
        parameterNode.targetDockingYawDeg = -35.0
        parameterNode.targetDockingYawConfirmed = True

        planeNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsPlaneNode",
            "BindingGuardDockPlane",
        )
        planeNode.SetAttribute(
            "DENTOBOT.MarkupsRole",
            "TargetDockingReferencePlane",
        )
        assemblyModel = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "BindingGuardDockAssembly",
        )
        assemblyModel.SetAttribute(
            "DENTOBOT.ModelRole",
            "TargetDockingAssembly",
        )
        storedParameters = normalize_target_docking_parameters(
            pattern_radius_mm=12.0,
            outer_diameter_mm=3.0,
            bore_diameter_mm=1.0,
            connector_diameter_mm=3.5,
            connector_thickness_mm=2.0,
            shared_depth_mm=5.0,
            individual_depths_mm=(5.0, 5.0, 5.0, 5.0),
            individual_depths_enabled=False,
            yaw_deg=-35.0,
            collision_clearance_mm=0.5,
            clearance_mm=0.3,
            reinforcement_radial_mm=1.0,
            processing_resolution_mm=0.3,
        )
        assemblyModel.SetAttribute(
            "DENTOBOT.ParametersJson",
            json.dumps(storedParameters, sort_keys=True, separators=(",", ":")),
        )
        confirmedUtc = "2026-08-25T00:00:00+00:00"
        for node in (assemblyModel, planeNode):
            node.SetAttribute("DENTOBOT.OrientationState", "Confirmed")
            node.SetAttribute("DENTOBOT.OrientationConfirmedUtc", confirmedUtc)
        parameterNode.targetDockingReferencePlane = planeNode
        parameterNode.targetDockingAssemblyModel = assemblyModel

        widget.setParameterNode(parameterNode)
        slicer.app.processEvents()

        for node in (assemblyModel, planeNode):
            self.assertEqual(
                node.GetAttribute("DENTOBOT.OrientationState"),
                "Confirmed",
            )
            self.assertEqual(
                node.GetAttribute("DENTOBOT.OrientationConfirmedUtc"),
                confirmedUtc,
            )
        widget.setParameterNode(None)

    def test_DENTOWorkflowTargetDockingYawMath(self) -> None:
        frame = {
            "originRas": (0.0, 0.0, 0.0),
            "xAxisRas": (1.0, 0.0, 0.0),
            "yAxisRas": (0.0, 1.0, 0.0),
            "zAxisRas": (0.0, 0.0, 1.0),
        }
        parameters = normalize_target_docking_parameters(
            pattern_radius_mm=10.0,
            outer_diameter_mm=2.0,
            bore_diameter_mm=1.0,
            connector_diameter_mm=2.5,
            connector_thickness_mm=1.0,
            shared_depth_mm=4.0,
            individual_depths_mm=(4.0, 4.0, 4.0, 4.0),
            individual_depths_enabled=False,
            clearance_mm=0.3,
            reinforcement_radial_mm=0.8,
            processing_resolution_mm=0.3,
            yaw_deg=0.0,
            collision_clearance_mm=0.5,
        )
        obstacleSource = vtk.vtkSphereSource()
        obstacleSource.SetCenter(10.0, 0.0, 2.0)
        obstacleSource.SetRadius(0.8)
        obstacleSource.SetThetaResolution(24)
        obstacleSource.SetPhiResolution(16)
        obstacleSource.Update()
        zeroReport = evaluate_target_docking_obstacle_clearance(
            frame,
            parameters,
            [obstacleSource.GetOutput()],
        )
        self.assertGreaterEqual(zeroReport["collidingDockCount"], 1)
        search = find_collision_aware_target_docking_yaw(
            frame,
            parameters,
            [obstacleSource.GetOutput()],
            step_deg=5.0,
        )
        self.assertGreater(search["collisionFreeCandidateCount"], 0)
        self.assertEqual(
            search["selectedClearanceReport"]["collidingDockCount"],
            0,
        )
        self.assertFalse(math.isclose(search["selectedYawDeg"] % 90.0, 0.0))
        rotatedParameters = dict(parameters)
        rotatedParameters["yawDeg"] = search["selectedYawDeg"]
        _surfaces, metrics = create_target_frame_docking_geometry(
            frame,
            rotatedParameters,
        )
        self.assertEqual(metrics["yawDeg"], search["selectedYawDeg"])
        self.assertEqual(metrics["dockCount"], 4)
        for dock in metrics["docks"]:
            self.assertAlmostEqual(dock["radialDistanceMm"], 10.0, places=6)
            self.assertLessEqual(abs(dock["topFacePlaneResidualMm"]), 1e-8)
        self.delayDisplay("DENTOWorkflow collision-aware Step 4C yaw tests passed")

    def test_DENTOWorkflowTinyFusionArtifactFiltering(self) -> None:
        """Discard only sub-resolution islands beside one printable component."""

        rankedLabels = np.zeros(125, dtype=np.uint16)
        rankedLabels[:100] = 1
        rankedLabels[100:103] = 2
        rankedLabels[103] = 3
        rankedLabels[104] = 4
        filteredMask, metrics = filter_tiny_occupied_region_artifacts(
            rankedLabels.reshape((5, 5, 5)),
            [100, 3, 1, 1],
            (0.3, 0.3, 0.3),
        )
        self.assertTrue(metrics["tinyOccupiedArtifactCleanupApplied"])
        self.assertEqual(metrics["maximumDiscardedOccupiedArtifactSampleCount"], 3)
        self.assertEqual(metrics["removedTinyOccupiedRegionCount"], 3)
        self.assertEqual(metrics["removedTinyOccupiedSampleCount"], 5)
        self.assertEqual(metrics["removedSingleVoxelOccupiedRegionCount"], 2)
        self.assertEqual(metrics["occupiedVolumeRegionCount"], 1)
        self.assertEqual(metrics["occupiedVolumeRegionSizes"], [100])
        self.assertEqual(int(np.count_nonzero(filteredMask)), 100)

        rankedLabels[100:] = 0
        rankedLabels[100:104] = 2
        retainedMask, retainedMetrics = filter_tiny_occupied_region_artifacts(
            rankedLabels.reshape((5, 5, 5)),
            [100, 4],
            (0.3, 0.3, 0.3),
        )
        self.assertFalse(retainedMetrics["tinyOccupiedArtifactCleanupApplied"])
        self.assertEqual(retainedMetrics["occupiedVolumeRegionCount"], 2)
        self.assertEqual(int(np.count_nonzero(retainedMask)), 104)

    def test_DENTOWorkflowVisibleTemplateSupportSurface(self) -> None:
        """Select crown-like patches from separate full-tooth surfaces in RAS."""

        slicer.mrmlScene.Clear(0)
        logic = DENTOWorkflowLogic()
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "VisibleSupportSegmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        for segmentId, segmentName, centerX in (
            ("tooth-16", "upper_right_first_molar_fdi16", -4.25),
            ("tooth-15", "upper_right_second_premolar_fdi15", 4.25),
            ("tooth-14", "upper_right_first_premolar_fdi14", 20.0),
            ("tooth-17", "upper_right_second_molar_fdi17", -12.0),
        ):
            sphere = vtk.vtkSphereSource()
            sphere.SetCenter(centerX, 0.0, 0.0)
            sphere.SetRadius(4.0)
            sphere.SetThetaResolution(64)
            sphere.SetPhiResolution(48)
            sphere.Update()
            segment = slicer.vtkSegment()
            segment.SetName(segmentName)
            segment.AddRepresentation(
                slicer.vtkSegmentationConverter
                .GetSegmentationClosedSurfaceRepresentationName(),
                sphere.GetOutput(),
            )
            segmentationNode.GetSegmentation().AddSegment(segment, segmentId)

        parentTransform = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLinearTransformNode",
            "VisibleSupportParentTransform",
        )
        transformMatrix = vtk.vtkMatrix4x4()
        transformMatrix.Identity()
        translation = (12.0, -7.0, 30.0)
        for axis, value in enumerate(translation):
            transformMatrix.SetElement(axis, 3, value)
        parentTransform.SetMatrixTransformToParent(transformMatrix)
        segmentationNode.SetAndObserveTransformNodeID(parentTransform.GetID())
        logic.setSegmentationReviewState(
            segmentationNode,
            "Reviewed",
            updatedUtc="2026-08-10T12:00:00+00:00",
        )

        sourceModel, _details = logic.createOrUpdateDraftTemplateSupportModel(
            segmentationNode,
            "tooth-16",
            ["tooth-15", "tooth-14"],
        )
        boundary = logic.createOrResetTemplateSupportBoundary(sourceModel)
        self.assertEqual(
            boundary.GetCurveTypeAsString(boundary.GetCurveType()),
            "linear",
        )
        self.assertIs(
            boundary.GetNodeReference(
                logic.TEMPLATE_SUPPORT_BOUNDARY_SOURCE_MODEL_REFERENCE_ROLE
            ),
            sourceModel,
        )
        for localPoint in (
            (8.25, 0.0, 0.0),
            (4.25, 4.0, 0.0),
            (0.0, 3.8, 0.0),
            (-4.25, 4.0, 0.0),
            (-8.25, 0.0, 0.0),
            (-4.25, -4.0, 0.0),
            (0.0, -3.8, 0.0),
            (4.25, -4.0, 0.0),
        ):
            boundary.AddControlPointWorld(
                vtk.vtkVector3d(
                    localPoint[0] + translation[0],
                    localPoint[1] + translation[1],
                    localPoint[2] + translation[2],
                )
            )

        directionTrajectory = logic.createTrajectoryNode(
            "Synthetic target insertion trajectory"
        )
        logic.configureTrajectoryTarget(
            directionTrajectory,
            segmentationNode,
            "tooth-16",
        )
        directionTrajectory.AddControlPointWorld(
            vtk.vtkVector3d(
                -4.25 + translation[0],
                translation[1],
                translation[2] + 4.0,
            )
        )
        directionTrajectory.AddControlPointWorld(
            vtk.vtkVector3d(
                -4.25 + translation[0],
                translation[1],
                translation[2],
            )
        )
        preview, metrics = logic.createOrUpdateVisibleTemplateSupportModel(
            sourceModel,
            boundary,
            directionTrajectory=directionTrajectory,
            samplingSpacingMm=0.5,
        )
        summary = logic.getVisibleTemplateSupportModelSummary(preview)
        self.assertEqual(
            metrics["method"],
            "PerToothTrajectoryDirectionalDijkstra",
        )
        self.assertEqual(metrics["sourceToothCount"], 3)
        self.assertEqual(metrics["selectedToothCount"], 2)
        self.assertEqual(metrics["omittedToothCount"], 1)
        self.assertEqual(metrics["surfaceRegionCount"], 2)
        self.assertEqual(summary["geometryState"], "Current")
        self.assertIs(summary["sourceModel"], sourceModel)
        self.assertIs(summary["boundary"], boundary)
        self.assertIs(summary["sourceSegmentation"], segmentationNode)
        self.assertIs(summary["directionTrajectory"], directionTrajectory)
        self.assertFalse(summary["directionReversed"])
        self.assertIsNone(preview.GetParentTransformNode())
        previewBounds = preview.GetPolyData().GetBounds()
        self.assertGreater(previewBounds[4], translation[2] - 0.2)
        self.assertGreater(previewBounds[5], translation[2] + 3.9)
        self.assertLess(
            preview.GetPolyData().GetNumberOfCells(),
            sourceModel.GetPolyData().GetNumberOfCells(),
        )

        insertionDirection = preview.GetNodeReference(
            logic.TEMPLATE_VISIBLE_SUPPORT_INSERTION_DIRECTION_REFERENCE_ROLE
        )
        self.assertTrue(logic.isTemplateInsertionDirectionNode(insertionDirection))
        self.assertTrue(insertionDirection.GetLocked())
        self.assertFalse(insertionDirection.GetSelectable())
        directionSummary = logic.getTemplateInsertionDirectionSummary(
            insertionDirection
        )
        self.assertEqual(directionSummary["insertionDirectionRas"], (0.0, 0.0, -1.0))
        self.assertEqual(directionSummary["removalDirectionRas"], (-0.0, -0.0, 1.0))
        self.assertIs(directionSummary["sourceTrajectory"], directionTrajectory)
        undercutModel, blockoutModel, undercutDetails = (
            logic.createOrUpdateTemplateUndercutAnalysis(
                sourceModel,
                preview,
                insertionDirection,
                angleToleranceDeg=5.0,
                interproximalReliefMm=1.0,
                samplingSpacingMm=0.3,
            )
        )
        undercutSummary = logic.getTemplateUndercutOutputSummary(
            undercutModel,
            "TemplateUndercutSurface",
        )
        blockoutSummary = logic.getTemplateUndercutOutputSummary(
            blockoutModel,
            "TemplateUndercutBlockout",
        )
        self.assertEqual(undercutSummary["geometryState"], "Current")
        self.assertEqual(blockoutSummary["geometryState"], "Current")
        self.assertIs(undercutSummary["insertionDirection"], insertionDirection)
        self.assertEqual(
            undercutDetails["blockout"]["method"],
            "InsertionFrameDirectionalHeightField",
        )
        self.assertEqual(
            undercutDetails["blockout"]["boundaryOrNonManifoldEdgeCount"],
            0,
        )
        self.assertEqual(
            undercutDetails["blockout"]["interproximalReliefMm"],
            1.0,
        )
        self.assertEqual(
            undercutDetails["blockout"]["collisionAnatomy"][
                "collisionToothCount"
            ],
            4,
        )
        self.assertIn(
            "tooth-17",
            undercutDetails["blockout"]["collisionAnatomy"][
                "collisionSegmentIds"
            ],
        )

        patientShell, shellDetails = logic.createOrUpdatePatientContactShell(
            sourceModel,
            preview,
            insertionDirection,
            blockoutModel,
            clearanceMm=0.3,
            thicknessMm=1.2,
            samplingSpacingMm=0.3,
            blockoutSafetyMm=0.1,
            voxelClosingMm=0.3,
        )
        shellSummary = logic.getPatientContactShellSummary(patientShell)
        self.assertEqual(shellSummary["geometryState"], "Current")
        self.assertEqual(shellSummary["undercutState"], "Processed")
        self.assertIs(shellSummary["sourceModel"], sourceModel)
        self.assertIs(shellSummary["visibleSupport"], preview)
        self.assertIs(shellSummary["boundary"], boundary)
        self.assertIs(shellSummary["insertionDirection"], insertionDirection)
        self.assertIs(shellSummary["blockoutModel"], blockoutModel)
        self.assertEqual(
            shellDetails["metrics"]["boundaryOrNonManifoldEdgeCount"],
            0,
        )
        self.assertEqual(
            shellDetails["metrics"]["method"],
            "DynamicModelerHollowWithTightVoxelClearanceBoolean",
        )
        self.assertTrue(shellDetails["metrics"]["boundaryBridgeIntegrated"])
        self.assertEqual(
            shellDetails["metrics"]["boundaryBridge"]["method"],
            "LiftedClosedBoundaryCollar",
        )
        self.assertIsNotNone(shellSummary["boundaryBridge"].GetPolyData())
        self.assertGreater(
            shellDetails["metrics"]["minimumAnatomyDistanceMm"],
            -0.2,
        )
        self.assertGreater(patientShell.GetPolyData().GetBounds()[4], 29.5)
        self.assertIsNotNone(shellSummary["fittingSurface"].GetPolyData())
        self.assertIsNotNone(shellSummary["hollowCandidate"].GetPolyData())

        directionTrajectory.SetLocked(True)
        guideTrajectories = [directionTrajectory]
        for segmentId, centerX in (("tooth-16", -2.25),):
            trajectory = logic.createTrajectoryNode(
                f"Synthetic guide trajectory {segmentId}"
            )
            logic.configureTrajectoryTarget(
                trajectory,
                segmentationNode,
                segmentId,
            )
            trajectory.AddControlPointWorld(
                vtk.vtkVector3d(
                    centerX + translation[0],
                    translation[1],
                    translation[2] + 4.0,
                )
            )
            trajectory.AddControlPointWorld(
                vtk.vtkVector3d(
                    centerX + translation[0],
                    translation[1],
                    translation[2],
                )
            )
            trajectory.SetLocked(True)
            guideTrajectories.append(trajectory)
        targetDockingParameters = normalize_target_docking_parameters(
            pattern_radius_mm=8.0,
            outer_diameter_mm=3.0,
            bore_diameter_mm=1.0,
            connector_diameter_mm=3.5,
            connector_thickness_mm=2.0,
            shared_depth_mm=4.0,
            individual_depths_mm=(4.0, 4.0, 4.0, 4.0),
            individual_depths_enabled=False,
            clearance_mm=0.3,
            reinforcement_radial_mm=1.0,
            processing_resolution_mm=0.3,
        )
        targetDockingPlane, targetDockingAssembly, targetDockingDetails = (
            logic.createOrUpdateTargetDockingAssembly(
                segmentationNode,
                "tooth-16",
                guideTrajectories,
                targetDockingParameters,
                supportModel=sourceModel,
                autoSelectYaw=True,
            )
        )
        targetDockingSummary = logic.getTargetDockingAssemblySummary(
            targetDockingAssembly
        )
        self.assertEqual(targetDockingSummary["geometryState"], "Current")
        self.assertEqual(targetDockingSummary["schemaVersion"], "4.0")
        self.assertIs(targetDockingSummary["supportModel"], sourceModel)
        self.assertEqual(
            targetDockingSummary["supportSegmentIds"],
            ["tooth-15", "tooth-14"],
        )
        self.assertEqual(targetDockingSummary["orientationState"], "Draft")
        self.assertEqual(len(targetDockingSummary["measurementNodes"]), 13)
        self.assertEqual(
            targetDockingDetails["metrics"]["autoYawSearch"]["selectedYawDeg"],
            targetDockingDetails["parameters"]["yawDeg"],
        )
        self.assertEqual(
            targetDockingDetails["metrics"]["collisionScreen"]["obstacleSurfaceCount"],
            3,
        )
        self.assertEqual(targetDockingDetails["metrics"]["dockCount"], 4)
        self.assertEqual(
            targetDockingDetails["metrics"]["independentDockComponentCount"],
            4,
        )
        self.assertFalse(targetDockingDetails["metrics"]["centralHubPresent"])
        self.assertEqual(targetDockingDetails["metrics"]["radialSpokeCount"], 0)
        self.assertEqual(
            targetDockingDetails["metrics"]["layoutSpecification"],
            "FourIndependentOcclusalTangentDockBranches",
        )
        self.assertLessEqual(
            targetDockingDetails["metrics"]["topPlaneMaxResidualMm"],
            0.1,
        )
        for dock in targetDockingDetails["metrics"]["docks"]:
            self.assertAlmostEqual(
                dock["terminalPlaneOffsetMm"],
                dock["depthMm"],
                places=5,
            )
            self.assertLessEqual(abs(dock["topFacePlaneResidualMm"]), 1e-5)
        frameOrigin = targetDockingDetails["frame"]["originRas"]
        hubDistance = vtk.vtkImplicitPolyDataDistance()
        hubDistance.SetInput(targetDockingAssembly.GetPolyData())
        self.assertGreater(hubDistance.EvaluateFunction(frameOrigin), 1.0)
        self.assertTrue(targetDockingPlane.GetLocked())
        self.assertFalse(targetDockingPlane.GetSelectable())
        targetDockingAssembly.SetAttribute(
            "DENTOBOT.TargetDockingSchemaVersion",
            "1.0",
        )
        legacyDockingSummary = logic.getTargetDockingAssemblySummary(
            targetDockingAssembly
        )
        self.assertEqual(legacyDockingSummary["geometryState"], "Stale")
        self.assertIn("predates collision-aware yaw", legacyDockingSummary["staleReason"])
        targetDockingAssembly.SetAttribute(
            "DENTOBOT.TargetDockingSchemaVersion",
            logic.TARGET_DOCKING_SCHEMA_VERSION,
        )
        with self.assertRaisesRegex(ValueError, "Confirm the collision-screened"):
            logic.createOrUpdateFinalPrintableTemplate(
                patientShell,
                targetDockingAssembly,
                guideTrajectories,
                outerDiameterMm=4.4,
                innerDiameterMm=1.5,
                heightMm=2.5,
                dockingClearanceMm=0.3,
                reinforcementRadialMm=1.0,
                reinforcementDepthMm=2.0,
                samplingSpacingMm=0.3,
            )
        targetDockingAssembly.SetAttribute("DENTOBOT.OrientationState", "Confirmed")
        targetDockingPlane.SetAttribute("DENTOBOT.OrientationState", "Confirmed")
        finalTemplate, guideModels, finalDetails = (
            logic.createOrUpdateFinalPrintableTemplate(
                patientShell,
                targetDockingAssembly,
                guideTrajectories,
                outerDiameterMm=4.4,
                innerDiameterMm=1.5,
                heightMm=2.5,
                dockingClearanceMm=0.3,
                reinforcementRadialMm=1.0,
                reinforcementDepthMm=2.0,
                samplingSpacingMm=0.3,
            )
        )
        finalSummary = logic.getFinalPrintableTemplateSummary(finalTemplate)
        self.assertEqual(finalSummary["geometryState"], "Current")
        self.assertEqual(finalSummary["verificationState"], "NotVerified")
        self.assertIs(finalSummary["patientShell"], patientShell)
        self.assertIs(
            finalSummary["targetDockingAssembly"],
            targetDockingAssembly,
        )
        self.assertEqual(finalSummary["trajectories"], guideTrajectories)
        self.assertEqual(
            finalDetails["assembly"]["targetDocking"][
                "mechanicalSpecification"
            ],
            "ProvisionalResearchFourIndependentOcclusalDocksV2",
        )
        self.assertEqual(
            finalDetails["assembly"]["trajectoryGuide"]["method"],
            "WorldRASTrajectoryGuideSleeveAssembly",
        )
        self.assertEqual(finalDetails["assembly"]["trajectoryCount"], 2)
        self.assertEqual(finalDetails["assembly"]["dockCount"], 4)
        self.assertEqual(
            finalDetails["assembly"]["shellContactBranches"]["branchCount"],
            4,
        )
        self.assertEqual(
            finalDetails["assembly"]["trajectoryGuideExclusion"]["docking"][
                "method"
            ],
            "ProtectedTrajectoryGuideEnvelopeSubtraction",
        )
        self.assertEqual(
            finalDetails["assembly"]["trajectoryGuideExclusion"]["docking"][
                "excludedOccupiedSampleCount"
            ],
            0,
        )
        self.assertEqual(
            finalDetails["assembly"]["trajectoryGuideExclusion"][
                "reinforcement"
            ]["method"],
            "ProtectedTrajectoryGuideEnvelopeSubtraction",
        )
        self.assertEqual(
            finalDetails["fusion"]["boundaryOrNonManifoldEdgeCount"],
            0,
        )
        self.assertEqual(
            finalDetails["fusion"]["occupiedVolumeRegionCount"],
            1,
        )
        self.assertGreaterEqual(finalDetails["fusion"]["surfaceRegionCount"], 1)
        self.assertGreater(finalTemplate.GetPolyData().GetNumberOfCells(), 0)

        collidingDockParameters = normalize_target_docking_parameters(
            pattern_radius_mm=2.0,
            outer_diameter_mm=3.0,
            bore_diameter_mm=1.0,
            connector_diameter_mm=3.5,
            connector_thickness_mm=2.0,
            shared_depth_mm=4.0,
            individual_depths_mm=(4.0, 4.0, 4.0, 4.0),
            individual_depths_enabled=False,
            clearance_mm=0.3,
            reinforcement_radial_mm=1.0,
            processing_resolution_mm=0.3,
        )
        collidingPlane, collidingAssembly, _collidingDetails = (
            logic.createOrUpdateTargetDockingAssembly(
                segmentationNode,
                "tooth-16",
                guideTrajectories,
                collidingDockParameters,
                supportModel=sourceModel,
            )
        )
        collidingAssembly.SetAttribute("DENTOBOT.OrientationState", "Confirmed")
        collidingPlane.SetAttribute("DENTOBOT.OrientationState", "Confirmed")
        with self.assertRaisesRegex(
            ValueError,
            "intersects the protected trajectory-guide envelope",
        ):
            logic.createOrUpdateFinalPrintableTemplate(
                patientShell,
                collidingAssembly,
                guideTrajectories,
                outerDiameterMm=4.4,
                innerDiameterMm=1.5,
                heightMm=2.5,
                dockingClearanceMm=0.3,
                reinforcementRadialMm=1.0,
                reinforcementDepthMm=2.0,
                samplingSpacingMm=0.3,
            )
        collisionRemovals = logic.deleteTargetDockingAssembly(collidingAssembly)
        self.assertEqual(len(collisionRemovals), 15)
        self.assertFalse(slicer.mrmlScene.IsNodePresent(collidingPlane))

        verification = logic.verifyFinalPrintableTemplate(finalTemplate)
        self.assertEqual(verification["overall"], "WARNING")
        self.assertFalse(
            any(check["result"] == "FAIL" for check in verification["checks"])
        )
        exportDirectory = Path(slicer.app.temporaryPath) / (
            f"dentobot-final-export-{uuid.uuid4().hex}"
        )
        exportDirectory.mkdir()
        try:
            exportedPath = logic.exportFinalPrintableTemplateStl(
                exportDirectory,
                finalTemplate,
            )
            self.assertTrue(exportedPath.is_file())
            self.assertEqual(exportedPath.name, "DENTO_Final_Printable_Template.stl")
        finally:
            exportedFile = exportDirectory / "DENTO_Final_Printable_Template.stl"
            exportedFile.unlink(missing_ok=True)
            exportDirectory.rmdir()

        logic.refreshWorkflowNodeStepTags()
        self.assertTrue(targetDockingPlane.GetName().startswith("[Step 4C]"))
        self.assertTrue(targetDockingAssembly.GetName().startswith("[Step 4C]"))
        self.assertTrue(boundary.GetName().startswith("[Step 5A]"))
        self.assertTrue(preview.GetName().startswith("[Step 5A]"))
        self.assertTrue(insertionDirection.GetName().startswith("[Step 5B]"))
        self.assertTrue(undercutModel.GetName().startswith("[Step 5B]"))
        self.assertTrue(blockoutModel.GetName().startswith("[Step 5B]"))
        self.assertTrue(patientShell.GetName().startswith("[Step 5B]"))
        self.assertTrue(finalTemplate.GetName().startswith("[Step 5C]"))
        parameterNode = logic.getParameterNode()
        parameterNode.teethSegmentation = segmentationNode
        parameterNode.draftTemplateSupportModel = sourceModel
        parameterNode.templateSupportBoundaryCurve = boundary
        parameterNode.visibleTemplateSupportModel = preview
        parameterNode.templateInsertionDirection = insertionDirection
        parameterNode.templateUndercutSurfaceModel = undercutModel
        parameterNode.templateUndercutBlockoutModel = blockoutModel
        parameterNode.patientContactShellModel = patientShell
        parameterNode.targetDockingReferencePlane = targetDockingPlane
        parameterNode.targetDockingAssemblyModel = targetDockingAssembly
        parameterNode.templateDockingAssemblyModel = guideModels["docking"]
        parameterNode.templateDockingClearanceModel = guideModels["clearance"]
        parameterNode.templateDockingReinforcementModel = guideModels["reinforcement"]
        parameterNode.templateDockingChannelsModel = guideModels["channels"]
        parameterNode.finalPrintableTemplateModel = finalTemplate
        sourceId = sourceModel.GetID()
        segmentationId = segmentationNode.GetID()

        scenePath = Path(slicer.app.temporaryPath) / (
            f"dentobot-visible-support-{uuid.uuid4().hex}.mrb"
        )
        try:
            self.assertTrue(slicer.util.saveScene(str(scenePath)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(scenePath)))
        finally:
            scenePath.unlink(missing_ok=True)

        reloadedLogic = DENTOWorkflowLogic()
        reloadedParameterNode = reloadedLogic.getParameterNode()
        reloadedBoundary = reloadedParameterNode.templateSupportBoundaryCurve
        reloadedPreview = reloadedParameterNode.visibleTemplateSupportModel
        reloadedInsertion = reloadedParameterNode.templateInsertionDirection
        reloadedUndercut = reloadedParameterNode.templateUndercutSurfaceModel
        reloadedBlockout = reloadedParameterNode.templateUndercutBlockoutModel
        reloadedPatientShell = reloadedParameterNode.patientContactShellModel
        reloadedTargetDocking = reloadedParameterNode.targetDockingAssemblyModel
        reloadedFinalTemplate = reloadedParameterNode.finalPrintableTemplateModel
        reloadedDockingSummary = reloadedLogic.getTargetDockingAssemblySummary(
            reloadedTargetDocking
        )
        self.assertEqual(reloadedDockingSummary["orientationState"], "Confirmed")
        self.assertEqual(len(reloadedDockingSummary["measurementNodes"]), 13)
        self.assertTrue(
            reloadedLogic.isTemplateSupportBoundaryNode(reloadedBoundary)
        )
        self.assertTrue(
            reloadedLogic.isVisibleTemplateSupportModelNode(reloadedPreview)
        )
        reloadedSummary = reloadedLogic.getVisibleTemplateSupportModelSummary(
            reloadedPreview
        )
        self.assertEqual(reloadedSummary["metrics"]["surfaceRegionCount"], 2)
        self.assertEqual(reloadedSummary["metrics"]["omittedToothCount"], 1)
        self.assertTrue(
            reloadedLogic.isDentobotTrajectoryNode(
                reloadedSummary["directionTrajectory"]
            )
        )
        self.assertIs(
            reloadedSummary["insertionDirection"],
            reloadedInsertion,
        )
        reloadedDirectionSummary = (
            reloadedLogic.getTemplateInsertionDirectionSummary(reloadedInsertion)
        )
        self.assertEqual(
            reloadedDirectionSummary["insertionDirectionRas"],
            (0.0, 0.0, -1.0),
        )
        self.assertIs(
            reloadedDirectionSummary["sourceTrajectory"],
            reloadedSummary["directionTrajectory"],
        )
        reloadedBlockoutSummary = reloadedLogic.getTemplateUndercutOutputSummary(
            reloadedBlockout,
            "TemplateUndercutBlockout",
        )
        self.assertIs(reloadedBlockoutSummary["insertionDirection"], reloadedInsertion)
        reloadedShellSummary = reloadedLogic.getPatientContactShellSummary(
            reloadedPatientShell
        )
        self.assertIs(reloadedShellSummary["visibleSupport"], reloadedPreview)
        self.assertIs(reloadedShellSummary["boundary"], reloadedBoundary)
        self.assertIs(reloadedShellSummary["insertionDirection"], reloadedInsertion)
        self.assertIs(reloadedShellSummary["blockoutModel"], reloadedBlockout)
        reloadedFinalSummary = reloadedLogic.getFinalPrintableTemplateSummary(
            reloadedFinalTemplate
        )
        self.assertIs(reloadedFinalSummary["patientShell"], reloadedPatientShell)
        self.assertIs(
            reloadedFinalSummary["targetDockingAssembly"],
            reloadedTargetDocking,
        )
        self.assertEqual(len(reloadedFinalSummary["trajectories"]), 2)
        self.assertEqual(reloadedFinalSummary["verificationState"], "WARNING")
        changedTrajectory = reloadedFinalSummary["trajectories"][0]
        originalEntry = [0.0, 0.0, 0.0]
        changedTrajectory.GetNthControlPointPositionWorld(0, originalEntry)
        movedEntry = list(originalEntry)
        movedEntry[0] += 0.5
        changedTrajectory.SetNthControlPointPositionWorld(0, movedEntry)
        failedVerification = reloadedLogic.verifyFinalPrintableTemplate(
            reloadedFinalTemplate
        )
        self.assertEqual(failedVerification["overall"], "FAIL")
        changedTrajectory.SetNthControlPointPositionWorld(0, originalEntry)
        restoredVerification = reloadedLogic.verifyFinalPrintableTemplate(
            reloadedFinalTemplate
        )
        self.assertEqual(restoredVerification["overall"], "WARNING")
        finalRemovals = reloadedLogic.deleteFinalPrintableTemplate(
            reloadedFinalTemplate
        )
        self.assertEqual(len(finalRemovals), 5)
        self.assertIsNone(reloadedParameterNode.finalPrintableTemplateModel)
        shellRemovals = reloadedLogic.deletePatientContactShell(
            reloadedPatientShell
        )
        self.assertEqual(len(shellRemovals), 6)
        self.assertIsNone(reloadedParameterNode.patientContactShellModel)
        undercutRemovals = reloadedLogic.deleteTemplateUndercutWorkflow(
            reloadedInsertion,
            reloadedUndercut,
            reloadedBlockout,
        )
        self.assertEqual(len(undercutRemovals), 3)
        self.assertIsNone(reloadedParameterNode.templateInsertionDirection)
        self.assertIsNone(reloadedParameterNode.templateUndercutSurfaceModel)
        self.assertIsNone(reloadedParameterNode.templateUndercutBlockoutModel)
        removals = reloadedLogic.deleteTemplateSupportSelection(
            reloadedBoundary,
            reloadedPreview,
        )
        self.assertEqual(len(removals), 2)
        self.assertIsNone(reloadedParameterNode.templateSupportBoundaryCurve)
        self.assertIsNone(reloadedParameterNode.visibleTemplateSupportModel)
        self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(sourceId))
        self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(segmentationId))
        self.delayDisplay(
            "DENTOWorkflow visible crown-support ROI, RAS, persistence, and deletion tests passed"
        )

    def test_DENTOWorkflowTemplateFinalizationCameraMath(self) -> None:
        frame = {
            "center": (10.0, 20.0, 30.0),
            "xAxis": (1.0, 0.0, 0.0),
            "yAxis": (0.0, 1.0, 0.0),
            "zAxis": (0.0, 0.0, 1.0),
            "distance": 100.0,
            "parallelScale": 12.5,
        }
        zeroPose = DENTOWorkflowWidget._templateFinalizationCameraPose(
            frame,
            0.0,
        )
        self.assertEqual(zeroPose["position"], (10.0, -80.0, 30.0))
        self.assertEqual(zeroPose["focalPoint"], frame["center"])
        self.assertEqual(zeroPose["viewUp"], frame["zAxis"])
        self.assertEqual(zeroPose["parallelScale"], 12.5)

        camera = vtk.vtkCamera()
        camera.SetFocalPoint(zeroPose["focalPoint"])
        camera.SetPosition(zeroPose["position"])
        self.assertAlmostEqual(
            DENTOWorkflowWidget._templateFinalizationYawFromCamera(camera, frame),
            0.0,
            places=6,
        )
        quarterTurnPose = DENTOWorkflowWidget._templateFinalizationCameraPose(
            frame,
            90.0,
        )
        self.assertAlmostEqual(quarterTurnPose["position"][0], 110.0, places=6)
        self.assertAlmostEqual(quarterTurnPose["position"][1], 20.0, places=6)
        self.assertAlmostEqual(quarterTurnPose["position"][2], 30.0, places=6)
        camera.SetPosition(quarterTurnPose["position"])
        self.assertAlmostEqual(
            DENTOWorkflowWidget._templateFinalizationYawFromCamera(camera, frame),
            90.0,
            places=6,
        )
        self.delayDisplay("DENTOWorkflow Step 5C ROI-frame camera math tests passed")

    def test_DENTOWorkflowTemplateFinalizationPlaneConstraint(self) -> None:
        slicer.mrmlScene.Clear(0)
        logic = DENTOWorkflowLogic()

        sphere = vtk.vtkSphereSource()
        sphere.SetRadius(10.0)
        sphere.Update()
        sourceShell = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Plane constraint source shell",
        )
        sourceShell.SetAndObservePolyData(sphere.GetOutput())
        sourceShell.SetAttribute("DENTOBOT.ModelRole", "ResearchTemplateShell")
        sourceShell.SetAttribute("DENTOBOT.GeometryState", "Current")

        roiNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsROINode",
            "Plane constraint ROI",
        )
        roiNode.SetAttribute("DENTOBOT.MarkupsRole", "TemplateShellTrimROI")
        roiMatrix = vtk.vtkMatrix4x4()
        roiMatrix.Identity()
        for row, values in enumerate(
            (
                (1.0, 0.0, 0.0, 3.0),
                (0.0, 0.0, 1.0, 4.0),
                (0.0, -1.0, 0.0, 5.0),
            )
        ):
            for column, value in enumerate(values):
                roiMatrix.SetElement(row, column, value)
        roiNode.SetAndObserveObjectToNodeMatrix(roiMatrix)
        roiNode.SetSize(20.0, 30.0, 40.0)
        sourceShell.SetNodeReferenceID(
            logic.TEMPLATE_GUIDE_ROI_REFERENCE_ROLE,
            roiNode.GetID(),
        )

        planeNode = logic.createOrResetTemplateTrimPlane(sourceShell)
        self.assertIs(
            planeNode.GetNodeReference(
                logic.TEMPLATE_FINALIZATION_ROI_REFERENCE_ROLE
            ),
            roiNode,
        )
        planeNode.SetOriginWorld((8.0, 13.0, 20.0))
        constraint = logic.constrainTemplateTrimPlaneToRoi(
            planeNode,
            roiNode,
        )
        self.assertTrue(np.allclose(constraint["zAxis"], (0.0, 1.0, 0.0)))
        self.assertAlmostEqual(constraint["heightMm"], 9.0, places=7)
        self.assertTrue(
            np.allclose(planeNode.GetOriginWorld(), (3.0, 13.0, 5.0))
        )
        self.assertTrue(
            np.allclose(planeNode.GetNormalWorld(), (0.0, 1.0, 0.0))
        )
        self.assertEqual(
            planeNode.GetAttribute(
                "DENTOBOT.TemplateFinalizationPlaneConstraint"
            ),
            "RoiZHeightOnly",
        )
        if hasattr(planeNode, "GetNormalPointRequired"):
            self.assertFalse(planeNode.GetNormalPointRequired())
        self.assertEqual(planeNode.GetRequiredNumberOfControlPoints(), 1)
        self.assertEqual(planeNode.GetMaximumNumberOfControlPoints(), 1)
        self.assertFalse(planeNode.GetLocked())
        self.assertTrue(planeNode.GetSelectable())
        displayNode = planeNode.GetDisplayNode()
        self.assertFalse(displayNode.GetHandlesInteractive())
        self.assertFalse(displayNode.GetTranslationHandleVisibility())
        self.assertFalse(displayNode.GetRotationHandleVisibility())
        self.assertFalse(displayNode.GetScaleHandleVisibility())
        logic.validateTemplateFinalizationEditNode(
            sourceShell,
            planeNode,
            "PlaneCut",
            requireComplete=False,
        )

        planeNode.SetNormalWorld((0.0, 0.0, 1.0))
        with self.assertRaisesRegex(ValueError, "parallel"):
            logic.validateTemplateFinalizationEditNode(
                sourceShell,
                planeNode,
                "PlaneCut",
                requireComplete=False,
            )
        logic.constrainTemplateTrimPlaneToRoi(planeNode, roiNode)
        planeNode.SetOriginWorld((8.0, 13.0, 20.0))
        with self.assertRaisesRegex(ValueError, "ROI Z axis"):
            logic.validateTemplateFinalizationEditNode(
                sourceShell,
                planeNode,
                "PlaneCut",
                requireComplete=False,
            )
        self.delayDisplay("DENTOWorkflow Step 5C plane constraint tests passed")

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
        self.assertTrue(targetBoundsRoi.GetLocked())
        self.assertFalse(targetBoundsRoi.GetSelectable())
        self.assertFalse(targetBoundsRoi.GetDisplayNode().GetHandlesInteractive())
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
        with self.assertRaisesRegex(ValueError, "Step 5B automatic shell bounds ROI"):
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
        with self.assertRaisesRegex(ValueError, "Step 5B automatic shell bounds ROI"):
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
        for workflowRoi in (targetBoundsRoi, roiNode):
            self.assertTrue(workflowRoi.GetLocked())
            self.assertFalse(workflowRoi.GetSelectable())
            self.assertFalse(workflowRoi.GetDisplayNode().GetHandlesInteractive())
            self.assertFalse(
                workflowRoi.GetDisplayNode().GetTranslationHandleVisibility()
            )
            self.assertFalse(
                workflowRoi.GetDisplayNode().GetRotationHandleVisibility()
            )
            self.assertFalse(
                workflowRoi.GetDisplayNode().GetScaleHandleVisibility()
            )
        roiNode.SetLocked(False)
        roiNode.SetSelectable(True)
        roiNode.GetDisplayNode().SetHandlesInteractive(True)
        roiNode.GetDisplayNode().SetTranslationHandleVisibility(True)
        roiNode.GetDisplayNode().SetRotationHandleVisibility(True)
        roiNode.GetDisplayNode().SetScaleHandleVisibility(True)
        logic.refreshWorkflowNodeStepTags()
        self.assertTrue(roiNode.GetLocked())
        self.assertFalse(roiNode.GetSelectable())
        self.assertFalse(roiNode.GetDisplayNode().GetHandlesInteractive())
        unrelatedSupportModel = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Unrelated Step 5A Model",
        )
        roiNode.SetNodeReferenceID(
            logic.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE,
            unrelatedSupportModel.GetID(),
        )
        with self.assertRaisesRegex(ValueError, "different Step 4B"):
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
        self.assertTrue(supportModel.GetName().startswith("[Step 4B]"))
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
            "Automatic shell bounds ROI was deleted.",
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
                "Automatic shell bounds ROI was deleted.",
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
        with self.assertRaisesRegex(ValueError, "DENTOBOT Step 4B"):
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

    def test_DENTOWorkflowTrajectoryBacktrackingAfterSceneReload(self) -> None:
        """Reload two trajectories and delete only one dependency subtree."""

        slicer.mrmlScene.Clear(0)
        logic = DENTOWorkflowLogic()
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "BacktrackingSegmentation",
        )
        segmentationNode.CreateDefaultDisplayNodes()
        segment = slicer.vtkSegment()
        segment.SetName("upper_right_first_premolar_fdi14")
        cube = vtk.vtkCubeSource()
        cube.SetBounds(-2.0, 2.0, -2.0, 2.0, -4.0, 4.0)
        cube.Update()
        segment.AddRepresentation(
            slicer.vtkSegmentationConverter
            .GetSegmentationClosedSurfaceRepresentationName(),
            cube.GetOutput(),
        )
        segmentationNode.GetSegmentation().AddSegment(segment, "tooth-14")
        roiNode, _bounds = logic.createOrUpdateTargetBoundsRoi(
            segmentationNode,
            "tooth-14",
        )

        trajectories = []
        for ordinal, xCoordinate in ((1, -0.5), (2, 0.5)):
            trajectory = logic.createTrajectoryNode(
                f"DENTO Trajectory FDI 14"
            )
            logic.enableAutomaticTrajectoryName(trajectory)
            logic.configureTrajectoryTarget(
                trajectory,
                segmentationNode,
                "tooth-14",
            )
            trajectory.SetNodeReferenceID(
                logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
                roiNode.GetID(),
            )
            trajectory.AddControlPointWorld(
                vtk.vtkVector3d(xCoordinate, 0.0, 3.0)
            )
            trajectory.AddControlPointWorld(
                vtk.vtkVector3d(xCoordinate, 0.0, -3.0)
            )
            trajectories.append(trajectory)
        trajectoryOne, trajectoryTwo = trajectories
        logic.refreshManagedTrajectoryNames()
        self.assertNotEqual(trajectoryOne.GetName(), trajectoryTwo.GetName())
        self.assertIn("Trajectory 1 [Complete]", trajectoryOne.GetName())
        self.assertIn("Trajectory 2 [Complete]", trajectoryTwo.GetName())

        draftModel = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Backtracking draft support",
        )
        draftModel.SetAttribute("DENTOBOT.ModelRole", "TemplateSupportDraft")
        draftModel.SetAndObservePolyData(cube.GetOutput())
        draftModel.CreateDefaultDisplayNodes()

        supportPlane = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsPlaneNode",
            "Backtracking support plane",
        )
        supportPlane.SetAttribute(
            "DENTOBOT.MarkupsRole",
            "TemplateSupportBoundaryPlane",
        )
        supportPlane.SetNodeReferenceID(
            logic.TEMPLATE_SUPPORT_PLANE_SOURCE_TRAJECTORY_REFERENCE_ROLE,
            trajectoryOne.GetID(),
        )
        supportPlane.CreateDefaultDisplayNodes()
        supportCurve = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsClosedCurveNode",
            "Backtracking support curve",
        )
        supportCurve.SetAttribute(
            "DENTOBOT.MarkupsRole",
            "TemplateSupportBoundary",
        )
        supportCurve.SetNodeReferenceID(
            logic.TEMPLATE_SUPPORT_BOUNDARY_INITIALIZER_PLANE_REFERENCE_ROLE,
            supportPlane.GetID(),
        )
        supportCurve.CreateDefaultDisplayNodes()
        visibleSupport = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Backtracking visible support",
        )
        visibleSupport.SetAttribute(
            "DENTOBOT.ModelRole",
            "VisibleTemplateSupportSurface",
        )
        visibleSupport.SetNodeReferenceID(
            logic.TEMPLATE_VISIBLE_SUPPORT_BOUNDARY_REFERENCE_ROLE,
            supportCurve.GetID(),
        )
        visibleSupport.SetNodeReferenceID(
            logic.TEMPLATE_VISIBLE_SUPPORT_DIRECTION_TRAJECTORY_REFERENCE_ROLE,
            trajectoryOne.GetID(),
        )
        visibleSupport.SetAndObservePolyData(cube.GetOutput())
        visibleSupport.CreateDefaultDisplayNodes()

        insertionDirection = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsLineNode",
            "Backtracking insertion direction",
        )
        insertionDirection.SetAttribute(
            "DENTOBOT.MarkupsRole",
            "TemplateInsertionDirection",
        )
        insertionDirection.SetNodeReferenceID(
            logic.TEMPLATE_INSERTION_DIRECTION_SOURCE_TRAJECTORY_REFERENCE_ROLE,
            trajectoryOne.GetID(),
        )
        insertionDirection.CreateDefaultDisplayNodes()
        patientShell = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Backtracking patient shell",
        )
        patientShell.SetAttribute(
            "DENTOBOT.ModelRole",
            "PatientContactShell",
        )
        patientShell.SetNodeReferenceID(
            logic.TEMPLATE_PATIENT_SHELL_SOURCE_SURFACE_REFERENCE_ROLE,
            visibleSupport.GetID(),
        )
        patientShell.SetNodeReferenceID(
            logic.TEMPLATE_PATIENT_SHELL_INSERTION_DIRECTION_REFERENCE_ROLE,
            insertionDirection.GetID(),
        )
        patientShell.SetAndObservePolyData(cube.GetOutput())
        patientShell.CreateDefaultDisplayNodes()

        dockingPlane = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsPlaneNode",
            "Backtracking docking plane",
        )
        dockingPlane.SetAttribute(
            "DENTOBOT.MarkupsRole",
            "TargetDockingReferencePlane",
        )
        dockingPlane.AddNodeReferenceID(
            logic.TARGET_DOCKING_SOURCE_TRAJECTORY_REFERENCE_ROLE,
            trajectoryOne.GetID(),
        )
        dockingPlane.CreateDefaultDisplayNodes()
        dockingAssembly = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "Backtracking docking assembly",
        )
        dockingAssembly.SetAttribute(
            "DENTOBOT.ModelRole",
            "TargetDockingAssembly",
        )
        dockingAssembly.SetNodeReferenceID(
            logic.TARGET_DOCKING_REFERENCE_PLANE_REFERENCE_ROLE,
            dockingPlane.GetID(),
        )
        dockingAssembly.AddNodeReferenceID(
            logic.TARGET_DOCKING_SOURCE_TRAJECTORY_REFERENCE_ROLE,
            trajectoryOne.GetID(),
        )
        dockingAssembly.SetAndObservePolyData(cube.GetOutput())
        dockingAssembly.CreateDefaultDisplayNodes()

        parameterNode = logic.getParameterNode()
        parameterNode.teethSegmentation = segmentationNode
        parameterNode.targetToothSegmentId = "tooth-14"
        parameterNode.targetToothBoundsRoi = roiNode
        parameterNode.trajectoryLine = trajectoryOne
        parameterNode.draftTemplateSupportModel = draftModel
        parameterNode.templateSupportBoundaryPlane = supportPlane
        parameterNode.templateSupportBoundaryCurve = supportCurve
        parameterNode.visibleTemplateSupportModel = visibleSupport
        parameterNode.templateInsertionDirection = insertionDirection
        parameterNode.patientContactShellModel = patientShell
        parameterNode.targetDockingReferencePlane = dockingPlane
        parameterNode.targetDockingAssemblyModel = dockingAssembly
        parameterNode.parameterNode.AddNodeReferenceID(
            logic.TEMPLATE_SELECTED_GUIDE_TRAJECTORY_REFERENCE_ROLE,
            trajectoryOne.GetID(),
        )
        parameterNode.parameterNode.AddNodeReferenceID(
            logic.TEMPLATE_SELECTED_GUIDE_TRAJECTORY_REFERENCE_ROLE,
            trajectoryTwo.GetID(),
        )

        retainedNodeIds = {
            segmentationNode.GetID(),
            roiNode.GetID(),
            draftModel.GetID(),
            trajectoryTwo.GetID(),
        }
        dependentNodeIds = {
            supportPlane.GetID(),
            supportCurve.GetID(),
            visibleSupport.GetID(),
            insertionDirection.GetID(),
            patientShell.GetID(),
            dockingPlane.GetID(),
            dockingAssembly.GetID(),
        }
        trajectoryOneId = trajectoryOne.GetID()
        trajectoryTwoId = trajectoryTwo.GetID()
        scenePath = Path(slicer.app.temporaryPath) / (
            f"dentobot-trajectory-backtrack-{uuid.uuid4().hex}.mrb"
        )
        reloadedPath = Path(slicer.app.temporaryPath) / (
            f"dentobot-trajectory-backtrack-result-{uuid.uuid4().hex}.mrb"
        )
        try:
            self.assertTrue(slicer.util.saveScene(str(scenePath)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(scenePath)))
            reloadedLogic = DENTOWorkflowLogic()
            reloadedParameterNode = reloadedLogic.getParameterNode()
            reloadedTrajectoryOne = slicer.mrmlScene.GetNodeByID(
                trajectoryOneId
            )
            reloadedTrajectoryTwo = slicer.mrmlScene.GetNodeByID(
                trajectoryTwoId
            )
            self.assertTrue(
                reloadedLogic.isDentobotTrajectoryNode(reloadedTrajectoryOne)
            )
            self.assertTrue(
                reloadedLogic.isDentobotTrajectoryNode(reloadedTrajectoryTwo)
            )
            reloadedLogic.refreshManagedTrajectoryNames()
            self.assertNotEqual(
                reloadedTrajectoryOne.GetName(),
                reloadedTrajectoryTwo.GetName(),
            )

            impact = reloadedLogic.getTrajectoryDependentWorkflowImpact(
                reloadedTrajectoryOne
            )
            self.assertTrue(impact["hasDependents"])
            self.assertTrue(impact["flags"]["targetDocking"])
            self.assertTrue(impact["flags"]["supportSelection"])
            self.assertTrue(impact["flags"]["patientShell"])
            deletion = reloadedLogic.deleteTrajectoryDependentWorkflow(
                reloadedTrajectoryOne,
                impact=impact,
            )
            self.assertTrue(dependentNodeIds.issubset(
                set(deletion["removedNodeIds"])
            ))
            for nodeId in dependentNodeIds:
                self.assertIsNone(slicer.mrmlScene.GetNodeByID(nodeId))
            for nodeId in retainedNodeIds:
                self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(nodeId))
            self.assertEqual(
                [
                    node.GetID()
                    for node in reloadedLogic.getSelectedTemplateGuideTrajectories()
                ],
                [trajectoryTwoId],
            )
            reloadedLogic.deleteTrajectoryNode(reloadedTrajectoryOne)
            self.assertIsNone(slicer.mrmlScene.GetNodeByID(trajectoryOneId))
            self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(trajectoryTwoId))
            self.assertIsNone(reloadedParameterNode.trajectoryLine)

            activeImpact = reloadedLogic.getActivePlanningDownstreamImpact()
            self.assertTrue(activeImpact["flags"]["draftSupport"])
            reloadedLogic.deleteActivePlanningDownstreamWorkflow(
                impact=activeImpact
            )
            self.assertIsNone(reloadedParameterNode.draftTemplateSupportModel)
            self.assertIsNotNone(slicer.mrmlScene.GetNodeByID(trajectoryTwoId))

            reloadedParameterNode.trajectoryLine = reloadedTrajectoryTwo
            self.assertTrue(slicer.util.saveScene(str(reloadedPath)))
            slicer.mrmlScene.Clear(0)
            self.assertTrue(slicer.util.loadScene(str(reloadedPath)))
            finalLogic = DENTOWorkflowLogic()
            finalParameterNode = finalLogic.getParameterNode()
            self.assertIs(
                finalParameterNode.trajectoryLine,
                slicer.mrmlScene.GetNodeByID(trajectoryTwoId),
            )
            self.assertIsNone(slicer.mrmlScene.GetNodeByID(trajectoryOneId))
            for nodeId in dependentNodeIds:
                self.assertIsNone(slicer.mrmlScene.GetNodeByID(nodeId))
        finally:
            scenePath.unlink(missing_ok=True)
            reloadedPath.unlink(missing_ok=True)

        self.delayDisplay(
            "DENTOWorkflow trajectory backtracking and saved-scene reload test passed"
        )
