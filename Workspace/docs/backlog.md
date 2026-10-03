# DENTOBOT pending backlog

Latest scoped checkpoint: **4 October 2026** (`S6-LIVE-01`, `PLAT-U-07`, `S6-P2-03`).
Local destination checkout: `/home/tarun/dentobot/ros2_ws/src/DentoBot` on `main`.
The broader 1 October task reconciliation and source-station integration routing
remain dated context; this checkpoint does not accept their open gates.
This is the sole queue for pending work. Read every section and search IDs,
synonyms and overlaps before planning. [TASKS.md](TASKS.md) holds contracts;
[DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) holds acceptance design;
[DECISIONS.md](DECISIONS.md) and [logbook](logbook/2026-10-01.md) hold decisions/evidence.

## Priority and completion rules

- **P0:** repair and demonstrate the existing Step6 setup-to-workbench workflow; first perform its bounded read-only diagnosis.
- **P1:** current correctness/reliability closure and ready-for-verdict reviews.
- **P2:** conclusive workflow acceptance, useful missing controls and verification learning.
- **P3:** next platform, representative/physical work and dependency-blocked roadmap.
- **P4:** explicit holds, fallback/experimental work and later hardware boundaries.

Priority is independent of implementation state. IDs containing old P0/P1/P2
labels retain their identity; the priority column below is current. Dependencies
can precede their dependent task. A ready review does not require reimplementation;
a demonstrated defect returns to its existing owner. Source completion is not
runtime/physical acceptance. Remove a task only after its required verdict and
evidence are recorded in TASKS/plan/logbook during the same turn.

**Current execution boundary:** bounded read-only workflow diagnosis first under the latest [recovery contract](diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md); subsequent source corrections and headed verification remain separately scoped. Tarun assesses robotics/usability after demonstrable setup recovery. No new autonomous Slicer/ROS/MoveIt/planner/preview
trial for this pass. Safe no-solution diagnostics are valid outcomes, not
infeasibility proof. Complete preview requires a fresh independently guarded
Home→PreEntry→Entry→Target chain. Keep exact J1–J5, fixed spindle/TCP geometry,
strict IK/collision/phase ownership, and explicit Base/Home acceptance. Saved
configuration/history never restores live ROS, route or preview authority.
Operator confirms performance integration completed (1 October); integrated manual-trial responsiveness remains OPEN under S6-P2-03. Slicer 5.12 remains held.

**4October narrow supersession (`S6-LIVE-01`):** Tarun explicitly requests
Oct4-case Home revalidation diagnosis, correction, Python reload and testing in
the same open headed runtime. That scope is complete for the rejection/cancel
recovery defect: host242 PASS and real Review → strict collision rejection →
Cancel → fresh Review PASS in PID2071. The rejected zero-joint pose remains
invalid; no Home was saved. Original draft/case/accepted state are preserved.
Tarun's usability verdict, admissible Home and broader continuity gates remain
open. This is not a fourth old repeatability-campaign attempt or authorization
for planner/preview/geometry changes. See [evidence](logbook/2026-10-04.md).

**Later4October steering (`S6-LIVE-01`):** “cannot plan and apply new home”
extends the same owner to the missing new-draft action. Plan + Apply Home Draft
is implemented/reloaded in PID2071 and targets the exact current or reviewed
draft; separate acceptance still saves Home. Actual button reached MoveIt;
all3 existing internal attempts stopped at CheckStartStateCollision for
`dentobot_mouth_barrier_lip_slab` / `pneumatic_spindle-Copy` in the all-zero
start. No waypoint/case/Home save. Source/UI routing correction is demonstrated;
positive route/application and Tarun verdict remain OPEN. Next bounded action:
operator review of this collision and selection of a collision-free starting
setup; no geometry/policy change or further planner retry is inferred.
See [4October evidence](logbook/2026-10-04.md).

Evidence routes: [current handoff](diagnostics/STEP6_IMPLEMENTATION_HANDOFF_2026-10-01.md),
[renovation contract](diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md),
[five-DOF checklist](diagnostics/STEP6_FIVE_DOF_DETAILED_ACCEPTANCE_CHECKLIST_2026-09-28.md),
[script reuse index](diagnostics/TESTING_VERIFICATION_SCRIPT_INDEX_2026-09-24.md),
[performance monitoring](PERFORMANCE_MONITORING.md). These elaborate existing IDs,
not separate queues. No engineer-owned records were accessed for this reconciliation.

## Implemented — user visual review and verdict remaining

These narrowly scoped corrections have no identified remaining implementation
work. Broader runtime/physical acceptance remains in its own row below. A review
may expose a defect; record it under the same owner rather than creating a duplicate.

| ID | Priority | Outcome | Evidence summary | Remaining user action | Dependency / overlap |
|---|---|---|---|---|---|
| `VIEW-U-01` | 1 | Opened anatomy and ghost-display correction | Shared 2D/3D and final-save normalization checked on the supplied case. | Tarun reviews opened/source views, target changes and save/reopen; record visual verdict. | Coordinate restore with S6-REUSABLE-CASE-SETUP; opacity is VIEW-U-02. |
| `W4-U-02` | 1 | Smooth-display controls | Toggle and opened-mask fallback implemented; bounded display checks passed. | Tarun checks default smooth, actual on/off, oblique exit and backtracking across steps. | Do not repeat implementation because endpoint setup stopped the broader runner. |
| `W5-U-04` | 1 | Bore-safe template correction | FDI11 and regenerated FDI31 pass the recorded geometry gates. | Tarun reviews Step 5B/5C, open bores and any remaining fragment/contributor evidence. | W5-U-03 owns broader fusion/export acceptance; no threshold relaxation. |
| `S6A-CHANGED-TARGET-GEOMETRY` | 1 | Target-change geometry cleanup | Clear/save guards implemented and checked. | Tarun completes a clean FDI44 workflow and visually checks target-attached geometry. | A real stale-chain finding returns to existing restore/construction owner. |
| `S6-U-04` | 1 | Diagnostics Close button | Dismissal correction implemented. | Tarun checks Close before/after evidence review, reopen and callback state. | Use an approved diagnostic session; no new planner experiment is implied. |
| `S3-U-01` | 1 | Scan/run inspection | Source-paired inspection implemented with focused Slicer evidence. | Tarun checks real preDental/postDental switching, compare, rename and Step 4 handoff. | Keep run/source identity intact. |
| `W4B-P2-SUPPORT-AUTO` | 1 | Automatic support suggestion | Four-nearest suggestion and pure boundary checks implemented. | Tarun reviews suggestion, manual lock/edit, edge/missing teeth and selected-jaw layout. | Existing Step 4B owner; broader polish remains UI-P3-01. |

## Partially implemented or acceptance incomplete — conclusive completion required

Rows marked runtime/physical acceptance may already have source implementation;
they are deliberately not classified as visual-verdict-only. Owner contracts and
current approval boundaries control the smallest remaining work.

| ID | Priority | State | Outcome | Remaining completion | Evidence / dependency / boundary |
|---|---|---|---|---|---|
| `S6-LIVE-01` | 0 | 6.1–6.3 continuity source/headless complete; case-bound repeat acceptance blocked at retry ceiling | Five-DOF engineering workbench | Immediate action: read-only actual-versus-required6.1/6.2→6.3 diagnosis under the latest recovery contract; end with first blocker and bounded correction proposal before expanding execution. Demonstrate changedBase and Home setup/recovery in offline/connected paths before calling the requested UX complete. First operator trial failed connected Base bounds acknowledgement/unknown rollback and offline stale-placement recovery; joint rows have collapsed labels/excessive gaps. Slider layout, strict bounds diagnostics/cache lifetime and Base lock notification ordering are source-corrected; 339 affected host checks passed. Tarun authorized the guard build; renovation Release build/install verified (matching binary SHA19cdc780…6cbe6a1). Corrections are present in integrated source checkpoint50ce208 (current HEADbaeee90). Tarun rejects the revised joint-slider appearance and requests design before implementation. Proposed five-row editor/precision-table comparison is in the existing renovation plan; Selected All joints visible iteration1 is implemented;312 affected host checks pass with2 unrelated concurrent-case tests excluded. Rendered Slicer usability verdict remains open. Operator now requests 6.1–6.3 redundancy/UX planning; source-derived consolidation proposal is appended to the existing renovation plan. Design review precedes any broader presentation implementation. Operator rejects omissions in the compressed sketch. Corrected same-step preservation ledger restores ROS connection, virtual-forehead/automatic-Base proposal and requested automatic unlocked-Base drag/status; inspect candidate targeting before changing the Step6 handle-suppression gate. Continuity review specifies inline acceptance, visible Manual/Workspace/Plan tabs, named complete tools and return/invalidation behavior. The new coherent interactive walkthrough is at `/home/light-tarun/dentobot/data/visualizations/step6-continuity-sketch.html`; it covers offline/connected/review/uncertain/stale/blocked states and preserves the full control ledger. Design verdict and native narrow-panel fit remain pending. Offline Base acceptance and connected scene acknowledgement still require verdict; runtime attribution/verdict remains open. Tarun tests Base/Home recovery, joint/TCP controls, failed-pose inspection, guarded outcomes, records and conditional planning/preview. 469 combined host checks passed; new layout/diagnostic rendering and native robotics verdict remain pending. Source and pure headless sequence now cover 6.1 Robot Setup, compact 6.2 Home, and 6.3 Manual/Workspace/Plan with owner-return continuity; 565 host checks pass. Case-bound repeatability r1–r3 reached connected scene acknowledgement in r3 but stopped on a stale pre-tab harness visibility assumption before Base/Home acceptance. The runner is tab-aware in source; protocol retry ceiling now blocks a fourth campaign this turn. Next: fresh authorized serialized run must complete changed Base and Home acceptance/reconfirmation twice, followed by Tarun visual verdict. | Existing r22 TCP, r26 reconciliation, r29 offline/connected Home and r30 strict reopen evidence are bounded passes; r31 retained no-endpoint evidence. No autonomous runtime for this pass; no forced planner success. 2026-10-01 integration r2 (Claude, rebuilt native overlay): case load→connect→Home accept→guarded J1→6.3 workspace PASS (16 PASS/1 FAIL/13 NOT_RUN); stopped at known PreEntry no-endpoint, Plan Approach not reached; r1 fingerprint fix (Facade `_motionControlNodeIdentity`) host+runtime verified. Headed runner has no modal-dialog watchdog. See logbook. 2026-10-02 offline attribution (validated replica of native IK): PreEntry failure = base-placement reach limit at J2 lower stop (stroke needs J2 −0.92…−12.17 mm); 13.18 mm base shift, world RAS (−0.42,−2.49,+12.93) mm, makes all stations converge. Collision/planner not yet measured; r4 with offset aborted on runtime overlap with operator desktop session. See 2026-10-02 logbook. 2026-10-03 r19 (session mode, simulation only): two complete button-driven cycles PASS (Plan → Approach preview → Prepare Drill → Drill preview → Return Home ×2; endpoints verified; drilling WARNING 4.25 of 9.74 mm); Tarun GUI verdict pending; see 2026-10-03 logbook and r19 `diagnostics-visual.md`. 2026-10-03 evidence boundary: the shared `/workspace/ros2_ws/install` used by these runs had `dentobot_description` linked to the retired `src/DentoBot` checkout (URDF with `pneumatic_spindle-Copy_Revolute-6`) and `dentobot_moveit_config` (`collision_guard`, `simulation.launch.py`) built 1 Oct 04:00 from the renovation checkout; `slicer.log`/`campaign.log` of all-items runs r2 and r4–r26 contain `Revolute-6`. Launcher now rebuilds both from the launched checkout; a rerun on matching packages is needed before these runs count as integration evidence. Relaunch at `51293e6` verified integration URDF/MoveIt packages loaded (`Revolute-6` absent). |
| `S3-P0-DENTAL-SEMANTICS` | 1 | Partial conclusive acceptance | Pulp inventory, existing unlabelled masks and candidates | Finish all-tooth throughput assessment, existing-mask Case B one/two assisted-line acceptance, and anatomy/UI verdict for the 52-voxel candidate. | No associated pulp means no pulp-based line. Preserve source labels/voxels; unique HIGH association/enclosure and ambiguity guards remain. Step 4A creates no masks; added candidates currently invalidate Step 3A. |
| `S4A-PULP-ENDPOINT` | 1 | Partial anatomy/contact closure | Assisted Entry/Target geometry | Resolve whether the small candidate needs a persisted local display-surface correction; compare successful operator Entry and native/displayed contact in trajectory-aligned MPR; retain FDI31 review. | Source checks and FDI11 creation exist; small-mask smoothing/contact discrepancy is unresolved. Crown Entry feature is W4-U-01. |
| `S6-REUSABLE-CASE-SETUP` | 1 | Bounded restore verified; broader acceptance open | Reusable cases and branch ownership | Conclude changed-Base/shared 3B–6.1, branch switching, stale evidence and final post-handoff save/reopen review. | r30 strictly reopened the r29 five-DOF fixture. Source-hidden/opened-proxy save/reopen checks exist; normal-window verdict and representative final package remain open. One case-foundation/reposition lane. |
| `S6-RESTORE-ROBOT-ROS` | 1 | Implemented; representative reconstruction acceptance open | Offline and connected robot restore | Verify fresh/warm offline hydration, no auto-connect/duplicates, and explicit current-scene revalidation. | Share S6-REUSABLE-CASE-SETUP campaign. Saved Home/history is configuration only; stale forehead evidence stays stale. |
| `S6-WORKSPACE-PURPOSE` | 1 | Operator decision 2026-10-02: optional visual; source-complete; runtime/operator acceptance open | Optional workspace, reach envelope and stroke-reach planning gate | Headed run: Plan Approach without workspace review; envelope and stations visible; Tarun verdict on envelope display. | Incisor-centered editable 200 mm TCP sampling domain is not a route/robot-link constraint; envelope is display only; empty cloud is not impossibility. No fresh workspace framework. 2026-10-03 operator request: optional task-space box (off by default, adjustable side, distinct from the rose barrier, low default opacities, opacity controls) source-complete `033ac9f`; runtime check r20, Tarun verdict pending. |
| `S6-BASE-DIAGNOSE` | Unprioritized | Operator-agreed 2026-10-02; not implemented | Diagnose This Base in 6.3 Plan tab | Implement ordered check (stroke reach → endpoint collision → Home→PreEntry route → drilling stroke) naming the first failing cause class; host tests; headed run shows each verdict; Tarun verdict. | Display/diagnostic only; reuses existing reach, PreEntry IK and P1/P2/P3 checks; no gate, guard, scene, limit or tolerance change. See DECISIONS 2 Oct. |
| `S6-TRUNCATION-WARNING` | Unprioritized | Operator decision 2026-10-02; not implemented | Truncated drilling shown as warning with highlighted remainder | Plan Approach/Drill status in warning state with reached/requested depth and blocking pair; remainder highlight visible and labelled; headed screenshot; Tarun verdict. | Policy 2b unchanged (truncated plan stays valid and previewable). r9–r12: 4.00 of 9.74 mm, spindle housing ↔ Step 5C template. |
| `S6-MANUAL-STAGE-PLAN` | Unprioritized | On hold (operator 2026-10-02: idea, not now) | Plan a single stage from a manually jogged state | None until the operator lifts the hold. | Would be diagnostic only, no preview authority. |
| `S6-PLAN-CANDIDATE-POLICY` | Unprioritized | Operator decisions 2026-10-03: A default; stamped dev fast mode B; depth-first ranking of Complete chains — source-complete; C not built (r16 data) | Plan Approach candidate evaluation and selection | Runtime: plan selects the deepest Complete chain (r16 case: 4.25 mm candidates over 4.00 mm); Tarun verdict. | r16 first plan: 14 candidates, 8 Complete, all truncated (4.25 mm: 0,7,8,9; 4.00 mm: 1,3,4,12); old ranking selected 3 (4.00 mm, motion 0.1878 vs 0.1909–0.1915). See DECISIONS 3 Oct. 2026-10-03: fast mode is also a 6.3 Run option checkbox (default off; read once per plan; `9534d38`); r23/r24 run-options check PASS. |
| `S6-ERRLOG-01` | Unprioritized | Operator request 2026-10-03; source-complete; runtime-verified r23/r24; operator verdict open | Slicer error log shows errors only for real step failures | Tarun opens the error log (status-bar icon) after a normal 6.1–6.3 run and confirms no misleading red/yellow entries. | No prior backlog match. r22: 2515 error/critical entries per passing run. Fixes `83b22bf`, native `f370474` (errlog-fix overlay), `7c9d629`, `6f332a8`, `1d30251`. r24 in-app log after case load, Find Reachable Base and Task Home: 0 errors, 0 warnings; at end: 0 errors, 1 warning (diagnostic probe's own). The operator launcher needs the errlog-fix overlay to drop the native error. See DECISIONS 3 Oct. |
| `S6-U-01` | 1 | Reliability partially corrected | Crashes, shutdown and process cleanup | Conclude representative case-bearing clean shutdown/recording and cleanup; investigate only a reproduced causal failure under the verification protocol. | Scheduled traceback dumping was removed after r18 GDB evidence. r22/r26/r29 exited cleanly; r30/r31/r14 exit 1 is explained by the headed runner's own FAILED verdict (`slicer.util.exit(1)`), not a native shutdown fault (2026-10-02 read-only analysis; see logbook). Do not attribute every older crash to one cause or resume retries from stale summaries. 2026-10-03: session-mode r19/r20 exit 1 after vtkDebugLeaks of MoveIt trajectory messages (factories lacked `VTK_NEWINSTANCE`); native `c42b862` leak-fix overlay → r21/r22 exit 0, transaction PASS, recording complete. r25 (main install from canonical `f370474`) SIGSEGV at exit in `~PlanningSceneMonitor`: canonical lacked the u01 teardown corrections; ported as native `ece3c42`, main install rebuilt → r26 exit 0, transaction PASS. Operator verdict pending. |
| `S6-P2-03` | 1 | Accepted scoped5.10 ports; broader responsiveness open | Responsiveness in consolidated integration | Increment1 attribution/paging-disk counters implemented and26 host checks passed; paired native identity/overhead/exit acceptance remains open. Increment2 native-wait source plus compile/wrapper/install and focused plan-only/shared-package API probes passed; deployed normal5.10 package, Python242checksPASS. Representative long-wait/cancel/ordinary-window responsiveness remains open; backend cleanup-11 tracked under S6-U-01. Increment3 Ubuntu NVIDIA source/profile port complete;13host/mock tests, shell syntax and frame self-check passed. Prior GPU-less source-station deferral is historical. 2026-10-03: destination RTX4060/driver580.178.04, X11 and NVIDIA Docker runtime verified; this machine is available for GPU acceptance. Current Slicer remains Mesa; NVIDIA renderer/FPS and operator verdict pending. Checklist: [NVIDIA workstation acceptance](diagnostics/NVIDIA_WORKSTATION_ACCEPTANCE_2026-10-03.md); await saved-session restart confirmation and named approved case. All three increments source-implemented; retain only existing acceptance boundaries. Retain ordinary-window/native/GPU acceptance separately; no scope expansion or5.12. | Recorded14gaps/max49.144s remain observations; earlier combined-source attribution withdrawn by checkout correction. No worker-threadMRML, planner-policy change or5.12 work. 2026-10-03: watchdog update applied to the integration checkout (resource sampler identity/alerts/zombie-parent stop; UI stall watchdog main-thread context, active-stall reporter thread, per-action wait totals, `ui_wait()` on the bridge guard wait); runtime acceptance open. 2026-10-03 r19 attribution: guard waits dominated by synchronous llvmpipe 3D renders (SlicerROS2 tf lookups re-apply unchanged link matrices every Spin; 204 ms/frame with depth peeling); validation-scoped render pause measured Plan Approach 116 s vs 279 s; SlicerROS2 tf skip (native `c8b446e`), handshake retry (`beb69a4`), per-command sweep removal (`933bfc1`) and trajectory leak fix (native `c42b862`) implemented 2026-10-03; trials r20–r22 all PASS: two cycles 595/643/510 s vs r19 1816 s; Plan Approach 104/99/77 s vs 279 s; guard check 8.5–10.3 ms vs 173.7 ms. Operator verdict pending; depth peeling (visual) undecided. 2026-10-03: depth peeling is now a 6.3 Run option (default on, operator per-session choice; `9534d38`). r23/r24 two cycles 651/683 s (PASS). 2026-10-03 increment-3 re-check: sources hash-match the 1 Oct evidence; 13 tests, self-check and static Compose config pass; hardware renderer/FPS still deferred. Launcher now refuses `nvidia` mode under WSL (exit 2, points to `wslg`); host tests only. Workstation acceptance is now `runtime.ubuntu_nvidia_render_acceptance` (`launch-dentoworkflow.bash --render-probe CASE` → `verdict.json`, then an operator Step 6 pass); NVIDIA-mode container recreated only when its GPU request is missing. Next: run it on the NVIDIA workstation. |
| `S6-LIVE-03` | 2 | Source implemented; conditional native acceptance | Interruption and Return Home | Tarun verifies exact accepted-prefix retention, Incomplete/AwayFromHome latch and Block Return; separately tests completed-route Return Home and repeat when a guarded route exists. | No reset/teleport or manual-history promotion. Exact-prefix reversal is future separately scoped work, not existing recovery. |
| `S6-LIVE-04` | 2 | Source implemented; conditional native acceptance | Preview/playback and route-intent restore | Conclude speed, ordered acknowledgements, visible paths, route intent and fresh replan on a Complete route. | Requires current complete independently guarded chain; historical replay is display-only. |
| `S6-LIVE-05` | 2 | Blocked representative full-cycle acceptance | Complete software workflow | Review a suitable case/tool/guide and prove approach, drill preview, withdrawal/Home, repeat and representative final save/reopen. | Depends on upstream integrity and accepted complete route; gates DCP-00/Studio. Planner no-solution alone does not prove software defect or infeasibility. |
| `W5-U-03` | 2 | Implemented; broader workflow acceptance open | Step 5B/5C fusion and export | Conclude FDI11/FDI31 fusion, PASS/WARNING/FAIL, stale-lineage handling, channel preservation, one-STL and fresh-reopen review. | Two-target headless repair passed; current normal-window verdict remains. W5-U-04 owns construction correction; independent targets do not imply a fused multi-target template. |
| `W5-U-05` | 2 | Partial implementation | Template dimension/reset interaction | Verify section-2 editability and dimension coupling; implement/review remaining Reset and interactive sizing. | Existing floor correction is implemented; preserve >=2.0 mm guide/channel requirement and owner interfaces. |
| `VERIFY-LEARN-01` | 2 | Teaching deliverable not completed | Learn testing and verification | One guided session on scoped pytest, py_compile, colcon/native builds, matrix routing, evidence levels, logs and result interpretation. | Reuse existing scripts/recorded failures; teaching does not authorize runtime or hardware. 2026-10-02: written session record/checklist [VERIFY_LEARN_01_GUIDED_SESSION_2026-10-02.md](diagnostics/VERIFY_LEARN_01_GUIDED_SESSION_2026-10-02.md) with a host-only worked example; the operator-driven live session is still open. |
| `UI-P3-01` | 3 | Focus slice implemented; broad redesign deferred | Workflow Focus and later GUI polish | Get bounded Focus visual/lifecycle verdict; defer broad New GUI/Legacy-parity redesign until functions and Studio settle. | Current Step 6 clipping belongs to S6-LIVE-01. Reuse W4B-P2-SUPPORT-AUTO, W5-U-05 and VIEW-U-02. |
| `PLAT-U-01` | 3 | Reconstruction acceptance open | Pinned inference/runtime image | Rebuild/verify pinned dependencies, backend/Bridge/Slicer/persistence and residual A-026 cancellation/lock checks against current baseline. | Approved isolated build/runtime gates; do not infer closure from launcher functionality. |
| `PLAT-U-04` | 3 | External-host/release acceptance open | Second WSL workstation and lab release | Verify exact manifest on the second direct-Engine WSL host; complete reviewed immutable release publication within approved scope. | Host availability and release authorization; A-034 residual acceptance. 2026-10-03: `LAB_RELEASE` pins candidate `lab/2026-10-03-4` (supersedes `lab/2026-10-03-3`, `-2` and `lab/2026-10-03`; native `ece3c42`, same image); Ubuntu evidence only (r26 PASS); safety notes in changelog. Next: one Windows/WSLg lab install/update and launch of this tag before labmates are told. |
| `PLAT-U-05` | 3 | External-host acceptance open | IITM CPU regression | Run documented IITM check-only regression and record result. | Requires host access; CPU remains default unless CUDA explicitly adopted. |
| `PLAT-U-07` | 3 | Source and launcher startup verified locally; migration acceptance and data exchange open | Workstation handoff and saved-case uploads | Verify representative case/image parity, shutdown, source-station local-only work and operator/cutover verdict; finish 10 remaining oversized approved bundles (7/17 uploaded). | 2026-10-03 local source: main `3997458`, native `ece3c42`; 50 host checks and check-only/GUI startup PASS, 3 packages rebuilt; no full workflow acceptance. Extensions-directory warning retained for review if extension installation is needed. Preserve September-30 notes separately. Only approved synthetic/de-identified individual cases under IITM Dentobot/Data; no whole raw tree or engineer-owned records. |
| `QA-U-01` | 3 | Aggregate evidence discrepancy unresolved | Runner/lifecycle exit diagnosis | Identify the first wrapper/lifecycle cause for nonzero aggregate exit despite isolated PASS. | Coordinate S6-U-01 without assuming a shared root cause; process exit and functional markers are distinct. 2026-10-02: only evidence is Aug 2026 source-build runs attributing exit 1 after the PASS marker to the VTK debug-leak reporter; not re-measured on the current 5.10 package (no leak/class-loader output in r14/r29/r30/r31). Next: one serialized aggregate run when runtime is free. |
| `IMG-U-01` | 3 | Representative acceptance not completed | Imaging/display uncertainty | Conclude governed CBCT mask/display review and acquisition/artifact/segmentation uncertainty evidence. | Data/reviewer availability; display overlap remains VIEW-U-01. |
| `W5-U-02` | 3 | Physical/representative acceptance not completed | Shell seating and removal | Validate support, margins, undercut/removability, shell contact/seating and terminal support on representative anatomy/phantom. | Criteria/physical fixture required; fixed S5B-TERMINAL-COLLAR defect remains closed. |
| `W5-U-01` | 3 | Physical provenance; optional manifest undecided | Guide/burr fit and manufacturing traceability | Verify actual dimensions/fit; decide optional STL checksum/revision manifest separately. | A-032 dimensional subset; export/STL never becomes Step 6 authority. |
| `POC-U-01` | 3 | Integrated physical acceptance not completed | Representative Template V0 PoC | Freeze task/thresholds, conclude software case, printing, seating/reseating, registration and total error budget. | Reuse W5-U-01/02/03, A-001/A-003/A-038; physical work needs inputs and explicit safety scope. |

## Remaining features and planned/deferred work

No execution follows from being planned. Each row identifies what is still to
be built or scoped; explicitly held items require new direction.

| ID | Priority | State | Outcome | Remaining work | Entry condition / overlap |
|---|---|---|---|---|---|
| `W4-U-01` | 2 | Design then implement | Crown Entry snapping | Define reviewed crown region/MPR contract, then source-fingerprinted snapping. | Share anatomy semantics with S6-P1-01; do not duplicate S4A-PULP-ENDPOINT. |
| `VIEW-U-02` | 2 | UX contract then implement | Mask opacity controls | Approve ownership/persistence contract; add stage-safe 2D fill/outline and 3D surface controls with CBCT parity. | Reuse Views/display owners; no separate renderer. |
| `DCP-00` | 3 | Evidence handoff not complete; blocked | Freeze backend and per-step headless coverage | Complete current-step production-path evidence inventory and backend handoff. | S6-LIVE-05 accepted; every step/save-reopen handoff headlessly automatable before Studio. Existing script index is a start, not blanket coverage. |
| `S6-P1-01` | 3 | Partially scaffolded; remaining feature planned | Anatomical safeguards | Implement bilateral condylar/crown regions, exact-source snapping and MPR/anatomical review. | Current correctness accepted; share W4-U-01 semantics. |
| `S6-P2-01` | 3 | Not implemented | Post-load integrity panel | Present Steps 1–6 Current/Needs attention/Stale/Blocked upstream/Rejected states. | Reuse existing restore/eligibility/invalidation backend. |
| `S6-P2-02` | 3 | Not implemented | Incisor-gap preview | Add smooth display-only preview and explicit commit. | S6-P1-01 accepted; reuse jaw transform. |
| `DCP-02..08` | 3 | Remaining domain work planned | Domain/session and cross-session proof | Implement only remaining contracts/proof; audit and reuse promoted foundations. | DCP-00; no rebuild of PreparedBranch/registry/shared environment/persistence. |
| `DCP-09..10` | 3 | Clean browser software and bounded native checks passed; operator UX/save/continuation review open | Project DentoCase library and case browser | Tarun reviews compact table/details and confirms manual save → scan → partial load → continuation → Save As → reopen. | Final affected host94PASS; cached1000 firstpage3.34ms/search2.18ms/details0.079ms, unchangedscan41.28ms/0archive reads; r29 full-load median22.459→17.610s (21.6% lower), matching source/resource identity. Native Qt1100×700/900×600 and synthetic paired-prefix/identity/reopen/rollback PASS, exit0, clear teardown. Loading previously operator-confirmed; final manual save/UX review remains open. Evidence: diagnostics/DENTOCASE_BROWSER_REDESIGN_2026-10-01.md; data/test-artifacts/dentocase-browser-20261001/. Resolved 2026-10-02 (Claude): `case_library.py` now uses a local `_CancelFlag` instead of `threading.Event`; `test_modular_structure` passes without a new allowlist entry. |
| `DSS-01..05` | 3 | Not implemented; on hold | Studio migration | Studio shell, Robot/Environment, Workspace, Trajectories and guarded-preview parity. | DCP-00 headless gate/data foundation; S6-WORKSPACE-PURPOSE before Workspace migration. |
| `DSS-06..12` | 3 | Not implemented; downstream | Studies/results/replay | Studies, results, historical replay and Procedure/Research separation. | DSS-01..05 guarded-preview parity; .dentocase remains package authority. |
| `W4C-U-01` | 3 | Mechanical design/closure planned | Dock/rail and robot-axis constraint | Define support-aware channels/docks/rails, collisions/tolerances and nonparallel trajectories versus one robot axis. | Registration vs load-bearing roles; coordinate A-038. |
| `ROS-U-01` | 3 | Contract not implemented | Medical-image/transform interoperability | Define narrow frame/data/ownership contract before wider ROS work. | Stable current frame requirements; reuse A-004/A-022 interfaces. |
| `S6-FDI11-DEPTH` | 3 | Case-specific investigation held | Historical drilling-contact blocker | After integrity acceptance, reconcile exact case/tool/guide and smallest Stage-3 check. | FDI21 housing-contact evidence retained; old x4/91.7% values do not authorize tuning. |
| `PLAT-U-02` | 4 | Fallback source exists; real-host regression held | Windows Steps 0–5 fallback | Verify fallback on Windows host with hidden Step 6/no automatic runtime restore. | No native Windows ROS; A-034 residual work. |
| `PLAT-U-03` | 4 | Observation deferred | CRD/GDM and renderer stability | Approved reboot/overnight availability and resource/FPS observation. | Preserve local work; A-033 renderer follow-up remains separate evidence. |
| `PLAT-U-06` | 4 | Explicitly held indefinitely | Slicer 5.12 candidate | Resume only on new explicit operator direction; preserve accepted 5.10 rollback and upgrade plan. | No candidate build/runtime/upstream integration/promotion; independent accepted-5.10 work is S6-P2-03. |
| `CASE-U-01` | 4 | Not implemented | Contaminated historical-scene migrator | Define and implement isolated offline no-ROS MRML/MRB migration. | Never load serialized ROS objects into live ROS; normal .dentocase restore has its own owner. |
| `S6-U-03` | 4 | Experimental design deferred | Observed oral-air representation | Define confidence/evidence from suitable open-mouth/phantom acquisition. | Unobserved space stays occupied/unknown; no planning authority. |
| `DHW-01..02` | 4 | Not implemented; safety/architecture gated | Hardware-session/digital-twin boundary | Prepare interface/data boundary under later explicit approved scope. | A-004/A-013; no hardware operation or drill control. |

## New planner prefix gate — 2026-10-02 (operator)

- **S6-LIVE-01, mouth-portal gate (Unprioritized; new):** virtual barrier for unsegmented lips/cheeks.
  Quadrilateral through the 4 canine crown points (FDI 13/23 upper, 33/43 lower after mouth opening;
  auto-derived cusp tips, operator-editable markups; missing canine -> first premolar, then lateral
  incisor, flagged). Best-fit plane, normal outward (Home side). Gate: planned Home->PreEntry TCP path
  must cross the plane inside the quadrilateral, outside->inside, before PreEntry. Later: tool-body
  virtual wall in the MoveIt scene. Next: implement pure geometry + gate, then wire into P1/Plan Approach.
  2 October update (source-complete, runtime acceptance open): lip line + 5 mm enlargement, gate
  enforced; 3D barrier (lip slab + cheek walls) published to MoveIt; 6.3 edge switch gum_line
  (default) / biting_edge / off; re-entry through the opening allowed. Next: r5 headed run with the
  barrier, then Tarun's verdict on the barrier shape in the viewport.

## Conditional subfeatures retained under existing owners

- **S6-LIVE-01, P3 subfeature (2026-10-02 operator supersession, source-complete,
  runtime confirmation in progress):** iterative forehead-plane Base placement by IK
  reachability preflight, ±30 mm in-plane, depth/orientation locked (logic present,
  disabled); "Find Reachable Base" stages for Review/Accept; Stage 2 connected
  confirmation classifies placement/collision/planner. See DECISIONS 2 October.
  Superseded text: failure-triggered detached Base translation up
  to ±20 mm on two reviewed oblique anatomical-plane axes. Await plane
  origin/orthonormal basis and sample budget; root↔crown direction alone does
  not define the plane. Preserve orientation, normal offset, zero baseline,
  anatomy/task/limits/policy. No automatic acceptance, Home reuse or route
  promotion; explicit Base review and fresh scene/Home/task/guard follow selection.
- **S6-LIVE-03, P4 subfeature:** future guarded reversal of an exact accepted
  partial prefix. Current policy is Block Return; reversal needs separately
  reviewed monitored-state identity, unchanged/revalidated scene, guarding and
  failure behavior before implementation.
- **UI-P3-01:** bounded Focus visual verdict is part of the implemented slice;
  broad GUI redesign remains deferred behind settled functions/Studio parity.

## External/team obligations — captured, current implementation status unconfirmed

These are preserved from the earlier authorized tracker reconciliation already
in local backlog. No engineer-owned tracker was read. Original P0/P1 labels are
source metadata, not agent execution order; do not label this work implemented
or unimplemented without current owner evidence. Keep aliases and dependencies.

| ID / aliases | Source priority / owner | Pending deliverable | Dependencies / acceptance / overlap |
|---|---|---|---|
| `A-001` / `A-015` | P0 / Tarun | Complete CBCT→template→robot-base→end-effector→tool/tooth frame contract | Planning coordinates and CAD frames; named transforms, RAS/LPS, units, calibration/uncertainty and landmark round-trip. Reuse bounded software transforms; remaining full physical chain links `S6-U-02`, `A-022`, `A-038`. |
| `A-002` / `A-028` | P0 / Tarun | Compare head-mounted and tooth-mounted registration/validation chains | Head/mount and bite-block geometry/FOV/compliance; option matrix, calibration, TRE/repeatability, remount/failure gates. Coordinate `A-001` and `A-038`. |
| `A-003` / `A-016` | P0 / Tarun | Measurable error budget and validation plan | Clinical tolerances, mechanics, metrology; imaging→printing→seating→docking→TCP→drilling errors, target/angular/depth/TRE metrics with justified uncertainty propagation. Error-budget owner for `POC-U-01`. |
| `A-004` / `A-017` | P0 / Tarun | Remaining planning/navigation/robot/tracker interface contract | Current planning/mechanics interfaces; data/frame/update-rate/ownership and gates. Reuse Slicer/ROS architecture; align future `ROS-U-01`/`DHW-01..02`, no new transport by default. |
| `A-005` | P0 / Tarun | Tooth/bite-block-mounted mechanism concepts | Open-mouth geometry and actuator/tool envelopes; 2–3 annotated concepts with datums, disposable split, access/removal. Coordinate `W4C-U-01`; physical design scope requires current team inputs. |
| `A-006` / `A-024` | P0 / P1 respectively; Tarun | Structured registration/dental robotics evidence matrix and referenced clinical-workflow papers | Paper access; auditable procedure, architecture, motion handling, autonomy, validation and status with lessons. One literature deliverable; source priority conflict must be resolved before scheduling. |
| `A-008` | P1 / Shared | Approved pneumatic POC procurement package | Specifications/quotes and professor approval; reviewed BOM/cost/vendor/owner/arrival. Overlaps `A-037` supplies; no order authorized. |
| `A-009` | P0 / Varun | Representative planning/open-mouth/full-head dataset handoff | Suitable permitted de-identified imaging, anatomy/bite-block/tool geometry; frame-labelled STL and entry/target handoff. Input for mechanics and `POC-U-01`; confirm what is already delivered. |
| `A-010` | P0 / Snekan | Head-mounted five-DoF mechanism down-selection | STL/tool/workspace/mass/force and registration inputs; 1–2 concepts with base frame. External dependency, not an agent coding assignment. |
| `A-011` | P1 / Tarun | Approved clinical observation and constraint notes | Clinic permission/consent and coordination; observation-only pen-and-paper access/irrigation/control/removal notes. No messaging, visit or recording authorized by capture. |
| `A-013` | P1 / Shared | Human-in-loop physical safety/enable/foot-pedal state machine | Clinical/registration/controller inputs and verified safety process; quality/alignment/drilling-enable/failure/retry/e-stop gates. Preserve existing simulation guards; coordinate `DHW-01..02`. |
| `A-018` | P0 / Shared | Confirm integrated demonstration scope | Team alignment on target tooth, imaging, template, autonomy and TRL-4 criteria; preserve settled software single-target contract. One scope decision set feeds `POC-U-01`; no new clinical threshold assumed. |
| `A-022` / `A-029` | P0 / Tarun | Remaining frame-aware planning-to-mechanics handoff | `A-001`, recipient CAD/controller needs; mesh/trajectory/transform package with frame metadata and round-trip landmark proof. Reuse existing callable modules and `.dentocase`; physical/export boundary overlaps `W5-U-01`, `ROS-U-01`. |
| `A-036` | P1 in register / P2 dashboard; Tarun | Internal sensing invention package | Team/ICSR input, prior-art questions and required experiment evidence; reviewable confidential outline. Resolve source-priority conflict before scheduling; no external disclosure. |
| `A-037` / `A-007` | P1 / Tarun | Pressure/acoustic transition POC and protocol | Existing datasets, sensor/plumbing/sample/ground-truth inputs; repeatable positive or negative transition evidence and preserved configuration. Includes pending live flash/Hz Config-tab acceptance of existing sensing tools; no duplicate tool build or automatic drilling/flash authorization. |
| `A-038` | P1 / Tarun | Registration fiducial concepts and physical TCP/base/TRE repeatability | Geometry/material/phantom/mechanical inputs; ≥3 concepts with frames/detection/seating risks, select a measurement experiment. Coordinate `W4C-U-01`, `S6-U-02`, `POC-U-01`; four registration features are not proof of load-bearing docking. |
| `PRODUCT-DEFERRED` | Unprioritized / owner to confirm | Tracker-deferred panoramic/curved views, camera/intraoral scan, NPU, full canal automation and extra sensing modalities | Capture only, no accepted implementation plan. Split a bounded item only if it is selected and no existing owner covers it; software UI goes through `UI-P3-01`, ROS through `ROS-U-01`. Core PoC and actual input need first. |

## Single-owner overlap rules

- **Case/restore/display:** S6-REUSABLE-CASE-SETUP owns branches/reposition;
  S6-RESTORE-ROBOT-ROS owns reconstruction; S6A-CHANGED-TARGET-GEOMETRY owns
  cleanup; VIEW-U-01 owns opened display; S6-P2-01 presents existing integrity.
  Share one invalidation backend. Display ghosts are not collision objects without evidence.
- **Assistance (A-035):** S3-P0-DENTAL-SEMANTICS owns association/candidates;
  S4A-PULP-ENDPOINT owns endpoint/line geometry; W4-U-01 owns crown Entry.
  Share anatomy semantics with S6-P1-01; no synthetic missing-pulp line.
- **Templates (A-023/A-032):** W5-U-04 construction; W5-U-03 fusion/export;
  W5-U-02 seating/removal; W5-U-01 dimensions; W4C-U-01 mechanics.
- **Reliability:** S6-P2-03 latency/progress; S6-U-01 crashes/shutdown;
  QA-U-01 aggregate wrapper. Share evidence, not assumed causes or retries.
- **Studio/studies:** DCP/DSS is the sole roadmap; superseded F0/F1/F2 and
  separate .dentostudy proposals do not restart work. Reuse accepted foundations.
- **Physical chain:** A-001 frames, A-003 error budget and A-038 metrology feed
  POC-U-01; A-004/A-022 overlap ROS-U-01 and manufacturing handoff.
- **Source aliases:** A-012/A-014/A-027 map to existing workflow owners;
  A-026 to PLAT-U-01; A-033/A-034 only retain remaining platform acceptance.
  Closed Step 3B/6.1 mirror and virtual-forehead simulation work do not reopen;
  physical metrology remains A-001/A-038. Do not build a second robot/widget.

Historical campaign narrative was relocated to
[the historical evidence archive](diagnostics/archive/step6/BACKLOG_NARRATIVE_HISTORY_TO_2026-10-01.md).
It is evidence only; this file and latest task-specific decisions control future work.


### DentoCase integration authorization — supersedes foundation hold

Operator: “no other active implementation is running, we can proceed and complete this integration now/. Use Luna max workers”; then explicitly permits up to four. DCP-09..10/S6-REUSABLE-CASE-SETUP/S6-P2-01 integration proceeds in existing checkout/branch, three available Luna Max lanes, disjoint schema/browser/projection ownership. Coordinator owns mapping, persistence activation, source review and acceptance. Snapshot/contract: diagnostics/PROJECT_DENTOCASE_IMPLEMENTATION_2026-10-01.md. No main merge, publication, robot action or inferred operator acceptance. Foundation36pass evidence preserved; integrated round trips remain required.


## 1 October — checkout correction and consolidation direction (supersedes preceding routing)

Operator corrected his earlier recollection: reviewed performance integration happened in DentoBot-step6-5.10-integration, while he continued newer development in DentoBot-step6-renovation. He now directs future implementation onto the integration branch, with Step6 development retaining the accepted performance changes. Earlier same-day assertions that integration completed into renovation, or that the newest manual watchdog session proved failure of the combined integration code, are withdrawn. The measured stalls remain valid observations; deployed-checkout attribution is unconfirmed.

Read-only Git evidence: integration/step6-5.10-reviewed-20260927 HEAD a795f89 includes immutable renovation checkpoint e7cd29f plus 14 subsequent integration commits. Renovation HEAD remains e7cd29f with substantial tracked and untracked later Step6 and DentoCase work. Integration has separate dirty documentation. Project DentoCase contract currently routes implementation to renovation; its production code is there. Neither tree may be overwritten, reset or blindly copied.

Direction: integration is the intended consolidated development target. First let the active DentoCase operation reach a stable checkpoint, preserve both complete development deltas, then reconcile renovation changes relative to e7cd29f against the existing integration corrections. Retain source-only/unaccepted states and focus verification on actual overlaps; no main promotion, runtime, 5.12 work or acceptance is inferred. The existing integration preparation contract governs transfer mechanics, superseded only as to future development target; backlog remains the sole pending queue. Performance upgrades requested the active DentoCase chat to hold further writes after its current bounded operation and report ownership/evidence before transfer. Actual transfer has not yet occurred.

## Approved consolidation — current execution scope


Tarun agrees to and approves the proposed consolidation and complete DentoCase goal, with up to four GPT-6 Luna Max workers apart from the orchestrator. Available concurrency remains three workers plus coordinator; four disjoint worker scopes are scheduled with the fourth following a released slot. This supersedes the earlier transfer hold for this bounded consolidation and moves future development to DentoBot-step6-5.10-integration, branch integration/step6-5.10-reviewed-20260927. Main promotion/publication, 5.12 and robot/hardware actions are excluded. Offline full/partial persistence verification is approved by the agreed plan; runtime resources remain serialized and existing operator processes preserved.

Git evidence: integration a795f89 already contains renovation e7cd29f; no renovation commits are missing. Later source/test changes are uncommitted. Both development deltas preserved in /tmp/dentocase-consolidation-20261001 with binary patches, development-only archives and SHA manifests; engineer-owned records/generated output excluded. Forty-two clean candidate source files applied and five conflicts resolved under coordinator dispositions. Accepted performance ports, strict restoration and method splits retained. No branch/HEAD change, stage, commit, main merge or rebuild performed during parallel work.

Owned worker scopes: robot-shell/manual method reconciliation; headed runner/source/planning tests; new case inventory ownership adapter/test; DentoCase catalog fixture correction. Coordinator owns remaining DentoCase persistence/projection/bootstrap/lifecycle/semantic inventory changes, verification matrix, source review, runtime and controlled records. No worker executes Slicer/ROS/build/runtime or edits controlled records. Current pending states remain under DCP-09..10, S6-REUSABLE-CASE-SETUP, S6-P2-01, S6-LIVE-01 and S6-P2-03. Source consolidation does not close native or operator acceptance.

**Integration-specific retained boundary:** accepted bounded Step5B numeric/visual result and module-size/API/install closure remain accepted at their recorded scope. Synthetic assisted-root fixture setup remains deferred under S4A-PULP-ENDPOINT. Mixed upgrade-branch retirement still requires retain/equivalent/defer/reject dispositions for graphics/WSLg/NVIDIA launcher changes137a56e/02eeb13, legacy jaw exception806256d, source-only probes/profiler and held5.12/resource-retriever54ef87c/e784cc2. Source stays recoverable; no wholesale promotion.
