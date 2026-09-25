"""Disposable Slicer check that one UI stall leaves a persistent stack trace."""

import sys
import time
import traceback
from pathlib import Path

import qt
import slicer


sys.path.insert(0, "/workspace/ros2_ws/src/DentoBot/DENTOWorkflow/Resources/Python")
from dentobot_workflow.ui_stall_watchdog import install_ui_stall_watchdog


def run():
    slicer.util.selectModule("DENTOWorkflow")
    watchdog = install_ui_stall_watchdog()
    assert watchdog is not None
    watchdog.note_phase("Watchdog smoke")
    time.sleep(6.2)
    slicer.app.processEvents()
    log = Path(watchdog.log.name).read_text()
    assert "Timeout (0:00:05)!" in log, log[-2000:]
    assert "UI_STALL_RECOVERED" in log, log[-2000:]
    print("DENTOBOT_UI_STALL_WATCHDOG_PASS", watchdog.log.name, flush=True)
    slicer.util.exit(0)


def safe_run():
    try:
        run()
    except Exception:
        traceback.print_exc()
        slicer.util.exit(1)


qt.QTimer.singleShot(0, safe_run)
