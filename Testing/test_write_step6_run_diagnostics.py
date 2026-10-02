import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import write_step6_run_diagnostics as writer  # noqa: E402


def test_session_commands_and_cycle_timeline_are_reported(tmp_path):
    outbox = tmp_path / "session" / "outbox"
    outbox.mkdir(parents=True)
    (outbox / "001-plan_only.json").write_text(json.dumps(
        {"command": "001-plan_only", "status": "ok", "duration_sec": 116.4,
         "result": {"elapsed_sec": 116.4, "status_state": "warning", "selected": 3}}))
    (outbox / "002-cycles.json").write_text(json.dumps(
        {"command": "002-cycles", "status": "ok", "duration_sec": 1816.4,
         "result": {"passed": True, "evidence": {"captures": [
             {"stage": "cycle_1_home_returned",
              "result": {"ui": "x-cycle_1_home_returned-ui.png", "viewport": "x-viewport.png",
                         "captured_at_utc": "2026-10-02T21:44:04+00:00"}}]}}}))
    (outbox / "003-bad.json").write_text("{not json")
    lines, frames = writer.session_evidence(tmp_path, start=None, video=None)
    text = "\n".join(lines)
    assert "| 001-plan_only | ok | 116.4 | elapsed_sec=116.4, status_state=warning, selected=3 |" in text
    assert "| 002-cycles | ok | 1816.4 | passed=True |" in text
    assert "### 002-cycles timeline" in text
    assert "| cycle_1_home_returned | 21:44:04 | [png](evidence/x-cycle_1_home_returned-ui.png) |" in text
    assert frames == []


def test_no_session_directory_adds_nothing(tmp_path):
    assert writer.session_evidence(tmp_path, start=None, video=None) == ([], [])
