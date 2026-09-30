"""Disposable Slicer check that a recovered UI stall is logged without a timeout trace."""

import re
import sys
import time
import traceback
from pathlib import Path

import qt
import slicer


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "DENTOWorkflow/Resources/Python"))
from dentobot_workflow.ui_stall_watchdog import install_ui_stall_watchdog


def run():
    slicer.util.selectModule("DENTOWorkflow")
    watchdog = install_ui_stall_watchdog()
    assert watchdog is not None
    watchdog.note_phase("Watchdog smoke")
    time.sleep(6.2)
    slicer.app.processEvents()
    watchdog.close()
    log = Path(watchdog.log.name).read_text()
    assert "SESSION_START" in log, log[-2000:]
    assert "WORKFLOW_PHASE phase=Watchdog smoke" in log, log[-2000:]
    recovered = re.search(
        r"UI_STALL_RECOVERED gap_seconds=([0-9.]+) phase=Watchdog smoke", log
    )
    assert recovered and 5.0 <= float(recovered.group(1)) < 10.0, log[-2000:]
    assert "SESSION_END" in log, log[-2000:]
    assert "Timeout (0:00:05)!" not in log, log[-2000:]
    print("DENTOBOT_UI_STALL_WATCHDOG_PASS", watchdog.log.name, flush=True)
    slicer.util.exit(0)


def safe_run():
    try:
        run()
    except Exception:
        traceback.print_exc()
        slicer.util.exit(1)


qt.QTimer.singleShot(0, safe_run)
