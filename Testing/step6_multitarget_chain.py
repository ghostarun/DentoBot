"""Build Step 4B-5C for one more target tooth inside a multi-target case (S6-MULTI-TARGET-01).

Same logic calls as Testing/run_dentobot_stage6_target_generation.py (_target_case),
but it never removes derived planning nodes: other teeth's PreparedBranches must
survive. Runs inside Slicer (session driver). Records per-stage timing/metrics and
the registry before and after, including the eligibility of every other branch.
Simulation / research only; the generated template is NOT operator-reviewed.
"""

from __future__ import annotations

import json
import time

from DENTOGuideGeometry import normalize_target_docking_parameters


def _support_selection(logic, segmentation, target_fdi: str):
    records = logic.getTargetToothRecords(segmentation)
    by_fdi = {str(r.get("fdiNumber") or ""): r for r in records if r.get("fdiNumber")}
    preferred = ("42", "41", "33", "32") if target_fdi == "31" else ()
    if preferred and all(v in by_fdi for v in preferred):
        selected, policy = list(preferred), "saved_fdi31_support_ids"
    else:
        arch = logic.dentalArchForFdi(target_fdi)
        candidates = [v for v in by_fdi if v != target_fdi and logic.dentalArchForFdi(v) == arch]
        selected = sorted(candidates, key=lambda v: (abs(int(v) - int(target_fdi)), int(v)))[:4]
        policy = "nearest_four_same_arch_fdi"
    if not selected:
        raise ValueError(f"no same-arch support teeth for FDI{target_fdi}")
    return [by_fdi[v]["segmentId"] for v in selected], {"policy": policy, "support_fdi": selected}


def _branch_states(logic, parameter):
    registry = logic.syncDentoCaseTrajectoryRegistry(parameter)
    states = {}
    for branch_id, branch in (registry.get("prepared_branches") or {}).items():
        gate = logic.evaluatePreparedBranchEligibility(parameter, branch_id, registry=registry)
        states[branch_id] = {
            "target_fdi": str(branch.get("target_fdi") or branch.get("targetFdi") or ""),
            "eligible": bool(gate.get("eligible")),
            "reason": gate.get("reason"),
        }
    return registry, states


def build_branch(widget, trajectory, target_fdi: str, *, process_events) -> dict:
    logic, parameter = widget.logic, widget._parameterNode
    report = {"target_fdi": target_fdi, "trajectory": trajectory.GetName(), "stages": []}
    started = time.monotonic()

    def stage(name, **data):
        report["stages"].append({"stage": name, "t_sec": round(time.monotonic() - started, 1), **data})

    _registry, before = _branch_states(logic, parameter)
    report["branches_before"] = before
    segmentation = parameter.teethSegmentation
    record = next(r for r in logic.getTargetToothRecords(segmentation) if str(r.get("fdiNumber")) == target_fdi)
    target_id = record["segmentId"]

    # Select the target trajectory (no eligible branch yet: 4B-5C references are detached, not deleted).
    logic.activateDentoCaseTrajectory(parameter, trajectory)
    parameter.trajectoryLine = trajectory
    widget._bindPlanningTrajectoryNode(trajectory)
    process_events(0.2)
    if parameter.targetToothSegmentId != target_id:
        raise ValueError(f"FDI{target_fdi} activation did not select its target tooth")
    bounds = logic.getTrajectoryBoundsReport(trajectory, segmentation, target_id)
    summary = logic.getTrajectorySummary(trajectory)
    if not (bounds["allDefinedPointsWithinBounds"] and summary["isValid"] and trajectory.GetLocked()):
        raise ValueError(f"FDI{target_fdi} trajectory invalid/unlocked/out of bounds")
    stage("4A selected", length_mm=round(float(summary.get("lengthMm", 0.0) or 0.0), 3),
          jaw_owner=logic._targetJawOwner(parameter, target_id))

    support_ids, support_report = _support_selection(logic, segmentation, target_fdi)
    draft, _details = logic.createOrUpdateDraftTemplateSupportModel(segmentation, target_id, support_ids)
    parameter.draftTemplateSupportModel = draft
    parameter.templateSupportToothSegmentIdsJson = logic.encodeTemplateSupportSegmentIds(support_ids)
    stage("4B support anatomy", **support_report)

    boundary = logic.createOrResetTemplateSupportBoundary(draft)
    parameter.templateSupportBoundaryCurve = boundary
    plane, _plane_details = logic.createOrUpdateTemplateSupportBoundaryPlane(
        draft, trajectory,
        reverseDirection=bool(parameter.templateSupportDirectionReversed),
        depthFromEntryMm=float(parameter.templateSupportPlaneDepthMm),
        crownCapPercent=float(parameter.templateSupportCrownCapPercent),
    )
    widget._restoringTemplateSupportBoundary = True
    try:
        boundary, _metrics = logic.createOrUpdateTemplateSupportBoundaryFromPlane(
            draft, plane, trajectory,
            samplingSpacingMm=float(parameter.templateSupportCurveSamplingSpacingMm), curveNode=boundary)
    finally:
        widget._restoringTemplateSupportBoundary = False
    parameter.templateSupportBoundaryPlane = plane
    parameter.templateSupportBoundaryCurve = boundary
    visible, _visible_metrics = logic.createOrUpdateVisibleTemplateSupportModel(
        draft, boundary, directionTrajectory=trajectory,
        reverseDirection=bool(parameter.templateSupportDirectionReversed),
        samplingSpacingMm=float(parameter.templateSupportCurveSamplingSpacingMm),
        terminalCoveragePercent=float(parameter.templateTerminalSupportCoveragePercent),
    )
    insertion = visible.GetNodeReference(logic.TEMPLATE_VISIBLE_SUPPORT_INSERTION_DIRECTION_REFERENCE_ROLE)
    if insertion is None:
        raise ValueError(f"FDI{target_fdi} insertion direction was not created")
    parameter.visibleTemplateSupportModel = visible
    parameter.templateInsertionDirection = insertion
    logic.setSelectedTemplateGuideTrajectories(draft, [trajectory])
    process_events(0.1)
    visible_summary = logic.getVisibleTemplateSupportModelSummary(visible)
    if visible_summary["geometryState"] != "Current":
        raise ValueError(f"FDI{target_fdi} 5A visible support stale: {visible_summary['staleReason']}")
    stage("5A boundary, plane, visible support, insertion")

    undercut, blockout, _u = logic.createOrUpdateTemplateUndercutAnalysis(
        draft, visible, insertion,
        angleToleranceDeg=float(parameter.templateUndercutAngleToleranceDeg),
        interproximalReliefMm=float(parameter.templateInterproximalReliefMm),
        samplingSpacingMm=float(parameter.templateSamplingSpacingMm),
    )
    parameter.templateUndercutSurfaceModel = undercut
    parameter.templateUndercutBlockoutModel = blockout
    shell, _s = logic.createOrUpdatePatientContactShell(
        draft, visible, insertion, blockout,
        clearanceMm=float(parameter.templateShellClearanceMm),
        thicknessMm=float(parameter.templateShellThicknessMm),
        samplingSpacingMm=float(parameter.templateSamplingSpacingMm),
        blockoutSafetyMm=float(parameter.templateBlockoutSafetyMm),
        voxelClosingMm=float(parameter.templateShellVoxelClosingMm),
    )
    parameter.patientContactShellModel = shell
    stage("5B undercut + contact shell")

    docking_parameters = normalize_target_docking_parameters(
        pattern_radius_mm=float(parameter.targetDockingPatternRadiusMm),
        outer_diameter_mm=float(parameter.targetDockingOuterDiameterMm),
        bore_diameter_mm=float(parameter.targetDockingBoreDiameterMm),
        connector_diameter_mm=float(parameter.targetDockingConnectorDiameterMm),
        connector_thickness_mm=float(parameter.targetDockingConnectorThicknessMm),
        shared_depth_mm=float(parameter.targetDockingSharedDepthMm),
        individual_depths_mm=tuple(float(getattr(parameter, f"targetDockingDepth{i}Mm")) for i in range(1, 5)),
        individual_depths_enabled=bool(parameter.targetDockingIndividualDepthsEnabled),
        yaw_deg=float(parameter.targetDockingYawDeg),
        collision_clearance_mm=float(parameter.targetDockingCollisionClearanceMm),
        clearance_mm=float(parameter.templateDockingClearanceMm),
        reinforcement_radial_mm=float(parameter.templateReinforcementRadialMm),
        processing_resolution_mm=float(parameter.templateSamplingSpacingMm),
    )
    dock_plane, assembly, docking_details = logic.createOrUpdateTargetDockingAssembly(
        segmentation, target_id, [trajectory], docking_parameters, supportModel=draft,
        autoSelectYaw=False, measurementsVisible=bool(parameter.targetDockingMeasurementsVisible))
    colliding = int((docking_details.get("metrics", {}).get("collisionScreen") or {}).get("collidingDockCount", 0))
    auto_yaw = False
    if colliding:
        dock_plane, assembly, docking_details = logic.createOrUpdateTargetDockingAssembly(
            segmentation, target_id, [trajectory], docking_parameters, supportModel=draft,
            planeNode=dock_plane, assemblyModel=assembly, autoSelectYaw=True,
            measurementsVisible=bool(parameter.targetDockingMeasurementsVisible))
        auto_yaw = True
    dock_yaw = float(docking_details["parameters"]["yawDeg"])
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for node in (dock_plane, assembly):
        node.SetAttribute("DENTOBOT.OrientationState", "Confirmed")
        node.SetAttribute("DENTOBOT.OrientationConfirmedUtc", timestamp)
    # Yaw first: setting it after the assembly reference makes the widget mark the dock stale.
    parameter.targetDockingYawDeg = dock_yaw
    parameter.targetDockingYawConfirmed = True
    parameter.targetDockingReferencePlane = dock_plane
    parameter.targetDockingAssemblyModel = assembly
    process_events(0.2)
    dock_state = logic.getTargetDockingAssemblySummary(assembly)
    if dock_state["geometryState"] != "Current":
        raise ValueError(f"FDI{target_fdi} 4C dock stale after confirm: {dock_state['staleReason']}")
    # Template docking yaw (about the drill axis), not the robot Base yaw.
    stage("4C docking", initial_colliding_docks=colliding, auto_docking_yaw=auto_yaw, docking_yaw_deg=dock_yaw)

    final_model, role_models, _f = logic.createOrUpdateFinalPrintableTemplate(
        shell, assembly, [trajectory],
        outerDiameterMm=float(parameter.templateSleeveOuterDiameterMm),
        innerDiameterMm=float(parameter.templateSleeveInnerDiameterMm),
        heightMm=float(parameter.templateSleeveHeightMm),
        dockingClearanceMm=float(parameter.templateDockingClearanceMm),
        reinforcementRadialMm=float(parameter.templateReinforcementRadialMm),
        reinforcementDepthMm=float(parameter.templateReinforcementDepthMm),
        samplingSpacingMm=float(parameter.templateSamplingSpacingMm),
    )
    parameter.templateDockingAssemblyModel = role_models["docking"]
    parameter.templateDockingClearanceModel = role_models["clearance"]
    parameter.templateDockingReinforcementModel = role_models["reinforcement"]
    parameter.templateDockingChannelsModel = role_models["channels"]
    parameter.finalPrintableTemplateModel = final_model
    verification = logic.verifyFinalPrintableTemplate(final_model)
    final_summary = logic.getFinalPrintableTemplateSummary(final_model)
    metrics = final_summary.get("metrics", {})
    checks = {str(c.get("name")): str(c.get("result")) for c in verification.get("checks", []) if isinstance(c, dict)}
    stage("5C final template + verification", overall=verification.get("overall"),
          connected_regions=int(metrics.get("occupiedVolumeRegionCount", 0)),
          channel_residual=int(metrics.get("channelResidualOccupiedSampleCount", -1)),
          failed_checks=[k for k, v in checks.items() if v == "FAIL"])
    if verification.get("overall") not in ("PASS", "WARNING"):
        raise ValueError(f"FDI{target_fdi} Step 5C verification failed: {checks}")

    registry, after = _branch_states(logic, parameter)
    new_ids = sorted(set(after) - set(before))
    report.update({
        "final_template_id": final_model.GetID(),
        "branches_after": after,
        "new_branch_ids": new_ids,
        "selected_branch_id": registry.get("selected_branch_id"),
        "others_still_eligible": all(after.get(b, {}).get("eligible") for b, s in before.items() if s.get("eligible")),
        "duration_sec": round(time.monotonic() - started, 1),
        "verification_checks": checks,
    })
    return report
