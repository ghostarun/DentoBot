# DENTOBOT Tasks

Last reconciled: 2026-09-04

This is the single actionable queue. `DEVELOPMENT_PLAN.md` defines the full
behavior and acceptance contract; this file records only work order and state.

## Now — Track A priority 0 gate

| Order | ID | Priority | State | Next bounded action |
|---:|---|---:|---|---|
| 1 | `S6-LIVE-00` | 0 | Documentation checkpoint recorded; source baseline `ea504349f99f` preserved | Review the bounded source diff, then run the approved static/runtime checks |
| 2 | `S6-LIVE-01` | 0 | Implemented: five-DOF canonical TCP model, exact sequential fixed-frame IK evidence, and full-path-only promotion | Runtime trial must confirm exact first-unsolved pose and 100% FK-verified recovery when available |
| 3 | `S6-LIVE-02` | 0 | Implemented: independent guard remains authoritative for J1–J5; legacy six-value spindle motion is rejected | Runtime trial must confirm every Stage 1/2/3 waypoint, narrow burr exception, and external-spindle boundary |
| 4 | `S6-LIVE-03` | 0 | Implemented: endpoint checks, consumed stop state, guarded Return Home/replan loop, and diagnostic/live-preview overlap guard | Runtime trial must complete Goal 1→Goal 2→Return Home→replan without Slicer restart |
| 5 | `S6-LIVE-04` | 0 | Implemented: timestamp/speed playback, 30 Hz display coalescing, progress UI, static phase paths | Runtime trial must confirm selectable speed preserves ordered acknowledgements and visible paths |
| 6 | `S6-LIVE-05` | 0 | Blocked at Goal 1: current canonical five-DOF TCP has no collision-aware PreEntry IK endpoint in the x4 scene | Diagnose canonical TCP goal/scene/seed mapping; then rerun one complete x4 Home-to-Target-to-Home loop |

### Current Track-A correction checkpoint — 2026-09-04

The bounded kinematic-model correction is implemented across the DentoBot
description, MoveIt configuration, SlicerROS2 FK bridge, Step 6 state/planning
facade, publisher, and C++ phase boundary. `dentobot_arm` now plans J1–J5 to
the fixed upstream `dentobot_drill_tcp`; J6 remains visual/collision-only at
neutral `0 rad`. Legacy six-value records are read as J1–J5 and old
roll-dependent evidence is stale by fingerprint. Focused pure tests, the
SlicerROS2 rebuild, the ROS/MoveIt smoke, and the phase-guard smoke are
complete. The normal-window x4 Home→PreEntry→Entry→Target→Home acceptance,
including Return Home and repeat, is still the only Track-A gate outstanding.
The first post-correction trial started ROS/Slicer cleanly and loaded the x4
case, but stopped before preview because MoveIt returned no collision-aware
PreEntry IK endpoint for the canonical non-spinning TCP. No partial path or
relaxed tolerance was accepted; the next action is focused diagnosis rather
than more retry/sampling tuning. Track B remains blocked.

## Track B — blocked by `S6-LIVE-05`

| Order | ID | Priority | State | Entry condition |
|---:|---|---:|---|---|
| 1 | `S6R-00` | 0 | Planned | Track A accepted |
| 2 | `S6R-01` | 0 | Planned | `S6R-00` |
| 3 | `S6R-02` | 0 | Planned | `S6R-01` |
| 4 | `S6R-03` | 1 | Planned prerequisite | `S6R-02`; implement before evidence studies |
| 5 | `S6R-04` | 2 | Planned | `S6R-03` |
| 6 | `S6R-05` | 0 | Planned | Stable schema, registry, and jaw fingerprint |
| 7 | `S6R-06` | 0 | Planned dependency | `S6R-05` |
| 8 | `S6R-07` | 0 | Planned | `S6R-06` |
| 9 | `S6R-08` | 0 | Planned | `S6R-07` |
| 10 | `S6R-09` | 0 | Planned | `S6R-08` |
| 11 | `S6R-10` | 0 | Planned | Track A accepted and `S6R-09` |
| 12 | `S6R-11` | 0 | Planned | `S6R-10` |
| 13 | `S6R-12` | 0 | Planned | `S6R-11` |
| 14 | `S6R-13` | 0 | Planned | `S6R-12` |
| 15 | `S6R-14` | 0 | Planned | `S6R-13` |
| 16 | `S6R-15` | 2 | Planned | Schema-2 restore and results accepted |
| 17 | `S6R-16` | 0 | Planned | Functional parity and approved acceptance matrix |

## Other active work

| ID | Priority | State | Next bounded action |
|---|---:|---|---|
| `S6-U-01` | 4 | Deferred reliability | Close retained SlicerROS2/MoveIt shutdown objects only after priorities 0-3 or if lifecycle failure again blocks routine work |
| `S6-U-02` | Unprioritized | Physical mount-frame truth unresolved | Obtain mount-face CAD/contact normal; keep the robot-derived forehead plane quarantined |
| `W5-U-01` | Unprioritized | Physical-fit provenance unresolved | Correct/verify guide bore versus burr and never gate Step 6 simulation on STL export alone |
| `VIEW-U-01` | Unprioritized | Representative acceptance pending | Exercise grouped anatomy, presets, toggles, frame/restore, opacity, and repeated load without view side effects |
| `PLAT-U-04` | Unprioritized | Windows WSLg acceptance deferred | Run only when a Windows lab trial is explicitly requested |
| `POC-U-01` | Unprioritized | Strategic parallel lane | Freeze the bounded task and physical acceptance thresholds |
| `UI-P3-01` | 3 | Deferred | Begin only after Studio functional acceptance |

All former `S6-P0-01`, `S6-P0-02`, `S6-P1-01`, and `S6-P2-01..03`
requirements are absorbed into the stable Track A/Track B IDs above. The
former `.dentostudy` F0-F2 sequence is superseded by schema-2 `.dentocase`
studies. Historical evidence remains in dated logbooks, decisions, traceability,
and the task archive.

## Maintenance rules

- Priority is numeric and ascending; recorded prerequisites may execute first.
- Update one stable row instead of duplicating the same task elsewhere.
- No item is successful without recorded verification at the stated evidence
  level.
- Testing/build/runtime work follows `AGENTIC_VERIFICATION_PROTOCOL.md` and
  requires the prescribed explanation and approval.
- No task authorizes hardware motion, powered drilling, patient-facing work,
  collision-policy relaxation, Git publication, or Drive synchronization.
