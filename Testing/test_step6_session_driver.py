import importlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import step6_session_driver as driver  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.write_text(text)
    stamp = time.time_ns() + 5_000_000_000
    os.utime(path, ns=(stamp, stamp))  # mtime must differ even on coarse clocks


def _fresh_modules(tmp_path, monkeypatch):
    pkg = tmp_path / "dentobot_workflow"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "zz_base.py").write_text("class Helper:\n    def value(self):\n        return 1\n")
    (pkg / "aa_user.py").write_text(
        "from dentobot_workflow.zz_base import Helper\n"
        "class Facade:\n    def __init__(self):\n        self.state = 'kept'\n"
        "    def answer(self):\n        return Helper().value()\n"
    )
    (tmp_path / "DENTOROS2Bridge.py").write_text("STATE = 'live'\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in [n for n in sys.modules if n.startswith("dentobot_workflow") or n == "DENTOROS2Bridge"]:
        monkeypatch.delitem(sys.modules, name)
    importlib.invalidate_caches()
    user = importlib.import_module("dentobot_workflow.aa_user")
    importlib.import_module("DENTOROS2Bridge")
    return pkg, user


def test_reload_changed_swaps_live_class_keeps_state_and_orders_dependencies(tmp_path, monkeypatch):
    pkg, user = _fresh_modules(tmp_path, monkeypatch)
    facade = user.Facade()
    reloader = driver.HotReloader(lambda: [facade])
    assert reloader.reload_changed()["reloaded"] == []
    _write(pkg / "zz_base.py", "class Helper:\n    def value(self):\n        return 2\n")
    report = reloader.reload_changed()
    assert report["changed"] == ["dentobot_workflow.zz_base"]
    # The dependent reloads after its dependency, so it binds the new Helper.
    assert report["reloaded"] == ["dentobot_workflow.zz_base", "dentobot_workflow.aa_user"]
    assert report["swapped"] == ["dentobot_workflow.aa_user.Facade"]
    assert facade.answer() == 2 and facade.state == "kept"
    assert report["restart_required"] == []


def test_bridge_is_never_reloaded_and_reports_restart(tmp_path, monkeypatch):
    _pkg, _user = _fresh_modules(tmp_path, monkeypatch)
    bridge = sys.modules["DENTOROS2Bridge"]
    bridge.STATE = "subscribed"
    reloader = driver.HotReloader(lambda: [])
    _write(tmp_path / "DENTOROS2Bridge.py", "STATE = 'new'\n")
    report = reloader.reload_changed()
    assert "DENTOROS2Bridge" not in report["reloaded"]
    assert report["restart_required"] == ["DENTOROS2Bridge"]
    assert bridge.STATE == "subscribed"


def test_rebind_callbacks_points_bound_methods_at_current_class():
    class Old:
        def handler(self):
            return "old"

    class New(Old):
        def handler(self):
            return "new"

    owner = Old()
    callbacks = {"a": owner.handler, "b": lambda: "lambda"}
    owner.__class__ = New
    assert callbacks["a"]() == "old"
    assert driver.rebind_callbacks(callbacks, owner) == 1
    assert callbacks["a"]() == "new" and callbacks["b"]() == "lambda"


def test_session_runs_commands_records_errors_and_stops(tmp_path):
    inbox = tmp_path / "session" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "001-ok.py").write_text("result = {'sum': value + 1}\n")
    (inbox / "002-fail.py").write_text("result = 'partial'\nraise ValueError('boom')\n")
    (inbox / "003-stop.py").write_text("result = 'bye'\n")
    outcome = driver.run_session({"value": 41}, tmp_path / "session", lambda _s: None)
    out = tmp_path / "session" / "outbox"
    assert outcome["reason"] == "stop_command"
    assert json.loads((out / "001-ok.json").read_text())["result"] == {"sum": 42}
    failed = json.loads((out / "002-fail.json").read_text())
    assert failed["status"] == "error" and "boom" in failed["traceback"] and failed["result"] == "partial"
    assert sorted(p.name for p in (tmp_path / "session" / "done").iterdir()) == [
        "001-ok.py", "002-fail.py", "003-stop.py"]
    assert json.loads((tmp_path / "session" / "ready.json").read_text())["ready"] is True


def test_session_exits_after_idle_limit(tmp_path):
    ticks = iter(range(0, 10_000, 30))
    outcome = driver.run_session({}, tmp_path / "s", lambda _s: None, idle_limit_sec=100,
                                 clock=lambda: next(ticks))
    assert outcome == {"reason": "idle_limit", "executed": []}


def test_sender_queues_numbered_command_and_reads_result(tmp_path):
    import step6_session_send as sender

    session = tmp_path / "session"
    for part in ("inbox", "outbox", "done"):
        (session / part).mkdir(parents=True)
    assert sender.send(tmp_path, "reload", 1.0)[0] == 3  # not serving yet
    (session / "ready.json").write_text("{}")
    (session / "done" / "004-old.py").write_text("")

    def fake_sleep(_seconds):
        queued = next((session / "inbox").glob("*.py"))
        (session / "outbox" / f"{queued.stem}.json").write_text(json.dumps({"status": "ok", "result": 1}))

    code, record = sender.send(tmp_path, "reload", 10.0, sleep=fake_sleep)
    assert code == 0 and record["result"] == 1
    assert (session / "inbox" / "005-reload.py").is_file()


def test_sender_stops_waiting_when_run_ended(tmp_path):
    import step6_session_send as sender

    session = tmp_path / "session"
    for part in ("inbox", "outbox", "done"):
        (session / part).mkdir(parents=True)
    (session / "ready.json").write_text("{}")
    (tmp_path / "transaction-status.json").write_text("{}")
    code, record = sender.send(tmp_path, "stop", 10.0, sleep=lambda _s: None)
    assert code == 3 and record["error"] == "the run has ended"


def test_modules_imported_after_start_are_baselined_not_reported_changed(tmp_path, monkeypatch):
    pkg, _user = _fresh_modules(tmp_path, monkeypatch)
    reloader = driver.HotReloader(lambda: [])
    (pkg / "late.py").write_text("VALUE = 1\n")
    importlib.invalidate_caches()
    importlib.import_module("dentobot_workflow.late")
    reloader.note_new_modules()
    assert reloader.reload_changed()["changed"] == []


def test_outbox_results_are_written_atomically():
    source = (Path(__file__).resolve().parent / "step6_session_driver.py").read_text()
    assert 'staging = outbox / f".{name}.json.tmp"' in source
    assert 'staging.rename(outbox / f"{name}.json")' in source


def test_sender_retries_a_partially_written_result(tmp_path):
    import step6_session_send as sender

    session = tmp_path / "session"
    for part in ("inbox", "outbox", "done"):
        (session / part).mkdir(parents=True)
    (session / "ready.json").write_text("{}")
    calls = {"n": 0}

    def fake_sleep(_seconds):
        calls["n"] += 1
        queued = next((session / "inbox").glob("*.py"), None)
        stem = queued.stem if queued else "001-reload"
        out = session / "outbox" / f"{stem}.json"
        out.write_text('{"status": "ok", "res' if calls["n"] == 1 else json.dumps({"status": "ok", "result": 2}))

    code, record = sender.send(tmp_path, "reload", 10.0, sleep=fake_sleep)
    assert code == 0 and record["result"] == 2 and calls["n"] >= 2
