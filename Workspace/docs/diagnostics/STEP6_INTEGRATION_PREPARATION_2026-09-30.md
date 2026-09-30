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

## Approved-plan execution — 2026-09-30

Tarun requested implementation of the detailed integration plan. Renovation was briefly frozen after both helper workers completed, captured in **e7cd29f**, verified clean, and released for further source development. Original dirty integration was preserved in **243e3a1**. Backup refs are `backup/step6-renovation-source-20260930` and `backup/step6-integration-pre-refresh-20260930`. These are unaccepted source checkpoints. The combined candidate merges immutable e7cd29f; later renovation edits are outside this pass.

The actual Git merge produced **19 conflict paths**, including add/add runner and logbook conflicts. Four GPT-6 Luna Max scopes have exclusive ownership; workers 1–3 run concurrently, worker 4 uses the first released slot. Coordinator owns records, runners, matrix, Git/build/runtime and acceptance. No worker imports tests while peers edit. Generated PDF output is excluded from the candidate. Latest renovation records govern current policy; distinct earlier integration logbook headings are retained as explicitly historical evidence.

### Coordinator change dispositions

| Source | Disposition / required behavior |
|---|---|
| `2c8e009` | preserve existing accepted port; reconcile against newer renovation |
| `e27820e` | preserve existing accepted port; reconcile against newer renovation |
| `93a6e33` | preserve existing accepted port; reconcile against newer renovation |
| `caa155b` | preserve existing accepted port; reconcile against newer renovation |
| `56f6c31` | preserve existing accepted port; reconcile against newer renovation |
| `6158d90` | preserve existing accepted port; reconcile against newer renovation |
| `5dd3b48` | preserve existing accepted port; reconcile against newer renovation |
| `502fbb1` | preserve existing accepted port; reconcile against newer renovation |
| `c7a5396` | preserve existing accepted port; reconcile against newer renovation |
| `7eb9e41` | preserve existing accepted port; reconcile against newer renovation |
| `e7b00b3` | preserve existing accepted port; reconcile against newer renovation |
| `d47c122` | port only missing production/test hunks after frozen comparison |
| `a533e78` | port only missing production/test hunks after frozen comparison |
| `9f301c5` | port only missing production/test hunks after frozen comparison |
| `9632cc7` | port only missing production/test hunks after frozen comparison |
| `edc3a2e` | equivalent newer renovation precision correction; do not replay older tolerance hypothesis |
| `48e0f49` | retain reversal of unsupported tolerance experiment |
| `PLAT-U-06` | deferred: no 5.12 image, full SuperBuild, release pins or native fork wholesale promotion |

### Verification and promotion boundary

Use the cheapest relevant host checks once source is stable, then the approved isolated integration build and bounded restore/Connect, inventory and shell checks if resource ownership and causal retry gates permit. Current runtime remains Slicer 5.10. The current recorded bounded r22 workbench pass does not accept planner/preview/repeat or final new-case/reopen. Final renovation incorporation, full combined acceptance, Tarun verdict and main promotion remain pending under existing task IDs. The sole pending queue remains backlog.md.

### Reviewed combined source dispositions

Workers completed and froze all four scopes. Coordinator inspected their diffs against immutable e7cd29f. Robot panel/state/façade/manual-jog tests retain exact renovation behavior. Accepted Connect wrappers restore suppression in `finally`, render batches resume on failures, collision proxy publication preserves identity. Restore now has one generation through queued events, hydration, strict post-hydration audit and transactional fallback; exact saved pose/landmarks remain unchanged. Stage persistence, fingerprint input invalidation and contiguous buffer hashing retained. Missing d47c122 inventory cache/progress, a533e78 fitting fallback/shell progress, 9f301c5 bulk refresh and 9632cc7 late teardown hunks ported with four-argument inventory callbacks aligned.

The host review exposed outdated planning/whitespace assertions and stale API/install records. Coordinator reconciled the existing API signatures/removals to frozen renovation plus accepted progress interfaces and added five missing internal CMake install entries. No old motion owner was restored. A pre-existing 1600-line module-budget failure stays visible in backlog; its limit remains unchanged.

The original headed runner skipped Connect with all motion opt-ins off. A narrow integration-only `DENTOBOT_HEADED_CONNECT_ONLY=1` gate now requires native provenance, rejects every competing action/save opt-in, uses production Connect/scene-readback/Disconnect, verifies unchanged case hash and stops before workspace recovery. Its focused host gate checks reject invalid modes and competing actions. Matrix and existing recorded-run runbook index this boundary.

### Combined source and early runtime checkpoint

Merge `514f86e` incorporates e7cd29f. Focused host 601 PASS (one known size gate held visible), static/JSON/diff pass. Restore/Connect/Disconnect: 10 selected PASS, intentional PARTIAL workflow, clean process/recording exits, Tarun bounded verdict accepted. Inventory audit/candidate/source-mask/MRB/DentoCase PASS with clean exits. Step 5B preliminary synthetic assisted-endpoint fixture failed its current Case Foundation prerequisite before package load; shell/fusion NOT_RUN. Existing runner now has default-off saved-fixture-only mode, retaining strict package and geometry checks; another runtime needs Tarun’s direction. Detailed evidence: `data/dentobot-runs/step6-5.10-integration-20260930/diagnostics.md`. Graph overlay refreshed successfully after sandbox escalation. Final renovation, full combined acceptance, size cleanup and main remain pending.
