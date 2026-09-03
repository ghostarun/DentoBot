# DENTOBOT Tasks

Last reconciled: 2026-09-03

This file is the single actionable queue. Each active item has one stable ID,
one priority, one status, and one next acceptance action. Implementation order
and workflow ownership are defined in `DEVELOPMENT_PLAN.md`; detailed decisions
and evidence are not repeated here. The full pre-cleanup issue ledger is
preserved in `archive/2026-09-01/TASKS_HISTORY.md`.

## Now — authoritative work order

| Order | ID | Priority | State | Next acceptance action |
|---:|---|---:|---|---|
| 1 | `S6-P0-01` | 0 | Operator trial passed Stage 1 (328 waypoints) and Stage 2 (18); Stage 3 remains blocked at 91.7%/42 partial waypoints. Candidate paths, display-only playback, speed control, and first-invalid classification are source/static verified; restore passed 28/28 and the new planning regression passed inside a 50-pass/1-known-AABB-failure gate | Re-run Goal 1 once, compare candidate paths, and use the first-invalid classification to resolve Stage 3. Accept only a 100% independently guarded Stage 3; keep 6.6 blocked otherwise |
| 2 | `S6-P0-02` | 0 | Operator trial proved transient reconstruction, but x4 stopped truthfully at 6.3 and initially displayed 5C. Direct Step 6 landing passed compilation and restore tests 28/28; normal-window behavior is unverified | Reload x4 and confirm Step 6 appears immediately, then verify saved workspace replay either reaches 6.5 or explains the exact 6.3 prerequisite without duplicate runtime ownership |
| 3 | `S6-P1-01` | 1 | Partially implemented; laterality, inferior direction, and retry flow corrected; anatomical subregions/MPR review missing | Add bilateral condylar and incisal/crown interaction regions, guide metrics, exact-source/MPR gates, and a representative operator trial |

## Next — queued by priority

| ID | Priority | State | Entry condition | Next acceptance action |
|---|---:|---|---|---|
| `S6-P2-01` | 2 | Planned | `S6-P0-02` checkpoint matrix understood | Implement one post-load visual integrity panel for Steps 1–6 with Current, Needs attention, Stale, Blocked upstream, and Rejected states |
| `S6-P2-02` | 2 | Planned | `S6-P1-01` accepted | Add smooth display-only incisor-gap preview and one explicit commit action |
| `S6-P2-03` | 2 | Planned | Priority-0 correctness accepted | Add shared truthful busy/progress/result/cancel behavior to long-running actions without fake percentages |
| `UI-P3-01` | 3 | Planned | Priority 1–2 correctness and interaction contracts accepted | Refine the New GUI while proving Legacy parity and zero MRML/ROS side effects |
| `S6-U-01` | 4 | Deferred reliability DENTO-NOTE. Functional connect/reload/reconnect/New Case/reconnect/save-reopen passes after the native ownership repair; only application shutdown still reports retained SlicerROS2/MoveIt VTK objects and class-loader warnings | Priority 0–3 work or an observed runtime regression no longer blocks it | Centralize native shutdown, release robot/parameter/pub-sub/MoveIt wrappers before library unload, correct test process-group cleanup, then require a zero-exit lifecycle run with no SlicerROS2 leaks |

## Unprioritized active and backlog

| ID | State | Next bounded action |
|---|---|---|
| `S6-U-04` | Fix implemented; normal-window acceptance pending. Goal 1 diagnostics **Close** did not dismiss the window before or after evidence review, forcing use of the title-bar X | Run Goal 1, open diagnostics, verify **Close** dismisses it both before and after **Mark Current Evidence Reviewed**, then reopen it and confirm no stale callback/window state |
| `S6-U-02` | Manual Simulation Base containment accepted; physical forehead/mount relationship unresolved | Obtain mount-face CAD/contact normal and define patient-contact-to-base transform, offsets, review, persistence, and invalidation |
| `W4-U-01` | Active design | Define reviewed crown region and MPR contract, then implement source-fingerprinted Entry snapping |
| `W5-U-01` | Backlog | Decide whether an optional path-independent STL export manifest is needed; never make STL Step 6 geometry authority |
| `IMG-U-01` | Representative acceptance pending | Compare authoritative masks and optional display previews on governed CBCT; define acquisition/artifact/segmentation uncertainty evidence |
| `W4-U-02` | Representative acceptance pending | Exercise trajectory selection, assisted/manual placement, oblique MPR, Step 4B support ownership/locking, save/reopen, and reference-linked backtracking on governed anatomy |
| `W4C-U-01` | Design and representative acceptance pending | Validate support-aware docks, collisions, channels, rail roles, tolerances, and the non-parallel-trajectory versus one robot-axis constraint |
| `W5-U-02` | Representative and physical acceptance pending | Validate the read-only Step 4B support pack in Step 5A, editable margin, undercut/removability, shell contact, seating, and terminal support on governed anatomy/phantom |
| `W5-U-03` | Representative acceptance pending | Run current Step 5B fusion and Step 5C PASS/WARNING/FAIL, reopen, stale-lineage, channel-preservation, and one-STL flow |
| `VIEW-U-01` | Cross-workflow normal-window acceptance pending | Exercise grouped anatomy, stage presets, manual toggles, frame/restore, opacity, CBCT rendering labels, save/reopen, and Legacy/New parity without renderer or geometry side effects |
| `S6-U-03` | Experimental design; not planning authority | Derive only confidence-labelled observed oral-air surfaces when suitable open-mouth/phantom data exists; keep unobserved space occupied/unknown |
| `CASE-U-01` | Backlog | Define and implement an offline no-ROS migrator for contaminated historical MRML/MRB scenes; never load them into a live ROS process |
| `PLAT-U-01` | Blocked by clean-image acceptance | Rebuild the pinned Ubuntu inference image and accept dependency, backend, Bridge, Slicer import, and persistence behavior without mutable-container repair |
| `PLAT-U-02` | Pending external workstation | Run Windows 11 **native Slicer** launcher, path, CUDA segmentation, cancellation, and scene-reopen acceptance |
| `PLAT-U-04` | Release candidate metadata now pins the DentoBot SlicerROS2 fork at `17f99931f54f`; the prior `lab/2026-09-02` image remains the last published image while the candidate build is pending; Windows GUI unaccepted | Build/publish the candidate image with matching OCI source/revision labels, then on one Windows 11 lab PC authenticate Docker to GHCR, run the pinned WSL installer, launch through WSLg, open DENTOWorkflow, and connect Step 6 ROS/MoveIt simulation. No hardware motion. |
| `PLAT-U-03` | Deferred observation | After an approved reboot, record overnight CRD/GDM availability and resource behavior before closing workstation stability |
| `QA-U-01` | Unresolved | Diagnose why the aggregate Slicer test wrapper returns nonzero although isolated members reach PASS; do not treat isolated PASS as aggregate closure |
| `ROS-U-01` | Future design | Define geometry-preserving medical-image and transform semantics before broadening ROS scope beyond current bounded simulation interfaces |
| `POC-U-01` | Strategic parallel lane | Freeze one narrow task and acceptance thresholds, then run representative software, print/seating, registration, and error-budget work |

## Future track

| Track | State | Gate |
|---|---|---|
| F0 evidence ledger | Planned | One reviewed V2 planning attempt and accepted Priority-0 diagnostic schema |
| F1 current-case plan-only study | Planned | F0 and truthful long-running action behavior accepted |
| E stable virtual mount/base | Planned | Physical mount-frame contract and review criteria defined |
| F2 trajectory × base study | Planned | Tracks E and F1 accepted |
| A canonical frame contract | Later | Current bounded transform contracts stable |
| G physical robot integration | Blocked by design | Registration/TRE, calibrated TCP, controller ownership, force/stop logic, and verified safety procedure |

## Recently closed or superseded

These are pointers only; complete evidence remains in the archive, decisions,
reproducibility record, changelog, and dated logbook.

| Item | Disposition |
|---|---|
| Cross-tool agentic verification protocol | V1 source/pure-contract complete 2026-09-02: one canonical protocol and resource-aware matrix serve Codex, Cursor, and Claude; runtime execution remains approval-gated and serialized |
| GitHub default / overlay / Windows-lab conversion docs | Reconciled 2026-09-02: `main` is authoritative; tag `lab/2026-09-02` and its private Linux/amd64 GHCR image are published; obsolete `81836a7` `main` was deleted; clean tag/overlay rehearsal and authenticated image pull passed. Windows WSLg GUI remains `PLAT-U-04` |
| Overlay Drive/MCP temps and nested `DentoBot/graphify-out/` | Deleted 2026-09-02; live graph stays at overlay `graphify-out/`. Launch scripts kept |
| Portable overlay `arduino-pressure/` package | Superseded; live bench is `tools/arduino-pressure/` in the DentoBot git tree |
| Host Arduino pressure fs / pipeline Config tab | Source complete 2026-09-02; `py_compile` and `--no-gui` verified; live flash/Hz click pending. Sensing-only |
| Step 6 action ownership/runtime-first ordering | Accepted and moved to the Development Plan ownership contract; no longer an active task |
| Collision object identity/audit | Runtime-accepted for the exact x4 scene; recheck only when its fingerprint changes |
| Viewer showing only internal tooth anatomy | Source-fixed and exact-package verified; remaining normal-window restore/toggle acceptance is owned by `S6-P0-02`, not a duplicate Priority-0 workstream |
| Step 6 substep split/restore deadlock | Fixed; superseded by `S6-P0-02` for checkpoint reconstruction acceptance |
| Schema-v1 bundle compatibility and orientation replay | Implemented and verified; retained as migration history |
| Goal 1 world/base Cartesian conversion defect | Diagnosed/fixed; remaining full-chain work belongs only to `S6-P0-01` |
| Earlier spindle-roll candidate planning | Superseded by spindle-locked arm-route planning; old evidence is historical only |
| Economical workflow modularization | Completed; the active ROS scene-clear abort remains only under `S6-U-01` |

## DENTO-NOTE triage and maintenance rules

- Record every new `DENTO-NOTE` once with a stable ID, affected workflow,
  evidence, impact, priority (or `Unprioritized`), and next acceptance action.
- Priority order is numeric and ascending: 0, 1, 2, 3. A documented dependency
  may execute earlier without acquiring a fabricated priority.
- Update the existing row when state changes; do not create a second active
  section, dated `Next` list, or repeated prose copy.
- Put implementation chronology in today's logbook and durable rationale in
  `DECISIONS.md`. Put exact hashes, schemas, and verification results in
  `REPRODUCIBILITY_AND_TRACEABILITY.md`.
- Move completed/superseded detail to an archive at a controlled documentation
  checkpoint. Do not delete historical evidence.
- No task is successful without recorded verification. Current approval covers
  `py_compile`, scoped pure `pytest`, and necessary production SlicerROS builds;
  Slicer/ROS/MoveIt runtime checks remain operator-led unless separately approved.
- No hardware motion, drilling, patient-facing action, or clinical/safety claim
  is authorized by this queue.
