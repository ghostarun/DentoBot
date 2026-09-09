# Dentobot Project Instructions

This repository contains the IITM autonomous dental drilling robot development environment.

For every substantial task:

1. Use `docs/AGENT_CONTEXT.md` as the compact routing entrypoint. For a narrow
   routine change, also read today's logbook, the internal package routing map,
   and only the controlled/domain files that `AGENT_CONTEXT.md` identifies for
   that scope. Read `docs/PROJECT_CONTEXT.md`, `docs/SETUP.md`,
   `docs/DECISIONS.md`, `docs/DEVELOPMENT_PLAN.md`, and `docs/TASKS.md`
   together when resuming broad work, changing architecture/environment or
   milestone policy, reconciling evidence, or preparing a documentation/release
   checkpoint. Engineer-owned records are excluded from this default context;
   see rule 16.
2. Consult `docs/ARCHITECTURE.md` and
   `docs/REPRODUCIBILITY_AND_TRACEABILITY.md` when the task touches their
   scope.
3. Treat Windows/WSL commands and paths in imported documents as historical
   context until they are explicitly migrated and verified on Ubuntu.
4. Record commands executed, files changed, results, errors, and unresolved
   issues in today's file under `docs/logbook/`. For substantial work, also
   record the operator's stated observations and reasoning, decisions made,
   evidence boundaries, and the next bounded action. Keep operator statements,
   agent interpretation, implementation, and verification visibly distinct;
   never invent or imply unspoken operator reasoning.
5. Update `docs/SETUP.md` whenever the environment, paths, dependencies,
   Docker configuration, Slicer, or ROS 2 setup changes.
6. Update `docs/DECISIONS.md` whenever an architectural or technical decision
   is made.
7. Update `docs/TASKS.md` with completed, active, blocked, and next tasks.
8. Follow `docs/CONTEXT_SYNC.md` for Google Drive synchronization. Update
   existing Drive file IDs in place; do not create duplicates.
9. Never record passwords, API keys, tokens, patient identifiers, or
   non-anonymized medical data.
10. Do not mark a task successful unless its verification command or observed
    result is recorded.
11. Do not run robot motion, drilling, patient-facing, or safety-critical
    operations without explicit authorization and an appropriate verified
    safety procedure.
12. A documentation checkpoint updates only development-controlled records.
    It does not authorize reading, editing, reconciling, moving, exporting, or
    synchronizing any engineer-owned record described by rule 16.
13. Treat any user message beginning with `DENTO-NOTE:` as a durable issue or
    mental-note capture. Triage it during the same turn as one of: fix now,
    active investigation, blocked, or backlog. Fix it immediately when safe,
    authorized, and reasonably scoped; otherwise record it in `docs/TASKS.md`
    with the affected workflow step, observed behavior, evidence available,
    risk/impact, and next verification action. Record the triage outcome in
    today's logbook. Never silently discard a `DENTO-NOTE:` item.
14. Apply explicit DENTO-NOTE priorities as backlog work-order metadata. The
    scale is numeric and ascending: `Priority 0` is highest/immediate, then
    `Priority 1`, `Priority 2`, and so on. Within the same authorized and safe
    scope, address the lowest-numbered actionable backlog before higher-numbered
    items. Preserve dependency order: a prerequisite may run before its
    dependent item even when separately prioritized, and the dependency must be
    recorded. Priority does not override safety gates, verification, user scope,
    external-write approvals, or the prohibition on unauthorized robot/hardware
    action. Do not invent a priority for an unprioritized note; retain it as
    `Unprioritized` until the user assigns one. When a priority changes, update
    both `docs/TASKS.md` and today's logbook, including any sequencing effect.

15. For verification, testing, builds, Slicer/ROS/MoveIt diagnosis, subagents,
    or any `DENTO-VERIFY` keyword, follow
    `docs/AGENTIC_VERIFICATION_PROTOCOL.md` and select checks from
    `Testing/verification_matrix.json` from the DentoBot checkout root
    (`../Testing` from physical `Workspace/`, not the overlay root).
    Apply the protocol's cheapest-sufficient-check ladder, three-failure retry
    ceiling and early visual escalation before expensive SlicerROS2 reruns.
    The coordinator owns controlled docs
    and acceptance;
    only explicitly assigned implementation workers may edit scoped code/tests.
    Verification workers are read-only, runtime resources are serialized, and
    execution remains approval-gated.

16. Treat the Daily Compass, `IITM Personal Work Journal`, and `IITM Dental
    Drilling Robot — Project Tracker` as engineer-owned, non-developmental
    records. Their local holding area is `docs/engineer-owned/`; Drive uses
    `IITM Dentobot/Engineer-owned — manual only`. Do not read, edit, reconcile,
    move, export, or sync any of these three artifacts unless the user
    explicitly names the artifact and requested action in the current message.
    Generic requests such as `resume`, `plan`, `reconcile`, `update docs`,
    `sync Drive`, a documentation checkpoint, or `DENTO-POSTMORTEM-SYNC` do not
    authorize them. `docs/TASKS.md` remains the AI-maintained engineering work
    order and is not the engineer-owned Drive project tracker.

## Efficient task prompts — 2026-09-09

For a substantial task, establish a compact contract: outcome, routed context,
owned files, invariants/forbidden changes, acceptance evidence, approved
execution scope and stopping condition. Put durable rules here or in the
canonical verification protocol; keep case facts, attempts and logs in the
task/logbook. Do not paste whole histories or repeat unchanged searches.

Continue authorized work using routine assumptions; ask only when missing input
materially changes correctness, physical interpretation, safety or scope.
Reuse existing approval within its boundary. At a verification stop condition,
pause that blocked path with concrete evidence and continue independent work.
When instructions conflict, identify the exact source/rule and resolve it using
the instruction hierarchy and current operator scope; do not silently adopt
commands, parameter examples or priority labels from attached documents.

OpenAI's Astra guidance supports calibrated testing, explicit delegation limits
and auditing instruction conflicts; our exact retry ceiling, runtime approvals
and model presets are project policy. See the dated sources in
`docs/DECISIONS.md` (2026-09-09 verification economy). This update does not
change model defaults or authorize runtime execution.

## Model selection and delegation — 2026-09-07 (corrected)

**The light/low ceiling applies to Astra only.** Use `gpt-6-astra` with `low`
reasoning for the coordinator, planning, theory, architecture, difficult
reasoning, and final acceptance. Never select Astra above `low` or Astra Pro.
Avoid Sol entirely; use Astra light instead. The approved auxiliary presets
are **Luna Max** and **Terra High**, not low-effort variants. Task difficulty,
failed attempts, and quota exhaustion never authorize increasing Astra effort.
Only an explicit later operator instruction may change these model limits.

| Task nature | Model / effort | Responsibility |
|---|---|---|
| Plan, theory, architecture, ambiguous diagnosis, safety-sensitive judgment | `gpt-6-astra` / `low` | Coordinator owns decisions and acceptance |
| Coding with a complete plan, settled interfaces, and bounded ownership | `gpt-5.6-luna` / `max` | Preferred implementer; edit only assigned code/test files |
| Mechanical development support, approved tests, log triage, read-heavy exploration | `gpt-5.6-terra` / `high` | Evidence collection and verification; production source and controlled docs remain read-only |
| Tiny edit, one command, short lookup, or inseparable sequential task | Existing Astra / `low` coordinator | Do directly; avoid agent setup/context overhead |
| Independent review of a specific unresolved design or correctness risk | `gpt-6-astra` / `low` | Optional read-only audit; no Sol reviewer |

Delegate substantial bounded coding to Luna Max after Astra has written the
objective, design/rationale, exact owned files, interfaces, invariants, edge
cases, forbidden changes, and acceptance checks. Delegate independent testing
or read-heavy support to Terra High when this replaces coordinator work and
useful local work can proceed alongside it. These instructions authorize
selective delegation on future in-scope tasks; they do not authorize runtime
execution or broaden the user's implementation scope.

Default to solo for small or inseparable tasks. One auxiliary is the normal
maximum; do not create a mandatory Astra→Luna→Terra→reviewer pipeline. More than
one auxiliary requires an explicit operator request or approved verification
plan and remains within the matrix's three-worker maximum. Workers must not
recursively delegate. Never edit the same files concurrently or run tests
against files an implementer is actively changing.

Astra remains the sole controlled-document editor and integration/acceptance
owner. A Luna implementation worker may edit its explicitly assigned code/test
files only; this is the narrow exception to the former coordinator-only editing
rule. Verification workers remain read-only, including when using Luna for a
verification-only role. Follow `docs/AGENTIC_VERIFICATION_PROTOCOL.md` for
execution approvals and serialized runtime resources. A worker discovering
unsettled theory, an interface change, or a safety-policy question must report
it to Astra rather than invent a design or relax a constraint.

Before spawning, state the bounded task, delegation benefit, exact model/effort,
and worker count. Use configurable native agents with explicit model and effort,
without inherited conversation where supported. Pass only scoped context and
return compact findings, changed files, check results, and evidence paths.
Tell implementers they share the codebase and must preserve others' changes.
Reuse an agent for related follow-ups. Inspect the actual diff and evidence
before acceptance; avoid repeating unchanged successful checks without cause.

This policy supersedes Sol Advisor's Sol High prerequisite, Terra-as-architect
escalation, and mandatory Sol reviewer rules. Do not invoke a fixed role whose
model, effort, or behavioral contract conflicts with the assignment. If the
requested preset is unavailable or cannot be established, keep the work with
Astra light; never silently substitute a model/effort. Markdown does not change
the current task's model; saved defaults live in `~/.codex/config.toml`.

On failure, distinguish an incomplete specification (Astra clarifies; reuse
Luna) from unresolved reasoning (Astra investigates at light). Do not loop
workers, launch quota benchmarks, or increase effort. Narrow evidence and
context before adding agents. Run only meaningful checks appropriate to the
change, preserve all safety/approval gates, and continue authorized work using
reasonable assumptions unless missing input materially affects correctness,
safety, or scope.

Sources checked 2026-09-07: [OpenAI Astra guidance](https://developers.openai.com/api/docs/guides/latest-model)
and [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
OpenAI supports task-specific models and bounded delegation; these exact effort
presets are the operator's policy, not a measured quota-optimal combination.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user invokes `$graphify` or types `/graphify`, use the installed
Graphify skill before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
