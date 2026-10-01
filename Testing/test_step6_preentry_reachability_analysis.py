import math
from pathlib import Path

import numpy as np

import Testing.step6_preentry_reachability_analysis as analysis

ROOT = Path(__file__).resolve().parents[1]
URDF = ROOT / "dentobot_description/urdf/dentobot.urdf"

TWO_JOINT_URDF = """<robot name="toy">
  <link name="base_link"/><link name="a"/><link name="dentobot_drill_tcp"/>
  <joint name="j_rot" type="revolute">
    <parent link="base_link"/><child link="a"/>
    <origin xyz="0 0 0" rpy="0 0 0"/><axis xyz="0 0 1"/>
    <limit lower="-3.14" upper="3.14" effort="1" velocity="1"/>
  </joint>
  <joint name="j_slide" type="prismatic">
    <parent link="a"/><child link="dentobot_drill_tcp"/>
    <origin xyz="0 0 0" rpy="0 1.5707963267948966 0"/><axis xyz="0 0 1"/>
    <limit lower="0.0" upper="0.05" effort="1" velocity="1"/>
  </joint>
</robot>
"""


def _toy(tmp_path):
    path = tmp_path / "toy.urdf"
    path.write_text(TWO_JOINT_URDF)
    return analysis.Chain.from_urdf(path)


def test_toy_chain_forward_and_solve_converges_inside_limits(tmp_path):
    chain = _toy(tmp_path)
    assert chain.names == ["j_rot", "j_slide"]
    tip, _ = chain.forward(np.array([0.0, 0.03]))
    assert np.allclose(tip[:3, 3], [0.03, 0.0, 0.0], atol=1e-12)
    target = np.array([0.0, 0.02, 0.0])
    result = analysis.solve(chain, [0.0, 0.01], target, np.array([0.0, 1.0, 0.0]), iterations=400)
    assert result["termination"] == "converged"
    assert abs(result["q"][1] - 0.02) < 3e-4


def test_slider_limit_pins_unreachable_target_and_relaxing_it_converges(tmp_path):
    chain = _toy(tmp_path)
    # Reaching x=-0.01 along +x axis requires slide=-0.01 (below its 0.0 limit).
    target = np.array([-0.01, 0.0, 0.0])
    axis = np.array([1.0, 0.0, 0.0])
    pinned = analysis.solve(chain, [0.0, 0.02], target, axis, iterations=400)
    assert pinned["termination"] != "converged"
    assert pinned["q"][1] == 0.0
    relaxed = analysis.solve(chain, [0.0, 0.02], target, axis, iterations=400,
                             relax=frozenset({"j_slide"}))
    assert relaxed["termination"] == "converged"
    assert abs(relaxed["q"][1] + 0.01) < 3e-4


def test_dentobot_chain_matches_urdf_active_joints_and_limits():
    chain = analysis.Chain.from_urdf(URDF)
    assert chain.names == [
        "link-1_Revolute-1", "link-2_Slider-2", "link-3_Revolute-3",
        "link-4_Slider-4", "link-5_Revolute-5",
    ]
    lower, upper = chain.bounds()
    assert lower[1] == 0.0 and math.isclose(upper[1], 0.08)
    assert math.isinf(lower[4]) and math.isinf(upper[4])


def test_dentobot_model_reproduces_recorded_native_residual_fixture():
    # Recorded r2 Home-seed PreEntry best state and residuals (base frame, metres).
    chain = analysis.Chain.from_urdf(URDF)
    pre_entry = np.array([-0.08356562987701481, 0.003596947188244599, 0.11020503086406573])
    axis = np.array([-0.28664960187713834, -0.010308780449910453, -0.9579800283874991])
    axis = axis / np.linalg.norm(axis)
    best = [-0.0189543532859353, 0.000439999999999989, 3.1511264337595364,
            0.0319612294219932, 0.2594205715119731]
    position, axis_error = analysis.residuals(chain, best, pre_entry, axis)
    assert abs(position * 1000.0 - 0.6900876700087326) < 0.01
    assert abs(math.degrees(axis_error) - 0.675109956028758) < 0.01
    seed = [0.008726646259971648, 0.030440000000000002, 3.141592653589793, 0.032, 0.0]
    native = analysis.solve(chain, seed, pre_entry, axis)
    assert native["termination"] == "iteration_limit" and native["iterations"] == 120
    assert abs(native["position_residual_mm"] - 0.6900876700087326) < 0.01
