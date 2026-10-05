# Run archive organization — 6 October 2026

Task: `RUN-ARCHIVE-01`. Local archive: `/home/tarun/dentobot/data/dentobot-runs`;
container view: `/workspace/data/dentobot-runs`.

Existing runs now live at `YYYY-MM-DD/<original-run-name>/`. Watchdog files
are grouped at `YYYY-MM-DD/ui-watchdog/`. Dates encoded in names take precedence
and are preserved literally, including inconsistent historical timestamps;
UUID-only runs use host-local directory mtime. Undated monitor stderr logs use
the matching resources-log PID/date. The three UUID run folders fall on
2026-09-07 (two) and 2026-09-17 (one).

[Move manifest](RUN_ARCHIVE_MOVES_2026-10-06.json) maps every old path to its new
path. Historical log/script/JSON path strings remain original evidence; use the
manifest to locate moved artifacts. This is a filesystem organization change,
not a change to prior run results or acceptance.

Both temporary root compatibility symlinks were retired on 6 October after
Tarun explicitly authorized stopping the active session. The dated GUI and
watchdog data directories remain intact; the manifest retains the former aliases
as retired mappings. The root now contains only date folders.

New simulation handoffs write shared watchdog output directly under the UTC
start-date folder; `DENTOBOT_WATCHDOG_LOG_DIR` selects run-local output. Other
producer defaults are unchanged: agents must configure the paths in
AGENT_CONTEXT.md or record an exception and archive after the writer stops.

Verification: 88 rename operations; device/inode/type identity unchanged for
all 3,795 moved filesystem entries. No payload rewrites or deletions. The local
5 GB archive is outside the source Git checkout; Git records this note, the
manifest and controlled-document updates, not the run payloads.
