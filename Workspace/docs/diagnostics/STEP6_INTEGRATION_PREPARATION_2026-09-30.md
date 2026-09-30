# Step 6 integration preparation — 2026-09-30

Operator direction: prepare integration ahead of renovation completion and
refresh the existing integration checkout with latest renovation work.
Existing owners: S6-LIVE-01, S6-P2-03, S6-REUSABLE-CASE-SETUP; Tarun explicitly confirms integrating accepted 5.10 fixes and retaining the
PLAT-U-06 deferral. No actual Slicer 5.12 runtime promotion is in scope.

## Current comparison

Renovation HEAD: `0186410`; integration HEAD: `c1bfba0`; performance HEAD:
`6c17425`. Integration HEAD is an ancestor of renovation, but its working
changes include independent selected fixes. A preliminary file-level
three-way comparison using integration HEAD as base found 13 conflicts,
15 automatic textual merges, four integration-only changes, five differing
files newly added in both trees, and 60 renovation-only differences. Counts
are an inspection snapshot, not acceptance or a frozen-source guarantee.
Automatic textual merges still need semantic review.

## Integration contract

Use renovation as the Step 6 behavior baseline. Preserve reviewed independent
5.10 performance/restore fixes from integration. First capture a fixed source
checkpoint and preserve integration's dirty changes and untracked development
files; exclude engineer-owned artifacts, generated output and local data.
Resolve current overlaps once, then refresh against successive identified
renovation checkpoints rather than replacing whole trees. Preserve request/
session/policy correlation, uncertainty latches, J1–J5 boundaries, strict
restore integrity and current native provenance. Controlled task records use
the latest explicit decisions; old task rows are not blindly merged.

A checkpoint commit may capture unfinished source without declaring the
feature accepted. Pending runtime/operator gates remain in the canonical
backlog. Avoid committing active files while another agent is editing them;
coordinate an implementation checkpoint before transfer.

After code reconciliation, run only focused checks selected from the
verification matrix under its execution gates. Reuse existing evidence only
where source/native/runtime identity matches. Select a representative combined
acceptance run for boundaries affected by both workstreams, serialize runtime,
and retain manual-verdict gates. Main promotion follows acceptance; do not
promote the mixed performance branch wholesale while 5.12 remains deferred.

No development source was copied or merged during this preparation. The
comparison and tentative merge outputs are under
`/tmp/dentobot-integration-prep-20260930/`; they are disposable review inputs,
not a deployable integration tree or full backup.

## Overlaps requiring review

- `DENTOWorkflow/Resources/Python/DENTORobotSimulationPanel.py` — conflict
- `DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py` — conflict
- `DENTOWorkflow/Resources/Python/dentobot_workflow/widget_case_backend.py` — conflict
- `DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot.py` — conflict
- `DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot_shell.py` — conflict
- `DENTOWorkflow/Resources/Python/dentobot_workflow/widget_segmentation.py` — integration_only
- `DENTOWorkflow/Resources/Python/dentobot_workflow/widget_view_catalog.py` — integration_only
- `Testing/run_dentobot_step6_headed_review.py` — both_changed
- `Testing/step6_historical_record_probe.py` — both_changed
- `Testing/test_case_bundle.py` — conflict
- `Testing/test_case_foundation_fingerprint_cache.py` — integration_only
- `Testing/test_robot_manual_jog_ui.py` — conflict
- `Testing/test_robot_workflow_facade.py` — conflict
- `Testing/test_step6_connect_render_source.py` — integration_only
- `Testing/test_step6_headed_review_source.py` — both_changed
- `Testing/test_step6_historical_record_probe.py` — both_changed
- `Testing/test_step6_state.py` — conflict
- `Testing/verification_matrix.json` — conflict
- `Workspace/docs/DECISIONS.md` — conflict
- `Workspace/docs/TASKS.md` — conflict
- `Workspace/docs/backlog.md` — conflict
- `Workspace/docs/logbook/2026-09-28.md` — both_changed
