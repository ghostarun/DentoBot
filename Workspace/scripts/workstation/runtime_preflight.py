#!/usr/bin/env python3
"""Read-only host and runtime preflight for a DentoBot checkout."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path


ENV_KEYS = {
    "DENTOBOT_BACKEND_PYTHON", "DENTOBOT_BACKEND_DEVICE", "DENTOBOT_BACKEND_EXECUTION_MODE",
    "DENTOBOT_RENDER_DEVICE", "DENTOBOT_RENDER_GID", "DENTOBOT_HOST_UID", "DENTOBOT_HOST_GID",
    "DENTOBOT_RUN_ARTIFACT_ROOT", "DENTOBOT_TOTALSEG_HOME_DIR", "DENTOBOT_WORKSPACE_ROOT",
    "DISPLAY", "XAUTHORITY",
}
PATH_KEYS = ("DENTOBOT_RUN_ARTIFACT_ROOT", "DENTOBOT_TOTALSEG_HOME_DIR", "DENTOBOT_WORKSPACE_ROOT")
RAM_LIMIT = 1024**3
DISK_LIMIT = 1024**3


def run_command(argv: list[str], timeout: int = 30, env: dict[str, str] | None = None):
    """Run one captured argv without a shell; never return raw errors to the report."""
    child_env = os.environ.copy()
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        child_env.update(env)
    try:
        completed = subprocess.run(
            [str(arg) for arg in argv], capture_output=True, text=True,
            timeout=timeout, check=False, env=child_env,
        )
    except subprocess.TimeoutExpired:
        return False, "", "", f"timed out after {timeout}s"
    except OSError:
        return False, "", "", "could not start command"
    if completed.returncode:
        return False, completed.stdout, completed.stderr, f"exited with status {completed.returncode}"
    return True, completed.stdout, completed.stderr, ""


def parse_env_file(path: Path) -> tuple[dict[str, str], list[str]]:
    """Read only whitelisted primitive assignments; shell syntax is never evaluated."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}, ["config file is missing or unreadable"]
    values, errors = {}, []
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.fullmatch(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", stripped)
        if not match:
            errors.append(f"unsupported config syntax on line {number}")
            continue
        key, raw = match.groups()
        if key not in ENV_KEYS:
            continue
        if any(char in raw for char in ("$", "`", ";", "|", "&", "<", ">")):
            errors.append(f"unsupported shell expression for {key} on line {number}")
            continue
        try:
            tokens = shlex.split(raw, comments=True, posix=True)
        except ValueError:
            errors.append(f"invalid quoting for {key} on line {number}")
            continue
        if len(tokens) > 1:
            errors.append(f"unquoted whitespace for {key} on line {number}")
            continue
        values[key] = tokens[0] if tokens else ""
    return values, errors


def effective_config(file_values: dict[str, str], environ: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    keys = sorted(ENV_KEYS)
    effective = {key: environ.get(key) or file_values.get(key, "") for key in keys}
    sources = {key: "environment" if environ.get(key) else ("config" if file_values.get(key) else "unset") for key in keys}
    return effective, sources


def _is_python_version_slice(node: ast.AST) -> bool:
    return (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name) and node.value.value.id == "sys"
            and node.value.attr == "version_info" and isinstance(node.slice, ast.Slice)
            and node.slice.lower is None and isinstance(node.slice.upper, ast.Constant)
            and node.slice.upper.value == 2 and node.slice.step is None)


def _probe_literals(code: str) -> tuple[dict[str, str], tuple[int, int], str]:
    tree = ast.parse(code)
    expected_nodes = [node.value for node in tree.body if
        (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "expected" for t in node.targets))
        or (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "expected")]
    if len(expected_nodes) != 1:
        raise ValueError("probe must assign one literal expected package mapping")
    expected = ast.literal_eval(expected_nodes[0])
    if not isinstance(expected, dict) or not expected or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in expected.items()):
        raise ValueError("probe expected mapping must contain package-name string pins")

    versions = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
            continue
        test = node.test
        if not _is_python_version_slice(test.left) or len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq) or len(test.comparators) != 1:
            continue
        try:
            version = ast.literal_eval(test.comparators[0])
        except (ValueError, TypeError):
            continue
        if isinstance(version, tuple) and len(version) == 2 and all(type(v) is int for v in version):
            versions.append(version)
    if len(versions) != 1:
        raise ValueError("probe must assert one literal sys.version_info[:2] tuple")

    torch_pin = next((pin.lower() for name, pin in expected.items() if name.lower().replace("-", "") == "torch"), None)
    if not torch_pin or "+" not in torch_pin:
        raise ValueError("probe torch pin has no CPU/CUDA build suffix")
    flavor = torch_pin.rsplit("+", 1)[1]
    if flavor == "cpu":
        device = "cpu"
    elif flavor == "cu" or (flavor.startswith("cu") and flavor[2:].isalnum()):
        device = "cuda:0"
    else:
        raise ValueError("probe torch pin has an unknown build suffix")
    return expected, versions[0], device


def extract_backend_probe(launcher_text: str, device: str) -> tuple[dict[str, str], tuple[int, int], str]:
    """Select a CPU/CUDA probe from shell literal assignments, parsing Python only as AST."""
    candidates = []
    pattern = r"(?m)^[ \t]*(?:export[ \t]+)?backend_dependency_probe[ \t]*="
    for match in re.finditer(pattern, launcher_text):
        start = match.end()
        line_end = launcher_text.find("\n", start)
        initial = launcher_text[start:line_end if line_end >= 0 else None].strip()
        if initial in ('""', "''"):
            continue
        while start < len(launcher_text) and launcher_text[start].isspace():
            start += 1
        if start >= len(launcher_text) or launcher_text[start] != "'":
            raise ValueError("probe must be a single-quoted literal")
        close = launcher_text.find("'", start + 1)
        if close < 0:
            raise ValueError("probe literal is not closed")
        line_end = launcher_text.find("\n", close)
        trailing = launcher_text[close + 1:line_end if line_end >= 0 else None].strip()
        if trailing and not trailing.startswith("#"):
            raise ValueError("probe assignment has trailing shell syntax")
        statement = launcher_text[match.start():close + 1].strip()
        tokens = shlex.split(statement, comments=False, posix=True)
        if tokens and tokens[0] == "export": tokens = tokens[1:]
        if len(tokens) != 1 or not tokens[0].startswith("backend_dependency_probe="):
            raise ValueError("probe is not a simple assignment")
        code = tokens[0].split("=", 1)[1]
        if code.strip():
            candidates.append(_probe_literals(code))
    selected = [candidate for candidate in candidates if candidate[2] == device]
    if len(selected) != 1:
        raise ValueError("no unique literal probe matches configured backend device")
    return selected[0]


def parse_compose_image(text: str) -> str:
    services = re.search(r"(?m)^services\s*:\s*(?:#.*)?$", text)
    if not services:
        raise ValueError("compose services block not found")
    tail = text[services.end():]
    service = re.search(r"(?m)^ {2}[A-Za-z0-9_.-]+\s*:\s*(?:#.*)?$", tail)
    if not service:
        raise ValueError("compose root service not found")
    body = re.split(r"(?m)^ {2}\S", tail[service.end():], maxsplit=1)[0]
    image = re.search(r"(?m)^ {4}image\s*:\s*(.*?)\s*(?:#.*)?$", body)
    if not image:
        raise ValueError("root service image is missing")
    value = image.group(1).strip()
    if "$" in value or "`" in value:
        raise ValueError("compose image uses unsupported interpolation")
    tokens = shlex.split(value, comments=True, posix=True)
    if len(tokens) != 1 or not tokens[0]:
        raise ValueError("compose image is not a simple scalar")
    return tokens[0]


def verify_data_manifest(manifest_path: Path, data_root: Path) -> tuple[bool, list[str], int]:
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, ["data manifest is missing or invalid JSON"], 0
    if not isinstance(manifest, list):
        return False, ["data manifest must be a JSON list"], 0
    root = data_root.resolve()
    for index, entry in enumerate(manifest, 1):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not isinstance(entry.get("sha256"), str):
            errors.append(f"manifest entry {index} needs path and sha256 strings")
            continue
        expected_hash = entry["sha256"].lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            errors.append(f"manifest entry {index} has an invalid SHA-256")
            continue
        supplied = Path(entry["path"])
        candidate = supplied if supplied.is_absolute() else root / supplied
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            errors.append(f"manifest entry {index} escapes workspace/data")
            continue
        if not resolved.is_file():
            errors.append(f"manifest entry {index} is not a regular file")
            continue
        digest = hashlib.sha256()
        try:
            with resolved.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            errors.append(f"manifest entry {index} could not be read")
            continue
        if digest.hexdigest() != expected_hash:
            errors.append(f"manifest entry {index} checksum does not match")
    return not errors, errors, len(manifest)


def _os_identity() -> dict:
    pretty_name = ""
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                fields = shlex.split(line.split("=", 1)[1], comments=False, posix=True)
                pretty_name = fields[0] if fields else ""
                break
    except (OSError, ValueError):
        pass
    return {
        "hostname": socket.gethostname(),
        "os": pretty_name or platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
    }


def _display_version(output: str):
    versions = []
    renderer = ""
    for line in output.splitlines():
        if "OpenGL renderer string:" in line:
            renderer = line.split("OpenGL renderer string:", 1)[1].strip()
        if re.search(r"OpenGL (?:core profile )?version string:", line):
            found = re.search(r"version string:\s*(\d+)\.(\d+)", line)
            if found:
                versions.append(("core profile" in line.lower(), int(found.group(1)), int(found.group(2))))
    if not versions:
        return None, renderer
    versions.sort(reverse=True)
    return (versions[0][1], versions[0][2]), renderer


def _memory_available() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def run_preflight(args, environ: dict[str, str] | None = None) -> dict:
    environ = os.environ if environ is None else environ
    checks = []
    def ck(name, ok, message, info=False):
        checks.append({"name": name, "status": "passed" if ok else ("info" if info else "blocked"), "message": message})

    result = {"preflight_passed": False, "runtime_verified": False, "loaded_code_verified": False,
              "safe_to_shutdown": False, "datasets_verified": False, "machine": _os_identity(), "checks": checks}
    repo_arg, sha_arg = getattr(args, "repo", None), getattr(args, "expected_sha", None)
    if not repo_arg or not sha_arg:
        ck("arguments", False, "--repo and --expected-sha are required")
        return result
    repo, expected_sha = Path(repo_arg).expanduser().resolve(), str(sha_arg).strip()
    result["repo"] = str(repo)
    if not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", expected_sha):
        ck("git_snapshot", False, "expected SHA must be a full Git object ID")
    elif not repo.is_dir():
        ck("git_snapshot", False, "repository directory is missing")
    else:
        ok, out, _, error = run_command(["git", "-C", str(repo), "rev-parse", "HEAD"])
        if not ok:
            ck("git_snapshot", False, f"could not read repository HEAD ({error})")
        else:
            sha = out.strip()
            ok_status, status, _, status_error = run_command(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"])
            clean, matches = ok_status and not status.strip(), sha.lower() == expected_sha.lower()
            message = ("HEAD matches the expected SHA and working tree is clean" if matches and clean else
                       "HEAD does not match the expected SHA" if not matches else
                       f"could not inspect working tree ({status_error})" if not ok_status else "working tree has local changes")
            ck("git_snapshot", matches and clean, message)
            result["git"] = {"head": sha, "clean": clean}

    workspace = repo.parents[2] if len(repo.parents) >= 3 else repo.parent
    layout_ok = (repo.parent.name == "src" and repo.parent.parent.name == "ros2_ws" and
                 (workspace / "ros2_ws" / "src").resolve() == repo.parent.resolve())
    result.update({"workspace": str(workspace), "intended_container_repo": f"/workspace/ros2_ws/src/{repo.name}"})
    ck("repo_layout", layout_ok, "checkout matches workspace/ros2_ws/src/<checkout>" if layout_ok else
       "checkout must be workspace/ros2_ws/src/<checkout>")

    launcher = repo / "Workspace/scripts/launch-dentoworkflow.bash"
    compose = repo / "Workspace/compose.yaml"
    override = workspace / "compose.override.yaml"
    module = repo / "DENTOWorkflow"
    required = launcher.is_file() and compose.is_file() and module.is_dir()
    ck("required_files", required, "launcher, compose file, and DENTOWorkflow directory are present" if required else
       "required launcher, compose file, or DENTOWorkflow directory is missing")
    managed_cuda_override = (
        override.is_symlink()
        and override.resolve() == (repo / "Workspace/compose.cuda.yaml").resolve()
        and override.is_file()
    )
    ck("compose_override", not override.exists() or managed_cuda_override,
       "versioned CUDA override selected" if managed_cuda_override else
       "no compose override is active" if not override.exists() else
       "compose.override.yaml is not modeled by this preflight")
    file_values, config_errors = parse_env_file(workspace / ".dentobot.env")
    config_exists = (workspace / ".dentobot.env").is_file()
    ck("config", config_exists and not config_errors, "whitelisted config assignments parsed" if config_exists and not config_errors else
       "config file is missing" if not config_exists else "; ".join(config_errors))
    config, sources = effective_config(file_values, dict(environ))
    display_arg, auth_arg = getattr(args, "display", None), getattr(args, "xauthority", None)
    display = display_arg or config["DISPLAY"]
    xauthority = auth_arg or config["XAUTHORITY"]
    config["DENTOBOT_BACKEND_DEVICE"] = config["DENTOBOT_BACKEND_DEVICE"] or "cpu"
    config["DENTOBOT_BACKEND_EXECUTION_MODE"] = config["DENTOBOT_BACKEND_EXECUTION_MODE"] or "local"
    config["DENTOBOT_RENDER_DEVICE"] = config["DENTOBOT_RENDER_DEVICE"] or "/dev/dri/renderD128"
    root_setting = config["DENTOBOT_WORKSPACE_ROOT"]
    try:
        root_matches = not root_setting or Path(root_setting).expanduser().resolve() == workspace.resolve()
    except OSError:
        root_matches = False
    ck("workspace_root", root_matches, "configured workspace root matches inferred workspace" if root_matches else
       "DENTOBOT_WORKSPACE_ROOT differs from inferred workspace")
    mode = config["DENTOBOT_BACKEND_EXECUTION_MODE"].strip().lower()
    ck("execution_mode", mode == "local", "local backend mode is supported" if mode == "local" else
       "nonlocal backend execution mode is not covered by this preflight")
    result["config"] = {
        "sources": sources, "backend_device": config["DENTOBOT_BACKEND_DEVICE"],
        "execution_mode": config["DENTOBOT_BACKEND_EXECUTION_MODE"],
        "render_device": config["DENTOBOT_RENDER_DEVICE"],
        "artifact_paths": {key: config[key] for key in PATH_KEYS if config.get(key)},
        "display": display or None, "display_source": "argument" if display_arg else sources["DISPLAY"],
        "xauthority_configured": bool(xauthority),
        "xauthority_source": "argument" if auth_arg else sources["XAUTHORITY"],
    }

    device = config["DENTOBOT_BACKEND_DEVICE"].strip().lower()
    expected, expected_python, probe_device = None, None, None
    try:
        expected, expected_python, probe_device = extract_backend_probe(launcher.read_text(encoding="utf-8"), device)
        ck("backend_probe", True, "package pins and Python version parsed from a literal probe")
    except (OSError, SyntaxError, ValueError):
        ck("backend_probe", False, "launcher dependency probe format is unknown or unavailable")
    backend_python = config["DENTOBOT_BACKEND_PYTHON"].strip()
    executable = shutil.which(backend_python) if backend_python else None
    python_ok = bool(executable and os.access(executable, os.X_OK))
    ck("backend_python", python_ok, "configured backend Python is executable" if python_ok else
       "DENTOBOT_BACKEND_PYTHON is missing or not executable")
    if probe_device:
        ck("backend_device", device == probe_device, "configured device matches the pinned torch build" if device == probe_device else
           "configured device does not match the pinned torch build")
    if python_ok and expected is not None and expected_python is not None:
        code = ("import json,sys\nfrom importlib.metadata import PackageNotFoundError,version\n"
                "packages={}\nfor name in sys.argv[1:]:\n try: packages[name]=version(name)\n"
                " except PackageNotFoundError: packages[name]=None\n"
                "print(json.dumps({'python':list(sys.version_info[:3]),'packages':packages}))\n")
        ok, out, _, error = run_command([executable, "-B", "-c", code, *expected], timeout=30)
        try:
            metadata = json.loads(out) if ok else None
        except json.JSONDecodeError:
            metadata = None
        if not isinstance(metadata, dict):
            ck("backend_metadata", False, f"backend metadata probe failed ({error or 'invalid response'})")
        else:
            installed, version = metadata.get("packages", {}), metadata.get("python", [])
            missing = [name for name in expected if not installed.get(name)]
            mismatched = [name for name, pin in expected.items() if installed.get(name) != pin]
            version_ok = isinstance(version, list) and len(version) >= 2 and tuple(version[:2]) == expected_python
            ok = not missing and not mismatched and version_ok
            details = ("missing metadata for " + ", ".join(missing) if missing else
                       "package pins differ for " + ", ".join(mismatched) if mismatched else "")
            if not version_ok:
                details = (details + "; " if details else "") + "Python version differs from the launcher pin"
            ck("backend_metadata", ok, "package pins and Python version match" if ok else details)
            result["backend"] = {"python": version, "packages": installed, "torch_build": probe_device}
    else:
        ck("backend_metadata", False, "backend executable or literal launcher pins are unavailable")

    try:
        image = parse_compose_image(compose.read_text(encoding="utf-8"))
        result["image"] = {"name": image}
        ck("compose_image", True, "root service image parsed")
    except (OSError, ValueError):
        image = None
        ck("compose_image", False, "compose root service image is missing or unsupported")
    if image:
        template = '{"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}},"Created":{{json .Created}}}'
        ok, out, _, error = run_command(["docker", "image", "inspect", "--format", template, image], timeout=20)
        try:
            identity = json.loads(out) if ok else None
        except json.JSONDecodeError:
            identity = None
        if not isinstance(identity, dict):
            ck("image_available", False, f"compose image is unavailable or inspect failed ({error or 'invalid response'})")
        else:
            result["image"].update({"id": identity.get("Id"), "repo_digests": identity.get("RepoDigests") or [],
                                    "created": identity.get("Created")})
            requested_id = getattr(args, "image_id", None)
            same_id = not requested_id or identity.get("Id") == requested_id
            ck("image_available", same_id, "image is available and identity matches" if same_id else
               "available image ID differs from --image-id")
    else:
        ck("image_available", False, "compose image could not be determined")

    data, home = workspace / "data", workspace / "slicer-home"
    extension = data / "SlicerEndoPlanner-main/PulpChamberOpenPlanning"
    paths_ok = data.is_dir() and home.is_dir() and extension.is_dir()
    ck("host_paths", paths_ok, "workspace data, Slicer home, and required extension directory are present" if paths_ok else
       "workspace/data, slicer-home, or required extension directory is missing")
    render = Path(config["DENTOBOT_RENDER_DEVICE"])
    render_ok = render.exists() and os.access(render, os.R_OK | os.W_OK)
    ck("render_device", render_ok, "render device exists and is readable/writable" if render_ok else
       "configured render device is missing or inaccessible")

    display_source = "argument" if display_arg else sources["DISPLAY"]
    if not display:
        sockets = sorted(Path("/tmp/.X11-unix").glob("X[0-9]*"))
        if len(sockets) == 1:
            display, display_source = ":" + sockets[0].name[1:], "inferred"
        else:
            ck("display", False, "DISPLAY is unset and no unique local X socket is available")
    if display:
        gl_env = {"DISPLAY": display}
        if xauthority:
            gl_env["XAUTHORITY"] = xauthority
        ok, out, _, error = run_command(["glxinfo", "-B"], timeout=15, env=gl_env)
        version, renderer = _display_version(out) if ok else (None, "")
        good = version is not None and version >= (3, 2)
        message = (f"glxinfo -B failed ({error}); display authentication may be unavailable" if not ok else
                   "glxinfo did not report an OpenGL version" if version is None else
                   "OpenGL version meets the 3.2 minimum" if good else "OpenGL version is below 3.2")
        ck("display", good, message)
        low = renderer.lower()
        kind = "llvmpipe/software" if any(x in low for x in ("llvmpipe", "softpipe", "swrast", "lavapipe")) else ("hardware" if renderer else "unknown")
        result["graphics"] = {"display": display, "display_source": display_source,
                              "opengl_version": list(version) if version else None,
                              "renderer": renderer or None, "renderer_class": kind,
                              "xauthority_configured": bool(xauthority)}

    memory = _memory_available()
    try:
        disk = shutil.disk_usage(workspace).free
    except OSError:
        disk = None
    resources_ok = memory is not None and disk is not None and memory >= RAM_LIMIT and disk >= DISK_LIMIT
    ck("resources", resources_ok, "available memory and disk meet the 1 GiB thresholds" if resources_ok else
       "available memory or workspace disk is below 1 GiB, or could not be measured")
    result["resources"] = {"memory_available_bytes": memory, "workspace_disk_free_bytes": disk,
                           "minimum_memory_bytes": RAM_LIMIT, "minimum_disk_bytes": DISK_LIMIT}
    manifest = getattr(args, "data_manifest", None)
    if manifest:
        verified, errors, count = verify_data_manifest(Path(manifest).expanduser(), data)
        result["datasets_verified"] = verified
        ck("data_manifest", verified, f"verified {count} listed dataset file(s)" if verified else "; ".join(errors))
    else:
        ck("data_manifest", False, "no manifest supplied; dataset and case readiness remain unverified", info=True)

    template = '{"Running":{{json .State.Running}},"Mounts":{{json .Mounts}}}'
    ok, out, stderr, error = run_command(["docker", "container", "inspect", "--format", template,
                                          "dentobot-slicerros2"], timeout=20)
    if not ok:
        missing = any(token in stderr.lower() for token in ("no such object", "no such container", "not found"))
        ck("container", False, "container is absent; launch has not been attempted" if missing else
           f"container was not inspected ({error})", info=missing)
    else:
        try:
            container = json.loads(out)
            running, mounts = bool(container.get("Running")), container.get("Mounts") or []
        except (json.JSONDecodeError, AttributeError):
            running, mounts = None, []
        if running is None:
            ck("container", False, "container inspect returned invalid metadata")
        elif not running:
            result["container"] = {"running": False}
            ck("container", False, "container is stopped; launch has not been attempted", info=True)
        else:
            expected_mounts = {"/workspace/ros2_ws": workspace / "ros2_ws",
                               "/workspace/data": data, "/home/dentobot": home}
            found = {}
            for destination, host in expected_mounts.items():
                found[destination] = [m.get("Destination") for m in mounts if isinstance(m, dict) and m.get("Source")
                               and m.get("Destination") == destination
                               and Path(m["Source"]).resolve() == host.resolve()] if isinstance(mounts, list) else []
            mounts_ok = all(found.values())
            result["container"] = {"running": True, "mount_sources_match": mounts_ok,
                                    "mount_destinations": found}
            ck("container_mounts", mounts_ok, "running container mounts match expected host paths" if mounts_ok else
               "running container mount sources do not match expected host paths")
    result["preflight_passed"] = not any(item["status"] == "blocked" for item in checks)
    return result

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--image-id")
    parser.add_argument("--display")
    parser.add_argument("--xauthority")
    parser.add_argument("--data-manifest")
    result = run_preflight(parser.parse_args(argv))
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0 if result.get("preflight_passed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
