"""Create one production-serialized foundation package from the 13-Sep case.

The supplied case is never modified.  A revision-only migration input is made
only when explicitly requested, then opened and saved through DENTOWorkflow's
normal case-bundle serializer.  The report is the evidence boundary for the
subsequent single-target FDI31 run.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback
import types
import zipfile

import qt
import slicer
import vtk


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
MODULE = ROOT / "DENTOWorkflow"
for path in (HELPERS, MODULE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from DENTOCaseBundle import validate_case_bundle  # noqa: E402


SOURCE = Path(
    os.environ.get(
        "DENTOBOT_FOUNDATION_SOURCE",
        "/workspace/data/Slicer_Saved/SampleStudy1/dentobot-case-13sept.dentocase",
    )
)
OUTPUT_ROOT = Path(
    os.environ.get(
        "DENTOBOT_FOUNDATION_OUTPUT_ROOT",
        "/workspace/data/dentobot-runs/fdi31-foundation-current-20260914",
    )
)
OUTPUT_CASE = OUTPUT_ROOT / "foundation-current.dentocase"
REPORT = OUTPUT_ROOT / "foundation-migration-report.json"


def process_events(seconds: float = 0.25) -> None:
    deadline = time.monotonic() + float(seconds)
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _archive_payloads(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path, "r") as archive:
        return {info.filename: archive.read(info.filename) for info in archive.infolist()}


def _mrb_payloads(payload: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        return {info.filename: archive.read(info.filename) for info in archive.infolist()}


def _inner_mrml(payload: bytes) -> str:
    members = _mrb_payloads(payload)
    names = [name for name in members if name.lower().endswith(".mrml")]
    require(len(names) == 1, "case MRB must contain exactly one MRML scene")
    return members[names[0]].decode("utf-8")


def _revision(text: str) -> int | None:
    match = re.search(r"step6BasePlacementRevision\s+(-?\d+)", text)
    return int(match.group(1)) if match else None


def package_summary(path: Path) -> dict[str, object]:
    inspection = validate_case_bundle(path)
    payloads = _archive_payloads(path)
    workflow = inspection.workflow
    foundation = workflow.get("caseFoundation") or {}
    step6 = workflow.get("step6") or {}
    base = step6.get("basePlacement") or {}
    environment = step6.get("environment") or {}
    registry = step6.get("trajectoryRegistry") or {}
    nodes = {
        str(record.get("field")): record
        for record in workflow.get("nodes", [])
        if isinstance(record, dict) and record.get("field")
    }
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "sizeBytes": path.stat().st_size,
        "archiveMembers": sorted(payloads),
        "manifest": inspection.manifest,
        "manifestFileChecksums": inspection.manifest.get("files", {}),
        "checksumsSha256": hashlib.sha256(
            payloads["integrity/checksums.sha256"]
        ).hexdigest(),
        "sceneSha256": inspection.scene_sha256,
        "workflowSchema": workflow.get("schemaVersion"),
        "source": {
            "volumeFingerprint": foundation.get("source_volume_fingerprint"),
            "segmentationFingerprint": foundation.get("source_segmentation_fingerprint"),
            "volumeNode": nodes.get("inputVolume"),
            "segmentationNode": nodes.get("teethSegmentation"),
        },
        "caseFoundation": {
            "foundationFingerprint": foundation.get("foundation_fingerprint"),
            "planningPoseFingerprint": foundation.get("planning_pose_fingerprint"),
            "pose": foundation.get("pose"),
            "base": foundation.get("base"),
            "jawLandmarks": nodes.get("step6CaseJawLandmarks"),
            "jawTransform": nodes.get("step6CaseJawTransform"),
            "gapLine": nodes.get("step6CaseJawGapLine"),
            "openedLowerJaw": nodes.get("step6OpenedLowerJawModel"),
            "fixedUpper": nodes.get("step6FixedUpperAnatomy"),
            "movingLower": nodes.get("step6MovingLowerAnatomy"),
        },
        "base": {
            "placement": base,
            "environment": {
                key: environment.get(key)
                for key in (
                    "base_authority",
                    "base_fingerprint",
                    "base_locked",
                    "base_matrix",
                    "base_revision",
                    "base_status",
                    "base_setup_fingerprint",
                )
            },
            "mrmlRevision": _revision(_inner_mrml(payloads["scene/case.mrb"])),
        },
        "registry": registry,
        "lineage": workflow,
    }


def make_revision_migration(source: Path) -> tuple[Path, dict[str, object]]:
    requested = os.environ.get("DENTOBOT_CASE_REPAIR_BASE_REVISION", "").strip()
    require(requested == "0", "explicit DENTOBOT_CASE_REPAIR_BASE_REVISION=0 is required")
    source_payloads = _archive_payloads(source)
    original = dict(source_payloads)
    original_mrb = original["scene/case.mrb"]
    changed = 0
    rebuilt_mrb = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_mrb), "r") as incoming, zipfile.ZipFile(
        rebuilt_mrb, "w", allowZip64=True
    ) as outgoing:
        for info in incoming.infolist():
            payload = incoming.read(info.filename)
            if info.filename.lower().endswith(".mrml"):
                changed += payload.count(b"step6BasePlacementRevision 1")
                payload = payload.replace(
                    b"step6BasePlacementRevision 1",
                    b"step6BasePlacementRevision 0",
                )
            outgoing.writestr(info, payload)
    require(changed == 1, f"expected one revision-only MRML change, found {changed}")
    original["scene/case.mrb"] = rebuilt_mrb.getvalue()
    manifest = json.loads(original["manifest.json"].decode("utf-8"))
    record = manifest["files"]["scene/case.mrb"]
    record["sha256"] = hashlib.sha256(original["scene/case.mrb"]).hexdigest()
    record["sizeBytes"] = len(original["scene/case.mrb"])
    original["manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    original["integrity/checksums.sha256"] = "".join(
        f"{value['sha256']}  {name}\n"
        for name, value in sorted(manifest["files"].items())
    ).encode("ascii")
    candidate = OUTPUT_ROOT / "migration-input-revision-0.dentocase"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    temporary = candidate.with_suffix(candidate.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
        for name, payload in original.items():
            archive.writestr(
                name,
                payload,
                compress_type=(
                    zipfile.ZIP_STORED
                    if name == "scene/case.mrb"
                    else zipfile.ZIP_DEFLATED
                ),
            )
    temporary.replace(candidate)
    validate_case_bundle(candidate)
    candidate_payloads = _archive_payloads(candidate)
    changed_members = [
        name for name in sorted(source_payloads.keys())
        if source_payloads[name] != candidate_payloads[name]
    ]
    require(
        changed_members == [
            "integrity/checksums.sha256",
            "manifest.json",
            "scene/case.mrb",
        ],
        f"migration changed unexpected outer members: {changed_members}",
    )
    inner_original = _mrb_payloads(source_payloads["scene/case.mrb"])
    inner_candidate = _mrb_payloads(candidate_payloads["scene/case.mrb"])
    inner_changed = [
        name for name in sorted(inner_original)
        if inner_original[name] != inner_candidate.get(name)
    ]
    require(
        inner_changed == ["case/case.mrml"],
        f"migration changed unexpected MRB members: {inner_changed}",
    )
    return candidate, {
        "applied": True,
        "requestedRevision": 0,
        "changedOuterPayloadMembers": changed_members,
        "changedInnerPayloadMembers": inner_changed,
        "changedMrmlTokenCount": changed,
        "sourceRevision": _revision(_inner_mrml(_archive_payloads(source)["scene/case.mrb"])),
        "candidateRevision": _revision(_inner_mrml(candidate_payloads["scene/case.mrb"])),
        "candidate": str(candidate),
    }


def capture(stem: str) -> list[str]:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    main = slicer.util.mainWindow()
    try:
        main.resize(1600, 1000)
        main.show()
        process_events(0.2)
        path = OUTPUT_ROOT / f"{stem}-ui.png"
        if main.grab().save(str(path)):
            paths.append(str(path))
    except Exception:
        pass
    try:
        view = slicer.app.layoutManager().threeDWidget(0).threeDView()
        view.forceRender()
        slicer.util.forceRenderAllViews()
        process_events(0.25)
        image = vtk.vtkWindowToImageFilter()
        image.SetInput(view.renderWindow())
        image.ReadFrontBufferOff()
        image.Update()
        writer = vtk.vtkPNGWriter()
        path = OUTPUT_ROOT / f"{stem}-viewport.png"
        writer.SetFileName(str(path))
        writer.SetInputConnection(image.GetOutputPort())
        writer.Write()
        if path.is_file():
            paths.append(str(path))
    except Exception:
        pass
    return paths


def run() -> dict[str, object]:
    require(SOURCE.is_file(), f"missing authoritative source: {SOURCE}")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    baseline = package_summary(SOURCE)
    mrml_revision = baseline["base"]["mrmlRevision"]
    saved_revision = baseline["lineage"]["step6"]["basePlacement"]["sourceRevision"]
    revision_discrepancy = mrml_revision != saved_revision

    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    require(widget is not None and widget.logic is not None, "DENTOWorkflow did not initialize")
    original_hydrated_validator = widget._validateHydratedCaseBundle

    def capture_hydrated_mismatch(self, expected):
        try:
            return original_hydrated_validator(expected)
        except Exception as exc:
            parameter_node = self.logic.getParameterNode()
            actual = self.logic._caseBundleNodeRecord(
                "targetToothBoundsRoi", parameter_node.targetToothBoundsRoi
            )
            expected_record = next(
                record
                for record in expected.get("nodes", [])
                if record.get("field") == "targetToothBoundsRoi"
            )
            (OUTPUT_ROOT / "load-mismatch-target-roi.json").write_text(
                json.dumps(
                    {
                        "error": f"{type(exc).__name__}: {exc}",
                        "expected": expected_record,
                        "actual": actual,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            raise

    widget._validateHydratedCaseBundle = types.MethodType(
        capture_hydrated_mismatch, widget
    )

    original_open = {"attempted": False, "succeeded": False, "error": ""}
    package_path = SOURCE
    migration = {"applied": False}
    if revision_discrepancy:
        original_open["attempted"] = True
        try:
            widget._openCaseBundle(str(SOURCE))
            original_open["succeeded"] = True
        except Exception as exc:
            original_open["error"] = f"{type(exc).__name__}: {exc}"
            package_path, migration = make_revision_migration(SOURCE)
            widget._openCaseBundle(str(package_path))
    else:
        widget._openCaseBundle(str(SOURCE))
    process_events(1.0)
    parameter = widget._parameterNode
    logic = widget.logic
    require(parameter is not None and logic is not None, "case state did not restore")
    foundation_before = logic.evaluateCaseFoundationEligibility(parameter)
    registry_before = logic.syncDentoCaseTrajectoryRegistry(parameter)
    require(parameter.inputVolume is not None, "source volume did not restore")
    require(parameter.teethSegmentation is not None, "source segmentation did not restore")
    require(not registry_before.get("prepared_branches"), "migration input unexpectedly has a branch")
    evidence = capture("foundation-before-production-save")
    save_inspection = widget._createCaseBundle(str(OUTPUT_CASE))
    del save_inspection
    process_events(0.5)
    saved = package_summary(OUTPUT_CASE)
    stable = {
        "sourceVolumeFingerprint": baseline["source"]["volumeFingerprint"] == saved["source"]["volumeFingerprint"],
        "sourceSegmentationFingerprint": baseline["source"]["segmentationFingerprint"] == saved["source"]["segmentationFingerprint"],
        "foundationFingerprint": baseline["caseFoundation"]["foundationFingerprint"] == saved["caseFoundation"]["foundationFingerprint"],
        "planningPoseFingerprint": baseline["caseFoundation"]["planningPoseFingerprint"] == saved["caseFoundation"]["planningPoseFingerprint"],
        "baseMatrix": baseline["base"]["environment"]["base_matrix"] == saved["base"]["environment"]["base_matrix"],
        "baseFingerprint": baseline["base"]["environment"]["base_fingerprint"] == saved["base"]["environment"]["base_fingerprint"],
        "landmarkFingerprint": baseline["lineage"]["step6"]["environment"]["jaw_landmarks_fingerprint"] == saved["lineage"]["step6"]["environment"]["jaw_landmarks_fingerprint"],
        "registryHasNoPreparedBranches": not saved["registry"].get("prepared_branches"),
        "productionSchema": saved["workflowSchema"] == "3.0",
    }
    require(all(stable.values()), "production save changed a protected foundation identity")
    evidence.extend(capture("foundation-after-production-save"))
    output_foundation = logic.evaluateCaseFoundationEligibility(parameter)
    report = {
        "status": "PASS",
        "source": str(SOURCE),
        "outputCase": str(OUTPUT_CASE),
        "baseline": baseline,
        "originalOpen": original_open,
        "migration": migration,
        "loadedPackage": str(package_path),
        "loadedFoundation": foundation_before,
        "saved": saved,
        "savedFoundation": output_foundation,
        "protectedIdentityChecks": stable,
        "evidence": evidence,
        "notes": [
            "The authoritative source was not overwritten.",
            "The final package was produced by DENTOWorkflow._createCaseBundle.",
            "The base transform was preserved; base locking remains a later reviewed Step 6 action.",
        ],
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    return report


try:
    result = run()
    print("DENTOBOT_FDI31_FOUNDATION_MIGRATION_PASS " + json.dumps({
        "outputCase": result["outputCase"],
        "report": str(REPORT),
        "migration": result["migration"],
        "protectedIdentityChecks": result["protectedIdentityChecks"],
    }, sort_keys=True), flush=True)
    slicer.util.exit(0)
except Exception as exc:
    failure = {
        "status": "ERROR",
        "source": str(SOURCE),
        "outputCase": str(OUTPUT_CASE),
        "errorType": type(exc).__name__,
        "error": str(exc),
        "traceback": traceback.format_exc(),
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
    print("DENTOBOT_FDI31_FOUNDATION_MIGRATION_FAIL " + json.dumps(failure, sort_keys=True), file=sys.stderr, flush=True)
    try:
        slicer.util.exit(1)
    except Exception:
        raise
