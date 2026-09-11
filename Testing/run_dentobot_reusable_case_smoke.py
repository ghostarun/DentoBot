"""Focused synthetic Slicer verification for S6-REUSABLE-CASE-SETUP."""

from __future__ import annotations

from pathlib import Path
import sys
import time

import slicer


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOWorkflow import DENTOWorkflowTest  # noqa: E402


def process_events(seconds: float = 0.5) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def run() -> None:
    slicer.util.selectModule("DENTOWorkflow")
    process_events()
    test = DENTOWorkflowTest()
    try:
        test.setUp()
        process_events()
        test._focusedPreparedBranchSmoke = True
        test.test_DENTOWorkflowVisibleTemplateSupportSurface()
    finally:
        test.setUp()
    print("DENTOBOT_REUSABLE_CASE_PASS", flush=True)
    slicer.util.exit(0)


try:
    run()
except Exception as exc:
    print(f"DENTOBOT_REUSABLE_CASE_FAILED: {exc}", file=sys.stderr, flush=True)
    slicer.util.exit(1)
