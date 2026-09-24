"""Verify the saved FDI11 derived pulp can persist its parent association."""

from pathlib import Path
import sys
import traceback

import slicer

sys.path.insert(0, "/workspace/ros2_ws/src/DentoBot/DENTOWorkflow/Resources/Python")
from DENTOCaseBundle import extract_scene_mrb  # noqa: E402

SOURCE = Path("/workspace/data/Slicer_Saved/SampleStudy1/SEPT24/pulp-testing-fdi11.dentocase")


def run():
    slicer.util.selectModule("DENTOWorkflow")
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    scene, _ = extract_scene_mrb(SOURCE, Path(slicer.app.temporaryPath) / "fdi11-parent-smoke")
    assert slicer.util.loadScene(str(scene), {"clear": True})
    slicer.app.processEvents()
    segmentation = next(
        node for node in slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
        if node.GetSegmentation().GetSegmentIdBySegmentName("upper_right_central_incisor_fdi11")
    )
    tooth_id = segmentation.GetSegmentation().GetSegmentIdBySegmentName("upper_right_central_incisor_fdi11")
    assert widget.logic.getSegmentationReviewState(segmentation) == "Reviewed"
    association = widget.logic.getTargetPulpAssociation(segmentation, tooth_id)
    assert association["validationState"] == "VALID"
    assert association["associationConfidence"] == "HIGH"
    assert association["targetFdiNumber"] == "11"
    pulp = next(record for record in widget.logic.getSegmentationReviewRecords(segmentation)
                if record["segmentId"] == association["pulpSegmentId"])
    assert pulp["canonicalName"] == "Pulp_FDI11"
    assert pulp["parentToothSegmentIds"] == [tooth_id]
    print("FDI11_PARENT_ASSOCIATION_PASS", flush=True)
    slicer.util.exit(0)


try:
    run()
except Exception:
    traceback.print_exc()
    slicer.util.exit(1)
