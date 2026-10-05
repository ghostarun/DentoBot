# DENTOBOT repository agent entrypoint

For the active Ubuntu workspace, read and follow `Workspace/AGENTS.md` and use
`Workspace/docs/AGENT_CONTEXT.md` as the compact routing entrypoint. The
`Workspace/docs/` controlled files are authoritative for current Ubuntu/ROS 2
work. The older top-level `docs/` set remains historical/cross-platform context
and should be consulted when a routed task specifically touches it.

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

## Shared agentic verification

For verification, testing, builds, Slicer/ROS/MoveIt diagnosis, subagents, or
any `DENTO-VERIFY` keyword, follow
`Workspace/docs/AGENTIC_VERIFICATION_PROTOCOL.md` and select checks from
`Testing/verification_matrix.json`. This is the common Codex/Cursor/Claude
contract; tool-specific instructions may point to it but must not redefine it.

## Future testing output storage — 6 October 2026

Follow the **Testing output storage** convention in `Workspace/docs/AGENT_CONTEXT.md` for
all future tests/diagnostics: durable artifacts under the Ubuntu overlay's
`data/dentobot-runs/YYYY-MM-DD/<task-id>-<UTC-start-timestamp>/`, using the UTC
run-start date. Configure existing output overrides before execution, keep all
run evidence/session files together, and archive completed verification scratch
there. Do not create flat root run folders, overwrite runs, or move live writers.
The canonical verification protocol retains execution/acceptance authority.
