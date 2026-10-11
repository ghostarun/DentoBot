"""Experimental Auto Task Home geometry and draft-only orchestration.

World RAS millimetres throughout. Depth is independent of the drill axis:
positive depth moves from the incisor midpoint toward the selected Entry.
Runtime IK, static collision checks and FK remain owned by the existing bridge.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import acos, degrees, hypot, isfinite

DEFAULT_DEPTH_MM = 0.0


def _xyz(values, label):
    if len(values) != 3:
        raise ValueError(f"{label} must contain three coordinates.")
    result = tuple(float(value) for value in values)
    if not all(isfinite(value) for value in result):
        raise ValueError(f"{label} must be finite.")
    return result


def _unit(vector, label):
    length = hypot(*vector)
    if not isfinite(length) or length <= 1e-12:
        raise ValueError(f"{label} is degenerate.")
    return tuple(value / length for value in vector)


@dataclass(frozen=True)
class AutoTaskHomeGeometry:
    midpoint_world_ras_mm: tuple[float, float, float]
    position_world_ras_mm: tuple[float, float, float]
    drill_axis_world_ras_unit: tuple[float, float, float]
    depth_mm: float


def auto_task_home_geometry(midpoint, entry, target, *, depth_mm=DEFAULT_DEPTH_MM):
    """Offset an existing biting-edge midpoint without recomputing landmarks."""
    midpoint = _xyz(midpoint, "Incisor midpoint")
    entry = _xyz(entry, "Entry")
    target = _xyz(target, "Target")
    depth_mm = float(depth_mm)
    if not isfinite(depth_mm):
        raise ValueError("Auto Task Home depth must be finite.")
    drill_axis = _unit(tuple(t - e for e, t in zip(entry, target)), "Entry→Target axis")
    position = midpoint
    if depth_mm != 0.0:
        inward = _unit(tuple(e - m for m, e in zip(midpoint, entry)), "Midpoint→Entry depth axis")
        position = _xyz(tuple(m + depth_mm * d for m, d in zip(midpoint, inward)), "Offset Home")
    return AutoTaskHomeGeometry(midpoint, position, drill_axis, depth_mm)


def pose_residual(geometry, pose):
    """Compare position and directed drill axis; axial roll is unconstrained."""
    position = _xyz(tuple(pose[i][3] for i in range(3)), "FK position")
    axis = _unit(_xyz(tuple(pose[i][2] for i in range(3)), "FK axis"), "FK axis")
    distance = hypot(*(p - q for p, q in zip(position, geometry.position_world_ras_mm)))
    cosine = sum(a * b for a, b in zip(axis, geometry.drill_axis_world_ras_unit))
    return distance, degrees(acos(max(-1.0, min(1.0, cosine))))


def incisor_biting_edge_midpoint(clouds):
    """Central incisor edge estimate, using the mouth-portal biting-point rule.

    Require both central incisors in each arch; no silent canine/centroid fallback.
    Clouds must already be in current opened world RAS millimetres.
    """
    import numpy as np
    from .mouth_portal import cusp_tip

    points = {}
    for fdi in ("11", "21", "31", "41"):
        cloud = np.asarray(clouds[fdi], dtype=float)
        if cloud.ndim != 2 or cloud.shape[1] != 3 or len(cloud) == 0 or not np.isfinite(cloud).all():
            raise ValueError(f"Central incisor {fdi} needs a finite nonempty surface.")
        points[fdi] = cloud
    upper = np.mean([points[fdi].mean(axis=0) for fdi in ("11", "21")], axis=0)
    lower = np.mean([points[fdi].mean(axis=0) for fdi in ("31", "41")], axis=0)
    direction = np.asarray(_unit(tuple(lower - upper), "Upper→lower incisor biting direction"))
    tips = {fdi: cusp_tip(cloud, direction if fdi in ("11", "21") else -direction)
            for fdi, cloud in points.items()}
    upper_edge = np.mean([tips["11"], tips["21"]], axis=0)
    lower_edge = np.mean([tips["31"], tips["41"]], axis=0)
    return {"upperEdgeWorldRasMm": tuple(upper_edge),
            "lowerEdgeWorldRasMm": tuple(lower_edge),
            "centerWorldRasMm": tuple((upper_edge + lower_edge) / 2.0),
            "incisorFdi": ("11", "21", "31", "41")}


def incisor_biting_edge_source(facade, parameter):
    """Reuse existing surface/world-opening adapters without creating scene nodes."""
    from vtk.util.numpy_support import vtk_to_numpy

    roi = facade.defaultTaskSpaceRoi()  # Existing Case Foundation freshness/role gate.
    if roi.success is not True:
        raise ValueError(roi.message)
    logic = facade._logic
    segmentation = parameter.teethSegmentation
    if segmentation is None:
        raise ValueError("Reviewed teeth segmentation is required for Auto Task Home.")
    by_fdi = logic._step6ToothSegmentIdsByFdi(segmentation)
    clouds = {}
    for fdi in ("11", "21", "31", "41"):
        if fdi not in by_fdi:
            raise ValueError(f"Central incisor {fdi} is unavailable; Auto Task Home cannot estimate its biting edge.")
        world = logic._segmentationSegmentsSurfaceWorld(segmentation, {by_fdi[fdi]})
        if world is None or world.GetNumberOfPoints() == 0:
            raise ValueError(f"Central incisor {fdi} has no surface.")
        if fdi in ("31", "41"):
            world = logic._step6CaseJawPolydataWorld(parameter, world)
        clouds[fdi] = vtk_to_numpy(world.GetPoints().GetData()).astype(float)
    return {**dict(roi.payload), **incisor_biting_edge_midpoint(clouds)}


def auto_task_home_ik_seeds(facade):
    """Default native seed then sixteen bounded elbow/yaw branch hints.

    These are solver inputs only, never saved Home or collision authority.
    Reuse the local URDF limit owner and the reference PreEntry seed pattern.
    """
    from DENTOStep6Planning import default_task_joint_limits_from_urdf
    from DENTORobotPlacement import joint_positions_si_from_display

    paths = facade._logic.robotDescriptionPaths()
    if not paths or not paths[0]:
        raise ValueError("The local robot URDF is unavailable for Auto Task Home seeds.")
    limits = default_task_joint_limits_from_urdf(paths[0])
    ranges = [getattr(limits, f"joint_{i}") for i in range(1, 6)]
    bounds = [(float(r.minimum), float(r.maximum)) for r in ranges]
    if any(not isfinite(lo) or not isfinite(hi) or lo > hi for lo, hi in bounds):
        raise ValueError("Auto Task Home mechanical seed limits are invalid.")
    middle = [(lo + hi) / 2.0 for lo, hi in bounds]
    seeds = [None]
    seen = set()
    for first in (0.0, 1.5, 3.0, 4.5):
        for third in (0.0, 1.5, 3.0, 4.5):
            display = list(middle)
            for index, angle in ((0, first), (2, third)):
                lo, hi = bounds[index]
                display[index] = min(hi, max(lo, degrees(angle)))
            seed = joint_positions_si_from_display(*display)
            key = tuple(seed.values())
            if key not in seen:
                seen.add(key)
                seeds.append(seed)
    return seeds


def _solve_home_ik(facade, result_type, seed):
    """Classify branch misses separately from unavailable validation authority."""
    bridge = facade._bridge
    ok, message, positions, diagnostic = bridge.solve_moveit_tcp_position_axis_goal(
        seed_joint_positions_si=seed, avoid_collisions=True,
    )
    diagnostic = dict(diagnostic or {})
    details = {"ikDiagnostic": diagnostic, "authoritativeStaticValidity": False,
               "collisionAwareValidated": False, "branchMiss": False}
    if ok is not True:
        # Only defined native branch outcomes may advance to another seed.
        details["branchMiss"] = diagnostic.get("termination_reason") in {
            "colliding", "iteration_limit", "timeout", "stalled",
        }
        return result_type(False, "auto_task_home_ik_failed", str(message), details=details)
    names = tuple(bridge.ROS2_JOINT_SI_ORDER)
    if not isinstance(positions, dict) or set(positions) != set(names):
        raise ValueError("Auto Task Home IK returned an incomplete joint vector.")
    candidate = {name: float(positions[name]) for name in names}
    if not all(isfinite(value) for value in candidate.values()):
        raise ValueError("Auto Task Home IK returned non-finite joints.")
    valid, static_message, authoritative = bridge.check_moveit_static_joint_state(candidate)
    details["staticValidityMessage"] = str(static_message)
    details["authoritativeStaticValidity"] = authoritative is True
    if authoritative is not True:
        return result_type(False, "auto_task_home_ik_failed",
                           "Authoritative static validity unavailable: " + str(static_message), details=details)
    if valid is not True:
        details["branchMiss"] = True
        return result_type(False, "auto_task_home_ik_failed",
                           "Auto Task Home candidate collided: " + str(static_message), details=details)
    details["collisionAwareValidated"] = True
    return result_type(True, "ik_solved", str(message), details=details, payload=candidate)


def propose_auto_task_home(facade, result_type, bridge_policy, *, depth_mm=DEFAULT_DEPTH_MM):
    """Return a guarded five-joint draft, never review/save/plan/apply it."""
    details = {"depthMm": depth_mm, "draftOnly": True}
    try:
        parameter = facade._require_context()

        def inputs():
            # Reuse the same connected Home-review gate and identity owner.
            identity = facade._manual_jog_current_identity(parameter, for_task_home_review=True)
            if (facade._manual_base_acceptance_in_progress
                    or facade._manual_base_acceptance_uncertain
                    or facade._manual_jog_uncertainty
                    or facade._manual_task_home_acceptance_in_progress
                    or facade._manual_task_home_acceptance_uncertain
                    or facade._manual_task_home_reconciliation_in_progress
                    or facade._manual_jog_in_progress
                    or facade._manual_jog_reconciliation_required):
                raise ValueError("Resolve the outstanding Home or manual-jog operation first.")
            source = incisor_biting_edge_source(facade, parameter)
            trajectory = facade._logic.step6TrajectorySummary(parameter)
            if trajectory.get("isValid") is not True:
                raise ValueError("Select a valid Entry→Target trajectory before Auto Task Home.")
            geometry = auto_task_home_geometry(
                source["centerWorldRasMm"], trajectory["entryRas"], trajectory["targetRas"],
                depth_mm=depth_mm,
            )
            return identity, source, trajectory, geometry

        before = inputs()
        scene = facade.moveItSceneComparison()
        if scene is None or scene.get("matches") is not True:
            raise ValueError("Synchronize and verify the current MoveIt collision scene before Auto Task Home.")
        identity, roi, trajectory, geometry = before
        details.update({"midpointWorldRasMm": geometry.midpoint_world_ras_mm,
                        "positionWorldRasMm": geometry.position_world_ras_mm,
                        "drillAxisWorldRasUnit": geometry.drill_axis_world_ras_unit,
                        "depthMm": geometry.depth_mm, "source": roi,
                        "taskHomeReviewIdentity": dict(identity),
                        "trajectoryWorldRasMm": {
                            "entry": _xyz(trajectory["entryRas"], "Entry"),
                            "target": _xyz(trajectory["targetRas"], "Target"),
                        }})
        pose = facade._bridge.tool_pose_matrices_world_mm(
            trajectory["entryRas"], trajectory["targetRas"], 2,
        )[0]
        for i, value in enumerate(geometry.position_world_ras_mm):
            pose.SetElement(i, 3, value)
        goal = facade.setTcpGoal(pose)
        if goal.success is not True:
            raise ValueError(goal.message)
        seeds = auto_task_home_ik_seeds(facade)
        details["ikSeedBudget"] = len(seeds)
        details["ikAttempts"] = []
        solved = None
        for index, seed in enumerate(seeds):
            if inputs() != before:
                raise ValueError("Auto Task Home inputs changed between IK seeds.")
            current_scene = facade.moveItSceneComparison()
            if current_scene is None or current_scene.get("matches") is not True:
                raise ValueError("MoveIt collision scene changed between Auto Task Home seeds.")
            solved = _solve_home_ik(facade, result_type, seed)
            details["ikAttempts"].append({
                "index": index, "seedJointPositionsSi": seed,
                "success": solved.success is True, "message": solved.message,
                **dict(solved.details or {}),
            })
            details.update(dict(solved.details or {}))
            if solved.success is True:
                details["selectedIkSeedIndex"] = index
                break
            if solved.details.get("branchMiss") is not True:
                return result_type(False, "auto_task_home_ik_failed", solved.message, details=details)
        if solved.success is not True:
            return result_type(False, "auto_task_home_ik_failed",
                               "Bounded same-pose IK seed search found no valid Home; "
                               "this does not prove infeasibility. Last outcome: " + solved.message,
                               details=details)
        facade._manual_task_home_candidate_within_mechanical_limits(solved.payload)
        ok, message, actual_pose = facade._bridge.compute_moveit_tcp_pose_world_ras_mm(
            solved.payload, base_transform=parameter.robotBaseTransform,
        )
        if ok is not True or actual_pose is None:
            raise ValueError("Auto Task Home FK validation failed: " + str(message))
        position_error, axis_error = pose_residual(geometry, actual_pose)
        details.update({"positionResidualMm": position_error, "axisResidualDeg": axis_error})
        if (position_error > bridge_policy.CARTESIAN_START_POSITION_TOLERANCE_MM
                or axis_error > bridge_policy.CARTESIAN_START_ORIENTATION_TOLERANCE_DEG):
            raise ValueError(f"Auto Task Home FK residual exceeds existing limits: {position_error:.6g} mm / {axis_error:.6g} deg.")
        if inputs() != before:
            raise ValueError("Auto Task Home inputs changed during IK; generate a fresh draft.")
        scene = facade.moveItSceneComparison()
        if scene is None or scene.get("matches") is not True:
            raise ValueError("MoveIt collision scene changed during Auto Task Home IK.")
        return result_type(
            True, "auto_task_home_draft_ready",
            "Auto Task Home draft ready at the opened incisor biting-edge midpoint "
            f"(depth {geometry.depth_mm:g} mm), facing Entry→Target. Review, Plan + Apply, "
            "then Accept & Validate to save Home. No motion was sent.",
            details=details, payload=solved.payload,
        )
    except Exception as exc:
        return result_type(False, "auto_task_home_blocked", str(exc), details=details)
