# Testing and verification script index — 2026-09-24

**Owner:** `DCP-00` foundations review. **Scope:** current development checkout
at `/home/light-tarun/dentobot/ros2_ws/src/DentoBot`. This is a reuse index,
not a test execution or acceptance record. Read the canonical
[`verification_matrix.json`](../../../Testing/verification_matrix.json) and
[`AGENTIC_VERIFICATION_PROTOCOL.md`](../AGENTIC_VERIFICATION_PROTOCOL.md)
before invoking a check. The matrix owns commands, resources, approval,
dependencies and pass conditions. Its entries do not record latest results.

## 9 October approved draft-disposal reuse evidence

Existing `run_dentobot_step6_headed_review.py` explicit `DENTOBOT_HEADED_DISCARD_STAGED_BASE=1` atddbad8e: production Cancel Review only after knowncurrentidentity, rawcandidate/acceptedstate preservation and firstfailure screenshots. DefaultOFF preserves pendingdraft. FourtargetedhostchecksPASS; actualAONECancelReviewPASS but Connectblocked/unlockedBase/noHome, advisorcommands NOT_RUNTIME_VERIFIED. ExactSHA/case/environment/invocation/outputs/limitations in retry20261008T220509Z launchreceipt/rawreport/diagnostics and9Octoberlogbook; no automationpromotion/fullfeatureacceptance. Same serializedresource/explicitruntime/unknownmodal/manualverdict gates; no duplicate runner.

## 9 October current A reuse evidence boundary

Existing headed runner/session reused on native A: narrow harness3562de5 fixes exact A per-SHA host binding and SESSION-only connection selection; production/native equal4736807. Four targeted host checks passed. Actual case-run stopped on staged Base prerequisite before Connect/advisor: session/advisor pieces remain NOT_RUNTIME_VERIFIED. Real26s video decoded/hashmatched/nonblack/changing, recording PARTIAL, no automation promotion/acceptance. Exact commands/results/artifacts in `data/dentobot-runs/2026-10-08/S6-ADVISOR-GUI-01-A-LIVE-20261008T185237Z/automation-01/diagnostics.md` and9October logbook. Visible:0 supersedes privateXvfb for this approved case; no unchangedtest rerun.

## 9 October — bounded S6-ADVISOR-GUI-01 reuse entries

Search-first reuse decision: compose the existing recorded headed runner/session,
private-Xvfb recorder, production restore/Connect, Diagnose owners and diagnostic
summarizer. No new workflow runner. Genuine coverage gaps were advisor-specific
consent/identity/owner-count observation, independent captured Cancel timing and
actual-video pixel acceptance; the bounded modules below fill these gaps. Commands,
resources, dependencies, approvals and pass conditions live in matrix routes
`pure.step6_advisor_session_host`, `runtime.step6_advisor_baseline_session`,
`runtime.step6_advisor_consented_trial_cancel`, plus existing `pure.screen_recorder`
and `runtime.step6_headed_review`. Matrix selection is never runtime permission.

| Script(s) under Testing/ | Purpose / invocation / output | Status and limits |
|---|---|---|
| `step6_session_commands/advisor_precheck.py` | Existing session inbox command; read-only identity/loaded-source checks, snapshots and first refusal. Run before baseline. | S6-ADVISOR-GUI-01; source/host-tested, NOT_RUNTIME_VERIFIED. UI navigation only, no repair or owner mutation. |
| `step6_session_commands/advisor_baseline.py` | Existing headed session command; real dialog/Start, consent OFF, baseline Diagnose, screenshot/report/timing/owner/restoration evidence. | NOT_RUNTIME_VERIFIED; serialized existing Slicer/ROS/domain/display, explicit runtime approval, manual outcome verdict. Safe blocked/no-solution is not successful configuration proof. |
| `step6_session_commands/advisor_consented_trials.py` | Separate approved continuation after baseline verdict; programmatic checkbox+More, production SAME-joints Base/Home trial, Cancel and restore ledger/snapshots. | NOT_RUNTIME_VERIFIED; scripted consent is not human-consent proof. No gate autoanswers; unexpected modal untouched. Explicit failing in-process fallback disclosed. Unknown commit never retried. |
| `step6_advisor_probe.py` | Imported by those commands; invariant snapshots/owner counts, temporary chained/restored actual-handler profile hook, timeline/failure retention and external-send timing bounds. | Host regressions only; no native responsiveness proof. Runtime wrappers declared before use; missing timing evidence fails measurement. |
| `advisor_cancel_helper.py` | `python3 … <session-dir> --display <private-display> --timeout-sec 900 --receipt-log <path>` in an independent process outside Slicer on B; one external X11 click/monotonic receipt. | NOT_RUNTIME_VERIFIED; Run B only, separately approved. Exact path mapping/tools/display access required, no Qt queued-intent substitution. |
| `step6_video_sanity.py` | `python3 -I … <actual-video> --manifest <manifest> --frames-dir <samples> --out <pixel-json>`; decode/hash/FPS/count/nonblack/changing-content gate. | Host/synthetic pixel-tested only; actual B recording NOT_RUNTIME_VERIFIED. Pixel gate plus manual visual verdict; screenshots/slideshow do not substitute. |

Latest evidence (not timeless PASS): production417f871 host checks/review and
metadata-only4736807 source comparison in
`data/dentobot-runs/2026-10-08/S6-ADVISOR-GUI-01-CONTINUE-20261008T140353Z/`
(`RECOVERY_CHECKPOINT.md`, `workers/LEDGER.md`, `checks/`). Case candidate is Oct4
FDI14 SHA c56d0e06…ad581; fresh B read-only preflight confirms bytes but proves no
native case execution. Runtime/operator acceptance absent. Before workflow
automation promotion, retain exact successful SHA/case/environment/commands/results/
artifacts and manual verdict; verify covered source/case/environment drift. No
unchanged suite rerun merely for indexing. Safety/retry/serialized-runtime gates
remain unchanged.

## 26 September renovation-checkout addendum

**27 September headed capture addendum:** The renovation checkout adds
`Testing/record_slicer_screen.py` (whole-display X11/FFmpeg recorder for an
automated command or opt-in operator session), its focused pure tests, and
`Testing/run_dentobot_step6_headed_review.py` for an itemized simulation-only
Step 6 GUI review. Matrix checks `pure.screen_recorder` and
`runtime.step6_headed_review` plus profile `step6-headed-review` index them;
the [recorded headed automation workflow](STEP6_RECORDED_HEADED_AUTOMATION_WORKFLOW.md)
gives the complete repeatable host/container/evidence procedure for agents
and a later operator manual;
the matrix now has **39 checks and 7 profiles**, including the bounded
`runtime.step6_integration_taskless_draft` checkpoint. The first recorded
current-case attempt was **blocked at package post-hydration validation**;
a later 27 September narrow integrated run reopened the corrected current
case and passed Connect/Disconnect but exited 1 on shutdown. Both are
partial evidence, not a whole-run recording. See the 27 September logbook
and the linked run diagnostics; video startup frames are not a case/UI
verdict. `Testing/summarize_step6_evidence.py` generates a run-local
planned-versus-observed report from runner JSON, video manifest and explicit
owned-process cleanup evidence, and fails closed on bounded/partial runs.
The recorder's `--until-enter`
mode lets an operator opt into screen capture of a manual simulation session.
The workbench's JSON manual-state record remains separate and authoritative
for motion/guard data; video alone never proves accepted robot state.

The inventory counts below are the 24 September snapshot. The current renovation
matrix includes `runtime.manual_jog_headless` (36 total checks): reuse
`Testing/run_dentobot_manual_jog_headless.bash` and `.py` for the bounded
simulation-only manual-jog check. It uses Xvfb-rendered Slicer and can capture
screenshots; without a reviewed rejection vector its result is at most PARTIAL.
It is not a planner/full-workbench or operator usability check. That older
launcher pins `45a38d9`, older than renovation HEAD `40ad290`; its exact
revision/provenance binding remains stale. Generic matrix container commands
naming `DentoBot` must not be mistaken for this renovation checkout. The later
headed review used the new exact-checkout entry above and stopped at
current-case integrity. See the [reconciled plan](STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md).

## Inventory boundary and decision rule

- `Testing/` contains **76 active Python/shell scripts**: 44 runners, 27
  `test_*.py` modules and 5 standalone Slicer test modules. Ten are currently
  **untracked** worktree additions; their availability is provisional. Two
  archived phantom scripts are excluded from active reuse.
- The matrix has **35 checks and 6 profiles**. It links 13 runners and 9 test
  modules directly; one matrix check invokes a `DENTOWorkflowTest` method.
  Remaining files can still be useful, but have no matrix command or approval
  metadata. A matrix profile selects candidate checks, not permission to run
  them all.
- Search this index and the matrix first. Reuse the smallest existing check
  that covers the same production behavior and case identity. If a script is
  diagnostic, case-specific, display-only or synthetic, retain that evidence
  boundary. Do not create a new runner merely because no single script spans
  the full workflow; first compose existing verified step checks in the
  approved sequence. A real coverage gap belongs to the existing step owner.

## Existing workflow coverage and first reuse choice

| Workflow slice | Existing first choices | Recorded boundary / gap |
|---|---|---|
| Inference/Bridge and Step 3 import | `run_ubuntu_bridge_a_health_test.py`, `run_mrml_nifti_roundtrip_test.py`, `run_slicerros2_imaging_bridge_test.py`, standalone Ubuntu bridge/import modules; `run_dentobot_segmentation_runs_smoke.py` | Bridge wrappers and Step 3 smoke are separate. No complete Step 0→3 production-path claim. |
| Step 2 pulp audit and Step 3 anatomy/opening | `run_dentobot_pulp_inventory_smoke.py`, its restore/bundle-reopen follow-ups, `run_dentobot_auto_open_mouth_smoke.py`, pure `test_pulp_inventory.py` and `test_virtual_open_mouth_articulator.py` | Sep-24 focused FDI11 subset and save/reopen passed; full 28-tooth bulk timed out. AUTO open-mouth has a recorded `test1_post` headless pass, not universal anatomy acceptance. |
| Steps 4A–5C preparation | `run_dentobot_pulp_shell_smoke.py`, `run_dentobot_stage6_target_generation.py`, `run_dentobot_reusable_case_smoke.py`, `run_dentobot_case13sept_fdi32_workflow_smoke.py`; focused pure tests | Each proves its stated target/step. `run_dentobot_reusable_case_smoke.py` has a recorded FDI21/31 headless path and fresh reopen through Step 6A; normal-window verdict remains open. No single accepted all-step production path. |
| Case package/save/reopen | `run_dentobot_case_bundle_smoke.py`, `run_dentobot_case_bundle_transaction_smoke.py`, `run_dentobot_case_reopen_diagnostic.py`, `run_dentobot_step6_restore_smoke.py`, `test_case_bundle.py` | Distinguish format/rollback tests from current-step lineage and operator acceptance. |
| Views and GUI state | `run_dentobot_step6_view_integrity_smoke.py`, `run_dentobot_view_composition_smoke.py`, `run_dentobot_view_u01_diagnostic.py`, `run_w4_u02_probe.py`, `test_view_presets.py` | Display-only probes do not establish native collision/planner behavior. `VIEW-U-01` and `W4-U-02` normal-window verdicts remain open. |
| Step 6 planning, guard, restore | Matrix `p0`, `step6-restore`, `s6-reusable-case`, `s6-target-matrix`; `run_dentobot_step65_exact_case_smoke.py`, `run_dentobot_phase_guard_smoke.py`, `run_dentobot_scene_lifecycle_smoke.py` | `S6-LIVE-01` is operator-paused. Historical diagnostic witnesses and partial paths do not satisfy `S6-LIVE-05` clean-case full loop/repeat or headless every-step gate. |
| Studio studies/results/replay | No current Studio production runner | Deferred `DSS-06..12`; existing diagnostic batch runners are not Studio study acceptance. |

**Approval:** reading this index authorizes no Slicer, ROS, MoveIt, build,
motion, hardware or patient operation. Use matrix and task-specific approval
rules. `S6-LIVE-01` remains paused, including its GUI comparison scripts.

## Matrix-linked `Testing/` runners

| Script (under `Testing/`) | Reuse scope | Check ID(s) |
|---|---|---|
| `run_c1_p3_r4_batch.bash` | Saved r4 P3/P4/P5 bounded diagnostic | `runtime.c1_p3_r4_endpoint`, `runtime.c1_p4_r4_insertion`, `runtime.c1_p5_r4_approach` |
| `run_dentobot_auto_open_mouth_smoke.py` | Reviewed-case AUTO opening | `runtime.auto_open_mouth_test1_post` |
| `run_dentobot_fdi31_recovery_diagnostic.py` | Frozen FDI31 recovery P1/P2 | `recovery.p1_scene_audit`, `recovery.p2_state_contact`; static/pure companions |
| `run_dentobot_phase_guard_smoke.py` | Simulation phase guard | `runtime.phase_guard` |
| `run_dentobot_pulp_shell_smoke.py` | Step 4A display and FDI11/31 shell | `runtime.step4a_pulp_display`, `runtime.pulp_shell_fdi11`, `runtime.pulp_shell_fdi31` |
| `run_dentobot_reusable_case_smoke.py` | PreparedBranch and package path | `runtime.s6_reusable_case` |
| `run_dentobot_scene_lifecycle_smoke.py` | Scene replacement with SlicerROS2 | `runtime.scene_lifecycle` |
| `run_dentobot_segmentation_runs_smoke.py` | Consecutive Step 3 runs | `runtime.step3_segmentation_runs` |
| `run_dentobot_slicer_reload_smoke.py` | Module reload lifecycle | `runtime.slicer_reload` |
| `run_dentobot_stage6_target_matrix.py` | FDI target matrix | `runtime.s6_target_matrix` |
| `run_dentobot_step65_exact_case_smoke.py` | Exact-case Step 6.5 | `runtime.step65_exact_case` |
| `run_dentobot_step6_restore_smoke.py` | Step 6 package restore | `runtime.step6_restore` |
| `run_dentobot_step6_view_integrity_smoke.py` | Restored/opened Views | `runtime.step6_view_integrity` |

`runtime.w5u04_bore_safe_template` directly calls
`DENTOWorkflowTest.test_DENTOWorkflowVisibleTemplateSupportSurface` outside
`Testing/`. The matrix also has static, pure, build and manual checks that
are not one standalone runner. The manual checks are not headless passes.

## Matrix-linked pure test modules

| Script (under `Testing/`) | Check ID(s) |
|---|---|
| `test_assisted_pulp_endpoint.py` | `pure.assisted_pulp_endpoint`; static compile |
| `test_case_bundle.py`, `test_robot_placement.py` | `pure.step6_restore` |
| `test_robot_workflow_facade.py`, `test_step6_planning.py` | `pure.step6_planning` |
| `test_step6_state.py` | `pure.step6_planning`, `pure.step6_restore` |
| `test_support_boundary_bridge.py` | `pure.support_boundary_bridge` |
| `test_step4b_support_auto.py` | `pure.step4b_support_auto` |
| `test_fdi31_recovery_diagnostic.py` | `pure.fdi31_recovery_diagnostic`; static compile |

## Other active `Testing/` runners — no direct matrix entry

No matrix entry means invocation, dependencies and pass criteria must be read
from the script and its owning task before reuse. **Provisional** means the
file is untracked in this worktree; it is not part of a published baseline.

| Script | Specific existing use / scope |
|---|---|
| `run_dentobot_application_shell_smoke.py` | Visible application-shell smoke |
| `run_dentobot_c1_display_only_recapture.py` | Historical Campaign-1 display recapture |
| `run_dentobot_case13sept_fdi32_workflow_smoke.py` | Saved-case FDI32 trajectory workflow |
| `run_dentobot_case_base_lineage_diagnostic.py` | Read-only base-lineage comparison |
| `run_dentobot_case_bundle_smoke.py` | Step 5C/6 package round trip |
| `run_dentobot_case_bundle_transaction_smoke.py` | Failed-load rollback |
| `run_dentobot_case_mask_visibility_save_smoke.py` | Opened-jaw display save copy |
| `run_dentobot_case_reopen_diagnostic.py` | Saved-package reopen inspection |
| `run_dentobot_existing_case_restore_smoke.py` | Repeated retained Step 6 package load |
| `run_dentobot_fd14_newcase_save_smoke.py` | New Empty Case then save |
| `run_dentobot_fdi31_foundation_migration.py` | 13-Sep foundation package migration |
| `run_dentobot_moveit_smoke.py` | ROS state/TF/Cartesian smoke |
| `run_dentobot_stage6_target_generation.py` | Single-target Step 4A–5C generation |
| `run_dentobot_step66_roll_diagnostic.py` | Exact-case axial-roll diagnosis |
| `run_dentobot_step6_geometry_diagnostic.py` | Read-only Step 6 saved geometry |
| `run_dentobot_step6_preentry_roll_diagnostic.py` | Read-only PreEntry roll reachability |
| `run_dentobot_step6a_package_gate_smoke.py` | Step 6A import/placement fallback |
| `run_dentobot_step6a_retry_restore_smoke.py` | Step 6A retry/package switch |
| `run_dentobot_view_composition_smoke.py` | Views composition/stage locks |
| `run_mrml_nifti_roundtrip_test.py` | Bridge B launcher |
| `run_slicerros2_imaging_bridge_test.py` | Imaging bridge launcher |
| `run_ubuntu_bridge_a_health_test.py` | Bridge A launcher |
| `run_dentobot_fdi11_pulp_envelope_smoke.py` **(provisional)** | FDI11 enclosed pulp candidate |
| `run_dentobot_pulp_inventory_bundle_reopen.py` **(provisional)** | Saved FDI11 pulp package reopen |
| `run_dentobot_pulp_inventory_restore_verify.py` **(provisional)** | Pulp report MRB/package restore |
| `run_dentobot_pulp_inventory_smoke.py` **(provisional)** | Pulp audit/bulk/save-reload |
| `run_dentobot_step65_collision_recapture.py` **(provisional)** | FDI21 first-invalid display recapture; retained recapture evidence is invalid and must not be promoted |
| `run_dentobot_step65_three_planner_gui.py` **(provisional)** | Opt-in three-planner GUI comparison; operator-paused |
| `run_dentobot_ui_performance_probe.py` **(provisional)** | Step 5B/4C timing/watchdog probe |
| `run_dentobot_view_u01_diagnostic.py` **(provisional)** | VIEW-U-01 display transition |
| `run_w4_u02_probe.py` **(provisional)** | Smooth/native display mode probe |

## Other active `Testing/` pure test modules — no direct matrix entry

| Script | Specific existing use / scope |
|---|---|
| `test_application_shell.py` | Application-shell contracts |
| `test_dental_semantics.py` | Tooth/pulp identity association |
| `test_dentobot_c1_display_only_recapture.py` | Campaign-1 recapture driver logic |
| `test_dentobot_slicer_handoff.py` | Simulation/diagnostic handoff wrapper |
| `test_fdi31_saved_trajectory.py` | Saved trajectory parser |
| `test_modular_structure.py` | Module/API/package boundaries |
| `test_module_reload.py` | Reload contract |
| `test_moveit_config.py` | MoveIt/frame configuration |
| `test_offline_placement_status.py` | Step 3B/6.1 placement status |
| `test_platform_contract.py` | Windows/Linux runtime configuration |
| `test_ros2_bridge.py` | ROS adapter |
| `test_ros2_cli_slicer_env.py` | Embedded-Slicer/ROS CLI separation |
| `test_simulation_status.py` | External status publisher graph |
| `test_verification_matrix.py` | Matrix integrity |
| `test_view_presets.py` | Stage/view recommendations |
| `test_virtual_forehead_mount.py` | Virtual forehead geometry |
| `test_virtual_open_mouth_articulator.py` | Open-mouth geometry |
| `test_pulp_inventory.py` **(provisional)** | Step 2 audit/bulk logic |

## Standalone Slicer modules and adjacent suites

The five standalone `Testing/` modules are
`SlicerROS2ImagingBridgeTest.py`, `SyntheticMRMLNiftiRoundTripTest.py`,
`UbuntuBridgeAHealthTest.py`, `UbuntuBridgeCEndToEndTest.py`, and
`UbuntuTeethImportTest.py`. They test imaging bridge, synthetic round trip,
Bridge A health, Bridge C end-to-end and completed inference import,
respectively. The matrix does not directly name them.

Outside `Testing/`, existing checks include
`Inference/tests/test_health.py`, `test_segmentation.py`, `test_cli.py`,
`test_roundtrip.py`; `dentobot_description/test/test_description.py`;
`Workspace/scripts/test-mrml-nifti-roundtrip.bash`; and the in-module
`DENTOWorkflow/Resources/Python/dentobot_workflow/slicer_tests.py` harness.
Inspect these before writing an inference, URDF, bridge or workflow check.

## Evidence limits and pending DCP-00 action

This index used file headers, matrix content, Git tracking state and dated
records; it **did not execute** a test, build, Slicer or ROS session. Examples
of recorded evidence are the 2026-09-18 AUTO open-mouth headless PASS, the
2026-09-22 reusable-case FDI21/31 headless save/fresh-reopen PASS, and the
2026-09-24 focused pulp inventory restore/reopen PASS. They cover those exact
cases and revisions. The FDI21 Step 6.5 planner comparison is incomplete;
the collision recapture is invalid evidence. See dated logbooks and the
owning task for full inputs/commands and first failures.

For `DCP-00`, the next bounded read-only step is a **step-by-step production
workflow evidence map**: link each step, transition and save/reopen boundary
to its existing script, exact command, case/revision, last result and owning
task. Mark gaps `NOT VERIFIED`; do not add a parallel script or claim that
matrix coverage equals full workflow coverage. Studio implementation remains
on hold under the existing `S6-LIVE-05` and headless step gates.

9October bounded configuredHome composition: run-local input/001-same-home-validation.py in /home/tarun/dentobot/data/dentobot-runs/2026-10-08/S6-ADVISOR-GUI-01-FDI14-RUNA-20261008T223432Z reuses existing headed _accept_current_state_as_task_home through session driver, same savedjoint gate, no motion/save; explicit configuredsetup approval/resource ownership required. Actual execution stopped at incorrect historical5s expectation before helper; NOT_RUNTIME_VERIFIED. Production default10s correction remains pending first-failure disposition; no automation recommendation. Outputs setupraw/state/screenshot/outbox; PASS requires strict sameHome owner + equality/currentscene/profile/defaultpolicy and unchangedcase, not syntax or matching savedfields. Existing matrix runtime.step6_advisor_baseline_session remains baseline route; no new runner/queue.

## 9 October — S6-ADVISOR-GUI-01 user-input harness entries (additive; Haiku docs pass)

Reuse decision: the headed runner and session commands keep their existing owners; only the press path changed. The new module is the single real-input press helper for the headed harness. Matrix status: `Testing/verification_matrix.json` has NO route for this module yet (checked 9 October); this docs pass did not edit the matrix. Latest results are in run evidence, not in this index.

| Script(s) under Testing/ | Purpose / invocation / output | Status and limits |
|---|---|---|
| `step6_user_input.py` (test: `test_step6_user_input.py`) | Real-user press for production controls in the headed harness: visible, enabled, uncovered checks; real tab presses to reach a control on a non-current tab page; X-level window activation and hit test; XTest pointer move and button press confirmed by the production `clicked` signal path. Imported by `run_dentobot_step6_headed_review.py` (the only importer; session commands run inside that runner process). Refuses rather than falls back to `click()`. | Commits `f86cdd5`, `3961b6c`, `ac030b4`, `a4f9aa1`, `3958e2c` on LOCAL branch `p0/advisor-gui-2026-10-08` (worktree `/home/tarun/dentobot-worktrees/advisor-gui-2026-10-08`); not in primary checkout HEAD; not pushed. Host-tested (host union 817 passed / 0 failed, `S6-ADVISOR-GUI-01-FIX7-HOST-20261009T032414Z`). Runtime-exercised in the 9 October GUI matrix and retests; accepted status NOT_RUNTIME_VERIFIED; human verdict pending. |
| `DENTOBOT_HEADED_INPUT` environment variable | `xtest` (default; real XTest input, no pacing), `demo` (same input plus pointer glide, highlight, caption and holds for a slowed recording), `qt_click` (legacy `QAbstractButton.click()`; not for new acceptance). Any other value is refused. | Routine S6-ADVISOR-GUI-01 runs use `xtest` (final retest argv: `DENTOBOT_HEADED_INPUT=xtest`). Slowed `demo` confirmation run waived for this task by the operator on 2026-10-09 (DECISIONS 2026-10-09); the user-memory rule still asks for at least one demo per feature. |
| `step6_session_commands/advisor_baseline.py`, `advisor_consented_trials.py` (4-line call-site changes in `f86cdd5`; `advisor_precheck.py` not changed by it) | Existing session commands; invocation and outputs unchanged from the 8 October entries above. Their former `.click()` calls became `_press(...)` (runner helper backed by `step6_user_input`), e.g. Find Working Configuration and Start search in `advisor_baseline.py`. | Same status as the 8 October entries; the matrix routes above still apply. Runtime results: RUNA-FIX and RETEST4 run roots (see logbook 2026-10-09). |

## 10 October — project progress visibility (`PROGRESS-DASH-01`)

Reuse lookup: this index/matrix and Workspace scripts have no standalone live
projection of development backlog + agent activity + private phone access.
In-module restored-case integrity/Studio and workflow runners address different
boundaries. The uncovered behavior requires the following small independent
stdlib service; it neither wraps nor duplicates Slicer/ROS production steps.

| Script | Purpose / invocation | Dependencies, approval, outputs and limitations |
|---|---|---|
| `Workspace/scripts/progress_dashboard/server.py` | Read-only live backlog/focus projection. `python3 …/server.py --overlay <overlay> --host 127.0.0.1 --host <tailnet-ip> --port 8766`. | Python stdlib, canonical docs; tcp8766 only. Local-web execution requires bounded approval. `/api/snapshot`, allowlisted `/source`, static UI. Pending rows/fresh reports are not accepted project progress or proof of agent execution. |
| `Workspace/scripts/progress_dashboard/focus.py` | `set`, `update`, `finish`, `status` explicit task/milestone/main-supporting receipts; invocation in SETUP. | Local operational metadata write, no robot/queue/acceptance authority. JSON/JSONL under overlay `data/project-progress/sessions/`; no automatic heartbeat. |
| `Workspace/scripts/progress_dashboard/install.py` | `--overlay <overlay> --port 8766 --tailscale --print-only` prepares unit; omit print-only to install/start dedicated user service. | Python/systemd user manager; optional existing tailscale IP; explicit startup scope, no all-interface/public binding or existing Serve-route changes. Availability follows host/user-manager uptime. |
| `Testing/test_project_progress_dashboard.py` | `DENTOBOT_VERIFICATION_DIR=<run-dir>/fixtures PYTHONDONTWRITEBYTECODE=1 python3 Testing/test_project_progress_dashboard.py` | Focused fixture/mock host checks, bounded approval, no Slicer/ROS/systemctl. Matrix `pure.project_progress_dashboard`; current results belong to dated run/logbook, not this index. |

Matrix profile `project-progress-dashboard` also separates local HTTP/browser
checks and operator phone/UX verdict. Source is dirty/uncommitted on the existing
P0 branch; no workflow promotion or exact committed-SHA acceptance is claimed.

### PROGRESS-DASH-01 adaptive revision — 10 October

Existing server/focus/fixture entries are materially extended, with no new runner: schema1 display metadata from existing DEVELOPMENT_PLAN; task-linked provenance; dynamic milestone/current projection; shared canonical ID/session discovery; current focus intervals and active/history separation. Fixture suite gains genuine source-change/lifecycle/validation acceptance cases; invocation/dependencies/output override unchanged. Matrix pure/runtime pass conditions updated, explain_then_approve retained; no results claimed for revised source. Existing local/tailnet service boundaries and operator-only phone/UX verdict unchanged.

### PROGRESS-DASH-01 chronology projection — 11 October (implementation in progress)

`Workspace/scripts/progress_dashboard/work_history.py` is an internal server projection helper, not another runner/queue. Owner PROGRESS-DASH-01; invoked through existing server.py snapshot, configured in overlaydata/project-progress/work-history-config.json. Inputs explicit focus/activity, exact controlled-record roots/files and exact nativeCodexsession/lifecycle metadata binding. Only assistant summaries/timestamp/lifecycle metadata, no user/system/rawtooloutputs or clinicalrecords. Output chronologicalwork_items/current_work/recent_work/active_now/sourcecoverage; latestmainpersistswhilecompleted/paused. LocalundocumentedCodexschema mustfailwithwarning ondrift, neverfalseempty/liveproof. Sameexistingdashboardfixture/service/browserapprovalclass, no newservice/resources. Verification latest linkedchronologyrun, not timelessPASS.


### PROGRESS-DASH-01 on-demand interpretation — 11 October

`Workspace/scripts/progress_dashboard/item_explanation.py` is an internal production helper owned by PROGRESS-DASH-01, invoked only by the existing server's explicit explanation API. It captures a bounded canonical current-item context, builds restricted exact Luna Max/Haiku CLI commands, manages one asynchronous request and a bounded semantic cache, and returns plain advisory text with captured provenance. Dependencies: Python stdlib plus existing `/home/tarun/.local/bin/codex` or `claude`, their local authentication, and required supported restriction flags; no new package/service. Models GET is capability metadata only. An explicit explanation POST uses the selected model resource; no automatic calls, retries or scheduler. Request origin/JSON/size/field and current-item identity guards must pass. Output: queued/running/completed/error with captured task/time/model; errors do not alter factual progress. Limitations: CLI metadata is not model authentication/response evidence, cache is in-memory, provider/schema availability can change, operator UX remains separate.

Existing `Testing/test_project_progress_dashboard.py` is extended rather than duplicated: mock-only explanation context/privacy/current selection/cache/one-job/error/HTTP and restricted CLI/timeout behavior. Same `pure.project_progress_dashboard` approved host command/output override; dated results live in the explanation run. Existing runtime dashboard scope covers own-service reload, metadata-only GETs and mocked browser UI checks; valid real-model POST is excluded from those host checks. `manual.project_progress_item_explanation` separately records operator-triggered real use/verdict, never a timeless PASS here. Dark red/violet presentation uses the existing index.html and browser resources only.
