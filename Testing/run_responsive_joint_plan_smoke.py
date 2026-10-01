"""One empty-scene plan-only SlicerROS2 probe; no case, command stream or execution."""
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

import qt
import slicer

root = Path(os.environ['DENTOBOT_CHECKOUT_ROOT'])
sys.path.insert(0, str(root / 'DENTOWorkflow/Resources/Python'))
import DENTOROS2Bridge as bridge

report = {'scope': 'empty-scene simulation plan-only', 'checkout': str(root)}
output = Path(os.environ['DENTOBOT_PLAN_SMOKE_OUTPUT'])
base = None
timer = qt.QTimer()
ticks = []
timer.setInterval(50)
timer.connect('timeout()', lambda: ticks.append(time.monotonic()))
code = 1
try:
    report['bridge_sha256'] = hashlib.sha256(Path(bridge.__file__).read_bytes()).hexdigest()
    deadline = time.monotonic() + 15
    ready = False
    while time.monotonic() < deadline:
        ready, error = bridge.ensure_slicer_ros2_runtime(require_stack=True)
        if ready:
            break
        slicer.app.processEvents()
        ros_logic = bridge.get_ros2_logic()
        if ros_logic is not None:
            ros_logic.Spin()
        time.sleep(.05)
    assert ready, error
    base = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLLinearTransformNode', 'PlanSmokeBase')
    robot, error = bridge.connect_dentobot_motion_control(
        base, open_motion_module=False, start_joint_command_stream=False)
    assert robot is not None, error
    logic = bridge.get_motion_control_logic()
    node = slicer.mrmlScene.GetNodeByID(logic.getParameterNode().motionControlNodeID)
    names = ('BeginMoveItTrajectoryFromState', 'GetJointPlanStatus', 'TakeJointPlanResult', 'CancelJointPlan')
    report['apis'] = {name: callable(getattr(node, name, None)) for name in names}
    assert all(report['apis'].values()), report['apis']
    report['native_library_maps'] = sorted(set(line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines() if 'libvtkSlicerROS2ModuleMRML.so' in line))
    assert report['native_library_maps'] and all('/tmp/dentobot-s6-u01-install/' in path for path in report['native_library_maps'])
    deadline = time.monotonic() + 10
    start = {}
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        bridge.get_ros2_logic().Spin()
        start = bridge.monitored_joint_positions_si()
        if start:
            break
        time.sleep(.05)
    assert start, 'No monitored five-joint state'
    goal = dict(start)
    goal[bridge.ROS2_JOINT_SI_ORDER[0]] += .05
    progress = []
    ticks.append(time.monotonic())
    timer.start()
    began = time.monotonic()
    result = bridge.plan_moveit_joint_goal(
        start_joint_positions_si=start, goal_joint_positions_si=goal,
        refresh_planning_scene=False, planning_attempts=1,
        allowed_planning_time_sec=3, responsive_wait=True,
        wait_progress=lambda text: progress.append(time.monotonic()),
        context_is_current=lambda: slicer.mrmlScene.GetNodeByID(node.GetID()) is node)
    ended = time.monotonic()
    timer.stop()
    ticks.append(ended)
    report.update(wall_seconds=ended-began, heartbeat_count=len(ticks)-2,
                  maximum_heartbeat_gap_seconds=max(b-a for a,b in zip(ticks,ticks[1:])),
                  progress_count=len(progress), planner_success=bool(result.success),
                  planner_message=str(result.message), native_message=node.GetLastJointPlanMessage())
    assert progress, 'Real async wait did not produce a progress callback'
    assert report['maximum_heartbeat_gap_seconds'] < 2, 'Main-thread stall exceeds focused 2s budget'
    assert 'timed out' not in report['planner_message'].lower(), report['planner_message']
    assert node.GetJointPlanStatus('joint-plan-1') == 'unknown', 'Completed request still owned'
    report['completed_reply_released'] = True
    report['outcome'] = 'PASS'
    code = 0
except Exception:
    report['outcome'] = 'FAIL'
    report['error'] = traceback.format_exc()
finally:
    timer.stop()
    try:
        if base is not None:
            ok, error = bridge.disconnect_dentobot_motion_control()
            assert ok, error
        bridge.shutdown_slicer_adapter()
        report['disconnect'] = 'PASS'
    except Exception:
        report['disconnect'] = traceback.format_exc()
        code = 1
    output.write_text(json.dumps(report, indent=2))
    print('RESPONSIVE_PLAN_SMOKE', json.dumps(report), flush=True)
    slicer.util.exit(code)
