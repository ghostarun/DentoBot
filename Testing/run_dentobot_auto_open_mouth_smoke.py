"""Headless Phase 3+4 AUTO open-mouth check on a reviewed segmentation scene.

Loads test1_post (or DENTOBOT_CASE_SOURCE). Does not require four manual TMJ
landmarks. Production path: AUTO propose incisors/arch/condyles → solve.

Marker: DENTOBOT_AUTO_OPEN_MOUTH_PASS
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

import slicer


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

SCENE_CANDIDATES = (
    os.environ.get("DENTOBOT_CASE_SOURCE", "").strip(),
    "/workspace/data/Slicer_Saved/SampleStudy1/test1_post.mrb",
    "/workspace/data/Slicer_Saved/SampleStudy1/test1_post.mrml",
    "/workspace/data/Slicer_Saved/study1/test1_post.mrb",
    "/workspace/data/Slicer_Saved/study1/test1_post.mrml",
    str(Path.home() / "dentobot/data/Slicer_Saved/SampleStudy1/test1_post.mrb"),
    "/home/light-tarun/dentobot/data/Slicer_Saved/SampleStudy1/test1_post.mrb",
)


def _existing_scene() -> Path:
    for candidate in SCENE_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():
            return path
    raise FileNotFoundError(
        "test1_post scene not found. Set DENTOBOT_CASE_SOURCE to the .mrb/.mrml path."
    )


def _pick_volume(nodes):
    named = [n for n in nodes if "post" in (n.GetName() or "").lower()]
    return (named or list(nodes))[0]


def _pick_segmentation(logic, nodes):
    reviewed = [
        n
        for n in nodes
        if logic.getSegmentationReviewState(n) == "Reviewed"
    ]
    if reviewed:
        return reviewed[0]
    named = [n for n in nodes if "post" in (n.GetName() or "").lower() or "seg" in (n.GetName() or "").lower()]
    return (named or list(nodes))[0]


def run() -> None:
    scene_path = _existing_scene()
    slicer.mrmlScene.Clear(0)
    if not slicer.util.loadScene(str(scene_path)):
        raise RuntimeError(f"Could not load scene: {scene_path}")

    slicer.util.selectModule("DENTOWorkflow")
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    logic = widget.logic
    parameter = widget._parameterNode
    volumes = list(slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"))
    segmentations = list(slicer.util.getNodesByClass("vtkMRMLSegmentationNode"))
    if not volumes or not segmentations:
        raise RuntimeError("Loaded scene has no volume or segmentation.")
    parameter.inputVolume = _pick_volume(volumes)
    parameter.teethSegmentation = _pick_segmentation(logic, segmentations)
    if logic.getSegmentationReviewState(parameter.teethSegmentation) != "Reviewed":
        logic.setSegmentationReviewState(parameter.teethSegmentation, "Reviewed")

    probe = logic.probeCaseFoundationArticulator(parameter, 28.0)
    if probe["hingeSource"] not in {
        "PATIENT_CONDYLES_SEGMENTED",
        "PATIENT_CONDYLES_ESTIMATED",
        "ARCH_INFERRED",
    }:
        raise AssertionError(
            f"AUTO path used non-production hinge_source={probe['hingeSource']}"
        )
    target = min(28.0, float(probe.get("profileMaxGapMm") or 28.0) - 0.2)
    if target <= float(probe.get("closedGapMm") or 0.0) + 1.0:
        target = float(probe["achievedGapMm"])
    parameter.step6CaseJawTargetGapMm = target
    _transform, _model, _gap, summary = logic.createOrUpdateStep6CaseJawOpening(
        parameter
    )
    hinge = str(summary.get("hingeSource") or "")
    if hinge not in {
        "PATIENT_CONDYLES_SEGMENTED",
        "PATIENT_CONDYLES_ESTIMATED",
        "ARCH_INFERRED",
    }:
        raise AssertionError(f"Commit used non-production hinge_source={hinge}")
    provenance = summary.get("articulatorProvenance") or {}
    if str(provenance.get("landmarkSource") or "") == "MANUAL_OVERRIDE":
        raise AssertionError("AUTO check must not take the manual-oracle path.")
    opened = summary.get("openedLowerIncisorRas")
    auto_lower = provenance.get("autoLowerIncisorRasMm")
    if opened is not None and auto_lower is not None:
        if float(opened[2]) >= float(auto_lower[2]) - 0.05:
            raise AssertionError(
                f"Opening is not inferior in RAS Z: closed {auto_lower[2]} open {opened[2]}"
            )
    if logic.step6CaseJawOpeningFreshnessIssues(parameter):
        raise AssertionError(
            "Case Foundation not current after AUTO commit: "
            + " ".join(logic.step6CaseJawOpeningFreshnessIssues(parameter))
        )
    payload = {
        "scene": str(scene_path),
        "volume": parameter.inputVolume.GetName(),
        "segmentation": parameter.teethSegmentation.GetName(),
        "hingeSource": hinge,
        "selection": (provenance.get("hingeResolution") or {}).get("selection"),
        "landmarkSource": provenance.get("landmarkSource"),
        "targetGapMm": target,
        "achievedGapMm": summary.get("gapMm"),
        "thetaDeg": summary.get("angleDeg"),
        "profileMaxGapMm": provenance.get("profile_max_gap_mm"),
        "openingRotationSign": provenance.get("opening_rotation_sign"),
    }
    print("DENTOBOT_AUTO_OPEN_MOUTH_PASS " + json.dumps(payload), flush=True)
    slicer.util.exit(0)


def _start() -> None:
    try:
        run()
    except Exception as exc:
        traceback.print_exc()
        print(
            "DENTOBOT_AUTO_OPEN_MOUTH_FAIL " + json.dumps({"error": str(exc)}),
            flush=True,
        )
        slicer.util.exit(1)


import qt

qt.QTimer.singleShot(0, _start)
