#!/usr/bin/env python3
"""Stage 2 of the forehead-plane Base placement: connected confirmation.

Host-side orchestrator (simulation only). Stage 1 (kinematic IK preflight,
``dentobot_workflow.base_placement_search``) ranks Base candidates. For the top
N spatially distinct candidates this script runs the existing headed
full-chain flow once each, through every production gate:

    Accept Base (offset) -> Task Home -> workspace -> PreEntry IK with
    collisions -> P1/P2/P3 diagnostics -> Plan Approach -> stopped preview

and classifies each outcome so the remaining blocker can be attributed:

    full_chain_pass         placement was the culprit and is resolved
    base_acceptance_failed  Step 6.1 acceptance problem
    preentry_ik_unreachable kinematic reach (placement/design)
    preentry_collision      endpoints reachable but colliding (collision)
    planner_failed:<stage>  valid endpoints, planner/route failed (planner)
    other_failure           anything else (see run report)

Runs are serialized: the script refuses to launch while any Slicer/MoveIt/
collision_guard process is active in the container. It never saves a case.
"""

from __future__ import annotations

import argparse
import glob
import io
import json
import math
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "DENTOWorkflow/Resources/Python"))

from dentobot_workflow import base_placement_search as search  # noqa: E402

CONTAINER = "dentobot-slicerros2"
TEMPLATE_FILES = (
    "container-transaction.bash", "run-in-container.bash", "launch-container.bash",
    "launch-gdb.bash", "gdb-events.py", "gdb-hooks.gdb", "faulthandler-wrapper.py",
    "validate-recording.py", "host-provenance.json",
)
OFFSET_ENV = "DENTOBOT_HEADED_BASE_OFFSET_RAS_MM"
GDB_SIGUSR1_LINE = "handle SIGUSR1 nostop noprint pass"


def faulthandler_wrapper_text(container_run_root: str, container_testing_dir: str) -> str:
    """Slicer --python-script wrapper for headed runs (generated, never copied).

    2026-10-03: r16 crashed with SIGSEGV inside the periodic
    ``faulthandler.dump_traceback_later`` watchdog thread
    (``_Py_DumpTracebackThreads`` reads other threads' frames without the GIL).
    Stacks are now dumped only on demand (SIGUSR1 from
    ``step6_run_stall_watch.py`` after a confirmed stall). The wrapper writes
    its own PID so the stall watcher signals only this run's Slicer.
    """
    return f'''import faulthandler
import os
import runpy
import signal
import sys
from pathlib import Path

root = Path({container_run_root!r})
handle = (root / "faulthandler.log").open("w", buffering=1)
faulthandler.enable(file=handle, all_threads=True)
# On-demand all-thread stacks only; no periodic dump_traceback_later (r16 SIGSEGV).
faulthandler.register(signal.SIGUSR1, file=handle, all_threads=True, chain=False)
(root / "slicer.pid").write_text(str(os.getpid()) + "\\n")
print("DENTOBOT_EXPLICIT_FAULTHANDLER_READY", flush=True)
testing = Path({container_testing_dir!r})
sys.path.insert(0, str(testing))
runpy.run_path(str(testing / "run_dentobot_step6_headed_review.py"), run_name="__main__")
'''


def ensure_gdb_sigusr1(text: str) -> str:
    """gdb must pass SIGUSR1 to Slicer without stopping it (hook-stop would capture)."""
    lines = [line for line in text.splitlines() if line.strip() != GDB_SIGUSR1_LINE]
    return "\n".join([GDB_SIGUSR1_LINE, *lines]) + "\n"


def forehead_frame_from_case(case_path: Path) -> np.ndarray:
    outer = zipfile.ZipFile(case_path)
    for name in outer.namelist():
        if not name.endswith(".mrb"):
            continue
        inner = zipfile.ZipFile(io.BytesIO(outer.read(name)))
        for member in inner.namelist():
            if member.endswith(".mrml"):
                text = inner.read(member).decode("utf-8", "replace")
                values = {}
                for key in ("ForeheadOriginMm", "ForeheadX", "ForeheadY", "ForeheadZ"):
                    match = re.search(r"DENTOBOT\." + key + r":([-0-9.,e]+)", text)
                    if not match:
                        raise ValueError(f"case has no stored forehead attribute {key}")
                    values[key] = np.array([float(v) for v in match.group(1).split(",")])
                frame = np.eye(4)
                frame[:3, 0], frame[:3, 1], frame[:3, 2] = (values["ForeheadX"],
                                                            values["ForeheadY"], values["ForeheadZ"])
                frame[:3, 3] = values["ForeheadOriginMm"]
                return frame
    raise ValueError("case has no scene MRB")


def task_from_evidence(evidence: dict, chain: search.Chain):
    probe = evidence["items"]["full_chain_interruption"]["probe_evidence"]
    session = probe["preentry_diagnostic_session"]
    conditioning = session["full_task_outcome"]["target_conditioning"]
    home = session["candidate_records"][0]["seed_joint_positions_si"]
    text = json.dumps(evidence)
    start = text.find('"accepted_matrix_world_ras_mm": [')
    matrix = json.loads(text[start + len('"accepted_matrix_world_ras_mm": '):].split("]", 1)[0] + "]")
    task = search.PlacementTask(
        np.array(conditioning["pre_entry_world_ras_mm"]),
        np.array(conditioning["entry_world_ras_mm"]),
        np.array(conditioning["target_world_ras_mm"]),
        [float(home[name]) for name in chain.names],
    )
    return task, np.array(matrix).reshape(4, 4)


def distinct_candidates(ranked: list[dict], count: int, separation_mm: float) -> list[dict]:
    chosen = []
    for record in ranked:
        if all(math.hypot(record["u_mm"] - c["u_mm"], record["v_mm"] - c["v_mm"]) >= separation_mm
               for c in chosen):
            chosen.append(record)
        if len(chosen) == count:
            break
    return chosen


def runtime_idle() -> bool:
    out = subprocess.run(
        ["docker", "exec", CONTAINER, "bash", "-c",
         "ps -eo comm | grep -Eic 'SlicerApp|move_group|collision_guard' || true"],
        capture_output=True, text=True, check=False,
    )
    return out.stdout.strip() == "0"


def prepare_run(template: Path, run_dir: Path, offset: list[float], checkout: Path, note: str,
                straight_path_check: bool = False) -> None:
    run_dir.mkdir(mode=0o700)
    for name in TEMPLATE_FILES:
        shutil.copy2(template / name, run_dir / name)
    status = subprocess.run(["git", "-C", str(checkout), "status", "--porcelain=v1"],
                            capture_output=True, text=True, check=True).stdout
    import hashlib
    status_sha = hashlib.sha256(status.encode()).hexdigest()
    offset_text = ",".join(f"{v:.9f}" for v in offset)
    for name in TEMPLATE_FILES:
        path = run_dir / name
        if path.suffix not in (".bash", ".py", ".gdb"):
            continue
        text = path.read_text().replace(template.name, run_dir.name)
        text = re.sub(r"DENTOBOT_HEADED_GIT_STATUS_SHA256=.*",
                      f"DENTOBOT_HEADED_GIT_STATUS_SHA256={status_sha}", text)
        text = re.sub(rf"{OFFSET_ENV}=.*", f"{OFFSET_ENV}={offset_text}", text)
        if path.name == "run-in-container.bash" and straight_path_check \
                and "DENTOBOT_HEADED_P1_STRAIGHT_PATH_CHECK" not in text:
            text = text.replace(f"export {OFFSET_ENV}=",
                                "export DENTOBOT_HEADED_P1_STRAIGHT_PATH_CHECK=1\n"
                                f"export {OFFSET_ENV}=", 1)
        path.write_text(text)
        path.chmod(0o755 if path.suffix == ".bash" else 0o644)
    (run_dir / "faulthandler-wrapper.py").write_text(faulthandler_wrapper_text(
        f"/workspace/data/dentobot-runs/{run_dir.name}",
        f"/workspace/ros2_ws/src/{Path(checkout).resolve().name}/Testing",
    ))
    hooks = run_dir / "gdb-hooks.gdb"
    hooks.write_text(ensure_gdb_sigusr1(hooks.read_text()))
    provenance = json.loads((run_dir / "host-provenance.json").read_text())
    provenance.update(run=run_dir.name, status_sha256=status_sha, base_offset_ras_mm=offset, note=note)
    (run_dir / "host-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


def classify(report: dict) -> tuple[str, str]:
    items = report.get("items", {})
    base = items.get("base_acceptance_trial", {})
    if base.get("status") == "FAIL":
        return "base_acceptance_failed", str(base.get("reason", ""))[:300]
    chain = items.get("full_chain_interruption", {})
    if chain.get("status") == "PASS":
        return "full_chain_pass", ""
    if chain.get("status") != "FAIL":
        first = next((k for k, v in items.items() if v.get("status") == "FAIL"), "unknown")
        return "other_failure", f"first failing item: {first}"
    reason = str(chain.get("reason", ""))
    evidence = chain.get("probe_evidence") or {}
    session = evidence.get("preentry_diagnostic_session") or {}
    records = session.get("candidate_records") or []
    if "PreEntry IK produced no collision-checked endpoint" in reason:
        colliding = [r for r in records if r.get("collision_check_status") == "colliding"
                     or r.get("termination_reason") == "colliding"]
        return ("preentry_collision" if colliding else "preentry_ik_unreachable"), reason[:300]
    for stage in ("P1", "P2", "P3"):
        outcome = (evidence.get("diagnostic_sessions") or {}).get(stage) or {}
        for stage_outcome in outcome.get("stage_outcomes") or []:
            if str(stage_outcome.get("status")) == "Failed":
                detail = str(stage_outcome.get("reason", ""))[:300]
                checks = evidence.get("p1_straight_path_checks") or []
                if stage == "P1" and checks:
                    codes = {c.get("code") for c in checks}
                    if codes == {"straight_path_clear"}:
                        return "planner_fault_confirmed:P1", "straight joint path clear; " + detail
                    if "straight_path_blocked" in codes and "straight_path_clear" not in codes:
                        return "p1_path_collision", "straight joint path blocked; " + detail
                return f"planner_failed:{stage}", detail
    return "other_failure", reason[:300]


def overall(results: list[dict]) -> str:
    kinds = [r["classification"] for r in results]
    if any(k == "full_chain_pass" for k in kinds):
        return "placement_resolved: at least one Base passes the full chain"
    if kinds and all(k == "planner_fault_confirmed:P1" for k in kinds):
        return "planner_fault_confirmed: straight Home->PreEntry path is clear at every tested Base, planner still fails"
    if kinds and all(k == "p1_path_collision" for k in kinds):
        return "p1_path_collision: straight Home->PreEntry path collides at every tested Base"
    if kinds and all(k.startswith(("planner_failed", "planner_fault_confirmed")) for k in kinds):
        return "planner_fault_likely: valid collision-free endpoints at every tested Base, planner fails"
    if kinds and all(k == "preentry_collision" for k in kinds):
        return "collision_blocker: endpoints reachable but colliding at every Base"
    if kinds and all(k == "preentry_ik_unreachable" for k in kinds):
        return "reach_or_design: kinematic preflight disagrees with native IK"
    return "mixed: see per-candidate classifications"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence", type=Path, required=True, help="headed-run evidence JSON (task + accepted Base)")
    parser.add_argument("--case", type=Path, required=True, help="source .dentocase with the stored forehead plane")
    parser.add_argument("--template-run", type=Path, required=True, help="previous run dir with wrapper scripts")
    parser.add_argument("--out", type=Path, required=True, help="new confirmation directory")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--separation-mm", type=float, default=4.0)
    parser.add_argument("--timeout-sec", type=int, default=1800)
    parser.add_argument("--dry-run", action="store_true", help="stage 1 + run preparation only")
    parser.add_argument("--p1-straight-path-check", action="store_true",
                        help="on P1 failure, test the straight Home->PreEntry joint path")
    parser.add_argument("--depth-fallback", action="store_true",
                        help="unlock depth +-10 mm if the in-plane search finds nothing")
    args = parser.parse_args()

    checkout = ROOT
    chain = search.Chain.from_urdf(ROOT / "dentobot_description/urdf/dentobot.urdf")
    evidence = json.loads(args.evidence.read_text())
    task, accepted = task_from_evidence(evidence, chain)
    frame = forehead_frame_from_case(args.case)
    # Reference = current accepted Base so each candidate differs only by an
    # in-plane translation, which the headed runner applies via production
    # Base review (orientation stays locked).
    stage1 = (search.search_with_depth_fallback(chain, frame, accepted, task)
              if args.depth_fallback else
              search.search_forehead_base_placement(chain, frame, accepted, task))
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "stage1_search.json").write_text(json.dumps(stage1, indent=2, default=float) + "\n")
    picks = distinct_candidates(stage1["ranked"] if stage1["ranked"] else [], args.top, args.separation_mm)
    if not picks:
        print("Stage 1 found no feasible Base; nothing to confirm.")
        (args.out / "confirmation.json").write_text(json.dumps(
            {"verdict": stage1["verdict"], "results": []}, indent=2) + "\n")
        return 2

    results = []
    for index, pick in enumerate(picks, start=1):
        matrix = np.array(pick["matrix_world_ras_mm"]).reshape(4, 4)
        offset = (matrix[:3, 3] - accepted[:3, 3]).tolist()
        run_dir = args.template_run.parent / f"{args.out.name}-c{index}"
        prepare_run(args.template_run, run_dir, offset, checkout,
                    f"stage-2 confirmation candidate {index}: u={pick['u_mm']} v={pick['v_mm']} mm",
                    straight_path_check=args.p1_straight_path_check)
        entry = {"candidate": index, "u_mm": pick["u_mm"], "v_mm": pick["v_mm"],
                 "offset_ras_mm": offset, "stage1_min_slider_margin_mm": pick["minimum_slider_margin_mm"],
                 "run_dir": str(run_dir)}
        if args.dry_run:
            entry["classification"] = "not_run"
            results.append(entry)
            continue
        if not runtime_idle():
            entry.update(classification="not_run", detail="runtime busy; refused to launch")
            results.append(entry)
            break
        subprocess.run(["bash", str(run_dir / "launch-container.bash")], check=True)
        deadline = time.monotonic() + args.timeout_sec
        while time.monotonic() < deadline and not (run_dir / "transaction-status.json").exists():
            time.sleep(10)
        reports = sorted(glob.glob(str(run_dir / "evidence/step6_headed_review_*.json")))
        if not reports:
            entry.update(classification="other_failure", detail="no runner report")
        else:
            kind, detail = classify(json.loads(Path(reports[0]).read_text()))
            entry.update(classification=kind, detail=detail)
        entry["transaction_finished"] = (run_dir / "transaction-status.json").exists()
        results.append(entry)
        print(json.dumps({k: entry[k] for k in ("candidate", "u_mm", "v_mm", "classification")}))
        if not entry["transaction_finished"]:
            break  # never start another run while one may still be active
    summary = {"stage1_verdict": stage1["verdict"], "stage1_feasible": stage1["feasible_count"],
               "stage1_evaluated": stage1["evaluated"], "results": results, "verdict": overall(results)}
    (args.out / "confirmation.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["# Base placement connected confirmation", "", f"Verdict: **{summary['verdict']}**", "",
             "| # | u mm | v mm | classification | detail |", "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['candidate']} | {r['u_mm']:.1f} | {r['v_mm']:.1f} | {r['classification']} | "
                     f"{str(r.get('detail', ''))[:120]} |")
    (args.out / "confirmation.md").write_text("\n".join(lines) + "\n")
    print(summary["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
