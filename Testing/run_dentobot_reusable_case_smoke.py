"""Focused synthetic Slicer verification for S6-REUSABLE-CASE-SETUP."""

from __future__ import annotations

from pathlib import Path
import sys

import slicer


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOWorkflow import DENTOWorkflowTest  # noqa: E402


def run() -> None:
    slicer.util.selectModule("DENTOWorkflow")
    test = DENTOWorkflowTest()
    test.setUp()
    test.test_DENTOWorkflowCaseFoundation()
    test.setUp()
    test._focusedPreparedBranchSmoke = True
    test.test_DENTOWorkflowVisibleTemplateSupportSurface()
    print("DENTOBOT_REUSABLE_CASE_PASS", flush=True)
    slicer.util.exit(0)


try:
    run()
except Exception as exc:
    print(f"DENTOBOT_REUSABLE_CASE_FAILED: {exc}", file=sys.stderr, flush=True)
    slicer.util.exit(1)
