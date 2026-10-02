"""Pure tests for Step 6 planning helpers."""

from pathlib import Path
import ast
import json
import math
import sys
from types import SimpleNamespace
from xml.etree import ElementTree

import numpy as np
import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HELPER_DIRECTORY = REPOSITORY_ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPER_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HELPER_DIRECTORY))

from DENTOStep6Planning import (
    CASE_VIEW_ROLES,
    JointLimitPair,
    MAX_TASK_SPACE_TCP_CANDIDATES,
    TaskSpaceRoi,
    WorkspaceAcceptedSample,
    apply_task_joint_limits_to_display_ranges,
    apply_task_limit_range_to_value,
    build_task_joint_limits_from_parameter_values,
    case_view_present_roles,
    combine_ras_bounds,
    default_task_joint_limits_from_urdf,
    default_task_space_roi_from_incisors,
    deterministic_task_space_tcp_candidates,
    deterministic_joint_workspace_samples_display,
    halton_value,
    evaluate_motion_configuration,
    joint_positions_si_from_display,
    joint_limit_margin_evidence,
    plan_trajectory_motion,
    sample_filtered_tcp_workspace,
    sample_trajectory_world_mm,
    step6_motion_plan_robot_ready,
    validate_planning_context,
)
from DENTORobotPlacement import link_transforms_base_m


URDF_PATH = REPOSITORY_ROOT / "dentobot_description" / "urdf" / "dentobot.urdf"
DESCRIPTION_ROOT = REPOSITORY_ROOT / "dentobot_description"


def test_validate_planning_context_reports_missing_roles() -> None:
    report = validate_planning_context(
        {
            "inputVolume": "vol1",
            "teethSegmentation": "",
            "trajectoryLine": "line1",
            "targetDockingAssemblyModel": "dock1",
            "finalPrintableTemplateModel": "template1",
        },
    )
    assert not report.ready
    assert report.missing_required == ("teethSegmentation",)
    assert "teethSegmentation" in report.message


def test_validate_planning_context_ready_when_all_required_present() -> None:
    roles = {
        "inputVolume": "vol1",
        "teethSegmentation": "seg1",
        "trajectoryLine": "line1",
        "targetDockingAssemblyModel": "dock1",
        "finalPrintableTemplateModel": "template1",
    }
    report = validate_planning_context(roles)
    assert report.ready
    assert report.missing_required == ()
    assert len(report.present) == 5


def test_step6_motion_plan_robot_ready_accepts_ros_or_mrml() -> None:
    assert step6_motion_plan_robot_ready(ros_motion_active=True, mrml_link_count=0)
    assert step6_motion_plan_robot_ready(ros_motion_active=False, mrml_link_count=7)
    assert not step6_motion_plan_robot_ready(ros_motion_active=False, mrml_link_count=0)


def test_case_view_present_roles_lists_linked_package_nodes() -> None:
    roles = case_view_present_roles(
        {
            "inputVolume": "vol1",
            "teethSegmentation": "seg1",
            "trajectoryLine": "line1",
            "targetDockingAssemblyModel": "",
            "finalPrintableTemplateModel": "template1",
            "targetToothBoundsRoi": "roi1",
        },
    )
    assert roles == (
        "inputVolume",
        "teethSegmentation",
        "trajectoryLine",
        "finalPrintableTemplateModel",
        "targetToothBoundsRoi",
    )


def test_case_view_roles_are_case_package_not_phantom() -> None:
    assert "inputVolume" in CASE_VIEW_ROLES
    assert "finalPrintableTemplateModel" in CASE_VIEW_ROLES
    assert "targetToothBoundsRoi" in CASE_VIEW_ROLES
    assert "draftPhantomSkullModel" not in CASE_VIEW_ROLES
    assert "draftPhantomMandibleModel" not in CASE_VIEW_ROLES


def test_step5b_guide_selector_inherits_entry_to_target_trajectories() -> None:
    bootstrap = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "widget_bootstrap.py"
    ).read_text()
    selector_index = bootstrap.index(
        "self.ui.templateGuideTrajectorySelector.addAttribute("
    )
    role_block = bootstrap[selector_index : selector_index + 220]
    assert '"DENTOBOT.TrajectoryRole"' in role_block
    assert '"EntryToTarget"' in role_block
    assert '"EntryTarget"' not in role_block
    build_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "widget_template_build.py"
    ).read_text()
    assert "def _inheritSelectedTemplateGuideTrajectoriesIfNeeded" in build_source
    assert "self._inheritSelectedTemplateGuideTrajectoriesIfNeeded()" in build_source
    assert "selected and all(node in eligible for node in selected)" in build_source


def test_step5c_target_guide_selector_uses_atomic_preverification_activation() -> None:
    ui_root = ElementTree.parse(
        REPOSITORY_ROOT / "DENTOWorkflow" / "Resources" / "UI" / "DENTOWorkflow.ui"
    ).getroot()
    selector = ui_root.find(".//widget[@name='finalVerificationModelSelector']")
    assert selector is not None
    assert selector.get("class") == "QComboBox"

    widget_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "widget_template_finalization.py"
    ).read_text()
    assert "registry[\"prepared_branches\"].items()" in widget_source
    assert "activateDentoCasePreparedBranchForVerification" in widget_source

    logic_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "logic_case_bundle.py"
    ).read_text()
    ready_gate = logic_source.index("if _forVerification:")
    strict_gate = logic_source.index('finalSummary["verificationState"] not in')
    assert ready_gate < strict_gate
    assert "def activateDentoCasePreparedBranchForVerification" in logic_source
    assert 'SetVisibility(nodeId in selectedNodeIds)' in logic_source


def test_step5c_dock_uniqueness_is_scoped_to_the_selected_branch() -> None:
    guide_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "logic_guide.py"
    ).read_text()
    assert "sameBranchModels" in guide_source
    assert 'candidate["trajectories"]' in guide_source
    assert 'GetAttribute("DENTOBOT.PlanningPoseFingerprint")' in guide_source
    assert 'node.GetID() in registeredDockIds' in guide_source
    assert "len(sameBranchModels) == 1" in guide_source
    assert "len(targetDockingModels) == 1" not in guide_source


def test_prepared_branch_activation_restores_target_owned_build_nodes() -> None:
    source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "logic_case_bundle.py"
    ).read_text()
    for assignment in (
        "parameterNode.draftTemplateSupportModel = draftSupport",
        "parameterNode.templateSupportBoundaryCurve = boundaryCurve",
        "parameterNode.visibleTemplateSupportModel = visibleSupport",
        'parameterNode.templateUndercutBlockoutModel = shellSummary["blockoutModel"]',
        "parameterNode.researchTemplateShellModel = researchShell",
        "parameterNode.researchTemplateSleeveModel = researchSleeve",
        "parameterNode.finalizedTemplateShellModel = finalizedShell",
        "parameterNode.templateTrimPlane = trimPlane",
        "parameterNode.templateTrimCurve = trimCurve",
        "parameterNode.targetDockingYawDeg = dockingParameters",
        ') = dockingParameters["configuredIndividualDepthsMm"]',
        "parameterNode.templateSamplingSpacingMm = dockingParameters",
    ):
        assert assignment in source
    assert "activeDockingParameters == dockingParameters" in source
    assert "model_node_ids=[node.GetID() for node in ownedNodes]" in source

    fallback = source[source.index("def activateDentoCaseTrajectory") :]
    for field in (
        "draftTemplateSupportModel",
        "templateSupportBoundaryPlane",
        "templateSupportBoundaryCurve",
        "visibleTemplateSupportModel",
        "templateUndercutSurfaceModel",
        "templateUndercutBlockoutModel",
        "researchTemplateShellModel",
        "researchTemplateSleeveModel",
        "finalizedTemplateShellModel",
        "templateTrimPlane",
        "templateTrimCurve",
    ):
        assert f"parameterNode.{field} = None" in fallback

    planning_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "widget_planning.py"
    ).read_text()
    assert "if segmentId != previousTargetId:" in planning_source
    assert "self._parameterNode.draftTemplateSupportModel = None" in planning_source
    assert "self._parameterNode.visibleTemplateSupportModel = None" in planning_source
    assert "TEMPLATE_FINAL_GUIDE_RESEARCH_SHELL_REFERENCE_ROLE" in source
    assert "TEMPLATE_FINAL_GUIDE_FINALIZED_SHELL_REFERENCE_ROLE" in source


def test_step64_confirmation_keeps_home_context_gates_without_workspace_gate() -> None:
    source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "widget_robot.py"
    ).read_text()
    assert "task_issues = self.logic.confirmedTaskFreshnessIssues(" in source
    button_start = source.index("panel.confirmTaskButton.enabled = bool(")
    prerequisite_start = source.index("confirmation_prerequisites = []")
    confirm_gate = source[button_start:prerequisite_start]
    assert "planning_anatomy_ready" in confirm_gate
    assert "home_runtime_validated" in confirm_gate
    assert "planning_scene_synchronized" in confirm_gate
    assert "workspace_runtime_validated" not in confirm_gate
    assert "assisted_reviewed" not in confirm_gate
    prerequisite_end = source.index("preview_active = bool(", prerequisite_start)
    prerequisites = source[prerequisite_start:prerequisite_end]
    assert "Activate the verified PreparedBranch in 6.0." in prerequisites
    assert "Apply and live-validate Task Home in 6.2." in prerequisites
    assert "Refresh the Case Foundation planning anatomy." in prerequisites
    assert "Complete the authoritative planning-scene audit in 6.1." in prerequisites
    planning_prerequisites_start = source.index(
        "planning_prerequisites = list(confirmation_prerequisites)",
        prerequisite_start,
    )
    confirmation_only = source[prerequisite_start:planning_prerequisites_start]
    assert "workspace" not in confirmation_only.lower()
    assert "assisted_reviewed" not in confirmation_only
    # Operator 2026-10-02: workspace and limit review are optional visuals.
    assert "if not workspace_runtime_validated:" not in prerequisites
    assert "Revalidate or generate workspace evidence in 6.3." not in prerequisites
    assert "if not assisted_reviewed:" not in prerequisites
    assert '" ".join(planning_prerequisites or task_issues)' in prerequisites
    assert '" ".join(confirmation_prerequisites or task_issues)' not in prerequisites


def test_trajectory_guide_bore_policy_is_two_mm_at_persistence_and_ui_boundaries() -> None:
    parameter_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "parameter_state.py"
    ).read_text()
    assert "templateChannelDiameterMm: float = 2.0" in parameter_source
    assert "templateSleeveInnerDiameterMm: float = 2.1" in parameter_source
    generation_source = (
        REPOSITORY_ROOT / "Testing" / "run_dentobot_stage6_target_generation.py"
    ).read_text()
    assert '"minimum_required_mm": 2.0' in generation_source
    assert '"guide_bore": guide_bore' in generation_source
    assert 'getModuleLogic("ROS2")' in generation_source
    assert "def _write_startup_failure_reports" in generation_source
    assert '"startup_error": failure' in generation_source
    assert "def _capture_screenshot_evidence" in generation_source
    assert '"diagnostic_evidence": diagnostic_evidence' in generation_source
    assert "def _target_directory" in generation_source
    assert 'FDI{_target_key(target_fdi)}-step5c.dentocase' in generation_source
    assert '_target_directory(target_fdi) / "screenshots"' in generation_source
    assert '"diagnostics"' in generation_source
    assert "def _write_target_diagnostic" in generation_source
    assert "exportFinalPrintableTemplateStl" in generation_source
    assert '"verified_stl": {' in generation_source
    assert '"saved_sha256":' in generation_source
    assert generation_source.index("exportFinalPrintableTemplateStl") < generation_source.index(
        "prepareDentoCaseSchema3ForSave"
    )
    assert "/workspace/data/Slicer_Saved/SampleStudy1" in generation_source
    assert "RUN_ID = os.environ.get" in generation_source
    assert "camera.SetParallelScale(max(5.0, 0.8 * span))" in generation_source
    assert "view_size = view.size" in generation_source
    assert "host.grab(qt.QRect(origin, view_size))" in generation_source
    docking_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "logic_docking.py"
    ).read_text()
    assert "def canonicalTrajectoryGeometry" in docking_source
    assert "self._registryWorldPoint" in docking_source
    assert "CaseFoundationPreparationMode" in docking_source
    guide_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_guide.py"
    ).read_text()
    assert "Single current-frame target dock" in guide_source
    assert "duplicate for this exact target and trajectory set" in guide_source
    for relative_path in (
        "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_docking.py",
        "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_guide.py",
        "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_template_build.py",
        "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_guide_support_setup.py",
    ):
        assert "canonicalTrajectoryGeometry" in (
            REPOSITORY_ROOT / relative_path
        ).read_text()
    support_setup_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "widget_guide_support_setup.py"
    ).read_text()
    assert "self._caseBundleRestoreDepth > 0" in support_setup_source
    exact_smoke_source = (
        REPOSITORY_ROOT / "Testing" / "run_dentobot_step65_exact_case_smoke.py"
    ).read_text()
    assert "def require_trajectory_guide_bore" in exact_smoke_source
    assert '"guideBore": guide_bore' in exact_smoke_source
    assert '"restoredGuideBore": restored_guide_bore' in exact_smoke_source
    assert "DENTOBOT_ENDPOINT_ONLY" in exact_smoke_source
    assert "def endpoint_only_diagnostic" in exact_smoke_source
    assert '"no approach or drilling planner invocation"' in exact_smoke_source
    assert "DENTOBOT_ENDPOINT_ONLY_COMPLETE" in exact_smoke_source
    assert "P3_MAX_IK_SOLVES = 128" in exact_smoke_source
    assert "P3_HALTON_BASES = (2, 3, 5, 7, 11)" in exact_smoke_source
    assert "P3 active joint range is invalid" in exact_smoke_source
    assert "robot_node.GetJointTypes()" in exact_smoke_source
    assert 'expected_names = set(bridge.ROS2_JOINT_SI_ORDER)' in exact_smoke_source
    assert "joint_type == \"continuous\"" in exact_smoke_source
    assert '"seed_manifest": seeds' in exact_smoke_source
    assert "generic_static_authoritative" in exact_smoke_source
    assert "P3_REVALIDATION_INPUT" in exact_smoke_source
    assert exact_smoke_source.index("endpoint_diagnostic = endpoint_only_diagnostic") < exact_smoke_source.index("facade.generateWorkspaceCloud()")
    assert exact_smoke_source.index(
        "if ENDPOINT_ONLY or INSERTION_ONLY or APPROACH_ONLY:\n        # P3/P4/P5 diagnostics"
    ) < exact_smoke_source.index("selected_before_connect = slicer.util.selectedModule()")
    assert "ephemeral_r4_p3_static_snapshot" in exact_smoke_source
    assert "static_state_only_no_task_home" in exact_smoke_source
    assert "P3 endpoint check has non-confirmation task freshness issues" in exact_smoke_source
    assert "build_task_snapshot(" in exact_smoke_source
    assert "bridge.joint_si_vector(positions_seed), 2.0, False" in exact_smoke_source

    p3_driver_source = (
        REPOSITORY_ROOT / "Testing/run_c1_p3_r4_batch.bash"
    ).read_text()
    assert "setsid ros2 launch dentobot_moveit_config simulation.launch.py" in p3_driver_source
    assert 'kill -TERM -- "-${stack_pid}"' in p3_driver_source
    assert "DENTOBOT_P3_READINESS_ONLY" in p3_driver_source
    assert "DENTOBOT_P3_REVALIDATION_INPUT" in p3_driver_source
    assert "8853f5208a87368d2611fd9c0a9737fe6b73b4da43de6851f4a428adee3f734c" in p3_driver_source
    assert "generateWorkspaceCloud" not in p3_driver_source

    from xml.etree import ElementTree

    ui_path = REPOSITORY_ROOT / "DENTOWorkflow" / "Resources" / "UI" / "DENTOWorkflow.ui"
    tree = ElementTree.parse(ui_path)
    for name in (
        "templateChannelDiameterSpinBox",
        "templateSleeveInnerDiameterSpinBox",
    ):
        widget = next(
            element
            for element in tree.iter("widget")
            if element.get("name") == name
        )
        minimum = widget.find("./property[@name='minimum']/double")
        assert minimum is not None
        assert float(minimum.text) == 2.0
    inner_widget = next(
        element
        for element in tree.iter("widget")
        if element.get("name") == "templateSleeveInnerDiameterSpinBox"
    )
    inner_value = inner_widget.find("./property[@name='value']/double")
    assert inner_value is not None
    assert float(inner_value.text) == 2.1
    guide_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "DENTOGuideGeometry.py"
    ).read_text()
    assert "MINIMUM_TRAJECTORY_BORE_DIAMETER_MM = 2.0" in guide_source
    assert "DEFAULT_TRAJECTORY_BORE_DIAMETER_MM = 2.1" in guide_source
    build_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "widget_template_build.py"
    ).read_text()
    assert "innerBoreMm < MINIMUM_TRAJECTORY_BORE_DIAMETER_MM" in build_source
    assert "spinBox.setReadOnly(False)" in build_source


def test_new_case_dock_and_support_defaults_match_operator_review() -> None:
    parameter_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow"
        / "Resources"
        / "Python"
        / "dentobot_workflow"
        / "parameter_state.py"
    ).read_text()
    assert "targetDockingPatternRadiusMm: float = 10.0" in parameter_source
    assert "targetDockingOuterDiameterMm: float = 3.0" in parameter_source
    assert "targetDockingBoreDiameterMm: float = 1.0" in parameter_source
    assert "targetDockingConnectorDiameterMm: float = 3.5" in parameter_source
    assert "targetDockingConnectorThicknessMm: float = 2.0" in parameter_source
    assert "targetDockingSharedDepthMm: float = 5.0" in parameter_source
    assert "targetDockingYawDeg: float = 35.0" in parameter_source
    assert "targetDockingCollisionClearanceMm: float = 0.5" in parameter_source
    assert "templateSupportPlaneDepthMm: float = 4.0" in parameter_source
    plane_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_guide_support.py"
    ).read_text()
    assert "depthFromEntryMm: float = 4.0" in plane_source

    tree = ElementTree.parse(
        REPOSITORY_ROOT / "DENTOWorkflow/Resources/UI/DENTOWorkflow.ui"
    )
    for name, expected in (
        ("targetDockingPatternRadiusSpinBox", 10.0),
        ("targetDockingBoreDiameterSpinBox", 1.0),
        ("templateSupportPlaneDepthSpinBox", 4.0),
    ):
        widget = next(
            element for element in tree.iter("widget") if element.get("name") == name
        )
        value = widget.find("./property[@name='value']/double")
        assert value is not None
        assert float(value.text) == expected


def test_p3_endpoint_static_revalidation_is_correlated_and_nonplanning() -> None:
    exact_source = (
        REPOSITORY_ROOT / "Testing" / "run_dentobot_step65_exact_case_smoke.py"
    ).read_text()
    module = ast.parse(exact_source)
    functions = {
        node.name: ast.get_source_segment(exact_source, node) or ""
        for node in module.body
        if isinstance(node, ast.FunctionDef)
    }
    endpoint_source = functions["endpoint_only_diagnostic"]
    static_source = functions["_p3_static_state_query"]
    revalidation_source = functions["_p3_revalidation_input"]
    recheck_source = functions["_p3_revalidate_saved_candidates"]
    static_runtime_source = functions["_p3_connect_static_runtime"]
    run_source = functions["run"]
    assert 'validation_kind="static_state"' in static_source
    assert 'phase: str = "drilling"' in static_source
    assert "validate_only=True" in static_source
    assert 'request_id=str(request_id)' in static_source
    assert "sequence=int(sequence)" in static_source
    assert "requested_positions" in static_source
    assert "starting_positions" in static_source
    assert "evaluated_positions" in static_source
    assert "evaluated_sample_index" in static_source
    assert "total_sample_count" in static_source
    assert "checked_samples" in static_source
    assert "guard_session_id" in static_source
    assert "collision_scene_policy_fingerprint" in static_source
    assert "INCONCLUSIVE" in static_source
    admissibility_source = functions["_p3_admissibility"]
    assert "generic_static_valid" not in admissibility_source
    assert "native_fk" not in admissibility_source
    assert "trustworthy_authoritative" in admissibility_source
    assert 'static_query["accepted"] is True' in admissibility_source
    assert "static_state_classification" in endpoint_source or "static_state_classification" in recheck_source
    assert "validate_task_phase_waypoints" not in endpoint_source
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "ComputeMoveItPositionAxisIK"
        for node in ast.walk(ast.parse(recheck_source))
    )
    assert "P3_REVALIDATION_SHA256" in revalidation_source
    assert "read_bytes()" in revalidation_source
    assert "hashlib.sha256" in revalidation_source
    assert "P3_REVALIDATION_MODE" in revalidation_source
    assert "exactly 21 finite canonical J1-J5 vectors" in revalidation_source
    assert "source_candidate_indexes" in recheck_source
    assert "seed_manifest" in recheck_source
    assert "native_fk_evidence" in recheck_source
    assert "static_only=True" in recheck_source
    assert "facade.generateWorkspaceCloud()" not in endpoint_source
    assert exact_source.index(
        "endpoint_diagnostic = endpoint_only_diagnostic"
    ) < exact_source.index("facade.generateWorkspaceCloud()")
    assert "no Home-to-candidate transition" in endpoint_source
    assert "start_joint_command_stream=False" in static_runtime_source
    assert "defer_runtime_acknowledgement=True" in static_runtime_source
    assert "wait_for_collision_guard_world" not in static_runtime_source
    assert "_apply_positions_si" not in static_runtime_source
    assert "plan_moveit" not in static_runtime_source
    endpoint_run = run_source.split("if ENDPOINT_ONLY or INSERTION_ONLY or APPROACH_ONLY:", 1)[1].split(
        "selected_before_connect", 1
    )[0]
    assert "_p3_connect_static_runtime" in endpoint_run
    assert "facade.connect" not in endpoint_run
    assert "saveTaskHome" not in endpoint_run
    assert "applyTaskHome" not in endpoint_run
    assert "generateWorkspaceCloud" not in endpoint_run


def test_p4_insertion_is_bounded_neighbor_seeded_and_read_only() -> None:
    source = (
        REPOSITORY_ROOT / "Testing" / "run_dentobot_step65_exact_case_smoke.py"
    ).read_text()
    functions = {
        node.name: ast.get_source_segment(source, node) or ""
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
    }
    p4 = functions["p4_insertion_diagnostic"]
    construction = functions["_p4_backward_continuation"]
    recover = functions["_p4_recover_segment"]
    ik = functions["_p4_ik_attempt"]
    transition = functions["_p4_transition_query"]
    forward = functions["_p4_forward_guard_validation"]
    visuals = functions["_p4_capture_visual_evidence"]
    assert "P4_MAX_REPRESENTATIVES = 8" in source
    assert "P4_MAX_IK_SOLVES = 1024" in source
    assert "P4_MAX_AXIAL_STEP_MM = 0.25" in source
    assert "P4_MAX_MIDPOINT_REFINEMENTS = 3" in source
    assert "list(reversed(construction[\"backward_states\"]))" in p4
    assert "ComputeMoveItPositionAxisIK" in ik
    assert "seed_positions" in ik
    assert "2.0," in ik and "False," in ik
    assert "P4_MAX_IK_SOLVES" in ik
    assert "P4_MAX_MIDPOINT_REFINEMENTS" in recover
    assert "reversed(forward_fractions[:-1])" in construction
    assert "validation_kind=\"transition\"" in transition
    assert "validate_only=True" in transition
    assert "request_id=str(request_id)" in transition
    assert "starting_positions" in transition
    assert "INCONCLUSIVE" in transition
    assert "preflight_start_positions_si=entry_positions" in forward
    assert "static_only=True" in forward
    assert "No P4 recovered J1-J5 state was applied or rendered." in visuals
    assert "_capture_view" in visuals
    for forbidden in (
        "facade.connect",
        "generateWorkspaceCloud",
        "plan_moveit",
        "apply_joint_positions_si_to_motion_control",
        "start_slicer_joint_command_stream",
    ):
        assert forbidden not in "\n".join((p4, construction, recover, ik, transition, forward, visuals))
    assert "P4 ends before P5" in p4

    names = {"P4_MAX_AXIAL_STEP_MM", "_p4_axial_fractions"}
    extracted = [
        node
        for node in ast.parse(source).body
        if isinstance(node, (ast.Assign, ast.FunctionDef))
        and (
            any(getattr(target, "id", "") in names for target in getattr(node, "targets", ()))
            or getattr(node, "name", "") in names
        )
    ]
    namespace = {"math": math}
    exec(compile(ast.Module(body=extracted, type_ignores=[]), "<p4>", "exec"), namespace)
    length, fractions = namespace["_p4_axial_fractions"](
        (0.0, 0.0, 0.0), (0.0, 0.0, 5.239400689721231)
    )
    assert math.isclose(length, 5.239400689721231)
    assert fractions[0] == 0.0 and fractions[-1] == 1.0
    assert all(
        (right - left) * length <= 0.25 + 1.0e-12
        for left, right in zip(fractions, fractions[1:])
    )

    driver = (REPOSITORY_ROOT / "Testing" / "run_c1_p3_r4_batch.bash").read_text()
    assert "DENTOBOT_P4_INSERTION_INPUT" in driver
    assert "DENTOBOT_P4_OUTPUT_DIR" in driver
    assert "ec6ad4febcf202de3469303f53ceb4d8056f14d2d6e03272a467ba5938fce362" in driver
    assert "DENTOBOT_P4_NATIVE_SOURCE_SHA256" in driver
    assert "DENTOBOT_P4_NATIVE_BINARY_SHA256" in driver
    assert "DENTOBOT_ENDPOINT_ONLY" in driver


def test_p5_approach_is_single_witness_guarded_and_nonapplying() -> None:
    source = (
        REPOSITORY_ROOT / "Testing" / "run_dentobot_step65_exact_case_smoke.py"
    ).read_text()
    functions = {
        node.name: ast.get_source_segment(source, node) or ""
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
    }
    p5 = functions["p5_approach_diagnostic"]
    input_reader = functions["_p5_p4_input"]
    edge_guard = functions["_p5_validate_guard_edges"]
    static_query = functions["_p3_static_state_query"]
    transition_query = functions["_p4_transition_query"]
    run_source = functions["run"]

    assert "P5_INPUT_SHA256" in source
    assert "P5_MAX_P4_WITNESSES = 1" in source
    assert "P5_STAGE1_PLANNING_ATTEMPTS = 1" in source
    assert "P5_STAGE1_ALLOWED_PLANNING_TIME_SEC = 5.0" in source
    assert "P5_APPROACH_INPUT" in source
    assert "3cc1759d1dc5042748d729d5e2a1ae784a94a60d33cb7c8350695b321492bc72" in source
    assert "p4_insertion_r4" in input_reader
    assert "SAMPLED_PASS" in input_reader
    assert "native_fk_evidence" in input_reader
    assert "monitored_joint_positions_si" in p5
    assert "wait_for_monitored_joint_positions_si" in p5
    assert "preflight_start_positions_si=start" in p5
    assert 'phase="approach"' in p5
    assert 'phase="terminal_contact"' in p5
    assert "include_workspace_seeds=False" in p5
    assert "avoid_collisions=False" in p5
    assert "require_generic_static=False" in p5
    assert "plan_moveit_joint_goal" in p5
    assert "plan_moveit_cartesian_path" in p5
    assert "minimum_fraction=1.0" in p5
    assert "stage2_endpoint" in p5
    assert "_p4_fk_residual" in p5
    assert "first_sequence=2" in p5
    assert "validation_kind=\"static_state\"" in static_query
    assert "validation_kind=\"transition\"" in transition_query
    assert "validate_only=True" in static_query
    assert "validate_only=True" in transition_query
    assert "request_id=f\"{request_prefix}-{phase}-edge-{offset + 1}\"" in edge_guard
    assert "INCONCLUSIVE" in edge_guard
    assert "P5 ends before P6/P7" in p5

    diagnostic_run = run_source.split(
        "if ENDPOINT_ONLY or INSERTION_ONLY or APPROACH_ONLY:", 1
    )[1].split("selected_before_connect", 1)[0]
    for forbidden in (
        "facade.connect",
        "saveTaskHome",
        "applyTaskHome",
        "confirmTask",
        "generateWorkspaceCloud",
        "previewPhase",
        "start_slicer_joint_command_stream",
        "_apply_positions_si",
    ):
        assert forbidden not in diagnostic_run

    driver = (REPOSITORY_ROOT / "Testing" / "run_c1_p3_r4_batch.bash").read_text()
    assert "DENTOBOT_P5_APPROACH_INPUT" in driver
    assert "DENTOBOT_P5_OUTPUT_DIR" in driver
    assert "DENTOBOT_P5_NATIVE_SOURCE_SHA256" in driver
    assert "DENTOBOT_P5_NATIVE_BINARY_SHA256" in driver
    assert "approach_branches.json" in driver


def test_p3_admissibility_is_phase_static_only_and_fails_closed() -> None:
    source = (
        REPOSITORY_ROOT / "Testing" / "run_dentobot_step65_exact_case_smoke.py"
    ).read_text()
    tree = ast.parse(source)
    helpers = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_p3_positions_within_ranges", "_p3_admissibility", "_p3_result"}
    ]
    namespace = {"math": math}
    exec(compile(ast.Module(body=helpers, type_ignores=[]), "<p3>", "exec"), namespace)
    positions = {"J1": 0.0}
    ranges = ({"name": "J1", "lower": -1.0, "upper": 1.0},)
    _, accepted = namespace["_p3_admissibility"](
        position_residual_mm=0.01,
        axis_residual_deg=0.01,
        positions=positions,
        ranges=ranges,
        static_query={"trustworthy_authoritative": True, "accepted": True},
    )
    _, rejected = namespace["_p3_admissibility"](
        position_residual_mm=0.01,
        axis_residual_deg=0.01,
        positions=positions,
        ranges=ranges,
        static_query={"trustworthy_authoritative": True, "accepted": False},
    )
    _, unknown = namespace["_p3_admissibility"](
        position_residual_mm=0.01,
        axis_residual_deg=0.01,
        positions=positions,
        ranges=ranges,
        static_query={"trustworthy_authoritative": False, "accepted": None},
    )
    assert accepted  # Generic/static-FK diagnostics are intentionally not gates.
    assert not rejected
    assert not unknown
    assert namespace["_p3_result"](
        {"inconclusive": 1, "admissible": 1}
    ) == "INCONCLUSIVE"


def test_p3_offline_attribution_accepts_only_native_status_rounding() -> None:
    source = (
        REPOSITORY_ROOT / "Testing" / "run_dentobot_step65_exact_case_smoke.py"
    ).read_text()
    module = ast.parse(source)
    names = {
        "P3_MAX_IK_SOLVES",
        "P3_REVALIDATION_SHA256",
        "P3_R4_CASE_SUFFIX",
        "P3_R4_CASE_SHA256",
        "P3_STATUS_VECTOR_REL_TOL",
        "P3_STATUS_VECTOR_ABS_TOL",
        "_p3_exact_vector",
        "_p3_exact_integer",
        "_p3_positions_within_ranges",
        "_p3_admissibility",
        "_p3_reclassify_saved_static_record",
        "_p3_summary",
        "_p3_result",
        "_p3_offline_reclassify_evidence",
    }
    extracted = [
        node
        for node in module.body
        if isinstance(node, (ast.Assign, ast.FunctionDef))
        and (
            any(getattr(target, "id", "") in names for target in getattr(node, "targets", ()))
            or getattr(node, "name", "") in names
        )
    ]
    namespace = {"json": json, "math": math}
    exec(
        compile(ast.Module(body=extracted, type_ignores=[]), "<p3-offline>", "exec"),
        namespace,
    )
    expected = [
        0.1332152122817458,
        0.05514424539772821,
        -0.5860683514818626,
        0.06430881861349524,
        0.805514819841229,
    ]
    serialized = [
        0.133215212282,
        0.0551442453977,
        -0.586068351482,
        0.0643088186135,
        0.805514819841,
    ]
    assert namespace["_p3_exact_vector"](serialized, expected)
    assert not namespace["_p3_exact_vector"](
        [serialized[0] + 1.0e-8, *serialized[1:]], expected
    )
    object_ids = [f"object-{index}" for index in range(31)]
    original_reasons = [
        "static response requested J1-J5 vector is missing or mismatched",
        "static response starting J1-J5 vector is missing or mismatched",
        "static response evaluated J1-J5 vector is missing or mismatched",
        "scene readback is not correlated to this publication/request",
    ]
    record = {
        "candidate_index": 0,
        "source_candidate_index": 0,
        "position_residual_mm": 0.01,
        "axis_residual_deg": 0.01,
        "solution_joint_positions_si": {"J1": expected[0]},
        "joint_bounds_valid": True,
        "phase_static_valid": None,
        "phase_static_authoritative": False,
        "static_state_classification": "INCONCLUSIVE",
        "authoritative_static_valid": None,
        "admissible": False,
        "native_static_evidence": {
            "command_ok": True,
            "request": {
                "request_id": "request-1",
                "validation_kind": "static_state",
                "phase": "drilling",
                "sequence": 1,
                "validate_only": True,
                "task_fingerprint": "task",
                "requested_positions": expected,
            },
            "response": {
                "accepted": True,
                "request_id": "request-1",
                "validation_kind": "static_state",
                "phase": "drilling",
                "sequence": 1,
                "validate_only": True,
                "task_fingerprint": "task",
                "guard_session_id": "session",
                "collision_scene_policy_fingerprint": "policy",
                "requested_positions": serialized,
                "starting_positions": serialized,
                "evaluated_positions": serialized,
                "evaluated_sample_index": 1,
                "total_sample_count": 1,
                "checked_samples": 1,
                "world_object_count": 31,
                "world_objects": [{"id": object_id} for object_id in object_ids],
            },
            "policy_identity": {
                "expected": "policy",
                "configured": "policy",
                "reported": "policy",
                "guard_session_id": "session",
            },
            "scene_acknowledgement": {
                "status": "Mismatch",
                "trusted": False,
                "attribution_allowed": False,
                "readback_correlated": False,
                "mismatches": [
                    "scene readback is not correlated to this publication/request"
                ],
                "expected_object_ids": object_ids,
                "observed_object_ids": object_ids,
                "expected_policy_fingerprint": "policy",
                "observed_policy_fingerprint": "policy",
            },
            "inconclusive_reasons": original_reasons,
        },
    }
    payload = {
        "mode": "p3_endpoint_revalidation_r4",
        "case": "/workspace/data" + namespace["P3_R4_CASE_SUFFIX"],
        "candidate_count": 21,
        "converged_candidate_count": 21,
        "active_joint_ranges": [{"name": "J1", "lower": -1.0, "upper": 1.0}],
        "input": {
            "sha256": namespace["P3_REVALIDATION_SHA256"],
            "candidate_count": namespace["P3_MAX_IK_SOLVES"],
        },
        "native_build_trusted": True,
        "candidates": [],
    }
    for index in range(21):
        candidate = json.loads(json.dumps(record))
        candidate["candidate_index"] = index
        candidate["source_candidate_index"] = index
        candidate["native_static_evidence"]["request"].update(
            {"request_id": f"request-{index + 1}", "sequence": index + 1}
        )
        candidate["native_static_evidence"]["response"].update(
            {"request_id": f"request-{index + 1}", "sequence": index + 1}
        )
        payload["candidates"].append(candidate)
    corrected = namespace["_p3_offline_reclassify_evidence"](
        payload,
        source_path="/evidence/original.json",
        source_sha256="a" * 64,
        case_sha256=namespace["P3_R4_CASE_SHA256"],
    )
    assert corrected["result"] == "PASS"
    assert corrected["phase_static_counts"] == {
        "accepted": 21,
        "rejected": 0,
        "inconclusive": 0,
    }
    assert corrected["candidates"][0]["admissible"] is True
    assert corrected["candidates"][0]["native_static_evidence"]["scene_acknowledgement"]["trusted"]
    bad = json.loads(json.dumps(payload))
    bad["candidates"][0]["native_static_evidence"]["response"]["request_id"] = "stale"
    assert namespace["_p3_offline_reclassify_evidence"](
        bad,
        source_path="/evidence/original.json",
        source_sha256="a" * 64,
        case_sha256=namespace["P3_R4_CASE_SHA256"],
    )["result"] == "INCONCLUSIVE"


def test_static_only_guard_uses_only_the_exact_deferred_scene_audit() -> None:
    source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_robot.py"
    ).read_text()
    mixin = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "RobotLogicMixin"
    )
    method = next(
        node for node in mixin.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "step6GuidanceCollisionObjectIds"
    )
    extracted = ast.Module(
        body=[ast.ClassDef(
            name="ExtractedGuideLookup", bases=[], keywords=[], body=[method],
            decorator_list=[],
        )],
        type_ignores=[],
    )
    namespace = {}
    exec(
        compile(ast.fix_missing_locations(extracted), "<static-guide-audit>", "exec"),
        namespace,
    )

    class Model:
        def GetID(self):
            return "guide-node"

        def GetName(self):
            return "guide-id"

        def GetAttribute(self, name):
            return "FinalPrintableTemplate" if name == "DENTOBOT.ModelRole" else ""

    class Host(namespace["ExtractedGuideLookup"]):
        def __init__(self, audit):
            self.audit = audit

        def collisionSceneAuditRecord(self, _parameter):
            return self.audit

    parameter = SimpleNamespace(
        finalPrintableTemplateModel=Model(),
        draftTemplateSupportModel=None,
        targetDockingAssemblyModel=None,
    )
    record = {
        "source_id": "guide-node",
        "outgoing_collision_object_id": "guide-id",
        "source_role": "verified-final-template",
        "publish_status": "PublishReturnedSuccess",
    }
    deferred = SimpleNamespace(
        status="RuntimeAcknowledgementDeferred",
        runtime_acknowledgement={"status": "Deferred"},
        object_records=(record,),
    )
    host = Host(deferred)
    assert host.step6GuidanceCollisionObjectIds(parameter) == ()
    assert host.step6GuidanceCollisionObjectIds(
        parameter, allow_deferred_static_ack=True
    ) == ("guide-id",)
    host.audit = SimpleNamespace(
        status="RuntimeAcknowledgementDeferred",
        runtime_acknowledgement={"status": "Acknowledged"},
        object_records=(record,),
    )
    assert host.step6GuidanceCollisionObjectIds(
        parameter, allow_deferred_static_ack=True
    ) == ()


def test_legacy_guide_hole_fails_5b_preflight_before_cached_geometry() -> None:
    source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_template_build.py"
    ).read_text()
    assembly_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_template_assembly.py"
    ).read_text()
    classes = [
        node for module in (ast.parse(source), ast.parse(assembly_source))
        for node in module.body if isinstance(node, ast.ClassDef)
        and node.name in {"TemplateBuildWidgetMixin", "TemplateAssemblyWidgetMixin"}
    ]
    methods = [
        node for mixin in classes for node in mixin.body if isinstance(node, ast.FunctionDef)
        and node.name in {
            "_normalizedTemplateDockingParameters",
            "_completeTemplateBuildPreflight",
        }
    ]
    extracted = ast.Module(
        body=[ast.ClassDef(
            name="ExtractedPreflight", bases=[], keywords=[], body=methods,
            decorator_list=[],
        )], type_ignores=[],
    )
    def normalize(**values):
        if values["inner_diameter_mm"] < 2.0:
            raise ValueError("Trajectory guide hole diameter must be at least 2.00 mm.")
        return values
    namespace = {"normalize_docking_parameters": normalize, "_": lambda text: text}
    exec(compile(ast.fix_missing_locations(extracted), "<5b-preflight>", "exec"), namespace)
    host = namespace["ExtractedPreflight"]()
    host.logic = object()
    host._parameterNode = SimpleNamespace(
        templateSleeveOuterDiameterMm=4.4,
        templateSleeveInnerDiameterMm=1.5,
        templateSleeveHeightMm=2.5,
        templateDockingClearanceMm=0.3,
        templateReinforcementRadialMm=1.0,
        templateReinforcementDepthMm=2.0,
        templateSamplingSpacingMm=0.3,
    )
    with pytest.raises(ValueError, match="Unified template dimensions.*Trajectory guide hole"):
        host._completeTemplateBuildPreflight()


def test_stage6_hard_constraints_preserve_depth_and_read_only_provenance() -> None:
    state_source = (
        REPOSITORY_ROOT / "DENTOWorkflow/Resources/Python/DENTOStep6State.py"
    ).read_text()
    robot_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_robot.py"
    ).read_text()
    facade_source = (
        REPOSITORY_ROOT / "DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py"
    ).read_text()
    shell_source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_patient_shell.py"
    ).read_text()
    getter = shell_source[shell_source.index("    def getTemplateInsertionDirectionSummary") :]
    getter = getter[:getter.index("\n    def ", 5)]
    assert 'SIMULATION_TARGET_DEPTH_POLICY = "simulation-target-depth-preserve-request-v2"' in state_source
    assert "SIMULATION_TARGET_DEPTH_CAP_MM" not in state_source
    assert "validate_simulation_target(" in robot_source
    assert "cap_simulation_target(" not in robot_source
    assert "maximumAllowedDrillingDepthMm\": None" in facade_source
    assert '"requestedTargetPreserved": True' in facade_source
    assert "def canonicalInsertionGeometryJson" in shell_source
    assert "def insertionGeometryMatches" in shell_source
    assert "SetNthControlPointLabel" not in getter
    assert "insertionGeometryMatches" in (
        REPOSITORY_ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_template_build.py"
    ).read_text()
    assert "insertionGeometryMatches" in (
        REPOSITORY_ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_guide.py"
    ).read_text()


def test_stage6_target_manifest_requires_each_distinct_campaign_target(tmp_path) -> None:
    testing_directory = REPOSITORY_ROOT / "Testing"
    if str(testing_directory) not in sys.path:
        sys.path.insert(0, str(testing_directory))
    from run_dentobot_stage6_target_matrix import load_case_manifest, run_matrix

    targets = {}
    for fdi in ("31", "32", "11", "12", "13", "14"):
        case = tmp_path / f"FDI{fdi}.dentocase"
        case.touch()
        targets[f"FDI{fdi}"] = str(case)
    manifest = tmp_path / "targets.json"
    manifest.write_text(json.dumps({"targets": targets}), encoding="utf-8")

    loaded = load_case_manifest(manifest)

    assert tuple(loaded) == ("31", "32", "11", "12", "13", "14")
    dry_run = run_matrix(
        manifest,
        tmp_path / "matrix-output",
        slicer="Slicer",
        module_root="DENTOWorkflow",
        runner="runner.py",
        timeout_sec=1,
        dry_run=True,
    )
    assert all(result["status"] == "not-run" for result in dry_run["results"])
    assert (tmp_path / "matrix-output" / "stage6-target-matrix-report.json").is_file()
    del targets["FDI13"]
    manifest.write_text(json.dumps({"targets": targets}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing FDI13"):
        load_case_manifest(manifest)


def test_stage6_target_matrix_requires_complete_saved_case_smoke_evidence() -> None:
    testing_directory = REPOSITORY_ROOT / "Testing"
    if str(testing_directory) not in sys.path:
        sys.path.insert(0, str(testing_directory))
    from run_dentobot_stage6_target_matrix import smoke_report_issues

    report = {
        "targetFdi": "31",
        "guideBore": {
            "channelDiameterMm": 2.0,
            "sleeveInnerDiameterMm": 2.0,
        },
        "guarded_preview_complete": True,
        "guarded_return_home_complete": True,
        "repeat_guarded_preview_complete": True,
        "final_target_position_error_mm": 0.1,
        "repeat_final_target_position_error_mm": 0.1,
        "savedCase": {
            "reopened": True,
            "restoredFdi": "31",
            "restoredPlanSelection": {"state": "locked"},
        },
        "hardware_execution_enabled": False,
    }
    assert smoke_report_issues(report, "31") == ()
    report["guideBore"]["channelDiameterMm"] = 1.9
    assert "report lacks a 2.0 mm trajectory-guide bore" in smoke_report_issues(
        report, "31"
    )


def test_combine_ras_bounds_unions_finite_positive_extent_boxes() -> None:
    combined = combine_ras_bounds(
        (
            (40.0, 50.0, 10.0, 20.0, 0.0, 5.0),
            (45.0, 60.0, 0.0, 12.0, 1.0, 8.0),
            (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            (float("nan"), 1.0, 0.0, 1.0, 0.0, 1.0),
        )
    )
    assert combined == (40.0, 60.0, 0.0, 20.0, 0.0, 8.0)


def test_combine_ras_bounds_returns_none_when_empty() -> None:
    assert combine_ras_bounds(()) is None
    assert combine_ras_bounds(((0.0, 0.0, 0.0, 0.0, 0.0, 0.0),)) is None


def test_default_task_joint_limits_match_five_joints() -> None:
    limits = default_task_joint_limits_from_urdf(URDF_PATH)
    assert limits.joint_1.unit == "deg"
    assert limits.joint_2.unit == "mm"
    assert limits.joint_1.minimum <= limits.joint_1.maximum
    assert len(limits.as_display_vector()) == 5


def test_joint_limit_margin_evidence_converts_si_and_compares_both_envelopes() -> None:
    mechanical = SimpleNamespace(
        joint_1=JointLimitPair(-90.0, 90.0, "deg"),
        joint_2=JointLimitPair(0.0, 100.0, "mm"),
    )
    reviewed = SimpleNamespace(
        joint_1=JointLimitPair(-45.0, 60.0, "deg"),
        joint_2=JointLimitPair(30.0, 80.0, "mm"),
    )
    metadata = {
        "joint_names": ("revolute", "prismatic"),
        "joint_limit_fields": ("joint_1", "joint_2"),
        "display_units": ("deg", "mm"),
        "mechanical_limits": mechanical,
        "task_limits": reviewed,
    }
    evidence = joint_limit_margin_evidence(
        {"revolute": math.radians(75.0), "prismatic": 0.025}, **metadata
    )

    assert evidence is not None
    assert evidence["revolute"]["value_display"] == pytest.approx(75.0)
    assert evidence["revolute"]["mechanical_lower_margin"] == pytest.approx(165.0)
    assert evidence["revolute"]["mechanical_upper_margin"] == pytest.approx(15.0)
    assert evidence["revolute"]["mechanical_within_limits"] is True
    assert evidence["revolute"]["reviewed_task_upper_margin"] == pytest.approx(-15.0)
    assert evidence["revolute"]["reviewed_task_within_limits"] is False
    assert evidence["prismatic"]["value_display"] == pytest.approx(25.0)
    assert evidence["prismatic"]["mechanical_lower_margin"] == pytest.approx(25.0)
    assert evidence["prismatic"]["mechanical_upper_margin"] == pytest.approx(75.0)
    assert evidence["prismatic"]["mechanical_within_limits"] is True
    assert evidence["prismatic"]["reviewed_task_lower_margin"] == pytest.approx(-5.0)
    assert evidence["prismatic"]["reviewed_task_within_limits"] is False
    assert joint_limit_margin_evidence({"revolute": 0.0}, **metadata) is None


def test_joint_limit_margin_evidence_validation_and_epsilon() -> None:
    mechanical = SimpleNamespace(joint_1=JointLimitPair(-90.0, 90.0, "deg"))
    reviewed = SimpleNamespace(joint_1=JointLimitPair(-90.0, 74.999999995, "deg"))
    arguments = {
        "joint_names": ("revolute",),
        "joint_limit_fields": ("joint_1",),
        "display_units": ("deg",),
        "mechanical_limits": mechanical,
        "task_limits": reviewed,
    }

    evidence = joint_limit_margin_evidence(
        {"revolute": math.radians(75.0)}, **arguments
    )
    assert evidence is not None
    assert evidence["revolute"]["reviewed_task_within_limits"] is True
    with pytest.raises(ValueError, match="equal lengths"):
        joint_limit_margin_evidence(
            {"revolute": 0.0}, **{**arguments, "display_units": ()}
        )
    with pytest.raises(ValueError, match="display units"):
        joint_limit_margin_evidence(
            {"revolute": 0.0}, **{**arguments, "display_units": ("rad",)}
        )
    with pytest.raises(ValueError, match="finite"):
        joint_limit_margin_evidence({"revolute": math.nan}, **arguments)


def test_apply_task_joint_limits_clamps_to_mechanical_bounds() -> None:
    urdf_limits = default_task_joint_limits_from_urdf(URDF_PATH)
    narrow = build_task_joint_limits_from_parameter_values(
        j1_min=urdf_limits.joint_1.minimum + 1.0,
        j1_max=urdf_limits.joint_1.maximum - 1.0,
        j2_min=urdf_limits.joint_2.minimum + 0.5,
        j2_max=urdf_limits.joint_2.maximum - 0.5,
        j3_min=urdf_limits.joint_3.minimum + 1.0,
        j3_max=urdf_limits.joint_3.maximum - 1.0,
        j4_min=urdf_limits.joint_4.minimum + 0.5,
        j4_max=urdf_limits.joint_4.maximum - 0.5,
        j5_min=urdf_limits.joint_5.minimum + 0.5,
        j5_max=urdf_limits.joint_5.maximum - 0.5,
    )
    clamped = apply_task_joint_limits_to_display_ranges(narrow, urdf_limits)
    assert len(clamped.as_display_vector()) == 5


def test_apply_task_joint_limits_rejects_inverted_range() -> None:
    urdf_limits = default_task_joint_limits_from_urdf(URDF_PATH)
    invalid = build_task_joint_limits_from_parameter_values(
        j1_min=100.0,
        j1_max=-100.0,
        j2_min=urdf_limits.joint_2.minimum,
        j2_max=urdf_limits.joint_2.maximum,
        j3_min=urdf_limits.joint_3.minimum,
        j3_max=urdf_limits.joint_3.maximum,
        j4_min=urdf_limits.joint_4.minimum,
        j4_max=urdf_limits.joint_4.maximum,
        j5_min=urdf_limits.joint_5.minimum,
        j5_max=urdf_limits.joint_5.maximum,
    )
    with pytest.raises(ValueError, match="exceeds mechanical range"):
        apply_task_joint_limits_to_display_ranges(invalid, urdf_limits)


def test_apply_task_limit_range_to_value_clamps_and_rejects_inverted() -> None:
    lo, hi, value = apply_task_limit_range_to_value(
        0.0,
        JointLimitPair(10.0, 20.0, "deg"),
    )
    assert (lo, hi, value) == (10.0, 20.0, 10.0)
    _lo, _hi, value = apply_task_limit_range_to_value(
        25.0,
        JointLimitPair(10.0, 20.0, "deg"),
    )
    assert value == 20.0
    with pytest.raises(ValueError, match="inverted"):
        apply_task_limit_range_to_value(0.0, JointLimitPair(20.0, 10.0, "deg"))


def test_step6_joint_limit_ui_merges_min_value_max_rows() -> None:
    from xml.etree import ElementTree

    ui_path = (
        REPOSITORY_ROOT / "DENTOWorkflow" / "Resources" / "UI" / "DENTOWorkflow.ui"
    )
    tree = ElementTree.parse(ui_path)
    names = {element.get("name") for element in tree.iter() if element.get("name")}
    assert "robotJointControlGroupBox" not in names
    assert "step6JointValueHeaderLabel" in names
    for index in range(1, 6):
        assert f"robotJoint{index}TaskMinSpinBox" in names
        assert f"robotJoint{index}SpinBox" in names
        assert f"robotJoint{index}TaskMaxSpinBox" in names
    assert "step6WorkspaceGroupBox" in names
    assert "robotWorkspaceSampleCountSpinBox" in names
    assert "generateRobotWorkspaceButton" in names
    assert "clearRobotWorkspaceButton" in names
    grid = tree.find(".//layout[@name='step6TaskJointLimitsGridLayout']")
    assert grid is not None
    j1_columns = {}
    for item in grid.findall("item"):
        widget = item.find("widget")
        if widget is None:
            continue
        name = widget.get("name")
        if name in {
            "robotJoint1TaskMinSpinBox",
            "robotJoint1SpinBox",
            "robotJoint1TaskMaxSpinBox",
        }:
            j1_columns[name] = (item.get("row"), int(item.get("column")))
    assert j1_columns["robotJoint1TaskMinSpinBox"][0] == j1_columns["robotJoint1SpinBox"][0]
    assert j1_columns["robotJoint1SpinBox"][0] == j1_columns["robotJoint1TaskMaxSpinBox"][0]
    assert (
        j1_columns["robotJoint1TaskMinSpinBox"][1]
        < j1_columns["robotJoint1SpinBox"][1]
        < j1_columns["robotJoint1TaskMaxSpinBox"][1]
    )


def test_sample_trajectory_world_mm_linear_interpolation() -> None:
    samples = sample_trajectory_world_mm(
        entry_ras_mm=(0.0, 0.0, 0.0),
        target_ras_mm=(10.0, 0.0, 0.0),
        sample_count=3,
    )
    assert len(samples) == 3
    assert np.allclose(samples[0], (0.0, 0.0, 0.0))
    assert np.allclose(samples[1], (5.0, 0.0, 0.0))
    assert np.allclose(samples[2], (10.0, 0.0, 0.0))


def test_canonical_drill_tcp_matches_reference_tip_and_rejects_extra_joint() -> None:
    zero = link_transforms_base_m(URDF_PATH, DESCRIPTION_ROOT, {})
    with pytest.raises(ValueError, match="exactly"):
        link_transforms_base_m(
            URDF_PATH, DESCRIPTION_ROOT, {"unexpected_joint": 1.1}
        )
    assert np.allclose(
        zero["dentobot_drill_tcp"],
        zero["dentobot_drill_tip_provisional"],
        atol=1.0e-12,
    )


def test_halton_workspace_sampling_is_deterministic_and_bounded() -> None:
    limits = default_task_joint_limits_from_urdf(URDF_PATH)
    first = deterministic_joint_workspace_samples_display(
        limits,
        12,
        current_display_joints=(0.0, 20.0, 10.0, 20.0, 5.0),
    )
    second = deterministic_joint_workspace_samples_display(
        limits,
        12,
        current_display_joints=(0.0, 20.0, 10.0, 20.0, 5.0),
    )
    assert first == second
    assert len(first) == 12
    minimums = limits.as_display_vector()
    maximums = limits.as_display_max_vector()
    for sample in first:
        assert all(
            minimum <= value <= maximum
            for value, minimum, maximum in zip(sample, minimums, maximums)
        )
    assert halton_value(1, 2) == pytest.approx(0.5)
    assert halton_value(2, 2) == pytest.approx(0.25)


def test_task_space_roi_halton_candidates_are_deterministic_and_strictly_inside() -> None:
    roi = TaskSpaceRoi(
        center_world_ras_mm=(10.0, -20.0, 30.0),
        dimensions_mm=(200.0, 100.0, 60.0),
    )
    axis = (0.0, 0.0, -2.0)
    first = deterministic_task_space_tcp_candidates(
        roi, 64, confirmed_drill_axis_world_ras=axis
    )
    second = deterministic_task_space_tcp_candidates(
        roi, 64, confirmed_drill_axis_world_ras=axis
    )

    assert first == second
    assert len(first) == 64
    assert all(
        roi.contains_world_ras_mm(sample.position_world_ras_mm) for sample in first
    )
    assert all(
        sample.drill_axis_world_ras_unit == (0.0, 0.0, -1.0)
        for sample in first
    )
    assert all(
        lower < coordinate < upper
        for sample in first
        for point in (sample.position_world_ras_mm,)
        for coordinate, lower, upper in zip(
            point,
            (-90.0, -70.0, 0.0),
            (110.0, 30.0, 60.0),
        )
    )


@pytest.mark.parametrize(
    "dimensions",
    ((0.0, 1.0, 1.0), (-1.0, 1.0, 1.0), (1.0, float("inf"), 1.0)),
)
def test_task_space_roi_rejects_nonpositive_or_nonfinite_dimensions(dimensions) -> None:
    with pytest.raises(ValueError):
        TaskSpaceRoi(center_world_ras_mm=(0.0, 0.0, 0.0), dimensions_mm=dimensions)


@pytest.mark.parametrize(
    "center",
    ((0.0, 0.0), (0.0, float("nan"), 0.0), (0.0, float("inf"), 0.0)),
)
def test_task_space_roi_rejects_invalid_world_ras_center(center) -> None:
    with pytest.raises(ValueError):
        TaskSpaceRoi(center_world_ras_mm=center)


def test_default_task_space_roi_from_opened_incisors() -> None:
    roi = default_task_space_roi_from_incisors(
        upper_incisor_world_ras_mm=(2.0, 4.0, -6.0),
        opened_lower_incisor_world_ras_mm=(8.0, 10.0, 2.0),
    )
    assert roi.center_world_ras_mm == (5.0, 7.0, -2.0)
    assert roi.dimensions_mm == (200.0, 200.0, 200.0)

    with pytest.raises(ValueError):
        default_task_space_roi_from_incisors((1.0, 2.0), (3.0, 4.0, 5.0))
    with pytest.raises(ValueError):
        default_task_space_roi_from_incisors(
            (1.0, 2.0, 3.0), (3.0, float("nan"), 5.0)
        )


def test_task_space_roi_rejects_candidate_counts_outside_the_bound() -> None:
    roi = TaskSpaceRoi(center_world_ras_mm=(0.0, 0.0, 0.0))
    axis = (0.0, 0.0, 1.0)

    with pytest.raises(ValueError):
        deterministic_task_space_tcp_candidates(
            roi, 0, confirmed_drill_axis_world_ras=axis
        )
    with pytest.raises(ValueError):
        deterministic_task_space_tcp_candidates(
            roi,
            MAX_TASK_SPACE_TCP_CANDIDATES + 1,
            confirmed_drill_axis_world_ras=axis,
        )


@pytest.mark.parametrize(
    "axis",
    ((0.0, 0.0, 0.0), (1.0, float("nan"), 0.0), (1.0, 2.0)),
)
def test_task_space_tcp_candidates_reject_invalid_confirmed_axis(axis) -> None:
    roi = TaskSpaceRoi(center_world_ras_mm=(0.0, 0.0, 0.0))

    with pytest.raises(ValueError):
        deterministic_task_space_tcp_candidates(
            roi, 1, confirmed_drill_axis_world_ras=axis
        )


def test_task_space_tcp_candidates_require_confirmed_drill_axis() -> None:
    roi = TaskSpaceRoi(center_world_ras_mm=(0.0, 0.0, 0.0))

    with pytest.raises(TypeError):
        deterministic_task_space_tcp_candidates(roi, 1)


def test_filtered_workspace_uses_fk_and_reports_all_requested_samples() -> None:
    limits = default_task_joint_limits_from_urdf(URDF_PATH)
    completed = []
    result = sample_filtered_tcp_workspace(
        limits=limits,
        sample_count=10,
        current_display_joints=(0.0, 20.0, 10.0, 20.0, 5.0),
        urdf_path=URDF_PATH,
        package_root=DESCRIPTION_ROOT,
        base_world_matrix=np.eye(4, dtype=float),
        coarse_self_clearance_mm=0.0,
        environment_points_mm=np.zeros((0, 3), dtype=float),
        environment_clearance_mm=2.0,
        progress=lambda done, total: completed.append((done, total)),
    )
    assert completed == [(10, 10)]
    assert result.requested_count == 10
    assert result.accepted_count == 10
    assert result.self_collision_rejections == 0
    assert result.environment_rejections == 0
    assert all(len(point) == 3 for point in result.accepted_tcp_base_mm)
    assert len(result.accepted_samples) == 10
    assert all(len(sample.joint_display) == 5 for sample in result.accepted_samples)
    assert all(len(sample.joint_positions_si) == 5 for sample in result.accepted_samples)


def test_workspace_sample_requires_canonical_exact_five_joint_values() -> None:
    joint_names = (
        "link-1_Revolute-1",
        "link-2_Slider-2",
        "link-3_Revolute-3",
        "link-4_Slider-4",
        "link-5_Revolute-5",
    )
    values = (0.1, 0.02, -0.3, 0.04, 0.5)
    canonical = WorkspaceAcceptedSample(
        tcp_base_mm=(1.0, 2.0, 3.0),
        joint_display=(0.0, 0.0, 0.0, 0.0, 0.0),
        joint_positions_si=tuple(zip(joint_names, values)),
    )
    extra_value = WorkspaceAcceptedSample(
        tcp_base_mm=(1.0, 2.0, 3.0),
        joint_display=(0.0, 0.0, 0.0, 0.0, 0.0),
        joint_positions_si=tuple(
            zip((*joint_names, "unexpected_joint"), (*values, 0.0))
        ),
    )
    assert canonical.joint_positions_si_dict() == dict(zip(joint_names, values))
    with pytest.raises(ValueError, match="exactly"):
        extra_value.joint_positions_si_dict()


def test_coarse_guard_excludes_known_baseline_false_positives_but_rejects_others() -> None:
    neutral_ok, neutral_reason, _neutral_tcp = evaluate_motion_configuration(
        joint_positions_si_from_display(0.0, 0.0, 0.0, 0.0, 0.0),
        urdf_path=URDF_PATH,
        package_root=DESCRIPTION_ROOT,
        base_world_matrix=np.eye(4, dtype=float),
        coarse_clearance_mm=0.0,
        environment_points_mm=None,
        environment_clearance_mm=2.0,
    )
    assert neutral_ok
    assert neutral_reason == ""

    colliding_display = (
        19.619997799988266,
        35.55555555555556,
        225.53998591992487,
        42.857142857142854,
        129.82908450905677,
    )
    collision_ok, collision_reason, _collision_tcp = evaluate_motion_configuration(
        joint_positions_si_from_display(*colliding_display),
        urdf_path=URDF_PATH,
        package_root=DESCRIPTION_ROOT,
        base_world_matrix=np.eye(4, dtype=float),
        coarse_clearance_mm=5.0,
        environment_points_mm=None,
        environment_clearance_mm=2.0,
    )
    assert not collision_ok
    assert "self-collision" in collision_reason.lower()


def test_case_foundation_plane_reparent_preserves_world_normal() -> None:
    source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_case_foundation.py"
    ).read_text()
    mixin = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "CaseFoundationLogicMixin"
    )
    method = next(
        node for node in mixin.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_reparentCaseFoundationNodePreservingWorld"
    )
    extracted = ast.Module(
        body=[ast.ClassDef(
            name="CaseFoundationStub", bases=[], keywords=[], body=[method],
            decorator_list=[],
        )], type_ignores=[],
    )
    namespace = {"_": lambda message: message}
    exec(compile(ast.fix_missing_locations(extracted), "<jaw-reparent>", "exec"), namespace)
    parent = SimpleNamespace(GetID=lambda: "opened-jaw")

    class PlaneStub:
        parent = None
        point = (-95.5, -71.7, 31.2)
        normal = (0.05, -0.74, -0.67)

        def IsA(self, class_name):
            return class_name in ("vtkMRMLMarkupsNode", "vtkMRMLMarkupsPlaneNode")

        def GetParentTransformNode(self):
            return self.parent

        def GetNumberOfControlPoints(self):
            return 1

        def GetNthControlPointPositionWorld(self, index, result):
            result[:] = self.point

        def SetAndObserveTransformNodeID(self, node_id):
            self.parent = parent if node_id else None
            self.normal = (0.06, -1.0, 0.0)  # Jaw rotation without normal restoration.

        def SetNthControlPointPositionWorld(self, index, *point):
            self.point = point

        def GetNormalWorld(self):
            return self.normal

        def SetNormalWorld(self, normal):
            self.normal = tuple(normal)

    plane = PlaneStub()
    world_point, world_normal = plane.point, plane.normal
    namespace["CaseFoundationStub"]()._reparentCaseFoundationNodePreservingWorld(
        plane, parent
    )
    assert plane.point == world_point
    assert plane.normal == world_normal


def test_assisted_limit_review_preserves_home_and_proposal_only_fingerprint() -> None:
    source = (
        REPOSITORY_ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_robot.py"
    ).read_text()
    mixin = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "RobotLogicMixin"
    )
    methods = [
        node for node in mixin.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {
            "step6TaskLimitsFingerprint",
            "proposeAssistedTaskLimits",
            "reviewAndApplyAssistedTaskLimits",
        }
    ]

    class Limit:
        def __init__(self, minimum, maximum, unit):
            self.minimum, self.maximum, self.unit = minimum, maximum, unit

    mechanical = SimpleNamespace(
        joint_1=Limit(-180.0, 180.0, "deg"),
        joint_2=Limit(0.0, 80.0, "mm"),
        joint_3=Limit(-180.0, 180.0, "deg"),
        joint_4=Limit(0.0, 80.0, "mm"),
        joint_5=Limit(-180.0, 180.0, "deg"),
        as_display_vector=lambda: (-180.0, 0.0, -180.0, 0.0, -180.0),
        as_display_max_vector=lambda: (180.0, 80.0, 180.0, 80.0, 180.0),
    )
    namespace = {
        "json": json,
        "math": math,
        "_": lambda message: message,
        "default_task_joint_limits_from_urdf": lambda _path: mechanical,
        "canonical_json": lambda value: json.dumps(value, sort_keys=True),
        "fingerprint": lambda value: json.dumps(value, sort_keys=True),
        "build_assisted_limit_proposal": lambda *args, **kwargs: SimpleNamespace(
            to_dict=lambda: {"revision": kwargs["revision"], "reviewed": False}
        ),
    }
    extracted = ast.Module(
        body=[ast.ClassDef(
            name="ExtractedRobotLogic", bases=[], keywords=[], body=methods,
            decorator_list=[],
        )],
        type_ignores=[],
    )
    exec(
        compile(ast.fix_missing_locations(extracted), "<assisted-limit-review>", "exec"),
        namespace,
    )

    class Host(namespace["ExtractedRobotLogic"]):
        def __init__(self, parameter, home, limits):
            self.parameter, self.home, self.limits = parameter, home, limits
            self.invalidations = []

        def robotDescriptionPaths(self):
            return ("robot.urdf", "")

        def taskHomeFreshnessIssues(self, _parameter):
            return ()

        def taskHomeRecord(self, _parameter):
            return self.home

        def invalidateStep6TaskConfirmation(self, _parameter, reason):
            self.invalidations.append(reason)

        def getTaskJointLimits(self, _parameter):
            return self.limits

    parameter = SimpleNamespace(
        step6AssistedLimitProposalJson=json.dumps({
            "minimum_display": [-90, 10, -90, 0, -90],
            "maximum_display": [90, 20, 90, 80, 90],
        }),
        robotJoint1TaskMinDeg=-90.0,
        robotJoint1TaskMaxDeg=90.0,
        robotJoint2TaskMinMm=0.0,
        robotJoint2TaskMaxMm=80.0,
        robotJoint3TaskMinDeg=-90.0,
        robotJoint3TaskMaxDeg=90.0,
        robotJoint4TaskMinMm=0.0,
        robotJoint4TaskMaxMm=80.0,
        robotJoint5TaskMinDeg=-90.0,
        robotJoint5TaskMaxDeg=90.0,
    )
    home = SimpleNamespace(
        joint_positions_si=(0.0, 0.030, 0.0, 0.040, 0.0),
    )
    limits = SimpleNamespace(
        as_display_vector=lambda: (-90.0, 0.0, -90.0, 0.0, -90.0),
        as_display_max_vector=lambda: (90.0, 80.0, 90.0, 80.0, 90.0),
    )
    host = Host(parameter, home, limits)
    original_proposal = parameter.step6AssistedLimitProposalJson

    with pytest.raises(ValueError, match="excludes the current Task Home"):
        host.reviewAndApplyAssistedTaskLimits(parameter)
    assert parameter.step6AssistedLimitProposalJson == original_proposal
    assert (parameter.robotJoint2TaskMinMm, parameter.robotJoint2TaskMaxMm) == (0.0, 80.0)
    assert host.invalidations == []

    before = host.step6TaskLimitsFingerprint(parameter)
    parameter.step6AssistedLimitProposalJson = '{"revision":99}'
    assert host.step6TaskLimitsFingerprint(parameter) == before
    host.proposeAssistedTaskLimits(
        parameter, SimpleNamespace(accepted_joint_display_vectors=((0, 30, 0, 40, 0),))
    )
    assert host.invalidations == []
    assert host.step6TaskLimitsFingerprint(parameter) == before

    parameter.step6AssistedLimitProposalJson = json.dumps({
        "minimum_display": [-90, 0, -90, 0, -90],
        "maximum_display": [90, 80, 90, 80, 90],
    })
    applied = host.reviewAndApplyAssistedTaskLimits(parameter)
    assert applied["reviewed"]
    assert host.invalidations == ["Reviewed task limits changed."]


def _exact_case_runner_helper(name):
    path = REPOSITORY_ROOT / "Testing" / "run_dentobot_step65_exact_case_smoke.py"
    tree = ast.parse(path.read_text())
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    module = ast.Module(body=[function], type_ignores=[])
    namespace = {"math": math, "RuntimeError": RuntimeError, "ValueError": ValueError}
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return namespace[name]


def test_exact_case_runner_expected_fdi_fails_closed_for_fdi11_campaign() -> None:
    require_fdi = _exact_case_runner_helper("require_expected_fdi")
    require_fdi("11", "11")
    require_fdi("11", "FDI11")
    require_fdi("31", "")
    with pytest.raises(RuntimeError, match="expected FDI 11"):
        require_fdi("31", "11")


def test_exact_case_runner_guide_warning_expectation_is_opt_in() -> None:
    source = (
        REPOSITORY_ROOT / "Testing" / "run_dentobot_step65_exact_case_smoke.py"
    ).read_text()
    parse_count = _exact_case_runner_helper(
        "parse_expected_guide_clearance_warning_count"
    )
    require_count = _exact_case_runner_helper(
        "require_expected_guide_clearance_warning_count"
    )
    assert parse_count("") is None
    assert parse_count(" 0 ") == 0
    assert parse_count("2") == 2
    require_count(0, None)
    require_count(3, None)
    require_count(0, 0)
    with pytest.raises(RuntimeError, match="expected 1, observed 0"):
        require_count(0, 1)
    with pytest.raises(ValueError, match="non-negative integer"):
        parse_count("-1")
    assert "if preflight_warning_count <= 0" not in source
    assert "require_expected_guide_clearance_warning_count(" in source
    assert '"preflight_guide_clearance_warnings": preflight_warning_details' in source


def test_exact_case_interruption_requires_prefix_and_blocks_return_and_repeat() -> None:
    validate = _exact_case_runner_helper("validate_interruption_evidence")
    home = {"j1": 0.0, "j2": 0.01}
    accepted = {"j1": 0.1, "j2": 0.01}
    evidence = {
        "status": "Incomplete",
        "endpointVerified": False,
        "acceptedWaypointCount": 1,
        "acceptedPrefix": [
            {"phase": "home", "positionsSi": home},
            {"phase": "approach", "positionsSi": accepted},
        ],
        "capturedHomePositionsSi": home,
        "pendingRequest": {
            "phase": "approach",
            "sequence": 7,
            "requestedPositionsSi": accepted,
        },
        "pendingRequestOutcome": {"accepted": True, "sequence": 7},
        "firstRejected": None,
    }
    result = validate(
        evidence,
        accepted,
        dict(accepted),
        SimpleNamespace(
            success=False,
            code="guarded_return_partial_phase",
            message="blocked",
        ),
        SimpleNamespace(
            success=False,
            code="incomplete_preview_blocks_motion",
            message="blocked",
        ),
    )
    assert result["accepted_waypoint_count"] == 1
    assert result["pending_request_outcome"] == evidence["pendingRequestOutcome"]
    assert result["return_home"]["blocked"]
    assert result["repeat_preview"]["blocked"]
    assert result["accepted_state_unchanged_after_blocked_actions"]
    assert result["no_home_teleport"]

    evidence["acceptedWaypointCount"] = 0
    with pytest.raises(RuntimeError, match="accepted preview prefix"):
        validate(
            evidence,
            accepted,
            accepted,
            SimpleNamespace(success=False, code="guarded_return_partial_phase", message=""),
            SimpleNamespace(success=False, code="incomplete_preview_blocks_motion", message=""),
        )


def test_exact_case_interruption_is_a_separate_non_complete_cycle_mode() -> None:
    source = (
        REPOSITORY_ROOT / "Testing" / "run_dentobot_step65_exact_case_smoke.py"
    ).read_text()
    assert 'os.environ.get("DENTOBOT_STEP65_INTERRUPTION_ONLY", "") == "1"' in source
    assert 'EXPECTED_FDI.removeprefix("FDI") != "11"' in source
    assert "separate fresh-process run" in source
    assert '"full_workflow_claimed": False' in source
    assert '"guarded_preview_complete": False' in source
    assert '"guarded_return_home_complete": False' in source
    assert '"repeat_guarded_preview_complete": False' in source
    start = source.index('    if INTERRUPTION_ONLY:\n        full_task_status =')
    end = source.index("    approach_finished = []", start)
    branch = source[start:end]
    assert "if int(index) > 0" in branch
    assert "widget._onStep6StopPreview()" in branch
    assert branch.index("widget._onStep6StopPreview()") < branch.index(
        "facade.returnToTaskHome()"
    )
    assert branch.index("facade.returnToTaskHome()") < branch.index(
        'facade.previewPhase("approach", interval_ms=50)'
    )
    assert "DENTOBOT_STEP65_INTERRUPTION_ONLY_PASS" in source
    assert "DENTOBOT_STEP65_INTERRUPTION_ONLY_FAILED" in source
    assert "DENTOBOT_STEP65_EXACT_CASE_PASS" in source
