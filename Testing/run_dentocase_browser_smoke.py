"""Narrow native Qt layout/lifecycle probe against a copied existing catalog."""
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback
import slicer

root = Path(os.environ['DENTOCASE_BENCH_ROOT'])
sys.path.insert(0, str(root / 'DENTOWorkflow/Resources/Python'))
from dentobot_workflow.case_library import show_case_library

evidence = Path(os.environ['DENTOCASE_EVIDENCE_DIR'])
evidence.mkdir(parents=True, exist_ok=True)
database = evidence / 'catalog.sqlite'
shutil.copyfile(os.environ['DENTOCASE_CATALOG_SOURCE'], database)
try:
    started = time.monotonic()
    session = show_case_library(slicer.util.mainWindow(), database_path=str(database),
        on_full_load=lambda *_: None, on_partial_load=lambda *_: None, on_partial_save=lambda *_: None)
    deadline = time.monotonic() + 8
    while (not session._rows or not session._details) and time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(.01)
    print('DENTOCASE_BROWSER_NATIVE', len(session._rows), session._details is not None,
          session._progress_status.text, flush=True)
    assert session.dialog.grab().save(str(evidence / 'browser.png'))
    assert session._rows and session._details, session._progress_status.text
    result = {'status': 'PASS', 'open_and_details_seconds': time.monotonic() - started,
              'rows': len(session._rows), 'native_qt': True}
    (evidence / 'result.json').write_text(json.dumps(result, indent=2))
    session.dialog.close()
    assert session._case_library_closed
except Exception:
    traceback.print_exc()
    slicer.util.exit(1)
else:
    slicer.util.exit(0)
