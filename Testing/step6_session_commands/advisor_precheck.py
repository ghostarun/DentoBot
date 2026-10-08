# S6-ADVISOR-GUI-01 bounded B verification (decision D1/O4): READ-ONLY preconditions + invariant snapshot.
# Changes nothing: no click, no owner call except reads. Any unmet precondition STOPS the run (no recovery attempt).
import json
import step6_advisor_probe as probe

widget._configureRobotSimulationShellSubstep(3)
widget._updateStep6PlanningUi()
_process_events(0.3)
snapshot = probe.invariant_snapshot(logic, facade, parameter_node, label="advisor-precheck")
problems = []
if not snapshot["ros_active"]:
    problems.append("ROS/MoveIt is not connected")
if not snapshot["base_locked"]:
    problems.append("the Base is not accepted/locked")
if snapshot["home_validation_gap"]:
    problems.append("Task Home is not runtime-validated: " + snapshot["home_validation_gap"])
problems += ["joint identity: " + text for text in probe.joints_equal_saved(snapshot)]
if (facade.manualTaskHomeReview().details or {}).get("staged"):
    problems.append("a Task Home review is already staged")
if snapshot["barrier_tuning"] != [2.0, 8.0, 5.0] or snapshot["barrier_edge_mode"] != "gum_line":
    problems.append("the mouth barrier is not at its production defaults")
if snapshot["spindle_allowance"] or snapshot["corridor_margin_samples"] != 0:
    problems.append("a guard setting is not at its default (allowance/corridor margin)")
_capture(report, evidence_dir, run_id, "advisor-precheck")
(evidence_dir / f"{run_id}-advisor-snapshot-precheck.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
result = {"snapshot": snapshot, "problems": problems, "nothing_changed": True}
if problems:
    raise RuntimeError("advisor precheck failed (nothing was changed): " + "; ".join(problems))
