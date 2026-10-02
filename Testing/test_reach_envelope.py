import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "DENTOWorkflow/Resources/Python"))

from dentobot_workflow import reach_envelope  # noqa: E402


def test_alpha_shape_keeps_separate_reach_regions_apart():
    rng = np.random.default_rng(0)
    left = rng.uniform(-10, 10, (40, 3))
    right = left + [60.0, 0.0, 0.0]
    surface, volume, method = reach_envelope.envelope(np.vstack([left, right]))
    assert method.startswith("alpha_shape")
    assert surface.GetNumberOfCells() > 0
    inside = reach_envelope.points_inside(volume, [(0, 0, 0), (30, 0, 0), (60, 0, 0), (200, 0, 0)])
    assert inside == [True, False, True, False]  # the gap between regions is not bridged


def test_too_few_samples_give_no_envelope_and_nothing_inside():
    surface, volume, method = reach_envelope.envelope([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    assert method == "too_few_samples" and surface.GetNumberOfCells() == 0
    assert reach_envelope.points_inside(volume, [(0, 0, 0)]) == [False]


def test_nearest_sample_distance():
    assert reach_envelope.nearest_sample_mm([(0, 0, 0), (10, 0, 0)], (13, 4, 0)) == 5.0
    assert reach_envelope.nearest_sample_mm([], (0, 0, 0)) == float("inf")
