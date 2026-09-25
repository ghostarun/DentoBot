# Planner implementation map — collision, three-stage motion, homing

**Date:** 2026-09-20  
**Purpose:** Manual-intervention reference for Step 6 planner work (PreEntry → Entry → Target → Homing).  
**Checkout root:** `/home/light-tarun/dentobot/ros2_ws/src/DentoBot`  
**Workspace root:** `/home/light-tarun/dentobot`

---

## Three-stage model (as implemented)

| UI / diagnostic label | Motion phase | Geometry | Primary planner API |
|---|---|---|---|
| **P1 / Stage 1** (`stage1_free_space`) | Home → **PreEntry** | Free-space joint plan to IK PreEntry pose | `plan_moveit_joint_goal()` |
| **P2 / Stage 2** (`stage2_strict_axis`) | PreEntry → **Entry** | Fixed-axis terminal contact along approach vector | `plan_moveit_cartesian_path()` (PreEntry→Entry) |
| **P3 / Stage 3** (`stage3_drilling`) | Entry → **Target** | Cartesian drilling line | `plan_moveit_cartesian_path()` (Entry→Target) |
| **Homing** | Return to Task Home | Reverse accepted guard history, or plan current→Home | `returnToTaskHome()` / `applyTaskHome()` |

PreEntry is computed as Entry minus `step6ApproachStandoffMm` along the Entry→Target axis (`approach_points()` in `DENTOStep6State.py`).

**Goal 1** (`planApproachPhase`) runs the full chain preflight (Stages 1–3) before committing. **Goal 2** (`planDrillingPhase`) only promotes the Stage 3 plan already validated in that preflight — it cannot replan drilling independently.

---

## Script responsibility table

### Core orchestration (start here for manual fixes)

| Script | Role |
|---|---|
| `DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py` | **Main planner orchestrator.** `planApproachPhase()` (Goal 1 / Stages 1–3 preflight), `planDrillingPhase()` (Goal 2), `previewPhase()`, `returnToTaskHome()`, `saveTaskHome()` / `applyTaskHome()`. Contains `_goal1_pre_entry_ik_candidates()`, `_goal1_candidate_chain_preflight()`, `_prepare_phase_guard()`. |
| `DENTOWorkflow/Resources/Python/DENTOROS2Bridge.py` | **ROS/MoveIt I/O layer.** `plan_moveit_joint_goal()`, `plan_moveit_cartesian_path()`, `solve_moveit_tcp_goal()`, `solve_moveit_tcp_position_axis_goal()`, `configure_task_phase_guard()`, `apply_task_phase_joint_positions()`, `validate_task_phase_waypoints()`, `diagnose_moveit_joint_segment()`, `wait_for_collision_guard_world()`. Does not start ROS processes. |
| `DENTOWorkflow/Resources/Python/DENTOStep6State.py` | **Contracts & fingerprints.** `approach_points()`, Task Home records, motion-diagnostic session (`build_motion_diagnostic_session`, `motion_diagnostic_plan_selection`), collision-audit parsing, J1–J5 planning policy, drill-frame policy (`stage1-position-axis-authoritative-fk-v3`). |
| `dentobot_moveit_config/src/collision_guard.cpp` | **Authoritative collision + phase guard (C++).** `DentobotCollisionGuard`: joint bounds, self/world collision, corridor monotonicity, phased commands (`approach`, `terminal_contact`, `drilling`, `retraction`), burr-to-target contact policy. |
| `dentobot_moveit_config/launch/simulation.launch.py` | **ROS stack launcher:** `robot_state_publisher`, `slicer_joint_state_publisher`, `move_group`, `collision_guard`, `simulation_status_publisher`. |

### Geometry & trajectory inputs (upstream of planning)

| Script | Role |
|---|---|
| `DENTOWorkflow/Resources/Python/dentobot_workflow/logic_robot.py` | `step6ApproachPoints()` — wraps `approach_points()` from confirmed trajectory; offline workspace sampling hooks into `DENTOStep6Planning`. |
| `DENTOWorkflow/Resources/Python/DENTOTrajectoryGeometry.py` | Assisted Entry/Target initialization from tooth surface (Step 4/5 upstream; not live MoveIt). |
| `DENTOWorkflow/Resources/Python/dentobot_workflow/logic_workflow.py` | Maps case-foundation coordinates to planning-frame Entry/Target points. |
| `DENTOWorkflow/Resources/Python/dentobot_workflow/parameter_state.py` | `step6ApproachStandoffMm`, motion-diagnostic JSON, task-home JSON, planning context flags. |
| `DENTOWorkflow/Resources/Python/DENTORobotPlacement.py` | Offline FK / J1–J6 display↔SI conversion; used for placement and native FK cross-checks. |

### Collision scene (must be correct before any plan)

| Script | Role |
|---|---|
| `DENTOWorkflow/Resources/Python/dentobot_workflow/logic_robot_scene_sync.py` | `syncStep6MoveItPlanningScene()` — publishes anatomy/template collision meshes to MoveIt; `collisionSceneAuditRecord()` / freshness checks. |
| `DENTOWorkflow/Resources/Python/dentobot_workflow/logic_step6_scene.py` | Case-jaw geometry, target-jaw selection, landmark evidence for collision-scene validity. |

### Offline / workspace planning (Step 6.3 — not the live three-stage path)

| Script | Role |
|---|---|
| `DENTOWorkflow/Resources/Python/DENTOStep6Planning.py` | Coarse offline planner: `evaluate_motion_configuration()`, `plan_trajectory_motion()`, workspace Halton sampling, URDF-based self-collision gates. Used for 6.3 workspace cloud, **not** the live MoveIt three-stage chain. |

### UI wiring (where you click)

| Script | Role |
|---|---|
| `DENTOWorkflow/Resources/Python/DENTORobotSimulationPanel.py` | Step 6 panel copy; Stage 1/2/3 labels; `showMotionDiagnostics()` dialog (13-leg table). |
| `DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot_shell.py` | Button handlers: connect, save/apply home, plan Goal 1/2, preview, return home. |
| `DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot.py` | Enables/disables plan buttons based on Task Home, workspace, diagnostics freshness. |

### ROS runtime nodes

| Script | Role |
|---|---|
| `dentobot_description/scripts/slicer_joint_state_publisher.py` | Publishes `/joint_states` from guard-validated `/dentobot/validated_joint_positions`. |
| `dentobot_description/scripts/simulation_status_publisher.py` | Publishes `/dentobot/simulation_status` (planning_ready, publisher counts). |
| `slicer_ros2_module/ROS2MotionControl/ROS2MotionControl.py` | Generic SlicerROS2 MoveIt UI (connect, obstacles, generic plan). DentoBot three-stage logic goes through the facade, not this directly. |
| `slicer_ros2_module/ROS2MotionControl/TrajectoryGenerators.py` | Generic joint-space trajectory generators for ROS2MotionControl widget. |

### MoveIt config

| Script | Role |
|---|---|
| `dentobot_moveit_config/config/ompl_planning.yaml` | OMPL planner pipelines for `move_group`. |
| `dentobot_moveit_config/config/kinematics.yaml` | IK solver config. |
| `dentobot_moveit_config/config/joint_limits.yaml` | Joint limit overrides. |
| `dentobot_description/urdf/dentobot.urdf` (+ SRDF) | Robot model including `pneumatic_spindle-Copy` collision geometry. |

### Diagnostics & test runners (for reproducing failures)

| Script | Role |
|---|---|
| `Testing/run_dentobot_step65_exact_case_smoke.py` | Full Step 6.5 exact-case smoke (r13-style); writes stage/first-invalid JSON sidecars. |
| `Testing/run_dentobot_fdi31_recovery_diagnostic.py` | Campaign-1 P1/P2 bounded diagnostic runner. |
| `Testing/run_dentobot_step6_preentry_roll_diagnostic.py` | PreEntry IK roll/candidate sweep diagnostic. |
| `Testing/run_dentobot_step6_geometry_diagnostic.py` | Geometry-only Step 6 checks. |
| `Testing/test_step6_planning.py` | Unit tests for planning contracts, trajectory policy. |
| `Testing/test_robot_workflow_facade.py` | Facade contract tests (phase guard, preflight chain). |
| `Testing/test_ros2_bridge.py` | Bridge parsing, guard topic contracts. |
| `Testing/test_moveit_config.py` | Collision-guard gating behavior. |

---

## Identified blockers (docs + diagnostics)

### 1. Current live session (most urgent — 2026-09-19 logbook)

| Blocker | Evidence |
|---|---|
| **All 13 IK legs fail at P1 (Home→PreEntry)** | Operator on `dentobot-case-step19-step6.dentocase`: GUI works through 6.5, but motion diagnostics never advance to P2/P3 preflight. |
| **Contradicts headless Codex trials** | Campaign-1 P3/P4/P5 ran on locked r4 packages with different evidence level — not the same as this live Goal 1 session. |

**Manual intervention focus:** `DENTORobotWorkflowFacade._goal1_pre_entry_ik_candidates()` → `DENTOROS2Bridge.solve_moveit_tcp_position_axis_goal()` / `plan_moveit_joint_goal()`, plus Task Home match (`wait_for_monitored_joint_positions_si`), workspace validation, and collision-scene audit freshness.

---

### 2. Historical FDI31 r13 (best documented full-chain failure)

| Stage | Result |
|---|---|
| Stage 1 (Home→PreEntry) | PASS |
| Stage 2 (PreEntry→Entry) | PASS |
| Stage 3 (Entry→Target) | **FAIL** at local index 27 |
| First-invalid collision pair | `dentobot_target_tooth_2.25...` vs **`pneumatic_spindle-Copy`** |
| Both IK candidates | Reached exact Target endpoint in preflight, then failed same pair in Stage 3 |

Classification: **`UNKNOWN`** — leading hypotheses `TOOL_COLLISION_MODEL` and `SCENE_CONSTRUCTION` (not proven).

**Manual intervention focus:** `collision_guard.cpp` contact policy for burr vs spindle; URDF/SRDF spindle collision mesh; `_goal1_candidate_chain_preflight()` Stage 3 Cartesian fraction.

---

### 3. Campaign 1 bounded search (headless, Sep 2026)

| Blocker | Status |
|---|---|
| P3 endpoint search (128 seeds) | **0/128 solutions** — `NO VALID TARGET SOLUTION FOUND IN BOUNDED SEARCH` |
| P4 insertion / full workflow | Not run |
| Guard consistency (P2) | **INCONCLUSIVE** — static collision pairs vs phase-guard `validate_only` disagree; scene ack expected 31 objects, observed 0 in one path vs 31 in guard later |
| P1 scene correctness | Machine checks PASS; **operator review INCOMPLETE** |

Source: `Workspace/docs/diagnostics/FDI31_PLANNER_RECOVERY_REPORT.md`

---

### 4. Stage 6 acceptance gates (S6-FINAL-VALIDATION, 2026-09-13)

| Gate | Status |
|---|---|
| Unit / runtime synthetic | PASS |
| **Integration (FDI31 package reopen)** | **NOT ACCEPTED** — failed all 3 cycles |
| **Full-cycle (approach + target + withdrawal + Home + repeat)** | **NOT VERIFIED** |
| **Operator normal-window observations** | **0/10** |

Ordered blockers before any live campaign:

1. Resolve `W5-U-04` / `W5-U-03` FDI31 geometry (4 open bores, zero residual channel, one solid)
2. Current case save + reopen integrity check
3. Fresh PreparedBranch through `4A→4B→4C→5A→5B→5C`
4. Ten normal-window observations
5. Only then: `S6-LIVE-01`–`04` runtime campaign

Source: `Workspace/docs/diagnostics/S6-FINAL-VALIDATION-2026-09-13.md`

---

### 5. Infrastructure / runtime (not root cause, but can stall you)

- `move_group` / `collision_guard` process ownership ambiguous (duplicate publishers, container exited after cleanup)
- Prior `move_group` segfault on shutdown (logged, not proven as planning cause)
- `PLANNER_GUARD_INCONSISTENCY`: diagnostic static collision vs live phase guard mismatch — trust boundary for interpreting failures

---

## Suggested manual intervention order

1. **Collision scene** — `logic_robot_scene_sync.syncStep6MoveItPlanningScene()` + audit fingerprint match (`collisionSceneAuditFreshnessIssues`).
2. **Task Home** — `saveTaskHome()` / `applyTaskHome()`; confirm monitored joints == saved Home before Goal 1.
3. **P1 failure** (current case) — trace `_goal1_pre_entry_ik_candidates()` and first `plan_moveit_joint_goal()` failure per leg in motion-diagnostics JSON (`step6MotionDiagnosticJson`).
4. **If P1 passes but P3 fails** — compare to r13: `plan_moveit_cartesian_path()` fraction + `collision_guard.cpp` first-invalid pair (target tooth vs spindle).
5. **Homing** — only after a complete guarded phase; `returnToTaskHome()` requires `_accepted_motion_history` and `_completed_phase in {approach, drilling}`.

---

## Source records

- [FDI31 Planner Recovery Report](FDI31_PLANNER_RECOVERY_REPORT.md)
- [S6 Final Validation 2026-09-13](../../S6-FINAL-VALIDATION-2026-09-13.md)
- [2026-09-19 logbook](../../../logbook/2026-09-19.md)
- [backlog](../../../backlog.md)
