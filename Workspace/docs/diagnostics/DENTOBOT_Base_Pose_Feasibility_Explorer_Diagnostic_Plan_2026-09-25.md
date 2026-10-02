# DENTOBOT Step 6 — Robot Design Feasibility Explorer & Base-Pose Diagnostic Plan

**Date:** 2026-09-25
**Purpose:** Convert the current Step 6 planning deadlock into a measurable **robot-design-vs-software decision process**, with explicit ROS/MoveIt/Slicer diagnostics over sampled forehead-mounted robot base poses.
**Scope:** Research simulation only. No hardware motion, drilling authorization, or clinical validation.

---

## 0. Executive takeaway

We are currently stuck between two obligations:

1. **Make the existing robot design work in simulation** with correct IK, planning, collision checking, preview, and return/recovery semantics.
2. **Use simulation to determine whether the robot design itself is valid** for the dental drilling use case and show, with evidence, what should change mechanically if it is not.

The mistake is to keep trying to solve both indefinitely through a single opaque "Plan Guarded Approach" workflow.

The correct separation is:

```text
LEVEL 0 — Frames / transforms / URDF / scene correctness
                    |
                    v
LEVEL 1 — Static task-pose feasibility
          PreEntry IK / Entry IK / Target IK
                    |
                    v
LEVEL 2 — Local drilling-line feasibility
          Entry -> Target continuity + collision + margins
                    |
                    v
=========== ROBOT DESIGN DECISION GATE ===========
                    |
          if locally feasible
                    v
LEVEL 3 — Home -> PreEntry motion planning
                    |
                    v
LEVEL 4 — Full-chain planner robustness
                    |
                    v
LEVEL 5 — Preview / recovery / return / repeatability
```

**The robot-design decision belongs after Level 2, not after a perfect OMPL planner.**

If the robot cannot realize the required drilling task throughout a physically admissible forehead-mount region, then further planner work cannot fix the mechanism. If a healthy feasible region exists, the robot geometry should be frozen and the software/planning stack becomes the main target.

---

# 1. Status labels

- **[OBSERVED]** — directly supported by retained project evidence / current operator observations.
- **[INFERENCE]** — engineering interpretation of observed evidence.
- **[PROPOSED]** — new diagnostic or implementation recommendation.
- **[DECISION GATE]** — a condition that determines whether effort should move toward robot redesign or software/planning work.

---

# 2. Current case interpretation

## 2.1 FDI11 — earliest-pipeline IK/reachability case

**[OBSERVED]**

Saved FDI11 analysis shows:

- Task Home: J1–J5 = zero.
- Both slider joints are at their lower mechanical limits.
- Home TCP to PreEntry distance: **36.89 mm**.
- Home drill-axis to required drill-axis angular difference: **162.26°**.
- Approach standoff: **2.0 mm**.
- In addition to Home, **10 Home-connected workspace states** were used as IK seeds.
- No candidate satisfied both acceptance conditions.
- Position tolerance: **0.25 mm**.
- Drill-axis tolerance: **0.5°**.
- Some attempts aligned the axis almost exactly but remained about **0.919 mm** from PreEntry.
- Another attempt reached about **0.268 mm** position error but remained about **1.542°** off-axis.
- Empty collision tuples on nonconverged IK attempts do **not** establish collision freedom because collision was not necessarily evaluated before IK tolerance acceptance.

**[INFERENCE]**

This is not an OMPL problem yet.

Possible causes that still need discrimination:

1. joint-limit / task-envelope boundary,
2. poor conditioning / near-singularity,
3. local IK convergence/solver behavior,
4. bad base placement relative to the requested drilling direction,
5. multiple isolated IK branches with poor seed coverage.

FDI11 is therefore the ideal **negative IK / base-placement diagnostic case**.

---

## 2.2 FDI21 — downstream Stage-3 insertion/collision case

**[OBSERVED]**

The latest meaningful FDI21 RRTConnect trial:

- passed Home -> PreEntry,
- passed PreEntry -> Entry,
- failed during Entry -> Target / Stage 3,
- native guard reported target tooth ↔ `pneumatic_spindle-Copy`,
- the retained diagnostic also carried a provisional insertion-envelope warning:
  - requested combined insertion: **8.071 mm**,
  - provisional envelope: **6.500 mm**,
  - excess: **1.571 mm**.

The existing offline collision screenshots are invalid for contact interpretation because the recapture path incorrectly applied the moving-lower-jaw transform to fixed upper FDI21.

**[INFERENCE]**

This is primarily an insertion/tool-envelope/branch/collision problem, not currently a planner-selection problem.

FDI21 is the ideal **negative local-insertion / tool-geometry diagnostic case** once exact native scene/state attribution is repaired.

---

## 2.3 FDI31 — positive full-chain witness

**[OBSERVED]**

An altered housing-on FDI31 setup completed the full chain in the operator-visible simulation after changes to mouth opening, Task Home, and robot base placement/orientation.

Because several inputs changed, it does not isolate a single causal variable.

**[INFERENCE]**

FDI31 is useful as a **positive regression / existence witness**, not as proof that the current mounting arrangement generalizes to other teeth.

---

# 3. The missing experiment: Base-Pose × Target Feasibility Explorer

## 3.1 Purpose

**[PROPOSED]**

Build a dedicated diagnostic that systematically samples **physically admissible robot-base poses on the forehead mount plane** and evaluates whether the robot can realize the selected dental drilling task.

This must answer:

> For this tooth and this approved drilling trajectory, where can the robot base be mounted such that J1–J5 can realize PreEntry, Entry, and the entire Entry->Target insertion while respecting joint limits and collision constraints?

This diagnostic should run **before Home planning and before OMPL planner comparison**.

---

# 4. What to compute for every sampled base pose

For each candidate base transform `T_world_base`, store the following.

| Metric | Why it matters |
|---|---|
| **PreEntry IK** | Basic ability to realize the required TCP position + drill axis |
| **Entry IK** | Whether the selected branch can continue through the approach |
| **Target IK** | Whether the final drilling depth is kinematically reachable |
| **Full insertion samples** | Whether a single continuous branch survives Entry -> Target |
| **Minimum joint margin** | Reveals knife-edge solutions near mechanical limits |
| **Minimum forbidden-collision clearance** | Measures tool/link viability and robustness |
| **Task Jacobian conditioning** | Reveals singular / poorly controllable task configurations |
| **Best position residual** | Useful when strict IK acceptance fails |
| **Best axis residual** | Useful when strict IK acceptance fails |
| **Failure stage** | Distinguishes IK, continuation, joint limit, collision, or data failure |
| **First-invalid sample** | Makes the exact blocker reproducible |
| **Branch continuity metric** | Detects discontinuous IK jumps during insertion |
| **Evaluation time** | Necessary for practical map generation and later optimization |

Do **not** collapse all of this into one green/red value internally. Preserve the raw evidence.

---

# 5. Recommended system architecture

## 5.1 Principle: one authoritative planning/scene implementation

**[PROPOSED]**

Do not create a second IK engine, second collision world, second transform policy, or a parallel "fake" robot simulator.

The feasibility explorer should be a **thin orchestration layer** over the existing authoritative project components:

```text
DENTOWorkflow / Slicer
   |
   | selected branch / trajectory / forehead plane / base candidates
   v
DENTORobotWorkflowFacade
   |
   | existing FK / IK / stage helpers
   v
DENTOROS2Bridge
   |
   +------------------> MoveIt RobotState / IK
   |
   +------------------> PlanningScene / collision guard
   |
   +------------------> robot FK / Jacobian
   |
   +------------------> exact scene/base fingerprints
```

The diagnostic should reuse the current robot profile, base-placement semantics, jaw preparation, collision policy, trajectory, J1–J5 joint limits, TCP definition, and branch/provenance identity.

---

## 5.2 Do not rewrite URDF per sample

**[PROPOSED]**

A sampled base pose must be applied through the existing robot-base transform / scene-placement path.

Avoid:

- runtime URDF XML surgery,
- generating a new URDF file for every candidate,
- bypassing the production scene-sync layer.

The exact implementation depends on the current architecture:

- if the base is represented as a world→base transform in the Slicer/MoveIt scene, update that transform;
- if robot placement is already handled by `createOrUpdateRobotPlacement` or equivalent, reuse it;
- if MoveIt has a fixed root and placement is injected through the scene/world transform, use that same route.

**One base-transform semantics only.**

---

# 6. Runtime evaluation pipeline for one base pose

## 6.1 Inputs

```yaml
case_id:
prepared_branch_id:
target_tooth:
trajectory_id:

scene_fingerprint:
robot_profile_fingerprint:
collision_policy_fingerprint:

base_transform_world:
  translation_mm: [x, y, z]
  quaternion: [qx, qy, qz, qw]

trajectory:
  preentry_pose_world:
  entry_pose_world:
  target_pose_world:
  drill_axis_world:

ik_tolerances:
  position_mm:
  axis_deg:

seed_policy:
  home:
  workspace_seeds:
  prior_branch_seed:
```

## 6.2 Candidate state machine

```text
APPLY CANDIDATE BASE
        |
        v
VERIFY SAME SCENE / PROFILE / POLICY
        |
        v
CHECK PREENTRY IK
        |
   fail |------------------> SAVE BEST FAILED STATE
        |                    + residuals
        |                    + joint margins
        |                    + conditioning
        |                    + stop candidate
        v
SELECT VALID PREENTRY BRANCH
        |
        v
CHECK ENTRY CONTINUATION
        |
   fail |------------------> SAVE FIRST FAILURE
        v
CHECK ENTRY -> TARGET SAMPLES
        |
        +--> IK / branch continuity
        +--> joint limits
        +--> forbidden collisions
        +--> clearance
        +--> Jacobian conditioning
        |
        v
SAVE FULL LOCAL-TASK RESULT
```

No Home→PreEntry planner should be called here.

No RRTConnect/RRT/RRT* should be called here.

---

# 7. ROS / MoveIt implementation

## 7.1 MVP: local facade evaluator first

Implement a callable facade method before creating a new ROS action:

```python
evaluateBasePoseTaskFeasibility(
    branch_id,
    base_transform,
    trajectory_id,
    options
) -> BasePoseFeasibilityResult
```

It should orchestrate existing ROS/MoveIt functionality.

Why this first:

- reuses the current bridge,
- easy to test headlessly,
- avoids premature new ROS message/action definitions,
- GUI and automated map runner can share one evaluator.

Only introduce a dedicated ROS action later if GUI blocking, cancellation, or batch throughput makes it necessary.

---

## 7.2 Apply the candidate base transform

Pseudo-flow:

```python
freeze = captureCurrentIdentities()

assert freeze.branch == selected_branch
assert freeze.robot_profile == active_robot_profile
assert freeze.scene_policy == active_collision_policy

applyBaseTransformUsingExistingProductionPath(T_world_base_candidate)

syncCollisionScene()

audit = acknowledgeScene()

assert audit.robot_profile == freeze.robot_profile
assert audit.policy == freeze.scene_policy
assert audit.base_transform == T_world_base_candidate
```

The base candidate must never silently modify tooth geometry, trajectory geometry, jaw transform, collision allowances, TCP, or joint limits.

---

# 8. PreEntry IK diagnostic per base pose

## 8.1 Seed set

For each base candidate use a controlled seed set such as:

1. Task Home,
2. retained Home-connected workspace states,
3. optional seed from the nearest previously feasible base cell,
4. optional prior accepted branch state during local refinement.

Every seed must retain provenance.

Example:

```json
{
  "seed_id": "WS-07",
  "seed_source": "saved_workspace_connected",
  "q_seed": []
}
```

---

## 8.2 Preserve best failed states

For every seed, retain:

```json
{
  "accepted": false,
  "q_seed": [],
  "q_best": [],
  "position_error_mm": 0.919,
  "axis_error_deg": 0.08,
  "position_tolerance_mm": 0.25,
  "axis_tolerance_deg": 0.5,
  "termination_reason": "...",
  "iterations": null,
  "collision_check_status": "NOT_EVALUATED",
  "collision_pairs": []
}
```

`collision_pairs = []` does **not** mean collision-free unless:

```text
collision_check_status == EVALUATED_CLEAR
```

---

## 8.3 Residual ranking

Store:

```text
normalized_position_error = position_error / position_tolerance
normalized_axis_error     = axis_error / axis_tolerance
```

Useful report-only aggregates:

```text
residual_score = max(
    normalized_position_error,
    normalized_axis_error
)
```

and optionally:

```text
residual_l2 = sqrt(
    normalized_position_error^2 +
    normalized_axis_error^2
)
```

Never replace the raw residuals with the aggregate.

---

# 9. Entry and Target continuation

## 9.1 Preserve the same branch

Once PreEntry has a valid q:

```text
q_preentry
    |
    | use as next seed
    v
q_entry
    |
    | use as next seed
    v
q_insert_1
    |
    v
q_insert_2
    |
   ...
    v
q_target
```

Do not independently solve Target from an unrelated seed and call the drilling line feasible.

---

## 9.2 Insertion sampling

Let:

```text
p(s) = Entry + s(Target - Entry)
s in [0,1]
```

At each sample:

- position follows the drilling line,
- drill axis remains fixed to the approved trajectory axis,
- previous accepted q becomes the next seed.

Development defaults can be tunable, for example:

```text
coarse insertion step: 0.5 mm
refined near failure: 0.1–0.25 mm
```

These are diagnostic discretization settings, **not clinical accuracy claims**.

The native collision guard may still perform finer interpolation internally.

---

# 10. Branch continuity metric

For consecutive accepted states `q_k` and `q_k+1`:

- revolute joints: wrapped angular difference,
- prismatic joints: linear difference.

Normalize by joint range:

```text
delta_q_norm_i =
    abs(q_i[k+1] - q_i[k]) /
    (q_i_max - q_i_min)
```

Store:

```text
max_step_joint_delta_norm
sum_joint_path_delta_norm
```

A large discontinuous jump suggests an IK branch switch.

Initially use this as diagnostic evidence, not a new rejection threshold unless existing stage semantics already define one.

---

# 11. Minimum joint margin

For each joint:

```text
lower_margin_i = q_i - q_i_min
upper_margin_i = q_i_max - q_i
absolute_margin_i = min(lower_margin_i, upper_margin_i)
```

Also store a normalized margin:

```text
normalized_margin_i =
    absolute_margin_i /
    (q_i_max - q_i_min)
```

Per candidate:

```text
min_joint_margin_absolute
min_joint_margin_normalized
limiting_joint_name
limiting_joint_side   # lower / upper
```

Across insertion:

```text
candidate_min_joint_margin_normalized =
    min(all insertion states, all joints)
```

This distinguishes **PASS but healthy** from **PASS but almost at a joint stop**.

---

# 12. Collision clearance

## 12.1 Boolean collision is not enough

The native guard remains authoritative for pass/fail.

For design diagnostics, additionally query:

```text
minimum distance to forbidden collision
```

if the installed MoveIt collision environment supports it.

Possible semantics if the API truly provides signed distance:

```text
clearance > 0 -> separated
clearance = 0 -> contact
clearance < 0 -> penetration
```

Otherwise store nonnegative minimum distance plus an independent collision boolean.

---

## 12.2 Use the same PlanningScene

Do not create a VTK-only collision estimator for acceptance.

A clearance query should use the same authoritative MoveIt scene, collision geometry, and allowed-collision policy as the guard.

If `collision_guard.cpp` currently exposes only collision yes/no, add a **read-only diagnostic distance query** against the same PlanningScene rather than a parallel scene.

Potential MoveIt direction to verify against the installed version:

```text
PlanningScene
  -> CollisionEnv
  -> distanceRobot(...)
  -> distanceSelf(...)
```

---

## 12.3 Handle allowed burr-target contact explicitly

During drilling:

- burr-to-target contact may be intentionally allowed,
- spindle-housing-to-target is not automatically allowed,
- robot-link-to-anatomy contact remains forbidden unless explicitly declared.

Store separately:

```text
minimum_forbidden_clearance_mm
minimum_robot_anatomy_clearance_mm
minimum_spindle_anatomy_clearance_mm
allowed_contact_pairs
first_forbidden_pair
```

Do not let intended burr contact force the entire design-clearance metric to zero and hide the surrounding geometry.

---

# 13. Task Jacobian conditioning

This is one of the strongest diagnostics for distinguishing poor robot geometry from poor numerical convergence.

## 13.1 Task Jacobian

The task constrains approximately:

- 3 TCP position components,
- 2 drill-axis direction components.

Rotation about the drill axis is not required.

Construct:

```text
J_task =
[
  J_position     # 3 x 5
  J_axis         # 2 x 5
]
                 # 5 x 5
```

## 13.2 Drill-axis differential

Let `a` be the current unit drill axis.

For angular velocity `omega`:

```text
da/dt = omega × a
```

If `Jw` is the angular part of the geometric Jacobian:

```text
da/dq = -[a]_x * Jw
```

Choose two orthonormal tangent vectors perpendicular to `a`:

```text
b1 ⟂ a
b2 ⟂ a
b1 ⟂ b2
```

Then:

```text
B = [b1 b2]       # 3 x 2
J_axis = B^T * (-[a]_x) * Jw
```

giving a `2 x 5` axis Jacobian.

---

## 13.3 Normalize mixed units before condition number

Raw Jacobian conditioning is misleading because:

- task rows mix translation and angle,
- joints mix revolute and prismatic units.

Normalize joint columns using joint ranges:

```text
Dq = diag(joint_range_1, ..., joint_range_5)
```

Normalize task rows using task tolerances:

```text
Wp = 1 / position_tolerance
Wa = 1 / axis_tolerance

W_task = diag(
    Wp, Wp, Wp,
    Wa, Wa
)
```

with consistent SI units internally.

Then:

```text
J_normalized = W_task * J_task * Dq
```

Perform SVD:

```text
J_normalized = U * S * V^T
```

Store:

```text
singular_values
sigma_min
sigma_max
condition_number = sigma_max / sigma_min
rank_estimate
```

This produces a dimensionless task-sensitivity diagnostic tied to usable joint ranges and required task precision.

Do **not** immediately define a hard acceptable condition-number threshold. First compare:

- feasible vs failed base poses,
- FDI11 vs FDI31,
- successful vs near-failed insertion states.

---

# 14. Failed-pose diagnostics

For failed base cells retain:

```text
best_position_error_mm
best_axis_error_deg
best_q
limiting_joint
min_joint_margin_norm
jacobian_sigma_min
jacobian_condition
solver_termination
```

Suggested evidence labels:

```text
FAIL_IK_POSITION
FAIL_IK_AXIS
FAIL_IK_COMBINED
FAIL_JOINT_LIMIT
FAIL_COLLISION
FAIL_INSERTION_CONTINUITY
FAIL_SCENE_IDENTITY
INCONCLUSIVE
```

Treat `FAIL_POOR_CONDITIONING` cautiously unless there is an agreed threshold; initially report the numerical conditioning rather than declaring it causal automatically.

---

# 15. Sampling the forehead base-placement space

## 15.1 Do not start with arbitrary SE(3)

A full six-dimensional base search is expensive and can produce mechanically impossible mount poses.

Represent the forehead mount using:

```text
forehead_plane_transform
admissible_mount_polygon / bounds
nominal_surface_normal
mount footprint constraints
orientation bounds
```

---

## 15.2 Hierarchical search

### Pass 1 — coarse position map

Keep orientation fixed to the nominal forehead-plane orientation.

Sample only in-plane coordinates:

```text
u, v
```

Possible development spacing:

```text
5 mm coarse grid
```

Purpose:

- identify broad reachable/unreachable regions,
- reveal topology,
- avoid orientation explosion.

### Pass 2 — local refinement

Around:

- feasible islands,
- feasibility boundaries,
- low failed residual areas,

refine to roughly:

```text
1–2 mm
```

### Pass 3 — bounded orientation sweep

At promising positions, sample only mechanically meaningful orientation offsets:

```text
pitch about one plane tangent
yaw about the other plane tangent
optional roll about plane normal
```

Possible development sweep:

```text
±10° with 5° coarse steps
then 1–2° local refinement
```

These are tunable development values, not final mounting tolerances.

---

# 16. Per-candidate record

```json
{
  "candidate_id": "base-u03-v08-pitch+05-yaw00",
  "case_id": "...",
  "branch_id": "...",
  "trajectory_id": "...",

  "base_transform_world": {
    "translation_m": [0.0, 0.0, 0.0],
    "quaternion_xyzw": [0.0, 0.0, 0.0, 1.0]
  },

  "identity": {
    "robot_profile_fingerprint": "...",
    "scene_content_fingerprint": "...",
    "collision_policy_fingerprint": "...",
    "trajectory_fingerprint": "..."
  },

  "preentry": {
    "status": "PASS",
    "selected_seed_id": "WS-02",
    "q": [],
    "position_error_mm": 0.0,
    "axis_error_deg": 0.0
  },

  "entry": {
    "status": "PASS",
    "q": []
  },

  "target": {
    "status": "PASS",
    "q": []
  },

  "insertion": {
    "status": "PASS",
    "num_samples": 18,
    "fraction_completed": 1.0,
    "first_invalid_sample": null,
    "max_joint_step_norm": 0.04
  },

  "joint_margin": {
    "minimum_normalized": 0.17,
    "limiting_joint": "link-4_Slider-4",
    "limiting_side": "upper"
  },

  "collision": {
    "status": "CLEAR",
    "minimum_forbidden_clearance_mm": 2.4,
    "minimum_pair": ["pneumatic_spindle-Copy", "FDI12"]
  },

  "conditioning": {
    "sigma_min": 0.12,
    "condition_number": 34.0
  },

  "best_failed_residual": null,

  "timing_ms": {
    "total": 184,
    "ik": 74,
    "collision": 81,
    "jacobian": 4
  }
}
```

Do not fabricate unavailable fields. Use `null` / `NotAvailable`.

---

# 17. Batch storage

Create one dataset per map run:

```text
FeasibilityMapRun
  |
  +-- run_manifest.json
  +-- candidates.jsonl
  +-- summary.json
  +-- map.vtp / map-node metadata
  +-- optional screenshots
```

`run_manifest.json` should freeze:

```text
case hash
branch ID
target
trajectory
robot profile
URDF/SRDF/mesh hashes
collision policy
jaw/open-mouth transform
forehead plane identity
sampling bounds
sampling resolution
tolerances
software revision
```

Use JSONL for per-candidate streaming so a timeout/cancel does not erase prior results.

---

# 18. Real-time / interactive execution strategy

## 18.1 Meaning of "real-time" here

For this research diagnostic, "real-time" means:

- the operator selects/moves to a base candidate,
- that candidate is evaluated through authoritative ROS/MoveIt checks,
- metrics stream back promptly,
- Slicer updates the robot ghost and map interactively.

It does **not** mean real-time physical robot control.

## 18.2 Minimal architecture

```text
Slicer GUI
   |
   | candidate T_world_base
   v
Feasibility Explorer Controller
   |
   | sequential calls
   v
Existing DENTORobotWorkflowFacade / DENTOROS2Bridge
   |
   +--> apply base transform
   +--> synchronize planning scene
   +--> IK
   +--> FK/Jacobian
   +--> collision/clearance
   +--> structured result
   |
   v
Slicer map renderer + diagnostic table
```

Run candidate evaluation outside the blocking GUI path.

All MRML updates should still use the project's Slicer-safe/main-thread conventions.

---

# 19. Optional ROS2 Action for batching

Only add this after the local evaluator works and if progress/cancellation/performance justify it.

Suggested semantics:

```text
EvaluateBasePoseBatch.action
```

### Goal

```yaml
case_identity
scene_fingerprint
robot_profile_fingerprint
trajectory
base_pose_candidates[]
sampling_options
ik_tolerances
```

### Feedback

```yaml
current_candidate_index
candidate_id
current_stage
elapsed_ms
partial_result
completed_count
```

### Result

```yaml
status
candidate_results[]
failed_candidate_count
inconclusive_count
identity_check_result
```

The server must call the same underlying IK/collision/FK logic used by the normal workflow.

---

# 20. Cancellation

On cancel:

- finish or safely abort the current read-only candidate,
- do not start new candidates,
- flush all completed candidate records,
- mark remaining candidates `NotRun`,
- restore the pre-run display/base state if needed,
- never promote a candidate automatically.

---

# 21. Paint the results onto the forehead plane in 3D Slicer

## 21.1 Model node

Create a review model such as:

```text
DENTOBOT_FeasibilityMap_<target>_<trajectory>
```

Construct a `vtkPolyData` grid over the sampled forehead plane.

Attach point/cell scalar arrays:

```text
feasible_local_task
failure_stage_code
preentry_ik_pass
entry_ik_pass
target_ik_pass
insertion_fraction

min_joint_margin_norm
min_forbidden_clearance_mm
jacobian_log10_condition
jacobian_sigma_min

best_position_residual_mm
best_axis_residual_deg

evaluation_time_ms
```

## 21.2 Display modes

Allow the operator to switch the active scalar.

### A. Local task feasibility

Suggested semantics:

```text
Green  = complete local task passed
Yellow = partial / near / unresolved
Red    = demonstrated failure
Gray   = not evaluated / stale / invalid
```

### B. Joint margin

Continuous scalar: low -> poor, high -> healthy.

### C. Collision clearance

Show increasing forbidden-clearance margin.

### D. Jacobian conditioning

Visualize:

```text
log10(condition_number)
```

instead of raw condition number.

### E. Best failed residual

Switch between:

- position residual,
- axis residual,
- normalized combined residual.

---

# 22. Click-to-inspect

When a sampled cell is clicked:

1. select that candidate record,
2. show all numeric metrics,
3. show the robot at that base as a **review-only ghost**,
4. optionally show:
   - PreEntry,
   - Entry,
   - Target,
   - accepted insertion states,
   - first-invalid state,
5. identify limiting joint,
6. show collision pair / clearance,
7. show Jacobian metrics.

Do not silently commit the candidate.

Use an explicit flow:

```text
[Review Candidate]
[Accept as Base Placement]
```

Accepting a new base must trigger normal invalidation semantics.

---

# 23. Decision semantics

## Outcome A — large healthy feasible region

Interpretation:

- task is kinematically feasible,
- mounting is not excessively sensitive,
- useful margins exist.

**Decision:** freeze robot geometry for this task class and focus on IK robustness, Home choice, OMPL, guard runtime, preview, and return.

---

## Outcome B — small but usable feasible island

Interpretation:

- robot can work,
- mounting is sensitive.

Direction:

- improve mount indexing,
- improve automatic base recommendation,
- quantify sensitivity,
- consider only small mechanical improvements if they enlarge robustness.

---

## Outcome C — isolated knife-edge solutions

Especially if feasible cells also show:

```text
joint margin ~ 0
high condition number
low collision clearance
```

Interpretation:

- mechanism technically reaches,
- but design robustness is poor.

**Decision:** mechanical optimization is more justified than endless planner tuning.

---

## Outcome D — no locally feasible base pose

After validating:

- scene,
- trajectory,
- bounded seed coverage,
- physically admissible base region,
- joint limits,
- TCP,

interpretation:

- robot design or declared mount/clinical scope is incompatible with the task.

**OMPL is irrelevant until geometry changes.**

---

## Outcome E — IK feasible but insertion collision everywhere

Interpretation:

The manipulator reaches the trajectory, but end-effector / spindle / burr / guide geometry cannot realize the insertion.

Primary design variables:

```text
burr protrusion
spindle nose length / diameter
TCP placement
guide thickness
tool mounting offset
trajectory clearance
```

Do not tune Home or RRT.

---

## Outcome F — local task works, but Home cannot connect

Interpretation:

Robot design can perform the dental task.

Now the problem legitimately becomes:

```text
Home choice
IK branch selection
free-space planning
OMPL
approach routing
```

This is the point where planner engineering is justified.

---

# 24. Use the same explorer for robot redesign

If redesign is needed, parameterize candidate mechanical changes:

```text
link length
slider stroke
joint offset
base-to-first-joint offset
spindle lateral offset
spindle nose length
burr protrusion
joint angular range
```

For each robot variant, rerun the same map and compare:

```text
feasible-region area
fraction of feasible cells
minimum joint-margin distribution
minimum clearance distribution
conditioning distribution
target coverage
```

This converts design changes into evidence.

Example conclusion:

> Increasing slider-4 usable travel by X increases anterior-target coverage and moves the limiting states away from the upper joint boundary.

---

# 25. Multi-tooth coverage

After validating the explorer on FDI11/FDI21/FDI31, expand to the registry.

For each target and trajectory slot:

```text
target
  -> trajectory 1
  -> trajectory 2
  -> trajectory 3
```

produce:

```text
feasible base region
robust base region
failure classes
```

Then calculate overlap between teeth.

If one head-mounted base pose is expected to serve multiple teeth without remounting, the important result is the **common feasible region**, not the best base pose for each tooth independently.

---

# 26. Recommended implementation sequence

## P0 — source reconciliation

Read current:

- base-placement logic,
- FK/IK helpers,
- Jacobian code,
- collision guard,
- scene sync,
- Step 6 state/facade,
- forehead plane model,
- workspace explorer.

Do not duplicate infrastructure.

## P1 — single-base local evaluator

Implement:

```text
evaluateBasePoseTaskFeasibility()
```

for the current base.

Test on:

```text
FDI11 -> negative IK case
FDI21 -> downstream local insertion/collision case
FDI31 -> positive-control case
```

## P2 — preserve failed IK evidence

Add:

- q_best,
- residuals,
- joint margins,
- collision-check status,
- solver termination,
- Jacobian diagnostics.

## P3 — interactive single candidate

Add:

```text
[Evaluate Current Base Pose]
```

This validates the diagnostic before map batching.

## P4 — coarse forehead-plane map

Sample 2D base positions at fixed nominal orientation.

## P5 — adaptive refinement

Refine around:

- feasible islands,
- feasibility boundaries,
- lowest failed residuals.

## P6 — bounded orientation sweep

Add mechanically admissible orientation offsets.

## P7 — robot design comparison

If current geometry has poor coverage, compare controlled geometry variants using the exact same map.

## P8 — resume planner work

Only for a base pose with healthy local task feasibility does:

```text
Home -> PreEntry
```

become a legitimate OMPL problem.

---

# 27. Performance guidance

The 23-Sep evidence showed repeated guard work dominating runtime, not native OMPL solve time.

For the feasibility explorer:

## Reuse immutable data

Safe within a frozen map run:

- RobotModel,
- static anatomy geometry,
- trajectory poses,
- joint bounds,
- TCP transform,
- collision policy definition,
- segmentation meshes,
- target identity.

Never cache collision verdicts across changing robot states.

## Avoid full scene reconstruction per candidate

If anatomy stays fixed and only base changes:

- reuse anatomy,
- update base transform,
- update RobotState,
- perform local checks.

Do not reopen the Slicer case or rebuild every mesh per point unless current architecture forces it.

## Prefer one synchronized scene + many RobotState checks

Desired pattern:

```text
synchronize authoritative PlanningScene once
        |
        +-> evaluate q
        +-> evaluate q
        +-> evaluate q
        +-> evaluate q
```

instead of repeatedly rebuilding/re-acknowledging the entire scene for every insertion sample.

---

# 28. Integrity constraints

The explorer must never:

- command hardware,
- publish physical motion,
- drill,
- relax tolerances to obtain a pass,
- suppress spindle collision,
- alter the target trajectory during evaluation,
- change tooth anatomy,
- alter allowed-collision policy silently,
- accept a sampled base automatically,
- treat a display ghost as authoritative,
- mix scene/profile/trajectory fingerprints,
- combine stages from different IK branches,
- call `collisions=()` collision-free when collision was not evaluated.

---

# 29. Required outputs

## Human-readable run summary

Example:

```text
Target: FDI11
Trajectory: 1
Candidates evaluated: 184
Locally feasible: 23
Inconclusive: 0

Largest contiguous feasible region:
  ...

Best joint-margin candidate:
  ...

Best clearance candidate:
  ...

Best-conditioned candidate:
  ...

Dominant observed failure:
  PreEntry IK / joint boundary / etc.
```

## Machine-readable evidence

- run manifest,
- JSONL per candidate,
- full-precision q vectors,
- exact base transforms,
- exact first-invalid samples,
- raw residuals,
- scene/profile identities,
- optional screenshots.

## Slicer visualization layers

- feasibility,
- failure stage,
- joint margin,
- collision clearance,
- conditioning,
- best residual.

---

# 30. Final decision framework

Ask one question:

> **Can a physically admissible forehead base region perform the local drilling task with healthy margins?**

### YES, robustly

```text
Robot geometry passes local task feasibility
-> freeze geometry
-> fix solver robustness / Home / OMPL / guard runtime
```

### YES, but only in tiny / singular / joint-limited islands

```text
Robot technically works
but design robustness is poor
-> minor mechanical optimization is justified
```

### NO, because IK never becomes feasible

```text
kinematic design / joint travel / base relation problem
-> redesign before more planner work
```

### NO, because insertion collides despite valid IK

```text
end-effector / spindle / burr / guide envelope problem
-> tool-stack redesign before more planner work
```

### Local task works, but Home cannot connect

```text
Now it is truly a motion-planning problem
-> OMPL / Home / route-search effort is justified
```

---

# 31. Final takeaway

The next major Step 6 deliverable should **not** be:

> "Make RRTConnect green."

It should be:

> **A Base-Pose × Target Feasibility Explorer that converts the physically admissible forehead mounting region into an evidence map of IK reachability, insertion continuity, joint margin, collision clearance, and task conditioning.**

That tool creates the missing engineering boundary between:

```text
FIX SOFTWARE
```

and:

```text
CHANGE ROBOT DESIGN
```

It also turns the Step 6 simulation into the actual engineering instrument this TRL-4 project needs:

> **a reproducible way to explain whether the robot works, where it works, how robustly it works, and which robot-design variable is limiting it when it does not.**


## 2 October 2026 implementation note

The forehead-plane map (in-plane translation) is implemented as an IK-reachability
preflight in `dentobot_workflow/base_placement_search.py` (±30 mm, 5 mm coarse and
1 mm refine, whole PreEntry->Target stroke, native-replica IK seeded from Task Home).
Depth and the ±10° orientation sweep are implemented but locked to 0 by default.
Connected confirmation per candidate: `Testing/run_step6_base_candidate_confirmation.py`.
See DECISIONS.md, 2 October.
