# Dentobot Project Instructions

This repository contains the IITM autonomous dental drilling robot development environment.

For every substantial task:

1. Read `docs/PROJECT_CONTEXT.md`, `docs/SETUP.md`, `docs/DECISIONS.md`,
   `docs/DEVELOPMENT_PLAN.md`, and `docs/TASKS.md` before making changes.
   When the user asks to resume, plan, reconcile notes, or update the daily
   mental model, also read `docs/DENTOBOT_Daily_Compass.docx`. Treat its
   unreconciled entries as editable working memory, not accepted requirements
   or verification claims.
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
