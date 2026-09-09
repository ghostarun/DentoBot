# DENTOBOT Agentic Verification Protocol

This is the canonical verification and subagent contract for Codex, Cursor,
Claude, and future agentic tools. Tool-specific instruction files must point
here instead of copying these rules.

## Verification economy — adopted 2026-09-09

Choose the cheapest evidence that can resolve the current question. Full
SlicerROS2 startup, rebuilds and complete workflow runs are final validation
tools, not the default debugging loop. This section integrates the operator's
`CODEX_TESTING_VERIFICATION_POLICY.md`; provenance and interpretation are in
DECISIONS.md and today's logbook. Its P0–P5 policy labels do not assign or change
TASKS.md priorities. Model/effort limits remain in `Workspace/AGENTS.md`.

Before execution, specify the question, relevant source/case identity,
hypothesis, smallest check, expected discriminating result, evidence level and
stop condition. Reuse existing evidence when its inputs/build/policy match;
saved evidence never restores live scene or guard validity. Reading source,
logs and documentation is not permission to execute a test.

| Level | Choose when it answers the question | Scope |
|---|---|---|
| 0 — inspect | Existing source, logs, settings or saved evidence suffice | Callers, units/frames, dimensions, registration, first causal error |
| 1 — isolated logic | Behavior can be reproduced without Slicer/ROS | One relevant function/fixture; geometry, transforms, clipping, serialization |
| 2 — narrow runtime | Runtime ownership or native behavior is necessary | One Slicer logic path, ROS node, guard or MoveIt request |
| 3 — focused integration | The defect crosses a subsystem boundary | One explicit Slicer→ROS, scene→guard or trajectory→planner question |
| 4 — full workflow | Lower applicable checks pass and end-to-end evidence is required | Complete guarded simulation and required repeat cycle |

The ladder is a selection rule, not five mandatory runs. Explain why cheaper
evidence is insufficient when selecting a higher level. Preserve matrix
dependencies; reuse a matching successful dependency or record an inapplicable
conditional build, rather than inventing meaningless lower-level tests.
Profiles select candidate checks, not automatic permission to run every check.
Resolve paths from the checkout root
`/home/light-tarun/dentobot/ros2_ws/src/DentoBot`; the matrix is
`Testing/verification_matrix.json` there (`../Testing` from `Workspace`, not
from the overlay root). A missing matrix command requires a concrete bounded
command in the proposed plan; never guess an invocation and execute it.

### Retry budget and stop conditions

Count failed executions against the same causal blocker, across commands,
workers, sessions and resumed tasks. Record the count and evidence in the run
record/logbook; a renamed run or parameter variation does not reset it.

1. First failure: preserve the earliest causal evidence and inspect it.
2. Second attempt: test one evidence-backed correction/hypothesis with the
   smallest relevant check, within approved scope.
3. A third attempt is permitted only if attempt two adds diagnostic evidence
   or the third tests a clearly different, stated hypothesis.

After three failures, stop autonomous retries on that blocker and ask Tarun
for the specific missing judgment/input. Three is a ceiling, not a target.
Stop earlier for a full-runtime failure with no new information, ambiguous
geometry/UI state, decision-critical unknown dimensions, questionable anatomy
or case validity, competing fixes requiring a design choice, or a proposed
safety relaxation. Continue independent authorized work while input is pending.
Resume the blocked check only after relevant operator guidance or an explicitly
approved revised plan, preserving the previous attempt history.

### Visual evidence and human escalation

For a new collision blocker, identify the exact bodies and save the stage,
waypoint, joints (names/units), tool pose/frame, scene identity and signed
distance/penetration with units if available. Mark missing fields `unknown`;
neither a planner fraction nor visual overlap proves collision.

Capture a context view and a close-up (alternate angle if useful) showing the
offending bodies and relevant axis/pose before trying geometric fixes. Use
retained artifacts or the already approved runtime first. A screenshot must
match the reported state; any reconstructed display is labelled as such.
Screenshots explain geometry; numerical guard evidence remains authoritative.
Do not start/restart Slicer, move the robot, replace an operator scene or relax
guards merely to obtain a picture without the applicable authorization. If no
safe capture is available, report that limitation immediately with the retained
diagnostic and a concrete capture/manual-inspection request; do not replace
missing visual evidence with repeated runtime guesses. Exclude patient identity.

For UI ambiguity, retain substep, target, readiness/button states and visible
versus hidden relevant objects; ask for the missing workflow observation.
Escalate early when a short operator visual review can settle the question.
Send one compact blocker package:

- Expected/actual behavior and exact failed step/waypoint.
- Only relevant configuration: target, depth, tool/guide dimensions, base,
  branch, pose/limits, guard policy and simulation assumptions.
- First error, exact pair/distance if present, and links to logs/images.
- At most three attempted actions; current hypothesis in one or two sentences.
- One narrow question whose answer selects the next bounded action.

At most one cheap discriminating check per hypothesis. Do not conduct blind
parameter sweeps unless explicitly requested. Authorized variations change one
parameter class and record the baseline and expected distinction. Changing
base, burr, guide, depth or a safety margin requires the existing scope/approval;
examples in the imported policy are not authorization. Never tune around unknown
physical dimensions. Label any approved provisional values `SIMULATION-ONLY`
with rationale, measurement needed to replace them and safety interpretation.
Do not promote them to requirements. Retired abnormal pre-surgery/x4 anatomy
remains a negative fixture; do not confuse it with every filename containing x4
or force it into acceptance through planner/geometry exceptions.

### Build and regression selection

Prefer reload or an isolated check for Python/data/fixture changes. Establish
that the intended code/assets are actually loaded; use a package install/build
only if deployment requires it. A changed compiled constant still needs its
owning native package rebuilt even if described as a threshold-only change.
Use incremental package builds for changed C++/interfaces/CMake. A full rebuild
needs a specific dependency/image/build reason and an explanation of why the
narrower build is insufficient. No unrelated container rebuilds after edits.

| Changed behavior | First meaningful regression scope |
|---|---|
| Template/boundary | Boundary processing, shell connectivity, unified geometry |
| Trajectory | Entry/direction preservation, endpoint policy, validity |
| Planning | Route/joint limits and guard, then affected stage/integration |
| Collision guard | Known safe, known forbidden, threshold edge, stale-object cleanup |
| Restore/UI lifecycle | State/serialization first, then affected load/reload interaction |

Run the applicable smoke/regression gate after targeted success or a meaningful
integration change, once for the resulting revision. Broaden/repeat only for
new changes, failures or unresolved risks; avoid tests mirroring trivial edits.
Required safety, native and full-cycle acceptance checks cannot be skipped for
economy. Documentation-only edits use readback/link/consistency inspection;
they do not require application tests. Matrix test/build commands retain their
approval classes, including static commands listed there.

### Completion claims

Report separate evidence levels: **Implemented**, **Unit Verified**, **Runtime
Verified**, **Integration Verified**, **Full-Cycle Verified**, and **Operator
Verified**. Scope each label to the tested behavior/case/revision. Inspection
or compilation is not Unit Verified; a build is not runtime evidence; functional
PASS with nonzero shutdown remains two outcomes. Do not say “fixed” on source
implementation alone. Operator acceptance is never inferred from an agent run.

The current full-cycle gate remains Task Home→guarded approach→PreEntry→Entry→
exact effective Target→guarded axial withdrawal→Home, then the required fresh
repeat cycle. Use current reviewed geometry, trajectory, joint/phase/guard
policy and explicitly recorded provisional assumptions; historical abbreviated
workflow arrows do not omit Entry, endpoint verification, withdrawal or repeat.
Authorized guide warnings retain their exact scope and evidence. This policy
does not create, widen or revoke a case-specific contact authorization, and
full-cycle simulation evidence is not hardware/clinical acceptance.

## Safety and authority

- Verification is simulation/research evidence only. It never authorizes robot
  motion, powered drilling, patient use, collision-policy relaxation, deletion,
  Git publication, or Google Drive synchronization.
- `DENTO-VERIFY PLAN <profile>` selects checks from
  `Testing/verification_matrix.json`, explains commands, dependencies,
  resources, expected evidence, and the next action, but executes nothing.
- `DENTO-VERIFY <profile>` also starts with the plan. Execution begins only
  after the operator explicitly approves that proposed plan in the current
  task. A keyword alone does not bypass approval.
- `DENTO-VERIFY STATUS <run-id>` reads existing evidence only.
- `DENTO-VERIFY RESUME <run-id>` proposes the smallest continuation after the
  failed or interrupted gate; newly introduced resources require approval.
- The operator may narrow or withdraw approval at any time. The latest scope
  wins immediately.
- Reuse approval already granted in this task for the same bounded plan; do not
  ask again per command. New scope/resources, safety-relevant input changes or
  continuation beyond the retry ceiling need the corresponding new decision.
  Complete authorized inspection/implementation before presenting a concrete
  execution plan. This policy update is not itself test/runtime authorization.

## Coordinator and workers

The coordinator is the sole controlled-document editor and owns integration
and final acceptance. Under the operator's corrected model policy in
`Workspace/AGENTS.md`, a Luna Max implementation worker may edit only explicitly
assigned code/test files after Astra light supplies the complete plan. This
exception does not apply to verification workers and does not authorize tests
or runtime execution. Do not overlap writes or check actively changing files.

Verification workers are read-only. A verification worker discovering a defect reports
it; it does not patch source, change parameters, relax collision rules, or
silently retry with different inputs.

For Codex model/effort selection, follow `Workspace/AGENTS.md` (Astra light
ceiling applies only to Astra; Luna Max implements, Terra High verifies).
Default to solo, or one justified auxiliary. The three workers below are available responsibilities, not a
mandatory team. More than one requires an explicit operator request or approved
verification plan. The matrix limit is a hard maximum, not a target.

Use at most three workers alongside the coordinator:

1. **Static worker** — Python compilation, Git diff checks, contracts.
2. **Pure-test/package worker** — scoped pytest and read-only package/schema
   inspection.
3. **Runtime worker** — the sole owner of Docker, ROS domain 73, Slicer,
   MoveIt, display, install tree, and the active MRML scene.

A diagnostic worker, if justified, is created or resumed only after a runtime failure and
uses the runtime worker's saved evidence. It remains read-only and does not
re-plan unless the approved check explicitly requires a reproduction.

Use the tool's native isolated subagent mechanism:

- **Codex:** spawn with no inherited chat history where supported; send a
  self-contained bounded prompt and reuse the same agent for retries.
- **Cursor:** use a self-contained read-only subagent/custom-agent task and
  resume it for retries.
- **Claude:** use a fresh read-only subagent prompt and resume the same task for
  follow-up diagnosis.

Do not depend on a tool-specific API name in shared prompts. Every worker gets
only the repository path, compact context path, matrix check IDs, approved
commands, expected PASS condition, forbidden actions, evidence directory, and
the result contract below.

## Parallel and sequential execution

Only checks whose matrix entry says `parallel_safe: true` may overlap. Runtime
resources are exclusive even when two commands appear independent.

```text
static/pure/package checks (parallel-safe)
                 |
                 v
conditional colcon build (exclusive install tree)
                 |
                 v
one Slicer/ROS/MoveIt runtime check at a time
                 |
          pass --+-- fail -> inspect saved evidence; optional diagnostic worker
                 |
                 v
manual normal-window operator acceptance
```

Exclusive resources are:

- `docker:dentobot-slicerros2`
- `ros_domain:73`
- `slicer_process`
- `mrml_scene`
- `display`
- `colcon_install`

Do not run two Slicer processes, two ROS/MoveIt campaigns, a build and runtime,
or two scene-lifecycle checks concurrently against those resources. Creating
extra containers or ROS domains merely to gain parallelism is deferred until a
measured need justifies the added isolation.

## Runtime transaction

For every approved runtime check, the runtime worker must:

1. acquire all declared exclusive resources;
2. record container/image, source revision/diff identity, ROS domain, case
   checksum, build identity, exact command, and start time;
3. inspect for a pre-existing operator-owned Slicer/ROS process and stop rather
   than killing or replacing it without approval;
4. start only the required stack and run one matrix check;
5. capture the declared PASS/FAIL marker, exit code, first failure, and bounded
   tail while writing full output to the evidence directory;
6. terminate only processes started by that worker and verify teardown; and
7. release resources before another runtime check starts.

A PASS marker followed by a non-zero shutdown must be reported as two pieces of
evidence, not collapsed into PASS or FAIL. Scene-clear, VTK leak, or native
abort evidence remains visible.

## Evidence and token budget

Use `/tmp/dentobot-verification/<run-id>/`. Each check writes its complete log
there and a compact `result.json`. Do not paste full logs into agent chat or
controlled documents.

Each worker returns at most 12 lines containing:

- check ID and status: `PASS`, `FAIL`, `BLOCKED`, or `NOT_RUN`;
- exact command and exit code;
- PASS/FAIL marker;
- first causal failure, not every downstream error;
- evidence paths;
- cleanup status; and
- one recommended next action.

Use a self-contained prompt instead of copying the parent conversation. Read
`Workspace/docs/AGENT_CONTEXT.md` plus only the matrix-routed source/docs.
Reuse a worker for retries. Within one run, a successful unchanged check may be
skipped; persistent cross-run caching is deferred.

## Failure routing

| Failure | Read-only diagnosis owner | Required first evidence |
|---|---|---|
| Python/contract | Static worker | file, line, exception/assertion |
| Package/schema | Package worker | package checksum, schema, first mismatch |
| Colcon/C++ | Runtime/build worker | package, first compiler/linker error |
| Slicer startup/reload/clear | Runtime worker | process exit, terminal tail, lifecycle phase |
| ROS ownership/readiness | Runtime worker | node/topic/service snapshot and owner |
| MoveIt Stage 1/2/3 | Diagnostic worker | structured motion report below |

The coordinator and operator decide whether to start a separate implementation
turn. A verification worker never converts diagnosis into a source change.

## Three-stage MoveIt failure report

Read `MotionDiagnosticSession` evidence first. Do not infer collision merely
from an IK endpoint or partial fraction. Report:

- failed stage: Home→PreEntry, PreEntry→Entry, or Entry→Target;
- task, trajectory, base, Home, robot, tool/frame, and collision-scene
  fingerprints;
- direct, seeded, or clearance-detour route and IK seed identity;
- planner error/status, fraction, distance, and waypoint counts;
- first invalid composed and stage-local waypoint;
- last-valid and first-invalid joint vectors where retained;
- first collision pair, bounds/corridor/backtrack/overshoot/identity cause, or
  explicit `unknown`;
- fixed-frame fingerprint and J6 lock state; and
- whether only a provisional Stage-1 preview remains.

Diagnostics are explanatory only. They cannot authorize a partial drilling
path, non-tool contact, new collision exemption, hardware action, or a clinical
claim.

## Matrix maintenance

- The matrix inventories existing checks; it is not a second test harness.
- Add a row when a reusable check already exists or a new acceptance gate is
  deliberately introduced.
- Every row declares dependencies, resources, approval class, timeout, evidence
  level, command/entrypoint, and PASS condition.
- Builds run only when their owned production sources changed or the operator
  requests a clean rebuild.
- Manual gates have no executable command and are never delegated.
