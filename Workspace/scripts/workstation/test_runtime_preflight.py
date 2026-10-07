from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import runtime_preflight as preflight


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def make_fixture(root: Path):
    workspace = root / "workspace"
    repo = workspace / "ros2_ws" / "src" / "DentoBot"
    launcher = repo / "Workspace" / "scripts" / "launch-dentoworkflow.bash"
    compose = repo / "Workspace" / "compose.yaml"
    module = repo / "DENTOWorkflow"
    launcher.parent.mkdir(parents=True)
    module.mkdir(parents=True)
    launcher.write_text(
        """backend_dependency_probe=""
if [ "$DENTOBOT_BACKEND_DEVICE" = cpu ]; then
backend_dependency_probe='
expected = {"torch": "2.6.0+cpu", "numpy": "1.26.4"}
assert sys.version_info[:2] == (3, 12)
raise RuntimeError("probe code must not execute")
'
else
backend_dependency_probe='
expected = {"torch": "2.6.0+cu121", "numpy": "1.26.4"}
assert sys.version_info[:2] == (3, 12)
'
fi
"""
    )
    compose.write_text("services:\n  slicer:\n    image: dentobot/slicerros2:test\n")
    data = workspace / "data"
    (data / "SlicerEndoPlanner-main" / "PulpChamberOpenPlanning").mkdir(parents=True)
    slicer_home = workspace / "slicer-home"
    slicer_home.mkdir()
    fake_bin = root / "fake bin"
    fake_bin.mkdir()
    backend_python = fake_bin / "backend python"
    backend_python.write_text("this executable is intercepted by the test\n")
    backend_python.chmod(0o755)
    render_device = root / "render device"
    render_device.write_text("")
    render_device.chmod(0o666)
    (workspace / ".dentobot.env").write_text(
        f"DENTOBOT_BACKEND_PYTHON='{backend_python}'\n"
        "DENTOBOT_BACKEND_DEVICE=cpu\n"
        "DENTOBOT_BACKEND_EXECUTION_MODE=local\n"
        f"DENTOBOT_RENDER_DEVICE='{render_device}'\n"
        "DENTOBOT_RUN_ARTIFACT_ROOT=/workspace/data/dentobot-runs\n"
        "DENTOBOT_TOTALSEG_HOME_DIR=/workspace/data/totalseg\n"
        f"DENTOBOT_WORKSPACE_ROOT={workspace}\n"
    )
    git(repo, "init", "--initial-branch=main")
    git(repo, "config", "user.name", "Preflight Test")
    git(repo, "config", "user.email", "preflight-test@example.invalid")
    (repo / "source.txt").write_text("committed snapshot\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixture")
    sha = git(repo, "rev-parse", "HEAD")
    args = SimpleNamespace(
        repo=str(repo), expected_sha=sha, image_id="sha256:expected", display=None,
        xauthority=None, data_manifest=None,
    )
    return {
        "workspace": workspace, "repo": repo, "launcher": launcher, "compose": compose,
        "data": data, "slicer_home": slicer_home, "backend_python": backend_python,
        "expected_sha": sha, "args": args,
    }


def mocked_host_probes(fixture, packages=None, wrong_home_destination=False):
    original = preflight.run_command
    packages = packages or {"torch": "2.6.0+cpu", "numpy": "1.26.4"}
    calls = []

    def run(argv, timeout=30, env=None):
        argv = [str(value) for value in argv]
        calls.append(argv)
        if argv[0] == "git":
            return original(argv, timeout=timeout, env=env)
        if argv[0] == str(fixture["backend_python"]):
            script = argv[3]
            if "importlib.metadata" not in script or "import torch" in script:
                return False, "", "", "unexpected backend probe"
            return True, json.dumps({"python": [3, 12, 13], "packages": packages}), "", ""
        if argv[:3] == ["docker", "image", "inspect"]:
            return True, json.dumps({
                "Id": "sha256:expected", "RepoDigests": ["dentobot/slicerros2@sha256:repo"],
                "Created": "2026-01-01T00:00:00Z",
            }), "", ""
        if argv[:3] == ["docker", "container", "inspect"]:
            workspace = fixture["workspace"]
            return True, json.dumps({"Running": True, "Mounts": [
                {"Source": str(workspace / "ros2_ws"), "Destination": "/workspace/ros2_ws"},
                {"Source": str(fixture["data"]), "Destination": "/workspace/data"},
                {"Source": str(fixture["slicer_home"]),
                 "Destination": "/home/wrong" if wrong_home_destination else "/home/dentobot"},
            ]}), "", ""
        if argv == ["glxinfo", "-B"]:
            return True, (
                "OpenGL renderer string: Mesa Intel(R) Graphics\n"
                "OpenGL core profile version string: 4.6 (Core Profile) Mesa\n"
            ), "", ""
        return False, "", "", "not available in test"

    return original, run, calls


class RuntimePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = make_fixture(Path(self.temp.name))

    def run_mocked(self, packages=None, repo=None, expected_sha=None, wrong_home_destination=False):
        fixture = self.fixture
        original, runner, calls = mocked_host_probes(fixture, packages, wrong_home_destination)
        args = SimpleNamespace(**vars(fixture["args"]))
        if repo:
            args.repo = str(repo)
        if expected_sha:
            args.expected_sha = expected_sha
        disk = SimpleNamespace(total=8 * 1024**3, used=1, free=8 * 1024**3)
        with mock.patch.object(preflight, "run_command", side_effect=runner), \
             mock.patch.object(preflight, "_memory_available", return_value=8 * 1024**3), \
             mock.patch.object(preflight.shutil, "disk_usage", return_value=disk):
            result = preflight.run_preflight(args, {"DISPLAY": ":99", "XAUTHORITY": "/auth/cookie"})
        return result, calls

    def test_layout_and_exact_clean_git_snapshot_are_required(self):
        result, _ = self.run_mocked()
        checks = {item["name"]: item for item in result["checks"]}
        self.assertEqual(checks["repo_layout"]["status"], "passed")
        self.assertEqual(checks["git_snapshot"]["status"], "passed")
        self.assertEqual(result["intended_container_repo"], "/workspace/ros2_ws/src/DentoBot")

        mismatch, _ = self.run_mocked(expected_sha="0" * 40)
        self.assertEqual({c["name"]: c["status"] for c in mismatch["checks"]}["git_snapshot"], "blocked")

        dirty_file = self.fixture["repo"] / "uncommitted.txt"
        dirty_file.write_text("local change\n")
        dirty, _ = self.run_mocked()
        self.assertEqual({c["name"]: c["status"] for c in dirty["checks"]}["git_snapshot"], "blocked")
        dirty_file.unlink()

        wrong_repo = Path(self.temp.name) / "other" / "src" / "checkout"
        wrong_repo.mkdir(parents=True)
        git(wrong_repo, "init", "--initial-branch=main")
        git(wrong_repo, "config", "user.name", "Preflight Test")
        git(wrong_repo, "config", "user.email", "preflight-test@example.invalid")
        (wrong_repo / "file").write_text("x")
        git(wrong_repo, "add", "file")
        git(wrong_repo, "commit", "-m", "wrong layout")
        rejected, _ = self.run_mocked(repo=wrong_repo, expected_sha=git(wrong_repo, "rev-parse", "HEAD"))
        self.assertEqual({c["name"]: c["status"] for c in rejected["checks"]}["repo_layout"], "blocked")

    def test_env_parser_rejects_shell_expansion_and_discards_unknown_values(self):
        env_file = Path(self.temp.name) / "unsafe.env"
        env_file.write_text(
            "DENTOBOT_BACKEND_PYTHON='/safe path/python' # comment\n"
            "UNKNOWN_SECRET='TOPSECRET'\n"
            "DENTOBOT_WORKSPACE_ROOT=$(touch /tmp/preflight-should-not-run)\n"
        )
        values, errors = preflight.parse_env_file(env_file)
        self.assertEqual(values["DENTOBOT_BACKEND_PYTHON"], "/safe path/python")
        self.assertNotIn("UNKNOWN_SECRET", values)
        self.assertTrue(any("DENTOBOT_WORKSPACE_ROOT" in error for error in errors))
        self.assertNotIn("TOPSECRET", json.dumps({"values": values, "errors": errors}))

    def test_probe_ast_selects_cpu_or_cuda_without_running_probe_code(self):
        text = self.fixture["launcher"].read_text()
        cpu, py_cpu, device_cpu = preflight.extract_backend_probe(text, "cpu")
        cuda, py_cuda, device_cuda = preflight.extract_backend_probe(text, "cuda:0")
        self.assertEqual(cpu["torch"], "2.6.0+cpu")
        self.assertEqual(cuda["torch"], "2.6.0+cu121")
        self.assertEqual((py_cpu, device_cpu), ((3, 12), "cpu"))
        self.assertEqual((py_cuda, device_cuda), ((3, 12), "cuda:0"))

    def test_missing_backend_metadata_blocks_preflight(self):
        result, _ = self.run_mocked(packages={"torch": None, "numpy": "1.26.4"})
        checks = {item["name"]: item for item in result["checks"]}
        self.assertEqual(checks["backend_metadata"]["status"], "blocked")
        self.assertFalse(result["preflight_passed"])
        self.assertFalse(result["runtime_verified"])

    def test_manifest_checks_only_contained_files_and_exact_checksums(self):
        data = self.fixture["data"]
        listed = data / "input.nrrd"
        listed.write_bytes(b"local fixture data")
        outside = Path(self.temp.name) / "outside.nrrd"
        outside.write_bytes(b"outside")
        manifest = Path(self.temp.name) / "data.json"
        good = {"path": "input.nrrd", "sha256": hashlib.sha256(listed.read_bytes()).hexdigest()}
        manifest.write_text(json.dumps([good]))
        self.assertEqual(preflight.verify_data_manifest(manifest, data), (True, [], 1))

        bad = [good, {"path": "../outside.nrrd", "sha256": hashlib.sha256(b"outside").hexdigest()},
               {"path": str(listed), "sha256": "0" * 64}]
        manifest.write_text(json.dumps(bad))
        ok, errors, count = preflight.verify_data_manifest(manifest, data)
        self.assertFalse(ok)
        self.assertEqual(count, 3)
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("escapes" in error for error in errors))
        self.assertTrue(any("checksum" in error for error in errors))

    def test_successful_static_preflight_never_claims_runtime_or_shutdown_safety(self):
        result, calls = self.run_mocked()
        self.assertTrue(result["preflight_passed"], result["checks"])
        self.assertFalse(result["runtime_verified"])
        self.assertFalse(result["loaded_code_verified"])
        self.assertFalse(result["safe_to_shutdown"])
        self.assertFalse(result["datasets_verified"])
        self.assertEqual(sum(call == ["glxinfo", "-B"] for call in calls), 1)
        self.assertFalse(any(call[:2] == ["docker", "exec"] for call in calls))
        self.assertFalse(any(str(self.fixture["launcher"]) in call for call in calls))
        script_call = next(call for call in calls if call[0] == str(self.fixture["backend_python"]))
        self.assertIn("importlib.metadata", script_call[3])
        self.assertNotIn("import torch", script_call[3])

    def test_running_container_with_wrong_mount_destination_is_blocked(self):
        result, _ = self.run_mocked(wrong_home_destination=True)
        checks = {item["name"]: item for item in result["checks"]}
        self.assertEqual(checks["container_mounts"]["status"], "blocked")
        self.assertFalse(result["preflight_passed"])

    def test_versioned_cuda_override_symlink_is_supported(self):
        cuda = self.fixture["repo"] / "Workspace/compose.cuda.yaml"
        cuda.write_text("services: {}\n")
        git(self.fixture["repo"], "add", str(cuda))
        git(self.fixture["repo"], "commit", "-m", "CUDA fixture")
        self.fixture["args"].expected_sha = git(self.fixture["repo"], "rev-parse", "HEAD")
        (self.fixture["workspace"] / "compose.override.yaml").symlink_to(cuda)
        result, _ = self.run_mocked()
        self.assertTrue(result["preflight_passed"], result["checks"])

    def test_workspace_compose_override_is_blocked(self):
        (self.fixture["workspace"] / "compose.override.yaml").write_text("services: {}\n")
        result, _ = self.run_mocked()
        self.assertEqual({c["name"]: c["status"] for c in result["checks"]}["compose_override"], "blocked")
        self.assertFalse(result["preflight_passed"])


if __name__ == "__main__":
    unittest.main()
