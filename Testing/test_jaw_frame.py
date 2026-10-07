"""Pure checks of the owning-jaw provenance frame (S6-MULTI-JAW-STALE-01)."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "DENTOWorkflow" / "Resources" / "Python"))

from dentobot_workflow import jaw_frame as jf  # noqa: E402


def _opening(theta_deg: float, shift=(0.0, -3.0, -8.0)) -> np.ndarray:
    """A rigid hinge-like jaw transform (rotation about x plus condylar translation)."""
    t = math.radians(theta_deg)
    m = np.eye(4)
    m[1:3, 1:3] = [[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]]
    m[:3, 3] = shift
    return m


DOCK_FRAME_LOCAL = {
    "originRas": [10.0, 20.0, 30.0],
    "xAxisRas": [1.0, 0.0, 0.0], "yAxisRas": [0.0, 1.0, 0.0], "zAxisRas": [0.0, 0.0, 1.0],
    "meanTrajectoryAxisRas": [0.0, 0.0, 1.0], "occlusalNormalRas": [0.0, 0.0, 1.0],
    "matrixColumnMajorRas": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 10, 20, 30, 1],
    "trajectoryGeometry": [{"entryRas": [10, 20, 40], "targetRas": [10, 20, 30], "axisRas": [0, 0, -1]}],
    "method": "TrajectoryPolarityTargetCrownOcclusalFrameV2", "yawDeg": 15.0,
}


def test_lower_jaw_provenance_is_identical_at_every_opening():
    local = DOCK_FRAME_LOCAL
    seen = []
    for theta in (8.0, 14.0, 21.5):
        jaw = _opening(theta)
        world = jf.to_world(local, jaw)                     # what Slicer shows at this opening
        seen.append(jf.round_provenance(jf.to_owning_jaw_frame(world, jaw)))
    assert seen[0] == seen[1] == seen[2]
    assert jf.provenance_matches(seen[0], jf.round_provenance(local))


def test_world_records_differ_between_openings_which_was_the_false_staleness():
    a = jf.to_world(DOCK_FRAME_LOCAL, _opening(8.0))
    b = jf.to_world(DOCK_FRAME_LOCAL, _opening(14.0))
    assert not jf.provenance_matches(a, b)


def test_upper_jaw_is_world_ras_unchanged():
    assert jf.to_owning_jaw_frame(DOCK_FRAME_LOCAL, None) is DOCK_FRAME_LOCAL
    assert jf.jaw_matrix_or_none("FixedUpper", _opening(10.0)) is None
    assert jf.jaw_matrix_or_none("", None) is None
    with pytest.raises(ValueError):
        jf.jaw_matrix_or_none("MovingLower", None)


def test_world_frame_matrix_and_axes_stay_consistent_after_conversion():
    jaw = _opening(17.0)
    world = jf.to_world(DOCK_FRAME_LOCAL, jaw)
    matrix = np.asarray(world["matrixColumnMajorRas"]).reshape(4, 4).T
    assert np.allclose(matrix[:3, 3], world["originRas"])
    assert np.allclose(matrix[:3, 2], world["zAxisRas"])
    assert world["yawDeg"] == 15.0 and world["method"] == DOCK_FRAME_LOCAL["method"]


def test_unknown_coordinate_fields_fail_closed():
    with pytest.raises(ValueError, match="unknown coordinate field"):
        jf.to_owning_jaw_frame({"cuspTipRas": [0, 0, 0]}, _opening(5.0))


def test_non_rigid_jaw_transform_is_rejected():
    scaled = np.diag([1.1, 1.0, 1.0, 1.0])
    with pytest.raises(ValueError, match="not rigid"):
        jf.to_owning_jaw_frame({"originRas": [0, 0, 0]}, scaled)


def test_lower_opening_matches_independent_point_arithmetic_and_upper_stays_fixed():
    theta = math.radians(30.0)
    shift = (1.0, -3.0, 5.0)
    lower = {"originRas": [2.0, 4.0, 6.0]}
    upper = {"originRas": [2.0, 4.0, 6.0]}

    opened_lower = jf.to_world(lower, _opening(30.0, shift))
    unchanged_upper = jf.to_world(upper, None)

    x, y, z = lower["originRas"]
    sine, cosine = math.sin(theta), math.cos(theta)
    expected_lower = [
        x + shift[0],
        cosine * y - sine * z + shift[1],
        sine * y + cosine * z + shift[2],
    ]
    assert opened_lower["originRas"] == pytest.approx(expected_lower)
    assert unchanged_upper is upper
    assert unchanged_upper["originRas"] == [2.0, 4.0, 6.0]


def test_base_yaw_and_translation_map_world_point_by_inverse_base_delta():
    # world_from_base = translation(10, 20, 30) * yaw(90 degrees)
    base_world = np.asarray(
        [[0.0, -1.0, 0.0, 10.0],
         [1.0,  0.0, 0.0, 20.0],
         [0.0,  0.0, 1.0, 30.0],
         [0.0,  0.0, 0.0,  1.0]],
    )

    base_point = jf.transform_point(jf.rigid_inverse(base_world), [11.0, 22.0, 33.0])

    assert base_point == pytest.approx([2.0, -1.0, 3.0])


def test_opening_then_inverse_base_composition_has_known_answer_and_order():
    opening = _opening(90.0, shift=(2.0, -4.0, 6.0))
    base_world = np.asarray(
        [[0.0, -1.0, 0.0, 10.0],
         [1.0,  0.0, 0.0, 20.0],
         [0.0,  0.0, 1.0, 30.0],
         [0.0,  0.0, 0.0,  1.0]],
    )
    local = {"originRas": [7.0, 8.0, 9.0]}
    opened_world = jf.to_world(local, opening)["originRas"]
    base_point = jf.transform_point(jf.rigid_inverse(base_world), opened_world)

    # About x: (7, 8, 9) -> (9, -13, 14); inverse yaw/translation -> (-33, 1, -16).
    assert opened_world == pytest.approx([9.0, -13.0, 14.0])
    assert base_point == pytest.approx([-33.0, 1.0, -16.0])

    reversed_order = jf.to_world(
        {"originRas": jf.transform_point(jf.rigid_inverse(base_world), local["originRas"])},
        opening,
    )["originRas"]
    assert base_point != pytest.approx(reversed_order)


def test_owning_jaw_provenance_round_trips_across_translated_openings():
    local = {
        "originRas": [10.0, 20.0, 30.0],
        "entryRas": [12.0, 19.0, 45.0],
        "axisRas": [0.0, 0.0, 1.0],
        "method": "known-answer",
    }
    openings = (
        _opening(8.0, shift=(4.0, -7.0, 9.0)),
        _opening(31.0, shift=(-2.0, 5.0, 3.0)),
    )
    worlds = [jf.to_world(local, opening) for opening in openings]
    canonical = [jf.to_owning_jaw_frame(world, opening) for world, opening in zip(worlds, openings)]

    assert not jf.provenance_matches(worlds[0], worlds[1])
    assert jf.provenance_matches(canonical[0], local)
    assert jf.provenance_matches(canonical[1], local)
    assert jf.provenance_matches(canonical[0], canonical[1])


def test_rigid_inverse_rejects_a_nonrigid_base_transform():
    scaled_base = np.diag([1.2, 1.0, 1.0, 1.0])
    with pytest.raises(ValueError, match="not rigid"):
        jf.rigid_inverse(scaled_base)


def test_branch_foundation_fingerprint_ignores_the_opening_only():
    pose = {"source_volume_fingerprint": "v", "source_segmentation_fingerprint": "s", "jaw_source_fingerprint": "j",
            "jaw_landmarks_fingerprint": "l", "landmark_positions_ras_mm": (1.0, 2.0), "landmark_review_fingerprint": "r",
            "hinge_model_schema": "h", "jaw_transform_matrix": [1.0] * 16, "mouth_gap_mm": 40.0, "opening_revision": 3}
    prep = {"mode": "CaseFoundationCurrent", "movingLowerSegmentIds": ["a"], "targetGapMm": 40.0,
            "achievedGapMm": 39.98, "hingeAngleDeg": 20.1, "openingRevision": 3, "worldRasMatrix": [1] * 16}
    base = jf.branch_foundation_fingerprint(pose, prep)
    opened = jf.branch_foundation_fingerprint(
        {**pose, "jaw_transform_matrix": [2.0] * 16, "mouth_gap_mm": 46.0, "opening_revision": 9},
        {**prep, "targetGapMm": 46.0, "achievedGapMm": 45.9, "hingeAngleDeg": 25.0, "openingRevision": 9,
         "worldRasMatrix": [2] * 16})
    assert opened == base
    assert jf.branch_foundation_fingerprint({**pose, "source_segmentation_fingerprint": "s2"}, prep) != base
    assert jf.branch_foundation_fingerprint(pose, {**prep, "movingLowerSegmentIds": ["a", "b"]}) != base


def test_legacy_world_records_migrate_only_when_stamped_at_the_current_pose():
    jaw = _opening(12.0)
    world = jf.to_world(DOCK_FRAME_LOCAL, jaw)
    migrated = jf.migrate_world_provenance(world, jaw, stamped_pose="p1", current_pose="p1")
    assert jf.provenance_matches(migrated, DOCK_FRAME_LOCAL)
    assert jf.migrate_world_provenance(world, jaw, stamped_pose="p0", current_pose="p1") is None
    assert jf.migrate_world_provenance(world, jaw, stamped_pose="", current_pose="") is None
