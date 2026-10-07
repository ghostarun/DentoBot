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
