# Joint-goal planning / collision diagnostic queries — 2026-09-20

Live sources: `DENTOROS2Bridge.py`, `DENTORobotWorkflowFacade.py`, `logic_robot_scene_sync.py`, `vtkMRMLROS2MotionControlNode.cxx`, `vtkMRMLROS2RobotNode.cxx`, `dentobot.urdf`, MoveIt config.

---

## QUERY 1 — What happens inside `plan_moveit_joint_goal()`?

### Call chain (Goal 1 Home → PreEntry)

`planApproachPhase()` invokes (`DENTORobotWorkflowFacade.py:4733-4742`):

```python
candidate_plan = self._bridge.plan_moveit_joint_goal(
    start_joint_positions_si=home_positions,
    goal_joint_positions_si=candidate["positions"],
    refresh_planning_scene=(candidate_index == 0),
    planning_attempts=1,
    allowed_planning_time_sec=GOAL1_DIRECT_PLANNING_TIME_SEC,  # 5.0 s
    planner_context="task_home_to_preentry_" + route_type,
)
```

### Execution trace

| Step | file:line | function | input → output | notes |
|------|-----------|----------|----------------|-------|
| 1 | `4545:4566` | `plan_moveit_joint_goal` | explicit start+goal mappings | `attempt_count=1`, `allowed_time=5.0` for Goal 1 |
| 2 | `4567:4572` | `_dentobot_native_motion_context` | — | requires SlicerROS2 motion node |
| 3 | `4583:4586` | `moveit_joint_goal_diagnostics` | Task Home, PreEntry IK goal | canonicalizes continuous revolute wraps; yields `submitted_start`, `submitted_goal` |
| 4 | `4617:4634` | equal start/goal guard | per-joint deltas | **FAIL** if Home≈PreEntry within monitored tolerances |
| 5 | `4668:4684` | `logic.RefreshMoveItPlanningScene` | first candidate only | 0.75 s settle loop when `refresh_planning_scene=True` |
| 6 | `4688:4718` | `motion_node.PlanMoveItTrajectoryFromState` | group, joint names, start[5], goal[5], vel=0.2, acc=0.2, time=5.0 | explicit-start OMPL plan |
| 7 | `4728:4732` | `GetLastJointPlanMessage` | native C++ status string | |
| 8 | `4732:4759` | `_moveit_trajectory_result` | trajectory | parses joint trajectory waypoints |
| 9 | `4760:4807` | retry / failure wrap | — | Goal 1 uses `planning_attempts=1` → single attempt |

Native OMPL entry (`vtkMRMLROS2MotionControlNode.cxx:185-302`):

| Step | line | action |
|------|------|--------|
| A | `219` | `MoveGroupInterface moveGroup(node, groupName)` |
| B | `252-264` | build `RobotState` from **submitted** start joints; bounds check |
| C | `266-270` | `setMaxVelocityScalingFactor(0.2)`, `setMaxAccelerationScalingFactor(0.2)`, `setPlanningTime(5.0)` |
| D | `271` | `moveGroup.setStartState(startState)` — **not** current monitored state |
| E | `273-276` | `setJointValueTarget` map of 5 joint names → goal values |
| F | `285-286` | `moveGroup.plan(plan)` → OMPL |
| G | `287-291` | SUCCESS → cache trajectory + VTK conversion |

### Answers (Goal 1 Home → PreEntry)

| # | Question | Answer | Evidence |
|---|----------|--------|----------|
| 1 | Ultimate MoveIt API | `moveit::planning_interface::MoveGroupInterface::plan()` via `PlanMoveItTrajectoryFromState` | `cxx:285-286` |
| 2 | OMPL vs interpolation | **OMPL only** for the plan. Joint interpolation is **not** used inside `plan_moveit_joint_goal`. Separate `diagnose_moveit_joint_segment` runs only **after** OMPL failure in `planApproachPhase` | `4745-4754`, `1852-1856` |
| 3 | Planner pipeline | `ompl` (`planning_plugins: ompl_interface/OMPLPlanner`) | `ompl_planning.yaml:1-2`, `simulation.launch.py:21` |
| 4 | Planner ID | **`RRTConnectkConfigDefault`** (group default; no `setPlannerId` in native code) | `ompl_planning.yaml:15-21`; only config listed for `dentobot_arm` |
| 5 | Planning time | **5.0 s** (`GOAL1_DIRECT_PLANNING_TIME_SEC`) | `Facade:74,4738`; passed to `setPlanningTime` `cxx:270` |
| 6 | Planning attempts | **1** per route (`planning_attempts=1`) | `Facade:4737`; bridge default would be 3 (`ROS2_MOVEIT_JOINT_PLAN_ATTEMPTS`) but Goal 1 overrides |
| 7 | Start state source | **Explicit submitted Task Home** joint vector (`home_positions` / `submitted_start`), not MoveIt current state | `cxx:271`; `planner_context=task_home_to_preentry_*` |
| 8 | Goal representation | `std::map<std::string,double>` joint value target for 5 planning joints | `cxx:273-276` |
| 9 | Path constraints | **None** supplied | no `setPathConstraints` / pose constraints in `PlanMoveItTrajectoryFromState` |
| 10 | Orientation/TCP constraints during Home→PreEntry | **None** — joint-space goal only; no TCP/orientation constraints | joint `setJointValueTarget` only `cxx:273-276` |
| 11 | Collision checking enabled | **Yes** — OMPL plans in MoveIt PlanningScene; request adapters include `CheckStartStateCollision` | `ompl_planning.yaml:7`; default MoveIt collision-aware planning |
| 12 | Arbitrary curved joint-space path | **Yes** — RRTConnect free-space joint planning | OMPL geometric planner `ompl_planning.yaml:16` |
| 13 | Failed straight interpolation vs OMPL order | Interpolation diagnosis runs **after** OMPL fails, not before | `4745-4754` calls `diagnose_moveit_joint_segment` only when `not candidate_plan.success` |
| 14 | Success/failure returned to `planApproachPhase` | **Success:** `MoveItCartesianResult.success=True`, non-empty trajectory with all `ROS2_JOINT_SI_ORDER` joints, start≠goal (`2030-2051`, `4508-4542`). **Failure:** empty/unreadable trajectory, missing joints, equal start/goal, native `MoveItErrorCode!=SUCCESS`, or exception — wrapped message with `native_planner_message` | `4732-4759`, `4799-4807`, `cxx:293-297` |

### Failure propagation in `planApproachPhase`

When all routes fail (`5105-5149`):
- Returns `RobotActionResult(False, "approach_start_goal_plan_failed", …)`
- Appends `direct_segment.message` from `diagnose_moveit_joint_segment(home, best_candidate["positions"])`
- Includes `planFailures` list per route with `nativePlannerMessage`, `message`, collision fraction from segment when present

---

## QUERY 2 — The 30.2% collision diagnostic

### Source function

`DENTOROS2Bridge.diagnose_moveit_joint_segment()` (`1846-1932`).

Invoked from `planApproachPhase` **only when** `plan_moveit_joint_goal` returns `success=False` (`4745-4754`, and clearance second leg `4932-4940`).

### Diagnostic algorithm

| Item | Detail | Evidence |
|------|--------|----------|
| 1 | Generator | `diagnose_moveit_joint_segment` | `1846` |
| 2 | Sample count | `interval_count = max(1, min(max(per-joint intervals), 720))`; `sample_count = interval_count + 1` (max **721** samples) | `1887-1888`, `maximum_samples=721` default `1850` |
| 3 | Interpolation model | **Independent linear interpolation per joint** in `ROS2_JOINT_SI_ORDER` | `1891-1894`: `start[name] + (goal[name]-start[name])*fraction` |
| 4 | Collision API | `robot_node.GetMoveItCollidingBodyPairs(ROS2_PLANNING_GROUP, values)` → MoveIt `PlanningScene::checkCollision` | `1896-1898`, `cxx:1175-1190` |
| 5 | Role of result | **Diagnostic only** — explicitly not a plan, not a hard gate before OMPL | `1852-1856`, `1922-1924` |
| 6 | OMPL when interpolation collides? | **Yes — OMPL already ran.** Interpolation runs **after** OMPL failure | `4745-4754` order |
| 7 | Origin of `30.2%` | `fraction = sample_index / interval_count`; message `f"{fraction * 100.0:.1f}%"` | `1890`, `1913-1914` |

Example: `30.2%` ⇒ `fraction ≈ 0.302` ⇒ e.g. `sample_index=217`, `interval_count=719` → `217/719×100 = 30.2%` (first colliding sample along the straight joint chord).

### Message template

```python
"The direct Task-Home-to-goal joint interpolation first "
f"collides at {fraction * 100.0:.1f}%: {first_pair}. "
"This does not rule out a curved collision-free plan."
```

(`1912-1916`)

---

## QUERY 3 — Route types: `direct`, `seeded`, `clearance-detour`

### Route taxonomy

| Route type | Joint waypoints | Source | OMPL calls | Manual geometry? | Why exists | Max attempts | Rejection |
|------------|-----------------|--------|------------|------------------|------------|--------------|-----------|
| **`direct`** | Task Home → PreEntry IK (one segment) | IK seed = Task Home (`route_type="direct"`, `seedSampleIndex=None`) | **One** `plan_moveit_joint_goal(Home, PreEntry)` | No — OMPL joint path | Default Stage-1 path from confirmed Task Home | Up to **14** IK/plan pairs (`GOAL1_MAX_PLANNED_IK_CANDIDATES`) | OMPL failure; or chain preflight failure after success |
| **`seeded`** | Same structure, different PreEntry goal | IK seed = HomeConnected 6.3 sample (`route_type="seeded"`, `seedSampleIndex=N`) | **One** OMPL Home→PreEntry per candidate | No | Alternative arm branches from bounded 6.3 evidence | Shares 14 cap with direct | Same as direct |
| **`clearance-detour`** | Home → 6.3 clearance posture → PreEntry | Waypoints from `accepted_sample_evidence` ranked by `_goal1_clearance_waypoints` | **Two** OMPL legs + `_merge_goal1_joint_plans` | No manual Cartesian path — only **reused joint states** from 6.3 | Fallback when direct Home→PreEntry OMPL fails but other endpoints exist | Max **3** clearance samples (`GOAL1_MAX_CLEARANCE_WAYPOINTS`); only entered when no complete direct route or operator locked clearance route (`4872-4879`) | Either leg OMPL fails; or `_goal1_candidate_chain_preflight` fails |
| **6.3 retained samples (IK only)** | Not a separate route label — feeds `seeded` IK | `step6AssistedLimitProposalJson.accepted_sample_evidence` | Used as IK seeds / clearance states, not as published path geometry | No | Branch exploration envelope | Bounded by `WORKSPACE_HOME_CONNECTIVITY_MAX_SAMPLES=13` + 1 direct | Invalid if not `HomeConnected` or wrong joint count |

### Diagnostic stage labels

- `task_home_to_preentry_direct` — direct/seeded OMPL leg (`4758`)
- `clearance_to_preentry` — second leg of detour (`4945`)

### Plain OMPL Home→PreEntry without custom detours?

**YES**

The `direct` route is exactly one explicit-start OMPL joint plan from Task Home to a collision-aware PreEntry IK goal with no intermediate waypoints (`4733-4742`). Custom detours (`clearance-detour`) are **optional fallbacks** only when direct/seeded OMPL routes fail or operator selects clearance (`4872-4883`).

Evidence:

```python
# Direct route — single OMPL call, no detour
candidate_plan = self._bridge.plan_moveit_joint_goal(
    start_joint_positions_si=home_positions,
    goal_joint_positions_si=candidate["positions"],
    ...
)
```

(`4733-4742`)

Clearance block is guarded: `if not any(route["chain"]["status"] == "Complete" for route in planned_candidate_routes) or preferred clearance route` (`4872-4879`).

---

## QUERY 4 — Colliding tooth object `dentobot_tooth_2.25.295747131114371335249908164658761923371_2a6f6202`

### Naming contract (source)

Non-target teeth (`logic_robot_scene_sync.py:934-939`):

```python
sourceName = "dentobot_tooth_" + re.sub(
    r"[^A-Za-z0-9_.-]+", "_", str(segmentId)
) + "_" + fingerprint(str(segmentId))[:8]
sourceRole = "non-target-tooth"
```

Target tooth uses separate prefix (`930-933`, `logic_robot.py:69-75`):

```python
return f"dentobot_target_tooth_{segment_id}"  # no fingerprint suffix
```

### Trace table

| # | Field | Finding | Evidence |
|---|-------|---------|----------|
| 1 | FDI tooth number | **Not determinable from object ID alone** — requires runtime `DENTOBOT.FDINumber` segment tag on `parameterNode.teethSegmentation` | `logic_step6_scene.py:255` sets tag; not embedded in MoveIt object name |
| 2 | Target vs adjacent | **`non-target-tooth`** role ( `dentobot_tooth_*` prefix, not `dentobot_target_tooth_*`) | `logic_robot_scene_sync.py:934-939` |
| 3 | Original segmentation node | `parameterNode.teethSegmentation` segment ID **`2.25.295747131114371335249908164658761923371`** | embedded in object name; `source_id = f"{segmentation.GetID()}:anatomy:{segmentId}"` `935` |
| 4 | Transform to MoveIt | World RAS surface → jaw transform if moving lower → `base_link` mm vertices; identity CollisionObject pose (vertices pre-transformed) | `910-914`, `995-998`, `1045-1048` |
| 5 | Mesh source | Segmentation closed surface from `_segmentationSegmentsSurfaceWorld` (or reviewed proxy if active) | `876-904`, `915-921` |
| 6 | Expected in Step-6 scene? | **Yes** — all jaw anatomy segment IDs are published during `syncStep6MoveItPlanningScene` | `872-962` |
| 7 | Duplicate copies? | One published obstacle per `source_id`; stale proxies removed; separate **audit display** copy (`DENTOBOT.CollisionAuditCopy`) not a second MoveIt obstacle | `964-965`, `1054-1066`, `5351-5366` |

Published via `sync_moveit_obstacle_polydata(source_name=sourceName, polydata_base_mm=…)` (`1062-1066`).

---

## QUERY 5 — Spindle collision vs visual geometry (`pneumatic_spindle-Copy`)

URDF: `dentobot_description/urdf/dentobot.urdf`

### Link `pneumatic_spindle-Copy` (lines 102-119)

| # | Item | Visual | Collision |
|---|------|--------|-----------|
| 1 | Geometry type | `mesh` `pneumatic_spindle-Copy.stl` | same |
| 2 | Origin xyz (m) | `0.05494618457295404, -0.008269433599944023, 0.032342388899358164` | **identical** |
| 3 | Origin rpy (rad) | `0.44718022829377824, 1.1053864680655217, 3.141592653589792` | **identical** |
| 4 | Scale | `0.001 0.001 0.001` (mm→m) | **identical** |
| 5 | Bounding size (STL, scaled) | ≈ **63 × 12.5 × 13.6 mm** (axis-aligned, mesh-only) | same mesh ⇒ same bounds |
| 6 | Visual vs collision origins identical? | **Yes** — same `<origin>` on both | `108-115` vs `114-118` |
| 7 | Intentionally inflated collision? | **No** in URDF — same mesh file and transform | `111-117` |
| 8 | J5 → spindle collision transform | Joint `link-5_Revolute-5`: origin xyz `(-0.02175, -0.00676, 0.00730)` m, rpy `(-2.933, -1.553, 2.926)`; parent `link-5`, child `pneumatic_spindle-Copy` | `185-190` |
| 9 | Spindle → `dentobot_drill_tcp` | Fixed joint `pneumatic_spindle-Copy_to_dentobot_drill_tcp`: xyz `(0.041042, -0.000048, 0.042854)` m, rpy `(-2.225, 0.843, -2.583)`; **`dentobot_drill_tcp` has no collision geometry** (empty link) | `219-225` |

### Other bodies on spindle branch

| Link | Collision? | Notes |
|------|------------|-------|
| `burr` | Yes — `burr_simulation_1mm.stl` | child of J6 (`192-141`) |
| `dentobot_tool_tcp` | No geometry | fixed to burr |
| `dentobot_drill_tip_provisional` | No | downstream visual tip |
| `dentobot_drill_tcp` | No | planning TCP link; collision uses upstream `pneumatic_spindle-Copy` / `burr` meshes in full robot model |

MoveIt planning group chain ends at `dentobot_drill_tcp` (`dentobot.srdf:3-4`) but collision checking uses full robot link meshes including `pneumatic_spindle-Copy` and `burr`.

---

## Query text (saved verbatim)

### QUERY 1
Inspect `plan_moveit_joint_goal()` and helpers until MoveIt returns — report API, OMPL vs interpolation, pipeline, planner ID, time, attempts, start/goal, constraints, collision, curved paths, interpolation ordering, success/failure to `planApproachPhase`.

### QUERY 2
Trace diagnostic `"The direct Task-Home-to-goal joint interpolation first collides at …"` — function, samples, interpolation model, collision API, diagnostic vs rejection, OMPL ordering, 30.2% origin.

### QUERY 3
Trace `direct`, `seeded`, `clearance-detour`, 6.3 routes in `planApproachPhase` — waypoints, sources, OMPL usage, manual geometry, purpose, max attempts, rejection; answer plain OMPL without detours YES/NO.

### QUERY 4
Trace `dentobot_tooth_2.25.295747131114371335249908164658761923371_2a6f6202` vs `pneumatic_spindle-Copy` — FDI, anatomy role, segmentation source, transform, mesh, expected in scene, duplicates.

### QUERY 5
Audit URDF `pneumatic_spindle-Copy` visual vs collision geometry, transforms, inflation, TCP chain, duplicate collision bodies.
