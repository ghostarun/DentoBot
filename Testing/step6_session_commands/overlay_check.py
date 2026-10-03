# 6.3 display overlays (operator 2026-10-03): task-space box off by default,
# adjustable side and opacity, rose barrier at low opacity, Slicer view frame hidden.
fc = mod("step6_full_chain_probe")
fc._enter_substep(widget, panel, fc.STEP6_PLANNING_SUBSTEP, _process_events)
_process_events(0.3)


def _role_display(role):
    for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
        if node.GetAttribute("DENTOBOT.ModelRole") == role and node.GetDisplayNode():
            display = node.GetDisplayNode()
            bounds = [0.0] * 6
            node.GetRASBounds(bounds)
            return {
                "name": node.GetName(),
                "visible": bool(display.GetVisibility()),
                "opacity": round(display.GetOpacity(), 3),
                "color": [round(v, 3) for v in display.GetColor()],
                "size_mm": [round(bounds[1] - bounds[0], 2), round(bounds[3] - bounds[2], 2),
                            round(bounds[5] - bounds[4], 2)],
            }
    return None


view_frames = [bool(v.GetBoxVisible()) for v in slicer.util.getNodesByClass("vtkMRMLViewNode")]
defaults = {
    "task_box_checked": bool(panel.showTaskSpaceBoxCheckBox.checked),
    "task_box_side_mm": float(panel.taskSpaceBoxSideSpinBox.value),
    "task_box_opacity_pct": int(panel.taskSpaceBoxOpacitySlider.value),
    "barrier_opacity_pct": int(panel.mouthBarrierOpacitySlider.value),
    "task_box_model": _role_display("Step6TaskSpaceBox"),
    "barrier_model": _role_display("Step6MouthBarrierDisplay"),
    "slicer_view_frame_visible": view_frames,
}
_capture(report, evidence_dir, run_id, "session-overlay-defaults")
panel.showTaskSpaceBoxCheckBox.checked = True
_process_events(0.3)
shown = _role_display("Step6TaskSpaceBox")
_capture(report, evidence_dir, run_id, "session-overlay-task-box-200mm")
panel.taskSpaceBoxSideSpinBox.value = 120.0
panel.taskSpaceBoxOpacitySlider.value = 25
_process_events(0.3)
resized = _role_display("Step6TaskSpaceBox")
_capture(report, evidence_dir, run_id, "session-overlay-task-box-120mm-25pct")
panel.taskSpaceBoxSideSpinBox.value = 200.0
panel.taskSpaceBoxOpacitySlider.value = 10
panel.showTaskSpaceBoxCheckBox.checked = False
_process_events(0.3)
result = {
    "defaults": defaults,
    "shown": shown,
    "resized": resized,
    "hidden_again": _role_display("Step6TaskSpaceBox"),
    "status_label": str(panel.taskSpaceBoxStatusLabel.text),
}
