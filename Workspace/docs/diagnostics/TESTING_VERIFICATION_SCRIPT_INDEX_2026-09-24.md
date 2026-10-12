# Testing and verification script index — 2026-09-24

**Owner:** `DCP-00` foundations review. **Scope:** current development checkout
at `/home/light-tarun/dentobot/ros2_ws/src/DentoBot`. This is a reuse index,
not a test execution or acceptance record. Read the canonical
[`verification_matrix.json`](../../../Testing/verification_matrix.json) and
[`AGENTIC_VERIFICATION_PROTOCOL.md`](../AGENTIC_VERIFICATION_PROTOCOL.md)
before invoking a check. The matrix owns commands, resources, approval,
dependencies and pass conditions. Its entries do not record latest results.

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


### 11 October — DCP-09 one-run observer prototype, not promoted

Owner DCP-09..10, solo coordinator. Private prototype `/home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z/input/fingerprint_trace.py` with `check_fingerprint_trace.py`: observes production fingerprint inputs and Save As boundaries; no reconstructed geometry. Host command, dependencies, PASS results and first loader FAIL are in run-local REVIEW.md. No native resources for fixture; host preparation only by explicit 11 October operator scope. Outputs private host-evidence/; mechanism PASS requires single call-through/restoration/privacy/fail-closed. Runtime companion remains matrix `runtime.dentocase_offline_persistence`, separately gated; full regression `pure.dentocase_integration` is not replaced. This stopped case-specific prototype is not reusable/promoted or a new matrix execution entry. Exact loader seam remains unverified; do not launch or reuse as accepted workflow.


11 October DCP-09 prototype update: authorized explicit-path loader correction PASS in isolated host exact-boot AST fixture `input/check_trace_loader.py`; updated invocation and output at `/home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z/PROPOSAL.md` and TASKS latest entry. Host static37 and observer mechanism PASS, native NOT_RUN. Prior stopped prototype evidence retained. This remains a case-specific run-owned diagnostic, not a promoted reusable workflow or replacement matrix entry.


### 2026-10-11 DCP-09 selected docking recipe regression extension

Existing `Testing/test_dentocase_projection.py` / `pure.dentocase_integration` now covers selected assembly recipe restoration, validation-before-write, clear-list preservation and binding order at source SHA 8e7e0b2662f94fe62536932089c87c051eff8ecf. Owner: DCP-09 coordinator; one Luna MAX test worker. Invocation/dependencies/resources/approval remain the existing matrix row (host pure, no native imports, explain-then-approve). Outputs: pytest logs under DCP-09-PARTIAL-PARAMETERS-20261011T011008Z/evidence; exit0 required. Limits: host mocks and extracted production normalizer do not establish native Qt/MRML or operator acceptance. No new runner/framework added.

2026-10-11 DCP-09 existing Testing/test_case_bundle.py extended with actual AST helper orphan lifecycle regressions (saved/referenced/owned/custom nodes preserved, failed reads before mutation); same pure.dentocase_integration command/dependencies/approval/resources. Owner coordinator, Luna MAX tests. Evidence DCP-09-DISPLAY-LIFECYCLE-20261011T015219Z/evidence; host only, no native acceptance. Verified source0000b4e4cd4009d7687a410da1f913ca5de0ec75.


2026-10-11 DCP-09 run-owned saved-child auditor correction in /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-COMBINED-REPAIR-20261011T080723Z/input/audit_saved_child.py. Owner coordinator; Luna MAX host fixture verification. Existing auditor composition retained; uncovered boundary is initial projection clears step6EnvironmentJson but accepted schema3 Save As regenerates it. Final audit now must validate production snapshot equality, unlocked Base/rev0/no Home and Case Foundation fingerprints. Invocation remains `PYTHONPATH=<pinned-source>/DENTOWorkflow/Resources/Python python3 <run>/input/audit_saved_child.py <source> <child> <plan> <report>`; host read-only, no native resources. Output HOST_CHILD_AUDIT_PASS only when all predicates pass; malformed/inherited-authority fixtures must reject. This case-specific diagnostic is not promoted as reusable automation and does not replace matrix runtime.dentocase_offline_persistence or operator verdict. Exact final hashes/results belong in run evidence.


DCP-09 run-owned native_reopen_boot.py return-interface correction, root /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-REOPEN-COMPLETE-20261011T085704Z: production CaseBundleInspection manifest/workflow/path adapter + focused host fixture1positive7negative; narrow native fresh reopen technical PASS at0000b4e, strict global FAILED retained. Existing runtime.dentocase_offline_persistence route, no reusable promotion; exact commands/hashes in manifest and evidence/host-reopen-adapter-check.json.


### 11 October — clean FDI34 advisor reuse, preparation only

S6-ADVISOR-GUI-01 resumes with accepted child06e3218c…ff624c; [concrete contract](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-CLEAN-PLAN-20261011T091706Z/UPDATED-TESTING-PLAN.md). Reuse runtime.step6_advisor_baseline_session and runtime.step6_advisor_consented_trial_cancel, headed runner/session driver/recorder/real-XTest helpers. No new runtime entry or automatic permission. Existing runner serves commands after Connect/scene ack and needs a bounded clean disconnected setup checkpoint before fresh Base/Home acceptance; no tested adapter yet. Historical FDI14 core evidence may be reused only with scoped drift/identity checks. H2 evidence-name uniqueness remains an explicit freeze gate. No tests/runtime run by this entry.


11October setup checkpoint implementation: existing run_dentobot_step6_headed_review.py now supports DENTOBOT_HEADED_CLEAN_SETUP_ONLY=1, before Base actions/native preflight/Connect. Existing Testing/test_step6_headed_review_source.py adds12 focused host checks; no new runtime framework. Exact prepared composition and outcome at /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-SETUP-GITMAP-20261011T133709Z/PROPOSAL.md. Native GUI checkpoint NOT_REACHED after wrapper Git-map failure; corrected identity-only preflight PASS, no corrected runtime.


S6-ADVISOR-GUI-01 update 2026-10-11 13:54 UTC: corrected disconnected setup captured at source34f5a7a, host170 PASS, cleanupPASS. Import succeeds; Base review rejects stale case_or_base_identity_changed, Base unlocked/Home absent. Advisor and FDI34 planning remain open, operator GUI verdict pending before production Base identity reconciliation. No planning or motion, opening<=46mm. Evidence /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-SETUP-CAPTURE-20261011T135256Z/evidence/outcome.json; full account in logbook/2026-10-11.md.


2026-10-11T14:08:37.061944+00:00 S6-ADVISOR-GUI-01 Base identity observation: existing headed clean setup checkpoint now reads production manualBaseReview before Import and after Import, preserving stale candidate; facade read-only details name changed identity fields. Focused host17/14 PASS, evidence /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-AUTOHOME-20261011T140338Z; native not run. Existing matrix pure.step6_planning/pure.step6_advisor_session_host and runtime baseline/consented entries retained. No separate runtime framework or automatic permission. AutoHome metrics contract remains run-local.


2026-10-11T14:15:19.447445+00:00 sourcecab6c74: clean-only Base observation now covers beforeLoad/afterLoad-beforeImport/afterImport-beforeBaseNavigation; identityChangedFields retains production stale failure. Advisor noHome setup fix calls existing _onStep6AutoTaskHome after releasing modal; no acceptance. Combined472PASS. Existing indexed harness frozen at /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-AUTOHOME-20261011T140338Z/PROPOSAL.md, manifestb212edf6b44ec77f2f1719893d9220f8df6797516bb3a9d6319e64f3a96f24e5, package/syntax/current read-only preflightPASS, nativeNOT_RUN pending exact approval; no new harness/matrix row or automatic execution.


2026-10-11 approved cab6c74 disconnected discriminator stopped at headed per-SHA checkout-root provenance (7character suffix vs12 required) before case/robot/Import/Base. Exact command consumed; cleanupPASS. New preparation S6-ADVISOR-GUI-01-BASE-PATHFIX-20261011T142152Z uses correct12character visible path and host-only production _checkout_profile/_checkout_evidence fixture, to reject old metadata before display/Slicer. Production source/guards unchanged; source472PASS not repeated. No retry/acceptance yet. Prior video6.6s launch-only; extracted4s frameblack, not configuration/GUI proof.


2026-10-11T14:30:56.672849+00:00 S6-ADVISOR-GUI-01 corrected host-only provenance fixture/wrapper: /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-PATHFIX-20261011T142152Z/input/provenance_preflight.py (production AST call-through, actual20source/runner hashes, positive+6negativePASS), run_setup.py --check (manifest/source guards then fixture, no runtime). Frozen proposal /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-PATHFIX-20261011T142152Z/PROPOSAL.md; --execute requires separate corrected-run decision after first-failure. No production provenance gate change.


2026-10-11T14:50:21.094854+00:00 S6-ADVISOR-GUI-01 /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-STAGING-20261011T144128Z/input/native_result_gate.py: read-only disconnected resultgate, positive+8negativePASS. run_setup.py --check checks hashes/productionprovenance only; --execute gated newapproval. Final manifestd08137f3f74260ad2db208a873553904804deb9294cb604b7d5beb5d3e371159. Hostmanual/facade/headedsource375PASS. No acceptance bypass.
