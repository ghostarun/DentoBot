"""Read-only geometry diagnostic for the exact saved Step 6 case."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import slicer
import vtk


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
for path in (ROOT / "DENTOWorkflow/Resources/Python", ROOT / "DENTOWorkflow"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

PACKAGE = Path(
    "/workspace/data/Slicer_Saved/SampleStudy1/"
    "dentobot-case-step6x4.dentocase"
)


def run():
    slicer.util.selectModule("DENTOWorkflow")
    slicer.app.processEvents()
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget._applyDENTOBOTGuiMode("legacy", persist=False)
    widget._openCaseBundle(PACKAGE)
    slicer.app.processEvents()
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    parameter_node = widget._parameterNode
    logic = widget.logic
    final_model = parameter_node.finalPrintableTemplateModel
    final_summary = logic.getFinalPrintableTemplateSummary(final_model)
    trajectory = logic.step6TrajectorySummary(parameter_node)
    entry = [float(value) for value in trajectory["entryRas"]]
    target = [float(value) for value in trajectory["targetRas"]]
    direction = [target[index] - entry[index] for index in range(3)]
    length = math.sqrt(sum(value * value for value in direction))
    direction = [value / length for value in direction]
    standoff = float(parameter_node.step6ApproachStandoffMm)
    template_world = logic._step6TargetAttachedModelPolydataWorld(
        parameter_node,
        final_model,
    )
    implicit = vtk.vtkImplicitPolyDataDistance()
    implicit.SetInput(template_world)
    samples = []
    for index in range(81):
        progress = -standoff + (length + standoff) * index / 80.0
        point = [entry[axis] + progress * direction[axis] for axis in range(3)]
        samples.append(
            {
                "progressMm": progress,
                "signedCenterlineDistanceMm": float(
                    implicit.EvaluateFunction(point)
                ),
            }
        )
    reader = vtk.vtkSTLReader()
    reader.SetFileName(str(ROOT / "dentobot_description/meshes/burr.stl"))
    reader.Update()
    bounds = [0.0] * 6
    reader.GetOutput().GetBounds(bounds)
    params = json.loads(final_summary["parametersJson"])
    closest = min(samples, key=lambda item: abs(item["signedCenterlineDistanceMm"]))
    print(
        json.dumps(
            {
                "targetJaw": logic.step6TargetJaw(parameter_node),
                "entryRasMm": entry,
                "targetRasMm": target,
                "trajectoryLengthMm": length,
                "approachStandoffMm": standoff,
                "guideOuterDiameterMm": params.get("outerDiameterMm"),
                "guideInnerDiameterMm": params.get("innerDiameterMm"),
                "guideProcessingResolutionMm": params.get(
                    "processingResolutionMm"
                ),
                "burrStlBoundsMm": bounds,
                "burrStlExtentsMm": [
                    bounds[1] - bounds[0],
                    bounds[3] - bounds[2],
                    bounds[5] - bounds[4],
                ],
                "closestCenterlineSample": closest,
                "entryCenterlineSignedDistanceMm": min(
                    samples, key=lambda item: abs(item["progressMm"])
                )["signedCenterlineDistanceMm"],
                "samples": samples,
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )


try:
    run()
    slicer.util.exit(0)
except Exception as exc:
    print(
        f"DENTOBOT_GEOMETRY_DIAGNOSTIC_FAILED: {exc}",
        file=sys.stderr,
        flush=True,
    )
    slicer.util.exit(1)
