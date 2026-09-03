# DENTOBOT Low-Level Changelog

## 2026-09-03 — Add bounded fixed-frame IK recovery for P0 Stage 3

- **Why:** MoveIt's collision-off Cartesian interpolator could stop near the
  end of the fixed Entry→Target line even when individual poses remained
  solvable, leaving Goal 1 at a truthful partial fraction.
- **Change:** After a partial exploratory Cartesian result, the bridge now
  retries the exact requested poses from the explicit start state with
  continuity-seeded MoveIt IK, deterministic small arm-seed perturbations, FK
  residual checks, continuous-joint canonicalization, and the existing J6-zero
  policy. A recovered line is still independently phase-guarded; failed
  recovery or guard validation remains blocked evidence.
- **Verification boundary:** `py_compile` and `git diff --check` pass;
  restore coverage passes 28/28. The scoped planning slice passes 50 tests and
  retains one already-known unrelated draft-AABB neutral-pose assertion failure.
  No Slicer/ROS/MoveIt runtime was run. The existing x4 91.7% result remains
  historical evidence until the reloaded candidate is exercised.

## 2026-09-03 — Pin and package the controlled SlicerROS2 repair

- **Why:** The native scene-lifetime and explicit-planning fixes were
  committed in a separate SlicerROS2 worktree, while the lab release still
  pointed at mutable upstream code and the old runtime image.
- **Change:** Published the repair on the DentoBot fork at
  `17f99931f54f1e7941d7a66b30a849d2a37baccd`, moved `Workspace/LAB_RELEASE` to
  `lab/2026-09-03`, and changed Compose to the matching candidate image name.
  The Dockerfile now records both DentoBot and SlicerROS2 source identities as
  OCI labels; the publisher rejects mismatches before a push.
- **Verification:** The image built with the exact tag/fork metadata, passed
  the publisher's fail-closed label check, and was pushed as OCI index digest
  `sha256:f71da23aaa35161730536530ed18c594ccb7766ed8d3a35cfd68d0f385280faa`.
  Windows WSLg acceptance remains pending and was intentionally not run.

## 2026-09-03 — Make Goal 1 candidate evidence inspectable

- **Why:** The operator could see 12 planner rows with equal Stage-1 waypoint
  counts but could not compare their geometry, the accepted preview took over
  a minute, and a 91.7% Stage-3 stop lost its first-invalid classification.
- **Change:** Retain candidate waypoints transiently, draw separate Stage 1/2/3
  TCP paths, animate selected complete or partial evidence only on the
  translucent goal robot, add a persistent 1×–10× workstation speed control,
  carry later-stage failure classification/position into diagnostics, make
  6.6 explain its full-chain gate, and enter Step 6 before saved-checkpoint
  reconstruction.
- **Verification:** Python compilation passed; restore tests passed `28/28`.
  Planning tests returned `50 passed, 1 failed`, with the sole failure being
  the pre-existing coarse-AABB neutral-pose assertion (`link-1`↔`link-3` at
  `0.00 mm`); the new diagnostic regression passed. Normal-window retry remains
  pending. No partial route is persisted, guarded, promoted, or executed.

## 2026-09-03 — Finalize Git/GHCR Windows-lab release metadata

- **Why:** The frozen source tag was installable, but the derived image first
  lacked GHCR authentication and inherited the upstream repository's OCI source
  label. Current documents also contained pre-publication status alongside the
  external agent's fuller reconstruction notes.
- **Change:** Published the private Linux/amd64 runtime with DENTOBOT
  source/revision/version labels, made future publisher runs reject a wrong
  source label, and reconciled current setup/architecture/task status without
  deleting the earlier chronological record.
- **Verification:** GHCR index digest is
  `sha256:46da2708dee8ecb764555e236a25b91a7b88e3a973ca79eeaa9527be4a2c468d`;
  authenticated pull passed. A clean temporary install detached DENTOBOT at
  `17af3d8`, detached SlicerROS2 at `4ef3d5b`, and reconstructed the overlay.
  Windows WSLg/Slicer/ROS remains the next operator trial. Package visibility
  remains private; no hardware action or Drive sync occurred.

## 2026-09-02 21:10 IST — Overlay, Windows-lab, and pressure reconstruction docs

- **Why:** Operator notes on the overlay restructure, GitHub `main` retarget,
  Windows WSL lab conversion, and pressure `fs` vs host filters were split
  across chat and dated logbook entries; SETUP/REPRO needed a single
  reconstruction path.
- **Change:** SETUP now has a numbered Windows 11 lab procedure and a
  source/image/cache table; Ubuntu overlay bullets name `main`, tag
  `lab/2026-09-02`, `docs-legacy/`, archive demo, and the in-repo Arduino
  bench. REPRO records overlay reconstruction, Windows-lab pins, and
  `pipeline.json` reconstruction. DECISIONS record `main`/lab-tag authority
  and that digital τ—not `fs`—quiets EMI. HOST_LAYOUT remains the overlay
  map. No Drive sync.
- **Verification:** Documentation-only. No GHCR push, Windows lab PC trial,
  Arduino flash, serial open, Slicer/ROS runtime, robot motion, or Git
  commit.

## 2026-09-02 20:26 IST — `main` authority and lab tag publication

- **Why:** The accepted Step 6/export tree replaced the obsolete GitHub
  `main`, but the local checkout still had a single-branch-style fetch map and
  no upstream; live documentation also named the retired integration branch
  and described the now-published lab tag as absent.
- **Change:** Made local `main` track `origin/main`, restored the standard
  all-origin-branches fetch mapping, aligned `origin/HEAD`, and updated live
  branch/release references. `lab/2026-09-02` is published at `17af3d8`; the
  GHCR image remains deliberately unpublished.
- **Verification:** Remote `HEAD`, `main`, `integration/gui-step6`, and the lab
  tag were queried directly; all resolve to `17af3d8`. Local ahead/behind is
  `0/0` before this documentation commit. No branch deletion, image push,
  Slicer/ROS runtime, hardware motion, or Drive sync was performed.

## 2026-09-02 19:40 IST — Windows lab WSL2 SlicerROS2 export scripts

- **Why:** Lab PCs on Windows need the current DENTOWorkflow including Step 6
  ROS, which native Windows Slicer cannot host.
- **Change:** Added `Workspace/LAB_RELEASE` and WSL install/update/launch
  scripts plus GHCR publish helper. Lab layout is documented in
  `Workspace/HOST_LAYOUT.md` and SETUP. Native `launch-dentoworkflow.ps1`
  is unchanged. No git tag, commit, or image push.
- **Verification:** `bash -n` on the new scripts; `install-lab-wsl.bash
  --check-only` parses the pin; `update-lab-release.bash --check-only`
  refuses the maintainer `integration/gui-step6` worktree;
  `launch-dentoworkflow.bash --check-only` still passed (GUI skipped).
  Windows WSLg/Docker GUI is unaccepted (`PLAT-U-04`). No robot motion,
  Drive sync, commit, or image push.

## 2026-09-02 18:30 IST — Drive/MCP scratch and nested graphify-out

- **Why:** Overlay Drive/MCP JSON leftovers and a second `graphify-out/`
  inside the DentoBot checkout were regenerable scratch, not source.
- **Change:** Deleted overlay `.tmp_*` / `.mcp_*` / `.upload_*` /
  `.drive_upload_*` JSON and DentoBot `.drive_upload_text/` plus
  `.drive_upload_b64_*.txt`. Removed nested `ros2_ws/src/DentoBot/graphify-out/`
  (~37 MB) and untracked its two accidental git entries. Ignored
  `graphify-out/` and Drive dumps in the DentoBot `.gitignore`. Kept all
  `Workspace/scripts/` launchers and `Infrastructure/` close-day/backend
  scripts. Left Docker-owned `__pycache__` / `.pytest_cache` in place
  (root-owned; regenerate on next container run).
- **Verification:** overlay temps gone; nested graphify directory absent;
  `git ls-files graphify-out` empty; overlay `~/dentobot/graphify-out`
  retained. Overlay `graphify update .`: 6,659 nodes, 10,539 edges, 626
  communities. No commit, Drive sync, robot motion, or serial open.

## 2026-09-02 18:14 IST — Host overlay cleanup and in-repo Arduino bench

- **Why:** Duplicate Arduino packages and a second docs/demo tree made the
  overlay unreadable. The live bench was outside the DentoBot git checkout.
- **Change:** Live pressure scripts now live at `tools/arduino-pressure/`
  in the DentoBot repo, with a `~/dentobot/tools` symlink. Removed
  `ros2_ws/src/Arduino/` and the overlay `arduino-pressure/` package.
  `--port` / `--list-ports` are on the in-repo copy. Stale `DentoBot/docs`
  is `docs-legacy/`. Frozen `DentoBot-demo-aff8b2e` is under
  `~/dentobot/archive/`. `pressure_runs/` is gitignored. See
  `Workspace/HOST_LAYOUT.md`.
- **Verification:** `pressure-env` `py_compile` on the moved modules;
  `pressure_monitor.py --help`. Live serial/GUI was not re-run.

## 2026-09-02 18:10:02 IST (UTC+05:30) — Pressure fs and pipeline Config tab

- **Why:** sampling rate was assumed in docs (“1 kHz”) but never paced,
  displayed, or editable; the live `.ino` was still 10-bit / 115200 / ~100 Hz.
- **Change:** paced 14-bit `seq,micros,raw` firmware with `RATE <hz>` (default
  1000 Hz from MPX5700 tR=1 ms). Shared `pressure_config.py`; live **Config**
  tab; always-on set vs measured fs strip; `pipeline.json` per run; analysis
  Pipeline tab can redetect with filter taus. Portable `arduino-pressure/`
  copy updated.
- **Verification:** `pressure-env` `py_compile`; `--no-gui` on an existing
  run; offscreen analysis GUI shows Hz. No Arduino flash or `/dev/ttyACM0`
  open. Sensing-only.
- **Pending:** operator flash of the UNO R4, then confirm measured ≈ set fs.

## 2026-09-01 20:18 IST — Saved Step 6 checkpoint resume

- Added a post-integrity-load, simulation-only resume transaction for packages
  containing Step 6 evidence. It reconstructs the local robot, reconnects
  ROS/MoveIt, reapplies Task Home, replays saved workspace evidence, and
  reconfirms the immutable task before selecting 6.5.
- Partial or stale checkpoints and unavailable external stacks stop at the
  first truthful substep with an explicit reason. ROS nodes, MoveIt plans,
  publishers/subscribers, guard sessions and active runtime flags remain
  excluded from `.dentocase`; 6.6 still requires a fresh complete Goal 1 plan.
- Full pure suite after the change: `131 passed, 1 deselected`; Graphify
  refreshed to 5,420 nodes, 8,610 edges and 402 communities; `git diff --check`
  passed. Normal-window package-resume acceptance remains pending.

## 2026-09-01 19:26 IST — Stage-1 fixed drilling-frame full-chain selection

- Made Stage 1 commit the complete FK-derived tool frame at PreEntry. The
  approved Entry→Target vector fixes tool +Z; the remaining arm-frame rotation
  is fingerprinted and reused without change in Stages 2 and 3.
- Corrected Stage 3 and diagnostics, which still discarded the selected frame
  and substituted the retired canonical `0°` roll.
- Changed direct/seeded branch selection from first Stage-2 success to bounded
  full-chain evaluation. Complete guard-accepted chains rank first; then the
  planner minimizes normalized joints-1–5 motion after PreEntry. Partial
  branches retain their actual blocked stage/fraction and may provide only a
  provisional Stage-1 preview.
- Added fixed-frame identity/status to the diagnostic session and Goal 1/Goal
  2 façade results. J6 remains compatibility-only at `0 rad`; collision and
  phase-guard policy is unchanged.
- Updated the narrow source-contract test for committed-frame propagation and
  full-chain-before-selection. With approval, the focused suite passed `45`
  tests with one unrelated draft-AABB assertion deselected; edited Python files
  compiled and `git diff --check` passed.
- The isolated exact-x4 ROS/MoveIt/Slicer smoke run emitted
  `DENTOBOT_STEP65_EXACT_CASE_PASS` with 55 guarded Home→PreEntry waypoints,
  J6 fixed at `0 rad`, a unit tool axis and a non-empty frame fingerprint.
  Full-chain status remained `Blocked` at Stage 2 after `50.0%` because MoveIt
  reported forbidden `link-3`↔tooth contact. No partial path was promoted.
- The Slicer process printed the known VTK/class-loader teardown warnings after
  the PASS marker; this remains separate lifecycle evidence. The AST-only
  Graphify refresh was rerun after the final source/test edits and rebuilt
  `graphify-out` with 5,414 nodes, 8,600 edges and 391 communities.

## 2026-09-01 16:21 IST — Exact-case spindle-lock runtime and causal Stage-2 block

- Corrected package hydration so legacy Task Home migration is read-only until
  the explicit 6.2 save action; loading no longer mutates confirmed lineage
  during post-bind validation.
- Corrected runtime workspace samples to retain `(joint name, SI value)` pairs;
  transition-build six-value samples are normalized on first use.
- Removed an artificial `74.6 deg` PreEntry→axis discontinuity. The selected
  J6-locked endpoint now derives its actual tool-axis roll from FK and carries
  that orientation into Stage 2 instead of overwriting it with the retired
  `0 deg` candidate constant.
- Goal 1 now checks the strict-axis reach of each bounded PreEntry arm branch
  before choosing the route. Endpoint reachability alone is not sufficient.
- Exact x4 ROS/MoveIt assertions emitted
  `DENTOBOT_STEP65_EXACT_CASE_PASS`: 55 guarded Home→PreEntry waypoints,
  preview complete, one Stage-1 path, and J6 exactly `0 rad`. Full task remains
  truthfully `Blocked` at Stage 2: the collision-aware axis reaches `50.0%`
  before MoveIt reports forbidden `link-3`↔tooth contact. No burr exception,
  partial-path promotion, collision relaxation, Goal 2, Execute, or hardware
  path was enabled.
- Focused pure suite passed (`62 passed`, one unrelated all-zero draft-AABB
  assertion deselected). The Slicer process still returns `1` after its
  explicit PASS while printing known VTK/class-loader teardown leaks; this is
  retained lifecycle evidence, not a planner-pass claim.

## 2026-09-01 15:29 IST — Spindle-locked, full-chain Step 6 planning

- Kept the pneumatic spindle in the six-joint compatibility schema but locked
  all planning, restore, workspace, guard and persistence state to `0 rad`.
  The C++ guard rejects nonzero ordinary and phased commands.
- Replaced eight routine axial-roll candidates with canonical direct,
  workspace-seeded and reviewed clearance-detour arm-route evidence.
- Added a non-mutating C++ phase-guard preflight over the composed
  Home→PreEntry→Entry→Target chain. Full task is `Complete` only when all
  stages pass; later failure retains a provisional approach preview and exact
  blocked-stage evidence. Goal 2 no longer replans independently.
- Added separate Stage 1/2/3 diagnostic summary and colored display-only TCP
  paths. Old nonzero spindle Homes migrate without changing joints 1–5 and
  invalidate roll-dependent evidence.
- Verification: focused host tests `46 passed`; Python compile/diff checks;
  container `dentobot_moveit_config` build passed. Normal-window full-chain
  acceptance remains pending. Hardware and Execute remain unavailable.

## Purpose

This file is the append-oriented, textual version history for DENTOBOT. It
records material source, documentation, configuration, dependency, model, and
accepted-specification changes in enough detail for an AI coding agent or a
researcher to reconstruct how the repository evolved.

Every entry must contain an explicit date, time, and timezone. One timestamp
may cover a cohesive change batch when separate timestamps would be redundant.
Retrospective entries must state when they were recorded and whether the
original event time is unknown. Do not include patient identifiers, secrets,
or credentials.

Use newest-first ordering. Each entry should state:

- what changed and why;
- files or subsystems affected;
- behavior added, removed, preserved, or superseded;
- verification performed and its environment;
- limitations, pending validation, and whether anything was reverted.

## 2026-09-01 13:38:45 IST (UTC+05:30) — Pressure analysis plots can fill the window

- **Why:** the inspector locked traces to a short wide strip above four stacked
  tables, so micro time windows were unreadable on the 0–250 kPa axis.
- **Change:** `ros2_ws/src/Arduino/pressure_analysis.py` now uses a splitter and
  a tabbed table panel. **Plots only** (F11) hides tables; **Show** isolates one
  trace; double-click a plot does the same. **Auto Y** scales to the visible
  window. Zoom resamples that interval at full CSV density. Portable copy
  `arduino-pressure/pressure_analysis.py` matches.
- **Verification:** `pressure-env` `py_compile`; `--no-gui run_20260831_181522`
  (40264 samples, 0 redetected tissue events). Offscreen GUI: Plots only grew
  the plot pane 655→823 px and hid tables; ΔP focus hid the other traces; a
  0.2 s zoom showed 232 points at stride 1. No live display click. Sensing-only.
- **Pending:** operator click on a physical display. No Git/Drive unless asked.

## 2026-09-01 04:06:00 IST (UTC+05:30) — Goal 1 PreEntry preview acceptance

- **Why:** the exact `dentobot-case-step6x4.dentocase` could produce valid
  collision-aware PreEntry IK endpoints, but the strict Cartesian terminal
  segment to Entry still returned a partial fraction. The operator needed a
  truthful, reviewable Goal 1 milestone instead of an empty plan or a false
  drilling preview.
- **Change:** `DENTORobotWorkflowFacade.planApproachPhase()` now preserves a
  complete strict Task-Home→PreEntry MoveIt plan as a successful, guarded
  `PhasePlan` when the terminal axis segment is blocked. It records the exact
  terminal fraction/error in the V2 diagnostic session, marks Stage 2 as
  `DeferredAtPreEntry`, leaves Entry and Goal 2 unavailable, and keeps the
  selected axial-roll branch and collision checking intact. The focused exact
  case smoke harness now handles packages without a pre-existing immutable
  snapshot and reports the live reconfirmed fingerprint safely.
- **Verification:** rebuilt/installed `slicer_ros2_module`; Python compile
  passed; focused facade/bridge/state/config tests passed (`48 passed`); a
  clean ROS 2/MoveIt stack and Slicer/Xvfb exact-case run emitted
  `DENTOBOT_STEP65_EXACT_CASE_PASS` with 55 strict waypoints, complete guarded
  PreEntry preview, and `goal2_deferred=true`. No hardware or execution path
  was enabled. `graphify update .` was attempted and remained blocked by the
  local watcher `Operation not permitted` error.
- **Pending:** terminal PreEntry→Entry reachability and Goal 2 drilling
  preview still require a valid collision-aware route; the fallback never
  promotes a partial Cartesian path or disables collision checks.

## 2026-09-01 04:25:00 IST (UTC+05:30) — Goal 1 stabilization postmortem and sync contract

- **Outcome:** Goal 1 now reaches the collision-free PreEntry milestone on the
  exact saved x4 case and displays the guarded TCP waypoint path. The clean
  ROS 2/MoveIt run produced 55 strict Home→PreEntry checkpoints, completed the
  guarded preview, and passed the path-model assertion. This is a PreEntry
  acceptance, not an Entry or drilling acceptance.
- **Main causes:** a valid IK endpoint was mistaken for a reachable connecting
  path; repeated attempts reused one distant joint branch; continuous-joint
  angle representations made equivalent goals look like large moves; the
  collision audit expected source IDs while transient proxies published
  display IDs; and a partial terminal Cartesian fraction could be mistaken for
  a usable plan. First-connect also seeded the cyan ROS robot at a default pose
  instead of the saved Task Home.
- **Fixes:** explicit Task-Home start ownership; shortest-angle normalization
  for continuous J5/J6; eight bounded axial-roll IK candidates ranked by Home
  continuity; bounded 6.3 clearance detours; canonical collision-proxy IDs
  with stale-ID cleanup; V2 diagnostics with stage, roll, joint-delta,
  last-valid, and sampled-collision evidence; fail-closed partial-path
  handling; and a transient TCP polyline from the same KDL FK/base transform
  as the robot preview.
- **Superseded:** three identical planner retries, endpoint-only success
  claims, partial Cartesian promotion, default-ROS first connection, and
  routine ROS ownership in 6.4. Connect/audit belongs to 6.1; 6.4 is
  confirmation-only; ROS objects and phase paths are not saved in `.dentocase`.
- **Verification:** focused host tests passed (`48 passed`), edited Python
  modules compiled, `git diff --check` passed, and the clean exact-case
  Slicer/Xvfb runtime emitted `DENTOBOT_STEP65_EXACT_CASE_PASS`. Known
  shutdown VTK/class-loader leak warnings remain lifecycle evidence only.
- **Next:** recover the strict PreEntry→Entry terminal route using V2
  diagnostics, then accept complete Goal 1 Entry before enabling Goal 2.

## 2026-09-01 03:48:00 IST (UTC+05:30) — Saved-Home bootstrap and J2 extended-zero URDF

- **Why:** a restored `.dentocase` reconstructed the grey MRML robot at its
  saved Task Home, but the first 6.1 connection created the cyan ROS robot at
  its default joint vector. Applying Home, disconnecting, and reconnecting hid
  the defect. J2 also used the opposite mechanical endpoint as zero.
- **Change:** 6.1 now selects a base/resource-current saved Task Home as its
  transient initial joint vector and reports the bootstrap source, while 6.2
  remains mandatory for live validation. The URDF moves J2's origin to the
  former `q=0.08 m` pose and reverses its axis so extended/home is `q=0` and
  `q_new=0.08-q_old`. The UI names the convention explicitly.
- **Compatibility:** package restore accepts only the exact tracked former
  URDF hash for automatic conversion. It converts saved/display J2 and task
  bounds, preserves the physical pose and base, rewrites Home against the new
  profile as `Unreviewed`, and invalidates workspace, collision, confirmation,
  and motion evidence. Other robot-profile differences remain blocked. The
  previously selected J1/J3/J5/J6 offsets were already absorbed into URDF
  origins and remain zero-valued defaults.
- **Verification:** implementation and read-only source/diff inspection only.
  Per operator policy, no syntax check, build, Slicer, ROS, MoveIt, test,
  preview, execution, or hardware action was run. Focused verification awaits
  explicit approval.

## 2026-09-01 02:43:00 IST (UTC+05:30) — Goal 1 branch selection and causal failure feedback

- **Why:** the first operator run through the runtime-first 6.1–6.4 flow
  reached Goal 1, displayed a valid PreEntry IK robot, then received an empty
  strict OMPL trajectory and only a generic `-99999` error. The reported
  `6.25726 rad` maximum delta did not name the joint or distinguish angle
  representation, swept collision, IK branch, or planner search failure.
- **Change:** `DENTOROS2Bridge.py` now canonicalizes only the tracked URDF's
  continuous spindle joint relative to Task Home, reports requested/submitted
  vectors plus raw/effective per-joint deltas, and can inspect the first exact
  MoveIt collision pair along a guard-resolution direct joint chord without
  promoting it as a plan. `DENTORobotWorkflowFacade.py` solves a bounded set of
  collision-aware PreEntry axial-roll IK endpoints, ranks them by normalized
  Home continuity, submits up to three distinct strict plans, keeps the chosen
  roll through the axis/contact/drilling preflight, and makes the translucent
  goal robot show the selected endpoint.
- **Preserved:** collision geometry, 1 mm research clearance, Task Home,
  immutable task, non-tool/self/world collision policy, partial-plan rejection,
  hidden Execute, and hardware prohibition are unchanged. Bounded full-turn
  joints are not wrapped through their URDF limits.
- **Verification:** source implementation and read-only diff review only. Per
  operator instruction, no syntax check, build, Slicer, ROS, MoveIt plan,
  preview, test, execution, or hardware action was run. Local `graphify update
  .` was attempted at both workspace and checkout roots but failed with
  `Operation not permitted`; the pre-edit graph query remains navigation-only.

## 2026-09-01 02:35:00 IST (UTC+05:30) — ΔP / change-point pressure detector

- **Why:** The 2 s residual detector treated air-off→~225 kPa spin-up as
  the main PEAK, and the p10–p90 fill hid cutting steps.
- **Change:** `pressure_filter.py` adds median + fast/slow LPF, ΔP,
  filtered dP/dt, air-spinup gating, DENTIN-armed step/transient events,
  and stage statistics. Live GUI is four linked plots. New CSV columns
  keep raw pressure. Old runs still load. Cues/annotations unchanged.
- **Verification:** `pressure-env` `py_compile`; synthetic 225→218 kPa
  dentin step reported as STEP −6.9 kPa at ~2.26 s with no spin-up event;
  `--no-gui run_20260831_181522` loaded 40264 samples, 0 redetected
  tissue events (no DENTIN annotation). Live serial/GUI not run.

## 2026-08-31 23:27:00 IST (UTC+05:30) — Restored Stage diagnostics and F0/F1/F2 study roadmap

- **Why:** the controlled tracker had compressed the multi-tooth/base study
  into one future line, obscuring the original distinction between completing
  Priority-0 single-trajectory truth, manually aggregating reviewed evidence,
  automating a current-case single-base study, and later varying base poses.
- **Change:** Development Plan and Tasks now require
  `MotionDiagnosticSessionV2` with Stage 1/2/3/full-task candidate evidence and
  a V1 reader; define evidence-only `.dentostudy` F0 manual aggregation; define
  F1 plan-only current-case automation with atomic per-result save and truthful
  progress; and reserve F2 trajectory × base studies until Track E. Decisions,
  Architecture, Project Context and Traceability record the same
  `.dentocase`/`.dentostudy` authority boundary.
- **Verification:** documentation reconciliation only. No source code, build,
  test, Slicer, ROS, MoveIt, preview, execution or hardware action was run.
  F0/F1/F2 implementation remains unauthorized until their recorded entry
  gates are met.

## 2026-08-31 22:42:00 IST (UTC+05:30) — Locked Step 6 action ownership and split 6.1 from 6.4

- **Why:** after moving runtime establishment ahead of Home/workspace
  validation, the programmatic panel still reused one card in 6.1 and 6.4.
  This visibly exposed Connect/Disconnect in task confirmation, left collision
  repair in 6.4, and allowed runtime and confirmation messages to overwrite
  each other. Disconnect there would invalidate exactly the live evidence 6.4
  needs.
- **Change:** split the shared panel into a 6.1 runtime card and a separate 6.4
  confirmation card; moved planning-scene audit controls to 6.1; separated
  runtime and confirmation statuses; disabled the hidden XML runtime controls;
  and added a panel action-owner map that rejects a callback outside its active
  substep. Added one authoritative 6.0–6.6 ownership/progress/acceptance ledger
  to the Development Plan and reconciled Architecture, Decisions, Project
  Context, Tasks, Traceability, Agent Context, and this logbook.
- **Verification:** Graphify refreshed to 8,482 nodes and 13,243 edges. With
  explicit approval, the isolated `slicer_ros2_module` rebuild completed one
  package in 27.4 seconds; the four affected Python modules passed
  `py_compile`; and both source repositories passed `git diff --check`. The
  host checks emitted non-fatal sandbox stream-descriptor warnings but returned
  zero with no Python or Git diagnostics. No Slicer/ROS call, planning request,
  preview, execution, or hardware action was run. Operator runtime acceptance
  remains pending.

## 2026-08-31 22:15:00 IST (UTC+05:30) — Explicit-state FK ownership and visible Task Home completion

- **Why:** the operator's manual 6.3 retry passed the earlier false TCP-goal
  prerequisite and began producing the workspace cloud, then stopped because
  native MoveIt FK could not obtain a live current-state `RobotState`. The
  candidate joint vector was already explicit, so coupling FK to asynchronous
  current-state monitoring was incorrect. Separately, successful Task Home
  application was easy to mistake for no action because its detailed result
  could be replaced during the next UI refresh.
- **Change:** SlicerROS2 explicit-state FK and explicit-start joint planning now
  obtain the immutable MoveIt robot model and construct their own RobotState
  containers, apply the submitted joints, update, check group bounds, and then
  compute FK or submit the start state. Step 6 restores the full Home action
  result after refresh and reports success in the card, status bar, and a
  confirmation dialog. A Priority-2 DENTO-NOTE records the broader shared
  progress/running/completion contract for long-running UI actions.
- **Verification:** none yet. Per operator instruction, no build, static check,
  Slicer/ROS request, planning request, preview, or hardware action was run.
  The isolated native package rebuild and bounded static checks require the
  operator's explicit approval; the subsequent runtime retry will be performed
  manually in a fresh Slicer session.

## 2026-08-31 19:24:00 IST (UTC+05:30) — Runtime-first Task Home and workspace source completion

- **Why:** Step 6 still treated direct strict-guard interpolation as a Home
  transition and persisted a workspace as static-valid without distinguishing
  whether MoveIt could reach representative samples from Home.
- **Change:** `DENTORobotWorkflowFacade` now reads the monitored current state,
  requests an explicit-start MoveIt plan to a different saved Home, and submits
  every returned waypoint to the strict simulation guard before marking Home
  live-valid. Workspace generation retains MoveIt FK/static-valid provenance
  for every accepted point and separately plans a deterministic bounded
  13-sample Home-connectivity set. The nested evidence persists in the existing
  optional assisted-limit JSON; ROS objects, plans, and session-valid keys do
  not. Legacy and Shell gates/status text now report the same distinction.
- **Native diagnostics:** SlicerROS2 explicit-start planning accepts bounded
  refresh/attempt/time context through the bridge and reports human-readable
  early failures and MoveIt error names/codes instead of only an empty
  trajectory.
- **Verification:** after explicit approval, both repositories passed
  `git diff --check` and the five edited Python files passed `py_compile` with
  bytecode redirected to `/tmp`. The isolated `slicer_ros2_module` build first
  exposed that pinned MoveIt lacks both attempted `hasVariable()` APIs in the
  earlier FK source; membership was changed to `RobotState::getVariableNames()`
  and the final build/install passed. No Graphify refresh, Slicer, ROS, plan
  request, preview, or hardware action was executed. The operator runtime trial
  requires separate approval.

## 2026-08-31 19:21:00 IST (UTC+05:30) — Portable Arduino pressure folder

- **Why:** Another PC needs the pressure monitor and post-processing
  without the DENTOBOT tree, while the lab scripts stay free for a live run.
- **Change:** Added `arduino-pressure/` with copied Python modules, a
  protocol-matching UNO R4 sketch, `requirements.txt`, and one Ubuntu/
  Windows README. Live files under `ros2_ws/src/Arduino/` were not edited.
- **Verification:** `pressure-env` `py_compile` on the package modules;
  `pressure_monitor.py --help` and `--list-ports`; `pressure_analysis.py
  --help`. Live USB/GUI on a second PC was not run.

## 2026-08-31 18:56:00 IST (UTC+05:30) — Combined Start Recording + looping auto cues

- **Why:** Stage cues needed a metronome once a run starts, without a
  second start control, while Space/click skip remains available.
- **Change:** **Start Recording + Cues** opens the run folder and starts
  an adjustable timer (default 10 s). Order loops AIR OFF → DRILL IN AIR →
  DRILL IN DENTIN → DRILL IN PULP until **Stop Recording**. Manual Space
  skips ahead and resets the countdown. Interval changes mid-run retune
  without an extra cue. `samples.csv` unchanged.
- **Verification:** `pressure-env` `py_compile` on monitor and
  `pressure_annotate.py`; `next_cue_key` loops the four stage keys twice.
  Live serial/GUI click acceptance was not run.

## 2026-08-31 18:39:00 IST (UTC+05:30) — Stage cues and latency-corrected annotations

- **Why:** The experiment needs a driller cue (air/dentin/pulp) and a
  separate annotator mark. The button lags the tissue-boundary dip.
- **Change:** Live monitor adds CUE NEXT STAGE (Space, beep+flash) and
  AIR OFF / DRILL IN AIR / DRILL IN DENTIN / DRILL IN PULP (F1–F4).
  `annotations.csv` stores press, latency (default 400 ms), and corrected
  time. Analysis overlays those marks and matches the nearby 50 ms median
  drop. `samples.csv` is unchanged.
- **Verification:** `pressure-env` `py_compile` plus a headless dip-match on
  `run_20260831_181522` (see logbook). Live GUI/beep click acceptance was
  not run.

## 2026-08-31 18:35:00 IST (UTC+05:30) — Median/envelope live plot and load boundaries

- **Why:** The 1 kHz overview is a filled band; contact and breakthrough
  steps were not readable. Helpers in `pressure_signal.py` were not wired.
- **Change:** Default **Trace → Median + envelope** on the live monitor and
  analysis inspector (50 ms median, p10–p90 fill). Vertical marks and an
  analysis table show contact, air/breakthrough, and held ≥20 kPa inner
  steps. The 1 s inset keeps raw under the overlay. `--no-gui` prints the
  boundaries. CSV unchanged.
- **Verification:** `pressure-env` `py_compile` on monitor, analysis,
  `pressure_signal.py`, and `pressure_plot.py`. Headless boundaries on
  today's runs (see logbook). Live serial/GUI click acceptance was not run.

## 2026-08-31 18:25:00 IST (UTC+05:30) — Air-off / air-on display filter

- **Why:** Today's drilling CSVs are bimodal (~0 kPa air-off vs ~225 kPa
  air-on / drill-in-air). Idle samples hide the plateau and mix two states.
- **Change:** `pressure_signal.py` classifies air-off with 50 ms median
  hysteresis (8 / 25 kPa, optional Otsu-style auto gates). Live monitor
  **Air** combo defaults to hide air-off; analysis `--no-gui` prints the
  fraction and the GUI has the same filter plus **Auto air gates**. CSV
  columns are unchanged.
- **Verification:** `pressure-env` `py_compile` on monitor, analysis, and
  `pressure_signal.py`. Headless classification on `run_20260831_181522`,
  `180819`, and `180324` (see logbook). Live serial/GUI click acceptance was
  not run.

## 2026-08-31 18:22:00 IST (UTC+05:30) — Live 1 s inset and optional live-only view

- **Why:** The whole-run 1 kHz trace fills the plot; operators still need the
  overview and a readable live waveform.
- **Change:** `pressure_monitor.py` defaults to overview plus a 1-second
  picture-in-picture inset (full-rate last second, orange region on the
  overview). **View → 1 s live only** uses the main plot for that window.
- **Verification:** `pressure-env` `python -m py_compile` on
  `pressure_monitor.py` passed. Live serial/GUI click acceptance was not run.

## 2026-08-31 18:14:00 IST (UTC+05:30) — Pressure-run CSV loader and dip inspector

- **Why:** Saved `samples.csv` / `events.csv` needed a review path that does
  not reopen serial and can find dips after a recording that started mid-event.
- **Change:** Added `ros2_ws/src/Arduino/pressure_analysis.py`. It loads a run
  folder, overlays live baseline/thresholds, redetects DIP/PEAK with the live
  algorithm, filters sub-20 ms glitches, and reports sequence gaps and ADC
  rails. Cursor launch config **Pressure Analysis** added.
- **Verification:** `pressure-env` `py_compile` passed. `--no-gui` on
  `run_20260831_181114` reported one 4342 ms redetected dip to -3.01 kPa and
  flagged the 1 ms recorded DIP as a glitch. `--no-gui` on
  `run_20260831_180324` reported six confirmed peaks and two seq gaps.
  Interactive GUI was not click-accepted in this turn.

## 2026-08-31 18:03:00 IST (UTC+05:30) — Pressure-monitor Start/Stop recording

- **Why:** Launch was writing CSV immediately, mixing idle and trial data.
- **Change:** `pressure_monitor.py` keeps live serial/plot at start. **Start
  Recording** creates `pressure_runs/run_<timestamp>/` and writes
  `samples.csv` / `events.csv`. **Stop Recording** flushes and closes the
  run. Window close stops an active recording. Serial `in_waiting` after
  port close is ignored.
- **Verification:**
  `/home/light-tarun/pressure-env/bin/python -m py_compile
  ros2_ws/src/Arduino/pressure_monitor.py` passed. Live serial/GUI click
  acceptance was not run in this turn.

## 2026-08-25 17:09:00 IST (UTC+05:30) — Context-bounded workflow modularization

- Replaced the 39,889-line implementation entrypoint with a 117-line public
  composition root and one `dentobot_workflow` package. Exact method-boundary
  mixins now separate bootstrap/lifecycle, view composition, planning/docking,
  guide/template, case/backend, robot scene/task, and logic domains. All
  routine implementation modules are capped at 1,500 lines; public methods,
  MRML/parameter state, algorithms, `.dentocase`, ROS/MoveIt, and preview-only
  contracts were preserved.
- Added an API manifest/ownership gate, CMake coverage, import-direction and
  process/network-boundary tests, a reproducible AST extraction utility, a
  compact agent routing document, and a package method-ownership map. The split
  is direct in-process inheritance and adds no transport, worker, serialization,
  bandwidth, or second state store.
- Developer reload now evicts both top-level `DENTO*.py` helpers and all
  internal package modules. `99` host tests, shell, composable-view, bounded
  Step 6 case-view, and five consecutive helper/internal reload cycles passed.
  A teardown-only destroyed-label callback was guarded and reran cleanly.
- Current limitation: the ROS-backed lifecycle smoke reaches connect, module
  reload, and reconnect, then native Slicer aborts at New Empty Case scene
  clear. A default-node singleton experiment did not fix it and was reverted.
  This remains a Track 1 lifecycle defect; no hardware or controller action was
  run and no warm active-ROS scene-replacement claim is made.

## 2026-08-25 14:41:00 IST (UTC+05:30) — Composable Views and guarded Step 6 workspace

- Replaced the routine 3×3 jaw-mask grid with compact Anatomy, Show-in, CBCT,
  and Overlays controls backed by a pure `ViewComposition` contract. Added
  metadata-first upper/lower/full anatomy scopes and a hierarchical Advanced
  object tree shared by Legacy and the application shell.
- Recommended views remain non-creating. An explicit CBCT 3D request may create
  Slicer intensity-rendering nodes lazily; DENTOBOT owns/removes only those
  view-session nodes and restores slice-composite plus pre-existing-renderer
  state.
- Step 6 now shows scene, robot, mouth-opening, and base-lock context; enforces
  case/phantom and MRML/ROS XOR in routine and Advanced views; and locks every
  non-owning workflow markup. This prevents accidental Step 6 editing of the
  patient-shell boundary while restoring its prior state in Step 5A.
- Verified with 92 host tests and the focused Slicer
  `DENTOBOT_COMPOSABLE_VIEWS_PASS` smoke, including explicit renderer cleanup,
  anatomy separation, lock/restore, and visual screenshot inspection. The
  shell and focused widget regressions printed
  `DENTOBOT_APPLICATION_SHELL_PASS`, `DENTOBOT_VIEW_WIDGET_PASS`, and
  `DENTOBOT_ROBOT_WIDGET_PASS`. Real case/theme/reload/operator acceptance
  remains pending. A teardown-only late destroyed-label callback remains logged
  for the module-lifecycle cleanup pass. No hardware operation, commit, push,
  or Drive sync occurred.

## 2026-08-25 13:45:00 IST (UTC+05:30) — Launcher auto-starts Docker daemon

- `launch-dentoworkflow.bash` now calls `ensure_docker_daemon` before Compose:
  starts `docker.socket`/`docker.service` when the API is unreachable, waits for
  `docker info`, and best-effort enables the units on boot (plain systemctl or
  passwordless `sudo -n`).
- On this host, start succeeds without a password; enable still needs an
  interactive `systemctl enable --now docker` once.
- Focused launcher tests: 6 passed. Stopped-daemon `--check-only` recovered
  Docker and printed `DENTOBOT launcher check passed`.

## 2026-08-25 13:34:00 IST (UTC+05:30) — Step 6.0A required case mouth opening

- Inserted required **6.0A Open Case Mouth about the TMJ** for imported case
  scenes before 6.1+ load/place/ROS/planning actions. Reuses the phantom
  four-landmark TMJ hinge solver without resampling source CBCT or masks.
- Persists landmarks, gap, hinge transform, gap line, and derived opened
  lower-jaw / mandibular trajectory/target display proxies. Freshness issues
  gate UI and `DENTORobotWorkflowFacade` connect/load/lock/sync. Phantom XOR
  scenes skip 6.0A.
- Collision and MoveIt planning-scene sync prefer opened lower-jaw polydata
  and mandibular trajectory proxies when current.
- Verification: Slicer `test_DENTOWorkflowStep6CaseJawOpening` →
  `DENTOBOT_CASE_JAW_OPENING_PASS`; focused façade/env tests and host
  `Testing/` suite passed in-session. Representative graphical acceptance
  after module reload remains open. Not clinical jaw kinematics.

## 2026-08-25 03:55:00 IST (UTC+05:30) — Connected case-save repair

- Reproduced Save Case Package rejection when the persistent robot base carried
  the live `Ros2MotionControlActive` flag. The archive audit correctly rejected
  the contaminated programmatic MRB snapshot.
- Package snapshots now explicitly mark SlicerROS2 nodes transient and suspend
  active flags around save, restoring the live scene location and active flag
  afterward even on failure. General scene-save observers remain in place.
- Extended the Slicer smoke to begin connected, verify the live flag resumes,
  reopen the package without ROS state, and compare geometry at `1e-6`.
  `DENTOBOT_CONNECTED_CASE_SAVE_PASS` was recorded for `test1_6_FD14.mrb`.
- Python AST parsing, static lifecycle coverage, `git diff --check`, and all 97
  host tests passed.
- The unrelated final historical-package check was unavailable because
  `dentobot-step6.dentocase` is currently absent. The live graphical session
  was not interrupted; source reload and operator save retry remain required.

## 2026-08-25 03:18:00 IST (UTC+05:30) — Step 5B microscopic-island repair

- Reproduced `test1_5b2.mrb` final fusion as occupied regions
  `[85852, 3, 1, 1]` after regenerating its saved stale prerequisites in a
  disposable Slicer process.
- Confirmed all four watertight 3.5 mm shell-contact branches existed with
  2.0 mm endpoint overlap and 0.003–0.310 mm shell gaps. The failure was the
  former one-voxel-only numerical-artifact filter, not missing dock branches.
- Replaced that narrow filter with a resolution-aware maximum 0.1 mm³
  per-artifact bound, applied only beside exactly one printable region. Raw and
  removed-region metrics are retained; larger disconnected parts still fail.
- The representative fusion produced one 85,852-voxel occupied volume, 89,524
  triangles, zero invalid edges, and four branch records. Focused and complete
  synthetic Slicer regressions passed; AST parsing and the 97-test host suite
  passed. Visual, fit, strength, manufacturing, and clinical acceptance remain
  open.

## 2026-08-25 00:52:52 IST (UTC+05:30) — Non-TTY workflow launch repair

- Made the final Ubuntu `docker exec` allocate `-it` only for a real
  interactive terminal. Cursor and automation can now keep an attached GUI
  launch without Docker rejecting non-terminal stdin.
- After Slicer closed with the pinned build's known VTK-leak exit code, the
  first repaired run exposed orphaned ROS/MoveIt children. The simulation
  launch now owns a separate process group and cleanup uses bounded INT, TERM,
  then KILL escalation across that group.
- Added a focused source regression and documented the active Docker-service
  prerequisite. The initial incident also required starting the inactive host
  Docker service; no dependency or container-image change was made.
- Bash syntax, five focused tests, the bounded process-group probe, and the
  97-test host suite passed. Full launcher preflight passed, then the repaired
  CRD launch started Slicer with DENTOWorkflow and a `ready:true` simulation
  stack containing one joint-state source. No hardware execution or robot
  motion ran.

## 2026-08-24 20:53:23 IST (UTC+05:30) — Native Step 6 placement-to-task stack

- **Workflow/UI:** rebuilt Legacy and New GUI Robot Simulation as the same
  seven-gate 6.0–6.6 sequence. Routine Connect stays in DENTOWorkflow; generic
  Motion Control is an explicit expert diagnostic with persistent Views and a
  one-click return. Execute remains hidden/disabled.
- **Persistent state:** added base status/source/revision, optional provisional
  curved forehead proxy, versioned six-joint Task Home, accepted workspace poses
  with joint vectors, reviewed assisted limits, immutable task snapshot, and
  independent Step 6 opacities. Material input changes invalidate task/phases;
  ROS robots/goals/plans/publishers/subscribers/guards remain transient.
- **Visualization:** added an explicit singleton CBCT renderer with current-WL,
  CT-Bone, and uCT-Skull intensity appearances; display-only opacity/visibility
  controls; combined robot+case framing; and a visualization-only proxy. Source
  scalar/IJK geometry and segmentation bounds are not changed.
- **Planning/runtime:** added direct façade operations for Task Home, workspace
  review, native Connect/Goal/IK/Plan, task confirmation, strict approach,
  terminal Entry contact, drilling preview, and phase status. Added
  `dentobot_drill_tip_provisional`, target/non-target collision objects, and a
  task-fingerprinted external phase guard that accepts only selected
  burr-target contact inside the approved corridor.
- **Verification:** 95 host tests passed. The focused Slicer persistence test,
  Step 6 operator-MRB restore, three-fixture case-package round trip, isolated
  ROS/MoveIt strict smoke, and phase-guard rejection/acceptance smoke printed
  their PASS markers. The supplied scenes preserve truthful stale Step 4C/5C
  lineage; the older `.dentocase` restores geometry at `1e-6` but remains
  robot-profile review-gated after the provisional-tip resource change.
- **Window/lifecycle evidence:** the main-window shell smoke exposed all seven
  substeps and shared Views; the native ROS report kept Connect/Goal/IK/Plan in
  DENTOWorkflow and returned from expert diagnostics; and reload, New Empty
  Case, reconnect, and saved-scene restore reached the lifecycle PASS marker.
  The arbitrary tangent visual-phantom pose remained colliding during its
  bounded diagnostic search, so representative base placement is still active.
- **Boundary:** no physical homing, calibrated TCP, registered base, controller,
  force/stop logic, hardware motion, drilling, or clinical validation was
  added. Normal visible-window representative-case acceptance remains active.
- **Final static gate:** whitespace, 66 Python AST files, two Qt UI files,
  eight canonical Markdown fence checks, dependency integrity, 13 inference
  tests, and five platform-contract tests passed.
- **Drive checkpoint:** replaced nine changed active-development Markdown files
  and six changed canonical Markdown files by their existing IDs. Readback
  retained both established parent folders and matched local byte sizes; no
  duplicate or non-document artifact was uploaded.

## 2026-08-24 19:18:32 IST (UTC+05:30) — Ordered Step 5B unified-template build panel

- **Why:** Step 5B displayed its generated output and action buttons before
  several shell and guide dimensions, which implied a finalized result and
  blurred the boundary between Steps 4B, 5B, and 5C.
- **Change:** rebuilt the visible Step 5B sequence as approved inputs/lineage →
  all nine dimensions → collapsed Advanced fit/intermediate processing →
  unified result → bottom Build/Inspect/Delete footer. Reused the existing
  parameter-bound widgets and complete-build backend; no geometry, MRML role,
  world-RAS/mm, invalidation, or Step 5C verification/export contract changed.
  Build/Update no longer becomes an inspection shortcut when the result is
  Current; inspection has dedicated display-only actions.
- **Implementation note:** Slicer's generated UI wrapper queries every original
  layout during parameter-node connection. Empty source layouts therefore stay
  alive after their widgets are reparented; destroying them caused and then
  resolved `removeWidget`/`property` errors during module construction.
- **Verification:** focused embedded-Slicer layout, navigation, and cache tests
  printed `DENTOBOT_UNIFIED_TEMPLATE_REGRESSION_PASS`; the host suite returned
  `101 passed`. The representative `test1_5b.mrb` loaded in isolated Slicer;
  visually inspected top/bottom screenshots confirmed dimensions precede the
  result and all actions are last. The saved case's missing Step 4C reference
  was explicitly reported and correctly disabled Build/Update.
- **Limits:** representative fresh-Current generation and normal-window
  operator acceptance remain pending. No robot motion, drilling, environment
  change, commit, push, or Drive synchronization was performed.

## 2026-08-24 18:09:33 IST (UTC+05:30) — Grouped Views and non-mutating volume-render inventory

- **Why:** the scene-wide Elements list was chaotic, unavailable from the New
  GUI header, and made CBCT volume rendering look like newly generated skin
  masks. Source tracing showed that refreshing the inventory itself called
  Slicer's default volume-render-node creation for every scalar volume.
- **Change:** added a shared New-GUI **Views** button; made Views open on
  Elements; added explicit per-stage recommendations; added upper/lower/all
  permanent-teeth shortcuts for 2D, 3D, or both; grouped anatomy by review
  category and FDI jaw; scoped routine choices to the authoritative teeth
  segmentation/input CBCT; collapsed unrelated scene data and the longer workflow inventory under
  Advanced; stopped creating volume renderers during inventory; labelled only
  existing renderers **not a mask** and removed them from recommended presets.
  Display changes remain transient and restore exact prior MRML display state.
- **Logic:** pure `DENTOViewPresets` maps FDI quadrants 1/2→upper and 3/4→lower,
  groups stable segment IDs without geometry inference, and defines one
  category set/description for each internal stage 0–10. The widget maps those
  results onto existing segmentation/display nodes; no mask voxels, polydata,
  workflow references, coordinate frames, or clinical algorithms change.
- **Verification:** Python compilation with a `/tmp` bytecode cache passed;
  the final task-local host suite returned 80 passed; focused embedded-Slicer tests
  printed `DENTOBOT_GROUPED_VIEWS_PASS`; the visible shell smoke printed
  `DENTOBOT_APPLICATION_SHELL_PASS`, opened the shared palette, and saved a
  visually inspected Elements screenshot. Xvfb/synthetic evidence is not a
  representative-anatomy, clinician, or clinical-validation claim.
- **Boundary:** no environment/setup contract changed. No robot motion,
  drilling, commit, push, or Google Drive synchronization was performed.

## 2026-08-24 18:06:10 IST (UTC+05:30) — Step 4B ownership lock and Step 5A consumer UI

- **Why:** workflow testing found the removed support checklist being made
  visible as an unmanaged child over the Step 4B arch, while Step 5A still
  exposed the custom support editor and implied a second place to change
  support membership.
- **Change:** made the hidden list a permanent state adapter; placed the arch
  in a full-width bounded Step 4B card; added a persistent support-selection
  lock to `TemplateSupportDraft`; added explicit revise→stale and
  rebuild→lock behavior; made Step 5A a read-only support-package summary with
  a return-to-Step-4B action; filtered the draft selector by DENTOBOT model
  role; propagated draft-selector changes through Step 4C and all Step 5
  descendants; and restored missing support JSON only from a matching Current
  locked model. No geometry or coordinate conversion changed.
- **Concurrent reconciliation:** preserved the simultaneously added grouped
  view-preset helper and new-shell Views action, then added the missing
  `DENTOViewPresets.py` CMake install entry and a packaging regression test so
  source-mounted and installed extensions use the same helper set.
- **Verification:** Python AST and whitespace checks passed. The complete host
  suite returned `100 passed` after preserving the concurrent grouped-view
  refactor. Real Slicer focused tests printed
  `DENTOBOT_STEP4B_5A_OWNERSHIP_TEST_PASS`,
  `DENTOBOT_STEP4B_LAYOUT_AND_LOCK_LOGIC_PASS`, and
  `DENTOBOT_STEP4B_5A_MRB_RESTORE_PASS`; the final combined rerun against the
  reconciled shared source printed
  `DENTOBOT_STEP4B_5A_RECONCILED_SUITE_PASS`. The MRB test saved, cleared, and
  reloaded the scene while retaining the locked Step 4B support IDs and the
  current Step 5A plane/boundary/preview provenance.
- **Limits:** Xvfb/synthetic evidence is not a representative anatomy,
  clinician, fit, collision, dimensional, or clinical-validation claim. A
  normal-window operator pass remains required. No robot motion, drilling,
  commit, Git publication, or Drive synchronization was performed.

## 2026-08-24 16:20:11 IST (UTC+05:30) — Controlled documentation and Drive checkpoint

- **Why:** the developer explicitly requested a current logbook, synchronization
  of the complete documentation state to Google Drive, and a local commit of
  the consolidated implementation worktree.
- **Daily Compass:** reconciled the existing workbook in place. All editable
  researcher-note fields remained placeholders; only the reconciliation date
  and current operating phase were updated. A ten-page render was inspected
  page by page with no visual defect, and DOCX archive integrity passed.
- **Drive:** replaced all eleven established active-development top-level
  documents by their existing IDs, replaced the two stale aggregate files in
  the separate controlled `docs` mirror, and uploaded exactly one copy of each
  missing dated logbook from 2026-08-18 through 2026-08-24. Folder readback
  confirmed one matching title per target and byte sizes equal to the local
  files. No duplicate established file, patient data, runtime artifact, scene,
  mesh, model, screenshot, or credential was uploaded.
- **Verification:** the close-day gate passed 55 Python AST files, two Qt UI
  files, eight Markdown fence checks, dependency integrity, 13 inference
  tests, and five platform-contract tests. The full current host suite returned
  `67 passed`; shell syntax, DOCX ZIP integrity, and whitespace checks passed.
- **Boundary:** the requested Git action is a local non-force commit only. No
  Git push, robot motion, drilling, or patient-facing operation is authorized
  or performed by this checkpoint.

## 2026-08-24 15:51:22 IST (UTC+05:30) — Transactional DENTOBOT case package V1

- **Why:** MRML/MRB case files could contain SlicerROS2 nodes and stale active
  state, causing duplicate subscribers, null URDF roots, failed reconnects,
  ambiguous fallback robots, and process loss after scene replacement or
  scripted-module reload.
- **Change:** added Step 0 **Save Case Package** / **Open Case Package** and a
  `.dentocase` ZIP64 schema containing a sanitized authoritative MRB,
  canonical manifest, SHA-256 inventory, workflow-lineage snapshot, portable
  robot-resource fingerprint, and save report. Save validates before atomic
  replacement. Open preflights before mutation, saves recovery state, clears
  and loads the embedded scene, validates restored world-RAS/mm records, and
  restores the prior scene on a post-load mismatch. ROS runtime objects and
  active connection state are excluded; connection remains explicit in Step
  6. A robot fingerprint mismatch visibly blocks Step 6 import.
- **Files:** `DENTOWorkflow.py`, `DENTOCaseBundle.py`, the module UI/CMake
  install list, two Slicer smoke scripts, pure-Python tests, and the controlled
  context/architecture/decision/plan/task/traceability/logbook documents.
- **Verification:** the full host suite returned `67 passed`; XML, Python
  compilation, and whitespace checks passed. Real Slicer round trips of
  `test1_5C_FD14.mrb` and `test1_6_FD14.mrb` printed
  `DENTOBOT_CASE_BUNDLE_PASS`. A deliberate post-load manifest mismatch
  restored the prior sentinel scene and printed
  `DENTOBOT_CASE_BUNDLE_TRANSACTION_PASS`. Successful open also clears the
  deleted temporary MRB as Slicer's save target; rollback restores the prior
  scene location.
- **Preserved truth:** both supplied samples remain blocked as stale because
  their Step 4B support draft changed after the Step 4C/5C outputs. Package
  integrity does not override workflow freshness.
- **Limits:** the known pinned SlicerROS2 VTK debug leak still returns 1 after
  explicit PASS markers at scripted shutdown. Normal graphical acceptance, a
  regenerated current Step 5C package, and offline legacy contaminated-scene
  migration remain pending. No hardware motion, Git publication, or Drive
  synchronization was performed.

## 2026-08-21 19:22:00 IST (UTC+05:30) — Step 0 scene-replacement crash repair

- **Why:** Slicer exited after Step 0 **New Empty Case** and **Load Saved
  Scene** while SlicerROS2 and DENTOWorkflow were loaded.
- **Root causes:** the workflow retained adapter-owned ROS MRML objects through
  scene deletion; the default SlicerROS2 node became detached after
  `vtkMRMLScene.Clear`; ROS subscribers were being serialized into case MRBs;
  the pinned SlicerROS2 removal code left stale reference IDs; and Slicer 5.10's
  transform display node does not implement every Markups handle method.
- **Change:** added ordered scene-close teardown and post-close ROS default-node
  reattachment; made status/joint subscribers, the joint publisher, and MoveIt
  proxy nodes non-persistent; removed exact stale adapter references after
  upstream deletion; and guarded transform display API calls.
- **Verification:** Python compilation and whitespace checks passed; the
  focused host suite returned `54 passed`; the real windowed-Xvfb SlicerROS2
  lifecycle probe cleared an empty case, reloaded a saved MRB with a locked
  Step 6 base, restored its sentinel/parameter state, and printed
  `DENTOBOT_SCENE_LIFECYCLE_PASS` without the prior exceptions/warnings.
- **Limit:** the known upstream SlicerROS2 VTK debug-leak report still causes
  exit code 1 after the explicit PASS marker during scripted app shutdown.
  Normal graphical operator confirmation remains advisable; no robot motion,
  Git publish, or Drive sync was performed.

## 2026-08-21 15:17:00 IST (UTC+05:30) — Step 6 documentation reconciliation

- **Why:** Operator requested detailed logbook/changelog/plan updates with
  timestamps, failures, fixes, algorithm status, fix-vs-replace guidance, and
  next vs backlog aligned to `DEVELOPMENT_PLAN.md`.
- **Change:** Expanded `docs/logbook/2026-08-21.md` with Step 6 slice
  checklist, 6.3 algorithm notes, Connect fix matrix, evidence labels, and
  priority ordering. Updated `DEVELOPMENT_PLAN.md` Step 6 status (bridge +
  planning sub-workflow now implemented). Updated `TASKS.md` with slice
  checklist and refreshed last-updated date.
- **Verification:** documentation-only; no pytest or container rerun.
- **Not claimed:** interactive Connect after extension reload; Git push; Google
  Drive sync; any change to planning/collision algorithms.

## 2026-08-21 14:45:00 IST (UTC+05:30) — Logbook reconciliation through 2026-08-21

- **Why:** Operator requested dated logbooks with latest changes, problems faced,
  and pending tasks mapped to `DEVELOPMENT_PLAN.md`.
- **Change:** Updated `docs/logbook/2026-08-18.md` and `2026-08-19.md` (session
  summaries, problem table); added `2026-08-20.md` (no dev recorded) and
  `2026-08-21.md` (checkpoint + work-package pending matrix). Mirrored to
  `ros2_ws/src/DentoBot/Workspace/docs/logbook/`.
- **Verification:** documentation-only; no code or pytest rerun.
- **Not claimed:** interactive Step 6 Connect; Git push; Google Drive sync.

## 2026-08-19 19:55:00 IST (UTC+05:30) — Connect forces a fresh ros2 node list

- **Why:** Retry after the 8 s timeout showed “RSP is running without the
  Slicer joint publisher” while both nodes were already up. Connect used a
  1.5 s node-list cache from the failed half-stack, and the live Slicer
  process still had the pre-PATH-fix module in memory.
- **Change:** Connect and stack start/stop invalidate that cache and pass
  `force=True`. Incomplete-stack copy tells the operator to reload.
- **Verification:** host `test_ros2_bridge.py` + CLI env tests 12 passed /
  4 skipped; container 16 passed; live nodes still RSP + slicer publisher +
  `/slicer`.
- **Not claimed:** interactive CreateAndAddRobotNode after reload.

## 2026-08-19 19:50:00 IST (UTC+05:30) — Connect description launch resets PATH

- **Why:** Connect reported the Slicer joint-state stack did not appear in
  8 s. Live leftover: RSP up, `slicer_joint_state_publisher` missing.
- **Change:** ROS children export a Jazzy/system PATH (not SuperBuild
  `python-install/bin`). Incomplete slicer-mode launches are stopped; launch
  logs are kept.
- **Verification:** container 14 passed including yaml/rclpy under Slicer
  PATH; after stopping pid 2066, a clean launch showed both description
  nodes plus `/slicer` in 1 s.
- **Not claimed:** hardware motion or interactive CreateAndAddRobotNode.

## 2026-08-19 19:45:00 IST (UTC+05:30) — Step 6.0 case view and 6.2 merged limits

- **Why:** After Connect, import still framed the phantom origin, and 6.2
  duplicated min/max plus a nested joint-value group. Plan/Preview could
  keep driving joints after `/slicer` died.
- **Change:** Import sets the CBCT slice background and frames case RAS
  bounds. 6.2 is one min/value/max row per joint; min/max changes update
  the value range. Plan/Preview call `ensure_slicer_ros2_runtime` when ROS
  is active.
- **Verification:** host `test_step6_planning.py` + `test_ros2_bridge.py` +
  `test_robot_placement.py` → 28 passed, 1 skipped. Container the same plus
  `test_ros2_cli_slicer_env.py` → 32 passed; live `SlicerApp-real` listed
  `/slicer`. Slicer widget tests added, not run until extension reload.
- **Not claimed:** hardware motion, MoveIt, or interactive GUI Connect.

## 2026-08-19 19:35:00 IST (UTC+05:30) — ros2 CLI from Slicer unsets PYTHONHOME

- **Why:** After the ROS2-module import fix, Connect showed “ros2 CLI is not
  available in this Slicer process.” Live Slicer PATH included
  `/opt/ros/jazzy/bin`; `PYTHONHOME` made the CLI load Slicer stdlib.
- **Change:** `run_ros2_cli` sources Jazzy/workspace after unsetting
  `PYTHONHOME`/`PYTHONPATH`/`PYTHONEXECUTABLE`. Description launch uses the
  same sanitized `bash -c`.
- **Verification:** host `test_ros2_bridge.py` 8 passed / 3 skipped; container
  `test_ros2_cli_slicer_env.py` + bridge tests 11 passed; live Slicer
  `PYTHONHOME` probe listed `/slicer`. Interactive Connect after extension
  reload is still required in the GUI.
- **Not claimed:** hardware motion or MoveIt.

## 2026-08-19 19:20:00 IST (UTC+05:30) — Start Stack & Connect discovers SlicerROS2

- **Why:** Step 6 Connect showed “The ROS2 Slicer module is not available.
  Use the dentobot SlicerROS2 container.” The live container Slicer already
  had SlicerROS2 directories on `--additional-module-paths`.
- **Change:** `get_ros2_logic()` now imports `slicer` at the call site instead
  of swallowing a `NameError`. `ensure_ros2_slicer_modules` can still register
  installed SlicerROS2 paths. `launch-dentoworkflow.bash` merges DENTO Workflow
  into `SLICER_ROS2_MODULE_PATHS`. If ROS2 is still missing, Connect offers
  the MRML robot fallback.
- **Verification:** host pytest `Testing/test_ros2_bridge.py` 6 passed;
  container helper resolved `libqSlicerROS2Module.so` and
  `ROS2MotionControl.py`. Interactive Connect after extension reload is still
  required.
- **Not claimed:** hardware motion, MoveIt, or Connect success in host/Windows
  Slicer.

## 2026-08-19 18:45:00 IST (UTC+05:30) — Step 6 panel order, gating, and Elements

- **Why:** Step 6 was a single dump: lock sat above placement, phantom and ROS
  competed with the case, and Elements had no Stage 6 list so the viewport
  force-showed every robot/phantom mesh.
- **Change:** Reordered 6.0–6.3; case vs phantom XOR; 6.1 disabled until a
  scene exists; place/lock until a robot is present; 6.3 until case+lock.
  Stage 9 Elements recommended presets. Stopped force-showing all Step 6
  display nodes.
- **Verification:** host pytest 22 passed. Slicer widget test updated for
  phantom-then-robot order; not re-run in this session.
- **Not claimed:** interactive Slicer verification; planner/collision rewrite.

## 2026-08-18 19:30:00 IST (UTC+05:30) — Step 6 planning sub-workflow (6.0–6.3)

- **Why:** Step 6 needed a structured path from upstream planning artifacts to
  simulated motion along the approved trajectory, with mount lock, user task
  joint limits, and draft collision screening.
- **Change:** `DENTOStep6Planning.py`; Step 6 UI sections 6.0–6.3 in
  `DENTOWorkflow.ui`; import/lock/limits/plan/preview handlers in
  `DENTOWorkflow.py`. Environment obstacles include subsampled teeth
  segmentation closed surfaces plus template, dock, and support geometry.
- **Verification:** host pytest: 22 passed (`test_step6_planning`,
  `test_robot_placement`, `test_ros2_bridge`, `test_description`).
- **Not claimed:** interactive Slicer GUI verification; MoveIt; hardware
  motion; swept-volume or clinical collision validation.

## 2026-08-18 18:10:00 IST (UTC+05:30) — Motion Control sliders drive simulated /joint_states

- **Why:** The Step 6 SlicerROS2 connect path loaded the URDF, but Motion Control
  sliders only updated a goal overlay while a competing neutral publisher held
  `/joint_states` at zero.
- **Change:** `joint_state_mode:=slicer` starts
  `dentobot_slicer_joint_state_publisher`; DENTOROS2Bridge streams slider
  values on `dentobot/slicer_joint_positions`. Connect refuses a live
  neutral/manual publisher. SETUP duplicate Motion Control sections merged.
- **Verification:** host `dentobot` conda pytest: 15 passed
  (`test_ros2_bridge`, `test_robot_placement`, `test_description`). Container
  `colcon build --packages-select dentobot_description` succeeded. Isolated
  `joint_state_mode:=slicer` launch showed both nodes; `/joint_states` started
  at zeros; publishing `[0.0, 0.04, 0, 0, 0, 0]` on
  `dentobot/slicer_joint_positions` set J2 to 0.04 m. Launcher `--check-only`
  passed. Interactive Slicer connect not re-run.
- **Not claimed:** interactive Slicer GUI connect; MoveIt; hardware command.

## 2026-08-18 17:45:00 IST (UTC+05:30) — Step 6 SlicerROS2 motion-control bridge

- **Why:** DENTOBOT needed an A–Z path from `dentobot_description` to
  SlicerROS2 Motion Control inside Step 6 without relying on manual ROS2 module
  field entry.
- **Change:** `DENTOROS2Bridge.py`; Step 6 UI (**Start Stack & Connect Motion
  Control**, **Disconnect ROS 2 Robot**); `launch-dentobot-description-for-slicer.bash`;
  SETUP subsection for the workflow. ROS robot parents under Step 6 base
  transform; MRML link meshes hide while ROS 2 is active; MoveIt remains off.
- **Verification:** `pytest` 7 passed (`test_ros2_bridge`, `test_robot_placement`);
  launcher `--check-only` passed; container `ros2 node list` showed
  `/dentobot_robot_state_publisher` after launch.
- **Not claimed:** interactive Slicer connect in this session; MoveIt IK/plan/execute.

## 2026-08-18 15:55:00 IST (UTC+05:30) — Host Record3D OBJ point-cloud viewer

- **Why:** `data/3dscan_iphone.zip` is a Record3D iPhone LiDAR sequence of
  coloured OBJ vertices in camera metres; it needed a host viewer and quality
  check before any Slicer/RAS use.
- **Change:** added `scripts/view_record3d_scan.py` (zip/folder/OBJ, vispy
  arcball, frame play/scrub, RGB or height colour, catalog warnings). Installed
  `vispy 0.16.2`, `PyOpenGL 3.1.10`, and `freetype-py 2.5.1` into
  `/home/light-tarun/pressure-env`. Cursor launch config **Record3D Scan
  Viewer** points at the example zip. Scan data stay local and unpacked-in-place.
- **Verification:** `--self-test` passed; `--report-only --scan-all` on the
  example zip reported 195 OBJ frames, missing indices 163 and 174–179, point
  counts 2,940–358,865, no empty frames, in 20.4 s. A vispy/Qt window loaded
  frame 0 (73,018 points) on `DISPLAY=:0` and exited cleanly.
- **Not claimed:** Slicer RAS conversion, registration, anatomical validity,
  or interactive FPS acceptance.

## 2026-08-17 21:02:00 IST (UTC+05:30) — Pressure-monitor CSV root next to the script

- **Why:** Keep acquisition CSVs with the Arduino tool instead of under the
  home directory.
- **Change:** `pressure_monitor.py` now writes
  `ros2_ws/src/Arduino/pressure_runs/run_<timestamp>/` via `Path(__file__)`.
  The empty `pressure_runs/` directory was created. Earlier home-directory
  runs in `~/pressure_runs/` were not moved.
- **Verification:** resolved path equals
  `/home/light-tarun/dentobot/ros2_ws/src/Arduino/pressure_runs` and the
  directory exists. The GUI was not relaunched for this path change.

## 2026-08-17 20:58:00 IST (UTC+05:30) — Cursor Python runner and host pressure-monitor launch

- **Why:** The Arduino pressure GUI needed a Cursor Run/F5 path that uses the
  existing host venv instead of Slicer or inference Python.
- **IDE:** Installed `ms-python.python` 2025.6.1 and `ms-python.debugpy`
  2026.6.0. Workspace `.vscode` settings select
  `/home/light-tarun/pressure-env/bin/python` and add a **Pressure Monitor**
  launch configuration. User settings enable terminal venv activation.
- **Runtime:**
  `/home/light-tarun/pressure-env/bin/python ros2_ws/src/Arduino/pressure_monitor.py`
  opened Arduino UNO WiFi R4 on `/dev/ttyACM0`, calibrated, and wrote
  `~/pressure_runs/`. Sensing-only; no robot motion.
- **Docs:** `SETUP.md`, `DECISIONS.md`, `TASKS.md`, `ARCHITECTURE.md`, and
  today's logbook.

## 2026-08-17 19:10:00 IST (UTC+05:30) — Step 6 landmark UX, workspace layout, and hinge-parent fix

- **Landmark placement UX:** Split create/reset into progressive **Place …
  landmark** clicks and a separate **Clear Landmarks** button. Each click uses
  one-at-a-time Markups placement (`StartPlaceMode(0)`) so the operator can pan
  between landmarks. After the fourth landmark is placed, jaw opening runs
  automatically. Files: `DENTOWorkflow.py`, `DENTOWorkflow.ui`.
- **Singleton and co-location:** Step 6 now rejects duplicate draft phantom or
  robot placement sets. A `[Step 6] Draft Phantom Workspace` linear transform
  relocates BodyParts3D meshes from their native ~Z 1500 mm coordinates to the
  research workspace center `(0, -150, 250)` mm RAS on first load. **Frame
  Phantom + Robot** frames combined bounds; the robot base auto-positions near
  the phantom when still at the world origin.
- **Hinge under workspace parent:** The Rodrigues hinge solver still returns a
  world-RAS matrix, but the jaw transform now stores
  `world_transform_to_parent_local()` relative to the workspace parent. This
  prevents the mandible separating from the skull after workspace relocation.
- **Verification:** `pytest -q Testing/test_robot_placement.py` passed five
  tests in the `dentobot` conda environment. Slicer logic/widget tests were
  updated for workspace-aligned landmark coordinates, seven-node phantom
  cleanup (includes workspace transform), and a 150 mm mandible/maxilla center
  bound after opening. Interactive Slicer extension reload was not re-run in this
  session.
- **Not changed:** ROS bridge, controller, hardware motion, clinical jaw
  mechanics, registration, calibrated TCP, or collision guarantees.

## 2026-08-17 16:06:00 IST (UTC+05:30) — Draft open-mouth Step 6 workspace

- Added the disposable BodyParts3D skull/maxilla/mandible loader, ordered
  four-point TMJ/incisor contract, Rodrigues pure-hinge transform, deterministic
  -60° to +60°/0.05° gap search, achieved-gap line, reset/delete controls, and
  active-Step-6 visibility restoration. The 40 mm value is the final incisor
  gap, not a literal mandible translation.
- Reused the URDF-driven seven-link hierarchy, photographed q=0, reversed J4,
  orthonormal plane snap, local base nudges, gated keyboard controls, and manual
  six-joint UI for provisional forehead placement and intraoral reach review.
- Four host tests, focused Slicer logic/widget tests, MRB save/reopen, inspected
  Xvfb viewport/control captures, and the close-day static gate passed. The
  graphical marker reported `40.001 mm`, seven robot models, and three phantom
  models. No ROS state, controller, hardware, patient data, clinical jaw model,
  exact collision, registration, IK, or calibrated TCP was involved.
- Local commits `28d940f` and `901ee17` were created. Google Drive replaced 11
  established active/controlled files in place and created exactly one new
  `2026-08-17.md` dated log (`1t9OpsCvyiTBCELkSZ-0X9XulF7iieB8i`). The first
  Git push was blocked by the environment's egress reviewer pending explicit
  approval for `https://github.com/ghostarun/DentoBot.git`; no workaround was
  attempted.
- A final container audit found four exact headless Slicer test process trees
  retained by the two viewport captures and two invalid harness invocations.
  Their four `SlicerApp-real` PIDs received SIGTERM; the follow-up process query
  returned no Slicer, Xvfb, or open-mouth QA process. No interactive/user
  Slicer process was targeted.

Publication update at 16:18 IST: after the developer explicitly approved the
named private-source destination, the non-force push advanced
`codex/ubuntu-migration` from `f49f4d9` to `f25bf6f`. `git ls-remote` returned
the exact local SHA `f25bf6f69ad7138d2233343bf0fc40db8cab6380`.

## 2026-08-14 20:38:57 IST (UTC+05:30) — Robot placement promoted to DENTOWorkflow Step 6

- Renamed the tenth workflow entry from the provisional Robot Lab label to
  **6 · Robot Placement** at the developer's request. Updated the section
  title, keyboard-safety wording, deletion messages, and all role-owned model/
  transform/plane display names from `[Robot Lab]` to `[Step 6]`.
- Preserved MRML role attributes, parameter names, URDF/STL geometry, joint
  behavior, placement controls, and simulation-only safety boundary. Existing
  scenes remain discoverable by stable role attributes and are renamed when
  Load/Refresh or plane reset runs.
- Reconciled the controlled context, architecture, setup, decisions, plan,
  tasks, traceability, and dated logbook so registration/calibration remains an
  explicit prerequisite but is no longer mislabeled as the visible workflow
  Step 6. No ROS bridge, controller, hardware command, Git publication, or
  Drive sync occurred.
- Seven host tests and the combined focused Slicer Step 6 logic, widget,
  ten-entry navigator, and MRB persistence checks passed with exit 0.

## 2026-08-14 20:24:43 IST (UTC+05:30) — Simulation-only Slicer Robot Lab placement

- Added a tenth, non-clinical **Robot Lab · Base and Joints** entry to
  DENTOWorkflow. It parses the tracked URDF, loads the seven existing STL assets
  explicitly as raw RAS/CAD geometry, and builds seven link-pose transforms
  beneath one persistent editable robot-base transform. Extension CMake derives
  an installed RobotDescription resource tree from the one tracked source copy;
  a packaged-path Slicer smoke test loaded all seven meshes.
- Added all-six-joint manual controls, a draggable Markups mount plane,
  scale/shear-free snap-to-plane, native base/plane transform handles, local
  X/Y/Z and Rx/Ry/Rz button nudges, configurable step sizes, framing/reset/
  delete actions, and opt-in keyboard nudges gated to Robot Lab and suppressed
  while text/numeric editors have focus.
- Added pure URDF/FK/plane/nudge helpers and two host tests. Focused Slicer 5.10
  logic and widget tests loaded all seven meshes, verified raw STL bounds and
  transform parenting, J4 direction, plane snap, local nudge, shortcut gating,
  synthetic MRB save/reopen, and complete owned-node deletion. The ten-entry
  navigator test also passed. An initial Slicer run exposed and corrected the
  API's required output matrix argument for `GetObjectToWorldMatrix`.
- Updated controlled context, setup, architecture, development plan, decisions,
  tasks, traceability, changelog, and dated logbook. This remains synthetic
  MRML-only evidence: no ROS bridge, IK, controller, hardware command, head/
  mouth collision, calibrated mount/TCP, Git publication, or Drive sync was
  introduced.

## 2026-08-14 19:18:17 IST (UTC+05:30) — Selected draft zero, planar base, and reversed J4

- Rebased the integrated URDF so the photographed
  `[25.38 deg, 0 mm, 62.46 deg, 0 mm, 1.08 deg, -35.28 deg]` state is q=0.
  Shifted finite rotary limits without changing their spans; the source URDF
  and every mesh remain unchanged.
- Rotated the integration root -90 degrees about X so link-1's mounting face is
  parallel to RViz XY with the robot above the grid. Negated J4's axis while
  retaining its positive 0–75 mm range; positive J4 now moves primarily in
  negative base X.
- Seven direct tests and eight Jazzy-reported tests passed. An isolated-domain
  six-joint TF probe passed, six zero states and the expected burr coordinates
  were observed, and the RViz pose/AABBs were visually inspected before clean
  shutdown.
- The developer's existing manual/RViz process was left running and must be
  restarted to load the new URDF. These remain draft coordinates, not physical
  home/calibration, head-mount, IK, Slicer, controller, or hardware evidence.
  No Git publication or Drive sync occurred.

## 2026-08-14 18:46:30 IST (UTC+05:30) — Draft 5 mm AABB workspace feedback

- Extended manual articulation with collision-STL-derived base-frame AABBs,
  a default 5 mm warning for non-adjacent link boxes, green/red RViz
  `MarkerArray` outlines, and live CAD burr-origin coordinates. Joint updates
  remain unrestricted and simulation-only.
- Added pure forward-kinematics/AABB coverage, geometry/visualization message
  dependencies, RViz display wiring, configurable launch plumbing, and the
  explicit conservative evidence boundary.
- Six direct tests passed; Jazzy reported seven tests with no failure. RViz
  subscribed to the single marker publisher, the warning UI and boxes were
  visually inspected, and shutdown left no residual process. Neutral reports
  two coarse overlaps.
- A first runtime launch incorrectly rejected valid colcon symlink-installed
  meshes; URI-component validation replaced the resolved-prefix check. No
  exact/swept/head/patient collision, Slicer, IK, controller, hardware, motion,
  Git publication, or Drive sync occurred.

## 2026-08-14 18:19:23 IST (UTC+05:30) — Manual robot-joint articulation gate

- Added a package-owned PyQt manual joint-state publisher, a dedicated launch,
  and neutral/manual/external source selection. Added the Ubuntu host launcher
  for RViz plus the six-joint control window; displayed values use degrees or
  millimetres while ROS messages retain radians/metres.
- Extended package tests for manual-control order, types, limits, units,
  launch/dependency wiring, and added a runtime TF probe for independent joint
  motion. Updated controlled robot-integration documentation and logs.
- Jazzy build/test passed with six reported tests. All six runtime joint probes
  passed; neutral and articulated RViz runs loaded every mesh without resource
  errors and shut down without residual processes.
- Evidence remains synthetic. Physical direction/scale/zero/limit acceptance,
  collision, IK/end-effector control, Slicer bridging, controllers, hardware,
  and motion remain pending. No Git publication or Drive sync occurred.

## 2026-08-14 17:07:00 IST (UTC+05:30) — Approved documentation and publication checkpoint

- Reconciled the complete Daily Compass against the current controlled
  Markdown. Its editable fields still contained placeholders only, so no
  clinical threshold, engineering decision, or acceptance claim was promoted.
- Updated only the workbook's reconciliation date and current phase: bounded
  Template V0 proof remains the primary work order, while the simulation-only
  robot description may be inspected and calibrated without motion.
- Rendered the updated workbook to ten pages and visually inspected every
  page. No clipping, overlap, broken table, missing glyph, or unreadable field
  was observed.
- The developer explicitly authorized this batched Git commit/push and Google
  Drive synchronization. Publication preserves the established two-mirror
  Drive structure and does not authorize robot motion, drilling, patient-facing
  activity, or upload of runtime/research data.

## 2026-08-14 16:50:57 IST (UTC+05:30) — Simulation-only ROS 2 robot description integration

- Added the tracked `dentobot_description` `ament_cmake` package with the
  supplied seven-link/six-movable-joint CAD tree, seven checksum-locked binary
  STL meshes, package-resolvable URDF, optional RViz preset, and a neutral
  joint-state publisher with no command or hardware interface.
- Preserved the supplied movable geometry, limits, inertials, scales, and mesh
  bytes. Renamed the generic robot, converted mesh paths to `package://`, and
  added only a massless `base_link` identity parent above `link-1` to remove
  KDL's unsupported-root-inertia warning.
- Added static integrity tests for tree connectivity, joint contracts, finite
  unit axes, positive-definite inertias, mesh references/scales, binary STL
  structure/bounds, and source checksums. Added a provenance/evidence boundary
  README and the workspace bootstrap source-space link needed because colcon
  identifies the repository root as the generic CMake Slicer extension.
- Updated Project Context, Setup, Architecture, Development Plan, Decisions,
  Tasks, root README, bootstrap behavior, repository logs, and the dated Ubuntu
  logbook. Existing DENTOWorkflow changes were not modified.

### Verification

- Source `check_urdf`, package XML, Python compilation, bootstrap syntax and
  idempotence, whitespace checks, and three direct pytest cases passed.
- ROS 2 Jazzy container `colcon build` and `colcon test` passed; the result
  summary reported no errors, failures, or skipped tests.
- The final headless launch exposed exactly one neutral-state node and one
  robot-state node, published all six zero joint positions, and resolved the
  `base_link -> burr` transform. SIGINT stopped both child publishers cleanly;
  final process and ROS-node checks were empty.
- The first runtime iteration revealed KDL root inertia, non-forwarded client
  shutdown, duplicate nodes, and a repeated-SIGINT teardown exception. The
  integration root, exact-process cleanup, and idempotent teardown corrected
  those issues. A direct `/tf_static` echo did not return before its timeout,
  but the single transient-local publisher was present and `tf2_echo` resolved
  the complete base-to-bur chain.
- RViz was not launched. Physical joint/frame calibration, mesh alignment and
  scale acceptance, collision simplification, TCP/docking frames, controllers,
  motion, hardware, drilling, clinical use, Git publication, and Drive sync
  remain outside this evidence.

## 2026-08-13 19:35:24 IST (UTC+05:30) — Step 4B collision-aware yaw and explicit dock confirmation

- Advanced the four-independent-dock assembly to schema v3. Added a persisted
  yaw parameter and deterministic 5-degree sweep against cached sampled closed
  surfaces of every other whole tooth on the target FDI arch. Opposing-jaw
  anatomy is excluded and omitted obstacle surfaces remain visible metadata.
- Added manual yaw correction/rebuild, Draft versus Confirmed state, automatic
  confirmation invalidation, and a Step 5B fusion gate requiring the current
  orientation to be explicitly confirmed.
- Added 13 referenced, read-only 2D/3D Markups annotations for the assumed
  crown centroid/normal and each dock's radius, outer/bore diameter, and depth.
  The annotations participate in viewport filtering, MRB persistence, and
  reference-driven Step 4B deletion.
- Added final verification checks: unconfirmed orientation or detected sampled
  tooth/dock collision is FAIL; an omitted same-jaw obstacle surface is WARNING.
  The vertex-sampling screen is documented as draft assistance, not clinical
  or continuous-surface collision proof.

### Verification

- Python compilation, UI XML parsing, and scoped whitespace checks passed.
- Slicer 5.10 passed the focused yaw math test, complete module-load check,
  schema-v3 support/shell/fusion/export integration with MRB save/reload and
  deletion, plus navigation/display/viewport/support-arch UI regressions.
- No Git commit/push or Google Drive synchronization occurred.

## 2026-08-13 18:45:03 IST (UTC+05:30) — PoC evidence pivot, Daily Compass, and Case-stage initialization

- Reconciled the August 2026 Research-to-Clinical Gap and Engineering Rigidity
  checklist against the current implementation. Updated Project Context,
  Architecture, Development Plan, Decisions, Tasks, Reproducibility, and the
  dated logbook to make the immediate work order explicit: freeze the narrow
  clinical/Template V0 contract, run representative acceptance, print and
  measure one template, formalize registration/TRE, keep robot/tool/sensing
  lanes active, and maintain a total-system error budget.
- Added a shared evidence vocabulary—Static, Synthetic, Developer-live,
  Representative anatomy, Printed phantom, and Clinician/expert—and explicitly
  separated software/topology results from clinical fit, manufacturing,
  mechanics, registration, and robot claims.
- Created `Workspace/docs/DENTOBOT_Daily_Compass.docx`, a locally editable
  OneNote-like workbook for daily focus, mental-model capture, unanswered
  clinical questions, lane status, Template V0 testing, registration/error
  budgeting, meeting notes, and later Codex reconciliation. The source
  checklist remains unchanged. The generated DOCX uses Letter pages, fixed
  editable tables, and shaded entry cells; its 11-page PDF render was inspected
  page by page.
- Corrected fresh DENTOWorkflow initialization so an empty scene opens the
  workflow navigator on **Case**, not **1 · CBCT Imaging**. Once the operator
  enters a de-identified case label, Imaging becomes the next recommendation
  without an automatic stage jump. Added the condition and focused widget
  regression to `DENTOWorkflow.py`.

### Verification

- `PYTHONPYCACHEPREFIX=/tmp/dentobot-pycache python3 -m py_compile`, UI XML
  parsing, and `git diff --check` passed.
- The focused Slicer 5.10
  `test_DENTOWorkflowWorkflowNavigationWidget` exited 0 in the existing
  container and now asserts fresh Case-stage initialization.
- The Daily Compass DOCX ZIP structure passed `unzip -t`; LibreOffice rendered
  it to an 11-page Letter PDF and all pages were visually inspected for
  clipping, overflow, tables, color, hierarchy, and editable space.
- No Git commit/push or Google Drive synchronization occurred in this batch.

## 2026-08-10 15:59:55 IST (UTC+05:30) — Step 5C zoom and ROI-height cut constraint

- Stopped the ROI-aligned camera lock from restoring its initial parallel
  scale after every camera event. The explicit isolate action still performs
  the initial ROI top-to-bottom fit; zoom then remains available with either
  yaw state, and plane/curve actions preserve the current zoom.
- Reduced the simple cut plane to one Point-Normal origin control. The origin
  is projected onto the current Step 5B ROI Z axis and the normal is fixed to
  ROI `+Z`; transform handles are hidden and validation rejects a tilted,
  laterally displaced, or wrong-ROI plane.
- Added ROI-reference persistence and reapplication after scene refresh and
  immediately before cutting, plus a focused Slicer-native constraint test.
  Python compilation, UI XML, whitespace, and repository static checks passed.
  Live zoom/placement/save-reopen acceptance remains pending because Slicer
  was not launched. No Git commit/push or Drive sync occurred.

## 2026-08-10 15:38:25 IST (UTC+05:30) — Continuous MPR trajectory correction

- Fixed the live-review defect where moving Entry or Target rebuilt the same
  slider angle against a different world-reference frame and could jump to a
  substantially different circumferential anatomy view.
- Added Markups point start/end interaction handling. The MPR matrix now stays
  fixed under the pointer throughout a drag, then updates once at release.
- Added continuity-preserving frame transport: project the old plane normal
  perpendicular to the corrected trajectory, reconstruct the closest valid
  longitudinal frame, and apply only the slider-angle delta. In-plane edits
  retain the exact plane; a previous-X fallback handles the singular case.
  Reset still deliberately rebuilds deterministic world-reference 0°.
- Extended Slicer-native math coverage for in-plane preservation, off-plane
  transport, singular fallback, slider delta, orthonormality, handedness, and
  endpoint containment. Python compilation, Qt UI XML, and whitespace checks
  passed. Live correction UX and the Slicer-native suite remain pending; no
  Slicer launch, inference, Git commit/push, or Drive sync occurred.

## 2026-08-10 14:50:42 IST (UTC+05:30) — Trajectory-aligned longitudinal oblique MPR

- Added a compact Step 4A Trajectory Verification group with enable, an
  interactive `-180°..+180°` rotation slider, live angle/status text, and a
  deterministic zero-orientation reset.
- Reused the selected world-RAS Entry/Target Markups line and the source CBCT
  referenced by its authoritative segmentation. Added singularity-safe,
  right-handed frame and `SliceToRAS` construction that places trajectory in
  slice Y, the rotated transverse direction in slice X, their cross-product in
  the normal, and the trajectory midpoint at the origin.
- Changed no volume or trajectory geometry. Rotation is an event-loop-coalesced
  native slice-matrix update; no resampled volume, segmentation, mesh work, or
  external process is created. The existing line is temporarily projected as
  the 2D overlay.
- Captured and restored the chosen slice matrix/FOV, composite layers/linking,
  and trajectory display state on disable, save, module exit, scene close,
  cleanup, and Step 5C isolation. The transient override is excluded from MRB
  save and resumed afterward.
- Added focused Slicer-native math cases for arbitrary and vertical axes,
  orthonormal/right-handed bases, midpoint placement, 90-degree rotation,
  in-plane endpoints, and degenerate/non-finite rejection. Python compilation,
  Qt UI XML, and whitespace checks passed; the new Slicer-native tests and live
  interaction/FPS acceptance were not run because no Slicer launch was
  authorized. No Git/Drive synchronization occurred.

## 2026-08-10 14:11:28 IST (UTC+05:30) — ROI-aligned Step 5C yaw workspace

- Replaced the fixed-anterior, simultaneous multi-view isolation with a
  temporary one-up 3D workspace driven by the current Step 5B automatic ROI.
  At yaw zero the camera looks along ROI `+Y`, ROI `+X` is viewport right, ROI
  `+Z` is viewport up, and the ROI Z extent fits the viewport top-to-bottom.
- Added a default lock for translation, zoom, pitch, and roll while preserving
  360-degree yaw around ROI `+Z`, plus an independent yaw lock that freezes the
  view. Camera corrections are coalesced and change only drifted properties.
  Isolation now preserves/restores layout, camera, crosshair, and visibility
  and no longer creates a markup or enters placement mode.
- Made Step 4A and Step 5B workflow-owned ROI nodes locked and non-selectable
  from views with all interaction handles disabled, including loaded scenes.
  Step 5B recomputes its axis-aligned automatic bounds before shell generation;
  its existing role name is retained only for scene compatibility.
- Added parameter defaults, camera-pose/yaw math coverage, ROI interaction-
  policy assertions, and relock-after-refresh coverage. Python compilation,
  Qt UI XML, `git diff --check`, and the repository static gate passed.
- No Slicer process was launched, so native mouse yaw, exact visual fit,
  layout/camera restoration, and FPS remain developer acceptance items. No
  inference, medical-data inspection, STL export, ROS, robot, motion, drilling,
  fabrication, Git publication, or Drive synchronization occurred.

## 2026-08-07 17:50:52 IST (UTC+05:30) — Step 5C shell finalization and export gate

- Moved the shell/sleeve STL action out of Step 5B and added Step 5C as a
  non-destructive finalization boundary. The raw Step 5B shell remains intact;
  export now requires a Current, source-matched, watertight Step 5C shell and a
  Current Step 5B sleeve.
- Added an isolated anterior parallel world-RAS view, optional camera/plane
  orientation lock, one-click horizontal-height Markups plane placement,
  positive/negative capped Dynamic Modeler Plane Cut, and adjustable
  surface-snapped closed-curve inside/outside Curve Cut. Curve output receives
  explicit capping, triangulation, cleanup, normals, and topology validation.
- Persisted method, kept region, plane/curve/final-shell references, source
  revision, edit geometry, Dynamic Modeler provenance, topology metrics,
  lineage, and Current/Stale state. Added owned Step 5C reset, Step 5B-to-5C
  cascade cleanup, expert Dynamic Modeler handoff, raw-shell export rejection,
  and MRB save/reopen coverage.
- Python compilation, Qt UI XML, and whitespace checks passed. Focused Plane
  Cut, Curve Cut, Step 5B/5C, UI load, and isolated-view tests passed. The
  correctly registered complete Slicer-native suite reached
  `DENTOWORKFLOW_FULL_SUITE_PASSED`; its source-build process returned 1 only
  after that marker because of the known VTK debug-leak reporter.
- No automatic 70–80 percent coverage, dental/occlusal frame, gingival-margin
  detection, fit validation, or clinical/print approval was added. No patient
  data, inference, ROS, robot, motion, drilling, or fabrication operation ran.

## 2026-08-07 17:06:17 IST (UTC+05:30) — Visible Step 5A/5B lineage controls

- Corrected the downstream color presentation gap reported after the Step 4A
  lineage work. The MRML nodes already received the inherited display color,
  but only the Step 4A selector exposed a UI swatch.
- Added explicit colored FDI/hex lineage badges to Steps 5A and 5B, matching
  swatches to the Step 5A model and Step 5B ROI/shell/sleeve selectors, and
  matching stripes to all six Step 5B Scene visibility controls. The cues are
  refreshed from persisted lineage attributes and remain display-only.
- Extended the active-widget regression to prove the Step 4A color reaches all
  downstream nodes and is visible in every new control. The focused UI test
  exited 0 with `DOWNSTREAM_LINEAGE_UI_TEST_PASSED`; the active-widget Step 5B
  geometry test and full Slicer-native suite reached their pass markers. The
  latter source-build processes returned 1 only after success because of the
  known VTK debug-leak reporter.
- A read-only older Step 5A MRB had no selected trajectory/model parameter
  references despite retaining its target ID and role-owned nodes. Added a
  display-only fallback that recovers the matching persisted target lineage
  without guessing which trajectory to select. It backfilled FDI 14 into the
  legacy Step 5A model and both badges, reaching
  `LEGACY_DOWNSTREAM_LINEAGE_UI_CHECK_PASSED` with exit 0.
- Git and Drive were not synchronized. No inference, export, robot, motion,
  drilling, fabrication, or patient-facing action ran.

## 2026-08-07 16:46:13 IST (UTC+05:30) — Step 4A lineage groups and invariant completion

- Completed the remaining Step 4A assistance backlog. Multiple trajectories
  stay visible in one selector; target-tooth selection emphasizes the matching
  group and restores the correct tooth without retargeting a line that belongs
  to another tooth. Each segmentation/tooth pair now retains its own bounds
  ROI rather than reusing and mutating another target's box.
- Added deterministic persisted target-tooth colors and selector swatches.
  The same RGB lineage is propagated through MRML references to the Step 4A
  bounds, Step 5A support anatomy, and Step 5B trim ROI, shell, and sleeve.
  Colors remain presentation metadata; references, roles, and segment IDs are
  authoritative.
- Enforced the Markups-line two-control-point Entry/Target contract and added
  active/inactive group display emphasis that preserves explicit visibility.
  Hardened Step 4A/5A/5B deletion by clearing workflow references before MRML
  removal, preventing live selectors from substituting unrelated nodes.
- Extended synthetic logic, active-widget, persistence, lineage, target-switch,
  ROI isolation, and clean-deletion regressions. Python AST parsing, Qt UI XML
  parsing, and `git diff --check` passed. The complete Slicer-native suite
  reached `DENTOWORKFLOW_FULL_SUITE_PASSED`; its source-build process returned
  1 only after the marker because of the known VTK debug-leak reporter. The
  supplied legacy MRB independently exited 0 with
  `LEGACY_SCENE_COMPATIBILITY_CHECK_PASSED` and no cross-role ROI.
- No inference, medical-data inspection, ROS, robot, motion, drilling,
  fabrication, or patient-facing action ran. Git and Drive were not
  synchronized.

## 2026-08-07 15:56:00 IST (UTC+05:30) — Step 5B ROI role isolation and legacy-scene repair

- Restricted the shell-ROI selector to
  `DENTOBOT.MarkupsRole=TemplateShellTrimROI` and disabled arbitrary ROI
  creation from the selector. Step 5B reset, generation, and deletion now
  reject Step 4A target bounds and unrelated ROIs; reset/generation also reject
  an ROI whose source reference is not the current Step 5A model.
- Added an in-place legacy repair for a Step 4A bounds ROI contaminated with
  Step 5B role/schema/source metadata. Invalid Step 5B parameter references are
  cleared without deleting their scene nodes, and the parameter-to-widget
  update path now has a re-entry barrier for nested MRML Modified events.
- Added synthetic regressions for selector auto-selection, cross-role repair
  without duplication, wrong-role/source rejection, and safe deletion. The
  focused tests and complete DENTOWorkflow suite reached their pass markers;
  the reported legacy `2026-07-23-Scene_5a.mrb` then passed a read-only load
  with no recursion, invalid Step 5B reference, or remaining cross-role ROI.
- Slicer's source-build VTK debug-leak reporter still makes the headless test
  process return status 1 after the pass marker; the separate legacy-scene
  compatibility process exited 0. No scene was overwritten, no medical data
  details were logged, and Git/Drive were not synchronized.

## 2026-08-07 15:18:18 IST (UTC+05:30) — Step 5B scene visibility controls

- Added a Step 5B Scene visibility panel for the selected Step 4A target box
  and trajectory, Step 5A support anatomy, Step 5B shell ROI, research shell,
  and research sleeve. Controls change MRML display visibility only.
- Updated target-bounds refresh, Step 5A model update, Step 5B ROI reset, and
  shell/sleeve regeneration to preserve an existing hidden state. MRB tests
  verify that hidden state survives save/reopen.
- Added role-driven `[Step 4A]`, `[Step 5A]`, and `[Step 5B]` node-name
  prefixes for DENTO selectors and Slicer's Data view. Names remain
  presentation labels and are not used for ownership, identity, or dependency
  decisions.
- Extended logic and widget regression coverage. Python AST parsing, Qt UI XML
  parsing, `git diff --check`, focused Slicer-native tests, and the complete
  DENTOWorkflow suite passed in the existing container. Git and Drive were not
  synchronized.

## 2026-08-06 23:05:48 IST (UTC+05:30) — Step 4A restoration and Step 5B ROI reset

- Restored a selected trajectory's persisted target segmentation, tooth ID,
  target-bounds ROI, selector state, highlight, and details during both MRB
  scene refresh and manual selector changes. Invalid partial/mismatched
  associations are rejected rather than silently overwritten.
- Added managed trajectory labels containing FDI, per-tooth sequence, and
  Empty/Entry only/Complete/Invalid state. Legacy default names are upgraded;
  editable names remain presentation only and never determine identity.
- Added a confirmed, role-gated **Delete Shell ROI** action. It removes the ROI
  and unshared auxiliaries, retains upstream planning and existing Step 5B
  models, and marks retained shell/sleeve outputs Stale.
- Added MRB persistence, duplicate-name, scene-load widget, selector widget,
  ownership-rejection, and ROI-deletion regression coverage. AST/XML parsing,
  `git diff --check`, focused Slicer-native tests, and the complete
  DENTOWorkflow Slicer-native suite passed in the existing container.
- The requested future closed-loop cascade deletion rule is awaiting scope
  confirmation before destructive behavior is implemented. Git and Drive were
  not synchronized.

## 2026-08-06 22:07:01 IST (UTC+05:30) — EndoPlanner inspection and Step 5B research geometry

### Added and changed

- Made the local untracked EndoPlanner preview load for UI inspection without
  installing packages into Slicer's embedded Python by making its optional
  imports non-fatal and adding a Slicer 5.10 ROI-class fallback.
- Corrected the persistent Slicer settings bind from the unused
  `/root/.config/NA-MIC` path to `/root/.config/slicer.org`; the launcher now
  includes the EndoPlanner checkout when it exists.
- Added Step 5B UI, parameter-node state, MRML role/provenance contracts, and a
  model-independent VTK geometry helper. Step 5B generates an ROI-trimmed
  clearance shell with a trajectory channel and a separate hollow sleeve.
- Added stale-input detection, sampling caps, topology metrics, overlap/
  multi-region warnings, role-gated confirmed deletion, binary STL export with
  atomic replacement, and MRB persistence coverage.

### Evidence and limitations

- EndoPlanner and DENTO Workflow both instantiated in isolated Slicer 5.10
  startups. No EndoPlanner dependency was installed; its processing remains
  incomplete because the preview omits weights and called helpers.
- Python AST, Qt UI XML, shell syntax, launcher preflight, backend identity,
  container recreation, GPU render-node/priority checks, the focused Step 5B
  synthetic test, and the full Slicer-native DENTO Workflow suite passed.
- Synthetic Step 5B outputs were watertight, exported to non-empty binary STL,
  survived MRB save/reload, and were safely deleted while their source model,
  trajectory, and ROI remained. No patient data, trained-model inference,
  robot, drilling, fabrication, or clinical operation ran.
- Representative anatomy, contact/removability, gingival clearance, sleeve/bit
  fit, printability, material/process parameters, and clinical safety remain
  unvalidated.

## 2026-08-06 19:21:52 IST (UTC+05:30) — Central configuration and Git-controlled workspace

### Added and changed

- Moved the active Ubuntu launcher/helpers, Compose definition, agent
  entrypoint, and documentation intact into the existing repository's tracked
  `Workspace/` layer. Relative symlinks preserve all former top-level paths.
- Added a safe workspace bootstrap, top-level Git helper, explicit absolute
  Compose mounts, and one ignored `.dentobot.env` for workstation-specific
  backend/render values.
- Disabled pytest's optional cache provider in the close check so
  container-owned cache residue does not generate host permission warnings.
- Made the launcher the runtime configuration authority and made DENTO
  Workflow consume its interpreter and run-record root automatically without
  saving machine paths into MRB scenes. Manual values remain advanced
  overrides, and the UI now explains the local input/output/JSON run records.
- Installed repository-pinned pytest 8.4.2 in the dedicated Conda backend;
  no Slicer Python package was changed.
- Updated setup, decisions, tasks, architecture, traceability, transfer, and
  synchronization guidance for the consolidated structure.

### Evidence and limitations

- Shell syntax, bootstrap/symlink resolution, launcher configuration lookup,
  Git helper, Compose rendering, Python AST, Qt UI XML, `pip check`, and all
  13 inference tests passed.
- No Slicer GUI/native test or inference/model process ran. No medical image,
  run record, model, patient data, credential, robot, motion, drilling, or
  fabrication artifact was added to Git or Drive.
- The GitHub CLI token was invalid when checked, so non-force publication
  requires re-authentication. Drive synchronization uses existing IDs only.

## 2026-08-04 13:42:57 IST (UTC+05:30) — Hardware rendering verified and safe output deletion added

### Added and changed

- Generalized the Ubuntu graphics setup guidance for Mesa-backed Intel/AMD
  render-node passthrough, multi-GPU node selection, non-root render-group
  access, NVIDIA's distinct container path, hardware-renderer checks, and
  Slicer's Linux process-priority override. The verified Intel Arrow Lake-S
  `i915` configuration remains the prioritized example.
- Added dedicated, confirmed deletion controls for the selected Step 4A
  DENTOBOT trajectory and Step 5A DENTOBOT draft support-anatomy model.
- Added role validation, workflow-reference cleanup, and conservative
  auxiliary-node destruction: display/storage nodes are removed only when no
  remaining scene node references them. Target, segmentation, bounds, manual
  support selection, shared auxiliaries, and unrelated user nodes are kept.
- Added Slicer-native coverage for deletion rejection, selective destruction,
  MRB save/reload, absence of dangling references, preserved source state,
  and successful recreation.
- Recorded the developer's instruction to batch notes and request approval
  before periodic Drive/Git synchronization rather than syncing each prompt.

### Evidence and limitations

- After authorized service recreation, direct GLX reported
  `Mesa Intel(R) Graphics (ARL)`, OpenGL 4.6, and direct rendering. The live
  Slicer process remained at nice level 0 and held four descriptors to the
  `i915` render node. User-perceived FPS on the original workload remains to
  be confirmed.
- `git diff --check` and `Infrastructure/close_day_checks.sh` passed: 20
  Python ASTs, two Qt UI files, eight controlled Markdown files, and Markdown
  fences. Backend tests were skipped because backend source was unchanged.
- The new Slicer-native deletion/persistence test was added but not run. No
  inference, segmentation, model download, patient data, robot, motion,
  drilling, fabrication, or clinical operation occurred.

## 2026-08-04 13:13:58 IST (UTC+05:30) — Slicer rendering bottlenecks configured for correction

### Added and changed

- Added Intel `/dev/dri/renderD128` passthrough to the ordinary SlicerROS2
  Compose service.
- Set Slicer's documented `SLICER_BACKGROUND_THREAD_PRIORITY=0` environment
  override to prevent its Linux background-thread setup from lowering the
  entire interactive process to nice level 19.
- Extended the daily launcher to require the host render node, verify it in
  the container, and verify the priority override before opening Slicer.
- Updated the active setup, decision, task, and dated logbook records.

### Evidence and limitations

- The pre-change live container had no `/dev/dri`; `SlicerApp-real` ran at
  nice level 19 and loaded Mesa/LLVM while the developer observed low FPS.
  The host exposes an Intel Arrow Lake-S render node and uses the `i915`
  kernel driver. The image includes Mesa's Intel `iris` driver path.
- `bash -n scripts/launch-dentoworkflow.bash` and `docker compose config -q`
  passed, and rendered Compose output contains the expected device and
  environment settings.
- The running service was deliberately not recreated because Slicer is open
  and its scene may be unsaved. Hardware renderer identity, live process
  priority, device use, comparative FPS, and user-perceived responsiveness
  remain unverified. No inference, model, patient data, ROS test, robot,
  motion, drilling, or fabrication operation occurred.

## 2026-08-03 17:36:17 IST (UTC+05:30) — Slicer health-process lifecycle gate closed

### Added and changed

- Updated the nested DENTOBOT Slicer 5.10 adapter so its fallback `QProcess`
  has explicit Qt parent ownership and disconnect/close/delete-later teardown.
- Added deterministic Bridge A harness cleanup and a direct headless-Slicer
  launcher with authoritative exit-code propagation.
- Reconciled the active Ubuntu task list and technical decisions with the
  migrated nested Git checkout and the ordered post-checkpoint gates.

### Verification and limitations

- Static checks passed for 20 Python ASTs, two Qt UI files, eight controlled
  nested Markdown files, Markdown fences, and Git whitespace.
- The full checkpoint backend passed explicit-CPU health. Two consecutive
  network-disabled, source-read-only Slicer 5.10 Bridge A probes passed in
  7.758992707 and 5.913129843 seconds; Slicer/backend processes exited and
  disposable containers were removed.
- The ordinary Compose container remains the minimal Bridge B runtime and was
  restored to its pre-session stopped state. No segmentation, model download,
  patient data, robot process, or clinical operation occurred.
- Clean checkpoint-image reconstruction is the next gate. No commit, tag,
  push, clean rebuild, NPU test, MRB reopen, Bridge B, or Bridge C run is
  claimed by this entry.

## 2026-07-31 16:30:30 IST (UTC+05:30) — Conda-backed one-command DENTO Workflow launcher

### Added and changed

- Added `scripts/launch-dentoworkflow.bash` as the daily Ubuntu entry point.
  It validates the backend, starts or unpauses Compose, scopes X11 access to
  the Slicer process, adds the repository module path, and automatically
  selects DENTO Workflow.
- Initialized the existing empty `dentobot` Conda environment with Python
  3.12.13, DENTOBOT inference 0.2.0, NumPy 2.2.6, NiBabel 5.4.2, packaging
  26.2, and typing-extensions 4.16.0.
- Replaced the provisional `/opt/dentobot-venv` Docker-volume design with a
  read-only bind mount of
  `/home/light-tarun/miniconda3/envs/dentobot` at the same container path.
- Updated DENTO Workflow's Linux default backend path and the synthetic Bridge
  B test launcher to use the Conda interpreter.

### Verification and limitations

- `scripts/launch-dentoworkflow.bash --check-only` passed after Compose
  recreated the service with the Conda mount.
- The full synthetic Bridge B test passed under
  `data/test-artifacts/bridge-b-l3V0RG`: backend status was `ok`, geometry and
  data matched, and the deliberate `0.01` mm geometry error was rejected.
- A headless Slicer startup reported `DENTO_AUTO_SELECTED=DENTOWorkflow`,
  proving module discovery and automatic selection. Its forced headless quit
  produced the known upstream VTK-leak exit diagnostic; interactive Slicer was
  not visually inspected in this execution environment.
- An initial package install from the source tree failed because generated
  egg-info files are owned by `nobody`; installation from an isolated
  temporary source copy succeeded. A no-write AST parse is used for source
  syntax verification because the existing module `__pycache__` is likewise
  not host-writable.
- The Conda environment currently supports Bridge B only. It does not yet
  include PyTorch, TotalSegmentator, CUDA model dependencies, or weights. No
  patient data, robot hardware, motion, or safety-critical operation was used.

## 2026-07-31 14:47:02 IST (UTC+05:30) — Synthetic MRML/NIfTI Bridge B validation

### Added and changed

- Added a two-phase headless Slicer test that generates an oblique,
  anisotropic int16 MRML volume, exports it as NIfTI, and validates the
  returned NIfTI against recorded voxels and IJK-to-RAS geometry.
- Added a launcher and orchestration script that execute the existing
  `dentobot_inference roundtrip` backend between Slicer export and import.
- Added a controlled negative check that perturbs one RAS translation element
  by `0.01` mm and requires DENTOWorkflow's geometry validator to reject it.
- Added an Ubuntu synthetic Bridge B evidence section to the controlled
  reproducibility record.

### Verification and limitations

- The final run used Slicer 5.10.0, external Python 3.12.3,
  DENTOBOT inference 0.2.0, NumPy 2.2.6, and NiBabel 5.4.2.
- Backend `geometryMatch` and `dataMatch` were true. Slicer re-imported exact
  `4 x 5 x 6` int16 voxels with KJI SHA-256
  `26f20beee1e0aa33140dbabf55d17853bc1265e1f9a9718c1e7ba92f3d557bd6`.
- The maximum IJK-to-RAS difference was approximately `4.77e-08`, and the
  deliberate `0.01` mm mismatch was rejected.
- Both Slicer phases and the backend exited 0. The temporary backend reported
  no broken Python requirements.
- This does not validate real DICOM/CBCT, segmentation labels, the interactive
  asynchronous adapter, anatomy, registration, or clinical behavior. No
  patient data or hardware was used, and nothing was reverted.

## 2026-07-31 14:20:54 IST (UTC+05:30) — SlicerROS2 imaging bridge verification

### Added and changed

- Added a host Lyrical synthetic-image probe using the system ROS Python and a
  headless Slicer test that bridges ROS images to and from an MRML scalar
  volume.
- Added an upstream-CI-style launcher for reproducible headless execution.
- Recorded standard ROS image transport as pixel plumbing rather than the
  geometry-preserving CBCT/segmentation exchange contract.
- The upstream suite installed `psutil 7.2.2` into the running container's
  embedded Slicer Python because the dependency was initially absent.

### Verification and limitations

- All 23 upstream SlicerROS2 tests passed in 22.694 seconds.
- The custom host/Slicer probe verified exact mono8 dimensions and pixel
  payloads in both directions; both final processes exited 0.
- After restarting the Compose service, domain 73, subnet discovery, and the
  SlicerROS2 overlay remained present, and the same image probe passed again.
- Early probe attempts exposed Miniconda `python3` shadowing the Ubuntu system
  interpreter and a nonzero Slicer `--python-script` shutdown path. The final
  probe uses `/usr/bin/python3`, an upstream-style `--python-code` launcher,
  explicit MRML/ROS endpoint cleanup, and exits cleanly.
- The Slicer run still prints upstream VTK leak diagnostics and benign
  create-before-first-spin warnings. Real CBCT geometry, affine and RAS/LPS
  semantics, segmentation data, custom DENTOBOT interfaces, latency,
  registration, and safety remain unverified. No hardware or patient data was
  used, and nothing was reverted.

## 2026-07-31 13:05:16 IST (UTC+05:30) — Lyrical/Jazzy interoperability baseline

### Added and changed

- Extended `scripts/source-host-ros2.bash` with DENTOBOT domain 73, subnet
  discovery, a localhost-only guard, domain override support, and conditional
  sourcing of a future separate host-native Lyrical overlay.
- Added matching ROS domain and discovery defaults to the SlicerROS2 Compose
  service and recreated the existing container from the unchanged image.
- Recorded that the project is in conceptual design, no robot hardware
  exists, and current implementation priority is the 3D Slicer
  medical-imaging workflow.

### Verification and limitations

- Helper syntax, source behavior, localhost-only rejection, and direct-
  execution rejection passed.
- Host Lyrical to container Jazzy and container Jazzy to host Lyrical
  `std_msgs/msg/String` tests passed with exact payloads.
- A host Lyrical `geometry_msgs/msg/TransformStamped` message was received
  exactly by the Jazzy container. Its frames and pose were explicitly
  simulated test values.
- A final host-to-container string test passed using only the persisted
  Compose discovery defaults.
- These results cover basic DDS discovery, transport, and the tested standard
  messages only. Custom SlicerROS2 interfaces, medical-image exchange,
  coordinate semantics, registration, tracking, timing, robot control,
  drilling, and safety were not tested. Nothing was reverted.

## 2026-07-31 12:29:42 IST (UTC+05:30) — Host ROS 2 Lyrical installation

### Added and changed

- Added the official Resolute `ros2-apt-source` package and installed ROS 2
  Lyrical Desktop plus `ros-dev-tools` on Ubuntu 26.04.
- Initialized rosdep and updated the user dependency cache.
- Added `scripts/source-host-ros2.bash` for explicit, guarded host Lyrical
  activation. Global shell startup remains unchanged.
- Documented the host Lyrical versus container Jazzy boundary, verification
  commands, workspace isolation rule, and interoperability backlog.

### Verification and limitations

- `dpkg --audit` returned no package-state errors. Installed package status
  was confirmed for `ros2-apt-source`, `ros-lyrical-desktop`, and
  `ros-dev-tools`.
- The sourced environment reported `ROS_DISTRO=lyrical`, ROS 2 version 2,
  Python 3, 287 packages, and `rmw_fastrtps_cpp`.
- A bounded Lyrical C++ talker published messages and the Python listener
  received messages 2 through 9. Both commands ended by the intentional
  10-second timeout.
- No robot, tracker, drilling, motion, patient data, or safety-critical
  operation was run.
- Host Lyrical to container Jazzy interoperability, host workspace builds,
  SlicerROS2 functional integration, and hardware behavior remain unverified.
  Nothing was reverted.

## 2026-07-24 16:11:03 IST (UTC+05:30) — Step 3C acceptance and quiet negative test

### Accepted and changed

- Recorded the developer's successful completion of the complete Step 3C
  checklist in Slicer 5.12.2. The selected label, authoritative segmentation,
  and source CBCT were correctly handed to Segment Editor; correction state,
  baseline-metric messaging, correction activity, and MRB persistence behaved
  as intended.
- Marked Steps 3A, 3B, and 3C developer-verified at the current Step 3 scope.
- Reworked the missing-source negative test to temporarily remove and restore
  the source reference on the existing valid test segmentation instead of
  creating a scene-owned orphan segmentation. This preserves the same
  `ValueError` coverage while avoiding expected Subject Hierarchy warnings.

### Verification and limitations

- The application workflow and Step 3C checklist were run by the developer in
  Slicer 5.12.2 and reported successful.
- The observed `CorrectionWithoutSource` Qt messages were traced to the
  deliberate negative-test fixture, not the real segmentation or correction
  workflow. The revised quiet fixture is statically validated here but still
  needs one future in-Slicer self-test run to confirm the console is quiet.
- Replaced `AGENTS.md`, `DEVELOPMENT_PLAN.md`, `changelog.md`, and
  `logbook.md` in place in the Drive mirror. Metadata readback confirmed the
  existing file IDs and byte sizes matching the local files.
- No anatomical or clinical accuracy claim was added. Corrected-mask metric
  recomputation and per-label review states remain optional later work.
- Nothing was reverted.

## 2026-07-24 15:50:44 IST (UTC+05:30) — Step 3C correction handoff

### Added and changed

- Added `Edit Selected Label in Segment Editor` to the segmentation review
  panel.
- Added strict handoff validation for the selected segment and the
  segmentation's persisted `DENTOBOT.SourceVolume` CBCT reference.
- Configured Slicer's built-in Segment Editor with the authoritative
  segmentation, source volume, and selected segment instead of copying masks
  or embedding another editing implementation.
- Starting a correction revision now conservatively sets the whole
  segmentation to `Needs Correction`, records a UTC correction-start time,
  and marks imported voxel/volume metrics as pre-correction inference
  baselines.
- Added content-specific observation of source-representation modifications
  and segment addition/removal while DENTO Workflow is active. These changes
  record the mask-edit timestamp and invalidate a previously `Reviewed`
  result; display, naming, selection, and metadata changes do not.
- Updated selected-label and provenance UI language so original inference
  metrics are not presented as current measurements after correction begins.
- Extended Slicer-native logic tests for source-volume validation, correction
  handoff state, metric validity, edit timestamps, automatic review
  invalidation, and invalid segment IDs.
- Recorded the developer's confirmation that Steps 3A and 3B work as intended
  in Slicer 5.12.2 and that the universal review state is intentional.

### Preserved

- The authoritative segmentation node, source geometry, original inference
  artifacts/provenance, and universal review-state model are preserved.
- No per-label approval state, corrected-mask metric recomputation,
  registration, planning, navigation, robotics, ROS, or clinical validation
  was added.

### Verification and limitations

- Official Slicer source and Slicer 5.12 developer documentation were checked
  for Segment Editor setters and `vtkSegmentation` event semantics.
- All 11 repository Python files passed AST parsing without importing the
  Slicer module in system Python. The Qt UI passed XML parsing; all 57
  `self.ui.*` references and 16 statically discovered callbacks resolve, UI
  object names are unique, Markdown fences are balanced, and `git diff
  --check` is clean.
- Slicer, WSL, CUDA, TotalSegmentator, DICOM, patient data, and installed
  Slicer files were not launched or modified during implementation.
- Replaced `AGENTS.md`, `ARCHITECTURE.md`, `DEVELOPMENT_PLAN.md`,
  `changelog.md`, and `logbook.md` in place in the Drive mirror. Folder
  readback confirmed stable file IDs and byte sizes matching the local files.
- Step 3C's Slicer-native test and manual Segment Editor handoff remain
  pending in the developer's Slicer 5.12.2 runtime. Nothing was reverted.

## 2026-07-24 15:06:56 IST (UTC+05:30) — Step 3B metrics, provenance, and review state

### Added and changed

- Extended the `Segmentation Review` panel with selected-label details:
  human-facing anatomy, source label, FDI number, model label ID, voxel count,
  and physical volume in mm³ and cm³.
- Added a compact provenance summary for run ID, source CBCT, backend and
  TotalSegmentator versions, model task/dataset/crop, CUDA device, inference
  and total time, and completion timestamp.
- Added segmentation-level `Unreviewed`, `Needs Correction`, and `Reviewed`
  workflow states with a persistent UTC update timestamp. UI warnings state
  explicitly that `Reviewed` is not clinical validation.
- Added a proper `DENTOBOT.SourceVolume` MRML node reference and versioned
  `DENTOBOT.SegmentMetricsJson` data keyed by stable segment ID. New Bridge C
  imports now persist the validated result's per-label metrics and expanded
  provenance directly on the segmentation node.
- Added a non-fatal compatibility path for older imported Bridge C results:
  when versioned review metadata is absent, the module attempts to validate
  and migrate the retained `result.json`. Missing or invalid retained
  metadata produces a visible warning without discarding the segmentation.
- Consolidated Bridge C provenance assignment through the new metadata
  enrichment routine after successful output validation and import.
- Extended Slicer-native logic tests for source-node references, per-label
  metric mapping, provenance rendering, review-state persistence, and invalid
  review-state rejection.
- Updated the controlled agent, architecture, and development-plan documents
  to record the Step 3B schema and remaining Step 3C boundary.

### Preserved

- Segment masks, reference geometry, inference commands, CUDA-only policy,
  artifact validation, and the Step 3A display behavior are unchanged.
- Segment Editor correction, edit-driven review invalidation, clinical
  approval, registration, planning, navigation, robot control, and ROS remain
  outside this increment.

### Verification and limitations

- All 11 repository Python files passed AST parsing without importing the
  Slicer module in system Python.
- `DENTOWorkflow.ui` passed XML parsing; all 54 `self.ui.*` references resolve
  to declared UI objects, and all 15 statically discovered signal callback
  methods exist.
- Slicer, WSL, CUDA, TotalSegmentator, DICOM, patient data, and installed
  Slicer files were not launched or modified.
- Updated the existing Drive files for `AGENTS.md`, `ARCHITECTURE.md`,
  `DEVELOPMENT_PLAN.md`, `changelog.md`, and `logbook.md` in place. Folder
  readback confirmed the same five file IDs and matching byte sizes.
- The extended Slicer-native test, known-label metric comparison, and MRB
  scene save/reopen acceptance remain pending in official Slicer 5.12.2.
  Nothing was reverted.

## 2026-07-24 15:00:25 IST (UTC+05:30) — Git version-control baseline

### Added and changed

- Added a repository-root `.gitignore` covering Python caches and packaging
  output, local environments, CMake build products, editor metadata, runtime
  artifacts, local environment files, and common medical/research image
  formats.
- Established Git as the source-version history from this project state
  forward. Material implementation and architecture commits continue to be
  described in this changelog and in `docs/logbook.md`.

### Safety and limitations

- Source medical/research data remains outside version control by default.
- No patient data, credentials, installed Slicer files, dependencies, models,
  or application behavior were changed.
- The GitHub remote is pending the repository URL and the initial push is
  therefore not part of this local baseline.

### Verification

- The ignore rules and staged baseline were inspected with Git locally.
- No Slicer, WSL, CUDA, model, robot, or hardware process was run.

## 2026-07-24 14:29:14 IST (UTC+05:30) — Step 3A segmentation explorer

### Added and changed

- Added a `Segmentation Review` panel to `DENTOWorkflow.ui` with a persistent
  segmentation selector, anatomy/FDI search, grouped label tree, visibility
  checkboxes, show/hide/isolate actions, 2D/3D visibility toggles, and opacity
  sliders.
- Added deterministic review descriptors for TotalSegmentator labels,
  including human-facing FDI tooth names and categories for teeth, pulp,
  jaws, neural/mandibular canals, sinuses/airway, restorations/implants, and
  other anatomy.
- Added reusable MRML logic for segment enumeration, visibility, isolation,
  selected-segment emphasis, and global 2D/3D display control.
- Reused the existing `teethSegmentation` parameter-node reference. Existing
  Bridge C results are auto-selected by their `DENTOBOT.BridgeOperation`
  provenance when no persistent selection exists.
- Added segmentation/display observers with cleanup and rebinding across
  node replacement, module exit, scene close, and cleanup.
- A successful Bridge C completion now collapses the backend panel and opens
  the review panel.
- Added Slicer-native logic coverage for FDI/category mapping, result
  discovery, visibility, isolation, emphasis, opacity, and invalid inputs.

### Preserved

- Bridge C command construction, inference, NIfTI validation, segmentation
  import, provenance, and source geometry were not changed.
- Review actions modify only MRML display properties; they do not duplicate,
  edit, resample, or otherwise change segmentation masks.
- Step 3B review state/provenance and Step 3C Segment Editor handoff remain
  outside this increment.

### Verification and limitations

- The Python source passed AST parsing. The Qt Designer file passed XML
  parsing; all 38 `self.ui.*` references resolve to declared UI objects, and
  the new selector has an MRML-scene connection.
- The display methods were checked against official Slicer segmentation
  display-node documentation.
- Slicer was not launched. The new Slicer-native test and manual 60-label UI
  acceptance run remain pending in official Slicer 5.12.2.
- No WSL, CUDA, model, inference, DICOM, patient data, installed Slicer file,
  or run artifact was changed. Nothing was reverted.

## 2026-07-24 13:55:18 IST (UTC+05:30) — Formal inference reproducibility baseline

### Added and changed

- Added `docs/REPRODUCIBILITY_AND_TRACEABILITY.md` as the controlled,
  professional installation, reconstruction, evidence, and diagnostic
  procedure for the external inference environment.
- Reworked `Inference/README.md` into a concise operational entry point with
  the Slicer/WSL boundary, validated setup commands, explicit model-cache
  preparation, verification, bridge configuration, commands, artifact rules,
  and limitations.
- Reduced `Inference/environment.yml` to a Python 3.10.20 Conda bootstrap and
  added exact validated top-level pip manifests under
  `Inference/requirements/`.
- Added `Inference/validated-environment.json`, recording backend 0.2.0,
  Slicer 5.12.2, the successful package/CUDA/GPU/model-task baseline, and the
  scope of the evidence run without patient identifiers.
- Updated the architecture, project context, development plan, and agent rules
  to distinguish controlled professional documentation from raw audit records.

### Deferred by decision

- Bridge C's verified happy path is accepted for continued development.
  Failure injection, cancellation/process cleanup, five segmentation-focused
  WSL tests, MRB persistence, anatomical validation, a complete transitive
  lock, and a clean-machine rebuild remain explicit later TODOs.
- The top-level pins are not described as a complete dependency lock.

### Verification and limitations

- The JSON baseline was parsed, dependency files and internal documentation
  links were checked, and Markdown structure was reviewed locally.
- Version values were grounded in the retained successful Bridge C
  `result.json` and official TotalSegmentator, PyTorch, Conda, and NVIDIA WSL
  installation guidance.
- No Slicer, WSL, model, CUDA, or inference process was launched in this
  documentation/dependency-manifest change. No patient data, installed Slicer
  file, model cache, or run artifact was modified or uploaded.
- Nothing was reverted.

## 2026-07-23 21:41:08 IST (UTC+05:30) — Bridge C real-CBCT runtime evidence

### Verified

- Developer-supplied evidence from official 3D Slicer 5.12.2 confirms that the
  Bridge C happy path completed without a displayed error.
- The selected real CBCT had dimensions 580 x 580 x 300, 0.25 mm isotropic
  spacing, signed-short scalar storage, valid IJK-to-RAS geometry, and was the
  same `Unnamed Series` shown as **Bridge input**.
- The GPU-only TotalSegmentator path completed teeth task 113 with
  craniofacial crop task 115 and returned an integer multilabel NIfTI matching
  the source 580 x 580 x 300 grid.
- Slicer retained `DENTOsegmentation_Teeth_93cbd5d1` with 60 validated
  segments. Colored masks were visible in the 2D slice views and the
  closed-surface representation was visible in the 3D view.
- The displayed metrics were 75.2 seconds total runtime, 48.65 cm^3 foreground
  volume, and 2.16 GiB peak GPU allocation. The terminal report showed
  `status: ok` and retained the research-output warning.

### Status changes

- Updated `AGENTS.md` and `DEVELOPMENT_PLAN.md` from “Bridge C runtime pending”
  to “core happy-path runtime verified.”
- This evidence verifies model-cache readiness, GPU inference, output contract
  validation, MRML import, label naming/coloring, and immediate 2D/3D display
  for one representative CBCT.

### Limitations

- The screenshot demonstrates technical execution and visual alignment, not
  anatomical accuracy, clinical validity, completeness against ground truth,
  or suitability for planning.
- The five new WSL unit tests, explicit error/cancellation paths, exact
  dependency lock, and MRB save/reopen persistence are not evidenced by this
  update and remain pending.
- No source code, installed Slicer file, environment, model, or patient data
  was changed or uploaded. Nothing was reverted.

### Files affected

- `docs/AGENTS.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/changelog.md`
- `docs/logbook.md`
- Corresponding raw Markdown mirrors in `IITM Dentobot/docs`

## 2026-07-23 21:34:29 IST (UTC+05:30) — Documentation mirror and final Bridge C static checks

### Added

- Established `IITM Dentobot/docs` in the connected Google Drive as a raw
  Markdown mirror of the repository's six documentation files.
- Added a standing agent rule: local repository documents remain canonical;
  changelog/logbook requests include an in-place sync of their corresponding
  Drive files plus any other design documents changed in the same batch.
- Explicitly excluded patient data, DICOM/NIfTI, segmentations, run artifacts,
  models, credentials, and other non-document data from this Drive workflow.

### Verified since the preceding entry

- `dentobot_inference --help` and `segment-teeth --help` both parsed and exposed
  the expected Bridge C command and required arguments.
- All 23 `self.ui.*` references in `DENTOWorkflow.py` matched objects in the Qt
  Designer file.
- Ten Python files passed AST parsing; the UI passed XML parsing;
  `pyproject.toml` passed TOML parsing at version `0.2.0`; all Markdown code
  fences were balanced.
- A stale-contract search found no active documentation still claiming that
  TotalSegmentator/Bridge C was a future or unimplemented command.

### Drive synchronization

- Grounded the existing Drive folder `IITM Dentobot` with ID
  `1e7AWrEeVLctMKfWaBGiqv0Ck8p0AbFWh`.
- Created its `docs` child folder with ID
  `1M5uicX_Vkk2Y130p5k4rme1TjfavWJuO`.
- Uploaded all six `.md` files as raw Markdown and verified the child-folder
  inventory. Future updates must replace those file contents in place and
  preserve their Drive IDs.

### Files affected

- `docs/AGENTS.md`
- `docs/PROJECT_CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/changelog.md`
- `docs/logbook.md`
- Connected Google Drive folder `IITM Dentobot/docs`

### Limitations

- This update adds documentation mirroring, not automatic background
  synchronization. Sync occurs when explicitly requested through an agent
  session with the connected Drive available.
- Bridge C WSL tests, model inference, Slicer import/display, and scene
  round-trip verification remain pending from the previous entry.
- No implementation, installed Slicer file, environment, model, or patient
  artifact was changed or reverted.

## 2026-07-23 21:14:55 IST (UTC+05:30) — Bridge C GPU teeth segmentation source

### Added

- Bumped `dentobot-inference` from `0.1.0` to `0.2.0` and added the
  `segment-teeth` command.
- Added GPU-only TotalSegmentator `teeth` inference on CUDA device 0 with no
  CPU fallback.
- Added a cache-only runtime guard for both required open models:
  ToothFairy3 task 113 and craniofacial crop task 115. The guard requires
  dataset metadata, plans, and final checkpoint files and prevents
  TotalSegmentator's Python API from downloading weights during a Slicer run.
- Added schema-versioned success/failure JSON with model/package versions,
  input/output geometry, CUDA identity, inference/total runtime, peak allocated
  and reserved GPU memory, detected labels, per-label voxel counts and physical
  volumes, and actionable error codes.
- Added backend validation for three-dimensional geometry, affine/spacing,
  integer/nonnegative labels, known teeth label IDs, and nonempty foreground.
  Incomplete output NIfTI is removed after a failed run while `result.json` is
  retained.
- Added five backend tests covering metrics, unknown labels, missing input,
  complete offline model caches, and missing model caches.
- Added a **Run Teeth Segmentation (GPU)** workflow action. It exports the
  exact visible selected volume, reuses the asynchronous WSL adapter, validates
  the returned report, geometry, label IDs, and voxel counts, and only then
  imports the result.
- Added deterministic label names/colors, a persistent
  `vtkMRMLSegmentationNode` parameter reference, binary-labelmap and
  closed-surface representations, 2D/3D visibility, compact inference metrics,
  and `DENTOBOT.*` provenance attributes.

### Changed

- Renamed the reproducible Conda environment definition to `dentobot` and
  aligned it with the working Python 3.10 environment.
- Added the optional `segmentation` dependency extra for
  `TotalSegmentator>=2.11,<3`.
- Updated backend setup/runtime instructions and the governing architecture,
  roadmap, and agent state to describe Bridge C accurately.
- Recorded the developer's confirmation that the selector-authority fix made
  the real-CBCT Bridge B round trip work.

### Files affected

- `Inference/src/dentobot_inference/segmentation.py`
- `Inference/src/dentobot_inference/cli.py`
- `Inference/src/dentobot_inference/__init__.py`
- `Inference/tests/test_segmentation.py`
- `Inference/pyproject.toml`
- `Inference/environment.yml`
- `Inference/README.md`
- `DENTOWorkflow/DENTOWorkflow.py`
- `DENTOWorkflow/Resources/UI/DENTOWorkflow.ui`
- `docs/AGENTS.md`
- `docs/PROJECT_CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/changelog.md`
- `docs/logbook.md`

### Verification and limitations

- Static AST parsing passed for all ten relevant Python source/test files.
- The Qt Designer UI file parsed successfully as XML, and `pyproject.toml`
  parsed with version `0.2.0` and both optional extras.
- Backend tests could not be run from Windows base Python because that
  interpreter has neither `pytest` nor `nibabel`; no package was installed to
  alter it.
- WSL unit tests, TotalSegmentator installation, model downloads, real
  inference, Slicer-native tests, result import/display, and MRB scene
  persistence were not run by this change and must not yet be reported as
  passing.
- No installed Slicer file, Slicer embedded package, WSL environment, model
  cache, original DICOM file, registration, trajectory, robotics code, or ROS
  component was changed. No implementation was reverted.

## 2026-07-23 20:55:56 IST (UTC+05:30) — Visible volume selector made authoritative

### Corrected diagnosis

- The developer clarified that Slicer's visible **Selected volume** already
  showed the real CBCT, while Bridge B still used `SyntheticCBCT`.
- This supersedes the earlier assumption that the user had left the visible
  selector on the test node. It indicates divergence between the
  `qMRMLNodeComboBox` current node and the persisted parameter-node reference
  trusted by the click handler.

### Fixed

- Added an explicit `currentNodeChanged` handler that synchronizes the visible
  selector's exact MRML node ID into the parameter node.
- Made `onRunRoundTrip` read `inputVolumeSelector.currentNode()` directly,
  validate that it is a scalar volume, and synchronize persistence immediately
  before export.
- The **Bridge input** display now reads from the same selector source used by
  the click handler.
- The imported result name is now forced after load to
  `DENTOBOT_RoundTrip_<run-id>`, independent of file-reader naming behavior.

### Verification

- Static Python AST validation passed.
- All 20 Python UI references resolved against the parsed UI.
- A real-CBCT retry is required to verify the runtime fix. No installed Slicer
  file was modified.

## 2026-07-23 20:47:25 IST (UTC+05:30) — Bridge B synthetic round trip passed and source clarified

### Validation evidence

- The developer reports that Bridge B completed after the compressed-I/O fix,
  returned a volume to MRML, and displayed it in the Slicer slice viewer.
- The successful run used `SyntheticCBCT`, confirming the complete
  Slicer-export, Windows/WSL artifact, backend validation, process completion,
  Slicer-import, MRML geometry validation, and returned-node path for a small
  synthetic volume.

### UI correction

- The run used test data because DENTOWorkflow's persisted **Selected volume**
  still referenced `SyntheticCBCT`; loading another volume does not
  intentionally override an existing explicit selection.
- Added a **Bridge input** field beside the backend configuration. It mirrors
  the exact selected scalar volume that the round-trip button will export.
- Preparation and success status text now name that selected source volume.
  The user must explicitly choose the intended CBCT in the existing Selected
  volume selector before the real-data retry.

### Verification and pending work

- The changed Python passed static AST parsing.
- The UI parsed as valid XML, and all 19 Python UI references resolved.
- A real-CBCT Bridge B run remains pending. No automatic “latest volume”
  override was added because silent source replacement would be unsafe and
  surprising.

## 2026-07-23 20:40:34 IST (UTC+05:30) — Bridge B compressed-NIfTI performance fix

### Observed failure

- The first Slicer-originated Bridge B attempt remained at the backend's
  “Loading input NIfTI” progress event for more than three minutes.
- The implementation calculated a voxel checksum by repeatedly slicing a
  NiBabel proxy backed by compressed `.nii.gz`. On a large CBCT, random slice
  access may repeatedly decompress the same stream and make the checksum
  disproportionately slow.

### Changed

- The Slicer adapter now stages Bridge B input and output as uncompressed
  `.nii` files. NIfTI affine/geometry is retained while avoiding gzip
  random-access overhead across the Windows/WSL boundary.
- The backend now materializes an image proxy once before hashing it in
  bounded planes, so directly supplied compressed NIfTI is processed
  sequentially rather than decompressed for every plane.
- Added explicit input/output checksum progress events, and the Slicer panel
  now displays backend progress messages instead of remaining at “Starting
  WSL backend”.
- Slicer-native tests now clear their synthetic MRML nodes in a `finally`
  block, preventing the test-only `SyntheticCBCT` reference from remaining in
  the Returned volume field after a test run.
- Updated active backend and architecture documentation to show uncompressed
  staging artifacts. Compressed NIfTI remains supported by the backend CLI.

### Verification and pending work

- The changed Slicer and backend files passed static AST parsing.
- The developer must rerun the three WSL tests, reload DENTO Workflow, and
  retry Bridge B. Runtime performance and MRML import are not yet claimed as
  passing.
- The stalled run should be cancelled. No installed Slicer file was modified.

## 2026-07-23 20:31:54 IST (UTC+05:30) — Bridge A translation-name shadowing fix

### Fixed

- Renamed the unused staging-root local in
  `DENTOWorkflowWidget.onCheckBackend` from `_` to `_stagingRoot`.
- Assigning to `_` made it a local variable throughout the method and
  shadowed Slicer's imported translation function `_()`, producing
  `UnboundLocalError` before the WSL health process could start.

### Verification

- The module passed static Python AST parsing after the fix.
- An AST check confirmed that no assignment target named `_` remains in the
  module.
- Slicer-originated Bridge A must be retried after reloading the module. No WSL
  process reached launch during the failed attempt, and no installed Slicer
  file was modified.

## 2026-07-23 20:26:30 IST (UTC+05:30) — Slicer-native tests reported passing

### Validation evidence

- The developer reports that DENTOWorkflow's Slicer-native tests passed inside
  Slicer after the Bridge A/B implementation.
- These tests cover the existing scalar-volume logic plus bridge path mapping,
  argument-list construction, JSON extraction, geometry comparison, and
  parameter-node references without launching WSL.

### Remaining scope

- The WSL configuration values were initially pasted into Bash because the
  prior walkthrough did not state clearly enough that they are labels and
  values for the AI Backend Bridge panel inside DENTO Workflow.
- Bash produced syntax/command-not-found messages only; no environment or
  repository change resulted.
- Slicer-originated WSL health and the complete Bridge B round trip remain
  pending.

## 2026-07-23 20:20:29 IST (UTC+05:30) — Clean WSL backend validation

### Validation evidence

- The developer recreated the Conda environment under the retained name
  `dentobot` and installed the repository as editable with its test extra.
- All three standalone backend tests passed under WSL2 with Python 3.10.20:
  the health-contract test, successful NIfTI data/geometry round trip, and
  missing-input failure result.
- `health --json --require-cuda` returned schema status `ok`, using
  `/home/tarun/miniconda3/envs/dentobot/bin/python`.
- The health result reported one NVIDIA GeForce RTX 4060 Laptop GPU, CUDA
  available, PyTorch 2.10.0+cu130 with CUDA 13.0, NiBabel 5.4.2, and NumPy
  2.2.6.

### Scope and pending verification

- This establishes the standalone WSL backend and CUDA portion of Bridge A.
- The health process has not yet been launched from Slicer. Bridge B has not
  yet exported a Slicer MRML volume, crossed WSL, or imported and validated the
  returned MRML volume.
- TotalSegmentator is intentionally absent from the clean environment at this
  checkpoint and model inference remains unimplemented.
- No source behavior was reverted and no installed Slicer file was modified.

## 2026-07-23 17:05:09 IST (UTC+05:30) — Bridge A/B external inference boundary

### Added

- Added the standalone `Inference/` Python distribution
  `dentobot-inference`, with a minimal Conda environment template and no
  dependency on Slicer's Python.
- Added `health --json --require-cuda`, which reports the actual interpreter,
  core package versions, guarded PyTorch import health, CUDA availability,
  CUDA runtime, and device names without installing or downloading anything.
- Added `roundtrip`, which loads and rewrites a NIfTI image, validates shape,
  affine, voxel type, and a chunked SHA-256 voxel checksum, and always writes a
  schema-versioned JSON result for success or failure.
- Added backend unit tests for the health contract, geometry/data preservation,
  and missing-input failure.
- Added an AI Backend Bridge panel to `DENTOWorkflow` with parameter-bound WSL
  distribution, absolute environment-Python path, staging root, returned
  volume reference, health check, NIfTI round trip, cancellation, status, and
  bounded process output.
- Added a direct asynchronous `wsl.exe` adapter that uses separate arguments,
  a named distribution, and the exact Linux Python interpreter. It does not
  construct a shell command or activate Conda interactively.
- Added isolated run IDs/directories, Windows-to-WSL path conversion,
  NIfTI export, JSON/run-ID/schema validation, MRML import, source/output
  geometry comparison, and `DENTOBOT.*` provenance attributes.
- Extended Slicer-native tests for path conversion, command construction,
  JSON extraction, geometry mismatch rejection, and parameter-node
  persistence. These tests do not launch WSL.

### Changed

- Updated the project context to reflect the developer's existing
  WSL2/Conda/CUDA experience and current focus on Slicer-to-WSL orchestration.
- Updated the active architecture and roadmap to make Bridge A/B the explicit
  gate before TotalSegmentator integration.
- Renamed this file's active title/purpose from DentalNav to DENTOBOT while
  retaining older names in historical entries.

### Verification and limitations

- Static AST parsing passed for the Slicer module and every backend Python
  source/test file.
- The Qt Designer file parsed as valid XML, and all Python `self.ui` references
  resolved to named UI objects.
- Official Slicer 5.12 documentation confirmed that
  `launchConsoleProcess(..., blocking=False)` accepts line and completion
  callbacks with the signatures used by the adapter.
- The ordinary Windows Python available to this coding session lacked NumPy
  and NiBabel. The health command was executed from source and correctly
  returned structured status `error` with exit code 2 and both missing
  dependencies; no package was installed.
- Backend round-trip unit tests were not run because their declared
  dependencies were absent. Slicer, WSL, CUDA, and TotalSegmentator were not
  launched or tested, and no model was downloaded.
- Slicer-native tests, asynchronous callback compatibility, cancellation
  behavior, NIfTI geometry round trip, parameter persistence, and UI layout
  remain to be verified in Slicer 5.12.2 and the user's WSL environment.
- No existing behavior was reverted, no installed Slicer file was modified,
  and TotalSegmentator inference/segmentation import is not yet implemented.

## 2026-07-23 15:49:05 IST (UTC+05:30) — DENTOBOT rename and Step 0 workflow implementation

### Changed

- Renamed the CMake extension project and parent product identity from the
  earlier DentalNav/DentalDrillNav naming to `DENTOBOT`.
- Established `DENTO` plus PascalCase as the identifier convention for all new
  Slicer modules. Examples are `DENTOWorkflow`, `DENTOSegmentation`,
  `DENTORegistration`, and `DENTOTrajectory`.
- Updated the active agent instructions, project context, architecture, and
  development plan to use DENTOBOT naming. Historical entries retain old names
  so the rename remains traceable.
- Removed stale placeholder homepage, icon URL, and screenshot URL values from
  extension metadata instead of replacing them with invented public URLs.
- Changed the root extension build to include `DENTOWorkflow` and exclude the
  legacy `DentalNavPlanning` module.

### Added

- Added the `DENTOWorkflow` scripted module with:
  - a minimal DENTOBOT Step 0 UI;
  - a de-identified case-label field;
  - New Empty Case with explicit confirmation;
  - Open Saved Scene for MRML/MRB scenes;
  - Open DICOM Browser using Slicer's core DICOM module;
  - a parameter-bound scalar-volume selector;
  - automatic display in Slicer's slice views;
  - name, dimensions, spacing, scalar type/range, orientation, and geometry
    status;
  - typed MRML parameter-node persistence;
  - scene-close, module-exit, and cleanup observer handling.
- Added Slicer-native logic tests for missing input, missing image data,
  synthetic volume geometry/metadata, latest-volume selection, and parameter
  node references.
- Added `DENTOWorkflow/CMakeLists.txt` and
  `DENTOWorkflow/Resources/UI/DENTOWorkflow.ui`.

### Preserved or disabled

- The physical workspace directory retains its older name; it is not the
  product identity.
- `DentalNavPlanning` remains in the repository as disabled legacy history.
  Its threshold UI, sample-data behavior, and trajectory experiment are not
  included in the DENTOBOT extension build.
- Original DICOM files remain outside scene clearing and are never modified by
  New Empty Case.

### Verification

- `DENTOWorkflow.py` passed a static Python AST parse. It was not imported or
  executed with system Python.
- `DENTOWorkflow.ui` parsed as well-formed XML.
- All Python `self.ui` references were matched to named objects in the parsed
  UI, and both `SlicerParameterName` bindings were found.
- Root CMake registration was checked to include `DENTOWorkflow` and exclude
  `DentalNavPlanning`.

### Limitations and pending validation

- Slicer was not launched. The module, UI, DICOM browser handoff, MRML
  parameter persistence, scene round-trip, and Slicer-native tests remain
  unverified in Slicer 5.12.2.
- No real or sample DICOM data was loaded.
- No WSL, CUDA, TotalSegmentator, registration, trajectory, or robot behavior
  was added or run.
- No installed Slicer file was read or modified by this change.

## 2026-07-22 20:13:27 IST (UTC+05:30) — Direct WSL process architecture and raw records

### Changed

- Replaced the proposed file/job communication architecture with a directly
  controlled, asynchronous WSL process architecture.
- Defined Slicer as the lifecycle owner: it exports NIfTI, invokes an explicit
  WSL distribution and Linux Python interpreter through `wsl.exe`, streams
  structured stdout, handles cancellation and exit status, validates the
  result, and imports it into MRML.
- Retained an isolated per-run directory only for NIfTI payloads, logs, and
  reproducibility metadata. It is no longer described as a queue, watched
  directory, worker protocol, or process-control mechanism.
- Replaced the planned `segment --request <request.json>` entry point with
  explicit CLI arguments for input, output, device, result JSON, and run ID.
- Reserved persistent HTTP/RPC services for a future measured requirement,
  rather than making one part of the initial design.
- Added mandatory timestamped traceability rules to the agent instructions and
  documented the raw-record layer in project context and architecture.

### Added

- Added `docs/changelog.md` for material repository/specification changes.
- Added `docs/logbook.md` for ideas, prompt/request summaries, decisions,
  experiments, failures, fixes, reversions, and session history.

### Files affected

- `docs/AGENTS.md`
- `docs/PROJECT_CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/changelog.md`
- `docs/logbook.md`

### Preserved

- Slicer remains responsible for DICOM, MRML, visualization, interaction, and
  scene persistence.
- PyTorch, CUDA, and TotalSegmentator remain isolated in WSL2.
- NIfTI remains the geometry-preserving bulk image exchange format.
- JSON remains the reproducibility/result metadata format.
- No ROS dependency was introduced.

### Verification and limitations

- This was a documentation-only change. No Slicer, WSL, CUDA, model, or robot
  process was run.
- At `2026-07-22 20:19:48 IST (UTC+05:30)`, all six documentation files were
  checked for stale active-contract phrases and balanced Markdown code fences.
  Historical mentions of the superseded job design were intentionally kept in
  this changelog and the logbook.
- The same check found no non-document file modified after this documentation
  batch began.
- The actual process adapter and backend CLI do not yet exist and therefore
  remain unvalidated implementation plans.
- No application source, installed Slicer file, dependency, or model was
  changed by this update.

## 2026-07-22 19:57:35–19:57:42 IST (UTC+05:30) — Initial architecture and roadmap reset

The timestamps in this heading are derived from the saved file timestamps of
the four governing documents.

### Changed

- Reframed the product as a focused Slicer extension during workflow
  development, followed later by a supported custom Slicer application build.
- Defined Slicer, external inference, and robot-control responsibilities.
- Made a minimal DICOM workflow shell Step 0, ahead of segmentation and
  trajectory planning.
- Isolated inference in a standalone WSL2 package and deferred ROS to a later
  evidence-based robotics decision gate.
- Added explicit protection against editing installed Slicer or original DICOM
  data.

### Superseded detail

- This version proposed a NIfTI/JSON job-directory contract as the primary
  Slicer–WSL interface. The 20:13:27 entry replaced that control model with
  direct process invocation while retaining file artifacts for bulk data and
  provenance.

### Verification

- Documentation structure and code-fence balance were checked.
- No application code was changed in this reset.

## Through 2026-07-22 15:53:04 IST (UTC+05:30) — Retrospective earlier repository state

This entry was written at `2026-07-22 20:13:27 IST (UTC+05:30)` from the
repository and available conversation history. The heading uses the observed
trajectory-file timestamp only to place the reconstructed state in sequence.
The original scaffold-creation time and individual edit times were not
captured, so they must not be inferred from either timestamp.

### Pre-existing scaffold

- `DentalDrillNav` was created using the Slicer Extension Wizard template.
- `DentalNavPlanning` retained the generated threshold UI, sample-data
  registration, threshold logic, and threshold test.

### Exploratory trajectory change

- `DentalNavPlanning/DentalNavPlanning.py` was extended with a
  `trajectoryLine` parameter-node reference, trajectory-line creation logic,
  world-RAS Euclidean length calculation, and Slicer-native test coverage.
- The current file timestamp observed during reconstruction was
  `2026-07-22 15:53:04 IST`.
- The exploratory trajectory code was not removed, but the trajectory-first
  roadmap was superseded by the Step 0 workflow-shell plan.
- A passing in-Slicer result for the final exploratory code is not documented;
  it must therefore be treated as unverified.

### Runtime/dependency state

- No TotalSegmentator, PyTorch, CUDA, or WSL dependency is part of this
  repository at this point.
- Reported failures in the installed Slicer environment did not produce a
  repository dependency change.
# 2026-07-29 — Ubuntu documentation continuity established

- Restored the Windows-era product context, architecture, development plan,
  inference reproducibility procedure, and changelog into the active Ubuntu
  documentation hierarchy.
- Preserved the Windows session history as
  `docs/logbook/logbook-windows-history.md`.
- Added platform-transition notices without rewriting historical validation
  claims.
- Established active controls, continuous design documents, change history,
  platform history, and dated Ubuntu evidence as distinct document classes.
- Verified the Ubuntu container, ROS 2 Jazzy environment, SlicerROS2 install
  prefix, and running Slicer process.
- Deferred Git migration until the documentation and development workflow have
  been migrated.

## Verification

- Compared local history-file byte counts with their Drive source sizes. The
  local copies differ only by the final newline added during local restoration.
- Re-read the active controls and checked the imported document headings and
  transition markers.
- Listed the active Drive folder and logbook folder to ground every existing
  file ID before in-place synchronization.

## 2026-08-21 — External Step 6 ROS/MoveIt simulation repair

- Added a reproducible SlicerROS2 derivative image with OMPL, MoveIt config
  utilities, and xacro; added `dentobot_moveit_config` and launcher-owned stack.
- Replaced Slicer-side subprocess/ROS-CLI orchestration with a versioned
  readiness subscriber and explicit simulation-only state checks.
- Added the provisional spindle-axis TCP, KDL/OMPL plan-only configuration,
  conservative limits, 5 mm robot padding, and base-frame collision proxies.
- Routed ROS-active Step 6 planning to MoveIt Cartesian planning; routed Step 6
  manual joints and preview waypoints to the single joint-state simulation path;
  made preview fail on publish errors.
- Added ROS and embedded-Slicer smoke tests. Verified open-mouth phantom,
  forehead base snap, J2/J4 translations, TF, planning-scene publication, and a
  fraction-1.0 Cartesian plan. No hardware or trajectory execution was added.
- Added an external MoveIt PlanningScene command guard between Slicer joint
  candidates and the sole `/joint_states` source. It interpolates changes,
  checks URDF bounds plus exact FCL self/world collision and 5 mm distance, and
  restores the last accepted state on rejection. Added direct KDL `/compute_ik`
  and deliberate under-clearance tests; no hand-authored IK equations were
  introduced.
- Added the persistent top-header **Reload Module (Dev)** action for rapid
  source iteration without restarting Slicer or the container. The action
  preserves the MRML scene and external ROS stack, safely releases the
  Slicer-side robot/adapter nodes, evicts all DENTO helper modules, and invokes
  Slicer's scripted-module reload API.
- Fixed graphical startup under strict Bash mode by disabling `nounset` only
  while sourcing ROS-generated Jazzy/workspace setup files, then restoring it.
  Verified a live `DISPLAY=:0` launch into DENTOWorkflow with Slicer,
  collision guard, MoveIt, readiness node, and the sole simulated joint-state
  publisher all running.
- Made every normal GUI launch restart the dedicated DENTOBOT container before
  Compose reconciliation. This clears stale Slicer, ROS 2, MoveIt, and test
  processes while retaining the container filesystem; `--check-only` remains
  non-destructive. A seeded stale process was removed, the GUI stack reached
  ready state, 52 host tests passed, and the container was stopped afterward.
- Hardened warm Slicer lifecycle: clear/replace saved-scene loading, lazy Step 6
  ROS creation, synchronous Motion Control/robot teardown, process-owned
  default ROS singleton, exact stale-reference removal, no deferred MoveIt
  wrapper callbacks, transient ROS save graph, and fail-closed Step 4B/5C
  freshness checks. The real `test1_6_FD14.mrb` round trip preserved its
  15.760533814 mm trajectory and 29,962-point final template without restoring
  ROS runtime state.

## 2026-08-22 — Motion Control clarity and filtered TCP workspace

- Aligned the generic current and goal robot roots to the placed Step 6 base.
- Added a DENTOBOT runtime adapter that exposes detected MoveIt readiness,
  fixed `dentobot_arm`, provisional `dentobot_tool_tcp`, visible IK/plan
  feedback, and permanently unavailable trajectory execution.
- Added Step 6.3 deterministic six-axis Halton sampling, URDF FK, draft 5 mm
  AABB and provisional TCP/environment filtering, and a transient cyan
  base-parented workspace cloud.
- Excluded two documented persistent CAD-AABB false-positive pairs only from
  the coarse fallback; MoveIt/FCL remains authoritative.
- Extended host and real embedded-Slicer acceptance coverage. The real report
  verified open-mouth/forehead placement, manual joints, generic IK/Plan,
  Cartesian planning, and 116 accepted workspace points.

## 2026-08-24 — Shared robot façade and six-workspace application shell

- Created one integration branch for parallel Step 6 and GUI work; no duplicate
  workflow module or ROS workspace was introduced.
- Added a UI-independent Step 6 façade and routed Legacy robot actions through
  it. Added structured capability/action results and retained simulation-only
  MoveIt/KDL/FCL ownership.
- Added the opt-in six-workspace Slicer shell, light/dark themes, Focus/Expert
  mode, Legacy fallback, and Robot Simulation runtime/IK/collision task cards.
- Added host and real-Slicer tests. Recorded 81 host passes, application-shell
  PASS, module reload PASS, scene lifecycle PASS, and live façade IK/planning/
  collision evidence. The known post-PASS SlicerROS2 shutdown leak remains.

## 2026-08-29 — Unreleased partial Step 6 runtime/state-ownership redesign

- Began replacing implicit MoveIt planner state with an explicit immutable
  Task Home start vector and the exact returned PreEntry IK goal vector.
- Added source-level monitored `/joint_states` convergence evidence, equal
  start/goal rejection, planner input diagnostics, and containment preventing
  the optional Expert Diagnostics widget from becoming DENTOWorkflow command
  authority.
- Began moving ROS/MoveIt connection and exact collision-scene synchronization
  into 6.1, with live collision/monitor validation for 6.2 Task Home and
  optional backward-compatible persistent validation provenance.
- Added an unverified read-only MoveIt static-state validity API and began using
  it to filter 6.3 deterministic workspace candidates; updated Step 6 labels
  and gates toward the runtime-first order.
- **Status:** intentionally paused mid-implementation. Workspace runtime-key
  completion, Home-connectivity classification, planned Home application,
  remaining gate reconciliation, and all verification are pending. No build,
  parser, reload, ROS/MoveIt request, preview, or motion test was run for this
  increment.

## 2026-09-01 — Goal 1 PreEntry preview path

- Added a transient, display-only world-RAS TCP polyline for every accepted
  Step 6 phase plan. The line is generated from the same SlicerROS2 KDL FK
  chain and locked-base transform used by the robot preview, so it does not
  introduce a second coordinate conversion or alter the MoveIt collision
  scene. It is never serialized into `.dentocase` and is removed with the
  transient phase session.
- Added the path to the shared DENTOBOT View catalog and trajectory
  visibility/opacity controls; the Step 6 panel refreshes the catalog as soon
  as planning returns. The panel now explicitly describes the orange TCP path
  as planned waypoint evidence alongside the translucent goal robot.
- Extended the exact-case smoke gate to require one path model with at least
  two points and a line cell after Goal 1 planning. The clean ROS 2/MoveIt run
  passed: 55 strict Home-to-PreEntry waypoints, guarded preview complete, and
  the TCP path was present. The strict terminal segment remains truthfully
  deferred; Goal 2 remains blocked.
