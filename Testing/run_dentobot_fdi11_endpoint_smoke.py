"""Reproduce FDI11 assisted Entry and pulp endpoint on the operator's saved case."""

import json
from pathlib import Path
import sys
import traceback

import numpy as np
import slicer
import vtk
from vtk.util.numpy_support import vtk_to_numpy

sys.path.insert(0, "/workspace/ros2_ws/src/DentoBot/DENTOWorkflow/Resources/Python")
from DENTOCaseBundle import extract_scene_mrb  # noqa: E402
from DENTOTrajectoryGeometry import first_mask_intersection, infer_root_targets  # noqa: E402

SOURCE = Path("/workspace/data/Slicer_Saved/SampleStudy1/SEPT24/pulp-testing-fdi11.dentocase")


def run():
    scene, _ = extract_scene_mrb(SOURCE, Path(slicer.app.temporaryPath) / "fdi11-endpoint-smoke")
    assert slicer.util.loadScene(str(scene), {"clear": True})
    slicer.util.selectModule("DENTOWorkflow")
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    logic = widget.logic
    parameter = widget._parameterNode
    segmentation = next(node for node in slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
                        if node.GetSegmentation().GetSegmentIdBySegmentName("upper_right_central_incisor_fdi11"))
    tooth_id = segmentation.GetSegmentation().GetSegmentIdBySegmentName("upper_right_central_incisor_fdi11")
    association = logic.getTargetPulpAssociation(segmentation, tooth_id)
    assert association["validationState"] == "VALID"
    assert logic.getSegmentationReviewState(segmentation) == "Reviewed"
    surface = logic._getClosedSurfaceCopy(segmentation, tooth_id)
    points = np.asarray(vtk_to_numpy(surface.GetPoints().GetData()), dtype=float)
    centered = points - np.mean(points, axis=0)
    eigenvalues, eigenvectors = np.linalg.eigh(centered.T @ centered)
    axis = eigenvectors[:, int(np.argmax(eigenvalues))]
    # Upper incisor crown is inferior in RAS; reuse the prior crown-cap placement logic.
    if axis[2] > 0:
        axis *= -1
    cap = points[(centered @ axis) >= np.quantile(centered @ axis, 0.84)]
    entry = points[int(np.argmin(np.linalg.norm(points - np.mean(cap, axis=0), axis=1)))]
    print("FDI11_AUTO_ENTRY " + json.dumps({"entryRas": entry.tolist(), "capCount": len(cap),
                                          "pulpSegmentId": association["pulpSegmentId"]}), flush=True)
    target = np.asarray(infer_root_targets(points, [entry], 1)["targetsRas"][0])
    pulp_id = association["pulpSegmentId"]
    image = slicer.vtkOrientedImageData()
    assert segmentation.GetBinaryLabelmapRepresentation(pulp_id, image)
    mask = vtk_to_numpy(image.GetPointData().GetScalars()).reshape(tuple(reversed(image.GetDimensions())))
    image_to_ras = vtk.vtkMatrix4x4()
    image.GetImageToWorldMatrix(image_to_ras)
    ras_to_image = vtk.vtkMatrix4x4()
    vtk.vtkMatrix4x4.Invert(image_to_ras, ras_to_image)
    entry_ijk = ras_to_image.MultiplyPoint((*entry, 1))[:3]
    target_ijk = ras_to_image.MultiplyPoint((*target, 1))[:3]
    fraction = first_mask_intersection(mask, entry_ijk, target_ijk, image.GetExtent()[::2])
    native_hit = entry + fraction * (target - entry)
    pulp_surface = logic._getClosedSurfaceCopy(segmentation, pulp_id)
    locator = vtk.vtkOBBTree()
    locator.SetDataSet(pulp_surface)
    locator.BuildLocator()
    hits = vtk.vtkPoints()
    locator.IntersectWithLine(entry, target, hits, None)
    distance = vtk.vtkImplicitPolyDataDistance()
    distance.SetInput(pulp_surface)
    print("FDI11_ENDPOINT_GEOMETRY " + json.dumps({
        "entryRas": entry.tolist(), "rootTargetRas": target.tolist(),
        "nativeHitRas": native_hit.tolist(), "nativeFraction": fraction,
        "nativeHitSurfaceSignedDistanceMm": distance.EvaluateFunction(native_hit),
        "surfaceHitCount": hits.GetNumberOfPoints(),
        "surfaceHitsRas": [hits.GetPoint(i) for i in range(hits.GetNumberOfPoints())],
        "pulpVoxelCount": int(np.count_nonzero(mask)),
        "pulpSurfacePoints": pulp_surface.GetNumberOfPoints(),
        "pulpSurfaceCells": pulp_surface.GetNumberOfCells(),
        "pulpSurfaceBoundsRas": pulp_surface.GetBounds(),
    }), flush=True)
    old_smoothing = segmentation.GetSegmentation().GetConversionParameter("Smoothing factor")
    segmentation.GetSegmentation().SetConversionParameter("Smoothing factor", "0")
    segmentation.GetSegmentation().RemoveRepresentation(
        slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName())
    assert segmentation.CreateClosedSurfaceRepresentation()
    unsmoothed = logic._getClosedSurfaceCopy(segmentation, pulp_id)
    unsmoothed_locator = vtk.vtkOBBTree()
    unsmoothed_locator.SetDataSet(unsmoothed)
    unsmoothed_locator.BuildLocator()
    unsmoothed_hits = vtk.vtkPoints()
    unsmoothed_locator.IntersectWithLine(entry, target, unsmoothed_hits, None)
    print("FDI11_UNSMOOTHED_GEOMETRY " + json.dumps({
        "originalSmoothingFactor": old_smoothing,
        "surfaceHitCount": unsmoothed_hits.GetNumberOfPoints(),
        "surfaceHitsRas": [unsmoothed_hits.GetPoint(i) for i in range(unsmoothed_hits.GetNumberOfPoints())],
        "surfacePoints": unsmoothed.GetNumberOfPoints(),
        "surfaceBoundsRas": unsmoothed.GetBounds(),
    }), flush=True)
    slicer.util.exit(0)


try:
    run()
except Exception:
    traceback.print_exc()
    slicer.util.exit(1)
