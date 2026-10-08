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

## Visible B case-open from A (`PLAT-U-07` Goal 2)

A-hosted agents can run a headed Slicer case-open on B's GNOME desktop (the operator watches B through Remmina) and get the verdict, screenshots and logs back on A. B stays script-only: no B agent, no MoveIt, no motion.

```bash
# On A, from a clean checkout whose HEAD is pushed (or pass --sha / --repo). Run it as a background job and keep working:
dentobot visible-case request --case Slicer_Saved/Shared/my-case.dentocase --hold 90
# Later, or after A lost its connection (also safe to repeat):
dentobot visible-case collect --run-id 20261008T122000Z
dentobot visible-case request ... --no-wait      # only start the run, collect later
```

`request` checks on A that the SHA is published on origin and the checkout is clean (it never uses `dentobot path`), asks B to start one **detached** supervised run, polls its state and collects. B prepares a detached worktree `DentoBot-visible-<sha12>` of exactly that SHA beside its selected checkout, requires `dentobot parity` to pass for it, copies the case into the run directory, grants a scoped `xhost` for its own user only, runs the case, revokes the grant and always writes `DONE.json` last (PASS/FAIL/ERROR, SHA, manifest of file hashes). A run killed without `DONE.json` reports `incomplete`; `collect --accept-incomplete` records it and never labels it PASS. Evidence is labelled "verified at <sha>" only for PASS.

Exit codes: 0 PASS (or accepted with `--no-wait`); 2 FAIL/ERROR/refusal; 3 not final or B unreachable (collect later). The last stdout line is always one JSON object. If B is unreachable and `ssh dentobot-b true` prints a Tailscale SSH check link, the operator must approve it in a browser; the run on B continues regardless.

`collect` copies `data/dentobot-runs/<date>/PLAT-U-07-B-visible-case-<id>/` (without `input/`, the case copy stays on B) into A's data tree through a temporary directory, verifies every file against `DONE.json`, then renames it into place. A second collect is a no-op; a different existing destination is refused, never overwritten. B's `request`-side commands are `run` and `status` (internal to A's requests, usable on B directly). Screenshots are Slicer window grabs: the target is framed by the production "Frame Target in All Views" action when the case has a planning target, and duplicate screenshots are dropped. The first screenshot set is for the operator's visual verdict; a PASS is not workflow acceptance.

Both hosts need the package installed, including `visible_case.py` and `visible_case_bootstrap.py`, and B only runs when no other Slicer/MoveIt owner or runtime lock exists.
