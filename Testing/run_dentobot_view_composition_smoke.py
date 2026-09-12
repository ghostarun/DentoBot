"""Focused Slicer-native smoke for composable Views and stage interaction locks."""

from __future__ import annotations

import traceback
import os

import slicer
import vtk


def _cube_segment(segmentation_node, segment_id, name, center_x, color=None):
    source = vtk.vtkCubeSource()
    source.SetBounds(center_x - 1.0, center_x + 1.0, -1.0, 1.0, -1.0, 1.0)
    source.Update()
    segment = slicer.vtkSegment()
    segment.SetName(name)
    if color is not None:
        segment.SetColor(*color)
    segment.AddRepresentation(
        slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName(),
        source.GetOutput(),
    )
    segmentation_node.GetSegmentation().AddSegment(segment, segment_id)


def _segment_ids(segmentation_node):
    ids = vtk.vtkStringArray()
    segmentation_node.GetSegmentation().GetSegmentIDs(ids)
    return [ids.GetValue(index) for index in range(ids.GetNumberOfValues())]


def _assert_all_segment_visibility(segmentation_node, visible=True):
    display = segmentation_node.GetDisplayNode()
    expected = bool(visible)
    assert bool(display.GetVisibility()) is expected, (
        "aggregate visibility: " + str(display.GetVisibility())
    )
    assert bool(display.GetVisibility2D()) is expected, (
        "aggregate 2D visibility: " + str(display.GetVisibility2D())
    )
    assert bool(display.GetVisibility3D()) is expected, (
        "aggregate 3D visibility: " + str(display.GetVisibility3D())
    )
    for segment_id in _segment_ids(segmentation_node):
        assert bool(display.GetSegmentVisibility(segment_id)) is expected, (
            segment_id + " visibility: " + str(display.GetSegmentVisibility(segment_id))
        )
        assert bool(display.GetSegmentVisibility3D(segment_id)) is expected, (
            segment_id + " 3D visibility: " + str(display.GetSegmentVisibility3D(segment_id))
        )
        if hasattr(display, "GetSegmentVisibility2DFill"):
            assert bool(display.GetSegmentVisibility2DFill(segment_id)) is expected, (
                segment_id + " 2D fill visibility: "
                + str(display.GetSegmentVisibility2DFill(segment_id))
            )
        if hasattr(display, "GetSegmentVisibility2DOutline"):
            assert bool(display.GetSegmentVisibility2DOutline(segment_id)) is expected, (
                segment_id + " 2D outline visibility: "
                + str(display.GetSegmentVisibility2DOutline(segment_id))
            )


def _save_view_evidence(widget, stem):
    ui_path = f"/workspace/data/dentobot-runs/{stem}-ui.png"
    viewport_path = f"/workspace/data/dentobot-runs/{stem}-viewport.png"
    assert widget._uiWidget.grab().save(ui_path)
    layout_manager = slicer.app.layoutManager()
    three_d = layout_manager.threeDWidget(0).threeDView()
    three_d.show()
    three_d.forceRender()
    slicer.app.processEvents()
    viewport = three_d.grab()
    if viewport.isNull():
        # Off-screen Slicer layouts can expose a null Qt grab even after a
        # successful render.  Capture the render window directly so visual
        # evidence remains the actual 3D viewport rather than a UI fallback.
        capture = vtk.vtkWindowToImageFilter()
        capture.SetInput(three_d.renderWindow())
        capture.ReadFrontBufferOff()
        capture.Update()
        writer = vtk.vtkPNGWriter()
        writer.SetFileName(viewport_path)
        writer.SetInputConnection(capture.GetOutputPort())
        writer.Write()
    else:
        assert viewport.save(viewport_path)
    assert os.path.isfile(viewport_path)
    return ui_path, viewport_path


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
    # Model a reviewed DENTOBOT run so the production inspection selector
    # treats this fixture exactly like the operator's selected result.
    segmentation.SetAttribute("DENTOBOT.BridgeOperation", "segment-teeth")
    segmentation.SetNodeReferenceID(logic.SOURCE_VOLUME_REFERENCE_ROLE, volume.GetID())
    segmentation.CreateDefaultDisplayNodes()
    _cube_segment(
        segmentation,
        "u11",
        "upper_central_incisor_fdi11",
        0.0,
        (0.95, 0.15, 0.15),
    )
    _cube_segment(
        segmentation,
        "l31",
        "lower_central_incisor_fdi31",
        4.0,
        (0.15, 0.85, 0.25),
    )
    _cube_segment(
        segmentation,
        "maxilla",
        "upper_jawbone",
        8.0,
        (0.20, 0.45, 1.00),
    )
    _cube_segment(
        segmentation,
        "mandible",
        "lower_jawbone",
        12.0,
        (0.95, 0.70, 0.10),
    )
    _cube_segment(
        segmentation,
        "pulp",
        "lower_central_incisor_pulp_fdi131",
        16.0,
        (0.85, 0.10, 0.85),
    )

    parameter_node = logic.getParameterNode()
    parameter_node.inputVolume = volume
    parameter_node.teethSegmentation = segmentation
    parameter_node.targetToothSegmentId = "u11"
    parameter_node.step6PlanningContextImported = True
    logic.setSegmentationReviewState(segmentation, "Reviewed")
    widget.setParameterNode(parameter_node)
    widget.selectInspectionContext(volume, segmentation)
    widget.ui.autoWorkflowViewCheckBox.checked = False

    # Regression: isolate/highlight state must never leak into the early
    # inspection stages.  Seed the exact failure observed by the operator
    # (only a pulp mask remains visible), then enter Stage 2 and apply its
    # recommended full-anatomy view.
    display = segmentation.GetDisplayNode()
    display.SetAllSegmentsVisibility(False)
    display.SetSegmentVisibility("pulp", True)
    display.SetSegmentVisibility3D("pulp", True)
    widget._setWorkflowStage(2, ensureVisible=False)
    print(
        "STAGE2_VISIBILITY",
        parameter_node.inspectedVolume.GetID() if parameter_node.inspectedVolume else None,
        parameter_node.inspectedSegmentation.GetID() if parameter_node.inspectedSegmentation else None,
        segmentation.GetID(),
        [(segment_id, bool(display.GetSegmentVisibility(segment_id)), bool(display.GetSegmentVisibility3D(segment_id))) for segment_id in _segment_ids(segmentation)],
    )
    _assert_all_segment_visibility(segmentation, True)
    stage2_evidence = _save_view_evidence(widget, "dentobot-case-views-stage2-full-anatomy")

    # Stage 3 is the dedicated Case Foundation view.  Before a committed
    # opening it still shows the complete source segmentation.
    display.SetAllSegmentsVisibility(False)
    display.SetSegmentVisibility("pulp", True)
    display.SetSegmentVisibility3D("pulp", True)
    widget._setWorkflowStage(3, ensureVisible=False)
    widget._applyWorkflowViewPreset("recommended")
    _assert_all_segment_visibility(segmentation, True)

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

    # Build the smallest real Case Foundation display fixture: the source
    # segmentation remains immutable, while the fixed-upper and transformed
    # moving-lower proxies copy the source segment colors.
    transform = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLLinearTransformNode",
        "[Case Foundation] Smoke jaw transform",
    )
    transform.SetAttribute("DENTOBOT.TransformRole", logic.STEP6_CASE_JAW_TRANSFORM_ROLE)
    smoke_matrix = vtk.vtkMatrix4x4()
    smoke_matrix.Identity()
    transform.SetMatrixTransformToParent(smoke_matrix)
    fixed = logic._createStep6DerivedAnatomy(
        parameter_node,
        segmentation,
        ("u11", "maxilla"),
        existingNode=None,
        name="[Case Foundation] Smoke fixed upper",
        role=logic.STEP6_FIXED_UPPER_ANATOMY_ROLE,
        mode="SmokeProxy",
    )
    moving = logic._createStep6DerivedAnatomy(
        parameter_node,
        segmentation,
        ("l31", "mandible", "pulp"),
        existingNode=None,
        name="[Case Foundation] Smoke moving lower",
        role=logic.STEP6_MOVING_LOWER_ANATOMY_ROLE,
        mode="SmokeProxy",
        transformNode=transform,
    )
    parameter_node.step6CaseJawTransform = transform
    parameter_node.step6FixedUpperAnatomy = fixed
    parameter_node.step6MovingLowerAnatomy = moving
    lower_surface = vtk.vtkCubeSource()
    lower_surface.SetBounds(10.0, 14.0, -1.0, 1.0, -1.0, 1.0)
    lower_surface.Update()
    lower_model = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLModelNode",
        "[Case Foundation] Smoke beige fallback",
    )
    lower_model.SetAttribute(
        "DENTOBOT.ModelRole", logic.STEP6_OPENED_LOWER_JAW_MODEL_ROLE
    )
    lower_model.SetAndObservePolyData(lower_surface.GetOutput())
    lower_model.SetAndObserveTransformNodeID(transform.GetID())
    lower_model.CreateDefaultDisplayNodes()
    lower_model.GetDisplayNode().SetVisibility3D(True)
    lower_model.GetDisplayNode().SetColor(0.90, 0.74, 0.56)
    parameter_node.step6OpenedLowerJawModel = lower_model
    original_freshness = logic.step6CaseJawOpeningFreshnessIssues
    logic.step6CaseJawOpeningFreshnessIssues = lambda _parameter: []
    try:
        widget._applyWorkflowViewPreset("recommended")
        assert not display.GetVisibility3D()
        assert fixed.GetDisplayNode().GetVisibility3D()
        assert moving.GetDisplayNode().GetVisibility3D()
        for source_id, derived_node in (
            ("u11", fixed),
            ("maxilla", fixed),
            ("l31", moving),
            ("mandible", moving),
            ("pulp", moving),
        ):
            source_color = tuple(
                float(value)
                for value in segmentation.GetSegmentation()
                .GetSegment(source_id)
                .GetColor()
            )
            derived_color = tuple(
                float(value)
                for value in derived_node.GetSegmentation()
                .GetSegment(source_id)
                .GetColor()
            )
            assert source_color == derived_color
        # The beige closed-surface fallback must not cover the vivid derived
        # segmentation when a moving-lower proxy is available.
        assert not lower_model.GetDisplayNode().GetVisibility3D()
        transformed_evidence = _save_view_evidence(
            widget, "dentobot-case-views-stage3-opened-anatomy"
        )
    finally:
        logic.step6CaseJawOpeningFreshnessIssues = original_freshness

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
        stage2_evidence,
        transformed_evidence,
    )


try:
    main()
except Exception:
    traceback.print_exc()
    slicer.util.exit(1)
else:
    slicer.util.exit(0)
