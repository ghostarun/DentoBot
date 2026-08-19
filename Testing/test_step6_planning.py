"""Pure tests for Step 6 planning helpers."""

from pathlib import Path
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
    apply_task_joint_limits_to_display_ranges,
    apply_task_limit_range_to_value,
    build_task_joint_limits_from_parameter_values,
    case_view_present_roles,
    combine_ras_bounds,
    default_task_joint_limits_from_urdf,
    plan_trajectory_motion,
    sample_trajectory_world_mm,
    step6_motion_plan_robot_ready,
    validate_planning_context,
)


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


def test_plan_trajectory_motion_reports_self_collision_with_strict_clearance() -> None:
    """Neutral pose can overlap coarse AABBs; strict clearance must reject it."""
    pytest.importorskip("scipy.optimize")
    limits = default_task_joint_limits_from_urdf(URDF_PATH)
    base_world = np.eye(4, dtype=float)
    burr_at_neutral = (-49.564540494, 1.369804798, 197.675185601)
    result = plan_trajectory_motion(
        entry_ras_mm=burr_at_neutral,
        target_ras_mm=burr_at_neutral,
        start_display_joints=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        limits=limits,
        urdf_path=URDF_PATH,
        package_root=DESCRIPTION_ROOT,
        base_world_matrix=base_world,
        sample_count=2,
        coarse_self_clearance_mm=5.0,
        environment_points_mm=None,
        environment_clearance_mm=2.0,
    )
    assert not result.success
    assert "self-collision" in result.message.lower() or "aabb" in result.message.lower()
    assert result.self_collision_indices == (0,)
