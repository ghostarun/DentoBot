#!/usr/bin/env python3
"""Shortcuts for the selected DentoBot checkout and existing handoff tools."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import handoff
import visible_case


CONFIG = Path.home() / ".config/dentobot/commands.json"


def read_config(path):
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("active_machine") not in ("A", "B"):
        raise RuntimeError("config needs active_machine A or B")
    if not isinstance(data.get("machines"), dict) or not isinstance(
        data["machines"].get(data["active_machine"]), dict
    ):
        raise RuntimeError("config needs settings for the active machine")
    return data


def write_config(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".commands-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=CONFIG)
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("path", help="print the selected local checkout")
    use = commands.add_parser("use", help="select a local checkout and pin its current HEAD")
    use.add_argument("repo", type=Path)
    status = commands.add_parser("status", help="inspect Git state; never modifies a checkout")
    status.add_argument("--machine", choices=("A", "B"))
    check = commands.add_parser("check", help="run the read-only runtime preflight")
    check.add_argument("--expected-sha", help="override the selected checkpoint SHA")
    check.add_argument("--image-id", help="override the local image pin")
    check.add_argument("--display")
    check.add_argument("--xauthority")
    check.add_argument("--data-manifest")
    for name in ("from-a", "to-a"):
        transfer = commands.add_parser(name, help="prepare a new worktree; requires both hosts online")
        transfer.add_argument("--note", required=True)
        if name == "from-a":
            transfer.add_argument("--committed-only", action="store_true")
    commands.add_parser("parity", help="verify the common image, native runtime and pinned assets")
    case = commands.add_parser("sync-case", help="checksum-transfer one saved .dentocase from this machine")
    case.add_argument("path", help="path relative to workspace/data")
    case.add_argument("--to", choices=("A", "B"), required=True)
    case.add_argument("--replace", action="store_true", help="retain a backup before updating a different destination")
    commands.add_parser("open", help="open the selected checkout in the local T3 desktop")
    launch = commands.add_parser("launch", help="launch the selected checkout using its verified installed runtime")
    launch.add_argument("--check-only", action="store_true", help="run launcher checks without opening Slicer")
    smoke = commands.add_parser("smoke", help="prepare a fresh no-case smoke; --run executes it")
    smoke.add_argument("--expected-sha")
    smoke.add_argument("--image-id")
    smoke.add_argument("--run", action="store_true")
    visible_case.add_subcommands(commands)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        config = read_config(args.config)
        active = config["active_machine"]
        machines = handoff._load_config(args.config)
        machine = handoff.Machine(active, machines[active])
        if machine.host is not None:
            raise RuntimeError("active_machine must identify this host; use the handoff CLI for remote execution")
        if args.command == "visible-case":
            return visible_case.dispatch(args, active=active, machines=machines)
        selected = config["machines"][active]
        if args.command == "parity":
            import runtime_sync
            result = runtime_sync.parity(Path(machine.repo))
            print(json.dumps(result, indent=2))
            return 0 if result["passed"] else 2
        if args.command == "sync-case":
            if args.to == active:
                raise RuntimeError("destination must be the other machine")
            import case_sync
            result = case_sync.sync_case(machine, handoff.Machine(args.to, machines[args.to]), args.path, args.replace)
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "path":
            print(machine.repo)
            return 0
        if args.command == "use":
            candidate = str(args.repo.expanduser().resolve())
            settings = {**machines[active], "repo": candidate}
            state = handoff.collect(handoff.Machine(active, settings))
            if state["branch"] == "HEAD":
                raise RuntimeError("select a checkout on a branch, not detached HEAD")
            original = handoff.collect(machine)
            if state["origin"] != original["origin"]:
                raise RuntimeError("selected checkout origin differs from the current DentoBot origin")
            selected.update(repo=candidate, expected_sha=state["sha"])
            write_config(args.config, config)
            print(json.dumps(state, indent=2))
            return 0
        if args.command == "status":
            return handoff.main(["--config", str(args.config), "inspect", "--machine", args.machine or active])
        if args.command in ("check", "smoke", "from-a", "to-a") and (Path(machine.repo) / "Workspace/runtime-lock.json").exists():
            import runtime_sync
            result = runtime_sync.parity(Path(machine.repo))
            if not result["passed"]:
                print(json.dumps(result, indent=2))
                return 2
        if args.command == "launch":
            if not (Path(machine.repo) / "Workspace/runtime-lock.json").is_file():
                raise RuntimeError("launch requires a versioned runtime lock")
            state = handoff.collect(machine)
            if state["dirty"] or state["sha"] != selected.get("expected_sha"):
                raise RuntimeError("launch requires the clean selected checkpoint; commit then explicitly dentobot use")
            command = ["bash", str(Path(machine.repo) / "Workspace/scripts/launch-dentoworkflow.bash"),
                       "--use-installed-runtime"]
            if args.check_only:
                command.append("--check-only")
            return subprocess.run(command, check=False).returncode
        if args.command in ("from-a", "to-a"):
            if active != "B":
                raise RuntimeError("from-a/to-a shortcuts run on B; use dentobot-handoff on A")
            source, destination = ("A", "B") if args.command == "from-a" else ("B", "A")
            command = ["--config", str(args.config), "prepare", "--source", source,
                       "--destination", destination, "--note", args.note]
            if getattr(args, "committed_only", False):
                command.append("--committed-only")
            return handoff.main(command)
        if args.command == "open":
            return subprocess.run(["t3", "app", machine.repo], check=False).returncode
        sha = args.expected_sha or selected.get("expected_sha")
        image = args.image_id or selected.get("image_id")
        if not sha or not image:
            raise RuntimeError("select a checkpoint SHA and image ID in config or pass explicit flags")
        if args.command == "smoke":
            import smoke_runtime
            command = ["--repo", machine.repo, "--expected-sha", sha, "--image-id", image]
            if args.run:
                command.append("--run")
            return smoke_runtime.main(command)
        command = ["--config", str(args.config), "doctor", "--machine", active,
                   "--expected-sha", sha, "--image-id", image]
        if not args.data_manifest and (Path(machine.repo) / "Workspace/runtime-data-manifest.json").exists():
            args.data_manifest = str(Path(machine.repo) / "Workspace/runtime-data-manifest.json")
        for name in ("display", "xauthority", "data_manifest"):
            value = getattr(args, name)
            if value:
                command.extend(("--" + name.replace("_", "-"), value))
        return handoff.main(command)
    except (RuntimeError, OSError) as exc:
        print(f"dentobot: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
