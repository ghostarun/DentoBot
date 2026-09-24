"""The FDI11 case must open for Step 3A repair despite a stale saved pose."""

import json
import traceback

import slicer


try:
    slicer.util.selectModule("DENTOWorkflow")
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget._openCaseBundle(
        "/workspace/data/Slicer_Saved/SampleStudy1/SEPT24/pulp-testing-fdi11.dentocase"
    )
    parameter = widget._parameterNode
    state = widget.logic.evaluateCaseFoundationEligibility(parameter)
    assert parameter.inspectedSegmentation is not None
    assert state["pose"]["eligible"] is False, state
    assert state["pose"]["code"] == "STALE_MOUTH_OPENING", state
    assert parameter.robotBaseMountLocked
    print("FDI11_STALE_CASE_OPEN_PASS " + json.dumps({
        "pose": state["pose"], "base": state["base"],
        "baseLocked": bool(parameter.robotBaseMountLocked),
    }), flush=True)
    slicer.util.exit(0)
except Exception:
    traceback.print_exc()
    slicer.util.exit(1)
