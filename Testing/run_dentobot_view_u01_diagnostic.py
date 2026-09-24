"""Display-only first-transition probe for VIEW-U-01."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import time

import qt
import slicer

sys.path.insert(0, '/workspace/ros2_ws/src/DentoBot/DENTOWorkflow/Resources/Python')
from DENTOROS2Bridge import shutdown_slicer_adapter

PACKAGE = Path('/workspace/data/Slicer_Saved/SampleStudy1/FDI21-31-headless-verified-sep22-step6a.dentocase')


def events(seconds=0.25):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def set_tree_item(widget, wanted, checked):
    widget._updateWorkflowViewControls()
    tree = widget._workflowAdvancedTree
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount)]
    while stack:
        item = stack.pop()
        if str(item.data(0, qt.Qt.UserRole) or '') == wanted:
            item.setCheckState(0, qt.Qt.Checked if checked else qt.Qt.Unchecked)
            events()
            return
        stack.extend(item.child(i) for i in range(item.childCount()))
    raise RuntimeError('view item missing: ' + wanted)


def record(label, widget):
    source = widget._parameterNode.teethSegmentation
    rows = []
    for node in slicer.util.getNodesByClass('vtkMRMLSegmentationNode'):
        display = node.GetDisplayNode()
        if display is None:
            continue
        segmentation = node.GetSegmentation()
        segment_ids = [segmentation.GetNthSegmentID(i) for i in range(segmentation.GetNumberOfSegments())]
        rows.append({
            'id': node.GetID(), 'name': node.GetName(), 'source': node is source,
            'parentTransform': node.GetTransformNodeID(),
            'visibility': bool(display.GetVisibility()),
            'visibility2D': bool(display.GetVisibility2D()),
            'visibility3D': bool(display.GetVisibility3D()),
            'segments': [{'id': sid, 'visible': bool(display.GetSegmentVisibility(sid)),
                          'visible2D': bool(display.GetSegmentVisibility2DFill(sid)
                                            or display.GetSegmentVisibility2DOutline(sid)),
                          'visible3D': bool(display.GetSegmentVisibility3D(sid))}
                         for sid in segment_ids],
        })
    models = []
    for node in slicer.util.getNodesByClass('vtkMRMLModelNode'):
        display = node.GetDisplayNode()
        if display is not None and display.GetVisibility():
            models.append({'id': node.GetID(), 'name': node.GetName(),
                           'parentTransform': node.GetTransformNodeID(),
                           'visibility2D': bool(display.GetVisibility2D()),
                           'visibility3D': bool(display.GetVisibility3D())})
    print('VIEW_U01_SNAPSHOT ' + json.dumps({'transition': label, 'nodes': rows,
                                              'visibleModels': models}), flush=True)
    source_row = next(row for row in rows if row['source'])
    for dimension in ('2D', '3D'):
        if source_row['visibility'] and source_row['visibility' + dimension] and any(
            seg['visible'] and seg['visible' + dimension] for seg in source_row['segments']
        ):
            raise RuntimeError('FIRST_SOURCE_GHOST ' + label + ' ' + dimension)


def run():
    if not PACKAGE.is_file():
        raise RuntimeError('missing package')
    slicer.util.selectModule('DENTOWorkflow')
    events(1)
    widget = slicer.util.getModuleWidget('DENTOWorkflow')
    widget._applyDENTOBOTGuiMode('legacy', persist=False)
    widget._openCaseBundle(PACKAGE)
    events(0.8)
    record('restore', widget)
    widget._setWorkflowStage(10, ensureVisible=False)
    events()
    record('step6_navigation', widget)
    widget._applyStep6RecommendedView()
    events()
    record('step6_recommended', widget)
    widget._setWorkflowStage(4, ensureVisible=False)
    events()
    record('step4a_navigation', widget)
    widget._applyWorkflowViewPreset('recommended', updateStatus=False)
    events()
    record('step4a_recommended', widget)
    widget._updatePlanning()
    combo = widget.ui.targetToothComboBox
    current = int(combo.currentIndex)
    target_index = next(
        (i for i in range(combo.count)
         if i != current and 'FDI 31' in str(combo.itemText(i))),
        -1,
    )
    if target_index < 0:
        raise RuntimeError('FDI31 target choice missing: ' + str(
            [str(combo.itemText(i)) for i in range(combo.count)]
        ))
    combo.setCurrentIndex(target_index)
    events(0.4)
    record('target_change_fdi31', widget)
    widget._applyWorkflowViewPreset('teeth_all_both', updateStatus=False)
    events()
    record('step4a_teeth_all_both', widget)
    if not all(
        node.GetDisplayNode().GetVisibility2D()
        for node in (widget._parameterNode.step6FixedUpperAnatomy,
                     widget._parameterNode.step6MovingLowerAnatomy)
    ):
        raise RuntimeError('opened upper/lower teeth were not shown in 2D')
    widget.onOpenViewControlsPalette()
    widget._setWorkflowStage(10, ensureVisible=False)
    fixed = widget._parameterNode.step6FixedUpperAnatomy
    set_tree_item(widget, 'node:step6FixedUpperAnatomy', False)
    if fixed.GetDisplayNode().GetVisibility():
        raise RuntimeError('custom hide of derived anatomy was overridden')
    set_tree_item(widget, 'node:step6FixedUpperAnatomy', True)
    if not fixed.GetDisplayNode().GetVisibility():
        raise RuntimeError('custom show of derived anatomy failed')
    widget._setWorkflowStage(4, ensureVisible=False)
    source = widget._parameterNode.teethSegmentation
    wanted = next(key for key, entry in widget._workflowViewEntriesByKey.items()
                  if entry.get('segmentationNode') is source
                  and entry.get('anatomyGroup') in {'upper_pulp', 'lower_pulp'})
    set_tree_item(widget, wanted, True)
    record('custom_source_pulp', widget)
    widget._restoreWorkflowViewState()
    events()
    record('view_restore', widget)
    widget._applyDENTOBOTGuiMode('shell', persist=False)
    widget._setWorkflowStage(4, ensureVisible=False)
    widget._applyWorkflowViewPreset('teeth_all_both', updateStatus=False)
    events()
    record('new_gui_teeth_all_both', widget)
    with tempfile.TemporaryDirectory(prefix='view-u01-') as directory:
        saved = Path(directory) / 'view-u01.dentocase'
        widget._createCaseBundle(saved)
        widget._openCaseBundle(saved)
        events(0.5)
        record('save_reopen', widget)
    print('VIEW_U01_DIAGNOSTIC_COMPLETE', flush=True)


status = 0
try:
    run()
except Exception as exc:
    print('VIEW_U01_DIAGNOSTIC_FAILED ' + type(exc).__name__ + ': ' + str(exc), flush=True)
    status = 1
finally:
    shutdown_slicer_adapter()
    slicer.util.exit(status)
