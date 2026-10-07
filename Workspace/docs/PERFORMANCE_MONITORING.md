# Permanent workflow performance and reliability monitoring

Operator direction: 2026-10-01. Applies to the accepted SlicerROS2 5.10 container and DENTOBOT workflow across Ubuntu and Windows/WSLg hosts.

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
