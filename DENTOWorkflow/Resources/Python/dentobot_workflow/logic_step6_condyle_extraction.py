"""Mandible-surface condyle centre estimation for Case Foundation."""

from __future__ import annotations

from .runtime import *

from dentobot_workflow.virtual_open_mouth_articulator import (
    DentalFrame,
    dental_frame_from_landmarks,
)


def _polydata_points_world_ras(polydata: vtk.vtkPolyData) -> np.ndarray:
    if polydata is None or polydata.GetNumberOfPoints() <= 0:
        return np.empty((0, 3), dtype=float)
    points = polydata.GetPoints()
    if points is None:
        return np.empty((0, 3), dtype=float)
    count = int(polydata.GetNumberOfPoints())
    array = np.zeros((count, 3), dtype=float)
    for index in range(count):
        points.GetPoint(index, array[index, 0], array[index, 1], array[index, 2])
    return array


def estimate_condyle_centres_from_mandible_points(
    points_world_ras_mm: np.ndarray,
    frame: DentalFrame,
    *,
    min_points_per_side: int = 12,
) -> tuple[np.ndarray, np.ndarray, float]:
    points = np.asarray(points_world_ras_mm, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] == 0:
        raise ValueError("Mandible surface points are missing.")
    relative = points - frame.origin_mm.reshape(1, 3)
    lateral = relative @ frame.x_hat
    anterior = relative @ frame.y_hat
    superior = relative @ frame.z_hat
    posterior_cut = np.quantile(anterior, 0.35)
    superior_cut = np.quantile(superior, 0.55)
    left_mask = (lateral < 0.0) & (anterior <= posterior_cut) & (superior >= superior_cut)
    right_mask = (lateral > 0.0) & (anterior <= posterior_cut) & (superior >= superior_cut)
    left_points = points[left_mask]
    right_points = points[right_mask]
    if left_points.shape[0] < min_points_per_side or right_points.shape[0] < min_points_per_side:
        raise ValueError("Insufficient mandible surface coverage for condylar ROI extraction.")
    left = np.median(left_points, axis=0)
    right = np.median(right_points, axis=0)
    coverage = min(left_points.shape[0], right_points.shape[0])
    confidence = float(min(0.95, 0.55 + coverage / 400.0))
    return left, right, confidence


class Step6CondyleExtractionMixin:

    def step6LateralArchReferencePoints(
        self,
        parameterNode,
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        segmentation = parameterNode.teethSegmentation
        if segmentation is None:
            return None, None
        records = self.getSegmentationReviewRecords(segmentation)
        preferred_pairs = ((36, 46), (34, 44), (31, 41))
        teeth_by_fdi: dict[int, str] = {}
        for record in records:
            if str(record.get("category") or "") != "Teeth":
                continue
            try:
                fdi = int(record.get("fdiNumber"))
            except (TypeError, ValueError):
                continue
            segment_id = str(record.get("segmentId") or "")
            if segment_id:
                teeth_by_fdi[fdi] = segment_id
        for left_fdi, right_fdi in preferred_pairs:
            left_id = teeth_by_fdi.get(left_fdi)
            right_id = teeth_by_fdi.get(right_fdi)
            if not left_id or not right_id:
                continue
            left_surface = self._segmentationSegmentsSurfaceWorld(segmentation, {left_id})
            right_surface = self._segmentationSegmentsSurfaceWorld(segmentation, {right_id})
            if left_surface is None or right_surface is None:
                continue
            left_points = _polydata_points_world_ras(left_surface)
            right_points = _polydata_points_world_ras(right_surface)
            if left_points.shape[0] == 0 or right_points.shape[0] == 0:
                continue
            return np.mean(left_points, axis=0), np.mean(right_points, axis=0)
        return None, None

    def step6EstimatePatientCondyleCentres(
        self,
        parameterNode,
        manual_left_mm: np.ndarray,
        manual_right_mm: np.ndarray,
        lower_incisor_mm: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, float]:
        segmentation = parameterNode.teethSegmentation
        if segmentation is None:
            raise ValueError(_("The authoritative dental segmentation is missing."))
        jaw_groups = self.step6CaseJawSegmentIds(segmentation)
        lower_ids = set(jaw_groups["lower"])
        if not lower_ids:
            raise ValueError(_("No mandibular surfaces are available for condyle extraction."))
        surface = self._segmentationSegmentsSurfaceWorld(segmentation, lower_ids)
        if surface is None or surface.GetNumberOfPoints() == 0:
            raise ValueError(_("Could not build the lower-jaw closed surface."))
        frame = dental_frame_from_landmarks(
            manual_left_mm,
            manual_right_mm,
            lower_incisor_mm,
        )
        return estimate_condyle_centres_from_mandible_points(
            _polydata_points_world_ras(surface),
            frame,
        )
