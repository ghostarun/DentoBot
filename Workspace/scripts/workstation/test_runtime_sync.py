from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import runtime_sync


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_fixture(root: Path) -> dict:
    workspace = root / "workspace"
    repo = workspace / "ros2_ws" / "src" / "DentoBot"
    native = workspace / "ros2_ws" / "src" / "slicer_ros2_module"
    (repo / "Workspace").mkdir(parents=True)
    native.mkdir(parents=True)

    git(native, "init", "--initial-branch=main")
    git(native, "config", "user.name", "Runtime Sync Test")
    git(native, "config", "user.email", "runtime-sync@example.invalid")
    (native / "source.txt").write_text("native source\n")
    git(native, "add", ".")
    git(native, "commit", "-m", "fixture")
    native_sha = git(native, "rev-parse", "HEAD")

    install = workspace / "ros2_ws" / "install" / "slicer_ros2_module"
    ros_install = workspace / "ros2_ws" / "install"
    files = {
        "lib/Slicer-5.10/qt-loadable-modules/libqSlicerROS2Module.so": b"native library bytes",
        "lib/Slicer-5.10/qt-scripted-modules/ROS2MotionControl.py": b"wrapper bytes",
    }
    native_entries = []
    for name, data in files.items():
        path = install / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        native_entries.append({"path": name, "sha256": sha(data)})

    data_root = workspace / "data"
    data_path = data_root / "fixtures" / "sample.dentocase"
    data_path.parent.mkdir(parents=True)
    data_bytes = b"approved local case fixture"
    data_path.write_bytes(data_bytes)
    ros_path = ros_install / "dentobot_description" / "share" / "dentobot_description" / "urdf" / "robot.urdf"
    ros_path.parent.mkdir(parents=True)
    ros_bytes = b"approved installed robot description"
    ros_path.write_bytes(ros_bytes)
    image_id = "sha256:" + "a" * 64
    lock = {
        "image_id": image_id,
        "image_name": "dentobot/slicerros2:test",
        "native_sha": native_sha,
        "native_files": native_entries,
        "data_files": [{"path": "fixtures/sample.dentocase", "sha256": sha(data_bytes)}],
        "ros_files": [{"path": "dentobot_description/share/dentobot_description/urdf/robot.urdf",
                       "sha256": sha(ros_bytes)}],
    }
    lock_path = repo / "Workspace" / "runtime-lock.json"
    lock_path.write_text(json.dumps(lock))
    return {
        "workspace": workspace, "repo": repo, "native": native, "install": install,
        "data": data_root, "data_path": data_path, "ros_path": ros_path,
        "lock_path": lock_path,
        "lock": lock, "image_id": image_id,
    }


class RuntimeSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = make_fixture(Path(self.temp.name))
        self.real_run = subprocess.run
        self.calls = []

    def mocked_run(self, argv, **kwargs):
        argv = [str(value) for value in argv]
        self.calls.append(argv)
        if argv[0] == "git":
            return self.real_run(argv, **kwargs)
        if argv[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=self.fixture["image_id"] + "\n", stderr="")
        if argv[:3] == ["docker", "container", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=self.fixture["image_id"] + "\n", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="unexpected command")

    def run_parity(self):
        with mock.patch.object(runtime_sync.subprocess, "run", side_effect=self.mocked_run):
            return runtime_sync.parity(self.fixture["repo"])

    def write_lock(self):
        self.fixture["lock_path"].write_text(json.dumps(self.fixture["lock"]))

    def test_clean_matching_runtime_passes_and_cli_emits_json(self):
        output = io.StringIO()
        with mock.patch.object(runtime_sync.subprocess, "run", side_effect=self.mocked_run), \
             contextlib.redirect_stdout(output):
            code = runtime_sync.main(["--repo", str(self.fixture["repo"])])
        report = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(report["passed"], report["checks"])
        self.assertTrue(all(check["passed"] for check in report["checks"].values()))
        self.assertIn("ros_files", report["checks"])
        self.assertEqual(sum(call[:3] == ["docker", "image", "inspect"] for call in self.calls), 1)
        self.assertTrue(all(call[3] == "--format" for call in self.calls if call[0] == "docker"))

    def test_file_hash_mismatch_reports_hashes_without_file_contents(self):
        (self.fixture["install"] / self.fixture["lock"]["native_files"][0]["path"]).write_bytes(
            b"PRIVATE_NATIVE_CONTENT"
        )
        self.fixture["data_path"].write_bytes(b"PRIVATE_CASE_CONTENT")
        report = self.run_parity()
        rendered = json.dumps(report)
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["native_files"]["passed"])
        self.assertFalse(report["checks"]["data_files"]["passed"])
        self.fixture["ros_path"].write_bytes(b"PRIVATE_URDF_CONTENT")
        self.write_lock()
        report = self.run_parity()
        self.assertFalse(report["checks"]["ros_files"]["passed"])
        self.assertNotIn("PRIVATE_NATIVE_CONTENT", rendered)
        self.assertNotIn("PRIVATE_CASE_CONTENT", rendered)
        self.assertNotIn("PRIVATE_URDF_CONTENT", json.dumps(report))
        self.assertIn("actual_sha256", rendered)

    def test_older_manifest_without_ros_files_remains_supported(self):
        self.fixture["lock"].pop("ros_files")
        self.write_lock()
        report = self.run_parity()
        self.assertTrue(report["passed"], report["checks"])
        self.assertNotIn("ros_files", report["checks"])

    def test_wrong_image_native_head_and_dirty_checkout_fail(self):
        self.fixture["lock"]["image_id"] = "sha256:" + "b" * 64
        self.fixture["lock"]["native_sha"] = "f" * 40
        self.write_lock()
        report = self.run_parity()
        self.assertFalse(report["checks"]["image_tag"]["passed"])
        self.assertFalse(report["checks"]["container_image"]["passed"])
        self.assertFalse(report["checks"]["native_git"]["passed"])

        self.fixture["lock"]["native_sha"] = git(self.fixture["native"], "rev-parse", "HEAD")
        (self.fixture["native"] / "untracked.txt").write_text("dirty\n")
        self.write_lock()
        dirty = self.run_parity()
        self.assertFalse(dirty["checks"]["native_git"]["passed"])
        self.assertFalse(dirty["checks"]["native_git"]["clean"])

    def test_missing_empty_duplicate_and_traversal_manifests_fail(self):
        self.fixture["lock_path"].unlink()
        missing = self.run_parity()
        self.assertFalse(missing["checks"]["manifest"]["passed"])
        self.assertEqual(self.calls, [])

        original = copy.deepcopy(self.fixture["lock"])
        cases = []
        empty = copy.deepcopy(original)
        empty["native_files"] = []
        cases.append((empty, "non-empty list"))
        duplicate = copy.deepcopy(original)
        duplicate["data_files"] *= 2
        cases.append((duplicate, "duplicate path"))
        traversal = copy.deepcopy(original)
        traversal["native_files"][0] = {"path": "../outside", "sha256": "0" * 64}
        cases.append((traversal, "stay relative"))
        for lock, detail in cases:
            self.fixture["lock"] = lock
            self.write_lock()
            report = self.run_parity()
            self.assertFalse(report["checks"]["manifest"]["passed"])
            self.assertIn(detail, report["checks"]["manifest"]["details"])

    def test_symlink_escape_is_rejected(self):
        outside = Path(self.temp.name) / "outside.dentocase"
        outside.write_bytes(b"outside fixture")
        link = self.fixture["data"] / "fixtures" / "escape.dentocase"
        link.symlink_to(outside)
        self.fixture["lock"]["data_files"] = [{"path": "fixtures/escape.dentocase", "sha256": sha(outside.read_bytes())}]
        self.write_lock()
        report = self.run_parity()
        self.assertFalse(report["checks"]["data_files"]["passed"])
        self.assertEqual(report["checks"]["data_files"]["files"][0]["details"], "path escapes manifest root")

    def test_missing_command_and_timeout_are_failed_checks(self):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired(["docker"], 20), PermissionError()):
            with self.subTest(error=type(error).__name__), \
                 mock.patch.object(runtime_sync.subprocess, "run", side_effect=error):
                report = runtime_sync.parity(self.fixture["repo"])
                self.assertFalse(report["passed"])
                self.assertFalse(report["checks"]["native_git"]["passed"])
                self.assertFalse(report["checks"]["image_tag"]["passed"])


if __name__ == "__main__":
    unittest.main()


class SourceParityTests(unittest.TestCase):
    setUp = RuntimeSyncTests.setUp
    mocked_run = RuntimeSyncTests.mocked_run

    def test_changed_robot_source_is_rejected_even_when_installed_files_match(self):
        f = self.fixture
        source = f['repo'] / 'dentobot_description' / 'robot.urdf'
        source.parent.mkdir()
        source.write_bytes(b'locked robot source')
        f['lock']['ros_source_files'] = [{'path': 'dentobot_description/robot.urdf',
                                         'sha256': sha(source.read_bytes())}]
        f['lock_path'].write_text(json.dumps(f['lock']))
        with mock.patch.object(runtime_sync.subprocess, 'run', side_effect=self.mocked_run):
            self.assertTrue(runtime_sync.parity(f['repo'])['passed'])
            source.write_bytes(b'changed robot source')
            result = runtime_sync.parity(f['repo'])
        self.assertFalse(result['passed'])
        self.assertFalse(result['checks']['ros_source_files']['passed'])
        self.assertTrue(result['checks']['ros_files']['passed'])
