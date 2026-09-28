"""Build a run-local Step 6 diagnostics summary from existing evidence."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
VIDEO_SUFFIXES = {".mkv", ".mp4", ".mov", ".avi", ".webm"}
LOG_SUFFIXES = {".log"}
EXIT_KEYS = ("exit_status", "command_exit_status", "ffmpeg_exit_status")


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _input_file(value: str, root: Path, label: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {value}")
    resolved = path.resolve()
    if not _within(resolved, root):
        raise ValueError(f"{label} must be inside --run-dir: {value}")
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} does not exist: {value}")
    return resolved


def _input_path(value: str, root: Path, label: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {value}")
    resolved = path.resolve(strict=False)
    if not _within(resolved, root):
        raise ValueError(f"{label} must be inside --run-dir: {value}")
    if resolved.exists() and not resolved.is_file():
        raise ValueError(f"{label} must be a file: {value}")
    return resolved


def _read_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_files(root: Path):
    files = []
    for directory, names, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        names[:] = [name for name in names if not (base / name).is_symlink()]
        for name in filenames:
            path = base / name
            if path.is_symlink() or not path.is_file():
                continue
            resolved = path.resolve()
            if _within(resolved, root):
                files.append(resolved)
    return sorted(set(files))


def _image_refs(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _image_refs(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _image_refs(item)
    elif isinstance(value, str) and Path(value).suffix.lower() in IMAGE_SUFFIXES:
        yield value


def _inventory(root: Path, report_path: Path, manifest_path: Path, cleanup_path: Path,
               report: dict, manifest: dict):
    entries = {}

    def add(kind: str, path: Path, status: str = "PRESENT", raw: str = ""):
        resolved = path.resolve(strict=False)
        if status == "PRESENT" and (path.is_symlink() or not _within(resolved, root)
                                      or not resolved.is_file()):
            status = "UNSAFE" if not _within(resolved, root) or path.is_symlink() else "MISSING"
        key = (kind, str(resolved) if status == "PRESENT" else raw or str(path))
        if key in entries:
            return
        entry = {"kind": kind, "path": (str(resolved.relative_to(root))
                                           if _within(resolved, root) else Path(raw or path).name),
                 "status": status}
        if status == "PRESENT":
            entry["sha256"] = _sha256(resolved)
            entry["bytes"] = resolved.stat().st_size
        entries[key] = entry

    for path in _run_files(root):
        suffix = path.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            add("Screenshot", path)
        elif suffix in LOG_SUFFIXES:
            add("Log", path)
        elif suffix in VIDEO_SUFFIXES:
            add("Video", path)
    add("Runner report", report_path)
    add("Video manifest", manifest_path)
    add("Cleanup report", cleanup_path, "PRESENT" if cleanup_path.is_file() else "MISSING")
    for name, kind in (
        ("step6-manual-record-probe.json", "Manual record JSON"),
        ("step6-manual-record-probe.report.txt", "Manual record report"),
    ):
        path = root / name
        if path.exists() or path.is_symlink():
            add(kind, path)

    missing_image_refs = []
    for raw in sorted(set(_image_refs(report.get("screenshots", {})))):
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = report_path.parent / path
        resolved = path.resolve(strict=False)
        if path.is_symlink() or not _within(resolved, root):
            add("Screenshot reference", path, "UNSAFE", raw)
            missing_image_refs.append(raw)
        elif not resolved.is_file():
            add("Screenshot reference", resolved, "MISSING", raw)
            missing_image_refs.append(raw)
        else:
            add("Screenshot", resolved)

    inventory = sorted(entries.values(), key=lambda item: (item["kind"], item["path"]))
    videos = [item for item in inventory if item["kind"] == "Video" and item["status"] == "PRESENT"]
    expected_video_hash = manifest.get("output_sha256")
    video_hash_matched = bool(expected_video_hash) and any(
        item.get("sha256") == expected_video_hash for item in videos
    )
    return inventory, missing_image_refs, video_hash_matched


def _functional_status(report: dict, items: dict) -> str:
    statuses = [str(item.get("status", "MISSING")).upper()
                for item in items.values() if isinstance(item, dict)]
    report_status = str(report.get("status", "MISSING")).upper()
    if report_status in {"FAIL", "FAILED", "ERROR"} or any(
        status in {"FAIL", "FAILED", "ERROR"} for status in statuses
    ):
        return "FAIL"
    if report_status == "PASS" and statuses and all(status == "PASS" for status in statuses):
        return "PASS"
    return "INCOMPLETE"


def _exit_text(value) -> str:
    return str(value) if type(value) is int else "missing"


def _reason(item: dict) -> str:
    for key in ("reason", "failure_reason", "error", "message", "note"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return "No explicit reason recorded."


def _escape(value) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _flatten(prefix: str, value):
    if isinstance(value, dict):
        for key, item in sorted(value.items()):
            yield from _flatten(f"{prefix}.{key}" if prefix else str(key), item)
    elif value not in (None, ""):
        text = json.dumps(value, sort_keys=True, ensure_ascii=False) if isinstance(value, (list, tuple)) else str(value)
        yield prefix, text


def _summary(run_dir: Path, report_path: Path, manifest_path: Path, cleanup_path: Path,
             session: str, plan_gate: str) -> tuple[str, bool]:
    report = _read_json(report_path, "runner report")
    manifest = _read_json(manifest_path, "video manifest")
    cleanup = _read_json(cleanup_path, "cleanup report") if cleanup_path.is_file() else None
    items = report.get("items")
    if not isinstance(items, dict):
        items = {}
    inventory, missing_images, video_hash_matched = _inventory(
        run_dir, report_path, manifest_path, cleanup_path, report, manifest
    )
    functional = _functional_status(report, items)
    exits_ok = all(type(manifest.get(key)) is int and manifest[key] == 0 for key in EXIT_KEYS)
    video_ok = manifest.get("status") == "complete" and exits_ok and video_hash_matched
    workflow_claimed = report.get("full_workflow_claimed") is True
    cleanup_ok = (cleanup is not None and cleanup.get("owned_process_cleanup") is True
                  and cleanup.get("remaining_owned_processes") == [])
    has_screenshot = any(item["kind"] == "Screenshot" and item["status"] == "PRESENT"
                         for item in inventory)
    complete = (functional == "PASS" and video_ok and workflow_claimed and cleanup_ok
                and has_screenshot and not missing_images)

    verdict = report.get("operator_verdict")
    verdict_text = "PENDING" if verdict in (None, "") else json.dumps(verdict, ensure_ascii=False)
    lines = [
        f"# Step 6 evidence — {_escape(session)}",
        "",
        f"**Plan gate:** {_escape(plan_gate)}",
        f"**Whole-run evidence:** {'COMPLETE' if complete else 'INCOMPLETE'}",
        f"**Functional checklist:** {functional} (runner status: {_escape(report.get('status', 'missing'))})",
        f"**Runner full-workflow claim:** {'true' if workflow_claimed else 'false or missing'}",
        f"**Process/recording shutdown:** command exit {_exit_text(manifest.get('command_exit_status'))}; "
        f"recorder exit {_exit_text(manifest.get('exit_status'))}; FFmpeg exit {_exit_text(manifest.get('ffmpeg_exit_status'))}; "
        f"video status {_escape(manifest.get('status', 'missing'))}",
        f"**Owned-process cleanup:** {'PASS' if cleanup_ok else 'INCOMPLETE'} "
        f"(owned_process_cleanup={_escape(cleanup.get('owned_process_cleanup', 'missing') if cleanup else 'missing')}; "
        f"remaining_owned_processes={_escape(json.dumps(cleanup.get('remaining_owned_processes', 'missing') if cleanup else 'missing'))})",
        "Cleanup attestation must come from the outer wrapper after exact owned PID/PGID checks; this tool does not infer process absence.",
        f"**Operator verdict:** {verdict_text}",
        "",
        "## Planned checks and observed results",
        "",
        "| Planned item | Observed status | Reason |",
        "|---|---|---|",
    ]
    if items:
        for name, value in sorted(items.items()):
            item = value if isinstance(value, dict) else {"status": "MISSING"}
            lines.append(
                f"| {_escape(name)} | {_escape(item.get('status', 'MISSING'))} | {_escape(_reason(item))} |"
            )
    else:
        lines.append("| No checklist items recorded | MISSING | Runner report has no items object. |")

    provenance = []
    for key in ("case_source", "case_sha256_before_open", "case_sha256_after_open", "saved_case"):
        if report.get(key) not in (None, ""):
            provenance.append((f"case.{key}", str(report[key])))
    for group in ("checkout", "native_preflight"):
        provenance.extend(_flatten(group, report.get(group, {})))
    lines.extend(["", "## Provenance", ""])
    if provenance:
        lines.extend(f"- `{_escape(key)}`: `{_escape(value)}`" for key, value in provenance)
    else:
        lines.append("No case, checkout, or native provenance was recorded in the report.")

    lines.extend(["", "## File SHA-256 inventory", "", "| Type | File | Status | SHA-256 | Bytes |", "|---|---|---|---|---:|"])
    for item in inventory:
        lines.append(
            f"| {_escape(item['kind'])} | `{_escape(item['path'])}` | {_escape(item['status'])} | "
            f"`{item.get('sha256', '')}` | {item.get('bytes', '')} |"
        )
    if missing_images:
        lines.extend(["", "Missing or unsafe screenshot references:"])
        lines.extend(f"- `{_escape(Path(raw).name)}`" for raw in missing_images)

    blockers = []
    if functional != "PASS":
        blockers.append(f"functional checklist is {functional}")
    if not workflow_claimed:
        blockers.append("runner full_workflow_claimed is not true")
    if cleanup is None:
        blockers.append("cleanup report is missing")
    elif cleanup.get("owned_process_cleanup") is not True:
        blockers.append("owned_process_cleanup is not true")
    elif cleanup.get("remaining_owned_processes") != []:
        blockers.append("remaining_owned_processes is not an empty list")
    if manifest.get("status") != "complete":
        blockers.append(f"video status is {manifest.get('status', 'missing')}")
    for key in EXIT_KEYS:
        if type(manifest.get(key)) is not int or manifest[key] != 0:
            blockers.append(f"{key} is {_exit_text(manifest.get(key))}")
    if not video_hash_matched:
        blockers.append("no local video matches the manifest output_sha256")
    if not has_screenshot:
        blockers.append("no screenshot evidence is present")
    if missing_images:
        blockers.append(f"{len(missing_images)} referenced screenshot(s) are missing or unsafe")
    lines.extend(["", "## Completion blockers", ""])
    lines.extend(f"- { _escape(blocker) }" for blocker in blockers) if blockers else lines.append("None.")
    return "\n".join(lines) + "\n", complete


def summarize(run_dir: str, report: str, video_manifest: str, cleanup_report: str,
              session: str, plan_gate: str) -> tuple[Path, bool]:
    root = Path(run_dir).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"--run-dir is not a directory: {run_dir}")
    output = root / "diagnostics.md"
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"refusing to overwrite {output}")
    report_path = _input_file(report, root, "--report")
    manifest_path = _input_file(video_manifest, root, "--video-manifest")
    cleanup_path = _input_path(cleanup_report, root, "--cleanup-report")
    content, complete = _summary(root, report_path, manifest_path, cleanup_path, session, plan_gate)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(output, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)
    return output, complete


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="existing headed runner JSON report")
    parser.add_argument("--video-manifest", required=True, help="existing screen recorder manifest")
    parser.add_argument("--cleanup-report", required=True,
                        help="run-local wrapper attestation from exact owned PID/PGID checks")
    parser.add_argument("--run-dir", required=True, help="run directory that contains both inputs")
    parser.add_argument("--session", required=True, help="short session label for the report")
    parser.add_argument("--plan-gate", required=True, help="plan gate ID or title")
    args = parser.parse_args(argv)
    try:
        output, complete = summarize(args.run_dir, args.report, args.video_manifest, args.cleanup_report,
                                     args.session, args.plan_gate)
    except (OSError, ValueError) as exc:
        print(f"step6 evidence summary failed: {exc}", file=sys.stderr)
        return 2
    print(output)
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
