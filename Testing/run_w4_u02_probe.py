"""Display-only probe of current smooth/native modes on the supplied case."""
import sys
import time
import slicer
sys.path.insert(0, '/workspace/ros2_ws/src/DentoBot/DENTOWorkflow/Resources/Python')
from DENTOROS2Bridge import shutdown_slicer_adapter

status = 0
try:
    slicer.util.selectModule('DENTOWorkflow')
    end = time.monotonic() + 0.5
    while time.monotonic() < end:
        slicer.app.processEvents()
        time.sleep(0.01)
    widget = slicer.util.getModuleWidget('DENTOWorkflow')
    widget._openCaseBundle('/workspace/data/Slicer_Saved/SampleStudy1/FDI21-31-headless-verified-sep22-step6a.dentocase')
    parameter = widget._parameterNode
    logic = widget.logic
    for name, node in (
        ('source', parameter.teethSegmentation),
        ('fixed', parameter.step6FixedUpperAnatomy),
        ('moving', parameter.step6MovingLowerAnatomy),
    ):
        segmentation = node.GetSegmentation()
        display = node.GetDisplayNode()
        print('W4_MODE', name,
              'binary', segmentation.ContainsRepresentation(logic.SEGMENTATION_BINARY_LABELMAP_REPRESENTATION),
              'surface', segmentation.ContainsRepresentation(logic.SEGMENTATION_CLOSED_SURFACE_REPRESENTATION),
              'reported', logic.getSegmentation2DRenderingMode(node),
              'actual', display.GetDisplayRepresentationName2D(), flush=True)
    for name, volume in (('source', parameter.inputVolume),
                         ('fixed', parameter.caseFoundationFixedUpperVolume),
                         ('moving', parameter.caseFoundationMovingLowerVolume)):
        print('W4_VOLUME', name, bool(volume),
              logic.getScalarVolumeInterpolation(volume) if volume else None,
              flush=True)
    node = parameter.step6MovingLowerAnatomy
    logic.setSegmentation2DRenderingMode(node, logic.SEGMENTATION_2D_RENDERING_MODE_NATIVE)
    print('W4_MOVING_OFF', 'reported', logic.getSegmentation2DRenderingMode(node),
          'actual', node.GetDisplayNode().GetDisplayRepresentationName2D(), flush=True)
    assert node.GetDisplayNode().GetDisplayRepresentationName2D() == logic.SEGMENTATION_BINARY_LABELMAP_REPRESENTATION
    control = widget._viewSmoothDisplayCheckBox
    assert control.objectName == 'viewSmoothDisplayCheckBox'
    widget._syncViewSmoothDisplayControl()
    assert control.checked is False
    widget.onViewSmoothDisplayToggled(False)
    for segmentNode in (parameter.teethSegmentation, parameter.step6FixedUpperAnatomy, parameter.step6MovingLowerAnatomy):
        assert segmentNode.GetDisplayNode().GetDisplayRepresentationName2D() == logic.SEGMENTATION_BINARY_LABELMAP_REPRESENTATION
    widget.onViewSmoothDisplayToggled(True)
    for segmentNode in (parameter.teethSegmentation, parameter.step6FixedUpperAnatomy, parameter.step6MovingLowerAnatomy):
        assert segmentNode.GetDisplayNode().GetDisplayRepresentationName2D() == logic.SEGMENTATION_CLOSED_SURFACE_REPRESENTATION
    for volume in (parameter.inputVolume, parameter.caseFoundationFixedUpperVolume, parameter.caseFoundationMovingLowerVolume):
        assert logic.getScalarVolumeInterpolation(volume)
    assert control.checked
    print('W4_ALL_STEPS_TOGGLE_PASS', flush=True)
    print('W4_PROBE_COMPLETE', flush=True)
except Exception as exc:
    status = 1
    print('W4_PROBE_FAIL', type(exc).__name__, str(exc), flush=True)
finally:
    shutdown_slicer_adapter()
    slicer.util.exit(status)
