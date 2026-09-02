# Host overlay layout

`~/dentobot` is not a git repository. Git lives in
`ros2_ws/src/DentoBot` (branch `main`, tracking `origin/main`).

Root shortcuts (symlinks) exist so Ubuntu looks like a normal project:

| You open | Real path |
|---|---|
| `docs/` | `ros2_ws/src/DentoBot/Workspace/docs/` |
| `AGENTS.md` | `ros2_ws/src/DentoBot/Workspace/AGENTS.md` |
| `scripts/` | `ros2_ws/src/DentoBot/Workspace/scripts/` |
| `compose.yaml` | `ros2_ws/src/DentoBot/Workspace/compose.yaml` |
| `tools/` | `ros2_ws/src/DentoBot/tools/` |

`Workspace/` here means the Ubuntu overlay (docs, Compose, launchers). It is
not the Slicer six-workspace UI.

## Source vs local data

- **Product:** `DENTOWorkflow/`, `dentobot_description/`, `dentobot_moveit_config/`, `Testing/`
- **Host tools:** `tools/arduino-pressure/`
- **Upstream ROS/Slicer:** `ros2_ws/src/slicer_ros2_module/`
- **Local only:** `data/`, `slicer-user/`, `ros2_ws/build|install|log/`, overlay `graphify-out/`, pressure `pressure_runs/`
- **Frozen snapshot:** `archive/DentoBot-demo-aff8b2e/` (own git; not on the colcon path)
- **Stale notes:** `docs-legacy/` inside the DentoBot checkout

Recreate the overlay links with `Workspace/bootstrap-workspace.bash`.

## Lab clone layout (Windows WSL2)

Lab PCs recreate this overlay **inside WSL**, never by zipping `~/dentobot`.

```text
~/dentobot/                          # overlay root; not a git repository
  compose.yaml -> ros2_ws/src/DentoBot/Workspace/compose.yaml
  scripts/     -> ros2_ws/src/DentoBot/Workspace/scripts/
  docs/        -> ros2_ws/src/DentoBot/Workspace/docs/
  .dentobot.env                      # local; not in git
  data/                              # local model cache and cases; not in git
  slicer-user/                       # local Slicer settings; not in git
  ros2_ws/
    src/DentoBot/                    # private git; detached lab/* tag
    src/slicer_ros2_module/          # public rosmed git; pinned SHA
    build/ install/ log/             # local colcon products; do not copy
```

Pin file: `ros2_ws/src/DentoBot/Workspace/LAB_RELEASE`.
First-time: `scripts/install-lab-wsl.bash` (or `install-lab-wsl.bat` from Windows).
Updates: `scripts/update-lab-release.bash` (or `update-lab-release.bat`).
Launch: `scripts/launch-dentoworkflow.bash` (or `launch-lab-workflow.bat`).
Do not use `launch-dentoworkflow.ps1` for this profile.
