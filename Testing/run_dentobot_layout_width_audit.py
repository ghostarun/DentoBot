"""Read-only Slicer width audit for the narrow-fit contract (UI-P3-01).

Opens the DENTOBOT shell with no case, visits every workspace and substep at
the narrow dock widths and records, per page, the viewport width, the content
width, the content's own minimum width (the "page needs" figure) and the visible
widgets whose minimum width exceeds the viewport, plus a dock screenshot.

It changes no case, scene, ROS or robot state.  ``DENTOBOT_NARROW_FIT=0`` runs
the same probe with the generic fit pass disabled for a before/after baseline.
Environment: ``DENTOBOT_AUDIT_OUT`` (directory), ``DENTOBOT_AUDIT_LABEL``.
"""

from __future__ import annotations

import json
import os
import traceback

import qt
import slicer


OUT_DIR = os.environ.get("DENTOBOT_AUDIT_OUT", "/workspace/data/dentobot-runs/layout-width-audit")
LABEL = os.environ.get("DENTOBOT_AUDIT_LABEL", "run")
WIDTHS = (340, 390)
TOP_OFFENDERS = 12


def _write(report: dict) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"{LABEL}.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in str(text)).strip("-").lower()


def run() -> None:
    report = {"label": LABEL, "pages": [], "error": None}
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        settings = qt.QSettings()
        settings.setValue("DENTOBOT/ApplicationShell/GuiMode", "legacy")
        settings.setValue("DENTOBOT/ApplicationShell/ExpertMode", False)
        slicer.util.selectModule("DENTOWorkflow")
        slicer.app.processEvents()
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        if widget is None or widget._applicationShell is None:
            raise RuntimeError("DENTOBOT application shell was not initialized")

        from DENTOLayoutFit import (
            fitEnabled,
            findWidthOffenders,
            qtValue,
            resizeDockWidth,
        )

        widget._applyDENTOBOTGuiMode("shell")
        slicer.app.processEvents()
        shell = widget._applicationShell
        if not shell.active:
            raise RuntimeError("shell mode did not activate")
        main_window = slicer.util.mainWindow()
        task_dock = main_window.findChild("QDockWidget", "DENTOBOTTaskDock")
        scroll = widget._workflowContentScrollArea
        content = widget._workflowContentWidget
        if task_dock is None or scroll is None or content is None:
            raise RuntimeError("task dock or workflow content scroll area is missing")

        report["fit_enabled"] = bool(fitEnabled())
        report["fit_controller"] = widget._narrowFit is not None
        report["main_window_width"] = int(qtValue(main_window.width))

        for requested in WIDTHS:
            resizeDockWidth(main_window, task_dock, requested)
            slicer.app.processEvents()
            for workspace_index, button in enumerate(shell._workspace_buttons):
                button.click()
                slicer.app.processEvents()
                substeps = int(shell._substep_combo.count) if shell._substep_combo.visible else 1
                for substep in range(max(1, substeps)):
                    if substeps > 1:
                        shell._substep_combo.setCurrentIndex(substep)
                        slicer.app.processEvents()
                    viewport = int(qtValue(qtValue(scroll.viewport).width))
                    content_width = int(qtValue(content.width))
                    content_min = int(qtValue(qtValue(content.minimumSizeHint).width))
                    chrome_min = int(
                        qtValue(qtValue(task_dock.widget().minimumSizeHint).width)
                    )
                    offenders = findWidthOffenders(content, viewport, visible_within=content)
                    title = str(button.text)
                    sub_title = str(shell._substep_combo.currentText) if substeps > 1 else ""
                    shot = os.path.join(
                        OUT_DIR,
                        f"{LABEL}-w{requested}-{workspace_index}-{_slug(title)}-{substep}.png",
                    )
                    saved = bool(task_dock.grab().save(shot))
                    report["pages"].append(
                        {
                            "requested_dock_width": requested,
                            "dock_width": int(qtValue(task_dock.width)),
                            "workspace": title,
                            "substep": sub_title,
                            "viewport_width": viewport,
                            "content_width": content_width,
                            "content_min_width": content_min,
                            "chrome_min_width": chrome_min,
                            "overflow_px": max(0, content_width - viewport),
                            "needs_more_than_viewport_px": max(0, content_min - viewport),
                            "offender_count": len(offenders),
                            "top_offenders": offenders[:TOP_OFFENDERS],
                            "screenshot": shot if saved else None,
                        }
                    )
        _write(report)
        print(json.dumps({"layout_width_audit": LABEL, "pages": len(report["pages"])}))
        print("DENTOBOT_LAYOUT_WIDTH_AUDIT_DONE", flush=True)
        slicer.util.exit(0)
    except Exception as exc:  # report, never hang the run
        report["error"] = f"{exc}\n{traceback.format_exc()}"
        try:
            _write(report)
        except Exception:
            pass
        print("DENTOBOT_LAYOUT_WIDTH_AUDIT_FAILED", report["error"], flush=True)
        slicer.util.exit(1)


qt.QTimer.singleShot(0, run)
