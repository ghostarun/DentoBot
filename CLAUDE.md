# DENTOBOT Claude entrypoint

Follow `Workspace/AGENTS.md`. For verification, testing, building,
Slicer/ROS/MoveIt diagnosis, subagents, or `DENTO-VERIFY`, follow the canonical
`Workspace/docs/AGENTIC_VERIFICATION_PROTOCOL.md` and
`Testing/verification_matrix.json`. Use fresh self-contained read-only
subagents and serialize all declared runtime resources. The coordinator alone
edits production source.


## Future testing output storage — 6 October 2026

Follow the **Testing output storage** convention in `Workspace/docs/AGENT_CONTEXT.md` for
all future tests/diagnostics: durable artifacts under the Ubuntu overlay's
`data/dentobot-runs/YYYY-MM-DD/<task-id>-<UTC-start-timestamp>/`, using the UTC
run-start date. Configure existing output overrides before execution, keep all
run evidence/session files together, and archive completed verification scratch
there. Do not create flat root run folders, overwrite runs, or move live writers.
The canonical verification protocol retains execution/acceptance authority.
