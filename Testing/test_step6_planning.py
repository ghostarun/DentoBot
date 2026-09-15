"""Pure tests for Step 6 planning helpers."""

from pathlib import Path
import json
import sys

import numpy as np
import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HELPER_DIRECTORY = REPOSITORY_ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPER_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HELPER_DIRECTORY))

from DENTOStep6Planning import (
    CASE_VIEW_ROLES,
    JointLimitPair,
    WorkspaceAcceptedSample,
    apply_task_joint_limits_to_display_ranges,
    apply_task_limit_range_to_value,
    build_task_joint_limits_from_parameter_values,
    case_view_present_roles,
    combine_ras_bounds,
    default_task_joint_limits_from_urdf,
    deterministic_joint_workspace_samples_display,
    halton_value,
    evaluate_motion_configuration,
    joint_positions_si_from_display,
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
    assert "templateSleeveInnerDiameterMm: float = 2.0" in parameter_source
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
    assert "no closed-jaw duplicate" in guide_source
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


def test_new_dock_defaults_match_latest_saved_fdi31_case() -> None:
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
    assert "targetDockingBoreDiameterMm: float = 1.5" in parameter_source
    assert "targetDockingConnectorDiameterMm: float = 3.5" in parameter_source
    assert "targetDockingConnectorThicknessMm: float = 2.0" in parameter_source
    assert "targetDockingSharedDepthMm: float = 5.0" in parameter_source
    assert "targetDockingYawDeg: float = 35.0" in parameter_source
    assert "targetDockingCollisionClearanceMm: float = 0.5" in parameter_source


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


def test_default_task_joint_limits_match_six_joints() -> None:
    limits = default_task_joint_limits_from_urdf(URDF_PATH)
    assert limits.joint_1.unit == "deg"
    assert limits.joint_2.unit == "mm"
    assert limits.joint_1.minimum <= limits.joint_1.maximum
    assert limits.joint_6.minimum <= limits.joint_6.maximum


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
        j6_min=-90.0,
        j6_max=90.0,
    )
    clamped = apply_task_joint_limits_to_display_ranges(narrow, urdf_limits)
    assert clamped.joint_6.minimum >= urdf_limits.joint_6.minimum
    assert clamped.joint_6.maximum <= urdf_limits.joint_6.maximum


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
        j6_min=urdf_limits.joint_6.minimum,
        j6_max=urdf_limits.joint_6.maximum,
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
    for index in range(1, 7):
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


def test_canonical_drill_tcp_matches_reference_tip_at_zero_and_ignores_j6() -> None:
    """The planning frame is upstream of the uncontrolled air rotor."""

    zero = link_transforms_base_m(URDF_PATH, DESCRIPTION_ROOT, {})
    spinning = link_transforms_base_m(
        URDF_PATH,
        DESCRIPTION_ROOT,
        {"pneumatic_spindle-Copy_Revolute-6": 1.1},
    )
    assert np.allclose(
        zero["dentobot_drill_tcp"],
        zero["dentobot_drill_tip_provisional"],
        atol=1.0e-12,
    )
    assert np.allclose(
        zero["dentobot_drill_tcp"],
        spinning["dentobot_drill_tcp"],
        atol=1.0e-12,
    )
    assert not np.allclose(
        zero["dentobot_drill_tip_provisional"],
        spinning["dentobot_drill_tip_provisional"],
        atol=1.0e-6,
    )


def test_halton_workspace_sampling_is_deterministic_and_bounded() -> None:
    limits = default_task_joint_limits_from_urdf(URDF_PATH)
    first = deterministic_joint_workspace_samples_display(
        limits,
        12,
        current_display_joints=(0.0, 20.0, 10.0, 20.0, 5.0, 0.0),
    )
    second = deterministic_joint_workspace_samples_display(
        limits,
        12,
        current_display_joints=(0.0, 20.0, 10.0, 20.0, 5.0, 0.0),
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


def test_filtered_workspace_uses_fk_and_reports_all_requested_samples() -> None:
    limits = default_task_joint_limits_from_urdf(URDF_PATH)
    result = sample_filtered_tcp_workspace(
        limits=limits,
        sample_count=10,
        current_display_joints=(0.0, 20.0, 10.0, 20.0, 5.0, 0.0),
        urdf_path=URDF_PATH,
        package_root=DESCRIPTION_ROOT,
        base_world_matrix=np.eye(4, dtype=float),
        coarse_self_clearance_mm=0.0,
        environment_points_mm=np.zeros((0, 3), dtype=float),
        environment_clearance_mm=2.0,
    )
    assert result.requested_count == 10
    assert result.accepted_count == 10
    assert result.self_collision_rejections == 0
    assert result.environment_rejections == 0
    assert all(len(point) == 3 for point in result.accepted_tcp_base_mm)
    assert len(result.accepted_samples) == 10
    assert all(len(sample.joint_display) == 6 for sample in result.accepted_samples)
    assert all(len(sample.joint_positions_si) == 5 for sample in result.accepted_samples)


def test_workspace_sample_normalizes_transition_build_ordered_joint_values() -> None:
    legacy_names = (
        "link-1_Revolute-1",
        "link-2_Slider-2",
        "link-3_Revolute-3",
        "link-4_Slider-4",
        "link-5_Revolute-5",
        "pneumatic_spindle-Copy_Revolute-6",
    )
    values = (0.1, 0.02, -0.3, 0.04, 0.5, 0.0)
    canonical = WorkspaceAcceptedSample(
        tcp_base_mm=(1.0, 2.0, 3.0),
        joint_display=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        joint_positions_si=tuple(zip(legacy_names[:5], values[:5])),
    )
    transition = WorkspaceAcceptedSample(
        tcp_base_mm=(1.0, 2.0, 3.0),
        joint_display=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        joint_positions_si=values,
    )
    assert canonical.joint_positions_si_dict() == dict(zip(legacy_names[:5], values[:5]))
    assert transition.joint_positions_si_dict() == dict(zip(legacy_names, values))


def test_coarse_guard_excludes_known_baseline_false_positives_but_rejects_others() -> None:
    neutral_ok, neutral_reason, _neutral_tcp = evaluate_motion_configuration(
        joint_positions_si_from_display(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
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
        -69.23076923076923,
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
