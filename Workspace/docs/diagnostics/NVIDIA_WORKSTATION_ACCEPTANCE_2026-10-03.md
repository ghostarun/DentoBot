# NVIDIA workstation acceptance — 3 October 2026

Owner: existing `S6-P2-03` (Priority 1); local handoff overlap `PLAT-U-07`.
Matrix: `runtime.ubuntu_nvidia_render_acceptance`; protocol:
[AGENTIC_VERIFICATION_PROTOCOL.md](../AGENTIC_VERIFICATION_PROTOCOL.md).
This is the executable checklist for that existing backlog item, not a new queue.

## Machine and evidence already verified

- [x] Native Ubuntu destination `/home/tarun/dentobot`; X11 desktop, DISPLAY=:0.
- [x] Host GPU: NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB; driver580.178.04.
- [x] NVIDIA Docker runtime listed; current container has NVIDIA GPU requests.
- [x] CUDA inference health passed; this does not prove NVIDIA OpenGL rendering.
- [x] Source main3997458, native ece3c42; matching description/MoveIt/native builds.
- [x] Matrix dependency `pure.ubuntu_graphics_profiles` satisfied by this turn's
  preceding 50 launcher/profile tests, syntax and render-frame self-check.
- [x] Slicer5.10/DENTOWorkflow already launched and remains open in Mesa mode.

## Approval and input checklist

The operator requested pending NVIDIA testing, a launch and an approval checklist.
Read-only prerequisites and checklist preparation proceed now. Before replacing
the existing session, obtain its save/close confirmation and the exact approved
synthetic/de-identified `.dentocase` under `/home/tarun/dentobot/data/`.
These are required inputs, not implied by elapsed time.

- [ ] Confirm current scene is saved and allow normal closure/restart; never
  terminate or replace unsaved/operator-owned state.
- [ ] Name approved case and record its SHA256; original bytes remain unchanged.
- [ ] Approve one NVIDIA preflight, one real-display 5-second render probe,
  normal NVIDIA relaunch and scoped shutdown inspection. Switching mode may
  recreate the dedicated container to apply NVIDIA graphics capabilities;
  existing image/native source stays fixed. No image rebuild/dependency install.
- [ ] Separately confirm the operator's simulation-only Step6 trial when ready.
  No automated planner/full-cycle run follows from a render probe.

## Bounded execution

1. Close current Slicer normally after save confirmation; let its launcher
   clean up its stack/watchdog/X11 access. Verify owned processes are gone.
2. Preserve the previous graphics setting. Set only
   `DENTOBOT_GRAPHICS_MODE=nvidia` in local `.dentobot.env`; retain backend CUDA
   configuration and all other settings. Record the exact config delta.
3. From `/home/tarun/dentobot`, run `./launch-dentobot --check-only`. Expect
   host driver/runtime/container-GPU checks, backend health and package checks
   to pass. No launch on a failed prerequisite.
4. Run `./launch-dentobot --render-probe /home/tarun/dentobot/data/APPROVED_CASE.dentocase`
   with the supplied real path. This loads the named case, measures5seconds of
   display rendering and Qt heartbeats, exits and writes
   `data/dentobot-runs/render-probe-<UTC>/{slicer-probe.log,verdict.json}`.
5. Inspect verdict and process teardown. Require complete probe, loaded case,
   real display, hardware NVIDIA renderer and median render interval<=17.0ms
   (the existing >=60FPS target with VSync tolerance). Record p95/heartbeat
   values and exit separately. A NVIDIA device/CUDA result alone is insufficient.
6. Launch `./launch-dentobot` normally in the same NVIDIA mode, inspect startup
   and leave it open for operator review.
7. Operator reviews a current simulation case: explicit Task Home, Plan Approach,
   guarded preview and Return Home only if a current independently guarded
   complete chain exists. Record no-solution/blocked states truthfully; no
   policy/geometry/limits tuning to force success. Record visual/interaction
   responsiveness and startup/shutdown verdict separately.

## Approval criteria and stopping rule

- [ ] Render verdict PASS with NVIDIA vendor/renderer and<=17.0ms median.
- [ ] Case hash unchanged; source/native/image/config identity retained.
- [ ] Operator Step6 visual/responsiveness verdict recorded.
- [ ] Clean probe teardown observed; normal-session shutdown remains separately
  unverified while left open.

For a measured improvement claim, a separately scoped paired Mesa baseline is
needed on the same case/camera/layout/window size and display settings; renderer
acceptance alone does not quantify speedup. Preserve depth-peeling and other
visual settings. No policy change, Slicer5.12, Windows/WSL acceptance, hardware
motion, drilling, clinical work, case overwrite, external sync or publication.
Stop at the first causal failure and retain logs/verdict. Retry only one
evidence-backed discriminator at a time under the protocol; three failures is
a ceiling, not authorization for three expensive attempts.

## Current result

Prerequisites verified; NVIDIA OpenGL/FPS probe NOT RUN. Awaiting save/close
confirmation and approved case. Existing Slicer session is already open and
was preserved. Runtime/operator acceptance remains in backlog under S6-P2-03.
