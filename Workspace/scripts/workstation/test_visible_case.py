"""Host-only tests for `dentobot visible-case` (no docker, ssh, rsync, X server, Slicer or network)."""

import ast
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import handoff
import smoke_runtime
import visible_case as vc


SHA = "a" * 40
RUN_ID = "20261008T122000Z"
IMAGE_ID = "sha256:" + "b" * 64
BOOTSTRAP = Path(vc.__file__).resolve().with_name("visible_case_bootstrap.py")
LOG_OK = ("DENTOBOT_B_LOADED_CODE_PASS\nDENTOBOT_VISIBLE_CASE_PASS\n"
          "[INFO] [Slicer-1]: process has finished cleanly [pid 64]\n")


class FakeGit:
    def __init__(self, status="", head=SHA, contained="  origin/test/visible\n"):
        self.table = {("status", "--porcelain"): status, ("rev-parse", "HEAD"): head + "\n",
                      ("branch", "-r"): contained}
        self.calls = []

    def __call__(self, repo, *args):
        self.calls.append(args)
        return self.table.get(tuple(args[:2]), "")


class FakeRemote:
    host = "dentobot-b"

    def __init__(self, run=(), status=()):
        self.queues = {"run": list(run), "status": list(status)}
        self.calls = []

    def call(self, args, timeout=60):
        self.calls.append(list(args))
        queue = self.queues[args[0]]
        if not queue:
            raise AssertionError(f"unexpected remote call: {args[0]}")
        item = queue[0] if len(queue) == 1 else queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return dict(item)


class FakeXhost:
    def __init__(self, grant=True, revoke=True):
        self.grant, self.revoke, self.calls = grant, revoke, []

    def __call__(self, args, env):
        self.calls.append(args[0])
        return self.grant if args[0].startswith("+") else self.revoke


class Clock:
    def __init__(self, step=0):
        self.now, self.step = 0, step

    def __call__(self):
        self.now += self.step
        return self.now


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data), encoding="utf-8")


def make_workspace(root, name):
    workspace = root / name
    repo = workspace / "ros2_ws/src/DentoBot"
    repo.mkdir(parents=True)
    (workspace / "data/Cases").mkdir(parents=True)
    (workspace / "data/Cases/a.dentocase").write_bytes(b"case-bytes")
    (workspace / ".dentobot.env").write_text(f"DENTOBOT_BACKEND_PYTHON={root / 'env/bin/python'}\n")
    return workspace, repo


def make_worktree(root, name="DentoBot-visible-aaaaaaaaaaaa"):
    worktree = root / "wt" / name
    (worktree / "Workspace").mkdir(parents=True)
    write_json(worktree / "Workspace/runtime-lock.json",
               {"image_id": IMAGE_ID, "image_name": "dentobot/slicerros2:test"})
    for relative in vc.COMMON_FILES:
        path = worktree / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n")
    return worktree


PRODUCTION = {"method": "onFramePlanningTarget", "status": "production", "reason": "planning target bounds available"}


def write_slicer_outputs(run_dir, shots=3, distinct=True, four_up=PRODUCTION, one_up=PRODUCTION):
    """What the visible bootstrap leaves behind, so smoke_runtime's checks can read it."""
    run_dir = Path(run_dir)
    (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    names = []
    for index in range(shots):
        name = f"{index + 1:02d}-shot.png"
        (run_dir / "screenshots" / name).write_bytes(f"shot-{index}".encode() if distinct else b"same")
        names.append(name)
    write_json(run_dir / "case-result.json", {"case_loaded": True, "screenshots": names,
                                              "dropped_duplicates": [], "framing": four_up,
                                              "framing_3d_only": one_up})
    write_json(run_dir / "reload-result.json", {"requested_exit_code": 0})
    write_json(run_dir / "loaded-code.json", {"matched": True, "files": {
        relative: {"matched": True} for relative in vc.COMMON_FILES}})
    (run_dir / "startup.png").write_bytes(b"png-startup")
    (run_dir / "final.png").write_bytes(b"png-final")
    return names


def fake_execute(*, shots=3, distinct=True, marker=True, raise_exc=None, seen=None, four_up=PRODUCTION, one_up=PRODUCTION):
    def execute(plan, evidence_fn=None):
        if seen is not None:
            seen.append(plan)
        if raise_exc is not None:
            raise raise_exc
        run_dir = Path(plan["run_path"])
        write_slicer_outputs(run_dir, shots=shots, distinct=distinct, four_up=four_up, one_up=one_up)
        log_text = LOG_OK if marker else LOG_OK.replace("DENTOBOT_VISIBLE_CASE_PASS\n", "")
        (run_dir / "slicer.log").write_text(log_text)
        checked = evidence_fn(plan, 0, log_text, True, {}, {}, 0, run_dir / "video/smoke.mkv")
        return {**checked, "launcher_exit_code": 0, "cleanup_confirmed": True}
    return execute


def finalized_run(workspace, status="PASS"):
    """A B-side run directory closed by the production finalize()."""
    run_dir = vc.run_dir_for(workspace, RUN_ID)
    for name in vc.SUBDIRS:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "request.json", {"schema": vc.SCHEMA_REQUEST, "run_id": RUN_ID, "sha": SHA,
                                          "case": "Cases/a.dentocase", "hold_s": 90,
                                          "requested_by": "A:test", "host": "b", "requested_at_utc": "x"})
    (run_dir / "input/a.dentocase").write_bytes(b"case-bytes")
    write_slicer_outputs(run_dir)
    vc.finalize(run_dir, run_id=RUN_ID, sha=SHA, status=status, checks={"case_opened": True},
                case_name="a.dentocase", case_sha256="c" * 64)
    return run_dir


def incomplete_run(workspace):
    run_dir = vc.run_dir_for(workspace, RUN_ID)
    for name in vc.SUBDIRS:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "request.json", {"schema": vc.SCHEMA_REQUEST, "run_id": RUN_ID, "sha": SHA,
                                          "case": "Cases/a.dentocase", "hold_s": 90})
    vc.set_state(run_dir, "running")
    process = subprocess.Popen(["true"])
    process.wait()
    write_json(run_dir / "supervisor.json", {"pid": process.pid, "start_ticks": 1,
                                             "boot_id": vc.boot_id()})
    return run_dir


class ValidationTests(unittest.TestCase):
    def test_run_id_sha_hold_and_case_names_are_checked(self):
        for bad in ("2026100T122000Z", "20261308T122000Z", "20261008t122000Z", "", None):
            with self.subTest(run_id=bad), self.assertRaises(vc.VisibleCaseError):
                vc.validate_run_id(bad)
        for bad in ("A" * 40, "a" * 39, "g" * 40, None):
            with self.subTest(sha=bad), self.assertRaises(vc.VisibleCaseError):
                vc.validate_sha(bad)
        for bad in (9, 301, True, "90", None):
            with self.subTest(hold=bad), self.assertRaises(vc.VisibleCaseError):
                vc.validate_hold(bad)
        for bad in ("/etc/a.dentocase", "../a.dentocase", "Cases/a.txt", "Cases/a\\b.dentocase", "", "Cases/a\n.dentocase"):
            with self.subTest(case=bad), self.assertRaises(vc.VisibleCaseError):
                vc.validate_case_name(bad)
        self.assertEqual(vc.validate_case_name("Cases/a b.dentocase"), "Cases/a b.dentocase")

    def test_case_resolution_refuses_escape_suffix_and_directories(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        workspace, _ = make_workspace(root, "ws")
        outside = root / "outside.dentocase"
        outside.write_bytes(b"x")
        (workspace / "data/Cases/escape.dentocase").symlink_to(outside)
        (workspace / "data/Cases/dir.dentocase").mkdir()
        (workspace / "data/Cases/inside.dentocase").symlink_to(workspace / "data/Cases/a.dentocase")
        self.assertEqual(vc.resolve_case(workspace, "Cases/a.dentocase").name, "a.dentocase")
        self.assertEqual(vc.resolve_case(workspace, "Cases/inside.dentocase").name, "a.dentocase")
        with self.assertRaisesRegex(vc.VisibleCaseError, "escapes"):
            vc.resolve_case(workspace, "Cases/escape.dentocase")
        with self.assertRaisesRegex(vc.VisibleCaseError, "regular"):
            vc.resolve_case(workspace, "Cases/dir.dentocase")
        with self.assertRaisesRegex(vc.VisibleCaseError, "does not exist"):
            vc.resolve_case(workspace, "Cases/missing.dentocase")

    def test_checkout_must_sit_in_a_ros2_ws_layout(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        with self.assertRaisesRegex(vc.VisibleCaseError, "ros2_ws/src"):
            vc.workspace_for(root / "DentoBot")
        self.assertEqual(vc.workspace_for(root / "ws/ros2_ws/src/DentoBot"), (root / "ws").resolve())


class RunCreationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.ws, self.repo = make_workspace(self.root, "B")
        self.spawned = []

    def spawn(self, argv, log_path):
        self.spawned.append((argv, Path(log_path)))
        return SimpleNamespace(pid=os.getpid())

    def start(self, **overrides):
        options = dict(selected_repo=str(self.repo), worktree_root=str(self.root / "wt"), case="Cases/a.dentocase",
                       sha=SHA, run_id=RUN_ID, hold=90, requested_by="A:tester", detach=True, spawn=self.spawn)
        options.update(overrides)
        return vc.start_run(**options)

    def test_detached_run_creates_files_once_and_reports_accepted(self):
        result = self.start()
        run_dir = vc.run_dir_for(self.ws, RUN_ID)
        self.assertEqual(result, {"run_id": RUN_ID, "run_path": str(run_dir), "state": "accepted"})
        for name in vc.SUBDIRS:
            self.assertTrue((run_dir / name).is_dir(), name)
        request = json.loads((run_dir / "request.json").read_text())
        self.assertEqual(request["schema"], vc.SCHEMA_REQUEST)
        self.assertEqual((request["run_id"], request["sha"], request["case"], request["hold_s"]),
                         (RUN_ID, SHA, "Cases/a.dentocase", 90))
        self.assertEqual(request["requested_by"], "A:tester")
        self.assertEqual(json.loads((run_dir / "STATE.json").read_text())["state"], "accepted")
        argv, log_path = self.spawned[0]
        self.assertEqual(argv[1], str(Path(vc.__file__).resolve()))
        self.assertEqual(argv[2:4], ["supervise", "--run-dir"])
        self.assertEqual(log_path, run_dir / "supervisor.log")
        supervisor = json.loads((run_dir / "supervisor.json").read_text())
        self.assertEqual(supervisor["pid"], os.getpid())

    def test_existing_run_directory_is_refused_and_left_intact(self):
        self.start(detach=True)
        run_dir = vc.run_dir_for(self.ws, RUN_ID)
        before = (run_dir / "request.json").read_bytes()
        with self.assertRaisesRegex(vc.VisibleCaseError, "refusing to overwrite"):
            self.start()
        self.assertEqual((run_dir / "request.json").read_bytes(), before)

    def test_invalid_inputs_create_nothing(self):
        for overrides in ({"case": "/abs/a.dentocase"}, {"case": "Cases/missing.dentocase"}, {"sha": "ABC"},
                          {"hold": 5}, {"run_id": "not-a-run"}, {"worktree_root": None},
                          {"selected_repo": str(self.root / "missing/ros2_ws/src/X")}):
            with self.subTest(overrides=overrides), self.assertRaises(vc.VisibleCaseError):
                self.start(**overrides)
        self.assertFalse((self.ws / "data/dentobot-runs").exists())
        self.assertEqual(self.spawned, [])

    def test_spawn_failure_closes_the_run_as_error(self):
        def failing(argv, log_path):
            raise OSError("no such interpreter")
        with self.assertRaisesRegex(vc.VisibleCaseError, "could not be started"):
            self.start(spawn=failing)
        done = json.loads((vc.run_dir_for(self.ws, RUN_ID) / "DONE.json").read_text())
        self.assertEqual((done["status"], done["verified_at_sha"]), ("ERROR", None))


class DoneAndStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.ws, _ = make_workspace(self.root, "B")
        self.run_dir = self.root / "run"
        self.run_dir.mkdir()
        (self.run_dir / "input").mkdir()
        (self.run_dir / "input/a.dentocase").write_bytes(b"case-bytes")
        write_slicer_outputs(self.run_dir)

    def finalize(self, **overrides):
        options = dict(run_id=RUN_ID, sha=SHA, status="PASS", checks={"case_opened": True},
                       case_name="a.dentocase")
        options.update(overrides)
        return vc.finalize(self.run_dir, **options)

    def test_done_is_published_last_and_only_through_an_atomic_replace(self):
        real_replace = os.replace
        seen = []

        def spy(source, destination):
            if Path(destination).name == "DONE.json":
                seen.append({"done_exists": Path(destination).exists(),
                             "log": (self.run_dir / "RUN_LOG.md").exists(),
                             "result": (self.run_dir / "result.json").exists(),
                             "temp": Path(source).name})
            return real_replace(source, destination)

        with patch.object(vc.os, "replace", side_effect=spy):
            self.finalize()
        self.assertEqual(len(seen), 1)
        self.assertFalse(seen[0]["done_exists"])
        self.assertTrue(seen[0]["log"] and seen[0]["result"])
        self.assertTrue(seen[0]["temp"].startswith(".DONE.json."))

    def test_crash_between_temp_write_and_replace_leaves_no_done(self):
        real_replace = os.replace

        def crash(source, destination):
            if Path(destination).name == "DONE.json":
                raise RuntimeError("simulated crash")
            return real_replace(source, destination)

        with patch.object(vc.os, "replace", side_effect=crash), \
             self.assertRaisesRegex(RuntimeError, "simulated crash"):
            self.finalize()
        self.assertFalse((self.run_dir / "DONE.json").exists())
        self.assertEqual([p.name for p in self.run_dir.iterdir() if p.name.startswith(".DONE.json.")], [])

    def test_manifest_covers_regular_files_and_excludes_done_collected_and_input(self):
        (self.run_dir / "COLLECTED.json").write_text("{}")
        (self.run_dir / "video").mkdir()
        (self.run_dir / "video/DONE.json").write_text("nested marker is evidence, not the terminal marker")
        done = self.finalize()
        paths = {entry["path"] for entry in done["files"]}
        self.assertTrue({"result.json", "RUN_LOG.md", "case-result.json", "screenshots/01-shot.png",
                         "video/DONE.json"} <= paths)
        self.assertFalse({"DONE.json", "COLLECTED.json"} & paths)
        self.assertFalse(any(path.startswith("input/") for path in paths))
        for entry in done["files"]:
            content = (self.run_dir / entry["path"]).read_bytes()
            self.assertEqual((entry["size"], entry["sha256"]),
                             (len(content), hashlib.sha256(content).hexdigest()))
        self.assertEqual(done["verified_at_sha"], SHA)

    def test_symlink_in_run_directory_closes_the_run_as_error(self):
        (self.run_dir / "link.txt").symlink_to(self.run_dir / "case-result.json")
        done = self.finalize(status="PASS")
        self.assertEqual(done["status"], "ERROR")
        self.assertIsNone(done["verified_at_sha"])
        self.assertIn("unexpected entries", done["error"])

    def test_status_reports_each_state_from_disk(self):
        missing = vc.status(self.ws, RUN_ID)
        self.assertEqual(missing["state"], "unknown")
        run_dir = vc.run_dir_for(self.ws, RUN_ID)
        run_dir.mkdir(parents=True)
        self.assertEqual(vc.status(self.ws, RUN_ID)["state"], "incomplete")
        vc.set_state(run_dir, "accepted")
        self.assertEqual(vc.status(self.ws, RUN_ID)["state"], "accepted")
        vc.write_supervisor(run_dir, os.getpid())
        self.assertEqual(vc.status(self.ws, RUN_ID)["state"], "accepted")
        vc.set_state(run_dir, "running")
        live = vc.status(self.ws, RUN_ID)
        self.assertEqual((live["state"], live["supervisor_alive"]), ("running", True))
        marker = json.loads((run_dir / "supervisor.json").read_text())
        write_json(run_dir / "supervisor.json", {**marker, "start_ticks": marker["start_ticks"] + 1})
        reused = vc.status(self.ws, RUN_ID)
        self.assertEqual((reused["state"], reused["supervisor_alive"]), ("incomplete", False))
        write_json(run_dir / "DONE.json", {"status": "FAIL"})
        done = vc.status(self.ws, RUN_ID)
        self.assertEqual((done["state"], done["done"], done["status"]), ("done", True, "FAIL"))

    def test_dead_supervisor_without_done_is_incomplete(self):
        run_dir = incomplete_run(self.ws)
        self.assertEqual(vc.status(self.ws, RUN_ID)["state"], "incomplete")
        self.assertFalse(vc.status(self.ws, RUN_ID)["supervisor_alive"])
        self.assertTrue(run_dir.is_dir())


class SuperviseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.ws, self.repo = make_workspace(self.root, "B")
        (self.repo / "README.md").write_text("selected checkout, must not change\n")
        self.worktree_root = self.root / "wt"
        self.worktree = make_worktree(self.root)
        self.xhost = FakeXhost()
        for patcher in (patch.object(vc.getpass, "getuser", return_value="tester"),
                        patch.object(smoke_runtime, "source_is_clean", return_value=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.run_dir = vc.run_dir_for(self.ws, RUN_ID)
        vc.start_run(selected_repo=str(self.repo), worktree_root=str(self.worktree_root), case="Cases/a.dentocase",
                     sha=SHA, run_id=RUN_ID, hold=90, requested_by="A:tester", detach=True,
                     spawn=lambda argv, log: SimpleNamespace(pid=os.getpid()))

    def supervise(self, execute=None, xhost=None, prepare=None, parity=None):
        return vc.supervise(
            self.run_dir, repo=str(self.repo), worktree_root=str(self.worktree_root),
            prepare=prepare or (lambda repo, sha, root: self.worktree),
            parity=parity or (lambda path: {"passed": True, "checks": {}}),
            execute=execute or fake_execute(), xhost=xhost or self.xhost)

    def done(self):
        return json.loads((self.run_dir / "DONE.json").read_text())

    def repo_snapshot(self):
        return {str(p.relative_to(self.repo)): p.read_bytes() for p in self.repo.rglob("*") if p.is_file()}

    def test_pass_publishes_verified_done_with_manifest_and_scoped_grant(self):
        before = self.repo_snapshot()
        self.supervise()
        done = self.done()
        self.assertEqual((done["status"], done["verified_at_sha"], done["error"]), ("PASS", SHA, None))
        self.assertTrue(all(done["checks"].values()), done["checks"])
        self.assertEqual(self.xhost.calls, ["+SI:localuser:tester", "-SI:localuser:tester"])
        paths = {entry["path"] for entry in done["files"]}
        self.assertNotIn("DONE.json", paths)
        self.assertFalse(any(path.startswith("input/") for path in paths))
        self.assertTrue((self.run_dir / "input/a.dentocase").is_file())
        self.assertIn(f"verified at {SHA}", (self.run_dir / "RUN_LOG.md").read_text())
        self.assertEqual(self.repo_snapshot(), before)
        self.assertEqual(json.loads((self.run_dir / "STATE.json").read_text())["state"], "finalizing")

    def test_failed_verification_publishes_fail_without_verified_sha(self):
        self.supervise(execute=fake_execute(marker=False))
        done = self.done()
        self.assertEqual((done["status"], done["verified_at_sha"]), ("FAIL", None))
        self.assertFalse(done["checks"]["visible_case_marker"])

    def test_fallback_or_unavailable_framing_is_never_reported_as_success(self):
        fallback = {"method": "reset_3d_camera", "status": "fallback", "reason": "production framing reported: boom"}
        unavailable = {"method": "reset_3d_camera", "status": "unavailable", "reason": "no planning target"}
        for four_up, one_up in ((fallback, PRODUCTION), (PRODUCTION, unavailable)):
            with self.subTest(four_up=four_up["status"], one_up=one_up["status"]):
                self.supervise(execute=fake_execute(four_up=four_up, one_up=one_up))
                done = self.done()
                self.assertEqual((done["status"], done["verified_at_sha"]), ("FAIL", None))
                self.assertFalse(done["checks"]["target_framing"])
                self.assertFalse(done["framing"]["framed"])
                self.assertIn("NOT DEMONSTRATED", (self.run_dir / "RUN_LOG.md").read_text())
                for name in ("DONE.json",):
                    (self.run_dir / name).unlink()  # allow the next subTest to supervise the same directory again

    def test_production_framing_on_both_layouts_is_recorded_as_framed(self):
        self.supervise()
        done = self.done()
        self.assertTrue(done["checks"]["target_framing"])
        self.assertEqual((done["framing"]["four_up"]["status"], done["framing"]["one_up_3d"]["status"]),
                         ("production", "production"))
        self.assertIn("production target-framing action", (self.run_dir / "RUN_LOG.md").read_text())

    def test_framing_summary_covers_every_status_and_missing_data(self):
        self.assertFalse(vc.framing_summary(None)["framed"])
        self.assertEqual(vc.framing_summary({})["four_up"]["status"], "not_run")
        self.assertEqual(vc.framing_summary({"framing": {"status": "bogus"}})["four_up"]["status"], "not_run")
        self.assertTrue(vc.framing_summary({"framing": PRODUCTION, "framing_3d_only": PRODUCTION})["framed"])

    def test_duplicate_screenshots_fail_the_distinctness_check(self):
        self.supervise(execute=fake_execute(distinct=False))
        self.assertEqual(self.done()["status"], "FAIL")
        self.assertFalse(self.done()["checks"]["screenshots_distinct"])

    def test_failed_revoke_makes_the_run_fail_not_pass(self):
        self.supervise(xhost=FakeXhost(revoke=False))
        done = self.done()
        self.assertEqual(done["status"], "FAIL")
        self.assertFalse(done["checks"]["xhost_revoked"])
        self.assertIn("not revoked", done["error"])

    def test_execute_exception_is_error_and_revoke_is_still_attempted(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.supervise(execute=fake_execute(raise_exc=RuntimeError("docker went away")))
        done = self.done()
        self.assertEqual((done["status"], done["verified_at_sha"]), ("ERROR", None))
        self.assertIn("RuntimeError", done["error"])
        self.assertEqual(self.xhost.calls[-1], "-SI:localuser:tester")

    def test_sigterm_style_system_exit_publishes_error_then_propagates(self):
        with self.assertRaises(SystemExit):
            self.supervise(execute=fake_execute(raise_exc=SystemExit(143)))
        self.assertEqual(self.done()["status"], "ERROR")
        self.assertEqual(self.xhost.calls[-1], "-SI:localuser:tester")

    def test_finished_run_is_never_supervised_again(self):
        self.supervise()
        first = (self.run_dir / "DONE.json").read_bytes()
        with self.assertRaisesRegex(vc.VisibleCaseError, "never supervised again"):
            self.supervise(execute=fake_execute(marker=False))
        self.assertEqual((self.run_dir / "DONE.json").read_bytes(), first)

    def test_sha_not_on_origin_is_error_and_execute_never_runs(self):
        seen = []
        git = FakeGit(contained="")
        prepare = lambda repo, sha, root: vc.prepare_source(repo, sha, root, git=git)
        self.supervise(prepare=prepare, execute=fake_execute(seen=seen))
        self.assertEqual(self.done()["status"], "ERROR")
        self.assertIn("not published on origin", self.done()["error"])
        self.assertEqual(seen, [])
        self.assertEqual(self.xhost.calls, [])

    def test_dirty_existing_worktree_is_error_and_never_reset_or_cleaned(self):
        target = self.worktree
        self.assertEqual(target.name, f"DentoBot-visible-{SHA[:12]}")
        (target / "local-edit.txt").write_text("keep me")
        git = FakeGit()
        prepare = lambda repo, sha, root: vc.prepare_source(repo, sha, root, git=git,
                                                            is_clean=lambda path, sha: False)
        self.supervise(prepare=prepare)
        self.assertEqual(self.done()["status"], "ERROR")
        self.assertEqual((target / "local-edit.txt").read_text(), "keep me")
        verbs = {args[0] for args in git.calls}
        self.assertFalse(verbs & {"reset", "clean", "checkout", "stash"}, git.calls)

    def test_parity_failure_is_error_and_records_parity(self):
        seen = []
        self.supervise(parity=lambda path: {"passed": False, "checks": {"native_git": {"passed": False}}},
                       execute=fake_execute(seen=seen))
        self.assertEqual(self.done()["status"], "ERROR")
        self.assertEqual(seen, [])
        self.assertFalse(json.loads((self.run_dir / "parity.json").read_text())["passed"])

    def test_refused_scoped_grant_never_runs_the_case(self):
        seen = []
        refused = FakeXhost(grant=False)
        self.supervise(xhost=refused, execute=fake_execute(seen=seen))
        self.assertEqual(self.done()["status"], "ERROR")
        self.assertEqual(seen, [])
        self.assertEqual(refused.calls, ["+SI:localuser:tester"])

    def test_bootstrap_plan_is_written_for_the_pinned_worktree(self):
        seen = []
        self.supervise(execute=fake_execute(seen=seen))
        plan = seen[0]
        self.assertEqual(plan["repo"], str(self.worktree))
        self.assertEqual(plan["timeout_sec"], 90 + 600)
        self.assertIn("export DISPLAY=:0", plan["argv"][-1])
        self.assertNotIn("xvfb-run", plan["argv"][-1])
        self.assertIn("DISPLAY=:0", plan["argv"])
        bootstrap = (self.run_dir / "bootstrap.py").read_text()
        self.assertTrue(bootstrap.startswith("PLAN = "))
        compile(bootstrap, "bootstrap.py", "exec")


class PrepareSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def test_published_sha_gets_a_detached_worktree_at_that_sha(self):
        git = FakeGit()
        target = vc.prepare_source(self.root / "sel", SHA, self.root / "wt", git=git, is_clean=lambda p, s: True)
        self.assertEqual(target, self.root / "wt" / f"DentoBot-visible-{SHA[:12]}")
        self.assertIn(("worktree", "add", "--detach", str(target), SHA), git.calls)
        self.assertEqual(git.calls[0], ("fetch", "--quiet", "origin"))

    def test_clean_existing_worktree_is_reused_without_adding(self):
        target = self.root / "wt" / f"DentoBot-visible-{SHA[:12]}"
        target.mkdir(parents=True)
        git = FakeGit()
        self.assertEqual(vc.prepare_source(self.root / "sel", SHA, self.root / "wt", git=git,
                                           is_clean=lambda p, s: True), target)
        self.assertFalse(any(args[:2] == ("worktree", "add") for args in git.calls))

    def test_symlinked_target_is_refused(self):
        target = self.root / "wt" / f"DentoBot-visible-{SHA[:12]}"
        target.parent.mkdir(parents=True)
        target.symlink_to(self.root)
        with self.assertRaisesRegex(vc.VisibleCaseError, "symlink"):
            vc.prepare_source(self.root / "sel", SHA, self.root / "wt", git=FakeGit(), is_clean=lambda p, s: True)


class PlanAndBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.ws, _ = make_workspace(self.root, "B")
        self.worktree = make_worktree(self.root)
        self.run_dir = vc.run_dir_for(self.ws, RUN_ID)

    def build(self, **overrides):
        options = dict(workspace=self.ws, worktree=self.worktree, run_dir=self.run_dir, sha=SHA, hold=90,
                       case_name="a.dentocase", lock={"image_id": IMAGE_ID, "image_name": "dentobot/slicerros2:test"},
                       config={"DENTOBOT_BACKEND_PYTHON": str(self.root / "env/bin/python")},
                       hashes={relative: "f" * 64 for relative in vc.COMMON_FILES},
                       bootstrap_template=BOOTSTRAP.read_text(encoding="utf-8"))
        options.update(overrides)
        return vc.build_plan(**options)

    def test_plan_is_pure_and_pins_the_worktree_and_image(self):
        with patch.object(subprocess, "run", side_effect=AssertionError("no subprocess in plan building")):
            plan, bootstrap = self.build()
        container = f"/workspace/ros2_ws/src/{self.worktree.name}"
        self.assertEqual((plan["repo"], plan["expected_sha"], plan["image_id"]),
                         (str(self.worktree), SHA, IMAGE_ID))
        self.assertEqual(plan["timeout_sec"], 90 + 600)
        self.assertEqual(plan["argv"][2:6], ["-e", "DISPLAY=:0", "-e",
                                             f"TMPDIR=/workspace/data/dentobot-runs/2026-10-08/{vc.TASK}-{RUN_ID}/tmp"])
        script = plan["argv"][-1]
        self.assertEqual(script.count("export DISPLAY=:0"), 1)
        self.assertNotIn("xvfb-run", script)
        payload = ast.literal_eval(bootstrap.split("\n", 1)[0][len("PLAN = "):])
        self.assertEqual(payload["repo"], container)
        self.assertEqual(payload["case"], f"{payload['evidence']}/input/a.dentocase")
        compile(bootstrap, "bootstrap.py", "exec")

    def test_relative_backend_python_and_bad_lock_are_refused(self):
        with self.assertRaisesRegex(vc.VisibleCaseError, "absolute"):
            self.build(config={"DENTOBOT_BACKEND_PYTHON": "python"})
        with self.assertRaisesRegex(vc.VisibleCaseError, "runtime lock"):
            vc.read_runtime_lock(self.root / "missing-worktree")


class BootstrapTests(unittest.TestCase):
    def test_compiles_with_plan_prefix_and_never_names_a_modal_helper(self):
        text = BOOTSTRAP.read_text(encoding="utf-8")
        compile("PLAN = {}\n" + text, "visible_case_bootstrap.py", "exec")
        tree = ast.parse(text)
        names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        names |= {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        strings = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        modal = ("errorDisplay", "infoDisplay", "warningDisplay")
        calls = {node.func.attr for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertFalse(calls & set(modal), "the bootstrap must never call a modal helper itself")
        self.assertTrue(set(modal) <= strings, "framing must guard the modal helpers it may trigger")
        self.assertIn("onFramePlanningTarget", names)
        self.assertIn("_planningTargetBoundsWorld", names)
        self.assertLess(text.index("_planningTargetBoundsWorld()"), text.index("onFramePlanningTarget()"))

    def run_bootstrap(self, *, bounds, shots, framing_message=None):
        """Execute the bootstrap against fake qt/slicer and drive its timers in order."""
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        out = root / "evidence"
        out.mkdir()
        plan = {"repo": str(root / "repo"), "evidence": str(out), "case": "/x/input/a.dentocase",
                "hold_s": 2, "common_files": [], "hashes": {}}
        qt, slicer = MagicMock(), MagicMock()
        timers = []
        qt.QTimer.singleShot.side_effect = lambda ms, callback: timers.append((ms, callback))
        widget = MagicMock()
        if bounds is None:
            widget._planningTargetBoundsWorld.side_effect = ValueError("no planning target")
        else:
            widget._planningTargetBoundsWorld.return_value = bounds
        slicer.modules.dentoworkflow.widgetRepresentation.return_value.self.return_value = widget
        original_error_display = slicer.util.errorDisplay
        if framing_message:
            widget.onFramePlanningTarget.side_effect = lambda: slicer.util.errorDisplay(framing_message)
        queue = list(shots)
        slicer.util.mainWindow.return_value.grab.return_value.save.side_effect = (
            lambda path: (Path(path).write_bytes(queue.pop(0)), True)[1])
        slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView = "4up"
        slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView = "1up3d"
        slicer.app.layoutManager.return_value.threeDViewCount = 1
        namespace = {"PLAN": plan}
        with patch.dict(sys.modules, {"qt": qt, "slicer": slicer}), contextlib.redirect_stdout(io.StringIO()):
            exec(compile(BOOTSTRAP.read_text(encoding="utf-8"), str(BOOTSTRAP), "exec"), namespace)
            timers[0][1]()  # start(): schedules open_case
            by_name = {callback.__name__: callback for _, callback in timers}
            by_name["open_case"]()  # schedules hold_shot at mid-hold and finish at hold end
            by_name = {callback.__name__: callback for _, callback in timers}
            by_name["hold_shot"]()
            by_name["finish"]()
        return SimpleNamespace(out=out, slicer=slicer, widget=widget, namespace=namespace,
                               original_error_display=original_error_display)

    def test_framing_falls_back_without_a_planning_target_and_drops_duplicate_shots(self):
        run = self.run_bootstrap(bounds=None, shots=[b"one", b"two", b"two", b"three", b"three"])
        result = json.loads((run.out / "case-result.json").read_text())
        self.assertEqual(result["framing"], {"method": "reset_3d_camera", "status": "unavailable",
                                             "reason": "no planning target"})
        self.assertEqual(result["framing_3d_only"]["status"], "unavailable")
        self.assertFalse(vc.framing_summary(result)["framed"])
        self.assertEqual(result["screenshots"], ["01-startup.png", "02-case-loaded.png", "04-3d-only-target-framed.png"])
        self.assertEqual(result["dropped_duplicates"], ["03-four-up-target-framed", "05-before-exit"])
        run.widget.onFramePlanningTarget.assert_not_called()
        run.slicer.util.errorDisplay.assert_not_called()
        run.slicer.util.infoDisplay.assert_not_called()
        run.slicer.util.exit.assert_called_with(0)

    def test_message_reported_by_production_framing_is_recorded_not_shown(self):
        run = self.run_bootstrap(bounds=((0, 1), (0, 1), (0, 1)), shots=[b"a", b"b", b"c", b"d", b"e"],
                                 framing_message="no trajectory")
        result = json.loads((run.out / "case-result.json").read_text())
        self.assertEqual((result["framing"]["method"], result["framing"]["status"]), ("reset_3d_camera", "fallback"))
        self.assertIn("no trajectory", result["framing"]["reason"])
        self.assertFalse(vc.framing_summary(result)["framed"])
        run.slicer.util.errorDisplay.assert_not_called()  # the original helper is restored afterwards, never invoked
        self.assertIs(run.slicer.util.errorDisplay, run.original_error_display)

    def test_production_framing_is_used_only_after_bounds_are_available(self):
        run = self.run_bootstrap(bounds=((0, 1), (0, 1), (0, 1)), shots=[b"a", b"b", b"c", b"d", b"e"])
        result = json.loads((run.out / "case-result.json").read_text())
        self.assertEqual(result["framing"]["method"], "onFramePlanningTarget")
        self.assertEqual(result["framing_3d_only"]["method"], "onFramePlanningTarget")
        self.assertTrue(vc.framing_summary(result)["framed"])
        self.assertEqual(run.widget.onFramePlanningTarget.call_count, 2)  # four-up, then one-up 3D
        self.assertEqual(len(result["screenshots"]), 5)
        self.assertEqual(result["dropped_duplicates"], [])


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name).resolve() / "run"
        self.run_dir.mkdir()
        (self.run_dir / "input").mkdir()
        (self.run_dir / "input/a.dentocase").write_bytes(b"case-bytes")
        self.case_sha = vc.sha256_file(self.run_dir / "input/a.dentocase")
        self.base_checks = {"ros_launcher_exit_code": True, "five_reload_rows_six_assertions": True,
                            "success_markers": True, "video_manifest_checksum_and_decode": True,
                            "slicer_process_exit_code": True}

    def evidence(self, xhost_state=None):
        base = lambda *args: {"checks": dict(self.base_checks), "reload_reports": 5, "runtime_verified": True}
        return vc.make_evidence(case_copy=self.run_dir / "input/a.dentocase", case_sha256=self.case_sha,
                                parity_passed=True, xhost_state=xhost_state or {"revoked": True}, base=base)

    def call(self, evidence, log=LOG_OK):
        return evidence({"run_path": str(self.run_dir)}, 0, log, True, {}, {}, 0, self.run_dir / "video/x.mkv")

    def test_evidence_drops_reload_checks_and_adds_visible_checks(self):
        write_slicer_outputs(self.run_dir)
        report = self.call(self.evidence())
        checks = report["checks"]
        for dropped in ("five_reload_rows_six_assertions", "success_markers", "video_manifest_checksum_and_decode"):
            self.assertNotIn(dropped, checks)
        self.assertNotIn("reload_reports", report)
        for added in ("case_opened", "visible_case_marker", "screenshots_distinct", "case_input_unchanged",
                      "xhost_revoked", "parity_passed", "target_framing"):
            self.assertIn(added, checks)
        self.assertTrue(report["runtime_verified"])
        self.assertIn("not visibility evidence", report["evidence_note"])

    def test_duplicate_or_too_few_screenshots_fail(self):
        write_slicer_outputs(self.run_dir, shots=3, distinct=False)
        self.assertFalse(self.call(self.evidence())["checks"]["screenshots_distinct"])
        write_slicer_outputs(self.run_dir, shots=2)
        self.assertFalse(self.call(self.evidence())["checks"]["screenshots_distinct"])

    def test_missing_marker_and_tampered_input_fail_their_checks(self):
        write_slicer_outputs(self.run_dir)
        self.assertFalse(self.call(self.evidence(), log="no marker here")["checks"]["visible_case_marker"])
        (self.run_dir / "input/a.dentocase").write_bytes(b"changed")
        self.assertFalse(self.call(self.evidence())["checks"]["case_input_unchanged"])


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.b_ws, _ = make_workspace(self.root, "B")
        self.a_ws, self.a_repo = make_workspace(self.root, "A")
        self.b_run = finalized_run(self.b_ws, "PASS")
        self.b_path = str(self.b_run)
        self.transfers = []

    def transfer_from(self, source, mutate=None):
        def transfer(host, run_path, dest):
            self.transfers.append((host, run_path))
            shutil.copytree(source, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("input"))
            if mutate:
                mutate(Path(dest))
        return transfer

    def collect(self, status_answers, transfer=None, accept=False):
        remote = FakeRemote(status=status_answers)
        return vc.collect(run_id=RUN_ID, remote=remote, local_workspace=str(self.a_repo),
                          accept_incomplete=accept, transfer=transfer or self.transfer_from(self.b_run))

    def done_answer(self):
        return {"run_id": RUN_ID, "state": "done", "done": True, "run_path": self.b_path, "status": "PASS"}

    def dest_dir(self):
        return self.a_ws / "data/dentobot-runs/2026-10-08" / f"{vc.TASK}-{RUN_ID}"

    def snapshot(self, folder):
        return {str(p.relative_to(folder)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in folder.rglob("*") if p.is_file()}

    def test_collect_publishes_verified_copy_without_input_and_no_temp_left(self):
        code, result = self.collect([self.done_answer()])
        self.assertEqual((code, result["status"], result["label"], result["already_collected"]),
                         (0, "PASS", f"verified at {SHA}", False))
        dest = self.dest_dir()
        self.assertEqual(result["local_path"], str(dest))
        self.assertFalse((dest / "input").exists())
        collected = json.loads((dest / "COLLECTED.json").read_text())
        self.assertEqual(collected["done_sha256"], vc.sha256_file(dest / "DONE.json"))
        self.assertTrue(collected["host"])
        self.assertEqual([p.name for p in dest.parent.iterdir() if ".collecting-" in p.name], [])

    def test_second_collect_is_idempotent_and_touches_nothing_in_destination(self):
        self.collect([self.done_answer()])
        before = self.snapshot(self.dest_dir())
        code, second = self.collect([self.done_answer()])
        self.assertEqual(code, 0)
        self.assertTrue(second["already_collected"])
        self.assertEqual(self.snapshot(self.dest_dir()), before)

    def test_different_existing_destination_is_refused_and_preserved(self):
        self.collect([self.done_answer()])
        before = self.snapshot(self.dest_dir())
        changed = finalized_run(self.b_ws, "FAIL")
        with self.assertRaisesRegex(vc.VisibleCaseError, "different collection"):
            self.collect([{**self.done_answer(), "run_path": str(changed)}],
                         transfer=self.transfer_from(changed))
        self.assertEqual(self.snapshot(self.dest_dir()), before)

    def test_corrupt_transfer_is_refused_with_no_destination(self):
        def corrupt(dest):
            (dest / "screenshots/01-shot.png").write_bytes(b"tampered in transit")
        with self.assertRaisesRegex(vc.VisibleCaseError, "manifest verification failed"):
            self.collect([self.done_answer()], transfer=self.transfer_from(self.b_run, mutate=corrupt))
        self.assertFalse(self.dest_dir().exists())
        self.assertEqual([p.name for p in self.dest_dir().parent.iterdir() if ".collecting-" in p.name], [])

    def test_complete_collection_supersedes_an_earlier_incomplete_one_without_deleting_it(self):
        other_ws, _ = make_workspace(self.root, "B-incomplete")
        run = incomplete_run(other_ws)
        answer = {"run_id": RUN_ID, "state": "incomplete", "done": False, "run_path": str(run)}
        self.collect([answer], transfer=self.transfer_from(run), accept=True)
        incomplete_copy = self.snapshot(self.dest_dir())
        code, result = self.collect([self.done_answer()])
        self.assertEqual((code, result["status"], result["already_collected"]), (0, "PASS", False))
        self.assertTrue((self.dest_dir() / "DONE.json").is_file())
        aside = Path(result["superseded_incomplete"])
        self.assertTrue(aside.name.startswith(self.dest_dir().name + ".incomplete-"))
        self.assertEqual(self.snapshot(aside), incomplete_copy)  # kept byte for byte
        again = self.collect([self.done_answer()])[1]            # now idempotent on the complete copy
        self.assertTrue(again["already_collected"])
        self.assertNotIn("superseded_incomplete", again)

    def test_incomplete_collection_never_replaces_a_complete_one(self):
        self.collect([self.done_answer()])
        before = self.snapshot(self.dest_dir())
        other_ws, _ = make_workspace(self.root, "B-incomplete")
        run = incomplete_run(other_ws)
        answer = {"run_id": RUN_ID, "state": "incomplete", "done": False, "run_path": str(run)}
        with self.assertRaisesRegex(vc.VisibleCaseError, "different collection"):
            self.collect([answer], transfer=self.transfer_from(run), accept=True)
        self.assertEqual(self.snapshot(self.dest_dir()), before)

    def test_incomplete_run_needs_the_flag_and_is_never_pass(self):
        other_ws, _ = make_workspace(self.root, "B-incomplete")
        run = incomplete_run(other_ws)
        answer = {"run_id": RUN_ID, "state": "incomplete", "done": False, "run_path": str(run)}
        with self.assertRaises(vc.NotFinal) as caught:
            self.collect([answer], transfer=self.transfer_from(run))
        self.assertIn("collect --run-id", str(caught.exception))
        self.assertEqual(self.transfers, [])
        self.assertFalse(self.dest_dir().exists())
        code, result = self.collect([answer], transfer=self.transfer_from(run), accept=True)
        self.assertEqual((code, result["status"]), (2, "INCOMPLETE"))
        self.assertTrue(result["label"].startswith("INCOMPLETE"))
        self.assertFalse((self.dest_dir() / "input").exists())

    def test_running_run_is_not_collected(self):
        with self.assertRaises(vc.NotFinal):
            self.collect([{"run_id": RUN_ID, "state": "running", "done": False, "run_path": self.b_path}])
        self.assertFalse(self.dest_dir().exists())

    def test_relative_run_path_outside_the_run_tree_is_refused(self):
        with self.assertRaisesRegex(vc.VisibleCaseError, "unexpected run path"):
            self.collect([{**self.done_answer(), "run_path": "/tmp/evil/../x"}])


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.b_ws, _ = make_workspace(self.root, "B")
        self.a_ws, self.a_repo = make_workspace(self.root, "A")
        self.b_run = finalized_run(self.b_ws, "PASS")
        self.log = []

    def accepted(self):
        return {"run_id": RUN_ID, "run_path": str(vc.run_dir_for(self.b_ws, RUN_ID)), "state": "accepted"}

    def request(self, remote, git=None, **overrides):
        options = dict(case="Cases/a.dentocase", repo=str(self.a_repo), hold=90, poll_interval=5, max_wait=1800,
                       remote=remote, local_workspace=str(self.a_repo), cwd=self.a_repo,
                       git=git or FakeGit(), transfer=self.transfer, sleep=lambda seconds: None,
                       clock=Clock(), run_id=RUN_ID, log=self.log.append)
        options.update(overrides)
        return vc.request(**options)

    def transfer(self, host, run_path, dest):
        shutil.copytree(self.b_run, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("input"))

    def test_refusals_happen_before_any_transport_call(self):
        cases = (
            ({"git": FakeGit(status=" M dirty.py\n")}, "dirty"),
            ({"git": FakeGit(contained="")}, "not on origin"),
            ({"sha": "ABC"}, "sha must be"),
            ({"hold": 500}, "hold must be"),
            ({"case": "/etc/passwd"}, "case must be"),
        )
        for overrides, message in cases:
            remote = FakeRemote(run=[self.accepted()])
            git = overrides.pop("git", None)
            with self.subTest(message=message), self.assertRaisesRegex(vc.VisibleCaseError, message):
                self.request(remote, git=git, **overrides)
            self.assertEqual(remote.calls, [])

    def test_default_source_is_the_git_toplevel_of_the_working_directory(self):
        git = FakeGit()
        git.table[("rev-parse", "--show-toplevel")] = f"{self.a_repo}\n"
        remote = FakeRemote(run=[self.accepted()])
        code, payload, _ = self.request(remote, git=git, repo=None, no_wait=True)
        self.assertEqual(code, 0)
        self.assertIn(("rev-parse", "--show-toplevel"), git.calls)
        self.assertEqual(payload["sha"], SHA)

    def test_no_wait_prints_the_run_and_returns_without_polling(self):
        remote = FakeRemote(run=[self.accepted()])
        code, payload, _ = self.request(remote, no_wait=True)
        self.assertEqual(code, 0)
        self.assertEqual((payload["run_id"], payload["state"]), (RUN_ID, "accepted"))
        self.assertEqual([call[0] for call in remote.calls], ["run"])
        self.assertEqual(remote.calls[0][remote.calls[0].index("--sha") + 1], SHA)

    def test_success_polls_then_collects_as_verified(self):
        done = {"run_id": RUN_ID, "state": "done", "done": True, "status": "PASS",
                "run_path": str(vc.run_dir_for(self.b_ws, RUN_ID))}
        remote = FakeRemote(run=[self.accepted()], status=[{"state": "running", "done": False}, done])
        code, payload, _ = self.request(remote)
        self.assertEqual((code, payload["status"], payload["label"]), (0, "PASS", f"verified at {SHA}"))
        self.assertTrue(Path(payload["local_path"]).is_dir())

    def test_fail_verdict_is_collected_but_exits_two(self):
        failed = finalized_run(self.b_ws, "FAIL")
        done = {"run_id": RUN_ID, "state": "done", "done": True, "status": "FAIL",
                "run_path": str(failed)}
        code, payload, _ = self.request(FakeRemote(run=[self.accepted()], status=[done]))
        self.assertEqual((code, payload["status"]), (2, "FAIL"))

    def test_transport_dying_mid_wait_exits_three_with_collect_hint_and_nothing_local(self):
        remote = FakeRemote(run=[self.accepted()],
                            status=[{"state": "running", "done": False},
                                    vc.TransportError("ssh connection reset")])
        with self.assertRaises(vc.NotFinal) as caught:
            self.request(remote)
        self.assertIn(f"collect --run-id {RUN_ID}", str(caught.exception))
        self.assertEqual(sum(1 for call in remote.calls if call[0] == "status"), vc.MAX_MISSES + 2)
        self.assertFalse((self.a_ws / "data/dentobot-runs").exists())

    def test_lost_initial_run_answer_falls_back_to_status_polling(self):
        done = {"run_id": RUN_ID, "state": "done", "done": True, "status": "PASS",
                "run_path": str(vc.run_dir_for(self.b_ws, RUN_ID))}
        remote = FakeRemote(run=[vc.TransportError("ssh dropped after the request")],
                            status=[{"state": "accepted", "done": False}, done])
        code, payload, _ = self.request(remote)
        self.assertEqual((code, payload["status"]), (0, "PASS"))
        self.assertEqual(remote.calls[0][0], "run")
        self.assertIn("polling", " ".join(self.log))

    def test_max_wait_exceeded_exits_three_with_hint(self):
        remote = FakeRemote(run=[self.accepted()], status=[{"state": "running", "done": False}])
        with self.assertRaisesRegex(vc.NotFinal, "not final after 150s"):
            self.request(remote, max_wait=150, clock=Clock(step=100))

    def test_incomplete_run_stops_polling_and_needs_explicit_accept(self):
        remote = FakeRemote(run=[self.accepted()],
                            status=[{"state": "incomplete", "done": False}])
        with self.assertRaisesRegex(vc.NotFinal, "accept-incomplete"):
            self.request(remote)

    def test_argv_items_reach_the_remote_as_single_arguments(self):
        home = self.root / "home"
        (home / ".local/bin").mkdir(parents=True)
        fake = home / ".local/bin/dentobot"
        fake.write_text(f"#!{sys.executable}\nimport json, sys\nprint(json.dumps({{'argv': sys.argv[1:]}}))\n")
        fake.chmod(0o755)
        odd = "Cases/it's \"odd\"; $HOME `x` y.dentocase"
        remote = vc.Remote.__new__(vc.Remote)
        remote.machine = handoff.Machine("B", {"host": None, "repo": str(self.b_ws / "ros2_ws/src/DentoBot"),
                                               "output": str(self.root / "out")})
        with patch.dict(os.environ, {"HOME": str(home)}):
            payload = remote.call(["run", "--case", odd, "--sha", SHA, "--run-id", RUN_ID, "--detach"])
        self.assertEqual(payload["argv"], ["visible-case", "run", "--case", odd, "--sha", SHA,
                                           "--run-id", RUN_ID, "--detach"])

    def test_ssh_timeout_names_the_tailscale_check(self):
        remote = vc.Remote.__new__(vc.Remote)
        remote.machine = MagicMock(host="dentobot-b")
        remote.machine.run.side_effect = RuntimeError("B: command timed out after 60s")
        with self.assertRaisesRegex(vc.TransportError, "Tailscale SSH check link"):
            remote.call(["status", "--run-id", RUN_ID])

    def test_remote_must_be_a_real_host(self):
        with self.assertRaisesRegex(vc.VisibleCaseError, "remote host"):
            vc.Remote(handoff.Machine("B", {"host": None, "repo": "/a", "output": "/b"}))


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.ws, _ = make_workspace(self.root, "B")

    def test_run_on_a_and_request_on_b_are_refused_before_any_ssh(self):
        args = SimpleNamespace(case="Cases/a.dentocase", sha=None, repo=None, hold=90, no_wait=True,
                               poll_interval=5, max_wait=60, visible_case_command="request")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()), \
             patch.object(handoff, "Machine") as machine:
            code = vc.cmd_request(args, active="B", machines={"B": {"host": "dentobot-b", "repo": "/x", "output": "/y"}})
        machine.assert_not_called()
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue().strip().splitlines()[-1])["error"],
                         "visible-case request runs on A")

    def test_status_command_prints_human_text_then_one_json_line(self):
        args = SimpleNamespace(run_id=RUN_ID)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = vc.cmd_status(args, active="B", machines={"B": {"host": None, "repo": str(self.ws / "ros2_ws/src/DentoBot"),
                                                                 "output": "/o"}})
        lines = out.getvalue().strip().splitlines()
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("run "))
        self.assertEqual(json.loads(lines[-1])["state"], "unknown")

    def test_supervise_entry_point_refuses_a_bad_run_directory_with_exit_two(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = vc.main(["supervise", "--run-dir", str(self.root / "nope"), "--repo",
                            str(self.ws / "ros2_ws/src/DentoBot"), "--worktree-root", str(self.root)])
        self.assertEqual(code, 2)
        self.assertIn("task", err.getvalue())


if __name__ == "__main__":
    unittest.main()
