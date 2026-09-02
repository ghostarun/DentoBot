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
   checkpoint. When the user asks to resume, plan, reconcile notes, or update
   the daily mental model, also read `docs/DENTOBOT_Daily_Compass.docx`. Treat
   its unreconciled entries as editable working memory, not accepted
   requirements or verification claims.
2. Consult `docs/ARCHITECTURE.md` and
   `docs/REPRODUCIBILITY_AND_TRACEABILITY.md` when the task touches their
   scope.
3. Treat Windows/WSL commands and paths in imported documents as historical
   context until they are explicitly migrated and verified on Ubuntu.
4. Record commands executed, files changed, results, errors, and unresolved
   issues in today's file under `docs/logbook/`.
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
12. At an approved documentation checkpoint, reconcile confirmed Daily Compass
    entries into the applicable controlled Markdown documents and dated
    logbook. Do not sync Git or Google Drive merely because the workbook was
    edited; retain the existing batched approval rule.
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
    `../Testing/verification_matrix.json`. The coordinator is the sole editor;
    workers are read-only, runtime resources are serialized, and execution
    remains approval-gated.

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
