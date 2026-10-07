# DENTOBOT pending backlog

Last reconciled: **1 October 2026**. Active checkout: `DentoBot-step6-renovation`.
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
| `S6-LIVE-01` | 0 | Workflow/UX completion reopened; host evidence retained | Five-DOF engineering workbench | Immediate action: read-only actual-versus-required6.1/6.2→6.3 diagnosis under the latest recovery contract; end with first blocker and bounded correction proposal before expanding execution. Demonstrate changedBase and Home setup/recovery in offline/connected paths before calling the requested UX complete. First operator trial failed connected Base bounds acknowledgement/unknown rollback and offline stale-placement recovery; joint rows have collapsed labels/excessive gaps. Slider layout, strict bounds diagnostics/cache lifetime and Base lock notification ordering are source-corrected; 339 affected host checks passed. Tarun authorized the guard build; renovation Release build/install verified (matching binary SHA19cdc780…6cbe6a1). Tarun retries offline Base acceptance, connected scene acknowledgement and joint layout before broader handoff review; runtime attribution/verdict remains open. Tarun tests Base/Home recovery, joint/TCP controls, failed-pose inspection, guarded outcomes, records and conditional planning/preview. 469 combined host checks passed; new layout/diagnostic rendering and native robotics verdict remain pending. | Existing r22 TCP, r26 reconciliation, r29 offline/connected Home and r30 strict reopen evidence are bounded passes; r31 retained no-endpoint evidence. No autonomous runtime for this pass; no forced planner success. |
| `S3-P0-DENTAL-SEMANTICS` | 1 | Partial conclusive acceptance | Pulp inventory, existing unlabelled masks and candidates | Finish all-tooth throughput assessment, existing-mask Case B one/two assisted-line acceptance, and anatomy/UI verdict for the 52-voxel candidate. | No associated pulp means no pulp-based line. Preserve source labels/voxels; unique HIGH association/enclosure and ambiguity guards remain. Step 4A creates no masks; added candidates currently invalidate Step 3A. |
| `S4A-PULP-ENDPOINT` | 1 | Partial anatomy/contact closure | Assisted Entry/Target geometry | Resolve whether the small candidate needs a persisted local display-surface correction; compare successful operator Entry and native/displayed contact in trajectory-aligned MPR; retain FDI31 review. | Source checks and FDI11 creation exist; small-mask smoothing/contact discrepancy is unresolved. Crown Entry feature is W4-U-01. |
| `S6-REUSABLE-CASE-SETUP` | 1 | Bounded restore verified; broader acceptance open | Reusable cases and branch ownership | Conclude changed-Base/shared 3B–6.1, branch switching, stale evidence and final post-handoff save/reopen review. | r30 strictly reopened the r29 five-DOF fixture. Source-hidden/opened-proxy save/reopen checks exist; normal-window verdict and representative final package remain open. One case-foundation/reposition lane. |
| `S6-RESTORE-ROBOT-ROS` | 1 | Implemented; representative reconstruction acceptance open | Offline and connected robot restore | Verify fresh/warm offline hydration, no auto-connect/duplicates, and explicit current-scene revalidation. | Share S6-REUSABLE-CASE-SETUP campaign. Saved Home/history is configuration only; stale forehead evidence stays stale. |
| `S6-WORKSPACE-PURPOSE` | 1 | Source implemented; yield/freshness acceptance open | Optional workspace and reviewed limits | Review ROI edits, sample yield/time, Home-inclusive limits and saved/reconnected freshness through the existing workbench. | Incisor-centered editable 200 mm TCP sampling domain is not a route/robot-link constraint; empty cloud is not impossibility. No fresh workspace framework. |
| `S6-U-01` | 1 | Reliability partially corrected | Crashes, shutdown and process cleanup | Conclude representative case-bearing clean shutdown/recording and cleanup; investigate only a reproduced causal failure under the verification protocol. | Scheduled traceback dumping was removed after r18 GDB evidence. r22/r26/r29 exited cleanly; r31 exited 1 with no native signal. Do not attribute every older crash to one cause or resume retries from stale summaries. |
| `S6-P2-03` | 1 | Partial measured correction | Responsiveness and reviewed 5.10 integration | Integrated manual trial reproduced 14 >=5 s gaps, maximum 49.144 s, with concurrent host I/O/memory pressure. Read-only trace existing workspace/static-check/route blocking boundaries and correlate ambiguous retained labels before one bounded correction. Prior integration hold is superseded by operator confirmation. | Monitoring/progress exists; native gaps and final usability verdict remain. No MRML/ROS worker thread; Slicer 5.12 remains held. |
| `S6-LIVE-03` | 2 | Source implemented; conditional native acceptance | Interruption and Return Home | Tarun verifies exact accepted-prefix retention, Incomplete/AwayFromHome latch and Block Return; separately tests completed-route Return Home and repeat when a guarded route exists. | No reset/teleport or manual-history promotion. Exact-prefix reversal is future separately scoped work, not existing recovery. |
| `S6-LIVE-04` | 2 | Source implemented; conditional native acceptance | Preview/playback and route-intent restore | Conclude speed, ordered acknowledgements, visible paths, route intent and fresh replan on a Complete route. | Requires current complete independently guarded chain; historical replay is display-only. |
| `S6-LIVE-05` | 2 | Blocked representative full-cycle acceptance | Complete software workflow | Review a suitable case/tool/guide and prove approach, drill preview, withdrawal/Home, repeat and representative final save/reopen. | Depends on upstream integrity and accepted complete route; gates DCP-00/Studio. Planner no-solution alone does not prove software defect or infeasibility. |
| `W5-U-03` | 2 | Implemented; broader workflow acceptance open | Step 5B/5C fusion and export | Conclude FDI11/FDI31 fusion, PASS/WARNING/FAIL, stale-lineage handling, channel preservation, one-STL and fresh-reopen review. | Two-target headless repair passed; current normal-window verdict remains. W5-U-04 owns construction correction; independent targets do not imply a fused multi-target template. |
| `W5-U-05` | 2 | Partial implementation | Template dimension/reset interaction | Verify section-2 editability and dimension coupling; implement/review remaining Reset and interactive sizing. | Existing floor correction is implemented; preserve >=2.0 mm guide/channel requirement and owner interfaces. |
| `VERIFY-LEARN-01` | 2 | Teaching deliverable not completed | Learn testing and verification | One guided session on scoped pytest, py_compile, colcon/native builds, matrix routing, evidence levels, logs and result interpretation. | Reuse existing scripts/recorded failures; teaching does not authorize runtime or hardware. |
| `UI-P3-01` | 3 | Focus slice implemented; broad redesign deferred | Workflow Focus and later GUI polish | Get bounded Focus visual/lifecycle verdict; defer broad New GUI/Legacy-parity redesign until functions and Studio settle. | Current Step 6 clipping belongs to S6-LIVE-01. Reuse W4B-P2-SUPPORT-AUTO, W5-U-05 and VIEW-U-02. |
| `PLAT-U-01` | 3 | Reconstruction acceptance open | Pinned inference/runtime image | Rebuild/verify pinned dependencies, backend/Bridge/Slicer/persistence and residual A-026 cancellation/lock checks against current baseline. | Approved isolated build/runtime gates; do not infer closure from launcher functionality. |
| `PLAT-U-04` | 3 | External-host/release acceptance open | Second WSL workstation and lab release | Verify exact manifest on the second direct-Engine WSL host; complete reviewed immutable release publication within approved scope. | Host availability and release authorization; A-034 residual acceptance. |
| `PLAT-U-05` | 3 | External-host acceptance open | IITM CPU regression | Run documented IITM check-only regression and record result. | Requires host access; CPU remains default unless CUDA explicitly adopted. |
| `PLAT-U-07` | 3 | Partial approved data exchange | Saved-case uploads | Finish 10 remaining oversized approved bundles and verify metadata/checksums; 7/17 were uploaded. | Only approved synthetic/de-identified individual cases under IITM Dentobot/Data; no whole raw tree or engineer-owned records. |
| `QA-U-01` | 3 | Aggregate evidence discrepancy unresolved | Runner/lifecycle exit diagnosis | Identify the first wrapper/lifecycle cause for nonzero aggregate exit despite isolated PASS. | Coordinate S6-U-01 without assuming a shared root cause; process exit and functional markers are distinct. |
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
| `DCP-09..10` | 3 | Isolated catalog/lineage foundation host-verified; integrated project pending | Project DentoCase library and case browser | Complete persistent ownership audit, independent projection, integrated browser/full-partial save/load, bounded round trips and Tarun's independent-case continuation verdict. | Foundation reviewed:36combined host passes; CLI inspect/scan/list grouped2identical copies; read-only r29inspection Valid/liveUnverified and source SHA unchanged. Seven existing production files unchanged; no schema/writer/startup/install/merge changes. Existing DCP order/current priority retained. Contract/evidence: diagnostics/PROJECT_DENTOCASE_IMPLEMENTATION_2026-10-01.md. Operator integration hold remains active. |
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

## Conditional subfeatures retained under existing owners

- **S6-LIVE-01, P3 subfeature:** failure-triggered detached Base translation up
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
