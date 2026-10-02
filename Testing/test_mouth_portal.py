import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "DENTOWorkflow/Resources/Python"))

from dentobot_workflow import mouth_portal as portal_module  # noqa: E402

# Portal in the plane y = 0 (anterior is +y): upper canines z = +10, lower z = -10.
VERTICES = [(-15.0, 0.0, 10.0), (15.0, 0.0, 10.0), (15.0, 0.5, -10.0), (-15.0, -0.5, -10.0)]
OUTSIDE = (0.0, 80.0, 0.0)


def _portal():
    return portal_module.build_portal(VERTICES, OUTSIDE)


def test_portal_plane_normal_points_outward_and_reports_planarity():
    portal = _portal()
    assert portal.normal_outward @ np.array([0.0, 1.0, 0.0]) > 0.99
    assert portal.signed_distance(OUTSIDE) > 0
    assert 0.0 < portal.planarity_max_mm < 0.5


def test_path_through_portal_passes_and_reports_crossing():
    result = portal_module.check_tcp_path(_portal(), [(0, 60, 0), (0, 20, 0), (0, -5, 0)])
    assert result["status"] == "passed"
    assert result["entry_crossing"]["inside_portal"] is True
    assert result["entry_crossing"]["edge_margin_mm"] > 9.0


def test_path_crossing_outside_quadrilateral_fails():
    result = portal_module.check_tcp_path(_portal(), [(40, 60, 0), (40, -5, 0)])
    assert result["status"] == "failed" and result["reason"] == "crossing_outside_portal"


def test_path_must_start_outside_and_end_inside():
    portal = _portal()
    assert portal_module.check_tcp_path(portal, [(40, -5, 0), (0, -10, 0)])["reason"] == "start_inside_outside_portal"
    assert portal_module.check_tcp_path(portal, [(0, 60, 0), (0, 10, 0)])["reason"] == "preentry_not_inside"


def test_vertex_teeth_use_canines_then_first_premolar_then_lateral_incisor():
    chosen = portal_module.choose_vertex_teeth(["13", "24", "22", "33", "42"])
    assert chosen["13"] == {"fdi": "13", "substituted": False}
    assert chosen["23"] == {"fdi": "24", "substituted": True}
    assert chosen["33"] == {"fdi": "33", "substituted": False}
    assert chosen["43"] == {"fdi": "42", "substituted": True}
    with pytest.raises(ValueError):
        portal_module.choose_vertex_teeth(["13", "23", "33"])


def test_cusp_tip_is_extreme_point_along_occlusal_direction():
    points = np.array([[0, 0, 0], [0, 0, -3.0], [1, 0, -1.0]])
    assert portal_module.cusp_tip(points, (0, 0, -1)).tolist() == [0.0, 0.0, -3.0]


def test_lip_line_shift_moves_portal_in_front_of_most_labial_point():
    portal = _portal()
    incisors = np.array([[0.0, 8.0, 5.0], [3.0, 6.0, -4.0]])
    shifted = portal_module.shift_portal_to_lip_line(portal, incisors, margin_mm=2.0)
    assert abs(shifted.signed_distance((0.0, 8.0, 5.0)) + 2.0) < 0.6
    assert shifted.vertex_teeth["lip_line_offset_mm"] > 9.0
    path = [(0, 60, 0), (0, 20, 0), (0, 7.0, 0)]  # PreEntry just behind the lip line
    assert portal_module.check_tcp_path(shifted, path)["status"] == "passed"


def test_enlarge_moves_every_edge_outward_by_margin():
    portal = _portal()
    grown = portal_module.enlarge_portal(portal, 5.0)
    poly = grown.polygon_2d()
    centre = portal.to_plane_2d(portal.origin_mm)
    for point in portal.polygon_2d():
        assert portal_module._point_in_polygon(point, poly)
    original = portal.polygon_2d()
    assert abs(portal_module._edge_margin(original[0] + (original[0] - centre) * 0.0, poly) - 5.0 * 2 ** 0.5) < 3.0
    assert grown.vertex_teeth["enlarge_mm"] == 5.0


def test_home_already_inside_portal_passes_only_within_opening():
    portal = _portal()
    assert portal_module.check_tcp_path(portal, [(0, -2, 0), (0, -6, 0)])["mode"] == "home_inside_portal"
    assert portal_module.check_tcp_path(portal, [(40, -2, 0), (0, -6, 0)])["reason"] == "start_inside_outside_portal"


def test_leaving_and_reentering_through_the_opening_passes_but_outside_fails():
    # r4 2026-10-02: Home 12 mm behind the lip line, P1 stepped out and back in.
    portal = _portal()
    through = portal_module.check_tcp_path(portal, [(0, -2, 0), (0, 5, 0), (0, -6, 0)])
    assert through["status"] == "passed" and len(through["crossings"]) == 2
    assert through["entry_crossing"]["direction"] == "inward"
    around = portal_module.check_tcp_path(portal, [(0, -2, 0), (40, 5, 0), (0, -6, 0)])
    assert around["reason"] == "crossing_outside_portal"


def _closed_and_volume(part):
    import collections
    edges = collections.Counter()
    for a, b, c in part.triangles:
        for edge in ((a, b), (b, c), (c, a)):
            edges[edge] += 1
    open_edges = [e for e, n in edges.items() if n != 1 or edges.get((e[1], e[0]), 0) != 1]
    points = part.points_mm
    volume = sum(points[a] @ np.cross(points[b], points[c]) for a, b, c in part.triangles) / 6.0
    return len(open_edges), volume


def test_gum_line_edge_mode_raises_the_opening_and_biting_edge_keeps_cusp_tips():
    portal = _portal()
    gum = portal_module.apply_edge_mode(portal, "gum_line", [(0, 0, 22)], [(0, 0, -24)])
    heights = gum.polygon_2d()
    assert gum.vertex_teeth["opening_height_cusp_tips_mm"] == pytest.approx(20.0, abs=0.1)
    assert gum.vertex_teeth["opening_height_gum_line_mm"] == pytest.approx(46.0, abs=0.1)
    assert np.ptp(heights[:, 1]) == pytest.approx(46.0, abs=0.1)
    # A gum point inside the cusp-tip opening never shrinks it.
    same = portal_module.apply_edge_mode(portal, "gum_line", [(0, 0, 5)], [(0, 0, -5)])
    assert np.allclose(same.vertices_mm, portal.vertices_mm)
    biting = portal_module.apply_edge_mode(portal, "biting_edge")
    assert np.allclose(biting.vertices_mm, portal.vertices_mm) and biting.vertex_teeth["edge_mode"] == "biting_edge"
    with pytest.raises(ValueError):
        portal_module.apply_edge_mode(portal, "lips")


def test_gum_point_uses_bone_crest_else_crown_height():
    tooth = np.array([[0, 0, 10.0], [0, 0, 4.0], [0, 0, -6.0]])  # occlusal is -z (upper tooth)
    bone = np.array([-3.0, 0.5, 5.0])  # root inside bone, crest contact at z=4, crown clear
    point, source = portal_module.gum_points_from_crest(tooth, bone, (0, 0, -1), tooth[2])
    assert source == "bone_crest" and point.tolist() == [0.0, 0.0, 2.0]
    point, source = portal_module.gum_points_from_crest(tooth, np.full(3, np.inf), (0, 0, -1), tooth[2])
    assert source == "crown_height_estimate" and point[2] == pytest.approx(3.0)


def test_barrier_is_closed_frames_the_opening_and_walls_the_cheeks():
    opening = portal_module.enlarge_portal(
        portal_module.apply_edge_mode(_portal(), "gum_line", [(0, 0, 22)], [(0, 0, -24)]), 5.0)
    teeth = np.array([[x, y, z] for x in (-25, 25) for y in (-40, 5) for z in (-8, 8)], float)
    extent = np.vstack([teeth, [[0, -30, 40], [0, -30, -45]]])
    barrier = portal_module.build_mouth_barrier(opening, extent, teeth)
    assert barrier.summary["parts"] == ["lip_slab", "cheek_low_u", "cheek_high_u"]
    for part in barrier.parts:
        open_edges, volume = _closed_and_volume(part)
        assert open_edges == 0 and volume > 0
    assert barrier.summary["opening_height_mm"] == pytest.approx(56.0, abs=0.5)
    contains = portal_module.barrier_contains_point
    assert contains(barrier, (0, 4, 0)) == ""            # through the opening tunnel
    assert contains(barrier, (0, 4, 35)) == "lip_slab"    # upper lip / nose base
    assert contains(barrier, (0, 4, -40)) == "lip_slab"   # lower lip / chin
    assert contains(barrier, (0, 12, 35)) == ""           # in front of the lips
    assert contains(barrier, (27.5, -10, 0)) == "cheek_high_u"
    assert contains(barrier, (0, -10, 0)) == ""           # intra-oral space


def test_mesh_path_preflight_never_includes_the_mouth_barrier():
    # r5/r6 2026-10-02: barrier meshes in the merged VTK collision check stalled
    # Find Reachable Base for hours; MoveIt enforces the barrier instead.
    source = (ROOT / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_robot_placement.py").read_text()
    start = source.index("def step6PathPreflightObstaclesWorld")
    body = source[start:source.index("\n    def ", start + 10)]
    assert "step6MouthBarrierPolydataWorld" not in body
