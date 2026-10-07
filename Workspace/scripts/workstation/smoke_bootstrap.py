"""Fixed Slicer-side bootstrap; smoke_runtime.py prepends a repr-safe SMOKE dict."""
import hashlib
import json
import sys
import traceback
from pathlib import Path

import qt
import slicer

ROOT = Path(SMOKE["repo"])
OUT = Path(SMOKE["evidence"])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finish(code):
    try:
        reports = NS.get("reports", [])
        (OUT / "reload-result.json").write_text(json.dumps({"requested_exit_code": code, "reports": reports}, indent=2) + "\n")
        if not slicer.util.mainWindow().grab().save(str(OUT / "final.png")):
            raise RuntimeError("final screenshot save failed")
    except Exception:
        (OUT / "finish-error.txt").write_text(traceback.format_exc())
        code = 1
    ORIGINAL_EXIT(code)


def run():
    try:
        slicer.util.selectModule("DENTOWorkflow")
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        actual = Path(slicer.util.modulePath("DENTOWorkflow")).resolve()
        expected = (ROOT / "DENTOWorkflow/DENTOWorkflow.py").resolve()
        files = {"DENTOWorkflow/DENTOWorkflow.py": actual}
        for name, relative in SMOKE["modules"].items():
            files[relative] = Path(sys.modules[name].__file__).resolve()
        checks = {}
        for relative, path in files.items():
            expected_path = (ROOT / relative).resolve()
            expected_hash = SMOKE["hashes"][relative]
            checks[relative] = {"path": str(path), "expected_path": str(expected_path),
                                "sha256": digest(path), "expected_sha256": expected_hash,
                                "matched": path == expected_path and digest(path) == expected_hash}
        matched = actual == expected and widget is not None and all(item["matched"] for item in checks.values())
        report = {"matched": matched, "loaded_module_path": str(actual), "expected_module_path": str(expected),
                  "files": checks, "widget_available": widget is not None,
                  "slicer_version": slicer.app.applicationVersion}
        (OUT / "loaded-code.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        if not matched:
            raise RuntimeError("loaded source paths or hashes differ from the clean checkout")
        slicer.app.processEvents()
        if not slicer.util.mainWindow().grab().save(str(OUT / "startup.png")):
            raise RuntimeError("startup screenshot save failed")
        print("DENTOBOT_B_LOADED_CODE_PASS", flush=True)
        test = ROOT / "Testing/run_dentobot_slicer_reload_smoke.py"
        NS.update({"__name__": "__main__", "__file__": str(test)})
        exec(compile(test.read_text(), str(test), "exec"), NS)
    except Exception:
        (OUT / "bootstrap-error.txt").write_text(traceback.format_exc())
        print(traceback.format_exc(), flush=True)
        slicer.util.exit(1)


NS = {}
ORIGINAL_EXIT = slicer.util.exit
slicer.util.exit = finish
qt.QTimer.singleShot(2000, run)
qt.QTimer.singleShot(120000, lambda: slicer.util.exit(3))
