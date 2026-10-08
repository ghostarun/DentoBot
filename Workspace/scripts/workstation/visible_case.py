#!/usr/bin/env python3
"""Visible case-open runs (PLAT-U-07 Goal 2): B supervises a detached run, A requests and collects.

`visible-case run` and `status` act on the host that runs them (B in practice). `request`
and `collect` run on A and reach B through handoff.Machine. Every run directory is closed
by DONE.json, written last, so a dropped SSH session cannot lose the terminal verdict.
"""

from __future__ import annotations

import argparse
import getpass
import glob
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import handoff
import runtime_preflight
import runtime_sync
import smoke_runtime


TASK = "PLAT-U-07-B-visible-case"
SCHEMA_REQUEST = "dentobot.visible-case.request.v1"
SCHEMA_DONE = "dentobot.visible-case.done.v1"
SCHEMA_COLLECTED = "dentobot.visible-case.collected.v1"
SUBDIRS = ("input", "tmp", "video", "ros-log", "watchdog")
RUNNING_STATES = ("accepted", "preparing", "running", "finalizing")
MODEL_CACHE = "/workspace/data/model-cache/totalsegmentator"
COMMON_FILES = ("DENTOWorkflow/DENTOWorkflow.py", *smoke_runtime.MODULES.values())
XVFB_EXEC = 'exec xvfb-run -a -s "-screen 0 1280x800x24 -nolisten tcp" bash -c \''
SCOPE = "visible B GNOME :0 case open + screenshots; no MoveIt, motion or rebuild"
EVIDENCE_NOTE = ("ffmpeg x11grab of rootless Xwayland :0 is not visibility evidence; "
                 "screenshots are Slicer window grabs")
MAX_MISSES = 5
RUN_PATH_RE = re.compile(
    r"/[A-Za-z0-9._/-]+/data/dentobot-runs/(\d{4}-\d{2}-\d{2}/" + TASK + r"-(\d{8}T\d{6}Z))")


class VisibleCaseError(RuntimeError):
    """A refusal or failure whose message is safe to show (exit 2)."""


class TransportError(RuntimeError):
    """B did not answer over SSH, or the transfer failed (exit 3)."""


class NotFinal(RuntimeError):
    """The run is not final yet, or was interrupted; collect later (exit 3)."""

    def __init__(self, message, payload):
        super().__init__(message)
        self.payload = payload


# --- validation -------------------------------------------------------------

def validate_run_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", value):
        raise VisibleCaseError("run id must look like 20261008T122000Z")
    try:
        datetime.strptime(value, "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise VisibleCaseError("run id is not a valid UTC timestamp") from exc
    return value


def validate_sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise VisibleCaseError("sha must be 40 lowercase hexadecimal characters")
    return value


def validate_hold(value):
    if not isinstance(value, int) or isinstance(value, bool) or not 10 <= value <= 300:
        raise VisibleCaseError("hold must be an integer from 10 to 300 seconds")
    return value


def validate_case_name(value):
    if not isinstance(value, str) or not value or "\\" in value or any(ord(c) < 32 for c in value):
        raise VisibleCaseError("case must be a data-relative .dentocase path")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts or path.suffix != ".dentocase":
        raise VisibleCaseError("case must be a relative .dentocase path under workspace/data without ..")
    return path.as_posix()


def validate_requested_by(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 120 or any(ord(c) < 32 for c in value):
        raise VisibleCaseError("requested-by must be short printable text")
    return value


def safe_relative(value):
    """A manifest path: plain relative POSIX path that never names input/."""
    if not isinstance(value, str) or not value or "\\" in value or any(ord(c) < 32 for c in value):
        raise VisibleCaseError("manifest path is malformed")
    path = PurePosixPath(value)
    if (path.is_absolute() or ".." in path.parts or not path.parts or path.as_posix() != value
            or path.parts[0] == "input"):
        raise VisibleCaseError("manifest path must be a plain relative path outside input/")
    return value


# --- paths ------------------------------------------------------------------

def workspace_for(repo):
    """Workspace root for <ws>/ros2_ws/src/<name>; anything else is refused."""
    checkout = Path(repo).expanduser().resolve()
    if checkout.parent.name != "src" or checkout.parent.parent.name != "ros2_ws" or len(checkout.parts) < 5:
        raise VisibleCaseError("selected checkout must be <workspace>/ros2_ws/src/<name>")
    return checkout.parents[2]


def run_dir_for(workspace, run_id):
    day = f"{run_id[0:4]}-{run_id[4:6]}-{run_id[6:8]}"
    return Path(workspace) / "data" / "dentobot-runs" / day / f"{TASK}-{run_id}"


def resolve_case(workspace, relative):
    """Resolve a data-relative case; symlinks may not leave workspace/data."""
    name = validate_case_name(relative)
    data = Path(workspace) / "data"
    try:
        real_data = data.resolve(strict=True)
        case = (data / name).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise VisibleCaseError("case file does not exist under workspace/data") from exc
    try:
        case.relative_to(real_data)
    except ValueError as exc:
        raise VisibleCaseError("case path escapes workspace/data") from exc
    if not case.is_file() or case.suffix != ".dentocase":
        raise VisibleCaseError("case must be a regular .dentocase file")
    return case


def run_id_from_dir(run_dir):
    name = Path(run_dir).name
    prefix = TASK + "-"
    if not name.startswith(prefix):
        raise VisibleCaseError("run directory name does not match the visible-case task")
    return validate_run_id(name[len(prefix):])


def run_relative(run_path, run_id):
    """Path below data/dentobot-runs for a B-reported run; anything else is refused."""
    match = RUN_PATH_RE.fullmatch(run_path) if isinstance(run_path, str) else None
    if not match or match.group(2) != run_id:
        raise VisibleCaseError("B reported an unexpected run path")
    return match.group(1)


# --- files, hashes and atomic JSON ------------------------------------------

def utc_now():
    return datetime.now(timezone.utc)


def utc_text(moment=None):
    return (moment or utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id(moment=None):
    return (moment or utc_now()).strftime("%Y%m%dT%H%M%SZ")


def write_text_atomic(path, text):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def write_json_atomic(path, data):
    write_text_atomic(path, json.dumps(data, indent=2, sort_keys=True, default=str) + "\n")


def read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def own_prefix_for(run_id):
    """Container-visible path of one run's evidence tree (what the Slicer container sees)."""
    return f"/workspace/data/dentobot-runs/{run_id[0:4]}-{run_id[4:6]}-{run_id[6:8]}/{TASK}-{run_id}"


def own_symlink(target, own_prefix):
    """A link that can only point into the run's own evidence tree (ROS logging's ros-log/latest): relative
    without .., or absolute under this run's container path. It is recorded, never followed or hashed."""
    if not isinstance(target, str) or not target or "\\" in target or any(ord(c) < 32 for c in target):
        return False
    path = PurePosixPath(target)
    if ".." in path.parts:
        return False
    if not path.is_absolute():
        return True
    return bool(own_prefix) and (path.as_posix() == own_prefix or path.as_posix().startswith(own_prefix + "/"))


def list_run_files(root, exclude_names=("DONE.json", "COLLECTED.json"), own_prefix=None, links=None):
    """Regular files under root (top-level input/ skipped) and any other entries found.

    Symlinks that only point into the run's own tree are appended to `links` as (path, target) and are
    not anomalies; every other non-regular entry (foreign symlink, socket, FIFO, device) is an anomaly."""
    root = Path(root)
    files, anomalies = [], []

    def note_link(path, relative):
        target = os.readlink(path)
        if own_symlink(target, own_prefix):
            if links is not None:
                links.append((relative, target))
        else:
            anomalies.append(relative)

    for current, dirs, names in os.walk(root):
        here = Path(current)
        if here == root:
            dirs[:] = [name for name in dirs if name != "input"]
        for name in dirs:
            if (here / name).is_symlink():
                note_link(here / name, (here / name).relative_to(root).as_posix())
        for name in names:
            path = here / name
            relative = path.relative_to(root).as_posix()
            if here == root and name in exclude_names:
                continue
            mode = os.lstat(path).st_mode
            if stat.S_ISLNK(mode):
                note_link(path, relative)
                continue
            if not stat.S_ISREG(mode):
                anomalies.append(relative)
                continue
            files.append(relative)
    return sorted(files), sorted(anomalies)


def file_entry(root, relative):
    path = Path(root) / relative
    return {"path": relative, "sha256": sha256_file(path), "size": path.stat().st_size}


def verify_manifest(root, entries):
    """Every listed file must exist as a regular file with the recorded size and SHA-256."""
    if not isinstance(entries, list):
        raise VisibleCaseError("manifest is not a list")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise VisibleCaseError("manifest entry is malformed")
        relative = safe_relative(entry.get("path"))
        digest, size = entry.get("sha256"), entry.get("size")
        if (relative in seen or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or not isinstance(size, int) or isinstance(size, bool)):
            raise VisibleCaseError("manifest entry is malformed")
        seen.add(relative)
        path = Path(root) / relative
        try:
            info = os.lstat(path)
        except OSError as exc:
            raise VisibleCaseError(f"manifest file is missing: {relative}") from exc
        if not stat.S_ISREG(info.st_mode) or info.st_size != size or sha256_file(path) != digest:
            raise VisibleCaseError(f"manifest verification failed for {relative}")
    return entries


def file_hashes(root, relatives):
    hashes = {}
    for relative in relatives:
        path = Path(root) / relative
        if not path.is_file():
            raise VisibleCaseError(f"loaded source file is missing from the pinned worktree: {relative}")
        hashes[relative] = sha256_file(path)
    return hashes


# --- run state and supervisor identity --------------------------------------

def set_state(run_dir, state):
    write_json_atomic(Path(run_dir) / "STATE.json", {"state": state, "updated_at_utc": utc_text()})


def read_state(run_dir):
    data = read_json(Path(run_dir) / "STATE.json")
    value = data.get("state") if data else None
    return value if value in RUNNING_STATES else None


def boot_id():
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip() or None
    except OSError:
        return None


def process_identity(pid):
    """(state, start_ticks) from /proc/<pid>/stat, or None when the pid is gone."""
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fields = text[text.rfind(")") + 2:].split()
    try:
        return fields[0], int(fields[19])
    except (IndexError, ValueError):
        return None


def write_supervisor(run_dir, pid):
    identity = process_identity(pid)
    current_boot = boot_id()
    if identity is None or current_boot is None:
        raise VisibleCaseError("supervisor process identity is unavailable")
    write_json_atomic(Path(run_dir) / "supervisor.json",
                      {"pid": pid, "start_ticks": identity[1], "boot_id": current_boot})


def supervisor_alive(run_dir):
    record = read_json(Path(run_dir) / "supervisor.json")
    if not record:
        return False
    pid, start, recorded_boot = record.get("pid"), record.get("start_ticks"), record.get("boot_id")
    if not (isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 and isinstance(start, int)):
        return False
    current = boot_id()
    if current is None or recorded_boot != current:
        return False
    identity = process_identity(pid)
    return identity is not None and identity[0] != "Z" and identity[1] == start


def status(workspace, run_id):
    """Read-only state of one run on this host."""
    run_id = validate_run_id(run_id)
    run_dir = run_dir_for(workspace, run_id)
    done = (run_dir / "DONE.json").is_file()
    final = None
    if done:
        marker = read_json(run_dir / "DONE.json")
        final = marker.get("status") if marker else None
    alive = supervisor_alive(run_dir)
    if not run_dir.is_dir():
        state = "unknown"
    elif done:
        state = "done"
    elif alive:
        state = read_state(run_dir) or "unknown"
    elif read_state(run_dir) == "accepted" and not (run_dir / "supervisor.json").exists():
        state = "accepted"
    else:
        state = "incomplete"
    return {"run_id": run_id, "run_path": str(run_dir), "state": state, "done": done,
            "status": final, "supervisor_alive": alive}


def read_request(run_dir):
    request = read_json(Path(run_dir) / "request.json")
    if not request or request.get("schema") != SCHEMA_REQUEST:
        raise VisibleCaseError("request.json is missing or is not a visible-case request")
    validate_run_id(request.get("run_id"))
    validate_sha(request.get("sha"))
    validate_case_name(request.get("case"))
    validate_hold(request.get("hold_s"))
    return request


# --- B side: run and supervise ----------------------------------------------

def _spawn_supervisor(argv, log_path):
    """Detached supervisor: its own session, so an SSH drop cannot signal it."""
    with open(log_path, "ab") as log:
        return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, close_fds=True)


def start_run(*, selected_repo, worktree_root, case, sha, run_id, hold, requested_by="unknown",
              detach=False, spawn=None, moment=None):
    """Validate, create the run directory once (never overwrite), then supervise or detach."""
    validate_run_id(run_id)
    validate_sha(sha)
    validate_hold(hold)
    case_rel = validate_case_name(case)
    requested_by = validate_requested_by(requested_by)
    if not worktree_root:
        raise VisibleCaseError("B worktree_root is not configured")
    if not Path(selected_repo).is_dir():
        raise VisibleCaseError("selected checkout is missing on this host")
    workspace = workspace_for(selected_repo)
    resolve_case(workspace, case_rel)
    run_dir = run_dir_for(workspace, run_id)
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise VisibleCaseError(f"run directory already exists for {run_id}; refusing to overwrite") from exc
    for name in SUBDIRS:
        (run_dir / name).mkdir()
    write_json_atomic(run_dir / "request.json", {
        "schema": SCHEMA_REQUEST, "run_id": run_id, "sha": sha, "case": case_rel, "hold_s": hold,
        "requested_by": requested_by, "host": socket.gethostname(), "requested_at_utc": utc_text(moment),
    })
    set_state(run_dir, "accepted")
    if not detach:
        supervise(run_dir, repo=selected_repo, worktree_root=worktree_root)
        return status(workspace, run_id)
    argv = [sys.executable, str(Path(__file__).resolve()), "supervise", "--run-dir", str(run_dir),
            "--repo", str(selected_repo), "--worktree-root", str(worktree_root)]
    try:
        process = (spawn or _spawn_supervisor)(argv, run_dir / "supervisor.log")
    except OSError as exc:
        finalize(run_dir, run_id=run_id, sha=sha, status="ERROR", error="supervisor could not be started",
                 requested_by=requested_by, host=socket.gethostname(), case_name=case_rel)
        raise VisibleCaseError("supervisor could not be started; run closed as ERROR") from exc
    try:
        write_supervisor(run_dir, process.pid)
    except VisibleCaseError:
        pass  # the supervisor records its own identity at startup, so this write is not load-bearing
    return {"run_id": run_id, "run_path": str(run_dir), "state": "accepted"}


def prepare_source(selected_repo, sha, worktree_root, *, git=None, is_clean=None):
    """Create or reuse a detached worktree at an origin-published sha; never reset or clean."""
    git = git or git_text
    is_clean = is_clean or smoke_runtime.source_is_clean
    validate_sha(sha)
    git(selected_repo, "fetch", "--quiet", "origin")
    git(selected_repo, "cat-file", "-e", f"{sha}^{{commit}}")
    contained = git(selected_repo, "branch", "-r", "--contains", sha)
    if not any(line.strip().startswith("origin/") for line in contained.splitlines()):
        raise VisibleCaseError(f"sha {sha[:12]} is not published on origin; push it before requesting B")
    target = Path(worktree_root) / f"DentoBot-visible-{sha[:12]}"
    if target.is_symlink():
        raise VisibleCaseError(f"{target.name} is a symlink; refusing to use it")
    if target.exists():
        if not is_clean(target, sha):
            raise VisibleCaseError(f"existing {target.name} is not a clean checkout at {sha[:12]}; not touched")
        return target
    git(selected_repo, "worktree", "add", "--detach", str(target), sha)
    return target


def read_runtime_lock(worktree):
    lock = read_json(Path(worktree) / "Workspace" / "runtime-lock.json") or {}
    image_id, image_name = lock.get("image_id"), lock.get("image_name")
    if (not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", image_id)
            or not isinstance(image_name, str) or not image_name):
        raise VisibleCaseError("pinned worktree needs a runtime lock with image_id and image_name")
    return {"image_id": image_id.lower(), "image_name": image_name}


def read_workspace_config(workspace):
    values, errors = runtime_preflight.parse_env_file(Path(workspace) / ".dentobot.env")
    if errors:
        raise VisibleCaseError("workspace .dentobot.env is missing or uses unsupported syntax")
    config, _ = runtime_preflight.effective_config(values, {})
    if not os.path.isabs(config.get("DENTOBOT_BACKEND_PYTHON", "")):
        raise VisibleCaseError("DENTOBOT_BACKEND_PYTHON must be an absolute path")
    return config


def build_plan(*, workspace, worktree, run_dir, sha, hold, case_name, lock, config, hashes,
               bootstrap_template, model_cache=MODEL_CACHE):
    """Pure plan construction (no Docker, no filesystem writes) from injected inputs."""
    validate_hold(hold)
    workspace, worktree, run_dir = Path(workspace), Path(worktree), Path(run_dir)
    backend = config.get("DENTOBOT_BACKEND_PYTHON", "")
    if not os.path.isabs(backend):
        raise VisibleCaseError("DENTOBOT_BACKEND_PYTHON must be an absolute path")
    try:
        relative_run = run_dir.relative_to(workspace / "data" / "dentobot-runs").as_posix()
    except ValueError as exc:
        raise VisibleCaseError("run directory is outside data/dentobot-runs") from exc
    container_repo = f"/workspace/ros2_ws/src/{worktree.name}"
    container_evidence = f"/workspace/data/dentobot-runs/{relative_run}"
    payload = {"repo": container_repo, "evidence": container_evidence,
               "case": f"{container_evidence}/input/{case_name}", "hold_s": hold,
               "common_files": list(COMMON_FILES), "hashes": dict(hashes)}
    bootstrap = "PLAN = " + repr(payload) + "\n" + bootstrap_template
    argv = smoke_runtime.make_command(container_repo, container_evidence, config, model_cache)
    script = argv[-1]
    if script.count(XVFB_EXEC) != 1:
        raise VisibleCaseError("runtime launcher text changed; visible plan refused")
    argv[-1] = script.replace(XVFB_EXEC, "export DISPLAY=:0\nexec bash -c '")
    argv[2:2] = ["-e", "DISPLAY=:0", "-e", f"TMPDIR={container_evidence}/tmp"]
    plan = {"repo": str(worktree), "workspace": str(workspace), "expected_sha": sha,
            "image_id": lock["image_id"], "image_name": lock["image_name"],
            "backend_env_dir": str(Path(backend).parent.parent.resolve()), "run_path": str(run_dir),
            "argv": argv, "timeout_sec": hold + 600, "scope": SCOPE}
    return plan, bootstrap


def copy_case(source, input_dir):
    """Copy the case into the run and prove the copy matches the source, before and after."""
    Path(input_dir).mkdir(exist_ok=True)
    before = sha256_file(source)
    target = Path(input_dir) / source.name
    shutil.copyfile(source, target)
    copied = sha256_file(target)
    if copied != before or sha256_file(source) != before:
        raise VisibleCaseError("case changed while it was copied; refusing to run")
    return target, copied


def kept_screenshots(run_dir, case_result):
    listed = case_result.get("screenshots")
    names = [name for name in listed if isinstance(name, str)] if isinstance(listed, list) else []
    kept = []
    for name in names:
        path = Path(run_dir) / "screenshots" / name
        if Path(name).name == name and path.is_file() and path.stat().st_size > 0:
            kept.append((name, sha256_file(path)))
    return names, kept


FRAMING_STATUSES = ("production", "fallback", "unavailable")


def framing_summary(case_result):
    """Per-layout target-framing status from case-result.json.

    Only "production" on BOTH layouts counts as framed; a fallback camera reset or an
    unavailable planning target is reported as such and never as successful framing.
    """
    result = case_result if isinstance(case_result, dict) else {}
    summary = {}
    for label, key in (("four_up", "framing"), ("one_up_3d", "framing_3d_only")):
        item = result.get(key) if isinstance(result.get(key), dict) else {}
        status = item.get("status") if item.get("status") in FRAMING_STATUSES else "not_run"
        summary[label] = {"status": status, "method": item.get("method"),
                          "reason": str(item.get("reason") or "")[:200]}
    summary["framed"] = all(summary[label]["status"] == "production" for label in ("four_up", "one_up_3d"))
    return summary


def _sha_if_file(path):
    return sha256_file(path) if Path(path).is_file() else None


def make_evidence(*, case_copy, case_sha256, parity_passed, xhost_state, base=None):
    """Evidence for the visible case, layered on smoke_runtime.evidence_checks.

    xhost_state["revoked"] is False while the run is still executing; supervise()
    records the real revoke result afterwards and recomputes the verdict.
    """
    def evidence(plan, launcher_code, log_text, cleanup_ok, host_after, container_after, decode_code, video):
        report = (base or smoke_runtime.evidence_checks)(
            plan, launcher_code, log_text, cleanup_ok, host_after, container_after, decode_code, video)
        checks = report["checks"]
        for name in ("five_reload_rows_six_assertions", "success_markers", "video_manifest_checksum_and_decode"):
            checks.pop(name, None)
        report.pop("reload_reports", None)
        run_dir = Path(plan["run_path"])
        case_result = read_json(run_dir / "case-result.json") or {}
        names, kept = kept_screenshots(run_dir, case_result)
        checks["case_opened"] = case_result.get("case_loaded") is True
        checks["visible_case_marker"] = "DENTOBOT_VISIBLE_CASE_PASS" in log_text
        checks["screenshots_distinct"] = (len(names) >= 3 and len(kept) == len(names)
                                          and len({digest for _, digest in kept}) == len(kept))
        checks["case_input_unchanged"] = _sha_if_file(case_copy) == case_sha256
        checks["target_framing"] = framing_summary(case_result)["framed"]
        checks["xhost_revoked"] = bool(xhost_state.get("revoked"))
        checks["parity_passed"] = bool(parity_passed)
        report["case_result"] = case_result
        report["runtime_verified"] = all(checks.values())
        report["evidence_note"] = EVIDENCE_NOTE
        return report
    return evidence


def x_environment():
    env = dict(os.environ, DISPLAY=":0")
    auth = sorted(glob.glob(f"/run/user/{os.getuid()}/.mutter-Xwaylandauth.*"))
    if auth:
        env["XAUTHORITY"] = auth[-1]
    return env


def x_user():
    user = getpass.getuser()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", user):
        raise VisibleCaseError("local user name cannot be granted X access safely")
    return user


def run_xhost(args, env):
    try:
        completed = subprocess.run(["xhost", *args], env=env, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _attempt(xhost, args, env):
    try:
        return bool(xhost(args, env))
    except Exception:
        return False


def _verdict(execution, revoked):
    checks = dict(execution.get("checks") or {})
    checks["xhost_revoked"] = bool(revoked)
    cleanup_problem = execution.get("cleanup_error") or execution.get("host_process_error")
    if execution.get("error"):
        return {"status": "ERROR", "error": str(execution["error"]), "checks": checks,
                "timed_out": bool(execution.get("timed_out"))}
    verified = "checks" in execution and all(checks.values()) and not cleanup_problem
    if verified:
        error = None
    elif cleanup_problem:
        error = str(cleanup_problem)
    elif not revoked:
        error = "scoped X grant was not revoked"
    else:
        error = None
    return {"status": "PASS" if verified else "FAIL", "error": error, "checks": checks,
            "timed_out": bool(execution.get("timed_out"))}


def _describe(exc):
    if isinstance(exc, (VisibleCaseError, smoke_runtime.SmokeError, OSError)):
        return (str(exc) or type(exc).__name__)[:300]
    if isinstance(exc, KeyboardInterrupt):
        return "supervisor was interrupted"
    if isinstance(exc, SystemExit):
        return "supervisor was terminated"
    return f"unexpected {type(exc).__name__} in supervisor"


def _terminate(signum, frame):
    raise SystemExit(128 + signum)


def supervise(run_dir, *, repo, worktree_root, prepare=None, parity=None, execute=None, xhost=None):
    """Prepare the pinned worktree, run the visible case, then always publish DONE.json last."""
    prepare = prepare or prepare_source
    parity = parity or runtime_sync.parity
    execute = execute or smoke_runtime.execute
    xhost = xhost or run_xhost
    run_dir = Path(run_dir)
    started = utc_text()
    run_id = run_id_from_dir(run_dir)
    if (run_dir / "DONE.json").exists():
        raise VisibleCaseError("run already has DONE.json; a finished run is never supervised again")
    context = {"sha": None, "case": None, "case_sha256": None, "requested_by": "unknown",
               "repo_name": "", "host": socket.gethostname()}
    outcome = {"status": "ERROR", "error": None, "checks": {}, "timed_out": False,
               "cleanup": {}, "result": {}}
    interrupted = None
    previous = signal.signal(signal.SIGTERM, _terminate)
    try:
        write_supervisor(run_dir, os.getpid())
        req = read_request(run_dir)
        if req["run_id"] != run_id:
            raise VisibleCaseError("request.json run id differs from the run directory")
        context.update(sha=req["sha"], case=req["case"], requested_by=req.get("requested_by", "unknown"))
        workspace = workspace_for(repo)
        if run_dir_for(workspace, run_id).resolve() != run_dir.resolve():
            raise VisibleCaseError("run directory is outside this workspace's run tree")
        set_state(run_dir, "preparing")
        worktree = Path(prepare(repo, req["sha"], worktree_root))
        parity_report = parity(str(worktree))
        write_json_atomic(run_dir / "parity.json", parity_report)
        if not isinstance(parity_report, dict) or parity_report.get("passed") is not True:
            raise VisibleCaseError("runtime parity did not pass for the pinned worktree")
        case_copy, case_sha = copy_case(resolve_case(workspace, req["case"]), run_dir / "input")
        context.update(case_sha256=case_sha, repo_name=worktree.name)
        plan, bootstrap = build_plan(
            workspace=workspace.resolve(), worktree=worktree, run_dir=run_dir.resolve(), sha=req["sha"],
            hold=req["hold_s"], case_name=case_copy.name, lock=read_runtime_lock(worktree),
            config=read_workspace_config(workspace), hashes=file_hashes(worktree, COMMON_FILES),
            bootstrap_template=Path(__file__).resolve().with_name("visible_case_bootstrap.py")
            .read_text(encoding="utf-8"))
        (run_dir / "bootstrap.py").write_text(bootstrap, encoding="utf-8")
        write_json_atomic(run_dir / "runtime-command.json", plan)
        set_state(run_dir, "running")
        user = x_user()
        env = x_environment()
        if not xhost(["+SI:localuser:" + user], env):
            raise VisibleCaseError("scoped X grant was refused; the case was not opened")
        grant = {"revoked": False}
        evidence = make_evidence(case_copy=case_copy, case_sha256=case_sha, parity_passed=True,
                                 xhost_state=grant)
        try:
            execution = execute(plan, evidence_fn=evidence)
        finally:
            grant["revoked"] = _attempt(xhost, ["-SI:localuser:" + user], env)
            outcome["cleanup"]["xhost_revoked"] = grant["revoked"]
        outcome.update(_verdict(execution, grant["revoked"]))
        outcome["result"] = {**execution, "runtime_verified": outcome["status"] == "PASS"}
    except Exception as exc:
        outcome.update(status="ERROR", error=_describe(exc))
        if not isinstance(exc, (VisibleCaseError, smoke_runtime.SmokeError, OSError)):
            traceback.print_exc()
    except BaseException as exc:
        outcome.update(status="ERROR", error=_describe(exc))
        interrupted = exc
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)  # a late TERM must not cut the verdict short
        try:
            done = finalize(run_dir, run_id=run_id, sha=context["sha"], case_sha256=context["case_sha256"],
                            status=outcome["status"], error=outcome["error"], checks=outcome["checks"],
                            timed_out=outcome["timed_out"], started_at=started, cleanup=outcome["cleanup"],
                            result=outcome["result"], requested_by=context["requested_by"],
                            host=context["host"], case_name=context["case"] or "",
                            repo_name=context["repo_name"])
        finally:
            signal.signal(signal.SIGTERM, previous if previous is not None else signal.SIG_DFL)
    if interrupted is not None:
        raise interrupted
    return done


def _screenshot_names(run_dir):
    listed = (read_json(Path(run_dir) / "case-result.json") or {}).get("screenshots")
    return [name for name in listed if isinstance(name, str)] if isinstance(listed, list) else []


def framing_line(framing):
    if framing["framed"]:
        return "- Framing: production target-framing action on both layouts (still subject to the operator's visual verdict)"
    parts = [f"{label}: {framing[label]['status']}" + (f" ({framing[label]['reason']})" if framing[label]["reason"] else "")
             for label in ("four_up", "one_up_3d")]
    return ("- Framing: NOT DEMONSTRATED — " + "; ".join(parts)
            + ". A fallback camera reset or missing planning target is not target framing; operator verdict needed.")


def run_log_text(*, run_id, requested_by, host, repo_name, sha, case_name, case_sha256, status, error,
                 checks, shots, framing):
    if status == "PASS":
        verdict = f"**PASS**: verified at {sha}"
    else:
        verdict = f"**{status}**: tested at {sha}: {status}"
    checks_line = ", ".join(f"{name}={'ok' if ok else 'FAIL'}" for name, ok in sorted(checks.items())) or "none"
    lines = [
        f"# B visible case run {run_id}", "",
        f"- Requested by: {requested_by}",
        f"- Host: {host} (GNOME :0, visible)",
        f"- Source: `{repo_name}` @ `{sha}`",
        f"- Case: `{case_name}` sha256 `{(case_sha256 or 'none')[:16]}…`",
        f"- Result: {verdict}",
        f"- Checks: {checks_line}",
        framing_line(framing),
        "- Screenshots: " + (", ".join(f"`screenshots/{name}`" for name in shots) or "none"),
        "- Session log: `session-log.json`; Slicer log: `slicer.log`",
        "- Boundary: offline case open only; no MoveIt, motion, rebuild. Video is not visibility evidence (Xwayland).",
    ]
    if error:
        lines.append(f"- Error: {error}")
    return "\n".join(lines) + "\n"


def finalize(run_dir, *, run_id, sha, status, case_sha256=None, error=None, checks=None, timed_out=False,
             started_at=None, cleanup=None, result=None, requested_by="unknown", host=None, case_name="",
             repo_name=""):
    """Write result and log, build the manifest, then publish DONE.json last."""
    run_dir = Path(run_dir)
    own_prefix = own_prefix_for(run_id)
    _, anomalies = list_run_files(run_dir, own_prefix=own_prefix)
    if anomalies:
        status = "ERROR"
        error = (error or "run directory has unexpected entries: " + ", ".join(anomalies[:5]))[:300]
    checks = dict(checks or {})
    framing = framing_summary(read_json(run_dir / "case-result.json"))
    set_state(run_dir, "finalizing")
    write_json_atomic(run_dir / "result.json", {
        **(result or {}), "run_id": run_id, "status": status, "error": error, "sha": sha, "framing": framing,
        "verified_at_sha": sha if status == "PASS" else None, "case_sha256": case_sha256,
        "checks": checks, "cleanup": cleanup or {}, "timed_out": bool(timed_out),
    })
    write_text_atomic(run_dir / "RUN_LOG.md", run_log_text(
        run_id=run_id, requested_by=requested_by, host=host or socket.gethostname(), repo_name=repo_name,
        sha=sha, case_name=case_name, case_sha256=case_sha256, status=status, error=error, checks=checks,
        shots=_screenshot_names(run_dir), framing=framing))
    links = []
    files, _ = list_run_files(run_dir, own_prefix=own_prefix, links=links)
    finished = utc_text()
    done = {
        "schema": SCHEMA_DONE, "run_id": run_id, "status": status, "sha": sha,
        "verified_at_sha": sha if status == "PASS" else None, "case_sha256": case_sha256,
        "checks": checks, "framing": framing, "error": error, "timed_out": bool(timed_out),
        "symlinks_not_followed": [{"path": path, "target": target} for path, target in sorted(links)],
        "started_at_utc": started_at or finished, "finished_at_utc": finished,
        "files": [file_entry(run_dir, relative) for relative in files], "cleanup": cleanup or {},
    }
    write_json_atomic(run_dir / "DONE.json", done)
    return done


# --- status and request/collect helpers --------------------------------------

def git_text(repo, *args, timeout=600):
    argv = ["env", "GIT_TERMINAL_PROMPT=0", "git", "-C", str(repo), *args]
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VisibleCaseError(f"git {args[0]} could not complete") from exc
    if completed.returncode:
        raise VisibleCaseError(f"git {args[0]} failed (exit {completed.returncode})")
    return completed.stdout


class Remote:
    """B-side protocol over handoff.Machine; Machine.run shell-quotes every argv item."""

    def __init__(self, machine):
        if machine.host is None:
            raise VisibleCaseError("B must be a remote host for request and collect")
        self.machine = machine

    @property
    def host(self):
        return self.machine.host

    def call(self, args, timeout=60):
        argv = ["sh", "-c", 'exec "$HOME/.local/bin/dentobot" "$@"', "sh", "visible-case", *args]
        try:
            output = self.machine.run(argv, timeout=timeout, allowed_returncodes=(0, 2))
        except RuntimeError as exc:
            message = str(exc)
            if "timed out" in message or "Tailscale" in message:
                message += (f"; if `ssh {self.host} true` prints a Tailscale SSH check link, "
                            "Tarun must approve it in a browser before A can reach B")
            raise TransportError(message) from exc
        payload = last_json_object(output)
        if payload is None:
            raise VisibleCaseError("B returned no visible-case answer; is the command deployed?")
        return payload


def last_json_object(text):
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except ValueError:
            return None
        return value if isinstance(value, dict) else None
    return None


def rsync_pull(host, run_path, dest):
    """Copy the run directory from B, excluding input/ (the case copy stays on B)."""
    if not host:
        raise VisibleCaseError("B host is required for transfer")
    ssh = shlex.join(["ssh", *handoff.SSH_OPTIONS])
    argv = ["rsync", "-a", "--exclude", "input/", "-e", ssh, f"{host}:{run_path}/", f"{dest}/"]
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=1800, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TransportError("transfer from B did not complete") from exc
    if completed.returncode:
        raise TransportError(f"transfer from B failed (rsync exit {completed.returncode})")


def flush_print(message):
    """Progress lines must reach a redirected output file at once (background jobs are read while they run)."""
    print(message, flush=True)


def collect_hint(run_id):
    return f"dentobot visible-case collect --run-id {run_id}"


def _preflight_source(*, repo, sha, cwd, git):
    """All A-side checks that must pass before any SSH call."""
    if repo is None:
        checkout = Path(git(cwd, "rev-parse", "--show-toplevel").strip())
    else:
        checkout = Path(repo).expanduser().resolve()
    if not checkout.is_dir():
        raise VisibleCaseError("selected checkout is not a directory")
    if git(checkout, "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=none").strip():
        raise VisibleCaseError("A selected checkout is dirty; commit and push before requesting B")
    if sha is None:
        sha = git(checkout, "rev-parse", "HEAD").strip()
    validate_sha(sha)
    git(checkout, "fetch", "--quiet", "origin")
    git(checkout, "cat-file", "-e", f"{sha}^{{commit}}")
    contained = git(checkout, "branch", "-r", "--contains", sha)
    if not any(line.strip().startswith("origin/") for line in contained.splitlines()):
        raise VisibleCaseError(f"A HEAD {sha} is not on origin; push it first")
    return checkout, sha


def request(*, case, sha=None, repo=None, hold=90, no_wait=False, poll_interval=20, max_wait=1800,
            remote, local_workspace, cwd, git=None, transfer=None, sleep=None, clock=None,
            run_id=None, requested_by="A", log=None):
    """Preflight on A, start one detached B run, poll its state, then collect the evidence."""
    git = git or git_text
    transfer = transfer or rsync_pull
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    log = log or flush_print
    case_rel = validate_case_name(case)
    hold = validate_hold(hold)
    if sha is not None:
        validate_sha(sha)
    if repo is not None and sha is not None:
        raise VisibleCaseError("use either --sha or --repo, not both")
    if not isinstance(poll_interval, int) or not 1 <= poll_interval <= 3600:
        raise VisibleCaseError("poll interval must be 1 to 3600 seconds")
    if not isinstance(max_wait, int) or not 1 <= max_wait <= 86400:
        raise VisibleCaseError("max wait must be 1 to 86400 seconds")
    workspace_for(local_workspace)
    checkout, sha = _preflight_source(repo=repo, sha=sha, cwd=cwd, git=git)
    run_id = validate_run_id(run_id) if run_id else new_run_id()
    log(f"A preflight passed: {sha} is published on origin ({checkout.name})")
    answer = None
    try:
        answer = remote.call(["run", "--case", case_rel, "--sha", sha, "--run-id", run_id,
                              "--hold", str(hold), "--requested-by", validate_requested_by(requested_by),
                              "--detach"], timeout=120)
    except TransportError as exc:
        log(f"B did not answer the run request ({exc}); polling run {run_id} instead")
    if answer is not None:
        if answer.get("error"):
            raise VisibleCaseError(str(answer["error"]))
        if answer.get("run_id") != run_id:
            raise VisibleCaseError("B answered for a different run id")
        log(f"B accepted run {run_id}")
        if no_wait:
            return 0, {"run_id": run_id, "run_path": answer.get("run_path"), "state": answer.get("state"),
                       "sha": sha, "case": case_rel, "hold_s": hold, "collect_hint": collect_hint(run_id)}, []
    elif no_wait:
        raise NotFinal(f"run {run_id} may have started on B but its answer was lost; check it, then: "
                       f"{collect_hint(run_id)}", {"run_id": run_id, "state": "unknown",
                                                   "done": False, "collect_hint": collect_hint(run_id)})
    deadline = clock() + max_wait
    misses = 0
    while True:
        try:
            state = remote.call(["status", "--run-id", run_id], timeout=60)
        except TransportError as exc:
            misses += 1
            log(f"poll {misses}: B unreachable ({exc})")
        else:
            if state.get("error"):
                raise VisibleCaseError(str(state["error"]))
            misses = misses + 1 if state.get("state") == "unknown" else 0
            log(f"B state: {state.get('state')}")
            if state.get("done"):
                break
            if state.get("state") == "incomplete":
                raise NotFinal(f"run {run_id} is incomplete on B (its supervisor exited without DONE.json); "
                               f"record it with: {collect_hint(run_id)} --accept-incomplete",
                               {"run_id": run_id, "state": "incomplete", "done": False,
                                "collect_hint": collect_hint(run_id)})
        if misses > MAX_MISSES:
            raise NotFinal(f"run {run_id} is not visible on B after {misses} polls; not final. "
                           f"Later: {collect_hint(run_id)}",
                           {"run_id": run_id, "state": "unknown", "done": False,
                            "collect_hint": collect_hint(run_id)})
        if clock() >= deadline:
            raise NotFinal(f"run {run_id} is not final after {max_wait}s. Later: {collect_hint(run_id)}",
                           {"run_id": run_id, "done": False, "collect_hint": collect_hint(run_id)})
        sleep(poll_interval)
    code, payload = collect(run_id=run_id, remote=remote, local_workspace=local_workspace,
                            transfer=transfer)
    return code, payload, []


def collection_label(status_value, sha, verified_at):
    if status_value == "PASS":
        return f"verified at {verified_at}"
    if status_value == "INCOMPLETE":
        return f"INCOMPLETE: no verdict; requested at {sha}"
    return f"tested at {sha}: {status_value}"


def _normalized(entries):
    return [{"path": entry["path"], "sha256": entry["sha256"], "size": entry["size"]} for entry in entries]


def collected_manifest(temp, run_id, *, expect_done):
    """Verify what arrived from B; returns (entries, done_sha, status, sha, verified_at)."""
    temp = Path(temp)
    has_done = (temp / "DONE.json").is_file()
    if expect_done and not has_done:
        raise VisibleCaseError("transfer did not include DONE.json")
    if has_done:
        done = read_json(temp / "DONE.json")
        if (not done or done.get("schema") != SCHEMA_DONE or done.get("run_id") != run_id
                or done.get("status") not in ("PASS", "FAIL", "ERROR")
                or not isinstance(done.get("sha"), str) or not isinstance(done.get("files"), list)):
            raise VisibleCaseError("DONE.json is not a valid visible-case marker")
        verify_manifest(temp, done["files"])
        found, anomalies = list_run_files(temp, exclude_names=("COLLECTED.json",), own_prefix=own_prefix_for(run_id))
        if anomalies:
            raise VisibleCaseError("transfer contains unexpected entries; refusing: " + ", ".join(anomalies[:5]))
        listed = {safe_relative(entry["path"]) for entry in done["files"]} | {"DONE.json"}
        if set(found) != listed:
            raise VisibleCaseError("transfer contents differ from the DONE.json manifest")
        entries = sorted(_normalized(done["files"]) + [file_entry(temp, "DONE.json")],
                         key=lambda entry: entry["path"])
        return entries, sha256_file(temp / "DONE.json"), done["status"], done["sha"], done.get("verified_at_sha")
    request_data = read_json(temp / "request.json")
    if not request_data or request_data.get("run_id") != run_id:
        raise VisibleCaseError("transfer has no request.json for an incomplete run")
    sha = validate_sha(request_data.get("sha"))
    found, anomalies = list_run_files(temp, exclude_names=("COLLECTED.json",), own_prefix=own_prefix_for(run_id))
    if anomalies:
        raise VisibleCaseError("transfer contains unexpected entries; refusing: " + ", ".join(anomalies[:5]))
    return [file_entry(temp, relative) for relative in found], None, "INCOMPLETE", sha, None


def _unique_aside(dest):
    """Sibling name for retaining an earlier INCOMPLETE collection; nothing is ever deleted or overwritten."""
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    candidate = dest.with_name(f"{dest.name}.incomplete-{stamp}")
    counter = 1
    while os.path.lexists(candidate):
        counter += 1
        candidate = dest.with_name(f"{dest.name}.incomplete-{stamp}-{counter}")
    return candidate


def collect(*, run_id, remote, local_workspace, accept_incomplete=False, transfer=None, host_name=None):
    """Copy one final B run into the local data tree, verified and never overwritten."""
    run_id = validate_run_id(run_id)
    transfer = transfer or rsync_pull
    answer = remote.call(["status", "--run-id", run_id], timeout=60)
    if answer.get("error"):
        raise VisibleCaseError(str(answer["error"]))
    state = answer.get("state")
    if not answer.get("done") and not (state == "incomplete" and accept_incomplete):
        raise NotFinal(f"run {run_id} is {state}, not final; later: {collect_hint(run_id)}",
                       {"run_id": run_id, "state": state, "done": False, "collect_hint": collect_hint(run_id)})
    relative = run_relative(answer.get("run_path"), run_id)
    dest = workspace_for(local_workspace) / "data" / "dentobot-runs" / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.parent / f".{dest.name}.collecting-{os.getpid()}"
    try:
        temp.mkdir()
    except FileExistsError as exc:
        raise VisibleCaseError("another collection is already using this destination") from exc
    published = False
    try:
        transfer(remote.host, answer["run_path"], temp)
        entries, done_sha, status_value, sha, verified_at = collected_manifest(
            temp, run_id, expect_done=bool(answer.get("done")))
        label = collection_label(status_value, sha, verified_at)
        write_json_atomic(temp / "COLLECTED.json", {
            "schema": SCHEMA_COLLECTED, "run_id": run_id, "status": status_value, "label": label,
            "sha": sha, "verified_at_sha": verified_at, "collected_at_utc": utc_text(),
            "host": host_name or socket.gethostname(), "source_run_path": answer["run_path"],
            "done_sha256": done_sha, "files": entries,
        })
        code = 0 if status_value == "PASS" else 2
        if not os.path.lexists(dest):
            os.replace(temp, dest)
            published = True
            return code, {"run_id": run_id, "status": status_value, "label": label,
                          "local_path": str(dest), "already_collected": False}
        existing = read_json(dest / "COLLECTED.json")
        if not existing or existing.get("schema") != SCHEMA_COLLECTED:
            raise VisibleCaseError("destination exists and is not a visible-case collection; not replaced")
        verify_manifest(dest, existing.get("files"))
        if (existing.get("run_id") == run_id and existing.get("done_sha256") == done_sha
                and existing.get("files") == entries):
            return code, {"run_id": run_id, "status": status_value, "label": label,
                          "local_path": str(dest), "already_collected": True}
        if existing.get("status") == "INCOMPLETE" and status_value != "INCOMPLETE":
            aside = _unique_aside(dest)
            os.rename(dest, aside)
            try:
                os.replace(temp, dest)
            except OSError:
                os.rename(aside, dest)
                raise
            published = True
            return code, {"run_id": run_id, "status": status_value, "label": label, "local_path": str(dest),
                          "already_collected": False, "superseded_incomplete": str(aside)}
        raise VisibleCaseError("a different collection already exists at the destination; not replaced")
    finally:
        if not published:
            shutil.rmtree(temp, ignore_errors=True)


# --- command line -----------------------------------------------------------

def _emit(payload, code, lines=(), error=None):
    for line in lines:
        print(line)
    if error:
        print(f"visible-case: {error}", file=sys.stderr)
    print(json.dumps(payload, sort_keys=True))
    return code


def _command(work):
    try:
        code, payload, lines = work()
    except NotFinal as exc:
        return _emit({**exc.payload, "error": str(exc)}, 3, lines=[str(exc)])
    except TransportError as exc:
        return _emit({"error": str(exc)}, 3, error=str(exc))
    except VisibleCaseError as exc:
        return _emit({"error": str(exc)}, 2, error=str(exc))
    return _emit(payload, code, lines=lines)


def cmd_run(args, *, active, machines):
    settings = machines[active]

    def work():
        if active != "B":
            raise VisibleCaseError("visible-case run executes on B; request runs on A")
        result = start_run(selected_repo=settings["repo"], worktree_root=settings.get("worktree_root"),
                           case=args.case, sha=args.sha, run_id=args.run_id, hold=args.hold,
                           requested_by=args.requested_by, detach=args.detach)
        return 0, result, [f"B run {result['run_id']}: state={result['state']} at {result['run_path']}"]
    return _command(work)


def cmd_status(args, *, active, machines):
    def work():
        result = status(workspace_for(machines[active]["repo"]), args.run_id)
        return 0, result, [f"run {result['run_id']}: state={result['state']} done={str(result['done']).lower()} "
                           f"status={result['status']}"]
    return _command(work)


def cmd_request(args, *, active, machines):
    def work():
        if active != "A":
            raise VisibleCaseError("visible-case request runs on A")
        return request(case=args.case, sha=args.sha, repo=args.repo, hold=args.hold, no_wait=args.no_wait,
                       poll_interval=args.poll_interval, max_wait=args.max_wait,
                       remote=Remote(handoff.Machine("B", machines["B"])),
                       local_workspace=machines["A"]["repo"], cwd=Path.cwd(),
                       requested_by=f"A:{socket.gethostname()}", log=flush_print)
    return _command(work)


def cmd_collect(args, *, active, machines):
    def work():
        if active != "A":
            raise VisibleCaseError("visible-case collect runs on A")
        code, payload = collect(run_id=args.run_id, remote=Remote(handoff.Machine("B", machines["B"])),
                                local_workspace=machines["A"]["repo"],
                                accept_incomplete=args.accept_incomplete)
        return code, payload, [f"{payload['run_id']}: {payload['label']} -> {payload['local_path']}"
                               f"{' (already collected)' if payload['already_collected'] else ''}"
                               f"{' (earlier INCOMPLETE copy kept at ' + payload['superseded_incomplete'] + ')' if payload.get('superseded_incomplete') else ''}"]
    return _command(work)


def add_subcommands(commands):
    group = commands.add_parser("visible-case", help="visible B case-open runs (run/status on B; request/collect on A)")
    sub = group.add_subparsers(dest="visible_case_command", required=True)
    run = sub.add_parser("run", help="B: start one supervised visible case run")
    run.add_argument("--case", required=True)
    run.add_argument("--sha", required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--hold", type=int, default=90)
    run.add_argument("--requested-by", default="unknown")
    run.add_argument("--detach", action="store_true")
    state = sub.add_parser("status", help="read one run's state; never modifies it")
    state.add_argument("--run-id", required=True)
    req = sub.add_parser("request", help="A: preflight, ask B to run, wait, then collect")
    req.add_argument("--case", required=True)
    source = req.add_mutually_exclusive_group()
    source.add_argument("--sha")
    source.add_argument("--repo")
    req.add_argument("--hold", type=int, default=90)
    req.add_argument("--no-wait", action="store_true")
    req.add_argument("--poll-interval", type=int, default=20)
    req.add_argument("--max-wait", type=int, default=1800)
    collect_parser = sub.add_parser("collect", help="A: collect a finished B run into the local data tree")
    collect_parser.add_argument("--run-id", required=True)
    collect_parser.add_argument("--accept-incomplete", action="store_true")
    return group


def dispatch(args, *, active, machines):
    command = args.visible_case_command
    if command == "run":
        return cmd_run(args, active=active, machines=machines)
    if command == "status":
        return cmd_status(args, active=active, machines=machines)
    if command == "request":
        return cmd_request(args, active=active, machines=machines)
    return cmd_collect(args, active=active, machines=machines)


def main(argv=None):
    """Internal entry point: `python3 visible_case.py supervise --run-dir D --repo R --worktree-root W`."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    supervise_parser = commands.add_parser("supervise", help="supervise one run directory")
    supervise_parser.add_argument("--run-dir", required=True)
    supervise_parser.add_argument("--repo", required=True)
    supervise_parser.add_argument("--worktree-root", required=True)
    args = parser.parse_args(argv)
    try:
        supervise(Path(args.run_dir), repo=args.repo, worktree_root=args.worktree_root)
    except VisibleCaseError as exc:
        print(f"visible-case supervise: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
