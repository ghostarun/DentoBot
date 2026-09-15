"""Save one production case copy after the opened-jaw display correction."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import time

import slicer
import vtk


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOCaseBundle import validate_case_bundle  # noqa: E402


SOURCE = Path(
    os.environ.get(
        "DENTOBOT_MASK_SOURCE",
        "/workspace/data/dentobot-runs/stage6-target-generation-fdi31-current-20260914-r2/FDI31/case.dentocase",
    )
)
OUTPUT = Path(
    os.environ.get(
        "DENTOBOT_MASK_OUTPUT",
        "/workspace/data/dentobot-runs/stage6-target-generation-fdi31-current-20260914-r2/FDI31/mask-visibility-fixed/case-mask-visibility-fixed.dentocase",
    )
)
REPORT = Path(
    os.environ.get(
        "DENTOBOT_MASK_SAVE_REPORT",
        "/workspace/data/dentobot-runs/stage6-target-generation-fdi31-current-20260914-r2/FDI31/mask-visibility-fixed/save-report.json",
    )
)


def process_events(seconds: float = 1.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def mask_metrics(parameter) -> dict[str, object]:
    source = parameter.teethSegmentation
    display = source.GetDisplayNode() if source else None
    segment_ids = vtk.vtkStringArray()
    if source:
        source.GetSegmentation().GetSegmentIDs(segment_ids)
    source_ids = [
        segment_ids.GetValue(index)
        for index in range(segment_ids.GetNumberOfValues())
    ]

    def snapshot_count(node) -> int:
        if node is None:
            return 0
        try:
            value = json.loads(
                node.GetAttribute("DENTOBOT.SourceSegmentVisibility3DJson")
                or "{}"
            )
        except (TypeError, json.JSONDecodeError):
            return 0
        return len(value) if isinstance(value, dict) else 0

    return {
        "sourceSegmentCount": len(source_ids),
        "sourceVisible3DCount": sum(
            bool(display.GetSegmentVisibility3D(segment_id))
            for segment_id in source_ids
        )
        if display
        else None,
        "fixedUpperSnapshotCount": snapshot_count(
            parameter.step6FixedUpperAnatomy
        ),
        "movingLowerSnapshotCount": snapshot_count(
            parameter.step6MovingLowerAnatomy
        ),
        "fixedUpperPresent": bool(parameter.step6FixedUpperAnatomy),
        "movingLowerPresent": bool(parameter.step6MovingLowerAnatomy),
        "jawTransformPresent": bool(parameter.step6CaseJawTransform),
    }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run() -> dict[str, object]:
    require(SOURCE.is_file(), f"source package is missing: {SOURCE}")
    require(not OUTPUT.exists(), f"refusing to overwrite output: {OUTPUT}")
    slicer.util.selectModule("DENTOWorkflow")
    process_events()
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    require(widget is not None and widget.logic is not None, "DENTOWorkflow is unavailable")
    widget._openCaseBundle(str(SOURCE))
    process_events()
    parameter = widget._parameterNode
    require(parameter is not None, "case parameter state did not restore")
    before_save = mask_metrics(parameter)
    require(
        before_save["sourceVisible3DCount"] == 0,
        f"source masks remain visible before save: {before_save}",
    )
    require(
        before_save["fixedUpperSnapshotCount"] == before_save["sourceSegmentCount"]
        and before_save["movingLowerSnapshotCount"] == before_save["sourceSegmentCount"],
        f"opened-jaw visibility snapshots are incomplete: {before_save}",
    )
    inspection = widget._createCaseBundle(str(OUTPUT))
    validate_case_bundle(inspection.path)
    after_save = {
        "path": str(inspection.path),
        "sha256": hashlib.sha256(inspection.path.read_bytes()).hexdigest(),
        "sizeBytes": inspection.path.stat().st_size,
    }
    report = {
        "status": "PASS",
        "source": str(SOURCE),
        "sourceSha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "output": after_save,
        "maskMetricsBeforeSave": before_save,
        "productionSerializer": "DENTOWorkflow.widget_case_backend._createCaseBundle",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("DENTOBOT_MASK_VISIBILITY_SAVE_PASS " + json.dumps(report, sort_keys=True), flush=True)
    slicer.util.exit(0)
    return report


try:
    run()
except Exception as exc:
    failure = {"status": "FAIL", "source": str(SOURCE), "output": str(OUTPUT), "error": str(exc)}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
    print("DENTOBOT_MASK_VISIBILITY_SAVE_FAIL " + json.dumps(failure, sort_keys=True), file=sys.stderr, flush=True)
    slicer.util.exit(1)
