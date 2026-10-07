#!/usr/bin/env python3
"""Prepare a pinned Git handoff between the A and B ThinkStation machines."""

from __future__ import annotations

import argparse
import json
import posixpath
import shlex
import socket
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


DEFAULTS = {
    "A": {
        "host": "dentobot-a",
        "repo": "/home/tarun/dentobot/ros2_ws/src/DentoBot",
        "output": "/home/tarun/dentobot-handoffs",
        "worktree_root": "/home/tarun/dentobot/ros2_ws/src",
    },
    "B": {
        "host": "dentobot-b",
        "repo": "/home/light-tarun/dentobot/ros2_ws/src/DentoBot",
        "output": "/home/light-tarun/dentobot-handoffs",
        "worktree_root": "/home/light-tarun/dentobot/ros2_ws/src",
    },
}

SSH_OPTIONS = [
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=15",
]


class Machine:
    def __init__(self, name, settings):
        self.name = name
        self.settings = dict(settings)
        if not self.settings.get("repo") or not self.settings.get("output"):
            raise RuntimeError(f"machine {name} needs repo and output paths")
        host = self.settings.get("host")
        if host is not None and (not isinstance(host, str) or not host):
            raise RuntimeError(f"machine {name} host must be a name or null")

    @property
    def host(self):
        return self.settings.get("host")

    @property
    def repo(self):
        return self.settings["repo"]

    @property
    def output(self):
        return self.settings["output"]

    def run(self, argv, input=None, timeout=30, allowed_returncodes=(0,)):
        argv = [str(arg) for arg in argv]
        if argv and argv[0] == "git":
            argv = ["env", "GIT_TERMINAL_PROMPT=0", *argv]
        if self.host is None:
            command = argv
        else:
            remote = " ".join(shlex.quote(arg) for arg in argv)
            command = ["ssh", *SSH_OPTIONS, self.host, remote]
        try:
            result = subprocess.run(
                command, input=input, capture_output=True, text=True,
                timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"{self.name}: command timed out after {timeout}s") from exc
        except OSError as exc:
            raise RuntimeError(f"{self.name}: cannot run command: {exc}") from exc
        if result.returncode not in allowed_returncodes:
            detail = (result.stderr or result.stdout).strip().replace("\n", " ")
            if len(detail) > 700:
                detail = detail[:697] + "..."
            raise RuntimeError(
                f"{self.name}: command failed ({result.returncode})"
                + (f": {detail}" if detail else "")
            )
        return result.stdout

    def git(self, *args, timeout=30):
        return self.run(["git", "-C", self.repo, *args], timeout=timeout)


def _default_config():
    machines = {name: dict(settings) for name, settings in DEFAULTS.items()}
    host = socket.gethostname().lower()
    local = "A" if "legion" in host else "B" if "thinkstation" in host else None
    if local:
        machines[local]["host"] = None
    return machines


def _load_config(path):
    machines = _default_config()
    if not path:
        return machines
    try:
        with open(path, encoding="utf-8") as stream:
            raw = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read config {path}: {exc}") from exc
    overrides = raw.get("machines", raw) if isinstance(raw, dict) else None
    if not isinstance(overrides, dict):
        raise RuntimeError("config must be an object with machine settings")
    for name, settings in overrides.items():
        if name not in machines:
            raise RuntimeError(f"unknown machine in config: {name}")
        if not isinstance(settings, dict):
            raise RuntimeError(f"config for machine {name} must be an object")
        machines[name].update(settings)
    return machines


def collect(machine):
    """Read the current Git identity and working-tree status."""
    branch = machine.git("rev-parse", "--abbrev-ref", "HEAD").strip()
    sha = machine.git("rev-parse", "HEAD").strip()
    status = machine.git(
        "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=none"
    )
    origin = machine.git("remote", "get-url", "origin").strip()
    push_origins = machine.git("remote", "get-url", "--push", "--all", "origin").splitlines()
    return {
        "machine": machine.name,
        "repo": machine.repo,
        "branch": branch,
        "sha": sha,
        "status": status,
        "dirty": bool(status),
        "origin": origin,
        "push_origins": push_origins,
    }


def _check_path_layout(machine, worktree_parent):
    script = (
        "import os,sys\n"
        "repo, output = map(os.path.realpath, sys.argv[1:])\n"
        "if os.path.commonpath((repo, output)) == repo:\n"
        "    raise SystemExit('handoff output must be outside the checkout')\n"
    )
    machine.run(["python3", "-c", script, machine.repo, worktree_parent])


def _reserve_record(machine, record_dir):
    script = (
        "import os,sys\n"
        "base, record = sys.argv[1:]\n"
        "os.makedirs(base, exist_ok=True)\n"
        "os.mkdir(record)\n"
    )
    machine.run(["python3", "-c", script, machine.output, record_dir])


def _write_record(machine, record_dir, manifest, prompt):
    script = (
        "import json,os,sys\n"
        "root=sys.argv[1]\n"
        "data=json.load(sys.stdin)\n"
        "for name, value in data.items():\n"
        "    with open(os.path.join(root,name),'x',encoding='utf-8') as f: f.write(value)\n"
    )
    payload = json.dumps({
        "manifest.json": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        "CONTINUE.md": prompt,
    })
    machine.run(["python3", "-c", script, record_dir], input=payload)


def _tracked_lfs_attribute_roots(machine, worktree):
    roots = [worktree]
    submodules = machine.run([
        "git", "-C", worktree, "submodule", "foreach", "--quiet", "--recursive",
        'printf "%s\\0" "$PWD"',
    ], timeout=1800)
    roots.extend(
        path if posixpath.isabs(path) else posixpath.join(worktree, path)
        for path in submodules.split("\0") if path
    )
    lfs_roots = []
    for root in roots:
        listing = machine.run(["git", "-C", root, "ls-files", "-z"], timeout=1800)
        for path in listing.split("\0"):
            if path.endswith(".gitattributes"):
                content = machine.run(
                    ["git", "-C", root, "show", f"HEAD:{path}"], timeout=1800
                )
                if any("filter=lfs" in line.split() and not line.lstrip().startswith("#")
                       for line in content.splitlines()):
                    lfs_roots.append(root)
                    break
    return lfs_roots


def _continue_text(manifest):
    source = manifest["source"]
    destination = manifest["destination"]
    status = source["status"] or "clean"
    readiness = "Git snapshot is ready." if manifest["git_ready"] else (
        "Git snapshot is pinned, but readiness checks did not pass."
    )
    return f"""# Continue handoff {manifest['id']}

{readiness}

Note: {manifest['note']}

- Source: {source['machine']} branch `{source['branch']}`, commit `{source['sha']}`
- Source status at capture: `{status}`
- Destination: {destination['machine']} worktree `{destination['worktree']}`
- Handoff ref: `{manifest['source_ref']}`
- Runtime verified: no

Only committed Git contents are transferred. Untracked and ignored files, runtime data,
build outputs, and scenes are not synced. Pause source writers before a full handoff;
this tool cannot stop agents or processes. Runtime behavior still needs separate verification.
"""


def prepare(source, destination, note, committed_only=False):
    if source.name == destination.name or (
        source.host == destination.host and source.repo == destination.repo
    ):
        raise RuntimeError("source and destination must be different machines/checkouts")
    if not isinstance(note, str) or not note.strip():
        raise RuntimeError("note must not be empty")

    before = collect(source)
    if before["branch"] == "HEAD":
        raise RuntimeError("source checkout is detached")
    if before["dirty"] and not committed_only:
        raise RuntimeError("source checkout is dirty; use --committed-only for a pinned snapshot")
    target = collect(destination)
    if before["origin"] != target["origin"]:
        raise RuntimeError("source and destination origin URLs differ")
    if before["push_origins"] != [before["origin"]]:
        raise RuntimeError("source origin must push to the same single URL used for fetching")

    created = datetime.now(timezone.utc)
    stamp = created.strftime("%Y%m%dT%H%M%SZ")
    handoff_id = f"{stamp}-{uuid.uuid4().hex}"
    branch = f"handoff/{handoff_id}"
    ref = f"refs/heads/{branch}"
    record_dir = posixpath.join(destination.output, handoff_id)
    worktree = posixpath.join(record_dir, "repo")
    worktree_root = destination.settings.get("worktree_root")
    if worktree_root:
        worktree = posixpath.join(worktree_root, f"DentoBot-handoff-{handoff_id}")
    manifest_path = posixpath.join(record_dir, "manifest.json")
    prompt_path = posixpath.join(record_dir, "CONTINUE.md")
    _check_path_layout(destination, record_dir)
    _check_path_layout(destination, worktree)
    existing = source.git("ls-remote", "origin", ref, timeout=1800)
    if any(line.split()[1:2] == [ref] for line in existing.splitlines()):
        raise RuntimeError(f"handoff ref already exists: {ref}")
    _reserve_record(destination, record_dir)

    destination_manifest = {
        "machine": destination.name,
        "repo": destination.repo,
        "origin": target["origin"],
        "branch": branch,
        "ref": ref,
        "worktree": worktree,
    }
    if worktree_root:
        destination_manifest["workspace_root"] = posixpath.dirname(
            posixpath.dirname(worktree_root.rstrip("/"))
        )
        destination_manifest["container_repo"] = (
            f"/workspace/ros2_ws/src/DentoBot-handoff-{handoff_id}"
        )
    manifest = {
        "id": handoff_id,
        "created_utc": created.isoformat().replace("+00:00", "Z"),
        "note": note,
        "committed_only": bool(committed_only),
        "source": {**before, "ref": ref},
        "source_ref": ref,
        "destination_ref": ref,
        "destination": destination_manifest,
        "source_after": None,
        "stable": False,
        "git_ready": False,
        "runtime_verified": False,
        "safe_to_shutdown": False,
        "ignored": [
            "untracked and ignored files",
            "runtime data",
            "build outputs",
            "scenes",
        ],
    }

    try:
        source.git("push", "--porcelain", "origin", f"{before['sha']}:{ref}", timeout=1800)
        remote = source.git("ls-remote", "--exit-code", "origin", ref, timeout=1800)
        matches = [line.split() for line in remote.splitlines() if line.strip()]
        if not any(len(row) >= 2 and row[0] == before["sha"] and row[1] == ref for row in matches):
            raise RuntimeError("origin did not advertise the exact pushed handoff commit")

        tracking_ref = f"refs/remotes/origin/{branch}"
        destination.git(
            "fetch", "--no-tags", "origin", f"{ref}:{tracking_ref}", timeout=1800
        )
        destination.git("worktree", "add", "-b", branch, worktree, before["sha"], timeout=1800)
        destination.run([
            "git", "-C", worktree, "branch", "--set-upstream-to", f"origin/{branch}"
        ])
        destination.run(
            ["git", "-C", worktree, "submodule", "update", "--init", "--recursive"],
            timeout=1800,
        )
        for root in _tracked_lfs_attribute_roots(destination, worktree):
            destination.run(["git", "-C", root, "lfs", "version"], timeout=60)
            destination.run(["git", "-C", root, "lfs", "pull"], timeout=1800)
            destination.run(["git", "-C", root, "lfs", "fsck"], timeout=1800)

        worktree_sha = destination.run(
            ["git", "-C", worktree, "rev-parse", "HEAD"]
        ).strip()
        worktree_branch = destination.run(
            ["git", "-C", worktree, "symbolic-ref", "--short", "HEAD"]
        ).strip()
        worktree_status = destination.run([
            "git", "-C", worktree, "status", "--porcelain", "--untracked-files=all",
            "--ignore-submodules=none",
        ])
        try:
            after = collect(source)
        except Exception as exc:
            after = None
            source_check_error = str(exc)
        else:
            source_check_error = None
        target_after = collect(destination)
        stable = after is not None and (
            after["sha"] == before["sha"]
            and after["status"] == before["status"]
            and after["branch"] == before["branch"]
            and after["origin"] == before["origin"]
            and after["push_origins"] == before["push_origins"]
        )
        dest_valid = (
            worktree_sha == before["sha"]
            and worktree_branch == branch
            and not worktree_status
            and target_after["origin"] == before["origin"]
        )
        ready = not before["dirty"] and stable and dest_valid
        reasons = []
        if before["dirty"]:
            reasons.append("source was dirty; only its committed HEAD was transferred")
        if not stable:
            reasons.append(source_check_error or "source SHA, branch, status, or origin changed during preparation")
        if not dest_valid:
            reasons.append("destination worktree verification failed")
        manifest["source_after"] = after
        manifest["destination"]["status"] = worktree_status
        manifest["stable"] = stable
        upstream_sha = destination.run([
            "git", "-C", worktree, "rev-parse", tracking_ref
        ]).strip()
        if upstream_sha != before["sha"]:
            ready = False
            reasons.append("destination upstream does not point to the pinned commit")
        manifest["git_ready"] = ready
        if reasons:
            manifest["readiness_error"] = "; ".join(reasons)
    except Exception as exc:
        manifest["failure"] = str(exc)
        try:
            manifest["source_after"] = collect(source)
            manifest["stable"] = (
                manifest["source_after"]["sha"] == before["sha"]
                and manifest["source_after"]["status"] == before["status"]
                and manifest["source_after"]["branch"] == before["branch"]
                and manifest["source_after"]["origin"] == before["origin"]
                and manifest["source_after"]["push_origins"] == before["push_origins"]
            )
        except Exception:
            pass
        try:
            _write_record(destination, record_dir, manifest, _continue_text(manifest))
        except Exception:
            pass
        if isinstance(exc, RuntimeError):
            raise RuntimeError(f"{exc} (record: {manifest_path})") from exc
        raise RuntimeError(f"handoff preparation failed: {exc} (record: {manifest_path})") from exc

    _write_record(destination, record_dir, manifest, _continue_text(manifest))
    result = {
        "id": handoff_id,
        "source": before,
        "destination": manifest["destination"],
        "source_ref": ref,
        "destination_ref": ref,
        "manifest": manifest_path,
        "worktree": worktree,
        "prompt": prompt_path,
        "git_ready": ready,
        "stable": stable,
        "safe_to_shutdown": False,
        "created_utc": manifest["created_utc"],
    }
    if reasons:
        result["error"] = manifest["readiness_error"]
    return result


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="JSON file overriding machine host, repo, and output")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="read Git state on one machine")
    inspect.add_argument("--machine", required=True, choices=("A", "B"))
    inspect.add_argument("--repo", help="override that machine's repository path")
    prepare_parser = commands.add_parser("prepare", help="prepare a pinned Git handoff")
    prepare_parser.add_argument("--source", required=True, choices=("A", "B"))
    prepare_parser.add_argument("--destination", required=True, choices=("A", "B"))
    prepare_parser.add_argument("--source-repo", help="override the source repository path")
    prepare_parser.add_argument("--destination-repo", help="override the destination repository path")
    prepare_parser.add_argument("--note", required=True)
    prepare_parser.add_argument("--committed-only", action="store_true")
    doctor = commands.add_parser("doctor", help="run pinned runtime preflight checks")
    doctor.add_argument("--machine", required=True, choices=("A", "B"))
    doctor.add_argument("--repo", help="override that machine's repository path")
    doctor.add_argument("--expected-sha", required=True)
    doctor.add_argument("--image-id")
    doctor.add_argument("--display")
    doctor.add_argument("--data-manifest")
    doctor.add_argument("--xauthority")
    return parser


def _doctor(machine, expected_sha, image_id=None, display=None, data_manifest=None,
            xauthority=None):
    helper = Path(__file__).resolve().with_name("runtime_preflight.py")
    try:
        script = helper.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read runtime preflight helper: {exc}") from exc
    command = [
        "python3", "-", "--repo", machine.repo, "--expected-sha", expected_sha,
    ]
    for flag, value in (
        ("--image-id", image_id),
        ("--display", display),
        ("--data-manifest", data_manifest),
        ("--xauthority", xauthority),
    ):
        if value is not None:
            command.extend((flag, value))
    output = machine.run(
        command, input=script, allowed_returncodes=(0, 2), timeout=120
    )
    try:
        result = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"runtime preflight returned invalid JSON: {exc}") from exc
    if not isinstance(result, dict) or not isinstance(result.get("preflight_passed"), bool):
        raise RuntimeError("runtime preflight JSON must contain a boolean preflight_passed")
    result["runtime_verified"] = False
    result["loaded_code_verified"] = False
    result["safe_to_shutdown"] = False
    return result


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        settings = _load_config(args.config)
        if args.command == "inspect":
            machine_settings = dict(settings[args.machine])
            if args.repo:
                machine_settings["repo"] = args.repo
            result = collect(Machine(args.machine, machine_settings))
        elif args.command == "doctor":
            machine_settings = dict(settings[args.machine])
            if args.repo:
                machine_settings["repo"] = args.repo
            result = _doctor(
                Machine(args.machine, machine_settings),
                args.expected_sha,
                image_id=args.image_id,
                display=args.display,
                data_manifest=args.data_manifest,
                xauthority=args.xauthority,
            )
        else:
            source_settings = dict(settings[args.source])
            destination_settings = dict(settings[args.destination])
            if args.source_repo:
                source_settings["repo"] = args.source_repo
            if args.destination_repo:
                destination_settings["repo"] = args.destination_repo
            result = prepare(
                Machine(args.source, source_settings),
                Machine(args.destination, destination_settings),
                args.note,
                committed_only=args.committed_only,
            )
    except RuntimeError as exc:
        print(f"handoff: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.command == "doctor" and not result["preflight_passed"]:
        return 2
    if args.command == "prepare" and not args.committed_only and not result["git_ready"]:
        print("handoff: Git readiness checks failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
