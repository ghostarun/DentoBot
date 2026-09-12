# DENTOBOT pending work and backlog

Last reconciled: 2026-09-13. **Check this file before every plan or new task.**
This is the sole pending-work queue: active, blocked, planned, deferred and
unaccepted work, including every open DENTO-NOTE. Detailed contracts live in
[TASKS.md](TASKS.md) and [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md); process and
completion rules live in [AGENTS.md](../AGENTS.md#backlog-first-gate--mandatory).
No completed-task history or execution logs belong here.

**Reading rule:** scan every section before a major plan; search IDs, synonyms,
workflow steps and overlap notes before any scoped plan. Reuse existing owners
and accepted implementation. A row marked acceptance pending requires review,
not automatic reimplementation. Table order outside the active sequence is not
new execution authority. Numeric priorities retain their recorded values;
Unprioritized stays unassigned. Dependencies and runtime/hardware gates apply.

Sources: local controlled records through 11 September and the read-only
[Project Tracker](https://docs.google.com/spreadsheets/d/1W118Z6oDqfA6IOBXg3llCo6-IowoSAif1HxuTFK7NHU/edit)
reconciled through 3 September. Tracker-only work is captured below with source
IDs and provisional status; its old dates, allocations and case diagnostics do
not override later local decisions. Tracker priorities are source metadata,
not promotions into the current development sequence.

## Pending planned work — active correction and acceptance

Current dependency sequence: `W5-U-04` → `S6-REUSABLE-CASE-SETUP` normal-window
single-target preparation/import → separately scoped explicit-pair/optional
registry acceptance → `S6-LIVE-01..05` as applicable. Optional testing is not a
requirement for the default single-target path. Step 4A review remains open in
the full preparation review. Wider Case Platform/Studio work stays behind
`S6-LIVE-05`; workspace purpose must be settled before Studio Workspace.

**Reusable-case implementation handoff:** the Case Foundation/offline-base
revision and the opened-planning-frame correction are reconciled into this
checkout. Targeted static/pure checks and the diagnostic FDI32 Slicer smoke pass;
the original saved-case integrity mismatch, current Step 5C branch acceptance,
and normal-window operator acceptance remain open. Do not repeat the source
implementation or revive the retired phantom path.

| ID | Priority | Remaining work / state | Dependency, next acceptance and overlap |
|---|---|---|---|
| `W5-U-04` | 0 | Blocked: FDI31 retains a 5-voxel fragment; FDI11 passes | Obtain approval for contributor classification, select one evidence-backed correction, rebuild once; require four open bores, zero channel occupancy and one solid, then normal-window review. Construction owner for the `W5-U-03` fusion defect; do not raise cleanup threshold. |
| `S6-REUSABLE-CASE-SETUP` | 0 | **Implemented; targeted verification passed:** schema-3 PreparedBranches bind current Step 5C evidence to Case Foundation pose; foundation-only offline save/reopen, reusable Manual Simulation Base paths, full-anatomy visibility, and opened-frame FDI32 assisted generation are implemented. The focused diagnostic Slicer run passed with screenshots; exact-package integrity, current Step 5C/PreparedBranch acceptance, and normal-window review remain open. | First resolve the supplied package's saved base-revision mismatch by explicit current save or reviewed migration, then run one current single-target `4A→4B→4C→5A→5B→5C→6` preparation/import and record the ten normal-window observations. Keep the task open until operator acceptance. Explicit pairing/optional 32 × 3 stay separately scoped. Reuse this foundation in `DCP-02..08`. |
| `S4A-PULP-ENDPOINT` | 0 | Source/focused checks pass; anatomical review pending | Deliberately regenerate legacy FDI31 assisted line; review shared native/displayed pulp contact and non-projecting slice glyphs. `A-035` internal-target subset; crown Entry remains `W4-U-01`. |
| `W4-U-02` | 0 | Smooth-display correction verified; normal-window and broader representative acceptance pending | Confirm truthful smooth on/off, CBCT/mask changes, oblique exit restoration and backtracking; distinct from missing opacity controls `VIEW-U-02`. |
| `S6-P0-BASELINE-CLEANUP` | 0 | Cleanup verified; clean-case full-loop acceptance pending | Reuse `S6-LIVE-05` review and full guarded loop; do not repeat source cleanup or revive retired-case exceptions. |
| `S6-LIVE-01` | 0 | Implemented; complete Stage-3 acceptance open | After workflow integrity, resolve reviewed case blocker with full endpoint/guard evidence; shares diagnostic owner `S6-FDI11-DEPTH`. |
| `S6-LIVE-02` | 0 | Implemented; runtime guard acceptance pending | Verify all three stages, J1–J5 guard, narrow burr exception and external-spindle boundary in the same authorized full-loop campaign. |
| `S6-LIVE-03` | 0 | Implemented; repeat-loop acceptance pending | Goal 1→Goal 2→Return Home→replan without restart; share campaign with `S6-LIVE-05`. |
| `S6-LIVE-04` | 0 | Implemented; playback acceptance pending | Confirm speed, ordered acknowledgements and visible paths in that campaign. |
| `S6-LIVE-05` | 0 | Blocked by workflow integrity and reviewed clean-case selection | Require finalized guide/tool geometry, complete guarded approach/drilling-preview/withdrawal/Home and fresh repeat. Gates P1 Studio; no hardware authorization. |
| `S6-FDI11-DEPTH` | Unprioritized | Paused: FDI21 housing contact at final drilling waypoint | After integrity acceptance, reconcile exact case/tool/guide identity and propose smallest Stage-3 check. Old 91.7%/x4 values are historical; no automatic base/depth/margin tuning. |
| `S6A-CHANGED-TARGET-GEOMETRY` | Unprioritized | Clear/save guard checks pass; clean FDI44 full workflow review pending | Verify Step 6A geometry from clean session; regenerate cross-target chains if reported. Coordinate stale-proxy ownership with reusable-case restore; do not infer mesh identity from text. |
| `S6-RESTORE-ROBOT-ROS` | Unprioritized | Offline-load contract implemented; fresh/warm reconstruction review pending | Share load campaign with reusable-case acceptance: no auto-connect or duplicate objects; saved Home is configuration only. Includes old `S6-P0-02` restore work. |
| `S3-U-01` | Unprioritized | Scan/run inspection implemented; real-scene visual acceptance pending | Review source-paired preDental/postDental switching, context, compare, rename and Step 4 handoff. |
| `S6-U-04` | Unprioritized | Diagnostics Close fix implemented; visual acceptance pending | Verify Close before/after evidence review, reopen and callback state in an authorized Goal 1 session. |

## Pending planned work — queued milestones

Accepted design intent does not authorize execution. Contract and detailed
acceptance references: TASKS.md and DEVELOPMENT_PLAN.md, under these same IDs.

| ID | Priority | Remaining outcome | Entry condition / overlap |
|---|---|---|---|
| `DCP-00` | 1 | Freeze accepted Track-A backend handoff | `S6-LIVE-05` complete. |
| `DCP-02..08` | 1 | Remaining domain/session and cross-session proof | `DCP-00`; audit/reuse accepted PreparedBranch, registry, shared environment and persistence. Never rebuild the promoted P0 subset. |
| `DCP-09..10` | 1 | SQLite DentoLibrary and case browser | Case/platform foundation accepted. |
| `DSS-01..05` | 1 | Studio shell, Robot/Environment, Workspace, Trajectories, guarded-preview migration | Data foundation; frozen Track-A behavior; `S6-WORKSPACE-PURPOSE` before Workspace migration. |
| `DSS-06..12` | 1 | Studies, results, replay, Procedure/Research separation | Guarded Preview parity; replaces old F0/F1/F2 and separate `.dentostudy` proposal. |
| `DHW-01..02` | 1 | Hardware-session/digital-twin interface preparation | Explicit later architecture/safety approval; no hardware operation. Coordinate `A-004`/`A-013`. |
| `S6-P1-01` | 1 | Bilateral condylar/crown regions, source snapping, MPR/anatomical safeguards | Current P0 accepted; shared crown semantics with `W4-U-01`, not a second anatomy authority. |
| `S6-P2-01` | 2 | Post-load Steps 1–6 integrity panel | Understand restore matrix via `S6-RESTORE-ROBOT-ROS`; reuse existing eligibility/staleness backend. |
| `S6-P2-02` | 2 | Display-only incisor-gap preview and explicit commit | `S6-P1-01` accepted; reuse existing jaw transform. |
| `S6-P2-03` | 2 | Truthful shared busy/progress/result/cancel behavior | P0 correctness accepted; coordinate Step 5B interaction and later studies. |
| `UI-P3-01` | 3 | New GUI refinement with Legacy parity | Studio functional acceptance and P1–2 correctness; consume `W4B-P2-SUPPORT-AUTO`, `W5-U-05`, `VIEW-U-02` contracts rather than duplicate them. |
| `PLAT-U-06` | Unprioritized | Investigate isolated Slicer 5.12 candidate and compatibility/performance | Follow [upgrade plan](SLICERROS2_5_12_UPGRADE.md); preserve accepted 5.10 rollback, audit fork APIs, isolated branch/build, separately approved runtime gates. |
| `PLAT-U-07` | Unprioritized | Proposed multi-workstation Git plus saved-case exchange boundary; no external data sync performed | Reuse the current Git-tracked overlay and docs-only `active-development-ubuntu` mirror. Exchange only individual synthetic or explicitly approved de-identified `.dentocase` bundles from a separately named Drive location; verify checksum/readback. Never sync the whole `Slicer_Saved` tree, raw/non-anonymized bundles, engineer-owned records, or credentials. |

## Backlog — DENTO-NOTEs, design and remaining verification

These are retained obligations; they are not automatically the next major plan.
Source observations, risks and evidence remain under the matching TASKS.md ID.

| ID | Priority | Pending outcome / observation | Dependency / next bounded action |
|---|---|---|---|
| `W4B-P2-SUPPORT-AUTO` | 2 | DENTO-NOTE: narrow two-row support arch; four-nearest support suggestion and single-row jaw UI | P0 integrity first; suggest two same-jaw teeth each side in arch order, preserve manual review/lock and edge/missing-tooth handling. UI layout integrates with `UI-P3-01`. |
| `S6-U-01` | 4 | DENTO-NOTE: non-clean native shutdown despite functional lifecycle pass | Preserve P0–3 ordering unless normal workflow regresses; release native wrappers and process group; require clean zero-exit lifecycle without leaks. Coordinate, do not assume same cause as `QA-U-01`. |
| `S6-WORKSPACE-PURPOSE` | Unprioritized | DENTO-NOTE: reported 5 mm clearance leaves no intraoral TCP workspace | Discuss 6.3 purpose; audit exact filter/consumers before any policy or value change; distinguish reach, whole-robot validity, Home connectivity and task feasibility. Prerequisite for Studio Workspace. Recommended P0 was never an assigned priority. |
| `VERIFY-LEARN-01` | Unprioritized | DENTO-NOTE: operator wants one guided, hands-on session to understand the DENTOBOT testing and verification workflow, including `py_compile`, focused `pytest`, conditional `colcon build`, evidence levels and result interpretation | Wait for the active reusable-case/Step 6 reposition implementation handoff and a stable diff. Then use one real, bounded matrix profile to teach inspect → smallest check → static compile/diff → focused pure tests → conditional package build → runtime/manual boundary. Explain each command before approval/execution, let the operator run or follow it, preserve logs/result, and finish with a short operator-readable checklist. No duplicate harness, blanket suite, robot motion or build while files/install tree are changing. |
| `W4-U-01` | Unprioritized | Reviewed crown Entry snapping/MPR contract | Define crown region, then source-fingerprinted snapping; remaining Entry subset of `A-035`. |
| `W5-U-01` | Unprioritized | Physical guide/burr fit provenance; optional export manifest | Verify actual dimensions and physical fit; decide manifest separately. Neither export nor STL becomes Step 6 authority. Includes tracker A-032 dimensional concern. |
| `IMG-U-01` | Unprioritized | Representative mask/display and uncertainty acceptance | Governed CBCT, acquisition/artifact/segmentation evidence; coordinate `VIEW-U-01` display campaign. |
| `W4C-U-01` | Unprioritized | Dock/rail mechanical design and representative acceptance | Agree registration vs load-bearing role, tolerances, channels/collisions and nonparallel trajectories vs one robot axis; overlaps `A-038` fiducial interfaces. |
| `W5-U-02` | Unprioritized | Physical/representative support, margin, undercut, shell seating/removal | Governed anatomy/phantom and criteria; includes remaining normal-window/manufacturing review after verified `S5B-TERMINAL-COLLAR`, without reopening its fixed defect. |
| `W5-U-03` | Unprioritized | DENTO-NOTE: detailed Step 5B/5C testing beyond smoke | After `W5-U-04`, review FDI11/FDI31 fusion, PASS/WARNING/FAIL, reopen, stale lineage, channels, one STL, visibility/printability. Shared construction fix stays under `W5-U-04`. |
| `W5-U-05` | Unprioritized | DENTO-NOTE: dimension coupling, missing Reset/interactive inspection, required controls hidden under Advanced | Plan Step 5B primary controls, owned geometry/parameter/stale reset, interactive sizing and upstream-lineage validation; coordinate GUI/progress plans. |
| `VIEW-U-01` | Unprioritized | Cross-workflow normal-window display acceptance | Review grouped anatomy, presets/toggles, frame/restore, opacity, labels, save/reopen and Legacy/New parity. Missing controls owned by `VIEW-U-02`. |
| `VIEW-U-02` | Unprioritized | DENTO-NOTE: lost mask 2D/3D opacity controls | Written UX plan acceptance first: map ownership, persistent stage-safe fill/outline/surface controls and CBCT parity, then implementation and normal-window trial. |
| `S6-U-02` | Unprioritized | Physical forehead/mount-frame truth unresolved | Obtain mount-face CAD/normal; patient-contact→base transform, review, offsets/persistence/invalidation. Manual Simulation Base acceptance is insufficient. Shares physical metrology lane with `A-001`/`A-038`. |
| `S6-U-03` | Unprioritized | Experimental observed oral-air representation | Suitable open-mouth/phantom data; confidence labels, unobserved space remains occupied/unknown; never planning authority. |
| `CASE-U-01` | Unprioritized | Offline migrator for ROS-contaminated historical MRML/MRB | Define isolated no-ROS migration; distinct from normal `.dentocase` offline restore. |
| `PLAT-U-01` | Unprioritized | Clean pinned inference-image reconstruction acceptance | Rebuild and verify dependencies/backend/Bridge/Slicer/persistence; reconcile A-026 residual tests and transitive lock against current Ubuntu baseline. |
| `PLAT-U-02` | Unprioritized | Native Windows Steps 0–5 fallback real-host regression | Windows host; verify hidden Step 6/no auto-restore, no native Windows ROS. A-034 residual fallback acceptance. |
| `PLAT-U-04` | Unprioritized | Second direct-Engine WSL machine acceptance and immutable lab release | Exact manifest plus approved check-only/GUI/segmentation/simulation; isolated release revision, stable/lab/tag/image publication within authorization. |
| `PLAT-U-05` | Unprioritized | IITM CPU workstation regression after NVIDIA launcher integration | Documented check-only on IITM host; keep CPU unless CUDA intentionally adopted. |
| `PLAT-U-03` | Unprioritized | CRD/GDM overnight stability observation | Approved reboot/observation; preserve work. A-033 renderer/FPS follow-up remains distinct evidence within this platform lane. |
| `QA-U-01` | Unprioritized | Aggregate Slicer wrapper exits nonzero despite isolated PASS | Diagnose first wrapper/lifecycle failure; isolated PASS is not aggregate closure. |
| `ROS-U-01` | Unprioritized | Medical-image/transform interoperability design | Frame requirements stable; geometry-preserving contract before wider ROS scope; coordinate `A-004`/`A-022`. |
| `POC-U-01` | Unprioritized | Representative software → printed Template V0 → seating/registration → error budget | Freeze narrow task/thresholds; reuse template acceptance and `A-001`/`A-003`/`A-038` metrology instead of starting separate implementations. |

## Backlog — tracker obligations missing from the local queue

All rows below are **captured pending reconciliation**, not freshly verified
status or newly authorized execution. Preserve original IDs and owners. P0/P1
values are tracker metadata; `%` suffixes were allocation, not task priority.
Obtain current inputs before scheduling; old target dates are not renewed.
Grouped alias IDs represent one deliverable owner, not parallel workstreams.

| Canonical ID / tracker aliases | Tracker priority / owner | Pending deliverable | Dependencies, acceptance and overlap |
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

## Overlaps to resolve when selecting work

| Pending scope / source aliases | Single owner and reuse rule |
|---|---|
| Tracker `A-023`, `A-032` template automation | `W5-U-04` construction; `W5-U-03` fusion/export acceptance; `W5-U-02` shell/fit; `W5-U-01` physical dimensions; `W4C-U-01` mechanics. Treat as linked acceptance slices, not a fresh template generator. |
| Tracker `A-035` trajectory assistance | `S4A-PULP-ENDPOINT` internal target and `W4-U-01` crown Entry. Old instruction to queue all assistance is superseded by later P0 correction. |
| Tracker `A-012`, `A-014`, `A-027` software/workflow umbrella | Reuse accepted Slicer architecture and implemented Steps 0–6. Remaining integration gates belong to `S6-REUSABLE-CASE-SETUP`, `S6-LIVE-01..05`, `POC-U-01` and `A-004`/`A-022` physical handoff. No architecture restart. |
| Tracker `A-026` inference robustness | `PLAT-U-01`; confirm cancellation/descendant cleanup, five old tests and lock requirements against current evidence before scheduling residual checks. |
| Tracker `A-033`, `A-034` marked complete but containing follow-ups | Retain only renderer/FPS and platform-host acceptance under `PLAT-U-03`, `PLAT-U-02`, `PLAT-U-04`, `PLAT-U-05`; migration itself stays closed. |
| Restore, stale target geometry, integrity UI | `S6-REUSABLE-CASE-SETUP` owns branch semantics; `S6-RESTORE-ROBOT-ROS` reconstruction; `S6A-CHANGED-TARGET-GEOMETRY` target cleanup; `S6-P2-01` presentation. Reuse one eligibility/invalidation backend. |
| Active reusable-case / Step 6 reposition implementation | Remains one `S6-REUSABLE-CASE-SETUP` lane. Wait for its handoff, then reconcile the actual diff and evidence before selecting residual work; do not start a second reposition, case-foundation or branch-activation implementation. |
| Track-A loop, baseline cleanup and exact FDI11 blocker | One authorized acceptance campaign can serve multiple IDs only when each gate is explicitly observed and recorded. A case-specific failure does not create another planner workstream. |
| Crown regions, jaw opening, Step 4A assistance | Agree shared source-fingerprinted anatomy semantics between `S6-P1-01` and `W4-U-01`; retain distinct workflow acceptance. |
| Studio, studies, old F0/F1/F2 | Only `DCP-*`/`DSS-*` roadmap; `.dentocase` stays package authority. No parallel `.dentostudy` store. |
| Registration, frame graph, fit and error budget | `A-001` frames, `A-002` architecture, `A-003` error budget, `A-038` metrology feed `POC-U-01`. Shared fixtures/evidence do not erase separate physical acceptance gates. |

Remove or rewrite overlap rows when their pending scope closes. Historical alias
and completion evidence belongs in TASKS.md/logbook, not as closed queue rows.
