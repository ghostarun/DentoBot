# Main development station migration — 30 September 2026

Owner: `PLAT-U-07` (Unprioritized), extending the existing multi-workstation
source/case exchange contract. Status: evidence-backed plan; migration and
destination runtime acceptance are not executed. backlog.md is the sole queue.

## Outcome and authority

Move primary development from Ubuntu 24.04 at
`/home/light-tarun/dentobot` to this Ubuntu 22.04.5 station at
`/home/tarun/dentobot`, preserving source, native dependencies, selected case
identities, engineering decisions and acceptance boundaries. The operator says
a **verified project-context handoff is sufficient**; original Codex chat
history migration is unnecessary.

This turn authorizes remote Git inspection and a detailed plan. It does not
authorize switching the active checkout, installing dependencies, rebuilding,
starting Slicer/ROS, transferring data, publishing Git, or enabling Drive
services. Preserve engineer-owned records without accessing or migrating them.
The source station remains primary until explicit cutover acceptance.

## Verified Git picture

Both repositories were fetched on 30 September. Dates below are commit dates;
they do not prove there is no newer uncommitted work on the source station.

| Reference | Tip | Date | Meaning for migration |
|---|---|---|---|
| Destination `main` | `0cc70f2` | Sep 18 | Clean tracked/untracked checkout before this plan; stale context checkpoint |
| `origin/main` | `001868f` | Sep 18 | Two commits ahead; pressure-tool/Drive work, not the latest workflow |
| `origin/cursor-agent/dentoworkflow-debug-20260918` | `b79161d` | Sep 22 | Earlier workflow/jaw recovery checkpoint |
| `origin/feature/step6-workflow-renovation-20260925` | `6b0d573` | Sep 25 | Recommended development lane, pending source-station confirmation |
| `origin/upgrade/slicerros2-5.12-performance` | `1f072d6` | Sep 25 | Separate candidate upgrade; retain isolation |
| `origin/codex/campaign1-checkpoint-b94a201` | `48c0c82` | Sep 15 | Historical diagnostic checkpoint, not current workflow authority |

Renovation is 30 commits ahead of remote main and 32 ahead of destination
HEAD. The upgrade and renovation branches share `fba15d8`: upgrade has two
branch-only documentation commits; renovation has one empty kickoff commit.
`6b0d573` changes no files. The latest committed workflow implementation and
evidence are therefore in `fba15d8`, not a completed renovation feature.
The destination-to-renovation diff spans 195 files; a pull of main cannot
substitute for selecting the intended development branch.

Full identities:

```text
destination: 0cc70f2eacac4995db5f59f94138cd778468a2ff
remote main: 001868f0177e9845e44bb80ac2d806c1d1891f84
renovation:  6b0d57313eebaed0e84605a609c5813b1ff3aadb
upgrade:     1f072d61283aac5772e99fba72b9c236ec2627b3
common:      fba15d8ec6543d25dfa0728f09e149ff7814e046
```

Important history: Sep 18–19 introduced AUTO jaw opening, virtual-forehead
simulation seating, Step 3B placement and normal-window acceptance records;
Sep 22–23 added planner diagnostics, explicit planner selection, RRT/RRT*,
exact profile compatibility and clearer configured-versus-executed identity;
Sep 24–25 checkpointed FDI11 case recovery, PreEntry IK evidence,
responsiveness instrumentation and the workflow-first renovation plan.
Older platform/Cursor branches are historical routes, not merge targets.

## Blocking identity gaps and destination observations

1. The other station's current branch, dirty files, worktrees and work after
   Sep 25 are unknown. GitHub is only the published checkpoint.
2. Destination SlicerROS2 is clean and detached at
   `17f99931f54f1e7941d7a66b30a849d2a37baccd`. Its fetched remote still has
   this DentoBot fork checkpoint. The Sep-25 upgrade document describes a
   later `49492e0` TCP-FK commit plus four uncommitted native IK files. Those
   source-station changes are not available from the inspected fork refs.
   New DentoBot Python with this older native library is not a reproducible
   installation. Capture the exact fork revision AND dirty source before build.
3. The top-level dentobot folder is an overlay, not the Git checkout. The
   checkout is `ros2_ws/src/DentoBot`; docs/scripts/AGENTS are symlinks.
   The Codex project currently points to the overlay and reports
   `isGitRepository=false`. Git-aware app features need a separately registered
   project rooted at the actual checkout; launchers still need the overlay.
4. Existing data, Slicer home, ROS build/install/log trees and a local NVIDIA
   Compose override are present. None is proven compatible with the new source.
   The filesystem had about 23 GiB free. Size the chosen images, native build,
   rollback copy and selected payloads before allocating them.
5. `/dev/dri` and `/dev/nvidia0` were not visible to this execution context.
   This is not a host GPU inventory or grounds for changing the driver/profile.
   Establish actual display/GPU/device access in the approved preflight.
6. Host Ubuntu differs. The accepted container remains Slicer 5.10 with
   Ubuntu/Jazzy runtime dependencies; do not transplant Ubuntu 24.04 host
   packages onto 22.04 or copy host-bound native install trees as validation.

## Phase 1 — freeze and capture the source station

Finish or pause its current agent turn, record any owned running processes,
and save operator scene changes through the ordinary case serializer to a
separately named approved bundle. Never kill an operator-owned process or
infer that its live scene matches an old on-disk package. Stop writers and
record an agreed handoff cutoff before collecting checksums.

Read-only Git inventory on the source, separately in **both** repositories:

```bash
git -C /home/light-tarun/dentobot/ros2_ws/src/DentoBot status --short --branch
git -C /home/light-tarun/dentobot/ros2_ws/src/DentoBot rev-parse HEAD
git -C /home/light-tarun/dentobot/ros2_ws/src/DentoBot worktree list
git -C /home/light-tarun/dentobot/ros2_ws/src/DentoBot log -12 --oneline --decorate
git -C /home/light-tarun/dentobot/ros2_ws/src/slicer_ros2_module status --short --branch
git -C /home/light-tarun/dentobot/ros2_ws/src/slicer_ros2_module rev-parse HEAD
git -C /home/light-tarun/dentobot/ros2_ws/src/slicer_ros2_module worktree list
```

Review scoped staged/unstaged diffs and list untracked paths. Inventory approved
ignored code/config inputs separately; status alone misses them. Exclude
engineer-owned artifacts, credentials and medical payloads from inspection and
source archives. Preserve unfinished code with an allowlisted local Git
checkpoint or Git bundle plus binary patches and explicitly listed untracked
files; a patch alone loses untracked files. A bundle alone loses dirty files.
Git publication needs its own authorization; do not use blanket `git add -A`.
Include all relevant worktrees/branches, not only the primary checkout.

Capture the actual running container image ID/digest, labels, Slicer/ROS
versions, loaded native-library/build identity, bind mounts, dependency locks
and model-cache manifest. Determine whether the native solver exists only in
the running container or source build. If mutable-container changes are
essential, document their reproducible source recipe; an image tag alone does
not capture them. Retain the working image as rollback pending reconstruction.

**Gate:** both source repositories and local-only implementation are accounted
for, source cutoff is fixed, and the exact target commit is agreed. Any newer
source work updates this plan; never silently overwrite it with `6b0d573`.

## Phase 2 — produce the compact context handoff

Have the source-station Codex coordinator create a development-controlled
handoff tied to the captured revisions, with these fields:

| Field | Required content |
|---|---|
| Identity | Both repo SHAs, branch/worktrees, dirty-patch hashes, runtime image/build identities, cutoff time |
| Current intent | Latest direct operator direction, superseded plans, task IDs and dependency order |
| Implementation | Exact owned files, completed source slices, unfinished work and relevant API changes |
| Evidence | Case/run IDs and hashes, commands/results, evidence level, shutdown/cleanup outcome |
| Open gates | First failure, retry counts, operator verdicts and source/runtime/physical acceptance still open |
| Authority | Approved scope and resource boundaries; proposed destination verification is separate |
| Continuation | One bounded next action, stopping condition and links into canonical records |

Validate each assertion against committed docs and the captured dirty state.
Unspoken operator reasoning remains unknown. No broad historical audit or
repeat investigation is needed. Keep pending work exclusively in backlog.md;
the handoff points to it and does not become another queue.

The published branch currently routes to
`diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md` before
case-specific planner solving, with existing `S6-WORKSPACE-PURPOSE`,
`S6-LIVE-01`, `S6-LIVE-03/04` and `S6-P2-03` owners. The canonical FDI31
M0–M4 contract remains open. Campaign-1 r4/P3/P4/P5 is historical diagnostic
evidence, not the next execution route. The changed-base/Home FDI11 IK-only
report does not close the original saved all-zero-Home failure; its distinct
changed-state package and operator verdict remain open. Preserve these limits.

**Gate:** a fresh chat can identify current intent, exact code/case identities,
first unaccepted result and the next bounded action without relying on memory.

## Phase 3 — preserve destination and select source safely

Keep this station's current checkout, overlay configuration and existing data
recoverable. This planning turn creates local documentation changes; migrate
them explicitly rather than letting a checkout switch overwrite them. Capture
their allowlisted patch/files, or make a local checkpoint when authorized.
Record destination `0cc70f2` and existing native `17f9993` before changes.

Prefer a separate checkout/overlay for staging if measured disk capacity allows
it. A detached review worktree is useful for source comparison but the bootstrap
requires the canonical `overlay/ros2_ws/src/DentoBot` layout; it is not by itself
a runnable environment. Do not silently move the active project's symlinks.
If staging in the current overlay is necessary, checkpoint local changes and
keep old build/install/image identities recoverable before a branch switch.

After exact source capture, create a local tracking branch from the agreed
renovation ref (or its newer captured continuation). Do not merge feature work
into main merely to migrate. Preserve upgrade as its sibling lane, with the
accepted 5.10 runtime. The lab updater follows the lab release and may detach
the checkout; it is not the development migration procedure.

Apply this plan's `PLAT-U-07` additions to the **newer** controlled records in
place. Never copy this station's whole Sept-17 backlog/TASKS/DECISIONS over the
Sept-25 versions: that would reopen completed work and restore obsolete order.

**Gate:** exact source and native changes are materialized, work is preserved,
controlled records remain current, and both old/new identities are recorded.

## Phase 4 — reconstruct the local environment and selected data

Use the selected branch's bootstrap and setup after reviewing side effects.
Recreate `.dentobot.env` from its example and explicitly map:

| Source | Destination | Interpretation |
|---|---|---|
| `/home/light-tarun/dentobot` | `/home/tarun/dentobot` | Host overlay root |
| `.../ros2_ws/src/DentoBot` | Same relative layout | Development Git checkout |
| `.../ros2_ws/src/slicer_ros2_module` | Same relative layout | Independent native Git checkout |
| `/workspace` | `/workspace` | Preserve container coordinate/path contract |
| Backend interpreter/cache/render device | Destination-specific | Verify; no global search/replace |

Rebuild or install inference from checked-in CPU/CUDA pins according to the
destination's verified device profile. Never copy a Conda/venv wholesale across
home paths or install inference into Slicer's embedded Python. Capture required
TotalSegmentator task/cache identities; acquisition is separate from launch.
Review local Compose override, UID/GID, GPU/render access, X11/display, RAM/PID
limits and mount paths. Do not retain an old NVIDIA override by assumption.
Inspect timer/service and auto-start definitions by name without exposing
credential contents; explicitly decide which belong here before activation.

Rebuild the captured native fork incrementally in the destination runtime when
its compiled inputs differ. ROS install/build products embed paths/ABI/runtime
assumptions and are not the source handoff. Source Jazzy and workspace setup
in the correct container; historical `librclcpp.so` startup failures are not
permission for another expensive startup loop. Verify Python is loading the
intended module and native library before application acceptance.

Transfer only individually selected synthetic or explicitly approved
de-identified `.dentocase` bundles, preserving relative layout and SHA-256.
Select the active Sep-22/Sep-24 baseline and any separately saved changed-state
setup from the source manifest; an older Drive pilot is not automatically
current. Do not enumerate, open or transfer patient-identifying payloads.
Standalone raw volumes, MRBs/STLs, screenshots and run trees remain outside
this contract unless separately authorized. Preserve their authoritative
source-station copies and identify missing evidence as missing. Git-tracked
controlled evidence stays with source. Open copied cases offline initially;
saved Home/workspace/guard validity never establishes a live runtime state.

Optional existing upload services are documented on newer branches, but this
migration does not enable them, run bulk upload or copy rclone/auth secrets.
Audit their narrower/later authorization against the current explicit rules;
do not treat a script's existence as authority. Preserve existing Drive IDs.

**Gate:** source/native/image/config identities match the captured manifest,
selected case bytes match, storage is sufficient and auto-start surprises are
resolved. Environment setup is not yet runtime acceptance.

## Phase 5 — start Codex here with verified context

Register the actual checkout for Git-aware app work while retaining the overlay
for launchers. Confirm CWD, trusted roots and accessible parent overlay before
any action. Review user/project config, skills, plugins and permissions with
secret values excluded; reauthenticate locally through normal UI when needed.
Do not copy the whole `~/.codex`, auth files, opaque session databases, machine
trust/approval rules or old absolute paths. Reinstall required plugins/skills
through supported mechanisms and inspect missing capabilities explicitly.

Destination user defaults currently say `gpt-6.1-sol` / `medium`. The current
operator-supplied instructions prefer 5.6 Sol; fetched Sep-23 general rules say
GPT-6 Sol Low / optional Luna xhigh, and Sep-25 Step-6 task-specific rules say
Sol Medium / up to two Luna Max workers. Record this policy conflict and follow
current instruction hierarchy and explicit task scope. Do not switch models or
spawn workers for this migration plan; Markdown cannot change this running
model. No imported approval history widens destination runtime scope.

Suggested first prompt after materialization:

> Continue the verified workstation handoff under PLAT-U-07. This station uses
> /home/tarun/dentobot; Git lives at ros2_ws/src/DentoBot. First read all of the
> current backlog, AGENTS, AGENT_CONTEXT and the revision-bound source handoff;
> follow matching IDs into TASKS, DEVELOPMENT_PLAN, DECISIONS and dated evidence.
> Compare actual DentoBot/native SHAs and dirty hashes with the manifest. Report
> conflicts, missing cases/native APIs, open verdicts and retry counts. Use the
> current workflow-first renovation order; do not resume Campaign 1 or change
> geometry/planner policy. Propose the cheapest destination verification gate,
> with no runtime until its scope is approved. Engineer-owned records are
> excluded. Use a fresh chat; original transcript migration is unnecessary.

Official Codex docs distinguish user/project configuration and project trust.
CLI `codex resume` resumes an available saved session and allows explicit CWD
selection; it does not establish a cross-machine migration procedure. This
plan uses a fresh chat plus repository evidence, so session import is not a
dependency. Managed worktrees do not generally materialize all ignored local
setup; keep the environment manifest explicit.

Sources: [configuration](https://learn.chatgpt.com/docs/config-file/config-basic),
[resume](https://learn.chatgpt.com/docs/developer-commands?surface=cli),
[worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees).

## Phase 6 — staged verification and primary-station cutover

Select from the **materialized checkout's** `Testing/verification_matrix.json`,
following `AGENTIC_VERIFICATION_PROTOCOL.md`. No check/build/runtime is run
by this plan. Present exact commands, inputs, expected discriminator, approval
class, resources, evidence and stopping condition before execution.

1. Level 0 identity inspection: both Git states, patch hashes, links/mounts,
   available native API/source/build identity, image digest, lock/cache and
   case hashes. Resolve this before starting Slicer.
2. Separately approved launcher `--check-only`/backend health and focused
   static/pure checks: `static.git_diff_check`, `static.step6_pycompile` and
   `pure.step6_restore` where applicable. Native package build only if its
   compiled inputs changed; no full-stack rebuild by default.
3. One explicitly approved serialized offline load/save-to-new-copy/reopen
   check, chosen from `runtime.step6_restore` or the applicable case gate.
   Preserve package lineage; no ROS auto-connect or planner on load.
4. If needed and explicitly approved, one ROS/native capability check with
   exact process ownership, image/source/build identity, domain 73 and scoped
   cleanup. Do not invoke the old P-series/planner harness as an install test.
5. Operator normal-window verdict on copied case, displayed anatomy/robot/base,
   status and save/reopen. Separate functional PASS from nonzero teardown.
   Migration acceptance does not close planner/full-cycle/physical milestones.

Use `/tmp/dentobot-verification/<run-id>/` for logs/result JSON; retain accepted
identity and compact evidence in the controlled logbook. Honor the three-failure
ceiling, earliest causal-error stop and early visual escalation. Runtime
resources are exclusive. Do not replace an existing operator-owned scene or
process. Hardware, powered spindle and patient-facing work remain prohibited.

Cutover requires: complete source/context capture, destination source/native/
runtime parity, selected case checksums, approved scoped checks, operator GUI
verdict and an explicit primary-writer change. At cutover update SETUP,
CONTEXT_SYNC authority paths and related controlled records to the destination,
keeping source paths in dated evidence. Disable duplicate source automation
only within explicit authorization and retain the old station as rollback.
Subsequent development uses one primary writer; secondary work is on explicit
branches with reconciliation before merge.

Rollback: pause destination writes/runtime, preserve its new work, and continue
at the intact source checkpoint with its captured working image/native build.
Never force-reset either station, rewrite cases or overwrite newer controlled
records to achieve rollback. PLAT-U-07 remains open until migration acceptance
and its distinct existing exchange obligations are resolved; a completed plan
is not a completed migration.
