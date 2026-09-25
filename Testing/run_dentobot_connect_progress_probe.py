"""Serialized, simulation-only Step 6.1 Connect responsiveness probe."""

import sys
import time
import traceback

import qt
import slicer

sys.path.insert(0, "/workspace/ros2_ws/src/DentoBot/DENTOWorkflow/Resources/Python")
from DENTOROS2Bridge import shutdown_slicer_adapter

CASE = "/workspace/data/Slicer_Saved/SampleStudy1/FDI21-31-headless-verified-sep22-step6a.dentocase"


def run():
    ticks = []
    timer = qt.QTimer()
    timer.setInterval(250)
    timer.connect("timeout()", lambda: ticks.append(time.monotonic()))
    slicer.util.selectModule("DENTOWorkflow")
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
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
    ticks.clear()
    timer.start()
    started = time.monotonic()
    widget._onShellConnectRobot()
    elapsed = time.monotonic() - started
    timer.stop()
    audit = logic.collisionSceneAuditRecord(node)
    assert audit and audit.status == "Acknowledged", audit
    assert widget._robotWorkflowFacade.capabilities().planning_scene_synchronized
    copies = [
        model for model in slicer.util.getNodesByClass("vtkMRMLModelNode")
        if model.GetAttribute("DENTOBOT.CollisionAuditCopy") == "true"
    ]
    assert len(copies) == len(audit.object_records), (len(copies), len(audit.object_records))
    assert all(model.GetParentTransformNode() == node.robotBaseTransform for model in copies)
    max_gap = max((b - a for a, b in zip([started, *ticks], [*ticks, started + elapsed])), default=0.0)
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
