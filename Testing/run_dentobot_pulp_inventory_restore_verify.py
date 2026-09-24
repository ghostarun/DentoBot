"""Approved focused check of the corrected pulp-report MRB/dentocase restore."""

import json
from pathlib import Path
import sys
import traceback

import numpy as np
import slicer

sys.path.insert(0, "/workspace/ros2_ws/src/DentoBot/DENTOWorkflow/Resources/Python")

SOURCE = Path("/tmp/Slicer-/pulp-inventory-smoke/checked.mrb")
OUTPUT = Path(slicer.app.temporaryPath) / "pulp-inventory-approved-restore"


def fdi11(node):
    tooth = node.GetSegmentation().GetSegmentIdBySegmentName("upper_right_central_incisor_fdi11")
    assert tooth
    return tooth


def selected_run():
    return next(node for node in slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
                if node.GetSegmentation().GetSegmentIdBySegmentName("upper_right_central_incisor_fdi11"))


def assert_candidate(logic, node, report):
    row = next(item for item in report["rows"] if item["fdi"] == "11")
    assert row["status"] == "candidate", row
    assert row["voxelCount"] == 52, row
    tooth = fdi11(node)
    reference = logic.getSegmentationSourceVolume(node)
    mask = slicer.util.arrayFromSegmentBinaryLabelmap(node, row["pulpSegmentId"], reference)
    tooth_mask = slicer.util.arrayFromSegmentBinaryLabelmap(node, tooth, reference)
    assert np.count_nonzero(mask) == 52
    assert np.count_nonzero(tooth_mask) == 3660
    assert not np.any((mask > 0) & (tooth_mask > 0))
    return row


def run():
    assert SOURCE.is_file(), SOURCE
    OUTPUT.mkdir(exist_ok=True)
    slicer.util.selectModule("DENTOWorkflow")
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    assert slicer.util.loadScene(str(SOURCE), {"clear": True})
    slicer.app.processEvents()
    widget.initializeParameterNode()
    node = selected_run()
    logic = widget.logic
    report = logic.checkPulpInventory(node)
    row = assert_candidate(logic, node, report)
    assert not logic.getPulpInventoryReport(node)["stale"]
    print("PULP_RESTORE_SOURCE " + json.dumps({"rows": len(report["rows"]), "fdi11": row["status"]}), flush=True)

    mrb = OUTPUT / "fdi11-checked.mrb"
    widget._saveSceneSnapshotToMrb(mrb)
    assert slicer.util.loadScene(str(mrb), {"clear": True})
    slicer.app.processEvents()
    widget.initializeParameterNode()
    node = selected_run()
    report = widget.logic.getPulpInventoryReport(node)
    assert report and not report["stale"], report and {"stale": report["stale"]}
    assert_candidate(widget.logic, node, report)
    print("PULP_RESTORE_MRB_PASS", flush=True)

    bundle = OUTPUT / "fdi11-checked.dentocase"
    widget._createCaseBundle(bundle)
    widget._openCaseBundle(bundle)
    slicer.app.processEvents()
    widget.initializeParameterNode()
    node = selected_run()
    report = widget.logic.getPulpInventoryReport(node)
    assert report and not report["stale"]
    assert_candidate(widget.logic, node, report)
    print("PULP_RESTORE_DENTOCASE_PASS", flush=True)
    slicer.util.exit(0)


try:
    run()
except Exception:
    traceback.print_exc()
    slicer.util.exit(1)
