"""Focused Slicer-native smoke for composable Views and stage interaction locks."""

from __future__ import annotations

import traceback

import slicer
import vtk


def _cube_segment(segmentation_node, segment_id, name, center_x):
    source = vtk.vtkCubeSource()
    source.SetBounds(center_x - 1.0, center_x + 1.0, -1.0, 1.0, -1.0, 1.0)
    source.Update()
    segment = slicer.vtkSegment()
    segment.SetName(name)
    segment.AddRepresentation(
        slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName(),
        source.GetOutput(),
    )
    segmentation_node.GetSegmentation().AddSegment(segment, segment_id)


def main() -> None:
    slicer.mrmlScene.Clear(0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget.initializeParameterNode()
    logic = widget.logic

    volume = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLScalarVolumeNode",
        "Composable Views CBCT",
    )
    image = vtk.vtkImageData()
    image.SetDimensions(8, 8, 8)
    image.AllocateScalars(vtk.VTK_SHORT, 1)
    volume.SetAndObserveImageData(image)
    volume.CreateDefaultDisplayNodes()

    segmentation = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLSegmentationNode",
        "Composable Views anatomy",
    )
    segmentation.CreateDefaultDisplayNodes()
    _cube_segment(segmentation, "u11", "upper_central_incisor_fdi11", 0.0)
    _cube_segment(segmentation, "l31", "lower_central_incisor_fdi31", 4.0)
    _cube_segment(segmentation, "maxilla", "upper_jawbone", 8.0)
    _cube_segment(segmentation, "mandible", "lower_jawbone", 12.0)

    parameter_node = logic.getParameterNode()
    parameter_node.inputVolume = volume
    parameter_node.teethSegmentation = segmentation
    parameter_node.targetToothSegmentId = "u11"
    parameter_node.step6PlanningContextImported = True
    widget.setParameterNode(parameter_node)
    widget.ui.autoWorkflowViewCheckBox.checked = False
    widget._setWorkflowStage(3, ensureVisible=False)
    widget._applyWorkflowViewPreset("recommended")

    assert widget._workflowAnatomyComboBox is not None
    assert widget._workflowCbctComboBox is not None
    assert widget._workflowAdvancedTree is not None
    assert widget._workflowAdvancedTree.topLevelItemCount > 0
    assert widget._workflowAdvancedTree.minimumHeight >= 250
    assert segmentation.GetDisplayNode().GetSegmentVisibility("u11")
    assert segmentation.GetDisplayNode().GetSegmentVisibility("l31")
    widget._viewControlsTabWidget.currentIndex = (
        widget._viewControlsElementsTabIndex
    )
    widget._workflowViewAdvancedButton.collapsed = False
    widget._viewControlsPalette.resize(430, 720)
    widget._viewControlsPalette.show()
    slicer.app.processEvents()
    assert widget._workflowAdvancedTree.visible
    assert widget._workflowAdvancedTree.height > 0
    screenshot = (
        "/workspace/data/dentobot-runs/"
        "dentobot-composable-views-advanced.png"
    )
    assert widget._viewControlsPalette.grab().save(screenshot)

    from DENTOViewPresets import ViewComposition

    widget._applyWorkflowViewComposition(
        ViewComposition(
            anatomy_scope="upper_jaw_anatomy",
            anatomy_dimension="3d",
            cbct_mode="intensity_3d",
            anatomy_opacity=0.35,
        ),
        recommended=False,
        allowRendererCreation=True,
    )
    display = segmentation.GetDisplayNode()
    assert display.GetSegmentVisibility("u11")
    assert display.GetSegmentVisibility("maxilla")
    assert not display.GetSegmentVisibility("l31")
    assert not display.GetSegmentVisibility("mandible")
    assert abs(display.GetSegmentOpacity3D("u11") - 0.35) < 1e-6
    rendering_logic = slicer.modules.volumerendering.logic()
    renderer = rendering_logic.GetFirstVolumeRenderingDisplayNode(volume)
    assert renderer is not None and renderer.GetVisibility()

    boundary = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLMarkupsClosedCurveNode",
        "Step 5A boundary lock smoke",
    )
    boundary.SetAttribute("DENTOBOT.MarkupsRole", "TemplateSupportBoundary")
    boundary.SetLocked(False)
    boundary.SetSelectable(True)
    parameter_node.templateSupportBoundaryCurve = boundary
    robot_stage = len(widget._workflowStageEntries()) - 1
    widget._setWorkflowStage(robot_stage, ensureVisible=False)
    assert boundary.GetLocked()
    assert not boundary.GetSelectable()
    widget._applyWorkflowViewPreset("recommended")
    widget._workflowViewAdvancedButton.collapsed = True
    slicer.app.processEvents()
    assert widget._step6ViewContextWidget.visible
    assert "Scene: case" in widget._step6ViewContextLabel.text
    assert "mutually exclusive" in widget._step6ViewContextLabel.text
    robot_screenshot = (
        "/workspace/data/dentobot-runs/"
        "dentobot-robot-workspace-view.png"
    )
    assert widget._viewControlsPalette.grab().save(robot_screenshot)
    widget._setWorkflowStage(7, ensureVisible=False)
    assert not boundary.GetLocked()
    assert boundary.GetSelectable()

    widget.onRestoreWorkflowView()
    assert rendering_logic.GetFirstVolumeRenderingDisplayNode(volume) is None
    print(
        "DENTOBOT_COMPOSABLE_VIEWS_PASS",
        screenshot,
        robot_screenshot,
    )


try:
    main()
except Exception:
    traceback.print_exc()
    slicer.util.exit(1)
else:
    slicer.util.exit(0)
