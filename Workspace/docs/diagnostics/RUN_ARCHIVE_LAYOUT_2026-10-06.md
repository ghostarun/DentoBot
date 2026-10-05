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

Two root compatibility symlinks preserve the currently active handoff:

- `gui-step4a-20261006T204848Z` → `2026-10-06/gui-step4a-20261006T204848Z`
- `ui-watchdog` → `2026-10-05/ui-watchdog`

The active watchdog writes through already open file descriptors. The GUI
session polls its original absolute path, so its alias must remain while active.
Retiring these aliases is pending under `RUN-ARCHIVE-01` in backlog.md. Existing
producers are unchanged; new runs may still use the flat root. Do not reuse the
watchdog alias for a new session on a different date without updating routing.

Verification: 88 rename operations; device/inode/type identity unchanged for
all 3,795 moved filesystem entries. No payload rewrites or deletions. The local
5 GB archive is outside the source Git checkout; Git records this note, the
manifest and controlled-document updates, not the run payloads.
