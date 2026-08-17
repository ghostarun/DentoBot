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
