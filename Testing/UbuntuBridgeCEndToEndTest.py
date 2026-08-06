"""Headless Slicer-launched Ubuntu Bridge C end-to-end test."""

import json
import os
import sys
import time
import traceback
from pathlib import Path

import qt
import slicer
import vtk

from DENTOWorkflow import DENTOWorkflowWidget


SOURCE_PATH = Path("/workspace/data/fixtures/cbct-dental-surgery.nii")
TIMEOUT_SECONDS = 15 * 60


def run_test():
    missing_variables = [
        name
        for name in (
            "DENTOBOT_BACKEND_PYTHON",
            "DENTOBOT_RUN_ARTIFACT_ROOT",
        )
        if not os.environ.get(name, "").strip()
    ]
    if missing_variables:
        raise RuntimeError(
            "Missing launcher runtime configuration: "
            + ", ".join(missing_variables)
        )
    staging_root = Path(os.environ["DENTOBOT_RUN_ARTIFACT_ROOT"])
    scene_path = staging_root / "ubuntu-bridge-c-e2e-20260731.mrb"
    os.environ["TOTALSEG_HOME_DIR"] = (
        "/workspace/data/model-cache/totalsegmentator"
    )
    source_volume = slicer.util.loadVolume(
        str(SOURCE_PATH),
        {"name": "CBCTDentalSurgery_BridgeC_E2E"},
    )
    if not source_volume:
        raise RuntimeError("Slicer could not load the public CBCT fixture")

    parent = slicer.qMRMLWidget()
    parent.setLayout(qt.QVBoxLayout())
    parent.setMRMLScene(slicer.mrmlScene)
    widget = DENTOWorkflowWidget(parent)
    widget.setup()
    widget.initializeParameterNode()
    widget._parameterNode.inferenceDevice = "cpu"
    widget._parameterNode.inputVolume = source_volume
    widget.ui.inputVolumeSelector.setCurrentNode(source_volume)

    widget.onRunTeethSegmentation()
    if not widget._backendIsRunning():
        raise RuntimeError(
            "Bridge C did not start: "
            f"{widget.ui.backendStatusLabel.text}"
        )

    deadline = time.monotonic() + TIMEOUT_SECONDS
    while widget._backendIsRunning() and time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.02)
    slicer.app.processEvents()
    if widget._backendIsRunning():
        widget.onCancelBackend()
        raise TimeoutError("Bridge C exceeded the 15-minute test timeout")

    segmentation = widget.logic.getLatestTeethSegmentationNode()
    if not segmentation:
        raise AssertionError(
            "Bridge C completed without a segmentation: "
            f"{widget.ui.backendStatusLabel.text}"
        )
    segment_count = segmentation.GetSegmentation().GetNumberOfSegments()
    if segment_count != 54:
        raise AssertionError(f"expected 54 segments, got {segment_count}")
    if segmentation.GetAttribute("DENTOBOT.ActualDevice") != "cpu":
        raise AssertionError("Bridge C did not preserve the explicit CPU device")
    if not slicer.util.saveScene(str(scene_path)):
        raise RuntimeError("Slicer could not save the end-to-end review scene")

    return {
        "event": "passed",
        "status": widget.ui.backendStatusLabel.text,
        "runId": segmentation.GetAttribute("DENTOBOT.RunId"),
        "resultJson": segmentation.GetAttribute(
            "DENTOBOT.ResultMetadataPath"
        ),
        "segmentCount": segment_count,
        "actualDevice": segmentation.GetAttribute("DENTOBOT.ActualDevice"),
        "scene": str(scene_path),
        "sceneSizeBytes": scene_path.stat().st_size,
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
