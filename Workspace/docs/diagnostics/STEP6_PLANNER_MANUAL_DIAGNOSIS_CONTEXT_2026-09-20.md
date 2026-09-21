# Step 6 Planner — Manual Intervention Diagnosis Context
**Date:** 2026-09-20  
**Purpose:** Preserve the current diagnosis, evidence, mental model, and next-step plan before any fixes are applied.  
**Scope:** Step 6 motion planning for DentoBot, especially Goal 1 (Task Home → PreEntry), with downstream relevance to Entry → Target and homing.

---

## 1. Why this manual intervention started

Tarun explicitly identified that the Step 6 planner had become harder to reason about than the underlying robotics problem justified. The core concern was that Codex had accumulated too many layers of candidate generation, route labels, workspace-derived seeds, preflight chains, phase guards, collision diagnostics, branch-continuity logic, custom validation layers, and homing state/history logic around a motion problem that should fundamentally reduce to:

1. Current/Home joint state
2. PreEntry
3. Entry
4. Target
5. Collision-aware motion planning between them

The intervention goal is therefore **not** to throw away safety or validation, but to separate what is fundamentally required for correct robotics, what is diagnostic/automation support, what may be accidental complexity, and what is actually causing the current blocker.

The intended debugging order is now:

**TF / coordinate truth → FK → IK → Home→PreEntry joint planning → Cartesian insertion → self-collision → patient collision → automation / guards / diagnostics**

This deliberately proves core robotics behavior before allowing orchestration layers to obscure it.

---

## 2. Tarun’s key contributions / thinking that shaped the diagnosis

These are important because the current diagnosis was not produced by code inspection alone.

### 2.1 Tarun challenged the J6 model
Tarun had already told Codex that there is **no robotic Joint 6**.

The physical drill is an **air-turbine / aerotor spindle whose rotation is pressure-controlled**, and that rotation is not part of the robot positioning loop.

Tarun’s intended physical abstraction was:

**J1 → J2 → J3 → J4 → J5 → fixed spindle body → fixed burr/tool geometry → TCP**

with pressure/RPM control treated separately from robot pose planning.

This led to the first audit question:

> Is Codex’s “J6” workaround contaminating MoveIt, IK, FK, collision checking, or TCP definitions?

### 2.2 Tarun proposed simplifying around SlicerROS2 + MoveIt
Tarun’s broader intuition was that the project should be able to rely much more directly on the existing SlicerROS2 / MoveIt stack instead of maintaining a large custom planner abstraction.

That produced the core simplification question:

> Can we reduce the live planner to “valid Home + valid PreEntry IK + normal OMPL joint-space plan + Cartesian Entry/Target motion + collision checking”?

This remains the correct mental model for the intervention.

### 2.3 Tarun identified the spindle body as a physical-design variable
After the live collision evidence repeatedly implicated the spindle housing, Tarun proposed the most important physical feasibility experiment:

> Temporarily remove the spindle-head body from collision checking and rerun the planner.

The purpose is **not** to permanently ignore the spindle. The purpose is to answer:

> Is the current failure fundamentally due to the physical volume of the spindle housing?

If disabling only that collision body allows the planner to succeed, then the software/kinematics may be fundamentally sound and the remaining problem becomes a new mechanical/planning design problem.

Tarun explicitly accepted that outcome:

> If the spindle constraint is the blocker, planning/redesigning around it can be treated as a separate engineering problem.

That is now one of the primary next experiments.

---

## 3. Authoritative motion architecture established from code

### 3.1 The actual MoveIt planning group is strictly 5-DOF
The authoritative MoveIt group is:

**`dentobot_arm`**

with chain:

**`base_link` → `dentobot_drill_tcp`**

and active joints:

1. `link-1_Revolute-1`
2. `link-2_Slider-2`
3. `link-3_Revolute-3`
4. `link-4_Slider-4`
5. `link-5_Revolute-5`

The fake spindle J6:

**`pneumatic_spindle-Copy_Revolute-6`**

is **not** part of the MoveIt planning group and is **not** listed in the MoveIt joint limits for `dentobot_arm`.

Therefore:

> **MOVEIT_CHAIN = STRICTLY J1–J5**

This substantially reduces the probability that J6 is causing the current Goal 1 failure.

### 3.2 J6 is still conceptually wrong, but not the immediate blocker
The URDF does contain a continuous J6 on the burr/spin branch, but the canonical planning TCP:

**`dentobot_drill_tcp`**

is fixed directly to the spindle body before J6.

Therefore J6 does not change the canonical planning TCP pose used by the Step 6 MoveIt group.

This means:

- J6 should still be cleaned up later for architectural clarity.
- J6 may still create confusion in legacy FK/visualization code.
- But **do not spend the next debugging session fixing J6 expecting the current Goal 1 planner failure to disappear.**

The current evidence says that is unlikely.

---

## 4. The 5-constraint PreEntry IK is actually implemented correctly

This was a major uncertainty and is now resolved.

The current live Step 6 PreEntry IK is not a fake 6-DOF pose solve.

It uses a custom MoveIt `RobotState` Jacobian-based solver with:

- TCP position = 3 constraints
- drill-axis direction = 2 constraints
- axial roll = unconstrained

This is the correct formulation for the 5-DOF robot.

### Important verified properties

- Seed vectors are J1–J5 only.
- J6 is stripped / never sent to the solver.
- The canonical tip is `dentobot_drill_tcp`.
- Position tolerance is approximately **0.25 mm**.
- Axis tolerance is approximately **0.5°**.
- Axial roll is explicitly unconstrained.
- Different Goal 1 candidates arise from different joint seeds / IK branches, not a roll sweep.
- The routine planner is not trying 13 different roll orientations.

This means the current IK architecture itself is broadly aligned with the intended robot kinematics.

---

## 5. What the “13 legs / candidates” actually mean

The earlier mental model that “13 IK attempts may be artificial roll variants” was wrong.

The 13 diagnostic legs are generated from different **joint-space seeds / candidate IK branches**.

The seed pool consists of:

- Task Home as the direct seed
- HomeConnected Step 6.3 workspace samples as additional seeds

The current code allows up to roughly:

- 13 workspace-derived seeds
- plus Task Home

and then deduplicates equivalent IK solutions.

Therefore the many candidates are not intrinsically evidence of a bad 6-DOF IK formulation.

They are primarily an attempt to find multiple local IK branches for the same PreEntry task.

---

## 6. Important finding: current live failure is NOT “PreEntry IK failed”

This is the most important diagnosis from the latest live screenshot.

The error states approximately:

> “Goal 1 found **3 collision-aware PreEntry IK endpoint(s)**, but MoveIt could not connect Task Home to the top-ranked arm branch(es)...”

That proves:

### Already successful
- PreEntry geometric target generation
- J1–J5 position-axis IK
- at least 3 distinct valid PreEntry joint configurations
- endpoint collision checking
- custom FK verification
- position residual tolerance
- drill-axis residual tolerance

Therefore:

> **The robot can reach PreEntry in at least three collision-free endpoint configurations.**

The current problem is now specifically:

**Task Home → valid PreEntry configuration**

not:

**Can the robot reach PreEntry?**

This is a major reduction in problem scope.

---

## 7. What the Home → PreEntry planner actually does

The current Goal 1 planner calls:

**`plan_moveit_joint_goal()`**

which ultimately invokes:

**MoveIt `MoveGroupInterface::plan()`**

using OMPL.

For the current direct Home→PreEntry plan:

- planner pipeline = OMPL
- default planner = `RRTConnectkConfigDefault`
- start state = explicit saved Task Home
- goal = explicit J1–J5 PreEntry joint solution
- no TCP orientation/path constraint is imposed during this leg
- no Cartesian constraint is imposed
- collision checking is enabled
- MoveIt is allowed to search a curved joint-space path
- planning time = approximately 5 s
- current Goal 1 uses one planning attempt per candidate/route

This is important because it means:

> The planner is already doing a genuine free-space OMPL search.

The software is **not** rejecting the route merely because straight interpolation collides.

---

## 8. The “30.2% direct interpolation collision” is diagnostic only

The live error also reports something like:

> “The direct Task-Home-to-goal joint interpolation first collides at 30.2% ...”

This initially looked suspicious because it sounded as if the planner might be rejecting a valid goal based on naive straight interpolation.

Code inspection proved otherwise.

The actual sequence is:

1. OMPL tries Home → PreEntry.
2. OMPL fails.
3. Only after that failure, the software linearly interpolates the five joints to diagnose where a simple direct joint chord first becomes invalid.
4. That result is printed as explanatory evidence.

Therefore:

> **The 30.2% interpolation is not a planner gate.**

It does not prevent OMPL from searching curved paths.

This eliminates one suspected source of accidental planner overconstraint.

---

## 9. Current first-invalid collision evidence

For the current live Goal 1 failure, the direct Home→PreEntry interpolation first encounters a collision between:

**`pneumatic_spindle-Copy`**

and a MoveIt anatomy object with a name like:

**`dentobot_tooth_<segment-id>_<fingerprint>`**

The object naming contract confirms this is a **non-target tooth** collision object.

It is not the target tooth prefix.

The exact FDI number is not embedded directly in the object ID, so it requires runtime segmentation metadata to map that segment ID to FDI.

The anatomy object appears to be legitimate:

- sourced from the teeth segmentation,
- converted to world/base geometry,
- expected in the planning scene,
- not obviously duplicated as a second MoveIt obstacle.

Therefore the current evidence does **not** indicate an obvious stale duplicate or fake anatomy obstacle.

---

## 10. Spindle collision geometry audit

The spindle housing collision model is:

**`pneumatic_spindle-Copy`**

The URDF audit established:

- visual geometry = spindle STL
- collision geometry = same spindle STL
- same mesh scale
- same origin
- same rotation
- no intentional collision inflation
- approximate mesh extent ≈ **63 × 12.5 × 13.6 mm**
- `dentobot_drill_tcp` itself has no collision geometry
- the spindle housing and burr provide the actual tool-side collision geometry

Therefore:

> There is no obvious “huge oversized box” or visual-vs-collision transform mismatch in the URDF.

That does **not** prove the geometry is physically correct. It only means the collision geometry is faithfully following the current CAD mesh.

---

## 11. Why the spindle has become a major suspect

The spindle housing has independently appeared in multiple failures.

### Historical Stage 3 failure
Earlier FDI31 full-chain testing passed:

- Stage 1 Home→PreEntry
- Stage 2 PreEntry→Entry

and then Stage 3 Entry→Target failed because:

**target tooth ↔ `pneumatic_spindle-Copy`**

### Current Stage 1 failure
Current live Goal 1 Home→PreEntry diagnostic shows:

**non-target tooth ↔ `pneumatic_spindle-Copy`**

This repetition matters.

It suggests the spindle housing volume may be a genuine limiting geometry throughout the task, not a one-off planner artifact.

---

# 12. The three active culprit hypotheses

These three must remain separate until experiments discriminate them.

---

## CULPRIT 1 — Task Home / configuration-space connectivity

### Hypothesis
The saved Task Home is on a poor side of configuration space relative to the valid PreEntry branches.

Both endpoints can be collision-free while the connecting free-space path is difficult or impossible because the spindle sweeps through the dentition.

### Why plausible
- Three valid collision-free PreEntry endpoints exist.
- OMPL cannot connect Task Home to them.
- The spindle collides during the direct joint chord.
- Joint-space motion can create large Cartesian sweeps.

### Diagnostic experiment
Choose a temporary Task Home closer to the accepted PreEntry branch but still clearly outside anatomy.

Keep everything else unchanged.

If:

**new Home → same PreEntry succeeds**

then Task Home placement/connectivity is a major contributor.

### Important interpretation
This would not mean the robot is “fixed”; it would mean the original Home posture is unsuitable for this task geometry.

---

## CULPRIT 2 — Planner/orchestration/search behavior

### Hypothesis
Although the core planner is valid OMPL, the surrounding Goal 1 orchestration may still be restricting search quality or wasting planning effort.

### What has already been ruled out
The following are **not** currently the problem:

- straight interpolation being used as a hard gate
- full 6-DOF orientation constraint during Home→PreEntry
- J6 contaminating the planning group
- fake roll sweeps
- manual Cartesian path construction for the direct route

### Remaining planner questions
Potentially relevant issues still include:

- only one OMPL planning attempt per candidate
- 5 s planning time
- default RRTConnect settings
- candidate ranking order
- whether valid branches receive enough planning effort
- whether the scene is so constrained that more planner diversity is required
- whether clearance-detour fallback helps or just adds complexity

### Important mental model
Culprit 2 is no longer “Codex replaced MoveIt with straight-line hacks.”

It is now the narrower question:

> Is the current OMPL invocation/search policy adequate for this constrained configuration-space problem?

---

## CULPRIT 3 — Spindle housing collision constraint / physical geometry

### Hypothesis
The actual spindle housing volume is the dominant obstacle preventing a feasible approach.

### Why plausible
- spindle housing causes current P1 collision
- spindle housing caused historical P3 collision
- collision mesh appears to faithfully match the current CAD spindle
- anatomy object appears legitimate
- IK endpoints remain valid

### Tarun’s proposed diagnostic experiment
Temporarily remove **only the spindle housing collision geometry** and rerun the exact same Goal 1.

Keep unchanged:

- J1–J5 kinematics
- `dentobot_drill_tcp`
- spindle link/frame
- burr collision
- robot placement
- Task Home
- trajectory
- patient anatomy collision objects
- MoveIt settings
- OMPL planner
- Goal 1 workflow

Only suppress:

**`pneumatic_spindle-Copy` collision geometry**

### Why this experiment is valuable
It asks one clean question:

> If the spindle housing occupied no collision volume, could this robot/planner connect Home to PreEntry?

### Outcome interpretation

#### If Goal 1 succeeds
Culprit 3 is strongly confirmed as the dominant current blocker.

Then:
- kinematics are viable,
- PreEntry IK is viable,
- MoveIt connectivity is viable once spindle volume is removed,
- next problem becomes mechanical architecture / placement / spindle envelope / approach strategy.

This is an acceptable R&D outcome.

#### If planner advances and hits another collision
The spindle is one blocker but not the only blocker.

Record the new first-invalid pair.

#### If Goal 1 still fails with spindle collision removed
Shift diagnostic priority back toward Culprit 1 and Culprit 2.

#### If Stage 1 succeeds but Stage 2/3 fails
Good diagnostic progress:
- Home→PreEntry is no longer the blocker.
- next problem belongs to insertion/drilling geometry.

---

## 13. Preferred way to perform Culprit 3 test

The cleanest experiment is to suppress the spindle’s **collision geometry only**.

Do NOT delete:

- the spindle link,
- J5→spindle structural transform,
- visual mesh,
- `dentobot_drill_tcp`,
- burr,
- tool-frame chain.

Conceptually:

**J5 → spindle link**
- visual = KEEP
- frame = KEEP
- TCP fixed transform = KEEP
- spindle collision mesh = TEMPORARILY OFF

Prefer a reversible development-only mechanism or diagnostic URDF variant.

Avoid making a broad “allow spindle ↔ all teeth” ACM exception unless necessary, because the stack contains both MoveIt and an independent collision/phase guard and it would be harder to guarantee every collision consumer uses the same exception.

---

## 14. Current planner route taxonomy

Goal 1 currently has several route labels, but they are less exotic than they first appeared.

### `direct`
- IK seed = Task Home
- result = one PreEntry joint solution
- route = one OMPL Home→PreEntry plan

### `seeded`
- IK seed = HomeConnected Step 6.3 sample
- result = a different PreEntry joint branch
- route = one OMPL Home→PreEntry plan

### `clearance-detour`
- Home → retained 6.3 clearance posture
- clearance posture → PreEntry
- each leg individually planned using OMPL

Therefore the custom route machinery is mostly choosing alternate seeds/waypoints; it is not replacing OMPL with handcrafted paths.

This means simplification may still be useful, but the current blocker should not be blamed on “fake path planning” without further evidence.

---

## 15. Historical vs current failure must not be conflated

There are two distinct failure regimes.

### Historical FDI31 r13
- Stage 1 PASS
- Stage 2 PASS
- Stage 3 FAIL
- target tooth ↔ spindle housing collision

### Current live session
- PreEntry IK endpoints exist
- Goal 1 cannot connect Task Home → PreEntry
- diagnostic first-invalid collision involves non-target tooth ↔ spindle housing

These may share a physical spindle-envelope problem, but they are not the same motion failure.

Do not treat historical P3 evidence as proof of current P1 root cause.

---

## 16. Things currently considered proven enough to stop re-investigating

Unless new evidence contradicts them, do not spend another session re-proving:

- MoveIt planning group is J1–J5.
- J6 is not part of the Step 6 planning group.
- current PreEntry IK is position + axis, not full 6-DOF.
- axial roll is unconstrained.
- current live run has at least 3 valid collision-aware PreEntry IK endpoints.
- Home→PreEntry uses real OMPL/RRTConnect planning.
- direct interpolation collision is diagnostic only and occurs after OMPL failure.
- spindle visual/collision meshes currently use the same STL/transform.
- the current colliding tooth object is a legitimate non-target anatomy obstacle class.

These are now baseline assumptions.

---

## 17. Things that should NOT be “fixed” blindly

Do not immediately:

- rewrite the IK solver,
- add more roll sweeps,
- reintroduce J6 into planning,
- increase candidate count,
- add more diagnostic route types,
- delete patient tooth collisions,
- globally disable collision checking,
- loosen FK tolerances,
- remove the spindle link itself,
- redesign the robot before the collision-off diagnostic,
- assume OMPL is broken merely because one run failed.

Each of those would destroy useful diagnostic isolation.

---

## 18. Recommended next experimental order when work resumes

### Experiment 1 — Spindle collision OFF
This is currently Tarun’s preferred immediate experiment.

Purpose:
- isolate Culprit 3.

Change:
- suppress only `pneumatic_spindle-Copy` collision geometry.

Keep everything else identical.

Record:
- whether Goal 1 succeeds,
- selected PreEntry branch,
- first new failure if any,
- whether Stage 2/3 become reachable.

### Experiment 2 — Alternate temporary Task Home
If spindle-off does not fully resolve the problem, or once spindle geometry is understood:

- choose a temporary clear Home closer to a known valid PreEntry branch,
- save as Task Home,
- rerun Goal 1.

Purpose:
- isolate Culprit 1.

### Experiment 3 — Planner search policy
If valid endpoints exist and collision geometry appears feasible but OMPL still fails:

Test controlled planner changes such as:
- increased allowed planning time,
- multiple OMPL attempts,
- alternative OMPL planner(s),
- same start/goal with no custom detour,
- compare candidate branches individually.

Purpose:
- isolate Culprit 2.

Do this **after** physical collision feasibility is better understood.

---

## 19. Evidence that should be captured for every experiment

For each run record:

1. exact Task Home J1–J5
2. robot placement / base transform fingerprint
3. selected trajectory ID
4. PreEntry / Entry / Target coordinates
5. valid PreEntry IK candidate count
6. chosen candidate joint values
7. planner ID
8. planning time
9. OMPL success/failure
10. first-invalid collision pair if any
11. stage reached:
   - P1 Home→PreEntry
   - P2 PreEntry→Entry
   - P3 Entry→Target
12. whether spindle collision was enabled
13. whether burr collision remained enabled
14. whether patient collisions remained enabled

This lets comparisons remain causal rather than anecdotal.

---

## 20. Current mental model in one compact diagram

```text
                          CURRENT VERIFIED STATE
                                  │
                                  ▼
                         Entry/Target geometry
                                  │
                                  ▼
                 5-constraint J1–J5 PreEntry IK
                                  │
                         SUCCESS: 3 endpoints
                                  │
                                  ▼
                           Task Home state
                                  │
                                  ▼
                    OMPL RRTConnect joint plan
                                  │
                              CURRENT FAIL
                                  │
                ┌─────────────────┼─────────────────┐
                │                 │                 │
                ▼                 ▼                 ▼
        CULPRIT 1           CULPRIT 2         CULPRIT 3
        Home / C-space      planner search     spindle-body
        connectivity        policy/orchestration collision volume
                │                 │                 │
                │                 │                 │
      alternate Home       planner policy     spindle collision OFF
          experiment         experiment          experiment
```

---

# 21. Restart statement for the next debugging session

When resuming work, use this as the starting statement:

> We are no longer debugging PreEntry reachability. The live system already produced three collision-aware J1–J5 PreEntry IK endpoints with authoritative FK validation. The active failure is Task Home → PreEntry free-space connection. The current evidence supports three separate hypotheses: (1) unsuitable Task Home / configuration-space connectivity, (2) insufficient OMPL search policy or surrounding route orchestration, and (3) the physical spindle housing collision envelope. J6 is not part of the Step 6 MoveIt group and is not the current primary suspect. The 30.2% direct interpolation collision is diagnostic only and occurs after OMPL failure. The next preferred experiment is to suppress only `pneumatic_spindle-Copy` collision geometry while preserving the link, TCP, burr collision, anatomy, robot placement, trajectory, and planner settings. If that allows Goal 1 to succeed, the current software/kinematic stack is likely viable and the spindle-envelope problem becomes a new mechanical/planning design task rather than a reason to further complicate the planner.

---

## 22. Source records used for this diagnosis

- `PLANNER_IMPLEMENTATION_MAP_2026-09-20.md`
- `preentry-ik-moveit-queries-2026-09-20.md`
- `joint-goal-planning-queries-2026-09-20.md`
- current live Step 6 screenshot showing 3 collision-aware PreEntry endpoints and Home→PreEntry failure
