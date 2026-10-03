# 6.3 run options (operator 2026-10-03): development fast mode off by default,
# depth peeling on by default; toggles reach the facade flag and every 3D view.
import slicer

fc = mod("step6_full_chain_probe")
fc._enter_substep(widget, panel, fc.STEP6_PLANNING_SUBSTEP, _process_events)
_process_events(0.3)


def _views():
    return [bool(v.GetUseDepthPeeling()) for v in slicer.util.getNodesByClass("vtkMRMLViewNode")]


defaults = {
    "fast_mode_checked": bool(panel.devFastModeCheckBox.checked),
    "facade_fast_mode": bool(facade._dev_first_complete_route),
    "depth_peeling_checked": bool(panel.depthPeelingCheckBox.checked),
    "views_depth_peeling": _views(),
    "group_visible": bool(panel.planningRunOptionsGroup.visible),
}
_capture(report, evidence_dir, run_id, "session-run-options-defaults")
panel.devFastModeCheckBox.checked = True
panel.depthPeelingCheckBox.checked = False
_process_events(0.3)
toggled = {"facade_fast_mode": bool(facade._dev_first_complete_route), "views_depth_peeling": _views()}
_capture(report, evidence_dir, run_id, "session-run-options-fast-no-peeling")
panel.devFastModeCheckBox.checked = False
panel.depthPeelingCheckBox.checked = True
_process_events(0.3)
result = {
    "defaults": defaults,
    "toggled": toggled,
    "restored": {"facade_fast_mode": bool(facade._dev_first_complete_route), "views_depth_peeling": _views()},
}
