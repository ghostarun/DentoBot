# Codex and Browser Chat Context Sync

## Sources of truth

1. Local Ubuntu paths under `/home/light-tarun/dentobot` are authoritative for
   current implementation work and documentation. The top-level active notes
   resolve to Git-tracked files under
   `ros2_ws/src/DentoBot/Workspace/docs`.
2. Google Drive `IITM Dentobot/active-development-ubuntu` is the exchange copy
   used by Codex CLI and browser ChatGPT.
3. Google Drive `IITM Dentobot/docs` is the controlled mirror for the
   repository's `docs/` design/history set. It retains platform-qualified
   Windows history and is updated in place when those tracked files change.

## Document classes

- Active controls: `AGENTS.md`, `docs/SETUP.md`, `docs/DECISIONS.md`,
  `docs/TASKS.md`, and `docs/CONTEXT_SYNC.md`.
- Continuous design baseline: `docs/PROJECT_CONTEXT.md`,
  `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_PLAN.md`, and
  `docs/REPRODUCIBILITY_AND_TRACEABILITY.md`.
- Change history: `docs/changelog.md`.
- Platform history: `docs/logbook/logbook-windows-history.md`.
- Active chronological evidence: dated files under `docs/logbook/`.

Imported design documents remain applicable at the product/design level.
Windows/WSL paths, commands, runtime boundaries, and validation claims are
platform-qualified history until verified in the Ubuntu environment.

The Drive mirror is not automatically authoritative merely because it has a
newer timestamp. A chat must first retrieve it, compare it with the local
record, and resolve conflicts explicitly.

## End-of-session sync

After a substantial Codex CLI development session:

1. Update `SETUP.md`, `DECISIONS.md`, `TASKS.md`, and today's logbook as
   required by `AGENTS.md`.
2. Record verification output or observed results.
3. Upload changed active documents to
   `IITM Dentobot/active-development-ubuntu`, replacing the matching copies by
   their existing Drive file IDs after checking names and parent folders.
   Never upload a second file with the same logical path.
4. Tell the browser chat the Drive sync time and which files changed.

Git and Drive have different scopes. Git now tracks both `docs/` and
`Workspace/docs/`; Drive keeps their two established folder/file-ID sets.
Never collapse same-named files across those folders or create duplicates.

After a browser planning session:

1. Save agreed plans or decisions into the active Ubuntu Drive folder.
2. In Codex CLI, retrieve and compare that material before changing local
   source-of-truth files.
3. Mark proposals as proposals until they have been implemented and verified.

## Conflict rule

Do not merge Windows commands, paths, dependency versions, or task completion
claims into the Ubuntu record without verification on the Ubuntu workstation.
When local and Drive copies disagree, preserve both, compare them, and record
the resolution in the daily logbook.

For a newly copied Drive history file, first bring the same bytes into the
local hierarchy. After that first reconciliation, the local copy is
authoritative and future syncs update the existing Drive file ID in place.

## Data safety

Never sync passwords, tokens, API keys, patient identifiers, or
non-anonymized medical data.
