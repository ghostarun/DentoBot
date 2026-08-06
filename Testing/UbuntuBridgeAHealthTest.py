"""Headless Slicer-launched Ubuntu Bridge A health test."""

import json
import os
import sys
import time
import traceback

import qt
import slicer
import vtk

from DENTOWorkflow import DENTOWorkflowWidget


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
    parent = slicer.qMRMLWidget()
    parent.setLayout(qt.QVBoxLayout())
    parent.setMRMLScene(slicer.mrmlScene)
    widget = DENTOWorkflowWidget(parent)
    try:
        widget.setup()
        widget.initializeParameterNode()
        widget._parameterNode.inferenceDevice = "cpu"

        widget.onCheckBackend()
        deadline = time.monotonic() + 60
        while widget._backendIsRunning() and time.monotonic() < deadline:
            slicer.app.processEvents()
            time.sleep(0.02)
        slicer.app.processEvents()
        if widget._backendIsRunning():
            widget.onCancelBackend()
            raise TimeoutError("Bridge A exceeded the 60-second test timeout")

        status = widget.ui.backendStatusLabel.text
        if not status.startswith("Backend healthy:"):
            raise AssertionError(status)
        report = widget.logic.findJsonReport(widget._backendOutputLines, "health")
        if not report or report.get("requestedDevice") != "cpu":
            raise AssertionError("Bridge A did not return explicit CPU health")
        return {
            "event": "passed",
            "status": status,
            "requestedDevice": report["requestedDevice"],
            "openvinoDevices": report["openvino"]["devices"],
        }
    finally:
        widget.cleanup()
        parent.deleteLater()
        slicer.app.processEvents()


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
