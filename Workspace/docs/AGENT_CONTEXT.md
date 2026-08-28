# DENTOBOT compact agent context

Use this file as the low-context entrypoint for routine implementation. It is
a routing aid, not a replacement for controlled architecture, safety,
reproducibility, or dated evidence documents.

## Current engineering state — 2026-08-28

- Authoritative development checkout: `/home/light-tarun/dentobot/ros2_ws/src/DentoBot`.
- Active integration branch: `integration/gui-step6`.
- `DENTOWorkflow.py` is a thin public Slicer entrypoint. Production UI and
  logic live in `DENTOWorkflow/Resources/Python/dentobot_workflow/`.
- Legacy and six-workspace Shell presentations share the same MRML parameter
  node, logic classes, helpers, and `DENTORobotWorkflowFacade`.
- Step 6 is simulation/preview only. MoveIt provides configured IK, planning,
  FCL self/world collision, and planning-scene services. DENTOBOT does not
  expose controller/hardware execution.
- Current Step 6 motion policy uses a 2 mm new-case pre-entry standoff and
  1 mm research guard margin. Strict approach remains collision checked;
  terminal/drilling exploration may suppress only configured burr-to-task-
  anatomy/guide contact and must report it. All non-tool/self/bounds/session/
  corridor/backtrack/overshoot checks remain fail-closed.
- Goal 1 now preflights complete Entry-to-Target reachability at 0.25 mm
  Cartesian sampling across bounded cylindrical-burr axial roll. The retained
  `dentobot-case-step6x4.dentocase` reaches only `44.44–45.34%`; its current
  base must be repositioned. Never treat that partial result as a drilling
  plan. The saved 2.0 mm burr versus 1.5 mm guide bore is a separate upstream
  physical-fit defect.
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
