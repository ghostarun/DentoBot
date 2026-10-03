# Host overlay layout

`~/dentobot` is not a git repository. Git lives in
`ros2_ws/src/DentoBot` (branch `main`, tracking `origin/main`).

Root shortcuts (symlinks) exist so Ubuntu looks like a normal project:

| You open | Real path |
|---|---|
| `docs/` | `ros2_ws/src/DentoBot/Workspace/docs/` |
| `AGENTS.md` | `ros2_ws/src/DentoBot/Workspace/AGENTS.md` |
| `scripts/` | `ros2_ws/src/DentoBot/Workspace/scripts/` |
| `launch-dentobot` | `scripts/launch-dentoworkflow.bash` (follows `scripts/`) |
| `compose.yaml` | `ros2_ws/src/DentoBot/Workspace/compose.yaml` |
| `tools/` | `ros2_ws/src/DentoBot/tools/` |

`Workspace/` here means the Ubuntu overlay (docs, Compose, launchers). It is
not the Slicer six-workspace UI.

## Source vs local data

- **Product:** `DENTOWorkflow/`, `dentobot_description/`, `dentobot_moveit_config/`, `Testing/`
- **Host tools:** `tools/arduino-pressure/`
- **Upstream ROS/Slicer:** `ros2_ws/src/slicer_ros2_module/`
- **Local only:** `data/`, `slicer-home/` (plus `slicer-user` →
  `slicer-home/.config/slicer.org`), `ros2_ws/build|install|log/`, overlay
  `graphify-out/`, pressure `pressure_runs/`
- **Frozen snapshot:** `archive/DentoBot-demo-aff8b2e/` (own git; not on the colcon path)
- **Stale notes:** `docs-legacy/` inside the DentoBot checkout

Recreate the overlay links with `Workspace/bootstrap-workspace.bash`.

## Lab clone layout (Windows WSL2)

Lab PCs recreate this overlay **inside WSL**, never by zipping `~/dentobot`.
The canonical installation and Docker-provider rules are in
`Workspace/docs/WINDOWS_SETUP.md`. Docker Engine inside the selected WSL
distribution is the default; Docker Desktop integration is a mutually
exclusive alternative.

```text
~/dentobot/                          # overlay root; not a git repository
  compose.yaml -> ros2_ws/src/DentoBot/Workspace/compose.yaml
  scripts/     -> ros2_ws/src/DentoBot/Workspace/scripts/
  launch-dentobot -> scripts/launch-dentoworkflow.bash
  docs/        -> ros2_ws/src/DentoBot/Workspace/docs/
  tools/       -> ros2_ws/src/DentoBot/tools/
  .dentobot.env                      # local; not in git
  data/                              # local model cache and cases; not in git
  slicer-home/                       # local Slicer HOME/config; not in git
  slicer-user -> slicer-home/.config/slicer.org
  ros2_ws/
    src/DentoBot/                    # git at detached lab/* tag (not main)
    src/slicer_ros2_module/          # DentoBot fork; pinned SHA
    src/dentobot_description -> DentoBot/dentobot_description
    build/ install/ log/             # local colcon products; do not copy
```

Pin file: `ros2_ws/src/DentoBot/Workspace/LAB_RELEASE` (read from `origin/main`;
current candidate on 3 October 2026: `lab/2026-10-03-2`, SlicerROS2 `ece3c427443a`).
First-time: `scripts/install-lab-wsl.bash` (or `install-lab-wsl.bat` from Windows).
Updates: `scripts/update-lab-release.bash` (or `update-lab-release.bat`).
Launch: `./launch-dentobot` or `scripts/launch-dentoworkflow.bash` from `~/dentobot`
(or `launch-lab-workflow.bat`). Add `--choose-checkout` to pick another
checkout for one launch. Native Ubuntu desktops can add an app-menu
entry with `scripts/install-desktop-launcher.bash` (`--remove` undoes it).
Use `launch-lab-workflow.bat` for this profile. The retired ambiguous
`launch-dentoworkflow.ps1` exits with profile-selection guidance.

WSLg hosts merge `Workspace/compose.wslg.yaml` (no `/dev/dri`). NVIDIA CUDA
inference merges `Workspace/compose.cuda.yaml`. Model weights:
`Workspace/scripts/install-lab-model-cache.bash` (or `.bat`). See
`Workspace/docs/logbook/2026-09-07.md` for the first Windows lab install
deltas.
