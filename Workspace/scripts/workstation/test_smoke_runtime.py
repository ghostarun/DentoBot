from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import smoke_runtime as smoke


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


class SmokeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        config_keys = ("DENTOBOT_BACKEND_PYTHON", "DENTOBOT_BACKEND_DEVICE",
                       "DENTOBOT_BACKEND_EXECUTION_MODE", "DENTOBOT_WORKSPACE_ROOT",
                       "DENTOBOT_HOST_UID", "DENTOBOT_HOST_GID", "DENTOBOT_TOTALSEG_HOME_DIR")
        self.env_patch = patch.dict(os.environ, {key: "" for key in config_keys})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        root = Path(self.temp.name)
        self.workspace = root / "workspace"
        self.repo = self.workspace / "ros2_ws/src/DentoBot"
        (self.repo / "Workspace/scripts").mkdir(parents=True)
        (self.repo / "Workspace/scripts/launch-dentoworkflow.bash").write_text(
            'totalseg_home_dir="${DENTOBOT_TOTALSEG_HOME_DIR:-/workspace/data/model-cache/totalsegmentator}"\n'
        )
        (self.repo / "Workspace/compose.yaml").write_text("services:\n  slicer:\n    image: dentobot/slicerros2:test\n")
        test_dir = self.repo / "Testing"
        test_dir.mkdir()
        (test_dir / "run_dentobot_slicer_reload_smoke.py").write_text(
            "reload_action_available = True\n_workflowReloadMenuAction = True\naction.trigger()\n"
        )
        (test_dir / "record_slicer_screen.py").write_text("# existing screen recorder\n")
        module = self.repo / "DENTOWorkflow"
        (module / "Resources/Python/dentobot_workflow").mkdir(parents=True)
        (module / "Resources/Python/DENTOROS2Bridge.py").write_text("# bridge\n")
        for name in ("DENTOWorkflow.py", "Resources/Python/dentobot_workflow/widget_application.py",
                     "Resources/Python/dentobot_workflow/widget_robot.py"):
            path = module / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# module\n")
        (self.workspace / "data").mkdir(parents=True)
        (self.workspace / "slicer-home").mkdir()
        backend = root / "env/bin/python"
        backend.parent.mkdir(parents=True)
        backend.write_text("fixture\n")
        backend.chmod(0o755)
        (self.workspace / ".dentobot.env").write_text(
            f"DENTOBOT_BACKEND_PYTHON={backend}\nAPI_TOKEN=must-not-be-recorded\n"
        )
        git(self.repo, "init", "--initial-branch=main")
        git(self.repo, "config", "user.name", "Smoke Test")
        git(self.repo, "config", "user.email", "smoke@example.invalid")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "fixture")
        self.sha = git(self.repo, "rev-parse", "HEAD")
        self.image_id = "sha256:" + "a" * 64

    def test_prepare_writes_fresh_dry_plan_without_docker_or_secrets(self):
        plan = smoke.prepare(self.repo, self.sha, self.image_id,
                             datetime(2026, 10, 7, 17, 0, tzinfo=timezone.utc))
        run_path = Path(plan["run_path"])
        self.assertTrue(run_path.is_dir())
        self.assertTrue((run_path / "bootstrap.py").is_file())
        command = json.loads((run_path / "runtime-command.json").read_text())
        self.assertIn("xvfb-run", command["argv"][-1])
        self.assertIn("record_slicer_screen.py", command["argv"][-1])
        self.assertIn("--fps 5", command["argv"][-1])
        artifacts = "".join(path.read_text(errors="ignore") for path in run_path.iterdir() if path.is_file())
        self.assertNotIn("must-not-be-recorded", artifacts)
        self.assertFalse(plan["runtime_verified"])

    def test_dirty_or_mismatched_checkout_fails_before_artifacts(self):
        with self.assertRaisesRegex(smoke.SmokeError, "does not match"):
            smoke.prepare(self.repo, "0" * 40, self.image_id)
        (self.repo / "uncommitted.txt").write_text("local edit\n")
        with self.assertRaisesRegex(smoke.SmokeError, "dirty"):
            smoke.prepare(self.repo, self.sha, self.image_id)
        self.assertFalse((self.workspace / "data/dentobot-runs").exists())

    def test_legacy_hidden_button_runner_is_blocked_with_checkpoint_instruction(self):
        runner = self.repo / "Testing/run_dentobot_slicer_reload_smoke.py"
        runner.write_text("reloadDENTOWorkflowButton.click()\n")
        git(self.repo, "add", str(runner))
        git(self.repo, "commit", "-m", "legacy runner fixture")
        self.sha = git(self.repo, "rev-parse", "HEAD")
        with self.assertRaisesRegex(smoke.SmokeError, "checkpoint the corrected production More"):
            smoke.prepare(self.repo, self.sha, self.image_id)

    def test_workspace_override_is_blocked_before_artifacts(self):
        (self.workspace / "compose.override.yaml").write_text("services: {}\n")
        with self.assertRaisesRegex(smoke.SmokeError, "compose.override"):
            smoke.prepare(self.repo, self.sha, self.image_id)
        self.assertFalse((self.workspace / "data/dentobot-runs").exists())

    def test_container_ownership_requires_stopped_exact_image_user_and_mounts(self):
        backend = self.workspace / "env"
        mounts = [
            {"Source": str(self.workspace / "ros2_ws"), "Destination": "/workspace/ros2_ws", "RW": True},
            {"Source": str(self.workspace / "data"), "Destination": "/workspace/data", "RW": True},
            {"Source": str(self.workspace / "slicer-home"), "Destination": "/home/dentobot", "RW": True},
            {"Source": str(backend), "Destination": str(backend), "RW": False},
            {"Source": "/tmp/.X11-unix", "Destination": "/tmp/.X11-unix", "RW": True},
        ]
        info = {"Id": "container-id", "Image": self.image_id, "Running": False, "Status": "exited",
                "ConfigImage": "dentobot/slicerros2:test", "ConfigCmd": ["sleep", "infinity"],
                "ConfigUser": f"{os.getuid()}:{os.getgid()}", "Mounts": mounts}
        self.assertEqual(smoke.validate_container(info, self.image_id, "dentobot/slicerros2:test",
                                                  self.workspace, backend, os.getuid(), os.getgid())["id"], "container-id")
        for change, message in (({"Running": True}, "running container"),
                                ({"Image": "sha256:" + "b" * 64}, "image or configured"),
                                ({"Mounts": mounts[:-1]}, "mount is missing")):
            with self.subTest(change=change), self.assertRaisesRegex(smoke.SmokeError, message):
                smoke.validate_container({**info, **change}, self.image_id, "dentobot/slicerros2:test",
                                         self.workspace, backend, os.getuid(), os.getgid())
        running = {**info, "Running": True, "Status": "running"}
        self.assertEqual(smoke.validate_container(
            running, self.image_id, "dentobot/slicerros2:test", self.workspace, backend,
            os.getuid(), os.getgid(), allow_idle_running=True)["id"], "container-id")
        with self.assertRaisesRegex(smoke.SmokeError, "sleep infinity"):
            smoke.validate_container({**running, "Status": "paused"}, self.image_id,
                                     "dentobot/slicerros2:test", self.workspace, backend,
                                     os.getuid(), os.getgid(), allow_idle_running=True)
        wrong_destination = [dict(mount, Destination="/home/slicer") if mount["Destination"] == "/home/dentobot" else mount
                             for mount in mounts]
        with self.assertRaisesRegex(smoke.SmokeError, "mount is missing"):
            smoke.validate_container({**info, "Mounts": wrong_destination}, self.image_id,
                                     "dentobot/slicerros2:test", self.workspace, backend,
                                     os.getuid(), os.getgid())

    def test_configured_workspace_or_host_identity_mismatch_is_rejected(self):
        config = self.workspace / ".dentobot.env"
        with patch.dict(os.environ, {"DENTOBOT_WORKSPACE_ROOT": "", "DENTOBOT_HOST_UID": "", "DENTOBOT_HOST_GID": ""}):
            config.write_text(config.read_text() + "DENTOBOT_WORKSPACE_ROOT=/wrong/workspace\n")
            with self.assertRaisesRegex(smoke.SmokeError, "WORKSPACE_ROOT"):
                smoke.prepare(self.repo, self.sha, self.image_id)
            config.write_text(
                f"DENTOBOT_BACKEND_PYTHON={self.temp.name}/env/bin/python\n"
                f"DENTOBOT_HOST_UID={os.getuid() + 1}\n"
            )
            with self.assertRaisesRegex(smoke.SmokeError, "UID/GID"):
                smoke.prepare(self.repo, self.sha, self.image_id)

    def test_runtime_evidence_fails_closed_on_launcher_exit_and_tokenless_rows(self):
        plan = smoke.prepare(self.repo, self.sha, self.image_id)
        run_path = Path(plan["run_path"])
        loaded_files = {path: {"matched": True} for path in {"DENTOWorkflow/DENTOWorkflow.py", *smoke.MODULES.values()}}
        (run_path / "loaded-code.json").write_text(json.dumps({"matched": True, "files": loaded_files}))
        reports = [{"cycle": cycle, **{field: True for field in (
            "reload_action_available", "helper_module_reloaded", "internal_module_reloaded",
            "module_reload_success", "scene_preserved", "workspace_explorer_visible")}}
            for cycle in range(1, 6)]
        (run_path / "reload-result.json").write_text(json.dumps({"requested_exit_code": 0, "reports": reports}))
        (run_path / "startup.png").write_bytes(b"png")
        (run_path / "final.png").write_bytes(b"png")
        video = run_path / "video/smoke.mkv"
        video.write_bytes(b"fixture video")
        (run_path / "video/smoke.manifest.json").write_text(json.dumps({
            "schema": "dentobot.screen-recording.v1", "status": "complete", "exit_status": 0,
            "command_exit_status": 0, "ffmpeg_exit_status": 0,
            "output_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
        }))
        clean_log = ("DENTOBOT_B_LOADED_CODE_PASS\nDENTOBOT_FIVE_RELOAD_CYCLES_PASS\n"
                     "[INFO] [Slicer-1]: process has finished cleanly [pid 64]\n")
        valid = smoke.evidence_checks(plan, 0, clean_log, True, {}, {}, 0, video)
        self.assertTrue(valid["runtime_verified"])
        invalid_exit = smoke.evidence_checks(plan, 2, clean_log, True, {}, {}, 0, video)
        self.assertFalse(invalid_exit["runtime_verified"])
        self.assertFalse(invalid_exit["checks"]["ros_launcher_exit_code"])
        slicer_failed = clean_log.replace(
            "[INFO] [Slicer-1]: process has finished cleanly [pid 64]",
            "[INFO] [Slicer-1]: process has died [pid 64, exit code -11]")
        invalid_slicer = smoke.evidence_checks(plan, 0, slicer_failed, True, {}, {}, 0, video)
        self.assertFalse(invalid_slicer["runtime_verified"])
        self.assertEqual(invalid_slicer["slicer_process_exit_code"], -11)
        manifest = json.loads((run_path / "video/smoke.manifest.json").read_text())
        manifest["output_sha256"] = "0" * 64
        (run_path / "video/smoke.manifest.json").write_text(json.dumps(manifest))
        invalid_video = smoke.evidence_checks(plan, 0, clean_log, True, {}, {}, 0, video)
        self.assertFalse(invalid_video["checks"]["video_manifest_checksum_and_decode"])

    def test_execute_uses_an_injected_evidence_function_when_given(self):
        run_path = Path(self.temp.name) / "run"
        run_path.mkdir()
        image = self.image_id
        info = {"Id": "cid", "Image": image, "Running": False, "Status": "exited",
                "ConfigImage": "dentobot/slicerros2:test", "ConfigCmd": ["sleep", "infinity"]}
        running = {**info, "Running": True, "Status": "running"}
        inspections = [info, running, running, info, info]
        proc = MagicMock()
        proc.wait.return_value = 0
        proc.poll.return_value = 0
        plan = {"check": "test", "repo": str(self.repo), "workspace": str(self.workspace), "expected_sha": self.sha,
                "image_id": image, "image_name": "dentobot/slicerros2:test", "backend_env_dir": str(self.workspace),
                "run_path": str(run_path), "timeout_sec": 30, "argv": ["true"]}
        injected = MagicMock(return_value={"checks": {"fake": True}, "runtime_verified": True})
        with patch.object(smoke.shutil, "which", return_value="/usr/bin/tool"), \
             patch.object(smoke, "acquire_locks", return_value=[]), patch.object(smoke, "release_locks"), \
             patch.object(smoke, "assert_no_owners", return_value={}), \
             patch.object(smoke, "await_owned_exit", return_value={}), \
             patch.object(smoke, "inspect_container", side_effect=inspections), \
             patch.object(smoke, "validate_container", return_value={}), \
             patch.object(smoke, "command", return_value=(0, image + "\n", "")), \
             patch.object(smoke, "source_is_clean", return_value=True), \
             patch.object(smoke.subprocess, "Popen", return_value=proc), \
             patch.object(smoke, "evidence_checks") as default_evidence:
            result = smoke.execute(plan, evidence_fn=injected)
        injected.assert_called_once()
        self.assertEqual(injected.call_args.args[1], 0)
        default_evidence.assert_not_called()
        self.assertEqual(result["checks"], {"fake": True})


if __name__ == "__main__":
    unittest.main()


def test_owned_exit_waits_for_reaping_but_retains_a_leak_error():
    from unittest.mock import patch
    import pytest
    import smoke_runtime as smoke
    clean = {name: 0 for name in smoke.PROCESS_NAMES}
    with patch.object(smoke, "assert_no_owners", side_effect=[smoke.SmokeError("Xvfb alive"), clean]), \
         patch.object(smoke.time, "sleep"):
        assert smoke.await_owned_exit() == clean
    with patch.object(smoke, "assert_no_owners", side_effect=smoke.SmokeError("leaked Xvfb")), \
         patch.object(smoke.time, "monotonic", side_effect=[0, 4]), \
         patch.object(smoke.time, "sleep"):
        with pytest.raises(smoke.SmokeError, match="leaked Xvfb"):
            smoke.await_owned_exit()
