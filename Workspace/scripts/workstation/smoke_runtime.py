#!/usr/bin/env python3
"""Prepare or run one private-Xvfb, no-case DentoBot Slicer reload smoke test."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime_preflight import effective_config, parse_compose_image, parse_env_file

CONTAINER = "dentobot-slicerros2"
LOCK_NAMES = ("docker-dentobot-slicerros2", "slicer_process", "mrml_scene", "display",
              "colcon_install", "ros_domain-73")
PROCESS_NAMES = ("SlicerApp-real", "move_group", "Xvfb", "ffmpeg")
MODULES = {
    "dentobot_workflow.widget_application": "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_application.py",
    "dentobot_workflow.widget_robot": "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot.py",
    "DENTOROS2Bridge": "DENTOWorkflow/Resources/Python/DENTOROS2Bridge.py",
}


class SmokeError(RuntimeError):
    pass


def command(argv, timeout=30):
    try:
        p = subprocess.run([str(x) for x in argv], capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise SmokeError(f"required command is missing: {Path(exc.filename).name}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SmokeError(f"command timed out after {timeout}s") from exc
    return p.returncode, p.stdout, p.stderr


def git(repo, *args):
    code, out, err = command(["git", "-C", repo, *args])
    if code:
        raise SmokeError("Git could not verify the selected checkout")
    return out.strip()


def source_is_clean(repo, expected_sha):
    try:
        return (git(repo, "rev-parse", "HEAD").lower() == expected_sha.lower()
                and not git(repo, "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=none"))
    except SmokeError:
        return False


def launcher_default(text, key):
    match = re.search(rf'(?m)^{key}="\$\{{[^:}}]+:-([^}}]+)}}"$', text)
    if not match or not match.group(1).startswith("/"):
        raise SmokeError(f"could not read the launcher's {key} default")
    return match.group(1)


def inspect_data(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SmokeError("Docker inspect returned invalid metadata") from exc


def validate_container(info, image_id, image_name, workspace, backend_dir, uid, gid, *, allow_idle_running=False):
    if info.get("Running") and not allow_idle_running:
        raise SmokeError("refusing to use a running container; preserve its current owner")
    expected_status = "running" if info.get("Running") else "exited"
    if info.get("Status") != expected_status or info.get("ConfigCmd") != ["sleep", "infinity"]:
        raise SmokeError("container is not a stopped sleep infinity development container")
    if info.get("Image") != image_id or info.get("ConfigImage") != image_name or info.get("ConfigUser") != f"{uid}:{gid}":
        raise SmokeError("container image or configured host user does not match this smoke request")
    required = {
        "/workspace/ros2_ws": (workspace / "ros2_ws", True),
        "/workspace/data": (workspace / "data", True),
        "/home/dentobot": (workspace / "slicer-home", True),
        str(backend_dir): (backend_dir, False),
        "/tmp/.X11-unix": (Path("/tmp/.X11-unix"), True),
    }
    mounts = info.get("Mounts") or []
    for destination, (source, writable) in required.items():
        matches = [m for m in mounts if m.get("Destination") == destination]
        if len(matches) != 1:
            raise SmokeError(f"container mount is missing or duplicated: {destination}")
        mount = matches[0]
        if Path(mount.get("Source", "/missing")).resolve() != source.resolve() or mount.get("RW") is not writable:
            raise SmokeError(f"container mount does not match the expected host path: {destination}")
    return {"id": info.get("Id"), "image_id": info.get("Image"), "user": info.get("ConfigUser"),
            "mount_destinations": sorted(required)}


def make_command(container_repo, evidence, config, model_cache):
    env = {
        "DENTOBOT_CONTAINER_REPOSITORY_ROOT": container_repo,
        "DENTOBOT_SMOKE_EVIDENCE": evidence,
        "DENTOBOT_BACKEND_SOURCE": container_repo + "/Inference/src",
        "DENTOBOT_BACKEND_PYTHON": config["DENTOBOT_BACKEND_PYTHON"],
        "DENTOBOT_BACKEND_DEVICE": "cpu", "DENTOBOT_BACKEND_EXECUTION_MODE": "local",
        "DENTOBOT_RUN_ARTIFACT_ROOT": "/workspace/data/dentobot-runs",
        "TOTALSEG_HOME_DIR": config.get("DENTOBOT_TOTALSEG_HOME_DIR") or model_cache,
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "DENTOBOT_WATCHDOG_DISABLED": "1",
        "ROS_LOG_DIR": evidence + "/ros-log",
        "DENTOBOT_WATCHDOG_LOG_DIR": evidence + "/watchdog",
    }
    argv = ["docker", "exec"]
    for key, value in env.items():
        argv += ["-e", f"{key}={value}"]
    script = '''set -euo pipefail
set +u
source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash
set -u
export PYTHONPATH="${DENTOBOT_CONTAINER_REPOSITORY_ROOT}/Inference/src${PYTHONPATH:+:${PYTHONPATH}}"
export SLICER_ROS2_MODULE_PATHS="${DENTOBOT_CONTAINER_REPOSITORY_ROOT}/DENTOWorkflow${SLICER_ROS2_MODULE_PATHS:+:${SLICER_ROS2_MODULE_PATHS}}"
exec xvfb-run -a -s "-screen 0 1280x800x24 -nolisten tcp" bash -c '
exec python3 "$DENTOBOT_CONTAINER_REPOSITORY_ROOT/Testing/record_slicer_screen.py" --display "$DISPLAY" --output "$DENTOBOT_SMOKE_EVIDENCE/video/smoke.mkv" --fps 5 --command -- ros2 launch slicer_ros2_module slicer.launch.py "slicer_args:=--disable-settings --no-splash --python-script $DENTOBOT_SMOKE_EVIDENCE/bootstrap.py"
'
'''
    return argv + [CONTAINER, "bash", "-lc", script]


def prepare(repo_arg, expected_sha, image_id, now=None):
    if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", expected_sha):
        raise SmokeError("--expected-sha must be a full Git object ID")
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", image_id):
        raise SmokeError("--image-id must be a full sha256 image ID")
    repo = Path(repo_arg).expanduser().resolve()
    if not repo.is_dir() or repo.parent.name != "src" or repo.parent.parent.name != "ros2_ws":
        raise SmokeError("repo must be workspace/ros2_ws/src/<checkout>")
    workspace = repo.parents[2]
    if git(repo, "rev-parse", "HEAD").lower() != expected_sha.lower():
        raise SmokeError("checkout HEAD does not match --expected-sha")
    if git(repo, "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=none"):
        raise SmokeError("checkout is dirty; checkpoint or clean it before smoke setup")
    launcher = repo / "Workspace/scripts/launch-dentoworkflow.bash"
    if (workspace / "compose.override.yaml").exists():
        raise SmokeError("workspace compose.override.yaml is not modeled by this smoke runner")
    try:
        launch_text = launcher.read_text(encoding="utf-8")
        image_name = parse_compose_image((repo / "Workspace/compose.yaml").read_text(encoding="utf-8"))
        values, errors = parse_env_file(workspace / ".dentobot.env")
    except OSError as exc:
        raise SmokeError("required launcher, compose file, or workspace config is missing") from exc
    if errors:
        raise SmokeError("workspace config contains unsupported shell syntax; use literal assignments")
    config, _ = effective_config(values, os.environ)
    config["DENTOBOT_BACKEND_DEVICE"] = config.get("DENTOBOT_BACKEND_DEVICE") or "cpu"
    config["DENTOBOT_BACKEND_EXECUTION_MODE"] = config.get("DENTOBOT_BACKEND_EXECUTION_MODE") or "local"
    if config["DENTOBOT_BACKEND_DEVICE"].lower() != "cpu" or config["DENTOBOT_BACKEND_EXECUTION_MODE"].lower() != "local":
        raise SmokeError("this B smoke runner supports only the CPU/local backend")
    workspace_root = config.get("DENTOBOT_WORKSPACE_ROOT")
    if workspace_root and Path(workspace_root).expanduser().resolve() != workspace:
        raise SmokeError("configured DENTOBOT_WORKSPACE_ROOT differs from inferred workspace")
    try:
        uid = int(config.get("DENTOBOT_HOST_UID") or os.getuid())
        gid = int(config.get("DENTOBOT_HOST_GID") or os.getgid())
    except ValueError as exc:
        raise SmokeError("configured host UID/GID must be integers") from exc
    if (uid, gid) != (os.getuid(), os.getgid()):
        raise SmokeError("configured container host UID/GID do not match the current user")
    backend_python = config.get("DENTOBOT_BACKEND_PYTHON", "")
    if not Path(backend_python).is_absolute() or not Path(backend_python).is_file() or not os.access(backend_python, os.X_OK):
        raise SmokeError("configured DENTOBOT_BACKEND_PYTHON must be an executable absolute path")
    backend_dir = Path(backend_python).parent.parent.resolve()
    config["DENTOBOT_BACKEND_PYTHON"] = backend_python
    model_cache = launcher_default(launch_text, "totalseg_home_dir")
    evidence_script = repo / "Testing/run_dentobot_slicer_reload_smoke.py"
    if not evidence_script.is_file():
        raise SmokeError("checkpoint the five-cycle production More-menu reload smoke runner")
    reload_text = evidence_script.read_text(encoding="utf-8")
    if not all(token in reload_text for token in ("reload_action_available", "_workflowReloadMenuAction", "action.trigger()")) or "reloadDENTOWorkflowButton.click()" in reload_text:
        raise SmokeError("checkpoint the corrected production More > Reload Module (Dev) QAction smoke runner; legacy hidden-button tests are unsupported")
    recorder = repo / "Testing/record_slicer_screen.py"
    if not recorder.is_file():
        raise SmokeError("Testing/record_slicer_screen.py is required for the 5 fps private-Xvfb capture")
    now = now or datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    run_dir = workspace / "data/dentobot-runs" / now.strftime("%Y-%m-%d") / f"PLAT-U-07-smoke-{run_id}"
    container_repo = f"/workspace/ros2_ws/src/{repo.name}"
    container_evidence = "/workspace/data/dentobot-runs/" + run_dir.relative_to(workspace / "data/dentobot-runs").as_posix()
    hashes = {}
    for relative in ("DENTOWorkflow/DENTOWorkflow.py", *MODULES.values()):
        path = repo / relative
        if not path.is_file():
            raise SmokeError(f"loaded source file is missing from checkout: {relative}")
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    run_dir.mkdir(parents=True, exist_ok=False)
    for child in ("video", "ros-log", "watchdog"):
        (run_dir / child).mkdir()
    payload = {"repo": container_repo, "evidence": container_evidence, "hashes": hashes, "modules": MODULES}
    template = Path(__file__).with_name("smoke_bootstrap.py").read_text(encoding="utf-8")
    (run_dir / "bootstrap.py").write_text("SMOKE = " + repr(payload) + "\n" + template, encoding="utf-8")
    argv = make_command(container_repo, container_evidence, config, model_cache)
    plan = {"check": "runtime.slicer_reload", "repo": str(repo), "workspace": str(workspace),
            "expected_sha": expected_sha.lower(), "image_id": image_id.lower(), "image_name": image_name,
            "container_repo": container_repo, "backend_env_dir": str(backend_dir),
            "run_path": str(run_dir), "timeout_sec": 300,
            "scope": "one no-case Slicer reload smoke; private Xvfb; no MoveIt, robot motion, or build",
            "runtime_verified": False, "operator_verified": False, "a_image_parity_verified": False,
            "bootstrap": str(run_dir / "bootstrap.py"), "argv": argv}
    (run_dir / "runtime-command.json").write_text(json.dumps({"argv": argv, "timeout_sec": 300}, indent=2) + "\n")
    (run_dir / "smoke-plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    return plan


def acquire_locks(workspace):
    handles = []
    paths = [Path("/tmp") / f"dentobot-runtime-{name}.lock" for name in LOCK_NAMES]
    paths.append(workspace / "data/dentobot-runtime-test.lock")
    try:
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open("a+")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                handle.close()
                raise SmokeError(f"runtime lock is busy: {path.name}") from exc
            handles.append(handle)
    except Exception:
        release_locks(handles)
        raise
    return handles


def release_locks(handles):
    for handle in reversed(handles):
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()
        except OSError:
            pass


def inspect_container():
    template = ('{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},'
                '"Status":{{json .State.Status}},"ConfigImage":{{json .Config.Image}},'
                '"ConfigCmd":{{json .Config.Cmd}},"ConfigUser":{{json .Config.User}},"Mounts":{{json .Mounts}}}')
    code, out, _ = command(["docker", "inspect", "--format", template, CONTAINER])
    if code:
        raise SmokeError("expected stopped development container is unavailable")
    return inspect_data(out)


def process_count(name, container=False):
    argv = (["docker", "exec", CONTAINER, "pgrep", "-c", "-x", name] if container
            else ["pgrep", "-c", "-x", name])
    code, out, _ = command(argv)
    if code not in (0, 1):
        raise SmokeError(f"could not inspect {name} process ownership")
    try:
        return int(out.strip() or "0")
    except ValueError as exc:
        raise SmokeError(f"could not parse {name} process count") from exc


def assert_no_owners(container=False):
    counts = {name: process_count(name, container) for name in PROCESS_NAMES}
    if any(counts.values()):
        where = "container" if container else "host"
        raise SmokeError(f"{where} runtime process owner is active: {counts}")
    return counts


def evidence_checks(plan, launcher_code, log_text, cleanup_ok, host_after, container_after, decode_code, video):
    base = Path(plan["run_path"])
    try:
        loaded = json.loads((base / "loaded-code.json").read_text())
        reload_result = json.loads((base / "reload-result.json").read_text())
    except (OSError, json.JSONDecodeError):
        loaded, reload_result = {}, {}
    reports = reload_result.get("reports", [])
    fields = ("reload_action_available", "helper_module_reloaded", "internal_module_reloaded",
              "module_reload_success", "scene_preserved", "workspace_explorer_visible")
    rows_ok = (len(reports) == 5 and [row.get("cycle") for row in reports] == [1, 2, 3, 4, 5]
               and all(all(row.get(key) is True for key in fields) for row in reports))
    expected_files = {"DENTOWorkflow/DENTOWorkflow.py", *MODULES.values()}
    loaded_files = loaded.get("files", {})
    loaded_ok = (loaded.get("matched") is True and set(loaded_files) == expected_files
                 and all(item.get("matched") is True for item in loaded_files.values()))
    slicer_exit = reload_result.get("requested_exit_code")
    markers_ok = "DENTOBOT_B_LOADED_CODE_PASS" in log_text and "DENTOBOT_FIVE_RELOAD_CYCLES_PASS" in log_text
    screenshots_ok = all((base / name).is_file() and (base / name).stat().st_size > 0
                         for name in ("startup.png", "final.png")) and not (base / "finish-error.txt").exists()
    source_ok = source_is_clean(plan["repo"], plan["expected_sha"])
    died = re.findall(r"\[Slicer-1\]: process has died \[pid \d+, exit code (-?\d+)(?:,[^\]]*)?\]", log_text)
    clean = re.findall(r"\[Slicer-1\]: process has finished cleanly \[pid \d+\]", log_text)
    actual_slicer_exit = int(died[0]) if len(died) == 1 and not clean else (0 if len(clean) == 1 and not died else None)
    try:
        manifest = json.loads((base / "video/smoke.manifest.json").read_text())
        actual_sha = hashlib.sha256(video.read_bytes()).hexdigest()
    except (OSError, json.JSONDecodeError):
        manifest, actual_sha = {}, ""
    video_ok = (video.is_file() and video.stat().st_size > 0 and decode_code == 0
                and manifest.get("schema") == "dentobot.screen-recording.v1"
                and manifest.get("status") == "complete" and manifest.get("exit_status") == 0
                and manifest.get("command_exit_status") == 0 and manifest.get("ffmpeg_exit_status") == 0
                and manifest.get("output_sha256") == actual_sha)
    checks = {"ros_launcher_exit_code": launcher_code == 0, "slicer_requested_exit_code": slicer_exit == 0,
              "slicer_process_exit_code": actual_slicer_exit == 0,
              "loaded_code_paths_and_hashes": loaded_ok, "five_reload_rows_six_assertions": rows_ok,
              "success_markers": markers_ok, "screenshots_saved": screenshots_ok,
              "video_manifest_checksum_and_decode": video_ok,
              "container_stopped": cleanup_ok, "no_host_process_owners": not any(host_after.values()),
              "no_container_process_owners": not any(container_after.values()), "source_still_clean": source_ok}
    return {"checks": checks, "reload_reports": len(reports), "slicer_requested_exit_code": slicer_exit,
            "slicer_process_exit_code": actual_slicer_exit,
            "video": {"path": str(video), "sha256": actual_sha or None,
                      "manifest": str(base / "video/smoke.manifest.json"), "decode_exit_code": decode_code},
            "runtime_verified": all(checks.values()), "operator_verified": False, "a_image_parity_verified": False}


def await_owned_exit():
    """Allow xvfb-run's exit trap to reap its server before asserting cleanup."""
    deadline = time.monotonic() + 3.0
    while True:
        try:
            return assert_no_owners(container=True)
        except SmokeError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


def execute(plan, evidence_fn=None):
    result = {"run_path": plan["run_path"], "runtime_verified": False,
              "operator_verified": False, "a_image_parity_verified": False, "launcher_exit_code": None}
    handles, started, proc, container_id = [], False, None, None
    cleanup_ok, host_after, container_after = False, {}, {}
    try:
        for tool in ("docker", "pgrep", "xvfb-run", "ffmpeg"):
            if not shutil.which(tool):
                raise SmokeError(f"required command is missing: {tool}")
        timeout_sec = plan.get("timeout_sec", 300)
        if not isinstance(timeout_sec, int) or isinstance(timeout_sec, bool) or not 30 <= timeout_sec <= 900:
            raise SmokeError("runtime timeout must be between 30 and 900 seconds")
        workspace, backend_dir = Path(plan["workspace"]), Path(plan["backend_env_dir"])
        handles = acquire_locks(workspace)
        host_before = assert_no_owners()
        info = inspect_container()
        code, out, _ = command(["docker", "image", "inspect", "--format", "{{.Id}}", info.get("ConfigImage", "")])
        if code or out.strip() != plan["image_id"]:
            raise SmokeError("configured Docker image is missing or differs from --image-id")
        summary = validate_container(info, plan["image_id"], plan["image_name"], workspace, backend_dir, os.getuid(), os.getgid())
        container_id = info["Id"]
        if not source_is_clean(plan["repo"], plan["expected_sha"]):
            raise SmokeError("source checkout changed before Docker start")
        (Path(plan["run_path"]) / "ownership-before.json").write_text(json.dumps(
            {"container": summary, "host_process_counts": host_before, "owner_pid": os.getpid(),
             "started_at_utc": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n")
        # Under the acquired runtime locks, the verified stopped container is now ours to start.
        # Set this before invoking Docker so a command timeout still reaches identity-guarded cleanup.
        started = True
        code, _, _ = command(["docker", "start", CONTAINER], timeout=30)
        if code:
            raise SmokeError("Docker could not start the verified stopped container")
        after_start = inspect_container()
        if after_start.get("Id") != container_id or not after_start.get("Running"):
            raise SmokeError("container identity changed during start")
        container_before = assert_no_owners(container=True)
        with (Path(plan["run_path"]) / "slicer.log").open("w") as log:
            proc = subprocess.Popen(plan["argv"], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                result["launcher_exit_code"] = proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                result["timed_out"] = True
                raise SmokeError(f"Slicer runtime exceeded the {timeout_sec} second timeout")
        container_after = await_owned_exit()
        log_text = (Path(plan["run_path"]) / "slicer.log").read_text(errors="replace")
        video = Path(plan["run_path"]) / "video/smoke.mkv"
        result["process_counts"] = {"host_before": host_before, "container_before": container_before,
                                    "container_after": container_after}
    except (SmokeError, OSError) as exc:
        result["error"] = str(exc) if isinstance(exc, SmokeError) else "could not write or read smoke evidence"
    finally:
        if started:
            try:
                current = inspect_container()
                if current.get("Id") != container_id:
                    raise SmokeError("container identity changed; refusing to stop a different container")
                if current.get("Running"):
                    code, _, _ = command(["docker", "stop", "--time", "30", CONTAINER], timeout=45)
                    if code:
                        raise SmokeError("could not stop the container started by this smoke runner")
                final = inspect_container()
                cleanup_ok = final.get("Id") == container_id and not final.get("Running")
                if not cleanup_ok:
                    raise SmokeError("owned container was not confirmed stopped")
            except SmokeError as exc:
                result["cleanup_error"] = str(exc)
            if proc and proc.poll() is None:
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    result["cleanup_error"] = "docker exec did not exit after the owned container stopped"
        try:
            host_after = assert_no_owners()
        except SmokeError as exc:
            result["host_process_error"] = str(exc)
        release_locks(handles)

    if result.get("launcher_exit_code") is not None:
        log_path = Path(plan["run_path"]) / "slicer.log"
        log_text = log_path.read_text(errors="replace") if log_path.is_file() else ""
        video = Path(plan["run_path"]) / "video/smoke.mkv"
        try:
            info = inspect_container()
            if info.get("Running"):
                container_after = assert_no_owners(container=True)
            elif not container_after:
                container_after = {name: 1 for name in PROCESS_NAMES}
        except SmokeError:
            container_after = {name: 1 for name in PROCESS_NAMES}
        decode_code = 127
        if video.is_file() and shutil.which("ffmpeg"):
            decode_code = command(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], timeout=60)[0]
        checked = (evidence_fn or evidence_checks)(plan, result["launcher_exit_code"], log_text, cleanup_ok,
                                                   host_after or {name: 1 for name in PROCESS_NAMES},
                                                   container_after or {name: 1 for name in PROCESS_NAMES}, decode_code, video)
        result.update(checked)
        result["process_counts"] = {**result.get("process_counts", {}), "host_after": host_after}
        if result.get("error") or result.get("cleanup_error") or result.get("host_process_error"):
            result["runtime_verified"] = False
    result["cleanup_confirmed"] = cleanup_ok
    try:
        (Path(plan["run_path"]) / "runtime-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    except OSError:
        result["runtime_verified"] = False
        result["error"] = "could not write runtime-result.json"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = prepare(args.repo, args.expected_sha, args.image_id)
        if args.run:
            result = execute(plan)
            print(json.dumps(result, sort_keys=True))
            return 0 if result.get("runtime_verified") else 2
        print(json.dumps({"plan": plan, "runtime_verified": False}, sort_keys=True))
        return 0
    except SmokeError as exc:
        print(json.dumps({"runtime_verified": False, "error": str(exc)}, sort_keys=True))
        return 2
    except OSError:
        print(json.dumps({"runtime_verified": False, "error": "could not prepare smoke artifacts"}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
