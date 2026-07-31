# DENTOBOT repository agent entrypoint

Read and follow `docs/AGENTS.md` before substantial work. The controlled
project context is in `docs/PROJECT_CONTEXT.md`, `docs/ARCHITECTURE.md`,
`docs/DEVELOPMENT_PLAN.md`, `docs/REPRODUCIBILITY_AND_TRACEABILITY.md`,
`docs/UBUNTU_TRANSFER.md`, `docs/changelog.md`, and `docs/logbook.md`.

## Standing close-day trigger

When the user says **"close my day"** or **"close the day"**, treat that phrase
as authorization to complete the repository close-day protocol in
`docs/AGENTS.md`. Do not merely summarize. Run the checks, update the
controlled documentation, create the Git commit and annotated checkpoint tag,
perform a non-force push when an upstream is available, synchronize changed
controlled Markdown to the existing Google Drive file IDs, verify the
checkpoint, and report any step that could not be completed.

The trigger never authorizes robot motion, drilling, deletion of research
data, force-pushes, uploading runtime/data/model artifacts, or committing
credentials.
