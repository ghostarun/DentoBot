"""Read-only fresh-process check of the supplied FDI11 Step 6 package."""

import sys

import slicer

sys.path.insert(0, "/workspace/ros2_ws/src/DentoBot/DENTOWorkflow/Resources/Python")


def run():
    slicer.util.selectModule("DENTOWorkflow")
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget._openCaseBundle(
        "/workspace/data/Slicer_Saved/SampleStudy1/SEPT24/fdi11_step6.dentocase"
    )
    node = widget._parameterNode
    print("FDI11_RESTORE_STATE", int(widget.ui.workflowStageComboBox.currentIndex),
          widget.logic.step6CaseJawOpeningFreshnessIssues(node),
          widget.logic.evaluateCaseFoundationEligibility(node)["pose"], flush=True)
    assert node.step6CaseJawPreparationMode == "CaseFoundationCurrent"
    assert not widget.logic.step6CaseJawOpeningFreshnessIssues(node)
    assert int(widget.ui.workflowStageComboBox.currentIndex) == 10
    assert node.step6CaseJawTransform is not None
    source = node.teethSegmentation.GetDisplayNode()
    assert not source.GetVisibility3D() and not source.GetVisibility2D()
    for opened in (node.step6FixedUpperAnatomy, node.step6MovingLowerAnatomy):
        assert opened is not None and opened.GetDisplayNode().GetVisibility3D()
    print("FDI11_STEP6_RESTORE_PASS", flush=True)


try:
    run()
except Exception:
    import traceback

    traceback.print_exc()
    slicer.app.exit(1)
else:
    slicer.app.exit(0)
