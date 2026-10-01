"""Owned async request waiting with a fake native API; no native/runtime proof."""
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "DENTOWorkflow/Resources/Python"))
import DENTOROS2Bridge as bridge


@pytest.mark.parametrize("terminal", ["ready", "error"])
def test_wait_pumps_then_consumes_once_and_releases(monkeypatch, terminal):
    events = []
    states = iter(["pending", terminal])
    node = SimpleNamespace(
        BeginMoveItTrajectoryFromState=lambda *args: events.append(("begin", args)) or "token",
        GetJointPlanStatus=lambda token: next(states),
        TakeJointPlanResult=lambda token: events.append(("take", token)) or "result",
        CancelJointPlan=lambda token: events.append(("cancel", token)),
    )
    monkeypatch.setitem(sys.modules, "slicer", SimpleNamespace(app=SimpleNamespace(processEvents=lambda: events.append("paint"))))
    monkeypatch.setattr(bridge, "get_ros2_logic", lambda: SimpleNamespace(Spin=lambda: events.append("spin")))
    monkeypatch.setattr(bridge.time, "sleep", lambda duration: events.append(("sleep", duration)))
    assert bridge._wait_for_native_joint_plan(node, ("group", 0.2), allowed_time=2, progress=lambda phase: events.append(phase), context_is_current=lambda: True) == "result"
    assert events[0] == ("begin", ("group", 0.2))
    assert events[-2:] == [("take", "token"), ("cancel", "token")]
    assert "paint" in events and "spin" in events and ("sleep", 0.05) in events


@pytest.mark.parametrize("reason", ["stale", "timeout", "cancelled", "unknown"])
def test_pending_failures_never_consume_a_result(monkeypatch, reason):
    events = []
    state = [True]
    clock = [0.0]
    def paint():
        state[0] = reason != "stale"
        clock[0] = 8.0
    node = SimpleNamespace(
        BeginMoveItTrajectoryFromState=lambda *args: "token",
        GetJointPlanStatus=lambda token: reason if reason in {"cancelled", "unknown"} else "pending",
        TakeJointPlanResult=lambda token: pytest.fail("stale/error wait took result"),
        CancelJointPlan=lambda token: events.append(token),
    )
    monkeypatch.setitem(sys.modules, "slicer", SimpleNamespace(app=SimpleNamespace(processEvents=paint)))
    monkeypatch.setattr(bridge, "get_ros2_logic", lambda: None)
    monkeypatch.setattr(bridge.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(bridge.time, "sleep", lambda duration: None)
    with pytest.raises((RuntimeError, TimeoutError)):
        bridge._wait_for_native_joint_plan(node, (), allowed_time=2, progress=None, context_is_current=lambda: state[0])
    assert events == ["token"]


def test_missing_async_api_does_not_fall_back_to_blocking_plan(monkeypatch):
    monkeypatch.setitem(sys.modules, "slicer", SimpleNamespace())
    node = SimpleNamespace(PlanMoveItTrajectoryFromState=lambda *args: pytest.fail("blocking fallback"))
    with pytest.raises(RuntimeError, match="lacks responsive"):
        bridge._wait_for_native_joint_plan(node, (), allowed_time=2, progress=None, context_is_current=lambda: True)
