# PreEntry IK / MoveIt investigation queries — 2026-09-20

Graph root: `/home/light-tarun/dentobot`  
Live sources: `ros2_ws/src/DentoBot/`, `ros2_ws/src/slicer_ros2_module/`  
Scope: implementation evidence only (tests cited only for Query D contract comparison).

---

## Query text (saved verbatim)

### QUERY A — Inspect the actual PreEntry IK implementation, not documentation

Use the exact live source symbols in:

`ros2_ws/src/DentoBot/DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py`

Find and inspect:

* `_goal1_pre_entry_ik_candidates()`
* every function it directly calls for IK generation
* every function it calls for candidate validation/rejection

Trace execution only until a candidate is either ACCEPTED or REJECTED.

For each step report:

`file:line → function → input → output → rejection condition`

I specifically need:

1. Number and names of joints entering the function.
2. Whether every seed is J1–J5 only.
3. Why there are 13 attempts/legs.
4. Whether different attempts represent different joint seeds, TCP roll angles, IK branches, or something else.
5. Exact reason codes capable of rejecting an IK result.
6. Whether any returned MoveIt IK solution can be rejected afterward by custom FK/axis/continuity checks.
7. Whether collision checking occurs before the candidate reaches `_goal1_candidate_chain_preflight()`.

### QUERY B — Exact `solve_moveit_tcp_position_axis_goal()` body

Inspect the complete live implementation of `DENTOROS2Bridge.solve_moveit_tcp_position_axis_goal()` and every helper it directly calls.

Answer exactly: ROS/MoveIt API, planning group, TCP link, frame ID, seed joint names/dimensionality, J6 handling, task representation, roll construction, tolerances, timeout/attempts, success/failure criteria, post-IK FK validation.

### QUERY C — Verify the authoritative MoveIt chain

Inspect SRDF, `kinematics.yaml`, `joint_limits.yaml`, launch/config. Return authoritative Step-6 MoveIt group configuration and verdict.

### QUERY D — Compare intended five-constraint IK vs current implementation

Compare logbook 2026-09-04, `test_stage1_uses_every_bounded_home_connected_seed_without_j6()`, `spindle_is_locked()`, and live implementation.

---

## QUERY A — PreEntry IK candidate generation (live trace)

### A.0 Joint inventory

| Symbol | Joints |
|--------|--------|
| `JOINT_NAMES` / `ROS2_JOINT_SI_ORDER` | `link-1_Revolute-1`, `link-2_Slider-2`, `link-3_Revolute-3`, `link-4_Slider-4`, `link-5_Revolute-5` |
| `SPINDLE_JOINT_NAME` | `pneumatic_spindle-Copy_Revolute-6` — **not** in planning order |

Source: `DENTOStep6State.py:48-56`, `DENTOROS2Bridge.py:32-34,74`.

`canonicalize_planning_joint_positions()` strips any legacy sixth key and returns **five** finite values only (`DENTOStep6State.py:71-84`).

### A.1 Execution trace per seed (until ACCEPT or REJECT)

Outer loop: `for route_type, seed_positions, seed_sample_index in seeds` (`DENTORobotWorkflowFacade.py:3878`).

Seeds built at `3847-3876`:
- Always `("direct", home_positions, None)` from Task Home.
- Up to `GOAL1_MAX_IK_SEEDS - 1` additional `("seeded", …)` from `step6AssistedLimitProposalJson.accepted_sample_evidence` where `home_connectivity.status == "HomeConnected"` and `joint_names == JOINT_NAMES`.

| Step | file:line | function | input | output | rejection condition |
|------|-----------|----------|-------|--------|-------------------|
| 1 | `3820:3841` | `_goal1_pre_entry_ik_candidates` | `pre_entry`, `entry`, `target`, `home_positions`, flags | empty `candidates`, `failures` | (setup only) |
| 2 | `3879-3887` | `_bridge.tool_pose_matrices_world_mm` | `entry`, `target`, `sample_count=2`, `axial_roll_start/end_deg=LEGACY_DIAGNOSTIC_TOOL_ROLL_DEG (0.0)`, optional `fixed_rotation_ras` | VTK 4×4 pose matrix; PreEntry XYZ written into translation at `3888-3889` | `ValueError` if entry/target invalid (not caught here — propagates) |
| 3 | `3890-3893` | `_bridge.set_moveit_tcp_goal_matrix` | pose matrix | `(ok, message, goal_node)` | **REJECT** if `ok` is false → `failures += "canonical TCP goal: …"` |
| 4 | `3899-3902` | `solve_moveit_tcp_position_axis_goal` | `seed_joint_positions_si=seed_positions`, `avoid_collisions` (default **True**) | `(ok, message, positions, ik_diagnostic)` | **REJECT** if `ok` false → `failures += "canonical TCP position-axis IK: …"` (+ residual/collision_pairs from diagnostic) |
| 5 | `3913-3927` | `check_moveit_static_joint_state` (if `require_generic_static=True`, default) | IK `positions` (J1–J5) | `(valid, message, authoritative)` | **REJECT** if not authoritative → `"could not be audited"`; **REJECT** if not valid → `"is invalid"` |
| 6 | `3929-3938` | `compute_tcp_pose_world_ras_mm` | `positions`, `base_transform` | `(fk_ok, message, authoritative_pose 4×4)` | **REJECT** if FK fails |
| 7 | `3940-3976` | inline FK residual check | `authoritative_pose`, `pre_entry`, `entry→target` axis | `position_residual_mm`, `axis_residual_deg` | **REJECT** if axis degenerate; **REJECT** if position > `0.25 mm` or axis > `0.5 deg` (`CARTESIAN_START_*` in `DENTOROS2Bridge.py:56-57`) |
| 8 | `3994-4000` | `_derived_axial_roll_deg`, `_tool_orientation_commitment` | FK rotation, tool axis | `rollDeg`, `orientationCommitment` | (no rejection — display/commitment metadata) |
| 9 | `4001-4004` | `moveit_joint_goal_diagnostics` | `home_positions`, `positions` | joint delta diagnostics | (no rejection) |
| 10 | `4005-4010` | dedup `seen_solutions` | rounded J1–J5 tuple | — | **REJECT** silently if duplicate IK solution (no `failures` entry) |
| 11 | `4022-4043` | append candidate | — | dict with `positions`, `rollDeg`, `routeType`, `seedSampleIndex`, diagnostics | **ACCEPT** |

**Direct IK call chain (step 4):**

| file:line | function | notes |
|-----------|----------|-------|
| `DENTOROS2Bridge.py:4433-4437` | `_dentobot_native_motion_context` | requires SlicerROS2 motion context |
| `DENTOROS2Bridge.py:4453-4454` | `joint_si_vector(seed)` | **5** seed values, J1–J5 only |
| `ROS2MotionControl.py:3364-3378` | `computeIKWithMoveIt(..., positionAxisOnly=True, avoidCollisions=…)` | timeout **0.2 s** to native solver |
| `vtkMRMLROS2RobotNode.cxx:931-1134` | `ComputeMoveItPositionAxisIK` | damped least-squares on **planning-group variables only** (5) |

### A.2 Answers to specific questions

**1. Joints entering the function**  
Five commandable joints (`JOINT_NAMES` above). Seeds are `Mapping[str,float]` with exactly those keys after `canonicalize_planning_joint_positions`.

**2. Are seeds J1–J5 only?**  
Yes. Workspace evidence must have `names == JOINT_NAMES` (`3865-3868`). `joint_si_vector` / `canonicalize_planning_joint_positions` reject or ignore J6 (`DENTOROS2Bridge.py:1708-1713`, `DENTOStep6State.py:76-78`).

**3. Why 13 attempts/legs?**  
Constants (`DENTORobotWorkflowFacade.py:58,67-72`):

```python
WORKSPACE_HOME_CONNECTIVITY_MAX_SAMPLES = 13
GOAL1_MAX_IK_SEEDS = WORKSPACE_HOME_CONNECTIVITY_MAX_SAMPLES + 1  # 14 max
GOAL1_MAX_PLANNED_IK_CANDIDATES = GOAL1_MAX_IK_SEEDS
```

6.3 runtime validation caps Home-connectivity evidence at **13** workspace samples (`994-996`). Goal 1 adds **Task Home** as the `direct` seed → at most **14** IK candidates.

The operator-reported **13 motion-diagnostic legs** (`logbook/2026-09-19.md`) are **one diagnostic row per `task_home_to_preentry_direct` plan attempt** in `planApproachPhase` (`4755-4765`), not separate roll sweeps. Thirteen legs means thirteen distinct IK candidates survived dedup and were joint-planned (typically 1 direct + 12 HomeConnected workspace seeds in that case).

**4. What varies across attempts?**

| Variant | Routine Goal 1? |
|---------|-----------------|
| **Different joint seeds** | **Yes** — `direct` (Task Home) vs `seeded` (6.3 `accepted_sample_evidence`) |
| **Different TCP roll angles** | **No** — pose scaffold uses fixed `LEGACY_DIAGNOSTIC_TOOL_ROLL_DEG = 0.0` for all seeds (`3879`, comment `64-66`). Roll is **derived after IK** from FK (`3994`), not searched. |
| **Different IK branches** | **Yes** — different seeds → different local convergence of Jacobian IK |
| **Clearance detours** | Separate diagnostic stage `clearance_to_preentry` — **after** this IK function, in `planApproachPhase` (`4942+`), not inside `_goal1_pre_entry_ik_candidates` |

**5. Rejection reason strings / codes**

Facade-level (`failures` list):
- `canonical TCP goal: {message}`
- `canonical TCP position-axis IK: {message} (best position=… mm, axis=… deg, collisions=…)`
- `canonical TCP IK state could not be audited: …`
- `canonical TCP IK state is invalid: …`
- `canonical TCP IK authoritative FK failed: …`
- `canonical TCP IK authoritative FK has no tool axis.`
- `canonical TCP IK authoritative FK exceeds tolerance: position=… mm, axis=… deg.`
- Silent skip: duplicate `solution_identity`

Wrapper `solve_moveit_tcp_position_axis_goal` (`DENTOROS2Bridge.py:4437-4505`):
- `TCP goal control is unavailable.`
- `The loaded SlicerROS2 build lacks position-axis IK; rebuild and restart it.`
- `MoveIt position-axis IK request failed: {exc}`
- Native `message` when `solution` empty (includes non-convergence, collision-at-endpoint, Jacobian failure — from `GetLastMoveItPositionAxisIKMessage()`)
- `MoveIt position-axis IK returned a joint-count mismatch.`

Native `ComputeMoveItPositionAxisIK` messages (`vtkMRMLROS2RobotNode.cxx:944-1131`):
- `MoveIt position-axis IK is not initialized.`
- `MoveIt position-axis IK received an invalid tip or seed.`
- `MoveIt position-axis IK target is non-finite or degenerate.`
- `Position-axis IK converged within tolerance but the endpoint is colliding.`
- `MoveIt could not compute the position-axis Jacobian.`
- `MoveIt position-axis IK produced a non-finite update.`
- `MoveIt position-axis IK stalled before reaching tolerance.`
- `Position-axis IK did not reach tolerance; best residuals were … mm and … deg.`
- `MoveIt position-axis IK exception: …`

**6. Post-MoveIt rejection by custom FK/axis checks?**  
**Yes.** Even when `solve_moveit_tcp_position_axis_goal` returns success, steps 5–7 can reject:
- MoveIt static state validity (`check_moveit_static_joint_state`)
- Authoritative KDL/MoveIt FK via `compute_tcp_pose_world_ras_mm` on `dentobot_drill_tcp`
- Custom tolerances `0.25 mm` / `0.5 deg`

`moveit_joint_goal_diagnostics` does not reject; it scores accepted candidates.

**7. Collision before `_goal1_candidate_chain_preflight()`?**  
**Yes.**

- Default `avoid_collisions=True` in `_goal1_pre_entry_ik_candidates` (`3829`) → native endpoint collision check inside `ComputeMoveItPositionAxisIK` when converged (`cxx:1021-1046`).
- `check_moveit_static_joint_state` queries PlanningScene validity (`DENTOROS2Bridge.py:4829-4892`) before accept.
- `_goal1_candidate_chain_preflight` is only reached from `planApproachPhase` **after** joint-space Home→PreEntry planning (`4775+`), which is downstream of IK candidate acceptance.

---

## QUERY B — `solve_moveit_tcp_position_axis_goal()` behavior

### B.1 Python wrapper (`DENTOROS2Bridge.py:4426-4505`)

```python
def solve_moveit_tcp_position_axis_goal(
    *,
    seed_joint_positions_si: Optional[Mapping[str, float]] = None,
    avoid_collisions: bool = True,
):
```

| # | Question | Answer | Evidence |
|---|----------|--------|----------|
| 1 | Ultimate API | `logic.computeIKWithMoveIt(..., positionAxisOnly=True)` → `robotmodel.ComputeMoveItPositionAxisIK(...)` (custom C++ Jacobian solver on MoveIt `RobotState`, **not** `kinematics.yaml` KDL `setFromIK`) | `ROS2MotionControl.py:3370-3378`, `vtkMRMLROS2RobotNode.cxx:931+` |
| 2 | Planning group | `dentobot_arm` (cached in robot node `JointModelGroupPtr` at IK setup) | `DENTOROS2Bridge.py:32`, `vtkMRMLROS2RobotNode.cxx:805` |
| 3 | Tip/TCP link | `dentobot_drill_tcp` (`ROS2_TOOL_TCP_LINK`) | `DENTOROS2Bridge.py:33,4449` |
| 4 | Frame ID | Probe goal transform: `GetMatrixTransformBetweenNodes(obsNode, toNode)` then `ConvertTipTargetToIKTarget` → IK target 4×4 in SI meters | `ROS2MotionControl.py:3348-3364,1807+` |
| 5 | Seed joint names | `ROS2_JOINT_SI_ORDER` (= five names above) | `4453-4454`, `1708-1713` |
| 6 | Seed dimensionality | **5** | `joint_si_vector` → `len(ROS2_JOINT_SI_ORDER)` |
| 7 | J6 | **Removed/never sent.** `canonicalize_planning_joint_positions` ignores spindle key. Native rejects seed if `size != variableCount` (5). Legacy 6-vector accepted only at KDL FK boundary for display, truncated before MoveIt (`vtkMRMLROS2RobotNode.cxx:1648-1654`). | |
| 8 | Task representation | **Position (3) + drill-axis direction (2 DOF in solver)** — Jacobian rows: translation + axis projected orthogonal to drill axis. **Not** full quaternion to KDL plugin. | `cxx:1066-1077`, comment `1066-1068` |
| 9 | Quaternion / roll | Facade sets probe matrix via `tool_pose_matrices_world_mm` with **fixed 0° roll** scaffold; position-axis IK **does not** consume that roll as a constraint. Solver message: *"axial tool roll was unconstrained"* (`cxx:1048-1049`). | `Facade 3879-3889`, `cxx:1048-1049` |
| 10 | Roll about drilling axis unconstrained? | **Yes** — axis projector omits axial component (`cxx:1069-1074`). | |
| 11 | Position tolerance | `0.00025 m` → **0.25 mm** | `cxx:986,1019` |
| 12 | Axis tolerance | `0.5 * M_PI / 180.0` rad → **0.5 deg** | `cxx:987,1019` |
| 13 | Timeout / attempts | Python passes **0.2 s**; C++ `maximumIterations = 120`, damped least-squares loop until deadline | `ROS2MotionControl.py:3376`, `cxx:988-1001` |
| 14 | Success vs failure | **Success:** non-empty `solution`, `len(solution)==5`, wrapper returns `True` + message. **Failure:** empty solution, wrong length, or exception; diagnostic retains best residuals / collision pairs. | `DENTOROS2Bridge.py:4498-4505` |
| 15 | Post-IK FK validation | **Not inside wrapper.** Caller `_goal1_pre_entry_ik_candidates` runs `compute_tcp_pose_world_ras_mm` → `robot_node.ComputeKDLFK(joint_si_vector(...), …, ROS2_TOOL_TCP_LINK)` with base transform (`DENTOROS2Bridge.py:4967-4971`). | |

### B.2 Helper: `joint_si_vector` (`1708-1713`)

Requires all `ROS2_JOINT_SI_ORDER` keys → returns `[canonical[name] for name in order]` (length 5).

### B.3 Helper: `computeIKWithMoveIt` (`3319-3391`)

- Refreshes planning scene at most once per second (`3360-3362`).
- Calls `ComputeMoveItPositionAxisIK(ikTargetPose, ikLink, seed, 0.2, avoidCollisions)`.

---

## QUERY C — Authoritative MoveIt configuration

| # | Item | Value | Source |
|---|------|-------|--------|
| 1 | Planning group name | `dentobot_arm` | `dentobot.srdf:3`, `kinematics.yaml:1`, `simulation.launch.py:74` |
| 2 | Definition | **Chain** `base_link` → `dentobot_drill_tcp` | `dentobot.srdf:3-4` |
| 3 | Base link | `base_link` | `dentobot.srdf:4` |
| 4 | Tip link | `dentobot_drill_tcp` | `dentobot.srdf:4`, `DENTOROS2Bridge.py:33` |
| 5 | Active joints (ordered) | `link-1_Revolute-1`, `link-2_Slider-2`, `link-3_Revolute-3`, `link-4_Slider-4`, `link-5_Revolute-5` | `dentobot.srdf:7-12`, `joint_limits.yaml`, `JOINT_NAMES` |
| 6 | `pneumatic_spindle-Copy_Revolute-6` in group? | **No** — downstream of tip link; URDF fixed joint `pneumatic_spindle-Copy_to_dentobot_drill_tcp` attaches TCP to spindle body | `test_moveit_config.py:18-21`, SRDF chain ends at `dentobot_drill_tcp` |
| 7 | J6 in `joint_limits.yaml`? | **No** — only five joints (`test_moveit_config.py:50-56`) | |
| 8 | IK plugin (MoveIt group) | `kdl_kinematics_plugin/KDLKinematicsPlugin` | `kinematics.yaml:2` |
| 9 | Solver params | `search_resolution: 0.002`, `timeout: 0.1`, `attempts: 5` | `kinematics.yaml:3-5` (applies to standard `ComputeMoveItIK` / OMPL, not position-axis Jacobian loop) |
| 10 | Second group / `dentobot_tool_tcp` EE? | **No** SRDF group. `dentobot_tool_tcp` is fixed child of `burr` on visual branch (`test_moveit_config.py:22-26`, SRDF collision pairs only) | |

Launch loads URDF + SRDF + kinematics + joint_limits (`simulation.launch.py:15-22,48-54`).

### Verdict

**`MOVEIT_CHAIN = STRICTLY J1-J5`**

Evidence: SRDF chain has five actuated joints ending at fixed TCP link; `joint_limits.yaml` lists exactly five joints; planning code and native position-axis IK use `variableCount` of the `dentobot_arm` group (5); J6 exists in URDF for visualization/collision only (`DENTOStep6State.py:43-46`).

---

## QUERY D — Intended vs current (comparison table)

Sources: `Workspace/docs/logbook/2026-09-04.md` (Five-constraint PreEntry IK), `Testing/test_robot_workflow_facade.py:624+`, `DENTOStep6State.py:71-93`, live facade/bridge/native code.

| Intended invariant | Test / doc assertion | Current implementation | Match? |
|--------------------|----------------------|------------------------|--------|
| J1–J5 only planning | Test: audited positions `set == ROS2_JOINT_SI_ORDER` | `canonicalize_planning_joint_positions`, `joint_si_vector`, native 5-DOF solver | **Match** |
| J6 locked/excluded | Test: 8 workspace seeds + direct, no sixth joint in evidence | `SPINDLE_JOINT_NAME` absent from `JOINT_NAMES`; seeds require `names == JOINT_NAMES`; `spindle_is_locked()` documented *"never used for planning"* (`87-88`) | **Match** |
| XYZ position constraint | Logbook: position-plus-axis task | `ComputeMoveItPositionAxisIK` minimizes position error to 0.25 mm | **Match** |
| Drill-axis constraint | Logbook: five-DOF axis task | Solver constrains tool +Z to target axis; 0.5 deg tolerance | **Match** |
| Free roll about drill axis | Logbook: housing roll not commanded | Axis projector drops axial component; `_tool_orientation_commitment` states roll not persisted (`3370-3373`) | **Match** |
| Bounded seed generation | Test: 9 candidates from 8 HomeConnected + direct; constants cap at 13+1 | `WORKSPACE_HOME_CONNECTIVITY_MAX_SAMPLES=13`, `GOAL1_MAX_IK_SEEDS=14` | **Match** |
| FK verification | Logbook: authoritative world-RAS FK | `compute_tcp_pose_world_ras_mm` + 0.25 mm / 0.5 deg gate before accept | **Match** (policy fingerprint advanced to `stage1-position-axis-authoritative-fk-v3` in code vs v2 in logbook) |
| Branch continuity | Logbook: bounded 6.3 seeds for branch evidence | `moveit_joint_goal_diagnostics` scores delta from Task Home; distinct seeds → distinct branches; dedup by rounded J1–J5 | **Match** |
| Collision-aware IK | Logbook: collision-aware endpoint | Default `avoid_collisions=True` + `check_moveit_static_joint_state` | **Match** |
| Roll sweep for routine Goal 1 | (not intended) | Fixed `LEGACY_DIAGNOSTIC_TOOL_ROLL_DEG=0.0` scaffold only | **Match** (no roll sweep) |

No architectural mismatches identified on the inspected invariants. Policy string version drift (`fk-v2` logbook vs `fk-v3` code) is a fingerprint bump, not a kinematic model change.

---

## Key code excerpts

### Seed cap and roll policy (`DENTORobotWorkflowFacade.py:64-72`)

```python
LEGACY_DIAGNOSTIC_TOOL_ROLL_DEG = 0.0
WORKSPACE_HOME_CONNECTIVITY_MAX_SAMPLES = 13
GOAL1_MAX_IK_SEEDS = WORKSPACE_HOME_CONNECTIVITY_MAX_SAMPLES + 1
```

### IK loop core (`DENTORobotWorkflowFacade.py:3878-4010`)

```python
for route_type, seed_positions, seed_sample_index in seeds:
    axial_roll_deg = LEGACY_DIAGNOSTIC_TOOL_ROLL_DEG
    pose = self._bridge.tool_pose_matrices_world_mm(...)[0]
    for index, value in enumerate(pre_entry):
        pose.SetElement(index, 3, float(value))
    ok, message, positions, ik_diagnostic = solve_position_axis(
        seed_joint_positions_si=seed_positions,
        avoid_collisions=bool(avoid_collisions),
    )
    # … static check, FK tolerance, dedup, candidates.append …
```

### Position-axis native tolerances (`vtkMRMLROS2RobotNode.cxx:986-987,1048-1049`)

```cpp
constexpr double positionToleranceM = 0.00025;
const double axisToleranceRad = 0.5 * M_PI / 180.0;
// success message:
"Position-axis IK converged using J1-J5; axial tool roll was unconstrained."
```

### SRDF chain (`dentobot.srdf:3-4`)

```xml
<group name="dentobot_arm">
  <chain base_link="base_link" tip_link="dentobot_drill_tcp"/>
</group>
```
