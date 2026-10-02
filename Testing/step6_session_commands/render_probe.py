# Render attribution for slow idle Spins (operator 2026-10-03 speed question):
# count real renders per view, find which MRML nodes change between renders,
# and re-time Spin while rendering is held paused (display only).
import collections as _collections
import time as _time

bridge_module = mod("DENTOROS2Bridge")
ros_logic = bridge_module.get_ros2_logic()
layout = slicer.app.layoutManager()
renders = _collections.Counter()
render_ms = _collections.defaultdict(float)
observers = []
starts = {}


def _watch_view(name, render_window):
    def on_start(_caller, _event, key=name):
        starts[key] = _time.monotonic()

    def on_end(_caller, _event, key=name):
        renders[key] += 1
        render_ms[key] += 1000 * (_time.monotonic() - starts.get(key, _time.monotonic()))

    observers.append((render_window, render_window.AddObserver("StartEvent", on_start)))
    observers.append((render_window, render_window.AddObserver("EndEvent", on_end)))


for index in range(layout.threeDViewCount):
    _watch_view(f"3d{index}", layout.threeDWidget(index).threeDView().renderWindow())
for name in layout.sliceViewNames():
    _watch_view(f"slice-{name}", layout.sliceWidget(name).sliceView().renderWindow())


def _all_mtimes():
    scene = slicer.mrmlScene
    return {
        scene.GetNthNode(i).GetID(): scene.GetNthNode(i).GetMTime()
        for i in range(scene.GetNumberOfNodes())
        if scene.GetNthNode(i) is not None
    }


def _spins(count, paused):
    timings = []
    changed_slow = _collections.Counter()
    if paused:
        slicer.app.pauseRender()
    try:
        for _ in range(count):
            before = _all_mtimes()
            started = _time.monotonic()
            ros_logic.Spin()
            duration = _time.monotonic() - started
            after = _all_mtimes()
            if duration > 0.05:
                for node_id, mtime in after.items():
                    if before.get(node_id) != mtime:
                        node = slicer.mrmlScene.GetNodeByID(node_id)
                        changed_slow[f"{node.GetClassName()}:{node.GetName()}"] += 1
            timings.append(duration)
            _time.sleep(0.002)
    finally:
        if paused:
            resume_started = _time.monotonic()
            slicer.app.resumeRender()
            resume_ms = 1000 * (_time.monotonic() - resume_started)
        else:
            resume_ms = None
    timings.sort()
    return {
        "median_ms": round(1000 * timings[len(timings) // 2], 2),
        "p90_ms": round(1000 * timings[int(len(timings) * 0.9)], 2),
        "slow_count": sum(1 for t in timings if t > 0.05),
        "total_ms": round(1000 * sum(timings), 1),
        "resume_render_ms": resume_ms,
        "renders": dict(renders),
        "render_ms": {k: round(v, 1) for k, v in render_ms.items()},
        "changed_nodes_in_slow_spins": changed_slow.most_common(20),
    }


try:
    normal = _spins(120, paused=False)
    renders.clear()
    render_ms.clear()
    paused = _spins(120, paused=True)
finally:
    for render_window, tag in observers:
        render_window.RemoveObserver(tag)
result = {
    "scene_nodes": slicer.mrmlScene.GetNumberOfNodes(),
    "normal": normal,
    "render_paused": paused,
}
