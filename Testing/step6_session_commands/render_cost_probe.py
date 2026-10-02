# Why one idle 3D frame costs ~200 ms and what requests it (operator
# 2026-10-03 speed question). Display-only experiments; settings restored.
import time as _time

bridge_module = mod("DENTOROS2Bridge")
ros_logic = bridge_module.get_ros2_logic()
layout = slicer.app.layoutManager()
view = layout.threeDWidget(0).threeDView()
view_node = view.mrmlViewNode()
render_window = view.renderWindow()

# 1. tf lookup transform events during idle spins, and whether the matrix changed.
import vtk as _vtk

lookup_stats = {}
tags = []
for node in slicer.util.getNodesByClass("vtkMRMLROS2Tf2LookupNode"):
    record = {"events": 0, "changed": 0, "last": None}
    lookup_stats[node.GetName()] = record

    def on_transform(caller, _event, record=record):
        matrix = _vtk.vtkMatrix4x4()
        caller.GetMatrixTransformToParent(matrix)
        values = tuple(round(matrix.GetElement(r, c), 12) for r in range(4) for c in range(4))
        record["events"] += 1
        if record["last"] is not None and values != record["last"]:
            record["changed"] += 1
        record["last"] = values

    tags.append((node, node.AddObserver(slicer.vtkMRMLTransformableNode.TransformModifiedEvent, on_transform)))
started = _time.monotonic()
slicer.app.pauseRender()
try:
    while _time.monotonic() - started < 2.0:
        ros_logic.Spin()
        _time.sleep(0.002)
finally:
    slicer.app.resumeRender()
    for node, tag in tags:
        node.RemoveObserver(tag)
lookups = {name: {"events": r["events"], "matrix_changed": r["changed"]} for name, r in lookup_stats.items()}


# 2. Cost of one frame under the current settings and with display variations.
def _frame_ms(repeats=5):
    times = []
    for _ in range(repeats):
        t0 = _time.monotonic()
        render_window.Render()
        times.append(1000 * (_time.monotonic() - t0))
    times.sort()
    return round(times[len(times) // 2], 1)


visible_models = 0
visible_triangles = 0
transparent = 0
for display in slicer.util.getNodesByClass("vtkMRMLModelDisplayNode"):
    if not display.GetVisibility() or not display.GetVisibility3D():
        continue
    model = display.GetDisplayableNode()
    polydata = model.GetPolyData() if model is not None else None
    if polydata is None:
        continue
    visible_models += 1
    visible_triangles += polydata.GetNumberOfCells()
    if display.GetOpacity() < 1.0:
        transparent += 1

settings = {
    "render_window_size": list(render_window.GetSize()),
    "depth_peeling": bool(view_node.GetUseDepthPeeling()),
    "max_peels": view_node.GetMaximumNumberOfPeels() if hasattr(view_node, "GetMaximumNumberOfPeels") else None,
    "fxaa": bool(view_node.GetFXAA()) if hasattr(view_node, "GetFXAA") else None,
    "visible_models": visible_models,
    "visible_cells": visible_triangles,
    "transparent_models": transparent,
    "gl_renderer": render_window.ReportCapabilities().splitlines()[1:3],
}
frames = {"current": _frame_ms()}
depth = view_node.GetUseDepthPeeling()
try:
    view_node.SetUseDepthPeeling(not depth)
    frames["depth_peeling_toggled"] = _frame_ms()
finally:
    view_node.SetUseDepthPeeling(depth)
result = {"tf_lookups_2s": lookups, "render_settings": settings, "frame_ms": frames}
