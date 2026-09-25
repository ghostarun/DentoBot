"""Serialized, simulation-only Step 6.1 Connect responsiveness probe."""

import sys
import time
import traceback
from pathlib import Path
import os
import cProfile
import io
import pstats

import qt
import slicer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "DENTOWorkflow/Resources/Python"))
from DENTOROS2Bridge import ROS2_ROBOT_NAME, find_ros2_robot_by_name, shutdown_slicer_adapter

CASE = "/workspace/data/Slicer_Saved/SampleStudy1/FDI21-31-headless-verified-sep22-step6a.dentocase"


def run():
    ticks = []
    timer = qt.QTimer()
    timer.setInterval(250)
    timer.connect("timeout()", lambda: ticks.append(time.monotonic()))
    slicer.util.selectModule("DENTOWorkflow")
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    refresh_times = []
    profile_refresh = [False]
    if os.environ.get("DENTOBOT_PERF_PROFILE_CONNECT_REFRESH") == "1":
        original_refresh = widget._updateFromParameterNodeOnce
        def timed_refresh():
            begun = time.perf_counter()
            try:
                if profile_refresh[0] and os.environ.get("DENTOBOT_PERF_CPROFILE_CONNECT_REFRESH") == "1":
                    profiler = cProfile.Profile()
                    try:
                        return profiler.runcall(original_refresh)
                    finally:
                        report = io.StringIO()
                        pstats.Stats(profiler, stream=report).sort_stats("cumulative").print_stats(25)
                        print("CONNECT_REFRESH_PROFILE", report.getvalue(), flush=True)
                return original_refresh()
            finally:
                refresh_times.append(round(time.perf_counter() - begun, 3))
        widget._updateFromParameterNodeOnce = timed_refresh
    widget._openCaseBundle(CASE)
    widget._setWorkflowStage(10, ensureVisible=False)
    node = widget._parameterNode
    logic = widget.logic
    registry = logic.syncDentoCaseTrajectoryRegistry(node)
    branch_id = str(registry["selected_branch_id"] or "")
    assert branch_id and branch_id in registry["prepared_branches"]
    logic.activateDentoCasePreparedBranch(node, branch_id)
    logic.importStep6PlanningContext(node)
    assert logic.evaluateCaseFoundationEligibility(node)["pose"]["eligible"]
    result = widget._robotWorkflowFacade.loadRobot()
    assert result.success, result.message
    if not logic.evaluateCaseFoundationEligibility(node)["base"]["eligible"]:
        result = widget._robotWorkflowFacade.lockBase()
        assert result.success, result.message
    print("CONNECT_PREFLIGHT", {
        "foundation": logic.evaluateCaseFoundationEligibility(node),
        "branch": logic.evaluatePreparedBranchEligibility(node),
        "imported": bool(node.step6PlanningContextImported),
        "local_robot": bool(logic.robotModelNodes()),
    }, flush=True)
    slicer.util.errorDisplay = lambda message, *args, **kwargs: print(
        "CONNECT_ERROR", message, flush=True
    )
    slicer.util.warningDisplay = lambda message, *args, **kwargs: print(
        "CONNECT_WARNING", message, flush=True
    )
    refresh_times.clear()
    profile_refresh[0] = True
    ticks.clear()
    timer.start()
    started = time.monotonic()
    if os.environ.get("DENTOBOT_PERF_CPROFILE_CONNECT") == "1":
        profiler = cProfile.Profile()
        try:
            profiler.runcall(widget._onShellConnectRobot)
        finally:
            report = io.StringIO()
            pstats.Stats(profiler, stream=report).sort_stats("cumulative").print_stats(35)
            print("CONNECT_ACTION_PROFILE", report.getvalue(), flush=True)
    else:
        widget._onShellConnectRobot()
    elapsed = time.monotonic() - started
    profile_refresh[0] = False
    timer.stop()
    ros_robot = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
    goal_models = [
        ros_robot.GetNthNodeReference("goal_model", index)
        for index in range(ros_robot.GetNumberOfNodeReferences("goal_model"))
    ] if ros_robot is not None else []
    assert goal_models and all(model and model.GetDisplayNode() for model in goal_models), (
        "ROS robot goal models or their display nodes are missing"
    )
    audit = logic.collisionSceneAuditRecord(node)
    assert audit and audit.status == "Acknowledged", audit
    assert len(audit.object_records) == 31, len(audit.object_records)
    assert widget._robotWorkflowFacade.capabilities().planning_scene_synchronized
    copies = [
        model for model in slicer.util.getNodesByClass("vtkMRMLModelNode")
        if model.GetAttribute("DENTOBOT.CollisionAuditCopy") == "true"
    ]
    assert len(copies) == 31, len(copies)
    assert len(copies) == len(audit.object_records), (len(copies), len(audit.object_records))
    assert all(model.GetParentTransformNode() == node.robotBaseTransform for model in copies)
    max_gap = max((b - a for a, b in zip([started, *ticks], [*ticks, started + elapsed])), default=0.0)
    if refresh_times:
        print("CONNECT_REFRESH_TIMES", refresh_times, flush=True)
    if os.environ.get("DENTOBOT_PERF_PROFILE_CONNECT_REFRESH") == "1":
        assert not refresh_times, f"full parameter-node widget refreshes during connect: {refresh_times}"
    print("CONNECT_PROGRESS_PASS", {"seconds": round(elapsed, 3), "max_qt_gap": round(max_gap, 3), "objects": len(copies)}, flush=True)
    print("CONNECT_DISCONNECT_START", flush=True)
    ticks.clear()
    timer.start()
    disconnect_started = time.monotonic()
    widget._onShellDisconnectRobot()
    disconnect_elapsed = time.monotonic() - disconnect_started
    timer.stop()
    assert not widget._robotWorkflowFacade.capabilities().connected
    disconnect_gap = max((b - a for a, b in zip([disconnect_started, *ticks], [*ticks, disconnect_started + disconnect_elapsed])), default=0.0)
    print("CONNECT_DISCONNECT_PASS", {"seconds": round(disconnect_elapsed, 3), "max_qt_gap": round(disconnect_gap, 3)}, flush=True)


try:
    run()
except Exception:
    traceback.print_exc()
    status = 1
else:
    status = 0
finally:
    shutdown_slicer_adapter()
    slicer.app.exit(status)
