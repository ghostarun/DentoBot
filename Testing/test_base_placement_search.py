import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "DENTOWorkflow/Resources/Python"))

from dentobot_workflow import base_placement_search as search  # noqa: E402

URDF = ROOT / "dentobot_description/urdf/dentobot.urdf"

# Rotating column + 50 mm slider; tool z axis points along the slider (+x).
TOY_URDF = """<robot name="toy">
  <link name="base_link"/><link name="a"/><link name="dentobot_drill_tcp"/>
  <joint name="j_rot" type="revolute">
    <parent link="base_link"/><child link="a"/>
    <origin xyz="0 0 0" rpy="0 0 0"/><axis xyz="0 0 1"/>
    <limit lower="-3.14" upper="3.14" effort="1" velocity="1"/>
  </joint>
  <joint name="j_Slider" type="prismatic">
    <parent link="a"/><child link="dentobot_drill_tcp"/>
    <origin xyz="0 0 0" rpy="0 1.5707963267948966 0"/><axis xyz="0 0 1"/>
    <limit lower="0.0" upper="0.05" effort="1" velocity="1"/>
  </joint>
</robot>
"""


def _toy_chain(tmp_path):
    path = tmp_path / "toy.urdf"
    path.write_text(TOY_URDF)
    return search.Chain.from_urdf(path)


def _toy_task():
    # Stroke along world +x from 58 mm (PreEntry) to 70 mm (Target): the 50 mm
    # slider cannot reach it from a Base at the origin.
    return search.PlacementTask(
        np.array([58.0, 0.0, 0.0]), np.array([60.0, 0.0, 0.0]),
        np.array([70.0, 0.0, 0.0]), [0.0, 0.01],
    )


def test_locked_dimensions_contribute_single_zero_and_unlocked_ranges_expand():
    assert search._values((0.0, 0.0, 0.0)) == [0.0]
    assert search._values((-10.0, 10.0, 5.0)) == [-10.0, -5.0, 0.0, 5.0, 10.0]
    config = search.ForeheadPlacementSearchConfig()
    assert search._values(config.depth_range_mm) == [0.0]
    for spec in (config.rotation_x_range_deg, config.rotation_y_range_deg,
                 config.rotation_z_range_deg):
        assert search._values(spec) == [0.0]


def test_grid_is_iterated_outward_from_the_plane_centre():
    points = search._grid(10.0, 5.0)
    assert points[0] == (0.0, 0.0)
    distances = [math.hypot(u, v) for u, v in points]
    assert distances == sorted(distances)
    assert len(points) == 25


def test_candidate_matrix_slides_in_plane_and_keeps_orientation_when_locked():
    frame = np.eye(4)
    frame[:3, 0] = [0.0, 1.0, 0.0]
    frame[:3, 1] = [0.0, 0.0, 1.0]
    frame[:3, 2] = [1.0, 0.0, 0.0]
    reference = np.eye(4)
    reference[:3, 3] = [5.0, 6.0, 7.0]
    moved = search.candidate_base_matrix(frame, reference, 2.0, -3.0)
    assert np.allclose(moved[:3, 3], [5.0, 8.0, 4.0])
    assert np.allclose(moved[:3, :3], reference[:3, :3])
    depth = search.candidate_base_matrix(frame, reference, 0.0, 0.0, n_mm=4.0)
    assert np.allclose(depth[:3, 3], [9.0, 6.0, 7.0])
    rotated = search.candidate_base_matrix(frame, reference, 0.0, 0.0, rz_deg=90.0)
    assert np.allclose(rotated[:3, 3], reference[:3, 3])  # pivot at Base origin
    assert not np.allclose(rotated[:3, :3], reference[:3, :3])


def test_toy_search_finds_nearest_in_plane_slide_that_reaches_whole_stroke(tmp_path):
    chain = _toy_chain(tmp_path)
    task = _toy_task()
    report = search.search_forehead_base_placement(chain, np.eye(4), np.eye(4), task)
    assert report["centre"]["reachable"] is False
    assert report["verdict"] == "feasible_base_found"
    best = report["best"]
    assert best["v_mm"] == 0.0
    assert 20.0 < best["u_mm"] <= 22.0  # slider <= 49 mm needs u >= 21
    assert best["minimum_slider_margin_mm"] >= 1.0
    assert report["locked_dimensions"] == {"depth": True, "orientation": True}


def test_toy_search_reports_no_base_when_stroke_exceeds_envelope(tmp_path):
    chain = _toy_chain(tmp_path)
    task = search.PlacementTask(
        np.array([118.0, 0.0, 0.0]), np.array([120.0, 0.0, 0.0]),
        np.array([130.0, 0.0, 0.0]), [0.0, 0.01],
    )
    report = search.search_forehead_base_placement(chain, np.eye(4), np.eye(4), task)
    assert report["best"] is None
    assert report["verdict"] == "no_reachable_base_in_locked_search_space"


# Regression fixture from the r29 FDI11 case (r2 evidence, world RAS mm).
R29_BASE = np.array([
    -0.0330574649102486, 0.9989464180111487, 0.03183171306108124, -97.87032867483634,
    0.9816188440529587, 0.026461242330670445, 0.18900859148316584, 27.661632974147835,
    0.18796714876233106, 0.03749475425993436, -0.9814593697087757, 176.59698359363338,
    0.0, 0.0, 0.0, 1.0]).reshape(4, 4)
R29_FOREHEAD = np.eye(4)
R29_FOREHEAD[:3, 0] = [0.998694774, 0.033563264, 0.038500063]
R29_FOREHEAD[:3, 1] = [0.028589422, 0.257291016, -0.965910958]
R29_FOREHEAD[:3, 2] = [-0.042324845, 0.965750920, 0.255995639]
R29_FOREHEAD[:3, 3] = [-96.964472700, -42.984298739, 178.437807322]
R29_TASK = search.PlacementTask(
    np.array([-88.00668836764936, -33.443086679110195, 52.862496931449705]),
    np.array([-88.06932067871094, -34.368526458740234, 54.6343994140625]),
    np.array([-88.37436150468885, -38.87573543740375, 63.26417193382737]),
    [0.008726646259971648, 0.030440000000000002, 3.141592653589793, 0.032, 0.0],
)


def test_r29_current_base_fails_at_preentry_and_v_minus_14_reaches_full_stroke():
    chain = search.Chain.from_urdf(URDF)
    config = search.ForeheadPlacementSearchConfig()
    current = search.evaluate_base(chain, R29_BASE, R29_TASK, config)
    assert current["reachable"] is False and current["first_failed_station"] == "pre_entry"
    moved = search.candidate_base_matrix(R29_FOREHEAD, R29_BASE, 0.0, -14.0)
    result = search.evaluate_base(chain, moved, R29_TASK, config)
    assert result["feasible"] is True
    assert result["minimum_slider_margin_mm"] >= 1.0


def test_depth_fallback_runs_only_when_in_plane_search_finds_nothing(tmp_path):
    chain = _toy_chain(tmp_path)
    # Depth axis (z_hat) is the slider direction, so only a depth shift helps.
    frame = np.eye(4)
    frame[:3, 0] = [0.0, 1.0, 0.0]
    frame[:3, 1] = [0.0, 0.0, 1.0]
    frame[:3, 2] = [1.0, 0.0, 0.0]
    task = search.PlacementTask(
        np.array([54.0, 0.0, 0.0]), np.array([56.0, 0.0, 0.0]),
        np.array([56.5, 0.0, 0.0]), [0.0, 0.01],
    )
    report = search.search_with_depth_fallback(chain, frame, np.eye(4), task)
    assert report["depth_fallback"]["ran"] is True
    assert report["depth_fallback"]["in_plane_verdict"] == "no_reachable_base_in_locked_search_space"
    assert report["best"] is not None and report["best"]["depth_mm"] > 0
    in_plane = search.search_with_depth_fallback(chain, np.eye(4), np.eye(4), _toy_task())
    assert in_plane["depth_fallback"] == {"ran": False}


def test_path_clear_selector_prefers_nearest_clear_and_flags_blocked(tmp_path):
    ranked = [
        {"u_mm": 0.0, "v_mm": -14.0, "displacement_mm": 14.0, "minimum_slider_margin_mm": 1.8},
        {"u_mm": 4.0, "v_mm": -14.0, "displacement_mm": 14.6, "minimum_slider_margin_mm": 1.7},
        {"u_mm": -4.0, "v_mm": -14.0, "displacement_mm": 14.6, "minimum_slider_margin_mm": 1.9},
    ]
    report = {"ranked_all": ranked, "best": ranked[0]}
    clear_at = {(-4.0, -14.0)}
    out = search.select_path_clear_candidate(
        report, lambda r: {"clear": (r["u_mm"], r["v_mm"]) in clear_at})
    assert out["best"]["u_mm"] == -4.0  # larger margin wins the displacement tie
    assert out["path_preflight"]["selected"] == "path_clear"
    assert [t["clear"] for t in out["path_preflight"]["tried"]] == [False, True]
    blocked = search.select_path_clear_candidate(
        {"ranked_all": ranked, "best": ranked[0]}, lambda r: {"clear": False})
    assert blocked["best"] is ranked[0]
    assert blocked["path_preflight"]["selected"] == "kinematic_best_path_blocked"


def test_tool_mesh_sweep_detects_contact_along_straight_path():
    import vtk
    from DENTORobotPlacement import robot_link_mesh_poses_mm
    from dentobot_workflow.path_clearance import ToolMeshSweep, _vtk_matrix, load_stl

    urdf = ROOT / "dentobot_description/urdf/dentobot.urdf"
    package = ROOT / "dentobot_description"
    home = {"link-1_Revolute-1": 0.0087, "link-2_Slider-2": 0.03044,
            "link-3_Revolute-3": 3.1416, "link-4_Slider-4": 0.032, "link-5_Revolute-5": 0.0}
    retracted = dict(home, **{"link-2_Slider-2": 0.0})
    pose = {p.link_name: p for p in robot_link_mesh_poses_mm(urdf, package, retracted)}["burr"]
    transform = vtk.vtkTransform()
    transform.SetMatrix(_vtk_matrix(pose.matrix_base_from_mesh_mm))
    posed = vtk.vtkTransformPolyDataFilter()
    posed.SetInputData(load_stl(pose.mesh_path))
    posed.SetTransform(transform)
    posed.Update()
    bounds = posed.GetOutput().GetBounds()
    ball = vtk.vtkSphereSource()
    ball.SetCenter((bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2, (bounds[4] + bounds[5]) / 2)
    ball.SetRadius(1.5)
    ball.Update()
    sweep = ToolMeshSweep(urdf, package, [("obstacle", ball.GetOutput())])
    names = list(home)
    assert sweep.contacts(np.eye(4), home) == []
    result = sweep.straight_path(np.eye(4), names, list(home.values()), list(retracted.values()))
    assert result["clear"] is False
    assert result["contacts"] == ["burr<->obstacle"]
    assert 0.0 < result["first_contact_fraction"] <= 1.0


def test_zero_area_triangles_are_dropped_before_collision_trees():
    """Error log 2026-10-03: segment surfaces carry zero-area triangles; OBB
    nodes made only of them gave NaN axes and vtkMath::Jacobi warnings."""
    import vtk

    from dentobot_workflow.path_clearance import drop_zero_area_triangles

    points = vtk.vtkPoints()
    for xyz in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (2, 0, 0), (3, 0, 0), (4, 0, 0)):
        points.InsertNextPoint(*xyz)
    cells = vtk.vtkCellArray()
    for tri in ((0, 1, 2), (3, 4, 5), (1, 3, 4)):  # one real, two collinear
        cells.InsertNextCell(3, tri)
    mesh = vtk.vtkPolyData()
    mesh.SetPoints(points)
    mesh.SetPolys(cells)
    cleaned = drop_zero_area_triangles(mesh)
    assert cleaned.GetNumberOfCells() == 1
    assert cleaned.GetCellData().GetArray("Quality") is None
    bounds = cleaned.GetBounds()
    assert (bounds[0], bounds[1], bounds[2], bounds[3]) == (0.0, 1.0, 0.0, 1.0)
    clean = drop_zero_area_triangles(cleaned)
    assert clean is cleaned  # no copy when nothing is degenerate
