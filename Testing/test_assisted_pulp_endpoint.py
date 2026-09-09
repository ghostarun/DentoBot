"""Exact binary-mask endpoint regression; no Slicer or robot runtime."""
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "DENTOWorkflow/Resources/Python"))
from DENTOTrajectoryGeometry import first_mask_intersection


def test_first_pulp_boundary_single_dual_and_misses():
    mask = np.zeros((9, 3, 3), dtype=np.uint8)
    mask[2, :, :] = 1
    mask[6, :, :] = 1
    for entries in ([(0, 0, 0)], [(0, 0, 0), (2, 2, 0)]):
        for entry in entries:
            target = (*entry[:2], 8)
            assert first_mask_intersection(mask, entry, target) == pytest.approx(1.5 / 8)
    assert first_mask_intersection(mask, (1, 1, 8), (1, 1, 0)) == pytest.approx(1.5 / 8)
    assert first_mask_intersection(mask, (0, 0, 0), (2, 2, 8)) == pytest.approx(1.5 / 8)
    assert first_mask_intersection(mask, (10, 20, 30), (10, 20, 38), (10, 20, 30)) == pytest.approx(1.5 / 8)
    for entry, target in [((5, 0, 0), (5, 0, 8)), ((0, 0, 0), (0, 0, 1))]:
        with pytest.raises(ValueError, match="does not intersect"):
            first_mask_intersection(mask, entry, target)
    with pytest.raises(ValueError, match="inside or touching"):
        first_mask_intersection(mask, (1, 1, 2), (1, 1, 8))
    with pytest.raises(ValueError, match="empty"):
        first_mask_intersection(np.zeros_like(mask), (0, 0, 0), (0, 0, 8))
    with pytest.raises(ValueError, match="non-finite"):
        first_mask_intersection(mask, (float("nan"), 0, 0), (0, 0, 8))
