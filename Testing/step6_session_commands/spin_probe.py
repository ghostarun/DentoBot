# Idle ROS Spin attribution (speed question, operator 2026-10-03): time each
# Spin with no guard command outstanding and record which ROS/transform MRML
# nodes it modified, so a slow Spin can be tied to the message that caused it.
import collections as _collections
import time as _time

bridge_module = mod("DENTOROS2Bridge")
ros_logic = bridge_module.get_ros2_logic()
watched_prefixes = ("vtkMRMLROS2", "vtkMRMLTransformNode", "vtkMRMLLinearTransformNode")


def _watched():
    nodes = {}
    for index in range(slicer.mrmlScene.GetNumberOfNodes()):
        node = slicer.mrmlScene.GetNthNode(index)
        if node is not None and node.GetClassName().startswith(watched_prefixes):
            nodes[node.GetID()] = node
    return nodes


nodes = _watched()
labels = {node_id: f"{node.GetClassName()}:{node.GetName()}" for node_id, node in nodes.items()}
spins = []
for _ in range(150):
    before = {node_id: node.GetMTime() for node_id, node in nodes.items()}
    started = _time.monotonic()
    ros_logic.Spin()
    duration = _time.monotonic() - started
    changed = sorted(labels[node_id] for node_id, node in nodes.items() if node.GetMTime() != before[node_id])
    spins.append((duration, changed))
    _time.sleep(0.002)

slow = [s for s in spins if s[0] > 0.05]
fast = [s for s in spins if s[0] <= 0.05]


def _counts(group):
    counter = _collections.Counter()
    for _duration, changed in group:
        counter.update(changed)
    return counter.most_common(25)


durations = sorted(s[0] for s in spins)
result = {
    "watched_nodes": len(nodes),
    "spins": len(spins),
    "slow_count": len(slow),
    "spin_ms": {
        "median": round(1000 * durations[len(durations) // 2], 2),
        "p90": round(1000 * durations[int(len(durations) * 0.9)], 2),
        "max": round(1000 * durations[-1], 2),
        "slow_mean": round(1000 * sum(s[0] for s in slow) / max(len(slow), 1), 2),
    },
    "changed_in_slow_spins": _counts(slow),
    "changed_in_fast_spins": _counts(fast),
    "fast_spins_with_any_change": sum(1 for s in fast if s[1]),
    "sequence_ms_and_change_count": [(round(1000 * d, 1), len(c)) for d, c in spins[:60]],
}
