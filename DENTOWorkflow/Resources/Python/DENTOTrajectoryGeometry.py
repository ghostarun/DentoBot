"""Geometry helpers for assisted DENTOBOT trajectory initialization.

The functions in this module do not create MRML nodes.  They estimate one or
two rootward target points from a complete tooth surface and clinician-placed
crown entry points.  The result is deliberately an initialization aid: CBCT
tooth surfaces do not identify a canal centreline or establish a safe drill
path.
"""

from __future__ import annotations

import math

import numpy as np


def _points(values, label: str, *, minimum_count: int = 3) -> np.ndarray:
    try:
        points = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain numeric 3D points.") from exc
    if (
        points.ndim != 2
        or points.shape[1] != 3
        or points.shape[0] < int(minimum_count)
    ):
        raise ValueError(
            f"{label} must contain at least {int(minimum_count)} 3D point(s)."
        )
    if not np.all(np.isfinite(points)):
        raise ValueError(f"{label} contains a non-finite coordinate.")
    return points


def _unit(vector: np.ndarray, label: str, epsilon: float = 1e-8) -> np.ndarray:
    length = float(np.linalg.norm(vector))
    if not math.isfinite(length) or length <= epsilon:
        raise ValueError(f"{label} does not define a stable direction.")
    return vector / length


def _transverse_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    references = np.eye(3, dtype=float)
    reference = references[int(np.argmin(np.abs(references @ axis)))]
    transverse_x = _unit(np.cross(reference, axis), "Tooth transverse axis")
    transverse_y = _unit(np.cross(axis, transverse_x), "Tooth transverse axis")
    return transverse_x, transverse_y


def _deterministic_two_means(points_2d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return stable two-cluster labels and centroids without a dependency."""

    centroid = np.mean(points_2d, axis=0)
    first_index = int(np.argmax(np.sum((points_2d - centroid) ** 2, axis=1)))
    second_index = int(
        np.argmax(np.sum((points_2d - points_2d[first_index]) ** 2, axis=1))
    )
    centers = np.vstack((points_2d[first_index], points_2d[second_index]))
    labels = np.zeros(points_2d.shape[0], dtype=np.int8)
    for _iteration in range(40):
        distances = np.sum(
            (points_2d[:, np.newaxis, :] - centers[np.newaxis, :, :]) ** 2,
            axis=2,
        )
        new_labels = np.argmin(distances, axis=1).astype(np.int8)
        if not np.any(new_labels == 0) or not np.any(new_labels == 1):
            raise ValueError("The root-side surface did not form two clusters.")
        new_centers = np.vstack(
            (np.mean(points_2d[new_labels == 0], axis=0),
             np.mean(points_2d[new_labels == 1], axis=0))
        )
        if np.array_equal(new_labels, labels) and np.allclose(
            new_centers, centers, atol=1e-8
        ):
            labels = new_labels
            centers = new_centers
            break
        labels = new_labels
        centers = new_centers
    return labels, centers


def _estimate_rootward_axis(
    surface_points: np.ndarray,
    entry_centroid: np.ndarray,
) -> np.ndarray:
    """Estimate crown-to-root polarity from the clinician's crown entries."""

    robust_centroid = np.median(surface_points, axis=0)
    initial = robust_centroid - entry_centroid
    if float(np.linalg.norm(initial)) <= 1e-8:
        centered = surface_points - np.mean(surface_points, axis=0)
        eigenvalues, eigenvectors = np.linalg.eigh(centered.T @ centered)
        initial = eigenvectors[:, int(np.argmax(eigenvalues))]
    axis = _unit(initial, "Entry-to-tooth-centre vector")

    # Refine toward the remote surface cap.  This makes the estimate less
    # sensitive to an off-centre crown click without assuming world X/Y/Z.
    for quantile in (0.60, 0.70, 0.78):
        projections = (surface_points - entry_centroid) @ axis
        far_points = surface_points[
            projections >= float(np.quantile(projections, quantile))
        ]
        if far_points.shape[0] >= 3:
            refined = np.mean(far_points, axis=0) - entry_centroid
            if float(np.linalg.norm(refined)) > 1e-8:
                axis = _unit(refined, "Refined crown-to-root axis")
    return axis


def infer_root_targets(
    surface_points_ras,
    entry_points_ras,
    root_count: int,
    *,
    minimum_root_separation_mm: float = 0.75,
    minimum_separation_ratio: float = 1.10,
) -> dict:
    """Estimate one/two rootward targets in world RAS.

    ``entry_points_ras`` resolves crown/root polarity.  For two roots, several
    root-side cap sizes are evaluated with deterministic two-means clustering;
    the most clearly separated transverse solution is retained.  Target order
    is paired to entry order by minimum transverse travel.
    """

    surface = _points(surface_points_ras, "Tooth surface")
    entries = _points(entry_points_ras, "Entry points", minimum_count=1)
    if isinstance(root_count, bool) or int(root_count) not in (1, 2):
        raise ValueError("Assisted trajectory count must be one or two.")
    root_count = int(root_count)
    if entries.shape[0] != root_count:
        raise ValueError(
            f"Place exactly {root_count} entry point(s) before target estimation."
        )
    minimum_separation = float(minimum_root_separation_mm)
    minimum_ratio = float(minimum_separation_ratio)
    if (
        not math.isfinite(minimum_separation)
        or minimum_separation <= 0.0
        or not math.isfinite(minimum_ratio)
        or minimum_ratio <= 0.0
    ):
        raise ValueError("Root-separation thresholds must be finite and positive.")

    entry_centroid = np.mean(entries, axis=0)
    axis = _estimate_rootward_axis(surface, entry_centroid)
    transverse_x, transverse_y = _transverse_basis(axis)
    centered_surface = surface - entry_centroid
    rootward = centered_surface @ axis
    transverse = np.column_stack(
        (centered_surface @ transverse_x, centered_surface @ transverse_y)
    )

    if root_count == 1:
        cap_threshold = float(np.quantile(rootward, 0.82))
        cap_indices = np.flatnonzero(rootward >= cap_threshold)
        if cap_indices.size < 3:
            raise ValueError("The tooth surface has too few root-side points.")
        target = np.mean(surface[cap_indices], axis=0)
        return {
            "method": "EntryDirectedRootSurfaceCapV1",
            "rootCount": 1,
            "targetsRas": [[float(value) for value in target]],
            "toothAxisRas": [float(value) for value in axis],
            "entryCentroidRas": [float(value) for value in entry_centroid],
            "rootCapFraction": 0.18,
            "rootCapPointCount": int(cap_indices.size),
            "rootSeparationMm": None,
            "rootSeparationRatio": None,
            "confidence": "GeometricEstimate",
        }

    best = None
    for cap_fraction in (0.18, 0.24, 0.30, 0.36, 0.42):
        threshold = float(np.quantile(rootward, 1.0 - cap_fraction))
        cap_indices = np.flatnonzero(rootward >= threshold)
        if cap_indices.size < 16:
            continue
        try:
            labels, centers = _deterministic_two_means(transverse[cap_indices])
        except ValueError:
            continue
        counts = np.bincount(labels, minlength=2)
        if int(np.min(counts)) < max(6, int(round(cap_indices.size * 0.10))):
            continue
        separation = float(np.linalg.norm(centers[0] - centers[1]))
        squared_residual = 0.0
        for cluster_index in (0, 1):
            cluster_points = transverse[cap_indices][labels == cluster_index]
            squared_residual += float(
                np.sum((cluster_points - centers[cluster_index]) ** 2)
            )
        within_rms = math.sqrt(squared_residual / float(cap_indices.size))
        ratio = separation / max(within_rms, 1e-8)
        balance = float(np.min(counts) / np.max(counts))
        score = ratio * math.sqrt(balance)
        candidate = {
            "score": score,
            "capFraction": cap_fraction,
            "capThreshold": threshold,
            "capIndices": cap_indices,
            "labels": labels,
            "centers": centers,
            "counts": counts,
            "separation": separation,
            "withinRms": within_rms,
            "ratio": ratio,
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate

    if best is None:
        raise ValueError("The root-side surface could not be separated into two branches.")
    if (
        best["separation"] < minimum_separation
        or best["ratio"] < minimum_ratio
    ):
        raise ValueError(
            "Two distinct root branches were not resolved confidently "
            f"(separation {best['separation']:.2f} mm, ratio {best['ratio']:.2f})."
        )

    targets = []
    for cluster_index in (0, 1):
        cluster_indices = best["capIndices"][best["labels"] == cluster_index]
        cluster_rootward = rootward[cluster_indices]
        apex_threshold = float(np.quantile(cluster_rootward, 0.75))
        apex_indices = cluster_indices[cluster_rootward >= apex_threshold]
        if apex_indices.size < 3:
            apex_indices = cluster_indices
        targets.append(np.mean(surface[apex_indices], axis=0))

    entry_transverse = np.column_stack(
        (((entries - entry_centroid) @ transverse_x),
         ((entries - entry_centroid) @ transverse_y))
    )
    target_array = np.asarray(targets, dtype=float)
    target_transverse = np.column_stack(
        (((target_array - entry_centroid) @ transverse_x),
         ((target_array - entry_centroid) @ transverse_y))
    )
    direct_cost = float(
        np.sum((entry_transverse - target_transverse) ** 2)
    )
    swapped_cost = float(
        np.sum((entry_transverse - target_transverse[::-1]) ** 2)
    )
    if swapped_cost < direct_cost:
        target_array = target_array[::-1]

    return {
        "method": "EntryDirectedTwoRootSurfaceClustersV1",
        "rootCount": 2,
        "targetsRas": [
            [float(value) for value in target] for target in target_array
        ],
        "toothAxisRas": [float(value) for value in axis],
        "entryCentroidRas": [float(value) for value in entry_centroid],
        "rootCapFraction": float(best["capFraction"]),
        "rootCapPointCount": int(best["capIndices"].size),
        "rootClusterPointCounts": [int(value) for value in best["counts"]],
        "rootSeparationMm": float(best["separation"]),
        "rootWithinClusterRmsMm": float(best["withinRms"]),
        "rootSeparationRatio": float(best["ratio"]),
        "confidence": "GeometricallySeparated",
    }
