"""Mouth-portal prefix gate: virtual barrier for unsegmented lips and cheeks.

Simulation planning gate (world RAS mm, pure numpy). Lips, cheeks and the
oral aperture are not segmented in the CBCT, so the tool must enter the
intra-oral space through a portal bounded by the four canine crowns:

    upper right 13 -> upper left 23 -> lower left 33 -> lower right 43

(lower canines taken after the virtual mouth opening). The four cusp tips
are generally not coplanar; a best-fit plane is used and the vertices are
projected onto it. The plane normal points OUTWARD (anterior, away from the
molars). The TCP gate passes only if the planned path ends inside (at
PreEntry), starts outside or within the opening, and every crossing of the
plane passes through the opening. The 3D mouth barrier (end of this module)
makes the same rule a MoveIt collision object for the whole robot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

PORTAL_VERTEX_FDI = ("13", "23", "33", "43")
# Nearest-neighbour substitutes when a canine is missing or unsegmented:
# first premolar, then lateral incisor of the same quadrant.
PORTAL_VERTEX_FALLBACK_FDI = {
    "13": ("14", "12"),
    "23": ("24", "22"),
    "33": ("34", "32"),
    "43": ("44", "42"),
}


def cusp_tip(points_world_mm: np.ndarray, occlusal_direction: np.ndarray) -> np.ndarray:
    """Crown point furthest along the tooth's occlusal (biting) direction."""
    points = np.asarray(points_world_mm, dtype=float).reshape(-1, 3)
    direction = np.asarray(occlusal_direction, dtype=float)
    direction = direction / np.linalg.norm(direction)
    return points[int(np.argmax(points @ direction))].copy()


def choose_vertex_teeth(available_fdi) -> dict[str, dict[str, object]]:
    """Map each portal vertex to the canine or its nearest-neighbour substitute."""
    available = {str(value) for value in available_fdi}
    chosen = {}
    for vertex in PORTAL_VERTEX_FDI:
        for candidate in (vertex, *PORTAL_VERTEX_FALLBACK_FDI[vertex]):
            if candidate in available:
                chosen[vertex] = {"fdi": candidate, "substituted": candidate != vertex}
                break
        else:
            raise ValueError(
                f"Mouth portal vertex {vertex} has no canine, first premolar or lateral incisor."
            )
    return chosen


@dataclass
class MouthPortal:
    origin_mm: np.ndarray
    normal_outward: np.ndarray
    u_axis: np.ndarray
    v_axis: np.ndarray
    vertices_mm: np.ndarray            # projected onto the plane, portal order
    source_vertices_mm: np.ndarray     # original cusp tips, portal order
    planarity_max_mm: float
    vertex_teeth: dict = field(default_factory=dict)

    def signed_distance(self, point_mm) -> float:
        return float((np.asarray(point_mm, float) - self.origin_mm) @ self.normal_outward)

    def to_plane_2d(self, point_mm) -> np.ndarray:
        delta = np.asarray(point_mm, float) - self.origin_mm
        return np.array([delta @ self.u_axis, delta @ self.v_axis])

    def polygon_2d(self) -> np.ndarray:
        return np.array([self.to_plane_2d(v) for v in self.vertices_mm])


def build_portal(vertices_mm, outside_hint_mm, vertex_teeth=None) -> MouthPortal:
    """Best-fit plane through the 4 ordered vertices; normal toward ``outside_hint``."""
    source = np.asarray(vertices_mm, dtype=float).reshape(4, 3)
    origin = source.mean(axis=0)
    _u, singular, vt = np.linalg.svd(source - origin)
    normal = vt[2] / np.linalg.norm(vt[2])
    if singular[1] < 1.0e-6:
        raise ValueError("Mouth portal vertices are degenerate (collinear).")
    if (np.asarray(outside_hint_mm, float) - origin) @ normal < 0.0:
        normal = -normal
    projected = source - np.outer((source - origin) @ normal, normal)
    u_axis = projected[1] - projected[0]
    u_axis = u_axis - (u_axis @ normal) * normal
    u_axis = u_axis / np.linalg.norm(u_axis)
    v_axis = np.cross(normal, u_axis)
    return MouthPortal(origin, normal, u_axis, v_axis, projected, source,
                       float(np.max(np.abs((source - origin) @ normal))), dict(vertex_teeth or {}))


def _point_in_polygon(point: np.ndarray, polygon: np.ndarray) -> bool:
    x, y = float(point[0]), float(point[1])
    inside = False
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        if (y1 > y) != (y2 > y):
            crossing = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < crossing:
                inside = not inside
    return inside


def _edge_margin(point: np.ndarray, polygon: np.ndarray) -> float:
    best = float("inf")
    for index in range(len(polygon)):
        a, b = polygon[index], polygon[(index + 1) % len(polygon)]
        edge = b - a
        t = float(np.clip((point - a) @ edge / max(edge @ edge, 1e-12), 0.0, 1.0))
        best = min(best, float(np.linalg.norm(point - (a + t * edge))))
    return best


def check_tcp_path(portal: MouthPortal, tcp_path_mm) -> dict:
    """Gate the planned TCP path (start ... PreEntry) through the portal."""
    path = [np.asarray(p, float) for p in tcp_path_mm]
    if len(path) < 2:
        return {"status": "failed", "reason": "path_too_short"}
    distances = [portal.signed_distance(p) for p in path]
    result = {"start_signed_distance_mm": distances[0], "end_signed_distance_mm": distances[-1],
              "planarity_max_mm": portal.planarity_max_mm}
    polygon = portal.polygon_2d()
    home_inside = distances[0] <= 0.0
    if home_inside and not _point_in_polygon(portal.to_plane_2d(path[0]), polygon):
        # Task Home already behind the lip line must lie within the opening.
        return {**result, "status": "failed", "reason": "start_inside_outside_portal"}
    if distances[-1] >= 0.0:
        return {**result, "status": "failed", "reason": "preentry_not_inside"}
    crossings = []
    for index in range(len(path) - 1):
        d0, d1 = distances[index], distances[index + 1]
        if (d0 > 0.0) != (d1 > 0.0):
            t = d0 / (d0 - d1)
            point = path[index] + t * (path[index + 1] - path[index])
            local = portal.to_plane_2d(point)
            crossings.append({
                "segment_index": index,
                "direction": "inward" if d0 > 0.0 else "outward",
                "point_ras_mm": point.tolist(),
                "inside_portal": _point_in_polygon(local, polygon),
                "edge_margin_mm": _edge_margin(local, polygon),
            })
    result["crossings"] = crossings
    # Leaving and re-entering is allowed (r4, 2026-10-02): every crossing of the
    # lip line, in either direction, must pass through the opening.
    bad = [c for c in crossings if not c["inside_portal"]]
    if bad:
        return {**result, "status": "failed", "reason": "crossing_outside_portal",
                "first_bad_crossing": bad[0]}
    inward = [c for c in crossings if c["direction"] == "inward"]
    if home_inside:
        return {**result, "status": "passed", "reason": "", "mode": "home_inside_portal",
                "entry_crossing": inward[-1] if inward else None}
    return {**result, "status": "passed", "reason": "", "entry_crossing": inward[-1]}


ANTERIOR_TEETH_FDI = ("11", "12", "13", "21", "22", "23", "31", "32", "33", "41", "42", "43")
LIP_LINE_MARGIN_MM = 2.0
PORTAL_ENLARGE_MM = 5.0  # operator option (b): cusp-tip outline enlarged all round


def shift_portal_to_lip_line(portal: MouthPortal, anterior_points_mm, margin_mm: float = LIP_LINE_MARGIN_MM) -> MouthPortal:
    """Option A (operator 2026-10-02): move the canine-shaped portal outward,
    parallel to itself, to just in front of the most labial anterior-tooth point
    plus a margin, approximating the lip line. In-plane shape is unchanged."""
    points = np.asarray(anterior_points_mm, dtype=float).reshape(-1, 3)
    offset = max(0.0, float(np.max((points - portal.origin_mm) @ portal.normal_outward))) + float(margin_mm)
    shift = portal.normal_outward * offset
    return MouthPortal(portal.origin_mm + shift, portal.normal_outward, portal.u_axis, portal.v_axis,
                       portal.vertices_mm + shift, portal.source_vertices_mm, portal.planarity_max_mm,
                       {**portal.vertex_teeth, "lip_line_offset_mm": offset})


def enlarge_portal(portal: MouthPortal, margin_mm: float = PORTAL_ENLARGE_MM) -> MouthPortal:
    """Grow the portal outline in its plane by ``margin_mm`` (each edge moved
    outward by the margin; corners follow the edge offsets)."""
    poly = portal.polygon_2d()
    count = len(poly)
    signed_area = 0.5 * sum(poly[i, 0] * poly[(i + 1) % count, 1] - poly[(i + 1) % count, 0] * poly[i, 1]
                            for i in range(count))
    orientation = 1.0 if signed_area > 0 else -1.0
    normals = []
    for i in range(count):
        edge = poly[(i + 1) % count] - poly[i]
        n = np.array([edge[1], -edge[0]]) * orientation
        normals.append(n / np.linalg.norm(n))
    grown = []
    for i in range(count):
        n_prev, n_next = normals[i - 1], normals[i]
        bisector = n_prev + n_next
        scale = margin_mm / max(1e-6, float(bisector @ n_next) / float(np.linalg.norm(bisector)))
        grown.append(poly[i] + bisector / np.linalg.norm(bisector) * scale)
    vertices = np.array([portal.origin_mm + p[0] * portal.u_axis + p[1] * portal.v_axis for p in grown])
    return MouthPortal(portal.origin_mm, portal.normal_outward, portal.u_axis, portal.v_axis,
                       vertices, portal.source_vertices_mm, portal.planarity_max_mm,
                       {**portal.vertex_teeth, "enlarge_mm": float(margin_mm)})


# --- 3D mouth barrier (operator 2026-10-02: "3d barrier go"; edges "Both, GUI switch") ---
#
# The portal plane alone cannot steer the planner and only checks the TCP. The
# barrier turns the portal into solid virtual soft tissue that MoveIt checks
# against the whole robot:
#   lip slab   - a frame from the lip-line plane outward by BARRIER_LIP_THICKNESS_MM,
#                with the portal opening cut through it (a short tunnel), out to
#                the case teeth/jaw outline + BARRIER_OUTER_MARGIN_MM (nose base
#                to chin, cheek to cheek);
#   cheek walls - thin walls behind the slab, just outside the buccal-most teeth,
#                back to the last tooth.
# Opening height (edge mode):
#   "gum_line"    lips retracted: upper/lower edges at the anterior gum line
#                 (bone crest + GUM_MARGIN_ABOVE_CREST_MM), then enlarged;
#   "biting_edge" lips relaxed: edges at the canine cusp tips, then enlarged;
#   "off"         no barrier and no portal gate (diagnosis only).
# Virtual anatomy for simulation planning; not a measured soft-tissue model.

BARRIER_EDGE_MODES = ("gum_line", "biting_edge", "off")
BARRIER_DEFAULT_EDGE_MODE = "gum_line"
GUM_MARGIN_ABOVE_CREST_MM = 2.0     # gingival margin sits ~2 mm occlusal of the bone crest
CREST_CONTACT_MM = 1.0              # tooth points within this of the jaw bone count as covered
CROWN_HEIGHT_FALLBACK_MM = 9.0      # cusp tip -> gum line when no jaw bone is segmented
BARRIER_LIP_THICKNESS_MM = 8.0
BARRIER_OUTER_MARGIN_MM = 10.0
CHEEK_WALL_GAP_MM = 2.0
CHEEK_WALL_THICKNESS_MM = 2.0


def _occlusal_axis_2d(portal: MouthPortal) -> np.ndarray:
    """Unit in-plane direction from the upper vertices (13, 23) to the lower (33, 43)."""
    poly = portal.polygon_2d()
    axis = poly[2:].mean(axis=0) - poly[:2].mean(axis=0)
    norm = float(np.linalg.norm(axis))
    if norm < 1.0e-6:
        raise ValueError("Mouth portal upper and lower vertices coincide.")
    return axis / norm


def apply_edge_mode(portal: MouthPortal, mode: str, upper_gum_points_mm=None,
                    lower_gum_points_mm=None) -> MouthPortal:
    """Set the opening's upper/lower edges for the lip edge mode.

    ``gum_line`` moves the two upper vertices apically to the most apical upper
    gum point and the two lower vertices to the most apical lower gum point
    (never shrinking the cusp-tip opening). ``biting_edge`` keeps the cusp tips.
    """
    if mode not in BARRIER_EDGE_MODES:
        raise ValueError(f"Unknown mouth barrier edge mode {mode!r}.")
    if mode != "gum_line":
        return MouthPortal(portal.origin_mm, portal.normal_outward, portal.u_axis, portal.v_axis,
                           portal.vertices_mm, portal.source_vertices_mm, portal.planarity_max_mm,
                           {**portal.vertex_teeth, "edge_mode": mode})
    if upper_gum_points_mm is None or lower_gum_points_mm is None:
        raise ValueError("Gum-line edges need upper and lower gum points.")
    occlusal = _occlusal_axis_2d(portal)
    poly = portal.polygon_2d()
    upper_level = min(float(portal.to_plane_2d(p) @ occlusal)
                      for p in np.asarray(upper_gum_points_mm, float).reshape(-1, 3))
    lower_level = max(float(portal.to_plane_2d(p) @ occlusal)
                      for p in np.asarray(lower_gum_points_mm, float).reshape(-1, 3))
    moved = []
    for index, point in enumerate(poly):
        level = float(point @ occlusal)
        target = min(level, upper_level) if index < 2 else max(level, lower_level)
        moved.append(point + (target - level) * occlusal)
    vertices = np.array([portal.origin_mm + p[0] * portal.u_axis + p[1] * portal.v_axis for p in moved])
    poly_before = portal.polygon_2d()
    return MouthPortal(portal.origin_mm, portal.normal_outward, portal.u_axis, portal.v_axis,
                       vertices, portal.source_vertices_mm, portal.planarity_max_mm,
                       {**portal.vertex_teeth, "edge_mode": mode,
                        "opening_height_cusp_tips_mm": float((poly_before[2:].mean(0) - poly_before[:2].mean(0)) @ occlusal),
                        "opening_height_gum_line_mm": float(lower_level - upper_level)})


def gum_points_from_crest(tooth_points_mm, bone_distance_mm, occlusal_direction,
                          cusp_tip_mm) -> tuple[np.ndarray, str]:
    """Gum point of one tooth: its most occlusal bone-covered point moved
    GUM_MARGIN_ABOVE_CREST_MM toward the biting edge. Without bone contact the
    cusp tip moved CROWN_HEIGHT_FALLBACK_MM apically is used."""
    points = np.asarray(tooth_points_mm, float).reshape(-1, 3)
    direction = np.asarray(occlusal_direction, float)
    direction = direction / np.linalg.norm(direction)
    covered = points[np.asarray(bone_distance_mm, float) < CREST_CONTACT_MM]
    if len(covered):
        crest = covered[int(np.argmax(covered @ direction))]
        return crest + GUM_MARGIN_ABOVE_CREST_MM * direction, "bone_crest"
    return np.asarray(cusp_tip_mm, float) - CROWN_HEIGHT_FALLBACK_MM * direction, "crown_height_estimate"


@dataclass
class BarrierPart:
    name: str              # "lip_slab", "cheek_right", "cheek_left"
    points_mm: np.ndarray  # (N, 3) world RAS mm
    triangles: np.ndarray  # (M, 3) int, outward-facing, closed and manifold


def _oriented(points: np.ndarray, triangles, outward_of) -> np.ndarray:
    """Flip each triangle so its normal points away from ``outward_of(tri)``'s
    interior reference point."""
    out = []
    for tri in triangles:
        a, b, c = (points[i] for i in tri)
        normal = np.cross(b - a, c - a)
        centre = (a + b + c) / 3.0
        out.append(tri if normal @ (centre - outward_of(tri)) >= 0.0 else (tri[0], tri[2], tri[1]))
    return np.asarray(out, dtype=int)


def _box(name, origin, axes, ranges) -> BarrierPart:
    """Closed box spanning ``ranges`` [(lo, hi)] x3 along the 3 ``axes``."""
    corners = []
    for i in (0, 1):
        for j in (0, 1):
            for k in (0, 1):
                corners.append(origin + axes[0] * ranges[0][i] + axes[1] * ranges[1][j] + axes[2] * ranges[2][k])
    points = np.asarray(corners)
    index = lambda i, j, k: i * 4 + j * 2 + k  # noqa: E731
    faces = []
    for axis in range(3):
        for side in (0, 1):
            quad = []
            for a in (0, 1):
                for b in (0, 1):
                    ijk = [0, 0, 0]
                    ijk[axis] = side
                    others = [x for x in range(3) if x != axis]
                    ijk[others[0]], ijk[others[1]] = a, b
                    quad.append(index(*ijk))
            faces += [(quad[0], quad[1], quad[3]), (quad[0], quad[3], quad[2])]
    centre = points.mean(axis=0)
    return BarrierPart(name, points, _oriented(points, faces, lambda _tri: centre))


@dataclass
class MouthBarrier:
    opening: MouthPortal
    outer_2d: np.ndarray
    parts: list
    summary: dict


def build_mouth_barrier(opening: MouthPortal, extent_points_mm, teeth_points_mm,
                        lip_thickness_mm: float = BARRIER_LIP_THICKNESS_MM,
                        outer_margin_mm: float = BARRIER_OUTER_MARGIN_MM) -> MouthBarrier:
    """Lip slab with the opening tunnelled through it, plus two cheek walls.

    ``opening`` is the final (lip-line, edge-mode, enlarged) portal; its plane
    is the slab's inner face and the slab extends ``lip_thickness_mm`` outward.
    ``extent_points_mm`` (teeth + jaws) sets the slab outline; ``teeth_points_mm``
    sets the cheek walls (buccal-most and most posterior tooth points).
    """
    poly = opening.polygon_2d()
    count = len(poly)
    area = 0.5 * sum(poly[i, 0] * poly[(i + 1) % count, 1] - poly[(i + 1) % count, 0] * poly[i, 1]
                     for i in range(count))
    order = list(range(count)) if area > 0 else list(reversed(range(count)))  # CCW about +normal
    inner = poly[order]
    centre = inner.mean(axis=0)
    extent = np.array([opening.to_plane_2d(p) for p in np.asarray(extent_points_mm, float).reshape(-1, 3)])
    lo = np.minimum(extent.min(axis=0), inner.min(axis=0)) - outer_margin_mm
    hi = np.maximum(extent.max(axis=0), inner.max(axis=0)) + outer_margin_mm
    outer = []
    quadrants = set()
    for point in inner:
        side = point >= centre
        quadrants.add((bool(side[0]), bool(side[1])))
        outer.append([hi[0] if side[0] else lo[0], hi[1] if side[1] else lo[1]])
    if len(quadrants) != 4:
        raise ValueError("Mouth barrier opening is too skewed to frame (vertices share a quadrant).")
    outer = np.asarray(outer)

    def lift(p2, n):
        return opening.origin_mm + p2[0] * opening.u_axis + p2[1] * opening.v_axis + n * opening.normal_outward

    t = float(lip_thickness_mm)
    # Indices: inner front 0-3, outer front 4-7, inner back 8-11, outer back 12-15.
    points = np.array([lift(p, t) for p in inner] + [lift(p, t) for p in outer]
                      + [lift(p, 0.0) for p in inner] + [lift(p, 0.0) for p in outer])
    tris, refs = [], []
    mid_front = lift(centre, t)
    for i in range(4):
        j = (i + 1) % 4
        # front ring (+normal), back ring (-normal)
        for a, b, c, d, sign in ((i, j, 4 + j, 4 + i, 1.0), (8 + i, 8 + j, 12 + j, 12 + i, -1.0)):
            for tri in ((a, b, c), (a, c, d)):
                tris.append(tri)
                refs.append(("dir", opening.normal_outward * sign))
        # outer wall (away from centre), inner tunnel wall (toward centre)
        for a, b, c, d, kind in ((4 + i, 4 + j, 12 + j, 12 + i, "out"), (i, j, 8 + j, 8 + i, "in")):
            for tri in ((a, b, c), (a, c, d)):
                tris.append(tri)
                refs.append((kind, None))

    oriented = []
    for tri, (kind, direction) in zip(tris, refs):
        a, b, c = (points[k] for k in tri)
        normal = np.cross(b - a, c - a)
        face_centre = (a + b + c) / 3.0
        if kind == "dir":
            want = direction
        else:
            radial = face_centre - mid_front
            radial = radial - (radial @ opening.normal_outward) * opening.normal_outward
            want = radial if kind == "out" else -radial
        oriented.append(tri if normal @ want >= 0.0 else (tri[0], tri[2], tri[1]))
    parts = [BarrierPart("lip_slab", points, np.asarray(oriented, dtype=int))]

    teeth = np.array([opening.to_plane_2d(p) for p in np.asarray(teeth_points_mm, float).reshape(-1, 3)])
    depth = np.array([opening.signed_distance(p) for p in np.asarray(teeth_points_mm, float).reshape(-1, 3)])
    back = float(depth.min()) - CHEEK_WALL_GAP_MM
    axes = (opening.u_axis, opening.v_axis, opening.normal_outward)
    u_low = min(float(teeth[:, 0].min()), float(inner[:, 0].min())) - CHEEK_WALL_GAP_MM
    u_high = max(float(teeth[:, 0].max()), float(inner[:, 0].max())) + CHEEK_WALL_GAP_MM
    v_range = (float(lo[1]), float(hi[1]))
    if back < 0.0:
        for name, u_range in (("cheek_low_u", (u_low - CHEEK_WALL_THICKNESS_MM, u_low)),
                              ("cheek_high_u", (u_high, u_high + CHEEK_WALL_THICKNESS_MM))):
            parts.append(_box(name, opening.origin_mm, axes, (u_range, v_range, (back, 0.0))))
    summary = {
        "edge_mode": opening.vertex_teeth.get("edge_mode"),
        "opening_vertices_ras_mm": opening.vertices_mm.tolist(),
        "opening_width_mm": float(inner[:, 0].max() - inner[:, 0].min()),
        "opening_height_mm": float(inner[:, 1].max() - inner[:, 1].min()),
        "slab_outline_u_mm": [float(lo[0]), float(hi[0])],
        "slab_outline_v_mm": [float(lo[1]), float(hi[1])],
        "lip_thickness_mm": t,
        "cheek_wall_depth_mm": float(-back) if back < 0.0 else 0.0,
        "cheek_wall_u_mm": [u_low, u_high],
        "parts": [part.name for part in parts],
    }
    return MouthBarrier(opening, outer, parts, summary)


def barrier_contains_point(barrier: MouthBarrier, point_mm) -> str:
    """Name of the barrier part containing ``point_mm`` (test/diagnostic aid), else ""."""
    opening = barrier.opening
    p2 = opening.to_plane_2d(point_mm)
    n = opening.signed_distance(point_mm)
    t = barrier.summary["lip_thickness_mm"]
    lo_u, hi_u = barrier.summary["slab_outline_u_mm"]
    lo_v, hi_v = barrier.summary["slab_outline_v_mm"]
    if 0.0 <= n <= t and lo_u <= p2[0] <= hi_u and lo_v <= p2[1] <= hi_v \
            and not _point_in_polygon(p2, opening.polygon_2d()):
        return "lip_slab"
    u_low, u_high = barrier.summary["cheek_wall_u_mm"]
    depth = barrier.summary["cheek_wall_depth_mm"]
    if -depth <= n <= 0.0 and lo_v <= p2[1] <= hi_v:
        if u_low - CHEEK_WALL_THICKNESS_MM <= p2[0] <= u_low:
            return "cheek_low_u"
        if u_high <= p2[0] <= u_high + CHEEK_WALL_THICKNESS_MM:
            return "cheek_high_u"
    return ""
