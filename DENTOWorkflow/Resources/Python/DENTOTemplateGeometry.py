"""Model-independent research template geometry for DENTO Workflow.

The routines in this file operate on VTK/MRML geometry only.  They do not run
trained models and they do not encode clinical or manufacturing approval.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import slicer
import vtk
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy


MAX_SAMPLE_POINTS = 12_000_000


def _finite_vector(values, expected_length: int, name: str) -> np.ndarray:
    vector = np.asarray(values, dtype=float)
    if vector.shape != (expected_length,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must contain {expected_length} finite values.")
    return vector


def _triangulated_clean_surface(poly_data: vtk.vtkPolyData) -> vtk.vtkPolyData:
    if not poly_data or not poly_data.GetNumberOfPoints():
        raise ValueError("Input anatomy contains no surface points.")

    triangle_filter = vtk.vtkTriangleFilter()
    triangle_filter.SetInputData(poly_data)
    triangle_filter.PassLinesOff()
    triangle_filter.PassVertsOff()

    clean_filter = vtk.vtkCleanPolyData()
    clean_filter.SetInputConnection(triangle_filter.GetOutputPort())

    normals_filter = vtk.vtkPolyDataNormals()
    normals_filter.SetInputConnection(clean_filter.GetOutputPort())
    normals_filter.ConsistencyOn()
    normals_filter.AutoOrientNormalsOn()
    normals_filter.SplittingOff()
    normals_filter.ComputePointNormalsOn()
    normals_filter.ComputeCellNormalsOff()
    normals_filter.Update()

    output = vtk.vtkPolyData()
    output.DeepCopy(normals_filter.GetOutput())
    if not output.GetNumberOfCells():
        raise ValueError("Input anatomy contains no usable surface cells.")
    return output


def model_polydata_in_world(model_node) -> vtk.vtkPolyData:
    """Return a deep world-RAS copy without modifying the source MRML model."""

    if not model_node or not model_node.IsA("vtkMRMLModelNode"):
        raise ValueError("Select a valid Step 5A support-anatomy model.")
    source = model_node.GetPolyData()
    if not source or not source.GetNumberOfPoints() or not source.GetNumberOfCells():
        raise ValueError("The Step 5A support-anatomy model has no usable geometry.")

    source_copy = vtk.vtkPolyData()
    source_copy.DeepCopy(source)
    parent_transform = model_node.GetParentTransformNode()
    if not parent_transform:
        return _triangulated_clean_surface(source_copy)

    world_transform = vtk.vtkGeneralTransform()
    slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(
        parent_transform,
        None,
        world_transform,
    )
    transform_filter = vtk.vtkTransformPolyDataFilter()
    transform_filter.SetInputData(source_copy)
    transform_filter.SetTransform(world_transform)
    transform_filter.Update()
    return _triangulated_clean_surface(transform_filter.GetOutput())


def surface_topology(poly_data: vtk.vtkPolyData) -> dict[str, int]:
    """Return compact mesh topology metrics used as research validity checks."""

    triangle_filter = vtk.vtkTriangleFilter()
    triangle_filter.SetInputData(poly_data)
    triangle_filter.Update()

    feature_edges = vtk.vtkFeatureEdges()
    feature_edges.SetInputConnection(triangle_filter.GetOutputPort())
    feature_edges.BoundaryEdgesOn()
    feature_edges.NonManifoldEdgesOn()
    feature_edges.FeatureEdgesOff()
    feature_edges.ManifoldEdgesOff()
    feature_edges.Update()

    connectivity = vtk.vtkPolyDataConnectivityFilter()
    connectivity.SetInputConnection(triangle_filter.GetOutputPort())
    connectivity.SetExtractionModeToAllRegions()
    connectivity.ColorRegionsOn()
    connectivity.Update()

    return {
        "pointCount": int(triangle_filter.GetOutput().GetNumberOfPoints()),
        "triangleCount": int(triangle_filter.GetOutput().GetNumberOfCells()),
        "boundaryOrNonManifoldEdgeCount": int(
            feature_edges.GetOutput().GetNumberOfCells()
        ),
        "surfaceRegionCount": int(connectivity.GetNumberOfExtractedRegions()),
    }


def _resample_closed_loop_points(
    loop_points_ras,
    spacing_mm: float,
) -> np.ndarray:
    """Return uniformly sampled points around one finite closed world-RAS loop."""

    spacing = float(spacing_mm)
    if not math.isfinite(spacing) or spacing <= 0.0:
        raise ValueError("Support-boundary sampling spacing must be greater than zero.")
    if isinstance(loop_points_ras, vtk.vtkPoints):
        if not loop_points_ras.GetData():
            raise ValueError("The support boundary contains no usable points.")
        points = np.asarray(vtk_to_numpy(loop_points_ras.GetData()), dtype=float)
    else:
        points = np.asarray(loop_points_ras, dtype=float)
    if points.ndim != 2 or points.shape[1:] != (3,) or points.shape[0] < 3:
        raise ValueError("The support boundary requires at least three world-RAS points.")
    if not np.all(np.isfinite(points)):
        raise ValueError("The support boundary must contain only finite world-RAS points.")

    filtered = [points[0]]
    for point in points[1:]:
        if float(np.linalg.norm(point - filtered[-1])) > 1e-6:
            filtered.append(point)
    if len(filtered) >= 2 and float(np.linalg.norm(filtered[-1] - filtered[0])) <= 1e-6:
        filtered.pop()
    if len(filtered) < 3:
        raise ValueError("The support boundary requires three distinct points.")

    points = np.asarray(filtered, dtype=float)
    closed_points = np.vstack((points, points[0]))
    segment_vectors = np.diff(closed_points, axis=0)
    segment_lengths = np.linalg.norm(segment_vectors, axis=1)
    if np.count_nonzero(segment_lengths > 1e-6) < 3:
        raise ValueError("The support boundary has insufficient non-zero edges.")
    perimeter = float(np.sum(segment_lengths))
    if not math.isfinite(perimeter) or perimeter <= 1e-6:
        raise ValueError("The support boundary has zero perimeter.")

    sample_count = max(3, int(math.ceil(perimeter / spacing)))
    sample_distances = np.linspace(0.0, perimeter, sample_count, endpoint=False)
    cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths)))
    resampled = np.empty((sample_count, 3), dtype=float)
    for sample_index, distance in enumerate(sample_distances):
        segment_index = int(np.searchsorted(cumulative, distance, side="right") - 1)
        segment_index = min(segment_index, len(segment_lengths) - 1)
        segment_length = float(segment_lengths[segment_index])
        fraction = (
            (distance - cumulative[segment_index]) / segment_length
            if segment_length > 1e-12
            else 0.0
        )
        resampled[sample_index] = (
            closed_points[segment_index]
            + fraction * segment_vectors[segment_index]
        )
    return resampled


def _connected_surface_regions(
    surface: vtk.vtkPolyData,
) -> list[vtk.vtkPolyData]:
    """Return deep-cleaned connected components without changing world RAS."""

    connectivity = vtk.vtkPolyDataConnectivityFilter()
    connectivity.SetInputData(surface)
    connectivity.SetExtractionModeToAllRegions()
    connectivity.Update()
    region_count = int(connectivity.GetNumberOfExtractedRegions())
    regions = []
    for region_index in range(region_count):
        extractor = vtk.vtkPolyDataConnectivityFilter()
        extractor.SetInputData(surface)
        extractor.SetExtractionModeToSpecifiedRegions()
        extractor.AddSpecifiedRegion(region_index)
        extractor.Update()
        regions.append(_triangulated_clean_surface(extractor.GetOutput()))
    return regions


def _orient_patch_outward(
    patch: vtk.vtkPolyData,
    closed_anatomy: vtk.vtkPolyData,
) -> tuple[vtk.vtkPolyData, float]:
    """Orient an open support patch away from its source closed anatomy."""

    prepared_patch = _triangulated_clean_surface(patch)
    normals = prepared_patch.GetPointData().GetNormals()
    if not normals or normals.GetNumberOfTuples() != prepared_patch.GetNumberOfPoints():
        raise ValueError("The selected support patch has no usable surface normals.")
    bounds = prepared_patch.GetBounds()
    diagonal = math.sqrt(
        sum(
            (bounds[2 * axis + 1] - bounds[2 * axis]) ** 2
            for axis in range(3)
        )
    )
    epsilon = max(1e-3, diagonal * 1e-4)
    implicit_distance = vtk.vtkImplicitPolyDataDistance()
    implicit_distance.SetInput(closed_anatomy)
    sample_count = min(128, prepared_patch.GetNumberOfPoints())
    sample_indices = np.linspace(
        0,
        prepared_patch.GetNumberOfPoints() - 1,
        sample_count,
        dtype=int,
    )
    scores = []
    for point_index in sample_indices:
        point = np.asarray(prepared_patch.GetPoint(int(point_index)), dtype=float)
        normal = np.asarray(normals.GetTuple(int(point_index)), dtype=float)
        normal_length = float(np.linalg.norm(normal))
        if normal_length <= 1e-12:
            continue
        normal /= normal_length
        scores.append(
            float(
                implicit_distance.EvaluateFunction(point + epsilon * normal)
                - implicit_distance.EvaluateFunction(point - epsilon * normal)
            )
        )
    if not scores:
        raise ValueError("The selected support patch normals could not be validated.")
    orientation_score = float(np.median(scores))
    if abs(orientation_score) <= epsilon * 1e-3:
        raise ValueError("The selected support patch normal direction is ambiguous.")
    if orientation_score < 0.0:
        reverse = vtk.vtkReverseSense()
        reverse.SetInputData(prepared_patch)
        reverse.ReverseCellsOn()
        reverse.ReverseNormalsOn()
        reverse.Update()
        outward_patch = vtk.vtkPolyData()
        outward_patch.DeepCopy(reverse.GetOutput())
        orientation_score = -orientation_score
    else:
        outward_patch = prepared_patch
    return outward_patch, orientation_score


def _extract_connected_support_patch(
    anatomy: vtk.vtkPolyData,
    loop_points: np.ndarray,
    selection_mode: str,
) -> tuple[vtk.vtkPolyData, dict]:
    """Apply the SlicerFSP-style Dijkstra clip to one connected surface."""

    vtk_loop_points = vtk.vtkPoints()
    for point in loop_points:
        vtk_loop_points.InsertNextPoint(*point)

    selector = vtk.vtkSelectPolyData()
    selector.SetInputData(anatomy)
    selector.SetLoop(vtk_loop_points)
    selector.SetEdgeSearchModeToDijkstra()
    selector.GenerateSelectionScalarsOn()
    if selection_mode == "Smallest":
        selector.SetSelectionModeToSmallestRegion()
    else:
        selector.SetSelectionModeToLargestRegion()
    selector.Update()

    selected_surface = selector.GetOutput()
    selection_scalars = (
        selected_surface.GetPointData().GetArray("Selection")
        if selected_surface
        else None
    )
    selection_edges = selector.GetSelectionEdges()
    if (
        not selected_surface
        or not selection_scalars
        or not selection_edges
        or selection_edges.GetNumberOfPoints() < 3
    ):
        raise ValueError(
            "The closed boundary could not be mapped onto a connected support "
            "surface. Keep the curve close to each selected tooth and avoid "
            "crossing itself."
        )
    scalar_range = selection_scalars.GetRange()
    if scalar_range[0] > 1e-6 or scalar_range[1] < -1e-6:
        raise ValueError(
            "The support boundary did not divide a connected source surface "
            "into two regions."
        )

    clip = vtk.vtkClipPolyData()
    clip.SetInputConnection(selector.GetOutputPort())
    clip.SetValue(0.0)
    clip.InsideOutOn()  # vtkSelectPolyData marks the selected region negative.
    clip.GenerateClippedOutputOff()
    clip.Update()
    patch = _triangulated_clean_surface(clip.GetOutput())
    if (
        patch.GetNumberOfPoints() < 3
        or patch.GetNumberOfCells() < 1
        or patch.GetNumberOfCells() >= anatomy.GetNumberOfCells()
    ):
        raise ValueError(
            "The support boundary produced an empty or unbounded surface selection."
        )
    patch, outward_orientation_score = _orient_patch_outward(patch, anatomy)
    return patch, {
        "assignedLoopPointCount": int(loop_points.shape[0]),
        "selectionBoundaryPointCount": int(selection_edges.GetNumberOfPoints()),
        "selectionBoundaryPolylineCount": int(selection_edges.GetNumberOfCells()),
        "sourcePointCount": int(anatomy.GetNumberOfPoints()),
        "sourceTriangleCount": int(anatomy.GetNumberOfCells()),
        "outwardNormalScore": outward_orientation_score,
        **surface_topology(patch),
    }


def _surface_direction_score_mm(
    surface: vtk.vtkPolyData,
    origin_ras: np.ndarray,
    direction_ras: np.ndarray,
) -> tuple[float, float]:
    """Return area-weighted axial centroid offset and triangle area."""

    prepared = _triangulated_clean_surface(surface)
    points = np.asarray(vtk_to_numpy(prepared.GetPoints().GetData()), dtype=float)
    polygon_data = np.asarray(
        vtk_to_numpy(prepared.GetPolys().GetData()),
        dtype=np.int64,
    )
    if polygon_data.size % 4:
        raise ValueError("The support candidate does not contain only triangles.")
    triangles = polygon_data.reshape((-1, 4))
    if triangles.size == 0 or not np.all(triangles[:, 0] == 3):
        raise ValueError("The support candidate has no usable triangles.")
    vertices = points[triangles[:, 1:4]]
    cross_products = np.cross(
        vertices[:, 1] - vertices[:, 0],
        vertices[:, 2] - vertices[:, 0],
    )
    areas = 0.5 * np.linalg.norm(cross_products, axis=1)
    valid = np.isfinite(areas) & (areas > 1e-12)
    if not np.any(valid):
        raise ValueError("The support candidate has zero usable surface area.")
    centroids = np.mean(vertices[valid], axis=1)
    offsets = np.dot(centroids - origin_ras, direction_ras)
    total_area = float(np.sum(areas[valid]))
    score = float(np.dot(offsets, areas[valid]) / total_area)
    if not math.isfinite(score) or not math.isfinite(total_area):
        raise ValueError("The support candidate direction score is invalid.")
    return score, total_area


def _extract_directional_connected_support_patch(
    anatomy: vtk.vtkPolyData,
    loop_points: np.ndarray,
    crown_direction_ras: np.ndarray,
) -> tuple[vtk.vtkPolyData, dict]:
    """Evaluate both clip sides and retain the crown/removal-direction side."""

    smaller_patch, smaller_metrics = _extract_connected_support_patch(
        anatomy,
        loop_points,
        "Smallest",
    )
    larger_patch, larger_metrics = _extract_connected_support_patch(
        anatomy,
        loop_points,
        "Largest",
    )
    boundary_center = np.mean(loop_points, axis=0)
    smaller_score, smaller_area = _surface_direction_score_mm(
        smaller_patch,
        boundary_center,
        crown_direction_ras,
    )
    larger_score, larger_area = _surface_direction_score_mm(
        larger_patch,
        boundary_center,
        crown_direction_ras,
    )
    use_smaller = smaller_score >= larger_score
    selected_patch = smaller_patch if use_smaller else larger_patch
    selected_metrics = smaller_metrics if use_smaller else larger_metrics
    score_separation = abs(smaller_score - larger_score)
    return selected_patch, {
        **selected_metrics,
        "selectionBasis": "TrajectoryCrownDirection",
        "selectedCandidate": "Smaller" if use_smaller else "Larger",
        "selectedDirectionScoreMm": max(smaller_score, larger_score),
        "otherDirectionScoreMm": min(smaller_score, larger_score),
        "directionScoreSeparationMm": score_separation,
        "directionSelectionAmbiguous": bool(score_separation < 0.25),
        "smallerCandidateAreaMm2": smaller_area,
        "largerCandidateAreaMm2": larger_area,
        "smallerCandidateDirectionScoreMm": smaller_score,
        "largerCandidateDirectionScoreMm": larger_score,
    }


def extract_directional_visible_support_surface(
    tooth_surfaces_world,
    loop_points_ras,
    crown_direction_ras,
    *,
    sampling_spacing_mm: float = 0.5,
) -> tuple[vtk.vtkPolyData, dict]:
    """Extract one trajectory-directed visible patch per addressed tooth.

    ``tooth_surfaces_world`` is a list of dictionaries containing stable
    ``segmentId`` values and world-RAS ``polyData``.  Connected mesh islands
    remain diagnostics inside their source tooth; they are never counted as
    additional teeth.
    """

    if not isinstance(tooth_surfaces_world, (list, tuple)) or not tooth_surfaces_world:
        raise ValueError("At least one source tooth surface is required.")
    crown_direction = _finite_vector(
        crown_direction_ras,
        3,
        "Crown/removal direction",
    )
    direction_length = float(np.linalg.norm(crown_direction))
    if direction_length <= 1e-9:
        raise ValueError("Crown/removal direction must be non-zero.")
    crown_direction /= direction_length
    loop_points = _resample_closed_loop_points(
        loop_points_ras,
        sampling_spacing_mm,
    )

    prepared_teeth = []
    seen_segment_ids = set()
    for tooth_index, item in enumerate(tooth_surfaces_world):
        if not isinstance(item, dict):
            raise ValueError("Every source tooth must include segment metadata.")
        segment_id = str(item.get("segmentId") or "").strip()
        if not segment_id or segment_id in seen_segment_ids:
            raise ValueError("Source tooth segment IDs must be non-empty and unique.")
        seen_segment_ids.add(segment_id)
        surface = _triangulated_clean_surface(item.get("polyData"))
        regions = _connected_surface_regions(surface)
        if not regions:
            raise ValueError(f"Source tooth {segment_id} has no connected surface.")
        locator = vtk.vtkStaticPointLocator()
        locator.SetDataSet(surface)
        locator.BuildLocator()
        prepared_teeth.append(
            {
                "toothIndex": tooth_index,
                "segmentId": segment_id,
                "displayName": str(item.get("displayName") or segment_id),
                "surface": surface,
                "regions": regions,
                "locator": locator,
            }
        )

    tooth_distances = np.empty(
        (loop_points.shape[0], len(prepared_teeth)),
        dtype=float,
    )
    for tooth_index, tooth in enumerate(prepared_teeth):
        for point_index, point in enumerate(loop_points):
            nearest_id = tooth["locator"].FindClosestPoint(point)
            nearest = np.asarray(
                tooth["surface"].GetPoint(nearest_id),
                dtype=float,
            )
            tooth_distances[point_index, tooth_index] = float(
                np.dot(point - nearest, point - nearest)
            )
    tooth_assignments = np.argmin(tooth_distances, axis=1)

    append = vtk.vtkAppendPolyData()
    tooth_metrics = []
    omitted_tooth_metrics = []
    raw_island_count = 0
    ignored_island_count = 0
    for tooth_index, tooth in enumerate(prepared_teeth):
        regions = tooth["regions"]
        raw_island_count += len(regions)
        assigned_points = loop_points[tooth_assignments == tooth_index]
        if assigned_points.shape[0] < 3:
            omitted_tooth_metrics.append(
                {
                    "segmentId": tooth["segmentId"],
                    "displayName": tooth["displayName"],
                    "assignedLoopPointCount": int(assigned_points.shape[0]),
                    "sourceIslandCount": len(regions),
                    "reason": "The boundary did not address this tooth.",
                }
            )
            continue

        region_distances = np.empty(
            (assigned_points.shape[0], len(regions)),
            dtype=float,
        )
        for region_index, region in enumerate(regions):
            locator = vtk.vtkStaticPointLocator()
            locator.SetDataSet(region)
            locator.BuildLocator()
            for point_index, point in enumerate(assigned_points):
                nearest_id = locator.FindClosestPoint(point)
                nearest = np.asarray(region.GetPoint(nearest_id), dtype=float)
                region_distances[point_index, region_index] = float(
                    np.dot(point - nearest, point - nearest)
                )
        region_assignments = np.argmin(region_distances, axis=1)
        region_counts = np.bincount(
            region_assignments,
            minlength=len(regions),
        )
        selected_region_index = int(np.argmax(region_counts))
        selected_region_points = assigned_points[
            region_assignments == selected_region_index
        ]
        ignored_island_count += max(0, len(regions) - 1)
        if selected_region_points.shape[0] < 3:
            omitted_tooth_metrics.append(
                {
                    "segmentId": tooth["segmentId"],
                    "displayName": tooth["displayName"],
                    "assignedLoopPointCount": int(assigned_points.shape[0]),
                    "sourceIslandCount": len(regions),
                    "reason": (
                        "The boundary points were split across disconnected "
                        "islands inside this tooth segment."
                    ),
                }
            )
            continue
        local_loop = _resample_closed_loop_points(
            selected_region_points,
            sampling_spacing_mm,
        )
        try:
            tooth_patch, metrics = _extract_directional_connected_support_patch(
                regions[selected_region_index],
                local_loop,
                crown_direction,
            )
        except ValueError as exc:
            omitted_tooth_metrics.append(
                {
                    "segmentId": tooth["segmentId"],
                    "displayName": tooth["displayName"],
                    "assignedLoopPointCount": int(assigned_points.shape[0]),
                    "sourceIslandCount": len(regions),
                    "reason": str(exc),
                }
            )
            continue
        append.AddInputData(tooth_patch)
        tooth_metrics.append(
            {
                **metrics,
                "segmentId": tooth["segmentId"],
                "displayName": tooth["displayName"],
                "sourceIslandCount": len(regions),
                "selectedIslandIndex": selected_region_index,
                "ignoredIslandCount": max(0, len(regions) - 1),
            }
        )

    if not tooth_metrics:
        details = "; ".join(
            f"{item['displayName']}: {item['reason']}"
            for item in omitted_tooth_metrics[:3]
        )
        raise ValueError(
            "No visible-support tooth patch could be extracted. Place one "
            "closed loop directly on the intended tooth surfaces near the "
            "gingival/cervical margin and avoid self-crossings."
            + (f" Details: {details}" if details else "")
        )
    append.Update()
    patch = _triangulated_clean_surface(append.GetOutput())
    topology = surface_topology(patch)
    return patch, {
        **topology,
        "method": "PerToothTrajectoryDirectionalDijkstra",
        "selectionBasis": "TrajectoryEntryToTargetCrownOpposite",
        "samplingSpacingMm": float(sampling_spacing_mm),
        "loopPointCount": int(loop_points.shape[0]),
        "crownDirectionRas": [float(value) for value in crown_direction],
        "sourceToothCount": len(prepared_teeth),
        "selectedToothCount": len(tooth_metrics),
        "omittedToothCount": len(omitted_tooth_metrics),
        "sourceSurfaceRegionCount": raw_island_count,
        "ignoredSourceIslandCount": ignored_island_count,
        "toothMetrics": tooth_metrics,
        "omittedToothMetrics": omitted_tooth_metrics,
        "boundsRas": tuple(float(value) for value in patch.GetBounds()),
    }


def extract_visible_support_surface(
    anatomy_world: vtk.vtkPolyData,
    loop_points_ras,
    *,
    sampling_spacing_mm: float = 0.5,
    selection_mode: str = "Smallest",
) -> tuple[vtk.vtkPolyData, dict]:
    """Extract the surface patch enclosed by a clinician-defined closed loop.

    This is the DENTOBOT adaptation of SlicerFSP ``CurveAndClip``.  Dijkstra
    edge search maps the world-RAS loop onto the input mesh, signed selection
    scalars split cells at the boundary, and the selected side remains an open
    surface patch for later fit/undercut/shell processing.
    """

    if selection_mode not in {"Smallest", "Largest"}:
        raise ValueError("Support-surface selection mode must be Smallest or Largest.")
    anatomy = _triangulated_clean_surface(anatomy_world)
    loop_points = _resample_closed_loop_points(
        loop_points_ras,
        sampling_spacing_mm,
    )
    source_topology = surface_topology(anatomy)
    regions = _connected_surface_regions(anatomy)
    if not regions:
        raise ValueError("The support anatomy has no connected surface regions.")

    if len(regions) == 1:
        patch, component_metrics = _extract_connected_support_patch(
            regions[0],
            loop_points,
            selection_mode,
        )
        component_metrics["sourceRegionIndex"] = 0
        per_region_metrics = [component_metrics]
        omitted_region_metrics = []
        mapping_method = "vtkSelectPolyDataDijkstra"
    else:
        # Unlike the connected optical-scan surface used by SlicerFSP, the
        # authoritative DENTOBOT anatomy contains one closed surface per tooth.
        # Assign the resampled global margin to its nearest tooth, then perform
        # the same geodesic Dijkstra clip independently on every tooth.  This
        # preserves separated anatomy and avoids inventing mesh bridges.
        distances = np.empty((loop_points.shape[0], len(regions)), dtype=float)
        for region_index, region in enumerate(regions):
            locator = vtk.vtkStaticPointLocator()
            locator.SetDataSet(region)
            locator.BuildLocator()
            for point_index, point in enumerate(loop_points):
                nearest_id = locator.FindClosestPoint(point)
                nearest = np.asarray(region.GetPoint(nearest_id), dtype=float)
                distances[point_index, region_index] = float(
                    np.dot(point - nearest, point - nearest)
                )
        assignments = np.argmin(distances, axis=1)
        append = vtk.vtkAppendPolyData()
        per_region_metrics = []
        omitted_region_metrics = []
        for region_index, region in enumerate(regions):
            assigned_points = loop_points[assignments == region_index]
            if assigned_points.shape[0] < 3:
                omitted_region_metrics.append(
                    {
                        "sourceRegionIndex": int(region_index),
                        "assignedLoopPointCount": int(assigned_points.shape[0]),
                        "reason": (
                            "The boundary did not provide three points for this "
                            "disconnected tooth surface."
                        ),
                    }
                )
                continue
            local_loop = _resample_closed_loop_points(
                assigned_points,
                sampling_spacing_mm,
            )
            try:
                region_patch, region_metrics = _extract_connected_support_patch(
                    region,
                    local_loop,
                    selection_mode,
                )
            except ValueError as exc:
                omitted_region_metrics.append(
                    {
                        "sourceRegionIndex": int(region_index),
                        "assignedLoopPointCount": int(assigned_points.shape[0]),
                        "reason": str(exc),
                    }
                )
                continue
            region_metrics["sourceRegionIndex"] = int(region_index)
            append.AddInputData(region_patch)
            per_region_metrics.append(region_metrics)
        if not per_region_metrics:
            failure_details = "; ".join(
                (
                    f"tooth surface {item['sourceRegionIndex'] + 1}: "
                    f"{item['reason']}"
                )
                for item in omitted_region_metrics[:3]
            )
            raise ValueError(
                "No visible-support patch could be extracted. Place one closed "
                "loop directly on the orange draft support surfaces near the "
                "intended gingival/cervical margin, right-click to finish the "
                "loop, and avoid self-crossings."
                + (f" Details: {failure_details}" if failure_details else "")
            )
        append.Update()
        patch = _triangulated_clean_surface(append.GetOutput())
        mapping_method = "PerConnectedSurfaceDijkstra"

    patch_topology = surface_topology(patch)
    if patch_topology["surfaceRegionCount"] != len(per_region_metrics):
        raise ValueError(
            "Visible-support extraction did not preserve one selected patch per "
            "addressed connected tooth surface."
        )
    bounds = tuple(float(value) for value in patch.GetBounds())
    return patch, {
        **patch_topology,
        "method": mapping_method,
        "selectionMode": selection_mode,
        "samplingSpacingMm": float(sampling_spacing_mm),
        "loopPointCount": int(loop_points.shape[0]),
        "sourcePointCount": int(anatomy.GetNumberOfPoints()),
        "sourceTriangleCount": int(anatomy.GetNumberOfCells()),
        "sourceSurfaceRegionCount": source_topology["surfaceRegionCount"],
        "selectedSurfaceRegionCount": len(per_region_metrics),
        "omittedSurfaceRegionCount": len(omitted_region_metrics),
        "componentMetrics": per_region_metrics,
        "omittedRegionMetrics": omitted_region_metrics,
        "boundsRas": bounds,
    }


def create_support_boundary_bridge(
    loop_points_ras,
    removal_direction_ras,
    *,
    fit_clearance_mm: float,
    shell_thickness_mm: float,
    sampling_spacing_mm: float,
) -> tuple[vtk.vtkPolyData, dict]:
    """Create a lifted closed collar that bridges separated tooth-shell rims.

    The clinician's continuous support boundary remains the authority.  This
    collar follows that boundary on the removal side of the fitting surfaces;
    it provides structural continuity across interdental gaps without adding
    a new patient-contact patch in those gaps.  The later blockout subtraction
    enforces the requested anatomy clearance on the complete union.
    """

    clearance = float(fit_clearance_mm)
    thickness = float(shell_thickness_mm)
    spacing = float(sampling_spacing_mm)
    if not math.isfinite(clearance) or clearance < 0.0:
        raise ValueError("Boundary-bridge clearance must be zero or greater.")
    if not math.isfinite(thickness) or thickness <= 0.0:
        raise ValueError("Boundary-bridge thickness must be positive.")
    if not math.isfinite(spacing) or not 0.1 <= spacing <= 2.0:
        raise ValueError(
            "Boundary-bridge processing resolution must be between 0.10 and 2.00 mm."
        )
    removal = _finite_vector(
        removal_direction_ras,
        3,
        "Boundary-bridge removal direction",
    )
    removal_length = float(np.linalg.norm(removal))
    if removal_length <= 1e-9:
        raise ValueError("Boundary-bridge removal direction must be non-zero.")
    removal /= removal_length
    loop_points = _resample_closed_loop_points(
        loop_points_ras,
        min(spacing, max(0.1, thickness * 0.35)),
    )

    tube_radius = max(0.65 * thickness, 1.25 * spacing)
    center_offset = clearance + 0.5 * thickness
    bridge_points = loop_points + center_offset * removal[np.newaxis, :]
    padding = tube_radius + 2.0 * spacing
    bounds = tuple(
        value
        for axis in range(3)
        for value in (
            float(np.min(bridge_points[:, axis]) - padding),
            float(np.max(bridge_points[:, axis]) + padding),
        )
    )
    dimensions = tuple(
        max(
            3,
            int(math.ceil((bounds[2 * axis + 1] - bounds[2 * axis]) / spacing))
            + 1,
        )
        for axis in range(3)
    )
    sample_point_count = int(np.prod(dimensions, dtype=np.int64))
    if sample_point_count > MAX_SAMPLE_POINTS:
        raise ValueError(
            "The support-boundary bridge domain and resolution request "
            f"{sample_point_count:,} samples; increase processing resolution."
        )
    actual_spacing = tuple(
        (bounds[2 * axis + 1] - bounds[2 * axis]) / (dimensions[axis] - 1)
        for axis in range(3)
    )
    coordinates = tuple(
        bounds[2 * axis]
        + np.arange(dimensions[axis], dtype=float) * actual_spacing[axis]
        for axis in range(3)
    )
    bridge_mask = np.zeros(
        (dimensions[2], dimensions[1], dimensions[0]),
        dtype=bool,
    )
    closed_bridge_points = np.vstack((bridge_points, bridge_points[0]))
    radius_squared = tube_radius * tube_radius
    for segment_index in range(bridge_points.shape[0]):
        point0 = closed_bridge_points[segment_index]
        point1 = closed_bridge_points[segment_index + 1]
        vector = point1 - point0
        length_squared = float(np.dot(vector, vector))
        if length_squared <= 1e-12:
            continue
        index_bounds = []
        for axis in range(3):
            lower = max(
                0,
                int(
                    math.floor(
                        (
                            min(point0[axis], point1[axis])
                            - tube_radius
                            - bounds[2 * axis]
                        )
                        / actual_spacing[axis]
                    )
                ),
            )
            upper = min(
                dimensions[axis] - 1,
                int(
                    math.ceil(
                        (
                            max(point0[axis], point1[axis])
                            + tube_radius
                            - bounds[2 * axis]
                        )
                        / actual_spacing[axis]
                    )
                ),
            )
            index_bounds.append((lower, upper))
        x_values = coordinates[0][
            index_bounds[0][0] : index_bounds[0][1] + 1
        ]
        y_values = coordinates[1][
            index_bounds[1][0] : index_bounds[1][1] + 1
        ]
        z_values = coordinates[2][
            index_bounds[2][0] : index_bounds[2][1] + 1
        ]
        dx = x_values[np.newaxis, np.newaxis, :] - point0[0]
        dy = y_values[np.newaxis, :, np.newaxis] - point0[1]
        dz = z_values[:, np.newaxis, np.newaxis] - point0[2]
        projection = np.clip(
            (dx * vector[0] + dy * vector[1] + dz * vector[2])
            / length_squared,
            0.0,
            1.0,
        )
        distance_squared = (
            (dx - projection * vector[0]) ** 2
            + (dy - projection * vector[1]) ** 2
            + (dz - projection * vector[2]) ** 2
        )
        bridge_mask[
            index_bounds[2][0] : index_bounds[2][1] + 1,
            index_bounds[1][0] : index_bounds[1][1] + 1,
            index_bounds[0][0] : index_bounds[0][1] + 1,
        ] |= distance_squared <= radius_squared
    bridge_mask[0, :, :] = False
    bridge_mask[-1, :, :] = False
    bridge_mask[:, 0, :] = False
    bridge_mask[:, -1, :] = False
    bridge_mask[:, :, 0] = False
    bridge_mask[:, :, -1] = False
    occupied_sample_count = int(np.count_nonzero(bridge_mask))
    if not occupied_sample_count:
        raise ValueError("The selected support boundary produced no bridge volume.")

    bridge_image = vtk.vtkImageData()
    bridge_image.SetDimensions(*dimensions)
    bridge_image.SetOrigin(bounds[0], bounds[2], bounds[4])
    bridge_image.SetSpacing(*actual_spacing)
    bridge_scalars = numpy_to_vtk(
        np.ascontiguousarray(bridge_mask.astype(np.uint8).ravel()),
        deep=True,
        array_type=vtk.VTK_UNSIGNED_CHAR,
    )
    bridge_scalars.SetName("DENTOBOT.TemplateSupportBoundaryBridgeMask")
    bridge_image.GetPointData().SetScalars(bridge_scalars)
    contour = vtk.vtkFlyingEdges3D()
    contour.SetInputData(bridge_image)
    contour.SetValue(0, 0.5)
    contour.ComputeNormalsOff()
    contour.ComputeGradientsOff()
    contour.Update()
    bridge = _triangulated_clean_surface(contour.GetOutput())
    topology = surface_topology(bridge)
    if topology["boundaryOrNonManifoldEdgeCount"]:
        raise ValueError(
            "The selected support boundary produced an invalid structural "
            f"bridge ({topology['boundaryOrNonManifoldEdgeCount']} invalid edges). "
            "Redraw the loop without self-crossings."
        )
    if topology["surfaceRegionCount"] != 1:
        raise ValueError("The selected support boundary did not produce one bridge.")
    return bridge, {
        **topology,
        "method": "LiftedClosedBoundaryCollar",
        "fitClearanceMm": clearance,
        "shellThicknessMm": thickness,
        "tubeRadiusMm": tube_radius,
        "centerOffsetMm": center_offset,
        "samplingSpacingMm": spacing,
        "actualSpacingMm": actual_spacing,
        "sampleDimensions": dimensions,
        "samplePointCount": sample_point_count,
        "occupiedSampleCount": occupied_sample_count,
        "resampledBoundaryPointCount": int(bridge_points.shape[0]),
        "removalDirectionRas": tuple(float(value) for value in removal),
        "boundsRas": tuple(float(value) for value in bridge.GetBounds()),
    }


def regularize_patient_contact_shell(
    hollow_candidate_world: vtk.vtkPolyData,
    anatomy_world: vtk.vtkPolyData,
    *,
    fit_clearance_mm: float,
    sampling_spacing_mm: float,
    voxel_closing_mm: float = 0.0,
    fitting_surface_world: vtk.vtkPolyData | None = None,
    shell_thickness_mm: float | None = None,
    boundary_bridge_world: vtk.vtkPolyData | None = None,
) -> tuple[vtk.vtkPolyData, dict]:
    """Voxel-union a Hollow candidate and enforce anatomy fit clearance.

    Dynamic Modeler Margin + Hollow provides the intended margin and side-wall
    geometry.  This tight-domain binary pass adapts SlicerFSP's robust
    segmentation/labelmap Boolean strategy: overlapping tooth shells are
    unioned, and any residual geometry inside the requested anatomy clearance
    is removed before extracting a watertight printable research surface.
    """

    clearance = float(fit_clearance_mm)
    requested_spacing = float(sampling_spacing_mm)
    closing = float(voxel_closing_mm)
    if not math.isfinite(clearance) or clearance < 0.0:
        raise ValueError("Fit clearance must be finite and zero or greater.")
    if (
        not math.isfinite(requested_spacing)
        or requested_spacing < 0.1
        or requested_spacing > 2.0
    ):
        raise ValueError("Shell processing resolution must be between 0.10 and 2.00 mm.")
    if not math.isfinite(closing) or closing < 0.0 or closing > 5.0:
        raise ValueError("Voxel closing must be between 0.00 and 5.00 mm.")
    candidate = _triangulated_clean_surface(hollow_candidate_world)
    anatomy = _triangulated_clean_surface(anatomy_world)
    candidate_topology = surface_topology(candidate)
    use_fitting_surface_fallback = bool(
        candidate_topology["boundaryOrNonManifoldEdgeCount"]
    )
    fitting_surface = None
    thickness = None
    if use_fitting_surface_fallback:
        if fitting_surface_world is None or shell_thickness_mm is None:
            raise ValueError(
                "Dynamic Modeler Hollow produced an open or non-manifold candidate "
                f"({candidate_topology['boundaryOrNonManifoldEdgeCount']} invalid "
                "edges), and no validated fitting surface was supplied for repair."
            )
        fitting_surface = _triangulated_clean_surface(fitting_surface_world)
        thickness = float(shell_thickness_mm)
        if not math.isfinite(thickness) or thickness <= 0.0:
            raise ValueError(
                "Shell thickness must be positive for fitting-surface repair."
            )

    boundary_bridge = None
    bridge_topology = None
    if boundary_bridge_world is not None:
        boundary_bridge = _triangulated_clean_surface(boundary_bridge_world)
        bridge_topology = surface_topology(boundary_bridge)
        if bridge_topology["boundaryOrNonManifoldEdgeCount"]:
            raise ValueError(
                "The support-boundary bridge is open or non-manifold "
                f"({bridge_topology['boundaryOrNonManifoldEdgeCount']} invalid edges)."
            )

    bounds_sources = [candidate.GetBounds()]
    if fitting_surface is not None:
        bounds_sources.append(fitting_surface.GetBounds())
    if boundary_bridge is not None:
        bounds_sources.append(boundary_bridge.GetBounds())
    bounds = tuple(
        value
        for axis in range(3)
        for value in (
            min(source[2 * axis] for source in bounds_sources),
            max(source[2 * axis + 1] for source in bounds_sources),
        )
    )
    padding = max(
        2.0 * requested_spacing,
        clearance + requested_spacing,
        (thickness + 2.0 * requested_spacing) if thickness is not None else 0.0,
    )
    expanded_bounds = []
    for axis in range(3):
        expanded_bounds.extend(
            (
                float(bounds[2 * axis] - padding),
                float(bounds[2 * axis + 1] + padding),
            )
        )
    dimensions = tuple(
        max(
            3,
            int(
                math.ceil(
                    (expanded_bounds[2 * axis + 1] - expanded_bounds[2 * axis])
                    / requested_spacing
                )
            )
            + 1,
        )
        for axis in range(3)
    )
    sample_point_count = int(np.prod(dimensions, dtype=np.int64))
    if sample_point_count > MAX_SAMPLE_POINTS:
        raise ValueError(
            "The visible support domain and processing resolution request "
            f"{sample_point_count:,} samples; increase the resolution value "
            f"to stay below {MAX_SAMPLE_POINTS:,}."
        )

    def sample_distances(poly_data: vtk.vtkPolyData):
        implicit = vtk.vtkImplicitPolyDataDistance()
        implicit.SetInput(poly_data)
        sample = vtk.vtkSampleFunction()
        sample.SetImplicitFunction(implicit)
        sample.SetModelBounds(*expanded_bounds)
        sample.SetSampleDimensions(*dimensions)
        sample.ComputeNormalsOff()
        sample.Update()
        return sample.GetOutput()

    candidate_image = sample_distances(candidate)
    anatomy_image = sample_distances(anatomy)
    candidate_distances = vtk_to_numpy(
        candidate_image.GetPointData().GetScalars()
    ).reshape(dimensions[2], dimensions[1], dimensions[0])
    anatomy_distances = vtk_to_numpy(
        anatomy_image.GetPointData().GetScalars()
    ).reshape(dimensions[2], dimensions[1], dimensions[0])
    actual_spacing = tuple(float(value) for value in candidate_image.GetSpacing())
    clearance_guard = max(0.0, clearance - max(actual_spacing) * 1.25)
    repair_band_limit = None
    if use_fitting_surface_fallback:
        fitting_image = sample_distances(fitting_surface)
        fitting_distances = vtk_to_numpy(
            fitting_image.GetPointData().GetScalars()
        ).reshape(dimensions[2], dimensions[1], dimensions[0])
        half_voxel_diagonal = 0.5 * math.sqrt(
            sum(value * value for value in actual_spacing)
        )
        repair_band_limit = thickness + half_voxel_diagonal
        # vtkImplicitPolyDataDistance remains a reliable closest-surface
        # distance for an open patch even when its sign is not meaningful.
        # The absolute-distance band creates a finite capped volume around the
        # fitting patch; the blockout/anatomy distance then removes its inward
        # half and preserves the requested seating clearance.
        shell_mask = np.abs(fitting_distances) <= repair_band_limit
    else:
        shell_mask = candidate_distances <= 0.0
    if boundary_bridge is not None:
        bridge_image = sample_distances(boundary_bridge)
        bridge_distances = vtk_to_numpy(
            bridge_image.GetPointData().GetScalars()
        ).reshape(dimensions[2], dimensions[1], dimensions[0])
        shell_mask |= bridge_distances <= 0.0
    shell_mask &= anatomy_distances >= clearance_guard
    closing_kernel_size = 1
    if closing > 0.0:
        closing_radius_voxels = max(
            1,
            int(math.ceil(closing / max(actual_spacing))),
        )
        closing_kernel_size = 2 * closing_radius_voxels + 1
        closing_image = vtk.vtkImageData()
        closing_image.DeepCopy(candidate_image)
        closing_scalars = numpy_to_vtk(
            np.ascontiguousarray(shell_mask.astype(np.uint8).ravel()),
            deep=True,
            array_type=vtk.VTK_UNSIGNED_CHAR,
        )
        closing_image.GetPointData().SetScalars(closing_scalars)
        dilate = vtk.vtkImageDilateErode3D()
        dilate.SetInputData(closing_image)
        dilate.SetKernelSize(
            closing_kernel_size,
            closing_kernel_size,
            closing_kernel_size,
        )
        dilate.SetDilateValue(1)
        dilate.SetErodeValue(0)
        erode = vtk.vtkImageDilateErode3D()
        erode.SetInputConnection(dilate.GetOutputPort())
        erode.SetKernelSize(
            closing_kernel_size,
            closing_kernel_size,
            closing_kernel_size,
        )
        erode.SetDilateValue(0)
        erode.SetErodeValue(1)
        erode.Update()
        shell_mask = vtk_to_numpy(
            erode.GetOutput().GetPointData().GetScalars()
        ).reshape(dimensions[2], dimensions[1], dimensions[0]) > 0
        # Closing must never reintroduce material inside the fit exclusion.
        shell_mask &= anatomy_distances >= clearance_guard
    occupied_sample_count = int(np.count_nonzero(shell_mask))
    if not occupied_sample_count:
        raise ValueError(
            "Fit-clearance subtraction removed the complete Hollow candidate."
        )

    binary_image = vtk.vtkImageData()
    binary_image.DeepCopy(candidate_image)
    scalars = numpy_to_vtk(
        np.ascontiguousarray(shell_mask.astype(np.uint8).ravel()),
        deep=True,
        array_type=vtk.VTK_UNSIGNED_CHAR,
    )
    scalars.SetName("DENTOBOT.PatientContactShellMask")
    binary_image.GetPointData().SetScalars(scalars)

    contour = vtk.vtkFlyingEdges3D()
    contour.SetInputData(binary_image)
    contour.SetValue(0, 0.5)
    contour.ComputeNormalsOff()
    contour.ComputeGradientsOff()
    triangle_filter = vtk.vtkTriangleFilter()
    triangle_filter.SetInputConnection(contour.GetOutputPort())
    clean_filter = vtk.vtkCleanPolyData()
    clean_filter.SetInputConnection(triangle_filter.GetOutputPort())
    normals_filter = vtk.vtkPolyDataNormals()
    normals_filter.SetInputConnection(clean_filter.GetOutputPort())
    normals_filter.ConsistencyOn()
    normals_filter.AutoOrientNormalsOn()
    normals_filter.SplittingOff()
    normals_filter.Update()
    shell = vtk.vtkPolyData()
    shell.DeepCopy(normals_filter.GetOutput())
    topology = surface_topology(shell)
    if not shell.GetNumberOfPoints() or not shell.GetNumberOfCells():
        raise RuntimeError("The patient-contact shell extraction produced no geometry.")
    if topology["boundaryOrNonManifoldEdgeCount"]:
        raise RuntimeError(
            "The patient-contact shell is not watertight/manifold after the "
            f"voxel Boolean ({topology['boundaryOrNonManifoldEdgeCount']} invalid edges)."
        )

    anatomy_distance = vtk.vtkImplicitPolyDataDistance()
    anatomy_distance.SetInput(anatomy)
    shell_clearances = np.asarray(
        [
            float(anatomy_distance.EvaluateFunction(shell.GetPoint(index)))
            for index in range(shell.GetNumberOfPoints())
        ],
        dtype=float,
    )
    return shell, {
        **topology,
        "method": (
            "DynamicModelerHollowWithFittingSurfaceDistanceFieldFallback"
            if use_fitting_surface_fallback
            else "DynamicModelerHollowWithTightVoxelClearanceBoolean"
        ),
        "candidateRepairMode": (
            "FittingSurfaceDistanceBand"
            if use_fitting_surface_fallback
            else "None"
        ),
        "repairBandLimitMm": repair_band_limit,
        "shellThicknessMm": thickness,
        "boundaryBridgeIntegrated": boundary_bridge is not None,
        "boundaryBridgeTopology": bridge_topology,
        "fitClearanceMm": clearance,
        "clearanceGuardMm": clearance_guard,
        "requestedSpacingMm": requested_spacing,
        "voxelClosingMm": closing,
        "closingKernelSizeVoxels": closing_kernel_size,
        "actualSpacingMm": actual_spacing,
        "sampleDimensions": dimensions,
        "samplePointCount": sample_point_count,
        "occupiedSampleCount": occupied_sample_count,
        "candidateTopology": candidate_topology,
        "minimumAnatomyDistanceMm": float(np.min(shell_clearances)),
        "fifthPercentileAnatomyDistanceMm": float(
            np.percentile(shell_clearances, 5.0)
        ),
        "boundsRas": tuple(float(value) for value in shell.GetBounds()),
    }


def _direction_frame(direction_ras) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    z_axis = _finite_vector(direction_ras, 3, "Direction")
    length = float(np.linalg.norm(z_axis))
    if length <= 1e-6:
        raise ValueError("Direction must have non-zero length.")
    z_axis /= length
    reference = np.array((0.0, 0.0, 1.0), dtype=float)
    if abs(float(np.dot(reference, z_axis))) > 0.9:
        reference = np.array((0.0, 1.0, 0.0), dtype=float)
    x_axis = np.cross(reference, z_axis)
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)
    y_axis /= np.linalg.norm(y_axis)
    return x_axis, y_axis, z_axis


def _transform_polydata_with_matrix(
    poly_data: vtk.vtkPolyData,
    matrix: vtk.vtkMatrix4x4,
) -> vtk.vtkPolyData:
    transform = vtk.vtkTransform()
    transform.SetMatrix(matrix)
    transform_filter = vtk.vtkTransformPolyDataFilter()
    transform_filter.SetInputData(poly_data)
    transform_filter.SetTransform(transform)
    transform_filter.Update()
    output = vtk.vtkPolyData()
    output.DeepCopy(transform_filter.GetOutput())
    return output


def analyze_surface_undercuts(
    support_patch_world: vtk.vtkPolyData,
    insertion_direction_ras,
    *,
    angle_tolerance_deg: float,
) -> tuple[vtk.vtkPolyData, dict]:
    """Extract retentive cells relative to Approach→Seat insertion direction."""

    insertion = _finite_vector(insertion_direction_ras, 3, "Insertion direction")
    insertion_length = float(np.linalg.norm(insertion))
    if insertion_length <= 1e-6:
        raise ValueError("Insertion direction must have non-zero length.")
    insertion /= insertion_length
    removal = -insertion
    tolerance = float(angle_tolerance_deg)
    if not math.isfinite(tolerance) or tolerance < 0.0 or tolerance > 45.0:
        raise ValueError("Undercut angle tolerance must be between 0 and 45 degrees.")

    patch = _triangulated_clean_surface(support_patch_world)
    normals_filter = vtk.vtkPolyDataNormals()
    normals_filter.SetInputData(patch)
    normals_filter.ComputePointNormalsOff()
    normals_filter.ComputeCellNormalsOn()
    normals_filter.ConsistencyOn()
    normals_filter.AutoOrientNormalsOff()
    normals_filter.SplittingOff()
    normals_filter.Update()
    prepared = normals_filter.GetOutput()
    cell_normals = prepared.GetCellData().GetNormals()
    dot_threshold = -math.sin(math.radians(tolerance))
    selected_cells = vtk.vtkCellArray()
    selected_area = 0.0
    total_area = 0.0
    selected_count = 0
    for cell_index in range(prepared.GetNumberOfCells()):
        cell = prepared.GetCell(cell_index)
        if cell.GetNumberOfPoints() != 3:
            continue
        point0 = np.asarray(prepared.GetPoint(cell.GetPointId(0)), dtype=float)
        point1 = np.asarray(prepared.GetPoint(cell.GetPointId(1)), dtype=float)
        point2 = np.asarray(prepared.GetPoint(cell.GetPointId(2)), dtype=float)
        area = 0.5 * float(np.linalg.norm(np.cross(point1 - point0, point2 - point0)))
        total_area += area
        normal = np.asarray(cell_normals.GetTuple(cell_index), dtype=float)
        normal_length = float(np.linalg.norm(normal))
        if normal_length <= 1e-12:
            continue
        normal /= normal_length
        if float(np.dot(normal, removal)) < dot_threshold:
            selected_cells.InsertNextCell(cell)
            selected_area += area
            selected_count += 1

    undercut = vtk.vtkPolyData()
    undercut.SetPoints(prepared.GetPoints())
    undercut.SetPolys(selected_cells)
    clean = vtk.vtkCleanPolyData()
    clean.SetInputData(undercut)
    clean.Update()
    output = vtk.vtkPolyData()
    output.DeepCopy(clean.GetOutput())
    return output, {
        "method": "SurfaceNormalRemovalDirection",
        "angleToleranceDeg": tolerance,
        "dotThreshold": dot_threshold,
        "insertionDirectionRas": tuple(float(value) for value in insertion),
        "removalDirectionRas": tuple(float(value) for value in removal),
        "sourceTriangleCount": int(prepared.GetNumberOfCells()),
        "undercutTriangleCount": int(selected_count),
        "sourceAreaMm2": total_area,
        "undercutAreaMm2": selected_area,
        "undercutAreaFraction": (
            selected_area / total_area if total_area > 1e-12 else 0.0
        ),
    }


def create_directional_blockout(
    anatomy_world: vtk.vtkPolyData,
    support_patch_world: vtk.vtkPolyData,
    insertion_direction_ras,
    *,
    sampling_spacing_mm: float,
    padding_mm: float,
) -> tuple[vtk.vtkPolyData, dict]:
    """Create a removal-axis height-field blockout in a tight local frame."""

    insertion = _finite_vector(insertion_direction_ras, 3, "Insertion direction")
    insertion_length = float(np.linalg.norm(insertion))
    if insertion_length <= 1e-6:
        raise ValueError("Insertion direction must have non-zero length.")
    insertion /= insertion_length
    removal = -insertion
    x_axis, y_axis, z_axis = _direction_frame(removal)
    spacing = float(sampling_spacing_mm)
    padding = float(padding_mm)
    if not math.isfinite(spacing) or spacing < 0.1 or spacing > 2.0:
        raise ValueError("Blockout processing resolution must be between 0.10 and 2.00 mm.")
    if not math.isfinite(padding) or padding < 1.0 or padding > 30.0:
        raise ValueError("Blockout padding must be between 1 and 30 mm.")

    anatomy = _triangulated_clean_surface(anatomy_world)
    support = _triangulated_clean_surface(support_patch_world)
    support_center = np.asarray(support.GetCenter(), dtype=float)
    world_to_local = vtk.vtkMatrix4x4()
    world_to_local.Identity()
    for row, axis in enumerate((x_axis, y_axis, z_axis)):
        for column in range(3):
            world_to_local.SetElement(row, column, float(axis[column]))
        world_to_local.SetElement(row, 3, -float(np.dot(axis, support_center)))
    local_to_world = vtk.vtkMatrix4x4()
    vtk.vtkMatrix4x4.Invert(world_to_local, local_to_world)
    local_anatomy = _transform_polydata_with_matrix(anatomy, world_to_local)
    local_support = _transform_polydata_with_matrix(support, world_to_local)
    support_bounds = local_support.GetBounds()
    local_bounds = (
        float(support_bounds[0] - padding),
        float(support_bounds[1] + padding),
        float(support_bounds[2] - padding),
        float(support_bounds[3] + padding),
        float(support_bounds[4] - padding),
        float(support_bounds[5] + padding),
    )
    dimensions = tuple(
        max(
            3,
            int(
                math.ceil(
                    (local_bounds[2 * axis + 1] - local_bounds[2 * axis])
                    / spacing
                )
            )
            + 1,
        )
        for axis in range(3)
    )
    sample_point_count = int(np.prod(dimensions, dtype=np.int64))
    if sample_point_count > MAX_SAMPLE_POINTS:
        raise ValueError(
            "The blockout domain and resolution request "
            f"{sample_point_count:,} samples; increase resolution or reduce padding."
        )

    implicit = vtk.vtkImplicitPolyDataDistance()
    implicit.SetInput(local_anatomy)
    sample = vtk.vtkSampleFunction()
    sample.SetImplicitFunction(implicit)
    sample.SetModelBounds(*local_bounds)
    sample.SetSampleDimensions(*dimensions)
    sample.ComputeNormalsOff()
    sample.Update()
    sampled_image = sample.GetOutput()
    distances = vtk_to_numpy(
        sampled_image.GetPointData().GetScalars()
    ).reshape(dimensions[2], dimensions[1], dimensions[0])
    anatomy_mask = distances <= 0.0
    any_anatomy = np.any(anatomy_mask, axis=0)
    if not np.any(any_anatomy):
        raise ValueError("The insertion-frame blockout domain contains no anatomy.")
    reversed_indices = np.argmax(anatomy_mask[::-1], axis=0)
    highest_indices = dimensions[2] - 1 - reversed_indices
    blockout_mask = np.zeros_like(anatomy_mask, dtype=bool)
    for row, column in np.argwhere(any_anatomy):
        highest = int(highest_indices[row, column])
        if highest >= 1:
            blockout_mask[1 : highest + 1, row, column] = True
    blockout_mask |= anatomy_mask
    # Keep a background layer around the volume so Flying Edges closes every cap.
    blockout_mask[0, :, :] = False
    blockout_mask[-1, :, :] = False
    blockout_mask[:, 0, :] = False
    blockout_mask[:, -1, :] = False
    blockout_mask[:, :, 0] = False
    blockout_mask[:, :, -1] = False
    occupied_count = int(np.count_nonzero(blockout_mask))
    if not occupied_count:
        raise ValueError("Directional blockout produced no occupied volume.")

    binary_image = vtk.vtkImageData()
    binary_image.DeepCopy(sampled_image)
    binary_scalars = numpy_to_vtk(
        np.ascontiguousarray(blockout_mask.astype(np.uint8).ravel()),
        deep=True,
        array_type=vtk.VTK_UNSIGNED_CHAR,
    )
    binary_scalars.SetName("DENTOBOT.DirectionalBlockoutMask")
    binary_image.GetPointData().SetScalars(binary_scalars)
    contour = vtk.vtkFlyingEdges3D()
    contour.SetInputData(binary_image)
    contour.SetValue(0, 0.5)
    contour.ComputeNormalsOff()
    contour.ComputeGradientsOff()
    triangle = vtk.vtkTriangleFilter()
    triangle.SetInputConnection(contour.GetOutputPort())
    clean = vtk.vtkCleanPolyData()
    clean.SetInputConnection(triangle.GetOutputPort())
    clean.Update()
    local_blockout = _triangulated_clean_surface(clean.GetOutput())
    world_blockout = _transform_polydata_with_matrix(
        local_blockout,
        local_to_world,
    )
    world_blockout = _triangulated_clean_surface(world_blockout)
    topology = surface_topology(world_blockout)
    if topology["boundaryOrNonManifoldEdgeCount"]:
        raise RuntimeError(
            "Directional blockout is not watertight/manifold "
            f"({topology['boundaryOrNonManifoldEdgeCount']} invalid edges)."
        )
    return world_blockout, {
        **topology,
        "method": "InsertionFrameDirectionalHeightField",
        "insertionDirectionRas": tuple(float(value) for value in insertion),
        "removalDirectionRas": tuple(float(value) for value in removal),
        "frameXAxisRas": tuple(float(value) for value in x_axis),
        "frameYAxisRas": tuple(float(value) for value in y_axis),
        "frameZAxisRas": tuple(float(value) for value in z_axis),
        "requestedSpacingMm": spacing,
        "actualSpacingMm": tuple(float(value) for value in sampled_image.GetSpacing()),
        "paddingMm": padding,
        "sampleDimensions": dimensions,
        "samplePointCount": sample_point_count,
        "occupiedSampleCount": occupied_count,
        "boundsRas": tuple(float(value) for value in world_blockout.GetBounds()),
    }


def _validate_template_parameters(
    clearance_mm: float,
    thickness_mm: float,
    sampling_spacing_mm: float,
    channel_diameter_mm: float,
    sleeve_outer_diameter_mm: float,
    sleeve_inner_diameter_mm: float,
    sleeve_height_mm: float,
) -> dict[str, float]:
    values = {
        "clearanceMm": float(clearance_mm),
        "thicknessMm": float(thickness_mm),
        "samplingSpacingMm": float(sampling_spacing_mm),
        "channelDiameterMm": float(channel_diameter_mm),
        "sleeveOuterDiameterMm": float(sleeve_outer_diameter_mm),
        "sleeveInnerDiameterMm": float(sleeve_inner_diameter_mm),
        "sleeveHeightMm": float(sleeve_height_mm),
    }
    if any(not math.isfinite(value) for value in values.values()):
        raise ValueError("All Step 5B dimensions must be finite.")
    if values["clearanceMm"] < 0.0:
        raise ValueError("Shell clearance must be zero or greater.")
    for key in (
        "thicknessMm",
        "samplingSpacingMm",
        "channelDiameterMm",
        "sleeveOuterDiameterMm",
        "sleeveInnerDiameterMm",
        "sleeveHeightMm",
    ):
        if values[key] <= 0.0:
            raise ValueError(f"{key} must be greater than zero.")
    if values["sleeveInnerDiameterMm"] >= values["sleeveOuterDiameterMm"]:
        raise ValueError("Sleeve inner diameter must be smaller than its outer diameter.")
    if values["channelDiameterMm"] < values["sleeveInnerDiameterMm"]:
        raise ValueError(
            "The shell channel diameter must be at least the sleeve inner diameter."
        )
    return values


def _trajectory_axis(entry_ras, target_ras) -> tuple[np.ndarray, np.ndarray, float]:
    entry = _finite_vector(entry_ras, 3, "Trajectory Entry")
    target = _finite_vector(target_ras, 3, "Trajectory Target")
    direction = target - entry
    length = float(np.linalg.norm(direction))
    if length <= 1e-6:
        raise ValueError("The Entry-to-Target trajectory must have non-zero length.")
    return entry, direction / length, length


def create_research_shell(
    anatomy_world: vtk.vtkPolyData,
    roi_bounds_ras,
    entry_ras,
    target_ras,
    *,
    clearance_mm: float,
    thickness_mm: float,
    sampling_spacing_mm: float,
    channel_diameter_mm: float,
    sleeve_outer_diameter_mm: float,
    sleeve_inner_diameter_mm: float,
    sleeve_height_mm: float,
) -> tuple[vtk.vtkPolyData, dict]:
    """Create an exterior distance-band shell, ROI trim, and drill channel."""

    parameters = _validate_template_parameters(
        clearance_mm,
        thickness_mm,
        sampling_spacing_mm,
        channel_diameter_mm,
        sleeve_outer_diameter_mm,
        sleeve_inner_diameter_mm,
        sleeve_height_mm,
    )
    bounds = _finite_vector(roi_bounds_ras, 6, "Shell ROI bounds")
    if any(bounds[2 * axis] >= bounds[2 * axis + 1] for axis in range(3)):
        raise ValueError("The shell ROI must have positive size in every axis.")
    entry, axis, trajectory_length = _trajectory_axis(entry_ras, target_ras)
    anatomy = _triangulated_clean_surface(anatomy_world)

    requested_spacing = parameters["samplingSpacingMm"]
    expanded_bounds = []
    for axis_index in range(3):
        expanded_bounds.extend(
            (
                float(bounds[2 * axis_index] - requested_spacing),
                float(bounds[2 * axis_index + 1] + requested_spacing),
            )
        )
    dimensions = tuple(
        max(
            3,
            int(
                math.ceil(
                    (expanded_bounds[2 * axis_index + 1]
                     - expanded_bounds[2 * axis_index])
                    / requested_spacing
                )
            )
            + 1,
        )
        for axis_index in range(3)
    )
    sample_point_count = int(np.prod(dimensions, dtype=np.int64))
    if sample_point_count > MAX_SAMPLE_POINTS:
        raise ValueError(
            "The ROI and sampling spacing request "
            f"{sample_point_count:,} samples; reduce the ROI or increase spacing "
            f"to stay below {MAX_SAMPLE_POINTS:,}."
        )

    implicit_distance = vtk.vtkImplicitPolyDataDistance()
    implicit_distance.SetInput(anatomy)
    sample = vtk.vtkSampleFunction()
    sample.SetImplicitFunction(implicit_distance)
    sample.SetModelBounds(*expanded_bounds)
    sample.SetSampleDimensions(*dimensions)
    sample.ComputeNormalsOff()
    sample.Update()

    sampled_image = sample.GetOutput()
    actual_spacing = tuple(float(value) for value in sampled_image.GetSpacing())
    origin = tuple(float(value) for value in sampled_image.GetOrigin())
    distances = vtk_to_numpy(sampled_image.GetPointData().GetScalars()).reshape(
        dimensions[2], dimensions[1], dimensions[0]
    )

    x = origin[0] + np.arange(dimensions[0], dtype=float) * actual_spacing[0]
    y = origin[1] + np.arange(dimensions[1], dtype=float) * actual_spacing[1]
    z = origin[2] + np.arange(dimensions[2], dtype=float) * actual_spacing[2]
    inside_roi = (
        (x[np.newaxis, np.newaxis, :] >= bounds[0])
        & (x[np.newaxis, np.newaxis, :] <= bounds[1])
        & (y[np.newaxis, :, np.newaxis] >= bounds[2])
        & (y[np.newaxis, :, np.newaxis] <= bounds[3])
        & (z[:, np.newaxis, np.newaxis] >= bounds[4])
        & (z[:, np.newaxis, np.newaxis] <= bounds[5])
    )
    shell_mask = (
        (distances >= parameters["clearanceMm"])
        & (
            distances
            <= parameters["clearanceMm"] + parameters["thicknessMm"]
        )
        & inside_roi
    )

    dx = x[np.newaxis, np.newaxis, :] - entry[0]
    dy = y[np.newaxis, :, np.newaxis] - entry[1]
    dz = z[:, np.newaxis, np.newaxis] - entry[2]
    projection = dx * axis[0] + dy * axis[1] + dz * axis[2]
    radial_squared = np.maximum(
        0.0,
        dx * dx + dy * dy + dz * dz - projection * projection,
    )
    channel_radius = parameters["channelDiameterMm"] / 2.0
    channel_mask = (
        (radial_squared <= channel_radius * channel_radius)
        & (projection >= -parameters["sleeveHeightMm"] - requested_spacing)
        & (projection <= trajectory_length + requested_spacing)
    )
    shell_mask[channel_mask] = False
    occupied_sample_count = int(np.count_nonzero(shell_mask))
    if not occupied_sample_count:
        raise ValueError(
            "The current ROI and shell dimensions produce no template geometry."
        )

    binary_image = vtk.vtkImageData()
    binary_image.DeepCopy(sampled_image)
    binary_scalars = numpy_to_vtk(
        np.ascontiguousarray(shell_mask.astype(np.uint8).ravel()),
        deep=True,
        array_type=vtk.VTK_UNSIGNED_CHAR,
    )
    binary_scalars.SetName("DENTOBOT.ResearchShellMask")
    binary_image.GetPointData().SetScalars(binary_scalars)

    contour = vtk.vtkFlyingEdges3D()
    contour.SetInputData(binary_image)
    contour.SetValue(0, 0.5)
    contour.ComputeNormalsOff()
    contour.ComputeGradientsOff()

    triangle_filter = vtk.vtkTriangleFilter()
    triangle_filter.SetInputConnection(contour.GetOutputPort())
    clean_filter = vtk.vtkCleanPolyData()
    clean_filter.SetInputConnection(triangle_filter.GetOutputPort())
    clean_filter.Update()

    shell = vtk.vtkPolyData()
    shell.DeepCopy(clean_filter.GetOutput())
    if not shell.GetNumberOfPoints() or not shell.GetNumberOfCells():
        raise RuntimeError("Slicer could not extract a shell surface from the mask.")
    topology = surface_topology(shell)
    if topology["boundaryOrNonManifoldEdgeCount"]:
        raise RuntimeError(
            "The generated shell is not watertight/manifold "
            f"({topology['boundaryOrNonManifoldEdgeCount']} invalid edges)."
        )
    return shell, {
        **parameters,
        **topology,
        "sampleDimensions": dimensions,
        "samplePointCount": sample_point_count,
        "occupiedSampleCount": occupied_sample_count,
        "actualSpacingMm": actual_spacing,
        "roiBoundsRas": tuple(float(value) for value in bounds),
        "trajectoryLengthMm": trajectory_length,
    }


def create_hollow_sleeve(
    entry_ras,
    target_ras,
    *,
    outer_diameter_mm: float,
    inner_diameter_mm: float,
    height_mm: float,
    resolution: int = 96,
) -> tuple[vtk.vtkPolyData, dict]:
    """Create a closed annular sleeve extending outward from Entry."""

    outer_diameter = float(outer_diameter_mm)
    inner_diameter = float(inner_diameter_mm)
    height = float(height_mm)
    if any(
        not math.isfinite(value)
        for value in (outer_diameter, inner_diameter, height)
    ):
        raise ValueError("Sleeve dimensions must be finite.")
    if inner_diameter <= 0.0 or outer_diameter <= inner_diameter or height <= 0.0:
        raise ValueError(
            "Sleeve dimensions require 0 < inner diameter < outer diameter and positive height."
        )
    if resolution < 12 or resolution > 720:
        raise ValueError("Sleeve resolution must be between 12 and 720.")

    entry, inward_axis, trajectory_length = _trajectory_axis(entry_ras, target_ras)
    outward_axis = -inward_axis
    reference = np.array((0.0, 0.0, 1.0), dtype=float)
    if abs(float(np.dot(reference, outward_axis))) > 0.9:
        reference = np.array((0.0, 1.0, 0.0), dtype=float)
    basis_u = np.cross(outward_axis, reference)
    basis_u /= np.linalg.norm(basis_u)
    basis_v = np.cross(outward_axis, basis_u)

    inner_radius = inner_diameter / 2.0
    outer_radius = outer_diameter / 2.0
    lower_center = entry
    upper_center = entry + outward_axis * height
    points = vtk.vtkPoints()
    rings = []
    for center, radius in (
        (lower_center, outer_radius),
        (upper_center, outer_radius),
        (lower_center, inner_radius),
        (upper_center, inner_radius),
    ):
        ring = []
        for index in range(resolution):
            angle = 2.0 * math.pi * index / resolution
            point = center + radius * (
                math.cos(angle) * basis_u + math.sin(angle) * basis_v
            )
            ring.append(points.InsertNextPoint(*point))
        rings.append(ring)

    outer_lower, outer_upper, inner_lower, inner_upper = rings
    triangles = vtk.vtkCellArray()

    def add_triangle(a: int, b: int, c: int) -> None:
        triangle = vtk.vtkTriangle()
        triangle.GetPointIds().SetId(0, a)
        triangle.GetPointIds().SetId(1, b)
        triangle.GetPointIds().SetId(2, c)
        triangles.InsertNextCell(triangle)

    for index in range(resolution):
        next_index = (index + 1) % resolution
        add_triangle(outer_lower[index], outer_lower[next_index], outer_upper[next_index])
        add_triangle(outer_lower[index], outer_upper[next_index], outer_upper[index])
        add_triangle(inner_lower[index], inner_upper[next_index], inner_lower[next_index])
        add_triangle(inner_lower[index], inner_upper[index], inner_upper[next_index])
        add_triangle(outer_lower[index], inner_lower[next_index], outer_lower[next_index])
        add_triangle(outer_lower[index], inner_lower[index], inner_lower[next_index])
        add_triangle(outer_upper[index], outer_upper[next_index], inner_upper[next_index])
        add_triangle(outer_upper[index], inner_upper[next_index], inner_upper[index])

    sleeve = vtk.vtkPolyData()
    sleeve.SetPoints(points)
    sleeve.SetPolys(triangles)
    sleeve = _triangulated_clean_surface(sleeve)
    topology = surface_topology(sleeve)
    if topology["boundaryOrNonManifoldEdgeCount"]:
        raise RuntimeError(
            "The generated sleeve is not watertight/manifold "
            f"({topology['boundaryOrNonManifoldEdgeCount']} invalid edges)."
        )
    return sleeve, {
        **topology,
        "outerDiameterMm": outer_diameter,
        "innerDiameterMm": inner_diameter,
        "heightMm": height,
        "resolution": int(resolution),
        "trajectoryLengthMm": trajectory_length,
        "entryRas": tuple(float(value) for value in entry),
        "outwardAxisRas": tuple(float(value) for value in outward_axis),
    }


def write_stl_atomic(poly_data: vtk.vtkPolyData, output_path: str | Path) -> Path:
    """Write one binary STL via a same-directory temporary file."""

    topology = surface_topology(poly_data)
    if topology["boundaryOrNonManifoldEdgeCount"]:
        raise ValueError("Only a watertight/manifold model can be exported to STL.")
    path = Path(output_path)
    if path.suffix.lower() != ".stl":
        raise ValueError("The STL output filename must end in .stl.")
    if not path.parent.is_dir():
        raise ValueError("The selected STL output directory does not exist.")

    temporary_path = path.with_name(f".{path.name}.dentobot-partial")
    writer = vtk.vtkSTLWriter()
    writer.SetFileName(str(temporary_path))
    writer.SetInputData(poly_data)
    writer.SetFileTypeToBinary()
    if writer.Write() != 1 or not temporary_path.is_file():
        if temporary_path.exists():
            temporary_path.unlink()
        raise RuntimeError(f"VTK could not write {path.name}.")
    os.replace(temporary_path, path)
    return path
