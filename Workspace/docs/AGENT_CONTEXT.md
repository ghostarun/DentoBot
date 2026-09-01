# DENTOBOT compact agent context

Use this file as the low-context entrypoint for routine implementation. It is
a routing aid, not a replacement for controlled architecture, safety,
reproducibility, or dated evidence documents.

## Current engineering state — 2026-09-01

- Authoritative development checkout: `/home/light-tarun/dentobot/ros2_ws/src/DentoBot`.
- Active integration branch: `integration/gui-step6`.
- `DENTOWorkflow.py` is a thin public Slicer entrypoint. Production UI and
  logic live in `DENTOWorkflow/Resources/Python/dentobot_workflow/`.
- Legacy and six-workspace Shell presentations share the same MRML parameter
  node, logic classes, helpers, and `DENTORobotWorkflowFacade`.
- Step 6 is simulation/preview only. MoveIt provides configured IK, planning,
  FCL self/world collision, and planning-scene services. DENTOBOT does not
  expose controller/hardware execution.
- Priority-0 source work has passed its bounded compile/import gate and a
  clean-stack exact-case runtime milestone: Python/UI parsing, the SlicerROS2
  wrapper build, the collision-guard build, and direct DENTOWorkflow widget
  construction completed. The x4 case now reaches a guarded Home→PreEntry
  preview in 6.5; terminal Entry/Goal 2 remain unaccepted. The circular
  base-plane
  path is quarantined behind a reviewed Manual Simulation Base contract;
  collision surfaces are per-segment and require guard-side PlanningScene
  ID/bounds acknowledgement; partial Cartesian candidates persist with
  last-valid/first-invalid evidence and an in-app inspector; Goal 1 is split
  into free-space, strict-axis, and final contact stages. The headless widget
  printed PASS with ROS2 uninstantiated, but the Slicer debug process returned
  `1` at shutdown while reporting retained VTK objects; treat that as open
  lifecycle evidence, not an initialization failure or an accepted leak. Do
  not run tests or
  build verification without first explaining the proposed check and receiving
  explicit operator approval.
- The latest clean runtime retry proves restored local-robot reconstruction
  and Task Home seeding work and that the rebuilt collision guard receives the
  published meshes. The remaining 6.4 failure was traced to object identity:
  SlicerROS2 derives `CollisionObject.id` from the hidden MRML proxy name, but
  the proxy used a display-prefixed label while the audit expected the source
  ID. Source now names each transient proxy with the exact canonical audit ID,
  removes an obsolete published ID on resync, and bounds mismatch reporting.
  This correction is runtime-verified in the exact-case clean stack; a
  normal-window operator retry remains separate evidence.
- Current Step 6 motion policy uses a 2 mm new-case pre-entry standoff and
  1 mm research guard margin. Strict approach remains collision checked;
  terminal/drilling exploration may suppress only configured burr-to-task-
  anatomy/guide contact and must report it. All non-tool/self/bounds/session/
  corridor/backtrack/overshoot checks remain fail-closed.
- Goal 1 currently preflights complete Entry-to-Target reachability at 0.25 mm
  Cartesian sampling across bounded cylindrical-burr axial roll. The retained
  `dentobot-case-step6x4.dentocase` reaches only `44.44–45.34%`, but that
  percentage alone does not prove collision, kinematic reach, or a mechanical
  base-placement deficiency. The current API discards the partial trajectory,
  and the Step 6.1 plane/base snap is circular rather than a patient-contact to
  robot-mount transform. Preserve x4 as a negative diagnostic fixture; do not
  treat its partial result as a drilling plan or tune the planner to make it
  pass. When strict Home→PreEntry succeeds but the terminal axis segment is
  blocked, the API retains a truthful guarded PreEntry-only PhasePlan and
  records the deferred terminal fraction; it never promotes the partial path.
  The saved 2.0 mm burr versus 1.5 mm guide bore remains a separate
  upstream physical-fit defect.
- The active Priority-0 strategy is now: audit the exact anatomy meshes sent to
  MoveIt, add structured last-valid/first-invalid motion diagnosis, then expose
  an explicit three-stage simulation planner (strict free-space approach,
  strict axis approach to Entry with a narrow terminal contact tolerance, and
  guarded Entry-to-Target drilling). Persist diagnostic evidence, not live ROS
  objects, in `.dentocase`. Broad automated verification and new diagnostic
  scripts remain paused; the next verification loop is operator-visible and
  in-application.
- The recovered post-Priority-0 study roadmap is no longer a one-line Track F.
  First complete `MotionDiagnosticSessionV2` with explicit Stage 1/2/3/full-
  task outcomes and a V1 reader. Then F0 manually aggregates reviewed,
  source-referenced results in an evidence-only `.dentostudy`; F1 performs
  plan-only automation over eligible trajectories in the active case at one
  reviewed base; later cross-case accumulation follows; and F2 varies base
  poses only after Track E. `.dentocase` remains geometry/lineage/current-
  attempt authority, and study load creates no MRML or ROS runtime object.
- The accepted Step 6 ordering is runtime-first and is source-complete as of
  2026-08-31. Its focused static/package build gate passed, and the clean
  exact-case stack reached the guarded PreEntry milestone on 2026-09-01: both repositories
  passed `git diff --check`, five edited Python files passed `py_compile`, and
  the isolated `slicer_ros2_module` package rebuilt successfully. Normal-window
  ROS/MoveIt behavior remains unverified. After case preparation and Manual Simulation Base
  review, 6.1 connects ROS/MoveIt and acknowledges the exact collision scene.
  6.2 saves a live-valid Home or explicitly plans monitored-current-to-Home in
  MoveIt before applying every waypoint through the strict guard. 6.3 retains
  every accepted MoveIt-FK/static-valid TCP plus its joint vector and separately
  classifies a deterministic bounded 13-sample set as `HomeConnected` or
  `PlanRejected`; unevaluated static-valid samples remain explicit. 6.4 is
  confirmation only. The reviewed min/max proposal is an exploration envelope,
  not a collision-free box. Saved evidence requires explicit regeneration or
  revalidation after reconnect because live ROS validity is transient.
- The first approved exact-x4 remote runtime trial on 2026-08-31 proved case,
  jaw-opening, Manual Simulation Base, seven-link local-robot reconstruction,
  32-object collision-scene acknowledgement, and live Task Home validation.
  It first stopped at the first 6.3 sample because the bridge incorrectly
  required a draggable TCP goal for explicit state-validity/FK queries. After
  that source correction, the operator's manual retry entered workspace
  generation and rendered accepted samples, then native FK failed because it
  requested a live current-state `RobotState` merely as a model/container for
  an already explicit six-joint vector. Native explicit-state FK and
  explicit-start planning now construct their own state from MoveIt's robot
  model; Task Home application also retains an action-specific result and
  displays explicit success confirmation. A follow-up ownership audit found
  that one shared card still exposed Connect/Disconnect in both 6.1 and 6.4,
  placed collision repair in 6.4, and reused one label for runtime and task
  confirmation. Source now splits 6.1 runtime/audit from confirmation-only
  6.4, disables the retired XML runtime controls, and rejects shared-panel
  actions outside their declared substep. `DEVELOPMENT_PLAN.md` contains the
  authoritative locked 6.0–6.6 ownership/progress ledger. These native/UI
  changes passed the approved isolated `slicer_ros2_module` rebuild,
  four-module `py_compile`, and both repository `git diff --check`; operator
  runtime verification was still pending at that earlier checkpoint; the
  later exact-case run reached 6.5 and accepted the PreEntry preview.
- A restored fresh Task Home is now the 6.1 transient bootstrap vector, not an
  incidental visible/default ROS pose; this prevents grey MRML/cyan ROS drift
  on first Connect but never restores live validity, so 6.2 remains mandatory.
  J2 now uses an extended/home zero and J5 is continuous in the URDF. Exact
  former-profile packages migrate by `q_new=0.08 m-q_old`, canonicalize J5 to
  its shortest representation, retain physical pose/base, and invalidate
  runtime, workspace and later evidence for explicit 6.2/6.3 regeneration.
  This source increment was built and exercised by the clean exact-case runtime;
  migration remains subject to normal-window operator confirmation.
- A subsequent clean-stack run completed the runtime-first gates through
  immutable confirmation in 6.4, then reached Goal 1. MoveIt found a
  collision-aware PreEntry IK endpoint (visible as the translucent robot) but
  strict explicit-start OMPL returned an empty trajectory after the old three
  identical attempts. The old message reported a raw `6.25726 rad` maximum
  Home-to-goal delta without naming its joint or a collision pair. Current
  source treats J5 and the spindle as continuous, evaluates all eight
  direct axial-roll IK branches, then tries bounded two-leg routes through at
  most three saved 6.3 samples already proven static-valid and Home-connected.
  Both legs are replanned in the current scene. V2 diagnostics retain explicit
  stage/full-task outcomes and direct/detour collision evidence while reading
  V1 records without changing their fingerprint. Collision margins and anatomy
  policy were not relaxed. The focused retry accepted 55 strict Home→PreEntry
  waypoints and a guarded preview; the terminal segment remains explicitly
  deferred.
- Saved current-profile 6.3 evidence now has an explicit live-revalidation
  action: after 6.1 Connect and 6.2 Home validation it replays every retained
  state/FK and the formerly evaluated Home-connectivity subset, preserves the
  reviewed limits, and requires fresh 6.4 confirmation. A mismatch requires
  regeneration; no live-valid key is restored from package JSON.
- Source CBCT geometry remains authoritative and unchanged. Volume rendering
  is display-only, not a segmentation surface or collision mesh.
- Step 6 uses seven shared one-card substeps in both presentations. A current
  Steps 0–5 package remains active when the post-import 6.0A jaw opening is
  missing; a reviewed pre-opening base restores as atomically unlocked
  `Stale`, never as a circular package/import lockout.
- `.dentocase` hydration is atomic, but continuation is modular: every Legacy
  stage and all six application workspaces stay selectable after restore;
  stage-local prerequisites gate actions, not navigation.
- High-priority Step 6A order is: retain the now-correct patient-RAS TMJ
  laterality (`Left X < Right X`) and inferior opening direction (`delta Z <
  0`), add source-fingerprinted left/right
  condylar and crown/incisal candidate surfaces plus enforced MPR review and
  contralateral guide, verify them on a representative case, then implement
  the transient realtime gap preview.
  Slider motion is display-only; `Lock / Accept Opening` alone commits the
  persistent transform/derived geometry, while MoveIt objects wait for
  explicit Connect/Sync.
- The Priority-0 Step 6 Viewer defect is code-fixed and exact-package verified:
  the current x1 package is explicitly reviewed/opened, Recommended shows 31
  derived upper/lower jaw-and-teeth segments, suppresses all 54 source
  closed-pose segments, and deferred tree refresh survives repeated real-item
  toggles. Restored placement flags are canceled because they are transient.
  Normal-window operator confirmation is still requested.
- The strongest automated evidence in this checkpoint is host-static or
  synthetic Slicer. It is not anatomical, clinical, registration, metrology,
  physical-fit, or hardware-safety evidence.

## Reusable documentation-and-Git keyword

When the operator sends `DENTO-POSTMORTEM-SYNC`, reconcile current
implementation evidence into the controlled changelog, development plan, and
dated logbook, then perform the requested Git diff-check, commit, and push for
that documentation checkpoint. The generated summary is generic and
evidence-based: what changed, why, what was superseded, verification,
limitations, and the next bounded work. Do not update Google Drive, the
personal journal/Daily Compass, or `TASKS.md`/the project tracker unless the
operator separately approves each destination. Drive synchronization always
requires explicit approval. Preserve unrelated dirty-worktree files and
never include credentials, patient identifiers, or transient ROS/runtime
objects in the summary.

## Read routing

For a routine, narrowly scoped code change, read:

1. this file;
2. today's `Workspace/docs/logbook/YYYY-MM-DD.md` entry;
3. `dentobot_workflow/README.md`; and
4. only the domain files identified by its routing table.

Also read the controlled file matching the change:

| Change scope | Additional controlled source |
|---|---|
| Architecture, state boundary, module ownership | `ARCHITECTURE.md`, `DECISIONS.md` |
| Environment, launcher, paths, dependencies | `SETUP.md` |
| Milestone priority or acceptance status | `DEVELOPMENT_PLAN.md`, `TASKS.md` |
| Persistence, evidence, hashes, releases | `REPRODUCIBILITY_AND_TRACEABILITY.md` |
| Resume/reconcile/mental-model work | `DENTOBOT_Daily_Compass.docx` plus `CONTEXT_SYNC.md` |
| Documentation checkpoint or release | all controlled files required by `Workspace/AGENTS.md` |

Do not reread every historical logbook or the 7k-line Slicer regression archive
for a routine local change. Search by method, MRML role, stage, or error first.

## Non-negotiable contracts

- Work only within the user-authorized milestone.
- No robot motion, drilling, patient-facing action, or safety-critical command
  without explicit authorization and a verified safety procedure.
- Preserve world RAS millimetres in Slicer, centralized ROS frame/unit
  conversion, source volume geometry, transform direction, and provenance.
- MRML nodes and the typed parameter node are authoritative. QSettings stores
  workstation presentation only; no duplicate case-state database.
- Keep hardware safety and real-time control outside Slicer.
- Never record credentials, patient identifiers, or non-anonymized medical data.
- Record exact verification before claiming success. State evidence level and
  unresolved failures explicitly.
- Preserve unrelated dirty-worktree changes and concurrent work.

## Modular workflow rules

- Public API: `DENTOWorkflow/DENTOWorkflow.py`.
- Domain implementation: `dentobot_workflow/` package and its README map.
- Stable shared helpers: top-level `DENTO*.py` files.
- Robot UI boundary: `DENTORobotWorkflowFacade.py`.
- Context budget: routine domain files at or below 1,500 lines; split by
  cohesive behavior rather than copying the full widget or logic class.
- Domain modules use direct Python inheritance. They add no IPC, serialization,
  worker, network, or secondary state boundary.
- Preserve public method signatures and use the API manifest/static ownership
  test to prevent duplicates.
- The Reload button must reload both helper and internal package modules; use
  the five-cycle Slicer smoke after lifecycle/reload changes.

## Fast verification

```bash
cd /home/light-tarun/dentobot/ros2_ws/src/DentoBot
pytest -q Testing
git diff --check
```

Use the focused `Testing/run_dentobot_*_smoke.py` matching the domain. Slicer,
ROS, and MoveIt checks must run in the pinned container and remain
simulation-only. Full inference tests require the configured inference
environment; a host `pytest` collection failure for missing `nibabel` or the
package path is an environment mismatch, not a substitute for those tests.

## Known active issue

The non-ROS application shell, composable viewer, Step 6 case view, and five
consecutive developer reloads pass after modularization. A separate Track 1
SlicerROS2 lifecycle smoke still aborts native Slicer when `mrmlScene.Clear(0)`
follows a live robot reconnect; the external simulation stack precondition and
all earlier reconnect steps pass. Treat this as an active native ROS scene-
lifecycle defect. Do not claim warm active-ROS New Case/save-reopen acceptance
until it is isolated and verified.
