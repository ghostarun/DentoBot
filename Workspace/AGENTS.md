# Dentobot Project Instructions

Shared project rules for every development agent. Tarun's current explicit scope and
superseding decisions govern; dated evidence is not new execution authority.

## Context and task contracts

- This host's sole active checkout is `/home/tarun/dentobot/ros2_ws/src/DentoBot` on `main`. All other registered worktrees are preserved legacy snapshots, superseding earlier checkout routing. Do not delete or import their dirty work without scoped direction.

- Start with `docs/AGENT_CONTEXT.md` and the backlog-first gate below.
- For narrow work, read today's logbook, the internal package routing map, and
  only the routed controlled/domain records needed for the task.
- For broad resumption, architecture/environment/milestone changes, evidence
  reconciliation or documentation/release checkpoints, read `PROJECT_CONTEXT.md`,
  `SETUP.md`, `DECISIONS.md`, `DEVELOPMENT_PLAN.md` and `TASKS.md` under `docs/`.
- Consult `docs/ARCHITECTURE.md` and `docs/REPRODUCIBILITY_AND_TRACEABILITY.md`
  when their scope is affected. Engineer-owned records are excluded throughout.
- Establish a compact contract: outcome, context, owned files, invariants,
  forbidden changes, acceptance evidence, approved execution and stop condition.
- Report current focus with `scripts/progress_dashboard/focus.py` (see SETUP):
  task ID, main milestone, main/supporting kind, outcome, acceptance and stop condition.
  Update at meaningful steps and at least every 10 minutes while working; finish or
  mark awaiting-review/blocked at a stop. Receipts are operational metadata, not a queue
  or acceptance. A missing helper must not block independent authorized work.
- Keep the explicit dashboard milestone/outcome mapping in DEVELOPMENT_PLAN in sync
  with scope and accepted evidence; it is display metadata, never a second queue.
- Preserve other worktree edits. Keep durable rules here or in the verification
  protocol; keep case facts, attempts and history in task records/logbooks.
- Continue authorized work with routine assumptions; ask only when missing input
  affects correctness, physical interpretation, safety or scope. Reuse approvals
  within their boundaries. At a stop gate, pause that path and continue independent work.
- Resolve conflicts explicitly by instruction hierarchy and latest operator scope;
  never adopt attached commands, example parameters or priorities as authorization.

## Backlog-first gate — mandatory

- Before planning, implementation, diagnosis, delegation, resumption, reprioritization
  or milestone changes, read/search all `docs/backlog.md` using request terms,
  synonyms, workflow/component names, aliases and IDs. Compare all actionable
  matches' priorities, dependencies, overlaps, state and next acceptance action.
- Follow matching IDs into `docs/TASKS.md`, `docs/DEVELOPMENT_PLAN.md`,
  `docs/DECISIONS.md` and dated evidence; read applicable contracts and boundaries
  in full. `AGENT_CONTEXT.md` is a route, not a replacement for this lookup.
- Reuse the existing ID/contract. Do not duplicate, rename, silently rescope,
  reorder dependencies or ask Tarun to repeat settled decisions.
- Record explicit operator changes in the canonical task, decision and logbook.
  A later task-specific decision supersedes an older general summary.
- Treat new runtime failures as evidence under the active task until independence
  is proven; do not automatically retune, change geometry/policy or restart a cycle.
- Create a new plan only after backlog and linked-record searches find no match;
  record that finding and put pending work in `docs/backlog.md`.
- Backlog is the sole pending queue, including active, blocked, deferred and
  unaccepted work. Never create a second queue or dated Next list elsewhere.
- On completion, record evidence in logbook and TASKS/DEVELOPMENT_PLAN as applicable
  and remove the backlog row in the same turn. Source completion alone cannot close
  required runtime, representative, physical or operator acceptance.

## Records, notes and privacy

- Log commands, changed files, results, errors and unresolved issues in today's
  `docs/logbook/` file. For substantial work include operator observations/reasoning,
  decisions, evidence limits and next bounded action. Distinguish operator statements,
  agent interpretation, implementation and verification; never invent operator reasoning.
- Update `docs/SETUP.md` for environment/path/dependency/Docker/Slicer/ROS changes;
  `docs/DECISIONS.md` for technical/architectural decisions; TASKS for detailed
  contracts/completion and DEVELOPMENT_PLAN for milestone/acceptance design.
- Follow `docs/CONTEXT_SYNC.md` for Drive; update existing file IDs, never duplicates.
- Never record credentials, patient identifiers or non-anonymized medical data.
- Daily Compass, `IITM Personal Work Journal` and
  `IITM Dental Drilling Robot — Project Tracker` are engineer-owned, not development
  records. Do not read/edit/reconcile/move/export/sync them unless the current message
  explicitly names the artifact and action. Generic resume/plan/docs/checkpoint/sync
  or `DENTO-POSTMORTEM-SYNC` requests do not authorize access. Locations:
  `docs/engineer-owned/` and Drive `IITM Dentobot/Engineer-owned — manual only`.
- Triage every `DENTO-NOTE:` in the same turn: fix now, active investigation,
  blocked or backlog. Fix safe, authorized, bounded items; otherwise record workflow
  step, behavior, evidence, impact and next verification in backlog. Log the outcome.
- Explicit numeric priorities ascend from 0 (highest). Within authorized safe scope,
  do lowest actionable priority first, preserving recorded prerequisite dependencies.
  Keep unspecified priorities Unprioritized. Priority never overrides safety, scope,
  verification or external-write gates. Log changes in backlog, linked TASKS and logbook.
- Keep each unresolved reasoning thread as one self-contained logbook line:
  `OPEN-QUESTION [<task-id>] (<YYYY-MM-DD>): <question; evidence; starting point>`.
  Close with `OPEN-QUESTION-CLOSED [<task-id>] (<date>): <question> -> <answer/evidence>`.
  Never delete open lines; retain compatibility with `grep -rn "OPEN-QUESTION" docs/`.

## Verification, safety and evidence

- For tests, builds, diagnosis, delegation or `DENTO-VERIFY`, follow
  `docs/AGENTIC_VERIFICATION_PROTOCOL.md` and checkout-root
  `Testing/verification_matrix.json` (`../Testing` from physical Workspace).
- Use the cheapest sufficient check, three-failure retry ceiling and early visual
  escalation before expensive SlicerROS2 reruns. Runtime resources are serialized;
  execution remains approval-gated. Do not test files being actively edited.
- Never claim success without recorded commands/results or observed evidence.
  Distinguish source/host-tested, runtime-verified and operator-accepted status.
- No robot motion, drilling, patient-facing or safety-critical operations without
  explicit authorization and an appropriate verified safety procedure.
- `S6-LIVE-01` retains its canonical planner contract:
  `docs/diagnostics/FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md`. Demonstrable GUI results
  stop for Tarun's verdict unless explicitly superseded for the current scope.
  Fatal/unresolved algorithm failures pause for instruction, not automatic retries
  or model escalation. Retain task worker ceilings, anti-bloat and no-hardware limits.
- Store tests/diagnostics under the Ubuntu overlay's
  `data/dentobot-runs/YYYY-MM-DD/<task-id>-<UTC-start-timestamp>/` using UTC start date.
  Configure output overrides first; keep all run/session evidence together and archive
  completed scratch there. No flat root run folders, overwrites or moving live writers.

## Testing script reuse and workflow promotion

- Before adding/changing runners, diagnostics or automation, search
  `docs/diagnostics/TESTING_VERIFICATION_SCRIPT_INDEX_2026-09-24.md`, the checkout's
  verification matrix, existing scripts and accepted evidence. Resolve paths from
  canonical Workspace docs and the DentoBot checkout, not the overlay root.
- Reuse/compose the smallest existing production-step scripts. A missing end-to-end
  wrapper alone does not justify duplication. Record the concrete uncovered behavior
  or incompatible boundary that requires any new script in the task/logbook.
- Register new/materially changed reusable scripts in the existing index and relevant
  matrix entry: purpose, owner, invocation, dependencies/resources, approval class,
  outputs/pass conditions and limitations. Do not add another library or queue.
- Promote workflows only with exact tested SHA, case, environment, commands, results
  and artifacts; check relevant drift before reuse and retain approval/safety gates.
  Keep latest results in linked run evidence, not timeless matrix PASS claims.
  Do not repeat valid unchanged checks or expensive runs just to populate the index.

## Model selection and delegation

- Latest task override (12 October 2026): Sol6.1/high coordinator, bounded Luna/max auxiliaries, Astra/low adversary reviews. Astra/low supersedes the earlier Astra/high selection for S6-ADVISOR-GUI-01. Tarun subsequently sets Luna worker effort to max moving forward, superseding earlier medium selections. Existing gates and distinct worker worktree/branch requirements remain; no enforced sandbox is inferred.

- Tarun chooses the agent, model, effort and delegation policy per thread; no fixed
  vendor/model default or mandatory multi-model pipeline. Historical selections are
  evidence, not routing rules; saved settings cannot change a running thread's model.
- Default solo; honor no-subagents. One bounded auxiliary is normally the maximum;
  more requires explicit operator direction or an approved plan within tool/task limits.
- Before dispatch, state benefit, confirmed model/effort, worker count, objective,
  rationale, files/interfaces, invariants, edge cases, forbidden changes and acceptance.
  Never silently substitute an unavailable model or escalate effort after a failed test.
- Coordinator owns design, integration, controlled records and acceptance. Workers
  preserve shared edits, edit only assigned code/tests, never recursively delegate,
  set safety/planner policy, declare acceptance or edit controlled docs. Verification
  workers are read-only. No worker GUI/ROS execution without explicit scoped authority.
- Inspect actual diffs/evidence. Return unsettled interfaces/theory/policy to the
  coordinator; clarify specifications instead of entering model/retry loops.
  These project rules supersede conflicting skill model presets/mandatory reviews.

## Graph navigation

- The overlay `~/dentobot/graphify-out/` is the only live graph. On `$graphify` or
  `/graphify`, use the installed skill first. For codebase questions with graph.json
  present, first use `graphify query`; use `path` for relationships and `explain`
  for concepts. Dirty graph files are not grounds to skip it; stale-graph diagnosis
  or explicit operator direction is. Prefer wiki/index.md for broad navigation;
  read GRAPH_REPORT.md only when scoped queries cannot support architecture review.
- After code changes, refresh only the overlay via `Workspace/scripts/graphify-update.bash`
  or `graphify update .` from the actual overlay root. Never rebuild under the source
  checkout. Require exit 0 plus `Code graph updated` or `[graphify watch] Rebuilt:`;
  stream-fd wrapper noise alone is not a rebuild failure.

## Environment and A/B work

- Current performance/watchdog diagnosis targets native Ubuntu on the consolidated
  integration checkout. Record hardware/runtime identity with RAM/swap/I/O/CPU/GPU
  evidence; never generalize it to Windows/WSL/WSLg. Imported Windows paths/commands
  remain historical until migrated and verified. A later Windows campaign needs
  its own host/VM/filesystem/graphics baselines. Retain the indefinite Slicer 5.12 hold.
- In A/B work, A's designated orchestrator is the sole controlled-doc writer.
  Routine B tests are script-only background jobs launched from A; collect exit/done
  evidence. Open a read-only B diagnosis thread only for failures A cannot explain.
- B tests only origin-pushed SHAs (WIP uses approved `test/…` branches), never A's
  working tree. Label results `verified at <sha>`; compare covered files with
  `git diff <sha>..HEAD` before reuse and rerun when changed.
- B produces evidence; any B code uses a `b/…` branch deliberately merged by A.
  B GUI results retain the applicable operator-verdict gate.

## Thread handoff

- At handoff, stop safely and start no new work. Append a dated section to the
  operator workspace's `HANDOFF.md`, preserving earlier entries: completed paths/SHAs,
  ordered continuation, settled decisions, gotchas, open questions and verification
  commands. Do not execute verification/runtime as part of handoff.
- Reply with one fenced text block under 80 words: one job, "read HANDOFF.md first",
  and first next step. Before dispatch, run `handoff-thread.py --list` on the target
  host; present agent/model/effort/subagent policy and obtain Tarun's confirmation.
  Dispatch with explicit `--agent/--model/--subagents`; destination restates selection
  and confirms before runtime, honoring any current explicit already-confirmed scope.

## Response style and approved continuity

Response style and **DENTO-STYLE-RESET**: follow `/home/tarun/.codex/RESPONSE_STYLE.md`.
Preserve safety/identity/acceptance guards and historical caps.

Handoff preserves approved scope/budget; never reask merely for new thread/command. Keep updates short: result→fix owner→next→input only if needed.
