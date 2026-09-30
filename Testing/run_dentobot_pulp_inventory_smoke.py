"""Bounded FDI11 run audit, bulk creation and portable save/reload check."""

import json
from pathlib import Path
import sys
import traceback

import numpy as np
import slicer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "DENTOWorkflow/Resources/Python"))
from DENTOCaseBundle import extract_scene_mrb  # noqa: E402


SOURCE = Path("/workspace/data/Slicer_Saved/SampleStudy1/dentobot-case-13sept.dentocase")


def case_segmentation():
    return next(node for node in slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
                if node.GetSegmentation().GetSegmentIdBySegmentName("upper_right_central_incisor_fdi11"))


def run():
    slicer.util.selectModule("DENTOWorkflow")
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    temporary = Path(slicer.app.temporaryPath) / "pulp-inventory-smoke"
    temporary.mkdir(exist_ok=True)
    scene, _ = extract_scene_mrb(SOURCE, temporary)
    assert slicer.util.loadScene(str(scene), {"clear": True})
    slicer.app.processEvents()
    logic = widget.logic
    node = case_segmentation()
    tooth_id = node.GetSegmentation().GetSegmentIdBySegmentName("upper_right_central_incisor_fdi11")
    label = int(node.GetSegmentation().GetSegment(tooth_id).GetLabelValue())
    before = (slicer.util.arrayFromSegmentInternalBinaryLabelmap(node, tooth_id) == label).copy()
    assert logic.getPulpInventoryReport(node) is None
    report = logic.checkPulpInventory(node)
    row = next(item for item in report["rows"] if item["fdi"] == "11")
    assert row["status"] == "missing", row
    assert not logic.getPulpInventoryReport(node)["stale"]
    print("PULP_INVENTORY_AUDIT " + json.dumps(report["counts"]), flush=True)

    # Bound the geometry/persistence check to FDI11. The complete 28-tooth
    # audit above is real; this altered eligibility is a diagnostic fixture.
    for item in report["rows"]:
        if item["fdi"] != "11" and item["status"] == "missing":
            item.update(status="ambiguous", reason="excluded from focused FDI11 smoke")
    report["counts"]["missing"] = 1
    node.SetAttribute(logic.PULP_REPORT_ATTRIBUTE, json.dumps(report, sort_keys=True, separators=(",", ":")))

    result = logic.createMissingPulpCandidates(node)
    row = next(item for item in result["rows"] if item["fdi"] == "11")
    assert row["status"] == "created" and row["voxelCount"] == 52, row
    assert np.array_equal(before, slicer.util.arrayFromSegmentInternalBinaryLabelmap(node, tooth_id) == label)
    assert node.GetAttribute("DENTOBOT.ReviewState") == "Needs Correction"
    second = logic.createMissingPulpCandidates(node)
    assert second["createdCount"] == 0, second
    print("PULP_INVENTORY_BULK " + json.dumps({"created": result["createdCount"], "failed": result["failedCount"]}), flush=True)

    mrb = temporary / "checked.mrb"
    widget._saveSceneSnapshotToMrb(mrb)
    assert slicer.util.loadScene(str(mrb), {"clear": True})
    slicer.app.processEvents()
    reloaded = case_segmentation()
    saved = widget.logic.getPulpInventoryReport(reloaded)
    assert saved and not saved["stale"]
    assert next(item for item in saved["rows"] if item["fdi"] == "11")["pulpSegmentId"]
    print("PULP_INVENTORY_MRB_PASS", flush=True)

    bundle = temporary / "checked.dentocase"
    widget._createCaseBundle(bundle)
    widget._openCaseBundle(bundle)
    slicer.app.processEvents()
    packaged = widget.logic.getPulpInventoryReport(case_segmentation())
    assert packaged and not packaged["stale"]
    print("PULP_INVENTORY_DENTOCASE_PASS", flush=True)
    slicer.util.exit(0)


try:
    run()
except Exception:
    traceback.print_exc()
    slicer.util.exit(1)
