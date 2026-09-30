# Step 6 meeting demonstration — 29 September 2026

**Checkout:** `DentoBot-step6-renovation`, branch
`feature/step6-workflow-renovation-20260925`. This is a simulation-only
engineering workbench demonstration. Tarun's normal-window robotics/usability
verdict is **PENDING**. Do not imply a working autonomous drilling route or
hardware readiness.

## Suggested 8-minute sequence

1. **Explain the problem (1 min).** The earlier planner-first approach hid
   whether failure came from a hard robot/Base constraint, a selected task,
   collision, IK continuity or the planner. Step 6 now lets the engineer
   inspect valid and invalid robot states and TCP goals before asking a
   planner to solve a full route.
2. **Show the current five-DOF case (1 min).** Open
   `data/Slicer_Saved/SampleStudy1/SEPT24/sept28_fdi11_step6_five_dof_acceptance.dentocase`
   (SHA-256 `d5a0e7bb13ebeda00e5cf9702ce1657f63c074359c833868678805dd854ff090`).
   The fresh-process r16 check passed strict reopen, current FDI11 branch,
   reviewed simulation Base, five-joint saved Home and opened anatomy. Explain
   that reopen intentionally clears live ROS/task confirmation and changes
   Home to `Unreviewed`; do not press Preview from an offline case.
3. **Demonstrate joint exploration (2 min).** In 6.3, use J1–J5 sliders or
   numeric fields to stage a display-only draft; use **Check Draft State** for
   valid/invalid diagnostics. Enable **joint keyboard nudges** and show Q/A,
   W/S, E/D, R/F, T/G with step selection. State that draft changes alone
   never move the accepted simulated robot. The recorded r19 physical-key
   check passed all ten keys, step change, numeric-editor focus, opt-out and
   unchanged accepted/monitored/guard/plan/preview state. For an accepted
   simulation jog, use the separate **Guarded Jog** button; r15 recorded one
   acknowledged +0.1° J1 jog and controlled unknown/reconciliation evidence.
4. **Show Cartesian TCP exploration (1 min).** The 6.3B TCP probe is off by
   default. Explicit **Enable TCP Drag** is required before moving its
   viewport sphere/goal. The bounded no-case headed run captured mouse drag,
   XYZ and drill-axis pitch/yaw nudges, J1–J5 position-axis IK staging and
   probe cleanup. This is ghost review; Solve IK stages a draft and does not
   itself accept a robot motion. Use the recorded screenshots/video if a live
   connected session is not already prepared.
5. **Show Base/Home and evidence (1 min).** Detached Base and Task Home review
   are separate from the accepted robot. The r15 case-bearing run passed
   Base stage/cancel/accept, current-pose Home accept, invalid reviewed-limit
   draft, JSON manual-record export and same-session display-only reopen.
   Fresh `.dentocase` persistence of that record remains deferred; do not
   claim it.
6. **Show planner diagnostics (2 min).** Open the FDI21 RRTConnect diagnostic
   screenshot below. The **Compare Three Planners** workflow exists for
   RRTConnect, RRT and RRT* with frozen identity, timeline, per-row checkpoints
   and display-only records. In the bounded FDI21 r6 campaign, RRTConnect
   completed Approach and PreEntry→Entry, then the independent Stage-3 guard
   rejected waypoint 459 for target-tooth↔spindle collision. Requested
   insertion 8.071 mm exceeded a provisional 6.500 mm envelope. It spent
   about 874 s total, including 813.39 s in eight guard calls. RRT began
   but the 20-minute cap interrupted its second guard; RRT* did not run.
   Thus it diagnosed a real blocker and performance cost, **not** a fair
   three-planner winner. Tarun's separate FDI11 three-row trial stopped all
   three at the shared PreEntry IK prerequisite before path search; this
   likewise cannot rank planners.

## Evidence to open during the meeting

| Topic | Direct artifact | Safe conclusion |
|---|---|---|
| Fresh five-DOF case | `data/dentobot-runs/s6-live-01-five-dof-qualify-20260928T200650Z-r16/diagnostics.md` and `recording/fresh-qualification.mkv` | Strict offline reopen passed; live authority still requires reconnection/review. |
| Case-bearing workbench | `data/dentobot-runs/s6-live-01-five-dof-campaign-20260928T193411Z-r15/diagnostics.md` and `recording/review-and-create.mkv` | 21 enabled checks passed, new case saved; native rejected-jog and full preview not run. |
| Physical keyboard | `data/dentobot-runs/s6-live-01-joint-keyboard-20260928T203130Z-r19/diagnostics.md` and `recording/joint-keyboard.mkv` | Ten physical keys and draft-only authority separation passed. |
| TCP drag | `data/dentobot-runs/step6-tcp-workbench-headed-20260928-9/diagnostics.md`, `video/whole-run.mkv`, `evidence/03-after-mouse-drag.png` | Explicit-enable no-case probe and IK draft staging passed. |
| FDI21 planner failure | `data/dentobot-runs/step65-three-planner-fdi21-31-20260923/fdi21-r6/FDI21-rrtconnect-diagnostic.png`, `timeline.jsonl`, `checkpoint.json` | Real Stage-3 guard blocker; comparison incomplete. |
| FDI11 planner prerequisite | `Workspace/docs/diagnostics/evidence/fdi11-step6-2026-09-24/` | Three rows reached the same PreEntry IK stop; no ranking. |
| Detailed context | `Workspace/docs/diagnostics/STEP6_WEEKLY_UPDATE_2026-09-29.md` | Dated history; its initial runtime-halt and case-not-created statements are superseded by the 29 September logbook and this checklist. |

## What remains open

- Deterministic case-bound native **rejected** jog and uncertain Base/Home
  reconciliation; full record persistence across fresh `.dentocase` reopen.
- Case-bound TCP drag/IK and text-editor keyboard focus in the representative
  normal window, plus measured 60 FPS interaction/responsiveness.
- Positive full-chain guarded Preview, interruption, Return Home and one
  complete representative whole-run recording. Manual/partial paths never
  gain preview authority.
- Tarun's own robotics/usability verdict and later case-specific solver work.

**Live demo safety:** This is a simulation-only setup. If the native stack,
current identity, scene readback or guard acknowledgement is unavailable,
show the complete recorded videos/screenshots instead of improvising planner
or motion actions. Do not connect hardware or operate the drill.
