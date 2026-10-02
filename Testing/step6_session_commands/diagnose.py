# Diagnose This Base (S6-BASE-DIAGNOSE) through the production button.
widget._configureRobotSimulationShellSubstep(3)
widget._updateStep6PlanningUi()
_show_step63_view(panel, 2, 0)
_run_base_diagnosis(widget, panel, facade, report, evidence_dir, run_id)
result = report["items"].get("base_diagnosis")
