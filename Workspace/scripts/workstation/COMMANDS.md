# DentoBot workstation commands

Both machines use the same versioned package in `Workspace/scripts/workstation`, installed under `~/.local/share/dentobot-handoff`. `~/.local/bin/dentobot` selects its host's configured checkout. A uses its original checkout; B uses the preserved runtime worktree. Older B checkouts are retained.

```bash
dentobot status
dentobot parity
dentobot check
dentobot open
dentobot launch
```

`parity` checks the shared image ID, native source and installed libraries, installed robot/MoveIt resources, all pinned model weights and the approved immutable test bundle. `check` includes that gate and the existing source/backend/desktop preflight. Host CUDA versus CPU, username/display paths and cache telemetry remain host-specific. No container starts during these checks.

After an intended reviewed commit, refresh the explicit source pin:

```bash
dentobot use "$(dentobot path)"
```

On B, prepare an exact Git checkpoint in a fresh worktree on the other host; commit intended edits first. No automatic commit, stash/reset or force-push occurs:

```bash
dentobot from-a --note 'Continue committed development on B.'
dentobot to-a --note 'Continue committed development on A.'
```

Select the returned destination worktree on that machine with `dentobot use /returned/path`, then run `dentobot check` before testing. Give the returned `CONTINUE.md` to its T3 thread. `--committed-only` on `from-a` explicitly excludes unfinished A edits. T3 Connect exposes threads; GitHub sharing shares provider access, and load balancing affects new threads. These settings do not copy local case files or running processes.

Exchange one newly saved case from its owning machine (data-relative path), including a byte checksum and source stability check:

```bash
dentobot sync-case Slicer_Saved/Shared/my-case.dentocase --to B
# On B, after saving a new revision:
dentobot sync-case Slicer_Saved/Shared/my-case.dentocase --to A --replace
```

A different destination is refused without `--replace`; that option retains a uniquely named backup before updating. Identical files are a no-op. Avoid changing the pinned immutable acceptance fixture; save development revisions under new names. Case exchange is explicit and individual; raw data, personal settings, tokens and engineer-owned records are not mirrored. A case in active use should be saved and its writer paused before exchange.

For isolated B GUI verification, without occupying A's desktop:

```bash
# Local B; prepares only without --run:
dentobot smoke --run
# From A:
ssh dentobot-b '~/.local/bin/dentobot smoke --run'
```

The five-reload smoke uses private Xvfb and recording. It requires clean pinned source, common runtime parity, stopped configured container, no existing runtime owners and exclusive locks. It never starts MoveIt or hardware. Case/frame/save-reopen evidence is a distinct bounded campaign. Artifacts are dated under `data/dentobot-runs`. A may go offline once destination Git, required case/runtime checks and destination thread ownership are confirmed; a Git-ready handoff alone does not establish runtime or conversation continuity.

For A desktop checks over SSH, the current session uses the GDM Xauthority file:

```bash
ssh dentobot-a 'PATH="$HOME/.local/bin:$PATH" ~/.local/bin/dentobot check --display :0 --xauthority /run/user/1000/gdm/Xauthority'
```

Authentication paths may change after logging out. A's GPU override points to the selected checkout's versioned `Workspace/compose.cuda.yaml`; other local overrides are refused by preflight. Both data locks now include EndoPlanner source/resources.

`dentobot launch` uses the selected clean checkpoint and verifies the lock before opening Slicer. It passes `--use-installed-runtime` to the existing launcher: no build, no stale-build deletion and no scripted-test removal. It refuses existing Slicer/MoveIt/recorder owners and validates image, host user and mounts. It starts the named container directly, avoiding Compose reconciliation/recreation and old rollback labels. Run it from a desktop terminal with the session display/authentication available. `dentobot launch --check-only` checks the launcher without opening Slicer, but may start the verified dedicated container; `dentobot check` remains read-only.

The lock also pins robot/MoveIt source files, so edited ROS resources cannot silently use old installed files. For an intentional native/ROS build, use the existing launcher/build procedure without `--use-installed-runtime`, then explicitly distribute and repin the common installed runtime on both hosts before handoff. Python-only workflow development uses the installed runtime. Native scripted test autoload modules are retained in dated backups and excluded from the common production install, matching its `SLICER_ROS2_INSTALL_SCRIPTED_TESTS=OFF` policy.
