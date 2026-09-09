"""Slicer smoke for Step 3 consecutive-result naming and visibility."""

import json
import traceback
import numpy as np
import qt
import slicer


def run():
    try:
        slicer.util.selectModule("DENTOWorkflow")
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        volumes = []
        for index, name in enumerate(("preDental", "postDental")):
            volume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", name)
            volume.SetAttribute("DENTOBOT.CaseScan", "true")
            slicer.util.updateVolumeFromArray(volume, np.full((8, 9, 10), index + 1, dtype=np.int16))
            volumes.append(volume)
        nodes = []
        for index, name in enumerate(("pre run 1", "pre run 2", "post run 1")):
            node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", name)
            node.SetAttribute("DENTOBOT.BridgeOperation", "segment-teeth")
            source = volumes[0 if index < 2 else 1]
            node.SetNodeReferenceID(widget.logic.SOURCE_VOLUME_REFERENCE_ROLE, source.GetID())
            node.SetReferenceImageGeometryParameterFromVolumeNode(source)
            node.CreateDefaultDisplayNodes()
            node.GetSegmentation().AddEmptySegment("tooth", "Tooth")
            nodes.append(node)
        parameter = widget._parameterNode
        parameter.inputVolume = volumes[0]
        parameter.teethSegmentation = nodes[0]
        trajectory = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsLineNode", "Existing planning intent")
        parameter.trajectoryLine = trajectory
        widget._setWorkflowStage(3)
        for index in (2, 0, 1, 2):
            source = volumes[0 if index < 2 else 1]
            widget.ui.inputVolumeSelector.setCurrentNode(source)
            widget.ui.reviewSegmentationSelector.setCurrentNode(nodes[index])
            widget.onApplyRecommendedWorkflowView()
            assert parameter.inspectedVolume == source, "wrong inspected scan"
            assert parameter.inspectedSegmentation == nodes[index], "wrong inspected run"
            for composite in slicer.util.getNodesByClass("vtkMRMLSliceCompositeNode"):
                assert composite.GetBackgroundVolumeID() == source.GetID(), "wrong actual slice background"
            assert [bool(n.GetDisplayNode().GetVisibility()) for n in nodes] == [i == index for i in range(3)], "run isolation failed"
            assert parameter.teethSegmentation == nodes[0], "inspection changed planning authority"
            assert parameter.trajectoryLine == trajectory, "inspection changed trajectory"
        widget.enterComparison(volumes[0], nodes[0])
        assert widget._comparisonState is not None, "comparison did not activate"
        composites = list(slicer.util.getNodesByClass("vtkMRMLSliceCompositeNode"))
        assert len(composites) >= 2, "cross-scan comparison needs two slice viewers"
        assert composites[0].GetBackgroundVolumeID() == volumes[1].GetID(), "active comparison source missing"
        assert composites[1].GetBackgroundVolumeID() == volumes[0].GetID(), "reference comparison source missing"
        widget.exitComparison()
        assert widget._comparisonState is None, "comparison did not restore"
        for composite in composites:
            assert composite.GetBackgroundVolumeID() == volumes[1].GetID(), "inspection context not restored"
        print("DENTOBOT_SEGMENTATION_RUNS_PASS " + json.dumps({"names": [node.GetName() for node in nodes]}), flush=True)
        slicer.util.exit(0)
    except Exception as exc:
        traceback.print_exc()
        print("DENTOBOT_SEGMENTATION_RUNS_FAIL " + json.dumps({"error": str(exc)}), flush=True)
        slicer.util.exit(1)


qt.QTimer.singleShot(0, run)
