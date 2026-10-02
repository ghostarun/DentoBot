# Per-candidate Plan Approach evidence (operator 2026-10-03): stage results,
# drilling depth/truncation, post-PreEntry arm motion and the selected index.
import json as _json

session = _json.loads(str(parameter_node.step6MotionDiagnosticJson or "{}"))
keep = ("status", "fraction", "cost", "truncat", "roll", "guide", "selected", "index", "route", "reason", "depth")
rows = []
for record in session.get("candidate_records") or ():
    rows.append({k: v for k, v in record.items() if any(part in k for part in keep)})
result = {
    "candidate_count": len(rows),
    "candidate_evaluation": getattr(facade, "_candidate_evaluation", None),
    "selected": (session.get("full_task_outcome") or {}).get("selected_candidate_index"),
    "full_task_outcome_keys": sorted((session.get("full_task_outcome") or {}).keys()),
    "candidates": rows,
}
