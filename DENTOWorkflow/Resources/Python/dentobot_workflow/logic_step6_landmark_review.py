"""Explicit review/migration of restored Step 6A landmark points."""

from __future__ import annotations

from .runtime import *


def cancel_transient_step6_case_jaw_landmark_placement(
    logic,
    parameterNode,
) -> dict:
    """Cancel a non-persistent placement interaction without promoting points."""

    landmarksNode = parameterNode.step6CaseJawLandmarks
    if not logic.isStep6CaseJawLandmarksNode(landmarksNode):
        return {"cancelled": False, "definedPointCount": 0}
    pendingIndex = str(
        landmarksNode.GetAttribute("DENTOBOT.PendingLandmarkIndex") or ""
    )
    pendingSource = str(
        landmarksNode.GetAttribute("DENTOBOT.PendingSourceSegmentID") or ""
    )
    visibilitySnapshot = str(
        landmarksNode.GetAttribute("DENTOBOT.PlacementVisibilitySnapshotJson")
        or ""
    )
    hadTransientState = bool(pendingIndex or pendingSource or visibilitySnapshot)
    if not hadTransientState:
        return {
            "cancelled": False,
            "definedPointCount": landmarksNode.GetNumberOfDefinedControlPoints(),
        }
    logic.stopTrajectoryPlacement()
    logic._restoreStep6CaseJawLandmarkPlacementVisibility(
        parameterNode,
        landmarksNode,
    )
    landmarksNode.SetAttribute("DENTOBOT.PendingLandmarkIndex", None)
    landmarksNode.SetAttribute("DENTOBOT.PendingSourceSegmentID", None)
    return {
        "cancelled": True,
        "pendingLandmarkIndex": pendingIndex,
        "pendingSourceSegmentId": pendingSource,
        "definedPointCount": landmarksNode.GetNumberOfDefinedControlPoints(),
    }


def review_and_project_existing_step6_case_jaw_landmarks(
    logic,
    parameterNode,
    landmarksNode: vtkMRMLMarkupsFiducialNode,
    maximumResidualMm: float = 5.0,
) -> dict:
    """Revalidate four existing points against current source surfaces.

    This operator-invoked path never promotes restored landmarks silently. All
    projections are computed before evidence is committed, and any failed
    anatomical check restores the original points and evidence.
    """

    summary = logic.getStep6CaseJawLandmarkSummary(landmarksNode)
    if not summary["isComplete"]:
        raise ValueError(_("Exactly four existing landmarks are required."))
    maximumResidual = float(maximumResidualMm)
    if not math.isfinite(maximumResidual) or maximumResidual <= 0.0:
        raise ValueError(_("The landmark projection tolerance is invalid."))
    associations = logic.step6CaseJawLandmarkSegmentAssociations(parameterNode)
    segmentation = parameterNode.teethSegmentation
    if segmentation is None:
        raise ValueError(_("The authoritative dental segmentation is missing."))

    originalPoints = []
    proposedPoints = []
    proposedEvidence = []
    for index, segmentId in enumerate(associations):
        point = [0.0, 0.0, 0.0]
        landmarksNode.GetNthControlPointPositionWorld(index, point)
        originalPoints.append(tuple(float(value) for value in point))
        surface = logic._segmentationSegmentsSurfaceWorld(
            segmentation,
            {segmentId},
        )
        if surface is None or surface.GetNumberOfPoints() == 0:
            raise ValueError(
                _("The intended surface for %1 is unavailable.").replace(
                    "%1", logic.DRAFT_JAW_LANDMARK_LABELS[index]
                )
            )
        locator = vtk.vtkStaticCellLocator()
        locator.SetDataSet(surface)
        locator.BuildLocator()
        closest = [0.0, 0.0, 0.0]
        cellId = vtk.reference(0)
        subId = vtk.reference(0)
        distanceSquared = vtk.reference(0.0)
        locator.FindClosestPoint(
            point,
            closest,
            cellId,
            subId,
            distanceSquared,
        )
        residual = math.sqrt(max(0.0, float(distanceSquared)))
        if residual > maximumResidual:
            raise ValueError(
                _(
                    "%1 is %2 mm from its intended current surface; clear "
                    "the landmarks and repeat guided placement."
                )
                .replace("%1", logic.DRAFT_JAW_LANDMARK_LABELS[index])
                .replace("%2", f"{residual:.3f}")
            )
        projected = tuple(float(value) for value in closest)
        proposedPoints.append(projected)
        proposedEvidence.append(
            {
                "landmarkIndex": index,
                "label": logic.DRAFT_JAW_LANDMARK_LABELS[index],
                "sourceSegmentId": segmentId,
                "sourceGeometryFingerprint": logic._step6CaseJawGeometryFingerprint(
                    segmentation,
                    (segmentId,),
                ),
                "placementMethod": (
                    "ExplicitExistingPointReviewThenExactSourceProjection"
                ),
                "projectionResidualMm": residual,
                "pointWorldRasMm": list(projected),
                "mprReviewState": "Pending",
            }
        )

    validate_patient_ras_condylar_landmarks(
        np.asarray(proposedPoints[0], dtype=float),
        np.asarray(proposedPoints[1], dtype=float),
    )
    originalEvidence = landmarksNode.GetAttribute("DENTOBOT.SurfaceEvidenceJson")
    wasModifying = landmarksNode.StartModify()
    try:
        for index, projected in enumerate(proposedPoints):
            landmarksNode.SetNthControlPointPositionWorld(
                index,
                vtk.vtkVector3d(*projected),
            )
        landmarksNode.SetAttribute(
            "DENTOBOT.SurfaceEvidenceJson",
            canonical_json(proposedEvidence),
        )
        landmarksNode.SetAttribute("DENTOBOT.PendingLandmarkIndex", None)
        landmarksNode.SetAttribute("DENTOBOT.PendingSourceSegmentID", None)
    finally:
        landmarksNode.EndModify(wasModifying)
    try:
        anatomyReview = logic.validateStep6CaseJawLandmarkAnatomy(parameterNode)
    except ValueError:
        wasModifying = landmarksNode.StartModify()
        try:
            for index, original in enumerate(originalPoints):
                landmarksNode.SetNthControlPointPositionWorld(
                    index,
                    vtk.vtkVector3d(*original),
                )
            landmarksNode.SetAttribute(
                "DENTOBOT.SurfaceEvidenceJson",
                originalEvidence,
            )
        finally:
            landmarksNode.EndModify(wasModifying)
        raise
    return {
        "evidence": proposedEvidence,
        "anatomyReview": anatomyReview,
        "maximumResidualMm": max(
            float(item["projectionResidualMm"])
            for item in proposedEvidence
        ),
    }
