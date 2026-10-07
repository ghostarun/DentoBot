#!/usr/bin/env python3
"""Read-only verification of a DentoBot runtime lock against the local host."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


CONTAINER = "dentobot-slicerros2"


def _command(argv: list[str]) -> tuple[str | None, str | None]:
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=20, check=False, env=env)
    except subprocess.TimeoutExpired:
        return None, "timed out after 20s"
    except OSError:
        return None, "could not start command"
    if result.returncode:
        return None, f"exited with status {result.returncode}"
    return result.stdout.strip(), None


def _safe_path(raw: object) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw or any(ord(c) < 32 for c in raw):
        raise ValueError("path must be a non-empty POSIX relative path")
    path = PurePosixPath(raw)
    if path.is_absolute() or re.match(r"^[A-Za-z]:", raw) or ".." in path.parts or not path.parts:
        raise ValueError("path must stay relative to its manifest root")
    return path.as_posix()


def _entries(value: object, label: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    result, seen = [], set()
    for number, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise ValueError(f"{label} entry {number} must be an object")
        path = _safe_path(item.get("path"))
        digest = item.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError(f"{label} entry {number} has an invalid SHA-256")
        if path in seen:
            raise ValueError(f"{label} contains duplicate path {path}")
        seen.add(path)
        result.append({"path": path, "sha256": digest.lower()})
    return result


def _load_manifest(path: Path) -> tuple[dict | None, str | None]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "runtime lock is missing or invalid JSON"
    if not isinstance(raw, dict):
        return None, "runtime lock must be a JSON object"

    image_id = raw.get("image_id")
    image_name = raw.get("image_name")
    native_sha = raw.get("native_sha")
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", image_id):
        return None, "image_id must be a full sha256 Docker ID"
    if (not isinstance(image_name, str) or not image_name or any(c.isspace() for c in image_name)
            or ":" not in image_name.rsplit("/", 1)[-1]):
        return None, "image_name must include a tag"
    if not isinstance(native_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", native_sha):
        return None, "native_sha must be a full Git SHA"
    try:
        native_files = _entries(raw.get("native_files"), "native_files")
        data_files = _entries(raw.get("data_files"), "data_files")
        ros_files = _entries(raw["ros_files"], "ros_files") if "ros_files" in raw else None
    except ValueError as exc:
        return None, str(exc)
    return {
        "image_id": image_id.lower(), "image_name": image_name,
        "native_sha": native_sha.lower(), "native_files": native_files,
        "data_files": data_files, "ros_files": ros_files,
    }, None


def _hash_files(root: Path, entries: list[dict[str, str]]) -> dict:
    details = []
    try:
        resolved_root = root.resolve(strict=True)
    except (OSError, RuntimeError):
        return {"passed": False, "details": "manifest root is missing", "files": []}

    for entry in entries:
        path = entry["path"]
        check = {"path": path, "expected_sha256": entry["sha256"]}
        try:
            resolved = (resolved_root / Path(*PurePosixPath(path).parts)).resolve(strict=True)
            try:
                resolved.relative_to(resolved_root)
            except ValueError:
                check.update({"passed": False, "details": "path escapes manifest root"})
                details.append(check)
                continue
            if not resolved.is_file():
                raise ValueError("not a regular file")
            digest = hashlib.sha256()
            with resolved.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            actual = digest.hexdigest()
            check.update({"actual_sha256": actual, "passed": actual == entry["sha256"]})
            if actual != entry["sha256"]:
                check["details"] = "checksum mismatch"
        except ValueError as exc:
            check.update({"passed": False, "details": str(exc)})
        except (OSError, RuntimeError):
            check.update({"passed": False, "details": "file is missing or unreadable"})
        details.append(check)

    passed = all(item["passed"] for item in details)
    return {
        "passed": passed,
        "details": f"{len(details)} file(s) match" if passed else "one or more file checks failed",
        "files": details,
    }


def _skipped(message: str) -> dict:
    return {"passed": False, "details": message}


def parity(repo: str | Path) -> dict:
    """Compare the selected checkout, image, container, and locked file hashes."""
    checks: dict[str, dict] = {}
    report = {"passed": False, "checks": checks}
    try:
        checkout = Path(repo).expanduser().resolve()
        workspace = checkout.parents[2]
    except (OSError, IndexError, RuntimeError, TypeError, ValueError):
        checks["manifest"] = _skipped("repo path cannot determine workspace")
        for name in ("native_git", "image_tag", "container_image", "native_files", "data_files"):
            checks[name] = _skipped("runtime lock is unavailable")
        return report

    report["repo"] = str(checkout)
    report["workspace"] = str(workspace)
    manifest_path = checkout / "Workspace" / "runtime-lock.json"
    manifest, error = _load_manifest(manifest_path)
    checks["manifest"] = {"passed": manifest is not None, "details": error or "runtime lock is valid"}
    if manifest is None:
        for name in ("native_git", "image_tag", "container_image", "native_files", "data_files"):
            checks[name] = _skipped("not checked because runtime lock is invalid")
        return report

    native_repo = workspace / "ros2_ws" / "src" / "slicer_ros2_module"
    head, error = _command(["git", "-C", str(native_repo), "rev-parse", "HEAD"])
    status, status_error = _command([
        "git", "-c", "core.fsmonitor=false", "-C", str(native_repo),
        "status", "--porcelain", "--untracked-files=all",
    ])
    clean = status == ""
    git_ok = error is None and status_error is None and head == manifest["native_sha"] and clean
    checks["native_git"] = {
        "passed": git_ok,
        "expected_sha": manifest["native_sha"],
        "actual_sha": head,
        "clean": clean if status_error is None else None,
        "details": ("HEAD matches and checkout is clean" if git_ok else
                    error or status_error or ("HEAD differs from runtime lock" if head != manifest["native_sha"] else "checkout is dirty")),
    }

    image_id, error = _command([
        "docker", "image", "inspect", "--format", "{{.Id}}", manifest["image_name"],
    ])
    checks["image_tag"] = {
        "passed": error is None and image_id == manifest["image_id"],
        "expected_id": manifest["image_id"], "actual_id": image_id,
        "details": ("tag resolves to locked image" if error is None and image_id == manifest["image_id"]
                    else error or "tag resolves to a different image"),
    }

    container_id, error = _command([
        "docker", "container", "inspect", "--format", "{{.Image}}", CONTAINER,
    ])
    checks["container_image"] = {
        "passed": error is None and container_id == manifest["image_id"],
        "expected_id": manifest["image_id"], "actual_id": container_id,
        "details": ("container uses locked image" if error is None and container_id == manifest["image_id"]
                    else error or "container uses a different image"),
    }

    checks["native_files"] = _hash_files(
        workspace / "ros2_ws" / "install" / "slicer_ros2_module", manifest["native_files"],
    )
    checks["data_files"] = _hash_files(workspace / "data", manifest["data_files"])
    if manifest["ros_files"] is not None:
        checks["ros_files"] = _hash_files(workspace / "ros2_ws" / "install", manifest["ros_files"])
    report["passed"] = all(check["passed"] for check in checks.values())
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args(argv)
    result = parity(args.repo)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
