"""Check that New Empty Case removes FD14 nodes before a .dentocase save."""

from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from pathlib import Path

import slicer


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOCaseBundle import validate_case_bundle  # noqa: E402


SOURCE = Path(
    "/workspace/data/Slicer_Saved/SampleStudy1/FDI14/dentobot-case-step6x4.dentocase"
)
OUTPUT = Path(slicer.app.temporaryPath) / "dentobot-fd14-after-newcase.dentocase"


def process_events(seconds: float = 1.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def mrml_text(package: Path) -> str:
    with zipfile.ZipFile(package) as outer:
        mrb = outer.read("scene/case.mrb")
    with zipfile.ZipFile(io.BytesIO(mrb)) as inner:
        mrml_name = next(name for name in inner.namelist() if name.endswith(".mrml"))
        return inner.read(mrml_name).decode("utf-8", "replace")


def package_fd14_hits(package: Path) -> dict[str, int]:
    with zipfile.ZipFile(package) as archive:
        lineage = archive.read("workflow/lineage.json").decode("utf-8", "replace")
    mrml = mrml_text(package)
    return {
        "mrml_FDI14": mrml.count("FDI14") + mrml.count("FDI 14"),
        "lineage_FDI14": lineage.count("FDI14") + lineage.count("FDI 14"),
    }


def run() -> None:
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    if widget is None:
        raise RuntimeError("DENTOWorkflow widget did not initialize")
    if not SOURCE.is_file():
        raise RuntimeError(f"FD14 source package is missing: {SOURCE}")
    widget._openCaseBundle(str(SOURCE))
    process_events(1.0)
    before = {
        "fd14_nodes": sum(
            1
            for index in range(slicer.mrmlScene.GetNumberOfNodes())
            if "FDI14" in (slicer.mrmlScene.GetNthNode(index).GetName() or "")
            or "FDI 14" in (slicer.mrmlScene.GetNthNode(index).GetName() or "")
        ),
        "package_hits": package_fd14_hits(SOURCE),
    }
    if before["fd14_nodes"] == 0:
        raise RuntimeError("FD14 package did not restore any FD14-labeled MRML node")

    original_confirm = slicer.util.confirmYesNoDisplay
    slicer.util.confirmYesNoDisplay = lambda *args, **kwargs: True
    try:
        widget.onNewCase()
    finally:
        slicer.util.confirmYesNoDisplay = original_confirm
    process_events(1.0)

    stale_names = []
    for index in range(slicer.mrmlScene.GetNumberOfNodes()):
        node = slicer.mrmlScene.GetNthNode(index)
        name = node.GetName() or ""
        if "FDI14" in name or "FDI 14" in name:
            stale_names.append(name)
    if stale_names:
        raise RuntimeError(f"New Empty Case retained FD14 nodes: {stale_names}")

    inspection = widget._createCaseBundle(OUTPUT)
    validate_case_bundle(inspection.path)
    hits = package_fd14_hits(inspection.path)
    if any(hits.values()):
        raise RuntimeError(f"New Empty Case save serialized FD14 artifacts: {hits}")
    with zipfile.ZipFile(inspection.path) as archive:
        lineage = json.loads(archive.read("workflow/lineage.json"))
    print(
        "DENTOBOT_FD14_NEW_CASE_SAVE_PASS "
        + json.dumps(
            {
                "source": before,
                "afterNodeCount": slicer.mrmlScene.GetNumberOfNodes(),
                "savedPackageHits": hits,
                "savedLineageNodeCount": len(lineage.get("nodes", [])),
                "output": str(inspection.path),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    slicer.mrmlScene.Clear(0)
    process_events(0.5)
    OUTPUT.unlink(missing_ok=True)
    slicer.util.exit(0)


try:
    run()
except Exception as exc:
    print(f"DENTOBOT_FD14_NEW_CASE_SAVE_FAIL: {exc}", file=sys.stderr)
    slicer.util.exit(1)
