# DENTOBOT Tasks

## 8 October — `PLAT-U-07` Goal 2: A-orchestrated visible B Slicer runtime (open)

**Operator clarification (Tarun, 8 October, confirmed "yes" to Claude's
summary):** the original request had two goals. Goal 1, a sequential A→B→A
handoff by Git with destination-hosted T3 threads, is the completed subgate
below. Goal 2 was never built: while A is on, the orchestrating agent thread
stays on A and only headed Slicer GUI testing runs on B, visible on B's GNOME
desktop (operator watches through Remmina RDP of B), with results returned to
A so A's development continues without its screen being taken over. Operator
wording (7 October): "just perform slicer GUI testing on system B while agent
runs in system A".

**Gap evidence:** every B runtime so far was started by a B-hosted thread; the
only remote command, `ssh dentobot-b 'dentobot smoke --run'`, uses private
Xvfb. T3 Device hub/Device hosts manage iOS Simulators/Android Emulators only
(`device_list`/`device_open` contract), so they cannot stream a Linux Slicer
window. A Claude B-local headed fixture run at `ab6953e` passed its test logic
(six stages, save/reopen) but its ffmpeg `x11grab` of rootless Xwayland `:0`
recorded black frames, so on-screen visibility is unproven; it does not count
as Goal 2 evidence.

**Contract (design pending; not yet implemented):**

- Outcome: from an A-hosted thread, one command or dispatched B turn runs a
  pinned-SHA headed Slicer session on B's GNOME `:0`, visible in Remmina, and
  returns verdict JSON, screenshots and logs to A.
- Candidate building blocks: existing `dentobot launch`/smoke/fixture harness
  over SSH; Slicer 5.10 built-in WebServer module (present in image
  `33a9e1e`) bound to container localhost and reached from A only through an
  SSH tunnel, for screenshots and driven steps; native T3 `thread.turn.start`
  to a B-hosted thread as the alternative dispatch route.
- Invariants: B runs only an origin-published SHA that A names; parity check
  first; serialized runtime ownership and existing cleanup checks; scoped
  `xhost` grant revoked afterwards; no MoveIt motion or hardware; WebServer
  exec never exposed beyond loopback/SSH.
- Acceptance: operator sees the B Slicer window in Remmina during an
  A-initiated run, and A receives the PASS/FAIL result plus screenshots without
  A's display being used. Screen evidence must come from a Wayland-capable
  capture or Slicer's own screenshots, not `x11grab` of `:0`.

**Prototype status (8 October, A-hosted Claude):** the SSH dispatch route is
prototyped outside the repo in `~/dentobot/tmp/b-visible-case/`
(`request-from-a.sh` → B `run.py --sha` → rsync back to A). Three
A-initiated runs at `ab6953e` passed 13/13 checks with byte-identical
screenshots. The operator confirmed in Remmina that he saw runs `225200Z` and
`230920Z`; `230525Z` was not watched. The acceptance behaviour has been
observed with the prototype only. It is not in the repo and Goal 2 stays open
until it is productized.

**Operator decisions (Tarun, 8 October ~05:00 IST):**

1. Completion notice uses (a) and (c):
   - (a) The A agent runs `request-from-a.sh` as a background job and keeps
     developing. It is notified when the job exits, and by then the evidence
     is already on A.
   - (c) B also writes the result folder plus a done marker under
     `data/dentobot-runs/`, so A can collect it later if it went offline
     mid-run.
2. Every handoff names the agent explicitly. The initiating agent runs
   `handoff-thread.py --list` on the target host and presents Tarun the
   options:
   - Agent: Codex (`gpt-6-sol`, effort `low`, the AGENTS.md default) or Claude
     (`claude-opus-5-5`).
   - Subagents: `none` (default), `one-readonly-verifier` or
     `one-implementation-worker`.

   It gets his confirmation before dispatching with explicit
   `--agent/--model/--subagents` flags; the script refuses to run without
   them. The new thread's first message carries the selection and must
   restate it and get confirmation before any runtime work. Enabled base
   instances: A `claude-work`, `codex`; B `claudeAgent`, `codex`.
3. No B-side agent for routine tests; B is script-only. A read-only B
   diagnosis thread is created only for a failure A cannot explain from the
   evidence.

Standing rules:
- B tests only a pushed SHA and never A's working tree. Work in progress goes
  on a throwaway `test/…` branch.
- Results are labelled "verified at X". Before reusing one at a later HEAD,
  check `git diff X..HEAD` over the covered files and rerun if they changed.
- B produces evidence, not code. If B must ever change code, it uses its own
  `b/…` branch and A merges deliberately.
- The A agent is the single writer of controlled docs.

**Remaining work (only after the operator says go):**
- Add the done marker and collect-later mode to `run.py`/`request-from-a.sh`.
- Fold the prototype into `Workspace/scripts/workstation/`, with tests, an
  install refresh on both hosts, and the proposed screenshot fixes (target
  framing; hold screenshots that show something new or are dropped). These
  fixes still need the operator's approval.

## 8 October — `PLAT-U-07` bounded A/B handoff closeout

**Completed subgate — native T3/Git A→B→A handoff:** original helper,
8-category runtime parity, desktop preflight, clean Git worktree preparation
and both destination checks PASS at application checkpoint `cc494f9`.
The final incoming docs checkpoint was
`45f072b4694cebf31a5e7cf95325e597a09460bc`; both initial fresh destination-hosted
threads proved that exact HEAD and clean status. The fixed-project
proofs below supersede their project routing. No runtime tests were repeated.

The selected worktrees remain:

- B: `/home/light-tarun/dentobot/ros2_ws/src/DentoBot-handoff-20261007T213102Z-3952c66c74094b8596877959a6adc048`
- A: `/home/tarun/dentobot/ros2_ws/src/DentoBot-handoff-20261007T213258Z-ebf146c5fa0944a3a2603b51114c4652`

**Authoritative T3 routing (operator correction):** use the existing fixed
projects named `dentobot`, not a new project for each Git handoff.

- B project `772e40ab-42c5-454b-bd5e-660c32d62e6a`, root `/home/light-tarun/dentobot`;
  continuation thread `a8815b54-033f-4480-9aa1-343da412036b`.
- A project `4ccd124e-ce14-4318-b6f9-0310fa437544`, root `/home/tarun/dentobot`;
  continuation thread `93766301-bcc4-4aa8-b6fd-beebaf953076`.

Both native Luna Max continuations completed with their `worktreePath` set to
the selected Git worktree above, correct host/path, clean status and
`c9ea7bf262381f4ab4aeb947d8b222c8046b9c0b`. Project roots were not changed.
Initial fresh B thread30241a1d proved local45f072b before any A access, but
its extra-project routing and initial A proof threada6060eac are superseded.
The typed API has no thread-move/reparent command; historical threads/projects
are retained without database edits or deletion. Both proof workers finished;
B coordinator retains closeout ownership.

**Capability correction:** native authenticated `project.create`,
`thread.create` and `thread.turn.start` work. The parent used them to create
this fresh B thread; this coordinator used A's packaged server CLI to mint a
short-lived bearer and dispatch the native A return. No database/auth bypass
or second server. A lacks a `t3` launcher on PATH, but its packaged server CLI
is callable with `ELECTRON_RUN_AS_NODE=1`; the blanket unavailable claim was
false. `dentobot open` still requires `t3 app`; select the existing `dentobot` project
on the intended T3 host. Thread creation is not conversation/process migration.

Evidence: `data/dentobot-runs/2026-10-07/PLAT-U-07-thread-finalize-20261007T214331Z/B-local-proof.json`,
`fixed-project-thread-identities.json`,
`A-fixed-project-thread-snapshot.json`, `B-fixed-project-thread-snapshot.json`;
parent closeout evidence retains parity, both handoff manifests and launcher
PASS. Physical A-offline observation remains unperformed (operator-controlled).
Full S6/operator/cutover acceptance, any new pinned-mode reload campaign and
oversized Drive uploads retain separate gates in the sole backlog row.

Operator asks whether the thread has entered a rabbit hole, then directs:
“yes make the plan for next steps as per recommendation, and use luna max
workers for further grunt work”. The immediate outcome is an easy, verified
T3 Connect + Git A→B→A handoff. This supersedes the preceding suggestion to
complete launcher/reload work before demonstrating the handoff. The existing
`PLAT-U-07` backlog row remains the sole pending-work entry.

**Accepted evidence reused:** common container/native/installed ROS resources,
models and original approved fixture were synchronized; the specifically
approved `63551f8` B offline six-stage test passed actual load/save/reopen and
owned cleanup. Its new saved bundle was checksum-transferred to A. No repeat
case campaign is required to establish conversation/source handoff.

**Sequential closeout contract:**

1. Inspect current A/B selected checkouts and origin; preserve every dirty or
   divergent checkout. Publish only intended reviewed commits, fast-forward A
   to the agreed published checkpoint, and install that checkpoint's existing
   workstation helper package on both machines. Refresh each explicit source
   pin with `dentobot use "$(dentobot path)"`. Acceptance: clean selected
   trees, equal branch/HEAD/live origin and matching installed helper hashes.
2. Run the existing read-only `dentobot parity` and `dentobot check` on both
   hosts with each host's desktop authentication where needed. Acceptance:
   common image/native/installed ROS/model/fixture identities match; expected
   CPU/CUDA, username, display and OS differences remain explicitly local.
   A missing desktop session is a recorded display limitation, not permission
   to change that session or silently waive another parity failure.
3. Prepare A→B using the existing B-side `dentobot from-a --note ...`; select
   its returned destination worktree on B and recheck it. In T3 Connect select
   the B environment and its existing `dentobot` project and start a B-hosted thread with the returned
   `CONTINUE.md`, commit identity, evidence links and remaining task. Give it
   one harmless read-only continuation and confirm its actual B hostname,
   checkout and HEAD. A must have no active implementation owner for the
   handed-off scope. Demonstrate that the B thread completes without accessing
   A; any real A shutdown/disconnection remains an operator action.
4. When A is available, prepare the return from B with `dentobot to-a --note
   ...`, select the returned worktree on A, recheck its checkpoint and continue
   in an A-hosted T3 thread inside its existing `dentobot` project,
   setting thread worktreePath to the returned checkout; do not add a project. Transfer evolving cases individually with the
   existing `dentobot sync-case` command only when a new save exists; the
   already transferred save/reopen fixture need not be copied again.
5. Record the exact commands, two destination paths, T3 thread/environment
   identities, checkpoint and evidence in this task's logbook. Acceptance:
   both thread continuations used the intended machine/checkpoint, required
   assets passed parity, and no unpublished edit or case was lost. Close only
   the A/B handoff subgate; unrelated `PLAT-U-07` obligations remain open.

**T3 settings:** use explicit environment selection while proving the flow;
leave load balancing off for the acceptance exercise. T3 Connect provides
remote environment/thread access. GitHub sharing concerns provider access and
is not required for Git synchronization; automatic pull does not replace the
explicit checkpoint checks on this development branch. The exposed Device Hub
tools support iOS/Android devices, not proven Linux Slicer desktop takeover.
The existing B-local private-Xvfb harness provides isolated GUI verification
without taking over A's desktop. Cross-PC interactive desktop control is a
separate optional capability, not a handoff acceptance condition.

**Historical launcher item — resolved by the passed closeout check:** the `b2dfda6` actual B
`dentobot launch --check-only` failed before container start with
`TypeError: validate_container() got an unexpected keyword argument
'allow_idle_running'`. A read-only stdin import reproduced caller-CWD
shadowing: the helper-workspace module lacks that keyword, while explicitly
putting the selected workstation directory first imports the correct signature.
Give one Luna worker only the minimal explicit selected-import-path fix.
Use relevant host/shell checks first, then propose one bounded launcher-only
check. `--check-only` may start the verified idle container despite opening no
Slicer. Stop at the first new causal failure; do not expand into case/MoveIt
testing. The actual cc494f9 launcher-only check subsequently passed; reuse its recorded evidence. Production-menu reload under this new pinned mode is a separate unrun gate.

**Staffing and execution boundary:** two `gpt-6-luna` / `max` read-only workers
collect current state and exact existing command semantics; no recursive
delegation, controlled-doc edits or GUI/ROS/runtime ownership. The coordinator
owns the plan, integration and acceptance. This turn prepares the plan and
inspects evidence; it does not start a new runtime campaign. Future bounded
implementation work is assigned with explicit file ownership; runtime remains
serialized under the verification protocol. No new synchronizer, scheduler,
container rebuild, full S6 campaign or Drive upload is part of this closeout.

**Planning-time state:** B was clean at `b2dfda6` before these controlled-doc
edits, with all14installed helper files matching its selected package and its
container stopped. A's SSH endpoint responded but PAM refused login during
boot; its current source/helper state is unverified. Repeat only the A snapshot
once login is available, before any transfer. B's cached origin ref matches;
live-origin equality must still be checked during closeout.

## 7 October — `S6-FRAME-SYNC-01` Step B implementation contract

**B isolated fixture runtime (latest):** A online, clean published a0733d2
confirmed; recorded five-tooth SampleCBCT case copied with SHA256 parity and no
serialized ROS nodes. Nine loaded code paths/hashes match. One native
`test_DENTOWorkflowFrameSyncKnownTransforms` execution FAILS during hydration:
`ValueError: guide set has no matching tooth target`. Zero transform stages
ran. Actual Slicer1/launcher0, complete recording, stopped owned container/count0.
No automatic retry or application/fixture mutation. Review protected production
load/bind versus raw fixture load and saved target references; cause unproven.
[Evidence](/home/light-tarun/dentobot/data/dentobot-runs/2026-10-07/S6-FRAME-SYNC-01-B-20261007T175644Z/fixture-20261007T180503Z/diagnostics.md).

**Earlier B continuation (before A returned online):** latest published A branch confirmed at a0733d2; B's frame
production/tests match exactly. `pure.frame_sync` **95PASS** on B (4.77s),
owned container stopped/count0. Isolated known-transform runtime awaits the
explicit approved runtime-free multi-branch fixture path; full case/runtime/operator
gate remains pending. [Evidence](/home/light-tarun/dentobot/data/dentobot-runs/2026-10-07/S6-FRAME-SYNC-01-B-20261007T175644Z/diagnostics.md).

Operator requests continuation with Step B and Claude handoff logs. Scope is
[authoritative handoff §4](handoffs/2026-10-07-P0-pass.md): L1 shared world model /
segment accessor + AST guard; L2 independent all-object mesh export/compare;
L3 known transforms/runtime regression; L4 three-way FK API; L5 collision/ACM
agreement; L6 matrix. Separate commits in that order. Native digest / production
mesh gate phase 2 remains deferred; no native build or runtime execution.
Preserve exact J1–J5, collision/barrier/corridor policy, registry 3.0 and source
geometry. Existing pure/container approval covers focused/matrix checks only.
Coordinator owns interfaces/source integration/docs/acceptance. One reused optional
Luna xhigh auxiliary owns only explicitly assigned code/test files per layer
(recorded in logbook); no recursive workers/runtime/docs/acceptance. Pending runtime/representative verdict stays
in backlog under this existing P0 owner. L1 source/pure complete: 38 focused
checks pass; eight required suites retain only two known shell baseline failures.
Evidence: S6-FRAME-SYNC-01-L1-20261007T145157Z (7 Oct run archive).
L2 ready: independent source exporter + all-object sampled mesh comparator;
55 focused pass; matrix baseline failures only. Runtime scripts not executed,
production mesh gate phase2 deferred. Evidence: S6-FRAME-SYNC-01-L2-20261007T145647Z.

L3 source/pure ready: 49 focused pass; explicit fixture Slicer regression
prepared but NOT RUN. Evidence: S6-FRAME-SYNC-01-L3-20261007T150834Z.

L4 source/pure ready: 43 focused pass; three-way reusable FK rows, unchanged
tolerances. Evidence: S6-FRAME-SYNC-01-L4-20261007T151409Z. Runtime NOT RUN.

L5 source/pure ready: 59 focused pass; reusable 3-link exact collision/ACM
agreement. Complete authoritative contacts/current snapshot required; unsigned
surface separation is not penetration depth or motion acceptance. Evidence:
S6-FRAME-SYNC-01-L5-20261007T152500Z. Runtime NOT RUN.

L6 source/pure ready: pure.frame_sync95 pass, structure5 pass; JSON/loader
valid, headed runtime exclusive and approval-gated. Eight required suites retain
baseline failures only. Evidence: S6-FRAME-SYNC-01-L6-20261007T152958Z.
All six Step B layers source/pure complete; runtime/case/operator acceptance
stays pending in backlog, production native mesh gate deferred phase2.

## 7 October — `S6-LIVE-01`: Auto Task Home draft

Operator requests immediate modular implementation. Latest explicit correction:
use the incisor biting-edge midpoint, with depth adjustable later through
experimentation (supersedes the initial gum-line midpoint idea). Reuse
mouth-portal biting-point extraction on central incisors 11/21/31/41
in current opened world geometry, not edited workspace ROI or tooth centroids.
Depth defaults to 0 mm; positive offset follows midpoint toward selected Entry.
Drill axis follows selected Entry→Target, solved with existing five-joint IK.
The 6.2 action stages a draft only, then uses existing Review / Plan + Apply /
Accept owners. Preserve collision, scene, Base, branch and identity gates;
no automatic motion, acceptance, saved Home change or safety-policy changes.
Owned code: modular `auto_task_home.py`, facade adapter, Home panel and existing
manual/shell callback owners; focused fake/geometry tests and CMake registration.
Source/pure checks only under existing P0 approval; no GUI/ROS launch or motion.
Runtime reachability, experimental depth and operator verdict stay pending in
backlog under S6-LIVE-01. Stop the runtime path at the existing verdict gate.

Implementation/source verification: the 6.2 Auto Task Home Draft button reuses
mouth-portal cusp-tip extraction on all four central incisors, current opened
world geometry, existing connected Home-review identity, guarded IK and MoveIt
FK. Missing teeth refuse explicitly; no centroid/canine fallback. Separate
`depth_mm` argument defaults to 0; positive offset is toward selected Entry.
33 new focused checks, 5 structure checks and 81 existing manual UI checks pass;
combined planning/bridge/UI suite: 541 passed, 2 pre-existing application-shell
failures. Compilation/diff checks pass. Evidence:
`data/dentobot-runs/2026-10-07/S6-LIVE-01-AUTO-HOME-20261007T143746Z`.
No GUI/runtime acceptance; experimental reachability and depth remain pending.
Graph refresh exited 1 (`graphify` not on PATH), no graph success claimed.

## 7 October — `S6-MULTI-JAW-STALE-01` Step A: load-only ROS auto-connect

Contract: [P0 handoff, Step A](handoffs/2026-10-07-P0-pass.md). Operator directs
implementation with up to two Luna Max workers. After a verified case load
lands in Step 6, a compatible robot profile, selected VALID branch and saved
configuration permit restoration followed by the existing shell Connect owner.
Manual navigation, Import and Restore never auto-connect. Task Home is staged
in the jog controls only; no automatic review, acceptance or motion.

Implemented in the shared case loader after restore-barrier teardown and final
profile checks, covering File and library loads. Each restore resets an explicit
success flag; failed/partial restores cannot connect. Matching configurations
still stage saved Home; missing controls fail closed. Case-open status uses live
ROS state. Public signatures, registry 3.0 and safety policy are preserved.

Evidence: 27 focused fake/AST checks, 5 structure checks and 80 existing P0 pure
checks passed; compilation and diff checks exited 0. Required matrix results:
planning 300, restore 99, dentocase 94, responsive planning 297 passed; handoff
579, focus 32, five-DOF 525 and manual TCP 390 passed with the same two documented
application-shell baseline failures each (exit 1, not a clean suite PASS).
Exact commands/results: `data/dentobot-runs/2026-10-07/S6-MULTI-JAW-STALE-01-A-20261007T140720Z`;
see [today's logbook](logbook/2026-10-07.md). Runtime/GUI/operator acceptance is
NOT RUN and remains in backlog under this owner. Graph refresh unavailable:
`graphify` not on PATH; no graph success claimed.

## 4 October — UI-P3-01 narrow-fit slice: whole-module width contract

**Operator statements (4 Oct):** redesign the GUI so contents always autofit the
narrow default spacing as source-monitor resolution keeps changing; contents
almost always need side and vertical scrolling and the lateral part spoils UX.
Asked for plan and sketch before implementation; after the mock-up: "yeah
perfect, exactly what i want. But for the whole module and not just step 6".

**Contract.** Outcome: every DENTOWorkflow page (legacy module panel, new shell,
dialogs) reflows from `MIN_FIT_WIDTH_PX` (340 logical px) with no horizontal
scrollbar; only the page body scrolls, vertically. Dock default width =
clamp(24 % of logical screen width, 340, 520 px), saved as a screen fraction and
re-clamped on monitor change. Invariants: no control removed or reordered across
steps; no workflow gate, guard, planner or Step 6 policy change; display and
layout only. Owned files: `DENTOLayoutFit.py` (new), `DENTOApplicationShell.py`,
`widget_application.py`, `widget_bootstrap.py`, `widget_navigation.py`,
`CMakeLists.txt`, `Testing/test_layout_fit.py`, matrix check `pure.layout_fit`.
`widget_robot_shell.py` is at the 1600-line budget and is not touched.
Approved design: `data/visualizations/narrow-fit-gui-mockup.html` (illustrative,
not runtime evidence).

**Phases.** 1 Foundation (source + host tests) — implemented 2026-10-04.
0 Measure — one headless Slicer run calling `findWidthOffenders` per page at
340/390 px to list real offenders (needs operator approval; resources
`docker:dentobot-slicerros2`, `slicer_process`, `display`). 2 Per-panel fixes
from that list (explicit minimums in `DENTORobotSimulationPanel` joint rows,
long checkbox captions, grids, dialog/table minimums, view-controls palette).
3 Width-matrix and screenshot checks under `S6-GUI-HARNESS-GAP`. 4 Tarun's
normal-window verdict.

**Evidence so far:** host `pure.layout_fit` 36 passed. Phase 0/1 runtime audit
executed 2026-10-04 in the container under `xvfb-run` (no case, no ROS):
baseline 12/15 pages exceeded the 377 px viewport (worst 753 px) and the shell
chrome blocked shrinking below 414 px; final fitted run 0/30 over the viewport,
chrome 265 px, dock reaches 340 px, Slicer exit 0, no Traceback; screenshots of
Segmentation and 6.3 inspected. Evidence `data/dentobot-runs/layout-width-audit-20261004T114944Z/summary.md`
(+ baseline `…114739Z`). Known gaps: loaded-case text, nine dialog sites,
section-title clipping, ~90 px pinned legacy header, real monitors/DPI and the
legacy module panel. Tarun's normal-window verdict PENDING.

## 4 October — S6-LIVE-01 current live planner resolution contract

Current operator scope authorizes serialized real GUI simulation chains/repeat in PID2071, continuing through individual results. It supersedes older no-runtime/per-result verdict stops for this run; final Tarun verdict PENDING. A requires two fresh guarded Complete cycles and endpoints; B requires every section6 certificate. Preserve Base/geometry/guard/tolerance/case/history and explicit restart/native-build approvals. Solo coordinator; no new task or queue.

Runtime: remote MoveGroup FDI31 mesh was stale19.435258mm despite guard acknowledgement; exact existing-proxy redelivery restored all34bounds and made the previously invalid PreEntry endpoint valid. Canonical-frame alias correction host/reload/realConfirm verified, Home2 preserved. CheckPreEntryIK passed. Corrected real Plan then failedP1: lip_slab/housing contact0.133527mm at30/43 of straight joint line, RRTConnect empty trajectory. Neither planner failure nor finite IK sampling proves physical infeasibility.

Source: confirmation migrates only URDF-equivalent historical TCP alias; reverse-travel corridor correction preserves drill axis and existing guards. Failing-first regressions retained; final affected host503PASS. Reverse-travel correction touches ROS-stateful bridge and is NOT loaded: execution stopped for fresh-session/checkpoint approval. No preview cycle complete. Durable multi-consumer scene acknowledgement, native corridor/full-chain/repeat and operator verdict remain open under this owner. Graph refresh unavailable. [Evidence](logbook/2026-10-04.md), `/home/tarun/dentobot/data/dentobot-runs/planner-resolution-20261004T015000Z`.

## 4 October (later) — S6-LIVE-01 Step 6 GUI state reliability: patches only, severe testing pending

**Operator statement:** the small button behaviours fixed on 4 October are
case-specific patchwork that cannot be verified until tested extensively over
repeatable behaviour without such errors. Many similar unexplained greyed
controls, error dialogs and other Step 6 issues remain pending severe testing
and verification; headed/headless testing so far did not face or point out
these GUI errors. Agent finding: the headed runner has no modal-dialog watchdog
and asserts selected controls along one order, which is consistent with, but
not proof of, the miss.

**Patches made (not acceptance):** (1) 6.2 Review/Accept/Plan + Apply show named
blockers (`dentobot_workflow/task_home_gate.py`, panel
`setTaskHomeActionBlockers`), Home group no longer disabled as a whole;
(2) `applyTaskHomeDraft` snaps MoveIt's tolerance-level end (≤2e-4) onto the
exact draft through the strict guard and treats an already-applied draft as a
no-op; (3) `taskHomeValidationGap` and planner-button tooltips explain why 6.3
is blocked (guard-policy change from the spindle-contact option invalidated Home
validation and the confirmed snapshot). Host: 269 tests pass; live: real
handlers in PID2071. Tarun's verdict and repeatability are not recorded.

**Pending contracts (backlog rows, all `S6-LIVE-01`, Unprioritized):**
- `S6-GUI-STATE-AUDIT` — outcome: every Step 6 control explains why it is
  disabled/hidden; state-invalidating options say so; expected refusals are
  inline, not modal. Owned files: `dentobot_workflow/widget_robot*.py`,
  `DENTORobotSimulationPanel.py`, `task_home_gate.py`, facade readers.
  Invariants: no change to Base/Home/planner/guard policy, tolerances or
  geometry. Acceptance: state-combination host tests that fail on any
  disabled-without-reason visible control, plus a headed pass.
- `S6-GUI-HARNESS-GAP` — outcome: automated headed/headless checks that
  detect these defect classes (modal watchdog, disabled-without-reason,
  unexplained status, order/revisit permutations). Acceptance: the checks fail
  on the 4 October defects when the patches are reverted in a scratch copy,
  and pass on current source.
- `S6-HOME-REPEAT` — outcome: repeatable 6.2 plan/apply/accept. Acceptance:
  consecutive clean real-button cycles with all dialogs/greys recorded; the
  ~5 minute apply duration decided separately. Needs explicit operator
  go-ahead; restore the exact original Home afterwards.
Stopping condition: do not call Step 6 GUI behaviour verified from a single
passing run or from these patches.

## 4 October — S6-LIVE-01 cancelled collision-rejection recovery

**Bounded contract:** Repair the reported inability to re-review Task Home
after collision rejection in the saved Oct4 case, hot-reload Python and test in
the same open headed Slicer. Latest operator authorization supersedes the
older read-only/no-runtime boundary only for this defect. Preserve native/ROS
ownership, exact five-joint/current-identity gates, geometry, strict collision
policy, saved case and original draft. No plan/apply, robot motion or preview.

**Implemented:** `widget_robot.py` now allows a new review after cancellation
of a definitive rejection in connected/offline modes and keeps offline draft
editing available. Staged rejected candidates still cannot be accepted;
uncertain acceptance still blocks review/cancel and requires reconciliation.
Failure evidence remains until explicit fresh staging. Regression added to
`Testing/test_robot_manual_jog_ui.py`.

**Unit Verified:** new regression fails on the original source; focused Home29
PASS; both affected UI/facade suites242 PASS. **Runtime/Integration Verified:**
real buttons in Slicer PID2071 exercise original-draft review/cancel, zero-pose
strict collision rejection, Cancel → fresh Review, then restore the original
draft. Loaded source hash matches host. ROS, accepted/monitored/displayed joints,
Home JSON and case SHA are unchanged; no Home is saved. Same Slicer left open
at6.2 with Review enabled. Evidence/commands: [logbook](logbook/2026-10-04.md).

**Acceptance boundary:** recovery defect demonstrated; Tarun's verdict is not
inferred. The actual mouth-barrier/spindle collision and broader valid-Home,
continuity/full-cycle gates remain open under the existing backlog row.

**30 September operator refresh gate:** Tarun directs that no further Step 6 implementation changes enter integration until they are fully implemented, tested and verified. Hold the existing incorporated `e7cd29f` checkpoint; do not merge later unfinished renovation checkpoints. This supersedes the earlier periodic unfinished-checkpoint refresh strategy for future transfers only. Resume source refresh from an identified completed/verified renovation commit with recorded evidence; then run delta-affected combined checks. Current integration-only capture evidence remains distinct; the inherited maintainability gate was subsequently closed on1October.


**2026-09-30 integration execution supersession (`S6-LIVE-01`, `S6-P2-03`, `S6-REUSABLE-CASE-SETUP`):** Tarun explicitly authorized committed unfinished source checkpoints and the curated-5.10 integration pass. Frozen renovation **e7cd29f** is being merged into `integration/step6-5.10-reviewed-20260927`, after preserving prior integration in **243e3a1**. This supersedes older no-current-integration/no-commit sequencing only for this plan. Four GPT-6 Luna Max scopes run within three available concurrent worker slots. 5.12 runtime (`PLAT-U-06`), main/publication, final renovation incorporation and full-cycle/operator acceptance remain deferred/pending. Preparation evidence and dispositions are in `diagnostics/STEP6_INTEGRATION_PREPARATION_2026-09-30.md`; this is not a new task or pending queue.


Last reconciled: 2026-09-26. Case Foundation AUTO-primary GUI completion
recorded 2026-09-18; Step 3B placement mirror source-complete 2026-09-19
(not a second pending queue beyond `S3B-ROBOT-PLACEMENT-MIRROR`).

## Record ownership

[backlog.md](backlog.md) is the sole pending queue and mandatory first planning
lookup. This file retains task contracts, evidence boundaries, historical
aliases and closure records. The sections below are the 2026-09-11 migration
baseline, not a second scheduling authority. Read current state/next action in
backlog.md before using these contracts; update substantive contract/acceptance
changes here and keep execution chronology in the dated logbook.

## Immediate P0 — bore-safe Step 5B dock attachments

- **ID:** `W5-U-04`; **Priority:** 0 (operator-promoted 2026-09-10);
  **State:** Synthetic and FDI11 runtime verified, including clean
  final-fusion bore-axis screenshots. The current regenerated FDI31 package
  passes the explicit four-open-bore, zero-channel-occupancy, one-solid and
  no-duplicate-dock gate; the historical 5-voxel fragment is not reproduced
  in that current artifact. Source-contributor classification and normal-window
  operator review remain open.
- **Failure evidence:** Extended 9.6 mm through-bore subtraction preserved the
  bore but split FDI11 into `[60677, 9, 4, 3, 1, 1, 1, 1, 1, 1]` occupied
  regions. The corrected FDI11 rebuild now has one region `[62258]`, zero
  residual channel occupancy and open-bore visual evidence. A prior diagnostic
  FDI31 rebuild retained `[45966, 5, 2, 2, 1, 1, 1, 1]`; its largest remnant
  was at least 7.66 mm from any dock-bore axis, so it was not evidence to tune
  a dock branch without contributor classification. The current regenerated
  FDI31 artifact does not reproduce that fragment. The 0.1 mm³ cleanup ceiling
  and one-solid gate remain authoritative.
- **Corrected contract:** Route each cylindrical shell attachment tangent to a
  protected bore radius equal to `bore radius + connector radius + one voxel`.
  Land it on the reinforced outer annulus with at least one voxel of ligament,
  retain configured endpoint overlap, extended final channel subtraction and
  four independent branches. Fail early with Step 4C/5B control guidance when
  the annulus, route or allowed gap cannot support that construction.
- **Diagnostics:** A disconnected final fusion now reports voxel counts,
  approximate extra-region volumes, the cleanup ceiling, the Step 5B
  **Shell + Guides** inspection view and the Step 4C radius/yaw/dimension
  controls to review. It explicitly warns against increasing the artifact
  threshold to hide a mechanical fragment.
- **Boundaries:** No patient shell, trajectory, bore/connector numeric value,
  artifact threshold, collision policy, robot plan or clinical/physical-fit
  acceptance changes. `W5-U-03` retains broader Step 5B/5C acceptance and
  `W4C-U-01` retains future mechanical/rail design.
- **Acceptance:** Focused synthetic geometry proves four bore-tangent branches,
  one-voxel minimum annular/bore clearance, zero protected-channel occupancy,
  four open bore axes, one watertight occupied solid and schema-1 invalidation.
  FDI11 passes this acceptance. The current FDI31 regeneration also passes the
  required geometry gate and reopens with one current PreparedBranch; the
  remaining acceptance is contributor/normal-window review, not a permission
  to relax the one-solid or channel checks. The bounded automated sequence is
  registered as verification profile `w5u04-bore-safe-template`.

## Step 6 offline restore — existing related backlog

- **ID:** `S6-RESTORE-ROBOT-ROS`; **Priority:** Unprioritized.
- **Observation:** Package load connected ROS before a usable local robot.
- **Current contract:** Offline geometry/configuration hydration, then explicit
  runtime activation. The former automatic checkpoint reconnect sequence is
  superseded, including for schema-1 migration.
- **Disposition:** Audit load/callback ordering under the current P0 correction;
  retain this ID for remaining robot reconstruction acceptance. Fresh and warm
  loads must not auto-connect or duplicate runtime objects. Saved Home is
  configuration, not restored live validation.
- **Evidence:** 2026-09-09 logbook; representative normal-window acceptance pending.

## Step 6.3 workspace purpose and clearance review before Studio — 2026-09-09

- **ID:** `S6-WORKSPACE-PURPOSE`; **Priority:** Unprioritized; **Recommended priority:** 0 for purpose/clearance review and any demonstrated current-workflow defect; **Triage:** Backlog, discussion/design prerequisite for Studio workspace migration. Broader Studio presentation remains P1.
- **Affected workflow:** Step 6.3 Generate Workspace, reviewed exploration limits, retained joint/TCP samples and Home-connectivity evidence; downstream planning seeds and future Studio workspace/study eligibility.
- **Operator observation and request:** The 5 mm clearance leaves no TCP workspace in the intraoral space. Step 6.3 needs updating for the latest developments, and its purpose must be discussed and revamped before the Simulation Studio revamp.
- **2026-09-24 operator supersession and inspected result:** Tarun directs folding 6.3 into one Planning & Diagnostics area with current 6.4 confirmation and 6.5 planning, followed by a separate Preview & Control area. `logic_robot.createOrUpdateRobotWorkspace` enforces `max(5 mm, robotCoarseSelfClearanceMm)` on non-adjacent-link AABBs; the independent burr-origin environment point check defaults to 2 mm. Pure evaluation of the saved FDI11 all-zero Home against its matching tracked URDF returns `link-1`↔`link-3` AABB overlap at 5 mm, while the package's Task Home is recorded live `Validated`. The sample-derived reviewed J2 lower bound is 1.437742 mm; Home J2 is 0. The cloud's bounds can therefore exclude a current valid Home and must not stand in for task-specific IK/path/guard acceptance. The 5 mm origin/consumer question is resolved at source level; representative operator/runtime judgment on the full geometry remains open.
- **Revised purpose:** Optional FK/static-valid reach visualization and bounded Home-connected seed evidence, with status distinctions retained across save/reconnect. Task-limit review, task identity and exact trajectory feasibility belong in the merged Planning & Diagnostics area. Keep URDF mechanical bounds, selected explicit task limits, authoritative MoveIt scene and independent guard in force; do not remove the filter or change a clearance value solely from this pure result. See the 2026-09-24 decision and DEVELOPMENT_PLAN.md migration contract. This task is a prerequisite for the `S6-LIVE-01` UI/confirmation migration, while Studio remains downstream.
- **2026-09-25 confirmed ROI scope:** Restrict TCP workspace *sampling* to an editable 200 × 200 × 200 mm cube initially centered between upper/lower central incisors. This is a compute-domain limit, not a route or collision rule. The current fixed-count joint sampler still evaluates every state before accepting TCPs; post-filtering alone cannot deliver the requested speedup. Resolve ROI frame/landmark fallback, reject out-of-ROI states before expensive checks, and measure time and in-ROI yield. Details remain in the linked Step 6 renovation plan.
- **Evidence available:** The 2026-09-24 source/pure inspection above resolves the 5 mm parameter, its AABB reference and the saved FDI11 Home rejection under that draft filter. Existing 6.3 also retains MoveIt-FK/static-valid TCP/joint samples and bounded Home-connectivity classification; reviewed min/max limits are an exploration envelope, not a collision-free box. Representative current-runtime geometry interpretation remains open.
- **Risk/impact:** An unsuitable exclusion may discard useful intraoral candidates or present misleading feasibility evidence. Conversely, removing clearance without distinguishing TCP location, complete tool/robot geometry and phase-specific contact could admit invalid states. An empty sampled set is not proof that no task path exists.
- **Discussion deliverable:** Agree whether 6.3 supplies an exploratory reachability display, reusable Home-connected planner seeds, task-specific feasibility evidence, or separately labelled combinations; specify what is mandatory for a single trajectory and what is reusable across the 96-record registry. Separate joint/FK reach, whole-robot static collision validity, Home connectivity and full oriented task-path acceptance.
- **Bounded follow-up:** Locate every consumer of the reported 5 mm setting and determine whether it is an ROI inset, TCP exclusion, tool-envelope allowance or collision policy. Compare it with the current five-DOF canonical TCP, actual tool/guide geometry and phase-specific rules. Propose the smallest justified 6.3 behavior/UI/invalidation change after discussion; no replacement clearance value is selected here.
- **Dependencies:** This purpose/ownership decision precedes Studio Workspace migration and workspace-related shared-environment fingerprints. Current restore readiness and freshly validated Home are prerequisites for live generation checks; existing `S6-LIVE-05` still gates the wider Studio implementation.
- **2026-10-02 operator decision (supersedes the planning-gate role):** "Optional visual (Recommended)". 6.3 workspace generation and assisted-limit review are no longer prerequisites for Plan Approach; the prerequisite is the native-replica check that the accepted Base reaches the whole PreEntry→Target stroke (`step6CurrentBaseStrokeReachability`). Workspace output adds a visual reach envelope (alpha shape around static-valid TCP samples, green Home-connected samples, PreEntry/Entry/Target inside/outside) with a 6.3 "Show reach envelope" toggle. Home-connected samples remain optional PreEntry IK seeds when present. Source-complete; runtime and operator acceptance open.
- **Next verification action:** First perform a scoped source/settings audit and document the contract. Then, under the prescribed approval, use a reviewed intraoral case to attribute sample rejection to the exact filter, distinguish static-valid/Home-connected/untested samples, and check reconnect/target-change invalidation. Full-task guards remain authoritative; no collision margin, joint limit, anatomy authority or live-validity requirement is relaxed by this note.

## P0 reusable Step 6 setup and PreparedBranches

- **ID:** `S6-REUSABLE-CASE-SETUP`; **Priority:** 0.
- **2026-09-25 FDI11 reopen regression:** Tarun's `SEPT24/fdi11_step6.dentocase` contains a current saved opening and Step 6 diagnostic but reopened at Step 3A with stale-pose/closed-mouth appearance. A fresh headless load reproduced `STALE_MOUTH_OPENING`; MRML rounded the saved jaw matrix to six significant digits while the integrity-checked environment retained the precise pose matrix. Source now restores those exact values only after fingerprint and rounded-matrix equality checks, and persists the selected stage for future packages (legacy diagnostic cases return to Step 6). The correction is source/pure-package verified; runtime and normal-window acceptance remain open. Do not promote the separately stale saved forehead plane or reconnect ROS automatically.
- **2026-09-25 operator display follow-up:** Tarun's normal window now opens the FDI11 package directly at Step 6, but his screenshot shows opened anatomy together with closed-source CBCT. The committed-opened Step 3A/6 recommended view now hides source CBCT slices by default and is applied on restored current-pose stages. Source CBCT remains explicitly selectable for inspection. The revised display needs his normal-window verdict; this does not establish Step 6 planner or robot acceptance.
- **Current state (2026-09-14):** **Blocked pending external guide/tool/base
  geometry correction.** Case Foundation and reusable offline-base
  implementation is source-complete in the current checkout. The authoritative
  source was preserved; the reviewed production foundation save/reopen passed;
  current FDI31 Step 5C produced one eligible schema-3 PreparedBranch and its
  saved package reopened current. The approved current-source exact FDI31 run
  reached the requested target endpoint kinematically, but both bounded
  candidates were stopped by the authoritative guard at Stage 3: candidate 0
  at composed waypoint 255 / Stage 3 waypoint 27 and candidate 1 at its
  corresponding final Stage-3 boundary, on the selected-tooth ↔
  `pneumatic_spindle-Copy` collision. Goal 2, Return Home, repeatability,
  playback and ten normal-window observations remain `NOT_RUN`/open. No
  planner-success claim is made.
- **Opened-jaw display correction (2026-09-14):** The source segmentation is
  now treated as closed-pose inspection anatomy while the Case Foundation is
  current: every source segment is hidden per-segment in 3D, and the fixed /
  moving derived proxies are the only opened planning displays. A pre-hide
  visibility baseline is shared by both restore snapshots, including legacy
  packages missing the all-source record. The focused Slicer save/reload/reset
  regression passed; the exact FDI31 reopen audit recorded `0/54` visible
  source segments and 54/54 snapshot IDs. This is display/restore evidence,
  not collision acceptance or a replacement for the remaining production
  save/reopen audit of this migrated display state.
- **Scene-sync correction (2026-09-14):** Collision-scene acknowledgement now
  reads the complete live `/joint_states` vector before sending the unchanged
  state through the guard; it falls back to saved display values only when no
  complete live vector exists for offline/fake tests. This removes the traced
  stale-slider path that republished `J2=0.00202 mm` after Task Home had been
  verified. The focused pure suite remained `88 passed`; the current exact run
  reached active planning without reproducing that Home mismatch. Guard policy,
  base, target depth and collision rules were unchanged.
- **Current-source exact guard result (2026-09-14):** The native
  `collision_guard` was rebuilt from the current checkout and the approved
  exact run used that binary. The run produced a target-specific
  `FIRST_INVALID` sidecar: Stage 1 and Stage 2 completed; Stage 3 reached the
  requested target endpoint but the final waypoint was rejected because the
  selected tooth collided with `pneumatic_spindle-Copy`. The exact runner did
  not modify the r7 package, and the immutable source package remains
  separate as documented. This is a
  guide/tool/base geometry ownership question, not permission to add an
  exemption, shorten depth, move the base or tune dimensions.
- **Endpoint branch probe (2026-09-14):** A temporary read-only diagnostic
  tried 22 deterministic endpoint position-axis seeds against the same exact
  package; 8 met the native IK tolerances and all eight remained on the same
  J5 branch with the same template↔spindle, burr↔selected-tooth and
  selected-tooth↔spindle contacts. The hook was removed after the probe. No
  alternate branch or compliant planner change was evidenced, so the strict
  Stage-3 blocker remains open and downstream Goal 2/Return Home/repeatability
  and playback remain `NOT_RUN`.
- **Visual contact attribution gate (2026-09-14):** The operator reports that
  they cannot select a geometry correction without seeing why the spindle
  collides. The existing Step 5C reopen viewport is blank and the r13 sidecar
  retains the rejected joint state but no nearest/contact point. Reconstruct
  that saved Stage-3 terminal pose in an isolated offline Slicer scene using
  the exact r7 package and robot/scene resources; show target tooth, spindle,
  burr, guide and trajectory with context and close-up images, and mark any
  mesh intersection. The sidecar's solver `last_valid` vector equals the
  guard-rejected vector, so it is not an accepted guard state. Label onset
  depth `unknown` until a bounded static scene query resolves it.
  Reconcile the displayed meshes/frames against the native guard before a
  geometry-owner choice. No preview, physical motion or policy change is part
  of this evidence gate.
- **Superseding workflow:** Reviewed segmentation now leads to one Case
  Foundation before Step 4A: four reviewed landmarks, one committed hinge/gap,
  fixed-upper and moving-lower planning displays, then Steps 4A–5C. Step 6
  permits branchless offline robot/base review and foundation-only persistence.
  ROS + MoveIt requires the current pose, one explicitly activated eligible
  PreparedBranch, the compatible reviewed locked base and matching robot profile.
- **Persistent contract:** Outer `.dentocase` stays 2.0 and MRB remains geometry
  authority. DentoCase state is 3.0, Case Foundation/environment is 2.0 and the
  PreparedBranch registry is 3.0; legacy readers migrate in memory and write
  only on explicit save. `step6CaseJaw*` remains a compatibility alias.
- **Prior accepted evidence:** Operator approved the audited correction and its focused automated
  single-target acceptance passed. The narrow FDI31 recovery now loads the
  package offline without the former environment-mismatch rollback; static and
  exact-package headless checks passed for that boundary. The package's legacy
  Step 5C final-guide schema 1.0 is deliberately stale under current schema 2.0,
  so the planning context is deactivated and transient mouth-open proxy is not
  retained. Duplicate source-dock hiding is implemented for eligible schema-2
  branch restoration, but cannot be accepted against this legacy package until
  the planned rework chooses an inspection-only migration or regeneration path.
- **Main workflow:** One target tooth; one trajectory normally or an explicitly
  paired two for a real two-canal case. Never auto-merge three trajectories.
- **Optional testing:** Separate opt-in workflow over the existing 32-tooth ×
  three-slot registry. T1→A, T2→B, T3→C are independent PreparedBranches;
  T1+T2→AB is allowed only through deliberate pairing. Registry capacity is
  neither template multiplicity nor a main-workflow requirement.
- **2026-09-22 target-switch repair:** In the operator's combined FDI31/FDI21
  case, Step 5B retained FDI31's selected-guide reference after FDI21 became
  the active target. The existing inheritance helper now preserves a valid
  current-target one/pair selection but replaces an empty or stale cross-target
  selection with the eligible active `trajectoryLine`. This unblocks an
  independent FDI21 template in the same session; it does not fuse different
  target teeth or implement batch/Studio execution. Focused source check passes;
  normal-window reload/build acceptance remains open.
- **2026-09-22 Step 5C design:** The operator confirmed the Step 5B repair and
  built the FDI21 template, then Step 5C failed `Single current-frame target
  dock`. The selector currently swaps only a raw template model and the check
  incorrectly requires one docking model scene-wide. Implement the existing
  PreparedBranch contract in four bounded phases: registry-backed target-guide
  selection with pre-verification atomic activation; exact-branch dock
  verification and evidence binding; explicit eligible Step 6 activation; then
  two-branch save/reopen/switch acceptance. Detailed behavior and stopping gates
  are in the PreparedBranch correction plan. No cross-target fusion or batch
  runner is included.
- **2026-09-22 Phase 1 implementation:** Step 5C's raw model picker is replaced
  by a registry-backed Target guide selector. A separate pre-verification gate
  reuses every strict dependency check through the current Step 5B template,
  then the existing rollback-safe activation transaction swaps the full branch,
  invalidates runtime evidence and isolates registered branch geometry. The
  ordinary `evaluatePreparedBranchEligibility()` path still requires matching
  PASS/WARNING Step 5C evidence. Focused source evidence passes; operator GUI
  acceptance is pending before the branch-scoped dock check changes in Phase 2.
- **2026-09-22 Phase 2 implementation:** The operator-visible Phase 1 selector
  correctly activated FDI21, while the deliberately unchanged scene-global
  dock count still failed. `Single current-frame target dock` now counts only
  assemblies matching the selected template's target, ordered trajectory set
  and Case Foundation planning-pose fingerprint. Other target branches may
  coexist; a second exact-branch assembly remains FAIL. Focused source checks
  pass; the operator's normal-window verification verdict is pending.
- **2026-09-22 per-target builder ownership:** Operator confirmed rebuilt FDI31
  passes Step 5C, but FDI21 had become stale during the pre-fix rebuild. The
  existing PreparedBranch activation transaction now restores upstream Step
  4B/5A/5B nodes from stored shell provenance, and new/unprepared target
  selection clears those active pointers before generation. Registry display
  ownership includes the upstream nodes without adding a second store or
  changing the branch verification revision formula. Focused source checks
  pass. Rebuild FDI21 once, verify it, then confirm FDI31 remains Verified;
  Phase 3 Step 6 handoff remains pending that manual two-branch verdict.
- **2026-09-22 Phase 3 operator evidence:** FDI21 passed Step 5C and the fresh
  Step 6 Goal 1 request consumed FDI21, then stopped in canonical TCP
  position-axis IK preflight with no collision contacts. The diagnostics viewer
  retained the prior FDI31 66/10/22 result but correctly marked it `Stale`
  because the target tooth changed. This accepts branch attribution and
  diagnostic invalidation only; it does not claim an FDI21 plan. Further
  algorithm/geometry diagnosis pauses for operator direction, and Phase 4
  save/reopen switching remains pending.
- **2026-09-22 residual branch-lineage and 6.4 repair:** Alternating FDI21 and
  FDI31 regeneration still staled the inactive target because PreparedBranch
  activation did not own/restore the mutable research shell, research sleeve,
  finalized shell and trim node. Newly generated final guides now hold explicit
  MRML references to those exact intermediates; registry revision/ownership and
  activation follow those references, while an unprepared target clears them.
  The immutable-task button remains fail-closed, but its status now enumerates
  the actual missing 6.0/6.1/6.2/6.3 prerequisite instead of showing only the
  circular confirmation prompt. Focused source checks pass; operator reload,
  one-time rebuild of both old-format branches, alternating verification, and
  6.4 UI acceptance remain pending.
- **2026-09-22 saved-package scalar-lineage diagnosis:** Read-only inspection
  of `FDI21-32-dentobot-case-sep22-step5c.dentocase` (SHA-256
  `5425ea7d6d58d3c4eeb7915e01fa735de06d6a967d3f52ed1267cc49b91d1953`)
  found distinct FDI21/FDI31 branch node sets. FDI21's retained docking assembly
  stores yaw `-40°`, while FDI31 stores `35°`; branch activation restored the
  dock node but not these parameter-node scalars. The shared activation
  transaction now restores the complete normalized Step 4C parameter set,
  rolls it back on failure and requires scalar equality before taking its
  idempotent return. This prevents selection alone from manufacturing a Step
  4C dimension change. Source verification passes; existing explicitly stale
  FDI21 data still requires one honest rebuild and normal-window/save-reopen
  acceptance.
- **2026-09-22 headless GUI runtime evidence:** The matrix-owned reusable-case
  runner now has an opt-in saved-case mode while retaining its default
  synthetic behavior. Against package SHA
  `5425ea7d6d58d3c4eeb7915e01fa735de06d6a967d3f52ed1267cc49b91d1953`,
  real GUI button clicks selected FDI21 in 4A and regenerated 4B, 4C, 5A and
  5B. Step 5C then verified FDI31→FDI21→FDI31, checking after every selection
  that active normalized docking parameters exactly equal the branch's stored
  parameters. FDI31 restored yaw `35°`; FDI21 restored `-40°`; neither became
  stale. A final FDI21 selection verified and Step 6A activation imported
  branch `guide-fe8080de25e7eb57622d`. Marker
  `DENTOBOT_MULTITARGET_STEP5C_PASS`, process exit 0 and clean teardown are
  retained with six screenshots. Normal-window operator verdict and a newly
  saved/reopened two-current-branch package remain open.
- **2026-09-22 headless save/reopen evidence:** The same GUI workflow saved a
  new package at `data/Slicer_Saved/SampleStudy1/FDI21-31-headless-verified-sep22-step6a.dentocase`
  (SHA-256 `c16e0406b589de1cb2144628b38a26100157458d48b5edb9c56ad4f8792d1c1d`)
  without overwriting the supplied source. A separate fresh Slicer process
  reopened and post-hydration validated it: selected FDI21 PreparedBranch
  `guide-fe8080de25e7eb57622d` was eligible/`VALID`, and both FDI21 and FDI31
  trajectory slots were `Current`. Normal-window operator acceptance remains
  open; no ROS, MoveIt, planner or preview was started.
- **2026-09-22 postmortem boundary:** The later operator screenshot identifies
  FDI21 in the viewport after a reported minor base adjustment, but its motion
  diagnostics are explicitly `Stale` after target change and retain the older
  FDI31 66/10/22 route. Do not promote this screenshot to fresh FDI21 planner
  success. The adjusted base is not in the saved headless package above. One
  exact-case, plan-only automated check is prepared but not run; it requires a
  separately saved adjusted scene and serialized runtime after the operator
  closes the active session. The 96-trajectory Studio ambition and predictive
  base/IK diagnostics remain downstream, not part of this acceptance gate.
- **2026-09-22 diagnostic-attribution correction (source verified):** The
  bounded PreEntry search now persists a current `preentry_ik_unreachable`
  motion-diagnostic record when it finds zero collision-aware endpoints instead
  of leaving the previous target's diagnostic visible. The inspector displays
  the retained task, trajectory and robot-base fingerprint prefixes and states
  that this regime is endpoint reachability rather than Home→PreEntry
  connectivity. This reuses the current diagnostic schema; it does not predict
  a new base pose, run a base sweep or establish FDI21 runtime acceptance.
- **PreparedBranch:** Exact trajectory selection and pairing intent, patient
  shell, unified template, dependent guide references and Step 5C verification
  identity. Step 6 selects this complete branch, not a raw trajectory.
- **Switch:** Preserve unchanged jaw opening, landmarks, base matrix/lock,
  Task Home and shared anatomy/environment. Swap the full branch and Step 5C
  evidence atomically. Invalidate branch confirmation/collision acknowledgement,
  plans, previews, guards and diagnostics; never stale shared setup solely
  because selection changed. Real dependency edits still invalidate dependents.
- **Legacy:** Three-trajectory templates remain inspectable but cannot become
  eligible prepared branches. Do not silently split geometry or discard case
  content. Load stays offline; migration writes only on explicit later save.
- **Plan:** [PreparedBranch correction plan](DEVELOPMENT_PLAN.md#s6-reusable-case-setup-correction-plan).
  The 2026-09-10 decision supersedes tooth-owned/per-slot-copy and raw-selector
  interpretations. Existing MRML, registry and .dentocase remain authority.
- **Evidence:** Registry schema/pure tests now cover one canonical branch record,
  selected-branch authority, explicit pairing, scoped staleness and fail-closed
  legacy migration. Static compilation and `git diff --check` pass; host pure
  suite is 85/85, container planning set 67/67 and container restore set 39/39.
  The focused runner invoked only the single-target current workflow, asserted
  eligibility, failed-activation preservation and Step 6 import, and exited 0
  with `DENTOBOT_REUSABLE_CASE_PASS`. Evidence is under
  `/tmp/dentobot-verification/prepared-branch-single-20260910/`.
  The exact failing package is
  `data/Slicer_Saved/SampleStudy1/FDI31/run2-dentobot-case-step6x5.dentocase`.
  Static MRML inspection shows the transformed Step 5C proxy plus a separately
  visible, untransformed `[Step 4C] DENTO Four Independent Robot Docks` model.
  The 2026-09-10 exact headless load reached `_openCaseBundle` successfully with
  `step6SchemaMigrationPending=True`; it then correctly classified the saved
  `DENTOBOT.FinalGuideSchemaVersion=1.0` as stale against required schema 2.0.
- **Prior evidence (2026-09-11; superseded 2026-09-15):** The targeted pass
  compiled every changed Python file using `/tmp/dentobot-case-foundation-pycache`;
  `Testing/test_step6_state.py` passed 23/23; the four task-relevant modular
  API/CMake/import checks passed; and the production module/UI contains no
  active draft-phantom import, control, callback or target-jaw fallback action.
  The aggregate modular test then reported the now-resolved 1,511-line
  `widget_template_build.py` failure against the former 1,500-line ceiling.
- **Current modular-gate evidence (2026-09-15):** The stale API manifest entries
  were reconciled to the intentional current signatures, including
  `baselineVisibility` and the correlated `syncStep6MoveItPlanningScene`
  options. The active routine-module ceiling is now 1,600 lines, with the
  public entrypoint still capped at 500 and all API/CMake/import/process-boundary
  checks retained. The complete `Testing/test_modular_structure.py` gate passes
  5/5; the current `widget_template_build.py` count is 1,520 lines.
- **Next:** Keep this one P0 lane. First capture and resolve the exact
  fingerprint-mismatch package identity reported from the manually opened
  Slicer case, then run one bounded exact runtime packet that writes its
  first-invalid/complete JSON before attempting the full repeat loop. After a
  complete guarded route, perform the ten-point normal-window review. Legacy
  branches remain inspection-only; do not infer operator acceptance from
  automated planning or continue whole-flow retries without a diagnostic
  artifact.

### Four-central-incisor exact-case campaign — superseding scope (2026-09-14)

Run FDI31 → FDI41 → FDI11 → FDI21 from the immutable open-mouth/base source,
one tooth per clean Slicer process, through 4A→4B→4C→5A→5B→5C, verified STL
export, production `.dentocase` save, fresh-process reload and exact Stage 6.
Store each target's package, STL, SHA-linked JSON and screenshots under
`data/Slicer_Saved/SampleStudy1/FDI<nn>/<run-id>/`; store the comparison under
`SampleStudy1/central-incisors/<run-id>/`. Current segmentation evidence has
all four tooth masks, pulp for FDI31/41 and no FDI11/21 pulp. Preflight
required pulp before Step 4A; absent pulp is an input-data result, not a
license to synthesize anatomy or change target depth. The preceding target's
scene is never the next target's input.

One first-causal failure per tooth marks downstream stages `NOT_RUN`. Preserve
target-specific anatomy/geometry/planner/guard failures for comparison and
propose the next tooth only after operator approval; stop on a shared source,
serializer, fingerprint or runtime
failure for a bounded root-cause correction. No base, depth, dimensions or
collision/guard policy workaround. The previous FDI31-success prerequisite and
FDI32 inclusion are superseded. The optional six-target matrix remains
downstream. See [the campaign gate](DEVELOPMENT_PLAN.md#2026-09-14-four-central-incisor-exact-case-campaign).

The operator selects Luna Max manually. On a novel ambiguous or higher-reasoning
decision, Luna stops the affected path and returns the evidence/reasoning-type
packet defined in the campaign gate; it does not silently change models,
delegate or improvise a fix. This is campaign-specific, not a global model
default.

**Execution is packet-gated:** A is the generator's STL/folder/diagnostic edit;
for each tooth, B input/fingerprint preflight, C one 4A–5C/STL/save, D
new-process reload, E exact Stage 6 route and F repeat/playback only after a
Complete E. One verified artifact or first-causal failure ends each packet.
Even a classified tooth-specific failure requires operator approval before
the next tooth; no compound instruction or automatic next packet. See the
campaign plan for exit evidence and `NOT_RUN` disposition.

**2026-09-14 operator approval and result:** After the first launch-only
failure, the operator explicitly approved the offline Slicer runtime check for
the current FDI31 semantic implementation and stated that no robot motion or
patient-facing action was authorized. The corrected current-source run used
the documented Jazzy/workspace/module-path setup and reached the exact
requested target endpoint, then stopped at the first native Stage-3 guard
failure: selected FDI31 tooth ↔ `pneumatic_spindle-Copy` at composed waypoint
255 / Stage-3 waypoint 27. The full FDI31 Step 4→Step 6 simulation remains
open; later packets and other teeth remain separately gated.

### 2026-09-14 FDI31 planner recovery — Campaign 1 supersession (historical status)

**2026-09-15 revised execution delta:** The operator has activated this same
`S6-REUSABLE-CASE-SETUP` / `S6-LIVE-01..04` task lane. The preceding Astra,
design-only and P4-end language is historical. The active task constructs and
reviews a new corrected FDI31 case from the 15 September opening/landmark/base
foundation, with FDI42/41/32/33 supports, 1.0 mm dock bores and >=2.0 mm
trajectory-guide/channel dimensions. It preserves r7/r13 unchanged and binds
the operator-specified approximately 5.2394 mm trajectory to exact saved
artifact identity before construction. Gates A–D cover scene, endpoint/
insertion, approach, and guarded withdrawal/Home/fresh-process reproduction.
One Luna Max worker may edit only explicitly assigned implementation files;
the main orchestrator owns diagnosis, runtime and acceptance. Frozen geometry,
task, policy and safety invariants remain unchanged.

**2026-09-15 source result:** `Testing/run_dentobot_stage6_target_generation.py`
now accepts the explicit `DENTOBOT_STAGE6_FDI31_TRAJECTORY_MRB` opt-in input,
strictly parses the retained Step-4A archive member, converts its LPS points
to RAS exactly once through the existing trajectory APIs, records
`SavedStep4A15Sept` provenance and does not generate an assisted duplicate.
The same correction sets the runner's FDI31 dock-bore default to `1.0 mm`.
`Testing/test_fdi31_saved_trajectory.py` exercises valid conversion and two
invalid input cases; the focused set passed 29/29, changed files compiled, and
`git diff --check` passed. This is **Implemented / Unit Verified** only. The
first corrected case, actual MRML lifecycle, geometry review and all Gates A–D
remain open.

**2026-09-15 Gate-A first-failure result:** The explicitly authorized, single
offline Slicer run `c1-gatea-fdi31-20260915-r1` passed its isolated-container,
no-competing-process, source/archive-hash and fresh-output preflight. It loaded
the 15-September source but then stopped at runner line 868 because
`logic.getTrajectorySummary(trajectory)["isValid"]` was false for the imported
line. The runner emitted `STAGE6_TARGET_FAIL FDI31 {"error": "FDI31 trajectory
is invalid"}` and a `passed: 0` generation report. No STL, saved case or reopen
acceptance exists; no planner, insertion, guard, ROS motion, controller,
hardware or patient path ran. The retained log hash is
`ea00448978da1b09b2c47577fd9f4bb77c1bb86d5325173d3f7d0be81f738270`; the FAIL
diagnostic and both Slicer screenshots are preserved under the run directory.
This closes the authorized Gate-A attempt as **FAIL / shared construction
blocker**. Do not retry or enter Gates B–D. Diagnose the exact MRML-state cause
and add a minimal source regression before seeking a new, separately authorized
runtime run.

**2026-09-15 source correction after Gate-A failure:** The line lock now occurs
only after the shared `getTrajectorySummary()` validity check, matching the
existing assisted-generation lifecycle; invalid output includes that summary.
The focused 29-test source set, `py_compile` and `git diff --check` pass. A
fresh r2 container/process/hash preflight passed, but the requested Slicer
launch was rejected before execution because the current operator message did
not explicitly authorize the separate second state-changing construction/reopen
attempt. No r2 artifact or runtime evidence exists. The remaining next action
is one explicitly authorized, isolated offline Gate-A r2 attempt only.

**2026-09-15 r2 result / conditional r3:** Explicitly authorized r2 ran once
after a clean preflight and failed before template generation. Its enriched
runner summary proves `definedPointCount: 0`, with null Entry/Target/length;
therefore r2 disproves the lock-after-validation hypothesis and localizes the
defect to point acceptance. The runner now explicitly unlocks the new saved
line before adding points and requires exactly two accepted points immediately.
The focused 29-test source set, compile and whitespace checks pass. r1/r2 are
the first two causal attempts. One explicit r3 attempt may test this distinct
live-lock hypothesis; any third failure stops autonomous runtime retry and
returns a three-attempt evidence packet. Gates B–D remain NOT RUN.

**2026-09-15 final r3 / source root cause:** r3 is the third and final
autonomous runtime attempt; it failed with zero points after the immediate
insertion assertion had already passed. Source trace attributes later removal
to the existing Step-4A bounds handler: the saved points were supplied in the
closed RAS frame while the FDI31 lower target is evaluated in the opened Case
Foundation frame. The runner now applies the existing frozen jaw matrix once to
both saved points and records those planning-frame values. Focused source checks
pass, but the retry ceiling prevents a fourth runtime attempt. Gate A remains
FAIL; any exception requires a new operator-approved verification plan. Gates
B–D and other teeth remain NOT RUN.

**2026-09-15 revised Gate-A r4 completion:** The operator then explicitly
authorized an r4 exception plan that checked the final Case Foundation mapping
before UI bounds enforcement. The single serialized offline run
`c1-gatea-fdi31-20260915-r4` emitted the runner's FDI31 PASS and all-targets
complete markers, wrote a new 84-MB `FDI31-step5c.dentocase`, verified STL and
save/reopen diagnostic, and captured post-reopen UI/viewport images. The
diagnostic status is PASS: two bounded planning-frame points retain the exact
5.239400689721231-mm saved trajectory, FDI42/41/32/33 are the four supports,
and the reopened PreparedBranch is current/verified. The outer Slicer process
returned exit 1 only during shutdown after those PASS markers, with leak
warnings; keep that process-health outcome distinct from Gate-A functionality.
Gate A is complete for corrected-case construction/save/reopen. It does not
accept Gates B-D, other teeth, physical/clinical fit, motion or hardware.

**2026-09-15 r4-only Gate-B preparation:** The operator selected the r4 saved
case as the only active execution baseline. The historical r7 endpoint runner
is not reusable because it hard-codes a different 6.6719049312-mm trajectory.
`run_dentobot_step65_exact_case_smoke.py` now offers an opt-in
`DENTOBOT_ENDPOINT_ONLY=1` branch that requires an explicit case path, loads
only that case, evaluates direct native position-axis IK at its exact saved
Target from no more than Task Home plus 13 Home-connected workspace seeds, and
records generic plus phase-aware static validity. It returns before any
approach/drilling planner, preview, insertion or route-locking call. Focused
static coverage passed 29/29; the separate serialized runtime check remains
the pending Gate-B evidence.

**2026-09-15 r4-only Gate-B runtime disposition:** That separate runtime
check is **NOT EXECUTED**, not a case or IK result. Its checksum/process
preflight passed, but three SlicerROS2 environment-initialization failures
stopped before r4 or the runner opened: unsupported `sh` option, ROS2 module
registration, then missing `librclcpp.so` for the ROS2 Slicer module. The
three-failure retry ceiling closed this runtime lane; no planner, preview,
insertion, motion, hardware or historical case path ran. The implementation
now emits `DENTOBOT_ENDPOINT_ONLY_COMPLETE` to distinguish successful runner
completion from its diagnostic result. Focused static coverage remains 29/29,
`py_compile` and `git diff --check` pass. A further runtime attempt requires a
new explicit operator-approved exception limited to this environment blocker.

**2026-09-15 P3 r4-only execution authorization:** The operator supplied that
exception and authorized the plan's P3 experiment. This supersedes the former
14-seed endpoint-only preparation as an acceptance path: the implemented
diagnostic must instead run one premanifested deterministic batch of at most
128 J1–J5 seeds using r4 current-state data and active runtime limits only.
Historical outputs are excluded completely. The prior loader error has a
specific environment correction—source Jazzy and the workspace install before
Slicer—but no P3 result exists until the serialized native batch completes.
P4 is conditional on a P3-valid endpoint; P3 excludes planner, preview,
insertion, route locking, motion, hardware and patient operations.

**2026-09-15 P3 runtime status:** Implementation and the matrix-routed runtime
contract are ready; focused checks pass. Exact r4 checksum/fresh-output/process
preflight passed. The attempted runtime dispatch was rejected before launch,
not failed, because it would be the fourth Slicer/ROS initialization attempt
after the three recorded initialization failures and the authorization did not
explicitly identify that retry risk. No case or output changed. A single,
explicitly named fourth-attempt authorization is required before executing the
already prepared offline r4 P3 batch; its no-planner/no-motion/no-hardware and
no-historical-input boundaries remain fixed.

**2026-09-15 P3 interrupted batch and minimal repair:** The authorized fourth
initialization batch was started and opened r4, but no P3 candidate result is
valid: its log exposed MoveIt planning requests before candidate evaluation.
The coordinator stopped the owned Slicer process, and the launcher/guard cleanup
was verified. No preview, execution, hardware, historical input or diagnostic
JSON occurred. The cause was the runner's automatic workspace regeneration
before its endpoint branch. P3 now returns before that production helper and a
focused source assertion enforces the ordering; the relevant static checks pass
29/29. The run is **INTERRUPTED / no endpoint verdict**. A future authorized
rerun must use a fresh evidence directory and explicitly preserve the
no-planning boundary; P4 remains NOT RUN.

**2026-09-15 P3 r2/r3 dispatch boundary:** The first replacement wrapper
started its temporary stack but exited before Slicer, `runtime.log` or any P3
candidate; the identified launcher and guard PIDs were cleaned up. The direct
P3 native IK call now disables only its generic collision prefilter so the
existing phase-aware predicate, rather than a generic ACM, determines every
converged candidate's admissibility. Focused checks remain 29/29. A subsequent
fresh r3 dispatch was rejected before launch: it exceeds the previously
authorized one replacement, and cleanup must not target all matching guard
processes by pattern. P3 remains INTERRUPTED/NOT TESTED and needs a new
explicit r3 authorization with PID-validated owned-process cleanup.

**2026-09-15 P3 r3 closure:** r3 started only its temporary stack and did not
reach Slicer, runtime logging or native candidate evaluation. The exact r3
launcher PID 3775 and guard PID 3800 were recorded from that run's evidence
before being terminated and verified absent. With r1's no-planning stop and the
r2/r3 pre-Slicer interruptions, P3 has reached its three-attempt runtime/setup
ceiling. P3 remains **NOT TESTED / INCONCLUSIVE**; P4 remains NOT RUN. A new
authorization alone does not reopen this lane: the next proposal must be a
revised, evidence-backed launcher/readiness plan using the cheapest
non-Slicer check and preserving all r4/no-planning/no-historical boundaries.

**2026-09-15 launcher/readiness repair complete:** The non-Slicer diagnostic
found that prior temporary stack launchers had left twelve log-attributed ROS
children, yielding four `/joint_states` publishers and blocking readiness.
Those exact PIDs were terminated after validation. The new dedicated P3 driver
starts `ros2 launch` in its own session/process group and terminates that group
on every exit; it sources ROS before enabling `set -u`. A fresh readiness-only
run passed immediately with one publisher and `ready:true`; teardown left zero
publishers and no stack process. Its syntax/matrix/static checks pass 29/29.
This is a verified launcher repair, not P3 endpoint evidence. P3 remains
NOT TESTED/INCONCLUSIVE at the prior retry ceiling and needs a revised explicit
runtime authorization before the repaired driver may open r4.

**2026-09-16 P3 r4 runtime interruption and source repair:** The explicitly
authorized fresh run `c1-p3-fdi31-20260916-r4` passed the exact r4 checksum and
stack readiness, then loaded r4 into Slicer. It stopped before any native IK
candidate, candidate JSON, endpoint marker, planner request, preview,
insertion, motion or hardware action. The terminal cause was the generic
post-restore `confirmTask()` call: it demands workspace-assisted limits, while
P3 must not generate that workspace because the helper submits planning
requests. The process-group trap removed the owned stack and post-run inventory
found no matching Slicer/ROS/MoveIt process. The P3 branch now uses the
restored r4 snapshot directly and fails closed if absent; it does not call
`confirmTask()` or workspace generation. Its source-order regression plus the
focused suite passed 29/29, compilation, syntax/matrix checks and Graphify
refresh passed. This is a runtime setup interruption, not endpoint evidence;
P3 remains NOT TESTED/INCONCLUSIVE and needs a new explicit one-batch r4-only
authorization before any rerun. P4 remains NOT RUN.

**2026-09-16 P3 r4 second setup interruption and ephemeral-snapshot repair:**
The separately authorized fresh run `c1-p3-fdi31-20260916-r4-r2` again passed
the r4 checksum and stack readiness and loaded r4, but produced no candidate,
candidate JSON, endpoint marker, planner request, preview, insertion or motion.
It failed closed because the offline r4 package intentionally has no persisted
confirmed-task snapshot. Endpoint-only mode now permits only that exact absence:
it constructs a non-persisted P3 snapshot with the existing pure constructor
from unchanged r4 trajectory, live Task Home, current base/task-limit/robot
fingerprints and established simulation-tool provenance. It records
`ephemeral_r4_p3_snapshot` in its output and rejects any other freshness issue.
It neither confirms a normal task nor generates workspace. Focused checks pass
29/29 with syntax/matrix/compile/diff checks and Graphify refresh. This is
still a setup interruption, not P3 endpoint evidence. A fresh explicit
one-batch r4-only authorization is required before runtime; P4 remains NOT RUN.

**2026-09-16 P3 r4 third setup interruption and native-joint mapping repair:**
The separately authorized fresh run `c1-p3-fdi31-20260916-r4-r3` passed the
locked r4 checksum, temporary-stack readiness and Slicer load, but stopped
before a native solve, candidate JSON, endpoint marker, planner request,
preview, insertion or motion. The runner had required its native joint-limit
API to equal the five planning joints; the live Slicer ROS node exposes the
complete KDL chain, J1–J5 plus the known external visual spindle. Endpoint-only
code now requires exactly that known six-joint API, reads native joint types,
maps only J1–J5 to `ROS2_JOINT_SI_ORDER`, rejects any missing/duplicate/
unexpected joint or invalid type/range, and wraps comparisons only for native
continuous J5. The external spindle remains outside all seed, IK and guard
inputs. Focused source checks passed 29/29 with syntax/matrix/compile/diff
checks and Graphify refresh. This does not establish endpoint feasibility;
P3 remains NOT TESTED/INCONCLUSIVE, a new explicit one-batch r4-only
authorization is required before runtime, and P4 remains NOT RUN.

**2026-09-16 P3 r4 completed bounded-negative endpoint gate:** The next
explicitly authorized fresh batch, `c1-p3-fdi31-20260916-r4-r4`, executed the
repaired r4-only diagnostic to completion. The direct non-executable driver
call failed before any runtime resource; the unchanged driver was then invoked
through `bash`, produced one stack/readiness pass and no second batch. It wrote
`endpoint_candidates.json` SHA-256
`8853f5208a87368d2611fd9c0a9737fe6b73b4da43de6851f4a428adee3f734c` and
`DENTOBOT_ENDPOINT_ONLY_COMPLETE`. Its complete premanifested set has 128
J1–J5 seeds, 21 converged native position-axis IK candidates, six deduplicated
clusters, zero generic-static-valid candidates, zero phase-static-valid
candidates and zero retained P4 representatives. The result is
`NO_VALID_TARGET_SOLUTION_FOUND_IN_BOUNDED_SEARCH`; all converged candidates
failed the existing phase guard because their provisional drill tip left the
approved Entry-to-Target corridor. Generic static records also list
Template↔visual-spindle and target-tooth↔burr contacts. `Planning request=0`;
the run did not use preview, joint/controller/hardware motion, spindle/patient
action or historical data. Cleanup left zero matching runtime processes. This
is a completed bounded negative, not a global feasibility claim. Per the P3
contract, do not add seeds, tune the solver, alter geometry/policy or run P4.
Campaign 1 is stopped at P3 pending architectural review; P4 remains NOT RUN.

### 2026-09-16 P3 diagnostic-correctness repair and saved-candidate revalidation

The operator directed a correction of the preceding classification, not a new
IK experiment. The old evidence JSON remains immutable input (SHA-256
`8853f5208a87368d2611fd9c0a9737fe6b73b4da43de6851f4a428adee3f734c`) and
supplies exactly its 21 converged canonical J1–J5 vectors. Review confirmed
two defects: `endpoint_only_diagnostic()` labelled a Home-to-endpoint transition
as phase-static, and generic-static collision diagnostics independently vetoed
contact that the authoritative phase-aware guard may permit. Its bounded-negative
result is therefore **superseded as a phase-static endpoint verdict**; historical
generic contact evidence and causal history are retained, not erased.

The repaired runner sends one unique, increasing-sequence,
`validate_only=true`, `validation_kind="static_state"`, `phase="drilling"`
request per saved vector. It retains exact request/guard identity, one-state
joint/sample attribution, corridor/contact/warning fields and native FK.
Admissibility is unchanged residual/bounds plus a trustworthy authoritative
phase-static acceptance only. Generic contacts and native FK are diagnostic;
missing, stale or mismatched replies fail closed as `INCONCLUSIVE`. Static
setup avoids the raw joint stream and Task Home transition; normal transition
callers retain their existing behavior.

Corrective runtime r1 stopped before a candidate after legacy ordinary
scene-acknowledgement issued an unchanged-current-state raw **simulation**
request and failed 31-versus-zero readback; no hardware or candidate action
followed. r2 stopped before a candidate because r4 has no persisted Task Home.
r3 stopped before a candidate because the normal guide-ID lookup rejected the
intentionally deferred static audit. The narrow final repair permits only that
exact `RuntimeAcknowledgementDeferred`/`Deferred` audit when `static_only=True`,
while still requiring the same approved, successfully published guide records.
Focused checks (compile, launcher/matrix syntax, focused P3/bridge/config/
recovery/trajectory tests and diff hygiene) pass: **79 passed**; Graphify is
refreshed.

All three corrective attempts cleaned up but emitted no new endpoint JSON or
candidate response. Corrected phase-static accepted/rejected/unknown counts,
rejection reasons, policy-warning versus housing-clear status, native evidence
and attributable screenshots are **not measured**. Corrected P3 is
**INCONCLUSIVE**. The static-runtime causal retry ceiling is exhausted: do not
launch a fourth r4-only batch without an explicit operator ceiling exception.
P4 remains not authorized.

**2026-09-16 completion update — fourth r4-only static batch and retained-evidence
correction:** The operator then expressly granted the one fourth fresh
revalidation batch after the deferred-audit guide-ID repair. It evaluated no
new seeds or IK: only the same 21 saved J1–J5 vectors from immutable input SHA
`8853f5208a87368d2611fd9c0a9737fe6b73b4da43de6851f4a428adee3f734c` against
locked Gate-A r4 SHA
`6235772e2d14d74b5417d42ed8a5e0cc160df82c77efd3014f589dd264113d83`.
The fresh raw artifact is
`c1-p3-fdi31-20260916-r4-static-revalidation-r4/endpoint_candidates.json`
(SHA `d5a3ef8857b518a293d1ed7c8a9c750d0bfe0922110150242c4a4107729acd4f`).
It contains 21 command-successful, unique/increasing (1–21), drilling,
`validate_only`, `static_state` replies with matching task/policy/session IDs,
31/31 scene objects and one requested/starting/evaluated state each.

The raw native guard accepted all 21, but the original runner treated all as
inconclusive because C++ `collision_guard` writes status doubles with
`std::setprecision(12)` and the Python attribution check required bit-exact
joint echoes. The source now accepts only that formatter-bounded echo
(`rel_tol=1e-12`, `abs_tol=5e-13`) while retaining all identity, policy, scene
and single-sample checks. The maximum observed echo delta is
`4.875266856885219e-13`. The new companion evidence
`endpoint_candidates.corrected_static_attribution.json` (SHA
`ec6ad4febcf202de3469303f53ceb4d8056f14d2d6e03272a467ba5938fce362`)
preserves every raw request, response, native FK and generic diagnostic and
records zero new native queries/IK calls. It correctly classifies **21
accepted, 0 rejected, 0 inconclusive and 21 admissible**.

Every generic-static diagnostic still rejects the explicit configuration for
`[Step 5C] DENTO Final Printable Template`↔`pneumatic_spindle-Copy` and
target-tooth↔`burr`; those contacts are evidence, not phase-static vetoes. The
authoritative guard accepts all 21 with an explicit configured, non-rotating
template/spindle contact warning at `0.326643468686`–`0.406108573858 mm`, below
its `0.500000 mm` simulation limit; burr-to-task contact is explicitly
suppressed for exploratory simulation. Thus no candidate is literally
guide/housing-clear relative to the final template, while native self,
unrelated-world and corridor checks pass for all 21. Residuals remain
`0.0003391622610791675`–`0.14985054830164712 mm`; axis residuals remain
`0.00000845192788808014`–`0.048384536734871954°`; bounds and native FK pass
for all 21. No image is claimed because the static-only run applied or displayed
no candidate state.

Focused compilation/pytest/diff checks pass **80 tests**, and the required
Graphify overlay refresh completed. The owned fourth stack is torn down; a
final container process inventory found no P3 launcher, Slicer, launch or
guard process. This establishes the corrected static endpoint **PASS** and
conditionally admits P4 only. P4 is still NOT RUN and needs separate operator
authorization; no fifth static batch, planning, motion/hardware action or
invariant/policy change is authorized.

**2026-09-16 P4/P5 completion update:** The operator later gave explicit
authority for bounded P4 and P5 diagnostic work while retaining the frozen
r4/case/task/tool/base/limit/tolerance/collision policy and prohibitions on
applied motion, hardware, powered spindle and patient action. P4's new
`c1-p4-fdi31-20260916-r4/insertion_branches.json` (SHA-256
`3cc1759d1dc5042748d729d5e2a1ae784a94a60d33cb7c8350695b321492bc72`)
records six complete, diagnostic-only Entry-to-Target witnesses. P5's new
`c1-p5-fdi31-20260916-r4/approach_branches.json` (SHA-256
`6455a52eb170ca304f33bf1b4e76bcb583bc552cc5991971fa3e9593546b7f9b`)
is `SAMPLED_PASS`: one fresh monitored simulation start, P4 source candidate
6, one five-second current-RRTConnect Stage-1 request, a complete Stage 2 and
one P4 Entry join. It retains 222 strictly increasing, unique,
`validate_only` requests (one static, 208 Stage-1, 12 Stage-2 and one join),
all accepted with correlated task/scene/policy/session evidence. Stage 2's
native FK endpoint residual is `0.0004285879962906579 mm` and
`0.0002018339679783406°`; the raw stream was false before/after and native
positions stayed unchanged. Its existing Cartesian request returned no native
points, then the existing bounded position-axis continuity fallback completed
the fixed-axis diagnostic line; no OMPL/configuration change was made.

This reaches P5 only. It does not override the retained P3 guide-warning
interpretation, prove physical seating or housing clearance, or authorize P6,
P7, insertion preview, withdrawal/Home, repeat/full cycle, another tooth,
hardware, spindle or patient work. The next action is a separately authorized
integration/physical-review decision, not an automatic follow-on.

**2026-09-17 operator pause and GUI-verification handoff:** The operator has
now explicitly paused Campaign 1 at P5 and redirected the active work to
normal-window operator workflow verification before any further gate work.
This supersedes only the previous generic “next integration decision” routing;
it preserves every Gate-A/P3/P4/P5 result and hash at its recorded evidence
level.

The key distinction is now part of acceptance: locked r4 did not exercise the
Assisted Trajectory Generation button. Its construction runner inserted the
saved Step-4A 15 September Entry/Target coordinates and tagged the resulting
line `SavedStep4A15Sept`. The P5 runner opened that prepared case, activated the
existing verified `PreparedBranch` by production logic, loaded the robot, then
entered a diagnostic-only runtime branch before the ordinary Connect/Task
Home/workspace path. It intentionally created an ephemeral task identity from
the fresh monitored simulation start and never saved/applied Task Home,
generated workspace, previewed, or applied motion. Consequently the automated
record is not operator evidence that the normal GUI works.

**Operator-intent clarification:** By “planner fix,” the operator expected a
headless Slicer run of the same production sequence an operator follows—not a
special branch that starts from a prepared case and calls internal services
around failed GUI gates. The P3/P4/P5 computations are real native
IK/FK/MoveIt/guard work, not mocked façade returns, but their demonstrated
integration is exact-r4 and diagnostic-harness-specific. P5 itself ends at the
P4 Entry witness; P4 separately supplies the Entry-to-Target witnesses. Their
compatibility is useful bounded evidence, but it is not one uninterrupted
GUI-created, executable start-to-Target plan and must not be reported as
“Step 6.5 reached Target.”

The guided task reuses `VERIFY-LEARN-01` and has two non-interchangeable
tracks:

- **Locked-r4 inspection:** open only
  `c1-gatea-fdi31-20260915-r4/FDI31-step5c.dentocase`; do not delete,
  regenerate, unlock or move its trajectory/base/guide. Verify the saved FDI31
  Entry/Target line in oblique MPR, opened-mouth Case Foundation, support and
  guide/template registration, active registry slot, `PreparedBranch`
  activation, offline robot display and Manual Simulation Base state. Assisted
  generation is expected to be disabled because the target already has a
  trajectory and existing plans are never overwritten.
- **Assisted-generation/operator workflow:** use a fresh or disposable-copy
  case with no trajectory for the selected target. Require Reviewed
  segmentation, selected target, current Case Foundation, a unique non-empty
  `HIGH`-confidence tooth↔pulp association, the requested one/two crown Entry
  points and explicit oblique-MPR correction/approval of every generated line.
  Continue 4B→4C→5A→5B→5C→6 only while the preceding geometry is visibly
  registered and current. A detached trajectory/guide, stale status, ambiguous
  pulp association or save/reopen mismatch is the first failure and stops the
  lane.

Acceptance for this pause is an operator-readable record containing the exact
case/copy identity, GUI mode, visible status text at each checkpoint,
screenshots, first failure or completed boundary, save/reopen result, and a
mapping to the responsible existing task owner. Automated checks may be used
only as focused discriminators under the verification protocol; they cannot
substitute for the normal-window observation. Return to the P-series requires
a coordinator reconciliation that explicitly states whether P5 remains the
resume anchor and which next gate is authorized. There is no automatic P3–P5
rerun or P6 entry.

**2026-09-17 bounded recovery closeout:** The operator stopped the extended
analysis because the available account quota was nearly exhausted and directed
the next session to implement the preserved findings rather than repeat the
audit. Read-only reconciliation classified the current work as follows:

- **Confirmed from saved package state:** `dentobot-case-15sept.dentocase`
  retains both the untransformed closed-source FDI31 display and the
  jaw-transform-parented moving-lower FDI31 display as visible. The resulting
  detached tooth is a restore/display-ownership defect. Preserve both data
  sources; the correction belongs at the shared visibility transition, not in
  ad-hoc target-selection cleanup.
- **Mechanism confirmed; runtime discriminator missing:** assisted placement
  reaches `startAssistedTrajectoryEntryPlacement`, calls `StartPlaceMode(0)`,
  and raises when the active markup ID or placement-valid state is wrong. No
  retained traceback/telemetry distinguishes those two postconditions. The
  first implementation increment must add that bounded evidence and fix the
  demonstrated shared native-state failure only.
- **Validation working but recovery unproved:** the FDI21 warning correctly
  rejects reuse of an FDI31-owned assisted-entry node. Target switching must
  leave placement mode and replace/rebind stale target-owned state while
  retaining this provenance guard.
- **Diagnostic traceability defect:** P5 Stage-2 edge 1 and its final P4 Entry
  join reuse one request ID. Distinct sequence numbers, vectors and responses
  preserve the saved result, but future IDs must be globally unique.
- **Acceptance boundary:** corrected P3, P4 and P5 remain useful diagnostic
  evidence. P5 does not prove normal Task Home/workspace/task confirmation,
  continuous swept-volume collision checking, literal housing clearance,
  physical fit, or operator-visible robot/anatomy parity. P5 operator
  verification therefore remains blocked.

Three earlier read-only evidence workers completed useful manual-workflow,
technical P3–P5 and artifact-inventory summaries. A fresh independent Sol
reviewer then terminated before substantive review at the account usage limit.
No worker was resumed, no missing review was recreated, and no worker output is
promoted to acceptance without coordinator reconciliation. The canonical
detail is Recovery Report Section AW and the 2026-09-17 logbook.

The operator accepted the causal review and assigned Astra architecture and Luna
Max implementation/evidence/documentation ownership. Reuse
`S6-REUSABLE-CASE-SETUP`, `S6-LIVE-01..04` and their existing upstream P0
dependencies. The complete bounded contract, write allowlist, gate acceptance,
runtime-approval boundary, exact Luna prompts and R1 report specification are in
[FDI31 Campaign 1](diagnostics/archive/step6/FDI31_PLANNER_RECOVERY_CAMPAIGN_1.md).

This supersedes earlier assertions that external geometry correction is the only
next path. The r13/r14 evidence establishes tested collisions, not exhaustive
infeasibility. Campaign 1 is P0 baseline, P1 input/scene audit with P2 supporting
instrumentation, P3 bounded endpoint and conditional P4 insertion, then Astra
review. P5–P7 are provisional later phases. On 2026-09-14 the operator
approved P1/P2 only. P1's saved-input/machine checks are PASS, but P1 overall
scene correctness and operator review are INCOMPLETE. P2 remains
`INCONCLUSIVE`: the initial missing-runtime condition was recovered once under
the later explicit cleanup authorization, and the final bounded packet now
contains two native diagnostic reconstructions with separate static and
transition records. The final scene acknowledgement reconciles 31/31 IDs,
poses/bounds and policy; the earlier `expected 31, observed 0` result remains
preserved historical evidence. The exact seven conflicting DentoBot simulation
processes were verified and stopped with SIGINT, one coherent simulation-only
stack reached ready on domain 73, and that launch-owned stack was then cleaned
up. The canonical final evidence is `c1-p1p2-recheck-20260914-r6`, with the
earlier attempts retained; no P3/P4 or motion was started. The three-failure
ceiling and all frozen case/task/tool/policy invariants remain. The corrected
handoff is now proven through Slicer entry, TCP/spindle FK pairing passes, and
burr-transform alias repair is now source-repaired and unit-verified. Native
verification of that repair was not completed because the shared container
exited 143 during a malformed continuation command and the standing boundary
excludes a restart. Do not infer operator review, input/geometry acceptance or
full-cycle acceptance from diagnostics, runner/test PASS markers, generated
flags or execution approval.

**2026-09-14 source-only handoff diagnosis:** The approved final2 stack log
proves simulation services initialized, but does not preserve the wrapper's
readiness return code/parser result or a Slicer-launch request. The cause is
therefore unproven. The existing launcher now delegates its unchanged
simulation/readiness/cleanup flow to
`Workspace/scripts/dentobot-simulation-slicer-handoff.bash`, which records
stage/reason markers and preserves the initiating diagnostic status. Local
stub tests pass for ready handoff, readiness failure and diagnostic-failure
cleanup. This historical source-only boundary was followed by the later
explicitly authorized bounded recheck: the first corrected invocation exposed
the `--no-main-window` Slicer-entry defect, and the final two attempts reached
Slicer and produced the current native packet. A subsequent source-only alias
repair passed focused tests, but native verification was blocked when the
shared container exited 143 during a malformed continuation command. This
source-only/native-launch history is superseded by the retained final packet
below; keep all P1 review and downstream gates open.

**2026-09-15 current disposition:** The retained final packet is the bounded
native P2 diagnostic/evidence result: P1 saved-input/machine checks are PASS
for completed checks, P1 overall scene correctness and operator review are
INCOMPLETE, and P2 bounded diagnostic evidence is PASS with campaign gate
`USER_REVIEW_REQUIRED`. It separates phase-aware static rejection of both
endpoints (final printable template ↔ spindle), generic static contacts
(including FDI31 tooth ↔ spindle and tooth ↔ burr), and Home-to-endpoint
corridor rejection. It also records trusted 31/31 scene acknowledgement and
TCP/spindle/burr FK evidence. The earlier zero-object, launcher and
container-exit results remain historical attempts; they do not make the
retained packet inconclusive. Operator acceptance of the 15 selections,
scene, geometry and contact interpretation remains unrecorded, and no P3/P4
or full-cycle acceptance follows.

**2026-09-15 Section-W source-only recapture correction:** The rejected
display recaptures remain historical and are not faithful state/geometry
evidence. The retained review driver now separates the endpoint from the
Home-to-endpoint sample, reconstructs prepared world-RAS display copies,
checks geometry fingerprints/bounds, compares displayed TCP/burr/spindle link
frames with saved endpoint native FK, and verifies the same review robot nodes
and transforms across save/reopen. Production transient robot persistence and
all collision/native policy remain unchanged. Ten focused pure tests pass.
One approved endpoint-only Slicer session loaded the retained MRB but stopped
before capture because this runtime lacks
`vtkMRMLModelDisplayNode.SetPropertiesLabelVisibility`; its error manifest is
preserved separately and contains no image or review MRB. Endpoint parity was
not reached, so this is a runtime compatibility stop rather than an endpoint
geometry/FK parity failure. The driver consumes a future explicitly saved
evaluated-sample FK record but does not substitute endpoint/offline FK. The
transition image remains `NOT_RUN` until the saved packet contains native FK
matrices for evaluated sample 1/134. No second display runtime is authorized
without a new explicit approval.
Operator scene review and acceptance remain open.

**2026-09-15 endpoint-only repair continuation:** The operator later
authorized a bounded rerun and source fixes for Slicer-session blockers. Two
minimal compatibility repairs were pure-verified (`12 focused tests`): an
optional display-label API guard and a model parent-transform world-matrix
fallback. The third and final scoped display attempt reached the parity gate
and failed closed. The final printable template matched exactly, but the
prepared FDI31 target fingerprint differed and its maximum bound error was
`40.74010467529297 mm` versus the `0.05 mm` tolerance. Robot mesh/link
transforms matched; native-vs-offline FK matched for TCP, burr and spindle;
displayed burr/spindle matched native FK; displayed TCP remained unavailable
because the seven displayed models contain no TCP model. Save/reopen was not
reached. The repair2 manifest and prior compatibility-error manifests are
preserved. Endpoint review is `BLOCKED`, transition is `NOT_RUN`, no geometry
or policy was changed, and the display-runtime retry ceiling is reached.
P1/P2 campaign acceptance and operator scene review remain open.

**2026-09-15 revised endpoint parity repair:** The operator explicitly
authorized source-only correction and focused testing for the two evidenced
repair2 defects, followed by at most three targeted endpoint-only offline
Slicer attempts. The driver now reuses the native Case Foundation jaw-opening
transform exactly once and the native triangle-filter semantics for the
display-only target copy; it also derives the meshless canonical
`dentobot_drill_tcp` from the actual displayed `pneumatic_spindle-Copy` mesh,
its visual-origin offset and the retained URDF fixed relation, with loaded
robot-profile identity matching. The focused suite passes 18 tests and the
container-mounted source hash matches the host. The repair3 pre-execution
command/output location is recorded in report Section AE. This remains an
endpoint-review evidence task only: transition is NOT_RUN, operator/P1/P2
acceptance is open, and P3/P4 plus geometry/policy/hardware actions remain
unauthorized.

**2026-09-15 endpoint parity repair result:** The final authorized repair5
attempt passed the endpoint machine parity gate. It verified native target and
template fingerprints/bounds, exactly one Case Foundation jaw preparation,
robot-description identity, displayed seven-link/model transforms, derived
meshless TCP/burr/spindle FK, and unchanged pose across save/reopen. The
separate review MRB, JSON packet and two nonblank endpoint images are recorded
in recovery report Section AH. The transition image remains `NOT_RUN` because
saved native sample-1/134 FK is unavailable. Visual label/scale review and
operator acceptance remain open; this does not close P1 overall scene review,
change the retained native P2 status, or authorize P3/P4.

**2026-09-15 operator visual review:** The operator accepts the repair5 endpoint
screenshots and requests a next-phase Luna prompt. The visual-review blocker
is closed for this retained endpoint only. Reconcile remaining P1 input/scene
decisions before conditional P3 under the existing Campaign-1 contract;
historical transition imagery is not a static-endpoint prerequisite. No blanket
input acceptance, runtime execution, or P4 approval is recorded. See report AI.

**2026-09-15 Step-4A–5B current-session delta:** Under
`S6-REUSABLE-CASE-SETUP`, the operator now specifically confirms FDI42/41 and
FDI33/32 as the four Step-4B support neighbours but reports a duplicate
closed/opened FDI31 display, oblique-looking Step-4C/5A planes and a legacy
1.5-mm Step-5B guide-hole failure. Report AK records read-only source/package
and r7 plane metrics. New-case dock/5A defaults and the Step-5B preflight/status
defect are corrected source-only with 24 focused pure tests passing; frozen
source/r7 geometry and policy remain unchanged. The live plane/display state
is not numerically captured, so P1 overall remains INCOMPLETE and conditional
P3 is not entered. `W4B-P2-SUPPORT-AUTO`, `W5-U-01`, `W5-U-05` retain their
separate priority/physical/UX acceptance slices; this manual support review
does not close those tasks.

**2026-09-15 separate test-case readback:** The operator deleted a perceived
FDI31 artifact and saved `dentobot-case-15sept.dentocase` for testing. Report
AL records its checksum and integrity: the active FDI31 registry has no target
or trajectory, but the MRML Step-4A target ID/ROI remain and FDI31 is saved
3D-visible in both the closed source and opened moving-lower segmentation.
The source mask and derived segment-file bytes match the immutable 13Sept
case; repeated Subject Hierarchy virtual entries increased across segments,
not just FDI31. This is a separate partial test fixture without 4C/5A planes,
final template or PreparedBranch. It neither replaces the frozen Campaign-1
input nor closes P1 scene review; no app/runtime test or P3/P4 was run.

**2026-09-15 clarified fixture and saved Step-5B scene:** The operator intends
15Sept as a reusable open-mouth + placed-base foundation to avoid repeating
landmarks/base placement and identifies `FDI31/2026-09-15-Scene.mrb` as the
separate Step-5B snapshot. Report AM verifies identical source segmentation,
jaw-opening and base matrices between the two; the base placement is saved but
`robotBaseMountLocked=False`, so 15Sept is not an eligible `FoundationOnly`
case. The Step-5B MRB has all four confirmed supports, four 1.0-mm robot-dock
bores, a 4-mm Step-5A plane, current shell, no final template, and the saved
1.5-mm trajectory-guide hole. Its source FDI31 is hidden in 3D and opened
moving-lower FDI31 visible, unlike the separate 15Sept bundle. The Step-5A
plane origin agrees with Entry+4 mm, but its displayed world normal is
42.454° from its saved crown-cap fit normal; the difference is the jaw-opening
rotation. Shared `CaseFoundationLogicMixin` reparenting preserved markup
positions but not plane normals. A minimal source-only repair restores the
plane world normal across reparent; an old-source focused stub regression
failed, then passed, and the focused file passed 25/25. The saved MRB was not
rewritten or reopened in Slicer, so runtime/world-frame parity and operator
scene correctness remain open. P1 overall INCOMPLETE; P2 retained PASS with
USER_REVIEW_REQUIRED; P3/P4 paused.

## FDI11 / Stage 3 — paused pending workflow integrity

- **ID:** `S6-FDI11-DEPTH`; **Priority:** Unprioritized; related P0
  acceptance stays under `S6-LIVE-01..05`.
- **Latest evidence:** The recorded -4 mm in-memory local-Z trial reaches the
  6 mm Stage-3 endpoint kinematically and records configured housing/template
  warnings, then rejects non-rotating spindle housing contact with adjacent
  FDI21 at the final drilling waypoint. Complete preview, axial withdrawal,
  monitored Home and the fresh repeat cycle have not passed.
- **Case:** The reviewed source package remains unchanged:
  `data/Slicer_Saved/SampleStudy1/FDI11/dentobot-case-step6x4x2.dentocase`.
  Its source trajectory is 7.977207292891484 mm; the recorded simulation cap
  is 6 mm, with no claim that the capped endpoint is pulp.
- **Policy evidence:** Bounded configured housing/guide contact and 0.1 mm
  burr/guide clearance are case-specific recorded authorizations, not defaults.
  Adjacent-anatomy contact remains forbidden. This cleanup does not change
  dimensions, base, depth, margins, guards or endpoint rules.
- **References:** `logbook/2026-09-08.md` hard-constraint checkpoint;
  `logbook/2026-09-09.md` exact-case evidence; retained views/state at
  `data/dentobot-runs/fdi21-blocker-20260909/`. Older fractions and former
  2 mm burr/x4 results remain historical evidence only.
- **Next:** After PreparedBranch/main-workflow integrity acceptance, reconcile
  current reviewed case/tool/guide identity against the retained blocker and
  propose the smallest applicable Stage-3 check. Do not automatically rerun,
  relocate the base or relax collision rules from this entry.

## Stale Case Foundation package reopen — 2026-09-24

- **Owner:** `S6-REUSABLE-CASE-SETUP`, overlapping `S3-P0-DENTAL-SEMANTICS` candidate-induced Step 3A invalidation.
- **Operator observation:** Reopening `SEPT24/pulp-testing-fdi11.dentocase` failed in `_openCaseBundle` because UI hydration called `setRobotBaseMountLocked(..., True)` and raised `The committed Case Foundation pose is stale.`
- **Correction:** Robot-placement UI refresh only synchronizes saved lock interaction state; explicit base-lock action and downstream pose/planning gates retain their validation. A stale case should load for Step 3A repair, without promoting its pose or base.
- **Acceptance:** Source compile/diff check passed. Tarun then reported “works” with a normal-window screenshot after reopening the same case; the subsequent FDI11 Step 4A trajectory is visible, so the prior load rollback is resolved in that session. The screenshot does not audit every saved base/Step 6 gate or establish anatomical trajectory acceptance.

## Assisted access endpoint — 2026-09-07

**30 September operator deferral:** Keep the synthetic assisted-root native test; backlog its stale Case Foundation setup repair for a separate bounded slice. The current shell integration uses only the reviewed case fixture and does not claim this synthetic regression passing. Retain endpoint, focus, node-lineage, duplicate-generation and MRB persistence assertions; no production prerequisite bypass. See backlog and today's logbook.

- **ID:** `S4A-PULP-ENDPOINT`; **Priority:** 0; **State:** Source and focused automated verification passed (2026-09-10); exact FDI31 normal-window anatomical review remains pending.
- **Operator observation:** The displayed FDI31 assisted target appears inside the pulp mask in 2D but does not contact the displayed pulp surface in 3D. The operator requires the mismatch fixed now, not deferred.
- **Exact-case finding:** The 4.23 mm line in `FDI31-step5c.mrb` belongs to a saved three-line set and has no current assisted-generation provenance; the Placement menu describes the creation action, not an existing line's origin. Slice projection also rendered off-slice Entry/Target glyphs over the mask. The saved Target is at the native voxel boundary, while the smoothed closed surface can diverge from that boundary.
- **Corrected contract:** New single/dual assisted generation must prove a shared interval between the selected tooth's FDI-matched binary pulp mask and its displayed 3D surface, preserve Entry and direction, and atomically set Target to the first point contained by both (the farther entry boundary). Record both boundary points and their offset. Reject a native/display miss or non-overlap. Off-slice trajectory projection is disabled. Existing/manual trajectories and Step 6 policy remain unchanged.
- **Verification:** Final diff check and scoped pycompile passed; pure endpoint test passed 1/1; focused Slicer target emitted `DENTOBOT_ASSISTED_PULP_PASS` and `DENTOBOT_STEP4A_P0_PASS`, exited 0, and left no Slicer process. Evidence: `/tmp/dentobot-verification/step4a-p0-20260910/result.json`.
- **Next:** Reload the module, deliberately delete the legacy FDI31 set, generate one current assisted line, and record normal-window 3D surface contact plus non-projecting 2D slice behavior before anatomical approval.
- **2026-09-24 FDI11 headless diagnosis:** The existing automated crown-cap Entry method reproduced the voxel/surface miss on `SEPT24/pulp-testing-fdi11.dentocase`: Entry `[-87.644, -33.814, 56.004]` RAS, 52 candidate voxels, native first hit `[-88.091, -37.750, 62.412]`, 0.392 mm outside the displayed default-smoothed surface, zero line hits. Regenerating the same candidate surface in memory with smoothing factor 0 produced eight line hits. The input archive predates the operator’s Step 3A rerun, so a full production generation from it stops at stale Case Foundation before geometry. A persisted candidate-specific representation correction and exact production rerun remain open; do not relax the shared-contact gate or claim anatomical approval.
- **2026-09-24 normal-window continuation:** Tarun reports the case now opens and screenshot shows one created FDI11 assisted trajectory (9.74 mm; success dialog reports maximum display-surface offset 1.14 mm). This demonstrates generation for his current Entry but does not explain why that Entry succeeded while the earlier automated crown-cap line missed, nor verify contact in trajectory-aligned MPR. Anatomical review remains open.

## P0 dental semantic normalization and pulp-to-tooth association — 2026-09-14

- **ID:** `S3-P0-DENTAL-SEMANTICS`; **Priority:** 0.
- **State:** Active implementation/integration. The source trace, bounded
  implementation plan, pure A-H semantic core, MRML registry integration and
  target-specific planning gate are implemented; integrated Slicer runtime,
  geometry, save/reopen and downstream full-workflow evidence remain open.
- **Operator note:** The attached `dentonote` requests a reliable semantic
  bridge between TotalSegmentator output and DentoWorkflow target/planning
  logic. The operator specifically asked for inspection and a detailed plan
  before any large refactor.
- **Triage:** Active investigation/design pending implementation. Keep this
  as one P0 owner. Do not create an FDI11-only special case or a second case
  database. Existing `S4A-PULP-ENDPOINT` retains displayed/native endpoint
  geometry; `S6-REUSABLE-CASE-SETUP` retains case/campaign sequencing and
  save/reopen acceptance.

### Source trace and current evidence

1. `Inference/src/dentobot_inference/segmentation.py` invokes
   `totalsegmentator(..., task="teeth", ml=True)` and reads the installed
   `class_map["teeth"]`. It preserves the actual raw `{id, name}` pairs in
   `result["labels"]`; `validate_segmentation_output()` checks geometry,
   integer labels, unknown IDs and per-label counts. Source inspection found
   no `label_value == 111` or `pulp_label_id - 100` assumption in the
   inference backend.
2. `widget_case_backend.py` imports the returned multilabel NIfTI into one
   Slicer segmentation. It validates label IDs/counts and builds a color table
   whose segment names come directly from the backend report. The importer
   does not independently validate that imported names are semantically
   equivalent to the report, and it does not create tooth/pulp relations.
3. `logic_segmentation.py` stores `SegmentMetricsJson` with segment ID, raw
   label ID, raw name, voxel count and volume. `describeSegmentForReview()`
   currently classifies by name substrings and parses `_fdi<digits>`; for a
   pulp suffix shaped like `1<FDI>` it strips the first digit. This is a
   presentation-compatible legacy grammar, not a verified backend semantic
   contract. `getSegmentationReviewRecords()` currently rebuilds records from
   the current Slicer display name.
4. `logic_lineage.py` treats review records with category `Teeth` as target
   teeth and validates a target by segment ID plus that derived category. It
   does not require canonical FDI provenance, non-empty geometry, or a
   validated pulp relation.
5. `logic_workflow.py` obtains assisted pulp by filtering review records for
   category `Pulp and root canals` and equal derived `fdiNumber`, then uses
   only that pulp mask/surface for the existing first-shared native/displayed
   endpoint calculation. It has no target-to-pulp spatial association gate.
6. `DENTOCaseBundle` persists the MRML scene inside `scene/case.mrb`, and the
   current segmentation node's `SegmentMetricsJson` therefore survives in the
   MRB. `workflow/lineage.json` currently records only the segmentation node
   inventory/segment count, so a semantic registry is not independently
   checked on reload.
7. Read-only inspection of
   `data/Slicer_Saved/SampleStudy1/FDI11/dentobot-case-step5b.dentocase` and
   `dentobot-case-13sept.dentocase` found 54 segment names, 18 pulp names,
   `upper_right_central_incisor_fdi11` at label 11, and no `*_pulp_fdi11*` or
   `*_pulp_fdi21*` entry. The current exact evidence therefore classifies
   FDI11/FDI21 missing pulp as an input-data failure. It does not prove that a
   different visual FDI11 report was not misclassified by TotalSegmentator,
   its class map, Slicer import, or our parser.

**Unresolved origin boundary:** The source audit rules out the suspected
hard-coded label arithmetic in the inference backend. A read-only inspection
now captures the installed 77-entry class map with fingerprint
`57c95824f888749b879511e06e4590b2029cdb35f1791b4a050ecebc35d9b328`; the
retained report, NIfTI and saved imported `.seg.nrrd` agree on the detected
54-label subset, including raw FDI31 tooth/pulp entries. A fresh current-
revision Slicer import has not yet run, so no claim about a model-level FDI11
identity error is made from the retained package.

### Smallest robust architecture

Keep `SegmentationLogicMixin` as the existing MRML-facing owner and add one
small pure helper module, `dentobot_workflow/dental_semantics.py`, only for
plain-record normalization, component association and validation math. Do not
add a generic registry service, a second database, a new case archive member,
or a new workflow façade.

The import path becomes:

```text
backend report/class map (raw source facts)
  -> canonical segment records in existing SegmentMetricsJson
  -> target-specific pulp association/validation
  -> target selection and assisted endpoint
```

The raw source name, raw label ID and terminology remain audit evidence. A
versioned backend adapter may use the report's source map to identify raw
structure kind and an optional FDI hint, but no downstream planner may parse a
Slicer display name or infer FDI from an arithmetic label relationship.
Unknown or changed backend naming becomes `UNRESOLVED`/reviewable input, not a
guess. Legacy name parsing is retained only as an explicit migration fallback
and is never sufficient by itself for pulp-dependent planning.

Each canonical record must carry, at minimum:

```text
segmentId                    MRML segment identity
sourceLabelId/sourceName     raw audit provenance only
structureType                TOOTH, PULP, or another explicit type
canonicalName                Tooth_FDI11 / Pulp_FDI11 when known
fdiNumber                    optional canonical FDI
parentToothSegmentIds       zero/one/many source segment IDs for pulp
associationMethod            source-hint, spatial, or manual-confirmed
associationConfidence        HIGH, MEDIUM, or null for failed states
validationState              VALID, AMBIGUOUS, MISSING, INVALID,
                              or MANUALLY_CONFIRMED
associationEvidence          deterministic metrics and runner-up details
```

Canonical records are stored by extending the existing
`DENTOBOT.SegmentMetricsJson`; node attributes carry the semantic schema
version, overall status and a deterministic semantic fingerprint. The
fingerprint includes segment IDs/label IDs and canonical relations, but not
display-only raw names, so a backend naming change cannot break an already
validated case. The full registry stays in MRML/MRB; `workflow/lineage.json`
adds only the semantic version/status/fingerprint to its existing segmentation
node record for save/reload integrity.

### Target-specific association algorithm

1. At import or migration, register every tooth candidate and every pulp
   candidate/component as existing geometry. Build tooth records globally, but
   defer expensive pulp-parent decisions until a target is selected.
2. For the selected canonical tooth, require a unique valid FDI, non-empty
   binary labelmap and usable closed surface. Enumerate every non-empty pulp
   segment in the segmentation and split its binary mask into deterministic
   connected components without creating a new anatomical segment.
3. Transform occupied component voxel centers and both tooth/pulp surfaces to
   the same world-RAS millimetre frame. For every component/tooth pair record
   minimum and robust central surface distances, centroid/bounds relation,
   enclosure or inside fraction against the closed tooth surface, and the
   fraction of component samples for which that tooth is the nearest
   consistent tooth. Voxel intersection is supporting evidence only.
4. Rank candidates using the combined evidence and retain the best and
   second-best candidate plus all raw metrics. Do not use nearest centroid as
   the decision by itself. A raw FDI hint may corroborate the result but cannot
   override a geometric disagreement.
5. Group fragmented components only when every component is non-empty,
   geometrically consistent with the same tooth and does not create a
   duplicate/conflicting parent. If components split their best association
   across adjacent teeth, or if the evidence disagrees without a safe margin,
   return `AMBIGUOUS`/`INVALID` and do not merge them.
6. Calibrate any numeric score/margin against the A–H fixtures before using
   it as a confidence band. Until that calibration exists, preserve raw
   metrics and fail closed rather than inventing an anatomical threshold.

Confidence and failure behavior is:

| Result | Meaning and workflow behavior |
|---|---|
| `HIGH` + `VALID` | Unique target tooth/pulp relation; eligible for the current pulp-dependent gate, still retaining ordinary manual verification. |
| `MEDIUM` | Spatially plausible but lower margin or source-hint disagreement; eligible only when all validation rules pass and the required review/confirmation transitions it to `MANUALLY_CONFIRMED`. |
| `AMBIGUOUS` | Competing adjacent candidate, inconsistent components, or unresolved top-two margin; block automatic pulp-dependent planning. |
| `MISSING` | No non-empty pulp candidate for the target; block pulp-dependent planning and preserve the target tooth for non-pulp review. |
| `INVALID` | Malformed geometry/metadata, duplicate canonical parent, non-finite metrics, or contradiction that cannot be safely resolved; block and expose diagnostics. |
| `MANUALLY_CONFIRMED` | Explicit review accepted a non-HIGH result without changing source geometry; preserve who/when/evidence and keep the trajectory's manual-verification flag. |

No state creates missing pulp. A target may proceed into the existing S4A
shared native/displayed-surface endpoint code only after the selected tooth,
one or more existing pulp components, and their spatial relation pass the
canonical validation gate. Step 6 remains downstream and unchanged.

### Implementation order and owned files

1. **Evidence adapter:** capture of the installed TotalSegmentator
   `class_map["teeth"]`, retained raw report, NIfTI IDs, imported Slicer IDs/
   names and saved `.seg.nrrd` metadata is complete as read-only evidence;
   fresh current-revision import remains pending.
2. **Pure semantics:** implemented the plain-record normalizer, deterministic
   component metrics/ranking, confidence states and A-H tests in one focused
   semantic test file. The pure layer has no Slicer dependency.
3. **MRML import/review:** `logic_segmentation.py` now builds/reads the
   canonical registry after validated import, keeps raw fields for audit,
   projects canonical records, and leaves the old name parser as a
   migration-only fallback.
4. **Target/planning gate:** `logic_lineage.py` and `logic_workflow.py` now
   call one canonical target-anatomy query. Existing S4A endpoint math, line
   creation and no-overwrite rules are preserved; the FDI/name pulp lookup is
   replaced by spatially associated source segment/component IDs and a
   semantic fingerprint.
5. **Persistence/migration:** update `logic_case_bundle.py` to include the
   semantic version/status/fingerprint in the existing segmentation node
   lineage record. On load, validate an existing registry against current
   segment IDs/label IDs/geometry; otherwise recover in memory, mark migration
   pending/needs-review, and write only on explicit user save. Never mutate
   mask voxels or silently rewrite a legacy case.
6. **Focused acceptance:** run the cheapest pure/static checks first, then one
   serialized Slicer save/reload test for the semantic registry. Only after
   those pass and a separate verification approval exists should a target
   packet exercise 4A–5C or Step 6. No broad Step 6 rerun is part of this
   task.

### Required acceptance cases

| Case | Fixture and expected result |
|---|---|
| A | Native FDI11 tooth plus raw FDI111 pulp hint: canonical `Tooth_FDI11` and `Pulp_FDI11`, unique spatial match, `HIGH`/`VALID`. |
| B | Pulp geometry is inside/consistent with FDI11 but raw identity is generic or absent: canonical FDI11 comes from spatial evidence, not the name. |
| C | Raw pulp hint says FDI11 while geometry favors FDI21: preserve disagreement, never let the hint override geometry; resolve only with a clear validated margin or block/review. |
| D | No labeled FDI11 pulp component: inspect the selected tooth for a dominant enclosed label-0 void. Create a separate reviewable pulp candidate only when one dominates and its voxels are unassigned; otherwise `MISSING`/review required. No endpoint before review. |
| E | Adjacent FDI11/FDI21 candidates are close or metrics conflict: `AMBIGUOUS`, no automatic planning. |
| F | One pulp is fragmented: same-tooth components may be grouped with component evidence; cross-tooth or duplicate assignments are `AMBIGUOUS`/`INVALID`. |
| G | Save, close, reopen and re-import a `.dentocase`: canonical records, relations, states and fingerprint remain identical; legacy recovery is migration-pending until explicit save. |
| H | Backend raw names/terminology change while source facts remain adaptable: target/pulp queries use canonical records and continue; an unadaptable source fails review rather than guessing. |

**Operator clarification (2026-09-24):** Acceptance case B is a required
feature, not merely a migration/parser example. If one or more detected pulp
masks/components have generic or absent FDI labels but the existing spatial
association validates them inside the selected tooth, assisted generation
must allow the requested one or two trajectories. If no pulp component is
detected/associated inside that tooth, do not generate a pulp-based line.
The later operator clarification includes existing masks of unknown source
type: an `OTHER` mask is promoted to canonical PULP only with unique HIGH
spatial association and full sampled-component enclosure in the selected
tooth. The 2026-09-24 correction additionally authorizes a derived mask from
a dominant closed label-0 void inside the target tooth. Read-only voxel
inspection of the usual 13Sept FDI11 case found 52 connected interior voxels
and a separate 3-voxel pocket; FDI21 has a dominant 52-voxel pocket and smaller
ones. The original source masks remain unchanged. A derived segment records
its tooth parent and method, invalidates prior review, and cannot feed assisted
generation until Step 2 is marked Reviewed. Occupied, open or ambiguous voids
fail closed. `S3-P0-DENTAL-SEMANTICS` owns candidate creation and association;
`S4A-PULP-ENDPOINT` owns native/displayed endpoint validation and line
construction. The parent semantic work item retains Priority 0.

### Boundaries and completion evidence

Non-goals are TotalSegmentator retraining/fine-tuning, edits to source masks,
FDI11-only heuristics, and a broad Step 6 rewrite.
Completion requires the source-map comparison, focused pure/static checks, A–F
semantic fixtures, G save/reload evidence, H naming-independence evidence, and
one explicit pulp-dependent planning gate check. A code change is not accepted
until its verification command/result is recorded in the dated logbook.

**UX correction (2026-09-24):** Candidate creation is an explicit Step 2
"Prepare Pulp Mask for Selected Tooth" action on a selected reviewed tooth.
It checks existing pulp first, creates a separate candidate only if missing,
shows the tooth and candidate together, and resets review for a new mask.
Step 4A placement checks pulp association before placing crown Entry points;
Generate creates trajectories only. The earlier create-then-error Generate
behavior and mistaken Step 3 review instruction are superseded.

**Per-run bulk extension (2026-09-24):** New segmentation runs receive an
automatic read-only audit; older loaded MRB/dentocase runs offer a manual
Step 2 Check Pulp Masks button. The selected run owns a versioned MRML report
with per-tooth outcomes, absent FDI positions, stale detection and a table
dialog. Bulk creation is one explicit action, preserving source masks and
requiring review before planning. Trusted legacy run metrics require matching
loaded segment IDs and label values. Runtime save/reopen and anatomical
acceptance remain open until verified.

**Next bounded action:** MRB and dentocase save/reopen now pass for the focused
FDI11 candidate. Inspect the Step 2 mask and report in a normal window for
Tarun's anatomical/UI verdict. Full all-tooth batch performance and
representative source-mask Case B remain open.

**Approved verification continuation (2026-09-24):** Tarun approved the
bounded save/reload check. Slicer re-audited the saved 28-row FDI11 run,
verified the 52-voxel candidate, and passed MRB save/reopen with a current
report. A first dentocase open failed post-hydration on the unrelated
`step6CaseJawTransform` stale-reason lineage because the loader passed
archive schema 2.0 to workflow-state schema 3.0 hydration. After using the
saved workflow-state version, a narrow fresh Slicer open passed and restored
all 28 rows, a current report, the 52-voxel FDI11 candidate and Needs
Correction review state. Full-batch runtime, ordinary-window anatomy/table
verdict and representative source-mask Case B remain open.

**FDI11 Step 4A parent-FDI failure (2026-09-24):** In the operator-saved
`SEPT24/pulp-testing-fdi11.dentocase`, a reviewed 52-voxel derived FDI11 pulp
candidate and FDI11 tooth are present. Step 4A displayed `A persisted pulp
association has no valid parent FDI.` The shared pure persistence helper
looked for `toothFdiNumber` on a component wrapper instead of its `selected`
child. The one-line correction and focused derived-association regression
pass. Tarun's later normal-window screenshot shows successful FDI11 assisted
trajectory generation after the correction; the independent scripted
exact-case runner was not executed while his GUI owned Slicer. The observed Step 3A re-performance
follows the existing segmentation-content fingerprint invalidation; changing
that safety policy is outside this one-line correction.

## Immediate P0 — restore truthful Step 4A smooth masks

- **ID:** `W4-U-02`; **Priority:** 0; **State:** Root-cause correction and focused automated verification passed (2026-09-10). The 2026-09-24 all-step default/control correction passes the supplied-case off/on probe; normal-window visual acceptance remains pending.
- **Operator observation:** Smooth masks do not work and must be restored now as Priority 0.
- **Finding:** The checked control returned without applying anything outside the special oblique-verification state and did not synchronize itself from the actual CBCT and segmentation display modes. It could therefore present a checked no-op in ordinary Step 4A.
- **Corrected contract:** With a complete selected trajectory, the same switch operates in ordinary Step 4A and oblique verification, using Slicer's existing scalar interpolation and closed-surface 2D representation without modifying source voxels or masks. Outside oblique verification it reflects the actual joint CBCT/mask state; oblique exit restores the captured prior modes.
- **Verification:** Focused Slicer target exercised the ordinary Step 4A handler, actual CBCT interpolation, smooth/native mask representations and endpoint persistence; it emitted `DENTOBOT_STEP4A_DISPLAY_PASS` and `DENTOBOT_STEP4A_P0_PASS` and exited 0. Evidence: `/tmp/dentobot-verification/step4a-p0-20260910/result.json`.
- **2026-09-24 operator delta and implementation:** Tarun requested smooth as the default and a permanent on/off option in the Views dialog across all steps; he deferred the `VIEW-U-01` visible verdict and advanced this task. The Views palette now shows “Smooth CBCT and masks” above its tabs, operating on source and both Case Foundation jaw displays without a trajectory prerequisite. New segmentation review defaults to smooth while saved choices remain. Native mode materializes a derived binary labelmap when an opened display contains only a closed surface, so off changes actual rendering. The reported mode follows Slicer's actual representation. Source voxels, authoritative masks, trajectory and planner policy are unchanged.
- **2026-09-24 evidence:** The supplied FDI21/31 case initially had surface-only fixed/moving displays; the old off control reported native while Slicer still rendered `Closed surface`. `/tmp/w4-u02-probe-after.log` then showed `W4_MOVING_OFF ... Binary labelmap` and exit 0. `/tmp/w4-u02-toggle.log` reported `W4_ALL_STEPS_TOGGLE_PASS` and exit 0 after source/fixed/moving mask and CBCT off/on assertions. Static compile and diff checks passed. The first matrix Step 4A run found a synthetic fixture marking smooth without creating a surface; after correcting the fixture, the second run emitted `DENTOBOT_STEP4A_DISPLAY_PASS`, then failed in assisted-endpoint Case Foundation review setup (`Review the segmentation before creating the Case Foundation`). The combined matrix run is not claimed passed; that downstream gate is outside this display correction and requires separate triage under its owning task.
- **Next:** Confirm in a normal Slicer window that the default and permanent Views control visibly change both CBCT and masks, the checked state is truthful, and oblique disable/exit restores the prior modes. The broader representative Step 4/backtracking acceptance remains part of this task.

## Immediate P0 — terminal coverage disconnects shell collar

- **ID:** `S5B-TERMINAL-COLLAR`; **Priority:** 0; **State:** Completed: approved host regression and exact FDI11 saved-loop/fresh-auto-loop preview→shell→unified builds passed, both exit 0 (2026-09-08).
- **Operator observation:** Automatic Step 5A boundary and manual backside adjustments both leave Step 5B unable to generate the shell/unified template. Screenshot reports two remaining components; target FDI11, four support teeth, terminal coverage 50%.
- **Source finding:** The bridge previously used the full boundary, then terminal half-planes clipped the completed union. This can remove both end connections and split a collar into two rails. This is a concrete failure mechanism, not yet proof of the exact screenshot's cause.
- **Implementation:** Clip and close the boundary at the existing terminal planes before collar construction. Retain the same anatomy exclusion, final coverage clipping and one-component gate. Error text no longer implies that redrawing alone necessarily resolves the failure.
- **Verification:** Old collar produced two regions; corrected collar produced one watertight region in original and rotated frames. Combined host run: 3 passed; compilation and diff check exit 0. Evidence: `/tmp/dentobot-verification/pulp-shell-20260908/`.
- **Exact-case evidence:** FDI11 `dentobot-case-step5b.dentocase`; saved and freshly regenerated automatic boundary both have 50 points, address all five teeth, and produce 3,363-point/6,028-triangle previews. Both shells have one surface region and zero invalid edges; both unified outputs have 74,988 triangles, one occupied volume region and zero invalid edges. Source package checksum unchanged; logs in the evidence directory.
- **Next:** Operator reload and normal-window build/inspection. Development defect is verified; anatomical/manufacturing and Track A acceptance remain separate.
- **Sequencing:** Operator requested completion of pulp-endpoint and P0 prompts one after another; endpoint source work precedes this correction. Approved host checks passed; runtime resources remain serialized.

## Immediate P0 baseline cleanup — retired pre-surgery workarounds

- **ID:** `S6-P0-BASELINE-CLEANUP`; **Priority:** 0; **State:** Completed source/guard scope. Source cleanup, 63 focused Python tests, native guard build, and 14-check synthetic ROS phase-guard test passed. The clean-case full-loop acceptance is owned only by `S6-LIVE-05`; this ID was removed from the pending backlog on 2026-09-23 to avoid a duplicate queue entry.
- **Reason:** The retired pre-surgery/x4 fixture exposed collision and guide-fit problems. It must not drive production exceptions or planner tuning. New baseline cases must use reviewed post-surgery/clean anatomy and a finalized Step 5C guide/tool model.
- **Implemented:** The production burr-proximity helper now returns only the selected target-tooth object. Adjacent teeth, jaw anatomy, and guide/template objects remain authoritative for collision and the research clearance margin. The façade no longer sends guide/template IDs as clearance exemptions, and the ROS bridge rejects non-empty guide-clearance exemptions.
- **Quarantined:** The historical Step 5C template-collision bypass is unavailable by default and requires the explicit process variable `DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE=1`. Session anatomy-review proxies are ignored by collision publication unless `DENTOBOT_ENABLE_HISTORICAL_ANATOMY_REVIEW=1`. Neither override is saved into a case or treated as baseline evidence.
- **Preserved:** J1–J5 canonical-TCP planning, J6-outside-planning policy, strict self/world/anatomy checks, the selected-target terminal-contact policy, endpoint/guard checks, and retained diagnostics remain unchanged.
- **Next:** Review/select one clean post-surgery case and complete its guarded approach, drilling, Return Home and repeat gate. Native guard evidence: `/tmp/dentobot-verification/cleanup-guard-20260907/`. Do not revive the retired x4 override or tune tolerances/base placement to make that fixture pass.

## Active operator interruption — Step 6A changed-target geometry

- **ID:** `S6A-CHANGED-TARGET-GEOMETRY`; **Priority:** Unprioritized (operator requests immediate cleanup); **State:** Source guard implemented; focused host verification and authorized Slicer clear/save round-trip passed; clean FDI44 end-to-end rerun remains pending.
- **Observed:** Operator completed the workflow on a different target tooth and reports FD14-like remnants attached/fused after applying the open-mouth transform. Screenshot is evidence of unexpected visible geometry; its source and actual fusion are unconfirmed.
- **Impact:** Step 6A preview and any derived planning geometry need an ownership audit before acceptance. Do not remove anatomical components based on appearance alone.
- **Evidence:** Source proxy reconstruction clears prior segments, while mandibular template display is copied separately from referenced Steps 0–5 models. The readable historical FD14 MRB contains explicit FD14 Step 5C template and Step 6 obstacle lineage. The relocated FDI44 archive was read-only audited through the authorized container path and showed FDI44 text/lineage with no FD14 strings; the authorized FD14 load → New Empty Case → save regression then reported zero FD14 hits in the saved MRML and lineage.
- **Implementation:** Target changes now clear Step 6A transient jaw/target-attached geometry before downstream deletion; authoritative segmentation changes do the same. The target-attached display builder filters models by persisted target lineage and hides/marks mismatched stale models. Restore validation now rejects mismatched trajectory/ROI/docking/template target chains, clears disposable opened-jaw proxies when deactivating a stale package, keeps mismatched source visibility suppressed, refuses to let a saved trajectory silently overwrite the active target during UI hydration, and keeps Reset reachable for stale transient refs while ROS is disconnected.
- **Verification:** Temporary-cache compile and `git diff --check` passed; the focused pure Step 6 suite passed `58 tests` including the modular/context budget; Graphify refreshed. The authorized pinned-container Slicer round-trip loaded FD14, cleared it with New Empty Case, saved a validated bundle, and reported `mrml_FDI14=0` and `lineage_FDI14=0`; no motion or hardware operation was performed.
- **Next action:** Repeat the complete FDI44 workflow from a clean session and visually verify Step 6A. The clear/save regression now supports session carry-over as the cause when New Empty Case is used successfully, while the separate FDI44 archive audit remains text/lineage-only and cannot establish binary mesh identity. Regenerate FDI44 Step 4A/4C/5C if the package reports a cross-target chain; only then repeat 6.0A. See `logbook/2026-09-07.md`.

## FDI31 GUI planner P0 reset — active contract (2026-09-21)

**Historical model routing (2026-09-23; superseded by 25 September overlay AGENTS.md/operator instruction):** `gpt-6-sol` at `low` is the
coordinator for this task; `gpt-6-luna` at `xhigh` is an optional bounded
implementation auxiliary. The former Terra-xhigh prerequisite no longer blocks
source work. The canonical plan's manual GUI verdict and runtime/safety gates
remain in force. See `Workspace/AGENTS.md` and the dated decision.

**2026-09-26 engineering-outcome review (supersedes intermediate status summaries):**
Baseline `40ad290` contains ROI-first sampling, shared endpoint evaluation,
separate diagnostic P1/P2/P3, draft/guarded J1–J5 controls and schema-1.0 JSON
recording. Prior host pure checks passed 193 tests. The full engineering solver
is partial: detached Base/Home candidates, arbitrary invalid-draft evaluation,
complete motion evidence/path/replay, final two-area integration and full-chain
promotion remain open. Native/runtime behavior and measured responsiveness are
unverified; the last headless fixture failed before any jog (scenarios NOT_RUN).
Tarun is remote: user simulation trial and visible verdict remain PENDING.
The [revised existing plan](diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md)
prioritizes engineer-led state/motion exploration before case-specific planner
solving. It specifies finite closure slices and reuse of indexed automation.
Headless and scripted headed Slicer checks are technically available, subject to
runtime authorization, provenance and the current fresh-case deferral. The
parallel performance/5.12 checkout is outside this task.

**2026-09-27 uncertainty source gate:** A post-submission unknown/stale manual
jog now latches its facade session and prevents a second publish. The panel
retains the draft, states that the simulation may have advanced, and exposes
available body-pair and measured-distance evidence. Host focused pure checks
passed (6 facade and 5 UI); no native runtime or operator verdict occurred.
Raw request/policy correlation and authoritative reconciliation remain open
before trusting live acceptance. Details are in the 27 September logbook and
the active renovation plan.

**2026-09-27 draft-state source gate:** Explicit Check Draft State uses the
existing shared static/endpoint evaluator on captured J1–J5 without motion or
accepted-state mutation. Identity and UI draft changes yield stale/unknown
evidence; static validity remains separate from task-target residuals. Focused
host pure checks passed (6 facade, 4 UI). Current draft controls still use the
reviewed-limit range; native static failures lack structured collision-pair
evidence. Runtime and Tarun's verdict remain pending.

**2026-09-27 recorded manual prerequisite:** The unchanged newer case has
`confirmedTask=null`. A 120-second headed recording passed checkout/case/native
provenance, production robot/context import, simulation Connect and 31-object
readback, then Check Draft State returned `not_reached` before a static query.
No jog was submitted. The task-independent manual exploration branch is the
next `S6-LIVE-01` source gate: freeze branch/Base/limits/profile/scene/ROS
identity, mark absent or stale Home unconfirmed, and permit static review and
guarded jog without asserting task-target
evidence, and invalidate this identity when a task becomes confirmed. Preserve
the exact native acknowledgement and accepted-state ordering. A new Home or
confirmed target must not be chosen just to make this diagnostic pass. The
run-local video/JSON/screenshot diagnostics and commands are in today's
logbook; source, runtime and operator acceptance remain open.

**2026-09-27 manual acknowledgement source gate:** After commit `407fde4`,
the native guard and Python bridge/facade gained a separate one-shot,
simulation-only manual request/status pair with unique request/session and
actual ordinary ACM policy identity. Exact vector, policy, world IDs and
task/scene identity are checked before the UI can mirror acceptance; uncertain
responses retain the last confirmed app state and pause the legacy heartbeat.
The combined host pure check passed 106 tests, Python compilation and diff
check passed; native build/current-case Slicer/ROS and operator verdict remain
open. This does not clear the uncertainty latch or promote a manual path.

**2026-09-27 reconciliation source retry:** The dedicated native read-only
query and UI Reconcile State action now have both source halves. Exact
request/session/policy/echo, frozen task/scene identity, scene object IDs and
fresh monitored J1–J5 must agree before clearing an uncertain-jog latch;
static collision validity remains separately reported. A missing operation
is rejected before motion. The combined host pure run passed 118 tests.
Native build and current-case Slicer/ROS/screenshot/operator acceptance remain
open; no manual path gains preview authority.

**Bound task:** `S6-LIVE-01` (Priority 0); pending `S6-LIVE-03..05` require acceptance
of their preceding milestone.

**2026-09-24 FDI11 diagnostic proposal (not implemented):** Tarun requested saved robot-base/Task Home analysis and proposed separate GUI planner stages. The inspected `SEPT24/fdi11_step6.dentocase` retains the later screenshot IK failure; matching-URDF FK shows all-zero Home 36.887 mm from PreEntry and 162.258° from its drilling axis. Ten further Home-connected seeds were used. Detailed evidence is in today's logbook and `diagnostics/evidence/fdi11-step6-2026-09-24/saved-pose-audit.json`. The immediate diagnostic gap is that the bridge's best failed joint vector is discarded when the facade saves only failure text; no best-state joint-limit attribution or collision-free verdict is available. Proposed minimum: an IK-only plan diagnostic exposing seed, best joints, both residuals, native limit proximity and whether collision checking ran. A later ordered P1/P2/P3 diagnostic view must reuse exact preceding endpoints/orientation, invalidate downstream results when task inputs change, and preserve full-chain/guard requirements before preview. `S6-LIVE-03` owns any plan-only Home view or recovery change: current-to-Home planning and reversing the accepted task route are separate operations. Current request authorizes analysis/design; agent planner runtime and implementation are not resumed by this proposal.

**2026-09-24 two-area direction, renovation-first supersession 2026-09-26:** The Planning & Diagnostics surface absorbs optional 6.3 workspace evidence, task confirmation, the full manual engineering workbench and PreEntry/P1/P2/P3/full-chain planning. Preview & Control owns simulation Approach/Drill preview, guarded return and repeat from 6.6 plus `S6-LIVE-03/04`. Keep 6.0–6.2 prerequisite actions and their single state owners. Goal-1, standalone PreEntry and explicit Check Current State use the shared versioned exact-TCP evaluator; current-state static validity is separate from Target match and identity changes remain stale. Source-only P1/P2/P3 actions now consume same-instance PreEntry endpoints, hand off exact preceding endpoints, evaluate their resulting TCP endpoints and independently guard each Home-rooted prefix. Their stored paths are diagnostic-only and cannot authorize preview. The existing panel exposes these actions temporarily; final two-area UI, complete-chain promotion, interactive manual controls/recording, clearance and exact-state conditioning remain open. The combined Step 6 host pure suite passed 181 tests. This source work precedes case-specific planner solving; FDI11 interpretation and the separately saved changed setup remain pending. Do not add a second planner, duplicate MRML owner or hardware command path. The previous separate-step presentation contract is superseded; M0–M4 evidence and manual verdict stops remain as milestone gates.

**2026-09-25 bounded source implementation and sequencing:** Tarun explicitly
authorized the [Step 6 renovation plan](diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md).
**Full renovation pointer:** The linked plan is the Step 6 implementation and acceptance sequence. Tarun approved the corrected 6.3A ROI, 6.3B ROS-connected Manual Robot Simulation Solver / Engineering Workbench, 6.3C shared planning diagnostics and 6.4 preview architecture. This contract links to the plan without duplicating its gates; the [active base-pose technical reference](diagnostics/DENTOBOT_Base_Pose_Feasibility_Explorer_Diagnostic_Plan_2026-09-25.md) supplies shared evaluator metrics.

**2026-09-25 source checkpoint:** Pure ROI-first candidates, current opened-incisor ROI default/draft, versioned display-only manual record and interrupted-preview Block Return latch have source checks. The workspace action now consumes the ROI draft, solves ROI TCP candidates through native position-axis IK before MoveIt static/FK and bounded Home connectivity, and records per-phase counts/timing and current ROI/axis identity. Optional workspace proposals no longer gate confirmation or change an accepted task's effective-limit fingerprint; applying reviewed limits still requires mechanical bounds and Home inclusion. The combined host pure suite passed 135 tests. This is source evidence only: live yield, timing, cloud display/reopen, manual solver/evaluator, two-area UI, Slicer/ROS checks and Tarun's visible verdict remain open under the linked plan; see today's logbook.
**2026-09-26 source checkpoint:** Goal-1, standalone PreEntry and explicit Check Current State use a versioned exact-TCP evaluator; PreEntry limit evidence uses a pure named-joint SI-to-display helper. Separate Check P1/P2/P3 actions now plan from the exact Home/preceding-stage endpoint, evaluate resulting TCP endpoints and independently guard each Home-rooted prefix, with request/session/policy/joint-vector matching before attributing guard status. The combined Step 6 host pure suite passed 181 tests, with Python compilation and `git diff --check` passing. These source diagnostics have no route authority and remain on the existing planning panel; the full ROS-connected manual workbench, recording, final two-area UI, complete-chain promotion, numeric forbidden clearance and exact-state conditioning remain open. No Slicer/ROS runtime or case-specific verdict follows. See [today's logbook](logbook/2026-09-26.md).
**2026-09-26 guarded-jog follow-up:** Exact J1–J5 draft/ghost controls and the simulation-only raw guard façade passed a 187-test combined host pure suite, Python compilation and `git diff --check`. The façade gates a fresh exact accepted echo on current task/branch/base/Home/limits/scene and acknowledged scene objects; UI mirroring requires that acceptance. Rejected/unknown requests retain draft and native evidence. Raw status lacks a policy fingerprint and request ID. **Headless Slicer/ROS manual-jog test: FAIL / acceptance pending after the later attempts below; user simulation trial: PENDING; Tarun's visible verdict: PENDING.** Base/Home acceptance, recording/export, full workbench diagnostics, final two-area UI and runtime acceptance remain open under the renovation plan.
**2026-09-26 approved headless gate attempt:** The new narrow runner/launcher and matrix entry were source-checked, but three sequential launcher preflight failures stopped before ROS/Slicer: dedicated container exited; its Git worktree pointer resolved to a host-only path; container `/tmp/dentobot-verification` parent was absent. No manual jog, native guard response, runner JSON or screenshot exists. The verification retry ceiling is reached. Preserve the two host run evidence directories and exact first errors in today's logbook. Further runtime requires Tarun's direction; his simulation trial and visible verdict stay pending.
**2026-09-26 resumed headless gate:** Tarun explicitly approved continuation and checkout diagnosis. The renovation Python source was mounted and hash-checked, but shared ROS build/install metadata points to the parallel `DentoBot` checkout; current native source hashes match, without proving binary provenance. Three further bounded attempts stopped at an awk self-match, an uninitialized runner case hash, and then a saved Step 6 package-lineage mismatch after ROS readiness and Slicer case import. The first two source defects were minimally fixed and statically checked. Attempt 6 produced a failure manifest with all scenarios `NOT_RUN`; no guard request, jog or screenshot occurred. Stack teardown passed on attempts 5–6. Durable logs/results are under `Testing/evidence/manual-jog-headless-preflight-20260926/attempt-4..6/`. Headless acceptance remains failed/pending; Tarun's simulation trial and visible verdict remain pending. The new three-failure ceiling is reached; diagnose lineage from retained evidence before another runtime decision.
**2026-09-26 operator deferral:** The fixture was `data/Slicer_Saved/SampleStudy1/FDI31/dentobot-case-sep22-step6.dentocase` (SHA-256 `eb48a805c81578bafcc8ca72663b6f8a98b1f9721c7f9e680d44b458558e7adb`). Its lineage mismatch is retained as older-case compatibility evidence, without inferring a current guarded-jog defect or relaxing validation. Tarun directed deferring further case-based runtime tests until substantial development progress and a newly saved case reflecting the renovation; a heavier user session may follow. Continue source/pure checks. Headless acceptance, screenshots and user verdict remain pending; this supersedes immediate fixture-lineage diagnosis as the next gate.
**2026-09-26 Base/Home and recording source gate:** Explicit candidate/Accept Base and Accept Task Home UI delegates to the existing `lockBase` and `saveTaskHome` owners. The façade now uses the existing manual simulation record schema for exact requested J1–J5, correlated guard accept/reject, unknown diagnostics and terminal Base/Home evidence; export is historical/display-only. A completed acceptance record is selected over a new empty ledger, and export feedback leaves visible guard failure evidence intact. The direct Base nudge path can occur before complete task identity, so its pre-commit recording is labelled unavailable rather than invented. Two Luna Max workers with disjoint files ran focused pure tests; combined final check passed 109 tests, 11-file Python compilation and `git diff --check`. No Slicer/ROS, planner, preview, case edit or hardware run. Path display/replay, fuller workbench diagnostics, measured interaction, final UI/full-chain gates and fresh-case/operator acceptance remain open.
**2026-09-26 quota-reset verification continuation:** Two Luna Max read-only workers ran the remaining disjoint host pure suites on the renovation checkout: 157 façade/state/planning and 36 UI/bridge tests passed (193 total). Eleven changed Python files compiled; launcher `bash -n`, matrix JSON parsing and `git diff --check` passed. This expands source verification only. The matrix container template points to the separate checkout and was not run; no Slicer/ROS/native/case-based check, screenshot or operator verdict followed. Fresh-case user session remains deferred by Tarun.
**Later-reference pointer:** [Step 6 later work and adjacent ideas](diagnostics/STEP6_LATER_WORK_AND_ADJACENT_IDEAS_2026-09-25.md) retains FDI11/21/31 case-specific solving, planner comparison, future recovery and related Step 3–5/Studio ideas under their existing IDs. It is not a second pending queue. The [Step 6 archive index](diagnostics/archive/step6/README.md) maps superseded prose records to their historical evidence.
**Superseding operator confirmation:** Valid workbench joint jogs advance the ROS-connected simulated robot after guard acknowledgement; rejected requests remain inspectable review states. Base/Task Home commitment is explicit through current ownership/invalidation, and recorded manual states cannot authorize preview without a fresh full guard. Renovation precedes case-specific planner solving. The first direct-display ordinary-interaction target is 60 FPS, with rendering/FK measured separately from guard/ROS/diagnostics under S6-P2-03 overlap.
The standalone FDI11 PreEntry IK action is source-checked and its first visible report pertains to an intentionally changed base/Home; Tarun's interpretation and separate saved setup remain open. The corrected workflow-first scope is the linked plan, including shared diagnostics and required recording. Case-specific FDI21/FDI31 solving and planner comparison follow under the later-reference index and canonical P0 gates. Agent runtime, complete-route preview and milestone verdicts remain separately gated. **Current task routing:** GPT-6 Sol orchestrates. Tarun's 28 September override permits up to four GPT-6 Luna Max bounded workers simultaneously for the detailed headed-campaign implementation, with disjoint files and coordinator review. Use only the number justified by independent work. The current platform permits three workers beside Sol concurrently; a fourth permitted worker is sequential. Sol retains controlled records, runtime and acceptance.

**2026-09-23 batch-comparison supersession:** The operator requested one
Step 6.5 action running RRTConnect, RRT and RRT* sequentially with identical
inputs, preserving ordinary failures and per-PreparedBranch fingerprinted
reports/waypoints across save/reopen. Saved paths are display-only and cannot
authorize preview; a chosen planner must be freshly replanned. Source checks,
one approved save/reopen integration, then one normal-window comparison and
Tarun's explicit verdict are the acceptance sequence. See the canonical plan.

**2026-09-23 operator delta/source state:** The full Step 6.5 error-dialog
message is retained in the fingerprinted Motion Diagnostics session; all five
parameter controls and labels have hover guidance, including the locked-mode
reasons; RRT* is an optional third configured joint planner with RRTConnect
still default. Focused source checks pass. Normal-window review and actual
planner comparisons remain open; the reported Stage-3 tooth↔spindle rejection
is unaccepted and collision/phase guards are unchanged.

**Canonical contract:**
[diagnostics/FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md](diagnostics/FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md)

**Input identity:** `data/Slicer_Saved/SampleStudy1/FDI31/dentobot-case-sep22-step6.dentocase`
(SHA-256 `eb48a805c81578bafcc8ca72663b6f8a98b1f9721c7f9e680d44b458558e7adb`).
The operator created this fresh workflow after installing the diagnostic URDF;
the Sep-19 package remains historical baseline evidence only.

**State and acceptance:** The initial Sep-22 run was canonical housing-on and
failed Home→PreEntry against tooth→`pneumatic_spindle-Copy`. After the launcher
propagation correction, the operator ran the explicit diagnostic description:
**`M1-DIAG / HOUSING-OFF PASS`**. The visible preflight completed P1 with 150
waypoints; it also computed P2 with 12 and P3 with 23 waypoints. Those P2/P3
results are retained diagnostic evidence only and do not authorize housing-off
preview, M2, or canonical acceptance. Route-selection then reported that Task
Home was not validated in the current session; no housing-off replan follows.
Acceptance is GUI-visible and operator-reviewed; headless results are
diagnostic only. Canonical M1 remains open. The next bounded action is to end
the housing-off session, restore canonical housing-on mode, and have the
operator select/review one temporary collision-valid Home for Experiment B.
The later screenshot with an approximately 45.96-mm mouth gap is not an
Experiment B result: it changed anatomy as well as Home and failed before P1
because no canonical TCP position-axis IK candidate met tolerance; its reported
collision sets were empty. Restore the Sep-22 anatomy/gap before comparing Home.
With that altered 45.96-mm geometry held fixed, a later operator-selected Home
did produce 31 free-space P1 samples and all 12 fixed-axis P2 checkpoints from
179 MoveIt samples; the full task then stopped at Stage 3. The paired results
show Home/IK-seed or branch sensitivity at the altered geometry, but do not by
themselves prove that base placement/orientation is incorrect and do not close
canonical M1 or M2.
The operator subsequently changed robot-base position and orientation while
retaining the displayed 45.96-mm gap and canonical spindle collision. The
visible Motion Diagnostics reports `CompletedWithWarnings`, with P1 66, P2 10
and P3 22 waypoints and a complete seeded chain on planner attempt 2. This is a
housing-on alternate-geometry full-chain diagnostic pass. It proves that the
housing is not intrinsically incompatible with FDI31 and makes the original
physical placement/configuration-space clearance the leading causal boundary.
Because base, anatomy and Home differ from the Sep-22 baseline, it does not yet
close canonical M1/M2 or authorize preview.
The canonical plan owns all
milestone procedures and Experiment A/B/C mechanics, including
the `M1-DIAG / HOUSING-OFF` boundary. Campaign-1 r4/P3/P4/P5 is preserved
historical evidence, not an execution input or acceptance substitute.

**Professor-recommended planner-policy delta (DENTO-NOTE P0, 2026-09-22):**
This is the immediate next `S6-LIVE-01` task after the currently running
`S6-REUSABLE-CASE-SETUP` work hands off. Motion Diagnostics must display the
effective runtime planner algorithm/configuration. Audit and apply RRT rather
than RRT*, disable approximate IK, and disable Cartesian-path planning in the
live workflow. The repository currently configures
`RRTConnectkConfigDefault` as `geometric::RRTConnect`, already an RRT-family
planner and not RRT*. Acceptance therefore requires proof of the effective
runtime planner ID, not a blind YAML rename. The canonical plan must define how
Stage 2/3 are planned without the current Cartesian path calls before source
changes. Preserve collision, phase, target-contact, J1-J5/J6, geometry and
no-hardware invariants. Required evidence is one focused policy/diagnostics
check and an operator-visible Motion Diagnostics verdict.

**First implementation slice (source verified):** The Goal-1 motion diagnostic
now fingerprints and displays the current planner ID/algorithm, attempt count,
planning allowance, approximate-IK state and Cartesian Stage-2/3 state. It
reports `RRTConnectkConfigDefault` / `geometric::RRTConnect`, one attempt, 5.0
seconds, approximate IK disabled and Cartesian Stage 2/3 enabled. This adds no
chooser and changes no runtime policy. The next slice is the real SlicerROS2
planner-ID input/output bridge; no cosmetic dropdown is accepted.

**Planner-ID bridge slice (source verified; build/runtime pending):** Both
SlicerROS2 joint-plan entry points accept an optional planner ID and expose the
effective ID returned by `MoveGroupInterface`. The Python bridge retains both
requested and effective IDs in its plan result, and the Step 6 explicit-state
call sites submit `RRTConnectkConfigDefault`. Focused pure tests pass. The
focused SlicerROS2 package rebuild passes. The shared editable pop-out,
configured planner list and visible effective-ID evidence remain open.

**Shared planner-dialog slice (source verified, 2026-09-22):** The same dialog is reachable
from Step 6.5 and 6.6. Its configured planner, bounded attempts and bounded time
are submitted to Goal-1 planning and retained in diagnostics. Approximate IK
and Cartesian mode are visible but locked at the implemented values. At this
checkpoint, a second planner and visible runtime acceptance remained open.

**Interactive chooser source pass (2026-09-23):** OMPL now configures
`RRTkConfigDefault` / `geometric::RRT` alongside the existing default. The
shared dialog lists exactly those configured choices. A plan with a selected
ID cannot be promoted when the SlicerROS2 reported ID is missing or differs;
Motion Diagnostics displays requested and reported IDs separately. Focused
source tests and the installed-config check pass. A visible per-planner trial
and operator verdict remain open.

**Terminology source slice (2026-09-23):** Step 6.5/6.6 navigation, phase
titles, primary preview buttons and local readiness wording use Approach/Drill
names. Public/internal Goal 1/Goal 2 APIs and saved-state vocabulary are
unchanged. Facade result/error wording and normal-window confirmation remain
open; the planner comparison trial still precedes further parameter controls.

**Operator-message terminology slice (2026-09-23):** The remaining live
facade/bridge/logic result and error strings use Approach/Drill preview names;
internal comments and saved diagnostic keys retain legacy Goal terminology.
The `planDrillingPhase` description now accurately says it prepares retained
Stage-3 preflight, without changing its code path. Focused checks pass;
normal-window terminology acceptance remains open.

**Planner attribution correction (2026-09-23):** The SlicerROS2 planner-ID
getter is read before `plan()`, so matching selected/reported IDs establish a
configured MoveGroup setting, not execution-algorithm provenance. The UI now
says `MoveGroup configured ID` and `execution algorithm unverified`; the
compatibility diagnostic keys remain. Focused source checks pass. The first
visible comparison must keep executed-algorithm attribution separate unless
planning-server evidence is captured.

**Latest implementation and visible evidence (2026-09-23):** The existing
chooser now includes optional `RRTstarkConfigDefault` / `geometric::RRTstar`
without changing the RRTConnect default. Hover guidance covers all planner
controls and explains the locked approximate-IK/Cartesian states. Exact Step
6.5 failure text is retained and reopenable in Motion Diagnostics. Focused
source checks and the installed OMPL configuration pass. Tarun's visible
RRTConnect trial reported the requested/configured RRTConnect ID, one 5-second
attempt, approximate IK disabled, Stage 1 and Stage 2 PASS, and Stage 3 blocked
by selected-tooth ↔ spindle collision. Cartesian Stage 2/3 was still enabled.
This is not an executed-algorithm attribution or a complete route. Remaining:
same-scene visible RRT and RRT* results with Tarun's verdict, followed by the
already-designed exact-pose sequential-IK Cartesian-off implementation and its
own visible stop.

## Step 6 planner manual diagnosis — archived context (2026-09-20)

**Bound task:** `S6-LIVE-01`. The [September 20 manual diagnosis](diagnostics/archive/step6/STEP6_PLANNER_MANUAL_DIAGNOSIS_CONTEXT_2026-09-20.md) and [implementation map](diagnostics/archive/step6/PLANNER_IMPLEMENTATION_MAP_2026-09-20.md) are preserved as dated evidence for the September 19 FDI31 P1 session. Their mandatory read order, restart statement and experiment order are superseded. For current work, read the [Step 6 renovation plan](diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md), this task's active row below, [backlog.md](backlog.md), and the [FDI31 P0 milestone contract](diagnostics/FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md) when its gate is implicated. Apply the 28 September superseding five-DOF decision: the current robot model and workflow expose exactly J1–J5; the drill spindle is outside joint states and IK. Keep exact scene/guard, manual verdict and no-hardware boundaries; the older session does not determine whether the changed-setup FDI11 PreEntry endpoint is reachable or Home-connected.

## Track A acceptance contracts — migration baseline

**30 September r22 bounded workbench acceptance:**19 selected headed checks passed with0fail, native exact IK solution retained in draft, real TCP drag/buttons/keys/editor suppression and default-off cleanup verified. Slicer/recorder exit0, complete503.733s bounded-run video and MP4/106-file manifest retained. Full workflow is explicitly not claimed: native rejected fixture, uncertain Base/Home, negative IK, full planner/preview/repeat, final new-case save/reopen, representative responsiveness and Tarun verdict remain open. Horizontal clipping visible with compactchrome still needs UI-P3-01 review. See current logbook and r22 diagnostics.

**30 September S6-LIVE-01 r21/source update:** Case-bound completed viewport drag, Cartesian buttons, physical TCP keys, numeric/text focus suppression and opt-out cleanup passed, with accepted robot unchanged. R21 failed exact native IK-to-draft staging; panel precision correction now passes130 focused host tests with true rounded-control regression. Runtime confirmation remains pending, as do negative IK/native rejected outcomes, uncertain Base/Home, full-chain preview/repeat/final case/reopen and operator verdict. R21 video is partial, no native signal. See current logbook/run diagnostics; host checks are not full runtime acceptance.

**30 September DENTO-NOTE — conditional bounded base-placement diagnostic (`S6-LIVE-01`):** Tarun requests iterative translation around the existing forehead-plane-center Base placement if planner testing fails due to IK unreachability: offsets up to ±20 mm on each of two in-plane axes only. His “XY” denotes an oblique anatomical plane parallel to the upper-teeth root↔crown direction, not an assumed world-RAS XY plane. Triage: planned conditional investigation under the existing planner/base-feasibility contract; the note itself is Unprioritized and does not change the parent Priority0. It supersedes blanket deferral only for this bounded failure-triggered diagnostic; broader sweeps, orientation search, heatmaps and robot redesign remain deferred. Prerequisites: complete the current workbench gate, capture exact current-task IK failure, and establish a reviewed plane origin/orthonormal basis and sampling budget. Root↔crown direction alone does not uniquely define a plane; do not invent its second axis or equate it to the forehead plane without review. Keep Base orientation and normal offset fixed, retain the zero-offset baseline, and freeze anatomy, task/TCP, limits and collision/phase policy. Reuse the shared five-joint evaluator, preserve each candidate transform, requested endpoint, IK/FK residuals, limit/collision evidence and identity in diagnostic records/screenshots. Candidates remain detached/display-only; no automatic Base acceptance, Home reuse, route promotion or preview. A selected candidate requires normal explicit Base review/acceptance, scene acknowledgement, fresh Home/workspace/task checks and full-chain guard before motion authority. No successful IK result or infeasibility proof is implied by this note; empty bounded search remains inconclusive beyond its evaluated coverage.

| Order | ID | Priority | State | Next bounded action |
|---:|---|---:|---|---|
| 1 | `S6-LIVE-00` | 0 | Documentation checkpoint recorded; source baseline `ea504349f99f` preserved; scoped static/pure checks, rebuild, runtime marker, and graph refresh recorded | Keep the checkpoint boundary explicit while reconciling the remaining Stage-3 reachability issue |
| 2 | `S6-LIVE-01` | 0 | **Engineering solver partial; five-DOF refactor verified.** Baseline `40ad290` includes ROI-first sampling, shared endpoint evaluation, diagnostic P1/P2/P3, draft/guarded J1–J5 controls and initial schema-1.0 JSON records. Manual request/session/policy and read-only reconciliation source gates were committed as `c1bfba0`. Checkpoint `84234a6` records the preceding workbench gates. The uncommitted 28 September refactor now makes URDF, guard, state, Home, limits, IK/FK, publishers, UI and current persistence exact J1–J5 while retaining fixed spindle/burr geometry and canonical TCP. Its indexed host suite passed 394 tests, both ROS packages built in an isolated overlay, and a serialized runtime passed exact five-value guard/state/static/TF/IK checks. Generic fixed-orientation Cartesian interpolation is recorded as unsupported for this five-DOF arm; Step 6 uses the separate position-plus-drill-axis continuity path. Earlier headed evidence includes Base/Home acceptance and a no-case TCP gate proving explicit default-off probe activation, real-time viewport mouse drag, Cartesian nudges, authoritative position-axis solve/stage, accepted-state separation, disable cleanup and zero route/preview authority. Physical keyboard events, case-bound rejected/unknown outcomes, representative responsiveness and positive full-chain preview/interruption remain open. User normal-window verdict PENDING. Case-specific FDI11/21/31 solving remains downstream. | Follow the [reconciled renovation plan](diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md) and [detailed five-DOF acceptance checklist](diagnostics/STEP6_FIVE_DOF_DETAILED_ACCEPTANCE_CHECKLIST_2026-09-28.md): retain bounded Base/Home/TCP evidence; create and fresh-reopen the named five-DOF FDI11 case; verify uncertain-commit reconciliation, invalid drafts and accepted/rejected/unknown runtime paths; then complete ordered records/export/reopen, physical-key/responsive two-area interaction and positive full-chain preview/interruption. Preserve exact case/native attribution, guard boundaries and diagnostic-only partial paths. The clean connected shutdown path is verified; older partial videos remain failure evidence. See the [28 September logbook](logbook/2026-09-28.md) for current commands and evidence boundaries. |

**2026-09-29 superseding `S6-LIVE-01` acceptance update:** Tarun resumed the
bounded simulation runtime after the 28 September halt. Recorded headed r15
passed 21 enabled production case/native/scene/draft/accepted J1/controlled
unknown-reconciliation/record/Base/Home/save checks; the case-bound native
rejection was NOT_RUN without an exact frozen candidate. It created
`SEPT24/sept28_fdi11_step6_five_dof_acceptance.dentocase`, SHA-256
`d5a0e7bb13ebeda00e5cf9702ce1657f63c074359c833868678805dd854ff090`.
Read-only fresh-process r16 passed all 12 saved/offline qualification checks;
its Slicer and recorder exited 0 and owned processes cleaned up. The saved
FDI11 task and validated five-DOF Home remain in lineage, while live task
confirmation is intentionally cleared and Home is `Unreviewed` until explicit
new-session validation. The input case is unchanged. Both runs have complete
video manifests, screenshots, JSON, diagnostics and SHA-256 manifests in
`data/dentobot-runs/`; see the [29 September logbook](logbook/2026-09-29.md).
The opt-in J1–J5 keyboard source and focused host checks plus recorded r19
physical-key draft-only headed gate are complete. Next: finish the detailed
campaign's native rejection, case-bound TCP, text-focus, responsiveness, record-persistence and
full-chain preview/interruption gates. Do not infer planner, preview, hardware
or Tarun's normal-window verdict from r15/r16.

**2026-09-30 demonstration recovery and later case-bearing evidence
(`S6-LIVE-01`):** Tarun's manual demonstration exposed an inaccessible
uncertain-Base recovery path and repeat workspace/planner staleness after
selecting the incisor-derived ROI. The visible Step 6 Base action now routes
uncertain acceptance to reconciliation; exact saved ROI/source reuse is a
no-op, changed ROI invalidates, and Approach/Compare require current runtime
workspace plus reviewed limits. The facade enforces the same prerequisites.
The 250-test host source gate passed. An r1 headed run exposed and led to
correction of a six-decimal versus full-precision workspace identity error.
R2/r3 then stopped on native exits. A subsequent isolated diagnostic and
recorded r6 passed strict source-case restore, five-joint robot, ROS/MoveIt,
31-object scene, J1 guard acceptance, historical record export/reopen,
Base/Home review, two workspace validations and production save. It created
`sept30_fdi11_step6_3_demo_ready.dentocase` (SHA-256
`539ee7948bd97434ab4ef8b675e1540f065219a7e5250c3a422d2cfb481c371a`)
with a complete zero-exit video. R7 strictly reopened it in a fresh Slicer
process with seven robot models and exit 0. R6/r7 do not establish planner,
TCP, preview or normal-window usability acceptance.

The next case-bound TCP/full-chain trial r8 exited before either probe.
Instrumented r9 and r10 captured `SlicerApp-real` exit 139/SIGSEGV 11
during post-hydration validation and Task Home connectivity 12/13 respectively.
No cgroup OOM or native stack was obtained; explicit Python faulthandler stayed
empty. R8/r9/r10 partial videos and run-local diagnostics are retained.
Their sequence reaches the verification protocol's three-failure stop on this
distinct native blocker. Source-only external mouse-delivery and failure-count
reporting refinements pass a 64-test combined host gate, compile and diff
checks. Further autonomous Slicer retries are stopped pending a specific
native-debugging strategy and Tarun's direction. Case-bound rejected/unknown
guard, mouse drag, full-chain/preview, representative responsiveness and
Tarun's normal-window robotics/usability verdict remain **PENDING**. Manual,
reopened and partial paths have no route/preview authority. See the
[30 September logbook](logbook/2026-09-30.md) and r6–r10 run-local diagnostics.

**29 September operator PreEntry diagnosis (`S6-LIVE-01`):** Tarun's guarded
approach screenshot shows no accepted PreEntry IK endpoint, with observed best
residuals outside the existing 0.25 mm/0.5 degree endpoint tolerances. He
reported that the hidden PreEntry coordinate and lack of spatial explanation
defeat the engineering workbench's purpose. The current saved FDI11 comparison
package yields PreEntry RAS `(-88.006688, -33.443087, 52.862497)` mm from its
confirmed trajectory and 2 mm standoff; this is saved-case geometry, not a live
task readback. A source-only gate now retains per-seed failed states and the
exact diagnostic fingerprint, shortens the modal, presents current-snapshot
PreEntry/Entry/Target RAS values, and displays transient unsaved target markers
and a best failed J1–J5 translucent goal pose for exact-current diagnostics.
Saved/stale PreEntry reports remain text-only and no partial result gains route
or preview authority. The final 166-test combined host check passed; headed
visual placement/cleanup, active-case identity and Tarun's spatial verdict
remain pending. See today's logbook and the amended renovation plan.

**2026-09-28 exact-case migration continuation:** Three recorded visible XFCE
attempts stopped respectively at exact profile mismatch, stale cached
parameter-node routing, and pre-audit compatibility mutation. The exact
six-to-five-DOF profile matcher/migration, fresh-node caller and final
post-hydration-audit ordering now pass 73 focused host tests, compile and diff
checks. The source case is unchanged and the planned acceptance case is still
absent. Runtime retry ceiling reached; final headed confirmation and every
downstream checklist item remain PENDING. Evidence and hashes are in the
[28 September logbook](logbook/2026-09-28.md); do not launch a fourth
autonomous retry.

**28 September guarded-jog completion checkpoint:** The r13 headed run passed
the corrected case-load/workspace/native boundary, accepted one in-limit J1
jog and an invalid reviewed-limit draft, then stopped before unknown-result
injection because the next valid Guarded Jog was disabled. The root cause was
completion ordering while `_workflowActionBusy` was true; the shell fix now
clears busy before the final Step 6 availability refresh. The full Manual Jog
UI suite passed 35 tests and the headed-runner source suite passed 44 tests,
with compile and diff checks clean. The prepared r14 retry was rejected before
runtime launch by the automatic approval usage limit, so this fix is not yet
headed-runtime verified and the named acceptance case remains absent. **Operator
halt:** do not launch r14 or any Slicer/ROS/MoveIt runtime until a later
explicit resume; preserve r13/r14 evidence and keep native rejection/unknown,
full-chain preview, responsiveness and Tarun's verdict pending.

**27 September revised verification/integration order:** Following Tarun's
concern that repeated GUI debugging is delaying an incomplete workbench,
finish `S6-LIVE-01` source slices with focused guard/identity/preview tests;
run a narrow native check only where source evidence is insufficient. Before
the final representative headed campaign, curate the proven accepted-5.10
integrity and performance delta from the clean parallel checkout into a new
reviewed integration branch. Compare overlaps with this dirty Step 6 tree;
do not wholesale merge the branch containing deferred 5.12 history. Keep
`S6-P2-03` load/performance, `S6-REUSABLE-CASE-SETUP` restore, `S6-U-01`
shutdown and `PLAT-U-06` 5.12 under their existing owners. This is sequencing,
not source/runtime/operator acceptance or permission to commit/push.

**27 September source closure and curated integration evidence:** The guarded
J1–J5/unknown/reconciliation, Base/Home, ordered recording and historical
display, five-page two-area UI, complete-chain-only preview, legacy API
closure and isolated Base candidate ghost source gates pass 225 combined host
tests in the renovation checkout. A fresh uncommitted integration worktree
`integration/step6-5.10-reviewed-20260927` adopted reviewed 5.10 case
restore/fingerprint/stage-save and Connect rendering changes without the
deferred 5.12 image/native history; 251 combined host tests pass there. The
strict Step 6 saved environment/landmark validation remains intact. One narrow
Slicer 5.10 integrated run on the unchanged current FDI11 case passed strict
reopen, 31-object scene acknowledgement and Connect/Disconnect, with UI and
viewport screenshots; Slicer still exited 1 on shutdown, so no complete
recording. A first stack-present load exited abnormally during control
refresh; a later offline trace and stack-present retry passed. The case has no
confirmed task, hence no current positive full-chain preview fixture. Keep
negative-state GUI, export/reopen, interruption, measured responsiveness,
whole-run video and Tarun's normal-window verdict pending. Exact commands,
hashes, attempts and evidence are in the [27 September logbook](logbook/2026-09-27.md)
and the run-local `step6-integration-narrow-fvnSqgdA/diagnostics.md`.

**28 September recording preparation:** In the reviewed integration worktree,
the 14-item headed runner gained an exact integration-checkout provenance
profile and a read-only taskless-draft stop. It deliberately exits `PARTIAL`
before jog/Base/Home, planner or preview. A new run-local diagnostics helper
requires an explicit full-workflow claim, all applicable item passes, complete
hashed video with zero command/recorder/FFmpeg exits, screenshot evidence and
a wrapper attestation of zero remaining owned processes before claiming whole-
run completion. The focused runner/helper/recorder host suite passed 33 tests
and four subtests; compilation and diff check passed. This does not complete
the final campaign runner, positive confirmed-task authority fixture, native
shutdown, representative video or operator review. See the [28 September
logbook](logbook/2026-09-28.md) for exact commands and evidence boundaries.
The next opt-in source slice adds a live-displayed-limit invalid-draft check
to the bounded runner and a separate callable production export/import/replay
probe. After Sol corrected a display/SI and joint-label/native-name mismatch,
the combined host suite passed 43 tests and four subtests. Both remain
source/host verified only; the historical helper is not in a complete headed
campaign, and genuine native rejected/unknown outcomes cannot be inferred
from injected host tests.

**28 September bounded headed evidence:** The opt-in historical probe is
joined to the integration runner after accepted jog. One recorded attempt
stopped at the runner's wrong substep 5 (Manual Jog is substep 3); its partial
video and failed checklist are retained. After the mapping correction and
50 focused tests plus four subtests, a fresh current-case attempt passed
read-only invalid J2 limit diagnostics, 31-object scene readback, correlated
accepted J1 +0.1° jog, ordered event JSON/report export, historical
display-only reopen/event step without accepted-state or route/preview
change, and detached Base stage/cancel. Base/Home acceptance was `NOT_RUN`
by opt-in, and planner/preview calls were zero. The case was not saved.
Slicer still exited 1 with native class-loader warnings, so its video
remains partial under `S6-U-01`. The final complete campaign, strict-current
confirmed-task positive chain, interruption and Tarun verdict remain open;
see the [28 September logbook](logbook/2026-09-28.md) and run-local diagnostics.

**28 September source and fixture follow-up:** Manual Jog actions now use
two shorter rows and the screenshot helper records actual pane/scroll geometry
with oversized-control limitations; 80 combined focused host tests and four
subtests passed. Headed readability and responsiveness remain unaccepted.
Read-only inventory of all three `SEPT24` cases found only the older
`fdi11_step6.dentocase` has a confirmed task, but its selected branch is
saved Stale with a Step 4C freshness issue. The two other cases lack a
confirmed task. No package was changed or promoted; positive full-chain
preview still requires a newly reviewed strict-current fixture and actual
complete guarded route.

**27 September invalid-draft source gate:** Read-only mechanical/reviewed
limit diagnostics and mechanical-range numeric review now let an engineer
inspect an out-of-reviewed-limit J1–J5 candidate while Guarded Jog is
disabled and Check Draft State remains available. Exact J1–J5/J6, missing-
limit/identity and accepted-state boundaries remain fail-closed. Two Luna Max
workers used disjoint façade/test and panel/test ownership. Focused checks
passed 15 façade draft tests and 16 UI tests; the final combined suite passed
114 tests, with Python compilation and diff checks passing. This is
**Implemented / Unit Verified** only. The final integrated headed campaign
must show the invalid candidate, explanation and unchanged accepted robot;
recording/export/reopen, two-area UI and full-chain boundaries remain open.

**27 September recording source gate:** Failed current manual identity
preparation now freezes the prior active ledger before another Base/Home
event can be appended. A successfully committed Base/Home action reports its
record unavailable if current identity preparation failed. Export retains all
completed sessions in order plus a distinct active record, validates each
schema-1.0 fingerprint and writes JSON with a readable companion report.
Two Luna Max workers owned disjoint facade/test and shell/test files. Focused
checks passed 13 facade and 4 export tests; their combined host suite passed
120 tests, with compilation and diff check passing. This is **Implemented /
Unit Verified** only. Per-sample TCP/axis/native evidence, display-only
reopen/replay, uncertain Base commit reconciliation and representative GUI
acceptance remain open under `S6-LIVE-01`.

**27 September uncertain Base source gate:** `reconcileManualBaseAcceptance`
reuses the current simulation scene-sync owner to re-establish the restored
accepted Base baseline. It clears the uncertainty latch only after current
identity, unlocked baseline, acknowledged audit/Base fingerprint/object IDs
and unchanged post-sync state agree. Candidate and failure evidence remain;
cancel/restage are blocked while unknown. The explicit UI control never
mirrors or accepts the draft. Two GPT-6 Luna Max workers owned disjoint
façade/test and panel/widget/test files. Focused façade checks passed 14 tests,
focused UI checks passed 3 tests, and the stable combined host suite passed
128 tests with compilation and diff check passing. This is **Implemented /
Unit Verified** only; live native reconciliation and Home uncertain-commit
closure remained open at that checkpoint.

**27 September uncertain Task Home source gate:** An ambiguous post-save Home
result now freezes the pre-save record/revision and non-Home manual identity.
`reconcileManualTaskHomeAcceptance` clears uncertainty only after proving the
expected new validated Home, current Base/profile/strict guard and audit,
correlated read-only native J1–J5 state with complete scene objects, fresh ROS
monitor and displayed state. It performs no second save or jog; failure
retains the staged candidate, latch and failure evidence. The dedicated UI
action disables Accept/Cancel while unknown. Two GPT-6 Luna Max workers owned
disjoint facade/test and panel/widget/test files. Focused façade checks
passed 10 tests, focused UI checks passed 4 tests, and the stable combined
host suite passed 132 tests with compilation and diff check passing. This is
**Implemented / Unit Verified** only. Native uncertain-commit proof, complete
motion evidence/reopen, two-area/full-chain integration and Tarun's verdict
remain open under `S6-LIVE-01`.

**27 September ordered motion-sample source gate:** Schema 1.0 now accepts
optional exact monitored joints, TCP world pose/point and unit drill axis
while preserving older records and historical-only status. The façade records
ordered requested/accepted/rejected/unknown jog evidence with native guard
facts, threshold and measured distances separately, and identity-checked FK
only when available. Rejected geometry remains labeled as a rejected
candidate; unknown events do not infer accepted TCP or route authority. Two
disjoint Luna Max workers owned schema/test and facade/test files. The schema
suite passed 53 tests; the stable combined state/facade/UI host suite passed
186 tests, compilation and diff check passed. This is **Implemented / Unit
Verified** only; path display, historical reopen/replay, native GUI samples
and final operator acceptance remain pending under `S6-LIVE-01`.

**27 September historical manual record source gate:** Validated JSON import
and event-by-event historical display now reopen one record or an exported
array without restoring live state. A transient renderer shows accepted TCP
segments broken by rejected/unknown outcomes and distinct candidate markers;
no phase-path nodes, guard, robot joints, Home, route or preview are touched.
Two disjoint Luna Max workers owned bridge/new path test and panel/shell/UI
test files. The bridge path suite passed 3 tests, UI suite passed 25 tests,
and the stable state/facade/UI/path suite passed 194 tests with compilation
and diff check passing. The event list is bounded to 10,000 imported events.
This is **Implemented / Unit Verified** only; headed visual replay, two-area
UI/full-chain authority and Tarun's verdict remain pending under `S6-LIVE-01`.

**27 September two-area/full-chain source gate:** Shared Step 6 navigator
labels and visibility now present Planning & Diagnostics and Preview & Control
without a second action owner. Partial Stage 2/3 path evidence cannot populate
the active motion plan. Preview Approach and Drill each require their exact
current complete-chain guard/plan binding; manual and reopened records remain
display-only. The interrupted-preview Block Return latch is retained. Two
disjoint Luna Max workers owned facade/test and application-shell/panel/widget/
UI-test files. Final stable five-file host suite passed 219 tests, compile and
diff check passed. This is **Implemented / Unit Verified** only. Native GUI
full-chain/interruption, responsive rendering, curated 5.10 integration,
whole-process recording and Tarun's verdict remain open under `S6-LIVE-01`
and `S6-LIVE-03/04`.

**2026-09-27 recorded headed gate:** Under Tarun's runtime authorization, the
first isolated native/exact-checkout Slicer checklist failed strict hydrated
final-template validation; its 27.033-second partial recording remains indexed
as failure evidence. Restore-time UI mutation was fixed without relaxing that
validator. A subsequent audited landmark roundoff/restore-order correction
passed 21 focused host tests and a fresh Slicer reopen of the unchanged case:
Case Foundation pose, Base and PreparedBranch were all `VALID`, and stored and
rebuilt pose fingerprints matched. The saved/current task-limits fingerprint
still differs. A second 37.676-second partial recording opened the case and
captured checklist screenshots, then stopped at disabled production Connect;
the runner had omitted Load Robot and Import Planning Context. Neither run
submitted a jog. Run-local diagnostics, video manifests, checklist JSON and
logs are indexed from today's logbook. Next: source-check the production
prerequisites and screenshot framing, then repeat one serialized recorded
trial with exact provenance. Manual solver acceptance and Tarun's verdict
remain pending.
| 3 | `S6-LIVE-02` | 0 | **Completed 2026-09-23:** independent full-chain guard implementation and native evidence are retained; the backlog row was removed because no acceptance action remains under this ID | Preserve as an invariant for later routes: strict bounds/phase/identity, exact J1–J5 state, separate spindle-speed domain, narrow contact policy and failed locked-route preservation |
| 4 | `S6-LIVE-03` | 0 | Completed-phase reverse-history Return Home is implemented; FDI31 repeat-loop acceptance is `NOT_RUN` because Packet E stopped at its first-invalid Stage-3 result. Tarun chose **Block return** for an interrupted phase after accepted motion. | Preserve the exact accepted prefix, last accepted/monitored state and rejected requested/evaluated state with native reason when applicable; latch Incomplete/AwayFromHome and block further preview and normal Return Home. Exact-prefix guarded reversal is a separate future feature/acceptance gate. For a Complete route only, trial Approach→Drill preview→guarded Return Home→replan/route choice after the preceding planner verdict. |
| 5 | `S6-LIVE-04` | 0 | Implemented; FDI31 playback/restore acceptance is `NOT_RUN` because Packet E did not complete | Confirm speed, ordered acknowledgements, visible stage paths, route lock state and current re-plan only for an accepted Complete target package |
| 6 | `S6-LIVE-05` | 0 | Historical x4 Goal-1 evidence is retained only as a negative diagnostic; clean-case acceptance is not yet run | Select a reviewed post-surgery/clean case with finalized guide/tool geometry, then complete the full guarded loop |

### Stage 6.5/6.6 planner interaction correction (2026-09-13)

The existing bounded diagnostic candidates are now an explicit operator choice
surface. The dialog keeps last-valid/first-invalid evidence and separate
Stage 1/2/3 display paths, then permits **Use Selected Route (replan)**,
**Lock + Replan Selected Route**, and **Unlock Saved Route**. Only a candidate
with `full_chain_candidate_status=Complete` can be applied or locked. A route
choice is identified by route type, IK seed, clearance sample and committed
axial frame; if the current planner cannot regenerate that identity as a
complete full chain, the request fails without activating another route.

The saved representation is the existing current motion-diagnostic JSON's
`full_task_outcome.plan_selection` extension. It stores route intent only and
never executable waypoint arrays, ROS/MoveIt validity, guard state or live path
buffers. Reopening a case therefore restores the selection/lock label and
requires a fresh current plan before Goal 1 or Goal 2 can use it. A changed
task, base, branch, collision audit or trajectory makes the diagnostic stale;
the saved selection cannot override that invalidation. Runtime, exact-package,
Step 5C geometry and normal-window acceptance remain open and are not implied
by this source correction.

The alternate-route apply path is transactional: it preserves the prior active
transient plan and saved diagnostic identity when the requested fresh re-plan
fails. The exact-case smoke now also accepts an expected FDI, can lock the
selected complete route, writes a detailed diagnostic file, saves a valid
`.dentocase`, and optionally reopens it to verify that route intent survives
without restoring ROS runtime state. The new serialized matrix launcher remains
a downstream six-target tool. The current acceptance campaign uses the same
exact-case runner serially for FDI31, FDI41, FDI11 and FDI21, each with its
own save/reopen evidence. A target-specific first-invalid result is retained
and the next tooth awaits explicit packet approval; missing required anatomy
is reported rather than synthesized by the planner.

The exact-case save path is fail-closed beyond ZIP/checksum validity. It records
and checks the current outer bundle schema, DentoCase/Case Foundation/registry
schemas, one selected current PreparedBranch, planning-pose and Step 5C
verification revisions, final-guide schema 2.0 and verification state, empty
save-time freshness issues, and the saved trajectory FDI identity. The final
guide schema is included in workflow lineage for manual package inspection.

The planner implementation additionally hard-stops stale or missing
PreparedBranch/Step 5C evidence, preserves the exact requested target depth,
audits the package again after post-hydration event drain with recovery-scene
rollback on failure, and requires the current-frame single-dock geometry gate.
These are source constraints; they do not close the open runtime, package
integrity, geometry, PreparedBranch, or normal-window acceptance records.

### 2026-09-14 exact FDI31 campaign result — earlier r2 record

The authoritative source package
`data/Slicer_Saved/SampleStudy1/dentobot-case-13sept.dentocase` remains
untouched (`SHA-256 14ed8f0f61e0c791d31b9582af7969ce712dd80d8cfd3a33319da63d0a996a15`).
Its reviewed base-revision discrepancy was handled by a one-field diagnostic
migration followed by an explicit production save. The current foundation
package reopened with preserved source volume/segmentation, Case Foundation
pose/landmarks, base matrix and lineage identities. The generated FDI31 package
is `data/dentobot-runs/stage6-target-generation-fdi31-current-20260914-r2/FDI31/case.dentocase`
(`SHA-256 3c8acf0ea9ba701c569b5173198208912368ca87b33283987acabfcb13bc932e`),
outer schema 2.0 and workflow/registry schema 3.0.

The reopened package contains exactly one current eligible PreparedBranch
(`guide-5c0da27697aceceb8f14`), current Step 5C evidence, four open bores, zero
residual channel occupancy, one connected printable solid and no closed-jaw
duplicate dock. Atomic failed activation preserved the prior active state.
The synthetic phase-guard runtime check also passed its J1–J5, bounds,
self/world/non-target collision, burr-guide warning, overshoot, retraction and
spindle-policy checks.

The exact simulation smoke was then run against that reopened package. Both
bounded candidates reached the requested `6.671904931162032 mm` target distance;
Stage 1 and Stage 2 passed. Candidate 0 was rejected at composed waypoint 237;
the selected candidate 1 was rejected at composed waypoint 274 (Stage 3
waypoint 27) by the authoritative guard because
`dentobot_target_tooth_2.25.127809691704402484963988182477922906518` contacted
`pneumatic_spindle-Copy`. The locked spindle value remained zero, requested
depth was not shortened, no template collision exclusion was active, and no
collision policy was changed. This is the current first-invalid exact-case
diagnosis, not planner success. Goal 2 completion, guarded Return Home,
repeatability, playback and route-intent save/reopen remain gated by a complete
Stage 3 route and therefore were not claimed.

**Current-source correction check (r13):** The generated current package is
`data/Slicer_Saved/SampleStudy1/FDI31/packet-a-fdi31-20260914-r7/FDI31-step5c.dentocase`
(`SHA-256 5440961c2f1464df10adec3dfb6ab59f8a0e412c6074cae7852d8150babe4fff`);
its verified STL is
`data/Slicer_Saved/SampleStudy1/FDI31/packet-a-fdi31-20260914-r7/DENTO_Final_Printable_Template.stl`
(`SHA-256 ccee3e597b7e579b0224a31f00308ee1d65e42bc89ac17bf9c68330d5bcec425`).
The approved r13 exact check used source HEAD
`3af2d864449679ead25398899d6325aefb50595a`, current diff fingerprint
`7e4e24d6278ba8bca98eb91bdf8902c2e6a018718b666e730e9fb97d6468be1c`, the
current rebuilt `collision_guard` binary
`9667b3aa6091db70cbb32c118af68af8f1d43179f099c6344f9184e2549c9ce9`, and
the pinned local image digest
`sha256:544c5b759ccef7ce6c41157bbd7bd8b602657de367f1f6b71352de054c81b019`.
Both direct and seeded candidates reached the exact FDI31 endpoint. The
selected direct candidate passed Cartesian Stage 1 and Stage 2 and was then
rejected by the current native guard at composed waypoint 255 / Stage 3
waypoint 27; the seeded candidate reached the corresponding Stage-3 boundary
at composed waypoint 295. Both failures were the same strict collision between
the selected FDI31 tooth and `pneumatic_spindle-Copy`. The requested depth,
saved base and J6-zero policy were unchanged. The run is a target-specific
`FIRST_INVALID`; Goal 2, Return Home and repeat/playback are `NOT_RUN`.

Evidence: `data/dentobot-runs/fdi31-foundation-current-20260914-r3/`,
`data/dentobot-runs/stage6-target-generation-fdi31-current-20260914-r2/FDI31/`,
`data/Slicer_Saved/SampleStudy1/FDI31/packet-a-fdi31-r7/diagnostics/FDI31-stage6-exact-r13.json`,
`/tmp/dentobot-verification/step65-fdi31-20260914-r13/runtime.log`, and the
dated 2026-09-14 logbook. No further blind whole-flow retry is authorized
until the guide/tool/base geometry owner explains or corrects this contact
without weakening the guard.

## P1 Case Platform / Simulation Studio — blocked by `S6-LIVE-05` and headless step coverage

2026-09-24 operator sequencing update: `DCP-00` also inventories the current
operator workflow step by step, including preparation, Step 6 and save/reopen,
and records a production-path headless automation command, input identity,
result and first failure for each step. Existing focused checks count only for
the exact behavior they exercise. Close gaps under the existing step owners and
keep Studio implementation on hold until every step is headlessly automatable
and verified, in addition to `S6-LIVE-05` acceptance. Headless evidence does
not replace Tarun's required normal-window verdict or authorize runtime runs.
`UI-P3-01` remains the later cohesive functional GUI/UX wrapper. Continue
bounded usability, accessibility, visibility and truthful-feedback repairs in
the current GUI under their existing task IDs when needed to operate or verify
the workflow; defer speculative layout/polish that depends on unsettled Studio
functions. No priority or planner-pause change follows from this update.

The read-only existing-script reuse index is
[TESTING_VERIFICATION_SCRIPT_INDEX_2026-09-24.md](diagnostics/TESTING_VERIFICATION_SCRIPT_INDEX_2026-09-24.md).
It inventories current code and matrix coverage before `DCP-00` acceptance;
it does not satisfy the per-step evidence gate or authorize execution.

| Order | ID | Priority | State | Entry condition |
|---:|---|---:|---|---|
| 1 | `DCP-00` | 1 | Planned | Track A full loop accepted; freeze façade/backend handoff and verify headless coverage of every current workflow step before Studio implementation |
| 2 | `DCP-01` | 1 | Complete as planning record | This 2026-09-05 supersession; no implementation work beyond controlled docs |
| 3 | `DCP-02..08` | 1 | Remaining work deferred; promoted P0 subset is under correction | `DCP-00`; reuse accepted registry/environment/persistence rather than implementing them again |
| 4 | `DCP-09..10` | 3 | Software/native bounded pass; operator review open | Case/platform foundations accepted; clean library evidence below |
| 5 | `DSS-01..05` | 1 | Planned | Data/platform foundation accepted; migrate Track-A behavior without changes |
| 6 | `DSS-06..12` | 1 | Planned | Guarded Preview parity accepted |
| 7 | `DHW-01..02` | 1 | Planned | Explicit later safety/architecture approval |

## Legacy task aliases

`S6-P0-01` full-chain planning is continued under `S6-LIVE-01..05`.
`S6-P0-02` restore continues under `S6-RESTORE-ROBOT-ROS` and the P0
PreparedBranch checks. Their old auto-reconnect and fixed-roll instructions
are historical. `S6-P0-DEPTH`, `S6-P0-CLEARANCE` and
`S6-P0-ANATOMY-REVIEW` retain historical evidence in the 2026-09-04–09
logbooks; no retired-case override is an active recovery action.

`AGENT-ASTRA-LOW` is superseded by `AGENT-SOL-RESTORE`; model policy is
maintained only in AGENTS.md, with dated rationale in DECISIONS.md.

## Priority task contracts — migration baseline

| ID | Priority | State | Entry condition | Next acceptance action |
|---|---:|---|---|---|
| `S6-P1-01` | 1 | Partially implemented; anatomical safeguards pending | Current P0 correction accepted | Add bilateral condylar/crown regions, exact-source snapping, MPR review and representative anatomy acceptance |
| `S6-P2-01` | 2 | Planned | `S6-P0-02` checkpoint matrix understood | Implement one post-load visual integrity panel for Steps 1–6 with Current, Needs attention, Stale, Blocked upstream, and Rejected states |
| `S6-P2-02` | 2 | Planned | `S6-P1-01` accepted | Add smooth display-only incisor-gap preview and one explicit commit action |
| `S6-P2-03` | 2 | Headless load, Step 4C/5B and Step 2 progress passed; Step 6.3/6.4 source checks passed; broad root-cause acceptance open | Tarun cannot launch Slicer manually. Latest headless Connect passed in 36.558 s with 31 acknowledged objects and 4.587 s maximum Qt gap. Disconnect now reports 0–31 removals and passes in 15.488 s, but native `RemoveRobot` caused an 8.293 s UI gap. A preceding run exited abnormally during load; Slicer exit remains 1 on shutdown. | Focused façade/bridge tests passed 63/63. Treat Connect/Disconnect as headless functional passes, not full responsiveness or desktop acceptance. Next: measured native teardown/load/shutdown corrections. Step 6.4 planner remains under `S6-LIVE-01` pause. No fake percentage or ETA |
| `W4B-P2-SUPPORT-AUTO` | 2 | Source suggestion and pure boundary checks complete (2026-09-15); normal-window UI/runtime acceptance pending | Current P0 PreparedBranch correction accepted; preserve Step 4B ownership | Auto-suggest the four nearest same-jaw support teeth—two on each side in dental-arch order—then require ordinary Step 4B review/lock. Verify the current arch selector in a normal window, with manual editing for edge, missing, or unsuitable teeth; the one-row selected-jaw layout remains part of `UI-P3-01` |
| `UI-P3-01` | 3 | Planned; broad revamp deferred | Studio functional acceptance and Priority 1–2 correctness | Design the final functional GUI/UX wrapper around settled behavior, prove Legacy parity, incorporate the `W4B-P2-SUPPORT-AUTO` single-row jaw requirement, and add no new MRML/ROS side effects; current-workflow fixes stay with existing owners |
| `S6-U-01` | 4 | **Completed 2026-09-28 for the reproduced no-case connected lifecycle.** Native robot removal now precedes subscription, publisher, ROS-node and ROS shutdown; each robot stops PlanningSceneMonitor activity and releases RobotModel/RobotModelLoader state. Two source-contract tests and ten Step 6 lifecycle tests pass. A final headed simulation on the isolated 5.10 build recorded connected robot, publisher release and widget cleanup, then exited Slicer `0` with no class-loader warning or fatal signal. Recorder/FFmpeg exited `0`, the 26.033 s video manifest is complete, and no owned process survived. The pinned installed package remains unchanged and the earlier partial/failure evidence is retained. | S6-LIVE-01 final whole-run recording previously depended on this gate | Accepted for the narrow reproduced shutdown condition. The final case-bearing Step 6 campaign must use the corrected reviewed native package and independently prove its own zero exit. This does not accept planner, preview, responsiveness, hardware or operator usability. See the 28 September logbook and `s6-u01-final-headed-20260928-0hCREB`. |

**2026-09-30 case-bearing `S6-U-01` status:** Preserve the accepted no-case condition above.
**R18 causal capture:** GDB located the reproduced SIGSEGV in asynchronous Python traceback dumping, with the GUI thread rendering. The watchdog scheduling owner has been removed while retaining Qt latency/phase logs; 84 focused host checks pass. R19 is the bounded recorded case-bearing confirmation. This does not attribute every earlier crash or accept unrun TCP/full-chain/save/reopen gates. See the dated logbook and r18 diagnostic package.
**Later authorized continuation:** Tarun approved the narrow native-debugger strategy. R15 passed workspace generation returned-current and strict restore under GDB; inferior exit 0, no signal, validated 348.9 s recording. This is non-reproduction, not a native defect fix. The next approved gate is focused case-bound 6.3 workbench verification, before planner/preview. Keep intermittent stability and full-case acceptance open; r15 original report and diagnostic-finalizer limitation are explained in the dated logbook and run-local diagnostics.

Case-bearing r6 and fresh offline r7 exited 0, but r8 stopped
during workspace revalidation; direct-child r9/r10 proved intermittent
`SlicerApp-real` SIGSEGV 11 at post-hydration and Task Home connectivity.
Cgroup `oom_kill=0`; no native backtrace or retrievable core was obtained.
The three-failure retry ceiling is reached for this distinct condition.
Do not infer robust case-bearing lifecycle acceptance from r6/r7, and do not
start another autonomous runtime trial. The next bounded diagnostic needs a
native debugger/backtrace strategy and Tarun's direction. Final case-bearing
acceptance still requires a complete zero-exit whole-run recording. See the
[30 September logbook](logbook/2026-09-30.md) and r8–r10 diagnostics.

## Unprioritized task contracts — migration baseline

| ID | State | Next bounded action |
|---|---|---|
| `S3-U-01` | Scan/run inspection workflow implemented; focused Slicer PASS | Operator reload and visual check on the real preDental/postDental scene; confirm Step 0–3 context bar, source-paired switching, compare, rename, and Step 4 handoff |
| `S3B-ROBOT-PLACEMENT-MIRROR` | **Accepted 2026-09-19.** Operator confirmed 3A/3B path, robot visibility through propose/lock, 6.1 mirror PASS, and Step 4A target-tooth scroll. Source: commit `8432210`; evidence `logbook/2026-09-19.md` §7; focused pytest 26 passed. | — |
| `S6-U-04` | Fix implemented; normal-window acceptance pending. Goal 1 diagnostics **Close** did not dismiss the window before or after evidence review, forcing use of the title-bar X | Run Goal 1, open diagnostics, verify **Close** dismisses it both before and after **Mark Current Evidence Reviewed**, then reopen it and confirm no stale callback/window state |
| `S6-U-02` | **Closed 2026-09-19 by operator** at simulation/lab scope. Accepted path: `VirtualForeheadPriorV1`, Step 3B/6.1 offline placement mirror, manual nudge/lock. Does not record mount-face CAD or measured patient-contact→base metrology; defer to `A-001` / `A-038` if hardware truth is required | — |
| `W4-U-01` | Active design | Define reviewed crown region and MPR contract, then implement source-fingerprinted Entry snapping |
| `W5-U-01` | Source gate updated 2026-09-19: new-case trajectory-guide hole default is **2.1 mm**; builder/UI floor remains 2.0 mm. Live Step 5B lifts in-memory holes below 2.0 mm to 2.1 mm so section-2 controls stay editable. The immutable 13-Sept source file may still store 1.5 mm on disk. Representative/physical fit acceptance and optional export manifest remain open | In a live session, confirm section-2 hole shows ≥2.1 mm (or ≥2.0 mm if already valid), controls are editable, and Build/Update is not blocked by the 1.5 mm legacy hole. Do not mutate the immutable 13-Sept file bytes or frozen Campaign-1 r7/P3. |
| `IMG-U-01` | Representative acceptance pending | Compare authoritative masks and optional display previews on governed CBCT; define acquisition/artifact/segmentation uncertainty evidence |
| `W4C-U-01` | Design and representative acceptance pending | Validate support-aware docks, collisions, channels, rail roles, tolerances, and the non-parallel-trajectory versus one robot-axis constraint |
| `W5-U-02` | Representative and physical acceptance pending | Validate the read-only Step 4B support pack in Step 5A, editable margin, undercut/removability, shell contact, seating, and terminal support on governed anatomy/phantom |
| `W5-U-03` | Representative acceptance pending. **DENTO-NOTE 2026-09-07:** Step 5B unified-template creation needs detailed operator testing beyond smoke. During 2026-09-10 Step 4A verification, the combined runner passed Step 4A display, assisted pulp and FDI11 shell stages, then failed independently at unified fusion with 10 occupied volumes `[60677, 9, 4, 3, 1, 1, 1, 1, 1, 1]`. Read-only diagnosis traces the regression boundary to the current `W5-U-04` extended through-bore subtraction: the same case passed on 2026-09-08 before dock channels grew from 5.6 mm to 9.6 mm; FDI11's 2.2 mm bore leaves 9- and 4-voxel slivers above the conservative 0.1 mm³ cleanup ceiling. The supplied FDI31 run-2 Step6x5 package is a successful comparison case (saved raw regions `[45846, 1]`, cleaned to one), not the failed artifact | Localize the FDI11 slivers and correct the shared bore/attachment construction under `W5-U-04` without relaxing the one-solid gate or blindly raising the artifact threshold; then run current Step 5B fusion and Step 5C PASS/WARNING/FAIL on both FDI11 and FDI31, reopen, stale-lineage, channel-preservation, and one-STL flow; include dock/rail visibility and printability review |
| `W5-U-05` | **DENTO-NOTE 2026-09-07 (UX / workflow).** Primary unified-template dimensions are in expanded section 2. 2026-09-19: section-2 spinboxes are force-enabled; live sub-floor holes lift to 2.1 mm. A clear owned Reset, interactive view while sizing/fusing, and full upstream dimension/lineage coupling still need representative UX work | Confirm section-2 editability in the live scene after Reload/restart; remaining Reset and interactive 3D inspection stay open. Do not relax the 2.0 mm builder floor. |
| `VIEW-U-01` | **Priority 1; source correction and focused Slicer evidence complete, operator-visible acceptance pending.** On the operator-supplied FDI21/31 headless-verified case (SHA `c16e0406…d1c1d`), the first reproduced ghost appeared when the Step 4A all-teeth 2D/3D preset exposed 28 closed-source segments in 2D; source node `vtkMRMLSegmentationNode1` has no parent transform, while moving-lower proxy `vtkMRMLSegmentationNode3` uses `vtkMRMLLinearTransformNode4`. The shared opened-jaw normalizer now suppresses source aggregate 2D/3D visibility and presents selected copied segments through derived displays. Target-priority highlighting and source Views-tree toggles call the same normalizer, while derived hide/show remains operator-controlled. Source anatomy, geometry, planner and collision state are unchanged. Final focused temporary save/reopen emitted `VIEW_U01_REOPEN_PASS` on the resulting revision. Opacity controls remain `VIEW-U-02`. | Tarun's normal-window visual verdict is needed before closure. Preserve source data and Legacy/New parity; coordinate any branch/restore issue with `S6-REUSABLE-CASE-SETUP`. Operator 2026-09-24: finish this before `W4-U-02`. |
| `VIEW-U-02` | **DENTO-NOTE 2026-09-07.** Viewer no longer exposes **2D / 3D opacity sliders for masks**. Legacy still wires `segmentation2DOpacitySlider` / `segmentation3DOpacitySlider` in segmentation UI; operator path (likely New GUI / View Controls) lost them. Needs a **deeper UI/UX plan**, not a one-off restore | Map Legacy vs New GUI vs View Composition ownership of mask opacity; design always-available 2D fill/outline + 3D surface opacity controls (stage-safe, display-only, scene-persistent); plan parity with CBCT opacity and group visibility; implement after written UX plan acceptance, then close with normal-window trial |
| `S6-U-03` | Experimental design; not planning authority | Derive only confidence-labelled observed oral-air surfaces when suitable open-mouth/phantom data exists; keep unobserved space occupied/unknown |
| `CASE-U-01` | Backlog | Define and implement an offline no-ROS migrator for contaminated historical MRML/MRB scenes; never load them into a live ROS process |
| `PLAT-U-01` | Blocked by clean-image acceptance | Rebuild the pinned Ubuntu inference image and accept dependency, backend, Bridge, Slicer import, and persistence behavior without mutable-container repair |
| `PLAT-U-02` | Retired as a primary install; retained as an explicit native Windows Steps 0–5 fallback. Source hides Step 6 and blocks its automatic runtime restore; real-host regression pending | On a Windows workstation, run the renamed fallback check and verify Steps 0–5 plus absence of Robot Simulation; keep native Windows ROS out of scope |
| `PLAT-U-04` | Direct Docker Engine inside WSL2 is the approved default and `WINDOWS_SETUP.md` is canonical; Docker Desktop WSL integration is an exclusive alternative. One Desktop install passed recorded WSLg/CUDA startup; the direct-Engine machine still lacks exact acceptance evidence | Capture the second machine manifest and approved check-only, GUI, segmentation, and simulation evidence; reconcile an isolated release revision, create/advance `stable/lab`, and publish a new immutable lab tag and image identity |
| `PLAT-U-05` | Ubuntu NVIDIA dual-GPU setup and launcher support integrated; laptop `--check-only` and in-container CUDA passed, while IITM CPU regression remains pending | Run the documented check-only gate on the IITM CPU workstation after updating to the integration commit; retain CPU configuration unless CUDA is intentionally adopted |
| `PLAT-U-06` | Active investigation: the fork base already includes upstream's Slicer 5.12 test commit, current upstream is only three non-runtime-code commits ahead, while the accepted derivative image still uses Slicer 5.10.0 | Preserve the 5.10 rollback; create an isolated 5.12.0 upgrade branch, merge upstream, capture/audit the uncommitted fork APIs, build from the upstream 5.12 digest, then request approval for the staged compatibility and performance gates in `SLICERROS2_5_12_UPGRADE.md` |
| `PLAT-U-07` | Data folder created; initial pilot partially synced with 7 of 17 approved `.dentocase` bundles uploaded; 10 bundles over the connector's 100 MB limit remain pending | Finish the remaining individual bundles in `IITM Dentobot/Data` through the authenticated browser, then verify metadata and checksums. Keep `active-development-ubuntu` docs-only and do not sync the whole `Slicer_Saved` tree or raw/non-anonymized case bundles |
| `PLAT-U-03` | Deferred observation | After an approved reboot, record overnight CRD/GDM availability and resource behavior before closing workstation stability |
| `QA-U-01` | Unresolved | Diagnose why the aggregate Slicer test wrapper returns nonzero although isolated members reach PASS; do not treat isolated PASS as aggregate closure |
| `ROS-U-01` | Future design | Define geometry-preserving medical-image and transform semantics before broadening ROS scope beyond current bounded simulation interfaces |
| `POC-U-01` | Strategic parallel lane | Freeze one narrow task and acceptance thresholds, then run representative software, print/seating, registration, and error-budget work |

### `PLAT-U-07` — Multi-workstation Git and saved-case exchange

- **2026-10-07 installed-command result:** selected B checkout checkpoint
  `515879a`; 27 helper checks and 13 affected host checks PASS. Installed
  `dentobot smoke --run` executes one fresh private-Xvfb no-case run: loaded
  source identity, all five reloads, actual Slicer0/launcher0, video checksum
  and decode, clean source and owned cleanup all PASS. Runtime Verified only
  for this synthetic contract; no case/performance/operator or A/B parity claim.
  [Evidence](/home/light-tarun/dentobot/data/dentobot-runs/2026-10-07/PLAT-U-07-smoke-20261007T173507Z-8aac2b8dd7bc/diagnostics.md).
  Commands are available on B while A is offline; transfers require A online.

- **2026-10-07 command/verification continuation:** operator explicitly requests
  B-hosted handoff and runtime verification while A is offline. Install the
  selected-checkout commands, checkpoint the seven owned harness/controlled
  files locally, then validate one fresh pinned B no-case five-reload run.
  Reuse `runtime.slicer_reload`, one private display and serialized resources;
  no case/planner/build scope or Git publication. Latest published A source
  remains the base; offline unpublished state, image/case parity and operator
  migration acceptance remain open. Evidence: [7 October logbook](logbook/2026-10-07.md).

- **2026-10-07 B bounded reload result:** selected runtime checkout on
  `runtime/B-20261007T160641Z-2313be5a`, published `a0733d25`; sole runtime
  owner while A offline. Harness-only More-menu correction; 11 host tests PASS.
  One no-case private-Xvfb run: source/startup PASS, five reloads PASS, actual
  Slicer0 and launcher0, stopped owned container and exact Slicer count0.
  Prior attempt retains startup PASS / pre-reload hidden-button harness failure /
  Slicer1 versus launcher0. B image differs from A; cases/operator/migration
  acceptance remain open. Source/test edits uncommitted, no publication.
  Evidence: [/home/light-tarun/dentobot/data/dentobot-runs/2026-10-07/PLAT-U-07-B-reload-20261007T170938Z/diagnostics.md](/home/light-tarun/dentobot/data/dentobot-runs/2026-10-07/PLAT-U-07-B-reload-20261007T170938Z/diagnostics.md),
  [7 October logbook](logbook/2026-10-07.md).

- **2026-10-03 destination launcher result:** Operator requested testing.
  50 focused launcher/profile tests, syntax/self-check and real check-only
  preflight PASS; all3packages built from the updated sources. Normal startup
  passed simulation readiness and loaded DENTOWorkflow in a visible Slicer5.10
  window with current native libraries. Left open for operator. Nonblocking
  extensions-directory warning retained. Shutdown, cases/FPS/operator verdict
  and full migration/cutover remain open; see today's logbook.

- **2026-10-03 local source handoff:** Operator explicitly requested latest
  progress as-is. Destination DentoBot `main` fast-forwarded
  `0cc70f2` → `3997458` (94 commits); native source advanced
  `17f9993` → release-pinned `ece3c42` on its published tracking branch.
  The seven local September-30 controlled files were preserved in an
  allowlisted Git stash and checksum-backed overlay backup before pulling.
  New root launcher link installed by the non-overwriting bootstrap.
  Source identity/parity inspection passed. At that source-only checkpoint,
  compiled runtime was unverified; the subsequent launcher result above
  verifies the three package builds and startup only. Cases, image parity,
  source-station dirty work, operator verdict and primary-writer cutover remain
  unverified. Migration and the distinct case-exchange obligation remain open;
  evidence and preservation paths are in the 2026-10-03 logbook.

- **Priority:** Unprioritized.
- **Operator request:** Keep script development in the repository while
  exchanging the saved Slicer case work needed by multiple workstations.
- **Outcome:** Each workstation reproduces the tracked source and runtime
  layout from Git; an individual approved `*.dentocase` can be materialized
  under the local `data/Slicer_Saved/` layout when needed.
- **Important payload boundary:** A `.dentocase` is not metadata-only. Its
  outer archive contains an MRB, and the embedded MRB can contain CBCT-derived
  NRRD volumes, segmentations, and anatomy. Therefore the exchange path is
  limited to synthetic or explicitly approved de-identified bundles. The
  folder itself is not a blanket privacy approval.
- **Boundaries:** Do not sync the whole `Slicer_Saved` directory, standalone
  `.mrb`, `.stl`, `.nrrd`, screenshots, run records, credentials, or
  engineer-owned records. Do not add a watcher, Drive mount, or automatic
  whole-folder mirror.
- **Acceptance:** The operator names the separate Drive location and confirms
  the permitted bundle class; one bundle is uploaded or replaced in place only
  after checking its Drive name/parent; the downloaded bytes match the source
  checksum; and the logbook records the artifact class, source revision,
  checksum result, and evidence boundary without patient identifiers.
- **Current state:** Policy and queue entry were recorded on 2026-09-12. On
  2026-09-13 the operator approved anonymous `.dentocase` exchange, the
  `IITM Dentobot/Data` folder was created, and 7 of 17 local bundles were
  uploaded into the preserved relative layout: the root bundle, FDI11, and
  FDI31. Ten FDI14/FDI44 bundles remain pending because the connector rejects
  files larger than 100 MB; the browser fallback is waiting at Google sign-in.
  No standalone `.mrb`, `.stl`, `.nrrd`, screenshot, run record, or
  engineer-owned record was uploaded.

## Future track

The former F0/F1/F2 and separate .dentostudy sequence is superseded by
`DCP-*`/`DSS-*`; it is not a second implementation queue. Physical
registration/mount/controller work retains its existing prerequisites.

## Recently closed or superseded

These are pointers only; complete evidence remains in the archive, decisions,
reproducibility record, changelog, and dated logbook.

| Item | Disposition |
|---|---|
| `S6-LIVE-02` | Completed and removed from backlog 2026-09-23. Independent full-chain guard, request correlation, scene acknowledgement and TCP/spindle/burr FK evidence remain authoritative. |
| `S6-P0-BASELINE-CLEANUP` | Completed source/guard scope and removed from backlog 2026-09-23. Its remaining clean-case full-loop proof is owned by `S6-LIVE-05`. |
| Cross-tool agentic verification protocol | V1 source/pure-contract complete 2026-09-02: one canonical protocol and resource-aware matrix serve Codex, Cursor, and Claude; runtime execution remains approval-gated and serialized |
| GitHub default / overlay / Windows-lab conversion docs | `main` is authoritative; the pinned lab release and private Linux/amd64 GHCR image are published. First Windows WSLg/CUDA functional startup passed on 2026-09-07; repeatability on the next clean lab PC remains `PLAT-U-04` |
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
| Virtual open-mouth AUTO-primary GUI (2026-09-18) | Source-complete on `cursor-agent/dentoworkflow-debug-20260918`. Production path is AUTO propose → visualize → confirm → Step 4A. Manual landmarks are fallback only. Unit tests 20 passed; `runtime.auto_open_mouth_test1_post` PASS (`ARCH_INFERRED`, `landmarkSource=AUTO`). TRL-4 occlusal-plane / condyle-head ROI / DW_Derived viz remain later work, not this GUI contract. |
| Virtual forehead prior V1 (2026-09-18) | Simulation visualization/placement source-complete. Independent of robot pose. Does not close `S6-U-02`. Pure tests in `test_virtual_forehead_mount.py`. |

## Verification workflow learning session — DENTO-NOTE 2026-09-11

- **ID:** `VERIFY-LEARN-01`; **Priority:** Unprioritized; **Triage:** Backlog.
- **Operator need:** Learn the testing and verification workflow once, hands-on,
  including `py_compile`, `pytest`, `colcon build`, and how DENTOBOT decides
  what evidence is sufficient.
- **Outcome:** After one guided session, the operator can identify the changed
  subsystem, choose the cheapest sufficient matrix check, explain what
  inspection/compile/unit/build/runtime/operator evidence proves, execute or
  supervise the approved commands, find the saved logs, distinguish PASS from
  partial/nonzero-shutdown outcomes, and apply the retry/stop rule.
- **Teaching sequence:** Start at checkout root; inspect the diff and
  `Testing/verification_matrix.json`; state the question, hypothesis, inputs,
  smallest check, expected result and stop condition; create one `/tmp`
  evidence directory; run/read one `py_compile` plus `git diff --check`; run one
  focused `pytest`; explain `colcon` workspace/package/install ownership and run
  one applicable focused package build only when the stable change or explicit
  learning plan justifies it; then explain why Slicer/ROS/MoveIt and normal
  window acceptance are separate higher evidence levels. Read the first causal
  failure and evidence artifact instead of blindly rerunning.
- **Dependencies and boundary:** Wait for the active
  `S6-REUSABLE-CASE-SETUP`/Step 6 reposition handoff so the lesson uses a stable
  revision and does not verify changing files. Use existing matrix commands and
  setup instructions; create no second harness or training framework. Every
  matrix command keeps its approval class. Serialize `colcon_install` and all
  runtime resources. No robot motion, drilling, patient-facing action, guard
  relaxation, blanket rebuild/suite, commit, push or Drive write is implied.
- **Acceptance:** One bounded run record contains the selected check IDs, exact
  commands, why each was selected or skipped, exit codes/PASS markers, evidence
  paths, first failure if any, cleanup status and operator questions. Finish
  with a concise reusable checklist linked to the canonical protocol/matrix.
  This is educational completion, not proof that every DENTOBOT subsystem was
  tested.
- **2026-09-17 activation delta:** The operator explicitly selected this task
  as the active route while Campaign 1 is paused at P5. The former dependency
  on a stable reusable-case/Step-6 handoff is satisfied by the preserved P5
  result. The session must first teach and record the distinction between
  headless diagnostic evidence and GUI/operator evidence, then perform the two
  tracks above. Numeric priority remains Unprioritized; the current execution
  order comes from the explicit operator direction. Completion must end with a
  clear recommendation to resume after P5, remain paused on a named GUI defect,
- **2026-09-19 GUI-path outcome:** Operator confirmed ordinary workflow through
  Step 6.5 on `cursor-agent/dentoworkflow-debug-20260918`. First truthful live
  planner failure is Goal 1 motion-diagnostics **P1 PreEntry** (13 legs, no
  P2/P3 preflight) on
  `data/Slicer_Saved/SampleStudy1/FDI31/dentobot-case-sep19-step6.dentocase`
  (the earlier `step19` spelling was corrected on 2026-09-21).
  Teaching-session pytest/colcon checklist remains open. Planner work returns
  to `S6-LIVE-01`. Codex Campaign-1 P3–P5 is not this GUI result.

## DENTO-NOTE triage and maintenance rules

Use [AGENTS.md](../AGENTS.md#backlog-first-gate--mandatory) and
[backlog.md](backlog.md). Capture every open note once in that queue with its
stable ID, observed workflow/behavior, priority or Unprioritized, evidence,
impact, dependencies and next acceptance action; link a detailed contract here
when needed. Do not create another active queue in this file.

On completion, record exact acceptance evidence in the dated logbook, update
this record and DEVELOPMENT_PLAN.md where their contract/milestone changes,
then remove the accomplished backlog row in the same turn. Source completion
alone does not close required operator/physical acceptance. Superseded or
cancelled work requires its explicit disposition and alias mapping preserved
here/logbook before removal. No history is silently deleted.

## 2026-09-11 backlog migration and tracker crosswalk

The operator requested one pending-only planning entrypoint to prevent lost
backlogs, repeated plans and redundant implementation. `docs/backlog.md` now
owns that queue; `AGENT-PLAN-FIRST` is amended to check it first and then these
contracts/history, including when no pending match exists. This documentation
change is completed; it is not itself a pending backlog item.

Read-only source: Project Tracker `1W118Z6oDqfA6IOBXg3llCo6-IowoSAif1HxuTFK7NHU`,
Master Work Register rows 4–41 (38 deliverables; 30 unfinished, 8 complete),
Dashboard and Priority Focus through 3 September, and Decisions/Risks. Current
local September 10–11 case/priority decisions supersede older source status.
No tracker content was edited. The tracker is not an automatically readable
future authority; rule 16 still requires explicit current-message permission.

All 30 unfinished source IDs are either pending owners/aliases or mapped to
existing work in backlog.md. `A-019`, `A-020`, `A-021`, `A-025`, `A-030`,
`A-031` remain source-complete history. `A-033`/`A-034` implementation remains
closed; only their explicit platform/renderer follow-ups are retained.
`A-006`/`A-024` literature priorities conflict (P0/P1); `A-036` register and
dashboard conflict (P1/P2). These source values are preserved for later
selection, not silently promoted into the current development order.

`S6-LIVE-00` and `DCP-01` are completed documentation checkpoints, excluded
from pending work. `S5B-TERMINAL-COLLAR` defect remains verified; its remaining
normal-window/physical acceptance is covered by `W5-U-02`/`W5-U-03`.
The source-complete pressure Config-tab live flash/Hz follow-up is retained
under `A-037`; no new tool implementation or hardware authorization is implied.
The stale F0/F1/F2 `.dentostudy` rows in DEVELOPMENT_PLAN.md are removed in
favor of their already accepted `DCP-*`/`DSS-*` successor contract.

### 2026-09-28 — VIEW-U-01 / S6-REUSABLE-CASE-SETUP saved-display checkpoint

Tarun's `sept28_fdi11_step6.dentocase` and screenshots show a closed-mouth
source in the Step 6 viewport after his Base/Home/jog trial. Offline MRML
inspection found the untransformed `Post_surgery_seg` visible in 2D/3D beside
opened proxies in both Sep27 and Sep28 packages; the jaw transform did not
change. The existing display normalizer now runs after transient view-state
restoration at Slicer's save boundary and after active-stage view refresh.
Focused host checks passed 9 tests. A fresh headed open, separate production
save and reopen of the unchanged source case passed source-hidden and
opened-proxy-visible readbacks plus state-matched screenshots. The original
case remained unchanged. This is bounded runtime verification of display and
save/reopen, with Tarun's post-correction normal-window visual verdict still
pending. No anatomy, geometry, collision or planner authority changed.

`S6-LIVE-01`'s separately recorded current-case GUI checklist passed 16/16
bounded items, including one invalid draft, acknowledged J1 jog, ordered
historical export/reopen, Base Accept and current-pose Task Home Accept. It did
not test native rejection/unknown, direct real-time TCP dragging, a confirmed
task, complete-chain preview/interruption or responsiveness. The whole-process
video remains partial because Slicer exited 1 after the functional PASS marker;
`S6-U-01` retains that shutdown dependency and its exhausted retry ceiling.
Run-local diagnostics and the 28 September logbook contain exact provenance,
commands, screenshots, video and cleanup evidence. Operator robotics/usability
verdict remains PENDING.

The 28 September 6.3B Cartesian TCP slice is source and bounded-runtime
verified. It adds a separate X/Y/Z plus pitch/yaw TCP review beside J1–J5,
with opt-in keyboard mappings and a default-off **Enable TCP Drag** gate as the
only native probe activation route. Enable requires a truthy native
acknowledgement; disable or leaving 6.3 removes the probe, goal robot and
observer. Live mouse/nudge interaction uses canonical J1–J5 position-axis IK
as ghost review, with axial roll unconstrained by the five-DOF arm. Only
explicit collision-aware Solve IK stages an exact J1–J5 draft; accepted state
still requires a later Guarded Jog acknowledgement. The focused host suite
passed 238 tests. The headed no-case package
`data/dentobot-runs/step6-tcp-workbench-headed-20260928-9/` passed mouse drag,
Cartesian nudges, authoritative solve/stage, accepted-state non-advancement,
disable cleanup, zero route/preview authority, complete video, Slicer exit 0
and owned-process cleanup. Physical key events, case-bound rejected/unknown
guard outcomes, positive full-chain preview/interruption, measured normal-
window responsiveness and Tarun's usability verdict remain pending.

## 2026-09-30 — UI-P3-01 bounded Workflow Focus slice

Tarun explicitly authorizes default Workflow Focus in the Step 6 renovation checkout alongside the active “step 6.3 final fix” chat. This advances only current-workflow space recovery; the broad Studio redesign and Priority 3 remain unchanged. Outcome: compact two-row navigation/view header, secondary actions in More, hidden logo/help/Data Probe/toolbars, reversible session-only Show Slicer tools, and exact chrome restoration on module exit/reload. Preserve existing handlers, research warning, MRML/ROS/case state and readiness gates. Header/application and lifecycle/helper ownership is disjoint from the other chat's Step 6 source/test work. Runtime resources stay with that chat. Source and host verification precede one serialized visual/lifecycle check and Tarun's verdict; doubled task-height is a visual target, not a source-only claim.

**30 September integration execution checkpoint:** `514f86e` merges frozen renovation `e7cd29f` with accepted 5.10 ports; `9068658` records early runtime evidence and explicit saved-fixture shell mode. Host 601 PASS (known pre-existing size-budget failure remains visible), restore/Connect/Disconnect and inventory runtime pass with clean exits; Tarun accepts bounded Connect result. Operator-approved shell-only trial failed strict historical package jaw-motion lineage validation before shell/fusion; both failures preserved. W5-U-04 / S6-REUSABLE-CASE-SETUP own the compatible-fixture/migration prerequisite. No acceptance of full Step 6, obsolete policy, 5.12 or main promotion. Pending queue remains backlog.md; full combined acceptance follows final renovation checkpoint.

**Latest 30 September Step5B integration result:** The explicitly selected reviewed current FDI11 demo passes strict restore and all bounded shell/fusion numeric gates, with source unchanged, Slicer/recorder exit0 and complete recording. Historical package failure remains separate. Geometry PNGs are blank, so visual acceptance is pending; capture-only clipping correction `f4fa2f7` has five passing host checks, awaiting operator-directed runtime. Synthetic assisted-root setup repair is deferred under S4A-PULP-ENDPOINT, no test deletion or production-gate bypass. No full Step6/main acceptance follows.

**1 October integration source closure (existing S6-LIVE-01 / reusable-case owners):** Mechanical sibling-mixin extraction closes the inherited1600-line gate on the current integration candidate. Coordinator AST comparison preserves all231 methods and constants (55 methods relocated). Focused host538 PASS includes unchanged size/API/install checks with no deselection; compile/JSON/diff checks pass. API manifest unchanged. No newer renovation implementation is imported. Corrected Step5B runtime/visual verdict remains the active bounded gate; synthetic setup repair remains deferred, and final renovation/full combined/main acceptance remains pending. See1October logbook and integration preparation record.

**1 October corrected Step5B runtime evidence:** Candidate a09fa02 passes the unchanged current-case saved-fixture trial: strict restore16.254s, shell/fusion topology and channel checks, unchanged input, Slicer/recorder0 and complete recording/cleanup. Overview and all4dock bore PNGs are now visible on coordinator inspection. Tarun’s required bounded GUI verdict is ACCEPTED on1October: “visually accepted and confirmed”. Evidence: /home/light-tarun/dentobot/data/dentobot-runs/step5b-integration-closure-20261001/diagnostics.md. No synthetic setup/fullStep6/main acceptance is inferred.

## 1 October — bounded integration visual acceptance

**Operator statement:** Tarun: “visually accepted and confirmed”. This is the required manual verdict for the corrected current-fixture Step5B integration trial on source a09fa02 (overview plus all four dock-bore images). The bounded Step5B result is now ACCEPTED. Together with the module-size/API/install closure and538passing focused host checks, both remaining items in the current integration pass are complete.

Evidence: /home/light-tarun/dentobot/data/dentobot-runs/step5b-integration-closure-20261001/diagnostics.md; strict restore, shell/fusion metrics, unchanged input hash, Slicer/recorder exit0, complete recording and empty owned-process cleanup were recorded before this verdict. Removed the completed current-pass entries from backlog.md. No new source or runtime work is needed for this acceptance. Future verified renovation transfer and final combined/full-cycle/main promotion remain pending under existing owners; synthetic assisted-root setup repair remains deferred.

## 1 October — approved consolidation and DentoCase completion

Tarun agrees to and approves the proposed consolidation and complete DentoCase goal, with up to four GPT-6 Luna Max workers apart from the orchestrator. Available concurrency remains three workers plus coordinator; four disjoint worker scopes are scheduled with the fourth following a released slot. This supersedes the earlier transfer hold for this bounded consolidation and moves future development to DentoBot-step6-5.10-integration, branch integration/step6-5.10-reviewed-20260927. Main promotion/publication, 5.12 and robot/hardware actions are excluded. Offline full/partial persistence verification is approved by the agreed plan; runtime resources remain serialized and existing operator processes preserved.

Git evidence: integration a795f89 already contains renovation e7cd29f; no renovation commits are missing. Later source/test changes are uncommitted. Both development deltas preserved in /tmp/dentocase-consolidation-20261001 with binary patches, development-only archives and SHA manifests; engineer-owned records/generated output excluded. Forty-two clean candidate source files applied and five conflicts resolved under coordinator dispositions. Accepted performance ports, strict restoration and method splits retained. No branch/HEAD change, stage, commit, main merge or rebuild performed during parallel work.

Owned worker scopes: robot-shell/manual method reconciliation; headed runner/source/planning tests; new case inventory ownership adapter/test; DentoCase catalog fixture correction. Coordinator owns remaining DentoCase persistence/projection/bootstrap/lifecycle/semantic inventory changes, verification matrix, source review, runtime and controlled records. No worker executes Slicer/ROS/build/runtime or edits controlled records. Current pending states remain under DCP-09..10, S6-REUSABLE-CASE-SETUP, S6-P2-01, S6-LIVE-01 and S6-P2-03. Source consolidation does not close native or operator acceptance.


## 1 October — DentoCase integrated software gate

Existing owners `DCP-09..10`, `S6-REUSABLE-CASE-SETUP` and `S6-P2-01` retain their contracts/priorities. The consolidated integration source now implements schema3 stable full-case identity and per-revision package IDs, schema1/2 reads and schema2 manual-record compatibility, metadata-only SQLite catalog, explicit folder scans, saved-lineage browser, audited independent partial construction, and recovery-backed activation. Unknown semantics/ownership blocks partial construction; saved statuses and live Unverified freshness remain separate. Paired preparations stay inseparable, omitted descendants/references/verification and historical/runtime authority clear, and partial loads require independent Save As.

Final matrix-derived host union558passed2.66s; native offline attempt4 PASS, exit0, clear teardown verifies full identity, actual browser,5B/5A paired prefix projection/reopen, independent partial continuation/Save As, source preservation and failed-load recovery. Evidence: `data/test-artifacts/dentocase-integration-20261001/integration-roundtrip-attempt4/`; commands/source hashes in run.json. After runtime freeze, the only source/test edits show existing integrity-check timestamp and saved-state details in the browser; four focused browser checks pass0.07s. Modular/API/install checks5pass0.53s. No new Slicer rerun is needed for this plain presentation delta. Broader Step6 robotics/native/operator gates remain open. Tarun's DentoCase browser and independent partial continuation verdict is required; do not mark overall Project DentoCase complete or remove its backlog row before that verdict.


**Local integrated source checkpoint:** `50ce2089342aeeac9a319bf6353809252cb70e23` (`50ce208`) on `integration/step6-5.10-reviewed-20260927` contains the55reviewed source/test files. Renovation commits were already ancestors; this checkpoint records the reconciled later dirty development delta and DentoCase integration. Accepted performance-owner files remain byte-identical to a795f89. Matrix host558PASS, offline persistence attempt4PASS/exit0/clear teardown, presentation4PASS and modular5PASS provide the bounded software evidence. No main merge or push. Overall Project DentoCase remains awaiting Tarun's library/independent continuation verdict under DCP-09..10; broader Step6 robotics/responsiveness acceptance remains in its existing owners.


## 1 October — newest Ubuntu watchdog and performance transfer audit

Read-only paired081211/081153session review found3recovered >=5s gaps (12.258,5.223,5.049s), no sampled OOM/throttling/zombies/alerts. Worst gap coincided with near-one-core SlicerCPU and low sampled memory/I/O pressure; attribution unknown because Case loaded label persisted after completion. Connectivity calls native planning synchronously despite per-sample WorkflowProgress Qt updates. Shared progress close fails to reset watchdog phase; explicit action-end/idle and runtime/source identity are the smallest diagnostic correction proposal. Native request/result scheduling needs separate bounded ownership/correlation review before responsiveness implementation. No native/GUI acceptance inferred.

Current integrationbaeee90/source50ce208 contains curated ports plus newer DentoCase/Step6 source; broader mixed-branch transfer is not100%certified. NativeNVIDIA graphics profile and wider launcher/diagnostic differences remain to disposition,5.12 remains held,WSL distinct. Evidence and source findings: diagnostics/PERFORMANCE_INTEGRATION_AUDIT_2026-10-01.md. Existing S6-P2-03/S6-U-01/platform owners retained; no new queue or task IDs.


## 1 October — Step 6 chat adopts consolidated integration checkout

Operator: “checkout has been updated to step6-5.10 integration. Update progress and get ready for next changes”. This confirms this chat's future development root as `/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-5.10-integration`, branch `integration/step6-5.10-reviewed-20260927`, inspected HEAD `baeee9001a842966e01a5ae8c575f99743e3af75`; source checkpoint `50ce208` and documentation checkpoint `baeee90` are recorded existing commits, not commits created in this turn.

Read-only source inspection confirms compact J1–J5 labels/size policies, the Base lock notification transaction, strict bounds evidence and strong native cache-object references are integrated. Guard source SHA256 `b67bd8e223465a618eae66c9b72d6e8f24169c4f1c3415a5f67b00caae1913aa` matches the previously approved build source. Installed/loaded binary provenance was not re-inspected. Prior 339 affected host checks and Release build remain evidence at their original scope; consolidated records report558host passes and synthetic offline persistence attempt4, whose result.json was read as PASS/liveAuthority Unverified.

Existing `S6-LIVE-01` Priority0 retains offline/connected Base recovery, rendered joint layout and robotics/usability verdict. `DCP-09..10` retains browser/independent continuation verdict; `S6-P2-03` retains normal-window responsiveness, owned by the performance-monitoring chat. No new task, priority change, implementation, build, GUI/ROS/planner trial, main promotion or 5.12 work follows from this readiness request. Subsequent changes use the integrated source and existing contracts; prior runtime approval is not expanded.


## 1 October — bounded Ubuntu performance implementation plan

Operator requests an elaborate implementation plan. Existing S6-P2-03, S6-U-01 and platform-transfer owners retain scope/priority. Contract appended to diagnostics/PERFORMANCE_INTEGRATION_AUDIT_2026-10-01.md: three finite increments—action/runtime identity plus low-cost paging/disk counters; one responsive explicit-start workspace planning path with frozen native ownership/correlation interface; nativeUbuntu NVIDIA profile port. Exact files, two disjoint LunaMax implementation lanes per qualifying increment, cheapest checks, proposed measurable acceptance and stop conditions recorded. No code/test/build/runtime/main/5.12 execution authorized by this planning turn. Prior native synchronous-call exposure is not universal freeze attribution. Windows/WSL remains a distinct later campaign.


## 1 October — joint-editor redesign requested before implementation

Operator: “not happy with the joint sliders revamped fix, still looks ugly”; requests proper UI/UX planning before the next implementation. Existing spacing fix is unaccepted at usability scope. Reuse S6-LIVE-01 Priority0; do not reopen broad UI-P3-01/Studio redesign or infer a numeric/ROS failure. Source inspection finds setManualJogLimits expands short joint labels into long limit paragraphs, conflicting with compact fixed-height identity rows. This concrete refresh-path defect was missed by the prior spacing change; latest rendered appearance is not independently observed here.

Proposed design and acceptance contract appended to diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md: five stable ID/unit rows, exact numeric draft, coarse slider, accepted comparison/delta, compact visible blocking status, detailed limit evidence outside labels, context-specific Home/manual actions, existing single editor/backend and strict draft/command separation. Two inline alternatives prepared: All joints visible (recommended) and Precision table. They use example screenshot values/schematic tracks and perform no application/ROS actions. Design selection remains open; implementation is not performed this turn. Input commit timing, guard policy, ranges, conversions and update cadence remain separate from presentation.


## 1 October — All joints visible iteration1 implementation authorized

Operator selects “all joints visible iteration #1” and directs implementation. This supersedes the design-selection hold for that bounded joint-editor change under S6-LIVE-01 Priority0. Implement in the integration checkout, preserving shared Home/manual ownership, draft-only editing, exact callbacks/SI conversion/range policy and explicit acceptance/guard actions. No Slicer/ROS/planner/motion trial or native build is inferred. Rendered usability verdict remains required after source/host closure.

## 1 October — S6-LIVE-01 complete 6.1–6.3 UX sketch checkpoint

Operator requires a new sketch optimized for smooth continuity rather than minimalism, removing only quarantined, redundant or legacy presentations. The interactive artifact at `/home/light-tarun/dentobot/data/visualizations/step6-continuity-sketch.html` now maps every retained action in the corrected control ledger to 6.1 Robot Setup, 6.2 Task Home or 6.3 Manual/Workspace/Plan. It includes modeless viewport display controls, inline decision states, explicit return navigation, Base-drag conditions and downstream invalidation examples. Structural fragment/JavaScript/ID/required-label verification passed. No application source, ROS, planner, build or motion operation occurred. Operator design verdict, native 320/360-width fit, large-font/short-height fit and actual Base-handle target verification remain open.

Exactly two GPT-6 Luna Max workers: joint_editor_source owns only DENTORobotSimulationPanel.py; joint_editor_tests owns only Testing/test_robot_manual_jog_ui.py. Coordinator owns specifications, integration review, checks and controlled records. Source scope is native Qt stable ID/unit rows, numeric drafts, accepted comparison/delta, range endpoints and explicit outside-slider notice, collapsible detailed limits/state, contextual editor title. Test scope is focused regression/harness changes after source freezes. No worker checks against changing files. Performance watchdog/progress/resource/launcher reservation and concurrent DentoCase files are excluded and preserved. Existing input timing/wheel behavior is not altered in this presentation pass.

Smallest acceptance check: matrix pure.step6_manual_tcp_workbench (four-file host selection), compile changed source/test, diff review and whitespace checks. Question: do presentation refreshes preserve short labels and honest accepted/draft/range displays with no implicit commands? Stop after applicable passing source checks; rendered Qt acceptance is a separate bounded manual verdict. No new task or priority change.


### 2026-10-01 — DCP-09..10 clean library execution supersession

Operator confirms library loading, rejects current tree presentation and slow scan/load, and has not tried manual save/reopen. Approved implementation retains the existing DCP-09..10 owner/priority3 and overlaps S6-P2-03 performance; no new task or numerical reprioritization. Compact case table/detail pane, paged lazy queries, untrusted metadata discovery, incremental refresh, catalog-only reset, on-demand verification and operation-owned one-pass preparation replace the prior eager tree/full scan path. Two GPT-6 Luna Max workers have disjoint catalog/inspection and browser scopes; coordinator owns package/activation/projection, runtime, review and controlled evidence. Existing identity, pairing, exact lineage, schema1/2/3, source preservation and recovery/rollback remain required. Approved contract and evidence: diagnostics/DENTOCASE_BROWSER_REDESIGN_2026-10-01.md. Software completion remains separate from native performance/visual and Tarun manual continuation acceptance; pending work stays only in backlog.md.


## 1 October — performance increment 1 source and host closure

Implemented under S6-P2-03/S6-U-01: token-scoped progress action start/phase/end, nested/out-of-order and repeated-close safety, Idle restoration, and recovered-gap capture before action closes. Generic close is not success; known cancellation/error are explicit. Scheduled traceback dumping remains absent.

Launcher records one sanitized session UUID and source checkout/revision/dirty state; handoff propagates it and selects its sibling resource collector rather than the legacy checkout. UI metadata checks its actual source origin and records the watchdog file SHA256. Revision is launcher-reported, file SHA is on-disk source, not proof of loaded native binaries. Unknown dirty fingerprint, image and native identity remain null.

Five-second resource collection adds kernel paging/major-fault rates, per-device read/write bytes/s (512-byte sectors), I/O and weighted I/O time, cgroup io.stat counters, and actual collection duration. First/reset/missing counters remain unknown. Do not aggregate stacked disks/partitions or infer universal disk latency. Native Ubuntu only; GPU/host-process attribution and Windows/WSL remain outside this increment.

Verification: pure.performance_watchdog, 26 passed in 20.42s, exit0; six owned Python files compile without bytecode writes; bash -n on launcher/handoff and owned git diff --check passed. Host/fake-Qt/shell-stub evidence only; no Slicer/ROS/MoveIt/native build launched. Evidence: /tmp/dentobot-verification/perf-increment1-20261001/host-check-r3.log. Runtime metadata correlation, clean native exit and collector p95<100ms criterion remain unverified. Increments 2/3 and broader acceptance remain in backlog, with existing safety/runtime gates and 5.12 hold unchanged.


## 1 October — All joints visible iteration1 source/host closure

Selected UI implemented in DENTORobotSimulationPanel.py: five unframed native Qt rows with permanent J1–J5/unit labels, numeric draft fields, full-width sliders, compact range endpoints, accepted-state/signed-delta comparison, full-row conditional warning and collapsed Limits and state details. Shared Home/manual editor and context title retained. Dynamic limit refresh no longer replaces IDs with prose. Comparison suppresses deltas for offline/unknown/pending/reconciliation-required/uninitialized/invalid states. Detailed numerical draft summary moves into the expandable area; actionable limit/guard reasons stay visible. Existing slider/numeric callbacks, draft updates, SI conversion, reset and request bodies are AST-identical to pre-edit snapshot. No range/policy/input timing/persistence/native change.

The two originally authorized Luna Max scopes were dispatched under the then-current delegation rule. Source worker froze its file; test worker stopped on usage limit. Tarun then supplied replacement AGENTS instructions permitting solo work and said continue. Coordinator finished the interrupted test file directly, preserving parallel edits; no replacement worker/model was substituted. Review corrections included compact unavailable messages/endpoints, full-width warning, explicit IDs in details and no synthetic zero-draft delta.

Matrix-derived pure.step6_manual_tcp_workbench command, from integration checkout:
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider Testing/test_robot_manual_jog_ui.py Testing/test_ros2_bridge.py Testing/test_robot_workflow_facade.py Testing/test_application_shell.py -k 'not test_new_empty_case_resets_entire_workflow_to_step_zero and not test_saved_case_navigation_keeps_every_workspace_selectable'`
Final **312 passed, 2 deselected in1.64s, exit0**. Two unrelated case-backend tests excluded because that file is concurrently edited under DentoCase ownership; no claim of a complete four-file suite. First run310passed/2failed/2deselected: incomplete extracted Home-review harnesses omitted the new helper; coordinator added it and repeated the same selection. Regression coverage includes accepted conversion/delta, uncertainty/offline/pending/uninitialized no-delta display, stale range clearing, preserved out-of-range numeric draft, short IDs after limit refresh, reconciliation transition and existing no-implicit-command behavior.

Changed panel and test compile passed with PYTHONPYCACHEPREFIX under /tmp/dentobot-joint-editor-iteration1-20261001/pycache; git diff --check exit0. Logs and pre-edit snapshots: /tmp/dentobot-joint-editor-iteration1-20261001/. No Slicer/ROS trial, planner/motion, native build, commit/stage/push or reset. Performance and DentoCase reserved files remain untouched. Source/host scope is complete; rendered narrow/default/wide/large-font and Home/manual usability verdict remains OPEN under S6-LIVE-01. No runtime owned by this chat.


### 2026-10-01 — DCP-09..10 clean library delivery evidence

Compact native table/detail browser, ≤100rows/page, label/FDI search and status filtering, revision/location/tooth/preparation selectors, separate saved/cutoff states, theme-aware badges and collapsed copied technical evidence are implemented. Metadata discovery remains untrusted; full verification stays default for CLI. Version2catalog migrates version1 transactionally, preserves trusted inventories/digests, scans incrementally, batches writes, retains changed/missing/error/conflict evidence and clears only catalog/remembered roots after writer cancellation/generation invalidation. Prepared archive extraction validates once and retains source identity/runtime audit/recovery/rollback. Partial child reuses its verified extraction, retains ownership/fresh reopen and independent history. Exact metrics text digest reused only during restore; geometry fingerprints/audits preserved.

Final affected host94PASS0.42s and scoped diffcheckPASS. Final portableSQL hostbenchmark meets all6targets:1000 firstpage3.336ms/search2.178ms/details0.079ms;50summary2.797ms;unchanged1000scan41.284ms/0archivebytes/0validation. r29 metadata2.325ms/0geometry; fullprep96.149ms/1validation. Native threewarm equivalent full medians22.459161→17.610422s,21.589% lower, equal packageSHA/robotprofile; noROS/motion. Actual Qt renders1100×700/900×600; synthetic pairedpartial5B/5A, independentSaveAs/continuation/freshreopen/sourcepreservation/failedloadrollbackPASS exit0 and clearteardown. Native pass precedes final small title/error-detail/checked-row/filenamefallback presentation changes; final hostgate passes after them. NativeSQLite windowquery incompatibility was diagnosed in a narrow probe and replaced with a portable query; failed artifacts retained.

This is bounded software/native evidence, not Tarun's UX or manual save/reopen/continuation verdict. Existing DCP-09..10 stays in backlog.md until that acceptance. S6-P2-03 broader responsiveness and robot/planner owners remain separate. Evidence/commands/source identity: diagnostics/DENTOCASE_BROWSER_REDESIGN_2026-10-01.md and data/test-artifacts/dentocase-browser-20261001/summary.json. No stage/commit/branchchange/build/mainpromotion.


## 1 October — S6-P2-03 increment2 implementation underway

Existing native-wait contract prerequisite verified installed MoveIt2.12.4 request-builder/action-client route and isolated accepted5.10 source/build identity. One bounded Luna xhigh worker owns native motion-control pair under latest routing; coordinator Python wait/context integration passes242 host checks. Native source review/build/runtime/deployment remain pending. Until new API is deployed, workspace explicitly reports missing responsive planning rather than using blocking fallback. No build/runtime/5.12 or broader planner migration authorized. Detailed commands/boundaries in today logbook and PERFORMANCE_INTEGRATION_AUDIT_2026-10-01.md.


### 2026-10-01 — S6-LIVE-01 6.1–6.3 UX consolidation proposal

Operator requests planning of duplicate/redundant controls across 6.1–6.3. Source-derived proposal appended to `diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md`: retain Base & Connection / Task Home / Workbench & Planning owners; consolidate duplicated recovery/Home/status presentation, group workspace/limits and joint/TCP work, preserve all distinct validation/authority operations. Planning only; source/runtime authorization and operator design/visual verdict remain open. Existing iteration1 source/host result remains unchanged; no new queue or acceptance claim.


2026-10-01 S6-LIVE-01: operator narrow-module/no-long-scroll constraint and three-step interactive button-placement sketch appended to existing renovation plan. Content switches in place; secondary dialogs replace expanding detail stacks. Planning/design evidence only, source and rendered acceptance remain open.


## S6-P2-03 increment2 native source checkpoint — 1 October 2026

Four async native methods now implemented in verified isolated5.10 motion-control pair and matching canonical SlicerROS2 source; previous interrupted/unwritten status superseded. Python242host checks passed, scoped whitespace checks passed. Native compilation/wrapper/lifetime/runtime/deployment pending separate approval; installed library still lacks new API. Cancelled local authority is revoked with best-effort backend cancellation and node-recreation requirement. Source-complete does not accept responsiveness or change5.12 hold. See today logbook/performance audit for hashes/ownership/commands. NativeUbuntu NVIDIA item3 unstarted.


2026-10-01 S6-LIVE-01 operator corrects the compressed narrow-panel sketch: preserve all essential controls, especially always-discoverable ROS connection, existing virtual-forehead/automatic-Base proposal and automatic unlocked-Base viewport handles with actual-state GUI status. Existing renovation plan now contains an explicit same-step control destination ledger and drag target/authority requirement; this supersedes the incomplete sketch. Source inspection finds Step6 suppresses Base handles despite unlock helper enabling them, so implementation must resolve candidate targeting before removing that gate. Planning/sketch only; no source/runtime acceptance or new task/priority.


## S6-P2-03 increment2 deployed checkpoint — 1 October 2026

Supersedes earlier unbuilt status: isolated single-job5.10 compile/wrapper/install passed; focused empty-scene explicit-start plan SUCCESS12points,0.108s/maxQtgap56ms, consumed reply/disconnect and Slicerexit0. Reviewed native library and identical wrapper installed into normal shared checkout package after backup; independent shared-package API probe loaded all four methods and exited0. Details/hashes/commands in today logbook and PERFORMANCE_INTEGRATION_AUDIT_2026-10-01.md. This is bounded API/software integration evidence. Representative long-wait/cancellation/ordinary-window responsiveness remains open; backend MoveIt shutdown-11 reproduced separately under S6-U-01. Watchdog paired overhead and NVIDIA increment3 pending;5.12 held.


2026-10-01 S6-LIVE-01 continuity review: existing renovation plan now recommends one inline review/accept mode, single navigation presentation, three visible 6.3 tabs (Manual/Workspace/Plan), named complete diagnostic/history tools, explicit return context and truthful downstream invalidation. Essential-function ledger preserved. Existing HTML is earlier illustrative evidence; coherent state walkthrough/native fit not yet accepted. Review/design only, no source/runtime change.

## 1 October — S6-LIVE-01 continuity implementation and bounded verification

Tarun approved 6.1/6.2 implementation and subsequently approved 6.3. Integrated source now provides the accepted 6.1 Placement/Scene organization, compact five-joint 6.2 Home editor, and 6.3 Manual/Workspace/Plan workbench with named modeless complete tools and Base/Home return-context preservation. Existing callbacks, records, review/accept/reconcile gates, policy and authority are reused. Focused checks pass 411/411; final Step 6 selection passes 565/565; compile and whitespace checks pass. The real-Qt headless sequence passes all three steps and both owner round trips with draft/authority invariants preserved.

The runtime acceptance portion remains open. Case-bound runs `s6-live-01-step63-repeatability-20261001-r1` through `-r3` consumed the three-attempt ceiling on harness adaptations; r3 reached connected scene acknowledgement and failed before Base/Home acceptance because the runner did not select Workspace/ROI. The runner is now tab-aware and source-tested. A later freshly authorized serialized campaign must demonstrate changed Base and Task Home review/accept/reconfirm twice with no stale behavior, preserve the input case, and stop for Tarun's rendered/manual verdict.


## S6-P2-03 increment3 source/test completion — 1 October 2026

Native Ubuntu NVIDIA profile now implemented on the integration checkout. Explicit nvidia rendering uses GPU reservation independently of cpu/cuda inference and clears Mesa DRM device mapping. Bounded10s host driver/Docker-runtime and container device-visibility checks provide actionable errors; device enumeration does not establish OpenGL acceleration. Existing auto/Mesa/WSL behavior, selected checkout routing and watchdog metadata preserved. Imported native profile/probe portions only from137a56e; CUDA graphics/display capabilities were already equivalent; WSL changes excluded.

Verification: pure.ubuntu_graphics_profiles,13host/mock tests passed in0.08s exit0; shell syntax, owned Python syntax, scoped whitespace and frame-probe --self-check passed. Tests cover MesaCPU/CUDA, NVIDIACPU/CUDA, WSL baseline selection, missing command/driver/runtime, container visibility, invalid mode, DRM reset/capabilities and source routing. Evidence /tmp/dentobot-verification/perf-increment3-20261001/{host.log,frame-selfcheck.log,summary.json,launcher-port.diff}. No actual GPU/Docker/container/Slicer/ROS runtime, image/native rebuild, case save or hardware action. Operator explicitly excludes GPU verification on this workstation; >=60FPS and renderer verification remain deferred to approved NVIDIA hardware.

All three finite increments now have source implementations. Item1 paired watchdog overhead/identity evidence and item2 representative long-wait/cancel/normal-window responsiveness remain open under existing S6-P2-03; item3 hardware acceptance deferred. Backend MoveIt cleanup-11 remains S6-U-01. No new increment, no5.12 restart, no main merge/push/commit.


S6-P2-03 native source publication checkpoint (2October): reviewed5.10 async motion-control pair committed locally as58fce9bc21709d9fd4e23fdb95febac9e19402c5 in separate slicer_ros2_module; native working tree clean. Source hashes match accepted bounded build/runtime evidence. Full source capture now includes integration1581380 plus native58fce9b. No new acceptance/push/5.12 work.

## Step 6.3 Diagnose This Base and truncated-drilling warning — 2026-10-02

- **IDs:** `S6-BASE-DIAGNOSE`, `S6-TRUNCATION-WARNING` (both Unprioritized); `S6-MANUAL-STAGE-PLAN` on hold.
- **Operator request:** see DECISIONS 2 October "Diagnose This Base; truncated drilling shown as a warning; manual stage planning on hold".
- **S6-BASE-DIAGNOSE contract:** one 6.3 Plan-tab button (owner substep 3). Ordered checks, stop at first failure: (1) stroke reach at the accepted Base → Base placement (first unreachable station, Find Reachable Base pointer); (2) PreEntry/Entry/Target endpoint validity → Collision (named pair); (3) Home→PreEntry route → Planner/corridor; (4) drilling stroke → Tool geometry (reached/requested depth). Result shown as an ordered table with PASS/FAIL/NOT RUN per check and one verdict line; saved with run diagnostics.
- **S6-TRUNCATION-WARNING contract:** when `drillingTruncation` is present, Plan Approach and Drill status use warning state, start with "WARNING: drilling shortened", and give reached/requested/remaining depth and blocking pair; the remainder stays highlighted and labelled in the viewport.
- **Invariants:** no change to Plan Approach gate, policy 2b, guard, MoveIt scene, mouth barrier, joint limits or tolerances; no route or preview authority from diagnostics; simulation only.
- **Acceptance:** host tests for check order, stop-at-first-failure, verdict mapping and warning state; headed run screenshots of the diagnosis table and warning/remainder; Tarun verdict.


## 2026-10-03 — S6-P2-03 NVIDIA acceptance on destination workstation

Operator requests noting pending NVIDIA GPU tests that can run here, launching
Slicer and providing an approval/verification checklist. This destination's
RTX4060 Laptop GPU (8188MiB, driver580.178.04), NVIDIA Docker runtime and X11
desktop are verified. The earlier GPU-less source-station deferral remains
historical; it does not describe this destination. Existing S6-P2-03 Priority1
owns the test, overlapping PLAT-U-07 local acceptance.

[NVIDIA acceptance checklist](diagnostics/NVIDIA_WORKSTATION_ACCEPTANCE_2026-10-03.md)
uses existing matrix `runtime.ubuntu_nvidia_render_acceptance` and recorded
50 host checks. Current Mesa Slicer is already open and preserved. Safe restart
requires save/close confirmation; representative render probe requires a named
approved case. NVIDIA OpenGL/FPS and operator Step6 verdict are NOT RUN. No
claim of improvement, full migration, hardware or clinical acceptance.


## 4 October extension — Plan + Apply new Home (`S6-LIVE-01`)

Operator: “cannot plan and apply new home”. The earlier recovery gate fix is
retained. The local Saved-Home-only callback left a new connected draft without
an application route, while saving required matching accepted robot state.
Plan + Apply Home Draft now uses the shared MoveIt joint-goal planner from the
monitored start and the existing strict per-waypoint guard. A reviewed candidate
may apply only when its exact draft/setup/identity/status match. Finite complete
states/waypoints, exact endpoint, identity stability and authoritative final
accepted/monitored/displayed evidence are required. Partial/unknown submission
latches the existing read-only native reconciliation route with Home-setup
identity. Application never saves or validates Home; explicit acceptance owns
that step. Saved applyTaskHome API remains unchanged.

Actual button routing verified in PID2071: one request reached MoveIt and its
existing3 internal stable-scene attempts all failed CheckStartStateCollision at
dentobot_mouth_barrier_lip_slab / pneumatic_spindle-Copy. No waypoint applied;
original draft, Home, case and accepted state unchanged. Source/host/button
routing are verified; positive route/application and operator verdict remain
OPEN under the existing backlog row. Evidence: logbook/2026-10-04.md.


### S6-LIVE-01 checkpoint continuation — 2026-10-04 UTC02:36
Separate checkpoint/fresh-session continuation approved by current operator message; local commit label `codex planner debug - oct 4`. Saved checkpoint verified original byte-identical; evidence `data/dentobot-runs/planner-resolution-20261004T023621Z`. Same guarded-chain/two-cycle acceptance contract and retry counters persist. Runtime bridge deployment and acceptance remain pending at commit time; no release claim.


### S6-LIVE-01 / S6-BASE-DIAGNOSE runtime continuation — 2026-10-04 UTC02:49
Approved separate checkpoint and local commit efd36b50f7b523b2105726189e1f20f0ef066641 (`codex planner debug - oct 4`); original case byte-identical. Tested bridge loaded in fresh simulation PID3122. Home3 revalidates identical Home2 joints, current snapshot; all34 MoveGroup object bounds match audit. Attempts109/121/124 reached P1 retry ceiling: original RRTConnect axis rejection, corrected RRTConnect corridor invalid goal/direct native ValidateSolution burr/template rejection, RRTstar5s timeout. No motion or downstream button, noA/B, no minimum physical-change certificate. Original planner/options/Base restored or preserved. Session now served from planner-resolution-20261004T023621Z/session. Compact blocker escalation required before more P1 retries. Tarun verdict PENDING.
Ordered diagnostic evidence: kinematic PreEntryIK PASS; Home/PreEntry staticvalid, sampled P1 housing/lip_slab invalid0.133527mm. Corrected corridor reaches native invalid-goal check; direct RRTConnect route rejected after time parameterization at burr/template, RRTstar5s timed out. No drilling/truncation evidence. Read-only diagnosis does not implement S6-BASE-DIAGNOSE. See current logbook and blocker-package.md; no pending ID removed.


### S6-LIVE-01 — native path-validation investigation approved, UTC02:58
**Operator:** “Yes proceed”, answering the specific request for bounded plan-only investigation of native post-timeparameterization burr/template rejection under unchanged guards.
**Interpretation / contract:** prior109/121/124 failures retained; approval resumes the specific diagnostic path, not a blind fourth fullGUI attempt. Contract in /home/tarun/dentobot/data/dentobot-runs/planner-resolution-20261004T025825Z/diagnostics.md. One rawGetMotionPlan request matching existingHome→PreEntry planner configuration, capture fullnative response/debugcontacts, independently verify any returnedstates. No route promotion, motion, preview, Base/Home/scene/policy change, nativebuild/restart. S6-LIVE-01P0 remains owner; no newqueue.


### S6-LIVE-01 / S6-BASE-DIAGNOSE native diagnostics — 2026-10-04 UTC03:09
Bounded native plan-only investigation approved by “Yes proceed” is complete: one rawservice request retains112points despite99999; authoritativechecks reproduceburr/template invalid104–108, dense41/51invalid peak0.286936408mm. Full34-objectscenegeometry/ACMunchanged, Home/PreEntryvalid, no motion/GUIplan/routeauthoritychange. Originalpre-TOTGverticesunknown; samplingversuspostprocessingnotproven. Proposed isolatedSIMULATION-ONLYOMPLfraction0.005→0.0005trial notloaded; collision-policy approvalneeded peroperatorsection3. Evidenceplanner-resolution-20261004T025825Z; prior109/121/124historyretained; neitherA/B, physicalminimumunknown, TarunverdictPENDING.
165static+58FKchecks; onefailedrawplanretained112points, no routepromotion. Source/UIobservabilitygap recorded underexistingowner, no newqueue/implementation. See latestlogbook/blocker-package.md/proposal.md.


### S6-LIVE-01 isolated sampling trial approved — UTC07:02
**Operator:** “approved”, answering the isolatedSIMULATION-ONLY0.005→0.0005proposal.
**Interpretation:** onlydomain74copyoneplan-onlyrequest; originaldomain73case/policy/guards/jointsunchanged. Priorfailurehistoryretained; noGUIfullchain/deploymentapprovalinferred. Newcontract/evidence /home/tarun/dentobot/data/dentobot-runs/planner-resolution-20261004T070243Z. Sessionidlelimitexpired; existingbootstrapreattachedsamePID3122withfocusedconsole, norestart.


### 4 October UTC07:11 — S6-LIVE-01 approved isolated sampling trial result
Operator “approved” authorized one domain74 SIMULATION-ONLY request at OMPL fraction0.0005 (original0.005), stop first valid result. Corrected geometry-verified copy TIMED_OUT5s, error99999/zero points; original scene unchanged and final PID3122/Home3/Base/snapshot/options unchanged, no motion. Earlier missing-overlay copy result134 excluded; known burr/template collision canary0.286936408427mm matched original. Copy stopped/domain74 empty (SIGINT cleanup crash139 retained). Evidence planner-resolution-20261004T070243Z,135/136 and logbook. NeitherA/B nor physical minimum certified. Next reviewable hypothesis is one30s plan-only copy request with all other settings identical; not executed or deployed. Original109/121/124 ceiling persists. Tarun verdict PENDING.


### S6-LIVE-01 30s copy trial approved — UTC07:14
**Operator:** “give better progress updates explaining what task you are working on, and previous output, reasoning for next attempt... approved trial”. **Interpretation:** specific proposal one30s copyrequest replaces prior5s budget only; finer sampling/config/scene unchanged, no live deployment/motion/GUI retry. Progress updates will name active blocker, prior result and discriminating hypothesis. Contract/evidence planner-resolution-20261004T071413Z; stop first result. Prior failure history preserved.


### S6-LIVE-01 approved 30s copy result — UTC07:16; continuation audit UTC11:25
The one approved domain74 RRTConnect request used one attempt,30s and OMPL
fraction0.0005 with execution disabled. It returned error99999 and zero points
after30.003044211s. Copy/original geometry and policy identity matched:34 world
objects, geometry SHA8e4ce8ab…e0e3f8, ACM SHA669b1d33…fc61d27, identical
padding/scale/fixed transform, and exact0.286936408427mm retained burr/template
canary depth. Original scene hashes remained unchanged. This is diagnostic
runtime evidence only: the longer budget did not yield a route, but neither
disconnection, infeasibility, OutcomeA/B nor a physical minimum is certified.
No GUI Plan, motion, route promotion, deployment, case/scene change or hardware
action occurred. Evidence: `planner-resolution-20261004T071413Z` items137/138.

Continuation found broader `planner-resolution-20261004T080424Z` artifacts and
an idle domain74 MoveGroup copy. Controlled records contain no approval that
expands the specific30s contract to those branch/planner/Base/spindle-scale
experiments. Preserve them as unaccepted diagnostic material; do not use them
for acceptance, geometry or policy changes without Tarun's disposition. Exact
copy PIDs4442/4466 ignored SIGINT and stopped after SIGTERM; live domain73
MoveGroup3022 and Slicer3122 remained running. No further runtime is authorized
by this result. Existing `S6-LIVE-01`/`S6-BASE-DIAGNOSE` stay open.

## 6 October — SIM-DYN-01: controller and physics simulation (planning contract)

**Operator:** add a plan to the backlog to simulate real robot movement when actuators/components are added to the URDF; start planning the week of 12 Oct.
**Today:** "Preview" is guarded kinematic playback. Each waypoint is accepted by the collision guard and broadcast by `slicer_joint_state_publisher`; there is no ros2_control or controller_manager, MoveIt has `allow_trajectory_execution: False`, and URDF transmission/actuator/mass/inertia data are unused. New links with collision meshes do already affect planning and the frame audit.
**Proposed stages (each its own approval):**
1. **Inventory:** current URDF joint limits (position/velocity/effort), the actuator/transmission data the engineer will add, the target controller types, and how the guard must observe commanded vs actual state.
2. **ros2_control with mock hardware:** `<ros2_control>` block (mock_components/GenericSystem), controller_manager, joint_trajectory_controller + joint_state_broadcaster; MoveIt `moveit_simple_controller_manager`; time-parameterised trajectories are tracked by the controller in simulation (no physics yet).
3. **Physics:** Gazebo (gz_ros2_control) or Isaac Sim with mass/inertia, actuator limits and gravity; compare tracked vs planned paths (tracking error, timing, limit hits).
4. **Execution semantics and safety:** enable trajectory execution in simulation only; the guard validates controller commands and actual states; keep "EXECUTE DISABLED" for hardware; GUI shows simulated execution distinctly from preview.
5. **Acceptance:** existing frame audit plus tracking-error thresholds per phase; 3-run series per case under execution.
**Boundaries:** simulation only; no hardware command path; any change to guard/execute semantics needs explicit operator approval and its own decision record.

## RUN-ARCHIVE-01 — datewise local run archive (6 October 2026)

**Operator outcome:** organize all existing dentobot-runs artifacts by date,
log the change, stage for commit. No matching organization task was found in the
full backlog or controlled-record overlap search. Existing diagnostic task
results and priorities remain unchanged.

**Contract:** own local run-path renames and the layout/move manifest plus
controlled records. Preserve payload bytes, names, evidence meaning and active
operator processes. No code, model policy, robot action, runtime launch,
engineer-owned record, external sync, or publication. Acceptance for the move:
same-filesystem device/inode/type identity for every moved entry; review and
stage only owned documents. Stop before disrupting a live path.

**Implemented / inspected:** 88 moves into six date folders, with all 3,795
entries retaining identity. UUID dates and watchdog pairing are documented in
the manifest. Two compatibility symlinks intentionally remain for the active
GUI and watchdog. Payloads are local and outside Git; no application testing
needed for this path-only migration. Evidence: logbook/2026-10-06.md and
[manifest](diagnostics/RUN_ARCHIVE_MOVES_2026-10-06.json).

**Pending closure:** after the operator handoff ends, confirm no live users of
the old paths, then retire only the two compatibility symlinks. Keep this task
in backlog until that bounded cleanup is recorded. Future automatic date routing
is a separate undecided option, not authorized implementation.

### RUN-ARCHIVE-01 follow-up — future output instructions and commit

Operator extends this same task to shared agent context plus Claude/Codex
entrypoints and explicitly authorizes commit. Added UTC run-start date/unique
run-directory guidance, output overrides, cross-midnight continuity, grouped
artifacts and scratch archiving; aligned the canonical verification protocol.
Documentation-only acceptance: readback/path parity and scoped Git diff checks.
Automatic producer source changes are outside this turn. The existing live-alias
cleanup remains pending in backlog; this does not authorize closing runtimes.

### RUN-ARCHIVE-01 — compatibility correction scope

Operator requests fixing compatibility-link issues. Both aliases are actively
used; do not unlink them or stop the operator session without explicit approval.
Scoped source owner: Workspace/scripts/dentobot-simulation-slicer-handoff.bash;
existing host stub tests: Testing/test_dentobot_slicer_handoff.py. New sessions
must bypass root ui-watchdog and preserve final HANDOFF_EXIT in the chosen
folder; explicit DENTOBOT_WATCHDOG_LOG_DIR supports run-local evidence. No ROS,
GUI, geometry or guard change. Smallest meaningful check: existing handoff stub
suite from pure.performance_watchdog, gated by operator approval. Alias cleanup
remains tracked until the active-session boundary is released and verified.

### RUN-ARCHIVE-01 — completed compatibility cleanup

Both aliases removed after operator-authorized Slicer/session shutdown; all
owned processes absent, dated data preserved and all 88 manifest destinations
exist. Updated handoff bypasses the retired alias for new watchdog sessions.
Approved existing host stub suite: 4 passed in 20.96 s, exit 0, including legacy
alias isolation, final HANDOFF_EXIT and run-local override. Removed backlog row.
Evidence: logbook/2026-10-06.md; durable
`data/dentobot-runs/2026-10-05/RUN-ARCHIVE-01-20261005T213640Z/`.
Shutdown status 127 / Slicer exit 1 is retained as a separate outcome, not clean
shutdown acceptance. The recorded shell-error hypothesis remains an open
reasoning thread; all requested alias cleanup and routing work is complete.


## 6 October — weekly report and presentation-content draft (`S6-LIVE-01`)

Operator accepted the discussion-priority split and requested its inclusion in `data/dentobot-runs/2026-10-06/weekly-report-20261006-S6-LIVE-01/REPORT.md`. Completed content deliverable: accepted priority/status tables and `SLIDE_CONTENT_DRAFT.md`, exactly six slides; overview first and questions/next last. Preserved the detailed evidence report, reserved additional-case comparison space and used the latest three-run rule and no-yaw clarification. PPTX production deliberately deferred by operator; no new pending queue or runtime campaign. Verification: file readback, six slide-heading assertion, local link checks and series-summary counts recorded in logbook/2026-10-06.md. Existing S6-MULTI-TARGET-01 owns additional cases; all acceptance boundaries retained.

**6 October content refinement:** operator requests a text-only first slide and comprehensive secondary accomplishments for 29 September–6 October. Completed a 74-item retrospective `WEEK_ACCOMPLISHMENTS_CHECKLIST.md` alongside the report, with dated evidence and implementation/runtime/acceptance boundaries. Replaced slide 1 with seven outcome-level bullets spanning planning, workbench, case management, templates, reliability and reproducibility; corrected the date range and linked the inventory. No task acceptance or pending-work priority changed. Document assertions and link/line readback passed; see today's log.

**6 October weekly presentation delivered (`S6-LIVE-01` reporting):** six-slide editable PPTX and PDF created in the dated weekly-report/presentation folder and copied to Downloads as Tarun_weeklyupdate_Oct6_2026.{pptx,pdf}. Includes weekly accomplishments, five-case outcomes, FDI14 evidence, advisor logic/learnings, FDI34 failure evidence and prioritized questions. Original template unchanged. FDI34 further testing not awaited; unresolved audit boundaries retained. Verification: package/layout checks, rendered visual inspection and copy hashes recorded in today's log.

**Weekly deck visual edition:** delivered 12-slide Tarun_weeklyupdate_Oct6_2026_visual.pptx and PDF in Downloads and the dated report/presentation directory. Six inserted screenshot-focused slides cover FDI14, FDI11, FDI31 and FDI34, with configuration captions, ghost labels and source notes. Original six-slide deck preserved. Package/layout validation and visual inspection recorded in today's log.


**Weekly deck v3 final (`S6-LIVE-01` reporting, 6 October):** delivered 14-slide PPTX/PDF in the dated report/presentation directory and Downloads. Combines fuller prerequisite coverage with six dedicated visual evidence slides, concise text and source notes; incorporates latest 42 mm FDI34 route failure without changing acceptance. Package/layout, rendered inspection and delivery-copy hashes recorded in today’s log. Prior editions preserved.

## 8 October — A/B parity and remaining restore blocker (`PLAT-U-07`, `S6-FRAME-SYNC-01`)

Common containerimage, native source/libraries, installed robot/MoveIt resources, required modelweights and the approved immutable SampleCBCT bundle synchronize acrossA/B. Both `dentobot parity` reports PASS everycategory, and the individualcase exchange command verifies the same SHA bothdirections. Normal Git source fast-forward and matching branch tracking are configured; old B checkouts and both pre-cutover runtimes retained. Workstation package tests38PASS+9subtests;71 focused restore checks pass, and publicAPI regression was corrected without changing its baseline. Runtime native wrappers expose `ApplyMoveItCollisionObject` and `GetMoveItWorldObjectBounds`.

The known-transform case still fails initial strict pre-bind branch revision validation on execution3. ActualSlicer1/launcher0, zero transform stages, complete video/checksum/decode and owned teardown retained. No save/reopen runtime success or full-case acceptance is claimed. Offline saved revision reconstruction matches exactly; live-ID/callback cause unproven. One instrumented offline diagnostic is prepared only and explicitly awaits Tarun under the three-failure policy. Independent no-case smoke/remaining checks recorded in the datedlogbook. Existing fullframe campaign/operator and separate oversized Drive bundle obligations remain in backlog. Evidence root `/home/light-tarun/dentobot/data/dentobot-runs/2026-10-07/PLAT-U-07-parity-20261007T184805Z`.


### S6-FRAME-SYNC-01 / PLAT-U-07 — 8 October instrumented follow-up

The operator-approved single diagnostic finished: initial legacy registry exactly matches, then summary readiness performs a second current-provenance sync before comparison. MRML IDs unchanged. Implemented deferred readiness during the private legacy integrity audit; regression11 PASS and pure-profile union785 PASS with two historical shell failures. Runtime/save-reopen remain NOT ACCEPTED, zero stages, full cleanup PASS. Evidence and approval boundary: logbook2026-10-08 instrumented restore section. Prepared corrected bounded offline case execution requires new operator direction; independent A/B source and runtime parity synchronization continues.


### S6-FRAME-SYNC-01 — corrected run result, 8 October

One newly authorized corrected B execution passed initial legacy validation and hydration, then stopped at the migrated trajectory-node fingerprint comparison. Implemented frozen-migration-backed expected fingerprint translation only, with identity/geometry strict. Focus52PASS; matrix791PASS/two baseline failures. Zero runtime stages/save-reopen still NOT_RUN; cleanupPASS. All earlier failures preserved. Corrected source must be synchronized and a new bounded case execution separately authorized; full-case, MoveIt and operator acceptance remain open.


### S6-FRAME-SYNC-01 — shared callback barrier correction, 8 October

The sixth specifically authorized actual case run stopped because UI callbacks migrated before hydration could record the legacy proof. Shared registry entrypoint now follows restore depth, permitting migration only inside validated hydration. Focus55PASS; matrix794PASS/two baseline shell failures. Runtime not accepted/save-reopen NOT_RUN. A/B environment, source5064165 and both desktop preflights PASS; command package14files identical. Next bounded case run must be explicitly approved, previous history retained.


### S6-FRAME-SYNC-01 / PLAT-U-07 — representative offline runtime acceptance, 8 October

The operator-approved63551f8 run PASS on B for initial legacy restore, baseline/opening/Base translation/Baseyaw/branch switch/actual save-reopen,18geometry rows, eleven loaded identities, immutable fixture, video checksum/decode and complete cleanup. New saved case checksum transferred to A. Original restore blocker is resolved for this supplied fixture. Full S6 MoveIt/kinematics/collision/case matrix and operator acceptance remain open; PLAT oversized Drive uploads are unchanged. Selected-checkout pinned launch/source-aware runtime lock integration is implemented and host-tested; finish its actual no-GUI launcher check and reload smoke, then publish final source/doc checkpoint and prove A/B/origin/command/runtime equality.

### 9 October — current combined S6 frame-sync/stale-object host scope

Tarun explicitly permits System A for the current authorized S6-FRAME-SYNC-01 and S6-MULTI-JAW-STALE-01 simulation campaign to obtain demonstrable results promptly. The earlier B-only runtime/A-display restriction is superseded for this campaign; A evidence is identified as A evidence, without a B-parity claim. Stop B-specific launcher/transport repair. Preserve prior B attempts and results. On A, inspect and preserve existing operator-owned processes, load and verify source/helper `51f2a01`, use the existing A launcher and real GUI input, and run the first upper FDI11/45.9 frame-sync L2 gate with the comparator outside Slicer. Continue to stale-object, lower target, second opening and Home-dependent L4/L5 only after their preceding gates pass. Stop at the first failure; operator GUI verdicts remain deferred. No original-case save, hardware action, geometry/policy relaxation, or p0/main publication follows. Discuss Item 4 design with Tarun before any implementation. Evidence/status: `data/dentobot-runs/2026-10-09/S6-NEXT-HANDOFF-20261009T180018Z/RUN-STATUS.md` and today's logbook.

- 2026-10-09 retained A stack disposition for combined 5a/5b: Tarun “yes i approve” permits reuse of domain-73 simulation stack and planning-scene update for the copied case after current stack/native/source identity checks. Offline A first gate stopped at modal Yes hit-test refusal; explain post-refusal actions, fix fail-stop input path and rerun bounded A gates. Connected L2/Step A, lower/second opening, L4/L5 remain open. No Item 4 implementation before design discussion; verdict deferred.

- 2026-10-09 operator scope update for P0 `S6-FRAME-SYNC-01` / `S6-MULTI-JAW-STALE-01`: Tarun “ok i approve this plan” for the clean A Step 5C→fresh Step 6 simulation baseline. First check case-specific supported partial-restore/projection ownership eligibility and use independent copy through verified Step 5C; report exact reason/alternative if blocked. If eligible, exclude downstream Step 6 state, verify retained A stack PID/start ownership and owned cleanup, launch fresh Slicer plus simulation, perform normal Import/robot/Base/Connect/scene/Home validation with original safety gates. Main frame-sync demonstration precedes separate saved-branch restoration 5b. Previous retained-stack hold/reuse-only wording is superseded for this identified stack. Preserve source/case/native/harness hashes, first-failure stop, and deferred operator verdict; no Item 4 code before design discussion.

### 2026-10-09 — DCP-09..10 partial-load repair first; dedicated code thread

Tarun directs repair of the existing DentoCase Library partial-loading workflow before further Step 6 demonstrations. This is execution sequencing under existing DCP-09..10 (numeric Priority 3 unchanged), overlapping S6-REUSABLE-CASE-SETUP case semantics; no new task or queue. A dedicated Sol medium thread `dcd07ad8-9069-4205-848e-40dce2321095` owns isolated code/tests and returns reviewed commits/evidence. This thread retains controlled docs, integration and later A loading/testing. Current production HEAD is `51f2a017cf11f11167a969cb2a20fed21c5712a8`; existing dirty files here are controlled `TASKS.md`, `DECISIONS.md`, `backlog.md`, and new `logbook/2026-10-09.md` only. No production code edits in this checkout.

Required partial result is selected branch and cutoff plus complete needed dependency closure, preserving exact source geometry, transforms, trajectories, docks, templates and references. Exclude downstream and unselected configuration/runtime/authority and legacy remnants not needed by that closure, including stale Step 6 configurations on retained template nodes; no automatic ROS connection. Foundation/Base geometry and its saved acceptance/live authority are distinct. Unknown ownership remains fail-closed. Diagnose the five-tooth schema-3 package SHA `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54` with 61 ownership reasons through production inventory/serializer/projection code. Required evidence includes metadata/eligibility, actual excluded and retained nodes/parameters, negative unknown-owner behavior, original hash, independent Save As/fresh reopen and representative library UI partial load; full-load/save must not regress. Frame-sync/stale GUI work pauses. No runtime or stack replacement during repair diagnosis.


#### DCP repair handback and native gate — 9 October

Repair commits `a769f27` and `fb0ec2a` are integrated locally as `6468f6edab111cccabd7b0b827638bd67c095932`; the host DentoCase matrix has 112 PASS. The exact five-tooth XML witness makes all five Step5C selections eligible, but a production child selects **one** target/branch. Native Library load, independent Save As, fresh reopen, full-load regression and operator verdict remain open. The first A native acceptance launch stopped before Slicer at ROS setup sourced under `nounset`, run `DCP-09-NATIVE-20261009T211507Z`. This is the third recorded failure of that causal preflight boundary across B/A, so another live attempt is held for operator guidance under the shared verification protocol. A run-owned wrapper correction is prepared but unexecuted.

The bounded follow-up repair `00de904` was integrated as `0971051150a02684777cda527d74b69657ad971f`: virtual Step5C evidence now binds the final-model update timestamp; schema-3 complete and incomplete cases both replan from the freshly audited restored scene before pruning. The disposable projector emits `restored_audit_complete` before destructive operations. Integrated matrix `pure.dentocase_integration` is 118 PASS in `data/dentobot-runs/2026-10-09/DCP-09-INTEGRATED-20261009T212502Z/evidence/`. A clean detached worktree is mounted in A at the integrated SHA. Native acceptance remains pending the preflight retry gate; no new Slicer/ROS execution occurred.

Tarun explicitly approved **one** serialized offline A Library retry after the focused repair review, using the proven A ROS setup wrapper, first-failure stop and untouched retained stack. This is a bounded revision to the three-failure `nounset` preflight hold; prior failures remain recorded and no unlimited retry follows. Integrated source is `0971051150a02684777cda527d74b69657ad971f`, host matrix 118 PASS.

The single Tarun-approved A Library retry (21:31:52–21:34:39Z) delivered real Verify, Load selected prefix and Yes for FDI34 `template.verify`. The Library correctly displayed “Scene audit required” for the source's 61 saved unknowns. Disposable projection then failed and Slicer displayed “Offline projection failed: Support Plane_2.mrk.json” amid vtkArchive zip-add output. The temporary projector log was not retained, so the exact traceback and whether projected save or reopen failed are unknown. No child case was released, Save As/reopen/full-load regression were not reached, and no native DCP acceptance is claimed. Screenshot, ledger and partial 2880×1800 video are in `DCP-09-NATIVE-RETRY-PREP-20261009T212610Z/`. The owned Slicer child was identity-checked and stopped before any downstream workflow; copied source hash stayed `be58b243...7e54`, retained stack PID 348/start 7510853 untouched. This consumes the one approved retry; further runtime requires a new bounded operator decision after source/log diagnosis.

Astra supervisor assessment after the failed native attempt: the single retry is consumed and all Slicer/GUI/ROS execution is paused. Read-only archive analysis and source/host DCP correction are authorized; `Support Plane_2.mrk.json` plus vtkArchive INFO is not a causal diagnosis. The owned projector is being corrected to retain the full child log/traceback, exit code and phase metadata under durable run evidence before temporary cleanup, with a focused failure regression. No further full Library run may occur solely to recover lost diagnostics without a concrete bounded plan and Tarun approval.

The diagnostic loss fix was integrated from isolated commits `1893a94` and `dc985ae` as local HEAD `fe0af4a77f03900d7f73409cd68850ed58851b7f`. It retains the disposable projector's full merged stdout/stderr/traceback and exit status under private `CRUN/evidence/projector-<uuid>/`, with stage markers for scene save, post-save inventory, package creation and reopen; the UI error points to that log. No causal geometry/storage/serializer correction is claimed. Integrated `pure.dentocase_integration` matrix is 120 PASS at `data/dentobot-runs/2026-10-09/DCP-09-DIAG-HOST-20261009T214151Z/evidence/`. Source/case original hashes remain unchanged. All native runtime remains paused: the one approved retry was consumed, the lost child traceback cannot be reconstructed, and a further bounded diagnostic execution requires Tarun's fresh approval after review of this plan. Native Library projection, Save As, fresh reopen, full-load regression and operator verdict remain open.

Tarun replied “approved” to exactly one serialized offline A Library diagnostic at integrated `fe0af4a77f03900d7f73409cd68850ed58851b7f`, using the exact copied FDI34 source, real Verify → Load → Yes, and retained private full child log/status/phase markers. Stop at first failure and preserve traceback/last phase; no automatic retry. If projection succeeds, inspect selected dependency closure and excluded state, then Save As and fresh reopen in this same attempt. Original case and retained domain-73 stack remain untouched; no ROS connection, hardware or Item 4.

The one Tarun-approved `fe0af4a` offline A diagnostic ran 21:42:45–21:43:29Z. Real Library Verify, FDI34 Load and Yes were delivered. The disposable child reported `restored_audit_complete` and `save_scene_complete`; the first failure was **post-save ownership capture**: `case_projection.py:398` raised `ValueError: Projected ownership is incomplete.` The source archive remained SHA `be58b243...7e54`; no child bundle, Save As or reopen. The earlier Support Plane filename/vtkArchive output was not the failing operation. Full private child log/status are under `DCP-09-DIAG-NATIVE-PREP-20261009T214226Z/evidence/projector-dd7edf150d394366b3bd9f37ad148abd/`; screenshot/ledger/video are in the same run. Owned Slicer PID 9333/start 17152145 was identity-checked and stopped; retained simulation stack PID 348/start 7510853 stayed untouched. This one diagnostic approval is consumed, and all further native runtime is paused. Post-save `unknownOwnership` reasons were not emitted; dedicated repair thread owns bounded source/host diagnosis and logging or causal correction, then a fresh concrete runtime decision is needed. Native DCP persistence remains unverified.

The isolated logging-only follow-up `0d1d358` was reviewed and cherry-picked as local HEAD `4fb7e79`. The failed disposable `projected.mrb` and structured ownership inventory were already removed with its temporary directory, so the exact native ownership mismatch remains unknown. The projector now records all post-save `unknownOwnership` reasons, captured node owners and minimal projection-plan IDs to a private mode-0600 JSON report before the unchanged fail-closed rejection; its private child log shows a bounded reason preview. No pruning, ownership policy, geometry or full-load behavior changed. Repair-thread focused 39 PASS/pure matrix 122 PASS and integrated checkout pure matrix 122 PASS. Evidence: `data/dentobot-runs/2026-10-09/DCP-09-POST-SAVE-OWNERSHIP-20261009T214451Z/evidence/`. Another native attempt requires a separately approved bounded discriminator; Save As, fresh reopen, full-load regression and operator verdict remain pending.

The supervisor requested retention of the actual failed projected MRB before another native request. Isolated `00db1a8` was reviewed and integrated as local HEAD `144874e56782becbbfc56f3cc79f083258ca091e`. A private projector directory now holds the complete process log/status, structured ownership report and, only after `save_scene_complete`, the failed `projected.mrb` with SHA256 and phase in sanitized status. The child copies before scratch cleanup on normal exception; the parent can recover one surviving completed MRB after abnormal child exit. A failed/absent save cannot claim or copy an MRB. Directory mode 0700 and artifact mode 0600; no geometry or ownership-policy correction. Repair focused 44 PASS/pure matrix 127 PASS and integrated checkout pure matrix 127 PASS; evidence `data/dentobot-runs/2026-10-09/DCP-09-FAILED-MRB-RETENTION-20261009T214902Z/evidence/`. Native runtime remains paused pending Tarun approval of one offline discriminator; the last failed child cannot be reconstructed retroactively.

Tarun approved one offline A FDI34 diagnostic at `144874e`. The 22:03:38–22:03:45Z attempt stopped **before Library/Verify/Load/Yes** because the run-owned boot script shadowed its module-level `importlib` with a local import; `native-library.json` has zero events and records `UnboundLocalError`. No projector, partial child, ownership report or MRB was created, so this is a harness preflight failure, not a DentoCase result. The copied case SHA stayed `be58b243...7e54`; recorder captured a partial 2880×1800 video, Slicer exited, retained stack PID348/start7510853 remained untouched. Failed evidence is `DCP-09-OWNERSHIP-NATIVE-20261009T220237Z/`. A corrected run-owned boot is staged only under `DCP-09-OWNERSHIP-RETRY-PREP-20261009T220404Z/`; AST, Python symbol-scope and shell syntax checks pass. The approved one run is consumed; no automatic retry. Native DCP persistence still needs a separately directed attempt.

### 2026-10-09 2026-10-09T22:50:38Z — DCP-09..10 approved corrected-boot attempt

Operator: “approved, continue” authorizes exactly one fresh serialized offline A Library FDI34 attempt at `144874e56782becbbfc56f3cc79f083258ca091e`, with corrected run-owned boot SHA256 `1eacdd13dcba236c8a119a80f919955c2b70ee818683245b0b2464587d8d0a50` and copied case SHA256 `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`. Real Verify → Load → Yes; stop at first failure with private complete logs, ownership reasons and failed projected MRB if saved. Only after projection and closure/exclusion audit pass, perform independent Save As and fresh reopen in the same attempt. No automatic retry, ROS connection, retained-stack mutation, original save, hardware or Item 4. Fresh run root `/home/tarun/dentobot/data/dentobot-runs/2026-10-09/DCP-09-OWNERSHIP-RETRY-20261009T225024Z`. Host and container detached source clean at the approved SHA; case_library SHA `983de7bb479b1331b4d181f22f5f03db51dae42e8913e6801249cfa4b24620a6`, case_projection SHA `83be7f822ade5cae10b0f54dd644ab6e1c31f14f5f9e60fb0dfa6848d1c9f9e9`, input helper SHA `00e46378ba71e4aff1ffb3fe8597771ac7408e18335350011ccc5a8ba44eb1a0`; retained stack PID348/start7510853 verified. Runtime outcome pending.

### 2026-10-09 2026-10-09T22:56:58Z — DCP-09..10 one-run outcome

The approved offline A attempt ran 22:50:43–22:56:10Z at pinned `144874e`. Real Library Verify, FDI34 selected-prefix Load and modal Yes were delivered (`session/user-input-ledger.jsonl`; selection screenshot). Disposable projection restored and saved its MRB, then failed the first acceptance gate at `post_save_inventory_begin`: `ValueError: Projected ownership is incomplete.` The private report identifies exactly one unknown reason, `registry has no Step 5C verification revision for template: vtkMRMLModelNode47`; that node is `[Step 5C] DENTO Final Printable Template`, included in the projection keep set. The complete `projected.mrb` SHA256 is `c3d95202f338a057f89f74a4f8054212a032ab146256de76752956b775eebfae`, retained beside `post-save-ownership.json`, `process.log` and `status.json` at `/home/tarun/dentobot/data/dentobot-runs/2026-10-09/DCP-09-OWNERSHIP-RETRY-20261009T225024Z/evidence/projector-ea6cb74a7752454eb36387ba8e7f8349/` (directory 0700, MRB 0600). No child bundle was released. Save As, selected closure/exclusion acceptance, and fresh reopen were NOT RUN.

The parent Slicer did not return after the projector exit. To honor first-failure stop, the run-owned launcher PID9913/start17559897 and child PID9915/start17559898 were identity-checked and sent SIGTERM; recorder finalized a partial video (ffmpeg exit0, overall command143). Slicer count subsequently 0, advisor lock free, retained simulation stack PID348/start7510853 unchanged. Copied source hash remains `be58b243...7e54`; no original case was opened or saved and no ROS connection/hardware action occurred. This one approval is consumed; no automatic retry. The exact cause of the absent registry revision and the parent wait behavior remain open under DCP-09..10; inspect retained MRB/registry and production projector path before proposing a separate repair/attempt.

### 2026-10-09 2026-10-09T23:17:12Z — DCP-09 retained-artifact causal review (read only)

Compared source `5tooth-source-copy.dentocase` and retained failed `projected.mrb` MRML for selected branch `guide-f8a3caff373bddb4f157` and `vtkMRMLModelNode47`, alongside the exact keep plan. The source is a legacy world-frame registry (no `provenance_frame`), with branch revision `69a750b5…`, `verification_revision=1eb0666f…`, branch state Current, and the kept final template has WARNING verification JSON whose canonical SHA256 is exactly `1eb0666f…`. The projected MRB has a new `provenance_frame`, branch revision `880f60d3…`, branch state Stale, blank `verification_revision` and blank branch-foundation fingerprint; the template's old WARNING verification JSON/hash remains `1eb0666f…` and its node revision changed to `880f60d3…`. The node is in `keepNodeIds`, not `removeNodeIds`. Production `case_inventory.py::_step5c_verification_artifacts` correctly rejects saved verification evidence with no registered verification revision. `logic_case_bundle.py::syncDentoCaseTrajectoryRegistry` recomputes branch revision and retains verification only if it matches that revision; the migration helper requires a current eligible foundation and matching legacy provenance. Exact transition within validation/sync remains to be isolated by a host regression; do not clear the error, claim the old verification valid, or remove required template geometry. The missing revision is a provenance/branch-state conversion consistency problem, not a missing MRB node or archive save failure.

The apparent parent wait has a separate direct explanation in recorded pixels: `video/whole-run/whole-run.mkv` at about 80s shows Slicer's modal “Could not load the independent partial case” error with OK and Show Details, behind an unfinished Library action. `widget_case_backend.py::_openLibraryPartialCase` wraps the projector in `slicer.util.tryWithErrorDisplay`, so the exception opens a blocking dialog before control returns to `case_library.py::_finish_job` and the boot's failure/exit path. The child had already exited; the parent was awaiting dismissal. The scripted run lacked a bounded failure-dialog handler. No further runtime is needed to establish this mechanism.

Supervisor found an authorization boundary error: this run's `A_NATIVE_RUN.sh` set `DISPLAY=:0`, confirmed by the recording manifest, while the prior handoff forbade A's display absent a specific operator request. The generic offline A approval did not specify desktop `:0`. Future A runtime preparation must use an isolated authenticated display or obtain specific permission for :0, while preserving real XTest actions; this note grants no runtime retry. One-run approval consumed. Evidence remains private at `/home/tarun/dentobot/data/dentobot-runs/2026-10-09/DCP-09-OWNERSHIP-RETRY-20261009T225024Z`; source/copy bytes preserved.

### 2026-10-10 2026-10-10T03:20:08Z — DCP-09 source/host repair checkpoint

Tarun directed source/host repair only, with no Slicer retry. The exact legacy five-tooth copied source MRML has selected branch revision `69a750b5…`, Current state and verification revision `1eb0666f…`, equal to the canonical hash of the retained final template's WARNING payload. The pure `filter_registry` at `template.verify` preserves those values. The failed native projected MRB instead has `provenance_frame=OwningJawRASmm`, revision `880f60d3…`, Stale state and blank verification revision, while the template's old payload remains. This locates the destructive conversion at the ordinary registry sync reached by `caseBundleWorkflowSummary(parameter)` in `case_projection.run_offline` after pruning, before scene save; post-save inventory correctly fails closed. The source's validated registry lacks the new provenance key, and its earlier restored audit used legacy provenance. Exact host trace: `/home/tarun/dentobot/data/dentobot-runs/2026-10-09/DCP-09-HOST-REPAIR-20261009T231800Z/evidence/exact-case-revision-trace.json`. No template geometry or original case was edited.

Reviewed code commit `6d6721a` (parent `144874e`) makes only the projection summary retain the already validated source registry provenance. The public summary's default remains current provenance for normal/full saves. A malformed registry is rejected; earlier cutoffs still clear verification; `case_inventory` retains its unknown/stale fail-closed checks. Focused projection/inventory/jaw-stale 66 PASS; indexed `pure.dentocase_integration` 128 PASS; `git diff --check` clean. Outputs: `/home/tarun/dentobot/data/dentobot-runs/2026-10-09/DCP-09-HOST-REPAIR-20261009T231800Z/evidence/focused-pytest.txt` and `matrix-pytest.txt`. These are host/source evidence, not native projection, Save As/reopen or operator acceptance. Full-load runtime regression remains pending the separately approved native campaign.

Future-run preparation only: `/home/tarun/dentobot/data/dentobot-runs/2026-10-09/DCP-09-HOST-REPAIR-20261009T231800Z/input/native_library_boot_WITH_ERROR_DISMISSAL.py` captures the exact expected Slicer error dialog and dismisses its OK by real XTest once, logging failure if delivery fails; it has Python syntax verification but no headed trial. `/home/tarun/dentobot/data/dentobot-runs/2026-10-09/DCP-09-HOST-REPAIR-20261009T231800Z/input/A_ISOLATED_DISPLAY_PREPARED.sh` stages authenticated container Xvfb `:98`, 2880×1800, private cookie, no TCP; shell syntax passes but it was not executed. Any native attempt needs a fresh dated root, identity review, same first-failure stop, serialized lock and run-owned cleanup; A desktop `:0` remains excluded absent specific permission. Prior one-run approval consumed. Concrete proposed next gate: one separately authorized offline Library FDI34 Verify → selected-prefix Load → real Yes with a private display at commit `6d6721a`, exact copied case hash `be58b243…7e54`, projector report/MRB/log retention; after projection audit selected dependency closure and excluded state, then independent Save As and fresh reopen within that same attempt. Stop on first failure; preserve original, retained stack and hardware boundary.

### 2026-10-10 2026-10-10T03:24:47Z — DCP-09 readiness follow-up, source/host only

Supervisor requested two concrete readiness corrections before a native request. Commit `4153c79` (on `6d6721a`) adds `Testing/test_dentocase_legacy_projection_sync.py`: AST-extracted production `caseBundleWorkflowSummary` and `syncDentoCaseTrajectoryRegistry` run on a registered legacy FDI34 WARNING template fixture. They preserve matching revision/verification at `template.verify`; the production filter plus node-attribute clearing drops verification at earlier `template.build`, and the production inventory refuses a mismatched verification payload with the exact unknown-owner reason. This extends rather than replaces the retained exact-case source/filter/projected-MRML trace. Affected host checks: 67 PASS, output `/home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-READINESS-20261010T032421Z/evidence/affected-pytest.txt`; `git show --check` clean. No Slicer runtime or original-case edit.

Prepared-only isolated display script now waits up to ten seconds for authenticated `xdpyinfo`, records PID/start and checks process identity before TERM cleanup on startup failure; shell syntax passes. SHA256 `c44686129f91946003bd50cb4b210b553636f0e1fbeb36fbd1f8891bdf7db8f8`. Prepared-only boot catches screenshot, missing OK button, unexpected Slicer error and real XTest delivery failures inside the timer; each is recorded, the error-only dialog is rejected fail-closed, and no load is accepted. Python AST passes; SHA256 `2345dd8ae52603a0d4612147274045f224830cce979f4c3e2d302ea4c87338b8`. Both scripts remain under `/home/tarun/dentobot/data/dentobot-runs/2026-10-09/DCP-09-HOST-REPAIR-20261009T231800Z/input/`, hardcode that preparation root, and are NOT an executable fresh native run package; a separately authorized run needs a new dated root, pinned `4153c79` detached checkout, refreshed exact hashes and owner cleanup. The last copied case remains SHA256 `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`. Prior native approval remains consumed.

### 2026-10-10 — DCP-09..10 approved native first-failure disposition

The one Tarun-approved offline A attempt at clean detached `4153c794633def1f841f0b61b54108874f11680c` ran 03:40:17–03:43:51 UTC from `/home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-NATIVE-PROPOSAL-20261010T032550Z` (manifest SHA256 `28bb381d2e50b482e6148761c8a06bd5cb0ef9d2b754320eaf9a2aa932f17ce6`, copied case SHA256 `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`). Real XTest Verify/FDI34 template.verify Load/Yes and private authenticated `:98` were delivered. Projector exit 0 and post-save inventory PASS are narrower than Library load acceptance: parent `_openCaseBundle` failed during saved workflow hydration with “The saved Step 6 environment or trajectory registry is invalid.” Live selected closure audit, Save As, child audit and fresh second-process reopen were not reached. `evidence/run-outcome.json`, `native-library.json`, projector process/status, error screenshot, XTest dismissal receipt and video manifest are private in that root. Owned cleanup PASS; Slicer/Xvfb 0, advisor lock free, retained stack PID348/start7510853 and copied case unchanged. No retry; approval consumed. Existing DCP-09..10 Priority 3 remains open, with next bounded read-only/source diagnosis of parent hydration rejection. Any new native attempt needs separate operator approval; no new implementation/runtime is authorized by this handoff.

### 2026-10-10 04:51Z — DCP-09..10 parent hydration diagnostic source checkpoint

Tarun approved source instrumentation after the 03:40 first failure. Commit `82e1cf1` retains a completed projected child package privately when parent Library loading rejects it and records its SHA256; schema-3 hydration logs whether environment or trajectory-registry parsing failed and the underlying parser exception. The original error still fails closed, and no production parsing or ownership rule was relaxed. Focused host checks 23 PASS and three edited Python AST parses PASS; `git diff --check` clean. The failed 03:40 child package was temporary and cannot be recovered from retained evidence, so the exact invalid payload remains unknown. A new pinned native attempt is required to diagnose it, followed by the existing closure/exclusion, independent Save As and fresh reopen gates only if earlier gates pass. The 03:40 approval remains consumed; no native retry was run for this checkpoint.

### 2026-10-10 05:02Z — DCP-09..10 bounded DentoCase demo preparation stop

Tarun narrowed the next checkpoint to one copied FDI34 five-tooth Library partial load at verified Step5C, retained selected dependencies and excluded legacy/Step 6 state, independent Save As, then fresh-process reopen. The reviewed offline A/private `:98` proposal used clean `82e1cf13a2e32f21aa84975906486d7af2254870`, manifest SHA256 `0ed558459e2f8502a2a7bcd09d08896a5e1ecb6a7ddc97aaf47432c0d863833a`, and the unchanged copied-case SHA256 `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`. One launch passed static identity preflight, then failed before Xvfb/Slicer because the proposal root lacked `evidence/`, making the display log redirection fail. No GUI gate or later simulation ran; no retry. The cleanup-log redirection also failed, but read-only checks showed SlicerApp-real/Xvfb 0, `:98` absent, advisor lock free, retained PID348/start7510853 and copied source unchanged. Private `evidence/run-outcome.json` and the canonical RUN-STATUS correction distinguish this preparation failure from a Library result. The visible DentoCase demo remains open; another run needs a corrected frozen package and an explicit operator decision. Other branches, frame-sync, Home, advisor and 2D work remain outside this checkpoint.

### 2026-10-10 — DCP-09..10 approved corrected attempt stopped before Library

Tarun approved the frozen `DCP-09-FDI34-DEMO-20261010T050516Z` proposal (manifest SHA256 `97c408e53f0be1005e9aade0c493a7a031a99a0ac231ab01c48e3a244e808fea`). One launch reached private display and stage1 Slicer, then `native_library_boot.py:64` failed its embedded case_projection SHA assertion: boot expected the old `9870230d…`, clean pinned source `82e1cf13` loaded `9bc7648791afec3d4a4dcb588ab09570e76d0637abdf1d9418d02c8e547cc5a3`. No Library action or case workflow gate was reached. First-failure stop, no retry; private `evidence/run-outcome.json` records the pre-Library failure. Exact-owned cleanup PASS, Slicer/Xvfb 0, lock free, retained stack PID348/start7510853 and copied case unchanged. Correct the boot identity and review the complete frozen package before proposing another explicitly approved single attempt. Do not expand beyond the FDI34 DentoCase demo.

### 2026-10-10 — DCP-09..10 current Go attempt and routine retry preparation

One Tarun-approved command at `/home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FDI34-DEMO-20261010T051801Z/input/A_NATIVE_RUN.sh` (manifest SHA256 `2cdd8ff83e44a0ce7c28dfeb86c3b4b54df351ba92af7616b236109ab5946eec`, clean `82e1cf13`, copied case `be58b243…7e54`) passed static and source identities, opened private `:98` and Slicer, then stopped at `Catalog(ROOT / "session/catalog.sqlite")`: its parent directory was missing. Library was NOT REACHED; Save As/reopen NOT REACHED. Exact-owned cleanup PASS, Slicer/Xvfb 0, lock free, retained stack PID348/start7510853 and copied case unchanged. Private run outcome and canonical RUN-STATUS record the first failure; no retry. Fresh preparation-only root `DCP-09-FDI34-DEMO-20261010T051956Z` has all run directories, pre-resource directory checks and manifest SHA256 `0b6828f20bdba00cb2c7a0c4b368bd56e1e94c5311691b997f4613d8123f6126`; host/container static 19-file check, AST, shell syntax, embedded hashes and directory visibility PASS. Native execution awaits the supervisor's exact retry decision under the unchanged single FDI34 demo scope.

### 2026-10-10 — DCP-09..10 FDI34 demo first failure and offline parser diagnosis

The one supervisor-approved immutable `DCP-09-FDI34-DEMO-20261010T060422Z` command ran 06:20:28–06:35:29 UTC at clean detached `82e1cf13a2e32f21aa84975906486d7af2254870` (manifest SHA256 `9bde676a868233fb297e7ca5b942188bb7f90d4de5afb944273ceb3a2be1421f`, copied case SHA256 `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`). Library loaded the source as Valid, selected FDI34 Step 5C `template.verify`, and delivered real XTest Yes. Parent loading then rejected the projected package while hydrating saved workflow. The run-owned 900-second watchdog ended it with command rc70; no selected closure audit, Save As, or fresh-process reopen was reached. No automatic retry. Exact-owned cleanup PASS at 06:35:29; host/container exact `SlicerApp-real` counts 0/0, private `:98` gone, advisor lock free, retained stack PID348/start7510853 and copied case unchanged. The canonical outcome is in `data/dentobot-runs/2026-10-09/S6-NEXT-HANDOFF-20261009T180018Z/RUN-STATUS.md`; this run has no `evidence/run-outcome.json`. Run-local exit and cleanup evidence is `slicer-exit-stage1.txt`, `recorder-exit.txt`, `evidence/interstage-gates.log`, `evidence/owned-cleanup.log`, and `evidence/slicer-process-counts.log` in the 060422Z root; `evidence/native-library.json` retains the reached Library actions.

The approved read-only offline parse of retained `evidence/projector-3ea85255159a48aabe9c7072b3354e28/parent-rejected.dentocase` (SHA256 `5f4abfec59941ddb242f404d2840490d83edab18664a38a9ded9fda0245f453a`) identifies schema 3.0 `step6EnvironmentJson` as the failing field: it is empty; the pinned `parse_robot_environment_snapshot("")` raises `JSONDecodeError` at character 0, wrapped by `logic_case_bundle.py:949-957` as `CaseBundleError`. The retained trajectory-registry JSON parses successfully. `case_projection.py` creates the projected summary and saves the scene without the environment builder used by ordinary schema-3 saves (`logic_case_bundle.py:898-901`). Minimal proposed correction is to build a valid case-foundation environment before the projected save, with a focused host regression and review of selected-prefix semantics before any new native proposal. No source edit or runtime retry is authorized by this diagnosis; this is at least the second native hydration occurrence. The single visible DentoCase demo remains open, distinct from later fresh Step 6 simulation and operator acceptance.

### 2026-10-10 — DCP-09..10 projected environment host fix and frozen demo proposal

Commit `912fa3801a0bf3b69b90c28428df636f78eb4942` adds the existing Case Foundation environment builder after selected-prefix pruning and Step 6 authority/Home clearing, before projected schema-3 summary/save. No parser relaxation or source-environment copy. A bounded GPT-6 Luna MAX worker added a host reconstruction test from the exact copied FDI34 source and retained projected MRB: selected branch/trajectory/template geometry and WARNING evidence retained; unselected branch and downstream checkpoints excluded; Base unlocked/revision 0, Home/confirmed task absent; production environment writer/parser round trip matches projected Case Foundation fingerprints and differs from the stale source environment. Existing incomplete/unknown-owner fail-closed check also passed; focused `2 passed` at `data/dentobot-runs/2026-10-10/DCP-09-ENV-FIX-20261010T071520Z/pytest.log`. This is host reconstruction of the previously retained projection, not a fresh Slicer save/load or full-save regression.

One complete *prepared-only* two-stage native proposal is frozen at `data/dentobot-runs/2026-10-10/DCP-09-FDI34-DEMO-20261010T071900Z/`, clean detached source `912fa38`, manifest SHA256 `1888f9009d6c9d607b67993ba8dd43ed113ca5937dd1d291cfb5f6fd19c6d70d`, copied case SHA256 `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`, exact proposed command `bash /home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FDI34-DEMO-20261010T071900Z/input/A_NATIVE_RUN.sh`. Reviewed host static 20-file identities, embedded source/projector hashes, shell syntax, 0700 run directories, private authenticated `:98`, prelaunch/interstage/postcleanup exact host+container Slicer zero gates, exact-owned cleanup and first-failure/no-retry boundaries. Source code SHA256 `da28314db5957b7a32a59e2ccd55420445e74bab3e786118b76f828adc6725c0`. Prior approval consumed; no new native command launched. The requested visible DentoCase Save As/fresh-process reopen and operator verdict remain open, separate from later Step 6 simulation.

### 2026-10-10 — DCP-09..10 approved 071900Z first-failure result

The one approved offline A/private `:98` command from frozen `DCP-09-FDI34-DEMO-20261010T071900Z` ran 07:19:14–07:19:52 UTC at clean `912fa38`, manifest SHA256 `1888f9009d6c9d607b67993ba8dd43ed113ca5937dd1d291cfb5f6fd19c6d70d`, copied case SHA256 `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`. Real XTest Library selection and FDI34 Step 5C Load/Yes succeeded; projector exit 0 and post-save inventory PASS, and the parent loaded the independent partial case disconnected. This establishes the prior empty-environment hydration failure is corrected in this run. The first failed gate was the live selected/excluded audit: required selected IDs were all present, but planned excluded ID `vtkMRMLScalarVolumeDisplayNode1` was observed in the parent scene. The run stopped immediately with rc70; Save As, child audit, separate stage2 fresh-process reopen, and operator verdict NOT REACHED. The meaning of this display-node collision is unresolved; do not infer acceptance or start a retry. Exact-owned cleanup PASS, host/container SlicerApp-real 0/0, private display gone, advisor lock free, retained stack PID348/start7510853 and copied case unchanged. Canonical `RUN-STATUS.md` has the outcome. Run evidence: `evidence/native-library.json`, `evidence/slicer-stage1.log`, `evidence/failure.png`, projector `status.json`/`process.log`, `slicer-exit-stage1.txt`, `recorder-exit.txt`, `evidence/owned-cleanup.log`, and `evidence/slicer-process-counts.log`. This root has no `evidence/run-outcome.json`. Approval consumed, no retry. Next bounded read-only action is to classify the exact display node against source plan ownership and retained scene evidence before any further decision.

### 2026-10-10 — DCP-09..10 071900Z excluded-display read-only classification

A bounded GPT-6 Luna MAX read-only review classified `vtkMRMLScalarVolumeDisplayNode1` in the copied source as real excluded PreDentalSurgery content: source MRML `vtkMRMLScalarVolumeNode1` (`PreDentalSurgery`, `DENTOBOT.CaseScan:true`) references display1 and storage2 (`Data/PreDentalSurgery.nrrd`); the frozen FDI34 host plan has display1 in `remove_node_ids`, not `keep_node_ids`, while the selected input is `PostDentalSurgery` volume2/display2. This positive source identity does **not** identify the live parent object: the 071900Z native audit recorded IDs only and asserted before its class/reference scan or a live closure report. Therefore the observed live display1 could be retained excluded content or a regenerated object assigned the same ID; neither a projection defect nor an audit false positive is established. The selected-prefix contract remains unaccepted despite successful hydration. Keep display1 excluded and the assertion fail-closed. Smallest next diagnostic proposal is a read-only live snapshot of that node's name/attributes/outgoing refs and reverse scene refs immediately before the existing exclusion assertion, in a separately reviewed and authorized run; do not waive the gate or automatically retry. This distinct post-hydration cause count is 1. No source/harness edits or runtime were made for classification.

### 2026-10-10 — DCP-09..10 display-ID diagnostic package, prepared only

One bounded GPT-6 Luna MAX implementation worker prepared a new private diagnostic root `data/dentobot-runs/2026-10-10/DCP-09-DISPLAY-ID-AUDIT-20261010T072540Z/` from the reviewed two-stage 071900Z package. Only `input/native_library_boot.py` has a semantic change: immediately before the unchanged fail-closed excluded-ID assertion, it captures a compact live identity report for `vtkMRMLScalarVolumeDisplayNode1` when observed. The 0600 atomic `evidence/live-excluded-node-identity.json` records ID/class, allowlisted Pre/Post names and source/ownership attribute values (otherwise hashes), outgoing/reverse refs, direct owner volumes with display/storage links, and volume1/display1 versus selected volume2/display2 identities. It stores no raw imaging data or broad attribute dump. A snapshot error still reaches the original assertion. The selected/excluded plan and copied source remain byte-identical; production source clean detached at `912fa3801a0bf3b69b90c28428df636f78eb4942` is unchanged. During coordinator review, the cloned launcher's RUN-STATUS path was corrected to the canonical status record; final normalized diff leaves only the boot diagnostic changed. Final manifest SHA256 `54b830faffbc7860fe5de5867c6231d0c890cb31afef220dc2aed080a74b78ea`, boot SHA256 `40b30137eb7effd82057614c578d1ef1541d6b4487a528093f93e7498f65edff`, copied case SHA256 `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`; exact proposed command `bash /home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-DISPLAY-ID-AUDIT-20261010T072540Z/input/A_NATIVE_RUN.sh`. Static 20-file identity preflight, Python AST, JSON/review hash, shell syntax, 0700 run directories, two-stage host/container zero gates and exact-owned cleanup reviewed. No Slicer/GUI/ROS/native execution or approval from this preparation; prior one-command approval consumed. A separate exact decision is needed. First-failure and no-retry remain.

### 2026-10-10 — DCP-09..10 approved display-ID diagnostic first failure

The one approved offline A/private `:98` diagnostic command ran 07:39:26–07:40:02 UTC from frozen `DCP-09-DISPLAY-ID-AUDIT-20261010T072540Z` (manifest SHA256 `54b830faffbc7860fe5de5867c6231d0c890cb31afef220dc2aed080a74b78ea`, clean `912fa38`, copied case SHA256 `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`). Real FDI34 Step 5C Library Load/Yes, projection and parent hydration succeeded. It stopped at the same unchanged live excluded-ID assertion with no required selected IDs missing and `vtkMRMLScalarVolumeDisplayNode1` present; Save As and fresh stage2 reopen NOT REACHED. The private 0600 `evidence/live-excluded-node-identity.json` SHA256 `6acc834e2e5af7621af8bda21a8d7b7677cd30ca4b294cce72748a0f57daf5ad` shows live display1 has no volume owner or reverse refs and volume1 is absent; selected `PostDentalSurgery` volume2 links display2/storage1. This rules out an attached PreDentalSurgery volume/display pair but does not establish whether display1 is regenerated or a retained orphan source display. The exclusion gate remains failed; no audit waiver or causal source change is justified from this report alone. This is the second distinct live audit occurrence. First-failure stop rc70, no retry; exact-owned cleanup PASS with host/container SlicerApp-real 0/0, private display gone, lock free, retained stack PID348/start7510853 and copied case unchanged. Canonical RUN-STATUS has outcome; private report, native-library.json, slicer-stage1.log, projector process/status, failure screenshot, exit and cleanup logs remain in the run root. No `evidence/run-outcome.json`. Supervisor received the ambiguity packet; any further decision is separate. Operator verdict and later fresh Step 6 simulation remain outside this diagnostic.

### 2026-10-10 — DCP-09..10 072540Z projector artifact check (read only)

No exact 072540Z projected child MRB/DentoCase is retained in the run-owned tree. `evidence/projector-d1e515dccdae49c790de6244928f3fca/status.json` records source SHA256 `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`, exit 0, `childOutputExists=true` under temporary `dentocase-project-h9w60a68/result.dentocase`, and post-save inventory, bundle creation and projector fresh reopen completed; `process.log` names temporary `projected.mrb`. The run tree retains only the copied source `.dentocase`, no projected child or post-save inventory payload; thus no child path/hash is available to compare display1 before parent load. Pinned `case_projection.py` clears references to planned removed IDs and calls `slicer.mrmlScene.RemoveNode(nodes[node_id])` before projected MRB save, but the log cannot prove display1's pre-parent-load identity or absence. Checked `Testing/verification_matrix.json`: `runtime.dentocase_offline_persistence` routes to `Testing/run_dentocase_integration_smoke.py`, which uses `project_package_offline` on a synthetic `template.build` case; the production entrypoint supports an exact copied-case target/branch/checkpoint and releases a destination bundle. Smallest discriminating future proposal is a separately reviewed projector-only offline copied FDI34 `template.verify` run, with its output released to a private run-owned path and hashed, then read-only nested MRB inspection of display1 and volume2/display2 **before** any parent Library load. This is a proposal, not an execution authorization. The full Library/native retry path remains stopped; no edits/runtime in this artifact check. Save As, fresh-process reopen and operator verdict remain open.

### 2026-10-10 — DCP-09..10 projector-only discriminator prepared, not executed

A bounded GPT-6 Luna MAX worker prepared one private projector-only root `data/dentobot-runs/2026-10-10/DCP-09-PROJECTOR-ONLY-20261010T074632Z/` using the existing production `project_package_offline` entrypoint routed from verification-matrix `runtime.dentocase_offline_persistence` / `Testing/run_dentocase_integration_smoke.py`. The thin future runner calls it once on unchanged copied FDI34 source SHA256 `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54` at clean detached `912fa3801a0bf3b69b90c28428df636f78eb4942`, target `target-81e6605865c1261dd534`, branch `guide-f8a3caff373bddb4f157`, checkpoint `template.verify`, with durable private output `output/fdi34-template-verify.projected.dentocase`. A separate read-only host inspector would hash/validate the released child, fail closed on invalid ownership/missing selected volume2-display2, and report presence/references for volume1/display1 versus volume2/display2 from the nested MRML **before** any parent Library load. No patient names, storage paths, raw imaging or broad MRML text are reported. This distinguishes a display1 already present after projection/save from one appearing only during parent load; it does not relax the live exclusion gate.

Final prepared manifest SHA256 `b0fef95e3302db18f2b6c9887d3ce76c98db2d109455a580527721ada3ca0628`; exact future command `bash /home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-PROJECTOR-ONLY-20261010T074632Z/input/A_PROJECTOR_ONLY.sh`. Host static preflight eight pinned files PASS, Python AST and shell syntax PASS; clean source/case hashes, 0700 private run directories, private authenticated `:98`, exclusive advisor lock, exact host+container SlicerApp-real 0/0 gates before/after, retained stack PID348/start7510853 checks, exact-owned cleanup, canonical RUN-STATUS start/end and first-failure/no-retry reviewed. Source case's `scene/case.mrb` member is stored and host ZipExtFile seekable, supporting the inspector path. No Docker/Slicer/GUI/ROS/projector runtime was launched; output child SHA, inventory and inner-MRML result are `NOT_GENERATED`/`NOT_RUN`. The full Library GUI path remains STOPPED; a projector-only execution would require a separate exact decision. Save As/fresh reopen/operator verdict remain open.

### 2026-10-10 — DCP-09..10 conditional projector-only attempt stopped before Slicer

The conditional one-command projector-only attempt ran 08:09:49–08:09:50 UTC from `DCP-09-PROJECTOR-ONLY-20261010T074632Z` (manifest SHA256 `b0fef95e3302db18f2b6c9887d3ce76c98db2d109455a580527721ada3ca0628`, clean `912fa38`, copied case SHA256 `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`). Before launch, a read-only retained-MRML check proved the frozen inspector recognizes the known selected volume2→display2 link in the serialized `references` attribute. Immediate lock, exact host/container Slicer zero, source/case identity, retained stack and private display gates passed. First failure occurred before Slicer/projector: `A_PROJECTOR_SLICER.sh` sourced `/opt/ros/jazzy/setup.bash` under `set -u`, and setup failed on unset `AMENT_TRACE_SETUP_FILES` (private `evidence/slicer-projector.log`). Projector NOT REACHED, child NOT GENERATED, hash unavailable, inspector NOT RUN; display1 pre-parent-load origin remains unresolved. The approved command ended rc1 with no automatic retry. Exact-owned cleanup PASS, host/container SlicerApp-real 0/0, private `:98` gone, advisor lock free, retained stack PID348/start7510853 and copied source unchanged. Canonical RUN-STATUS records start/end/outcome; private first-failure, launcher and cleanup/process logs are in the root. Supervisor received the stop packet. The full Library path remains STOPPED; no corrected projector launch or repair loop under this consumed approval. Save As/fresh reopen/operator verdict remain open.

### 2026-10-10 — DCP-09..10 projector-only nounset correction prepared, not relaunched

The 08:09:49Z projector-only first failure was a distinct pre-Slicer setup cause (count 1): `AMENT_TRACE_SETUP_FILES` unset while `/opt/ros/jazzy/setup.bash` was sourced under `set -u`. One bounded GPT-6 Luna MAX worker prepared a NEW private root `data/dentobot-runs/2026-10-10/DCP-09-PROJECTOR-ONLY-NOUNSET-20261010T081441Z/`. Normalized input comparison against the failed root shows only two semantic shell lines in `A_PROJECTOR_SLICER.sh`: `set +u` before the exact ROS/workspace/native setup sources and `set -u` afterward. The production projector, copied case, target/branch/checkpoint, inspector, lock, process gates, display, cleanup and first-failure/no-retry scope are unchanged. Coordinator ran one permitted non-Slicer container shell smoke of those three sources under this boundary: `THREE_SETUP_SOURCES_NOUNSET_BOUNDARY_PASS`, with nounset on afterward. No Slicer, GUI, ROS connection or projector runtime was launched.

Final manifest SHA256 `9ffd83664c954b810c71c287fc5ffaef19d0738015715934aabebde755c33e43`, corrected launcher SHA256 `9d43bf416a5fb38555c20385147596f5400a630b606fcf125ffd1379924328ed`; exact proposed command `bash /home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-PROJECTOR-ONLY-NOUNSET-20261010T081441Z/input/A_PROJECTOR_ONLY.sh`. Clean detached source `912fa3801a0bf3b69b90c28428df636f78eb4942`, unchanged copied case SHA256 `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`; host static eight-file preflight, shell syntax and Python AST PASS. Child SHA/inspection remain NOT_GENERATED/NOT_RUN. A separate exact supervisor execution decision is required; the full Library path remains STOPPED and display-ID audit cause count remains 2. Save As, fresh-process reopen and operator verdict remain open.

2026-10-10 DCP-09 projector-only nounset-root execution STOP_FIRST_FAILURE: approved one command started 08:20:33Z, ended 08:20:34Z rc1. The three setup sources passed, but pre-Slicer `git -C` source identity check failed because the container-visible linked worktree `.git` points to host-only `/home/tarun/dentobot/ros2_ws/src/DentoBot/.git/worktrees/DentoBot-visible-912fa3801a0b`. Projector, child inventory, and parent Library were NOT REACHED. Exact-owned cleanup PASS: host/container Slicer0/0, display removed, retained stack PID348/start7510853 unchanged, lock free. Evidence under `data/dentobot-runs/2026-10-10/DCP-09-PROJECTOR-ONLY-NOUNSET-20261010T081441Z/evidence/`. Approval consumed; no retry. Display-ID audit remains unresolved at count2. Save As/reopen/operator verdict remain open.

2026-10-10 DCP-09 projector-only source-identity correction PREPARED, NOT RUN: new private root `DCP-09-PROJECTOR-ONLY-NOUNSET-20261010T082459Z`, final manifest SHA256 `12fbf81069657adc9f423e7399e966151a48f34c1ea1b4988f298b0c86854487`. One bounded GPT-6 Luna MAX worker prepared run-script/test bytes only. Coordinator normalized diff and static preflight PASS (12 files, ten imported-source hashes); exact shared pre-Slicer prefix no-Slicer container smoke PASS with explicit container Git admin HEAD/clean, setup nounset boundary, pinned environment and Slicer0. Copied FDI34 case SHA unchanged; projected child absent. No native launch approval consumed for this root. Conservative pre-Slicer preparation sequence count2; display-ID audit count2. Full Library retry remains STOPPED; Save As/reopen/operator verdict open.

2026-10-10 DCP-09 projector-only 082459Z approved command STOP_FIRST_FAILURE before start marker: host source hash output created `evidence/host-source-preflight.log`, then static preflight rejected that run-owned file as outside its package allowlist. rc1; no display, Slicer, projector or child. Postcheck host/container Slicer0/0, advisor lock free, retained stack PID348/start7510853 unchanged. Exact approval consumed; conservative pre-Slicer preparation sequence count3 ceiling reached. No automatic repair or retry; supervisor judgment required. Full Library STOPPED, display-ID audit count2 unresolved, Save As/reopen/operator verdict open.

2026-10-10 DCP-09 revised projector-only package PREPARED, NOT RUN: root `DCP-09-PROJECTOR-ONLY-NOUNSET-20261010T084228Z`, manifest SHA256 `e700ffc5295145dd4c3ee797fa4c203c7c46a6f31603c9678c748e51db7e343d`. Static preflight now checks frozen manifest input/PROPOSAL hashes and private modes while permitting only named private run-owned evidence files; output/child must be absent. Actual top-level host prelaunch dry-run branch passed TWICE on the same root with first pass evidence retained; shared container pre-Slicer prefix smoke PASS. Host HEAD/clean and ten hashes, container running, stack348/7510853, Slicer0/0 passed. No START marker, display, Slicer, projector or child. Conservative pre-Slicer sequence count3 ceiling stands; future projector execution requires separate explicit revised-plan supervisor decision. Full Library STOPPED; Save As/reopen/operator verdict open.

2026-10-10 DCP-09 approved projector-only discriminator PASS: root `DCP-09-PROJECTOR-ONLY-NOUNSET-20261010T084228Z`, start 08:51:33Z, end 08:51:55Z rc0. Durable private copied-FDI34 child `output/fdi34-template-verify.projected.dentocase` SHA256 `9b03d38814500568728774a84c1fdcc3649d17e92bf80648bd984e71b8ba9391`; nested MRML volume1/display1 absent, selected volume2/display2 present and linked. Valid schema3 inventory, complete ownership, unknown0. This places the 072540Z live orphan display1 at/after parent Library hydration rather than in the projected child. Parent Library, Save As, independent parent reopen and operator verdict NOT REACHED; full Library runtime still STOPPED pending decision. Exact-owned cleanup PASS, Slicer0/0, retained stack348/7510853 unchanged, lock free.

2026-10-10 DCP-09 read-only Luna MAX Library display provenance review: projected child SHA `9b03d38814500568728774a84c1fdcc3649d17e92bf80648bd984e71b8ba9391` excludes volume1/display1 and retains volume2→display2, but 072540Z live orphan display1 lacks pre-load identity, semantic signature and add/remove chronology. Pinned parent load uses clear-scene import and later rebuilds CaseFoundation display volumes; source MRB is not loaded in parent by boot. Source residual in serialized child is ruled out; pre-existing parent residue versus regenerated/reused ID remains unresolved. ID-only audit remains fail closed. Proposed smallest discriminator is pre-load baseline plus node remove/add ledger and semantic signatures at import/bind/hydration; host fixtures must distinguish newly-added nonmatching orphan from true excluded-source content and fail ambiguous provenance. No source/harness edits or runtime; Library Save As/reopen/operator verdict open.

2026-10-10 DCP-09 display lifecycle diagnostic PREPARED, NOT RUN: new private root `DCP-09-DISPLAY-LIFECYCLE-20261010T091454Z`, manifest SHA256 `4af0e36945680866ccded010331f6c1d64bd2a2b335706b356deaa247f309a09`, clean source `912fa3801a0bf3b69b90c28428df636f78eb4942`, copied case SHA unchanged. Bounded GPT-6 Luna MAX worker added run-owned observational four-ID lifecycle/semantic probe and diagnostic-only stage1 harness; unchanged real XTest Library Load/Yes and strict selected/excluded assertion, no Save As/stage2. Coordinator read-only host/container static preflight PASS 22 hashes, five host fixtures PASS, shell syntax/Python compile PASS. Dynamic VTK hooks remain unverified until separately authorized run; missing chronology/instrumentation fails closed. Full Library demo STOPPED, live audit cause count2; proposed third diagnostic needs supervisor execution decision. Save As/reopen/operator verdict open.

2026-10-10 DCP-09 third display lifecycle diagnostic STOP_FIRST_FAILURE before native START: `evidence/interstage-gates/` already existed empty in frozen root; launcher required absence before creating it. Host/container static 22-file preflight and PRELAUNCH Slicer0/0 PASS. rc1; no display, Slicer, Library Load, lifecycle report, Save As or reopen. Postcheck Slicer0/0, advisor lock free, retained stack348/7510853 unchanged; no owned cleanup needed. One approval consumed. Third same-cause diagnostic yielded no provenance; no autonomous native repair/retry, Tarun judgment required. Operator verdict open.

2026-10-10 DCP-09 FDI34 demo exception package PREPARED, NOT RUN: new private root `DCP-09-FDI34-DEMO-EXCEPTION-20261010T124856Z`, manifest SHA256 `9635f447c5def025fc69b9f50bd641cba83ff69b17d42d41c9fb6c3461630d37`, clean source `912fa3801a0bf3b69b90c28428df636f78eb4942`, copied case SHA `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`. Derived from reviewed 071900Z two-stage path; host/container static 24-file hash check PASS, 19 exception fixtures PASS with strict audit FAILED, syntax/contract checks PASS. Frozen `evidence/interstage-gates` absent; prior failure screenshot/report preserved. Narrow proposed exception requires explicit Tarun decision and only exact orphan display1 conditions; audit remains FAILED and operator verdict open even if Save As/fresh reopen later pass. No native launch, no exception approval yet. Full Library demo remains STOPPED; existing live audit and pre-Slicer attempt histories unchanged.

2026-10-10 DCP-09 demo package status-path correction PREPARED, NOT RUN: new root `DCP-09-FDI34-DEMO-EXCEPTION-20261010T131243Z`, manifest SHA256 `df1953b500685d63f63f2f5950a6a91aa3ed4c07b7996e88ca24ef79e6190bec`. Normalized semantic diff from 124856Z is only `A_NATIVE_RUN.sh` STATUS target changed to canonical S6-NEXT-HANDOFF RUN-STATUS.md; all other changes are root repins. Manifest 24/24 hashes and shell syntax PASS, interstage gate directory absent. Prior root untouched; no native run or display1 exception approved.

2026-10-10 DCP-09 FDI34 demo exception attempt1 STOP_FIRST_FAILURE: approved 131243Z run 13:22:59–13:23:36Z reached real XTest Library Load/Yes and independent partial hydration. Strict audit FAILED: missing=[], unexpected=[display1], plus 21 dangling references and 2 ROS nodes. Narrow exception STOP (other audit failures and orphan display1 identity exact check failed). No Save As or fresh-process reopen. Exact-owned cleanup PASS, host/container Slicer0/0, private display removed, retained stack348/7510853 unchanged, lock free; copied case SHA unchanged. One of up-to-five total new attempts used; no automatic retry. Read-only classification of extra failures and display1 identity is the next bounded proposal, without widening exception. Operator verdict open.

2026-10-10 DCP-09 attempt1 timeboxed read-only classification: live audit retains 21 dangling-reference entries and two ROS-class node counts, but not exact edge rows, ROS IDs/classes/creators, or current display1 class/name. The display1 identity predicate false narrows to class mismatch or nonempty name, exact value unknown; earlier 072540Z observation cannot substitute. Matching retained projected child lacks display1/volume1 and ROS-class nodes, selected volume2→display2 intact; extras arise on parent-load/hydration side but route unresolved. Smallest proposed next evidence is a read-only pre-strict-gate allowlisted snapshot with edge rows, ROS IDs/classes/refs, display1 class/name and lifecycle chronology; strict FAILED gate and narrow exception unchanged, Save As/reopen only if existing conditions pass. No edit/run, cap 1/5 used.

2026-10-10 DCP-09 attempt2 scene-snapshot package PREPARED, NOT RUN: new root `DCP-09-FDI34-DEMO-EXCEPTION-20261010T133748Z`, manifest SHA256 `3489e120233396085f86c68d9968a248d940aabf273f6fa6a2e2969724f72c85`, clean source/case/FDI34 selection unchanged. Two allowlisted read-only 0600 snapshots are staged before Library load and before strict audit for display1 identity, dangling edge rows, ROS-class node identities/refs and disconnected state; unknown names hashed. Strict FAILED audit, narrow exception, Save As/stage2 gates and canonical STATUS unchanged. Host-only 26-file static PASS, privacy fixture PASS, 19 exception fixtures PASS, shell syntax PASS; interstage gate absent. No native/runtime/GUI/ROS launch. Tarun cap 1/5 used; attempt2 requires separate supervisor decision.

2026-10-10 DCP-09 attempt2 roles API correction PREPARED, NOT RUN: new frozen root `DCP-09-FDI34-DEMO-EXCEPTION-ROLES-20261010T135347Z`, manifest SHA256 `3e01cc59f5f6d9c7377b9c14917bdac28ebb4dc53e17badfb8f44c3f9e617411`. Sole semantic code change is snapshot `GetNodeReferenceRoles` Python-list enumeration matching pinned production; new-root repins include correct RH. Host-only 26-file hash/static, syntax, snapshot fixture and 19 strict-FAILED exception fixtures PASS; gate directory absent. Tarun existing up-to-five same-scope approval recorded; exact attempt2 command awaits supervisor adjudication. No runtime, cap remains 1/5 used.

2026-10-10 DCP-09 FDI34 demo attempt2 STOP_FIRST_FAILURE: approved 135347Z run 13:59:35–14:00:11Z reached real Library Load/Yes then strict audit FAILED; narrow exception STOP. Private before/after snapshots show display1 absent pre-click, present afterward with nonempty hashed name; 21 dangling `vtkMRMLColorTableNodeFile*.txt` storage edges to missing ColorTableStorageNode1..21 after load; two ROS-class IDs present before click and after, disconnected. This identifies the current failed predicate but does not prove ROS instance creation route. Save As/reopen NOT REACHED. Exact-owned cleanup PASS, Slicer0/0, display removed, retained stack348/7510853 unchanged, lock free, case SHA unchanged. Tarun cap 2/5 used; no automatic retry or audit widening. Next action is read-only baseline/policy classification for these exact rows before any correction.

2026-10-10 DCP-09 attempt2 timeboxed read-only classification: 21 post-load ColorTable storage dangling edges are absent from source/child MRML and selected/excluded plan; likely Slicer palette infrastructure, exact creation unproven. Two ROS-class nodes were present before Library click and after, reciprocal refs, disconnected, absent source/child/plan; pinned bridge documents process-lifetime default ROS node, exact subscriber creator unproven. Display1 absent pre-click/child, post-load generic `VolumeDisplay` name with no owner/refs/attrs; source name hash matches only generic label, so provenance remains unresolved and hard fail. Any palette/default ROS audit-policy change needs Tarun approval; display1 remains fail-closed. No run/edit; Save As/reopen still open, cap 2/5 used.

2026-10-10 DCP-09 FDI34 demo continuation attempt3/5 STOP_FIRST_FAILURE: exact approved 151300Z root, manifest SHA256 `713ff119e77cd64477d9d9c2dc00fd98a3e3d260b3c09aa3297992cc6ba64bde`, ran 14:49:22–14:49:59Z rc70. Real Library Verify/Load/Yes and parent hydration reached; strict live audit remained FAILED (missing=[], display1 unexpected, 21 palette dangling edges, 2 ROS). Exact continuation stopped because the pre-click and post-load ROS subscriber had case_owned=True, violating the approved no-case-ownership predicate; no audit widening. Save As, child audits, fresh reopen and operator verdict NOT REACHED. Exact-owned cleanup PASS, host/container Slicer0/0, private :98 removed, lock free, stack348/start7510853 and copied case unchanged. Three of five permitted attempts used; no automatic retry or attempt4 authorization. Private evidence under `DCP-09-FDI34-DEMO-CONTINUATION-STRICT-20261010T151300Z/evidence/`; canonical RUN-STATUS has START/END/outcome.

2026-10-10 DCP-09 attempt3 bounded read-only GPT-6 Luna MAX review: retained pre-click and post-load sanitized ROS subscriber snapshots contain only id/class/hashed name/refs/SaveWithScene/case_owned. They report case_owned=True but omit attribute key names, so the matching key, its pre-click presence, and genuine case ownership versus overbroad marker match are unresolved. Worker stopped without edits/runtime. Smallest future discriminator is attribute NAMES ONLY for the exact subscriber at both phases under a separately reviewed decision; no values, gate/policy change or attempt4 authorized. Cap3/5, Save As/reopen/operator verdict open.

2026-10-10 DCP-09 FDI34 demo-only attempt4/5 STOP_FIRST_FAILURE: exact approved 145923Z root, manifest SHA256 `5f4c1c37001209841b6bf3e1cccef30f4f2eaf3290b668ab7fe3c1519dc6c68d`, ran 15:02:26–15:03:08Z rc70. Real XTest Library Load/Yes and parent hydration reached. Strict live audit remained FAILED; exact waiver continuation gate passed. Independent Save As produced child SHA256 `68852abd0353a356404722688a34f5d62031b793fec924d162fe37f494124ac2`; child identity/integrity/ownership/new identity checks passed, copied source unchanged. First failure at unchanged host `audit_saved_child.py` select_prefix: missing `template.verify` checkpoint artifact and selected dependencies rejected. Child audit did not pass; adjacent palette/ROS audit and distinct fresh-process reopen NOT REACHED. Exact-owned cleanup PASS, host/container Slicer0/0, :98 removed, lock free, retained stack348/start7510853 unchanged. Four of five attempts used; no automatic retry/attempt5 authorization. Operator verdict NOT_PERFORMED. Retained child and traceback are in `DCP-09-FDI34-DEMO-ROS-WAIVER-ATTEMPT4-20261010T145923Z/evidence/`; canonical RUN-STATUS has START/END/outcome. Next bounded route is read-only saved-child inventory/registry comparison against projected child and select_prefix contract, without audit relaxation.

2026-10-10 DCP-09 attempt4 timeboxed read-only GPT-6 Luna MAX review: independently saved child passed identity/integrity/ownership/new package checks but unchanged host audit failed at production `select_prefix(template.verify)` before retained-node/exclusion/field comparisons. Projector child was previously schema3/ownership complete. No pre-Save-As artifact/revision snapshot was identified; Save As state loss versus already-missing live state remains unresolved. Worker did not independently decode exact artifact counts/revisions within timebox, so no product correction or auditor relaxation is justified. Smallest route is host-only two-package artifact/dependency/revision comparison and search for a pre-save live snapshot; any missing capture requires separate decision. No edit/runtime/attempt5 package/token; cap4/5, strict audit FAILED, fresh reopen NOT REACHED.

2026-10-10 DCP-09 exact host-only two-package comparison: SHA-verified projected child `9b03d388...b9391` has 28 artifacts, 207 projection node IDs, template.verify WARNING preview and branch verification artifact `verification:guide-f8a3caff373bddb4f157` depending on vtkMRMLModelNode47; production select_prefix permits FDI34 template.verify. SHA-verified attempt4 Save As child `68852abd...24ac2` has 27 artifacts, 211 projection node IDs, lacks that sole verification artifact/preview, and production selection rejects; vtkMRMLModelNode47 and its template.build artifact persist in both. Thus eligible checkpoint exists in projected package and is absent from independently saved package; exact loss timing between parent hydration/live scene and Save As is unresolved because pre-save reports omit artifact/revision state. Auditor remains correct/fail-closed. Smallest route is pinned parent hydration/Save As source-path review and focused host regression if causal; otherwise a separately authorized pre-save IDs/revisions capture. No edits/runtime/attempt5 prep; cap4/5, strict audit FAILED, fresh reopen not reached.

2026-10-10 DCP-09 bounded Luna MAX read-only source review: pinned 912fa38 Save As path calls schema3 prepare, repeated trajectory-registry sync and summary before inventory. `syncDentoCaseTrajectoryRegistry` clears verification_revision when template PreparedBranchRevision differs from recomputed branch revision; inventory then omits template.verify artifact unless current revision/hash evidence matches. Exact projected child has branch revision 69a750…, Current, verification revision 1eb066…, template.verify WARNING; Save As child has revision 202bd7…, Stale, empty verification revision, model47 persists, artifacts 28→27. This product-state gate explains selector failure; exact first mutation may occur in post-hydration sync or Save As sync because pre-save revision snapshot is absent. No auditor relaxation justified. Smallest next route is host-only replay of exact projected branch/model metadata through pinned sync→schema3 prep→summary→inventory; if still ambiguous, separately decide names/IDs/revisions-only pre-save/per-sync capture. No edits/runtime/attempt5 prep; cap4/5, strict audit FAILED, operator verdict open.

2026-10-10 DCP-09 host-only replay seam STOP: bounded Luna MAX worker verified exact package hashes and found indexed legacy projection-sync test substitutes jaw/world fingerprints and never loads exact DentoCase MRML; schema3 prep requires Slicer environment/geometry. Feeding saved fingerprints as fake inputs would be circular, so no exact production replay/regression or source fix was claimed. Package delta: branch revision 69a750…4065b Current verification revision 1eb066…f6cd → 202bd7…61a9 Stale empty; template Current/WARNING → Stale/NotVerified, VerificationJson hash 08498af…cca6b → absent; trajectory fingerprint changed and target-docking model became Stale. Legacy verification upgrade and foundation-pose invalidation are candidates, but no pre-Save-As snapshot identifies first mutation. Smallest missing evidence is allowlisted IDs/revisions/fingerprint hashes after hydration and around sync/Save As under separate decision. No edit/runtime/attempt5 prep; cap4/5, strict/final FAILED, operator verdict open.

2026-10-10 DCP-09 coordinator checkpoint — AWAITING MATERIAL OPERATOR REVIEW: SHA-verified projected child `9b03d388...b9391` contains `template.verify`; attempt4 independent Save As child `68852abd...24ac2` lacks the verification artifact and production `select_prefix` rejects it. First mutation phase remains unresolved. Exact host replay seam is unsuitable; proposed observational phase wrappers were not proven safe or frozen within the preparation timebox, so preparation stopped without a new package. No live writer/run, attempt5 token or execution. Cap 4/5 used; strict audit and final outcome remain FAILED, reopen and operator verdict open. Next action requires a NEW material operator choice: spend the final run on reviewed diagnostic instrumentation, or preserve it and redirect scope.

2026-10-10 17:28Z DCP-09 direct pre-Save-As preparation STOP: attempt4 boot has a direct insertion point immediately before `_createCaseBundle`, but the timeboxed worker did not verify the allowlisted field extraction/fail-closed capture or freeze a new package. Worker interrupted; no new root, run-owned file edit, approval token, test, or native run. Focus remains AWAITING MATERIAL OPERATOR REVIEW; cap 4/5, strict/final FAILED, fresh reopen and operator verdict open. Tarun's “Continue” did not authorize a fifth command.

2026-10-10 DCP-09 material direction: Tarun chose “Diagnose template.verify loss: locate the revision change; a full demo may need another run.” This authorizes one preparation-only proposal for a direct, read-only pre-Save-As registry/template snapshot and projected/saved comparison. It does not authorize attempt5 execution, a token, policy widening or acceptance. Cap 4/5, strict/final FAILED and operator verdict open.

2026-10-10 DCP-09 diagnostic proposal preparation STOP at observation gap: GPT-6 Luna MAX read-only source review confirmed a direct stage1 hook before Save As and raw live branch/template revision, state and fingerprint getters. SHA-verified projected child `9b03d388...b9391` has the selected verification artifact. The live parameter registry has no selected artifact list/count, and `_openLibraryPartialCase` discards `_openCaseBundle` inspection; no widget cache exposes that list. A live artifact count would require inventory computation or an inference from verification revision, outside the approved read-only sampler. No frozen root, run-owned edit, host fixture, token or attempt5 run. First mutation phase unresolved; cap 4/5, strict/final FAILED, verdict open. Further observation design requires a new material decision.

2026-10-10 DCP-09 supervisor routine scope adjustment: Tarun's objective is the revision-change interval; a live artifact count is not needed. One preparation-only direct pre-Save-As raw registry/template snapshot may omit artifact count and early-stop logic, leaving existing Save As, production child selector and fresh reopen gates unchanged. It must not call sync, inventory or inspection. No attempt5 execution/token approved; cap 4/5, strict/final FAILED, operator verdict open.

2026-10-10 18:04:50Z DCP-09 narrow revision proposal preparation STOP at supervisor timebox: the direct boot hook and raw getter seam were identified, but no root, sampler, manifest, fixture or static/identity review was completed. Worker stopped before creating partial files; no runtime/token or attempt5. No revision interval diagnosis was obtained. Focus AWAITING MATERIAL OPERATOR REVIEW; cap 4/5, strict/final FAILED, verdict open.

2026-10-10 DCP-09 revised preparation sequence: Tarun approved staging one input-only private root before assigning one bounded Luna MAX worker to implement the direct raw pre-Save-As revision snapshot and pure fixture. This is guidance for preparation after the prior no-freeze stops, with the attempt history preserved. No fifth native command, token or policy change is authorized; cap 4/5, strict/final FAILED, operator verdict open.

2026-10-10 DCP-09 revision trace proposal PREPARED, NOT LAUNCHED: coordinator staged one private root `/home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FDI34-REVISION-TRACE-20261010T181031Z`; manifest SHA256 `95c2689035a95a9e1eca27c13553ad73cfd39193c8838ab4dc097a62e0a71a4d`, proposal SHA256 `eb2328f5a0fe7730239a8757d2fba0383525c5eff9f2811cb9bf0facf9950352`. One GPT-6 Luna MAX worker added only the run-owned raw sampler, pure fixture and direct call immediately before `_createCaseBundle`; parent repinned run/approval identity and metadata. The sampler reads raw registry and template attributes, records allowlisted revisions/states and fingerprint/VerificationJson hashes, and never invokes sync/inventory/inspection; no artifact count or early stop. Existing Save As, child selector and fresh reopen remain unchanged. Host fixture PASS (read-only/privacy/fail-closed/0600); 30-file host static PASS; 15 Python AST, bash syntax, source/case SHA, normalized diff and private empty-directory/approval/gate checks PASS. Foundation fingerprint is explicitly absent if raw registry lacks it; comparison can locate projected→pre-save versus pre-save→saved interval, not an exact internal sync. No container or native behavior verified, approval record/token or fifth run. Strict/final FAILED, cap 4/5, operator verdict open; exact launch needs a separate Tarun decision.

2026-10-10 DCP-09 fifth/final approved revision trace STOP_FIRST_FAILURE: exact 181031Z root, manifest SHA256 `95c26890...0a71a4d`, ran 19:02:32–19:03:21Z rc70. Real XTest FDI34 `template.verify` Library Load/Yes and parent hydration reached; strict scene audit FAILED and exact demo waiver continued. Pre-Save-As raw snapshot SHA256 `53d7af5a...04540dae` shows branch revision `fecd3a66...55ce87` Current, verification revision `6135fa16...d3ed6b`, matching template PreparedBranchRevision and VerificationJson SHA; template Current/WARNING. Retained projected child SHA `9b03d388...b9391` had branch `69a750...4065b` Current and verification `1eb066...f6cd`, so revision and verification payload changed by pre-save (Library load/hydration interval). Independent Save As child SHA `c1e6dee4...44dbafd` passed identity/integrity/ownership/new-case checks but had branch `202bd7...61a9` Stale, empty verification revision, template Stale/NotVerified; unchanged production `select_prefix` rejected missing `template.verify` artifact and selected dependencies. This locates a second revision/verification loss between the direct pre-save snapshot and saved child, not its exact internal sync call or pre-save artifact count. Fresh-process reopen NOT REACHED. Exact-owned cleanup PASS, host/container Slicer0/0, private display removed, advisor lock free, retained stack348/start7510853 and copied case SHA unchanged; private token file removed. Cap 5/5 consumed, no retry or sixth run; strict/final `FAILED_STRICT_SELECTED_EXCLUDED_AUDIT`, operator verdict NOT_PERFORMED. Next bounded non-runtime action: pinned source-only review of post-hydration registry sync and Save As schema3 prep/summary sync against these three revisions, then one focused host regression only if it can reproduce the specific transition without fabricated geometry. No audit relaxation or runtime is authorized.


### 2026-10-10T21:17:55Z — DCP-09 dedicated Astra solo preparation and first-defect stop

Operator explicitly confirms dedicated Codex GPT-6 Astra low/light SOLO; no supervisor/subagents. Current coordinator assumes sole DCP-09 controlled-record ownership here, preserving all prior dirty edits. Source work is isolated at `/home/tarun/dentobot-worktrees/dcp-partial-case-complete-astra-20261011` on `repair/dcp-partial-case-complete-astra-20261011`, clean HEAD `912fa3801a0bf3b69b90c28428df636f78eb4942`; failed T3 launch did no source work. Current explicit scope supersedes historical worker/supervisor routing. Backlog-first review retains existing DCP-09..10 Priority 3 and overlap with S6-REUSABLE-CASE-SETUP; higher-priority Step 6 tasks are outside this one-job authorization.

Authorized scope: preparation only, observe actual production revision fingerprint invocation and Save As boundaries, one fresh private root, host mechanism fixture, no product source/case change. Staged `/home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z` (UTC start 10 October, local date 11 October), excluding old approval/output/bytecode. Helper 5,468 bytes reuses getter-only sampler and actual production expression instead of geometry reconstruction. Mechanism fixture exit0 PASS for single call-through, input/result identity, restoration, exception identity, privacy/0600, missing-call and swallowed-error fail-closed; host-only static 35-file preflight exit0 PASS. No native case replay claim.

First substantive integration defect: new boot bare import assumes run input is on sys.path; existing boot uses explicit file loaders and the sampler is loaded under another module name. Isolated host import reproduction exit1 `ModuleNotFoundError: fingerprint_trace`. Stopped without fixing/retrying per operator gate. Manifest is explicitly STOP_PREPARATION_FIRST_SUBSTANTIVE_DEFECT, not launch-ready. Review/commands/results/identities: `/home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z/REVIEW.md` and `host-evidence/`. Manifest SHA `38ca277c07a26147ce5fc61e212997724ae3fc160f273318b9ca76aee355b52a`, copied case SHA `be58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54`. No source edits, container/native/Slicer/GUI/ROS command, token, original save, retained-stack mutation or Item4. Cap5/5 remains exhausted; strict/final FAILED_STRICT_SELECTED_EXCLUDED_AUDIT; fresh reopen/operator verdict NOT_PERFORMED. Next bounded material choice: authorize only explicit-file loading plus injected sampler and focused host loader check, then freeze/review; sixth runtime would still need separate material/exact-command authorization.


### 2026-10-11T00:39:02Z — DCP-09 authorized loader correction, prepared only

Tarun answered “Authorized” to the preparation-only explicit-path loader correction and focused host check. This supersedes the preceding preparation stop only for that correction; no sixth native command/token or audit change. Same private root `/home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z` retained; prior files preserved under host-evidence/before-loader-correction and failed import evidence unchanged. Run-owned observer now loads via exact file path, with existing raw snapshot callable/branch ID injected; no ambient input sys.path dependency. Source checkout remains clean at 912fa3801a0bf3b69b90c28428df636f78eb4942.

Checks: `python3 -I /home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z/input/check_trace_loader.py /home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z` exit0 TRACE_LOADER_PASS (exact boot loader/context AST, isolated imports, callable identity, no native imports). `PYTHONDONTWRITEBYTECODE=1 python3 /home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z/input/check_fingerprint_trace.py /home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z/host-evidence/fixture-loader-corrected` exit0 PASS (single call-through/input/result, restoration, exceptions, privacy/0600, missing-call/swallowed-error fail-closed). Python AST and bash -n PASS; host-only static_preflight.py --host-only exit0 PASS37. The -I invocation ignored PYTHONDONTWRITEBYTECODE and created host bytecode; only completed run-owned input/__pycache__ was removed before freeze. No production/native test or exact case replay claim.

Proposal `/home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z/PROPOSAL.md`; manifest SHA `17ca75a54a4fd343ac6bd8118e6170c04fa0587de087b14091294cfbeab1994c`, proposal SHA `f256a38ad45ed7ce0d0d67d6c14a6f1e526dd4c1946054391d61547bb68e5731`, helper 5414 bytes. Exact source/case/contract identities and semantic loader diff retained in host-evidence. Frozen inputs, empty runtime directories and absent approval record verified. Preparation complete; awaiting separate Tarun material decision to exceed 5/5 and authorize exact launcher if desired. Diagnostic keeps strict FAILED status and exact historical demo-only waivers; no full DCP acceptance follows even if it later saves/reopens. Fresh reopen/operator verdict NOT_PERFORMED.


2026-10-11T00:41:26Z DCP-09 operator delegation override: Tarun says “Use luna max workers for testing”, then “Authorized” after the coordinator states one read-only host worker scope. This supersedes earlier SOLO/no-subagents only for bounded testing. Live T3 catalog confirms codex/gpt-6-luna/max; native worker /root/dcp09_host_test_review dispatched with exact model/effort, no recursive delegation. Astra remains coordinator/sole controlled-doc owner, no supervisor added. Worker reads frozen manifest 17ca75a54a4fd343ac6bd8118e6170c04fa0587de087b14091294cfbeab1994c and existing host evidence; probes only concrete exception/restoration/privacy/fail-closed gaps, writes only new private host-evidence/luna-review-UTC directory, stops first substantive defect. Frozen inputs/source/cases/docs read-only. No unchanged-test repetition, native/GUI/ROS/Docker command, token, audit widening or sixth-run authorization. Previous exact-command/material decision remains pending; cap5/5, strict/final FAILED, operator verdict NOT_PERFORMED.


2026-10-11T00:52:11Z DCP-09 one Luna MAX host review returned: no concrete observer defect, no new tests/probes or worker files, no frozen/source edits. Worker inspected existing PASS evidence rather than repeating it. Coverage limitation: extracted revisionOf fixture has one invocation per sync while nonlegacy production has legacy+current calls; both pose-key shapes accepted by observer, two-call sequence not directly tested. Coordinator bounded the extended review with interruption/final request; no forced PASS or native acceptance. Report `/home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z/host-evidence/luna-review-report.md`. Manifest re-read SHA unchanged 17ca75a54a4fd343ac6bd8118e6170c04fa0587de087b14091294cfbeab1994c. Testing delegation policy now Luna max per Tarun; coordinator remains Astra. Separate sixth-run material/command decision pending, no token/native command, cap5/5, strict/final FAILED, operator verdict NOT_PERFORMED.


2026-10-11T00:56:21Z DCP-09 material/exact-command approval: Tarun “Approved” after final notice that sixth-run approval remained pending. Coordinator records exactly one sixth offline diagnostic under frozen manifest 17ca75a54a4fd343ac6bd8118e6170c04fa0587de087b14091294cfbeab1994c and PROPOSAL.md at `/home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z`. Command `bash /home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z/input/A_NATIVE_RUN.sh`; exact frozen demo-only display1/palette/ROS waivers, strict FAILED retained, first-failure stop/no retry, independent child audit before distinct disconnected reopen. Prior5/5 history preserved; this is one additional explicit attempt, not unlimited cap reset. Fresh private approval record/token issued without logging token. One GPT-6 Luna MAX worker assigned runtime execution, coordinator sole controlled-doc/acceptance owner; no supervisor or recursive delegation. No source/case change, original save, retained-stack mutation, ROS connection, hardware or Item4. Host double-call fixture coverage limit disclosed, not native acceptance.


### 2026-10-11T01:06:05Z — DCP-09 separately approved sixth diagnostic stopped with discriminating trace

One Luna MAX runtime worker executed `bash /home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z/input/A_NATIVE_RUN.sh` once under frozen manifest 17ca75a54a4fd343ac6bd8118e6170c04fa0587de087b14091294cfbeab1994c. Native 01:01:43–01:02:25 UTC, rc70. Worker initially imposed an unsupported hexadecimal-token precheck; coordinator corrected that pre-spawn assumption to the frozen validator's actual nonempty/token-hash contract. No launcher had run on that precheck and no input/token was changed. Host+container static37, material approval and zero-process gates passed. Real Library Verify/FDI34 Load/Yes and Save As reached; strict live audit FAILED, exact demo-only waiver continued. Seven child identity checks PASS; unchanged audit_saved_child.py production select_prefix rejected missing template.verify/dependencies. Independent disconnected child reopen NOT_REACHED; projector reopen is not this gate. No retry.

Thirty-record production fingerprint trace SHA c36cc59cd29906ffaab705fd7ade9c1cc615fcc500a65643f2dfb93f045adae7 ends save_return. First current-frame calculation (row4) retains fecd3a66…55ce87 Current/verification; second (row8), still in prepareDentoCaseSchema2ForSave, produces202bd7…61a9 Stale/empty verification. Equivalent input comparison finds only model47 state Current→Stale, model42 state Current→Stale and model42 orientation Confirmed→unknown hashed value. Other ordered inputs, including trajectory/insertion/foundation, match. Thus inner observed invalidation interval is narrowed; exact setter/correctness remains unknown, no product fix inferred. Saved child SHA 62671cff427bbf0dfea1a5fa8a00f22ca870c50bd9154545ccb211a3825c4e5f. Analysis and commands/results: `/home/tarun/dentobot/data/dentobot-runs/2026-10-10/DCP-09-FINGERPRINT-PREP-20261010T211417Z/evidence/OUTCOME.md`, trace-first-transition-analysis.json, run-outcome.json and recorder.log.

Cleanup PASS: host/container Slicer0/0, :98 gone, advisor lock free, stack348/start7510853 unchanged, copied source SHA unchanged, isolated source clean. Secret runtime token removed; worker reported ancillary one-use interstage field exposed in tool output, not the material approval secret; no values retained in controlled notes. Prior5/5 plus this separately approved sixth are consumed; strict/final FAILED_STRICT_SELECTED_EXCLUDED_AUDIT, operator verdict NOT_PERFORMED. Next bounded non-runtime starting point: schema preparation between first/second sync, environment/foundation snapshot and model47/model42 invalidation setters. No seventh command or audit change authorized.


2026-10-11T01:12:59+00:00 DCP-09 Tarun “Do it” authorizes causal source correction and Luna MAX host testing toward completion, not implicit seventh runtime. New run root /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-PARTIAL-PARAMETERS-20261011T011008Z. Initial root creation failed because UTC date parent absent; corrected before diagnostics by parents=True, no runtime. Saved child model42/47 StaleReason explicitly A Step 4C docking dimension changed; model42 OrientationState Draft. Read-only archive extraction finds global targetDockingYawDeg=-25 in original and sixth saved child, selected model42 saved construction yawDeg=15. Projection rebinds model references but not scalar branch settings; widget_docking compares recipes and marks stale. Coordinator implements selected retained docking recipe restoration in isolated checkout case_projection.py using existing normalizer, respecting clearParameters and not altering geometry/verification. One existing Luna MAX worker assigned only Testing/test_dentocase_projection.py and new host evidence for positive/negative regression; production file frozen during tests. No source acceptance yet, no seventh run/token/audit-policy change.


2026-10-11T01:16Z DCP-09 source diagnosis: exact-parameter-witness.json under DCP-09-PARTIAL-PARAMETERS-20261011T011008Z records original/child global targetDockingYawDeg=-25 and selected FDI34 assembly construction yawDeg=15. Child model42 and model47 stale reason is exactly “A Step 4C docking dimension changed.” widget_docking._updateTargetDocking compares the normalized editor recipe against saved model parameters and calls existing stale setters. Projection had rebound selected model references without restoring their scalar recipe. Proposed correction validates the complete selected recipe through the existing production normalizer before writing only retained fields, respecting clearParameters. Geometry, verification evidence and audit policy are unchanged. Focused Luna MAX host validation in progress; native correction unverified, no seventh run authority.


2026-10-11T01:26Z DCP-09 source-host checkpoint: isolated branch repair/dcp-partial-case-complete-astra-20261011 committed 8e7e0b2662f94fe62536932089c87c051eff8ecf. case_projection restores the selected saved docking recipe through existing production validation, preserving checkpoint clearing and geometry/verification state. Luna MAX regression results: focused8 PASS, projection30 PASS/1 skipped, exact pure.dentocase_integration matrix137 PASS/1 skipped; git diff --check PASS. Logs under /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-PARTIAL-PARAMETERS-20261011T011008Z/evidence/. Parent reviewed actual diff and results. These are host tests only, not full partial-load acceptance. Operator latest “Use luna max workers wherever possible for efficiency” extends bounded auxiliary usage; parent retains design/integration/records/acceptance, one current worker. Worker now prepares only fresh exact source-pinned proposal, no token/native command. Prior5+1 consumed; strict live audit and child/fresh-reopen/operator gates remain open.


2026-10-11T01:38:14.699312+00:00 DCP-09 exact seventh-diagnostic preparation complete, NOT AUTHORIZED/NOT LAUNCHED. One Luna MAX worker staged /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-RECIPE-VERIFY-20261011T012646Z, clean detached visible source8e7e0b2662f94fe62536932089c87c051eff8ecf, unchanged copied casebe58b2431c4829c3101a2dd732c3dcfde823013461a399b0e9f071f0f34f7e54. Manifest5c700ecfdc09e103ae7d57cc7a351e2f339acd312bd36d6eb9eb8adf075b3b81; proposal d6b584eaad424fc7d5b211b56c52f56b364ba8f6f1c765575fcc419862b08282; scope64268346c80bfdb963f478381e01db5d598d081fe6f35195202550a590b71980. Host static39/Python18/bash5 PASS; initial pre-correction output retained, required stale projector digest and worktree-admin pin corrected before final check. Parent independently rehashed all manifest entries/scope, inspected normalized script and contract differences, verified no approval/token. Beyond run/source rebinding, scripts add normalizer digest assertion and direct runtime status to run-local evidence; canonical record remains parent-owned. Contract changes limited to run ID, diagnostic scope and scope hash; exact audit exception conditions unchanged. Command: bash /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-RECIPE-VERIFY-20261011T012646Z/input/A_NATIVE_RUN.sh. Exactly one offline serialized attempt, 900s, first failure stop, independent Save As then strict child/continuation audits then distinct disconnected reopen only if gates pass. Prior5+1 consumed; new material/command authorization required, no automatic retry. Strict live FAILED/final FAILED_STRICT_SELECTED_EXCLUDED_AUDIT and operator verdict NOT_PERFORMED remain. Host source fix is not full feature completion.


2026-10-11T01:40:48.810906+00:00 DCP-09 Tarun Approved exact seventh proposal, manifest 5c700ecfdc09e103ae7d57cc7a351e2f339acd312bd36d6eb9eb8adf075b3b81. Exactly one serialized offline command bash /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-RECIPE-VERIFY-20261011T012646Z/input/A_NATIVE_RUN.sh; source8e7e0b2662f94fe62536932089c87c051eff8ecf. Fresh private approval record/token issued; exact historical demo-only conditions, strict FAILED retained, first failure stop/no retry. One Luna MAX runtime worker; parent records/acceptance owner. No hardware, ROS connection, original save, retained-stack mutation or Item4.


2026-10-11T01:47Z DCP-09 seventh separately approved attempt STOP_FIRST_FAILURE, rc70, 01:44:33–01:45:27Z, source8e7e0b2662f94fe62536932089c87c051eff8ecf. Luna MAX worker executed exact frozen launcher once. Before launch worker again guessed approval record fields; parent directed existing validator, which approved without changing token/record. No native spawn occurred on guessed precheck. Save As complete; all7 identity checks PASS. Strict saved-child auditor passed valid/complete ownership, new case/package, no history, selected branch and production select_prefix(template.verify), then failed audit_saved_child.py:39 because excluded source ID vtkMRMLScalarVolumeDisplayNode1 persisted. This is native evidence that the recipe correction resolves the previous missing-template.verify failure, not full child acceptance. Strict live FAILED unchanged: display1,21 dangling palette refs,2ROS nodes; exact approved demo-only continuation. Continuation-child audit and distinct disconnected reopen NOT_REACHED; operator verdict NOT_PERFORMED. Saved child SHA5d917b609950b124a8d8cca53e4ce43ec2db160ac7a6a5331f7cf23b2fa67e15. Cleanup PASS host/container0/0, retained stack348/start7510853 unchanged, copied source SHA unchanged. One-time token removed; approval/evidence retained. Prior5+sixth+seventh consumed, no eighth command authorized and no retry. Evidence: /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-RECIPE-VERIFY-20261011T012646Z/evidence/{OUTCOME.md,run-outcome.json,recorder.log,native-library.json,save-as-identity-check.json,owned-cleanup.log,slicer-process-counts.log}. Next bounded source-only route: determine why excluded display1 returns during parent hydration/Save As and correct its ownership/lifecycle without audit weakening; preserve palette/ROS findings as unresolved.


2026-10-11T01:57:05.718891+00:00 DCP-09 Tarun “Proceed and fix” authorizes source lifecycle correction and host testing; no eighth runtime. Backlog-first DCP route retained, latest seventh outcome read, graph query first mistakenly run in isolated checkout (no graph) then successfully overlay; graph stale after prior exit143 refresh, no alternate graph built. Existing protocol/matrix/index reused. One Luna MAX read-only evidence worker found display1 source/child same ID/class/name-hash, different level/window/visibility; source has volume owner, child is unreferenced orphan. Projected temporary package absent, so exact creator and instance identity unresolved, not asserted. Evidence /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-DISPLAY-LIFECYCLE-20261011T015219Z/evidence/display1-lifecycle-review.{md,json}. Parent chose a bounded restore-lifecycle correction, not an ID exception: after hydration inside recovery transaction, discard only exact scalar displays absent audited saved nodeIds with no live incoming/outgoing refs, displayable owner, singleton or custom attributes. All reference/attribute reads complete before any removal, error propagates to recovery; absent inventory no-op. Saved/or referenced/custom nodes preserved; no geometry, source case or strict auditor change. One Luna MAX worker now tests actual helper preservation/error cases and existing pure matrix, owns only Testing/test_case_bundle.py. Production frozen during testing; native effectiveness not yet known.


2026-10-11T07:45Z DCP-09 resumed after Tarun Continue. Source clean0000b4e4cd4009d7687a410da1f913ca5de0ec75 contains orphan restore cleanup; parent reviewed helper/test diff, focused15/module41/pure matrix151 PASS1skip. Initial test-only ordering assertion corrected once, failure preserved. Previous worker no longer present and no ORPHAN proposal root exists; one new GPT-6 Luna MAX preparation worker /root/orphan_verify_prep assigned exact fresh package, no runtime. New proposal narrows prior display exception to require display1 absent; remaining exact palette/ROS exceptions and strict FAILED retained. All prior7 native attempts consumed. Bounded graphify --no-cluster session no longer available, no process found, empty log/no success marker: refresh unverified, no claim or repeated expensive run. No source edits on resume or eighth launch.


2026-10-11T07:58:09.151891+00:00 DCP-09 eighth proposal PREPARED ONLY after Tarun Continue. Source0000b4e4cd4009d7687a410da1f913ca5de0ec75 clean; host151PASS1skip, no new native run. One Luna MAX prep worker staged /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-ORPHAN-VERIFY-20261011T074639Z. Parent reviewed semantic gate/native/reopen changes, verified all39 manifest files and canonical scope, strict saved-child auditor byte-identical. Proposed material contract now requires unexpected_excluded empty and explicit display1=None plus no owners/reverse refs; old display exception removed, exact21palette/2ROS conditions remain, strict/final FAILED retained. Fixture PASS29negatives; host-only static39 PASS; worker syntax18Python/5bash PASS report (invoking syntax shell snippet not retained, limitation explicit in log). Logs recorded from worker captured output after checks. Final manifestcf74492b4dce4d1f2b0ec2d8facc505ee4944d26d3ec0c79806438edd9a06287; proposal040e6fa39753780b45650bf721053fa599735325be3bd4375bc15999f4b13c67; scopec827f455d60103579dbf3ea6d2aea139bd7926d0081e80ea0aabec6dd6a6ed68. No approval/token/cache/runtime output. Exact command bash /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-ORPHAN-VERIFY-20261011T074639Z/input/A_NATIVE_RUN.sh; single900s serialized attempt, stop first failure, strict child/continuation audit before distinct disconnected reopen. No eighth authority until separate material/exact-command decision. Full feature acceptance and operator verdict still pending.


2026-10-11T08:02:47.974346+00:00 DCP-09 Tarun Approved exact eighth proposal, manifest cf74492b4dce4d1f2b0ec2d8facc505ee4944d26d3ec0c79806438edd9a06287. Exactly one command bash /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-ORPHAN-VERIFY-20261011T074639Z/input/A_NATIVE_RUN.sh, source0000b4e4cd4009d7687a410da1f913ca5de0ec75, narrowed display1-absence material gate; strict audits unchanged. Fresh private approval issued, no secret disclosure. First failure stop/no retry; no original save, ROS connection, retained stack mutation, hardware or Item4.


2026-10-11T08:07:23.161457+00:00 DCP-09 eighth run08:04:13–08:04:56Z rc70: display1 absent/excluded empty PASS, Save As identity7 PASS; strict child now fails step6EnvironmentJson clearing, reopen NOT_REACHED. Cleanup PASS host/container0, source unchanged, token removed. User directs plan remaining work, implement/test together uninterrupted with current runtime. No live Slicer session remains; coordinator consolidates source/host repair and one combined native proposal rather than successive single-defect runs. Frozen expected plan clears step6EnvironmentJson while current production owner foundation.pose; reconcile contract before changing assertion. Combined root /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-COMBINED-REPAIR-20261011T080723Z. Prior8 native attempts consumed; no inferred automatic retries, hardware/ROS connection/retained stack changes.


2026-10-11T08:12Z DCP-09 combined environment reconciliation: initial ownership-only hypothesis refined. projection._STEP6_AUTHORITY_PARAMETERS explicitly clears step6EnvironmentJson before rebuilding, while accepted source912fa38 and TASKS projected-environment fix require a fresh schema3 Case Foundation snapshot for hydration. Thus final child empty-default assertion is stale stage semantics, not authority escape. Read-only eighth child production parse PASS, raw environment equals workflow environment; Base unlocked/rev0, HomeNone; foundation/planning/base fingerprints match caseFoundation. Evidence DCP-09-COMBINED-REPAIR-20261011T080723Z/evidence/environment-reconciliation.json. Proposed new final auditor must validate regenerated snapshot properties while keeping other clearing checks; no blanket skip or product parser relaxation. ROS default singleton source explicitly warns destruction during scene clear crashes warm New Case; preserve it. Broad any-DENTOBOT-attribute case_owned heuristic also includes DENTOBOT.SimulationStatusSubscriber runtime marker; precise ownership reconciliation is required before any changed audit interpretation.


2026-10-11T08:17:48.038435+00:00 DCP-09 combined remaining-gate review: all eighth saved-child downstream host predicates inspected; 56/57 clearing checks pass, sole mismatch final step6EnvironmentJson (production clears then regenerates by accepted912fa38 contract). All excluded IDs/ROS nodes/palette owners and storage targets absent child. Parent specifies production-parser validation, equality to workflow environment, unlocked Base/rev0/no Home and three nonempty matching Case Foundation fingerprints; one Luna MAX worker implements/tests only run-owned auditor, no product changes. Preserve exact strict live FAILED (21palette/2runtime ROS); module-owned default singleton must survive and runtime subscriber attribute heuristic is not case deletion authority. New root DCP-09-COMBINED-REPAIR-20261011T080723Z stages a single ninth proposal, no token/approval/native command issued; eight attempts consumed. Current runtime ended, contrary to user assumption. Distinct reopen and operator verdict remain outstanding; backlog priority/dependencies unchanged.


2026-10-11T08:27:41.029003+00:00 DCP-09 combined host checkpoint, not completion: new root /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-COMBINED-REPAIR-20261011T080723Z. Run-owned final auditor now validates deliberately rebuilt environment via production parser/lineage equality/unlocked Base revision0/no Home/nonempty matching Case Foundation fingerprints; remaining56 clear checks unchanged. Luna MAX captured host commands exit0: exact eighth child HOST_CHILD_AUDIT_PASS, continuation child8/8 PASS, environment1positive10negative PASS. Parent continuation29negative PASS, syntax22 plus worker2 PASS, final static43 PASS. Parent reviewed actual diff and captured evidence. Final manifest c0ca0655025045352f4fbb33025a6530aaaf7582ad3a401bafe4432960f35adc, auditor01cf9a175fd298e772198495d9a747363cec204630a7aeeb980269469f625044, canonical scope66ff18b282d982791a7c4436fca7e5f01f04c7a04b9b8c761d9843f5cfbe8d6a. Review initially rejected self-embedded scope digest caused by staging dictionary alias; serialization corrected, independent scope/hash assertions and static check then PASS; no native execution. Source clean0000b4e unchanged, all files0600/root0700. Exact ninth proposal bash <root>/input/A_NATIVE_RUN.sh covers load/Save As/both child audits/distinct fresh disconnected reopen,900s serialized stop-first-failure/no retry. Prior8 attempts consumed; separate material/command authorization required, no token. Strict live/final FAILED retained for exact21palette/2ROS residuals; fresh reopen NOT_RUN and operator NOT_PERFORMED. Milestone remains case-platform/DCP-09..10 pending in backlog, no queue/priority/dependency change. Coordinator review and PROPOSAL.md are concrete review artifacts.


2026-10-11T08:45:25.732869+00:00 DCP-09 Tarun explicitly Approved, one shot: exact frozen ninth combined proposal manifest c0ca0655025045352f4fbb33025a6530aaaf7582ad3a401bafe4432960f35adc. One serialized command bash /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-COMBINED-REPAIR-20261011T080723Z/input/A_NATIVE_RUN.sh. Stop first failure/no retry; strict FAILED retained; no hardware/ROS connection/original save/retained-stack mutation/Item4. Private single-use approval created.


2026-10-11T08:47:27.871562+00:00 DCP-09 approved ninth one-shot08:45:36–08:46:38Z exit1. Exact frozen combined command executed once at source0000b4e; Save As PASS, strict saved-child HOST_CHILD_AUDIT_PASS and continuation child PASS. ChildSHA06e3218c8f82f928c52a6b8f788f770c63cbe253fb7347c53e77cd5d17ff624c. Distinct stage2 process26174 started only after stage1 ended/interstage host-container Slicer counts0/0. _openCaseBundle returned, then native_reopen_boot.py:117 failed AttributeError: CaseBundleInspection has no integrity attribute. Post-open identity/connectivity checks NOT_REACHED; fresh reopen is NOT_VERIFIED, never PASS. Strict live FAILED21palette/2ROS retained, excluded empty/display1 absent. Operator verdict NOT_PERFORMED. Source and child hashes unchanged; cleanup PASS host/container0/0 and retained stack348/start7510853 unchanged. Single-use token removed; approval retained. All9 attempts consumed, no retry or tenth authority. Stop-first-failure honored. Remaining bounded defect is run-owned reopen helper return-type contract; no product failure inferred and no helper/source edit performed after stop. Evidence /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-COMBINED-REPAIR-20261011T080723Z/evidence/{run-outcome.json,native-reopen.json,saved-child-audit.json,continuation-child-audit.json,coordinator-launch-result.json,owned-cleanup.log,slicer-process-counts.log}.


2026-10-11T08:59:12.856792+00:00 DCP-09 latest Tarun direction: Proceed for full completion, return to clean FDI34 advisor GUI not fully tested. Coordinator interprets this as authorization to correct the demonstrated run-owned return-type defect and complete one narrow fresh disconnected reopen using the ninth audited child, not repeat successful Library/Save As or silently accept live strict failure. New root DCP-09-REOPEN-COMPLETE-20261011T085704Z; source0000b4e unchanged. CaseBundleInspection actual schema manifest/workflow lacks library-summary properties; production open returned before helper failure. One Luna MAX worker owns run-owned helper + host interface fixtures only; parent runtime/records. Exact prior residual palette/ROS contract preserved, strict FAILED; no original save/retained-stack mutation/ROS connection/hardware/Item4 in this gate. Canonical clean Step5C→Step6 main5a then saved-branch5b route recovered from TASKS; advisor acceptance remains open and is not inferred from DCP persistence. Existing backlog priorities/dependencies unchanged. Graph known stale after recorded failed refresh; no new codebase graph claim. Fresh native execution follows reviewed host adapter and pinned narrow package; stop first substantive failure, no automatic retry.


2026-10-11T09:02:23.663676+00:00 DCP-09 narrow reopen reviewed and authorized by latest full-completion direction. Manifest5f7b82777b465c8641ac5762198b717b66360969f9f66ae8e2a0809d90a8495a, source0000b4e, exact ninth child06e3218c..., helper real production schema1positive7negative PASS; parent diff reviewed, syntax23 and static48 PASS. Command bash /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-REOPEN-COMPLETE-20261011T085704Z/input/A_NATIVE_RUN.sh executes fresh stage2 only; reused ninth audits/Save As provenance explicit. Stop first failure/no retry; strict live FAILED retained. No hardware/connection/original save/retained-stack mutation. Private approval issued; no secret output.


2026-10-11T09:03:36.023326+00:00 DCP-09 narrow corrected fresh reopen09:02:23–09:02:44Z technical PASS in distinct process26782, source0000b4e unchanged. Reused ninth independent Save As and both PASS child audits by immutable childSHA06e3218c8f82f928c52a6b8f788f770c63cbe253fb7347c53e77cd5d17ff624c; no repeated Library/Save As. Corrected return-type adapter passes all6 post-open type/path/manifest case/package/workflow/ownership checks, loaded parameter identity, offline before/after and unchanged source/child hashes. Screenshot fresh-reopen-mainwindow.png visually inspected: FDI34 Step5C selected, verification table and WARNING visible; no advisor GUI acceptance inferred. Raw live/final FAILED_STRICT_SELECTED_EXCLUDED_AUDIT and commandrc70 intentionally retained for prior21palette/2ROS residuals, not a reopen error. Recorder ffmpeg0 but manifest partial because intentional command70; no complete-video claim. Cleanup PASS host/container0/0, retained stack348/start7510853 unchanged, token removed. No retry. Tarun requested verdict asynchronously; operator PENDING, task remains backlog. Clean advisor return follows existing baseline matrix then separate consented-trial/cancel/manual gates, with normal Import/robot/Base/Connect/scene/Home and case/native/source checks; no connected action started. Evidence /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-REOPEN-COMPLETE-20261011T085704Z/evidence/native-reopen.json and run-outcome.json.


2026-10-11T09:05:33.388015+00:00 DCP-09 Tarun accepts demonstrated FDI34 partial-load/independent Save As/audited child/distinct fresh disconnected reopen as baseline for advisor testing. Exact child06e3218c8f82f928c52a6b8f788f770c63cbe253fb7347c53e77cd5d17ff624c; verdict evidence /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-REOPEN-COMPLETE-20261011T085704Z/evidence/operator-verdict.json. This resolves this baseline operator gate only; global live palette/ROS strict FAILED, broader DCP/full-load/UX obligations and advisor GUI acceptance remain open. Resume existing clean FDI34 advisor route without inherited Step6 authority; no blanket policy waiver, hardware or Item4 authority.


2026-10-11T09:13:32.478183+00:00 Tarun requests new Astra low/Luna MAX handoff and updated clean FDI34 advisor plan. Reconciled primary9Oct advisor final RETEST4 and noHome FDI34 stop; accepted partial child now input, not inherited authority. Plan /home/tarun/dentobot/data/dentobot-runs/2026-10-11/DCP-09-REOPEN-COMPLETE-20261011T085704Z/ADVISOR-CLEAN-RESTART-PLAN.md. Existing backlog sole queue; no runtime during handoff. Destination existing isolated checkout0000b4e, not nonGit overlay.


## 11 October — clean FDI34 advisor and planning reconciliation

Tarun transfers sole ownership to this Codex GPT-6 Astra low thread, one bounded GPT-6 Luna MAX auxiliary, no supervisor. Latest direction adds successful planning of the given FDI34 trajectory to advisor GUI completion; all supported adjustable parameters may be considered, mouth opening never above46mm. A solid impossibility conclusion under the fixed trajectory/collision constraints is acceptable, but a finite heuristic search or planner timeout is insufficient proof. Current handoff remains runtime-free; prior exact-command, ownership, first-failure and operator-verdict gates persist, with no DCP cap reset or automatic RunB.

Concrete reconciled contract: [UPDATED-TESTING-PLAN.md](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-CLEAN-PLAN-20261011T091706Z/UPDATED-TESTING-PLAN.md). Existing task IDs/priorities/dependencies remain. Accepted input SHA06e3218c8f82f928c52a6b8f788f770c63cbe253fb7347c53e77cd5d17ff624c is baseline-only; global live21palette/2ROS audit FAILED and broader DCP/GUI acceptance remain open. Primary `/home/tarun/dentobot/docs/logbook/2026-10-09.md:169–234` fills the history absent from this worktree's daily record: final FDI14 RETEST4 at13649e6 has R08 unconfirmed restoration/R10 refusal and pending human verdict, not positive Apply/save acceptance. ConsentON requires explicit6.3Task reconfirmation. FDI34 has no accepted saved nonzeroHome; historical IKseed/zeroHome/opening/Base trials cannot supply it.

Read-only comparison confirms advisor_service/home/identity/feasibility logic, baseline/precheck/consented commands, session driver and recorder unchanged from13649e6; GUI/input/branch/load paths changed. Full hashes in `/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-CLEAN-PLAN-20261011T091706Z/evidence/scoped-drift.json`. Existing headed runner serves its inbox only after Connect/scene ack; prepare a bounded disconnected setup checkpoint before using it on clean Step5C. Normal robot/Import/Base review→Connect/scene→guarded Home→precheck→consentOFF baseline→verdict precede consented search/cancel/reconfirmation/positive ApplySave/reopen. Main clean5a precedes saved-branch5b; downstream frame-sync lower/second-opening/L4/L5 and per-tooth acceptance stay gated.


### 11 October13:38UTC — S6-ADVISOR-GUI-01 clean setup checkpoint and prelaunch stop

Tarun “Go ahead” resumed the approved combined advisor/FDI34 plan. Parent implemented opt-in DENTOBOT_HEADED_CLEAN_SETUP_ONLY in existing headed runner: normal robot/Import then disconnected capture before Base/Connect, refusing inherited Base/Home and conflicting opt-ins; current Base review details retained without acceptance. Local commit068ca378557d8465bc63275d21b36a3fde32cfa7, two Testing files only, clean isolated source. Host runner/advisor169 PASS (4.63s), final capture12 PASS (0.77s); git diff --check PASS. Logs `/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-SETUP-PREP-20261011T133127Z/host-checks.log` and host-final-capture.log. No Luna substitution (worker quota remained unavailable).

One recorded setup attempt under user Go ahead STOPPED BEFORE Slicer: A_NATIVE_SLICER.sh guessed Git admin directory from renamed worktree basename. Actual admin remained DentoBot-visible-068ca37HEAD after git worktree move; error “not a git repository”. Display/recorder started, Slicer/Load/Import/Base/Home/advisor/planning NOT_REACHED. Native return1, cleanup PASS, host/containerSlicer0/0, retainedstack348/start7510853 unchanged. No retry. Evidence `/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-SETUP-PREP-20261011T133127Z/evidence/` recorder.log,outcome.json,owned-cleanup.log,postflight.json. This repeats a known Git-map failure class; prior attempts are retained, no new retry budget claimed.

Corrected fresh package [S6-ADVISOR-GUI-01-SETUP-GITMAP-20261011T133709Z](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-SETUP-GITMAP-20261011T133709Z/PROPOSAL.md), manifestd278aba27a67203418d32b4483b0758d7b957e4508e6850777cd729f3697e57d, PREPARED ONLY. Uses actual git rev-parse --absolute-git-dir mapped to container, and container HEAD/clean preflight before display. Actual read-only container preflight PASS; source/case/guard identities stable. Exact command `python3 /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-SETUP-GITMAP-20261011T133709Z/input/run_setup.py --execute`. Same single300s disconnected capture and first-failure/no-retry bounds, no acceptance/Connect/planner/save. Separate operator disposition required after the one-shot stop; no automatic launch. Advisor/full FDI34 planning not complete. Graphify overlay update --no-cluster timed out45s exit124 with no success marker; refresh remains unverified. No publication/Drive sync/hardware/Item4.


S6-ADVISOR-GUI-01 update 2026-10-11 13:54 UTC: corrected disconnected setup captured at source34f5a7a, host170 PASS, cleanupPASS. Import succeeds; Base review rejects stale case_or_base_identity_changed, Base unlocked/Home absent. Advisor and FDI34 planning remain open, operator GUI verdict pending before production Base identity reconciliation. No planning or motion, opening<=46mm. Evidence /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-SETUP-CAPTURE-20261011T135256Z/evidence/outcome.json; full account in logbook/2026-10-11.md.


## 2026-10-11T13:59:28.258358+00:00 — accepted setup; Base identity and advisor automatic Task Home handoff

Tarun explicitly accepts the disconnected setup checkpoint at /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-SETUP-CAPTURE-20261011T135256Z, and directs “resolve base identity next”. He further states: “Missing home is not a valid state check anymore, we perform auto task home, and need to test and improve it to make it part of the advisor proposal and essentially have high success rate of setting task home ideal to respective target tooth and trajectories.” This supersedes the earlier blanket Item4/auto-Home exclusion for this requested scope. Missing saved Home is expected input to automatic Task Home generation, not a standalone blocker or an excuse to stop. Runtime collision/identity validation and explicit acceptance of a generated proposal still apply; no zero/stale Home or PreEntryIKseed may be promoted to accepted Home. No high-success-rate claim yet: successor must define measurable tooth/trajectory-specific evidence and retain infeasibility outcomes.

New sole orchestrator: Codex GPT-6.1 Sol medium, one bounded GPT-6 Luna MAX worker at a time, no supervisor, no recursion, no worker controlled-doc/runtime/policy ownership. Selection explicitly confirmed by this user request; do not ask again. Current parent stops after dispatch. No runtime/test/cleanup during handoff. Checkpoint acceptance is recorded separately without overwriting immutable runtime evidence. Existing first-failure, GUI verdict, exact runtime scope, fixed collision constraints and mouth opening<=46mm remain. Earlier pending checkpoint verdict is resolved by this message; full advisor/FDI34 acceptance remains open.


### 2026-10-11T14:08:37.061944+00:00 — S6-ADVISOR-GUI-01 / S6-LIVE-01 sole-owner continuation

Latest Tarun instruction authorizes up to ten Luna MAX or Sol light auxiliary assignments for active work, superseding the one-at-a-time limit. This does not require ten workers or create recursion/supervision/runtime authority. Current Sol6.1 medium owns source integration, runtime and controlled records; bounded disjoint app-owned LunaMAX source review and advisor-draft implementation only. Accepted disconnected setup verdict is settled; absent Home is input to automatic draft generation. Existing acceptance/identity/collision/<=46mm gates persist.

Parent implementation adds field-name-only Base identity mismatch evidence (no stale rebinding) and opt-in disconnected checkpoints before/after Import. Focused host Base17 PASS and clean setup14 PASS; source/runtime root [/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-AUTOHOME-20261011T140338Z](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-AUTOHOME-20261011T140338Z). Exact runtime mismatch is not identified by the old setup JSON, which lacks identity-field evidence. Native diagnosis remains separately scoped. Advisor missing-Home action is being wired to the existing guarded 6.2 draft owner, with no automatic authority or search-readiness relaxation. [Measurement contract](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-AUTOHOME-20261011T140338Z/AUTO-HOME-MEASUREMENT.md) distinguishes coverage, guarded draft, explicit acceptance and complete repeated route; high success remains unmeasured. No runtime/retry/cap reset or accepted FDI34 path.


2026-10-11T14:15:19.447445+00:00 S6-ADVISOR-GUI-01/S6-LIVE-01 source checkpoint: parent reviewed both bounded T3 LunaMAX results and all actual edits; local clean commitcab6c748336580eb1ad281186db1141b9a0c0319,8files. Advisor noHome offers existing automatic draft owner only; search still requires reviewed/accepted runtime Home, zero/stale handling preserved. Base read-only identityChangedFields preserves frozen candidate and stale rejection; existing clean harness observes before Load, after Load/before Import, after Import/before navigation. Combined472 host tests PASS5.71s; first combined2 stale-harness assertion failures retained and corrected, not product guard failures. Worker108 PASS and focused17/14 evidence retained. Exact Base field native result remains unresolved; no FDI34 route/autoHome rate acceptance.

Frozen next diagnostic [/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-AUTOHOME-20261011T140338Z/PROPOSAL.md](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-AUTOHOME-20261011T140338Z/PROPOSAL.md), manifestb212edf6b44ec77f2f1719893d9220f8df6797516bb3a9d6319e64f3a96f24e5: `python3 /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-AUTOHOME-20261011T140338Z/input/run_setup.py --execute`. PREPARED ONLY; one300s disconnected copied-child Load/Import with field/interval capture, private display/recording and exact-owned cleanup; no acceptance/Connect/Home generation/planner/save. Package hashes/syntax PASS; fresh read-only preflight host/containerSlicer0/0, retained348/start7510853 and guardb71e2b4d… stable; source/container cab6c74 clean. Runtime must repeat checks under lock. New exact-command approval remains pending; accepted old setup verdict not re-requested. Existing DCP caps/strictFAILED and automaticRunB hold unchanged. Graph refresh45s exit124 no success marker, remains unverified.


2026-10-11T14:23:50.088122+00:00 S6-ADVISOR-GUI-01 approved Base identity diagnostic STOP_FIRST_FAILURE: sourcecab6c74, frozen manifestb212edf6… commandrc1. Runner rejected host path DentoBot-visible-cab6c74 because production per-SHA provenance requires12-character suffix DentoBot-visible-cab6c7483365. Parent preparation missed this rule; no guard relaxation justified. Slicer launched, but case loading/LoadRobot/Import/Base identity capture NOT_REACHED; no Home/Connect/planner/save. CleanupPASS host/containerSlicer0/0, retainedstack348/start7510853/nativeguard unchanged; private display/owned processes cleaned. Exact approval consumed, no retry or old setup verdict reversal. Raw evidence /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-AUTOHOME-20261011T140338Z/evidence/{slicer-stage1.log,outcome.json,postflight.json,execution-assessment.json}, video/whole-run/whole-run.mkv. New root S6-ADVISOR-GUI-01-BASE-PATHFIX-20261011T142152Z preparation-only: source unchanged, correct separate12-character visible checkout and actual derived Git admin; bounded LunaMAX host fixture validates the production _checkout_profile/_checkout_evidence with positive/negative paths before freeze. Prior seven-character checkout and frozen run remain immutable. Native Base cause/FDI34 planning/autoHome runtime remain open; all historical caps retained.


2026-10-11T14:30:56.672849+00:00 S6-ADVISOR-GUI-01 corrected launch package FROZEN/PREPARED ONLY: /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-PATHFIX-20261011T142152Z/PROPOSAL.md, manifestSHA256 93b0eb5232fe913a1f9fc9e23098fee197b9e9e6a7f3d95e36691cfc77bc53a8, source clean cab6c748336580eb1ad281186db1141b9a0c0319. Correct host/container visible checkout uses required12-character suffix cab6c7483365 and actual Git admin. Bounded T3 LunaMAX provenance-fixture task completed; production guard positive actualenvironment PASS and all6negative fixtures rejected. Parent reviewed160-line helper, added actual clean-status digest verification and exclusive per-invocation evidence filenames, preserving original delegate report. Final wrapper --check PASS, all Python/shell syntaxPASS, frozen16 input/source entries plus production20source/runner hashes checked. Read-only ownership preflightPASS host/containerSlicer0/0 retained348/start7510853/nativeguard unchanged; runtime must repeat under exclusive lock. No runtime/process launch or retry in this correction. Prior approved run stopped at checkout-name guard before case/configuration; whole-run video only6.6seconds, inspected frame black/cursor, no Base GUI verdict evidence.

Exact pending new command: `python3 /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-PATHFIX-20261011T142152Z/input/run_setup.py --execute`. One300s disconnected normal LoadRobot/Import with production Base identity field/interval observations, actual screenshots/video, exact-owned cleanup. No Base acceptance/restage, Home generation/acceptance, Connect/planner/save. Prior approval consumed at first failure; corrected command awaits new explicit disposition, not old setup reacceptance. Existing DCP caps/globalstrictFAILED, opening<=46mm, trajectory/collision/identity guards and no automaticRunB remain. Next evidence-dependent work: identify first changed Base field, minimal lifecycle correction preserving fail-closed review; then accepted Base/guarded automatic Home draft + tooth/trajectory measurement and full advisor/FDI34 route or defensible infeasibility. Finite search failures do not prove infeasibility; high success unmeasured.


2026-10-11T14:38:35.197359+00:00 S6-ADVISOR-GUI-01 corrected exact approved diagnostic completed rc0 BASE_IDENTITY_CAPTURED_ONLY/cleanupPASS. Tarun replied Approved to frozenmanifest93b0eb5232fe913a1f9fc9e23098fee197b9e9e6a7f3d95e36691cfc77bc53a8; exact command executed once, approval.json retained. Actual report /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-PATHFIX-20261011T142152Z/evidence/step6_headed_review_20261011T143629465341Z.json: before_robot_load staged/current/nochangedfields; normal Load Robot7/7 immediately causes stale case_or_base_identity_changed with sole field baseAttributes.DENTOBOT.RobotBasePlacementAuthority; after Import unchanged samefield. Matrices identical. Import successful, Base unlocked, noHome, disconnected; no Base/Home acceptance, planner/search/save. Host/containerSlicer0/0 retained348/start7510853/nativeguard/source unchanged at postflight. Actual configuration screenshot inspected: robot7/7, offline, incisor gap40.06mm. Video probed and hashed; parent-assessment.json retains evidence/privacy/acceptance limits. No operator GUI verdict inferred; prior accepted setup remains settled.

Production setter located logic_robot_placement.py:createOrUpdateRobotPlacement missing-authority initialization to ManualSimulationBaseUnreviewed. Premature _ensureStep61BaseEditCandidate triggers on6.1 entry before that normal load initialization. Minimal source correction assigned bounded T3 LunaMAX task base-authority-stage-gate-20261011-r1, only widget_robot_manual.py/test_robot_manual_jog_ui.py: require nonempty available authority before automatic/explicit begin; never set it as part of staging, auto-load, clear/restage/rebind stale draft or weaken facade comparison. Existing stale/uncertain acceptance evidence retained. Parent sole source integration/runtime/docs/acceptance. Next runtime must use corrected source/frozen plan under new exact decision; no automatic retry/RunB. Home/FDI34 route acceptance and high success remain unmeasured.
OPEN-QUESTION-CLOSED [S6-ADVISOR-GUI-01] (2026-10-11): Which exact Base candidate identity field first changes in clean normal Load→Import? -> sole observed change RobotBasePlacementAuthority during LoadRobot, not Import; three native checkpoints in above report.


2026-10-11T14:50:21.094854+00:00 S6-ADVISOR-GUI-01 Base lifecycle source correction reviewed/integrated: clean localcommit0cc888bfb3661ead0bb2a6950a174d43a9b6ba2e, only widget_robot_manual.py and test_robot_manual_jog_ui.py. Automatic/explicit begin require available nonblank placement authority, preventing captured premature missing-authority draft before normal Load initialization. No authority write/autoLoad, stale rebind/drop/cancel, facade identity change or acceptance relaxation. Availability guard is not proof of actual Load or Base readiness/acceptance; all later production review/validation gates remain. T3 LunaMAX task completed;86 manualhostPASS; parent reviewed finaldiff and combinedmanual/facade/headedsource375PASS6.22s. No repeated unchanged advisor/DCP tests.

Corrected-source verification package /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-STAGING-20261011T144128Z/PROPOSAL.md FROZEN/PREPARED ONLY, manifestSHA256d08137f3f74260ad2db208a873553904804deb9294cb604b7d5beb5d3e371159,19input/source entries including manualwidget/authoritysetter;20production-source+runnerhash parity checked. Actual derived12-character visiblecheckout DentoBot-visible-0cc888bfb366 and Git admin. Final wrappercheckPASS positiveproductionprovenance+6negative; native resultgate positive+8negativePASS rejects premature/stale/missing/disconnected-scope violations. Initial preparation fixture suffix mapping aligned with newlypinnedSHA before finalfreeze; pre-final input/manifest/proposal bytes and all checkreports retained without overwrite. Read-only preparationownershipPASS host/containerSlicer0/0 retained348/start7510853/nativeguard stable; actual runtime requires freshchecks under lock. No active native writer or newruntime.

Exact pending operatorcommand: `python3 /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-STAGING-20261011T144128Z/input/run_setup.py --execute`. Single300s disconnected unchangedcopyLoadRobot/Import, firstcheckpoint unstaged, allidentitycheckpoints current with no changedfields, finalBase current/staged. Actualcapture/screenshots/video and exact-ownedcleanup. No Base/Homeacceptance, Connect, automaticHomegeneration, planner/search/save or retry. Successful source/tests do not establish native correction or GUI verdict. Stop at captured verification for operator configuration disposition; accepted historicalsetup not re-requested. Then separately freeze reviewedBase/guarded automaticHome advisor proposal, per-tooth/trajectory measurements and FDI34 completepathsearch under fixedconstraints/opening<=46mm. Fullacceptance/highrate remainOPEN; finitefailure no impossibilityproof; DCPcaps/strictFAILED/noautomaticRunB retained.


2026-10-11T14:50:46.540237+00:00 S6-ADVISOR-GUI-01 graph refresh after0cc888b: timeout45 graphify update . --no-cluster (overlayroot) exit124; no completion marker, graph refresh unverified. PDF extraction warning for missingpypdf is retained but not established as timeout cause; no dependencyinstall/retry. Log /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-BASE-STAGING-20261011T144128Z/evidence/graph-refresh.log. Sourcecheckout remainsclean0cc888b, package finalcheckPASS; nativeverification still pending exactapproval.


2026-10-11T15:06:55.190969+00:00 S6-ADVISOR-GUI-01 operator process correction: Tarun objects to slow, fragmented implementation, ambiguous updates and repeated approval requests for parent-owned test mistakes. Adopt session rules in AGENTIC_VERIFICATION_PROTOCOL latest section: autonomous routine repairs/checks; one bounded campaign plan and meaningful operator decisions; distinguish test setup error/product defect/expected configuration; reuse approval within actual scope/budget, retain existing caps/acceptance guards. No new runtime authorized. Confirmed communication: brief Result → failure/fix owner → next action → user input only if needed. Parent will prepare coherent Base→automaticHome→advisor/FDI34 campaign; current isolated native verification remains unexecuted, no repeat approval request now.


2026-10-11T15:16:01.791451+00:00 S6-ADVISOR-GUI-01 Tarun explicitly asks about integrating autoHome into advisor while continuing Base→Home→advisor→FDI34. Clarification: implemented missingHome fix action invokes existing automatic draft owner; it is entry-point integration only. Existing HomeRevalidator revalidates unchanged saved joints; current consent does not cover generation/acceptance of different joints. Full configuration-proposal integration remains pending: attributed generatedHome evidence and explicit draft/pause/review/resume, task reconfirmation and cancellation/restoration semantics. Parent planning snapshot /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-INTEGRATED-PLAN-20261011T151601Z/PLAN.md identifies existingcommands suitable/unsuitable, source/no-runtime limits and ordered campaign. No standalone Home bypass, silent acceptance, autoRunB or extra runtime authority. Current user authorizes preparation/implementation; next runtime decision belongs to one coherent bounded plan.


2026-10-11T15:28:49.970190+00:00 S6-ADVISOR-GUI-01 Tarun replies Approved to integrated autoHome/advisor plan. Implementation/preparation proceeds; the plan snapshot has no frozen native command/resource budget, so no runtime launched. Bounded T3 LunaMAX advisor-autohome-proposal-evidence-20261011-r1 implements attributed initial draft/evidence only, scoped manual/advisorgui/newpureproposal/tests, no service/consent/runtime/docs. Parent implements opt-in disconnected setup session using existing driver, preserving default clean capture and default connected-session flow. Requires current staged Base checkpoint before serving, does not accept/connect/generateHome automatically; opt-in stop_on_error prevents later queued command execution.107focusedhostPASS prior stricter standalone-option preflight; finalcheck running. No trial/Home identity relaxation. Planning question sent: newHome review between batches (recommended preserved restoration invariants) versus midtrial pause/review/resume; independent work continues pending preference. All dirtydocs/source edits preserved; no new runtime or acceptedHome claim. Evidence /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-INTEGRATED-PLAN-20261011T151601Z/evidence.

### 11 October — advisor automatic Home integration source checkpoint
S6-ADVISOR-GUI-01 remains open. Source6c3c0da implements attributed initial drafts and replacement Home review BETWEEN restored batches, with pending-review/restoration guards and hard generated-Home acceptance/Task-reconfirmation gate before a fresh session.194 affected host checks passed. Base native confirmation, target-specific generated draft effectiveness and FDI34 full route are still pending; accepted partial-reload baseline and global strictFAILED boundary unchanged. Next exact session [PROPOSAL.md](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-INTEGRATED-NATIVE-20261011T154531Z/PROPOSAL.md), manifest4d4082ace9fbf9d5190d24b7412653e5c04bb9942b1bb038ba3ad16584c1c5a7: one20min private recorded session, explicit current Base verdict before AcceptBase/Connect/advisorAutoHome, stop Home verdict; no Home motion/acceptance/save. Prepared only, execution decision pending.

11Oct S6-ADVISOR-GUI-01 native integration update: first one-launch session stopped after Import because the runner captured before its navigation-queued Base staging timer; no Connect/Home/planner. CleanupPASS. Testing-only timing correction89b4ec5/97hostPASS; native effectiveness pending. [Corrected continuation](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-INTEGRATED-NATIVE-CONTINUE-20261011T155910Z/PROPOSAL.md) prepared/not approved/not launched; Base verdict → Connect/advisor draft → Home verdict remain next. No new task, DCP replay or cap reset.

11Oct S6-ADVISOR-GUI-01: corrected89b4ec5 native Base draft current/staged identity gap resolved; Tarun accepted exact Base configuration. Session expired at20min review wait, cleanupPASS, no Connect/Home attempted. [Remaining Home proposal continuation](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-HOME-PROPOSAL-CONTINUE-20261011T162614Z/PROPOSAL.md) preserves exact Base verdict with equality refusal guard; one native-launch decision pending, no automatic retry. FullFDI34 and native advisorHome remain open.

11Oct S6-ADVISOR-GUI-01: Base exact match/accepted verdict preserved; remaining native command stopped before AcceptBase because run-local click lacked scroll-to-visible. CleanupPASS; Connect/autoHome untested. Parent repaired command/visibility fixture, checksPASS; [corrected continuation](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-HOME-VISIBLE-CONTINUE-20261011T172437Z/PROPOSAL.md) prepared/not launched; one-runtime-launch decision pending. No product guard changes or new task.

11Oct21UTC S6-ADVISOR-GUI-01: production Base acceptance verified after exact retained verdict. Connect fails because retained move_group373 died(-9); launch348alive is insufficient readiness. Native autoHome/fullFDI34 not reached. Modal unanswered; reconciledowned cleanup/postflightPASS, lock released. Read-only planner-liveness preflight now refuses this degraded stack before GUI launch. Stack recovery/resource change requires concrete bounded plan; no restart/retry performed. Evidence HOME-RESUME-20261011T211240Z/evidence/resolved-result.json.


11Oct S6-ADVISOR-GUI-01: kernel confirms global OOM killed retained planner on10Oct17:16:36Z; Base accepted, nativeHome/fullFDI34 NOT_RUN. Prepared bounded missing-planner-only recovery+service-first GUI/Home proposal at /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-PLANNER-RECOVERY-20261011T212230Z/PROPOSAL.md; readonly/source/provenance checks PASS, not executed. Preserve retained processes; one new-resource execution decision pending. Memory-exhaustion root cause unproven.


11Oct S6-ADVISOR-GUI-01: approved missing-planner recovery PASS services3/3; currentBase accepted. RealConnectsceneidentity guard rejects34/34objects with target/non-target IDs swapped for two teeth; nativeHome NOT_RUN. ExactownedGUI/plannercleanupPASS, retained5/5unchanged, no activeruntime. Evidence /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-PLANNER-RECOVERY-20261011T212230Z/evidence/resolved-result.json. One LunaMAX readonlyreview traces cause; no retry/newruntime requested, GUIverdictPENDING, Home/FDI34OPEN.


11Oct S6-ADVISOR-GUI-01: read-only review complete. Confirmed cached ordinary-heartbeat scene-readback ambiguity corrected with matched read-only state_query at474f1d8,125hostPASS; exact collision/identity/policy guards preserved, no remote objects removed. Native pending, prepared single combined fresh-readback/Home proposal /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-SCENE-READBACK-NATIVE-20261011T214310Z/PROPOSAL.md; no launch. Base nativeaccepted, autoHome native/fullFDI34 stillOPEN.


2026-10-11T21:50:23.264778+00:00 S6-ADVISOR-GUI-01: Tarun explicitly APPROVES frozen SCENE-READBACK-NATIVE-20261011T214310Z combinedrun, requestsnewthreadhandoff andshorter/fewerapprovalupdates. Both exactmanifestapprovalmarkers recorded; no runtime started. SoleSolMEDIUM→newSolMEDIUM/LunaMAXboundedpolicyhandoff in /home/tarun/dentobot/HANDOFF.md finalsection; successorcontinuesapprovedtest WITHOUT reasking. Oldparentstopsafterdispatch.


### 12 October IST / 11 October UTC — S6-ADVISOR-GUI-01 approved fresh-readback run stopped

Tarun's carried approval executed once on474f1d8: missing-planner recovery services3/3 PASS, exact live Base equality and carried verdict PASS, production Base acceptance observed. Connect collision-scene acknowledgement FAILED: "No correlated manual-joint response arrived before timeout." AutoHome/Home acceptance/Plan/Apply/motion/save NOT_RUN. Modal captured unanswered. Exact owned Slicer stop allowed wrapper recorder/display cleanup; GUI raw143 is cleanup stop, not causal error. GUI/planner cleanupPASS; post-cleanup retained5/5 exact, host/containerSlicer0/0 and both locks free. No retry, retained-stack mutation, object deletion, rebuild, DCP replay/cap reset or publication. Evidence [/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-SCENE-READBACK-NATIVE-20261011T214310Z/evidence/resolved-result.json](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-SCENE-READBACK-NATIVE-20261011T214310Z/evidence/resolved-result.json); actual screenshot gui/evidence/live-after-readback.png. Video1607 decodedframes/283distinct/pixelPASS,87black startupframes; ffmpeg0 but original manifestpartial/143 remains unaccepted as complete-run capture. Host ffmpeg absent; existing container decoder used.

Parent reconciled one completed readonly LunaMAX review: reject its incorrect readbackPASS and source/build-drift claims. Current guard source SHA256c296201c exactly matches original build-source receipt; Git474f1d8 is a different identity type, no rebuild justified. Native code supportsstate_query; timeout alone cannot distinguish no delivery/no publish/parse or correlation rejection. Raw request/status payloads are missing because unanswered modal blocked command-result write. RootcauseUNKNOWN; transient DDS interface discovery before immediate single publish is only a hypothesis. Parent-owned next evidence design is bounded raw read-only query/status correlation capture; no additional native run follows automatically. Source125hostPASS remains scoped, native effectivenessFAILED/OPEN, Home/fullFDI34OPEN, fixedopening<=46mm/trajectory/collision/productionacceptanceguards remain. Detailed parent-static-assessment.json retains review correction.
OPEN-QUESTION [S6-ADVISOR-GUI-01] (2026-10-12): Why did fresh native state_query yield no matching response? Source/build hash matches; capture raw request/status plus publisher/subscriber discovery timing to distinguish delivery, publication, parsing and exact-correlation refusal. Evidence SCENE-READBACK-NATIVE-20261011T214310Z/evidence/parent-static-assessment.json.


### 12 October IST — S6-ADVISOR-GUI-01 raw query diagnosis approved and executed

Operator: Tarun replied "Approved" to raw request/reply diagnosis after the stopped GUI scene-readback run. Scope: one read-only state_query, existing retained guard/domain73/SUBNET/container, no Slicer, missing planner replacement, build, case change, Home acceptance or motion. Root [/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-RAW-QUERY-20261011T220150Z](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-RAW-QUERY-20261011T220150Z); PLAN.md/approval.json and frozen input scripts preserve exact commands.

Implementation/diagnostic setup: query.py first stopped before publishing because the diagnostic's added endpoint-name assertion treated DDS `_NODE_NAME_UNKNOWN_` as foreign. publish_count0/cleanupPASS, original preserved. Passive5s endpoint inspection confirmed manual command subscriber/status publisher exist but native graph names remain unknown; ROS CLI short discovery returned unknown topics. Parent corrected only run-owned query02.py: wait for passive state, exactly2 command subscribers (native+own capture) and1 native status publisher, reject other resolved names, preserve all production guards. No query was consumed by that prepublish harness refusal.

Actual native evidence: exactly1state_query published after7.755s endpoint discovery; request017f98c0-4a4d-459b-b301-c695de748d17/session0d538c7f-8582-400c-8feb-298686fd59d2. Diagnostic subscriber observed request, but this does not prove native callback delivery. No raw native manual status in5s; queryexit1. Existing ordinary heartbeat continues with exactly identical cached payload. Accepted and monitored J1-J5 before/after are exactly unchanged; echoed old accepted joints are diagnostic input ONLY and confer no FDI34Home authority. Current/source native guard supports state_query, source/binary provenance unchanged. Raw-replies.json is empty, so production reply parser has no payload to assess.

Assessment: timeout persists with established endpoints/long-lived client, making Python parser-only and initial-discovery-only explanations insufficient. Native request delivery/response publication or callback path remains UNKNOWN; FastDDS transport and native callback are hypotheses, not established defects. Guard thread wait-channel snapshot alone proves neither deadlock nor fault. No speculative rebuild/timeout increase/policy relaxation/retained process mutation. Native timeout causal history1GUI+1raw query=2; zero-publish diagnostic setup refusal remains separate; no caps reset.

Final ownership: retained5/5 exact, Slicerhost/container0/0, no live planner, querynode destroyed, both locks free, cleanupPASS. Evidence [resolved-result.json](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-RAW-QUERY-20261011T220150Z/evidence/resolved-result.json), phase02/request.json/raw-deliveries.json/raw-replies.json/discovery.json/passive-status.json/result.json; original errors retained. AutoHome/fullFDI34 remainNOT_RUN/OPEN. Smallest next distinction is a single UDP-only diagnostic-client query to discriminate shared-memory delivery; replacing/instrumenting the retained native guard is a separate material resource decision. Neither next action executed. No GUI retry, DCP replay, hardware/motion/save or publication.
OPEN-QUESTION [S6-ADVISOR-GUI-01] (2026-10-12): Does established-endpoint manual state_query fail in FastDDS transport or native callback/response processing? One raw query produced no manual reply while ordinary heartbeat/joints persisted; start with phase02/discovery.json/raw-deliveries.json/raw-replies.json and isolate diagnostic-client transport before any retained-guard change.


### 12 October IST — S6-ADVISOR-GUI-01 actionable transport recovery

Operator: "Plan to resolve? Dont just stop here" directs continued diagnosis/recovery preparation. Distinct third bounded diagnostic changed only owned rclpy client transport to UDPv4 against unchanged retained guard. Exactly1query, reply0.217241s; productionparserPASS/all7correlationfieldsTRUE, guardstaticaccepted,34objects and exactaccepted/monitored joints unchanged. NoSHMclientthreads/defaultprofile, cleanupPASS. Evidence /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-UDP-QUERY-20261011T220816Z/evidence/{result.json,raw-replies.json,client-transport.json}. Original defaulttransport2timeouts retained; this third isPASS, not reset/newdefaulttimeoutbudget. Nativecallback is demonstrably capable of responding on this path; shared-memory/defaulttransport mechanism remains unproven. No native/source/guardpolicy defect or Home/GUIpass claim. OfficialFastDDS2.14.6 env_vars supports ownedclientUDPv4, localguard uses sameversion.

Concrete recovery [/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-UDP-HOME-20261011T221005Z/PROPOSAL.md](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-UDP-HOME-20261011T221005Z/PROPOSAL.md) frozen/PREPAREDONLY. One missingplanner-only/servicefirst+recordedSlicer continuation, same474f1d8/child06e3218c/Basecheckpointd7448fd8/ASTparity/nativebinary. Only ownedSlicer UDPv4/rmwfastrtps_cpp environment and launcher childenv guard differ; conditional actioncommand byte-identical. Inputdelta review, syntax, provenancepositive+6negative and freshreadonly retained/hash/noSlicer/noplannerPASS; locksfree. Preparation ordering error (outermanifest beforeGUIcopy) preserved and repaired beforefreeze, no runtime. Manifests recovery1d0f8635ff6185e19ccf3c57c2615dab913f764bda9cb66e72ae005089832f33, GUI5fab628516cfe9c1dda34b791b118453bcad0c457f46550b479c9532b01aaae3. Noapproval/startmarker; prior consumedcombinedapproval doesnot authorize newGUIlaunch. Final material decision is this oneadditionalrecordedGUI/replacementplanner resource budget, no routinefix/Base reapproval. Stopfirstfailure/Homeproposal; noHomeaccept/Plan/Apply/motion/save/RunB/hardware/publication, fixedtrajectory/collision/opening<=46mm. Fulladvisor/FDI34planning/infeasibility remainsOPEN; finitefailure notproof.
OPEN-QUESTION-CLOSED [S6-ADVISOR-GUI-01] (2026-10-12): Is the unchanged nativeguard incapable of publishing matchingmanualqueryresponses? -> No: UDP-only client received valid exactcorrelatedresponse in0.217s; defaulttransportpath is implicated, exactdeliveryfailure mechanism remainsunknown.


### 12 October IST — UDP GUI result and read-only discovery source correction (S6-ADVISOR-GUI-01)

Operator: Tarun replied “Approved” to the frozen UDP-HOME continuation. The exact manifests were approved at root and GUI, then executed once. Services3/3, exact Base equality and production Base acceptance passed. The owned Slicer environment was UDPv4/rmw_fastrtps_cpp, with no SHM threads. Connect still failed “No correlated manual-joint response arrived before timeout.” Auto Home, Home acceptance, Plan/Apply, motion and save were not reached. The error modal was captured unanswered at [/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-UDP-HOME-20261011T221005Z/gui/evidence/live-first-check.png](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-UDP-HOME-20261011T221005Z/gui/evidence/live-first-check.png).

Exact owned Slicer termination allowed the wrapper to finalize recorder/display cleanup; owned planner STOP followed GUI cleanup. Both cleanup results pass, retained5/5 identities remain exact, host/container Slicer counts are0/0, planner is absent, both locks are free. Raw Slicer/recorder exit143 is the failure-stop cleanup consequence; resolved causal result is [/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-UDP-HOME-20261011T221005Z/evidence/resolved-result.json](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-UDP-HOME-20261011T221005Z/evidence/resolved-result.json). Video1405 decodedframes/214 distinct,77 black startupframes, pixel sanityPASS, decoder/ffmpeg0 and hash match; original manifest remainspartial, not complete-run acceptance. Three timeout failures are retained; no fourth native retry occurred.

Source finding: SlicerROS2 PublisherNativeInternals.h:185 emits no message at zero matched subscribers and returns0; PublisherMacros.h:51 forwards that count. The bridge ignored0 and immediately marked the transient request submitted. This is a confirmed source defect, but its causal role in the last GUI failure is unproven because that runtime did not retain Publish return values. The earlier long-lived UDP raw-query PASS0.217s proves the unchanged guard can respond; it does not prove GUI recovery or a specific SHM fault.

Parent correction committed locally as5ed8b386855d944045e06b8d45e163df31cc7684, only DENTOROS2Bridge.py and test_ros2_bridge.py. Read-only state_query waits/retries only a definite integer-zero/no-send result, with the same immutable payload inside the existing total deadline. Positive, ambiguous or exceptional sends are never replayed. Jog remains single-call with its original post-Publish acknowledgement timing/uncertainty. Exact request/session/policy/positions/operation/query_only checks and all collision/acceptance guards remain. Success/failure diagnostics capture IDs, submitted flag and zero-subscriber call count. Final130 affected host testsPASS0.62s, including real API zero-send modeling, eventual discovery, unsent timeout, no replay after positive/ambiguous send, jog no-retry and deadline semantics. One read-only LunaMAX review found no substantive defect and retained the native-causality caution. No C++/native binary changed or build performed; no push. Intentional dirty AGENTS edit preserved. Evidence [/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-QUERY-DISCOVERY-FIX-20261011T222125Z/evidence/parent-review.json](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-QUERY-DISCOVERY-FIX-20261011T222125Z/evidence/parent-review.json).

Prepared revised package [/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-DISCOVERY-HOME-20261011T222700Z/PROPOSAL.md](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-DISCOVERY-HOME-20261011T222700Z/PROPOSAL.md), no approval or start marker. Source5ed8b38 is clean in pinned checkout DentoBot-visible-5ed8b386855d; initial mistyped new worktree suffix was corrected before freeze, actual Git admin derived after move and container identity verified. Frozen AST/source comparison preserves all nodes outside declared query dependencies and all other production files; Base facade/manual widget/placement bytes are identical to reviewed89b4ec5. The receipt does not falsely claim the old broad non-scene equality: the scoped guard requires exact query dependency list plus protected Base equality, and runtime exact live clean_setup equality remains mandatory. No new Base question/verdict. Provenance positive+6negative, checkpoint2positive+8refusal, command1positive+3refusal, Base-parity1positive+6refusal, syntax and fresh ownership/hash checksPASS; locks free. One explicit source-corrected verification beyond the three-failure stop is the remaining material decision. No automatic retry or cap reset.

Overlay graph refresh was bounded20s and exited124 without a completion marker; remains unverified. Added **/engineer-owned/** to graph metadata exclusions before scan, preserving prior config receipt; no engineer-owned artifact read/edited. No graph rebuild success is claimed. Advisor AutoHome/full FDI34 planning or defensible infeasibility remain OPEN; source tests do not confer runtime/operator acceptance. Fixed trajectory/collision/opening<=46mm and review between restored batches remain.
OPEN-QUESTION [S6-ADVISOR-GUI-01] (2026-10-12): Does correcting the definite-zero-send discovery path resolve the Slicer query timeout? Source defect and130 host checks are established; inspect the revised run's query submitted/zero-publish logs and correlated world evidence, only after the specific three-failure exception is approved.


### 12 October IST — S6-ADVISOR-GUI-01 discovery correction native result; retained aliases identified

Operator: after “Dentostyle reset”, Tarun replied “Approved” to the revised5ed8b38verification and ONE exception beyond3retainedtimeoutfailures. Exactroot/GUIapprovalmarkers bind bothfrozenmanifests, preserve count history and authorize no capreset. One combinedrun executed: missingplanner32342/start34777637services3/3PASS, recordedSlicer, exactliveBaseequality/ASTscope carriedexistingverdict, productionBaseaccepted. NativeConnect read-onlyquery now returned currentworldevidence; no correlated-querytimeout. Queryreply capability at this source/runtime isRuntimeVerified, notfullsceneack/Home/operatoracceptance.

Firstfailure changed to exactsceneidentity: expected34, observed36, unexpectedIDs dentobot_target_tooth_2.25.136609116074707562447255670692958970673 and dentobot_tooth_2.25.231954978512953535286616690100905882826_02eb03d7. Strictguard refused; no AutoHome/Homeaccept/Plan/Apply/motion/save. Screenshot [/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-DISCOVERY-HOME-20261011T222700Z/gui/evidence/live-first-check.png](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-DISCOVERY-HOME-20261011T222700Z/gui/evidence/live-first-check.png) capturedunansweredmodal. CurrentqueryIDs/rawreply were notretained in commandresult becausemodalblockedcompletion; do notinventthem or implyfullquerylogproof. Actual36-objectidentityerror proves matchedreadback path progressed; timeoutnativeeffectiveness nowdemonstratedatthisscope.

OwnedSlicer-onlystop letwrapperfinalizerecorder/display, thenrootSTOPendedplanner. GUI/plannercleanupPASS, retained5/5exact, Slicerhost/container0/0, noplanner, locksfree. Raw143iscleanupstopconsequence, causalfailureis36vs34sceneidentity. Evidence [/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-DISCOVERY-HOME-20261011T222700Z/evidence/resolved-result.json](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-DISCOVERY-HOME-20261011T222700Z/evidence/resolved-result.json). Video2171decodedframes/199distinct/85blackstartupframes, pixelPASS, ffmpeg0/hashmatch; originalmanifestpartial remainsnotcomplete-runacceptance.

Read-onlytrace: bothunexpectedIDs exactlymatchrecords in earlierUDPrawsnapshot (34objects, sourcehashretained in resolved-result). Productionlogic_robot.py:step6TargetCollisionObjectName and logic_robot_scene_sync.py:1295–1304 derive currentoppositerolecounterparts: dentobot_tooth_2.25.136609116074707562447255670692958970673_62555506 and dentobot_target_tooth_2.25.231954978512953535286616690100905882826. Retainedoldaliases plusnewcorrectroles explainobserved36. Allothercurrentgeometry stillneedsfullack; naming/IDevidence alone notshape/collisionacceptance. No remoteobjectsremoved.

Parentprepared [/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-ALIAS-CLEANUP-20261011T225118Z/PROPOSAL.md](/home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-ALIAS-CLEANUP-20261011T225118Z/PROPOSAL.md): ONE exact2aliasREMOVEtransaction in ownedUDPclient, existingguard/domain/container, noplan/Slicer/build/retainedrestart. Beforedeletefreshmatchedquerymusthaveexact36IDs andexactfrozen2aliasrecords; after2REMOVEpublishesthenfreshquerymusthaveexact34IDs, allremainingrecords/acceptedjoints/policyfingerprintunchanged. Queryonlybefore/after, firstfailurestop/noautoretry/partialdeleteevidencerequired. Gatefixture2positive+8refusalPASS, syntaxPASS, exactmanifestapprovalrequired. FROZEN/PREPAREDONLY; NOapproval/runtime/removal. CompletedGUIapprovalforbidsremoteobjectdeletion, so thisspecificscenechangeisnextmaterialdecision; no repeatedroutine/Basequestion. FullGUIaudit/AutoHome stillpendingaftercleanup.
OPEN-QUESTION-CLOSED [S6-ADVISOR-GUI-01] (2026-10-12): Does correcting definite-zero-send discovery advance Slicer query past timeout? -> Yes at5ed8b38nativeConnect: strictsceneauditreported36observedIDs, nottimeout; exactreadbackackfailsseparatelyon2retainedaliases. Screenshot andresolvedresult linkedabove.
OPEN-QUESTION [S6-ADVISOR-GUI-01] (2026-10-12): Will removal of exactly2snapshot-matched retainedrolealiases permit the fullcurrent34-objectsceneaudit and AutoHome? Preparedbefore/afteridentity/geometry/joints/policygates refuseunknownstate; removalrequiresmaterialapproval, thenfullGUIaudit remainsnecessary. No feasibilityclaim.


### 12 October IST — approved alias cleanup and native Auto Home checkpoint
Tarun explicitly approves removal and subsequent runtime, then authorizes routine implementation/testing through Advisor Home integration success. Existing Home acceptance/motion/Plan/Apply/save/hardware/publication gates remain separate. Sole parent owns source/runtime/records.
Exact two stale role aliases removed in ALIAS-CLEANUP-20261011T225118Z/phase03: fresh exact2-to-empty readback, accepted joints/policy unchanged, cleanupPASS. Two preceding pre-delete refusals preserved: GUI teardown had removed its current34, leaving2; production parser tuple normalization then required frozen arrays normalized identically. No other objects deleted.
HOME-AFTER-ALIASES-20261011T225757Z Connect passed; run-owned driver failed scrolling Sync because it remained in Placement tab. No AutoHome invocation. Parent fixed driver to select Scene tab; fixture1positive/3refusal passed.
HOME-SCENE-TAB-20261011T225949Z at5ed8b38: services3/3, exact acceptedBase equality, productionBase acceptance, Connect/Sync and exact34-object presence/geometry acknowledgement PASS. Advisor propose_auto_home invoked once; proposal REFUSED auto_task_home_ik_failed: spindle contacts jaw and3teeth. Raw outbox010-connect-propose-home.json retains outcome. No staged/acceptedHome, no motion/Plan/Apply/save. GUI and replacementplanner cleanupPASS; original5owners unchanged. Presence acknowledgement does not grant publication-policy attribution.
Generator currently uses one cached/default IK branch at one midpoint; finite collision refusal is not infeasibility. Next source correction: bounded deterministic alternate IK seeds at EXACT same midpoint/Entry-to-Target axis, retain authoritative static validity/mechanical/FK/identity/scene gates; record every attempt and stop on unknown authority. No opening/Base/trajectory/geometry/policy change. Host verification then one serialized recorded GUI proposal under continuing approval.
OPEN-QUESTION-CLOSED [S6-ADVISOR-GUI-01] (2026-10-12): Will exact stale-alias removal permit the full34-object audit and AutoHome? -> Yes in HOME-SCENE-TAB-20261011T225949Z; generator subsequently refused its single colliding candidate.

12OctIST S6-ADVISOR-GUI-01: source25f64bb adds <=17 same-pose mechanically bounded IK branch hints and explicit native collision-aware/static validity checks, with no geometry/opening/Base/trajectory/policy change. Every attempt retained; unknown authority or stale inputs stop. Existing mechanical/FK/identity/scene gates unchanged.227 affected host checksPASS3.81s; final40focusedPASS0.41s after reviewer assertion improvement. One bounded readonly LunaMAX found no substantive defect; no worker runtime/docs. Local2-filecommit/no push. Frozen HOME-SEEDS-NATIVE-20261011T230851Z carries Tarun's explicit continuing implementation/testing authority. Source/provenance/refusal/fresh ownership preflightsPASS. One replacementplanner services3/3PASS before recordedGUI nowrunning; source-clean pinned25f64bb, actualGitadmin derived, exactacceptedBasecarry onlyonliveequality. No Homeaccept/Plan/Apply/motion/save.

12OctIST S6-ADVISOR-GUI-01: HOME-SEEDS-NATIVE-20261011T230851Z source25f64bb realadvisor17-seed search exhausted:4converged/colliding,13iteration_limit; no draft/infeasibility/acceptance. Exact34-object scene acknowledgementPASS and Base equality retained; GUI+ownedplannercleanupPASS. Detailed attempts and source/output identities preserved in outbox and evidence/resolved-result.json.
Parent read-only canonicalURDF/FK/STL/nativecontact-bound diagnosis (outward-geometry-diagnostic.json) matches canonical dentobot_drill_tcp at0.008373mm. Earlier diagnostic used legacy dentobot_tool_tcp and unavailabletrimesh; no source/native drift conclusion, corrected frame and dependency-free binarySTL read. Conservativecontact AABB separation hints7.09–16.69mm outward. Bounds are candidate hints only, not collision evidence or infeasibility.
Next bounded source correction uses exactlyONE measured outwarddepth hint after midpoint17-seed exhaustion, capped20mm, along existingnegativeDepth direction; no arbitrarygeometryladder/opening/Base/trajectory/policy change. All nativecollision/static/mechanical/FK/currentidentity/source/trajectory guards required. Home remains explicitreviewdraft; no acceptance/motion. Operator continuing implementation/testing authority reused;233affectedhostPASS3.51s, readonly LunaMAX adapterreview pending.

12OctIST S6-ADVISOR-GUI-01 sourcebd26148: measured outward-hint algorithm reviewed readonlyLunaMAX no definite frame/sign/authority defect. Parent closed adaptertestgap: actualtrackedURDF/STL/robot_link_mesh_poses_mm, auditfields,90degBase world-Y/base-X knownanswer-6mm, missingcurrentobjects and visual/collisionoriginmismatch refusals.233affectedchecksPASS plus45finalfocusedPASS; scopedwhitespacePASS, local2-filecommit/no push. Frozen HOME-OUTWARD-NATIVE-20261011T231904Z explicitlycarriesongoingTarunapproval; currentcase/nativeguard/Baseprotectedsource+bridgeAST frozen. Freshownership/packagePASS, missingplanner services3/3PASS; recordedGUIserving, exactBaseclean_setupMATCH acceptedverdictcarried, productionConnect→audit→advisorAutoHomeonce nowrunning. Max17midpoint+17ONEderivedoutwarddepth<=20mm, no arbitrarygeometrysweep; allguards strict. Stopfirstsubstantivefailure/proposalverdict; noHomeaccept/Plan/Apply/motion/save/RunB/hardware/mainpublication.

12OctIST S6-ADVISOR-GUI-01 HOME-OUTWARD-NATIVE-20261011T231904Z atbd26148: real one16.690704mm outwardhint adapter exercised;4IKsolutions converge and clear originaljaw/3teeth contacts but all4 collide fixed dentobot_mouth_barrier_lip_slab,13other seeds miss tolerance. Full34scenePASS, no stage/accept/motion/infeasibility. GUI+ownedplannercleanupPASS, originalownersunchanged. Outbox/evidence auto-home-proposal andresolved-result preserve all34midpoint/outward attempts.
Correction8adeb9d: contact-only hint omittedfixedbarrierfrontplane. Now include whole spindle's minimum signed distance to existinglipfront and its outward speed; derive ONE exterior pose, no ladder or changedbarrier. Proposal-only hintcap20→40mm accommodates fixedbarrier; Homejointmechanical/static/FK/identity/source/scene authority unchanged, no clinicalacceptance. Pureknownanswers includeobliqueplaneprojection/tangentrefusal/nonfinite geometry.235affectedhostPASS4.36s, staticdiffPASS. Priornativefailurehistory retained, no capreset; explicitcontinuingTarun implementation/testing-throughsuccessauthority reused for routine source-corrected same-resource run; not per-command/repeatedBaseapproval.
Frozen HOME-BARRIER-NATIVE-20261011T232542Z source8adeb9d, cleanpin/exactGitadmin; source/provenance/freshownershipPASS, replacementplanner services3/3PASS before recordedGUI. Onlynativepending; no Homeaccept/Plan/Apply/motion/save/RunB/hardware/mainpublication. Stopfirstsubstantivefailure/draftverdict, cleanupownedonly.
OPEN-QUESTION [S6-ADVISOR-GUI-01] (2026-10-12): Will the fixedlipfront-aware single exterior Home hint yield a static-valid reviewed draft? Contact-only16.69mm Home clears jaw/teeth butlipcollision remains; inspect8adeb9d proposal and allguards before feasibility/acceptance claims.

12OctIST S6-ADVISOR-GUI-01 HOME-BARRIER-NATIVE-20261011T232542Z at8adeb9d: PRODUCT NATIVE SUCCESS, realadvisor outcome statusstaged/successtrue/stagedtrue, no Home acceptance or motion. ONE contact+fixedlipfront hint38.0659369mmoutward, selectedalternateIKseed9 (10outwardattempts after17midpoint), authoritativeStaticValidity/collisionAwareValidated true, fullscene34PASS, independentFK0.012864mm/0.001413deg, mechanical/identity/source guardsPASS. PriorrawcommandFAIL retained: run-owned driver readUTF8 proposal usingdefaultASCII, UnicodeDecodeError at success Entry→Target message; this is testscriptfailure, not generator refusal. Productartifact archived evidence/auto-home-proposal.json and resolved-result.json preserves both outcomes. GUI+replacementplannercleanupPASS.
Parent owns routineUTF8repair: new HOME-UTF8-FINAL-20261011T232947Z sameclean8adeb9d/case/Base/geometry/native source; only command readsartifact encodingUTF8. Discriminatingfixture suppliesUnicode successmessage underforcedASCIIdefault, positive+3preactionrefusalsPASS; package/source/freshownershipPASS. Existing235productchecks reused unchanged. ExplicitcontinuingTarunauthority carriesone finalrecorded flow→draftcapture→productionDisconnect→ownedcleanup, no acceptance/motion/save. Service3/3PASS before GUI currentlystarting; no extra Base decision. Highsuccessrate/fullFDI34 notclaimed; Homeproposaloperatorverdict pendingactualcapture.
OPEN-QUESTION-CLOSED [S6-ADVISOR-GUI-01] (2026-10-12): Will fixedlipfront-aware exterior Home hint yield static-validdraft? -> Yes at8adeb9d: native realadvisor STAGED/VALID38.0659mmoutward, exactscene/mechanical/FK/currentidentity/source gatesPASS. Fullrecordedflow stillneedsUTF8driverrepair; operatoracceptance distinct.

12OctIST S6-ADVISOR-GUI-01 operator supersession: Tarun proposes currentcreatedmouthbarriercentre, dynamicwithbarrieradjustments, asbetter/easierHome thanincisormidpoint becauseanatomy/openingvaries. Parent implements usableaperturecentre at lipslabmiddepth: meanfinal4openingvertices+0.5currentthickness*outwardnormal. Incisorbitingmidpoint retainedreference, no oldanchoracceptance. Currentbarriervertices/normal/thickness/summary capturedand rechecked so anyadjustment invalidatesdraft. Barrier-disabled/invalidgeometry refuses, no silentincisor fallback. Fixedtrajectory, opening<=46, acceptedBase andproductionstatic/mechanical/FK/identity/scene/draftacceptance guards unchanged.
Sourcebfb6b98 UItooltip+generator+tests,329affectedhostPASS7.24s; local3filecommit/no push, userdirtyAGENTSpreserved. Prior8adeb9d draftvalid/nativeSTAGED38.0659mmoutward andUTF8commandPASS; finalDisconnecttestdriverfailedbecause6.1controlhiddenin6.2. OwnedcleanupPASS, no motion/acceptance; parentcorrectedrun-drivernavigationbeforeDisconnect. No falseoverallflowPASS.
Frozen BARRIER-CENTER-NATIVE-20261011T233622Z explicitlycarriessupersedinganchorrequest+continuingtestingauthority. Freshsource/provenance/ownershipPASS, services3/3 beforeGUI currentlyloading. OneadvisorAutoHomeproposal thenstop, noHomeaccept/Plan/Apply/motion/save/hardware/RunB/publication. FullFDI34 remainsdependent onvalidreviewedHome; highsuccessrate unmeasured.

### 12 October IST — dynamic barrier-centre Auto Home native integration PASS
Sourcebfb6b98ebf7885ba8b576520a77c92d8cbe52498, BARRIER-CENTER-NATIVE-20261011T233622Z realadvisor action+export+staging PASS40.133s, productionDisconnect/stopPASS5.123s, GUIwrapper0/plannerwrapper0/cleanupbothPASS. ExactacceptedBaseequality and34objectsceneauditPASS; original5retainedownersunchanged/Slicer0/0. No Homeaccept/Plan/Apply/motion/save.
Currentbarrieropeningcentre worldRASmm[-91.08324408357889,-32.323761894908586,40.02238522795062], slabmiddepth. Incisorreference[-91.4158763885498,-40.442108154296875,43.235246658325195] retained. Draft succeeds FIRST nativeIKseed(index0), depth0, nooutwardfallback. Authoritativestaticcollisionvalidity/mechanical/source/currentbarrieridentity/scenePASS; independentFKresidual0.000688308mm/axis0deg. DisplaydraftJ1-7.16deg/J229.70mm/J31.24deg/J438.45mm/J528.73deg. Opening40.06mm/fixedtrajectory/Base/policy unchanged.329affectedhostchecksPASS; dynamicvertices/slabchangeknownanswers/stalerejection tested. SinglecasePASS doesnotestablishhighsuccessrate orfullFDI34planning.
Screenshot advisor-auto-home-draft-review-ui.png visuallyinspected: actualnonzeroJ1–J5draftpresent, noacceptedHome. Product/flow summary andproposal in run/evidence/{resolved-result.json,auto-home-proposal.json}. OperatorverdictPENDING; nextrequiredmaterialgate is reviewactualdraft before anyHomeacceptance/motion/FDI34route. No extra routineexecutionapproval asked; continuingauthoritycarried. NewHomebetweenrestoredsearchbatches remains unchanged.


### 12 October IST — S6-ADVISOR-GUI-01 sole-owner hierarchical continuation

Sole coordinator Sol6.1/high on existing repair checkout bfb6b98. Current explicit operator routing supersedes dated instructions: Luna/medium bounded auxiliaries, unique worktree AND branch for each implementation worker, Astra/high adversary reviews at required gates. Requested files have no 12 October hierarchical section; no extra gates invented. Full-access runtime and no exposed named-profile/sandbox selector mean review is behaviorally read-only, not enforced security isolation. Current effective Sol/high supported by runtime metadata/dispatch receipt, whereas catalog option defaults are low/medium and are not actual effort. No new top-level thread or supervisor needed: this is the dispatched continuation.

Saved native proposal/Disconnect/cleanup evidence matches bfb6b98; accepted Base verdict/equality remains settled. Draft at dynamic usable-aperture/slab centre is native static-valid, first seed/depth0; generated Home is not accepted and no motion, Plan/Apply, save or full FDI34 run occurred. Existing host329 success reused unchanged. Finished recording inspection: step6_video_sanity.py exit0 PASS, 1345 decoded/container frames, 1233 content frames, 178 distinct, complete/hashmatch. Original recording remains unchanged. New evidence/video-sanity.json contains full command inputs/results; six samples retained. This is recording quality, not workflow or operator acceptance.

Astra/high round1 /root/astra_home_review_r1 inspecting saved code/evidence; no tests/native launches/source edits by reviewer. Possible replacement-Home acceptance binding defect under investigation; existing Home review gate remains open. No independent code change yet. Routine fixes/testing authorized by retained broad operator approval; Home acceptance/motion/Plan/Apply/save and RunB/hardware/publication remain separate.

Evidence: /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-HIERARCHICAL-REVIEW-20261011T234302Z/REVIEW-STATUS.md. Existing dirty controlled records preserved; no commit/push/Drive.


### S6-ADVISOR-GUI-01 — replacement Home binding source checkpoint, 12 October IST

Sole owner Sol6.1/high retained. Current explicit routing recorded additively in canonical protocol: Luna/medium implementation auxiliary in its unique worktree/branch; two distinct Astra/high review rounds. Native dispatch used explicit supported model/effort overrides, but auxiliary independent effective-config readback was unavailable; do not claim it independently verified. No named adversary profile/sandbox selector; full-access review was behaviorally read-only. Intentional AGENTS.md/Workspace/AGENTS.md SHA hashes and all unrelated dirty controlled docs preserved.

Astra round1 found P1 product defect: generated replacement B could leave old validated Home A saved; confirming A cleared the boolean pending-draft gate and started search with A. Isolated Luna worker reproduced pre-fix prepare() invocation, then patched two scoped files. Parent inspected/refined/integrated. Gate now binds canonical finite exact generated joints, stable branch/Base/trajectory/profile/scene/limits identity and pre-generation saved revision; requires a NEW matching Validated Home, successful current unstaged manual review and matching fresh Task confirmation. Captured binding persists across advisor close/reopen/new session, evidence-write errors and unstaged generator refusals; inconsistent staged outcome fails closed. No geometry/authority/motion owner changed. Local implementation commit d972094; test-only production-record followup commit 2b49251. No push/main/Drive.

Verification: isolated worker final57 host PASS; parent indexed pure.step6_advisor_session_host plus affected proposal tests103 PASS2.02s, changed Python compile/scoped diff PASS. Astra round2 PROCEED_SOURCE_REVIEW, P1 closed at source, no new definite defect in bounded inspection. Parent added its recommended real build/serialize/parse Home record + production task fingerprint check: initial None→revision1 and replacement6→7 refuse stale task, allow fresh task; 1 focused test PASS0.12s. Source production bytes unchanged after review; broader103 check reused unchanged. Initial intended red product regression was retained as console excerpt, not a full raw pytest log; two later host fixture/AST namespace failures and fixes retained separately. No native new-gate verification inferred.

Saved native proposal at bfb6b98 remains matched by exact generator/manual/Panel/facade/bridge byte equality. Native draft firstseed/depth0 staticvalid/FK0.000688308mm/axis0deg and proposal+Disconnect/cleanup evidence retained. Completed recording pixel/decode/hash PASS1345frames,1233content,178distinct. Fresh owner inspection original5/5exact, Slicerhost/container0/0. No runtime was launched this turn, no Home accepted/Plan/Apply/motion/save/fullFDI34. Single case never establishes high success or ideal Home. Overlay graph refresh remains unverified with prior timeouts retained.

Operator question pending: accept the actual captured draft and authorize one guarded SIMULATION Home Plan+Apply→Accept&Validate→ConfirmTask after cleared source review; first refusal/changed proposal stop, no dentocase Save. Concrete Home scope in HOME-CONTINUATION.md; executable frozen package still to be prepared before any launch. Separate Home gate is expected setup, not product failure. Current-to-draft start is zero; endpoint static PASS does not prove transition. Original Base verdict/equality remains settled; no repeated Base/runtime routine approval requested. Full advisor/FDI34 trajectory/repeat/positive persistence and broader DCP strictFAILED acceptance remain open under existing backlog IDs. Fixed trajectory/tool/collision/identity/opening<=46, review BETWEEN restored batches, historical caps and retained processes preserved.

Evidence: /home/tarun/dentobot/data/dentobot-runs/2026-10-11/S6-ADVISOR-GUI-01-HIERARCHICAL-REVIEW-20261011T234302Z/REVIEW-STATUS.md; evidence/astra-review-r1.json, astra-review-r2.json, luna-integration.patch, integrated-validation.json, production-record-host.log, native-draft-source-parity.json, video-sanity.json, fresh-owner-inspection.json, commands-and-results.json. Current source 2b49251de5f066a5af5cd4a224174e6f09797d56 on repair/dcp-partial-case-complete-astra-20261011.


### 12 October IST — operator accepts exact Home proposal and authorizes guarded simulation progression

Operator quote: “Accept proposal and authorize guarded simulation Home progression.” This resolves the actual captured barrier-centre draft verdict and authorizes ONE guarded SIMULATION Home Plan+Apply→Accept&Validate→ConfirmTask after Astra source gate. Stop at first refusal or changed proposal, original stack preserved, no dentocase Save. It does not authorize advisor baseline/search/full FDI34 route/RunB/hardware/main/Drive. Routine implementation/package repairs retain existing broad authorization; no duplicate Base or per-command approval.

Parent source2b49251 retains Astra/high R2 sourcecleared/host103+realrecord1PASS; generator/native/Base owners unchanged. Fresh dated package preparation uses exact copied child and exact accepted proposal hash; clean12-character pin/actualGitadmin, fixed nativeguard identities, UDPv4/rmw client, missingplanner only/services3of3 before Slicer/private:98 recorded1200s, exact retained5/noexistingSlicer and cleanup ledgers. New run-local Home command binds exact authorization/source/joints/sourcegeometry/trajectory/currentstart and real production controls. Parent corrected prelaunch modal watchdog to capture-only/neverreject orclose, preserving stop rule; finalhostfixture2positive+13refusalPASS, provenance6negative/checkpoint8negative/connect3negative/syntaxPASS. Native NOT_STARTED; Astra/high R3 finalcommand review pending before execution. Initial UTC-day parent-directory preparation error fixed before worktree/runtime creation, not a product/native failure. No old evidence/caps overwritten.

Frozen package/evidence /home/tarun/dentobot/data/dentobot-runs/2026-10-12/S6-ADVISOR-GUI-01-HOME-PROGRESSION-20261012T000103Z/PROPOSAL.md; exact approved proposal SHA c21d8a70ae609b8450ab63d81b8d8e8dd1d0b66a846123e5ebfd74bd8d0788f2.


### 12 October IST — native Home motion/acceptance PASS; Task confirmation harness stop

Operator had accepted the exact captured barrier-centre Home and authorized ONE guarded SIMULATION Plan+Apply→AcceptValidate→ConfirmTask, firstrefusal/changedproposalstop, originalstack/no dentocasesave. Source2b49251/R2 source gate cleared; newcommand R3 reviewed after parent corrected modal watchdog to capture-only/neverdismiss. Fresh root frozen/all20sources/runner/helpers nativehashes/sourcepin/caseexact, provenance6negative/checkpoint8negative/connect3negative/Home13negative/syntaxPASS. UTC-day directory preparation error fixed before runtime; not productfailure. One missingplanner36938/start35316480 services3/3 beforeprivate:98 recordedGUI. Exact live Base checkpoint equality carries originalacceptedverdict; Connect/sync/full34scene/freshadvisorproposalPASS, exact joints/sourcegeometry/trajectory/stableidentity equal acceptedproposal, seed0/depth0.

Product native Home progression: MoveIt current0→approvedHome planned; all158productionstrictguardwaypoints applied including guarded endpoint snap. PlanApply task_home_draft_applied PASS. Review exactcandidate current/stagedPASS. Production AcceptValidate manual_task_home_review_accepted PASS, saved/livevalidated Home revision1 against34objects; acceptance details accepted=monitored=candidate exactzeroerror. Plan result earlier monitor field retained8.86329e-05SI tolerance gap while accepted exact; later command exactchecks and acceptance readbackzero supersede it without overwritingrawfields. MinimumClearanceMm=1.0 is the production-reported field, not an independently measured separation certificate. SuccessfulHome save is runtime MRML/configuration only; NOdentocaseSave. Optionalmanualsimulationrecord unavailable because assistedlimits not reviewed, but Homeacceptance itself successful; no automaticworkspace/limitsreview inferred.

Firstfailure TESTSCRIPTERROR beforeConfirmTask: _scroll_to_visible found enabledConfirmcontrolhidden. Harness navigated6.3 but remainedManual; Confirmbutton belongsPlanpage. Command020error726.42s and traceback retained; no runtimeguardfailure/newinfeasibility. LateractionsNOTREACHED, no baseline/advisorbatch/fullFDI34. GUIwrapper recordsoverallcommanderror while slicer/recorderexit0/cleanupPASS; ownedplannerrootcleanupPASS. Original5retainedPID/start/cmdexact/Slicerhost/container0/0. No newnativeattempt orpassedDCPchain replay. Finishedrecordingcomplete/hash/pixelPASS12311decodedframes358distinct, fullmetricsretained. Actualapplied-stateUIshows acceptednonzerojoints; no accepted+confirmed screenshot becauseconfirmationneverreached.

Parent owns routinefix: copiedfreshpreparationonlyroot selects existingproduction _show_step63_view(panel,2,0) beforerealConfirm, archivesacceptedHome record first, and adds exactretainedaccepted=monitored=displayed=candidate1e-12 precondition beforePlanApply. This forbidsrepeat158waypointmotion: productionexactalreadyAtDraft no-oponly, otherwiseSTOP. Freshgenerator still mustmatchacceptedproposalexactly; retainedseedcouldproducechangedIK, whichstopsforreviewwithoutthresholdrelaxation. FixtureexecutesproductionnavigationAST andverifiesPlanvisible;2positive+14refusalPASS/modaluntouched, syntax/provenancepositive+6negativePASS. Source/pinnednative/Base/caseunchanged, originalrunimmutable. AstrahighR4 READY_FOR_OPERATOR_APPROVAL no definitecorrectivedefect. New1200s sameownedresource missingplanner→GUIconfirmationcontinuationPREPARED ONLY/noapprovalmarkers/start; explicitone-shotprevioussessionended, sooneadditionalresourcecontinuationdecisionrequired, notrepeatHomeproposal/Baseacceptance orroutinefixapproval. No hardware/RunB/save/publication/Drive.

Originalraw/resolvedevidence /home/tarun/dentobot/data/dentobot-runs/2026-10-12/S6-ADVISOR-GUI-01-HOME-PROGRESSION-20261012T000103Z/evidence/resolved-result.json; correctedconcretepackage /home/tarun/dentobot/data/dentobot-runs/2026-10-12/S6-ADVISOR-GUI-01-HOME-CONFIRM-CONTINUE-20261012T024514Z/PROPOSAL.md; no parallelqueue/taskrename. Existing S6-ADVISOR-GUI-01 backlog remainsOPEN for ConfirmTask/nativeadvisorgate/fullFDI34 and positivepersistence/representativeacceptance.


### 12 October IST — exact no-new-motion confirmation continuation authorized

Operator: “Approve one confirmation continuation with no new motion.” This approves the frozen HOME-CONFIRM-CONTINUE package after Astra/high R4 review, not another motion trial. Exact root and GUI approval markers bind final manifests. Fresh package/provenance and retained-owner/no-existing-Slicer checks passed. One owned missing planner (37492/start36280788) reached all three required services before the recorded GUI started. The command requires current accepted, monitored and displayed joints to equal the approved candidate within1e-12; the production exact already-at-draft branch sends no motion. Any changed candidate/source or retained pose stops before progression. No dentocase save, advisor search, full FDI34 route, RunB, hardware or publication is authorized. Source and native inputs remain unchanged.
Evidence and frozen scope: /home/tarun/dentobot/data/dentobot-runs/2026-10-12/S6-ADVISOR-GUI-01-HOME-CONFIRM-CONTINUE-20261012T024514Z/PROPOSAL.md and evidence/operator-continuation-authorization.json. Runtime result pending; no success inferred.


### 12 October IST — FDI34 Home accepted and Task confirmed; no-new-motion continuation PASS

Tarun explicitly approved “one confirmation continuation with no new motion.” The corrected frozen package at source2b49251 completed the fresh advisor proposal → production no-op Plan + Apply → Review → Accept & Validate → Confirm Task sequence. The exact approved joints, current barrier/incisor source geometry, trajectory and stable source identity matched. Accepted, monitored and displayed pose equalled the draft. Plan + Apply reported alreadyAtDraft=true and appliedWaypointCount=0: it planned and moved nothing. Production Home acceptance saved a Validated revision1 in this fresh copied scene, and the confirmed task existed with no freshness issues. The actual captured Plan-page UI visibly reports one confirmed immutable SIMULATION task with the requested Entry→Target depth.

The preceding authorized session had already proved the zero-pose→approvedHome transition using158strictly guarded waypoints and Home acceptance. Its command stopped before Confirm Task on the parent's wrong-tab test script; that raw failure is preserved. This continuation corrected the Plan-tab selection, retained the exact-pose gate and completed confirmation without repeating motion. The source repository stayed at2b49251; no C++/URDF/native build or production-code change was needed for this run-local repair.

Native commands passed: connect/proposal41.982s, Home progression12.617s, production Disconnect/stop5.35s. GUI and recorder exits0; GUI and owned replacement-planner cleanupPASS; original five PID/start/command identities unchanged; host/container Slicer0/0; owned planner37492 absent. Recording complete/decode/pixel/hashPASS2315frames/223distinct, ffmpeg0. Astra/high R5 inspected saved artifacts and returned ACCEPTED_SCOPED_EVIDENCE, finding no definite blocker to native Home acceptance/current Task confirmation/no-new-motion claims. Reviewer performed no tests, runtime or writes; full-access behavioral read-only and independently unavailable effort readback remain recorded limitations.

Evidence boundaries are explicit. Generic planning_or_motion=true fields are inherited coarse flags, retained unchanged; the actual production alreadyAtDraft/zero-waypoint result establishes no new motion. MinimumClearanceMm=1.0 is production reporting, not an independent separation certificate. Matched request/session state-query object/pose/bounds acknowledgment does not confer trusted publication-policy attribution: trusted=false/readback_correlated=false/attribution_allowed=false remain deliberate. The optional manual simulation recording identity was unavailable because assisted limits were not reviewed; that limits recording evidence without negating successful Home validation. No limits-review or workspace authority is inferred.

No dentocase save, advisor baseline/search, native execution of the new advisor Start gate, full FDI34 route/cycle, RunB, hardware, publication or Drive action occurred. The runtime ended normally, so these artifacts grant no live Home/scene/guard authority. The operator's Home proposal verdict is settled; broader GUI verdict, positive persistence, representative success rate and complete Home→PreEntry→Entry→Target→withdrawal→Home acceptance remain under existing backlog contracts. Single-case success is not a high-success-rate or ideal-Home claim. Review of a new replacement Home BETWEEN restored batches, fixed trajectory/tool/collision/identity constraints, opening<=46, original owners and historical caps remain intact.

Evidence: /home/tarun/dentobot/data/dentobot-runs/2026-10-12/S6-ADVISOR-GUI-01-HOME-CONFIRM-CONTINUE-20261012T024514Z/CHECKPOINT.md; raw gui/session/outbox/{010-connect-propose-home,020-home-progression,999-end-stop}.json; evidence/{resolved-result,astra-native-r5,final-retained-owners,video-sanity}.json; actual screenshot gui/evidence/20261012T025120384890Z-approved-home-accepted-task-confirmed-ui.png. Prior motion/failure evidence remains HOME-PROGRESSION-20261012T000103Z/evidence/resolved-result.json.
