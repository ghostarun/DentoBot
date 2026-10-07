"""Local-Git safety tests for the handoff workflow."""

from __future__ import annotations

import subprocess
import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
from pathlib import Path

from handoff import Machine, main, prepare


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class HandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.origin = self.root / "origin.git"
        self._make_origin(self.origin, "initial content\n")
        self.source = self._clone(self.origin, self.root / "source")
        self.destination = self._clone(self.origin, self.root / "destination")
        self.output = self.root / "destination-output"
        self.output.mkdir()

    def _make_origin(self, origin: Path, content: str) -> str:
        seed = origin.with_name(origin.name + "-seed")
        seed.mkdir()
        subprocess.run(
            ["git", "init", "--bare", "--initial-branch=main", str(origin)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "init", "--initial-branch=main", str(seed)],
            check=True,
            capture_output=True,
            text=True,
        )
        git(seed, "config", "user.name", "Handoff Test")
        git(seed, "config", "user.email", "handoff-test@example.invalid")
        (seed / "tracked.txt").write_text(content)
        git(seed, "add", "tracked.txt")
        git(seed, "commit", "-m", "initial commit")
        git(seed, "remote", "add", "origin", str(origin))
        git(seed, "push", "-u", "origin", "main")
        return git(seed, "rev-parse", "HEAD")

    def _clone(self, origin: Path, destination: Path) -> Path:
        subprocess.run(
            ["git", "clone", str(origin), str(destination)],
            check=True,
            capture_output=True,
            text=True,
        )
        git(destination, "config", "user.name", "Handoff Test")
        git(destination, "config", "user.email", "handoff-test@example.invalid")
        return destination

    def _machine(
        self, name: str, repo: Path, output: Path, worktree_root: Path | None = None
    ) -> Machine:
        settings = {"host": None, "repo": str(repo), "output": str(output)}
        if worktree_root is not None:
            settings["worktree_root"] = str(worktree_root)
        return Machine(
            name,
            settings,
        )

    def _remote_handoff_refs(self, origin: Path) -> dict[str, str]:
        lines = git(
            origin,
            "for-each-ref",
            "--format=%(refname) %(objectname)",
            "refs/heads/handoff",
        ).splitlines()
        return dict(line.split() for line in lines)

    def _assert_result_shape(self, result: dict) -> Path:
        self.assertIn("worktree", result)
        self.assertIn("manifest", result)
        self.assertIn("prompt", result)
        self.assertIsInstance(result["prompt"], str)
        self.assertTrue(result["prompt"].strip())
        self.assertTrue(result["manifest"])
        manifest = json.loads(Path(result["manifest"]).read_text())
        self.assertEqual(manifest["git_ready"], result["git_ready"])
        self.assertFalse(manifest["runtime_verified"])
        self.assertFalse(manifest["safe_to_shutdown"])
        self.assertTrue(Path(result["prompt"]).is_file())
        worktree = Path(result["worktree"])
        self.assertTrue(worktree.is_dir(), worktree)
        return worktree

    def test_clean_transfer_mirrors_sha_and_preserves_checkouts(self) -> None:
        quoted_source = self.root / "source 'quoted' \"with spaces\""
        # Put the source clone at a path that exercises local command quoting.
        self.source.rename(quoted_source)
        source = self._machine("source", quoted_source, self.root / "unused-source-output")
        destination = self._machine("destination", self.destination, self.output)

        (self.destination / "tracked.txt").write_text("local destination edit\n")
        (self.destination / "untracked.txt").write_text("keep me\n")
        destination_head = git(self.destination, "rev-parse", "HEAD")
        destination_status = git(self.destination, "status", "--porcelain")
        source_head = git(quoted_source, "rev-parse", "HEAD")
        source_status = git(quoted_source, "status", "--porcelain")

        result = prepare(source, destination, "Continue the repair")

        worktree = self._assert_result_shape(result)
        self.assertEqual(worktree.parent.parent, self.output)
        transfer_id = worktree.parent.name
        self.assertEqual(worktree.name, "repo")
        self.assertEqual(git(worktree, "branch", "--show-current"), f"handoff/{transfer_id}")
        self.assertEqual(git(worktree, "rev-parse", "@{upstream}"), source_head)
        self.assertEqual(git(worktree, "rev-parse", "HEAD"), source_head)
        self.assertEqual(self._remote_handoff_refs(self.origin), {
            f"refs/heads/handoff/{transfer_id}": source_head,
        })
        self.assertTrue(result["git_ready"])
        self.assertFalse(result["safe_to_shutdown"])
        self.assertEqual(git(quoted_source, "rev-parse", "HEAD"), source_head)
        self.assertEqual(git(quoted_source, "status", "--porcelain"), source_status)
        self.assertEqual(git(self.destination, "rev-parse", "HEAD"), destination_head)
        self.assertEqual(git(self.destination, "status", "--porcelain"), destination_status)
        self.assertEqual((self.destination / "tracked.txt").read_text(), "local destination edit\n")
        self.assertEqual((self.destination / "untracked.txt").read_text(), "keep me\n")
        self.assertEqual(git(worktree, "status", "--porcelain"), "")

    def test_configured_workspace_keeps_manifest_separate_from_worktree(self) -> None:
        source = self._machine("source", self.source, self.root / "unused-source-output")
        workspace_root = self.root / "mock-workspace"
        worktree_root = workspace_root / "ros2_ws" / "src"
        worktree_root.mkdir(parents=True)
        destination = self._machine(
            "destination", self.destination, self.output, worktree_root=worktree_root
        )

        result = prepare(source, destination, "Use the configured workspace")
        worktree = self._assert_result_shape(result)
        manifest_path = Path(result["manifest"])
        manifest = json.loads(manifest_path.read_text())
        handoff_id = result["id"]

        self.assertEqual(worktree, worktree_root / f"DentoBot-handoff-{handoff_id}")
        self.assertEqual(manifest_path, self.output / handoff_id / "manifest.json")
        self.assertNotEqual(manifest_path.parent, worktree)
        self.assertEqual(manifest["destination"]["worktree"], str(worktree))
        self.assertEqual(manifest["destination"]["workspace_root"], str(workspace_root))
        self.assertEqual(
            manifest["destination"]["container_repo"],
            f"/workspace/ros2_ws/src/DentoBot-handoff-{handoff_id}",
        )
        self.assertTrue(result["git_ready"])

    def test_doctor_propagates_failed_checker_json_and_exit_status(self) -> None:
        config = self.root / "machines.json"
        config.write_text(json.dumps({"machines": {
            "A": {
                "host": None,
                "repo": str(self.source),
                "output": str(self.output),
            },
        }}))
        expected = {
            "preflight_passed": False,
            "runtime_verified": False,
            "loaded_code_verified": False,
            "safe_to_shutdown": False,
            "checks": [{"name": "fixture", "passed": False}],
        }
        captured = {}

        def fake_run(machine, argv, input=None, timeout=30, allowed_returncodes=(0,)):
            captured["argv"] = argv
            captured["input"] = input
            captured["timeout"] = timeout
            captured["allowed_returncodes"] = allowed_returncodes
            return json.dumps(expected)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.object(Machine, "run", fake_run), patch.object(
            Path, "read_text", return_value="print('fixture helper')\n"
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main([
                "--config", str(config), "doctor", "--machine", "A",
                "--repo", str(self.source), "--expected-sha", "abc123",
                "--image-id", "sha256:fixture", "--display", ":99",
                "--data-manifest", str(self.root / "data.json"),
                "--xauthority", str(self.root / "Xauthority"),
            ])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(json.loads(stdout.getvalue()), expected)
        self.assertEqual(captured["argv"][:6], [
            "python3", "-", "--repo", str(self.source), "--expected-sha", "abc123"
        ])
        self.assertEqual(captured["argv"][6:], [
            "--image-id", "sha256:fixture", "--display", ":99",
            "--data-manifest", str(self.root / "data.json"),
            "--xauthority", str(self.root / "Xauthority"),
        ])
        self.assertEqual(captured["timeout"], 120)
        self.assertEqual(captured["allowed_returncodes"], (0, 2))
        self.assertEqual(captured["input"], "print('fixture helper')\n")

    def test_dirty_source_is_refused_without_mutation_or_can_send_committed_head(self) -> None:
        source = self._machine("source", self.source, self.root / "unused-source-output")
        destination = self._machine("destination", self.destination, self.output)
        (self.source / "tracked.txt").write_text("uncommitted edit\n")
        (self.source / "untracked.txt").write_text("uncommitted file\n")
        dirty_status = git(self.source, "status", "--porcelain")
        source_head = git(self.source, "rev-parse", "HEAD")
        refs_before = self._remote_handoff_refs(self.origin)

        with self.assertRaises(RuntimeError):
            prepare(source, destination, "Do not lose local edits")

        self.assertEqual(self._remote_handoff_refs(self.origin), refs_before)
        self.assertEqual(git(self.source, "status", "--porcelain"), dirty_status)
        self.assertEqual(list(self.output.iterdir()), [])

        result = prepare(source, destination, "Use the committed snapshot", committed_only=True)

        worktree = self._assert_result_shape(result)
        transfer_id = worktree.parent.name
        self.assertEqual(git(worktree, "rev-parse", "HEAD"), source_head)
        self.assertEqual((worktree / "tracked.txt").read_text(), "initial content\n")
        self.assertFalse((worktree / "untracked.txt").exists())
        self.assertEqual(
            self._remote_handoff_refs(self.origin)[f"refs/heads/handoff/{transfer_id}"],
            source_head,
        )
        self.assertFalse(result["git_ready"])
        self.assertFalse(result["safe_to_shutdown"])
        self.assertEqual(git(self.source, "status", "--porcelain"), dirty_status)

    def test_different_origin_and_same_machine_are_rejected(self) -> None:
        source = self._machine("source", self.source, self.root / "unused-source-output")
        source_head = git(self.source, "rev-parse", "HEAD")
        source_refs_before = self._remote_handoff_refs(self.origin)

        other_origin = self.root / "other-origin.git"
        self._make_origin(other_origin, "different project\n")
        other_destination_repo = self._clone(other_origin, self.root / "other-destination")
        other_destination = self._machine(
            "other-destination", other_destination_repo, self.root / "other-output"
        )
        self.assertNotEqual(git(other_destination_repo, "rev-parse", "HEAD"), source_head)
        with self.assertRaises(RuntimeError):
            prepare(source, other_destination, "Wrong project")
        self.assertEqual(self._remote_handoff_refs(self.origin), source_refs_before)
        self.assertEqual(list((self.root / "other-output").glob("**/repo")), [])

        with self.assertRaises(RuntimeError):
            prepare(source, source, "Same machine")
        self.assertEqual(self._remote_handoff_refs(self.origin), source_refs_before)
        self.assertEqual(list((self.root / "unused-source-output").glob("**/repo")), [])

    def test_repeated_transfer_creates_distinct_worktrees_and_refs(self) -> None:
        source = self._machine("source", self.source, self.root / "unused-source-output")
        destination = self._machine("destination", self.destination, self.output)
        source_head = git(self.source, "rev-parse", "HEAD")

        first = self._assert_result_shape(prepare(source, destination, "First transfer"))
        second = self._assert_result_shape(prepare(source, destination, "Second transfer"))

        self.assertNotEqual(first, second)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.assertEqual(git(first, "rev-parse", "HEAD"), source_head)
        self.assertEqual(git(second, "rev-parse", "HEAD"), source_head)
        self.assertEqual(git(first, "branch", "--show-current"), f"handoff/{first.parent.name}")
        self.assertEqual(git(second, "branch", "--show-current"), f"handoff/{second.parent.name}")
        self.assertEqual(set(self._remote_handoff_refs(self.origin).values()), {source_head})
        self.assertEqual(len(self._remote_handoff_refs(self.origin)), 2)

    def test_source_advancing_during_transfer_prevents_readiness(self) -> None:
        source = self._machine("source", self.source, self.root / "unused-source-output")
        destination = self._machine("destination", self.destination, self.output)
        captured_sha = git(self.source, "rev-parse", "HEAD")
        original_git = source.git

        def concurrent_writer(*args, **kwargs):
            result = original_git(*args, **kwargs)
            if args[0] == "push":
                (self.source / "tracked.txt").write_text("new work after checkpoint\n")
                git(self.source, "add", "tracked.txt")
                git(self.source, "commit", "-m", "concurrent source work")
            return result

        with patch.object(source, "git", side_effect=concurrent_writer):
            result = prepare(source, destination, "Source changed during transfer")

        worktree = self._assert_result_shape(result)
        self.assertEqual(git(worktree, "rev-parse", "HEAD"), captured_sha)
        self.assertNotEqual(git(self.source, "rev-parse", "HEAD"), captured_sha)
        self.assertFalse(result["git_ready"])
        self.assertFalse(result["stable"])

    def test_separate_push_destination_is_rejected_before_publication(self) -> None:
        other_origin = self.root / "wrong-push-origin.git"
        self._make_origin(other_origin, "different project\n")
        git(self.source, "config", "remote.origin.pushurl", str(other_origin))
        source = self._machine("source", self.source, self.root / "unused-source-output")
        destination = self._machine("destination", self.destination, self.output)
        with self.assertRaisesRegex(RuntimeError, "same single URL"):
            prepare(source, destination, "Must not publish to a separate push URL")
        self.assertEqual(self._remote_handoff_refs(self.origin), {})
        self.assertEqual(self._remote_handoff_refs(other_origin), {})
        self.assertEqual(list(self.output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
