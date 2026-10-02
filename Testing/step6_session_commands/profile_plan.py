# Profile one Plan Guarded Approach on the Slicer main thread (speed question,
# operator 2026-10-03): where the guard round trip and the planning time go.
import cProfile as _cprofile
import io as _io
import pstats as _pstats
import time as _time

fc = mod("step6_full_chain_probe")
bridge_module = mod("DENTOROS2Bridge")
if facade.motionPlan is not None:
    facade.invalidateMotionPlan()
fc._enter_substep(widget, panel, fc.STEP6_PLANNING_SUBSTEP, _process_events)
widget._updateStep6PlanningUi()
if not panel.planApproachButton.enabled:
    raise RuntimeError("Plan Guarded Approach is disabled.")

# Idle ROS Spin cost with no guard command outstanding.
ros_logic = bridge_module.get_ros2_logic()
idle = []
for _ in range(100):
    started = _time.monotonic()
    ros_logic.Spin()
    idle.append(_time.monotonic() - started)
    _time.sleep(0.002)
idle.sort()

bridge_module.task_command_wait_stats(reset=True)
profiler = _cprofile.Profile(builtins=True)
started = _time.monotonic()
profiler.enable()
try:
    _modal_guarded_click(report, evidence_dir, run_id, panel.planApproachButton, "session-profile-plan")
    _wait_until(lambda: not bool(getattr(widget, "_workflowActionBusy", False)), 3600.0)
finally:
    profiler.disable()
elapsed = _time.monotonic() - started
profile_path = evidence_dir / "profile-plan.prof"
profiler.dump_stats(str(profile_path))


def _top(sort_key, count):
    buffer = _io.StringIO()
    _pstats.Stats(profiler, stream=buffer).sort_stats(sort_key).print_stats(count)
    return buffer.getvalue()


text_path = evidence_dir / "profile-plan.txt"
text_path.write_text(
    "== cumulative ==\n" + _top("cumulative", 70) + "\n== tottime ==\n" + _top("tottime", 50)
)
result = {
    "elapsed_sec": round(elapsed, 2),
    "plan_present": facade.motionPlan is not None,
    "status_text": str(panel.approachStatusLabel.text)[:300],
    "idle_spin_ms": {
        "median": round(1000 * idle[len(idle) // 2], 3),
        "p90": round(1000 * idle[int(len(idle) * 0.9)], 3),
        "max": round(1000 * idle[-1], 3),
    },
    "guard_wait_stats": bridge_module.task_command_wait_stats(),
    "profile": str(profile_path),
    "profile_text": str(text_path),
}
