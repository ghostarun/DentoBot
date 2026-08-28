"""Pure tests for draft Slicer robot placement geometry."""

from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HELPER_DIRECTORY = REPOSITORY_ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPER_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HELPER_DIRECTORY))

from DENTORobotPlacement import (
    hinge_rotation_matrix,
    joint_positions_si_from_display,
    local_nudge_matrix,
    orthonormal_plane_pose,
    robot_link_mesh_poses_mm,
    solve_hinge_rotation_for_gap,
    solve_anatomy_directed_hinge_rotation_for_gap,
    validate_patient_ras_condylar_landmarks,
    world_transform_to_parent_local,
)


URDF_PATH = REPOSITORY_ROOT / "dentobot_description" / "urdf" / "dentobot.urdf"
DESCRIPTION_ROOT = REPOSITORY_ROOT / "dentobot_description"


def test_selected_zero_and_reversed_joint_four_match_robot_description() -> None:
    zero_positions = joint_positions_si_from_display(0, 0, 0, 0, 0, 0)
    zero_poses = {
        pose.link_name: pose
        for pose in robot_link_mesh_poses_mm(
            URDF_PATH,
            DESCRIPTION_ROOT,
            zero_positions,
        )
    }
    assert len(zero_poses) == 7
    assert np.allclose(
        zero_poses["burr"].matrix_base_from_link_mm[:3, 3],
        (-49.564540494, 1.369804798, 197.675185601),
        atol=1e-6,
    )

    moved_positions = dict(zero_positions)
    moved_positions["link-4_Slider-4"] = 0.01
    moved_poses = {
        pose.link_name: pose
        for pose in robot_link_mesh_poses_mm(
            URDF_PATH,
            DESCRIPTION_ROOT,
            moved_positions,
        )
    }
    displacement = (
        moved_poses["link-5"].matrix_base_from_link_mm[:3, 3]
        - zero_poses["link-5"].matrix_base_from_link_mm[:3, 3]
    )
    assert displacement[0] < -9.99
    assert abs(displacement[1]) < 0.23
    assert abs(displacement[2]) < 1e-9


def test_plane_snap_removes_scale_and_local_nudges_follow_snapped_axes() -> None:
    plane = np.eye(4, dtype=float)
    plane[:3, 0] = (0.0, 2.0, 0.0)
    plane[:3, 1] = (-3.0, 0.0, 0.0)
    plane[:3, 2] = (0.0, 0.0, 4.0)
    plane[:3, 3] = (12.0, -8.0, 25.0)
    snapped = orthonormal_plane_pose(plane)
    assert np.allclose(snapped[:3, :3].T @ snapped[:3, :3], np.eye(3), atol=1e-12)
    assert np.linalg.det(snapped[:3, :3]) > 0.999999
    assert np.allclose(snapped[:3, 3], plane[:3, 3])

    nudged = local_nudge_matrix(snapped, translation_local_mm=(2.0, 0.0, 0.0))
    assert np.allclose(nudged[:3, 3], (12.0, -6.0, 25.0), atol=1e-12)
    rotated = local_nudge_matrix(snapped, rotation_local_deg=(0.0, 0.0, 90.0))
    assert np.allclose(rotated[:3, 3], snapped[:3, 3])
    assert np.allclose(rotated[:3, 2], snapped[:3, 2], atol=1e-12)


def test_draft_jaw_opening_is_pure_tmj_hinge_rotation_to_40_mm_gap() -> None:
    left_tmj = np.asarray((-50.0, 0.0, 0.0))
    right_tmj = np.asarray((50.0, 0.0, 0.0))
    upper_incisor = np.asarray((0.0, -90.0, -10.0))
    lower_closed = np.asarray((0.0, -90.0, -12.0))

    angle, matrix, opened_lower, gap = solve_hinge_rotation_for_gap(
        left_tmj,
        right_tmj,
        upper_incisor,
        lower_closed,
        40.0,
    )

    assert abs(angle) > 1.0
    assert abs(gap - 40.0) < 0.1
    assert np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-12)
    assert np.isclose(np.linalg.det(matrix[:3, :3]), 1.0, atol=1e-12)
    for hinge_point in (left_tmj, right_tmj):
        transformed = (matrix @ np.append(hinge_point, 1.0))[:3]
        assert np.allclose(transformed, hinge_point, atol=1e-9)
    assert np.allclose(
        opened_lower,
        (hinge_rotation_matrix(left_tmj, right_tmj, angle)
         @ np.append(lower_closed, 1.0))[:3],
    )


def test_draft_jaw_opening_rejects_degenerate_hinge() -> None:
    point = np.asarray((1.0, 2.0, 3.0))
    with np.testing.assert_raises_regex(ValueError, "distinct"):
        solve_hinge_rotation_for_gap(
            point,
            point,
            np.asarray((0.0, 0.0, 0.0)),
            np.asarray((0.0, 0.0, -2.0)),
        )


def test_case_jaw_opening_uses_only_gap_increasing_direction() -> None:
    left_tmj = np.asarray((-50.0, 0.0, 0.0))
    right_tmj = np.asarray((50.0, 0.0, 0.0))
    upper = np.asarray((0.0, -90.0, -10.0))
    lower = np.asarray((0.0, -90.0, -12.0))

    angle, matrix, opened, gap = solve_anatomy_directed_hinge_rotation_for_gap(
        left_tmj,
        right_tmj,
        upper,
        lower,
        40.0,
    )

    assert abs(gap - 40.0) <= 0.01
    assert angle != 0.0
    assert opened[2] < lower[2]
    assert np.linalg.norm(opened - upper) > np.linalg.norm(lower - upper)
    for hinge_point in (left_tmj, right_tmj):
        transformed = (matrix @ np.append(hinge_point, 1.0))[:3]
        assert np.allclose(transformed, hinge_point, atol=1e-9)


def test_case_jaw_opening_uses_inferior_branch_for_representative_ras_geometry() -> None:
    left_tmj = np.asarray((-132.735245, -96.085297, 73.430153))
    right_tmj = np.asarray((-47.763081, -95.850441, 76.087006))
    upper = np.asarray((-86.294014, -49.384068, 50.155613))
    lower = np.asarray((-87.795975, -45.079147, 51.003372))

    angle, _matrix, opened, gap = solve_anatomy_directed_hinge_rotation_for_gap(
        left_tmj,
        right_tmj,
        upper,
        lower,
        40.0,
    )

    assert angle < 0.0
    assert opened[2] < lower[2]
    assert abs(gap - 40.0) <= 0.01


def test_patient_ras_condylar_laterality_uses_positive_x_as_patient_right() -> None:
    review = validate_patient_ras_condylar_landmarks(
        np.asarray((-48.0, -32.0, 20.0)),
        np.asarray((51.0, -31.0, 21.0)),
    )
    assert review["leftRasXmm"] < review["rightRasXmm"]
    assert review["separationMm"] > 90.0
    with np.testing.assert_raises_regex(ValueError, "side-swapped"):
        validate_patient_ras_condylar_landmarks(
            np.asarray((48.0, -32.0, 20.0)),
            np.asarray((-51.0, -31.0, 21.0)),
        )


def test_case_jaw_opening_rejects_already_open_and_unreachable_targets() -> None:
    left_tmj = np.asarray((-50.0, 0.0, 0.0))
    right_tmj = np.asarray((50.0, 0.0, 0.0))
    upper = np.asarray((0.0, -90.0, -10.0))
    lower = np.asarray((0.0, -90.0, -50.0))
    with np.testing.assert_raises_regex(ValueError, "already reaches"):
        solve_anatomy_directed_hinge_rotation_for_gap(
            left_tmj,
            right_tmj,
            upper,
            lower,
            40.0,
        )
    with np.testing.assert_raises_regex(ValueError, "unreachable"):
        solve_anatomy_directed_hinge_rotation_for_gap(
            left_tmj,
            right_tmj,
            np.asarray((0.0, -1.0, -10.0)),
            np.asarray((0.0, -1.0, -12.0)),
            40.0,
            maximum_angle_deg=1.0,
        )


def test_draft_jaw_opening_hinge_survives_workspace_parent_translation() -> None:
    """World hinge rotation must be expressed in workspace-local parent space."""

    parent_to_world = np.eye(4, dtype=float)
    parent_to_world[:3, 3] = (0.0, -50.0, -1305.0)

    def to_world(native: np.ndarray) -> np.ndarray:
        return (parent_to_world @ np.append(native, 1.0))[:3]

    left_native = np.asarray((-45.0, -105.0, 1500.0))
    right_native = np.asarray((45.0, -105.0, 1500.0))
    upper_native = np.asarray((0.0, -178.0, 1472.0))
    lower_native = np.asarray((0.0, -175.0, 1468.0))
    left_world = to_world(left_native)
    right_world = to_world(right_native)
    upper_world = to_world(upper_native)
    lower_world = to_world(lower_native)

    angle, world_matrix, opened_lower, gap = solve_hinge_rotation_for_gap(
        left_world,
        right_world,
        upper_world,
        lower_world,
        40.0,
    )
    jaw_local = world_transform_to_parent_local(world_matrix, parent_to_world)

    closed_world = to_world(lower_native)
    opened_via_chain = (
        parent_to_world @ jaw_local @ np.append(lower_native, 1.0)
    )[:3]
    assert abs(gap - 40.0) < 0.1
    assert np.allclose(opened_via_chain, opened_lower, atol=1e-3)
    assert np.allclose(
        opened_via_chain,
        (world_matrix @ np.append(closed_world, 1.0))[:3],
        atol=1e-3,
    )
    for hinge_world in (left_world, right_world):
        hinge_local = np.linalg.inv(parent_to_world) @ np.append(hinge_world, 1.0)
        hinge_after = (parent_to_world @ jaw_local @ hinge_local)[:3]
        assert np.allclose(hinge_after, hinge_world, atol=1e-3)
