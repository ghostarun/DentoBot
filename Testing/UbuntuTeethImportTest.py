"""Headless Slicer import test for a completed Ubuntu teeth inference run."""

import json
import sys
import traceback
from pathlib import Path

import qt
import slicer
import vtk

from DENTOWorkflow import DENTOWorkflowWidget


RUN_ID = "ubuntu-cpu-standalone-20260731"
RUN_DIRECTORY = Path(
    "/workspace/data/dentobot-runs/ubuntu-cpu-standalone-20260731"
)
SOURCE_PATH = Path("/workspace/data/fixtures/cbct-dental-surgery.nii")
SCENE_PATH = RUN_DIRECTORY / "dentobot-teeth-review.mrb"


def run_test():
    source_volume = slicer.util.loadVolume(
        str(SOURCE_PATH),
        {"name": "CBCTDentalSurgery_UbuntuCPU"},
    )
    if not source_volume:
        raise RuntimeError("Slicer could not load the public CBCT fixture")

    parent = slicer.qMRMLWidget()
    parent.setLayout(qt.QVBoxLayout())
    parent.setMRMLScene(slicer.mrmlScene)
    widget = DENTOWorkflowWidget(parent)
    widget.setup()
    widget.initializeParameterNode()

    widget._completeTeethSegmentation(
        {
            "runId": RUN_ID,
            "paths": {
                "result": RUN_DIRECTORY / "result.json",
                "output": RUN_DIRECTORY / "teeth.nii.gz",
            },
            "sourceVolumeId": source_volume.GetID(),
            "device": "cpu",
        },
        0,
    )

    segmentation = widget.logic.getLatestTeethSegmentationNode()
    if not segmentation:
        raise AssertionError("Bridge C did not create a teeth segmentation node")
    segment_count = segmentation.GetSegmentation().GetNumberOfSegments()
    if segment_count != 54:
        raise AssertionError(f"expected 54 segments, got {segment_count}")
    if segmentation.GetAttribute("DENTOBOT.BridgeOperation") != "segment-teeth":
        raise AssertionError("Bridge C review metadata is missing")
    if not segmentation.GetSegmentation().ContainsRepresentation(
        slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName()
    ):
        raise AssertionError("closed-surface representation is missing")
    if not slicer.util.saveScene(str(SCENE_PATH)):
        raise RuntimeError("Slicer could not save the review scene")

    return {
        "event": "passed",
        "runId": RUN_ID,
        "sourceShape": list(source_volume.GetImageData().GetDimensions()),
        "segmentCount": segment_count,
        "segmentationNode": segmentation.GetName(),
        "scene": str(SCENE_PATH),
        "sceneSizeBytes": SCENE_PATH.stat().st_size,
    }


exit_code = 1
try:
    print(json.dumps(run_test(), sort_keys=True), flush=True)
    exit_code = 0
except Exception as error:
    print(
        json.dumps(
            {
                "event": "failed",
                "errorType": type(error).__name__,
                "message": str(error),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    traceback.print_exc()
finally:
    vtk.vtkDebugLeaks.SetExitError(False)
    slicer.app.quit()
    sys.exit(exit_code)
