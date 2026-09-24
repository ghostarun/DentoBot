"""Narrow approved check for reopening the saved FDI11 pulp .dentocase."""

import json
from pathlib import Path
import traceback

import numpy as np
import slicer

SOURCE = Path("/tmp/Slicer-/pulp-inventory-approved-restore/fdi11-checked.dentocase")


def run():
    assert SOURCE.is_file(), SOURCE
    slicer.util.selectModule("DENTOWorkflow")
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget._openCaseBundle(SOURCE)
    slicer.app.processEvents()
    node = next(node for node in slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
                if node.GetSegmentation().GetSegmentIdBySegmentName("upper_right_central_incisor_fdi11"))
    report = widget.logic.getPulpInventoryReport(node)
    assert report and not report["stale"], report and {"stale": report["stale"]}
    row = next(item for item in report["rows"] if item["fdi"] == "11")
    assert row["status"] == "candidate" and row["voxelCount"] == 52, row
    reference = widget.logic.getSegmentationSourceVolume(node)
    candidate = slicer.util.arrayFromSegmentBinaryLabelmap(node, row["pulpSegmentId"], reference)
    assert np.count_nonzero(candidate) == 52
    assert node.GetAttribute("DENTOBOT.ReviewState") == "Needs Correction"
    print("PULP_RESTORE_DENTOCASE_PASS " + json.dumps({"rows": len(report["rows"]), "fdi11Voxels": 52}), flush=True)
    slicer.util.exit(0)


try:
    run()
except Exception:
    traceback.print_exc()
    slicer.util.exit(1)
