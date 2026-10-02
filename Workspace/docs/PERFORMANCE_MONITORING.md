# Permanent workflow performance and reliability monitoring

Operator direction: 2026-10-01. Current scope is the accepted SlicerROS2 5.10 container and DENTOBOT workflow on native Ubuntu. Windows/WSL/WSLg checks require a distinct environment-specific campaign and separate evidence.

## Ownership and records

Use the existing `S6-P2-03` performance task, `S6-U-01` lifecycle task and relevant workflow IDs. `backlog.md` is the sole bug/performance pending queue; `TASKS.md` holds contracts and accepted results; dated logbooks hold commands, measurements and dispositions. Do not create a second issue queue. Local raw evidence lives under `/home/light-tarun/dentobot/data/dentobot-runs/ui-watchdog`; use the configured data root on other hosts. Retain run/source/image/native-module/machine identities with comparisons. Never commit patient data or raw sensitive stacks.

## Standing quality check

For each already-authorized representative runtime or release check, confirm the existing UI and external resource watchdogs are enabled and producing records. Review workflow phase timings, progress and cancellation, event-loop gaps, session start/end, actual exit status, exceptions/crash evidence, CPU/RSS/thread/FD trends, child-process/zombie cleanup, host available RAM/swap/disk, and cgroup OOM/throttling/CPU-memory-I/O pressure. Record unavailable metrics as unavailable. A UI-only log cannot exclude resource pressure; an absent alert cannot prove absence of leaks. Compare repeated equivalent runs and idle/recovery baselines before claiming a leak or speed gain.

For an actionable anomaly, record UTC timestamp (and local offset when useful), workflow action, revision/runtime identity, expected/observed behavior, measurements, first causal stack/function if available, evidence boundary, retry count and one bounded next action in the existing task/logbook. Deduplicate repeated reports and follow the cheapest-sufficient-check protocol. A recovered phase label may be stale; correlate stacks and explicit phase boundaries before attributing a long gap. Runtime PASS, clean teardown and operator visual acceptance remain separate results.

## Monitor safety and escalation

Read-only log review does not authorize starting Slicer, ROS, MoveIt, planner or hardware. Preserve current task-specific approvals, serialized runtime and S6-LIVE-01 verdict/retry rules. Do not change collision, geometry or eligibility policy to improve timing. Do not run MRML/VTK operations on Python worker threads without verified ownership. PLAT-U-06/5.12 remains indefinitely deferred until explicit approval.

The 2026-09-30 r18 GDB evidence implicated scheduled Python traceback dumping while the GUI rendered. Preserve the newer UI watchdog implementation that no longer schedules dumps; never restore the old faulthandler timer as a monitoring default. Use approved external/native capture only when needed. Watchdog overhead and its own failures are quality issues too.

Daily approved log review stays quiet for unchanged/non-actionable evidence and reports meaningful anomalies without identifiers or raw stack paths. The existing `dentobot-ui-stall-evidence-review` automation remains the recurring reviewer; no duplicate scheduler is required.

## Evidence handoff and remaining scope

Accepted 5.10 performance work includes progress for long actions, rendering/refresh batching, Step 2 inventory/hydration guards and saved-pose precision restoration. The focused Step 5B desktop run passed current watertight shell/template, live progress, unchanged case hash and clean exit; Tarun confirmed the completion capture. Two same-host copy/buffer load pairs reduced segmentation fingerprint time from 4.328/4.372 to 3.618/3.630 seconds and full load from 15.239/14.956 to 14.265/14.336 seconds, with strict lineage and VALID pose. These are scoped results, not universal guarantees.

Later renovation runs showed recurring robot-load, collision-acknowledgement and Task Home connectivity gaps; their root causes and current fix state must be reconciled against the newest Step 6 evidence before another correction. Long gaps with stale case-load labels are not proof of case validation failure. The r18 watchdog correction supersedes old stack-dumping advice. Final Step 6 acceptance, crash/connected lifecycle and capable-GPU >=60 presented FPS/frame pacing remain governed by their existing tasks. GPU-host evidence must include actual renderer, device/VRAM, viewport, scene and responsive input; CPU/llvmpipe diagnostics cannot establish it.


## 1 October — permanent performance-monitoring chat ownership

Operator confirms consolidation completed and assigns Performance upgrades chat permanently to container/DENTOBOT runtime performance monitoring and periodic bounded corrections. Current development target is DentoBot-step6-5.10-integration / integration/step6-5.10-reviewed-20260927. Use existing S6-P2-03 and S6-U-01, backlog as sole queue, and PERFORMANCE_MONITORING.md as standing policy. This supersedes older renovation-routing/transfer-pending summaries; source consolidation does not imply runtime acceptance. Existing daily reviewer remains; do not create duplicate monitoring jobs.

Collector capability verified by reading Workspace/scripts/dentobot-resource-watchdog.py: default five-second sampling, container-visible process RSS/CPU/threads/FDs and zombies, host/Linux-kernel MemAvailable/SwapFree/load/CPU-memory-I/O PSI, cgroup memory/OOM/CPU-throttle/PID/pressure, and free capacity on the log filesystem. It does not collect disk byte throughput/device latency/utilization, paging/swap-in/out rates, all-host process attribution, GPU/VRAM, or Windows host resources outside the WSL kernel. Shorter-than-sample spikes can be missed. Resource correlation supports investigation but does not alone prove the blocking call or leak. Preserve this evidence boundary in future reviews.

## Performance environment scope — operator direction 2026-10-01

Current container/DENTOBOT performance diagnosis, watchdog improvements and acceptance target **native Ubuntu** on the consolidated integration checkout. Attribute host RAM, swap, disk/I/O, CPU and graphics measurements to that Ubuntu workstation and record its hardware/runtime identity. Do not generalize native Ubuntu results to Windows/WSL/WSLg.

Windows/WSL performance verification is a separate later environment-specific campaign under existing platform owners. Adapt collection and checks to Windows host resources, WSL VM memory/swap limits, filesystem boundaries and WSLg/GPU presentation; retain separate baselines and acceptance evidence. Cross-platform support remains intended, but it does not expand the current Ubuntu investigation. Reuse existing tasks and monitoring infrastructure; no new queue, runtime authorization or change to the indefinite 5.12 hold.



## Increment 1 capability update — 1 October 2026

This supersedes the earlier same-day counter inventory: source now includes paging/major-fault rates and per-device disk throughput/I/O-time counters, cgroup io.stat and sampler collection duration. Default sampling remains five seconds, so shorter spikes can still be missed. Kernel counters may cover the Ubuntu host while process/cgroup visibility remains container-scoped. No privileged host agent or GPU counter was added. Device-mapper and partitions are reported individually; never sum them as independent physical disks. Interpret timing fields using the [Linux kernel I/O statistics documentation](https://docs.kernel.org/admin-guide/iostats.html).

Correlate session UUIDs across SESSION_METADATA and MONITOR_START. UI action tokens and Idle/parent restoration supersede stale completed-load phase attribution for shared WorkflowProgress users. Unscoped legacy phase callers and native blocking calls still need evidence; instrumentation alone does not make those calls responsive. Source-file digest/revision are provenance with stated boundaries, not a loaded-binary attestation. Source and 26 host checks passed; paired real-session identity, native teardown and measured sampling overhead remain pending under S6-P2-03/S6-U-01.


## Native Ubuntu NVIDIA profile evidence boundary — 1 October 2026

Profile source/config tests use mocked driver and Docker responses and do not establish GPU access. The optional rendering probe retains software-renderer flags, viewport pixels, EndEvent interval statistics and Qt heartbeat timing; these are forced-render proxy measurements, not presented FPS. Hardware validation is deferred on the current GPU-less workstation at the operator's direction. No GPU sampler/runtime, driver installation or container recreation is performed in this source port. Future GPU quality checks remain under S6-P2-03 and the existing >=60FPS acceptance contract.


## 3 October — watchdog coverage for harness runtimes and evidence-driven culprits

Evidence base (24 Sep – 2 Oct 2026, native Ubuntu, 314 UI logs, 38 sampler logs, 46 faulthandler dumps): 20 of 46 stall dumps had the Qt main thread inside `DENTOROS2Bridge._wait_for_task_command_result` (a 100 Hz `Spin()`/`processEvents()` poll, 6 s timeout per waypoint) reached from `planApproachPhase`; 5 were `workflow_progress.update` from `generateWorkspaceCloud`. Stalls of 5 s or more were 2.5x more likely under host IO/memory-pressure samples, but about 98% of samples were low-pressure, so most stalls are CPU- or wait-bound inside Slicer. Harness runs (`run-in-container.bash`, gdb-wrapped Slicer) start the sampler directly, so all 38 of their sampler logs had null session/checkout/revision and could not be joined to UI logs.

**Resource sampler** (`Workspace/scripts/dentobot-resource-watchdog.py`)
- `MONITOR_START` now carries `run_id` (`--run-id`, `DENTOBOT_RUN_ID`, else the run directory name; shared log directories give none) and `metadata_source` (`launcher` or `sampler_derived`). Without launcher metadata the sampler derives session id, checkout, revision and dirty flag from its own checkout, so a directly started sampler is never anonymous.
- New alerts (previously only cgroup memory/PIDs and log disk, none of which can fire with `memory.max=max`): host MemAvailable < 2 GiB, swap used >= 75%, memory PSI full avg10 >= 5, IO PSI full avg10 >= 20, CPU PSI some avg10 >= 80, load >= 2x CPUs, swap in+out >= 20 MiB/s, zombie present, sample gap > 2x interval, Slicer RSS >= 5 GiB, Slicer RSS growth >= 1 GiB in 2 min. Thresholds come from the evidence above and are constants at the top of the script.
- New fields: `slicer` summary (pid, state, RSS, `vm_swap_mib`, threads, FDs, CPU, `major_faults`), per-process `vm_swap_mib`/`major_faults`, `host_mem_total_kib`, `host_swap_total_kib`.
- A zombie parent now ends sampling (previously an unreaped parent kept it running).

**In-Slicer UI watchdog** (`dentobot_workflow/ui_stall_watchdog.py`)
- `UI_LATENCY`/`UI_STALL_RECOVERED` gain `main_cpu_seconds`, `main_cpu_fraction`, `blocked_hint` (`cpu_bound` >= 0.7, `waiting` < 0.2, else `mixed`; a hint, not proof), `main_state`, `process_cpu_seconds`, `major_faults_delta`, `rss_mib`, `swap_mib`, `threads` and host `host_mem_available_mib`, `host_swap_free_mib`, `host_psi_mem_full_avg10`, `host_psi_io_full_avg10`.
- `UI_STALL_ACTIVE` / `UI_STALL_ONGOING` (every 30 s) are written by a daemon thread while a stall is still running, so a hang that never recovers leaves evidence. The thread reads only `/proc` and Python state and writes one line; no traceback, no Qt/MRML access (the r18 finding stands). It is silent while a native call holds the GIL; the external GDB capture remains the tool for those. `DENTOBOT_UI_WATCHDOG_ACTIVE=0` disables it.
- `ACTION_END` adds `max_gap_seconds`, `stalls`, `stalled_seconds`, `waits`, `wait_seconds`, `wait_max_seconds`, `wait_timeouts`. `SESSION_END` adds session totals and peak RSS/swap. `UI_SUMMARY` adds `rss_mib`, `swap_mib`, `threads`, `fds`, so the last minute before a crash is in the log even without the sampler.
- `ui_wait(kind, label)` times a synchronous UI-thread wait and logs `UI_WAIT` (>= 1 s or any non-ok outcome, at most 500 lines per session). `_wait_for_task_command_result` is wrapped with it (`kind=task_command_result`, `label=<phase>`, `outcome=timeout` when the 6 s budget expires).
- `SESSION_METADATA` adds `run_id` (from `DENTOBOT_RUN_ID` or the parent of `DENTOBOT_HEADED_EVIDENCE_DIR`, so it equals the sampler's), `graphics_environment` (software-GL/driver/Qt-platform variables) and `cpu_count`.

Join key: sampler `MONITOR_START.run_id` = UI `SESSION_METADATA.run_id` for harness runs; time overlap does the rest.

**Still-unrecorded information that would help (not implemented)**: per-waypoint index/total and the ROS node's own service latency for the task-command round trip (separates a slow `collision_guard` from the Qt poll); renderer identity (`GL_RENDERER`, llvmpipe thread count) read once from VTK on the main thread; `stack.log` lines carry no wall-clock time, so they cannot be aligned with UI gaps; the constant `[FATAL] trajectory_execution_manager ... moveit_controller_manager not specified` (98 occurrences across 98 `stack.log` files) and the repeated time-optimal-trajectory warning (62 in r16 alone) drown real `move_group` errors, so a reviewer filter or an explicit fake controller is worth deciding; gdb crash captures lack Slicer's last `UI_SUMMARY` and active phase.
