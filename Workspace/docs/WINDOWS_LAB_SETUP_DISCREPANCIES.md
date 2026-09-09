# Windows lab setup — discrepancies vs docs (updated 2026-09-09, Tarun-X1)

Source of truth reviewed: `README.md`, `Workspace/docs/SETUP.md`,
`Workspace/LAB_RELEASE`, `install-lab-wsl.{bat,bash}`, `launch-lab-workflow.bat`,
`compose.yaml` / `compose.wslg.yaml` / `compose.cuda.yaml`.

Observed on **Tarun-X1** (Windows 11 + WSL Ubuntu **26.04** named `Ubuntu` +
**docker-ce in WSL** after Docker Desktop OOM; overlay `G:\IITM\Dentobot`;
CUDA RTX 3060). Earlier notes from 2026-09-08 kept and extended.

Companion narrative: `Workspace/docs/logbook/2026-09-09.md` and
`Workspace/docs/logbook/logbook-windows-history.md` (entry 2026-09-09).

## Verdict

Still **not stranger-proof**. The lab path is implementable on this PC
(CUDA check-only green; operator saw Slicer/DENTO Workflow via WSLg), but
defaults, Docker Desktop guidance, post-install automation, and WSLg GL
hardening remain incomplete. `PLAT-U-04` stays open.

## Profile confusion (docs)

| Doc signal | Issue |
|---|---|
| README "Windows 11 + WSL2" | Native Windows Slicer + WSL inference; **Docker not required** |
| SETUP "Windows 11 lab (WSL2)" | Linux Slicer in Docker via WSLg; **Docker required** |
| README still hedges Linux GUI via Docker/WSL2 | Contradicts SETUP `install-lab-wsl` / `launch-lab-workflow` |

**README fix:** One-screen chooser: planning-only (native Slicer) vs lab/ROS
Step 6 (WSLg+Docker). Never mix `launch-dentoworkflow.ps1` vs
`launch-lab-workflow.bat`.

## Hard blockers / wrong defaults

1. **WSL distro name** — bats default `Ubuntu-24.04`. This PC: `Ubuntu` (26.04).
2. **Workspace root hard-coded to `~/dentobot`** — overlay on
   `G:\IITM\Dentobot` is invisible to bats unless `DENTOBOT_WORKSPACE_ROOT`
   is set.
3. **`install-lab-wsl.bash` requires `docker` even with `--skip-docker`**.
4. **Private GHCR image** — needs `read:packages` + `docker login ghcr.io`.
5. **Post-install incomplete** — installer does not create Conda, does not
   download TotalSegmentator 113/115/298, leaves placeholder
   `DENTOBOT_BACKEND_PYTHON`.

## Host stability (Tarun-X1 — hit hard)

6. **Docker Desktop memory balloon** — `com.docker.backend` ~49–63 GB private
   on a 32 GB machine → hard reset / Safe Mode. **Resolution used:** uninstall
   Desktop; install **docker-ce in WSL**; never re-enable Desktop; set
   `%USERPROFILE%\.wslconfig` (`memory`/`swap`/`processors`) before heavy use.
7. Docs had **zero** pre-first-start hardening (`.wslconfig`, Desktop
   MemoryMiB, disable Docker AI, kill autostart Run key).
8. After Desktop removal, fix Docker config if `credsStore: desktop` remains.

## CUDA / inference (added 2026-09-09)

9. CPU pin (Py 3.12 OpenVINO) ≠ GPU Bridge C pin (Py **3.10** +
   `torch==2.10.0+cu130`). Use a separate env (here: `dentobot-cuda`).
10. Launcher pin probe also requires **`pytest==8.4.2`** (easy miss).
11. `DENTOBOT_BACKEND_DEVICE=cuda:0` needs **nvidia-container-toolkit** on
    docker-ce (`could not select device driver "nvidia"` without it) plus
    `compose.cuda.yaml`. Host WSL CUDA via `/dev/dxg` is not enough for the
    container device request.

## Path / graphics / WSLg GUI (added 2026-09-09)

12. Overlay on `/mnt/<drive>/...` — slow/fragile binds; prefer ext4
    `~/dentobot` when possible.
13. No `/dev/dri` on WSLg — use `DENTOBOT_GRAPHICS_MODE=wslg` +
    `compose.wslg.yaml` (`devices: !reset []`).
14. **Taskbar-only / invisible Slicer** is common even when the process is
    healthy (DENTOWorkflow already selected). Hardening that worked here:
    - bind-mount `/usr/lib/wsl` and set `LD_LIBRARY_PATH=/usr/lib/wsl/lib`
    - `XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir` (not `/run/user/1000`)
    - software GL fallback: `LIBGL_ALWAYS_SOFTWARE=1`, `GALLIUM_DRIVER=llvmpipe`,
      `QT_OPENGL=software`
    - restore off-screen windows (`-32000,-32000`) via Show-Window helper
15. Black slice/3D viewports under llvmpipe are **expected** for this lab
    posture (functional UI checks, not render acceptance).
16. Windows `.bat` must not embed bash `${VAR}` — cmd mangles `%`/`:` forms.
    Call a `.sh` helper (`launch-from-windows.sh`).
17. Slicer **pip-as-root** WARNING is Slicer's embedded pip, not a conda failure.

## Doc drift / consistency

18. SETUP body may still mention older image tags; `LAB_RELEASE` pins
    `jazzy-moveit-sim-20260903`.
19. Handoff text says stay on `main` while lab installer detaches to
    `lab/2026-09-03`; this trial also used branch `windows/lab-wslg-cuda`.
20. PLAT-U-04 remains unverified as a clean exportable path.

## What is solid on Tarun-X1 (after fixes)

- Overlay bootstrap + GHCR image pull (with auth fixed).
- docker-ce in WSL + nvidia-container-toolkit + CUDA health in host and
  container.
- `dentobot-cuda` + model cache 298/115/113 + launcher `--check-only` green.
- Operator-visible Slicer with DENTO Workflow (software GL).
- Desktop launchers on `E:\OneDrive\Desktop`.

## Recommended README skeleton (lab) — still needed

1. Prerequisites: Win11, WSLg, distro name policy, **prefer docker-ce in WSL**;
   if Desktop is mentioned, hard-require memory caps **before first start**
   and document Desktop OOM recovery / uninstall path.
2. Verify: `wsl -l -v`, `docker version` **inside** the distro (Server line).
3. GHCR login with `read:packages`.
4. Install overlay; support non-home `DENTOBOT_WORKSPACE_ROOT`.
5. Once per machine: Conda CPU **or** CUDA Bridge C checklist; `.dentobot.env`;
   model cache 113/115/298; nvidia-container-toolkit when `cuda:0`.
6. WSLg GL mounts + software-GL fallback; `--check-only` then GUI launch from
   a real Desktop session.
7. Troubleshooting: Desktop OOM, wrong distro/path, GHCR 403, missing pytest,
   nvidia runtime missing, taskbar-only window / off-screen restore.

## Observed machine notes (not universal)

- Distro `Ubuntu` 26.04; overlay `G:\IITM\Dentobot`; RTX 3060.
- Docker Desktop removed; docker-ce only.
- Desktop = OneDrive `E:\OneDrive\Desktop`.
