import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_step6_base_candidate_confirmation as confirmation  # noqa: E402
import step6_run_stall_watch as watcher  # noqa: E402

RUN = "s6-live-01-test-r99"


def _run_dir(tmp_path, *, pid="4242"):
    run = tmp_path / RUN
    run.mkdir()
    (run / "campaign.log").write_text("start\n")
    if pid is not None:
        (run / "slicer.pid").write_text(pid + "\n")
    return run


def _runner(cmdline, calls):
    def run(args, **_kw):
        calls.append(args)
        if args[3] == "cat":
            return SimpleNamespace(returncode=0 if cmdline else 1, stdout=cmdline)
        return SimpleNamespace(returncode=0, stdout="")
    return run


OWNED = f"/opt/slicer/SlicerApp-real\0--python-script\0/workspace/data/dentobot-runs/{RUN}/faulthandler-wrapper.py\0"


def test_ownership_requires_pid_file_slicer_and_this_runs_wrapper(tmp_path):
    calls = []
    (tmp_path / "missing").mkdir()
    no_pid = _run_dir(tmp_path / "missing", pid=None)
    assert watcher.owned_slicer_pid(no_pid, runner=_runner(OWNED, calls)) == (None, "slicer.pid missing or invalid")
    run = _run_dir(tmp_path)
    assert watcher.owned_slicer_pid(run, runner=_runner("", calls)) == (None, "pid 4242 not running in dentobot-slicerros2")
    assert watcher.owned_slicer_pid(run, runner=_runner("/usr/bin/python3\0x", calls))[1] == "pid 4242 is not SlicerApp-real"
    other = OWNED.replace(RUN, "someone-elses-run")
    assert watcher.owned_slicer_pid(run, runner=_runner(other, calls))[1] == f"pid 4242 was not launched by run {RUN}"
    assert watcher.owned_slicer_pid(run, runner=_runner(OWNED, calls)) == (4242, "owned")


def test_one_dump_per_stall_rearms_on_progress_and_never_kills(tmp_path):
    run = _run_dir(tmp_path)
    log = run / "campaign.log"
    calls = []
    clock = {"t": log.stat().st_mtime}
    script = {"step": 0}

    def sleep(seconds):
        clock["t"] += seconds
        script["step"] += 1
        if script["step"] == 60:  # progress resumes after the first stall
            log.write_text("start\nmore\n")
            os.utime(log, (clock["t"], clock["t"]))
        if script["step"] == 200:
            (run / "transaction-status.json").write_text("{}")

    record = watcher.watch(run, idle_sec=600, poll_sec=20, runner=_runner(OWNED, calls),
                           clock=lambda: clock["t"], sleep=sleep)
    sent = [e for e in record["events"] if e["event"] == "sigusr1_sent"]
    assert len(sent) == 2 and all(e["pid"] == 4242 for e in sent)
    assert any(e["event"] == "progress_resumed" for e in record["events"])
    signals = [args for args in calls if args[3] == "kill"]
    assert signals == [["docker", "exec", "dentobot-slicerros2", "kill", "-USR1", "4242"]] * 2
    assert json.loads((run / "stall-watch.json").read_text())["events"] == record["events"]


def test_unowned_process_is_never_signalled(tmp_path):
    run = _run_dir(tmp_path)
    calls = []
    clock = {"t": (run / "campaign.log").stat().st_mtime + 700}

    def sleep(seconds):
        clock["t"] += seconds
        (run / "transaction-status.json").write_text("{}")

    record = watcher.watch(run, idle_sec=600, runner=_runner(OWNED.replace(RUN, "other"), calls),
                           clock=lambda: clock["t"], sleep=sleep)
    assert record["events"][0]["event"] == "not_signalled"
    assert not any(args[3] == "kill" for args in calls)


def test_generated_wrapper_has_on_demand_dump_and_pid_file_only():
    text = confirmation.faulthandler_wrapper_text("/workspace/data/dentobot-runs/r1", "/workspace/x/Testing")
    compile(text, "wrapper", "exec")
    assert "dump_traceback_later" not in text.replace("no periodic dump_traceback_later", "")
    assert "faulthandler.register(signal.SIGUSR1, file=handle, all_threads=True, chain=False)" in text
    assert '(root / "slicer.pid").write_text(str(os.getpid())' in text
    hooks = confirmation.ensure_gdb_sigusr1("source a\n" + confirmation.GDB_SIGUSR1_LINE + "\n")
    assert hooks.splitlines()[0] == confirmation.GDB_SIGUSR1_LINE
    assert hooks.count(confirmation.GDB_SIGUSR1_LINE) == 1


def test_prepare_run_regenerates_wrapper_instead_of_copying_the_template(tmp_path):
    template = tmp_path / "r-old"
    template.mkdir()
    for name in confirmation.TEMPLATE_FILES:
        (template / name).write_text("x\n")
    (template / "faulthandler-wrapper.py").write_text("faulthandler.dump_traceback_later(300, repeat=True)\n")
    (template / "gdb-hooks.gdb").write_text("define hook-stop\nend\n")
    (template / "host-provenance.json").write_text("{}")
    run = tmp_path / "r-new"
    confirmation.prepare_run(template, run, [], Path(__file__).resolve().parents[1], "note")
    wrapper = (run / "faulthandler-wrapper.py").read_text()
    assert "dump_traceback_later(300" not in wrapper and "SIGUSR1" in wrapper
    assert "/workspace/data/dentobot-runs/r-new" in wrapper
    assert (run / "gdb-hooks.gdb").read_text().startswith(confirmation.GDB_SIGUSR1_LINE)
