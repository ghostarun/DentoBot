#!/usr/bin/env python3
"""Host-side visual evidence report for one headed Step 6 run directory.

Writes, inside the run directory (never overwriting existing files):
  recording/<video>.mp4      lossless stream copy of the MKV for easy viewing
  evidence/frames/*.png      labelled video frames at every recorded item
                             time and at the failure moment (VIDEO FRAMES, not
                             state-matched screenshots)
  cleanup.json               attestation from a container process check
  diagnostics.md             items table, first failure, new-feature evidence
                             (Find Reachable Base, mouth portal, Entry
                             contact, drilling truncation), screenshots,
                             frames and video links

Then calls the existing Testing/summarize_step6_evidence.py when possible.
Simulation evidence only; operator verdict stays PENDING.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import subprocess
from pathlib import Path

CONTAINER = "dentobot-slicerros2"


def _utc(text):
    return dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))


def _active_runtime_count() -> int:
    out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                          "ps -eo comm | grep -Eic 'SlicerApp|move_group|collision_guard' || true"],
                         capture_output=True, text=True, check=False).stdout.strip()
    return int(out or "0")


def _frame(video: Path, seconds: float, out: Path) -> bool:
    if out.exists():
        return True
    out.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["ffmpeg", "-loglevel", "error", "-n", "-ss", f"{max(0.0, seconds):.2f}",
                             "-i", str(video), "-frames:v", "1", str(out)], check=False)
    return result.returncode == 0 and out.exists()


def _summary(result) -> str:
    if not isinstance(result, dict):
        return str(result)[:120]
    keys = ("passed", "error", "elapsed_sec", "status_state", "completed_depth_mm", "selected",
            "mean_wait_ms", "stopping")
    return ", ".join(f"{k}={result[k]}" for k in keys if k in result)[:240]


def session_evidence(run: Path, start, video):
    """Session-mode commands (operator 2026-10-02 checkpoint + command inbox).

    The runner's item table stops at the checkpoint; checks driven through the
    command inbox are reported from ``session/outbox`` with their state-matched
    captures and a video frame at each capture time.
    """
    records = []
    for path in sorted((run / "session" / "outbox").glob("*.json")):
        try:
            records.append(json.loads(path.read_text()))
        except (OSError, ValueError):
            continue
    if not records:
        return [], []
    lines = ["", "## Session commands", "", "| command | status | duration s | result |", "|---|---|---|---|"]
    for record in records:
        lines.append(f"| {record.get('command')} | {record.get('status')} | {record.get('duration_sec')} | "
                     f"{_summary(record.get('result'))} |")
    frames = []
    for record in records:
        evidence = (record.get("result") or {}).get("evidence") if isinstance(record.get("result"), dict) else None
        captures = (evidence or {}).get("captures") or []
        if not captures:
            continue
        lines += ["", f"### {record.get('command')} timeline", "",
                  "| stage | UTC | screenshot | viewport | video frame |", "|---|---|---|---|---|"]
        for capture in captures:
            shot = capture.get("result") or {}
            stamp = shot.get("captured_at_utc")
            frame = ""
            if video is not None and start is not None and stamp:
                seconds = (_utc(stamp) - start).total_seconds()
                out = run / "evidence/frames" / f"t{seconds:07.1f}s-session-{capture.get('stage')}.png"
                if _frame(video, seconds, out):
                    frames.append((seconds, f"session-{capture.get('stage')}", out))
                    frame = f"[frame]({out.relative_to(run)})"
            links = [f"[png](evidence/{shot[k]})" if shot.get(k) else "" for k in ("ui", "viewport")]
            lines.append(f"| {capture.get('stage')} | {str(stamp or '')[11:19]} | {links[0]} | {links[1]} | {frame} |")
    return lines, frames


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--session", default="Claude S6-LIVE-01 verification")
    parser.add_argument("--plan-gate", default="S6-LIVE-01")
    args = parser.parse_args()
    run = args.run_dir.resolve()
    report_path = Path(sorted(glob.glob(str(run / "evidence/step6_headed_review_*.json")))[0])
    report = json.loads(report_path.read_text())
    manifests = sorted(glob.glob(str(run / "recording/*.manifest.json")))
    manifest = json.loads(Path(manifests[0]).read_text()) if manifests else {}
    videos = sorted(glob.glob(str(run / "recording/*.mkv")))
    video = Path(videos[0]) if videos else None

    mp4 = None
    if video is not None:
        mp4 = video.with_suffix(".mp4")
        if not mp4.exists():
            subprocess.run(["ffmpeg", "-loglevel", "error", "-n", "-i", str(video), "-c", "copy", str(mp4)],
                           check=False)

    cleanup = run / "cleanup.json"
    active = _active_runtime_count()
    if not cleanup.exists():
        cleanup.write_text(json.dumps({
            "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "container_runtime_process_count": active,
            "owned_process_cleanup": active == 0,
            "remaining_owned_processes": [] if active == 0 else ["runtime processes still present"],
        }, indent=2) + "\n")

    items = report.get("items", {})
    start = _utc(manifest["started_at_utc"]) if manifest.get("started_at_utc") else None
    frames = []
    if video is not None and start is not None:
        for name, item in items.items():
            stamp = item.get("recorded_at_utc")
            if not stamp or item.get("status") == "NOT_RUN":
                continue
            seconds = (_utc(stamp) - start).total_seconds()
            label = f"{item['status'].lower()}-{name}"
            out = run / "evidence/frames" / f"t{seconds:07.1f}s-{label}.png"
            if _frame(video, seconds, out):
                frames.append((seconds, label, out))
        failed = [(n, i) for n, i in items.items() if i.get("status") == "FAIL"]
        if failed and failed[0][1].get("recorded_at_utc"):
            seconds = (_utc(failed[0][1]["recorded_at_utc"]) - start).total_seconds()
            for delta in (-5.0, -1.0):
                out = run / "evidence/frames" / f"t{seconds + delta:07.1f}s-before-failure.png"
                if _frame(video, seconds + delta, out):
                    frames.append((seconds + delta, "before-failure", out))
    frames.sort()

    counts = {}
    for item in items.values():
        counts[item.get("status")] = counts.get(item.get("status"), 0) + 1
    probe = (items.get("full_chain_interruption") or {}).get("probe_evidence") or {}
    lines = [
        f"# {run.name} — diagnostics", "",
        f"Session: {args.session}. Plan gate: {args.plan_gate}. Operator verdict: **PENDING**.", "",
        f"Runner status **{report.get('status')}** — {counts}.",
        f"First failure / stop: {report.get('failure_or_stop_reason') or 'none'}", "",
        f"Recording: status `{manifest.get('status')}`, {manifest.get('started_at_utc')} → "
        f"{manifest.get('ended_at_utc')}; MKV `{video.relative_to(run) if video else None}`; "
        f"MP4 `{mp4.relative_to(run) if mp4 and mp4.exists() else None}`.",
        f"Cleanup: runtime processes after run = {active}.", "",
        *(["Session mode: items after the checkpoint show NOT_RUN in the runner table; the checks run "
           "through the command inbox are under **Session commands** below.", ""]
          if report.get("status") == "SESSION_END" else []),
        "## Items", "", "| item | status | reason |", "|---|---|---|",
    ]
    for name, item in items.items():
        lines.append(f"| {name} | {item.get('status')} | {str(item.get('reason') or '')[:140]} |")
    lines += ["", "## New-feature evidence", ""]
    lines.append("- Find Reachable Base: `" + json.dumps(report.get("find_reachable_base"), default=str)[:900] + "`")
    lines.append("- Drilling truncation: `" + json.dumps(report.get("drilling_truncation"), default=str)[:900] + "`")
    for stage, session in (probe.get("diagnostic_sessions") or {}).items():
        for outcome in session.get("stage_outcomes") or []:
            endpoint = outcome.get("endpoint_evidence") or {}
            lines.append(f"- {stage} {outcome.get('stage')}: {outcome.get('status')} "
                         f"({outcome.get('waypoint_count')} waypoints) — {str(outcome.get('reason'))[:200]}")
            gate = endpoint.get("mouth_portal_gate")
            if gate:
                teeth = gate.get("vertex_teeth") or {}
                lines.append(f"  - mouth portal gate: {gate.get('status')} {gate.get('reason') or ''} "
                             f"(edges {gate.get('edge_mode')}, gum-line height "
                             f"{teeth.get('opening_height_gum_line_mm')}, cusp-tip height "
                             f"{teeth.get('opening_height_cusp_tips_mm')}, gum sources "
                             f"{teeth.get('gum_line_sources')})")
            collision = (endpoint.get("endpoint_fk") or {}).get("collision")
            if collision and collision.get("status") == "allowed_contact":
                lines.append(f"  - Entry/drilling allowed contact: {collision.get('pairs')}")
    checks = probe.get("p1_straight_path_checks") or []
    if checks:
        lines.append(f"- P1 straight-path checks: {[c.get('code') for c in checks]} — {checks[0].get('message')}")
    session_lines, session_frames = session_evidence(run, start, video)
    lines += session_lines
    frames = sorted(frames + session_frames)
    lines += ["", "## State-matched screenshots", ""]
    for shot in sorted(glob.glob(str(run / "evidence/*-ui.png"))):
        rel = Path(shot).relative_to(run)
        lines.append(f"- [{rel.name}]({rel})")
    lines += ["", "## Video frames (labelled by recording time; not state-matched)", ""]
    for seconds, label, out in frames:
        rel = out.relative_to(run)
        lines.append(f"![{label} at {seconds:.1f}s]({rel})")
    target = run / "diagnostics.md"
    if target.exists():
        target = run / "diagnostics-visual.md"
    target.write_text("\n".join(lines) + "\n")

    summarizer = Path(__file__).with_name("summarize_step6_evidence.py")
    if manifests and summarizer.exists():
        subprocess.run(["python3", str(summarizer), "--report", str(report_path),
                        "--video-manifest", manifests[0], "--cleanup-report", str(cleanup),
                        "--run-dir", str(run), "--session", args.session, "--plan-gate", args.plan_gate],
                       check=False, capture_output=True)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
