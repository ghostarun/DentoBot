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

- Active controls: `AGENTS.md`, `docs/backlog.md`, `docs/SETUP.md`,
  `docs/DECISIONS.md`, `docs/TASKS.md`, and `docs/CONTEXT_SYNC.md`.
- Continuous design baseline: `docs/PROJECT_CONTEXT.md`,
  `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_PLAN.md`, and
  `docs/REPRODUCIBILITY_AND_TRACEABILITY.md`.
- Active GUI migration inventory: `docs/GUI_ACTION_PARITY.md`.
- Change history: `docs/changelog.md`.
- Platform history: `docs/logbook/logbook-windows-history.md`.
- Active chronological evidence: dated files under `docs/logbook/`.
- Engineer-owned records: local `docs/engineer-owned/` and Drive
  `IITM Dentobot/Engineer-owned — manual only`. This class contains
  `DENTOBOT_Daily_Compass.docx`, `IITM Personal Work Journal`, and
  `IITM Dental Drilling Robot — Project Tracker`. These are not development
  controls or sources for acceptance claims.

Imported design documents remain applicable at the product/design level.
Windows/WSL paths, commands, runtime boundaries, and validation claims are
platform-qualified history until verified in the Ubuntu environment.

The Drive mirror is not automatically authoritative merely because it has a
newer timestamp. A chat must first retrieve it, compare it with the local
record, and resolve conflicts explicitly.

## Engineer-owned record boundary

Do not read, edit, reconcile, move, export, or synchronize an engineer-owned
record unless the user explicitly names that artifact and action in the
current request. Generic requests such as `resume`, `plan`, `reconcile`,
`update docs`, `sync Drive`, a documentation checkpoint, `close my day`, or
`DENTO-POSTMORTEM-SYNC` are insufficient. A Drive development sync excludes
the engineer-owned folder by default.

When the user explicitly requests Daily Compass reconciliation:

1. read the complete workbook and compare its entries with repository state;
2. identify contradictions, unsafe assumptions, and clinical thresholds that
   are still ambiguous rather than guessing a resolution;
3. promote confirmed context, decisions, tasks, evidence, and failures into
   the applicable controlled Markdown file and today's dated logbook;
4. leave exploratory or incomplete notes in the workbook until the researcher
   accepts them; and
5. update the workbook's reconciliation date and current operating picture.

Engineer-record reconciliation is a local documentation action. It does not by itself
authorize Git publication or Google Drive synchronization. Those remain
explicit batched operations under the existing approval rule.

## End-of-session sync

After a substantial Codex CLI development session:

1. Update `backlog.md`, `SETUP.md`, `DECISIONS.md`, `TASKS.md`, and today's
   logbook as required by `AGENTS.md`.
2. Record verification output or observed results.
3. Upload changed active documents to
   `IITM Dentobot/active-development-ubuntu`, replacing the matching copies by
   their existing Drive file IDs after checking names and parent folders.
   Never upload a second file with the same logical path.
4. Tell the browser chat the Drive sync time and which files changed.

The three engineer-owned records are excluded from this sequence unless the
current request explicitly names the record and requested Drive action.

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

## Multi-workstation source/data boundary — 2026-09-12

Git and Drive have separate jobs for the multi-workstation checkout:

- Git at `ros2_ws/src/DentoBot` is authoritative for source, tests, launchers,
  Compose/configuration examples, and controlled documentation. Each
  workstation keeps its own `.dentobot.env`, build/install/log products,
  `slicer-home/`, and local `data/` tree.
- `IITM Dentobot/active-development-ubuntu` is the in-place mirror for active
  Ubuntu documents. It is not a bulk case-data or run-record folder.
- The operator-approved saved-case destination is `IITM Dentobot/Data`
  (`1u1K2EVeBe3-U1-JeWxKhOKslEW-zFnkd`). Preserve the local
  `SampleStudy1/FDI*` layout there; do not mix it with the document mirror.
- The narrow exchange unit is an individual `*.dentocase` file, not the whole
  `data/Slicer_Saved/` directory. A `.dentocase` is a portable archive: its
  embedded MRB may contain CBCT-derived NRRD volumes, segmentations, and other
  anatomy. Exchange only synthetic or explicitly approved de-identified
  bundles. A personal Drive account and file size do not by themselves approve
  storage of patient-derived data.
- Keep `.mrb`, `.stl`, `.nrrd`, screenshots, run records, and other
  `Slicer_Saved` files out of the exchange by default. Do not watch, mount, or
  mirror the whole `data/` tree. Use a non-identifying logical case key and
  verify the bundle checksum before opening it on another workstation.
- Drive writes remain batched and explicit. Before replacing a file, verify
  its name and parent and update the existing Drive file ID in place; never
  create a duplicate logical path. The 2026-09-13 pilot is recorded in the
  dated logbook; its remaining large-file uploads require an authenticated
  browser because the connector has a 100 MB input limit.

## Dated logbook standard

For every substantial development turn, today's dated logbook separates:

1. the operator's reported observation and stated reasoning;
2. the engineering interpretation or decision;
3. work performed and files changed;
4. commands and verification evidence;
5. failures, limitations, and evidence boundaries; and
6. the next bounded action.

Record only reasoning the operator actually stated. Label agent inference as
interpretation, and never present inferred motivation as the operator's own.
